"""
Data Loader — Loads heritage sites from DeepSeek-curated data.
"""
from typing import List, Tuple
from services.ai_service.models import HeritageSite


def load_all_data() -> Tuple[List[HeritageSite], List]:
    from services.ai_service.curated_data import CURATED_HERITAGE
    return list(CURATED_HERITAGE), []
