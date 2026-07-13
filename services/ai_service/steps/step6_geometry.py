"""Step 6 — OSRM geometry + road-aware route re-optimization."""
import asyncio
import logging

import numpy as np

from config import settings
from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext
from services.ai_service.step6_routing import (
    get_route_geometry,
    optimize_route_open,
)

log = logging.getLogger("heritage.pipeline")

# Daily time budget in seconds (soft, warning-only) — from config max_daily_hours
DAILY_BUDGET_SECONDS = settings.max_daily_hours * 3600


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

        # ---- Phase 1: Re-optimize each cluster's order via OSRM road durations ----
        reordered = []
        route_results = []
        for i, cluster in enumerate(clusters):
            if not cluster:
                reordered.append([])
                route_results.append(None)
                continue

            is_first = non_empty_idx and i == non_empty_idx[0]
            is_last = non_empty_idx and i == non_empty_idx[-1]

            if is_first:
                anchor_start = start_anchor
            else:
                previous = [day for day in non_empty_idx if day < i]
                anchor_start = (
                    (reordered[previous[-1]][-1].site.lat, reordered[previous[-1]][-1].site.lng)
                    if previous else None
                )
            anchor_end = end_anchor if is_last else None

            try:
                result = await asyncio.to_thread(
                    optimize_route_open,
                    cluster,
                    start_anchor=anchor_start,
                    end_anchor=anchor_end,
                )
                ordered = result.ordered_sites
            except Exception:
                log.warning("[%s] route re-optimization failed for day %d, keeping TTDP order",
                            ctx.request_id, i + 1)
                ordered = cluster
                result = None

            reordered.append(ordered)
            route_results.append(result)

        ctx.optimized_clusters = reordered

        # ---- Phase 2: Fetch route geometry for each reordered cluster ----
        # Only intra-day routing is drawn; cross-day connectors are tracked
        # via travel_from_previous_minutes in the response data.
        route_tasks = []
        for i, cluster in enumerate(reordered):
            if not cluster:
                route_tasks.append(asyncio.sleep(0, result=None))
                continue

            route_tasks.append(asyncio.to_thread(get_route_geometry, cluster, None, None))

        ctx.route_geometries = await asyncio.gather(*route_tasks)

        # ---- Phase 3: Retain road distances for Step 8 without another table call ----
        flat_ordered = [site for cluster in reordered for site in cluster]
        total_count = len(flat_ordered)
        global_matrix = np.full((total_count, total_count), np.nan)
        cursor = 0
        has_road_data = False
        for cluster, result in zip(reordered, route_results):
            size = len(cluster)
            if result is not None and result.distance_matrix is not None:
                global_matrix[cursor:cursor + size, cursor:cursor + size] = result.distance_matrix
                has_road_data = True
            cursor += size
        ctx.distance_matrix = (
            {"sites": flat_ordered, "matrix": global_matrix} if has_road_data else None
        )

        # ---- Phase 4: Validate road travel + visit duration against budget ----
        total_sites = 0
        for i, (cluster, result) in enumerate(zip(reordered, route_results)):
            total_sites += len(cluster)
            if not cluster:
                continue
            visit_duration = sum(
                s.site.estimated_visit_minutes * 60 for s in cluster
            )
            total_duration = visit_duration + (result.total_duration_s if result and result.total_duration_s else 0)
            if total_duration > DAILY_BUDGET_SECONDS:
                log.warning("[%s] day %d exceeds daily budget (%ds > %ds)",
                            ctx.request_id, i + 1, total_duration, DAILY_BUDGET_SECONDS)

        # ---- Phase 5: Detect island/offshore crossings for client warnings ----
        import math
        for i, cluster in enumerate(reordered):
            if len(cluster) < 2:
                continue
            for j in range(len(cluster) - 1):
                a, b = cluster[j].site, cluster[j + 1].site
                dlat = (b.lat - a.lat) * 111.32
                dlng = (b.lng - a.lng) * 111.32 * 0.85
                if math.sqrt(dlat * dlat + dlng * dlng) > 150:
                    ctx.warnings.append("island_route")
                    log.info("[%s] day %d has island/offshore leg: %s → %s (%.0f km)",
                             ctx.request_id, i + 1, a.name, b.name,
                             math.sqrt(dlat * dlat + dlng * dlng))
                    break  # one warning per day is enough

        geom_count = sum(1 for g in ctx.route_geometries if g)
        log.info("[%s] geometry done  %d polylines  %d items",
                 ctx.request_id, geom_count, total_sites)
        return ctx
