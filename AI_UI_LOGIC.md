# Heritage Travel System - Logic & AI Algorithms

## 1. UI Logic (Logic Giao Diện)

### English
The User Interface (UI) in `App.jsx` handles the workflow for planning a heritage trip intuitively.
- **Planner Dialog**: A multi-step wizard modal guides the user through the process.
  - **Step 1 (Regions & Sites)**: Users can select one or more provinces. Once selected, users can either pick specific heritage sites or leave it blank to let AI recommend sites based on their textual preferences (interests).
  - **Minimize to Map**: To solve the issue of the modal blocking the map view, a new "Minimize to view map" (Thu nhỏ để chọn trên bản đồ) button has been added. Users can also manually close the modal using the `x` button.
  - **Floating Return Button**: If the user minimizes or closes the modal while actively configuring a trip (e.g., provinces are selected but the route is not yet generated), a floating action button labeled "Quay lại lịch trình" (Return to Planner) appears at the bottom-center of the screen. This allows users to freely interact with the map, click on sites, and quickly resume their planning.
  - **Step 2 & 3 (Departure & Routing)**: Users define their starting/ending points, duration, transport mode, and advanced constraints (avoid tolls, max distance, max duration).
- **Visualization**: Once the AI or OSRM backend returns the itinerary, the UI clears the modal and overlays the optimized multi-day routes onto the maplibregl instance, complete with colorful paths, markers, and a side-panel summarizing the itinerary.

### Tiếng Việt
Giao diện người dùng (UI) trong `App.jsx` quản lý luồng công việc lên lịch trình di sản một cách trực quan.
- **Planner Dialog**: Một hộp thoại đa bước hướng dẫn người dùng qua từng giai đoạn.
  - **Bước 1 (Vùng đất & Di sản)**: Người dùng chọn một hoặc nhiều tỉnh. Sau khi chọn, người dùng có thể ghim các điểm bắt buộc hoặc để trống để AI tự động gợi ý dựa trên sở thích nhập bằng văn bản.
  - **Thu nhỏ xem bản đồ**: Để giải quyết vấn đề hộp thoại che khuất bản đồ, hệ thống bổ sung nút "Thu nhỏ để chọn trên bản đồ". Người dùng cũng có thể tắt hộp thoại bằng nút `x`.
  - **Nút Quay lại nổi (Floating Button)**: Nếu người dùng ẩn hộp thoại khi đang cấu hình dở dang (đã chọn tỉnh nhưng chưa tạo lịch trình), một nút nổi ở cạnh dưới màn hình với dòng chữ "Quay lại lịch trình" sẽ xuất hiện. Điều này giúp người dùng tự do tương tác, xem bản đồ và dễ dàng gọi lại hộp thoại bất cứ lúc nào.
  - **Bước 2 & 3 (Khởi hành & Lộ trình)**: Chọn điểm đi/đến, thời gian chuyến đi, phương tiện, và các giới hạn như tránh trạm thu phí hay giới hạn số km.
- **Hiển thị**: Khi backend trả về lịch trình, giao diện sẽ tự động ẩn hộp thoại, vẽ đường đi (route) nhiều ngày lên bản đồ với màu sắc phân biệt, ghim các điểm dừng và hiển thị một bảng tóm tắt bên phải màn hình.

---

## 2. AI Recommendation Algorithm (Thuật toán Gợi ý AI)

### English
The backend recommendation engine solves a highly complex real-world variant of the **Tourist Trip Design Problem (TTDP)**. The objective is to maximize user satisfaction (score) while strictly adhering to time budgets and opening hours over a multi-day trip.

- **Previous Approach (Naive Clustering + TSP)**: 
  Originally, the system scored all candidate sites, grouped them into day-clusters using geographic K-Means, and optimized each day's route individually using the Nearest Neighbor and 2-opt algorithms. This approach was flawed because it separated clustering from routing, potentially grouping sites that take too long to travel between in a single day.
- **New Approach (OR-Tools Constraint Solver)**:
  The algorithm is now modeled as an **Orienteering Problem with Time Windows (OPTW)** and solved using **Google OR-Tools** (Vehicle Routing solver).
  1. **Scoring**: Each candidate site is scored based on user interests (TF-IDF/Semantic overlap), popularity, accessibility (e.g., suitable for elderly), and forecasted weather conditions.
  2. **Time Matrix**: The system computes a full distance/time matrix between all points using Haversine distances scaled by transport speeds.
  3. **Constraints**:
     - Vehicles represent `num_days`.
     - Time dimension limits each day to a maximum time budget (e.g., 8 hours).
     - Site visit durations are strictly accounted for (e.g., a museum requires 2 hours).
     - Optional Sites (Disjunctions): Sites are added as optional nodes with a heavy penalty equal to their `score * 1,000,000`. 
  4. **Optimization**: OR-Tools attempts to minimize the total cost (travel time + penalties). Because high-scoring sites have massive penalties if skipped, the solver is heavily incentivized to visit the most relevant and high-scoring sites while fitting them perfectly into the daily time constraints.
  5. **Routing**: The selected optimal sequence is then passed to the OSRM backend to fetch the exact geographic polyline for mapping.

### Tiếng Việt
Hệ thống gợi ý backend giải quyết một biến thể phức tạp trong thực tế của bài toán **Tourist Trip Design Problem (TTDP)**. Mục tiêu là tối đa hóa sự hài lòng (điểm sở thích) của người dùng trong khi phải tuân thủ nghiêm ngặt ngân sách thời gian và thời lượng tham quan trong một chuyến đi nhiều ngày.

- **Cách tiếp cận cũ (Clustering + TSP cơ bản)**:
  Trước đây, hệ thống tính điểm các điểm đến, chia chúng vào các ngày bằng thuật toán K-Means theo khoảng cách địa lý, sau đó tìm đường cho từng ngày bằng Nearest Neighbor và 2-opt. Cách này có nhược điểm lớn vì việc phân cụm tách biệt với tìm đường dễ dẫn đến việc một ngày phải đi lại quá nhiều do nhét các điểm không thuận đường vào cùng cụm.
- **Cách tiếp cận mới (OR-Tools Constraint Solver)**:
  Bài toán nay được mô hình hóa dưới dạng **Orienteering Problem with Time Windows (OPTW)** và giải bằng bộ giải **Google OR-Tools** (Vehicle Routing solver).
  1. **Tính điểm (Scoring)**: Mỗi điểm được chấm điểm dựa trên độ trùng khớp sở thích (bằng văn bản người dùng nhập), độ nổi tiếng, tính tiếp cận (VD: phù hợp người cao tuổi) và tình hình thời tiết dự báo.
  2. **Ma trận thời gian**: Hệ thống tính toán ma trận thời gian đi lại giữa tất cả các điểm dựa trên khoảng cách.
  3. **Ràng buộc (Constraints)**:
     - Số lượng xe (Vehicles) đại diện cho số ngày của chuyến đi (`num_days`).
     - Ràng buộc thời gian (Time Dimension) giới hạn tổng thời gian mỗi ngày (VD: tối đa 8 tiếng đi lại và tham quan).
     - Thời gian lưu trú tại mỗi điểm được tính toán đầy đủ (VD: bảo tàng mất 2 tiếng).
     - Điểm tự chọn (Disjunctions): Các điểm không bắt buộc sẽ được đưa vào mô hình với "hình phạt" (penalty) rất lớn tỉ lệ thuận với điểm số (`score * 1,000,000`).
  4. **Tối ưu hóa**: OR-Tools tối ưu hóa bằng cách cực tiểu hóa tổng chi phí (thời gian đi lại + hình phạt khi bỏ qua các điểm). Do các điểm phù hợp với sở thích có hình phạt rất cao nếu bị bỏ qua, thuật toán buộc phải chọn ra một tổ hợp các điểm đến tốt nhất, có tổng điểm cao nhất sao cho xếp vừa vặn vào quỹ thời gian trong ngày.
  5. **Tìm đường (Routing)**: Chuỗi các điểm tối ưu sau đó được gửi đến OSRM để lấy đường vẽ tọa độ chính xác (polyline) hiển thị lên bản đồ.
