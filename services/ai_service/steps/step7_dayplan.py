"""Step 7 — Build day plans."""
import logging

from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext
from services.ai_service.step5_clustering import clusters_to_day_plans

log = logging.getLogger("heritage.pipeline")


class DayPlanStep(PipelineStep):
    name = "step7_dayplans"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        ctx.day_plans = clusters_to_day_plans(
            ctx.optimized_clusters, ctx.trip_request.start_date
        )
        total = sum(len(d.items) for d in ctx.day_plans)
        log.info("[%s] dayplans  %d items across %d days",
                 ctx.request_id, total, len(ctx.day_plans))
        return ctx
