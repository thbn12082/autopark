"""Ngăn LiDAR gắn vào cửa sổ đỗ xe: nối RPLIDAR C1 (hoặc phát lại bản ghi), hiện hình quét, và giữ vật cản trên sa
bàn ĐÚNG NHƯ LiDAR ĐANG THẤY — cập nhật sau mỗi vòng quét, không có "bản đồ nền" chụp một lần.

Luồng: thread đọc LiDAR → hàng đợi → timer 50 ms lấy ra, cập nhật hình quét, điểm thô trên sa bàn và lớp
`LiveLidar` (N vòng gần nhất; ô phải bị chạm ở ≥ k vòng mới thành vật cản, lọc nhiễu chớp tắt). LiDAR được coi là
ĐỨNG YÊN tại vị trí xuất phát của sa bàn, cùng hướng xe.

- Đang chỉnh sa bàn (EDITING): sau mỗi vòng quét, hộp nào không còn bị chặn thì bỏ, hộp mới thì thêm
  (`ObstacleBridge.sync_incremental`). Xoay LiDAR hay dời đồ vật là hộp đi theo ngay.
- Đã bấm "Tìm đường đỗ" (READY) và lúc chạy: vật cản được GIỮ CỐ ĐỊNH để lập đường và bám đường; lúc xe chạy, vật
  mới bền vững chạm hành lang quỹ đạo làm xe dừng (MAP_CHANGED của giai đoạn 0), LiDAR quá cũ/mất cũng dừng.
- Đổi cấu hình LiDAR (lề mặt nạ, số vòng, chiều góc) hoặc ngắt kết nối trong lúc xe chạy → yêu cầu dừng, vì bản đồ
  đang dùng không còn là bản đồ đã lập đường. Yêu cầu mang mã LIDAR_CONFIG_CHANGED / LIDAR_MIRROR_CHANGED /
  LIDAR_DISCONNECTED, nguồn lidar_dock; qua VehicleIO nó thành dòng session_stop của events.csv (02/10/2026, T13).
- Đồng hồ (02/10/2026, T3): driver và phát lại `.npz` mở với đồng hồ bàn thử `RIG_CLOCK` (perf_counter, như rig.bench),
  không còn `time.monotonic` (bước 15,6 ms trên Windows). Luồng đọc bọc nguồn bằng `rig.recording.LidarTap`: khi ngăn
  "Ghi cảm biến" đang ghi (`record_sink`), mọi vòng quét vào bản ghi — chỉ từ luồng đọc HIỆN HÀNH và chỉ khi nguồn dùng
  RIG_CLOCK và có `t0` (`lidar_clock_ok`); hình quét, vật cản và giám sát dữ liệu cũ không đổi.

Chỉ hiển thị và chèn vật cản; không có liên hệ tới phần cứng chấp hành.

Thêm 02/10/2026 (T2, nguồn tư thế LiDAR; chỉ kiểm offscreen với nguồn giả, CHƯA THỬ với LiDAR gá trên xe chạy):
đồng hồ của C1 và của bản ghi phát lại là `time.perf_counter` (để đổi dấu thời gian vòng quét sang đồng hồ io); mọi
`ScanReader` chia sẻ danh sách `scan_consumers` (nguồn tư thế LiDAR nhận từng vòng ở luồng đọc); ngắt nguồn hay đổi
chiều góc báo `feed_reset` cho chúng. Khi có `pose_provider` (cửa sổ chọn "LiDAR thật: định vị trên bản đồ tĩnh"):
LiDAR KHÔNG còn coi là đứng yên ở điểm xuất phát; vòng quét chờ (tối đa 5 vòng, 0,3 s) tới khi nguồn tư thế cho tư
thế OK của chính vòng đó rồi mới vào lớp `LiveLidar` ở tư thế ấy (gá theo cấu hình định vị); vòng không có tư thế bị
bỏ và đếm. Mũi tên vàng = tư thế OK gần nhất. Không có `pose_provider`: như trước.

Loại nguồn cho người tiêu thụ (sửa 02/10/2026 sau review gộp đợt 2; chỉ kiểm bằng test): mỗi lần gắn nguồn, ngắt nguồn
và khi nhận người tiêu thụ mới lúc đang có nguồn, ngăn báo `set_feed_kind(feed_kind())` như báo chiều góc: "live" CHỈ
khi nguồn là driver RPLIDAR C1 do `connect_source` mở, "recording_replay" (`--recording`), "session_replay"
(`--session-replay`), "other" (nguồn do test hay nơi khác gắn), None khi ngắt. Nguồn tư thế LiDAR dựa vào đó để từ chối
bo thật khi vòng quét không phải của LiDAR thật.
"""
from __future__ import annotations

from collections import deque
import math
from pathlib import Path
import queue
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QDockWidget, QGraphicsItem, QLabel, QLineEdit, QListWidget, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from autopark.application.session import EDITABLE_STATES, SessionError, SessionState
from autopark.domain.types import Bounds, Pose
from autopark.fusion.bridge import ObstacleBridge
from autopark.fusion.fuse import fuse
from autopark.fusion.layers import LiveLidarLayer, sensor_pose_in_map
from autopark.fusion.obstacles import count_objects
from autopark.lidar.live_view import PacedReplay, ScanReader, ScanStreamEnded
from autopark.lidar.port import CONFIG_PATH, LidarPortError, configured_lidar_port, lidar_port
from autopark.perception.costmap import GridSpec
from autopark.rig.recording import LidarTap
from autopark.rig.replay import END_MESSAGE, STOPPED_MESSAGE
from autopark.safety.freshness import FreshnessMonitor, SourcePolicy
from autopark.ui import theme
from autopark.ui.items import ObstacleItem, cosmetic_pen
from autopark.ui.scan_view import ScanView
from autopark.ui.theme import Card, WrapLabel
from autopark.video.multicam import RIG_CLOCK

RESOLUTION_M = 0.05
MAX_AGE_S = 0.3
EXPECTED_PERIOD_S = 0.1
DRIVING_STATES = (SessionState.RUNNING, SessionState.STOPPING)
PENDING_MAX = 5                   # T2: số vòng chờ tư thế tối đa khi có pose_provider
PENDING_MAX_AGE_S = 0.3           # vòng chờ quá lâu (nguồn tư thế treo) thì bỏ


def lidar_clock_ok(source) -> tuple[bool, str]:
    """Vòng quét của `source` vào được bản ghi cảm biến (T3) không: stamp + `t0` phải là perf_counter của máy này, tức
    nguồn mở với `RIG_CLOCK` và đã có `t0`; phát lại `.npz` thì thêm tốc độ ×1 (ở tốc độ khác stamp + t0 không phải giờ
    thật). (ok, lý do khi không)."""
    if getattr(source, "clock", None) is not RIG_CLOCK:
        return False, "nguồn không dùng đồng hồ perf_counter của bàn thử (RIG_CLOCK)"
    if getattr(source, "t0", None) is None:
        return False, "nguồn chưa có mốc t0 (driver chưa start())"
    speed = getattr(source, "speed", 1.0)
    if isinstance(speed, (int, float)) and speed != 1.0:
        return False, f"phát lại ×{speed:g}: stamp không phải giờ thật"
    return True, ""


class DockLidarReplay:
    """Nguồn LiDAR của ngăn lấy từ MỘT `rig.replay.ReplaySession` dùng chung với ngăn AI camera (T3b, `ui.lidar_app
    --session-replay`, 02/10/2026): vòng quét ra theo CÙNG đồng hồ phát lại với khung camera, nên giữ đúng độ lệch như lúc
    ghi. Như `RplidarC1Source` ở những gì ngăn dùng: `source_id`, `clock`, `t0` (= gốc đồng hồ phát lại, None trước
    `begin()`), `now()` (0 trước `begin()`), `read()`, `last_revolution`, `last_quality`, `describe()`, `stats()`,
    `flush()`, `close()`. Hết bản ghi hay phát lại đã dừng → `ScanStreamEnded` (ngăn tự ngắt), không chặn luồng đọc."""

    def __init__(self, session):
        self.session = session
        self.inner = session.open_lidar()               # ValueError khi bản ghi không có LiDAR
        self.source_id = self.inner.source_id
        self.clock = session.clock
        self.closed = False

    @property
    def t0(self) -> float | None:
        return self.session.origin

    @property
    def last_revolution(self):
        return self.inner.last_revolution

    @property
    def last_quality(self):
        return self.inner.last_quality

    def now(self) -> float:
        origin = self.session.origin
        return 0.0 if origin is None else max(0.0, self.clock() - origin)

    def read(self):
        if self.closed or self.inner.done:
            raise ScanStreamEnded("hết bản ghi phát lại")
        try:
            return self.inner.read()
        except RuntimeError as exc:                     # lỗi đọc đã ghi thì ném lại nguyên văn như lúc ghi
            if END_MESSAGE in str(exc) or STOPPED_MESSAGE in str(exc):
                raise ScanStreamEnded(str(exc)) from exc
            raise

    def describe(self) -> dict:
        return self.inner.describe()

    def stats(self) -> dict:
        return self.inner.stats()

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True
        self.inner.close()


class LidarPointsItem(QGraphicsItem):
    """Điểm phản hồi của vòng quét mới nhất, vẽ trong hệ sa bàn: vàng = dùng được, nâu mờ = bị mặt nạ thân xe bỏ.
    Điểm ngoài sa bàn không vẽ. Mũi tên đứt nét là chỗ đặt LiDAR và hướng nó nhìn. Chỉ để nhìn."""

    def __init__(self, bounds: Bounds, anchor: Pose | None = None):
        super().__init__()
        self.bounds = bounds
        self.anchor = anchor
        self.points = np.zeros((0, 2))
        self.masked = np.zeros((0, 2))
        self.setZValue(2.6)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self) -> QRectF:
        b = self.bounds
        return QRectF(b.xmin - 0.3, b.ymin - 0.3, b.width + 0.6, b.height + 0.6)

    def set_points(self, points: np.ndarray, masked: np.ndarray) -> None:
        self.points, self.masked = points, masked
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.anchor is not None:
            ax, ay, yaw = self.anchor.x, self.anchor.y, self.anchor.yaw
            tip = QPointF(ax + 0.32 * math.cos(yaw), ay + 0.32 * math.sin(yaw))
            painter.setPen(cosmetic_pen(QColor("#ffd166"), 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(ax, ay), tip)
            painter.setPen(cosmetic_pen(QColor("#ffd166"), 1.5))
            for side in (+1, -1):                                   # arrow head, so the heading is unmistakable
                a = yaw + side * math.radians(150)
                painter.drawLine(tip, QPointF(tip.x() + 0.07 * math.cos(a), tip.y() + 0.07 * math.sin(a)))
        if len(self.masked):
            painter.setPen(cosmetic_pen(QColor("#8a6d3b"), 2.5))
            painter.drawPoints(QPolygonF([QPointF(float(x), float(y)) for x, y in self.masked]))
        if len(self.points):
            painter.setPen(cosmetic_pen(QColor("#ffd166"), 3.5))
            painter.drawPoints(QPolygonF([QPointF(float(x), float(y)) for x, y in self.points]))


class LidarDock(QDockWidget):
    def __init__(self, window, *, port: str | None = None, recording: Path | None = None, parent=None):
        """`port` None: ô cổng điền sẵn `lidar_port` của configs/thiet_bi.json; ô để trống lúc kết nối cũng lấy từ đó."""
        super().__init__("LiDAR", parent or window)
        self.window = window
        self.session = window.session
        self.setObjectName("lidarDock")
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.source = None
        self.reader: ScanReader | None = None
        self.queue: queue.Queue = queue.Queue()
        self.recording = recording
        self.grid: GridSpec | None = None
        self.layer: LiveLidarLayer | None = None
        self.bridge: ObstacleBridge | None = None
        self.monitor: FreshnessMonitor | None = None
        self.scan_source_id = ""
        self.anchor: Pose = self.session.scenario.start
        self.scans = 0
        self.periods: deque[float] = deque(maxlen=30)
        self.last_stamp: float | None = None
        self.map_updates = 0
        self.new_on_path = 0
        self.stale_stops = 0
        self.last_error: str | None = None
        self.stale = False
        self.points_item: LidarPointsItem | None = None
        self._scan_arrived = False
        # bản ghi cảm biến (T3): hàm trả bộ ghi hiện hành hay None (ui.lidar_app nối vào SessionSensorRecorder)
        self.record_sink = lambda: None
        self.source_kind: str | None = None       # "live" | "replay" | "other" (nguồn do test hay nơi khác mở)
        self.source_port: str | None = None
        self.source_key: int | None = None        # tăng mỗi lần gắn nguồn: bản ghi biết LiDAR được nối lại
        self.clock_ok, self.clock_why = False, ""
        self._attached = 0
        self.replay_session = None                # T3b: ReplaySession chung với ngăn AI camera (--session-replay)
        # T2: người tiêu thụ vòng quét ở luồng đọc (chung cho mọi ScanReader) và nguồn tư thế để neo vòng quét
        self.scan_consumers: list = []
        self.pose_provider = None
        self._pending: deque = deque()
        self.pose_dropped = 0

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        card = Card("Kết nối")
        try:
            shown = port or configured_lidar_port()
        except LidarPortError:
            shown = ""                  # tệp cấu hình hỏng: ô trống, lỗi hiện khi bấm Kết nối
        self.edit_port = QLineEdit(shown)
        self.edit_port.setPlaceholderText(f"COMx hoặc auto; trống = {CONFIG_PATH.parent.name}/{CONFIG_PATH.name}")
        self.btn_connect = QPushButton("Kết nối")
        self.btn_connect.clicked.connect(self.toggle_connection)
        self.chk_mirror = QCheckBox("Đảo chiều góc")
        self.chk_mirror.toggled.connect(self._set_mirror)
        self.lbl_device = WrapLabel("Chưa kết nối.")
        self.lbl_device.setObjectName("hint")
        self.lbl_rate = QLabel("")
        self.lbl_points = WrapLabel("")
        self.lbl_points.setObjectName("hint")
        self.chk_points = QCheckBox("Hiện điểm LiDAR trên sa bàn")
        self.chk_points.setChecked(True)
        self.chk_points.toggled.connect(self._toggle_points)
        card.add_layout(theme.row(self.edit_port, self.btn_connect))
        card.add(self.chk_mirror, self.lbl_device, self.lbl_rate, self.lbl_points, self.chk_points)
        layout.addWidget(card)

        self.view = ScanView(max_range=4.0, front_up=False)      # cùng hướng sa bàn: phía trước = bên phải
        self.view.setMinimumSize(300, 300)
        layout.addWidget(self.view)
        orientation = WrapLabel("Hình quét xoay cùng hướng sa bàn: phía trước của LiDAR là bên phải, cùng hướng xe ảo. "
                                "Mũi tên vàng trên sa bàn là chỗ đặt và hướng nhìn của LiDAR.")
        orientation.setObjectName("hint")
        layout.addWidget(orientation)

        card = Card("Bản đồ thời gian thực")
        self.chk_live = QCheckBox("Vật cản bám theo LiDAR")
        self.chk_live.setChecked(True)
        self.chk_live.setToolTip("Khi đang chỉnh sa bàn, mỗi vòng quét cập nhật lại các hộp: LiDAR thấy sao, sa bàn vậy")
        self.spin_window = QSpinBox()
        self.spin_window.setRange(1, 10)
        self.spin_window.setValue(3)
        self.spin_window.setSuffix(" vòng gộp")
        self.spin_window.setToolTip("Bản đồ lấy từ bấy nhiêu vòng quét gần nhất")
        self.spin_min_hits = QSpinBox()
        self.spin_min_hits.setRange(1, 10)
        self.spin_min_hits.setValue(2)
        self.spin_min_hits.setSuffix(" lần thấy mới tính")
        self.spin_min_hits.setToolTip("Ô chỉ thành vật cản khi bị chạm ở ít nhất bấy nhiêu vòng trong số vòng gộp")
        self.spin_mask = QSpinBox()
        self.spin_mask.setRange(0, 20)
        self.spin_mask.setValue(10)
        self.spin_mask.setSuffix(" cm quanh xe bỏ")
        self.spin_mask.setToolTip("Bỏ phản hồi trong thân xe cộng lề này: trên bàn là dây cáp, bo adapter; "
                                  "trên xe thật nên nhỏ (3 cm)")
        self.btn_clear = QPushButton("Xóa vật LiDAR")
        self.btn_clear.clicked.connect(self.clear_lidar_obstacles)
        self.lbl_map = WrapLabel("Chưa có vòng quét nào.")
        self.lbl_map.setObjectName("hint")
        card.add(self.chk_live)
        card.add_layout(theme.row(self.spin_window, self.spin_min_hits))
        card.add_layout(theme.row(self.spin_mask, self.btn_clear))
        card.add(self.lbl_map)
        layout.addWidget(card)

        card = Card("Khi xe chạy")
        self.chk_track = QCheckBox("Vật mới trên đường làm xe dừng")
        self.chk_track.setChecked(True)
        self.lbl_track = WrapLabel("Chưa chạy.")
        self.lbl_track.setObjectName("hint")
        card.add(self.chk_track, self.lbl_track)
        layout.addWidget(card)

        self.log = QListWidget()
        self.log.setMaximumHeight(150)
        layout.addWidget(self.log)
        layout.addStretch(1)
        self.setWidget(body)

        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self._refresh_buttons()

    # ---------------------------------------------------------------- helpers
    def say(self, text: str) -> None:
        self.log.addItem(text)
        if self.log.count() > 200:
            self.log.takeItem(0)
        self.log.scrollToBottom()

    def _driving(self) -> bool:
        return self.session.state in DRIVING_STATES

    def _stop_run(self, reason: str, code: str) -> None:
        """The map the car planned on is no longer the map we have: brake and say so. `code` (LIDAR_CONFIG_CHANGED,
        LIDAR_MIRROR_CHANGED, LIDAR_DISCONNECTED) and the source "lidar_dock" go into the session_stop row of
        events.csv when the run goes through VehicleIO (T13, 2026-10-02)."""
        if not self._driving():
            return
        self.stale_stops += 1
        self.say(f"Dừng: {reason}")
        try:
            self.session.request_stop(reason, code=code, source="lidar_dock")
        except SessionError as exc:
            self.say(f"Không dừng được: {exc}")
        self.window._refresh_mode_widgets()
        self.window._refresh_status()

    def _bounds_grid(self) -> GridSpec:
        """Board bounds snapped DOWN to whole cells: a 3.02 m board becomes a 3.00 m grid instead of an error."""
        b: Bounds = self.session.scenario.bounds
        cols = max(1, int((b.xmax - b.xmin) / RESOLUTION_M + 1e-9))
        rows = max(1, int((b.ymax - b.ymin) / RESOLUTION_M + 1e-9))
        return GridSpec(b.xmin, b.xmin + cols * RESOLUTION_M, b.ymin, b.ymin + rows * RESOLUTION_M, RESOLUTION_M)

    def _settings(self) -> tuple:
        window = self.spin_window.value()
        return (self._bounds_grid(), self.spin_mask.value() / 100.0, window, min(self.spin_min_hits.value(), window),
                self._mount())

    def _mount(self) -> tuple[float, float, float]:
        """Gá LiDAR của lớp: theo cấu hình định vị khi có `pose_provider` (T2), không thì (0, 0, 0) như trước."""
        provider = self.pose_provider
        config = getattr(provider, "config", None)
        return config.mount.as_tuple() if config is not None else (0.0, 0.0, 0.0)

    def _ensure_layers(self) -> None:
        """Build the live layer, and rebuild it when the settings or the board change.

        A rebuild empties the scan window, so during a run it would silently change the map the car is driving
        on: there the change is refused until the car stops (the widgets are disabled, this is the backstop).
        """
        grid, mask, window, min_hits, mount = self._settings()
        current = None if self.layer is None else (self.grid, self.layer.mask_margin, self.layer.window,
                                                   self.layer.min_hits, self.layer.mount)
        if current != (grid, mask, window, min_hits, mount):
            if current is not None and self._driving():
                self._stop_run("cấu hình LiDAR đổi trong lúc chạy", "LIDAR_CONFIG_CHANGED")
            self.grid = grid
            self.layer = LiveLidarLayer(grid, mount=mount, window=window, min_hits=min_hits, max_age_s=MAX_AGE_S,
                                        expected_period_s=EXPECTED_PERIOD_S, self_mask=self.session.cfg,
                                        mask_margin=mask)
        if self.bridge is None or self.bridge.session is not self.session:
            self.bridge = ObstacleBridge(self.session, prefix="lidar", path_margin=0.10)

    def _ensure_points_item(self) -> LidarPointsItem:
        item = self.points_item
        try:
            alive = item is not None and item.scene() is self.window.scene
        except RuntimeError:                      # the scene was rebuilt: the C++ item is gone
            alive = False
        if not alive:
            item = LidarPointsItem(self.session.scenario.bounds, self.anchor)
            item.setVisible(self.chk_points.isChecked())
            self.window.scene.addItem(item)
            self.points_item = item
        mount = self.layer.mount if self.layer is not None else (0.0, 0.0, 0.0)
        # T2: có gá (pose_provider) thì mũi tên ở tâm quay LiDAR, không ở tâm trục sau
        item.anchor = self.anchor if mount == (0.0, 0.0, 0.0) else Pose(*sensor_pose_in_map(self.anchor, mount))
        return item

    def _toggle_points(self, on: bool) -> None:
        if self.points_item is not None:
            try:
                self.points_item.setVisible(on)
            except RuntimeError:
                self.points_item = None

    def _set_mirror(self, on: bool) -> None:
        if self.source is None:
            return
        if not hasattr(self.source, "mirror"):
            self.say("Bản ghi đã chốt chiều góc lúc ghi: không đảo được khi phát lại")
            return
        self.source.mirror = on
        self.layer = None                         # the window still holds scans with the old sign: start afresh
        self._pending.clear()
        self._notify_consumers("feed_reset", "đổi chiều góc")
        self._notify_consumers("set_lidar_mirror", on)
        self.say(("Đảo" if on else "Bỏ đảo") + " chiều góc: có hiệu lực từ vòng quét sau")
        if self._driving():
            self._stop_run("chiều góc LiDAR đổi trong lúc chạy", "LIDAR_MIRROR_CHANGED")
        elif self.session.state in EDITABLE_STATES:
            self.clear_lidar_obstacles()

    def _refresh_buttons(self) -> None:
        connected = self.source is not None
        editable = self.session.state in EDITABLE_STATES
        self.btn_connect.setText("Ngắt" if connected else "Kết nối")
        self.edit_port.setEnabled(not connected)
        self.btn_clear.setEnabled(editable and self.bridge is not None and bool(self.bridge.owned()))
        for widget in (self.spin_window, self.spin_min_hits, self.spin_mask, self.chk_mirror):
            widget.setEnabled(not self._driving())   # changing these mid-run would swap the map under the car

    # ---------------------------------------------------------------- scan consumers (T2)
    def add_scan_consumer(self, consumer) -> None:
        """`consumer.on_scan(scan, quality, t_first_perf, t_perf)` được gọi ở LUỒNG ĐỌC cho mỗi vòng quét (cả với
        ScanReader đang chạy: danh sách dùng chung). Đang có nguồn thì báo ngay chiều góc và loại nguồn
        (`feed_kind`)."""
        if consumer not in self.scan_consumers:
            self.scan_consumers.append(consumer)
            mirror = self.lidar_mirror()
            if mirror is not None and hasattr(consumer, "set_lidar_mirror"):
                consumer.set_lidar_mirror(mirror)
            if self.source is not None and hasattr(consumer, "set_feed_kind"):
                consumer.set_feed_kind(self.feed_kind())

    def remove_scan_consumer(self, consumer) -> None:
        if consumer in self.scan_consumers:
            self.scan_consumers.remove(consumer)

    def _notify_consumers(self, name: str, *args) -> None:
        for consumer in list(self.scan_consumers):
            hook = getattr(consumer, name, None)
            if hook is None:
                continue
            try:
                hook(*args)
            except Exception as exc:  # noqa: BLE001 - người tiêu thụ hỏng không được chặn ngắt/đổi chiều
                self.say(f"Lỗi {type(consumer).__name__}.{name}: {exc!r}")

    def feed_kind(self) -> str | None:
        """Loại nguồn ĐANG gắn, cho người tiêu thụ vòng quét (sửa 02/10/2026 sau review gộp đợt 2): "live" chỉ khi là
        driver RPLIDAR C1 do chính ngăn mở (`connect_source`), "recording_replay" (`--recording`: .npz hay thư mục bản
        ghi phiên), "session_replay" (`--session-replay`, T3b), "other" (nguồn do test hay nơi khác gắn), None khi chưa
        nối."""
        source = self.source
        if source is None:
            return None
        if self.source_kind == "live":
            return "live"
        if self.source_kind == "replay":
            return "session_replay" if isinstance(source, DockLidarReplay) else "recording_replay"
        return "other"

    def planned_feed_kind(self) -> str:
        """Nguồn mà "Kết nối" của ngăn sẽ mở: "session_replay" (`replay_session`), "recording_replay" (`recording`) hay
        "live" (cổng COM)."""
        if self.replay_session is not None:
            return "session_replay"
        if self.recording is not None:
            return "recording_replay"
        return "live"

    def lidar_mirror(self) -> bool | None:
        """Chiều góc của nguồn đang nối: cờ của driver, hoặc cờ ghi trong bản ghi phát lại; None khi chưa biết."""
        source = self.source
        if source is None:
            return None
        if hasattr(source, "mirror"):
            return bool(source.mirror)
        meta = getattr(getattr(getattr(source, "replay", None), "recording", None), "meta", None) or {}
        return None if meta.get("mirror") is None else bool(meta.get("mirror"))

    # ---------------------------------------------------------------- connection
    def toggle_connection(self) -> None:
        if self.source is None:
            self.connect_source()
        else:
            self.disconnect_source()

    def attach_source(self, source, *, start_thread: bool = True, kind: str = "other", port: str | None = None) -> None:
        """Use an already opened source (driver, replay or a fake in tests). `kind` (đặt ở MỌI lần gắn, sửa 02/10/2026
        sau review gộp đợt 2): "live" (driver C1 do `connect_source` mở ở cổng `port`), "replay" (bản ghi phát lại) hay
        "other" (mặc định: nguồn do test hay nơi khác gắn, không bao giờ tính là LiDAR thật)."""
        self.source = source
        self._attached += 1
        self.source_key = self._attached
        self.clock_ok, self.clock_why = lidar_clock_ok(source)
        self.source_kind, self.source_port = kind, port
        self.queue = queue.Queue()
        self.scan_source_id = source.source_id
        self.monitor = FreshnessMonitor({source.source_id: SourcePolicy(max_age_s=MAX_AGE_S, expected_period_s=EXPECTED_PERIOD_S)})
        self._ensure_layers()
        if hasattr(source, "mirror"):
            source.mirror = self.chk_mirror.isChecked()
        describe = getattr(source, "describe", None)
        if describe is not None and describe().get("device"):
            device = describe()["device"]
            self.lbl_device.setText(f"Model {device['model_hex']}, firmware {device['firmware']}, serial …{device['serial'][-6:]}")
        else:
            self.lbl_device.setText(f"Nguồn: {source.source_id}")
        self.reader = self._make_reader(source)
        self._notify_consumers("set_feed_kind", self.feed_kind())     # trước vòng quét đầu của nguồn này
        mirror = self.lidar_mirror()
        if mirror is not None:
            self._notify_consumers("set_lidar_mirror", mirror)
        if start_thread:
            self.reader.start()
        self.say("Đã kết nối " + source.source_id)
        self._refresh_buttons()

    def _make_reader(self, source) -> ScanReader:
        """Luồng đọc của nguồn, bọc `LidarTap` (T3): vòng quét chỉ vào bản ghi khi luồng này còn là luồng HIỆN HÀNH của
        ngăn (sau "Ngắt"/kết nối lại, luồng cũ đang thoát không đẩy được gì) và nguồn cùng đồng hồ bàn thử. `self.source`
        vẫn là nguồn gốc (đổi chiều góc vẫn đặt thẳng vào driver)."""
        ok = self.clock_ok
        reader = None

        def sink():
            return self.record_sink() if ok and self.reader is reader else None
        reader = ScanReader(LidarTap(source, sink, RIG_CLOCK, ignore=(ScanStreamEnded,)), self.queue,
                            self.scan_consumers)        # T2: người tiêu thụ ở luồng đọc
        return reader

    def connect_source(self) -> None:
        try:
            if self.replay_session is not None:                             # T3b: cùng đồng hồ với ngăn AI camera
                source = DockLidarReplay(self.replay_session)
                kind, port = "replay", None
            elif self.recording is not None:
                source = PacedReplay(self.recording, clock=RIG_CLOCK)       # .npz hay thư mục bản ghi phiên (T3)
                kind, port = "replay", None
            else:
                from autopark.lidar.rplidar_c1 import RplidarC1Source

                port = lidar_port(self.edit_port.text())
                source = RplidarC1Source.open(port, clock=RIG_CLOCK)       # như rig.bench: cùng đồng hồ với camera
                source.start()
                kind = "live"
        except Exception as exc:  # noqa: BLE001 - mọi lỗi mở cổng phải hiện ra cho người dùng
            self.lbl_device.setText(f"Không kết nối được: {exc}")
            self.say(f"Lỗi kết nối: {exc}")
            return
        self.attach_source(source, kind=kind, port=port)

    def disconnect_source(self) -> None:
        if self._driving():
            self._stop_run("mất LiDAR (ngắt kết nối) trong lúc chạy", "LIDAR_DISCONNECTED")
        if self.reader is not None:
            self.reader.stop_event.set()
        if self.source is not None:
            try:
                self.source.close()
            except Exception as exc:  # noqa: BLE001
                self.say(f"Lỗi khi đóng: {exc}")
        self.source, self.reader = None, None
        self.source_kind, self.source_port = None, None
        self._pending.clear()
        self._notify_consumers("feed_reset", "ngắt LiDAR")
        self._notify_consumers("set_feed_kind", None)
        self.lbl_device.setText("Đã ngắt. Vật cản đang có là ảnh chụp lúc ngắt.")
        self.lbl_rate.setText("")
        self.view.set_scan(None)
        self.say("Đã ngắt LiDAR")
        self._refresh_buttons()

    # ---------------------------------------------------------------- obstacles on the board
    def _scene_add(self, obstacles) -> None:
        for obstacle in obstacles:
            item = ObstacleItem(obstacle, editable=False, on_change=self.window._on_obstacle_item_changed)
            self.window.scene.addItem(item)
            self.window._obstacle_items[obstacle.id] = item

    def _scene_remove(self, obstacles) -> None:
        for obstacle in obstacles:
            item = self.window._obstacle_items.pop(obstacle.id, None)
            if item is not None:
                try:
                    self.window.scene.removeItem(item)
                except RuntimeError:              # the scene was rebuilt under us
                    pass

    def _window_refresh(self) -> None:
        w = self.window
        w._refresh_obstacle_list()
        w._sync_path_items()
        w._refresh_validity()
        w._refresh_mode_widgets()
        w._refresh_status()

    def clear_lidar_obstacles(self) -> None:
        if self.bridge is None or self.session.state not in EDITABLE_STATES:
            return
        owned = self.bridge.owned()
        for obstacle in owned:
            try:
                self.session.remove_obstacle(obstacle.id)
            except SessionError:
                pass
        self._scene_remove(owned)
        self.bridge.seen = []
        self._window_refresh()
        self.lbl_map.setText("Đã xóa vật cản LiDAR.")
        self.say(f"Đã xóa {len(owned)} vật cản LiDAR")
        self._refresh_buttons()

    def _apply_live_map(self, now: float) -> None:
        """While editing: make the board's LiDAR obstacles equal to what the LiDAR says right now."""
        fused = fuse([self.layer], self.grid, now)
        if not fused.valid:
            return
        try:
            added, removed = self.bridge.sync_incremental(fused)
        except (SessionError, RuntimeError) as exc:
            self.say(f"Không cập nhật được vật cản: {exc}")
            return
        self._scene_remove(removed)
        self._scene_add(added)
        counts = count_objects(fused.costmap, bounds=self.session.scenario.bounds)
        self.lbl_map.setText(f"{counts['objects']} vật thể, chia thành {counts['rectangles']} hộp "
                             f"({counts['cells']} ô 5 cm), cập nhật theo từng vòng quét. "
                             "Bấm 'Tìm đường đỗ' để chốt bản đồ rồi lập đường.")
        if added or removed:
            self.map_updates += 1
            self._window_refresh()

    # ---------------------------------------------------------------- per frame
    def _handle_scan(self, scan, quality, t_first, t_perf=None) -> None:
        self.scans += 1
        if self.last_stamp is not None and scan.stamp.t > self.last_stamp:
            self.periods.append(scan.stamp.t - self.last_stamp)
        self.last_stamp = scan.stamp.t
        now = self.source.now()
        if scan.stamp.source_id not in self.monitor.policies:          # stamps are keyed by the scan's own source id
            self.monitor.policies[scan.stamp.source_id] = SourcePolicy(max_age_s=MAX_AGE_S, expected_period_s=EXPECTED_PERIOD_S)
            self.monitor.records[scan.stamp.source_id] = type(self.monitor.records[self.scan_source_id])()
        self.scan_source_id = scan.stamp.source_id
        rejected = self.monitor.observe(scan.stamp, now=now)
        if rejected:
            self.say("Vòng quét bị từ chối: " + ", ".join(e.code for e in rejected))
            return
        if self.pose_provider is not None:
            self.view.set_scan(scan, stale=False)
            if t_perf is None:
                self.pose_dropped += 1                # không có dấu perf: không hỏi được tư thế của vòng này
                self._refresh_points_label()
                return
            self._pending.append((scan, float(t_perf)))
            while len(self._pending) > PENDING_MAX:
                self._pending.popleft()
                self.pose_dropped += 1
            self._resolve_pending()
            return
        self.layer.add_scan(scan, self.anchor)
        self.view.set_scan(scan, stale=False)
        self._show_points(scan)
        self._scan_arrived = True

    def _resolve_pending(self) -> None:
        """T2: vòng chờ → lớp LiveLidar ở tư thế OK của chính vòng đó; vòng "bad" hay chờ quá 0,3 s thì bỏ."""
        now = time.perf_counter()
        while self._pending:
            scan, t_perf = self._pending[0]
            status, pose = self.pose_provider.pose_for_stamp(t_perf)
            if status == "pending" and now - t_perf <= PENDING_MAX_AGE_S:
                return
            self._pending.popleft()
            if status != "ok" or pose is None:
                self.pose_dropped += 1
                self._refresh_points_label()
                continue
            self.anchor = pose
            self.layer.add_scan(scan, pose)
            self._show_points(scan)
            self._scan_arrived = True

    def _show_points(self, scan) -> None:
        """Draw the scan in the map frame and count where its returns went (board / masked / outside)."""
        angles = np.asarray(scan.angles_rad, np.float64)
        ranges = np.asarray(scan.ranges_m, np.float64)
        valid = np.isfinite(ranges)
        filtered = np.isfinite(np.asarray(self.layer.filter_scan(scan).ranges_m, np.float64))
        sx, sy, syaw = sensor_pose_in_map(self.anchor, self.layer.mount)
        x = sx + ranges * np.cos(angles + syaw)
        y = sy + ranges * np.sin(angles + syaw)
        b = self.session.scenario.bounds
        inside = valid & (x >= b.xmin) & (x <= b.xmax) & (y >= b.ymin) & (y <= b.ymax)
        masked = inside & ~filtered
        usable = inside & filtered
        self._ensure_points_item().set_points(np.column_stack([x[usable], y[usable]]), np.column_stack([x[masked], y[masked]]))
        self._points_text = (f"{int(valid.sum())} phản hồi: {int(usable.sum())} trong sa bàn dùng được, "
                             f"{int(masked.sum())} sát xe bị bỏ, {int((valid & ~inside).sum())} ngoài sa bàn")
        self._refresh_points_label()

    def _refresh_points_label(self) -> None:
        """Nhãn điểm LiDAR; có pose_provider (T2) thì thêm số vòng bị bỏ vì chưa có tư thế."""
        self.lbl_points.setText(getattr(self, "_points_text", "")
                                + (f" · bỏ vì chưa có tư thế: {self.pose_dropped} vòng"
                                   if self.pose_provider is not None else ""))

    def tick(self) -> None:
        if self.source is None:
            self._refresh_buttons()
            return
        self._ensure_layers()
        if self.session.state in EDITABLE_STATES and self.pose_provider is None:
            self.anchor = self.session.scenario.start   # the LiDAR sits where the virtual car starts
        self._scan_arrived = False
        while True:
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, Exception):
                self.last_error = f"{type(item).__name__}: {item}"
                self.say(self.last_error)
                if isinstance(item, ScanStreamEnded):
                    self.disconnect_source()
                    return
                continue
            self._handle_scan(*item)
        if self.pose_provider is not None:
            self._resolve_pending()
        now = self.source.now()
        events = self.monitor.check(now)
        stale = any(e.code in ("STALE_DATA", "NO_DATA") for e in events)
        if stale != self.stale:
            self.stale = stale
            if self.view.scan is not None:
                self.view.set_scan(self.view.scan, stale=stale)
        state = self.monitor.status(now)[self.scan_source_id]
        rate = (1.0 / (sum(self.periods) / len(self.periods))) if self.periods else 0.0
        beams = len(self.view.scan.angles_rad) if self.view.scan is not None else 0
        age = "—" if state["age_s"] is None else f"{state['age_s']:.2f} s"
        self.lbl_rate.setText(f"{rate:4.1f} Hz · {beams} tia/vòng · tuổi {age} · " + ("CŨ" if stale else "mới"))
        st = self.session.state
        if st == SessionState.EDITING:
            if self._scan_arrived and self.chk_live.isChecked():
                self._apply_live_map(now)
        elif st == SessionState.RUNNING and self.chk_track.isChecked():
            fused = fuse([self.layer], self.grid, now)
            stops_before = self.bridge.stops
            try:
                added = self.bridge.inject(fused)
            except SessionError as exc:
                self.say(f"Không chèn được vật cản: {exc}")
                added = []
            if self.bridge.stops > stops_before:
                self.stale_stops += 1
                self.say("Dừng: bản đồ LiDAR không dùng được (" + "; ".join(fused.reasons) + ")")
            self._scene_add(added)
            if added:
                self.new_on_path += len(added)
                self.say(f"Vật mới trên đường: {len(added)} → xe dừng")
                self.window._refresh_mode_widgets()
                self.window._refresh_status()
        if st in DRIVING_STATES or self.new_on_path or self.stale_stops:
            self.lbl_track.setText(f"Vật mới trên đường: {self.new_on_path} · ngoài đường (bỏ qua): "
                                   f"{len(self.bridge.seen)} · dừng vì LiDAR: {self.stale_stops}")
        self._refresh_buttons()

    def shutdown(self) -> None:
        self.timer.stop()
        if self.source is not None:
            self.disconnect_source()

    # ---------------------------------------------------------------- bản ghi cảm biến (T3, 02/10/2026)
    def recording_info(self) -> dict | None:
        """Nguồn đang gắn, cho bản ghi cảm biến: None khi chưa kết nối. `source_key` đổi mỗi lần gắn nguồn; `clock_ok`,
        `why`: vòng quét có vào được bản ghi không (`lidar_clock_ok`); `settings`: cấu hình bản đồ LiDAR của ngăn."""
        source = self.source
        if source is None:
            return None
        describe = getattr(source, "describe", None)
        try:
            described = describe() if callable(describe) else None
        except Exception as exc:  # noqa: BLE001
            described = {"error": f"{type(exc).__name__}: {exc}"}
        anchor = self.anchor
        replayed = self.replay_session.folder if self.replay_session is not None else self.recording
        return {"source_key": self.source_key, "source_id": getattr(source, "source_id", None), "kind": self.source_kind,
                "port": self.source_port, "recording": None if self.source_kind != "replay" else str(replayed),
                "describe": described, "clock_ok": self.clock_ok, "why": self.clock_why,
                "settings": {"window": self.spin_window.value(), "min_hits": min(self.spin_min_hits.value(),
                                                                                 self.spin_window.value()),
                             "mask_m": self.spin_mask.value() / 100.0, "mirror": self.chk_mirror.isChecked(),
                             "anchor": [anchor.x, anchor.y, anchor.yaw]}}

    def recording_stats(self) -> dict:
        """Số của ngăn lúc dừng ghi (meta.json lidar_at_stop)."""
        rate = (1.0 / (sum(self.periods) / len(self.periods))) if self.periods else None
        driver = None
        stats = getattr(self.source, "stats", None) if self.source is not None else None
        try:
            driver = stats() if callable(stats) else None
        except Exception as exc:  # noqa: BLE001
            driver = {"error": f"{type(exc).__name__}: {exc}"}
        return {"scans": self.scans, "rate_hz": None if rate is None else round(rate, 3), "last_error": self.last_error,
                "stale_stops": self.stale_stops, "driver": driver}
