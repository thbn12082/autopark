"""Widget hiển thị bản quét LiDAR 2D (PySide6): điểm phản hồi, chùm không có phản hồi, vòng cự ly và nhãn.

Dùng cho màn hình scan của giai đoạn 1 (phát lại DROW trước, RPLIDAR sau). Chỉ vẽ; dữ liệu cũ hay hợp lệ
là việc của `safety.freshness`, widget chỉ đổi màu tiêu đề khi được báo là cũ.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from autopark.domain.sensors import LidarScan
from autopark.lidar.drow import scan_points, valid_mask


class ScanView(QWidget):
    def __init__(self, parent=None, max_range: float = 10.0, front_up: bool = True):
        super().__init__(parent)
        self.max_range = max_range
        self.front_up = front_up           # True: phía trước lên trên; False: cùng hướng sa bàn (+x phải, +y lên)
        self.scan: LidarScan | None = None
        self.detections: list[tuple[float, float]] = []
        self.stale = False
        self.setMinimumSize(320, 320)

    def set_scan(self, scan: LidarScan | None, detections=None, stale: bool = False) -> None:
        self.scan = scan
        self.detections = list(detections or [])
        self.stale = stale
        self.update()

    def _to_widget(self, x: float, y: float) -> QPointF:
        """Cảm biến ở giữa, +x (trước) lên trên, +y (trái) sang trái."""
        side = min(self.width(), self.height())
        scale = (side / 2 - 12) / self.max_range
        if self.front_up:
            return QPointF(self.width() / 2 - y * scale, self.height() / 2 - x * scale)
        return QPointF(self.width() / 2 + x * scale, self.height() / 2 - y * scale)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#101821"))
        centre = self._to_widget(0.0, 0.0)
        side = min(self.width(), self.height())
        scale = (side / 2 - 12) / self.max_range
        p.setPen(QPen(QColor("#2a3642"), 1))
        for r in range(1, int(self.max_range) + 1):
            p.drawEllipse(centre, r * scale, r * scale)
        font = QFont("Segoe UI")
        font.setPixelSize(12)
        p.setFont(font)
        tip = self._to_widget(self.max_range * 0.35, 0.0)       # mũi tên "phía trước" để đối chiếu với sa bàn
        p.setPen(QPen(QColor("#4c6274"), 1, Qt.PenStyle.DashLine))
        p.drawLine(centre, tip)
        p.setPen(QColor("#7b8e9f"))
        p.drawText(QRectF(tip.x() + 6, tip.y() - 8, 60, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "trước")
        if self.scan is None:
            p.setPen(QColor("#7b8e9f"))
            p.drawText(QRectF(8, 6, self.width() - 16, 20), "Chưa có bản quét")
            p.end()
            return
        angles = np.asarray(self.scan.angles_rad)
        ok = valid_mask(self.scan)
        p.setPen(QPen(QColor("#1d2731"), 1))
        for a in angles[~ok]:
            p.drawLine(centre, self._to_widget(self.max_range * math.cos(a), self.max_range * math.sin(a)))
        p.setPen(QPen(QColor("#3a4a5a"), 1))
        for a in (angles[0], angles[-1]):
            p.drawLine(centre, self._to_widget(self.max_range * math.cos(a), self.max_range * math.sin(a)))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffd166" if not self.stale else "#8a6d3b"))
        for x, y in scan_points(self.scan):
            p.drawEllipse(self._to_widget(x, y), 2.0, 2.0)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#ff5c5c"), 2))
        for r, phi in self.detections:
            p.drawEllipse(self._to_widget(r * math.cos(phi), r * math.sin(phi)), 0.35 * scale + 3, 0.35 * scale + 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#8cf0d6"))
        p.drawEllipse(centre, 4, 4)
        p.setPen(QColor("#e4edf4" if not self.stale else "#ff8c5c"))
        status = "CŨ" if self.stale else "mới"
        p.drawText(QRectF(8, 6, self.width() - 16, 20),
                   f"{self.scan.stamp.source_id}  t={self.scan.stamp.t:.2f}s  phản hồi {int(ok.sum())}/{len(ok)}  ({status})")
        p.end()
