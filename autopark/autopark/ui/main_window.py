"""Cockpit đỗ xe: mặt sàn toàn khung, hướng dẫn theo giai đoạn và thanh thao tác nổi.

Luồng chính của Qt chỉ nhận thao tác và vẽ bản chụp trạng thái; mô phỏng tiến theo
bước cố định trong `Session.advance()`; lập đường chạy trong luồng nền và được hỏi
kết quả mỗi nhịp vẽ (tài liệu mục 5.2, 6.2).

Các lớp HUD và đồng hồ lái nằm trong `ui/cockpit.py`; tham số kỹ thuật mở trong
ngăn sa bàn. Tương tác trên cảnh luôn được đổi về tọa độ thật trước khi cập nhật.
"""
from __future__ import annotations

import math
from dataclasses import replace
from html import escape
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient, QTransform
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from autopark.application.session import EDITABLE_STATES, Session, SessionError, SessionState
from autopark.domain.types import Bounds, Obstacle, ParkingMode, ParkingSlot, Pose, wrap_angle
from autopark.planning.hybrid_astar import PlanResult
from autopark.storage.scenario_store import load_scenario, load_vehicle_config, save_scenario
from autopark.ui import theme
from autopark.ui.items import (
    COLOR_EGO_BODY,
    COLOR_EGO_OUTLINE,
    COLOR_EGO_WINDOW,
    COLOR_GOAL,
    COLOR_START,
    CarItem,
    MarkerItem,
    ObstacleItem,
    PathItem,
    SlotItem,
    SweepItem,
    TrailItem,
    cosmetic_pen,
)
from autopark.ui.theme import Card, StatusPill, WrapLabel
from autopark.ui.cockpit import CockpitStage, DrivingReadout, StepRail

SCENE_MARGIN = 0.12
COLOR_BG = QColor("#0c131b")
COLOR_FLOOR = QColor("#1b2b37")
COLOR_FLOOR_EDGE = QColor("#111d28")
COLOR_GRID_MINOR = QColor("#203341")
COLOR_GRID_MAJOR = QColor("#2b4151")
COLOR_BOUNDS = QColor("#344b5a")

_STATE_TONE = {
    SessionState.COMPLETED: theme.OK,
    SessionState.READY: theme.OK,
    SessionState.FAULT: theme.DANGER,
    SessionState.STOPPED: theme.WARN,
    SessionState.RUNNING: theme.ACCENT,
    SessionState.PLANNING: theme.ACCENT,
    SessionState.PREPARING_PREVIEW: theme.ACCENT,
    SessionState.PREVIEW: theme.ACCENT,
    SessionState.STOPPING: theme.WARN,
    SessionState.MANUAL: theme.WARN,
}


class SandboxView(QGraphicsView):
    """View lật trục y để y bản đồ hướng lên; chuyển phím cho cửa sổ chính."""

    def __init__(self, scene: QGraphicsScene, key_handler: Callable[[object], bool]):
        super().__init__(scene)
        self._key_handler = key_handler
        self.safe_insets = (330, 83, 38, 143)
        self.place_slot = None
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setBackgroundBrush(COLOR_BG)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    def fit_scene(self) -> None:
        rect = self.scene().sceneRect()
        if rect.isEmpty():
            return
        vw = max(self.viewport().width(), 1)
        vh = max(self.viewport().height(), 1)
        left, top, right, bottom = self.safe_insets
        safe = QRectF(left, top, max(200, vw - left - right), max(200, vh - top - bottom))
        base = QTransform().scale(1, -1)
        box = base.mapRect(rect)
        scale = min(safe.width() / box.width(), safe.height() / box.height()) * 0.96
        transform = QTransform().scale(scale, -scale)
        self.setTransform(transform)
        self.setSceneRect(rect.adjusted(-10, -10, 10, 10))
        inverse, _ = transform.inverted()
        shift = safe.center() - QPointF(vw / 2, vh / 2)
        delta = inverse.map(shift) - inverse.map(QPointF(0, 0))
        self.centerOn(rect.center() - delta)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.place_slot is not None:
            # Vehicle/obstacle/slot gestures retain their own drag behavior.
            draggable = False
            for item in self.items(event.position().toPoint()):
                obj = item
                while obj is not None:
                    if isinstance(obj, (CarItem, SlotItem, ObstacleItem)):
                        draggable = True
                        break
                    obj = obj.parentItem()
            if not draggable and self.place_slot(self.mapToScene(event.position().toPoint())):
                event.accept()
                return
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_scene()

    def keyPressEvent(self, event) -> None:
        if self._key_handler(event):
            event.accept()
            return
        super().keyPressEvent(event)


def _spin(lo: float, hi: float, step: float, suffix: str, decimals: int = 1) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setSingleStep(step)
    sb.setSuffix(suffix)
    sb.setDecimals(decimals)
    sb.setKeyboardTracking(False)
    sb.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
    return sb


class PoseEditor(QWidget):
    """Ba ô nhập x (cm), y (cm), hướng (độ)."""

    def __init__(self, on_change: Callable[[Pose], None], parent: QWidget | None = None):
        super().__init__(parent)
        self._on_change = on_change
        self._syncing = False
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        self.x = _spin(-1000, 1000, 1.0, " cm")
        self.y = _spin(-1000, 1000, 1.0, " cm")
        self.yaw = _spin(-180, 180, 5.0, " °")
        form.addRow("x", self.x)
        form.addRow("y", self.y)
        form.addRow("hướng", self.yaw)
        for sb in (self.x, self.y, self.yaw):
            sb.valueChanged.connect(self._emit)

    def set_bounds(self, bounds: Bounds) -> None:
        self.x.setRange((bounds.xmin - 1) * 100, (bounds.xmax + 1) * 100)
        self.y.setRange((bounds.ymin - 1) * 100, (bounds.ymax + 1) * 100)

    def set_pose(self, pose: Pose) -> None:
        self._syncing = True
        try:
            self.x.setValue(pose.x * 100)
            self.y.setValue(pose.y * 100)
            self.yaw.setValue(math.degrees(pose.yaw))
        finally:
            self._syncing = False

    def pose(self) -> Pose:
        return Pose(self.x.value() / 100, self.y.value() / 100, math.radians(self.yaw.value()))

    def _emit(self) -> None:
        if not self._syncing:
            self._on_change(self.pose())


class MainWindow(QMainWindow):
    PREVIEW_DT = 0.02   # s mô phỏng giữa hai mẫu xem trước (nhịp điều khiển 50 Hz)

    def __init__(self, session: Session, scenario_path: Path | None = None):
        super().__init__()
        self.session = session
        self.scenario_path = scenario_path
        self._syncing = False
        self._selection_sync = False
        self._rebuilding_scene = False
        self._obstacle_items: dict[str, ObstacleItem] = {}
        self._preview_index = 0
        self._preview_accum = 0.0
        self._last_state = session.state
        self.setWindowTitle("Autopark — hỗ trợ đỗ xe")
        self.setStyleSheet(theme.STYLE)

        self.scene = QGraphicsScene(self)
        self.view = SandboxView(self.scene, self._handle_key)

        self._build_controls()
        self._build_inspector()
        self._build_cockpit()
        self._rebuild_scene()
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_tick)
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer.start()

        self.setMinimumSize(1100, 720)
        self.resize(1440, 900)
        self._refresh_all()

    def _build_controls(self) -> None:
        self.primary_action = QPushButton("Tìm đường đỗ")
        self.primary_action.setObjectName("primary")
        self.primary_action.setMinimumWidth(205)
        self.primary_action.clicked.connect(self._primary_dispatch)
        self.preview_action = QPushButton("Xem trước")
        self.preview_action.clicked.connect(self.preview)
        self.reset_action = QPushButton("Vị trí khác")
        self.reset_action.clicked.connect(self._return_to_editing)
        self.mode_selector = QPushButton()
        self.mode_selector.setObjectName("modeSelector")
        self.mode_selector.setMinimumWidth(155)
        self.mode_selector.setCheckable(True)
        self.mode_selector.toggled.connect(lambda on: self.mode_menu.setVisible(on))
        self.mode_menu = QFrame()
        self.mode_menu.setObjectName("modeMenu")
        menu_layout = QVBoxLayout(self.mode_menu)
        menu_layout.setContentsMargins(10, 10, 10, 10)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons = {}
        for mode in (ParkingMode.REVERSE_IN, ParkingMode.HEAD_IN, ParkingMode.PARALLEL):
            button = QPushButton(mode.label)
            button.setObjectName("modeOption")
            button.setIcon(theme.icon(mode.value))
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, m=mode: self._choose_mode(m))
            self.mode_group.addButton(button)
            self.mode_buttons[mode] = button
            menu_layout.addWidget(button)
        self.lbl_step = QLabel()
        self.lbl_step.setObjectName("stepLine")
        self.lbl_plan = WrapLabel()
        self.lbl_plan.setObjectName("planLine")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setValue(0)

    @staticmethod
    def _scroll_page(panel: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        return scroll

    # ------------------------------------------------------------------ bảng phải: sa bàn
    def _build_inspector(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 23, 20, 20)
        layout.setSpacing(26)

        self.box_file = Card("Kịch bản")
        self.lbl_file = WrapLabel("")
        self.btn_open = QPushButton("Mở…")
        self.btn_save = QPushButton("Lưu")
        self.btn_save_as = QPushButton("Lưu thành…")
        self.btn_open.clicked.connect(self._open_scenario)
        self.btn_save.clicked.connect(self._save_scenario)
        self.btn_save_as.clicked.connect(self._save_scenario_as)
        self.box_file.add(self.lbl_file)
        self.box_file.add_layout(theme.row(self.btn_open, self.btn_save, self.btn_save_as))
        layout.addWidget(self.box_file)

        self.box_slot = Card("Ô đỗ")
        form = QFormLayout()
        form.setSpacing(6)
        self.slot_x = _spin(-1000, 1000, 1.0, " cm")
        self.slot_y = _spin(-1000, 1000, 1.0, " cm")
        self.slot_yaw = _spin(-180, 180, 5.0, " °")
        self.slot_len = _spin(5, 500, 1.0, " cm")
        self.slot_w = _spin(5, 500, 1.0, " cm")
        for name, sb in (("x", self.slot_x), ("y", self.slot_y), ("hướng", self.slot_yaw),
                         ("dài", self.slot_len), ("rộng", self.slot_w)):
            form.addRow(name, sb)
            sb.valueChanged.connect(self._on_slot_editor_changed)
        self.box_slot.add_layout(form)
        self.lbl_goal_valid = QLabel("")
        self.box_slot.add(self.lbl_goal_valid)
        layout.addWidget(self.box_slot)

        self.box_start = Card("Xuất phát")
        self.start_editor = PoseEditor(self._on_start_editor_changed)
        self.lbl_start_valid = QLabel("")
        self.box_start.add(self.start_editor, self.lbl_start_valid)
        layout.addWidget(self.box_start)

        self.box_obstacles = Card("Vật cản")
        self.list_obstacles = QListWidget()
        self.list_obstacles.setMaximumHeight(140)
        self.list_obstacles.currentTextChanged.connect(self._on_obstacle_selected)
        self.combo_kind = QComboBox()
        for kind, label in (("car", "xe đỗ"), ("box", "hộp"), ("wall", "tường"), ("unknown", "chưa quan sát")):
            self.combo_kind.addItem(label, kind)
        self.btn_add_obs = QPushButton("Thêm")
        self.btn_del_obs = QPushButton("Xóa")
        self.btn_add_obs.clicked.connect(self._add_obstacle)
        self.btn_del_obs.clicked.connect(self._remove_selected_obstacle)
        form = QFormLayout()
        form.setSpacing(6)
        self.obs_w = _spin(1, 500, 1.0, " cm")
        self.obs_h = _spin(1, 500, 1.0, " cm")
        self.obs_x = _spin(-1000, 1000, 1.0, " cm")
        self.obs_y = _spin(-1000, 1000, 1.0, " cm")
        self.obs_yaw = _spin(-180, 180, 1.0, " °")
        self.obs_yaw.setWrapping(True)
        for editor in (self.obs_x, self.obs_y, self.obs_yaw, self.obs_w, self.obs_h):
            editor.valueChanged.connect(self._on_obstacle_editor_changed)
        form.addRow("vị trí x", self.obs_x)
        form.addRow("vị trí y", self.obs_y)
        form.addRow("góc xoay", self.obs_yaw)
        form.addRow("dài (x)", self.obs_w)
        form.addRow("rộng (y)", self.obs_h)
        obs_hint = WrapLabel("Chọn xe rồi kéo nút tròn để xoay tự do. Q / E xoay 5° (Shift: 1°). "
                             "Có thể nhập góc bất kỳ và kéo xe tới vị trí khác.")
        obs_hint.setObjectName("hint")
        self.box_obstacles.add(self.list_obstacles)
        self.box_obstacles.add_layout(theme.row(self.combo_kind, self.btn_add_obs, self.btn_del_obs))
        self.box_obstacles.add_layout(form)
        self.box_obstacles.add(obs_hint)
        layout.addWidget(self.box_obstacles)

        self.box_sim = Card("Mô phỏng")
        form = QFormLayout()
        form.setSpacing(6)
        self.spin_rt = _spin(0.1, 8.0, 0.1, " ×", 1)
        self.spin_rt.setValue(1.0)
        self.spin_rt.valueChanged.connect(lambda val: setattr(self.session, "realtime_factor", val))
        form.addRow("tốc độ chạy", self.spin_rt)
        self.btn_manual = QPushButton("Lái tay")
        self.btn_export = QPushButton("Xuất log CSV…")
        self.btn_manual.clicked.connect(self._start_manual)
        self.btn_export.clicked.connect(self._export_log)
        keys = WrapLabel("Lái tay: ↑/↓ tốc độ, ←/→ lái, Space phanh, 0 trả lái, R đặt lại, Esc thoát. "
                         "Khi đang đỗ: Space hoặc Esc để dừng.")
        keys.setObjectName("hint")
        self.box_sim.add_layout(form)
        self.combo_feedback = QComboBox()
        self.combo_feedback.addItems(["Phản hồi lý tưởng", "Trễ 40 ms + nhiễu 2 mm / 0,2°"])
        self.combo_feedback.currentIndexChanged.connect(self._set_feedback_profile)
        self.box_sim.add(self.combo_feedback)
        self.box_sim.add_layout(theme.row(self.btn_manual, self.btn_export))
        self.box_sim.add(keys)
        layout.addWidget(self.box_sim)

        card = Card("Xe")
        self.lbl_vehicle = WrapLabel("")
        self.lbl_vehicle.setObjectName("hint")
        card.add(self.lbl_vehicle)
        layout.addWidget(card)
        layout.addStretch(1)

        self.settings_page = self._scroll_page(panel)

    def _build_cockpit(self) -> None:
        self.stage = CockpitStage(self.view, self._arrange_cockpit)
        self.header = QWidget(self.stage)
        row = QHBoxLayout(self.header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(15)
        brand = QLabel("AUTO / PARK")
        brand.setObjectName("wordmark")
        row.addWidget(brand)
        version = QLabel("PARKING ASSIST")
        version.setObjectName("eyebrow")
        row.addWidget(version)
        row.addStretch(1)
        self.pill = StatusPill()
        self.lbl_state = self.pill
        row.addWidget(self.pill)
        self.manual_action = QPushButton("Lái tay")
        self.manual_action.setObjectName("hudButton")
        self.manual_action.clicked.connect(lambda: self.stop() if self.session.state == SessionState.MANUAL
                                           else self._start_manual())
        row.addWidget(self.manual_action)
        self.scatter_action = QPushButton("Xáo xe")
        self.scatter_action.setObjectName("hudButton")
        self.scatter_action.setToolTip("Đổi vị trí và góc của các xe đỗ, không để xe chồng lên nhau")
        self.scatter_action.clicked.connect(self._scatter_cars)
        row.addWidget(self.scatter_action)
        self.settings_action = QPushButton("Sa bàn  +")
        self.settings_action.setObjectName("hudButton")
        self.settings_action.setCheckable(True)
        self.settings_action.toggled.connect(self._toggle_drawer)
        row.addWidget(self.settings_action)

        self.hero = QWidget(self.stage)
        layout = QVBoxLayout(self.hero)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.phase_tag = QLabel("01 / CHỌN VỊ TRÍ")
        self.phase_tag.setObjectName("eyebrow")
        self.phase_title = QLabel("Chọn chỗ\nđỗ xe.")
        self.phase_title.setObjectName("heroTitle")
        self.phase_hint = WrapLabel()
        self.phase_hint.setObjectName("heroHint")
        layout.addWidget(self.phase_tag)
        layout.addWidget(self.phase_title)
        layout.addWidget(self.phase_hint)
        layout.addStretch(1)
        self.steps = StepRail(self.stage)
        self.instrument = DrivingReadout(self.stage)
        self.object_editor = QWidget(self.stage)
        object_layout = QVBoxLayout(self.object_editor)
        object_layout.setContentsMargins(0, 0, 0, 0)
        object_layout.setSpacing(10)
        self.lbl_selected_object = QLabel()
        self.lbl_selected_object.setObjectName("eyebrow")
        object_layout.addWidget(self.lbl_selected_object)
        self.quick_yaw = _spin(-180, 180, 1.0, " °")
        self.quick_yaw.setWrapping(True)
        self.quick_yaw.valueChanged.connect(self._on_quick_yaw_changed)
        self.rotate_left = QPushButton("−15°")
        self.rotate_right = QPushButton("+15°")
        self.rotate_left.setToolTip("Xoay ngược 15 độ")
        self.rotate_right.setToolTip("Xoay thêm 15 độ")
        self.rotate_left.clicked.connect(lambda: self._rotate_selected(-15))
        self.rotate_right.clicked.connect(lambda: self._rotate_selected(15))
        object_layout.addLayout(theme.row(self.rotate_left, self.quick_yaw, self.rotate_right, spacing=6))
        object_hint = WrapLabel("Kéo nút tròn để xoay tự do.<br>Q / E xoay 5° · Shift để chỉnh 1°.")
        object_hint.setObjectName("hint")
        object_layout.addWidget(object_hint)
        self.object_details = QPushButton("Vị trí & kích thước  →")
        self.object_details.clicked.connect(self._show_obstacle_details)
        object_layout.addWidget(self.object_details)
        self.object_editor.hide()
        self.lbl_report = WrapLabel(parent=self.stage)
        self.lbl_report.setObjectName("resultText")
        self.lbl_run = QLabel(self.stage)
        self.lbl_run.hide()

        self.scene_context = QWidget(self.stage)
        context_layout = QHBoxLayout(self.scene_context)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.setSpacing(14)
        self.lbl_scene_name = QLabel()
        self.lbl_scene_name.setObjectName("sectionTitle")
        self.lbl_scene_name.setMaximumWidth(140)
        self.lbl_scene_name.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_dimensions = QLabel()
        self.lbl_dimensions.setObjectName("hint")
        context_layout.addWidget(self.lbl_scene_name)
        context_layout.addWidget(self.lbl_dimensions)
        legend = QLabel("<span style='color:#8cf0d6'>— Tiến</span> &nbsp; "
                        "<span style='color:#efb76b'>— Lùi</span>")
        legend.setObjectName("hint")
        context_layout.addWidget(legend)
        self.map_tools = QWidget(self.stage)
        tools_layout = QVBoxLayout(self.map_tools)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_grid = QToolButton()
        self.btn_grid.setIcon(theme.icon("grid", theme.TEXT_DIM))
        self.btn_grid.setCheckable(True)
        self.btn_grid.setToolTip("Hiện lưới đo 10 cm")
        self.btn_grid.setAccessibleName("Hiện hoặc ẩn lưới")
        self.btn_grid.toggled.connect(self._toggle_grid)
        self.btn_fit = QToolButton()
        self.btn_fit.setIcon(theme.icon("focus", theme.TEXT_DIM))
        self.btn_fit.setToolTip("Căn lại toàn cảnh")
        self.btn_fit.setAccessibleName("Căn lại toàn cảnh")
        self.btn_fit.clicked.connect(self.view.fit_scene)
        tools_layout.addWidget(self.btn_grid)
        tools_layout.addWidget(self.btn_fit)
        self.btn_inject = QPushButton("Vật cản giả")
        self.btn_loss = QPushButton("Mất dữ liệu")
        self.btn_inject.setToolTip("Chèn hộp trên đường phía trước theo chiều xe đang chạy")
        self.btn_inject.clicked.connect(self._inject_test_obstacle)
        self.btn_loss.clicked.connect(self._inject_test_loss)
        tools_layout.addWidget(self.btn_inject)
        tools_layout.addWidget(self.btn_loss)
        self.btn_save_run = QPushButton("Lưu phiên…")
        self.btn_save_run.clicked.connect(self._export_log)
        tools_layout.addWidget(self.btn_save_run)

        self.action_dock = QFrame(self.stage)
        self.action_dock.setObjectName("actionDock")
        dock = QVBoxLayout(self.action_dock)
        dock.setContentsMargins(21, 15, 21, 12)
        dock.setSpacing(12)
        controls = QHBoxLayout()
        controls.setSpacing(16)
        controls.addWidget(self.mode_selector)
        info = QVBoxLayout()
        info.setSpacing(4)
        info.addWidget(self.lbl_step)
        info.addWidget(self.lbl_plan)
        controls.addLayout(info, 1)
        controls.addWidget(self.reset_action)
        controls.addWidget(self.preview_action)
        controls.addWidget(self.primary_action)
        dock.addLayout(controls)
        dock.addWidget(self.bar)
        self.mode_menu.setParent(self.stage)
        self.mode_menu.hide()

        self.drawer = QFrame(self.stage)
        self.drawer.setObjectName("settingsDrawer")
        drawer_layout = QVBoxLayout(self.drawer)
        drawer_layout.setContentsMargins(5, 14, 5, 10)
        drawer_header = QHBoxLayout()
        drawer_header.setContentsMargins(17, 0, 10, 4)
        label = QLabel("Thiết lập sa bàn")
        label.setObjectName("pageTitle")
        drawer_header.addWidget(label)
        drawer_header.addStretch(1)
        close = QPushButton("×")
        close.setObjectName("hudButton")
        close.setAccessibleName("Đóng thiết lập sa bàn")
        close.clicked.connect(lambda: self.settings_action.setChecked(False))
        drawer_header.addWidget(close)
        drawer_layout.addLayout(drawer_header)
        drawer_layout.addWidget(self.settings_page)
        self.drawer.hide()
        self.footnote = QLabel("MÔ PHỎNG 2D  ·  ESC / SPACE ĐỂ DỪNG", self.stage)
        self.footnote.setObjectName("note")
        self.footnote.setToolTip("Bộ bám đường dùng vị trí thật của xe mô phỏng; chưa có nhiễu cảm biến.")
        self.setCentralWidget(self.stage)
        self.view.place_slot = self._place_slot

    def _arrange_cockpit(self, width, height) -> None:
        if not hasattr(self, "drawer"):
            return
        left = 34
        compact = width < 1200
        hero_width = 255 if compact else 290
        self.header.setGeometry(left, 20, width - left * 2, 44)
        self.hero.setGeometry(left + 4, 126, hero_width, 228)
        self.phase_title.setStyleSheet("font-size: 39px;" if compact else "font-size: 46px;")
        self.steps.move(left + 5, 383)
        self.instrument.move(left + 5, 337 if compact else 376)
        self.object_editor.setGeometry(left + 5, 372, 252, 172)
        self.lbl_report.setGeometry(left + 5, 389, hero_width, 200)
        dock_width = min(1070, width - 70)
        dock_x = (width - dock_width) // 2
        dock_y = height - 130
        self.action_dock.setGeometry(dock_x, dock_y, dock_width, 96)
        self.mode_menu.setGeometry(dock_x + 6, dock_y - 190, 250, 181)
        self.drawer.setGeometry(width - 380, 84, 346, height - 237)
        self.scene_context.setGeometry(width - 480, 83, 380, 29)
        self.map_tools.setGeometry(width - 142, 173, 112, 230)
        self.footnote.setGeometry(left + 3, height - 25, width - 80, 20)
        self.view.safe_insets = (300 if compact else 330, 83,
                                 398 if self.drawer.isVisible() else 38, 143)
        self.view.fit_scene()

    def _toggle_drawer(self, visible: bool) -> None:
        if not hasattr(self, "drawer"):
            return
        self.drawer.setVisible(visible)
        if visible:
            self.drawer.raise_()
            self.mode_selector.setChecked(False)
        self.scene_context.setVisible(not visible)
        self.map_tools.setVisible(not visible)
        self._arrange_cockpit(self.stage.width(), self.stage.height())

    def _choose_mode(self, mode: ParkingMode) -> None:
        self._set_mode(mode)
        self.mode_selector.setChecked(False)

    def _primary_dispatch(self) -> None:
        st = self.session.state
        if st == SessionState.EDITING:
            self.plan()
        elif st in (SessionState.READY, SessionState.COMPLETED):
            self.run()
        elif st in (SessionState.PLANNING, SessionState.PREPARING_PREVIEW, SessionState.PREVIEW,
                    SessionState.RUNNING, SessionState.MANUAL):
            self.stop()
        elif st in (SessionState.STOPPED, SessionState.FAULT):
            self._return_to_editing()

    def _return_to_editing(self) -> None:
        self.reset()
        if self.session.state in EDITABLE_STATES:
            self._edit(lambda: self.session.set_start(self.session.scenario.start))

    def _place_slot(self, point) -> bool:
        if self.mode_selector.isChecked():
            self.mode_selector.setChecked(False)
            return True
        if self.session.state not in EDITABLE_STATES:
            return False
        if not self.session.scenario.bounds.contains_point(point.x(), point.y()):
            return False
        self.scene.clearSelection()
        slot = self.session.scenario.slot
        if slot is not None:
            slot = ParkingSlot(point.x(), point.y(), slot.yaw, slot.length, slot.width)
            self._edit(lambda: self.session.set_slot(slot))
            self.slot_item.set_slot(slot)
            self._sync_slot_editor()
        else:
            self._edit(lambda: self.session.set_goal_pose(
                Pose(point.x(), point.y(), self.session.scenario.goal.pose.yaw)))
        return True

    def _toggle_grid(self, visible: bool) -> None:
        for item in getattr(self, "_grid_items", []):
            item.setVisible(visible)

    # ------------------------------------------------------------------ cảnh
    def _rebuild_scene(self) -> None:
        self._rebuilding_scene = True
        self.scene.clear()
        self._obstacle_items = {}
        self._grid_items = []
        sc = self.session.scenario
        cfg = self.session.cfg
        b = sc.bounds
        editable = self.session.state in EDITABLE_STATES
        self.scene.setSceneRect(QRectF(b.xmin - SCENE_MARGIN, b.ymin - SCENE_MARGIN,
                                       b.width + 2 * SCENE_MARGIN, b.height + 2 * SCENE_MARGIN))

        # Nền sa bàn: sáng ở giữa, tối dần ra mép, cho đỡ phẳng
        floor = QGraphicsRectItem(b.xmin, b.ymin, b.width, b.height)
        grad = QRadialGradient(b.xmin + b.width / 2, b.ymin + b.height / 2, max(b.width, b.height) * 0.75)
        grad.setColorAt(0.0, COLOR_FLOOR)
        grad.setColorAt(1.0, COLOR_FLOOR_EDGE)
        floor.setBrush(grad)
        floor.setPen(Qt.PenStyle.NoPen)
        floor.setZValue(-3)
        self.scene.addItem(floor)

        minor, major = cosmetic_pen(COLOR_GRID_MINOR, 1.0), cosmetic_pen(COLOR_GRID_MAJOR, 1.0)
        i, x = 0, b.xmin
        while x <= b.xmax + 1e-9:
            line = QGraphicsLineItem(x, b.ymin, x, b.ymax)
            line.setPen(major if i % 5 == 0 else minor)
            line.setZValue(-2)
            self.scene.addItem(line)
            self._grid_items.append(line)
            x += 0.10
            i += 1
        j, y = 0, b.ymin
        while y <= b.ymax + 1e-9:
            line = QGraphicsLineItem(b.xmin, y, b.xmax, y)
            line.setPen(major if j % 5 == 0 else minor)
            line.setZValue(-2)
            self.scene.addItem(line)
            self._grid_items.append(line)
            y += 0.10
            j += 1
        frame = QGraphicsRectItem(b.xmin, b.ymin, b.width, b.height)
        frame.setPen(cosmetic_pen(COLOR_BOUNDS, 2.0))
        frame.setZValue(-1)
        self.scene.addItem(frame)

        self._toggle_grid(self.btn_grid.isChecked())

        self.sweep_item = SweepItem()
        self.scene.addItem(self.sweep_item)
        self.path_item = PathItem()
        self.scene.addItem(self.path_item)
        self.trail_item = TrailItem(QColor("#b7f6e6"))
        self.scene.addItem(self.trail_item)

        for obs in sc.obstacles:
            item = ObstacleItem(obs, editable=editable, on_change=self._on_obstacle_item_changed)
            self.scene.addItem(item)
            self._obstacle_items[obs.id] = item

        self.slot_item: SlotItem | None = None
        if sc.slot is not None:
            self.slot_item = SlotItem(sc.slot, editable=editable, on_change=self._on_slot_item_changed)
            self.scene.addItem(self.slot_item)

        self.goal_item = CarItem(cfg, QColor(140, 240, 214, 28), QColor(140, 240, 214, 55), COLOR_GOAL,
                                 label="", editable=sc.slot is None, on_change=self._on_goal_item_changed,
                                 dashed=True, opacity=0.95)
        self.goal_item.setZValue(4)
        self.goal_item.set_pose(sc.goal.pose)
        self.scene.addItem(self.goal_item)

        self.start_item = CarItem(cfg, COLOR_EGO_BODY, COLOR_EGO_WINDOW, COLOR_START,
                                  label="XE CỦA BẠN", editable=editable, on_change=self._on_start_item_changed)
        self.start_item.setZValue(5)
        self.start_item.set_pose(sc.start)
        self.scene.addItem(self.start_item)

        self.ghost_item = CarItem(cfg, COLOR_EGO_BODY, COLOR_EGO_WINDOW, COLOR_EGO_OUTLINE, opacity=0.95)
        self.ghost_item.setZValue(11)
        self.ghost_item.setVisible(False)
        self.scene.addItem(self.ghost_item)

        self.sim_item = CarItem(cfg, COLOR_EGO_BODY, COLOR_EGO_WINDOW, COLOR_EGO_OUTLINE)
        self.sim_item.setZValue(12)
        self.sim_item.setVisible(False)
        self.scene.addItem(self.sim_item)

        self.lookahead_item = MarkerItem(QColor("#ba7525"))
        self.lookahead_item.setVisible(False)
        self.scene.addItem(self.lookahead_item)

        self.start_editor.set_bounds(b)
        self.slot_x.setRange((b.xmin - 1) * 100, (b.xmax + 1) * 100)
        self.slot_y.setRange((b.ymin - 1) * 100, (b.ymax + 1) * 100)
        self.view.fit_scene()
        self._sync_path_items()
        self._rebuilding_scene = False
        self._on_scene_selection_changed()

    def _sync_path_items(self) -> None:
        traj = self.session.trajectory
        if traj is not None and not traj.valid:
            traj = None
        self.path_item.set_trajectory(traj)
        self.sweep_item.set_trajectory(traj, self.session.cfg)

    # ------------------------------------------------------------------ đồng bộ hiển thị
    def _refresh_all(self) -> None:
        sc = self.session.scenario
        cfg = self.session.cfg
        scene_title = {"bai_do_xe": "Bãi đỗ xe"}.get(sc.name, sc.name.replace("_", " "))
        self.lbl_scene_name.setText(scene_title)
        self.lbl_scene_name.setToolTip(sc.name)
        self.lbl_dimensions.setText(f"{sc.bounds.width:g} × {sc.bounds.height:g} m")
        if self.scenario_path is not None:
            self.lbl_file.setText(f"<b>{self.scenario_path.name}</b>")
            self.lbl_file.setToolTip(str(self.scenario_path))
        else:
            self.lbl_file.setText("(chưa lưu)")
        self.lbl_vehicle.setText(
            f"<b>{cfg.name}</b> — dài {cfg.length * 100:.0f} cm, rộng {cfg.width * 100:.0f} cm, "
            f"chiều dài cơ sở {cfg.wheelbase * 100:.0f} cm, lái ±{math.degrees(cfg.max_steer):.0f}°, "
            f"bán kính quay nhỏ nhất {cfg.min_turn_radius * 100:.0f} cm.<br>{cfg.notes}")
        self._syncing = True
        try:
            self.start_editor.set_pose(sc.start)
            if sc.slot is not None:
                self.slot_x.setValue(sc.slot.cx * 100)
                self.slot_y.setValue(sc.slot.cy * 100)
                self.slot_yaw.setValue(math.degrees(sc.slot.yaw))
                self.slot_len.setValue(sc.slot.length * 100)
                self.slot_w.setValue(sc.slot.width * 100)
            for mode, btn in self.mode_buttons.items():
                btn.setChecked(mode == sc.mode)
        finally:
            self._syncing = False
        self._refresh_obstacle_list()
        self._refresh_validity()
        self._refresh_mode_widgets()
        self._refresh_status()

    def _refresh_validity(self) -> None:
        start = self.session.start_check()
        goal = self.session.goal_check()
        for check, label in ((start, self.lbl_start_valid), (goal, self.lbl_goal_valid)):
            label.setText(check.describe())
            label.setStyleSheet(f"color: {theme.OK}; font-size: 9pt" if check.ok
                                else f"color: {theme.DANGER}; font-size: 9pt; font-weight: 600")
        if self.slot_item is not None:
            self.slot_item.set_valid(goal.ok)
        self.goal_item.set_pose(self.session.scenario.goal.pose)

    def _refresh_obstacle_list(self) -> None:
        current = self.list_obstacles.currentItem().text() if self.list_obstacles.currentItem() else None
        self._syncing = True
        try:
            self.list_obstacles.clear()
            for obs in self.session.scenario.obstacles:
                self.list_obstacles.addItem(obs.id)
            if current is not None:
                matches = self.list_obstacles.findItems(current, Qt.MatchFlag.MatchExactly)
                if matches:
                    self.list_obstacles.setCurrentItem(matches[0])
        finally:
            self._syncing = False
        self._on_obstacle_selected(self.list_obstacles.currentItem().text()
                                   if self.list_obstacles.currentItem() else "")

    def _sync_obstacle_editor(self) -> None:
        obs = self._selected_obstacle()
        editable = self.session.state in EDITABLE_STATES and obs is not None
        self._syncing = True
        try:
            for editor in (self.obs_x, self.obs_y, self.obs_yaw, self.obs_w, self.obs_h, self.quick_yaw):
                editor.setEnabled(editable)
            if obs is not None:
                self.obs_x.setValue(obs.cx * 100)
                self.obs_y.setValue(obs.cy * 100)
                self.obs_yaw.setValue(math.degrees(obs.yaw))
                self.quick_yaw.setValue(math.degrees(obs.yaw))
                self.obs_w.setValue(obs.width * 100)
                self.obs_h.setValue(obs.height * 100)
                self.lbl_selected_object.setText("ĐANG CHỌN  /  " + obs.id.upper())
        finally:
            self._syncing = False

    def _on_scene_selection_changed(self) -> None:
        if self._syncing or self._selection_sync or self._rebuilding_scene:
            return
        selected = next((item for item in self.scene.selectedItems() if isinstance(item, ObstacleItem)), None)
        self._selection_sync = True
        try:
            with QSignalBlocker(self.list_obstacles):
                matches = (self.list_obstacles.findItems(selected.obstacle_id, Qt.MatchFlag.MatchExactly)
                           if selected is not None else [])
                if matches:
                    self.list_obstacles.setCurrentItem(matches[0])
                else:
                    self.list_obstacles.setCurrentRow(-1)
        finally:
            self._selection_sync = False
        self._sync_obstacle_editor()
        self._refresh_status()

    def _refresh_mode_widgets(self) -> None:
        st = self.session.state
        self._sync_path_items()
        editable = st in EDITABLE_STATES
        for w in (self.box_file, self.box_slot, self.box_start, self.box_obstacles):
            w.setEnabled(editable)
        self.box_slot.setEnabled(editable and self.session.scenario.slot is not None)
        for mode, button in self.mode_buttons.items():
            button.setEnabled(editable)
            button.setChecked(mode == self.session.scenario.mode)
        self.mode_selector.setEnabled(editable)
        self.mode_selector.setText(self.session.scenario.mode.label + ("   ˅" if editable else ""))
        if not editable:
            self.mode_selector.setChecked(False)
            self.settings_action.setChecked(False)
        self.settings_action.setEnabled(editable)
        self.scatter_action.setEnabled(editable and any(o.kind == "car" for o in self.session.scenario.obstacles))
        self.manual_action.setEnabled(editable or st == SessionState.MANUAL)
        self.manual_action.setText("Thoát lái tay" if st == SessionState.MANUAL else "Lái tay")
        titles = {
            SessionState.EDITING: "Tìm đường đỗ   →", SessionState.PLANNING: "Hủy tính đường",
            SessionState.READY: "Bắt đầu đỗ   →", SessionState.PREPARING_PREVIEW: "Hủy xem trước",
            SessionState.PREVIEW: "Kết thúc xem trước", SessionState.RUNNING: "Dừng xe",
            SessionState.STOPPING: "Đang dừng…", SessionState.STOPPED: "Chọn lại vị trí",
            SessionState.COMPLETED: "Đỗ lại   →", SessionState.FAULT: "Chọn lại vị trí",
            SessionState.MANUAL: "Kết thúc lái tay",
        }
        self.primary_action.setText(titles[st])
        self.primary_action.setEnabled(st != SessionState.STOPPING)
        theme.set_role(self.primary_action, "danger" if st == SessionState.RUNNING else "primary")
        self.preview_action.setVisible(st == SessionState.READY)
        self.preview_action.setEnabled(st == SessionState.READY)
        self.reset_action.setVisible(st in (SessionState.READY, SessionState.COMPLETED))
        self.btn_manual.setEnabled(editable)
        self.combo_feedback.setEnabled(editable)
        self.btn_inject.setVisible(st == SessionState.RUNNING)
        self.btn_loss.setVisible(st == SessionState.RUNNING)
        self.btn_loss.setEnabled(st == SessionState.RUNNING and self.session.feedback is not None
                                 and not self.session.feedback.lost)
        self.btn_export.setEnabled(len(self.session.log) > 0)
        self.btn_save_run.setVisible(len(self.session.log) > 0)
        for item in self._obstacle_items.values():
            item.set_editable(editable)
        self.start_item.set_editable(editable)
        self.start_item.setVisible(editable or st in (SessionState.PLANNING, SessionState.PREPARING_PREVIEW))
        if self.slot_item is not None:
            self.slot_item.set_editable(editable)
        self.goal_item.set_editable(editable and self.session.scenario.slot is None)
        self.goal_item.setVisible(self.session.scenario.slot is None)
        driving = (SessionState.RUNNING, SessionState.STOPPING, SessionState.STOPPED,
                   SessionState.COMPLETED, SessionState.FAULT, SessionState.MANUAL)
        self.sim_item.setVisible(st in driving)
        self.ghost_item.setVisible(st == SessionState.PREVIEW)
        self.lookahead_item.setVisible(False)
        self._arrange_cockpit(self.stage.width(), self.stage.height())

    def _refresh_status(self) -> None:
        s, st = self.session, self.session.state
        self.pill.set(st.label, _STATE_TONE.get(st, theme.TEXT_DIM))
        copy = {
            SessionState.EDITING: ("01 / CHỌN VỊ TRÍ", "Chọn chỗ\nđỗ xe.", "Nhấp mặt sàn để đặt ô đỗ.\nChọn từng xe để kéo và xoay.", 0),
            SessionState.PLANNING: ("02 / LẬP LỘ TRÌNH", "Đang tìm\nđường đỗ.", "Bạn có thể hủy bất cứ lúc nào.", 1),
            SessionState.READY: ("02 / SẴN SÀNG", "Lộ trình\nđã sẵn sàng.", "Xem trước lộ trình hoặc bắt đầu\nđể xe tự đỗ.", 1),
            SessionState.PREPARING_PREVIEW: ("02 / XEM TRƯỚC", "Chuẩn bị\nchạy thử.", "Đang mô phỏng chuyển động\ntrước khi bắt đầu.", 1),
            SessionState.PREVIEW: ("02 / XEM TRƯỚC", "Xem cách\nxe di chuyển.", "Đây là lần chạy thử theo lộ trình.", 1),
            SessionState.RUNNING: ("03 / TỰ ĐỖ", "Xe đang\nvào vị trí.", "Nhấn Dừng xe hoặc Esc\nđể dừng bất cứ lúc nào.", 2),
            SessionState.STOPPING: ("03 / GIẢM TỐC", "Xe đang\ndừng lại.", "Đang phanh về trạng thái đứng yên.", 2),
            SessionState.STOPPED: ("ĐÃ DỪNG", "Bạn đang\nkiểm soát.", "Chọn lại vị trí khi sẵn sàng tiếp tục.", 2),
            SessionState.COMPLETED: ("HOÀN TẤT", "Đỗ xe\nhoàn tất.", "Lượt đỗ đã hoàn tất.", 3),
            SessionState.FAULT: ("CẦN ĐIỀU CHỈNH", "Xe đã\ndừng lại.", "Kiểm tra thông báo rồi chọn\nlại vị trí đỗ.", 2),
            SessionState.MANUAL: ("LÁI TAY", "Cầm lái\ntheo cách bạn.", "↑ ↓ Tăng / giảm tốc\n← → Đánh lái · Space phanh", 2),
        }
        tag, title, hint, stage = copy[st]
        self.phase_tag.setText(tag)
        self.phase_title.setText(title)
        self.phase_hint.setText(hint.replace("\n", "<br>"))
        if st == SessionState.EDITING:
            goal_check = s.goal_check()
            start_check = s.start_check()
            if not goal_check.ok or not start_check.ok:
                self.phase_tag.setText("VỊ TRÍ CHƯA HỢP LỆ")
                self.phase_hint.setText(escape(goal_check.describe() if not goal_check.ok
                                              else start_check.describe()))
        self.steps.set_stage(stage)
        live = st in (SessionState.RUNNING, SessionState.STOPPING, SessionState.PREVIEW,
                      SessionState.MANUAL, SessionState.STOPPED)
        preview_done = (st == SessionState.PREVIEW and s.preview is not None and bool(s.preview.states)
                        and self._preview_index >= len(s.preview.states) - 1)
        self.instrument.setVisible(live and not preview_done)
        self.steps.setVisible(not live and st not in (SessionState.COMPLETED, SessionState.FAULT))
        selected_object = self._selected_obstacle() if st in EDITABLE_STATES else None
        self.object_editor.setVisible(selected_object is not None)
        if selected_object is not None:
            self.steps.hide()
            self.phase_tag.setText("CHỈNH XE ĐỖ" if selected_object.kind == "car" else "CHỈNH VẬT CẢN")
            self.phase_title.setText("Xoay góc.\nĐặt vị trí.")
            self.phase_hint.setText("Kéo để di chuyển. Kéo nút tròn<br>hoặc nhập góc để xoay.")
        self.lbl_report.setVisible(st in (SessionState.COMPLETED, SessionState.FAULT) or preview_done)
        if preview_done:
            self.phase_title.setText("Xem trước\nhoàn tất.")
            self.phase_hint.setText("Kết quả của lượt mô phỏng thử.")
        pr = s.plan_result
        if st == SessionState.PLANNING:
            self.lbl_plan.setText("Đang tìm lộ trình phù hợp…")
        elif st == SessionState.PREPARING_PREVIEW:
            self.lbl_plan.setText("Đang chuẩn bị mô phỏng…")
        elif pr is None:
            self.lbl_plan.setText("Đặt ô đỗ, sau đó tìm đường.")
        elif pr.ok and s.trajectory is not None:
            self.lbl_plan.setText(f"{s.trajectory.length:.2f} m  ·  {s.trajectory.n_cusps} lần đổi chiều")
            self.lbl_plan.setToolTip(pr.message)
        else:
            self.lbl_plan.setText("Chưa có đường phù hợp. Hãy điều chỉnh vị trí.")
            self.lbl_plan.setToolTip(pr.message)
        self._refresh_progress()
        self._refresh_instrument()
        self._refresh_report()

    def _refresh_progress(self) -> None:
        s = self.session
        traj, out = s.trajectory, s.last_output
        if s.state in (SessionState.PLANNING, SessionState.PREPARING_PREVIEW):
            self.bar.setRange(0, 0)
            self.lbl_step.setText("Đang tìm đường…" if s.state == SessionState.PLANNING
                                  else "Đang chuẩn bị xem trước…")
            return
        self.bar.setRange(0, 1000)
        if s.state == SessionState.PREVIEW and s.preview is not None and s.preview.states:
            i = min(self._preview_index, len(s.preview.states) - 1)
            frac = i / max(1, len(s.preview.states) - 1)
            self.lbl_step.setText(f"Xem trước · {frac * 100:.0f}%")
            self.bar.setValue(int(frac * 1000))
            return
        if traj is None:
            self.lbl_step.setText("Chưa có lộ trình")
            self.bar.setValue(0)
            return
        if s.state == SessionState.COMPLETED:
            self.lbl_step.setText("Đã hoàn tất đỗ xe")
            self.bar.setValue(1000)
            return
        if out is None or s.state in EDITABLE_STATES:
            self.lbl_step.setText("Lộ trình đã sẵn sàng")
            self.bar.setValue(0)
            return
        pts = traj.points
        done = pts[min(out.index, len(pts) - 1)].s
        frac = done / traj.length if traj.length > 0 else 1.0
        way = "tiến" if pts[min(out.index, len(pts) - 1)].direction > 0 else "lùi"
        self.lbl_step.setText(f"Đoạn {out.segment + 1}/{len(traj.segments)} · {way} · {frac * 100:.0f}%")
        self.bar.setValue(int(min(1.0, frac) * 1000))

    def _refresh_instrument(self) -> None:
        s = self.session
        if s.state == SessionState.PREVIEW and s.preview is not None and s.preview.states:
            state = s.preview.states[min(self._preview_index, len(s.preview.states) - 1)]
            self.instrument.set_values(state.speed, math.degrees(state.steer), None)
        elif s.world is not None:
            state = s.world.state
            clearance = s.world.last_collision.min_clearance
            self.instrument.set_values(state.speed, math.degrees(state.steer),
                                       clearance if math.isfinite(clearance) else None)
        else:
            self.instrument.set_values(0.0, 0.0, None)

    def _refresh_report(self) -> None:
        s = self.session
        st = s.state
        report = s.report if st in (SessionState.COMPLETED, SessionState.FAULT, SessionState.STOPPED) else \
            (s.preview.report if st == SessionState.PREVIEW and s.preview is not None
             and self._preview_index >= len(s.preview.states) - 1 else None)
        if report is None:
            self.lbl_report.setText("")
            return
        tol_ok = (report.position_error <= s.scenario.goal.tolerance_xy
                  and abs(report.heading_error) <= s.scenario.goal.tolerance_yaw)
        inside = s.footprint_inside_slot(report.final_state.pose)
        color = theme.OK if report.completed and tol_ok else (theme.DANGER if report.collided else theme.WARN)
        lines = [f"<span style='color:{color}'>{report.describe()}</span>"]
        if report.completed:
            verdict = ("<b>ĐẠT dung sai</b>" if tol_ok else "<b>Ngoài dung sai</b>")
            if inside is not None:
                verdict += " · thân xe " + ("trong ô" if inside else "<b>ngoài ô</b>")
            lines.append(f"<span style='color:{color}'>{verdict}</span>")
        self.lbl_report.setText("<br>".join(lines))

    # ------------------------------------------------------------------ chỉnh sa bàn
    def _edit(self, action: Callable[[], None]) -> None:
        """Áp một thao tác chỉnh sa bàn rồi cập nhật hiển thị; đường cũ bị hủy theo Session."""
        if self._syncing:
            return
        try:
            action()
        except SessionError as exc:
            self.statusBar().showMessage(str(exc), 4000)
            return
        self._sync_path_items()
        self._refresh_validity()
        self._refresh_mode_widgets()
        self._refresh_status()

    def _on_start_item_changed(self) -> None:
        self._edit(lambda: self.session.set_start(self.start_item.pose()))
        self.start_editor.set_pose(self.session.scenario.start)

    def _on_start_editor_changed(self, pose: Pose) -> None:
        self._edit(lambda: self.session.set_start(pose))
        self.start_item.set_pose(self.session.scenario.start)

    def _on_goal_item_changed(self) -> None:
        self._edit(lambda: self.session.set_goal_pose(self.goal_item.pose()))

    def _on_slot_item_changed(self) -> None:
        if self.slot_item is None:
            return
        self._edit(lambda: self.session.set_slot(self.slot_item.slot()))
        self._sync_slot_editor()

    def _sync_slot_editor(self) -> None:
        slot = self.session.scenario.slot
        if slot is None:
            return
        self._syncing = True
        try:
            self.slot_x.setValue(slot.cx * 100)
            self.slot_y.setValue(slot.cy * 100)
            self.slot_yaw.setValue(math.degrees(slot.yaw))
            self.slot_len.setValue(slot.length * 100)
            self.slot_w.setValue(slot.width * 100)
        finally:
            self._syncing = False

    def _on_slot_editor_changed(self) -> None:
        if self._syncing or self.session.scenario.slot is None:
            return
        slot = ParkingSlot(self.slot_x.value() / 100, self.slot_y.value() / 100,
                           math.radians(self.slot_yaw.value()),
                           self.slot_len.value() / 100, self.slot_w.value() / 100)
        self._edit(lambda: self.session.set_slot(slot))
        if self.slot_item is not None:
            self.slot_item.set_slot(slot)

    def _set_mode(self, mode: ParkingMode) -> None:
        self._edit(lambda: self.session.set_mode(mode))

    def _on_obstacle_item_changed(self, obstacle_id: str) -> None:
        item = self._obstacle_items.get(obstacle_id)
        if item is None:
            return
        self._edit(lambda: self.session.update_obstacle(item.to_obstacle()))
        self._sync_obstacle_editor()

    def _selected_obstacle(self) -> Obstacle | None:
        current = self.list_obstacles.currentItem()
        if current is None:
            return None
        return self.session.scenario.obstacle_by_id(current.text())

    def _on_obstacle_selected(self, obstacle_id: str) -> None:
        if self._syncing or self._selection_sync or self._rebuilding_scene:
            return
        self._selection_sync = True
        try:
            for oid, item in self._obstacle_items.items():
                item.setSelected(oid == obstacle_id)
        finally:
            self._selection_sync = False
        self._sync_obstacle_editor()
        self._refresh_status()

    def _on_obstacle_editor_changed(self) -> None:
        obs = self._selected_obstacle()
        if obs is None or self._syncing:
            return
        new = Obstacle(obs.id, self.obs_x.value() / 100, self.obs_y.value() / 100,
                       self.obs_w.value() / 100, self.obs_h.value() / 100,
                       math.radians(self.obs_yaw.value()), obs.kind)
        self._edit(lambda: self.session.update_obstacle(new))
        self._obstacle_items[obs.id].set_obstacle(new)
        self._sync_obstacle_editor()

    def _on_quick_yaw_changed(self, value: float) -> None:
        if not self._syncing:
            self._set_selected_yaw(value)

    def _set_selected_yaw(self, degrees: float) -> None:
        obs = self._selected_obstacle()
        if obs is None or self.session.state not in EDITABLE_STATES:
            return
        updated = replace(obs, yaw=wrap_angle(math.radians(degrees)))
        self._edit(lambda: self.session.update_obstacle(updated))
        self._obstacle_items[obs.id].set_obstacle(updated)
        self._sync_obstacle_editor()

    def _rotate_selected(self, delta: float) -> None:
        obs = self._selected_obstacle()
        if obs is not None:
            self._set_selected_yaw(math.degrees(obs.yaw) + delta)

    def _show_obstacle_details(self) -> None:
        self.settings_action.setChecked(True)
        self.settings_page.ensureWidgetVisible(self.obs_yaw, 0, 80)

    def _scatter_cars(self) -> None:
        try:
            self.session.scatter_cars()
        except SessionError as exc:
            self.statusBar().showMessage(str(exc), 6000)
            return
        self._rebuild_scene()
        self._refresh_all()
        self.statusBar().showMessage("Đã xáo xe. Tìm đường để kiểm tra bố trí mới.", 6000)

    def _add_obstacle(self) -> None:
        kind = self.combo_kind.currentData()
        cfg = self.session.cfg
        cx, cy = self.session.scenario.bounds.center
        if kind == "car":
            obs = Obstacle(self.session.scenario.next_obstacle_id(), cx, cy, cfg.length, cfg.width, 0.0, "car")
        elif kind == "wall":
            obs = Obstacle(self.session.scenario.next_obstacle_id(), cx, cy, 0.6, 0.05, 0.0, "wall")
        else:
            obs = Obstacle(self.session.scenario.next_obstacle_id(), cx, cy, 0.2, 0.2, 0.0, kind)
        try:
            self.session.add_obstacle(obs)
        except SessionError as exc:
            QMessageBox.warning(self, "Không thêm được", str(exc))
            return
        item = ObstacleItem(obs, editable=True, on_change=self._on_obstacle_item_changed)
        self.scene.addItem(item)
        self._obstacle_items[obs.id] = item
        self._refresh_obstacle_list()
        matches = self.list_obstacles.findItems(obs.id, Qt.MatchFlag.MatchExactly)
        if matches:
            self.list_obstacles.setCurrentItem(matches[0])
        self._sync_path_items()
        self._refresh_validity()
        self._refresh_mode_widgets()
        self._refresh_status()

    def _remove_selected_obstacle(self) -> None:
        obs = self._selected_obstacle()
        if obs is None:
            selected = [i for i in self._obstacle_items.values() if i.isSelected()]
            if not selected:
                return
            obs = selected[0].to_obstacle()
        try:
            self.session.remove_obstacle(obs.id)
        except SessionError as exc:
            QMessageBox.warning(self, "Không xóa được", str(exc))
            return
        item = self._obstacle_items.pop(obs.id, None)
        if item is not None:
            self.scene.removeItem(item)
        self._refresh_obstacle_list()
        self._sync_path_items()
        self._refresh_validity()
        self._refresh_mode_widgets()
        self._refresh_status()

    # ------------------------------------------------------------------ tệp
    def _scenario_dir(self) -> Path:
        return self.scenario_path.parent if self.scenario_path is not None else Path.cwd()

    def _open_scenario(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Mở kịch bản", str(self._scenario_dir()), "JSON (*.json)")
        if not path:
            return
        try:
            scenario = load_scenario(path)
            cfg = load_vehicle_config(scenario.vehicle_config_path)
            self.session.replace_scenario(scenario, cfg)
        except Exception as exc:  # noqa: BLE001 - báo lỗi cho người dùng
            QMessageBox.critical(self, "Không mở được kịch bản", str(exc))
            return
        self.scenario_path = Path(path)
        self._rebuild_scene()
        self._refresh_all()
        self.statusBar().showMessage(f"Đã mở {path}", 4000)

    def _save_scenario(self) -> None:
        if self.scenario_path is None:
            self._save_scenario_as()
            return
        try:
            save_scenario(self.session.scenario, self.scenario_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Không lưu được", str(exc))
            return
        self.statusBar().showMessage(f"Đã lưu {self.scenario_path}", 4000)

    def _save_scenario_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Lưu kịch bản", str(self._scenario_dir()), "JSON (*.json)")
        if not path:
            return
        self.scenario_path = Path(path)
        self._save_scenario()
        self._refresh_all()

    def _export_log(self) -> None:
        default = str(self._scenario_dir().parent / "logs" / "lan_chay.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Xuất log", default, "CSV (*.csv)")
        if not path:
            return
        try:
            self.session.log.to_csv(path)
            if self.session.run_snapshot is not None and self.session.world is not None:
                from datetime import datetime
                from autopark.storage.run_store import export_run
                bundle = Path(path).with_suffix("").with_name(
                    Path(path).stem + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
                export_run(self.session, bundle)
        except OSError as exc:
            QMessageBox.critical(self, "Không ghi được", str(exc))
            return
        self.statusBar().showMessage(f"Đã ghi {len(self.session.log)} dòng vào {path}", 5000)

    def _set_feedback_profile(self, index: int) -> None:
        from autopark.simulation.feedback import FeedbackConfig
        self.session.feedback_config = (FeedbackConfig(delay_s=0.04, position_std_m=0.002,
                                                       yaw_std_rad=math.radians(0.2))
                                        if index else FeedbackConfig())

    def _inject_test_obstacle(self) -> None:
        if self.session.state != SessionState.RUNNING:
            return
        s = self.session
        state = s.world.state
        direction = 1 if state.speed >= 0 else -1
        # Chừa khoảng phanh; đây là vật giả trên đường, không phải cảm biến phát hiện.
        offset = (s.cfg.wheelbase + s.cfg.front_overhang + 0.30 if direction > 0
                  else -s.cfg.rear_overhang - 0.30)
        x, y = state.pose.to_world(offset, 0)
        obstacle = Obstacle(s.scenario.next_obstacle_id(), x, y, 0.12, 0.12)
        s.inject_obstacle(obstacle)
        item = ObstacleItem(obstacle, editable=False, on_change=self._on_obstacle_item_changed)
        self.scene.addItem(item)
        self._obstacle_items[obstacle.id] = item
        self._refresh_mode_widgets()
        self._refresh_status()

    def _inject_test_loss(self) -> None:
        if self.session.state == SessionState.RUNNING:
            self.session.inject_data_loss()
            self.btn_loss.setEnabled(False)

    # ------------------------------------------------------------------ đỗ xe
    def plan(self, sync: bool = False) -> PlanResult | None:
        try:
            if sync:
                result = self.session.plan_sync()
                self._after_plan(result)
                return result
            self.session.plan_async()
        except SessionError as exc:
            QMessageBox.warning(self, "Không tính được đường", str(exc))
            return None
        self._refresh_mode_widgets()
        self._refresh_status()
        return None

    def _after_plan(self, result: PlanResult | None) -> None:
        self._sync_path_items()
        self._refresh_mode_widgets()
        self._refresh_status()
        if result is not None and not result.ok:
            self.statusBar().showMessage(result.message, 6000)

    def preview(self) -> None:
        try:
            self.session.begin_preview_async()
        except SessionError as exc:
            QMessageBox.warning(self, "Không xem trước được", str(exc))
            return
        self._after_preview()

    def _after_preview(self) -> None:
        self._preview_index = 0
        self._preview_accum = 0.0
        pv = self.session.preview
        if self.session.state == SessionState.PREVIEW and pv is not None and pv.states:
            self.ghost_item.set_pose(pv.states[0].pose, pv.states[0].steer)
        if self.session.preview_error:
            self.statusBar().showMessage(self.session.preview_error, 8000)
        self._clock.restart()
        self._refresh_mode_widgets()
        self._refresh_status()

    def run(self) -> None:
        try:
            if self.session.state == SessionState.COMPLETED:
                self.session.reset()
            self.session.start_run()
        except SessionError as exc:
            QMessageBox.warning(self, "Không bắt đầu được", str(exc))
            return
        self.trail_item.clear()
        st = self.session.world.state
        self.sim_item.set_pose(st.pose, st.steer)
        self._clock.restart()
        self._refresh_mode_widgets()
        self._refresh_status()
        self.view.setFocus()

    def stop(self) -> None:
        st = self.session.state
        if st in (SessionState.PREVIEW, SessionState.PREPARING_PREVIEW):
            self.session.end_preview()
        elif st == SessionState.PLANNING:
            self.session.cancel_plan()
        elif st == SessionState.MANUAL:
            self.session.stop_manual()
        else:
            self.session.request_stop()
        self._refresh_mode_widgets()
        self._refresh_status()

    def reset(self) -> None:
        st = self.session.state
        if st == SessionState.MANUAL:
            self.session.stop_manual()
        elif st in (SessionState.PREVIEW, SessionState.PREPARING_PREVIEW):
            self.session.end_preview()
        else:
            self.session.reset()
        self.trail_item.clear()
        self.start_item.set_pose(self.session.scenario.start)
        self._refresh_all()

    def _start_manual(self) -> None:
        try:
            self.session.start_manual()
        except SessionError as exc:
            QMessageBox.warning(self, "Không lái tay được", str(exc))
            return
        self.trail_item.clear()
        st = self.session.world.state
        self.sim_item.set_pose(st.pose, st.steer)
        self._clock.restart()
        self._refresh_mode_widgets()
        self._refresh_status()
        self.view.setFocus()

    # ------------------------------------------------------------------ nhịp
    def _on_tick(self) -> None:
        real_dt = min(self._clock.restart() / 1000.0, 0.1)
        st = self.session.state
        if st == SessionState.PLANNING:
            result = self.session.poll_plan()
            if self.session.state != SessionState.PLANNING:
                self._after_plan(result)
        elif st == SessionState.PREPARING_PREVIEW:
            self.session.poll_preview()
            if self.session.state != SessionState.PREPARING_PREVIEW:
                self._after_preview()
        elif st == SessionState.PREVIEW:
            self._advance_preview(real_dt)
        elif self.session.simulating:
            self.advance_by(real_dt)
        if self.session.state != self._last_state:
            self._last_state = self.session.state
            self._refresh_mode_widgets()
            self._refresh_status()

    def _advance_preview(self, real_dt: float) -> None:
        pv = self.session.preview
        if pv is None or not pv.states:
            self.session.end_preview()
            return
        self._preview_accum += real_dt * self.session.realtime_factor
        while self._preview_accum >= self.PREVIEW_DT and self._preview_index < len(pv.states) - 1:
            self._preview_index += 1
            self._preview_accum -= self.PREVIEW_DT
        state = pv.states[self._preview_index]
        lights = 1 if state.speed > 1e-3 else (-1 if state.speed < -1e-3 else 0)
        self.ghost_item.set_pose(state.pose, state.steer, lights)
        self._refresh_status()

    def advance_by(self, real_dt: float) -> None:
        """Tiến mô phỏng một khoảng thời gian thực; tách riêng để test không cần timer."""
        results = self.session.advance(real_dt)
        if results:
            st = results[-1].state
            lights = 1 if st.speed > 1e-3 else (-1 if st.speed < -1e-3 else 0)
            self.sim_item.set_pose(st.pose, st.steer, lights)
            self.trail_item.add(st.pose)
            out = self.session.last_output
            if out is not None and out.lookahead is not None:
                self.lookahead_item.setPos(out.lookahead.x, out.lookahead.y)
        self._refresh_status()
        self.btn_export.setEnabled(len(self.session.log) > 0)

    def _handle_key(self, event) -> bool:
        key = event.key()
        K = Qt.Key
        st = self.session.state
        if key == K.Key_Escape:
            if self.mode_menu.isVisible():
                self.mode_selector.setChecked(False)
                return True
            if self.drawer.isVisible():
                self.settings_action.setChecked(False)
                return True
        if st == SessionState.MANUAL:
            if key == K.Key_Up:
                self.session.nudge_speed(+self.session.speed_step)
            elif key == K.Key_Down:
                self.session.nudge_speed(-self.session.speed_step)
            elif key == K.Key_Left:
                self.session.nudge_steer(+self.session.steer_step)
            elif key == K.Key_Right:
                self.session.nudge_steer(-self.session.steer_step)
            elif key == K.Key_Space:
                self.session.brake()
            elif key == K.Key_0:
                self.session.center_steer()
            elif key == K.Key_R:
                self.session.reset_manual()
                self.trail_item.clear()
            elif key == K.Key_Escape:
                self.stop()
            else:
                return False
            self._refresh_status()
            return True
        if st in (SessionState.RUNNING, SessionState.PREVIEW, SessionState.PLANNING,
                  SessionState.PREPARING_PREVIEW) and key in (K.Key_Space, K.Key_Escape):
            self.stop()
            return True
        if st in EDITABLE_STATES and key == K.Key_Delete:
            self._remove_selected_obstacle()
            return True
        if st in EDITABLE_STATES and key in (K.Key_Q, K.Key_E) and self._selected_obstacle() is not None:
            step = 1.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 5.0
            self._rotate_selected(-step if key == K.Key_Q else step)
            return True
        return False

    def keyPressEvent(self, event) -> None:
        if self._handle_key(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        self.session.close()
        super().closeEvent(event)
