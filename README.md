# Xe mô hình tự đỗ — đồ án

MN300 Tank300 1/12 + laptop + RPLIDAR C1 + bốn camera USB + ESP32-S3. Người dùng đặt vị trí/hướng đỗ; hệ thống lập đường, tự đỗ có phản hồi và dừng — đánh giá lại khi gặp vật cản. Làm phần mềm và nhận thức trước, tích hợp xe thật sau.

> **Ghi công bắt buộc theo giấy phép dữ liệu:** nghiên cứu nhận thức trong dự án này được thực hiện với **Valeo WoodScape Dataset** (<https://woodscape.valeo.com>, [repo](https://github.com/valeoai/WoodScape)). Giới hạn sử dụng: [autopark/docs/GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md).

| Tài liệu | Nội dung |
|---|---|
| [KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) | Kế hoạch 11 giai đoạn, 6 đợt mua, điều kiện chuyển bước; bảng theo dõi tiến độ ở mục 17.4 |
| [BAO_CAO_GIAI_DOAN_0.md](BAO_CAO_GIAI_DOAN_0.md) | Giai đoạn 0 — mô phỏng: 220 test, 2.880 ca theo seed, replay |
| [HUAN_LUYEN.md](HUAN_LUYEN.md) | Nhận thức FREE/BLOCKED: baseline WoodScape (phần I, 21/09/2026), đánh giá ngoài miền và ngưỡng thiên về an toàn (phần II, 22/09), thêm AVM-SS và ACDC, kiểm ba seed (phần III, 23/09) |
| [autopark/docs/GIAY_PHEP_DU_LIEU.md](autopark/docs/GIAY_PHEP_DU_LIEU.md) | Giấy phép từng bộ dữ liệu. **WoodScape cấm dùng mô hình huấn luyện trên nó để vận hành hoặc hỗ trợ vận hành phương tiện**; quyết định ngày 22/09/2026 của người làm khóa luận và giới hạn của quyết định đó |
| [autopark/docs/GIAI_DOAN_1_CHUAN_BI.md](autopark/docs/GIAI_DOAN_1_CHUAN_BI.md) | Giai đoạn 1 khi chưa đủ thiết bị: calibration, ROI, costmap, nguồn phát lại, giám sát dữ liệu cũ (22/09/2026) |
| [autopark/docs/GIAI_DOAN_1_LIDAR.md](autopark/docs/GIAI_DOAN_1_LIDAR.md) | Nhánh LiDAR thật: driver RPLIDAR C1, ghi phiên, bench, bản đồ tĩnh (22/09/2026) |
| [autopark/docs/GIAI_DOAN_1_CAMERA.md](autopark/docs/GIAI_DOAN_1_CAMERA.md) | Nhánh camera thật: bốn camera USB qua hub UGREEN, mode, FPS, khung cũ, danh tính theo cổng hub (23/09/2026; đính chính ở mục 4.6) |
| [autopark/docs/gate_01.md](autopark/docs/gate_01.md) | Biên bản cổng chuyển bước giai đoạn 1 — CHƯA ĐẠT (cập nhật 23/09/2026, ghi chú thêm 24/09) |
| [autopark/docs/GIAI_DOAN_2_BAN_THU.md](autopark/docs/GIAI_DOAN_2_BAN_THU.md) | Bàn thử giai đoạn 2: bốn camera + LiDAR + AI chạy chung trên máy bàn, giao diện trực tiếp; khung MJPEG bị cắt khi bốn camera chạy chung qua hub, nên mặc định 640×480 (23/09/2026) |
| [autopark/docs/HIEU_CHUAN_CAMERA.md](autopark/docs/HIEU_CHUAN_CAMERA.md) | Hiệu chuẩn nội tham từng camera 130° bằng bảng ô vuông: bảng in sẵn, giao diện chụp, cách nhận/loại (mã có từ 24/09/2026, mới kiểm trên ảnh tổng hợp) |
| [autopark/docs/GAN_NHAN_SA_BAN.md](autopark/docs/GAN_NHAN_SA_BAN.md) | Gán nhãn ảnh sa bàn chụp từ bàn thử: nháp từ AI, sửa tay, duyệt, xuất cache huấn luyện (24/09/2026) |
| [autopark/docs/GIAO_THUC_XE.md](autopark/docs/GIAO_THUC_XE.md) | Giao thức laptop–ESP32-S3, VehicleIO mô phỏng/phần cứng, logic firmware (bản Python đã kiểm; C++ chưa biên dịch) (24/09/2026) |
| [autopark/docs/GIAI_DOAN_3_CHUAN_BI.md](autopark/docs/GIAI_DOAN_3_CHUAN_BI.md) | Giai đoạn 3 khi chưa có IMU/ToF/ESP32: lớp bản đồ, hợp nhất, cầu nối vật cản vào phiên mô phỏng, demo với LiDAR thật đứng yên (22/09/2026) |
| [autopark/README.md](autopark/README.md) | Mã nguồn: cách cài, chạy mô phỏng, kiểm thử, huấn luyện, chạy LiDAR/camera/bàn thử |

**Mức bằng chứng hiện tại (24/09/2026):** giai đoạn 0 đạt trong mô phỏng; AI được chấm trên ảnh lưu sẵn của bộ dữ liệu công khai, chưa chấm trên ảnh sa bàn; LiDAR C1 và bốn camera USB mới đo trên máy bàn (cảm biến nằm trên bàn, chưa gá, camera chưa hiệu chuẩn, sai số khoảng cách LiDAR chưa đo, chưa thử trên laptop của xe). Chưa có kết quả trên xe thật.

Không nằm trong repo (xem `autopark/.gitignore`): dataset, cache huấn luyện, checkpoint và thư mục `autopark/runs/` — các link tới `runs/` trong tài liệu chỉ mở được trên máy có dữ liệu.
