# Hệ Thống Gợi Ý Du Lịch Di Sản Việt Nam

Hệ thống 8 bước tạo lịch trình du lịch theo ngày trên 63 tỉnh thành Việt Nam, sử dụng 830+ di sản được tuyển chọn, dữ liệu thời tiết thời gian thực, tối ưu hóa tuyến đường bằng OR-Tools, và sắp xếp lại theo khoảng cách đường thực tế OSRM.

## Kiến Trúc

```
Đầu Vào Người Dùng (TripInput)
    │
    ▼
Bước 1 — Chuẩn Hóa Đầu Vào           (trích xuất từ khóa dựa trên luật)
    │     ▼ TripRequest
Bước 2 — Tạo Ứng Viên                (tương đồng danh mục tín dụng một phần + lọc tỉnh)
    │     ▼ HeritageSite[]
Bước 3 — Dịch Vụ Thời Tiết           (API Open-Meteo miễn phí, dự báo theo giờ)
    │     ▼ Forecast{}
Bước 4 — Chấm Điểm Địa Điểm          (7 chiều có trọng số, tái chuẩn hóa động)
    │     ▼ ScoredSite[]
Bước 4b — Xếp Hạng Đa Dạng MMR       (Maximal Marginal Relevance, λ=0.7)
    │     ▼ ScoredSite[] (đã đa dạng hóa)
Bước 5 — Phân Chia Ngày TTDP          (OR-Tools OPTW, khoảng cách haversine)
    │     ▼ List[ScoredSite][] (cụm theo ngày)
Bước 6 — Sắp Xếp Lại Theo Đường OSRM  (1 table + 2-opt đường mở mỗi ngày, neo cố định)
    │     ▼ List[ScoredSite][] (đã sắp xếp) + hình học tuyến + ma trận khoảng cách
Bước 7 — Tạo Kế Hoạch Ngày            (kế hoạch theo ngày với khung giờ)
    │     ▼ DayPlan[]
Bước 8 — Lắp Ráp Hành Trình           (7 chiều điểm chất lượng + khoảng cách OSRM + ngân sách)
    │     ▼ Itinerary
Đầu Ra (JSON)
```

---

## Chi Tiết Từng Bước

---

### Bước 1 — Chuẩn Hóa Đầu Vào

**Tệp:** `step1_normalizer.py` · **Thuật toán:** Trích xuất từ khóa dựa trên luật

**Sử dụng:** 5 từ điển từ khóa (68 từ khóa sở thích, 12 nhịp độ, 11 ngân sách, 14 ràng buộc, 27 tỉnh) bao phủ tiếng Việt và tiếng Anh. Regex để trích xuất thời gian (`\d+\s*ngày`, `\d+\s*days?`). Chuẩn hóa NFKD `unicodedata` để khớp tỉnh không dấu.

**Tại sao dùng cách này:** Khớp từ khóa dựa trên luật có tính xác định, nhanh (dưới 1 ms), không cần chi phí suy luận LLM cho đầu vào biểu mẫu có cấu trúc, và xử lý được hầu hết các cụm từ du lịch tiếng Việt phổ biến.

**Dự phòng:** Tỉnh không xác định giữ nguyên; các trường thiếu mặc định là `"Hà Nội"`, 2 ngày, nhịp độ `"moderate"`.

---

### Bước 2 — Tạo Ứng Viên

**Tệp:** `step2_candidates.py` · **Thuật toán:** Tương đồng danh mục tín dụng một phần với lọc

**Sử dụng:** Ma trận `CATEGORY_SIM` 180 mục ánh xạ quan hệ chéo giữa các danh mục. Khớp mờ tỉnh với chuẩn hóa NFKD. Cơ chế bỏ qua cho địa điểm bắt buộc (bỏ qua bộ lọc tỉnh/ràng buộc).

**Tại sao dùng tín dụng một phần thay vì Jaccard:** Jaccard cứng (`|A ∩ B| / |A|`) cho điểm 0 khi sở thích người dùng và danh mục địa điểm không có thẻ trùng chính xác — ví dụ: người dùng thích `architecture` nhận 0 điểm cho địa điểm chỉ gắn thẻ `history`. Tín dụng một phần gán 0.6, giúp các địa điểm chất lượng cao không bị loại sớm.

**Công thức tương đồng:**

```
S_interest = (1 / |interests|) * Σᵢ maxⱼ CATEGORY_SIM(interestᵢ, categoryⱼ)
```

Trong đó `CATEGORY_SIM` ánh xạ các cặp:
| Cặp | Điểm |
|-----|------|
| `(history, architecture)` | 0.6 |
| `(spiritual, pagoda)` | 0.8 |
| `(unesco, history)` | 0.8 |
| `(museum, history)` | 0.7 |

**Lọc ràng buộc:** `elderly_friendly` yêu cầu `suitable_for_elderly=True` và `indoor_score > 0.3`; `child_friendly` yêu cầu `suitable_for_children=True`; `avoid_long_walking` yêu cầu `indoor_score > 0.5`.

**Đầu ra:** Tối đa 30 ứng viên, với địa điểm bắt buộc được đặt lên đầu.

---

### Bước 3 — Dịch Vụ Thời Tiết

**Tệp:** `step3_weather.py` · **Thuật toán:** Tổng hợp thời tiết đa nguồn với cache TTL

**Sử dụng:** API **Open-Meteo** miễn phí (không cần khóa API) cho nhiệt độ, lượng mưa, chỉ số UV. **OpenWeatherMap** tùy chọn cho PM2.5 và AQI. Cache LRU theo tọa độ với `weather_cache_ttl=3600` (1 giờ).

**Tại sao dùng Open-Meteo:** Miễn phí, không cần khóa API, phủ toàn cầu, trả về dự báo theo giờ lên đến 16 ngày. Không giới hạn tốc độ ở bậc miễn phí.

**Phạm vi:** Lấy `max(duration_days, 3)` ngày dự báo. Với chuyến 5 ngày = 5 × 24 = 120 điểm dữ liệu mỗi địa điểm.

---

### Bước 4 — Chấm Điểm Địa Điểm

**Tệp:** `step4_scoring.py` · **Thuật toán:** Điểm tổng hợp có trọng số 7 chiều với tái chuẩn hóa trọng số động

**Sử dụng:** Khớp sở thích tín dụng một phần (từ Bước 2), điểm phổ biến/lịch sử suy diễn từ heuristic danh mục, phạt thời tiết theo giờ, suy giảm khoảng cách logarit, điểm khả năng tiếp cận từ indoor_score + thời lượng + ràng buộc, phù hợp ngân sách từ ticket_price vs ngưỡng budget_level.

#### Trọng Số Cơ Bản

| Chiều | Trọng Số | Nguồn |
|-------|----------|-------|
| Khớp sở thích | 0.30 | Tương đồng danh mục tín dụng một phần |
| Tầm quan trọng lịch sử | 0.20 | Suy diễn từ danh mục + bậc tỉnh |
| Phù hợp thời tiết | 0.15 | Khớp dự báo theo giờ |
| Khoảng cách | 0.15 | Suy giảm logarit |
| Độ phổ biến | 0.10 | Suy diễn từ danh mục + bậc tỉnh |
| Khả năng tiếp cận | 0.05 | Điểm trong nhà + thời lượng + ràng buộc |
| Phù hợp ngân sách | 0.05 | Giá vé vs mức ngân sách |

#### Tái Chuẩn Hóa Trọng Số Động

Khi người dùng yêu cầu rõ ràng ràng buộc về khả năng tiếp cận hoặc ngân sách:

| Điều Kiện | Tăng |
|-----------|------|
| `elderly_friendly` hoặc `child_friendly` | accessibility: 0.05 → 0.15 |
| `budget_level = "low"` | budget: 0.05 → 0.15 |

**Tại sao dùng trọng số động:** Người dùng yêu cầu `elderly_friendly` cần khả năng tiếp cận ảnh hưởng không cân xứng đến kết quả. Không có trọng số động, accessibility chỉ đóng góp 5% — gần như không có tác dụng.

#### Công Thức Điểm Số

**Độ Phổ Biến Suy Diễn (0.45–0.95):** Tổng hợp từ danh mục + bậc tỉnh, giới hạn 0.95.

**Tầm Quan Trọng Lịch Sử Suy Diễn (0.45–0.95):** UNESCO +0.30, history +0.15, museum +0.10, architecture +0.08, spiritual +0.05, craft_village +0.03, long_description +0.02, bậc tỉnh +0.01–0.08. Giới hạn 0.95.

**Tại sao suy diễn:** Các địa điểm được tuyển chọn có sẵn trường `popularity_score` và `historical_importance_score`, nhưng địa điểm thu thập từ web/OSM có thể thiếu. Công thức suy diễn cung cấp đường cơ sở nhất quán từ dữ liệu danh mục có sẵn.

#### Bậc Tỉnh

| Bậc | Thưởng | Tỉnh |
|-----|--------|------|
| Bậc 1 | +0.08 | Hà Nội, Huế, Quảng Nam (Hội An) |
| Bậc 2 | +0.06 | TP. Hồ Chí Minh, Đà Nẵng |
| Bậc 3 | +0.05 | Ninh Bình, Quảng Ninh |
| Bậc 4 | +0.04 | Hải Phòng, Khánh Hòa, Lào Cai, Hà Giang, Lâm Đồng |
| Bậc 5 | +0.03 | Cần Thơ, Bình Định, Thanh Hóa, Nghệ An, Bắc Ninh |
| Mặc định | +0.02 | Tất cả các tỉnh khác |

#### Phạt Thời Tiết Theo Giờ

Sử dụng giờ dự báo gần nhất với thời gian tham quan thực tế:

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

**Tại sao khớp theo giờ:** Một địa điểm lúc 08:00 không nên bị phạt thời tiết do cơn giông lúc 14:00. Trung bình ngày làm mờ sự khác biệt này.

#### Điểm Khoảng Cách Logarit

```
dist_score = max(0.15, 1.0 / (1.0 + dist_km / 20.0))
```

**Tại sao logarit:** Suy giảm tuyến tính (`1 − dist/max_dist`) phạt quá nặng các địa điểm gần. Một địa điểm cách 5 km gần như dễ tiếp cận như địa điểm cách 1 km khi lái xe. Logarit giảm nhanh ban đầu (0→10 km) rồi phẳng dần, phù hợp với thực tế lái xe.

---

### Bước 4b — Xếp Hạng Đa Dạng MMR

**Tệp:** `mmr_rerank.py` · **Thuật toán:** Maximal Marginal Relevance (Carbonell & Goldstein, 1998)

**Sử dụng:** Chọn tham lam với λ = 0.7 (70% liên quan, 30% đa dạng). Độ tương đồng pha trộn: 60% khoảng cách địa lý (giới hạn 10 km) + 40% độ trùng danh mục Jaccard.

```
MMR(địa_điểm) = λ · điểm(địa_điểm) − (1−λ) · max_đã_chọn similarity(địa_điểm, đã_chọn)
```

**Tại sao dùng MMR:** Không có MMR, 3 địa điểm điểm cao nhất thường nằm trong cùng khu vực (VD: Văn Miếu, Hoàng Thành, Hồ Gươm đều trong bán kính 2 km ở trung tâm Hà Nội). MMR đẩy các địa điểm điểm thấp hơn nhưng đa dạng địa lý (VD: làng gốm Bát Tràng, cách 15 km) vào nhóm ứng viên.

**Tại sao λ = 0.7:** Chọn theo thực nghiệm để cân bằng liên quan-đa dạng cho 3–7 địa điểm/ngày.

---

### Bước 5 — Phân Chia Ngày TTDP (Chọn Lọc + Sắp Xếp Ban Đầu)

**Tệp:** `ttdp_solver.py`, `step5_ttdp.py` · **Thuật toán:** Team Orienteering Problem with Time Windows (OPTW) qua Google OR-Tools

**Sử dụng:** OR-Tools Routing Solver với `PATH_CHEAPEST_ARC` khởi tạo, `GUIDED_LOCAL_SEARCH` metaheuristic, và phạt disjunction cho POI tùy chọn. Ma trận khoảng cách tính bằng haversine vectorized trong NumPy.

**Mô hình hóa bài toán:**

Bài toán Thiết Kế Chuyến Đi Du Lịch (TTDP) được mô hình hóa thành **Orienteering Problem with Time Windows (OPTW):**
- **Nút:** 0 = neo xuất phát, 1 = neo kết thúc, 2..N+1 = POI ứng viên
- **N xe** = N ngày du lịch, mỗi xe bắt đầu tại nút 0, kết thúc tại nút 1
- **Mục tiêu:** Tối đa hóa tổng điểm thu thập trên tất cả các ngày
- **Ràng buộc:** Mỗi ngày ≤ 8 giờ; mỗi POI ≤ 1 lần ghé; cửa sổ thời gian được tôn trọng
- **Phạt:** `điểm × 1,000,000` cho việc bỏ qua POI (điểm cao hơn → chi phí bỏ qua cao hơn)

**Tại sao dùng OR-Tools:** OR-Tools cung cấp lập trình ràng buộc đã được kiểm chứng với metaheuristic tìm kiếm cục bộ tích hợp. Thư viện Routing xử lý disjunctions (nút tùy chọn), cửa sổ thời gian, và cấu hình đa xe (đa ngày) sẵn có. Các lựa chọn thay thế như thuật toán di truyền tự viết hoặc simulated annealing cần điều chỉnh đáng kể để đạt chất lượng tương đương.

**Tại sao dùng haversine ở bước này:** Bước 5 cần nhanh chóng khám phá POI nào thuộc ngày nào — đây là bài toán chọn tổ hợp, không phải bài toán định tuyến chính xác. Haversine là O(1) mỗi cặp, chạy hoàn toàn trong tiến trình, và đủ chính xác để phân chia POI giữa các ngày. Độ chính xác khoảng cách đường thực tế được áp dụng trong Bước 6 sau khi phân công ngày đã cố định.

**Thời gian giải:** 2 giây (có thể cấu hình). GLS hội tụ nhanh cho 15–30 POI trên 3–5 ngày.

**Dự phòng:** Nếu OR-Tools thất bại (VD: cửa sổ thời gian không khả thi), dự phòng bằng chọn tham lam Top-N theo điểm số.

---

### Bước 6 — Sắp Xếp Lại Theo Khoảng Cách Đường OSRM

**Tệp:** `step6_routing.py`, `step6_geometry.py` · **Thuật toán:** TSP đường mở có neo cố định với tìm kiếm chính xác (≤8 địa điểm) hoặc láng giềng gần nhất + heuristic 2-opt, tối ưu trên thời gian lái xe OSRM

**Sử dụng:** OSRM table API cho thời gian lái xe có hướng giữa tất cả các cặp địa điểm + neo; OSRM route API cho hình học polyline. `lru_cache` (512 mục) cho kết quả table. `asyncio.to_thread` cho I/O mạng không chặn.

**Tại sao cần bước này:** Bộ giải TTDP của Bước 5 tối ưu *địa điểm nào* thuộc *ngày nào* bằng khoảng cách haversine (đường chim bay). Nhưng một địa điểm bên kia sông hoặc sau núi có thể cách 500 m theo đường chim bay nhưng 5 km theo đường bộ. Bước 6 sắp xếp lại tập POI cố định của mỗi ngày để tối thiểu hóa thời gian di chuyển thực tế bằng thời gian lái xe OSRM.

**Thuật toán — `optimize_route_open()`:**

1. **Một yêu cầu OSRM table duy nhất mỗi ngày** bao gồm tất cả neo: `[neo_đầu?, site_1, ..., site_n, neo_cuối?]`. Mọi cặp có hướng sử dụng cùng đơn vị thời gian đường bộ — không chuyển đổi haversine sang giây.

2. **Neo được cố định ngoài hoán vị địa điểm.** Chi phí của một thứ tự địa điểm là:
   ```
   cost = duration(xuất_phát → site_đầu)
        + Σ duration(site_i → site_{i+1})
        + duration(site_cuối → kết_thúc)
   ```
   Chỉ thứ tự địa điểm được hoán vị; neo giữ nguyên vị trí cố định 0 và N+1.

3. **Tìm kiếm chính xác** cho ≤ 8 địa điểm: đánh giá tất cả `n!` hoán vị (tối đa 40,320 cho n=8). Sử dụng `itertools.permutations` với tính chi phí trực tiếp.

4. **Heuristic** cho > 8 địa điểm: láng giềng gần nhất đa điểm xuất phát (mỗi địa điểm làm điểm đầu tiên tiềm năng) sau đó tìm kiếm cục bộ 2-opt trên đường mở. Ứng viên rẻ nhất được chọn.

5. **Kiểm tra ma trận:** Từ chối ma trận không vuông, NaN, vô hạn, hoặc không khớp kích thước. Khi thất bại, giữ nguyên thứ tự TTDP — không thay thế bằng haversine.

**Tại sao tìm kiếm chính xác cho ≤ 8:** Hành trình ngày điển hình có 3–7 POI. Tìm kiếm toàn diện trên 7! = 5,040 hoán vị là tức thời (~1 ms) và đảm bảo tối ưu.

**Tại sao 2-opt đường mở:** 2-opt TSP tiêu chuẩn giả định tour khép kín (điểm cuối → điểm đầu). Hành trình ngày là đường mở (xuất phát → địa điểm → kết thúc). Phiên bản đường mở chỉ đánh giá `n−1` cạnh và loại trừ cạnh vòng.

**Ma trận khoảng cách cho Bước 8:** Ma trận OSRM mỗi ngày được lắp ráp thành ma trận toàn cục khối chéo. Mục chéo ngày giữ NaN → Bước 8 dự phòng haversine cho khoảng cách liên ngày. Điều này tránh yêu cầu OSRM table toàn cục trùng lặp.

**Kiểm tra thời lượng:** Sau khi sắp xếp, tổng thời gian đường bộ + thời gian tham quan được so sánh với ngân sách 8 giờ/ngày. Ngày vượt ngân sách được ghi log cảnh báo (không phải lỗi).

**Hình học:** Tọa độ polyline được lấy từ OSRM route API *sau khi* sắp xếp lại, để tuyến đường vẽ theo thứ tự đã tối ưu.

---

### Bước 7 — Tạo Kế Hoạch Ngày

**Tệp:** `step7_dayplan.py`, `step5_clustering.py` · **Thuật toán:** Xây dựng kế hoạch theo ngày với dự phòng địa lý

**Sử dụng:** Các cụm đã tối ưu từ Bước 5/6 (đã sắp xếp theo khoảng cách đường bộ). Khung giờ bắt đầu từ 08:00 và tăng dần dựa trên thời gian di chuyển (từ OSRM khi có) + thời lượng tham quan. Giới hạn nhịp độ: `relaxed` = 3 địa điểm/ngày, `moderate` = 5, `packed` = 7.

**Dự phòng phân cụm:** Nếu TTDP thất bại, các địa điểm được chia theo ngày bằng round-robin địa lý theo vĩ độ. Địa điểm bắt buộc được phân phối đều làm hạt giống, sau đó các địa điểm còn lại được gán cho trọng tâm ngày gần nhất.

**Tại sao round-robin theo vĩ độ:** Đơn giản, xác định, và tạo nhóm ngày gọn địa lý mà không cần sklearn KMeans. Với hầu hết các tỉnh Việt Nam có bố cục bắc-nam rõ ràng, sắp xếp theo vĩ độ tạo ranh giới ngày tự nhiên.

---

### Bước 8 — Lắp Ráp Hành Trình

**Tệp:** `step8_assembly.py` · **Thuật toán:** Điểm chất lượng có trọng số 7 chiều với tính khoảng cách hai lượt

**Sử dụng:** Khoảng cách đường thực tế OSRM từ ma trận khối chéo (Bước 6), với dự phòng haversine cho mọi mục NaN/None. Chèn nhà hàng (chưa kích hoạt). Phù hợp ngân sách từ giá vé thực tế. Tạo tóm tắt tiếng Việt.

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

**Tính khoảng cách hai lượt:**

- **Lượt 1 (OSRM):** `_lookup_distance()` truy vấn ma trận khối chéo cho các cặp liên tiếp cùng ngày. Trả về khoảng cách lái xe thực tế (mét).
- **Lượt 2 (Haversine):** Dự phòng `haversine(lat1, lng1, lat2, lng2)` cho mọi mục liên ngày hoặc không có sẵn.

Cả hai lượt đóng góp vào `total_distance` trong `total_distance_km`, đảm bảo điểm chất lượng phản ánh tất cả khoảng cách bất kể OSRM có sẵn cho từng ngày riêng lẻ.

---

## Nguồn Dữ Liệu

| Tệp | Nội Dung |
|------|----------|
| `data/curated_heritage.json` | 830+ địa điểm trên 63 tỉnh thành |
| `data/curated_restaurants.json` | Dữ liệu nhà hàng được tuyển chọn |
| `data/crawled_heritage.json` | Di sản thu thập từ web (370 mục) |
| `data/deepseek_clean.json` | Dữ liệu di sản đã AI làm sạch |
| `data/deepseek_enriched.json` | Mô tả địa điểm đã AI làm giàu |
| `data/geocode_cache.json` | Kết quả mã hóa địa lý Nominatim |

### Danh Mục Di Sản (8 loại)
`history`, `nature`, `spiritual`, `architecture`, `entertainment`, `museum`, `unesco`, `craft_village`

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

## Kiểm Thử

```bash
# Chạy tất cả kiểm thử
python -m pytest tests/ -v

# Tệp kiểm thử riêng lẻ
python tests/test_heritage_model.py         # 16 kiểm thử xác thực mô hình
python tests/test_heritage_position.py      # 12 kiểm thử tọa độ/vị trí
python tests/test_heritage_data_quality.py  # 14 kiểm thử chất lượng dữ liệu
python tests/test_heritage_route_position.py # 10 kiểm thử neo tuyến đường
python tests/test_road_routing.py           # 6 kiểm thử tối ưu tuyến
python tests/test_phase1_enhancements.py    # 105 kiểm thử công thức điểm
python tests/test_all_input_fields.py       # 53 kiểm thử chuẩn hóa đầu vào
python tests/test_logging.py                # 50 kiểm thử logging
python tests/test_province_fix.py           # 40 kiểm thử chuẩn hóa tỉnh
python tests/test_all_provinces.py          # 226 kiểm thử phủ tỉnh
```

Tổng: **532 kiểm thử** trên 11 tệp.

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
| `LOG_LEVEL` | `INFO` | Mức logging: `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_DIR` | (trống) | Thư mục cho tệp log xoay vòng (JSON Lines) |
| `LOG_FILE` | `heritage.log` | Tên tệp log khi `LOG_DIR` được đặt |
| `AI_SERVICE_URL` | `http://localhost:8001` | Địa chỉ AI service (API gateway dùng) |
| `ROUTE_CACHE_TTL` | `86400` | TTL cache kết quả OSRM (giây) |
| `WEATHER_CACHE_TTL` | `3600` | TTL cache dự báo thời tiết (giây) |
| `CANDIDATE_CACHE_TTL` | `86400` | TTL cache địa điểm ứng viên (giây) |

---

## Chạy Hệ Thống

```bash
pip install -r requirements.txt
docker compose up -d   # khởi động API gateway + AI service + OSRM
```

### API Endpoints

| Phương Thức | Endpoint | Mô Tả |
|------------|----------|-------|
| `POST` | `/api/v1/trips/recommend` | Tạo lịch trình du lịch di sản |
| `POST` | `/api/v1/recommend` | Bí danh cho `/api/v1/trips/recommend` |
| `POST` | `/api/v1/routes/plan` | Lập kế hoạch tuyến xuất phát/kết thúc cố định |
| `GET`  | `/api/v1/heritage-sites` | Liệt kê tất cả di sản |
| `GET`  | `/api/v1/heritage-sites/{id}` | Xem chi tiết địa điểm |
| `GET`  | `/api/v1/heritage-sites/{id}/images` | Xem ảnh địa điểm |
| `GET`  | `/api/v1/heritage-sites/{id}/reviews` | Xem đánh giá |
| `GET`  | `/api/v1/heritage-sites/{id}/enrich` | Xem mô tả làm giàu |
| `GET`  | `/api/v1/heritage-sites/{id}/narrate` | Xem tường thuật địa điểm |
| `GET`  | `/api/v1/health` | Kiểm tra sức khỏe |
| `GET`  | `/docs` | Swagger UI |

### Ví Dụ Request

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

### Logging

- **Dev cục bộ** (terminal TTY): đầu ra ANSI có màu với thời gian từng bước
- **Production / Docker** (non-TTY): định dạng JSON Lines cho tổng hợp log (ELK, Grafana, v.v.)
- **Ghi file log**: đặt `LOG_DIR=/app/logs` để bật đầu ra file xoay vòng (10 MB mỗi file, 5 bản sao lưu)
- Mỗi request nhận header `X-Request-ID` để truy vết qua các service
