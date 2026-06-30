# SPEC: Heritage Itinerary & Shortest Route Planner

> Purpose: this document is written as a structured specification intended to be read and implemented by an LLM/coding agent. It defines exact input schema, decision rules, algorithm steps, and output schema. No information is implied — everything needed to implement is stated explicitly.

---

## 1. System Goal

Given a set of heritage/tourist sites, a fixed start point, and a fixed end point, produce:
1. The optimal **visiting order** of the sites (between start and end).
2. The actual **road route** (turn-by-turn) connecting them in that order.
3. A structured **itinerary** (times, distances, durations) ready to render in a UI.

This is two sub-problems chained together:

```
Problem A: Sequencing  = Open-Path TSP (start fixed, end fixed, order of middle nodes is the unknown)
Problem B: Routing     = Shortest Path between two fixed points on a real road graph (Dijkstra / A* / production routing engine)
```

---

## 2. Input Schema

Use this exact JSON shape as the contract between frontend and backend:

```json
{
  "province": "string (e.g. 'Hue')",
  "sites": [
    { "id": "string", "name": "string", "lat": 0.0, "lng": 0.0,
      "open_time": "HH:MM", "close_time": "HH:MM",
      "visit_duration_min": 60 }
  ],
  "start": { "id": "string|null", "lat": 0.0, "lng": 0.0, "label": "string" },
  "end":   { "id": "string|null", "lat": 0.0, "lng": 0.0, "label": "string" },
  "transport_mode": "driving | motorbike | walking | transit",
  "trip_date": "YYYY-MM-DD",
  "available_window": { "start_time": "HH:MM", "end_time": "HH:MM" },
  "num_days": 1,
  "constraints": {
    "avoid_highways": false,
    "avoid_tolls": false,
    "max_total_distance_km": null,
    "max_total_duration_min": null
  }
}
```

### Field rules
| Field | Required | Validation rule |
|---|---|---|
| `sites` | yes | length ≥ 0; if empty, system just returns start→end shortest path |
| `start` | yes | must resolve to valid `lat`/`lng` (geocode if only `label` given) |
| `end` | yes | same as `start`; if `end == start`, treat as round trip |
| `transport_mode` | yes | must map to a routing profile (see §4.1) |
| `num_days` | no | default 1; if > 1, trigger clustering step (§4.4) before sequencing |
| `available_window` | no | if present, used to check feasibility in §4.5 |

If any required field is missing → reject the request and return a validation error listing missing fields. Do not silently guess values.

---

## 3. Decision Rules (read top to bottom, first match wins)

```
IF sites.length == 0:
    → run Routing only (Dijkstra/A* or routing engine) from start to end. DONE.

IF end == start:
    → mode = ROUND_TRIP_TSP

ELSE:
    → mode = OPEN_PATH_TSP   (start fixed at position 0, end fixed at last position)

IF num_days > 1:
    → run CLUSTERING step first (§4.4), producing day_1..day_n site groups
    → run sequencing (§4.2) separately per day group
    → ELSE → run sequencing once on the full site list

IF sites.length <= 12:
    → sequencing_algorithm = "held_karp_exact"
ELSE:
    → sequencing_algorithm = "or_tools_routing"   (heuristic, supports constraints)
```

---

## 4. Algorithm Pipeline (execute steps in this exact order)

### 4.1 Step 1 — Geocode & normalize
- For every site/start/end without `lat`/`lng`, call a geocoding API to resolve it.
- Map `transport_mode` to routing engine profile:
  | `transport_mode` | engine profile |
  |---|---|
  | `driving` | `driving-car` |
  | `motorbike` | `driving-car` (closest available; flag for custom profile if engine supports motorbike) |
  | `walking` | `foot-walking` |
  | `transit` | requires GTFS-based engine (e.g. OpenTripPlanner), not OSRM/ORS |

### 4.2 Step 2 — Build distance/time matrix
- Input: list of N points = `[start] + sites + [end]`.
- Call routing engine's matrix endpoint once (not N² individual calls) to get:
  ```
  distance_matrix[i][j]  -> meters
  duration_matrix[i][j]  -> seconds
  ```
- Tooling: OSRM `/table`, GraphHopper Matrix API, OpenRouteService `/matrix`, or Google Distance Matrix API.

### 4.3 Step 3 — Solve sequencing (per decision in §3)

**If `held_karp_exact`:**
```
function held_karp(matrix, start_idx, end_idx, n):
    # dp[S][i] = min cost to visit set S, ending at node i
    # S is a bitmask of visited middle nodes
    # base case: dp[{start}][start] = 0
    # transition: dp[S ∪ {k}][k] = min(dp[S][i] + matrix[i][k]) for i in S
    # final answer: min over dp[full_set][i] + matrix[i][end_idx]
    return optimal_order, optimal_cost
```
Complexity: O(n² · 2ⁿ) — only use when n ≤ 12.

**If `or_tools_routing`:**
```
1. Load distance_matrix into OR-Tools RoutingIndexManager
2. Fix start node index = 0, end node index = N-1 (use SetFixedCostOfVertex or single-vehicle Start/End)
3. Add constraints if present:
     - time windows -> AddTimeWindowConstraintForVertex(open_time, close_time)
     - max distance -> AddDimension("distance", ...) with capacity = max_total_distance_km
4. Set first_solution_strategy = PATH_CHEAPEST_ARC
5. Set local_search_metaheuristic = GUIDED_LOCAL_SEARCH (improves via 2-opt/or-opt internally)
6. Solve with a time limit (e.g. 5-30s depending on n)
7. Extract order from solution.Value(routing.NextVar(...)) chain
```

### 4.4 Step 4 — Multi-day clustering (only if `num_days > 1`)
```
1. Cluster sites into num_days groups using k-means on (lat, lng),
   OR use OR-Tools multi-vehicle mode where each "vehicle" = one day
   (this also balances total travel time per day automatically).
2. Within each day cluster, sequencing day's start = previous day's end (or hotel),
   day's end = next day's start (or hotel).
3. Run Step 3 independently for each day's cluster.
```

### 4.5 Step 5 — Feasibility check
```
total_time = sum(travel_time_between_consecutive_stops) + sum(visit_duration_min)
IF total_time > available_window duration:
    → flag itinerary as "over time budget"
    → suggest: drop lowest-priority site, OR extend to num_days+1
ELSE:
    → mark itinerary "feasible"
```

### 4.6 Step 6 — Final detailed route
```
For the now-fixed order of stops:
  call routing engine /directions (or /route) with the ordered waypoint list
  → returns: turn-by-turn steps, polyline (for map rendering), per-leg distance/duration
```

### 4.7 Step 7 — Assemble itinerary output
Combine: ordered stops + per-leg distance/duration + arrival/departure time estimates (computed by walking the order and adding travel_time + visit_duration sequentially, starting from `available_window.start_time`) + polyline.

---

## 5. Output Schema

```json
{
  "status": "feasible | over_time_budget | error",
  "total_distance_km": 0.0,
  "total_duration_min": 0,
  "days": [
    {
      "day": 1,
      "stops": [
        {
          "site_id": "string",
          "name": "string",
          "arrival_time": "HH:MM",
          "departure_time": "HH:MM",
          "travel_from_prev_km": 0.0,
          "travel_from_prev_min": 0
        }
      ],
      "polyline": "encoded-polyline-string"
    }
  ],
  "warnings": ["string"]
}
```

---

## 6. Tool/Library Mapping (use exactly these unless told otherwise)

| Pipeline step | Tool |
|---|---|
| Geocoding | Nominatim (OSM) / Google Geocoding API |
| Distance/time matrix | OSRM `/table`, OpenRouteService `/matrix`, GraphHopper Matrix API |
| Sequencing (n ≤ 12) | Held-Karp DP — implement directly, no external library needed |
| Sequencing (n > 12, or with constraints) | Google OR-Tools (`ortools.constraint_solver.routing`) |
| Turn-by-turn route | OSRM `/route`, OpenRouteService `/directions`, Google Directions API |
| Multi-day clustering | k-means (`sklearn.cluster.KMeans`) or OR-Tools multi-vehicle mode |

Do not implement a custom routing engine from raw OSM data — always call one of the listed engines (self-hosted or API).

---

## 7. Reference implementations (for code patterns, not direct reuse)

- `tzmartin/Google-Maps-TSP-Solver` — has `solveAtoZ()` matching the fixed start/end case exactly; auto-switches brute force → 2-opt → 3-opt → ant colony based on n. https://github.com/tzmartin/Google-Maps-TSP-Solver
- `rgr4y/tspsolver` — same algorithm as a Node.js backend API instead of a browser widget. https://github.com/rgr4y/tspsolver
- `opentripplanner/OpenTripPlanner` — reference architecture if `transport_mode == "transit"` is needed. https://github.com/opentripplanner/OpenTripPlanner

None of these contain Vietnam-specific heritage data or road graphs — the site database and road network must be supplied separately.

---

## 8. Implementation Checklist (in order)

- [ ] Define and validate input JSON (§2)
- [ ] Implement geocoding fallback for `label`-only inputs
- [ ] Implement matrix-building call to chosen routing engine
- [ ] Implement Held-Karp DP for n ≤ 12
- [ ] Integrate OR-Tools Routing for n > 12 and for constrained cases
- [ ] Implement multi-day clustering (only needed if `num_days > 1` is supported)
- [ ] Implement feasibility check against `available_window`
- [ ] Implement final turn-by-turn route call
- [ ] Assemble and return output JSON (§5)
