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
        trip = ctx.trip_request
        start_loc = trip.start_location if trip and trip.start_location else None
        end_loc = trip.end_location if trip and trip.end_location else None
        start_anchor = (start_loc["lat"], start_loc["lng"]) if start_loc else None
        end_anchor = (end_loc["lat"], end_loc["lng"]) if end_loc else None

        clusters = ctx.optimized_clusters
        non_empty_idx = [i for i, c in enumerate(clusters) if c]

        route_tasks = []
        for i, cluster in enumerate(clusters):
            if not cluster:
                route_tasks.append(asyncio.sleep(0, result=None))
                continue

            is_first = non_empty_idx and i == non_empty_idx[0]
            is_last = non_empty_idx and i == non_empty_idx[-1]

            if is_first:
                lead = start_anchor
            else:
                prev = [j for j in non_empty_idx if j < i]
                lead = (clusters[prev[-1]][-1].site.lat, clusters[prev[-1]][-1].site.lng) if prev else None

            tail = end_anchor if is_last else None
            route_tasks.append(asyncio.to_thread(get_route_geometry, cluster, lead, tail))

        ctx.route_geometries = await asyncio.gather(*route_tasks)

        flat_ordered = [s for c in ctx.optimized_clusters for s in c]
        dm_matrix, dm_coords, _ = build_distance_matrix_osrm(flat_ordered)

        ctx.distance_matrix = {"sites": flat_ordered, "matrix": dm_matrix} if len(flat_ordered) > 0 else None

        geom_count = sum(1 for g in ctx.route_geometries if g)
        log.info("[%s] geometry done  %d polylines  %d items",
                 ctx.request_id, geom_count, len(flat_ordered))
        return ctx
