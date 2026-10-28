"""Bo ảo QEMU trong phiên đỗ: XE MÔ PHỎNG PHÍA LAPTOP (thêm 02/10/2026; người dùng giao quyết định 02/10/2026).

Firmware THẬT của xe (env `esp32s3_qemu`, `qemu_board`) chạy trong QEMU nhưng chưa đọc cảm biến nào (`read_inputs()`
của main.cpp để mọi cờ `*_valid` = 0): telemetry không có tốc độ, góc lái đo được, nên `VehicleLink` từ chối START (luật
bảo vệ bo thật, giữ nguyên). Để chạy cả phiên đỗ qua firmware thật mà KHÔNG nới luật đó và KHÔNG thêm mã mô phỏng vào
firmware, phía laptop có một xe mô phỏng (`LaptopPlant`: mô hình xe đạp động học `SimVehicle`, giới hạn của
`VehicleConfig`) bám tham chiếu `speed_ref`, `steer_ref` mà firmware báo trong telemetry. Tốc độ, góc lái "đo" và tư thế
lấy từ xe đó: đều là MÔ PHỎNG, không phải số đo.

- Không có byte hay thông điệp mới nào tới firmware: số của xe mô phỏng chỉ thay `speed_mps`, `steer_rad` của khung
  telemetry phía laptop (`QemuPlantVehicleIO._telemetry_from_message`); cờ của firmware giữ nguyên (telemetry.csv vẫn có
  SPEED_VALID = STEER_VALID = 0 trong khi cột speed_mps, steer_rad có số của xe mô phỏng).
- Firmware vẫn chạy mạch hở (effort = feedforward, trần 250 ‰): vòng PI, STALL, FEEDBACK_LOST KHÔNG được thử ở đây.
  Được thử, theo thời gian thực: phiên, số thứ tự, HELLO với chu kỳ telemetry xin, ARM, hạn lệnh, dốc tham chiếu, cổng
  đổi chiều, watchdog liên lạc, DISARM, CLEAR_FAULT, LOOP_OVERRUN khi máy bận.
- Chỉ nối tới `socket://127.0.0.1:<cổng>` của bo ảo do chính ứng dụng mở (`check_emulator_url`), và HELLO_ACK phải có
  đúng boot_id bo ảo báo lúc khởi động: cầu TCP tới một ESP32 thật chiếm cổng đó bị từ chối trước ARM.
- Bằng chứng `QEMU_EVIDENCE`, chỉ ở mức MP; KHÔNG nói gì về bo hay xe thật (docs/PHAN_CUNG_VA_HIEU_CHUAN.md).

Phương án khác đã loại (người dùng giao quyết định 02/10/2026): đưa cảm biến giả vào firmware (mã mô phỏng trong
firmware, đổi giao thức), ghi thẳng bộ nhớ chip ảo qua GDB/HMP, cho VehicleLink coi speed_ref là số đo (nới luật START),
mô hình ngoại vi QEMU (chưa có cho S3), lái xe mô phỏng theo `effort` (trần 250 ‰ cho ≤ 0,094 m/s với vùng chết giả định).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import random
import re
from typing import Callable, Protocol

from autopark.domain.types import Pose, VehicleConfig, VehicleState
from autopark.simulation.vehicle import SimVehicle

from .protocol import TelemetryMsg
from .vehicle_io import (STALE_MIN_PERIODS, U32, HelloInfo, SerialVehicleIO, VehicleIOError, VehicleTelemetry,
                         speed_from_wire, speed_to_wire, steer_from_wire, steer_to_wire)

ROOT = Path(__file__).resolve().parents[2]
QEMU_EVIDENCE = "qemu_firmware_simulated_vehicle"
QEMU_KIND = "bo ảo QEMU (firmware xe trong giả lập; KHÔNG phải bo thật)"
DEFAULT_PLANT_CONFIG = ROOT / "configs" / "bo_ao_qemu.json"
PLANT_SCHEMA_VERSION = 1
# Ngưỡng TELEMETRY_STALE của io bo ảo (bằng mặc định của VehicleIO; liên kết bo ảo không đổi nó).
QEMU_TELEMETRY_TIMEOUT_S = 0.3
# Chu kỳ telemetry xin trong HELLO (sửa 02/10/2026 theo review): firmware kẹp vào 20..1000 ms, nhưng VehicleIO đòi
# ngưỡng trên >= STALE_MIN_PERIODS chu kỳ nên chỉ nhận tới 100 ms. Trước đó tệp cấu hình nhận tới 1000 ms và mọi START
# với chu kỳ 101..1000 ms hỏng ở bước dựng io (START_ABORTED). 100 ms cũng giữ tuổi telemetry giữa hai khung dưới
# max_state_age_s 0,15 s của VehicleLink, nhưng ít dư; mặc định 20 ms.
MIN_TELEMETRY_PERIOD_MS = 20
MAX_TELEMETRY_PERIOD_MS = round(QEMU_TELEMETRY_TIMEOUT_S * 1000) // STALE_MIN_PERIODS
_EMULATOR_URL = re.compile(r"socket://127\.0\.0\.1:(\d{1,5})")
# Khóa hợp lệ của configs/bo_ao_qemu.json (góc theo độ, *_deg): khóa lạ hay gõ sai bị từ chối, như _SIM_IO_KEYS.
_PLANT_KEYS = {
    "": {"schema_version", "notes", "telemetry_period_ms", "plant"},
    "plant": {"step_ms", "speed_noise_std_mps", "steer_noise_std_deg", "seed"},
}


class QemuBoardHandle(Protocol):
    """Bo ảo đang chạy mà io nối tới: `qemu_board.QemuBoard` (giao diện: `ui/qemu_runner.py`), bo giả trong test."""

    url: str                                  # socket://127.0.0.1:<cổng> (UART0)
    hello: HelloInfo | None                   # HELLO_ACK lúc khởi động (boot_id của chip ảo này)
    clock: Callable[[], float] | None         # None: io theo đồng hồ của liên kết; test truyền ManualClock

    def running(self) -> bool: ...

    def transport_opener(self) -> Callable[[], object]: ...

    def describe(self) -> dict: ...


def check_emulator_url(url) -> int:
    """Cổng TCP của URL bo ảo; chỉ nhận đúng `socket://127.0.0.1:<1..65535>` (bo ảo do chính ứng dụng mở trên máy này).
    COMx, rfc2217://, máy khác, `localhost`, cổng 0 → ValueError."""
    match = _EMULATOR_URL.fullmatch(url) if isinstance(url, str) else None
    port = int(match.group(1)) if match else 0
    if not 1 <= port <= 65535:
        raise ValueError(f"Bo ảo QEMU chỉ nối tới socket://127.0.0.1:<cổng> do chính ứng dụng mở (đang là {url!r})")
    return port


def _check_keys(section: str, mapping) -> None:
    if not isinstance(mapping, dict):
        raise ValueError(f"{section or 'mức ngoài'}: phải là một đối tượng JSON")
    unknown = set(mapping) - _PLANT_KEYS[section]
    if unknown:
        raise ValueError(f"khóa lạ trong {section or 'mức ngoài'} của cấu hình bo ảo: {sorted(unknown)}")


def _number(mapping: dict, key: str, default: float) -> float:
    value = mapping.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} phải là số (đang là {value!r})")
    return float(value)


@dataclass(frozen=True)
class PlantConfig:
    """Tham số của liên kết bo ảo và của xe mô phỏng phía laptop (configs/bo_ao_qemu.json). Đều là GIẢ ĐỊNH của mô
    phỏng, không phải số đo; ghi vào link.json (khóa "plant")."""

    telemetry_period_ms: int = 20             # xin trong HELLO, 20..100 ms (MAX_TELEMETRY_PERIOD_MS): tư thế mới 50 Hz
    step_ms: int = 5                          # bước tích phân lớn nhất của xe mô phỏng
    speed_noise_std_mps: float = 0.0          # nhiễu Gauss thêm vào tốc độ "đo"
    steer_noise_std_rad: float = 0.0          # nhiễu Gauss thêm vào góc lái "đo"
    seed: int = 0
    notes: str = ""

    def __post_init__(self):
        for name in ("telemetry_period_ms", "step_ms", "seed"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} phải là số nguyên (đang là {value!r})")
        if not MIN_TELEMETRY_PERIOD_MS <= self.telemetry_period_ms <= MAX_TELEMETRY_PERIOD_MS:
            raise ValueError(f"telemetry_period_ms phải trong [{MIN_TELEMETRY_PERIOD_MS}, "
                             f"{MAX_TELEMETRY_PERIOD_MS}] ms (đang là {self.telemetry_period_ms}): firmware kẹp chu kỳ "
                             f"xin vào 20..1000 ms, nhưng ngưỡng mất liên lạc {QEMU_TELEMETRY_TIMEOUT_S:.1f} s của "
                             f"liên kết phải phủ {STALE_MIN_PERIODS} chu kỳ")
        if not 1 <= self.step_ms <= 20:
            raise ValueError("step_ms phải trong [1, 20] ms")
        for name in ("speed_noise_std_mps", "steer_noise_std_rad"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} phải hữu hạn và >= 0")
        if not isinstance(self.notes, str):
            raise ValueError("notes phải là chuỗi")

    def to_dict(self) -> dict:
        return {"schema_version": PLANT_SCHEMA_VERSION, "notes": self.notes,
                "telemetry_period_ms": self.telemetry_period_ms,
                "plant": {"step_ms": self.step_ms, "speed_noise_std_mps": self.speed_noise_std_mps,
                          "steer_noise_std_deg": math.degrees(self.steer_noise_std_rad), "seed": self.seed}}

    @classmethod
    def from_dict(cls, d: dict) -> "PlantConfig":
        """Khóa vắng mặt lấy mặc định ở trên; khóa lạ, gõ sai hay schema_version khác 1 → ValueError."""
        _check_keys("", d)
        if d.get("schema_version") != PLANT_SCHEMA_VERSION:
            raise ValueError(f"schema_version {d.get('schema_version')!r} không được hỗ trợ (cần {PLANT_SCHEMA_VERSION})")
        plant = d.get("plant", {})
        _check_keys("plant", plant)
        base = cls()
        return cls(telemetry_period_ms=d.get("telemetry_period_ms", base.telemetry_period_ms),
                   step_ms=plant.get("step_ms", base.step_ms),
                   speed_noise_std_mps=_number(plant, "speed_noise_std_mps", base.speed_noise_std_mps),
                   steer_noise_std_rad=math.radians(_number(plant, "steer_noise_std_deg",
                                                            math.degrees(base.steer_noise_std_rad))),
                   seed=plant.get("seed", base.seed), notes=d.get("notes", ""))


def load_plant_config(path: Path | str = DEFAULT_PLANT_CONFIG) -> PlantConfig:
    """Nạp configs/bo_ao_qemu.json. Không đọc được → OSError; JSON hỏng hay khóa sai → ValueError."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))      # utf-8-sig: tệp lưu bằng Notepad có BOM
    return PlantConfig.from_dict(data)


class LaptopPlant:
    """MÔ PHỎNG xe phía laptop, KHÔNG phải số đo: `SimVehicle` (giới hạn tăng/giảm tốc, tốc độ đổi lái của
    `VehicleConfig`) tiến tới thời điểm của mỗi khung telemetry, hướng về tham chiếu của CHÍNH khung đó.

    Thời điểm của khung (đồng hồ io, `QemuPlantVehicleIO._frame_times`): khung cuối của một lần đọc cổng ở đúng lúc
    laptop nhận; khung trước nó trong cùng lần đọc lùi theo đồng hồ bo (sửa 02/10/2026 theo review: trước đó mọi khung
    của lần đọc chung một t, nên khi vòng đọc trễ xe theo tham chiếu của khung CŨ NHẤT suốt khoảng trễ, bỏ qua dốc về 0
    và DISARM của firmware). Firmware dốc tham chiếu theo cùng giới hạn, nên tại thời điểm của khung xe đạt xấp xỉ tham
    chiếu; khoảng thời gian không bao giờ bị ngoại suy quá khung cuối. Socket mở lại (`reanchor()`): khoảng không có kết
    nối không được tích phân. `measured()` làm tròn theo đơn vị trên dây (1 mm/s, 1 mrad), cộng nhiễu tùy chọn (mặc
    định 0)."""

    def __init__(self, cfg: VehicleConfig, pose: Pose, config: PlantConfig | None = None):
        self.config = config or PlantConfig()
        self.vehicle = SimVehicle(cfg, VehicleState(pose, 0.0, 0.0, 0.0))
        self._t: float | None = None
        self._resync = False                  # khung kế tiếp chỉ ghi t (socket vừa mở lại)
        self._rng = random.Random(self.config.seed)

    @property
    def pose(self) -> Pose:
        return self.vehicle.state.pose

    @property
    def state(self) -> VehicleState:
        return self.vehicle.state

    @property
    def t(self) -> float | None:
        """Thời điểm (đồng hồ io) của khung cuối đã tiến tới; None trước khung đầu tiên sau khi đặt xe."""
        return self._t

    def reanchor(self) -> None:
        """Socket tới bo ảo vừa mở lại (thêm 02/10/2026 theo review): khung kế tiếp chỉ ghi t, như khung đầu tiên sau
        khi đặt xe, nên khoảng socket đóng (giữa hai lần chạy, trước "Xóa lỗi bo") không bao giờ được tích phân. Trước
        đó khung đầu tiên sau khi mở lại tích phân cả khoảng nghỉ theo bước 5 ms trên luồng giao diện (một giờ nghỉ:
        720 000 bước). Xe giữ tư thế, tốc độ, góc lái; `t` vẫn là t của khung cuối đã tiến tới cho tới khi có khung
        mới."""
        self._resync = True

    def advance_to(self, t: float, target_speed: float, target_steer: float) -> None:
        """Lần đầu (và lần đầu sau `reanchor()`) chỉ ghi t. Sau đó chia (t − t trước) thành n = ⌈dt / step⌉ bước bằng
        nhau của `SimVehicle.step` hướng về mục tiêu; dt ≤ 0 (khung không mới hơn khung trước) thì không làm gì."""
        if self._t is None or self._resync:
            self._t, self._resync = t, False
            return
        dt = t - self._t
        if not dt > 0:
            return
        steps = max(1, math.ceil(dt * 1000.0 / self.config.step_ms - 1e-9))
        for _ in range(steps):
            self.vehicle.step(dt / steps, target_speed, target_steer)
        self._t = t

    def measured(self) -> tuple[float, float]:
        """(tốc độ m/s, góc lái rad) "đo" lúc này: trạng thái xe mô phỏng + nhiễu, làm tròn theo đơn vị trên dây."""
        cfg = self.config
        state = self.vehicle.state
        speed = state.speed + (self._rng.gauss(0.0, cfg.speed_noise_std_mps) if cfg.speed_noise_std_mps else 0.0)
        steer = state.steer + (self._rng.gauss(0.0, cfg.steer_noise_std_rad) if cfg.steer_noise_std_rad else 0.0)
        return speed_from_wire(speed_to_wire(speed)), steer_from_wire(steer_to_wire(steer))


class QemuPlantVehicleIO(SerialVehicleIO):
    """`SerialVehicleIO` tới UART0 của MỘT bo ảo QEMU do ứng dụng mở, kèm xe mô phỏng phía laptop (`LaptopPlant`).

    Dựng ở trạng thái "chưa mở" (như `SerialVehicleIO.deferred`): không có socket tới khi `reopen()`. `connect()` đòi
    HELLO_ACK có đúng boot_id bo ảo báo lúc khởi động. Sau `place_vehicle()` mỗi khung telemetry làm xe mô phỏng tiến
    tới thời điểm của khung đó (khung của cùng một lần đọc cổng: lùi theo đồng hồ bo từ lúc nhận) và mang tốc độ, góc
    lái của nó; trước đó khung đi qua nguyên vẹn (không có số đo, như firmware thật). Dấu thời gian của khung
    (`stamp.t`) vẫn là lúc nhận. `reopen()` neo lại thời gian của xe: khoảng socket đóng không được tích phân. Người lái
    của chế độ quan sát (`set_human_targets`) thay tham chiếu của firmware làm mục tiêu của xe. `source_id`
    "qemu_board": sự kiện và telemetry phân biệt được với bo thật ("esp32_vehicle")."""

    source_id = "qemu_board"

    def __init__(self, board: QemuBoardHandle, *, plant_config: PlantConfig | None = None,
                 clock: Callable[[], float] | None = None, **kwargs):
        check_emulator_url(board.url)                 # trước mọi việc khác: không mở gì với URL lạ
        config = plant_config or PlantConfig()
        kwargs.setdefault("telemetry_timeout_s", QEMU_TELEMETRY_TIMEOUT_S)   # ngưỡng mà PlantConfig kiểm chu kỳ theo
        super().__init__(None, clock=board.clock or clock, opener=board.transport_opener(), port=board.url,
                         telemetry_period_ms=config.telemetry_period_ms, **kwargs)
        self.board = board
        self.plant_config = config
        self.plant: LaptopPlant | None = None
        self.human_targets: tuple[float, float] | None = None
        self._plant_times: dict[int, float] = {}       # id(khung) → thời điểm cho xe mô phỏng, trong một lần đọc

    def place_vehicle(self, cfg: VehicleConfig, pose: Pose) -> None:
        """Người đặt xe vào `pose` (điểm xuất phát của lần chạy): xe mô phỏng MỚI, đứng yên, lái thẳng; bỏ mục tiêu của
        người lái (như bo mô phỏng của giao diện tạo xe mới ở điểm xuất phát mỗi lần Bắt đầu đỗ)."""
        with self._lock:
            self.plant = LaptopPlant(cfg, pose, self.plant_config)
            self.human_targets = None

    def set_human_targets(self, speed: float, steer: float) -> None:
        """Chế độ quan sát: xe mô phỏng theo (tốc độ, góc lái) của người lái thay vì tham chiếu của firmware."""
        with self._lock:
            self.human_targets = (float(speed), float(steer))

    def plant_sample(self) -> tuple[Pose, float] | None:
        """(tư thế, t của khung cuối) của xe mô phỏng; None trước khung đầu tiên sau `place_vehicle()`."""
        with self._lock:
            plant = self.plant
            if plant is None or plant.t is None:
                return None
            return plant.pose, plant.t

    def connect(self, timeout_s: float = 1.0) -> HelloInfo:
        """Như `VehicleIO.connect`, rồi đòi boot_id của HELLO_ACK bằng boot_id bo ảo báo lúc khởi động (`board.hello`).
        Khác → `connected` = False và VehicleIOError: không ARM, không COMMAND nào tới thiết bị đó."""
        with self._lock:
            expected = self.board.hello
            if expected is None:
                self.connected = False
                raise VehicleIOError(f"Bo ảo {self.port} không có HELLO_ACK lúc khởi động nên không kiểm được boot_id; "
                                     f"tắt rồi khởi động lại bo ảo")
            info = super().connect(timeout_s)
            if info.boot_id != expected.boot_id:
                self.connected = False
                raise VehicleIOError(f"HELLO_ACK có boot_id {info.boot_id:08x}, khác bo ảo đã khởi động "
                                     f"({expected.boot_id:08x}): cổng {self.port} không phải bo ảo này hoặc chip ảo đã "
                                     f"khởi động lại; tắt rồi khởi động lại bo ảo")
            return info

    def reopen(self) -> None:
        """Như `SerialVehicleIO.reopen`, rồi neo lại thời gian của xe mô phỏng (`LaptopPlant.reanchor`, thêm 02/10/2026
        theo review): khung đầu tiên sau khi mở chỉ ghi t. Liên kết đóng socket sau mỗi lần chạy, nên không có bước này
        "Xóa lỗi bo" sau một lúc nghỉ tích phân cả lúc nghỉ trên luồng giao diện."""
        with self._lock:
            super().reopen()
            if self.plant is not None:
                self.plant.reanchor()

    def _on_bytes(self, data: bytes, t: float) -> None:
        """Như `VehicleIO._on_bytes`, kèm thời điểm riêng cho xe mô phỏng của từng khung telemetry trong lần đọc này
        (`_frame_times`); dấu thời gian của khung vẫn là t (lúc nhận)."""
        messages = self.parser.feed(data)
        self._plant_times = self._frame_times(messages, t) if self.plant is not None else {}
        try:
            for msg in messages:
                self._on_message(msg, t)
        finally:
            self._plant_times = {}

    def _frame_times(self, messages: list, t: float) -> dict[int, float]:
        """Thời điểm (đồng hồ io) cho xe mô phỏng của các khung telemetry trong CÙNG một lần đọc cổng (sửa 02/10/2026
        theo review): khung cuối ở đúng lúc nhận t, khung trước lùi theo đồng hồ bo, t_k = t − (τ_cuối − τ_k)/1000 với
        τ = sample_time_ms. Không bao giờ quá t (không ngoại suy quá khung cuối); khung có t_k không sau thời điểm xe đã
        tới thì xe không tiến (`advance_to`). Chỉ tính khung của phiên đang mở (khung khác `_on_message` bỏ). Đồng hồ bo
        lùi trong lần đọc (bo khởi động lại giữa chừng) → khung đó lấy t."""
        frames = [m for m in messages if isinstance(m, TelemetryMsg) and m.session_id == self.session_id]
        if len(frames) < 2:
            return {}
        last = frames[-1].sample_time_ms
        times = {}
        for msg in frames:
            lag_ms = (last - msg.sample_time_ms) & U32
            times[id(msg)] = t - lag_ms / 1000.0 if lag_ms < 0x80000000 else t
        return times

    def _telemetry_from_message(self, msg: TelemetryMsg, t: float) -> VehicleTelemetry:
        tel = super()._telemetry_from_message(msg, t)    # mã lạ → ValueError: bad_values, xe mô phỏng không tiến
        plant = self.plant
        if plant is None:
            return tel                                   # chưa đặt xe: đúng khung của firmware (không có số đo)
        speed_target, steer_target = self.human_targets or (tel.speed_ref_mps, tel.steer_ref_rad)
        # Thời điểm của CHÍNH khung này (khung trước khung cuối của lần đọc: sớm hơn t); dấu thời gian vẫn là t.
        plant.advance_to(self._plant_times.get(id(msg), t), speed_target, steer_target)
        speed, steer = plant.measured()
        # Cờ của firmware giữ nguyên: telemetry.csv vẫn nói firmware không đo gì (SPEED_VALID = STEER_VALID = 0).
        return replace(tel, speed_mps=speed, steer_rad=steer)
