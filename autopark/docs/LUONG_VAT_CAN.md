# Luồng vật cản

Cập nhật 26/11/2026 · thiết kế mục tiêu, chưa chạy trên xe thật.

## Ai làm gì

```
Xe
├── Cảm biến
│   ├── 4 camera ───── hub USB ──► Pi
│   ├── LiDAR C1 ───── USB ──────► Pi
│   └── MT6701 ×2, BNO085 ───────► ESP32   (chưa đấu nối)
├── Pi
│   ├── định vị
│   ├── kiểm hành lang thân xe
│   └── lệnh dừng ──── USB ──────► ESP32
├── ESP32
│   ├── ga, lái (ESC, servo)
│   └── lệnh hết hạn → tự dừng
└── Laptop (Wi-Fi)
    ├── AI trên 4 camera
    └── hợp nhất → yêu cầu dừng về Pi
```

## Hai nhánh phát hiện

```
Vật cản
├── LiDAR thấy ────────► Pi dừng ngay, không chờ Wi-Fi
└── Chỉ camera thấy ───► Pi → Wi-Fi → Laptop AI → Wi-Fi → Pi dừng
                         (chậm hơn: phải tính độ trễ vào tốc độ)
```

## Khi nào dừng

```
Đang chạy
├── Vật ngoài hành lang ................ chạy tiếp
├── Vật vào hành lang .................. DỪNG
├── Vùng mù, chưa rõ ................... DỪNG (không coi là trống)
├── Dữ liệu cũ, mất định vị ............ DỪNG
├── Mất Wi-Fi quá hạn .................. DỪNG
├── Pi treo, đứt USB, lệnh hết hạn ..... ESP32 tự DỪNG
└── Không đo được tốc độ ............... giữ DỪNG, chưa coi là đã đứng yên
```

Hành lang = vùng toàn thân xe sắp quét qua + sai số + quãng dừng.

## Sau khi dừng

```
DỪNG
└── tốc độ đo ≈ 0 đủ lâu
    └── Pi đo tư thế mới
        └── Laptop lập đường mới từ tư thế đó
            └── người dùng xác nhận
                └── chạy lượt mới
```

Vật biến mất hay mạng nối lại → **không tự chạy lại**.

## Mã hiện có

```
Đã có
├── application/session.py ........ dừng, chuẩn bị lượt mới (mô phỏng)
├── fusion/ ....................... hợp nhất vật cản camera + LiDAR
├── safety/freshness.py ........... phát hiện dữ liệu cũ, thiếu
└── firmware/esp32_vehicle ........ lệnh hết hạn → dừng; PWM ESC/servo đã chạy trên bàn
Chưa có
├── dịch vụ trên Pi: thu, kiểm hành lang, dừng
├── giao thức Laptop ↔ Pi
└── phản hồi MT6701, BNO085
```

Liên quan: [Luồng tính đường](LUONG_TINH_DUONG.md) · [Lắp ráp điện 2D](LAP_RAP_DIEN_2D.md)
