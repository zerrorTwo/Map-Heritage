# Vietnam Heritage Travel Recommendation System

An 8-step pipeline that generates day-by-day travel itineraries across 63 Vietnamese provinces using 830+ curated heritage sites, real-time weather data, and OR-Tools route optimization.

## Architecture

```
User Input (TripInput)
    │
    ▼
Step 1 — Input Normalizer           (step1_normalizer.py)
Step 2 — Candidate Generator        (step2_candidates.py)
Step 3 — Weather Service            (step3_weather.py)
Step 4 — Site Scorer                (step4_scoring.py)
Step 4b — MMR Diversity Re-ranker   (mmr_rerank.py)
Step 5/6 — TTDP Route Optimization  (ttdp_solver.py, step6_routing.py)
Step 7 — Day Plan Builder           (step5_clustering.py)
Step 8 — Itinerary Assembler        (step8_assembly.py)
    │
    ▼
Output (Itinerary)
```

---

## Code Structure — Pipeline Pattern

The pipeline uses a **Strategy + Chain of Responsibility** pattern. Each step is a self-contained class implementing a common interface. Steps are composed into a `PipelineRunner` that executes them in sequence — no hardcoded control flow.

### Directory Layout

```
services/ai_service/
├── pipeline.py              # Pipeline orchestrator (builds + runs step chain)
├── steps/                   # Pipeline Pattern implementation
│   ├── __init__.py
│   ├── context.py           # PipelineContext — all intermediate state
│   ├── base.py              # PipelineStep (ABC) + PipelineRunner
│   ├── step1_normalize.py   # NormalizeStep
│   ├── step2_candidates.py  # CandidateStep
│   ├── step3_weather.py     # WeatherStep
│   ├── step4_scoring.py     # ScoringStep
│   ├── step4b_mmr.py        # MMRStep
│   ├── step5_ttdp.py        # TTDPRoutingStep
│   ├── step6_geometry.py    # GeometryStep
│   ├── step7_dayplan.py     # DayPlanStep
│   └── step8_assembly.py    # AssemblyStep
├── step1_normalizer.py      # Algorithm logic (unchanged)
├── step2_candidates.py      # Algorithm logic (unchanged)
├── step3_weather.py         # Algorithm logic (unchanged)
├── step4_scoring.py         # Algorithm logic (unchanged)
├── step5_clustering.py      # Algorithm logic (unchanged)
├── step6_routing.py         # Algorithm logic (unchanged)
├── step8_assembly.py        # Algorithm logic (unchanged)
├── mmr_rerank.py            # Algorithm logic (unchanged)
├── ttdp_solver.py           # Algorithm logic (unchanged)
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
    optimized_clusters: List[List[ScoredSite]] = []  # Step 5 output
    route_geometries: List = []                   # Step 6 output
    distance_matrix: Optional[dict] = None        # Step 6 output
    day_plans: List[DayPlan] = []                 # Step 7 output
    itinerary: Optional[Itinerary] = None         # Step 8 output

    step_timings: Dict[str, float] = {}  # Performance trace
    errors: List[str] = []               # Error log
```

#### PipelineStep (`steps/base.py`)

Abstract base class. Every step must implement `execute(ctx) → ctx`.

```python
class PipelineStep(ABC):
    name: str = ""   # Display name for logging

    @abstractmethod
    async def execute(self, ctx: PipelineContext) -> PipelineContext: ...
```

#### PipelineRunner (`steps/base.py`)

Accepts a list of steps, runs them sequentially with per-step timing, error handling, and structured logging.

```python
class PipelineRunner:
    def __init__(self, steps: List[PipelineStep]): ...
    async def run(self, ctx: PipelineContext) -> PipelineContext: ...
```

### Step Composition

Steps are composed in `pipeline.py` via `_build_runner()`. This is the **only place** you modify to add, remove, or reorder steps:

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

1. **Create the step class** in `steps/stepX_feature.py`:

```python
from services.ai_service.steps.base import PipelineStep
from services.ai_service.steps.context import PipelineContext

class FeatureStep(PipelineStep):
    name = "stepX_feature"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        # Use ctx.trip_request, ctx.candidates, etc.
        # Write result to ctx (new field or existing)
        return ctx
```

2. **Add to `pipeline.py`** `_build_runner()`:

```python
return PipelineRunner(steps=[
    ...
    GeometryStep(),
    FeatureStep(),         # ← insert at desired position
    DayPlanStep(),
    ...
])
```

3. **Done.** The new step runs automatically with timing, logging, and error handling inherited from `PipelineRunner`.

### Step Independence

Each step operates on `PipelineContext` from the previous step — not on raw intermediate variables. This means:
- Steps are **order-swappable** (within logical constraints)
- Steps are **independently testable** — mock a `PipelineContext`, call `step.execute(ctx)`, assert on the result
- Steps have **no shared mutable state** outside the context

### Logging Integration

Every step automatically gets colored structured logging via `PipelineRunner`. No manual logging needed inside step classes — the runner logs step name, duration, and success/failure.

```
14:30:05  INFO    pipeline  [req:abc123] step1_normalize  OK  0ms
14:30:05  INFO    pipeline  [req:abc123] step2_candidates  OK  12ms
14:30:06  INFO    pipeline  [req:abc123] step3_weather     OK  886ms
14:30:08  INFO    pipeline  [req:abc123] step5_ttdp        OK  2020ms
14:30:09  INFO    pipeline  [req:abc123] DONE  4300ms  score=61%  id=it-abc123
14:30:09  ERROR   pipeline  [req:abc123] step3_weather FAILED  ConnectionError
```

Local terminals see ANSI-colored output. Docker/production output is JSON Lines for log aggregation.

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
If `raw_text` is provided, Step 1 extracts interests, pace, budget, constraints, province, and duration using keyword matching in both Vietnamese and English.

---

## Pipeline Steps

### Step 1 — Input Normalizer
Converts `TripInput` → `TripRequest`. Parses free-text via keyword dictionaries. Resolves province names to geographic coordinates.

### Step 2 — Candidate Generator
Filters 830 heritage sites by:
1. **Must-visit sites**: always included first (bypassed province filter)
2. **Province filter**: strict matching against `destination_provinces`
3. **Constraint filter**: `elderly_friendly`, `child_friendly`, `prefer_indoor`, `prefer_outdoor`
4. **Interest ranking**: partial-credit similarity (see below)
5. **Top-N**: returns max 30 candidates

**Partial-Credit Interest Similarity:**
Instead of strict Jaccard (`|A ∩ B| / |A|`), each user interest matches to the best site category using a 180-entry similarity matrix. For example, a user interested in `architecture` gets 0.6 credit for a site tagged `history`, rather than 0. This lifts floor scores that Jaccard was zeroing out.

```
S_interest = (1 / |interests|) * Σᵢ maxⱼ CATEGORY_SIM(interestᵢ, categoryⱼ)
```

Where `CATEGORY_SIM` maps pairs like:
- `(history, architecture)` → 0.6
- `(spiritual, pagoda)` → 0.8
- `(unesco, history)` → 0.8
- `(museum, history)` → 0.7

### Step 3 — Weather Service
Fetches hourly weather forecasts from **Open-Meteo** (free API) for the trip area:
- Temperature (°C)
- Precipitation probability (%)
- UV index
- Air quality (PM2.5, AQI) via OpenWeatherMap (optional)

Caches results by coordinate + date hash. Forecasts cover `max(duration_days, 3)` days.

### Step 4 — Site Scorer
Computes a weighted composite score (0–1) for each heritage site using **7 dimensions**.

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

### Step 4b — MMR Diversity Re-ranking
Applies **Maximal Marginal Relevance** (λ = 0.7) to diversify the candidate pool:

```
MMR(site) = λ · score(site) − (1−λ) · max_selected similarity(site, selected)
```

Similarity blends geographic proximity (60%) and category Jaccard overlap (40%), capped at 10 km. This prevents 3 near-duplicate top sites in the same neighborhood from dominating the pool.

### Step 5/6 — TTDP Route Optimization
Uses **Google OR-Tools** to solve a Team Orienteering Problem with Time Windows (OPTW):
- Input: scored sites as POIs with scores, visit durations, time windows
- N vehicles = N travel days
- Max 8h per day, 40 km/h speed
- Max 2-second solve timeout
- Falls back to top-N greedy selection if solver fails

### Step 7 — Day Plan Builder
Converts optimized route indices into `DayPlan` objects with chronological dates and `ItineraryItem` entries. Time slots are assigned starting from 08:00 each day.

### Step 8 — Itinerary Assembler
Computes final metrics with two-pass distance scoring:
- **Pass 1**: Uses OSRM real road distances (table API) when available
- **Pass 2**: Falls back to Haversine approximation + 30 km/h estimate

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

#### Route Efficiency (two-pass)
When OSRM distance matrix is available, uses real driving distances instead of Haversine, which corrects for:
- Underestimated distances in dense urban cores (Hà Nội, Hội An)
- Overestimated distances on highways

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
| `data/crawled_heritage.json` | Web-crawled heritage sites |
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

## Configuration

Environment variables (`.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OSRM_BASE_URL` | `http://localhost:5000` | OSRM routing server |
| `OPENWEATHER_API_KEY` | (empty) | OpenWeatherMap API key (optional, for air quality) |
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_DIR` | (empty) | Directory for rotating log files (JSON Lines) |
| `LOG_FILE` | `heritage.log` | Log file name when `LOG_DIR` is set |
| `AI_SERVICE_URL` | `http://localhost:8001` | AI service address (used by API gateway) |

---

## Running

```bash
pip install -r requirements.txt
docker compose up -d   # starts API gateway + AI service
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
