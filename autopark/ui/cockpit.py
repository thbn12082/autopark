"""Canvas-first cockpit components. The scene stays beneath independent HUD layers."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class CockpitStage(QWidget):
    def __init__(self, view, arrange):
        super().__init__()
        self.view = view
        self.view.setParent(self)
        self.arrange = arrange

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.view.setGeometry(self.rect())
        self.view.lower()
        self.arrange(self.width(), self.height())


class StepRail(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.stage = 0
        self.setFixedSize(235, 126)

    def set_stage(self, stage):
        if self.stage != stage:
            self.stage = stage
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#34414d"), 1))
        p.drawLine(10, 14, 10, 100)
        labels = ("Chọn vị trí", "Xem trước chuyển động", "Thực hiện và dừng")
        font = QFont("Segoe UI")
        font.setPixelSize(13)
        p.setFont(font)
        for i, label in enumerate(labels):
            y = 15 + i * 42
            active, passed = i == self.stage, i < self.stage
            color = QColor("#8cf0d6" if active or passed else "#556575")
            p.setPen(QPen(color, 1.5))
            p.setBrush(QColor("#8cf0d6" if passed else "#101821"))
            p.drawEllipse(QPointF(10, y), 5, 5)
            if active:
                p.setBrush(color)
                p.drawEllipse(QPointF(10, y), 2, 2)
            p.setPen(QColor("#e4edf4" if active else "#7b8e9f"))
            p.drawText(QRectF(31, y - 10, 190, 22), f"0{i + 1}   {label}")


class DrivingReadout(QWidget):
    """A single live driving instrument rather than a row of dashboard tiles."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.speed = self.steer = 0.0
        self.clearance = None
        self.gear = "P"
        self.full_scale_mps = 0.3       # cung tốc độ đầy ở mức này; cửa sổ đặt bằng max_speed của xe (02/10/2026)
        self.setFixedSize(244, 240)

    def set_values(self, speed, steer, clearance):
        self.speed, self.steer, self.clearance = speed, steer, clearance
        self.gear = "D" if speed > 0.001 else ("R" if speed < -0.001 else "P")
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QRectF(2, 2, 164, 164)
        p.setPen(QPen(QColor("#263541"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(ring, 220 * 16, -260 * 16)
        p.setPen(QPen(QColor("#8cf0d6"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        full = self.full_scale_mps if self.full_scale_mps > 0 else 0.3
        p.drawArc(ring, 220 * 16, -int(max(0.014, min(abs(self.speed) / full, 1)) * 260 * 16))
        font = QFont("Segoe UI")
        font.setPixelSize(42)
        font.setWeight(QFont.Weight.Light)
        p.setFont(font)
        p.setPen(QColor("#f0f6fb"))
        p.drawText(QRectF(2, 46, 164, 58), Qt.AlignmentFlag.AlignCenter, f"{abs(self.speed):.2f}")
        font.setPixelSize(12)
        p.setFont(font)
        p.setPen(QColor("#8499aa"))
        p.drawText(QRectF(2, 100, 164, 24), Qt.AlignmentFlag.AlignCenter, "m / s")
        font.setPixelSize(16)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor("#8cf0d6"))
        p.drawText(QRectF(2, 138, 164, 25), Qt.AlignmentFlag.AlignCenter, self.gear)
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor("#91a4b3"))
        p.drawText(4, 201, "GÓC LÁI")
        p.drawText(124, 201, "KHOẢNG HỞ")
        font.setPixelSize(18)
        p.setFont(font)
        p.setPen(QColor("#e4edf4"))
        p.drawText(4, 229, f"{self.steer:+.0f}°")
        if self.clearance is not None:
            p.setPen(QColor("#edb566" if self.clearance < 0.05 else "#e4edf4"))
        p.drawText(124, 229, "—" if self.clearance is None else f"{self.clearance * 100:.1f} cm")
