# Bản vẽ 2D kết nối AutoPark

Các bản vẽ thể hiện phương án ESP32-S3 + ESC rời, có các nhánh chưa xác minh được đánh dấu. Đây là tài liệu thiết kế, chưa nghiệm thu điện hoặc chạy xe thật.

| Tờ | PNG để xem | SVG để phóng to |
|---|---|---|
| Linh kiện và điểm nối | [00-components.png](00-components.png) | [00-components.svg](00-components.svg) |
| Nguồn và chấp hành | [01-system.png](01-system.png) | [01-system.svg](01-system.svg) |
| Tín hiệu, phản hồi và USB | [02-signal-feedback.png](02-signal-feedback.png) | [02-signal-feedback.svg](02-signal-feedback.svg) |
| Sạc pin tách khỏi xe | [03-charging.png](03-charging.png) | [03-charging.svg](03-charging.svg) |

[Hướng dẫn lắp và các điều kiện cần xác minh](../../LAP_RAP_DIEN_2D.md) · [Review độc lập](REVIEW.md) · [Nguồn hình linh kiện](component_notes.md)

## Dựng lại

Từ thư mục dự án Python `autopark/`:

```powershell
.\.venv\Scripts\python.exe docs/hardware/wiring-v1/render_png.py
```

Script dựng lại SVG, xuất PNG ở tỷ lệ 2×, kiểm XML/QtSvg, kích thước và ảnh không rỗng, rồi ghi `export_manifest.json` với hash. Dùng `--no-rebuild` nếu chỉ muốn xuất các SVG đang có; dùng `--scale 1.5` để đổi độ phân giải. Không mở thiết bị hoặc gọi mạng.

`components.py` chứa hình linh kiện và tọa độ pad; `build_wiring.py` ghép các dây và ghi `wiring_spec.json`. Netlist và hình là kiểm tra nhất quán của thiết kế, không phải mô phỏng điện hay bằng chứng phần cứng tương thích. Ảnh gốc người dùng không được nhúng hoặc xuất bản trong bộ tệp này.
