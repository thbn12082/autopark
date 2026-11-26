"""Lái tay (thêm 26/11/2026): vô lăng chỉnh góc lái, giữ Space để tiến, giữ W để lùi.

```
Lái tay
├── Kết nối ............... dùng kết nối chung của tab Kết nối xe (ui/car_connection.py); tab này không tự kết nối
├── Vô lăng ............... kéo chuột để xoay, ← → cũng xoay, nhấp đúp về giữa; giữ nguyên góc khi nhả chuột
├── Space / W ............. giữ để tiến / lùi với tốc độ đặt bằng thanh trượt; nhả phím là về 0; giữ cả hai là 0
└── Esc hoặc nút DỪNG ..... dừng và DISARM; "Bật lái" để ARM lại
```

Tab này chỉ là nguồn lệnh (`CarConnection.command_source`): kết nối chung gửi lệnh 50 lần/giây, mỗi lệnh có hạn ngắn,
nên app treo hay Wi-Fi rớt thì xe tự về trung tính (firmware). Phím chỉ được tính khi cửa sổ AutoPark đang được chọn và
tab này đang hiện; chuyển cửa sổ hay chuyển tab thì coi như nhả hết phím. Tốc độ là tốc độ đặt cho firmware; xe chưa có
MT6701 nên firmware chạy vòng hở (ga theo feedforward), tốc độ thật có thể khác.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSizePolicy, QSlider, QVBoxLayout, QWidget)

from autopark.transport.protocol import State
from autopark.ui import theme
from autopark.ui.car_connection import (FALLBACK_MAX_SPEED_MPS, STATE_TEXT, CarConnection, page_style, panel,
                                        set_tone, value_grid)

TICK_MS = 20
UI_REFRESH_S = 0.1
WHEEL_MAX_DEG = 270.0             # vô lăng xoay ±270° là hết lái
KEY_STEER_RATE_DEG_S = 360.0      # giữ ← → thì vô lăng quay ngần này độ mỗi giây
DEFAULT_SPEED_MPS = 0.10


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
        rim_w = max(14.0, r * 0.13)
        rim_r = r - 12 - rim_w / 2          # vành luôn nằm trong cung chỉ góc, cách 12 px, ở mọi cỡ
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


# ------------------------------------------------------------------------------------------------ tab
EXTRA_STYLE = f"""
QWidget#manualDrive QLabel#steerReadout {{ font-size: 15px; color: {theme.TEXT}; }}
QWidget#manualDrive QFrame#keyTile {{ background: #15212c; border: 1px solid {theme.BORDER}; border-radius: 12px; }}
QWidget#manualDrive QFrame#keyTile[on="true"] {{ background: #1f3a35; border-color: {theme.ACCENT}; }}
QWidget#manualDrive QLabel#keyName {{ font-family: {theme.MONO}; font-size: 20px; font-weight: 600;
    color: {theme.TEXT_DIM}; }}
QWidget#manualDrive QLabel#keyTitle {{ font-size: 12px; color: {theme.TEXT_FAINT}; }}
QWidget#manualDrive QFrame#keyTile[on="true"] QLabel#keyName {{ color: {theme.ACCENT}; }}
QWidget#manualDrive QFrame#keyTile[on="true"] QLabel#keyTitle {{ color: {theme.TEXT}; }}
QWidget#manualDrive QSlider::groove:horizontal {{ height: 6px; background: #273844; border-radius: 3px; }}
QWidget#manualDrive QSlider::sub-page:horizontal {{ background: {theme.ACCENT}; border-radius: 3px; }}
QWidget#manualDrive QSlider::handle:horizontal {{ background: {theme.TEXT}; width: 16px; margin: -6px 0;
    border-radius: 8px; }}
"""


class ManualDriveWindow(QWidget):
    """Tab Lái tay: nguồn lệnh cho kết nối chung `CarConnection`."""

    def __init__(self, connection: CarConnection, *, clock=None):
        super().__init__()
        self.connection = connection
        self.clock = clock or time.perf_counter
        self.setObjectName("manualDrive")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(page_style("manualDrive") + EXTRA_STYLE)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.drive = DriveInput()
        self.steer_keys = {Qt.Key.Key_Left: False, Qt.Key.Key_Right: False}
        self._last_tick = self.clock()
        self._last_ui = -math.inf
        self._shown_io = None
        self._filter_installed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(12)
        head = QHBoxLayout()
        title = QLabel("Lái tay")
        title.setObjectName("pageTitle")
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.arm_button = QPushButton("Bật lái")
        self.arm_button.setObjectName("arm")
        self.arm_button.setToolTip("ARM lại bo sau khi DỪNG, mất liên lạc hoặc lỗi")
        self.arm_button.clicked.connect(self.connection.arm)
        self.connect_tab_button = QPushButton("Tab Kết nối xe")
        self.connect_tab_button.clicked.connect(lambda: self._go("ket_noi_xe"))
        head.addWidget(title)
        head.addSpacing(14)
        head.addWidget(self.status)
        head.addStretch(1)
        head.addWidget(self.arm_button)
        head.addWidget(self.connect_tab_button)
        root.addLayout(head)

        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(16, 10, 10, 10)
        banner_text = QLabel("Chưa kết nối xe. Kết nối ở tab Kết nối xe rồi quay lại đây để lái.")
        banner_go = QPushButton("Mở tab Kết nối xe")
        banner_go.setObjectName("primary")
        banner_go.clicked.connect(lambda: self._go("ket_noi_xe"))
        bl.addWidget(banner_text, 1)
        bl.addWidget(banner_go)
        root.addWidget(self.banner)

        body = QHBoxLayout()
        body.setSpacing(16)
        wheel_panel = panel("VÔ LĂNG")
        wl = wheel_panel.layout()
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
        pedals = panel("GA")
        pl = pedals.layout()
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
        self.stop_button.setObjectName("stop")
        self.stop_button.clicked.connect(self.emergency_stop)
        pl.addWidget(self.stop_button)
        side.addWidget(pedals)

        tele = panel("XE")
        grid, self.tele = value_grid((("state", "Bo"), ("command", "Lệnh gửi"), ("ref", "Bo đang chạy"),
                                      ("measured", "Đo được"), ("effort", "Ga ra ESC"), ("stop", "Lý do dừng"),
                                      ("link", "Liên lạc")))
        tele.layout().addLayout(grid)
        side.addWidget(tele)

        self.track = TrackView()
        self.track_panel = panel("ĐƯỜNG ĐI (MÔ PHỎNG)")
        self.track_panel.layout().addWidget(self.track, 1)
        side.addWidget(self.track_panel, 1)
        body.addLayout(side, 4)
        root.addLayout(body, 1)

        hint = QLabel("Giữ Space để tiến, giữ W để lùi, nhả phím là dừng. Kéo vô lăng bằng chuột hoặc giữ ← →, "
                      "nhấp đúp để về giữa. Esc: dừng và tắt lái. Phím chỉ có tác dụng khi cửa sổ này đang được chọn.")
        hint.setObjectName("pageHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        for button in self.findChildren(QPushButton):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)       # Space không được "bấm" nút nào

        connection.command_source = self.command
        self._speed_changed(self.speed.value())
        self._wheel_changed(0.0)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)
        self._refresh_ui(force=True)

    def _go(self, key: str) -> None:
        window = self.window()
        if hasattr(window, "show_page"):
            window.show_page(key)

    # ---- lệnh ---------------------------------------------------------------------------------------------------
    def command(self) -> tuple[float, float]:
        """Lệnh hiện tại cho kết nối chung: (tốc độ m/s có dấu, góc lái rad)."""
        c = self.connection
        return drive_command(self.drive, c.steer_limit(), c.max_speed())

    def emergency_stop(self) -> None:
        self.drive.forward = self.drive.reverse = False
        self._refresh_keys()
        self.connection.stop()
        self._refresh_ui(force=True)

    def _wheel_changed(self, value: float) -> None:
        self.drive.steer_frac = value
        deg = math.degrees(value * self.connection.steer_limit())
        side = "trái" if deg > 0.05 else ("phải" if deg < -0.05 else "thẳng")
        servo = "" if self.connection.is_sim else f" · servo {self.connection.servo_us(math.radians(deg))} µs"
        self.steer_readout.setText(f"Góc lái {abs(deg):.1f}° {side}{servo}")
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
        turn = self.steer_keys[Qt.Key.Key_Left] - self.steer_keys[Qt.Key.Key_Right]
        if turn:
            self.wheel.rotate_by(-turn * KEY_STEER_RATE_DEG_S * dt)
        c = self.connection
        if c.io is not self._shown_io:            # vừa kết nối/ngắt: cập nhật giới hạn, xóa vết mô phỏng
            self._shown_io = c.io
            self.speed.setMaximum(max(self.speed.minimum(), int(c.max_speed() * 100 + 1e-6)))
            self._speed_changed(self.speed.value())
            self._wheel_changed(self.wheel.value)
            self.track.reset()
            if c.io is not None and self.isVisible():
                self.setFocus()
        if c.is_sim:
            pose = c.io.truth.pose
            self.track.set_pose(pose.x, pose.y, pose.yaw)
        self._refresh_ui()

    # ---- hiển thị -----------------------------------------------------------------------------------------------
    def _refresh_ui(self, force: bool = False) -> None:
        now = self.clock()
        if not force and now - self._last_ui < UI_REFRESH_S:
            return
        self._last_ui = now
        c = self.connection
        set_tone(self.status, *c.status())
        self.banner.setVisible(not c.connected)
        self.track_panel.setVisible(c.is_sim)
        can_drive = c.can_drive()
        self.arm_button.setVisible(c.connected and not can_drive)
        self.stop_button.setEnabled(c.connected)
        if self.wheel.active != can_drive:
            self.wheel.active = can_drive
            self.wheel.update()
        v, steer = c.last_command
        self.tele["command"].setText(f"{v:+.2f} m/s · {math.degrees(steer):+.1f}°")
        io = c.io
        latest = io.latest() if io is not None else None
        if latest is None:
            for key in ("state", "ref", "measured", "effort", "stop", "link"):
                self.tele[key].setText("—")
            return
        self.tele["state"].setText(STATE_TEXT.get(c.board_state(), "—"))
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
        """Phím lái chỉ có tác dụng khi tab đang hiện và cửa sổ AutoPark đang được chọn."""
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
        self.setFocus()
        app = QApplication.instance()
        if app is not None and not self._filter_installed:
            app.installEventFilter(self)
            self._filter_installed = True

    def hideEvent(self, event) -> None:
        self.release_all()                  # chuyển tab: coi như nhả hết phím, xe về 0
        app = QApplication.instance()
        if app is not None and self._filter_installed:
            app.removeEventFilter(self)
            self._filter_installed = False
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.release_all()
        if self.connection.command_source == self.command:
            self.connection.command_source = None
        event.accept()
