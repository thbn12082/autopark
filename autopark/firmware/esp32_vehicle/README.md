# Firmware ESP32-S3 — nhận lệnh, giới hạn, watchdog, telemetry (giai đoạn 5, "khi chưa đủ phần cứng")

**Trạng thái (30/09/2026):** lõi `src/core` khớp bản tham chiếu Python trên máy tính (test host 703 check, 0 lệch,
29/09/2026); cả firmware biên dịch cho ESP32-S3 (Arduino-ESP32 2.0.17, 0 lỗi, 0 cảnh báo, 29/09/2026); bản env
`esp32s3_qemu` chạy trong bo ảo QEMU (30/09/2026, chỉ là giả lập). **CHƯA NẠP, CHƯA CHẠY trên bo thật**; mọi bước
"Cách kiểm trên bo" chưa làm. Chi tiết ở ba đoạn "Cập nhật" dưới và các mục tương ứng.

*Trạng thái lúc viết mã (24/09/2026), giữ làm lịch sử:* mã nguồn viết trước khi có mạch. CHƯA BIÊN DỊCH, CHƯA NẠP, CHƯA
CHẠY trên bo nào. Máy bàn dùng tới 25/09/2026 không có trình biên dịch C/C++ (không gcc/clang/MSVC) và không có
PlatformIO, nên kể cả bộ test C++ trên máy tính (`test/host`) cũng chưa từng được biên dịch.
Phần đã kiểm là **bản tham chiếu Python**
(`autopark/transport/firmware_model.py`) — mã C++ này được viết để khớp từng dòng với nó, và bộ test C++ sẽ
kiểm điều đó bằng vector mẫu chung khi có trình biên dịch.

**Cập nhật 29/09/2026 (máy bàn mới, g++ 16.1.0 MinGW-w64 UCRT, cmake 4.4.1, Ninja): lõi `src/core` đã biên dịch và
khớp bản tham chiếu Python trên máy tính** — `test/host` in `703 checks, 0 failures` (CRC, COBS, 13 thông điệp, 11 luồng
byte, 10 kịch bản máy trạng thái so từng byte gửi đi), lần biên dịch đầu không sửa dòng nào của `src/core`. Chi tiết và
giới hạn: mục "Cách kiểm trên máy tính" bên dưới.

**Cập nhật chiều 29/09/2026: cả firmware (`src/main.cpp` + `src/core`) đã BIÊN DỊCH cho ESP32-S3 bằng PlatformIO,
0 lỗi, 0 cảnh báo, không sửa dòng mã nào** — Arduino-ESP32 2.0.17 theo `platformio.ini` (nay khóa `espressif32 @ 7.1.3`),
và thêm Arduino-ESP32 3.3.12 trên bản sao tạm; mỗi bản cả `AP_ENABLE_PWM_OUTPUTS=0` lẫn `=1` với chân giả. Vẫn **CHƯA
NẠP, CHƯA CHẠY trên bo nào**. Biên dịch và objdump chỉ chứng minh tên/chữ ký API (móc panic, `esp_rom_gpio_connect_out_signal`,
`SIG_GPIO_OUT_IDX`, thanh ghi `GPIO_OUT_W1TC`/`W1TS`, `esp_register_shutdown_handler`, LEDC, task watchdog) đúng với hai
core đó và mã máy làm đúng thứ tự viết; không chứng minh hành vi trên chân thật (thời gian, độ rộng xung, ESC phản ứng
ra sao). Một lỗi thật tìm ra lúc biên dịch: với 3.x qua PlatformIO **phải giữ** cờ `-Wl,--wrap=esp_panic_handler`
(chú thích cũ bảo xóa), nếu không móc panic không bao giờ chạy. Chi tiết: mục "Biên dịch cho ESP32-S3" bên dưới.
Bước tiếp theo vẫn là đo bằng máy hiện sóng theo đoạn "Cách kiểm trên bo" trong mục An toàn trước khi nối ESC.

**Cập nhật 30/09/2026: firmware chạy được trong bo ảo QEMU** (env `esp32s3_qemu`, Serial qua UART0), laptop nói chuyện
bằng đúng `SerialVehicleIO`; xem mục "Chạy trong bo ảo (QEMU)". Vẫn CHƯA chạy trên bo thật.

Đặc tả giao thức và máy trạng thái: [`docs/GIAO_THUC_XE.md`](../../docs/GIAO_THUC_XE.md).

## Cấu trúc

| Đường dẫn | Nội dung | Phụ thuộc |
|---|---|---|
| `src/core/crc16.*`, `cobs.*` | CRC-16/CCITT-FALSE, COBS | C++17 thuần |
| `src/core/protocol.*` | cấu trúc thông điệp, mã hóa/giải mã, `FrameParser` chịu rác/khung cụt/quá dài | C++17 thuần |
| `src/core/vehicle_core.*` | máy trạng thái, phiên/số thứ tự, watchdog liên lạc, hết hạn lệnh, giới hạn + dốc, khóa đổi chiều, vòng tốc độ PI số nguyên có trần effort, kiểm STALL, chốt lỗi, telemetry | C++17 thuần |
| `src/main.cpp` | lớp dán Arduino: USB CDC, chu kỳ 10 ms, xung 50 Hz cho ESC/servo (TẮT mặc định), đọc E-stop (an toàn khi hở mạch), task watchdog, bộ hẹn giờ ép trung tính, móc panic/`esp_restart()` kéo chân ESC xuống thấp | Arduino-ESP32 2.x hoặc 3.x |
| `test/vectors.json` | vector mẫu chung, **sinh từ Python** — không sửa tay | — |
| `test/host/test_main.cpp` | test C++ trên máy tính đọc `vectors.json` (kèm bộ đọc JSON tối giản) | C++17 + STL |
| `qemu/tao_anh_flash.py` | (30/09/2026) post-script của env `esp32s3_qemu`: ghép ảnh flash 8 MB cho bo ảo QEMU | PlatformIO (SCons) |

`src/core` không include header Arduino nào, không cấp phát động, không dùng ngoại lệ, không dùng số thực: mọi
phép tính là số nguyên (µm/s, µrad, ms uint32 có quay vòng) để C++ và Python ra cùng byte.

Hai điểm phải giữ khớp tay giữa hai bên (có test Python kiểm):
- Bộ đệm gửi tĩnh `VehicleCore::kTxBufferSize` = 1024 byte = `firmware_model.TX_BUFFER_SIZE`; `tx_capacity` chỉ nhận
  1…1024 (Python từ chối giá trị lớn hơn). Test đọc hằng số trong `vehicle_core.h`; vector `tx_overflow_gap` và trường
  `tx_overflow` của mọi bước kịch bản kiểm hai bên bỏ đúng cùng khung khi đầy.
- Lịch telemetry theo hạn trước (`last_telemetry_ms_ += period`, bắt nhịp lại khi tụt quá một chu kỳ): chu kỳ trung
  bình bằng giá trị trong HELLO_ACK kể cả khi không là bội của 10 ms (vector `telemetry_period_not_multiple_of_tick`).

Ngoài ra `tests/test_transport_firmware_source.py` đọc mã C++ và kiểm tĩnh: giá trị mặc định của `ap::Config` bằng
`FirmwareConfig()`, `test_main.cpp` đọc được mọi khóa cấu hình, các enum trong `protocol.h` bằng enum Python (kể cả
`Fault::Stall = 5`), và vài mẫu an toàn trong `main.cpp` (mục an toàn bên dưới). Kiểm tĩnh không thay được biên dịch.

## CHƯA CHỐT theo bo thực (không được tự điền là đã chốt)

Hằng số phần cứng nằm ở đầu `src/main.cpp`; tham số lõi (trần effort, STALL, hệ số vòng tốc độ) ở `ap::Config`
(`src/core/vehicle_core.h`, mặc định = `FirmwareConfig()` Python):

- Loại bo ESP32-S3 (`board` trong `platformio.ini`) và cổng USB nào là `Serial` (bo DevKitC có hai cổng). Phiên bản
  Arduino-ESP32: `platform = espressif32 @ 7.1.3` (2.0.17); chuyển sang 3.x (pioarduino) thì **GIỮ** cờ
  `-Wl,--wrap=esp_panic_handler` trong `platformio.ini` (sửa 29/09/2026, trước đó ghi nhầm là xóa; mục "Biên dịch cho ESP32-S3").
- Chân ESC, servo, E-stop (`kPinEsc`, `kPinServo`, `kPinEstop` = -1). **Kiểu đấu E-stop đã chọn, chưa lắp: an toàn khi
  hở mạch** — tiếp điểm NC (loại mở cưỡng bức) nối giữa chân và GND, điện trở kéo lên (`kEstopActiveLow = false`,
  `INPUT_PULLUP`; nên thêm 4,7–10 kΩ ngoài lên 3V3 tại bo vì kéo trong chỉ ≈ 45 kΩ). Hở mạch (đứt dây, tuột đầu nối) =
  đang nhấn → FAULT; cắm nhầm tiếp điểm NO thì xe luôn ở FAULT. Điện trở kéo luôn đặt về phía mức tích cực, nên không
  cấu hình nào đọc "đứt dây" thành "nhả nút".
- Điện trở kéo xuống (ví dụ ≈ 10 kΩ) trên dây tín hiệu ESC: phủ lúc bật nguồn/system reset/sụt áp, khi chân thả nổi
  trước `setup_outputs()`. Không phủ reset CPU (móc panic lo phần đó, mục dưới).
- Trần effort `max_effort_permille` = 250 ‰ (với `kEscSpanUs` = 500 là 1500 ± 125 µs), ngưỡng STALL
  `stall_effort_permille` = 200 ‰, `stall_timeout_ms` = 1000 ms: số thận trọng cho lần thử đầu, chưa đo trên xe. STALL
  chỉ kiểm được khi có encoder; hiện chưa có mã đọc encoder nên chỉ còn trần effort bảo vệ.
- ESC: xung trung tính, biên độ, chiều, có cần "trung tính khi bật nguồn" bao lâu (`boot_hold_ms`), hành vi phanh
  và lùi (nhiều ESC RC cần phanh → trung tính → lùi; không mặc định ga âm là lùi ngay — lõi đã có
  `direction_change_hold_ms`, nhưng thời lượng đúng phải đo).
- Servo: xung giữa, µs/rad, chiều, giới hạn cơ khí (từ `steering_calibration.yaml` ở giai đoạn 5).
- Cảm biến: encoder/MT6701, AS5600, BNO085, VL53L1X, đo điện áp — **chưa có mã đọc**; `read_inputs()` trả
  `*_valid = false`, telemetry báo "không có số đo" (giá trị 0 kèm cờ hợp lệ 0, không bao giờ là "khoảng cách xa").
- Hệ số vòng tốc độ (`kp/ki/ff/deadzone_comp`): chọn trên mô hình mô phỏng giả định, chưa chỉnh trên xe.

`AP_ENABLE_PWM_OUTPUTS=0` (mặc định): không chân nào bị điều khiển. Bật lên 1 khi các chân còn là -1 thì
`static_assert` chặn biên dịch.

## An toàn: điều firmware này làm và KHÔNG làm

Làm ở mức logic lõi (`vehicle_core`; đã thử trên bản tham chiếu Python `firmware_model.py`; lõi C++ khớp
nó trên máy tính qua `test/host` từ 29/09/2026; chưa thử trên bo):
- Khởi động luôn ở BOOT → DISARMED, `effort_permille = 0` (test `test_boot_is_neutral_silent_without_session_then_disarmed`);
  không bao giờ tự vào RUNNING. Xung trên chân ESC: xem mục "Chỉ có trong `src/main.cpp`" bên dưới.
- Chỉ chạy khi: có phiên (HELLO) → ARM → COMMAND có `enable=1` gửi SAU ARM, còn hạn, đúng phiên, số thứ tự mới.
- Lệnh hết hạn → dốc về trung tính (ARMED); không nhận thông điệp hợp lệ nào quá `link_timeout_ms` (500 ms) → DISARMED.
- Reset, kết nối lại (HELLO mới), mất liên lạc dài hơn `link_timeout_ms`: đều kết thúc ở DISARMED — **reconnect không
  tự chạy tiếp**. DISARM và HELLO trong BOOT/FAULT không đổi trạng thái (không rút ngắn BOOT, không xóa lỗi).
- Hai cơ chế mất liên lạc KHÁC nhau: watchdog của bo (500 ms không nhận thông điệp hợp lệ → DISARMED) và
  `TELEMETRY_STALE` của laptop (0,3 s không có telemetry, phải ≥ 3 chu kỳ telemetry). Mất liên lạc ngắn hơn 500 ms,
  hoặc chỉ mất chiều bo → laptop trong khi laptop vẫn PING, có thể để bo ở ARMED; điều ngăn xe tự chạy lại khi đó là
  chốt phía laptop: `VehicleIO` gửi DISARM, từ chối mọi `send(enable=True)` và chỉ gỡ chốt bằng `arm()` hoặc `connect()` (xem
  `docs/GIAO_THUC_XE.md` mục 5). Firmware không tự biết laptop đã coi là mất liên lạc.
- E-stop (ngõ vào) → FAULT ngay, effort 0 ngay, chốt tới khi nhả nút VÀ laptop gửi CLEAR_FAULT; sau đó vẫn phải ARM
  (mức logic: `inputs.estop` → FAULT, vector `estop_latch`; đọc chân E-stop ở `main.cpp`, `kPinEstop` còn -1, chưa thử).
- `|effort| ≤ max_effort_permille` ở cả mạch hở lẫn vòng kín. `max_speed_mm_s` chỉ kẹp MỤC TIÊU, không giới hạn tốc độ
  thật: chạy mạch hở (chưa có encoder) với hệ số giả định, 300 mm/s đòi 700 ‰ (≈ 70 % ga) — trần mặc định 250 ‰ chặn
  việc đó. Vòng kín mà `|effort| ≥ stall_effort_permille` và số đo không đi theo chiều mục tiêu (encoder kẹt 0 với cờ hợp
  lệ, encoder đảo dấu, bánh kẹt) liên tục `stall_timeout_ms` → FAULT `STALL` (mã 5), effort 0 ngay (vector
  `effort_cap_and_stall`, các test `test_effort_never_exceeds_cap_*`, `test_stall_*`).

Chỉ có trong `src/main.cpp`, KHÔNG có bản tương ứng trong `firmware_model.py`: **đã biên dịch (29/09/2026), CHƯA THỬ trên
bo** (bo ảo QEMU từ 30/09/2026 chỉ cho đọc lại cấu hình TWDT; nó không có LEDC, GPIO vào, watchdog không kích hoạt;
bản Python không có các cơ chế này). `tests/test_transport_firmware_source.py` chỉ kiểm tĩnh mã nguồn (đúng mẫu, đúng thứ tự lời
gọi), không chạy mã nào; biên dịch kèm objdump chỉ kiểm mã máy (mục "Biên dịch cho ESP32-S3"):
- Xung trung tính trên chân khi khởi động: `setup_outputs()` ghi 1500 µs cho ESC và xung giữa cho servo, chỉ khi
  `AP_ENABLE_PWM_OUTPUTS=1`. Trước khi `setup()` chạy, chân chưa có xung nào (sau bật nguồn: thả nổi nếu không có điện
  trở kéo xuống ngoài). ESC xử lý khoảng không có xung này ra sao: CHƯA CHỐT.
- Loop im > 100 ms (`kOutputGuardMs`): tác vụ `esp_timer` `output_guard` ép xung ESC về trung tính, không đụng servo.
  Guard đọc mốc thời gian của loop TRƯỚC `millis()` và so hiệu có dấu (loop chạy ở lõi khác; phép trừ không dấu cũ có
  thể ép trung tính nhầm giữa lúc chạy). Bản Python KHÔNG có cơ chế này: trong lúc treo, mô hình giữ nguyên effort cuối
  và chỉ chốt `LOOP_OVERRUN` ở chu kỳ đầu tiên sau khi hết treo.
- Loop treo > 300 ms (`kTaskWatchdogMs`, Arduino 3.x): task watchdog gây panic và khởi động lại chip. Với 2.x (2.0.17):
  1 s. Arduino khởi tạo TWDT sẵn (5 s), nhưng `esp_task_wdt_init(1, true)` của IDF 4.4 gặp TWDT đã khởi tạo thì đổi thời
  hạn chứ không báo lỗi; thanh ghi đọc trong QEMU ngày 29/09/2026 là 1 s / 2 s. *(Sửa 30/09/2026: trước đó ghi nhầm
  "nếu TWDT đã khởi tạo sẵn thì giữ mặc định 5 s"; [MO_PHONG_FIRMWARE.md](../../docs/MO_PHONG_FIRMWARE.md) mục 5.)*
- Panic, interrupt watchdog, task watchdog, `esp_restart()`: trên ESP32-S3 với Arduino chỉ reset CPU; LEDC và ma trận
  GPIO KHÔNG bị reset, nên không làm gì thì xung ga cuối cùng tiếp tục qua in panic, ghi coredump, ROM, bootloader,
  initArduino cho tới `setup_outputs()`. `esc_line_low_now()` (IRAM, chỉ ghi thanh ghi và gọi hàm ROM) tách chân ESC
  khỏi LEDC và kéo xuống thấp (mất xung); gọi từ móc panic (`__wrap_esp_panic_handler` với 2.x;
  `set_arduino_panic_handler` với 3.x; CẢ HAI cần cờ `-Wl,--wrap=esp_panic_handler`) và từ `esp_register_shutdown_handler`
  (`esp_restart()`). Không ghi duty trung tính vì sau reset CPU chạy bằng XTAL, APB có thể về 40 MHz và độ rộng xung LEDC
  có thể nhân đôi (CẦN ĐO). Servo không bị kéo thấp (CHƯA CHỐT).
- Đọc chân E-stop: điện trở kéo về phía mức tích cực, hở mạch đọc là đang nhấn (mục CHƯA CHỐT ở trên).

Cách kiểm trên bo (chưa làm): bật `AP_ENABLE_PWM_OUTPUTS=1` với chân đã chốt, CHƯA nối ESC/servo, đo chân ESC bằng máy
hiện sóng hoặc logic analyzer:
1. Từ lúc cấp nguồn: thời điểm có xung 1500 µs đầu tiên, mức chân trong khoảng trước đó (có/không điện trở kéo xuống).
2. Build thử có cờ gọi `delay(150)` một lần trong `loop()` khi effort ≠ 0: kỳ vọng xung ESC về 1500 µs trong khoảng
   100–110 ms sau lần loop cuối; sau khi loop chạy lại, telemetry báo FAULT `LOOP_OVERRUN`. Chạy nhiều giờ ở RUNNING với
   loop khỏe: đếm số lần guard ghi trung tính, kỳ vọng 0.
3. Treo loop: guard ép trung tính sau ≈ 100 ms trong mọi trường hợp. Bản nạp vào xe (Arduino 2.0.17, TWDT 1 s):
   `delay(400)` KHÔNG làm chip reset (loop chạy lại, telemetry báo FAULT `LOOP_OVERRUN`); `while (1)` hoặc `delay(1500)`
   → task watchdog panic sau ≈ 1 s (tầng reset hệ thống 2 s). Với Arduino 3.x (300 ms), `delay(400)` đã đủ để reset.
   Lúc panic chân xuống thấp; HELLO_ACK lần kết nối sau có `reset_reason = Watchdog`, `boot_id` mới, BOOT → DISARMED.
   Ghi lại khoảng mất xung tới khi có lại 1500 µs. *(Sửa 30/09/2026: trước đó chỉ ghi kỳ vọng của 3.x.)*
4. `abort()` trong loop, khóa ngắt trên cả hai lõi (interrupt watchdog) và `esp_restart()`, mỗi lần ở effort cao nhất cho
   phép (trần mặc định 250 ‰ → 1625 µs): thời gian từ sự cố tới lúc chân xuống thấp hoặc về trung tính, và độ rộng xung
   trong pha chạy bằng XTAL nếu còn xung. So với một bản build thử bỏ lời gọi `esc_line_low_now()` trong móc (phải thấy
   xung cũ còn phát suốt lúc reset) để biết móc thật sự có tác dụng.
5. Rút đầu nối E-stop (khi đã chốt `kPinEstop`): telemetry cờ `ESTOP_INPUT = 1`, FAULT `ESTOP`; CLEAR_FAULT bị từ chối
   (`ESTOP_ACTIVE`) cho tới khi cắm lại.

Chưa đo xong các bước này thì không được ghi các cơ chế trên là "đã thử". Bảng thời hạn/watchdog và các cơ chế "chỉ trên
bo": [`docs/GIAO_THUC_XE.md`](../../docs/GIAO_THUC_XE.md) mục 5.

KHÔNG làm được / chưa chứng minh:
- Không thay E-stop phần cứng: nút dừng phải cắt động lực độc lập với phần mềm (kế hoạch mục 10).
- Chưa đo được gì về thời gian/quãng đường dừng thật; "effort = 0" không có nghĩa xe đứng yên ngay.
- Khi cả chip treo với ngắt bị tắt mà KHÔNG vào được panic, LEDC vẫn phát xung cuối cùng; ESC có coi xung đều là hợp lệ
  hay không phụ thuộc ESC (CHƯA CHỐT). Panic/IWDT/TWDT/`esp_restart()` chỉ reset CPU (ESP32-S3 + Arduino dùng
  `esp_restart_noos`): LEDC và ma trận GPIO không reset, clk init giữ xung nhịp LEDC; nếu móc panic không chạy thì xung
  cuối cùng tiếp tục qua in panic, ghi coredump vào flash, ROM, bootloader và initArduino. Chỉ bật nguồn/system reset mới
  làm chân thả nổi. Sụt áp (brownout): không chắc đi qua móc panic, hành vi chân CẦN ĐO. Độ rộng xung ở pha XTAL: CẦN ĐO.
- Hành vi ESC khi mất xung (chân bị kéo thấp lúc chip reset, hoặc thả nổi lúc bật nguồn) chưa biết.
- E-stop: một tiếp điểm chỉ phát hiện đứt dây tín hiệu, không phát hiện mất động lực ESC. *(Sửa tối 24/09/2026.)* Đọc
  thêm tiếp điểm thứ hai của nút chỉ cho biết thêm về chính cái nút (so hai tiếp điểm thì thấy được một tiếp điểm hỏng);
  nó KHÔNG thấy cầu chì đứt, đầu nối động lực lỏng, pin cạn hay phần tử ngắt không đóng lại, vì các lỗi đó nằm phía
  động lực, sau nút. Cách phát hiện mất động lực đúng nghĩa là đo điện áp phía động lực (sau cầu chì và phần tử ngắt, gần
  đầu vào ESC) qua bộ chia áp vào ADC của bo. Chưa làm: điểm đo, bộ chia áp và ngưỡng CHƯA CHỐT, chưa có mã đọc điện áp.

## Cách kiểm trên máy tính

```bash
# 1) Sinh lại / kiểm vector từ bản tham chiếu Python (trong thư mục autopark của repo, thư mục có pyproject.toml)
python -X utf8 -m autopark.transport.vectors --check

# 2) Test lõi C++ trên máy tính (trong firmware/esp32_vehicle)
cmake -S test/host -B build/host -DCMAKE_BUILD_TYPE=Release
cmake --build build/host --config Release        # --config/-C: cho Visual Studio (nhiều cấu hình); Ninja bỏ qua
ctest --test-dir build/host -C Release --output-on-failure   # hoặc: ./build/host/host_tests test/vectors.json
# (Visual Studio để exe ở build/host/Release/host_tests.exe; ctest --test-dir cần CMake ≥ 3.20)
# không có cmake: g++ -std=c++17 -O1 -Wall -Wextra -Isrc/core src/core/*.cpp test/host/test_main.cpp -static -o build/host_tests
# host_tests in "N checks, K failures"; mã thoát 0 = đạt, 1 = có check lệch, 2 = không mở được tệp vector

# 3) Biên dịch cho ESP32-S3 (chưa nạp): mục "Biên dịch cho ESP32-S3" bên dưới
pio run -e esp32s3
```

Bước 1 và 2 cũng nằm trong bộ test Python: `tests/test_transport_firmware_host.py` build `test/host` bằng cmake vào
thư mục tạm, chạy trên `vectors.json`, và kiểm thêm rằng một vector sai một bit làm exe thoát 1. Máy không có cmake hoặc
trình biên dịch C++ trên PATH thì hai test đó bỏ qua.

Nếu bước 2 báo lệch: bản tham chiếu Python là chuẩn (nó được test trong `tests/test_transport_*.py`); sửa C++ cho
khớp. Chỉ khi quyết định đổi hành vi mới sửa Python, chạy lại `--write` và cập nhật docs.

**Lần chạy đầu, 29/09/2026** (máy bàn mới; g++ 16.1.0 MinGW-w64 x86_64 UCRT của WinLibs, cmake 4.4.1, Ninja; vector
`--check` khớp bản Python): `703 checks, 0 failures`, mã thoát 0, ở cả Debug, Release (`-O3`), `-O1`, `-O2`; thêm
`-Wpedantic -Wshadow -Wconversion -Wsign-conversion -Wold-style-cast -Wcast-align -Wnull-dereference` không ra cảnh báo
nào ở `src/core` (cảnh báo duy nhất, một overload `to_hex` không dùng trong `test_main.cpp`, đã xóa); `-fsanitize=undefined
-fsanitize-trap=all -D_GLIBCXX_ASSERTIONS` và `-O0 -ftrapv` cũng đạt. Đột biến bảy vector (CRC, COBS, khung thông điệp,
đếm lỗi CRC của luồng, trạng thái / effort / byte gửi của kịch bản): cả bảy làm exe báo lệch và thoát 1. Bằng chứng:
[firmware_host_20260929.txt](../../docs/evidence/chuyen_may_20260929/firmware_host_20260929.txt).

Giới hạn của lần chạy này:
- Chỉ `src/core` trên x86-64 Windows (int 32 bit, little-endian như ESP32-S3; con trỏ 64 bit, ESP32-S3 32 bit). Chưa
  chạy trên bo. (Biên dịch bằng toolchain Xtensa: mục dưới; biên dịch không chạy test vector.)
- Không có AddressSanitizer (MinGW không có runtime ASan/UBSan; UBSan chạy chế độ trap, không in chỗ lỗi).
- **Chạy exe trong Git Bash có thể segfault ngay ở `std::ifstream`** nếu exe liên kết động: Git Bash đặt
  `C:\Program Files\Git\mingw64\bin` (có `libstdc++-6.dll` cũ hơn) trước WinLibs trên PATH. Đo 29/09/2026: bản `-O1`/`-O2`
  liên kết động segfault trong Git Bash, cùng exe đó chạy trong PowerShell ra 703/0. Vì vậy `CMakeLists.txt` liên kết
  tĩnh (`-static`) khi dùng MinGW, và lệnh g++ tay ở trên có `-static`.

## Biên dịch cho ESP32-S3

Máy bàn (từ 29/09/2026): PlatformIO Core 6.2.0 cài trong venv riêng `D:\xetulai\_platformio\penv` (ngoài repo);
toolchain và framework ở `D:\xetulai\_platformio\core` (≈ 3 GB), qua biến môi trường người dùng
`PLATFORMIO_CORE_DIR` (đã đặt cố định; ổ C gần đầy). Trong `firmware/esp32_vehicle`:

```bat
D:\xetulai\_platformio\penv\Scripts\python.exe -m platformio run -e esp32s3
```

Máy khác: `pip install platformio` (hoặc extension PlatformIO của VS Code) rồi `pio run -e esp32s3`; lần đầu tải
nền tảng `espressif32 @ 7.1.3` (≈ 2,5 GB). Chưa có lệnh nạp (`-t upload`) nào được chạy: chưa có bo.

**Kết quả 29/09/2026** (bằng chứng: [firmware_esp32_20260929.txt](../../docs/evidence/chuyen_may_20260929/firmware_esp32_20260929.txt)):

| Bản build | Core | Kết quả |
|---|---|---|
| `platformio.ini` của repo (PWM tắt) | espressif32 7.1.3 = Arduino-ESP32 2.0.17, GCC Xtensa 8.4.0 | SUCCESS, 0 cảnh báo, RAM 20 192 B (6,2 %), flash 271 469 B (8,1 %); build sạch hai lần ra cùng kích thước |
| bản sao tạm, PWM bật, chân giả ESC 4 / servo 5 / E-stop 6 | như trên | SUCCESS, 0 cảnh báo |
| bản sao tạm, PWM tắt và bật | pioarduino 55.3.312 = Arduino-ESP32 3.3.12, ESP-IDF 5.5.5, GCC 14.2.0 | SUCCESS, 0 cảnh báo (nhánh `AP_ARDUINO_V3` có vào bản build) |

Mã dự án biên dịch với `-std=gnu++17 -Wall -Wextra -Os`; framework tự thêm `-Wno-sign-compare -Wno-unused-parameter`,
nên "0 cảnh báo" không gồm hai loại đó. Kiểm mã máy bằng objdump:
- 2.0.17: `panic_handler` của ESP-IDF gọi `__wrap_esp_panic_handler` (IRAM) của `main.cpp`, hàm này gọi
  `esc_line_low_now()` rồi `esp_panic_handler` thật. Với PWM tắt, `esc_line_low_now()` rỗng.
- `esc_line_low_now()` (bản chân giả, cả hai core): nằm ở IRAM; ghi bit chân vào `GPIO_OUT_W1TC` (0x6000400C) trước, rồi
  `GPIO_ENABLE_W1TS` (0x60004024), rồi gọi `esp_rom_gpio_connect_out_signal` trong ROM (0x40001AA0) với `SIG_GPIO_OUT_IDX`
  = 0x100; không gọi hàm nào trong flash.
- **3.3.12 (lỗi tìm ra):** lõi 3.x tự định nghĩa `__wrap_esp_panic_handler` (gọi hàm đăng ký bằng
  `set_arduino_panic_handler`), nhưng chỉ Arduino IDE thêm cờ `-Wl,--wrap=esp_panic_handler`; PlatformIO/pioarduino thì
  không. Làm theo chú thích cũ (3.x thì xóa cờ) thì ELF không có `__wrap`, `panic_handler` gọi thẳng `esp_panic_handler`,
  và `ap_on_panic` không bao giờ chạy. Giữ cờ thì chuỗi gọi đủ: `panic_handler` → `__wrap_esp_panic_handler` →
  `handle_custom_backtrace` → `ap_on_panic` → `esc_line_low_now`. Đã sửa chú thích trong `main.cpp` và `platformio.ini`;
  test kiểm tĩnh vốn đã đòi cờ này có mặt. Trên 3.x móc chạy SAU khi lõi dựng backtrace (từ flash), còn 2.x chạy móc
  đầu tiên từ IRAM: độ trễ tới lúc chân ESC xuống thấp CẦN ĐO trên bo.

Giới hạn: biên dịch không chạy mã; mọi mục "Cách kiểm trên bo" vẫn chưa làm. `board = esp32-s3-devkitc-1` (8 MB flash,
không PSRAM) vẫn là giả định (CHƯA CHỐT). Hai nền tảng dùng chung một `PLATFORMIO_CORE_DIR` làm hỏng bản 7.1.3 (thiếu
`intelhex` lúc tạo bootloader): kiểm lại 3.x thì dùng một `PLATFORMIO_CORE_DIR` khác.

## Chạy trong bo ảo (QEMU, 30/09/2026)

Env `esp32s3_qemu` trong `platformio.ini` là bản CHỈ ĐỂ GIẢ LẬP của đúng mã nguồn này: `Serial` qua UART0 (QEMU của
Espressif không nối USB-Serial-JTAG ra máy tính) và flash DIO (QEMU 9.2.2 đọc sai flash QIO lúc chạy). Sau build,
`qemu/tao_anh_flash.py` ghép ảnh `.pio/build/esp32s3_qemu/qemu_flash.bin` (8 MB). Không nạp bản này vào xe.

```bat
:: trong thư mục autopark của repo; công cụ lấy từ configs\thiet_bi.json
.venv\Scripts\python.exe -X utf8 -m autopark.transport.qemu_board kiem
.venv\Scripts\python.exe -X utf8 -m pytest tests\test_firmware_qemu.py
```

Bo ảo kiểm được giao thức, máy trạng thái, dốc tốc độ, hết hạn lệnh, mất liên lạc và reset chip trên bản build thật,
với đúng `SerialVehicleIO` của laptop. Nó KHÔNG có LEDC, GPIO vào (E-stop), I2C, task watchdog kích hoạt, USB-CDC thật, nên
mọi bước "Cách kiểm trên bo" ở trên vẫn phải làm trên bo. Chi tiết, các trình giả lập khác đã thử (esp32sim chạy được bản
USB-CDC; a159x36/qemu có LEDC và tiêm chân, mới thử với sketch thử; esp-emulator có watchdog kích hoạt) và giới hạn:
[MO_PHONG_FIRMWARE.md](../../docs/MO_PHONG_FIRMWARE.md).

## Trình tự thử trên bo (đề xuất, chưa làm)

1. Nạp với `AP_ENABLE_PWM_OUTPUTS=0`, bo chỉ cắm USB. Dùng `SerialVehicleIO.open("COMx")` trên laptop: `connect()`,
   xem HELLO_ACK (boot_id, lý do reset, giới hạn), telemetry 20 Hz; thử ARM/lệnh/hết hạn/rút cáp/cắm lại/reset và
   ghi log. Mỗi lần bo khởi động lại hay panic, chữ ROM/log/backtrace đi chung cổng USB với luồng nhị phân: kỳ vọng bộ
   đếm lỗi khung tăng (bo ảo: 1 lỗi `oversize` mỗi đợt chữ) và mất một khung, không phải lỗi đường truyền
   ([MO_PHONG_FIRMWARE.md](../../docs/MO_PHONG_FIRMWARE.md) mục 5.5; CHƯA THỬ trên bo). Đo `stats.ack_rtt_s`, `stats.cmd_echo_s` thật (không lấy số của mô phỏng). Khi đã chốt `kPinEstop`: rút
   đầu nối E-stop phải thấy `ESTOP_INPUT = 1` và FAULT, CLEAR_FAULT bị từ chối (`ESTOP_ACTIVE`) cho tới khi cắm lại.
   *(Thêm 25/09/2026: phần đầu của bước này (HELLO_ACK, so giới hạn bo với cấu hình xe, đọc vài khung telemetry, không
   ARM, không COMMAND nào) nay làm được bằng nút "Kiểm kết nối bo" ở thẻ "Bo điều khiển" của giao diện, commit `6db5087`;
   [CHE_DO_QUAN_SAT.md](../../docs/CHE_DO_QUAN_SAT.md) mục 6. Mới thử với cổng serial GIẢ; ARM, lệnh, rút cáp vẫn phải
   gọi `SerialVehicleIO` như trên.)*
2. Đo bằng máy hiện sóng/logic analyzer chân xung khi đã chốt chân, vẫn CHƯA nối ESC/servo: các bước 1–5 ở mục
   "Cách kiểm trên bo" phía trên (bật nguồn, loop im 150 ms, treo 400 ms, `abort()`, interrupt watchdog,
   `esp_restart()`, rút E-stop). Ghi thời gian tới lúc chân xuống thấp hoặc về trung tính, và độ rộng xung ở pha XTAL.
3. Nối servo rồi ESC theo sơ đồ đã đối chiếu, xe kê cao bánh không chạm đất, E-stop phần cứng sẵn sàng
   (kế hoạch mục 9 đoạn "Có đồ", mục 10; tên cũ "Khi đủ phần cứng" ở
   [bản `9d68257`](https://github.com/thbn12082/autopark/blob/9d68257/KE_HOACH_TRIEN_KHAI_XE_TU_DO_v3.1.md)), giữ trần
   effort mặc định 250 ‰. Chỉ nâng `max_effort_permille` sau khi
   đã đo đường cong effort–tốc độ (giai đoạn 4), có encoder, và đã thấy STALL chốt đúng khi giữ bánh.
