"""Tests for HeritageSite model validators."""
import math
import sys
import pytest

sys.path.insert(0, ".")

from services.ai_service.models import HeritageSite


# === coord validation ===

def test_valid_lat_rejects_out_of_range():
    with pytest.raises(ValueError, match="lat must be between"):
        HeritageSite(id="t", name="T", province="HN", lat=91.0, lng=105.0)
    with pytest.raises(ValueError, match="lat must be between"):
        HeritageSite(id="t", name="T", province="HN", lat=-91.0, lng=105.0)

def test_valid_lat_accepts_edge():
    s = HeritageSite(id="t", name="T", province="HN", lat=90.0, lng=105.0)
    assert s.lat == 90.0
    s = HeritageSite(id="t", name="T", province="HN", lat=-90.0, lng=105.0)
    assert s.lat == -90.0

def test_valid_lng_rejects_out_of_range():
    with pytest.raises(ValueError, match="lng must be between"):
        HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=181.0)
    with pytest.raises(ValueError, match="lng must be between"):
        HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=-181.0)

def test_valid_lng_accepts_edge():
    s = HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=180.0)
    assert s.lng == 180.0
    s = HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=-180.0)
    assert s.lng == -180.0


# === visit minutes ===

def test_valid_visit_minutes_rejects_negative():
    with pytest.raises(ValueError, match="estimated_visit_minutes must be"):
        HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=105.0,
                     estimated_visit_minutes=-1)


# === score range ===

def test_valid_popularity_score_range():
    with pytest.raises(ValueError, match="score must be in"):
        HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=105.0,
                     popularity_score=1.5)
    with pytest.raises(ValueError, match="score must be in"):
        HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=105.0,
                     popularity_score=-0.1)

def test_valid_historical_score_range():
    with pytest.raises(ValueError, match="score must be in"):
        HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=105.0,
                     historical_importance_score=2.0)

def test_valid_indoor_outdoor_range():
    with pytest.raises(ValueError, match="score must be in"):
        HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=105.0,
                     indoor_score=1.1)
    with pytest.raises(ValueError, match="score must be in"):
        HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=105.0,
                     outdoor_score=-0.1)

def test_score_range_accepts_edge():
    s = HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=105.0,
                     popularity_score=0.0, historical_importance_score=1.0,
                     indoor_score=1.0, outdoor_score=0.0)
    assert s.popularity_score == 0.0
    assert s.historical_importance_score == 1.0


# === ticket price ===

def test_valid_ticket_price_non_negative():
    with pytest.raises(ValueError, match="ticket_price must be"):
        HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=105.0,
                     ticket_price=-50000)


# === non-empty strings ===

def test_valid_id_non_empty():
    with pytest.raises(ValueError, match="id must not be empty"):
        HeritageSite(id="", name="T", province="HN", lat=21.0, lng=105.0)

def test_valid_name_non_empty():
    with pytest.raises(ValueError, match="name must not be empty"):
        HeritageSite(id="t", name="", province="HN", lat=21.0, lng=105.0)

def test_valid_province_non_empty():
    with pytest.raises(ValueError, match="province must not be empty"):
        HeritageSite(id="t", name="T", province="", lat=21.0, lng=105.0)


# === NaN handling ===

def test_nan_lat_rejected():
    with pytest.raises(ValueError):
        HeritageSite(id="t", name="T", province="HN", lat=float("nan"), lng=105.0)

def test_nan_lng_rejected():
    with pytest.raises(ValueError):
        HeritageSite(id="t", name="T", province="HN", lat=21.0, lng=float("nan"))

def test_inf_lat_rejected():
    with pytest.raises(ValueError):
        HeritageSite(id="t", name="T", province="HN", lat=float("inf"), lng=105.0)
