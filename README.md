# Vietnam Heritage Travel Recommendation System

8-step pipeline generating day-by-day itineraries across 62 Vietnamese provinces using **780 OSM-verified heritage sites**, real-time weather data, geographic clustering, and OSRM road-distance optimization.

## Architecture

```
User Input (TripInput)
    │
    ▼
Step 1 — Input Normalizer          (rule-based keyword extraction)
    │     ▼ TripRequest
Step 2 — Candidate Generator       (partial-credit category similarity + province filter)
    │     ▼ HeritageSite[]
Step 3 — Weather Service           (Open-Meteo, hourly forecasts)
    │     ▼ Forecast{}
Step 4 — Site Scorer               (7-dimension weighted composite)
    │     ▼ ScoredSite[]
Step 4b — MMR Diversity Re-ranker  (Maximal Marginal Relevance, λ=0.7)
    │     ▼ ScoredSite[] (diversified)
Step 5 — Geographic Clustering     (pace-capped, must-visit-seeded, per-day groups)
    │     ▼ List[ScoredSite][]
Step 6 — OSRM Route Optimization   (exact TSP ≤8 sites + 2-opt, island fallback)
    │     ▼ List[ScoredSite][] + geometries + distance matrix
Step 7 — Day Plan Builder          (chronological time slots)
    │     ▼ DayPlan[]
Step 8 — Itinerary Assembler       (quality scoring + multi-province summary + warnings)
    │     ▼ Itinerary (JSON)
Output
```

## Pipeline Pattern

Each step is a self-contained class implementing `execute(ctx) → ctx`. Steps are composed in `pipeline.py` via `PipelineRunner` — no hardcoded control flow. Adding a step requires only 3 changes.

```
services/ai_service/
├── pipeline.py              # Orchestrator
├── steps/                   # Pipeline pattern
│   ├── context.py           # PipelineContext (dataclass)
│   ├── base.py              # PipelineStep (ABC) + PipelineRunner
│   ├── step1_normalize.py
│   ├── step2_candidates.py
│   ├── step3_weather.py
│   ├── step4_scoring.py
│   ├── step4b_mmr.py
│   ├── step5_ttdp.py        # Geographic clustering (not TTDP)
│   ├── step6_geometry.py    # OSRM routing + island detection
│   ├── step7_dayplan.py
│   └── step8_assembly.py
├── step1_normalizer.py
├── step2_candidates.py
├── step3_weather.py
├── step4_scoring.py
├── mmr_rerank.py
├── step5_clustering.py      # partition_into_days algorithm
├── step6_routing.py         # OSRM table/route + optimize_route_open
├── step8_assembly.py        # Final assembly + quality score
└── main.py                  # FastAPI entry point
```

## Core Algorithms

### Step 2 — Partial-Credit Category Matching

Instead of strict Jaccard similarity, uses a 180-entry `CATEGORY_SIM` matrix for cross-category affinity. Example: user interest `architecture` matches site tagged `history` at 0.6 (not 0). Formula:

```
S_interest = (1/|interests|) × Σ max CATEGORY_SIM(interest, category)
```

Must-visit sites bypass all filters. Province filter is strict (no radius fallback).

### Step 4 — 7-Dimension Scoring

Base weights: interest_match 0.30, historical_importance 0.20, weather 0.15, distance 0.15, popularity 0.10, accessibility 0.05, budget 0.05. Dynamic re-weighting when constraints are specified (accessibility/budget boosted to 0.15).

Key innovations:
- **Derived popularity/historical** from category signals (UNESCO → +0.25 pop, +0.30 hist)
- **Logarithmic distance decay**: `max(0.15, 1.0/(1.0 + dist_km/20.0))` — gentler than linear
- **Hour-level weather matching** — uses the exact visit hour, not daily averages

### Step 4b — MMR Diversity

Maximal Marginal Relevance (Carbonell & Goldstein, 1998) with λ=0.7. Blended similarity: 60% geographic proximity + 40% Jaccard category overlap. Prevents top-scoring sites from clustering in one neighborhood.

### Step 5 — Geographic Day Clustering

Replaced the original OR-Tools TTDP solver. Algorithm (`partition_into_days`):
1. Distribute must-visit sites across days (round-robin by geographic order)
2. Fill empty days with farthest-point recommended seeds
3. Assign remaining sites to nearest non-full day (MMR order) capped by pace (relaxed=3, moderate=5, packed=7)
4. Ensure `duration_days` clusters returned (empty trailing days OK)

### Step 6 — OSRM Road Optimization

**Route ordering** (`optimize_route_open`): Exact permutation search for ≤8 sites/day (5,040 permutations at 7 sites), nearest-neighbor + 2-opt for larger clusters. Anchors are fixed outside the permutation.

**Geometry**: Polyline from OSRM route API, intra-day only (cross-day connectors excluded from visual display). Clusters spanning >150 km consecutive pairs (e.g., mainland→island) fall back to straight-line geometry.

**Island detection**: Consecutive site pairs >150 km apart flag `island_route` warning in the response.

### Step 8 — Quality Scoring

```
quality = 0.25 × avg_site_score
        + 0.20 × route_efficiency    (1 − dist_per_day / cap, cap = 100 × √province_count)
        + 0.15 × weather_fit
        + 0.15 × preference_fit
        + 0.10 × food_score
        + 0.10 × schedule_balance
        + 0.05 × budget_fit
```

Route efficiency cap scales with province count: 1 province → 100 km/day, 4 provinces → 200 km/day.

## Data

**780 verified heritage sites** across 62 provinces (`services/ai_service/curated_data.py`). Each site has OSM-verified coordinates, categories (history/nature/spiritual/architecture/museum/unesco/craft_village/entertainment), scores, opening hours, ticket prices, and Vietnamese descriptions.

## Running

```bash
pip install -r requirements.txt
docker compose up -d --build    # API gateway + AI service + OSRM (public)
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/trips/recommend` | Generate itinerary |
| `GET`  | `/api/v1/heritage-sites` | List all 780 sites |
| `GET`  | `/api/v1/health` | Health check |
| `GET`  | `/docs` | Swagger UI |

### Example

**Request:**
```json
{
  "destination_provinces": ["Hà Nội", "Ninh Bình"],
  "duration_days": 3,
  "interests": ["history", "architecture"],
  "pace": "moderate"
}
```

**Response:**
```json
{
  "itinerary_id": "it-a1b2c3d4e5f6",
  "summary": "Chuyến du lịch 3 ngày tại Hà Nội, Ninh Bình. Khám phá 15 di sản. Chất lượng hành trình: 68%",
  "total_score": 0.6832,
  "total_distance_km": 120.5,
  "warnings": [],
  "days": [...],
  "route_geometries": [...]
}
```

## Testing

```bash
python -m pytest tests/ -v    # 532 tests across 11 test files
```
