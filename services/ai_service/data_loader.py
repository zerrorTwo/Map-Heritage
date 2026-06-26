"""
Data Loader — Uses DeepSeek-curated data for all 63 provinces.
"""

from typing import List, Tuple
from services.ai_service.models import HeritageSite, Restaurant


def load_all_data() -> Tuple[List[HeritageSite], List[Restaurant]]:
    """Load heritage sites and restaurants from DeepSeek-curated data."""
    from services.ai_service.curated_data import CURATED_HERITAGE, CURATED_RESTAURANTS
    return list(CURATED_HERITAGE), list(CURATED_RESTAURANTS)
