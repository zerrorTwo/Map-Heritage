"""
AI Service Pipeline — Orchestrates all 8 steps from the architecture spec.
"""

import asyncio
import time as time_mod
import logging
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [PIPELINE] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("pipeline")

from services.ai_service.models import (
    HeritageSite, TripRequest, Itinerary, ScoredSite,
    DayPlan, Forecast, TripInput,
)
from services.ai_service.step1_normalizer import parse_trip_request
from services.ai_service.step2_candidates import generate_candidates
from services.ai_service.step3_weather import weather_service
from services.ai_service.step4_scoring import score_all_sites
from services.ai_service.step5_clustering import split_into_days, clusters_to_day_plans
from services.ai_service.step6_routing import optimize_route
from services.ai_service.step8_assembly import assemble_itinerary


class Pipeline:
    """Orchestrates the full 8-step recommendation pipeline."""

    def __init__(self):
        self._sites_cache: List[HeritageSite] = []
        self._forecast_cache: dict = {}

    def load_data(self, sites: List[HeritageSite]):
        self._sites_cache = sites

    async def run(self, raw_input: TripInput) -> Itinerary:
        t_start = time_mod.time()
        log.info("=" * 50)
        log.info("START — Itinerary generation")
        log.info(f"  Input: provinces={raw_input.destination_provinces or raw_input.destination_area}, days={raw_input.duration_days}, interests={raw_input.interests}, pace={raw_input.pace}")
        if raw_input.start_lat: log.info(f"  Start: ({raw_input.start_lat:.4f}, {raw_input.start_lng:.4f})")
        if raw_input.end_lat: log.info(f"  End: ({raw_input.end_lat:.4f}, {raw_input.end_lng:.4f})")
        log.info(f"  Data pool: {len(self._sites_cache)} sites loaded")

        # Step 1: Normalize input
        t0 = time_mod.time()
        trip = parse_trip_request(raw_input)
        log.info(f"STEP 1 — Normalize ({time_mod.time()-t0:.2f}s): dest={trip.destination_area}, provinces={trip.destination_provinces}, days={trip.duration_days}, pace={trip.pace}")

        # Step 2: Generate candidates
        t0 = time_mod.time()
        candidates = generate_candidates(trip, self._sites_cache)
        log.info(f"STEP 2 — Candidates ({time_mod.time()-t0:.2f}s): {len(candidates)} sites from {len(self._sites_cache)} total")

        # Step 3: Fetch weather
        t0 = time_mod.time()
        forecasts = await weather_service.fetch_forecasts(candidates, trip)
        log.info(f"STEP 3 — Weather ({time_mod.time()-t0:.2f}s): {len(forecasts)} forecasts")

        # Step 4: Score each site. Must-visit sites get max score to guarantee inclusion
        t0 = time_mod.time()
        scored = score_all_sites(candidates, trip, forecasts)
        # Force must-visit sites to max score
        must_ids = set(trip.must_visit_site_ids)
        for s in scored:
            if s.site.id in must_ids:
                s.score = 0.99  # Near-max to ensure top priority in clustering
        top5 = [(s.site.name, f"{s.score:.3f}", "★" if s.site.id in must_ids else "") for s in scored[:5]]
        log.info(f"STEP 4 — Scoring ({time_mod.time()-t0:.2f}s): {len(scored)} scored | must-visit: {len(must_ids)} | top: {top5}")

        # Step 5: Day clustering
        t0 = time_mod.time()
        clusters = split_into_days(scored, trip.duration_days, trip.pace)
        cluster_sizes = [len(c) for c in clusters]
        log.info(f"STEP 5 — Clustering ({time_mod.time()-t0:.2f}s): {len(clusters)} days | sizes: {cluster_sizes}")

        # Step 6: Route optimization per day with OSRM
        t0 = time_mod.time()
        route_tasks = [
            asyncio.to_thread(optimize_route, c) if c else asyncio.sleep(0, result=(c, None))
            for c in clusters
        ]
        route_results = await asyncio.gather(*route_tasks)
        optimized_clusters = []
        route_geoms = []
        for di, (ordered, geom) in enumerate(route_results):
            optimized_clusters.append(ordered)
            route_geoms.append(geom)
            wp = len(geom) if geom else 0
            log.info(f"  Day {di+1} OSRM: {len(ordered)} sites ordered | route: {wp} waypoints")
        log.info(f"STEP 6 — Routing ({time_mod.time()-t0:.2f}s): {sum(1 for g in route_geoms if g)}/{len(route_geoms)} OSRM routes")

        # Step 7: Day plans
        t0 = time_mod.time()
        day_plans = clusters_to_day_plans(optimized_clusters, trip.start_date)
        log.info(f"STEP 7 — Day Plans ({time_mod.time()-t0:.2f}s): {sum(len(d.items) for d in day_plans)} items")

        # Step 8: Assemble
        t0 = time_mod.time()
        itinerary = assemble_itinerary(day_plans, optimized_clusters, trip, route_geoms)
        log.info(f"STEP 8 — Assemble ({time_mod.time()-t0:.2f}s): score={itinerary.total_score:.0%}, distance={itinerary.total_distance_km}km, id={itinerary.itinerary_id}")

        total_time = time_mod.time() - t_start
        log.info(f"DONE — Total: {total_time:.2f}s | ID: {itinerary.itinerary_id}")
        log.info("=" * 50)

        return itinerary


pipeline = Pipeline()
