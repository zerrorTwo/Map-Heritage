"""Tests for heritage site coordinate positions and edge cases."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from services.ai_service.models import HeritageSite, ScoredSite


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


# === Vietnam basemap bounds ===

def test_all_crawled_sites_within_vietnam_basemap():
    """lat ∈ [8, 24], lng ∈ [102, 110] — rough Vietnam bounding box."""
    data = _load_crawled()
    sites = _build_sites(data)
    out_of_bounds = [
        (s.id, s.name, s.province, s.lat, s.lng)
        for s in sites
        if not (8.0 <= s.lat <= 24.0 and 102.0 <= s.lng <= 110.0)
    ]
    assert not out_of_bounds, f"sites outside Vietnam basemap: {out_of_bounds}"


# === extreme VN positions ===

def test_extreme_south_valid():
    s = HeritageSite(id="t", name="Cà Mau", province="Cà Mau", lat=8.56, lng=104.83)
    assert -90 <= s.lat <= 90

def test_extreme_north_valid():
    s = HeritageSite(id="t", name="Hà Giang", province="Hà Giang", lat=23.36, lng=105.36)
    assert -90 <= s.lat <= 90

def test_extreme_east_valid():
    s = HeritageSite(id="t", name="Khánh Hòa", province="Khánh Hòa", lat=12.24, lng=109.46)
    assert -180 <= s.lng <= 180

def test_extreme_west_valid():
    s = HeritageSite(id="t", name="Điện Biên", province="Điện Biên", lat=21.39, lng=102.23)
    assert -180 <= s.lng <= 180

def test_phu_quoc_island_valid():
    s = HeritageSite(id="t", name="Phú Quốc", province="Kiên Giang", lat=10.23, lng=104.02)
    assert -90 <= s.lat <= 90


# === zero / negative coords ===

def test_zero_lat_valid_but_unusual():
    """Lat=0 is on the equator — technically valid but shouldn't exist in VN."""
    s = HeritageSite(id="t", name="Equator", province="VN", lat=0.0, lng=105.0)
    assert s.lat == 0.0

def test_negative_lat_valid_but_not_vietnam():
    """Lat=-10 is valid globally ([-90,90]) but impossible in Vietnam.
    The model can't catch province-level errors — this documents the gap."""
    s = HeritageSite(id="t", name="Bad", province="VN", lat=-10.0, lng=105.0)
    assert s.lat == -10.0


# === foreign coords in VN provinces ===

def test_foreign_lng_laos_range():
    """lng < 102 is likely Laos/Cambodia, not Vietnam."""
    import pytest
    # Known bad data pattern: sites in "Nghệ An" with Laos coordinates
    s = HeritageSite(id="t", name="Plain of Jars", province="Nghệ An",
                     lat=19.29, lng=103.15)
    # Currently accepted because model only validates lat ∈ [-90,90], lng ∈ [-180,180]
    # This test documents the expected behavior — a warning would be better
    assert s.lng == 103.15


# === duplicate coords ===

def test_duplicate_identical_coords_two_sites():
    s1 = HeritageSite(id="a", name="Site A", province="HN", lat=21.0285, lng=105.8542)
    s2 = HeritageSite(id="b", name="Site B", province="HN", lat=21.0285, lng=105.8542)
    assert (s1.lat, s1.lng) == (s2.lat, s2.lng)

def test_duplicate_coords_same_province_warning():
    """Sites with identical coords in the same province should be flagged.
    Currently there's no check — this documents the gap."""
    s1 = HeritageSite(id="x", name="X", province="HN", lat=21.0, lng=105.0)
    s2 = HeritageSite(id="y", name="Y", province="HN", lat=21.0, lng=105.0)
    assert (s1.lat, s1.lng) == (s2.lat, s2.lng)


# === province-coordinate consistency ===

def test_hanoi_sites_within_reasonable_range():
    """Sites labelled 'Hà Nội' should be within ~150km of Hanoi center."""
    center = (21.0285, 105.8542)
    data = _load_crawled()
    sites = _build_sites(data)
    hanoi_sites = [s for s in sites if s.province == "Hà Nội"]
    assert len(hanoi_sites) > 0

    far_sites = []
    for s in hanoi_sites:
        import math
        dlat = abs(s.lat - center[0]) * 111  # km per degree lat
        dlng = abs(s.lng - center[1]) * 111 * math.cos(math.radians(center[0]))
        approx_km = math.sqrt(dlat**2 + dlng**2)
        if approx_km > 200:
            far_sites.append((s.id, s.name, round(approx_km)))
    assert not far_sites, f"Hà Nội sites too far from capital: {far_sites}"
