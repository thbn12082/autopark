"""Kết nối xe (thêm 26/11/2026): một kết nối tới bo ESP32 dùng chung cho cả cửa sổ AutoPark, và tab để mở/ngắt nó.

```
Kết nối xe (tab) ── CarConnection (một đối tượng cho cả app) ──┬── Lái tay: đặt command_source, đọc trạng thái
                                                               └── (các tab sau này)
CarConnection
├── Xe thật ..... ssh xe@<ip> → cầu nối trên Pi → USB → ESP32 (transport/ssh_serial.py)
├── Mô phỏng .... SimVehicleIO + FirmwareModel, không cần xe
└── nhịp 50 Hz .. đọc telemetry; có command_source thì gửi lệnh của nó, không thì chỉ PING giữ liên lạc
```

Kết nối xong là bo được ARM, nhưng xe không chạy tới khi một tab (Lái tay) đặt `command_source` và gửi tốc độ khác 0.
Mỗi lệnh có hạn ngắn (150–250 ms), nên app treo hay Wi-Fi rớt thì firmware tự về trung tính. `stop()` (DỪNG) gửi lệnh
dừng rồi DISARM; `arm()` (Bật lái) cho chạy lại. Tab Kết nối xe đóng (thoát app) thì kết nối được ngắt: xe về trung
tính, DISARM, đóng SSH.
"""
from __future__ import annotations

import math
from pathlib import Path
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from autopark.transport.protocol import ResetReason, State
from autopark.transport.vehicle_io import SerialVehicleIO, SimVehicleIO, VehicleIO, VehicleIOError, VehicleLimits
from autopark.ui import theme

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SIM_CONFIG = PROJECT_ROOT / "configs" / "vehicle_io_sim.json"

TICK_MS = 20                      # 50 lệnh/giây, như thu_ban_pwm.py
PING_IDLE_S = 0.2
# Góc lái hết cỡ lấy từ giới hạn bo báo trong HELLO_ACK. Env esp32s3_16mb_pwm đặt nó bằng nửa tầm servo (1 mrad ≈ 1 µs
# quanh 1500; AP_MAX_STEER_MRAD, platformio.ini), nên vô lăng hết cỡ = servo ở mép giới hạn firmware. Chưa kết nối thì
# hiển thị theo giá trị này.
DEFAULT_STEER_LIMIT_RAD = 0.30
SERVO_CENTER_US = 1500
SERVO_US_PER_RAD = 1000
FALLBACK_MAX_SPEED_MPS = 0.30
LOG_LIMIT = 300

MODES = (("pi", "Xe thật (qua Pi)"), ("sim", "Mô phỏng"))
VALIDITY_S = {"pi": 0.25, "sim": 0.15}
TELEMETRY_TIMEOUT_S = {"pi": 0.5, "sim": 0.3}
STEPS = {
    "pi": ("SSH vào Pi", "Mở ESP32 trên Pi", "Bắt tay với bo (HELLO)", "Bật lái (ARM)"),
    "sim": ("Dựng xe mô phỏng", "Firmware mô phỏng khởi động", "Bắt tay với bo (HELLO)", "Bật lái (ARM)"),
}
STATE_TEXT = {State.BOOT: "đang khởi động", State.DISARMED: "tắt lái (DISARMED)", State.ARMED: "sẵn sàng (ARMED)",
              State.RUNNING: "đang nhận lệnh (RUNNING)", State.FAULT: "lỗi (FAULT)"}


# ------------------------------------------------------------------------------------------------ mở liên kết (nền)
class Connector:
    """Mở liên kết và ARM trong luồng nền (SSH có thể chờ người dùng gõ mật khẩu). `step` là bước đang làm (chỉ số
    trong STEPS); `result` = (io, None) hoặc (None, lỗi) khi xong; `cancel()` đóng cổng đang chờ."""

    def __init__(self, mode: str, target: str, *, sim_config: Path = SIM_CONFIG):
        self.mode, self.target, self.sim_config = mode, target, sim_config
        self.result: tuple[VehicleIO | None, str | None] | None = None
        self.step = 0
        self.pi_port = ""                 # cổng ESP32 trên Pi, biết sau bước 2
        self.cancelled = False
        self._port = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name="autopark-car-connect", daemon=True)

    def start(self) -> "Connector":
        self._thread.start()
        return self

    def run_now(self) -> tuple[VehicleIO | None, str | None]:
        self._run()
        return self.result

    def done(self) -> bool:
        return self.result is not None

    def cancel(self) -> None:
        with self._lock:
            self.cancelled = True
            io = self.result[0] if self.result is not None else None
        if io is not None:                  # đã kết nối xong mà không ai nhận nữa: tắt lái, đóng
            shutdown_io(io)
        port = self._port
        if port is not None:
            try:
                port.close()
            except OSError:
                pass

    def _open(self) -> VehicleIO:
        timeout = TELEMETRY_TIMEOUT_S[self.mode]
        if self.mode == "sim":
            io = SimVehicleIO.from_files(self.sim_config, telemetry_timeout_s=timeout)
            self.step = 1
            return io
        from autopark.transport.ssh_serial import SshSerialPort

        port = SshSerialPort.to_pi(self.target)
        self._port = port
        if self.cancelled:
            port.close()
        port.wait_ready()                   # SSH (mật khẩu) rồi Pi mở ESP32; lời chào chỉ tới sau cả hai
        self.pi_port = port.port
        self.step = 2
        return SerialVehicleIO(port, port=f"ssh://xe@{self.target}{port.port}", telemetry_timeout_s=timeout)

    def _run(self) -> None:
        io = None
        try:
            io = self._open()
            self.step = 2
            io.connect(timeout_s=2.0)
            state = io.wait_ready(timeout_s=3.0)
            if state == State.FAULT:
                io.clear_fault()
            self.step = 3
            io.arm()
            with self._lock:
                if not self.cancelled:
                    self.step = 4
                    self.result = (io, None)
                    return
            raise VehicleIOError("Đã hủy")
        except (OSError, ValueError, VehicleIOError) as exc:
            if io is not None:
                shutdown_io(io)
            elif self._port is not None:
                self._port.close()
            self.result = (None, "Đã hủy kết nối" if self.cancelled else (str(exc) or type(exc).__name__))


def shutdown_io(io: VehicleIO) -> None:
    """Về trung tính, DISARM, đóng cổng. Không ném lỗi."""
    try:
        if io.connected:
            io.stop()
            io.disarm(timeout_s=0.3)
    except (OSError, VehicleIOError):
        pass
    try:
        io.close()
    except OSError:
        pass


# ------------------------------------------------------------------------------------------------ kết nối dùng chung
class CarConnection(QObject):
    """Kết nối tới bo, dùng chung cho mọi tab. Mọi thao tác chạy trong luồng giao diện, trừ bước mở liên kết."""

    logged = Signal(str)

    def __init__(self, *, connector_factory: Callable[[str, str], Connector] = Connector,
                 clock: Callable[[], float] = time.perf_counter, auto_tick: bool = True):
        super().__init__()
        self.connector_factory = connector_factory
        self.clock = clock
        self.mode = "pi"
        self.target = ""
        self.io: VehicleIO | None = None
        self.connector: Connector | None = None
        self.pi_port = ""
        self.driving_allowed = False        # False sau DỪNG; Bật lái (ARM) mới cho chạy lại
        self.failed_step: int | None = None
        self.last_error = ""
        self.lost = False                   # đã kết nối rồi mất (khác với chưa từng kết nối)
        # Tab lái đặt hàm này: trả (tốc độ m/s có dấu, góc lái rad); bị kẹp theo giới hạn bo trước khi gửi.
        self.command_source: Callable[[], tuple[float, float]] | None = None
        self.last_command = (0.0, 0.0)
        self.lines: list[str] = []
        self._armed_at = -math.inf          # io.now() lúc ARM xong: telemetry cũ hơn mốc này chưa kịp báo ARMED
        self._last_tick = clock()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        if auto_tick:
            self.timer.start(TICK_MS)

    # ---- thông tin ----------------------------------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self.io is not None

    @property
    def connecting(self) -> bool:
        return self.connector is not None

    @property
    def is_sim(self) -> bool:
        return isinstance(self.io, SimVehicleIO)

    @property
    def limits(self) -> VehicleLimits | None:
        return self.io.hello.limits if self.io is not None and self.io.hello is not None else None

    def steer_limit(self) -> float:
        """Góc lái ứng với hết lái: giới hạn bo báo (firmware thật đặt bằng nửa tầm servo)."""
        return self.limits.max_steer_rad if self.limits is not None else DEFAULT_STEER_LIMIT_RAD

    def servo_us(self, steer_rad: float) -> int:
        """Xung servo (µs) mà firmware xuất cho góc lái này: 1500 + 1000·rad (main.cpp), kẹp theo giới hạn góc lái."""
        lim = self.steer_limit()
        return SERVO_CENTER_US + round(min(lim, max(-lim, steer_rad)) * SERVO_US_PER_RAD)

    def max_speed(self) -> float:
        return self.limits.max_speed_mps if self.limits is not None else FALLBACK_MAX_SPEED_MPS

    def board_state(self) -> State | None:
        """Trạng thái bo theo telemetry mới nhất; telemetry gửi trước lúc ARM xong (bo đã trả ACK OK) coi là ARMED."""
        latest = self.io.latest() if self.io is not None else None
        if latest is None:
            return None
        if latest.stamp.t < self._armed_at and latest.state == State.DISARMED:
            return State.ARMED
        return latest.state

    def can_drive(self) -> bool:
        return (self.io is not None and self.driving_allowed and not self.io.rearm_required
                and self.board_state() in (State.ARMED, State.RUNNING))

    def step(self) -> int:
        return self.connector.step if self.connector is not None else (4 if self.io is not None else 0)

    def status(self) -> tuple[str, str]:
        """(chữ, sắc thái "ok"/"warn"/"bad"/"") cho ô trạng thái của mọi tab."""
        if self.connector is not None:
            wait = " · gõ mật khẩu Pi trong cửa sổ dòng lệnh" if self.mode == "pi" and self.connector.step == 0 else ""
            return f"Đang kết nối{wait}", "warn"
        if self.io is None:
            if self.lost:
                return "Mất kết nối", "bad"
            return ("Không kết nối được", "bad") if self.last_error else ("Chưa kết nối xe", "")
        if self.can_drive():
            return "Đã kết nối · sẵn sàng lái", "ok"
        if self.io.rearm_required:
            return "Mất liên lạc · bấm Bật lái", "bad"
        latest = self.io.latest()
        if latest is not None and latest.state == State.FAULT:
            return f"Lỗi bo: {latest.fault.name} · bấm Bật lái", "bad"
        return "Đã kết nối · tắt lái", "warn"

    def log(self, text: str) -> None:
        line = f"{time.strftime('%H:%M:%S')}  {text}"
        self.lines.append(line)
        del self.lines[:-LOG_LIMIT]
        self.logged.emit(line)

    # ---- thao tác -----------------------------------------------------------------------------------------------
    def connect_to(self, mode: str, target: str) -> bool:
        if self.io is not None or self.connector is not None:
            return False
        if mode == "pi" and not target:
            self.log("Chưa nhập địa chỉ IP của Pi.")
            return False
        self.mode, self.target = mode, target
        self.failed_step, self.last_error, self.lost, self.pi_port = None, "", False, ""
        self.log(f"Kết nối {dict(MODES)[mode]}{'' if mode == 'sim' else ' ' + target}")
        self.connector = self.connector_factory(mode, target).start()
        return True

    def disconnect(self) -> None:
        if self.connector is not None:
            self.connector.cancel()
            self.connector = None
            self.log("Hủy kết nối")
        if self.io is not None:
            shutdown_io(self.io)
            self.io = None
            self.log("Đã ngắt: xe về trung tính, tắt lái, đóng kết nối")
        self.driving_allowed = False
        self.last_command = (0.0, 0.0)

    def shutdown(self) -> None:
        self.timer.stop()
        self.disconnect()

    def stop(self) -> None:
        """DỪNG: lệnh dừng rồi DISARM. Không gửi lệnh chạy nữa tới khi `arm()`."""
        self.driving_allowed = False
        self.last_command = (0.0, 0.0)
        if self.io is None:
            return
        try:
            self.io.stop()
            self.io.disarm(timeout_s=0.5)
            self.log("DỪNG: tắt lái (DISARM). Bấm Bật lái để chạy tiếp.")
        except VehicleIOError as exc:
            self.log(f"DỪNG: {exc}")

    def arm(self) -> bool:
        if self.io is None:
            return False
        try:
            latest = self.io.latest()
            if latest is not None and latest.state == State.FAULT:
                self.io.clear_fault()
            self.io.arm()
        except VehicleIOError as exc:
            self.log(f"Không bật lái được: {exc}")
            return False
        self.driving_allowed = True
        self._armed_at = self.io.now()
        self.log("Bật lái (ARM)")
        return True

    # ---- nhịp 50 Hz ---------------------------------------------------------------------------------------------
    def _connector_finished(self) -> None:
        connector, self.connector = self.connector, None
        io, error = connector.result
        if io is None:
            self.failed_step = connector.step
            self.last_error = error or "lỗi không rõ"
            self.log(f"Không kết nối được ({STEPS[self.mode][min(connector.step, 3)]}): {self.last_error}")
            return
        self.io = io
        self.pi_port = connector.pi_port
        self.driving_allowed = True
        self._armed_at = io.now()
        info = io.hello
        self.log(f"Đã kết nối · firmware {info.firmware_version} · tốc độ tối đa {info.limits.max_speed_mps:.2f} m/s"
                 f" · lái tối đa {math.degrees(self.steer_limit()):.0f}° · bo đã ARM")

    def tick(self) -> None:
        now = self.clock()
        dt = min(max(now - self._last_tick, 0.0), 0.1)
        self._last_tick = now
        if self.connector is not None and self.connector.done():
            self._connector_finished()
            self._last_tick = self.clock()
            return
        io = self.io
        if io is None:
            return
        try:
            if isinstance(io, SimVehicleIO):
                io.advance(dt)
            else:
                io.poll(block=False)
            for event in io.events():
                self.log(f"{event.code}: {event.message}")
            if not io.connected:
                self.log("Mất kết nối với bo. Bấm Kết nối để nối lại.")
                shutdown_io(io)
                self.io = None
                self.driving_allowed = False
                self.lost = True
                self.last_command = (0.0, 0.0)
                return
            self._send(io)
        except VehicleIOError as exc:
            self.log(str(exc))

    def send_now(self) -> None:
        """Gửi lệnh của command_source ngay, không chờ nhịp 20 ms kế tiếp (tab lái gọi khi bấm/nhả phím ga)."""
        io = self.io
        if io is None or not io.connected or isinstance(io, SimVehicleIO):   # mô phỏng: thời gian chỉ chạy theo nhịp
            return
        try:
            self._send(io)
        except VehicleIOError as exc:
            self.log(str(exc))

    def _send(self, io: VehicleIO) -> None:
        if self.command_source is not None and self.can_drive():
            v, steer = self.command_source()
            vmax, smax = self.max_speed(), self.steer_limit()
            v, steer = min(vmax, max(-vmax, v)), min(smax, max(-smax, steer))
            io.send(v, steer, validity_s=min(VALIDITY_S[self.mode], io.hello.limits.max_validity_s))
            self.last_command = (v, steer)
        else:
            self.last_command = (0.0, 0.0)
            if io.now() - io.last_tx_time >= PING_IDLE_S:
                io.ping()


_shared: CarConnection | None = None


def shared_connection() -> CarConnection:
    """Kết nối duy nhất của app. Thoát app thì tự ngắt (xe về trung tính, DISARM, đóng SSH)."""
    global _shared
    if _shared is None:
        _shared = CarConnection()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(_shared.shutdown)
    return _shared


# ------------------------------------------------------------------------------------------------ giao diện chung
def page_style(root: str) -> str:
    """Bảng kiểu chung của tab Kết nối xe và Lái tay; `root` là objectName của trang."""
    r = f"QWidget#{root}"
    return f"""
{r} {{ background: {theme.BG}; }}
{r} QLabel {{ color: {theme.TEXT}; background: transparent; }}
{r} QLabel#pageTitle {{ font-size: 21px; font-weight: 500; }}
{r} QLabel#pageHint, {r} QLabel#pageNote {{ color: {theme.TEXT_DIM}; font-size: 12px; }}
{r} QLabel#section {{ color: {theme.TEXT_FAINT}; font-size: 10px; font-weight: 600; letter-spacing: 1.5px; }}
{r} QLabel#status {{ font-size: 13px; font-weight: 600; padding: 7px 14px; border-radius: 14px;
    background: #1b2a36; color: {theme.TEXT_DIM}; }}
{r} QLabel#status[tone="ok"] {{ background: #1f3a35; color: {theme.OK}; }}
{r} QLabel#status[tone="warn"] {{ background: #3b3122; color: {theme.WARN}; }}
{r} QLabel#status[tone="bad"] {{ background: #462d34; color: {theme.DANGER}; }}
{r} QLabel#teleKey {{ color: {theme.TEXT_FAINT}; font-size: 12px; }}
{r} QLabel#teleValue {{ font-family: {theme.MONO}; font-size: 13px; }}
{r} QLabel#stepIcon {{ font-family: {theme.MONO}; font-size: 14px; color: {theme.TEXT_FAINT}; }}
{r} QLabel#stepIcon[tone="ok"] {{ color: {theme.OK}; }}
{r} QLabel#stepIcon[tone="warn"] {{ color: {theme.WARN}; }}
{r} QLabel#stepIcon[tone="bad"] {{ color: {theme.DANGER}; }}
{r} QLabel#stepText {{ font-size: 13px; color: {theme.TEXT_DIM}; }}
{r} QFrame#panel {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER_SOFT}; border-radius: 14px; }}
{r} QFrame#banner {{ background: #1b2a36; border: 1px solid {theme.BORDER}; border-radius: 12px; }}
{r} QPushButton {{ color: {theme.TEXT}; background: #1b2a36; border: 1px solid {theme.BORDER};
    border-radius: 9px; padding: 8px 16px; }}
{r} QPushButton:hover {{ background: #243847; }}
{r} QPushButton:disabled {{ color: #4d6373; border-color: #233441; }}
{r} QPushButton#primary {{ background: {theme.ACCENT}; color: #10362d; border-color: {theme.ACCENT};
    font-size: 14px; font-weight: 600; padding: 10px 22px; }}
{r} QPushButton#primary:hover {{ background: #b6ffe9; }}
{r} QPushButton#stop {{ background: #462d34; border-color: #8e5159; color: #ffd4d1; font-size: 15px;
    font-weight: 600; padding: 14px 20px; border-radius: 12px; }}
{r} QPushButton#stop:hover {{ background: #62333c; }}
{r} QPushButton#arm {{ background: #1f3a35; border-color: #3d7a6a; color: {theme.ACCENT}; font-weight: 600; }}
{r} QLineEdit, {r} QComboBox {{ background: #15212c; color: {theme.TEXT}; border: 1px solid {theme.BORDER};
    border-radius: 8px; padding: 7px 10px; font-size: 13px; }}
{r} QPlainTextEdit {{ background: #101b24; color: {theme.TEXT_DIM}; border: 1px solid {theme.BORDER_SOFT};
    border-radius: 10px; font-family: {theme.MONO}; font-size: 11px; }}
"""


def panel(title: str | None = None) -> QFrame:
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 14, 18, 16)
    layout.setSpacing(10)
    if title:
        layout.addWidget(section(title))
    return frame


def section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("section")
    return label


def set_tone(label: QLabel, text: str, tone: str) -> None:
    if label.text() != text or label.property("tone") != tone:
        label.setText(text)
        label.setProperty("tone", tone)
        label.style().unpolish(label)
        label.style().polish(label)


def value_grid(rows: tuple[tuple[str, str], ...]) -> tuple[QGridLayout, dict[str, QLabel]]:
    grid = QGridLayout()
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(5)
    values: dict[str, QLabel] = {}
    for row, (key, label) in enumerate(rows):
        k = QLabel(label)
        k.setObjectName("teleKey")
        v = QLabel("—")
        v.setObjectName("teleValue")
        v.setWordWrap(True)
        v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(k, row, 0)
        grid.addWidget(v, row, 1)
        values[key] = v
    grid.setColumnStretch(1, 1)
    return grid, values


# ------------------------------------------------------------------------------------------------ tab Kết nối xe
class CarConnectionPage(QWidget):
    """Tab Kết nối xe: chọn xe thật/mô phỏng, nhập IP Pi, kết nối/ngắt, xem từng bước và thông tin bo."""

    def __init__(self, connection: CarConnection, host: str = "", *, settings: QSettings | None = None):
        super().__init__()
        self.connection = connection
        self.settings = settings
        self.setObjectName("carConnection")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(page_style("carConnection"))

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(14)
        head = QHBoxLayout()
        title = QLabel("Kết nối xe")
        title.setObjectName("pageTitle")
        self.status = QLabel("")
        self.status.setObjectName("status")
        head.addWidget(title)
        head.addSpacing(14)
        head.addWidget(self.status)
        head.addStretch(1)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(14)

        form = panel("KẾT NỐI")
        fl = form.layout()
        row = QHBoxLayout()
        row.setSpacing(8)
        self.mode_box = QComboBox()
        for key, label in MODES:
            self.mode_box.addItem(label, key)
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        self.host = QLineEdit(host or self._setting("host", ""))
        self.host.setPlaceholderText("Địa chỉ IP của Pi, ví dụ 192.168.1.50")
        self.host.setMinimumWidth(240)
        self.host.returnPressed.connect(self.toggle)
        self.connect_button = QPushButton("Kết nối")
        self.connect_button.setObjectName("primary")
        self.connect_button.clicked.connect(self.toggle)
        row.addWidget(self.mode_box)
        row.addWidget(self.host, 1)
        row.addWidget(self.connect_button)
        fl.addLayout(row)
        self.note = QLabel("")
        self.note.setObjectName("pageNote")
        self.note.setWordWrap(True)
        fl.addWidget(self.note)
        left.addWidget(form)

        steps = panel("CÁC BƯỚC")
        self.step_rows: list[tuple[QLabel, QLabel]] = []
        for _ in range(4):
            line = QHBoxLayout()
            icon = QLabel("○")
            icon.setObjectName("stepIcon")
            icon.setFixedWidth(22)
            text = QLabel("")
            text.setObjectName("stepText")
            line.addWidget(icon)
            line.addWidget(text, 1)
            steps.layout().addLayout(line)
            self.step_rows.append((icon, text))
        self.error = QLabel("")
        self.error.setObjectName("pageNote")
        self.error.setWordWrap(True)
        self.error.setStyleSheet(f"color: {theme.DANGER};")
        self.error.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        steps.layout().addWidget(self.error)
        left.addWidget(steps)

        actions = panel("LÁI")
        al = actions.layout()
        buttons = QHBoxLayout()
        self.arm_button = QPushButton("Bật lái (ARM)")
        self.arm_button.setObjectName("arm")
        self.arm_button.clicked.connect(self.connection.arm)
        self.stop_button = QPushButton("DỪNG · tắt lái")
        self.stop_button.setObjectName("stop")
        self.stop_button.clicked.connect(self.connection.stop)
        self.drive_button = QPushButton("Mở tab Lái tay")
        self.drive_button.clicked.connect(lambda: self._go("lai_tay"))
        buttons.addWidget(self.arm_button)
        buttons.addWidget(self.stop_button)
        buttons.addStretch(1)
        buttons.addWidget(self.drive_button)
        al.addLayout(buttons)
        left.addWidget(actions)
        left.addStretch(1)
        body.addLayout(left, 5)

        right = QVBoxLayout()
        right.setSpacing(14)
        board = panel("BO ESP32")
        grid, self.board = value_grid((("where", "Đường đi"), ("firmware", "Firmware"), ("boot", "Lần khởi động"),
                                       ("state", "Trạng thái"), ("fault", "Lỗi"), ("stop", "Lý do dừng gần nhất"),
                                       ("supply", "Điện áp")))
        board.layout().addLayout(grid)
        right.addWidget(board)
        limits = panel("GIỚI HẠN BO BÁO")
        grid, self.limit_values = value_grid((("speed", "Tốc độ tối đa"), ("steer", "Góc lái tối đa"),
                                              ("validity", "Hạn một lệnh"), ("link", "Mất liên lạc sau")))
        limits.layout().addLayout(grid)
        right.addWidget(limits)
        link = panel("LIÊN LẠC")
        grid, self.link_values = value_grid((("telemetry", "Telemetry"), ("rtt", "Trễ ACK"),
                                             ("frames", "Khung gửi / nhận"), ("errors", "Mất / lỗi")))
        link.layout().addLayout(grid)
        right.addWidget(link)
        right.addStretch(1)
        body.addLayout(right, 4)
        root.addLayout(body, 1)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(LOG_LIMIT)
        self.log.setFixedHeight(130)
        for line in connection.lines:
            self.log.appendPlainText(line)
        connection.logged.connect(self.log.appendPlainText)
        root.addWidget(self.log)

        index = max(0, self.mode_box.findData(connection.mode if connection.connected else self._setting("mode", "pi")))
        self.mode_box.setCurrentIndex(index)
        self._mode_changed(index)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(100)
        self.refresh()

    # ---- cài đặt -----------------------------------------------------------------------------------------------
    def _setting(self, key: str, default: str) -> str:
        if self.settings is None:
            return default
        try:
            value = self.settings.value(f"ket_noi_xe/{key}", default)
            return value if isinstance(value, str) else default
        except Exception:
            return default

    def _save_setting(self, key: str, value: str) -> None:
        if self.settings is not None:
            try:
                self.settings.setValue(f"ket_noi_xe/{key}", value)
            except Exception:
                pass

    def _go(self, key: str) -> None:
        window = self.window()
        if hasattr(window, "show_page"):
            window.show_page(key)

    # ---- thao tác -----------------------------------------------------------------------------------------------
    def _mode(self) -> str:
        return self.mode_box.currentData() or "pi"

    def _mode_changed(self, _index: int) -> None:
        mode = self._mode()
        self.host.setVisible(mode == "pi")
        self.note.setText(
            "Laptop SSH vào Pi qua Wi-Fi; Pi chuyển lệnh sang ESP32 đang cắm USB vào Pi. Gõ mật khẩu Pi trong cửa sổ "
            "dòng lệnh đã mở app nếu được hỏi. Muốn xem camera cùng lúc thì mở Quan sát Pi trước rồi mới kết nối."
            if mode == "pi" else "Không cần xe: firmware mô phỏng và mô hình xe chạy trên laptop.")
        if not self.connection.connected and not self.connection.connecting:
            self._show_steps(mode, 0, None)

    def toggle(self) -> None:
        if self.connection.connected or self.connection.connecting:
            self.connection.disconnect()
        else:
            mode, target = self._mode(), self.host.text().strip()
            if self.connection.connect_to(mode, target if mode == "pi" else "sim"):
                self._save_setting("mode", mode)
                if mode == "pi":
                    self._save_setting("host", target)
        self.refresh()

    # ---- hiển thị -----------------------------------------------------------------------------------------------
    def _show_steps(self, mode: str, done: int, failed: int | None) -> None:
        for k, (icon, text) in enumerate(self.step_rows):
            text.setText(STEPS[mode][k])
            if failed is not None and k == failed:
                set_tone(icon, "✗", "bad")
            elif k < done:
                set_tone(icon, "✓", "ok")
            elif k == done and self.connection.connecting:
                set_tone(icon, "…", "warn")
            else:
                set_tone(icon, "○", "")

    def refresh(self) -> None:
        c = self.connection
        set_tone(self.status, *c.status())
        busy = c.connecting or c.connected
        self.connect_button.setText("Hủy" if c.connecting else ("Ngắt kết nối" if c.connected else "Kết nối"))
        self.mode_box.setEnabled(not busy)
        self.host.setEnabled(not busy)
        mode = c.mode if busy or c.failed_step is not None else self._mode()
        failed = c.failed_step if not busy else None
        self._show_steps(mode, c.step() if failed is None else failed, failed)
        self.error.setText(c.last_error if not busy and c.last_error else "")
        self.error.setVisible(bool(self.error.text()))
        can_drive = c.can_drive()
        self.arm_button.setEnabled(c.connected and not can_drive)
        self.stop_button.setEnabled(c.connected)

        io = c.io
        if io is None:
            for values in (self.board, self.limit_values, self.link_values):
                for label in values.values():
                    label.setText("—")
            return
        if c.is_sim:
            self.board["where"].setText("mô phỏng trên laptop")
        else:
            self.board["where"].setText(f"laptop → SSH xe@{c.target} → Pi {c.pi_port or '?'} → ESP32")
        info = io.hello
        self.board["firmware"].setText(info.firmware_version)
        reset = ResetReason(info.reset_reason).name if info.reset_reason in ResetReason._value2member_map_ else "?"
        self.board["boot"].setText(f"boot_id {info.boot_id:08x} · reset {reset}")
        latest = io.latest()
        state = c.board_state()
        self.board["state"].setText(STATE_TEXT.get(state, "chưa có telemetry"))
        if latest is not None:
            self.board["fault"].setText(latest.fault.name if latest.fault else "không")
            stopped = latest.state != State.RUNNING
            self.board["stop"].setText(latest.stop_reason.name if latest.stop_reason and stopped else "—")
            self.board["supply"].setText("chưa đo" if latest.supply_v is None else f"{latest.supply_v:.2f} V")
        lim = info.limits
        self.limit_values["speed"].setText(f"{lim.max_speed_mps:.2f} m/s")
        servo = "" if c.is_sim else f" (servo {c.servo_us(-lim.max_steer_rad)}–{c.servo_us(lim.max_steer_rad)} µs)"
        self.limit_values["steer"].setText(f"{math.degrees(lim.max_steer_rad):.0f}°{servo}")
        self.limit_values["validity"].setText(f"{lim.max_validity_s * 1000:.0f} ms (app dùng "
                                              f"{min(VALIDITY_S[c.mode], lim.max_validity_s) * 1000:.0f} ms)")
        self.limit_values["link"].setText(f"{lim.link_timeout_s * 1000:.0f} ms")
        s = io.stats
        age = "—" if latest is None else f"{max(0.0, io.now() - latest.stamp.t) * 1000:.0f} ms trước"
        self.link_values["telemetry"].setText(f"{age} · chu kỳ {info.telemetry_period_s * 1000:.0f} ms")
        self.link_values["rtt"].setText("—" if s.ack_rtt_s is None else
                                        f"{s.ack_rtt_s * 1000:.0f} ms (lớn nhất {s.ack_rtt_max_s * 1000:.0f} ms)")
        self.link_values["frames"].setText(f"{s.frames_sent} / {s.messages_received}")
        self.link_values["errors"].setText(f"mất {s.device_messages_missed} · lỗi cổng {s.link_errors}")

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.connection.shutdown()              # thoát app: xe về trung tính, DISARM, đóng SSH
        event.accept()
