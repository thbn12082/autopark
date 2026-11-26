"""Góc nhìn quanh xe, lấy ảnh từ các ô camera đang quan sát."""
from __future__ import annotations

import math
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from autopark.ui.rig_app import to_qimage


_RENDER_INTERVAL_S = 0.10
_NOTICE_STYLE = "padding: 7px 10px; border-radius: 5px; font-weight: 600;"
_NOTICE_NEUTRAL = _NOTICE_STYLE + "color: #9cafbe; background: #1c2a36;"
_NOTICE_PREVIEW = _NOTICE_STYLE + "color: #efb76b; background: #3a2e1c;"


def _make_renderer():
    from autopark.perception.surround_view import SurroundViewRenderer

    return SurroundViewRenderer()


class _SquareCanvas(QWidget):
    painted = Signal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(290, 290)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pixmap = None
        self._unreported = None

    def present(self, pixmap, camera_count: int, is_preview: bool) -> None:
        self._pixmap = pixmap
        self._unreported = (camera_count, is_preview)
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self._unreported = None
        self.update()

    def paintEvent(self, event):
        inner = QRectF(self.rect()).adjusted(45, 24, -45, -24)
        side = min(inner.width(), inner.height())
        center = inner.center()
        square = QRectF(center.x() - side / 2, center.y() - side / 2, side, side)

        painter = QPainter(self)
        painter.fillRect(square, QColor("#101821"))
        if self._pixmap is not None:
            scale = side / max(self._pixmap.width(), self._pixmap.height())
            width, height = self._pixmap.width() * scale, self._pixmap.height() * scale
            target = QRectF(center.x() - width / 2, center.y() - height / 2, width, height)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
        else:
            painter.setPen(QColor("#aebfcd"))
            painter.drawText(square, Qt.AlignmentFlag.AlignCenter, "Chờ ảnh mới")

        painter.setPen(QPen(QColor("#42596d"), 1))
        painter.drawRect(square)
        font = QFont(painter.font())
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        for text, area in (
            ("↑ Trước", QRectF(square.left(), square.top() - 24, side, 24)),
            ("Sau", QRectF(square.left(), square.bottom(), side, 24)),
            ("Trái", QRectF(square.left() - 45, square.top(), 45, side)),
            ("Phải", QRectF(square.right(), square.top(), 45, side)),
        ):
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()

        if self._unreported is not None:
            sample, self._unreported = self._unreported, None
            self.painted.emit(*sample)


class SurroundViewPanel(QWidget):
    """Ghép ảnh trên một luồng nền và hiển thị kết quả còn mới."""

    rendered = Signal(int, bool)  # số ảnh nguồn của khung đã vẽ, chế độ xem thử
    _completed = Signal(object)

    def __init__(self, parent=None, *, renderer_factory=None):
        super().__init__(parent)
        self.notice = QLabel("Góc nhìn quanh xe đang chờ ảnh camera.")
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet(_NOTICE_NEUTRAL)
        self.canvas = _SquareCanvas(self)
        self.canvas.painted.connect(self.rendered.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.notice)
        layout.addWidget(self.canvas, 1)

        self._renderer_factory = _make_renderer if renderer_factory is None else renderer_factory
        self._renderer = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autopark-surround")
        self._closed = threading.Event()
        self._generation = 0
        self._active: tuple[int, Future] | None = None
        self._pending: tuple[int, dict[int, np.ndarray]] | None = None
        self._last_start = -math.inf
        self._delay = QTimer(self)
        self._delay.setSingleShot(True)
        self._delay.timeout.connect(self._start_next)
        self._completed.connect(self._finish, Qt.ConnectionType.QueuedConnection)

    def submit(self, frames: dict[int, np.ndarray]) -> None:
        if self._closed.is_set():
            return
        self._pending = (self._generation, dict(frames))
        if self._active is None and not self._delay.isActive():
            self._start_next()

    def clear(self) -> None:
        self._generation += 1
        self._pending = None
        self._delay.stop()
        self.canvas.clear()

    def shutdown(self) -> None:
        if not self._closed.is_set():
            self._closed.set()
            self.clear()
            self._active = None
            self._executor.shutdown(wait=False, cancel_futures=True)

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def _start_next(self) -> None:
        if self._closed.is_set() or self._active is not None or self._pending is None:
            return
        now = time.monotonic()
        wait_s = _RENDER_INTERVAL_S - (now - self._last_start)
        if wait_s > 0:
            self._delay.start(math.ceil(1_000 * wait_s))
            return
        generation, frames = self._pending
        self._pending = None
        self._last_start = now
        future = self._executor.submit(self._render, frames)
        self._active = (generation, future)
        future.add_done_callback(self._notify_done)

    def _render(self, frames):
        if self._renderer is None:
            self._renderer = self._renderer_factory()
        image = self._renderer.render(frames)
        if not (isinstance(image, np.ndarray) and image.ndim == 3 and image.shape[2] == 3
                and image.size and image.dtype == np.uint8):
            raise ValueError("Ảnh ghép phải có ba kênh BGR 8 bit")
        return to_qimage(image), len(frames), self._renderer.is_preview, self._renderer.notice

    def _notify_done(self, future):
        if not self._closed.is_set():
            try:
                self._completed.emit(future)
            except RuntimeError:
                pass  # Widget có thể đã bị Qt hủy lúc luồng kết thúc.

    def _finish(self, future):
        if self._active is None or self._active[1] is not future:
            return
        generation = self._active[0]
        self._active = None
        if self._closed.is_set():
            return
        if generation == self._generation:
            try:
                image, camera_count, is_preview, notice = future.result()
            except Exception as exc:  # noqa: BLE001 - báo lỗi renderer trong giao diện
                self.canvas.clear()
                self._show_notice(f"Lỗi ảnh ghép. {' '.join(str(exc).split())[:200]}", False)
            else:
                if is_preview and "xem thử" not in notice.casefold():
                    notice = f"Xem thử · {notice}"
                self._show_notice(notice, is_preview)
                self.canvas.present(QPixmap.fromImage(image), camera_count, is_preview)
        self._start_next()

    def _show_notice(self, text: str, is_preview: bool) -> None:
        if self.notice.text() != text:
            self.notice.setText(text)
        style = _NOTICE_PREVIEW if is_preview else _NOTICE_NEUTRAL
        if self.notice.styleSheet() != style:
            self.notice.setStyleSheet(style)
