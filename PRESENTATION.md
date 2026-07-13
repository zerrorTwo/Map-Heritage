# Hệ thống Gợi ý Lịch trình Du lịch Di sản Việt Nam

## Bài trình bày trước Hội đồng

---

## 1. Bài toán

Du khách muốn khám phá di sản văn hóa Việt Nam gặp khó khăn:
- **62 tỉnh thành**, hàng trăm di sản — không biết chọn điểm nào
- **Thời gian hạn chế** — làm sao tối ưu 2-5 ngày để tham quan được nhiều nhất?
- **Sở thích đa dạng** — lịch sử, kiến trúc, tâm linh, thiên nhiên...
- **Yếu tố thực tế** — thời tiết, giao thông, ngân sách, người già/trẻ em

**Giải pháp:** Hệ thống tự động lập lịch trình du lịch di sản theo ngày, cá nhân hóa theo sở thích, tối ưu tuyến đường thực tế qua OSRM.

---

## 2. Kiến trúc tổng quan

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│  API Gateway │────▶│  AI Service  │
│  (React.js)  │     │   (FastAPI)  │     │   (Pipeline) │
│  Google Maps │     │   Port 8001  │     │   Port 8000  │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                 │
                    ┌────────────────────────────┼────────────────────────────┐
                    │                            │                            │
              ┌─────▼─────┐              ┌──────▼──────┐              ┌──────▼──────┐
              │   OSRM    │              │  Open-Meteo │              │  Nominatim  │
              │  (Routing)│              │  (Weather)  │              │ (Geocoding) │
              └───────────┘              └─────────────┘              └─────────────┘
```

**Công nghệ:** Python FastAPI, Docker microservices, Google OR-Tools, OSRM, MapLibre GL

---

## 3. Dữ liệu

| Thông số | Giá trị |
|----------|---------|
| Tổng số di sản | **780** |
| Tỉnh thành | **62/63** |
| Danh mục | 8 loại (lịch sử, thiên nhiên, tâm linh, kiến trúc, bảo tàng, UNESCO, làng nghề, giải trí) |
| Tọa độ | OSM-verified qua Nominatim |
| Metadata | Mô tả, giờ mở cửa, giá vé, thời gian tham quan, điểm trong/ngoài trời, phù hợp người già/trẻ em |

---

## 4. Pipeline xử lý — 8 bước

```
Input → [1] Normalize → [2] Candidates → [3] Weather → [4] Score → [4b] MMR → [5] Cluster → [6] Route → [7] DayPlan → [8] Assemble → Output
```

### Bước 1 — Chuẩn hóa đầu vào
- Tách sở thích, nhịp độ, ngân sách, tỉnh từ văn bản tự do hoặc form
- 68+ từ khóa song ngữ Việt-Anh, regex, NFKD normalization

### Bước 2 — Lọc ứng viên
- **Partial-credit similarity**: ma trận 180 cặp quan hệ giữa các danh mục
- VD: `architecture` khớp với `history` ở mức 0.6 (thay vì 0 nếu Jaccard)
- Công thức: `S = (1/n) × Σ max CATEGORY_SIM(interest, category)`

### Bước 3 — Thời tiết
- Open-Meteo API (miễn phí, không API key)
- Dự báo theo giờ, cache TTL 1 giờ

### Bước 4 — Chấm điểm (7 chiều)

| Chiều | Trọng số | Cách tính |
|-------|----------|-----------|
| Interest match | 0.30 | Partial-credit similarity |
| Historical importance | 0.20 | Dẫn xuất từ danh mục + province tier |
| Weather | 0.15 | Dự báo theo giờ khớp giờ tham quan |
| Distance | 0.15 | Log decay: `1/(1+dist/20)` |
| Popularity | 0.10 | Dẫn xuất từ danh mục |
| Accessibility | 0.05 | Indoor score + thời gian + constraints |
| Budget | 0.05 | Giá vé vs ngân sách |

**Dynamic re-weighting:** Khi user chọn `elderly_friendly` → accessibility tăng 0.05→0.15

### Bước 4b — Đa dạng hóa (MMR)
- Maximal Marginal Relevance (Carbonell & Goldstein, 1998)
- `MMR = λ×score − (1−λ)×max_similarity(selected)`
- λ = 0.7: 70% chất lượng, 30% đa dạng địa lý
- Ngăn 3 điểm top đều ở cùng 1 khu phố

### Bước 5 — Phân chia theo ngày (Geographic Clustering)

**Thuật toán `partition_into_days`:**
1. Phân bố must-visit sites đều các ngày (round-robin theo vĩ độ)
2. Điền ngày trống bằng farthest-point seeds
3. Gán sites còn lại vào ngày gần nhất, giới hạn theo pace:
   - `relaxed`: 3 sites/ngày
   - `moderate`: 5 sites/ngày
   - `packed`: 7 sites/ngày
4. Back-fill theo thứ tự MMR (đa dạng địa lý + danh mục)

### Bước 6 — Tối ưu tuyến đường thực tế (OSRM)

**Bài toán:** TSP open-path — tìm thứ tự tham quan tối ưu trong ngày

```
cost = duration(start→site₁) + Σ duration(siteᵢ→siteᵢ₊₁) + duration(siteₙ→end)
```

- **Exact search** cho ≤8 sites: duyệt toàn bộ `n!` hoán vị (7! = 5,040, <1ms)
- **Heuristic** cho >8 sites: multi-start nearest-neighbor + 2-opt
- Anchor chỉ áp dụng ngày đầu/ngày cuối — các ngày giữa nối tiếp nhau

**Phát hiện đảo:** Cặp sites liên tiếp >150km → fallback đường chim bay + gắn cảnh báo `island_route`

### Bước 7 — Xây dựng kế hoạch ngày
- Time slot bắt đầu từ 08:00, tăng dần theo travel time + visit duration
- Travel time từ OSRM (ưu tiên) hoặc haversine fallback

### Bước 8 — Đánh giá chất lượng

```
Quality = 0.25 × avg_score + 0.20 × route_eff + 0.15 × weather + 0.15 × pref
        + 0.10 × food + 0.10 × balance + 0.05 × budget
```

- `route_eff` = `1 − dist_per_day / cap` với `cap = 100 × √số_tỉnh`
- 1 tỉnh → 100 km/ngày, 4 tỉnh → 200 km/ngày
- Cảnh báo đảo (`island_route`) được trả về trong response

---

## 5. API & Output

**Request:**
```json
{
  "destination_provinces": ["Hà Nội", "Ninh Bình"],
  "duration_days": 3,
  "interests": ["history", "architecture"],
  "pace": "moderate",
  "constraints": ["elderly_friendly"]
}
```

**Response (trích):**
```json
{
  "itinerary_id": "it-a1b2c3d4e5f6",
  "summary": "Chuyến du lịch 3 ngày tại Hà Nội, Ninh Bình. Khám phá 15 di sản. CL: 68%",
  "total_score": 0.6832,
  "total_distance_km": 120.5,
  "warnings": [],
  "days": [
    { "day": 1, "items": [
        { "time": "08:00-09:00", "name": "Văn Miếu - Quốc Tử Giám", "travel_from_previous_minutes": 0 },
        { "time": "09:15-10:15", "name": "Hoàng thành Thăng Long", "travel_from_previous_minutes": 15 }
    ]}
  ],
  "route_geometries": [[[105.85,21.03], [105.84,21.04]]]
}
```

---

## 6. Điểm sáng tạo

| STT | Sáng tạo | Chi tiết |
|-----|----------|----------|
| 1 | **Partial-credit similarity** | Ma trận 180 cặp quan hệ danh mục — không mất ứng viên chất lượng vì khác tag |
| 2 | **Dynamic weight re-normalization** | Tự động tăng trọng số accessibility/budget khi user yêu cầu |
| 3 | **Hour-level weather matching** | Dùng giờ tham quan cụ thể, không phải trung bình ngày |
| 4 | **MMR diversity** | Cân bằng chất lượng-đa dạng, ngăn 3 điểm top cùng khu phố |
| 5 | **Geographic clustering + pace** | Phân bố sites theo địa lý, giới hạn sites/ngày, back-fill tự động |
| 6 | **Exact TSP ≤8 sites** | Tối ưu toàn cục cho lịch trình thực tế (3-7 sites/ngày) |
| 7 | **Island detection** | Tự động nhận diện tuyến qua đảo, fallback đường chim bay + cảnh báo |
| 8 | **Multi-province quality** | Route efficiency tự scale theo số tỉnh được chọn |

---

## 7. Kết quả thực nghiệm

### Ví dụ: Hà Nội 3 ngày, pace=moderate
```
Day 1: Văn Miếu → Hoàng Thành → Hồ Gươm → Nhà thờ Lớn → Bảo tàng LS
Day 2: Chùa Trấn Quốc → Lăng Bác → Chùa Một Cột → Bảo tàng HCM → Hồ Tây
Day 3: Làng gốm Bát Tràng → Đền Sóc → Chùa Thầy → Đền Và
→ Chất lượng: 68% | Khoảng cách: 95 km
```

### Ví dụ: Đà Lạt 2 ngày, pace=moderate
```
Day 1: Ga Đà Lạt → Hồ Xuân Hương → Chợ Đà Lạt → Dinh Bảo Đại → Nhà thờ Con Gà
Day 2: Thiền viện Trúc Lâm → Hồ Tuyền Lâm → Thác Datanla → Thung lũng TY → Đồi chè Cầu Đất
→ Chất lượng: 72% | Khoảng cách: 58 km
```

---

## 8. Hướng phát triển

- **AI mô tả/Narrator**: Tự động sinh audio kể chuyện về mỗi di sản
- **Real-time traffic**: Tích hợp dữ liệu giao thông thời gian thực
- **Multi-modal transport**: Kết hợp xe máy, đi bộ, phà cho tuyến qua đảo
- **Collaborative filtering**: Gợi ý dựa trên lịch sử người dùng tương tự
- **Mobile app**: Ứng dụng di động với GPS navigation theo lịch trình

---

## Cảm ơn Hội đồng đã lắng nghe!
