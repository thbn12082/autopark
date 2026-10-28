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
import sys
from typing import Callable

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient, QTransform
from PySide6.QtWidgets import (
    QApplication,
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

from autopark.application.cusp_policy import SOURCE_ACCEPTANCE, SOURCE_CLI   # T12 theo kịch bản nghiệm thu
from autopark.application.session import EDITABLE_STATES, Session, SessionError, SessionState
from autopark.application.vehicle_link import (BoardFaultClear, BoardProbe, DriveMode, LinkParams,
                                               PlantHumanDriver, SimHumanDriver, VehicleLink, VehicleLinkError,
                                               probe_board)
from autopark.domain.types import Bounds, Obstacle, Pose, wrap_angle
from autopark.evaluation.sync_marks import DEFAULT_SYNC_DIR, SyncMarkLog, sync_file_path
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.maneuver import maneuver_bounds
from autopark.storage.scenario_store import load_scenario, load_vehicle_config, save_scenario
from autopark.storage.scenario_store import (CONFIGS_DIR, VehicleConfigError, VehicleConfigFile,  # ô "Cấu hình xe"
                                            list_vehicle_configs, load_vehicle_config_file, path_key)
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
    SweepItem,
    TrailItem,
    cosmetic_pen,
)
from autopark.ui.theme import Card, StatusPill, WrapLabel
from autopark.ui.cockpit import CockpitStage, DrivingReadout, StepRail
from autopark.ui.qemu_runner import BUSY_STATES as QEMU_BUSY_STATES, QemuBoardRunner, QemuRunnerState
from autopark.ui.sync_flash import SyncFlash, SyncMarker

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

# Nhánh chạy chọn trong giao diện (24/09/2026): hai nhánh VehicleIO đều nối với bo MÔ PHỎNG (SimVehicleIO +
# FirmwareModel) và tư thế lấy từ mô phỏng. (Cập nhật 24/09/2026: thẻ "Bo điều khiển" chọn được cổng serial tới bo
# thật; với bo thật START luôn bị từ chối vì chưa có nguồn tư thế thật, xem `VehicleLink.serial_port`.)
DRIVE_MODE_CHOICES = (
    (DriveMode.SIM, "Mô phỏng giai đoạn 0 (mặc định)",
     "Xe ảo chạy thẳng theo lệnh, phản hồi giả như giai đoạn 0."),
    (DriveMode.VEHICLE_IO, "VehicleIO: GỬI lệnh tới bo",
     "Lệnh bám đường đi qua giao thức tới bo chọn ở thẻ Bo điều khiển. Mặc định là bo mô phỏng (SimVehicleIO + "
     "FirmwareModel): tốc độ và góc lái lấy từ telemetry, tư thế lấy từ mô phỏng (định vị lý tưởng)."),
    (DriveMode.OBSERVE, "Quan sát: tính lệnh, KHÔNG gửi",
     "Người lái cầm lái xe mô phỏng bằng ↑ ↓ ← → (Space phanh, Esc kết thúc). Phần mềm chỉ tính và ghi lệnh "
     "(commands.csv); bo giữ DISARMED, không nhận COMMAND nào. Tư thế lấy từ mô phỏng."),
)
SIM_BOARD_LABEL = "Bo mô phỏng (mặc định)"
# Nguồn tư thế của nhánh VehicleIO/Quan sát (T2, 02/10/2026; application/lidar_pose_source.py). "lidar_real" chỉ có trong
# ui.lidar_app (cần ngăn LiDAR và bản đồ); bo mô phỏng chỉ đi với sim_truth / lidar_sim, bo COM với sim_truth / lidar_real.
POSE_SOURCE_CHOICES = (
    ("sim_truth", "Mô phỏng: định vị lý tưởng (mặc định)"),
    ("lidar_sim", "LiDAR mô phỏng: định vị trên vòng quét dựng từ sa bàn"),
    ("lidar_real", "LiDAR thật: định vị trên bản đồ tĩnh"),
)
LIDAR_REAL_ONLY_TIP = "Chỉ có trong python -m autopark.ui.lidar_app (cần ngăn LiDAR)"
ESPRESSIF_VID = 0x303A        # VID USB của Espressif (USB CDC/JTAG gắn liền ESP32-S3); chỉ để gợi ý, không để lọc
# Nút "Xóa lỗi bo (CLEAR_FAULT)" (thêm 02/10/2026, T15): `VehicleLink.clear_fault` trên liên kết đang chọn.
CLEAR_FAULT_TIP = ("Đọc trạng thái bo của nhánh chạy (VehicleIO hoặc Quan sát). Chỉ khi bo đang FAULT và telemetry báo "
                   "nút dừng khẩn đã nhả mới gửi CLEAR_FAULT; bo về DISARMED. Không ARM, không gửi lệnh chuyển động. "
                   "Chỉ dùng khi chưa chạy.")
# Thẻ "Xe" (thêm 02/10/2026; người dùng giao quyết định 02/10/2026 ('làm hết'): xe nghiệm thu riêng 0,10 m/s, mặc định
# không đổi): ô "Cấu hình xe" chọn tệp configs/vehicle_*.json; bo mô phỏng tự chọn theo tệp xe (choose_sim_io_config).
VEHICLE_CHOICE_TIP = ("Tệp cấu hình xe mà planner, bộ bám và bo mô phỏng dùng. Chỉ đổi khi đang chỉnh hoặc sẵn sàng; "
                      "đổi xe hủy đường đã lập. Xe chọn ở đây (hay bằng --vehicle-config) được giữ khi mở kịch bản "
                      "khác; Lưu ghi tệp xe này vào kịch bản.")
VEHICLE_ACCEPTANCE_HINT = ("Nghiệm thu: vehicle_nghiem_thu.json — tốc độ mục tiêu ≤ 0,10 m/s (N-V1, ĐỀ XUẤT – CHỜ "
                           "CHỐT). vehicle_default.json: planner chạy 0,15 m/s, vượt N-V1.")
# Bo ảo QEMU trong phiên đỗ (thêm 02/10/2026; người dùng giao quyết định 02/10/2026): firmware THẬT trong QEMU, tốc độ,
# góc lái và tư thế từ xe mô phỏng phía laptop (transport/qemu_plant.py, ui/qemu_runner.py). KHÔNG phải bo thật.
QEMU_BOARD_KEY = "qemu"
QEMU_BOARD_LABEL = "Bo ảo QEMU (firmware xe trong giả lập)"
QEMU_COCKPIT_TAG = "BO ẢO QEMU · XE MÔ PHỎNG"
QEMU_START_TIP = ("Build firmware env esp32s3_qemu nếu ảnh thiếu hoặc cũ hơn mã nguồn (lần đầu vài phút), rồi chạy QEMU ở "
                  "một cổng TCP tự chọn trên 127.0.0.1. QEMU dùng khoảng một lõi CPU tới khi tắt; tự tắt khi chọn bo khác "
                  "hoặc đóng cửa sổ.")
QEMU_BOARD_HINT = ("Bo ảo QEMU: firmware THẬT của xe (bản esp32s3_qemu: Serial qua UART0, flash DIO) chạy trong QEMU trên "
                   "máy này — KHÔNG phải bo thật, không có xe thật. Firmware chưa đọc cảm biến nào, nên tốc độ, góc lái và "
                   "tư thế lấy từ XE MÔ PHỎNG phía laptop bám tham chiếu speed_ref, steer_ref mà firmware gửi trong "
                   "telemetry. Mỗi lần Bắt đầu đỗ: đặt xe mô phỏng ở điểm xuất phát, mở socket://, HELLO, kiểm START, "
                   "ARM; xong lần chạy thì DISARM và đóng kết nối. Bo ảo không có xung ESC/servo, E-stop, cảm biến hay "
                   "watchdog phần cứng; đây chỉ là mức MP, không chứng minh gì về bo thật.")
QEMU_PROBE_NOTE = ("Tốc độ, góc lái '—': firmware chưa đọc cảm biến; trong phiên đỗ số đo lấy từ xe mô phỏng phía "
                   "laptop.")

# Lần chạy đang mở (xe đang chạy hoặc đang dừng; 02/10/2026). Luồng giao diện cũng là luồng của vòng điều khiển 50 Hz,
# nên khi đó giao diện không ghi đĩa lâu: "Xuất log CSV…"/"Lưu phiên…" bị khóa và gói phát lại (export_run: PowerShell,
# nén mã nguồn, ≈ 1,4 s) chỉ xuất sau khi xe dừng. Ô "tốc độ chạy" cũng khóa: một lần chạy chỉ một hệ số (cột time_scale).
RUN_OPEN_STATES = (SessionState.RUNNING, SessionState.STOPPING)
# Dấu đồng bộ video–log (T14, thêm 02/10/2026): khóa khi xe đang chạy (ô nháy che cockpit 0,5 s, ghi đĩa trên luồng giao
# diện); dòng CLOCK tự ghi khi phiên vào một trạng thái của lần chạy.
SYNC_BLOCKED_STATES = RUN_OPEN_STATES
RUN_STATES = (SessionState.RUNNING, SessionState.STOPPING, SessionState.STOPPED, SessionState.COMPLETED,
              SessionState.FAULT)


def list_serial_ports() -> list[tuple[str, str]]:
    """(tên cổng, mô tả) của các cổng COM mà pyserial liệt kê, sắp theo số cổng. Chỉ LIỆT KÊ (không mở cổng nào).

    Không có pyserial hoặc liệt kê lỗi thì trả danh sách rỗng."""
    try:
        from serial.tools import list_ports
        found = list(list_ports.comports())
    except Exception:                     # ImportError, lỗi SetupAPI: coi như không có cổng nào
        return []
    out = []
    for info in found:
        device = str(getattr(info, "device", "") or "")
        if not device:
            continue
        desc = str(getattr(info, "description", "") or "")
        if getattr(info, "vid", None) == ESPRESSIF_VID:
            desc = (desc + " · " if desc else "") + "Espressif (VID 303A)"
        out.append((device, desc))

    def key(item):
        digits = "".join(ch for ch in item[0] if ch.isdigit())
        return (item[0].rstrip("0123456789"), int(digits) if digits else -1, item[0])

    return sorted(out, key=key)


def _open_serial_io(port: str):
    """Mở cổng thật cho "Kiểm kết nối bo" (test thay hàm này bằng cổng serial giả)."""
    from autopark.transport.vehicle_io import SerialVehicleIO
    return SerialVehicleIO.open(port)


def _open_qemu_probe_io(board):
    """Kết nối thường (`SerialVehicleIO`, KHÔNG có xe mô phỏng) tới UART0 của bo ảo cho "Kiểm kết nối bo" (02/10/2026):
    báo đúng telemetry của firmware. Đồng hồ của bo nếu có (bo giả trong test), không thì perf_counter."""
    from autopark.transport.vehicle_io import SerialVehicleIO
    return SerialVehicleIO(board.transport_opener()(), port=board.url, clock=board.clock)


class PortCombo(QComboBox):
    """Ô chọn cổng: liệt kê lại cổng COM mỗi lần người dùng mở danh sách (không liệt kê lúc dựng cửa sổ)."""

    def __init__(self, before_popup: Callable[[], None], parent: QWidget | None = None):
        super().__init__(parent)
        self._before_popup = before_popup

    def showPopup(self) -> None:
        self._before_popup()
        super().showPopup()


class SandboxView(QGraphicsView):
    """View lật trục y để y bản đồ hướng lên; chuyển phím cho cửa sổ chính."""

    def __init__(self, scene: QGraphicsScene, key_handler: Callable[[object], bool]):
        super().__init__(scene)
        self._key_handler = key_handler
        self.safe_insets = (330, 83, 38, 143)
        self.place_goal = None
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
        if event.button() == Qt.MouseButton.LeftButton and self.place_goal is not None:
            # Vehicle/obstacle/slot gestures retain their own drag behavior.
            draggable = False
            for item in self.items(event.position().toPoint()):
                obj = item
                while obj is not None:
                    if isinstance(obj, (CarItem, ObstacleItem)):
                        draggable = True
                        break
                    obj = obj.parentItem()
            if not draggable and self.place_goal(self.mapToScene(event.position().toPoint())):
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
    SYNC_SOURCE = "ui.app"   # cột source của dấu đồng bộ (T14); BenchWindow của ui.lidar_app đặt "ui.lidar_app"

    def __init__(self, session: Session, scenario_path: Path | None = None, *,
                 vehicle_override: VehicleConfigFile | None = None):
        super().__init__()
        self.session = session
        self.scenario_path = scenario_path
        # Xe đã chọn (--vehicle-config hay ô "Cấu hình xe"): giữ khi "Mở…" kịch bản khác; None = theo tệp xe kịch bản.
        self.vehicle_override = vehicle_override
        self.sim_board_choice = None           # SimIOChoice của lần chọn bo mô phỏng gần nhất (_sim_io_config)
        self._syncing = False
        self._selection_sync = False
        self._rebuilding_scene = False
        self._obstacle_items: dict[str, ObstacleItem] = {}
        self._preview_index = 0
        self._preview_accum = 0.0
        self._last_state = session.state
        self.setWindowTitle("Autopark — hỗ trợ thao tác gần")
        self.setStyleSheet(theme.STYLE)

        self.scene = QGraphicsScene(self)
        self.view = SandboxView(self.scene, self._handle_key)

        self._build_controls()
        self._build_inspector()
        self._build_cockpit()
        self._build_sync_marks()
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
        if session.acceptance_rule is not None:        # tệp sa bàn gắn nghiệm thu: giới hạn đổi chiều của kịch bản
            self.statusBar().showMessage(session.cusp_limit().summary(), 10000)

    def _build_controls(self) -> None:
        self.primary_action = QPushButton("Tính thao tác")
        self.primary_action.setObjectName("primary")
        self.primary_action.setMinimumWidth(205)
        self.primary_action.clicked.connect(self._primary_dispatch)
        self.preview_action = QPushButton("Xem trước")
        self.preview_action.clicked.connect(self.preview)
        self.reset_action = QPushButton("Vị trí khác")
        self.reset_action.clicked.connect(self._return_to_editing)
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
        self.lbl_cusp_limit = WrapLabel("")              # T12: giới hạn đổi chiều (theo trường acceptance của tệp)
        self.lbl_cusp_limit.setObjectName("hint")
        self.box_file.add(self.lbl_cusp_limit)
        self.box_file.add_layout(theme.row(self.btn_open, self.btn_save, self.btn_save_as))
        layout.addWidget(self.box_file)

        self.box_start = Card("Xuất phát")
        self.start_editor = PoseEditor(self._on_start_editor_changed)
        self.lbl_start_valid = QLabel("")
        self.lbl_goal_valid = QLabel("")
        self.box_start.add(self.start_editor, self.lbl_start_valid, self.lbl_goal_valid)
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
        # 02/10/2026: khóa khi xe đang chạy (RUN_OPEN_STATES) để một lần chạy chỉ có một hệ số, ghi ở cột time_scale của
        # dấu đồng bộ (đổi giờ video ↔ thời gian phiên); lái tay và xem trước vẫn đổi được.
        self.spin_rt.setToolTip("Giây mô phỏng trên một giây thật (nhánh SIM, bo mô phỏng, lái tay, xem trước). Bo chạy "
                                "thời gian thực bỏ qua hệ số này. Khóa khi xe đang chạy: một lần chạy chỉ có một hệ số, "
                                "ghi ở cột time_scale của dấu đồng bộ.")
        form.addRow("tốc độ chạy", self.spin_rt)
        self.btn_manual = QPushButton("Lái tay")
        self.btn_export = QPushButton("Xuất log CSV…")
        self.btn_manual.clicked.connect(self._start_manual)
        self.btn_export.clicked.connect(self._export_log)
        keys = WrapLabel("Lái tay: ↑/↓ tốc độ, ←/→ lái, Space phanh, 0 trả lái, R đặt lại, Esc thoát. "
                         "Khi đang đỗ: Space hoặc Esc để dừng. F8: dấu đồng bộ video–log.")
        keys.setObjectName("hint")
        self.box_sim.add_layout(form)
        self.combo_feedback = QComboBox()
        self.combo_feedback.addItems(["Phản hồi lý tưởng", "Trễ 40 ms + nhiễu 2 mm / 0,2°"])
        self.combo_feedback.currentIndexChanged.connect(self._set_feedback_profile)
        self.box_sim.add(self.combo_feedback)
        drive_title = QLabel("Nhánh chạy khi bấm Thực hiện")
        self.combo_drive = QComboBox()
        for mode, label, _hint in DRIVE_MODE_CHOICES:
            self.combo_drive.addItem(label, mode.value)
        self.combo_drive.setToolTip("Chỉ đổi được khi chưa chạy. Xem trước và lái tay luôn là mô phỏng giai đoạn 0.")
        self.combo_drive.currentIndexChanged.connect(self._set_drive_mode)
        self.lbl_drive_hint = WrapLabel(DRIVE_MODE_CHOICES[0][2])
        self.lbl_drive_hint.setObjectName("hint")
        self.box_sim.add(drive_title, self.combo_drive, self.lbl_drive_hint)
        self.box_sim.add_layout(theme.row(self.btn_manual, self.btn_export))
        self.box_sim.add(keys)
        layout.addWidget(self.box_sim)

        # Bo nhận lệnh của VEHICLE_IO/OBSERVE (thêm 24/09/2026). Mặc định bo mô phỏng; chọn cổng không mở cổng.
        self.box_board = Card("Bo điều khiển")
        self.combo_port = PortCombo(self._refresh_ports)
        self.combo_port.addItem(SIM_BOARD_LABEL, "")
        self.combo_port.addItem(QEMU_BOARD_LABEL, QEMU_BOARD_KEY)     # bo ảo QEMU (02/10/2026): chọn không chạy gì
        self.combo_port.setToolTip("Mở danh sách để quét lại cổng COM. Chọn cổng không mở cổng và không gửi gì.")
        self.combo_port.currentIndexChanged.connect(self._on_port_changed)
        self.btn_ports = QPushButton("Quét cổng")
        self.btn_ports.setToolTip("Liệt kê lại cổng COM (chỉ liệt kê, không mở cổng)")
        self.btn_ports.clicked.connect(self._refresh_ports)
        self.btn_probe = QPushButton("Kiểm kết nối bo")
        self.btn_probe.setToolTip("Mở cổng, gửi HELLO, đọc vài khung telemetry, so giới hạn với cấu hình xe rồi đóng. "
                                  "Không ARM, không gửi lệnh chuyển động.")
        self.btn_probe.clicked.connect(self._probe_board)
        # T15 (02/10/2026): xóa lỗi bo trên VehicleIO của liên kết đang chọn; hàng riêng vì ngăn chỉ rộng 346 px.
        self.btn_clear_fault = QPushButton("Xóa lỗi bo (CLEAR_FAULT)")
        self.btn_clear_fault.setToolTip(CLEAR_FAULT_TIP)
        self.btn_clear_fault.clicked.connect(self._clear_board_fault)
        self.lbl_board_hint = WrapLabel("")
        self.lbl_board_hint.setObjectName("hint")
        self.lbl_board_report = WrapLabel("")
        self.lbl_board_report.setObjectName("hint")
        self.lbl_board_report.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.box_board.add(self.combo_port)
        self.box_board.add(self._build_qemu_row())
        self.box_board.add_layout(theme.row(self.btn_ports, self.btn_probe))
        self.box_board.add(self.btn_clear_fault)
        self.box_board.add(self.lbl_board_hint, self.lbl_board_report)
        self._build_pose_source_widgets()
        layout.addWidget(self.box_board)
        self.serial_io_factory: Callable[[str], object] = _open_serial_io
        self.last_board_probe: BoardProbe | None = None
        self.last_board_clear: BoardFaultClear | None = None
        # mục của liên kết đang chọn: None bo mô phỏng, QEMU_BOARD_KEY bo ảo (02/10/2026), hoặc cổng COM
        self._link_port: str | None = None
        self._sync_sim_board()                 # chọn tệp bo mô phỏng theo tệp xe, rồi viết gợi ý của thẻ

        card = Card("Xe")
        # Ô "Cấu hình xe" (02/10/2026): danh sách configs/vehicle_*.json, đổi được khi đang chỉnh hoặc sẵn sàng.
        self.combo_vehicle = QComboBox()
        self.combo_vehicle.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_vehicle.setMinimumContentsLength(16)      # tên tệp dài không nới ngăn sa bàn (346 px)
        self.combo_vehicle.setToolTip(VEHICLE_CHOICE_TIP)
        self.combo_vehicle.currentIndexChanged.connect(self._on_vehicle_chosen)
        vehicle_hint = WrapLabel(escape(VEHICLE_ACCEPTANCE_HINT))
        vehicle_hint.setObjectName("hint")
        self.lbl_vehicle = WrapLabel("")
        self.lbl_vehicle.setObjectName("hint")
        card.add(QLabel("Cấu hình xe"), self.combo_vehicle, vehicle_hint, self.lbl_vehicle)
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
        # Bo ảo QEMU (02/10/2026): nhãn màu cảnh báo, thấy được trong video màn hình (T14); hiện khi chọn bo ảo và nhánh
        # chạy không phải SIM.
        self.board_tag = QLabel(QEMU_COCKPIT_TAG)
        self.board_tag.setObjectName("eyebrow")
        self.board_tag.setStyleSheet(f"color: {theme.WARN};")
        self.board_tag.hide()
        row.addWidget(self.board_tag)
        row.addStretch(1)
        self.pill = StatusPill()
        self.lbl_state = self.pill
        row.addWidget(self.pill)
        self.sync_action = QPushButton("Dấu đồng bộ · F8")
        self.sync_action.setObjectName("hudButton")
        self.sync_action.setAccessibleName("Tạo dấu đồng bộ video và log")
        self.sync_action.setToolTip(
            "Dấu đồng bộ video–log (T14): nháy ô trắng lớn trên cửa sổ này 0,5 s để camera quay (R3) thấy, ghi dòng "
            "SYNC_MARK kèm perf_counter vào runs/sync_marks/. Xuất log CSV ghi thêm tệp …_sync_marks.csv cạnh tệp log. "
            "Dùng trước khi thực hiện và sau khi xe dừng; khóa khi xe đang chạy.")
        self.sync_action.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # bấm nút không lấy phím của sa bàn (lái tay)
        self.sync_action.clicked.connect(lambda: self.make_sync_mark("button"))
        row.addWidget(self.sync_action)
        self.manual_action = QPushButton("Lái tay")
        self.manual_action.setObjectName("hudButton")
        self.manual_action.clicked.connect(lambda: self.stop() if self.session.state == SessionState.MANUAL
                                           else self._start_manual())
        row.addWidget(self.manual_action)
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
        self.phase_title = QLabel("Xoay trở\ntrong chỗ hẹp.")
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
        self.footnote.setToolTip("Mặc định bộ bám đường dùng phản hồi lý tưởng của xe mô phỏng; chọn trễ + nhiễu ở ngăn Mô phỏng.")
        self.setCentralWidget(self.stage)
        self.view.place_goal = self._place_goal

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
        self.scene_context.setVisible(not visible)
        self.map_tools.setVisible(not visible)
        self._arrange_cockpit(self.stage.width(), self.stage.height())

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
        if self.session.scenario.maneuver is not None and self.session.state in (SessionState.COMPLETED, SessionState.STOPPED):
            self.session.prepare_next_maneuver()
            self.trail_item.clear()
            self.start_item.set_pose(self.session.scenario.start)
            self._refresh_all()
            return
        self.reset()
        if self.session.state in EDITABLE_STATES:
            self._edit(lambda: self.session.set_start(self.session.scenario.start))

    def _place_goal(self, point) -> bool:
        if self.session.state not in EDITABLE_STATES or not self.session.scenario.bounds.contains_point(point.x(), point.y()):
            return False
        self.scene.clearSelection()
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

        self.maneuver_area_item = QGraphicsRectItem()
        self.maneuver_area_item.setPen(cosmetic_pen(COLOR_GOAL, 1.0, Qt.PenStyle.DashLine))
        self.maneuver_area_item.setZValue(-1)
        self.maneuver_area_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene.addItem(self.maneuver_area_item)

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

        self.goal_item = CarItem(cfg, QColor(140, 240, 214, 28), QColor(140, 240, 214, 55), COLOR_GOAL,
                                 label="ĐÍCH GẦN", editable=editable, on_change=self._on_goal_item_changed,
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
        self.setWindowTitle("AutoPark — thao tác gần trong chỗ hẹp")
        scene_title = {"bai_do_xe": "Bãi đỗ xe"}.get(sc.name, sc.name.replace("_", " "))
        self.lbl_scene_name.setText(scene_title)
        self.lbl_scene_name.setToolTip(sc.name)
        self.lbl_dimensions.setText(f"{sc.bounds.width:g} × {sc.bounds.height:g} m")
        if self.scenario_path is not None:
            self.lbl_file.setText(f"<b>{self.scenario_path.name}</b>")
            self.lbl_file.setToolTip(str(self.scenario_path))
        else:
            self.lbl_file.setText("(chưa lưu)")
        self._refresh_cusp_limit()
        vehicle_file = sc.vehicle_config_path
        self.lbl_vehicle.setText(
            f"<b>{escape(cfg.name)}</b>"
            + (f" ({escape(Path(vehicle_file).name)})" if vehicle_file is not None else "")
            + f" — dài {cfg.length * 100:.0f} cm, rộng {cfg.width * 100:.0f} cm, "
            f"chiều dài cơ sở {cfg.wheelbase * 100:.0f} cm, lái ±{math.degrees(cfg.max_steer):.0f}°, "
            f"bán kính quay nhỏ nhất {cfg.min_turn_radius * 100:.0f} cm, "
            f"tốc độ tối đa {cfg.max_speed:.2f} m/s.<br>{escape(cfg.notes)}")
        self.lbl_vehicle.setToolTip(str(vehicle_file) if vehicle_file is not None else "")
        self._refresh_vehicle_combo()
        self.instrument.full_scale_mps = cfg.max_speed      # cung tốc độ của đồng hồ lái đầy ở tốc độ tối đa của xe
        self._syncing = True
        try:
            self.start_editor.set_pose(sc.start)
        finally:
            self._syncing = False
        self._refresh_obstacle_list()
        self._refresh_validity()
        self._refresh_mode_widgets()
        self._refresh_status()

    def _refresh_cusp_limit(self) -> None:
        """Nhãn giới hạn đổi chiều trong thẻ Kịch bản (T12; 02/10/2026: theo trường acceptance của tệp sa bàn, chỉ đọc).
        Màu cảnh báo khi cờ --max-cusps không dùng được (lớn hơn số của kịch bản) hay siết hơn số của kịch bản."""
        limit = self.session.cusp_limit()
        rule = limit.rule
        text = escape(limit.summary())
        if limit.cli_ignored or (limit.source == SOURCE_CLI and rule is not None):
            text = f"<span style='color:{theme.WARN}'>{text}</span>"
        self.lbl_cusp_limit.setText(text)
        if rule is None:
            tip = "Giới hạn số lần đổi chiều trước khi thực hiện: --max-cusps, --warn-cusps"
        else:
            mapping = f"acceptance {rule.tag.label} → khóa {rule.key} · " if rule.tag.label != rule.key else ""
            tip = (f"{mapping}Tệp ngưỡng {rule.path} · {rule.status} · sha256 {rule.sha256[:12]} · sửa tệp ngưỡng thì "
                   "mở lại kịch bản")
        self.lbl_cusp_limit.setToolTip(tip)

    def _acceptance_note(self) -> str:
        """' · ' + tóm tắt giới hạn đổi chiều khi tệp đang mở gắn kịch bản nghiệm thu (T12), không thì rỗng."""
        return f" · {self.session.cusp_limit().summary()}" if self.session.acceptance_rule is not None else ""

    def _refresh_validity(self) -> None:
        bounds = maneuver_bounds(self.session.scenario)
        self.maneuver_area_item.setRect(bounds.xmin, bounds.ymin, bounds.width, bounds.height)
        self.maneuver_area_item.setVisible(self.session.scenario.maneuver is not None)
        start = self.session.start_check()
        goal = self.session.goal_check()
        for check, label in ((start, self.lbl_start_valid), (goal, self.lbl_goal_valid)):
            label.setText(check.describe())
            label.setStyleSheet(f"color: {theme.OK}; font-size: 9pt" if check.ok
                                else f"color: {theme.DANGER}; font-size: 9pt; font-weight: 600")
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
        for w in (self.box_file, self.box_start, self.box_obstacles):
            w.setEnabled(editable)
        if not editable:
            self.settings_action.setChecked(False)
        self.settings_action.setEnabled(editable)
        self.manual_action.setEnabled(editable or st == SessionState.MANUAL)
        self.manual_action.setText("Thoát lái tay" if st == SessionState.MANUAL else "Lái tay")
        self.sync_action.setEnabled(st not in SYNC_BLOCKED_STATES)
        titles = {
            SessionState.EDITING: "Tìm đường đỗ   →", SessionState.PLANNING: "Hủy tính đường",
            SessionState.READY: "Bắt đầu đỗ   →", SessionState.PREPARING_PREVIEW: "Hủy xem trước",
            SessionState.PREVIEW: "Kết thúc xem trước", SessionState.RUNNING: "Dừng xe",
            SessionState.STOPPING: "Đang dừng…", SessionState.STOPPED: "Chọn lại vị trí",
            SessionState.COMPLETED: "Đỗ lại   →", SessionState.FAULT: "Chọn lại vị trí",
            SessionState.MANUAL: "Kết thúc lái tay",
        }
        titles.update({SessionState.EDITING: "Tính thao tác   →", SessionState.READY: "Thực hiện   →",
                       SessionState.COMPLETED: "Chọn đích tiếp   →"})
        self.primary_action.setText(titles[st])
        self.primary_action.setEnabled(st != SessionState.STOPPING)
        theme.set_role(self.primary_action, "danger" if st == SessionState.RUNNING else "primary")
        self.preview_action.setVisible(st == SessionState.READY)
        self.preview_action.setEnabled(st == SessionState.READY)
        self.reset_action.setVisible(st in (SessionState.READY, SessionState.COMPLETED))
        self.btn_manual.setEnabled(editable)
        self.spin_rt.setEnabled(st not in RUN_OPEN_STATES)
        # Hồ sơ phản hồi giả chỉ có tác dụng ở nhánh SIM; nhánh chạy chỉ đổi được khi chưa chạy.
        self.combo_feedback.setEnabled(editable and self.session.vehicle_link is None)
        self.combo_drive.setEnabled(editable)
        self.combo_vehicle.setEnabled(editable)          # đổi xe hủy đường: chỉ khi đang chỉnh hoặc sẵn sàng
        # Cổng và "Kiểm kết nối bo" chỉ dùng khi chưa chạy (không mở cổng song song với một lần chạy).
        for widget in (self.combo_port, self.btn_ports, self.btn_probe):
            widget.setEnabled(editable)
        self._refresh_clear_fault_button()
        self._refresh_qemu_widgets()
        self._refresh_pose_widgets(editable)
        self.btn_inject.setVisible(st == SessionState.RUNNING)
        self.btn_loss.setVisible(st == SessionState.RUNNING)
        self.btn_loss.setEnabled(st == SessionState.RUNNING and self.session.feedback is not None
                                 and not self.session.feedback.lost)
        self._refresh_export_buttons()
        for item in self._obstacle_items.values():
            item.set_editable(editable)
        self.start_item.set_editable(editable)
        self.start_item.setVisible(editable or st in (SessionState.PLANNING, SessionState.PREPARING_PREVIEW))
        self.goal_item.set_editable(editable)
        self.goal_item.setVisible(True)
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
            SessionState.FAULT: ("CẦN ĐIỀU CHỈNH", "Xe đã\ndừng lại.", "Kiểm tra thông báo rồi chọn\nlại tư thế đích.", 2),
            SessionState.MANUAL: ("LÁI TAY", "Cầm lái\ntheo cách bạn.", "↑ ↓ Tăng / giảm tốc\n← → Đánh lái · Space phanh", 2),
        }
        if s.scenario.maneuver is not None:
            limits = s.scenario.maneuver
            copy.update({
                SessionState.EDITING: ("01 / ĐÍCH GẦN", "Xoay trở\ntrong chỗ hẹp.",
                    f"Kéo và xoay xe đích trong {limits.max_goal_distance_m * 100:.0f} cm.\n"
                    f"Đường ≤ {limits.max_path_length_m:.2f} m · đổi chiều ≤ {limits.max_cusps} lần.", 0),
                SessionState.PLANNING: ("02 / TÍNH THAO TÁC", "Đang tìm\ncách đánh lái.", "Chỉ tìm trong vùng nét đứt quanh xe.", 1),
                SessionState.READY: ("02 / SẴN SÀNG", "Thao tác\nđã sẵn sàng.", "Xem trước rồi nhấn Thực hiện.\nXe tự dừng tại đích gần.", 1),
                SessionState.RUNNING: ("03 / THAO TÁC GẦN", "Xe đang\nxoay trở.", "Nhấn Dừng xe hoặc Esc\nđể dừng bất cứ lúc nào.", 2),
                SessionState.COMPLETED: ("ĐÃ DỪNG TẠI ĐÍCH", "Thao tác\nhoàn tất.", "Bạn chọn đích tiếp theo\ntừ vị trí xe vừa dừng.", 3),
            })
            if st in (SessionState.RUNNING, SessionState.COMPLETED):
                self.pill.set("Đang thao tác" if st == SessionState.RUNNING else "Thao tác xong", _STATE_TONE.get(st, theme.OK))
        tag, title, hint, stage = copy[st]
        if st == SessionState.RUNNING and self._observe_human() is not None:
            self.pill.set("Quan sát", theme.WARN)
            tag, title = "03 / QUAN SÁT", "Người lái\ncầm lái."
            hint = "Phần mềm chỉ tính lệnh, KHÔNG gửi.\n↑ ↓ ← → lái xe mô phỏng · Esc kết thúc"
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
            self.lbl_plan.setText("Đang tìm thao tác phù hợp…")
        elif st == SessionState.PREPARING_PREVIEW:
            self.lbl_plan.setText("Đang chuẩn bị mô phỏng…")
        elif pr is None:
            self.lbl_plan.setText("Chọn tư thế đích gần, sau đó tính thao tác.")
        elif pr.ok and s.trajectory is not None:
            text, tip = f"{s.trajectory.length:.2f} m  ·  {s.trajectory.n_cusps} lần đổi chiều", pr.message
            cusps = s.cusp_check()                # T12: chỉ báo; chặn ở Session.start_run khi có --max-cusps
            limit = s.cusp_limit()                # hay khi tệp sa bàn gắn nghiệm thu (02/10/2026)
            if cusps.refused:
                of = f" của {limit.rule.key}" if limit.source == SOURCE_ACCEPTANCE else ""
                text += (f"  ·  <span style='color:{theme.DANGER}'>"
                         f"{escape(f'vượt giới hạn {cusps.max_cusps}{of}: không chạy')}</span>")
            elif cusps.warned:
                text += (f"  ·  <span style='color:{theme.WARN}'>"
                         f"{escape(f'nhiều đổi chiều (> {cusps.warn_cusps})')}</span>")
            elif limit.short():
                text += "  ·  " + escape(limit.short())
            if cusps.refused or cusps.warned:
                tip += "\n" + cusps.describe()
            if limit.rule is not None:
                tip += "\n" + limit.summary()
            self.lbl_plan.setText(text)
            self.lbl_plan.setToolTip(tip)
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
            self.lbl_step.setText("Chưa có thao tác")
            self.bar.setValue(0)
            return
        if s.state == SessionState.COMPLETED:
            self.lbl_step.setText("Đã hoàn tất thao tác")
            self.bar.setValue(1000)
            return
        if out is None or s.state in EDITABLE_STATES:
            self.lbl_step.setText("Thao tác đã sẵn sàng")
            self.bar.setValue(0)
            return
        pts = traj.points
        done = pts[min(out.index, len(pts) - 1)].s
        frac = done / traj.length if traj.length > 0 else 1.0
        way = "tiến" if pts[min(out.index, len(pts) - 1)].direction > 0 else "lùi"
        text = f"Đoạn {out.segment + 1}/{len(traj.segments)} · {way} · {frac * 100:.0f}%"
        if self._observe_human() is not None:
            text += (f" · gợi ý {out.target_speed:+.2f} m/s, lái {math.degrees(out.target_steer):+.0f}°"
                     " (không gửi)")
        self.lbl_step.setText(text)
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
        color = theme.OK if report.completed and tol_ok else (theme.DANGER if report.collided else theme.WARN)
        description = report.describe()
        if s.scenario.maneuver is not None:
            description = description.replace("Đỗ xong", "Thao tác xong")
        lines = [f"<span style='color:{color}'>{description}</span>"]
        if report.completed:
            verdict = ("<b>ĐẠT dung sai</b>" if tol_ok else "<b>Ngoài dung sai</b>")
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
        """Mở kịch bản. Đã chọn xe (--vehicle-config hay ô "Cấu hình xe", `vehicle_override`) thì kịch bản dùng xe đó và
        tệp xe của kịch bản không được đọc (tệp đó thiếu hay hỏng cũng không hiện hộp lỗi); không thì dùng tệp xe của
        kịch bản. 02/10/2026: gộp BenchWindow._open_scenario của ui.lidar_app vào đây."""
        path, _ = QFileDialog.getOpenFileName(self, "Mở kịch bản", str(self._scenario_dir()), "JSON (*.json)")
        if not path:
            return
        override = self.vehicle_override
        try:
            scenario = load_scenario(path)
            if override is not None:
                scenario.vehicle_config_path = override.path     # lưu lại thì trỏ đúng tệp xe đang dùng
                cfg = override.cfg
            else:
                cfg = load_vehicle_config(scenario.vehicle_config_path)
            self.session.replace_scenario(scenario, cfg)
        except Exception as exc:  # noqa: BLE001 - báo lỗi cho người dùng
            QMessageBox.critical(self, "Không mở được kịch bản", str(exc))
            return
        self.scenario_path = Path(path)
        self._rebuild_scene()
        self._refresh_all()
        self._sync_sim_board()
        if override is None:
            self.statusBar().showMessage(f"Đã mở {path}{self._acceptance_note()}", 4000)
        else:
            self.statusBar().showMessage(f"Đã mở {path}; xe theo {override.path.name} (đã chọn bằng --vehicle-config "
                                         f"hay ô Cấu hình xe; không dùng tệp xe của kịch bản){self._acceptance_note()}",
                                         8000)

    def _save_scenario(self) -> None:
        if self.scenario_path is None:
            self._save_scenario_as()
            return
        self._write_scenario(self.scenario_path)

    def _write_scenario(self, path: Path) -> bool:
        try:
            save_scenario(self.session.scenario, path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Không lưu được", str(exc))
            return False
        self.scenario_path = path
        vehicle_file = self.session.scenario.vehicle_config_path      # Lưu ghi tệp xe đang dùng vào kịch bản
        self.statusBar().showMessage(f"Đã lưu {self.scenario_path}"
                                     + (f" (xe: {Path(vehicle_file).name})" if vehicle_file is not None else ""), 4000)
        return True

    def _save_scenario_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Lưu kịch bản", str(self._scenario_dir()), "JSON (*.json)")
        if not path:
            return
        if self._write_scenario(Path(path)):
            self._refresh_all()

    def _refusal_link(self) -> VehicleLink | None:
        """Liên kết đang chọn khi chỉ nó giữ bằng chứng chưa xuất được (thêm 02/10/2026): log hiện tại không phải của
        lần chạy qua VehicleIO nào, liên kết chưa mở lần chạy nào, nhưng đã có START bị từ chối (`start_refusals.csv`,
        ví dụ START_TOO_MANY_CUSPS của T12 — bằng chứng GD2) hay lần bấm "Xóa lỗi bo" (`board_actions.csv`, T15). Xuất log
        khi đó ghi log của liên kết này: nó chưa chạy lần nào nên không lẫn log của lần chạy cũ. None khi không có."""
        s = self.session
        if s.run_snapshot is not None and "vehicle_link" in s.run_snapshot:
            return None                          # log là của một lần chạy qua VehicleIO: xuất log của chính lần đó
        link = s.vehicle_link
        if link is None or link.runs > 0 or not (link.start_refusals or link.board_actions):
            return None
        return link

    def _refresh_export_buttons(self) -> None:
        """"Xuất log CSV…" và "Lưu phiên…": dùng được khi có log của phiên hoặc log từ chối START của liên kết đang chọn
        (`_refusal_link`); khóa khi lần chạy đang mở (RUN_OPEN_STATES): ghi đĩa trên luồng của vòng điều khiển."""
        exportable = len(self.session.log) > 0 or self._refusal_link() is not None
        run_open = self.session.state in RUN_OPEN_STATES
        for button in (self.btn_export, self.btn_save_run):
            button.setEnabled(exportable and not run_open)
            button.setToolTip("Khóa khi xe đang chạy: lưu sau khi xe dừng." if run_open else "")
        self.btn_save_run.setVisible(exportable)

    def _export_log(self) -> None:
        default = str(self._scenario_dir().parent / "logs" / "lan_chay.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Xuất log", default, "CSV (*.csv)")
        if not path:
            return
        # Chỉ ghi log VehicleIO khi log hiện tại là của đúng lần chạy qua liên kết đó (snapshot có khóa vehicle_link);
        # log lái tay (run_snapshot None) không kèm log VehicleIO của lần chạy trước.
        snap = self.session.run_snapshot
        link = self.session.run_link if snap is not None and "vehicle_link" in snap else None
        refusal_link = None if link is not None else self._refusal_link()
        bundle, refused = None, ""
        sync_file = None
        try:
            self.session.log.to_csv(path)
            if link is not None or refusal_link is not None:
                # Lần chạy qua VehicleIO / quan sát: thư mục <tên>_vehicle_io (log VehicleLink, như trước T9). Chưa có
                # lần chạy như thế: log START bị từ chối / "Xóa lỗi bo" của liên kết đang chọn (02/10/2026).
                (link or refusal_link).write_logs(Path(path).with_suffix("").with_name(Path(path).stem + "_vehicle_io"))
            if self.session.run_snapshot is not None and self.session.world is not None:
                # Gói <tên>_<thời điểm>: SIM tái mô phỏng; qua VehicleIO (T9, 02/10/2026) có thêm vehicle_io/ và
                # phát lại bằng log. Gói bị từ chối thì CSV và thư mục _vehicle_io vẫn ghi; chỉ báo ở thanh trạng thái
                # (không mở hộp thoại).
                if self.session.state in RUN_OPEN_STATES:
                    # Lần chạy còn mở (nút đã khóa; đây là lớp phòng thủ cho lời gọi thẳng): export_run chạy PowerShell
                    # và nén mã nguồn ≈ 1,4 s trên luồng của vòng điều khiển, gói lại tả một lần chạy chưa xong.
                    refused = "lần chạy chưa kết thúc, chỉ xuất sau khi xe dừng"
                else:
                    from datetime import datetime
                    from autopark.storage.run_store import ReplayNotSupported, export_run
                    target = Path(path).with_suffix("").with_name(
                        Path(path).stem + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
                    try:
                        bundle = export_run(self.session, target)
                    except ReplayNotSupported as exc:
                        refused = str(exc)
            sync_file = self._export_sync_marks(Path(path))
            extras = self._export_extras(Path(path), bundle)
        except OSError as exc:
            QMessageBox.critical(self, "Không ghi được", str(exc))
            return
        extra = ""
        if refused:
            extra = (" (+ thư mục _vehicle_io; " if link is not None else " (") + f"KHÔNG xuất gói phát lại: {refused})"
        elif link is not None:
            extra = " (+ thư mục _vehicle_io" + (f", gói phát lại {bundle.name})" if bundle is not None else ")")
        if refusal_link is not None:
            extra += (f" (+ thư mục _vehicle_io của liên kết đang chọn, chưa chạy lần nào: {refusal_link.refused_starts} "
                      f"lần START bị từ chối, {len(refusal_link.board_actions)} lần Xóa lỗi bo)")
        extra += " (+ dấu đồng bộ)" if sync_file is not None else ""
        extra += extras
        self.statusBar().showMessage(f"Đã ghi {len(self.session.log)} dòng vào {path}{extra}", 5000)

    def _export_extras(self, csv_path: Path, bundle: Path | None) -> str:
        """Tệp thêm của lớp con khi xuất log, sau dấu đồng bộ (T3, 02/10/2026: tệp trỏ tới bản ghi cảm biến của
        `ui.lidar_app`). Trả phần chữ thêm vào lời báo; lỗi đĩa (OSError) ném ra như các tệp khác."""
        return ""

    def _set_drive_mode(self, index: int) -> None:
        mode = DriveMode(self.combo_drive.itemData(index))
        port = self.board_port()
        try:
            # T2: (nhánh, bo, nguồn tư thế); tổ hợp bị cấm → ValueError tiếng Việt, trả cả ba ô về liên kết đang dùng
            link = self._build_link(mode, port, self.pose_choice())
        except ValueError as exc:
            self._revert_link_widgets()
            QMessageBox.warning(self, "Không đổi được nhánh chạy", str(exc))
            return
        try:
            self.session.set_vehicle_link(link)
        except SessionError as exc:
            if link is not None:
                link.close()
            with QSignalBlocker(self.combo_drive):
                self.combo_drive.setCurrentIndex(self.combo_drive.findData(self.session.drive_mode.value))
            with QSignalBlocker(self.combo_port):
                self.combo_port.setCurrentIndex(max(0, self.combo_port.findData(self._link_port or "")))
            QMessageBox.warning(self, "Không đổi được nhánh chạy", str(exc))
            return
        self._link_port = self.board_key() or None
        self._link_pose_choice = self.pose_choice()
        self.lbl_drive_hint.setText(escape(DRIVE_MODE_CHOICES[index][2]))
        self._refresh_board_hint()
        self._refresh_mode_widgets()
        self._refresh_status()

    # ------------------------------------------------------------------ bo điều khiển (24/09/2026)
    def board_key(self) -> str:
        """Mục đang chọn ở thẻ "Bo điều khiển": "" bo mô phỏng, QEMU_BOARD_KEY bo ảo QEMU (02/10/2026), hoặc cổng COM."""
        data = self.combo_port.currentData()
        return str(data) if data else ""

    def board_is_qemu(self) -> bool:
        return self.board_key() == QEMU_BOARD_KEY

    def board_port(self) -> str | None:
        """Cổng serial đang chọn ở thẻ "Bo điều khiển"; None = bo mô phỏng (mặc định) hoặc bo ảo QEMU."""
        key = self.board_key()
        return key if key and key != QEMU_BOARD_KEY else None

    def _refresh_ports(self) -> None:
        """Liệt kê lại cổng COM (không mở cổng). Cổng đang chọn mà không còn thấy vẫn được giữ, ghi "(không thấy)":
        không tự đổi sang bo khác. Bo mô phỏng và bo ảo QEMU luôn là hai mục đầu."""
        current = self.board_key()
        ports = list_serial_ports()
        with QSignalBlocker(self.combo_port):
            self.combo_port.clear()
            self.combo_port.addItem(SIM_BOARD_LABEL, "")
            self.combo_port.addItem(QEMU_BOARD_LABEL, QEMU_BOARD_KEY)
            for device, desc in ports:
                self.combo_port.addItem(f"{device} — {desc}" if desc else device, device)
            if current and self.combo_port.findData(current) < 0:
                self.combo_port.addItem(f"{current} (không thấy — đã rút?)", current)
            self.combo_port.setCurrentIndex(max(0, self.combo_port.findData(current)))
        self.statusBar().showMessage(f"Thấy {len(ports)} cổng COM" if ports else
                                     "Không thấy cổng COM nào (hoặc pyserial không liệt kê được)", 5000)

    def _on_port_changed(self, _index: int = -1) -> None:
        if (self.board_key() or None) == self._link_port:
            self._refresh_board_hint()
            return
        self.lbl_board_report.setText("")
        self._set_drive_mode(self.combo_drive.currentIndex())
        self._after_board_choice()

    def _sim_board_note(self) -> str:
        """Câu đầu của gợi ý bo mô phỏng: tệp vehicle_io_sim*.json đã chọn theo tệp xe (02/10/2026); '' khi chưa
        chọn."""
        choice = self.sim_board_choice
        if choice is None:
            return ""
        vehicle_file = self.session.scenario.vehicle_config_path
        source = choice.path.name if choice.path is not None else "cấu hình mặc định trong mã"
        if choice.matched:
            text = f"Bo mô phỏng theo {source} (khớp tệp xe {Path(vehicle_file).name})"
            return text + (f"; {choice.note}" if choice.note else "")
        return (f"Bo mô phỏng theo {source}: {choice.note}. Giới hạn bo lệch cấu hình xe theo hướng nguy hiểm (bo cho "
                f"chạy nhanh hơn xe…) thì Bắt đầu đỗ ở VehicleIO bị TỪ CHỐI (LIMITS_MISMATCH); bo chặt hơn chỉ "
                f"cảnh báo")

    def _refresh_board_hint(self) -> None:
        port = self.board_port()
        if self.board_is_qemu():
            text = QEMU_BOARD_HINT
        elif port is None:
            head = self._sim_board_note()
            text = ((f"{head}. " if head else "Bo mô phỏng: ")
                    + "VehicleIO và Quan sát đi qua SimVehicleIO + FirmwareModel, tư thế lấy từ mô phỏng. "
                    "Kiểm kết nối bo ở đây dùng bo mô phỏng. Xóa lỗi bo (CLEAR_FAULT) không dùng với bo mô phỏng: mỗi "
                    "lần Bắt đầu đỗ tạo bo mới ở DISARMED.")
        else:
            text = (f"Bo THẬT qua {port}. Chọn cổng không mở cổng. Bắt đầu đỗ ở VehicleIO hay Quan sát sẽ bị TỪ CHỐI: "
                    f"chưa có nguồn tư thế thật (định vị LiDAR chưa nối vào phiên); tư thế mô phỏng không dùng với bo "
                    f"thật. Kiểm kết nối bo chỉ gửi HELLO (bo về DISARMED), đọc telemetry rồi đóng cổng; không ARM, "
                    f"không gửi lệnh chuyển động. Xóa lỗi bo (CLEAR_FAULT, ở nhánh VehicleIO hoặc Quan sát) dùng chính "
                    f"cổng này: mở, HELLO, đọc trạng thái, chỉ gửi CLEAR_FAULT khi bo đang FAULT và nút dừng khẩn đã "
                    f"nhả, rồi đóng cổng.")
        text = self._pose_board_hint(port, text)
        self.lbl_board_hint.setText(escape(text))

    # ------------------------------------------------------------------ nguồn tư thế (T2, 02/10/2026)
    def _build_pose_source_widgets(self) -> None:
        """"Nguồn tư thế" trong thẻ Bo điều khiển: ô chọn, bản đồ LiDAR, "Đặt xuất phát theo LiDAR", nhãn trạng thái
        (làm mới 5 Hz). Không đổi gì của liên kết cho tới khi người dùng chọn."""
        self.lidar_pose_source = None              # LidarPoseSource của ui.lidar_app (BenchWindow); None ở ui.app
        self._link_pose_choice = "sim_truth"
        self._hinted_start: Pose | None = None
        self.lidar_pose_item: CarItem | None = None
        self._pose_config = None
        title = QLabel("Nguồn tư thế")
        self.combo_pose = QComboBox()
        for key, label in POSE_SOURCE_CHOICES:
            self.combo_pose.addItem(label, key)
        if not self._lidar_real_supported():
            item = self.combo_pose.model().item(self.combo_pose.findData("lidar_real"))
            item.setEnabled(False)
            item.setToolTip(LIDAR_REAL_ONLY_TIP)
        self.combo_pose.setToolTip("Chỉ đổi được khi chưa chạy. LiDAR thật chỉ đi với bo COM, LiDAR mô phỏng chỉ đi "
                                   "với bo mô phỏng.")
        self.combo_pose.currentIndexChanged.connect(self._on_pose_choice_changed)
        self.btn_lidar_map = QPushButton("Chọn bản đồ LiDAR…")
        self.btn_lidar_map.setToolTip("Thư mục bản đồ của autopark.lidar.map_builder (costmap.json, hệ sa bàn)"
                                      if self._lidar_real_supported() else LIDAR_REAL_ONLY_TIP)
        self.btn_lidar_map.clicked.connect(self._choose_lidar_map)
        self.btn_start_from_lidar = QPushButton("Đặt xuất phát theo LiDAR")
        self.btn_start_from_lidar.setToolTip("Lấy tư thế OK hiện tại của định vị LiDAR làm điểm xuất phát. Khi đó kiểm "
                                             "START với điểm xuất phát không còn là kiểm độc lập.")
        self.btn_start_from_lidar.clicked.connect(self._start_from_lidar)
        self.lbl_lidar_map = WrapLabel("")
        self.lbl_lidar_map.setObjectName("hint")
        self.lbl_pose_status = WrapLabel("")
        self.lbl_pose_status.setObjectName("hint")
        self.lbl_pose_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.box_board.add(title, self.combo_pose)
        self.box_board.add_layout(theme.row(self.btn_lidar_map, self.btn_start_from_lidar))
        self.box_board.add(self.lbl_lidar_map, self.lbl_pose_status)
        self._pose_timer = QTimer(self)
        self._pose_timer.setInterval(200)
        self._pose_timer.timeout.connect(self._refresh_pose_status)
        self._pose_timer.start()

    def pose_choice(self) -> str:
        """Nguồn tư thế đang chọn: "sim_truth", "lidar_sim" hoặc "lidar_real"."""
        return str(self.combo_pose.currentData() or "sim_truth")

    def _lidar_real_supported(self) -> bool:
        """LiDAR thật cần ngăn LiDAR và bản đồ: chỉ cửa sổ của ui.lidar_app (BenchWindow) trả True."""
        return False

    def _dock_lidar_port(self) -> str | None:
        """Cổng LiDAR của ngăn LiDAR (BenchWindow); None ở ui.app."""
        return None

    def _choose_lidar_map(self) -> None:
        self.statusBar().showMessage(LIDAR_REAL_ONLY_TIP, 5000)

    def _lidar_pose_config(self):
        """Cấu hình định vị LiDAR (configs/dinh_vi_lidar_v0.json), nạp một lần."""
        if self._pose_config is None:
            from autopark.lidar.pose_config import load_lidar_pose_config
            self._pose_config = load_lidar_pose_config()
        return self._pose_config

    def _on_pose_choice_changed(self, _index: int = -1) -> None:
        if self.pose_choice() != self._link_pose_choice:
            self._set_drive_mode(self.combo_drive.currentIndex())
        self._after_pose_choice()
        self._refresh_board_hint()

    def _build_link(self, mode: DriveMode, port: str | None, choice: str) -> VehicleLink | None:
        """Liên kết cho (nhánh, bo, nguồn tư thế). Tổ hợp bị cấm → ValueError (lời tiếng Việt cho hộp thoại)."""
        if mode == DriveMode.SIM:
            return None
        if self.board_is_qemu():
            if choice != "sim_truth":
                raise ValueError("Bo ảo QEMU chỉ đi với tư thế của xe mô phỏng phía laptop; LiDAR mô phỏng chỉ dùng "
                                 "với bo mô phỏng, LiDAR thật chỉ với bo COM")
            # Bo ảo QEMU (02/10/2026): chưa mở gì; mỗi START lấy bo đang chạy từ runner của thẻ Bo điều khiển.
            return VehicleLink.qemu_board(mode, self.qemu_runner, plant_config=self._qemu_plant_config())
        lidar_port = self._dock_lidar_port()
        if port is not None and lidar_port and port.strip().upper() == lidar_port.strip().upper():
            raise ValueError(f"{port} là cổng của LiDAR ở ngăn LiDAR, không phải bo ESP32-S3")
        if port is None:
            if choice == "lidar_real":
                raise ValueError("LiDAR thật không đi cùng bo mô phỏng: xe mô phỏng chạy còn LiDAR đứng trên bàn, tư "
                                 "thế đo được không phải của xe đang chạy")
            if choice == "lidar_sim":
                from autopark.application.lidar_pose_source import LidarSimPoseFactory
                config = self._lidar_pose_config()
                # Tuổi tư thế tối đa riêng + dự đoán tư thế tới io.now() (LinkParams.for_lidar, sửa sau review 02/10)
                return VehicleLink.simulated(mode, self._sim_io_config(),
                                             params=LinkParams.for_lidar(config.max_pose_age_s),
                                             pose_factory=LidarSimPoseFactory(config))
            return VehicleLink.simulated(mode, self._sim_io_config())
        if choice == "lidar_sim":
            raise ValueError("LiDAR mô phỏng chỉ dùng với bo mô phỏng")
        if choice == "lidar_real":
            source = self.lidar_pose_source
            if source is None:
                raise ValueError("Chưa nạp bản đồ LiDAR: bấm 'Chọn bản đồ LiDAR…' trước")
            # CHƯA THỬ với bo thật: VehicleIO bị từ chối (START_POSE_UNVERIFIED) tới khi gá đo và đủ điều kiện tiên quyết
            # Dự đoán tư thế (for_lidar) chỉ chạy khi telemetry có tốc độ, góc lái đo (bo thật chưa có: T8).
            return VehicleLink.serial_port(mode, port, pose_source=source,
                                           params=LinkParams.for_lidar(source.config.max_pose_age_s))
        # Bo thật (24/09/2026): cổng CHƯA mở; chưa có nguồn tư thế thật nên START sẽ bị từ chối rõ ràng.
        return VehicleLink.serial_port(mode, port)

    def _revert_link_widgets(self) -> None:
        """Trả ô nhánh chạy, ô cổng và ô nguồn tư thế về liên kết đang dùng."""
        with QSignalBlocker(self.combo_drive):
            self.combo_drive.setCurrentIndex(self.combo_drive.findData(self.session.drive_mode.value))
        with QSignalBlocker(self.combo_port):
            self.combo_port.setCurrentIndex(max(0, self.combo_port.findData(self._link_port or "")))
        with QSignalBlocker(self.combo_pose):
            self.combo_pose.setCurrentIndex(max(0, self.combo_pose.findData(self._link_pose_choice)))
        self._after_pose_choice()

    def _after_pose_choice(self) -> None:
        """Móc cho BenchWindow (nối nguồn LiDAR thật với ngăn LiDAR theo lựa chọn)."""

    def _pose_board_hint(self, port: str | None, text: str) -> str:
        if self.board_is_qemu():              # bo ảo QEMU: giữ gợi ý của bo ảo (chỉ tư thế xe mô phỏng)
            return text
        choice = self.pose_choice()
        if port is None and choice == "lidar_sim":
            return ("Bo mô phỏng + LiDAR MÔ PHỎNG: mỗi lần Bắt đầu đỗ tạo bo mới; LiDAR mô phỏng quét sa bàn từ tư thế "
                    "THẬT của xe mô phỏng, định vị (a) + (b) trên bản đồ dựng từ sa bàn, tuổi tư thế tối đa 0,25 s "
                    "(kiểm trên tuổi thô của vòng quét); tư thế được dời tới hiện tại bằng tốc độ, góc lái đo trước "
                    "khi vào bộ bám. Dừng khi định vị lạc (POSE_LOST), lệch (POSE_DISAGREE), không kiểm chéo được "
                    "(POSE_UNCHECKED) hay tư thế cũ (STALE_POSE). Bằng chứng: simulation_only.")
        if port is not None and choice == "lidar_real":
            return (f"Bo THẬT qua {port} + LiDAR thật (định vị trên bản đồ tĩnh). VehicleIO: Bắt đầu đỗ bị TỪ CHỐI "
                    f"trước khi mở cổng (START_POSE_UNVERIFIED) tới khi configs/dinh_vi_lidar_v0.json ghi gá LiDAR đã "
                    f"đo và đạt p04, DV-2, DV-1. Quan sát: ghi POSE_SOURCE_WARNING, mở cổng ở lần Bắt đầu đỗ đầu tiên và "
                    f"giữ mở giữa các lần chạy ('Kiểm kết nối bo' đóng cổng đó trước khi kiểm, lần Bắt đầu đỗ sau mở "
                    f"lại); START_CHECK vẫn từ chối khi telemetry không có tốc độ/góc lái đo (T8). CHƯA THỬ với bo "
                    f"thật.")
        return text

    def _refresh_pose_widgets(self, editable: bool) -> None:
        choice = self.pose_choice()
        self.combo_pose.setEnabled(editable)
        self.btn_lidar_map.setEnabled(editable and self._lidar_real_supported())
        status = self._pose_status()
        self.btn_start_from_lidar.setEnabled(editable and choice != "sim_truth" and status is not None
                                             and status.available and status.vehicle_pose is not None)

    def _pose_status(self):
        """Trạng thái nguồn LiDAR đang chọn (None khi không có): LiDAR thật của cửa sổ, hoặc LiDAR mô phỏng của liên
        kết đang dùng (chỉ có sau lần Bắt đầu đỗ đầu tiên)."""
        choice = self.pose_choice()
        if choice == "lidar_real" and self.lidar_pose_source is not None:
            return self.lidar_pose_source.status()
        if choice == "lidar_sim":
            link = self.session.run_link or self.session.vehicle_link
            source = getattr(link, "pose_source", None)
            if source is not None and hasattr(source, "status"):
                return source.status()
        return None

    def _refresh_pose_status(self) -> None:
        """5 Hz: nhãn trạng thái định vị, gợi ý điểm xuất phát cho nguồn LiDAR thật, xe định vị trên sa bàn."""
        choice = self.pose_choice()
        source = self.lidar_pose_source
        start = self.session.scenario.start
        if source is not None and start != self._hinted_start and self.session.state in EDITABLE_STATES:
            source.set_hint(start)
            self._hinted_start = start
        status = self._pose_status()
        if choice == "sim_truth":
            text = "Mô phỏng: tư thế thật của xe mô phỏng (định vị lý tưởng)."
        elif status is not None:
            text = status.text
        elif choice == "lidar_sim":
            text = "LiDAR mô phỏng: nguồn tạo mới ở mỗi lần Bắt đầu đỗ (bản đồ dựng từ sa bàn)."
        else:
            text = "LiDAR thật: chưa nạp bản đồ."
        self.lbl_pose_status.setText(escape(text))
        st = self.session.state
        editable = st in EDITABLE_STATES
        self.btn_start_from_lidar.setEnabled(editable and choice != "sim_truth" and status is not None
                                             and status.available and status.vehicle_pose is not None)
        show = (choice != "sim_truth" and st not in RUN_STATES and status is not None
                and status.vehicle_pose is not None and math.isfinite(status.vehicle_pose.x))
        if show:
            item = self._ensure_lidar_pose_item()
            item.set_pose(status.vehicle_pose)
            item.setVisible(True)
        elif self.lidar_pose_item is not None:
            try:
                self.lidar_pose_item.setVisible(False)
            except RuntimeError:                  # cảnh đã dựng lại
                self.lidar_pose_item = None

    def _ensure_lidar_pose_item(self) -> CarItem:
        """Xe theo định vị LiDAR trên sa bàn (viền màu nhấn), dựng lại khi cảnh được dựng lại."""
        item = self.lidar_pose_item
        try:
            alive = item is not None and item.scene() is self.scene
        except RuntimeError:                      # cảnh đã dựng lại: đối tượng C++ đã mất
            alive = False
        if not alive:
            item = CarItem(self.session.cfg, QColor(0, 0, 0, 0), QColor(0, 0, 0, 0), QColor(theme.ACCENT), dashed=True,
                           opacity=0.9)
            item.setZValue(6)
            item.setVisible(False)
            self.scene.addItem(item)
            self.lidar_pose_item = item
        return item

    def _start_from_lidar(self) -> None:
        """"Đặt xuất phát theo LiDAR": tư thế OK hiện tại → điểm xuất phát (nguồn "lidar_localize")."""
        status = self._pose_status()
        if self.session.state not in EDITABLE_STATES or status is None or not status.available \
                or status.vehicle_pose is None:
            self.statusBar().showMessage("Chưa có tư thế OK từ định vị LiDAR", 5000)
            return
        pose = status.vehicle_pose
        self._edit(lambda: self.session.set_start(pose, source="lidar_localize"))
        self.start_item.set_pose(self.session.scenario.start)
        self.start_editor.set_pose(self.session.scenario.start)
        self.statusBar().showMessage(
            f"Đặt xuất phát theo LiDAR: ({pose.x:.3f}; {pose.y:.3f}) m, {math.degrees(pose.yaw):.1f}°. Kiểm START với "
            f"điểm xuất phát không còn là kiểm độc lập", 10000)

    def _probe_board(self) -> BoardProbe | None:
        """"Kiểm kết nối bo": HELLO, vài khung telemetry, so giới hạn với cấu hình xe, đóng cổng.

        Không ARM, không COMMAND."""
        if self.session.state not in EDITABLE_STATES:
            return None
        if self.board_is_qemu():
            return self._probe_qemu_board()
        port = self.board_port()
        cfg = self.session.cfg
        released, note = None, ""
        if port is None:
            from autopark.transport.vehicle_io import SimVehicleIO
            io = SimVehicleIO(cfg, self._sim_io_config())
        else:
            answer = QMessageBox.question(
                self, "Kiểm kết nối bo",
                f"Mở {port}, gửi HELLO và đọc vài khung telemetry?\n\nKhông ARM, không gửi lệnh chuyển động. HELLO đưa "
                f"bo về DISARMED. Mở cổng có thể làm ESP32-S3 khởi động lại (DTR/RTS, chưa kiểm).\n\nChỉ tiếp tục nếu "
                f"{port} là bo ESP32-S3 của xe (không phải LiDAR hay thiết bị khác).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return None
            released = self._release_link_port(port)
            note = (f" (đã đóng {released} mà nhánh chạy giữ mở từ lần Bắt đầu đỗ trước; lần Bắt đầu đỗ sau mở lại)"
                    if released else "")
            try:
                io = self.serial_io_factory(port)
            except Exception as exc:          # SerialException (OSError), ValueError, ImportError...
                self.lbl_board_report.setText(escape(f"Không mở được {port}: {exc}{note}"))
                self.statusBar().showMessage(f"Không mở được {port}{note}", 8000)
                return None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report = probe_board(io, cfg, target=port or "bo mô phỏng")
        finally:
            QApplication.restoreOverrideCursor()
        self.last_board_probe = report
        color = theme.OK if report.ok and (report.limits is None or not report.limits.risky) else theme.WARN
        lines = report.lines()
        if released:
            lines.append(f"Trước khi kiểm đã đóng {released} mà nhánh chạy giữ mở từ lần Bắt đầu đỗ trước (bước 0c); "
                         f"lần Bắt đầu đỗ sau mở lại cổng.")
        body = "<br>".join(escape(line) for line in lines)
        self.lbl_board_report.setText(f"<span style='color:{color}'>{body}</span>")
        self.statusBar().showMessage(f"Kiểm kết nối {report.target}: " + ("đạt" if report.ok else "có lỗi") + note,
                                     8000 if released else 6000)
        return report

    def _release_link_port(self, port: str) -> str | None:
        """Sửa sau review 02/10/2026: nhánh chạy đang chọn giữ `port` mở giữa các lần chạy (bước 0c của VehicleLink, T2:
        sau một lần Bắt đầu đỗ, kể cả lần bị từ chối ở START_CHECK) thì đóng cổng đó (`VehicleLink.release_port`) trước
        khi "Kiểm kết nối bo" mở nó: trên Windows một cổng COM chỉ mở được một lần ("Access is denied"). Lần Bắt đầu đỗ
        sau mở lại cổng. Trả tên cổng đã đóng; None khi không đóng gì."""
        link = self.session.vehicle_link
        held = getattr(getattr(link, "io", None), "port", None)
        if link is None or not held or held.strip().upper() != port.strip().upper():
            return None
        return link.release_port()

    def _clear_fault_blocker(self) -> str | None:
        """Lý do nút "Xóa lỗi bo" bị khóa; None = dùng được (T15, thêm 02/10/2026)."""
        st = self.session.state
        if st not in EDITABLE_STATES:
            return f"chỉ dùng khi đang chỉnh hoặc sẵn sàng (đang {st.label})"
        link = self.session.vehicle_link
        if link is None:
            return "nhánh Mô phỏng giai đoạn 0 không dùng bo: chọn nhánh VehicleIO hoặc Quan sát"
        return link.clear_fault_blocker

    def _refresh_clear_fault_button(self) -> None:
        blocker = self._clear_fault_blocker()
        self.btn_clear_fault.setEnabled(blocker is None)
        self.btn_clear_fault.setToolTip(CLEAR_FAULT_TIP + (f"\n\nĐang khóa: {blocker}." if blocker else ""))

    def _clear_board_fault(self) -> BoardFaultClear | None:
        """"Xóa lỗi bo (CLEAR_FAULT)" trên VehicleIO của nhánh chạy đang chọn (`VehicleLink.clear_fault`).

        Chỉ khi chưa chạy, ở nhánh VehicleIO hoặc Quan sát với bo chọn ở cổng COM; kiểm lại cả khi gọi thẳng (nút đã
        khóa ở trạng thái khác). Bo thật: hỏi xác nhận trước khi mở cổng. Không ARM, không COMMAND."""
        blocker = self._clear_fault_blocker()
        if blocker is not None:
            self.statusBar().showMessage(f"Không xóa lỗi bo: {blocker}", 6000)
            return None
        link = self.session.vehicle_link
        if link.realtime and not link.is_qemu:          # bo ảo QEMU: không có ESP32, DTR hay LiDAR để nhầm
            port = getattr(link.io, "port", None) or "cổng serial"
            answer = QMessageBox.question(
                self, "Xóa lỗi bo (CLEAR_FAULT)",
                f"Mở {port} nếu chưa mở, gửi HELLO nếu chưa có phiên, rồi đọc trạng thái bo. Chỉ khi bo đang FAULT và "
                f"telemetry báo nút dừng khẩn đã NHẢ mới gửi CLEAR_FAULT.\n\nCLEAR_FAULT chỉ đưa bo từ FAULT về "
                f"DISARMED: không ARM, không gửi lệnh chuyển động; bánh xe phải đứng yên. Mở cổng có thể làm ESP32-S3 "
                f"khởi động lại (DTR/RTS, chưa kiểm).\n\nChỉ tiếp tục nếu {port} là bo ESP32-S3 của xe (không phải "
                f"LiDAR hay thiết bị khác).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report = link.clear_fault()
        except VehicleLinkError as exc:
            self.lbl_board_report.setText(escape(str(exc)))
            self.statusBar().showMessage(str(exc), 6000)
            return None
        finally:
            QApplication.restoreOverrideCursor()
            self._refresh_export_buttons()        # dòng board_actions.csv mới: xuất được cả khi chưa chạy lần nào
        self.last_board_clear = report
        color = theme.OK if report.ok else theme.WARN
        body = "<br>".join(escape(line) for line in report.lines())
        self.lbl_board_report.setText(f"<span style='color:{color}'>{body}</span>")
        self.statusBar().showMessage(f"CLEAR_FAULT {report.target}: {report.summary()}", 8000)
        return report

    # ------------------------------------------------------------------ bo ảo QEMU (02/10/2026)
    def _build_qemu_row(self) -> QWidget:
        """Hàng "Khởi động bo ảo" và dòng trạng thái của thẻ Bo điều khiển; chỉ hiện khi chọn bo ảo QEMU. Runner rảnh: không
        hẹn giờ, không đọc tệp nào tới khi chọn mục bo ảo."""
        self.qemu_row = QWidget()
        layout = QVBoxLayout(self.qemu_row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.btn_qemu = QPushButton("Khởi động bo ảo")
        self.btn_qemu.setToolTip(QEMU_START_TIP)
        self.btn_qemu.clicked.connect(self._toggle_qemu)
        self.lbl_qemu = WrapLabel("")
        self.lbl_qemu.setObjectName("hint")
        self.lbl_qemu.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.btn_qemu)
        layout.addWidget(self.lbl_qemu)
        self.qemu_row.hide()
        self.qemu_probe_io_factory: Callable[[object], object] = _open_qemu_probe_io
        self.qemu_runner: QemuBoardRunner | None = None
        self.attach_qemu_runner(QemuBoardRunner(self))
        return self.qemu_row

    def attach_qemu_runner(self, runner: QemuBoardRunner) -> None:
        """Dùng `runner` làm bo ảo của cửa sổ (test: runner với bo giả; gọi trước khi chọn mục bo ảo). Runner cũ bị tắt."""
        old = self.qemu_runner
        if old is not None and old is not runner:
            try:
                old.changed.disconnect(self._on_qemu_changed)
            except (RuntimeError, TypeError):
                pass
            old.shutdown()
        self.qemu_runner = runner
        runner.changed.connect(self._on_qemu_changed)
        if hasattr(self, "board_tag"):           # cửa sổ đã dựng xong
            self._on_qemu_changed()

    def _on_qemu_changed(self) -> None:
        self._refresh_qemu_widgets()
        self._refresh_clear_fault_button()       # "Xóa lỗi bo" của liên kết bo ảo cần bo đang chạy

    def _refresh_qemu_widgets(self) -> None:
        """Hàng bo ảo (chỉ khi chọn bo ảo), nút "Khởi động"/"Tắt bo ảo" (chỉ khi đang chỉnh hoặc sẵn sàng; khóa khi đang
        tắt hay máy chưa cấu hình), "Kiểm kết nối bo" (bo ảo phải đang chạy) và nhãn BO ẢO QEMU của cockpit."""
        runner = self.qemu_runner
        qemu = self.board_is_qemu()
        st = runner.state
        editable = self.session.state in EDITABLE_STATES
        self.qemu_row.setVisible(qemu)
        self.btn_qemu.setText("Tắt bo ảo" if st in QEMU_BUSY_STATES else "Khởi động bo ảo")
        self.btn_qemu.setEnabled(qemu and editable and st not in (QemuRunnerState.STOPPING, QemuRunnerState.UNAVAILABLE))
        tone = {QemuRunnerState.RUNNING: theme.OK, QemuRunnerState.FAILED: theme.DANGER,
                QemuRunnerState.STOPPED: theme.TEXT_DIM}.get(st, theme.WARN)
        text = escape(runner.status_text()).replace("\n", "<br>")      # lỗi build kèm 25 dòng cuối của PlatformIO
        self.lbl_qemu.setText(f"<span style='color:{tone}'>{text}</span>")
        if qemu:
            self.btn_probe.setEnabled(editable and st == QemuRunnerState.RUNNING)
        self.board_tag.setVisible(qemu and self.session.drive_mode != DriveMode.SIM)

    def _after_board_choice(self) -> None:
        """Sau khi đổi mục ở thẻ Bo điều khiển: chọn bo ảo chỉ kiểm cấu hình máy (không khởi động gì); rời bo ảo khi nó
        đang chạy, build hay khởi động thì tắt nó."""
        runner = self.qemu_runner
        if self.board_is_qemu():
            runner.availability()
        elif runner.state in QEMU_BUSY_STATES:
            runner.stop("deselect")
            self.statusBar().showMessage("Đã tắt bo ảo QEMU (đã chọn bo khác)", 6000)
        self._on_qemu_changed()

    def _toggle_qemu(self) -> None:
        """Nút "Khởi động bo ảo" / "Tắt bo ảo"."""
        runner = self.qemu_runner
        if runner.state in QEMU_BUSY_STATES:
            runner.stop("user")
        elif self.session.state in EDITABLE_STATES and self.board_is_qemu():
            runner.start()
        self._on_qemu_changed()

    def _qemu_plant_config(self):
        """Tham số xe mô phỏng phía laptop từ configs/bo_ao_qemu.json; lỗi thì mặc định và cảnh báo ở thanh trạng thái."""
        from autopark.transport.qemu_plant import PlantConfig, load_plant_config
        try:
            return load_plant_config()
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"Không đọc được configs/bo_ao_qemu.json ({exc}): dùng tham số mặc định của xe "
                                         f"mô phỏng phía laptop", 8000)
            return PlantConfig()

    def _probe_qemu_board(self) -> BoardProbe | None:
        """"Kiểm kết nối bo" với bo ảo QEMU: không hỏi xác nhận (không có ESP32, DTR hay LiDAR để nhầm), HELLO và vài khung
        telemetry của firmware trong giả lập, so giới hạn, rồi đóng kết nối. Không ARM, không COMMAND."""
        board, reason = self.qemu_runner.current_board()
        if board is None:
            self.lbl_board_report.setText(escape(f"Bo ảo chưa chạy ({reason}): bấm 'Khởi động bo ảo'"))
            self.statusBar().showMessage("Bo ảo chưa chạy: bấm 'Khởi động bo ảo'", 6000)
            return None
        target = f"bo ảo QEMU {board.url}"
        try:
            io = self.qemu_probe_io_factory(board)
        except Exception as exc:          # ConnectionRefusedError (OSError), ValueError...
            self.lbl_board_report.setText(escape(f"Không mở được {target}: {exc}"))
            self.statusBar().showMessage(f"Không mở được {target}", 6000)
            return None
        from autopark.transport.qemu_plant import QEMU_KIND
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report = probe_board(io, self.session.cfg, target=target, kind=QEMU_KIND)
        finally:
            QApplication.restoreOverrideCursor()
        self.last_board_probe = report
        color = theme.OK if report.ok and (report.limits is None or not report.limits.risky) else theme.WARN
        body = "<br>".join(escape(line) for line in report.lines() + [QEMU_PROBE_NOTE])
        self.lbl_board_report.setText(f"<span style='color:{color}'>{body}</span>")
        self.statusBar().showMessage(f"Kiểm kết nối {report.target}: " + ("đạt" if report.ok else "có lỗi"), 6000)
        return report

    def _qemu_url(self, link: VehicleLink) -> str | None:
        """URL bo ảo của liên kết: của io lần chạy gần nhất, không thì của bo đang chạy (nếu có)."""
        port = getattr(link.io, "port", None)
        if port:
            return port
        board = self.qemu_runner.board if self.qemu_runner.state == QemuRunnerState.RUNNING else None
        return getattr(board, "url", None)

    def _qemu_run_text(self, link: VehicleLink) -> str:
        branch = "VehicleIO" if link.mode == DriveMode.VEHICLE_IO else "Quan sát"
        return (f"Nhánh chạy: {branch} qua BO ẢO QEMU ({self._qemu_url(link)}) — tốc độ, góc lái, tư thế từ XE MÔ PHỎNG "
                f"phía laptop; không phải bo hay xe thật")

    def _sim_io_config(self):
        """Cấu hình bo mô phỏng theo tệp xe đang dùng (toàn số GIẢ ĐỊNH; 02/10/2026): tệp configs/vehicle_io_sim*.json
        có vehicle_config trỏ đúng tệp xe, không có thì vehicle_io_sim.json, tệp đó lỗi thì mặc định trong mã
        (`choose_sim_io_config`). Lần chọn ghi ở `sim_board_choice` cho gợi ý của thẻ Bo điều khiển. Không tham số:
        test thay hàm này bằng lambda trả SimIOConfig."""
        from autopark.transport.vehicle_io import choose_sim_io_config
        choice = choose_sim_io_config(self.session.scenario.vehicle_config_path, CONFIGS_DIR)
        self.sim_board_choice = choice
        return choice.config

    def _sync_sim_board(self) -> None:
        """Chọn lại bo mô phỏng theo tệp xe đang dùng rồi viết lại gợi ý của thẻ Bo điều khiển (02/10/2026). Gọi lúc
        dựng thẻ, ngay trước Bắt đầu đỗ, sau khi đổi xe và sau khi mở kịch bản. Liên kết bo mô phỏng đang chọn
        (`sim_config` khác None; liên kết cổng serial hay QEMU không có) nhận cấu hình mới khi chưa có lần chạy đang mở:
        giữ nguyên đối tượng liên kết cùng bằng chứng start_refusals / board_actions, và mỗi lần Bắt đầu đỗ dùng bo khớp
        xe. Không nới kiểm tra nào: bo lệch xe vẫn bị LIMITS_MISMATCH từ chối lúc START ở VehicleIO."""
        config = self._sim_io_config()
        link = self.session.vehicle_link
        if link is not None and link.sim_config is not None and self.session.state not in RUN_OPEN_STATES:
            link.sim_config = config
        self._refresh_board_hint()

    def _refresh_vehicle_combo(self) -> None:
        """Ô "Cấu hình xe": các tệp configs/vehicle_*.json dùng được (`list_vehicle_configs`; tệp hỏng chỉ ghi ở chú
        thích), cộng tệp xe của phiên khi nằm ngoài configs/; chọn đúng tệp xe của phiên (không có tệp xe: không chọn
        mục nào)."""
        files, problems = list_vehicle_configs(CONFIGS_DIR)
        current = self.session.scenario.vehicle_config_path
        key = path_key(current) if current is not None else None
        with QSignalBlocker(self.combo_vehicle):
            self.combo_vehicle.clear()
            for item in files:
                self.combo_vehicle.addItem(f"{item.path.name} — tối đa {item.cfg.max_speed:.2f} m/s",
                                           path_key(item.path))
            if key is not None and self.combo_vehicle.findData(key) < 0:
                self.combo_vehicle.addItem(f"{Path(current).name} (ngoài configs/) — tối đa "
                                           f"{self.session.cfg.max_speed:.2f} m/s", key)
            self.combo_vehicle.setCurrentIndex(self.combo_vehicle.findData(key) if key is not None else -1)
        self.combo_vehicle.setToolTip(VEHICLE_CHOICE_TIP + (f"\n\nTệp không dùng được: {'; '.join(problems)}"
                                                            if problems else ""))

    def _on_vehicle_chosen(self, index: int) -> None:
        """Đổi xe ở ô "Cấu hình xe" (02/10/2026). Chỉ khi đang chỉnh hoặc sẵn sàng; đường đã lập bị hủy; phiên còn log
        (lần chạy hay lái tay, chưa xuất thì mất) thì hỏi trước, mặc định Không. Xe chọn được giữ khi "Mở…" kịch bản
        khác (như --vehicle-config); bo mô phỏng chọn lại theo tệp xe. Không đổi được thì ô trở về xe đang dùng."""
        key = self.combo_vehicle.itemData(index)
        current = self.session.scenario.vehicle_config_path
        if not key or (current is not None and key == path_key(current)):
            return
        st = self.session.state
        if st not in EDITABLE_STATES:
            self._refresh_vehicle_combo()
            self.statusBar().showMessage(f"Chỉ đổi xe khi đang chỉnh hoặc sẵn sàng (đang {st.label})", 6000)
            return
        try:
            chosen = load_vehicle_config_file(key)
        except VehicleConfigError as exc:
            self._refresh_vehicle_combo()
            QMessageBox.warning(self, "Không đổi được xe", str(exc))
            return
        if len(self.session.log) > 0:
            answer = QMessageBox.question(
                self, "Đổi cấu hình xe",
                f"Đổi sang {chosen.path.name} xóa log của lần chạy hay lái tay trước; chưa Xuất log thì mất. Tiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self._refresh_vehicle_combo()
                return
        try:
            self.session.set_vehicle(chosen.cfg, chosen.path)
        except SessionError as exc:
            self._refresh_vehicle_combo()
            QMessageBox.warning(self, "Không đổi được xe", str(exc))
            return
        self.vehicle_override = chosen                  # giữ khi Mở… kịch bản khác
        self._rebuild_scene()
        self._refresh_all()
        self._sync_sim_board()
        cfg = chosen.cfg
        self.statusBar().showMessage(f"Đã chọn xe {cfg.name} ({chosen.path.name}), tốc độ tối đa {cfg.max_speed:.2f} "
                                     "m/s; đường cũ bị hủy: bấm Tính thao tác. Xe này được giữ khi mở kịch bản khác.",
                                     8000)

    def _observe_human(self) -> SimHumanDriver | PlantHumanDriver | None:
        """Người lái mô phỏng của lần quan sát đang chạy (None nếu không ở chế độ quan sát); bo ảo QEMU: người lái xe mô
        phỏng phía laptop."""
        link = self.session.run_link
        if self.session.state != SessionState.RUNNING or link is None or not link.observe_only:
            return None
        return link.human

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
        elif result is not None:
            cusps = self.session.cusp_check()          # T12: đường đổi chiều nhiều / quá giới hạn
            if cusps is not None and (cusps.refused or cusps.warned):
                self.statusBar().showMessage(cusps.describe(), 10000)

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
        if self.session.scenario.maneuver is not None and self.session.state == SessionState.COMPLETED:
            self._return_to_editing()
            return
        if self.sync_flash.lit():
            # Ô dấu đồng bộ (T14) còn phủ cả cửa sổ và không nhận chuột: cú bấm xuyên qua nó tới nút Bắt đầu đỗ. Chờ ô tắt
            # (≤ 0,5 s) để xe không chạy khi cockpit còn bị che; không tắt ô sớm (cạnh bật phải đủ dài trong video).
            self.statusBar().showMessage("Ô dấu đồng bộ còn sáng: chờ ô tắt (0,5 s) rồi mới thực hiện", 4000)
            return
        try:
            if self.session.state == SessionState.COMPLETED:
                self.session.reset()
            self._sync_sim_board()               # bo mô phỏng khớp tệp xe đang dùng (02/10/2026)
            self.session.start_run()
        except SessionError as exc:
            self._refresh_export_buttons()         # START bị từ chối qua VehicleIO: có dòng start_refusals để xuất
            QMessageBox.warning(self, "Không bắt đầu được", str(exc))
            return
        self.trail_item.clear()
        st = self.session.world.state
        self.sim_item.set_pose(st.pose, st.steer)
        self._clock.restart()
        self._refresh_mode_widgets()
        self._refresh_status()
        link = self.session.run_link
        if link is not None:
            limits = link.limits_check
            if limits is not None and not limits.ok:
                # START đã qua nên lệch chỉ là bo chặt hơn (hoặc quan sát): cảnh báo, chi tiết trong events.csv.
                self.statusBar().showMessage(f"LIMITS_MISMATCH (cảnh báo): {limits.describe()}", 15000)
            elif link.is_qemu:
                self.statusBar().showMessage(self._qemu_run_text(link), 8000)
            else:
                self.statusBar().showMessage(f"Nhánh chạy: {self.combo_drive.currentText()}", 8000)
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

    # ------------------------------------------------------------------ dấu đồng bộ video–log (T14, 02/10/2026)
    def _build_sync_marks(self) -> None:
        """Nhật ký dấu đồng bộ trong bộ nhớ và ô nháy phủ cửa sổ. Tệp sống `sync_dir/<giờ>_<nguồn>.csv` chỉ được tạo ở
        dấu đầu tiên (dòng CLOCK trước đó nằm trong bộ nhớ và được ghi lúc tạo tệp): không bấm dấu nào thì không ghi gì
        xuống đĩa. Test đổi `sync_dir` trước dấu đầu tiên."""
        # Thanh trạng thái có từ đầu: QMainWindow chỉ tạo nó ở lần gọi statusBar() đầu tiên. Tạo sau khi ô nháy đã được
        # nâng lên trên cùng (lời báo của dấu đầu tiên) thì nó nằm đè lên ô: một dải 22 px màu giao diện trong video.
        self.statusBar()
        self.sync_dir = DEFAULT_SYNC_DIR
        self.sync_marks = SyncMarkLog(self.SYNC_SOURCE)
        self.sync_flash = SyncFlash(self)
        self.sync_marker = SyncMarker(self.sync_marks, self.sync_flash,
                                      open_file=lambda: sync_file_path(self.sync_dir, self.SYNC_SOURCE))

    def make_sync_mark(self, trigger: str = "button") -> dict | None:
        """Nút "Dấu đồng bộ · F8": nháy ô trắng có số lên cả cửa sổ trong 0,5 s và ghi dòng SYNC_MARK (perf_counter, trạng
        thái phiên, đồng hồ VehicleIO nếu có). Từ chối khi xe đang chạy (RUNNING/STOPPING), khi ô trước còn sáng hoặc
        chưa đủ khoảng cách giữa hai dấu; kết quả báo ở thanh trạng thái. Trả dòng đã ghi hoặc None."""
        if self.session.state in SYNC_BLOCKED_STATES:
            self.statusBar().showMessage("Dấu đồng bộ chỉ dùng trước khi thực hiện hoặc sau khi xe đã dừng", 6000)
            return None
        row = self.sync_marker.mark(trigger, self._sync_context)
        if row is None:
            self.statusBar().showMessage(f"Dấu trước còn đang nháy hoặc chưa đủ {self.sync_marker.min_gap_s:g} s: "
                                         "bấm lại sau", 4000)
            return None
        log = self.sync_marks
        text = (f"Dấu đồng bộ #{row['n']} lúc {row['t_wall'][11:]}, perf_counter {row['t_perf']:.6f} s → "
                f"{log.path.name if log.path is not None else '(chưa có tệp)'}")
        if log.path is None:
            text += f" — CHƯA GHI ĐƯỢC ra đĩa ({log.error}); dấu vẫn giữ trong bộ nhớ, Xuất log CSV sẽ ghi"
        elif log.unwritten:                      # cả dòng CLOCK hỏng trước đó, không chỉ dấu này (02/10/2026)
            text += " — " + self._sync_unwritten_text()
        self.statusBar().showMessage(text, 10000)
        return row

    def _sync_unwritten_text(self) -> str:
        log = self.sync_marks
        return (f"{log.unwritten} dòng CHƯA GHI ĐƯỢC vào {log.path.name} ({log.error}); vẫn giữ trong bộ nhớ, lần ghi sau "
                f"ghi lại cả tệp, Xuất log CSV có bản đủ")

    def _warn_sync_unwritten(self) -> None:
        """Dòng CLOCK không ghi được vào tệp sống (ví dụ tệp đang mở trong Excel, 02/10/2026): báo ở thanh trạng thái, nối
        sau lời báo đang hiện (nhánh chạy, LIMITS_MISMATCH…) thay vì che nó."""
        warning = "Dấu đồng bộ: " + self._sync_unwritten_text()
        current = self.statusBar().currentMessage().split("  ·  Dấu đồng bộ: ")[0]
        if current.startswith("Dấu đồng bộ"):
            current = ""
        self.statusBar().showMessage(f"{current}  ·  {warning}" if current else warning, 10000)

    def _sync_link(self) -> VehicleLink | None:
        """Liên kết VehicleIO mà dấu đồng bộ đọc đồng hồ: trong và sau một lần chạy là liên kết của chính lần đó
        (`run_link`); trước Bắt đầu đỗ là liên kết lần chạy tới sẽ dùng (`vehicle_link`)."""
        s = self.session
        return s.run_link if s.state in RUN_STATES else s.vehicle_link

    def _time_scale(self) -> float:
        """Cột `time_scale` (02/10/2026): giây phiên trên một giây thật. Lần chạy (hay lần Bắt đầu đỗ tới) qua VehicleIO
        thời gian thực: 1, vì thời gian phiên bám `io.now()` và bỏ qua "tốc độ chạy" (`Session.advance`); còn lại (SIM,
        bo mô phỏng, lái tay): `realtime_factor`."""
        s = self.session
        link = self._sync_link()
        if s.state != SessionState.MANUAL and link is not None and link.realtime:
            return 1.0
        return round(s.realtime_factor, 6)

    def _sync_context(self, t_perf: float) -> dict:
        """Các cột của dòng dấu đồng bộ ngoài perf_counter. `t_session` chỉ khi phiên đang mô phỏng (lái tay): sau một
        lần chạy đồng hồ phiên đứng yên. `t_io` đọc `io.now()` của liên kết (cổng serial chưa mở vẫn đọc được: đồng hồ
        perf_counter − hằng số, không chạm cổng). `time_scale`: `_time_scale()`."""
        s = self.session
        ctx: dict = {"state": s.state.value, "note": "SIM", "time_scale": self._time_scale()}
        if s.simulating and s.world is not None:
            ctx["t_session"] = round(s.world.time, 4)
        link = self._sync_link()
        if link is not None:
            port = getattr(link.io, "port", None)
            ctx["note"] = f"{link.mode.value}, " + (f"bo ảo QEMU {self._qemu_url(link) or '(chưa chạy)'}" if link.is_qemu
                                                    else f"cổng {port}" if port else "bo mô phỏng")
            if link.io is not None:
                ctx["t_io"] = round(link.io.now(), 6)
                ctx["io_clock"] = "realtime" if link.realtime else "sim"
        return ctx

    def _clock_context(self, t_perf: float, old: SessionState, new: SessionState) -> dict:
        """Cột của dòng CLOCK lúc phiên đổi trạng thái: `t_session` mỗi khi có `world`, ghi chú là bước chuyển (kèm lý do
        dừng khi có)."""
        ctx = self._sync_context(t_perf)
        if self.session.world is not None:
            ctx["t_session"] = round(self.session.world.time, 4)
        note = f"{old.value}→{new.value}"
        if new != SessionState.RUNNING and self.session.stop_reason:
            note += f": {self.session.stop_reason}"
        ctx["note"] = note
        return ctx

    def _poll_state_change(self) -> None:
        """Gọi mỗi nhịp, ngay sau khi mô phỏng tiến: phiên đổi trạng thái thì cập nhật giao diện (như trước 02/10/2026);
        trạng thái mới thuộc một lần chạy (RUN_STATES) thì thêm một dòng CLOCK ghép perf_counter với thời gian phiên
        trong cùng nhịp (≈ 16 ms; tới 100 ms khi giao diện khựng, vì real_dt bị chặn)."""
        st = self.session.state
        if st == self._last_state:
            return
        old, self._last_state = self._last_state, st
        if st in RUN_STATES:
            self.sync_marker.clock_row("state_change", lambda t: self._clock_context(t, old, st))
            if self.sync_marks.path is not None and self.sync_marks.unwritten:
                self._warn_sync_unwritten()
        self._refresh_mode_widgets()
        self._refresh_status()

    def _export_sync_marks(self, csv_path: Path) -> Path | None:
        """Bản đầy đủ của dấu đồng bộ (cả dòng CLOCK) cạnh tệp log: `<tên>_sync_marks.csv`. Chưa có dấu nào: không ghi."""
        if self.sync_marks.marks == 0:
            return None
        return self.sync_marks.write_csv(csv_path.with_name(csv_path.stem + "_sync_marks.csv"))

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
        self._poll_state_change()

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
        self._refresh_export_buttons()

    def _handle_key(self, event) -> bool:
        key = event.key()
        K = Qt.Key
        st = self.session.state
        if key == K.Key_F8:                       # dấu đồng bộ (T14): trước mọi phím khác, kể cả khi lái tay
            if not event.isAutoRepeat():
                self.make_sync_mark("key_f8")
            return True
        if key == K.Key_Escape:
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
        human = self._observe_human()
        if human is not None and key in (K.Key_Up, K.Key_Down, K.Key_Left, K.Key_Right, K.Key_Space, K.Key_0):
            # Quan sát: phím lái xe mô phỏng thay người lái (tay điều khiển RC); không có gì gửi tới bo.
            speed, steer = human.speed, human.steer
            if key == K.Key_Up:
                speed += self.session.speed_step
            elif key == K.Key_Down:
                speed -= self.session.speed_step
            elif key == K.Key_Left:
                steer += self.session.steer_step
            elif key == K.Key_Right:
                steer -= self.session.steer_step
            elif key == K.Key_Space:
                speed = 0.0
            else:
                steer = 0.0
            human.set(speed, steer)
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
        self._pose_timer.stop()                  # T2: nhãn trạng thái định vị LiDAR
        log = self.sync_marks                    # thử lần cuối ghi đủ tệp dấu đồng bộ (02/10/2026)
        if log.path is not None:
            lost = 0 if log.flush() else log.unwritten
        else:
            lost = len(log.rows) if log.marks else 0      # có dấu mà chưa tạo được tệp sống (lỗi ở log.error)
        if lost:
            print(f"CẢNH BÁO: {lost} dòng dấu đồng bộ chưa ghi được ra đĩa ({log.error}); mất khi đóng cửa sổ nếu chưa "
                  f"Xuất log CSV", file=sys.stderr)
        self.session.close()
        self.qemu_runner.shutdown()              # SAU session.close(): enable=0 + DISARM qua liên kết trước khi tắt QEMU
        super().closeEvent(event)
