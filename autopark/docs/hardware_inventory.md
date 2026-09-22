# Kiểm kê phần cứng — giai đoạn 1

Cập nhật: 22/09/2026. Chỉ ghi những gì đã cầm trên tay hoặc máy đọc được; mục "chưa ghi" là chưa kiểm, không phải giả định.

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

## Camera USB mẫu

Chưa có thiết bị nào cắm vào máy (Device Manager không thấy lớp Camera/Image ngày 22/09/2026). `camera_modes.csv`, `camera_01_calibration.yaml`: chưa có.

## ESP32-S3, IMU BNO085, ToF VL53L1X, encoder, xe MN300

Chưa nhận / chưa kiểm kê.
