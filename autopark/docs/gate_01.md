# Biên bản cổng chuyển bước giai đoạn 1 — kế hoạch v3.1, mục 5

Cập nhật: 22/09/2026. **Trạng thái: CHƯA ĐẠT** — nhánh LiDAR đã đọc được scan và ghi/phát lại được; sai số khoảng cách và định vị chưa có; nhánh camera chưa có thiết bị.

Theo yêu cầu của kế hoạch, ba kết quả LiDAR được tách riêng:

| Kết quả | Trạng thái | Bằng chứng |
|---|---|---|
| Đọc scan được | **ĐẠT** trên máy bàn: COM4, chế độ Standard, 10,09 Hz, 508 tia/vòng, bản ghi 17,8 s không mất vòng, 0 byte lệch | [p07_nen_phong.analysis.json](evidence/lidar/p07_nen_phong.analysis.json), [hình](evidence/lidar/p07_nen_phong.png) |
| Tạo map được | **MỘT PHẦN**: bản đồ lưới tĩnh từ 181 vòng tại một vị trí cố định, lưu theo hợp đồng `Costmap` (không phải SLAM, không có tư thế ước lượng) | [map_p07.png](evidence/lidar/map_p07.png) |
| Định vị lại được | **CHƯA** — chưa có odometry, chưa có xe | |

## Điều kiện chuyển bước

- [ ] Laptop nhận LiDAR và camera ổn ở mode đã ghi rõ — LiDAR: đạt trên máy bàn (mode Standard, 460800 bps, COM4); laptop của xe chưa thử; camera: chưa có.
- [ ] Có dữ liệu và phép thử lưu/nạp bản đồ; phần định vị chưa đạt được báo riêng — có bản đồ tĩnh và file `costmap.json`; chưa có phép thử nạp lại/định vị.
- [ ] Camera đủ nét trong vùng làm việc; hiệu chuẩn được và chạy AI trên ảnh thật — chưa có camera.
- [ ] Có số đo, không chỉ nhận xét video "mượt" — có số đo tần số, tia/vòng, khoảng trống, tỉ lệ không phản hồi; **sai số khoảng cách so với thước chưa đo** (cần phiên đặt hộp, mục 3 của [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)).
- [ ] Chỉ quyết định mua thêm ba camera sau khi mẫu vượt kiểm tra đơn camera — chưa có mẫu.

## Đầu ra phải có

| Tệp | Trạng thái |
|---|---|
| `hardware_inventory.md` | có, thiếu ảnh bộ thực giao và model trên nhãn ([hardware_inventory.md](hardware_inventory.md)) |
| `camera_modes.csv`, `camera_01_calibration.yaml` | chưa có camera |
| Bản quét / bản đồ thử | `runs/lidar_bench/20260922/` (git-ignored) và bản sao nhỏ ở `docs/evidence/lidar/` |
| Log nhận ảnh, video mẫu | chưa có camera |
| `gate_01.md` | tệp này |
