"""
Step 4 — Score each site using the scoring formula from §4 Step 4.

site_score =
    0.30 * interest_match_score +
    0.20 * historical_importance_score +
    0.15 * weather_suitability_score +
    0.15 * distance_score +
    0.10 * popularity_score +
    0.05 * accessibility_score +
    0.05 * budget_score

Phase 2: derives richer popularity/historical_importance/accessibility from
category signals instead of relying on near-uniform raw data fields.
"""

import math
from typing import List, Optional
from services.ai_service.models import HeritageSite, TripRequest, Forecast, ScoredSite
from services.ai_service.step2_candidates import _category_similarity


BASE_WEIGHTS = {
    "interest_match": 0.30,
    "historical_importance": 0.20,
    "weather_suitability": 0.15,
    "distance": 0.15,
    "popularity": 0.10,
    "accessibility": 0.05,
    "budget": 0.05,
}

PROVINCE_TIER = {
    "Hà Nội": 0.08, "Thừa Thiên Huế": 0.08, "Quảng Nam": 0.08,
    "TP. Hồ Chí Minh": 0.06, "Hồ Chí Minh": 0.06, "Đà Nẵng": 0.06,
    "Ninh Bình": 0.05, "Quảng Ninh": 0.05, "Hải Phòng": 0.04,
    "Khánh Hòa": 0.04, "Lào Cai": 0.04, "Hà Giang": 0.04,
    "Lâm Đồng": 0.04, "Cần Thơ": 0.03, "Bình Định": 0.03,
    "Thanh Hóa": 0.03, "Nghệ An": 0.03, "Bắc Ninh": 0.03,
    "Vĩnh Phúc": 0.02, "Hải Dương": 0.02, "Hà Nam": 0.02,
    "Nam Định": 0.02, "Thái Bình": 0.02, "Bắc Giang": 0.02,
    "Phú Thọ": 0.02, "Hòa Bình": 0.02, "Yên Bái": 0.02,
    "Tuyên Quang": 0.02, "Sơn La": 0.02, "Điện Biên": 0.02,
    "Lai Châu": 0.02, "Cao Bằng": 0.02, "Bắc Kạn": 0.02,
    "Lạng Sơn": 0.02, "Quảng Bình": 0.02, "Quảng Trị": 0.02,
    "Quảng Ngãi": 0.02, "Phú Yên": 0.02, "Đắk Lắk": 0.02,
    "Gia Lai": 0.02, "Kon Tum": 0.02, "Đắk Nông": 0.02,
    "Bình Phước": 0.02, "Tây Ninh": 0.02, "Bình Dương": 0.02,
    "Đồng Nai": 0.02, "Bà Rịa - Vũng Tàu": 0.02,
    "Long An": 0.02, "Tiền Giang": 0.02, "Bến Tre": 0.02,
    "Trà Vinh": 0.02, "Vĩnh Long": 0.02, "Đồng Tháp": 0.02,
    "An Giang": 0.02, "Kiên Giang": 0.02, "Hậu Giang": 0.02,
    "Sóc Trăng": 0.02, "Bạc Liêu": 0.02, "Cà Mau": 0.02,
    "Bình Thuận": 0.02, "Ninh Thuận": 0.02,
}


def _get_dynamic_weights(trip: TripRequest) -> dict:
    w = dict(BASE_WEIGHTS)
    boosted = False
    if any(c in (trip.constraints or []) for c in ("elderly_friendly", "child_friendly")):
        w["accessibility"] = 0.15
        boosted = True
    if (trip.budget_level or "").lower() == "low":
        w["budget"] = 0.15
        boosted = True
    if boosted:
        total = sum(w.values())
        if total > 0:
            w = {k: v / total for k, v in w.items()}
    return w


def derive_popularity(site: HeritageSite) -> float:
    """Derive richer popularity from category signals + province tier (range ~0.45-0.95)."""
    score = 0.45
    cats = set(c.lower() for c in site.categories)
    if "unesco" in cats:
        score += 0.25
    if "museum" in cats:
        score += 0.10
    if "history" in cats:
        score += 0.08
    if "architecture" in cats:
        score += 0.08
    if "craft_village" in cats:
        score += 0.05
    if "entertainment" in cats:
        score += 0.05
    if "spiritual" in cats:
        score += 0.04
    if "nature" in cats:
        score += 0.04
    if site.description or site.long_description:
        score += 0.04
    if site.visit_tips:
        score += 0.03
    if site.reference_url:
        score += 0.02
    tier = PROVINCE_TIER.get(site.province, 0.01)
    score += tier
    return 0.95 if site.rating is not None and site.review_count is not None else min(0.95, score)


def derive_historical_importance(site: HeritageSite) -> float:
    """Derive richer historical importance from category signals + province tier (range ~0.45-0.95)."""
    score = 0.45
    cats = set(c.lower() for c in site.categories)
    if "unesco" in cats:
        score += 0.30
    if "history" in cats:
        score += 0.15
    if "museum" in cats:
        score += 0.10
    if "architecture" in cats:
        score += 0.08
    if "spiritual" in cats:
        score += 0.05
    if "craft_village" in cats:
        score += 0.03
    if site.long_description:
        score += 0.02
    tier = PROVINCE_TIER.get(site.province, 0.01)
    score += tier
    return min(0.95, score)


def derive_accessibility(site: HeritageSite, constraints: List[str]) -> float:
    """Rich accessibility from indoor/outdoor balance, visit duration, and constraints."""
    score = 0.50
    score += site.indoor_score * 0.25
    minutes = site.estimated_visit_minutes
    if minutes <= 30:
        score += 0.10
    elif minutes <= 60:
        score += 0.08
    elif minutes <= 90:
        score += 0.05

    if "elderly_friendly" in constraints:
        score += 0.05 if site.indoor_score > 0.4 else 0.0
        score += 0.05 if minutes <= 60 else 0.0
    if "child_friendly" in constraints:
        score += 0.05 if minutes <= 60 else 0.0
    if "avoid_long_walking" in constraints:
        score += 0.10 if site.indoor_score > 0.5 else -0.05

    if not constraints:
        score += 0.08

    return max(0.0, min(1.0, score))


def compute_interest_match(site: HeritageSite, interests: List[str]) -> float:
    if not interests:
        return 0.5
    site_cats = [c.lower() for c in site.categories]
    total = 0.0
    for user_interest in interests:
        best = max(_category_similarity(user_interest.lower(), sc) for sc in site_cats) if site_cats else 0.0
        total += best
    return total / len(interests)


def compute_weather_suitability(
    site: HeritageSite,
    forecasts: List[Forecast],
    visit_hour: int = 10,
) -> float:
    score = 1.0
    if not forecasts:
        return score
    best_fc = forecasts[0]
    best_diff = abs(forecasts[0].hour - visit_hour)
    for f in forecasts:
        diff = abs(f.hour - visit_hour)
        if diff < best_diff:
            best_diff = diff
            best_fc = f

    temp = best_fc.temperature_c
    rain = best_fc.rain_probability
    uv = best_fc.uv_index

    if rain > 70 and site.outdoor_score > 0.6:
        score -= 0.35
    elif rain > 50 and site.outdoor_score > 0.6:
        score -= 0.15
    if temp > 35 and site.outdoor_score > 0.6:
        score -= 0.25
    elif temp > 32 and site.outdoor_score > 0.6:
        score -= 0.10
    if uv > 8 and 11 <= visit_hour <= 14:
        score -= 0.20
    elif uv > 6 and 11 <= visit_hour <= 15:
        score -= 0.10
    if temp < 10 and site.outdoor_score > 0.6:
        score -= 0.15
    elif temp < 15 and site.outdoor_score > 0.6:
        score -= 0.05

    return max(0.0, min(1.0, score))


def compute_distance_score(
    site: HeritageSite, start_lat: float, start_lng: float, half_dist_km: float = 20.0
) -> float:
    """Logarithmic distance decay — gentler than linear, higher floor.
    half_dist_km=20 means a site 20km away scores 0.5 instead of 0.8 (linear)."""
    dlat = site.lat - start_lat
    dlng = site.lng - start_lng
    dist_km = math.sqrt(dlat**2 + dlng**2) * 111.32
    return max(0.15, 1.0 / (1.0 + dist_km / half_dist_km))


def compute_budget_fit(site: HeritageSite, budget_level: str) -> float:
    budget_thresholds = {"low": (0, 30000), "medium": (0, 100000), "high": (0, 1000000)}
    lo, hi = budget_thresholds.get(budget_level, (0, 100000))
    if site.ticket_price <= lo:
        return 1.0
    if site.ticket_price >= hi:
        return 0.2
    return 1.0 - (site.ticket_price - lo) / (hi - lo)


def score_site(
    site: HeritageSite,
    trip: TripRequest,
    forecasts: List[Forecast],
    start_lat: float = 21.0285,
    start_lng: float = 105.8542,
    visit_hour: int = 10,
) -> ScoredSite:
    w = _get_dynamic_weights(trip)

    interest = compute_interest_match(site, trip.interests)
    weather = compute_weather_suitability(site, forecasts, visit_hour)
    distance = compute_distance_score(site, start_lat, start_lng)
    accessibility = derive_accessibility(site, trip.constraints)
    budget = compute_budget_fit(site, trip.budget_level)
    popularity = derive_popularity(site)
    historical = derive_historical_importance(site)

    total = (
        w["interest_match"] * interest
        + w["historical_importance"] * historical
        + w["weather_suitability"] * weather
        + w["distance"] * distance
        + w["popularity"] * popularity
        + w["accessibility"] * accessibility
        + w["budget"] * budget
    )

    return ScoredSite(
        site=site,
        score=round(total, 4),
        interest_match=round(interest, 4),
        weather_suitability=round(weather, 4),
    )


def score_all_sites(
    candidates: List[HeritageSite],
    trip: TripRequest,
    forecasts_by_site: dict,
) -> List[ScoredSite]:
    start = trip.start_location or {"lat": 21.0285, "lng": 105.8542}
    scored = []
    for site in candidates:
        fcasts = forecasts_by_site.get(site.id, [])
        sc = score_site(site, trip, fcasts, start["lat"], start["lng"])
        scored.append(sc)
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored
