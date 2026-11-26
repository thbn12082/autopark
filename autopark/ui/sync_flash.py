"""Ô nháy của dấu đồng bộ video–log (T14, docs/KIEM_THU_VA_LO_TRINH.md): một ô vuông trắng lớn có số thứ tự, trên
nền đen, sáng `FLASH_MS` rồi tắt — camera quay R3 nhìn màn hình laptop thấy cả lúc bật lẫn lúc tắt.

- Trong cửa sổ có sẵn (`SyncFlash(host)`, cockpit đỗ xe và `ui.rig_app`): một widget con phủ toàn bộ cửa sổ, nâng lên
  trên mọi widget anh em (cả các ngăn và thanh trạng thái) lúc nháy. Widget anh em tạo SAU lúc đó nằm trên ô, nên cửa sổ
  chủ phải tạo sẵn chúng: QMainWindow chỉ tạo thanh trạng thái ở lần gọi `statusBar()` đầu tiên, nên cockpit gọi nó lúc
  dựng (review 02/10/2026). Không tạo cửa sổ hệ điều hành mới, không đổi tiêu điểm bàn phím, không có hiệu ứng hiện/ẩn
  của Windows; vẽ xong ngay trong `repaint()` (thử offscreen 02/10/2026). Ô không nhận chuột: cú bấm xuyên qua nó, nên
  cockpit từ chối Bắt đầu đỗ khi ô còn sáng.
- Không có cửa sổ (`SyncFlash(None, screen)`, `rig.bench` chạy trong cửa sổ lệnh): một cửa sổ không viền, luôn trên cùng,
  không nhận chuột/phím/tiêu điểm, phủ cả một màn hình. Windows làm mờ dần cửa sổ lúc hiện/ẩn, làm nhòe cạnh bật qua vài
  khung video: `disable_window_transitions` tắt hiệu ứng đó (DWMWA_TRANSITIONS_FORCEDISABLED). Cửa sổ mới hiện chỉ được vẽ
  khi hệ điều hành báo đã hiện (expose) trong vòng sự kiện — `repaint()` ngay sau `show()` không vẽ gì (thử offscreen
  02/10/2026) — nên `show_mark` chờ tới lúc đó (tối đa `EXPOSE_WAIT_S`) rồi mới vẽ. Trên màn hình Windows thật: CHƯA THỬ
  (hiệu ứng hiện/ẩn, việc không lấy tiêu điểm của cửa sổ lệnh, khóa màn hình trong phiên dài).

`SyncMarker` nối ô nháy với `evaluation.sync_marks.SyncMarkLog`: đọc `perf_counter` NGAY SAU khi ô đã vẽ, từ chối dấu mới
khi ô còn sáng hoặc chưa đủ `MIN_GAP_S` (hai dấu không dính nhau trong video). Mô-đun này chỉ nhập thư viện chuẩn, PySide6
và `evaluation.sync_marks` (không torch, không mô-đun camera), để `ui.lidar_app` vẫn không kéo theo torch.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QCoreApplication, QEventLoop, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QScreen
from PySide6.QtWidgets import QWidget

from autopark.evaluation.sync_marks import CLOCK, SYNC_MARK, SyncMarkLog

FLASH_MS = 500            # ≥ 10 khung ở 24 khung/s: thấy rõ cả cạnh bật lẫn cạnh tắt
MIN_GAP_S = 1.0           # hai dấu cách nhau ít nhất chừng ấy, không dính nhau trong video
SQUARE_SHARE = 0.9        # cạnh ô trắng = chừng ấy × cạnh ngắn của vùng phủ
EXPOSE_WAIT_S = 0.25      # cửa sổ riêng: chờ hệ điều hành báo đã hiện tối đa chừng ấy trước khi vẽ
DWMWA_TRANSITIONS_FORCEDISABLED = 3


def disable_window_transitions(widget: QWidget) -> bool:
    """Tắt hiệu ứng hiện/ẩn của Windows (DWM) cho một cửa sổ. True khi đã tắt; False ngoài Windows, ở nền offscreen, với
    widget con, hoặc khi lời gọi lỗi."""
    if sys.platform != "win32" or QGuiApplication.platformName() != "windows" or not widget.isWindow():
        return False
    try:
        import ctypes

        value = ctypes.c_int(1)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(int(widget.winId())),
                                                            DWMWA_TRANSITIONS_FORCEDISABLED, ctypes.byref(value),
                                                            ctypes.sizeof(value))
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    return result == 0


class SyncFlash(QWidget):
    """Ô trắng có số trên nền đen. `host`: phủ cửa sổ đó (widget con). `host` None: cửa sổ riêng phủ `screen` (None = màn
    hình chính). Không nhận chuột, không nhận tiêu điểm; ẩn cho tới `show_mark`."""

    def __init__(self, host: QWidget | None = None, screen: QScreen | None = None):
        super().__init__(host)
        self.host = host
        self.target_screen = screen
        self.number = 0
        self.transitions_off = False
        if host is None:
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                                | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
                                | Qt.WindowType.WindowDoesNotAcceptFocus)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.transitions_off = disable_window_transitions(self)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.finish)

    def area(self) -> QRect:
        """Vùng phủ: toàn bộ cửa sổ chủ (tọa độ của nó), hoặc toàn bộ màn hình đã chọn."""
        if self.host is not None:
            return self.host.rect()
        return (self.target_screen or QGuiApplication.primaryScreen()).geometry()

    def show_mark(self, number: int, duration_ms: int = FLASH_MS) -> None:
        """Hiện ô số `number`, vẽ xong rồi mới trả về; tự tắt sau `duration_ms` (cần vòng sự kiện Qt chạy)."""
        self.number = number
        self.setGeometry(self.area())
        self.show()
        self.raise_()
        if self.isWindow():
            self._wait_exposed()
        self.repaint()
        self.timer.start(duration_ms)

    def _wait_exposed(self, timeout_s: float = EXPOSE_WAIT_S) -> None:
        """Cửa sổ riêng: xử lý sự kiện cho tới khi hệ điều hành báo cửa sổ đã hiện (lần vẽ đầu nằm trong sự kiện đó)."""
        deadline = time.perf_counter() + timeout_s
        while not self.testAttribute(Qt.WidgetAttribute.WA_Mapped) and time.perf_counter() < deadline:
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 5)
            if not self.testAttribute(Qt.WidgetAttribute.WA_Mapped):
                time.sleep(0.001)

    def finish(self) -> None:
        self.timer.stop()
        self.hide()

    def lit(self) -> bool:
        """Ô đang bật. Dùng `isHidden()` chứ không dùng `isVisible()`: cửa sổ trong test không bao giờ được hiện."""
        return not self.isHidden()

    def square(self) -> QRect:
        side = int(SQUARE_SHARE * min(self.width(), self.height()))
        return QRect((self.width() - side) // 2, (self.height() - side) // 2, side, side)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        square = self.square()
        painter.fillRect(square, QColor("#ffffff"))
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(max(1, int(0.45 * square.width())))
        painter.setFont(font)
        painter.setPen(QColor("#000000"))
        painter.drawText(square, Qt.AlignmentFlag.AlignCenter, str(self.number))
        painter.end()


class SyncMarker:
    """Tạo dấu đồng bộ: nháy `flash` rồi ghi dòng SYNC_MARK vào `log`; `clock_row` ghi dòng CLOCK (không nháy).

    `open_file`: hàm trả đường dẫn tệp sống; gọi ở dấu đầu tiên nếu `log` chưa có tệp (không có dấu nào thì không tạo
    tệp nào). `flash_ms`, `min_gap_s` đọc từ hằng của mô-đun lúc dựng (test đổi hằng trước khi dựng)."""

    def __init__(self, log: SyncMarkLog, flash: SyncFlash, *, clock: Callable[[], float] = time.perf_counter,
                 open_file: Callable[[], Path] | None = None):
        self.log, self.flash, self.clock, self.open_file = log, flash, clock, open_file
        self.flash_ms = FLASH_MS
        self.min_gap_s = MIN_GAP_S
        self.last_t: float | None = None

    def ready(self, now: float | None = None) -> bool:
        """Ô đã tắt và đã đủ `min_gap_s` từ dấu trước."""
        if self.flash.lit():
            return False
        if self.last_t is None:
            return True
        return (self.clock() if now is None else now) - self.last_t >= self.min_gap_s

    def mark(self, trigger: str, context: Callable[[float], dict] | None = None) -> dict | None:
        """Một dấu: dòng SYNC_MARK đã thêm, hoặc None khi chưa được phép (ô còn sáng / chưa đủ khoảng cách; không thêm
        dòng nào). `context(t_perf)` trả các cột thêm (state, t_session, t_io, …). Không tạo được tệp sống thì vẫn nháy và
        giữ dấu trong bộ nhớ; lỗi ở `log.error`."""
        now = self.clock()
        if not self.ready(now):
            return None
        if self.log.path is None and self.open_file is not None:
            try:
                self.log.open(self.open_file())
            except OSError as exc:
                self.log.error = f"không tạo được tệp dấu đồng bộ: {type(exc).__name__}: {exc}"
        t0 = self.clock()
        self.flash.show_mark(self.log.marks + 1, self.flash_ms)
        t_perf = self.clock()
        self.last_t = t_perf
        fields = dict(context(t_perf)) if context is not None else {}
        fields.update(trigger=trigger, flash_ms=self.flash_ms, paint_ms=round(1000.0 * (t_perf - t0), 3))
        return self.log.add(SYNC_MARK, t_perf, **fields)

    def clock_row(self, trigger: str, context: Callable[[float], dict] | None = None) -> dict:
        """Dòng CLOCK: ghép `t_perf` lúc này với các đồng hồ khác do `context(t_perf)` trả; không nháy."""
        t = self.clock()
        fields = dict(context(t)) if context is not None else {}
        fields["trigger"] = trigger
        return self.log.add(CLOCK, t, **fields)
