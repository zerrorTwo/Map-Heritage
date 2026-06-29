"""
Description & Review Enricher — fetches Wikipedia extracts + generates reviews.
"""
import json, urllib.request, urllib.parse, time, re, threading
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed


def _rest_summary(host: str, title: str, timeout: int = 8) -> dict | None:
    encoded = urllib.parse.quote(title.replace(" ", "_"))
    url = f"https://{host}/api/rest_v1/page/summary/{encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": "HeritagePlanner/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def enrich_site(name: str, province: str = "", ref_url: str = "") -> dict:
    """Get rich description data for a heritage site."""
    result = {
        "description": "",
        "long_description": "",
        "visit_tips": "",
        "reference_url": ref_url or "",
        "wikipedia_extract": "",
    }

    # 1. Try vi.wikipedia from reference URL
    if ref_url and "vi.wikipedia.org" in ref_url:
        m = re.search(r'wikipedia\.org/wiki/(.+?)(?:[?#]|$)', ref_url)
        if m:
            title = urllib.parse.unquote(m.group(1)).replace("_", " ")
            data = _rest_summary("vi.wikipedia.org", title)
            if data and data.get("extract"):
                extract = data["extract"]
                result["wikipedia_extract"] = extract
                result["long_description"] = extract
                result["description"] = data.get("description", "") or extract[:200]

    # 2. Try en.wikipedia
    if not result["long_description"]:
        data = _rest_summary("en.wikipedia.org", f"{name} {province} Vietnam")
        if not data or not data.get("extract"):
            data = _rest_summary("en.wikipedia.org", name)
        if data and data.get("extract"):
            extract = data["extract"]
            if len(extract) > len(result.get("wikipedia_extract", "")):
                result["long_description"] = extract
                result["description"] = data.get("description", "") or extract[:200]

    # 3. Try just name on vi.wikipedia
    if not result["long_description"]:
        data = _rest_summary("vi.wikipedia.org", name)
        if data and data.get("extract"):
            extract = data["extract"]
            result["long_description"] = extract
            result["description"] = data.get("description", "") or extract[:200]

    # Fallback: generate from name + province
    if not result["description"]:
        result["description"] = f"{name} — điểm du lịch nổi tiếng tại {province}, Việt Nam."
    if not result["long_description"]:
        result["long_description"] = result["description"]

    return result


def generate_reviews(name: str, province: str, popularity: float = 0.5) -> List[Dict]:
    """Generate synthetic review summaries based on popularity score."""
    reviews = []
    
    # Review templates based on score
    if popularity >= 0.7:
        reviews.append({
            "author": "Travel Vietnam",
            "rating": 5,
            "text": f"Điểm đến tuyệt vời! {name} là một trong những địa danh không thể bỏ qua khi đến {province}. Phong cảnh đẹp, không khí trong lành, rất đáng để trải nghiệm.",
            "source": "travelvietnam.com"
        })
        reviews.append({
            "author": "Lonely Planet Vietnam",
            "rating": 4,
            "text": f"Một điểm dừng chân ấn tượng. {name} mang đậm bản sắc văn hóa và lịch sử của {province}. Khuyên bạn nên dành ít nhất 2-3 tiếng để khám phá.",
            "source": "lonelyplanet.com"
        })
    elif popularity >= 0.4:
        reviews.append({
            "author": "Travel Vietnam",
            "rating": 4,
            "text": f"{name} là điểm đến thú vị tại {province}. Nếu có dịp ghé qua, bạn nên dành thời gian ghé thăm. Giá vé hợp lý, phù hợp cho cả gia đình.",
            "source": "travelvietnam.com"
        })
        reviews.append({
            "author": "Local Guide",
            "rating": 4,
            "text": f"Địa điểm này có nét đẹp riêng. Người dân địa phương thân thiện, đồ ăn xung quanh ngon. Rất thích hợp cho chuyến đi cuối tuần.",
            "source": "local"
        })
    else:
        reviews.append({
            "author": "Local Guide",
            "rating": 3,
            "text": f"{name} là điểm đến khá thú vị ở {province}. Phù hợp cho những ai muốn khám phá văn hóa địa phương. Cần cải thiện thêm về cơ sở vật chất.",
            "source": "local"
        })

    return reviews
