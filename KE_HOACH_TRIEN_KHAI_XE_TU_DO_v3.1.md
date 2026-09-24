# KẾ HOẠCH TRIỂN KHAI ĐỒ ÁN XE MÔ HÌNH TỰ ĐỖ
## Phần mềm và nhận thức trước — tích hợp xe thật sau

**Phiên bản:** v3.1  
**Ngày biên soạn:** 19/09/2026  
**Tài liệu cơ sở:** `KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.0.md` và các quyết định mới nhất trong cuộc trao đổi.  
**Mục đích:** hướng dẫn làm việc theo từng giai đoạn, gắn với từng đợt mua; chỉ rõ việc làm khi chưa có linh kiện, khi nhận được linh kiện, sản phẩm phải bàn giao và điều kiện chuyển bước.

> **Phạm vi giữ nguyên:** MN300 Tank300 1/12 + laptop xử lý chính + LiDAR toàn cục + bốn camera USB nhận thức cục bộ + một ESP32-S3 điều khiển cấp thấp. Người dùng chọn vị trí/hướng đỗ. Hệ thống lập đường, tự đỗ có phản hồi và xử lý vật cản bất ngờ bằng dừng — cập nhật — đánh giá lại — lập đường mới khi đủ điều kiện.
>
> Đây là kế hoạch thực hiện và kiểm chứng, không phải xác nhận phần cứng đã mua, đã tương thích hoặc đã đạt các chỉ tiêu. Không xem các mốc đề xuất là kết quả thực nghiệm.

---

## MỤC LỤC

1. Cấu hình và phạm vi hiện hành.
2. Luồng hệ thống và nguyên tắc triển khai.
3. Sáu đợt mua và điều kiện mua tiếp.
4. Giai đoạn 0 — phần mềm thuần và mô phỏng.
5. Giai đoạn 1 — LiDAR và một camera mẫu.
6. Giai đoạn 2 — bốn camera USB và BEV cục bộ.
7. Giai đoạn 3 — hợp nhất cảm biến trên bàn thử.
8. Giai đoạn 4 — tiếp nhận và đo đặc tính MN300.
9. Giai đoạn 5 — ESP32-S3 và điều khiển có phản hồi.
10. Giai đoạn 6 — nguồn và kiểm chứng dừng an toàn.
11. Giai đoạn 7 — chuyển cụm cảm biến lên xe.
12. Giai đoạn 8 — hợp nhất toàn cục/cục bộ trên xe chuyển động.
13. Giai đoạn 9 — tự đỗ thật và xử lý vật cản.
14. Giai đoạn 10 — đánh giá và hoàn thiện khóa luận.
15. Bảng công việc khi thiếu linh kiện hoặc linh kiện về không cùng lúc.
16. Bảng mục tiêu đo lường và tiêu chí hoàn thành V1.
17. Hồ sơ bàn giao, các điểm chưa chốt và kế hoạch bắt đầu ngay.
18. Link nguồn mua đã được người dùng cung cấp.

---

# 1. CẤU HÌNH VÀ PHẠM VI HIỆN HÀNH

### 1.1. Các phần đã thống nhất về chức năng

| Thành phần | Vai trò trong dự án | Trạng thái lựa chọn |
|---|---|---|
| **MN300 Tank300 1/12 4WD RTR** | Xe nền, tận dụng cơ khí, truyền động, motor và servo phù hợp. | Thay HSP theo quyết định của người dùng; chưa mặc định bộ điện thực giao đã nhận lệnh từ ESP32. |
| **Laptop** | Camera, AI/CV, SLAM/định vị, hợp nhất dữ liệu, lập đường, điều khiển cấp cao, giao diện và ghi log. | Giữ là bộ não; cấu hình máy thực tế cần ghi lại để đo hiệu năng. |
| **RPLIDAR C1/C1M1** | Cấp bản quét cho phần mềm dựng bản đồ 2D, định vị và cập nhật hình học vật cản. | Kiểm tra đúng bộ, adapter, dây và nguồn trước khi đặt. |
| **4 camera USB UVC** | Trước, sau, trái, phải; nhận thức cục bộ, vùng trống/vật cản, BEV và quan sát quanh xe. | Theo BOM mới: thử mẫu AdaChoi 1080p phân loại **130°**. Định nghĩa góc nhìn và mode thực còn cần xác minh. |
| **Hub USB và cáp** | Đưa bốn luồng ảnh về laptop bằng dây. | UGREEN 50985 là ứng viên đã nêu; ORICO W5P-U3 là phương án thay được cân nhắc, chưa bắt buộc đổi. |
| **1 ESP32-S3 chính** | Đọc cảm biến, xuất lệnh cho ESC/servo, giám sát mất lệnh và gửi telemetry. | Không dùng ESP32-S3 để truyền bốn luồng camera. |
| **AS5600 + nam châm** | Phản hồi góc tại cơ cấu lái sau khi xác định vị trí gá và hiệu chuẩn. | Chưa chốt thiết kế gá; góc đo ở trục cảm biến chưa tự đồng nghĩa góc bánh. |
| **MT6701 hoặc encoder phù hợp** | Phản hồi chuyển động quay, quy đổi sang tốc độ/quãng đường. | Kiểm tra chân tín hiệu, cấu hình, vị trí gá và tỷ số truyền trước khi chốt. |
| **BNO085** | Dữ liệu quán tính/hướng để hỗ trợ ước lượng trạng thái. | Không coi là nguồn vị trí tuyệt đối độc lập. |
| **Khoảng 4 VL53L1X** | Giám sát khoảng cách gần tại các hướng được giao nhiệm vụ. | Thử 2 trước; hoàn thiện số lượng/vị trí theo vùng quan sát thực. |
| **Nguồn, cầu chì, E-stop và phần tử ngắt động lực** | Cấp điện đúng tải, bảo vệ và thực hiện dừng khi có lỗi. | Chưa mặc định UBEC/XL4015, cầu chì 15 A hay công tắc ghi 30 A đều phù hợp. |

**Cập nhật 24/09/2026 (tình trạng nhận hàng; lựa chọn trong bảng giữ nguyên):** đã nhận RPLIDAR C1 (22/09; adapter CP2102N, cổng COM4; model in trên nhãn chưa ghi), bốn camera USB "HD Camera" (VID 1BCF/PID 0B09; 130° theo nhà bán, góc nhìn thực chưa đo) và một hub UGREEN 4 cổng (23/09; mã model chưa ghi). Mode công bố của camera đã liệt kê trong [camera_modes.csv](autopark/docs/camera_modes.csv). Chưa nhận MN300, ESP32-S3, BNO085, VL53L1X, AS5600, encoder; linh kiện nguồn/E-stop chưa có trong kiểm kê. Xem [kiểm kê phần cứng](autopark/docs/hardware_inventory.md) và mục 17.4.

**Những cấu hình cũ không được tự đưa trở lại:** HSP làm xe nền mặc định; camera truyền video qua Wi-Fi; bốn ESP32-CAM; máy tính trên xe thay laptop; LiDAR bị bỏ khỏi V1.

**Đường điều khiển laptop–ESP32:** chưa coi việc đổi camera sang USB là quyết định tự động chốt toàn bộ liên lạc điều khiển. USB dùng thử trên bàn là phương án triển khai; cần ghi rõ đường điều khiển được chọn khi tích hợp xe.

### 1.2. V1 phải làm gì?

Người dùng đặt đích trên giao diện; xe tìm và thực hiện quỹ đạo tiến/lùi phù hợp cơ cấu lái. LiDAR cung cấp bản đồ/định vị; bốn camera cung cấp nhận thức cục bộ. Khi có vật cản hoặc dữ liệu cần thiết không còn hợp lệ, hệ thống dừng và đánh giá lại.

**Không bắt buộc trong V1:** nhận diện vạch đỗ, tự tìm ô đỗ, tự lái đến bãi từ nơi khác, điều khiển end-to-end bằng mạng neural, MPC nâng cao, dự đoán chuyển động người hoặc tái dựng 3D toàn cảnh.

### 1.3. Lưu ý bổ sung so với v3.0 — không phải thay đổi kiến trúc

Bản này giữ 11 giai đoạn và 6 nhóm mua, nhưng ghi rõ những phụ thuộc mà v3.0 chưa thể hiện đầy đủ:

- **Đọc IMU/ToF trên bench cần có đường giao tiếp với laptop.** Nếu dùng ESP32-S3 như kiến trúc đã chọn, đề xuất chuyển **chính bo điều khiển duy nhất** từ đợt 5 lên đợt 3. Không mua thêm một bo thứ hai. Nếu chưa mua bo, chỉ làm phần dữ liệu giả và giao diện phần mềm ở bước này.
- **Giai đoạn nguồn/an toàn không được hiểu là đợi điều khiển xe xong mới làm.** Thiết kế nguồn bắt đầu từ đợt cảm biến; phần dừng phải có trước thử chấp hành do phần mềm điều khiển. Giai đoạn 6 là mốc xác nhận tổng thể, phải hoàn thành trước chạy tự động trên sàn.
- **Ngưỡng số đo chưa được chốt thì để trạng thái “cần chốt”.** Không tự gán kết quả đã đạt, tổng tiền hoặc tỷ lệ hoàn thành phần mềm.
- **Bench, mô phỏng và xe thật là ba mức bằng chứng khác nhau.** Cờ STOP trên laptop chưa chứng minh xe thật dừng được; ảnh BEV hiển thị chưa chứng minh hình học đủ chính xác.

---

# 2. LUỒNG HỆ THỐNG VÀ NGUYÊN TẮC TRIỂN KHAI

### 2.1. Luồng khi hệ thống hoàn chỉnh

```text
LiDAR ── adapter/giao tiếp đã xác nhận ──> LAPTOP
                                            │
                                  Bản đồ + định vị
                                            │
4 camera USB ── hub/cổng USB ──────────> LAPTOP
                                            │
                              AI/CV + BEV cục bộ
                                            │
Cảm biến chuyển động/ToF ──> ESP32 ── telemetry
                                            │
                                            v
                              Hợp nhất trạng thái/bản đồ
                                            │
Người dùng đặt đích ───────────────> Kiểm tra đích và đường
                                            │
                                  Hybrid A* / Reeds–Shepp
                                            │
                              Quỹ đạo có tốc độ/góc lái
                                            │
                                 Xem trước → cho phép chạy
                                            │
LAPTOP ── lệnh có thời hạn ──> ESP32 ──> ESC + servo ──> MN300
   ^                               │                         │
   └──────── ảnh/quét/telemetry ────┴──── phản hồi thực ──────┘

Nhánh giám sát luôn hoạt động:
Nguy cơ / dữ liệu cũ / mất lệnh → dừng → kiểm tra lại → chờ hoặc lập đường mới.
E-stop vật lý là đường dừng riêng, không phụ thuộc giao diện laptop.
```

SLAM và AI nằm trên **laptop**, không nằm trong bản thân LiDAR hay camera.

### 2.2. Đợt mua không phải là giai đoạn phần mềm

Một đợt mua có thể phục vụ nhiều giai đoạn. Ngược lại, một giai đoạn có thể bắt đầu bằng dữ liệu giả rồi thay bằng cảm biến thật khi hàng về.

```text
Nhánh A: mô phỏng + giao diện + AI từ dữ liệu có sẵn ─────────────────┐
Nhánh B: LiDAR/camera → bench → nhiều cảm biến → sensor rig ──────────┤
Nhánh C: MN300 → đo đặc tính → điều khiển + nguồn + dừng ─────────────┤
                                                                  v
                                               Tích hợp → tự đỗ → đánh giá
```

Không cần chờ hoàn thành toàn bộ mô phỏng mới được cắm thử camera. Cũng không được dùng xe thật để bỏ qua những lỗi hình học đã có thể tìm thấy trong mô phỏng.

### 2.3. Quy tắc ghi nhận tiến độ

Mỗi giai đoạn có năm phần: **đồ cần có — việc khi chưa có đồ — việc khi có đồ — đầu ra — điều kiện chuyển bước**. Dùng trạng thái `CHƯA LÀM / ĐANG LÀM / CHƯA ĐẠT / ĐẠT` và đính kèm log hoặc biên bản thử.

---

# 3. SÁU ĐỢT MUA VÀ ĐIỀU KIỆN MUA TIẾP

| Đợt | Mua/chuẩn bị | Việc được mở khóa | Điều kiện mua tiếp |
|---|---|---|---|
| **1 — Cảm biến mẫu** | 1 RPLIDAR C1/C1M1 với bộ nối laptop phù hợp; 1 camera USB; hub ứng viên nếu cần; dây ngắn và nguồn bench phù hợp. | Đọc scan, lưu dữ liệu; kiểm tra camera, hiệu chuẩn, chạy AI trên ảnh thật. | Xác nhận camera mẫu dùng được cho mục tiêu gần xe trước khi mua thêm 3. |
| **2 — Bốn camera** | Thêm 3 camera cùng loại đã thử; hub/cổng nguồn phù hợp; gá cứng; dây ngắn. Cáp kéo dài chỉ đưa vào sau khi cấu hình ngắn đã ổn. | Bốn video đồng thời; hiệu chuẩn liên camera; BEV và kiểm tra overlap. | Phải thử cả bốn cùng hoạt động, không suy từ kết quả một camera. |
| **3 — Cảm biến bench** | BNO085; 2 VL53L1X; dây tín hiệu; **đề xuất mua sớm 1 ESP32-S3 chính để đọc cảm biến**. | IMU/ToF thật, telemetry và kiểm thử logic dừng trên bàn. | Có sơ đồ nguồn/giao tiếp đã đối chiếu; đọc ổn từng cảm biến rồi mới mở rộng. |
| **4 — Xe nền** | MN300 Tank300 1/12 RTR, đúng gói pin/sạc/phụ kiện xác nhận với shop. | Đo tốc độ thấp, cơ cấu lái, pin, bộ điện và khả năng gắn cảm biến. | Có cơ sở chọn encoder/gá và cách điều khiển ESC/servo. |
| **5 — Phản hồi/chấp hành** | AS5600; MT6701 hoặc encoder đã kiểm tra phù hợp; gá và dây chuyển; thêm 2 ToF khi bố trí cần; ESP32 chỉ mua nếu chưa có ở đợt 3. | Điều khiển thực có phản hồi, không mua trùng ESP32. | Phần nguồn và dừng của bước thử phải sẵn sàng; không chạy chấp hành chỉ với dây thử chưa kiểm tra. |
| **6 — Hoàn thiện nguồn/an toàn** | Bộ nguồn theo tải, LA38 + phần ngắt, cầu chì/đầu nối đúng định mức, dây final, gá final, quản lý dây USB. | Xác nhận tích hợp toàn hệ thống, chuẩn bị chạy tự động. | Các thử mất lệnh, dừng, reset và tải đồng thời phải đạt trước tự đỗ thật. |

**Hai ghi chú về mua hàng:** nguồn bench và bộ nối LiDAR không phải phụ kiện có thể bỏ qua đến cuối; mua sớm những gì cần để cấp và đọc cảm biến đúng cách. Mua một camera mẫu giúp sàng lọc model, nhưng chưa chứng minh hiệu năng của bốn camera chung hub.

---

# 4. GIAI ĐOẠN 0 — PHẦN MỀM THUẦN VÀ MÔ PHỎNG

### Đồ cần có

Laptop có môi trường lập trình; chưa cần xe hoặc cảm biến. Ghi cấu hình CPU/GPU/RAM/hệ điều hành để các lần đo sau so sánh được.

### Khi chưa có phần cứng: làm ngay

1. Tạo repository và cấu hình dự án; dùng các công cụ đã dự kiến: Python, OpenCV, NumPy, PyTorch, Shapely, PySide6, Git, pytest và công cụ đọc video phù hợp. Ghi lại phiên bản đã cài, không thay hàng loạt thư viện giữa một đợt thử.
2. Định nghĩa `VehicleState`, `GoalPose`, `CameraFrame`, `LidarScan`, `Telemetry`, `Costmap`, `Trajectory`, `SafetyEvent`. Mỗi nguồn dữ liệu phải có nhận dạng, thời gian và trạng thái hợp lệ.
3. Dựng xe ảo với `x, y, theta, v, delta`; đặt hình học xe trong file cấu hình, chưa xem giá trị giả định là kích thước MN300 đã đo.
4. Tạo bản đồ 2D gồm tường, vật cản, vùng chưa biết và vị trí đỗ tự chọn.
5. Làm giao diện kéo/xoay đích, xem xe hiện tại, đường dự kiến, nút lập đường, xem trước, chạy và dừng.
6. Tạo planner cơ sở Hybrid A* kết hợp Reeds–Shepp phù hợp; kiểm tra thân xe và vùng thân xe quét qua, không chỉ đường tâm.
7. Tạo điều khiển xe ảo tiến/lùi, giảm tốc tại đổi chiều; thêm trễ, nhiễu và tình huống mất dữ liệu giả.
8. Chèn vật cản giả khi đang chạy để kiểm tra `STOP → cập nhật → đánh giá lại → lập lại đường/chờ`.
9. Tải/xem dữ liệu công khai đã nêu trong dự án; kiểm tra **nhãn thực sự có phù hợp free-space/obstacle hay không** trước khi huấn luyện. Dataset chỉ có điểm ô đỗ không tự cung cấp nhãn pixel vật cản.

Mô hình cơ sở giữ theo tài liệu:

```text
x_dot     = v * cos(theta)
y_dot     = v * sin(theta)
theta_dot = v * tan(delta) / wheelbase
```

### Nếu linh kiện về trong lúc giai đoạn 0 chưa xong

Thực hiện kiểm tra tiếp nhận ở giai đoạn 1 song song. Chưa ghép mọi thứ vào một chương trình lớn; vẫn giữ nguồn dữ liệu giả để tái hiện lỗi.

### Đầu ra phải có

`README.md`, cấu trúc mã nguồn, cấu hình xe giả định, bản đồ mẫu, video mô phỏng, bài thử va chạm/đổi chiều/mất dữ liệu và log một phiên chạy.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [x] Kéo và xoay đích được; đích nằm trong vật cản bị từ chối.
- [x] Xe ảo chạy tiến/lùi; đường tuân thủ giới hạn lái đặt trong cấu hình.
- [x] Kiểm tra va chạm xét toàn thân xe.
- [x] Vật cản mới làm đường cũ mất hiệu lực; xe ảo dừng trước khi thử đường mới.
- [x] Xem trước không phát lệnh đến phần cứng.
- [x] Ghi lại đủ cấu hình và log để chạy lại cùng kịch bản.

**Cập nhật 20/09/2026:** sáu điều kiện trên đã kiểm chứng ở mức mô phỏng trong `autopark`; xem [biên bản và giới hạn](autopark/docs/GIAI_DOAN_0.md), [dataset và kiểm tra nhãn](autopark/datasets/DANH_MUC_DATASET.md). Không diễn giải thành kết quả xe thật.

**Nếu chưa đạt:** sửa dữ liệu/hình học/logic tại mô phỏng. Không cần mua thêm cảm biến để xử lý một lỗi thuần phần mềm.

---

# 5. GIAI ĐOẠN 1 — LIDAR VÀ MỘT CAMERA MẪU

### Đồ cần có

Đợt 1: LiDAR và bộ nối, một camera USB, dây ngắn, nguồn đúng thiết bị; hub nếu dùng để khảo sát kiến trúc. Hai nhánh LiDAR và camera có thể làm độc lập.

### Khi đang chờ đồ

- Viết nguồn camera đọc video lưu sẵn; nguồn LiDAR đọc bản quét lưu sẵn hoặc mô phỏng.
- Viết màn hình scan, bộ lưu phiên đo và kiểm tra dữ liệu cũ.
- Làm pipeline AI trên ảnh có sẵn, trước mắt chứng minh nạp mô hình → suy luận → lưu kết quả.
- Chuẩn bị bảng hiệu chuẩn có kích thước đo được, vật cản mẫu và lưới tọa độ trên sàn.
- Kiểm tra đầu vào bắt buộc của phương án SLAM dự kiến. Chưa có odometry thì không tự coi chuỗi scan là đủ cho mọi thư viện hoặc gán odometry bằng 0 để báo đã có định vị.

### Khi nhận LiDAR

1. Kiểm kê model, adapter, dây, đầu nối và hướng dẫn nguồn; chụp bộ thực giao.
2. Đọc scan bằng đường nối laptop được xác nhận; ghi khoảng cách, góc, thời gian, trạng thái và tốc độ cập nhật thực.
3. Đặt cảm biến cố định, dùng vật ở vị trí đã đo để kiểm tra hình hiển thị và đơn vị.
4. Gắn lên gá ổn định; khảo sát chuyển động chậm có kiểm soát trong mặt phẳng phù hợp với bài thử. Tránh dùng dữ liệu rung/lắc rồi kết luận SLAM sai.
5. Tích hợp mapping khi các đầu vào cần thiết đã có; lưu bản đồ và những tệp trạng thái mà thuật toán yêu cầu.
6. Nạp lại bản đồ, thử định vị tại các vị trí có tham chiếu độc lập. Tách “đọc scan được”, “tạo map được” và “định vị lại được” thành ba kết quả.

### Khi nhận một camera

1. Xác nhận biến thể và giao tiếp; dùng dây ngắn trước.
2. Liệt kê mode độ phân giải/FPS/format thực; không chỉ dựa tên bán hàng “1080p”.
3. Đo FPS nhận, thời gian suy luận, độ trễ, mất hình, CPU/GPU và nhiệt trong một phiên thử.
4. Kiểm tra ảnh ở độ cao, góc chúc và khoảng cách dự kiến gần xe; ghi góc nhìn thực hoặc phần còn chưa xác minh.
5. Hiệu chuẩn camera, lưu nội tại và tham số méo kèm mode ảnh đang dùng.
6. Chạy AI trên ảnh thật và lưu cả lỗi, đặc biệt tình huống vật cản bị dự đoán thành vùng trống.

### Đầu ra phải có

`hardware_inventory.md`, `camera_modes.csv`, `camera_01_calibration.yaml`, bản quét/bản đồ thử, log nhận ảnh, video mẫu và biên bản `gate_01.md`.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Laptop nhận LiDAR và camera ổn ở mode đã ghi rõ.
- [ ] Có dữ liệu và phép thử lưu/nạp bản đồ; phần định vị chưa đạt được báo riêng.
- [ ] Camera đủ nét trong vùng làm việc; hiệu chuẩn được và chạy AI trên ảnh thật.
- [ ] Có số đo, không chỉ nhận xét video “mượt”.
- [ ] **Chỉ quyết định mua thêm ba camera sau khi mẫu vượt kiểm tra đơn camera.**

**Nếu camera chưa đạt:** thử cấu hình hoặc model khác trước khi nhân số lượng. **Nếu LiDAR đến trước:** làm scan/map và tiếp tục AI với dữ liệu lưu sẵn; không chờ camera.

---

# 6. GIAI ĐOẠN 2 — BỐN CAMERA USB VÀ BEV CỤC BỘ

### Đồ cần có

Bốn camera cùng cấu hình phù hợp, hub/cổng USB và nguồn đã đối chiếu, gá cứng, dây ngắn. Tổng cộng bốn chiếc, không phải mua thêm bốn sau camera mẫu.

### Khi chưa đủ bốn camera

- Viết `MultiCameraManager` nhận bốn nguồn dữ liệu phát lại.
- Tách hiệu chuẩn, thu ảnh, suy luận và hiển thị thành các phần có thể đo riêng.
- Định nghĩa `front/rear/left/right`; lên bản vẽ gá và vùng sàn cần quan sát.
- Viết hàng đợi giới hạn và logic bỏ bộ ảnh quá lệch thời gian.
- Với video giả không cùng vị trí/thời điểm, chỉ dùng kiểm thử giao diện và luồng dữ liệu; không dùng để công bố kết quả hiệu chuẩn đa camera.

### Khi đủ bốn camera

1. Thử cả bốn trên dây ngắn và mode chung. Mốc khởi đầu đã đề xuất là **720p30 MJPEG**, rồi mới xem xét 1080p khi hệ thống đáp ứng.
2. Ghi FPS/độ trễ/mất hình riêng từng camera; chạy đồng thời với LiDAR và AI, không chỉ thử mở bốn cửa sổ.
3. Ghi sơ đồ cổng USB, nguồn hub và cách gán camera vào hướng. Kiểm tra lại nhận dạng sau rút/cắm hoặc khởi động máy.
4. Hiệu chuẩn riêng từng camera; gắn lên rig rồi xác định vị trí/hướng của camera so với rig.
5. Đồng bộ ở mức phần mềm và ghi sai lệch thời gian còn lại. Cùng FPS hoặc cùng hub không được ghi thành bằng chứng chụp đồng thời.
6. Chạy AI từng camera, quy đổi thông tin hình học có cơ sở về cùng hệ tọa độ và hợp nhất vùng chồng lấn.
7. Tạo BEV phục vụ thuật toán; ảnh ghép đẹp cho giao diện là đầu ra riêng, không thay thế kiểm tra tọa độ.
8. Đặt vật cản ở trước/sau/hông và vùng giáp ranh để đo vùng được quan sát, vùng che khuất và sai lệch giữa các camera.
9. Chỉ sau khi cấu hình ngắn đạt mới thêm cáp kéo dài. Ghi một phép thử A/B ngắn–dài để biết lỗi xuất hiện ở bước nào.

**Lưu ý cần kiểm chứng:** phép chiếu mặt sàn dùng cho điểm có cơ sở thuộc mặt sàn; không tự biến toàn bộ mask của một vật cao thành footprint chính xác. Phương pháp xác định biên tiếp xúc/độ sâu/vùng không chắc chắn còn phải được lựa chọn và đánh giá.

### Đầu ra phải có

Bản vẽ rig, bốn tệp calibration, `camera_rig_extrinsics.yaml`, `usb_topology.md`, log bốn luồng, sơ đồ vùng quan sát và báo cáo sai số BEV.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Bốn camera chạy đồng thời ở mode đã thống nhất; có báo cáo tải và mất hình.
- [ ] Đọc đúng camera theo đúng hướng sau khi khởi động lại.
- [ ] Có bộ hiệu chuẩn đa camera gắn với gá thực.
- [ ] Vật mẫu xuất hiện tại vị trí có thể đối chiếu trên BEV, không chỉ hiện một ô màu bất kỳ.
- [ ] Vùng chưa quan sát/thiếu tin cậy được giữ là `UNKNOWN`, không mặc định `FREE`.
- [ ] Có thử riêng dây kéo dài trước khi đưa vào vận hành xe.

**Nếu chưa đạt:** quay về bài thử cổng/nguồn/mode từng bước. Không mặc định đổi hub đắt hơn sẽ giải quyết mọi vấn đề; ghi nguyên nhân và bằng chứng trước khi mua lại.

---

# 7. GIAI ĐOẠN 3 — HỢP NHẤT CẢM BIẾN TRÊN BÀN THỬ

### Đồ cần có

Rig LiDAR + camera; BNO085; hai VL53L1X mẫu; dây và nguồn phù hợp. **Cần có bo đọc cảm biến/giao tiếp tương ứng. Đề xuất dùng sớm chính ESP32-S3 sẽ dùng trên xe.**

### Khi chưa có IMU, ToF hoặc ESP32

- Tạo telemetry giả với cùng cấu trúc sẽ dùng cho dữ liệu thật.
- Viết các lớp `StaticMap`, `LiveLidar`, `CameraSemantic`, `NearField` và trạng thái dữ liệu hợp lệ/cũ.
- Viết phép biến đổi rig–map, thử bằng vị trí biết trước.
- Làm logic: đường đang hợp lệ → thêm vật cản → hủy tính hợp lệ → phát cờ dừng → lập lại đường hoặc chờ.
- Không ghi nhận “ToF thật đã hoạt động” khi mới thay bằng dữ liệu giả.

### Khi nhận đủ phần cứng đọc cảm biến

1. Kiểm tra sơ đồ chân/nguồn của từng breakout; đọc từng cảm biến riêng trước.
2. ESP32 gửi telemetry có mã nguồn, timestamp, giá trị và cờ hợp lệ lên laptop; chưa nối chấp hành xe.
3. Với BNO085, ghi chế độ dữ liệu sử dụng, kiểm tra dấu/trục/hướng và độ ổn định khi rig đứng yên/di chuyển chậm.
4. Với ToF, kiểm tra khoảng cách, vật liệu/màu, điểm không đo được và timeout; khi thêm cảm biến thứ hai phải có phương án địa chỉ/giao tiếp rõ.
5. Đưa số đo về hệ tọa độ rig và hiển thị vùng đo; không xem mỗi số đo là bao phủ cả đầu hoặc hông xe.
6. Hợp nhất bản đồ toàn cục, vị trí rig và BEV cục bộ; đối chiếu một số vật mẫu có tọa độ đo được.
7. Dùng vật nhẹ đặt vào vùng thử khi rig đứng yên; ghi thời điểm nhận biết, cờ dừng, cập nhật bản đồ và kết quả lập lại đường.

### Đầu ra phải có

Firmware đọc cảm biến, sơ đồ dây bench, `telemetry_schema`, log đồng bộ, màn hình map/BEV và bộ bài thử vật cản có kết quả.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] IMU/ToF thật được đọc qua một đường giao tiếp đã xác định.
- [ ] Mỗi số đo có thời gian và trạng thái; lỗi sensor không bị biến thành giá trị khoảng cách “an toàn”.
- [ ] Global map và local BEV đặt được vào cùng phép mô tả tọa độ.
- [ ] Vật mới làm đường mất hiệu lực; phần mềm phát dừng và phân biệt đường bị chắn với chính đích bị chiếm.
- [ ] Có log cho `STOP → quan sát lại → cập nhật → replan/chờ`.

**Giới hạn bằng chứng:** giai đoạn này chứng minh nhận thức và logic; chưa chứng minh quãng đường dừng hoặc độ chính xác đỗ thật.

---

# 8. GIAI ĐOẠN 4 — TIẾP NHẬN VÀ ĐO ĐẶC TÍNH MN300

### Đồ cần có

MN300 đúng gói đã xác nhận, pin và sạc phù hợp, dụng cụ đo hình học/điện cần thiết và vùng thử kiểm soát. Chưa mua ESC thay thế chỉ từ tên xe.

### Khi chưa có xe

- Tiếp tục perception, AI, map và planner trên rig.
- Viết phiếu kiểm kê xe; chuẩn bị bảng đo tốc độ, góc lái, bán kính quay và dừng.
- Để hình học xe trong cấu hình với nhãn `CHƯA ĐO`; thử độ nhạy planner theo các kích thước giả định.
- Lên phương án gá có thể điều chỉnh, chưa đặt gia công phần phụ thuộc kích thước chưa biết.

### Khi nhận xe

1. Kiểm kê và chạy bằng điều khiển nguyên bản trong vùng thử trước khi can thiệp điện.
2. Ghi hành vi tiến/lùi, vùng ga không phản ứng, tốc độ thấp nhất giữ được, đổi chiều và dừng/thả trôi.
3. Đo chiều dài cơ sở, bề rộng, phần nhô trước/sau, góc lái/bán kính quay thực và kích thước cần cho footprint.
4. Mở phần vỏ phù hợp để chụp motor, servo, ESC/bộ thu, pin, đầu nối và trục truyền động. Đối chiếu đúng thiết bị, không lấy cấu hình của xe khác thay cho nó.
5. Xác định bộ thu và ESC có tách không, servo giao tiếp thế nào và cách đưa lệnh từ ESP32. Nếu chưa đủ dữ liệu thì giữ nguyên xe và hỏi/đo thêm.
6. Chọn vị trí đo góc lái, chuyển động quay và gá sensor rig; kiểm tra vướng cơ cấu lái/hệ treo.
7. Cập nhật mô hình mô phỏng bằng thông số đã đo, lưu rõ nguồn của từng tham số.

### Đầu ra phải có

`mn300_inventory.md`, ảnh bộ điện/giắc, `vehicle_measured.yaml`, đường cong lệnh–chuyển động ban đầu, bảng dừng và thiết kế gá dự kiến.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Hiểu được hoạt động xe nguyên bản và có dữ liệu chạy chậm, không chỉ biết tốc độ quảng cáo.
- [ ] Có kích thước thực dùng cho planner.
- [ ] Có phương án can thiệp ESC/servo được xác minh hoặc danh sách thông tin còn thiếu rõ ràng.
- [ ] Xác định được phương án gá encoder/góc lái đủ cơ sở để đặt linh kiện.
- [ ] Nếu phải đổi một cụm điện/cơ khí, quyết định dựa trên phép thử, không mua thay đồng loạt.

**Nếu chưa đạt:** tiếp tục hoàn thiện phần mềm trên rig; không đẩy lỗi xe chạy giật sang việc đổi thuật toán AI.

---

# 9. GIAI ĐOẠN 5 — ESP32-S3 VÀ ĐIỀU KHIỂN CÓ PHẢN HỒI

### Đồ cần có

Một ESP32-S3 chính, cảm biến/gá góc lái, encoder/gá chuyển động, bộ dây ESC/servo đã đối chiếu. **Nguồn và đường dừng của từng phép thử phải sẵn sàng; giai đoạn 6 được làm song song trước khi xe chạy tự động trên sàn.**

### Khi chưa đủ phần cứng

- Viết firmware nhận lệnh, giới hạn lệnh, watchdog, telemetry và trạng thái cho phép chạy.
- Viết `VehicleIO` với hai nhánh: mô phỏng và phần cứng; dùng cùng định nghĩa tốc độ/góc lái, không mặc định cùng độ trễ.
- Kiểm thử parser với gói thiếu/sai/cũ, reset phiên, mất liên lạc và reconnect.
- Thử bộ điều khiển trong mô phỏng có vùng chết, độ trễ và phản hồi nhiễu.
- Hoàn thiện thiết kế nguồn/dừng cho phép thử sắp thực hiện.

Gói dữ liệu cần được đặc tả tối thiểu:

```text
Command: session_id, sequence, validity/timeout, enable,
         speed_target, steering_target
Telemetry: sample_time, sequence, speed_measured,
           steering_measured, imu, tof, supply/status, fault
```

Đây là hợp đồng dữ liệu dự kiến; chân GPIO, mức tín hiệu và mã đóng gói chỉ chốt theo bo thực.

### Khi đủ phần cứng

1. Đọc cảm biến và thử giao tiếp khi chưa nối động lực; bảo đảm khởi động không tự vào trạng thái chạy.
2. Nối từng cơ cấu theo sơ đồ đã đối chiếu; thử ban đầu khi xe được kê cố định, không vướng trục/bánh.
3. Hiệu chuẩn góc đo với góc lái tương đương của mô hình; đo điểm giữa, hai giới hạn và độ rơ khi đổi hướng lái.
4. Kiểm tra encoder, chiều quay, độ phân giải thực và quy đổi tới quãng đường xe. Ghi rõ cấu hình count/xung và tỷ số truyền đã dùng.
5. Tạo điều khiển tốc độ thấp có phản hồi; giới hạn gia tốc, góc lái và tốc độ thay đổi góc. Không cho các vòng điều khiển chưa được hiểu rõ tranh quyền với bộ điện có sẵn.
6. Thử trình tự giảm tốc → xác nhận dừng → đổi chiều; không mặc định một lệnh ga âm luôn khiến xe lùi ngay.
7. Thử mất lệnh/reset và đo phản ứng. Chỉ chuyển sang thử có tải trên sàn sau kiểm tra nguồn/dừng phù hợp ở giai đoạn 6.

### Đầu ra phải có

Firmware phiên bản, sơ đồ dây đúng bo, `steering_calibration.yaml`, `speed_conversion.yaml`, log điều khiển và báo cáo watchdog/khởi động/reset.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Nhận lệnh đúng đơn vị và chỉ chạy khi được cho phép.
- [ ] Đo được tốc độ/góc lái; đã kiểm tra dấu và hệ số quy đổi.
- [ ] Có số đo sai số bám tốc độ/góc ở miền thử nghiệm.
- [ ] Đổi tiến/lùi theo trình tự đã kiểm chứng trên bộ điện thực.
- [ ] Mất lệnh/reset làm hệ thống về trạng thái đã thiết kế; reconnect không tự chạy tiếp.

**Nếu chưa đạt:** phân biệt lỗi đo, cơ khí, nguồn và bộ điều khiển; không tăng gain tùy tiện để bù một encoder lắp sai hoặc tín hiệu không hợp lệ.

---

# 10. GIAI ĐOẠN 6 — NGUỒN VÀ KIỂM CHỨNG DỪNG AN TOÀN

### Vị trí trong kế hoạch

Đây là một nhánh xuyên suốt, không phải công việc đợi tới cuối. Thiết kế nguồn bench từ đợt 1; nguồn/chấp hành và dừng thực hiện song song giai đoạn 4–5. **Cổng xác nhận tổng thể này phải đạt trước giai đoạn chạy tự động trên sàn.**

### Khi chưa có nguồn final

- Lập bảng điện áp, dòng tải, nguồn vào/ra, đầu nối và phần dữ liệu còn chưa rõ.
- Tách đường nguồn động lực, servo và logic/camera/LiDAR theo thiết kế thực; kiểm tra đường nguồn USB của laptop/hub.
- Xác định nút LA38 sẽ tác động tới phần tử nào. Một nút bấm đơn lẻ không được đánh dấu là đã hoàn tất E-stop.
- Chọn cầu chì, dây, đầu nối và phần tử ngắt theo cấu hình đã kiểm tra; không khóa con số 15 A/30 A chỉ vì danh sách bán hàng.
- Viết trước các tình huống mất nguồn logic, mất cáp, mất cảm biến, treo chương trình và khởi động lại.

### Khi có phần cứng nguồn/dừng

1. Đo điện áp trước khi nối từng tải; kiểm tra đúng cực và đường cấp nguồn.
2. Bật lần lượt logic, LiDAR, một rồi bốn camera; tiếp theo thử chấp hành có kiểm soát.
3. Đo tải đồng thời, sụt áp, reset và nhiệt; ghi điều kiện pin/nguồn của mỗi lần đo.
4. Thử tải và động cơ theo tài liệu thiết bị. **Không tự khóa cứng motor/servo để đo dòng kẹt khi chưa có phương pháp giới hạn dòng và bảo vệ phù hợp.**
5. Kiểm tra nút dừng, lệnh dừng phần mềm, mất lệnh, rút cáp và reset; đo thời gian/quãng đường phản ứng thực.
6. Xác nhận không tự chạy lại sau nhả nút dừng hoặc nối lại cáp; phải có thao tác cho phép mới.

### Đầu ra phải có

`power_budget.md`, sơ đồ nguồn, sơ đồ dừng, bảng định mức còn cần kiểm tra, log tải, nhiệt và kết quả thử các tình huống lỗi.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Có sơ đồ cấp điện và ngắt động lực khớp thiết bị thực.
- [ ] Không reset/disconnect ngoài dự kiến trong bộ thử tải đã định.
- [ ] Các đường dừng đã thử, không chỉ tồn tại trên sơ đồ.
- [ ] Đo được khoảng dừng trong điều kiện thử; không coi cắt nguồn là đứng yên tức thì.
- [ ] Phần nguồn/dừng được xác nhận trước tự đỗ thật.

---

# 11. GIAI ĐOẠN 7 — CHUYỂN CỤM CẢM BIẾN LÊN XE

### Khi chưa có gá final hoặc chưa sẵn xe

- Thiết kế sàn/gá trên số đo MN300; giữ bản vẽ vị trí và hệ tọa độ cảm biến.
- Kiểm tra vùng nhìn camera, mặt phẳng quét LiDAR, vị trí ToF và đường đi dây trên mô hình bố trí.
- Làm replay với cấu hình rig hiện tại; mọi thay đổi vị trí dự kiến được ghi thành phiên bản mới, chưa sửa dữ liệu hiệu chuẩn cũ như thể đã đo lại.

### Khi có đủ xe và gá

1. Gắn cảm biến chắc chắn, không cản cơ cấu lái, hệ treo hoặc bánh.
2. Đi dây, chống kéo tuột và bảo vệ dây USB khỏi quấn bánh; kiểm tra cả tiến, lùi và rẽ.
3. Ghi footprint sau khi thêm phụ kiện, không chỉ kích thước thân xe nguyên bản.
4. Đo lại phép biến đổi `vehicle↔rig`, camera, LiDAR, IMU và ToF theo trạng thái lắp thực.
5. Kiểm tra lại hiệu chuẩn trên vật tham chiếu; nếu gá/camera/mode ảnh thay đổi thì cập nhật phần hiệu chuẩn liên quan.
6. Thử cảm biến khi xe đứng yên rồi di chuyển chậm có giám sát; đo tác động của rung, độ nghiêng thân và dây kéo.

### Đầu ra phải có

Bản vẽ gá final, ảnh lắp, `vehicle_sensor_extrinsics.yaml`, footprint thực, báo cáo kiểm tra lại camera/LiDAR và đường đi dây.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Sensor và dây không cản chuyển động.
- [ ] Vùng bị che đã được ghi lại; không tự khẳng định bốn camera phủ kín mọi điểm quanh xe.
- [ ] Bộ hiệu chuẩn đúng phiên bản gá và mode ảnh.
- [ ] Sai lệch khi xe chuyển động nằm trong giới hạn đã chọn cho bước tích hợp.

---

# 12. GIAI ĐOẠN 8 — HỢP NHẤT TOÀN CỤC/CỤC BỘ TRÊN XE CHUYỂN ĐỘNG

### Khi chưa thể chạy trên xe

- Chạy lại dữ liệu bench với các độ trễ, sai lệch timestamp và mất nguồn dữ liệu giả lập.
- Kiểm tra phép đổi tọa độ bằng điểm biết trước.
- Kiểm tra chính sách khi global map nói trống nhưng quan sát hiện tại báo có vật cản.
- Kiểm tra dữ liệu cũ không tự tồn tại mãi như bằng chứng vùng trống an toàn.

### Khi có xe và cảm biến hoạt động

1. Kết hợp vị trí toàn cục, odometry/IMU và dữ liệu cảm biến theo thời điểm tương ứng.
2. Đưa BEV cục bộ về map; theo dõi vật tĩnh khi xe tiến/lùi/rẽ để tìm lỗi lệch trục hoặc độ trễ.
3. Hợp nhất bản đồ tĩnh, LiDAR trực tiếp, camera cục bộ, khoảng cách gần và độ không chắc chắn.
4. Chạy thử dưới điều khiển tay/giám sát trước; planner mới chỉ đưa ra đề xuất, chưa tự phát động lực nếu điều kiện chưa đạt.
5. Làm mới/từ chối kết quả planner theo phiên bản map và đích. Kết quả tính xong cho map cũ không được tự đem chạy.
6. Kiểm tra điều kiện dữ liệu còn mới, vùng quan sát và khoảng hở trước mỗi đoạn chuyển động.

### Đầu ra phải có

Log cảm biến đồng bộ, phép biến đổi tọa độ, video map/BEV trên xe chạy, bảng lỗi hệ tọa độ/độ trễ và bộ bài thử độ hợp lệ của quỹ đạo.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Vật mẫu có vị trí hợp lý trên map khi xe đổi tư thế.
- [ ] Phát hiện được mâu thuẫn giữa cảm biến hoặc mất độ tin cậy.
- [ ] Dữ liệu cần thiết bị cũ/mất thì không cho tiếp tục mù.
- [ ] Planner nhận môi trường hiện hành và kết quả cũ bị loại đúng.
- [ ] Có đánh giá định vị/BEV bằng tham chiếu độc lập, không dùng cùng một đầu ra tự xác nhận chính nó.

---

# 13. GIAI ĐOẠN 9 — TỰ ĐỖ THẬT VÀ XỬ LÝ VẬT CẢN

### Khi các khối thật chưa đồng thời sẵn sàng

- Chạy toàn phiên đỗ trong mô phỏng bằng kích thước/giới hạn đã đo trên MN300.
- Chạy chế độ quan sát: người điều khiển xe, phần mềm tính đường/lệnh nhưng không gửi chấp hành.
- Hoàn thiện quy trình bắt đầu, dừng, xác nhận lại và báo lỗi trên UI.
- Chuẩn bị sa bàn có số đo và vật cản mềm; không dùng người đứng trong đường xe để làm vật cản thử.

### Khi đủ điều kiện chạy thật

1. Kiểm tra nguồn/dừng, dữ liệu, hiệu chuẩn, vị trí xe, vùng quan sát và đích trước khi ARM.
2. Bắt đầu với vùng rộng, tốc độ thấp trong miền đã thử; người giám sát có phương án dừng.
3. Người dùng kéo/xoay đích; hệ thống kiểm tra footprint đích và tìm quỹ đạo hợp lệ.
4. Xem trước chỉ là mô phỏng; trước START phải kiểm tra lại trạng thái thực.
5. Xe chạy quỹ đạo tiến/lùi có phản hồi; tại điểm đổi chiều phải thực hiện trình tự đã kiểm chứng.
6. Gần đích giảm tốc và kiểm tra đồng thời sai số vị trí, hướng và tốc độ. Cơ chế hiệu chỉnh cuối không được giả định xe có thể trượt ngang hoặc quay tại chỗ.
7. Làm đỗ vuông góc trong vùng rộng trước, rồi mở rộng vị trí xuất phát và đỗ song song.
8. Dùng vật nhẹ đưa vào vùng thử từ khoảng cách an toàn để kiểm tra vật cản bất ngờ. Không ném vật vào sát xe rồi kỳ vọng hệ thống dừng tức thì.

### Luồng phản ứng với vật cản

```text
Quan sát phát hiện thay đổi/nguy cơ
  → kiểm tra vùng thân xe dự kiến đi qua
  → yêu cầu dừng và kiểm chứng trạng thái dừng
  → cập nhật bản đồ, quan sát lại
  → đích còn hợp lệ?
      Không: chờ người dùng thay đích / hủy phiên
      Có: tìm đường mới
           Không có đường đủ điều kiện: giữ dừng
           Có đường: kiểm tra lại và cho phép tiếp tục theo chính sách đã chốt
```

Mất liên lạc, E-stop hoặc lỗi yêu cầu xác nhận không được tự chuyển về RUN chỉ vì lỗi vừa biến mất. Chính sách tự chạy tiếp sau một vật cản thông thường phải được ghi rõ; khi thử ban đầu ưu tiên người dùng xác nhận lại.

### Đầu ra phải có

Log từng phiên tự đỗ, quỹ đạo đặt/thực, sai số cuối, thời gian, số đổi chiều, lý do dừng, video và biên bản sự kiện vật cản.

### Mục tiêu cần đạt / điều kiện chuyển bước

- [ ] Tự đỗ từ nhiều tư thế xuất phát trong phạm vi đã định, không chỉ phát chuỗi lệnh theo thời gian.
- [ ] Có kết quả đỗ vuông góc và song song; mọi thất bại đều được ghi.
- [ ] Kiểm tra cả sai số cuối vị trí, hướng và khoảng hở.
- [ ] Vật cản chắn đường hoặc chiếm đích tạo hành vi khác nhau đúng thiết kế.
- [ ] Không có đường phù hợp thì giữ dừng, không ép planner phải trả một đường bất kỳ.

---

# 14. GIAI ĐOẠN 10 — ĐÁNH GIÁ VÀ HOÀN THIỆN KHÓA LUẬN

### Khi chưa đủ bộ xe hoặc chưa đạt tự đỗ

- Viết tổng quan, yêu cầu, thiết kế hệ thống, quy trình dữ liệu và phương pháp đánh giá.
- Hoàn thành kết quả riêng AI/CV, mô phỏng và bench; ghi rõ mỗi kết quả thuộc mức nào.
- Chuẩn bị bảng kịch bản, cách đo độc lập và định nghĩa thành công/thất bại trước khi thu kết quả cuối.
- Tách tập huấn luyện/kiểm chứng/kiểm tra theo phiên hoặc bối cảnh để tránh dùng ảnh gần trùng cho các tập khác nhau.

### Khi hệ thống tích hợp hoạt động

1. Đóng phiên bản code, model, map, calibration, sơ đồ dây và cấu hình trước bộ thử cuối.
2. Lặp các kiểu đỗ, tư thế xuất phát, khoảng hở, ánh sáng và vật cản đã định.
3. Đánh giá riêng AI/CV và đánh giá toàn xe; tỷ lệ đỗ thành công không thay thế chỉ số nhận thức.
4. Ghi cả lần dừng bảo vệ, lỗi liên lạc và can thiệp của người giám sát. Dừng an toàn có thể đúng chức năng nhưng không phải hoàn thành nhiệm vụ đỗ.
5. Thử dữ liệu cũ/mất camera/mất LiDAR/mất lệnh trong môi trường có kiểm soát.
6. Phân loại nguyên nhân lỗi: ảnh/AI, định vị, hình học, planner, control, cơ khí, nguồn, liên lạc hoặc đích không hợp lệ.
7. Tổng hợp báo cáo, video, mã nguồn, hướng dẫn lắp/chạy/dừng và các giới hạn còn lại.

### Đầu ra phải có

Luận văn, dữ liệu đánh giá, bảng thống kê, đồ thị, video, hướng dẫn vận hành, BOM đã mua thực và hồ sơ tái lập thí nghiệm.

### Mục tiêu cần đạt

- [ ] Có chỉ số định lượng và định nghĩa cách đo.
- [ ] Có tham chiếu độc lập cho sai số vị trí/hướng/khoảng cách.
- [ ] Không chỉ chọn các lần demo thành công.
- [ ] Phân biệt bài toán đã giải quyết với phần chưa đạt hoặc ngoài phạm vi.
- [ ] Người khác đọc hướng dẫn có thể tái lập một phiên thử trong điều kiện đã nêu.

---

# 15. THIẾU LINH KIỆN HOẶC HÀNG VỀ KHÔNG CÙNG LÚC THÌ LÀM GÌ?

| Tình trạng | Việc có thể làm ngay | Điều chưa được kết luận |
|---|---|---|
| Chưa có bất kỳ thiết bị dự án nào | Mô phỏng, UI, planner, dataset, AI trên ảnh lưu sẵn, log/replay. | Chưa có hiệu năng cảm biến hoặc điều khiển xe thật. |
| Chỉ có LiDAR | Driver/scan, ghi dữ liệu, mapping khi có đủ đầu vào, thử lưu/nạp và định vị. | Chưa hoàn thành hợp nhất đa camera. |
| Chỉ có một camera | Mode/FPS/độ trễ, hiệu chuẩn, AI ảnh thật, một vùng BEV. | Chưa chứng minh bốn camera chạy chung bus. |
| Chưa đủ bốn camera | Manager đa nguồn bằng replay, UI, nhãn dữ liệu, thiết kế gá. | Video giả không chứng minh đồng bộ/góc nhìn thật. |
| Có IMU/ToF nhưng chưa có bo đọc | Đối chiếu pinout, thiết kế dây, fake telemetry và parser. | Chưa coi cảm biến thật đã tích hợp với laptop. |
| Có rig nhưng chưa có xe | Perception, mapping, đổi tọa độ, logic vật cản, planner với xe ảo. | Cờ STOP chưa là khoảng dừng xe thật. |
| Có xe nhưng thiếu encoder/gá | Đo cơ khí, chạy nguyên bản có giám sát, xem bộ điện và chuẩn bị thiết kế đo. | Chưa có closed-loop tốc độ đúng nghĩa. |
| Có ESP32 nhưng chưa xác minh ESC | Giao tiếp, watchdog, đọc cảm biến; mô phỏng ngõ ra hoặc thử không chấp hành. | Không cắm thử tùy tiện vào bo xe. |
| Thiếu nguồn/dừng final | Tính tải, sơ đồ, firmware, bench được cấp nguồn phù hợp. | Không chuyển sang chạy tự động có động lực. |
| Cáp dài lỗi nhưng cáp ngắn ổn | Tiếp tục AI/BEV trên cáp ngắn; tách việc kiểm tra đường truyền. | Không coi lỗi USB là lỗi mô hình AI. |

---

# 16. MỤC TIÊU ĐO LƯỜNG VÀ ĐIỀU KIỆN HOÀN THÀNH V1

### 16.1. Mục tiêu thử khởi đầu đã được đề xuất trong trao đổi

| Hạng mục | Mốc làm việc | Cách dùng |
|---|---|---|
| Camera | Bắt đầu thử 720p30 MJPEG; kiểm tra 1080p sau. | Đây là mode mục tiêu, không cam kết listing hỗ trợ hoặc bốn camera chắc chắn đạt. |
| Chạy dài cảm biến | Dùng phiên thử khoảng 30 phút làm bước sàng lọc ban đầu. | Ghi dropout, reset, tăng độ trễ và tải thực; chưa chứng minh độ tin cậy vô hạn. |
| Tốc độ xe | Khảo sát miền 0,05–0,15 m/s đã nêu. | Chỉ chọn tốc độ vận hành trong phần miền đã đo phù hợp với khoảng dừng và khoảng hở. |
| Đích đỗ | Có tọa độ và hướng, đặt bởi người dùng. | Không cần vạch sơn hoặc AI tự tìm ô để chạy V1. |
| Vật cản mới | Dừng, cập nhật, đánh giá lại, replan hoặc giữ dừng. | Không yêu cầu V1 tự lách liên tục qua vật đang chuyển động. |

### 16.2. Những ngưỡng vẫn phải chốt từ yêu cầu và phép đo

Không có đủ thông số xe/sa bàn/thực nghiệm để tự ghi một bộ ngưỡng cuối. Trước nghiệm thu phải hoàn thiện bảng:

| Nhóm | Đại lượng cần đo | Ngưỡng chấp nhận |
|---|---|---|
| Camera | FPS từng luồng, độ trễ p50/p95, khoảng đứng hình dài nhất, sai lệch thời gian giữa camera. | Cần chốt theo tốc độ và nhiệm vụ nhận thức. |
| Hình học | Sai số chiếu/BEV trong vùng dùng được; độ lệch giữa các camera. | Cần chốt theo khoảng hở mục tiêu. |
| AI | mIoU/precision/recall phù hợp nhãn; tỷ lệ nhầm vật cản thành vùng trống; hành vi với vùng không chắc chắn. | Cần chốt trên tập kiểm tra xác định. |
| Định vị | Sai số vị trí/hướng, độ ổn định và khả năng định vị lại. | Cần chốt bằng phép đo độc lập. |
| Điều khiển | Sai số bám tốc độ/góc, đổi chiều, trễ đáp ứng và quãng dừng. | Cần chốt trên xe thật. |
| Tự đỗ | Sai số cuối vị trí/hướng, khoảng hở nhỏ nhất, tỷ lệ hoàn thành, thời gian và số đổi chiều. | Cần chốt với loại ô/vị trí xuất phát đã định. |
| Phản ứng lỗi | Thời gian phát hiện, phát lệnh dừng, dừng thực; xử lý reconnect. | Cần chốt theo bài thử và khả năng dừng đo được. |

**Tiêu chí `UNKNOWN` cần được định nghĩa:** đó có thể là vùng chưa quan sát, số đo không hợp lệ, vùng che khuất hoặc dự đoán thiếu tin cậy. Không mặc định thêm một tên lớp vào mô hình sẽ bảo đảm nhận ra mọi vật lạ.

### 16.3. Bộ kịch bản nghiệm thu

| Nhóm | Kịch bản cần có |
|---|---|
| Đỗ cơ sở | Vuông góc, song song; các tư thế xuất phát đã ghi; ô rộng rồi thu hẹp trong phạm vi thử. |
| Nhận thức | Ánh sáng khác nhau, vật ở mép ảnh/overlap, vật thấp, vật không xuất hiện trong tập huấn luyện. |
| Vật cản mới | Chặn trước, chặn sau khi lùi, bên hông vùng thân xe quét qua, chiếm đích, chắn đường nhưng đích còn trống. |
| Liên lạc/cảm biến | Mất một camera, ảnh cũ, mất scan, ToF không hợp lệ, mất telemetry/lệnh. |
| Điều khiển/an toàn | Đổi chiều, dừng phần mềm, E-stop, reset, reconnect và nguồn yếu trong quy trình thử có bảo vệ. |

**Không cam kết phát hiện được mọi vật bất ngờ trong mọi điều kiện.** Phải công bố vùng làm việc, loại/kích thước vật thử, ánh sáng, tốc độ, khoảng phát hiện và các giới hạn còn lại.

### 16.4. V1 hoàn thành khi

- [ ] Bản đồ/định vị LiDAR hoạt động trong khu vực thử đã định.
- [ ] Bốn camera USB cùng hoạt động và có hiệu chuẩn đúng gá.
- [ ] AI/CV cung cấp thông tin cục bộ cho planner, có đo sai số/nhầm lẫn.
- [ ] Người dùng chọn vị trí/hướng, xem trước và ra lệnh bắt đầu được.
- [ ] Quỹ đạo xét giới hạn lái và toàn thân xe.
- [ ] Xe thực thi có phản hồi tốc độ/góc, không chỉ chạy theo thời gian.
- [ ] Hoàn thành các bài đỗ theo tiêu chí đã chốt.
- [ ] Vật cản/dữ liệu không hợp lệ làm dừng hoặc từ chối chạy đúng thiết kế.
- [ ] Nguồn, watchdog và E-stop đã kiểm chứng.
- [ ] Có dữ liệu, cấu hình và hướng dẫn để tái hiện kết quả.

---

# 17. HỒ SƠ BÀN GIAO VÀ KẾ HOẠCH BẮT ĐẦU NGAY

### 17.1. Tổ chức hồ sơ đề xuất

```text
project/
├── docs/                 # Đặc tả, sơ đồ, biên bản các cổng kiểm tra
├── src/parking_project/
│   ├── perception/
│   ├── lidar/
│   ├── bev/
│   ├── fusion/
│   ├── planning/
│   ├── control/
│   ├── simulation/
│   ├── ui/
│   ├── transport/
│   └── logging/
├── firmware/
├── configs/              # Thông số giả định/đo thực, ngưỡng và mode
├── calibration/          # Theo serial/ID camera và phiên bản gá
├── datasets/             # Danh mục nguồn, giấy phép, nhãn và cách chia tập
├── tests/
├── scenarios/
└── runs/
    └── run_<id>/
        ├── manifest.json
        ├── config_snapshot/
        ├── camera/
        ├── lidar/
        ├── telemetry.csv
        ├── commands.csv
        ├── trajectory.csv
        ├── events.jsonl
        └── result.json
```

Log phải ghi phiên bản code/model/map/calibration và phép thử; tránh đo hai cấu hình khác nhau rồi so sánh như cùng điều kiện.

### 17.2. Những phần còn cần xác minh, không tự điền là đã chốt

| Vấn đề | Xác minh ở đâu/khi nào? |
|---|---|
| Laptop và sơ đồ cổng USB thực | Giai đoạn 0–2. |
| Camera 130° là loại góc nào, mode/MJPEG, lấy nét gần | Mẫu camera ở giai đoạn 1. |
| Hub UGREEN hay phương án thay thế, nguồn hub và bốn luồng | Giai đoạn 1–2; không mua trùng hai hub chỉ vì có hai tên. |
| Bộ C1M1 kèm adapter/cáp nào; đầu vào thư viện SLAM | Trước đợt 1 và khi tiếp nhận. |
| Bộ điện MN300 và giao tiếp servo/ESC | Giai đoạn 4. |
| Chân/mode MT6701, vị trí encoder và quy đổi chuyển động | Giai đoạn 4–5. |
| Gá AS5600 và quan hệ tới góc lái mô hình | Giai đoạn 4–5. |
| Địa chỉ/giao tiếp nhiều ToF, vùng thực sự được giám sát | Giai đoạn 3 và 7. |
| Nguồn/regulator, cầu chì và phần ngắt động lực | Thiết kế song song; xác nhận tổng thể ở giai đoạn 6. |
| Tự tiếp tục hay cần xác nhận sau vật cản thông thường | Chốt chính sách trước giai đoạn 9. |
| Mốc thời gian hoàn thành | Chưa có deadline/giờ công được người dùng chốt; không tự cam kết lịch. |

### 17.3. Năm công việc đầu tiên có thể bắt đầu ngay

1. Tạo repository, ghi cấu hình laptop và danh sách yêu cầu V1.
2. Viết xe ảo + map + giao diện đặt/xoay đích, đồng thời dựng cơ chế ghi log.
3. Chuẩn bị pipeline dữ liệu AI phù hợp free-space/vật cản, không mặc định dataset ô đỗ đã có đầy đủ nhãn cần dùng.
4. Xác nhận gói LiDAR, chọn một camera mẫu và phương án nguồn/dây bench; chưa mua đồng loạt bốn camera.
5. Tạo phiếu kiểm thử mẫu camera/LiDAR và bảng theo dõi các giai đoạn bên dưới.

### 17.4. Bảng theo dõi tiến độ

| Giai đoạn | Trạng thái | Bằng chứng/log | Vướng mắc | Công việc tiếp theo |
|---|---|---|---|---|
| 0 — Phần mềm/mô phỏng | ĐẠT (mô phỏng, 20/09/2026) *khuya 24/09/2026 (chưa commit, không phiên đo thiết bị nào):* nhãn `expected` của 16 ca khó được kiểm lại: cả 16 có đường chứng kiểm độc lập, `parallel_122` và `parallel_115` đổi `infeasible` → `feasible`; TIMEOUT/NO_PATH của planner ở các ca đó là giới hạn của planner; trạng thái giai đoạn không đổi | [Biên bản, test, video và replay](autopark/docs/GIAI_DOAN_0.md); [báo cáo giai đoạn 0](BAO_CAO_GIAI_DOAN_0.md); [AI baseline WoodScape, đánh giá ngoài miền, thử thêm AVM-SS/ACDC](HUAN_LUYEN.md); [kiểm lại nhãn ca khó, đường chứng (khuya 24/09/2026, mô phỏng)](autopark/docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md) | Chưa kiểm chứng phần cứng; AI chưa được chấm trên ảnh sa bàn; [giấy phép WoodScape](autopark/docs/GIAY_PHEP_DU_LIEU.md) cấm dùng mô hình huấn luyện trên nó để vận hành hoặc hỗ trợ vận hành phương tiện, cách hiểu của người làm khóa luận (22/09) chưa được Valeo xác nhận; *(khuya 24/09/2026)* hai trường hợp `test_ca_vo_nghiem_khong_bao_thanh_cong_gia` trong `tests/test_planner_hard_cases.py` hỏng vì còn khẳng định nhãn cũ *(đã sửa 25/09/2026: test đổi tên `test_ca_rat_chat_khong_bao_thanh_cong_gia`, toàn bộ bộ test `.venv` 1242 đạt / 7 bỏ qua, `.venv-train` 386 đạt)*; "giải được" chưa có nghĩa dùng được trên xe (tiêu chí số lần đổi chiều CHƯA CHỐT) | Đã chuyển sang giai đoạn 1–3 và phần chuẩn bị của giai đoạn 5 (24/09/2026); giữ bộ test và replay mô phỏng làm kiểm thử hồi quy; *(khuya 24/09/2026)* sửa `tests/test_planner_hard_cases.py` theo nhãn mới *(đã làm 25/09/2026)* và thêm đối chứng âm có chứng minh (hiện có `test_walled_off_goal_reports_no_path`, chỉ đòi planner không báo thành công) |
| 1 — LiDAR + camera mẫu | ĐANG LÀM (24/09/2026: LiDAR đọc scan, ghi/phát lại phiên, bản đồ lưới tĩnh trên máy bàn; kiểm lại 24/09 không thấy dấu hiệu hỏng ở giao tiếp, tần số quét và số tia: cùng serial, health OK, bỏ 3 s đầu mỗi bản ghi thì ≈10,0 Hz / ≈510 tia mỗi vòng như 22/09, 0 lỗi đọc / 0 vòng mất qua 26 phiên có LiDAR 22–24/09 (33.932 vòng); sai số khoảng cách chưa đo; camera: bài thử đơn camera đạt về mode/FPS trên máy bàn, chưa đặt ở độ cao thật, chưa hiệu chuẩn; gate 1 CHƯA ĐẠT; *cập nhật tối 24/09/2026:* có công cụ định vị trên bản đồ tĩnh đã lưu (khớp scan, không phải SLAM, không odometry); chạy offline trên bản ghi có sẵn: cùng chỗ thì nhất quán (live_headless 60/60 OK, hướng lệch +4,3° so với lúc dựng bản đồ, chưa rõ nguyên nhân), chỗ khác thì báo hỏng (k01 151/151 FAILED); chưa có vị trí tham chiếu độc lập nên "định vị lại được" vẫn chưa đạt; ngưỡng CHƯA CHỐT) *khuya 24/09/2026 (chưa commit, không phiên đo thiết bị nào):* độ lặp lại khoảng cách viết lại thành `lidar/repeatability.py`, chạy offline cho lại đúng số của mục 3b (p07, k01: trung vị 1,0–1,5 mm giữa hai vòng); thêm live_headless 0,75–1,0 mm (28 vòng, chưa rõ vì sao thấp hơn), nên khoảng của ba bản ghi là 0,75–1,5 mm; đều là độ lặp lại giữa hai vòng, không phải sai số so với thước *(sửa sau rà soát, khuya 24/09/2026: bản trước gán cả khoảng 0,75–1,5 mm cho mục 3b)*; bản nhỏ của k01 đã chép vào `docs/evidence/lidar/`; odometry khớp scan (`lidar/scan_odometry.py`) và so sánh bốn phương án định vị, chạy offline trên dữ liệu tổng hợp, DROW v2 và bản ghi C1 đứng yên; đề xuất bản đồ tĩnh + định vị lại làm nguồn tư thế chính: ĐỀ XUẤT – CHỜ CHỐT; "định vị lại được" vẫn chưa đạt | [Chuẩn bị khi chờ đồ](autopark/docs/GIAI_DOAN_1_CHUAN_BI.md); [Nhánh LiDAR: driver C1, ghi phiên, bản đồ tĩnh, kiểm lại 24/09 ở mục 3b](autopark/docs/GIAI_DOAN_1_LIDAR.md); [Nhánh camera: mode, FPS, khung cũ, đính chính mục 4.6](autopark/docs/GIAI_DOAN_1_CAMERA.md); [mode camera](autopark/docs/camera_modes.csv); [gate_01](autopark/docs/gate_01.md); [kiểm kê](autopark/docs/hardware_inventory.md); [công cụ hiệu chuẩn camera, bảng in (mã có từ 24/09/2026, mới kiểm trên ảnh tổng hợp)](autopark/docs/HIEU_CHUAN_CAMERA.md); [công cụ gán nhãn ảnh sa bàn: nháp từ AI, sửa tay, duyệt (có từ 24/09/2026, chưa gán nhãn ảnh thật nào)](autopark/docs/GAN_NHAN_SA_BAN.md); [định vị LiDAR trên bản đồ tĩnh (tối 24/09/2026; dữ liệu tổng hợp, 29 test, và bản ghi có sẵn; chưa có tham chiếu độc lập)](autopark/docs/DINH_VI_LIDAR.md); [độ lặp lại LiDAR, mục 3c (khuya 24/09/2026)](autopark/docs/GIAI_DOAN_1_LIDAR.md); [so sánh phương án định vị/SLAM, odometry khớp scan (khuya 24/09/2026, offline)](autopark/docs/SO_SANH_DINH_VI_SLAM.md) | Còn thiếu 7 lần đặt hộp để đo sai số khoảng cách và chốt dấu góc trái/phải (cần người); camera chưa đặt ở độ cao/góc chúc dự kiến, chưa hiệu chuẩn (mã hiệu chuẩn fisheye và bảng để in có từ 24/09, mới kiểm trên ảnh tổng hợp; chưa in bảng, chưa chụp ảnh); AI chưa chấm trên ảnh thật có nhãn; chưa có định vị *(tối 24/09/2026: có công cụ định vị trên bản đồ tĩnh, nhưng chưa có tham chiếu độc lập, chưa thử khi cảm biến di chuyển, chưa có SLAM)*; chưa thử trên laptop RTX 3050 Ti (máy nộp đồ án); *(khuya 24/09/2026)* chưa có bản ghi C1 nào khi cảm biến di chuyển; phương án định vị chờ người dùng chọn | Phiên đặt hộp 7 lần theo GIAI_DOAN_1_LIDAR.md mục 6; *(tối 24/09/2026)* cùng buổi: hai phiên liên tiếp có khởi động lại mô-tơ để biết gốc góc có đổi không, và 3–6 vị trí/hướng đo bằng thước làm tham chiếu cho định vị (DINH_VI_LIDAR.md mục 7); in bảng ô vuông và hiệu chuẩn camera; chụp ảnh sa bàn ở độ cao thật, gán nhãn, chấm AI; thử trên laptop RTX 3050 Ti (máy nộp đồ án); *(khuya 24/09/2026)* cùng buổi đặt hộp: đẩy C1 trên tấm ván theo đường dán băng có mốc (SO_SANH_DINH_VI_SLAM.md mục 8.4); người dùng chọn phương án định vị |
| 2 — Bốn camera/BEV | ĐANG LÀM (24/09/2026: bốn camera + LiDAR + AI chạy chung trên máy bàn, có giao diện trực tiếp; mặc định 640×480 vì khung MJPEG bị cắt khi bốn camera chạy chung qua hub; danh tính camera theo cổng hub giữ được sau khởi động lại; từ 24/09 AI không chờ camera chậm quá ≈ 62 ms (`--max-wait-ms`, mặc định bật, GIAI_DOAN_2_BAN_THU.md mục 10): đo trên bàn thử không bỏ nhầm camera khỏe nào (0 trong 7155 bộ, chỉ đúng khi bốn camera cùng nhịp), nhưng lợi ích chính chưa đo được vì không phiên nào có camera chậm; chưa gá, chưa hiệu chuẩn, chưa có BEV; *cập nhật tối 24/09/2026:* bản trên bỏ camera khỏe ở 263/855 bộ khi cổng 1 chạy 29,3 khung/s ở phơi sáng tự động còn cổng 2–4 chạy 23,85 khung/s (m02, 720p, 15:25), nên quy tắc chờ đổi sang ngưỡng riêng theo nhịp của từng camera (GIAI_DOAN_2_BAN_THU.md mục 10.1–10.2); đo lại trên máy bàn: bỏ camera khỏe 0/715 bộ (o01, 720p chỉ camera) và 0/2862 bộ (o02, 480p + LiDAR + AI, trước đó m01 3/2861), đổi lại độ lệch trong bộ lớn hơn ở 720p (trung vị 28,5 so với 24,5 ms, max 52,8 so với 40,3 ms); nhánh bỏ camera lỡ nhịp (khung hỏng, treo) chỉ kiểm bằng mô phỏng và test vì hai phiên không có khung hỏng; AI làm nóng mọi cỡ lô trước bộ ảnh đầu (lô đầu mỗi cỡ 4/3/2/1 ảnh mất 1,2–1,7 s), o07 sau sửa 0 bộ bỏ camera, lô chậm nhất 18,3 ms; ghi/phát lại phiên bốn camera + LiDAR: một phiên thật 60 s (5724 khung, 0 khung bị bỏ, 4,98 MB/s, cảnh tối), phát lại cho đúng 1432/1432 bộ và cùng độ lệch trung vị/p95/max; BEV từ AI: phần mềm và test trên rig tổng hợp, **chưa chạy trên camera dự án** (chưa hiệu chuẩn, ngoại tham GIẢ ĐỊNH — CHƯA ĐO, chưa có ROI), chưa kiểm vật mẫu trên BEV; mọi thay đổi tối 24/09 chưa commit *(khuya 24/09/2026: đã commit và push lúc 20:22 trong `bfcbfc2` (bàn thử, tham chiếu 19:08) và `1d2b857` (BEV))*) *khuya 24/09/2026 (chưa commit, không phiên đo thiết bị nào):* công cụ ngoại tham (bảng trên sàn, đo bằng thước trong hệ xe) và mặt nạ ROI cho camera dự án, giao diện `ui/roi_app.py`, **chỉ kiểm trên ảnh tổng hợp**, chưa đo camera nào; BEV nhanh hơn ≈ 10 lần, kết quả trùng từng bit, ≈ 7–12 ms cho 4 camera trên rig tổng hợp (máy bàn, dưới tải); vẫn chưa chạy trên camera dự án | [Bàn thử giai đoạn 2: số đo, khung bị cắt, giao diện](autopark/docs/GIAI_DOAN_2_BAN_THU.md); [sơ đồ cổng USB, danh tính sau rút/cắm và khởi động lại](autopark/docs/usb_topology.md); [hiệu chuẩn từng camera (bước 4): công cụ có từ 24/09/2026, chưa hiệu chuẩn camera nào](autopark/docs/HIEU_CHUAN_CAMERA.md); [số đo tối 24/09/2026 rút gọn: o01–o07, m01/m02, lô đầu từng cỡ](autopark/docs/evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json); [ghi/phát lại phiên bàn thử, mục 7 là phiên thật (tối 24/09/2026)](autopark/docs/GHI_PHAT_LAI_BAN_THU.md); [BEV từ AI (bước 7; tối 24/09/2026, rig tổng hợp, chưa chạy trên camera dự án)](autopark/docs/BEV.md); [ngoại tham và ROI (khuya 24/09/2026, ảnh tổng hợp)](autopark/docs/NGOAI_THAM_VA_ROI.md) | 720p × 4 qua hub này không dùng được (khung bị cắt phụ thuộc cảnh: ngày 24/09 camera nhìn chỗ tối thì 720p không có khung bị cắt nào, chưa phải bằng chứng 720p dùng được); ở 480p camera cổng 1 vẫn có đợt 26–36 % khung hỏng, chưa rõ nguyên nhân (bộ dò loại các khung đó); chưa thử nguồn ngoài cho hub; chưa đo độ trễ từ sự kiện thật tới máy; chưa đo trên laptop RTX 3050 Ti (máy nộp đồ án); *(tối 24/09/2026)* lợi ích của quy tắc chờ khi camera lỡ nhịp thật vẫn chưa đo trên phần cứng; BEV cần nội tham bốn camera, ngoại tham đo và ROI, và mất ≈ 69,5 ms cho bốn camera (hơn một chu kỳ khung); làm nóng AI làm bàn thử sẵn sàng chậm hơn ≈ 4,2 s; laptop chưa có mã tối 24/09 cho tới khi commit/push *(khuya 24/09/2026: đã commit và push, laptop `git pull` là có)*; *(muộn tối 24/09/2026)* tham chiếu máy bàn cho lệnh đo laptop đã đo lại lúc 19:08 bằng mã mới ([tham_chieu_20260924_toi.json](autopark/docs/evidence/may_ban/tham_chieu_20260924_toi.json), chưa commit *(khuya 24/09/2026: nay trong `bfcbfc2`)*): 480p 0/2861 bộ bỏ camera khỏe, làm nóng AI tổng ≈ 5,9 s; ở 720p lần này không camera nào chạy ≈ 29 khung/s (camera nhanh không cố định một cổng: cổng 3 ở s01–s07, t01, t02 ngày 23/09; cổng 1 ở t05 ngày 23/09 và lúc 15:25, 17:56 ngày 24/09), nên phiên 720p đó không thử lại tình huống hai nhịp khác nhau; *(khuya 24/09/2026)* BEV không còn chậm hơn một chu kỳ khung trên máy bàn (mục 6b của BEV.md), nhưng khung đầu vẫn ≈ 0,3–0,5 s để dựng bảng và laptop CHƯA ĐO; ngoại tham và ROI có công cụ nhưng chờ nội tham và gá; sai số thước là nguồn sai số lớn nhất của ngoại tham (tổng hợp: ±2,5 mm mỗi điểm cho tới 0,93° hướng camera) | Tách camera ra nhiều cổng gốc, thử nguồn ngoài cho hub; chạy một phiên có camera chậm thật để đo lợi ích và mức bỏ nhầm của quy tắc không chờ; hiệu chuẩn từng camera, gá rig, rồi BEV và hợp nhất với LiDAR (GIAI_DOAN_2_BAN_THU.md mục 9); *(tối 24/09/2026)* ghi phiên có camera lỡ nhịp rồi phát lại cùng bản ghi với `--max-wait-ms 60` và `--max-wait-ms 0`; sau hiệu chuẩn, gá và ROI thì đặt vật mẫu ở vị trí đo bằng thước để kiểm BEV (BEV.md mục 8); *(khuya 24/09/2026)* chạy `bev bench` trên laptop; sau hiệu chuẩn nội tham và gá: đo ngoại tham, dựng ROI bằng `ui.roi_app` theo NGOAI_THAM_VA_ROI.md |
| 3 — Fusion bench | ĐANG LÀM (phần mềm khi chưa có IMU/ToF/ESP32, 22/09/2026) *khuya 24/09/2026 (chưa commit, không phiên đo thiết bị nào):* cầu nối `VehicleTelemetry` → `NearFieldReading` với bảng gá ToF `configs/tof_mounts_v0.json` (GIẢ ĐỊNH – CHƯA ĐO); một ToF không dùng được chỉ mất cung của nó; demo hợp nhất bỏ ≥ 22 vòng khởi động và có `--warmup`; cả hai chỉ kiểm bằng nguồn giả | [Các lớp bản đồ, hợp nhất, cầu nối vào phiên, demo LiDAR thật](autopark/docs/GIAI_DOAN_3_CHUAN_BI.md); [đặc tả trường IMU/ToF trong telemetry xe, có cờ hợp lệ và mặt nạ ToF (24/09/2026, làm trong giai đoạn 5)](autopark/docs/GIAO_THUC_XE.md) | Chưa có IMU, ToF, ESP32, gá cảm biến; ToF chỉ có số đo giả; khung camera thật chưa đi qua lớp `CameraSemantic`; chưa thử đưa tay hay rút cáp LiDAR thật khi xe ảo đang chạy; *(24/09/2026)* trường IMU/ToF trong telemetry mới có đặc tả và mã Python, chưa có bo; VehicleIO mô phỏng chưa sinh số ToF (luôn không hợp lệ); chưa có cầu nối từ `VehicleTelemetry` sang `NearFieldReading`; *(khuya 24/09/2026)* cầu nối đã có (chưa commit) nhưng ToF chưa vào phiên; giao thức v1 không phân biệt "không có vật" với "ToF hỏng" (mặt nạ sức khỏe: ĐỀ XUẤT – CHỜ CHỐT) | Đọc ToF/IMU thật qua ESP32; thử vật mẫu có tọa độ đo được; thử đưa tay/rút cáp với LiDAR thật; *(khuya 24/09/2026)* chạy demo với C1 thật `--warmup 4.5` để xem vòng nền |
| 4 — Đo MN300 | ĐANG LÀM (phần "khi chưa có xe", 24/09/2026: hình học xe trong cấu hình ghi rõ là giả định, chưa phải số đo MN300; chiến dịch kiểm thử 20/09 đã chạy planner với kích thước giả định biến đổi — 40 ca, bề rộng và chiều dài cơ sở 0,85–1,15 lần mặc định; các ca hình học và phiên kín vòng 0,7–1,4 lần — nhưng chưa phải phép thử độ nhạy riêng; chưa có MN300, chưa đo gì trên xe; *cập nhật tối 24/09/2026:* đã soạn phiếu kiểm kê MN300 (mẫu, chưa điền), bảng đo B0–B8 (hình học, góc lái, bán kính quay, tốc độ thấp, đổi chiều, quãng dừng, đường cong lệnh, xung servo), cách đưa số đo vào cấu hình, khái niệm gá điều chỉnh được; phép thử độ nhạy riêng mới đề xuất, CHƯA CHẠY; mọi số CHƯA ĐO) *khuya 24/09/2026 (chưa commit, không phiên đo thiết bị nào):* phép thử độ nhạy với sa bàn cố định đã chạy hai lượt **mô phỏng** bằng `evaluation/sensitivity.py` (860 lần chạy mỗi lượt, dưới tải, chưa chạy khi máy rảnh): 11/20 sa bàn giải được ở mọi biến thể ±5/10/20 %, mười cặp hỏng ở cả hai lượt đều là xe dài hơn 10–20 %; `robustness`, `phase0`, `ui.lidar_app` nhận `--vehicle-config`; vẫn chưa có số đo MN300 | [vehicle_default.json](autopark/configs/vehicle_default.json) (trường `notes`); [kiểm thử độ bền giai đoạn 0, mục 3](autopark/docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md); `planner_case` trong [evaluation/robustness.py](autopark/autopark/evaluation/robustness.py); [chuẩn bị giai đoạn 4, bảng đo B0–B8 (bản nháp tối 24/09/2026, CHƯA ĐO)](autopark/docs/GIAI_DOAN_4_CHUAN_BI.md); [phiếu kiểm kê MN300 (mẫu, chưa điền)](autopark/docs/mn300_inventory.md); [độ nhạy theo kích thước xe (khuya 24/09/2026, mô phỏng)](autopark/docs/DO_NHAY_KICH_THUOC_XE.md) | Chưa có MN300; chưa có phiếu kiểm kê xe, bảng đo tốc độ/góc lái/bán kính quay/dừng, phương án gá *(tối 24/09/2026: phiếu kiểm kê và bảng đo đã có dạng nháp; gá mới ở mức khái niệm; định dạng `vehicle_measured` và dụng cụ đo xung CHƯA CHỐT)*; *(khuya 24/09/2026)* `robustness --vehicle-config` chỉ giữ tỉ lệ footprint, góc lái/tốc độ/gia tốc vẫn rút từ khoảng cố định; `fusion/demo.py` chưa nhận tệp xe | Viết phiếu kiểm kê xe và bảng đo tốc độ, góc lái, bán kính quay, quãng dừng *(tối 24/09/2026: đã soạn)*; chạy phép thử độ nhạy theo GIAI_DOAN_4_CHUAN_BI.md mục 5.3; khi nhận xe làm theo mục 8 và thứ tự ở GIAI_DOAN_4_CHUAN_BI.md mục 7; *(khuya 24/09/2026)* chạy lại độ nhạy khi máy rảnh (`--workers 1`); khi có số đo, chạy `--plan-config` với `configs/vehicle_measured.json` |
| 5 — Điều khiển có phản hồi | ĐANG LÀM (phần "khi chưa đủ phần cứng", 24/09/2026: đặc tả giao thức Command/Telemetry, bản tham chiếu Python của firmware có watchdog/giới hạn/trạng thái cho phép chạy/trần ga, VehicleIO mô phỏng có vùng chết, độ trễ, nhiễu; firmware C++ cho ESP32-S3 viết xong nhưng CHƯA biên dịch; *cập nhật tối 24/09/2026:* `VehicleIO` nối vào phiên đỗ xe (chế độ `VEHICLE_IO`) và có chế độ quan sát, **chỉ với bo mô phỏng và cổng serial giả**; kiểm trạng thái thật trước START, dừng khi telemetry/tư thế cũ, không tự chạy tiếp sau dừng (trừ một khoảng trống đã biết trên mô phỏng khi chạy kèm `Heartbeat`: có thể thêm một COMMAND enable=1, test `xfail`, cách sửa CHƯA LÀM, [GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md) mục 12); ghi `commands.csv`, `telemetry.csv`; tư thế lấy từ mô phỏng (định vị lý tưởng); 34 test đạt lúc 17:41; *chạy lại 18:41 sau khi tệp test được bổ sung:* 50 test, 49 đạt + 1 `xfail` strict, chính là khoảng trống trên; *cập nhật muộn tối 24/09/2026:* khoảng trống đó đã sửa (`VehicleLink.refresh()` lấy telemetry và sự kiện đã tới trước nhịp điều khiển; `command()` không gửi lệnh chạy khi còn sự kiện dừng chưa xử lý), vẫn **chỉ kiểm trên mô phỏng và cổng serial giả**; còn khoảng hở khi khung telemetry báo bo đã về ARMED chưa tới laptop (suy ra từ mã, chưa có test, [GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md) mục 12); tệp test nay 60 test, 60 đạt, 0 `xfail`) *khuya 24/09/2026 (chưa commit, không phiên đo thiết bị nào):* thẻ "Bo điều khiển" chọn cổng serial và nút "Kiểm kết nối bo" (HELLO, so giới hạn, đọc telemetry, không ARM, không COMMAND); so giới hạn trong HELLO_ACK với cấu hình xe, lệch nguy hiểm thì START ở `VEHICLE_IO` bị từ chối (ĐỀ XUẤT – CHỜ CHỐT); START với bo thật luôn bị từ chối vì chưa có nguồn tư thế thật; **chỉ bo mô phỏng và cổng serial giả**; chốt firmware sau `COMMAND_TIMEOUT` để đóng khoảng hở còn lại: chờ người dùng duyệt, CHƯA LÀM | [Giao thức xe và firmware](autopark/docs/GIAO_THUC_XE.md); [nối `VehicleIO` vào phiên, chế độ quan sát (tối 24/09/2026, chỉ mô phỏng)](autopark/docs/CHE_DO_QUAN_SAT.md) | Chưa có ESP32-S3, MN300, encoder, AS5600; chân GPIO, mức xung ESC/servo, hành vi ESC khi mất xung đều CHƯA CHỐT; máy hiện không có trình biên dịch C/C++; *(tối 24/09/2026)* chưa có nguồn tư thế thật cùng đồng hồ với bo; giao diện chưa có lựa chọn cổng serial tới bo thật; lần chạy qua `VehicleIO` chưa replay được; *(tối 24/09/2026)* sau khi vòng điều khiển treo quá hạn lệnh mà `Heartbeat` vẫn chạy, phiên có thể gửi thêm một COMMAND enable=1 trước khi nhận `VEHICLE_STOPPED` (chỉ thấy trên mô phỏng, chưa sửa) *(muộn tối 24/09/2026: đã sửa ở mức mô phỏng; chưa thử trên bo thật; còn khoảng hở khi khung báo bo về ARMED chưa tới laptop, suy ra từ mã, chưa có test; `replay_run` nay từ chối rõ lần chạy qua `VehicleIO` bằng `ReplayNotSupported`, vẫn chưa phát lại được)*; *(khuya 24/09/2026)* lựa chọn cổng serial đã có ở mức giao diện (chưa mở cổng thật nào); còn thiếu nguồn tư thế thật và bước mở cổng trong `begin_run`; "Kiểm kết nối bo" chưa thử với ESP32-S3 (DTR/RTS có làm bo khởi động lại không: cần tra) | Biên dịch firmware bằng PlatformIO, chạy test host với vectors.json; khi có bo: đo xung bằng máy hiện sóng theo [firmware/esp32_vehicle/README.md](autopark/firmware/esp32_vehicle/README.md); *(tối 24/09/2026)* sửa khoảng trống COMMAND sau treo (`vehicle_link.py`/`session.py`), xem [GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md) mục 12 *(muộn tối 24/09/2026: đã làm ở mức mô phỏng; khi có ESP32-S3, chạy lại kịch bản treo quá hạn lệnh khi có `Heartbeat` trên bo thật)*; *(khuya 24/09/2026)* người dùng quyết định chốt firmware sau `COMMAND_TIMEOUT` (GIAO_THUC_XE.md mục 12); khi có bo, chạy "Kiểm kết nối bo" trước |
| 6 — Nguồn/dừng | ĐANG LÀM (phần "khi chưa có nguồn final", 24/09/2026: trong đặc tả giao thức và firmware đã viết trước các tình huống mất liên lạc, rút cáp, treo chương trình, bo khởi động lại; reset và reconnect luôn về DISARMED; E-stop chốt FAULT; đã chọn ngõ vào E-stop an toàn khi hở mạch nhưng chưa lắp; firmware C++ CHƯA biên dịch; chưa có phần cứng nguồn/dừng; *cập nhật tối 24/09/2026:* có bản nháp bảng tải, sơ đồ nguồn, sơ đồ dừng, bảng định mức còn phải kiểm và 16 kịch bản lỗi L1–L16; số điện duy nhất là datasheet RPLIDAR C1, còn lại CHƯA ĐO hoặc CẦN TRA datasheet; cả 16 kịch bản CHƯA THỬ trên thiết bị) | [Giao thức xe, mục 0, 5, 6 và 10](autopark/docs/GIAO_THUC_XE.md); [nguồn và dừng: bản nháp khi chưa có nguồn final (tối 24/09/2026, CHƯA ĐO, CHƯA THỬ)](autopark/docs/GIAI_DOAN_6_CHUAN_BI.md) | Chưa có bộ nguồn, LA38, cầu chì, dây, phần tử ngắt; chưa có `power_budget.md`, sơ đồ nguồn/dừng *(tối 24/09/2026: có bản nháp trong GIAI_DOAN_6_CHUAN_BI.md, chưa có số đo; tách `power_budget.md` riêng hay không CHƯA CHỐT)*; ngõ vào E-stop của firmware không thay đường cắt động lực; *(tối 24/09/2026)* các lựa chọn N1–N7 (laptop trên xe, nguồn bo, nguồn servo, UBEC/XL4015, nguồn hub, công tắc logic, ESC) và phần tử mà LA38 cắt CHƯA CHỐT | Lập bảng tải điện áp/dòng, sơ đồ nguồn và sơ đồ dừng; xác định phần tử mà LA38 cắt (mục 10) *(tối 24/09/2026: nháp đã có; bước kế là chốt N1–N7 và phần tử ngắt trước đợt mua 6, rồi đo theo GIAI_DOAN_6_CHUAN_BI.md mục 1.3 và thử các kịch bản mục 5 khi có phần cứng)* |
| 7 — Sensor rig lên xe | CHƯA LÀM (24/09/2026: chưa có MN300, chưa có gá) | | Thiết kế sàn/gá cần số đo MN300 (giai đoạn 4) | Thiết kế gá sau khi đo xe |
| 8 — Fusion trên xe | ĐANG LÀM (phần "khi chưa thể chạy trên xe", 22/09/2026, trên bàn thử và xe ảo: mỗi lớp dữ liệu có tuổi tối đa; lớp bắt buộc cũ hoặc mất làm bản đồ hợp nhất không hợp lệ, mọi ô bị chặn; phép đổi tọa độ rig–map mới thử bằng điểm biết trước trong test; chưa chạy trên xe) *khuya 24/09/2026 (chưa commit):* odometry khớp scan (b) có mã và chạy offline; đề xuất dùng nó làm dự đoán và giám sát chéo cho định vị trên bản đồ tĩnh, thêm odometry bánh xe/IMU khi có (ĐỀ XUẤT – CHỜ CHỐT, SO_SANH_DINH_VI_SLAM.md mục 7); chưa ghép, chưa nối vào phiên | [Giai đoạn 3 — chuẩn bị, mục 1](autopark/docs/GIAI_DOAN_3_CHUAN_BI.md); [safety/freshness.py](autopark/autopark/safety/freshness.py) | Chưa có xe chuyển động và cảm biến trên xe; chưa kiểm phép đổi tọa độ bằng điểm biết trước trên dữ liệu thật; chưa thử mâu thuẫn global map/quan sát trên dữ liệu thật | Chạy lại dữ liệu bàn thử với trễ, lệch timestamp và mất nguồn dữ liệu giả lập (mục 12) |
| 9 — Tự đỗ thật | CHƯA LÀM phần chạy thật (24/09/2026); quy trình bắt đầu, dừng, chọn lại vị trí và lập lại đường trên UI mới có trong mô phỏng giai đoạn 0 (20/09/2026); *cập nhật tối 24/09/2026:* chế độ quan sát (phần mềm tính đường và lệnh nhưng không gửi COMMAND nào, bo phải ở DISARMED) và kiểm lại trạng thái thật trước START có trong phiên đỗ xe, **chỉ mô phỏng** *khuya 24/09/2026 (chưa commit):* có bản nháp bộ kịch bản nghiệm thu (nhóm vật cản mới VC, dừng và an toàn AT…), mọi kịch bản CHƯA THỬ | [Giai đoạn 0](autopark/docs/GIAI_DOAN_0.md); [chế độ quan sát (tối 24/09/2026, chỉ mô phỏng)](autopark/docs/CHE_DO_QUAN_SAT.md) | Chưa có xe; chưa có kích thước/giới hạn đo trên MN300 để chạy toàn phiên đỗ mô phỏng theo mục 13; chưa có chế độ quan sát *(tối 24/09/2026: có ở mức mô phỏng; chưa có tư thế thật, cách đấu dây khi quan sát CHƯA CHỐT)* | Sau giai đoạn 4–8 |
| 10 — Đánh giá/khóa luận | ĐANG LÀM (phần "khi chưa đủ bộ xe", 24/09/2026: đã có biên bản kết quả riêng AI/CV trên ảnh của bộ dữ liệu công khai và kết quả mô phỏng; công cụ gán nhãn sa bàn chia tập theo phiên chụp và đóng băng split; chưa có kết quả xe thật; *cập nhật tối 24/09/2026:* có dàn ý khóa luận đề xuất (bản nháp, không thêm số đo mới) và bảng kịch bản lỗi nguồn/dừng L1–L16 (CHƯA THỬ) ở tài liệu giai đoạn 6) *khuya 24/09/2026 (chưa commit, không phiên đo thiết bị nào):* bản nháp bộ kịch bản nghiệm thu (37 kịch bản, 9 nhóm, phương pháp đo độc lập R1–R7, mẫu biên bản) và ngưỡng đề xuất cho mục 16.2 (mã N-…); mọi ngưỡng ĐỀ XUẤT – CHỜ CHỐT, mọi kịch bản CHƯA THỬ; chấm RoadAnomaly21 (10 ảnh có nhãn, dữ liệu công khai); `evaluate.py` từ chối chấm ảnh đã học | [Huấn luyện AI](HUAN_LUYEN.md); [báo cáo giai đoạn 0](BAO_CAO_GIAI_DOAN_0.md); [gán nhãn sa bàn](autopark/docs/GAN_NHAN_SA_BAN.md); [dàn ý khóa luận (bản nháp tối 24/09/2026)](autopark/docs/DAN_Y_KHOA_LUAN.md); [kịch bản nghiệm thu (bản nháp khuya 24/09/2026)](autopark/docs/KICH_BAN_NGHIEM_THU.md); [ngưỡng nghiệm thu đề xuất (khuya 24/09/2026)](autopark/docs/NGUONG_NGHIEM_THU_DE_XUAT.md) | AI chưa chấm trên ảnh sa bàn có nhãn; chưa có bảng kịch bản và cách đo độc lập cho nghiệm thu; giấy phép WoodScape (xem dòng giai đoạn 0); *(tối 24/09/2026)* mẫu khóa luận của trường, kiểu trích dẫn, giới hạn trang và quy định khai báo công cụ AI chưa biết; *(khuya 24/09/2026)* bảng kịch bản và cách đo độc lập đã có bản nháp, chưa duyệt; còn thiếu công cụ T2–T15 (nguồn tư thế thật, tham chiếu trên cao, ghi sự kiện dừng, dấu đồng bộ video–log, nút CLEAR_FAULT…) | Chấm AI trên ảnh sa bàn có nhãn; chuẩn bị bảng kịch bản (mục 16.3), cách đo độc lập và định nghĩa thành công/thất bại trước khi thu kết quả cuối; *(tối 24/09/2026)* hỏi GVHD/khoa về mẫu khóa luận và quy định khai báo công cụ AI (DAN_Y_KHOA_LUAN.md mục 7); *(khuya 24/09/2026)* người dùng + GVHD duyệt từng mã N-… và bộ kịch bản trước khi thu kết quả cuối; làm ngay DV-1, DV-2, LD-1 (KICH_BAN_NGHIEM_THU.md mục 6) |

*Cập nhật 24/09/2026: chưa cổng nào từ 1 tới 10 đạt (mới có biên bản [gate_01](autopark/docs/gate_01.md), CHƯA ĐẠT); chưa điều kiện V1 nào ở mục 16.4 được đánh dấu đạt.*

*Cập nhật tối 24/09/2026: các dòng giai đoạn 1, 2, 4, 5, 6, 9, 10 ghi thêm bảy việc tối 24/09 (tóm tắt ở [TONG_HOP_DU_AN.md](TONG_HOP_DU_AN.md) đầu tệp). Không cổng và không điều kiện V1 nào đổi trạng thái. Số đo trên thiết bị của đợt này chỉ có trên máy bàn; chưa có gì trên laptop RTX 3050 Ti (máy nộp đồ án). Mã và tài liệu của đợt này chưa commit.*

*Cập nhật muộn tối 24/09/2026 (sau 19:08): dòng giai đoạn 5 ghi bản sửa khoảng trống an toàn (chỉ mô phỏng và cổng serial giả), dòng giai đoạn 2 ghi tham chiếu máy bàn mới cho laptop. Toàn bộ bộ test chạy lại trên máy bàn: `.venv` 895 đạt, 6 bỏ qua (mô-đun cần torch); `.venv-train` 248 đạt. Vẫn không cổng và không điều kiện V1 nào đổi trạng thái; vẫn chưa commit.*

*Cập nhật khuya 24/09/2026: bảy việc tối 24/09 nêu ở hai dòng trên **đã commit và push** lúc 20:22 thành năm commit `bfcbfc2`, `1d2b857`, `b100a5d`, `c43e8d3`, `9bcc30c` (`origin/main` = `9bcc30c`), nên chữ "chưa commit" ở hai dòng trên đã lỗi thời, và cả mọi chữ "chưa commit" hay "cho tới khi commit/push" gắn với việc tối hoặc muộn tối 24/09 trong các dòng giai đoạn của bảng (dòng giai đoạn 2 có ghi chú tại chỗ); chỉ chữ "chưa commit" trong phần ghi "khuya 24/09/2026" là còn đúng. *(Sửa sau rà soát, khuya 24/09/2026: bản trước chỉ nói hai dòng trên; cùng lần sửa, dòng giai đoạn 1 tách số độ lặp lại của mục 3b khỏi số mới của live_headless.)* Các dòng giai đoạn 0, 1, 2, 3, 4, 5, 8, 9, 10 ghi thêm đợt khuya (mười một việc, **chưa commit**, tóm tắt ở [TONG_HOP_DU_AN.md](TONG_HOP_DU_AN.md) đầu tệp và mục 4.15). Đợt này không có phiên đo mới nào trên thiết bị: chỉ ảnh/dữ liệu tổng hợp, mô phỏng, cổng serial giả, hoặc chạy offline trên dữ liệu có sẵn. Không cổng và không điều kiện V1 nào đổi trạng thái. Chốt firmware sau `COMMAND_TIMEOUT` còn chờ người dùng duyệt.*

---

# 18. LINK NGUỒN MUA ĐÃ ĐƯỢC NGƯỜI DÙNG CUNG CẤP

**Chỉ lưu lại để đối chiếu đợt mua. Không xác minh lại giá, tồn kho hoặc đúng biến thể trong lần biên soạn kế hoạch này; không phải giỏ hàng đã được bảo đảm tương thích.** Không đưa tổng tiền cũ vào làm ngân sách đã chốt.

| Hạng mục | Link đã cung cấp | Ghi chú dùng trong kế hoạch |
|---|---|---|
| MN300 Tank300 | https://shopee.vn/product/49222047/24674768117 | Xe nền hiện hành; xác nhận gói pin/sạc thực giao. |
| RPLIDAR C1M1 | https://shopee.vn/product/1419756587/45651899727 | Hỏi rõ bộ nối laptop. |
| Camera USB AdaChoi | https://shopee.vn/product/1264216444/55807744269 | Mẫu theo BOM: 130°; mua một trước. |
| UGREEN 50985 | https://shopee.vn/product/1283561216/28453158757 | Hub ứng viên; không mặc định đủ tải bốn camera. |
| Cáp UGREEN 90722 | https://shopee.vn/product/60169370/22378467940 | Thử sau cấu hình dây ngắn; không bắt buộc mua đợt 1. |
| ESP32-S3 chính | https://shopee.vn/product/107147748/40425371167 | Một bo duy nhất; có thể mua sớm để đọc IMU/ToF trên bench. |
| AS5600 | https://shopee.vn/product/578443443/11880418419 | Xác minh bộ nam châm, giao tiếp và gá. |
| MT6701 | https://shopee.vn/product/1257696740/40455544497 | Xác minh chân/mode và gá trước chốt. |
| GY-BNO085 | https://shopee.vn/product/81431289/27362128544 | Đúng phân loại BNO085 theo danh sách người dùng. |
| VL53L1X | https://shopee.vn/product/237617462/26162878906 | Mẫu hàn sẵn chân; thử hai trước. |
| UBEC ứng viên | https://shopee.vn/product/75359161/7525834451 | Chỉ chọn theo điện áp/tải thực; không khẳng định mọi phân loại tương đương. |
| XL4015 ứng viên cũ | https://shopee.vn/product/27117857/349326027 | Chưa bắt buộc mua; chọn nguồn sau bảng tải. |
| Nút LA38 | https://shopee.vn/product/1097845497/25309631912 | Phải phối hợp với đường dừng/phần tử ngắt phù hợp. |
| Cầu chì/đế | https://shopee.vn/product/265439065/18077814935 | Không chốt 15 A chỉ từ link. |
| XT60 dây sẵn | https://shopee.vn/product/27693865/40306450328 | Kiểm tra tương thích đầu nối hệ nguồn. |

---

## KẾT LUẬN KẾ HOẠCH

**Làm phần mềm, AI/CV và perception bench trước; xe thật là bước kiểm chứng tiếp theo, không phải điều kiện để bắt đầu mọi công việc.**

```text
Chưa có đồ: mô phỏng + dữ liệu AI + giao diện + hợp đồng dữ liệu + kiểm thử.
Có cảm biến: đo từng khối → kiểm tra đồng thời → hiệu chuẩn → hợp nhất trên rig.
Có xe: đo đặc tính → nguồn/dừng + điều khiển phản hồi → chuyển rig lên xe.
Đủ điều kiện: tự đỗ thật → vật cản bất ngờ → đánh giá định lượng → luận văn.
```

Có thể chuyển sang công việc độc lập khi thiếu linh kiện, nhưng **không được thay thế phép thử phần cứng bằng kết quả mô phỏng hoặc bỏ qua cổng an toàn để giữ tiến độ**.
