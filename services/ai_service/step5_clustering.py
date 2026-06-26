"""
Step 5 — Split into day-clusters.
Uses geographic clustering (k-means) with pace constraints.
"""

from typing import List
from services.ai_service.models import ScoredSite, HeritageSite, DayPlan, ItineraryItem
import numpy as np

try:
    from sklearn.cluster import KMeans, DBSCAN
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


PACE_LIMITS = {
    "relaxed": 3,
    "moderate": 5,
    "packed": 7,
}


def split_into_days(
    scored_sites: List[ScoredSite],
    duration_days: int,
    pace: str = "moderate",
) -> List[List[ScoredSite]]:
    """
    Split scored sites into day clusters using k-means on coordinates.
    Each cluster capped by pace limit.
    """
    if not scored_sites:
        return [[] for _ in range(duration_days)]

    max_per_day = PACE_LIMITS.get(pace, 5)
    total_capacity = duration_days * max_per_day
    sites = scored_sites[:total_capacity]

    if duration_days == 1:
        return [sites]

    coords = np.array([[s.site.lat, s.site.lng] for s in sites])

    if HAS_SKLEARN and len(sites) >= duration_days * 2:
        k = min(duration_days, len(sites))
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(coords)
    else:
        labels = _simple_geographic_split(coords, duration_days)

    clusters: List[List[ScoredSite]] = [[] for _ in range(duration_days)]
    for i, s in enumerate(sites):
        cluster_idx = labels[i] % duration_days
        clusters[cluster_idx].append(s)

    balanced = []
    for cluster in clusters:
        cluster.sort(key=lambda s: s.score, reverse=True)
        balanced.append(cluster[:max_per_day])

    return balanced


def _simple_geographic_split(coords: np.ndarray, k: int) -> np.ndarray:
    """Fallback split by latitude banding."""
    lats = coords[:, 0]
    sorted_idx = np.argsort(lats)
    labels = np.zeros(len(coords), dtype=int)
    chunk_size = max(1, len(coords) // k)
    for i, idx in enumerate(sorted_idx):
        labels[idx] = min(i // chunk_size, k - 1)
    return labels


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
