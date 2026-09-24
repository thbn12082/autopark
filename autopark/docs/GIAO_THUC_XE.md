# Giao thức laptop ↔ ESP32-S3 (v1), firmware và `VehicleIO` — phần làm khi chưa có mạch (24/09/2026)

**Kế hoạch đối chiếu:** [v3.1](../../KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md) mục 9 (giai đoạn 5, "Khi chưa đủ phần
cứng"), mục 10 (dừng an toàn, reset, reconnect), mục 7 (telemetry có thời gian và cờ hợp lệ), mục 16.2–16.3.

**Mức bằng chứng:** phần mềm + mô phỏng. Chưa có ESP32-S3, MN300, ESC, servo, encoder, AS5600, BNO085, VL53L1X
hay phần cứng dừng. **Mã C++ firmware chưa từng được biên dịch** (máy này không có trình biên dịch C/C++ lẫn
PlatformIO). Phần đã chạy và được test là bản tham chiếu Python của firmware, bộ mã hóa giao thức và `VehicleIO`.
Không số nào dưới đây là số đo trên xe hay trên bo.

| Thành phần | File | Đã kiểm bằng |
|---|---|---|
| Giao thức (CRC, COBS, thông điệp, bộ tách khung) | `autopark/transport/protocol.py` | `tests/test_transport_protocol.py` |
| Bản tham chiếu firmware | `autopark/transport/firmware_model.py` | `tests/test_transport_firmware_model.py` |
| `VehicleIO`: nhánh mô phỏng + nhánh serial | `autopark/transport/vehicle_io.py`, `loopback.py` | `tests/test_transport_vehicle_io.py` |
| Vector mẫu chung Python ↔ C++ | `autopark/transport/vectors.py` → `firmware/esp32_vehicle/test/vectors.json` | cả hai file test Python ở trên |
| Firmware C++ (lõi portable + lớp Arduino) | `firmware/esp32_vehicle/src/` (hướng dẫn biên dịch, test host, đo trên bo: [README firmware](../firmware/esp32_vehicle/README.md)) | **chưa biên dịch**; `test/host/test_main.cpp` sẵn sàng khi có trình biên dịch; kiểm tĩnh mã nguồn (không chạy): `tests/test_transport_firmware_source.py` |
| Cấu hình mô phỏng | `configs/vehicle_io_sim.json` | test nạp file |
| Nối `VehicleIO` vào phiên đỗ xe, chế độ quan sát *(thêm tối 24/09/2026)* | `autopark/application/vehicle_link.py`, `session.py` ([CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md)) | `tests/test_session_vehicle.py` (bo mô phỏng + cổng serial GIẢ) |

## 0. Đã quyết định và CHƯA CHỐT

| Đã quyết định trong phần mềm (có thể đổi, nhưng đổi thì tăng phiên bản giao thức) | CHƯA CHỐT theo bo thực |
|---|---|
| Khung COBS + 0x00, CRC-16/CCITT-FALSE, little-endian, byte phiên bản | Đường vật lý khi lên xe (kế hoạch 1.1: USB là phương án thử trên bàn) |
| Loại thông điệp, trường, đơn vị, độ dài cố định | Loại bo ESP32-S3, cổng USB nào là `Serial` |
| Quy tắc phiên (HELLO), số thứ tự uint16 quay vòng | Chân GPIO ESC/servo/E-stop. Ngõ vào E-stop an toàn khi hở mạch (đã chọn, chưa lắp): tiếp điểm NC nối GND, kéo lên; đứt dây/tuột đầu nối = đang nhấn → FAULT |
| Thời hạn mỗi lệnh + watchdog liên lạc, dốc về trung tính | Xung trung tính/biên độ/chiều ESC, hành vi phanh–lùi, thời gian "trung tính lúc bật" |
| Máy trạng thái BOOT/DISARMED/ARMED/RUNNING/FAULT; reset và reconnect luôn về DISARMED | Ánh xạ góc lái → xung servo (sau `steering_calibration.yaml`) |
| Mất liên lạc phía laptop (`TELEMETRY_STALE`) được chốt trong `VehicleIO`; chỉ `arm()`/`connect()` gỡ (mục 5) | |
| Khóa đổi chiều: về 0, đứng 0 đủ lâu, (nếu đo được) đã dừng | Thời lượng khóa đổi chiều đúng với ESC thật |
| Vòng tốc độ PI số nguyên trong firmware, feedforward + bù vùng chết | Hệ số PI/feedforward/vùng chết (chỉ chọn trên mô hình giả định) |
| Trần \|effort\| độc lập với giới hạn tốc độ; kiểm STALL ở vòng kín (mục 7) | Giá trị trần (mặc định 250 ‰), ngưỡng/thời hạn STALL (200 ‰, 1000 ms) |
| Telemetry 20 Hz mặc định, cờ hợp lệ riêng cho từng số đo | Chế độ báo cáo BNO085, địa chỉ nhiều VL53L1X, cách đo điện áp, ngưỡng sụt áp |
| Giới hạn mặc định = `configs/vehicle_default.json` (GIẢ ĐỊNH) | Giới hạn thật sau khi đo MN300 (giai đoạn 4) |

## 1. Khung trên dây

- Đường truyền dùng thử: USB CDC của ESP32-S3 (baudrate bị bỏ qua). Giao thức không phụ thuộc đường truyền: UART
  hay mạng chỉ thay lớp `transport`.
- **Khung** = `COBS(thông điệp ‖ CRC_lo ‖ CRC_hi) ‖ 0x00`. CRC-16/CCITT-FALSE (đa thức 0x1021, khởi tạo 0xFFFF, không
  đảo bit, không XOR cuối; `CRC("123456789") = 0x29B1`) tính trên toàn bộ thông điệp. COBS theo bộ mã tham chiếu
  (khối 254 byte khác 0 ở cuối không kèm mã 0x01 thừa); kết quả không có byte 0 nên 0x00 chỉ là dấu kết thúc khung.
- Khung nhận dài quá **80 byte** COBS (không kể 0x00) bị bỏ tới 0x00 kế tiếp. Khung dài nhất thật: TELEMETRY 54 byte.
- Bộ tách khung (`FrameParser`, cả Python và C++) không bao giờ ném lỗi; đếm riêng từng loại lỗi:

| Bộ đếm | Khi nào |
|---|---|
| `oversize` | khung vượt 80 byte trước 0x00 |
| `cobs` | COBS hỏng (khối chạy quá cuối khung) |
| `short` | sau giải COBS còn < 10 byte (8 đầu + 2 CRC) |
| `crc` | CRC sai |
| `version` | byte phiên bản ≠ 1 |
| `type` | loại lạ, hoặc loại sai chiều (bo chỉ nhận HELLO/REQUEST/COMMAND; laptop chỉ nhận 0x81–0x84) |
| `length` | độ dài khác độ dài cố định của loại |
| `empty` (không phải lỗi) | 0x00 liên tiếp — dùng để đồng bộ |

Mở cổng giữa dòng thì khung dở đầu tiên thành đúng một lỗi, khung kế đọc bình thường. CRC-16 không tuyệt đối: một
khung hỏng ngẫu nhiên vẫn có xác suất cỡ 1/65 536 lọt qua CRC; kiểm tra phiên bản/loại/độ dài và phiên/số thứ tự
giảm thêm nhưng không về 0.

## 2. Phần đầu (8 byte, mọi thông điệp)

| Byte | Trường | Kiểu | Ghi chú |
|---|---|---|---|
| 0 | `version` | u8 | = 1 |
| 1 | `type` | u8 | bảng dưới |
| 2–5 | `session_id` | u32 | 0 = "không có phiên" (chỉ hợp lệ trong ACK trả lời HELLO session 0) |
| 6–7 | `sequence` | u16 | laptop và bo đếm độc lập; quay vòng |

| Loại | Mã | Chiều | Tổng độ dài |
|---|---|---|---|
| HELLO | 0x01 | laptop → bo | 14 |
| REQUEST | 0x02 | laptop → bo | 9 |
| COMMAND | 0x03 | laptop → bo | 15 |
| HELLO_ACK | 0x81 | bo → laptop | 36 |
| ACK | 0x82 | bo → laptop | 14 |
| TELEMETRY | 0x83 | bo → laptop | 51 |
| FAULT | 0x84 | bo → laptop | 16 |

## 3. Thân thông điệp (offset tính từ đầu thông điệp, little-endian)

**HELLO** (laptop chọn `session_id` ngẫu nhiên ≠ 0)

| Offset | Trường | Kiểu | Đơn vị / ý nghĩa |
|---|---|---|---|
| 8 | `telemetry_period_ms` | u16 | chu kỳ telemetry muốn; 0 = mặc định (50 ms); bo kẹp vào [20, 1000] |
| 10 | `host_time_ms` | u32 | đồng hồ laptop, chỉ để đối chiếu log |

**REQUEST**: offset 8 `action` u8 — 1 ARM, 2 DISARM, 3 CLEAR_FAULT, 4 PING (giữ liên lạc, không đổi lệnh chuyển động).

**COMMAND**

| Offset | Trường | Kiểu | Đơn vị / ý nghĩa |
|---|---|---|---|
| 8 | `validity_ms` | u16 | thời hạn lệnh tính từ lúc BO NHẬN; 0 bị từ chối; bo kẹp về `max_validity_ms` (300 ms) |
| 10 | `flags` | u8 | bit0 ENABLE; bit 1–7 dự trữ, phải 0 (khác 0 → BAD_FIELD) |
| 11 | `speed_mm_s` | i16 | tốc độ mục tiêu mm/s, có dấu (âm = lùi) |
| 13 | `steer_mrad` | i16 | góc lái tương đương mục tiêu, mrad; dương = rẽ trái khi tiến (quy ước `domain/types.py`) |

**HELLO_ACK**

| Offset | Trường | Kiểu | Ý nghĩa |
|---|---|---|---|
| 8 | `hello_sequence` | u16 | số thứ tự của HELLO được trả lời |
| 10 / 11 | `fw_major` / `fw_minor` | u8 | phiên bản firmware |
| 12 | `boot_id` | u32 | ngẫu nhiên mỗi lần khởi động; đổi = bo đã khởi động lại |
| 16 | `reset_reason` | u8 | 0 không rõ, 1 bật nguồn, 2 phần mềm, 3 watchdog, 4 sụt áp, 5 khác |
| 17 | `state` | u8 | trạng thái sau khi nhận HELLO |
| 18 | `telemetry_period_ms` | u16 | chu kỳ TRUNG BÌNH bo dùng (sau kẹp); khoảng cách từng mẫu là bội của chu kỳ điều khiển 10 ms quanh giá trị này (xin 25 ms → 30/20 ms xen kẽ) |
| 20–35 | giới hạn (8 × u16) | u16 | `max_speed_mm_s, max_steer_mrad, max_steer_rate_mrad_s, max_accel_mm_s2, max_decel_mm_s2, stop_decel_mm_s2, max_validity_ms, link_timeout_ms` |

**ACK**: offset 8 `acked_type` u8, 9 `acked_sequence` u16, 11 `result` u8, 12 `state` u8, 13 `fault` u8. Phần đầu
mang **`session_id` của thông điệp được trả lời** (để laptop phiên sai vẫn nhận được lý do). Bo gửi ACK cho mọi
REQUEST (kể cả OK) và cho mọi HELLO/COMMAND bị từ chối; COMMAND được nhận thì KHÔNG có ACK (telemetry báo
`last_cmd_seq`), để không nhân đôi lưu lượng ở 20–50 Hz.

**TELEMETRY**

| Offset | Trường | Kiểu | Đơn vị / ý nghĩa |
|---|---|---|---|
| 8 | `sample_time_ms` | u32 | `millis()` của bo lúc lấy mẫu |
| 12 / 13 / 14 | `state` / `fault` / `stop_reason` | u8 | mục 9 |
| 15 | `flags` | u8 | bit0 ESTOP_INPUT, 1 LINK_OK, 2 CMD_ACTIVE, 3 SPEED_VALID, 4 STEER_VALID, 5 IMU_VALID, 6 SUPPLY_VALID, 7 SPEED_LOOP_CLOSED |
| 16 | `last_cmd_seq` | u16 | COMMAND gần nhất được nhận trong phiên |
| 18 | `cmd_age_ms` | u16 | tuổi lệnh đó (bão hòa 65 534); 65 535 = phiên chưa có lệnh |
| 20 | `speed_measured_mm_s` | i16 | 0 khi SPEED_VALID = 0 |
| 22 | `steer_measured_mrad` | i16 | 0 khi STEER_VALID = 0 |
| 24 | `speed_ref_mm_s` | i16 | mục tiêu sau kẹp + dốc (đầu vào vòng tốc độ) |
| 26 | `steer_ref_mrad` | i16 | góc lái đang xuất (sau kẹp + tốc độ đổi lái) |
| 28 | `effort_permille` | i16 | −1000…1000, đầu ra chuẩn hóa cho ESC (ánh xạ sang xung: CHƯA CHỐT) |
| 30 / 32 / 34 | `gyro_z_mrad_s` / `accel_x_mm_s2` / `accel_y_mm_s2` | i16 | 0 khi IMU_VALID = 0 |
| 36 | `tof_valid_mask` | u8 | bit i = ToF i hợp lệ |
| 37–44 | `tof_mm[4]` | u16 | mm; **0 khi không hợp lệ — không bao giờ dùng số lớn để nói "không thấy gì"** |
| 45 | `supply_mv` | u16 | 0 khi SUPPLY_VALID = 0 |
| 47 | `rx_errors` | u16 | tổng lỗi bộ tách khung phía bo (bão hòa) |
| 49 | `rejects` | u16 | tổng thông điệp bị bo từ chối (bão hòa) |

**FAULT**: offset 8 `fault` u8, 9 `state` u8, 10 `time_ms` u32, 14 `detail` u16 (LOOP_OVERRUN: khoảng hở ms;
SUPPLY_LOW: mV; STALL: |effort| ‰ lúc chốt; còn lại 0). Gửi một lần khi lỗi bị chốt; telemetry tiếp tục mang `fault` tới khi xóa.

## 4. Phiên và số thứ tự

- **Laptop chọn `session_id`** (ngẫu nhiên, ≠ 0) và gửi HELLO. Bo chỉ đổi phiên khi nhận HELLO; không có cách nào
  khác. Sau HELLO, bo lấy `sequence` của HELLO làm mốc.
- REQUEST/COMMAND kiểm theo thứ tự: bo chưa có phiên → `NO_SESSION`; khác phiên → `WRONG_SESSION`;
  `d = (seq − last) mod 65536`: `d = 0` → `DUPLICATE`, `d ≥ 32768` → `OUT_OF_ORDER` (cũ), còn lại nhận (khoảng hở do
  mất gói được chấp nhận). Thông điệp qua được hai kiểm tra này thì cập nhật mốc số thứ tự và làm tươi watchdog liên
  lạc, **kể cả khi sau đó bị từ chối vì trạng thái hoặc trường sai** (nó vẫn đến từ laptop của phiên này).
- HELLO khi đang ARMED/RUNNING → DISARMED (`NEW_SESSION`). HELLO không xóa FAULT, không rút ngắn BOOT. DISARM cũng
  vậy: trong BOOT/FAULT được ACK OK nhưng trạng thái giữ nguyên (chỉ CLEAR_FAULT khi hết nguyên nhân mới xóa FAULT);
  có test và vector (`disarm_and_hello_keep_boot_and_fault`).
- Bo đếm số thứ tự gửi riêng (mọi khung bo gửi, kể cả khung bị bỏ vì đầy bộ đệm — để laptop thấy khoảng hở). Bộ đệm
  gửi `tx_capacity` giới hạn trong 1…1024 byte vì firmware dùng bộ đệm tĩnh 1024 byte (`kTxBufferSize`); bản tham chiếu
  Python từ chối giá trị lớn hơn để hai bên bỏ đúng cùng khung khi đầy (vector `tx_overflow_gap`). Laptop
  bỏ khung bo trùng/cũ và khung phiên khác. Riêng ACK `NO_SESSION`/`WRONG_SESSION` được xử lý không qua kiểm số thứ
  tự: bo vừa khởi động lại thì bộ đếm của nó về 0, và loại ACK này chỉ có thể khiến laptop BỎ phiên (hướng an toàn).
- Laptop phát hiện bo khởi động lại bằng: telemetry ngừng (bo mất phiên thì không gửi), ACK `NO_SESSION`, và
  `boot_id` khác trong HELLO_ACK lần kết nối sau (sự kiện `FIRMWARE_RESET`).

## 5. Thời hạn lệnh và watchdog

| Cơ chế | Mặc định | Hậu quả khi hết |
|---|---|---|
| Thời hạn mỗi COMMAND (`validity_ms`, kẹp ≤ `max_validity_ms`) | laptop gửi 150 ms (`VehicleIO.default_validity_s`, hoặc `validity_s` truyền vào `send()`; trùng giá trị với `DriveCommand.valid_for` nhưng hai bên chưa nối với nhau, xem mục 12); kẹp 300 ms | RUNNING → ARMED, `COMMAND_TIMEOUT`, dốc về trung tính |
| Watchdog liên lạc CỦA BO: không nhận thông điệp hợp lệ nào | 500 ms | ARMED/RUNNING → DISARMED, `LINK_TIMEOUT`; phải ARM lại |
| `TELEMETRY_STALE` CỦA LAPTOP: không có telemetry hợp lệ (mục 10) | 0,3 s (phải ≥ 3 chu kỳ telemetry) | CHỐT phía laptop: gửi DISARM, `send(enable=True)` bị từ chối tới khi `arm()` hoặc `connect()` |
| Vòng điều khiển trễ (hai lần `step` cách nhau) | > 100 ms | FAULT `LOOP_OVERRUN` (chốt) |
| Task watchdog ESP-IDF (chỉ trên bo) | 300 ms (Arduino 3.x); Arduino 2.x (bản build mặc định theo `platformio.ini`, `platform = espressif32`): 1 s nếu `esp_task_wdt_init(1, true)` thành công, nếu TWDT đã khởi tạo sẵn thì giữ thời hạn cũ (thường 5 s) — CẦN KIỂM TRÊN BO | TWDT: guard đã ép trung tính sau 100 ms; panic → móc kéo chân ESC xuống thấp (mất xung) tới `setup_outputs()`; chip khởi động lại → BOOT → DISARMED (chưa đo) |
| Bộ hẹn giờ `esp_timer` ép ESC trung tính (chỉ trên bo) | loop im > 100 ms | xung ESC = trung tính |
| Panic tức thời, interrupt watchdog, `esp_restart()` (chỉ trên bo) | — | chỉ reset CPU, LEDC không dừng; móc panic/shutdown kéo chân ESC xuống thấp tới `setup_outputs()` (chưa biên dịch, chưa đo); bật nguồn/system reset: chân thả nổi → điện trở kéo xuống ngoài |

Thời hạn tính từ lúc **bo nhận**; trễ truyền trước đó bo không biết. Laptop thấy trễ qua `cmd_age_ms`,
`stats.cmd_echo_s` và `stats.ack_rtt_s` (mục 10). PING giữ liên lạc nhưng không kéo dài lệnh chuyển động: nếu ứng
dụng trên laptop treo mà luồng `Heartbeat` vẫn chạy, xe vẫn dừng theo thời hạn lệnh (có test). *(Cập nhật tối
24/09/2026.)* Bo khi đó ở ARMED, và ARMED + COMMAND enable=1 → RUNNING (mục 6): điều giữ xe đứng yên lúc ứng dụng hết
treo là phía laptop, không phải bo. Trong phiên đỗ xe qua `VehicleIO` đã tìm thấy một khoảng trống (chỉ trên mô phỏng,
mục 12). *(Cập nhật muộn hơn tối 24/09/2026: khoảng trống này đã được sửa cùng tối ở phía laptop (`VehicleLink.refresh()`
trước nhịp điều khiển + chặn gửi khi còn sự kiện dừng chưa xử lý). Mới kiểm trên bo mô phỏng và cổng serial giả, CHƯA
THỬ với bo thật; mục 12.)*

Hai khái niệm "mất liên lạc" là HAI cơ chế khác nhau, không được lẫn:
- **Watchdog của bo** (500 ms không nhận thông điệp hợp lệ → DISARMED). Một đợt mất ngắn hơn 500 ms nhưng dài hơn thời
  hạn lệnh chỉ đưa bo về ARMED (`COMMAND_TIMEOUT`); nếu chỉ mất chiều bo → laptop mà `Heartbeat` vẫn PING thì bo không
  bao giờ thấy mất liên lạc.
- **`TELEMETRY_STALE` của laptop** (0,3 s không có telemetry) được CHỐT trong `VehicleIO`: laptop gửi DISARM (tới được
  bo nếu chiều laptop → bo còn thông) và từ chối mọi `send(enable=True)`; telemetry có lại chỉ sinh
  `TELEMETRY_RESUMED` (LOG), KHÔNG gỡ chốt. Chỉ `arm()` thành công (thao tác cho phép mới) hoặc `connect()` (phiên mới,
  bo về DISARMED) mới gỡ. Vì vậy mọi đợt mất liên lạc mà laptop nhận ra đều cần một thao tác cho phép mới trước khi xe
  chạy lại (kế hoạch mục 10 bước 6, mục 13), kể cả khi bo chưa kịp tự DISARM. `stop()` (enable=0) vẫn gửi được.

## 6. Máy trạng thái

```text
          hết boot_hold                  ARM                COMMAND enable=1 (gửi SAU ARM)
  BOOT ───────────────> DISARMED ─────────────> ARMED ─────────────────────────> RUNNING
    │                     ^   ^                   │  ^                              │
    │                     │   │ DISARM / HELLO mới │  └── lệnh hết hạn / enable=0 ───┘
    │                     │   └── mất liên lạc ────┴──────────────────────────────────┘
    │   CLEAR_FAULT khi hết nguyên nhân (không bao giờ về thẳng ARMED/RUNNING)
    │                     │
    └──── mọi trạng thái ──> FAULT (chốt: E-stop, LOOP_OVERRUN, SUPPLY_LOW, FEEDBACK_LOST, STALL)
```

| Trạng thái | Đầu ra | Nhận |
|---|---|---|
| BOOT | trung tính | HELLO (giữ BOOT); ARM/COMMAND → `NOT_READY` |
| DISARMED | dốc tốc độ về 0 (`stop_decel`), rồi trả lái về giữa | ARM; COMMAND → `BAD_STATE` (không được nhớ để chạy sau) |
| ARMED | như DISARMED | COMMAND enable=1 → RUNNING; enable=0 → ở ARMED |
| RUNNING | bám mục tiêu đã kẹp, có dốc | COMMAND cập nhật mục tiêu và thời hạn |
| FAULT | effort = 0 NGAY (không dốc), mục tiêu tốc độ = 0, giữ góc lái | CLEAR_FAULT; ARM/COMMAND → `FAULT_ACTIVE` |

- **Reset và reconnect (HELLO mới) luôn kết thúc ở DISARMED** (hoặc BOOT/FAULT): "reconnect không tự chạy tiếp". Sau
  ARM phải gửi COMMAND enable mới; lệnh cũ đã bị xóa khi DISARM/ARM. Mất liên lạc ngắn hơn watchdog của bo mà KHÔNG
  kết nối lại thì bo có thể chỉ ở ARMED; điều ngăn xe tự chạy lại khi đó là chốt `TELEMETRY_STALE` phía laptop (mục 5),
  không phải máy trạng thái của bo.
- E-stop (ngõ vào) chốt FAULT ở mọi trạng thái; CLEAR_FAULT bị từ chối (`ESTOP_ACTIVE`) khi nút còn nhấn. SUPPLY_LOW chỉ
  xóa được khi điện áp đo lại ≥ ngưỡng. Lỗi đầu tiên được giữ làm nguyên nhân gốc.
- Ngõ vào E-stop của firmware **không thay** đường cắt động lực phần cứng (kế hoạch mục 2.1, mục 10). Ngõ vào E-stop an
  toàn khi hở mạch: đứt dây/tuột đầu nối = đang nhấn → FAULT (tiếp điểm NC nối GND, điện trở kéo về phía mức tích cực;
  `main.cpp`, chưa lắp, chưa thử). Cắm nhầm tiếp điểm NO thì xe luôn ở FAULT.
- STALL (vòng kín, mục 7) chốt như mọi lỗi; CLEAR_FAULT xóa được ngay (không có ngõ vào giữ chốt), sau đó vẫn phải ARM.

## 7. Giới hạn, dốc, đổi chiều, vòng tốc độ

Tất cả là số nguyên: mục tiêu tốc độ lưu bằng µm/s, góc bằng µrad; gia tốc mm/s² × dt ms = µm/s, không làm tròn.

- **Kẹp**: `|speed| ≤ max_speed_mm_s` (300), `|steer| ≤ max_steer_mrad` (524 ≈ 30°). Lệnh vượt giới hạn bị kẹp, không bị
  từ chối; giá trị đang dùng hiện ở `speed_ref_mm_s`/`steer_ref_mrad`. Kẹp này chỉ áp lên MỤC TIÊU, **không giới hạn tốc
  độ thật**: chạy mạch hở (chưa có encoder), feedforward giả định cho 300 mm/s là 100 + 2000 × 0,3 = 700 ‰ (≈ 70 % ga,
  1850 µs với ánh xạ mặc định), tốc độ thật tương ứng chưa biết; vòng kín với encoder báo sai thì effort bão hòa.
- **Trần effort**: `|effort| ≤ max_effort_permille` (mặc định 250 ‰, CHƯA CHỐT, thận trọng cho lần thử đầu) ở cả mạch hở
  lẫn vòng kín; chống bão hòa tích phân dùng đúng trần này. Mô phỏng (`vehicle_io.SIM_FIRMWARE_DEFAULT`) đặt 1000 ‰ vì
  cơ cấu chấp hành giả định cần effort cao; đó là số của mô phỏng.
- **STALL**: ở vòng kín, nếu `|effort| ≥ stall_effort_permille` (200), mục tiêu > `standstill_mm_s` và số đo không đi
  theo chiều mục tiêu (`sign(ref) · v_đo ≤ standstill_mm_s`: encoder kẹt 0 với cờ hợp lệ, encoder đảo dấu, bánh kẹt) liên
  tục `stall_timeout_ms` (1000, 0 = tắt) → FAULT `STALL` (effort 0 ngay). `FEEDBACK_LOST` chỉ bắt cờ không hợp lệ; STALL
  bắt số đo hợp lệ mà vô lý. Không có encoder thì không kiểm được: khi đó chỉ còn trần effort.
- **Dốc**: tăng độ lớn ≤ `max_accel` (300 mm/s²), giảm ≤ `max_decel` (600) khi RUNNING, ≤ `stop_decel` (600) khi dừng do
  hết lệnh/disarm/mất liên lạc; góc lái ≤ `max_steer_rate` (1571 mrad/s ≈ 90°/s). Khi dừng, góc lái được giữ tới khi
  mục tiêu tốc độ về 0 rồi mới trả về giữa.
- **Đổi chiều**: mục tiêu giảm về 0 (không vượt qua 0 trong một bước), đứng ở 0 ít nhất `direction_change_hold_ms`
  (300 ms, CHƯA CHỐT) và — nếu có phản hồi tốc độ — `|v đo| ≤ standstill_mm_s` (10) mới sang chiều mới. Đây là trình
  tự "giảm tốc → xác nhận dừng → đổi chiều" của kế hoạch mục 9; hành vi thật của ESC khi lùi vẫn phải đo.
- **Vòng tốc độ** (chạy trong firmware vì encoder nằm ở bo):
  `effort = sign(ref)·(deadzone_comp + ff·|ref|) + kp·(ref − v_đo) + I`, kẹp ±`max_effort_permille`; không bao giờ đẩy ngược chiều
  mục tiêu (phanh/lùi của ESC là CHƯA CHỐT); tích phân dừng khi đầu ra bão hòa theo hướng sai số (chống bão hòa) và bị
  kẹp `integ_limit`. Không có phản hồi tốc độ → chỉ feedforward (cờ `SPEED_LOOP_CLOSED` = 0).
  Mục tiêu = 0 hoặc FAULT → effort = 0 và xóa tích phân.

## 8. Telemetry

- Chu kỳ mặc định 50 ms (20 Hz), laptop chọn trong [20, 1000] ms qua HELLO. Chỉ gửi khi có phiên. Bo chỉ gửi ở biên
  chu kỳ điều khiển 10 ms, lên lịch theo hạn trước (hạn kế = hạn trước + chu kỳ, không phải "lúc gửi + chu kỳ"): chu kỳ
  trung bình đúng bằng giá trị trong HELLO_ACK, từng khoảng cách ≤ chu kỳ + 10 ms; mỗi chu kỳ điều khiển gửi tối đa
  một mẫu, tụt sau quá một chu kỳ (vòng trễ) thì bắt nhịp lại, không gửi dồn.
- Ngưỡng `TELEMETRY_STALE` của laptop (mặc định 0,3 s) phải ≥ 3 lần chu kỳ telemetry (so bằng ms nguyên), để một khung
  mất cộng dao động thời gian không bị coi là mất liên lạc. Mặc định 0,3 s vì vậy cho phép chu kỳ tới 100 ms; chu kỳ
  dài hơn thì phải tăng `telemetry_timeout_s` tương ứng, nếu không hàm dựng `VehicleIO` (chu kỳ xin) hoặc `connect()`
  (chu kỳ bo thật sự chọn, kể cả mặc định của bo khi xin 0) từ chối.
- Mỗi số đo có cờ hợp lệ riêng; số đo không hợp lệ gửi 0 và laptop đổi thành `None` (`VehicleTelemetry`). Mảng ToF
  dùng mặt nạ bit. Đúng yêu cầu mục 7: "lỗi sensor không bị biến thành giá trị khoảng cách an toàn".
- Hợp đồng tối thiểu của kế hoạch mục 9 → trường: `sample_time` → `sample_time_ms`; `sequence` → phần đầu;
  `speed_measured`, `steering_measured`; `imu` → `gyro_z/accel_x/accel_y`; `tof` → `tof_mm[4]` + mặt nạ;
  `supply/status` → `supply_mv`, `state`, `flags`, `stop_reason`, `rx_errors`, `rejects`; `fault` → `fault` + FAULT.
  Hợp đồng lệnh: `session_id`, `sequence` (phần đầu), `validity/timeout` → `validity_ms`, `enable` → bit0 `flags`,
  `speed_target` → `speed_mm_s`, `steering_target` → `steer_mrad`.
- IMU mới có tốc độ quay trục z và gia tốc x/y (đủ cho ước lượng phẳng); quaternion BNO085 chưa có trường — thêm
  thì tăng phiên bản giao thức.

## 9. Mã

| `result` (ACK) | | `stop_reason` | | `fault` | |
|---|---|---|---|---|---|
| 0 | OK | 0 | NONE | 0 | NONE |
| 1 | NO_SESSION | 1 | BOOT | 1 | ESTOP |
| 2 | WRONG_SESSION | 2 | HOST_DISARM | 2 | LOOP_OVERRUN |
| 3 | DUPLICATE | 3 | COMMAND_TIMEOUT | 3 | SUPPLY_LOW (ngưỡng CHƯA CHỐT, mặc định tắt) |
| 4 | OUT_OF_ORDER | 4 | LINK_TIMEOUT | 4 | FEEDBACK_LOST (chỉ khi bật `require_speed_feedback`) |
| 5 | BAD_STATE | 5 | NEW_SESSION | 5 | STALL (vòng kín: effort cao mà xe không đi theo chiều mục tiêu) |
| 6 | FAULT_ACTIVE | 6 | ENABLE_CLEARED | | |
| 7 | ESTOP_ACTIVE | 7 | FAULT | | |
| 8 | BAD_FIELD | | | | |
| 9 | NOT_READY | | | | |

Mã `fault` 5 (STALL) được thêm ngày 24/09/2026 mà KHÔNG tăng `PROTOCOL_VERSION` (bố cục byte không đổi, chưa bo nào
được nạp). Laptop bản cũ gặp mã 5 sẽ ném `ValueError` khi giải telemetry/FAULT, nên phải cập nhật hai bên cùng lúc.

## 10. Phía laptop: `VehicleIO`

- Một lớp cơ sở `VehicleIO` (phiên, số thứ tự, chờ ACK, lọc telemetry, sự kiện) và hai nhánh:
  `SimVehicleIO` (laptop ↔ trễ/mất gói ↔ `FirmwareModel` → cơ cấu chấp hành có trễ + vùng chết → `SimVehicle` →
  cảm biến có trễ + nhiễu) và `SerialVehicleIO` (pyserial; thử ở đây chỉ qua `FirmwareSerialLoopback`). Hai nhánh đi
  qua **cùng byte** (có test so từng byte), cùng đơn vị: API m/s, rad; dây mm/s, mrad (làm tròn nửa ra xa 0).
- **Không mặc định cùng độ trễ.** Độ trễ mô phỏng là tham số trong `configs/vehicle_io_sim.json` (giả định: 4 ms mỗi
  chiều, cơ cấu chấp hành 30 ms, encoder 20 ms, góc lái 10 ms). Cả hai nhánh đo cùng hai đại lượng theo cùng cách:
  `stats.ack_rtt_s` (REQUEST → ACK) và `stats.cmd_echo_s` (COMMAND → telemetry đầu tiên báo đã nhận; cận trên, gồm
  chờ chu kỳ telemetry). Số của bo thật phải đo, không lấy số mô phỏng.
- API xác định cho test: `connect()` (phiên mới, chờ HELLO_ACK) → `wait_ready()` → `arm()` → `send(speed, steer)`
  mỗi chu kỳ; `poll()` (serial) hoặc `advance(dt)` (mô phỏng) trả MỌI telemetry nhận được kể từ lần gọi trước.
  `Heartbeat` là luồng nền tùy chọn: chỉ `service()` (tiến I/O + kiểm STALE, KHÔNG lấy hàng đợi của `poll()`) và PING,
  không bao giờ lặp lệnh chuyển động; khi nó chạy, `poll()` của ứng dụng vẫn nhận đủ mọi khung (có test đếm từng số
  thứ tự). Hàng đợi chờ `poll()` có giới hạn (`new_telemetry_limit`, mặc định 512 ≈ 10 s ở 50 Hz): ứng dụng chỉ đọc
  `latest()` thì khung cũ nhất bị đẩy ra và được đếm ở `stats.telemetry_unpolled_dropped`, không phình bộ nhớ.
- *(Thêm tối 24/09/2026.)* `poll(block=False)` (và `service(block=False)`): chỉ đọc byte đã có sẵn trong cổng; cổng rỗng
  thì trả ngay, không chờ timeout đọc (10 ms với `SerialVehicleIO.open`). Vòng điều khiển của phiên đỗ xe dùng dạng
  này (`VehicleLink.pump`, [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md) mục 4 quy tắc 4). Mặc định vẫn `block=True` (một lần
  đọc chờ tối đa timeout của cổng khi chưa có byte), dùng trong các hàm chờ (`connect`, `wait_ready`, `arm`...) và trong
  `Heartbeat`. Nhánh mô phỏng bỏ qua `block` (mỗi lần gọi là đúng một nhịp mô phỏng).
- *(Thêm muộn hơn tối 24/09/2026.)* `take_new()` (hàm công khai mới): trả telemetry đang chờ trong hàng đợi của
  `poll()` (kể cả khung do `Heartbeat` đọc) mà KHÔNG tiến I/O: không đọc cổng, không chạy thêm nhịp bo mô phỏng, không
  đẩy đồng hồ mô phỏng, không kiểm STALE. `VehicleLink.refresh()` dùng nó với bo mô phỏng; với bo thật `refresh()` dùng
  `poll(block=False)` (mục 12). Chưa có test riêng trong `test_transport_vehicle_io.py`; được kiểm qua
  `tests/test_session_vehicle.py`.
- *(Thêm tối 24/09/2026.)* Đồng hồ mặc định của `SerialVehicleIO` là `time.perf_counter()` tính từ lúc tạo đối tượng
  (trước đó là `time.monotonic()`). Lý do: trên Windows `time.monotonic()` là `GetTickCount64()`, độ phân giải 15,625 ms
  (`time.get_clock_info`, Python 3.12.10, máy bàn, kiểm lại tối 24/09/2026; `perf_counter` là
  `QueryPerformanceCounter()`, 1e-07 s), mà thời gian phiên và nhịp điều khiển 20 ms bám `now()` của nhánh này. Truyền
  `clock=` thì dùng đồng hồ đó (test dùng `ManualClock`).
- Sự kiện (`SafetyEvent`, `events()`): `TELEMETRY_STALE` (STOP; telemetry cũ hơn `telemetry_timeout_s` = 0,3 s — "mất
  liên lạc" phía laptop; CHỐT: gửi DISARM, `rearm_required = True`, `send(enable=True)` ném `VehicleIOError` tới khi
  `arm()`/`connect()`), `TELEMETRY_RESUMED` (LOG; không gỡ chốt), `VEHICLE_FAULT` (STOP), `VEHICLE_STOPPED` (kèm lý do),
  `SESSION_LOST` (STOP), `FIRMWARE_RESET` (STOP), `LINK_ERROR` (STOP; lỗi cổng/rút cáp), `COMMAND_REJECTED` (báo một
  lần mỗi loại, đếm mọi lần).
- `telemetry_timeout_s` phải ≥ 3 × chu kỳ telemetry (mục 8): kiểm ở hàm dựng với chu kỳ xin và ở `connect()` với chu kỳ
  bo trả trong HELLO_ACK; không thỏa thì `connect()` ném lỗi và KHÔNG nhận phiên (`connected` giữ False).
- `configs/vehicle_io_sim.json`: khóa lạ hoặc gõ sai ở mọi mục (gốc, `link`, `actuator`, `sensors`, `firmware`) bị từ
  chối; khóa vắng mặt lấy mặc định của các dataclass `Sim*Config` (một bộ mặc định duy nhất, đều là giả định). Mục
  `firmware` lấy `SIM_FIRMWARE_DEFAULT` = `FirmwareConfig()` với trần effort 1000 ‰; từ 24/09 file JSON ghi rõ ba khóa
  `max_effort_permille` = 1000, `stall_effort_permille` = 200, `stall_timeout_ms` = 1000 (trần 1000 ‰ chỉ cho mô phỏng;
  firmware thật mặc định 250 ‰).
- `SimVehicleIO.reset_firmware(reason, hold_last_output_ms=0)`: bo khởi động lại, mất phiên, về BOOT. Mặc định mô phỏng
  firmware CÓ móc panic kéo chân ESC xuống thấp (cơ cấu chấp hành thôi kéo ngay) và giả định ESC coi mất xung là không
  kéo — cả hai CHƯA KIỂM trên bo. `hold_last_output_ms > 0` mô phỏng trường hợp xấu (reset CPU không dừng LEDC, móc không
  chạy): ga cuối cùng giữ nguyên trong khoảng đó dù bo đang BOOT.
- Telemetry đóng dấu bằng **thời điểm laptop nhận** (`stamp.t`, theo `now()` của nhánh — với `SerialVehicleIO` mặc
  định là `perf_counter` ở trên); tuổi tính từ đó nhỏ hơn tuổi thật một khoảng trễ truyền. `source_policy()` trả
  `SourcePolicy` cho `FreshnessMonitor` với cùng ngưỡng.

### Kết quả mô phỏng (bộ điều khiển với vùng chết, trễ, phản hồi nhiễu)

Cấu hình `configs/vehicle_io_sim.json` (mọi số GIẢ ĐỊNH; trần effort của firmware mô phỏng 1000 ‰, xem trên): vùng
chết ESC 150 ‰ nhưng firmware chỉ bù 100 ‰;
xe đạt 0,8 m/s ở effort tối đa nhưng feedforward giả định 0,5 m/s; trễ cơ cấu chấp hành 30 ms; encoder trễ 20 ms,
nhiễu σ = 0,01 m/s; xe mô phỏng `vehicle_default.json` (tăng tốc 0,3 m/s², phanh 0,6 m/s²). Laptop gửi lệnh mỗi
50 ms. Sai số = tốc độ THẬT của xe mô phỏng − mục tiêu, lấy từ 2 s tới 4 s sau bước; 3 seed.

| Mục tiêu | Sai số TB | max \|sai số\| | Đỉnh | Vào ±2 cm/s sau |
|---|---|---|---|---|
| 0,05 m/s | −0,0001…+0,0005 | 0,0076–0,0102 | 0,063–0,067 | 0,25 s |
| 0,10 m/s | +0,0001…+0,0005 | 0,0068–0,0101 | 0,150–0,154 | 0,90–1,00 s |
| 0,15 m/s | +0,0004…+0,0010 | 0,0064–0,0109 | 0,231–0,235 | 1,35–1,45 s |
| 0,10 m/s, không encoder (feedforward hở) | +0,041 (xác lập 0,141) | | | không vào |
| 0,10 m/s, feedforward khớp mô hình | +0,0004 | 0,0044 | 0,122 | 0,50 s |

Đọc bảng: vòng PI bù được vùng chết và hệ số sai (sai số TB < 1 mm/s), nhưng **vọt lố 26–57 %** (50–57 % ở 0,10 và
0,15 m/s) khi feedforward sai lệch như giả định, và 21–24 % ngay cả khi feedforward khớp (trễ 50 ms + dốc firmware bằng đúng gia tốc tối đa của
xe mô phỏng). Hệ quả cho xe thật: feedforward phải lấy từ đường cong lệnh–tốc độ đo ở giai đoạn 4, và `max_accel`
của firmware nên thấp hơn gia tốc xe làm được. `kp = 500 ‰/(m/s)`, `ki = 4000 ‰/(m/s·s)` được chọn bằng quét lưới
trên chính mô hình này (kp lớn hơn gây dao động giới hạn ±0,02 m/s do trễ); không có giá trị gì với xe thật.
Dừng khi ứng dụng ngừng gửi lệnh (đang 0,15 m/s): xe mô phỏng đứng yên sau 0,39 s, trôi thêm 3,9 cm — chỉ là
con số của mô hình, không phải quãng dừng xe thật (kế hoạch mục 16.2 "Điều khiển", "Phản ứng lỗi": cần chốt trên xe).

## 11. Kiểm chứng

Chạy trong `D:/ap/autopark`, `.venv` (Python 3.12, pyserial 3.5, không torch):

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_transport_protocol.py tests/test_transport_firmware_model.py tests/test_transport_vehicle_io.py tests/test_transport_firmware_source.py
.\.venv\Scripts\python.exe -X utf8 -m autopark.transport.vectors --check
```

Nội dung test (đều không mở cổng thật nào):
- **Giao thức**: giá trị kiểm CRC; các ví dụ COBS chuẩn (kể cả khối 254/255 byte); khứ hồi mọi loại thông điệp với giá
  trị biên; bố cục byte little-endian; mã hóa từ chối giá trị tràn thay vì cắt ngầm; từng loại lỗi khung được đếm và
  khung sau vẫn nhận; cắt cụt ở mọi vị trí; giới hạn độ dài; lọc chiều; fuzz 12 seed (rác, lật bit, khung cụt): không
  bao giờ ném lỗi, không bao giờ trả thông điệp không có trong tập gốc, mọi khung nguyên vẹn đều được nhận.
- **Bản tham chiếu firmware**: BOOT im lặng và trung tính; HELLO_ACK; lệnh trước ARM không được nhớ; trùng/cũ/quay
  vòng số thứ tự với 5 mốc bắt đầu; phiên mới; hết hạn lệnh → dốc đúng `stop_decel` rồi trả lái; PING giữ liên lạc mà
  không giữ chuyển động; watchdog liên lạc đúng 300 ms (cấu hình test); reconnect không chạy tiếp; kẹp thời hạn;
  trường sai; E-stop chốt; LOOP_OVERRUN; SUPPLY_LOW; FEEDBACK_LOST; kẹp + dốc tốc độ/góc; khóa đổi chiều có/không
  phản hồi; tích phân và chống bão hòa; telemetry số đo không hợp lệ = 0 + cờ; đếm lỗi; đầy bộ đệm gửi; `millis()`
  quay vòng; DISARM khi đang chạy → DISARMED, dốc đúng `stop_decel`, giữ lái tới khi dừng; DISARM/HELLO trong BOOT và
  FAULT không rút ngắn BOOT, không xóa lỗi; chu kỳ telemetry trung bình = HELLO_ACK với 20/25/33/50/55 ms, vòng trễ chỉ
  gửi một mẫu rồi bắt nhịp lại; `tx_capacity` ≤ 1024 và khớp `kTxBufferSize` đọc từ `vehicle_core.h`; chạy lại mọi kịch
  bản vector từng byte (kể cả số khung bỏ vì đầy bộ đệm); vector phủ mọi trạng thái, mọi mã kết quả, mọi lý do dừng,
  DISARM/HELLO trong BOOT/RUNNING/FAULT. Trần effort: không bao giờ vượt `max_effort_permille` ở mạch hở, encoder kẹt 0
  và encoder đảo dấu, cả hai chiều, telemetry cũng vậy; trần mặc định nhỏ hơn feedforward ở `max_speed` (700 ‰). STALL:
  chốt đúng `stall_timeout_ms` với encoder kẹt 0 và đảo dấu, effort 0 ngay, một FAULT với `detail` = |effort|, lệnh sau
  bị `FAULT_ACTIVE`, CLEAR_FAULT → DISARMED; không chốt khi xe bám mục tiêu, khi không có encoder, khi điều kiện bị ngắt
  quãng; cấu hình trần/ngưỡng sai bị từ chối; vector `effort_cap_and_stall` (C++ phải ra cùng byte).
- **VehicleIO**: đơn vị chung; hai nhánh cùng giao diện và cùng byte; vòng kín theo bậc với vùng chết/trễ/nhiễu (3 seed,
  |sai số TB| < 5 mm/s, max < 2 cm/s sau 2 s) và đối chứng không encoder (tốc độ xác lập đúng giá trị công thức vùng
  chết cho, ≈ 0,141 m/s, sai số > 3 cm/s); mô hình cơ cấu chấp hành được kiểm trực tiếp: effort trong vùng chết không
  làm xe nhúc nhích, trễ chấp hành 0/30/60 ms dời đúng thời điểm xe bắt đầu chạy, encoder trễ đúng
  `speed_latency_ms`, độ lệch chuẩn nhiễu encoder đo lại nằm trong ±20 % giá trị cấu hình; không ARM thì không nhúc
  nhích; ngừng gửi → tự dừng < 0,6 s; mất liên lạc → dừng, DISARMED, reconnect phải ARM lại; mất liên lạc 0,4 s (giữa
  thời hạn lệnh và watchdog của bo) rồi cắm lại KHÔNG connect() → mọi `send()` bị từ chối, xe không chạy lại tới khi
  `arm()`; chỉ mất chiều bo → laptop → laptop gửi DISARM, xe dừng ≤ 0,6 s sau STALE; bo reset → phát hiện
  (SESSION_LOST ngay sau STALE), không tự chạy; E-stop; độ trễ đo được thay đổi theo cấu hình; cấu hình mô phỏng từ
  chối khóa lạ/gõ sai; nhánh serial qua cổng giả: kết nối, bỏ khung trùng/cũ/phiên khác, rút cáp → LINK_ERROR, mở lại
  vẫn DISARMED; bo treo → TELEMETRY_STALE; luồng `Heartbeat` giữ liên lạc 3 s mà không lặp lệnh chuyển động, và khi
  nó chạy `poll()` của ứng dụng vẫn nhận đủ mọi khung (đếm từng số thứ tự); hàng đợi `poll()` có giới hạn và đếm khung
  bị đẩy ra; `telemetry_timeout_s` < 3 chu kỳ bị từ chối ở hàm dựng và ở `connect()`; chu kỳ 50/100/500 ms với ngưỡng
  tương ứng chạy 5 s không báo STALE. Trần 250 ‰ trong cả chuỗi mô phỏng: lệnh 0,3 m/s nhưng xe mô phỏng không vượt
  ≈ 0,094 m/s (có và không encoder); vùng chết ESC 300 ‰ > trần → xe đứng yên, bo chốt STALL, laptop nhận mã 5 và
  `VEHICLE_FAULT`. Bo reset khi đang chạy: mặc định (có móc) cơ cấu chấp hành thôi kéo ngay; `hold_last_output_ms = 400`
  (không có móc) → ga cuối giữ nguyên 400 ms dù bo đã BOOT, xe còn chạy ở 0,3 s. Mục `firmware` thiếu khóa lấy
  `SIM_FIRMWARE_DEFAULT`, khóa có thì giữ.
  *(Cập nhật tối 24/09/2026.)* `poll(block=False)` và đồng hồ mặc định `perf_counter` (mục 10) chưa có test riêng trong
  `test_transport_vehicle_io.py`; chúng được kiểm qua phiên đỗ xe trong `tests/test_session_vehicle.py` bằng cổng
  serial GIẢ (`test_realtime_link_session_clock_follows_io_clock_without_blocking_reads`,
  `test_realtime_serial_link_does_not_block_the_ui_tick`, `test_serial_default_clock_is_fine_grained`).
- **Kiểm tĩnh mã C++** (`test_transport_firmware_source.py`; đọc mã nguồn, KHÔNG biên dịch hay chạy C++): mặc định
  `ap::Config` = `FirmwareConfig()`; `test_main.cpp` đọc được mọi khóa cấu hình; enum `protocol.h` = enum Python;
  `update_speed_loop` dùng trần, `step` gọi `check_stall` ngay sau vòng tốc độ; `output_guard` đọc mốc của loop trước
  `millis()` và so hiệu int32 (kèm phép tính cho trường hợp loop ghi mốc mới hơn và `millis()` quay vòng); E-stop hở
  mạch đọc là đang nhấn với cả hai giá trị `kEstopActiveLow`; móc panic/`esp_restart()` kéo chân ESC xuống thấp (mức 0
  trước, rồi tách LEDC, không ghi duty), được đăng ký sau `setup_outputs()`, và `platformio.ini` có cờ `--wrap`.

Kết quả chạy ngày 24/09/2026 (`.venv`), sau đợt sửa theo phản biện: **157 đạt, 0 lỗi** (giao thức 52, bản tham chiếu
firmware 60, VehicleIO 45; ≈ 8,5 s); `vectors --check` báo file cập nhật; các test có sẵn liên quan
(`test_vehicle_model`, `test_tracker`, `test_runtime_safety`, `test_phase0`, `test_session`) 77 đạt. Để chắc test
không "đạt cho có", đã chạy đột biến mã trên một BẢN SAO của gói (script ngoài repo, không sửa mã nguồn): đợt đầu 21
đột biến (bỏ kiểm trùng/cũ/sai phiên, HELLO không disarm, lệnh không hết hạn, bỏ watchdog, nhận lệnh khi DISARMED,
CLEAR_FAULT bỏ qua E-stop, bỏ chống bão hòa, bỏ tích phân, bỏ khóa đổi chiều, bỏ kẹp tốc độ, lỗi dốc thay vì cắt, báo
ToF không hợp lệ, bỏ CRC, laptop không lọc số thứ tự/phiên, không báo TELEMETRY_STALE, Heartbeat lặp lệnh chuyển động,
kết nối lại giữ phiên cũ, ARM giữ lệnh cũ; đột biến "giữ phiên cũ" ban đầu sống sót, đã thêm test khung lệnh cũ tới
muộn sau khi kết nối lại). Đợt sau 22 đột biến cho các chỗ đã sửa (bỏ chốt STALE ở `send`/ở `check`, `arm()` không gỡ
chốt, telemetry có lại tự gỡ chốt, không gửi DISARM lúc STALE, lịch telemetry theo `now`, không bắt nhịp lại, Heartbeat
dùng `poll()`, không đếm khung bị đẩy khỏi hàng đợi, bỏ kiểm chu kỳ ở hàm dựng/ở `connect()`, so chu kỳ bằng số thực,
bỏ kiểm khóa cấu hình mô phỏng, bỏ giới hạn `tx_capacity`, DISARM đổi trạng thái trong BOOT/FAULT, DISARM bị bỏ qua khi
RUNNING, HELLO disarm trong mọi trạng thái, DISARM cắt tốc độ thay vì dốc, bỏ vùng chết/trễ chấp hành/nhiễu encoder/trễ
encoder khỏi mô hình): cả 22 đều làm ít nhất một test hỏng; các đột biến của bản tham chiếu firmware bị bắt bởi test
đơn vị riêng, không chỉ bởi test so file vector.

Đợt sửa thứ hai cùng ngày (trần effort + STALL, `output_guard` giữa hai lõi, E-stop an toàn khi hở mạch, móc reset CPU):
**184 đạt, 0 lỗi** (giao thức 52, bản tham chiếu firmware 73, VehicleIO 48, kiểm tĩnh C++ 11; ≈ 8,5 s); `vectors --check`
báo file cập nhật; 5 file test liên quan ở trên vẫn 77 đạt. Chín kịch bản vector cũ giữ nguyên TỪNG BƯỚC (kịch bản đặt
trần 1000 ‰; chỉ thêm ba khóa cấu hình), thêm kịch bản thứ 10 `effort_cap_and_stall`. Trên bản sao gói với mã CŨ, các
test mới hỏng (bản tham chiếu firmware 18 hỏng, VehicleIO không nạp được vì thiếu `SIM_FIRMWARE_DEFAULT`, kiểm tĩnh 11/11
hỏng). Đợt đột biến thứ ba, 22 đột biến trên bản sao (13 trên mã C++ — kéo điện trở E-stop về phía nhả, mặc định
active-low cũ, guard đọc `millis()` trước, guard so không dấu, bỏ đăng ký móc, bỏ cờ `--wrap`, móc ghi duty thay vì tách
LEDC, wrap không gọi móc, lõi C++ kẹp ±1000, bỏ `check_stall`, mặc định trần C++ lệch Python, thiếu `Stall` trong
`protocol.h`, `test_main.cpp` thiếu khóa; 9 trên Python — kẹp ±1000 ở mạch hở/vòng kín, bỏ kiểm STALL, STALL không cần
liên tục, STALL bỏ qua dấu, `detail` 0, `reset_firmware` bỏ qua `hold`, cấu hình mô phỏng không lấy mặc định mô phỏng,
kiểm STALL cả khi mạch hở): cả 22 đều làm ít nhất một test hỏng. Đột biến C++ chỉ bị bắt bằng kiểm tĩnh mã nguồn.

Firmware C++ **chưa** qua `test/host` vì chưa biên dịch được.

*(Tối 24/09/2026, máy bàn, `.venv`.)* Chạy lại sau khi `VehicleIO` được nối vào phiên đỗ xe: bốn tệp `test_transport_*`
vẫn **184 đạt** (52 + 73 + 48 + 11); `tests/test_session_vehicle.py` 49 đạt + 1 `xfail` (khoảng trống an toàn ở mục 12).
Vẫn chỉ là bản tham chiếu Python, bo mô phỏng và cổng serial giả. *(Cập nhật cùng tối: thêm bản ép pha của test treo
0,25 s và hai test `test_resume_burst_*` (mục 12); `tests/test_session_vehicle.py` nay **57 đạt + 2 `xfail`** (cả hai `xfail` là pha 0 của khoảng trống ở mục 12).)*
*(Cập nhật muộn hơn tối 24/09/2026, sau bản sửa khoảng trống ở mục 12: `tests/test_session_vehicle.py` **60 đạt, 0
`xfail`**; hai `xfail` cũ nay đạt, hai test `test_resume_burst_*` được viết lại và đổi tên, thêm một test mới (mục 12).
Chạy lại riêng tệp này khi sửa tài liệu (máy bàn, `.venv`): 60 passed. Bốn tệp `test_transport_*` vẫn 184 test (đếm
bằng `--collect-only`; `take_new()` chưa có test riêng ở đây). Bộ test đầy đủ cuối tối 24/09/2026 (`.venv`): 895 đạt,
6 bỏ qua (mô-đun cần torch), 215 s.)*

## 12. Chưa làm / giới hạn

- C++ chưa biên dịch: lỗi cú pháp/kiểu có thể còn; hàm Arduino-ESP32 (`ledcAttach`/`ledcSetup`, `esp_task_wdt_*`,
  `Serial.setTxTimeoutMs`) viết cho cả 2.x và 3.x theo hiểu biết, chưa đối chiếu tài liệu của đúng phiên bản core
  (như `firmware/esp32_vehicle/README.md`), chưa thử trên phiên bản nào. Móc reset CPU
  (`esc_line_low_now`: thanh ghi `GPIO_OUT_W1TC_REG`/`GPIO_ENABLE_W1TS_REG`, `esp_rom_gpio_connect_out_signal`,
  `SIG_GPIO_OUT_IDX`; `__wrap_esp_panic_handler` + `-Wl,--wrap` cho 2.x; `set_arduino_panic_handler` cho 3.x;
  `esp_register_shutdown_handler`) viết theo hiểu biết về ESP-IDF/Arduino-ESP32, không đối chiếu được tài liệu trên máy
  này; tên hàm/thanh ghi/tiêu đề phải kiểm khi biên dịch, và tác dụng phải đo bằng máy hiện sóng
  ([firmware/esp32_vehicle/README.md](../firmware/esp32_vehicle/README.md), đoạn "Cách kiểm trên bo" trong mục An toàn).
- Chưa có mã đọc encoder, AS5600, BNO085, VL53L1X, điện áp; firmware báo mọi số đo là không hợp lệ.
- *(Cập nhật tối 24/09/2026; dòng cũ "chưa nối `VehicleIO` vào `session.py`, chưa ghi `commands.csv`/`telemetry.csv`"
  đã lỗi thời.)* `VehicleIO` đã được nối vào phiên đỗ xe: `application/vehicle_link.py` + `session.py`, ba nhánh SIM
  (mặc định, giai đoạn 0 không đổi) / `VEHICLE_IO` / `OBSERVE` (quan sát, không gửi COMMAND nào); `VehicleLink.write_logs`
  ghi `commands.csv`, `telemetry.csv`, `events.csv`, `start_refusals.csv`, `link.json`. Mới chạy với **bo mô phỏng**
  (`SimVehicleIO` + `FirmwareModel`) và cổng serial GIẢ; chưa với ESP32-S3 thật, chưa có nguồn tư thế thật (tư thế lấy
  từ mô phỏng). Chi tiết và giới hạn: [CHE_DO_QUAN_SAT.md](CHE_DO_QUAN_SAT.md). Thời hạn lệnh của phiên lấy
  `LinkParams.command_validity_s` (mặc định `None` = 0,15 s của `VehicleIO`); `DriveCommand.valid_for` vẫn chưa được
  dùng (mục 5).
- *(Thêm tối 24/09/2026, khoảng trống an toàn, chỉ trên mô phỏng. Cập nhật muộn hơn cùng tối: **ĐÃ SỬA** phía laptop,
  xem đoạn "Bản sửa" cuối gạch đầu dòng này; phần mô tả dưới đây giữ nguyên làm lịch sử, các câu về `xfail`,
  `test_resume_burst_*` và "CHƯA LÀM" là trạng thái lúc tìm thấy.)* Vòng điều khiển treo lâu hơn thời hạn lệnh trong khi
  một luồng khác vẫn đọc telemetry (như `Heartbeat`, có PING nên bo không DISARM): bo về ARMED (`COMMAND_TIMEOUT`),
  telemetry vẫn mới, chốt `TELEMETRY_STALE` không bật. Nếu bước 5 ms đầu tiên sau khi hết treo rơi vào nhịp điều khiển,
  phiên gửi **một** COMMAND enable=1 trước khi lấy sự kiện `VEHICLE_STOPPED` (lớp nối chỉ gom sự kiện của `VehicleIO`
  trong `pump()`, chạy sau nhịp điều khiển), nên bo ARMED → RUNNING thêm một lần; ngay sau đó (2 bước 5 ms của phiên
  trong các test dưới) phiên mới lấy sự kiện, dừng và gửi enable=0. Test: `test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes[0]` là `xfail(strict=True)`
  (pha 1–3 đạt). *(Làm rõ tối 24/09/2026; câu cũ "trên cả bo mô phỏng lẫn cổng serial giả, lệnh enable=0 tới bo cùng
  mili giây với lệnh enable=1 nên effort vẫn 0" không nêu nguồn và dễ hiểu nhầm.)* Hai lệnh tới bo cùng mili giây, effort
  vẫn 0, trên bo mô phỏng (`test_resume_burst_commands_share_sim_clock_ms`) và trên cổng serial giả có vòng đọc lúc treo
  (`ManualClock`; `test_resume_burst_effort_grows_with_gap_between_commands`, gap 0). Kết quả 0 này do đồng hồ mô
  phỏng, KHÔNG phải tính chất của thiết kế: sau khi treo, đồng hồ của `SimVehicleIO` đi trước thời gian phiên ≈ 1 s nên
  các bước 5 ms đuổi kịp của phiên không tiến bo (hai lệnh cách nhau 2 bước của phiên nhưng cùng một mốc io);
  `ManualClock` cũng không tiến trong một lần `Session.advance()`. Vì vậy giữa hai lệnh không có chu kỳ bo nào. Cho bo
  chạy thêm 10/20/40 ms trước lệnh enable=0 thì effort lớn nhất là 107/115/130 ‰ (cùng test; mô hình bo hiện tại, đầu
  vào đứng yên, không phải số đo). Trên bo thật, hai lệnh cách nhau bằng thời gian tính của đợt đuổi kịp cộng trễ
  USB/serial, còn chu kỳ bo là 10 ms (`kTickMs`), nên có thể có chu kỳ RUNNING với effort khác 0. Khoảng cách giữa hai
  lệnh và effort trên bo thật: CHƯA ĐO. Hai test `test_resume_burst_*` ghi lại hành vi HIỆN TẠI (có enable=1 lọt tới
  bo); sửa xong khoảng trống thì phải thay chúng.
  *(Cập nhật tối 24/09/2026.)* Test cũ `test_vehicle_io_command_timeout_after_freeze_never_resumes` (treo 0,25 s bằng
  `SimVehicleIO.advance`, tức laptop vẫn đọc telemetry trong lúc treo; không cần PING vì 0,25 s < watchdog 0,5 s) là
  cùng trường hợp này. Nó đạt chỉ vì lúc treo tình cờ rơi vào pha 3. Ép pha 0 (cùng kịch bản test): hết treo lúc
  1440 ms, bo nhận enable=1 150 mm/s ở 1450 ms (mô phỏng). Bản ép pha:
  `test_vehicle_io_command_timeout_after_freeze_by_phase` (pha 0 là `xfail(strict=True)`, pha 1–3 đạt).
  Khi KHÔNG có luồng nào đọc cổng lúc treo (phiên hiện không dùng `Heartbeat`), 8 trường hợp (treo 0,3 s và 1 s × 4 pha,
  cổng serial giả) đều dừng và không có lệnh enable nào (`test_realtime_hang_without_heartbeat_never_resumes`). Cách
  sửa (ví dụ gom sự kiện `VehicleIO` trước nhịp điều khiển, hoặc từ chối gửi khi telemetry cho thấy bo đã rời RUNNING
  sau lệnh của lần chạy này) thuộc `vehicle_link.py`/`session.py`, CHƯA LÀM.

  **Bản sửa (muộn hơn tối 24/09/2026, máy bàn; chỉ bo mô phỏng và cổng serial GIẢ, CHƯA THỬ với ESP32-S3 thật).** Hai
  lớp, trong `application/vehicle_link.py`, `application/session.py`, `transport/vehicle_io.py`:
  1. `VehicleLink.refresh()`, được `Session._step_closed_loop` gọi ở đầu MỌI bước 5 ms khi phiên đang RUNNING, TRƯỚC nhịp
     điều khiển: bo thật → `poll(block=False)` (chỉ byte đã có sẵn); bo mô phỏng → `VehicleIO.take_new()` (hàng đợi hiện
     có, không tiến I/O hay đồng hồ mô phỏng, mục 10); rồi gom sự kiện của `VehicleIO`. Nhờ vậy `VEHICLE_STOPPED`
     (`COMMAND_TIMEOUT`) mà telemetry đã mang tới được `Session` lấy và chuyển sang dừng trước khi tới nhịp điều khiển.
  2. `VehicleLink.command()` không gửi gì và trả `HALTED` nếu còn sự kiện dừng nằm trong hàng chờ của lớp nối mà
     `Session` chưa lấy (ngoài chốt `_halted` đã có).

  Test (`tests/test_session_vehicle.py`, nay 60 test, 60 đạt, 0 `xfail`): hai `xfail(strict=True)` cũ ở pha 0 của
  `test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes` và
  `test_vehicle_io_command_timeout_after_freeze_by_phase` nay đạt; hai test ghi hành vi lỗi được viết lại và đổi tên:
  `test_resume_after_hang_sends_no_enable_to_the_sim_board` (bo mô phỏng, pha 0, treo 1 s: lệnh đầu tiên tới bo sau
  khi hết treo là enable=0, không có enable=1, effort luôn 0) và
  `test_resume_after_hang_keeps_effort_zero_whatever_the_gap_before_the_stop[0/10/20/40]` (cổng serial giả, `ManualClock`:
  không enable=1 nào, effort 0 ở mọi khoảng bo chạy thêm trước lệnh dừng; trước bản sửa là 0/107/115/130 ‰); thêm
  `test_command_refuses_enable_while_a_stop_event_is_pending` (lớp 2). Đột biến trong tiến trình (vá bằng plugin
  pytest ngoài repo, không sửa tệp nào; chạy lại khi viết tài liệu này): bỏ lời gọi `refresh()` → 7 test hỏng (hai pha 0
  ở trên, `test_resume_after_hang_sends_no_enable_to_the_sim_board`, bốn trường hợp `..._whatever_the_gap_...`), dù lớp
  2 vẫn còn; bỏ lớp 2 → đúng test mới hỏng, 59 test còn lại đạt. Tức là lớp 2 chỉ chặn sự kiện ĐÃ được lớp nối gom, còn
  việc bắt được khoảng trống này là nhờ lớp 1.

  Giới hạn còn lại (suy ra từ mã, chưa có test): `refresh()` chỉ thấy những gì đã tới laptop. Nếu bo vừa về ARMED mà khung
  telemetry báo điều đó chưa tới (bo gửi mỗi 50 ms, cộng trễ USB) thì laptop không biết và vẫn có thể gửi enable=1 (bo
  ARMED → RUNNING theo mục 6); `VEHICLE_STOPPED` chỉ sinh ra khi laptop nhận một khung rời RUNNING. Trên bo thật, khoảng
  hở này và effort khi đó: CHƯA ĐO.
- *(Thêm tối 24/09/2026.)* Lần chạy qua `VehicleIO` không có gói replay: `storage/run_store.export_run` và `replay_run`
  từ chối (`ReplayNotSupported`, lời báo tiếng Việt) vì trạng thái lấy từ telemetry + nguồn tư thế, không tái tạo được
  bằng mô phỏng; bằng chứng của lần chạy là log `VehicleLink.write_logs` (test `tests/test_run_store_vehicle.py`).
- *(24/09/2026)* Chưa có mã đổi `VehicleTelemetry.tof_m` sang `NearFieldReading` của `NearFieldLayer`
  ([giai đoạn 3](GIAI_DOAN_3_CHUAN_BI.md)). Trên dây ToF chỉ là `tof_mm[4]` + mặt nạ theo chỉ số, không có `sensor_id`
  hay `max_range_m`; cả bốn số đo dùng chung stamp của khung (thời điểm laptop nhận). Ánh xạ chỉ số →
  `sensor_id`/`max_range_m`/vị trí gắn phải lấy từ cấu hình, hiện chưa có file cấu hình nào ghi; `NearFieldLayer` vẫn
  chỉ chạy với số đo giả.
- Mô hình cơ cấu chấp hành đơn giản: vùng chết đối xứng, tốc độ xác lập tuyến tính theo effort, không có ma sát tĩnh
  khác động, không có phanh ESC, không có độ rơ lái; mọi hệ số là giả định.
- Chưa có xác thực nguồn gửi (một tiến trình khác mở được cổng có thể gửi HELLO); chấp nhận ở mức bàn thử một laptop.
- Việc cuối trong kế hoạch mục 9, "Khi chưa đủ phần cứng" (thiết kế nguồn/dừng cho phép thử sắp thực hiện): *(cập nhật
  tối 24/09/2026; dòng cũ "repo chưa có bảng tải, `power_budget.md`, sơ đồ nguồn hay sơ đồ dừng" đã lỗi thời)* đã có
  **bản nháp** [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md): bảng tải (mục 1, gần như toàn CHƯA ĐO / CẦN TRA
  datasheet), sơ đồ nguồn (mục 2), sơ đồ dừng (mục 3), bảng định mức còn phải kiểm (mục 4), kịch bản thử lỗi (mục 5, đều
  CHƯA THỬ). Chưa có phần cứng nguồn hay dừng nào, chưa đo điện áp/dòng thiết bị nào; tách `power_budget.md` riêng hay
  không: CHƯA CHỐT. Mới chọn cách đấu ngõ vào E-stop an toàn khi hở mạch (tiếp điểm NC nối GND, kéo lên; mục 0, mục 6),
  chưa lắp, chưa thử; ngõ vào này không thay đường cắt động lực phần cứng.
