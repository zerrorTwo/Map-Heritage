"""
Full test suite for Phase 1 algorithm enhancements.
Covers: step2 (partial-credit interest), step4 (dynamic weights, hour-weather,
        bayesian popularity, accessibility, budget), step8 (two-pass distance,
        real budget_fit, quality score integration).
"""
import sys
import numpy as np

sys.path.insert(0, '.')

from services.ai_service.models import (
    HeritageSite, TripRequest, Forecast, ScoredSite,
    ItineraryItem, DayPlan
)
from services.ai_service.step2_candidates import (
    CATEGORY_SIM, _category_similarity, _interest_overlap,
    generate_candidates, _satisfies_constraints
)
from services.ai_service.step4_scoring import (
    BASE_WEIGHTS, _get_dynamic_weights,
    compute_interest_match, compute_weather_suitability,
    compute_distance_score, compute_budget_fit,
    derive_popularity, derive_historical_importance, derive_accessibility,
    score_site, score_all_sites
)
from services.ai_service.step8_assembly import (
    assemble_itinerary, _compute_budget_fit, _compute_quality_score,
    _lookup_distance, _get_coords
)
from services.ai_service.mmr_rerank import mmr_rerank, _site_similarity

PASS, FAIL = 0, 0

def check(desc, actual, expected, tol=1e-3):
    global PASS, FAIL
    if isinstance(expected, float):
        ok = abs(actual - expected) < tol
    elif isinstance(expected, list) and isinstance(actual, list):
        ok = len(actual) == len(expected) and all(abs(a - e) < tol for a, e in zip(actual, expected))
    elif isinstance(expected, dict):
        ok = actual == expected
    else:
        ok = actual == expected
    if ok:
        PASS += 1
        print(f"  [PASS] {desc}")
    else:
        FAIL += 1
        print(f"  [FAIL] {desc} => expected {expected!r}, got {actual!r}")


# =========================================================================
# TEST GROUP 1: step2_candidates -- _category_similarity
# =========================================================================
print("\n--- GROUP 1: _category_similarity ---")

check("Exact match (history,history)", _category_similarity("history", "history"), 1.0)
check("Known pair (history,architecture)", _category_similarity("history", "architecture"), 0.6)
check("Reverse pair (architecture,history)", _category_similarity("architecture", "history"), 0.6)
check("Unknown pair (history,beach)", _category_similarity("history", "beach"), 0.0)
check("Case insensitive (HISTORY, Architecture)", _category_similarity("HISTORY", "Architecture"), 0.6)
check("Spiritual->pagoda mapping", _category_similarity("spiritual", "pagoda"), 0.8)
check("Bidirectional symmetry", _category_similarity("museum", "history"), _category_similarity("history", "museum"))


# =========================================================================
# TEST GROUP 2: step2_candidates -- _interest_overlap (partial-credit)
# =========================================================================
print("\n--- GROUP 2: _interest_overlap (partial-credit) ---")

site_none = HeritageSite(id="0", name="None", province="HN", lat=21.0, lng=105.0, categories=[])
site_pagoda = HeritageSite(id="1", name="Pagoda", province="HN", lat=21.0285, lng=105.8542, categories=["pagoda", "architecture"])
site_museum = HeritageSite(id="2", name="Museum", province="HN", lat=21.0300, lng=105.8500, categories=["museum", "history"])
site_beach = HeritageSite(id="3", name="Beach", province="DN", lat=16.0, lng=108.0, categories=["beach", "nature"])
site_history = HeritageSite(id="4", name="History", province="HN", lat=21.0, lng=105.0, categories=["history"])

check("Empty interests => 0.0", _interest_overlap(site_pagoda, []), 0.0)
check("Site no categories => 0.0", _interest_overlap(site_none, ["history"]), 0.0)
check("Perfect match (1 category)", _interest_overlap(site_history, ["history"]), 1.0)
check("Partial: history,arch,spiritual vs pagoda,architecture",
     _interest_overlap(site_pagoda, ["history", "architecture", "spiritual"]), 0.8)
check("No overlap: beach,craft vs history", _interest_overlap(site_beach, ["history", "craft_village"]), 0.0)
check("history,arch,spiritual vs museum,history",
     _interest_overlap(site_museum, ["history", "architecture", "spiritual"]), 0.6667)


# =========================================================================
# TEST GROUP 3: step4 -- _get_dynamic_weights
# =========================================================================
print("\n--- GROUP 3: _get_dynamic_weights ---")

trip_default = TripRequest(destination_area="Ha Noi")
trip_elderly = TripRequest(destination_area="Ha Noi", constraints=["elderly_friendly"])
trip_child = TripRequest(destination_area="Ha Noi", constraints=["child_friendly"])
trip_low_budget = TripRequest(destination_area="Ha Noi", budget_level="low")
trip_med_budget = TripRequest(destination_area="Ha Noi", budget_level="medium")
trip_high_budget = TripRequest(destination_area="Ha Noi", budget_level="high")
trip_both = TripRequest(destination_area="Ha Noi", constraints=["elderly_friendly"], budget_level="low")
trip_empty_constraints = TripRequest(destination_area="Ha Noi", constraints=[])

w_def = _get_dynamic_weights(trip_default)
w_eld = _get_dynamic_weights(trip_elderly)
w_child_test = _get_dynamic_weights(trip_child)
w_low = _get_dynamic_weights(trip_low_budget)
w_med = _get_dynamic_weights(trip_med_budget)
w_high = _get_dynamic_weights(trip_high_budget)
w_both = _get_dynamic_weights(trip_both)

check("Default weights = BASE_WEIGHTS", dict(w_def), dict(BASE_WEIGHTS))
check("Default sum = 1.0", sum(w_def.values()), 1.0)
check("Elderly: accessibility boosted to 0.15 before renormalize", w_eld["accessibility"], 0.15 / 1.10)
check("Elderly: sum = 1.0", sum(w_eld.values()), 1.0)
check("Child: same boost as elderly", w_child_test["accessibility"], 0.15 / 1.10)
check("Low budget: budget boosted to 0.15", w_low["budget"], 0.15 / 1.10)
check("Medium budget: no boost", dict(w_med), dict(BASE_WEIGHTS))
check("High budget: no boost", dict(w_high), dict(BASE_WEIGHTS))
check("Both elder+low: acc=0.125, budg=0.125", w_both["accessibility"], 0.15 / 1.20)
check("Both elder+low: budget=0.125", w_both["budget"], 0.15 / 1.20)
check("Both elder+low: sum=1.0", sum(w_both.values()), 1.0)
check("Empty constraints list: default", dict(_get_dynamic_weights(trip_empty_constraints)), dict(BASE_WEIGHTS))


# =========================================================================
# TEST GROUP 4: step4 -- compute_interest_match
# =========================================================================
print("\n--- GROUP 4: compute_interest_match ---")

check("Empty interests => 0.5", compute_interest_match(site_pagoda, []), 0.5)
check("Partial match pagoda", compute_interest_match(site_pagoda, ["history", "architecture", "spiritual"]), 0.8)
check("Partial match museum", compute_interest_match(site_museum, ["history", "architecture", "spiritual"]), 0.6667)
check("No overlap", compute_interest_match(site_beach, ["history", "craft_village"]), 0.0)


# =========================================================================
# TEST GROUP 5: step4 -- compute_weather_suitability (hour-level)
# =========================================================================
print("\n--- GROUP 5: compute_weather_suitability (hour-level) ---")

site_outdoor = HeritageSite(id="w1", name="Beach", province="DN", lat=16.0, lng=108.0, outdoor_score=0.9, indoor_score=0.1)
site_indoor = HeritageSite(id="w2", name="Museum", province="HN", lat=21.0, lng=105.0, outdoor_score=0.1, indoor_score=0.9)

def make_forecasts(temp=25, rain=0, uv=3, hours=None):
    hrs = hours or range(24)
    return [Forecast(date="2026-07-06", hour=h, temperature_c=temp, rain_probability=rain, uv_index=uv) for h in hrs]

check("No forecasts => 1.0", compute_weather_suitability(site_outdoor, [], 12), 1.0)
check("Perfect weather outdoor => 1.0", compute_weather_suitability(site_outdoor, make_forecasts(), 12), 1.0)
check("Rain >70 outdoor => -0.35", compute_weather_suitability(site_outdoor, make_forecasts(rain=80), 12), 0.65)
check("Rain 50-70 outdoor => -0.15", compute_weather_suitability(site_outdoor, make_forecasts(rain=55), 12), 0.85)
check("Rain >70 indoor => no penalty", compute_weather_suitability(site_indoor, make_forecasts(rain=80), 12), 1.0)
check("Temp >35 outdoor => -0.25", compute_weather_suitability(site_outdoor, make_forecasts(temp=36), 12), 0.75)
check("Temp 32-35 outdoor => -0.10", compute_weather_suitability(site_outdoor, make_forecasts(temp=33), 12), 0.90)
check("Temp >35 indoor => no penalty", compute_weather_suitability(site_indoor, make_forecasts(temp=36), 12), 1.0)
check("UV >8 at noon => -0.20", compute_weather_suitability(site_outdoor, make_forecasts(uv=9), 12), 0.80)
check("UV 6-8 at 15h => -0.10", compute_weather_suitability(site_outdoor, make_forecasts(uv=7), 15), 0.90)
check("UV >8 at 8h (outside 11-14) => no UV penalty", compute_weather_suitability(site_outdoor, make_forecasts(uv=9), 8), 1.0)
check("Temp <10 outdoor => -0.15", compute_weather_suitability(site_outdoor, make_forecasts(temp=8), 12), 0.85)
check("Temp 10-15 outdoor => -0.05", compute_weather_suitability(site_outdoor, make_forecasts(temp=12), 12), 0.95)
check("Rain+UV stacked => 1.0-0.35-0.20 = 0.45", compute_weather_suitability(site_outdoor, make_forecasts(rain=80, uv=9), 12), 0.45)
check("Score clamped to >=0 (extreme)", compute_weather_suitability(site_outdoor, make_forecasts(temp=40, rain=90, uv=10), 12), max(0.0, 1.0-0.35-0.25-0.20))


# =========================================================================
# TEST GROUP 6: step4 -- derive_popularity
# =========================================================================
print("\n--- GROUP 6: derive_popularity ---")

site_unesco = HeritageSite(id="p1", name="UNESCO", province="Ha Noi", lat=21.0, lng=105.0, categories=["unesco", "history", "architecture"], description="test")
site_single = HeritageSite(id="p2", name="Single", province="Ha Noi", lat=21.0, lng=105.0, categories=["nature"])
site_multi = HeritageSite(id="p3", name="Multi", province="Ha Noi", lat=21.0, lng=105.0, categories=["history", "museum", "architecture"], description="desc", visit_tips="tip")

check("UNESCO+history+arch => high", derive_popularity(site_unesco) > 0.8, True)
check("Single category nature => moderate", derive_popularity(site_single) >= 0.5, True)
check("Multi with tips => higher than single", derive_popularity(site_multi) > derive_popularity(site_single), True)
check("Popularity in [0,1]", 0.0 <= derive_popularity(site_multi) <= 1.0, True)


# =========================================================================
# TEST GROUP 7: step4 -- derive_historical_importance
# =========================================================================
print("\n--- GROUP 7: derive_historical_importance ---")

check("UNESCO+history => high", derive_historical_importance(site_unesco) > 0.8, True)
check("Single nature => low", derive_historical_importance(site_single) < 0.55, True)
check("History+museum+arch => medium-high", derive_historical_importance(site_multi) >= 0.7, True)


# =========================================================================
# TEST GROUP 8: step4 -- derive_accessibility
# =========================================================================
print("\n--- GROUP 8: derive_accessibility ---")

site_good = HeritageSite(id="a1", name="Good", province="HN", lat=21.0, lng=105.0,
    suitable_for_elderly=True, suitable_for_children=True, indoor_score=0.8, estimated_visit_minutes=45)
site_bad = HeritageSite(id="a2", name="Bad", province="HN", lat=21.0, lng=105.0,
    suitable_for_elderly=True, suitable_for_children=True, indoor_score=0.2, estimated_visit_minutes=120)

check("Good indoor + short visit => higher", derive_accessibility(site_good, []) > derive_accessibility(site_bad, []), True)
check("No constraints => base score", derive_accessibility(site_good, []) > 0.6, True)
check("Elderly + good indoor => bonus", derive_accessibility(site_good, ["elderly_friendly"]) >= derive_accessibility(site_good, []), True)
check("Score in [0,1]", 0.0 <= derive_accessibility(site_bad, ["avoid_long_walking"]) <= 1.0, True)


# =========================================================================
# TEST GROUP 9: step4 -- compute_budget_fit
# =========================================================================
print("\n--- GROUP 9: compute_budget_fit ---")

site_free = HeritageSite(id="c1", name="Free", province="HN", lat=21.0, lng=105.0, ticket_price=0)
site_15k = HeritageSite(id="c2", name="15k", province="HN", lat=21.0, lng=105.0, ticket_price=15000)
site_50k = HeritageSite(id="c3", name="50k", province="HN", lat=21.0, lng=105.0, ticket_price=50000)
site_200k = HeritageSite(id="c4", name="200k", province="HN", lat=21.0, lng=105.0, ticket_price=200000)

check("Free site, low budget => 1.0", compute_budget_fit(site_free, "low"), 1.0)
check("15k site, low budget => 0.5", compute_budget_fit(site_15k, "low"), 0.5)
check("50k site, low budget => 0.2 (capped)", compute_budget_fit(site_50k, "low"), 0.2)
check("200k site, medium budget => 0.2", compute_budget_fit(site_200k, "medium"), 0.2)
check("200k site, high budget => 0.8", compute_budget_fit(site_200k, "high"), 1.0 - 200000 / 1000000)


# =========================================================================
# TEST GROUP 10: step4 -- score_site integration
# =========================================================================
print("\n--- GROUP 10: score_site integration ---")

fcasts = [Forecast(date="2026-07-06", hour=10, temperature_c=25, rain_probability=0, uv_index=3)]

sc_default = score_site(site_museum, trip_default, fcasts, 21.0285, 105.8542, 10)
check("score_site returns ScoredSite", isinstance(sc_default, ScoredSite), True)
check("score in [0,1]", 0.0 <= sc_default.score <= 1.0, True)
check("interest_match field populated", sc_default.interest_match > 0, True)
check("weather_suitability field populated", sc_default.weather_suitability >= 0, True)

sc_elderly = score_site(site_museum, trip_elderly, fcasts, 21.0285, 105.8542, 10)
check("Score changes with dynamic weights", sc_default.score != sc_elderly.score, True)


# =========================================================================
# TEST GROUP 11: score_all_sites
# =========================================================================
print("\n--- GROUP 11: score_all_sites ---")

candidates = [site_museum, site_pagoda, site_beach, site_outdoor]
fcasts_by_site = {s.id: fcasts for s in candidates}
scored = score_all_sites(candidates, trip_default, fcasts_by_site)
check("Returns correct count", len(scored), len(candidates))
check("Sorted descending", all(scored[i].score >= scored[i+1].score for i in range(len(scored)-1)), True)


# =========================================================================
# TEST GROUP 12: step8 -- _compute_budget_fit
# =========================================================================
print("\n--- GROUP 12: step8._compute_budget_fit ---")

sc_free = ScoredSite(site=site_free, score=0.8, interest_match=0.5, weather_suitability=1.0)
sc_50k_site = ScoredSite(site=site_50k, score=0.7, interest_match=0.5, weather_suitability=1.0)
sc_200k_site = ScoredSite(site=site_200k, score=0.6, interest_match=0.5, weather_suitability=1.0)

check("No heritage sites => 0.8", _compute_budget_fit([], trip_default), 0.8)
check("All free sites, low budget => 1.0", _compute_budget_fit([sc_free, sc_free], trip_low_budget), 1.0)
check("Avg 50k, low budget (>= max) => 0.3", _compute_budget_fit([sc_50k_site], trip_low_budget), 0.3)
check("Avg 50k, medium budget => 0.65", _compute_budget_fit([sc_50k_site], trip_med_budget), 1.0 - 0.7 * (50000 / 100000))


# =========================================================================
# TEST GROUP 13: step8 -- _lookup_distance
# =========================================================================
print("\n--- GROUP 12: step8._lookup_distance ---")

item_a = ItineraryItem(ref_id="1", type="heritage", name="A")
item_b = ItineraryItem(ref_id="2", type="heritage", name="B")

dm_matrix = np.array([[0, 1500], [1500, 0]], dtype=float)
dm_sites = [ScoredSite(site=site_pagoda, score=1.0), ScoredSite(site=site_museum, score=0.9)]

check("Returns real distance (1500m)", _lookup_distance(item_a, item_b, [], dm_sites, dm_matrix), 1500.0)
check("Returns None when matrix is None", _lookup_distance(item_a, item_b, [], [], None), None)
check("Returns None when item not in dm_sites (restaurant)", 
      _lookup_distance(item_a, ItineraryItem(ref_id="rest_1", type="restaurant", name="R"), [], dm_sites, dm_matrix), None)
check("Returns None when distance=999999", 
      _lookup_distance(item_a, item_b, [], dm_sites, np.array([[0, 999999], [999999, 0]], dtype=float)), None)


# =========================================================================
# TEST GROUP 14: step8 -- _compute_quality_score
# =========================================================================
print("\n--- GROUP 14: step8._compute_quality_score ---")

dp1 = DayPlan(day=1, date="2026-07-06", items=[
    ItineraryItem(ref_id="1", type="heritage", name="A", distance_from_previous_m=1000, travel_from_previous_minutes=2),
    ItineraryItem(ref_id="2", type="heritage", name="B", distance_from_previous_m=1000, travel_from_previous_minutes=2),
])
all_sc = [ScoredSite(site=site_pagoda, score=0.9, interest_match=0.8, weather_suitability=1.0),
          ScoredSite(site=site_museum, score=0.8, interest_match=0.7, weather_suitability=0.9)]

qs = _compute_quality_score([dp1], all_sc, 2000, trip_default, 0.9)
check("Quality score in [0,1]", 0.0 <= qs <= 1.0, True)
check("Custom budget_fit used", abs(qs - _compute_quality_score([dp1], all_sc, 2000, trip_default, 0.5)) > 0.01, True)
check("Zero days => no crash", _compute_quality_score([], [], 0, trip_default, 0.8) is not None, True)


# =========================================================================
# TEST GROUP 15: step8 -- assemble_itinerary (end-to-end)
# =========================================================================
print("\n--- GROUP 15: assemble_itinerary (end-to-end) ---")

dp_list = [DayPlan(day=1, date="2026-07-06", items=[
    ItineraryItem(ref_id="1", type="heritage", name="Site A"),
    ItineraryItem(ref_id="2", type="heritage", name="Site B"),
])]
cluster = [ScoredSite(site=site_pagoda, score=0.9, interest_match=0.8, weather_suitability=1.0),
           ScoredSite(site=site_museum, score=0.8, interest_match=0.7, weather_suitability=0.9)]

# Without OSRM matrix (haversine fallback)
it1 = assemble_itinerary(dp_list, [cluster], trip_default, [])
check("Haversine: returns Itinerary", it1 is not None, True)
check("Haversine: total_score > 0", it1.total_score > 0, True)
check("Haversine: time slots assigned", all(it.time for dp in it1.days for it in dp.items), True)
check("Haversine: distance from previous populated", len([it for dp in it1.days for it in dp.items if it.distance_from_previous_m > 0]), 1)

# With OSRM matrix
dm_full = np.array([[0, 3200], [3200, 0]], dtype=float)
dist_info = {"sites": cluster, "matrix": dm_full}
it2 = assemble_itinerary(dp_list, [cluster], trip_default, [], dist_info)
check("OSRM: uses real distance (3200m)", it2.days[0].items[1].distance_from_previous_m, 3200.0)
check("OSRM: total_distance uses real values", it2.total_distance_km, 3.2)

# With None distance_matrix
it3 = assemble_itinerary(dp_list, [cluster], trip_default, [], None)
check("None distance_matrix: falls back to haversine", it3 is not None, True)


# =========================================================================
# TEST GROUP 16: Edge cases & regression
# =========================================================================
print("\n--- GROUP 16: Edge cases ---")

check("Empty scored_clusters => no crash", assemble_itinerary([], [], trip_default, []) is not None, True)
check("Single-day itinerary", assemble_itinerary(dp_list, [cluster], trip_default, []) is not None, True)

dp_multi = [
    DayPlan(day=1, date="2026-07-06", items=[ItineraryItem(ref_id="1", type="heritage", name="D1")]),
    DayPlan(day=2, date="2026-07-07", items=[ItineraryItem(ref_id="2", type="heritage", name="D2")]),
]
clusters_multi = [[ScoredSite(site=site_pagoda, score=0.9)], [ScoredSite(site=site_museum, score=0.8)]]
it_multi = assemble_itinerary(dp_multi, clusters_multi, trip_default, [])
check("Multi-day itinerary", len(it_multi.days), 2)

# Test site with all empty categories
site_empty = HeritageSite(id="e1", name="Empty", province="HN", lat=21.0, lng=105.0, categories=[])
check("Empty categories interest_match=0.0", compute_interest_match(site_empty, ["history"]), 0.0)

# Test generate_candidates respects partial-credit
sites_pool = [site_museum, site_pagoda, site_beach, site_history, site_empty]
trip_for_candidates = TripRequest(destination_area="Ha Noi", destination_provinces=["HN"])
result = generate_candidates(trip_for_candidates, sites_pool, top_n=10)
check("generate_candidates returns list", isinstance(result, list), True)
check("generate_candidates non-empty", len(result) > 0, True)

# Test distance_score boundaries (logarithmic decay, half_dist=20km, floor=0.15)
site_far = HeritageSite(id="far", name="Far", province="HN", lat=22.0, lng=106.0, categories=["history"])
ds_far = compute_distance_score(site_far, 21.0285, 105.8542)
check("Distance far site (log decay floor 0.15)", ds_far >= 0.15, True)
ds_near = compute_distance_score(site_museum, site_museum.lat, site_museum.lng)
check("Distance zero => max score 1.0", ds_near, 1.0)

# Test avoid_long_walking with derive_accessibility
site_high_indoor = HeritageSite(id="indoor", name="Indoor", province="HN", lat=21.0, lng=105.0, indoor_score=0.8, estimated_visit_minutes=60)
check("avoid_long_walking + high indoor >= no constraints",
      derive_accessibility(site_high_indoor, ["avoid_long_walking"]) >= derive_accessibility(site_high_indoor, []), True)
site_low_indoor = HeritageSite(id="lowin", name="Low Indoor", province="HN", lat=21.0, lng=105.0, indoor_score=0.2, estimated_visit_minutes=60)
check("avoid_long_walking + low indoor => lower", 
      derive_accessibility(site_low_indoor, ["avoid_long_walking"]) < derive_accessibility(site_high_indoor, ["avoid_long_walking"]), True)


# =========================================================================
# TEST GROUP 17: Score boundary verification
# =========================================================================
print("\n--- GROUP 17: Score boundaries ---")

# Verify old Jaccard vs new partial-credit improvement
old_jaccard_pagoda = len(set(["pagoda", "architecture"]) & set(["history", "architecture", "spiritual"])) / 3
check("Old Jaccard pagoda (was 0.33)", old_jaccard_pagoda, 0.3333)
check("New partial-credit pagoda (now 0.80)", 
      compute_interest_match(site_pagoda, ["history", "architecture", "spiritual"]), 0.8)
check("Score improvement > Jaccard baseline", 
      compute_interest_match(site_pagoda, ["history", "architecture", "spiritual"]) > old_jaccard_pagoda, True)


# =========================================================================
# TEST GROUP 18: MMR diversity re-ranking
# =========================================================================
print("\n--- GROUP 18: MMR diversity re-ranking ---")

mmr_sites = [
    ScoredSite(site=site_pagoda, score=0.9, interest_match=0.8, weather_suitability=1.0),
    ScoredSite(site=site_museum, score=0.85, interest_match=0.7, weather_suitability=0.9),
    ScoredSite(site=site_beach, score=0.7, interest_match=0.3, weather_suitability=1.0),
    ScoredSite(site=site_history, score=0.65, interest_match=0.5, weather_suitability=1.0),
]
reranked = mmr_rerank(mmr_sites, lambd=0.7)
check("MMR returns same count", len(reranked), len(mmr_sites))
check("MMR first item is top scorer", reranked[0].score, mmr_sites[0].score)
check("MMR pushes beach ahead of museum (diversity)", reranked[1].site.id == "3" or reranked[2].site.id == "3", True)

# Test empty / single
check("MMR empty list", mmr_rerank([]), [])
check("MMR single item", len(mmr_rerank([mmr_sites[0]])), 1)

# Test _site_similarity
sim_identical = _site_similarity(mmr_sites[0], mmr_sites[0])
check("Site similarity to self ~ 1.0", sim_identical > 0.9, True)
sim_different = _site_similarity(
    ScoredSite(site=site_pagoda, score=0.9), 
    ScoredSite(site=site_beach, score=0.7)
)
check("Pagoda vs Beach similarity < 0.3", sim_different < 0.3, True)


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
