"""Step 3 — Fetch weather."""
from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext
from services.ai_service.step3_weather import weather_service


class WeatherStep(PipelineStep):
    name = "step3_weather"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        ctx.forecasts = await weather_service.fetch_forecasts(
            ctx.candidates, ctx.trip_request
        )
        return ctx
