# Bản vẽ 2D kết nối AutoPark

Các bản vẽ thể hiện kiến trúc mục tiêu **Laptop ↔ Wi-Fi LAN ↔ Raspberry Pi trên xe ↔ USB ngắn ↔ ESP32**. Laptop chạy AI trên bốn camera, fusion, chọn ô và lập quỹ đạo; Pi thu cảm biến, định vị, bám quỹ đạo và dừng vật cản cục bộ; ESP32 nhận lệnh chấp hành và dừng khi lệnh hết hạn; ESC (GPIO4) và servo (GPIO5) đã chạy trên bàn thử. C1 và hub bốn camera nối USB về Pi. Tờ 02 bổ sung dây đề xuất: hai MT6701 trên hai bus I²C (GPIO6/7 và GPIO8/9), BNO085 qua SPI (GPIO10–16), nguồn 3V3 và GND chung. Các nhãn đầu dây trùng nhau là cùng kết nối. **Chưa đấu thử thực tế, chưa có driver cảm biến.**

Pin 2S chia nhánh cho ESC và hai bộ nguồn ổn áp riêng cho Pi/hub. Pi 4 Model B RAM 8 GB, thẻ microSD 64 GB; bộ nguồn và hub có DC-in phù hợp còn chờ chọn/xác minh, kể cả kiểm chống cấp ngược USB. BEC 6 V cấp servo (đã chạy trên bàn thử 24/11/2026); không cấp Pi, hub hoặc ESP32. Sạc B3 giữ chế độ pin tách khỏi toàn bộ xe.

Đây là **thiết kế mục tiêu**; mới kiểm trên bàn phần ESC/servo. Phần mềm đã tự tìm ô đỗ trên bản đồ LiDAR; Pi bám quỹ đạo chưa triển khai. Dừng khi hành lang có vật cản không an toàn, dữ liệu cũ hoặc mất liên kết; không tự chạy lại. Laptop lập lại từ pose mới đo khi xe đã dừng, rồi cần xác nhận lượt chạy mới. 4G chỉ là tùy chọn về sau.

| Tờ | PNG để xem | SVG để phóng to |
|---|---|---|
| Linh kiện và điểm nối | [00-components.png](00-components.png) | [00-components.svg](00-components.svg) |
| Nguồn và chấp hành | [01-system.png](01-system.png) | [01-system.svg](01-system.svg) |
| Tín hiệu, phản hồi và USB | [02-signal-feedback.png](02-signal-feedback.png) | [02-signal-feedback.svg](02-signal-feedback.svg) |
| Sạc pin tách khỏi xe | [03-charging.png](03-charging.png) | [03-charging.svg](03-charging.svg) |

[Hướng dẫn lắp và các điều kiện cần xác minh](../../LAP_RAP_DIEN_2D.md) · [Ghi chú kiểm tra bản dựng](REVIEW.md) · [Nguồn hình linh kiện](component_notes.md)

## Dựng lại

Từ thư mục dự án Python `autopark/`:

```powershell
.\.venv\Scripts\python.exe docs/hardware/wiring-v1/render_png.py
```

Script dựng lại SVG, xuất PNG ở tỷ lệ 2×, kiểm XML/QtSvg, kích thước và ảnh không rỗng, rồi ghi `export_manifest.json` với hash. `--no-rebuild` bỏ qua dựng lại ba sơ đồ mạch; bảng linh kiện vẫn được dựng lại. Dùng `--scale 1.5` để đổi độ phân giải. Không mở thiết bị hoặc gọi mạng.

`components.py` chứa hình linh kiện và tọa độ pad; `build_wiring.py` ghép các dây và ghi `wiring_spec.json`. Netlist và hình là kiểm tra nhất quán của thiết kế, không phải mô phỏng điện hay bằng chứng phần cứng tương thích. Ảnh gốc người dùng không được nhúng hoặc xuất bản trong bộ tệp này.
