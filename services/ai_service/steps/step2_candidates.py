"""Step 2 — Generate candidates."""
import logging
from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext
from services.ai_service.step2_candidates import generate_candidates

log = logging.getLogger("heritage.pipeline")


class CandidateStep(PipelineStep):
    name = "step2_candidates"

    def __init__(self, sites_cache: list):
        self.sites_cache = sites_cache

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        ctx.candidates = generate_candidates(ctx.trip_request, self.sites_cache)
        if not ctx.candidates:
            log.warning("[%s] step2 returned 0 candidates — check province match: wanted=%s",
                        ctx.request_id, ctx.trip_request.destination_provinces)
        return ctx
