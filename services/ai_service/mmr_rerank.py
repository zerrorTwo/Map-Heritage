"""
MMR (Maximal Marginal Relevance) diversity re-ranking.
Prevents the candidate pool from being dominated by near-duplicate
high-scoring sites in the same neighborhood, which indirectly raises
preference_fit and schedule_balance in step8.
"""

import math
from typing import List
from services.ai_service.models import ScoredSite


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _site_similarity(a: ScoredSite, b: ScoredSite, geo_weight: float = 0.6) -> float:
    """Blended similarity: geographic proximity + category overlap."""
    dist_m = haversine_m(a.site.lat, a.site.lng, b.site.lat, b.site.lng)
    geo_sim = max(0.0, 1.0 - dist_m / 10000.0)
    a_cats = set(c.lower() for c in a.site.categories)
    b_cats = set(c.lower() for c in b.site.categories)
    if not a_cats or not b_cats:
        cat_sim = 0.5
    else:
        cat_sim = len(a_cats & b_cats) / len(a_cats | b_cats)
    return geo_weight * geo_sim + (1.0 - geo_weight) * cat_sim


def mmr_rerank(
    scored_sites: List[ScoredSite],
    lambd: float = 0.7,
    top_k: int = None,
    geo_weight: float = 0.6,
) -> List[ScoredSite]:
    """
    Maximal Marginal Relevance re-ranking.
    lambd: weight for score (1-lambd = weight for diversity).
    top_k: cap output size (None = all).
    """
    if len(scored_sites) <= 1:
        return list(scored_sites)

    remaining = list(scored_sites)
    selected = [remaining.pop(0)]

    while remaining and (top_k is None or len(selected) < top_k):
        best_idx = max(
            range(len(remaining)),
            key=lambda i: lambd * remaining[i].score
            - (1.0 - lambd) * max(
                _site_similarity(remaining[i], s, geo_weight) for s in selected
            ),
        )
        selected.append(remaining.pop(best_idx))

    return selected
