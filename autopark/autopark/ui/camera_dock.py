"""Ngăn "AI camera" gắn vào cửa sổ đỗ xe: AI của bốn camera (hay bản ghi phát lại) thành NGUỒN VẬT CẢN thứ hai bên cạnh
LiDAR, theo đúng khuôn của ngăn LiDAR (ui/lidar_dock.py). Tài liệu: docs/AI_DIEU_KHIEN_XE.md (25/09/2026).

Luồng: `rig.core.Rig` (luồng camera + luồng AI, không LiDAR) → timer 50 ms đọc lô AI mới nhất → `fusion.camera_ai.
CameraObstacleMapper` (chặn khi BEV không dùng được, BEV, đặt vào lưới sa bàn, lọc 2/3 lô) → `fuse` → `ObstacleBridge`
riêng tiền tố "camera_ai":

- Đang chỉnh sa bàn (EDITING), "Vật cản bám theo AI" bật: sau mỗi lô dùng được, hộp AI không còn thì bỏ, hộp mới thì thêm
  (`sync_incremental`, chỉ hộp CỦA AI). Planner lập đường tránh chúng. Hộp của LiDAR, của người dùng hay của kịch bản
  không bao giờ bị AI xóa hay sửa: FREE/UNKNOWN của camera không xóa gì ngoài hộp AI của chính nó lúc chỉnh sa bàn.
  Cửa sổ lọc vừa bị xóa (đổi cấu hình, lô bị chặn, khoảng trống > 0,5 s) thì hộp AI được giữ tới khi cửa sổ có đủ
  `min_hits` lô: lô đầu sau khi xóa chưa thể có ô OCCUPIED nào, đó không phải bằng chứng "trống".
- Sẵn sàng (READY): bản đồ giữ cố định để lập đường, như ngăn LiDAR.
- Đang chạy (RUNNING): chỉ THÊM; hộp AI mới chạm hành lang quỹ đạo còn lại (nới 10 cm) → `inject_obstacle` → phiên phát
  MAP_CHANGED và dừng (đường của giai đoạn 0). Hộp mới ngoài hành lang chỉ được ghi nhớ.
- AI cũ (khung cũ nhất của lô mới nhất quá 0,5 s), không có kết quả, bị chặn, hay lỗi bất ngờ khi xử lý lô trong lúc
  chạy: mặc định CẢNH BÁO (mỗi loại một lần trong một lần chạy) và GIỮ vật cản đã có (AI là nguồn phụ, LiDAR vẫn là nguồn
  chính). Chỉ khi người dùng tích "AI bắt buộc" thì làm như ngăn LiDAR với dữ liệu cũ: yêu cầu dừng xe. Lý do chọn: AI
  chưa từng được chấm trên ảnh sa bàn và AI dừng/chậm (GPU bận, bản ghi hết) không được làm hỏng một lần chạy mà LiDAR
  vẫn bảo vệ; ai cần AI như nguồn bắt buộc thì bật rõ ràng (ĐỀ XUẤT – CHỜ CHỐT). Tệp hiệu chuẩn hỏng hay lỗi bất ngờ
  không bao giờ để ngăn giữ Rig mà không có nguồn vật cản: chúng thành lý do chặn, nên "AI bắt buộc" vẫn dừng xe.
- Đổi cấu hình (ngưỡng, cửa sổ lọc, lề thân xe, cách đặt camera) hay nạp lại hiệu chuẩn trong lúc chạy → dừng, vì bản
  đồ đang dùng không còn là bản đồ đã lập đường (các ô bị khóa khi chạy; đây là chốt chặn cuối).

Nguồn: camera thật theo CỔNG HUB (`video.multicam.resolve_ports`), hoặc bản ghi phiên bàn thử (`rig.replay.ReplaySession`,
không mở thiết bị nào). Rig TỔNG HỢP (`--camera-ai-test-rig`) chỉ chạy với bản ghi hay nguồn giả, luôn hiện nhãn TỔNG HỢP,
và bị từ chối với camera thật. torch chỉ được nhập khi bật AI thật (`perception.live`), nên ngăn chạy được trong `.venv`
với nguồn giả.

Chỉ đọc camera, chạy AI và chèn vật cản vào phiên; không có liên hệ tới phần cứng chấp hành. Mức bằng chứng: chỉ kiểm bằng
nguồn giả, bản ghi phát lại của nguồn giả và rig tổng hợp (tests/test_camera_dock_ui.py); CHƯA THỬ với camera thật.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDockWidget, QDoubleSpinBox, QFrame, QLabel, QLineEdit,
                               QListWidget, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from autopark.application.session import EDITABLE_STATES, SessionError, SessionState
from autopark.domain.types import Bounds, Pose
from autopark.fusion import camera_ai
from autopark.fusion.bridge import ObstacleBridge
from autopark.fusion.camera_ai import (AI_MASK_MARGIN_M, AI_MIN_HITS, AI_T_BLOCKED, AI_WINDOW, SOURCE_FAKE, SOURCE_LABELS,
                                       SOURCE_LIVE, SOURCE_REPLAY, CameraObstacleMapper, gate_text)
from autopark.fusion.fuse import fuse
from autopark.fusion.obstacles import count_objects
from autopark.perception import bev
from autopark.perception.costmap import GridSpec
from autopark.ui import theme
from autopark.ui.items import ObstacleItem
from autopark.ui.theme import Card, WrapLabel

RESOLUTION_M = 0.05
DRIVING_STATES = (SessionState.RUNNING, SessionState.STOPPING)
POSE_BENCH, POSE_CAR = 0, 1
POSE_LABELS = ("Camera cố định trên bàn (tại chỗ xuất phát)", "Camera gắn trên xe (theo tư thế xe)")


def parse_ports(text: str) -> list[int]:
    """"1 2 3 4" hay "1,2" → [1, 2, 3, 4]; chữ lạ → ValueError nói rõ."""
    parts = [p for p in str(text).replace(",", " ").split() if p]
    try:
        ports = [int(p) for p in parts]
    except ValueError:
        raise ValueError(f"cổng camera phải là số nguyên, cách nhau bằng dấu cách (nhận {text!r})") from None
    if not ports or any(p < 0 for p in ports) or len(set(ports)) != len(ports):
        raise ValueError(f"cần ít nhất một cổng, không trùng, không âm (nhận {text!r})")
    return ports


def real_segmenter_factory():
    """Hàm tạo bộ phân đoạn thật (LiveSegmenter, cần torch). Nhập muộn: không bật AI thì không nhập torch."""
    from autopark.perception.live import LiveSegmenter

    def make_segmenter(path: str):
        return LiveSegmenter(path)
    return make_segmenter


class CameraAIDock(QDockWidget):
    def __init__(self, window, *, ports=(1, 2, 3, 4), replay: Path | None = None,
                 checkpoint: Path | None = None, calibration_dir: Path | None = None, extrinsics: Path | None = None,
                 roi_dir: Path | None = None, test_rig: bool = False, parent=None):
        super().__init__("AI camera", parent or window)
        self.window = window
        self.session = window.session
        self.setObjectName("cameraAIDock")
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.test_rig = bool(test_rig)
        self.rig = None                          # autopark.rig.core.Rig đang chạy (None: tắt)
        self.source_kind: str | None = None
        self.camera_rig: camera_ai.CameraRig | None = None
        self.mapper: CameraObstacleMapper | None = None
        self.bridge: ObstacleBridge | None = None
        self.grid: GridSpec | None = None
        self._mapper_settings: tuple | None = None
        self.anchor: Pose = self.session.scenario.start
        self.last_update: camera_ai.MapperUpdate | None = None
        self.map_updates = 0
        self.new_on_path = 0
        self.stale_stops = 0
        self.stale_warnings = 0
        self.stale = False
        self._warned_kinds: set[str] = set()      # loại "AI không dùng được" đã cảnh báo trong lần chạy này
        self._last_gate: str | None = None

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.lbl_attribution = WrapLabel(bev.WOODSCAPE_ATTRIBUTION + ". Dùng trong vòng điều khiển theo quyết định "
                                         "25/09/2026 của người làm khóa luận; Valeo chưa xác nhận cách đọc điều khoản "
                                         "(docs/GIAY_PHEP_DU_LIEU.md).")
        self.lbl_attribution.setObjectName("hint")
        layout.addWidget(self.lbl_attribution)
        if self.test_rig:
            self.lbl_synthetic = WrapLabel("RIG TỔNG HỢP (camera ảo, ngoại tham GIẢ ĐỊNH): chỉ để thử phần mềm với bản "
                                           "ghi phát lại. Vật cản AI ở chế độ này KHÔNG phải số đo.")
            self.lbl_synthetic.setStyleSheet(f"color: {theme.DANGER}; font-weight: 600;")
            layout.addWidget(self.lbl_synthetic)
        else:
            self.lbl_synthetic = None

        card = Card("Nguồn")
        self.edit_ports = QLineEdit(" ".join(str(int(p)) for p in ports))
        self.edit_ports.setPlaceholderText("cổng hub, ví dụ 1 2 3 4")
        self.edit_replay = QLineEdit("" if replay is None else str(replay))
        self.edit_replay.setPlaceholderText("thư mục bản ghi phiên (trống = camera thật)")
        self.edit_checkpoint = QLineEdit(str(checkpoint or camera_ai.DEFAULT_CHECKPOINT))
        self.btn_start = QPushButton("Bật AI camera")
        self.btn_start.clicked.connect(self.toggle_ai)
        self.lbl_source = WrapLabel("AI camera đang tắt.")
        self.lbl_source.setObjectName("hint")
        self.lbl_rate = WrapLabel("")
        card.add_layout(theme.row(QLabel("Cổng"), self.edit_ports))
        card.add_layout(theme.row(QLabel("Bản ghi"), self.edit_replay))
        card.add_layout(theme.row(QLabel("Mô hình"), self.edit_checkpoint))
        card.add(self.btn_start, self.lbl_source, self.lbl_rate)
        layout.addWidget(card)

        card = Card("Hiệu chuẩn (bắt buộc)")
        self.edit_calib = QLineEdit(str(calibration_dir or camera_ai.DEFAULT_CALIBRATION_DIR))
        self.edit_extr = QLineEdit(str(extrinsics or (bev.DEFAULT_EXTRINSICS if self.test_rig
                                                      else camera_ai.DEFAULT_EXTRINSICS)))
        self.edit_roi = QLineEdit(str(roi_dir or camera_ai.DEFAULT_ROI_DIR))
        self.btn_reload = QPushButton("Nạp lại hiệu chuẩn")
        self.btn_reload.clicked.connect(self.reload_calibration)
        self.lbl_gate = WrapLabel("Chưa bật.")
        self.lbl_gate.setObjectName("hint")
        card.add_layout(theme.row(QLabel("Nội tham"), self.edit_calib))
        card.add_layout(theme.row(QLabel("Ngoại tham"), self.edit_extr))
        card.add_layout(theme.row(QLabel("ROI"), self.edit_roi))
        card.add(self.btn_reload, self.lbl_gate)
        layout.addWidget(card)

        card = Card("Bản đồ từ AI")
        self.combo_pose = QComboBox()
        self.combo_pose.addItems(POSE_LABELS)
        self.combo_pose.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_pose.setMinimumContentsLength(16)
        self.combo_pose.setToolTip("Bàn thử: camera đứng yên ở chỗ xuất phát (như ngăn LiDAR). Trên xe thật: camera đi "
                                   "theo tư thế xe của phiên")
        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(0.10, 0.95)
        self.spin_threshold.setSingleStep(0.05)
        self.spin_threshold.setDecimals(2)
        self.spin_threshold.setValue(AI_T_BLOCKED)
        self.spin_threshold.setPrefix("vật cản khi P ≥ ")
        self.spin_threshold.setToolTip("0,15 = ngưỡng an toàn chọn trên val WoodScape (HUAN_LUYEN.md mục 10); "
                                       "0,50 = argmax. Chưa kiểm trên sa bàn")
        self.spin_window = QSpinBox()
        self.spin_window.setRange(1, 10)
        self.spin_window.setValue(AI_WINDOW)
        self.spin_window.setSuffix(" lô gộp")
        self.spin_min_hits = QSpinBox()
        self.spin_min_hits.setRange(1, 10)
        self.spin_min_hits.setValue(AI_MIN_HITS)
        self.spin_min_hits.setSuffix(" lần thấy mới tính")
        self.spin_min_hits.setToolTip("Ô chỉ thành vật cản khi OCCUPIED ở ít nhất bấy nhiêu lô trong số lô gộp; không "
                                      "vượt được số lô gộp")
        # ô hiện đúng luật đang dùng: bớt "lô gộp" xuống dưới "lần thấy" thì ô "lần thấy" giảm theo, không kẹp ngầm
        self.spin_min_hits.setMaximum(self.spin_window.value())
        self.spin_window.valueChanged.connect(self.spin_min_hits.setMaximum)
        self.spin_mask = QSpinBox()
        self.spin_mask.setRange(0, 20)
        self.spin_mask.setValue(int(round(AI_MASK_MARGIN_M * 100)))
        self.spin_mask.setSuffix(" cm quanh xe bỏ")
        self.chk_live = QCheckBox("Vật cản bám theo AI")
        self.chk_live.setChecked(True)
        self.chk_live.setToolTip("Khi chỉnh sa bàn, mỗi lô AI dùng được cập nhật lại các hộp AI (chỉ hộp AI)")
        self.btn_clear = QPushButton("Xóa vật AI")
        self.btn_clear.clicked.connect(self.clear_ai_obstacles)
        self.lbl_map = WrapLabel("Chưa có lô AI nào.")
        self.lbl_map.setObjectName("hint")
        card.add(self.combo_pose, self.spin_threshold)
        card.add_layout(theme.row(self.spin_window, self.spin_min_hits))
        card.add_layout(theme.row(self.spin_mask, self.btn_clear))
        card.add(self.chk_live, self.lbl_map)
        layout.addWidget(card)

        card = Card("Khi xe chạy")
        self.chk_track = QCheckBox("Vật mới trên đường làm xe dừng")
        self.chk_track.setChecked(True)
        self.chk_required = QCheckBox("AI bắt buộc (AI cũ thì dừng xe)")
        self.chk_required.setChecked(False)
        self.chk_required.setToolTip("Tắt (mặc định): AI cũ, chưa có hay bị chặn khi xe chạy thì cảnh báo và giữ vật cản "
                                     "đã có. Bật: như LiDAR — dừng xe")
        self.lbl_track = WrapLabel("Chưa chạy.")
        self.lbl_track.setObjectName("hint")
        card.add(self.chk_track, self.chk_required, self.lbl_track)
        layout.addWidget(card)

        self.log = QListWidget()
        self.log.setMaximumHeight(150)
        layout.addWidget(self.log)
        layout.addStretch(1)
        scroll = QScrollArea()                    # ngăn cao hơn cửa sổ 960 px: cuộn thay vì cắt mất thẻ "Khi xe chạy"
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        self.setWidget(scroll)

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

    def _now(self) -> float:
        return self.rig.clock()

    def _stop_run(self, reason: str) -> None:
        if not self._driving():
            return
        self.stale_stops += 1
        self.say(f"Dừng: {reason}")
        try:
            self.session.request_stop(reason)
        except SessionError as exc:
            self.say(f"Không dừng được: {exc}")
        self.window._refresh_mode_widgets()
        self.window._refresh_status()

    def _bounds_grid(self) -> GridSpec:
        """Như ngăn LiDAR: biên sa bàn làm tròn XUỐNG theo ô 5 cm."""
        b: Bounds = self.session.scenario.bounds
        cols = max(1, int((b.xmax - b.xmin) / RESOLUTION_M + 1e-9))
        rows = max(1, int((b.ymax - b.ymin) / RESOLUTION_M + 1e-9))
        return GridSpec(b.xmin, b.xmin + cols * RESOLUTION_M, b.ymin, b.ymin + rows * RESOLUTION_M, RESOLUTION_M)

    def _settings(self) -> tuple:
        window = self.spin_window.value()
        return (self._bounds_grid(), round(self.spin_threshold.value(), 4), window,
                min(self.spin_min_hits.value(), window), self.spin_mask.value() / 100.0, self.combo_pose.currentIndex(),
                self.session.cfg)

    def _vehicle_pose(self) -> Pose:
        """Chỗ đặt hệ xe của BEV trong hệ sa bàn. Cố định trên bàn: tư thế xuất phát lúc còn chỉnh sa bàn, giữ nguyên khi
        chạy (như ngăn LiDAR). Trên xe: tư thế xe của phiên (mô phỏng, hay thế giới gương của VehicleIO)."""
        if self.combo_pose.currentIndex() == POSE_CAR and self.session.world is not None \
                and self.session.state not in EDITABLE_STATES:
            return self.session.world.state.pose
        return self.anchor

    def _load_camera_rig(self, rig=None, *, ports=None, size=None) -> camera_ai.CameraRig:
        """Rig camera từ các ô hiệu chuẩn, cho cổng và cỡ khung của `rig` (mặc định rig đang chạy), hay cho `ports`/`size`
        cho sẵn. Không bao giờ ném: lỗi bất ngờ thành rig rỗng có lý do chặn (nguồn vật cản chặn mọi lô)."""
        try:
            if ports is None:
                rig = self.rig if rig is None else rig
                ports = [int(s.port) for s in rig.cams.specs]
                size = (int(rig.cfg.width), int(rig.cfg.height))
            if self.test_rig:
                return camera_ai.synthetic_camera_rig(ports, size, extrinsics=Path(self.edit_extr.text().strip()))
            return camera_ai.load_camera_rig(ports, size, extrinsics=Path(self.edit_extr.text().strip()),
                                             calibration_dir=Path(self.edit_calib.text().strip()),
                                             roi_dir=Path(self.edit_roi.text().strip()))
        except Exception as exc:  # noqa: BLE001 - lỗi nạp không được để ngăn giữ Rig mà không có nguồn vật cản
            return camera_ai.CameraRig({}, None, self.test_rig,
                                       (f"không nạp được rig camera ({type(exc).__name__}: {exc})",), "lỗi nạp")

    def _ensure_mapper(self) -> None:
        """Dựng nguồn vật cản, và dựng lại khi cấu hình, sa bàn hay rig camera đổi. Dựng lại xóa cửa sổ lọc nên đổi bản đồ
        đang chạy: trong lúc xe chạy thì yêu cầu dừng (các ô bị khóa khi chạy; đây là chốt chặn cuối)."""
        if self.rig is None or self.camera_rig is None:
            return
        settings = self._settings()
        current = None if self.mapper is None else self._mapper_settings
        if current != settings or self.mapper.rig is not self.camera_rig:
            if self.mapper is not None and self._driving():
                self._stop_run("cấu hình AI camera đổi trong lúc chạy")
            grid, t_blocked, window, min_hits, mask, _, cfg = settings
            t_free = min(camera_ai.AI_T_FREE, t_blocked / 2)
            self.mapper = CameraObstacleMapper(self.camera_rig, grid, source_kind=self.source_kind, vehicle_cfg=cfg,
                                               t_free=t_free, t_blocked=t_blocked, window=window, min_hits=min_hits,
                                               mask_margin=mask)
            self._mapper_settings = settings
            self.grid = grid
            if not self.mapper.blocked:
                ms = self.mapper.warm_up()
                self.say(f"Dựng bảng hình học BEV: {ms:.0f} ms")
        if self.bridge is None or self.bridge.session is not self.session:
            self.bridge = ObstacleBridge(self.session, prefix=camera_ai.SOURCE_ID, path_margin=0.10)

    def _refresh_buttons(self) -> None:
        on = self.rig is not None
        editable = self.session.state in EDITABLE_STATES
        self.btn_start.setText("Tắt AI camera" if on else "Bật AI camera")
        for widget in (self.edit_ports, self.edit_replay, self.edit_checkpoint):
            widget.setEnabled(not on)
        self.btn_clear.setEnabled(editable and self.bridge is not None and bool(self.bridge.owned()))
        for widget in (self.spin_threshold, self.spin_window, self.spin_min_hits, self.spin_mask, self.combo_pose,
                       self.btn_reload, self.edit_calib, self.edit_extr, self.edit_roi):
            widget.setEnabled(not self._driving())       # đổi giữa lần chạy là đổi bản đồ dưới bánh xe

    # ---------------------------------------------------------------- bật / tắt
    def toggle_ai(self) -> None:
        if self.rig is None:
            self.start_ai()
        else:
            self.stop_ai()

    def start_ai(self, make_segmenter=None) -> bool:
        """Dựng Rig từ các ô (bản ghi nếu có, không thì camera thật theo cổng) rồi bật. `make_segmenter`: None = bộ phân
        đoạn thật (cần torch); test truyền bộ giả. Rig tổng hợp mà không có bản ghi → từ chối, KHÔNG mở camera nào."""
        from autopark.rig.core import Rig, RigConfig
        from autopark.video.multicam import MultiCameraManager

        if self.rig is not None:
            return True
        try:
            ports = parse_ports(self.edit_ports.text())
        except ValueError as exc:
            self.say(f"Lỗi cổng: {exc}")
            self.lbl_source.setText(str(exc))
            return False
        replay_text = self.edit_replay.text().strip()
        if self.test_rig and not replay_text:
            message = ("Từ chối: rig TỔNG HỢP chỉ chạy với bản ghi phát lại, không bao giờ với camera thật "
                       "(điền ô 'Bản ghi' hoặc bỏ --camera-ai-test-rig)")
            self.say(message)
            self.lbl_source.setText(message)
            return False
        checkpoint = self.edit_checkpoint.text().strip()
        if make_segmenter is None:
            if importlib.util.find_spec("torch") is None:
                message = "AI camera cần torch: chạy bằng .venv-train\\Scripts\\python.exe"
                self.say(message)
                self.lbl_source.setText(message)
                return False
            if not Path(checkpoint).is_file():
                message = f"Không có tệp mô hình {checkpoint}"
                self.say(message)
                self.lbl_source.setText(message)
                return False
            make_segmenter = real_segmenter_factory()
        try:
            if replay_text:
                from autopark.rig.replay import ReplaySession

                session = ReplaySession(Path(replay_text), ports=ports)
                mode = session.camera_mode()
                width, height = int(mode.get("width") or 640), int(mode.get("height") or 480)
                cams = MultiCameraManager(session.camera_specs(), width=width, height=height,
                                          fps=mode.get("fps") or 30.0, fourcc=mode.get("fourcc") or "MJPG",
                                          open_source=session.open_camera)
                cfg = RigConfig(width=width, height=height, checkpoint=checkpoint,
                                notes={"camera_ai": "phát lại", "replay": replay_text})
                rig = Rig(cams, cfg, make_segmenter=make_segmenter, replay=session)
                kind = SOURCE_REPLAY
            else:
                from autopark.video.multicam import resolve_ports

                cams = MultiCameraManager(resolve_ports(ports), width=640, height=480, fps=30.0, fourcc="MJPG")
                rig = Rig(cams, RigConfig(checkpoint=checkpoint, notes={"camera_ai": "camera thật"}),
                          make_segmenter=make_segmenter)
                kind = SOURCE_LIVE
        except Exception as exc:  # noqa: BLE001 - mọi lỗi mở nguồn phải hiện ra cho người dùng
            self.say(f"Không bật được AI camera: {exc}")
            self.lbl_source.setText(f"Không bật được: {exc}")
            return False
        self.attach_rig(rig, kind)
        return True

    def attach_rig(self, rig, source_kind: str, *, start: bool = True) -> None:
        """Dùng một Rig đã dựng (camera thật, phát lại, hay nguồn giả trong test); `source_kind` nói nó là gì — rig tổng
        hợp bị từ chối khi "live". Dựng bảng hình học BEV trước khi rig chạy."""
        if source_kind not in camera_ai.SOURCE_KINDS:
            raise ValueError(f"source_kind phải là một trong {camera_ai.SOURCE_KINDS}")
        if self.rig is not None:
            self.stop_ai()                      # một rig tại một thời điểm
        camera_rig = self._load_camera_rig(rig)  # không ném; nạp TRƯỚC khi nhận rig
        self.rig, self.source_kind = rig, source_kind
        self.camera_rig = camera_rig
        self.mapper = None
        self.last_update = None
        self._last_gate = None
        try:
            self._ensure_mapper()
        except Exception as exc:  # noqa: BLE001 - tick() dựng lại và coi lỗi là "AI không dùng được"
            self.say(f"Lỗi dựng nguồn vật cản AI ({type(exc).__name__}: {exc})")
        text = f"Nguồn: {SOURCE_LABELS[source_kind]}, cổng {[s.port for s in rig.cams.specs]}, mô hình {rig.cfg.checkpoint}"
        if self.camera_rig.synthetic:
            text += " — RIG TỔNG HỢP"
        self.lbl_source.setText(text)
        self.say("Bật AI camera: " + text)
        if self.mapper is not None and self.mapper.blocked:
            self._last_gate = gate_text(self.mapper.static_reasons)
            self.say(self._last_gate)
            self.lbl_gate.setText(self._last_gate)
        if start:
            rig.start()
        self._refresh_buttons()

    def stop_ai(self) -> None:
        """Tắt AI camera. Vật cản AI đang có được giữ (ảnh chụp lúc tắt). Trong lúc chạy: dừng xe nếu "AI bắt buộc"."""
        if self.rig is None:
            return
        if self._driving():
            if self.chk_required.isChecked():
                self._stop_run("tắt AI camera trong lúc chạy (AI bắt buộc)")
            else:
                self.say("Tắt AI camera trong lúc chạy: giữ vật cản đã có (AI không bắt buộc)")
        rig, self.rig = self.rig, None
        alive = rig.stop()
        if alive:
            self.say("Luồng chưa dừng: " + ", ".join(alive))
        self.lbl_source.setText("Đã tắt. Vật cản AI đang có là ảnh chụp lúc tắt.")
        self.lbl_rate.setText("")
        self.say("Đã tắt AI camera")
        self._refresh_buttons()

    def reload_calibration(self) -> None:
        """Đọc lại tệp hiệu chuẩn (không khi xe chạy). AI đang bật: dựng lại nguồn vật cản với tệp mới. AI đang tắt: chỉ
        KIỂM tệp cho các cổng của ô "Cổng" ở cỡ 640×480 (mode chạy bốn camera) và hiện lý do chặn biết trước — không mở
        camera nào, không dựng Rig."""
        if self._driving():
            return
        if self.rig is None:
            try:
                ports = parse_ports(self.edit_ports.text())
            except ValueError as exc:
                text = f"Lỗi cổng: {exc}"
            else:
                size = (640, 480)
                checked = self._load_camera_rig(ports=ports, size=size)
                kind = SOURCE_REPLAY if self.edit_replay.text().strip() else SOURCE_LIVE
                reasons = camera_ai.preflight_reasons(checked, kind)
                text = gate_text(reasons) if reasons else (
                    f"Hiệu chuẩn đọc được và đạt cho camera {checked.ports} ở {size[0]}×{size[1]} (AI đang tắt; khi bật, "
                    f"từng lô AI vẫn được kiểm lại)")
                if checked.synthetic and not reasons:
                    text = "RIG TỔNG HỢP: " + text
            self.lbl_gate.setText(text)
            self.say("Kiểm hiệu chuẩn (AI đang tắt): " + text)
            return
        self.camera_rig = self._load_camera_rig()
        self.say("Nạp lại hiệu chuẩn: " + self.camera_rig.description)
        try:
            self._ensure_mapper()
        except Exception as exc:  # noqa: BLE001 - tick() dựng lại và coi lỗi là "AI không dùng được"
            self.say(f"Lỗi dựng nguồn vật cản AI ({type(exc).__name__}: {exc})")

    # ---------------------------------------------------------------- vật cản trên sa bàn
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
                except RuntimeError:              # cảnh đã được dựng lại
                    pass

    def _window_refresh(self) -> None:
        w = self.window
        w._refresh_obstacle_list()
        w._sync_path_items()
        w._refresh_validity()
        w._refresh_mode_widgets()
        w._refresh_status()

    def clear_ai_obstacles(self) -> None:
        """Xóa mọi hộp của AI (chỉ hộp tiền tố camera_ai; hộp LiDAR và hộp người dùng giữ nguyên)."""
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
        self.lbl_map.setText("Đã xóa vật cản AI.")
        self.say(f"Đã xóa {len(owned)} vật cản AI")
        self._refresh_buttons()

    def _apply_live_map(self, now: float) -> None:
        """Đang chỉnh sa bàn: hộp AI = những gì AI (sau lọc) đang thấy. Chỉ hộp của AI bị thêm/bớt."""
        fused = fuse([self.mapper.layer], self.grid, now, source_id=camera_ai.SOURCE_ID)
        if not fused.valid:
            return
        try:
            added, removed = self.bridge.sync_incremental(fused)
        except (SessionError, RuntimeError) as exc:
            self.say(f"Không cập nhật được vật cản AI: {exc}")
            return
        self._scene_remove(removed)
        self._scene_add(added)
        counts = count_objects(fused.costmap, bounds=self.session.scenario.bounds)
        self.lbl_map.setText(f"{counts['objects']} vật thể từ AI, chia thành {counts['rectangles']} hộp "
                             f"({counts['cells']} ô 5 cm). Bấm 'Tìm đường đỗ' để chốt bản đồ rồi lập đường.")
        if added or removed:
            self.map_updates += 1
            self._window_refresh()

    def _inject(self, now: float) -> None:
        fused = fuse([self.mapper.layer], self.grid, now, source_id=camera_ai.SOURCE_ID)
        try:
            added = self.bridge.inject(fused)
        except SessionError as exc:
            self.say(f"Không chèn được vật cản AI: {exc}")
            added = []
        self._scene_add(added)
        if added:
            self.new_on_path += len(added)
            self.say(f"Vật mới từ AI trên đường: {len(added)} → xe dừng")
            self.window._refresh_mode_widgets()
            self.window._refresh_status()

    def _unusable_while_driving(self, kind: str, why: str) -> None:
        """AI cũ / chưa có / bị chặn / lỗi trong lúc chạy: dừng nếu 'AI bắt buộc', không thì cảnh báo MỘT lần cho mỗi loại
        trong một lần chạy (`kind`: "blocked", "none", "stale", "error" — không theo chữ, vì tuổi trong chữ đổi mỗi nhịp;
        AI cũ rồi mới lại rồi cũ lại không cảnh báo lần hai, dòng trạng thái vẫn hiện "CŨ") và giữ vật cản."""
        if self.chk_required.isChecked():
            self._stop_run(f"AI camera không dùng được ({why}) và 'AI bắt buộc' đang bật")
            return
        if kind not in self._warned_kinds:
            self._warned_kinds.add(kind)
            self.stale_warnings += 1
            self.say(f"Cảnh báo: AI camera không dùng được ({why}); giữ vật cản đã có, xe vẫn chạy (AI không bắt buộc)")

    # ---------------------------------------------------------------- nhịp
    def _show_status(self, now: float, upd) -> None:
        mapper = self.mapper
        age = mapper.age(now)
        ai = self.rig.ai.stats(now) if self.rig.ai is not None else None
        parts = []
        if ai is None:
            parts.append("AI không có (thiếu mô hình)")
        elif ai["load_error"]:
            parts.append(f"lỗi nạp mô hình: {ai['load_error']}")
        elif ai["model"] is None:
            parts.append("đang nạp mô hình…")
        else:
            parts.append(f"AI {ai['sets_per_s_last3s']:.1f} lô/s")
        parts.append(f"dùng {mapper.rate():.1f} lô/s")
        parts.append("tuổi —" if age is None else f"tuổi {age:.2f} s")
        parts.append("CŨ" if self.stale else "mới")
        if upd is not None and upd.bev_ms is not None:
            parts.append(f"BEV {upd.bev_ms:.0f} ms")
        replay = self.rig.replay_status()
        if replay is not None:
            parts.append(f"phát lại {replay['position_s']}/{replay['duration_s']} s"
                         + (" HẾT BẢN GHI" if replay["finished"] else ""))
        self.lbl_rate.setText(" · ".join(str(p) for p in parts))
        if upd is None or (not upd.reasons and not upd.processed and mapper.batches == 0):
            gate = "Chưa có lô AI nào." if not mapper.blocked else gate_text(mapper.static_reasons)
        elif upd.reasons:
            gate = upd.gate_text()
        else:
            used = ", ".join(upd.cameras_used) or "—"
            gate = f"BEV dùng được: camera {used}; {len(self.bridge.owned())} hộp AI trên sa bàn"
            if self.camera_rig.synthetic:
                gate = camera_ai.SYNTHETIC_NOTE + ". " + gate
        if upd is not None and upd.notes:
            extra = [n for n in upd.notes if n != camera_ai.SYNTHETIC_NOTE]
            if extra:
                gate += " (" + "; ".join(extra[:3]) + ")"
        self.lbl_gate.setText(gate)
        if upd is not None and upd.reasons:                   # ghi log mỗi khi lý do chặn đổi, không lặp mỗi nhịp
            text = upd.gate_text()
            if text != self._last_gate:
                self.say(text)
            self._last_gate = text
        elif upd is not None and upd.usable:
            self._last_gate = None

    def tick(self) -> None:
        if self.rig is None:
            self._refresh_buttons()
            return
        if self.session.state in EDITABLE_STATES:
            self.anchor = self.session.scenario.start      # camera trên bàn đứng ở chỗ xe ảo xuất phát
            self._warned_kinds.clear()                     # lần chạy sau cảnh báo lại từ đầu
        try:
            self._ensure_mapper()
            result = self.rig.ai.result() if self.rig.ai is not None else None
            # đồng hồ đọc SAU khi lấy lô: lô được công bố trước khi result() trả về và mọi stamp của nó ≤ t_done ≤ now
            # (cùng đồng hồ bàn thử), nên tuổi không bao giờ âm dù luồng giao diện đứng giữa hai dòng (như ngăn LiDAR)
            now = self._now()
            upd = self.mapper.update(result, self._vehicle_pose(), now)
        except Exception as exc:  # noqa: BLE001 - lỗi bất ngờ = "AI không dùng được", không làm hỏng timer
            why = f"lỗi xử lý AI camera ({type(exc).__name__}: {exc})"
            if why != self._last_gate:
                self.say(why)
                self._last_gate = why
            self.lbl_gate.setText(gate_text([why]))
            if self.session.state == SessionState.RUNNING:
                self._unusable_while_driving("error", why)
            self._refresh_buttons()
            return
        self.last_update = upd
        stale = not self.mapper.fresh(now)
        if stale != self.stale:
            self.stale = stale
        st = self.session.state
        if st == SessionState.EDITING:
            if upd.processed and upd.usable and self.chk_live.isChecked():
                # cửa sổ lọc vừa xóa (đổi cấu hình/dựng lại, lô bị chặn, khoảng trống > max_age_s): chưa đủ min_hits lô
                # thì không ô nào có thể OCCUPIED — đó không phải bằng chứng "trống", nên giữ hộp AI tới khi đủ lô
                if upd.window_fill >= self.mapper.min_hits:
                    self._apply_live_map(now)
                else:
                    self.lbl_map.setText(f"Cửa sổ lọc đang đầy lại ({upd.window_fill}/{self.mapper.min_hits} lô): "
                                         "giữ hộp AI đã có.")
        elif st == SessionState.RUNNING:
            if self.mapper.blocked or upd.reasons:
                self._unusable_while_driving("blocked", "bị chặn: " + "; ".join(upd.reasons or self.mapper.static_reasons))
            elif stale:
                age = self.mapper.age(now)
                if age is None:
                    self._unusable_while_driving("none", "chưa có kết quả")
                else:
                    self._unusable_while_driving("stale", f"quá cũ: {age:.2f} s > {self.mapper.max_age_s:g} s")
            elif upd.processed and self.chk_track.isChecked():
                self._inject(now)
        self._show_status(now, upd)                        # sau khi đồng bộ/chèn: số hộp AI hiện là số mới
        if st in DRIVING_STATES or self.new_on_path or self.stale_stops or self.stale_warnings:
            self.lbl_track.setText(f"Vật mới từ AI trên đường: {self.new_on_path} · ngoài đường (bỏ qua): "
                                   f"{len(self.bridge.seen)} · dừng vì AI: {self.stale_stops} · "
                                   f"cảnh báo AI không dùng được: {self.stale_warnings}")
        self._refresh_buttons()

    def shutdown(self) -> None:
        self.timer.stop()
        if self.rig is not None:
            self.stop_ai()


__all__ = ["CameraAIDock", "parse_ports", "real_segmenter_factory", "SOURCE_FAKE", "SOURCE_LIVE", "SOURCE_REPLAY"]
