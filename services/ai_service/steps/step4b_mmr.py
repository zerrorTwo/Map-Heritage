"""Step 4b — MMR diversity re-ranking."""
from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext
from services.ai_service.mmr_rerank import mmr_rerank


class MMRStep(PipelineStep):
    name = "step4b_mmr"

    def __init__(self, lambd: float = 0.7):
        self.lambd = lambd

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        must_ids = set(ctx.trip_request.must_visit_site_ids)
        must_visit_scored = [s for s in ctx.scored_sites if s.site.id in must_ids]
        recommended_scored = [s for s in ctx.scored_sites if s.site.id not in must_ids]
        if recommended_scored:
            recommended_scored = mmr_rerank(recommended_scored, lambd=self.lambd)
        ctx.scored_sites = must_visit_scored + recommended_scored
        return ctx
