"""
Test: All input fields — verifies structured fields are not overridden
by raw_text parser defaults (the bug fix for step1_normalizer.py).
"""
import sys
sys.path.insert(0, '.')

from services.ai_service.models import TripInput, TripRequest
from services.ai_service.step1_normalizer import parse_trip_request

PASS = FAIL = 0

def check(desc, actual, expected=None):
    global PASS, FAIL
    if expected is not None:
        if isinstance(expected, list):
            ok = sorted(actual) == sorted(expected)
        elif isinstance(expected, str):
            ok = actual == expected
        elif isinstance(expected, (int, float)):
            ok = actual == expected
        else:
            ok = actual == expected
    else:
        ok = bool(actual)
    if ok:
        PASS += 1; print(f"  [PASS] {desc}")
    else:
        FAIL += 1; print(f"  [FAIL] {desc} => expected {expected!r}, got {actual!r}")


# =========================================================================
# The exact bug report from user:
#   raw_text = "Đền chùa & Tâm linh, Thích hợp cho trẻ em"
#   destination_provinces = ["Bà Rịa - Vũng Tàu", "Bình Dương"]
#   duration_days = 3
#   Before fix: duration=2, dest=Hà Nội (WRONG)
#   After  fix: duration=3, dest="Bà Rịa - Vũng Tàu, Bình Dương" (CORRECT)
# =========================================================================
print("--- GROUP 1: User's exact bug report ---")

inp = TripInput(
    raw_text="Đền chùa & Tâm linh, Thích hợp cho trẻ em",
    destination_provinces=["Bà Rịa - Vũng Tàu", "Bình Dương"],
    duration_days=3,
    number_of_people=2,
    pace="moderate",
    travel_mode="driving",
    start_lat=10.822, start_lng=106.6257,
    end_lat=10.822, end_lng=106.6257,
)
r = parse_trip_request(inp)
check("duration_days: 3 (not 2 — user set)", r.duration_days, 3)
check("destination_area: BRVT+Bình Dương (not Hà Nội)",
      "Bà Rịa" in r.destination_area and "Bình Dương" in r.destination_area, True)
check("travel_mode: driving (not mixed)", r.travel_mode, "driving")
check("constraints: child_friendly parsed", "child_friendly" in r.constraints, True)
check("interests: has spiritual (parsed) + defaults",
      "spiritual" in r.interests and len(r.interests) >= 1, True)
check("start_location: user coords", r.start_location["lat"], 10.822)
check("number_of_people: 2", r.number_of_people, 2)


# =========================================================================
# GROUP 2: duration_days — raw_text không chứa số ngày
# =========================================================================
print("\n--- GROUP 2: duration_days ---")

# Text has NO day count → must keep user-set value
inp2 = TripInput(raw_text="thích đi chơi", destination_provinces=["Hà Nội"],
                 duration_days=5, pace="moderate")
r2 = parse_trip_request(inp2)
check("no number in text → keep user's 5", r2.duration_days, 5)

# Text HAS day count → parse it
inp2b = TripInput(raw_text="đi 3 ngày", destination_provinces=["Hà Nội"],
                  duration_days=5, pace="moderate")
r2b = parse_trip_request(inp2b)
check("text has '3 ngày' → use parsed 3", r2b.duration_days, 3)

# Text HAS "4 days" in English
inp2c = TripInput(raw_text="4 days trip", destination_provinces=["Hà Nội"],
                  duration_days=5, pace="moderate")
r2c = parse_trip_request(inp2c)
check("text has '4 days' → use parsed 4", r2c.duration_days, 4)

# No raw_text → use user-set value
inp2d = TripInput(destination_provinces=["Hà Nội"], duration_days=7, pace="moderate")
r2d = parse_trip_request(inp2d)
check("no raw_text → use user's 7", r2d.duration_days, 7)

# Default (no raw_text, no user-set)
inp2e = TripInput(destination_provinces=["Hà Nội"])
r2e = parse_trip_request(inp2e)
check("default duration → 2", r2e.duration_days, 2)


# =========================================================================
# GROUP 3: destination_area — raw_text không chứa tên tỉnh
# =========================================================================
print("\n--- GROUP 3: destination_area ---")

# Text has province keyword → text wins, prepended to user's province list
inp3a = TripInput(raw_text="đi Hà Nội", destination_provinces=["Đà Nẵng"],
                  duration_days=1)
r3a = parse_trip_request(inp3a)
check("text has 'Hà Nội' → dest=Hà Nội", r3a.destination_area, "Hà Nội")
check("text province prepended to list", r3a.destination_provinces, ["Hà Nội", "Đà Nẵng"])

# Text has NO province → use user's provinces
inp3b = TripInput(raw_text="đi chơi thôi", destination_provinces=["Đà Nẵng", "Hội An"],
                  duration_days=2)
r3b = parse_trip_request(inp3b)
check("no province in text → dest from user provinces",
      "Đà Nẵng" in r3b.destination_area, True)

# Text has NO province but user set destination_area
inp3c = TripInput(raw_text="đi chơi", destination_area="Ninh Bình",
                  destination_provinces=["Ninh Bình"], duration_days=2)
r3c = parse_trip_request(inp3c)
check("no province in text + user set area", r3c.destination_area, "Ninh Bình")

# Text has hoi an → maps to Quảng Nam
inp3d = TripInput(raw_text="đi Hội An 2 ngày", duration_days=3)
r3d = parse_trip_request(inp3d)
check("text has 'Hội An' → dest=Quảng Nam", r3d.destination_area, "Quảng Nam")
check("duration parsed from text", r3d.duration_days, 2)


# =========================================================================
# GROUP 4: interests — merge parsed + user-set
# =========================================================================
print("\n--- GROUP 4: interests ---")

# User set non-default interests → merge with parsed
inp4a = TripInput(raw_text="thích lịch sử và kiến trúc",
                  destination_provinces=["Hà Nội"], duration_days=1,
                  interests=["local_food", "museum"])
r4a = parse_trip_request(inp4a)
check("merge: history(parsed) + architecture(parsed) + local_food(user) + museum(user)",
      set(r4a.interests) >= {"history", "architecture", "local_food", "museum"}, True)

# User set default interests → just use parsed
inp4b = TripInput(raw_text="thích tâm linh và thiên nhiên",
                  destination_provinces=["Hà Nội"], duration_days=1)
r4b = parse_trip_request(inp4b)
check("default interests → use parsed: spiritual + nature",
      set(r4b.interests) >= {"spiritual", "nature"}, True)

# No raw_text → user interests
inp4c = TripInput(destination_provinces=["Hà Nội"], duration_days=1,
                  interests=["spiritual", "museum"])
r4c = parse_trip_request(inp4c)
check("no raw_text → keep user interests", set(r4c.interests), {"spiritual", "museum"})

# Text has food but no raw interests → parse
inp4d = TripInput(raw_text="thích ăn uống", destination_provinces=["Hà Nội"], duration_days=1)
r4d = parse_trip_request(inp4d)
check("text 'ăn' → local_food parsed", "local_food" in r4d.interests, True)


# =========================================================================
# GROUP 5: pace — chỉ override nếu text có keyword
# =========================================================================
print("\n--- GROUP 5: pace ---")

inp5a = TripInput(raw_text="đi chơi thôi", destination_provinces=["Hà Nội"],
                  duration_days=1, pace="relaxed")
r5a = parse_trip_request(inp5a)
check("no pace keyword in text → keep user's relaxed", r5a.pace, "relaxed")

inp5b = TripInput(raw_text="đi thư giãn", destination_provinces=["Hà Nội"],
                  duration_days=1, pace="packed")
r5b = parse_trip_request(inp5b)
check("text has 'thư giãn' → parsed 'relaxed' overrides user's packed", r5b.pace, "relaxed")

inp5c = TripInput(destination_provinces=["Hà Nội"], duration_days=1)
r5c = parse_trip_request(inp5c)
check("no raw_text → default moderate", r5c.pace, "moderate")


# =========================================================================
# GROUP 6: budget_level — chỉ override nếu text có keyword
# =========================================================================
print("\n--- GROUP 6: budget_level ---")

inp6a = TripInput(raw_text="đi chơi", destination_provinces=["Hà Nội"],
                  duration_days=1, budget_level="high")
r6a = parse_trip_request(inp6a)
check("no budget keyword → keep user's high", r6a.budget_level, "high")

inp6b = TripInput(raw_text="đi tiết kiệm", destination_provinces=["Hà Nội"],
                  duration_days=1, budget_level="high")
r6b = parse_trip_request(inp6b)
check("text 'tiết kiệm' → parsed 'low' overrides", r6b.budget_level, "low")


# =========================================================================
# GROUP 7: travel_mode — không override từ raw_text
# =========================================================================
print("\n--- GROUP 7: travel_mode ---")

inp7a = TripInput(raw_text="đi chơi", destination_provinces=["Hà Nội"],
                  duration_days=1, travel_mode="driving")
r7a = parse_trip_request(inp7a)
check("user set driving → keep", r7a.travel_mode, "driving")

inp7b = TripInput(raw_text="đi chơi", destination_provinces=["Hà Nội"], duration_days=1)
r7b = parse_trip_request(inp7b)
check("no raw_text + no user → default driving", r7b.travel_mode, "driving")


# =========================================================================
# GROUP 8: constraints — luôn merge cả hai
# =========================================================================
print("\n--- GROUP 8: constraints ---")

inp8a = TripInput(raw_text="đi với trẻ em", destination_provinces=["Hà Nội"],
                  duration_days=1, constraints=["elderly_friendly"])
r8a = parse_trip_request(inp8a)
check("merge: child_friendly(parsed) + elderly_friendly(user)",
      set(r8a.constraints) >= {"child_friendly", "elderly_friendly"}, True)

inp8b = TripInput(raw_text="đi chơi", destination_provinces=["Hà Nội"],
                  duration_days=1, constraints=["elderly_friendly"])
r8b = parse_trip_request(inp8b)
check("no constraint in text → keep user's", r8b.constraints, ["elderly_friendly"])


# =========================================================================
# GROUP 9: start/end location
# =========================================================================
print("\n--- GROUP 9: start/end location ---")

inp9a = TripInput(raw_text="đi Hà Nội", destination_provinces=["Hà Nội"],
                  duration_days=1, start_lat=10.822, start_lng=106.6257,
                  end_lat=10.822, end_lng=106.6257)
r9a = parse_trip_request(inp9a)
check("user coords kept", r9a.start_location["lat"], 10.822)
check("end coords kept", r9a.end_location["lat"], 10.822)

# No user coords → province coords
inp9b = TripInput(raw_text="đi Hà Nội", duration_days=1)
r9b = parse_trip_request(inp9b)
check("no coords → Hà Nội default", r9b.start_location["lat"], 21.0285)


# =========================================================================
# GROUP 10: number_of_people
# =========================================================================
print("\n--- GROUP 10: number_of_people ---")

inp10a = TripInput(raw_text="đi chơi", destination_provinces=["Hà Nội"],
                   duration_days=1, number_of_people=5)
r10a = parse_trip_request(inp10a)
check("user set 5 people → keep", r10a.number_of_people, 5)

inp10b = TripInput(raw_text="đi chơi", destination_provinces=["Hà Nội"], duration_days=1)
r10b = parse_trip_request(inp10b)
check("no people set → default 2", r10b.number_of_people, 2)


# =========================================================================
# GROUP 11: must_visit_site_ids
# =========================================================================
print("\n--- GROUP 11: must_visit_site_ids ---")

inp11a = TripInput(raw_text="đi chơi", destination_provinces=["Hà Nội"],
                   duration_days=1, must_visit_site_ids=["hn-001", "hn-002"])
r11a = parse_trip_request(inp11a)
check("must_visit users kept", len(r11a.must_visit_site_ids), 2)
check("must_visit users kept values", r11a.must_visit_site_ids, ["hn-001", "hn-002"])


# =========================================================================
# GROUP 12: Full end-to-end — input giống user thực tế
# =========================================================================
print("\n--- GROUP 12: End-to-end (user's actual input) ---")

inp12 = TripInput(
    raw_text="Đền chùa & Tâm linh, Thích hợp cho trẻ em",
    destination_provinces=["Bà Rịa - Vũng Tàu", "Bình Dương"],
    start_date="2026-07-08",
    duration_days=3,
    number_of_people=2,
    pace="moderate",
    travel_mode="driving",
    start_lat=10.822, start_lng=106.6257,
    end_lat=10.822, end_lng=106.6257,
)
r12 = parse_trip_request(inp12)
check("duration=3 (was 2)", r12.duration_days, 3)
check("dest contains BRVT", "Bà Rịa" in r12.destination_area, True)
check("dest contains BD", "Bình Dương" in r12.destination_area, True)
check("NOT Hà Nội", r12.destination_area != "Hà Nội", True)
check("travel_mode=driving", r12.travel_mode, "driving")
check("constraint child_friendly", "child_friendly" in r12.constraints, True)
check("people=2", r12.number_of_people, 2)
check("province count=2", len(r12.destination_provinces), 2)


# =========================================================================
# GROUP 13: raw_text has everything → parsed values take priority
# =========================================================================
print("\n--- GROUP 13: raw_text fully specified → parsed wins ---")

inp13 = TripInput(
    raw_text="Tôi muốn đi Đà Nẵng 5 ngày, thích lịch sử, nhịp độ thư giãn, ngân sách tiết kiệm, đi cùng người già",
    destination_provinces=["Hà Nội"],  # different from text
    duration_days=2,                    # different from text
    pace="packed",                      # different from text
    budget_level="high",                # different from text
)
r13 = parse_trip_request(inp13)
check("text says 5 ngày → wins over user's 2", r13.duration_days, 5)
check("text says Đà Nẵng → dest=Đà Nẵng", r13.destination_area, "Đà Nẵng")
check("text province prepended", r13.destination_provinces, ["Đà Nẵng", "Hà Nội"])
check("text says thư giãn → wins over packed", r13.pace, "relaxed")
check("text says tiết kiệm → wins over high", r13.budget_level, "low")
check("text says người già → constraint added", "elderly_friendly" in r13.constraints, True)
check("text says lịch sử → interest added", "history" in r13.interests, True)


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
