"""
Step 8 — Assemble and return final Itinerary.
Combines ordered sites + inserted restaurants + per-item reason strings.
"""

import uuid
from typing import List, Dict
from services.ai_service.models import (
    ScoredSite, DayPlan, Itinerary, ItineraryItem, TripRequest
)
from services.ai_service.step6_routing import haversine


def assemble_itinerary(
    day_plans: List[DayPlan],
    scored_clusters: List[List[ScoredSite]],
    trip: TripRequest,
    route_geoms: List = None,
) -> Itinerary:
    """
    Combine ordered sites, inserted restaurants, and compute final itinerary metrics.
    """
    total_score = 0.0
    total_distance = 0.0
    all_scored = [s for cluster in scored_clusters for s in cluster]
    score_count = len(all_scored)

    for day_plan in day_plans:
        prev = None
        for item in day_plan.items:
            if prev and item.type in ("heritage", "restaurant") and prev.type in ("heritage", "restaurant"):
                prev_coords = _get_coords(prev, all_scored)
                curr_coords = _get_coords(item, all_scored)
                if prev_coords and curr_coords:
                    dist = haversine(*prev_coords, *curr_coords)
                    item.distance_from_previous_m = round(dist, 1)
                    item.travel_from_previous_minutes = max(1, int(dist / 200))  # approx walking
                    total_distance += dist
            prev = item

    if score_count > 0:
        total_score = round(
            sum(s.score for s in all_scored) / score_count, 4
        )

    # Quality scoring formula §6
    quality_score = _compute_quality_score(day_plans, all_scored, total_distance, trip)

    summary = _build_summary(day_plans, trip, quality_score)

    return Itinerary(
        itinerary_id=f"it-{uuid.uuid4().hex[:12]}",
        summary=summary,
        total_score=round(quality_score, 4),
        total_distance_km=round(total_distance / 1000, 2),
        days=day_plans,
        route_geometries=[g for g in (route_geoms or []) if g],
    )


def _get_coords(item: ItineraryItem, all_scored: List[ScoredSite]) -> tuple:
    for sc in all_scored:
        if sc.site.id == item.ref_id:
            return (sc.site.lat, sc.site.lng)
    return None


def _compute_quality_score(
    day_plans: List[DayPlan],
    all_scored: List[ScoredSite],
    total_distance: float,
    trip: TripRequest,
) -> float:
    """Itinerary quality score from §6."""
    avg_site_score = sum(s.score for s in all_scored) / max(1, len(all_scored))

    # Route efficiency: penalize if > 50km/day
    days = max(1, len(day_plans))
    dist_per_day = (total_distance / 1000) / days
    route_eff = max(0.0, 1.0 - dist_per_day / 100)

    # Weather fit
    weather_fit = sum(s.weather_suitability for s in all_scored) / max(1, len(all_scored))

    # User preference fit
    pref_fit = sum(s.interest_match for s in all_scored) / max(1, len(all_scored))

    # Food experience: simplified
    restaurant_count = sum(
        1 for dp in day_plans for item in dp.items if item.type == "restaurant"
    )
    food_score = min(1.0, restaurant_count / max(1, days * 3))

    # Schedule balance
    schedule_balance = 1.0
    if day_plans:
        counts = [len(dp.items) for dp in day_plans]
        if max(counts) > 0:
            schedule_balance = 1.0 - (max(counts) - min(counts)) / max(1, max(counts))

    # Budget fit
    budget_fit = 0.8  # Simplified

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
    return (
        f"Chuyến du lịch {trip.duration_days} ngày tại {trip.destination_area}. "
        f"Khám phá {total_sites} di sản và {total_restaurants} nhà hàng. "
        f"Chất lượng hành trình: {quality:.0%}"
    )
