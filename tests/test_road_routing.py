"""Deterministic regression tests for OSRM road-aware itinerary routing."""
import asyncio
import sys
from unittest.mock import patch

import numpy as np

sys.path.insert(0, ".")

from services.ai_service import step6_routing
from services.ai_service.models import DayPlan, HeritageSite, ItineraryItem, ScoredSite, TripInput, TripRequest
from services.ai_service.steps.context import PipelineContext
from services.ai_service.steps.step6_geometry import GeometryStep
from services.ai_service.step8_assembly import assemble_itinerary


def make_site(site_id: str, lat: float, lng: float) -> ScoredSite:
    return ScoredSite(
        site=HeritageSite(
            id=site_id, name=site_id, province="HN", lat=lat, lng=lng,
            categories=["history"], estimated_visit_minutes=60,
        ),
        score=0.8,
    )


def check(label: str, actual, expected):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_open_two_opt_keeps_fixed_anchor_costs():
    # Site order [A, B] costs 100 + 100 + 100; [B, A] costs 1 + 1 + 1.
    # The first and final anchor indices must remain outside the site permutation.
    cost = np.array([
        [0, 100, 1, 999],
        [999, 0, 100, 1],
        [999, 1, 0, 100],
        [999, 999, 999, 0],
    ], dtype=float)
    route = step6_routing.two_opt_open([1, 2], cost, start_index=0, end_index=3)
    check("fixed-anchor 2-opt", route, [2, 1])


def test_optimizer_uses_one_osrm_table_with_anchors_and_returns_road_matrices():
    sites = [make_site("a", 21.0, 105.0), make_site("b", 21.1, 105.1)]
    requested = []
    response = {
        "code": "Ok",
        # start, a, b, end; B -> A is the road-duration optimum.
        "durations": [
            [0, 100, 1, 999],
            [999, 0, 100, 1],
            [999, 1, 0, 100],
            [999, 999, 999, 0],
        ],
        "distances": [
            [0, 1000, 10, 9999],
            [9999, 0, 1000, 10],
            [9999, 10, 0, 1000],
            [9999, 9999, 9999, 0],
        ],
    }

    def fake_osrm(endpoint, coords, extra_params=""):
        requested.append((endpoint, coords))
        return response

    with patch.object(step6_routing, "_osrm_request", side_effect=fake_osrm):
        result = step6_routing.optimize_route_open(
            sites, start_anchor=(20.0, 104.0), end_anchor=(22.0, 106.0)
        )

    check("one table request", len(requested), 1)
    check("anchors included in OSRM request", len(requested[0][1]), 4)
    check("road-duration order", [site.site.id for site in result.ordered_sites], ["b", "a"])
    check("ordered distance matrix", result.distance_matrix.tolist(), [[0.0, 10.0], [1000.0, 0.0]])
    check("ordered duration matrix", result.duration_matrix.tolist(), [[0.0, 1.0], [100.0, 0.0]])
    check("road duration includes fixed anchor legs", result.total_duration_s, 3.0)


def test_unreachable_or_malformed_osrm_keeps_ttdp_order():
    sites = [make_site("a", 21.0, 105.0), make_site("b", 21.1, 105.1)]
    malformed = {"code": "Ok", "durations": [[0, None], [1, 0]], "distances": [[0, 1], [1, 0]]}
    with patch.object(step6_routing, "_osrm_request", return_value=malformed):
        result = step6_routing.optimize_route_open(sites)

    check("unreachable preserves order", [site.site.id for site in result.ordered_sites], ["a", "b"])
    check("unreachable has no reporting matrix", result.distance_matrix, None)
    check("unreachable has no duration", result.total_duration_s, None)


async def test_geometry_step_uses_ordered_result_and_preserves_osrm_reporting_matrix():
    a, b = make_site("a", 21.0, 105.0), make_site("b", 21.1, 105.1)
    result = step6_routing.OpenRouteResult(
        ordered_sites=[b, a],
        distance_matrix=np.array([[0.0, 10.0], [1000.0, 0.0]]),
        duration_matrix=np.array([[0.0, 1.0], [100.0, 0.0]]),
        total_duration_s=7201.0,
    )
    ctx = PipelineContext(input=TripInput(duration_days=1), request_id="routing-test")
    ctx.trip_request = TripRequest(destination_area="HN", duration_days=1, interests=["history"])
    ctx.optimized_clusters = [[a, b]]
    geometry_inputs = []

    def fake_geometry(sites, start=None, end=None):
        geometry_inputs.append([site.site.id for site in sites])
        return []

    with patch("services.ai_service.steps.step6_geometry.optimize_route_open", return_value=result), \
         patch("services.ai_service.steps.step6_geometry.get_route_geometry", side_effect=fake_geometry):
        await GeometryStep().execute(ctx)

    check("GeometryStep uses optimizer order", [site.site.id for site in ctx.optimized_clusters[0]], ["b", "a"])
    check("geometry uses optimizer order", geometry_inputs, [["b", "a"]])
    check("assembly road matrix has final order", [site.site.id for site in ctx.distance_matrix["sites"]], ["b", "a"])
    check("assembly road matrix is retained", ctx.distance_matrix["matrix"].tolist(), [[0.0, 10.0], [1000.0, 0.0]])


async def test_intermediate_day_uses_same_previous_endpoint_for_optimization_and_geometry():
    first, second = make_site("first", 21.0, 105.0), make_site("second", 21.2, 105.2)
    ctx = PipelineContext(input=TripInput(duration_days=2), request_id="anchor-test")
    ctx.trip_request = TripRequest(destination_area="HN", duration_days=2, interests=["history"])
    ctx.optimized_clusters = [[first], [second]]
    optimizer_starts = []
    geometry_starts = []

    def fake_optimize(sites, start_anchor=None, end_anchor=None):
        optimizer_starts.append(start_anchor)
        return step6_routing.OpenRouteResult(
            ordered_sites=list(sites),
            distance_matrix=np.zeros((len(sites), len(sites))),
            duration_matrix=np.zeros((len(sites), len(sites))),
            total_duration_s=0.0,
        )

    def fake_geometry(sites, start=None, end=None):
        geometry_starts.append((sites[0].site.id, start))
        return []

    with patch("services.ai_service.steps.step6_geometry.optimize_route_open", side_effect=fake_optimize), \
         patch("services.ai_service.steps.step6_geometry.get_route_geometry", side_effect=fake_geometry):
        await GeometryStep().execute(ctx)

    expected_previous_endpoint = (first.site.lat, first.site.lng)
    check("intermediate optimizer gets previous endpoint", optimizer_starts[1], expected_previous_endpoint)
    geometry_start_by_site = dict(geometry_starts)
    check("intermediate geometry gets previous endpoint", geometry_start_by_site["second"], expected_previous_endpoint)


def test_assembly_combines_real_and_fallback_distances_when_osrm_is_partial():
    a, b = make_site("a", 21.0, 105.0), make_site("b", 21.0, 105.01)
    c, d = make_site("c", 21.1, 105.0), make_site("d", 21.1, 105.01)
    days = [
        DayPlan(day=1, items=[ItineraryItem(type="heritage", ref_id="a"), ItineraryItem(type="heritage", ref_id="b")]),
        DayPlan(day=2, items=[ItineraryItem(type="heritage", ref_id="c"), ItineraryItem(type="heritage", ref_id="d")]),
    ]
    trip = TripRequest(destination_area="HN", duration_days=2, interests=["history"])
    # Day 1 has a 1km OSRM leg; day 2's NaN entry must fall back to haversine.
    matrix = np.array([
        [0.0, 1000.0, np.nan, np.nan],
        [1000.0, 0.0, np.nan, np.nan],
        [np.nan, np.nan, 0.0, np.nan],
        [np.nan, np.nan, np.nan, 0.0],
    ])
    itinerary = assemble_itinerary(days, [[a, b], [c, d]], trip, distance_matrix={
        "sites": [a, b, c, d], "matrix": matrix,
    })
    # The total must contain the 1km OSRM leg plus day 2's haversine fallback.
    if itinerary.total_distance_km <= 2.0:
        raise AssertionError(f"partial OSRM total excluded fallback distance: {itinerary.total_distance_km}")


if __name__ == "__main__":
    test_open_two_opt_keeps_fixed_anchor_costs()
    test_optimizer_uses_one_osrm_table_with_anchors_and_returns_road_matrices()
    test_unreachable_or_malformed_osrm_keeps_ttdp_order()
    asyncio.run(test_geometry_step_uses_ordered_result_and_preserves_osrm_reporting_matrix())
    asyncio.run(test_intermediate_day_uses_same_previous_endpoint_for_optimization_and_geometry())
    test_assembly_combines_real_and_fallback_distances_when_osrm_is_partial()
    print("road routing tests passed")
