"""Step 6 — Geometry + OSRM distance matrix."""
import asyncio
import logging

from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext
from services.ai_service.step6_routing import get_route_geometry, build_distance_matrix_osrm

log = logging.getLogger("heritage.pipeline")


class GeometryStep(PipelineStep):
    name = "step6_geometry"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        route_tasks = [
            asyncio.to_thread(get_route_geometry, c) if c else asyncio.sleep(0, result=None)
            for c in ctx.optimized_clusters
        ]
        ctx.route_geometries = await asyncio.gather(*route_tasks)

        flat_ordered = [s for c in ctx.optimized_clusters for s in c]
        dm_matrix, dm_coords, _ = build_distance_matrix_osrm(flat_ordered)

        ctx.distance_matrix = {"sites": flat_ordered, "matrix": dm_matrix} if len(flat_ordered) > 0 else None

        geom_count = sum(1 for g in ctx.route_geometries if g)
        log.info("[%s] geometry done  %d polylines  %d items",
                 ctx.request_id, geom_count, len(flat_ordered))
        return ctx
