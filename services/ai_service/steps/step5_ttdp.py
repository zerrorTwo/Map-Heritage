"""Step 5 — Geographic day-partitioning (pace-capped, must-visit-seeded)."""
import logging
from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext
from services.ai_service.step5_clustering import partition_into_days

log = logging.getLogger("heritage.pipeline")

class TTDPRoutingStep(PipelineStep):
    name = "step5_ttdp"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        trip = ctx.trip_request
        ctx.optimized_clusters = partition_into_days(
            ctx.scored_sites,
            duration_days=trip.duration_days,
            pace=trip.pace,
            must_visit_ids=trip.must_visit_site_ids,
        )
        counts = [len(c) for c in ctx.optimized_clusters]
        log.info("[%s] partition pace=%s days=%d counts=%s",
                 ctx.request_id, trip.pace, trip.duration_days, counts)
        return ctx
