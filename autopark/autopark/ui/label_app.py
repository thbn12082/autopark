"""Công cụ gán nhãn ảnh sa bàn: nhãn nháp từ AI, người tô sửa, rồi duyệt hoặc loại.

    python -m autopark.ui.label_app --project datasets/sa_ban_labels

Dự án tạo bằng `python -m autopark.perception.labels import runs/rig_snapshots --project datasets/sa_ban_labels`
(quy trình và quy tắc gán nhãn: docs/GAN_NHAN_SA_BAN.md). Không mở camera, không cần torch: xác suất AI đã được
chép vào dự án lúc nhập, "tô lại theo AI" chỉ so lại ngưỡng trên xác suất đó.

- Lớp tô: xanh = FREE, đỏ = BLOCKED, xám sọc = IGNORE. Độ đậm chỉnh bằng thanh trượt, O bật/tắt.
- Chuột: kéo trái = tô bằng cọ, hoặc thêm đỉnh đa giác (nhấp đúp hay Enter để tô kín, Esc để bỏ); kéo phải hoặc
  giữa = kéo khung nhìn; lăn = phóng to/thu nhỏ quanh con trỏ; Ctrl + lăn = cỡ cọ (một nấc bánh xe = một bước; bánh xe
  mịn/touchpad gửi nhiều sự kiện nhỏ thì cộng dồn cho đủ một nấc).
- Phím: 1 FREE, 2 BLOCKED, 3 IGNORE; B cọ, G đa giác; F vừa khung; H tô IGNORE vùng hỏng bộ dò định vị được; Ctrl+Z /
  Ctrl+Y hoàn tác / làm lại (bấm giữa lúc kéo cọ thì nét đóng lại, phần kéo còn lại không tô tới khi nhả chuột); Ctrl+S
  lưu; PgDown / PgUp ảnh sau / trước (theo đúng các dòng đang hiện trong danh sách); Ctrl+Enter đã duyệt.
- Sang ảnh khác hay đóng cửa sổ là TỰ LƯU, không hỏi; đa giác đang dở lúc đó: ≥ 3 đỉnh thì được tô kín, < 3 đỉnh thì
  bị bỏ — cả hai đều có báo. "Đã duyệt" lưu rồi chốt đúng nhãn đang thấy và sang ảnh kế; duyệt bị TỪ CHỐI khi còn đa
  giác chưa đóng (Enter tô kín / Esc bỏ trước). Sửa một ảnh đã duyệt thì nó về "nháp" và phải duyệt lại. Khung bị đánh
  dấu hỏng phải xác nhận riêng mới duyệt được, và vùng hỏng bộ dò định vị được phải là IGNORE (hỏi để tô hộ).
- Lưu hỏng (hết chỗ, file chỉ-đọc): ở lại ảnh đó; đóng cửa sổ thì hỏi trước, mặc định là ở lại để không mất nét đã tô.
- "Tô lại theo AI" đặt lại nháp theo ngưỡng đang chọn ở những pixel CHƯA tô tay; "Tô lại toàn bộ" xóa cả phần đã tô
  (hỏi trước). Cả hai hoàn tác được.
"""
from __future__ import annotations

import argparse
import html
import math
from pathlib import Path
import sys

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QKeySequence, QPainter, QPalette, QPen, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSlider,
                               QSplitter, QVBoxLayout, QWidget)

from autopark.perception.labels import (BLOCKED, DEFAULT_PROJECT, FREE, IGNORE, STATUS_NAMES, LabelEditor, LabelError,
                                        LabelProject)

CLASS_INDEX = np.zeros(256, np.uint8)
CLASS_INDEX[BLOCKED], CLASS_INDEX[IGNORE] = 1, 2
# RGBA theo chỉ số: FREE xanh, BLOCKED đỏ (cùng màu lớp tô của bàn thử), IGNORE hai tông xám xen kẽ thành sọc chéo
OVERLAY_RGBA = np.array([[60, 190, 60, 255], [230, 50, 50, 255], [150, 150, 150, 255], [60, 60, 60, 255]], np.uint8)
STRIPE = 6
# Màu chữ trạng thái trong danh sách, theo nền của bảng màu đang dùng (Windows 11 có thể sáng hoặc tối): chữ gần trắng
# trên nền trắng thì không đọc được (thấy 24/09 trên màn hình thật). "draft" = None: giữ màu chữ mặc định của bảng màu.
STATUS_COLORS_ON_DARK = {"draft": None, "reviewed": "#8cf0d6", "rejected": "#ff8e8a"}
STATUS_COLORS_ON_LIGHT = {"draft": None, "reviewed": "#0b7a3e", "rejected": "#b3261e"}


def status_color(status: str, list_widget) -> QColor | None:
    """Màu chữ cho một trạng thái, đọc được trên nền của `list_widget` (None = để màu mặc định)."""
    dark = list_widget.palette().color(QPalette.ColorRole.Base).lightness() < 128
    code = (STATUS_COLORS_ON_DARK if dark else STATUS_COLORS_ON_LIGHT)[status]
    return None if code is None else QColor(code)
STATUS_MARKS = {"draft": "·", "reviewed": "✓", "rejected": "✗"}
CLASS_BUTTONS = ((FREE, "1  FREE (sàn, giấy)"), (BLOCKED, "2  BLOCKED (vật cản)"), (IGNORE, "3  IGNORE (bỏ qua)"))


def stripes(height: int, width: int) -> np.ndarray:
    yy, xx = np.indices((height, width))
    return (((xx + yy) // STRIPE) % 2).astype(np.uint8)


def overlay_rgba(label: np.ndarray, stripe: np.ndarray | None = None) -> np.ndarray:
    """(H, W, 4) uint8 cho lớp tô: xanh FREE, đỏ BLOCKED, xám sọc IGNORE (độ đậm áp khi vẽ)."""
    index = CLASS_INDEX[label]
    if stripe is not None:
        index = index + ((label == IGNORE) & (stripe == 1)).astype(np.uint8)
    return OVERLAY_RGBA[index]


def to_qimage_rgb(image_bgr: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def to_qimage_rgba(rgba: np.ndarray) -> QImage:
    rgba = np.ascontiguousarray(rgba)
    h, w = rgba.shape[:2]
    return QImage(rgba.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()


class LabelCanvas(QWidget):
    """Ảnh + lớp nhãn, phóng/kéo, cọ và đa giác. Mọi thay đổi nhãn đi qua `LabelEditor` (hoàn tác được)."""

    changed = Signal()              # nhãn đổi sau một thao tác trọn vẹn (nhả chuột, đóng đa giác)
    radiusChanged = Signal(int)
    hover = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(480, 320)
        self.editor: LabelEditor | None = None
        self.image: QImage | None = None
        self.overlay: QImage | None = None
        self._stripe: np.ndarray | None = None
        self.scale, self.offset, self.user_view = 1.0, QPointF(0.0, 0.0), False
        self.tool, self.cls, self.radius = "brush", BLOCKED, 8
        self.opacity, self.show_overlay = 0.45, True
        self.polygon: list[tuple[int, int]] = []
        self._painting = False
        self._pan_from: QPointF | None = None
        self._mouse: QPointF | None = None
        self._radius_acc = 0             # angleDelta cộng dồn cho Ctrl + lăn (một nấc bánh xe = 120)

    # ---- nội dung
    def set_content(self, image_bgr: np.ndarray, editor: LabelEditor) -> None:
        self.image = to_qimage_rgb(image_bgr)
        self._stripe = stripes(*editor.shape)
        self.editor, self.polygon, self._painting, self._pan_from = editor, [], False, None
        self.hover.emit("")              # tọa độ/lớp của ảnh trước không còn đúng
        self.refresh_overlay()
        self.fit()

    def clear(self) -> None:
        self.editor = self.image = self.overlay = None
        self.update()

    def refresh_overlay(self) -> None:
        if self.editor is not None:
            self.overlay = to_qimage_rgba(overlay_rgba(self.editor.label, self._stripe))
        self.update()

    # ---- khung nhìn
    def fit(self) -> None:
        if self.image is None:
            return
        w, h = self.image.width(), self.image.height()
        self.scale = max(1e-3, min(self.width() / w, self.height() / h))
        self.offset = QPointF((self.width() - w * self.scale) / 2, (self.height() - h * self.scale) / 2)
        self.user_view = False
        self.update()

    def zoom_at(self, pos: QPointF, factor: float) -> None:
        if self.image is None:
            return
        x, y = self.to_image(pos)
        self.scale = min(40.0, max(0.05, self.scale * factor))
        self.offset = QPointF(pos.x() - x * self.scale, pos.y() - y * self.scale)
        self.user_view = True
        self.update()

    def to_image(self, pos: QPointF) -> tuple[float, float]:
        return (pos.x() - self.offset.x()) / self.scale, (pos.y() - self.offset.y()) / self.scale

    def to_widget(self, x: float, y: float) -> QPointF:
        """Tâm pixel (x, y) của ảnh trong tọa độ widget."""
        return QPointF(self.offset.x() + (x + 0.5) * self.scale, self.offset.y() + (y + 0.5) * self.scale)

    def to_pixel(self, pos: QPointF) -> tuple[int, int]:
        x, y = self.to_image(pos)
        return int(math.floor(x)), int(math.floor(y))

    def set_radius(self, radius: int) -> None:
        radius = int(min(150, max(1, radius)))
        if radius != self.radius:
            self.radius = radius
            self.radiusChanged.emit(radius)
            self.update()

    # ---- thao tác (giao diện và test gọi chung)
    def paint_stroke(self, points, cls: int | None = None, radius: int | None = None) -> bool:
        """Một nét cọ qua các pixel ảnh."""
        if self.editor is None:
            return False
        changed = self.editor.paint(points, self.cls if cls is None else cls, self.radius if radius is None else radius)
        self.refresh_overlay()
        if changed:
            self.changed.emit()
        return changed

    def close_polygon(self) -> bool:
        points, self.polygon = self.polygon, []
        changed = False
        if self.editor is not None and len(points) >= 3:
            changed = self.editor.fill_polygon(points, self.cls)
            self.refresh_overlay()
            if changed:
                self.changed.emit()
        self.update()
        return changed

    def cancel_polygon(self) -> None:
        self.polygon = []
        self.update()

    # ---- sự kiện
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.user_view:
            self.fit()

    def mousePressEvent(self, event):
        if self.editor is None:
            return
        pos = event.position()
        if event.button() == Qt.MouseButton.LeftButton:
            x, y = self.to_pixel(pos)
            if self.tool == "brush":
                self.editor.begin_stroke(self.cls, self.radius)
                self.editor.stroke_to(x, y)
                self._painting = True
                self.refresh_overlay()
            else:
                self.polygon.append((x, y))
                self.update()
        elif event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._pan_from = pos

    def mouseMoveEvent(self, event):
        pos = event.position()
        self._mouse = pos
        if self._painting and (self.editor is None or not self.editor.stroking):
            self._painting = False      # nét đã bị đóng giữa chừng (Ctrl+Z, Ctrl+Y, Tô lại): bỏ phần kéo còn lại tới khi nhả chuột
        if self._painting:
            self.editor.stroke_to(*self.to_pixel(pos))
            self.refresh_overlay()
        elif self._pan_from is not None:
            self.offset += pos - self._pan_from
            self._pan_from = pos
            self.user_view = True
            self.update()
        else:
            self.update()
        if self.editor is not None:
            x, y = self.to_pixel(pos)
            h, w = self.editor.shape
            if 0 <= x < w and 0 <= y < h:
                value = int(self.editor.label[y, x])
                name = {FREE: "FREE", BLOCKED: "BLOCKED", IGNORE: "IGNORE"}[value]
                self.hover.emit(f"x {x}, y {y}: {name}{' (đã tô tay)' if self.editor.edited[y, x] else ''}")

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._painting:
            self._painting = False
            if self.editor is not None and self.editor.end_stroke():
                self.changed.emit()
            self.refresh_overlay()
        elif event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._pan_from = None

    def mouseDoubleClickEvent(self, event):
        if self.tool == "polygon" and event.button() == Qt.MouseButton.LeftButton and self.editor is not None:
            # nhấp đúp thật: lần nhấn đầu đã thêm đỉnh này; QTest.mouseDClick (Qt 6) chỉ gửi sự kiện nhấp đúp
            point = self.to_pixel(event.position())
            if not self.polygon or self.polygon[-1] != point:
                self.polygon.append(point)
            self.close_polygon()
        else:
            # Qt không giao lần nhấn thứ hai của cú nhấp đúp (widget nhận Press, Release, DblClick, Release): coi nó là
            # một lần nhấn thường để nét cọ / kéo khung nhìn bắt đầu từ đó, như QWidget mặc định.
            self.mousePressEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if not delta:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # cỡ cọ theo ĐỘ LỚN delta, không theo số sự kiện: bánh xe mịn/touchpad gửi nhiều sự kiện nhỏ (đo: 24 sự kiện
            # 5 đơn vị từng đưa bán kính 8 -> 150 thay vì 8 -> 9); phần lẻ giữ lại, đổi chiều thì bỏ
            if self._radius_acc * delta < 0:
                self._radius_acc = 0
            self._radius_acc += delta
            while abs(self._radius_acc) >= 120:
                step = 1 if self._radius_acc > 0 else -1
                self.set_radius(self.radius + step * max(1, self.radius // 5))
                self._radius_acc -= step * 120
        else:
            self._radius_acc = 0
            self.zoom_at(event.position(), 1.25 ** (delta / 120.0))
        event.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.polygon and \
                not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.close_polygon()
        elif event.key() == Qt.Key.Key_Escape and self.polygon:
            self.cancel_polygon()
        else:
            super().keyPressEvent(event)

    def leaveEvent(self, event):
        self._mouse = None
        self.hover.emit("")
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101821"))
        if self.image is None:
            p.setPen(QColor("#9cafbe"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Chưa có ảnh")
            return
        p.save()
        p.translate(self.offset)
        p.scale(self.scale, self.scale)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.scale < 1.0)   # phóng to: thấy rõ từng pixel
        p.drawImage(0, 0, self.image)
        if self.show_overlay and self.overlay is not None:
            p.setOpacity(self.opacity)
            p.drawImage(0, 0, self.overlay)
            p.setOpacity(1.0)
        p.restore()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.polygon:
            p.setPen(QPen(QColor("#ffd24a"), 2))
            points = [self.to_widget(x, y) for x, y in self.polygon]
            for a, b in zip(points, points[1:]):
                p.drawLine(a, b)
            if self._mouse is not None:
                p.setPen(QPen(QColor("#ffd24a"), 1, Qt.PenStyle.DashLine))
                p.drawLine(points[-1], self._mouse)
            p.setBrush(QBrush(QColor("#ffd24a")))
            for point in points:
                p.drawEllipse(point, 3, 3)
        if self._mouse is not None and self.tool == "brush":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 200), 1))
            r = (self.radius + 0.5) * self.scale
            p.drawEllipse(self._mouse, r, r)


class LabelWindow(QMainWindow):
    def __init__(self, project: LabelProject, start_id: str | None = None):
        super().__init__()
        self.project = project
        self.current_id: str | None = None
        self.editor: LabelEditor | None = None
        self.last_message = ""
        self.confirm = self._ask                # test thay bằng hàm (tiêu đề, nội dung) -> bool để khỏi mở hộp thoại
        self.setWindowTitle(f"Gán nhãn sa bàn — {project.root}")

        self.filter_box = QComboBox()
        for text, status in (("Tất cả", None), ("Nháp", "draft"), ("Đã duyệt", "reviewed"), ("Loại", "rejected")):
            self.filter_box.addItem(text, status)
        self.filter_box.currentIndexChanged.connect(lambda _: self.refresh_list(self.current_id))
        self.item_list = QListWidget()
        self.item_list.currentItemChanged.connect(self.on_current_item)
        self.summary = QLabel()
        left = QVBoxLayout()
        left.addWidget(self.filter_box)
        left.addWidget(self.item_list, 1)
        left.addWidget(self.summary)
        left_box = QWidget()
        left_box.setLayout(left)

        self.canvas = LabelCanvas()
        self.canvas.changed.connect(self.on_edit)
        # tọa độ/lớp dưới con trỏ: nhãn cố định ở mép phải thanh trạng thái — không đè thông báo tạm của notify()
        self.hover_label = QLabel()
        self.statusBar().addPermanentWidget(self.hover_label)
        self.canvas.hover.connect(self.hover_label.setText)
        self._damage_region: np.ndarray | None = None       # vùng hỏng định vị được của ảnh đang mở (None: không có)

        self.class_group = QButtonGroup(self)
        self.class_group.setExclusive(True)
        class_row = QVBoxLayout()
        for value, text in CLASS_BUTTONS:
            button = QPushButton(text)
            button.setCheckable(True)
            self.class_group.addButton(button, value)
            class_row.addWidget(button)
        self.class_group.idClicked.connect(self.set_class)
        self.btn_brush, self.btn_polygon = QPushButton("Cọ (B)"), QPushButton("Đa giác (G)")
        self.tool_group = QButtonGroup(self)
        for button, tool in ((self.btn_brush, "brush"), (self.btn_polygon, "polygon")):
            button.setCheckable(True)
            self.tool_group.addButton(button)
            button.clicked.connect(lambda _=False, t=tool: self.set_tool(t))
        self.radius_slider = QSlider(Qt.Orientation.Horizontal)
        self.radius_slider.setRange(1, 150)
        self.radius_slider.valueChanged.connect(self.canvas.set_radius)
        self.canvas.radiusChanged.connect(self.on_radius)
        self.radius_label = QLabel()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.valueChanged.connect(self.set_opacity)
        self.chk_overlay = QCheckBox("Hiện lớp nhãn (O)")
        self.chk_overlay.toggled.connect(self.set_overlay)
        self.thr_slider = QSlider(Qt.Orientation.Horizontal)
        self.thr_slider.setRange(1, 99)                     # × 0,01
        self.thr_slider.valueChanged.connect(self.on_threshold)
        self.thr_label = QLabel()
        self.btn_regen = QPushButton("Tô lại theo AI (giữ chỗ đã tô)")
        self.btn_regen.clicked.connect(lambda: self.regenerate(keep_edits=True))
        self.btn_regen_all = QPushButton("Tô lại toàn bộ theo AI…")
        self.btn_regen_all.clicked.connect(lambda: self.regenerate(keep_edits=False))
        self.btn_damage = QPushButton("Tô IGNORE vùng hỏng (H)")
        self.btn_damage.clicked.connect(lambda: self.fill_damage())
        self.btn_undo, self.btn_redo = QPushButton("Hoàn tác"), QPushButton("Làm lại")
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo.clicked.connect(self.redo)
        self.btn_prev, self.btn_next = QPushButton("◀ Trước"), QPushButton("Sau ▶")
        self.btn_prev.clicked.connect(lambda: self.go_relative(-1))
        self.btn_next.clicked.connect(lambda: self.go_relative(1))
        self.btn_review = QPushButton("Đã duyệt ✓")
        self.btn_review.clicked.connect(self.mark_reviewed)
        self.btn_reject = QPushButton("Loại ✗")
        self.btn_reject.clicked.connect(self.mark_rejected)
        self.btn_draft = QPushButton("Về nháp")
        self.btn_draft.clicked.connect(self.mark_draft)
        self.btn_save = QPushButton("Lưu")
        self.btn_save.clicked.connect(lambda: self.save_current())
        self.btn_fit = QPushButton("Vừa khung (F)")
        self.btn_fit.clicked.connect(self.canvas.fit)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("ghi chú (vd. lý do loại, vùng không chắc)")
        self.info = QLabel()
        self.info.setTextFormat(Qt.TextFormat.RichText)
        self.info.setWordWrap(True)
        self.info.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        right = QVBoxLayout()
        right.addWidget(QLabel("Lớp"))
        right.addLayout(class_row)
        tools = QHBoxLayout()
        tools.addWidget(self.btn_brush)
        tools.addWidget(self.btn_polygon)
        right.addLayout(tools)
        right.addWidget(self.radius_label)
        right.addWidget(self.radius_slider)
        right.addWidget(self.chk_overlay)
        right.addWidget(QLabel("Độ đậm lớp nhãn"))
        right.addWidget(self.opacity_slider)
        right.addWidget(self.thr_label)
        right.addWidget(self.thr_slider)
        right.addWidget(self.btn_regen)
        right.addWidget(self.btn_regen_all)
        right.addWidget(self.btn_damage)
        grid = QGridLayout()
        for k, button in enumerate((self.btn_undo, self.btn_redo, self.btn_save, self.btn_fit,
                                    self.btn_prev, self.btn_next)):
            grid.addWidget(button, k // 2, k % 2)
        right.addLayout(grid)
        status_row = QHBoxLayout()
        for button in (self.btn_review, self.btn_reject, self.btn_draft):
            status_row.addWidget(button)
        right.addLayout(status_row)
        right.addWidget(self.notes)
        right.addWidget(self.info, 1)
        right_box = QWidget()
        right_box.setLayout(right)
        right_box.setMaximumWidth(380)

        splitter = QSplitter()
        splitter.addWidget(left_box)
        splitter.addWidget(self.canvas)
        splitter.addWidget(right_box)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 900, 360])
        self.setCentralWidget(splitter)
        self.resize(1600, 900)

        for keys, slot in ((("1",), lambda: self.set_class(FREE)), (("2",), lambda: self.set_class(BLOCKED)),
                           (("3",), lambda: self.set_class(IGNORE)), (("B",), lambda: self.set_tool("brush")),
                           (("G",), lambda: self.set_tool("polygon")), (("O",), self.chk_overlay.toggle),
                           (("F",), self.canvas.fit), (("H",), self.fill_damage),
                           (("Ctrl+Z",), self.undo), (("Ctrl+Y", "Ctrl+Shift+Z"), self.redo),
                           (("Ctrl+S",), self.save_current), (("PgDown",), lambda: self.go_relative(1)),
                           (("PgUp",), lambda: self.go_relative(-1)),
                           (("Ctrl+Return", "Ctrl+Enter"), self.mark_reviewed)):
            for key in keys:
                shortcut = QShortcut(QKeySequence(key), self)
                shortcut.activated.connect(slot)

        self.set_class(BLOCKED)
        self.set_tool("brush")
        self.radius_slider.setValue(self.canvas.radius)
        self.on_radius(self.canvas.radius)
        self.opacity_slider.setValue(int(round(self.canvas.opacity * 100)))
        self.chk_overlay.setChecked(True)
        self.thr_slider.setValue(50)
        self.refresh_list(start_id)
        if self.current_id is None and self.item_list.count():
            self.item_list.setCurrentRow(0)
        self.update_controls()

    # ---- hộp thoại (thay được khi test)
    def _ask(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(self, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def notify(self, text: str, error: bool = False) -> None:
        self.last_message = text
        self.statusBar().showMessage(text, 15000)
        if error and QApplication.platformName() != "offscreen":
            QMessageBox.warning(self, "Gán nhãn sa bàn", text)

    # ---- danh sách
    def visible_ids(self) -> list[str]:
        return self.project.ids(self.filter_box.currentData())

    def list_text(self, item_id: str) -> str:
        item = self.project.item(item_id)
        warn = "  ⚠ hỏng" if item["damage"]["damaged"] else ""
        return f"{STATUS_MARKS[item['status']]} {item_id}  [{STATUS_NAMES[item['status']]}]{warn}"

    def refresh_list(self, select_id: str | None = None) -> None:
        ids = self.visible_ids()
        self.item_list.blockSignals(True)
        self.item_list.clear()
        for item_id in ids:
            entry = QListWidgetItem(self.list_text(item_id))
            entry.setData(Qt.ItemDataRole.UserRole, item_id)
            color = status_color(self.project.item(item_id)["status"], self.item_list)
            if color is not None:
                entry.setForeground(color)
            self.item_list.addItem(entry)
        self.item_list.blockSignals(False)
        counts = {s: len(self.project.ids(s)) for s in STATUS_NAMES}
        self.summary.setText(f"{len(self.project.ids())} ảnh · nháp {counts['draft']} · duyệt {counts['reviewed']} · "
                             f"loại {counts['rejected']}")
        target = select_id if select_id in ids else (ids[0] if ids else None)
        if target is None:
            return
        row = ids.index(target)
        if target != self.current_id:
            self.item_list.setCurrentRow(row)           # phát tín hiệu -> open_item
        else:
            self.item_list.blockSignals(True)
            self.item_list.setCurrentRow(row)
            self.item_list.blockSignals(False)

    def on_current_item(self, current, _previous) -> None:
        if current is not None:
            item_id = current.data(Qt.ItemDataRole.UserRole)
            if item_id != self.current_id:
                self.open_item(item_id)

    def _settle_polygon(self, why: str) -> None:
        """Đa giác đang dở lúc rời ảnh / đóng cửa sổ: ≥ 3 đỉnh thì tô kín (một bước hoàn tác; lưu thành nháp), ít hơn
        thì bỏ. Luôn báo, không im lặng."""
        n = len(self.canvas.polygon)
        if not n or self.current_id is None:
            return
        if n >= 3:
            changed = self.canvas.close_polygon()
            self.notify(f"{self.current_id}: đa giác {n} đỉnh chưa đóng đã được tô kín trước khi {why}"
                        + ("" if changed else " (nhãn không đổi)"))
        else:
            self.canvas.cancel_polygon()
            self.notify(f"{self.current_id}: bỏ đa giác chưa đóng ({n} đỉnh, cần ít nhất 3) trước khi {why}")

    def open_item(self, item_id: str) -> None:
        self._settle_polygon("sang ảnh khác")
        if self.save_current() is None:                   # tự lưu, không hỏi; lưu hỏng thì ở lại, không mất nét đã tô
            self._select_row(self.current_id)
            return
        try:
            image = self.project.image(item_id)
            editor = self.project.editor(item_id)
            region = self.project.damage_region(item_id) if self.project.item(item_id)["damage"]["damaged"] else None
        except LabelError as error:
            self.notify(str(error), error=True)
            return
        self._damage_region = region if region is not None and region.any() else None
        self.current_id, self.editor = item_id, editor
        self.canvas.set_content(image, editor)
        self.notes.setText(self.project.item(item_id).get("notes", ""))
        self.thr_slider.blockSignals(True)
        self.thr_slider.setValue(int(round(editor.threshold * 100)))
        self.thr_slider.blockSignals(False)
        self.on_threshold(self.thr_slider.value())
        self.update_info()
        self.update_controls()

    def _row_of(self, item_id: str | None) -> int:
        """Dòng của ảnh trong CHÍNH danh sách đang hiện. Không tra qua `visible_ids()`: tự lưu có thể đưa một ảnh đã
        duyệt về nháp mà danh sách không dựng lại (đang ở trong tín hiệu đổi dòng), nên hai danh sách lệch nhau."""
        for row in range(self.item_list.count()):
            if self.item_list.item(row).data(Qt.ItemDataRole.UserRole) == item_id:
                return row
        return -1

    def _select_row(self, item_id: str | None) -> None:
        row = self._row_of(item_id)
        if row >= 0:
            self.item_list.blockSignals(True)
            self.item_list.setCurrentRow(row)
            self.item_list.blockSignals(False)

    def go_relative(self, step: int) -> None:
        # Đi theo dòng của danh sách đang hiện: ảnh vừa bị tự lưu đưa về "nháp" vẫn còn trong danh sách (đánh dấu nháp,
        # nhắc người duyệt lại) cho tới lần dựng lại kế tiếp.
        count = self.item_list.count()
        if not count:
            return
        row = self._row_of(self.current_id)
        index = row + step if row >= 0 else 0
        if 0 <= index < count:
            self.item_list.setCurrentRow(index)
        else:
            self.save_current()
            self.notify("Đã ở ảnh " + ("cuối" if step > 0 else "đầu") + " danh sách")

    # ---- lưu và trạng thái
    def save_current(self, action: str = "sửa nhãn") -> bool | None:
        """True = đã ghi, False = không có gì đổi, None = ghi HỎNG (đã báo; người gọi không được bỏ ảnh này đi)."""
        if self.current_id is None or self.editor is None:
            return False
        try:
            changed = self.project.save(self.current_id, self.editor.label, self.editor.edited,
                                        notes=self.notes.text(), draft_threshold=self.editor.threshold, action=action)
        except (LabelError, OSError) as error:
            self.notify(f"KHÔNG LƯU ĐƯỢC {self.current_id}: {error}", error=True)
            return None
        self.editor.dirty = False
        if changed:
            self._refresh_row(self.current_id)
            self.update_info()
        return changed

    def _refresh_row(self, item_id: str) -> None:
        for row in range(self.item_list.count()):
            entry = self.item_list.item(row)
            if entry.data(Qt.ItemDataRole.UserRole) == item_id:
                entry.setText(self.list_text(item_id))
                color = status_color(self.project.item(item_id)["status"], self.item_list)
                entry.setForeground(color if color is not None else self.item_list.palette().color(QPalette.ColorRole.Text))

    def _next_after_current(self) -> str | None:
        ids = self.visible_ids()
        if self.current_id not in ids:
            return ids[0] if ids else None
        index = ids.index(self.current_id)
        if index + 1 < len(ids):
            return ids[index + 1]
        return ids[index - 1] if index > 0 else self.current_id

    def _set_status(self, status: str, reason: str | None = None, advance: bool = True) -> bool:
        if self.current_id is None:
            return False
        if status == "reviewed" and self.canvas.polygon:    # duyệt chốt đúng nhãn đang thấy: không tô hộ, không bỏ
            self.notify(f"Chưa duyệt {self.current_id}: đa giác chưa đóng ({len(self.canvas.polygon)} đỉnh). "
                        "Enter để tô kín, Esc để bỏ, rồi duyệt lại.", error=True)
            return False
        if advance:                                          # sắp rời ảnh (Loại): như khi chuyển ảnh
            self._settle_polygon("đổi trạng thái")
        if self.save_current() is None:
            return False
        item = self.project.item(self.current_id)
        override = False
        if status == "reviewed" and item["damage"]["damaged"]:
            if not self.confirm("Khung bị đánh dấu hỏng",
                                "Khung này bị đánh dấu hỏng:\n" + "\n".join(item["damage"]["reasons"]) +
                                "\n\nChỉ duyệt nếu đã xem kỹ và tô IGNORE mọi vùng hỏng. Vẫn duyệt?"):
                self.notify("Không duyệt (khung hỏng)")
                return False
            if not self._damage_is_ignored():
                return False
            override = True
        target = self._next_after_current() if advance else self.current_id
        try:
            self.project.set_status(self.current_id, status, reason=reason, override_damage=override)
        except LabelError as error:
            self.notify(str(error), error=True)
            return False
        self.notify(f"{self.current_id}: {STATUS_NAMES[status]}")
        done = self.current_id
        self.refresh_list(target)
        if self.current_id == done:                      # không có ảnh kế, hay ảnh kế chính là ảnh này
            self.update_info()
            self.update_controls()
        return True

    def mark_reviewed(self) -> bool:
        return self._set_status("reviewed")

    def mark_rejected(self) -> bool:
        return self._set_status("rejected", reason=self.notes.text().strip() or "loại tay")

    def mark_draft(self) -> bool:
        return self._set_status("draft", reason="mở lại", advance=False)

    def _damage_is_ignored(self) -> bool:
        """Trước khi duyệt khung hỏng: vùng hỏng bộ dò định vị được đã là IGNORE chưa; chưa thì hỏi để tô hộ rồi lưu.
        (Bất biến thật nằm ở `LabelProject.set_status`/`export`; đây chỉ giúp người tô.)"""
        region = self._damage_region
        if region is None or self.editor is None:
            return True
        left = int((self.editor.label[region] != IGNORE).sum())
        if not left:
            return True
        damage = self.project.item(self.current_id)["damage"]
        if not self.confirm("Vùng hỏng chưa là IGNORE",
                            f"{left} pixel trong vùng hỏng bộ dò định vị được ({damage.get('truncated_rows', 0)} dòng "
                            f"đáy, {damage.get('torn_bands', 0)} dải xé) chưa là IGNORE.\n\nTô IGNORE vùng đó rồi duyệt? "
                            "(Hoàn tác được; vùng hỏng thật có thể rộng hơn phần bộ dò tìm thấy — xem lại ảnh.)"):
            self.notify(f"Không duyệt {self.current_id}: vùng hỏng chưa là IGNORE (nút 'Tô IGNORE vùng hỏng' hoặc H)")
            return False
        self.fill_damage()
        return self.save_current() is not None

    def fill_damage(self) -> int | None:
        """Tô IGNORE vùng hỏng bộ dò định vị được (một bước hoàn tác). Trả số pixel nhãn đổi, None nếu không làm gì."""
        if self.editor is None or self.current_id is None:
            return None
        if self._damage_region is None:
            damaged = self.project.item(self.current_id)["damage"]["damaged"]
            self.notify("Ảnh này không có vùng hỏng bộ dò định vị được" +
                        (" (lý do chỉ là bottom_repeat_share hay khung cũ: tự xét bằng mắt)" if damaged else ""))
            return None
        region = self._damage_region
        before = int((self.editor.label[region] != IGNORE).sum())
        self.canvas._painting = False                        # fill_mask đóng nét đang kéo (nếu có): canvas thôi tô
        self.editor.fill_mask(region, IGNORE)
        self.canvas.refresh_overlay()
        self.update_controls()
        self.notify(f"Tô IGNORE vùng hỏng: {before} pixel đổi ({int(region.sum())} pixel trong vùng)")
        return before

    # ---- công cụ
    def set_class(self, value: int) -> None:
        self.canvas.cls = int(value)
        button = self.class_group.button(int(value))
        if button is not None and not button.isChecked():
            button.setChecked(True)

    def set_tool(self, tool: str) -> None:
        if tool != "polygon" and self.canvas.polygon:
            n = len(self.canvas.polygon)
            self.canvas.cancel_polygon()
            self.notify(f"Bỏ đa giác chưa đóng ({n} đỉnh) khi đổi sang cọ")
        self.canvas.tool = tool
        (self.btn_brush if tool == "brush" else self.btn_polygon).setChecked(True)
        self.canvas.update()

    def on_radius(self, radius: int) -> None:
        self.radius_label.setText(f"Cỡ cọ: bán kính {radius} px (Ctrl + lăn chuột)")
        if self.radius_slider.value() != radius:
            self.radius_slider.blockSignals(True)
            self.radius_slider.setValue(radius)
            self.radius_slider.blockSignals(False)

    def set_opacity(self, value: int) -> None:
        self.canvas.opacity = value / 100.0
        self.canvas.update()

    def set_overlay(self, on: bool) -> None:
        self.canvas.show_overlay = bool(on)
        self.canvas.update()

    @property
    def threshold(self) -> float:
        return round(self.thr_slider.value() / 100.0, 2)

    def on_threshold(self, _value: int) -> None:
        text = f"Ngưỡng BLOCKED cho nháp AI: {self.threshold:.2f}".replace(".", ",")
        if self.editor is not None and abs(self.editor.threshold - self.threshold) > 1e-9:
            text += f" (nhãn đang theo {self.editor.threshold:.2f})".replace(".", ",")
        self.thr_label.setText(text)

    def regenerate(self, keep_edits: bool = True) -> int | None:
        if self.editor is None:
            return None
        if not keep_edits and not self.confirm("Tô lại toàn bộ", "Tô lại TOÀN BỘ ảnh theo AI, xóa mọi chỗ đã tô tay? "
                                                                 "(Hoàn tác được bằng Ctrl+Z.)"):
            return None
        try:
            changed = self.editor.regenerate(self.threshold, keep_edits=keep_edits)
        except LabelError as error:
            self.notify(str(error), error=True)
            return None
        self.canvas._painting = False                        # regenerate đã đóng nét đang kéo (nếu có): canvas thôi tô
        self.canvas.refresh_overlay()
        self.on_threshold(self.thr_slider.value())
        self.notify(f"Tô lại theo AI ở ngưỡng {self.threshold:.2f}: {changed} pixel đổi".replace(".", ","))
        self.update_controls()
        return changed

    def undo(self) -> None:
        self.canvas._painting = False                        # Ctrl+Z giữa nét kéo: editor đóng nét, canvas thôi tô
        if self.editor is not None and self.editor.undo():
            self.canvas.refresh_overlay()
            self.on_threshold(self.thr_slider.value())
        self.update_controls()

    def redo(self) -> None:
        self.canvas._painting = False
        if self.editor is not None and self.editor.redo():
            self.canvas.refresh_overlay()
            self.on_threshold(self.thr_slider.value())
        self.update_controls()

    def on_edit(self) -> None:
        self.update_controls()

    def update_controls(self) -> None:
        has = self.editor is not None
        self.btn_undo.setEnabled(has and bool(self.editor.undo_stack))
        self.btn_redo.setEnabled(has and bool(self.editor.redo_stack))
        has_prob = has and self.editor.prob is not None
        for button in (self.btn_regen, self.btn_regen_all):
            button.setEnabled(has_prob)
            button.setToolTip("" if has_prob else "Ảnh này không có xác suất AI (lúc chụp AI tắt, hoặc nhập với --no-draft)")
        for button in (self.btn_review, self.btn_reject, self.btn_draft, self.btn_save):
            button.setEnabled(has)
        self.btn_damage.setEnabled(has and self._damage_region is not None)

    def update_info(self) -> None:
        if self.current_id is None:
            self.info.setText("")
            return
        it = self.project.item(self.current_id)
        e = html.escape
        src, cam, draft, damage = it["source"], it["source"].get("camera") or {}, it["draft"], it["damage"]
        fmt = lambda x, nd=2: "—" if x is None else f"{x:.{nd}f}".replace(".", ",")
        origin = {"snapshot_prob": "xác suất lưu lúc chụp", "live_segmenter": "chạy mô hình lúc nhập",
                  "none": "không có (nháp toàn IGNORE)"}.get(draft["origin"], draft["origin"])
        lines = [f"<b>{e(it['id'])}</b> — <b>{e(STATUS_NAMES[it['status']])}</b>"]
        if it.get("status_reason"):
            lines.append(f"lý do: {e(str(it['status_reason']))}")
        lines.append(f"bộ ảnh {e(src['snapshot'])} · cổng {src['port']} · {it['image']['width']}×{it['image']['height']}"
                     f" · chụp {e(str(src.get('captured_local') or '—'))}")
        lines.append(f"nháp: {e(origin)} · mô hình {e(str(draft.get('model') or '—'))} · ngưỡng {fmt(draft['threshold'])}"
                     f" (ngưỡng hiển thị lúc chụp {fmt(src.get('capture_display_threshold'))})")
        if draft.get("note"):
            lines.append(f"<span style='color:#efb76b'>{e(draft['note'])}</span>")
        lines.append(f"khung lúc chụp: tuổi {fmt(cam.get('age_ms'), 0)} ms · cũ {e(str(cam.get('stale', '—')))} · "
                     f"bottom_repeat_share {fmt(damage.get('bottom_repeat_share'))} ({e(damage.get('bottom_repeat_share_from', ''))})")
        if damage["damaged"]:
            age, limit = damage.get("frame_age_ms"), damage.get("frame_age_limit_ms")
            too_old = damage.get("frame_too_old", age is not None and limit is not None and age > limit)
            broken = [r for r in damage["reasons"] if not r.startswith("khung cũ")]
            if broken:
                region = self._damage_region
                where = (f" Vùng bộ dò định vị được: {int(region.sum())} pixel (nút 'Tô IGNORE vùng hỏng')."
                         if region is not None else " Bộ dò không định vị được vùng nào: tự xét bằng mắt.")
                lines.append("<span style='color:#ff6b6b'><b>⚠ KHUNG HỎNG:</b> " + e("; ".join(broken)) +
                             ". Không dùng để huấn luyện trừ khi đã tô IGNORE mọi vùng hỏng." + e(where) + "</span>")
            if too_old:
                lines.append(f"<span style='color:#ff6b6b'><b>⚠ KHUNG CŨ (camera treo):</b> khung chụp "
                             f"{fmt(age / 1000.0, 1)} s TRƯỚC giờ bộ ảnh (age_ms), nên cảnh có thể đã khác và khung có "
                             "thể thuộc phiên chụp khác (được xếp phiên theo giờ khung). Tô IGNORE không sửa được việc "
                             "này: chỉ duyệt nếu chắc cảnh trong khung đúng là cảnh lúc đó.</span>")
        lines.append(f"đã tô tay {fmt(100 * float(it['label'].get('edited_fraction') or 0.0), 1)} % ảnh · sửa: "
                     f"{e(str(it.get('edited_by') or '—'))} {e(str(it.get('edited_at') or ''))}")
        lines.append(f"duyệt: {e(str(it.get('reviewed_by') or '—'))} {e(str(it.get('reviewed_at') or ''))}")
        lines.append("<span style='color:#9cafbe'>Nháp từ mô hình huấn luyện trên WoodScape, chưa từng được chấm trên "
                     "sa bàn; đã thấy báo động giả trên thảm. Sửa theo mắt, không theo nháp.</span>")
        self.info.setText("<br>".join(lines))

    def closeEvent(self, event):
        self._settle_polygon("đóng cửa sổ")
        if self.save_current() is None:                  # lưu hỏng: mặc định ở lại để không mất nét đã tô
            if not self.confirm("Không lưu được",
                                f"{self.last_message}\n\nĐóng và BỎ mọi thay đổi chưa lưu của {self.current_id}?\n"
                                "(Chọn Không để ở lại: sửa quyền ghi hoặc chỗ trống rồi Ctrl+S; hoặc Ctrl+Z hết nét.)"):
                event.ignore()
                return
        super().closeEvent(event)


def fit_to_screen(window: QWidget, available: QRect | None = None, size=(1600, 900), frame=(40, 80)) -> None:
    """Co cửa sổ cho vừa vùng làm việc của màn hình rồi đặt giữa. Qt chỉ căn giữa cửa sổ vừa màn hình, không co: laptop
    1920×1080 ở 125 % là 1536×864 logic (trừ thanh tác vụ ≈ 816), cửa sổ 1600×900 tràn mép phải và mép dưới, che nửa
    phải bảng điều khiển và thanh trạng thái. `frame`: phần chừa cho viền + thanh tiêu đề (chưa show thì Qt chưa biết)."""
    if available is None:
        screen = window.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
    w = max(1, min(int(size[0]), available.width() - frame[0]))
    h = max(1, min(int(size[1]), available.height() - frame[1]))
    window.resize(w, h)
    w, h = window.width(), window.height()                # có thể lớn hơn nếu bị kẹp bởi kích thước tối thiểu
    window.move(available.x() + max(0, (available.width() - w - frame[0]) // 2),
                available.y() + max(0, (available.height() - h - frame[1]) // 2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--who", default=None, help="tên người gán nhãn (mặc định: tài khoản máy)")
    parser.add_argument("--item", default=None, help="mở thẳng ảnh có mã này")
    args = parser.parse_args(argv)
    try:
        project = LabelProject(args.project, who=args.who)
    except LabelError as error:
        print(f"LỖI: {error}", file=sys.stderr)
        return 2
    if not project.ids():
        print(f"Dự án {project.root} chưa có ảnh nào. Nhập trước: python -m autopark.perception.labels import "
              f"runs/rig_snapshots --project {args.project}", file=sys.stderr)
        return 2
    app = QApplication.instance() or QApplication(sys.argv)
    window = LabelWindow(project, start_id=args.item)
    fit_to_screen(window)                             # sau __init__ (đặt 1600×900): co lại nếu màn hình nhỏ hơn
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
