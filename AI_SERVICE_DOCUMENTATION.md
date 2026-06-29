# Vietnam Heritage Travel Recommendation System

Hệ thống gợi ý lịch trình du lịch di sản Việt Nam theo tỉnh/thành, sở thích, số ngày và tốc độ di chuyển. Backend dùng FastAPI, dữ liệu di sản local, thời tiết Open-Meteo và định tuyến đường bộ bằng OSRM local.

## Mục Tiêu

- Tạo lịch trình du lịch nhiều ngày theo điểm đến người dùng chọn.
- Chọn điểm di sản phù hợp theo tỉnh, sở thích và ràng buộc.
- Chia điểm tham quan theo ngày.
- Tối ưu thứ tự đi trong từng ngày bằng ma trận khoảng cách đường bộ.
- Trả về itinerary, tổng quãng đường và route geometry để vẽ trên bản đồ.

## Kiến Trúc

```text
Browser / Map UI
    |
    v
API Gateway :8000
    |
    v
AI Service :8001
    |
    +--> Local heritage data
    +--> Open-Meteo weather API
    +--> OSRM local :5000
    +--> Image/review/enrichment cache

Docker infrastructure
    +--> PostGIS :5432
    +--> Redis :6379
    +--> OSRM :5000
```

## Services

| Service | Port | Vai trò |
|---|---:|---|
| API Gateway | 8000 | Serve frontend, forward API request tới AI service |
| AI Service | 8001 | Chạy recommendation pipeline |
| OSRM | 5000 | Tính khoảng cách đường bộ và route geometry |
| PostGIS | 5432 | Database infra |
| Redis | 6379 | Cache infra |

## Pipeline Gợi Ý

1. Normalize input

Chuyển payload người dùng thành `TripRequest` chuẩn.

2. Generate candidates

Lọc di sản theo `destination_provinces`, constraints và interests. Must-visit site luôn được ưu tiên đưa vào.

3. Fetch weather

Gọi Open-Meteo theo centroid khu vực để lấy forecast. Có cache trong memory cho request lặp lại.

4. Score sites

Chấm điểm candidate theo mức khớp sở thích, độ phổ biến, tầm quan trọng lịch sử, thời tiết và các yếu tố phù hợp khác.

5. Split into days

Chia các điểm đã chấm điểm thành cụm theo ngày. Số điểm/ngày phụ thuộc `pace`:

- `relaxed`: tối đa 3 điểm/ngày
- `moderate`: tối đa 5 điểm/ngày
- `packed`: tối đa 7 điểm/ngày

6. Optimize routing

Với từng ngày, hệ thống gọi OSRM local để lấy distance matrix, sau đó tối ưu thứ tự bằng nearest-neighbor + 2-opt. Các ngày được chạy song song bằng `asyncio.gather`.

Nếu OSRM không sẵn sàng, service fallback sang haversine để không làm request treo lâu.

7. Build day plans

Chuyển các cụm đã tối ưu thành `DayPlan`.

8. Assemble itinerary

Tính tổng điểm, tổng khoảng cách, summary và route geometry.

## Cách Chạy

### Chạy toàn bộ hệ thống

```bash
bash start.sh
```

Script sẽ:

- Cài Python dependencies từ `requirements.txt`.
- Start PostGIS, Redis và OSRM qua Docker Compose.
- Start AI service tại `http://localhost:8001`.
- Start API gateway tại `http://localhost:8000`.

### Chạy riêng infra Docker

```bash
docker compose up -d
```

Hoặc chỉ chạy các service cần thiết:

```bash
docker compose up -d postgis redis osrm
```

### Kiểm tra health

```bash
curl http://localhost:8000/api/v1/health
```

Kết quả mong đợi:

```json
{"gateway":"ok","ai_service":"ok","version":"1.0.0"}
```

## OSRM Local

OSRM được cấu hình trong `docker-compose.yml` và mount dữ liệu từ:

```text
data/osrm/
```

Các file OSRM đã preprocess không nên commit vào git vì dung lượng lớn. Thư mục này đã được ignore trong `.gitignore`.

### Chuẩn bị dữ liệu OSRM

Chỉ cần làm lại khi thiếu `data/osrm` hoặc muốn update map.

```bash
mkdir -p data/osrm
curl -L https://download.geofabrik.de/asia/vietnam-latest.osm.pbf -o data/osrm/vietnam-latest.osm.pbf

docker run --rm -t -v "$PWD/data/osrm:/data" ghcr.io/project-osrm/osrm-backend:v5.27.1 osrm-extract -p /opt/car.lua /data/vietnam-latest.osm.pbf

docker run --rm -t -v "$PWD/data/osrm:/data" ghcr.io/project-osrm/osrm-backend:v5.27.1 osrm-partition /data/vietnam-latest.osrm

docker run --rm -t -v "$PWD/data/osrm:/data" ghcr.io/project-osrm/osrm-backend:v5.27.1 osrm-customize /data/vietnam-latest.osrm
```

### Test OSRM

```bash
curl "http://localhost:5000/route/v1/driving/105.8542,21.0285;105.8342,21.0367?overview=false"
```

Nếu trả về `"code":"Ok"` là OSRM local đã chạy đúng.

## API Chính

### Generate itinerary

```bash
curl -X POST http://localhost:8000/api/v1/trips/recommend \
  -H 'Content-Type: application/json' \
  -d '{
    "destination_provinces": ["Hà Nội"],
    "duration_days": 2,
    "pace": "moderate",
    "interests": ["history", "local_food"]
  }'
```

Response gồm:

- `itinerary_id`
- `summary`
- `total_score`
- `total_distance_km`
- `days`
- `route_geometries`

### List heritage sites

```bash
curl http://localhost:8000/api/v1/heritage-sites
```

### Get site images

```bash
curl http://localhost:8000/api/v1/heritage-sites/{site_id}/images
```

### Get reviews

```bash
curl http://localhost:8000/api/v1/heritage-sites/{site_id}/reviews
```

### Get enriched site info

```bash
curl http://localhost:8000/api/v1/heritage-sites/{site_id}/enrich
```

## Log Và Debug

Khi chạy bằng `nohup`, log được ghi vào:

```text
logs/ai_service.log
logs/api_gateway.log
```

Log pipeline có format từng step:

```text
STEP 1 — Normalize (...s)
STEP 2 — Candidates (...s)
STEP 3 — Weather (...s)
STEP 4 — Scoring (...s)
STEP 5 — Clustering (...s)
STEP 6 — Routing (...s)
STEP 7 — Day Plans (...s)
STEP 8 — Assemble (...s)
DONE — Total: ...s
```

Nếu OSRM local hoạt động, log routing sẽ có route waypoints:

```text
Day 1 OSRM: 5 sites ordered | route: 35 waypoints
STEP 6 — Routing (0.05s): 2/2 OSRM routes
```

Nếu OSRM lỗi hoặc chưa chạy, log sẽ có fallback:

```text
OSRM fallback: table/v1/driving failed (...)
```

## Kiểm Tra Trạng Thái

### Docker services

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

### Python services

```bash
pgrep -af 'services.ai_service|api_gateway|uvicorn'
```

### OSRM logs

```bash
docker logs heritage_osrm
```

## Troubleshooting

### OSRM không lên

Kiểm tra thư mục `data/osrm` có đủ file preprocess chưa:

```bash
ls data/osrm
```

Nếu thiếu, chạy lại bước chuẩn bị dữ liệu OSRM.

### API chậm

Xem `logs/ai_service.log` để biết step nào chậm. Các nguyên nhân thường gặp:

- `STEP 3 — Weather` chậm do Open-Meteo API/network.
- `STEP 6 — Routing` chậm do OSRM chưa chạy hoặc đang fallback.
- Request đầu tiên sau restart thường chậm hơn do cache chưa warm.

### Route geometry rỗng

Kiểm tra OSRM:

```bash
curl "http://localhost:5000/route/v1/driving/105.8542,21.0285;105.8342,21.0367?overview=false"
```

Nếu OSRM OK nhưng response vẫn rỗng, xem log AI service để kiểm tra có fallback không.

## File Quan Trọng

| File | Vai trò |
|---|---|
| `start.sh` | Start toàn bộ hệ thống |
| `docker-compose.yml` | Khai báo PostGIS, Redis, OSRM |
| `config/settings.py` | URL service và cấu hình runtime |
| `api_gateway/main.py` | API gateway và frontend serving |
| `services/ai_service/main.py` | FastAPI app của AI service |
| `services/ai_service/pipeline.py` | Orchestrator 8 bước |
| `services/ai_service/step6_routing.py` | OSRM routing, cache, fallback |
| `frontend/map.html` | Frontend map UI |
| `data/osrm/` | Dữ liệu OSRM local, không commit |

## Trạng Thái Hiện Tại

- OSRM local đã được cấu hình chạy mặc định trong Docker Compose.
- AI service ưu tiên `settings.osrm_base_url`, mặc định `http://localhost:5000`.
- Routing theo ngày chạy song song.
- OSRM request có cache in-memory và timeout ngắn để tránh treo lâu.
- Nếu OSRM lỗi, hệ thống fallback sang haversine để vẫn trả itinerary.
