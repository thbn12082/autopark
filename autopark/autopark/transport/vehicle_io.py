"""`VehicleIO`: một giao diện điều khiển xe cho hai nhánh — mô phỏng và bo ESP32-S3 thật (kế hoạch mục 9).

Cả hai nhánh dùng CÙNG định nghĩa đại lượng và cùng bộ mã hóa: API nhận/trả m/s và rad (quy ước dự án: tốc độ có
dấu, âm là lùi; góc lái dương là rẽ trái khi tiến), trên dây là mm/s và mrad nguyên (`speed_to_wire`,
`steer_to_wire`), khung theo `protocol.py`. Nhánh mô phỏng đi qua đúng các byte mà nhánh phần cứng gửi, tới
`FirmwareModel` — bản tham chiếu của firmware — nên phần giao thức, phiên, số thứ tự và máy trạng thái được thử
thật, chỉ phần cơ cấu chấp hành là mô hình.

KHÔNG mặc định hai nhánh có cùng độ trễ. Nhánh mô phỏng lấy độ trễ từ cấu hình (`configs/vehicle_io_sim.json`,
đều là giả định); nhánh phần cứng có độ trễ thật chưa đo. Cả hai đo cùng hai đại lượng theo cùng cách để so sánh:
`stats.ack_rtt_s` (gửi REQUEST → nhận ACK) và `stats.cmd_echo_s` (gửi COMMAND → nhận telemetry đầu tiên báo đã
nhận lệnh đó; đây là cận trên, gồm cả chờ chu kỳ telemetry).

Thời gian: `now()` là đồng hồ phiên của laptop (mô phỏng: thời gian mô phỏng). Telemetry được đóng dấu bằng thời
điểm laptop NHẬN khung (`stamp.t`); tuổi tính từ đó không gồm trễ truyền, nên nhỏ hơn tuổi thật của số đo. Đồng hồ
bo (`device_time_ms`) giữ nguyên để đối chiếu log.

Cách dùng theo bước (xác định, dùng trong test): `connect()` → `arm()` → gọi `send()` mỗi chu kỳ điều khiển và
`poll()` (serial) hoặc `advance(dt)` (mô phỏng) để xử lý byte đến; `poll()`/`advance()` trả MỌI telemetry nhận được
kể từ lần gọi trước. `Heartbeat` là luồng nền tùy chọn cho chạy thật: chỉ `service()` (tiến I/O, KHÔNG lấy hàng đợi
của `poll()`) và gửi PING để giữ liên lạc, KHÔNG BAO GIỜ lặp lại lệnh chuyển động — ứng dụng treo thì lệnh cuối hết
hạn và bo tự dốc về trung tính.

Mất liên lạc phía laptop (`TELEMETRY_STALE`: không có telemetry hợp lệ quá `telemetry_timeout_s`) được CHỐT: laptop
gửi DISARM (nếu chiều laptop → bo còn thông thì bo về DISARMED ngay) và `send(enable=True)` bị từ chối tới khi có
thao tác cho phép mới là `arm()` (hoặc `connect()` mở phiên mới, bo về DISARMED). Telemetry có lại không tự gỡ chốt
(kế hoạch mục 10 bước 6, mục 13: mất liên lạc không được tự chuyển về RUN).
"""
from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import random
import threading
import time
from typing import Callable

from autopark.domain.sensors import SafetyEvent, SourceStamp, Telemetry
from autopark.domain.types import Pose, VehicleConfig, VehicleState
from autopark.safety.freshness import SourcePolicy
from autopark.simulation.vehicle import SimVehicle

from .firmware_model import FirmwareConfig, FirmwareInputs, FirmwareModel
from .protocol import (DEVICE_TO_HOST, N_TOF, NO_COMMAND_AGE, Ack, Action, Command, Fault, FaultMsg, FrameParser,
                       Hello, HelloAck, Message, Request, ResetReason, Result, State, StopReason, TelemetryFlag,
                       TelemetryMsg, COMMAND_FLAG_ENABLE, encode_frame)

U16 = 0xFFFF
U32 = 0xFFFFFFFF
INT16_MIN, INT16_MAX = -32768, 32767
# Ngưỡng TELEMETRY_STALE phải phủ ít nhất ngần này chu kỳ telemetry, để một khung mất cộng dao động thời gian không
# bị coi là mất liên lạc. So sánh bằng ms nguyên (3 × 0,1 = 0,30000000000000004 > 0,3 trong số thực).
STALE_MIN_PERIODS = 3
DEFAULT_NEW_TELEMETRY_LIMIT = 512          # ≈ 10 s telemetry ở 50 Hz chờ `poll()`


class VehicleIOError(RuntimeError):
    """Không kết nối được, bị từ chối, hết thời gian chờ, hoặc cổng hỏng. `result` là mã từ chối của bo nếu có."""

    def __init__(self, message: str, result: Result | int | None = None):
        super().__init__(message)
        self.result = result


# ---- đơn vị: dùng chung cho cả hai nhánh ---------------------------------------------------------------------------
def round_half_away(x: float) -> int:
    """Làm tròn nửa ra xa 0 (0,5 → 1; -0,5 → -1), giống `lround` của C."""
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def _to_int16(value: float, scale: float, name: str) -> int:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    wire = round_half_away(value * scale)
    if not INT16_MIN <= wire <= INT16_MAX:
        raise ValueError(f"{name}={value} does not fit the wire format (int16 after ×{scale:g})")
    return wire


def speed_to_wire(speed_mps: float) -> int:
    """m/s → mm/s nguyên (độ phân giải 1 mm/s)."""
    return _to_int16(speed_mps, 1000.0, "speed_mps")


def steer_to_wire(steer_rad: float) -> int:
    """rad → mrad nguyên (độ phân giải 1 mrad ≈ 0,057°)."""
    return _to_int16(steer_rad, 1000.0, "steer_rad")


def speed_from_wire(speed_mm_s: int) -> float:
    return speed_mm_s / 1000.0


def steer_from_wire(steer_mrad: int) -> float:
    return steer_mrad / 1000.0


# ---- dữ liệu phía laptop ------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class VehicleLimits:
    """Giới hạn bo báo trong HELLO_ACK (đơn vị SI). Bo tự kẹp lệnh theo các giới hạn này."""

    max_speed_mps: float
    max_steer_rad: float
    max_steer_rate_rad_s: float
    max_accel_mps2: float
    max_decel_mps2: float
    stop_decel_mps2: float
    max_validity_s: float
    link_timeout_s: float


@dataclass(frozen=True)
class HelloInfo:
    session_id: int
    boot_id: int
    firmware_version: str
    reset_reason: int
    state: State
    telemetry_period_s: float
    limits: VehicleLimits
    received_at: float


@dataclass(frozen=True)
class ImuSample:
    gyro_z_rad_s: float
    accel_x_mps2: float
    accel_y_mps2: float


@dataclass(frozen=True)
class VehicleTelemetry:
    """Một khung telemetry đã đổi đơn vị. Số đo không hợp lệ là None — không bao giờ là 0 hay giá trị lớn."""

    stamp: SourceStamp                 # t = lúc laptop nhận (đồng hồ phiên)
    device_time_ms: int
    sequence: int
    state: State
    fault: Fault
    stop_reason: StopReason
    flags: TelemetryFlag
    speed_mps: float | None
    steer_rad: float | None
    speed_ref_mps: float
    steer_ref_rad: float
    effort: float                      # -1..1
    last_cmd_seq: int
    cmd_age_s: float | None
    imu: ImuSample | None
    tof_m: tuple[float | None, ...]
    supply_v: float | None
    rx_errors: int
    rejects: int

    @property
    def link_ok(self) -> bool:
        return bool(self.flags & TelemetryFlag.LINK_OK)

    @property
    def estop_input(self) -> bool:
        return bool(self.flags & TelemetryFlag.ESTOP_INPUT)

    def to_domain(self) -> Telemetry | None:
        """Hợp đồng `Telemetry` của dự án; None khi thiếu tốc độ hoặc góc lái đo được."""
        if self.speed_mps is None or self.steer_rad is None:
            return None
        return Telemetry(self.stamp, self.speed_mps, self.steer_rad)

    @classmethod
    def from_message(cls, msg: TelemetryMsg, received_at: float, source_id: str) -> "VehicleTelemetry":
        flags = TelemetryFlag(msg.flags)
        state, fault, reason = State(msg.state), Fault(msg.fault), StopReason(msg.stop_reason)  # mã lạ → ValueError
        imu = None
        if flags & TelemetryFlag.IMU_VALID:
            imu = ImuSample(msg.gyro_z_mrad_s / 1000.0, msg.accel_x_mm_s2 / 1000.0, msg.accel_y_mm_s2 / 1000.0)
        tof = tuple(msg.tof_mm[k] / 1000.0 if msg.tof_valid_mask & (1 << k) else None for k in range(N_TOF))
        return cls(
            stamp=SourceStamp(source_id, received_at, True, "vehicle"),
            device_time_ms=msg.sample_time_ms, sequence=msg.sequence, state=state, fault=fault, stop_reason=reason,
            flags=flags,
            speed_mps=speed_from_wire(msg.speed_measured_mm_s) if flags & TelemetryFlag.SPEED_VALID else None,
            steer_rad=steer_from_wire(msg.steer_measured_mrad) if flags & TelemetryFlag.STEER_VALID else None,
            speed_ref_mps=speed_from_wire(msg.speed_ref_mm_s), steer_ref_rad=steer_from_wire(msg.steer_ref_mrad),
            effort=msg.effort_permille / 1000.0, last_cmd_seq=msg.last_cmd_seq,
            cmd_age_s=None if msg.cmd_age_ms == NO_COMMAND_AGE else msg.cmd_age_ms / 1000.0,
            imu=imu, tof_m=tof,
            supply_v=msg.supply_mv / 1000.0 if flags & TelemetryFlag.SUPPLY_VALID else None,
            rx_errors=msg.rx_errors, rejects=msg.rejects)


@dataclass
class LinkStats:
    frames_sent: int = 0
    commands_sent: int = 0
    requests_sent: int = 0
    messages_received: int = 0
    telemetry_received: int = 0
    device_messages_missed: int = 0    # khoảng hở số thứ tự phía bo (mất khung hoặc bo bỏ vì đầy bộ đệm)
    stale_or_duplicate: int = 0
    foreign_session: int = 0           # khung của phiên khác (phiên cũ, hoặc trước HELLO_ACK)
    bad_values: int = 0                # telemetry có mã trạng thái/lỗi lạ
    link_errors: int = 0
    telemetry_unpolled_dropped: int = 0    # telemetry bị đẩy khỏi hàng đợi của poll() vì ứng dụng không poll() kịp
    rejected: dict = field(default_factory=dict)
    ack_rtt_s: float | None = None
    ack_rtt_max_s: float | None = None
    cmd_echo_s: float | None = None
    cmd_echo_max_s: float | None = None


def _max(a: float | None, b: float) -> float:
    return b if a is None else max(a, b)


# ---- phần chung của hai nhánh -------------------------------------------------------------------------------------
class VehicleIO:
    """Phía laptop của giao thức: phiên, số thứ tự, chờ ACK, kiểm tra telemetry, sự kiện an toàn.

    Lớp con cung cấp `now()`, `_write(bytes)`, `_pump()` (tiến một bước I/O: đọc cổng, hoặc chạy một nhịp mô
    phỏng, rồi gọi `_on_bytes`) và `close()`. Các phương thức chờ (`connect`, `arm`...) lặp `_pump()` tới khi có
    trả lời hoặc hết thời gian theo `now()`, nên với đồng hồ mô phỏng chúng xác định hoàn toàn.
    """

    source_id = "vehicle_io"

    def __init__(self, *, rng: random.Random | None = None, telemetry_timeout_s: float = 0.3,
                 default_validity_s: float = 0.15, telemetry_period_ms: int = 0, request_timeout_s: float = 0.5,
                 new_telemetry_limit: int = DEFAULT_NEW_TELEMETRY_LIMIT):
        for name, value in (("telemetry_timeout_s", telemetry_timeout_s), ("default_validity_s", default_validity_s),
                            ("request_timeout_s", request_timeout_s)):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and > 0")
        if (not isinstance(telemetry_period_ms, int) or isinstance(telemetry_period_ms, bool)
                or not 0 <= telemetry_period_ms <= U16):
            raise ValueError("telemetry_period_ms must be an int in [0, 65535] (0 = mặc định của bo)")
        if telemetry_period_ms and not self._timeout_covers_period(telemetry_timeout_s, telemetry_period_ms):
            raise ValueError(f"telemetry_timeout_s ({telemetry_timeout_s:.3f} s) phải >= {STALE_MIN_PERIODS} lần "
                             f"telemetry_period_ms ({telemetry_period_ms} ms), nếu không sẽ báo TELEMETRY_STALE giữa "
                             f"hai khung bình thường")
        if not isinstance(new_telemetry_limit, int) or isinstance(new_telemetry_limit, bool) or new_telemetry_limit < 1:
            raise ValueError("new_telemetry_limit must be an int >= 1")
        self._lock = threading.RLock()
        self.rng = rng or random.Random()
        self.telemetry_timeout_s = telemetry_timeout_s
        self.default_validity_s = default_validity_s
        self.telemetry_period_ms = telemetry_period_ms
        self.request_timeout_s = request_timeout_s
        self.parser = FrameParser(accept_types=DEVICE_TO_HOST)
        self.stats = LinkStats()
        self.session_id = 0
        self.tx_seq = 0
        self.connected = False
        self.hello: HelloInfo | None = None
        self.known_boot_id: int | None = None
        self.last_tx_time = -math.inf
        self._connected_at = 0.0
        self._pending_hello: int | None = None
        self._last_dev_seq: int | None = None
        self._waiting: set[int] = set()
        self._acks: dict[int, tuple[Ack, float]] = {}
        self._req_sent: dict[int, float] = {}
        self._cmd_sent: OrderedDict[int, float] = OrderedDict()
        self._last_echo_seq: int | None = None
        self._latest: VehicleTelemetry | None = None
        self._new: deque[VehicleTelemetry] = deque(maxlen=new_telemetry_limit)
        self._events: deque[SafetyEvent] = deque(maxlen=1000)
        self._stale_reported = False
        # Chốt "mất liên lạc" phía laptop: đặt khi báo TELEMETRY_STALE, chỉ gỡ bằng arm() thành công hoặc connect().
        self.rearm_required = False
        self._fault_reported: Fault | None = None
        self._last_state: State | None = None
        self._reported_rejects: set[tuple[int, int]] = set()

    # ---- lớp con cài đặt -----------------------------------------------------------------------------------------
    def now(self) -> float:
        raise NotImplementedError

    def _write(self, data: bytes) -> None:
        raise NotImplementedError

    def _pump(self) -> None:
        raise NotImplementedError

    def _is_open(self) -> bool:
        return True

    def close(self) -> None:
        self.connected = False

    # ---- tiện ích ------------------------------------------------------------------------------------------------
    @staticmethod
    def _timeout_covers_period(timeout_s: float, period_ms: int) -> bool:
        return STALE_MIN_PERIODS * period_ms <= round_half_away(timeout_s * 1000)

    def _event(self, code: str, message: str, action: str = "STOP", t: float | None = None) -> None:
        stamp = SourceStamp(self.source_id, max(0.0, self.now() if t is None else t))
        self._events.append(SafetyEvent(stamp, code, message, action))

    def _next_seq(self) -> int:
        seq = self.tx_seq
        self.tx_seq = (seq + 1) & U16
        return seq

    def _send_message(self, msg: Message) -> None:
        self._write(encode_frame(msg))
        self.stats.frames_sent += 1
        self.last_tx_time = self.now()

    def _wait(self, predicate: Callable[[], bool], timeout_s: float, what: str) -> None:
        deadline = self.now() + timeout_s
        while not predicate():
            if self.now() >= deadline:
                raise VehicleIOError(f"Hết {timeout_s:.3f} s chờ {what}")
            self._pump()

    # ---- phiên ---------------------------------------------------------------------------------------------------
    def connect(self, timeout_s: float = 1.0) -> HelloInfo:
        """Mở phiên MỚI (session_id ngẫu nhiên khác 0) bằng HELLO và chờ HELLO_ACK. Gọi lại = kết nối lại: bo luôn
        về DISARMED (hoặc giữ BOOT/FAULT), lệnh của phiên cũ bị từ chối. Phát hiện bo đã khởi động lại qua boot_id."""
        with self._lock:
            if not self._is_open():
                raise VehicleIOError("Cổng chưa mở")
            self.connected = False
            self.session_id = self.rng.randrange(1, U32 + 1)
            self.tx_seq = 0
            self.hello = None
            self._last_dev_seq = None
            self._latest = None
            self._new.clear()
            self._waiting.clear()
            self._acks.clear()
            self._req_sent.clear()
            self._cmd_sent.clear()
            self._last_echo_seq = None
            self._stale_reported = False
            self.rearm_required = False        # HELLO đưa bo về DISARMED (hoặc giữ BOOT/FAULT): bo tự đòi ARM
            self._fault_reported = None
            self._last_state = None
            self._reported_rejects.clear()
            seq = self._next_seq()
            self._pending_hello = seq
            self._send_message(Hello(self.session_id, seq, self.telemetry_period_ms, round_half_away(self.now() * 1000) & U32))
            self._wait(lambda: self.hello is not None, timeout_s, "HELLO_ACK")
            info = self.hello
            if self.known_boot_id is not None and info.boot_id != self.known_boot_id:
                self._event("FIRMWARE_RESET", f"Bo đã khởi động lại (boot_id {self.known_boot_id:08x} → "
                                              f"{info.boot_id:08x}, lý do reset {info.reset_reason}); trạng thái "
                                              f"{info.state.name}", "STOP")
            self.known_boot_id = info.boot_id
            period_ms = round_half_away(info.telemetry_period_s * 1000)
            if not self._timeout_covers_period(self.telemetry_timeout_s, period_ms):
                # Bo kẹp chu kỳ xin, hoặc dùng mặc định của nó khi xin 0. Không nhận phiên: `connected` giữ False
                # (hướng an toàn — bo ở DISARMED và không nhận lệnh chạy nào từ laptop này).
                raise VehicleIOError(f"Bo chọn chu kỳ telemetry {period_ms} ms, quá dài so với ngưỡng "
                                     f"telemetry_timeout_s {self.telemetry_timeout_s:.3f} s (cần >= "
                                     f"{STALE_MIN_PERIODS} chu kỳ)")
            self.connected = True
            self._connected_at = self.now()
            return info

    def wait_ready(self, timeout_s: float = 3.0) -> State:
        """Chờ tới khi telemetry báo bo đã qua BOOT."""
        with self._lock:
            self._wait(lambda: self._latest is not None and self._latest.state != State.BOOT, timeout_s,
                       "bo ra khỏi BOOT")
            return self._latest.state

    def _request(self, action: Action, *, wait: bool = True, timeout_s: float | None = None) -> Ack | None:
        with self._lock:
            if not self.connected:
                raise VehicleIOError("Chưa có phiên: gọi connect()")
            seq = self._next_seq()
            if wait:
                self._waiting.add(seq)
                self._req_sent[seq] = self.now()
            self._send_message(Request(self.session_id, seq, int(action)))
            self.stats.requests_sent += 1
            if not wait:
                return None
            try:
                self._wait(lambda: seq in self._acks, timeout_s or self.request_timeout_s, f"ACK của {action.name}")
            finally:
                self._waiting.discard(seq)
                self._req_sent.pop(seq, None)
            ack, _ = self._acks.pop(seq)
            if ack.result != Result.OK:
                result = Result(ack.result) if ack.result in Result._value2member_map_ else ack.result
                name = result.name if isinstance(result, Result) else str(result)
                raise VehicleIOError(f"Bo từ chối {action.name}: {name}", result)
            return ack

    def arm(self, timeout_s: float | None = None) -> None:
        """DISARMED → ARMED. Sau đó vẫn phải gửi COMMAND enable mới chạy (ARM không tự chạy tiếp lệnh cũ).

        Đây cũng là "thao tác cho phép mới" gỡ chốt `rearm_required` sau TELEMETRY_STALE (chỉ khi bo trả OK)."""
        with self._lock:
            self._request(Action.ARM, timeout_s=timeout_s)
            self.rearm_required = False

    def disarm(self, timeout_s: float | None = None) -> None:
        self._request(Action.DISARM, timeout_s=timeout_s)

    def clear_fault(self, timeout_s: float | None = None) -> None:
        """FAULT → DISARMED, chỉ khi nguyên nhân đã hết (E-stop đã nhả...)."""
        self._request(Action.CLEAR_FAULT, timeout_s=timeout_s)

    def ping(self, *, wait: bool = False) -> None:
        """Giữ liên lạc (watchdog liên lạc của bo) mà không đổi lệnh chuyển động."""
        self._request(Action.PING, wait=wait)

    # ---- lệnh ----------------------------------------------------------------------------------------------------
    def send(self, speed_mps: float, steer_rad: float, *, enable: bool = True, validity_s: float | None = None) -> int:
        """Gửi một COMMAND có thời hạn; trả số thứ tự. Không chờ ACK (bo chỉ ACK khi từ chối; telemetry báo
        last_cmd_seq khi nhận). Bo kẹp tốc độ/góc/tốc độ đổi lái theo giới hạn của nó.

        Sau TELEMETRY_STALE (`rearm_required`), lệnh `enable=True` bị từ chối bằng `VehicleIOError` tới khi `arm()`
        lại; lệnh `enable=False` (`stop()`) vẫn gửi được."""
        validity = self.default_validity_s if validity_s is None else validity_s
        if not math.isfinite(validity):
            raise ValueError("validity_s must be finite")
        validity_ms = round_half_away(validity * 1000)
        if not 1 <= validity_ms <= U16:
            raise ValueError("validity_s must be in [0.001, 65.535] s")
        speed_mm, steer_mrad = speed_to_wire(speed_mps), steer_to_wire(steer_rad)
        with self._lock:
            if not self.connected:
                raise VehicleIOError("Chưa có phiên: gọi connect()")
            if enable and self.rearm_required:
                raise VehicleIOError("Laptop đã coi là mất liên lạc (TELEMETRY_STALE): phải arm() lại mới chạy tiếp")
            seq = self._next_seq()
            self._send_message(Command(self.session_id, seq, validity_ms, COMMAND_FLAG_ENABLE if enable else 0,
                                       speed_mm, steer_mrad))
            self.stats.commands_sent += 1
            self._cmd_sent[seq] = self.now()
            while len(self._cmd_sent) > 64:
                self._cmd_sent.popitem(last=False)
            return seq

    def stop(self, validity_s: float | None = None) -> int:
        """COMMAND enable=0: RUNNING → ARMED, đầu ra dốc về trung tính."""
        return self.send(0.0, 0.0, enable=False, validity_s=validity_s)

    # ---- nhận ----------------------------------------------------------------------------------------------------
    def service(self) -> None:
        """Tiến một bước I/O và kiểm tra telemetry cũ, KHÔNG lấy hàng đợi telemetry mới (dùng cho luồng nền như
        `Heartbeat`, để `poll()` của ứng dụng vẫn nhận đủ mọi khung)."""
        with self._lock:
            if self._is_open():
                self._pump()
            self.check()

    def _take_new(self) -> list[VehicleTelemetry]:
        out = list(self._new)
        self._new.clear()
        return out

    def poll(self) -> list[VehicleTelemetry]:
        """Tiến một bước I/O, kiểm tra telemetry cũ; trả MỌI telemetry nhận được kể từ lần `poll()` trước (kể cả
        khung do `Heartbeat` đọc). Hàng đợi có giới hạn `new_telemetry_limit`; khung cũ nhất bị đẩy ra được đếm ở
        `stats.telemetry_unpolled_dropped`."""
        with self._lock:
            self.service()
            return self._take_new()

    def latest(self) -> VehicleTelemetry | None:
        with self._lock:
            return self._latest

    def telemetry_fresh(self, now: float | None = None, max_age_s: float | None = None) -> bool:
        with self._lock:
            now = self.now() if now is None else now
            limit = self.telemetry_timeout_s if max_age_s is None else max_age_s
            return self._latest is not None and 0 <= now - self._latest.stamp.t <= limit

    def source_policy(self) -> SourcePolicy:
        """Chính sách tuổi cho `FreshnessMonitor` với cùng ngưỡng mà VehicleIO dùng để báo TELEMETRY_STALE."""
        period = self.hello.telemetry_period_s if self.hello else None
        return SourcePolicy(max_age_s=self.telemetry_timeout_s, expected_period_s=period)

    def events(self) -> list[SafetyEvent]:
        with self._lock:
            out = list(self._events)
            self._events.clear()
            return out

    def check(self, now: float | None = None) -> None:
        """Báo TELEMETRY_STALE (một lần mỗi đợt) khi đang có phiên mà telemetry cũ hơn `telemetry_timeout_s`.

        Mất liên lạc được CHỐT (`rearm_required`): từ đó `send(enable=True)` bị từ chối tới khi `arm()` hoặc
        `connect()`; telemetry có lại không gỡ chốt. Đồng thời gửi DISARM (không chờ ACK): nếu chỉ mất chiều bo →
        laptop thì bo về DISARMED ngay thay vì chờ lệnh hết hạn; mất cả hai chiều thì khung bị mất và watchdog liên
        lạc của bo lo."""
        with self._lock:
            if not self.connected:
                return
            now = self.now() if now is None else now
            last = self._latest.stamp.t if self._latest is not None else self._connected_at
            if now - last > self.telemetry_timeout_s and not self._stale_reported:
                self._stale_reported = True
                self.rearm_required = True
                self._event("TELEMETRY_STALE", f"Không có telemetry hợp lệ trong {now - last:.3f} s "
                                               f"(ngưỡng {self.telemetry_timeout_s:.3f} s): coi như mất liên lạc; "
                                               f"phải arm() lại mới chạy tiếp", "STOP", now)
                try:
                    self._request(Action.DISARM, wait=False)
                except VehicleIOError:
                    pass                           # cổng hỏng: đã thành LINK_ERROR, phiên đã bị bỏ

    def _on_bytes(self, data: bytes, t: float) -> None:
        for msg in self.parser.feed(data):
            self._on_message(msg, t)

    def _on_message(self, msg: Message, t: float) -> None:
        if self.session_id == 0 or msg.session_id != self.session_id:
            self.stats.foreign_session += 1
            return
        if isinstance(msg, HelloAck):
            if self._pending_hello is None or msg.hello_sequence != self._pending_hello:
                self.stats.stale_or_duplicate += 1
                return
            if msg.state not in State._value2member_map_:
                self.stats.bad_values += 1
                return
            self._pending_hello = None
            self._last_dev_seq = msg.sequence
            self.stats.messages_received += 1
            lim = msg.limits
            self.hello = HelloInfo(
                session_id=msg.session_id, boot_id=msg.boot_id, firmware_version=f"{msg.fw_major}.{msg.fw_minor}",
                reset_reason=msg.reset_reason, state=State(msg.state),
                telemetry_period_s=msg.telemetry_period_ms / 1000.0,
                limits=VehicleLimits(lim.max_speed_mm_s / 1000.0, lim.max_steer_mrad / 1000.0,
                                     lim.max_steer_rate_mrad_s / 1000.0, lim.max_accel_mm_s2 / 1000.0,
                                     lim.max_decel_mm_s2 / 1000.0, lim.stop_decel_mm_s2 / 1000.0,
                                     lim.max_validity_ms / 1000.0, lim.link_timeout_ms / 1000.0),
                received_at=t)
            return
        if isinstance(msg, Ack) and msg.result in (Result.NO_SESSION, Result.WRONG_SESSION):
            # Bo vừa khởi động lại thì bộ đếm số thứ tự của nó bắt đầu lại từ 0, nên ACK này sẽ bị lọc "cũ" nếu đi
            # qua kiểm tra số thứ tự. Nó chỉ có thể làm laptop BỎ phiên (hướng an toàn), nên được xử lý ngay.
            self.stats.messages_received += 1
            self._on_ack(msg, t)
            return
        if self._last_dev_seq is None:
            self.stats.foreign_session += 1       # khung đến trước HELLO_ACK của phiên này
            return
        diff = (msg.sequence - self._last_dev_seq) & U16
        if diff == 0 or diff >= 0x8000:
            self.stats.stale_or_duplicate += 1
            return
        self.stats.device_messages_missed += diff - 1
        self._last_dev_seq = msg.sequence
        self.stats.messages_received += 1
        if isinstance(msg, Ack):
            self._on_ack(msg, t)
        elif isinstance(msg, TelemetryMsg):
            self._on_telemetry(msg, t)
        elif isinstance(msg, FaultMsg):
            self._on_fault(msg, t)

    def _on_ack(self, ack: Ack, t: float) -> None:
        if ack.acked_sequence in self._waiting:
            self._acks[ack.acked_sequence] = (ack, t)
            sent = self._req_sent.pop(ack.acked_sequence, None)
            if sent is not None:
                self.stats.ack_rtt_s = t - sent
                self.stats.ack_rtt_max_s = _max(self.stats.ack_rtt_max_s, t - sent)
        if ack.result == Result.OK:
            return
        name = Result(ack.result).name if ack.result in Result._value2member_map_ else f"RESULT_{ack.result}"
        self.stats.rejected[name] = self.stats.rejected.get(name, 0) + 1
        if ack.result in (Result.NO_SESSION, Result.WRONG_SESSION):
            if self.connected:
                self.connected = False
                self._event("SESSION_LOST", f"Bo không còn phiên này ({name}); có thể bo đã khởi động lại. "
                                            f"Phải connect() lại; bo sẽ ở DISARMED", "STOP", t)
            return
        key = (ack.acked_type, ack.result)
        if key not in self._reported_rejects:
            self._reported_rejects.add(key)
            kind = {0x01: "HELLO", 0x02: "REQUEST", 0x03: "COMMAND"}.get(ack.acked_type, f"0x{ack.acked_type:02x}")
            self._event("COMMAND_REJECTED", f"Bo từ chối {kind} #{ack.acked_sequence}: {name} "
                                            f"(trạng thái {ack.state})", "LOG", t)

    def _on_telemetry(self, msg: TelemetryMsg, t: float) -> None:
        try:
            tel = VehicleTelemetry.from_message(msg, t, self.source_id)
        except ValueError:
            self.stats.bad_values += 1
            return
        self._latest = tel
        if len(self._new) == self._new.maxlen:
            self.stats.telemetry_unpolled_dropped += 1
        self._new.append(tel)
        self.stats.telemetry_received += 1
        if self._stale_reported:
            self._stale_reported = False
            self._event("TELEMETRY_RESUMED", "Telemetry đã có lại" + ("; vẫn phải arm() lại mới chạy tiếp (chốt mất "
                                                                      "liên lạc)" if self.rearm_required else ""),
                        "LOG", t)
        if msg.cmd_age_ms != NO_COMMAND_AGE and msg.last_cmd_seq != self._last_echo_seq:
            sent = self._cmd_sent.get(msg.last_cmd_seq)
            if sent is not None:
                self._last_echo_seq = msg.last_cmd_seq
                self.stats.cmd_echo_s = t - sent
                self.stats.cmd_echo_max_s = _max(self.stats.cmd_echo_max_s, t - sent)
        if tel.fault != Fault.NONE:
            if self._fault_reported != tel.fault:
                self._fault_reported = tel.fault
                self._event("VEHICLE_FAULT", f"Bo báo lỗi {tel.fault.name} (trạng thái {tel.state.name})", "STOP", t)
        else:
            self._fault_reported = None
        if self._last_state == State.RUNNING and tel.state != State.RUNNING:
            self._event("VEHICLE_STOPPED", f"Bo rời RUNNING → {tel.state.name}, lý do {tel.stop_reason.name}", "LOG", t)
        self._last_state = tel.state

    def _on_fault(self, msg: FaultMsg, t: float) -> None:
        try:
            fault = Fault(msg.fault)
        except ValueError:
            self.stats.bad_values += 1
            return
        if self._fault_reported != fault:
            self._fault_reported = fault
            self._event("VEHICLE_FAULT", f"Bo chốt lỗi {fault.name} lúc {msg.time_ms} ms (chi tiết {msg.detail})",
                        "STOP", t)


# ---- nhánh phần cứng ----------------------------------------------------------------------------------------------
class SerialVehicleIO(VehicleIO):
    """Bo thật qua cổng nối tiếp (USB CDC của ESP32-S3; baudrate bị bỏ qua với USB CDC).

    `transport` là đối tượng kiểu `serial.Serial`: `write(bytes)`, `read(n)` (trả sớm sau timeout riêng của nó),
    `in_waiting`, `close()`. Lỗi cổng (rút cáp: `serial.SerialException`, là `OSError`) → sự kiện LINK_ERROR, mất
    phiên, cổng bị đóng; `reopen()` mở lại rồi phải `connect()` và `arm()` lại. CHƯA THỬ VỚI BO THẬT."""

    source_id = "esp32_vehicle"

    def __init__(self, transport, *, clock: Callable[[], float] | None = None,
                 opener: Callable[[], object] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.transport = transport
        self._opener = opener
        if clock is None:
            t0 = time.monotonic()
            clock = lambda: time.monotonic() - t0  # noqa: E731
        self.clock = clock

    @classmethod
    def open(cls, port: str, *, baudrate: int = 115200, read_timeout_s: float = 0.01, write_timeout_s: float = 0.05,
             **kwargs) -> "SerialVehicleIO":
        import serial  # pyserial

        def opener():
            return serial.Serial(port, baudrate, timeout=read_timeout_s, write_timeout=write_timeout_s)

        return cls(opener(), opener=opener, **kwargs)

    def now(self) -> float:
        return self.clock()

    def _is_open(self) -> bool:
        return self.transport is not None

    def _link_failed(self, exc: BaseException) -> None:
        self.stats.link_errors += 1
        was_connected = self.connected
        self.connected = False
        transport, self.transport = self.transport, None
        try:
            if transport is not None:
                transport.close()
        except OSError:
            pass
        self._event("LINK_ERROR", f"Lỗi cổng nối tiếp ({exc}); {'mất phiên, ' if was_connected else ''}"
                                  f"cần reopen() + connect() + arm()", "STOP")

    def _write(self, data: bytes) -> None:
        if self.transport is None:
            raise VehicleIOError("Cổng đã đóng")
        try:
            self.transport.write(data)
        except OSError as exc:
            self._link_failed(exc)
            raise VehicleIOError(f"Không ghi được ra cổng: {exc}") from exc

    def _pump(self) -> None:
        if self.transport is None:
            raise VehicleIOError("Cổng đã đóng")
        try:
            waiting = self.transport.in_waiting
            data = self.transport.read(waiting if waiting > 0 else 1)
        except OSError as exc:
            self._link_failed(exc)
            raise VehicleIOError(f"Không đọc được cổng: {exc}") from exc
        if data:
            self._on_bytes(bytes(data), self.now())

    def service(self) -> None:
        try:
            super().service()
        except VehicleIOError:
            pass                               # lỗi cổng đã thành sự kiện LINK_ERROR; poll() vẫn trả khung đã nhận

    def reopen(self) -> None:
        with self._lock:
            if self._opener is None:
                raise VehicleIOError("Không có hàm mở lại cổng")
            if self.transport is not None:
                try:
                    self.transport.close()
                except OSError:
                    pass
            self.transport = self._opener()
            self.parser.reset()
            self.connected = False

    def close(self) -> None:
        with self._lock:
            self.connected = False
            if self.transport is not None:
                self.transport.close()
                self.transport = None


class Heartbeat:
    """Luồng nền cho chạy thật: `service()` liên tục (tiến I/O, KHÔNG lấy hàng đợi của `poll()` — ứng dụng vẫn nhận
    đủ mọi telemetry qua `poll()`) và gửi PING khi laptop im lặng quá `period_s`.

    KHÔNG lặp lại lệnh chuyển động: nếu vòng điều khiển của ứng dụng treo, lệnh cuối hết hạn (validity) và bo dốc
    về trung tính dù luồng này vẫn giữ liên lạc; chỉ khi cả laptop im lặng quá `link_timeout` thì bo mới DISARMED."""

    def __init__(self, io: VehicleIO, period_s: float = 0.1, idle_sleep_s: float = 0.005):
        if not (math.isfinite(period_s) and period_s > 0 and math.isfinite(idle_sleep_s) and idle_sleep_s >= 0):
            raise ValueError("period_s must be > 0 and idle_sleep_s >= 0")
        self.io = io
        self.period_s = period_s
        self.idle_sleep_s = idle_sleep_s
        self.pings = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="vehicle-io-heartbeat", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 1.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout_s)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.io.service()
                if self.io.connected and self.io.now() - self.io.last_tx_time >= self.period_s:
                    self.io.ping(wait=False)
                    self.pings += 1
            except VehicleIOError:
                pass
            self._stop.wait(self.idle_sleep_s)


# ---- nhánh mô phỏng -----------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SimLinkConfig:
    host_to_device_latency_ms: int = 4
    device_to_host_latency_ms: int = 4
    drop_probability: float = 0.0          # xác suất mất một lần ghi (mỗi hướng), để thử mất gói


@dataclass(frozen=True)
class SimActuatorConfig:
    """ESC + motor: vùng chết theo effort, tốc độ xác lập tỉ lệ với phần effort vượt vùng chết, trễ thuần.
    Động học tăng/giảm tốc và tốc độ đổi lái lấy từ `VehicleConfig` (SimVehicle). Toàn bộ là GIẢ ĐỊNH."""

    latency_ms: int = 30
    effort_deadzone_permille: int = 150
    speed_at_full_effort_mps: float = 0.8
    steer_offset_rad: float = 0.0          # lệch trim của servo (góc thật = lệnh + lệch)
    estop_cuts_power: bool = True          # giả định: E-stop cắt động lực nên effort mất tác dụng


@dataclass(frozen=True)
class SimSensorConfig:
    speed_available: bool = True           # False: chưa có encoder → bo chạy feedforward hở
    speed_latency_ms: int = 20
    speed_noise_std_mps: float = 0.01
    steer_available: bool = True
    steer_latency_ms: int = 10
    steer_noise_std_rad: float = 0.005
    imu_available: bool = True
    gyro_noise_std_rad_s: float = 0.01


# Khóa hợp lệ của configs/vehicle_io_sim.json (tên theo JSON: góc tính bằng độ, *_deg). Khóa lạ/gõ sai bị từ chối
# thay vì âm thầm rơi về giá trị mặc định giả định. Thêm khóa vào `SimIOConfig.to_dict` thì phải thêm vào đây (test
# vòng from_dict(to_dict()) sẽ báo nếu quên). Mục "firmware" do `FirmwareConfig.from_dict` tự kiểm.
_SIM_IO_KEYS = {
    "": {"schema_version", "notes", "vehicle_config", "tick_ms", "seed", "link", "actuator", "sensors", "firmware"},
    "link": {"host_to_device_latency_ms", "device_to_host_latency_ms", "drop_probability"},
    "actuator": {"latency_ms", "effort_deadzone_permille", "speed_at_full_effort_mps", "steer_offset_deg",
                 "estop_cuts_power"},
    "sensors": {"speed_available", "speed_latency_ms", "speed_noise_std_mps", "steer_available", "steer_latency_ms",
                "steer_noise_std_deg", "imu_available", "gyro_noise_std_deg_s"},
}


# Tham số firmware mặc định của MÔ PHỎNG: như FirmwareConfig() nhưng trần effort 1000 ‰. Lý do: cơ cấu chấp hành
# giả định (SimActuatorConfig) đạt 0,8 m/s ở effort tối đa với vùng chết 150 ‰; trần 250 ‰ dành cho lần thử đầu trên
# xe thật sẽ chặn xe mô phỏng ở ≈ 0,09 m/s và làm mất các thí nghiệm bậc 0,10/0,15 m/s (docs/GIAO_THUC_XE.md mục 10).
# Đây là số của mô phỏng, không phải đề xuất cho xe.
SIM_FIRMWARE_DEFAULT = FirmwareConfig(max_effort_permille=1000)


def _check_sim_keys(section: str, mapping) -> None:
    if not isinstance(mapping, dict):
        raise ValueError(f"{section or 'top level'}: must be a JSON object")
    unknown = set(mapping) - _SIM_IO_KEYS[section]
    if unknown:
        raise ValueError(f"unknown {section or 'top-level'} sim config keys: {sorted(unknown)}")


@dataclass(frozen=True)
class SimIOConfig:
    tick_ms: int = 10
    link: SimLinkConfig = SimLinkConfig()
    actuator: SimActuatorConfig = SimActuatorConfig()
    sensors: SimSensorConfig = SimSensorConfig()
    firmware: FirmwareConfig = SIM_FIRMWARE_DEFAULT
    seed: int = 0
    notes: str = ""

    def __post_init__(self):
        if not isinstance(self.tick_ms, int) or self.tick_ms <= 0:
            raise ValueError("tick_ms must be a positive int")
        for name in ("host_to_device_latency_ms", "device_to_host_latency_ms"):
            if getattr(self.link, name) < 0:
                raise ValueError(f"{name} must be >= 0")
        if not 0 <= self.link.drop_probability <= 1:
            raise ValueError("drop_probability must be in [0, 1]")
        a, s = self.actuator, self.sensors
        if a.latency_ms < 0 or not 0 <= a.effort_deadzone_permille < 1000 or not a.speed_at_full_effort_mps > 0:
            raise ValueError("actuator: latency >= 0, deadzone in [0, 1000), speed_at_full_effort > 0")
        for value in (s.speed_latency_ms, s.steer_latency_ms, s.speed_noise_std_mps, s.steer_noise_std_rad,
                      s.gyro_noise_std_rad_s):
            if not math.isfinite(value) or value < 0:
                raise ValueError("sensor latencies and noise must be finite and >= 0")

    def to_dict(self) -> dict:
        a, s = self.actuator, self.sensors
        return {
            "schema_version": 1, "notes": self.notes, "tick_ms": self.tick_ms, "seed": self.seed,
            "link": asdict(self.link),
            "actuator": {"latency_ms": a.latency_ms, "effort_deadzone_permille": a.effort_deadzone_permille,
                         "speed_at_full_effort_mps": a.speed_at_full_effort_mps,
                         "steer_offset_deg": math.degrees(a.steer_offset_rad), "estop_cuts_power": a.estop_cuts_power},
            "sensors": {"speed_available": s.speed_available, "speed_latency_ms": s.speed_latency_ms,
                        "speed_noise_std_mps": s.speed_noise_std_mps, "steer_available": s.steer_available,
                        "steer_latency_ms": s.steer_latency_ms, "steer_noise_std_deg": math.degrees(s.steer_noise_std_rad),
                        "imu_available": s.imu_available,
                        "gyro_noise_std_deg_s": math.degrees(s.gyro_noise_std_rad_s)},
            "firmware": self.firmware.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SimIOConfig":
        """Khóa vắng mặt lấy mặc định của các dataclass ở trên (một bộ mặc định duy nhất, đều là GIẢ ĐỊNH); khóa lạ
        hoặc gõ sai → ValueError."""
        _check_sim_keys("", d)
        version = int(d.get("schema_version", 0))
        if version != 1:
            raise ValueError(f"schema_version {version} không được hỗ trợ (cần 1)")
        for section in ("link", "actuator", "sensors"):
            _check_sim_keys(section, d.get(section, {}))
        a, s, link = d.get("actuator", {}), d.get("sensors", {}), d.get("link", {})
        fw = d.get("firmware", {})
        if not isinstance(fw, dict):
            raise ValueError("firmware: must be a JSON object")
        base = cls()
        a0, s0, l0 = base.actuator, base.sensors, base.link
        actuator = SimActuatorConfig(
            latency_ms=int(a.get("latency_ms", a0.latency_ms)),
            effort_deadzone_permille=int(a.get("effort_deadzone_permille", a0.effort_deadzone_permille)),
            speed_at_full_effort_mps=float(a.get("speed_at_full_effort_mps", a0.speed_at_full_effort_mps)),
            steer_offset_rad=(math.radians(float(a["steer_offset_deg"])) if "steer_offset_deg" in a
                              else a0.steer_offset_rad),
            estop_cuts_power=bool(a.get("estop_cuts_power", a0.estop_cuts_power)))
        sensors = SimSensorConfig(
            speed_available=bool(s.get("speed_available", s0.speed_available)),
            speed_latency_ms=int(s.get("speed_latency_ms", s0.speed_latency_ms)),
            speed_noise_std_mps=float(s.get("speed_noise_std_mps", s0.speed_noise_std_mps)),
            steer_available=bool(s.get("steer_available", s0.steer_available)),
            steer_latency_ms=int(s.get("steer_latency_ms", s0.steer_latency_ms)),
            steer_noise_std_rad=(math.radians(float(s["steer_noise_std_deg"])) if "steer_noise_std_deg" in s
                                 else s0.steer_noise_std_rad),
            imu_available=bool(s.get("imu_available", s0.imu_available)),
            gyro_noise_std_rad_s=(math.radians(float(s["gyro_noise_std_deg_s"])) if "gyro_noise_std_deg_s" in s
                                  else s0.gyro_noise_std_rad_s))
        return cls(tick_ms=int(d.get("tick_ms", base.tick_ms)),
                   link=SimLinkConfig(int(link.get("host_to_device_latency_ms", l0.host_to_device_latency_ms)),
                                      int(link.get("device_to_host_latency_ms", l0.device_to_host_latency_ms)),
                                      float(link.get("drop_probability", l0.drop_probability))),
                   actuator=actuator, sensors=sensors,
                   # khóa firmware vắng mặt lấy SIM_FIRMWARE_DEFAULT (cùng quy tắc với các mục khác); khóa lạ bị
                   # FirmwareConfig.from_dict từ chối
                   firmware=FirmwareConfig.from_dict({**base.firmware.to_dict(), **fw}),
                   seed=int(d.get("seed", base.seed)), notes=str(d.get("notes", "")))


def load_sim_io_config(path) -> tuple[SimIOConfig, VehicleConfig]:
    """Nạp `configs/vehicle_io_sim.json` và cấu hình xe mà nó trỏ tới (đường dẫn tương đối so với file)."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    vehicle_path = (path.parent / data.get("vehicle_config", "vehicle_default.json")).resolve()
    vehicle = VehicleConfig.from_dict(json.loads(vehicle_path.read_text(encoding="utf-8")))
    return SimIOConfig.from_dict(data), vehicle


class SimVehicleIO(VehicleIO):
    """Nhánh mô phỏng: laptop ↔ (trễ, mất gói) ↔ `FirmwareModel` → cơ cấu chấp hành (trễ, vùng chết) →
    `SimVehicle` → cảm biến (trễ, nhiễu) → `FirmwareModel`. Thời gian chỉ tiến khi gọi `advance()` hoặc khi một
    lệnh chờ (connect/arm...) cần, theo nhịp `tick_ms`; hoàn toàn xác định theo `seed`.

    `truth` là trạng thái thật của xe — chỉ để chấm điểm/test, bộ điều khiển không được đọc."""

    source_id = "sim_vehicle_io"

    def __init__(self, vehicle_cfg: VehicleConfig, config: SimIOConfig | None = None, *,
                 start: VehicleState | None = None, **kwargs):
        self.config = config or SimIOConfig()
        kwargs.setdefault("rng", random.Random(self.config.seed + 1))
        super().__init__(**kwargs)
        self.vehicle_cfg = vehicle_cfg
        self.vehicle = SimVehicle(vehicle_cfg, start or VehicleState(Pose(0.0, 0.0, 0.0), 0.0, 0.0, 0.0))
        self.t_ms = 0
        self._noise = random.Random(self.config.seed)
        self._link_rng = random.Random(self.config.seed + 2)
        self.firmware = FirmwareModel(self.config.firmware, now_ms=0, boot_id=self._noise.getrandbits(32),
                                      reset_reason=ResetReason.POWER_ON)
        self._h2d: deque[tuple[int, bytes]] = deque()
        self._d2h: deque[tuple[int, bytes]] = deque()
        self._actuator: deque[tuple[int, int, int]] = deque()
        self.applied_effort_permille = 0
        self.applied_steer_mrad = 0
        self._history: deque[tuple[int, float, float]] = deque([(0, self.vehicle.state.speed, self.vehicle.state.steer)])
        self._prev_speed = self.vehicle.state.speed
        self.link_up = True
        self.estop = False
        self.firmware_resets = 0
        self.frames_dropped = 0

    @classmethod
    def from_files(cls, sim_config_path, **kwargs) -> "SimVehicleIO":
        sim_cfg, vehicle_cfg = load_sim_io_config(sim_config_path)
        return cls(vehicle_cfg, sim_cfg, **kwargs)

    # ---- điều khiển mô phỏng -------------------------------------------------------------------------------------
    def now(self) -> float:
        return self.t_ms / 1000.0

    @property
    def truth(self) -> VehicleState:
        return self.vehicle.state

    def advance(self, seconds: float) -> list[VehicleTelemetry]:
        """Chạy mô phỏng thêm `seconds` (làm tròn theo tick); trả mọi telemetry nhận được kể từ lần
        `advance()`/`poll()` trước (cùng hàng đợi với `poll()`)."""
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("seconds must be finite and >= 0")
        with self._lock:
            for _ in range(round(seconds * 1000 / self.config.tick_ms)):
                self._pump()
                self.check()
            return self._take_new()

    def set_link(self, up: bool) -> None:
        """Rút/cắm cáp giả: khi mất, mọi byte hai chiều (kể cả đang trên đường) bị mất."""
        with self._lock:
            self.link_up = bool(up)
            if not up:
                self._h2d.clear()
                self._d2h.clear()

    def set_estop(self, active: bool) -> None:
        with self._lock:
            self.estop = bool(active)

    def reset_firmware(self, reason: ResetReason = ResetReason.WATCHDOG, *, hold_last_output_ms: int = 0) -> None:
        """Bo khởi động lại (panic/watchdog/esp_restart): mất phiên, về BOOT; byte đang tới bo bị mất.

        Trên ESP32-S3 các lần reset này chỉ reset CPU: LEDC và ma trận GPIO KHÔNG bị reset, nên nếu không làm gì thì
        xung ga cuối cùng vẫn phát qua in panic, ROM, bootloader, khởi tạo Arduino cho tới `setup_outputs()`.
        Mặc định (`hold_last_output_ms=0`) mô phỏng firmware CÓ hook panic/shutdown (`main.cpp`, `esc_line_low_now`)
        kéo chân ESC xuống thấp ngay, và giả định ESC coi mất xung là không kéo — cả hai CHƯA KIỂM trên bo, hành vi
        ESC khi mất xung CHƯA CHỐT. `hold_last_output_ms > 0` mô phỏng trường hợp xấu (hook không chạy, ví dụ sụt
        áp; hoặc bản firmware không có hook): cơ cấu chấp hành giữ effort cuối trong khoảng đó rồi mới theo đầu ra
        của bo mới khởi động (BOOT: 0). Độ rộng xung trong pha chạy bằng XTAL sau reset (có thể gấp đôi) không mô
        phỏng: CẦN ĐO."""
        if not isinstance(hold_last_output_ms, int) or isinstance(hold_last_output_ms, bool) or hold_last_output_ms < 0:
            raise ValueError("hold_last_output_ms must be an int >= 0")
        with self._lock:
            self.firmware = FirmwareModel(self.config.firmware, now_ms=self.t_ms, boot_id=self._noise.getrandbits(32),
                                          reset_reason=reason)
            self._h2d.clear()
            self._actuator.clear()
            if hold_last_output_ms:
                # Mục chặn đầu hàng đợi: tới hạn mới được lấy, kéo theo mọi đầu ra của bo mới xếp phía sau nó.
                self._actuator.append((self.t_ms + hold_last_output_ms, 0, self.applied_steer_mrad))
            else:
                self.applied_effort_permille = 0
            self.firmware_resets += 1

    # ---- mô hình ---------------------------------------------------------------------------------------------------
    def _write(self, data: bytes) -> None:
        if not self.link_up or (self.config.link.drop_probability and
                                self._link_rng.random() < self.config.link.drop_probability):
            self.frames_dropped += 1
            return
        self._h2d.append((self.t_ms + self.config.link.host_to_device_latency_ms, bytes(data)))

    def _actuator_speed(self, effort_permille: int) -> float:
        a = self.config.actuator
        if self.estop and a.estop_cuts_power:
            return 0.0
        magnitude = abs(effort_permille)
        if magnitude <= a.effort_deadzone_permille:
            return 0.0
        v = a.speed_at_full_effort_mps * (magnitude - a.effort_deadzone_permille) / (1000 - a.effort_deadzone_permille)
        return math.copysign(v, effort_permille)

    def _delayed(self, t: int, latency_ms: int) -> tuple[float, float]:
        target = t - latency_ms
        value = self._history[0]
        for entry in self._history:
            if entry[0] > target:
                break
            value = entry
        return value[1], value[2]

    def _sensor_inputs(self, t: int, truth: VehicleState, dt_s: float) -> FirmwareInputs:
        s = self.config.sensors
        values: dict = {"estop": self.estop}
        if s.speed_available:
            speed, _ = self._delayed(t, s.speed_latency_ms)
            values.update(speed_valid=True,
                          speed_mm_s=round_half_away((speed + self._noise.gauss(0.0, s.speed_noise_std_mps)) * 1000))
        if s.steer_available:
            _, steer = self._delayed(t, s.steer_latency_ms)
            values.update(steer_valid=True,
                          steer_mrad=round_half_away((steer + self._noise.gauss(0.0, s.steer_noise_std_rad)) * 1000))
        if s.imu_available:
            yaw_rate = truth.speed * math.tan(truth.steer) / self.vehicle_cfg.wheelbase
            values.update(imu_valid=True,
                          gyro_z_mrad_s=round_half_away((yaw_rate + self._noise.gauss(0.0, s.gyro_noise_std_rad_s)) * 1000),
                          accel_x_mm_s2=round_half_away((truth.speed - self._prev_speed) / dt_s * 1000),
                          accel_y_mm_s2=round_half_away(truth.speed * yaw_rate * 1000))
        return FirmwareInputs(**values)

    def _pump(self) -> None:
        cfg = self.config
        tick = cfg.tick_ms
        while self._actuator and self._actuator[0][0] <= self.t_ms:
            _, self.applied_effort_permille, self.applied_steer_mrad = self._actuator.popleft()
        steer_target = self.applied_steer_mrad / 1000.0 + cfg.actuator.steer_offset_rad
        self._prev_speed = self.vehicle.state.speed
        self.vehicle.step(tick / 1000.0, self._actuator_speed(self.applied_effort_permille), steer_target)
        self.t_ms += tick
        t = self.t_ms
        truth = self.vehicle.state
        self._history.append((t, truth.speed, truth.steer))
        horizon = t - max(cfg.sensors.speed_latency_ms, cfg.sensors.steer_latency_ms)
        while len(self._history) > 1 and self._history[1][0] <= horizon:
            self._history.popleft()

        while self._h2d and self._h2d[0][0] <= t:
            self.firmware.receive(self._h2d.popleft()[1], t)
        out = self.firmware.step(t, self._sensor_inputs(t, truth, tick / 1000.0))
        self._actuator.append((t + cfg.actuator.latency_ms, out.effort_permille, out.steer_ref_mrad))
        tx = self.firmware.take_tx()
        if tx:
            if not self.link_up or (cfg.link.drop_probability and self._link_rng.random() < cfg.link.drop_probability):
                self.frames_dropped += 1
            else:
                self._d2h.append((t + cfg.link.device_to_host_latency_ms, tx))
        while self._d2h and self._d2h[0][0] <= t:
            self._on_bytes(self._d2h.popleft()[1], t / 1000.0)
