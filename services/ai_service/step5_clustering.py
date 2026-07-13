"""
Step 5 — Partition scored sites into per-day clusters.
Dependency-free geographic clustering: pace-capped, must-visit-seeded,
farthest-point recommended seeds, then MMR-ordered nearest-day back-fill.
"""

from typing import List, Optional, Tuple
from services.ai_service.models import ScoredSite, HeritageSite, DayPlan, ItineraryItem
from services.ai_service.step2_candidates import haversine_distance


PACE_LIMITS = {
    "relaxed": 3,
    "moderate": 5,
    "packed": 7,
}


def _centroid(cluster: List[ScoredSite]) -> Tuple[float, float]:
    """Return (mean_lat, mean_lng) over a cluster. Guarded for empties."""
    if not cluster:
        return (0.0, 0.0)
    mean_lat = sum(s.site.lat for s in cluster) / len(cluster)
    mean_lng = sum(s.site.lng for s in cluster) / len(cluster)
    return (mean_lat, mean_lng)


def _hav(scored_site: ScoredSite, latlng: Tuple[float, float]) -> float:
    """Haversine meters between a ScoredSite and a (lat, lng) point."""
    lat, lng = latlng
    return haversine_distance(scored_site.site.lat, scored_site.site.lng, lat, lng)


def partition_into_days(
    scored_sites: List[ScoredSite],
    duration_days: int,
    pace: str = "moderate",
    must_visit_ids: Optional[List[str]] = None,
) -> List[List[ScoredSite]]:
    """
    Partition scored sites into exactly `duration_days` day-clusters using
    geographic proximity, capped per-day by pace, must-visit-seeded, with
    farthest-point recommended seeds and nearest-day MMR back-fill.
    """
    D = max(1, duration_days)
    mv = set(must_visit_ids or [])
    cap = PACE_LIMITS.get(pace, 5)

    if not scored_sites:
        return [[] for _ in range(D)]

    must = [s for s in scored_sites if s.site.id in mv]          # guaranteed included
    rec = [s for s in scored_sites if s.site.id not in mv]       # preserves incoming (MMR) order

    # Single day
    if D == 1:
        return [must + rec[: max(0, cap - len(must))]]

    clusters: List[List[ScoredSite]] = [[] for _ in range(D)]
    used = set()

    # Seed 1: spread must-visit across days, round-robin by geo (lat,lng) order
    for i, s in enumerate(sorted(must, key=lambda s: (s.site.lat, s.site.lng))):
        clusters[i % D].append(s)
        used.add(s.site.id)

    # Seed 2: fill still-empty days with farthest-point recommended seeds
    centroids = [_centroid(c) for c in clusters if c]
    for day_i in [i for i in range(D) if not clusters[i]]:
        pool = [s for s in rec if s.site.id not in used]
        if not pool:
            break
        if not centroids:
            pick = pool[0]                                        # top MMR/score as first seed
        else:
            pick = max(pool, key=lambda s: min(_hav(s, c) for c in centroids))
        clusters[day_i].append(pick)
        used.add(pick.site.id)
        centroids.append((pick.site.lat, pick.site.lng))

    # Assign remaining recommended to nearest NON-FULL day (backfill in MMR order)
    for s in rec:
        if s.site.id in used:
            continue
        candidates = [i for i in range(D) if len(clusters[i]) < cap]
        if not candidates:
            break                                                # all full → drop (pace cap)
        best = min(candidates, key=lambda i: _hav(s, _centroid(clusters[i])))
        clusters[best].append(s)
        used.add(s.site.id)

    # Order within day: must-visit first, then score desc (Step 6 re-optimizes order anyway)
    for c in clusters:
        c.sort(key=lambda s: (0 if s.site.id in mv else 1, -s.score))

    return clusters   # length == D


def clusters_to_day_plans(
    clusters: List[List[ScoredSite]],
    start_date: str = "",
) -> List[DayPlan]:
    """Convert clusters to DayPlan objects for further processing."""
    from datetime import datetime, timedelta

    days = []
    base_date = datetime.now()
    if start_date:
        try:
            base_date = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            pass

    for day_idx, cluster in enumerate(clusters):
        day_date = (base_date + timedelta(days=day_idx)).strftime("%Y-%m-%d")
        items = []
        for sc in cluster:
            items.append(ItineraryItem(
                type="heritage",
                ref_id=sc.site.id,
                name=sc.site.name,
                reason=f"Score: {sc.score:.2f} | Interest match: {sc.interest_match:.0%}",
            ))
        days.append(DayPlan(day=day_idx + 1, date=day_date, items=items))
    return days
