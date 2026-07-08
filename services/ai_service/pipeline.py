"""
AI Service Pipeline — Orchestrates all steps using Pipeline Pattern.
To add/remove/reorder steps, edit the `_build_runner()` method.
"""

import logging
import time as time_mod
import uuid
from typing import List

from services.ai_service.models import HeritageSite, Itinerary, TripInput
from services.ai_service.steps.base import PipelineRunner
from services.ai_service.steps.context import PipelineContext
from services.ai_service.steps.step1_normalize import NormalizeStep
from services.ai_service.steps.step2_candidates import CandidateStep
from services.ai_service.steps.step3_weather import WeatherStep
from services.ai_service.steps.step4_scoring import ScoringStep
from services.ai_service.steps.step4b_mmr import MMRStep
from services.ai_service.steps.step5_ttdp import TTDPRoutingStep
from services.ai_service.steps.step6_geometry import GeometryStep
from services.ai_service.steps.step7_dayplan import DayPlanStep
from services.ai_service.steps.step8_assembly import AssemblyStep

log = logging.getLogger("heritage.pipeline")


class Pipeline:
    """Orchestrates the full recommendation pipeline using composable steps."""

    def __init__(self):
        self._sites_cache: List[HeritageSite] = []
        self._forecast_cache: dict = {}

    def load_data(self, sites: List[HeritageSite]):
        self._sites_cache = sites

    def _build_runner(self) -> PipelineRunner:
        """Build pipeline step chain. Add/remove/reorder steps here."""
        return PipelineRunner(steps=[
            NormalizeStep(),
            CandidateStep(sites_cache=self._sites_cache),
            WeatherStep(),
            ScoringStep(),
            MMRStep(lambd=0.7),
            TTDPRoutingStep(speed_kmh=40.0, time_limit_sec=2),
            GeometryStep(),
            DayPlanStep(),
            AssemblyStep(),
        ])

    async def run(self, raw_input: TripInput) -> Itinerary:
        t_start = time_mod.time()

        ctx = PipelineContext(
            input=raw_input,
            request_id=uuid.uuid4().hex[:8],
        )

        log.info("[%s] START  provinces=%s  days=%s  pace=%s  pool=%d",
                 ctx.request_id,
                 raw_input.destination_provinces or raw_input.destination_area,
                 raw_input.duration_days, raw_input.pace, len(self._sites_cache))

        try:
            runner = self._build_runner()
            ctx = await runner.run(ctx)
        except Exception:
            log.exception("[%s] PIPELINE FAILED", ctx.request_id)
            raise

        total_ms = int((time_mod.time() - t_start) * 1000)
        itinerary = ctx.itinerary

        if ctx.errors:
            log.error("[%s] errors: %s", ctx.request_id, ctx.errors)

        log.info("[%s] DONE  %dms  score=%d%%  distance=%.1fkm  id=%s  steps=%d",
                 ctx.request_id, total_ms,
                 int(itinerary.total_score * 100),
                 itinerary.total_distance_km,
                 itinerary.itinerary_id,
                 len(ctx.step_timings))

        return itinerary


pipeline = Pipeline()
