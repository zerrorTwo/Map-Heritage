"""
Step 6 — Route optimization with OSRM real road routing.
Uses OSRM public API for distance matrix + route geometry.
Fallback to haversine if OSRM is unreachable.
"""

import json
import logging
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from itertools import permutations
from typing import List, Tuple, Optional
from config import settings
from services.ai_service.models import ScoredSite
import numpy as np

OSRM_BASE = settings.osrm_base_url.rstrip("/") or "https://router.project-osrm.org"
OSRM_TIMEOUT_SECONDS = 3
log = logging.getLogger("pipeline")


@dataclass
class OpenRouteResult:
    """Road-routing result with matrices retained for final itinerary reporting."""

    ordered_sites: List[ScoredSite]
    distance_matrix: Optional[np.ndarray]
    duration_matrix: Optional[np.ndarray]
    total_duration_s: Optional[float]


def _coords_key(coords: List[Tuple[float, float]]) -> Tuple[Tuple[float, float], ...]:
    return tuple((round(lat, 6), round(lng, 6)) for lat, lng in coords)


@lru_cache(maxsize=512)
def _cached_osrm_request(endpoint: str, coords: Tuple[Tuple[float, float], ...], extra_params: str = "") -> Optional[dict]:
    """Call OSRM API and return parsed JSON."""
    coord_str = ";".join(f"{lng},{lat}" for lat, lng in coords)
    url = f"{OSRM_BASE}/{endpoint}/{coord_str}?annotations=distance,duration{extra_params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "heritage-planner/1.0"})
        with urllib.request.urlopen(req, timeout=OSRM_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        log.info(f"  OSRM fallback: {endpoint} failed ({type(exc).__name__})")
        return None


def _osrm_request(endpoint: str, coords: List[Tuple[float, float]], extra_params: str = "") -> Optional[dict]:
    return _cached_osrm_request(endpoint, _coords_key(coords), extra_params)


def get_route_geometry(
    sites: List[ScoredSite],
    start: Optional[Tuple[float, float]] = None,
    end: Optional[Tuple[float, float]] = None,
) -> Optional[list]:
    """
    Get the route LineString geometry from OSRM for a list of ordered sites.
    Optional `start`/`end` anchors (lat, lng) connect the day to the trip origin,
    the previous day, and/or the trip end so the drawn route is continuous.
    Returns GeoJSON LineString coordinates [[lng,lat],...] or None.

    If the straight-line distance between the first and last site exceeds
    500 km (indicating an island or water crossing that OSRM cannot route),
    falls back to simple straight-line geometry to avoid broken coastal paths.
    """
    site_coords = [(s.site.lat, s.site.lng) for s in sites]
    coords = (
        ([start] if start else [])
        + site_coords
        + ([end] if end else [])
    )
    if len(coords) < 2:
        return None

    # Pre-check: skip OSRM for clusters with any consecutive pair > 150 km
    # apart (e.g. mainland-to-island like Côn Đảo) — OSRM produces broken paths
    if len(sites) >= 2:
        import math
        for i in range(len(site_coords) - 1):
            a, b = site_coords[i], site_coords[i + 1]
            dlat = (b[0] - a[0]) * 111.32
            dlng = (b[1] - a[1]) * 111.32 * 0.85
            if math.sqrt(dlat * dlat + dlng * dlng) > 150:
                return [[lng, lat] for (lat, lng) in coords]

    result = _osrm_request("route/v1/driving", coords, extra_params="&geometries=geojson&overview=simplified")
    if result and "routes" in result and len(result["routes"]) > 0:
        geom = result["routes"][0].get("geometry")
        if isinstance(geom, dict):
            return geom.get("coordinates", [])
        # If polyline string, decode
        if isinstance(geom, str) and geom:
            return _decode_polyline(geom)
    # Fallback: straight-line segments so the route stays connected without OSRM
    return [[lng, lat] for (lat, lng) in coords]


def _decode_polyline(polyline_str: str, precision: int = 5) -> list:
    """Decode OSRM polyline string to [[lng,lat],...]"""
    coords = []
    index, lat, lng = 0, 0, 0
    factor = 10 ** precision
    while index < len(polyline_str):
        result = 0; shift = 0
        while True:
            byte = ord(polyline_str[index]) - 63; index += 1
            result |= (byte & 0x1f) << shift; shift += 5
            if byte < 0x20: break
        dlat = ~(result >> 1) if result & 1 else result >> 1
        lat += dlat
        result = 0; shift = 0
        while True:
            byte = ord(polyline_str[index]) - 63; index += 1
            result |= (byte & 0x1f) << shift; shift += 5
            if byte < 0x20: break
        dlng = ~(result >> 1) if result & 1 else result >> 1
        lng += dlng
        coords.append([lng / factor, lat / factor])
    return coords


def two_opt_open(
    route: List[int],
    cost_matrix: np.ndarray,
    start_index: Optional[int] = None,
    end_index: Optional[int] = None,
    max_iter: int = 200,
) -> List[int]:
    """2-opt for site order while keeping optional anchors fixed outside the route."""
    best = list(route)
    n = len(best)
    if n <= 1:
        return best

    def _path_cost(r: List[int]) -> float:
        total = 0.0
        if start_index is not None:
            total += cost_matrix[start_index][r[0]]
        total += sum(cost_matrix[r[i]][r[i + 1]] for i in range(n - 1))
        if end_index is not None:
            total += cost_matrix[r[-1]][end_index]
        return float(total)

    best_cost = _path_cost(best)
    for _ in range(max_iter):
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                candidate_cost = _path_cost(candidate)
                if candidate_cost < best_cost - 1e-6:
                    best = candidate
                    best_cost = candidate_cost
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break
    return best


def _open_path_cost(
    route: List[int], cost_matrix: np.ndarray,
    start_index: Optional[int], end_index: Optional[int],
) -> float:
    if not route:
        return 0.0
    total = 0.0
    if start_index is not None:
        total += cost_matrix[start_index][route[0]]
    total += sum(cost_matrix[route[i]][route[i + 1]] for i in range(len(route) - 1))
    if end_index is not None:
        total += cost_matrix[route[-1]][end_index]
    return float(total)


def _nearest_neighbor_open(
    site_indices: List[int], cost_matrix: np.ndarray, start_index: Optional[int], first_site: Optional[int] = None,
) -> List[int]:
    if not site_indices:
        return []
    if first_site is None:
        first_site = min(site_indices, key=lambda site: cost_matrix[start_index][site])
    route = [first_site]
    unvisited = set(site_indices)
    unvisited.remove(first_site)
    while unvisited:
        current = route[-1]
        next_site = min(unvisited, key=lambda site: cost_matrix[current][site])
        route.append(next_site)
        unvisited.remove(next_site)
    return route


def _valid_osrm_matrix(values, expected_size: int) -> Optional[np.ndarray]:
    try:
        matrix = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        return None
    if matrix.shape != (expected_size, expected_size) or not np.isfinite(matrix).all():
        return None
    return matrix


def optimize_route_open(
    cluster: List[ScoredSite],
    start_anchor: Optional[Tuple[float, float]] = None,
    end_anchor: Optional[Tuple[float, float]] = None,
) -> OpenRouteResult:
    """Optimize site order using one OSRM duration table with fixed anchors.

    The OSRM request contains ``[start?, sites..., end?]`` so every directed
    cost uses the same road-duration unit. On malformed, unavailable, or
    unreachable data the original TTDP order is retained with no matrices.
    """
    n = len(cluster)
    if n == 0:
        return OpenRouteResult([], np.zeros((0, 0)), np.zeros((0, 0)), 0.0)

    coords = ([] if start_anchor is None else [start_anchor]) + [
        (site.site.lat, site.site.lng) for site in cluster
    ] + ([] if end_anchor is None else [end_anchor])
    result = _osrm_request("table/v1/driving", coords)
    if result is None or result.get("code") != "Ok":
        return OpenRouteResult(list(cluster), None, None, None)

    duration_full = _valid_osrm_matrix(result.get("durations"), len(coords))
    distance_full = _valid_osrm_matrix(result.get("distances"), len(coords))
    if duration_full is None or distance_full is None:
        return OpenRouteResult(list(cluster), None, None, None)

    start_index = 0 if start_anchor is not None else None
    site_offset = 1 if start_anchor is not None else 0
    site_indices = list(range(site_offset, site_offset + n))
    end_index = len(coords) - 1 if end_anchor is not None else None

    # Exact search is inexpensive for normal 3–7-stop days and avoids local
    # minima. Larger clusters use multiple nearest-neighbor starts plus 2-opt.
    if n <= 8:
        best_route = min(
            permutations(site_indices),
            key=lambda route: _open_path_cost(list(route), duration_full, start_index, end_index),
        )
        ordered_indices = list(best_route)
    else:
        seeds = [None] if start_index is not None else site_indices
        candidates = []
        for seed in seeds:
            route = _nearest_neighbor_open(site_indices, duration_full, start_index, seed)
            route = two_opt_open(route, duration_full, start_index, end_index)
            candidates.append(route)
        ordered_indices = min(
            candidates,
            key=lambda route: _open_path_cost(route, duration_full, start_index, end_index),
        )

    original_indices = [index - site_offset for index in ordered_indices]
    ordered_sites = [cluster[index] for index in original_indices]
    ordered_duration = duration_full[np.ix_(ordered_indices, ordered_indices)]
    ordered_distance = distance_full[np.ix_(ordered_indices, ordered_indices)]
    total_duration = _open_path_cost(ordered_indices, duration_full, start_index, end_index)
    return OpenRouteResult(ordered_sites, ordered_distance, ordered_duration, total_duration)
