"""
Pipeline context — Holds all intermediate state flowing through the pipeline.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.ai_service.models import (
    TripInput, TripRequest, HeritageSite, Forecast,
    ScoredSite, DayPlan, Itinerary,
)


@dataclass
class PipelineContext:
    input: TripInput
    request_id: str = ""

    trip_request: Optional[TripRequest] = None
    candidates: List[HeritageSite] = field(default_factory=list)
    forecasts: Dict[str, List[Forecast]] = field(default_factory=dict)
    scored_sites: List[ScoredSite] = field(default_factory=list)
    optimized_clusters: List[List[ScoredSite]] = field(default_factory=list)
    route_geometries: List = field(default_factory=list)
    distance_matrix: Optional[dict] = None
    day_plans: List[DayPlan] = field(default_factory=list)
    itinerary: Optional[Itinerary] = None

    step_timings: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
