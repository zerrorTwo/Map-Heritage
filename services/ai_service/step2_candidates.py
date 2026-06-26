"""
Step 2 — Generate candidates: Filter heritage sites by area, interest, constraints.
"""

from typing import List, Optional
from services.ai_service.models import HeritageSite, TripRequest
import numpy as np


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in meters."""
    R = 6371000
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def generate_candidates(
    trip: TripRequest,
    all_sites: List[HeritageSite],
    radius_km: float = 100.0,
    top_n: int = 30,
) -> List[HeritageSite]:
    """
    Filter heritage sites:
      1. Province / area match (within radius)
      2. Force-include must_visit_site_ids
      3. Filter by group constraints
      4. Rank by interest tag overlap
      5. Return top N
    """
    must_visit_ids = set(trip.must_visit_site_ids)
    candidates: List[HeritageSite] = []
    must_visits: List[HeritageSite] = []

    start_lat = trip.start_location["lat"] if trip.start_location else 21.0285
    start_lng = trip.start_location["lng"] if trip.start_location else 105.8542

    for site in all_sites:
        if site.id in must_visit_ids:
            must_visits.append(site)
            continue

        # Multi-province filtering
        target_provinces = trip.destination_provinces or [trip.destination_area]
        if site.province not in target_provinces:
            dist = haversine_distance(start_lat, start_lng, site.lat, site.lng)
            if dist > radius_km * 1000:
                continue

        if not _satisfies_constraints(site, trip.constraints):
            continue

        candidates.append(site)

    candidates.sort(
        key=lambda s: _interest_overlap(s, trip.interests),
        reverse=True,
    )

    result = must_visits + candidates[: top_n - len(must_visits)]
    return result


def _satisfies_constraints(site: HeritageSite, constraints: List[str]) -> bool:
    if "elderly_friendly" in constraints and not site.suitable_for_elderly:
        return False
    if "child_friendly" in constraints and not site.suitable_for_children:
        return False
    if "prefer_indoor" in constraints and site.indoor_score < 0.4:
        return False
    if "prefer_outdoor" in constraints and site.outdoor_score < 0.4:
        return False
    return True


def _interest_overlap(site: HeritageSite, interests: List[str]) -> float:
    if not interests:
        return 0.0
    common = set(c.lower() for c in site.categories) & set(i.lower() for i in interests)
    return len(common) / len(interests)
