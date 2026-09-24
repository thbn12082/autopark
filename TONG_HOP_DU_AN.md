# Tổng hợp dự án xe mô hình tự đỗ — theo mảng (24/09/2026)

> **Ghi công bắt buộc theo giấy phép dữ liệu:** nghiên cứu nhận thức trong dự án này được thực hiện với **Valeo WoodScape Dataset** (<https://woodscape.valeo.com>, [repo](https://github.com/valeoai/WoodScape)). Giới hạn sử dụng: [autopark/docs/GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md).

**Dành cho:** sinh viên làm khóa luận và giảng viên hướng dẫn. Đọc tệp này trước để biết dự án đang ở đâu, rồi theo link vào tài liệu chi tiết. Tệp này chỉ tóm tắt. Khi có chỗ khác nhau, tài liệu chi tiết và tệp đo trong `autopark/runs/` là nguồn gốc.

**Nguồn:** tài liệu trong repo sau đợt rà soát tài liệu chiều 24/09/2026 (cập nhật tối 24/09/2026 theo tám tài liệu mới
và mục 10.1–10.3 của GIAI_DOAN_2_BAN_THU.md, xem bảng dưới), mã nguồn và tệp đo. Mỗi con số dưới đây lấy
từ một tài liệu hoặc tệp đo được nêu kèm; số đếm của đợt rà soát kế hoạch ở mục 3 lưu ở
[autopark/docs/evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json](autopark/docs/evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json).
Chưa có số đo thì ghi "chưa đo"; người dùng chưa xác nhận thì ghi "chưa xác nhận".

**Đợt rà soát tài liệu 24/09/2026:** sáu agent đọc 26 tài liệu; mỗi phát hiện có một agent khác kiểm lại với mã, số đo và
git. Có 125 phát hiện, 112 được xác nhận và đã sửa tại chỗ, bằng ghi chú có ngày chứ không viết lại lịch sử. Những chỗ cũ
đáng chú ý đã sửa:

- Bảng 17.4 của kế hoạch nay có trạng thái cho mọi giai đoạn; trước đó giai đoạn 4, 6, 7, 8, 9, 10 ghi "Chưa cập nhật".
- Vai trò hai máy theo xác nhận của người dùng (24/09): máy bàn i9 là máy phát triển chính, laptop RTX 3050 Ti là máy mang đi nộp đồ án; mọi tài liệu đã ghi theo đó.
- Thêm phần kiểm lại LiDAR ngày 24/09 ([GIAI_DOAN_1_LIDAR.md](autopark/docs/GIAI_DOAN_1_LIDAR.md) mục 3b).
- Giờ và số lần rút/cắm camera ngày 23/09 ghi đúng theo mục 4.5 của GIAI_DOAN_1_CAMERA.md.
- `CameraCalibration.from_dict` đã đọc `theta_max_deg`; giao diện hiệu chuẩn đã mở camera thật một lần.
- GAN_NHAN_SA_BAN.md: bỏ câu nhầm "khởi tạo từ trọng số ImageNet" (trainer không có tùy chọn đó).
- Chỗ nào còn để ngỏ thì ghi ở mục 5 (việc cần quyết định) của tệp này.

**Cập nhật tối 24/09/2026.** Sau đợt rà soát trên, có bảy việc phần mềm mới, mỗi việc một tài liệu. Tất cả **chưa commit**
(nằm trên HEAD `2bd37b6`). Chỉ việc 1, 2 và 4 có phiên đo mới trên thiết bị thật, đều trên máy bàn tối 24/09. Việc 5 chạy offline trên bản ghi
LiDAR thật có sẵn (22/09 và 24/09), không mở thiết bị. Chưa việc nào chạy trên laptop RTX 3050 Ti (máy nộp đồ án).

| # | Việc | Mức bằng chứng | Tài liệu | Mục ở tệp này |
|---:|---|---|---|---|
| 1 | Quy tắc chờ theo nhịp **của chính từng camera**, thay ngưỡng chung theo camera nhanh nhất | mô phỏng + test; **đo lại trên máy bàn** (o01, o02) | [GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md) mục 10.1–10.3 | 4.5 |
| 2 | Làm nóng AI cho mọi cỡ lô (lô đầu của mỗi cỡ 4/3/2/1 ảnh mất 1,2–1,7 s) | đo trên máy bàn (o06, o07) | GIAI_DOAN_2_BAN_THU.md mục 10.3 | 4.2, 4.5 |
| 3 | BEV chiếm chỗ từ AI nhiều camera | rig tổng hợp + một ảnh WoodScape *(sửa muộn tối 24/09/2026: thêm một lần ba ảnh khác thời điểm `00000_FV`, `00028_RV`, `00140_MVL`, chỉ thử luồng hợp nhất, có lỗi ROI ở ảnh MVL chưa sửa; BEV.md mục 6)*; **chưa chạy trên camera dự án** | [BEV.md](autopark/docs/BEV.md) | 4.12 |
| 4 | Ghi và phát lại phiên bàn thử (bốn camera + LiDAR) | test với nguồn giả; **một phiên thật 60 s** trên máy bàn | [GHI_PHAT_LAI_BAN_THU.md](autopark/docs/GHI_PHAT_LAI_BAN_THU.md) | 4.11 |
| 5 | Định vị LiDAR trên bản đồ tĩnh (khớp scan, không phải SLAM) | dữ liệu tổng hợp; chạy offline trên bản ghi 22/09 và 24/09; **chưa có tham chiếu độc lập** | [DINH_VI_LIDAR.md](autopark/docs/DINH_VI_LIDAR.md) | 4.3 |
| 6 | Nối `VehicleIO` vào phiên đỗ xe; chế độ quan sát | **chỉ mô phỏng** và cổng serial giả; một khoảng trống an toàn đã biết, chưa sửa (mục 4.9) *(cập nhật muộn tối 24/09/2026: đã sửa, cũng chỉ kiểm trên mô phỏng và cổng serial giả, xem dưới bảng)* | [CHE_DO_QUAN_SAT.md](autopark/docs/CHE_DO_QUAN_SAT.md) | 4.9 |
| 7 | Bản nháp giai đoạn 4 và 6, phiếu kiểm kê MN300, dàn ý khóa luận | tài liệu; mọi số CHƯA ĐO, mọi kịch bản CHƯA THỬ | [GIAI_DOAN_4_CHUAN_BI.md](autopark/docs/GIAI_DOAN_4_CHUAN_BI.md), [mn300_inventory.md](autopark/docs/mn300_inventory.md), [GIAI_DOAN_6_CHUAN_BI.md](autopark/docs/GIAI_DOAN_6_CHUAN_BI.md), [DAN_Y_KHOA_LUAN.md](autopark/docs/DAN_Y_KHOA_LUAN.md) | 4.10, 4.13, 4.14 |

Chưa thay đổi: chưa nhận MN300, ESP32-S3; firmware C++ chưa biên dịch; AI chưa nối vào lập đường (chờ quyết định giấy phép
WoodScape); mặc định camera vẫn 640×480.

**Cập nhật muộn tối 24/09/2026 (sau 19:08, máy bàn, vẫn chưa commit, trên HEAD `2bd37b6`).** Thêm bốn điều sau bảng trên:

- **Khoảng trống an toàn của việc 6 đã sửa**, ở mức mô phỏng và cổng serial giả; chưa thử trên ESP32-S3 thật; còn một
  khoảng hở hẹp khi khung báo bo đã dừng chưa tới laptop, suy ra từ mã, chưa có test (mục 4.9).
  `tests/test_session_vehicle.py` nay 60 test, 60 đạt, không còn `xfail`.
- **`lidar.bench record` khi rút cáp giữa phiên** không còn ném lỗi lần hai lúc đóng cổng; phần đã ghi vẫn được lưu và
  phân tích. Chỉ kiểm bằng cổng serial giả; rút cáp C1 thật CHƯA THỬ (mục 4.3).
- **Chạy lại lệnh đo máy mới (`may_moi`) lúc 19:08 bằng mã mới** và lưu thành tham chiếu mới cho laptop,
  [tham_chieu_20260924_toi.json](autopark/docs/evidence/may_ban/tham_chieu_20260924_toi.json); tệp 15:25 giữ lại để đối
  chiếu (mục 4.5, 5.2). Lần này ở 720p **không** camera nào chạy ≈ 29 khung/s (mục 4.4).
- **Chạy lại toàn bộ bộ test** (máy bàn): `.venv` 895 đạt, 6 bỏ qua (các mô-đun chỉ chạy được với torch), 215 s;
  `.venv-train` (sáu mô-đun cần torch cùng `test_labels`, `test_rig_replay`, `test_multicam_rig`, `test_rig_app_ui`,
  `test_may_moi`) 248 đạt. Không còn test nào đánh dấu `xfail` trong `tests/`. Đây là số của cây làm việc chưa commit;
  sau khi commit phải chạy lại và ghi kèm mã commit.

---

## 1. Mục tiêu V1, phạm vi và mức bằng chứng

**V1 phải làm** ([kế hoạch v3.1](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 1.2): người dùng đặt đích trên giao diện. Xe tìm và chạy quỹ đạo tiến/lùi hợp với cơ cấu lái. LiDAR cho bản đồ và định vị; bốn camera cho nhận thức cục bộ. Khi có vật cản, hoặc dữ liệu cần thiết không còn hợp lệ, hệ thống dừng và đánh giá lại.

**Không bắt buộc trong V1:** nhận diện vạch đỗ, tự tìm ô đỗ, tự lái tới bãi, điều khiển end-to-end bằng mạng neural, MPC nâng cao, dự đoán chuyển động người, tái dựng 3D.

**Cấu hình giữ nguyên** (mục 1.1): xe MN300 Tank300 1/12, laptop xử lý chính, RPLIDAR C1, bốn camera USB, một ESP32-S3 điều khiển cấp thấp.

**Điều kiện hoàn thành V1** (mục 16.4): 10 điều kiện, **chưa điều kiện nào đạt** (24/09/2026). Các ngưỡng của mục 16.2 (camera, hình học, AI, định vị, điều khiển, tự đỗ, phản ứng lỗi) vẫn ở trạng thái "cần chốt".

Kế hoạch (mục 1.3) tách ba mức bằng chứng. Kết quả ở mức dưới không thay được mức trên:

| Mức | Đã có (24/09/2026) |
|---|---|
| Mô phỏng | Giai đoạn 0 ĐẠT sáu điều kiện chuyển bước (20/09). Xe ảo lập đường quanh vật thật do LiDAR đứng yên quét, và đỗ xong (22/09); phép thử "vật mới làm xe ảo dừng" mới chạy với nguồn quét kịch bản. `VehicleIO` mô phỏng giao thức xe (24/09). *(Tối 24/09:)* `VehicleIO` nối vào phiên đỗ xe, có chế độ quan sát, với bo mô phỏng và tư thế lý tưởng lấy từ mô phỏng. BEV từ AI mới kiểm trên rig tổng hợp và một ảnh WoodScape *(sửa muộn tối 24/09/2026: và một lần ba ảnh WoodScape khác thời điểm, chỉ thử luồng hợp nhất; mục 4.12)*. |
| Bàn thử trên máy bàn | LiDAR C1 và bốn camera USB nằm trên bàn, chưa gá. AI chạy trực tiếp trên bốn camera để đo thời gian và xem lớp tô (23–24/09). *(Tối 24/09:)* đo lại quy tắc chờ mới; ghi một phiên 60 s rồi phát lại. Định vị LiDAR chạy offline trên bản ghi có sẵn. Chưa có số đo nào trên laptop RTX 3050 Ti (máy nộp đồ án) *(sửa tối 24/09: bản trước viết "laptop sẽ đặt lên xe"; vai trò laptop theo xác nhận 24/09 là máy nộp đồ án)*. |
| Xe thật | Chưa có. Chưa nhận MN300, ESP32-S3 và phần nguồn/dừng. |

AI mới được chấm trên ảnh lưu sẵn của bộ dữ liệu công khai, chưa chấm trên ảnh sa bàn có nhãn.

## 2. Thiết bị

**Đã nhận** ([hardware_inventory.md](autopark/docs/hardware_inventory.md)):

| Thiết bị | Nhận | Tình trạng |
|---|---|---|
| RPLIDAR C1, adapter CP2102N, cổng COM4 | 22/09 | Đọc scan được trên máy bàn. Health OK ngày 22/09 và 24/09, cùng serial `f57ffc8b…`, firmware 1.2. Sai số khoảng cách so với thước **chưa đo**. Model in trên nhãn chưa ghi. |
| Bốn camera USB "HD Camera" (VID 1BCF / PID 0B09, không có serial) | 23/09 | 130° là số nhà bán, góc nhìn thật **chưa đo**. Chưa gá, chưa hiệu chuẩn. Danh tính của camera là cổng hub nó cắm vào. |
| Hub UGREEN 4 cổng (chip Genesys Logic) | 23/09 | Cả bốn camera chung một nhánh USB 2.0. Hub chạy bus-powered trong mọi phiên ngày 23/09; thử nguồn ngoài **chưa làm**. Mã model chưa ghi. |

**Chưa nhận:** MN300, ESP32-S3, BNO085, VL53L1X, AS5600 + nam châm, encoder (MT6701 hoặc loại khác), bộ nguồn (UBEC hay XL4015 chưa chọn), cầu chì, nút E-stop LA38, phần tử ngắt động lực. *(Tối 24/09:)* phiếu kiểm kê MN300 đã soạn sẵn để điền khi nhận xe ([mn300_inventory.md](autopark/docs/mn300_inventory.md)); phiếu chưa chứa thông tin nào về xe thật.

**Máy tính đã dùng:**

| Máy | Dùng cho | Nguồn |
|---|---|---|
| Máy bàn i9-14900 + RTX 4000 Ada 20 GB, RAM 64 GB, Windows 11 | Huấn luyện AI (từ 21/09) và mọi số đo LiDAR, camera, bàn thử (22–24/09) | [HUAN_LUYEN.md](HUAN_LUYEN.md) đầu tệp |
| Laptop i7-12700H + RTX 3050 Ti Laptop 4 GB | Hồ sơ giai đoạn 0 (mô phỏng, 20/09); **máy mang đi nộp và trình diễn đồ án** (người dùng xác nhận 24/09). Chưa đo LiDAR, camera, AI trực tiếp trên máy này | [BAO_CAO_GIAI_DOAN_0.md](BAO_CAO_GIAI_DOAN_0.md) mục 10 |

**Chưa xác nhận:**

- **Số đo trên laptop nộp đồ án.** Mọi số hiệu năng đến nay là trên máy bàn. Laptop RTX 3050 Ti có ít VRAM hơn (4 GB so với 20 GB) và bộ điều khiển USB khác, nên thời gian AI và hiện tượng khung bị cắt phải đo lại trên nó; sơ đồ cổng USB của nó chưa có.
- Đường điều khiển laptop–ESP32 khi lên xe (USB mới là phương án thử trên bàn, kế hoạch mục 1.1).
- Hub có adapter nguồn ngoài dùng được hay không; chiều dài và loại dây camera.

## 3. Tiến độ theo 11 giai đoạn

Cột "Trạng thái" lấy từ bảng theo dõi của kế hoạch (mục 17.4, cập nhật 24/09). Bốn cột số là kết quả đợt rà soát kế hoạch ngày 24/09: mỗi việc trong kế hoạch được xếp vào một trong bốn loại. Bảng chi tiết của đợt rà soát (275 việc, trạng thái, bằng chứng và cái đang chặn từng việc) lưu ở [autopark/docs/evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json](autopark/docs/evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json); bảng 17.4 vẫn là hồ sơ chính thức của kế hoạch. Đây là số việc, không phải tỉ lệ hoàn thành (kế hoạch mục 1.3 không cho tự gán tỉ lệ hoàn thành). *Ghi chú tối 24/09/2026:* bốn cột số là của đợt rà soát chiều 24/09, **trước** bảy việc tối 24/09, và chưa đếm lại; phần in nghiêng ở cột trạng thái là thay đổi tối 24/09 (bảng 17.4 đã ghi theo).

| GĐ | Nội dung | Trạng thái (17.4) | Xong | Một phần | Chưa bắt đầu | Chờ thiết bị chưa mua | Cổng chuyển bước |
|---|---|---|---:|---:|---:|---:|---|
| 0 | Phần mềm, mô phỏng | ĐẠT (mô phỏng, 20/09) | 24 | 0 | 0 | 0 | ĐẠT ở mức mô phỏng ([GIAI_DOAN_0.md](autopark/docs/GIAI_DOAN_0.md)) |
| 1 | LiDAR + camera mẫu | ĐANG LÀM *(tối 24/09: có công cụ định vị LiDAR trên bản đồ tĩnh, chưa có tham chiếu độc lập)* | 11 | 17 | 2 | 0 | CHƯA ĐẠT ([gate_01.md](autopark/docs/gate_01.md)) |
| 2 | Bốn camera, BEV | ĐANG LÀM *(tối 24/09: quy tắc chờ theo nhịp riêng, đo lại trên máy bàn; ghi/phát lại phiên; BEV mới là phần mềm + rig tổng hợp)* | 6 | 14 | 10 | 2 | chưa đạt, chưa có biên bản |
| 3 | Hợp nhất trên bàn thử | ĐANG LÀM (phần mềm, chưa có IMU/ToF/ESP32) | 5 | 11 | 2 | 6 | chưa đạt |
| 4 | Đo đặc tính MN300 | ĐANG LÀM (phần "khi chưa có xe"; *tối 24/09: phiếu kiểm kê và bảng đo nháp, CHƯA ĐO*) | 0 | 2 | 2 | 19 | chưa đạt |
| 5 | ESP32-S3, điều khiển có phản hồi | ĐANG LÀM (phần "khi chưa đủ phần cứng"; *tối 24/09: `VehicleIO` nối vào phiên, chỉ mô phỏng*) | 3 | 7 | 0 | 15 | chưa đạt |
| 6 | Nguồn, dừng an toàn | ĐANG LÀM (phần "khi chưa có nguồn final"; *tối 24/09: nháp bảng tải, sơ đồ nguồn/dừng, 16 kịch bản lỗi CHƯA THỬ*) | 0 | 5 | 4 | 15 | chưa đạt |
| 7 | Chuyển cảm biến lên xe | CHƯA LÀM | 0 | 1 | 1 | 12 | chưa đạt |
| 8 | Hợp nhất trên xe chuyển động | ĐANG LÀM (phần "khi chưa thể chạy trên xe") | 1 | 7 | 1 | 7 | chưa đạt |
| 9 | Tự đỗ thật, xử lý vật cản | CHƯA LÀM phần chạy thật *(tối 24/09: chế độ quan sát có trong mô phỏng)* | 0 | 3 | 2 | 14 | chưa đạt |
| 10 | Đánh giá, khóa luận | ĐANG LÀM (phần "khi chưa đủ bộ xe"; *tối 24/09: dàn ý khóa luận nháp*) | 0 | 10 | 3 | 7 | chưa đạt |
| — | Các mục chung ngoài 11 giai đoạn (suy ra = tổng − 11 giai đoạn) | | 6 | 15 | 0 | 3 | |
| | **Tổng (275 việc)** | | **56** | **92** | **27** | **100** | |

Cổng 1 tới 10 chưa cổng nào đạt; mới có biên bản của cổng 1. Điều kiện V1: 0/10 đạt.

## 4. Nội dung theo mảng

Mỗi mảng có: trạng thái hiện hành, số liệu chính (kèm ngày), giới hạn và điều chưa kiểm, tài liệu chi tiết, việc tiếp theo.

### 4.1. Mô phỏng và lập đường (giai đoạn 0)

**Trạng thái:** ĐẠT sáu điều kiện chuyển bước ở mức mô phỏng (20/09/2026). Bộ test và replay được giữ làm kiểm thử hồi quy.

**Số liệu chính** (20/09, laptop i7-12700H):

- Pytest 220/220 đạt. Chiến dịch 2.880 trường hợp theo seed, 0 vi phạm bất biến.
- 240 phiên kín vòng: 25 COMPLETED, 185 STOPPED (dừng đúng logic, không tính là đỗ xong), 30 FAULT (cố tình chèn vật quá gần để phanh). 40/40 bài planner có đường hợp lệ và chạy xong.
- Coverage: 93,93 % dòng / 84,25 % nhánh trên 10 module cốt lõi; toàn package 52,52 % / 38,11 %.
- Năm phiên mẫu có video, log, replay khớp. Ví dụ phiên parking: COMPLETED, sai số vị trí cuối 8,92 mm.

**Giới hạn:** thông số xe trong `configs/vehicle_default.json` là giả định, chưa phải số đo MN300. Preview là rollout lý tưởng. Vật chèn quá gần có thể gây FAULT. Tìm đường trong thời hạn phụ thuộc tải CPU. Cờ dừng mô phỏng không chứng minh phanh hay E-stop thật.

**Tài liệu:** [BAO_CAO_GIAI_DOAN_0.md](BAO_CAO_GIAI_DOAN_0.md), [GIAI_DOAN_0.md](autopark/docs/GIAI_DOAN_0.md), [KIEM_THU_DO_BEN_GIAI_DOAN_0.md](autopark/docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md), [autopark/README.md](autopark/README.md).

**Tiếp theo:** khi có MN300, thay thông số giả định bằng số đo (giai đoạn 4) rồi chạy lại chiến dịch. *(Tối 24/09:)* bảng đo và cách đưa số đo vào cấu hình đã soạn sẵn (mục 4.13).

### 4.2. AI nhận thức, dữ liệu và giấy phép

**Trạng thái:** baseline L-RASPP + MobileNetV3-Large, hai lớp FREE / BLOCKED (255 = IGNORE). Checkpoint tham chiếu `runs/ai_woodscape_rtx4000_v1/best.pt` (21/09). Từ 23/09 mô hình chạy trực tiếp trên bốn camera của bàn thử, nhưng chỉ để đo thời gian và xem lớp tô. **Chưa nối vào costmap hay planner.** *(Tối 24/09:)* đã có mô-đun chiếu kết quả AI xuống sàn thành costmap BEV (mục 4.12), nhưng mô-đun chưa nối vào bàn thử, hợp nhất hay planner, và chưa chạy trên camera dự án.

**Số liệu chính** (máy bàn):

- WoodScape test giữ riêng, chấm một lần (21/09): mIoU 0,9692; 1,75 % pixel vật cản bị gọi là FREE. Ba seed (22/09): test 0,9693 ± 0,0001.
- Ngoài miền (22/09): ACDC thời tiết xấu mIoU 0,908, vật cản → FREE 4,42 % (ban đêm 8,38 %). RoadObstacle21 (vật lạ nhỏ, 30 ảnh): recall 68,3 %, vật cản → FREE 31,7 %.
- Ngưỡng 0,15, chọn trên val theo F2: vật cản → FREE còn 0,69 % (WoodScape test), 2,28 % (ACDC), 18,2 % (RoadObstacle21). Đổi lại báo động giả tăng, ví dụ WoodScape test 1,37 → 3,97 %.
- Thêm AVM-SS và ACDC (22–23/09; ba seed cho lượt nền, lượt trộn WoodScape + AVM và lượt trộn có trọng số lớp; AVM-SS riêng và lượt trộn ba bộ mỗi lượt một seed): không lượt nào vượt lượt nền trên hai tập chưa chạm. Trộn WoodScape + AVM làm vật cản → FREE trên ACDC tăng từ 4,1 ± 0,4 % lên 13,5 ± 2,8 %. Trọng số lớp không phải cách gỡ.
- Độ trễ một ảnh khi GPU rảnh (22/09): torch CUDA fp32 4,4 ms; onnxruntime CPU 7,6 ms. Trên bàn thử (23/09, u01): lô bốn ảnh 640×480 trung vị 16,4 ms. Tối 24/09 (o02, 120 s, cùng máy bàn): trung vị 12,1 ms, p95 14,5 ms, max 20,8 ms. Chưa kiểm vì sao thấp hơn u01 (tải máy lúc đo có thể khác; chưa so). *(Thêm muộn tối 24/09/2026:)* lần `may_moi` lúc 19:08: bước `ai` (một lô 4 ảnh 480p, 60 lô sau 5 lô khởi động) trung vị 10,4 ms, p95 11,4 ms, VRAM đỉnh 78 MB; trong bàn thử 480p 120 s, lô trung vị 13,2 ms.
- **Lô đầu của mỗi cỡ lô chậm** (đo tối 24/09 trên máy bàn, [GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md) mục 10.3): trong cùng một tiến trình, lô đầu 4 / 3 / 2 / 1 ảnh mất 1665 / 1444 / 1431 / 1265 ms, các lô sau 14–18 ms. Từ tối 24/09, bàn thử chạy trước một lô ảnh đen cho mỗi cỡ lô ngay sau khi nạp mô hình (`AIWorker.warm_up`, json ghi `ai.warm_up_ms`). Nhờ vậy AI không còn đứng ≈ 1,4 s khi một cỡ lô xuất hiện lần đầu giữa phiên; đổi lại AI sẵn sàng chậm hơn ≈ 4,2 s. Thời gian làm nóng trên laptop RTX 3050 Ti: **CHƯA ĐO**. *(Thêm muộn tối 24/09/2026:)* lần `may_moi` lúc 19:08 trên máy bàn ghi `ai.warm_up_ms` = 1482 / 1448 / 1553 / 1410 ms cho cỡ 4 / 3 / 2 / 1, tổng ≈ 5,9 s, tức AI sẵn sàng ≈ 6 s sau khi nạp mô hình.
- Ảnh camera thật đầu tiên (23/09, chưa có nhãn): lượt nền gọi BLOCKED 11 / 31 / 39 / 60 % pixel ở cổng 1–4 (ngưỡng 0,50). Nhìn bằng mắt, ở cổng 2–4 phần lớn vùng đó là thảm hoa văn, tức báo động giả. Chưa phải số đo so với nhãn.

**Dữ liệu:** danh mục 44 bộ/nhánh (20/09). Đã tải và kiểm AVM-SS (6.763 cặp), DROW v2 (464.023 scan), WoodScape (8.234 cặp), ACDC, RoadAnomaly21, RoadObstacle21. Các ZIP gốc đã được chuyển đi ngày 21/09; bản giải nén là bản duy nhất đã biết trên máy.

**Giấy phép** ([GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md), kiểm 22/09 và 24/09): điều khoản WoodScape cấm dùng mô hình huấn luyện trên nó để vận hành hoặc hỗ trợ vận hành phương tiện. Ngày 22/09 người làm khóa luận chọn cách hiểu: xe 1/12 trên sa bàn trong phòng thuộc "personal experimentation" và "academic research". **Valeo chưa xác nhận cách hiểu này.** AVM-SS không có giấy phép (tác giả giữ toàn quyền). ACDC chỉ cho mục đích phi thương mại, không có điều khoản về phương tiện. Giấy phép RoadObstacle21 chưa xác minh.

**Giới hạn:** chưa chấm trên ảnh sa bàn có nhãn. Split WoodScape chưa loại trừ rò rỉ bối cảnh. RoadAnomaly21 chưa chấm. Mô hình yếu về đêm, yếu với vật lạ nhỏ, không phân biệt vỉa hè với đường. Huấn luyện không tái lập từng bit trên GPU. Độ trễ chưa đo trên laptop RTX 3050 Ti (máy nộp đồ án). Khi phát lại một bản ghi, kết quả AI không trùng từng bit với lúc chạy trực tiếp vì ảnh đã mã hóa lại JPEG (mục 4.11).

**Tài liệu:** [HUAN_LUYEN.md](HUAN_LUYEN.md) phần I–III; [GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md); [GIAI_DOAN_1_CHUAN_BI.md](autopark/docs/GIAI_DOAN_1_CHUAN_BI.md) (ROI, costmap, ONNX); [DANH_MUC_DATASET.md](autopark/datasets/DANH_MUC_DATASET.md), [TAI_VA_KIEM_TRA.md](autopark/datasets/TAI_VA_KIEM_TRA.md).

**Tiếp theo:** chụp ảnh sa bàn ở độ cao thật, gán nhãn, dựng thêm tập chấm tô tay từ đầu, rồi chấm ba checkpoint ở hai ngưỡng 0,50 và 0,15 (HUAN_LUYEN.md mục 18). Chốt hướng giấy phép trước khi nối AI vào costmap/planner.

### 4.3. LiDAR RPLIDAR C1

**Trạng thái:** đọc scan, ghi/phát lại phiên, bản đồ lưới tĩnh, tất cả trên máy bàn. Theo gate 1: đọc scan ĐẠT (trên máy bàn), tạo map MỘT PHẦN, định vị CHƯA. *(Cập nhật tối 24/09/2026:)* đã có công cụ định vị từng vòng quét trên bản đồ tĩnh đã lưu ([DINH_VI_LIDAR.md](autopark/docs/DINH_VI_LIDAR.md)). Công cụ nhất quán trên bản ghi có sẵn nhưng **chưa có vị trí tham chiếu độc lập**, nên dòng "định vị" của gate 1 vẫn là CHƯA ĐẠT.

**Số liệu chính:**

- 22/09 (phiên p07, 17,8 s, không làm nóng): 10,09 Hz; trung vị 508 tia/vòng; 0 byte lệch trong 91.507 node; 34,6 % tia không phản hồi ở chỗ đặt đó; phản hồi 0,09–14,6 m; node đầu tới sau ≈ 2,2 s kể từ lệnh SCAN. Hai số đầu tính cả lúc mô-tơ khởi động.
- Bản đồ lưới tĩnh từ p07: 160 × 160 ô 5 cm, 5.657 ô FREE, 230 ô OCCUPIED. Ngày 24/09 nạp lại và ghi lại tệp `costmap.json` thật cho kết quả bằng nhau.
- **Kiểm lại 24/09** (phiên k01, `autopark/runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.*`, ghi 15 s sau 3 s làm nóng, LiDAR đã dời chỗ): cùng model, firmware 1.2, phần cứng 18 và cùng serial; health OK. 151 vòng; 0 lỗi đọc, 0 byte lệch, 0 vòng bị bỏ. Số gộp 9,98 Hz, trung vị 512 tia/vòng (492–552).
- Bỏ 3 s đầu mỗi bản ghi thì cả 22/09 và 24/09 đều ≈ 10,0 Hz, ≈ 510 tia/vòng (504–516). Chênh lệch giữa 10,09 và 9,98 Hz là do đoạn khởi động mô-tơ nằm trong bản ghi; chưa thấy dấu hiệu thiết bị thay đổi.
- Độ lặp lại khoảng cách giữa hai vòng liên tiếp, trên mặt tĩnh 0,2–4 m: trung vị chênh 1,0–1,5 mm, p90 4–8 mm (script tạm ngày 24/09, không lưu trong repo). Đây không phải sai số so với thước.
- Cộng bộ đếm driver của 26 phiên ghi 22–24/09: 33.932 vòng, 0 byte lệch, 0 vòng bị bỏ; 5 lần đóng vòng theo điểm góc (≈ 1/6.800 vòng). Ba phiên 10 phút trên bàn thử (s07, t09, u04): 6.006 / 6.005 / 6.006 vòng, 0 lỗi đọc, 0 vòng mất. Tối 24/09 trên bàn thử: o02 (120 s) 1.201 vòng, 10,008 Hz, 0 lỗi; o03 (60 s, có ghi phiên) 601 vòng, 10,0 Hz, 0 lỗi.

**Định vị trên bản đồ tĩnh** (24/09, chạy offline trên máy bàn, [DINH_VI_LIDAR.md](autopark/docs/DINH_VI_LIDAR.md)). Công cụ `lidar/localize.py` khớp từng vòng quét với lưới chiếm chỗ đã lưu, bằng nhánh-cận nhiều mức rồi tinh chỉnh cục bộ, và trả OK / AMBIGUOUS / FAILED kèm lý do. Đây **không phải SLAM**: bản đồ không được cập nhật, không có odometry.

- Trên dữ liệu tổng hợp (29 test): sai số 0,4–0,7 cm và 0,004–0,10° trên 6 tư thế của test.
- Trên bản ghi thật, bản đồ `map_p07` (22/09):
  - p07: 181/181 OK. Đây chính là dữ liệu dựng bản đồ, không độc lập.
  - live_headless (22/09, 2,5 phút sau p07, dự kiến cùng chỗ): 60/60 OK, vị trí lệch dưới 1 cm, nhưng hướng lệch ổn định **+4,3°**. Một phép kiểm không dùng bản đồ cũng cho +4,4°. Chưa phân biệt được thiết bị bị xoay nhẹ trên bàn hay gốc góc lệch giữa hai lần khởi động mô-tơ.
  - k01 (24/09, LiDAR đã dời chỗ): 151/151 FAILED, đúng như mong đợi. Tìm trên cả bản đồ, 31 vòng cho **cùng một** đỉnh sai, nên tư thế ổn định qua các vòng không chứng minh tư thế đúng.
- Thời gian mỗi vòng, cửa sổ mặc định, cảnh khớp: trung vị ≈ 11–13 ms trên máy bàn. Tìm trên cả bản đồ: 0,5–6 s mỗi vòng, chỉ hợp để chạy offline hoặc khởi tạo.
- Mọi ngưỡng chấp nhận là tạm, **CHƯA CHỐT**. Đây là số **nhất quán**, không phải sai số so với thực tế.

**Chưa kiểm / còn mở:**

- **Sai số khoảng cách so với thước chưa đo.** Cần 7 lần đặt hộp p01–p06 và p08 (GIAI_DOAN_1_LIDAR.md mục 6). Dấu góc trái/phải chưa xác minh bằng vật thật (mục 6b).
- Đỉnh khởi động 552 tia (k01), cao hơn 536 (p07) và 540 (live_headless). Mới có ba lần khởi động được ghi, chưa đủ để kết luận.
- Có tia rất gần (0,135–0,173 m), chất lượng thấp, ở hai vùng góc cố định (k01: −56…−52° và −30…−28° theo quy ước dự án), thấy cả ở chỗ đặt cũ. Nghi dây cáp, chưa kiểm.
- `bench` và `live_view` đóng dấu bằng `time.monotonic` (bước 15,6 ms trên Windows), nên số chu kỳ trong các bản ghi đó bị lượng tử hóa.
- Chưa rút cáp để xem `STALE_DATA` trên thiết bị thật. Chưa đo trên laptop RTX 3050 Ti (máy nộp đồ án). Chưa có SLAM/định vị. Chưa dùng chế độ DenseBoost. *(Cập nhật tối 24/09/2026:)* đã có định vị trên bản đồ tĩnh (ở trên), nhưng chưa có SLAM. Cũng chưa có tham chiếu độc lập và chưa thử khi cảm biến di chuyển. Bản rút gọn kết quả offline (ảnh overlay p07, live_headless, k01 và tệp tóm tắt [dinh_vi_tren_p07_20260924.json](autopark/docs/evidence/lidar/dinh_vi_tren_p07_20260924.json)) đã được chép vào `autopark/docs/evidence/lidar/` tối 24/09, chưa commit.
- *(Thêm muộn tối 24/09/2026)* **Xử lý rút cáp trong phần mềm, chỉ kiểm bằng cổng serial giả** (`tests/test_lidar_unplug.py`, 13 test, máy bàn): khi cổng nối tiếp lỗi, driver ném `LidarTransportError` (lớp con của `ScanReadError`); `fusion/demo.py` dừng xe ảo gọn với lý do "Mất kết nối LiDAR"; `lidar.bench record` sau 3 lỗi đọc thì dừng, `close()` trên cổng đã chết không còn ném lỗi lần hai, phần đã ghi vẫn được lưu và phân tích, in cảnh báo và thoát mã 1. Rút cáp C1 thật: **CHƯA THỬ** (vẫn là việc cần người, mục 5.2).
- Hướng lệch +4,3° giữa p07 và live_headless: chưa rõ nguyên nhân (xem ở trên). Nếu gốc góc đổi sau mỗi lần khởi động mô-tơ thì phải hiệu chuẩn lại hướng LiDAR so với xe mỗi lần bật.

**Tài liệu:** [GIAI_DOAN_1_LIDAR.md](autopark/docs/GIAI_DOAN_1_LIDAR.md) (mục 3, 3b, 6, 6b, 8), [DINH_VI_LIDAR.md](autopark/docs/DINH_VI_LIDAR.md), [hardware_inventory.md](autopark/docs/hardware_inventory.md), [gate_01.md](autopark/docs/gate_01.md).

**Tiếp theo:** phiên đặt hộp 7 lần (cần người); thử rút cáp; xác định vật ở hai vùng góc gần; chọn phương án SLAM/định vị và kiểm đầu vào của nó (mục 5.4). *(Tối 24/09:)* cùng buổi đặt hộp, làm hai phép thử cho định vị (DINH_VI_LIDAR.md mục 7): (1) ghi hai phiên liên tiếp không chạm thiết bị, khởi động lại mô-tơ giữa hai phiên, để biết gốc góc có đổi không; (2) dời C1 tới 3–6 vị trí và hướng đo bằng thước, rồi so với kết quả định vị.

### 4.4. Camera USB và khung MJPEG bị cắt

**Trạng thái:** bốn camera đã đo trên máy bàn (23–24/09). Từ 23/09 mặc định 640×480 MJPG. Bộ dò `truncated_rows` / `torn_bands` loại khung hỏng trước khi tới AI. Bộ dò còn bỏ sót khi bộ giải mã tô bằng màu phẳng, khi khung bị cắt giữa hàng khối cuối, hoặc khi dải xé bắt đầu cách mép phải dưới 64 điểm. Chưa có phép kiểm độc lập bằng byte MJPEG thô (GIAI_DOAN_2_BAN_THU.md mục 2.2).

**Số liệu chính:**

- Mode công bố: MJPG 640×480, 1280×720, 1920×1080, đều 30 fps. Đo được ≈ 23,85 khung/s ở phơi sáng tự động, nhịp xen kẽ ≈ 31 ms và ≈ 48 ms. Ép phơi sáng thủ công thì 29,3 khung/s nhưng ảnh gần đen. Cơ chế chưa xác định. *(Cập nhật tối 24/09/2026:)* không phải lúc nào cũng 23,85 khung/s ở phơi sáng tự động. **Có camera đã chạy ≈ 29 khung/s ở phơi sáng tự động, và camera nhanh không cố định một cổng** (bổ sung cổng 3 tối 24/09/2026; bản trước chỉ nêu cổng 1). Cổng 1: t05 (23/09, 640×480, 29,3), m02 lúc 15:25 và o01 tối 24/09 (1280×720, chỉ camera, máy bàn, 29,3 khung tốt/s, 0 khung bị cắt/xé; GIAI_DOAN_2_BAN_THU.md mục 10.1, 10.3); ở ba phiên này cổng 2–4 ≈ 23,85 khung/s. Cổng 3: s01–s07 (23/09, 480p/720p/1080p, 29,0–29,3) và t01, t02 (23/09, 720p, 28,9 / 29,0; GIAI_DOAN_2_BAN_THU.md mục 5); từ t03 cổng 3 về 23,85. Số FPS của loạt s và v2 gồm cả khung có thể bị cắt, vì đo trước khi có bộ dò. Mọi phiên nêu trên ghi `"exposure": null` (phơi sáng tự động) trong `.rig.json`. Chi tiết từng phiên: [hardware_inventory.md](autopark/docs/hardware_inventory.md) (dòng "FPS thật đo được"). Chưa biết khi nào và vì sao một camera chạy nhịp này: cùng ngày 24/09, ở w03/w04 (12:13–12:22, 720p) cổng 1 vẫn 23,85 khung/s; ở 480p (m01 lúc 15:25, o02 tối 24/09) cả bốn camera ≈ 23,85 khung/s. Vì vậy phần mềm không được giả định bốn camera cùng nhịp (mục 4.5). *(Cập nhật muộn tối 24/09/2026:)* o01 chạy lúc 17:56. Lần `may_moi` lúc 19:08 (720p chỉ camera, 30 s, cùng hub và chỗ đặt, `exposure: null`) thì **không** camera nào chạy ≈ 29: bốn cổng 23,83 / 23,87 / 23,87 / 23,87 khung/s. Tóm lại, camera chạy ≈ 29 khung/s thay đổi giữa các lần mở camera: cổng 3 ở s01–s07, t01, t02 (23/09); cổng 1 ở t05 (23/09) và lúc 15:25, 17:56 ngày 24/09; không cổng nào lúc 19:08. Nó không gắn với một cổng hay một camera cố định.
- Khung bị cắt khi chạy chung (23/09, camera nhìn thảm hoa văn): chạy một mình thì không camera nào bị cắt. Ở 720p/1080p với cả bốn camera, hai–ba camera bị cắt phần lớn khung (r04, r08, r09, r11). Với ba camera ở 720p, chỉ một camera bị cắt phần lớn khung (r03: cổng 1 97 %; r05: cổng 4 67 %). Ví dụ phiên u02 (720p, cùng LiDAR + AI, 60 s): cổng 1 và cổng 4 có 1.431 và 1.430 khung bị cắt, còn 0,0 khung tốt/s.
- 640×480, 18 phiên ngày 23/09: cổng 1 hỏng 1.418 / 31.142 khung (4,6 %), gần hết trong hai đợt 26,3 % và 36,2 %; cổng 2 và 3: 0; cổng 4: 6 khung. Nguyên nhân các đợt của cổng 1 chưa rõ.
- 24/09 (phiên w03, w04; 720p × 4, 60 s, camera nhìn chỗ tối): 0 khung bị cắt/xé. Đây thêm một dấu hiệu mức cắt phụ thuộc cảnh (kích thước JPEG), **không** phải bằng chứng 720p dùng được. Chiều và tối 24/09 cũng vậy (m02 lúc 15:25 và o01, 720p × 4, 30 s, chỉ camera, cảnh tối): 0 khung bị cắt/xé. *(Thêm muộn tối 24/09/2026:)* lần 19:08 (m02 của `may_moi` tối, cùng cảnh tối) cũng 0.
- Khung hỏng mà tới được AI thì vùng vân xám bị gọi gần hết là FREE. Số đo trên hai khung 720p của bộ ảnh 14:57 ngày 23/09, chụp trước khi có bộ lọc (cổng 1: 450.551 / 450.560 pixel của phần đáy ở ngưỡng 0,50). Đó là lỗi theo hướng không an toàn. Mới đo trên hai khung mà bộ dò bắt được; chưa đo trên khung thật sự lọt bộ dò.
- Sau khởi động lại máy (23/09), InstanceId theo cổng giữ nguyên nhưng index OpenCV đổi. Vì vậy mã chọn camera theo cổng hub.

**Chưa kiểm:** nguyên nhân khung bị cắt (giả thuyết băng thông USB 2.0 dùng chung qua hub, chưa chứng minh; chưa đọc được byte MJPEG thô); tách camera ra nhiều cổng gốc; nguồn ngoài cho hub; băng thông mỗi camera; đổi cổng camera; góc nhìn thật; độ nét ở độ cao dự kiến; độ trễ từ sự kiện thật tới máy (cần LED nháy); nhiệt CPU; mọi số trên laptop RTX 3050 Ti (máy nộp đồ án).

**Tài liệu:** [GIAI_DOAN_1_CAMERA.md](autopark/docs/GIAI_DOAN_1_CAMERA.md) (đính chính ở mục 4.6), [usb_topology.md](autopark/docs/usb_topology.md), [GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md) mục 2, [camera_modes.csv](autopark/docs/camera_modes.csv).

**Tiếp theo:** tách camera ra nhiều cổng gốc rồi chạy lại 720p với cảnh sáng, nhiều chi tiết; thử nguồn ngoài cho hub; đổi chỗ camera cổng 1 và cổng 2 để tách lỗi "camera" với lỗi "cổng".

### 4.5. Bàn thử bốn camera + LiDAR + AI và quy tắc không chờ camera chậm

**Trạng thái:** bốn camera, LiDAR và AI chạy chung ổn trên máy bàn ở 640×480 (23/09). Từ 24/09, AI không chờ camera chậm (mặc định bật). *(Cập nhật tối 24/09/2026:)* quy tắc chờ nay xét mỗi camera theo nhịp của chính nó, và đã đo lại trên máy bàn. AI được làm nóng cho mọi cỡ lô trước bộ ảnh đầu. Bàn thử ghi và phát lại được một phiên (mục 4.11). Mọi thay đổi này chưa commit.

**Số liệu chính** (23/09, loạt `autopark/runs/rig_bench/20260923_v3/`):

- u01 (120 s): 4 × 23,8–23,9 khung tốt/s, 0 khung hỏng. AI chấm 23,8 bộ/s; lô bốn ảnh trung vị 16,4 ms (mạng 11,6 ms). Kết quả AI có mặt 34,8 ms (trung vị) sau khi khung cũ nhất của bộ tới máy.
- u01: độ lệch trong bộ ảnh trung vị 15,0 ms, p95 24,1 ms. Điểm giữa vòng LiDAR sớm hơn mốc bộ ảnh ≈ 80 ms (trung vị). GPU trung bình 26 %, 41 → 46 °C.
- u04 (600 s): 6 khung hỏng (cổng 4). AI 23,1 bộ/s, 15,6 ms/lô. LiDAR 6.006 vòng, 0 vòng mất.

**Quy tắc không chờ, bản đầu** (trưa 24/09, GIAI_DOAN_2_BAN_THU.md mục 10; **đã thay tối 24/09**, xem dưới): khi một camera chưa có khung mới, bàn thử chờ tối đa L = max(60 ms; 1,5 × chu kỳ khung của camera nhanh nhất), tức ≈ 62 ms ở 24 khung/s, rồi ghép bộ không có camera đó. Tham số `--max-wait-ms` (0 = quy tắc cũ, chờ mọi camera).

- Năm phiên w01–w05 (12:13–12:22 ngày 24/09; ba phiên bật w01, w03, w05, hai phiên tắt w02, w04): ở ba phiên bật, 0 bộ thiếu camera khỏe trong 7.155 bộ. Số bộ/s bằng lúc tắt. *(Tối 24/09:)* kết luận này chỉ đúng khi bốn camera cùng nhịp; ở w01–w05 cả bốn đều 23,85 khung/s.
- Tuổi kết quả AI ≈ 37–42 ms khi bật, ≈ 62 ms khi tắt. Cơ chế chưa giải thích được, nên chưa coi là lợi ích.
- **Lợi ích chính chưa thấy trên phần cứng:** không phiên nào có camera chậm.
- Trong mô phỏng, khi pha từng camera trôi, mỗi cổng khỏe vẫn bị bỏ 0,2–2,7 % số bộ. Chưa sửa. *(Tối 24/09: xem quy tắc mới dưới đây.)*
- **Chỗ hỏng thấy trên phần cứng** (phiên m02 lúc 15:25 ngày 24/09, 720p chỉ camera, 30 s): cổng 1 chạy 29,3 khung/s, cổng 2–4 chạy 23,85 khung/s (mục 4.4). Vì ngưỡng và điều kiện ghép bộ tính theo camera nhanh nhất, bản đầu bỏ camera 24 khung/s **khỏe** ở 263 / 855 bộ. Ở 480p (m01, 120 s, bốn camera cùng nhịp) nó bỏ camera khỏe ở 3 / 2.861 bộ.

**Quy tắc chờ theo nhịp riêng** (tối 24/09, người dùng duyệt; GIAI_DOAN_2_BAN_THU.md mục 10.1–10.2; mã `autopark/video/multicam.py`):

- Mỗi camera có ngưỡng riêng L = max(60 ms; 1,5 × chu kỳ khung đo được của **chính nó**), ≈ 63 ms ở 24 khung/s. Camera bị bỏ khỏi bộ khi khung mới cũ nhất đã chờ quá L của nó, khi khung "đúng lượt" của nó trễ quá nửa chu kỳ của nó, khi khung đúng lượt tới mà hỏng, hoặc khi nó treo (không có lần tới nào trong 2,5 chu kỳ của nó).
- Camera khỏe mà chậm hơn **không** bị bỏ: nó định nhịp cả chuỗi, khung dư của camera nhanh không vào bộ nào. Hệ quả: một camera chậm cố định vẫn làm AI chậm theo. Quy tắc chỉ giúp khi một camera lỡ nhịp của chính nó.
- `.rig.json` ghi `policy.wait_rule = "own_cadence"` và `policy.wait_periods_of_own`; khóa cũ `wait_periods_of_fastest` vẫn được ghi để trình đọc cũ không hỏng. `--max-wait-ms 0` vẫn là quy tắc chờ mọi camera.
- Mô phỏng (đồng hồ giả, khoảng cách khung thật đo ngày 23/09; không phải số đo phần cứng): kịch bản 720p 29,3 + 23,85 khung/s: bỏ camera khỏe từ 12,4–18,3 % xuống 0–0,42 % số bộ (chỉ còn ở cổng 1, camera nhanh). Kịch bản nhịp 31/48 ms trôi pha: bỏ "chậm" 0 %, còn 2,1–2,5 % số bộ bị để dành để gom lại pha. Các hệ số 1,5, nửa chu kỳ, 2,5 và 15 % là lựa chọn thiết kế, **chưa đo** trên phần cứng.
- Vòng kiểm tra độc lập tối 24/09 tìm hai lỗi của bản này và đã sửa, cả hai tái hiện bằng đồng hồ giả (GIAI_DOAN_2_BAN_THU.md mục 10.2). Tần suất của lỗi thứ hai trên phần cứng: **CHƯA ĐO**.

**Đo lại trên phần cứng** (tối 24/09, máy bàn, cùng hub, cùng chỗ đặt camera như lúc 15:25; bản rút gọn trong git: [cho_nhip_rieng_ghi_phat_lai_20260924.json](autopark/docs/evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json); *sửa muộn tối 24/09/2026:* "trong git" chỉ có nghĩa là tệp nằm trong `autopark/docs/evidence/` chứ không trong `runs/` bị git-ignore; hiện tệp **chưa theo dõi, chưa commit**, laptop chưa có cho tới khi commit/push):

| Phiên | Cấu hình | Khung tốt/s cổng 1 / 2 / 3 / 4 | Bộ | Bộ bỏ camera khỏe | Độ lệch bộ trung vị / p95 / max (ms) |
|---|---|---|---:|---|---|
| m02 (15:25, bản đầu) | 720p chỉ camera, 30 s | 29,3 / 23,85 / 23,85 / 23,85 | 855 | 263 | 24,5 / 36,0 / 40,3 |
| o01 (nhịp riêng) | 720p chỉ camera, 30 s | 29,27 / 23,87 / 23,87 / 23,83 | 715 | **0** | 28,5 / 36,4 / 52,8 |
| m01 (15:25, bản đầu) | 480p + LiDAR + AI, 120 s | 23,85 cả bốn | 2.861 | 3 | 27,8 / 28,0 / 41,2 |
| o02 (nhịp riêng) | 480p + LiDAR + AI, 120 s | 23,85 cả bốn | 2.862 | **0** | 23,1 / 23,3 / 25,8 |
| m02 (19:08, `may_moi`, nhịp riêng; *thêm muộn tối 24/09*) | 720p chỉ camera, 30 s | 23,83 / 23,87 / 23,87 / 23,87 | 716 | 0 | 16,6 / 31,8 / 34,4 |
| m01 (19:08, `may_moi`, nhịp riêng; *thêm muộn tối 24/09*) | 480p + LiDAR + AI, 120 s | 23,85 / 23,85 / 23,85 / 23,84 | 2.861 | 0 | 29,1 / 30,1 / 33,9 |

- o01: 23,8 bộ/s; camera 24 khung/s định nhịp, 164 khung dư của cổng 1 không vào bộ nào. **Cái giá:** độ lệch trong bộ lớn hơn ở 720p (trung vị 28,5 so với 24,5 ms, max 52,8 so với 40,3 ms), như mô phỏng đã báo.
- o02: AI 23,85 bộ/s, một lô trung vị 12,1 ms (p95 14,5, max 20,8). LiDAR 10,008 Hz, 0 lỗi.
- Cả hai phiên 0 khung bị cắt/xé vì camera nhìn chỗ tối. Vì vậy **nhánh "bỏ camera lỡ nhịp" (camera có khung hỏng hay bị treo) mới chỉ kiểm bằng mô phỏng và test**, chưa thấy trên phần cứng. Đây **không** phải bằng chứng 720p dùng được.

**Chạy lại `may_moi` lúc 19:08 bằng mã mới** (*thêm muộn tối 24/09/2026*; máy bàn, cùng hub, cùng chỗ đặt, camera vẫn nhìn
chỗ tối; `runs/may_moi_20260924_toi/`, git-ignore; bản rút gọn trong `docs/evidence/`:
[tham_chieu_20260924_toi.json](autopark/docs/evidence/may_ban/tham_chieu_20260924_toi.json), chưa commit). Hai dòng 19:08
ở bảng trên. Tệp rút gọn không chứa độ lệch trong bộ; số độ lệch ở bảng đọc từ hai tệp `.rig.json` gốc.

- 480p + LiDAR + AI, 120 s: 0 khung hỏng, 0 bộ thiếu camera khỏe (lúc 15:25: 3), AI 23,85 bộ/s, lô trung vị 13,2 ms,
  LiDAR 10,01 Hz, 0 lỗi. Làm nóng AI 1482 / 1448 / 1553 / 1410 ms (mục 4.2).
- 720p chỉ camera, 30 s: lần này cả bốn camera ≈ 23,85 khung/s (mục 4.4), nên phiên này **không** thử lại tình huống hai
  nhịp khác nhau đã làm quy tắc cũ hỏng lúc 15:25. Số 0 bộ bỏ camera ở đây vì vậy không phải lần xác nhận thứ hai cho
  o01; bằng chứng cho tình huống đó vẫn chỉ là o01.
- Bước `ai` riêng của `may_moi` (một lô 4 ảnh, 60 lô sau 5 lô khởi động cỡ 4): trung vị 10,4 ms, p95 11,4 ms, VRAM đỉnh
  78 MB. Bước này tự khởi động, không phụ thuộc phần làm nóng mọi cỡ lô của bàn thử.

**Làm nóng AI cho mọi cỡ lô** (tối 24/09, mục 10.3): lô đầu mỗi cỡ 4 / 3 / 2 / 1 ảnh mất 1,2–1,7 s (mục 4.2). Lỗi này lộ ra khi phát lại (mục 4.11). Nếu một cỡ lô xuất hiện lần đầu giữa phiên thật, ví dụ hai camera cùng lỡ nhịp, AI sẽ đứng ≈ 1,4 s. Suy luận này **chưa kiểm** trên phiên thật: m01 có 3 lô thiếu camera mà lô chậm nhất chỉ 20,2 ms, giải thích có lý là lô đó rơi vào 5 s làm nóng. Sửa: `AIWorker.warm_up` (`autopark/rig/core.py`) chạy một lô ảnh đen cho mỗi cỡ lô ngay sau khi nạp mô hình; `rig.bench` chờ xong rồi mới tính 5 s làm nóng; json ghi `ai.warm_up_ms` (máy bàn: 1682 / 1444 / 1468 / 1283 ms). Phiên thật sau sửa, o07 (480p + LiDAR + AI, 30 s): 715 bộ, 0 bộ bỏ camera, 23,87 bộ/s, lô chậm nhất 18,3 ms. Laptop: **CHƯA ĐO**.

**Giới hạn:** mọi stamp là lúc dữ liệu tới máy, không phải lúc phơi sáng. Khi đo, một dự án khác chạy cùng máy (có ghi CPU cả máy). Nhiệt CPU không đọc được vì không có quyền admin. Lớp tô AI chỉ để nhìn. Chưa có BEV, chưa chiếu kết quả AI xuống sàn. *(Cập nhật tối 24/09/2026:)* đã có mô-đun BEV (mục 4.12), nhưng mô-đun chưa nối vào bàn thử và chưa chạy trên camera dự án.

**Tài liệu:** [GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md) (mục 3–4 số đo chính thức, mục 5–6 loạt cũ, mục 10 quy tắc không chờ, mục 10.1–10.2 quy tắc theo nhịp riêng, mục 10.3 đo lại tối 24/09 và làm nóng AI); [GHI_PHAT_LAI_BAN_THU.md](autopark/docs/GHI_PHAT_LAI_BAN_THU.md).

**Tiếp theo:** chạy một phiên có camera chậm thật, bật và tắt quy tắc; đo độ trễ bằng LED nháy; chạy lại `rig.bench` trên laptop RTX 3050 Ti (máy nộp đồ án). *(Tối 24/09:)* cách so hai quy tắc tốt hơn là **ghi** một phiên có camera lỡ nhịp thật (khung bị cắt/xé, thường ở 720p khi camera nhìn cảnh sáng, nhiều chi tiết), rồi phát lại cùng bản ghi với `--max-wait-ms 60` và `--max-wait-ms 0` (mục 4.11). Trên laptop cần đo thêm thời gian làm nóng AI.

### 4.6. Hiệu chuẩn camera

**Trạng thái:** công cụ có từ 24/09. **Chưa hiệu chuẩn camera nào; bảng chưa in.**

**Đã có:** bảng in sẵn A4 ô 20 mm và A3 ô 30 mm (`autopark/calibration/bang_in/`); hiệu chuẩn Kannala–Brandt bằng `cv2.fisheye`, luôn tinh chỉnh góc bằng `cornerSubPix`; giao diện chụp `ui/calib_app.py`. Tệp ra là `calibration/cam_p<cổng>.json`, chỉ chứa nội tham, mặc định ở mode 640×480.

**Số liệu** (ảnh tổng hợp dựng qua một camera đã biết): fx tìm được 351,03 so với 351,0 thật; RMS chiếu lại 0,071 px; sai lệch mô hình trung vị 0,05 px, lớn nhất 0,49 px ở góc ảnh (vùng ngoại suy). Giao diện đã mở camera thật cổng 2 một lần (24/09, ≈ 6 s, 0 khung hỏng) nhưng không chụp ảnh nào.

**Giới hạn:** các tiêu chí chấp nhận (RMS ≤ 0,5 px, ≥ 15 ảnh, phủ ≥ 70 % lưới…) chỉ là đề xuất. Chưa biết ống kính thật có khớp mô hình 4 hệ số không. Chưa có ngoại tham (`camera_rig_extrinsics.yaml`) và chưa có công cụ cho nó. `CameraCalibration.from_dict` chưa nạp thẳng được `cam_p*.json`. Chưa có mặt nạ ROI cho camera của dự án. *(Cập nhật tối 24/09/2026:)* có tệp ngoại tham `configs/rig/camera_rig_extrinsics_v0.json` (JSON vì hai môi trường không có thư viện YAML), nhưng mọi tư thế trong đó là **GIẢ ĐỊNH — CHƯA ĐO** (`"measured": false`), đặt tay cho một xe giả định 0,40 × 0,20 m; gán cổng → hướng CHƯA CHỐT. Bộ nạp `load_rig()` của BEV ghép `calibration/cam_p<cổng>.json` với tệp này và từ chối khi thiếu nội tham (mục 4.12). Công cụ đo ngoại tham: vẫn chưa có.

**Tài liệu:** [HIEU_CHUAN_CAMERA.md](autopark/docs/HIEU_CHUAN_CAMERA.md), [autopark/calibration/README.md](autopark/calibration/README.md).

**Tiếp theo:** in bảng đúng 100 %, đo cỡ ô bằng thước, chụp 20–30 ảnh mỗi camera, so K của bốn camera với nhau. Chọn cách đo ngoại tham khi có gá. Hiệu chuẩn nội tham là điều kiện đầu tiên để BEV chạy được trên camera dự án (BEV.md mục 8).

### 4.7. Gán nhãn ảnh sa bàn

**Trạng thái:** công cụ có từ 24/09. **Chưa gán nhãn ảnh thật nào.**

**Đã có:** nhập bộ ảnh do nút "Chụp bộ ảnh" của bàn thử ghi ra; nhãn nháp từ xác suất AI; cọ, đa giác, duyệt, loại; export ra cache cùng định dạng huấn luyện. Chỉ ảnh đã duyệt được vào cache. Split đóng băng theo phiên chụp (các bộ cách nhau ≤ 60 s là cùng phiên). `export --disjoint-from` giữ tập chấm tách rời tập huấn luyện. Khung hỏng chỉ duyệt được khi vùng hỏng đã tô IGNORE.

**Đã thử:** hai bộ ảnh thật ngày 23/09 (camera nằm trên bàn, không ở độ cao của xe): 8 ảnh, hai khung 720p bị cắt được đánh dấu hỏng; export và `PreparedCache.open` chạy được. Test: 35 hàm (48 trường hợp) cho `labels.py`; 15 hàm (20 trường hợp) cho giao diện, chạy offscreen.

**Giới hạn:** tốc độ gán nhãn chưa đo. Nhãn sửa từ nháp bị thiên lệch neo về phía lượt nền, nên phép chấm cho khóa luận phải dùng tập tô tay từ đầu (`--no-draft`, dự án riêng). Nhãn dẫn xuất từ nháp của mô hình WoodScape có chịu điều khoản Valeo không thì **chưa đánh giá**. `evaluate.py` chưa tự kiểm ảnh chấm có nằm trong train của checkpoint không.

**Tài liệu:** [GAN_NHAN_SA_BAN.md](autopark/docs/GAN_NHAN_SA_BAN.md).

**Tiếp theo:** gá camera ở độ cao và góc chúc dự kiến; chụp phiên huấn luyện vào `runs/rig_snapshots`, phiên chấm vào `runs/rig_snapshots_cham`; nhắm 100–200 ảnh có nhãn (HUAN_LUYEN.md mục 18).

### 4.8. Hợp nhất cảm biến (giai đoạn 3, chuẩn bị cho giai đoạn 8)

**Trạng thái:** phần mềm có từ 22/09. Đầu vào thật duy nhất là LiDAR C1 đứng yên trên bàn.

**Đã có:** các lớp `StaticMap`, `LiveLidar`, `CameraSemantic`, `NearField`, mỗi lớp có tuổi tối đa. Quy tắc hợp nhất: ô OCCUPIED nếu có lớp tươi nào OCCUPIED; FREE nếu có lớp tươi FREE; còn lại UNKNOWN. Lớp bắt buộc bị cũ thì bản đồ hợp nhất không hợp lệ, mọi ô bị chặn. Có cầu nối vật cản vào phiên mô phỏng giai đoạn 0 và ngăn LiDAR trong cửa sổ đỗ xe.

**Số liệu** (22/09, COM4): LiDAR cố định tại điểm xuất phát; xe ảo lập đường quanh 20 vật cản thật và đỗ xong (COMPLETED); 202 vòng quét, 0 lỗi đọc, 0 dừng giả. Năm quy tắc (bền vững 2/3 vòng, mặt nạ thân xe, hành lang quỹ đạo, bản đồ thời gian thực, cảm biến cố định) đều được thêm sau một lần dừng giả trên bàn.

**Giới hạn:** chưa thử đưa tay/hộp hoặc rút cáp với LiDAR thật khi xe ảo đang chạy (mới kiểm bằng nguồn quét kịch bản). ToF chỉ có số đo giả. Lớp camera chưa có khung thật đi qua. Chưa có định vị. *(Cập nhật tối 24/09/2026:)* định vị LiDAR trên bản đồ tĩnh có công cụ chạy offline (mục 4.3) nhưng chưa nối vào hợp nhất hay phiên; costmap BEV đặt được vào `CameraSemanticLayer` trong test (mục 4.12), chưa nối vào bàn thử. Bỏ 15 vòng đầu chưa phủ hết giai đoạn khởi động mô-tơ: số tia đạt đỉnh ở vòng 16–17 và ổn định từ vòng 21–22 (ghi chú 24/09). Chưa có mã đổi `VehicleTelemetry` sang `NearFieldReading`.

**Tài liệu:** [GIAI_DOAN_3_CHUAN_BI.md](autopark/docs/GIAI_DOAN_3_CHUAN_BI.md); giám sát dữ liệu cũ ở [GIAI_DOAN_1_CHUAN_BI.md](autopark/docs/GIAI_DOAN_1_CHUAN_BI.md) mục 4.

**Tiếp theo:** thử đưa tay và rút cáp (cần người); tăng `initial_skip` hoặc chờ theo thời gian nếu bản đồ nền bị ảnh hưởng; đọc ToF/IMU thật khi có ESP32.

### 4.9. Giao thức xe, VehicleIO và firmware ESP32-S3

**Trạng thái:** phần mềm và mô phỏng (24/09). **Firmware C++ chưa biên dịch lần nào** vì máy không có trình biên dịch C/C++ hay PlatformIO. Chưa có bo. *(Cập nhật tối 24/09/2026:)* `VehicleIO` đã nối vào phiên đỗ xe, có thêm chế độ quan sát ([CHE_DO_QUAN_SAT.md](autopark/docs/CHE_DO_QUAN_SAT.md)). Mức bằng chứng: **chỉ mô phỏng** và cổng serial giả.

**Đã có:** khung COBS + CRC-16/CCITT-FALSE, bảy loại thông điệp, phiên và số thứ tự; bản tham chiếu Python của firmware; `VehicleIO` hai nhánh (mô phỏng và serial) đi qua cùng byte; vector mẫu chung cho Python và C++.

**Cơ chế an toàn trong phần mềm:** mỗi lệnh có thời hạn (laptop gửi 150 ms, bo kẹp ≤ 300 ms). Watchdog liên lạc của bo: 500 ms → DISARMED. Laptop chốt `TELEMETRY_STALE` sau 0,3 s và phải `arm()` lại. Reset và kết nối lại luôn về DISARMED. E-stop chốt FAULT. Trần effort 250 ‰ (CHƯA CHỐT). Lỗi STALL ở vòng kín.

**Số liệu** (24/09, `.venv`): 184 test đạt, 0 lỗi (giao thức 52, bản tham chiếu firmware 73, VehicleIO 48, kiểm tĩnh C++ 11). Ba đợt đột biến mã (21, 22, 22 đột biến); sau khi thêm test, mọi đột biến đều bị bắt. Riêng 13 đột biến trên mã C++ của đợt ba chỉ bị bắt bằng kiểm tĩnh mã nguồn, không phải bằng chạy mã (C++ chưa biên dịch). Mô phỏng vòng tốc độ với số giả định: sai số trung bình < 1 mm/s nhưng vọt lố 26–57 %. Ngừng gửi lệnh lúc 0,15 m/s thì xe mô phỏng dừng sau 0,39 s, trôi 3,9 cm. Đó là số của mô hình, không phải quãng dừng xe thật.

**CHƯA CHỐT theo bo thật:** chân GPIO, xung ESC/servo, hành vi ESC khi mất xung và khi lùi, đường vật lý khi lên xe, hệ số PI/feedforward.

**Nối vào phiên đỗ xe và chế độ quan sát** (tối 24/09, [CHE_DO_QUAN_SAT.md](autopark/docs/CHE_DO_QUAN_SAT.md)): ô chọn nhánh chạy trong ngăn "Mô phỏng" của giao diện có ba lựa chọn.

- `SIM` (mặc định): giữ nguyên hành vi giai đoạn 0.
- `VEHICLE_IO`: mỗi nhịp 50 Hz gửi một COMMAND có thời hạn qua `VehicleIO`. Tốc độ và góc lái lấy từ telemetry.
- `OBSERVE` (quan sát): người lái; phần mềm tính đường và lệnh nhưng **không gửi COMMAND nào**, bo phải ở DISARMED. Đây là chế độ quan sát mà kế hoạch mục 13 yêu cầu.
- Trước START, lớp nối kiểm lại trạng thái thật: 3 khung telemetry mới, bo không FAULT/E-stop, xe đứng yên, tư thế mới và cách điểm xuất phát ≤ 3 cm / 5°. Sai thì từ chối, bo không bị bỏ lại ở ARMED. Đã dừng thì không tự chạy tiếp, kể cả khi kết nối lại (trên mô phỏng; *cập nhật tối 24/09/2026:* có một khoảng trống đã biết khi chạy kèm luồng `Heartbeat`, xem **Giới hạn** dưới; *cập nhật muộn tối 24/09/2026:* khoảng trống đó đã sửa, cũng chỉ kiểm trên mô phỏng và cổng serial giả). Dừng mà sau 2 s chưa xác nhận được xe đứng yên thì FAULT `STOP_NOT_CONFIRMED`.
- Mỗi lần chạy ghi `commands.csv`, `telemetry.csv`, `events.csv`, `start_refusals.csv`, `link.json`. `SerialVehicleIO` đọc không chặn (`poll(block=False)`); đồng hồ mặc định đổi sang `time.perf_counter` vì `time.monotonic` trên Windows chỉ đổi mỗi 15,625 ms.
- Test: `tests/test_session_vehicle.py`, 34 đạt lúc viết CHE_DO_QUAN_SAT.md (17:41 24/09); một lần chạy lại tối 24/09, trước khi tệp được bổ sung, cùng `test_bev.py` và `test_lidar_localize.py`: 95 đạt (32 + 29 + 34). *(Cập nhật tối 24/09/2026, 18:41, máy bàn, `.venv`, chỉ mô phỏng:)* tệp test đã được bổ sung sau đó (treo vòng điều khiển khi có/không có `Heartbeat`, từ chối START khi thiếu góc lái đo), nay thu 50 test: **49 đạt + 1 `xfail` strict**. Ba tệp cùng chạy: 110 đạt + 1 xfail (32 + 29 + 49 + 1). Test `xfail` ghi lại khoảng trống an toàn ở **Giới hạn** dưới, CHƯA SỬA; pytest báo `1 xfailed` là kết quả đúng, không phải lỗi mới. Đột biến: 6 + 27 đột biến, đều bị bắt (với bộ 34 test lúc 17:41). *(Cập nhật muộn tối 24/09/2026, sau bản sửa khoảng trống:)* tệp nay có **60 test, 60 đạt, 0 `xfail`** (chạy lại riêng tệp khi cập nhật tệp này, máy bàn, `.venv`); ba tệp `test_bev.py` + `test_lidar_localize.py` + `test_session_vehicle.py`: 121 đạt (32 + 29 + 60). Các số 50 / 49 + 1 và 110 + 1 ở trên là của bản trước khi sửa.
- Số của mô phỏng (thông số giả định, **không** phải số của MN300): `VEHICLE_IO` đỗ xong, sai số cuối 0,60 cm / +1,15°. Rút cáp giả ở 0,10 m/s: phát hiện sau 120 ms, xe mô phỏng trôi 4,1 cm.
- **Tư thế là định vị lý tưởng** (`SimTruthPose`, tư thế thật của xe mô phỏng). Định vị LiDAR (mục 4.3) chưa nối vào đây, và chưa kiểm yêu cầu "cùng đồng hồ" với bo thật. Giao diện chưa có lựa chọn cổng serial tới bo thật.

**Giới hạn:** chưa có mã đọc encoder, AS5600, BNO085, VL53L1X, điện áp. `VehicleIO` chưa nối vào phiên và bộ bám quỹ đạo; chưa ghi `commands.csv` / `telemetry.csv`. *(Cập nhật tối 24/09/2026: đã nối và đã ghi ở mức mô phỏng, xem trên. Chưa từng chạy với ESP32-S3 hay MN300. Cách đấu dây ở chế độ quan sát CHƯA CHỐT. `replay_run` chưa phát lại được lần chạy qua `VehicleIO`.)* *(Cập nhật muộn tối 24/09/2026: `export_run`/`replay_run` nay nhận ra lần chạy qua `VehicleIO` và từ chối rõ bằng `ReplayNotSupported`, 4 test trong `tests/test_run_store_vehicle.py`; bằng chứng của lần chạy là các log ở trên. Vẫn chưa phát lại được.)* Không xác thực nguồn gửi.

*(Thêm tối 24/09/2026, khoảng trống an toàn đã biết, chỉ thấy trên mô phỏng; **đã sửa muộn tối 24/09/2026**, xem đoạn tiếp theo. Đoạn này giữ nguyên làm hồ sơ:)* nếu vòng điều khiển treo lâu hơn hạn lệnh (0,15 s) trong khi một luồng khác (`Heartbeat`) vẫn PING và đọc telemetry, bo về ARMED (`COMMAND_TIMEOUT`) mà telemetry vẫn mới, nên chốt `TELEMETRY_STALE` không bật. Khi bước đầu tiên sau lúc hết treo rơi vào nhịp điều khiển, phiên gửi **một** COMMAND enable=1 trước khi lấy sự kiện `VEHICLE_STOPPED`, nên bo ARMED → RUNNING thêm một lần; nhịp sau phiên mới dừng và gửi enable=0. Test `test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes[0]` là `xfail(strict=True)` (pha 1–3 đạt). Trên bo mô phỏng và cổng serial giả, enable=0 tới cùng mili giây nên effort vẫn 0; trên bo thật: CHƯA ĐO. Phiên hiện không dùng `Heartbeat`. Khi không có luồng nào đọc cổng lúc treo, 8 trường hợp (treo 0,3 s và 1 s × 4 pha, cổng serial giả) đều dừng và không có lệnh enable nào. Cách sửa (ở `vehicle_link.py`/`session.py`): CHƯA LÀM. Chi tiết: [GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md) mục 12.

*(Cập nhật muộn tối 24/09/2026, máy bàn, `.venv`; mức bằng chứng: **chỉ mô phỏng và cổng serial giả**, chưa thử trên ESP32-S3 thật.)* **Khoảng trống trên đã sửa.**

- **Câu "effort vẫn 0" ở đoạn trên chỉ đúng khi lệnh dừng tới cùng mili giây với lệnh enable=1.** Test mới cho bo chạy thêm 10 / 20 / 40 ms trước khi lệnh dừng tới (như thời gian tính và trễ USB trên máy thật): trước bản sửa, mô hình bo đưa effort lên 107 / 115 / 130 ‰. Đây là số của mô hình bo (`FirmwareModel`, cổng serial giả, đầu vào đứng yên), không phải số đo.
- **Cách sửa, hai lớp:** (1) hàm mới `VehicleLink.refresh()`, được `Session._step_closed_loop` gọi đầu mỗi bước khi đang RUNNING, **trước** nhịp điều khiển. Với bo thật nó gọi `poll(block=False)`, chỉ lấy byte đã có sẵn. Với bo mô phỏng nó gọi hàm mới `VehicleIO.take_new()`, chỉ lấy telemetry đang chờ, không tiến I/O hay đồng hồ mô phỏng. Sau đó nó gom sự kiện. (2) Lớp chặn thứ hai trong `VehicleLink.command()`: còn sự kiện dừng chưa được phiên lấy thì không gửi gì và trả `HALTED`. Mã: `application/vehicle_link.py`, `application/session.py`, `transport/vehicle_io.py`.
- **Test** (`tests/test_session_vehicle.py`, 60 test, 60 đạt, 0 `xfail`): hai trường hợp `xfail` strict cũ (pha 0 của `test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes` và `test_vehicle_io_command_timeout_after_freeze_by_phase`) nay đạt. Hai test từng ghi lại hành vi lỗi được viết lại và đổi tên: `test_resume_after_hang_sends_no_enable_to_the_sim_board` và `test_resume_after_hang_keeps_effort_zero_whatever_the_gap_before_the_stop[0/10/20/40]` (sau khi hết treo không có enable=1 nào, effort 0 ở mọi khoảng trễ). Thêm `test_command_refuses_enable_while_a_stop_event_is_pending`.
- **Đột biến:** bỏ lời gọi `refresh()` thì 7 test hỏng; bỏ lớp chặn thứ hai thì test mới hỏng.
- **Còn mở:** thứ tự "lấy sự kiện trước nhịp điều khiển" mới kiểm trên mô phỏng; trên bo thật, khoảng trễ giữa telemetry báo dừng và lệnh kế tiếp CHƯA ĐO. Phiên hiện vẫn không dùng `Heartbeat`. *(Thêm muộn tối 24/09/2026:)* `refresh()` chỉ thấy khung đã tới laptop: nếu bo vừa về ARMED (`COMMAND_TIMEOUT`) mà khung telemetry báo điều đó chưa tới (bo gửi mỗi 50 ms, cộng trễ USB), laptop vẫn có thể gửi một enable=1 (bo ARMED → RUNNING). Điều này suy ra từ mã, chưa có test; khoảng hở này và effort khi đó trên bo thật CHƯA ĐO ([GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md) mục 12, [CHE_DO_QUAN_SAT.md](autopark/docs/CHE_DO_QUAN_SAT.md) mục 8).

**Tài liệu:** [GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md), [firmware/esp32_vehicle/README.md](autopark/firmware/esp32_vehicle/README.md), [CHE_DO_QUAN_SAT.md](autopark/docs/CHE_DO_QUAN_SAT.md). Dòng "chưa nối `VehicleIO` vào phiên" ở GIAO_THUC_XE.md mục 12 đã được đánh dấu lỗi thời tại chỗ (tối 24/09).

**Tiếp theo:** cài PlatformIO (người dùng quyết định), biên dịch, chạy test C++ trên máy tính với `vectors.json`. Khi có bo: đo xung bằng máy hiện sóng trước khi nối ESC. *(Tối 24/09:)* khi có bo và định vị: thêm lựa chọn cổng serial trong giao diện, thay `SimTruthPose` bằng nguồn tư thế thật cùng đồng hồ với `VehicleIO`. *(Thêm tối 24/09/2026:)* sửa khoảng trống enable=1 sau `COMMAND_TIMEOUT` (ở **Giới hạn** trên) trước khi nối bo thật. *(Cập nhật muộn tối 24/09/2026: đã sửa ở mức mô phỏng; khi có ESP32-S3, chạy lại kịch bản "treo quá hạn lệnh khi có `Heartbeat`" trên bo thật.)*

### 4.10. Nguồn và an toàn

**Trạng thái:** giai đoạn 6 mới ở phần "khi chưa có nguồn final". Chưa có phần cứng nguồn hay dừng nào.

**Đã có:** các tình huống mất liên lạc, rút cáp, treo chương trình, bo khởi động lại đã được viết trong đặc tả giao thức và firmware (mục 4.9). Đã chọn cách đấu ngõ vào E-stop an toàn khi hở mạch (tiếp điểm NC nối GND, điện trở kéo lên), chưa lắp, chưa thử. Phiên mô phỏng giai đoạn 0 dừng khi phản hồi cũ hơn 150 ms.

**Chưa có:** bảng tải điện áp/dòng, `power_budget.md`, sơ đồ nguồn, sơ đồ dừng *(tối 24/09: đã có bản nháp, xem dưới; chưa có số đo)*. Chưa chọn UBEC hay XL4015, định mức cầu chì, phần tử mà LA38 cắt. Ngõ vào E-stop của firmware **không thay** đường cắt động lực phần cứng. Cờ STOP trên laptop không chứng minh xe thật dừng được.

*(Cập nhật tối 24/09/2026:)* có **bản nháp** cho bốn đầu ra mà kế hoạch đặt tên, gộp trong [GIAI_DOAN_6_CHUAN_BI.md](autopark/docs/GIAI_DOAN_6_CHUAN_BI.md): bảng tải (nháp `power_budget`), sơ đồ nguồn, sơ đồ dừng, bảng định mức còn phải kiểm, cùng 16 kịch bản lỗi L1–L16. Mức bằng chứng: bản nháp thiết kế.

- Số điện duy nhất trong repo vẫn là số datasheet của RPLIDAR C1. Mọi dòng khác của bảng tải là CHƯA ĐO hoặc CẦN TRA datasheet.
- Cả 16 kịch bản lỗi đều **CHƯA THỬ** trên thiết bị. Vài kịch bản mới có test với cổng giả hoặc nguồn quét kịch bản.
- Còn mở, người dùng quyết định: N1–N7 (laptop có đặt trên xe không, nguồn cho bo, nguồn servo, UBEC hay XL4015, nguồn hub, công tắc logic, ESC nguyên bản có nhận xung riêng không), phương án phần tử ngắt, và `require_speed_feedback`.
- Tách `power_budget.md` thành tệp riêng hay giữ trong tệp nháp: CHƯA CHỐT.

**Tài liệu:** [GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md) mục 0, 5, 6, 12; [GIAI_DOAN_6_CHUAN_BI.md](autopark/docs/GIAI_DOAN_6_CHUAN_BI.md); kế hoạch mục 10 (giai đoạn 6) và mục 3 (đợt mua 6).

**Tiếp theo:** lập bảng tải và sơ đồ nguồn/dừng trước khi thử chấp hành. Giai đoạn 6 phải xong trước khi chạy tự động trên sàn. *(Tối 24/09:)* bản nháp đã có; bước kế là chốt N1–N7 trước đợt mua 6, rồi đo từng dòng bảng tải khi có phần cứng (GIAI_DOAN_6_CHUAN_BI.md mục 1.3).

### 4.11. Ghi và phát lại phiên bàn thử (thêm tối 24/09/2026)

**Trạng thái:** phần mềm có test với nguồn giả. **Một** phiên thật đã được ghi và phát lại trên máy bàn (tối 24/09). Chưa commit.

**Đã có:** `rig.bench --record` và nút "Ghi phiên" của `rig_app` ghi mọi khung tốt của bốn camera (JPEG q95 mặc định, hoặc PNG), sự kiện khung hỏng, mọi vòng LiDAR và `meta.json`. `rig.bench --replay` và `rig_app --replay` chạy lại cả bàn thử từ bản ghi, không mở thiết bị nào, nên so được hai quy tắc chờ trên **cùng một** dữ liệu. Khung bị bỏ và lỗi ghi được đếm và báo, không im lặng. Test: `tests/test_rig_replay.py`, 27 hàm (chạy lại tối 24/09 trong `.venv-train`: 27 đạt); 12 + 15 đột biến đều bị bắt (theo GHI_PHAT_LAI_BAN_THU.md mục 6).

**Phiên thật đầu tiên** (o03, tối 24/09, máy bàn, 640×480 × 4 + LiDAR + AI, 60 s, camera nhìn chỗ tối):

- Ghi: 5.724 khung (1.431 mỗi camera), **0 khung bị bỏ**, 601 vòng LiDAR, 298,6 MB, tức **4,98 MB/s** (≈ 52 KB/khung). Ước lượng trước đó 15 MB/s làm trên ảnh thảm hoa văn; cảnh sa bàn thật **chưa đo**. Ghi không ảnh hưởng thấy được tới bàn thử (AI 23,85 bộ/s, 0 bộ bỏ camera). CPU tiến trình tăng ≈ 0,1 lõi so với o02, chưa tách khỏi nhiễu giữa hai phiên.
- Phát lại lần đầu (o04) để 34 / 34 / 67 / 34 khung (cổng 1 / 2 / 3 / 4) không vào bộ nào, chủ yếu vì lô AI đầu mất 1,46 s; cổng 3 mất thêm ≈ 33 khung, nguyên nhân chưa tách (có thể do lô AI đầu của cỡ 3 ảnh ở bộ thiếu camera, như o05; CHƯA KIỂM). Đây là cách phát hiện chỗ chậm ở mục 4.2. Sau khi làm nóng mọi cỡ lô (o06): 1.432 / 1.432 bộ, độ lệch bộ trung vị / p95 / max 26,0 / 42,1 / 44,8 ms, trùng phiên thật tới 0,1 ms. Còn khác: một bộ thiếu cổng 3 ở giây đầu, khi chưa đo được nhịp camera.

**Giới hạn:** stamp được đổi gốc sang đồng hồ phát lại, nên chỉ so khoảng cách và độ lệch, không so giá trị tuyệt đối. JPEG mã hóa lại làm AI không trùng từng bit. Bản ghi chỉ chứa khung tốt, nên phát lại không thử lại được bộ dò khung hỏng. Phát lại không tái tạo tranh chấp USB hay DirectShow, nên CPU/GPU/thời gian AI của phiên phát lại không thay số đo trực tiếp. Ở speed ≠ 1, kết quả ghép bộ không so được với phiên gốc.

**Chưa thử:** bản ghi có camera lỡ nhịp thật; giao diện `--replay` với bản ghi thật (mới chạy với nguồn giả); speed ≠ 1 trên bản ghi thật; laptop RTX 3050 Ti (luồng ghi có theo kịp không, đĩa có đủ chỗ không).

**Tài liệu:** [GHI_PHAT_LAI_BAN_THU.md](autopark/docs/GHI_PHAT_LAI_BAN_THU.md) (mục 7 là phiên thật).

**Tiếp theo:** ghi một phiên có camera lỡ nhịp thật, rồi phát lại với `--max-wait-ms 60` và `--max-wait-ms 0`; ghi một phiên nhìn sa bàn thật để biết MB/s ở cảnh có chi tiết.

### 4.12. BEV chiếm chỗ từ AI nhiều camera (thêm tối 24/09/2026)

**Trạng thái:** phần mềm và test trên rig tổng hợp. **Chưa chạy được trên camera của dự án**, vì còn thiếu ba thứ: chưa camera nào được hiệu chuẩn (`calibration/cam_p*.json` chưa có), ngoại tham trong `configs/rig/camera_rig_extrinsics_v0.json` là **GIẢ ĐỊNH — CHƯA ĐO**, và chưa có mặt nạ ROI cho camera dự án. Chưa commit.

**Đã có:** `perception/bev.py` chiếu P(BLOCKED) của từng camera xuống mặt sàn (giả định sàn phẳng) và hợp nhất thành `Costmap` trong hệ xe. Hai ngưỡng: p ≤ 0,15 là FREE, p ≥ 0,50 là OCCUPIED, ở giữa là UNKNOWN. Ô bị che, ngoài tầm, dưới thân xe, hay thuộc camera thiếu dữ liệu đều là UNKNOWN, **không bao giờ mặc định FREE**. Ô có một camera nói OCCUPIED thì là OCCUPIED. Costmap tự đánh dấu không dùng được cho lập đường khi ngoại tham chưa đo, khi thiếu ROI, hoặc khi nội tham không qua tiêu chí; vì vậy mọi BEV từ tệp rig v0 hiện đều không dùng được.

**Đã chạy** (24/09, máy bàn):

- Rig tổng hợp bốn camera (tư thế v0, ống kính danh định), 32 test đạt ở cả `.venv` lẫn `.venv-train`; 23 đột biến đều bị bắt.
- Một ảnh WoodScape (`00000_FV`) với checkpoint tham chiếu: nhìn bằng mắt thì mặt đường phía trước là FREE, xe phía trước cắt vùng FREE. Đây là minh họa, **không** phải phép đo sai số BEV (không có nhãn mặt sàn). WoodScape chỉ có một camera mỗi khung, nên không có bộ bốn camera đồng bộ.
- *(Thêm muộn tối 24/09/2026; bản trước chỉ ghi một ảnh.)* Ba ảnh WoodScape khác thời điểm (`00000_FV`, `00028_RV`, `00140_MVL`; mỗi mã khung chỉ có một camera): chạy được, costmap bị đánh dấu không dùng được vì các khung không đồng bộ; chỉ để thử luồng hợp nhất, không phải bộ bốn camera đồng bộ. **Có một lỗi thấy được:** ảnh MVL cho một đường cong mảnh OCCUPIED/occluded phía sau mặt phẳng ảnh của camera trái (θ gần 90–100°), do `configs/roi/woodscape_v1/roi_MVL.png` không loại hết pixel sát thân xe; chưa sửa. Với camera dự án, ROI phải dựng kỹ ở mép thân xe (BEV.md mục 6).
- Bộ ảnh thật ngày 23/09: lệnh `snapshot` từ chối và liệt kê bốn tệp hiệu chuẩn còn thiếu. Đúng như thiết kế.
- Thời gian bốn camera, lưới 6 × 6 m ô 5 cm, supersample 2: trung vị ≈ 69,5 ms, chậm hơn một chu kỳ khung (≈ 42 ms); khung đầu thêm ≈ 250–380 ms để dựng bảng. Không kiểm tải máy lúc đo.

**Giới hạn:** giả định sàn phẳng, nên với vật cao chỉ cạnh chân vật hướng về camera là OCCUPIED; biên tiếp xúc chưa chọn phương pháp. Độ phân giải mặt sàn giảm nhanh theo khoảng cách (số **tính** trên rig giả định: ≈ 9,5 cm/pixel ở 2 m với camera trước). Hai ngưỡng 0,15 / 0,50 chưa kiểm trên ảnh sa bàn. Điều kiện của kế hoạch mục 6, "vật mẫu xuất hiện tại vị trí có thể đối chiếu trên BEV", **chưa kiểm**. Chưa nối vào bàn thử, hợp nhất hay planner; việc nối AI vào lập đường còn chờ quyết định giấy phép WoodScape. *(Thêm muộn tối 24/09/2026:)* ROI WoodScape `roi_MVL.png` còn sót pixel sát thân xe (lỗi thấy ở lần ba ảnh, chưa sửa).

**Tài liệu:** [BEV.md](autopark/docs/BEV.md).

**Tiếp theo** (BEV.md mục 8): hiệu chuẩn nội tham bốn camera; gá, chốt gán cổng → hướng, đo ngoại tham; dựng mặt nạ ROI; đặt vật mẫu ở vị trí đo bằng thước và so với BEV; tối ưu tốc độ.

### 4.13. Chuẩn bị giai đoạn 4: đo MN300 khi chưa có xe (thêm tối 24/09/2026)

**Trạng thái:** tài liệu soạn trước. **Chưa nhận MN300, chưa đo gì trên xe.** Mọi ô "đo được" để trống hoặc ghi CHƯA ĐO.

**Đã có:**

- [mn300_inventory.md](autopark/docs/mn300_inventory.md): phiếu kiểm kê mẫu (gói hàng, pin/sạc, ESC, bộ thu, servo, motor, đầu nối, sơ đồ đấu dây nguyên bản, chạy thử bằng điều khiển nguyên bản, câu hỏi cho shop). Mỗi hàng tách cột "theo shop/hộp" với cột "thực nhận/đo được".
- [GIAI_DOAN_4_CHUAN_BI.md](autopark/docs/GIAI_DOAN_4_CHUAN_BI.md): chín khóa của `configs/vehicle_default.json` và các tham số khác phụ thuộc số đo xe; bảng đo B0–B8 (hình học, góc lái và bán kính quay, tốc độ đổi lái, tốc độ thấp, đổi chiều, quãng dừng, đường cong lệnh, xung servo); cách đưa số đo vào cấu hình và mô phỏng; khái niệm gá điều chỉnh được; thứ tự làm khi nhận xe.
- Phép thử độ nhạy của planner theo kích thước giả định: mới **đề xuất, CHƯA CHẠY**. Chiến dịch 20/09 có đổi kích thước nhưng không phải phép thử độ nhạy riêng (GIAI_DOAN_4_CHUAN_BI.md mục 5).

**Còn mở:** định dạng `vehicle_measured` (YAML theo kế hoạch hay JSON theo mã); dụng cụ đo xung, đồng hồ vạn năng, bộ thử servo đã có hay chưa; thư mục lưu ảnh kiểm kê CHƯA CHỐT.

### 4.14. Dàn ý khóa luận (thêm tối 24/09/2026)

**Trạng thái:** [DAN_Y_KHOA_LUAN.md](autopark/docs/DAN_Y_KHOA_LUAN.md) là dàn ý **đề xuất**, dựng từ biên bản trong repo tới 24/09 (gồm biên bản của bảy việc phần mềm tối 24/09). Nó không thêm số đo mới. Dàn ý có sáu nhãn mức bằng chứng (MP, DL, BT, TH, TK, XT), bảng mức sẵn sàng từng chương, danh sách hình/bảng có sẵn, tài liệu tham khảo, các câu dễ viết sai, và 22 việc cần làm trước khi viết (mục 7; việc 19–22 thêm tối 24/09: commit việc tối 24/09 rồi ghi commit cạnh số, ghi phiên có camera cắt/xé khung thật, chép bằng chứng định vị/BEV vào `docs/evidence/`, đo phần mới trên laptop; việc 10, 12, 15 được bổ sung tối 24/09). *(Sửa tối 24/09/2026: bản trước của tệp này ghi 18 việc.)*

**Giới hạn:** mẫu trình bày của trường, kiểu trích dẫn, giới hạn trang và quy định khai báo công cụ AI đều **chưa biết** ("cần tra"). Bản đầu của dàn ý (chiều 24/09) được viết khi các việc phần mềm song song ngày 24/09 (quy tắc chờ, BEV, ghi/phát lại, định vị LiDAR, chế độ quan sát, nháp giai đoạn 4/6) chưa có biên bản. *(Cập nhật tối 24/09/2026)* Dàn ý đã được cập nhật tối 24/09 theo biên bản của cả bảy việc: mục 8 của nó ghi mức bằng chứng thật của từng việc (BT/TH/DL/MP/TK) và cột "Đã cập nhật ở" liệt kê các mục đã sửa; ghi chú đầu tệp liệt kê mọi mục sửa/thêm (thêm 3.6b, 3.8b, 3.12b, 4.6b, 4.9b). Không thêm số đo mới. Số lấy từ việc tối 24/09 thuộc phần chưa commit, nên khi đưa vào khóa luận phải ghi commit chứa nó (dàn ý mục 1 ý 11, mục 7 việc 19). Dàn ý vẫn ghi 34 test cho chế độ quan sát; số mới (49 đạt + 1 `xfail`) ở mục 4.9 tệp này. Lần kiểm lại năm tệp test ở cuối mục 8 của dàn ý (237 đạt) cũng chạy khi tệp test phiên còn 34 test (237 − 34 = 203 test của bốn tệp kia, 203 + 50 = 253 như lần chạy lại); chạy lại đúng lệnh đó lúc ≈ 18:42 tối 24/09 (máy bàn, `.venv`, offscreen): 252 đạt + 1 xfail. *(Cập nhật muộn tối 24/09/2026:)* dàn ý đã được cập nhật theo bản sửa khoảng trống an toàn (60 test, không còn `xfail`; lệnh kiểm năm tệp ở cuối mục 8 của nó nay thu 263 test), theo lần chạy lại `may_moi` lúc 19:08 và theo cách nói "camera ≈ 29 khung/s không cố định một cổng".

## 5. Việc tiếp theo

### 5.1. Cần người dùng quyết định

| Việc | Vì sao cần | Tài liệu |
|---|---|---|
| Hướng giấy phép WoodScape cho khóa luận: giữ cách hiểu ngày 22/09 (chưa được Valeo xác nhận), tách vai trò, huấn luyện lại không dính WoodScape, hay hỏi Valeo | Quyết định có nối AI vào costmap/planner hay không, và có dùng nháp AI khi gán nhãn hay không | GIAY_PHEP_DU_LIEU.md |
| Có thêm ghi công WoodScape vào các tài liệu khác trong `autopark/docs/` không | Điều khoản Valeo yêu cầu ghi công trong tài liệu công bố | GIAY_PHEP_DU_LIEU.md cuối tệp |
| Có đưa `datasets/sa_ban_labels/` vào git không | Ảnh chép vào dự án gán nhãn khá nặng | GAN_NHAN_SA_BAN.md mục 8 |
| Sau vật cản thông thường: xe tự tiếp tục hay chờ xác nhận | Phải chốt trước giai đoạn 9 | kế hoạch 17.2 |
| Ngưỡng nghiệm thu (mục 16.2), bộ kịch bản (16.3), mốc thời gian | Chưa có ngưỡng và deadline được chốt | kế hoạch mục 16, 17.2 |
| Cài PlatformIO hoặc trình biên dịch C/C++ | Không có thì firmware không biên dịch được | firmware README |
| Sao lưu `autopark/runs/` (checkpoint tham chiếu `ai_woodscape_rtx4000_v1/best.pt` và mọi bản ghi đo LiDAR, camera, bàn thử) và bản giải nén dataset | Các thư mục này bị git-ignore nên không có trên GitHub. ZIP gốc không còn trong `D:\ap`. Không tài liệu nào ghi đã có bản sao lưu; HUAN_LUYEN.md mục 5 chỉ ghi "cần sao lưu riêng nếu muốn giữ". *(Tối 24/09: thêm bản ghi phát lại `runs/rig_recordings/o03_20260924/`, ≈ 300 MB, và `runs/rig_bench/20260924_own/`)* | HUAN_LUYEN.md mục 5, TRANG_THAI_TAI_DAY_DU.md |
| *(Thêm tối 24/09/2026)* Commit và push bảy việc ngày 24/09 | Mã và tài liệu của mục 4.3, 4.5, 4.9–4.14 **chưa commit** (nằm trên HEAD `2bd37b6`); mất cây làm việc là mất cả mã lẫn biên bản. Laptop lấy mã bằng `git clone`/`git pull` (MAY_NOP_DO_AN.md), nên chưa push thì laptop chạy bản **không** có quy tắc chờ mới và làm nóng AI. *(Cập nhật muộn tối 24/09/2026:)* commit cần gồm cả bản sửa khoảng trống an toàn (mục 4.9), bản sửa `lidar.bench record` (mục 4.3) và các tệp chưa theo dõi: tệp tham chiếu mới `autopark/docs/evidence/may_ban/tham_chieu_20260924_toi.json`, bản rút gọn `autopark/docs/evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json` và `autopark/docs/evidence/lidar/dinh_vi_*`; thiếu tệp tham chiếu mới thì laptop so với tham chiếu 15:25 (quy tắc chờ cũ, chưa làm nóng AI) | `git status` |
| *(Thêm tối 24/09/2026)* Phương án định vị cho V1: chỉ định vị trên bản đồ tĩnh (đã có công cụ) hay cần SLAM | Kế hoạch mục 1.2 cần "LiDAR cho bản đồ và định vị"; công cụ hiện có không cập nhật bản đồ và không có odometry | DINH_VI_LIDAR.md |
| *(Thêm tối 24/09/2026)* Nguồn và dừng: N1–N7 (laptop có đặt trên xe không, nguồn bo, nguồn servo, UBEC hay XL4015, nguồn hub, công tắc logic, ESC nguyên bản), phần tử mà LA38 cắt | Cần trước đợt mua 6 | GIAI_DOAN_6_CHUAN_BI.md mục 2.1, 3.2, 6 |
| *(Thêm tối 24/09/2026)* Cách đấu dây ở chế độ quan sát (ESC nối máy thu RC hay nối ESP32) | Chế độ quan sát trong mã giả định người lái bằng tay điều khiển RC | CHE_DO_QUAN_SAT.md mục 8 |
| *(Thêm tối 24/09/2026)* Định dạng `vehicle_measured` (YAML theo kế hoạch hay JSON theo mã); dụng cụ đo xung, đồng hồ vạn năng, bộ thử servo | Quyết định bảng đo nào làm ở giai đoạn 4 hay 5 | GIAI_DOAN_4_CHUAN_BI.md mục 8 |
| *(Thêm tối 24/09/2026)* Hỏi GVHD/khoa: mẫu khóa luận, kiểu trích dẫn, giới hạn trang, quy định khai báo công cụ AI | Chưa biết; ảnh hưởng mọi chương | DAN_Y_KHOA_LUAN.md mục 1, 7 |

### 5.2. Làm được với thiết bị đang có (cần người thao tác)

- **LiDAR:** 7 lần đặt hộp p01–p06, p08; lần đặt bên trái chốt dấu góc. Kiểm vật ở hai vùng góc gần. Rút cáp khi `live_view` đang chạy. *(Tối 24/09:)* cùng buổi: hai phiên liên tiếp có khởi động lại mô-tơ (gốc góc có đổi không), và 3–6 vị trí/hướng đo bằng thước làm tham chiếu độc lập cho định vị (DINH_VI_LIDAR.md mục 7).
- **Hợp nhất:** đưa tay/hộp vào trước LiDAR (cách ≥ 40 cm) và rút cáp khi xe ảo đang chạy.
- **Camera:** tách camera ra nhiều cổng gốc; thử nguồn ngoài cho hub; đổi chỗ camera cổng 1 và 2; chạy một phiên có camera chậm; thử ánh sáng sa bàn và `CAP_PROP_GAIN`; đo độ trễ bằng LED nháy. Ghi thêm dây camera, model hub, nhãn LiDAR, ảnh bộ thực giao. *(Tối 24/09:)* phiên có camera chậm nên **ghi lại** (`--record`) để phát lại với hai quy tắc chờ; cho camera nhìn cảnh sáng, nhiều chi tiết thì 720p dễ có khung bị cắt. Ghi thêm một phiên nhìn sa bàn thật để biết MB/s.
- **Hiệu chuẩn:** in bảng, đo cỡ ô, hiệu chuẩn bốn camera.
- **Ảnh sa bàn:** dựng giá ở độ cao và góc chúc dự kiến, chụp, gán nhãn, chấm AI.
- **Laptop RTX 3050 Ti (máy nộp đồ án):** làm theo [MAY_NOP_DO_AN.md](autopark/docs/MAY_NOP_DO_AN.md): chép checkpoint từ `D:\CHUYEN_SANG_LAPTOP\` (có mã SHA-256), chạy `cai_dat.cmd` và `cai_dat_train.cmd`, rồi `do_may_moi.cmd`. Lệnh này đo cấu hình, cổng USB, LiDAR, thời gian AI, bàn thử 480p và 720p, rồi so với tham chiếu máy bàn. *(Tối 24/09:)* tham chiếu máy bàn trong `docs/evidence/may_ban/` đo lúc 15:25, trước quy tắc chờ theo nhịp riêng và trước làm nóng AI; số tối 24/09 nằm ở [cho_nhip_rieng_ghi_phat_lai_20260924.json](autopark/docs/evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json). Trên laptop cần đo thêm: thời gian làm nóng AI, luồng ghi phiên có theo kịp không, BEV và định vị LiDAR mất bao lâu. *(Cập nhật muộn tối 24/09/2026:)* đã có tham chiếu máy bàn đo bằng mã mới lúc 19:08, [tham_chieu_20260924_toi.json](autopark/docs/evidence/may_ban/tham_chieu_20260924_toi.json) (quy tắc chờ theo nhịp riêng, làm nóng AI). `may_moi` lấy tệp đứng cuối theo tên trong thư mục đó, tức tệp mới; tệp 15:25 giữ lại để đối chiếu. Laptop chỉ có mã mới và tham chiếu mới sau khi người dùng commit và push, rồi `git pull` trên laptop. Thời gian làm nóng AI của laptop nằm ở `ai.warm_up_ms` trong `m01_480p_lidar_ai.rig.json`; `tom_tat.md` chưa in dòng này.

### 5.3. Thiết bị cần mua để mở khóa (kế hoạch mục 3)

| Đợt | Thiết bị | Mở khóa |
|---|---|---|
| 3 | BNO085, 2 × VL53L1X, ESP32-S3 (kế hoạch đề xuất mua sớm, một bo duy nhất) | IMU/ToF thật, nạp và chạy firmware, thử logic dừng trên bàn (giai đoạn 3 và 5) |
| 4 | MN300 Tank300 1/12 RTR, đúng gói pin/sạc | Đo tốc độ, góc lái, bán kính quay, quãng dừng; thay thông số giả định (giai đoạn 4, rồi 7) |
| 5 | AS5600 + nam châm, MT6701 hoặc encoder phù hợp, gá; thêm 2 ToF nếu cần | Điều khiển có phản hồi (giai đoạn 5) |
| 6 | Bộ nguồn theo tải, LA38 + phần tử ngắt, cầu chì, dây và gá final | Giai đoạn 6, điều kiện trước khi chạy tự động |

Ngoài kế hoạch mua: đồng hồ đo USB để đo dòng camera (usb_topology.md ghi chưa có). Adapter nguồn cho hub và máy hiện sóng (để đo xung trước khi nối ESC): tài liệu chưa ghi đã có hay chưa.

### 5.4. Phần mềm làm được ngay, không cần thiết bị mới

- Mã đổi `VehicleTelemetry.tof_m` sang `NearFieldReading`, kèm tệp cấu hình chỉ số ToF → vị trí gá.
- Nối `VehicleIO` (nhánh mô phỏng) vào phiên giai đoạn 0 / `TrajectoryTracker`; ghi `commands.csv`, `telemetry.csv`. *(Đã làm tối 24/09/2026 ở mức mô phỏng: mục 4.9, CHE_DO_QUAN_SAT.md. Còn lại: `replay_run` chưa phát lại được lần chạy qua `VehicleIO`; giao diện chưa có lựa chọn cổng serial.)* *(Cập nhật muộn tối 24/09/2026: `replay_run` nay từ chối rõ bằng `ReplayNotSupported`; phát lại thật vẫn chưa có.)*
- Công cụ ngoại tham camera (ví dụ `cv2.fisheye.solvePnP` với bảng đặt trên sàn) và bước ghép nội tham + ngoại tham để `costmap.py` dùng được camera của dự án. Công cụ dựng mặt nạ ROI cho camera dự án. *(Tối 24/09/2026: bước ghép nội tham + ngoại tham đã có trong `load_rig()` của BEV, mục 4.12; công cụ đo ngoại tham và công cụ dựng ROI vẫn chưa có.)*
- Sửa nhược điểm của quy tắc không chờ khi pha camera trôi (0,2–2,7 % số bộ). *(Đã làm tối 24/09/2026: quy tắc theo nhịp riêng, mục 4.5; trong mô phỏng bỏ "chậm" 0 %, còn 2,1–2,5 % số bộ để dành để gom lại pha.)*
- `initial_skip` ≥ 22 vòng, hoặc chờ theo thời gian, trong demo hợp nhất.
- Cho `evaluate_external` chấm RoadAnomaly21; cho `evaluate.py` kiểm ảnh chấm không nằm trong train; thêm `labels import --exclude`.
- Lưu script đo độ lặp lại LiDAR vào repo; chép bản nhỏ của k01 vào `autopark/docs/evidence/lidar/`. *(Tối 24/09:)* ảnh overlay và tóm tắt kết quả định vị offline đã chép vào cùng chỗ (`dinh_vi_*.png`, `dinh_vi_tren_p07_20260924.json`); script độ lặp lại và bản nhỏ của chính bản ghi k01 thì chưa.
- Chọn phương án SLAM/định vị 2D cho LiDAR và kiểm đầu vào bắt buộc của nó (kế hoạch mục 5 "Khi đang chờ đồ" và mục 17.2 "đầu vào thư viện SLAM"). Chưa tài liệu nào ghi phương án đã chọn. Thử trước trên dữ liệu lưu sẵn: DROW v2 có `.odom2` (đã ghép thử 300 vòng ở GIAI_DOAN_1_LIDAR.md mục 5, mới là bằng chứng gián tiếp, chưa phải kiểm chứng SLAM) và các bản ghi C1 (LiDAR đứng yên). Chưa có odometry thật thì không gán odometry bằng 0 để báo đã có định vị. Việc này đang chặn điều kiện V1 đầu tiên (mục 16.4) và dòng "Định vị lại được: CHƯA" của gate 1. *(Cập nhật tối 24/09/2026: đã có định vị trên bản đồ tĩnh, mục 4.3. Nó không phải SLAM và không dùng odometry. Dòng gate 1 vẫn chặn vì thiếu tham chiếu độc lập, việc đó cần người, mục 5.2. SLAM: chưa chọn.)*
- Soạn trước: phiếu kiểm kê và bảng đo MN300 (giai đoạn 4), bảng kịch bản nghiệm thu (16.3) và cách đo độc lập, khung bảng tải điện. *(Tối 24/09/2026: phiếu kiểm kê, bảng đo B0–B8 và khung bảng tải đã có ở dạng nháp, mục 4.10 và 4.13. Bảng kịch bản nghiệm thu 16.3 và cách đo độc lập vẫn chưa có; GIAI_DOAN_6_CHUAN_BI.md chỉ có phần kịch bản lỗi.)*
- *(Thêm tối 24/09/2026)* Sửa khoảng trống an toàn ở mục 4.9 (một COMMAND enable=1 sau `COMMAND_TIMEOUT` khi `Heartbeat` giữ liên lạc lúc vòng điều khiển treo), trong `application/vehicle_link.py` hoặc `session.py`, rồi bỏ dấu `xfail` của test tương ứng ([GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md) mục 12). *(Đã làm muộn tối 24/09/2026 ở mức mô phỏng: `VehicleLink.refresh()` trước nhịp điều khiển và lớp chặn trong `command()`; không còn `xfail`; mục 4.9.)*
- *(Thêm tối 24/09/2026)* Tăng tốc BEV: ≈ 69,5 ms cho bốn camera, chậm hơn một chu kỳ khung (BEV.md mục 8).
- *(Thêm tối 24/09/2026)* Phép thử độ nhạy của planner theo kích thước xe với sa bàn cố định; thêm tùy chọn cấu hình xe cho `robustness.py`, `phase0.py`, `fusion/demo.py`, `ui/lidar_app.py` (GIAI_DOAN_4_CHUAN_BI.md mục 5.3, 8).

## 6. Bản đồ tài liệu

"Hiện hành" = dùng làm tình trạng hiện nay. "Hồ sơ" = ghi lại một đợt làm việc; số liệu đúng cho đợt đó, chỗ lỗi thời có ghi chú tại chỗ. Cột "Cập nhật" là ngày sửa nội dung gần nhất.

| # | Tài liệu | Vai trò | Tình trạng | Cập nhật |
|---:|---|---|---|---|
| 1 | [TONG_HOP_DU_AN.md](TONG_HOP_DU_AN.md) | Tổng hợp theo mảng, đọc đầu tiên | hiện hành (cập nhật tối 24/09: bảy việc mới, mục 4.11–4.14; muộn tối 24/09: sửa khoảng trống an toàn, rút cáp LiDAR, tham chiếu máy bàn 19:08, tổng số test) | 24/09 |
| 2 | [README.md](README.md) | Trang đầu repo, mục lục tài liệu, mức bằng chứng | hiện hành (thêm tài liệu mới tối 24/09) | 24/09 |
| 3 | [KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) | Kế hoạch 11 giai đoạn, 6 đợt mua, điều kiện chuyển bước, V1 | thân tệp là kế hoạch (19/09), không phải kết quả; mục 1.1 (nhận hàng) và bảng 17.4 hiện hành (bảng 17.4 cập nhật tối 24/09) | 24/09 |
| 4 | [BAO_CAO_GIAI_DOAN_0.md](BAO_CAO_GIAI_DOAN_0.md) | Báo cáo giai đoạn 0 | hồ sơ 20/09; chỗ lỗi thời đánh dấu "Cập nhật 24/09/2026" | 24/09 |
| 5 | [HUAN_LUYEN.md](HUAN_LUYEN.md) | Biên bản AI: phần I (21/09), II (22/09), III (22–23/09) | hiện hành; sửa và cập nhật 24/09 tại chỗ | 24/09 |
| 6 | [autopark/README.md](autopark/README.md) | Cách cài, chạy, kiểm thử; cấu trúc mã; quy ước | hiện hành (thêm lệnh BEV, ghi/phát lại, định vị LiDAR tối 24/09; muộn tối 24/09: số test sau bản sửa khoảng trống an toàn, tham chiếu máy bàn mới) | 24/09 |
| 7 | [autopark/docs/GIAI_DOAN_0.md](autopark/docs/GIAI_DOAN_0.md) | Biên bản cổng giai đoạn 0 | hồ sơ 20/09 (169 test, năm phiên đầu); số sau sửa ở tệp 8; ghi chú 24/09 cuối tệp | 24/09 |
| 8 | [autopark/docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md](autopark/docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md) | Kiểm thử mở rộng: 220 test, 2.880 ca, coverage | hồ sơ 20/09, vẫn đúng cho giai đoạn 0 | 24/09 |
| 9 | [autopark/docs/GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md) | Giấy phép từng bộ dữ liệu, quyết định 22/09 | hiện hành | 24/09 |
| 10 | [autopark/docs/GIAI_DOAN_1_CHUAN_BI.md](autopark/docs/GIAI_DOAN_1_CHUAN_BI.md) | Calibration WoodScape, ROI, costmap, nguồn phát lại, giám sát dữ liệu cũ, ONNX | hồ sơ 22/09; cập nhật 24/09 ở đầu tệp, mục 1, 5, 7 | 24/09 |
| 11 | [autopark/docs/GIAI_DOAN_1_LIDAR.md](autopark/docs/GIAI_DOAN_1_LIDAR.md) | Nhánh LiDAR: driver, ghi phiên, bản đồ tĩnh | hiện hành; kiểm lại 24/09 ở mục 3b; mục 8 (định vị) thêm 24/09 | 24/09 |
| 12 | [autopark/docs/GIAI_DOAN_1_CAMERA.md](autopark/docs/GIAI_DOAN_1_CAMERA.md) | Nhánh camera: mode, FPS, khung cũ, danh tính theo cổng | hồ sơ 23/09; **có đính chính ở mục 4.6**: chữ "sạch" ở mục 4.2–4.5 chỉ nói khung cũ | 24/09 |
| 13 | [autopark/docs/evidence/camera/report_20260923.md](autopark/docs/evidence/camera/report_20260923.md) | Báo cáo đo camera do công cụ tự sinh (12:23, 23/09) | bằng chứng lịch sử, trước khi có bộ dò khung bị cắt; đọc cùng tệp 12 mục 4.6 | 23/09 |
| 14 | [autopark/docs/usb_topology.md](autopark/docs/usb_topology.md) | Sơ đồ cổng USB, danh tính camera | hiện hành; cập nhật 24/09 | 24/09 |
| 15 | [autopark/docs/hardware_inventory.md](autopark/docs/hardware_inventory.md) | Kiểm kê phần cứng | hiện hành | 24/09 |
| 16 | [autopark/docs/gate_01.md](autopark/docs/gate_01.md) | Biên bản cổng giai đoạn 1 | hiện hành: CHƯA ĐẠT | 24/09 |
| 17 | [autopark/docs/GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md) | Bàn thử bốn camera + LiDAR + AI | hiện hành; mục 5–6 (loạt cũ) chỉ dùng được một phần; mục 10 thêm 24/09; mục 10.1–10.3 (quy tắc chờ theo nhịp riêng, đo lại, làm nóng AI) thêm tối 24/09 | 24/09 |
| 18 | [autopark/docs/HIEU_CHUAN_CAMERA.md](autopark/docs/HIEU_CHUAN_CAMERA.md) | Hiệu chuẩn nội tham camera | hiện hành; có đính chính cuối mục 5 (giao diện đã mở camera thật một lần) | 24/09 |
| 19 | [autopark/calibration/README.md](autopark/calibration/README.md) | Quy ước tệp `cam_p<N>.json` | hiện hành | 24/09 |
| 20 | [autopark/docs/GAN_NHAN_SA_BAN.md](autopark/docs/GAN_NHAN_SA_BAN.md) | Gán nhãn ảnh sa bàn | hiện hành | 24/09 |
| 21 | [autopark/docs/GIAI_DOAN_3_CHUAN_BI.md](autopark/docs/GIAI_DOAN_3_CHUAN_BI.md) | Hợp nhất cảm biến, demo LiDAR thật với xe ảo | hồ sơ 22/09; cập nhật 24/09 ở mục 1, 2, 3b, 6 | 24/09 |
| 22 | [autopark/docs/GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md) | Giao thức laptop–ESP32-S3, `VehicleIO`, firmware | hiện hành; mục 12 có ghi chú tối 24/09: `VehicleIO` đã nối vào phiên ở mức mô phỏng (xem tệp 29), và một khoảng trống an toàn đã biết, chưa sửa (test `xfail`, mục 4.9 tệp này); *muộn tối 24/09/2026:* khoảng trống đó đã sửa ở mức mô phỏng, không còn `xfail` (mục 4.9 tệp này) | 24/09 |
| 23 | [autopark/firmware/esp32_vehicle/README.md](autopark/firmware/esp32_vehicle/README.md) | Firmware C++: cấu trúc, CHƯA CHỐT, an toàn, cách biên dịch và thử | hiện hành; C++ chưa biên dịch | 24/09 |
| 24 | [autopark/datasets/DANH_MUC_DATASET.md](autopark/datasets/DANH_MUC_DATASET.md) | Danh mục 44 bộ/nhánh dataset | khảo sát 20/09; cột giấy phép có đính chính 24/09 ở đầu tệp | 24/09 |
| 25 | [autopark/datasets/TAI_VA_KIEM_TRA.md](autopark/datasets/TAI_VA_KIEM_TRA.md) | Các bộ đã tải và kiểm | hồ sơ 20/09; cập nhật 24/09 | 24/09 |
| 26 | [autopark/datasets/TRANG_THAI_TAI_DAY_DU.md](autopark/datasets/TRANG_THAI_TAI_DAY_DU.md) | Trạng thái tải đầy đủ | tệp do script tự sinh (19/09 UTC), thêm ghi chú tay 21/09 và 24/09; chạy lại script sẽ xóa ghi chú | 24/09 |
| 27 | [autopark/datasets/woodscape_metadata/README.md](autopark/datasets/woodscape_metadata/README.md) | README của Valeo đi kèm metadata WoodScape | bản sao của bên thứ ba, không phải tài liệu dự án | 21/09 |
| 28 | [autopark/docs/GHI_PHAT_LAI_BAN_THU.md](autopark/docs/GHI_PHAT_LAI_BAN_THU.md) | Ghi và phát lại phiên bàn thử (bốn camera + LiDAR) | hiện hành (tối 24/09); mục 7 là phiên thật đầu tiên | 24/09 |
| 29 | [autopark/docs/CHE_DO_QUAN_SAT.md](autopark/docs/CHE_DO_QUAN_SAT.md) | Nối `VehicleIO` vào phiên đỗ xe, chế độ quan sát | hiện hành (tối 24/09); chỉ mô phỏng và cổng serial giả; số test trong tệp (34/34, 17:41) cũ hơn tệp test hiện nay (49 đạt + 1 `xfail`, mục 4.9 tệp này; *muộn tối 24/09/2026:* 60 test, 60 đạt, 0 `xfail` sau bản sửa khoảng trống an toàn); *(cập nhật muộn tối 24/09/2026: câu "cũ hơn" không còn đúng. CHE_DO_QUAN_SAT.md đã tự ghi thêm ở mục 7: 60 test, 60 đạt, 0 `xfail`, cùng hai đột biến 28–29 của bản sửa; mục 8 ghi khoảng trống an toàn đã sửa, chỉ trên mô phỏng và cổng serial giả. Số 34/34 ở mục 7 được giữ làm lịch sử.)* | 24/09 |
| 30 | [autopark/docs/BEV.md](autopark/docs/BEV.md) | BEV chiếm chỗ từ AI nhiều camera | hiện hành (tối 24/09); rig tổng hợp, chưa chạy trên camera dự án | 24/09 |
| 31 | [autopark/docs/DINH_VI_LIDAR.md](autopark/docs/DINH_VI_LIDAR.md) | Định vị LiDAR trên bản đồ tĩnh (khớp scan, không phải SLAM) | hiện hành (tối 24/09); chưa có tham chiếu độc lập | 24/09 |
| 32 | [autopark/docs/GIAI_DOAN_4_CHUAN_BI.md](autopark/docs/GIAI_DOAN_4_CHUAN_BI.md) | Giai đoạn 4 khi chưa có xe: tham số cần đo, bảng đo B0–B8, độ nhạy planner, gá | bản nháp (tối 24/09); mọi số CHƯA ĐO | 24/09 |
| 33 | [autopark/docs/mn300_inventory.md](autopark/docs/mn300_inventory.md) | Phiếu kiểm kê MN300 để điền khi nhận xe | mẫu (tối 24/09); chưa điền, chưa có xe | 24/09 |
| 34 | [autopark/docs/GIAI_DOAN_6_CHUAN_BI.md](autopark/docs/GIAI_DOAN_6_CHUAN_BI.md) | Nguồn và dừng: nháp bảng tải, sơ đồ nguồn/dừng, định mức, 16 kịch bản lỗi | bản nháp (tối 24/09); CHƯA ĐO, CHƯA THỬ | 24/09 |
| 35 | [autopark/docs/DAN_Y_KHOA_LUAN.md](autopark/docs/DAN_Y_KHOA_LUAN.md) | Dàn ý khóa luận đề xuất, mức sẵn sàng từng chương | bản nháp (24/09, cập nhật tối 24/09 theo bảy việc mới; muộn tối 24/09: bản sửa khoảng trống an toàn, tham chiếu máy bàn 19:08, số test); mẫu của trường chưa biết | 24/09 |
| 36 | [autopark/docs/evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json](autopark/docs/evidence/rig/cho_nhip_rieng_ghi_phat_lai_20260924.json) | Bản rút gọn số đo bàn thử tối 24/09 (m01/m02, o01–o07, lô đầu từng cỡ) | bằng chứng; tệp gốc ở `runs/` (git-ignore); **chưa commit** (tệp chưa theo dõi; *thêm muộn tối 24/09/2026*) | 24/09 |
| 37 | [autopark/docs/MAY_NOP_DO_AN.md](autopark/docs/MAY_NOP_DO_AN.md) | Laptop RTX 3050 Ti (máy nộp đồ án): chép checkpoint, cài `.venv`/`.venv-train` (`cai_dat.cmd`, `cai_dat_train.cmd`), một lệnh đo `do_may_moi.cmd` (`autopark.rig.may_moi`), so với tham chiếu máy bàn | hiện hành (24/09), chưa chạy trên laptop; *(cập nhật tối 24/09/2026)* tham chiếu máy bàn (tệp 38) đo 15:25, trước quy tắc chờ theo nhịp riêng và làm nóng AI; số tối 24/09 ở tệp 36; *muộn tối 24/09/2026:* có tham chiếu mới đo bằng mã mới lúc 19:08 (tệp 39), `may_moi` dùng tệp này | 24/09 |
| 38 | [autopark/docs/evidence/may_ban/tham_chieu_20260924.json](autopark/docs/evidence/may_ban/tham_chieu_20260924.json) | Tham chiếu máy bàn cho lệnh đo máy mới: bản rút gọn lần chạy `may_moi` đầy đủ lúc 15:25 ngày 24/09 (cấu hình, USB, LiDAR, AI, bàn thử 480p = m01 và 720p = m02) | bằng chứng; máy bàn 15:25 24/09, quy tắc chờ cũ, chưa làm nóng AI; *từ muộn tối 24/09/2026 chỉ giữ để đối chiếu*, `may_moi` dùng tệp 39 | 24/09 |
| 39 | [autopark/docs/evidence/may_ban/tham_chieu_20260924_toi.json](autopark/docs/evidence/may_ban/tham_chieu_20260924_toi.json) | Tham chiếu máy bàn mới cho lệnh đo máy mới (*thêm muộn tối 24/09/2026*): bản rút gọn lần `may_moi` đầy đủ lúc 19:08 bằng mã mới (quy tắc chờ theo nhịp riêng, làm nóng AI; `ai_warm_up_ms`); tệp gốc `runs/may_moi_20260924_toi/` | bằng chứng; máy bàn 19:08 24/09, camera nhìn chỗ tối; **chưa commit** | 24/09 |

## 7. Cách đọc bằng chứng và quy ước

**Mức bằng chứng và cách ghi:**

- Ba mức mô phỏng / bàn thử máy bàn / xe thật không thay nhau (mục 1).
- "Giả định" = số chưa đo (ví dụ `configs/vehicle_default.json`, `configs/vehicle_io_sim.json`, `configs/rig/camera_rig_extrinsics_v0.json`). "Đề xuất" = ngưỡng chưa kiểm trên thiết bị thật. "Chưa đo", "chưa xác nhận" = đúng như chữ.
- Trạng thái giai đoạn dùng `CHƯA LÀM / ĐANG LÀM / CHƯA ĐẠT / ĐẠT` (kế hoạch mục 2.3).
- Mọi số đo là của một phiên cụ thể trên một máy cụ thể, không phải cam kết. Ngày giờ là giờ máy (UTC+7); tệp đo ghi thêm `created_utc`.

**Đơn vị và hệ tọa độ:**

- Mã dùng mét, giây, radian. Giao thức dây dùng số nguyên mm/s, mrad, ms.
- Tư thế xe tại tâm trục sau; x hướng trước, y sang trái, yaw dương ngược chiều kim đồng hồ. Quy ước này trùng hệ xe ISO 8855 của WoodScape.
- LiDAR: góc thiết bị tăng theo chiều kim đồng hồ; driver đổi dấu để ra góc dương ngược chiều kim đồng hồ. Dấu trái/phải **chưa xác minh bằng vật thật**.
- Costmap: `cells[row][col]`, row theo y, col theo x, gốc tại `(x_min, y_min)`.
- Camera gọi theo cổng hub 1–4 (`cam_p1` … `cam_p4`), không theo index OpenCV.

**Thời gian:**

- Bàn thử dùng một đồng hồ `perf_counter` cho mọi luồng. Stamp camera = lúc `read()` trả khung (đã gồm giải mã), không phải lúc phơi sáng. Stamp LiDAR = lúc byte cuối của vòng tới máy. Telemetry xe = lúc laptop nhận.
- `bench` và `live_view` của LiDAR dùng `time.monotonic`, bước 15,6 ms trên Windows.
- *(Thêm tối 24/09/2026)* Phát lại bản ghi bàn thử: stamp được đổi gốc sang đồng hồ phát lại; khoảng cách giữa các stamp giữ nguyên (chia cho speed). `SerialVehicleIO` mặc định dùng `time.perf_counter` (trước tối 24/09 là `time.monotonic`).

**Thuật ngữ:**

- Nhãn AI: 0 FREE, 1 BLOCKED, 255 IGNORE. "Vật cản → FREE" là lỗi nguy hiểm (có thể đâm). "FREE → vật cản" là báo động giả (chỉ làm xe dừng). Ngưỡng 0,50 là argmax; 0,15 là ngưỡng thiên về an toàn.
- Camera: "khung cũ" = driver trả lại đúng khung trước; "khung bị cắt/xé" = khung MJPEG thiếu dữ liệu, phần thiếu bị tô vân xám. Camera "thiếu" = không có khung tốt trong 0,5 s; camera "chậm" = bị bỏ khỏi bộ vì chờ quá ≈ 62 ms. *(Cập nhật tối 24/09/2026:)* từ quy tắc theo nhịp riêng, camera "chậm" = bị bỏ khỏi bộ vì chờ quá ngưỡng riêng của nó (≈ 63 ms ở 24 khung/s), vì lỡ khung đúng lượt, vì khung đúng lượt hỏng, hoặc vì treo (mục 4.5).
- Tên phiên: p07, k01 = phiên đo LiDAR; m*, n*, q* = phiên đo camera ngày 23/09; s*, t*, u*, a*, f*, d01 = bàn thử ngày 23/09; w01–w05 = bàn thử ngày 24/09. *(Thêm tối 24/09:)* m01, m02 cũng là tên phiên `may_moi` lúc 15:25 ngày 24/09 trên máy bàn (`runs/may_moi_20260924_may_ban/`), **trùng tên** với phiên camera m01, m02 ngày 23/09; luôn ghi kèm ngày. *(Thêm muộn tối 24/09/2026:)* lần `may_moi` lúc 19:08 cũng đặt tên m01, m02 (`runs/may_moi_20260924_toi/`); ghi kèm cả giờ (15:25 hay 19:08). o01–o07 = bàn thử tối 24/09 (`runs/rig_bench/20260924_own/`); o04–o06 là phát lại bản ghi o03. live_headless = bản ghi LiDAR 22/09 dùng để thử định vị.

**Tệp không có trên GitHub** (git-ignore): `autopark/runs/`, `autopark/datasets/prepared/`, `autopark/datasets/download_metadata/` (có biên bản CRC mà TRANG_THAI_TAI_DAY_DU.md dẫn link), dataset, checkpoint, `autopark/review_artifacts/`, `autopark/docs/evidence/coverage_html/`, và mọi tệp `*.csv` trừ `docs/evidence/*.csv` và `docs/camera_modes.csv`. Link tới các thư mục này chỉ mở được trên máy có dữ liệu. Bản sao nhỏ của vài bằng chứng nằm trong `autopark/docs/evidence/`, có trên GitHub.
