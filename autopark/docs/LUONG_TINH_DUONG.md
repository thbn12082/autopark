# Luồng tính đường

Cập nhật 26/11/2026 · ✅ đã có trong phần mềm (mô phỏng) · ⏳ chưa làm.

## Các bước

```
1. Pi thu dữ liệu ⏳
   ├── camera, LiDAR, phản hồi xe (gắn thời điểm đo)
   └── định vị (x, y, hướng)
2. Gửi lên Laptop qua Wi-Fi ⏳
3. Laptop
   ├── AI + hợp nhất → bản đồ: trống / vật cản / chưa rõ
   ├── tìm ô đỗ trên bản đồ LiDAR ✅
   ├── chọn ô (bấm trong giao diện) → tư thế đích ✅
   ├── lập quỹ đạo tiến / lùi ✅
   ├── mô phỏng bám đường, không đạt thì loại ✅
   └── người dùng xác nhận ✅
4. Gửi quỹ đạo xuống Pi, một lần ⏳
   └── không gửi từng nhịp lái qua Wi-Fi
5. Pi kiểm trước khi chạy ⏳
   ├── đúng phiên, còn hạn
   ├── xe đứng yên, đúng điểm xuất phát
   ├── hành lang an toàn
   └── sai một điều → từ chối, giữ dừng
6. Pi bám đường, mỗi nhịp dùng số đo ⏳
   └── lệnh tốc độ / góc lái có hạn ── USB ──► ESP32
7. ESP32
   ├── ESC, servo ✅ (thử trên bàn)
   └── đọc MT6701, BNO085 ⏳ (chưa đấu nối)
8. Xong khi
   ├── vị trí, hướng trong dung sai
   └── tốc độ đo ≈ 0
```

## Gói quỹ đạo (Laptop → Pi) ⏳

```
Gói quỹ đạo
├── định danh: phiên, phiên bản
├── hệ tọa độ, cấu hình xe
├── thời gian: lúc lập, hạn dùng
├── đầu, cuối: tư thế + dung sai
├── các điểm: tư thế, tiến/lùi, tốc độ, góc lái
└── giới hạn: tốc độ, hành lang
```

## Sự cố

```
Sự cố
├── Vật mới vào hành lang ........ Pi dừng, không chờ Laptop
├── Dữ liệu cũ, mất định vị ...... Pi dừng
├── Mất Wi-Fi quá hạn ............ Pi dừng
├── Pi treo, đứt USB ............. ESP32 tự dừng
└── Không có đường ............... giữ đứng yên, báo lý do
```

Sau dừng: đo tư thế mới → lập lại → xác nhận lượt mới. **Không tự chạy lại.**

## Mã hiện có

```
autopark/
├── planning/slot_finder.py ....... tìm ô đỗ trên bản đồ LiDAR
├── ui/slot_picker.py ............. nút "Tìm ô đỗ", bấm chọn ô
├── planning/maneuver_planner.py .. lập quỹ đạo, kiểm bám bằng mô phỏng
├── control/tracker.py ............ bộ bám đường
├── simulation/slot_run.py ........ chạy kín: quét → tìm ô → lập → bám
└── application/session.py ........ lập, xem trước, chạy, dừng
```

Liên quan: [Luồng vật cản](LUONG_VAT_CAN.md) · [Lắp ráp điện 2D](LAP_RAP_DIEN_2D.md)
