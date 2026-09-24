# Giai đoạn 4 — chuẩn bị đo đặc tính MN300 khi chưa có xe (24/09/2026)

**Kế hoạch đối chiếu:** [v3.1](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 8 (giai đoạn 4, "Khi chưa có xe" và "Khi
nhận xe"), mục 3 (đợt mua 4), mục 16.1 (khảo sát tốc độ 0,05–0,15 m/s), mục 16.2 (ngưỡng "Điều khiển" cần chốt trên xe).

**Mức bằng chứng:** tài liệu và công thức. **Chưa nhận MN300; chưa đo gì trên xe.** Mọi số trong tệp này là giá trị giả
định đang có trong cấu hình và mã, hoặc là kết quả tính từ các giá trị đó. Không số nào là thông số của MN300. Mọi ô
"Đo được" để trống hoặc ghi "CHƯA ĐO".

Phiếu kiểm kê xe (gói hàng, pin/sạc, ESC, bộ thu, servo, motor, đầu nối, ảnh, câu hỏi cho shop):
[mn300_inventory.md](mn300_inventory.md). Nguồn và dừng khẩn cấp: [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md).

## 0. Bốn việc "khi chưa có xe" của kế hoạch mục 8

| Việc trong kế hoạch | Ở đâu | Trạng thái (24/09/2026) |
|---|---|---|
| Viết phiếu kiểm kê xe | [mn300_inventory.md](mn300_inventory.md) | mẫu đã soạn, chưa điền (chưa có xe) |
| Chuẩn bị bảng đo tốc độ, góc lái, bán kính quay và dừng | mục 3 dưới đây (B0–B8) | bảng và cách đo đã soạn; CHƯA ĐO |
| Để hình học xe trong cấu hình với nhãn `CHƯA ĐO`; thử độ nhạy planner theo kích thước giả định | mục 1 (ánh xạ tham số), mục 5 (độ nhạy) | trường `notes` của [vehicle_default.json](../configs/vehicle_default.json) đã ghi rõ là giả định; **chưa có phép thử độ nhạy riêng** (mục 5 giải thích vì sao chiến dịch 20/09 chưa phải phép thử đó) |
| Lên phương án gá điều chỉnh được, chưa gia công phần phụ thuộc kích thước chưa biết | mục 6 | khái niệm bằng bảng; chưa quyết định kích thước, vật liệu hay cách gia công |

## 1. Tham số cần đo và nơi đang dùng

### 1.1. Chín khóa của `configs/vehicle_default.json`

Tệp [vehicle_default.json](../configs/vehicle_default.json) được `VehicleConfig.from_dict`
([domain/types.py](../autopark/domain/types.py)) nạp. Trường `notes` của nó ghi: toàn bộ là giả định, giữ kích thước nhỏ
để tái hiện sa bàn hiện có, không phải số đo MN300. Mô hình trong mã là xe đạp động học, tư thế tại tâm trục sau, thân xe
là **một hình chữ nhật** tính từ trục sau (x hướng trước, y sang trái).

| Đại lượng | Khóa | Giá trị hiện tại | Đang dùng ở | Đo ở bảng | Trạng thái |
|---|---|---|---|---|---|
| Chiều dài cơ sở (trục trước – trục sau) | `wheelbase_m` | 0,19 m | mô hình xe `θ̇ = v·tan δ / L`, footprint, bán kính quay | B1 | GIẢ ĐỊNH – CHƯA ĐO |
| Bề rộng thân (phần rộng nhất, kể cả bánh nếu bánh nhô ra) | `width_m` | 0,14 m | footprint chữ nhật: kiểm va chạm, planner, mặt nạ thân xe của lớp LiDAR | B1 | GIẢ ĐỊNH – CHƯA ĐO |
| Nhô trước (trục trước → điểm xa nhất phía trước) | `front_overhang_m` | 0,06 m | footprint | B1 | GIẢ ĐỊNH – CHƯA ĐO |
| Nhô sau (trục sau → điểm xa nhất phía sau) | `rear_overhang_m` | 0,06 m | footprint | B1 | GIẢ ĐỊNH – CHƯA ĐO |
| Góc lái tương đương lớn nhất | `max_steer_deg` | 30,0° | planner mặc định `plan_parking` → `portfolio.plan` (`USE_PORTFOLIO = True`) lập đường ở 0,85 / 0,90 / 0,97 × giá trị này tùy nấc và chặng (xem 1.2); bộ bám, xe mô phỏng; firmware `max_steer_mrad` = 524 | B2 | GIẢ ĐỊNH – CHƯA ĐO |
| Tốc độ lớn nhất cho phép (cả lùi) | `max_speed_mps` | 0,3 m/s | hồ sơ tốc độ quỹ đạo, bộ bám, xe mô phỏng; firmware `max_speed_mm_s` = 300 | B4, B6, B7 | GIẢ ĐỊNH – CHƯA ĐO; đây là **giới hạn vận hành chọn**, không phải tốc độ tối đa của xe |
| Gia tốc (tăng độ lớn tốc độ) | `max_accel_mps2` | 0,3 m/s² | hồ sơ tốc độ quỹ đạo, xe mô phỏng; firmware `max_accel_mm_s2` = 300 | B7 | GIẢ ĐỊNH – CHƯA ĐO |
| Giảm tốc (phanh) | `max_decel_mps2` | 0,6 m/s² | hồ sơ tốc độ; bộ bám giới hạn tốc độ theo `√(2·max_decel·quãng còn lại)`; xe mô phỏng; firmware `max_decel_mm_s2`, `stop_decel_mm_s2` = 600 | B6 | GIẢ ĐỊNH – CHƯA ĐO |
| Tốc độ đổi lái | `max_steer_rate_deg_s` | 90,0°/s | xe mô phỏng; firmware `max_steer_rate_mrad_s` = 1571 | B3 | GIẢ ĐỊNH – CHƯA ĐO |

Đại lượng suy ra (tính từ các giá trị giả định trên, không phải số đo):

| Đại lượng | Công thức | Giá trị với cấu hình giả định |
|---|---|---|
| Chiều dài thân | nhô sau + L + nhô trước | 0,31 m |
| Bán kính quay nhỏ nhất tại tâm trục sau | L / tan(δ_max) (`VehicleConfig.min_turn_radius`) | 0,329 m ở 30° |
| Bán kính tâm trục sau mà planner dùng | L / tan(k · δ_max), k = 0,85 / 0,90 / 0,97 | 0,398 / 0,373 / 0,341 m (25,5° / 27,0° / 29,1°); trường hợp xấu nhất 0,341 m |
| Bán kính góc trước phía ngoài, ở góc lái của planner | √((R + w/2)² + (L + nhô trước)²) | 0,531 / 0,509 / 0,481 m |

k là tỉ lệ góc lái của từng nấc/chặng planner (bảng 1.2, dòng "tỉ lệ góc lái và lề của planner"). Kiểm bằng mô phỏng ngày
24/09/2026 trên máy bàn: `plan_parking` (portfolio mặc định), 16 ca của `evaluation/hard_cases.py`, xe mặc định, 20 s mỗi
ca. 14 ca có đường. Góc lái lớn nhất trên đường là 0,85 × δ_max ở 8 ca, 0,90 × δ_max ở 4 ca, 0,97 × δ_max = 29,10° ở
`uturn_w55` (nấc `gộp-nhanh`). `reverse_long_corridor` chạy thẳng, góc 0. Hai ca không ra đường là `parallel_115`
(TIMEOUT) và `zigzag_corridor` (NO_PATH). Nấc/chặng nào giải được một ca còn phụ thuộc thời gian và tải CPU, nên con số
theo từng ca có thể đổi giữa các lần chạy. Mọi giá trị trong bảng này tính từ cấu hình giả định, không phải số đo.

### 1.2. Tham số khác phụ thuộc số đo MN300 (ngoài `vehicle_default.json`)

| Tham số | Nơi | Giá trị hiện tại | Phụ thuộc bảng | Ghi chú |
|---|---|---|---|---|
| `actuator.effort_deadzone_permille` | [vehicle_io_sim.json](../configs/vehicle_io_sim.json) | 150 ‰ | B5, B7 | vùng chết ESC của mô phỏng; GIẢ ĐỊNH |
| `actuator.speed_at_full_effort_mps` | vehicle_io_sim.json | 0,8 m/s | B7 | mô phỏng: `v = v_full·(e − e_dz)/(1000 − e_dz)` khi `e > e_dz` |
| `actuator.latency_ms` | vehicle_io_sim.json | 30 ms | (giai đoạn 5, cần encoder) | trễ cơ cấu chấp hành; GIẢ ĐỊNH |
| `actuator.steer_offset_deg` | vehicle_io_sim.json | 0,0° | B2 (lệch khi lái về giữa) | |
| `firmware.deadzone_comp_permille`, `firmware.ff_permille_per_mps` | vehicle_io_sim.json; `FirmwareConfig` trong [transport/firmware_model.py](../autopark/transport/firmware_model.py); `ap::Config` trong firmware C++ | 100 ‰; 2000 ‰/(m/s) | B7 | feedforward `effort = deadzone_comp + ff·\|v\|`; cố ý lệch với mô phỏng để vòng PI phải bù ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 10) |
| `direction_change_hold_ms` | `FirmwareConfig` | 300 ms | B5 | CHƯA CHỐT theo ESC thật |
| `boot_hold_ms` | `FirmwareConfig` | 1000 ms | phiếu kiểm kê C1.12 | thời gian giữ trung tính sau khởi động |
| `max_effort_permille` | `FirmwareConfig` (thật) / vehicle_io_sim.json (mô phỏng) | 250 ‰ / 1000 ‰ | B7 | [firmware README](../firmware/esp32_vehicle/README.md): chỉ nâng sau khi đo đường cong effort–tốc độ, có encoder và đã thấy STALL chốt đúng |
| `kEscNeutralUs`, `kEscSpanUs`, `kEscDirection` | [firmware/esp32_vehicle/src/main.cpp](../firmware/esp32_vehicle/src/main.cpp) | 1500 µs; 500 µs; +1 | B7, phiếu kiểm kê C2.5 | xung = 1500 + chiều · effort · 500 / 1000 µs; CHƯA CHỐT |
| `kServoCenterUs`, `kServoUsPerRad`, `kServoDirection`, `kServoMinUs`/`kServoMaxUs` | main.cpp | 1500 µs; 1000 µs/rad; +1; 1000/2000 µs | B2, B8 | chốt ở `steering_calibration.yaml` (giai đoạn 5) |
| `creep_speed` | `TrackerParams` ([control/tracker.py](../autopark/control/tracker.py)) và `build_trajectory` ([planning/trajectory.py](../autopark/planning/trajectory.py)) | 0,03 m/s | B4 | tốc độ bò tối thiểu gần cuối đoạn. Nếu tốc độ ổn định thấp nhất đo được lớn hơn 0,03 m/s thì xe thật không bám được pha này |
| `preset_steer` | `TrackerParams` | True | B3 | đánh lái khi đứng yên ở đầu đoạn; mã ghi "cần phần cứng cho phép đánh lái tại chỗ" |
| Tỉ lệ góc lái và lề của planner (`steer_ratio` / trần lề tìm kiếm) | planner mặc định `plan_parking` → `portfolio.plan` ([planning/parking.py](../autopark/planning/parking.py), `USE_PORTFOLIO = True`): `_STAGES` trong [planning/cand_lattice_macro.py](../autopark/planning/cand_lattice_macro.py) (nấc `gộp-nhanh`, `gộp-kỹ`); `RRTParams` trong [planning/cand_rrt_rs.py](../autopark/planning/cand_rrt_rs.py) (nấc `ngẫu nhiên`); `RefParams` của nấc `lưới mịn` trong `portfolio.default_ladder` | `_STAGES`: `tho` 0,85 / 0,030 m; `min` 0,90 / 0,030 m; `le-hep` 0,90 / 0,015 m; `le-hep-cuoi` 0,97 / 0,008 m. `RRTParams`: 0,85 / 0,03 m. `lưới mịn`: 0,90 / 0,012 m | B2, B1 | phần góc lái để dành cho bộ bám; nới thân xe khi tìm kiếm. Lề ở lưới gộp và RRT còn bị chặn ở nửa khoảng hở tại xuất phát/đích, nên có thể về 0. Ở `lưới mịn`, lề bị chặn ở 0,40 × khoảng hở đó, sàn 4 mm. `PlannerParams.steer_ratio` / `safety_margin` (0,85; 0,03 m, [planning/hybrid_astar.py](../autopark/planning/hybrid_astar.py)) chỉ có hiệu lực khi gọi thẳng `hybrid_astar` (`USE_PORTFOLIO = False`, ứng viên `goc` của `compare`, hoặc `bench --planner autopark.planning.hybrid_astar:plan`). `plan_parking` chỉ lấy `time_limit` từ `PlannerParams` (đọc mã 24/09/2026) |
| `path_margin` (hành lang quỹ đạo) và `mask_margin` (mặt nạ thân xe cho LiDAR) | [fusion/bridge.py](../autopark/fusion/bridge.py), [fusion/demo.py](../autopark/fusion/demo.py) | 0,10 m (mặc định của bridge); 0,10 m (demo truyền vào; mặc định của lớp LiDAR là 0,05 m) | B1 (và footprint sau khi lắp gá, giai đoạn 7) | nới quanh footprint trong cấu hình, nên footprint sai thì hai vùng này sai theo |

## 2. Điều kiện chung cho mọi phiên đo

### 2.1. An toàn và thứ tự

1. Kiểm kê và chụp ảnh theo [mn300_inventory.md](mn300_inventory.md) mục A–E **trước** khi chạy hay đổi dây.
2. Chạy bằng **điều khiển nguyên bản** trước khi can thiệp điện (kế hoạch mục 8 bước 1). Thử mới nào cũng kê cao bánh
   trước, rồi mới đặt xuống sàn.
3. Vùng thử kiểm soát, sàn phẳng cùng loại với sa bàn. Không dùng người đứng trong đường xe; vật cản thử là vật cản mềm
   (kế hoạch mục 13). Rào mềm ở hai đầu vùng thử là đề xuất của tài liệu này, kế hoạch không nêu (CHƯA CHỐT).
4. Không khóa cứng motor hay servo để đo dòng hoặc lực (kế hoạch mục 10 bước 4).
5. Mỗi phiên ghi điện áp pin trước và sau. Tốc độ và quãng dừng phụ thuộc điện áp pin, nên số đo ở hai mức pin khác
   nhau không so trực tiếp với nhau được.

### 2.2. Dụng cụ

| Dụng cụ | Dùng cho | Tình trạng (theo tài liệu dự án, 24/09/2026) |
|---|---|---|
| Thước thép / thước dây, thước kẹp | B1, B2, B6 | tài liệu chưa ghi |
| Thước đo góc, giấy kẻ ô hoặc băng dính đánh dấu trên sàn | B2 | tài liệu chưa ghi |
| Camera quay video có số khung/s biết trước (điện thoại hoặc một camera USB của dự án) | B3, B4, B6, B7 | camera USB của dự án đo được ≈ 23,85 khung/s với phơi sáng tự động, nhịp không đều ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md)); cần tính sai số theo nhịp khung thật |
| Đồng hồ vạn năng | điện áp pin, BEC | tài liệu chưa ghi |
| Máy hiện sóng hoặc logic analyzer | độ rộng xung ở ESC/servo (B7, B8, phiếu kiểm kê C2) | tài liệu chưa ghi ([TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md) mục 5.3) |
| Cân | khối lượng (phiếu kiểm kê E5) | tài liệu chưa ghi |

Chưa có máy hiện sóng hoặc logic analyzer thì phần định lượng của B7 và B8 phải chờ giai đoạn 5, khi ESP32-S3 phát effort
đã biết chính xác vào ESC sẽ dùng thật (nguyên bản hay thay: phiếu kiểm kê mục H). Trong giai đoạn 4 khi đó chỉ ghi quan
sát định tính.

## 3. Bảng đo

### B0. Thông tin mỗi phiên đo (điền cho từng phiên)

| Mục | Giá trị |
|---|---|
| Mã phiên (ví dụ `x01`), ngày, giờ bắt đầu/kết thúc | |
| Người đo, người giám sát | |
| Mặt sàn (loại, sạch/bụi), vùng thử (kích thước) | |
| Điện áp pin trước / sau phiên | CHƯA ĐO / CHƯA ĐO |
| Nhiệt độ phòng (nếu có) | |
| Cấu hình xe: nguyên bản / đã đổi gì | |
| Bộ phát: trim lái, trim ga, D/R lái, giới hạn ga/chế độ tốc độ, đảo kênh (vị trí; hoặc "như phiếu kiểm kê A2b, ảnh …") | |
| Tốc độ dùng khi chạy vòng ở B2 (từ B4) | |
| Dụng cụ dùng; số khung/s của video | |
| Tệp video, ảnh, ghi chép (tên tệp ASCII) | |

### B1. Hình học và footprint

Mục đích: `wheelbase_m`, `width_m`, `front_overhang_m`, `rear_overhang_m`. Đo khi xe đứng trên mặt phẳng, bánh thẳng. Mỗi
đại lượng đo ba lần, ghi cả ba. Chiều dài cơ sở đo từ tâm trục trước tới tâm trục sau ở **cả hai bên** xe, vì lệch trái/phải
cho biết khung có vặn không. Phần nhô tính tới **điểm xa nhất** của xe (cản, móc, đèn, phụ kiện), không tính tới mép vỏ.

| Đại lượng | Lần 1 | Lần 2 | Lần 3 | Dùng giá trị | Khóa cấu hình |
|---|---|---|---|---|---|
| Chiều dài cơ sở, bên trái | CHƯA ĐO | | | | `wheelbase_m` |
| Chiều dài cơ sở, bên phải | CHƯA ĐO | | | | `wheelbase_m` |
| Vệt bánh trước (tâm lốp – tâm lốp) | CHƯA ĐO | | | | (chưa có khóa; cần cho Ackermann, B2) |
| Vệt bánh sau | CHƯA ĐO | | | | (chưa có khóa) |
| Bề rộng qua mép ngoài bánh | CHƯA ĐO | | | | ứng viên cho `width_m` |
| Bề rộng thân/vỏ, phần rộng nhất | CHƯA ĐO | | | | ứng viên cho `width_m` |
| Trục trước → điểm xa nhất phía trước | CHƯA ĐO | | | | `front_overhang_m` |
| Trục sau → điểm xa nhất phía sau | CHƯA ĐO | | | | `rear_overhang_m` |
| Chiều dài tổng (kiểm chéo = nhô sau + L + nhô trước) | CHƯA ĐO | | | | kiểm chéo |
| Chiều cao (không gá) | CHƯA ĐO | | | | (cho gá, mục 6) |
| Đường kính bánh (4 bánh) | CHƯA ĐO | | | | (encoder, giai đoạn 5) |

Quy tắc chọn giá trị (đề xuất, CHƯA CHỐT): footprint lấy giá trị **lớn nhất** trong ba lần đo (thân xe là vùng cấm, lấy
lớn là phía an toàn). `width_m` lấy số lớn hơn giữa bề rộng qua bánh và bề rộng thân. Sau khi lắp gá cảm biến (giai đoạn 7)
phải đo lại footprint; kế hoạch mục 11 bước 3 yêu cầu footprint gồm cả phụ kiện.

### B2. Góc lái thật và bán kính quay

Mục đích: `max_steer_deg`, `actuator.steer_offset_deg`, và kiểm tra các tỉ lệ góc lái 0,85–0,97 của planner (nấc cuối
dùng 0,97; bảng 1.2).

Cách đo (đề xuất):
0. Đặt D/R lái ở mức lớn nhất và trim lái ở giữa (nếu bộ phát có); không đặt được thì ghi vị trí thật vào B0. Khi kê cao
   bánh, kiểm lái hết cỡ có chạm chặn cơ khí không. Nếu bánh dừng trước chặn thì góc đo là giới hạn của bộ phát/servo: ghi
   rõ.
1. Lái hết cỡ sang trái, chạy vòng tròn ở tốc độ ổn định thấp nhất đo ở B4 (B4 làm trước B2, xem mục 7) để trượt ít nhất,
   và ghi tốc độ đã dùng vào B0. Dán hai điểm đánh dấu ở tâm tiếp đất của hai bánh sau; đánh dấu vết của chúng trên sàn
   qua ít nhất một vòng đủ.
2. Đo đường kính vòng của bánh sau trong và bánh sau ngoài (qua tâm, hai hướng vuông góc nhau). Bán kính tâm trục sau
   `R_sau = (R_trong + R_ngoài) / 2`; góc lái tương đương `δ = atan(L / R_sau)`, với L từ B1.
3. Đánh dấu thêm vết của điểm xa nhất phía trước, phía ngoài vòng: đây là bán kính quét của thân xe, dùng để kiểm hình
   chữ nhật footprint có đủ bao không.
4. Lặp lại khi lái hết cỡ sang phải. Mỗi chiều làm ba lần.
5. Lệch lái khi về giữa: lái về giữa, chạy thẳng 2 m, đo độ lệch ngang ở cuối. Làm ba lần mỗi chiều chạy (tiến, lùi).
6. (Tùy chọn) Đo góc từng bánh trước khi đứng yên bằng ảnh chụp từ trên xuống, để biết cơ cấu lái có kiểu Ackermann không.

| Chiều | Lần | R bánh sau trong | R bánh sau ngoài | R_sau | δ = atan(L/R_sau) | R điểm xa nhất phía trước |
|---|---:|---|---|---|---|---|
| Trái | 1 | CHƯA ĐO | | | | |
| Trái | 2 | | | | | |
| Trái | 3 | | | | | |
| Phải | 1 | CHƯA ĐO | | | | |
| Phải | 2 | | | | | |
| Phải | 3 | | | | | |

| Chạy thẳng 2 m, lái về giữa | Lần 1 | Lần 2 | Lần 3 |
|---|---|---|---|
| Tiến: lệch ngang (+ = sang trái) | CHƯA ĐO | | |
| Lùi: lệch ngang | CHƯA ĐO | | |

Quy tắc chọn (đề xuất, CHƯA CHỐT): `VehicleConfig` chỉ có một `max_steer` đối xứng, nên lấy **góc nhỏ hơn** của hai chiều
(xe không quay gắt hơn được chiều yếu). Chênh lệch trái/phải và lệch khi về giữa ghi vào `steer_offset_deg` của mô phỏng và
chuyển sang `steering_calibration.yaml` ở giai đoạn 5. Lệch khi về giữa đo lúc trim lái không ở giữa là lệch của trim cộng
lệch cơ khí. Ghi vị trí trim (và xung trung tính nếu đo được, B8 / phiếu kiểm kê C2.5). Chỉ phần cơ khí mới chuyển sang
`steer_offset_deg`/`steering_calibration.yaml`, vì ở giai đoạn 5 ESP32 phát xung trực tiếp nên trim của bộ phát không còn
tác dụng.

Nếu góc đo được nhỏ hơn nhiều so với 30°, hoặc bộ bám không còn dư địa, xem lại:
- `steer_ratio` trong `_STAGES` của `planning/cand_lattice_macro.py`. Chặng `le-hep-cuoi` dùng 0,97, gần sát góc tối đa;
- `RRTParams.steer_ratio` trong `planning/cand_rrt_rs.py`;
- `RefParams` của nấc `lưới mịn` trong `portfolio.default_ladder`.

`PlannerParams.steer_ratio` không có hiệu lực trên đường mặc định (bảng 1.2). Các tỉ lệ này để dành phần góc cho bộ bám,
chưa được chọn theo độ rơ lái thật. Trước khi chạy bất kỳ đường nào trên xe thật, cần biết rằng đường lập ở 0,97 · δ_max
chỉ còn 3 % góc lái cho bộ bám. Mã ghi lý do chặn các chặng khác ở 0,90: gần góc tối đa thì phản hồi hướng của bộ bám
bão hòa (đo trong mô phỏng: `uturn_w46` lệch 8,7° ở tỉ lệ 0,95).

### B3. Tốc độ đổi lái và đánh lái khi đứng yên

Mục đích: `max_steer_rate_deg_s`; kiểm điều kiện `preset_steer` của bộ bám.

1. Kê cao bánh, quay video từ trên xuống: lái từ hết trái sang hết phải và ngược lại, mỗi chiều ba lần. Tốc độ đổi lái =
   (góc hết trái + góc hết phải, từ B2) / thời gian theo số khung video.
2. Đặt xe trên sàn, đứng yên: lái hết cỡ hai bên. Ghi bánh có quay tới hết cỡ không, có giật không, servo có kêu gằn không.

| Phép đo | Lần 1 | Lần 2 | Lần 3 | Ghi chú |
|---|---|---|---|---|
| Hết trái → hết phải, kê cao (s) | CHƯA ĐO | | | số khung/s của video: |
| Hết phải → hết trái, kê cao (s) | CHƯA ĐO | | | |
| Đứng yên trên sàn: bánh tới hết cỡ trái? | CHƯA THỬ | | | |
| Đứng yên trên sàn: bánh tới hết cỡ phải? | CHƯA THỬ | | | |

Nếu servo không đánh được lái khi đứng yên trên sàn thì `preset_steer = True` của bộ bám không dùng được trên xe thật;
khi đó bộ bám và planner phải được xem lại (ghi vào mục 7).

### B4. Hành vi tốc độ thấp: vùng ga không phản ứng, tốc độ ổn định thấp nhất

Mục đích: vùng chết (`effort_deadzone_permille` của mô phỏng, `deadzone_comp_permille` của firmware); tốc độ ổn định thấp
nhất so với `creep_speed` = 0,03 m/s; miền tốc độ 0,05–0,15 m/s của kế hoạch mục 16.1.

Đại lượng lệnh: với điều khiển nguyên bản, vị trí cần ga không lặp lại được chính xác. Nếu có máy hiện sóng/logic analyzer,
ghi **độ rộng xung ở dây tín hiệu ga** (đo song song, không cắt dây). Nếu không có, ghi định tính và để phần định lượng cho
giai đoạn 5 (ESP32 phát effort ‰ đã biết).

Chỉ đo song song xung ga được khi phiếu kiểm kê C1.2/C2.3 cho thấy có dây tín hiệu ga tách rời giữa bộ thu và ESC. Nếu bộ
thu và ESC gộp một khối thì không có dây để đo: ghi định tính. Khi đó phần định lượng đo ở giai đoạn 5, trên đúng ESC sẽ
được ESP32 điều khiển (ESC nguyên bản nếu nó nhận xung, hoặc ESC thay thế).

Ghi trim ga và giới hạn ga/chế độ tốc độ lúc đo vào B0.

1. Kê cao bánh: tăng ga thật chậm từ trung tính; ghi độ rộng xung lúc bánh bắt đầu quay và lúc bánh dừng khi giảm ga. Hai
   số này thường khác nhau (khởi động và duy trì), nên ghi cả hai. Làm cho cả tiến và lùi.
2. Trên sàn, đoạn đo 1 m đánh dấu bằng băng dính, có 0,5 m chạy đà trước đoạn đo: tìm mức ga nhỏ nhất giữ xe chạy liên
   tục hết 1 m không khựng. Tốc độ = 1 m / thời gian theo số khung video.
3. Ở mỗi tốc độ 0,05 / 0,10 / 0,15 m/s (hoặc gần nhất đạt được), cả tiến và lùi: đo tốc độ trên đoạn 1 m như bước 2 (theo
   số khung video) và ghi xe có chạy đều hết 1 m không (khựng/giật ở đâu). Tốc độ đo được ở đây là "gần nhất đạt được ở
   B4" mà B6 dùng.

| Phép đo | Chiều | Lần 1 | Lần 2 | Lần 3 | Đơn vị |
|---|---|---|---|---|---|
| Xung lúc bánh bắt đầu quay (kê cao) | tiến | CHƯA ĐO | | | µs |
| Xung lúc bánh dừng khi giảm ga (kê cao) | tiến | CHƯA ĐO | | | µs |
| Xung lúc bánh bắt đầu quay (kê cao) | lùi | CHƯA ĐO | | | µs |
| Xung lúc bánh dừng khi giảm ga (kê cao) | lùi | CHƯA ĐO | | | µs |
| Tốc độ ổn định thấp nhất trên sàn | tiến | CHƯA ĐO | | | m/s |
| Tốc độ ổn định thấp nhất trên sàn | lùi | CHƯA ĐO | | | m/s |
| Xung tương ứng (nếu đo được) | tiến / lùi | CHƯA ĐO | | | µs |
| Nhắm 0,05 m/s: tốc độ đo trên 1 m | tiến | CHƯA ĐO | | | m/s |
| Nhắm 0,05 m/s: chạy đều hết 1 m (có/không; ghi khựng/giật) | tiến | CHƯA THỬ | | | có/không |
| Nhắm 0,10 m/s: tốc độ đo trên 1 m | tiến | CHƯA ĐO | | | m/s |
| Nhắm 0,10 m/s: chạy đều hết 1 m (có/không; ghi khựng/giật) | tiến | CHƯA THỬ | | | có/không |
| Nhắm 0,15 m/s: tốc độ đo trên 1 m | tiến | CHƯA ĐO | | | m/s |
| Nhắm 0,15 m/s: chạy đều hết 1 m (có/không; ghi khựng/giật) | tiến | CHƯA THỬ | | | có/không |
| Nhắm 0,05 m/s: tốc độ đo trên 1 m | lùi | CHƯA ĐO | | | m/s |
| Nhắm 0,05 m/s: chạy đều hết 1 m (có/không; ghi khựng/giật) | lùi | CHƯA THỬ | | | có/không |
| Nhắm 0,10 m/s: tốc độ đo trên 1 m | lùi | CHƯA ĐO | | | m/s |
| Nhắm 0,10 m/s: chạy đều hết 1 m (có/không; ghi khựng/giật) | lùi | CHƯA THỬ | | | có/không |
| Nhắm 0,15 m/s: tốc độ đo trên 1 m | lùi | CHƯA ĐO | | | m/s |
| Nhắm 0,15 m/s: chạy đều hết 1 m (có/không; ghi khựng/giật) | lùi | CHƯA THỬ | | | có/không |

### B5. Đổi chiều và dừng / thả trôi

Mục đích: `direction_change_hold_ms` (khóa đổi chiều của firmware: về 0, đứng ở 0 ít nhất 300 ms, rồi mới sang chiều
mới; [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 7). Kế hoạch mục 9 bước 6 nhắc: "không mặc định một lệnh ga âm luôn khiến
xe lùi ngay". Nhiều ESC RC có trình tự phanh → trung tính → lùi, nhưng ESC của chiếc xe này làm gì thì **CHƯA BIẾT**.

Làm khi xe kê cao bánh trước, rồi trên sàn ở tốc độ thấp:

| # | Thao tác | Quan sát (ghi đúng điều thấy) | Lần |
|---:|---|---|---|
| D1 | Tiến → nhả về trung tính → bánh tự dừng hay quay tiếp (thả trôi) | CHƯA THỬ | |
| D2 | Tiến → đẩy thẳng sang lùi (không dừng ở trung tính) | CHƯA THỬ: phanh? lùi ngay? không gì? | |
| D3 | Sau D2, về trung tính rồi lùi lần nữa | CHƯA THỬ | |
| D4 | Đứng yên → lùi ngay | CHƯA THỬ | |
| D5 | Lùi → sang tiến | CHƯA THỬ | |
| D6 | Thời gian phải đứng ở trung tính để lùi được (nếu có máy phát xung: thử 100 / 200 / 300 / 500 / 1000 ms) | CHƯA ĐO | |

Chưa có thiết bị phát xung đúng thời lượng (bộ thử servo, hoặc ESP32 ở giai đoạn 5) thì D6 để lại giai đoạn 5.

### B6. Quãng dừng

Mục đích: `max_decel_mps2`, `stop_decel_mm_s2` của firmware; bộ bám dùng `√(2·max_decel·quãng còn lại)` để giảm tốc
trước cuối đoạn nên cần giảm tốc thật. Kế hoạch mục 16.2 ("Điều khiển", "Phản ứng lỗi") đòi quãng dừng đo trên xe.

1. Đoạn chạy đà ≥ 1 m rồi mốc "lệnh dừng" đánh dấu trên sàn; quay video ngang từ bên hông, có thước dọc sàn trong khung.
2. Ở mỗi tốc độ 0,05 / 0,10 / 0,15 m/s (hoặc gần nhất đạt được ở B4), khi mũi xe qua mốc: (a) nhả ga về trung tính; (b)
   phanh hoặc lùi nếu ESC có phanh (theo B5).
3. Từ video, tìm khung đầu tiên xe bắt đầu chậm lại, gọi là **mốc giảm tốc** (khác với **mốc lệnh**, là mốc dán trên sàn
   ở bước 1). Mỗi lần chạy ghi:
   - `v0`: tốc độ trung bình trên ≥ 5 khung ngay trước mốc giảm tốc, tính từ vị trí so với thước chia cho khoảng cách thời
     gian **thật** giữa các khung (không dùng số khung/s danh định);
   - `d_px`: quãng từ mốc lệnh tới mốc giảm tốc (phản xạ của người cộng trễ ESC);
   - `d_hãm`, `t_hãm`: quãng và thời gian từ mốc giảm tốc tới lúc xe đứng hẳn;
   - `d_tổng = d_px + d_hãm`, vẫn cần để kiểm khoảng hở theo kế hoạch mục 16.2.

   Mỗi ô năm lần, cả tiến lẫn lùi. Ghi một dòng cho mỗi lần chạy, hoặc ghi năm số trong một ô, cách nhau bằng dấu chấm phẩy.

Với điều khiển nguyên bản, "lúc có lệnh" là lúc người nhả cần ga, nên có sai số phản xạ; vì vậy tách `d_px` khỏi `d_hãm`.
Số chính xác hơn phải chờ giai đoạn 5, khi laptop ghi thời điểm lệnh và ESP32 bật một đèn LED thấy được trong video (CHƯA
LÀM).

| Tốc độ nhắm | Chiều | Cách dừng | v0 thực, 5 lần (m/s, từ video) | d_px (cm) | d_hãm (cm) | t_hãm (s) | d_tổng (cm) | a = v0²/(2·d_hãm) (m/s²) | Số khung/s thật | Pin trước/sau (V) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0,05 m/s | tiến | thả trôi | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO |
| 0,05 m/s | tiến | phanh (nếu có) | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | | |
| 0,10 m/s | tiến | thả trôi | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | | |
| 0,10 m/s | tiến | phanh (nếu có) | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | | |
| 0,15 m/s | tiến | thả trôi | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | | |
| 0,15 m/s | tiến | phanh (nếu có) | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | | |
| 0,05 m/s | lùi | thả trôi | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | | |
| 0,05 m/s | lùi | phanh (nếu có) | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | | |
| 0,10 m/s | lùi | thả trôi | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | | |
| 0,10 m/s | lùi | phanh (nếu có) | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | | |
| 0,15 m/s | lùi | thả trôi | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | | |
| 0,15 m/s | lùi | phanh (nếu có) | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | | |

Cách suy ra giảm tốc (đề xuất, CHƯA CHỐT):
- Mỗi lần chạy: `a = v0² / (2·d_hãm)`, dùng `v0` **đo được** của chính lần đó, không dùng tốc độ nhắm. `a` tỉ lệ với bình
  phương `v0`, nên sai 20 % ở tốc độ thành sai khoảng 44 % ở `a`.
- Kiểm chéo với `v0 / t_hãm`. Nếu hai số lệch nhiều thì giảm tốc không đều: ghi lại điều đó, không ép lấy trung bình.
- Mỗi ô báo trung vị và khoảng min–max của năm lần.
- Giới hạn phân giải: với ≈ 23,85 khung/s (≈ 42 ms mỗi khung, camera USB của dự án), dừng từ 0,05 m/s ở 0,6 m/s² chỉ mất
  khoảng 2 khung và khoảng 0,2 cm (tính từ giá trị giả định), nên `a` từ dòng 0,05 m/s không tin được. Ưu tiên dòng
  0,15 m/s hoặc một camera có số khung/s cao hơn, và ghi sai số theo một khung.

Để so sánh (không phải số đo): riêng dốc mục tiêu của firmware (`stop_decel` = 600 mm/s²) đưa mục tiêu từ 0,15 m/s về 0
trong 0,25 s, ứng với 1,9 cm nếu xe bám đúng mục tiêu. Xe mô phỏng trong [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 10 trôi
3,9 cm từ 0,15 m/s; đó là số của mô hình. Quãng dừng thật cộng thêm trễ ESC, quán tính và trượt, **CHƯA ĐO**.

### B7. Đường cong lệnh – chuyển động ban đầu

Mục đích: `ff_permille_per_mps`, `deadzone_comp_permille` (firmware); `effort_deadzone_permille`,
`speed_at_full_effort_mps` (mô phỏng); `max_accel_mps2`. [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 10 kết luận từ mô phỏng:
feedforward phải lấy từ đường cong đo ở giai đoạn 4, và `max_accel` của firmware nên thấp hơn gia tốc xe làm được.

Ánh xạ effort → xung hiện có trong `main.cpp` (CHƯA CHỐT): xung ESC = 1500 + chiều · effort(‰) · 500 / 1000 µs. Trần
effort mặc định của firmware thật là 250 ‰ (1500 ± 125 µs). Với hệ số giả định (`deadzone_comp` 100 ‰, `ff` 2000 ‰/(m/s)),
feedforward cho 0,15 m/s là 400 ‰, vượt trần 250 ‰; vì vậy phải có đường cong đo trước khi chọn trần và hệ số.

Cách đo: trên sàn, mỗi mức lệnh giữ đủ lâu để tốc độ ổn định; đo tốc độ trên đoạn 1 m như B4. Gia tốc lấy từ video lúc
khởi hành (vị trí theo từng khung). Mỗi mức ba lần, cả tiến và lùi. Mức lệnh là độ rộng xung (µs) nếu đo được xung, hoặc
effort (‰) khi ESP32 phát ở giai đoạn 5. Ghi trim ga và giới hạn ga/chế độ tốc độ lúc đo vào B0.

Đường cong chỉ đúng cho ESC đã đo. Nếu sau phiếu kiểm kê mục H phải thay ESC thì đo lại B4, B5 (kể cả D6) và B7 trên ESC
mới; không chuyển số đo của ESC nguyên bản sang.

| Mức lệnh (µs hoặc ‰) | Tốc độ ổn định tiến, 3 lần (m/s) | Tốc độ ổn định lùi, 3 lần (m/s) | Gia tốc khởi hành (m/s²) | Pin (V) |
|---|---|---|---|---|
| | CHƯA ĐO | CHƯA ĐO | CHƯA ĐO | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |

Khớp số (đề xuất): với các điểm có `e > e_dz`, khớp đường thẳng `v = k·(e − e_dz)`. Khi đó `deadzone_comp ≈ e_dz`,
`ff ≈ 1/k` (‰ cho mỗi m/s), và trong mô phỏng `effort_deadzone_permille = e_dz`, `speed_at_full_effort_mps = k·(1000 −
e_dz)`. Ghi cả phần dư của phép khớp. Nếu đường cong không thẳng trong miền 0,05–0,15 m/s thì mô hình tuyến tính của mô
phỏng không đủ; ghi lại, không ép khớp.

### B8. Ánh xạ xung servo → góc lái (sơ bộ)

Chỉ làm được khi đo được xung (máy hiện sóng/logic analyzer ở dây servo) hoặc khi ESP32 phát xung ở giai đoạn 5. Kết quả
chính thức thuộc `steering_calibration.yaml` của giai đoạn 5; ở đây chỉ ghi để biết `kServoCenterUs`, `kServoUsPerRad`,
`kServoDirection`, `kServoMinUs`/`kServoMaxUs` trong `main.cpp` có cùng cỡ không.

| Vị trí cần lái | Độ rộng xung (µs) | Góc bánh trong / ngoài (°) | Góc tương đương từ B2 (°) |
|---|---|---|---|
| Hết trái | CHƯA ĐO | | |
| Giữa | CHƯA ĐO | | |
| Hết phải | CHƯA ĐO | | |

## 4. Đưa số đo vào cấu hình và mô phỏng

### 4.1. Tệp nào

Kế hoạch mục 8 đặt tên đầu ra là `vehicle_measured.yaml`. Mã hiện tại chỉ đọc cấu hình xe dạng JSON
(`storage/scenario_store.py::load_vehicle_config`), và `.venv` không có PyYAML (kiểm 24/09/2026:
`import yaml` → `ModuleNotFoundError`). Cách làm **CHƯA CHỐT**; đề xuất:

1. **`configs/vehicle_measured.json`**: cùng lược đồ với `vehicle_default.json` (chín khóa, `name`, `notes`) để mọi công
   cụ nạp được qua `VehicleConfig.from_dict`. Hàm này kiểm mọi kích thước > 0 và góc lái trong (0°, 89°), và bỏ qua
   khóa lạ.
2. **Biên bản nguồn từng tham số** (tên `vehicle_measured.yaml` theo kế hoạch, hoặc một tệp JSON đi kèm): mỗi tham số ghi
   giá trị, đơn vị, bảng đo (B1–B8), phiên đo, số lần lặp, độ tản, dụng cụ, ngày, và trạng thái `ĐO` hay `GIẢ ĐỊNH`.
   Tham số nào chưa đo thì giữ giá trị giả định, nhưng biên bản và trường `notes` phải liệt kê đúng những tham số đó.
3. **Không sửa đè `vehicle_default.json`.** Tệp này là cấu hình của bộ kiểm thử và chiến dịch giai đoạn 0; giữ nguyên để
   chạy lại được hồi quy (kế hoạch mục 17.4, dòng giai đoạn 0: giữ bộ test và replay mô phỏng làm kiểm thử hồi quy; xem
   thêm mục 4: giữ nguồn dữ liệu giả để tái hiện lỗi).

Muốn đọc YAML thì phải cài thêm thư viện hoặc viết bước chuyển sang JSON; người dùng quyết định.

### 4.2. Cách chọn giá trị

| Khóa | Lấy từ | Quy tắc (đề xuất, CHƯA CHỐT) |
|---|---|---|
| `wheelbase_m` | B1 | trung bình hai bên; ghi độ lệch trái/phải |
| `width_m`, `front_overhang_m`, `rear_overhang_m` | B1 | lớn nhất trong các lần đo |
| `max_steer_deg` | B2 | góc nhỏ hơn của hai chiều |
| `max_steer_rate_deg_s` | B3 | chiều chậm hơn |
| `max_speed_mps` | B4 (dòng "Nhắm 0,05/0,10/0,15 m/s"), B6, B7 | giới hạn vận hành chọn trong phần miền 0,05–0,15 m/s đã đo, hợp với quãng dừng và khoảng hở (kế hoạch mục 16.1) |
| `max_accel_mps2` | B7 | thấp hơn gia tốc xe làm được ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 10) |
| `max_decel_mps2` | B6 | lấy `a` của cách dừng mà firmware sẽ dùng (thả trôi hay phanh); chọn giá trị nhỏ nhất (hoặc phân vị thấp) trong các lần đo, tính từ `v0` đo được, không dùng tốc độ danh định; ghi riêng `d_px` để xét `TrackerParams.stop_distance` (0,01 m, giả định) và khoảng hở. `stop_decel_mm_s2` của firmware cũng lấy từ bảng này |

### 4.3. Chạy mô phỏng với cấu hình đo

Các công cụ nhận `--config` (chạy trong `D:/ap/autopark`):

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.bench   --config configs/vehicle_measured.json --json runs/bench_mn300.json
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.compare --config configs/vehicle_measured.json --all
.\.venv\Scripts\python.exe -X utf8 -m autopark.evaluation.render  --config configs/vehicle_measured.json --planner autopark.planning.portfolio:plan --out runs/render_mn300
```

- `render` không có `--planner` thì chỉ vẽ ca dựng lại theo cấu hình, không lập đường. `--planner` ở đây trùng mặc định
  của `bench` (`DEFAULT_PLANNER` trong `evaluation/bench.py`). `--time-limit` của cả `bench` lẫn `render` mặc định 20 s mỗi
  ca. Muốn so với cấu hình giả định thì chạy lại cùng lệnh với `--config configs/vehicle_default.json --out
  runs/render_default`.
- Giao diện và phiên mô phỏng nạp xe theo khóa `vehicle_config` của tệp kịch bản (đường dẫn tương đối so với tệp kịch
  bản). Cả bốn tệp trong `scenarios/` đang trỏ `../configs/vehicle_default.json`. Đề xuất: chép kịch bản thành bản mới
  trỏ `../configs/vehicle_measured.json`, không sửa bản cũ.
- `VehicleIO` mô phỏng: chép `configs/vehicle_io_sim.json` thành bản mới (không sửa bản cũ). Trong bản mới:
  1. đổi `vehicle_config` sang `vehicle_measured.json`;
  2. điền mục `actuator` từ B2 (`steer_offset_deg`), B4, B5, B7;
  3. **sửa cả mục `firmware`**. Mọi khóa có trong mục này ghi đè mặc định: `SimIOConfig.from_dict` gộp
     `{**SIM_FIRMWARE_DEFAULT.to_dict(), **firmware}` ([transport/vehicle_io.py](../autopark/transport/vehicle_io.py)), và
     `vehicle_io_sim.json` hiện ghi tường minh mọi khóa. Nếu chỉ đổi `FirmwareConfig`/`ap::Config` thì bản chép vẫn giữ
     giới hạn của xe giả định. Các khóa cần sửa:
     - `max_speed_mm_s`, `max_steer_mrad`, `max_steer_rate_mrad_s`, `max_accel_mm_s2`, `max_decel_mm_s2`: tính theo dòng
       "Quy đổi" ở cuối mục này, từ chính các giá trị trong `vehicle_measured.json`;
     - `stop_decel_mm_s2`: chọn ≤ `max_decel_mm_s2` theo B6 (CHƯA CHỐT);
     - `deadzone_comp_permille`, `ff_permille_per_mps`: theo phép khớp ở B7 (`deadzone_comp ≈ e_dz`, `ff ≈ 1/k`) và B4;
     - `direction_change_hold_ms`: theo B5 dòng D6. Chưa đo thì giữ 300 và ghi GIẢ ĐỊNH;
     - `max_effort_permille` = 1000 là số riêng của mô phỏng (firmware thật mặc định 250 ‰). Giữ nguyên, trừ khi muốn mô
       phỏng trần của xe thật; đổi thì ghi rõ.

     Cách khác: xóa các khóa đó khỏi mục `firmware` để mô phỏng lấy `SIM_FIRMWARE_DEFAULT`. Khi đó phải sửa
     `FirmwareConfig` trước, theo gạch đầu dòng "Firmware" dưới đây.
  4. Kiểm tay sau khi sửa. Không có chỗ nào tự đối chiếu giới hạn firmware với cấu hình xe (đọc mã 24/09/2026):
     `load_sim_io_config` nạp hai tệp độc lập, còn `VehicleIO` chỉ lưu giới hạn HELLO_ACK vào `hello.limits`, không so
     sánh. Lệch nhau (ví dụ xe 35° mà bo mô phỏng 524 mrad = 30°) sẽ không có cảnh báo, và vòng kín bám sai vì một lý do
     không có ở xe. Cách kiểm: `SimVehicleIO.from_files(<tệp mới>).connect().limits` (đơn vị m/s, rad) phải khớp
     `vehicle_measured.json` sau khi quy đổi đơn vị, sai khác không quá làm tròn (1 mm/s, 1 mrad).
- **Chỗ đang cố định `vehicle_default.json`** (kiểm bằng grep 24/09/2026): `evaluation/phase0.py`,
  `evaluation/robustness.py` (chiến dịch độ bền), `fusion/demo.py` (`default_vehicle`), `ui/lidar_app.py`
  (`DEFAULT_VEHICLE`). Muốn chạy chiến dịch độ bền với xe đo thì phải thêm tùy chọn cấu hình cho các công cụ này; tài liệu
  này không sửa mã.
- **Firmware:** giới hạn của bo (`max_speed_mm_s`, `max_steer_mrad`, `max_steer_rate_mrad_s`, `max_accel_mm_s2`,
  `max_decel_mm_s2`, `stop_decel_mm_s2`) là hằng số của firmware, laptop không gửi xuống. Bo báo chúng trong HELLO_ACK
  ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 3). Đổi mặc định thì phải đổi cùng lúc `FirmwareConfig` (Python) và `ap::Config`
  (C++; `tests/test_transport_firmware_source.py` kiểm hai bên bằng nhau), rồi chạy
  `python -X utf8 -m autopark.transport.vectors --check`. Vector mẫu dùng mặc định cho các trường mà `VECTOR_CONFIG` không
  đặt, nên có thể phải sinh lại vector. Đổi mặc định `FirmwareConfig` không tự đổi mô phỏng nếu tệp sim JSON còn ghi khóa
  đó (xem gạch đầu dòng `VehicleIO` mô phỏng ở trên).
- Quy đổi: `max_speed_mm_s = round(max_speed_mps × 1000)`; `max_steer_mrad = round(radian(max_steer_deg) × 1000)`;
  `max_steer_rate_mrad_s = round(radian(max_steer_rate_deg_s) × 1000)`; `max_accel_mm_s2 = round(max_accel_mps2 × 1000)`;
  `max_decel_mm_s2 = round(max_decel_mps2 × 1000)`; `stop_decel_mm_s2` chọn từ B6 (CHƯA CHỐT).

## 5. Độ nhạy của planner với kích thước giả định

### 5.1. Chiến dịch 20/09 đã làm gì, và vì sao chưa phải phép thử độ nhạy

Chiến dịch độ bền ([KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 3) có thay đổi kích thước xe: 0,7–1,4
lần ở các ca hình học/kín vòng, 0,85–1,15 lần bề rộng và chiều dài cơ sở ở 40 ca có planner. Đọc
[evaluation/robustness.py](../autopark/evaluation/robustness.py) (`planner_case`) thấy:

- Bốn nhóm ca planner, mỗi nhóm chạy 10 lần (`index % 4`). Sa bàn lấy từ `build_cases(cfg)` với xe đã đổi cỡ, nhưng chỉ
  một phần sa bàn phóng theo xe:
  - `parallel_160`: ô dài 1,60 × `cfg.length`, hai xe đỗ cùng cỡ với xe ta; làn đường cố định 0,52 m.
  - `perp_aisle_170`: lối đi 1,70 × `cfg.length`, ô rộng `cfg.width` + 0,09 m, sâu `cfg.length` + 0,09 m; chiều dài sa
    bàn cố định 1,90 m.
  - `reverse_long_corridor` (hành lang 1,70 × 0,40 m) và `lateral_shift` (1,30 × 0,44 m, dịch ngang 0,18 m): hình học
    **cố định hoàn toàn**. 20/40 lần chạy thuộc hai nhóm này, tức là đặt xe khác cỡ vào hành lang cố định. Ở hành lang
    0,40 m, bề rộng và chiều dài cơ sở bằng 0,854–1,107 lần xe mặc định (rộng 0,120–0,155 m). Ở hành lang 0,44 m, hệ số là
    0,929–1,095 lần (rộng 0,130–0,153 m). Cả 20 lần đều `OK` và `COMPLETED`, không vi phạm nào, theo
    [cases.jsonl](../runs/robustness_final_2026-09-20/cases.jsonl) (mô phỏng, đọc lại ngày 24/09/2026; thư mục `runs/`
    không có trong git).

  Vậy chiến dịch đã có một ít bằng chứng về "xe khác cỡ trong hành lang cố định", nhưng vẫn chưa phải phép thử độ nhạy, vì:
  - hệ số là một lần rút ngẫu nhiên cho mỗi ca;
  - trong hành lang cố định, xe lớn nhất chỉ khoảng 1,11 lần (dài khoảng 0,33 m, vì phần nhô không đổi);
  - không có bước tìm ngưỡng mà từ đó hết đỗ được;
  - hai nhóm còn lại phóng ô/lối đi theo xe.
- Ca planner chỉ đổi bề rộng và chiều dài cơ sở; không đổi phần nhô và góc lái tối đa.
- Bộ ca khó (`evaluation/hard_cases.py`) trộn kích thước tương đối (ô đỗ song song = 1,15–1,60 × chiều dài xe; lối đi ở
  ca đỗ vuông góc = 1,15–1,70 × chiều dài xe) với kích thước tuyệt đối (đường cạnh ô đỗ song song rộng 0,40–0,52 m; hành
  lang quay đầu rộng 0,46 / 0,55 / 0,70 m; ngõ cụt rộng 0,62 m). Nhãn `expected` (feasible /
  infeasible) được đặt cho xe mặc định. *(Cập nhật 25/09/2026: từ khuya 24/09 cả 16 ca mang nhãn `feasible`, mỗi ca có
  đường chứng kiểm độc lập; `infeasible` chỉ dùng khi có chứng minh hình học, hiện không ca nào — xem
  [KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 6. Đường chứng là cho xe mặc định; xe khác cần
  kiểm lại.)* Chạy `bench --config` với xe khác thì một phần hình học đổi theo, một phần không,
  nên nhãn cũ có thể không còn đúng. Một ca thất bại với xe đo cần xem lại hình học trước khi coi là lỗi planner.
- Hết giờ tìm đường (TIMEOUT) phụ thuộc tải CPU và không có nghĩa là vô nghiệm hình học
  ([KIEM_THU_DO_BEN_GIAI_DOAN_0.md](KIEM_THU_DO_BEN_GIAI_DOAN_0.md) mục 4).

### 5.2. Hình học quay vòng theo tham số (công thức, không phải số đo)

Tính với `L` = 0,19 m, `w` = 0,14 m, nhô trước 0,06 m (đều là giá trị giả định). Planner dùng k · δ_max, với k = 0,85 ở
chặng đầu tới 0,97 ở chặng cuối (bảng 1.2). Ba số trong mỗi ô là R tâm trục sau / R góc trước phía ngoài / bề rộng vành
quét (R góc trước ngoài − R mép trong, R mép trong = R − w/2). Cột k = 0,97 là trường hợp xấu nhất (quay gắt nhất).

| δ_max | R tâm trục sau (L/tan δ_max) | Planner k = 0,85 | Planner k = 0,90 | Planner k = 0,97 (xấu nhất) |
|---|---|---|---|---|
| 20° | 0,522 m | 0,621 / 0,735 / 0,184 m | 0,585 / 0,701 / 0,186 m | 0,540 / 0,659 / 0,189 m |
| 25° | 0,407 m | 0,489 / 0,612 / 0,193 m | 0,459 / 0,585 / 0,196 m | 0,422 / 0,552 / 0,200 m |
| 30° (giả định hiện tại) | 0,329 m | 0,398 / 0,531 / 0,203 m | 0,373 / 0,509 / 0,206 m | 0,341 / 0,481 / 0,210 m |
| 35° | 0,271 m | 0,332 / 0,474 / 0,211 m | 0,310 / 0,455 / 0,215 m | 0,282 / 0,432 / 0,220 m |

Nhân mọi kích thước dài với hệ số s (giữ 30°) thì mọi bán kính trên cũng nhân s. Ở k = 0,97, đường kính vòng góc trước
ngoài là 0,67 m (s = 0,7), 0,96 m (s = 1), 1,35 m (s = 1,4), 1,93 m (s = 2). Ở k = 0,85, các số tương ứng là 0,74 / 1,06 /
1,49 / 2,12 m. Mọi số ở mục này tính từ giá trị giả định, không phải số đo. Hệ quả cần kiểm khi có số đo: sa bàn 3 × 2 m và các kịch bản
trong `scenarios/` có kích thước tuyệt đối. Nếu MN300 lớn hơn nhiều so với 0,31 × 0,14 m giả định, hoặc quay kém hơn 30°,
một số bài quay đầu và đỗ trong các kịch bản đó có thể trở nên vô nghiệm. Khi đó là giới hạn hình học của sa bàn, không
phải lỗi planner.

### 5.3. Phép thử độ nhạy với sa bàn cố định (đề xuất; đã chạy hai lượt mô phỏng 24/09/2026, CHƯA chạy khi máy rảnh, CHƯA có số đo MN300)

1. Giữ **sa bàn cố định**: các kịch bản trong `scenarios/` và bộ ca khó dựng một lần từ xe mặc định.
2. Mỗi lần chỉ đổi **một** tham số của xe: `wheelbase_m`, `width_m`, phần nhô, `max_steer_deg`, mỗi tham số ở vài mức (ví
   dụ 0,8 / 1,0 / 1,2 / 1,5 lần; góc 20–35°).
3. Ghi trạng thái lập đường, thời gian, độ dài, số lần đổi chiều, khoảng hở nhỏ nhất, kết quả bám kín vòng. Chạy khi máy
   rảnh (TIMEOUT phụ thuộc tải CPU).
4. Kết quả: với mỗi kịch bản, ngưỡng kích thước/góc lái mà từ đó hết đỗ được. Khi có số đo MN300, đặt số đo lên các ngưỡng
   này để biết kịch bản nào còn dùng được.

`bench`/`compare` hiện dựng ca từ cùng cấu hình dùng để lập đường, nên bước 1 cần một tùy chọn mới (dựng ca từ một cấu hình,
lập đường với cấu hình khác) hoặc một script riêng. Chưa làm (tại thời điểm soạn; xem cập nhật tối 24/09/2026 ngay dưới).

*(Cập nhật tối 24/09/2026:)* đã làm bằng script riêng `evaluation/sensitivity.py`; cách dùng và kết quả ở
[DO_NHAY_KICH_THUOC_XE.md](DO_NHAY_KICH_THUOC_XE.md). **Chỉ mô phỏng**, quanh xe `vehicle_default.json` (GIẢ ĐỊNH – CHƯA
ĐO). Sa bàn gồm 16 ca khó và bốn kịch bản `scenarios/`, dựng một lần từ xe giả định. Mỗi tham số (chiều dài thân, bề
rộng, phần nhô, chiều dài cơ sở, góc lái) đổi ±5/10/20 %, cộng ba tổ hợp. Hai lượt chạy trên máy bàn, ngân sách 8 s
và 20 s mỗi ca, nhiều tiến trình song song trong khi các agent khác cũng chạy. Mười một sa bàn (gồm cả bốn kịch bản
`scenarios/`) giải được ở mọi biến thể. Mười cặp hỏng ở cả hai lượt, kể cả khi chạy lại với ngân sách dài hơn, đều là
xe dài hơn 10–20 % (`parallel_135`, `perp_aisle_115`, `pillar_at_slot_mouth`, `parallel_160`). `uturn_w46` nằm sát
biên ngay với xe giả định. Khác với bước 3 ở trên: hai lượt này **không** chạy khi máy rảnh (tải máy đổi được kết quả,
tài liệu kia, mục 4), nên mỗi ô "hết giờ" chỉ có nghĩa là không tìm được trong ngân sách ở tải máy lúc đó, không phải
vô nghiệm; CHƯA tách được phần nào do tải máy, phần nào do ngân sách (chưa có lượt chạy khi máy rảnh). Để biết cỡ: ở
lượt A, 141/181 ô hết giờ thuộc bốn sa bàn mà xe giả định không giải được ở cả năm lần chạy của tài liệu kia, mục 4
(`parallel_122`, `parallel_115`, `zigzag_corridor`, `pocket_exit_park`; đếm lại từ `ket_qua.json` lượt A, 24/09/2026).
Bước 4 mới làm được một phần: mức 5/10/20 % chỉ khoanh ngưỡng thô, và vẫn chờ số đo MN300 (lệnh `--plan-config`).

## 6. Gá điều chỉnh được (khái niệm, chưa quyết định gia công)

Nguyên tắc: gá tạm có rãnh hoặc lỗ dãy để dịch chỉnh; **không khoan, cắt hay đặt gia công chi tiết nào phụ thuộc kích thước
xe trước khi có B1 và phiếu kiểm kê mục E** (kế hoạch mục 8: "chưa đặt gia công phần phụ thuộc kích thước chưa biết"). Mỗi
vị trí cố định xong phải đo lại và ghi thành phiên bản mới của ngoại tham, không sửa số cũ như thể đã đo lại (kế hoạch mục
11). Gốc tọa độ đo mọi vị trí: tâm trục sau, x hướng trước, y sang trái, z lên.

| Cụm | Cần chỉnh được | Ràng buộc đã biết (nguồn) | Phụ thuộc số đo | Trạng thái |
|---|---|---|---|---|
| Tấm đế | dịch dọc trước/sau; chiều cao so với khung | bắt vào điểm có sẵn trên khung/cột vỏ; không cản cơ cấu lái, hệ treo, bánh (kế hoạch mục 11 bước 1) | B1; phiếu kiểm kê E1–E4 | CHƯA CHỐT |
| RPLIDAR C1 | chiều cao cột; xoay quanh trục đứng (hướng "trước") | mặt phẳng quét phải cao hơn vỏ, camera và các cột khác, nếu không chúng hiện thành tia gần; datasheet: vùng mù 0,05 m (lớp LiDAR bỏ tia dưới 0,05 m); lớp LiDAR bỏ tia trong thân xe nới 10 cm ([GIAI_DOAN_3_CHUAN_BI.md](GIAI_DOAN_3_CHUAN_BI.md) mục 2, quy tắc 2); hướng "trước" của C1 theo trục x hình 2-4 datasheet; dấu góc trái/phải chưa xác minh bằng vật thật ([GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6b) | chiều cao xe (B1), vị trí camera | CHƯA CHỐT; sau khi lắp phải ghi các cung góc bị che |
| 4 camera USB | chiều cao; góc chúc; xoay ngang | góc nhìn 130° là số nhà bán, **chưa đo**; danh tính camera là cổng hub, nên dán nhãn cổng lên từng gá ([usb_topology.md](usb_topology.md)); ngoại tham `camera_rig_extrinsics.yaml` chưa có công cụ ([HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md)) | kích thước thân (B1): camera phải thấy sàn sát xe | CHƯA CHỐT |
| VL53L1X (2, có thể 4) | vị trí trước/sau/góc; hướng | mã giả định góc nhìn 25° (`NearFieldMount.fov_deg`, [fusion/layers.py](../autopark/fusion/layers.py)), là số trong mã, chưa đo; mỗi cảm biến cần vị trí `x, y, yaw` trong cấu hình (chưa có tệp, [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12) | footprint (B1) | CHƯA CHỐT; chưa nhận cảm biến |
| ESP32-S3 + BNO085 | vị trí hộp mạch | IMU gắn cứng, trục ghi rõ so với trục xe; dây USB về laptop có giảm kéo | — | CHƯA CHỐT; chưa nhận |
| AS5600 + nam châm | chỗ gắn ở cơ cấu lái | "góc đo ở trục cảm biến chưa tự đồng nghĩa góc bánh" (kế hoạch mục 1.1) | phiếu kiểm kê C4.6; B2, B8 | CHƯA CHỐT |
| Encoder (MT6701 hoặc loại khác) | chỗ gắn: trục motor, trục truyền hay bánh | cần tỉ số truyền và đường kính bánh để quy đổi | phiếu kiểm kê C4.3, C4.5, C4.7 | CHƯA CHỐT |
| Nút E-stop LA38 | vị trí trên xe | người giám sát bấm được từ trên; không nằm trong mặt phẳng quét LiDAR; đường cắt động lực ở [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) | — | CHƯA CHỐT |
| Dây USB, hub | đường đi dây, điểm giảm kéo | không quấn bánh khi tiến, lùi và rẽ (kế hoạch mục 11 bước 2); hub đặt trên xe hay ngoài xe phụ thuộc laptop đặt ở đâu (CHƯA CHỐT) | — | CHƯA CHỐT |

## 7. Khi nhận xe: thứ tự làm

1. Phiếu kiểm kê mục 0, A–E: chụp ảnh, đo điện áp pin lúc nhận, ghi đầu nối ([mn300_inventory.md](mn300_inventory.md)).
2. Chạy thử bằng điều khiển nguyên bản (phiếu kiểm kê mục F), kê cao bánh trước.
3. Đo B1 → B4 → B2 → B3 → B5 → B6 → B7 → B8, mỗi phiên điền B0. B4 làm trước B2 vì B2 chạy vòng ở tốc độ ổn định thấp
   nhất đo ở B4 (bước 2 của B4 chỉ cần đoạn 1 m và video); B3 cần góc từ B2; B6 cần B4, B5; B8 cần B2.
4. Lập `vehicle_measured.json` và biên bản nguồn theo mục 4; chạy `bench`/`compare`/`render` với cấu hình mới; ghi kết quả
   cạnh kết quả với cấu hình giả định, nói rõ ca nào đổi hình học (mục 5.1).
5. Kết luận phiếu kiểm kê mục H: ESC/servo can thiệp được thế nào, hoặc danh sách thông tin còn thiếu (điều kiện chuyển
   bước của kế hoạch mục 8).
6. Chọn chỗ gắn encoder/AS5600 và gá theo mục 6; chỉ đặt linh kiện khi có đủ cơ sở.

## 8. Còn mở

| Việc | Ai quyết | Ghi chú |
|---|---|---|
| Định dạng `vehicle_measured` (YAML theo kế hoạch hay JSON theo mã) | người dùng | mục 4.1 |
| Có dụng cụ đo xung (máy hiện sóng/logic analyzer), đồng hồ vạn năng, bộ thử servo không | người dùng | quyết định B4, B5 (D6), B7, B8 làm ở giai đoạn 4 hay 5 |
| Thêm tùy chọn cấu hình xe cho `robustness.py`, `phase0.py`, `fusion/demo.py`, `ui/lidar_app.py` | việc phần mềm | mục 4.3. *(Tối 24/09/2026:)* đã thêm `--vehicle-config` cho `robustness`, `phase0` và `ui/lidar_app`. Không có tùy chọn thì vẫn dùng `vehicle_default.json`; tệp hỏng thì thoát mã 2 kèm lý do. Chỉ kiểm bằng test (`tests/test_vehicle_sensitivity.py`); `lidar_app` với LiDAR thật CHƯA THỬ. Lưu ý: `robustness` chỉ lấy tỉ lệ footprint từ tệp, góc lái/tốc độ/gia tốc vẫn rút từ khoảng cố định, nên KHÔNG thử giới hạn lái/tốc độ đo được (chi tiết: DO_NHAY_KICH_THUOC_XE.md mục 3). `fusion/demo.py` CHƯA có tùy chọn này. Lệnh: [DO_NHAY_KICH_THUOC_XE.md](DO_NHAY_KICH_THUOC_XE.md) mục 3 |
| Công cụ thử độ nhạy với sa bàn cố định | việc phần mềm | mục 5.3. *(Tối 24/09/2026:)* đã có `evaluation/sensitivity.py`; hai lượt mô phỏng đầu tiên ở [DO_NHAY_KICH_THUOC_XE.md](DO_NHAY_KICH_THUOC_XE.md). Còn mở: chạy lại khi máy rảnh (`--workers 1`), chạy với số đo MN300 khi có |
| Nếu servo không đánh lái được khi đứng yên: xem lại `preset_steer` của bộ bám | sau B3 | mục 3, B3 |
| Nếu tốc độ ổn định thấp nhất > 0,03 m/s: xem lại `creep_speed` | sau B4 | mục 1.2 |
| Bộ phát có D/R, EPA, giới hạn ga không | sau phiếu kiểm kê A2b | quyết định điều kiện đo B2/B4/B7 |
| Bộ thu/ESC gộp thì có thay ESC không | người dùng, sau phiếu kiểm kê mục H và chạy thử | quyết định B4/B5/B7 đo trên ESC nào; nhánh động lực ở [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) N7 |
| Tỉ lệ góc lái 0,97 ở chặng cuối của planner có giữ khi chạy xe thật không | người dùng, sau B2 và giai đoạn 5 | mục 1.2, B2 |
