# Heritage Map - System Logic & Algorithms / Logic Hệ thống & Thuật toán AI

This document explains the core UI logic and AI algorithms driving the Heritage Travel system.
Tài liệu này giải thích logic giao diện người dùng và các thuật toán AI cốt lõi vận hành hệ thống Du lịch Di sản.

## 1. UI Flow & State Management (Logic Giao diện)

### Modal & Planner Flow (Luồng Lên lịch trình)
- **Step 1: Location & Interests (Vùng đất & Sở thích)**
  - Users select one or more provinces. (Người dùng chọn một hoặc nhiều tỉnh thành).
  - Users select explicit heritage sites to visit, OR check their interests (e.g. History, Nature) for AI recommendations. (Người dùng chọn các điểm đến cụ thể, HOẶC tick chọn sở thích để AI tự gợi ý).
  - *Auto-hide Modal (Tự động ẩn Modal):* Users can close the modal to interact with the map. A "Return to planner" (Quay lại lịch trình) button will float on the screen to restore the modal. (Người dùng có thể thu nhỏ modal để xem bản đồ. Nút "Quay lại lịch trình" sẽ hiện nổi để mở lại modal).

- **Step 2: Start & End Points (Khởi hành & Hồi trình)**
  - Users define where the trip starts and ends. (Xác định điểm xuất phát và kết thúc).
  - Support for geolocation, text search (Nominatim), and map-picking. (Hỗ trợ định vị, tìm kiếm địa chỉ, và chọn trực tiếp trên bản đồ).

- **Step 3: Constraints (Giới hạn lộ trình)**
  - Users configure trip duration (days), transportation mode (driving, walking, motorbike), and max distance/time. (Thiết lập số ngày, phương tiện, giới hạn quãng đường/thời gian).

### Interactive Map (Bản đồ Tương tác)
- Built with MapLibre GL JS. Markers dynamically render based on current filters and active route.
- (Xây dựng bằng MapLibre GL JS. Các điểm đánh dấu tự động hiển thị theo bộ lọc và lộ trình).

## 2. AI Recommendation & Routing (Thuật toán Gợi ý & Lộ trình AI)

### Candidate Filtering & Scoring (Lọc & Chấm điểm ứng viên)
- **Distance & Region (Khoảng cách & Khu vực):** Filter sites belonging to the selected provinces.
- **Weather Constraint (Ràng buộc thời tiết):** Uses Open-Meteo API. If the probability of heavy rain is high (> 70%), outdoor sites are penalized.
- **Semantic Matching (So khớp ngữ nghĩa):** If the user selects interests (e.g., "Kiến trúc"), the AI computes a similarity score between the user's interests and the site's categories/description.
- **Hybrid Score (Điểm tổng hợp):** `Score = (Popularity * 0.4) + (Historical Importance * 0.3) + (Interest Match * 0.3)`.

### Route Assembly (Team Orienteering Problem)
- **Problem formulation (Mô hình bài toán):** The system models the itinerary as a Team Orienteering Problem with Time Windows (TOPTW). The goal is to maximize the sum of scores of visited sites while respecting the time budget per day and travel time between nodes.
- **Solver (Bộ giải):** Google OR-Tools is used to find the optimal sequence of visits.
- **Cost Matrix (Ma trận chi phí):** The OSRM routing engine calculates the actual travel time and distance matrix between all candidate sites.
- **Assembly (Ghép lịch trình):** 
  - The solver assigns sites to specific "vehicles" (which represent Days in the trip).
  - Each site requires a visit duration (default 1-2 hours) and opens/closes at specific times.
  - The final output includes realistic travel times, distances, and expected arrival times.

### Natural Language Generation (Tạo ngôn ngữ tự nhiên)
- Currently, the system uses a heuristic-based summarizer to generate a brief overview of the trip. Future iterations will integrate a Large Language Model (LLM) for personalized storytelling based on the generated route.
