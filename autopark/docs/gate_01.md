# Biên bản cổng chuyển bước giai đoạn 1 — kế hoạch v3.1, mục 5

Cập nhật: 23/09/2026. **Trạng thái: CHƯA ĐẠT** — nhánh LiDAR đã đọc được scan và ghi/phát lại được; sai số khoảng cách và định vị chưa có; nhánh camera đã có bốn camera và hub, đo xong mode/FPS/bốn luồng trên máy bàn ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md)), chưa gá, chưa hiệu chuẩn, chưa chạy AI trên ảnh thật.

Theo yêu cầu của kế hoạch, ba kết quả LiDAR được tách riêng:

| Kết quả | Trạng thái | Bằng chứng |
|---|---|---|
| Đọc scan được | **ĐẠT** trên máy bàn: COM4, chế độ Standard, 10,09 Hz, 508 tia/vòng, bản ghi 17,8 s không mất vòng, 0 byte lệch | [p07_nen_phong.analysis.json](evidence/lidar/p07_nen_phong.analysis.json), [hình](evidence/lidar/p07_nen_phong.png) |
| Tạo map được | **MỘT PHẦN**: bản đồ lưới tĩnh từ 181 vòng tại một vị trí cố định, lưu theo hợp đồng `Costmap` (không phải SLAM, không có tư thế ước lượng) | [map_p07.png](evidence/lidar/map_p07.png) |
| Định vị lại được | **CHƯA** — chưa có odometry, chưa có xe | |

## Điều kiện chuyển bước

- [ ] Laptop nhận LiDAR và camera ổn ở mode đã ghi rõ — LiDAR: đạt trên máy bàn (mode Standard, 460800 bps, COM4); laptop của xe chưa thử; camera: đạt trên máy bàn cho một camera MJPG 720p (m01/n01: 23,9 fps trong ánh sáng phòng, 0 khung cũ trong 30 s, nhịp khung không đều, không đổi sau khi lột phim bảo vệ ống kính); bốn camera 720p đồng thời với hub bus-powered: ba chiếc không rớt, camera cổng 4 rớt thất thường (0 khung cũ/60 s ở n03, 4 ở m05; 18,6 / 22,3 / 3,9 fps ở ba phiên 10 s m12a–c); sau khi rút/cắm lại các camera: 0 khung cũ ở cả 720p × 4 và 1080p × 4 trong 7 phiên, nguyên nhân chưa rõ (mục 4.5); laptop của xe chưa thử.
- [ ] Có dữ liệu và phép thử lưu/nạp bản đồ; phần định vị chưa đạt được báo riêng — có bản đồ tĩnh và file `costmap.json`; chưa có phép thử nạp lại/định vị.
- [ ] Camera đủ nét trong vùng làm việc; hiệu chuẩn được và chạy AI trên ảnh thật — chưa: camera chưa đặt ở độ cao/góc chúc dự kiến, chưa hiệu chuẩn (chưa có bảng, chưa có mã cho ống kính thật), chưa chạy AI trên ảnh thật.
- [ ] Có số đo, không chỉ nhận xét video "mượt" — có số đo tần số, tia/vòng, khoảng trống, tỉ lệ không phản hồi; **sai số khoảng cách so với thước chưa đo** (cần phiên đặt hộp, mục 3 của [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)). Camera: có FPS, khung cũ, khoảng cách khung, CPU ([GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4); **chưa đo** độ trễ đầu-cuối, thời gian suy luận, tải GPU, nhiệt.
- [ ] Chỉ quyết định mua thêm ba camera sau khi mẫu vượt kiểm tra đơn camera — đã mua đủ bốn trước khi thử; bài thử đơn camera làm ngày 23/09: đạt về mode và FPS, chưa đạt về vùng làm việc/hiệu chuẩn.

## Đầu ra phải có

| Tệp | Trạng thái |
|---|---|
| `hardware_inventory.md` | có, thiếu ảnh bộ thực giao và model trên nhãn ([hardware_inventory.md](hardware_inventory.md)) |
| `camera_modes.csv`, `camera_01_calibration.yaml` | `camera_modes.csv`: có ([docs/camera_modes.csv](camera_modes.csv)); calibration: chưa |
| Bản quét / bản đồ thử | `runs/lidar_bench/20260922/` (git-ignored) và bản sao nhỏ ở `docs/evidence/lidar/` |
| Log nhận ảnh, video mẫu | có: `runs/camera_bench/20260923/` (17 file `*.measure.json` của 13 phiên m01–m13 còn phim bảo vệ ống kính, 6 file n01–n06 sau khi lột phim, 10 file q* sau khi rút/cắm lại camera; 3 video, 9 ảnh tĩnh; git-ignored), bản nhỏ ở [evidence/camera/](evidence/camera/) |
| `gate_01.md` | tệp này |
