"""Step 5 — TTDP route optimization (OR-Tools)."""
import asyncio
import logging

from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext
from services.ai_service.ttdp_solver import solve_ttdp

log = logging.getLogger("heritage.pipeline")


class TTDPRoutingStep(PipelineStep):
    name = "step5_ttdp"

    def __init__(self, speed_kmh: float = 40.0, time_limit_sec: int = 2):
        self.speed_kmh = speed_kmh
        self.time_limit_sec = time_limit_sec

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        trip = ctx.trip_request
        start_lat = trip.start_location.get('lat') if trip.start_location else 21.0285
        start_lng = trip.start_location.get('lng') if trip.start_location else 105.8542
        end_lat = trip.end_location.get('lat') if trip.end_location else start_lat
        end_lng = trip.end_location.get('lng') if trip.end_location else start_lng

        locations = [(start_lat, start_lng), (end_lat, end_lng)]
        scores = [0.0, 0.0]
        durations = [0, 0]
        time_windows = [(0, 100000), (0, 100000)]

        for s in ctx.scored_sites:
            locations.append((s.site.lat, s.site.lng))
            scores.append(s.score)
            durations.append(s.site.estimated_visit_minutes * 60)
            time_windows.append((0, 100000))

        max_sec_per_day = 8 * 3600
        routes_indices = await asyncio.to_thread(
            solve_ttdp, locations, scores, durations, time_windows,
            trip.duration_days, max_sec_per_day,
            speed_kmh=self.speed_kmh, time_limit_sec=self.time_limit_sec
        )

        clusters = []
        for route_idx in routes_indices:
            cluster = [ctx.scored_sites[i - 2] for i in route_idx]
            clusters.append(cluster)

        if ctx.scored_sites and not any(clusters):
            log.warning("[%s] TTDP empty — falling back to top scored", ctx.request_id)
            max_sites = min(len(ctx.scored_sites), max(3, trip.duration_days * 3))
            selected = ctx.scored_sites[:max_sites]
            clusters = [selected[i::trip.duration_days] for i in range(trip.duration_days)]

        ctx.optimized_clusters = clusters
        return ctx
