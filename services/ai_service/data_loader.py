"""
Data Loader — Uses DeepSeek-curated data for all 63 provinces.
"""

from typing import List, Tuple
from services.ai_service.models import HeritageSite, Restaurant


JUNK_PATTERNS = [
    'chính sách', 'điều khoản', 'copyright', 'all rights',
    'liên hệ', 'tuyển dụng', 'bảo mật', 'hợp tác b2b',
    'năng lực b2b', 'quy định thanh toán', 'q n s o f t',
    'về chúng tôi', 'giới thiệu',
]


def load_all_data() -> Tuple[List[HeritageSite], List[Restaurant]]:
    """Load heritage sites and restaurants from curated data, filtering junk."""
    from services.ai_service.curated_data import CURATED_HERITAGE, CURATED_RESTAURANTS
    sites = []
    for s in CURATED_HERITAGE:
        name_lower = s.name.lower()
        if not any(kw in name_lower for kw in JUNK_PATTERNS):
            sites.append(s)
    return sites, list(CURATED_RESTAURANTS)
