# Vietnam Heritage Travel Recommendation System

An 8-step pipeline that generates day-by-day travel itineraries across 63 Vietnamese provinces using 830+ curated heritage sites, real-time weather data, OR-Tools route optimization, and OSRM road-distance reordering.

## Architecture

```
User Input (TripInput)
    │
    ▼
Step 1 — Input Normalizer           (rule-based keyword matching)
    │     ▼ TripRequest
Step 2 — Candidate Generator        (partial-credit category similarity + province filter)
    │     ▼ HeritageSite[]
Step 3 — Weather Service            (Open-Meteo free API, hourly forecasts)
    │     ▼ Forecast{}
Step 4 — Site Scorer                (7-dimension weighted composite, dynamic re-weighting)
    │     ▼ ScoredSite[]
Step 4b — MMR Diversity Re-ranker   (Maximal Marginal Relevance, λ=0.7)
    │     ▼ ScoredSite[] (diversified)
Step 5 — TTDP Day Partitioning      (OR-Tools OPTW solver, haversine distances)
    │     ▼ List[ScoredSite][] (per-day clusters)
Step 6 — OSRM Route Reordering      (1 table + 2-opt open-path per day, anchor-aware)
    │     ▼ List[ScoredSite][] (road-ordered) + route geometries + distance matrix
Step 7 — Day Plan Builder           (chronological day plans with time slots)
    │     ▼ DayPlan[]
Step 8 — Itinerary Assembler        (7-dimension quality score + OSRM distances + budget fit)
    │     ▼ Itinerary
Output (JSON)
```

---

## Code Structure — Pipeline Pattern

The pipeline uses a **Strategy + Chain of Responsibility** pattern. Each step is a self-contained class implementing a common interface. Steps are composed into a `PipelineRunner` that executes them in sequence — no hardcoded control flow.

### Directory Layout

```
services/ai_service/
├── pipeline.py              # Pipeline orchestrator (builds + runs step chain)
├── steps/                   # Pipeline Pattern implementation
│   ├── context.py           # PipelineContext — all intermediate state
│   ├── base.py              # PipelineStep (ABC) + PipelineRunner
│   ├── step1_normalize.py   # NormalizeStep
│   ├── step2_candidates.py  # CandidateStep
│   ├── step3_weather.py     # WeatherStep
│   ├── step4_scoring.py     # ScoringStep
│   ├── step4b_mmr.py        # MMRStep
│   ├── step5_ttdp.py        # TTDPRoutingStep
│   ├── step6_geometry.py    # GeometryStep (OSRM reordering + geometry)
│   ├── step7_dayplan.py     # DayPlanStep
│   └── step8_assembly.py    # AssemblyStep
├── step1_normalizer.py      # Free-text parsing with keyword dictionaries
├── step2_candidates.py      # Candidate filtering + interest similarity
├── step3_weather.py         # Open-Meteo API client
├── step4_scoring.py         # 7-dimension weighted scoring engine
├── mmr_rerank.py            # Maximal Marginal Relevance re-ranker
├── ttdp_solver.py           # OR-Tools OPTW solver (Tourist Trip Design)
├── step6_routing.py         # OSRM table/route API + open-path route optimizer
├── step5_clustering.py      # Geographic day clustering (fallback)
├── step8_assembly.py        # Final itinerary assembly + quality scoring
└── main.py                  # FastAPI app entry point
```

### Core Abstractions

#### PipelineContext (`steps/context.py`)

Dataclass holding all state that flows between steps. Every step reads from and writes to the same context.

```python
@dataclass
class PipelineContext:
    input: TripInput                  # Raw user input
    request_id: str = ""              # Correlation ID for tracing

    trip_request: Optional[TripRequest] = None    # Step 1 output
    candidates: List[HeritageSite] = []           # Step 2 output
    forecasts: Dict[str, List[Forecast]] = {}     # Step 3 output
    scored_sites: List[ScoredSite] = []           # Step 4 output
    optimized_clusters: List[List[ScoredSite]] = []  # Step 5 output, reordered by Step 6
    route_geometries: List = []                   # Step 6 output
    distance_matrix: Optional[dict] = None        # Step 6 output (block-diagonal OSRM)
    day_plans: List[DayPlan] = []                 # Step 7 output
    itinerary: Optional[Itinerary] = None         # Step 8 output

    step_timings: Dict[str, float] = {}  # Performance trace
    errors: List[str] = []               # Error log
```

#### PipelineStep (`steps/base.py`)

Abstract base class. Every step must implement `execute(ctx) → ctx`.

#### PipelineRunner (`steps/base.py`)

Accepts a list of steps, runs them sequentially with per-step timing, error handling, and structured logging.

### Step Composition

Steps are composed in `pipeline.py` via `_build_runner()`:

```python
def _build_runner(self) -> PipelineRunner:
    return PipelineRunner(steps=[
        NormalizeStep(),
        CandidateStep(sites_cache=self._sites_cache),
        WeatherStep(),
        ScoringStep(),
        MMRStep(lambd=0.7),
        TTDPRoutingStep(speed_kmh=40.0, time_limit_sec=2),
        GeometryStep(),
        DayPlanStep(),
        AssemblyStep(),
    ])
```

### Adding a New Step

No changes to existing code. Just 3 actions:

1. Create the step class in `steps/stepX_feature.py`
2. Add to `pipeline.py` `_build_runner()`
3. Done — timing, logging, and error handling are inherited

---

## Input Specification

### API Endpoint (TripInput)

The system accepts both structured form input and free-text natural language input.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `raw_text` | string | no | — | Free-text description (e.g. "Tôi muốn đi Hà Nội 3 ngày, thích lịch sử") |
| `destination_area` | string | no | `"Hà Nội"` | Target destination city/province name |
| `destination_provinces` | string[] | no | from destination_area | Exact province names to filter by |
| `start_date` | string | no | `""` | Start date YYYY-MM-DD |
| `end_date` | string | no | `""` | End date YYYY-MM-DD |
| `duration_days` | int | no | `1` | Number of travel days |
| `number_of_people` | int | no | `1` | Group size |
| `interests` | string[] | no | `["history","local_food"]` | Interest tags |
| `pace` | string | no | `"moderate"` | Travel pace: `relaxed` / `moderate` / `packed` |
| `travel_mode` | string | no | `"mixed"` | Transport mode |
| `budget_level` | string | no | `"medium"` | Budget: `low` / `medium` / `high` |
| `constraints` | string[] | no | `[]` | Accessibility: `elderly_friendly`, `child_friendly`, `avoid_long_walking`, `prefer_indoor`, `prefer_outdoor` |
| `must_visit_site_ids` | string[] | no | `[]` | Force-include these site IDs |
| `start_lat` / `start_lng` | float | no | City centroid | Start location |
| `end_lat` / `end_lng` | float | no | start_lat/lng | End location |

### Supported Interest Tags
`history`, `architecture`, `spiritual`, `craft_village`, `museum`, `local_food`, `nature`, `photography`

### Free-Text Parsing (Vietnamese + English)
If `raw_text` is provided, Step 1 extracts interests, pace, budget, constraints, province, and duration using bilingual keyword matching dictionaries.

---

## Pipeline Steps — Detailed

---

### Step 1 — Input Normalizer

**File:** `step1_normalizer.py` · **Algorithm:** Rule-based keyword extraction

**What it uses:** 5 keyword dictionaries (68 interest keywords, 12 pace keywords, 11 budget keywords, 14 constraint keywords, 27 province keywords) covering Vietnamese and English. Regex for duration extraction (`\d+\s*ngày`, `\d+\s*days?`). `unicodedata` NFKD normalization for diacritic-insensitive province matching.

**Why this approach:** Rule-based keyword matching is deterministic, fast (sub-millisecond), requires no LLM inference cost for structured form input, and handles the most common Vietnamese travel phrases. More complex free-text inputs fall through to structured defaults.

**Fallback:** Unknown provinces remain as-is; missing fields default to `"Hà Nội"`, 2 days, `"moderate"` pace.

---

### Step 2 — Candidate Generator

**File:** `step2_candidates.py` · **Algorithm:** Partial-credit category similarity with filtering

**What it uses:** 180-entry `CATEGORY_SIM` matrix mapping cross-category relationships. Province fuzzy matching with NFKD normalization. Must-visit bypass that skips province/constraint filters.

**Why partial credit over Jaccard:** Strict Jaccard (`|A ∩ B| / |A|`) floors to 0 when user interests and site categories share no exact tag — e.g. a user interested in `architecture` gets 0 for a site tagged only `history`. Partial-credit assigns 0.6, which prevents high-quality sites from being excluded during early filtering.

**Similarity formula:**

```
S_interest = (1 / |interests|) * Σᵢ maxⱼ CATEGORY_SIM(interestᵢ, categoryⱼ)
```

Where `CATEGORY_SIM` maps pairs like:
| Pair | Score |
|------|-------|
| `(history, architecture)` | 0.6 |
| `(spiritual, pagoda)` | 0.8 |
| `(unesco, history)` | 0.8 |
| `(museum, history)` | 0.7 |

**Constraint filtering:** `elderly_friendly` requires `suitable_for_elderly=True` and `indoor_score > 0.3`; `child_friendly` requires `suitable_for_children=True`; `avoid_long_walking` requires `indoor_score > 0.5`.

**Output:** Up to 30 candidates, with must-visit sites prepended.

---

### Step 3 — Weather Service

**File:** `step3_weather.py` · **Algorithm:** Multi-source weather aggregation with TTL cache

**What it uses:** **Open-Meteo** free API (no API key) for temperature, precipitation, UV index. Optional **OpenWeatherMap** for PM2.5 and AQI. Coordinate-keyed LRU cache with `weather_cache_ttl=3600` (1 hour).

**Why Open-Meteo:** Free, no API key required, global coverage, returns hourly forecasts up to 16 days. No rate limits on the free tier. OpenWeatherMap is optional and only used for air quality enrichment.

**Coverage:** Fetches `max(duration_days, 3)` days of forecasts. For a 5-day trip, this means 5 days × 24 hours = 120 data points per location.

---

### Step 4 — Site Scorer

**File:** `step4_scoring.py` · **Algorithm:** 7-dimension weighted composite scoring with dynamic weight re-normalization

**What it uses:** Partial-credit interest matching (from Step 2), derived popularity/historical scores from category heuristics, hour-level weather penalties, logarithmic distance decay, accessibility scoring from indoor_score + visit duration + constraints, budget fit from ticket_price vs budget_level thresholds.

#### Base Weights

| Dimension | Weight | Source |
|-----------|--------|--------|
| Interest match | 0.30 | Partial-credit category similarity |
| Historical importance | 0.20 | Derived from categories + province tier |
| Weather suitability | 0.15 | Hour-level forecast matching |
| Distance | 0.15 | Logarithmic distance decay |
| Popularity | 0.10 | Derived from categories + province tier |
| Accessibility | 0.05 | Indoor score + visit duration + constraints |
| Budget fit | 0.05 | Ticket price vs budget level |

#### Dynamic Weight Re-normalization

When the user explicitly requests accessibility or budget constraints, corresponding weights are boosted and all weights re-normalized to sum to 1.0:

| Trigger | Boost |
|---------|-------|
| `elderly_friendly` or `child_friendly` in constraints | accessibility: 0.05 → 0.15 |
| `budget_level = "low"` | budget: 0.05 → 0.15 |

**Why dynamic weights:** A user who explicitly requests `elderly_friendly` should have accessibility disproportionately affect their results. Without dynamic weights, accessibility contributes only 5% to the final score, making it effectively irrelevant.

#### Derived Popularity (0.45–0.95 range)

```
popularity = 0.45
  + 0.25  if unesco
  + 0.10  if museum
  + 0.08  if history
  + 0.08  if architecture
  + 0.05  if craft_village
  + 0.05  if entertainment
  + 0.04  if spiritual
  + 0.04  if nature
  + 0.04  if has description
  + 0.03  if has visit_tips
  + 0.02  if has reference_url
  + PROVINCE_TIER[province]  (0.01–0.08)
→ capped at 0.95
```

#### Derived Historical Importance (0.45–0.95 range)

```
historical = 0.45
  + 0.30  if unesco
  + 0.15  if history
  + 0.10  if museum
  + 0.08  if architecture
  + 0.05  if spiritual
  + 0.03  if craft_village
  + 0.02  if has long_description
  + PROVINCE_TIER[province]  (0.01–0.08)
→ capped at 0.95
```

**Why derived scores:** Curated sites have `popularity_score` and `historical_importance_score` fields, but crawled/OSM-imported sites may lack them. The derived formulas provide a consistent baseline from available category data, then cap at 0.95 to avoid saturating the scoring dimension.

#### Province Tier Bonus

Provinces are ranked by tourism prominence:

| Tier | Bonus | Provinces |
|------|-------|-----------|
| Tier 1 | +0.08 | Hà Nội, Huế, Quảng Nam (Hội An) |
| Tier 2 | +0.06 | TP. Hồ Chí Minh, Đà Nẵng |
| Tier 3 | +0.05 | Ninh Bình, Quảng Ninh |
| Tier 4 | +0.04 | Hải Phòng, Khánh Hòa, Lào Cai, Hà Giang, Lâm Đồng |
| Tier 5 | +0.03 | Cần Thơ, Bình Định, Thanh Hóa, Nghệ An, Bắc Ninh |
| Default | +0.02 | All other provinces |

#### Hour-Level Weather Matching

Uses the forecast hour closest to the itinerary visit time (not daily average):

| Condition | Penalty |
|-----------|---------|
| Rain > 70% + outdoor | −0.35 |
| Rain 50–70% + outdoor | −0.15 |
| Temp > 35°C + outdoor | −0.25 |
| Temp 32–35°C + outdoor | −0.10 |
| UV > 8 (11:00–14:00) | −0.20 |
| UV > 6 (11:00–15:00) | −0.10 |
| Temp < 10°C + outdoor | −0.15 |
| Temp 10–15°C + outdoor | −0.05 |

Indoor sites (outdoor_score ≤ 0.6) are exempt from rain/temperature penalties.

**Why hour-level matching:** A site scheduled at 08:00 should not inherit a "poor" weather penalty caused by a 14:00 thunderstorm. Daily averages obscure this.

#### Logarithmic Distance Score

```
dist_score = max(0.15, 1.0 / (1.0 + dist_km / 20.0))
```

| Distance | Score (log) | Score (linear, old) |
|----------|-------------|---------------------|
| 0 km | 1.00 | 1.00 |
| 5 km | 0.80 | 0.95 |
| 10 km | 0.67 | 0.90 |
| 20 km | 0.50 | 0.80 |
| 60 km | 0.25 | 0.40 |
| Floor | 0.15 | 0.00 |

**Why logarithmic:** Linear decay (e.g. `1 − dist/max_dist`) penalizes nearby sites too harshly. A site 5 km away is nearly as accessible as one 1 km away in a driving context. Logarithmic decay has a steep initial drop (0→10 km) then flattens, matching real-world drivability.

#### Accessibility Score

```
accessibility = 0.50
  + 0.25 * indoor_score
  + visit_bonus  (≤30min: +0.10, ≤60min: +0.08, ≤90min: +0.05)
  + constraint_bonuses
  + (0.08 if no constraints)
```

Constraint bonuses (always additive):
- `elderly_friendly`: +0.05 if indoor_score > 0.4, +0.05 if ≤ 60 min
- `child_friendly`: +0.05 if ≤ 60 min
- `avoid_long_walking`: +0.10 if indoor_score > 0.5, −0.05 otherwise

#### Budget Fit

```
budget_fit = 1.0                              if ticket_price == 0
           = 0.2                               if ticket_price ≥ threshold
           = 1.0 − (price − lo) / (hi − lo)   otherwise
```
Thresholds: low: 30,000 VND, medium: 100,000 VND, high: 1,000,000 VND

---

### Step 4b — MMR Diversity Re-ranking

**File:** `mmr_rerank.py` · **Algorithm:** Maximal Marginal Relevance (Carbonell & Goldstein, 1998)

**What it uses:** Greedy selection with λ = 0.7 (70% relevance, 30% diversity). Blended similarity: 60% geographic proximity (capped at 10 km) + 40% Jaccard category overlap.

```
MMR(site) = λ · score(site) − (1−λ) · max_selected similarity(site, selected)
```

**Why MMR:** Without diversity re-ranking, the top 3 scoring sites are often in the same neighborhood (e.g. Văn Miếu, Hoàng Thành, and Hồ Gươm are all within 2 km in central Hà Nội). MMR pushes lower-scoring but geographically diverse sites (e.g. Bát Tràng pottery village, 15 km away) into the pool. This indirectly improves `schedule_balance` and `route_efficiency` in Step 8 because each day ends up with better-spaced sites.

**Why λ = 0.7:** Empirically chosen to balance relevance-diversity for 3–7 sites/day. Higher λ (>0.8) produces near-identical results to no MMR; lower λ (<0.5) over-diversifies and excludes genuinely good sites.

---

### Step 5 — TTDP Day Partitioning (Selection + Initial Ordering)

**File:** `ttdp_solver.py`, `step5_ttdp.py` · **Algorithm:** Team Orienteering Problem with Time Windows (OPTW) via Google OR-Tools

**What it uses:** OR-Tools Routing Solver with `PATH_CHEAPEST_ARC` initial construction, `GUIDED_LOCAL_SEARCH` metaheuristic, and disjunction penalties for optional POIs. Distance matrix computed via vectorized haversine in NumPy.

**Problem formulation:**

The Tourist Trip Design Problem (TTDP) is modeled as an **Orienteering Problem with Time Windows (OPTW):**
- **Nodes:** 0 = start anchor (trip origin), 1 = end anchor, 2..N+1 = candidate POIs
- **N vehicles** = N travel days, each starting at node 0 and ending at node 1
- **Objective:** Maximize total collected score across all days
- **Constraints:** Each day ≤ 8 hours; each POI ≤ 1 visit; time windows respected
- **Penalty:** `score × 1,000,000` for skipping a POI (higher score → higher cost of omission)

**Why OR-Tools:** OR-Tools provides battle-tested constraint programming with built-in local search metaheuristics. The Routing library handles disjunctions (optional nodes), time windows, and multi-vehicle (multi-day) configurations out of the box. Alternatives like a custom genetic algorithm or simulated annealing would require significant tuning for comparable quality.

**Why haversine at this stage:** Step 5 needs to rapidly explore which POIs go to which day — a combinatorial selection problem, not a precision routing problem. Haversine is O(1) per pair, runs entirely in-process, and provides enough accuracy to partition POIs across days. Road-distance precision is applied in Step 6 after the day assignment is fixed.

**Time limit:** 2 seconds (configurable via `TTDPRoutingStep(time_limit_sec=N)`). GLS converges quickly for typical 15–30 POIs across 3–5 days. A larger time budget would improve the optimum marginally but the dominant quality gain comes from Step 6's road-distance reordering.

**Fallback:** If OR-Tools fails (e.g. impossible time windows), falls back to top-N greedy selection sorted by score.

---

### Step 6 — OSRM Road-Distance Reordering

**File:** `step6_routing.py`, `step6_geometry.py` · **Algorithm:** Anchor-aware open-path TSP with exact search (`≤8` sites) or nearest-neighbor + 2-opt heuristic, optimized on OSRM road durations

**What it uses:** OSRM table API for directed road-travel durations between all site pairs + anchors; OSRM route API for polyline geometry. `lru_cache` (512 entries) for table results. `asyncio.to_thread` for non-blocking network I/O.

**Why this step exists:** Step 5's TTDP solver optimizes *which* sites go to *which* day using haversine (straight-line) distances. But a site across a river or behind a mountain may be 500 m away as the crow flies and 5 km by road. Step 6 reorders each day's fixed set of POIs to minimize actual road travel time using real OSRM driving durations.

**Algorithm — `optimize_route_open()`:**

1. **Single OSRM table request per day** includes all applicable anchors: `[start_anchor?, site_1, ..., site_n, end_anchor?]`. Every directed pair has the same road-duration unit — no haversine-to-seconds conversion.

2. **Anchors are fixed outside the site permutation.** The cost of a site order is:
   ```
   cost = duration(start → first_site)
        + Σ duration(site_i → site_{i+1})
        + duration(last_site → end)
   ```
   Only the site order is permuted; anchors remain at fixed positions 0 and N+1.

3. **Exact search** for ≤ 8 sites: evaluates all `n!` permutations (max 40,320 for n=8). Uses `itertools.permutations` with direct cost computation.

4. **Heuristic** for > 8 sites: multi-start nearest-neighbor (each site as potential first stop) followed by 2-opt local search on the open path. The cheapest candidate across all starts is selected.

5. **Matrix validation:** Rejects non-square, NaN, infinite, or mismatched OSRM matrices. On any failure, preserves the TTDP order exactly — no haversine replacement.

**Why exact search for ≤ 8:** Typical daily itineraries have 3–7 POIs. Exhaustive search over 7! = 5,040 permutations is instantaneous (~1 ms) and guarantees optimality. Beyond 8 sites/day, the heuristic is used.

**Why open-path 2-opt:** Standard TSP 2-opt assumes a closed tour (last → first). Day itineraries are open paths (start → sites → end). The open-path variant evaluates only `n−1` edges and excludes the wrap-around edge.

**Distance matrix for Step 8:** Per-day OSRM distance matrices are assembled into a block-diagonal global matrix. Cross-day entries remain NaN → Step 8 falls back to haversine for inter-day distances (which are never consecutive itinerary items). This avoids a redundant global OSRM table request.

**Duration validation:** After reordering, total road duration + visit durations are compared against the 8-hour daily budget. Over-budget days are logged as warnings (not errors — the itinerary is still usable).

**Geometry:** Polyline coordinates are fetched from OSRM route API *after* reordering, so the drawn route follows the optimized order.

---

### Step 7 — Day Plan Builder

**File:** `step7_dayplan.py`, `step5_clustering.py` · **Algorithm:** Chronological day plan construction with geographic fallback

**What it uses:** The optimized clusters from Step 5/6 (already ordered by road distance). Time slots start at 08:00 and increment based on travel time (from OSRM distances when available) + visit durations. Pacing limits: `relaxed` = 3 sites/day, `moderate` = 5, `packed` = 7.

**Fallback clustering** (`step5_clustering.py`): If TTDP fails and top-N greedy is used, sites are split across days via geographic round-robin by latitude. Must-visit sites are distributed evenly as seeds, then remaining sites are assigned to the nearest day centroid.

**Why round-robin by latitude:** Simple, deterministic, and produces geographically compact day groups without requiring sklearn KMeans. For most Vietnamese provinces with a clear north-south layout, latitude sorting produces natural day boundaries.

---

### Step 8 — Itinerary Assembler

**File:** `step8_assembly.py` · **Algorithm:** 7-dimension weighted quality scoring with two-pass distance computation

**What it uses:** Real OSRM road distances from the block-diagonal matrix (Step 6), with haversine fallback for any NaN/None entries. Restaurant insertion (not yet active). Budget fit from actual ticket prices. Vietnamese summary generation.

#### Quality Score (0–1)

```
quality = 0.25 × avg_site_score
        + 0.20 × route_efficiency        (1 − dist_per_day / 100km)
        + 0.15 × weather_fit             (avg weather suitability)
        + 0.15 × preference_fit          (avg interest match)
        + 0.10 × food_score              (restaurants / max(1, days×3))
        + 0.10 × schedule_balance        (1 − (max_items − min_items) / max_items)
        + 0.05 × budget_fit              (from ticket prices average)
```

**Two-pass distance scoring:**

- **Pass 1 (OSRM):** `_lookup_distance()` queries the block-diagonal matrix for consecutive same-day item pairs. Returns real driving distance in meters. Invalid/missing entries (NaN, >999999) return None.
- **Pass 2 (Haversine):** `haversine(lat1, lng1, lat2, lng2)` fallback for any cross-day or unavailable entry.

Both passes contribute to `total_distance` in `total_distance_km`, ensuring the quality score reflects all distances regardless of OSRM availability for individual days.

**Distance display:** Default travel time estimate: `distance_m / 500` minutes (approximately 30 km/h in urban areas). When OSRM real distance is available, it replaces the haversine value in the output.

---

## Output Specification

### Itinerary

```json
{
  "itinerary_id": "it-a1b2c3d4e5f6",
  "summary": "Chuyến du lịch 3 ngày tại Hà Nội. Khám phá 9 di sản và 6 nhà hàng. Chất lượng hành trình: 78%",
  "total_score": 0.7832,
  "total_distance_km": 45.30,
  "days": [
    {
      "day": 1,
      "date": "2026-07-06",
      "items": [
        {
          "time": "08:00-09:30",
          "type": "heritage",
          "ref_id": "hn-001",
          "name": "Văn Miếu - Quốc Tử Giám",
          "reason": "Score: 0.94 | Interest match: 100%",
          "travel_from_previous_minutes": 0,
          "distance_from_previous_m": 0.0
        }
      ]
    }
  ],
  "route_geometries": [[[105.85, 21.03], [105.84, 21.03]]]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `itinerary_id` | string | Unique 12-char hex ID |
| `summary` | string | Vietnamese one-line summary |
| `total_score` | float | Quality score (0–1), higher = better |
| `total_distance_km` | float | Total route distance in km |
| `days[]` | DayPlan[] | One per travel day |
| `days[].day` | int | Day number (1-indexed) |
| `days[].date` | string | Date YYYY-MM-DD |
| `days[].items[]` | ItineraryItem[] | Ordered stops |
| `days[].items[].time` | string | Time slot HH:MM-HH:MM |
| `days[].items[].type` | string | `"heritage"` or `"restaurant"` |
| `days[].items[].ref_id` | string | Site/restaurant ID |
| `days[].items[].name` | string | Display name |
| `days[].items[].reason` | string | Scoring breakdown |
| `days[].items[].travel_from_previous_minutes` | int | Travel time from previous stop |
| `days[].items[].distance_from_previous_m` | float | Distance from previous stop (meters) |
| `route_geometries[]` | float[][][] | GeoJSON LineString coords per day |

---

## Data Sources

| File | Contents |
|------|----------|
| `data/curated_heritage.json` | 830+ sites across 63 provinces |
| `data/curated_restaurants.json` | Curated restaurant data |
| `data/crawled_heritage.json` | Web-crawled heritage sites (370 entries) |
| `data/deepseek_clean.json` | AI-cleaned heritage data |
| `data/deepseek_enriched.json` | AI-enriched site descriptions |
| `data/geocode_cache.json` | Nominatim geocoding results |

### Heritage Site Categories (8 types)
`history`, `nature`, `spiritual`, `architecture`, `entertainment`, `museum`, `unesco`, `craft_village`

---

## Scoring Distribution (Benchmark)

Measured across 214 scored sites over 10 trip configurations:

| Stat | Value |
|------|-------|
| Mean site score | 0.70 |
| Median | 0.70 |
| Std deviation | 0.13 |
| P25–P75 | 0.61–0.78 |
| P90 | 0.86 |
| Max | 0.94 |

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Individual test files
python tests/test_heritage_model.py         # 16 model validation tests
python tests/test_heritage_position.py      # 12 coordinate/position tests
python tests/test_heritage_data_quality.py  # 14 data quality tests
python tests/test_heritage_route_position.py # 10 route anchor tests
python tests/test_road_routing.py           # 6 routing optimizer tests
python tests/test_phase1_enhancements.py    # 105 scoring formula tests
python tests/test_all_input_fields.py       # 53 input normalizer tests
python tests/test_logging.py                # 50 logging tests
python tests/test_province_fix.py           # 40 province normalization tests
python tests/test_all_provinces.py          # 226 province coverage tests
```

Total: **532 tests** across 11 test files.

---

## Configuration

Environment variables (`.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OSRM_BASE_URL` | `http://localhost:5000` | OSRM routing server |
| `OPENWEATHER_API_KEY` | (empty) | OpenWeatherMap API key (optional, for air quality) |
| `DEFAULT_CANDIDATE_LIMIT` | `30` | Max candidates per query |
| `MAX_DAILY_HOURS` | `10` | Max active hours per day |
| `MAX_SOLVE_TIMEOUT` | `5.0` | Max OR-Tools solve time (seconds) |
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_DIR` | (empty) | Directory for rotating log files (JSON Lines) |
| `LOG_FILE` | `heritage.log` | Log file name when `LOG_DIR` is set |
| `AI_SERVICE_URL` | `http://localhost:8001` | AI service address (used by API gateway) |
| `ROUTE_CACHE_TTL` | `86400` | OSRM result cache TTL (seconds) |
| `WEATHER_CACHE_TTL` | `3600` | Weather forecast cache TTL (seconds) |
| `CANDIDATE_CACHE_TTL` | `86400` | Candidate site cache TTL (seconds) |

---

## Running

```bash
pip install -r requirements.txt
docker compose up -d   # starts API gateway + AI service + OSRM
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/trips/recommend` | Generate heritage travel itinerary |
| `POST` | `/api/v1/recommend` | Alias for `/api/v1/trips/recommend` |
| `POST` | `/api/v1/routes/plan` | Plan a fixed start/end route |
| `GET`  | `/api/v1/heritage-sites` | List all heritage sites |
| `GET`  | `/api/v1/heritage-sites/{id}` | Get site detail |
| `GET`  | `/api/v1/heritage-sites/{id}/images` | Get site images |
| `GET`  | `/api/v1/heritage-sites/{id}/reviews` | Get site reviews |
| `GET`  | `/api/v1/heritage-sites/{id}/enrich` | Get enriched description |
| `GET`  | `/api/v1/heritage-sites/{id}/narrate` | Get site narration |
| `GET`  | `/api/v1/health` | Health check |
| `GET`  | `/docs` | Swagger UI |

### Example Request

```json
{
  "destination_provinces": ["Hà Nội"],
  "duration_days": 3,
  "interests": ["history", "architecture"],
  "pace": "moderate",
  "constraints": ["elderly_friendly"],
  "start_date": "2026-07-10"
}
```

### Example Response

```json
{
  "itinerary_id": "it-a1b2c3d4e5f6",
  "summary": "Chuyến du lịch 3 ngày tại Hà Nội. Khám phá 9 di sản và 6 nhà hàng. Chất lượng hành trình: 78%",
  "total_score": 0.7832,
  "total_distance_km": 45.30,
  "days": [...],
  "route_geometries": [...]
}
```

### Logging

- **Local dev** (TTY terminal): colored ANSI output with step timings
- **Production / Docker** (non-TTY): JSON Lines format for log aggregation (ELK, Grafana, etc.)
- **File logging**: set `LOG_DIR=/app/logs` to enable rotating file output (10 MB per file, 5 backups)
- Every request gets an `X-Request-ID` header for traceability across services
