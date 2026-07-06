# Plan: Improving Itinerary & Site Scores in Map-Heritage

> Based on the architecture described in `README.md` (8-step recommendation pipeline).
> This plan is written from the documented design only — I haven't reviewed the actual
> source code. Treat each item as a hypothesis to validate against your real data/code,
> not a guaranteed fix. Section 7 explains how to check that a "higher score" really
> means a "better itinerary" and not just a gamed metric.

---

## 1. Where the score likely leaks

Two scoring layers exist in your pipeline:

- **Per-site score** (`step4_scoring.py`) — 7 weighted dimensions → feeds clustering/routing.
- **Itinerary score** (`step8_assembly.py`) — 7 weighted components → the `total_score` shown to the user (e.g. `0.82`).

Likely reasons the final number sits lower than you'd like:

| Cause | Where |
|---|---|
| Weights are hand-guessed, never empirically tuned | step4 + step8 |
| Jaccard similarity punishes *partial* interest matches harshly | step2 / step4 |
| `distance` score in step4 uses haversine, computed **before** real routing exists | step4 → step6 |
| Weather bucket (`excellent/good/fair/poor/bad`) is coarse, not tied to the actual visit hour | step3 → step4 |
| K-means (step5) and TTDP (step6a) are two separate optimizations — clustering mistakes propagate downstream and hurt `route_efficiency` / `schedule_balance` in step8 | step5 → step6 → step8 |
| `accessibility`/`budget` stay at fixed 5% weight even when the user explicitly asked for `wheelchair_accessible` or `budget_level: low` | step4 |
| No feedback loop — weights never adapt to what users actually pick | step4 + step8 |

---

## 2. Phase 1 — Quick wins (low effort, do these first)

1. **Soften interest matching.**
   Replace pure Jaccard with a partial-credit similarity: give category pairs like
   `history`↔`architecture` or `art`↔`museum` a nonzero similarity instead of 0.
   ```
   S_interest = Σ max_j sim(user_interest_i, site_category_j) / |user_interests|
   ```
   This alone usually lifts `interest_match` scores that Jaccard was flooring to 0.

2. **Re-normalize weights when constraints are explicit.**
   If `constraints` contains `wheelchair_accessible` or `elderly_friendly`, temporarily
   boost `accessibility` weight (e.g. 0.05 → 0.15) and re-normalize the other 6 weights
   to sum to 1. Same idea for `budget_level: low` → boost `budget` weight. Right now a
   user who explicitly asks for something is still only getting 5% credit for it.

3. **Two-pass distance scoring.**
   Keep haversine for the step4 pre-filter (it's cheap and needed before clustering),
   but once `step6_routing.py` returns real OSRM travel times, **re-score** `distance`
   and `route_efficiency` using actual minutes instead of straight-line km before
   computing the final `total_score` in step8. Haversine underestimates real travel
   time in dense urban cores (Hà Nội, Hội An) and overestimates it on highways —
   both distort the final number.

4. **Hour-level weather matching.**
   Match each item's forecast to its actual `time` slot (e.g. 12:00–13:00) instead of
   a daily aggregate bucket. A site scheduled at 08:00 shouldn't inherit a "poor"
   rating caused by a 14:00 thunderstorm.

5. **Apply the Bayesian weighted rating to heritage sites too**, not just restaurants
   (step7 already does this — just reuse the same formula for the `popularity`
   dimension in step4). This reduces noise from sites with very few reviews.

**Expected effect:** these are formula/data fixes, not new algorithms — cheapest to
ship, and each removes an artificial ceiling rather than "inflating" the score.

---

## 3. Phase 2 — Algorithmic changes (medium effort)

### 3.1 Merge clustering + routing into one solve

Right now: K-means (step5) picks day-clusters by lat/lng → then OR-Tools TTDP (step6a)
optimizes each day independently. K-means doesn't know about visit durations, time
windows, or site scores — it can hand day 2 a cluster that's geographically tight but
impossible to fit in an 08:00–17:00 window, which then tanks `schedule_balance` and
`route_efficiency` in step8.

**Alternative:** model the whole trip as a **Team Orienteering Problem (TOP)** —
OR-Tools supports this as a multi-vehicle Orienteering Problem with Time Windows,
where each "vehicle" = one day. This jointly decides which cluster of sites goes to
which day *and* the visiting order, maximizing total score under time-window and
duration constraints in a single solve.

- Pro: no error propagation between clustering and routing; usually a real total_score bump.
- Con: harder to implement/debug than two separate steps; solve time can grow with `duration_days × site_count` (mitigate with the same 2s time limit + a fallback to your current two-stage approach if it times out).

### 3.2 Tune weights empirically instead of guessing

Two options depending on what data you have:

- **No user data yet:** curate 15–30 "gold" itineraries by hand (or with a Vietnam
  travel expert) for a few personas, then grid-search or Bayesian-optimize
  (e.g. with Optuna) the 7+7 weight vectors to maximize agreement with those
  gold itineraries.
- **You do have user data (saves, edits, removals):** treat removed/edited sites as
  negative signal and train a lightweight **Learning-to-Rank** model (LightGBM
  ranker or even plain logistic regression) on the existing 7 features per site.
  This replaces the fixed 0.30/0.20/0.15… weights with learned ones and can be
  retrained periodically.

### 3.3 Embedding-based interest matching

`interests` today is a small fixed tag list (`history`, `architecture`, …). But you
already have rich text per site (`deepseek_enriched.json`, Wikipedia descriptions)
and free-text `raw_text` from the user. Compute a sentence embedding of `raw_text`
and of each site's enriched description (e.g. `sentence-transformers`,
multilingual model since input is Vietnamese), and blend cosine similarity into
`S_interest` alongside the tag-based Jaccard/partial-credit score. This captures
nuance tags can't ("chùa cổ ít khách du lịch" → prefers quiet, historic pagodas)
which pure tag-matching will always miss.

### 3.4 Diversity-aware re-ranking (MMR)

After step4 scoring, apply **Maximal Marginal Relevance** before clustering so the
candidate pool isn't dominated by 3 near-duplicate high-score sites in the same
neighborhood. This indirectly raises `preference_fit` and `schedule_balance` in
step8 because each day ends up with more varied, better-spaced sites instead of
redundant top-scorers.

---

## 4. Phase 3 — Structural / long-term

1. **Build an evaluation harness.** Keep a fixed set of ~20–50 gold itineraries
   (different personas: history buff, foodie, family with kids, elderly couple).
   Every time you change a formula or algorithm, re-run this set and compare
   `total_score` *and* a human/expert quality rating. This is what prevents Phase
   1–2 changes from just being "score inflation" — see Section 7.

2. **Feedback loop.** Add thumbs up/down per item or per itinerary in the client,
   store it, and periodically retrain the weight vector (batch job, e.g. weekly)
   instead of keeping weights static forever.

3. **Show multiple itineraries instead of one scalar-optimized one.** A single
   weighted sum forces every user into the same trade-off. Consider generating 2–3
   Pareto-different itineraries per request — "Most historical," "Most efficient
   route," "Best food" — so "the score feels low" stops being a single-number
   problem and becomes "pick the version that matches what you care about."

4. **Data quality audit.** You have 6 heritage data sources
   (`curated_heritage.json`, `crawled_heritage.json`, `deepseek_clean.json`,
   `deepseek_enriched.json`, plus restaurants). Dedup, verify coordinates, verify
   category tags, and reconcile conflicting popularity/rating numbers across these
   files. No scoring formula can score higher than what the underlying data allows —
   this is often the actual ceiling, not the weights.

---

## 5. Suggested roadmap

| Phase | Task | Effort | Files touched | Expected impact |
|---|---|---|---|---|
| 1 | Partial-credit interest similarity | S | `step2_candidates.py`, `step4_scoring.py` | Medium |
| 1 | Constraint-driven weight re-normalization | S | `step4_scoring.py` | Medium |
| 1 | Re-score distance with real OSRM time (2-pass) | S–M | `step4_scoring.py`, `step6_routing.py`, `step8_assembly.py` | Medium–High |
| 1 | Hour-level weather matching | S | `step3_weather.py`, `step4_scoring.py` | Low–Medium |
| 1 | Bayesian rating for heritage popularity | S | `step4_scoring.py` | Low |
| 2 | Merge clustering + routing (TOP model) | L | `step5_clustering.py`, `step6_routing.py`, `ttdp_solver.py` | High |
| 2 | Empirical weight tuning (grid/Bayesian/LTR) | M–L | `step4_scoring.py`, `step8_assembly.py` | High |
| 2 | Embedding-based interest matching | M | `step2_candidates.py`, `step4_scoring.py` | Medium–High |
| 2 | MMR diversity re-ranking | S–M | new module before `step5_clustering.py` | Medium |
| 3 | Evaluation harness (gold itineraries) | M | new, e.g. `eval/` | Enables everything above |
| 3 | Feedback loop + periodic retraining | L | client + new job | High (compounding) |
| 3 | Multi-itinerary Pareto output | M–L | `step8_assembly.py`, API response schema | Reframes the problem |
| 3 | Data quality audit across 6 JSON sources | M | `data/*.json` | High (raises the ceiling) |

(S = small, M = medium, L = large effort)

---

## 6. Concrete formula tweaks you can try immediately

```
# current (step4)
Score = 0.30*S_interest + 0.20*S_historical + 0.15*S_weather
      + 0.15*S_distance  + 0.10*S_popularity + 0.05*S_access + 0.05*S_budget

# suggested: dynamic weights based on explicit constraints
if "wheelchair_accessible" in constraints or "elderly_friendly" in constraints:
    w_access = 0.15   # up from 0.05
if budget_level == "low":
    w_budget = 0.15    # up from 0.05
# then re-normalize all 7 weights to sum to 1.0 before scoring
```

```
# soft interest similarity instead of strict Jaccard
CATEGORY_SIM = {
    ("history", "architecture"): 0.6,
    ("art", "museum"): 0.7,
    ("religion", "history"): 0.5,
    # ... fill in based on your category taxonomy
}
S_interest = mean(
    max(CATEGORY_SIM.get((u, c), 1.0 if u == c else 0.0) for c in site_categories)
    for u in user_interests
)
```

---

## 7. Important caution — don't just chase the number

Because `total_score` is a weighted sum of formulas you control, it's easy to
"increase" it by loosening the rubric (e.g. lowering thresholds, adding more
partial credit everywhere) without the itinerary actually getting better — this is
Goodhart's Law. Before shipping any change:

1. Keep a **fixed regression set** of representative requests + their current
   outputs, and diff scores before/after each change.
2. Cross-check with the **gold-itinerary harness** (Section 4.1) — if a change
   raises `total_score` on your regression set but *not* agreement with
   expert-curated itineraries, it's inflating the metric, not the quality.
3. Prefer changes that fix a **measurement error** (Phase 1 items — haversine vs.
   real travel time, coarse weather buckets) over changes that just **relax
   scoring criteria**.

---

## 8. Techniques to look up

- OR-Tools **Team Orienteering Problem (TOP)** / multi-vehicle OPTW
- **Learning to Rank**: LightGBM Ranker, RankNet, or plain logistic regression on your 7 existing features
- **Maximal Marginal Relevance (MMR)** for diversity-aware re-ranking
- **sentence-transformers** (multilingual model) for semantic interest matching
- **Optuna** or grid search for weight hyperparameter tuning
- **Bayesian weighted rating** (already in your `step7_restaurants.py` — reuse it)
