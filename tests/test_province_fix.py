"""
Test: Province normalization & fuzzy matching (Phase A fix).
Verifies that province names with/without diacritics are handled correctly.
"""
import sys
sys.path.insert(0, '.')

from services.ai_service.models import TripInput, HeritageSite, TripRequest
from services.ai_service.step1_normalizer import (
    parse_trip_request, _normalize_province, PROVINCE_KEYWORDS
)
from services.ai_service.step2_candidates import (
    _normalize_text, generate_candidates, _satisfies_constraints
)

PASS = FAIL = 0

def check(desc, actual, expected, tol=1e-3):
    global PASS, FAIL
    if isinstance(expected, float):
        ok = abs(actual - expected) < tol
    elif isinstance(expected, list):
        ok = list(actual) == list(expected)
    else:
        ok = actual == expected
    if ok:
        PASS += 1; print(f"  [PASS] {desc}")
    else:
        FAIL += 1; print(f"  [FAIL] {desc} => expected {expected!r}, got {actual!r}")


# =========================================================================
# GROUP 1: _normalize_text (fuzzy province matching)
# =========================================================================
print("\n--- GROUP 1: _normalize_text ---")
check("Hà Nội -> ha noi",    _normalize_text("Hà Nội"), "ha noi")
check("TP. Hồ Chí Minh",     _normalize_text("TP. Hồ Chí Minh"), "tp. ho chi minh")
check("Thừa Thiên Huế",      _normalize_text("Thừa Thiên Huế"), "thua thien hue")
check("Bà Rịa - Vũng Tàu",   _normalize_text("Bà Rịa - Vũng Tàu"), "ba ria - vung tau")
check("Đà Nẵng -> da nang",       _normalize_text("Đà Nẵng"), "da nang")
check("Quảng Nam -> quang nam", _normalize_text("Quảng Nam"), "quang nam")
check("Mixed case: Hà NỘI",  _normalize_text("Hà NỘI"), "ha noi")
check("Extra spaces:  Hà  Nội ", _normalize_text("  Hà  Nội "), "ha noi")


# =========================================================================
# GROUP 2: _normalize_province
# =========================================================================
print("\n--- GROUP 2: _normalize_province ---")
check("ha noi -> Hà Nội",        _normalize_province("ha noi"), "Hà Nội")
check("Ha Noi -> Hà Nội",        _normalize_province("Ha Noi"), "Hà Nội")
check("hanoi -> Hà Nội",         _normalize_province("hanoi"), "Hà Nội")
check("Hà Nội -> Hà Nội",       _normalize_province("Hà Nội"), "Hà Nội")
check("ho chi minh -> TP. Hồ Chí Minh", _normalize_province("ho chi minh"), "TP. Hồ Chí Minh")
check("hcm -> TP. Hồ Chí Minh",   _normalize_province("hcm"), "TP. Hồ Chí Minh")
check("da nang -> Đà Nẵng",       _normalize_province("da nang"), "Đà Nẵng")
check("Da Nang -> Đà Nẵng",       _normalize_province("Da Nang"), "Đà Nẵng")
check("hue -> Thừa Thiên Huế",    _normalize_province("hue"), "Thừa Thiên Huế")
check("sai gon -> TP. Hồ Chí Minh", _normalize_province("sai gon"), "TP. Hồ Chí Minh")
check("unknown province unchanged", _normalize_province("Somewhere"), "Somewhere")


# =========================================================================
# GROUP 3: parse_trip_request normalization
# =========================================================================
print("\n--- GROUP 3: parse_trip_request (structured input) ---")

test_cases = [
    (["Ha Noi"], ["Hà Nội"]),
    (["ha noi"], ["Hà Nội"]),
    (["hanoi"], ["Hà Nội"]),
    (["Hà Nội"], ["Hà Nội"]),
    (["ho chi minh"], ["TP. Hồ Chí Minh"]),
    (["Da Nang"], ["Đà Nẵng"]),
    (["sai gon"], ["TP. Hồ Chí Minh"]),
    (["Ha Noi", "da nang"], ["Hà Nội", "Đà Nẵng"]),
    (["Hà Nội", "Thừa Thiên Huế"], ["Hà Nội", "Thừa Thiên Huế"]),
    (["Bà Rịa - Vũng Tàu"], ["Bà Rịa - Vũng Tàu"]),
]

for inp, expected in test_cases:
    t = TripInput(destination_provinces=inp, duration_days=1)
    r = parse_trip_request(t)
    check(f"{inp} -> {expected}", r.destination_provinces, expected)


# =========================================================================
# GROUP 4: parse_trip_request with raw_text
# =========================================================================
print("\n--- GROUP 4: parse_trip_request (raw_text path) ---")

t = TripInput(raw_text="đi Hà Nội 3 ngày", destination_provinces=["ha noi"], duration_days=1)
r = parse_trip_request(t)
check("raw_text path: [ha noi] -> Hà Nội", r.destination_provinces, ["Hà Nội"])

t2 = TripInput(raw_text="du lịch Ninh Bình", destination_provinces=["Ninh Binh"], duration_days=2)
r2 = parse_trip_request(t2)
check("raw_text path: [Ninh Binh] -> Ninh Bình", r2.destination_provinces, ["Ninh Bình"])


# =========================================================================
# GROUP 5: generate_candidates with fuzzy province
# =========================================================================
print("\n--- GROUP 5: generate_candidates (fuzzy province filter) ---")

sites = [
    HeritageSite(id="hn1", name="Văn Miếu", province="Hà Nội", lat=21.0, lng=105.8, categories=["history"]),
    HeritageSite(id="hn2", name="Hoàng Thành", province="Hà Nội", lat=21.03, lng=105.84, categories=["history"]),
    HeritageSite(id="hue1", name="Đại Nội", province="Thừa Thiên Huế", lat=16.46, lng=107.59, categories=["history"]),
    HeritageSite(id="dn1", name="Bà Nà", province="Đà Nẵng", lat=16.05, lng=108.25, categories=["nature"]),
    HeritageSite(id="vt1", name="Bạch Dinh", province="Bà Rịa - Vũng Tàu", lat=10.35, lng=107.07, categories=["history"]),
]

# Test 1: Exact province match
trip = TripRequest(destination_area="Hà Nội", destination_provinces=["Hà Nội"])
r = generate_candidates(trip, sites)
check("Exact: Hà Nội -> 2 sites", len(r), 2)

# Test 2: No diacritics (the bug we fixed)
trip2 = TripRequest(destination_area="Hà Nội", destination_provinces=["Ha Noi"])
r2 = generate_candidates(trip2, sites)
check("No diacritics: Ha Noi -> 2 sites (was 0 before fix)", len(r2), 2)

# Test 3: Lowercase
trip3 = TripRequest(destination_area="Hà Nội", destination_provinces=["ha noi"])
r3 = generate_candidates(trip3, sites)
check("Lowercase: ha noi -> 2 sites", len(r3), 2)

# Test 4: Mixed case
trip4 = TripRequest(destination_area="", destination_provinces=["Da Nang"])
r4 = generate_candidates(trip4, sites)
check("Mixed: Da Nang -> 1 site", len(r4), 1)

# Test 5: Multi-diacritic province
trip5 = TripRequest(destination_area="", destination_provinces=["Bà Rịa - Vũng Tàu"])
r5 = generate_candidates(trip5, sites)
check("Exact: Bà Rịa - Vũng Tàu -> 1 site", len(r5), 1)

# Test 6: Multi-diacritic no diacritics
trip6 = TripRequest(destination_area="", destination_provinces=["Ba Ria - Vung Tau"])
r6 = generate_candidates(trip6, sites)
check("No diacritics: Ba Ria - Vung Tau -> 1 site", len(r6), 1)

# Test 7: Unknown province returns 0
trip7 = TripRequest(destination_area="", destination_provinces=["Mars"])
r7 = generate_candidates(trip7, sites)
check("Unknown province -> 0 sites", len(r7), 0)

# Test 8: Must-visit always included regardless of province
trip8 = TripRequest(destination_area="", destination_provinces=["Hà Nội"], must_visit_site_ids=["hue1"])
r8 = generate_candidates(trip8, sites)
check("Must-visit bypasses province filter", len(r8), 3)  # hue1 + 2 HN sites
check("Must-visit is first", r8[0].id, "hue1")


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
