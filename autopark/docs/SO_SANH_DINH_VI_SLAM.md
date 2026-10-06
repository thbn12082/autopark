# So sánh phương án định vị / SLAM LiDAR cho V1 (24/09/2026, sửa đêm 24/09/2026)

**Kế hoạch đối chiếu:** [v3.1 bản `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md)
*(cập nhật 30/09/2026: tên đoạn, số bước và câu trích dưới đây theo bản trước đợt biên tập 26/09/2026;
[bản hiện tại](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) giữ số mục, mục 5 có đoạn "Khi chờ đồ" và "Có đồ")* mục 1.2
(V1: *"LiDAR cung cấp bản đồ/định vị"*); mục 5 "Khi đang chờ đồ" (*"Kiểm tra đầu vào bắt buộc của phương án SLAM dự
kiến. Chưa có odometry thì không tự coi chuỗi scan là đủ cho mọi thư viện hoặc gán odometry bằng 0 để báo đã có định
vị."*); mục 5 "Khi nhận LiDAR" bước 4–6; mục 12 (giai đoạn 8: hợp nhất vị trí toàn cục với odometry/IMU); bảng
16.2 dòng "Định vị"; điều kiện V1 đầu tiên ở 16.4; mục 17.2 ("đầu vào thư viện SLAM"). Việc này đang để ngỏ ở [TONG_HOP_DU_AN.md](../../TONG_HOP_DU_AN.md) mục 5.1 (phương án
định vị cho V1 cần người dùng quyết định) và 4.3 (công cụ định vị chạy offline; phương án cho V1 là đề xuất chờ chốt).
*(Cập nhật 30/09/2026: ý "chọn phương án SLAM/định vị 2D, kiểm đầu vào của nó" là mục 5.4 của
[bản `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/TONG_HOP_DU_AN.md).)*
*(Cập nhật 02/10/2026: việc này không còn để ngỏ: người dùng giao quyết định 02/10/2026 ('làm hết'), theo đề xuất mục 7;
xem mục 0, 7, 10 và [NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md).)*

**Mức bằng chứng.** Mọi thứ trong tài liệu này chạy **offline trên máy bàn i9-14900, tối và đêm 24/09/2026**. Không mở
LiDAR, camera hay cổng COM nào. Dữ liệu dùng:
1. phòng và hành lang tổng hợp trong test (quỹ đạo biết trước);
2. DROW v2: SICK S300 225°, robot khác, trong viện dưỡng lão có nhiều người. Odometry `.odom2` đi kèm **không phải ground
   truth**, nên mọi số so với nó là *chênh lệch giữa hai ước lượng*, không phải sai số;
3. sáu bản ghi C1 có sẵn (22/09 và 24/09). **Trong cả sáu bản ghi, cảm biến đều đứng yên.**

Chưa có bản ghi C1 nào khi cảm biến di chuyển. Chưa có vị trí đo bằng thước (tham chiếu độc lập). Chưa chạy trên laptop
RTX 3050 Ti (máy nộp đồ án). Số thời gian ở đây đo khi máy bàn đang chạy song song nhiều tiến trình thí nghiệm, kiểm đột
biến và các agent khác, nên chỉ dùng để so tương đối.

**Sửa đêm 24/09/2026.** Agent kiểm tra tìm ra lỗi trong bản đầu của (b); đã sửa, chạy lại mọi thí nghiệm, và sửa các số,
kết luận sai ở bản trước của tài liệu này. Quan trọng nhất: phần lớn FAILED/`lost` của (b) trên DROW là do **khóa trục
cứng** khi phép kiểm suy biến báo nhầm (mục 3.3 phát hiện 5, mục 3.4 kiểu hỏng 1), **không phải** do thiếu odometry bánh
xe như bản trước kết luận. Số của bản đầu vẫn giữ trong tệp bằng chứng riêng để so.

**Tài liệu này không chốt gì.** Mục 7 là **ĐỀ XUẤT – CHỜ CHỐT**; người dùng quyết định. *(Cập nhật 02/10/2026:
người dùng giao quyết định 02/10/2026 ('làm hết'), theo đề xuất mục 7; các ngưỡng vẫn ĐỀ XUẤT – CHỜ CHỐT.)*

## 0. Tóm tắt

| Phương án | Có gì (24/09/2026) | Bằng chứng | Điểm yếu chính đã thấy |
|---|---|---|---|
| **(a)** Bản đồ tĩnh + định vị lại từng vòng | `lidar/localize.py`, [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md) | 29 test tổng hợp; bản ghi thật cho kết quả nhất quán (cùng chỗ thì OK, chỗ khác thì FAILED); **chưa có tham chiếu độc lập** | Hướng lệch +4,3° giữa hai phiên, chưa rõ nguyên nhân; bản đồ từ một chỗ đặt; sa bàn đối xứng sẽ cho kết quả nhập nhằng |
| **(b)** Odometry khớp scan + bản đồ tăng dần | **mới:** `lidar/scan_odometry.py`, `tests/test_scan_odometry.py` (32 test) | Tổng hợp: xe đi 4,4 m, lệch cuối 4 mm. DROW: 35 chuỗi, 1.856 m. C1: 6 bản ghi đứng yên | Trôi theo quãng đường; lạc trong đám đông (không định vị lại); hành lang trơn thật sự thì dọc trục là "không biết" (báo AMBIGUOUS); không đóng vòng |
| **(c)** Thư viện ngoài (Cartographer, slam_toolbox, Hector, GMapping, BreezySLAM, KISS-ICP…) | **Không có gì** trên máy bàn: không gói nào trong hai `.venv`, không ROS | Chỉ kiểm được là **chưa cài**; mọi yêu cầu khác là **cần tra** | Cần cài đặt (bị cấm trong đợt này), cần Linux/ROS hoặc cầu nối; chưa rõ giấy phép và đầu vào |
| **(d)** Odometry bánh xe / IMU | Giao thức xe đã có `speed_measured_mm_s`, `steer_measured_mrad`, `gyro_z_mrad_s` ([GIAO_THUC_XE.md](GIAO_THUC_XE.md)) | **Chưa có phần cứng**: AS5600, encoder, BNO085 chưa mua | Chưa có bộ đếm quãng đường cộng dồn trong telemetry |

**Số chính của (b), offline, 24/09/2026:**

- **DROW, 35 chuỗi (tối đa 3.000 vòng mỗi chuỗi):** tính trên đoạn 5 m, `scan_to_map` lệch so với odometry DROW trung vị
  **2,2 %** quãng đường và **0,12°/m** (trung vị của các trung vị theo chuỗi). **2,8 % số vòng FAILED**, 7/35 chuỗi có
  lúc bị "lạc"; ở 4/7 chuỗi đó hầu hết vòng FAILED có lý do tỉ lệ khớp thấp + mâu thuẫn với bản đồ (vật mới trong vùng
  đã thấy trống, suy ra là người). Bản đầu (khóa cứng): 2,7 %, 9,8 % FAILED, 19/35 chuỗi lạc. Tắt hẳn phép kiểm suy biến
  cho số gần như ngang bản sửa (2,2 %, 2,9 % FAILED, 9/35). `scan_to_scan` không bao giờ FAILED nhưng lệch **23,9 %** và
  0,54°/m, và đếm thiếu quãng đường (tỉ lệ bước trung vị 0,82).
- **DROW, chạy hết chiều dài 9 chuỗi dài** (90.561 vòng, 6–36 phút mỗi chuỗi): `scan_to_map` FAILED **30,9 %** số vòng
  (bản đầu 56,4 %), 6/9 chuỗi có lúc lạc; riêng một chuỗi đông người 36 phút chiếm 25.952 vòng FAILED, bỏ chuỗi đó thì
  còn 3,2 %. Đã lạc thì gần như không bắt lại được (không có định vị lại). Chỗ này vẫn nghiêng về (a) làm nguồn tư thế
  chính.
- **C1 đứng yên:** `scan_to_map` không trôi. Trong 57 s (o03, bàn thử 24/09) lệch lớn nhất 9 mm và 0,5°, độ dốc 0,6 mm/phút.
  Ngược lại `scan_to_scan` trôi **17,5 cm và 6,6° trong 57 s**, tức ≈ 22 cm/phút.

**ĐỀ XUẤT – CHỜ CHỐT (mục 7):**

- V1 dùng (a) làm nguồn tư thế chính: bản đồ tĩnh của sa bàn, dựng trước, cố định trong lượt chạy; định vị lại mỗi vòng.
- (b) `scan_to_map` làm việc phụ: dự đoán giữa các vòng, giám sát chéo (lệch nhau thì dừng), và ghép bản đồ từ nhiều chỗ đặt.
- Không đưa (c) vào V1.
- Khi có encoder/AS5600/BNO085: thay dự đoán vận tốc không đổi của (b) bằng odometry bánh xe + gyro (d).

Phương án này chỉ đúng khi có đủ các điều kiện ở mục 7. Mục 8 là các phép đo để xác nhận nó.

*(Cập nhật 02/10/2026: người dùng giao làm theo đề xuất mục 7 ("làm hết"); ngưỡng vẫn ĐỀ XUẤT – CHỜ CHỐT, dùng cho
nghiệm thu tới khi chốt. Đã viết nguồn tư thế (a) + (b) nối vào phiên đỗ xe và công cụ dựng bản đồ nhiều chỗ đặt:
[NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md); mới kiểm ở mức MP và trên bản ghi C1 đứng yên, chưa thử trên xe chạy.
Không phải SLAM.)*

## 1. Bối cảnh V1 và ràng buộc

| Ràng buộc | Giá trị | Nguồn |
|---|---|---|
| Máy chạy | Laptop Windows (máy nộp đồ án, **chưa đo LiDAR/định vị trên máy này**); máy bàn Windows 11 để phát triển | TONG_HOP mục 2 |
| Môi trường Python | `.venv`: numpy, opencv, PySide6, shapely, pyserial; **không có scipy**, không torch. `.venv-train`: torch, opencv, PySide6, pyserial | kiểm `pip list` tối 24/09/2026 trên máy bàn |
| LiDAR | RPLIDAR C1, ≈ 10,0 Hz, ≈ 510 tia/vòng, 360°, phản hồi 0,09–14,6 m; sai số so với thước **CHƯA ĐO** | [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 3, 3b |
| Xe | 1/12; `max_speed_mps` 0,3 là **giả định** (`configs/vehicle_default.json`) → ≈ 3 cm mỗi vòng quét ở 10 Hz | cấu hình |
| Sa bàn | ví dụ 3 × 2 m (`scenarios/sa_ban_3x2_hai_hop.json`, ghi rõ "kích thước chỉ là ví dụ"); chiều cao vật/tường so với mặt quét của LiDAR trên xe **CHƯA CHỐT** (chưa có gá) | kịch bản |
| Cảm biến chuyển động | AS5600, encoder (MT6701 hoặc loại khác), BNO085 **chưa mua** | TONG_HOP mục 2, 5.3 |
| Yêu cầu kế hoạch | Tách ba kết quả "đọc scan / tạo map / định vị lại"; định vị phải có tham chiếu độc lập; không gán odometry = 0 để báo đã có định vị | kế hoạch mục 5, 12 |

Hệ quả cho việc chọn phương án:
- Sa bàn nhỏ và tĩnh. Từ gần như mọi chỗ trong sa bàn, C1 (tầm tới ≈ 12 m) thấy được toàn bộ biên sa bàn và tường phòng.
  Vì vậy V1 không cần bản đồ dựng dần khi xe đi xa, và không cần đóng vòng: đó là hai lý do chính để dùng SLAM.
- Chuỗi phần mềm hiện tại là Python trên Windows. Thư viện nào cần ROS/Linux thì thêm một tầng hệ thống và cầu nối dữ
  liệu (mục 4).

## 2. Phương án (a): bản đồ tĩnh + định vị lại từng vòng (đã có)

Chi tiết ở [DINH_VI_LIDAR.md](DINH_VI_LIDAR.md). Tóm lại:

- `lidar/occupancy.py` dựng lưới UNKNOWN/FREE/OCCUPIED 5 cm từ các vòng quét. `lidar/localize.py` đặt từng vòng quét lên
  lưới đó: trường khoảng cách, khớp tương quan nhánh-cận kiểu Cartographer, tinh chỉnh Gauss-Newton, rồi kiểm từng tia.
  Kết quả là OK / AMBIGUOUS / FAILED kèm lý do.
- Mỗi vòng được đặt **độc lập** lên bản đồ cố định, nên sai số không cộng dồn theo thời gian hay quãng đường.
- Số đo offline (24/09/2026, bản đồ `map_p07`):
  - live_headless: 60/60 OK, tư thế ổn định trong vài mm, nhưng hướng **+4,33°** so với lúc dựng bản đồ;
  - k01 (LiDAR đã dời chỗ): 151/151 FAILED, tức bộ định vị không nhận bừa;
  - thời gian mỗi vòng với cửa sổ ±0,5 m / ±30°: trung vị ≈ 11–13 ms trên máy bàn; tìm trên cả bản đồ 0,5–6 s.
- **Chưa đạt theo kế hoạch:** chưa có vị trí tham chiếu đo bằng thước.

Điểm mạnh cho V1: không trôi; báo hỏng trung thực; không cần đầu vào nào ngoài vòng quét; đã chạy được bằng `.venv` trên
Windows.

Điểm yếu và điều kiện:
- Cần tư thế ban đầu gần đúng, hoặc một lần tìm toàn bản đồ (0,5–6 s, chỉ để khởi tạo).
- Bản đồ dựng từ một chỗ đặt có nhiều ô UNKNOWN phía sau vật; cần ghép bản đồ từ nhiều chỗ đặt, mà việc ghép cần biết tư
  thế từng chỗ (đo bằng thước, hoặc dùng (b)).
- Sa bàn đối xứng (hình chữ nhật trơn) sẽ cho đỉnh thứ hai, tức AMBIGUOUS.
- Vật mới trong sa bàn (tay người, hộp mới) gây mâu thuẫn với bản đồ. Ngưỡng `conflicts_with_map` 0,25 là tạm, CHƯA CHỐT.
- Hướng lệch +4,3° giữa hai phiên liên tiếp chưa rõ là do thiết bị bị xoay hay gốc góc đổi sau mỗi lần khởi động mô-tơ.
  Nếu là gốc góc đổi thì hướng của C1 so với xe phải hiệu chuẩn lại mỗi lần bật.
- Dấu trái/phải của góc chưa xác minh bằng vật thật. Mọi phương án đều như vậy: đảo dấu thì bản đồ và định vị vẫn nhất
  quán, chỉ là trong một thế giới lật gương.

## 3. Phương án (b): odometry khớp scan + bản đồ chiếm chỗ tăng dần (viết ngày 24/09/2026)

Mã: [`autopark/lidar/scan_odometry.py`](../autopark/lidar/scan_odometry.py). Test:
[`tests/test_scan_odometry.py`](../tests/test_scan_odometry.py). Công cụ chạy theo lô, không mở cửa sổ; lệnh ở mục 9.

### 3.1. Cách làm

Dùng lại bộ máy của (a): `LocalizationMap` (trường khoảng cách, nhánh-cận, kiểm từng tia) và `OccupancyCounts`. Mỗi vòng
quét đi qua các bước sau:

1. **Dự đoán** tư thế bằng vận tốc không đổi. Vận tốc là chuyển động từ vòng chấp nhận gần nhất tới vòng chấp nhận hiện
   tại, chia đều cho số vòng giữa hai vòng đó. Đây **không phải odometry bánh xe** và không gán odometry bằng 0.
   (Sửa đêm 24/09/2026: bản đầu lấy chuyển động từ tư thế của vòng ngay trước, kể cả khi vòng đó FAILED và tư thế chỉ
   là dự đoán hoặc đang đứng yên vì `lost`. Khi bắt lại sau một đoạn mù, cả bước nhảy tích lũy bị coi là chuyển động
   của một vòng rồi được ngoại suy tiếp; mục 3.3, phát hiện 6.)
2. **Chọn điểm để khớp.** Lấy tia có tầm ≤ tầm bản đồ − 1 m (8 − 1 = 7 m) và có một tia kề theo góc chạm cách ≤ 10 cm
   (mục 3.3, phát hiện 1).
3. **Khớp nhánh-cận** trong cửa sổ ±0,15 m / ±8° quanh dự đoán. Nếu đỉnh ở mép cửa sổ thì tìm lại một lần với cửa sổ
   ×2,5.
4. **Xét suy biến** bằng pháp tuyến bề mặt của chính vòng quét. Tính λmin/λmax của Σ n·nᵀ trên cửa sổ 7 tia; nếu < 0,04
   thì mọi bề mặt thấy được gần song song, như ở hành lang (mục 3.3, phát hiện 2).
5. **Tinh chỉnh Gauss-Newton** có số hạng kéo về dự đoán (σ 5 cm, 2° mỗi vòng). Khi suy biến (bước 4): điểm xuất phát
   bỏ thành phần dọc hướng suy biến của kết quả tìm, và thêm một **tiên nghiệm mềm** kéo thành phần đó về dự đoán
   (σ 3 cm mỗi vòng, `lock_sigma_m`); trạng thái AMBIGUOUS, lý do `degenerate`. Nếu đỉnh tìm ra mép cửa sổ **chỉ** theo
   hướng suy biến thì không tính là mép cửa sổ (thành phần đó đã bị bỏ); ghi thêm lý do `edge_along_axis`.
   (Sửa đêm 24/09/2026, ĐỀ XUẤT – CHỜ CHỐT. Bản đầu khóa **cứng**, σ 2 mm, và vẫn tính mép theo hướng suy biến là mép.
   Phép kiểm pháp tuyến báo suy biến cả khi cột, khung cửa vẫn cho biết vị trí dọc trục; khóa cứng làm tư thế dọc trục
   chạy theo vận tốc cũ, robot đổi tốc độ là lạc. Mục 3.3, phát hiện 5; số trước/sau ở mục 3.4.)
6. **Kiểm từng điểm.** Nếu tỉ lệ khớp < 0,5, ít hơn 30 điểm khớp, mâu thuẫn > 0,5 hoặc đỉnh ở mép cửa sổ thì FAILED:
   tư thế lấy theo dự đoán và **không cập nhật bản đồ**. Sau 5 lần FAILED **liên tiếp** thì thêm lý do `lost` và thôi
   ngoại suy vận tốc. Hai điều cần biết về các cổng này (test giữ, đo 24/09/2026 trên cảnh tổng hợp):
   - Với ngưỡng mặc định 0,5 / 0,5, mâu thuẫn > 0,5 luôn kéo theo tỉ lệ khớp < 0,5 (vì số điểm mâu thuẫn c và khớp m
     thỏa c/(m + c) ≤ 1 − m/N). Cổng mâu thuẫn vì vậy chỉ **thêm lý do**, không tự quyết FAILED. Muốn nó có tác dụng
     riêng thì cần `max_conflict_fraction` < 1 − `min_matched_fraction` (test dùng 0,25 / 0,6). **CHƯA CHỐT.**
   - Cổng mép cửa sổ loại cả vòng mà tinh chỉnh đã khớp tốt: hướng nhảy 30° giữa hai vòng (cửa sổ tìm lại ±20°) cho tỉ
     lệ khớp 1,00 mà vẫn FAILED `window_edge`. Đây là quy ước thận trọng, cố ý giữ.
7. **Bản đồ tham chiếu:**
   - `scan_to_map` (mặc định): một lưới đếm bền. Vòng quét được thêm làm khung khóa khi đã đi ≥ 10 cm hoặc quay ≥ 5°;
     lưới tự nới khi cảm biến tới gần mép. Cảm biến đứng yên thì không có khung khóa mới, nên không cộng dồn;
   - `scan_to_scan`: vòng chấp nhận ngay trước làm tham chiếu.

**Không phải:** SLAM đầy đủ (không đóng vòng, không tối ưu đồ thị tư thế, không định vị lại khi đã lạc); không có đầu vào
bánh xe/IMU; chưa nối vào phiên đỗ xe. Mọi ngưỡng là tạm, **CHƯA CHỐT**. *(Cập nhật 02/10/2026: (b) nay chạy trong
nguồn tư thế LiDAR của phiên đỗ xe, làm tâm cửa sổ và phép kiểm chéo cho (a), mới ở mức MP và trên bản ghi C1 đứng yên;
[NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) mục 3. Vẫn không phải SLAM.)*

### 3.2. Kiểm bằng dữ liệu tổng hợp (quỹ đạo biết trước)

`tests/test_scan_odometry.py`: 32 test (18 test ban đầu, thêm 14 test đêm 24/09/2026 sau khi agent kiểm tra phát hiện
lỗi; một trong số đó chạy trên dữ liệu DROW thật và tự bỏ qua nếu máy không có DROW). Vòng quét kiểu C1 (360°, 500 tia,
nhiễu 1 cm, 10 % tia mất phản hồi, 3 vật di động không có trong bản đồ) hoặc kiểu DROW (224,5°, 450 tia). Số đo lấy
lúc viết test trên máy bàn, 24/09/2026. Cận trong test thường rộng hơn số đo 2–5 lần; ở test chạy nhiều seed, cận
rộng hơn số đo xấu nhất trên 41 seed khoảng 1,5–2 lần.

| Kịch bản | Số đo |
|---|---|
| Xe đi tới 1,8 m, rẽ trái 90°, dừng, lùi, lùi cong: 4,4 m, 0,3 m/s, 211 vòng (`scan_to_map`) | Mọi vòng OK. Sai số lớn nhất 10,6 mm và 0,20°; cuối 4,1 mm và 0,12°; đoạn 1 m trung vị 0,23 %; 47 khung khóa |
| Đứng yên 30 s (300 vòng, nhiễu mới mỗi vòng, có vật di động) | `scan_to_map`: 1 khung khóa. Trên 600 vòng (60 s): lệch lớn nhất 7,4 mm và 0,19°, độ dốc 0,2 mm/phút |
| Đứng yên 15 s không vật di động | `scan_to_scan` lệch lớn nhất 33 mm và 0,41°; `scan_to_map` 6 mm và 0,15° trên cùng dữ liệu |
| Tốc độ 0,25 m mỗi vòng (lớn hơn cửa sổ ±0,15 m) | Vận tốc không đổi: chỉ vòng đầu phải tìm lại. Mô hình đứng yên: gần như mọi vòng phải tìm lại |
| Hành lang hai tường song song ±30 m, không có đầu hồi, nhiễu 5 mm (41 seed × 60 vòng bằng script tạm; test chạy 4 seed) | Mọi vòng AMBIGUOUS/`degenerate`, 0 vòng FAILED; tỉ số pháp tuyến ≤ 0,0103. Dọc trục gần dự đoán: thật đi 1,8 m, ước lượng lớn nhất 134 mm (trung vị 20 mm), tức **không biết**, và được báo là không biết. Ngang trục ≤ 24 mm, hướng ≤ 0,83°. Đỉnh ra mép cửa sổ chỉ theo dọc trục trung bình 0,7 lần mỗi chuỗi, không tính là mép. Bản khóa cứng (bản đầu 24/09/2026, chạy lại trên bản sao mã cũ): 19/41 seed có vòng FAILED `window_edge` (tổng 29 vòng), dọc trục ≤ 29 mm, ngang ≤ 17 mm, hướng ≤ 0,62°; test cũ chỉ chạy seed 14 × 30 vòng nên không thấy |
| Hành lang trơn ±300 m, nhiễu 1 cm, 60 vòng (thật đi 1,8 m), 41 seed (script tạm, không phải test) | **Cái giá của khóa mềm.** Vận tốc dọc trục lấy từ các vòng suy biến nên đi bộ ngẫu nhiên: dọc trục lớn nhất trung vị 0,15 m, 14/41 seed > 0,5 m, xấu nhất 3,7 m. Khóa cứng: ≤ 33 mm. Không kéo (σ 1 km): trung vị 0,36 m, 20/41 seed > 0,5 m. Mọi vòng của cả ba cách đều AMBIGUOUS: dọc trục ở cảnh này là **không biết**; khóa cứng chỉ "đứng yên" vì giữ vận tốc cũ, không phải vì đo được. Hai seed 300 vòng (90 m): khóa mềm 0,14 và 0,23 m, khóa cứng ≤ 2 cm |
| Hành lang có vài cột mảnh 4 × 4 cm | Hessian vẫn tốt (độ lệch chuẩn < 5 cm và < 2°), chỉ phép kiểm pháp tuyến bắt được. Tắt phép kiểm thì odometry báo OK một quỹ đạo sai dọc trục (tỉ lệ bước 0,60). Mặc định: AMBIGUOUS, dọc trục gần dự đoán (tỉ lệ bước 0,11), tức cột 4 cm quá nhỏ để thắng tiên nghiệm |
| Hội trường 30 × 6 m có cột 0,2 × 0,3 m, giảm tốc 1,5 → 0,5 m/s, 12 m (seed 18) | Cột quá nhỏ để có pháp tuyến: 87/120 vòng AMBIGUOUS/`degenerate` có khóa. Khóa mềm: 0 FAILED, lệch cuối 2,9 cm (seed 19, 20: 10,0 và 4,0 cm). Khóa cứng (bản đầu, chạy lại trên bản sao mã cũ): 18 FAILED, lệch cuối 1,82 m (seed 19, 20: 5,84 và 1,83 m); với vận tốc không đổi thì khóa cứng vẫn ổn (4,8 cm), nên test cũ không thấy. Đây là kiểu hỏng 1 của DROW tái hiện trên cảnh tổng hợp |
| Hành lang có hốc cửa, kiểu DROW, 8 m, `scan_to_scan` | Có hai bộ lọc điểm: lệch cuối 3,8 cm. Bỏ cả hai: 12 cm (120 vòng: 3,6 cm so với 22 cm) |
| Một người đi trước-phải cách 1,3 m, cùng tốc độ, 8 m | `scan_to_scan`: tỉ lệ bước 0,76, lệch cuối 1,89 m. `scan_to_map`: 1,00 và 3,3 cm |
| Đảo dấu góc vòng quét | Quay ngược chiều thật (`yaw_gain` < −0,9) |
| Vòng quét lạ (hội trường tròn), vòng toàn NaN | FAILED; tư thế theo dự đoán; lưới đếm không đổi từng ô; các vòng sau lại OK |
| 8 vòng NaN liên tiếp khi đang quay tại chỗ | Hai vòng đầu còn ngoại suy; từ lần FAILED thứ 3 (`lost_after`=3 trong test) báo `lost`; sau đó tư thế đứng yên |
| Đi tới 3 cm/vòng, 17 vòng NaN (lạc), bắt lại rồi lùi ngay | Vòng 48 bắt lại, vận tốc 0,027 m/vòng, không FAILED nào sau đó, lệch cuối 7,5 mm. Bản đầu (chạy lại trên bản sao mã cũ): vận tốc = cả bước nhảy tích lũy (0,35 m/vòng), cả 29 vòng sau đó FAILED, lệch cuối 2,6 m |
| Hội trường 30 × 6 m có cột 0,8 × 0,6 m, đi 18,3 m có tăng/giảm tốc (1,5 → 0,9 → 1,8 → 1,2 m/s) | Lưới tự nới 4 lần; 0 vòng khóa; lệch cuối 17,8 cm, hướng ≤ 0,73° (seed 18; seed 1–3: 3,5–3,6 cm). Bản trước của test dùng cột nhỏ và vận tốc không đổi: 87/120 vòng khóa theo dự đoán, nên con số 4,8 cm khi đó đo mô hình dự đoán, không đo khớp scan |
| Cổng chấp nhận, mỗi cổng một kịch bản chỉ nó quyết định | Vật mới trong vùng trống → `conflicts_with_map` (119 điểm, mâu thuẫn 1,00); ngưỡng 0,6 / 0,25 → chỉ `conflicts_with_map` (khớp 0,67, mâu thuẫn 0,33); hướng nhảy 30° → chỉ `window_edge` dù tỉ lệ khớp 1,00; góc phòng nhỏ → chỉ `few_matched` (21 điểm); `lost` cần 5 FAILED **liên tiếp**; độ lệch chuẩn vượt ngưỡng → AMBIGUOUS không khóa; < 20 pháp tuyến → không xét suy biến hình học |
| CLI | Hai bản ghi cùng tên ở hai thư mục → hai tệp kết quả riêng (bản đầu ghi đè nhau); `--skip-seconds`, `--mirror` với C1; nội suy odometry DROW theo thời gian (gỡ quấn yaw qua ±π) |
| DROW thật `10-34-20-c`, vòng 300–859, 26,7 m (tự bỏ qua nếu không có DROW) | 0 FAILED, lệch cuối 0,56 m (2,1 %), đoạn 5 m trung vị 1,60 %. Bản đầu: 358 FAILED, 16,8 m, 98,9 % |

**Kiểm đột biến** (đêm 24/09/2026, trên bản sao trong thư mục tạm, không sửa repo): 36 đột biến của `scan_odometry.py`,
34 bị bắt; danh sách và kết quả ở mục 3.7.

### 3.3. Sáu phát hiện (đều có test giữ; 5 và 6 do agent kiểm tra tìm ra đêm 24/09/2026)

1. **Điểm xa thưa ghim chuyển động về 0.** Ở góc tới sượt, tường xa chỉ được lấy mẫu thành những chấm cách nhau nhiều ô,
   và vị trí chấm gắn với tư thế của vòng quét. Thêm vào đó, tường trong bản đồ của vòng trước dừng đúng ở tầm tối đa.
   Khớp cả những điểm này thì chuyển động dọc hành lang bị kéo về 0. Cách sửa: chỉ khớp điểm ≤ tầm bản đồ − 1 m và có tia
   kề ≤ 10 cm. Trên hành lang có hốc cửa, 8 m: lệch cuối 12 cm → 3,8 cm.
2. **Hessian của phép khớp không phát hiện được hành lang.** Trên hành lang tổng hợp, bản đồ dựng từ một vòng quét có "vân"
   do lượng tử hóa ô. Tỉ số trị riêng phần tịnh tiến của JᵀWJ ≈ 0,6 (trông như ràng buộc tốt), trong khi ước lượng dọc
   hành lang nhảy tùy ý. Pháp tuyến bề mặt của chính vòng quét không phụ thuộc bản đồ: hành lang cho tỉ số ≤ 0,028 (nhiễu
   1 cm) và 0,010 (nhiễu 5 mm). Bản ghi C1 thật (bàn làm việc, phòng; p07, k01, o03, cứ 5 vòng lấy một) cho ≥ 0,42.
3. **Vật đi cùng tốc độ lừa `scan_to_scan`.** DROW `run_2015-11-25-10-34-20-a`, vòng 140–180: một vật phía trước-phải
   ở cách 1,1–1,5 m suốt đoạn, trong khi odometry báo robot đi 2,0 m. Trên vòng 100–200 (4,5 m theo odometry),
   `scan_to_scan` chỉ đếm được 16 % quãng đường (11–22 % theo từng đoạn 25 vòng), còn `scan_to_map` 100 % (97–104 %).
   Các vòng này không có nhãn người, nên "người đi cùng" là **suy luận**. Test tổng hợp tái hiện đúng hiện tượng.
4. **Chỉ số so hướng phải lấy trên đoạn, không lấy từng bước.** Ban đầu hệ số hồi quy Δθ từng bước của khớp scan theo
   odometry DROW là 0,88. Có hai cách giải thích: odometry DROW quay dư ≈ 13 %, hoặc chỉ số bị kéo về 0 bởi nhiễu thời
   gian. Kiểm độc lập bằng độ nét bản đồ dựng từ odometry DROW, 2 chuỗi, script tạm: nhân góc quay của odometry với
   0,885 thì bản đồ **mờ hơn** (độ nét 0,290 → 0,242 và 0,284 → 0,260), tức odometry quay đúng tỉ lệ. Tính trên đoạn
   ≥ 5 vòng thì hệ số ≈ 1,00. Công cụ nay tính trên đoạn 10 vòng (`yaw_gain`).
5. **Phép kiểm pháp tuyến báo suy biến nhầm, và khóa cứng biến lỗi đó thành lạc.** Pháp tuyến chỉ có ở chỗ 7 tia liền
   nhau nằm gần thẳng hàng. Cột, khung cửa, người thì không cho pháp tuyến, nên cảnh "hai tường dài + vài cột" có tỉ số
   pháp tuyến < 0,04 và bị báo suy biến, trong khi cột vẫn cho biết vị trí dọc trục. Bản đầu khóa **cứng** (σ 2 mm)
   thành phần dọc trục vào dự đoán vận tốc không đổi, bỏ mất số đo đó; robot đổi tốc độ thì ước lượng vượt trước, đỉnh
   ra mép cửa sổ, FAILED, rồi `lost`. Đây mới là nguyên nhân chính của "kiểu hỏng 1" trên DROW (mục 3.4), **không phải**
   việc thiếu odometry bánh xe như bản trước của tài liệu này viết. Sửa: khóa mềm σ 3 cm, và mép cửa sổ chỉ theo dọc
   trục không tính là mép. Hai phần này phải đi cùng nhau: chỉ bỏ qua mép dọc trục mà vẫn khóa cứng thì ước lượng vượt
   trước mà không bị chặn (agent kiểm tra đo trên `13-47-42`: tỉ lệ bước 1,98, đoạn 5 m 27,7 %; chưa chạy lại). Cái
   giá: ở hành lang trơn thật sự, vận tốc dọc trục đi bộ ngẫu nhiên (nhiễu 1 cm, 60 vòng: 14/41 seed lệch dọc trục > 0,5
   m, khóa cứng ≤ 33 mm; mục 3.2); các vòng đó vẫn báo AMBIGUOUS. Tắt hẳn phép kiểm (`--min-normal-ratio 0`) cho số DROW
   gần như ngang khóa mềm (mục 3.4), nhưng hành lang cột mảnh thì báo OK một quỹ đạo sai (tỉ lệ bước 0,60). Chưa có cách
   nào tốt ở cả hai loại cảnh (mục 10).
6. **Vận tốc sau khi bắt lại.** Sau các vòng FAILED, tư thế chỉ là dự đoán (hoặc đứng yên khi `lost`). Bản đầu tính vận
   tốc từ tư thế đó, nên cả bước nhảy tích lũy trong lúc mù bị coi là chuyển động của một vòng, rồi được ngoại suy tiếp.
   Tổng hợp: 0,35 m/vòng thay vì 0,03, xe lùi ngay sau khi bắt lại thì cả 29 vòng sau đó FAILED. Sửa: lấy từ vòng chấp
   nhận gần nhất, chia đều theo số vòng (hàm `scale_motion`, xoắn không đổi trong SE(2)). Vận tốc tính theo số vòng,
   không theo thời gian: nếu vòng quét bị rơi trước khi tới `update` thì vẫn sai; **CHƯA SỬA**, và chưa kiểm dữ liệu
   C1/DROW đã chạy có rơi vòng hay không. *(02/10/2026: `OdometryConfig.velocity_per = "second"` tính vận tốc theo thời
   gian; nguồn tư thế dùng nó, mặc định "scan" giữ số cũ. Phòng tổng hợp 0,3 m/s, 30 % vòng rơi: sai số dự đoán lớn
   nhất 9,8 mm theo giây, 62 mm theo vòng)*

### 3.4. DROW v2: so với odometry đi kèm (không phải ground truth)

**Dữ liệu và cách chạy.** 30 chuỗi val + 5 chuỗi test, mỗi chuỗi tối đa 3.000 vòng đầu: 59.175 vòng, 1.855,5 m theo
odometry DROW. Cấu hình mặc định (tầm bản đồ 8 m). Tư thế ghép với vòng quét theo dòng, như loader của tác giả. Nội suy
odometry theo thời gian vòng quét thay cho ghép theo dòng chỉ đổi trung vị đoạn 5 m 0,03 (`scan_to_map`) và 0,08
(`scan_to_scan`) điểm phần trăm. Chạy đêm 24/09/2026 trên máy bàn bằng bản sửa (khóa mềm). Cột "bản đầu" là lần chạy
tối 24/09/2026 bằng bản khóa cứng, cùng lệnh, giữ ở tệp bằng chứng riêng (cuối mục này).

**Chỉ số dùng trong bảng:**
- *đoạn 5 m*: với mỗi vòng i, lấy j là vòng đầu tiên mà odometry DROW đã đi ≥ 5 m kể từ i; so chuyển động tương đối
  i→j của hai quỹ đạo (tịnh tiến theo % quãng đường, quay theo độ/m); lấy trung vị theo i, rồi trung vị theo chuỗi;
- *cuối/quãng đường*: hai quỹ đạo cùng gốc, chênh vị trí cuối chia quãng đường;
- *tỉ lệ bước*: tổng quãng đường khớp scan chia tổng quãng đường odometry DROW. Rung từng vòng cũng làm chỉ số này tăng.

| Chỉ số (35 chuỗi) | `scan_to_map`, bản sửa | `scan_to_map`, bản đầu (khóa cứng) | `scan_to_map`, không xét suy biến (`--min-normal-ratio 0`) | `scan_to_scan`, bản sửa |
|---|---|---|---|---|
| Vòng FAILED | **1.646 (2,78 %)** | 5.777 (9,76 %) | 1.718 (2,90 %) | 0 |
| Vòng AMBIGUOUS | 9.349 (15,8 %) | 7.403 (12,5 %) | 3 | 9.349 (15,8 %) |
| Chuỗi có ít nhất một lần `lost` | **7/35** | 19/35 | 9/35 | 0/35 |
| Đoạn 5 m, tịnh tiến: trung vị các trung vị (33 chuỗi có ≥ 5 m) | **2,19 %** (0,92–89,7 %) | 2,70 % (1,24–88,2 %) | 2,16 % (1,01–89,5 %) | 23,9 % (3,6–76,1 %) |
| Đoạn 5 m, quay: trung vị các trung vị | **0,122°/m** | 0,124°/m | 0,119°/m | 0,537°/m |
| Cuối/quãng đường, chuỗi ≥ 10 m: trung vị (khoảng) | 4,1 % (0,6–75,3 %) | 5,1 % (0,2–74,4 %) | 2,9 % (0,6–75,0 %) | 20,3 % (1,8–45,3 %) |
| Tỉ lệ bước, chuỗi ≥ 10 m: trung vị (khoảng) | 1,004 (0,85–1,18) | 1,001 (0,62–1,25) | 1,009 (0,85–1,18) | 0,824 (0,68–1,35) |
| Thời gian mỗi vòng: trung vị các trung vị (máy bận, tải khác nhau giữa các cột; chỉ để so tương đối) | 19,7 ms | 28,5 ms | 29,1 ms | 50,8 ms |

- `scan_to_map` tốt hơn `scan_to_scan` theo đoạn 5 m ở **32/33** chuỗi. Ngoại lệ duy nhất là `11-01-30` (kiểu hỏng 3
  dưới đây). Ở bản đầu, ngoại lệ thứ hai là `10-34-20-c`, do khóa cứng: nay 1,51 %, `scan_to_scan` 3,61 %.
- Bản sửa, tách theo `lost`: 28 chuỗi không `lost` (26 có đoạn ≥ 5 m, cũng là 26 chuỗi ≥ 10 m): đoạn 5 m trung vị
  2,0 %, p95 theo đoạn 5 m (lấy trung vị theo chuỗi) 15 %, cuối/quãng đường trung vị 3,1 %. 7 chuỗi có `lost`: 4,5 %,
  p95 106 % (21–134 %), cuối/quãng đường 7,5 %.
- Bản đầu, tính lại từ tệp bằng chứng cũ (bản trước của tài liệu này ghi sai hai số: "14 chuỗi không `lost`" và "p95
  … là 56 %"): 16 chuỗi không `lost` (14 chuỗi trong đó có đoạn ≥ 5 m, cũng là 14 chuỗi ≥ 10 m): đoạn 5 m trung vị
  2,3 %, cuối/quãng đường 3,0 %. 19 chuỗi có `lost` (cả 19 có đoạn ≥ 5 m): 3,8 %, nhưng p95 theo đoạn 5 m, lấy trung
  vị theo chuỗi, là 99 % (14,7–134,5 %); để so, 14 chuỗi không `lost` là 28 %, cả 33 chuỗi là 56 %.
- **Khóa mềm so với tắt hẳn phép kiểm suy biến:** gần như ngang nhau trên DROW. Khóa mềm ít FAILED hơn (1.646 so với
  1.718) và ít chuỗi `lost` hơn (7 so với 9); nhưng đoạn 5 m của nó tốt hơn chỉ ở 12/33 chuỗi (xấu hơn ở 20, bằng ở 1),
  cuối/quãng đường trung vị 4,1 % so với 2,9 %, và xấu nhất ở `11-18-12-b` (10,5 % so với 3,1 %). Như vậy trên DROW,
  phép kiểm suy biến **không** làm ước lượng đúng hơn. Lý do vẫn giữ: nó báo AMBIGUOUS trung thực ở cảnh suy biến thật
  (mục 3.2, hành lang cột mảnh). **ĐỀ XUẤT – CHỜ CHỐT.**
- Mọi vòng bị báo suy biến đều được chấp nhận: số AMBIGUOUS của hai chế độ bằng nhau ở từng chuỗi, và không vòng FAILED
  nào của bản sửa có khóa (3.000 vòng đầu).

**Các kiểu hỏng của `scan_to_map` đã xem kỹ:**

1. **Khóa trục khi phép kiểm pháp tuyến báo suy biến trong khi vòng quét vẫn có thông tin dọc trục (bản đầu; đã sửa
   đêm 24/09/2026, mục 3.3 phát hiện 5).** `run_t_2015-11-26-13-47-42`, vòng 755–789: tỉ số pháp tuyến 0,010–0,039
   (dưới ngưỡng 0,04, nên khóa σ 2 mm), xen vài vòng OK có tỉ số vừa trên 0,04. Mỗi vòng OK đặt lại vận tốc bằng cả
   phần chênh đã dồn: vòng 773 đặt 16,3 cm/vòng, rồi các vòng khóa giữ đúng 16,3 cm/vòng, trong khi odometry DROW đi
   3,1–6,7 cm/vòng. Ước lượng vượt trước, đỉnh ra mép cửa sổ (`window_edge`, lần đầu ở vòng 780), lạc từ vòng 787.
   Bản trước của tài liệu này ghi "8 cm/vòng" và kết luận "đây đúng là chỗ cần odometry bánh xe": sai cả số lẫn kết
   luận. Bản sửa, **không cần odometry bánh xe** (3.000 vòng đầu):
   - `13-47-42`: FAILED 1.765 → 2; vòng `lost` 1.731 → 0; đoạn 5 m 72,6 % → 3,3 %; cuối 7,27 → 0,69 m trên 55,9 m;
   - `10-34-20-c`: FAILED 367 → 0; đoạn 5 m 7,93 % → 1,51 %; cuối 16,2 → 0,45 m trên 42,4 m;
   - `13-35-21`: FAILED 696 → 14; đoạn 5 m 19,2 % → 4,5 %; cuối 50,4 → 7,4 m trên 98,2 m.
2. **Đông người.** Không đổi sau khi sửa. Tỉ lệ khớp thấp và mâu thuẫn > 0,5 (điểm rơi vào ô đã thấy trống), nên FAILED
   liên tiếp rồi lạc. Ví dụ `14-07-15-a` (FAILED từ vòng 322, `lost` từ vòng 1.523, không bắt lại trong 3.000 vòng
   đầu), `11-01-30` (vòng 2.197), `15-52-55-a` (vòng 122), `15-52-55-e` (vòng 602). Khi đã lạc thì tư thế đứng yên;
   tracker chỉ bắt lại được nếu robot tình cờ quay về trong cửa sổ tìm. **Không có định vị lại toàn cục.**
3. **Cảnh gần, không giải thích được.** Chuỗi test `run_2015-11-25-11-01-30`: ở vòng 50–130, 55–66 % tia < 2 m; nhãn có
   một xe lăn cách 1,0–1,6 m ở vòng 5–100. Ngay từ đầu, khớp scan và odometry đã khác nhau: ở vòng 59–69 khớp scan báo
   đi 3,5 cm/vòng trong khi odometry đứng yên. Các vòng đó vẫn OK với tỉ lệ khớp 0,86–0,99, nên đây là **lỗi tự tin**.
   Chưa xác định nguyên nhân (không đổi sau khi sửa: đoạn 5 m 89,7 %).
4. **Vòng `window_edge` lẻ ở cảnh không suy biến.** Phần FAILED còn lại ngoài đám đông là các vòng lẻ chỉ có lý do
   `window_edge`, không vòng nào bị khóa: ví dụ `11-02-09-a` (19 vòng từ vòng 305), `16-26-37-d` (12), `13-35-21` (13).
   **CHƯA XEM KỸ** nguyên nhân (quay nhanh hơn cửa sổ tìm lại ±20°/vòng, hay đổi tốc độ đột ngột).

Ví dụ ảnh (DROW, trích theo giấy phép MIT, xem cuối tệp; bản sửa, trừ ảnh cuối):
[odometry_khop_scan_drow_10-34-20-a_scan_to_map.png](evidence/lidar/odometry_khop_scan_drow_10-34-20-a_scan_to_map.png),
[odometry_khop_scan_drow_10-34-20-a_scan_to_scan.png](evidence/lidar/odometry_khop_scan_drow_10-34-20-a_scan_to_scan.png),
[odometry_khop_scan_drow_13-47-42_scan_to_map.png](evidence/lidar/odometry_khop_scan_drow_13-47-42_scan_to_map.png)
(sau khi sửa: 2 vòng FAILED),
[odometry_khop_scan_drow_13-47-42_scan_to_map_khoa_cung_truoc_sua.png](evidence/lidar/odometry_khop_scan_drow_13-47-42_scan_to_map_khoa_cung_truoc_sua.png)
(bản đầu, khóa cứng: minh họa **lỗi khóa trục** của kiểu hỏng 1, không phải giới hạn của phương pháp). Trong ảnh: xanh
dương = khớp scan, tím = odometry DROW (không phải ground truth), X đen = vòng FAILED. Toàn bộ số theo từng chuỗi:
[odometry_khop_scan_20260924.json](evidence/lidar/odometry_khop_scan_20260924.json) (bản sửa, cả cột "không xét suy
biến") và [odometry_khop_scan_20260924_khoa_cung_truoc_sua.json](evidence/lidar/odometry_khop_scan_20260924_khoa_cung_truoc_sua.json)
(bản đầu).

**Chạy hết chiều dài** 9 chuỗi dài nhất (4 chuỗi val + 5 chuỗi test, mỗi chuỗi ≥ 4.546 vòng; `15-52-55-m` chỉ 3.140
vòng nên không tính), `scan_to_map`, 90.561 vòng, 1.909,8 m:

| Chuỗi | Vòng (thời lượng) | Bản sửa: FAILED / `lost` | Bản sửa: đoạn 5 m | Bản đầu: FAILED / `lost` | Bản đầu: đoạn 5 m | Không xét suy biến: FAILED / `lost` |
|---|---|---|---|---|---|---|
| val `14-58-49-b` | 4.546 (6,0 phút) | 0 / 0 | 2,28 % | 6 / 2 | 2,75 % | 0 / 0 |
| val `10-33-02-a` | 5.167 (6,8 phút) | 0 / 0 | 5,53 % | 7 / 0 | 5,26 % | 70 / 64 |
| val `11-02-09-a` | 5.215 (6,8 phút) | 22 / 1 | 3,11 % | 818 / 692 | 19,62 % | 2.142 / 2.100 |
| val `14-07-15-a` | 27.502 (36,1 phút) | 25.952 / 25.936 | 60,82 % | 25.888 / 25.859 | 59,70 % | 25.952 / 25.936 |
| test `11-01-30` | 11.138 (14,6 phút) | 85 / 40 | 1,91 % | 2.266 / 2.150 | 36,65 % | 64 / 34 |
| test `11-22-03` | 12.384 (16,3 phút) | 665 / 591 | 1,55 % | 8.807 / 8.693 | 96,68 % | 435 / 430 |
| test `11-55-45` | 4.842 (6,4 phút) | 1 / 0 | 2,27 % | 509 / 411 | 3,64 % | 137 / 128 |
| test `13-35-21` | 6.620 (8,7 phút) | 1.028 / 1.009 | 4,06 % | 889 / 755 | 4,88 % | 35 / 1 |
| test `13-47-42` | 13.147 (17,3 phút) | 224 / 124 | 4,32 % | 11.912 / 11.878 | 85,25 % | 9 / 0 |

- Bản sửa: 27.977 vòng FAILED (30,9 %), 6/9 chuỗi có `lost`; đoạn 5 m trung vị các trung vị 3,11 % (bản đầu 56,4 %,
  8/9, 19,6 %). Riêng `14-07-15-a` (đông người, 36 phút) chiếm 25.952 vòng FAILED ở cả ba cách chạy; bỏ chuỗi này thì
  bản sửa còn 2.025 / 63.059 vòng (3,2 %).
- Không xét suy biến: 28.844 vòng FAILED (31,9 %), 7/9 chuỗi có `lost`, đoạn 5 m 2,46 %, cuối/quãng đường trung vị
  8,0 % (bản sửa 8,4 %). Hai cách hơn kém nhau tùy chuỗi (`13-35-21`: 1.028 so với 35 vòng FAILED; `11-02-09-a`: 22
  so với 2.142), nên chưa có căn cứ chọn giữa hai cách trên DROW.
- `lost` vẫn gần như là trạng thái "hút": tư thế đứng yên và chỉ bắt lại được khi robot tình cờ quay về trong cửa sổ
  tìm (`14-07-15-a`: lạc từ vòng 1.523, bắt lại đúng một lần trong 26.000 vòng sau đó; `11-22-03`: lạc từ vòng 6.829,
  bắt lại 9 lần).
- `13-47-42` (bản sửa): tỉ lệ bước 1,84, tính theo bước 50 vòng còn 1,21; tức phần lớn là rung từng vòng, phần còn lại
  **CHƯA XEM KỸ**. Đoạn 5 m trung vị 4,32 %.
- Ở các chuỗi bị lạc, chỉ số "cuối/quãng đường" **không có ý nghĩa**: tư thế bị giữ yên, robot đi vòng trong vùng nhỏ.
- Kết luận không đổi: không dùng (b) một mình làm nguồn tư thế cho một lượt chạy dài. Cần một nguồn định vị lại, tức
  (a). Bản sửa bỏ được phần lớn FAILED do lỗi khóa trục, nhưng không bỏ được FAILED do đông người.

**Kiểm dấu góc bằng odometry** (`--mirror`, 3 chuỗi, 1.500 vòng đầu, bản sửa). Đảo dấu góc vòng quét thì `yaw_gain` là
−1,005 (`10-34-20-a`), −1,013 (`15-52-55-m`) và −1,000 (`11-55-45`); không đảo thì +1,007, +1,014 và +1,000. Như vậy
quy ước góc của `lidar/drow.py` (không đảo) cùng chiều với odometry DROW, khớp với phép kiểm độ nét bản đồ ngày 22/09
(GIAI_DOAN_1_LIDAR mục 5). Ở bản đầu, `15-52-55-m` lạc sau khi đảo (787 vòng FAILED) nên khi đó chỉ dùng được hai
chuỗi; nay chuỗi này không FAILED vòng nào. Với C1, khi có gyro BNO085, phép kiểm này thay được một phần lần đặt hộp
bên trái (mục 5).

DROW khác sa bàn ở nhiều điểm: cảm biến khác, 225° thay cho 360°, hành lang dài, đông người, robot đi 1–1,3 m/s. Vì vậy
các con số này **không chuyển thẳng sang sa bàn**. Chúng chỉ cho thấy phương pháp hỏng ở đâu và theo cách nào.

### 3.5. C1 đứng yên: odometry phải đứng yên

Sáu bản ghi, mọi bản ghi đều là cảm biến đứng yên, nên tư thế đúng là (0, 0, 0). Bỏ 3 s đầu (mô-tơ khởi động).
"Lớn nhất" là độ lệch xa nhất so với vòng đầu; "độ dốc" là hồi quy tuyến tính theo thời gian. Chạy lại đêm 24/09/2026
bằng bản sửa, cả sáu bản ghi trong **một** lệnh (hai `l01_tinh.npz` nay ra hai tệp kết quả riêng): mọi số dưới đây giống
hệt lần chạy bằng bản đầu, vì không vòng nào suy biến hay FAILED nên các chỗ sửa không có tác dụng ở đây.

| Bản ghi (ngày, thời lượng sau khi bỏ 3 s) | `scan_to_map`: lớn nhất; cuối; độ dốc | `scan_to_scan`: cuối; lớn nhất |
|---|---|---|
| p07 (22/09, 14,8 s) | 13,7 mm, 0,34°; 10,8 mm, +0,05°; 25 mm/phút | 33 mm, +0,58°; 39 mm, 0,86° |
| live_headless (22/09, 2,7 s; quá ngắn để tính độ dốc) | 7,5 mm, 0,17°; 5,2 mm, +0,10° | 18 mm; 22 mm |
| k01 (24/09, 12,0 s) | 6,6 mm, 0,38°; 3,7 mm, −0,10°; 5,5 mm/phút | 37 mm, −0,73°; 43 mm, 1,28° |
| l01 15:25 (24/09, 12,0 s) | 10,6 mm, 0,43°; 5,5 mm, +0,04°; 6,4 mm/phút | 36 mm, +2,31°; 37 mm, 2,31° |
| l01 19:08 (24/09, 11,9 s) | 5,2 mm, 0,46°; 1,5 mm, +0,28°; 3,7 mm/phút | 31 mm, −0,05°; 41 mm, 1,59° |
| **o03** (bàn thử 24/09, `perf_counter`, **56,7 s**) | **9,1 mm, 0,49°; 8,2 mm, +0,27°; 0,6 mm/phút, +0,05°/phút** | **175 mm, +6,55°; 181 mm, 8,2°** (≈ 22 cm/phút, 8°/phút) |

- Không bỏ 3 s đầu thì o03 (59,8 s) cho `scan_to_map` lớn nhất 4,6 mm và 0,42°, độ dốc 0,2 mm/phút.
- `scan_to_map` không có khung khóa mới nào (1 khung khóa mỗi bản ghi), nên đây là **kiểm "không trôi khi đứng yên"**,
  không phải kiểm trôi khi di chuyển. Rung vòng-với-vòng: độ lệch chuẩn 1,5–3,3 mm và 0,07–0,18°. Rung này lớn hơn của (a)
  trên bản đồ 181 vòng (1,4–2,7 mm, 0,05–0,07°), vì ở đây tham chiếu chỉ là một vòng quét.
- Với bản ghi 12–15 s, con số "mỗi phút" tính từ độ lệch cuối chủ yếu là rung chứ không phải trôi. Chỉ o03 đủ dài để nói
  về độ dốc.
- `scan_to_scan` đi bộ ngẫu nhiên: 3–4 cm trong 12–15 s, 17,5 cm và 6,6° trong 57 s.
- Tỉ lệ khớp trung vị 0,92–1,00; không vòng nào FAILED; không vòng nào `degenerate`. Tỉ số pháp tuyến trên p07, k01, o03
  (cứ 5 vòng lấy một) ≥ 0,42, tức cảnh không suy biến.

### 3.6. Thời gian

Đo trên máy bàn khi đang chạy song song nhiều tiến trình thí nghiệm DROW, 6 tiến trình kiểm đột biến và các agent
khác, nên chỉ để so tương đối (bản sửa, đêm 24/09/2026; số của bản đầu trong ngoặc):

- C1, `scan_to_map`: trung vị 14–33 ms mỗi vòng, p95 ≤ 42 ms (7–30 ms, p95 ≤ 40 ms);
- C1, `scan_to_scan`: 52–92 ms, vì phải dựng lại bản đồ mỗi vòng (44–89 ms);
- DROW: trung vị các trung vị 19,7 ms (`scan_to_map`) và 50,8 ms (`scan_to_scan`) (28,5 và 57,5 ms). Chưa tách được
  phần chênh là do bản sửa (ít vòng FAILED phải tìm lại với cửa sổ rộng?) hay do tải máy khác nhau lúc đo.

Ở 10 Hz, `scan_to_map` cộng với định vị (a) (≈ 11–13 ms khi máy rảnh, DINH_VI_LIDAR mục 5) nằm trong 100 ms của một vòng
trên máy bàn. **Laptop RTX 3050 Ti: CHƯA ĐO.** Phần này chạy trên CPU, không dùng GPU.

### 3.7. Kiểm đột biến và giới hạn

**Kiểm đột biến** (chạy lại đêm 24/09/2026 với 32 test). Mỗi đột biến sửa một chỗ của `scan_odometry.py` trên một
bản sao trong thư mục tạm (repo không bị sửa; thư mục `datasets` của bản sao trỏ tới dữ liệu thật để test DROW không bị
bỏ qua), rồi chạy lại toàn bộ `tests/test_scan_odometry.py`. Đột biến đối chứng (ném lỗi ở đầu `update`) làm 22 test hỏng
và 1 lỗi, tức bộ chạy thử hoạt động. Kết quả: **34/36 đột biến làm ít nhất một test hỏng**; 1–18 là danh sách cũ, 19–25
là các cổng mà agent kiểm tra thấy chưa có test, 26–36 là các chỗ sửa đêm 24/09/2026.

| # | Đột biến | Test bắt (tên rút gọn) |
|---|---|---|
| 1 | Bỏ lọc khoảng cách điểm kề | `dense_points_drop_sparse…`, `featureless_corridor…` |
| 2 | Bỏ lề tầm khớp | `dense_points_drop_sparse…` (lần chạy đầu 24/09 sống sót; đã thêm tường vuông góc ở 7,5 m vào test) |
| 3 | Không bao giờ báo suy biến theo pháp tuyến | `featureless_corridor…`, `nearly_featureless_corridor…`, `degenerate_flag_from_small_pillars…` |
| 4 | Báo suy biến nhưng không có số hạng khóa | cùng ba test trên |
| 5 | Bỏ mô hình vận tốc không đổi | 10 test, gồm `constant_velocity_prediction…` |
| 6 | Lạc mà vẫn ngoại suy vận tốc | `lost_tracker_stops_extrapolating` |
| 7 | Vòng FAILED vẫn thêm vào bản đồ | `failed_scan_uses_the_prediction…`, `velocity_after_recapture…`, `new_object_in_known_free_space…` |
| 8 | `scan_to_map` thêm khung khóa mỗi vòng | 7 test, gồm `scan_to_map_tracks_a_known_car_trajectory…` |
| 9 | `scan_to_scan` dùng bản đồ bền | `static_sensor…`, `matching_filters…`, `companion_moving…` |
| 10 | `yaw_gain` tính từng bước | `yaw_gain_is_taken_over_windows…` |
| 11 | Bỏ số hạng kéo về dự đoán | `nearly_featureless_corridor…`, `new_object_in_known_free_space…` (trước đây chỉ bị bắt nhờ một vòng FAILED `window_edge` ngẫu nhiên của seed 14, theo agent kiểm tra; chưa xem kỹ vì sao hai test này bắt) |
| 12 | Không tìm lại khi đỉnh ở mép cửa sổ | 5 test, gồm `constant_velocity_prediction…` |
| 13 | Không nới lưới | `map_grows_when_the_sensor_leaves…` |
| 14 | Bỏ ngưỡng tỉ lệ khớp | `failed_scan_uses_the_prediction…` |
| 15 | So quỹ đạo không đưa về gốc chung | 5 test, gồm `scan_to_map_tracks…` và test DROW thật |
| 16 | Độ dốc trôi tĩnh không đổi sang "mỗi phút" | `static_drift_metrics_known_values` |
| 17 | `--workers` bị bỏ qua (chạy tuần tự) | **sống sót**: tùy chọn chỉ ảnh hưởng tốc độ; test kiểm chạy song song cho kết quả giống hệt chạy tuần tự, nên không phân biệt được |
| 18 | `--drow` không mở rộng thư mục | `cli_writes_trajectory_summary…` |
| 19 | Tắt cổng mâu thuẫn với bản đồ | `new_object_in_known_free_space…` |
| 20 | Tắt cổng mép cửa sổ | `peak_at_the_edge_of_the_widened_window…` |
| 21 | Tắt cổng `few_matched` | `small_patch_of_a_known_corner…` |
| 22 | Không báo suy biến theo độ lệch chuẩn | `loose_covariance_alone…` |
| 23 | Không xóa bộ đếm FAILED khi có vòng tốt | `lost_needs_consecutive_failures` |
| 24 | Kiểm từng điểm ở tư thế rời rạc thay vì tư thế đã tinh chỉnh | `new_object_in_known_free_space…`, `peak_at_the_edge…` |
| 25 | Bỏ ngưỡng số pháp tuyến tối thiểu | `few_surface_normals_do_not_trigger…` |
| 26 | Khóa cứng lại (σ 2 mm) | `degenerate_flag_from_small_pillars…`, test DROW thật `10-34-20-c` |
| 27 | Mép cửa sổ chỉ dọc trục vẫn tính là mép | `featureless_corridor…`, `nearly_featureless_corridor…` |
| 28 | Khóa gần như không kéo (σ 1 km) | **sống sót**: không test nào ghim độ mạnh của khóa. Đo bằng script tạm (hành lang trơn, nhiễu 1 cm, 41 seed): khóa mềm tốt hơn không kéo ở trung vị (0,15 so với 0,36 m) nhưng từng seed thì lẫn lộn, nên chưa viết được test tất định đáng tin; trên DROW, tắt hẳn phép kiểm cũng cho số gần như ngang (mục 3.4) |
| 29 | Không bỏ thành phần dọc trục của kết quả tìm | `featureless_corridor…` |
| 30 | Vận tốc lấy từ tư thế vòng trước (bản đầu) | `velocity_after_recapture…` |
| 31 | Tên tệp kết quả chỉ theo tên bản ghi (bản đầu) | `same_named_inputs_in_different_folders…` |
| 32 | `--mirror` không đảo góc C1 | `cli_c1_skip_seconds_and_mirror` |
| 33 | `--skip-seconds` bị bỏ qua | `cli_c1_skip_seconds_and_mirror` |
| 34 | Nội suy odometry thành lấy dòng gần nhất | `interpolate_odometry_known_values…`, `cli_writes_trajectory_summary…` |
| 35 | Không ghi lý do `edge_along_axis` | `featureless_corridor…` |
| 36 | Chia chuyển động theo dây cung (nhân thẳng với phần chia) | `scale_motion_is_the_constant_twist_fraction` |

**Giới hạn của (b):**
- Không có tham chiếu độc lập cho chuyển động thật của C1: chưa có bản ghi C1 nào khi cảm biến di chuyển.
- Trôi theo quãng đường (DROW: trung vị 2,2 % mỗi 5 m, cuối/quãng đường trung vị 4,1 %), không đóng vòng. Đã lạc thì
  không định vị lại: chạy hết chiều dài 9 chuỗi DROW dài thì 30,9 % số vòng FAILED ở bản sửa (bản đầu 56,4 %), phần lớn
  ở một chuỗi đông người.
- Hành lang và cảnh chỉ có mặt song song: dọc trục là "không biết" (được báo AMBIGUOUS); với khóa mềm, vận tốc dọc trục
  đi bộ ngẫu nhiên (mục 3.2). Cảnh có cột nhỏ bị báo suy biến nhưng vẫn bám được (hội trường tổng hợp, DROW).
- Đông người: FAILED nhiều (DROW), kể cả sau khi sửa. Trong sa bàn, người thao tác đứng gần có thể gây hiện tượng tương
  tự; CHƯA THỬ.
- Tư thế là của tâm quay LiDAR. Đổi sang tâm trục sau xe cần phép biến đổi gá LiDAR–xe: CHƯA ĐO.
- Mọi ngưỡng CHƯA CHỐT.

## 4. Phương án (c): thư viện SLAM có sẵn

**Kiểm offline được (máy bàn, tối 24/09/2026):**
- `pip list` của `.venv` và `.venv-train`: không có gói nào tên chứa slam, icp, open3d, ros, carto, breezy, kiss, gtsam,
  g2o, pcl; cũng không có scipy, numba;
- trên PATH không có `ros2`, `roscore`, `rosrun`, `colcon`, `catkin_make`;
- có Docker Desktop (lệnh `docker`) và WSL 2, nhưng WSL chỉ có bản phân phối `docker-desktop`, không có Ubuntu;
- **laptop nộp đồ án: chưa kiểm.**

Đợt làm việc này không được tải hay cài gì, nên **không thư viện nào được chạy thử**. Mọi cột dưới đây là **cần tra**.
Cột cuối là ghi nhớ của người viết, **CHƯA KIỂM**, chỉ để biết cần tra gì, **không dùng làm căn cứ**.

| Thư viện | Nền tảng / Windows | Đầu vào bắt buộc (odometry, IMU, dạng scan) | Giấy phép | Ghi nhớ CHƯA KIỂM (cần tra lại tại nguồn chính thức) |
|---|---|---|---|---|
| Cartographer (+ cartographer_ros) | cần tra | cần tra | cần tra | C++; thường chạy qua ROS; 2D có thể không cần IMU/odometry; có đóng vòng; nghi Apache-2.0; tình trạng bảo trì cần tra |
| slam_toolbox | cần tra | cần tra | cần tra | gói ROS 2 (có nhánh ROS 1); nghi cần khung odometry (TF `odom`); nghi LGPL-2.1 |
| Hector SLAM | cần tra | cần tra | cần tra | gói ROS 1; nghi không cần odometry nhưng cần LiDAR tần số cao; nghi BSD; ROS 1 đã hết hỗ trợ (cần tra) |
| GMapping (slam_gmapping, OpenSLAM) | cần tra | cần tra | cần tra | lọc hạt; nghi **bắt buộc có odometry**; phần lõi OpenSLAM nghi có giấy phép phi thương mại |
| BreezySLAM | cần tra | cần tra | cần tra | Python + phần mở rộng C (CoreSLAM/tinySLAM); odometry tùy chọn; nghi LGPL-3.0; chạy trên Windows cần tra |
| KISS-ICP | cần tra | cần tra | cần tra | odometry LiDAR (chủ yếu 3D), cài bằng pip; nghi MIT; không đóng vòng; dùng cho 2D cần tra |
| Khác: rf2o_laser_odometry, Karto/open_karto, iris_lama, csm (PL-ICP), Open3D (ICP), GTSAM (đồ thị tư thế) | cần tra | cần tra | cần tra | để tham khảo khi cần odometry laser hoặc tầng đóng vòng |

Tích hợp vào dự án, suy ra từ cấu trúc hiện tại (không phải kết quả thử):
- Thư viện chạy qua ROS/Linux cần thêm WSL 2 + Ubuntu + ROS (chưa có) hoặc Docker.
- LiDAR C1 đang đọc qua cổng COM trong Windows (`lidar/rplidar_c1.py`), số cổng đặt ở `configs/thiet_bi.json`: COM3 trên
  máy bàn từ 29/09/2026 (máy bàn tới 25/09/2026 dùng COM4) ([chuyển máy](CHUYEN_MAY_BAN.md)). Muốn chạy thư viện trong WSL thì phải chuyển USB vào
  WSL (cần tra) hoặc gửi vòng quét qua mạng. Việc này thêm một tầng trễ và một điểm hỏng. Phải có giám sát dữ liệu cũ ở
  cả hai phía, theo nhánh giám sát ở kế hoạch mục 2 ("dữ liệu cũ → dừng").
- Thư viện nào bắt buộc odometry (nghi là GMapping, slam_toolbox) thì **chưa dùng được** cho tới khi có (d). Kế hoạch
  cấm gán odometry = 0 để báo đã có định vị.
- Giấy phép phải đối chiếu với khóa luận. Tệp [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md) chỉ xét dữ liệu, chưa xét phần
  mềm.

## 5. (d) Odometry bánh xe và IMU: cần gì

| Nguồn | Cho gì | Cần hiệu chuẩn / đo | Trạng thái 24/09/2026 |
|---|---|---|---|
| Encoder (MT6701 hoặc loại khác) trên trục động cơ/bánh | Tốc độ và quãng đường dọc thân xe | Tỉ số truyền, bán kính bánh (chạy 2–3 m đo thước), chiều quay, trượt trên mặt sa bàn | Chưa mua; vị trí gá CHƯA CHỐT |
| AS5600 + nam châm ở cơ cấu lái | Góc lái δ, suy ra tốc độ quay v·tan δ / L | Quan hệ trục cảm biến ↔ góc bánh (không tuyến tính?), chiều dài cơ sở L | Chưa mua; góc ở trục cảm biến chưa chắc bằng góc bánh (kế hoạch mục 1.1) |
| BNO085 | Tốc độ quay trục z (gyro); hướng tích phân | Độ lệch gyro khi đứng yên, trục gá; từ kế trong nhà không tin cậy (cần kiểm) | Chưa mua; kế hoạch mục 1.1: không coi là nguồn vị trí tuyệt đối độc lập |

- Giao thức xe đã có `speed_measured_mm_s`, `steer_measured_mrad`, `gyro_z_mrad_s` và `sample_time_ms`, telemetry mặc định
  20 Hz, mỗi số đo có cờ hợp lệ riêng ([GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 3, 8). Firmware chưa đọc cảm biến nào.
- **Thiếu:** chưa có bộ đếm quãng đường cộng dồn (ví dụ `distance_mm` u32 hoặc số xung encoder). Tích phân tốc độ 20 Hz
  sẽ mất quãng đường khi rơi khung. ĐỀ XUẤT – CHỜ CHỐT: thêm một trường như vậy khi tăng phiên bản giao thức.
- **Cách dùng với (b), khi có:** thay dự đoán vận tốc không đổi bằng chuyển động từ encoder + gyro giữa hai vòng quét.
  Có ích ở hai chỗ: (1) hành lang/mặt song song **thật sự** không có gì ràng buộc dọc trục (tổng hợp, nhiễu 1 cm:
  khóa mềm lệch dọc trục > 0,5 m ở 14/41 seed sau 60 vòng), khi đó tiên nghiệm dọc trục bám theo quãng đường đo được
  thay vì theo vận tốc ước lượng từ chính các vòng suy biến; (2) khi vòng
  quét FAILED (đám đông, bị che), chạy theo odometry bánh xe thay vì ngoại suy, nên dễ bắt lại hơn. Bản trước của tài
  liệu này nói (d) "giải quyết đúng điểm yếu lớn nhất theo DROW kiểu hỏng 1"; sai: kiểu hỏng 1 chủ yếu do khóa cứng
  (mục 3.3, phát hiện 5), đã sửa mà không cần (d). **Chưa viết:** `ScanOdometry.update` chưa nhận dự đoán từ ngoài.
- **Kiểm dấu miễn phí:** khi có gyro, `yaw_gain` giữa khớp scan và gyro phải ≈ +1. Nếu ≈ −1 thì dấu góc LiDAR bị đảo:
  test tổng hợp cho < −0,9 khi đảo dấu.

## 6. Bảng so sánh

| Tiêu chí | (a) Bản đồ tĩnh + định vị lại | (b) `scan_to_map` | (a) + (b) | (c) Thư viện ngoài | + (d) khi có |
|---|---|---|---|---|---|
| Chạy được ngay trên Windows bằng `.venv` | Có (offline) | Có (offline) | Có (offline), chưa ghép | Không (chưa cài) | — |
| Trôi theo thời gian khi đứng yên | Không (theo thiết kế) | Không (C1 o03: 0,6 mm/phút) | Không | cần tra | — |
| Trôi theo quãng đường | Không (mỗi vòng đặt lên bản đồ cố định) | Có: DROW trung vị 2,2 %/5 m (bản đầu 2,7 %) | (a) chặn trôi | cần tra | giảm trôi dọc trục của (b) ở cảnh suy biến |
| Cần bản đồ trước | Có | Không | Có | Thường không (SLAM) | — |
| Cần tư thế ban đầu | Có (hoặc tìm toàn bản đồ 0,5–6 s) | Không (gốc = vòng đầu) | Có | cần tra | — |
| Hành lang / mặt song song | AMBIGUOUS (`second_peak`, `degenerate`) | AMBIGUOUS + tiên nghiệm mềm theo dự đoán; dọc trục là "không biết", có thể trôi (mục 3.2) | Báo không chắc | cần tra | Cho dọc trục theo quãng đường đo được |
| Người/vật mới | `conflicts_with_map` → FAILED | FAILED khi tỉ lệ khớp < 0,5 (khi đó mâu thuẫn > 0,5 chỉ thêm lý do, mục 3.1 bước 6); DROW 2,8 % vòng FAILED, chủ yếu ở chuỗi đông người | Hai phép kiểm | cần tra | Chạy qua được khi FAILED ngắn |
| Đóng vòng / định vị lại khi lạc | Có (tìm toàn bản đồ) | Không (DROW 9 chuỗi dài: 30,9 % vòng FAILED, bản đầu 56,4 %) | (a) làm việc này | Tùy thư viện (cần tra) | — |
| Tham chiếu độc lập | Chưa có | Chưa có (C1 chưa di chuyển) | Chưa có | Chưa có | — |
| Đầu vào ngoài LiDAR | Không | Không | Không | cần tra (GMapping nghi bắt buộc odometry) | Encoder, AS5600, BNO085 |
| Rủi ro tích hợp | Thấp (đã có mã, test) | Thấp (đã có mã, test) | Trung bình (chưa ghép, chưa nối phiên) | Cao (ROS/Linux, cầu nối, giấy phép) | Trung bình (phần cứng, hiệu chuẩn) |

*(Cập nhật 02/10/2026: cột (a) + (b) — nay đã ghép (`lidar/pose_estimator.py`) và nối vào phiên đỗ xe
(`application/lidar_pose_source.py`), nên "chưa ghép" và "chưa nối phiên" ở bảng trên không còn đúng; mới kiểm ở mức MP
và trên bản ghi C1 đứng yên, chưa thử trên xe; [NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md).)*

## 7. Đề xuất cho V1: người dùng giao làm theo đề xuất ngày 02/10/2026 (ngưỡng vẫn ĐỀ XUẤT – CHỜ CHỐT)

*(Cập nhật 02/10/2026: người dùng giao quyết định 02/10/2026 ('làm hết'), theo đề xuất dưới đây; phần đã làm và các
ngưỡng chọn ở [NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md). Tên mục trước ngày này là "Đề xuất cho V1: ĐỀ XUẤT – CHỜ
CHỐT"; nội dung dưới đây giữ như ngày 24/09/2026, kèm ghi chú có ngày.)*

**Đề xuất.**

1. **Bản đồ:** trước mỗi buổi chạy, đặt C1 (đã gá trên xe) ở 3–5 vị trí trong sa bàn và ghi mỗi vị trí 10–15 s. Ghép
   thành một bản đồ tĩnh. Tư thế của các chỗ đặt lấy từ (b) khi dời C1 chậm giữa các chỗ, hoặc đo bằng thước. Công cụ
   ghép nhiều chỗ đặt **chưa viết** *(02/10/2026: đã viết, `lidar/map_builder.py`)*: `occupancy.py` hiện chỉ nhận một
   tư thế cố định hoặc odometry DROW. Bản đồ cố định
   trong suốt lượt chạy; vật mới đi vào costmap vật cản, không đi vào bản đồ định vị.
2. **Định vị mỗi vòng (10 Hz):** dùng (a), `localize` với cửa sổ quanh tư thế dự đoán. Chỉ tư thế OK mới được dùng cho
   lập đường và điều khiển.
3. **Dự đoán và giám sát:** dùng (b) `scan_to_map`. Nó cho tư thế dự đoán làm tâm cửa sổ của (a), và là phép kiểm chéo:
   nếu (a) và (b) lệch nhau quá ngưỡng (CHƯA CHỐT) hoặc (a) không OK quá N vòng liên tiếp thì dừng và đánh giá lại, đúng
   yêu cầu V1 "dữ liệu cần thiết không còn hợp lệ thì dừng". Vòng (b) báo AMBIGUOUS `degenerate` thì không dùng thành
   phần dọc trục của nó để kiểm chéo (mục 3.2: hành lang trơn tổng hợp, sau 6 s lệch dọc trục trung vị 0,15 m, xấu
   nhất 3,7 m). **Việc
   ghép (a) + (b) chưa viết.** *(02/10/2026: đã viết, `lidar/pose_estimator.py` + `application/lidar_pose_source.py`;
   dung sai kiểm chéo 4 cm + 3 % quãng đi, 2° + 2°/m; 2 vòng (a) không OK liên tiếp → POSE_LOST; ĐỀ XUẤT)*
4. **Khi có encoder/AS5600/BNO085:** thay vận tốc không đổi bằng odometry bánh xe + gyro trong (b) (mục 5), rồi đo lại.
   Đây là cải tiến cho cảnh suy biến thật và cho lúc bị che, **không** phải điều kiện để (b) chạy được: trên DROW, sau
   khi sửa lỗi khóa trục, (b) không có (d) vẫn cho 2,8 % vòng FAILED (mục 3.4).
5. **Không** đưa thư viện ngoài (c) vào V1. Nếu sau này cần SLAM thật (sa bàn lớn hơn tầm nhìn, cần đóng vòng), thử (c)
   trên WSL 2 sau khi tra đủ nền tảng, đầu vào và giấy phép.

**Điều kiện tiên quyết.** Nếu thiếu điều nào thì đề xuất trên không đứng:
- Sa bàn có đủ cấu trúc đứng trong mặt quét của C1 khi đã gá trên xe: vách, hộp, tường phòng ở độ cao mặt quét. Sa bàn
  phải không đối xứng và không phải một hành lang: tỉ số pháp tuyến phải cao (C1 trên bàn cho ≥ 0,42; ngưỡng suy biến
  0,04), và (a) không được báo `second_peak`. Trên sa bàn thật, tỉ lệ vòng (b) báo `degenerate` phải gần 0; **CHƯA
  ĐO** (chưa có bản ghi C1 di chuyển trong sa bàn).
- Cảnh cố định trong lượt chạy. Người thao tác đứng ngoài vùng quét hoặc ở vị trí đã tính.
- C1 gá cứng; phép biến đổi LiDAR ↔ tâm trục sau đo được.
- Dấu góc trái/phải đã chốt bằng lần đặt hộp bên trái (p04).
- Nguyên nhân +4,3° đã rõ. Nếu gốc góc đổi theo lần khởi động mô-tơ thì phải có bước hiệu chuẩn hướng mỗi lần bật.
- Tốc độ xe ≤ khoảng 0,3 m/s (≈ 3 cm/vòng, trong cửa sổ ±0,15 m). Nhanh hơn thì phải tăng cửa sổ và đo lại thời gian.
- Thời gian (a) + (b) trên laptop RTX 3050 Ti < 100 ms/vòng. **CHƯA ĐO.**

*(Cập nhật 02/10/2026: phép biến đổi LiDAR ↔ tâm trục sau (gá), dấu góc p04 và nguyên nhân +4,3° (DV-2), cùng định vị
tĩnh so với thước (DV-1), nay là cổng của nguồn tư thế LiDAR với bo thật trong `configs/dinh_vi_lidar_v0.json`
([NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md) mục 6). Chưa đạt điều nào, nên VehicleIO với bo thật luôn bị từ chối
(START_POSE_UNVERIFIED). Thời gian (a) + (b) trên laptop vẫn CHƯA ĐO.)*

**Không tuyên bố:** không nói V1 "đã có SLAM". Không nói (b) là odometry bánh xe. Không lấy độ nhất quán hay độ không
trôi khi đứng yên làm bằng chứng độ đúng.

## 8. Phép đo để xác nhận (cần người, dùng thiết bị đang có trừ khi ghi khác)

Lệnh ghi LiDAR theo [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md) mục 6; mỗi lệnh một dòng, thay `<ngày>` trước khi dán
vào cmd.exe.

1. **Bảy lần đặt hộp p01–p06, p08** (GIAI_DOAN_1_LIDAR mục 6). Mục đích: sai số khoảng cách so với thước (ngưỡng tạm ở đó
   là 30 mm) và dấu góc (p04 bên trái). Áp dụng cho mọi phương án.
2. **Hai phiên liên tiếp có khởi động lại mô-tơ, không chạm thiết bị** (DINH_VI_LIDAR mục 7, bước 1). Mục đích: gốc góc
   có đổi không, để giải thích +4,3°. Cùng hai bản ghi đó, chạy `scan_odometry` phải cho mỗi phiên đứng yên (như mục 3.5).
3. **3–6 vị trí và hướng đo bằng thước** (DINH_VI_LIDAR mục 7, bước 2). Đây là tham chiếu độc lập cho (a). ĐỀ XUẤT – CHỜ
   CHỐT: sai số ≤ 3 cm và ≤ 2° tại mọi điểm; con số cuối phải chốt theo khoảng hở ô đỗ ở bảng 16.2 của kế hoạch.
4. **Mới, cho (b): dời C1 bằng tay theo đường dán băng.**
   - Dán cố định C1 trên một tấm ván phẳng, đánh dấu tâm quay và vạch hướng.
   - Trên sàn dán băng: một đoạn thẳng 1,5 m, rẽ 90° rồi đi thêm 1 m, và 4–6 điểm mốc đo bằng thước (vị trí + hướng).
   - Đẩy tấm ván chậm, cỡ 0,1–0,3 m/s; dừng 3–5 s ở mỗi mốc; cuối cùng quay về mốc xuất phát.
   - Ghi bằng `.venv\Scripts\python.exe -X utf8 -m autopark.lidar.bench record --out runs/lidar_bench/<ngày> --name d10_di_chuyen_bang --seconds 60`.
     Cổng LiDAR lấy từ `configs/thiet_bi.json`; thêm `--port COMx` để ghi đè ([chuyển máy](CHUYEN_MAY_BAN.md)).
   - Chạy offline `scan_odometry` và `localize --track` rồi so với mốc: lệch ở từng mốc, lệch khi quay về gốc, trôi theo m.
   - Đếm vòng AMBIGUOUS `degenerate` (và `edge_along_axis`): ở sa bàn đủ cấu trúc phải gần 0; nếu không, dọc trục của
     (b) ở các vòng đó là "không biết" (mục 3.2) và điều kiện tiên quyết ở mục 7 không đạt.
   - ĐỀ XUẤT – CHỜ CHỐT cho (b) trên quãng ≤ 3 m: ≤ 2 % quãng đường, ≤ 1°/m, và không vòng FAILED khi không có người trong
     vùng quét.
   - **CHƯA THỬ.** Ván trượt tay có rung; kế hoạch mục 5 bước 4 lưu ý không kết luận SLAM sai từ dữ liệu rung lắc.
5. **Khi có xe (giai đoạn 7–8):** chạy vòng kín quanh sa bàn, dừng ở mốc đo bằng thước. So (a), (b) và (d) với mốc, và
   so với nhau.

## 9. Lệnh chạy lại (trong `autopark`, mỗi lệnh một dòng, dán được vào cmd.exe; thay `<...>` bằng thư mục thật)

```
.venv\Scripts\python.exe -X utf8 -m autopark.lidar.scan_odometry --recording runs/rig_recordings/o03_20260924/lidar/part_0000.npz --skip-seconds 3 --mode both --out <thư mục>
.venv\Scripts\python.exe -X utf8 -m autopark.lidar.scan_odometry --recording runs/lidar_bench/20260922/p07_nen_phong.npz runs/lidar_bench/20260922/live_headless.npz runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.npz runs/may_moi_20260924_may_ban/lidar/l01_tinh.npz runs/may_moi_20260924_toi/lidar/l01_tinh.npz --skip-seconds 3 --mode both --out <thư mục>
.venv\Scripts\python.exe -X utf8 -m autopark.lidar.scan_odometry --drow datasets/drow/DROWv2-data/val datasets/drow/DROWv2-data/test --limit 3000 --mode both --workers 8 --out <thư mục>
.venv\Scripts\python.exe -X utf8 -m autopark.lidar.scan_odometry --drow datasets/drow/DROWv2-data/val datasets/drow/DROWv2-data/test --limit 3000 --min-normal-ratio 0 --workers 8 --out <thư mục>
.venv\Scripts\python.exe -X utf8 -m pytest tests/test_scan_odometry.py
```

- `--drow` nhận thư mục vì cmd.exe không tự mở rộng `*`.
- Kết quả: `odometry.json` (cấu hình, tóm tắt, so sánh), một `.csv` mỗi vòng và một `.png` cho mỗi bản ghi và chế độ.
  Hai bản ghi cùng tên ở hai thư mục (hai `l01_tinh.npz` ở lệnh thứ hai, hay các `part_0000.npz` của bàn thử) thì tên
  tệp kết quả có thêm thư mục cha, ví dụ `may_moi_20260924_toi__lidar__l01_tinh__scan_to_map.csv`; bản đầu 24/09/2026
  ghi đè tệp của nhau. Cùng một tệp đưa hai lần thì báo lỗi.
- `--min-normal-ratio 0` tắt phép kiểm suy biến theo pháp tuyến (và khóa trục), chỉ để so sánh; `--lock-sigma` đổi σ
  của tiên nghiệm dọc trục.
- Lệnh chạy chuỗi DROW dài hết chiều dài: như lệnh DROW ở trên nhưng liệt kê 9 tệp `.bag.csv` (tên ở mục 3.4), bỏ
  `--limit`, thêm `--mode scan_to_map` (tệp JSON bằng chứng ghi đủ dòng lệnh).
- Đêm 24/09/2026 các lệnh trên ghi vào thư mục tạm của phiên làm việc, không vào `runs/`. Bản rút gọn ở
  `docs/evidence/lidar/odometry_khop_scan_*`, làm bằng một script tạm không lưu trong repo; tệp JSON ghi dòng lệnh đã chạy
  và mã băm SHA-256 của `scan_odometry.py` lúc chạy.

## 10. Còn mở

- Chọn phương án cho V1: **người dùng quyết định** (TONG_HOP mục 5.1). Tài liệu này chỉ đề xuất. *(02/10/2026: người
  dùng giao làm theo đề xuất mục 7)*
- Chưa viết: ghép (a) + (b) thành một nguồn tư thế; nối vào phiên đỗ xe thay cho tư thế lý tưởng của mô phỏng; công cụ
  dựng bản đồ từ nhiều chỗ đặt; `ScanOdometry.update` nhận dự đoán từ odometry bánh xe; định vị lại toàn cục khi (b) lạc.
  *(Cập nhật 02/10/2026: đã viết ghép (a) + (b), nối vào phiên, công cụ dựng bản đồ nhiều chỗ đặt, tìm toàn cục lúc khởi
  tạo (chỉ ngoài lần chạy); xem [NGUON_TU_THE_LIDAR.md](NGUON_TU_THE_LIDAR.md). Còn thiếu: `ScanOdometry.update` nhận dự
  đoán từ odometry bánh xe.)*
- Chưa có bản ghi C1 di chuyển, chưa có tham chiếu độc lập, chưa đo trên laptop.
- (c): mọi yêu cầu **cần tra** tại nguồn chính thức trước khi cân nhắc.
- Giao thức xe: ĐỀ XUẤT thêm bộ đếm quãng đường cộng dồn (mục 5).
- Kiểu hỏng 3 trên DROW (`11-01-30`: khớp scan tự tin nhưng khác odometry) chưa rõ nguyên nhân.
- Phát hiện suy biến: khóa mềm σ 3 cm là **ĐỀ XUẤT – CHỜ CHỐT**, mới chọn trên DROW và cảnh tổng hợp. Trên DROW nó
  gần như ngang với tắt hẳn phép kiểm; ở hành lang trơn tổng hợp, vận tốc dọc trục đi bộ ngẫu nhiên (mục 3.2). Chưa
  làm: không cập nhật (hoặc lọc thông thấp) thành phần vận tốc dọc trục từ vòng suy biến, phép kiểm dùng cả vật nhỏ
  (ví dụ đếm điểm nằm ngoài các mặt song song), khóa có điều kiện, hay σ theo tốc độ. Mọi phương án phải chạy lại cả
  bảng 3.000 vòng lẫn bảng chạy hết chiều dài, và cả hai cảnh tổng hợp (hội trường cột nhỏ giảm tốc, hành lang trơn).
  Không test nào ghim độ mạnh của khóa (đột biến M28 sống sót, mục 3.7).
- Vận tốc dự đoán tính theo số vòng, không theo thời gian: vòng bị rơi trước `update` thì vẫn sai (mục 3.3, phát hiện 6).
  *(02/10/2026: có `velocity_per="second"`, mục 3.3)*
- DROW sau khi sửa, **CHƯA XEM KỸ**: các vòng FAILED `window_edge` lẻ ở cảnh không suy biến (mục 3.4, kiểu hỏng 4); tỉ
  lệ bước 1,84 của `13-47-42` khi chạy hết chiều dài; `13-35-21` chạy hết chiều dài FAILED nhiều hơn bản đầu (1.028 so
  với 889).

## Ghi công dữ liệu

Kết quả ở mục 3.4 và ảnh `odometry_khop_scan_drow_*` dùng **DROW v2** (giấy phép MIT, yêu cầu trích cả hai bài):

> Beyer*, L., Hermans*, A., Leibe, B. (2017). DROW: Real-Time Deep Learning-Based Wheelchair Detection in 2-D Range
> Data. IEEE Robotics and Automation Letters, 2(2), 585-592.
>
> Beyer, L., Hermans, A., Linder T., Arras O.K., Leibe, B. (2018). Deep Person Detection in 2D Range Data. IEEE Robotics
> and Automation Letters, 3(3), 2726-2733.

Xem thêm [GIAY_PHEP_DU_LIEU.md](GIAY_PHEP_DU_LIEU.md) và `datasets/drow/LICENSE_source.txt`.
