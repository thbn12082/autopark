// Firmware ESP32-S3 cho xe mô hình tự đỗ — lớp dán Arduino quanh lõi portable (src/core).
//
// TRẠNG THÁI: ĐÃ BIÊN DỊCH (29/09/2026, PlatformIO, 0 cảnh báo: Arduino-ESP32 2.0.17 theo platformio.ini; thêm
// Arduino-ESP32 3.3.12 trên bản sao tạm; mỗi bản cả PWM tắt lẫn bật với chân giả, xem README). CHƯA NẠP, CHƯA CHẠY
// TRÊN BO NÀO: biên dịch chỉ chứng minh tên/chữ ký API đúng với core đó. Mọi hằng số phần cứng bên dưới là CHƯA CHỐT: chưa nhận MN300, chưa biết ESC/servo giao
// tiếp thế nào, chưa có sơ đồ chân bo thật. Mặc định AP_ENABLE_PWM_OUTPUTS = 0: KHÔNG chân nào được điều khiển,
// firmware chỉ nói giao thức, chạy máy trạng thái và gửi telemetry (effort/góc nó SẼ xuất ra).
//
// Luồng: USB CDC (Serial) -> VehicleCore::receive -> mỗi 10 ms VehicleCore::step -> (nếu bật) xung 50 Hz cho ESC
// và servo -> telemetry qua USB CDC. Đường dừng vật lý (E-stop cắt động lực) phải độc lập với firmware này; chân
// E-stop ở đây chỉ để firmware biết và chốt lỗi, không thay được phần cứng ngắt.
#include <Arduino.h>
#include <esp_system.h>
#include <esp_task_wdt.h>
#include <esp_timer.h>
#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif
#if __has_include(<esp_random.h>)
#include <esp_random.h>
#endif

#include <atomic>

#include "core/vehicle_core.h"

#ifndef AP_ENABLE_PWM_OUTPUTS
#define AP_ENABLE_PWM_OUTPUTS 0
#endif

#if AP_ENABLE_PWM_OUTPUTS
#include <esp_rom_gpio.h>      // esp_rom_gpio_connect_out_signal: hàm ROM, gọi được trong panic
#include <soc/gpio_reg.h>      // GPIO_OUT_W1TC_REG, GPIO_ENABLE_W1TS_REG, ...
#include <soc/gpio_sig_map.h>  // SIG_GPIO_OUT_IDX
#include <soc/soc.h>           // REG_WRITE
#endif

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
#define AP_ARDUINO_V3 1
#else
#define AP_ARDUINO_V3 0
#endif

namespace {

// ===================== CHƯA CHỐT theo bo thực (đo/đối chiếu ở giai đoạn 4-5 rồi mới điền) =====================
constexpr int kPinEsc = -1;                // chân xung ESC
constexpr int kPinServo = -1;              // chân xung servo lái
constexpr int kPinEstop = -1;              // chân đọc trạng thái nút E-stop (chỉ để báo/chốt lỗi)
// E-stop AN TOÀN KHI HỞ MẠCH: tiếp điểm NC (loại mở cưỡng bức, khối NC của nút) nối giữa chân và GND, điện trở kéo
// LÊN (trong ≈ 45 kΩ; nên thêm 4,7–10 kΩ ngoài lên 3V3 ngay tại bo vì dây đi cạnh ESC/động cơ). Nhả nút: NC đóng, chân
// LOW. Nhấn nút, đứt dây, tuột đầu nối: chân HIGH = E-stop → FAULT. Cắm nhầm tiếp điểm NO thì xe luôn ở FAULT (hướng
// an toàn). setup() luôn đặt điện trở kéo về phía mức TÍCH CỰC, nên kiểu đấu ngược (kEstopActiveLow = true) chỉ an
// toàn khi đi kèm NC nối 3V3 + kéo xuống; kiểu "kéo về phía không nhấn" (đứt dây = nhả) không cấu hình được nữa.
constexpr bool kEstopActiveLow = false;    // false: HIGH = nhấn HOẶC đứt dây (NC nối GND, kéo lên)
constexpr uint32_t kPwmHz = 50;            // chu kỳ 20 ms, kiểu RC phổ biến — chưa xác nhận với ESC/servo thật
constexpr uint8_t kPwmBits = 14;           // ESP32-S3 LEDC tối đa 14 bit
constexpr int kEscNeutralUs = 1500;        // xung trung tính ESC
constexpr int kEscSpanUs = 500;            // effort ±1000 ‰ -> ±kEscSpanUs
constexpr int kEscDirection = 1;           // +1/-1: chiều tiến của ESC
constexpr int kServoCenterUs = 1500;       // xung servo khi góc lái 0 (từ steering_calibration.yaml)
constexpr int kServoUsPerRad = 1000;       // µs trên mỗi rad góc lái tương đương
constexpr int kServoDirection = 1;         // +1/-1: dương = rẽ trái
constexpr int kServoMinUs = 1000;          // giới hạn cơ khí servo
constexpr int kServoMaxUs = 2000;
// ===============================================================================================================

constexpr uint32_t kTickMs = 10;               // chu kỳ điều khiển
constexpr uint32_t kTaskWatchdogMs = 300;      // treo vòng loop lâu hơn -> chip khởi động lại (Arduino 3.x)
constexpr uint32_t kOutputGuardMs = 100;       // loop im lặng lâu hơn -> bộ hẹn giờ ép ESC về trung tính
constexpr uint8_t kEscChannel = 0;             // chỉ dùng với Arduino 2.x (API ledc theo kênh)
constexpr uint8_t kServoChannel = 1;

#if AP_ENABLE_PWM_OUTPUTS
static_assert(kPinEsc >= 0 && kPinServo >= 0 && kPinEstop >= 0,
              "CHUA CHOT: dat chan ESC/servo/E-stop da doi chieu voi so do day truoc khi bat AP_ENABLE_PWM_OUTPUTS");
static_assert(kPinEsc <= 48, "ESP32-S3 chi co GPIO 0..48 (esc_line_low_now ghi thanh ghi theo so chan)");
#endif

ap::VehicleCore g_core;
uint32_t g_next_tick_ms = 0;
// loop() (lõi 1) ghi, output_guard (tác vụ esp_timer, lõi 0) đọc: atomic để thứ tự đọc/ghi giữa hai lõi có nghĩa.
std::atomic<uint32_t> g_last_loop_ms{0};
volatile bool g_outputs_attached = false;
esp_timer_handle_t g_guard_timer = nullptr;

uint32_t pulse_to_duty(int pulse_us) {
  const uint32_t period_us = 1000000u / kPwmHz;
  const uint32_t max_duty = (1u << kPwmBits) - 1u;
  return static_cast<uint32_t>(static_cast<uint64_t>(pulse_us) * max_duty / period_us);
}

[[maybe_unused]] void pwm_attach(int pin, uint8_t channel) {
#if AP_ARDUINO_V3
  (void)channel;
  ledcAttach(static_cast<uint8_t>(pin), kPwmHz, kPwmBits);
#else
  ledcSetup(channel, kPwmHz, kPwmBits);
  ledcAttachPin(static_cast<uint8_t>(pin), channel);
#endif
}

void pwm_write_us(int pin, uint8_t channel, int pulse_us) {
#if AP_ARDUINO_V3
  (void)channel;
  ledcWrite(static_cast<uint8_t>(pin), pulse_to_duty(pulse_us));
#else
  (void)pin;
  ledcWrite(channel, pulse_to_duty(pulse_us));
#endif
}

[[maybe_unused]] int esc_pulse_us(int32_t effort_permille) {
  return kEscNeutralUs + kEscDirection * static_cast<int>(effort_permille * kEscSpanUs / 1000);
}

[[maybe_unused]] int servo_pulse_us(int32_t steer_mrad) {
  const long us = kServoCenterUs + kServoDirection * static_cast<long>(steer_mrad) * kServoUsPerRad / 1000;
  return static_cast<int>(us < kServoMinUs ? kServoMinUs : (us > kServoMaxUs ? kServoMaxUs : us));
}

void setup_outputs() {
#if AP_ENABLE_PWM_OUTPUTS
  pwm_attach(kPinEsc, kEscChannel);
  pwm_attach(kPinServo, kServoChannel);
  pwm_write_us(kPinEsc, kEscChannel, kEscNeutralUs);       // trung tính ngay khi khởi động
  pwm_write_us(kPinServo, kServoChannel, kServoCenterUs);
  g_outputs_attached = true;
#endif
}

void apply_outputs(const ap::Outputs& out) {
#if AP_ENABLE_PWM_OUTPUTS
  pwm_write_us(kPinEsc, kEscChannel, esc_pulse_us(out.effort_permille));
  pwm_write_us(kPinServo, kServoChannel, servo_pulse_us(out.steer_ref_mrad));
#else
  (void)out;
#endif
}

// Chạy trong tác vụ esp_timer (ưu tiên cao hơn loop): nếu loop không chạy quá kOutputGuardMs thì ép ESC trung
// tính. Lý do: LEDC tiếp tục phát xung cuối cùng khi CPU treo, và ESC không coi xung đều là mất tín hiệu.
// Watchdog/panic chỉ reset CPU, không dừng LEDC; khi ngắt bị tắt (tác vụ này không chạy) chỉ còn hook panic
// (esc_line_low_now) và E-stop phần cứng.
// g_last_loop_ms do loop() ghi trên lõi khác (Arduino loop: lõi 1; tác vụ esp_timer: lõi 0), không có thứ tự với lời
// gọi millis() ở đây. Vì vậy: (1) đọc last TRƯỚC khi gọi millis() — millis() là bộ đếm chung đơn điệu nên last <= now;
// (2) so bằng hiệu CÓ DẤU: nếu loop vừa ghi một mốc mới hơn "now" thì hiệu âm, nghĩa là loop còn sống, không ép. Viết
// `millis() - g_last_loop_ms` trong một biểu thức thì thứ tự tính hai toán hạng không được C++ quy định, và hiệu
// không dấu quay vòng thành ≈ 2^32 > 100 → ép trung tính giữa lúc chạy bình thường. Hiệu int32 vẫn đúng qua mốc tràn
// 2^32 ms của millis() với mọi khoảng im < 2^31 ms; task watchdog khởi động lại chip sớm hơn rất nhiều.
void output_guard(void*) {
  if (!g_outputs_attached) {
    return;
  }
  const uint32_t last = g_last_loop_ms.load(std::memory_order_acquire);  // trước millis(): không đổi thứ tự được
  const uint32_t now = millis();
  const int32_t silent_ms = static_cast<int32_t>(now - last);
  if (silent_ms > static_cast<int32_t>(kOutputGuardMs)) {
    pwm_write_us(kPinEsc, kEscChannel, kEscNeutralUs);
  }
}

// ---- Reset CPU không dừng LEDC --------------------------------------------------------------------------------------
// Panic (abort, ngoại lệ, tràn stack), interrupt watchdog, task watchdog (trigger_panic) và esp_restart() trên
// ESP32-S3 với Arduino chỉ reset CPU (esp_restart_noos): LEDC và ma trận GPIO KHÔNG bị reset, và clk init sau reset
// CPU giữ các xung nhịp đang bật. Không làm gì thì xung ga cuối cùng tiếp tục suốt lúc in panic, ghi coredump, ROM,
// bootloader, initArduino, cho tới setup_outputs(). CPU chạy lại bằng XTAL nên APB có thể về 40 MHz và độ rộng xung
// LEDC có thể bị nhân đôi (1500 → ≈ 3000 µs): CẦN ĐO. Vì vậy, trong panic và trước esp_restart(): tách chân ESC khỏi
// LEDC và kéo xuống thấp (MẤT xung). Không ghi duty trung tính vì duty ở pha XTAL không đáng tin. Chân giữ thấp qua
// reset CPU tới khi setup_outputs() nối lại LEDC và ghi trung tính.
// Không phủ: bật nguồn/system reset/sụt áp (chân thả nổi lúc khởi động → cần điện trở kéo xuống ngoài, ví dụ ≈ 10 kΩ,
// trên dây tín hiệu ESC), treo cứng không vào được panic. Servo: có kéo thấp hay không là CHƯA CHỐT (giữ nguyên).
// Hành vi ESC khi mất xung: CHƯA CHỐT. Chỉ dùng thanh ghi và hàm ROM, nằm trong IRAM: gọi được khi cache flash tắt.
// CHƯA ĐO: xem README, "Trình tự thử trên bo", bước 2. (Biên dịch 29/09/2026 với chân giả: nằm ở IRAM, chỉ ghi thanh
// ghi và gọi esp_rom_gpio_connect_out_signal trong ROM — kiểm bằng objdump, cả 2.0.17 lẫn 3.3.12.)
[[maybe_unused]] IRAM_ATTR void esc_line_low_now() {
#if AP_ENABLE_PWM_OUTPUTS
  const uint32_t bit = 1u << (static_cast<uint32_t>(kPinEsc) & 31u);
  if (kPinEsc < 32) {
    REG_WRITE(GPIO_OUT_W1TC_REG, bit);       // mức ra = 0 TRƯỚC khi đổi nguồn tín hiệu: không có gai lên
    REG_WRITE(GPIO_ENABLE_W1TS_REG, bit);
  } else {
    REG_WRITE(GPIO_OUT1_W1TC_REG, bit);
    REG_WRITE(GPIO_ENABLE1_W1TS_REG, bit);
  }
  // Như gpio_output_enable() của ESP-IDF: chân lấy tín hiệu từ thanh ghi GPIO_OUT thay vì LEDC.
  esp_rom_gpio_connect_out_signal(static_cast<uint32_t>(kPinEsc), SIG_GPIO_OUT_IDX, false, false);
#endif
}

#if AP_ARDUINO_V3
// Arduino-ESP32 3.x: __wrap_esp_panic_handler của lõi (esp32-hal-misc.c) gọi hàm đăng ký bằng set_arduino_panic_handler()
// trước trình xử lý panic mặc định — CHỈ KHI liên kết có -Wl,--wrap=esp_panic_handler. Arduino IDE thêm cờ đó
// (platform.txt); PlatformIO/pioarduino 55.3.312 thì KHÔNG: không có cờ trong platformio.ini thì móc này không bao giờ
// được gọi (kiểm 29/09/2026 bằng objdump: panic_handler gọi thẳng esp_panic_handler). Trước móc, lõi còn dựng
// backtrace (handle_custom_backtrace, chạy từ flash), nên chân ESC xuống thấp muộn hơn bản 2.x: CẦN ĐO.
[[maybe_unused]] IRAM_ATTR void ap_on_panic(arduino_panic_info_t*, void*) { esc_line_low_now(); }
#endif

void setup_reset_hooks() {
#if AP_ENABLE_PWM_OUTPUTS
#if AP_ARDUINO_V3
  set_arduino_panic_handler(ap_on_panic, nullptr);
#endif
  // esp_restart()/ESP.restart(): chạy trước khi reset CPU. Arduino 2.x: panic đi qua __wrap_esp_panic_handler (dưới).
  (void)esp_register_shutdown_handler(&esc_line_low_now);
#endif
}

void start_output_guard() {
  esp_timer_create_args_t args = {};
  args.callback = &output_guard;
  args.name = "ap_out_guard";
  if (esp_timer_create(&args, &g_guard_timer) == ESP_OK) {
    esp_timer_start_periodic(g_guard_timer, 10 * 1000);
  }
}

void setup_task_watchdog() {
#if AP_ARDUINO_V3
  esp_task_wdt_config_t config = {};
  config.timeout_ms = kTaskWatchdogMs;
  config.idle_core_mask = 0;
  config.trigger_panic = true;
  if (esp_task_wdt_reconfigure(&config) != ESP_OK) {
    esp_task_wdt_init(&config);
  }
#else
  // IDF 4.4: đơn vị giây. Arduino 2.0.17 đã khởi tạo TWDT sẵn (5 s, sdkconfig); khi đó esp_task_wdt_init() ĐỔI thời
  // hạn và chế độ panic chứ không báo lỗi (esp_task_wdt.h của IDF 4.4). Sửa 30/09/2026, trước đó ghi nhầm "trả lỗi, giữ
  // 5 s". Kiểm 29/09/2026: thanh ghi TIMG0 của bản build này trong QEMU = 1 s (tầng ngắt) / 2 s (tầng reset hệ thống).
  // esp-emulator: một sketch thử (KHÔNG phải firmware này) gọi cùng esp_task_wdt_init(1, true) bị TWDT kích hoạt
  // ≈ 1,2 s sau khi loop() treo (docs/MO_PHONG_FIRMWARE.md mục 2.4). Firmware này CHƯA THỬ treo trong trình giả lập có
  // watchdog; trên bo thật: CẦN KIỂM.
  esp_task_wdt_init(1, true);
#endif
  esp_task_wdt_add(nullptr);
}

ap::ResetReason map_reset_reason(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_POWERON: return ap::ResetReason::PowerOn;
    case ESP_RST_SW: return ap::ResetReason::Software;
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT: return ap::ResetReason::Watchdog;
    case ESP_RST_BROWNOUT: return ap::ResetReason::Brownout;
    case ESP_RST_UNKNOWN: return ap::ResetReason::Unknown;
    default: return ap::ResetReason::Other;
  }
}

ap::Inputs read_inputs() {
  ap::Inputs in;
  if (kPinEstop >= 0) {
    const int level = digitalRead(static_cast<uint8_t>(kPinEstop));
    in.estop = kEstopActiveLow ? (level == LOW) : (level == HIGH);
  }
  // CHƯA CÓ cảm biến: encoder/MT6701 (tốc độ), AS5600 (góc lái), BNO085 (IMU), VL53L1X (ToF), đo điện áp.
  // Tất cả để *_valid = false: telemetry báo "không có số đo", vòng tốc độ chạy feedforward hở.
  return in;
}

void read_host_bytes(uint32_t now) {
  uint8_t buffer[64];
  int available = Serial.available();
  while (available > 0) {
    const size_t want = available < static_cast<int>(sizeof(buffer)) ? static_cast<size_t>(available) : sizeof(buffer);
    const size_t got = Serial.read(buffer, want);
    if (got == 0) {
      break;
    }
    g_core.receive(buffer, got, now);
    available = Serial.available();
  }
}

void flush_tx() {
  const size_t pending = g_core.tx_size();
  if (pending == 0) {
    return;
  }
  if (!Serial) {
    g_core.tx_clear();   // không có máy chủ USB: bỏ, tránh gửi telemetry cũ khi cắm lại (laptop thấy khoảng hở)
    return;
  }
  const int room = Serial.availableForWrite();
  if (room <= 0) {
    return;
  }
  const size_t n = Serial.write(g_core.tx_data(), pending < static_cast<size_t>(room) ? pending : static_cast<size_t>(room));
  g_core.tx_consume(n);
}

}  // namespace

#if !AP_ARDUINO_V3
// Arduino-ESP32 2.x (ESP-IDF 4.4) không có móc panic cho người dùng: bọc esp_panic_handler bằng cờ liên kết
// -Wl,--wrap=esp_panic_handler (platformio.ini). Định nghĩa luôn có mặt (kể cả khi AP_ENABLE_PWM_OUTPUTS=0, khi đó
// esc_line_low_now không làm gì) vì cờ liên kết không phụ thuộc cờ biên dịch. Chuyển sang 3.x (pioarduino) thì nhánh
// này tắt và dùng set_arduino_panic_handler, nhưng VẪN GIỮ cờ --wrap (lõi 3.x tự định nghĩa __wrap, xem ap_on_panic).
// Biên dịch 29/09/2026 (2.0.17): panic_handler của IDF gọi hàm này, hàm này gọi esp_panic_handler thật (objdump).
// Móc có thật sự chạy lúc panic hay không vẫn phải đo trên bo (abort() trong loop).
extern "C" void __real_esp_panic_handler(void* info);
extern "C" IRAM_ATTR void __wrap_esp_panic_handler(void* info) {
  esc_line_low_now();
  __real_esp_panic_handler(info);
}
#endif

void setup() {
  setup_outputs();                                       // trung tính trước mọi việc khác
  setup_reset_hooks();                                   // panic/esp_restart: kéo chân ESC xuống thấp (mất xung)
  if (kPinEstop >= 0) {
    // Điện trở kéo về phía mức TÍCH CỰC: hở mạch (đứt dây/tuột đầu nối) đọc là "đang nhấn" → FAULT, không bao giờ là
    // "nhả". Lõi chốt FAULT ở mọi trạng thái kể cả BOOT, nên khởi động khi đầu nối đang tuột cũng vào FAULT.
    pinMode(static_cast<uint8_t>(kPinEstop), kEstopActiveLow ? INPUT_PULLDOWN : INPUT_PULLUP);
  }
  Serial.begin(115200);                                  // USB CDC: baudrate không có ý nghĩa
#if defined(ARDUINO_USB_MODE) && ARDUINO_USB_MODE == 1 && defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
  Serial.setTxTimeoutMs(0);                              // HWCDC: không chặn loop khi laptop không đọc
#endif
  uint32_t boot_id = esp_random() ^ static_cast<uint32_t>(esp_timer_get_time());
  if (boot_id == 0) {
    boot_id = 1;
  }
  ap::Config config;                                     // mặc định = FirmwareConfig() của bản tham chiếu Python
  const uint32_t now = millis();
  g_core.begin(config, now, boot_id, map_reset_reason(esp_reset_reason()));
  g_next_tick_ms = now;
  g_last_loop_ms.store(now, std::memory_order_release);
  setup_task_watchdog();
  start_output_guard();
}

void loop() {
  const uint32_t now = millis();
  g_last_loop_ms.store(now, std::memory_order_release);  // mốc này luôn <= millis() mà output_guard đọc sau nó
  read_host_bytes(now);
  if (static_cast<int32_t>(now - g_next_tick_ms) >= 0) {
    g_next_tick_ms += kTickMs;
    if (static_cast<int32_t>(now - g_next_tick_ms) >= 0) {
      g_next_tick_ms = now + kTickMs;                    // trễ nhiều chu kỳ: không chạy bù; lõi tự báo LOOP_OVERRUN
    }
    const ap::Outputs out = g_core.step(now, read_inputs());
    apply_outputs(out);
  }
  flush_tx();
  esp_task_wdt_reset();
}
