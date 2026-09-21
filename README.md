# Xe mô hình tự đỗ — đồ án

MN300 Tank300 1/12 + laptop + RPLIDAR C1 + bốn camera USB + ESP32-S3. Người dùng đặt vị trí/hướng đỗ; hệ thống lập đường, tự đỗ có phản hồi và dừng — đánh giá lại khi gặp vật cản. Làm phần mềm và nhận thức trước, tích hợp xe thật sau.

| Tài liệu | Nội dung |
|---|---|
| [KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md](KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) | Kế hoạch 11 giai đoạn, 6 đợt mua, điều kiện chuyển bước |
| [BAO_CAO_GIAI_DOAN_0.md](BAO_CAO_GIAI_DOAN_0.md) | Giai đoạn 0 — mô phỏng: 220 test, 2.880 ca theo seed, replay |
| [HUAN_LUYEN.md](HUAN_LUYEN.md) | Huấn luyện baseline nhận thức FREE/BLOCKED trên WoodScape (21/09/2026) |
| [autopark/README.md](autopark/README.md) | Mã nguồn: cách cài, chạy mô phỏng, kiểm thử, huấn luyện |

**Mức bằng chứng hiện tại:** mô phỏng trên laptop và AI trên ảnh lưu sẵn. Chưa có kết quả trên phần cứng hay xe thật.

Không nằm trong repo (xem `autopark/.gitignore`): dataset, cache huấn luyện, checkpoint và thư mục `autopark/runs/` — các link tới `runs/` trong tài liệu chỉ mở được trên máy có dữ liệu.
