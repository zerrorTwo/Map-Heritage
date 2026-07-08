"""Step 1 — Normalize input."""
from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext
from services.ai_service.step1_normalizer import parse_trip_request


class NormalizeStep(PipelineStep):
    name = "step1_normalize"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        ctx.trip_request = parse_trip_request(ctx.input)
        return ctx
