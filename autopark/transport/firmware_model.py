"""Bản tham chiếu Python của logic firmware ESP32-S3 (kế hoạch mục 9, "Khi chưa đủ phần cứng").

Đây là thứ `firmware/esp32_vehicle/src/core/vehicle_core.cpp` phải khớp: cùng máy trạng thái, cùng kiểm tra
phiên/số thứ tự, cùng watchdog, cùng giới hạn và dốc, cùng vòng tốc độ, cùng byte telemetry. Vector mẫu chung
(`autopark.transport.vectors`) được sinh từ lớp này và bộ test C++ đọc lại chúng. Khi hai bên lệch nhau, sửa bên
sai rồi sinh lại vector; không sửa vector bằng tay.

Toàn bộ phép tính là số nguyên (tốc độ trong µm/s, góc trong µrad, thời gian ms uint32 có quay vòng), để C++ và
Python cho kết quả giống từng bit: gia tốc mm/s² × dt ms = µm/s và tốc độ đổi lái mrad/s × dt ms = µrad, không
có làm tròn. Phép chia là chia cắt về 0 (`tdiv`), đúng ngữ nghĩa `/` của C++ với số có dấu.

Đồng hồ được TIÊM: mọi hàm nhận `now_ms` (tương đương `millis()` trên bo). Mô hình không đọc đồng hồ hệ thống.

Máy trạng thái (docs/PHAN_CUNG_VA_HIEU_CHUAN.md):
    BOOT ──hết boot_hold──> DISARMED ──ARM──> ARMED ──COMMAND enable──> RUNNING
    RUNNING ──lệnh hết hạn / enable=0──> ARMED (đầu ra dốc về trung tính)
    ARMED/RUNNING ──DISARM / mất liên lạc / HELLO mới──> DISARMED
    mọi trạng thái ──E-stop / lỗi──> FAULT (chốt) ──CLEAR_FAULT khi hết nguyên nhân──> DISARMED
Không có đường nào từ DISARMED sang RUNNING mà không qua ARM rồi một COMMAND enable gửi SAU ARM: khởi động lại,
kết nối lại, hết hạn liên lạc đều kết thúc ở DISARMED ("reconnect không tự chạy tiếp").

Ngoài phạm vi (CHƯA CHỐT theo bo thực): chân GPIO, mức tín hiệu, ánh xạ effort → độ rộng xung ESC, ánh xạ góc →
xung servo, hành vi lùi của ESC, ngưỡng điện áp. Mô hình dừng ở `effort_permille` và `steer_ref_mrad`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

from .protocol import (COMMAND_FLAG_ENABLE, HOST_TO_DEVICE, N_TOF, NO_COMMAND_AGE, Ack, Action, Command, Fault,
                       FaultMsg, FrameParser, Hello, HelloAck, Limits, Message, Request, ResetReason, Result, State,
                       StopReason, TelemetryFlag, TelemetryMsg, encode_frame)

U32 = 0xFFFFFFFF
U16 = 0xFFFF
TX_BUFFER_SIZE = 1024   # = VehicleCore::kTxBufferSize (vehicle_core.h), bộ đệm tĩnh của firmware; đổi một bên phải đổi bên kia


def elapsed_ms(now: int, then: int) -> int:
    """Khoảng thời gian uint32 có quay vòng (millis() tràn sau 49,7 ngày)."""
    return (now - then) & U32


def tdiv(a: int, b: int) -> int:
    """Chia nguyên cắt về 0 như C++ (`-7 / 2 == -3`), khác `//` của Python."""
    if b == 0:
        raise ZeroDivisionError("tdiv by zero")
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def sign(x: int) -> int:
    return (x > 0) - (x < 0)


def clamp(x: int, lo: int, hi: int) -> int:
    return lo if x < lo else hi if x > hi else x


def sat16(x: int) -> int:
    return clamp(x, -32768, 32767)


def satu16(x: int) -> int:
    return clamp(x, 0, U16)


@dataclass(frozen=True)
class FirmwareConfig:
    """Tham số firmware. Giới hạn chuyển động mặc định lấy theo `configs/vehicle_default.json` (GIẢ ĐỊNH, chưa đo
    MN300); thời gian và hệ số vòng tốc độ là giá trị khởi đầu để thử, không phải kết quả hiệu chỉnh."""

    boot_hold_ms: int = 1000                # giữ trung tính sau khởi động (ESC thường cần; thời lượng CHƯA CHỐT)
    max_speed_mm_s: int = 300
    max_steer_mrad: int = 524               # 30°
    max_steer_rate_mrad_s: int = 1571       # 90°/s
    max_accel_mm_s2: int = 300
    max_decel_mm_s2: int = 600
    stop_decel_mm_s2: int = 600             # dốc về trung tính khi hết lệnh / disarm / mất liên lạc
    max_validity_ms: int = 300              # thời hạn một lệnh bị kẹp về giá trị này
    link_timeout_ms: int = 500              # không nhận thông điệp hợp lệ nào trong khoảng này → DISARMED
    default_telemetry_period_ms: int = 50
    min_telemetry_period_ms: int = 20
    max_telemetry_period_ms: int = 1000
    max_tick_gap_ms: int = 100              # vòng điều khiển trễ quá mức này → lỗi LOOP_OVERRUN
    direction_change_hold_ms: int = 300     # đứng ở 0 bao lâu trước khi đổi chiều (CHƯA CHỐT theo ESC thật)
    standstill_mm_s: int = 10               # "đã dừng" khi có phản hồi tốc độ
    ff_permille_per_mps: int = 2000         # feedforward: effort ‰ cho 1 m/s (giả định)
    deadzone_comp_permille: int = 100       # bù vùng chết ESC (giả định; đo ở giai đoạn 4-5)
    kp_permille_per_mps: int = 500          # chọn trên mô hình mô phỏng giả định (docs mục 10), chưa chỉnh trên xe
    ki_permille_per_m: int = 4000           # ‰ effort cho mỗi (m/s × s) sai số tích lũy
    integ_limit_permille: int = 300
    # Trần |effort| (tức ga ra ESC), độc lập với max_speed_mm_s: kẹp max_speed chỉ áp lên MỤC TIÊU, không giới hạn tốc
    # độ thật khi chạy mạch hở (feedforward 300 mm/s = 700 ‰ với hệ số giả định) hay khi encoder báo sai. 250 ‰ là số
    # thận trọng cho lần thử đầu trên xe, CHƯA CHỐT; mô phỏng dùng 1000 (vehicle_io.SIM_FIRMWARE_DEFAULT).
    max_effort_permille: int = 250
    stall_effort_permille: int = 200        # vòng kín: |effort| ≥ ngưỡng này mà xe không đi theo chiều mục tiêu ...
    stall_timeout_ms: int = 1000            # ... liên tục ngần này ms → FAULT STALL (0 = tắt; CHƯA CHỐT)
    min_supply_mv: int = 0                 # 0 = tắt kiểm tra điện áp (ngưỡng CHƯA CHỐT)
    require_speed_feedback: bool = False    # True: đang chạy mà mất phản hồi tốc độ → FAULT
    fw_major: int = 1
    fw_minor: int = 0
    tx_capacity: int = 512                  # byte chờ gửi, 1..TX_BUFFER_SIZE (1024); đầy thì bỏ khung mới, đếm tx_overflow

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name == "require_speed_feedback":
                if not isinstance(value, bool):
                    raise ValueError("require_speed_feedback must be bool")
                continue
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{f.name} must be an int")
            if value < 0 or value > (255 if f.name.startswith("fw_") else 65535):
                raise ValueError(f"{f.name}={value} out of range")
        for name in ("max_speed_mm_s", "max_steer_mrad", "max_steer_rate_mrad_s", "max_accel_mm_s2",
                     "max_decel_mm_s2", "stop_decel_mm_s2", "max_validity_ms", "link_timeout_ms",
                     "min_telemetry_period_ms", "max_tick_gap_ms", "tx_capacity"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        if not 1 <= self.max_effort_permille <= 1000:
            raise ValueError(f"max_effort_permille={self.max_effort_permille} must be in [1, 1000]")
        if not 1 <= self.stall_effort_permille <= self.max_effort_permille:
            # Ngưỡng STALL cao hơn trần thì effort không bao giờ chạm ngưỡng: kiểm STALL bị tắt ngầm.
            raise ValueError("stall_effort_permille must be in [1, max_effort_permille]")
        if self.tx_capacity > TX_BUFFER_SIZE:
            # Firmware C++ có bộ đệm gửi tĩnh TX_BUFFER_SIZE byte: cấu hình lớn hơn thì Python và C++ bỏ khác khung nhau.
            raise ValueError(f"tx_capacity={self.tx_capacity} vượt bộ đệm gửi của firmware ({TX_BUFFER_SIZE} byte)")
        if self.max_speed_mm_s > 32767 or self.max_steer_mrad > 32767:
            raise ValueError("speed/steer limits must fit int16")
        if not (self.min_telemetry_period_ms <= self.default_telemetry_period_ms <= self.max_telemetry_period_ms):
            raise ValueError("default telemetry period must lie in [min, max]")

    def limits(self) -> Limits:
        return Limits(self.max_speed_mm_s, self.max_steer_mrad, self.max_steer_rate_mrad_s, self.max_accel_mm_s2,
                      self.max_decel_mm_s2, self.stop_decel_mm_s2, self.max_validity_ms, self.link_timeout_ms)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FirmwareConfig":
        known = {f.name for f in fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"unknown firmware config keys: {sorted(unknown)}")
        return cls(**d)


@dataclass(frozen=True)
class FirmwareInputs:
    """Một lần lấy mẫu ngõ vào của bo. Trường `*_valid = False` nghĩa là không có số đo dùng được (chưa lắp, lỗi,
    timeout); giá trị đi kèm khi đó bị bỏ qua và telemetry ghi 0 cùng cờ hợp lệ = 0."""

    estop: bool = False
    speed_valid: bool = False
    speed_mm_s: int = 0
    steer_valid: bool = False
    steer_mrad: int = 0
    imu_valid: bool = False
    gyro_z_mrad_s: int = 0
    accel_x_mm_s2: int = 0
    accel_y_mm_s2: int = 0
    tof_valid_mask: int = 0
    tof_mm: tuple[int, int, int, int] = (0, 0, 0, 0)
    supply_valid: bool = False
    supply_mv: int = 0

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name == "tof_mm":
                if len(value) != N_TOF or not all(isinstance(v, int) and not isinstance(v, bool) for v in value):
                    raise ValueError(f"tof_mm needs {N_TOF} ints")
            elif f.type == "bool":
                if not isinstance(value, bool):
                    raise ValueError(f"{f.name} must be bool")
            elif not isinstance(value, int) or isinstance(value, bool) or not -2**31 <= value < 2**31:
                raise ValueError(f"{f.name} must be an int32 (firmware input), got {value!r}")

    def to_dict(self) -> dict:
        """Chỉ các trường khác mặc định (dạng dùng trong vector mẫu)."""
        default = FirmwareInputs()
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value != getattr(default, f.name):
                out[f.name] = list(value) if isinstance(value, tuple) else value
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "FirmwareInputs":
        values = dict(d)
        if "tof_mm" in values:
            values["tof_mm"] = tuple(values["tof_mm"])
        return cls(**values)


@dataclass(frozen=True)
class FirmwareOutputs:
    state: State
    speed_ref_mm_s: int
    steer_ref_mrad: int
    effort_permille: int      # |effort| ≤ max_effort_permille (≤ 1000); ánh xạ sang xung ESC là CHƯA CHỐT (main.cpp)


class FirmwareModel:
    """Logic firmware, không phụ thuộc phần cứng. Dùng: `receive(bytes, now_ms)` khi có byte từ laptop,
    `step(now_ms, inputs)` mỗi chu kỳ điều khiển (10 ms trên bo), `take_tx()` lấy byte cần gửi lên laptop.

    Trong một chu kỳ, bo xử lý byte nhận được TRƯỚC rồi mới `step` (cùng thứ tự với vector mẫu)."""

    def __init__(self, config: FirmwareConfig | None = None, *, now_ms: int = 0, boot_id: int = 0,
                 reset_reason: int = ResetReason.POWER_ON):
        self.cfg = config or FirmwareConfig()
        if not 0 <= boot_id <= U32:
            raise ValueError("boot_id must fit uint32")
        self.boot_ms = now_ms & U32
        self.boot_id = boot_id
        self.reset_reason = int(reset_reason)
        self.boot_done = False
        self.state = State.BOOT
        self.fault = Fault.NONE
        self.stop_reason = StopReason.BOOT
        # phiên và liên lạc
        self.session_id = 0
        self.last_rx_seq = 0
        self.last_rx_ms = self.boot_ms
        self.telemetry_period_ms = self.cfg.default_telemetry_period_ms
        self.last_tel_ms: int | None = None
        self.tx_seq = 0
        self.tx = bytearray()
        self.tx_overflow = 0
        self.rejects = 0
        self.parser = FrameParser(accept_types=HOST_TO_DEVICE)
        # lệnh
        self.cmd_active = False
        self.cmd_speed_mm_s = 0
        self.cmd_steer_mrad = 0
        self.cmd_rx_ms = self.boot_ms
        self.cmd_validity_ms = 0
        self.has_cmd = False
        self.last_cmd_seq = 0
        # đầu ra
        self.speed_ref_um = 0
        self.steer_ref_urad = 0
        self.last_dir = 0
        self.zero_since_ms: int | None = self.boot_ms
        self.integ = 0                         # tích phân sai số, đơn vị ‰ × 1e9
        self.effort_permille = 0
        self.loop_closed = False
        self.stall_since_ms: int | None = None    # lúc điều kiện STALL bắt đầu (liên tục); None = không đang nghi
        self.inputs = FirmwareInputs()
        self.last_tick_ms: int | None = None

    # ---- tiện ích ------------------------------------------------------------------------------------------------
    @property
    def speed_ref_mm_s(self) -> int:
        return tdiv(self.speed_ref_um, 1000)

    @property
    def steer_ref_mrad(self) -> int:
        return tdiv(self.steer_ref_urad, 1000)

    def outputs(self) -> FirmwareOutputs:
        return FirmwareOutputs(self.state, self.speed_ref_mm_s, self.steer_ref_mrad, self.effort_permille)

    def take_tx(self) -> bytes:
        data = bytes(self.tx)
        self.tx.clear()
        return data

    def _send(self, msg_factory) -> None:
        """`msg_factory(sequence)` → thông điệp. Số thứ tự tăng cả khi khung bị bỏ vì đầy bộ đệm (laptop thấy khoảng hở)."""
        frame = encode_frame(msg_factory(self.tx_seq))
        self.tx_seq = (self.tx_seq + 1) & U16
        if len(self.tx) + len(frame) > self.cfg.tx_capacity:
            self.tx_overflow += 1
            return
        self.tx += frame

    def _ack(self, msg: Message, result: Result) -> None:
        if result != Result.OK:
            self.rejects += 1
        self._send(lambda seq: Ack(msg.session_id, seq, int(msg.TYPE), msg.sequence, int(result), int(self.state),
                                   int(self.fault)))

    def _clear_cmd(self) -> None:
        self.cmd_active = False
        self.cmd_speed_mm_s = 0
        self.cmd_steer_mrad = 0

    def _disarm(self, reason: StopReason) -> None:
        self.state = State.DISARMED
        self.stop_reason = reason
        self._clear_cmd()

    def _latch_fault(self, code: Fault, detail: int, now: int) -> None:
        if self.state == State.FAULT:
            return                             # giữ lỗi đầu tiên (nguyên nhân gốc)
        self.state = State.FAULT
        self.fault = code
        self.stop_reason = StopReason.FAULT
        self._clear_cmd()
        self.speed_ref_um = 0
        self.effort_permille = 0
        self.integ = 0
        if self.session_id:
            self._send(lambda seq: FaultMsg(self.session_id, seq, int(code), int(State.FAULT), now, satu16(detail)))

    # ---- nhận ----------------------------------------------------------------------------------------------------
    def receive(self, data: bytes, now_ms: int) -> None:
        now = now_ms & U32
        for msg in self.parser.feed(data):
            self._handle(msg, now)

    def _handle(self, msg: Message, now: int) -> None:
        if isinstance(msg, Hello):
            self._handle_hello(msg, now)
            return
        result = self._check_link(msg)
        if result != Result.OK:
            self._ack(msg, result)
            return
        self.last_rx_seq = msg.sequence
        self.last_rx_ms = now
        if isinstance(msg, Request):
            self._handle_request(msg, now)
        elif isinstance(msg, Command):
            self._handle_command(msg, now)

    def _check_link(self, msg: Message) -> Result:
        if self.session_id == 0:
            return Result.NO_SESSION
        if msg.session_id != self.session_id:
            return Result.WRONG_SESSION
        diff = (msg.sequence - self.last_rx_seq) & U16
        if diff == 0:
            return Result.DUPLICATE
        if diff >= 0x8000:
            return Result.OUT_OF_ORDER
        return Result.OK

    def _handle_hello(self, msg: Hello, now: int) -> None:
        if msg.session_id == 0:
            self._ack(msg, Result.BAD_FIELD)
            return
        self.session_id = msg.session_id
        self.last_rx_seq = msg.sequence
        self.last_rx_ms = now
        period = msg.telemetry_period_ms or self.cfg.default_telemetry_period_ms
        self.telemetry_period_ms = clamp(period, self.cfg.min_telemetry_period_ms, self.cfg.max_telemetry_period_ms)
        if self.state in (State.ARMED, State.RUNNING):
            self._disarm(StopReason.NEW_SESSION)
        self.has_cmd = False
        self.last_cmd_seq = 0
        self.last_tel_ms = None
        self._send(lambda seq: HelloAck(self.session_id, seq, msg.sequence, self.cfg.fw_major, self.cfg.fw_minor,
                                        self.boot_id, self.reset_reason, int(self.state), self.telemetry_period_ms,
                                        self.cfg.limits()))

    def _handle_request(self, msg: Request, now: int) -> None:
        action = msg.action
        if action == Action.ARM:
            if self.state == State.BOOT:
                result = Result.NOT_READY
            elif self.state == State.FAULT:
                result = Result.FAULT_ACTIVE
            elif self.inputs.estop:
                result = Result.ESTOP_ACTIVE
            else:
                if self.state == State.DISARMED:
                    self.state = State.ARMED
                    self._clear_cmd()
                result = Result.OK
        elif action == Action.DISARM:
            if self.state in (State.ARMED, State.RUNNING):
                self._disarm(StopReason.HOST_DISARM)
            result = Result.OK
        elif action == Action.CLEAR_FAULT:
            if self.state != State.FAULT:
                result = Result.OK
            elif self.inputs.estop:
                result = Result.ESTOP_ACTIVE
            elif (self.fault == Fault.SUPPLY_LOW and self.cfg.min_supply_mv and
                  (not self.inputs.supply_valid or self.inputs.supply_mv < self.cfg.min_supply_mv)):
                result = Result.FAULT_ACTIVE
            else:
                self.state = State.DISARMED if self.boot_done else State.BOOT
                self.fault = Fault.NONE
                result = Result.OK
        elif action == Action.PING:
            result = Result.OK
        else:
            result = Result.BAD_FIELD
        self._ack(msg, result)

    def _handle_command(self, msg: Command, now: int) -> None:
        if (msg.flags & ~COMMAND_FLAG_ENABLE & 0xFF) != 0 or msg.validity_ms == 0:
            result = Result.BAD_FIELD
        elif self.state == State.BOOT:
            result = Result.NOT_READY
        elif self.state == State.FAULT:
            result = Result.FAULT_ACTIVE
        elif self.state == State.DISARMED:
            result = Result.BAD_STATE
        else:
            self.last_cmd_seq = msg.sequence
            self.cmd_rx_ms = now
            self.has_cmd = True
            if msg.enable:
                self.cmd_active = True
                self.cmd_speed_mm_s = msg.speed_mm_s
                self.cmd_steer_mrad = msg.steer_mrad
                self.cmd_validity_ms = min(msg.validity_ms, self.cfg.max_validity_ms)
                self.state = State.RUNNING
            else:
                if self.state == State.RUNNING:
                    self.stop_reason = StopReason.ENABLE_CLEARED
                self.state = State.ARMED
                self._clear_cmd()
            return
        self._ack(msg, result)

    # ---- chu kỳ điều khiển ---------------------------------------------------------------------------------------
    def step(self, now_ms: int, inputs: FirmwareInputs | None = None) -> FirmwareOutputs:
        cfg = self.cfg
        now = now_ms & U32
        inputs = inputs or FirmwareInputs()
        gap = 0 if self.last_tick_ms is None else elapsed_ms(now, self.last_tick_ms)
        dt = min(gap, cfg.max_tick_gap_ms)
        self.last_tick_ms = now
        self.inputs = inputs

        if gap > cfg.max_tick_gap_ms:
            self._latch_fault(Fault.LOOP_OVERRUN, gap, now)
        if inputs.estop:
            self._latch_fault(Fault.ESTOP, 0, now)
        if cfg.min_supply_mv and inputs.supply_valid and inputs.supply_mv < cfg.min_supply_mv:
            self._latch_fault(Fault.SUPPLY_LOW, inputs.supply_mv, now)
        if cfg.require_speed_feedback and self.state == State.RUNNING and not inputs.speed_valid:
            self._latch_fault(Fault.FEEDBACK_LOST, 0, now)

        if not self.boot_done and elapsed_ms(now, self.boot_ms) >= cfg.boot_hold_ms:
            self.boot_done = True
        if self.state == State.BOOT and self.boot_done:
            self.state = State.DISARMED
        if self.state in (State.ARMED, State.RUNNING) and elapsed_ms(now, self.last_rx_ms) >= cfg.link_timeout_ms:
            self._disarm(StopReason.LINK_TIMEOUT)
        if self.state == State.RUNNING and elapsed_ms(now, self.cmd_rx_ms) >= self.cmd_validity_ms:
            self.state = State.ARMED
            self.stop_reason = StopReason.COMMAND_TIMEOUT
            self._clear_cmd()

        self._update_references(dt, now)
        self._update_speed_loop(dt)
        self._check_stall(now)
        if self.session_id and (self.last_tel_ms is None or
                                elapsed_ms(now, self.last_tel_ms) >= self.telemetry_period_ms):
            self._send(lambda seq: self._telemetry(seq, now))
            # Lịch theo hạn trước (không theo `now`): chu kỳ trung bình đúng bằng giá trị báo trong HELLO_ACK kể cả
            # khi nó không là bội của chu kỳ điều khiển (25 ms → khoảng cách 30/20 ms xen kẽ). Mỗi step gửi tối đa
            # một mẫu; tụt sau quá một chu kỳ (vòng trễ, LOOP_OVERRUN) thì bắt nhịp lại từ `now`, không gửi dồn.
            if self.last_tel_ms is None:
                self.last_tel_ms = now
            else:
                self.last_tel_ms = (self.last_tel_ms + self.telemetry_period_ms) & U32
                if elapsed_ms(now, self.last_tel_ms) >= self.telemetry_period_ms:
                    self.last_tel_ms = now
        return self.outputs()

    def _reverse_gate_open(self, now: int) -> bool:
        if self.zero_since_ms is None or elapsed_ms(now, self.zero_since_ms) < self.cfg.direction_change_hold_ms:
            return False
        return not self.inputs.speed_valid or abs(self.inputs.speed_mm_s) <= self.cfg.standstill_mm_s

    @staticmethod
    def _ramp(ref: int, target: int, up: int, down: int) -> int:
        """Một bước dốc: đổi chiều hoặc về 0 thì giảm độ lớn tới 0 (không vượt qua 0); cùng chiều thì tăng theo
        `up`, giảm theo `down`."""
        if ref != 0 and sign(target) != sign(ref):
            return sign(ref) * max(0, abs(ref) - down)
        if abs(target) >= abs(ref):
            return ref + sign(target) * min(abs(target) - abs(ref), up)
        return ref - sign(ref) * min(abs(ref) - abs(target), down)

    def _update_references(self, dt: int, now: int) -> None:
        cfg = self.cfg
        if self.state == State.FAULT:
            self.speed_ref_um = 0
        else:
            if self.state == State.RUNNING:
                target = clamp(self.cmd_speed_mm_s, -cfg.max_speed_mm_s, cfg.max_speed_mm_s) * 1000
                decel = cfg.max_decel_mm_s2
            else:
                target = 0
                decel = cfg.stop_decel_mm_s2
            if (self.speed_ref_um == 0 and target != 0 and self.last_dir != 0 and sign(target) != self.last_dir
                    and not self._reverse_gate_open(now)):
                target = 0                     # đổi chiều: đứng ở 0 đủ lâu (và đã dừng nếu đo được) mới đi tiếp
            self.speed_ref_um = self._ramp(self.speed_ref_um, target, cfg.max_accel_mm_s2 * dt, decel * dt)
        if self.speed_ref_um == 0:
            if self.zero_since_ms is None:
                self.zero_since_ms = now
        else:
            self.zero_since_ms = None
            self.last_dir = sign(self.speed_ref_um)

        step = cfg.max_steer_rate_mrad_s * dt
        if self.state == State.RUNNING:
            target = clamp(self.cmd_steer_mrad, -cfg.max_steer_mrad, cfg.max_steer_mrad) * 1000
        elif self.state != State.FAULT and self.speed_ref_um == 0:
            target = 0                         # đã về 0 thì mới trả lái về giữa; đang giảm tốc thì giữ góc
        else:
            return
        self.steer_ref_urad += clamp(target - self.steer_ref_urad, -step, step)

    def _update_speed_loop(self, dt: int) -> None:
        cfg = self.cfg
        ref = self.speed_ref_um
        self.loop_closed = False
        if self.state == State.FAULT or ref == 0:
            self.effort_permille = 0
            self.integ = 0
            return
        ff = sign(ref) * (cfg.deadzone_comp_permille + tdiv(cfg.ff_permille_per_mps * abs(ref), 1_000_000))
        cap = cfg.max_effort_permille          # trần |effort| cho cả mạch hở lẫn vòng kín
        if not self.inputs.speed_valid:
            self.integ = 0
            self.effort_permille = clamp(ff, -cap, cap)
            return
        self.loop_closed = True
        # Kẹp số đo về int16 (như trên dây) để phía C++ tính int64 không bao giờ tràn với số đo vô lý.
        error_um = ref - sat16(self.inputs.speed_mm_s) * 1000
        u = ff + tdiv(cfg.kp_permille_per_mps * error_um, 1_000_000) + tdiv(self.integ, 1_000_000_000)
        sat_hi, sat_lo = u > cap, u < -cap     # chống bão hòa tích phân theo đúng trần đang dùng
        u = clamp(u, -cap, cap)
        if ref > 0 and u < 0:
            u, sat_lo = 0, True                # không đẩy ngược chiều (phanh/lùi của ESC là CHƯA CHỐT)
        elif ref < 0 and u > 0:
            u, sat_hi = 0, True
        if not ((sat_hi and error_um > 0) or (sat_lo and error_um < 0)):
            limit = cfg.integ_limit_permille * 1_000_000_000
            self.integ = clamp(self.integ + cfg.ki_permille_per_m * error_um * dt, -limit, limit)
        self.effort_permille = u

    def _check_stall(self, now: int) -> None:
        """Kiểm hợp lý vòng kín: |effort| ≥ stall_effort_permille mà số đo không đi theo chiều mục tiêu (encoder kẹt 0
        với cờ hợp lệ, encoder đảo dấu, bánh kẹt) liên tục ≥ stall_timeout_ms → FAULT STALL. Chỉ kiểm được khi có phản
        hồi tốc độ (vòng kín); chạy mạch hở thì chỉ còn trần effort bảo vệ."""
        cfg = self.cfg
        stalled = (cfg.stall_timeout_ms > 0 and self.loop_closed
                   and abs(self.effort_permille) >= cfg.stall_effort_permille
                   and abs(self.speed_ref_um) > cfg.standstill_mm_s * 1000
                   and sign(self.speed_ref_um) * sat16(self.inputs.speed_mm_s) <= cfg.standstill_mm_s)
        if not stalled:
            self.stall_since_ms = None
        elif self.stall_since_ms is None:
            self.stall_since_ms = now
        elif elapsed_ms(now, self.stall_since_ms) >= cfg.stall_timeout_ms:
            self.stall_since_ms = None
            self._latch_fault(Fault.STALL, abs(self.effort_permille), now)

    def _telemetry(self, seq: int, now: int) -> TelemetryMsg:
        i = self.inputs
        flags = TelemetryFlag(0)
        if i.estop:
            flags |= TelemetryFlag.ESTOP_INPUT
        if self.session_id and elapsed_ms(now, self.last_rx_ms) < self.cfg.link_timeout_ms:
            flags |= TelemetryFlag.LINK_OK
        if self.cmd_active:
            flags |= TelemetryFlag.CMD_ACTIVE
        if i.speed_valid:
            flags |= TelemetryFlag.SPEED_VALID
        if i.steer_valid:
            flags |= TelemetryFlag.STEER_VALID
        if i.imu_valid:
            flags |= TelemetryFlag.IMU_VALID
        if i.supply_valid:
            flags |= TelemetryFlag.SUPPLY_VALID
        if self.loop_closed:
            flags |= TelemetryFlag.SPEED_LOOP_CLOSED
        mask = i.tof_valid_mask & ((1 << N_TOF) - 1)
        tof = tuple(satu16(i.tof_mm[k]) if mask & (1 << k) else 0 for k in range(N_TOF))
        cmd_age = min(elapsed_ms(now, self.cmd_rx_ms), NO_COMMAND_AGE - 1) if self.has_cmd else NO_COMMAND_AGE
        return TelemetryMsg(
            self.session_id, seq, now, int(self.state), int(self.fault), int(self.stop_reason), int(flags),
            self.last_cmd_seq, cmd_age,
            sat16(i.speed_mm_s) if i.speed_valid else 0,
            sat16(i.steer_mrad) if i.steer_valid else 0,
            sat16(self.speed_ref_mm_s), sat16(self.steer_ref_mrad), self.effort_permille,
            sat16(i.gyro_z_mrad_s) if i.imu_valid else 0,
            sat16(i.accel_x_mm_s2) if i.imu_valid else 0,
            sat16(i.accel_y_mm_s2) if i.imu_valid else 0,
            mask, tof,
            satu16(i.supply_mv) if i.supply_valid else 0,
            satu16(self.parser.stats.errors), satu16(self.rejects))
