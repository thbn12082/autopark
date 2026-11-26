"""Lái tay (thêm 26/11/2026): vô lăng chỉnh góc lái, giữ Space để tiến, giữ W để lùi.

```
Lái tay
├── Kết nối qua
│   ├── Pi qua Wi-Fi ...... ssh xe@<ip> → cầu nối trên Pi → USB → ESP32 (transport/ssh_serial.py)
│   ├── ESP32 cắm laptop .. cổng COM trực tiếp
│   └── Mô phỏng .......... SimVehicleIO + FirmwareModel, không cần xe
├── Vô lăng ............... kéo chuột để xoay, ← → cũng xoay, nhấp đúp về giữa; giữ nguyên góc khi nhả chuột
├── Space / W ............. giữ để tiến / lùi với tốc độ đặt bằng thanh trượt; nhả phím là về 0; giữ cả hai là 0
└── Esc hoặc nút DỪNG ..... dừng và DISARM; "Bật lái" để ARM lại
```

Mọi lệnh đi qua `VehicleIO.send()` như bộ bám quỹ đạo: 50 lệnh/giây, mỗi lệnh có hạn ngắn, nên app treo, Wi-Fi rớt hay
cửa sổ mất tiêu điểm thì xe tự về trung tính (firmware). Phím chỉ được tính khi cửa sổ AutoPark đang được chọn và trang
này đang hiện; chuyển cửa sổ hay chuyển trang thì coi như nhả hết phím. Tốc độ là tốc độ đặt cho firmware; xe chưa có
MT6701 nên firmware chạy vòng hở (ga theo feedforward), tốc độ thật có thể khác.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import threading
import time
from typing import Callable

from PySide6.QtCore import QEvent, QPointF, QRectF, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from autopark.transport.protocol import State
from autopark.transport.vehicle_io import SerialVehicleIO, SimVehicleIO, VehicleIO, VehicleIOError
from autopark.ui import theme

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SIM_CONFIG = PROJECT_ROOT / "configs" / "vehicle_io_sim.json"

TICK_MS = 20                      # 50 lệnh/giây, như thu_ban_pwm.py
UI_REFRESH_S = 0.1
WHEEL_MAX_DEG = 270.0             # vô lăng xoay ±270° là hết lái
KEY_STEER_RATE_DEG_S = 360.0      # giữ ← → thì vô lăng quay ngần này độ mỗi giây
# Env esp32s3_16mb_pwm kẹp servo 1200–1800 µs, 1 mrad ≈ 1 µs: quá ±0,30 rad servo không quay thêm dù bo cho phép 0,524.
SERVO_LIMIT_RAD = 0.30
DEFAULT_SPEED_MPS = 0.10
FALLBACK_MAX_SPEED_MPS = 0.30
PING_IDLE_S = 0.2

MODES = (("pi", "Pi qua Wi-Fi"), ("usb", "ESP32 cắm laptop"), ("sim", "Mô phỏng"))
VALIDITY_S = {"pi": 0.25, "usb": 0.15, "sim": 0.15}
TELEMETRY_TIMEOUT_S = {"pi": 0.5, "usb": 0.3, "sim": 0.3}


# ------------------------------------------------------------------------------------------------ phần tính thuần
@dataclass
class DriveInput:
    forward: bool = False          # Space đang giữ
    reverse: bool = False          # W đang giữ
    steer_frac: float = 0.0        # -1..1, dương = rẽ trái (quy ước dự án)
    speed_mps: float = DEFAULT_SPEED_MPS


def drive_command(inp: DriveInput, max_steer_rad: float, max_speed_mps: float) -> tuple[float, float]:
    """(tốc độ m/s có dấu, góc lái rad). Không phím hoặc cả hai phím: tốc độ 0. Mọi giá trị bị kẹp trong giới hạn."""
    speed = min(max(inp.speed_mps, 0.0), max_speed_mps)
    v = 0.0 if inp.forward == inp.reverse else (speed if inp.forward else -speed)
    frac = min(1.0, max(-1.0, inp.steer_frac))
    return v, frac * max_steer_rad


def steer_limit(io: VehicleIO | None, mode: str) -> float:
    """Góc lái ứng với vô lăng hết cỡ: giới hạn bo báo, với xe thật thêm giới hạn servo của bản thử bàn."""
    board = io.hello.limits.max_steer_rad if io is not None and io.hello is not None else SERVO_LIMIT_RAD
    return board if mode == "sim" else min(board, SERVO_LIMIT_RAD)


# ------------------------------------------------------------------------------------------------ vô lăng
class SteeringWheel(QWidget):
    """Vô lăng vẽ tay. `value` -1..1, dương = rẽ trái (xoay ngược chiều kim đồng hồ)."""

    changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Kéo để xoay vô lăng · nhấp đúp để về giữa")
        self._deg = 0.0                # góc vô lăng trên màn hình, dương = chiều kim đồng hồ (rẽ phải)
        self._drag_angle: float | None = None
        self.active = True
        self.caption = "0°"            # chữ giữa vô lăng: góc lái của bánh xe (trang đặt)

    @property
    def value(self) -> float:
        return -self._deg / WHEEL_MAX_DEG

    def set_value(self, value: float) -> None:
        deg = -min(1.0, max(-1.0, value)) * WHEEL_MAX_DEG
        if deg != self._deg:
            self._deg = deg
            self.update()
            self.changed.emit(self.value)

    def rotate_by(self, deg: float) -> None:
        self.set_value(-(self._deg + deg) / WHEEL_MAX_DEG)

    def _pointer_angle(self, pos: QPointF) -> float:
        c = QPointF(self.width() / 2, self.height() / 2)
        return math.degrees(math.atan2(pos.y() - c.y(), pos.x() - c.x()))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_angle = self._pointer_angle(event.position())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_angle is None:
            return
        angle = self._pointer_angle(event.position())
        delta = (angle - self._drag_angle + 180.0) % 360.0 - 180.0
        self._drag_angle = angle
        self.rotate_by(delta)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_angle = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        self.set_value(0.0)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 16
        r = side / 2
        c = QPointF(self.width() / 2, self.height() / 2)
        accent = QColor(theme.ACCENT if self.active else theme.TEXT_FAINT)

        # cung chỉ góc lái: từ đỉnh tới vị trí hiện tại, quanh vô lăng
        gauge = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        p.setPen(QPen(QColor(theme.BORDER_SOFT), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(gauge, 0, 360 * 16)
        if abs(self._deg) > 0.5:
            p.setPen(QPen(accent, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            span = -self._deg / WHEEL_MAX_DEG * 135.0          # hết lái = 135° cung
            p.drawArc(gauge, 90 * 16, int(span * 16))

        p.translate(c)
        p.rotate(self._deg)
        rim_r = r - 18
        rim_w = max(14.0, r * 0.13)
        p.setPen(QPen(QColor("#2b3c49"), rim_w))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(0, 0), rim_r, rim_r)
        p.setPen(QPen(QColor("#3d5262"), 2))
        p.drawEllipse(QPointF(0, 0), rim_r + rim_w / 2, rim_r + rim_w / 2)
        p.drawEllipse(QPointF(0, 0), rim_r - rim_w / 2, rim_r - rim_w / 2)
        # ba nan hoa
        p.setPen(QPen(QColor("#2b3c49"), rim_w * 0.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        for deg in (180.0, 0.0, 90.0):
            a = math.radians(deg)
            p.drawLine(QPointF(math.cos(a) * r * 0.22, math.sin(a) * r * 0.22),
                       QPointF(math.cos(a) * (rim_r - rim_w / 2), math.sin(a) * (rim_r - rim_w / 2)))
        # moay-ơ
        p.setPen(QPen(QColor("#3d5262"), 2))
        p.setBrush(QColor("#1c2a36"))
        p.drawEllipse(QPointF(0, 0), r * 0.24, r * 0.24)
        # vạch đỉnh: thấy vô lăng đang xoay bao nhiêu
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(-5, -rim_r - rim_w / 2 + 1, 10, rim_w - 2), 3, 3)
        p.resetTransform()

        p.setPen(QColor(theme.TEXT))
        font = QFont(self.font())
        font.setPointSizeF(max(9.0, r * 0.06))
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.drawText(QRectF(c.x() - r * 0.24, c.y() - r * 0.24, r * 0.48, r * 0.48), Qt.AlignmentFlag.AlignCenter,
                   self.caption)
        p.end()


class KeyTile(QFrame):
    """Ô hiện phím Space/W đang giữ hay không."""

    def __init__(self, key: str, title: str):
        super().__init__()
        self.setObjectName("keyTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        self.key = QLabel(key)
        self.key.setObjectName("keyName")
        self.title = QLabel(title)
        self.title.setObjectName("keyTitle")
        layout.addWidget(self.key)
        layout.addWidget(self.title)
        self.set_on(False)

    def set_on(self, on: bool) -> None:
        if self.property("on") == on:
            return
        self.setProperty("on", on)
        self.style().unpolish(self)
        self.style().polish(self)
        for child in (self.key, self.title):
            child.style().unpolish(child)
            child.style().polish(child)


class TrackView(QWidget):
    """Đường xe đi trong chế độ mô phỏng (nhìn từ trên, lưới 0,5 m)."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(170)
        self.trail: list[tuple[float, float]] = []
        self.pose = (0.0, 0.0, 0.0)
        self.length, self.width_m = 0.3, 0.16

    def reset(self) -> None:
        self.trail.clear()
        self.update()

    def set_pose(self, x: float, y: float, yaw: float) -> None:
        self.pose = (x, y, yaw)
        if not self.trail or math.dist(self.trail[-1], (x, y)) > 0.01:
            self.trail.append((x, y))
            del self.trail[:-2000]
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#101b24"))
        scale = min(self.width(), self.height()) / 3.0          # 3 m vừa khung
        x0, y0, yaw = self.pose
        cx, cy = self.width() / 2, self.height() / 2

        def to_px(x: float, y: float) -> QPointF:             # x tiến lên trên màn hình, y sang trái
            return QPointF(cx - (y - y0) * scale, cy - (x - x0) * scale)

        p.setPen(QPen(QColor("#1d2c38"), 1))
        step = 0.5
        for k in range(-8, 9):
            gx = math.floor(x0 / step) * step + k * step
            gy = math.floor(y0 / step) * step + k * step
            a, b = to_px(gx, y0 - 5), to_px(gx, y0 + 5)
            p.drawLine(a, b)
            a, b = to_px(x0 - 5, gy), to_px(x0 + 5, gy)
            p.drawLine(a, b)
        if len(self.trail) > 1:
            path = QPainterPath(to_px(*self.trail[0]))
            for pt in self.trail[1:]:
                path.lineTo(to_px(*pt))
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.drawPath(path)
        p.translate(to_px(x0, y0))
        p.rotate(-math.degrees(yaw))
        p.setPen(QPen(QColor(theme.TEXT), 1.5))
        p.setBrush(QColor("#2c4656"))
        L, W = self.length * scale, self.width_m * scale
        p.drawRoundedRect(QRectF(-W / 2, -L * 0.8, W, L), 3, 3)
        p.setBrush(QColor(theme.ACCENT))
        p.drawEllipse(QPointF(0, -L * 0.8 + 4), 3, 3)
        p.end()


# ------------------------------------------------------------------------------------------------ kết nối nền
class Connector:
    """Mở liên kết và ARM trong luồng nền (SSH có thể chờ người dùng gõ mật khẩu). `result` = (io, None) hoặc
    (None, lỗi) khi xong; `cancel()` đóng cổng đang chờ."""

    def __init__(self, mode: str, target: str, *, sim_config: Path = SIM_CONFIG):
        self.mode, self.target, self.sim_config = mode, target, sim_config
        self.result: tuple[VehicleIO | None, str | None] | None = None
        self.cancelled = False
        self._port = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name="autopark-drive-connect", daemon=True)

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
        if io is not None:                  # đã kết nối xong mà trang không nhận nữa: tắt lái, đóng
            _shutdown(io)
        port = self._port
        if port is not None:
            try:
                port.close()
            except OSError:
                pass

    def _open(self) -> VehicleIO:
        timeout = TELEMETRY_TIMEOUT_S[self.mode]
        if self.mode == "sim":
            return SimVehicleIO.from_files(self.sim_config, telemetry_timeout_s=timeout)
        if self.mode == "usb":
            return SerialVehicleIO.open(self.target, telemetry_timeout_s=timeout)
        from autopark.transport.ssh_serial import SshSerialPort

        port = SshSerialPort.to_pi(self.target)
        self._port = port
        if self.cancelled:
            port.close()
        port.wait_ready()
        return SerialVehicleIO(port, port=f"ssh://xe@{self.target}{port.port}", telemetry_timeout_s=timeout)

    def _run(self) -> None:
        io = None
        try:
            io = self._open()
            io.connect(timeout_s=2.0)
            state = io.wait_ready(timeout_s=3.0)
            if state == State.FAULT:
                io.clear_fault()
            io.arm()
            with self._lock:
                if not self.cancelled:
                    self.result = (io, None)
                    return
            raise VehicleIOError("Đã hủy")
        except (OSError, ValueError, VehicleIOError) as exc:
            if io is not None:
                _shutdown(io)
            elif self._port is not None:
                self._port.close()
            self.result = (None, "Đã hủy kết nối" if self.cancelled else (str(exc) or type(exc).__name__))


def _shutdown(io: VehicleIO) -> None:
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


# ------------------------------------------------------------------------------------------------ trang
STYLE = f"""
QWidget#manualDrive {{ background: {theme.BG}; }}
QWidget#manualDrive QLabel {{ color: {theme.TEXT}; background: transparent; }}
QWidget#manualDrive QLabel#driveTitle {{ font-size: 21px; font-weight: 500; }}
QWidget#manualDrive QLabel#driveHint, QWidget#manualDrive QLabel#driveNote {{ color: {theme.TEXT_DIM}; font-size: 12px; }}
QWidget#manualDrive QLabel#driveSection {{ color: {theme.TEXT_FAINT}; font-size: 10px; font-weight: 600; letter-spacing: 1.5px; }}
QWidget#manualDrive QLabel#driveStatus {{ font-size: 13px; font-weight: 600; padding: 7px 14px; border-radius: 14px;
    background: #1b2a36; color: {theme.TEXT_DIM}; }}
QWidget#manualDrive QLabel#driveStatus[tone="ok"] {{ background: #1f3a35; color: {theme.OK}; }}
QWidget#manualDrive QLabel#driveStatus[tone="warn"] {{ background: #3b3122; color: {theme.WARN}; }}
QWidget#manualDrive QLabel#driveStatus[tone="bad"] {{ background: #462d34; color: {theme.DANGER}; }}
QWidget#manualDrive QLabel#steerReadout {{ font-size: 15px; color: {theme.TEXT}; }}
QWidget#manualDrive QLabel#teleKey {{ color: {theme.TEXT_FAINT}; font-size: 12px; }}
QWidget#manualDrive QLabel#teleValue {{ font-family: {theme.MONO}; font-size: 13px; }}
QFrame#drivePanel {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER_SOFT}; border-radius: 14px; }}
QFrame#keyTile {{ background: #15212c; border: 1px solid {theme.BORDER}; border-radius: 12px; }}
QFrame#keyTile[on="true"] {{ background: #1f3a35; border-color: {theme.ACCENT}; }}
QWidget#manualDrive QLabel#keyName {{ font-family: {theme.MONO}; font-size: 20px; font-weight: 600; color: {theme.TEXT_DIM}; }}
QWidget#manualDrive QLabel#keyTitle {{ font-size: 12px; color: {theme.TEXT_FAINT}; }}
QWidget#manualDrive QFrame#keyTile[on="true"] QLabel#keyName {{ color: {theme.ACCENT}; }}
QWidget#manualDrive QFrame#keyTile[on="true"] QLabel#keyTitle {{ color: {theme.TEXT}; }}
QWidget#manualDrive QPushButton {{ color: {theme.TEXT}; background: #1b2a36; border: 1px solid {theme.BORDER};
    border-radius: 9px; padding: 8px 16px; }}
QWidget#manualDrive QPushButton:hover {{ background: #243847; }}
QWidget#manualDrive QPushButton:disabled {{ color: #4d6373; border-color: #233441; }}
QPushButton#driveStop {{ background: #462d34; border-color: #8e5159; color: #ffd4d1; font-size: 15px;
    font-weight: 600; padding: 14px 20px; border-radius: 12px; }}
QPushButton#driveStop:hover {{ background: #62333c; }}
QPushButton#driveArm {{ background: #1f3a35; border-color: #3d7a6a; color: {theme.ACCENT}; font-weight: 600; }}
QWidget#manualDrive QLineEdit, QWidget#manualDrive QComboBox {{ background: #15212c; color: {theme.TEXT};
    border: 1px solid {theme.BORDER}; border-radius: 8px; padding: 6px 10px; }}
QWidget#manualDrive QPlainTextEdit {{ background: #101b24; color: {theme.TEXT_DIM}; border: 1px solid
    {theme.BORDER_SOFT}; border-radius: 10px; font-family: {theme.MONO}; font-size: 11px; }}
QWidget#manualDrive QSlider::groove:horizontal {{ height: 6px; background: #273844; border-radius: 3px; }}
QWidget#manualDrive QSlider::sub-page:horizontal {{ background: {theme.ACCENT}; border-radius: 3px; }}
QWidget#manualDrive QSlider::handle:horizontal {{ background: {theme.TEXT}; width: 16px; margin: -6px 0;
    border-radius: 8px; }}
"""

STATE_TEXT = {State.BOOT: "đang khởi động", State.DISARMED: "tắt lái (DISARMED)", State.ARMED: "sẵn sàng (ARMED)",
              State.RUNNING: "đang nhận lệnh (RUNNING)", State.FAULT: "lỗi (FAULT)"}


class ManualDriveWindow(QWidget):
    """Trang Lái tay của cửa sổ AutoPark."""

    def __init__(self, host: str = "", *, connector_factory: Callable[[str, str], Connector] = Connector,
                 clock: Callable[[], float] = time.perf_counter, settings: QSettings | None = None):
        super().__init__()
        self.setObjectName("manualDrive")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STYLE)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.connector_factory = connector_factory
        self.clock = clock
        self.settings = settings
        self.io: VehicleIO | None = None
        self.mode = "pi"
        self.connector: Connector | None = None
        self.drive = DriveInput()
        self.driving_allowed = False        # False sau DỪNG; Bật lái (ARM) mới cho chạy lại
        self.steer_keys = {Qt.Key.Key_Left: False, Qt.Key.Key_Right: False}
        self.last_command = (0.0, 0.0)
        self._armed_at = -math.inf          # io.now() lúc ARM xong: telemetry cũ hơn mốc này chưa kịp báo ARMED
        self._last_tick = clock()
        self._last_ui = -math.inf
        self._filter_installed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("Lái tay")
        title.setObjectName("driveTitle")
        self.status = QLabel("Chưa kết nối")
        self.status.setObjectName("driveStatus")
        head.addWidget(title)
        head.addSpacing(14)
        head.addWidget(self.status)
        head.addStretch(1)
        root.addLayout(head)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.mode_box = QComboBox()
        for key, label in MODES:
            self.mode_box.addItem(label, key)
        self.mode_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        self.host = QLineEdit(host or self._setting("host", ""))
        self.host.setPlaceholderText("Địa chỉ IP của Pi")
        self.host.setMaximumWidth(200)
        self.host.returnPressed.connect(self.toggle_connection)
        self.port_box = QComboBox()
        self.port_box.setMinimumWidth(240)
        self.port_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.refresh_ports = QPushButton("Dò cổng")
        self.refresh_ports.clicked.connect(self.list_ports)
        self.connect_button = QPushButton("Kết nối")
        self.connect_button.clicked.connect(self.toggle_connection)
        self.arm_button = QPushButton("Bật lái")
        self.arm_button.setObjectName("driveArm")
        self.arm_button.setToolTip("ARM lại bo sau khi DỪNG, mất liên lạc hoặc lỗi")
        self.arm_button.clicked.connect(self.rearm)
        bar.addWidget(QLabel("Kết nối qua"))
        bar.addWidget(self.mode_box)
        bar.addWidget(self.host)
        bar.addWidget(self.port_box)
        bar.addWidget(self.refresh_ports)
        bar.addWidget(self.connect_button)
        bar.addWidget(self.arm_button)
        bar.addStretch(1)
        root.addLayout(bar)
        self.link_note = QLabel("")
        self.link_note.setObjectName("driveNote")
        self.link_note.setWordWrap(True)
        root.addWidget(self.link_note)

        body = QHBoxLayout()
        body.setSpacing(16)
        wheel_panel = self._panel()
        wl = wheel_panel.layout()
        wl.addWidget(self._section("VÔ LĂNG"))
        self.wheel = SteeringWheel()
        self.wheel.changed.connect(self._wheel_changed)
        wl.addWidget(self.wheel, 1)
        steer_row = QHBoxLayout()
        self.steer_readout = QLabel("")
        self.steer_readout.setObjectName("steerReadout")
        center = QPushButton("Về giữa")
        center.clicked.connect(lambda: self.wheel.set_value(0.0))
        steer_row.addWidget(self.steer_readout, 1)
        steer_row.addWidget(center)
        wl.addLayout(steer_row)
        body.addWidget(wheel_panel, 5)

        side = QVBoxLayout()
        side.setSpacing(12)
        pedals = self._panel()
        pl = pedals.layout()
        pl.addWidget(self._section("GA"))
        tiles = QHBoxLayout()
        self.forward_tile = KeyTile("Space", "Giữ để tiến")
        self.reverse_tile = KeyTile("W", "Giữ để lùi")
        tiles.addWidget(self.forward_tile)
        tiles.addWidget(self.reverse_tile)
        pl.addLayout(tiles)
        speed_row = QHBoxLayout()
        self.speed_label = QLabel("")
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.speed.setRange(2, round(FALLBACK_MAX_SPEED_MPS * 100))
        self.speed.setValue(round(DEFAULT_SPEED_MPS * 100))
        self.speed.valueChanged.connect(self._speed_changed)
        speed_row.addWidget(QLabel("Tốc độ"))
        speed_row.addWidget(self.speed, 1)
        speed_row.addWidget(self.speed_label)
        pl.addLayout(speed_row)
        self.stop_button = QPushButton("DỪNG  ·  Esc")
        self.stop_button.setObjectName("driveStop")
        self.stop_button.clicked.connect(self.emergency_stop)
        pl.addWidget(self.stop_button)
        side.addWidget(pedals)

        tele = self._panel()
        tl = tele.layout()
        tl.addWidget(self._section("XE"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(5)
        self.tele: dict[str, QLabel] = {}
        for row, (key, label) in enumerate((("state", "Bo"), ("command", "Lệnh gửi"), ("ref", "Bo đang chạy"),
                                            ("measured", "Đo được"), ("effort", "Ga ra ESC"),
                                            ("stop", "Lý do dừng"), ("link", "Liên lạc"))):
            k = QLabel(label)
            k.setObjectName("teleKey")
            v = QLabel("—")
            v.setObjectName("teleValue")
            v.setWordWrap(True)
            grid.addWidget(k, row, 0)
            grid.addWidget(v, row, 1)
            self.tele[key] = v
        grid.setColumnStretch(1, 1)
        tl.addLayout(grid)
        side.addWidget(tele)

        self.track = TrackView()
        self.track_panel = self._panel()
        self.track_panel.layout().addWidget(self._section("ĐƯỜNG ĐI (MÔ PHỎNG)"))
        self.track_panel.layout().addWidget(self.track, 1)
        side.addWidget(self.track_panel, 1)
        side.addStretch(0)
        body.addLayout(side, 4)
        root.addLayout(body, 1)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.log.setMaximumBlockCount(300)
        self.log.setFixedHeight(92)
        root.addWidget(self.log)
        hint = QLabel("Giữ Space để tiến, giữ W để lùi, nhả phím là dừng. Kéo vô lăng bằng chuột hoặc giữ ← →, "
                      "nhấp đúp để về giữa. Esc: dừng và tắt lái. Phím chỉ có tác dụng khi cửa sổ này đang được chọn.")
        hint.setObjectName("driveHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        for button in self.findChildren(QPushButton):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)       # Space không được "bấm" nút nào

        mode = self._setting("mode", "pi")
        index = max(0, self.mode_box.findData(mode))
        self.mode_box.setCurrentIndex(index)
        self._mode_changed(index)
        self._speed_changed(self.speed.value())
        self._wheel_changed(0.0)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)
        self._refresh_ui(force=True)

    # ---- dựng ---------------------------------------------------------------------------------------------------
    @staticmethod
    def _panel() -> QFrame:
        frame = QFrame()
        frame.setObjectName("drivePanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(10)
        return frame

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("driveSection")
        return label

    def _setting(self, key: str, default: str) -> str:
        if self.settings is None:
            return default
        try:
            value = self.settings.value(f"lai_tay/{key}", default)
            return value if isinstance(value, str) else default
        except Exception:
            return default

    def _save_setting(self, key: str, value: str) -> None:
        if self.settings is not None:
            try:
                self.settings.setValue(f"lai_tay/{key}", value)
            except Exception:
                pass

    def _log(self, text: str) -> None:
        self.log.appendPlainText(f"{time.strftime('%H:%M:%S')}  {text}")

    def _set_status(self, text: str, tone: str = "") -> None:
        if self.status.text() != text or self.status.property("tone") != tone:
            self.status.setText(text)
            self.status.setProperty("tone", tone)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)

    # ---- chọn kết nối -------------------------------------------------------------------------------------------
    def _mode_changed(self, index: int) -> None:
        self.mode = self.mode_box.itemData(index) or "pi"
        self.host.setVisible(self.mode == "pi")
        self.port_box.setVisible(self.mode == "usb")
        self.refresh_ports.setVisible(self.mode == "usb")
        self.track_panel.setVisible(self.mode == "sim")
        notes = {
            "pi": "Lái qua Wi-Fi: laptop SSH vào Pi, Pi chuyển lệnh sang ESP32 qua USB. Gõ mật khẩu Pi trong cửa sổ "
                  "dòng lệnh đã mở app nếu được hỏi. Muốn xem camera cùng lúc thì mở trang Quan sát Pi TRƯỚC.",
            "usb": "ESP32 cắm thẳng vào laptop bằng cáp USB.",
            "sim": "Không cần xe: firmware mô phỏng và mô hình xe chạy trên laptop.",
        }
        self.link_note.setText(notes[self.mode])
        if self.mode == "usb" and self.port_box.count() == 0:
            self.list_ports()

    def list_ports(self) -> None:
        self.port_box.clear()
        try:
            from serial.tools import list_ports
            ports = sorted(list_ports.comports(), key=lambda p: (p.vid != 0x303A, p.device))
        except Exception as exc:
            self._log(f"Không dò được cổng COM: {exc}")
            return
        for p in ports:
            tag = " · ESP32" if p.vid == 0x303A else ""
            self.port_box.addItem(f"{p.device}{tag} · {p.description}", p.device)
        if not ports:
            self.port_box.addItem("Không thấy cổng COM nào", "")

    def _target(self) -> str:
        if self.mode == "pi":
            return self.host.text().strip()
        if self.mode == "usb":
            return self.port_box.currentData() or ""
        return "sim"

    # ---- kết nối ------------------------------------------------------------------------------------------------
    def toggle_connection(self) -> None:
        if self.io is not None or self.connector is not None:
            self.disconnect_link()
        else:
            self.connect_link()

    def connect_link(self) -> None:
        if self.io is not None or self.connector is not None:
            return
        target = self._target()
        if not target:
            self._log("Chưa nhập địa chỉ Pi." if self.mode == "pi" else "Chưa chọn cổng COM.")
            return
        self._save_setting("mode", self.mode)
        if self.mode == "pi":
            self._save_setting("host", target)
        self._log(f"Kết nối {dict(MODES)[self.mode]} {'' if self.mode == 'sim' else target}".rstrip())
        self.connector = self.connector_factory(self.mode, target).start()
        self.setFocus()
        self._refresh_ui(force=True)

    def disconnect_link(self) -> None:
        if self.connector is not None:
            self.connector.cancel()
            self.connector = None
            self._log("Hủy kết nối")
        if self.io is not None:
            _shutdown(self.io)
            self.io = None
            self._log("Đã ngắt: xe về trung tính, tắt lái")
        self.driving_allowed = False
        self._refresh_ui(force=True)

    def _connector_finished(self) -> None:
        io, error = self.connector.result
        self.connector = None
        if io is None:
            self._log(f"Không kết nối được: {error}")
            self._set_status("Không kết nối được", "bad")
            self._refresh_ui(force=True)
            return
        self.io = io
        self.driving_allowed = True
        self._armed_at = io.now()
        info = io.hello
        lim = info.limits
        self.speed.setMaximum(max(self.speed.minimum(), int(lim.max_speed_mps * 100 + 1e-6)))
        self._log(f"Đã kết nối · firmware {info.firmware_version} · tốc độ tối đa {lim.max_speed_mps:.2f} m/s · "
                  f"lái tối đa {math.degrees(steer_limit(io, self.mode)):.0f}° · lệnh hạn "
                  f"{VALIDITY_S[self.mode] * 1000:.0f} ms")
        self.track.reset()
        self._last_tick = self.clock()
        self.setFocus()
        self._speed_changed(self.speed.value())
        self._wheel_changed(self.wheel.value)
        self._refresh_ui(force=True)

    # ---- lệnh ---------------------------------------------------------------------------------------------------
    def emergency_stop(self) -> None:
        self.drive.forward = self.drive.reverse = False
        self.driving_allowed = False
        if self.io is None:
            return
        try:
            self.io.stop()
            self.io.disarm(timeout_s=0.5)
            self._log("DỪNG: tắt lái (DISARM). Bấm Bật lái để chạy tiếp.")
        except VehicleIOError as exc:
            self._log(f"DỪNG: {exc}")
        self._refresh_ui(force=True)

    def rearm(self) -> None:
        if self.io is None:
            return
        try:
            latest = self.io.latest()
            if latest is not None and latest.state == State.FAULT:
                self.io.clear_fault()
            self.io.arm()
            self.driving_allowed = True
            self._armed_at = self.io.now()
            self._log("Bật lái (ARM)")
        except VehicleIOError as exc:
            self._log(f"Không bật lái được: {exc}")
        self._refresh_ui(force=True)

    def _wheel_changed(self, value: float) -> None:
        self.drive.steer_frac = value
        deg = math.degrees(value * steer_limit(self.io, self.mode))
        side = "trái" if deg > 0.05 else ("phải" if deg < -0.05 else "thẳng")
        self.steer_readout.setText(f"Góc lái {abs(deg):.1f}° {side}")
        self.wheel.caption = f"{'◀ ' if deg > 0.05 else ''}{abs(deg):.0f}°{' ▶' if deg < -0.05 else ''}"
        self.wheel.update()

    def _speed_changed(self, value: int) -> None:
        self.drive.speed_mps = value / 100.0
        self.speed_label.setText(f"{self.drive.speed_mps:.2f} m/s")

    def set_key(self, key, pressed: bool) -> bool:
        """Một phím được nhấn/nhả. Trả True nếu là phím lái (đã xử lý)."""
        if key == Qt.Key.Key_Space:
            self.drive.forward = pressed
        elif key == Qt.Key.Key_W:
            self.drive.reverse = pressed
        elif key in self.steer_keys:
            self.steer_keys[key] = pressed
        elif key == Qt.Key.Key_Escape:
            if pressed:
                self.emergency_stop()
        else:
            return False
        self._refresh_keys()
        return True

    def release_all(self) -> None:
        self.drive.forward = self.drive.reverse = False
        for key in self.steer_keys:
            self.steer_keys[key] = False
        self._refresh_keys()

    def _refresh_keys(self) -> None:
        self.forward_tile.set_on(self.drive.forward and not self.drive.reverse)
        self.reverse_tile.set_on(self.drive.reverse and not self.drive.forward)

    def tick(self) -> None:
        now = self.clock()
        dt = min(max(now - self._last_tick, 0.0), 0.1)
        self._last_tick = now
        if self.connector is not None and self.connector.done():
            self._connector_finished()
        turn = self.steer_keys[Qt.Key.Key_Left] - self.steer_keys[Qt.Key.Key_Right]
        if turn:
            self.wheel.rotate_by(-turn * KEY_STEER_RATE_DEG_S * dt)
        io = self.io
        if io is not None:
            try:
                if isinstance(io, SimVehicleIO):
                    io.advance(dt)
                else:
                    io.poll(block=False)
                for event in io.events():
                    self._log(f"{event.code}: {event.message}")
                if not io.connected:
                    self._log("Mất kết nối với bo. Bấm Kết nối để nối lại.")
                    _shutdown(io)
                    self.io = None
                    self.driving_allowed = False
                    self._set_status("Mất kết nối", "bad")
                else:
                    self._send(io)
            except VehicleIOError as exc:
                self._log(str(exc))
            if isinstance(io, SimVehicleIO) and self.io is not None:
                pose = io.truth.pose
                self.track.set_pose(pose.x, pose.y, pose.yaw)
        self._refresh_ui()

    def _board_state(self, io: VehicleIO) -> State | None:
        """Trạng thái bo theo telemetry mới nhất; telemetry gửi trước lúc ARM xong (bo đã trả ACK OK) coi là ARMED."""
        latest = io.latest()
        if latest is None:
            return None
        if latest.stamp.t < self._armed_at and latest.state == State.DISARMED:
            return State.ARMED
        return latest.state

    def _send(self, io: VehicleIO) -> None:
        ready = self._board_state(io) in (State.ARMED, State.RUNNING)
        if self.driving_allowed and ready and not io.rearm_required:
            limits = io.hello.limits
            v, steer = drive_command(self.drive, steer_limit(io, self.mode), limits.max_speed_mps)
            validity = min(VALIDITY_S[self.mode], limits.max_validity_s)
            io.send(v, steer, validity_s=validity)
            self.last_command = (v, steer)
        else:
            self.last_command = (0.0, 0.0)
            if io.now() - io.last_tx_time >= PING_IDLE_S:
                io.ping()

    # ---- hiển thị -----------------------------------------------------------------------------------------------
    def _refresh_ui(self, force: bool = False) -> None:
        now = self.clock()
        if not force and now - self._last_ui < UI_REFRESH_S:
            return
        self._last_ui = now
        connecting = self.connector is not None
        io = self.io
        busy = connecting or io is not None
        self.connect_button.setText("Hủy" if connecting else ("Ngắt" if io is not None else "Kết nối"))
        self.mode_box.setEnabled(not busy)
        self.host.setEnabled(not busy)
        self.port_box.setEnabled(not busy)
        self.refresh_ports.setEnabled(not busy)
        latest = io.latest() if io is not None else None
        state = self._board_state(io) if io is not None else None
        can_drive = (io is not None and self.driving_allowed and not io.rearm_required
                     and state in (State.ARMED, State.RUNNING))
        self.arm_button.setEnabled(io is not None and not can_drive)
        self.stop_button.setEnabled(io is not None)
        self.wheel.active = can_drive
        self.wheel.update()
        if connecting:
            wait = " · gõ mật khẩu Pi trong cửa sổ dòng lệnh" if self.mode == "pi" else ""
            self._set_status(f"Đang kết nối{wait}", "warn")
        elif io is not None:
            if can_drive:
                self._set_status("Sẵn sàng lái", "ok")
            elif io.rearm_required:
                self._set_status("Mất liên lạc · bấm Bật lái", "bad")
            elif state == State.FAULT:
                self._set_status(f"Lỗi bo: {latest.fault.name} · bấm Bật lái", "bad")
            else:
                self._set_status("Đã tắt lái · bấm Bật lái", "warn")
        elif self.status.property("tone") != "bad":
            self._set_status("Chưa kết nối")

        v, steer = self.last_command
        self.tele["command"].setText(f"{v:+.2f} m/s · {math.degrees(steer):+.1f}°")
        if latest is None:
            for key in ("state", "ref", "measured", "effort", "stop", "link"):
                self.tele[key].setText("—")
            return
        self.tele["state"].setText(STATE_TEXT.get(state, str(state)))
        self.tele["ref"].setText(f"{latest.speed_ref_mps:+.2f} m/s · {math.degrees(latest.steer_ref_rad):+.1f}°")
        if latest.speed_mps is None and latest.steer_rad is None:
            self.tele["measured"].setText("chưa có cảm biến")
        else:
            sv = "—" if latest.speed_mps is None else f"{latest.speed_mps:+.2f} m/s"
            st = "—" if latest.steer_rad is None else f"{math.degrees(latest.steer_rad):+.1f}°"
            self.tele["measured"].setText(f"{sv} · {st}")
        self.tele["effort"].setText(f"{latest.effort * 100:+.0f} %")
        stopped = latest.state != State.RUNNING           # lý do dừng gần nhất chỉ có nghĩa khi không chạy
        self.tele["stop"].setText(latest.stop_reason.name if latest.stop_reason and stopped else "—")
        rtt = io.stats.ack_rtt_s
        age = max(0.0, io.now() - latest.stamp.t)
        self.tele["link"].setText(f"telemetry {age * 1000:.0f} ms trước" + (f" · ACK {rtt * 1000:.0f} ms" if rtt else ""))

    # ---- bàn phím -----------------------------------------------------------------------------------------------
    def keys_live(self) -> bool:
        """Phím lái chỉ có tác dụng khi trang đang hiện và cửa sổ AutoPark đang được chọn."""
        return self.isVisible() and self.window().isActiveWindow()

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        if kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if event.isAutoRepeat() or not self.keys_live():
                return False
            key = event.key()
            focus = QApplication.focusWidget()
            typing = isinstance(focus, (QLineEdit, QAbstractSpinBox)) and focus.isEnabled()
            if typing and key != Qt.Key.Key_Escape:
                return False
            return self.set_key(key, kind == QEvent.Type.KeyPress)
        if kind in (QEvent.Type.ApplicationDeactivate, QEvent.Type.WindowDeactivate):
            self.release_all()
        return False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        app = QApplication.instance()
        if app is not None and not self._filter_installed:
            app.installEventFilter(self)
            self._filter_installed = True

    def hideEvent(self, event) -> None:
        self.release_all()                  # chuyển trang: coi như nhả hết phím, xe về 0
        app = QApplication.instance()
        if app is not None and self._filter_installed:
            app.removeEventFilter(self)
            self._filter_installed = False
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.release_all()
        self.disconnect_link()
        event.accept()
