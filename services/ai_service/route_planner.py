"""Spec-compliant route planner from alth.md.

This endpoint solves fixed-start/fixed-end sequencing with OSRM road costs,
then asks OSRM for the final route geometry.
"""

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import numpy as np

from config import settings
from services.ai_service.models import (
    PlannerPoint,
    PlannerSite,
    RoutePlanDay,
    RoutePlanRequest,
    RoutePlanResponse,
    RoutePlanStop,
)

try:
    from sklearn.cluster import KMeans
except ImportError:  # pragma: no cover - dependency is optional at runtime
    KMeans = None

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
except ImportError:  # pragma: no cover - dependency is optional at runtime
    pywrapcp = None
    routing_enums_pb2 = None


OSRM_BASE = settings.osrm_base_url.rstrip("/")
OSRM_FALLBACK_BASES = [
    "http://heritage_osrm:5000",
    "http://localhost:5000",
    "http://host.docker.internal:5000",
]
REQUEST_TIMEOUT_SECONDS = 15
UNREACHABLE_COST = 10**12


def plan_route(request: RoutePlanRequest) -> RoutePlanResponse:
    warnings: List[str] = []
    if request.transport_mode == "transit":
        return RoutePlanResponse(
            status="error",
            warnings=["transport_mode=transit requires a GTFS routing engine; OSRM cannot serve transit routes"],
        )
    if request.transport_mode in {"motorbike", "walking"}:
        warnings.append(f"transport_mode={request.transport_mode} is routed with OSRM driving profile")
    if request.constraints.avoid_highways or request.constraints.avoid_tolls:
        warnings.append("avoid_highways/avoid_tolls are not supported by the current OSRM car profile")

    try:
        start = _resolve_point(request.start)
        end = _resolve_point(request.end)
        sites = [_resolve_site(site, request.province) for site in request.sites]
    except ValueError as exc:
        return RoutePlanResponse(status="error", warnings=[str(exc)])

    if not sites:
        try:
            route = _fetch_route([start, end])
        except ValueError as exc:
            return RoutePlanResponse(status="error", warnings=[str(exc)])
        distance_km = round(route["distance_m"] / 1000, 2)
        duration_min = math.ceil(route["duration_s"] / 60)
        return RoutePlanResponse(
            status=_status_for_limits(distance_km, duration_min, request, warnings),
            total_distance_km=distance_km,
            total_duration_min=duration_min,
            days=[RoutePlanDay(day=1, stops=[], polyline=route["polyline"])],
            warnings=warnings,
        )

    day_groups = _cluster_sites(sites, request.num_days, warnings)
    total_distance_m = 0.0
    total_duration_s = 0.0
    days: List[RoutePlanDay] = []

    for day_index, group in enumerate(day_groups, start=1):
        if not group:
            days.append(RoutePlanDay(day=day_index, stops=[], polyline=""))
            continue

        try:
            ordered, order, durations, distances = _sequence_sites(start, end, group, request, warnings)
        except Exception as exc:
            return RoutePlanResponse(status="error", warnings=warnings + [f"OSRM table request failed: {exc}"])
        route_points = [start] + [_site_point(site) for site in ordered] + [end]
        try:
            route = _fetch_route(route_points)
        except ValueError as exc:
            return RoutePlanResponse(status="error", warnings=warnings + [str(exc)])
        matrix_order = [0] + order + [len(group) + 1]
        leg_distances, leg_durations = _route_legs(route, matrix_order, distances, durations)
        day_stops = _build_stops(ordered, leg_distances, leg_durations, request.available_window.start_time, warnings)

        total_distance_m += sum(leg_distances)
        total_duration_s += sum(leg_durations) + sum(site.visit_duration_min * 60 for site in ordered)
        days.append(RoutePlanDay(day=day_index, stops=day_stops, polyline=route["polyline"]))

    total_distance_km = round(total_distance_m / 1000, 2)
    total_duration_min = math.ceil(total_duration_s / 60)
    status = _status_for_limits(total_distance_km, total_duration_min, request, warnings)
    return RoutePlanResponse(
        status=status,
        total_distance_km=total_distance_km,
        total_duration_min=total_duration_min,
        days=days,
        warnings=warnings,
    )


def _resolve_point(point: PlannerPoint) -> PlannerPoint:
    if point.lat is not None and point.lng is not None:
        return point
    if point.label:
        resolved = _geocode(point.label)
        if resolved:
            point.lat, point.lng = resolved
            return point
    raise ValueError(f"point '{point.label or point.id or 'unknown'}' must have valid lat/lng or a geocodable label")


def _resolve_site(site: PlannerSite, province: str) -> PlannerSite:
    if site.lat is not None and site.lng is not None:
        return site
    query = f"{site.name} {province} Vietnam" if province else f"{site.name} Vietnam"
    resolved = _geocode(query)
    if resolved:
        site.lat, site.lng = resolved
        return site
    raise ValueError(f"site '{site.name}' must have valid lat/lng or a geocodable name")


def _geocode(query: str) -> Optional[Tuple[float, float]]:
    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "vn"})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "heritage-planner/1.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None
    return None


def _cluster_sites(sites: List[PlannerSite], num_days: int, warnings: List[str]) -> List[List[PlannerSite]]:
    if num_days <= 1:
        return [sites]
    if num_days >= len(sites):
        return [[site] for site in sites] + [[] for _ in range(num_days - len(sites))]
    if KMeans is None:
        warnings.append("sklearn KMeans unavailable; using latitude split for multi-day clustering")
        ordered = sorted(sites, key=lambda site: (site.lat or 0.0, site.lng or 0.0))
        return [ordered[i::num_days] for i in range(num_days)]

    coords = np.array([[site.lat, site.lng] for site in sites], dtype=float)
    labels = KMeans(n_clusters=num_days, random_state=0, n_init=10).fit_predict(coords)
    groups = [[site for site, label in zip(sites, labels) if label == day] for day in range(num_days)]
    return [sorted(group, key=lambda site: (site.lat or 0.0, site.lng or 0.0)) for group in groups]


def _sequence_sites(
    start: PlannerPoint,
    end: PlannerPoint,
    sites: List[PlannerSite],
    request: RoutePlanRequest,
    warnings: List[str],
) -> Tuple[List[PlannerSite], List[int], List[List[float]], List[List[float]]]:
    points = [start] + [_site_point(site) for site in sites] + [end]
    distances, durations = _fetch_table(points)
    needs_constraints = _has_solver_constraints(request)
    if len(sites) <= 12 and not needs_constraints:
        order = _held_karp(durations, len(sites))
    elif pywrapcp is not None and routing_enums_pb2 is not None:
        order = _ortools_open_path(durations, distances, sites, request, warnings)
    else:
        warnings.append("OR-Tools is not installed; using nearest-neighbor + 2-opt heuristic without solver constraints")
        order = _heuristic_open_path(durations, len(sites))
    return [sites[i - 1] for i in order], order, durations, distances


def _fetch_table(points: List[PlannerPoint]) -> Tuple[List[List[float]], List[List[float]]]:
    coord_str = ";".join(f"{point.lng},{point.lat}" for point in points)
    url = f"{OSRM_BASE}/table/v1/driving/{coord_str}?annotations=distance,duration"
    data = _json_request(url)
    if data.get("code") != "Ok" or "distances" not in data or "durations" not in data:
        raise ValueError("OSRM table request failed")
    return _clean_matrix(data["distances"]), _clean_matrix(data["durations"])


def _fetch_route(points: List[PlannerPoint]) -> dict:
    coord_str = ";".join(f"{point.lng},{point.lat}" for point in points)
    url = f"{OSRM_BASE}/route/v1/driving/{coord_str}?overview=full&geometries=polyline&steps=true"
    data = _json_request(url)
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError("OSRM route request failed")
    route = data["routes"][0]
    return {
        "distance_m": float(route.get("distance", 0.0)),
        "duration_s": float(route.get("duration", 0.0)),
        "polyline": route.get("geometry", ""),
        "legs": route.get("legs", []),
    }


def _json_request(url: str) -> dict:
    urls = [url]
    for base in OSRM_FALLBACK_BASES:
        if OSRM_BASE and url.startswith(OSRM_BASE) and base != OSRM_BASE:
            urls.append(base + url[len(OSRM_BASE):])

    last_error: Optional[Exception] = None
    for candidate in dict.fromkeys(urls):
        try:
            req = urllib.request.Request(candidate, headers={"User-Agent": "heritage-planner/1.0"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            last_error = exc
    raise ValueError(str(last_error) if last_error else "request failed")


def _clean_matrix(matrix: List[List[Optional[float]]]) -> List[List[float]]:
    return [[float(value) if value is not None else UNREACHABLE_COST for value in row] for row in matrix]


def _held_karp(cost: List[List[float]], site_count: int) -> List[int]:
    if site_count == 0:
        return []
    full_mask = (1 << site_count) - 1
    dp = {}
    parent = {}
    for idx in range(1, site_count + 1):
        mask = 1 << (idx - 1)
        dp[(mask, idx)] = cost[0][idx]
        parent[(mask, idx)] = 0

    for mask in range(1, full_mask + 1):
        for last in range(1, site_count + 1):
            if not mask & (1 << (last - 1)):
                continue
            prev_mask = mask ^ (1 << (last - 1))
            if prev_mask == 0:
                continue
            best_prev = min(
                (prev for prev in range(1, site_count + 1) if prev_mask & (1 << (prev - 1))),
                key=lambda prev: dp.get((prev_mask, prev), UNREACHABLE_COST) + cost[prev][last],
            )
            dp[(mask, last)] = dp[(prev_mask, best_prev)] + cost[best_prev][last]
            parent[(mask, last)] = best_prev

    end_idx = site_count + 1
    last = min(range(1, site_count + 1), key=lambda idx: dp[(full_mask, idx)] + cost[idx][end_idx])
    order = []
    mask = full_mask
    while last:
        order.append(last)
        prev = parent[(mask, last)]
        mask ^= 1 << (last - 1)
        last = prev
    return list(reversed(order))


def _heuristic_open_path(cost: List[List[float]], site_count: int) -> List[int]:
    unvisited = set(range(1, site_count + 1))
    order = []
    current = 0
    while unvisited:
        nxt = min(unvisited, key=lambda idx: cost[current][idx])
        order.append(nxt)
        unvisited.remove(nxt)
        current = nxt
    return _two_opt_open(order, cost, site_count + 1)


def _ortools_open_path(
    durations: List[List[float]],
    distances: List[List[float]],
    sites: List[PlannerSite],
    request: RoutePlanRequest,
    warnings: List[str],
) -> List[int]:
    site_count = len(sites)
    end_idx = site_count + 1
    manager = pywrapcp.RoutingIndexManager(len(durations), 1, [0], [end_idx])
    routing = pywrapcp.RoutingModel(manager)

    def duration_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        service_seconds = 0
        if 1 <= from_node <= site_count:
            service_seconds = sites[from_node - 1].visit_duration_min * 60
        return int(durations[from_node][to_node] + service_seconds)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(distances[from_node][to_node])

    transit_callback_index = routing.RegisterTransitCallback(duration_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    if request.constraints.max_total_distance_km is not None:
        distance_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.AddDimension(
            distance_callback_index,
            0,
            int(request.constraints.max_total_distance_km * 1000),
            True,
            "Distance",
        )

    start_sec = _time_seconds(request.available_window.start_time)
    end_sec = _time_seconds(request.available_window.end_time)
    if end_sec < start_sec:
        end_sec += 24 * 3600
    latest_end_sec = end_sec
    if request.constraints.max_total_duration_min is not None:
        latest_end_sec = min(latest_end_sec, start_sec + request.constraints.max_total_duration_min * 60)
    horizon = max(latest_end_sec, end_sec, start_sec) + 24 * 3600
    routing.AddDimension(transit_callback_index, 0, horizon, False, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")
    time_dimension.CumulVar(routing.Start(0)).SetRange(start_sec, start_sec)
    time_dimension.CumulVar(routing.End(0)).SetRange(start_sec, latest_end_sec)
    for node, site in enumerate(sites, start=1):
        open_sec = _time_seconds(site.open_time)
        close_sec = _time_seconds(site.close_time)
        if close_sec < open_sec:
            close_sec += 24 * 3600
        index = manager.NodeToIndex(node)
        try:
            time_dimension.CumulVar(index).SetRange(open_sec, close_sec)
        except Exception:
            warnings.append(f"{site.name} has an incompatible time window for OR-Tools; solver may fail")

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search.time_limit.seconds = 10

    solution = routing.SolveWithParameters(search)
    if solution is None:
        warnings.append("OR-Tools did not find a solution; using nearest-neighbor + 2-opt heuristic")
        return _heuristic_open_path(durations, site_count)

    order: List[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if 1 <= node <= site_count:
            order.append(node)
        index = solution.Value(routing.NextVar(index))
    return order


def _has_solver_constraints(request: RoutePlanRequest) -> bool:
    return (
        request.constraints.max_total_distance_km is not None
        or request.constraints.max_total_duration_min is not None
    )


def _two_opt_open(order: List[int], cost: List[List[float]], end_idx: int) -> List[int]:
    def total(seq: List[int]) -> float:
        path = [0] + seq + [end_idx]
        return sum(cost[path[i]][path[i + 1]] for i in range(len(path) - 1))

    best = order[:]
    best_cost = total(best)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                candidate_cost = total(candidate)
                if candidate_cost < best_cost:
                    best = candidate
                    best_cost = candidate_cost
                    improved = True
                    break
            if improved:
                break
    return best


def _route_legs(route: dict, matrix_order: List[int], distances: List[List[float]], durations: List[List[float]]):
    legs = route.get("legs", [])
    expected_count = len(matrix_order) - 1
    if len(legs) == expected_count:
        return [float(leg.get("distance", 0.0)) for leg in legs], [float(leg.get("duration", 0.0)) for leg in legs]
    return (
        [distances[matrix_order[i]][matrix_order[i + 1]] for i in range(expected_count)],
        [durations[matrix_order[i]][matrix_order[i + 1]] for i in range(expected_count)],
    )


def _build_stops(
    ordered: List[PlannerSite],
    leg_distances: List[float],
    leg_durations: List[float],
    start_time: str,
    warnings: List[str],
) -> List[RoutePlanStop]:
    current = _parse_time(start_time)
    stops: List[RoutePlanStop] = []
    for idx, site in enumerate(ordered):
        current += timedelta(seconds=leg_durations[idx])
        arrival = current
        departure = arrival + timedelta(minutes=site.visit_duration_min)
        if not _within_site_window(arrival, departure, site.open_time, site.close_time):
            warnings.append(f"{site.name} is scheduled outside its open_time/close_time window")
        stops.append(RoutePlanStop(
            site_id=site.id,
            name=site.name,
            arrival_time=arrival.strftime("%H:%M"),
            departure_time=departure.strftime("%H:%M"),
            travel_from_prev_km=round(leg_distances[idx] / 1000, 2),
            travel_from_prev_min=math.ceil(leg_durations[idx] / 60),
        ))
        current = departure
    return stops


def _status_for_limits(distance_km: float, duration_min: int, request: RoutePlanRequest, warnings: List[str]) -> str:
    status = "feasible"
    window_min = _window_minutes(request.available_window.start_time, request.available_window.end_time)
    if duration_min > window_min * max(1, request.num_days):
        status = "over_time_budget"
        warnings.append("itinerary exceeds available_window; drop low-priority sites or add another day")
    if request.constraints.max_total_distance_km is not None and distance_km > request.constraints.max_total_distance_km:
        status = "over_time_budget"
        warnings.append("itinerary exceeds max_total_distance_km")
    if request.constraints.max_total_duration_min is not None and duration_min > request.constraints.max_total_duration_min:
        status = "over_time_budget"
        warnings.append("itinerary exceeds max_total_duration_min")
    return status


def _site_point(site: PlannerSite) -> PlannerPoint:
    return PlannerPoint(id=site.id, lat=site.lat, lng=site.lng, label=site.name)


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value or "08:00", "%H:%M")


def _window_minutes(start: str, end: str) -> int:
    start_dt = _parse_time(start)
    end_dt = _parse_time(end)
    if end_dt < start_dt:
        end_dt += timedelta(days=1)
    return max(0, int((end_dt - start_dt).total_seconds() // 60))


def _time_seconds(value: str) -> int:
    parsed = _parse_time(value)
    return parsed.hour * 3600 + parsed.minute * 60


def _within_site_window(arrival: datetime, departure: datetime, open_time: str, close_time: str) -> bool:
    try:
        open_dt = _parse_time(open_time)
        close_dt = _parse_time(close_time)
    except ValueError:
        return True
    if close_dt < open_dt:
        close_dt += timedelta(days=1)
    return open_dt <= arrival <= close_dt and departure <= close_dt
