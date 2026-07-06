# Hệ Thống Gợi Ý Du Lịch Di Sản Việt Nam

Hệ thống 8 bước tạo lịch trình du lịch theo ngày trên 63 tỉnh thành Việt Nam, sử dụng 830+ di sản được tuyển chọn, dữ liệu thời tiết thời gian thực và tối ưu hóa tuyến đường bằng OR-Tools.

## Kiến Trúc

```
Đầu Vào Người Dùng (TripInput)
    │
    ▼
Bước 1 — Chuẩn Hóa Đầu Vào          (step1_normalizer.py)
Bước 2 — Tạo Ứng Viên               (step2_candidates.py)
Bước 3 — Dịch Vụ Thời Tiết          (step3_weather.py)
Bước 4 — Chấm Điểm Địa Điểm         (step4_scoring.py)
Bước 4b — Xếp Hạng Đa Dạng MMR      (mmr_rerank.py)
Bước 5/6 — Tối Ưu Tuyến Đường TTDP  (ttdp_solver.py, step6_routing.py)
Bước 7 — Tạo Kế Hoạch Ngày          (step5_clustering.py)
Bước 8 — Lắp Ráp Hành Trình         (step8_assembly.py)
    │
    ▼
Đầu Ra (Itinerary)
```

---

## Đặc Tả Đầu Vào

### API Endpoint (TripInput)

Hệ thống chấp nhận cả đầu vào có cấu trúc và văn bản tự do (tiếng Việt & tiếng Anh).

| Trường | Kiểu | Bắt Buộc | Mặc Định | Mô Tả |
|--------|------|----------|----------|-------|
| `raw_text` | string | không | — | Mô tả tự do (VD: "Tôi muốn đi Hà Nội 3 ngày, thích lịch sử") |
| `destination_area` | string | không | `"Hà Nội"` | Tên tỉnh/thành phố đích |
| `destination_provinces` | string[] | không | từ destination_area | Danh sách tỉnh chính xác để lọc |
| `start_date` | string | không | `""` | Ngày bắt đầu YYYY-MM-DD |
| `end_date` | string | không | `""` | Ngày kết thúc YYYY-MM-DD |
| `duration_days` | int | không | `1` | Số ngày du lịch |
| `number_of_people` | int | không | `1` | Số người trong đoàn |
| `interests` | string[] | không | `["history","local_food"]` | Thẻ sở thích |
| `pace` | string | không | `"moderate"` | Nhịp độ: `relaxed` / `moderate` / `packed` |
| `travel_mode` | string | không | `"mixed"` | Phương tiện di chuyển |
| `budget_level` | string | không | `"medium"` | Ngân sách: `low` / `medium` / `high` |
| `constraints` | string[] | không | `[]` | Ràng buộc: `elderly_friendly`, `child_friendly`, `avoid_long_walking`, `prefer_indoor`, `prefer_outdoor` |
| `must_visit_site_ids` | string[] | không | `[]` | ID các địa điểm bắt buộc phải ghé |
| `start_lat` / `start_lng` | float | không | Tọa độ trung tâm tỉnh | Vị trí xuất phát |
| `end_lat` / `end_lng` | float | không | start_lat/lng | Vị trí kết thúc |

### Các Thẻ Sở Thích Được Hỗ Trợ
`history` (lịch sử), `architecture` (kiến trúc), `spiritual` (tâm linh), `craft_village` (làng nghề), `museum` (bảo tàng), `local_food` (ẩm thực), `nature` (thiên nhiên), `photography` (chụp ảnh)

### Phân Tích Văn Bản Tự Do (Tiếng Việt + Tiếng Anh)
Nếu `raw_text` được cung cấp, Bước 1 sẽ trích xuất sở thích, nhịp độ, ngân sách, ràng buộc, tỉnh và thời gian bằng cách khớp từ khóa song ngữ.

---

## Chi Tiết Các Bước

### Bước 1 — Chuẩn Hóa Đầu Vào
Chuyển đổi `TripInput` → `TripRequest`. Phân tích văn bản tự do qua từ điển từ khóa. Ánh xạ tên tỉnh sang tọa độ địa lý.

### Bước 2 — Tạo Ứng Viên
Lọc 830 di sản theo:
1. **Địa điểm bắt buộc**: luôn được bao gồm đầu tiên (bỏ qua bộ lọc tỉnh)
2. **Bộ lọc tỉnh**: khớp chính xác với `destination_provinces`
3. **Bộ lọc ràng buộc**: `elderly_friendly`, `child_friendly`, `prefer_indoor`, `prefer_outdoor`
4. **Xếp hạng sở thích**: độ tương đồng tín dụng một phần (xem bên dưới)
5. **Top-N**: trả về tối đa 30 ứng viên

**Độ Tương Đồng Sở Thích Tín Dụng Một Phần:**
Thay vì Jaccard cứng (`|A ∩ B| / |A|`), mỗi sở thích của người dùng được khớp với danh mục địa điểm tốt nhất bằng ma trận tương đồng 180 mục. Ví dụ: người dùng thích `architecture` nhận được 0.6 điểm cho địa điểm gắn thẻ `history`, thay vì 0.

```
S_interest = (1 / |interests|) * Σᵢ maxⱼ CATEGORY_SIM(interestᵢ, categoryⱼ)
```

Trong đó `CATEGORY_SIM` ánh xạ các cặp như:
- `(history, architecture)` → 0.6
- `(spiritual, pagoda)` → 0.8
- `(unesco, history)` → 0.8
- `(museum, history)` → 0.7

### Bước 3 — Dịch Vụ Thời Tiết
Lấy dự báo thời tiết theo giờ từ **Open-Meteo** (API miễn phí) cho khu vực du lịch:
- Nhiệt độ (°C)
- Xác suất mưa (%)
- Chỉ số UV
- Chất lượng không khí (PM2.5, AQI) qua OpenWeatherMap (tùy chọn)

Lưu cache theo hash tọa độ + ngày. Dự báo bao phủ `max(duration_days, 3)` ngày.

### Bước 4 — Chấm Điểm Địa Điểm
Tính điểm tổng hợp có trọng số (0–1) cho mỗi di sản theo **7 chiều**.

#### Trọng Số Cơ Bản

| Chiều | Trọng Số | Nguồn |
|-------|----------|-------|
| Khớp sở thích | 0.30 | Độ tương đồng danh mục tín dụng một phần |
| Tầm quan trọng lịch sử | 0.20 | Suy diễn từ danh mục + bậc tỉnh |
| Phù hợp thời tiết | 0.15 | Khớp dự báo theo giờ |
| Khoảng cách | 0.15 | Hàm suy giảm logarit |
| Độ phổ biến | 0.10 | Suy diễn từ danh mục + bậc tỉnh |
| Khả năng tiếp cận | 0.05 | Điểm trong nhà + thời lượng + ràng buộc |
| Phù hợp ngân sách | 0.05 | Giá vé vs mức ngân sách |

#### Chuẩn Hóa Lại Trọng Số Động

Khi người dùng yêu cầu rõ ràng ràng buộc về khả năng tiếp cận hoặc ngân sách, các trọng số tương ứng được tăng lên và tất cả trọng số được chuẩn hóa lại để tổng = 1.0:

| Điều Kiện | Tăng |
|-----------|------|
| `elderly_friendly` hoặc `child_friendly` | accessibility: 0.05 → 0.15 |
| `budget_level = "low"` | budget: 0.05 → 0.15 |

#### Độ Phổ Biến Suy Diễn (khoảng 0.45–0.95)

```
popularity = 0.45
  + 0.25  nếu unesco
  + 0.10  nếu museum
  + 0.08  nếu history
  + 0.08  nếu architecture
  + 0.05  nếu craft_village
  + 0.05  nếu entertainment
  + 0.04  nếu spiritual
  + 0.04  nếu nature
  + 0.04  nếu có description
  + 0.03  nếu có visit_tips
  + 0.02  nếu có reference_url
  + PROVINCE_TIER[tỉnh]  (0.01–0.08)
→ giới hạn 0.95
```

#### Tầm Quan Trọng Lịch Sử Suy Diễn (khoảng 0.45–0.95)

```
historical = 0.45
  + 0.30  nếu unesco
  + 0.15  nếu history
  + 0.10  nếu museum
  + 0.08  nếu architecture
  + 0.05  nếu spiritual
  + 0.03  nếu craft_village
  + 0.02  nếu có long_description
  + PROVINCE_TIER[tỉnh]  (0.01–0.08)
→ giới hạn 0.95
```

#### Điểm Thưởng Bậc Tỉnh

Các tỉnh được xếp hạng theo mức độ nổi bật du lịch:

| Bậc | Thưởng | Tỉnh |
|-----|--------|------|
| Bậc 1 | +0.08 | Hà Nội, Huế, Quảng Nam (Hội An) |
| Bậc 2 | +0.06 | TP. Hồ Chí Minh, Đà Nẵng |
| Bậc 3 | +0.05 | Ninh Bình, Quảng Ninh |
| Bậc 4 | +0.04 | Hải Phòng, Khánh Hòa, Lào Cai, Hà Giang, Lâm Đồng |
| Bậc 5 | +0.03 | Cần Thơ, Bình Định, Thanh Hóa, Nghệ An, Bắc Ninh |
| Mặc định | +0.02 | Tất cả các tỉnh khác |

#### Khớp Thời Tiết Theo Giờ

Sử dụng giờ dự báo gần nhất với thời gian tham quan thực tế (không phải trung bình ngày):

| Điều Kiện | Phạt |
|-----------|------|
| Mưa > 70% + ngoài trời | −0.35 |
| Mưa 50–70% + ngoài trời | −0.15 |
| Nhiệt độ > 35°C + ngoài trời | −0.25 |
| Nhiệt độ 32–35°C + ngoài trời | −0.10 |
| UV > 8 (11:00–14:00) | −0.20 |
| UV > 6 (11:00–15:00) | −0.10 |
| Nhiệt độ < 10°C + ngoài trời | −0.15 |
| Nhiệt độ 10–15°C + ngoài trời | −0.05 |

Địa điểm trong nhà (outdoor_score ≤ 0.6) được miễn phạt mưa/nhiệt độ.

#### Điểm Khoảng Cách Logarit

```
dist_score = max(0.15, 1.0 / (1.0 + dist_km / 20.0))
```

| Khoảng Cách | Điểm (log) | Điểm (tuyến tính, cũ) |
|-------------|-----------|----------------------|
| 0 km | 1.00 | 1.00 |
| 5 km | 0.80 | 0.95 |
| 10 km | 0.67 | 0.90 |
| 20 km | 0.50 | 0.80 |
| 60 km | 0.25 | 0.40 |
| Sàn | 0.15 | 0.00 |

#### Điểm Khả Năng Tiếp Cận

```
accessibility = 0.50
  + 0.25 * indoor_score
  + thưởng_thời_gian  (≤30ph: +0.10, ≤60ph: +0.08, ≤90ph: +0.05)
  + thưởng_ràng_buộc
  + (0.08 nếu không có ràng buộc)
```

Thưởng ràng buộc (luôn cộng thêm):
- `elderly_friendly`: +0.05 nếu indoor_score > 0.4, +0.05 nếu ≤ 60 phút
- `child_friendly`: +0.05 nếu ≤ 60 phút
- `avoid_long_walking`: +0.10 nếu indoor_score > 0.5, −0.05 nếu ngược lại

#### Phù Hợp Ngân Sách

```
budget_fit = 1.0                                     nếu ticket_price == 0
           = 0.2                                      nếu ticket_price ≥ ngưỡng
           = 1.0 − (giá − lo) / (hi − lo)            còn lại
```
Ngưỡng: thấp: 30,000 VND, vừa: 100,000 VND, cao: 1,000,000 VND

### Bước 4b — Xếp Hạng Đa Dạng MMR
Áp dụng **Maximal Marginal Relevance** (λ = 0.7) để đa dạng hóa nhóm ứng viên:

```
MMR(địa_điểm) = λ · điểm(địa_điểm) − (1−λ) · max_đã_chọn similarity(địa_điểm, đã_chọn)
```

Độ tương đồng pha trộn khoảng cách địa lý (60%) và độ trùng danh mục Jaccard (40%), giới hạn 10 km. Điều này ngăn 3 địa điểm điểm cao gần như trùng lặp trong cùng khu vực chiếm ưu thế nhóm ứng viên.

### Bước 5/6 — Tối Ưu Tuyến Đường TTDP
Sử dụng **Google OR-Tools** để giải bài toán Team Orienteering Problem with Time Windows (OPTW):
- Đầu vào: địa điểm đã chấm điểm là POI với điểm số, thời lượng tham quan, cửa sổ thời gian
- N xe = N ngày du lịch
- Tối đa 8h mỗi ngày, tốc độ 40 km/h
- Thời gian giải tối đa 2 giây
- Dự phòng: chọn tham lam Top-N nếu bộ giải thất bại

### Bước 7 — Tạo Kế Hoạch Ngày
Chuyển đổi chỉ số tuyến đường đã tối ưu thành đối tượng `DayPlan` với ngày theo lịch và các mục `ItineraryItem`. Khung giờ được gán bắt đầu từ 08:00 mỗi ngày.

### Bước 8 — Lắp Ráp Hành Trình
Tính toán chỉ số cuối cùng với chấm điểm khoảng cách hai lượt:
- **Lượt 1**: Sử dụng khoảng cách đường thực tế OSRM (table API) khi có sẵn
- **Lượt 2**: Dự phòng Haversine + ước tính 30 km/h

#### Điểm Chất Lượng (0–1)

```
quality = 0.25 × điểm_TB_địa_điểm
        + 0.20 × hiệu_quả_tuyến        (1 − dist_mỗi_ngày / 100km)
        + 0.15 × phù_hợp_thời_tiết     (TB độ phù hợp thời tiết)
        + 0.15 × phù_hợp_sở_thích      (TB độ khớp sở thích)
        + 0.10 × điểm_ẩm_thực           (số nhà hàng / max(1, ngày×3))
        + 0.10 × cân_bằng_lịch          (1 − (max_items − min_items) / max_items)
        + 0.05 × phù_hợp_ngân_sách      (từ trung bình giá vé)
```

#### Hiệu Quả Tuyến Đường (hai lượt)
Khi ma trận khoảng cách OSRM có sẵn, sử dụng khoảng cách lái xe thực tế thay vì Haversine, khắc phục:
- Khoảng cách bị đánh giá thấp trong lõi đô thị đông đúc (Hà Nội, Hội An)
- Khoảng cách bị đánh giá cao trên đường cao tốc

---

## Đặc Tả Đầu Ra

### Itinerary (Hành Trình)

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

| Trường | Kiểu | Mô Tả |
|--------|------|-------|
| `itinerary_id` | string | ID hex 12 ký tự duy nhất |
| `summary` | string | Tóm tắt một dòng tiếng Việt |
| `total_score` | float | Điểm chất lượng (0–1), càng cao càng tốt |
| `total_distance_km` | float | Tổng khoảng cách tuyến đường (km) |
| `days[]` | DayPlan[] | Một cho mỗi ngày du lịch |
| `days[].day` | int | Số ngày (bắt đầu từ 1) |
| `days[].date` | string | Ngày YYYY-MM-DD |
| `days[].items[]` | ItineraryItem[] | Điểm dừng theo thứ tự |
| `days[].items[].time` | string | Khung giờ HH:MM-HH:MM |
| `days[].items[].type` | string | `"heritage"` hoặc `"restaurant"` |
| `days[].items[].ref_id` | string | ID địa điểm/nhà hàng |
| `days[].items[].name` | string | Tên hiển thị |
| `days[].items[].reason` | string | Phân tích điểm số |
| `days[].items[].travel_from_previous_minutes` | int | Thời gian di chuyển từ điểm trước (phút) |
| `days[].items[].distance_from_previous_m` | float | Khoảng cách từ điểm trước (mét) |
| `route_geometries[]` | float[][][] | Tọa độ GeoJSON LineString cho mỗi ngày |

---

## Nguồn Dữ Liệu

| Tệp | Nội Dung |
|------|----------|
| `data/curated_heritage.json` | 830+ địa điểm trên 63 tỉnh thành |
| `data/curated_restaurants.json` | Dữ liệu nhà hàng được tuyển chọn |
| `data/crawled_heritage.json` | Di sản thu thập từ web |
| `data/deepseek_clean.json` | Dữ liệu di sản đã AI làm sạch |
| `data/deepseek_enriched.json` | Mô tả địa điểm đã AI làm giàu |
| `data/geocode_cache.json` | Kết quả mã hóa địa lý Nominatim |

### Danh Mục Di Sản (8 loại)
`history` (lịch sử), `nature` (thiên nhiên), `spiritual` (tâm linh), `architecture` (kiến trúc), `entertainment` (giải trí), `museum` (bảo tàng), `unesco`, `craft_village` (làng nghề)

---

## Phân Phối Điểm Số (Benchmark)

Đo trên 214 địa điểm được chấm điểm qua 10 cấu hình chuyến đi:

| Chỉ Số | Giá Trị |
|--------|---------|
| Điểm TB địa điểm | 0.70 |
| Trung vị | 0.70 |
| Độ lệch chuẩn | 0.13 |
| P25–P75 | 0.61–0.78 |
| P90 | 0.86 |
| Tối đa | 0.94 |

---

## Cấu Hình

Biến môi trường (`.env`):

| Biến | Mặc Định | Mô Tả |
|------|----------|-------|
| `OSRM_BASE_URL` | `http://localhost:5000` | Máy chủ định tuyến OSRM |
| `OPENWEATHER_API_KEY` | (trống) | Khóa API OpenWeatherMap (tùy chọn, cho chất lượng không khí) |
| `DEFAULT_CANDIDATE_LIMIT` | `30` | Số ứng viên tối đa mỗi truy vấn |
| `MAX_DAILY_HOURS` | `10` | Số giờ hoạt động tối đa mỗi ngày |
| `MAX_SOLVE_TIMEOUT` | `5.0` | Thời gian giải OR-Tools tối đa (giây) |

---

## Chạy Hệ Thống

```bash
pip install -r requirements.txt
docker-compose up   # khởi động API gateway + AI service + OSRM
```

API endpoint: `POST http://localhost:8000/api/recommend`

### Ví Dụ Request

```json
{
  "raw_text": "Tôi muốn đi Hà Nội 3 ngày, thích lịch sử và kiến trúc, đi cùng người già",
  "start_date": "2026-07-10",
  "duration_days": 3,
  "number_of_people": 2
}
```

### Ví Dụ Response

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
