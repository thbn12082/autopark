// CHỈ ĐỂ THỬ TRÌNH GIẢ LẬP (29/09/2026) — KHÔNG phải firmware xe. Arduino-ESP32 2.0.17, console UART0 (dạng chữ).
// Đo khả năng của từng trình giả lập ESP32-S3 với đúng toolchain/cờ của dự án (espressif32 7.1.3, --wrap panic):
// lý do reset, TWDT/IWDT, móc panic, chân INPUT_PULLUP để hở, LEDC -> chân, esp_timer, đọc flash theo từng read_mode
// (QEMU issue #169), NVS qua các lần khởi động, tốc độ thời gian. Lệnh 1 ký tự qua UART0: W I A R L P M S.
#include <Arduino.h>
#include <Preferences.h>
#include <esp_flash.h>
#include <esp_rom_gpio.h>
#include <esp_rom_sys.h>
#include <esp_spi_flash.h>
#include <esp_system.h>
#include <esp_task_wdt.h>
#include <esp_timer.h>
#include <esp32s3/rom/rtc.h>
#include <soc/gpio_periph.h>
#include <soc/gpio_reg.h>
#include <soc/gpio_sig_map.h>
#include <soc/io_mux_reg.h>
#include <soc/ledc_reg.h>
#include <soc/soc.h>
#include <driver/periph_ctrl.h>

namespace {
constexpr int kPinPwm = 21;       // a159x36/qemu: servo model on GPIO21
constexpr int kPinPullup = 14;    // a159x36/qemu: button 2 (key '2') on GPIO14
constexpr int kPinPulldown = 5;
constexpr int kPinFloat = 6;
constexpr uint32_t kPwmHz = 50;
constexpr uint8_t kPwmBits = 14;

volatile uint32_t g_timer_cb = 0;
uint32_t g_boot_snapshot[8];

uint32_t duty_for_us(uint32_t us) { return static_cast<uint32_t>((uint64_t)us * ((1u << kPwmBits) - 1u) / (1000000u / kPwmHz)); }

void IRAM_ATTR timer_cb(void*) { g_timer_cb = g_timer_cb + 1; }
}  // namespace

RTC_NOINIT_ATTR uint32_t r_magic;
RTC_NOINIT_ATTR uint32_t r_boots;
RTC_NOINIT_ATTR uint32_t r_wrap;
RTC_NOINIT_ATTR uint32_t r_wrap_outsel;
RTC_NOINIT_ATTR uint32_t r_shutdown;
RTC_NOINIT_ATTR uint32_t r_last_cmd;

extern "C" void __real_esp_panic_handler(void* info);
extern "C" IRAM_ATTR void __wrap_esp_panic_handler(void* info) {
  const uint32_t bit = 1u << kPinPwm;
  REG_WRITE(GPIO_OUT_W1TC_REG, bit);
  REG_WRITE(GPIO_ENABLE_W1TS_REG, bit);
  esp_rom_gpio_connect_out_signal(kPinPwm, SIG_GPIO_OUT_IDX, false, false);
  r_wrap_outsel = REG_READ(GPIO_FUNC0_OUT_SEL_CFG_REG + 4 * kPinPwm);
  r_wrap = 0xC0DE0001;
  esp_rom_printf("\nPROBE_WRAP ran: outsel21=0x%x out=0x%x en=0x%x\n", r_wrap_outsel, REG_READ(GPIO_OUT_REG),
                 REG_READ(GPIO_ENABLE_REG));
  __real_esp_panic_handler(info);
}

static void IRAM_ATTR on_shutdown() {
  r_shutdown = 0x5D5D0001;
  esp_rom_printf("\nPROBE_SHUTDOWN handler ran\n");
}

static const char* reason_name(esp_reset_reason_t r) {
  switch (r) {
    case ESP_RST_UNKNOWN: return "UNKNOWN";
    case ESP_RST_POWERON: return "POWERON";
    case ESP_RST_EXT: return "EXT";
    case ESP_RST_SW: return "SW";
    case ESP_RST_PANIC: return "PANIC";
    case ESP_RST_INT_WDT: return "INT_WDT";
    case ESP_RST_TASK_WDT: return "TASK_WDT";
    case ESP_RST_WDT: return "WDT";
    case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
    case ESP_RST_BROWNOUT: return "BROWNOUT";
    case ESP_RST_SDIO: return "SDIO";
    default: return "?";
  }
}

static void print_pins() {
  pinMode(kPinPullup, INPUT_PULLUP);
  pinMode(kPinPulldown, INPUT_PULLDOWN);
  pinMode(kPinFloat, INPUT);
  delay(2);
  Serial.printf("PINS pullup14=%d pulldown5=%d float6=%d GPIO_IN=0x%08x\n", digitalRead(kPinPullup),
                digitalRead(kPinPulldown), digitalRead(kPinFloat), (unsigned)REG_READ(GPIO_IN_REG));
}

// QEMU (Espressif) has no LEDC model: ledcSetup() -> ledc_get_freq() divides by a register read as 0 and panics.
static bool ledc_modeled() {
  periph_module_enable(PERIPH_LEDC_MODULE);
  const uint32_t before = REG_READ(LEDC_LSTIMER0_CONF_REG);
  REG_WRITE(LEDC_LSTIMER0_CONF_REG, (256u << 4) | 14u);
  const uint32_t v = REG_READ(LEDC_LSTIMER0_CONF_REG);
  REG_WRITE(LEDC_LSTIMER0_CONF_REG, before);
  Serial.printf("LEDC probe: wrote 0x%x read 0x%08x\n", (256u << 4) | 14u, (unsigned)v);
  return (v & 0x3FFFFFu) == ((256u << 4) | 14u);
}

static void measure_pwm() {
  if (!ledc_modeled()) {
    Serial.println("LEDC NOT MODELLED: skipping ledcSetup (it would divide by zero)");
    return;
  }
  ledcSetup(0, kPwmHz, kPwmBits);
  ledcAttachPin(kPinPwm, 0);
  ledcWrite(0, duty_for_us(1500));
  PIN_INPUT_ENABLE(GPIO_PIN_MUX_REG[kPinPwm]);
  delay(25);
  Serial.printf("LEDC regs: ch0_conf0=0x%08x ch0_duty=0x%08x ch0_duty_r=0x%08x timer0_conf=0x%08x outsel21=0x%x\n",
                (unsigned)REG_READ(LEDC_LSCH0_CONF0_REG), (unsigned)REG_READ(LEDC_LSCH0_DUTY_REG),
                (unsigned)REG_READ(LEDC_LSCH0_DUTY_R_REG), (unsigned)REG_READ(LEDC_LSTIMER0_CONF_REG),
                (unsigned)REG_READ(GPIO_FUNC0_OUT_SEL_CFG_REG + 4 * kPinPwm));
  // Phân tích logic bằng phần mềm: lấy mẫu mức chân 21 qua GPIO_IN trong 60 ms.
  const int64_t t0 = esp_timer_get_time();
  int last = -1, rises = 0;
  int64_t high_us = 0, last_t = t0, first_rise = -1, last_rise = -1;
  uint32_t samples = 0;
  while (esp_timer_get_time() - t0 < 60000) {
    const int64_t t = esp_timer_get_time();
    const int v = (REG_READ(GPIO_IN_REG) >> kPinPwm) & 1;
    if (last == 1) high_us += t - last_t;
    if (last == 0 && v == 1) {
      ++rises;
      if (first_rise < 0) first_rise = t;
      last_rise = t;
    }
    last = v;
    last_t = t;
    ++samples;
  }
  Serial.printf("PWM pin21 sampled %u times/60ms: rises=%d high_total_us=%lld avg_period_us=%lld\n", (unsigned)samples,
                rises, (long long)high_us, rises > 1 ? (long long)((last_rise - first_rise) / (rises - 1)) : -1LL);
}

static void flash_modes_test() {
  const void* map_ptr = nullptr;
  spi_flash_mmap_handle_t handle;
  if (spi_flash_mmap(0, 0x10000, SPI_FLASH_MMAP_DATA, &map_ptr, &handle) != ESP_OK) {
    Serial.println("FLASH mmap failed");
    return;
  }
  const uint8_t* ref = static_cast<const uint8_t*>(map_ptr) + 0x8000;
  Serial.printf("FLASH mmap@0x8000: %02x %02x %02x %02x %02x %02x %02x %02x (default read_mode=%d)\n", ref[0], ref[1],
                ref[2], ref[3], ref[4], ref[5], ref[6], ref[7], (int)esp_flash_default_chip->read_mode);
  const esp_flash_io_mode_t saved = esp_flash_default_chip->read_mode;
  static const char* const names[] = {"SLOWRD", "FASTRD", "DOUT", "DIO", "QOUT", "QIO"};
  for (int m = SPI_FLASH_SLOWRD; m <= SPI_FLASH_QIO; ++m) {
    uint8_t buf[40] = {0};
    esp_flash_default_chip->read_mode = static_cast<esp_flash_io_mode_t>(m);
    const esp_err_t err = esp_flash_read(esp_flash_default_chip, buf, 0x8000, sizeof(buf));
    int shift = 99;
    for (int s = -4; s <= 4; ++s) {
      bool ok = true;
      for (int i = 8; i < 32; ++i) {
        if (buf[i] != ref[i - s]) { ok = false; break; }
      }
      if (ok) { shift = s; break; }
    }
    Serial.printf("FLASH esp_flash_read mode=%s err=%d first8=%02x %02x %02x %02x %02x %02x %02x %02x shift=%d\n",
                  names[m], (int)err, buf[0], buf[1], buf[2], buf[3], buf[4], buf[5], buf[6], buf[7], shift);
  }
  esp_flash_default_chip->read_mode = saved;
  spi_flash_munmap(handle);
}

void setup() {
  // Ảnh chụp thanh ghi NGAY khi khởi động, trước khi đụng tới LEDC/GPIO: trạng thái có sống qua reset CPU không.
  g_boot_snapshot[0] = REG_READ(GPIO_FUNC0_OUT_SEL_CFG_REG + 4 * kPinPwm);
  g_boot_snapshot[1] = REG_READ(GPIO_ENABLE_REG);
  g_boot_snapshot[2] = REG_READ(GPIO_OUT_REG);
  g_boot_snapshot[3] = REG_READ(LEDC_LSCH0_CONF0_REG);
  g_boot_snapshot[4] = REG_READ(LEDC_LSCH0_DUTY_R_REG);
  g_boot_snapshot[5] = REG_READ(LEDC_LSTIMER0_CONF_REG);
  Serial.begin(115200);
  delay(50);
  const bool warm = (r_magic == 0xA11CE5ED);
  if (!warm) {
    r_magic = 0xA11CE5ED;
    r_boots = 0;
    r_wrap = 0;
    r_shutdown = 0;
    r_last_cmd = 0;
    r_wrap_outsel = 0;
  }
  ++r_boots;
  const esp_reset_reason_t rr = esp_reset_reason();
  Serial.printf("\nPROBE v1 boot=%u rtc_mem_kept=%d reason=%s(%d) rom_reason0=%d rom_reason1=%d last_cmd=%c\n",
                (unsigned)r_boots, warm ? 1 : 0, reason_name(rr), (int)rr, (int)rtc_get_reset_reason(0),
                (int)rtc_get_reset_reason(1), r_last_cmd ? (char)r_last_cmd : '-');
  Serial.printf("MARKERS wrap=0x%08x wrap_outsel21=0x%x shutdown=0x%08x\n", (unsigned)r_wrap, (unsigned)r_wrap_outsel,
                (unsigned)r_shutdown);
  Serial.printf("BOOTREGS outsel21=0x%x gpio_en=0x%08x gpio_out=0x%08x ledc_ch0_conf0=0x%08x ledc_ch0_duty_r=0x%08x "
                "ledc_timer0=0x%08x\n",
                (unsigned)g_boot_snapshot[0], (unsigned)g_boot_snapshot[1], (unsigned)g_boot_snapshot[2],
                (unsigned)g_boot_snapshot[3], (unsigned)g_boot_snapshot[4], (unsigned)g_boot_snapshot[5]);
  r_wrap = 0;
  r_shutdown = 0;
  r_last_cmd = 0;
  Preferences prefs;
  const bool nvs_ok = prefs.begin("probe", false);
  uint32_t nvs_boots = nvs_ok ? prefs.getUInt("boots", 0) : 0;
  size_t put = nvs_ok ? prefs.putUInt("boots", nvs_boots + 1) : 0;
  prefs.end();
  Serial.printf("NVS begin=%d boots_before=%u put=%u\n", nvs_ok ? 1 : 0, (unsigned)nvs_boots, (unsigned)put);
  Serial.printf("RANDOM %08x %08x\n", (unsigned)esp_random(), (unsigned)esp_random());
  flash_modes_test();
  print_pins();
  (void)esp_register_shutdown_handler(&on_shutdown);
  const esp_err_t w1 = esp_task_wdt_init(1, true);
  const esp_err_t w2 = esp_task_wdt_add(nullptr);
  Serial.printf("TWDT init(1s,panic)=%d add=%d\n", (int)w1, (int)w2);
  esp_timer_create_args_t args = {};
  args.callback = &timer_cb;
  args.name = "probe";
  esp_timer_handle_t h;
  esp_timer_create(&args, &h);
  esp_timer_start_periodic(h, 10000);
  measure_pwm();
  Serial.println("READY");
}

void loop() {
  static uint32_t next_ms = millis() + 1000;
  static uint32_t last_cb = 0, last_ms = millis();
#ifdef PROBE_AUTO_CMD
  // For emulators whose UART RX cannot deliver single bytes (esp32sim has no RX-timeout interrupt): run one command
  // by itself, once, PROBE_AUTO_MS after the first power-on boot.
  static bool auto_fired = false;
  const bool auto_now = !auto_fired && r_boots == 1 && millis() >= PROBE_AUTO_MS;
  if (auto_now) {
    auto_fired = true;
    Serial.printf("AUTO command %c\n", (char)PROBE_AUTO_CMD);
  }
  if (Serial.available() || auto_now) {
    const int c = auto_now ? PROBE_AUTO_CMD : Serial.read();
#else
  if (Serial.available()) {
    const int c = Serial.read();
#endif
    if (c == 'W' || c == 'I' || c == 'A' || c == 'R') {
      r_last_cmd = static_cast<uint32_t>(c);
      Serial.printf("CMD %c at ms=%u\n", c, (unsigned)millis());
      Serial.flush();
      if (c == 'W') { while (true) { } }
      if (c == 'I') { portDISABLE_INTERRUPTS(); while (true) { } }
      if (c == 'A') { abort(); }
      if (c == 'R') { esp_restart(); }
    } else if (c == 'L') {
      measure_pwm();
    } else if (c == 'P') {
      print_pins();
    } else if (c == 'M') {
      flash_modes_test();
    } else if (c == 'S') {
      Serial.printf("STATUS ms=%u\n", (unsigned)millis());
    }
  }
  const uint32_t now = millis();
  if (static_cast<int32_t>(now - next_ms) >= 0) {
    next_ms += 1000;
    const uint32_t cb = g_timer_cb;
    Serial.printf("T ms=%u us=%lld timer_cb=%u (+%u in %u ms) pin14=%d\n", (unsigned)now,
                  (long long)esp_timer_get_time(), (unsigned)cb, (unsigned)(cb - last_cb), (unsigned)(now - last_ms),
                  digitalRead(kPinPullup));
    last_cb = cb;
    last_ms = now;
  }
  esp_task_wdt_reset();
}
