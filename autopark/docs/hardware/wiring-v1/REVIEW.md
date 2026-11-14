# Kiểm tra bộ bản vẽ điện 2D AutoPark

Ngày cập nhật: **14/11/2026**. Revision: **`pi4_dual_mt6701_target_v4`**.

Đây là kiểm tra tài liệu và ảnh thiết kế, không phải nghiệm thu điện hoặc chạy xe thật. Các kết quả cũ của revision trước không tự áp dụng cho hai module MT6701 mới.

## Cấu hình được thể hiện

- Pi 4 Model B RAM 4 GB, microSD 64 GB; AI/chọn ô/lập đường ở laptop; Pi thu cảm biến, định vị và bám đường; ESP32 điều khiển ga/lái.
- Hai MT6701 độc lập: #1 ở cơ cấu lái, đọc góc tuyệt đối qua I²C tại GPIO6/7; #2 ở bánh/trục, xuất A/B tại GPIO8/9. Hai nam châm và hai gá riêng.
- Theo MagnTek Rev.1.8, hình 17–18: #1 MODE và Z/CSN ở 3V3 để dùng I²C. Theo hình 6–7: #2 MODE về GND, chọn ABZ; Z là đầu ra không dùng, để trống. Các nhánh này được thêm vào netlist và hình, phải đối chiếu jumper/pinout breakout thực nhận.
- GPIO không thay so với bản trước; tên nhánh lái đổi sang STEER. Không suy ra 14 bit góc tuyệt đối thành 14 bit số xung/vòng A/B; PPR cần chọn và đo.
- Giữ Wi-Fi laptop–Pi, USB ngắn trên xe, BEC chỉ cấp servo tương thích; Pi/hub dùng nguồn ổn áp riêng. Không thêm ToF/IMU hoặc đường ngắt động lực độc lập như thiết bị đã lắp.

## Các phép kiểm của bản dựng

| Hạng mục | Phép kiểm |
|---|---|
| Danh mục | 17 mục hình; trong đó có hai module MT6701 theo hai chế độ, một hình camera dùng bốn lần |
| Netlist | 17 net nguồn/tín hiệu; cổng tồn tại, không thuộc hai net khác nhau; MODE/Z của #1 chỉ ở 3V3, MODE của #2 ở GND, Z của #2 không nối net |
| Giao tiếp | 7 cáp USB, một cáp C1 gốc và Wi-Fi; cả hai MT6701 nối ESP32, không nối trực tiếp Pi |
| Nguồn | BEC dương chỉ tới servo có điều kiện; hai DC–DC không nối song song đầu ra; USB Pi 4 có giới hạn tổng 1,2 A |
| Ảnh | Dựng lại bốn sơ đồ phần cứng và hai luồng xử lý từ mã SVG; kiểm XML, kích thước PNG và bố cục chữ/đường |
| Tái tạo | So hash ảnh, spec và manifest qua hai lần dựng cùng Qt/font; các khóa cache ảnh phải khớp ảnh mới |
| Liên kết | Kiểm đường dẫn tương đối trong README và tài liệu hiện hành; đối chiếu mã nguồn ảnh với manifest |

Mã ứng dụng và firmware điều khiển không đổi. PWM vẫn chưa bật; driver phản hồi thật, hiệu chuẩn và triển khai Pi còn phải làm. Kết quả dựng hình không xác nhận độ trễ camera, quãng phanh hoặc độ chính xác cảm biến thật.

## Những phần vẫn phải xác minh

Module MT6701 thực nhận, mức logic 3V3, jumper MODE/Z, PPR, hai vị trí gá/nam châm và quan hệ góc cảm biến–góc bánh; nguồn Pi/cáp/tải USB, nguồn hub/chống cấp ngược; tương thích servo 6 V và mức tín hiệu ESC; tải motor, nhiễu và sụt áp; hiệu chuẩn LiDAR/camera và băng thông bốn luồng.

Nguồn: [MagnTek MT6701 Rev.1.8](https://www.magntek.com.cn/upload/pdf/202407/MT6701_Rev.1.8.pdf), [Raspberry Pi — phần cứng và nguồn](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html). Chi tiết lắp ở [hướng dẫn điện](../../LAP_RAP_DIEN_2D.md). Hình là mốc chức năng; không thay pinout của module mua thực tế.
