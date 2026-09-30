"""Kiểm tĩnh mã firmware C++ (biên dịch được từ 29/09/2026 nhưng chưa chạy trên bo; lõi: test_transport_firmware_host).

Các test ở đây đọc mã nguồn trong `firmware/esp32_vehicle` và kiểm những điều vector mẫu chung không phủ được: lớp
dán Arduino (`src/main.cpp`: bộ hẹn giờ ép trung tính, E-stop, móc panic) và sự khớp tay giữa cấu hình/enum C++ với
bản tham chiếu Python. Chúng KHÔNG thay cho biên dịch, `test/host` hay đo trên bo; chúng chỉ chặn việc quay lại đúng
các lỗi đã biết. Đổi cấu trúc mã thì phải sửa test theo (test báo "không tìm thấy" chứ không đạt cho có)."""
import configparser
import re

import pytest

from autopark.transport import protocol
from autopark.transport.firmware_model import FirmwareConfig
from autopark.transport.vectors import DEFAULT_PATH

FIRMWARE = DEFAULT_PATH.parents[1]
MAIN_CPP = FIRMWARE / "src" / "main.cpp"
CORE = FIRMWARE / "src" / "core"


def _code(path) -> str:
    """Mã nguồn đã bỏ chú thích (chú thích trong các file này có nhắc lại đúng những mẫu lỗi cần cấm)."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _body(code: str, signature: str) -> str:
    """Thân hàm (giữa cặp ngoặc nhọn khớp nhau) của định nghĩa đầu tiên khớp `signature` (regex)."""
    match = re.search(signature + r"[^;{]*\{", code)
    assert match, f"không tìm thấy định nghĩa {signature!r}"
    depth, start = 1, match.end()
    for i in range(start, len(code)):
        depth += {"{": 1, "}": -1}.get(code[i], 0)
        if depth == 0:
            return code[start:i]
    raise AssertionError(f"ngoặc không khớp trong {signature!r}")


# ---- lõi C++ khớp bản tham chiếu Python --------------------------------------------------------------------------
def test_cpp_config_defaults_match_python_reference():
    """main.cpp dùng `ap::Config` mặc định; nó phải bằng FirmwareConfig() (kể cả trần effort và STALL)."""
    struct = re.search(r"struct Config \{(.*?)\n\};", _code(CORE / "vehicle_core.h"), flags=re.S)
    assert struct
    fields = dict(re.findall(r"(?:int32_t|bool|uint8_t)\s+(\w+)\s*=\s*([^;]+);", struct.group(1)))
    cpp = {name: (value == "true") if value in ("true", "false") else int(value) for name, value in fields.items()}
    assert cpp == FirmwareConfig().to_dict()


def test_cpp_host_test_reads_every_config_key():
    """test/host/test_main.cpp chết với "unknown config key" nếu thiếu khóa mà vectors.json có."""
    code = _code(FIRMWARE / "test" / "host" / "test_main.cpp")
    keys = set(re.findall(r'\{"(\w+)",\s*&ap::Config::(\w+)\}', code))
    assert all(a == b for a, b in keys)
    handled = {a for a, _ in keys} | set(re.findall(r'member\.first == "(\w+)"', code))
    assert handled == set(FirmwareConfig().to_dict())


def test_cpp_enums_match_python_protocol():
    code = _code(CORE / "protocol.h")
    enums = {name: body for name, body in re.findall(r"enum class (\w+) : uint8_t \{([^}]*)\}", code)}
    for name in ("MsgType", "State", "Fault", "StopReason", "Result", "Action", "ResetReason"):
        cpp = {re.sub(r"(?<!^)(?=[A-Z])", "_", k).upper(): int(v, 0)
               for k, v in re.findall(r"(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)", enums[name])}
        assert cpp == {m.name: int(m) for m in getattr(protocol, name)}, name


def test_cpp_speed_loop_uses_effort_cap_and_step_checks_stall():
    code = _code(CORE / "vehicle_core.cpp")
    loop = _body(code, r"void VehicleCore::update_speed_loop\(int32_t dt\)")
    assert "cfg_.max_effort_permille" in loop and not re.search(r"-1000\s*,\s*1000", loop)
    step = _body(code, r"Outputs VehicleCore::step\(uint32_t now_ms, const Inputs& in\)")
    assert re.search(r"update_speed_loop\(dt\);\s*check_stall\(now\);", step)       # như FirmwareModel.step
    stall = _body(code, r"void VehicleCore::check_stall\(uint32_t now\)")
    assert "Fault::Stall" in stall and "cfg_.stall_timeout_ms" in stall and "cfg_.stall_effort_permille" in stall


# ---- main.cpp: bộ hẹn giờ ép trung tính ----------------------------------------------------------------------------
def _u32(x: int) -> int:
    return x & 0xFFFFFFFF


def _i32(x: int) -> int:
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x >= 1 << 31 else x


@pytest.mark.parametrize("last, now, should_fire", [
    (1000, 1050, False), (1000, 1101, True),
    (1001, 1000, False),                                # loop (lõi khác) vừa ghi mốc mới hơn "now" mà guard đọc
    (0xFFFFFFF0, 5, False), (0xFFFFFFF0, 200, True),    # millis() quay vòng qua 2^32
])
def test_output_guard_reads_loop_stamp_before_clock_and_compares_signed(last, now, should_fire):
    """main.cpp: đọc g_last_loop_ms TRƯỚC millis() (hai câu lệnh riêng) và so hiệu int32. Hiệu không dấu cũ
    (`millis() - g_last_loop_ms > 100`) ép ESC trung tính khi loop vừa ghi mốc mới hơn — trường hợp (1001, 1000)."""
    body = _body(_code(MAIN_CPP), r"void output_guard\(void\*\)")
    assert not re.search(r"millis\(\)\s*-\s*g_last_loop_ms", _code(MAIN_CPP))
    load = re.search(r"const uint32_t last = g_last_loop_ms\.load\(std::memory_order_acquire\);", body)
    clock = re.search(r"const uint32_t now = millis\(\);", body)
    assert load and clock and load.start() < clock.start()
    diff = re.search(r"const int32_t (\w+) = static_cast<int32_t>\(now - last\);", body)
    assert diff and re.search(rf"if \({diff.group(1)} > static_cast<int32_t>\(kOutputGuardMs\)\)", body)
    guard_ms = int(re.search(r"kOutputGuardMs = (\d+);", _code(MAIN_CPP)).group(1))
    assert (_i32(now - last) > guard_ms) == should_fire                  # phép so như main.cpp (int32)
    if (last, now) == (1001, 1000):
        assert _u32(now - last) > guard_ms                               # phép so không dấu cũ: ép nhầm


# ---- main.cpp: E-stop an toàn khi hở mạch ---------------------------------------------------------------------------
def test_estop_input_reads_pressed_when_wire_is_open_for_both_polarities():
    """Điện trở kéo phải đặt về phía mức TÍCH CỰC: đứt dây/tuột đầu nối (chân chỉ còn điện trở kéo) = đang nhấn."""
    code = _code(MAIN_CPP)
    default = re.search(r"constexpr bool kEstopActiveLow = (true|false);", code)
    assert default and default.group(1) == "false"                       # kiểu đấu chuẩn: NC nối GND + kéo lên
    pull = re.search(r"pinMode\(static_cast<uint8_t>\(kPinEstop\),\s*kEstopActiveLow \? (INPUT_\w+) : (INPUT_\w+)\)",
                     code)
    read = re.search(r"in\.estop = kEstopActiveLow \? \(level == (LOW|HIGH)\) : \(level == (LOW|HIGH)\);", code)
    assert pull and read
    for active_low, k in ((True, 1), (False, 2)):
        open_level = {"INPUT_PULLUP": "HIGH", "INPUT_PULLDOWN": "LOW"}[pull.group(k)]
        assert read.group(k) == open_level, f"kEstopActiveLow={active_low}: hở mạch đọc là 'không nhấn'"


# ---- main.cpp: reset CPU không dừng LEDC -----------------------------------------------------------------------------
def test_panic_and_restart_hooks_detach_esc_from_ledc_and_drive_it_low():
    code = _code(MAIN_CPP)
    assert re.search(r"IRAM_ATTR void esc_line_low_now\(\)", code)
    low = _body(code, r"IRAM_ATTR void esc_line_low_now\(\)")
    out_low = low.find("GPIO_OUT_W1TC_REG")
    connect = low.find("esp_rom_gpio_connect_out_signal(static_cast<uint32_t>(kPinEsc), SIG_GPIO_OUT_IDX")
    assert 0 <= out_low < connect                       # mức 0 trước, rồi mới lấy tín hiệu từ GPIO_OUT thay LEDC
    assert "GPIO_OUT1_W1TC_REG" in low and "ledcWrite" not in low and "pwm_write_us" not in low   # không ghi duty
    hooks = _body(code, r"void setup_reset_hooks\(\)")
    assert "set_arduino_panic_handler(ap_on_panic, nullptr)" in hooks                    # Arduino 3.x
    assert "esp_register_shutdown_handler(&esc_line_low_now)" in hooks                   # esp_restart()
    wrap = _body(code, r'extern "C" IRAM_ATTR void __wrap_esp_panic_handler\(void\* info\)')   # Arduino 2.x
    assert 0 <= wrap.find("esc_line_low_now();") < wrap.find("__real_esp_panic_handler(info);")
    setup = _body(code, r"void setup\(\)")
    assert 0 <= setup.find("setup_outputs();") < setup.find("setup_reset_hooks();")
    # Từng env riêng: env esp32s3_qemu (bo ảo, 30/09/2026) ghi lại build_flags vì `extends` KHÔNG gộp build_flags, nên
    # tìm cờ ở bất kỳ dòng nào của tệp thì bản nạp vào xe mất cờ vẫn đạt.
    ini = configparser.ConfigParser(inline_comment_prefixes=(";",), interpolation=None)
    ini.read(FIRMWARE / "platformio.ini", encoding="utf-8")
    car, qemu = (ini[f"env:{env}"]["build_flags"].split() for env in ("esp32s3", "esp32s3_qemu"))
    assert "-Wl,--wrap=esp_panic_handler" in car                        # bản nạp vào xe
    # bo ảo chỉ khác bản nạp vào xe ở Serial (cờ dưới) và flash DIO (board_build.flash_mode, không phải build_flags)
    assert set(car) ^ set(qemu) == {"-DARDUINO_USB_CDC_ON_BOOT=1", "-DARDUINO_USB_CDC_ON_BOOT=0"}
