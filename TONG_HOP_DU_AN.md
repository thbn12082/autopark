# Tổng hợp dự án xe mô hình tự đỗ — theo mảng (24/09/2026)

> **Ghi công bắt buộc theo giấy phép dữ liệu:** nghiên cứu nhận thức trong dự án này được thực hiện với **Valeo WoodScape Dataset** (<https://woodscape.valeo.com>, [repo](https://github.com/valeoai/WoodScape)). Giới hạn sử dụng: [autopark/docs/GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md).

**Dành cho:** sinh viên làm khóa luận và giảng viên hướng dẫn. Đọc tệp này trước để biết dự án đang ở đâu, rồi theo link vào tài liệu chi tiết. Tệp này chỉ tóm tắt. Khi có chỗ khác nhau, tài liệu chi tiết và tệp đo trong `autopark/runs/` là nguồn gốc.

**Nguồn:** tài liệu trong repo sau đợt rà soát tài liệu chiều 24/09/2026, mã nguồn và tệp đo. Mỗi con số dưới đây lấy
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

---

## 1. Mục tiêu V1, phạm vi và mức bằng chứng

**V1 phải làm** ([kế hoạch v3.1](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 1.2): người dùng đặt đích trên giao diện. Xe tìm và chạy quỹ đạo tiến/lùi hợp với cơ cấu lái. LiDAR cho bản đồ và định vị; bốn camera cho nhận thức cục bộ. Khi có vật cản, hoặc dữ liệu cần thiết không còn hợp lệ, hệ thống dừng và đánh giá lại.

**Không bắt buộc trong V1:** nhận diện vạch đỗ, tự tìm ô đỗ, tự lái tới bãi, điều khiển end-to-end bằng mạng neural, MPC nâng cao, dự đoán chuyển động người, tái dựng 3D.

**Cấu hình giữ nguyên** (mục 1.1): xe MN300 Tank300 1/12, laptop xử lý chính, RPLIDAR C1, bốn camera USB, một ESP32-S3 điều khiển cấp thấp.

**Điều kiện hoàn thành V1** (mục 16.4): 10 điều kiện, **chưa điều kiện nào đạt** (24/09/2026). Các ngưỡng của mục 16.2 (camera, hình học, AI, định vị, điều khiển, tự đỗ, phản ứng lỗi) vẫn ở trạng thái "cần chốt".

Kế hoạch (mục 1.3) tách ba mức bằng chứng. Kết quả ở mức dưới không thay được mức trên:

| Mức | Đã có (24/09/2026) |
|---|---|
| Mô phỏng | Giai đoạn 0 ĐẠT sáu điều kiện chuyển bước (20/09). Xe ảo lập đường quanh vật thật do LiDAR đứng yên quét, và đỗ xong (22/09); phép thử "vật mới làm xe ảo dừng" mới chạy với nguồn quét kịch bản. `VehicleIO` mô phỏng giao thức xe (24/09). |
| Bàn thử trên máy bàn | LiDAR C1 và bốn camera USB nằm trên bàn, chưa gá. AI chạy trực tiếp trên bốn camera để đo thời gian và xem lớp tô (23–24/09). Chưa có số đo nào trên laptop sẽ đặt lên xe. |
| Xe thật | Chưa có. Chưa nhận MN300, ESP32-S3 và phần nguồn/dừng. |

AI mới được chấm trên ảnh lưu sẵn của bộ dữ liệu công khai, chưa chấm trên ảnh sa bàn có nhãn.

## 2. Thiết bị

**Đã nhận** ([hardware_inventory.md](autopark/docs/hardware_inventory.md)):

| Thiết bị | Nhận | Tình trạng |
|---|---|---|
| RPLIDAR C1, adapter CP2102N, cổng COM4 | 22/09 | Đọc scan được trên máy bàn. Health OK ngày 22/09 và 24/09, cùng serial `f57ffc8b…`, firmware 1.2. Sai số khoảng cách so với thước **chưa đo**. Model in trên nhãn chưa ghi. |
| Bốn camera USB "HD Camera" (VID 1BCF / PID 0B09, không có serial) | 23/09 | 130° là số nhà bán, góc nhìn thật **chưa đo**. Chưa gá, chưa hiệu chuẩn. Danh tính của camera là cổng hub nó cắm vào. |
| Hub UGREEN 4 cổng (chip Genesys Logic) | 23/09 | Cả bốn camera chung một nhánh USB 2.0. Hub chạy bus-powered trong mọi phiên ngày 23/09; thử nguồn ngoài **chưa làm**. Mã model chưa ghi. |

**Chưa nhận:** MN300, ESP32-S3, BNO085, VL53L1X, AS5600 + nam châm, encoder (MT6701 hoặc loại khác), bộ nguồn (UBEC hay XL4015 chưa chọn), cầu chì, nút E-stop LA38, phần tử ngắt động lực.

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

Cột "Trạng thái" lấy từ bảng theo dõi của kế hoạch (mục 17.4, cập nhật 24/09). Bốn cột số là kết quả đợt rà soát kế hoạch ngày 24/09: mỗi việc trong kế hoạch được xếp vào một trong bốn loại. Bảng chi tiết của đợt rà soát (275 việc, trạng thái, bằng chứng và cái đang chặn từng việc) lưu ở [autopark/docs/evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json](autopark/docs/evidence/ke_hoach/kiem_toan_ke_hoach_20260924.json); bảng 17.4 vẫn là hồ sơ chính thức của kế hoạch. Đây là số việc, không phải tỉ lệ hoàn thành (kế hoạch mục 1.3 không cho tự gán tỉ lệ hoàn thành).

| GĐ | Nội dung | Trạng thái (17.4) | Xong | Một phần | Chưa bắt đầu | Chờ thiết bị chưa mua | Cổng chuyển bước |
|---|---|---|---:|---:|---:|---:|---|
| 0 | Phần mềm, mô phỏng | ĐẠT (mô phỏng, 20/09) | 24 | 0 | 0 | 0 | ĐẠT ở mức mô phỏng ([GIAI_DOAN_0.md](autopark/docs/GIAI_DOAN_0.md)) |
| 1 | LiDAR + camera mẫu | ĐANG LÀM | 11 | 17 | 2 | 0 | CHƯA ĐẠT ([gate_01.md](autopark/docs/gate_01.md)) |
| 2 | Bốn camera, BEV | ĐANG LÀM | 6 | 14 | 10 | 2 | chưa đạt, chưa có biên bản |
| 3 | Hợp nhất trên bàn thử | ĐANG LÀM (phần mềm, chưa có IMU/ToF/ESP32) | 5 | 11 | 2 | 6 | chưa đạt |
| 4 | Đo đặc tính MN300 | ĐANG LÀM (phần "khi chưa có xe") | 0 | 2 | 2 | 19 | chưa đạt |
| 5 | ESP32-S3, điều khiển có phản hồi | ĐANG LÀM (phần "khi chưa đủ phần cứng") | 3 | 7 | 0 | 15 | chưa đạt |
| 6 | Nguồn, dừng an toàn | ĐANG LÀM (phần "khi chưa có nguồn final") | 0 | 5 | 4 | 15 | chưa đạt |
| 7 | Chuyển cảm biến lên xe | CHƯA LÀM | 0 | 1 | 1 | 12 | chưa đạt |
| 8 | Hợp nhất trên xe chuyển động | ĐANG LÀM (phần "khi chưa thể chạy trên xe") | 1 | 7 | 1 | 7 | chưa đạt |
| 9 | Tự đỗ thật, xử lý vật cản | CHƯA LÀM phần chạy thật | 0 | 3 | 2 | 14 | chưa đạt |
| 10 | Đánh giá, khóa luận | ĐANG LÀM (phần "khi chưa đủ bộ xe") | 0 | 10 | 3 | 7 | chưa đạt |
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

**Tiếp theo:** khi có MN300, thay thông số giả định bằng số đo (giai đoạn 4) rồi chạy lại chiến dịch.

### 4.2. AI nhận thức, dữ liệu và giấy phép

**Trạng thái:** baseline L-RASPP + MobileNetV3-Large, hai lớp FREE / BLOCKED (255 = IGNORE). Checkpoint tham chiếu `runs/ai_woodscape_rtx4000_v1/best.pt` (21/09). Từ 23/09 mô hình chạy trực tiếp trên bốn camera của bàn thử, nhưng chỉ để đo thời gian và xem lớp tô. **Chưa nối vào costmap hay planner.**

**Số liệu chính** (máy bàn):

- WoodScape test giữ riêng, chấm một lần (21/09): mIoU 0,9692; 1,75 % pixel vật cản bị gọi là FREE. Ba seed (22/09): test 0,9693 ± 0,0001.
- Ngoài miền (22/09): ACDC thời tiết xấu mIoU 0,908, vật cản → FREE 4,42 % (ban đêm 8,38 %). RoadObstacle21 (vật lạ nhỏ, 30 ảnh): recall 68,3 %, vật cản → FREE 31,7 %.
- Ngưỡng 0,15, chọn trên val theo F2: vật cản → FREE còn 0,69 % (WoodScape test), 2,28 % (ACDC), 18,2 % (RoadObstacle21). Đổi lại báo động giả tăng, ví dụ WoodScape test 1,37 → 3,97 %.
- Thêm AVM-SS và ACDC (22–23/09; ba seed cho lượt nền, lượt trộn WoodScape + AVM và lượt trộn có trọng số lớp; AVM-SS riêng và lượt trộn ba bộ mỗi lượt một seed): không lượt nào vượt lượt nền trên hai tập chưa chạm. Trộn WoodScape + AVM làm vật cản → FREE trên ACDC tăng từ 4,1 ± 0,4 % lên 13,5 ± 2,8 %. Trọng số lớp không phải cách gỡ.
- Độ trễ một ảnh khi GPU rảnh (22/09): torch CUDA fp32 4,4 ms; onnxruntime CPU 7,6 ms. Trên bàn thử (23/09, u01): lô bốn ảnh 640×480 trung vị 16,4 ms.
- Ảnh camera thật đầu tiên (23/09, chưa có nhãn): lượt nền gọi BLOCKED 11 / 31 / 39 / 60 % pixel ở cổng 1–4 (ngưỡng 0,50). Nhìn bằng mắt, ở cổng 2–4 phần lớn vùng đó là thảm hoa văn, tức báo động giả. Chưa phải số đo so với nhãn.

**Dữ liệu:** danh mục 44 bộ/nhánh (20/09). Đã tải và kiểm AVM-SS (6.763 cặp), DROW v2 (464.023 scan), WoodScape (8.234 cặp), ACDC, RoadAnomaly21, RoadObstacle21. Các ZIP gốc đã được chuyển đi ngày 21/09; bản giải nén là bản duy nhất đã biết trên máy.

**Giấy phép** ([GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md), kiểm 22/09 và 24/09): điều khoản WoodScape cấm dùng mô hình huấn luyện trên nó để vận hành hoặc hỗ trợ vận hành phương tiện. Ngày 22/09 người làm khóa luận chọn cách hiểu: xe 1/12 trên sa bàn trong phòng thuộc "personal experimentation" và "academic research". **Valeo chưa xác nhận cách hiểu này.** AVM-SS không có giấy phép (tác giả giữ toàn quyền). ACDC chỉ cho mục đích phi thương mại, không có điều khoản về phương tiện. Giấy phép RoadObstacle21 chưa xác minh.

**Giới hạn:** chưa chấm trên ảnh sa bàn có nhãn. Split WoodScape chưa loại trừ rò rỉ bối cảnh. RoadAnomaly21 chưa chấm. Mô hình yếu về đêm, yếu với vật lạ nhỏ, không phân biệt vỉa hè với đường. Huấn luyện không tái lập từng bit trên GPU. Độ trễ chưa đo trên laptop RTX 3050 Ti (máy nộp đồ án).

**Tài liệu:** [HUAN_LUYEN.md](HUAN_LUYEN.md) phần I–III; [GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md); [GIAI_DOAN_1_CHUAN_BI.md](autopark/docs/GIAI_DOAN_1_CHUAN_BI.md) (ROI, costmap, ONNX); [DANH_MUC_DATASET.md](autopark/datasets/DANH_MUC_DATASET.md), [TAI_VA_KIEM_TRA.md](autopark/datasets/TAI_VA_KIEM_TRA.md).

**Tiếp theo:** chụp ảnh sa bàn ở độ cao thật, gán nhãn, dựng thêm tập chấm tô tay từ đầu, rồi chấm ba checkpoint ở hai ngưỡng 0,50 và 0,15 (HUAN_LUYEN.md mục 18). Chốt hướng giấy phép trước khi nối AI vào costmap/planner.

### 4.3. LiDAR RPLIDAR C1

**Trạng thái:** đọc scan, ghi/phát lại phiên, bản đồ lưới tĩnh, tất cả trên máy bàn. Theo gate 1: đọc scan ĐẠT (trên máy bàn), tạo map MỘT PHẦN, định vị CHƯA.

**Số liệu chính:**

- 22/09 (phiên p07, 17,8 s, không làm nóng): 10,09 Hz; trung vị 508 tia/vòng; 0 byte lệch trong 91.507 node; 34,6 % tia không phản hồi ở chỗ đặt đó; phản hồi 0,09–14,6 m; node đầu tới sau ≈ 2,2 s kể từ lệnh SCAN. Hai số đầu tính cả lúc mô-tơ khởi động.
- Bản đồ lưới tĩnh từ p07: 160 × 160 ô 5 cm, 5.657 ô FREE, 230 ô OCCUPIED. Ngày 24/09 nạp lại và ghi lại tệp `costmap.json` thật cho kết quả bằng nhau.
- **Kiểm lại 24/09** (phiên k01, `autopark/runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.*`, ghi 15 s sau 3 s làm nóng, LiDAR đã dời chỗ): cùng model, firmware 1.2, phần cứng 18 và cùng serial; health OK. 151 vòng; 0 lỗi đọc, 0 byte lệch, 0 vòng bị bỏ. Số gộp 9,98 Hz, trung vị 512 tia/vòng (492–552).
- Bỏ 3 s đầu mỗi bản ghi thì cả 22/09 và 24/09 đều ≈ 10,0 Hz, ≈ 510 tia/vòng (504–516). Chênh lệch giữa 10,09 và 9,98 Hz là do đoạn khởi động mô-tơ nằm trong bản ghi; chưa thấy dấu hiệu thiết bị thay đổi.
- Độ lặp lại khoảng cách giữa hai vòng liên tiếp, trên mặt tĩnh 0,2–4 m: trung vị chênh 1,0–1,5 mm, p90 4–8 mm (script tạm ngày 24/09, không lưu trong repo). Đây không phải sai số so với thước.
- Cộng bộ đếm driver của 26 phiên ghi 22–24/09: 33.932 vòng, 0 byte lệch, 0 vòng bị bỏ; 5 lần đóng vòng theo điểm góc (≈ 1/6.800 vòng). Ba phiên 10 phút trên bàn thử (s07, t09, u04): 6.006 / 6.005 / 6.006 vòng, 0 lỗi đọc, 0 vòng mất.

**Chưa kiểm / còn mở:**

- **Sai số khoảng cách so với thước chưa đo.** Cần 7 lần đặt hộp p01–p06 và p08 (GIAI_DOAN_1_LIDAR.md mục 6). Dấu góc trái/phải chưa xác minh bằng vật thật (mục 6b).
- Đỉnh khởi động 552 tia (k01), cao hơn 536 (p07) và 540 (live_headless). Mới có ba lần khởi động được ghi, chưa đủ để kết luận.
- Có tia rất gần (0,135–0,173 m), chất lượng thấp, ở hai vùng góc cố định (k01: −56…−52° và −30…−28° theo quy ước dự án), thấy cả ở chỗ đặt cũ. Nghi dây cáp, chưa kiểm.
- `bench` và `live_view` đóng dấu bằng `time.monotonic` (bước 15,6 ms trên Windows), nên số chu kỳ trong các bản ghi đó bị lượng tử hóa.
- Chưa rút cáp để xem `STALE_DATA` trên thiết bị thật. Chưa đo trên laptop RTX 3050 Ti (máy nộp đồ án). Chưa có SLAM/định vị. Chưa dùng chế độ DenseBoost.

**Tài liệu:** [GIAI_DOAN_1_LIDAR.md](autopark/docs/GIAI_DOAN_1_LIDAR.md) (mục 3, 3b, 6, 6b), [hardware_inventory.md](autopark/docs/hardware_inventory.md), [gate_01.md](autopark/docs/gate_01.md).

**Tiếp theo:** phiên đặt hộp 7 lần (cần người); thử rút cáp; xác định vật ở hai vùng góc gần; chọn phương án SLAM/định vị và kiểm đầu vào của nó (mục 5.4).

### 4.4. Camera USB và khung MJPEG bị cắt

**Trạng thái:** bốn camera đã đo trên máy bàn (23–24/09). Từ 23/09 mặc định 640×480 MJPG. Bộ dò `truncated_rows` / `torn_bands` loại khung hỏng trước khi tới AI. Bộ dò còn bỏ sót khi bộ giải mã tô bằng màu phẳng, khi khung bị cắt giữa hàng khối cuối, hoặc khi dải xé bắt đầu cách mép phải dưới 64 điểm. Chưa có phép kiểm độc lập bằng byte MJPEG thô (GIAI_DOAN_2_BAN_THU.md mục 2.2).

**Số liệu chính:**

- Mode công bố: MJPG 640×480, 1280×720, 1920×1080, đều 30 fps. Đo được ≈ 23,85 khung/s ở phơi sáng tự động, nhịp xen kẽ ≈ 31 ms và ≈ 48 ms. Ép phơi sáng thủ công thì 29,3 khung/s nhưng ảnh gần đen. Cơ chế chưa xác định.
- Khung bị cắt khi chạy chung (23/09, camera nhìn thảm hoa văn): chạy một mình thì không camera nào bị cắt. Ở 720p/1080p với cả bốn camera, hai–ba camera bị cắt phần lớn khung (r04, r08, r09, r11). Với ba camera ở 720p, chỉ một camera bị cắt phần lớn khung (r03: cổng 1 97 %; r05: cổng 4 67 %). Ví dụ phiên u02 (720p, cùng LiDAR + AI, 60 s): cổng 1 và cổng 4 có 1.431 và 1.430 khung bị cắt, còn 0,0 khung tốt/s.
- 640×480, 18 phiên ngày 23/09: cổng 1 hỏng 1.418 / 31.142 khung (4,6 %), gần hết trong hai đợt 26,3 % và 36,2 %; cổng 2 và 3: 0; cổng 4: 6 khung. Nguyên nhân các đợt của cổng 1 chưa rõ.
- 24/09 (phiên w03, w04; 720p × 4, 60 s, camera nhìn chỗ tối): 0 khung bị cắt/xé. Đây thêm một dấu hiệu mức cắt phụ thuộc cảnh (kích thước JPEG), **không** phải bằng chứng 720p dùng được.
- Khung hỏng mà tới được AI thì vùng vân xám bị gọi gần hết là FREE. Số đo trên hai khung 720p của bộ ảnh 14:57 ngày 23/09, chụp trước khi có bộ lọc (cổng 1: 450.551 / 450.560 pixel của phần đáy ở ngưỡng 0,50). Đó là lỗi theo hướng không an toàn. Mới đo trên hai khung mà bộ dò bắt được; chưa đo trên khung thật sự lọt bộ dò.
- Sau khởi động lại máy (23/09), InstanceId theo cổng giữ nguyên nhưng index OpenCV đổi. Vì vậy mã chọn camera theo cổng hub.

**Chưa kiểm:** nguyên nhân khung bị cắt (giả thuyết băng thông USB 2.0 dùng chung qua hub, chưa chứng minh; chưa đọc được byte MJPEG thô); tách camera ra nhiều cổng gốc; nguồn ngoài cho hub; băng thông mỗi camera; đổi cổng camera; góc nhìn thật; độ nét ở độ cao dự kiến; độ trễ từ sự kiện thật tới máy (cần LED nháy); nhiệt CPU; mọi số trên laptop RTX 3050 Ti (máy nộp đồ án).

**Tài liệu:** [GIAI_DOAN_1_CAMERA.md](autopark/docs/GIAI_DOAN_1_CAMERA.md) (đính chính ở mục 4.6), [usb_topology.md](autopark/docs/usb_topology.md), [GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md) mục 2, [camera_modes.csv](autopark/docs/camera_modes.csv).

**Tiếp theo:** tách camera ra nhiều cổng gốc rồi chạy lại 720p với cảnh sáng, nhiều chi tiết; thử nguồn ngoài cho hub; đổi chỗ camera cổng 1 và cổng 2 để tách lỗi "camera" với lỗi "cổng".

### 4.5. Bàn thử bốn camera + LiDAR + AI và quy tắc không chờ camera chậm

**Trạng thái:** bốn camera, LiDAR và AI chạy chung ổn trên máy bàn ở 640×480 (23/09). Từ 24/09, AI không chờ camera chậm (mặc định bật).

**Số liệu chính** (23/09, loạt `autopark/runs/rig_bench/20260923_v3/`):

- u01 (120 s): 4 × 23,8–23,9 khung tốt/s, 0 khung hỏng. AI chấm 23,8 bộ/s; lô bốn ảnh trung vị 16,4 ms (mạng 11,6 ms). Kết quả AI có mặt 34,8 ms (trung vị) sau khi khung cũ nhất của bộ tới máy.
- u01: độ lệch trong bộ ảnh trung vị 15,0 ms, p95 24,1 ms. Điểm giữa vòng LiDAR sớm hơn mốc bộ ảnh ≈ 80 ms (trung vị). GPU trung bình 26 %, 41 → 46 °C.
- u04 (600 s): 6 khung hỏng (cổng 4). AI 23,1 bộ/s, 15,6 ms/lô. LiDAR 6.006 vòng, 0 vòng mất.

**Quy tắc không chờ** (24/09, GIAI_DOAN_2_BAN_THU.md mục 10): khi một camera chưa có khung mới, bàn thử chờ tối đa L = max(60 ms; 1,5 × chu kỳ khung của camera nhanh nhất), tức ≈ 62 ms ở 24 khung/s, rồi ghép bộ không có camera đó. Tham số `--max-wait-ms` (0 = quy tắc cũ).

- Năm phiên w01–w05 (12:13–12:22 ngày 24/09; ba phiên bật w01, w03, w05, hai phiên tắt w02, w04): ở ba phiên bật, 0 bộ thiếu camera khỏe trong 7.155 bộ. Số bộ/s bằng lúc tắt.
- Tuổi kết quả AI ≈ 37–42 ms khi bật, ≈ 62 ms khi tắt. Cơ chế chưa giải thích được, nên chưa coi là lợi ích.
- **Lợi ích chính chưa thấy trên phần cứng:** không phiên nào có camera chậm.
- Trong mô phỏng, khi pha từng camera trôi, mỗi cổng khỏe vẫn bị bỏ 0,2–2,7 % số bộ. Chưa sửa.

**Giới hạn:** mọi stamp là lúc dữ liệu tới máy, không phải lúc phơi sáng. Khi đo, một dự án khác chạy cùng máy (có ghi CPU cả máy). Nhiệt CPU không đọc được vì không có quyền admin. Lớp tô AI chỉ để nhìn. Chưa có BEV, chưa chiếu kết quả AI xuống sàn.

**Tài liệu:** [GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md) (mục 3–4 số đo chính thức, mục 5–6 loạt cũ, mục 10 quy tắc không chờ).

**Tiếp theo:** chạy một phiên có camera chậm thật, bật và tắt quy tắc; đo độ trễ bằng LED nháy; chạy lại `rig.bench` trên laptop RTX 3050 Ti (máy nộp đồ án).

### 4.6. Hiệu chuẩn camera

**Trạng thái:** công cụ có từ 24/09. **Chưa hiệu chuẩn camera nào; bảng chưa in.**

**Đã có:** bảng in sẵn A4 ô 20 mm và A3 ô 30 mm (`autopark/calibration/bang_in/`); hiệu chuẩn Kannala–Brandt bằng `cv2.fisheye`, luôn tinh chỉnh góc bằng `cornerSubPix`; giao diện chụp `ui/calib_app.py`. Tệp ra là `calibration/cam_p<cổng>.json`, chỉ chứa nội tham, mặc định ở mode 640×480.

**Số liệu** (ảnh tổng hợp dựng qua một camera đã biết): fx tìm được 351,03 so với 351,0 thật; RMS chiếu lại 0,071 px; sai lệch mô hình trung vị 0,05 px, lớn nhất 0,49 px ở góc ảnh (vùng ngoại suy). Giao diện đã mở camera thật cổng 2 một lần (24/09, ≈ 6 s, 0 khung hỏng) nhưng không chụp ảnh nào.

**Giới hạn:** các tiêu chí chấp nhận (RMS ≤ 0,5 px, ≥ 15 ảnh, phủ ≥ 70 % lưới…) chỉ là đề xuất. Chưa biết ống kính thật có khớp mô hình 4 hệ số không. Chưa có ngoại tham (`camera_rig_extrinsics.yaml`) và chưa có công cụ cho nó. `CameraCalibration.from_dict` chưa nạp thẳng được `cam_p*.json`. Chưa có mặt nạ ROI cho camera của dự án.

**Tài liệu:** [HIEU_CHUAN_CAMERA.md](autopark/docs/HIEU_CHUAN_CAMERA.md), [autopark/calibration/README.md](autopark/calibration/README.md).

**Tiếp theo:** in bảng đúng 100 %, đo cỡ ô bằng thước, chụp 20–30 ảnh mỗi camera, so K của bốn camera với nhau. Chọn cách đo ngoại tham khi có gá.

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

**Giới hạn:** chưa thử đưa tay/hộp hoặc rút cáp với LiDAR thật khi xe ảo đang chạy (mới kiểm bằng nguồn quét kịch bản). ToF chỉ có số đo giả. Lớp camera chưa có khung thật đi qua. Chưa có định vị. Bỏ 15 vòng đầu chưa phủ hết giai đoạn khởi động mô-tơ: số tia đạt đỉnh ở vòng 16–17 và ổn định từ vòng 21–22 (ghi chú 24/09). Chưa có mã đổi `VehicleTelemetry` sang `NearFieldReading`.

**Tài liệu:** [GIAI_DOAN_3_CHUAN_BI.md](autopark/docs/GIAI_DOAN_3_CHUAN_BI.md); giám sát dữ liệu cũ ở [GIAI_DOAN_1_CHUAN_BI.md](autopark/docs/GIAI_DOAN_1_CHUAN_BI.md) mục 4.

**Tiếp theo:** thử đưa tay và rút cáp (cần người); tăng `initial_skip` hoặc chờ theo thời gian nếu bản đồ nền bị ảnh hưởng; đọc ToF/IMU thật khi có ESP32.

### 4.9. Giao thức xe, VehicleIO và firmware ESP32-S3

**Trạng thái:** phần mềm và mô phỏng (24/09). **Firmware C++ chưa biên dịch lần nào** vì máy không có trình biên dịch C/C++ hay PlatformIO. Chưa có bo.

**Đã có:** khung COBS + CRC-16/CCITT-FALSE, bảy loại thông điệp, phiên và số thứ tự; bản tham chiếu Python của firmware; `VehicleIO` hai nhánh (mô phỏng và serial) đi qua cùng byte; vector mẫu chung cho Python và C++.

**Cơ chế an toàn trong phần mềm:** mỗi lệnh có thời hạn (laptop gửi 150 ms, bo kẹp ≤ 300 ms). Watchdog liên lạc của bo: 500 ms → DISARMED. Laptop chốt `TELEMETRY_STALE` sau 0,3 s và phải `arm()` lại. Reset và kết nối lại luôn về DISARMED. E-stop chốt FAULT. Trần effort 250 ‰ (CHƯA CHỐT). Lỗi STALL ở vòng kín.

**Số liệu** (24/09, `.venv`): 184 test đạt, 0 lỗi (giao thức 52, bản tham chiếu firmware 73, VehicleIO 48, kiểm tĩnh C++ 11). Ba đợt đột biến mã (21, 22, 22 đột biến); sau khi thêm test, mọi đột biến đều bị bắt. Riêng 13 đột biến trên mã C++ của đợt ba chỉ bị bắt bằng kiểm tĩnh mã nguồn, không phải bằng chạy mã (C++ chưa biên dịch). Mô phỏng vòng tốc độ với số giả định: sai số trung bình < 1 mm/s nhưng vọt lố 26–57 %. Ngừng gửi lệnh lúc 0,15 m/s thì xe mô phỏng dừng sau 0,39 s, trôi 3,9 cm. Đó là số của mô hình, không phải quãng dừng xe thật.

**CHƯA CHỐT theo bo thật:** chân GPIO, xung ESC/servo, hành vi ESC khi mất xung và khi lùi, đường vật lý khi lên xe, hệ số PI/feedforward.

**Giới hạn:** chưa có mã đọc encoder, AS5600, BNO085, VL53L1X, điện áp. `VehicleIO` chưa nối vào phiên và bộ bám quỹ đạo; chưa ghi `commands.csv` / `telemetry.csv`. Không xác thực nguồn gửi.

**Tài liệu:** [GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md), [firmware/esp32_vehicle/README.md](autopark/firmware/esp32_vehicle/README.md).

**Tiếp theo:** cài PlatformIO (người dùng quyết định), biên dịch, chạy test C++ trên máy tính với `vectors.json`. Khi có bo: đo xung bằng máy hiện sóng trước khi nối ESC.

### 4.10. Nguồn và an toàn

**Trạng thái:** giai đoạn 6 mới ở phần "khi chưa có nguồn final". Chưa có phần cứng nguồn hay dừng nào.

**Đã có:** các tình huống mất liên lạc, rút cáp, treo chương trình, bo khởi động lại đã được viết trong đặc tả giao thức và firmware (mục 4.9). Đã chọn cách đấu ngõ vào E-stop an toàn khi hở mạch (tiếp điểm NC nối GND, điện trở kéo lên), chưa lắp, chưa thử. Phiên mô phỏng giai đoạn 0 dừng khi phản hồi cũ hơn 150 ms.

**Chưa có:** bảng tải điện áp/dòng, `power_budget.md`, sơ đồ nguồn, sơ đồ dừng. Chưa chọn UBEC hay XL4015, định mức cầu chì, phần tử mà LA38 cắt. Ngõ vào E-stop của firmware **không thay** đường cắt động lực phần cứng. Cờ STOP trên laptop không chứng minh xe thật dừng được.

**Tài liệu:** [GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md) mục 0, 5, 6, 12; kế hoạch mục 10 (giai đoạn 6) và mục 3 (đợt mua 6).

**Tiếp theo:** lập bảng tải và sơ đồ nguồn/dừng trước khi thử chấp hành. Giai đoạn 6 phải xong trước khi chạy tự động trên sàn.

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
| Sao lưu `autopark/runs/` (checkpoint tham chiếu `ai_woodscape_rtx4000_v1/best.pt` và mọi bản ghi đo LiDAR, camera, bàn thử) và bản giải nén dataset | Các thư mục này bị git-ignore nên không có trên GitHub. ZIP gốc không còn trong `D:\ap`. Không tài liệu nào ghi đã có bản sao lưu; HUAN_LUYEN.md mục 5 chỉ ghi "cần sao lưu riêng nếu muốn giữ" | HUAN_LUYEN.md mục 5, TRANG_THAI_TAI_DAY_DU.md |

### 5.2. Làm được với thiết bị đang có (cần người thao tác)

- **LiDAR:** 7 lần đặt hộp p01–p06, p08; lần đặt bên trái chốt dấu góc. Kiểm vật ở hai vùng góc gần. Rút cáp khi `live_view` đang chạy.
- **Hợp nhất:** đưa tay/hộp vào trước LiDAR (cách ≥ 40 cm) và rút cáp khi xe ảo đang chạy.
- **Camera:** tách camera ra nhiều cổng gốc; thử nguồn ngoài cho hub; đổi chỗ camera cổng 1 và 2; chạy một phiên có camera chậm; thử ánh sáng sa bàn và `CAP_PROP_GAIN`; đo độ trễ bằng LED nháy. Ghi thêm dây camera, model hub, nhãn LiDAR, ảnh bộ thực giao.
- **Hiệu chuẩn:** in bảng, đo cỡ ô, hiệu chuẩn bốn camera.
- **Ảnh sa bàn:** dựng giá ở độ cao và góc chúc dự kiến, chụp, gán nhãn, chấm AI.
- **Laptop RTX 3050 Ti (máy nộp đồ án):** làm theo [MAY_NOP_DO_AN.md](autopark/docs/MAY_NOP_DO_AN.md): chép checkpoint từ `D:\CHUYEN_SANG_LAPTOP\` (có mã SHA-256), chạy `cai_dat.cmd` và `cai_dat_train.cmd`, rồi `do_may_moi.cmd`. Lệnh này đo cấu hình, cổng USB, LiDAR, thời gian AI, bàn thử 480p và 720p, rồi so với tham chiếu máy bàn.

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
- Nối `VehicleIO` (nhánh mô phỏng) vào phiên giai đoạn 0 / `TrajectoryTracker`; ghi `commands.csv`, `telemetry.csv`.
- Công cụ ngoại tham camera (ví dụ `cv2.fisheye.solvePnP` với bảng đặt trên sàn) và bước ghép nội tham + ngoại tham để `costmap.py` dùng được camera của dự án. Công cụ dựng mặt nạ ROI cho camera dự án.
- Sửa nhược điểm của quy tắc không chờ khi pha camera trôi (0,2–2,7 % số bộ).
- `initial_skip` ≥ 22 vòng, hoặc chờ theo thời gian, trong demo hợp nhất.
- Cho `evaluate_external` chấm RoadAnomaly21; cho `evaluate.py` kiểm ảnh chấm không nằm trong train; thêm `labels import --exclude`.
- Lưu script đo độ lặp lại LiDAR vào repo; chép bản nhỏ của k01 vào `autopark/docs/evidence/lidar/`.
- Chọn phương án SLAM/định vị 2D cho LiDAR và kiểm đầu vào bắt buộc của nó (kế hoạch mục 5 "Khi đang chờ đồ" và mục 17.2 "đầu vào thư viện SLAM"). Chưa tài liệu nào ghi phương án đã chọn. Thử trước trên dữ liệu lưu sẵn: DROW v2 có `.odom2` (đã ghép thử 300 vòng ở GIAI_DOAN_1_LIDAR.md mục 5, mới là bằng chứng gián tiếp, chưa phải kiểm chứng SLAM) và các bản ghi C1 (LiDAR đứng yên). Chưa có odometry thật thì không gán odometry bằng 0 để báo đã có định vị. Việc này đang chặn điều kiện V1 đầu tiên (mục 16.4) và dòng "Định vị lại được: CHƯA" của gate 1.
- Soạn trước: phiếu kiểm kê và bảng đo MN300 (giai đoạn 4), bảng kịch bản nghiệm thu (16.3) và cách đo độc lập, khung bảng tải điện.

## 6. Bản đồ tài liệu

"Hiện hành" = dùng làm tình trạng hiện nay. "Hồ sơ" = ghi lại một đợt làm việc; số liệu đúng cho đợt đó, chỗ lỗi thời có ghi chú tại chỗ. Cột "Cập nhật" là ngày sửa nội dung gần nhất.

| # | Tài liệu | Vai trò | Tình trạng | Cập nhật |
|---:|---|---|---|---|
| 1 | [TONG_HOP_DU_AN.md](TONG_HOP_DU_AN.md) | Tổng hợp theo mảng, đọc đầu tiên | hiện hành (24/09) | 24/09 |
| 2 | [README.md](README.md) | Trang đầu repo, mục lục tài liệu, mức bằng chứng | hiện hành | 24/09 |
| 3 | [KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) | Kế hoạch 11 giai đoạn, 6 đợt mua, điều kiện chuyển bước, V1 | thân tệp là kế hoạch (19/09), không phải kết quả; mục 1.1 (nhận hàng) và bảng 17.4 hiện hành | 24/09 |
| 4 | [BAO_CAO_GIAI_DOAN_0.md](BAO_CAO_GIAI_DOAN_0.md) | Báo cáo giai đoạn 0 | hồ sơ 20/09; chỗ lỗi thời đánh dấu "Cập nhật 24/09/2026" | 24/09 |
| 5 | [HUAN_LUYEN.md](HUAN_LUYEN.md) | Biên bản AI: phần I (21/09), II (22/09), III (22–23/09) | hiện hành; sửa và cập nhật 24/09 tại chỗ | 24/09 |
| 6 | [autopark/README.md](autopark/README.md) | Cách cài, chạy, kiểm thử; cấu trúc mã; quy ước | hiện hành | 24/09 |
| 7 | [autopark/docs/GIAI_DOAN_0.md](autopark/docs/GIAI_DOAN_0.md) | Biên bản cổng giai đoạn 0 | hồ sơ 20/09 (169 test, năm phiên đầu); số sau sửa ở tệp 8; ghi chú 24/09 cuối tệp | 24/09 |
| 8 | [autopark/docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md](autopark/docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md) | Kiểm thử mở rộng: 220 test, 2.880 ca, coverage | hồ sơ 20/09, vẫn đúng cho giai đoạn 0 | 24/09 |
| 9 | [autopark/docs/GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md) | Giấy phép từng bộ dữ liệu, quyết định 22/09 | hiện hành | 24/09 |
| 10 | [autopark/docs/GIAI_DOAN_1_CHUAN_BI.md](autopark/docs/GIAI_DOAN_1_CHUAN_BI.md) | Calibration WoodScape, ROI, costmap, nguồn phát lại, giám sát dữ liệu cũ, ONNX | hồ sơ 22/09; cập nhật 24/09 ở đầu tệp, mục 1, 5, 7 | 24/09 |
| 11 | [autopark/docs/GIAI_DOAN_1_LIDAR.md](autopark/docs/GIAI_DOAN_1_LIDAR.md) | Nhánh LiDAR: driver, ghi phiên, bản đồ tĩnh | hiện hành; kiểm lại 24/09 ở mục 3b | 24/09 |
| 12 | [autopark/docs/GIAI_DOAN_1_CAMERA.md](autopark/docs/GIAI_DOAN_1_CAMERA.md) | Nhánh camera: mode, FPS, khung cũ, danh tính theo cổng | hồ sơ 23/09; **có đính chính ở mục 4.6**: chữ "sạch" ở mục 4.2–4.5 chỉ nói khung cũ | 24/09 |
| 13 | [autopark/docs/evidence/camera/report_20260923.md](autopark/docs/evidence/camera/report_20260923.md) | Báo cáo đo camera do công cụ tự sinh (12:23, 23/09) | bằng chứng lịch sử, trước khi có bộ dò khung bị cắt; đọc cùng tệp 12 mục 4.6 | 23/09 |
| 14 | [autopark/docs/usb_topology.md](autopark/docs/usb_topology.md) | Sơ đồ cổng USB, danh tính camera | hiện hành; cập nhật 24/09 | 24/09 |
| 15 | [autopark/docs/hardware_inventory.md](autopark/docs/hardware_inventory.md) | Kiểm kê phần cứng | hiện hành | 24/09 |
| 16 | [autopark/docs/gate_01.md](autopark/docs/gate_01.md) | Biên bản cổng giai đoạn 1 | hiện hành: CHƯA ĐẠT | 24/09 |
| 17 | [autopark/docs/GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md) | Bàn thử bốn camera + LiDAR + AI | hiện hành; mục 5–6 (loạt cũ) chỉ dùng được một phần; mục 10 thêm 24/09 | 24/09 |
| 18 | [autopark/docs/HIEU_CHUAN_CAMERA.md](autopark/docs/HIEU_CHUAN_CAMERA.md) | Hiệu chuẩn nội tham camera | hiện hành; có đính chính cuối mục 5 (giao diện đã mở camera thật một lần) | 24/09 |
| 19 | [autopark/calibration/README.md](autopark/calibration/README.md) | Quy ước tệp `cam_p<N>.json` | hiện hành | 24/09 |
| 20 | [autopark/docs/GAN_NHAN_SA_BAN.md](autopark/docs/GAN_NHAN_SA_BAN.md) | Gán nhãn ảnh sa bàn | hiện hành | 24/09 |
| 21 | [autopark/docs/GIAI_DOAN_3_CHUAN_BI.md](autopark/docs/GIAI_DOAN_3_CHUAN_BI.md) | Hợp nhất cảm biến, demo LiDAR thật với xe ảo | hồ sơ 22/09; cập nhật 24/09 ở mục 1, 2, 3b, 6 | 24/09 |
| 22 | [autopark/docs/GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md) | Giao thức laptop–ESP32-S3, `VehicleIO`, firmware | hiện hành | 24/09 |
| 23 | [autopark/firmware/esp32_vehicle/README.md](autopark/firmware/esp32_vehicle/README.md) | Firmware C++: cấu trúc, CHƯA CHỐT, an toàn, cách biên dịch và thử | hiện hành; C++ chưa biên dịch | 24/09 |
| 24 | [autopark/datasets/DANH_MUC_DATASET.md](autopark/datasets/DANH_MUC_DATASET.md) | Danh mục 44 bộ/nhánh dataset | khảo sát 20/09; cột giấy phép có đính chính 24/09 ở đầu tệp | 24/09 |
| 25 | [autopark/datasets/TAI_VA_KIEM_TRA.md](autopark/datasets/TAI_VA_KIEM_TRA.md) | Các bộ đã tải và kiểm | hồ sơ 20/09; cập nhật 24/09 | 24/09 |
| 26 | [autopark/datasets/TRANG_THAI_TAI_DAY_DU.md](autopark/datasets/TRANG_THAI_TAI_DAY_DU.md) | Trạng thái tải đầy đủ | tệp do script tự sinh (19/09 UTC), thêm ghi chú tay 21/09 và 24/09; chạy lại script sẽ xóa ghi chú | 24/09 |
| 27 | [autopark/datasets/woodscape_metadata/README.md](autopark/datasets/woodscape_metadata/README.md) | README của Valeo đi kèm metadata WoodScape | bản sao của bên thứ ba, không phải tài liệu dự án | 21/09 |

## 7. Cách đọc bằng chứng và quy ước

**Mức bằng chứng và cách ghi:**

- Ba mức mô phỏng / bàn thử máy bàn / xe thật không thay nhau (mục 1).
- "Giả định" = số chưa đo (ví dụ `configs/vehicle_default.json`, `configs/vehicle_io_sim.json`). "Đề xuất" = ngưỡng chưa kiểm trên thiết bị thật. "Chưa đo", "chưa xác nhận" = đúng như chữ.
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

**Thuật ngữ:**

- Nhãn AI: 0 FREE, 1 BLOCKED, 255 IGNORE. "Vật cản → FREE" là lỗi nguy hiểm (có thể đâm). "FREE → vật cản" là báo động giả (chỉ làm xe dừng). Ngưỡng 0,50 là argmax; 0,15 là ngưỡng thiên về an toàn.
- Camera: "khung cũ" = driver trả lại đúng khung trước; "khung bị cắt/xé" = khung MJPEG thiếu dữ liệu, phần thiếu bị tô vân xám. Camera "thiếu" = không có khung tốt trong 0,5 s; camera "chậm" = bị bỏ khỏi bộ vì chờ quá ≈ 62 ms.
- Tên phiên: p07, k01 = phiên đo LiDAR; m*, n*, q* = phiên đo camera ngày 23/09; s*, t*, u*, a*, f*, d01 = bàn thử ngày 23/09; w01–w05 = bàn thử ngày 24/09.

**Tệp không có trên GitHub** (git-ignore): `autopark/runs/`, `autopark/datasets/prepared/`, `autopark/datasets/download_metadata/` (có biên bản CRC mà TRANG_THAI_TAI_DAY_DU.md dẫn link), dataset, checkpoint, `autopark/review_artifacts/`, `autopark/docs/evidence/coverage_html/`, và mọi tệp `*.csv` trừ `docs/evidence/*.csv` và `docs/camera_modes.csv`. Link tới các thư mục này chỉ mở được trên máy có dữ liệu. Bản sao nhỏ của vài bằng chứng nằm trong `autopark/docs/evidence/`, có trên GitHub.
