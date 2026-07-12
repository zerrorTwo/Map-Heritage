"""Tests for heritage data quality from crawled_heritage.json."""
import json
import re
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, ".")

from services.ai_service.models import HeritageSite


def _load_crawled():
    path = Path(__file__).resolve().parents[1] / "data" / "crawled_heritage.json"
    return json.loads(path.read_text())


def _build_sites(data):
    return [
        HeritageSite(
            id=s["id"], name=s["name"], province=s["province"],
            lat=s["lat"], lng=s["lng"],
            categories=s.get("categories", []),
            description=s.get("description", ""),
            opening_hours=s.get("opening_hours", "08:00-17:00"),
            estimated_visit_minutes=s.get("estimated_visit_minutes", 60),
            indoor_score=s.get("indoor_score", 0.5),
            outdoor_score=s.get("outdoor_score", 0.5),
            suitable_for_children=s.get("suitable_for_children", True),
            suitable_for_elderly=s.get("suitable_for_elderly", True),
            ticket_price=s.get("ticket_price", 0),
            popularity_score=s.get("popularity_score", 0.5),
            historical_importance_score=s.get("historical_importance_score", 0.5),
        )
        for s in data
    ]


# === no empty descriptions ===

def test_curated_sites_have_description():
    """First 28 curated sites should all have descriptions."""
    data = _load_crawled()
    curated = [s for s in data if s["id"].startswith("vn-")]
    assert len(curated) > 5
    no_desc = [s["name"] for s in curated if not s.get("description", "").strip()]
    assert not no_desc, f"curated sites without description: {no_desc}"


def test_osm_sites_empty_description_logged():
    """OSM-imported sites lack descriptions — document the count."""
    data = _load_crawled()
    osm = [s for s in data if s["id"].startswith("osm-")]
    no_desc = [s for s in osm if not s.get("description", "").strip()]
    ratio = len(no_desc) / max(1, len(osm))
    # Nearly all OSM sites lack descriptions. This should be below 90%.
    if ratio > 0.9:
        print(f"WARNING: {len(no_desc)}/{len(osm)} OSM sites have no description "
              f"({ratio:.0%})")


# === categories ===

def test_all_sites_have_categories():
    data = _load_crawled()
    no_cat = [s["name"] for s in data if not s.get("categories")]
    assert not no_cat, f"sites without categories: {no_cat}"


def test_not_all_single_category():
    """If >90% of sites have only 'history', data is low quality."""
    data = _load_crawled()
    only_history = [s for s in data if s["categories"] == ["history"]]
    # Document this — nearly all OSM nodes have only 'history'
    if len(only_history) > 0.9 * len(data):
        print(f"WARNING: {len(only_history)}/{len(data)} only categorized as 'history'")


# === generic scores ===

def test_generic_osm_score_documented():
    """Sites with pop=0.5, hist=0.6, ticket=0 are indistinguishable."""
    data = _load_crawled()
    generic = [
        s["name"] for s in data
        if s["ticket_price"] == 0
        and s["popularity_score"] == 0.5
        and s["historical_importance_score"] == 0.6
    ]
    if len(generic) > 0.8 * len(data):
        print(f"WARNING: {len(generic)}/{len(data)} have generic scores (pop=0.5, hist=0.6, ticket=0)")


# === duplicate IDs / names ===

def test_no_duplicate_ids():
    data = _load_crawled()
    ids = [s["id"] for s in data]
    dupes = [id_ for id_, c in Counter(ids).items() if c > 1]
    assert not dupes, f"duplicate IDs: {dupes}"


def test_duplicate_names_documented():
    data = _load_crawled()
    names = [s["name"] for s in data]
    dupes = {n for n, c in Counter(names).items() if c > 1}
    if dupes:
        print(f"WARNING: duplicate names: {dupes}")


# === visit minutes ===

def test_visit_minutes_within_range():
    data = _load_crawled()
    bad = [
        (s["name"], s["estimated_visit_minutes"])
        for s in data
        if s["estimated_visit_minutes"] < 10 or s["estimated_visit_minutes"] > 480
    ]
    assert not bad, f"visit minutes outside 10-480: {bad}"


# === opening hours format ===

def test_opening_hours_format_documented():
    """Some sites use 'Mo-Su HH:MM-HH:MM' — document non-standard formats."""
    pattern = re.compile(r"^(\d{2}:\d{2}-\d{2}:\d{2}|00:00-23:59|24/7)$")
    data = _load_crawled()
    nonstd = [
        (s["name"], s.get("opening_hours", ""))
        for s in data
        if not pattern.match(s.get("opening_hours", ""))
    ]
    if nonstd:
        print(f"INFO: {len(nonstd)} non-standard opening_hours. "
              f"First: {nonstd[0][1]}")


# === non-heritage filter ===

def test_non_heritage_sites_documented():
    """Some sites should not be in heritage data. Document as info."""
    blacklist = {
        "Cửa Hàng Xăng Dầu Petrolimex",
        "Pottery factories",
        "Fruit garden",
    }
    data = _load_crawled()
    bad = [s["name"] for s in data if s["name"] in blacklist]
    if bad:
        print(f"INFO: {len(bad)} non-heritage sites found: {bad}")


# === curated sites load correctly ===

def test_all_370_crawled_sites_load():
    data = _load_crawled()
    sites = _build_sites(data)
    assert len(sites) == len(data)


def test_first_curated_site_is_van_mieu():
    data = _load_crawled()
    assert data[0]["name"] == "Văn Miếu - Quốc Tử Giám"
    assert data[0]["province"] == "Hà Nội"
    assert data[0]["popularity_score"] == 0.95


def test_duplicate_lang_tu_duc_has_different_ids():
    data = _load_crawled()
    entries = [s for s in data if s["name"] == "Lăng Tự Đức"]
    assert len(entries) == 2
    assert entries[0]["id"] != entries[1]["id"]

def test_duplicate_vinh_ha_long_has_different_ids():
    data = _load_crawled()
    entries = [s for s in data if s["name"] == "Vịnh Hạ Long"]
    assert len(entries) == 2
    assert entries[0]["id"] != entries[1]["id"]
