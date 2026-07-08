"""Step 4 — Score sites."""
import logging
from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext
from services.ai_service.step4_scoring import score_all_sites

log = logging.getLogger("heritage.pipeline")


class ScoringStep(PipelineStep):
    name = "step4_scoring"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        ctx.scored_sites = score_all_sites(ctx.candidates, ctx.trip_request, ctx.forecasts)
        must_ids = set(ctx.trip_request.must_visit_site_ids)
        for s in ctx.scored_sites:
            if s.site.id in must_ids:
                s.score = 0.99
        top = [(s.site.name, f"{s.score:.3f}") for s in ctx.scored_sites[:3]]
        log.info("[%s] scoring done  %d scored  must_visit=%d  top=%s",
                 ctx.request_id, len(ctx.scored_sites), len(must_ids), top)
        return ctx
