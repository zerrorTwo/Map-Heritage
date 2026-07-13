"""
Step 8 — Assemble and return final Itinerary.
Combines ordered sites + inserted restaurants + per-item reason strings.
"""

import math
import uuid
from typing import List, Dict, Optional
from services.ai_service.models import (
    ScoredSite, DayPlan, Itinerary, ItineraryItem, TripRequest
)


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def assemble_itinerary(
    day_plans: List[DayPlan],
    scored_clusters: List[List[ScoredSite]],
    trip: TripRequest,
    route_geoms: List = None,
    distance_matrix: Optional[dict] = None,
    warnings: List[str] = None,
) -> Itinerary:
    """
    Combine ordered sites, inserted restaurants, and compute final itinerary metrics.
    Supports two-pass distance scoring: uses real OSRM distances when available.
    """
    total_distance = 0.0
    all_scored = [s for cluster in scored_clusters for s in cluster]
    score_count = len(all_scored)

    dm = distance_matrix or {}
    dm_sites = dm.get("sites", [])
    dm_osrm = dm.get("matrix", None)

    for day_plan in day_plans:
        current_time_minutes = 8 * 60
        prev = None
        for item in day_plan.items:
            if prev and item.type in ("heritage", "restaurant") and prev.type in ("heritage", "restaurant"):
                prev_coords = _get_coords(prev, all_scored)
                curr_coords = _get_coords(item, all_scored)

                if prev_coords and curr_coords:
                    real_dist = _lookup_distance(prev, item, all_scored, dm_sites, dm_osrm)
                    haversine_dist = haversine(*prev_coords, *curr_coords)

                    if real_dist is not None:
                        item.distance_from_previous_m = round(real_dist, 1)
                        item.travel_from_previous_minutes = max(1, int(real_dist / 500))
                        total_distance += real_dist
                    else:
                        item.distance_from_previous_m = round(haversine_dist, 1)
                        item.travel_from_previous_minutes = max(1, int(haversine_dist / 500))
                        total_distance += haversine_dist

            current_time_minutes += item.travel_from_previous_minutes

            visit_duration = 60
            if item.type == "heritage":
                for sc in all_scored:
                    if sc.site.id == item.ref_id:
                        visit_duration = sc.site.estimated_visit_minutes
                        break
            elif item.type == "restaurant":
                visit_duration = 45

            start_hh = int(current_time_minutes // 60) % 24
            start_mm = int(current_time_minutes % 60)
            current_time_minutes += visit_duration
            end_hh = int(current_time_minutes // 60) % 24
            end_mm = int(current_time_minutes % 60)
            item.time = f"{start_hh:02d}:{start_mm:02d}-{end_hh:02d}:{end_mm:02d}"

            prev = item

    if score_count > 0:
        total_score = round(
            sum(s.score for s in all_scored) / score_count, 4
        )

    budget_fit = _compute_budget_fit(all_scored, trip)
    quality_score = _compute_quality_score(
        day_plans, all_scored, total_distance, trip, budget_fit
    )

    summary = _build_summary(day_plans, trip, quality_score)

    return Itinerary(
        itinerary_id=f"it-{uuid.uuid4().hex[:12]}",
        summary=summary,
        total_score=round(quality_score, 4),
        total_distance_km=round(total_distance / 1000, 2),
        days=day_plans,
        route_geometries=[(g if g else []) for g in (route_geoms or [])],
        warnings=warnings or [],
    )


def _get_coords(item: ItineraryItem, all_scored: List[ScoredSite]) -> tuple:
    for sc in all_scored:
        if sc.site.id == item.ref_id:
            return (sc.site.lat, sc.site.lng)
    return None


def _lookup_distance(
    prev_item: ItineraryItem,
    curr_item: ItineraryItem,
    all_scored: List[ScoredSite],
    dm_sites: List[ScoredSite],
    dm_osrm,
) -> Optional[float]:
    """Look up real OSRM distance between two itinerary items."""
    if dm_osrm is None or not dm_sites:
        return None
    prev_idx = None
    curr_idx = None
    for i, s in enumerate(dm_sites):
        if s.site.id == prev_item.ref_id:
            prev_idx = i
        if s.site.id == curr_item.ref_id:
            curr_idx = i
    if prev_idx is not None and curr_idx is not None:
        try:
            d = dm_osrm[prev_idx][curr_idx]
            if d > 0 and d < 999999:
                return float(d)
        except (IndexError, TypeError):
            pass
    return None


def _compute_budget_fit(all_scored: List[ScoredSite], trip: TripRequest) -> float:
    """Compute actual budget fit from site ticket prices and user budget_level."""
    heritage_sites = [s for s in all_scored if s.site.ticket_price is not None]
    if not heritage_sites:
        return 0.8

    total_cost = sum(s.site.ticket_price for s in heritage_sites)
    avg_cost = total_cost / len(heritage_sites)

    thresholds = {"low": 30000, "medium": 100000, "high": 1000000}
    max_acceptable = thresholds.get(trip.budget_level, 100000)

    if avg_cost <= max_acceptable * 0.3:
        return 1.0
    if avg_cost >= max_acceptable:
        return 0.3
    return 1.0 - 0.7 * (avg_cost / max_acceptable)


def _compute_quality_score(
    day_plans: List[DayPlan],
    all_scored: List[ScoredSite],
    total_distance: float,
    trip: TripRequest,
    budget_fit: float = 0.8,
) -> float:
    """Itinerary quality score from §6, with real-distance route_efficiency and actual budget_fit."""
    avg_site_score = sum(s.score for s in all_scored) / max(1, len(all_scored))

    days = max(1, len(day_plans))
    # Scale distance cap by province count — multi-province trips naturally span farther
    prov_count = len(trip.destination_provinces) if trip.destination_provinces else 1
    dist_cap = 100 * max(1, prov_count ** 0.5)
    dist_per_day = (total_distance / 1000) / days
    route_eff = max(0.0, 1.0 - dist_per_day / dist_cap)

    weather_fit = sum(s.weather_suitability for s in all_scored) / max(1, len(all_scored))

    pref_fit = sum(s.interest_match for s in all_scored) / max(1, len(all_scored))

    restaurant_count = sum(
        1 for dp in day_plans for item in dp.items if item.type == "restaurant"
    )
    food_score = min(1.0, restaurant_count / max(1, days * 3))

    schedule_balance = 1.0
    if day_plans:
        counts = [len(dp.items) for dp in day_plans]
        if max(counts) > 0:
            schedule_balance = 1.0 - (max(counts) - min(counts)) / max(1, max(counts))

    return (
        0.25 * avg_site_score
        + 0.20 * route_eff
        + 0.15 * weather_fit
        + 0.15 * pref_fit
        + 0.10 * food_score
        + 0.10 * schedule_balance
        + 0.05 * budget_fit
    )


def _build_summary(day_plans: List[DayPlan], trip: TripRequest, quality: float) -> str:
    total_sites = sum(1 for dp in day_plans for item in dp.items if item.type == "heritage")
    total_restaurants = sum(1 for dp in day_plans for item in dp.items if item.type == "restaurant")
    probs = trip.destination_provinces or [trip.destination_area or "Hà Nội"]
    dest = ", ".join(probs) if len(probs) <= 3 else f"{len(probs)} tỉnh thành"
    parts = [f"Chuyến du lịch {trip.duration_days} ngày tại {dest}."]
    if total_restaurants > 0:
        parts.append(f"Khám phá {total_sites} di sản và {total_restaurants} nhà hàng.")
    else:
        parts.append(f"Khám phá {total_sites} di sản.")
    parts.append(f"Chất lượng hành trình: {quality:.0%}")
    return " ".join(parts)
