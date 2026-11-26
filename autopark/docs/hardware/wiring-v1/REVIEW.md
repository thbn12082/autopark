# Kiểm tra bộ bản vẽ điện 2D AutoPark

Ngày cập nhật: **26/11/2026**. Revision: **`pi4_sensors_unwired_v5`**.

Đây là kiểm tra tài liệu và ảnh thiết kế, không phải nghiệm thu điện hoặc chạy xe thật.

## Thay đổi so với `pi4_dual_mt6701_target_v4` (14/11/2026)

- **MT6701 vẽ lại theo module thực nhận**: bo đen, một hàng 5 chân `VDD`, `GND`, `Analog/PWM`, `SCL`, `SDA` theo chữ in mặt sau. Bản cũ vẽ module 6 chân có `MODE`, `Z/CSN`, A/B và nối #1 vào GPIO6/7 (MODE, Z lên 3V3), #2 vào GPIO8/9 theo A/B (MODE về GND). Module thật không có các chân đó nên cách nối cũ sai và đã bỏ.
- **Thêm BNO085** (bo GY-BNO08X, 10 chân `VCC`, `GND`, `SCL`, `SDA`, `ADO`, `CS`, `INT`, `RST`, `PS1`, `PS0`).
- **Hai MT6701 và BNO085 chưa đấu nối vào xe**: tờ 2 đặt chúng trong khung "Chưa đấu nối", không có dây nào tới ESP32. ESP32 không còn chân dự kiến cho cảm biến; netlist bỏ các net 3V3, SDA, SCL, ENC_A, ENC_B.
- ESC (GPIO4), servo (GPIO5) và BEC 6 V cấp servo vẽ nét liền: đã chạy trên bàn thử 24–25/11/2026.
- Pi 4 Model B RAM 8 GB (bản cũ ghi 4 GB).

## Các phép kiểm của bản dựng

| Hạng mục | Phép kiểm |
|---|---|
| Danh mục | 18 mục hình; hai MT6701 cùng hình module 5 chân, một BNO085, một hình camera dùng bốn lần |
| Netlist | Cổng tồn tại, không thuộc hai net khác nhau; không cổng nào của hai MT6701 và BNO085 nằm trong net hay liên kết nào |
| Giao tiếp | 7 cáp USB, một cáp C1 gốc và Wi-Fi |
| Nguồn | BEC dương chỉ tới servo; hai DC–DC không nối song song đầu ra; USB Pi 4 có giới hạn tổng 1,2 A |
| Ảnh | Dựng lại bốn tờ từ mã SVG; kiểm XML, kích thước PNG |

## Những phần vẫn phải xác minh

Cách đấu hai MT6701 và BNO085 (bus, GPIO, cách đo tốc độ), vị trí gá và nam châm, quan hệ góc cảm biến–góc bánh; nguồn Pi/cáp/tải USB, nguồn hub/chống cấp ngược; dòng servo khi chạy trên sàn; tải motor, nhiễu và sụt áp; hiệu chuẩn LiDAR/camera và băng thông bốn luồng.

Nguồn: [MagnTek MT6701 Rev.1.8](https://www.magntek.com.cn/upload/pdf/202407/MT6701_Rev.1.8.pdf), [Raspberry Pi — phần cứng và nguồn](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html). Chi tiết lắp ở [hướng dẫn điện](../../LAP_RAP_DIEN_2D.md).
