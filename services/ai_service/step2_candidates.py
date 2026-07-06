"""
Step 2 — Generate candidates: Filter heritage sites by area, interest, constraints.
MUST-VISIT sites are ALWAYS included with top priority, regardless of filters.
"""

from typing import List, Optional
from services.ai_service.models import HeritageSite, TripRequest
import numpy as np


CATEGORY_SIM = {
    ("history", "architecture"): 0.6,
    ("history", "museum"): 0.7,
    ("history", "spiritual"): 0.4,
    ("history", "religion"): 0.4,
    ("history", "culture"): 0.6,
    ("history", "war"): 0.8,
    ("history", "palace"): 0.7,
    ("history", "tomb"): 0.7,
    ("history", "citadel"): 0.8,
    ("history", "monument"): 0.7,
    ("history", "temple"): 0.4,
    ("history", "pagoda"): 0.4,
    ("architecture", "museum"): 0.5,
    ("architecture", "spiritual"): 0.5,
    ("architecture", "religion"): 0.5,
    ("architecture", "temple"): 0.6,
    ("architecture", "pagoda"): 0.5,
    ("architecture", "church"): 0.6,
    ("architecture", "palace"): 0.7,
    ("architecture", "bridge"): 0.6,
    ("architecture", "tower"): 0.6,
    ("architecture", "citadel"): 0.6,
    ("architecture", "monument"): 0.5,
    ("architecture", "culture"): 0.4,
    ("architecture", "history"): 0.6,
    ("spiritual", "religion"): 0.9,
    ("spiritual", "temple"): 0.8,
    ("spiritual", "pagoda"): 0.8,
    ("spiritual", "church"): 0.7,
    ("spiritual", "history"): 0.4,
    ("spiritual", "architecture"): 0.5,
    ("spiritual", "culture"): 0.4,
    ("craft_village", "art"): 0.6,
    ("craft_village", "culture"): 0.6,
    ("craft_village", "village"): 0.7,
    ("craft_village", "history"): 0.4,
    ("craft_village", "local_food"): 0.3,
    ("museum", "history"): 0.7,
    ("museum", "art"): 0.7,
    ("museum", "culture"): 0.6,
    ("museum", "war"): 0.7,
    ("museum", "architecture"): 0.5,
    ("local_food", "culture"): 0.5,
    ("local_food", "market"): 0.6,
    ("local_food", "street"): 0.5,
    ("local_food", "festival"): 0.4,
    ("local_food", "village"): 0.3,
    ("nature", "photography"): 0.6,
    ("nature", "landscape"): 0.8,
    ("nature", "mountain"): 0.7,
    ("nature", "beach"): 0.7,
    ("nature", "cave"): 0.6,
    ("nature", "waterfall"): 0.7,
    ("nature", "lake"): 0.6,
    ("nature", "park"): 0.6,
    ("nature", "garden"): 0.5,
    ("nature", "island"): 0.6,
    ("nature", "forest"): 0.8,
    ("nature", "river"): 0.5,
    ("photography", "nature"): 0.6,
    ("photography", "landscape"): 0.7,
    ("photography", "architecture"): 0.5,
    ("photography", "street"): 0.5,
    ("photography", "sunset"): 0.6,
    ("photography", "beach"): 0.4,
    ("photography", "mountain"): 0.5,
    ("photography", "culture"): 0.4,
    ("culture", "history"): 0.6,
    ("culture", "festival"): 0.7,
    ("culture", "craft_village"): 0.6,
    ("culture", "local_food"): 0.5,
    ("culture", "spiritual"): 0.4,
    ("culture", "museum"): 0.6,
    ("culture", "village"): 0.5,
    ("culture", "street"): 0.5,
    ("art", "museum"): 0.7,
    ("art", "architecture"): 0.5,
    ("art", "craft_village"): 0.6,
    ("art", "culture"): 0.5,
    ("war", "history"): 0.8,
    ("war", "museum"): 0.7,
    ("temple", "spiritual"): 0.8,
    ("temple", "religion"): 0.8,
    ("temple", "history"): 0.4,
    ("temple", "architecture"): 0.6,
    ("pagoda", "spiritual"): 0.8,
    ("pagoda", "religion"): 0.8,
    ("pagoda", "history"): 0.4,
    ("pagoda", "architecture"): 0.5,
    ("church", "spiritual"): 0.7,
    ("church", "religion"): 0.7,
    ("church", "architecture"): 0.6,
    ("market", "local_food"): 0.6,
    ("market", "culture"): 0.5,
    ("market", "street"): 0.4,
    ("village", "culture"): 0.5,
    ("village", "craft_village"): 0.7,
    ("village", "nature"): 0.3,
    ("palace", "history"): 0.7,
    ("palace", "architecture"): 0.7,
    ("tomb", "history"): 0.7,
    ("tomb", "architecture"): 0.5,
    ("citadel", "history"): 0.8,
    ("citadel", "architecture"): 0.6,
    ("monument", "history"): 0.7,
    ("monument", "architecture"): 0.5,
    ("bridge", "architecture"): 0.6,
    ("bridge", "history"): 0.4,
    ("bridge", "photography"): 0.4,
    ("tower", "architecture"): 0.6,
    ("tower", "history"): 0.4,
    ("cave", "nature"): 0.6,
    ("cave", "adventure"): 0.5,
    ("waterfall", "nature"): 0.7,
    ("waterfall", "photography"): 0.5,
    ("lake", "nature"): 0.6,
    ("lake", "photography"): 0.4,
    ("park", "nature"): 0.6,
    ("park", "garden"): 0.5,
    ("garden", "nature"): 0.5,
    ("garden", "park"): 0.5,
    ("forest", "nature"): 0.8,
    ("forest", "adventure"): 0.5,
    ("mountain", "nature"): 0.7,
    ("mountain", "adventure"): 0.5,
    ("mountain", "photography"): 0.5,
    ("beach", "nature"): 0.7,
    ("beach", "photography"): 0.4,
    ("beach", "island"): 0.5,
    ("island", "nature"): 0.6,
    ("island", "beach"): 0.5,
    ("landscape", "nature"): 0.8,
    ("landscape", "photography"): 0.7,
    ("religion", "spiritual"): 0.9,
    ("religion", "temple"): 0.8,
    ("religion", "pagoda"): 0.8,
    ("religion", "church"): 0.7,
    ("religion", "history"): 0.4,
    ("religion", "architecture"): 0.5,
    ("street", "photography"): 0.5,
    ("street", "culture"): 0.5,
    ("street", "local_food"): 0.5,
    ("street", "market"): 0.4,
    ("festival", "culture"): 0.7,
    ("festival", "local_food"): 0.4,
    ("festival", "spiritual"): 0.3,
    ("adventure", "nature"): 0.5,
    ("adventure", "mountain"): 0.5,
    ("adventure", "cave"): 0.5,
    ("adventure", "forest"): 0.5,
    ("unesco", "history"): 0.8,
    ("unesco", "architecture"): 0.6,
    ("unesco", "culture"): 0.7,
    ("unesco", "nature"): 0.5,
    ("unesco", "museum"): 0.6,
    ("unesco", "spiritual"): 0.4,
    ("unesco", "photography"): 0.5,
    ("history", "unesco"): 0.8,
    ("architecture", "unesco"): 0.6,
    ("culture", "unesco"): 0.7,
    ("nature", "unesco"): 0.5,
    ("museum", "unesco"): 0.6,
    ("entertainment", "culture"): 0.5,
    ("entertainment", "local_food"): 0.3,
    ("entertainment", "photography"): 0.3,
    ("entertainment", "nature"): 0.2,
    ("entertainment", "architecture"): 0.2,
    ("entertainment", "street"): 0.4,
    ("culture", "entertainment"): 0.5,
    ("local_food", "entertainment"): 0.3,
    ("photography", "entertainment"): 0.3,
    ("craft_village", "unesco"): 0.5,
    ("unesco", "craft_village"): 0.5,
    ("spiritual", "museum"): 0.3,
    ("museum", "spiritual"): 0.3,
    ("spiritual", "culture"): 0.4,
    ("craft_village", "museum"): 0.3,
    ("museum", "craft_village"): 0.3,
}


def _category_similarity(user_interest: str, site_category: str) -> float:
    """Return similarity between two categories, with symmetry support."""
    if user_interest == site_category:
        return 1.0
    key = (user_interest.lower(), site_category.lower())
    if key in CATEGORY_SIM:
        return CATEGORY_SIM[key]
    rev_key = (site_category.lower(), user_interest.lower())
    if rev_key in CATEGORY_SIM:
        return CATEGORY_SIM[rev_key]
    return 0.0


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in meters."""
    R = 6371000
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def generate_candidates(
    trip: TripRequest,
    all_sites: List[HeritageSite],
    top_n: int = 30,
) -> List[HeritageSite]:
    """
    Filter heritage sites STRICTLY by selected provinces only.
    Must-visit sites are ALWAYS included with top priority.
    No radius fallback — only sites from target provinces.
    """
    must_visit_ids = set(trip.must_visit_site_ids)
    must_visits: List[HeritageSite] = []
    candidates: List[HeritageSite] = []
    site_map = {s.id: s for s in all_sites}

    # Step 1: Force-include must-visit sites (regardless of province)
    for sid in must_visit_ids:
        if sid in site_map:
            must_visits.append(site_map[sid])

    # Step 2: STRICT province filter — only target provinces
    target_provinces = set(trip.destination_provinces or [trip.destination_area])
    
    for site in all_sites:
        # Skip already-included must-visit sites
        if site.id in must_visit_ids:
            continue

        # STRICT: only include sites from selected provinces
        if site.province not in target_provinces:
            continue

        if not _satisfies_constraints(site, trip.constraints):
            continue

        candidates.append(site)

    # Step 3: Rank by interest overlap
    candidates.sort(
        key=lambda s: _interest_overlap(s, trip.interests),
        reverse=True,
    )

    # Step 4: Combine — must-visit sites FIRST, then top recommended
    remaining_slots = max(0, top_n - len(must_visits))
    result = must_visits + candidates[:remaining_slots]

    return result


def _satisfies_constraints(site: HeritageSite, constraints: List[str]) -> bool:
    if "elderly_friendly" in constraints and not site.suitable_for_elderly:
        return False
    if "child_friendly" in constraints and not site.suitable_for_children:
        return False
    if "prefer_indoor" in constraints and site.indoor_score < 0.4:
        return False
    if "prefer_outdoor" in constraints and site.outdoor_score < 0.4:
        return False
    return True


def _interest_overlap(site: HeritageSite, interests: List[str]) -> float:
    """Partial-credit interest similarity using category similarity matrix."""
    if not interests:
        return 0.0
    site_cats = [c.lower() for c in site.categories]
    total = 0.0
    for user_interest in interests:
        best = max(_category_similarity(user_interest.lower(), sc) for sc in site_cats) if site_cats else 0.0
        total += best
    return total / len(interests)

