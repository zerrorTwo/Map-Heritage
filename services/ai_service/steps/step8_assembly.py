"""Step 8 — Assemble final itinerary."""
import logging

from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext
from services.ai_service.step8_assembly import assemble_itinerary

log = logging.getLogger("heritage.pipeline")


class AssemblyStep(PipelineStep):
    name = "step8_assembly"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        ctx.itinerary = assemble_itinerary(
            ctx.day_plans, ctx.optimized_clusters, ctx.trip_request,
            ctx.route_geometries, ctx.distance_matrix,
        )
        log.info("[%s] assembly  score=%d%%  distance=%.1fkm  id=%s",
                 ctx.request_id, int(ctx.itinerary.total_score * 100),
                 ctx.itinerary.total_distance_km, ctx.itinerary.itinerary_id)
        return ctx
