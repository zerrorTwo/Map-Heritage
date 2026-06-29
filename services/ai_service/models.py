"""
Domain entity models matching the canonical schema from §2 of the architecture spec.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class HeritageSite(BaseModel):
    id: str
    name: str
    province: str
    lat: float
    lng: float
    categories: List[str] = Field(default_factory=list)
    description: str = ""
    long_description: str = ""
    visit_tips: str = ""
    reference_url: str = ""
    opening_hours: str = "08:00-17:00"
    estimated_visit_minutes: int = 60
    indoor_score: float = 0.5
    outdoor_score: float = 0.5
    suitable_for_children: bool = True
    suitable_for_elderly: bool = True
    ticket_price: int = 0
    popularity_score: float = 0.5
    historical_importance_score: float = 0.5


class Restaurant(BaseModel):
    id: str
    name: str
    lat: float
    lng: float
    province: str
    specialty_tags: List[str] = Field(default_factory=list)
    rating: float = 4.0
    review_count: int = 0
    price_level: int = 2
    opening_hours: str = "06:00-22:00"
    source: str = "manual"
    distance_to_nearest_heritage_m: float = 0.0


class TripRequest(BaseModel):
    destination_area: str = "Hà Nội"
    destination_provinces: List[str] = Field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    duration_days: int = 1
    number_of_people: int = 1
    interests: List[str] = Field(default_factory=lambda: ["history", "architecture", "local_food"])
    pace: str = "moderate"
    travel_mode: str = "mixed"
    budget_level: str = "medium"
    constraints: List[str] = Field(default_factory=list)
    must_visit_site_ids: List[str] = Field(default_factory=list)
    start_location: Optional[dict] = None


class ItineraryItem(BaseModel):
    time: str = "08:00-09:00"
    type: str = "heritage"
    ref_id: str = ""
    name: str = ""
    reason: str = ""
    travel_from_previous_minutes: int = 0
    distance_from_previous_m: float = 0.0


class DayPlan(BaseModel):
    day: int
    date: str = ""
    items: List[ItineraryItem] = Field(default_factory=list)


class Itinerary(BaseModel):
    itinerary_id: str = ""
    summary: str = ""
    total_score: float = 0.0
    total_distance_km: float = 0.0
    days: List[DayPlan] = Field(default_factory=list)
    route_geometries: List[List[List[float]]] = Field(default_factory=list)


class ScoredSite(BaseModel):
    site: HeritageSite
    score: float = 0.0
    interest_match: float = 0.0
    weather_suitability: float = 1.0


class Forecast(BaseModel):
    date: str
    hour: int
    temperature_c: float = 25.0
    rain_probability: float = 0.0
    uv_index: float = 5.0
    pm2_5: float = 15.0
    aqi_level: str = "good"


class TripInput(BaseModel):
    """Free-text or structured user input before normalization."""
    raw_text: Optional[str] = None
    destination_area: str = "Hà Nội"
    destination_provinces: List[str] = Field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    duration_days: int = 1
    number_of_people: int = 1
    interests: List[str] = Field(default_factory=lambda: ["history", "local_food"])
    pace: str = "moderate"
    travel_mode: str = "mixed"
    budget_level: str = "medium"
    constraints: List[str] = Field(default_factory=list)
    must_visit_site_ids: List[str] = Field(default_factory=list)
    start_lat: float = 21.0285
    start_lng: float = 105.8542
