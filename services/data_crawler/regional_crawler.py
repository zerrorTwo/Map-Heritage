"""
Targeted OSM Overpass Crawler — queries by region for reliability.
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Dict, Any

OVERPASS_URL = "http://overpass-api.de/api/interpreter"

REGIONS = [
    {"name": "Hà Nội", "south": 20.9, "west": 105.6, "north": 21.1, "east": 106.0},
    {"name": "TP. Hồ Chí Minh", "south": 10.6, "west": 106.5, "north": 11.0, "east": 106.9},
    {"name": "Huế & Đà Nẵng", "south": 15.8, "west": 107.5, "north": 16.5, "east": 108.5},
    {"name": "Hội An & Quảng Nam", "south": 15.7, "west": 108.0, "north": 16.0, "east": 108.5},
    {"name": "Hạ Long & Quảng Ninh", "south": 20.7, "west": 106.9, "north": 21.2, "east": 107.5},
    {"name": "Ninh Bình", "south": 20.1, "west": 105.7, "north": 20.4, "east": 106.0},
    {"name": "Sapa & Lào Cai", "south": 22.1, "west": 103.6, "north": 22.6, "east": 104.0},
    {"name": "Hà Giang", "south": 22.8, "west": 104.8, "north": 23.5, "east": 105.5},
    {"name": "Cần Thơ & Mekong", "south": 9.8, "west": 105.2, "north": 10.5, "east": 106.0},
    {"name": "Nha Trang & Khánh Hòa", "south": 12.0, "west": 108.9, "north": 12.5, "east": 109.5},
    {"name": "Đà Lạt & Lâm Đồng", "south": 11.7, "west": 108.1, "north": 12.1, "east": 108.7},
    {"name": "Hải Phòng", "south": 20.6, "west": 106.5, "north": 20.9, "east": 106.9},
    {"name": "Nghệ An & Hà Tĩnh", "south": 18.2, "west": 105.2, "north": 19.2, "east": 106.0},
]

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
}


def _overpass_query(query: str, timeout: int = 120):
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "heritage-crawler/1.0",
        "Accept": "application/json",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(5)
    return {"elements": []}


def match_province(lat: float, lng: float) -> str:
    min_dist = float("inf")
    best = "Unknown"
    for (pc_lat, pc_lng), name in PROVINCE_CENTERS.items():
        d = (lat - pc_lat) ** 2 + (lng - pc_lng) ** 2
        if d < min_dist:
            min_dist = d
            best = name
    return best


def map_categories(tags: Dict[str, str]) -> List[str]:
    cats = set()
    cat_map = {
        "museum": "museum", "gallery": "museum",
        "temple": "spiritual", "place_of_worship": "spiritual",
        "monastery": "spiritual", "church": "spiritual",
        "cathedral": "spiritual", "pagoda": "spiritual",
        "castle": "architecture", "ruins": "history",
        "monument": "history", "memorial": "history",
        "archaeological_site": "history", "tomb": "history",
        "city_gate": "architecture",
    }
    for k, v in tags.items():
        if k in ("historic", "tourism"):
            cat = cat_map.get(v)
            if cat:
                cats.add(cat)
        if k == "historic" and v in ("yes", "building", "manor", "house"):
            cats.add("history")
        if k == "craft":
            cats.add("craft_village")
        if k == "amenity" and v == "place_of_worship":
            cats.add("spiritual")
    if not cats:
        cats.add("history")
    return list(cats)


def crawl_region(region: dict, tag_type: str = "heritage") -> list:
    """Crawl a single region for heritage sites or restaurants."""
    bbox = f"{region['south']},{region['west']},{region['north']},{region['east']}"

    if tag_type == "heritage":
        tags_clause = f"""
  node["tourism"="attraction"]({bbox});
  way["tourism"="attraction"]({bbox});
  node["historic"]({bbox});
  way["historic"]({bbox});
  node["tourism"="museum"]({bbox});
  way["tourism"="museum"]({bbox});
  node["tourism"="gallery"]({bbox});
  way["tourism"="gallery"]({bbox});
"""
    else:
        tags_clause = f"""
  node["amenity"="restaurant"]({bbox});
  way["amenity"="restaurant"]({bbox});
  node["amenity"="cafe"]({bbox});
  way["amenity"="cafe"]({bbox});
"""

    query = f"""[out:json][timeout:60];
({tags_clause});
out center 200;
"""
    try:
        result = _overpass_query(query, timeout=90)
        return result.get("elements", [])
    except Exception as e:
        print(f"    Error: {e}")
        return []


def parse_heritage(el: dict) -> dict | None:
    tags = el.get("tags", {})
    name = tags.get("name") or tags.get("name:en") or tags.get("name:vi") or ""
    if not name or len(name) < 2:
        return None
    lat = el.get("lat") or (el.get("center", {}).get("lat"))
    lng = el.get("lon") or (el.get("center", {}).get("lon"))
    if lat is None or lng is None:
        return None
    cats = map_categories(tags)
    return {
        "id": f"osm-{el['type']}-{el['id']}",
        "name": name,
        "province": match_province(float(lat), float(lng)),
        "lat": float(lat),
        "lng": float(lng),
        "categories": cats,
        "description": tags.get("description", tags.get("description:en", "")),
        "opening_hours": (tags.get("opening_hours") or "08:00-17:00")[:40],
        "estimated_visit_minutes": 60,
        "indoor_score": 0.3 if "museum" in cats else 0.1,
        "outdoor_score": 0.9 if "museum" not in cats else 0.1,
        "suitable_for_children": True,
        "suitable_for_elderly": tags.get("wheelchair") != "no",
        "ticket_price": 0,
        "popularity_score": 0.5,
        "historical_importance_score": 0.6,
    }


def parse_restaurant(el: dict) -> dict | None:
    tags = el.get("tags", {})
    name = tags.get("name") or tags.get("name:en") or tags.get("name:vi") or ""
    if not name or len(name) < 2:
        return None
    lat = el.get("lat") or (el.get("center", {}).get("lat"))
    lng = el.get("lon") or (el.get("center", {}).get("lon"))
    if lat is None or lng is None:
        return None
    cuisine = tags.get("cuisine", "")
    return {
        "id": f"osm-r-{el['type']}-{el['id']}",
        "name": name,
        "lat": float(lat),
        "lng": float(lng),
        "province": match_province(float(lat), float(lng)),
        "specialty_tags": [cuisine] if cuisine else ["local_food"],
        "rating": 4.0,
        "review_count": 10,
        "price_level": 2,
        "opening_hours": (tags.get("opening_hours") or "06:00-22:00")[:40],
        "source": "osm",
        "distance_to_nearest_heritage_m": 0,
    }


def main():
    all_sites = []
    all_restaurants = []
    seen_site_ids = set()
    seen_rest_ids = set()

    for region in REGIONS:
        print(f"Region: {region['name']}")

        # Heritage sites
        elements = crawl_region(region, "heritage")
        for el in elements:
            site = parse_heritage(el)
            if site and site["id"] not in seen_site_ids:
                seen_site_ids.add(site["id"])
                all_sites.append(site)
        print(f"  Heritage: {len(elements)} raw → {sum(1 for s in all_sites if s['province'] == match_province_from_region(region['name']))} in region")

        time.sleep(2)

        # Restaurants
        elements = crawl_region(region, "restaurant")
        for el in elements:
            rest = parse_restaurant(el)
            if rest and rest["id"] not in seen_rest_ids:
                seen_rest_ids.add(rest["id"])
                all_restaurants.append(rest)
        print(f"  Restaurants: {len(elements)} raw")

        time.sleep(3)

    print(f"\nTotal: {len(all_sites)} heritage sites, {len(all_restaurants)} restaurants")

    with open("crawled_heritage.json", "w", encoding="utf-8") as f:
        json.dump(all_sites, f, ensure_ascii=False, indent=2)
    with open("crawled_restaurants.json", "w", encoding="utf-8") as f:
        json.dump(all_restaurants, f, ensure_ascii=False, indent=2)
    print("Saved to crawled_heritage.json + crawled_restaurants.json")


def match_province_from_region(region_name: str) -> str:
    mapping = {
        "Hà Nội": "Hà Nội",
        "TP. Hồ Chí Minh": "TP. Hồ Chí Minh",
        "Huế & Đà Nẵng": "Thừa Thiên Huế",
        "Hội An & Quảng Nam": "Quảng Nam",
        "Hạ Long & Quảng Ninh": "Quảng Ninh",
        "Ninh Bình": "Ninh Bình",
        "Sapa & Lào Cai": "Lào Cai",
        "Hà Giang": "Hà Giang",
        "Cần Thơ & Mekong": "Cần Thơ",
        "Nha Trang & Khánh Hòa": "Khánh Hòa",
        "Đà Lạt & Lâm Đồng": "Lâm Đồng",
        "Hải Phòng": "Hải Phòng",
        "Nghệ An & Hà Tĩnh": "Nghệ An",
    }
    return mapping.get(region_name, "Unknown")


if __name__ == "__main__":
    main()
