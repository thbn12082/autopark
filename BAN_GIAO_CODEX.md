# Bàn giao AutoPark

Cập nhật 26/11/2026. Bản dài cũ (lịch sử từ tháng 9) vẫn còn trong lịch sử git.

## Hiện trạng

```
Phần cứng
├── Pi 4 Model B 8 GB trên xe, nối laptop qua Wi-Fi LAN
├── ESP32-S3 (flash 16 MB) cắm USB vào Pi
│   └── firmware env esp32s3_16mb_pwm: ESC GPIO4, servo GPIO5, đã chạy trên bàn thử 25/11
├── 4 camera USB + LiDAR C1 nối Pi, xem được trên laptop
└── MT6701 ×2, BNO085: có sơ đồ chân đề xuất, CHƯA nối, chưa có driver
    ├── MT6701 #1 góc lái: I²C 0, SDA GPIO6, SCL GPIO7
    ├── MT6701 #2 tốc độ: I²C 1, SDA GPIO8, SCL GPIO9
    └── BNO085: SPI, CS GPIO10, MOSI GPIO11, SCK GPIO12, MISO GPIO13, INT 14, RST 15, PS0 16

Phần mềm (chạy trong mô phỏng)
├── tìm ô đỗ trên bản đồ LiDAR ......... autopark/planning/slot_finder.py
├── nút "Tìm ô đỗ", bấm chọn ô ......... autopark/ui/slot_picker.py
├── chạy kín quét → tìm ô → đỗ ......... autopark/simulation/slot_run.py
├── xe đo thật ......................... configs/vehicle_measured.json (góc lái, tốc độ còn giả định)
└── nút "Ghi LiDAR" trên cửa sổ Pi ..... autopark/ui/remote_sensor_view.py → runs/lidar_pi/

Hiệu chuẩn camera
├── nội tham 4 camera đạt ............. calibration/cam_p1..p4.json
└── ngoại tham BEV: 4 tờ ChArUco in .... calibration/bang_in/to_ngoai_tham/ (chờ in và chụp)
```

## Việc còn lại

1. **Bản đồ sa bàn thật:** bấm "Ghi LiDAR" ở vài chỗ đặt xe → `lidar.map_builder` (lưới 0,02 m) → `planning.slot_finder --map`.
2. **BEV:** in 4 tờ, đặt chạm lốp, chụp mỗi camera một ảnh → `perception/sheet_extrinsics.py solve`.
3. **MT6701 và BNO085:** lắp, nối theo sơ đồ trên, viết driver ESP32. Sau đó đo góc lái tối đa và tốc độ, cập nhật `configs/vehicle_measured.json`.
4. **LiDAR:** ghi vị trí gá đã đo (x 180, y +30, z 160 mm) vào `configs/dinh_vi_lidar_v0.json`; làm 3 bước kiểm p04, DV-2, DV-1.
5. **Pi bám quỹ đạo:** chưa chốt giữa "Pi tự chạy bộ bám" và "laptop lái tạm qua Wi-Fi".

## Quyết định phải giữ

- Không dùng E-stop (đã bỏ theo thiết kế).
- Ô đỗ tìm được không bị giới hạn 0,7 m.
- Không đo tay góc lái hay tốc độ: chờ MT6701.
- AI không lái trực tiếp; Wi-Fi không mang từng nhịp lái; dừng rồi thì không tự chạy lại.

## Chạy nhanh (Windows, tại gốc repo)

```
cai_dat.cmd ............ tạo .venv (một lần)
chay_app.cmd ........... app AutoPark: mọi công cụ trong một cửa sổ (autopark/ui/shell.py)
chay_test.cmd .......... toàn bộ test
chay_kiem_huong.cmd .... cửa sổ quan sát camera + LiDAR từ Pi
```

```powershell
.\.venv\Scripts\python.exe -X utf8 -m autopark.simulation.slot_run --scenario scenarios/tim_khe_vuong_goc.json --out runs/slot_run
```

## Firmware

- PlatformIO lỗi khi đường dẫn có dấu ("xe tự lái"). Chép `firmware/esp32_vehicle` sang thư mục chỉ có ký tự ASCII rồi `pio run -e esp32s3_16mb_pwm`.
- Nạp từ Pi (ESP32 cắm USB vào Pi): esptool với flash 16 MB. Thử trên bàn bằng `firmware/esp32_vehicle/tools/thu_ban_pwm.py`, nhấc bánh khỏi sàn.

Cấu trúc thư mục: xem [README](README.md#cấu-trúc-thư-mục).
