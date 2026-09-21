"""Đối tượng vẽ trên sa bàn: xe dạng ô tô, khung ô đỗ, vật cản, đường đi, vùng quét, gợi ý.

Tọa độ cảnh = tọa độ bản đồ (mét, y hướng lên); view lật trục y khi vẽ. Chữ dùng
cờ ItemIgnoresTransformations để không bị lật. Kéo để dời; lăn chuột trên đối
tượng để xoay 5° (Shift: 1°).
"""
from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPolygonF)
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsPathItem, QGraphicsSimpleTextItem
from shapely.ops import unary_union

from autopark.domain.types import Obstacle, ParkingSlot, Pose, VehicleConfig, wrap_angle
from autopark.geometry.footprint import body_polygon
from autopark.planning.trajectory import Trajectory

COLOR_EGO_BODY = QColor("#d8e4ed")
COLOR_EGO_WINDOW = QColor("#172c3d")
COLOR_EGO_OUTLINE = QColor("#edf8ff")
COLOR_START = QColor("#bfdfea")
COLOR_GOAL = QColor("#8cf0d6")
COLOR_PARKED_BODY = QColor("#526879")
COLOR_PARKED_WINDOW = QColor("#182937")
COLOR_BOX = QColor("#a88151")
COLOR_WALL = QColor("#485d6b")
COLOR_SLOT_OK = QColor("#8cf0d6")
COLOR_SLOT_BAD = QColor("#ff8e8a")
COLOR_FORWARD = QColor("#8cf0d6")
COLOR_REVERSE = QColor("#efb76b")
COLOR_SWEEP = QColor(140, 240, 214, 15)
COLOR_TEXT = QColor("#91a7b7")
COLOR_SHADOW = QColor(0, 0, 0, 100)

FONT_LABEL = QFont("Segoe UI", 9)


def cosmetic_pen(color: QColor, width: float = 2.0, style=Qt.PenStyle.SolidLine) -> QPen:
    pen = QPen(color, width, style)
    pen.setCosmetic(True)
    return pen


def attach_label(parent: QGraphicsItem, text: str, x: float, y: float, color: QColor = COLOR_TEXT) -> QGraphicsSimpleTextItem:
    label = QGraphicsSimpleTextItem(text, parent)
    label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
    label.setBrush(QBrush(color))
    label.setFont(FONT_LABEL)
    label.setPos(x, y)
    return label


def paint_car(painter: QPainter, rear: float, wheelbase: float, front: float, half: float,
              body: QColor, window: QColor, outline: QColor, steer: float = 0.0,
              dashed: bool = False, lights: int = 0, shadow: bool = True) -> None:
    """Vẽ xe trong hệ xe: gốc ở tâm trục sau, x tới đầu xe. Kích thước bằng mét.

    `lights`: 0 tắt, +1 bật đèn trước (đang tiến), -1 bật đèn lùi (đang lùi).
    """
    length = front - rear
    width = 2 * half
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    radius = min(0.035, width * 0.24)
    body_rect = QRectF(rear, -half * 0.92, length, width * 0.92)

    if shadow:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(COLOR_SHADOW))
        painter.drawRoundedRect(body_rect.adjusted(0.004, 0.006, 0.004, 0.006), radius, radius)

    # bánh xe, bánh trước xoay theo góc lái
    wheel_len, wheel_w = width * 0.34, width * 0.13
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor("#15171b")))
    for ax, angle in ((0.0, 0.0), (wheelbase, steer)):
        for side in (1, -1):
            painter.save()
            painter.translate(ax, side * (half - wheel_w * 0.35))
            painter.rotate(math.degrees(angle))
            painter.drawRoundedRect(QRectF(-wheel_len / 2, -wheel_w / 2, wheel_len, wheel_w),
                                    wheel_w * 0.35, wheel_w * 0.35)
            painter.restore()

    # thân xe: chuyển sắc nhẹ từ nóc xuống hông cho có khối
    grad = QLinearGradient(0.0, -half, 0.0, half)
    grad.setColorAt(0.0, body.lighter(112))
    grad.setColorAt(0.55, body)
    grad.setColorAt(1.0, body.darker(112))
    path = QPainterPath()
    # A tapered body silhouette, with a rounded nose and sculpted rear bumper.
    path.moveTo(rear + radius, -half * 0.92)
    path.lineTo(front - radius * 1.6, -half * 0.88)
    path.cubicTo(front, -half * 0.8, front, -half * 0.62, front, -half * 0.38)
    path.lineTo(front, half * 0.38)
    path.cubicTo(front, half * 0.62, front, half * 0.8, front - radius * 1.6, half * 0.88)
    path.lineTo(rear + radius, half * 0.92)
    path.quadTo(rear, half * 0.92, rear, half * 0.45)
    path.lineTo(rear, -half * 0.45)
    path.quadTo(rear, -half * 0.92, rear + radius, -half * 0.92)
    path.closeSubpath()
    painter.setPen(cosmetic_pen(outline, 1.4, Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine))
    painter.setBrush(QBrush(grad) if body.alpha() > 200 else QBrush(body))
    painter.drawPath(path)

    # khoang kính và nóc
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(window))
    painter.drawRoundedRect(QRectF(rear + length * 0.28, -half * 0.74, length * 0.46, width * 0.74),
                            radius * 0.8, radius * 0.8)
    painter.setBrush(QBrush(window.lighter(125)))
    painter.drawRoundedRect(QRectF(rear + length * 0.40, -half * 0.62, length * 0.20, width * 0.62),
                            radius * 0.6, radius * 0.6)
    painter.setBrush(QBrush(body.lighter(109)))
    painter.drawRoundedRect(QRectF(rear + length * 0.43, -half * 0.58, length * 0.15, width * 0.58),
                            radius * 0.35, radius * 0.35)
    painter.setPen(cosmetic_pen(QColor(210, 231, 241, 70), 0.7))
    painter.drawLine(QPointF(rear + length * 0.75, -half * 0.65), QPointF(front - length * 0.08, -half * 0.58))
    painter.drawLine(QPointF(rear + length * 0.75, half * 0.65), QPointF(front - length * 0.08, half * 0.58))

    # đèn: hai chấm ở đầu hoặc đuôi xe
    if lights:
        lamp = QColor("#fff2c2") if lights > 0 else QColor("#ff6b6b")
        glow = QColor(lamp)
        glow.setAlpha(70)
        lx = front - length * 0.03 if lights > 0 else rear + length * 0.03
        for side in (1, -1):
            c = QPointF(lx, side * half * 0.55)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(c, width * 0.16, width * 0.16)
            painter.setBrush(QBrush(lamp))
            painter.drawEllipse(c, width * 0.07, width * 0.07)
    else:
        painter.setPen(cosmetic_pen(outline, 1.6))
        painter.drawLine(QPointF(front - length * 0.03, -half * 0.5),
                         QPointF(front - length * 0.03, half * 0.5))


class RotationHandle(QGraphicsItem):
    """A screen-sized knob which rotates its parent in world coordinates."""
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.offset = 0.0
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Kéo nút tròn để xoay. Giữ Shift để bám góc 15°.")
        self.setZValue(30)
        self.hide()

    def boundingRect(self) -> QRectF:
        return QRectF(-9, -9, 18, 18)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(COLOR_GOAL, 1.5))
        painter.setBrush(QColor("#152a30"))
        painter.drawEllipse(QPointF(0, 0), 7, 7)
        painter.setBrush(COLOR_GOAL)
        painter.drawEllipse(QPointF(0, 0), 2, 2)

    def mousePressEvent(self, event) -> None:
        if not self.owner._editable:
            event.ignore()
            return
        delta = event.scenePos() - self.owner.scenePos()
        self.offset = math.degrees(math.atan2(delta.y(), delta.x())) - self.owner.rotation()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self.owner._editable:
            event.ignore()
            return
        delta = event.scenePos() - self.owner.scenePos()
        if math.hypot(delta.x(), delta.y()) < 1e-5:
            return
        angle = math.degrees(math.atan2(delta.y(), delta.x())) - self.offset
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            angle = round(angle / 15.0) * 15.0
        self.owner.setRotation(math.degrees(wrap_angle(math.radians(angle))))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        event.accept()


class _Draggable:
    """Phần dùng chung: kéo/xoay có callback; các lớp Qt kế thừa thêm."""

    ROTATE_STEP_DEG = 5.0
    ROTATE_FINE_DEG = 1.0

    def _init_drag(self, editable: bool, on_change: Callable | None) -> None:
        self._on_change = on_change
        self._updating = False
        self._editable = editable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self._rotation_handle = RotationHandle(self)
        self.set_editable(editable)

    def set_editable(self, on: bool) -> None:
        self._editable = on
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, on)
        self.setCursor(Qt.CursorShape.OpenHandCursor if on else Qt.CursorShape.ArrowCursor)
        self._sync_rotation_handle()

    def _sync_rotation_handle(self) -> None:
        self._rotation_handle.setPos(self.boundingRect().right() + 0.06, 0.0)
        self._rotation_handle.setVisible(self._editable and self.isSelected())
        self.update()

    def _paint_rotation_guide(self, painter: QPainter) -> None:
        if self._editable and self.isSelected():
            painter.setPen(cosmetic_pen(COLOR_GOAL, 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(self.boundingRect().right() - 0.03, 0), self._rotation_handle.pos())

    def _notify(self) -> None:
        if self._on_change is not None and not self._updating:
            self._on_change()

    def itemChange(self, change, value):
        if change in (QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged):
            self._notify()
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._sync_rotation_handle()
        return super().itemChange(change, value)  # type: ignore[misc]

    def wheelEvent(self, event) -> None:
        if not self._editable:
            event.ignore()
            return
        fine = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        step = self.ROTATE_FINE_DEG if fine else self.ROTATE_STEP_DEG
        direction = 1.0 if event.delta() > 0 else -1.0
        self.setSelected(True)
        self.setRotation(self.rotation() + direction * step)  # type: ignore[attr-defined]
        event.accept()


class CarItem(_Draggable, QGraphicsItem):
    """Xe dạng ô tô, gốc ở tâm trục sau. Dùng cho xe mô phỏng, mốc xuất phát và bóng đích."""

    def __init__(self, cfg: VehicleConfig, body: QColor, window: QColor, outline: QColor,
                 label: str = "", editable: bool = False, on_change: Callable | None = None,
                 dashed: bool = False, opacity: float = 1.0):
        QGraphicsItem.__init__(self)
        self.rear = -cfg.rear_overhang
        self.front = cfg.wheelbase + cfg.front_overhang
        self.wheelbase = cfg.wheelbase
        self.half = cfg.width / 2
        self.colors = (body, window, outline)
        self.dashed = dashed
        self.steer = 0.0
        self.lights = 0          # +1 đang tiến, -1 đang lùi, 0 đứng yên
        self.setOpacity(opacity)
        if label:
            self._label = attach_label(self, label, self.rear, self.half + 0.075, outline)
        self._init_drag(editable, on_change)

    def boundingRect(self) -> QRectF:
        pad = 0.03
        return QRectF(self.rear - pad, -self.half - pad, self.front - self.rear + 2 * pad, 2 * self.half + 2 * pad)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(QRectF(self.rear, -self.half, self.front - self.rear, 2 * self.half))
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        body, window, outline = self.colors
        paint_car(painter, self.rear, self.wheelbase, self.front, self.half, body, window,
                  outline, self.steer, self.dashed, self.lights, shadow=body.alpha() > 200)
        self._paint_rotation_guide(painter)

    def set_pose(self, pose: Pose, steer: float = 0.0, lights: int = 0) -> None:
        self._updating = True
        try:
            self.setPos(pose.x, pose.y)
            self.setRotation(math.degrees(pose.yaw))
            if abs(steer - self.steer) > 1e-4 or lights != self.lights:
                self.steer = steer
                self.lights = lights
                self.update()
        finally:
            self._updating = False

    def pose(self) -> Pose:
        return Pose(self.pos().x(), self.pos().y(), wrap_angle(math.radians(self.rotation())))


class SlotItem(_Draggable, QGraphicsItem):
    """Khung ô đỗ: ba cạnh liền, cạnh cửa ô nét đứt, chữ P. Gốc ở tâm ô, x hướng vào đáy ô."""

    def __init__(self, slot: ParkingSlot, editable: bool = True, on_change: Callable | None = None):
        QGraphicsItem.__init__(self)
        self.length = slot.length
        self.width = slot.width
        self.color = COLOR_SLOT_OK
        self._label = attach_label(self, "P", 0.0, 0.0, COLOR_SLOT_OK)
        self._label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.setZValue(3)
        self._init_drag(editable, on_change)
        self.set_slot(slot)

    def boundingRect(self) -> QRectF:
        pad = 0.03
        return QRectF(-self.length / 2 - pad, -self.width / 2 - pad, self.length + 2 * pad, self.width + 2 * pad)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(QRectF(-self.length / 2, -self.width / 2, self.length, self.width))
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        hl, hw = self.length / 2, self.width / 2
        fill = QColor(self.color)
        fill.setAlpha(10 if not self.isSelected() else 25)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(fill))
        painter.drawRect(QRectF(-hl, -hw, self.length, self.width))
        edge = QColor(self.color)
        edge.setAlpha(140)
        pen = cosmetic_pen(edge, 1.2)
        painter.setPen(pen)
        # ba cạnh liền: hai cạnh dài và đáy ô (x = +hl)
        painter.drawLine(QPointF(-hl, -hw), QPointF(hl, -hw))
        painter.drawLine(QPointF(-hl, hw), QPointF(hl, hw))
        painter.drawLine(QPointF(hl, -hw), QPointF(hl, hw))
        # cửa ô nét đứt, kèm hai chevron chỉ chiều đi vào ô
        painter.setPen(cosmetic_pen(self.color, 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(-hl, -hw), QPointF(-hl, hw))
        painter.setPen(cosmetic_pen(self.color, 2.0))
        chev = min(0.035, self.width * 0.18)
        for k, alpha in ((0.0, 200), (1.0, 90)):
            col = QColor(self.color)
            col.setAlpha(alpha)
            painter.setPen(cosmetic_pen(col, 2.0))
            bx = -hl + chev * (0.6 + 1.4 * k)
            painter.drawLine(QPointF(bx - chev * 0.7, hw * 0.42), QPointF(bx, 0.0))
            painter.drawLine(QPointF(bx - chev * 0.7, -hw * 0.42), QPointF(bx, 0.0))
        # góc đánh dấu
        painter.setPen(cosmetic_pen(self.color, 3.0))
        tick = min(0.04, self.width * 0.15)
        for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            painter.drawLine(QPointF(sx * hl, sy * hw), QPointF(sx * hl - sx * tick, sy * hw))
            painter.drawLine(QPointF(sx * hl, sy * hw), QPointF(sx * hl, sy * hw - sy * tick))
        self._paint_rotation_guide(painter)

    def set_valid(self, ok: bool) -> None:
        self.color = COLOR_SLOT_OK if ok else COLOR_SLOT_BAD
        self._label.setBrush(QBrush(self.color))
        self.update()

    def set_slot(self, slot: ParkingSlot) -> None:
        self._updating = True
        try:
            self.prepareGeometryChange()
            self.length, self.width = slot.length, slot.width
            self.setPos(slot.cx, slot.cy)
            self.setRotation(math.degrees(slot.yaw))
            self._label.setPos(-0.03, 0.03)
            self._sync_rotation_handle()
            self.update()
        finally:
            self._updating = False

    def slot(self) -> ParkingSlot:
        return ParkingSlot(self.pos().x(), self.pos().y(), wrap_angle(math.radians(self.rotation())), self.length, self.width)


class ObstacleItem(_Draggable, QGraphicsItem):
    """Vật cản: xe đỗ (vẽ dạng ô tô), hộp hoặc tường. Gốc ở tâm, x theo chiều dài."""

    def __init__(self, obstacle: Obstacle, editable: bool = True, on_change: Callable[[str], None] | None = None):
        QGraphicsItem.__init__(self)
        self.obstacle_id = obstacle.id
        self.kind = obstacle.kind
        self.w, self.h = obstacle.width, obstacle.height
        self.setZValue(2)
        self._label = attach_label(self, obstacle.id, -obstacle.width / 2, obstacle.height / 2 + 0.01, COLOR_TEXT)
        self._label.hide()
        self._init_drag(editable, None)
        self._on_change_id = on_change
        self.set_obstacle(obstacle)

    def _notify(self) -> None:
        if self._on_change_id is not None and not self._updating:
            self._on_change_id(self.obstacle_id)

    def hoverEnterEvent(self, event) -> None:
        self._label.show()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._label.setVisible(self.isSelected())
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._label.setVisible(bool(value))
        return super().itemChange(change, value)

    def boundingRect(self) -> QRectF:
        pad = 0.03
        return QRectF(-self.w / 2 - pad, -self.h / 2 - pad, self.w + 2 * pad, self.h + 2 * pad)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(QRectF(-self.w / 2, -self.h / 2, self.w, self.h))
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.kind == "car":
            rear_len, front_len = self.w * 0.22, self.w * 0.18
            wheelbase = self.w - rear_len - front_len
            painter.save()
            painter.translate(-self.w / 2 + rear_len, 0.0)
            paint_car(painter, -rear_len, wheelbase, wheelbase + front_len, self.h / 2,
                      COLOR_PARKED_BODY, COLOR_PARKED_WINDOW, COLOR_PARKED_BODY.lighter(130))
            painter.restore()
        elif self.kind in ("wall", "unknown"):
            painter.setPen(cosmetic_pen(COLOR_WALL.lighter(140), 1.5))
            painter.setBrush(QBrush(COLOR_WALL, Qt.BrushStyle.BDiagPattern))
            painter.drawRect(QRectF(-self.w / 2, -self.h / 2, self.w, self.h))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(-self.w / 2, -self.h / 2, self.w, self.h))
        else:
            painter.setPen(cosmetic_pen(COLOR_BOX.lighter(140), 1.5))
            painter.setBrush(QBrush(COLOR_BOX))
            r = min(0.02, self.h * 0.2, self.w * 0.2)
            painter.drawRoundedRect(QRectF(-self.w / 2, -self.h / 2, self.w, self.h), r, r)
        if self.isSelected():
            painter.setPen(cosmetic_pen(COLOR_GOAL, 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(-self.w / 2, -self.h / 2, self.w, self.h))
        self._paint_rotation_guide(painter)

    def set_obstacle(self, obstacle: Obstacle) -> None:
        self._updating = True
        try:
            self.prepareGeometryChange()
            self.obstacle_id = obstacle.id
            self.kind = obstacle.kind
            self.w, self.h = obstacle.width, obstacle.height
            self.setPos(obstacle.cx, obstacle.cy)
            self.setRotation(math.degrees(obstacle.yaw))
            self._label.setText(obstacle.id)
            self._label.setPos(-self.w / 2, self.h / 2 + 0.01)
            self._sync_rotation_handle()
            self.update()
        finally:
            self._updating = False

    def to_obstacle(self) -> Obstacle:
        return Obstacle(self.obstacle_id, self.pos().x(), self.pos().y(), self.w, self.h,
                        wrap_angle(math.radians(self.rotation())), self.kind)


class PathItem(QGraphicsItem):
    """Đường đi của tâm trục sau.

    Vẽ ba lớp cho dễ đọc: dải nền mờ rộng, nét sáng mảnh, và mũi tên chỉ chiều chạy
    rải đều dọc đường. Xanh khi tiến, vàng khi lùi; chấm tròn ở mỗi điểm đổi chiều.
    """

    ARROW_SPACING = 0.14        # m giữa hai mũi tên

    def __init__(self) -> None:
        super().__init__()
        self._forward = QPainterPath()
        self._reverse = QPainterPath()
        self._cusps: list[QPointF] = []
        self._arrows: list[tuple[QPointF, float, bool]] = []   # (vị trí, hướng, đang tiến)
        self._rect = QRectF()
        self.setZValue(6)

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for color, path in ((COLOR_FORWARD, self._forward), (COLOR_REVERSE, self._reverse)):
            if path.isEmpty():
                continue
            halo = QColor(color)
            halo.setAlpha(55)
            painter.setPen(cosmetic_pen(halo, 9.0))
            painter.drawPath(path)
            painter.setPen(cosmetic_pen(color, 2.4))
            painter.drawPath(path)

        for pos, yaw, forward in self._arrows:
            color = COLOR_FORWARD if forward else COLOR_REVERSE
            painter.save()
            painter.translate(pos)
            painter.rotate(math.degrees(yaw) + (0.0 if forward else 180.0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawPolygon(QPolygonF([QPointF(0.022, 0.0), QPointF(-0.014, 0.013),
                                           QPointF(-0.014, -0.013)]))
            painter.restore()

        for c in self._cusps:
            painter.setPen(cosmetic_pen(QColor("#ffffff"), 2.0))
            painter.setBrush(QBrush(COLOR_REVERSE))
            painter.drawEllipse(c, 0.019, 0.019)

    def set_trajectory(self, traj: Trajectory | None) -> None:
        self.prepareGeometryChange()
        self._forward = QPainterPath()
        self._reverse = QPainterPath()
        self._cusps = []
        self._arrows = []
        if traj is None or not traj.points:
            self._rect = QRectF()
            self.update()
            return
        xs, ys = [], []
        next_arrow = self.ARROW_SPACING * 0.5
        for si, (a, b) in enumerate(traj.segments):
            pts = traj.points[a:b + 1]
            forward = pts[0].direction > 0
            path = self._forward if forward else self._reverse
            path.moveTo(pts[0].pose.x, pts[0].pose.y)
            for p in pts[1:]:
                path.lineTo(p.pose.x, p.pose.y)
                if p.s >= next_arrow:
                    self._arrows.append((QPointF(p.pose.x, p.pose.y), p.pose.yaw, forward))
                    next_arrow = p.s + self.ARROW_SPACING
            for p in pts:
                xs.append(p.pose.x)
                ys.append(p.pose.y)
            if si > 0:
                self._cusps.append(QPointF(pts[0].pose.x, pts[0].pose.y))
        pad = 0.06
        self._rect = QRectF(min(xs) - pad, min(ys) - pad,
                            max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)
        self.update()


class SweepItem(QGraphicsPathItem):
    """Vùng thân xe quét dọc quỹ đạo (hợp các footprint lấy mẫu mỗi vài cm)."""

    def __init__(self) -> None:
        super().__init__()
        self.setPen(cosmetic_pen(QColor(52, 211, 153, 70), 1.0))
        self.setBrush(QBrush(COLOR_SWEEP))
        self.setZValue(1)

    def set_trajectory(self, traj: Trajectory | None, cfg: VehicleConfig, step: float = 0.015) -> None:
        """Lấy mẫu càng dày thì viền vùng quét càng mượt; 1,5 cm là đủ mà vẫn nhanh."""
        path = QPainterPath()
        if traj is not None and traj.points:
            polys = []
            last_s = -1.0
            for p in traj.points:
                if p.s - last_s >= step or p is traj.points[-1]:
                    polys.append(body_polygon(cfg, p.pose))
                    last_s = p.s
            union = unary_union(polys)
            geoms = getattr(union, "geoms", [union])
            for geom in geoms:
                ring = list(geom.exterior.coords)
                poly = QPolygonF([QPointF(x, y) for x, y in ring])
                path.addPolygon(poly)
                for interior in geom.interiors:
                    path.addPolygon(QPolygonF([QPointF(x, y) for x, y in interior.coords]))
        self.setPath(path)


class TrailItem(QGraphicsPathItem):
    """Vệt tâm trục sau đã đi trong lần chạy."""

    def __init__(self, color: QColor) -> None:
        super().__init__()
        self.setPen(cosmetic_pen(color, 2.0, Qt.PenStyle.DotLine))
        self.setZValue(7)
        self._path = QPainterPath()
        self._started = False

    def clear(self) -> None:
        self._path = QPainterPath()
        self._started = False
        self.setPath(self._path)

    def add(self, pose: Pose) -> None:
        if not self._started:
            self._path.moveTo(pose.x, pose.y)
            self._started = True
        else:
            self._path.lineTo(pose.x, pose.y)
        self.setPath(self._path)


class MarkerItem(QGraphicsEllipseItem):
    """Chấm nhỏ đánh dấu (điểm nhìn trước, v.v.)."""

    def __init__(self, color: QColor, radius: float = 0.015) -> None:
        super().__init__(-radius, -radius, 2 * radius, 2 * radius)
        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(QBrush(color))
        self.setZValue(8)
