# Mô phỏng firmware ESP32-S3 khi chưa có bo (29–30/09/2026)

**Câu hỏi của người dùng (29/09/2026):** có framework mã nguồn mở nào để kiểm phần cứng, nạp firmware và test thử luôn
mà không cần phần cứng, bằng mô phỏng, hay không.

**Trả lời ngắn.** Có, nhưng không công cụ mã nguồn mở nào tự làm được hết. Firmware THẬT của dự án (Arduino-ESP32
2.0.17, ESP32-S3, `firmware/esp32_vehicle`) đã chạy được trong **ba** trình giả lập trên máy bàn (mục 2): QEMU của
Espressif và esp-emulator với bản build đưa `Serial` qua UART0, esp32sim với đúng bản nạp vào xe (USB-CDC). Fork
a159x36/qemu mới chạy sketch thử khả năng, CHƯA chạy firmware xe. Cái dùng được nhất đã được đưa vào repo thành **bo ảo**
(mục 1): QEMU của Espressif (GPL) chạy bản build thật, laptop nói chuyện bằng đúng `SerialVehicleIO`. Bo ảo kiểm được
giao thức, máy trạng thái, dốc tốc độ, hết hạn lệnh, mất liên lạc, reset chip. Nó KHÔNG kiểm được xung ESC/servo, chân
E-stop, cảm biến, USB-CDC thật, task watchdog kích hoạt, thời gian thực chính xác: các việc đó cần công cụ khác (mục 3–4)
hoặc bo thật với máy phân tích logic. Chạy được trong giả lập không chứng minh gì về bo thật.

Cách làm: khảo sát ngày 29/09/2026 bằng 13 tác tử (5 nhóm nghiên cứu, mỗi nhóm một tác tử phản biện đối chiếu nguồn
gốc, một tác tử thử QEMU với firmware thật, một tác tử rà chỗ thiếu, một tác tử bổ sung); các tác tử tự tải và chạy QEMU,
fork a159x36, esp32sim, esp-emulator trên máy bàn. Ngày 30/09/2026 đưa bo ảo vào repo, sửa các lỗi tìm ra, rồi cho 4 tác
tử review các thay đổi (23 phát hiện, không lưu log; phần đã xác nhận được sửa trong ngày). Trước khi commit, thêm một
lượt review 5 góc, mỗi góc một tác tử kiểm chứng chéo (26 phát hiện, 16 được xác nhận và đã sửa; không lưu log). Kết quả
thô của khảo sát 29/09:
[ket_qua_workflow_20260929.json](evidence/mo_phong_20260930/nghien_cuu/ket_qua_workflow_20260929.json).

## 1. Bo ảo trong repo (30/09/2026)

| Thành phần | Nội dung |
|---|---|
| [`configs/thiet_bi.json`](../configs/thiet_bi.json) | khóa `qemu_xtensa` (qemu-system-xtensa của Espressif), `platformio_python` (python có gói platformio), `platformio_core_dir` (phải là thư mục có sẵn); đổi máy chỉ sửa tệp này |
| [`platformio.ini`](../firmware/esp32_vehicle/platformio.ini) env `esp32s3_qemu` | mã nguồn y hệt env `esp32s3`; chỉ khác: `Serial` qua UART0 (`ARDUINO_USB_CDC_ON_BOOT=0`) và flash DIO (mục 2.1). Không nạp bản này vào xe |
| [`qemu/tao_anh_flash.py`](../firmware/esp32_vehicle/qemu/tao_anh_flash.py) | sau build, ghép bootloader + bảng phân vùng + boot_app0 + app thành `.pio/build/esp32s3_qemu/qemu_flash.bin` (8 MB); offset lấy từ builder của PlatformIO |
| [`autopark/transport/qemu_board.py`](../autopark/transport/qemu_board.py) | `QemuBoard`: chạy QEMU với một bản sao ảnh, UART0 ra `socket://127.0.0.1:<cổng>`, monitor HMP, chỉ báo sẵn sàng khi firmware trả HELLO_ACK, khởi động QEMU tối đa 5 lần (thử lại tới 4 lần) khi QEMU chết lúc khởi động (cổng tự chọn thì mỗi lần một cổng mới); trên Windows gắn QEMU vào một Job Object nên QEMU chết theo tiến trình Python (Ctrl+C, bị kill), không bị bỏ lại chạy ngầm |
| [`autopark/transport/socket_port.py`](../autopark/transport/socket_port.py) | `SocketPort`: cổng kiểu pyserial trên TCP cho URL `socket://`, thay `socket://` của pyserial (mục 5.1–5.3) |
| [`tests/test_firmware_qemu.py`](../tests/test_firmware_qemu.py) | 6 test bo ảo; 5 test đọc cấu hình và 2 test cơ chế chạy lại (bo giả, chạy ở mọi máy); máy không có QEMU thì phần bo ảo bỏ qua |

Lệnh (trong thư mục `autopark` của repo):

```bat
:: build, chạy bo ảo, HELLO + 2 s telemetry, in kết quả rồi tắt
.venv\Scripts\python.exe -X utf8 -m autopark.transport.qemu_board kiem
:: chạy bo ảo ở socket://127.0.0.1:5555 tới khi Ctrl+C
.venv\Scripts\python.exe -X utf8 -m autopark.transport.qemu_board chay
.venv\Scripts\python.exe -X utf8 -m pytest tests\test_firmware_qemu.py
```

Từ Python: `SerialVehicleIO.open("socket://127.0.0.1:5555")` (từ 30/09/2026 `open()` nhận URL). Giao diện (thẻ "Bo điều
khiển") hiện chỉ liệt kê cổng COM, nên CHƯA dùng bo ảo từ giao diện được.

**Test bo ảo kiểm gì** (bản build thật, qua đúng đường byte của laptop):

| Test | Kiểm |
|---|---|
| `test_hello_ack_matches_the_python_reference` | giới hạn, chu kỳ telemetry, phiên bản trong HELLO_ACK = của `FirmwareModel(FirmwareConfig())`; lý do reset POWER_ON; DISARMED |
| `test_telemetry_is_20hz_with_clean_frames` | ≥ 17 khung/s, trung vị bước thời gian bo 50 ms, không lỗi khung, không mất số thứ tự |
| `test_command_ramps_then_expires_and_host_silence_disarms` | ARM rồi COMMAND enable=1 → RUNNING; tốc độ mục tiêu có tăng (≥ 0,03 m/s) và dốc không vượt giới hạn; hết hạn lệnh → ARMED/COMMAND_TIMEOUT; laptop im → DISARMED/LINK_TIMEOUT không sớm hơn `link_timeout` |
| `test_command_while_disarmed_is_rejected` | COMMAND khi DISARMED → ACK BAD_STATE |
| `test_nonblocking_control_loop_keeps_up_with_telemetry` | vòng 50 Hz `poll(block=False)` như `Session`: ≥ 36/≈ 40 khung trong 2 s, không mất số thứ tự, không TELEMETRY_STALE (hồi quy lỗi mục 5.1) |
| `test_chip_reset_is_seen_as_firmware_reset` | reset cả chip (HMP `system_reset`) → laptop thấy mất liên lạc, phiên mới có boot_id mới, sự kiện FIRMWARE_RESET |

Kết quả (mã sau review, chạy 10:11–10:13 ngày 30/09/2026, máy bàn; trước khi `QemuBoard` chuyển sang hàm chung
`autopark/power_throttling.py` lúc 11:53; lượt trên commit: [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 8):
- `kiem` đạt: HELLO_ACK báo lý do reset POWER_ON, chu kỳ telemetry 50 ms; trạng thái DISARMED in ra là trạng thái đọc
  sau khi chờ bo ra khỏi BOOT (`wait_ready`); QEMU khởi động 1 lần
  ([kiem_bo_ao.txt](evidence/mo_phong_20260930/bo_ao_30092026/kiem_bo_ao.txt)). Tệp đó ghi "55 khung trong 2 s", nhưng
  bản `kiem` lúc ấy đếm gộp cả khung nhận trong lúc kết nối và chờ bo ra khỏi BOOT: theo lượt đếm tách riêng dưới đây,
  khoảng 16 khung trong số đó tới trước cửa sổ đo và khoảng 39 khung trong 2 s. Bản `kiem` đếm tách riêng (mã
  `ff4a018` + sửa cách đếm, chưa commit lúc chạy; hai lượt ≈ 15:00 ngày 30/09/2026) cho 40 và 39 khung trong 2 s
  (≈ 20 Hz), cộng 16 khung nhận trước đó; lượt đầu phải khởi động QEMU 2 lần (lỗi #175)
  ([kiem_bo_ao_dem_rieng.txt](evidence/mo_phong_20260930/bo_ao_30092026/kiem_bo_ao_dem_rieng.txt)). Một lượt `kiem` lúc
  sáng cùng ngày (mã trước review) phải khởi động QEMU 3 lần (2 lần QEMU tự thoát, lỗi #175 ở dưới; đầu ra console,
  không lưu log).
- Chạy lặp riêng `tests/test_firmware_qemu.py` 10 lượt: 10/10 lượt đạt cả 13 test (6 trong đó chạy firmware thật trong
  QEMU), không lượt nào phải chạy lại
  ([chay_lap_test_bo_ao.txt](evidence/mo_phong_20260930/bo_ao_30092026/chay_lap_test_bo_ao.txt)). Số của toàn bộ bộ test:
  [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 8.
- Chạy lại trên commit `ebbec83` (cây làm việc sạch, 13:47–13:49):
  - `kiem` đạt: 55 khung tính từ lúc kết nối, cùng cách đếm gộp như trên (≈ 16 khung chờ bo ra khỏi BOOT + ≈ 39
    khung trong 2 s), QEMU khởi động 1 lần
    ([kiem_bo_ao_ebbec83.txt](evidence/mo_phong_20260930/bo_ao_30092026/kiem_bo_ao_ebbec83.txt)).
  - Chạy lặp 10 lượt: 10/10 lượt đạt cả 13 test (6 trong đó chạy firmware thật trong QEMU), không có cảnh báo #175 hay
    LOOP_OVERRUN
    ([chay_lap_test_bo_ao_ebbec83.txt](evidence/mo_phong_20260930/bo_ao_30092026/chay_lap_test_bo_ao_ebbec83.txt)).

**Độ tin cậy khi máy bận** (30/09/2026; máy bàn đang chạy việc khác của người dùng):
- Lúc sáng, khi máy đang rất bận (đo nhanh bằng `Get-Process`: Edge chạy ẩn dựng hình bằng CPU ≈ 13 lõi, một job mô
  phỏng, một crawler 12 luồng; không lưu log), 5/10 lượt chạy lặp của bản test đầu tiên có test hỏng: firmware chốt
  LOOP_OVERRUN (hai chu kỳ 10 ms cách nhau > 100 ms vì QEMU bị bỏ đói), ghi ra socket "quá hạn" (mục 5.2), hoặc QEMU tự
  thoát khi chip khởi động lại. Đó là đầu ra console, không lưu log riêng.
- QEMU tự thoát lúc khởi động (espressif/qemu#175): 2/12 lần với chế độ mặc định (đa luồng, mã 0xC0000005). Chế độ TCG
  đơn luồng (`-accel tcg,thread=single`) hết lỗi này (0/12) nhưng chậm: bước telemetry tới 160 ms, LOOP_OVERRUN cả 12/12
  lượt ([boot_reliability.out](evidence/mo_phong_20260930/bo_ao_30092026/boot_reliability.out)); ngày 29/09 nó còn làm
  QEMU chết ở cả 3/3 lần reset do firmware (`esp_restart`, `abort`)
  ([qemu175_va_tcg_don_luong/](evidence/mo_phong_20260930/so_sanh_29092026/qemu_espressif/qemu175_va_tcg_don_luong/)).
  Vì vậy giữ chế độ mặc định, `QemuBoard.start()` thử tối đa 5 lần. (`-icount shift=3,sleep=off` khởi động lại đúng 2/2
  lần ngày 29/09; CHƯA dùng.)
- Test chạy lại một kịch bản (tối đa 3 lần, test reset 4 lần, có cảnh báo) chỉ khi có bằng chứng lỗi thuộc bo ảo: tiến
  trình QEMU đã chết (khởi động lại bo ảo), hoặc firmware đang chốt LOOP_OVERRUN (chốt này giữ qua HELLO nên hỏi lại được
  bằng một phiên mới; CLEAR_FAULT rồi mở phiên mới mới đọc được trạng thái thật). Hỏng vì lý do khác thì báo lỗi ngay. Cơ
  chế này có test riêng với bo giả `LoopbackBoard`, chạy ở mọi máy. *(Bản đầu ngày 30/09 có lỗi: sau CLEAR_FAULT còn đọc
  khung FAULT cũ, nên nhánh chạy lại vì LOOP_OVERRUN không bao giờ chạy; review tìm ra và đã sửa.)*
- `QemuBoard` chạy QEMU với ưu tiên trên mức thường và tắt EcoQoS của Windows cho tiến trình đó. Đo A/B lúc máy bớt bận
  không thấy khác biệt ([ab_boost.out](evidence/mo_phong_20260930/bo_ao_30092026/ab_boost.out)); giữ vì vô hại.

**Giới hạn của bo ảo** (QEMU esp-develop-9.2.2-20260417; mục 2.1): không LEDC, không GPIO vào, không I2C/SPI/ADC/PCNT,
USB-Serial-JTAG chỉ là vỏ thanh ghi; watchdog phần cứng không bao giờ kích hoạt; thời gian bám đồng hồ máy (chậm
≈ 0,1–0,17 %), máy bận có thể làm firmware chốt LOOP_OVERRUN; `millis()` không về 0 khi reset; QEMU ghi ngược vào ảnh
flash (bo ảo dùng bản sao mỗi lần). Hai bản build khác nhau ở cách nối `Serial`, nên đường USB-CDC của bản nạp vào xe
KHÔNG được kiểm ở đây (xem esp32sim, mục 2.3). Bo ảo bị giết cứng (không kịp dọn) có thể để lại thư mục `bo_ao_qemu_*`
chứa bản sao ảnh 8 MB trong `%TEMP%`.

## 2. Các trình giả lập đã chạy thử (29/09/2026)

| Công cụ | Mã nguồn | Firmware nạp vào xe (USB-CDC) | Firmware xe + `SerialVehicleIO` | E-stop, PWM | Watchdog, lý do reset |
|---|---|---|---|---|---|
| QEMU của Espressif 9.2.2 | mở (GPL-2.0), Windows | chạy nhưng không nói chuyện được (USB chỉ là vỏ) | **có**, bản UART0 | không mô phỏng; bật PWM thì `ledcSetup` panic; chân vào luôn LOW | không bao giờ kích hoạt; lý do reset SW/PANIC/POWER_ON đúng |
| esp32sim (Rust/WASM) | mở (MIT), chạy bằng Node | **có**: HELLO_ACK + telemetry 20 Hz | cần vá kênh nối tiếp (byte ≥ 0x80 hỏng) | tiêm được nút; mọi chân vào mặc định HIGH; LEDC không dạng sóng | không có watchdog; SW đúng; bước chính xác theo chu kỳ |
| esp-emulator 0.44 (Espressif, beta) | **đóng** (bản Linux, qua WSL2) | CHƯA THỬ nói chuyện (chỉ UART nối ra ngoài) | có, bản UART0 (29/09, qua bộ chuyển `in_waiting` trước khi sửa `_pump`) | mọi chân vào đọc HIGH (E-stop sẽ "đang nhấn"); LEDC chỉ thanh ghi | **TWDT/IWDT có kích hoạt**; mọi reset báo WDT |
| a159x36/qemu v5.4.1 | mở (GPL), Windows | CHƯA THỬ | CHƯA THỬ (chỉ chạy sketch thử, lệnh chữ qua UART0) | sketch thử: thanh ghi LEDC có; tiêm được chân qua monitor; không dạng sóng | sketch thử: không kích hoạt; lý do reset đúng; móc panic có tác dụng |

### 2.1. QEMU của Espressif (dùng cho bo ảo)

Bản `esp-develop-9.2.2-20260417` (QEMU 9.2.2; phát hành 19/04/2026, mới nhất tại 29/09/2026), bản Windows x86_64 36 MB,
SHA-256 khớp tệp checksum của bản phát hành; chạy thẳng, không cần cài. Tác tử thử ngày 29/09/2026
([qemu_espressif_29092026/](evidence/mo_phong_20260930/qemu_espressif_29092026/)):
- Bản UART0: HELLO_ACK lần đầu sau 7,9 ms; REQUEST → ACK 1,2–1,6 ms (tối đa 11 ms); telemetry 19,97–19,99 Hz; 178/178
  khung giải mã được. Đủ các kịch bản ARM, RUNNING, hết hạn lệnh, LINK_TIMEOUT, BAD_STATE, dòng lệnh 20 Hz, kết nối lại,
  reset qua monitor ([run2_probe_console.txt](evidence/mo_phong_20260930/qemu_espressif_29092026/run2_probe_console.txt),
  [run2_report.json](evidence/mo_phong_20260930/qemu_espressif_29092026/run2_report.json)).
- Bản nạp vào xe (USB-CDC): khởi động và chạy, nhưng laptop nhận 0 byte. Thiết bị `misc.esp32c3.usb_serial_jtag` của
  máy esp32s3 là vỏ thanh ghi, không nối ra ngoài ([x2_cdc_report.json](evidence/mo_phong_20260930/qemu_espressif_29092026/x2_cdc_report.json)).
- Ảnh flash: bản QIO ghi thành ảnh 8 MB khởi động lặp (assert trong `esp_flash_init_default_chip`) vì mô hình flash
  8 MB (GigaDevice gd25q64) không có bit bật QIO ([run1_qio_8MB_boot_loop.txt](evidence/mo_phong_20260930/qemu_espressif_29092026/run1_qio_8MB_boot_loop.txt)).
  Ảnh 16 MB thì khởi động, nhưng mọi lần đọc flash kiểu quad lúc chạy lệch 2 byte (espressif/qemu#169; bản sửa PR #177
  chưa gộp): NVS/Preferences không bao giờ giữ, core dump đọc ra rác (thông báo `Incorrect size of core dump image:
  -65536` là triệu chứng của lỗi này) ([q_qio16.log](evidence/mo_phong_20260930/so_sanh_29092026/qemu_espressif/q_qio16.log)).
  Bản DIO 8 MB đọc đúng ở chế độ của chính bản build (DIO) và NVS giữ qua `esp_restart`, `abort` (bộ đếm 0 → 1 → 2,
  [q_dio8_mt.log](evidence/mo_phong_20260930/so_sanh_29092026/qemu_espressif/q_dio8_mt.log)); nhưng nếu lúc chạy đổi sang
  FASTRD/DOUT/QOUT thì lệch −1 byte, QIO lệch +4, và sau `abort` vẫn báo `Core dump data check failed` (chưa tìm nguyên
  nhân). Vì vậy env `esp32s3_qemu` dùng DIO; bản firmware xe hiện không đọc flash lúc chạy ngoài phần khởi động của
  Arduino. ([q_dio8.log](evidence/mo_phong_20260930/so_sanh_29092026/qemu_espressif/q_dio8.log) là lượt TCG đơn luồng,
  `esp_restart` không trở lại.)
- Watchdog: firmware đặt TWDT 1 s đúng như mã (thanh ghi TIMG0: tầng ngắt 1 s, tầng reset 2 s; IWDT 300/600 ms,
  [run2_timg_wdt_regs.txt](evidence/mo_phong_20260930/qemu_espressif_29092026/run2_timg_wdt_regs.txt)), nhưng QEMU không
  bao giờ cho chúng kích hoạt: mô hình TIMG chỉ chốt cấu hình khi ghi bit `CONF_UPDATE_EN`, mà HAL S3 của ESP-IDF (4.4,
  5.5) không ghi bit đó. Bản thử có lệnh treo `loop()`: hơn 16 s không có thông báo task_wdt, không reset (`probe` trong
  JSON nghiên cứu; [x3_wdt_console_HANG.txt](evidence/mo_phong_20260930/qemu_espressif_29092026/x3_wdt_console_HANG.txt)
  chỉ ghi 1,5 s đầu); sketch thử im ≈ 44 s không reset ([q_qio16.log](evidence/mo_phong_20260930/so_sanh_29092026/qemu_espressif/q_qio16.log)).
- Panic: `abort()` trong bản thử đi qua `__wrap_esp_panic_handler` (móc có chạy), khởi động lại với lý do PANIC;
  `esp_restart()` cho lý do SOFTWARE ([x3_wdt_console_ABORT_RESTART.txt](evidence/mo_phong_20260930/qemu_espressif_29092026/x3_wdt_console_ABORT_RESTART.txt)).
  esp-idf-monitor 1.10.0 giải mã được backtrace của Arduino 2.0.17 từ `socket://`
  ([esp_idf_monitor_giai_ma_panic.txt](evidence/mo_phong_20260930/so_sanh_29092026/qemu_espressif/esp_idf_monitor_giai_ma_panic.txt)).
- Thời gian: bám đồng hồ máy, chậm 0,1–0,17 %; `millis()` không về 0 khi reset. LOOP_OVERRUN bị chốt một lần trong
  ≈ 13 phút lúc máy bận; các lượt canh 120 s (máy rảnh), 30 s (32 luồng đốt CPU), 300 s (build + QEMU khác chạy cùng)
  không lần nào. `-icount shift=3,sleep=off` cho thời gian bo xác định tới khi có byte từ máy tính (≈ 1,35 lần thời gian
  thực; [q_dio8_ic1.log](evidence/mo_phong_20260930/so_sanh_29092026/qemu_espressif/q_dio8_ic1.log)); CHƯA dùng trong repo.
- Không mô phỏng cho ESP32-S3: LEDC, ma trận GPIO/IOMUX (E-stop luôn đọc LOW), I2C, GP-SPI, RMT, PCNT, ADC, USB, Wi-Fi.

### 2.2. a159x36/qemu (fork cộng đồng của QEMU Espressif)

Bản v5.4.1 (29/06/2026) có gói Windows 21 MB, GPL. **Chỉ chạy sketch thử khả năng**
([sketch_thu_gia_lap_main.cpp](evidence/mo_phong_20260930/so_sanh_29092026/sketch_thu_gia_lap_main.cpp), KHÔNG phải
firmware xe; lệnh một ký tự qua UART0), chưa chạy firmware xe hay `SerialVehicleIO`. Với sketch đó: LEDC được mô phỏng
(đọc lại cấu hình và duty, định tuyến ra chân), thanh ghi LEDC giữ qua `esp_restart`/`abort` (đúng như `main.cpp` giả
định về chip thật); điện trở kéo lên/xuống có mô hình; tiêm mức chân GPIO14 bằng lệnh monitor `sendkey 2`; đọc flash
đúng mọi chế độ; lý do reset SW/PANIC đúng; lệnh ghi ma trận GPIO của móc panic có tác dụng. TWDT không kích hoạt (3/3
lượt: [W1](evidence/mo_phong_20260930/so_sanh_29092026/a159x36_qemu/a_qio16_W1.log),
[W2](evidence/mo_phong_20260930/so_sanh_29092026/a159x36_qemu/a_qio16_W2.log),
[W3](evidence/mo_phong_20260930/so_sanh_29092026/a159x36_qemu/a_qio16_W3.log)). I2C chỉ có hai thiết bị cố định (tmp105,
mpu6050). 1/5 lượt thoát ngay sau bootloader (chưa rõ vì sao). Không tài liệu, không API tiêm chân chính thức
([a_qio16.log](evidence/mo_phong_20260930/so_sanh_29092026/a159x36_qemu/a_qio16.log),
[a_qio16_hmp.txt](evidence/mo_phong_20260930/so_sanh_29092026/a159x36_qemu/a_qio16_hmp.txt)). Hợp để kiểm E-stop, cấu hình
LEDC và móc panic ở mức thanh ghi với một bản build thử có chân giả; CHƯA đưa vào repo.

### 2.3. esp32sim (joakimeriksson, MIT)

Trình giả lập viết bằng Rust, bản WebAssembly trên GitHub Pages (nhánh main 4ab7e90, 23/09/2026), chạy bằng Node trên
Windows. **Là công cụ mở duy nhất chạy được bản firmware nạp vào xe (USB-CDC)**: HELLO → HELLO_ACK, rồi telemetry đúng
mỗi 50,000 ms thời gian giả lập, vì mô hình USB-Serial-JTAG tạo ngắt SOF 4 lần/ms nên `HWCDC` của Arduino 2.0.17 coi là
đang cắm ([prod.log](evidence/mo_phong_20260930/so_sanh_29092026/esp32sim/prod.log); thời điểm từng byte:
[prod.log.usb.json](evidence/mo_phong_20260930/so_sanh_29092026/esp32sim/prod.log.usb.json)). Chạy từng bước đúng số chu
kỳ, nên có thể phát lại `vectors.json` với thời gian xác định; nhưng 4/10 kịch bản cần tiêm đầu vào (E-stop, cảm biến tốc
độ; `read_inputs()` của `main.cpp` luôn báo không có số đo), kịch bản quay vòng đồng hồ cần `millis()` gần 2^32, và
`boot_id` lấy từ `esp_random()` phải che: các phần đó cần GDB hoặc bản build có móc thử. Hạn chế khác: kênh nối tiếp phía
máy tính là chuỗi JSON, byte ≥ 0x80 không gửi được và byte ra bị thay bằng U+FFFD, phải vá (MIT cho phép) trước khi so từng
byte; mọi chân vào mặc định HIGH, kể cả INPUT_PULLDOWN (với `kEstopActiveLow = false` nghĩa là E-stop "đang nhấn");
không dạng sóng LEDC (thanh ghi LEDC còn bị xóa khi reset CPU, khác chip thật); không watchdog; UART0 không nhận byte lẻ;
0,69 lần thời gian thực.

### 2.4. esp-emulator (Espressif, beta)

Bản 0.44.0; hỗ trợ S3 từ 0.43.0 (18/09/2026). **Mã đóng**: repo chỉ có tài liệu và script (Apache-2.0), nhị phân chỉ cho
Linux/macOS; câu hỏi công bố mã nguồn (issue #10) chưa quyết. Tác tử phản biện chạy nó trong WSL2 trên máy bàn với bản
build thật của firmware xe (Serial qua UART0): khởi động tới `loop()` và qua đủ giao thức (HELLO_ACK, telemetry 20 Hz, ARM,
RUNNING, hết hạn lệnh, LINK_TIMEOUT), qua một bộ chuyển `in_waiting` (MSG_PEEK) vì lúc đó `_pump` chưa sửa
([firmware_xe/](evidence/mo_phong_20260930/so_sanh_29092026/esp_emulator/firmware_xe/); kết quả trong JSON nghiên cứu,
phần phản biện nhóm "others"). Với sketch thử: TWDT kích hoạt ≈ 1,2 s sau khi `loop()` treo
([e_qio8_W.log](evidence/mo_phong_20260930/so_sanh_29092026/esp_emulator/e_qio8_W.log)), IWDT cũng kích hoạt
([e_qio8_I.log](evidence/mo_phong_20260930/so_sanh_29092026/esp_emulator/e_qio8_I.log)); nhưng mọi lần reset do firmware
(abort, TWDT, IWDT, `esp_restart`) đều thành `RTCWDT_SYS_RST`, lý do reset luôn là WDT; mọi chân vào đọc HIGH; LEDC chỉ ở
mức thanh ghi; 0,48 lần thời gian thực. Chỉ đáng dùng để thấy watchdog thật sự kích hoạt.

### 2.5. Không chạy thử

- **Wokwi** (CLI v0.27.1, 16/09/2026, MIT; lõi mô phỏng mã đóng, chạy trên cloud): theo tài liệu, S3 có GPIO, UART,
  USB-Serial-JTAG (chỉ phần nối tiếp), I2C chủ, SPI, LEDC, PCNT, timer, watchdog, ADC; có máy phân tích logic xuất VCD,
  nút bấm điều khiển bằng script, chip tự định nghĩa (Custom Chips). Phủ rộng nhất, nhưng phải tải firmware lên cloud của
  Wokwi, cần tài khoản/token; bản miễn phí chỉ cho "cá nhân phi thương mại" (50 phút mô phỏng CI/tháng), extension VS
  Code miễn phí chỉ cho repo công khai mã nguồn mở. `HWCDC` của Arduino 2.0.17 trên Wokwi chưa ai chứng minh (phụ thuộc
  mô hình ngắt SOF). Không chạy vì việc tải firmware lên và mở tài khoản là quyết định của người dùng.
- **Renode** 1.17.0 (07/09/2026, MIT): chưa khởi động được ảnh ESP32-S3 (mô hình ngoại vi S3 mới có ở bản nightly từ
  25/09/2026, chưa có timer/watchdog). **PICSimLab** 0.9.3 (GPL): chỉ ESP32 và ESP32-C3. **SimulIDE**: bản chính không có
  S3; một fork cá nhân thử nghiệm. **Velxio** v3.0.5 (AGPL/thương mại): có S3 qua QEMU, hướng tới Arduino 3.x ảnh DIO 4 MB;
  chưa thử. **Proteus, Tinkercad, Cirkit Designer**: mã đóng và/hoặc không có S3.

### 2.6. Chạy `main.cpp` trên máy tính, không cần chip

Hai lượt tác tử ngày 29/09/2026 dựng hai bản thử lớp giả API Arduino/ESP-IDF (g++ 16.1.0, CMake):
1. Lượt 1 (`glue_poc`, macro CHECK tự viết): 4 biến thể (2.x/3.x × PWM tắt/bật), 97 kiểm tra đạt; và một bản chạy thời
   gian thực `sil_v2_pwm0` từ `main.cpp` KHÔNG sửa (2.0.17, PWM tắt), nối `Serial` giả ra TCP. `sil_client.py` dùng
   `SerialVehicleIO` qua một bộ chuyển (`in_waiting` báo đủ byte): HELLO_ACK, ARM, 30 khung telemetry trong 1,5 s ở RUNNING;
   qua `socket://` của pyserial thì báo TELEMETRY_STALE (lỗi mục 5.1)
   ([lop_gia_pc/](evidence/mo_phong_20260930/so_sanh_29092026/lop_gia_pc/): báo cáo của lượt này, nhật ký SIL, đầu ra trích
   từ nhật ký tác tử).
2. Lượt 2 (`hostglue`, fff + doctest): 3 biến thể, 21 ca test, 120 kiểm tra đạt. Chỉ biến thể 2.0.17 PWM tắt biên dịch
   `main.cpp` nguyên vẹn; kiểm E-stop, LEDC và móc panic chạy trên bản sao đổi 3 hằng số chân -1 → 4/5/6.

PlatformIO `native` + ArduinoFake, gMock cũng chạy được. Cách này rẻ nhất để kiểm thứ tự lời gọi của lớp dán (E-stop,
output guard, móc reset), nhưng không chứng minh thời gian hay tác dụng thanh ghi. Mã nguồn hai bản thử được giữ ngoài
repo ở `D:\xetulai\_platformio\giu_lai\lop_gia_pc` (mục 6); CHƯA đưa vào repo.

## 3. Nạp và test chung cho giả lập và bo thật (đề xuất, CHƯA LÀM)

- **pytest-embedded** (Espressif, MIT, 2.9.3 ngày 31/08/2026): một bộ test pytest chạy với QEMU, Wokwi và bo thật; với bo
  thật tự nạp bằng esptool rồi đọc cổng nối tiếp. Tác tử đã chạy trên máy bàn Windows với QEMU S3 (khởi động, reset qua
  QMP, kết quả Unity của PlatformIO dạng JUnit, 4/4 lượt). Phù hợp nhất cho bước "nạp rồi test luôn" khi có bo. Bo ảo
  trong repo hiện dùng pytest thường + `subprocess`, không thêm phụ thuộc.
- **esp-idf-monitor** 1.10.0 (PyPI): giải mã backtrace panic của Arduino 2.0.17 từ URL `socket://` (đã thử với QEMU).
- **sigrok-cli** + máy phân tích logic giá rẻ (fx2lafw, GPL): đo tự động độ rộng xung ESC/servo, thời điểm chân ESC xuống
  thấp khi panic, trên bo thật (các bước "Cách kiểm trên bo" của [README firmware](../firmware/esp32_vehicle/README.md)).
- **OpenOCD/GDB** (openocd-esp32 v0.12.0-esp32-20260831; GDB của toolchain đã có): dừng, đọc/ghi biến, tiêm lỗi trên cả
  giả lập lẫn bo. Lưu ý: OpenOCD tắt bộ đếm watchdog ở mỗi điểm dừng, nên đừng kiểm watchdog khi đang gắn OpenOCD.
- labgrid, LAVA, OpenHTF, Robot Framework: cho dàn nhiều bo; quá nặng với một bo.

## 4. Kiểm cái gì bằng gì (đề xuất)

| Muốn kiểm | Công cụ | Trạng thái |
|---|---|---|
| Giao thức, máy trạng thái (so từng byte) | test lõi C++ trên máy tính + `FirmwareModel` + `vectors.json` | có từ trước |
| Bản build thật + phần mềm laptop | bo ảo QEMU (mục 1) | **có từ 30/09/2026** |
| Lớp dán `main.cpp` (thứ tự lời gọi) | lớp giả trên máy tính (mục 2.6) | bản thử ngoài repo |
| Bản nạp vào xe (USB-CDC) | esp32sim sau khi vá kênh nối tiếp | CHƯA LÀM |
| E-stop, cấu hình LEDC, móc panic (mức thanh ghi) | a159x36/qemu với bản build thử có chân giả | CHƯA LÀM |
| Watchdog thật sự kích hoạt | esp-emulator (mã đóng) hoặc bo thật | CHƯA LÀM |
| Dạng sóng ESC/servo, chân ESC khi panic, ESC phản ứng | bo thật + máy phân tích logic (sigrok), hoặc Wokwi nếu chấp nhận cloud | CHƯA LÀM |
| Cảm biến I2C sau này (AS5600, VL53L1X, BNO085) | Wokwi Custom Chips (cloud) hoặc tự viết mô hình (esp32sim) | CHƯA LÀM |

## 5. Phát hiện ảnh hưởng mã và tài liệu của dự án

1. **`SerialVehicleIO` qua `socket://` của pyserial mất telemetry mà không báo.** pyserial 3.5 báo `in_waiting` của socket
   chỉ 0 hoặc 1, `_pump` cũ đọc đúng chừng đó mỗi lần. Với QEMU ngày 29/09/2026: vòng 50 Hz `poll(block=False)` + `send`
   nhận 2/≈ 40 khung trong 2 s, hai lần TELEMETRY_STALE, 84 lệnh gửi bị từ chối (bộ chuyển đếm đúng byte: 40/40)
   ([run2_report.json](evidence/mo_phong_20260930/qemu_espressif_29092026/run2_report.json), `loop`); vòng hỏi nhanh hơn
   (≈ 2 ms) nhận 73/≈ 200 khung trong 10 s, khung dồn lại mà tuổi khung (đóng dấu lúc nhận) không lộ ra
   ([trich_nhat_ky_tac_tu.txt](evidence/mo_phong_20260930/so_sanh_29092026/cau_rfc2217/trich_nhat_ky_tac_tu.txt)).
   **Sửa 30/09/2026:** `_pump` đọc cho tới hết byte sẵn có (chỉ gọi `read` khi `in_waiting > 0`; tối đa 64 KB và 20 ms mỗi
   lần), byte đọc được trước lỗi cổng vẫn được xử lý; và `socket://` nay dùng `SocketPort` của dự án với `in_waiting` đúng
   số byte. Test mới trong `tests/test_transport_vehicle_io.py` (cổng giả báo 0/1 và đếm lần đọc phải chờ; luồng vô tận đọc
   chậm; `SocketPort` với TCP thật; một "bo" `FirmwareModel` sau cổng TCP thật) hỏng với mã cũ, đạt với mã mới. Cổng COM
   thật báo đúng số byte, nên theo mã thì không đổi hành vi; với bo thật CHƯA THỬ.
2. **`socket://` của pyserial 3.5 còn hai điểm xấu:** `write()` kiểm hạn ghi SAU khi đã gửi xong (`protocol_socket.py`),
   nên tiến trình bị trễ lịch lâu hơn hạn 50 ms là báo "Write timeout" dù đã gửi hết (gặp một lần trong các lượt chạy lặp
   sáng 30/09/2026 lúc máy rất bận, `SerialTimeoutException` từ `send()`; đầu ra console, không lưu log); `close()` ngủ
   0,3 s. `SocketPort` không có hai điểm này (chỉ báo lỗi ghi khi socket thật sự không nhận hết trong hạn).
3. **`SerialVehicleIO.open()` nay nhận URL**: `socket://` qua `SocketPort`; URL khác của pyserial (`rfc2217://`...) qua
   `serial_for_url`, riêng rfc2217 bỏ `write_timeout` vì client của pyserial không nhận tham số này. Cầu
   `examples/rfc2217_server.py` của pyserial đặt trước cổng TCP thô của QEMU cũng tránh được lỗi 1 (200/200 khung với mã cũ,
   [trich_nhat_ky_tac_tu.txt](evidence/mo_phong_20260930/so_sanh_29092026/cau_rfc2217/trich_nhat_ky_tac_tu.txt)).
4. **Chú thích watchdog sai.** `main.cpp`, README firmware, [GIAO_THUC_XE.md](GIAO_THUC_XE.md) và
   [GIAI_DOAN_6_CHUAN_BI.md](GIAI_DOAN_6_CHUAN_BI.md) ghi: với Arduino 2.x, nếu TWDT đã khởi tạo sẵn thì
   `esp_task_wdt_init(1, true)` trả lỗi và giữ 5 s. Sai: ESP-IDF 4.4 ghi rõ hàm này gặp TWDT đã khởi tạo thì đổi thời hạn
   và chế độ panic; thanh ghi đọc trong QEMU là 1 s / 2 s; với sketch thử (không phải firmware xe, mục 2.4)
   esp-emulator kích hoạt sau ≈ 1,2 s. Đã sửa các chỗ đó ngày
   30/09/2026 (mã firmware không đổi), cả kỳ vọng ở bước thử watchdog trên bo. Trên bo thật vẫn CẦN ĐO.
5. **Trên bo thật, chữ khởi động và backtrace panic sẽ lẫn vào luồng nhị phân trên cùng cổng USB.** ROM của S3 in ra
   USB-Serial-JTAG theo mặc định của ROM/eFuse (không do cấu hình của app); cấu hình SDK của Arduino 2.0.17 cho S3 có thêm
   `CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=1`, nên log của app và backtrace panic cũng ra đó. esp32sim cho thấy chữ ROM
   trên luồng USB của bản nạp vào xe. Bo ảo (bản UART0) cho biết bộ tách khung phản ứng ra sao: reset chip → 367 byte chữ →
   đúng 1 lỗi `oversize`, 0 lỗi COBS/CRC, khung đầu tiên sau đoạn chữ bị bỏ cùng
   ([run2_report.json](evidence/mo_phong_20260930/qemu_espressif_29092026/run2_report.json) `reset`,
   [run2_reset_rx.txt](evidence/mo_phong_20260930/qemu_espressif_29092026/run2_reset_rx.txt)). Trên bo thật CHƯA THỬ; đã
   ghi vào [GIAO_THUC_XE.md](GIAO_THUC_XE.md) mục 12 và bước 1 "Trình tự thử trên bo" của README firmware.
6. Bo ảo tránh hai lỗi QEMU ở mục 2.1 nhờ dùng DIO và thử lại; bản nạp vào xe (QIO, USB-CDC) không bị ảnh hưởng.

## 6. Công cụ đã tải về máy bàn và dọn dẹp

Đặt ngoài repo, trên ổ D (ổ C gần đầy):

| Thư mục | Nội dung |
|---|---|
| `D:\xetulai\_platformio\qemu` | QEMU của Espressif 9.2.2 cho Windows (≈ 139 MB giải nén + 36 MB gói tải); đường dẫn ghi trong `configs/thiet_bi.json` |
| `D:\xetulai\_platformio\a159_qemu` | fork a159x36 v5.4.1 cho Windows (76 MB) |
| `D:\xetulai\_platformio\kiem_qemu`, `kiem_probe`, `kiem_pwm`, `kiem_v3_*` | bản sao firmware, ảnh, log của các lượt thử 29/09/2026. Log được dẫn trong tài liệu này đã chép vào bằng chứng (mục 7); phần còn lại (ảnh 8–16 MB, bản build) xóa được khi không cần tái hiện |
| `D:\xetulai\_platformio\giu_lai` | mã nguồn hai bản thử lớp giả trên máy tính (mục 2.6) và cầu rfc2217, chép từ thư mục tạm trước khi dọn |

esp-emulator và esp32sim được tải vào thư mục tạm của phiên làm việc, không cài vào hệ thống. esp-emulator chỉ có bản
Linux: tác tử chép nó vào `/tmp` của WSL (Ubuntu 24.04 có sẵn trên máy) rồi chạy từ đó. Kiểm ngày 30/09/2026: bản sao đó
đã mất sau khi WSL dừng, còn thư mục tạm của phiên đã xóa khi dọn ổ C ([CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 8).

## 7. Bằng chứng

Thư mục [evidence/mo_phong_20260930/](evidence/mo_phong_20260930/):
- [nghien_cuu/ket_qua_workflow_20260929.json](evidence/mo_phong_20260930/nghien_cuu/ket_qua_workflow_20260929.json): 5
  báo cáo nghiên cứu (mỗi công cụ 13 tiêu chí kèm URL nguồn), 5 lượt phản biện (247 khẳng định: xác nhận / bác bỏ / chưa
  rõ, kèm sửa), báo cáo thử QEMU (`probe`), danh sách chỗ thiếu và 21 câu trả lời bổ sung.
- [qemu_espressif_29092026/](evidence/mo_phong_20260930/qemu_espressif_29092026/): log và báo cáo của lượt thử QEMU với
  firmware thật, cùng hai script đã dùng (`qemu_probe.py`, `qemu_monitor.py`).
- [so_sanh_29092026/](evidence/mo_phong_20260930/so_sanh_29092026/): cùng một sketch thử
  ([sketch_thu_gia_lap_main.cpp](evidence/mo_phong_20260930/so_sanh_29092026/sketch_thu_gia_lap_main.cpp), KHÔNG phải
  firmware xe) trên QEMU Espressif, a159x36, esp-emulator; lượt esp-emulator với firmware xe (`esp_emulator/firmware_xe/`);
  các lần QEMU tự thoát và chế độ TCG đơn luồng (`qemu_espressif/qemu175_va_tcg_don_luong/`); esp-idf-monitor; log
  esp32sim; cầu rfc2217; hai bản thử lớp giả trên máy tính (`lop_gia_pc/`). Tệp `trich_nhat_ky_tac_tu*.txt` là đầu ra
  trích nguyên văn từ nhật ký tác tử, cho các số không có log gốc riêng.
- [bo_ao_30092026/](evidence/mo_phong_20260930/bo_ao_30092026/): `kiem` và chạy lặp test bo ảo (10:11–10:13, mã sau
  review), JUnit của test bo ảo và `vehicle_io` lúc 08:56 (mã trước review: 11 + 68 test; mã commit có 13 + 71), đo độ
  tin cậy khởi động, đo A/B ưu tiên tiến trình; `kiem_bo_ao_dem_rieng.txt`: hai lượt `kiem` đếm tách khung trước cửa sổ
  2 s (≈ 15:00, mã `ff4a018` + sửa cách đếm, chưa commit lúc chạy; mục 1).
- Trước khi commit (30/09/2026), đường dẫn hồ sơ người dùng Windows, mã phiên tác tử và tên các việc khác trên máy trong
  các tệp bằng chứng đã được thay bằng `%USERPROFILE%`, `<phiên>` và mô tả chung; ngoài ra nội dung giữ nguyên.
- Tệp có mã commit `ebbec83` (`kiem_bo_ao_ebbec83.txt`, `chay_lap_test_bo_ao_ebbec83.txt`, `pytest_venv*_ebbec83.xml`,
  `chay_tren_commit_ebbec83.txt`, script `chay_tren_commit.py`): chạy lại trên commit, cây làm việc sạch.
- `pytest_venv*_30092026*.xml`: toàn bộ bộ test ngày 30/09. [ecoqos_30092026/](evidence/mo_phong_20260930/ecoqos_30092026/):
  vì sao test ngân sách thời gian `uturn_w46` hỏng khi chạy từ tiến trình không cửa sổ. Cả hai được giải thích ở
  [CHUYEN_MAY_BAN.md](CHUYEN_MAY_BAN.md) mục 8.

## 8. Nguồn chính

- QEMU của Espressif: <https://github.com/espressif/qemu/releases/tag/esp-develop-9.2.2-20260417>; tài liệu
  <https://github.com/espressif/esp-toolchain-docs/tree/main/qemu>; lỗi <https://github.com/espressif/qemu/issues/169>,
  <https://github.com/espressif/qemu/pull/177>, <https://github.com/espressif/qemu/issues/175>.
- a159x36/qemu: <https://github.com/a159x36/qemu/releases/tag/v5.4.1>. esp32sim: <https://github.com/joakimeriksson/esp32sim>.
  esp-emulator: <https://github.com/espressif/esp-emulator> (issue #10).
- Wokwi: <https://docs.wokwi.com/guides/esp32>, <https://wokwi.com/pricing>, <https://wokwi.com/legal/terms>,
  <https://github.com/wokwi/wokwi-cli>.
- pytest-embedded: <https://github.com/espressif/pytest-embedded>. Renode: <https://github.com/renode/renode>. PICSimLab:
  <https://github.com/lcgamboa/picsimlab>. Velxio: <https://github.com/davidmonterocrespo24/velxio>.
- pyserial 3.5: <https://github.com/pyserial/pyserial/blob/v3.5/serial/urlhandler/protocol_socket.py> (`in_waiting`,
  `write`, `close`), <https://github.com/pyserial/pyserial/blob/v3.5/examples/rfc2217_server.py>.
- ESP-IDF 4.4 `esp_task_wdt.h` (bản trong gói Arduino 2.0.17: `framework-arduinoespressif32/tools/sdk/esp32s3/include/
  esp_system/include/esp_task_wdt.h`); `HWCDC.cpp` của Arduino-ESP32 2.0.17:
  <https://github.com/espressif/arduino-esp32/blob/2.0.17/cores/esp32/HWCDC.cpp>.
