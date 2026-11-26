"""Thẻ "3D quanh xe" (thêm 26/11/2026): cảnh 3D từ bốn camera, kéo chuột để xoay, lăn để phóng to.

Máy có OpenGL 3.3 thì vẽ bằng GPU (`ui.surround_3d_gl`): xoay mượt theo nhịp màn hình. Không có thì dựng bằng CPU ở luồng
nền (`perception.surround_3d.Surround3DRenderer`, kéo chuột dựng ở nửa độ phân giải). Chưa có ảnh từ Pi thì hiện **cảnh
mẫu** (sa bàn tổng hợp) để xem thử.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
import threading
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QWidget)

from autopark.ui import theme

OVERLAY_STYLE = f"""
QLabel#badge {{ margin: 14px; padding: 6px 12px; border-radius: 13px; font-size: 12px; font-weight: 600; }}
QLabel#badge[tone="warn"] {{ color: {theme.WARN}; background: rgba(48, 36, 18, 210); border: 1px solid #6b5228; }}
QLabel#badge[tone="ok"] {{ color: {theme.OK}; background: rgba(18, 44, 38, 210); border: 1px solid #2f6b5c; }}
QFrame#presetBar {{ margin-bottom: 16px; background: rgba(12, 19, 27, 215); border: 1px solid {theme.BORDER};
    border-radius: 14px; }}
QPushButton#preset {{ background: transparent; color: {theme.TEXT_DIM}; border: none; border-radius: 9px;
    padding: 7px 14px; font-size: 12px; }}
QPushButton#preset:hover {{ background: rgba(38, 57, 71, 220); color: {theme.TEXT}; }}
QPushButton#preset:checked {{ background: rgba(31, 58, 53, 235); color: {theme.ACCENT}; font-weight: 600; }}
QLabel#hint3d {{ margin: 0 16px 22px 0; padding: 5px 10px; color: {theme.TEXT_DIM}; font-size: 11px;
    background: rgba(12, 19, 27, 190); border-radius: 10px; }}
"""

LIVE_TIMEOUT_S = 1.5          # quá chừng này không có ảnh mới từ Pi thì quay về cảnh mẫu
FRAME_INTERVAL_S = 0.10       # tối đa 10 khung/giây
DRAG_QUALITY = 0.5


def _make_renderer():
    from autopark.perception.surround_3d import Surround3DRenderer
    return Surround3DRenderer()


class _Canvas(QWidget):
    """Vẽ ảnh mới nhất giữ tỷ lệ; báo kéo chuột và lăn chuột."""

    dragged = Signal(float, float)       # dx, dy (pixel) từ lúc nhấn
    pressed = Signal()
    released = Signal()
    wheeled = Signal(float)              # số nấc lăn (dương = lăn ra xa)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.pixmap: QPixmap | None = None
        self._start: QPointF | None = None

    def present(self, pixmap: QPixmap) -> None:
        self.pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.BG))
        if self.pixmap is not None:
            scale = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
            w, h = self.pixmap.width() * scale, self.pixmap.height() * scale
            target = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
        else:
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Đang dựng cảnh 3D…")
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.pressed.emit()

    def mouseMoveEvent(self, event):
        if self._start is not None:
            delta = event.position() - self._start
            self.dragged.emit(delta.x(), delta.y())

    def mouseReleaseEvent(self, event):
        if self._start is not None and event.button() == Qt.MouseButton.LeftButton:
            self._start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.released.emit()

    def wheelEvent(self, event):
        self.wheeled.emit(-event.angleDelta().y() / 120.0)


class Surround3DPanel(QWidget):
    """Cảnh 3D quanh xe. `submit(frames, overlays)` khi có ảnh mới; không gọi thì hiện cảnh mẫu."""

    rendered = Signal(bool, bool)        # (đang xem thử gá giả định, đang dùng cảnh mẫu)
    _completed = Signal(object)

    def __init__(self, parent=None, *, renderer_factory=None, clock=time.monotonic, use_gl: bool | None = None):
        super().__init__(parent)
        from autopark.perception.surround_3d import PRESETS
        from autopark.ui.surround_3d_gl import gl_available

        self._presets = PRESETS
        self.setStyleSheet(OVERLAY_STYLE)
        # nhãn trạng thái nổi ở góc trên trái của khung hình
        self.notice = QLabel("Đang chuẩn bị cảnh 3D…")
        self.notice.setObjectName("badge")
        self.notice.setProperty("tone", "warn")
        # thanh góc nhìn nổi ở cạnh dưới của khung hình
        self.preset_bar = QFrame()
        self.preset_bar.setObjectName("presetBar")
        bar = QHBoxLayout(self.preset_bar)
        bar.setContentsMargins(6, 6, 6, 6)
        bar.setSpacing(2)
        self.preset_buttons: dict[str, QPushButton] = {}
        self._preset_group = QButtonGroup(self)
        self._preset_group.setExclusive(True)
        for key, (label, _view) in PRESETS.items():
            button = QPushButton(label)
            button.setObjectName("preset")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, k=key: self.use_preset(k))
            self._preset_group.addButton(button)
            self.preset_buttons[key] = button
            bar.addWidget(button)
        self.preset_buttons["sau_phai"].setChecked(True)
        self.hint = QLabel("Kéo để xoay · lăn để phóng to")
        self.hint.setObjectName("hint3d")
        self.gl = (gl_available() if use_gl is None else use_gl) and renderer_factory is None
        self._gl_notice = ""
        if self.gl:
            from autopark.perception.surround_view import display_cameras
            from autopark.ui.surround_3d_gl import Surround3DGLWidget
            cameras, preview, self._gl_notice = display_cameras()
            self._gl_cameras, self._gl_preview = cameras, preview
            self.canvas = Surround3DGLWidget(cameras, is_preview=preview, parent=self)
            self.canvas.on_manual_view = self._clear_preset
        else:
            self.canvas = _Canvas(self)
            self.canvas.pressed.connect(self._drag_start)
            self.canvas.dragged.connect(self._drag)
            self.canvas.released.connect(self._drag_end)
            self.canvas.wheeled.connect(self._zoom)
        stage = QGridLayout(self)
        stage.setContentsMargins(0, 0, 0, 0)
        stage.addWidget(self.canvas, 0, 0)
        stage.addWidget(self.notice, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        stage.addWidget(self.preset_bar, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
        stage.addWidget(self.hint, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        for overlay in (self.notice, self.preset_bar, self.hint):
            overlay.raise_()

        self.clock = clock
        self.view = PRESETS["sau_phai"][1]
        self.quality = 1.0
        self._drag_from = None
        self._renderer_factory = renderer_factory or _make_renderer
        self._renderer = None
        self._demo = None
        self._frames: dict[int, np.ndarray] = {}
        self._overlays = None
        self._live_at: float | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autopark-3d")
        self._closed = threading.Event()
        self._active: Future | None = None
        self._dirty = True
        self._last_start = -1e9
        self.using_demo = True
        self._demo_future: Future | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(int(FRAME_INTERVAL_S * 1000))
        self._timer.timeout.connect(self._tick)
        self._completed.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        self._timer.start()

    # ------------------------------------------------------------------ đầu vào
    def submit(self, frames: dict[int, np.ndarray], overlays=None) -> None:
        """Ảnh mới từ Pi (cổng → BGR 640×480) và lớp vẽ chồng (`surround_3d.Overlays`)."""
        if frames:
            self._frames = dict(frames)
            self._live_at = self.clock()
        if overlays is not None:
            self._overlays = overlays
        if self.gl:
            if frames:
                if self.using_demo:                       # bỏ ảnh mẫu còn lại trên các cổng chưa có ảnh thật
                    self.canvas.clear_frames()
                    self.using_demo = False
                    self._show_gl_notice()
                self.canvas.set_frames(frames)
            if overlays is not None:
                self.canvas.set_overlays(overlays)
            return
        self._dirty = True

    def use_preset(self, key: str) -> None:
        self.preset_buttons[key].setChecked(True)
        self.set_view(self._presets[key][1])

    def set_view(self, view, quality: float = 1.0) -> None:
        self.view = view.clamped()
        self.quality = quality
        self._dirty = True
        if self.gl:
            self.canvas.set_view(self.view)

    def _clear_preset(self):
        self._preset_group.setExclusive(False)
        for button in self.preset_buttons.values():
            button.setChecked(False)
        self._preset_group.setExclusive(True)

    def _drag_start(self):
        self._clear_preset()
        self._drag_from = self.view

    def _drag(self, dx, dy):
        if self._drag_from is None:
            return
        base = self._drag_from
        self.set_view(replace(base, azimuth_deg=base.azimuth_deg - 0.4 * dx,
                              elevation_deg=base.elevation_deg + 0.3 * dy), DRAG_QUALITY)

    def _drag_end(self):
        self._drag_from = None
        self.set_view(self.view, 1.0)

    def _zoom(self, steps):
        self.set_view(replace(self.view, distance_m=self.view.distance_m * (1.1 ** steps)), 1.0)

    # ------------------------------------------------------------------ dựng nền
    def _tick_gl(self, live: bool):
        """GPU: chỉ lo chuyển giữa ảnh thật và cảnh mẫu; xoay đã vẽ ngay trong canvas."""
        if live or self._closed.is_set():
            return
        if self._demo is None:
            if self._demo_future is None:
                from autopark.perception import surround_3d as s3
                self._demo_future = self._executor.submit(s3.demo_frames, self._gl_cameras)
            if not self._demo_future.done():
                return
            self._demo = self._demo_future.result()
        if not self.using_demo or not self.canvas._frames:
            self.canvas.clear_frames()
            self.canvas.set_frames(self._demo)
            self.using_demo = True
            self._show_gl_notice()
            self.rendered.emit(self._gl_preview, True)

    def _show_gl_notice(self):
        self._set_badge(self.using_demo, self._gl_preview, self._gl_notice + " Vẽ bằng GPU.")

    def _set_badge(self, demo: bool, preview: bool, detail: str) -> None:
        """Nhãn nổi: nguồn ảnh · tình trạng hiệu chuẩn; lời giải thích đầy đủ ở tooltip."""
        source = "Cảnh mẫu" if demo else "Ảnh trực tiếp"
        calib = "gá camera giả định" if preview else "đã hiệu chuẩn"
        self.notice.setText(f"●  {source} · {calib}")
        tip = ("Chưa có ảnh từ Pi: đang hiện sa bàn tổng hợp để xem thử. " if demo else "") + detail
        self.notice.setToolTip(tip)
        tone = "warn" if (demo or preview) else "ok"
        if self.notice.property("tone") != tone:
            self.notice.setProperty("tone", tone)
            self.notice.style().unpolish(self.notice)
            self.notice.style().polish(self.notice)

    def _tick(self):
        live = self._live_at is not None and self.clock() - self._live_at <= LIVE_TIMEOUT_S
        if self.gl:
            self._tick_gl(live)
            return
        if live == self.using_demo:            # đổi giữa ảnh thật và cảnh mẫu
            self._dirty = True
        if self._closed.is_set() or self._active is not None or not self._dirty or not self.isVisible():
            return
        self._dirty = False
        self._last_start = self.clock()
        job = (self.view.scaled(self.quality) if self.quality < 1.0 else self.view,
               dict(self._frames) if live else None, self._overlays)
        self._active = self._executor.submit(self._render, *job)
        self._active.add_done_callback(self._notify)

    def _render(self, view, frames, overlays):
        from autopark.perception import surround_3d as s3
        from autopark.ui.rig_app import to_qimage
        if self._renderer is None:
            self._renderer = self._renderer_factory()
        r = self._renderer
        if r.view is None or r.view != replace(view, target=r.view.target):
            r.set_view(view)
        demo = frames is None
        if demo:
            if self._demo is None:
                self._demo = s3.demo_frames(r.cameras)
            frames = self._demo
        image = r.render(frames, overlays)
        return to_qimage(np.ascontiguousarray(image)), r.is_preview, demo, r.notice

    def _notify(self, future):
        if not self._closed.is_set():
            try:
                self._completed.emit(future)
            except RuntimeError:
                pass

    def _finish(self, future):
        if future is not self._active:
            return
        self._active = None
        if self._closed.is_set():
            return
        try:
            image, is_preview, demo, notice = future.result()
        except Exception as exc:  # noqa: BLE001 - báo lỗi dựng hình trong giao diện
            self.notice.setText(f"Lỗi dựng cảnh 3D: {' '.join(str(exc).split())[:200]}")
            return
        self.using_demo = demo
        self._set_badge(demo, is_preview, notice)
        self.canvas.present(QPixmap.fromImage(image))
        self.rendered.emit(is_preview, demo)

    def wait_idle(self, timeout: float = 30.0) -> bool:
        """Chờ lần dựng đang chạy xong (cho test)."""
        future = self._active
        if future is None:
            return True
        future.result(timeout)
        return True

    def shutdown(self) -> None:
        if not self._closed.is_set():
            self._closed.set()
            self._timer.stop()
            self._executor.shutdown(wait=False, cancel_futures=True)

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
