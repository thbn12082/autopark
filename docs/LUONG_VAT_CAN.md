# Luồng vật cản

```
Thấy vật cản
├── LiDAR thấy
│   └── Pi dừng xe ngay
└── Chỉ camera thấy
    └── Laptop báo Pi → Pi dừng xe

Lỗi
├── Dữ liệu cũ, mất định vị, mất Wi-Fi → Pi dừng xe
└── Pi treo, đứt USB → ESP32 tự dừng

Sau khi dừng
└── Đứng yên → đo vị trí mới → tính đường mới → bạn xác nhận → chạy tiếp
```

Xe **không bao giờ tự chạy lại**.

Liên quan: [Luồng tính đường](LUONG_TINH_DUONG.md)
