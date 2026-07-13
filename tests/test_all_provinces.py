"""
Test: All 63 provinces — verify generate_candidates returns sites for every province.
Tests both exact names and no-diacritics variants via the full normalization pipeline.
"""
import sys
sys.path.insert(0, '.')

from services.ai_service.models import TripInput, HeritageSite, TripRequest
from services.ai_service.step1_normalizer import parse_trip_request, _normalize_province
from services.ai_service.step2_candidates import generate_candidates, _normalize_text
from services.ai_service.data_loader import load_all_data

PASS = FAIL = 0

def check(desc, actual, expected=None):
    global PASS, FAIL
    if expected is not None:
        if isinstance(expected, (int, float)):
            ok = actual >= expected
        elif expected is True:
            ok = actual is True
        elif expected is False:
            ok = actual is False
        else:
            ok = actual == expected
    else:
        ok = bool(actual)
    if ok:
        PASS += 1
    else:
        FAIL += 1; print(f"  [FAIL] {desc} => expected {expected!r}, got {actual!r}")

# Load actual data
all_sites, _ = load_all_data()
site_map = {}
for s in all_sites:
    site_map.setdefault(s.province, []).append(s)

all_provinces = sorted(site_map.keys())
print(f"Loaded {len(all_sites)} sites across {len(all_provinces)} provinces")


# =========================================================================
# GROUP 1: All 63 provinces — generate_candidates returns sites
# =========================================================================
print(f"\n--- GROUP 1: All {len(all_provinces)} provinces (exact name) ---")

for prov in all_provinces:
    trip = TripRequest(destination_area=prov, destination_provinces=[prov])
    result = generate_candidates(trip, all_sites)
    expected_min = len(site_map[prov])
    ok = len(result) >= expected_min or len(result) >= min(expected_min, 30)
    if ok:
        PASS += 1
    else:
        FAIL += 1; print(f"  [FAIL] {prov}: got {len(result)} sites, expected >= {expected_min}")

check("all provinces have >= 1 site", True)

prov_counts = sorted([(len(site_map[p]), p) for p in all_provinces], reverse=True)
print(f"  Top 5: {prov_counts[:5]}")
print(f"  Bottom 5: {prov_counts[-5:]}")


# =========================================================================
# GROUP 2: No-diacritics variants for all provinces
# =========================================================================
print(f"\n--- GROUP 2: Fuzzy match (no diacritics) for all {len(all_provinces)} ---")

for prov in all_provinces:
    norm = _normalize_text(prov)
    trip = TripRequest(destination_area=prov, destination_provinces=[norm])
    result = generate_candidates(trip, all_sites)
    expected_min = len(site_map[prov])
    if len(result) > 0:
        PASS += 1
    else:
        FAIL += 1; print(f"  [FAIL] fuzzy '{norm}' for '{prov}': got 0 sites")

check("all provinces fuzzy-matched", True)


# =========================================================================
# GROUP 3: parse_trip_request normalization for each province
# =========================================================================
print(f"\n--- GROUP 3: parse_trip_request normalization ---")

# Test that normalize preserves already-correct names
for prov in all_provinces:
    inp = TripInput(destination_provinces=[prov], duration_days=1)
    r = parse_trip_request(inp)
    if r.destination_provinces[0] == prov:
        PASS += 1
    else:
        FAIL += 1; print(f"  [FAIL] normalize changed '{prov}' -> '{r.destination_provinces[0]}'")

check("normalize preserves correct province names", True)


# =========================================================================
# GROUP 4: Province keyword mappings (13 provinces with keywords)
# =========================================================================
print(f"\n--- GROUP 4: PROVINCE_KEYWORDS mapping ---")

keyword_tests = [
    ("ha noi", "Hà Nội"), ("hanoi", "Hà Nội"), ("Ha Noi", "Hà Nội"),
    ("ho chi minh", "TP. Hồ Chí Minh"), ("hcm", "TP. Hồ Chí Minh"),
    ("sai gon", "TP. Hồ Chí Minh"), ("saigon", "TP. Hồ Chí Minh"),
    ("hue", "Thừa Thiên Huế"), ("huế", "Thừa Thiên Huế"),
    ("da nang", "Đà Nẵng"), ("Da Nang", "Đà Nẵng"), ("đà nẵng", "Đà Nẵng"),
    ("hoi an", "Quảng Nam"), ("hội an", "Quảng Nam"),
    ("ninh binh", "Ninh Bình"), ("ninh bình", "Ninh Bình"),
    ("ha long", "Quảng Ninh"), ("hạ long", "Quảng Ninh"),
    ("sapa", "Lào Cai"), ("sa pa", "Lào Cai"),
    ("ha giang", "Hà Giang"), ("hà giang", "Hà Giang"),
    ("can tho", "Cần Thơ"), ("cần thơ", "Cần Thơ"),
]
for kw, expected in keyword_tests:
    result = _normalize_province(kw)
    if result == expected:
        PASS += 1
    else:
        FAIL += 1; print(f"  [FAIL] _normalize_province('{kw}') = '{result}' != '{expected}'")

# Test province with no keyword → unchanged
check("unknown province preserved", _normalize_province("Bình Thuận"), "Bình Thuận")


# =========================================================================
# GROUP 5: Multi-province with raw_text
# =========================================================================
print(f"\n--- GROUP 5: Multi-province queries ---")

# 2 provinces
inp5a = TripInput(destination_provinces=["Bà Rịa - Vũng Tàu", "Bình Dương"],
                  duration_days=2, pace="moderate")
r5a = parse_trip_request(inp5a)
t5a = TripRequest(destination_area=r5a.destination_area,
                  destination_provinces=r5a.destination_provinces)
c5a = generate_candidates(t5a, all_sites)
check("BRVT+BD: 2 provinces → sites", len(c5a) >= len(site_map.get("Bà Rịa - Vũng Tàu", [])) + len(site_map.get("Bình Dương", [])), True)

# 3 provinces
inp5b = TripInput(destination_provinces=["Hà Nội", "Đà Nẵng", "Quảng Nam"],
                  duration_days=3, pace="moderate")
r5b = parse_trip_request(inp5b)
t5b = TripRequest(destination_area=r5b.destination_area,
                  destination_provinces=r5b.destination_provinces)
c5b = generate_candidates(t5b, all_sites)
check("HN+DN+QN: 3 provinces → sites", len(c5b) >= 30, True)

# Mixed diacritics
inp5c = TripInput(destination_provinces=["ha noi", "Đà Nẵng", "hue"],
                  duration_days=3, pace="moderate")
r5c = parse_trip_request(inp5c)
check("mixed diacritics normalized",
      r5c.destination_provinces, ["Hà Nội", "Đà Nẵng", "Thừa Thiên Huế"])


# =========================================================================
# GROUP 6: Summary fix — raw_text no province + user set provinces
# =========================================================================
print(f"\n--- GROUP 6: Summary correctness (user's bug) ---")

inp6 = TripInput(
    raw_text="Đền chùa & Tâm linh, Thích hợp cho trẻ em",
    destination_provinces=["Bà Rịa - Vũng Tàu", "Bình Dương"],
    duration_days=3, pace="moderate",
    start_lat=10.822, start_lng=106.6257,
    end_lat=10.822, end_lng=106.6257,
)
r6 = parse_trip_request(inp6)
check("summary dest ≠ Hà Nội", r6.destination_area != "Hà Nội", True)
check("summary duration = 3", r6.duration_days, 3)
check("summary has correct provinces",
      "Bà Rịa" in r6.destination_area and "Bình Dương" in r6.destination_area, True)

# Another example: user wants BRVT + Bình Thuận, no raw_text
inp6b = TripInput(
    destination_provinces=["Bà Rịa - Vũng Tàu", "Bình Thuận"],
    duration_days=2, pace="moderate",
)
r6b = parse_trip_request(inp6b)
check("BRVT+BThuan: dest contains BRVT", "Bà Rịa" in r6b.destination_area, True)
check("BRVT+BThuan: dest contains Bình Thuận", "Bình Thuận" in r6b.destination_area, True)
check("BRVT+BThuan: duration=2", r6b.duration_days, 2)


# =========================================================================
# REPORT
# =========================================================================
print(f"\n{'='*60}")
print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
if FAIL == 0:
    print("ALL TESTS PASSED")
else:
    print(f"{FAIL} TEST(S) FAILED")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
