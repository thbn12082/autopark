# Kiểm kê phần cứng — giai đoạn 1

Cập nhật: 23/09/2026 (camera và hub), 22/09/2026 (LiDAR). Chỉ ghi những gì đã cầm trên tay hoặc máy đọc được; mục "chưa ghi" là chưa kiểm, không phải giả định.

## RPLIDAR C1 (đợt mua 1)

| Mục | Giá trị | Nguồn |
|---|---|---|
| Thiết bị tự báo | model 0x41 (C1), firmware 1.2, phần cứng 18 | lệnh GET_INFO qua `python -m autopark.lidar.rplidar_c1 info --port COM4` |
| Serial | `f57ffc8bc6e598d1b59598f976dd5762` | GET_INFO |
| Sức khỏe | OK (0), mã lỗi 0 | GET_HEALTH |
| Chế độ quét thiết bị công bố | 0 "Standard": 200 µs/mẫu, xa nhất 16 m, kiểu trả lời 0x81 — **đang dùng**; 1 "DenseBoost": 200 µs/mẫu, 40 m, 0x85 — thiết bị gọi là typical, **chưa dùng** | GET_LIDAR_CONF |
| Adapter USB | CP2102N USB to UART Bridge, VID 10C4 / PID EA60 | Device Manager |
| Driver Windows | Silicon Labs CP210x Universal Windows Driver 11.6.0.420 (Silicon Laboratories, ngày driver 14/08/2026); cổng **COM4** | Device Manager; người dùng cài ngày 22/09/2026 |
| UART | 460800 bps, 8N1, TTL 3,3 V | datasheet C1M1 rev 1.1; giao tiếp thực tế ở 460800 |
| Nguồn | 5 V qua USB máy tính; datasheet: khởi động 800 mA, làm việc 230 (max 260) mA ở 10 Hz | datasheet C1M1 rev 1.1 |
| Đầu nối | XH2.54-5P (VCC, TX, RX, GND, MOTOCTL) từ LiDAR tới adapter; adapter tới máy bằng cáp USB | datasheet, sổ tay C1 |
| Model in trên nhãn / hộp | chưa ghi (datasheet mô tả model C1M1) | |
| Ảnh bộ thực giao | chưa chụp | |
| Cổng USB của máy đang dùng | chưa ghi (nên cắm thẳng cổng USB 3, không qua hub không nguồn) | |
| Laptop chạy xe (RTX 3050 Ti) | chưa thử; mọi số đo dưới đây là trên máy bàn i9-14900 | |

Số đo trên bàn ngày 22/09/2026, chế độ Standard, chưa làm nóng, không đặt vật ([bản ghi](evidence/lidar/p07_nen_phong.json), [phân tích](evidence/lidar/p07_nen_phong.analysis.json)): 10,09 Hz; trung vị 508 tia/vòng (396–536); ≈5,1 kHz mẫu; 0 byte lệch trong 91.507 node; 34,6 % tia không phản hồi ở vị trí đặt; phản hồi xa nhất 14,6 m (vượt 12 m datasheet, datasheet ghi "chỉ để tham khảo"); mô-tơ mất ≈2,2 s từ lệnh SCAN tới node đầu. Sai số khoảng cách so với thước: **chưa đo** (cần phiên đặt hộp, xem [GIAI_DOAN_1_LIDAR.md](GIAI_DOAN_1_LIDAR.md)).

## Bốn camera USB 130° (theo nhà bán, chưa đo) và hub UGREEN (nhận 23/09/2026)

| Mục | Giá trị | Nguồn |
|---|---|---|
| Camera | 4 × "HD Camera", VID 1BCF (Sunplus Innovation) PID 0B09, UVC composite, **không có serial** → danh tính = cổng hub | Device Manager, DirectShow |
| Mode công bố | MJPG 640×480 / 1280×720 / 1920×1080 đều 30 fps; YUY2 640×480 30, 1280×720 10, 1920×1080 5 fps ([camera_modes.csv](camera_modes.csv)) | `python -m autopark.video.camera_bench modes` |
| FPS thật đo được | ≈ 24 fps với phơi sáng tự động trong phòng (720p và 1080p một camera: m01, m03, m08, m13; 640×480 chỉ đo trong phiên bốn camera m04), nhịp khung không đều (trung bình 41,9 ms, trung vị 47 ms); 29,3 fps khi ép phơi sáng −5…−8 (ảnh tối, m02/m11) | [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.1 |
| Bốn luồng đồng thời | 640×480 (m04, 30 s): 4 × 23,9 fps, 0 khung cũ. 720p (m05, 60 s): 4 × 23,8 fps, camera cổng 4 rớt 4 khung; ba phiên 10 s (m12a–c) camera cổng 4 còn 18,6 / 22,3 / 3,9 fps, ba chiếc kia không rớt. 1080p (m06, m09, m10): camera cổng 4 còn 22,5 / 13,1 / 18,7 fps, cổng 3 còn 22,3–22,7; ba camera 1080p (m07) cổng 3 còn 20,0 fps | cùng tài liệu, mục 4.2 |
| Khung MJPEG bị cắt khi chạy chung | 23/09 chiều: ở 720p/1080p, khi ba hoặc bốn camera chạy chung qua hub, khung của vài camera bị cắt cụt (đáy do bộ giải mã tô). Chạy một mình thì không. Ở 640×480 phần lớn thời gian cả bốn nguyên vẹn (u01: 4 × 23,85 khung tốt/s, 120 s, cùng LiDAR + AI), nhưng camera cổng 1 có những đợt 26–36 % khung hỏng, chưa rõ nguyên nhân. Số "bốn luồng đồng thời" ở dòng trên chưa kiểm khung bị cắt. | [GIAI_DOAN_2_BAN_THU.md](GIAI_DOAN_2_BAN_THU.md) mục 2, [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.6 |
| Hub | UGREEN 4 cổng, chip Genesys Logic: 05E3:0626 "USB3.1 Hub" ở cổng gốc 24 và 05E3:0610 "USB2.1 Hub" ở cổng gốc 5; cả bốn camera ở nhánh USB 2.0 cổng 1–4 ([usb_topology.md](usb_topology.md)) | `camera_bench list` → `usb_topology.json` khóa `hubs` |
| Nguồn hub | hub có cổng nguồn ngoài (theo người dùng); **bus-powered trong mọi phiên ngày 23/09**, chưa thử adapter; dòng camera **chưa đo** | |
| Rút/cắm lại camera | hai lần (≈ 11:45 các camera; ≈ 12:00 camera cổng 3 sau khi bị treo không mở được): index và InstanceId giữ nguyên; sau đó 0 khung cũ trong 7 phiên, nguyên nhân chưa rõ | `usb_topology_replug1/2.json`, [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.5 |
| Khởi động lại máy | 12:35 ngày 23/09: InstanceId theo cổng giữ nguyên, index OpenCV đổi (cổng 2 ↔ cổng 4) → chọn camera theo cổng, không theo index | `usb_topology_20260923_after_reboot.json` |
| Góc nhìn thực, nhãn/hộp, độ nét trong vùng làm việc | **chưa đo** (camera mới nằm trên bàn) | |
| Lớp phim bảo vệ ống kính | các phiên m01–m13 đo khi còn phim; lột lúc ≈ 11:15 ngày 23/09; phiên n01–n06 sau khi lột: nhịp khung/FPS không đổi, ảnh sáng hơn ≈ 5 lần ở cùng phơi sáng thủ công | [GIAI_DOAN_1_CAMERA.md](GIAI_DOAN_1_CAMERA.md) mục 4.4 |
| `camera_01_calibration.yaml` | chưa có (chưa in bảng hiệu chuẩn, chưa chụp). Mã đã có từ 24/09: tệp ra sẽ là `calibration/cam_p<cổng>.json`, mới kiểm trên ảnh tổng hợp | [HIEU_CHUAN_CAMERA.md](HIEU_CHUAN_CAMERA.md) |
| Dây camera (chiều dài, loại) | **chưa ghi** — kế hoạch yêu cầu thử dây ngắn trước rồi mới cáp kéo dài | |
| Laptop của xe | chưa thử | |

## ESP32-S3, IMU BNO085, ToF VL53L1X, encoder, xe MN300

Chưa nhận / chưa kiểm kê.
