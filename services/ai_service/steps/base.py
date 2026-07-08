"""
Pipeline base classes — PipelineStep ABC and PipelineRunner.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import List

from services.ai_service.steps.context import PipelineContext

log = logging.getLogger("heritage.pipeline")


class PipelineStep(ABC):
    name: str = ""

    @abstractmethod
    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        ...


class PipelineRunner:
    """Runs a list of PipelineStep instances in sequence with timing and error handling."""

    def __init__(self, steps: List[PipelineStep]):
        self.steps = steps

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        for step in self.steps:
            t0 = time.time()
            try:
                ctx = await step.execute(ctx)
                duration_ms = int((time.time() - t0) * 1000)
                ctx.step_timings[step.name] = duration_ms
                log.info("[%s] %s  %dms", ctx.request_id, step.name, duration_ms)
            except Exception as e:
                duration_ms = int((time.time() - t0) * 1000)
                log.exception("[%s] %s FAILED  %dms", ctx.request_id, step.name, duration_ms)
                ctx.errors.append(f"{step.name}: {str(e)}")
                raise
        return ctx
