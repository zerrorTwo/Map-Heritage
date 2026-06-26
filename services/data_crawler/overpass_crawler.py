"""
OSM Overpass API Crawler for Vietnam Heritage Sites & Restaurants

Data sources:
  - OpenStreetMap Overpass API (free, no API key)
  - Tags: historic=*, tourism=*, amenity=restaurant, amenity=cafe
  - Geographic scope: Vietnam bounding box

Usage:
  python3 -m services.data_crawler.overpass_crawler
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Dict, Any

VIETNAM_BBOX = {
    "south": 8.18, "west": 102.14,
    "north": 23.39, "east": 109.46
}

OVERPASS_URL = "http://overpass-api.de/api/interpreter"

PROVINCE_CENTERS = {
    (21.0285, 105.8542): "Hà Nội",
    (10.8231, 106.6297): "TP. Hồ Chí Minh",
    (16.0544, 108.2022): "Đà Nẵng",
    (16.4637, 107.5909): "Thừa Thiên Huế",
    (15.8801, 108.3380): "Quảng Nam",
    (21.0069, 107.2926): "Quảng Ninh",
    (20.2506, 105.9745): "Ninh Bình",
    (10.3800, 105.4230): "An Giang",
    (10.0328, 105.7705): "Cần Thơ",
    (22.3356, 103.8436): "Lào Cai",
    (23.2785, 105.3590): "Hà Giang",
    (20.8550, 106.6830): "Hải Phòng",
    (18.6796, 105.6813): "Nghệ An",
    (11.9404, 108.4580): "Lâm Đồng",
    (12.2388, 109.1967): "Khánh Hòa",
    (13.7696, 109.2317): "Bình Định",
    (10.9574, 106.8426): "Đồng Nai",
    (21.5910, 105.8500): "Thái Nguyên",
}

HERITAGE_TAGS = [
    "historic=*",
    "tourism=attraction",
    "tourism=museum",
    "tourism=gallery",
    "historic=monument",
    "historic=memorial",
    "historic=archaeological_site",
    "historic=temple",
    "historic=tomb",
    "historic=ruins",
    "historic=castle",
    "historic=city_gate",
]

RESTAURANT_TAGS = [
    "amenity=restaurant",
    "amenity=cafe",
    "amenity=fast_food",
]


def _overpass_query(query: str, timeout: int = 120) -> dict:
    """Send query to Overpass API and return JSON."""
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "heritage-crawler/1.0",
            "Accept": "application/json",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, json.JSONDecodeError) as e:
            if attempt == 2:
                raise
            time.sleep(3)
    return {"elements": []}


def build_overpass_query(tags: List[str], bbox: Dict[str, float], limit: int = 500) -> str:
    """Build an Overpass QL query for nodes and ways with given tags."""
    bbox_str = f"{bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']}"
    tag_queries = []
    for tag in tags:
        tag_queries.append(f'  node["{tag.replace("=", '"="')}"]({bbox_str});')
        tag_queries.append(f'  way["{tag.replace("=", '"="')}"]({bbox_str});')
        tag_queries.append(f'  relation["{tag.replace("=", '"="')}"]({bbox_str});')

    return f"""
[out:json][timeout:120][maxsize:1073741824];
(
{chr(10).join(tag_queries)}
);
out center {limit};
"""


def match_province(lat: float, lng: float) -> str:
    """Simple nearest-province-by-distance matching."""
    min_dist = float("inf")
    best = "Unknown"
    for (pc_lat, pc_lng), name in PROVINCE_CENTERS.items():
        d = (lat - pc_lat) ** 2 + (lng - pc_lng) ** 2
        if d < min_dist:
            min_dist = d
            best = name
    return best


def map_osm_tags_to_categories(tags: Dict[str, str]) -> List[str]:
    """Map OSM tags to our category system."""
    categories = set()
    cat_map = {
        "museum": "museum",
        "gallery": "museum",
        "temple": "spiritual",
        "place_of_worship": "spiritual",
        "monastery": "spiritual",
        "church": "spiritual",
        "cathedral": "spiritual",
        "pagoda": "spiritual",
        "castle": "architecture",
        "ruins": "history",
        "monument": "history",
        "memorial": "history",
        "archaeological_site": "history",
        "tomb": "history",
        "city_gate": "architecture",
        "attraction": None,
        "viewpoint": None,
    }

    for k, v in tags.items():
        if k in ("historic", "tourism"):
            if v in cat_map:
                cat = cat_map[v]
                if cat:
                    categories.add(cat)
        if k == "historic" and v in ("yes", "building", "manor", "house"):
            categories.add("history")
        if k == "craft" or v == "craft":
            categories.add("craft_village")
        if k == "amenity" and v == "place_of_worship":
            categories.add("spiritual")

    if "heritage" in tags:
        categories.add("unesco")
    if "unesco" in str(tags).lower():
        categories.add("unesco")
    if not categories:
        categories.add("history")

    return list(categories)


def parse_opening_hours(osm_oh: str | None) -> str:
    """Convert OSM opening_hours to simplified HH:MM-HH:MM format."""
    if not osm_oh:
        return "08:00-17:00"
    return osm_oh.strip()[:40]


def parse_element(el: Dict[str, Any]) -> Dict[str, Any] | None:
    """Parse a single OSM element into our HeritageSite or skip."""
    tags = el.get("tags", {})
    name = tags.get("name", tags.get("name:en", tags.get("name:vi", "")))
    if not name:
        name = tags.get("historic", tags.get("tourism", ""))
    if not name or len(name) < 2:
        return None

    lat = el.get("lat") or (el.get("center", {}).get("lat"))
    lng = el.get("lon") or (el.get("center", {}).get("lon"))
    if lat is None or lng is None:
        return None

    categories = map_osm_tags_to_categories(tags)

    return {
        "id": f"osm-{el['type']}-{el['id']}",
        "name": name,
        "province": match_province(float(lat), float(lng)),
        "lat": float(lat),
        "lng": float(lng),
        "categories": categories,
        "description": tags.get("description", tags.get("description:en", "")),
        "opening_hours": parse_opening_hours(tags.get("opening_hours")),
        "estimated_visit_minutes": 60,
        "indoor_score": 0.3 if "museum" in categories else 0.1,
        "outdoor_score": 0.9 if "museum" not in categories else 0.1,
        "suitable_for_children": True,
        "suitable_for_elderly": tags.get("wheelchair") != "no",
        "ticket_price": 0,
        "popularity_score": 0.5,
        "historical_importance_score": 0.6,
    }


def crawl_heritage_sites(limit: int = 500) -> List[Dict[str, Any]]:
    """Crawl heritage sites from OSM Overpass API."""
    query = build_overpass_query(HERITAGE_TAGS, VIETNAM_BBOX, limit)
    print(f"  Sending query ({len(query)} chars)...")
    data = _overpass_query(query, timeout=180)
    elements = data.get("elements", [])
    print(f"  Got {len(elements)} raw elements")

    sites = []
    for el in elements:
        site = parse_element(el)
        if site:
            sites.append(site)
    return sites


def crawl_restaurants(limit: int = 500) -> List[Dict[str, Any]]:
    """Crawl restaurants from OSM Overpass API."""
    query = build_overpass_query(RESTAURANT_TAGS, VIETNAM_BBOX, limit)
    print(f"  Sending query ({len(query)} chars)...")
    data = _overpass_query(query, timeout=180)
    elements = data.get("elements", [])
    print(f"  Got {len(elements)} raw elements")

    restaurants = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en") or tags.get("name:vi") or ""
        if not name or len(name) < 2:
            continue
        lat = el.get("lat") or (el.get("center", {}).get("lat"))
        lng = el.get("lon") or (el.get("center", {}).get("lon"))
        if lat is None or lng is None:
            continue

        cuisine = tags.get("cuisine", tags.get("food", ""))
        specialty = [cuisine] if cuisine else ["local_food"]

        restaurants.append({
            "id": f"osm-r-{el['type']}-{el['id']}",
            "name": name,
            "lat": float(lat),
            "lng": float(lng),
            "province": match_province(float(lat), float(lng)),
            "specialty_tags": specialty,
            "rating": 4.0,
            "review_count": 10,
            "price_level": 2,
            "opening_hours": parse_opening_hours(tags.get("opening_hours")),
            "source": "osm",
            "distance_to_nearest_heritage_m": 0,
        })
    return restaurants
