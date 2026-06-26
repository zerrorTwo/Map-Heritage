"""
AI Service Pipeline — Orchestrates all 8 steps from the architecture spec.
"""

import asyncio
from typing import List
from services.ai_service.models import (
    HeritageSite, Restaurant, TripRequest, Itinerary, ScoredSite,
    DayPlan, Forecast, TripInput,
)
from services.ai_service.step1_normalizer import parse_trip_request
from services.ai_service.step2_candidates import generate_candidates
from services.ai_service.step3_weather import weather_service
from services.ai_service.step4_scoring import score_all_sites
from services.ai_service.step5_clustering import split_into_days, clusters_to_day_plans
from services.ai_service.step6_routing import optimize_route
from services.ai_service.step7_restaurants import insert_restaurants
from services.ai_service.step8_assembly import assemble_itinerary


class Pipeline:
    """Orchestrates the full 8-step recommendation pipeline."""

    def __init__(self):
        self._sites_cache: List[HeritageSite] = []
        self._restaurants_cache: List[Restaurant] = []
        self._forecast_cache: dict = {}

    def load_data(self, sites: List[HeritageSite], restaurants: List[Restaurant]):
        self._sites_cache = sites
        self._restaurants_cache = restaurants

    async def run(self, raw_input: TripInput) -> Itinerary:
        """
        Execute the full 8-step pipeline:
          Step 1 — Normalize input
          Step 2 — Generate candidate sites
          Step 3 — Fetch weather/environment
          Step 4 — Score each site
          Step 5 — Split into day-clusters
          Step 6 — Optimize visiting order per day
          Step 7 — Insert restaurants
          Step 8 — Assemble final itinerary
        """
        # Step 1: Normalize
        trip = parse_trip_request(raw_input)

        # Step 2: Generate candidates
        candidates = generate_candidates(trip, self._sites_cache)

        # Step 3: Fetch weather
        forecasts = await weather_service.fetch_forecasts(candidates, trip)

        # Step 4: Score
        scored = score_all_sites(candidates, trip, forecasts)

        # Step 5: Day clustering
        clusters = split_into_days(scored, trip.duration_days, trip.pace)

        # Step 6: Route optimization per day with OSRM (offloaded to thread)
        optimized_clusters = []
        route_geoms = []
        for c in clusters:
            ordered, geom = await asyncio.to_thread(optimize_route, c)
            optimized_clusters.append(ordered)
            route_geoms.append(geom)

        # Step 7: Convert to DayPlan, insert restaurants
        day_plans = clusters_to_day_plans(optimized_clusters, trip.start_date)
        day_plans = insert_restaurants(
            day_plans, self._restaurants_cache,
            optimized_clusters,
            specialty_prefs=trip.interests,
            budget_level=trip.budget_level,
        )

        # Step 8: Assemble itinerary
        itinerary = assemble_itinerary(day_plans, optimized_clusters, trip, route_geoms)

        return itinerary


pipeline = Pipeline()
