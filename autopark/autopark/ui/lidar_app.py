"""Cửa sổ thao tác gần kèm ngăn LiDAR thật (bàn thử giai đoạn 1–3).

    python -m autopark.ui.lidar_app
    python -m autopark.ui.lidar_app --recording runs/lidar_bench/20260922/p07_nen_phong.npz
    python -m autopark.ui.lidar_app --scenario scenarios/sa_ban_3x2_hai_hop.json
    python -m autopark.ui.lidar_app --vehicle-config configs/vehicle_measured.json
    python -m autopark.ui.lidar_app --max-cusps 2

Số lần đổi chiều (T12, 02/10/2026): `--max-cusps N` từ chối Bắt đầu đỗ khi đường có hơn N lần đổi chiều (mặc định không
chặn, giới hạn CHƯA CHỐT), `--warn-cusps N` cảnh báo khi hơn N (mặc định 7), như `run_app.py`; giữ cả khi "Mở kịch bản".
Như `run_app.py` (02/10/2026): tệp sa bàn có trường `acceptance` dùng giới hạn của kịch bản nghiệm thu đó trong
configs/nguong_nghiem_thu.json (ĐỀ XUẤT – CHỜ CHỐT), cờ chỉ siết thêm; `--scenario` gắn thẻ mà tệp ngưỡng không cho được
giới hạn thì báo lỗi, thoát mã 2 trước khi mở cửa sổ hay LiDAR.

Cổng LiDAR: không có `--port` thì lấy `lidar_port` trong configs/thiet_bi.json (đổi máy chỉ sửa tệp đó, 29/09/2026;
autopark/lidar/port.py); `--port COMx` ghi đè cho một lần chạy.

Cấu hình xe: không có `--vehicle-config` thì như cũ (sa bàn mặc định dùng configs/vehicle_default.json, GIẢ ĐỊNH –
CHƯA ĐO; `--scenario` dùng tệp xe mà kịch bản trỏ tới). Có `--vehicle-config` thì tệp đó thay cho cả hai, và vẫn giữ
khi mở kịch bản khác bằng nút "Mở kịch bản" trong cửa sổ (không dùng tệp xe của kịch bản đó; thanh trạng thái báo
điều này). Tệp hỏng thì báo lỗi và thoát trước khi mở cửa sổ hay cổng COM. Chỉ kiểm bằng test offscreen (không mở cổng
COM, 24/09/2026); CHƯA THỬ với LiDAR thật. Từ 02/10/2026 việc giữ xe nằm ở MainWindow, chung với `run_app.py
--vehicle-config` và ô "Cấu hình xe" của thẻ Xe; bo mô phỏng chọn theo tệp xe (xe nghiệm thu:
configs/vehicle_nghiem_thu.json).

Mặc định mở sa bàn 3 × 2 m trống, xe ở (0,5; 1,0) hướng +x, đích ở (2,0; 1,0). Trình tự trên màn hình:
Kết nối → vật cản LiDAR hiện ngay và bám theo cảm biến → Tìm đường đỗ (chốt bản đồ) → Bắt đầu đỗ → đưa tay vào trước LiDAR
để thấy xe ảo dừng (MAP_CHANGED). Ngăn LiDAR ở bên phải, kéo ra được. Dấu đồng bộ video–log cho video R3 (T14,
02/10/2026): nút "Dấu đồng bộ · F8" hay phím F8 như ở `ui.app`, trước Bắt đầu đỗ và sau khi xe dừng; tệp
runs/sync_marks/<giờ>_ui_lidar_app.csv (chỉ kiểm offscreen).

AI camera làm nguồn vật cản thứ hai (thêm 25/09/2026, docs/KIEN_TRUC.md; cần .venv-train vì AI dùng torch):

    .venv-train\\Scripts\\python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --cam-ports 1 2 3 4
    .venv-train\\Scripts\\python.exe -X utf8 -m autopark.ui.lidar_app --no-connect --camera-ai --cam-replay runs/rig_recordings/<phiên>
    .venv-train\\Scripts\\python.exe -X utf8 -m autopark.ui.lidar_app --no-connect --camera-ai --cam-replay runs/rig_recordings/<phiên> --camera-ai-test-rig

Tùy chọn khác: `--checkpoint` (mặc định runs/ai_woodscape_rtx4000_v1/best.pt), `--calibration-dir` (calibration),
`--extrinsics` (configs/rig/camera_rig_extrinsics_v1.json), `--roi-dir` (configs/roi/rig_v1). AI chỉ tạo vật cản khi BEV
dùng được (nội tham đạt + ngoại tham đo + ROI, không tổng hợp); tới 25/09/2026 chưa camera nào được hiệu chuẩn nên trên
bàn thật AI chỉ hiện lý do bị chặn. `--camera-ai-test-rig` (rig TỔNG HỢP) chỉ nhận cùng `--cam-replay`. Các tùy chọn
camera không đi kèm `--camera-ai` bị từ chối. Không có `--camera-ai` thì cửa sổ như trước, không nhập torch hay ngăn
camera (chạy được trong .venv). `--no-connect` không mở LiDAR và không bật camera thật (bấm "Bật AI camera" trong ngăn);
AI từ `--cam-replay` thì luôn tự bật vì không mở thiết bị nào. `--cam-replay` chỉ cấp ảnh camera; LiDAR của cùng bản ghi
phát lại được bằng `--recording <thư mục>` (02/10/2026), nhưng hai ngăn bắt đầu phát lại ở hai lúc khác nhau (LiDAR lúc
kết nối, camera khi AI nạp xong) nên KHÔNG cùng một cảnh theo thời gian. Muốn cùng một cảnh thì dùng `--session-replay
<thư mục>` (T3b, 02/10/2026): MỘT ReplaySession cho cả hai ngăn, một đồng hồ phát lại (bắt đầu khi AI nạp xong; không có
`--camera-ai` thì ngay khi gắn LiDAR); không dùng cùng `--recording`, `--cam-replay`, `--port`; luôn tự bật vì không mở
thiết bị nào; phát lại chỉ một lần (tắt AI camera là dừng phát lại cho cả hai ngăn). Chỉ kiểm offscreen.

    .venv-train\\Scripts\\python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --session-replay runs/session_recordings/<thư mục>

Ghi cảm biến trong phiên đỗ (T3, 02/10/2026; docs/VAN_HANH.md): ngăn "Ghi cảm biến" (thẻ cạnh ngăn LiDAR) ghi
mọi khung tốt của camera ở ngăn AI camera và mọi vòng quét của ngăn LiDAR vào runs/session_recordings/<ngày_giờ>_<tên>/,
cùng đồng hồ perf_counter với log VehicleIO và dấu đồng bộ (mốc ở session/clock.csv); không gửi gì tới bo, không dừng hay
chặn xe; "Bắt đầu ghi" khóa khi xe đang chạy. "Xuất log CSV…" ghi thêm <tên>_sensor_recordings.json trỏ tới các bản ghi.
Đóng cửa sổ (sửa 02/10/2026 sau review gộp đợt 2): dừng ghi, rồi dừng xe (enable=0 + DISARM qua liên kết, tắt bo ảo
QEMU) TRƯỚC khi tắt các ngăn và chờ bản ghi ghi nốt (tối đa 60 s). meta.json ghi bo đang chọn ("sim", "qemu" hay cổng
COM) và giới hạn đổi chiều có hiệu lực (gộp kịch bản nghiệm thu).

    python -m autopark.ui.lidar_app --record-root runs/session_recordings --record-format jpg --jpeg-quality 95
    python -m autopark.ui.lidar_app --recording runs/session_recordings/<thư mục>     (mọi phần LiDAR của bản ghi)

`--record-min-free-gb` (mặc định 5, phải > 2 = ngưỡng tự dừng; ĐỀ XUẤT – CHỜ CHỐT): không bắt đầu ghi khi ổ còn ít hơn.
Tùy chọn ghi sai bị từ chối (mã 2) trước khi mở cửa sổ hay thiết bị. Chỉ kiểm offscreen với nguồn giả; CHƯA THỬ với
camera và LiDAR thật.

EcoQoS (02/10/2026): như `ui.app`, `main()` tự tắt EcoQoS cho tiến trình này trước mọi việc khác và hiện trạng thái ở
thanh trạng thái; AUTOPARK_KEEP_ECOQOS=1 giữ mặc định của Windows (autopark/power_throttling.py).

Nguồn tư thế LiDAR (T2, 02/10/2026; application/lidar_pose_source.py, chỉ kiểm offscreen với nguồn giả):

    python -m autopark.ui.lidar_app --pose-source lidar_real --lidar-map runs/lidar_maps/<ngay>_<ten>
    python -m autopark.ui.lidar_app --pose-source lidar_sim

`--pose-source {sim_truth,lidar_sim,lidar_real}` chọn sẵn ô "Nguồn tư thế" của thẻ Bo điều khiển; `--lidar-map` nạp bản
đồ của `autopark.lidar.map_builder` (phải ở hệ sa bàn, "session_ready"); `--lidar-config` thay configs/dinh_vi_lidar_v0.json.
Kiểm trước khi mở cửa sổ hay cổng nào: lidar_real thiếu bản đồ, bản đồ hỏng hay không ở hệ sa bàn, cấu hình hỏng →
thoát mã 2. Với "LiDAR thật", cửa sổ giữ một `LidarPoseSource` nhận vòng quét của ngăn LiDAR (luồng "dinh_vi_lidar"),
ngăn LiDAR neo vòng quét ở tư thế định vị được; bo COM ở VehicleIO vẫn bị từ chối (START_POSE_UNVERIFIED) tới khi gá
LiDAR được đo và đạt p04, DV-2, DV-1. CHƯA THỬ với LiDAR gá trên xe chạy và với bo thật. Sửa 02/10/2026 sau review gộp
đợt 2: nhãn bằng chứng theo nguồn ĐANG gắn ở ngăn LiDAR ("device" chỉ với driver C1 thật; `--recording` là
"recording_replay", `--session-replay` là "session_replay"); vòng quét phát lại không bao giờ đi với bo COM
(START_POSE_UNVERIFIED ở cả VehicleIO lẫn Quan sát, kể cả khi đủ điều kiện tiên quyết). Chỉ kiểm bằng test.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox      # QMessageBox: lỗi của "Chọn bản đồ LiDAR…" (T2)

from autopark.application.cusp_policy import (ACCEPTANCE_THRESHOLDS, AcceptanceTagError, CuspPolicy, add_cusp_args,
                                              cusp_policy_from_args)
from autopark.application.session import Session, SessionError
from autopark.domain.types import Bounds, ParkingGoal, Pose, Scenario
from autopark.storage.scenario_store import VehicleConfigFile, load_vehicle_config_file, vehicle_config_arg
from autopark.power_throttling import apply_ecoqos_policy
from autopark.rig.recording import DEFAULT_JPEG_QUALITY, IMAGE_FORMATS, write_json_atomic
from autopark.rig.session_recording import DEFAULT_ROOT, MIN_FREE_START_GB, RecordOptions, SessionSensorRecorder
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from autopark.ui.lidar_dock import LidarDock
from autopark.ui.main_window import POSE_SOURCE_CHOICES, MainWindow
from autopark.ui.process_status import add_ecoqos_label
from autopark.ui.record_dock import SensorRecordDock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VEHICLE = PROJECT_ROOT / "configs" / "vehicle_default.json"
RECORD_WAIT_S = 60.0       # đóng cửa sổ: chờ bản ghi cảm biến ghi nốt tối đa chừng ấy


def bench_scenario() -> Scenario:
    return Scenario("ban_thu_lidar", Bounds(0.0, 0.0, 3.0, 2.0), Pose(0.5, 1.0, 0.0), ParkingGoal(Pose(0.8, 1.0, 0.0)),
                    obstacles=[], slot=None, vehicle_config_path=DEFAULT_VEHICLE)


CAMERA_AI_OPTIONS = ("cam_ports", "cam_replay", "checkpoint", "extrinsics", "roi_dir", "calibration_dir")


class BenchWindow(MainWindow):
    """The phase-0 cockpit plus the LiDAR dock; closing the window stops the LiDAR thread first.

    `camera_ai` (dict tham số của `CameraAIDock`, hay None): thêm ngăn AI camera, xếp thành thẻ cạnh ngăn LiDAR. None thì
    không nhập mô-đun ngăn camera, cửa sổ đúng như trước 25/09/2026."""

    SYNC_SOURCE = "ui.lidar_app"     # dấu đồng bộ video–log (T14): nút và phím F8 kế thừa từ MainWindow

    def __init__(self, session: Session, scenario_path: Path | None, *, port: str | None, recording: Path | None,
                 vehicle_override: VehicleConfigFile | None = None, camera_ai: dict | None = None,
                 record: RecordOptions | None = None, lidar_config=None):
        # --vehicle-config: MainWindow giữ xe này cả khi "Mở kịch bản" trong cửa sổ (02/10/2026: chung với ui.app)
        super().__init__(session, scenario_path, vehicle_override=vehicle_override)
        self.lidar_config = lidar_config            # T2: --lidar-config (None: configs/dinh_vi_lidar_v0.json)
        self.setWindowTitle("Autopark — bàn thử LiDAR")
        self.dock = LidarDock(self, port=port, recording=recording)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.camera_dock = None
        if camera_ai is not None:
            from autopark.ui.camera_dock import CameraAIDock   # nhập muộn: không có --camera-ai thì không cần

            self.camera_dock = CameraAIDock(self, **camera_ai)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.camera_dock)
            self.tabifyDockWidget(self.dock, self.camera_dock)
            self.dock.raise_()
            title = "Autopark — bàn thử LiDAR + AI camera"
            if camera_ai.get("test_rig"):
                title += " (RIG TỔNG HỢP)"
            self.setWindowTitle(title)
        # bản ghi cảm biến trong phiên đỗ (T3, 02/10/2026): ngăn "Ghi cảm biến" xếp thẻ cạnh ngăn LiDAR
        self.sensor_recording = SessionSensorRecorder(self, record)
        self.record_dock = SensorRecordDock(self, self.sensor_recording)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.record_dock)
        self.tabifyDockWidget(self.dock, self.record_dock)
        self.dock.record_sink = self.sensor_recording.lidar_sink
        if self.camera_dock is not None:
            self.camera_dock.on_batch = self.sensor_recording.add_ai_batch
        self.dock.raise_()

    # ---- bản ghi cảm biến (T3): RecordingHost của rig.session_recording ----
    def anchor_context(self, t_perf: float) -> dict:
        """Cột của một mốc session/clock.csv: như dấu đồng bộ (`_sync_context`), thêm t_session mỗi khi phiên có world."""
        ctx = self._sync_context(t_perf)
        if self.session.world is not None:
            ctx["t_session"] = round(self.session.world.time, 4)
        return ctx

    def camera_rig(self):
        return None if self.camera_dock is None else self.camera_dock.rig

    def camera_info(self) -> dict | None:
        return None if self.camera_dock is None else self.camera_dock.recording_info()

    def lidar_info(self) -> dict | None:
        return self.dock.recording_info()

    def lidar_stats(self) -> dict | None:
        return self.dock.recording_stats()

    def session_meta(self) -> dict:
        """Khối `session` của meta.json bản ghi cảm biến. Sửa 02/10/2026 sau review gộp đợt 2: "board" là mục của thẻ Bo
        điều khiển ("sim" bo mô phỏng, "qemu" bo ảo QEMU, hay cổng COM; trước đó bo ảo QEMU bị ghi "sim"); "cusp_policy"
        là giới hạn đổi chiều CÓ HIỆU LỰC mà Bắt đầu đỗ áp (`Session.cusp_limit().to_dict()`: cờ gộp với kịch bản nghiệm
        thu, có source, max_cusps, warn_cusps, cli_max_cusps; tệp gắn nghiệm thu thêm acceptance, key, tệp ngưỡng)."""
        s = self.session
        vehicle = self.vehicle_override.path if self.vehicle_override is not None else s.scenario.vehicle_config_path
        live_file = self.sync_marks.path
        return {"scenario": s.scenario.name, "scenario_path": None if self.scenario_path is None else str(self.scenario_path),
                "vehicle_config": None if vehicle is None else str(vehicle), "drive_mode": s.drive_mode.value,
                "board": self.board_key() or "sim", "cusp_policy": s.cusp_limit().to_dict(), "state": s.state.value,
                "sync_marks_live_file": None if live_file is None else str(live_file)}

    def sync_rows(self) -> list[dict]:
        return [dict(row) for row in self.sync_marks.rows]

    def window_state(self) -> str:
        if self.isMinimized():
            return "minimized"
        return "normal" if self.isVisible() else "hidden"

    def _poll_state_change(self) -> None:
        """Như MainWindow (dòng CLOCK của dấu đồng bộ), rồi báo bước chuyển cho bản ghi cảm biến — mốc riêng ở
        session/clock.csv, KHÔNG BAO GIỜ thêm dòng vào dấu đồng bộ của cửa sổ — và làm mới ngăn ghi ngay (nút khóa khi xe
        chạy). Không ném vào nhịp điều khiển."""
        old = self._last_state
        super()._poll_state_change()
        new = self._last_state
        recorder = getattr(self, "sensor_recording", None)
        if new == old or recorder is None:
            return
        recorder.on_state_change(old.value, new.value, self.session.stop_reason)
        try:
            self.record_dock.refresh()
        except Exception as exc:  # noqa: BLE001 - lỗi làm mới ngăn không được làm hỏng nhịp 16 ms
            self.record_dock.say(f"Lỗi làm mới ngăn Ghi cảm biến: {type(exc).__name__}: {exc}")

    def _export_extras(self, csv_path: Path, bundle: Path | None) -> str:
        """Tệp trỏ tới bản ghi cảm biến của cửa sổ (T3): `<tên>_sensor_recordings.json` cạnh tệp log và
        `sensor_recordings.json` trong gói phát lại (nếu có gói). Bản ghi KHÔNG được chép vào gói."""
        extra = super()._export_extras(csv_path, bundle)
        refs = self.sensor_recording.export_refs()
        if refs is None:
            return extra
        write_json_atomic(csv_path.with_name(csv_path.stem + "_sensor_recordings.json"), refs)
        if bundle is not None:
            write_json_atomic(Path(bundle) / "sensor_recordings.json", refs)
        return extra + f" (+ trỏ tới {len(refs['recordings'])} bản ghi cảm biến)"

    # ------------------------------------------------------------------ nguồn tư thế LiDAR thật (T2)
    def _lidar_real_supported(self) -> bool:
        return True

    def _dock_lidar_port(self) -> str | None:
        dock = getattr(self, "dock", None)
        if dock is None or dock.recording is not None or dock.replay_session is not None:
            return None                     # phát lại (--recording, --session-replay): ngăn không giữ cổng COM nào
        text = dock.edit_port.text().strip()
        return None if not text or text.lower() == "auto" else text

    def _lidar_pose_config(self):
        return getattr(self, "lidar_config", None) or super()._lidar_pose_config()

    def load_lidar_map(self, path, *, threaded: bool = True):
        """Nạp bản đồ LiDAR (thư mục của map_builder, hệ sa bàn) và dựng nguồn tư thế LiDAR thật cho cửa sổ (móc cho
        test: `threaded=False` rồi gọi `pump()`). Bản đồ không dùng được → ValueError tiếng Việt, nguồn cũ giữ nguyên.

        Nhãn bằng chứng (sửa 02/10/2026 sau review gộp đợt 2): theo nguồn ĐANG gắn ở ngăn LiDAR, chưa gắn thì theo nguồn
        mà ngăn sẽ mở (`--session-replay`, `--recording` hay cổng COM); sau đó ngăn báo lại mỗi lần gắn hay ngắt nguồn
        (`set_feed_kind`). Chỉ driver C1 thật là "device"; khác thì bo COM bị từ chối ở mọi nhánh (`start_gate`)."""
        from autopark.application.lidar_pose_source import LidarPoseSource, evidence_for_feed
        from autopark.lidar.localize import load_map
        from autopark.lidar.pose_estimator import LidarPoseEstimator

        path = Path(path)
        config = self._lidar_pose_config()
        map_info = lidar_map_info(path)
        lmap = load_map(path, config.localize)
        estimator = LidarPoseEstimator(lmap, config.localizer, mount=config.mount, odometry=config.odometry,
                                       self_mask=self.session.cfg, hint=self.session.scenario.start)
        source = LidarPoseSource(estimator, config, map_info=map_info, threaded=threaded,
                                 evidence=evidence_for_feed(self.dock.planned_feed_kind()))
        if self.dock.source is not None:
            source.set_feed_kind(self.dock.feed_kind())
        old = self.lidar_pose_source
        if old is not None:
            self.dock.remove_scan_consumer(old)
            if self.dock.pose_provider is old:
                self.dock.pose_provider = None
            old.close()
        self.lidar_pose_source = source
        self._hinted_start = self.session.scenario.start
        source.start()
        self.lbl_lidar_map.setText(f"Bản đồ LiDAR: {path.name} (hệ {map_info['frame']}, sha256 "
                                   f"{map_info['sha256'][:12]}…)")
        self._after_pose_choice()
        if self.pose_choice() == "lidar_real" and self.session.vehicle_link is not None:
            self._set_drive_mode(self.combo_drive.currentIndex())    # liên kết cũ giữ nguồn cũ: dựng lại
        self._refresh_mode_widgets()
        return source

    def _choose_lidar_map(self) -> None:
        from PySide6.QtWidgets import QFileDialog as Dialog

        folder = Dialog.getExistingDirectory(self, "Chọn bản đồ LiDAR (thư mục có costmap.json)",
                                             str(PROJECT_ROOT / "runs"))
        if not folder:
            return
        try:
            self.load_lidar_map(folder)
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, "Không nạp được bản đồ LiDAR", str(exc))

    def _after_pose_choice(self) -> None:
        """Nguồn LiDAR thật nhận vòng quét và neo vòng quét của ngăn LiDAR CHỈ khi đang chọn "LiDAR thật"."""
        dock, source = getattr(self, "dock", None), self.lidar_pose_source
        if dock is None or source is None:
            return
        if self.pose_choice() == "lidar_real":
            dock.add_scan_consumer(source)
            dock.pose_provider = source
        else:
            dock.remove_scan_consumer(source)
            if dock.pose_provider is source:
                dock.pose_provider = None

    def closeEvent(self, event) -> None:
        """Đóng cửa sổ. Sửa 02/10/2026 sau review gộp đợt 2: MainWindow.closeEvent (dừng nhịp 50 Hz, `session.close()`
        gửi enable=0 + DISARM qua liên kết VehicleIO, tắt bo ảo QEMU) chạy NGAY sau khi dừng ghi, trước mọi việc có thể
        chờ: tắt ngăn AI camera, nguồn tư thế LiDAR (≤ 1 s), ngăn LiDAR, rồi chờ bản ghi cảm biến ghi nốt (tối đa
        RECORD_WAIT_S). Trước đó lệnh dừng + DISARM đi SAU lần chờ ghi nốt, trong lúc vòng 50 Hz đứng."""
        self.record_dock.shutdown()              # dừng ghi trước khi tắt nguồn (không chờ ở đây)
        try:
            super().closeEvent(event)            # dừng xe và bo trước mọi việc có thể chờ
        finally:
            if self.camera_dock is not None:
                self.camera_dock.shutdown()
            if self.lidar_pose_source is not None:     # T2: dừng luồng định vị trước khi đóng LiDAR
                self.dock.remove_scan_consumer(self.lidar_pose_source)
                self.dock.pose_provider = None
                self.lidar_pose_source.close()
            self.dock.shutdown()
            if not self.sensor_recording.wait_finished(RECORD_WAIT_S):
                print(f"CẢNH BÁO: bản ghi cảm biến {self.sensor_recording.rec.folder} chưa ghi nốt xong sau "
                      f"{RECORD_WAIT_S:g} s: meta.json có thể còn \"đang ghi\"", file=sys.stderr)


def lidar_map_info(path) -> dict:
    """Thông tin bản đồ cho nguồn tư thế LiDAR thật (T2): đường dẫn, sha256 của costmap.json, hệ, mốc neo, mirror.
    Bản đồ không phải của map_builder hay không ở hệ sa bàn → ValueError tiếng Việt."""
    import hashlib

    from autopark.lidar.map_builder import SA_BAN_FRAME, read_map_build

    path = Path(path)
    costmap = path / "costmap.json" if path.is_dir() else path
    if not costmap.is_file():
        raise ValueError(f"Không có costmap.json ở {path}")
    try:
        block = read_map_build(costmap)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Bản đồ {path} không đọc được: {exc}") from exc
    if not block:
        raise ValueError(f"Bản đồ {path} không do autopark.lidar.map_builder dựng (không có khối map_build)")
    if block.get("frame") != SA_BAN_FRAME or not block.get("session_ready"):
        raise ValueError(f"Bản đồ {path} ở hệ {block.get('frame')!r}, không phải hệ sa bàn (dựng lại với --anchor hoặc "
                         f"--anchor-vehicle): nguồn tư thế của phiên không nhận")
    return {"path": str(path), "sha256": hashlib.sha256(costmap.read_bytes()).hexdigest(), "frame": block.get("frame"),
            "anchor": block.get("anchor"), "session_ready": True, "mirror": block.get("mirror")}


def build_window(scenario_path: Path | None, *, port: str | None, recording: Path | None,
                 vehicle_config: Path | None = None, camera_ai: dict | None = None,
                 cusp_policy: CuspPolicy | None = None, record: RecordOptions | None = None,
                 acceptance_thresholds: Path | None = ACCEPTANCE_THRESHOLDS, lidar_config=None) -> tuple[BenchWindow, LidarDock]:
    """`vehicle_config` (nếu có) thay cấu hình xe của sa bàn mặc định hoặc của kịch bản, kể cả kịch bản mở sau đó
    bằng "Mở kịch bản" trong cửa sổ. `camera_ai`: tham số của ngăn AI camera (xem `camera_ai_options`), None = không có
    ngăn đó; ngăn ở `window.camera_dock`. `cusp_policy` (T12): giới hạn số lần đổi chiều, giữ cả khi "Mở kịch bản".
    `record` (T3): tùy chọn của bản ghi cảm biến (`record_options`), None = mặc định; ngăn ở `window.record_dock`.
    `acceptance_thresholds`: tệp ngưỡng cho tệp sa bàn gắn nghiệm thu (AcceptanceTagError trước khi có cửa sổ)."""
    if scenario_path is not None:
        scenario = load_scenario(scenario_path)
    else:
        scenario = bench_scenario()
    chosen: VehicleConfigFile | None = None
    if vehicle_config is not None:
        chosen = load_vehicle_config_file(vehicle_config)
        cfg = chosen.cfg
        scenario.vehicle_config_path = chosen.path     # lưu kịch bản thì trỏ đúng tệp xe đang dùng
    elif scenario_path is not None:
        cfg = load_vehicle_config(scenario.vehicle_config_path)
    else:
        cfg = load_vehicle_config(DEFAULT_VEHICLE)
    session = Session(scenario, cfg, cusp_policy=cusp_policy, acceptance_thresholds=acceptance_thresholds)
    window = BenchWindow(session, scenario_path, port=port, recording=recording,
                         vehicle_override=chosen, camera_ai=camera_ai, record=record,
                         lidar_config=lidar_config)
    return window, window.dock


def add_record_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("Ghi cảm biến trong phiên đỗ (T3, docs/VAN_HANH.md)")
    group.add_argument("--record-root", type=Path, default=None,
                       help="thư mục gốc của bản ghi cảm biến, mặc định runs/session_recordings (git bỏ qua)")
    group.add_argument("--record-format", choices=IMAGE_FORMATS, default="jpg",
                       help="ảnh camera: jpg (mặc định) hay png (không mất mát, lớn ≈ 4,5 lần: chỉ đoạn ngắn)")
    group.add_argument("--jpeg-quality", type=int, default=DEFAULT_JPEG_QUALITY,
                       help=f"chất lượng JPEG 1..100 (mặc định {DEFAULT_JPEG_QUALITY})")
    group.add_argument("--record-min-free-gb", type=float, default=MIN_FREE_START_GB,
                       help=f"không bắt đầu ghi khi ổ còn ít hơn chừng ấy GB (mặc định {MIN_FREE_START_GB:g}; phải lớn "
                            "hơn ngưỡng tự dừng 2 GB; ĐỀ XUẤT – CHỜ CHỐT)")


def record_options(parser: argparse.ArgumentParser, args) -> RecordOptions:
    """Tùy chọn ghi từ dòng lệnh; sai → parser.error (mã 2), trước khi mở cửa sổ hay thiết bị nào."""
    try:
        return RecordOptions(root=args.record_root or DEFAULT_ROOT, image_format=args.record_format,
                             jpeg_quality=args.jpeg_quality, min_free_gb=args.record_min_free_gb).check()
    except ValueError as exc:
        parser.error(f"tùy chọn ghi cảm biến sai: {exc}")


def session_replay_from_args(parser: argparse.ArgumentParser, args):
    """`--session-replay` (T3b): một `ReplaySession` cho cả hai ngăn (cổng camera theo `--cam-ports` nếu có), hoặc None.
    Dùng cùng `--recording`/`--cam-replay`/`--port`, hay thư mục không đọc được → parser.error (mã 2), trước khi mở cửa
    sổ hay thiết bị nào."""
    if args.session_replay is None:
        return None
    clash = [name for name, value in (("--recording", args.recording), ("--cam-replay", args.cam_replay),
                                      ("--port", args.port)) if value is not None]
    if clash:
        parser.error("--session-replay không dùng cùng " + ", ".join(clash))
    from autopark.rig.replay import ReplaySession

    try:
        return ReplaySession(args.session_replay, ports=args.cam_ports or None)
    except (OSError, ValueError) as exc:          # ReplayError, meta.json hỏng (JSONDecodeError), cổng không có
        parser.error(f"--session-replay: {exc}")


def start_session_replay(window: BenchWindow, session, *, make_segmenter=None) -> bool:
    """T3b: gắn MỘT ReplaySession cho cả hai ngăn. Ngăn LiDAR đọc vòng quét của bản ghi (`DockLidarReplay`); ngăn AI camera
    (nếu có) chạy Rig phát lại trên CHÍNH phiên đó, đồng hồ bắt đầu khi AI nạp xong mô hình. Không có ngăn AI camera, hay
    AI không bật được (thiếu torch, thiếu mô hình), thì bắt đầu đồng hồ ngay sau khi gắn LiDAR. Trả True khi AI chạy."""
    window.dock.replay_session = session
    if session.has_lidar:
        window.dock.connect_source()
    started = window.camera_dock is not None and window.camera_dock.start_ai(make_segmenter, replay_session=session)
    if not started:
        session.begin()
    return started


def add_camera_ai_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("AI camera làm nguồn vật cản (docs/KIEN_TRUC.md, cần .venv-train)")
    group.add_argument("--camera-ai", action="store_true", help="thêm ngăn AI camera (vật cản từ AI của các camera)")
    group.add_argument("--cam-ports", type=int, nargs="+", default=None, help="cổng hub của camera, mặc định 1 2 3 4")
    group.add_argument("--cam-replay", type=Path, default=None,
                       help="chạy AI từ một bản ghi phiên bàn thử (không mở camera nào)")
    group.add_argument("--checkpoint", type=Path, default=None,
                       help="mô hình AI, mặc định runs/ai_woodscape_rtx4000_v1/best.pt")
    group.add_argument("--extrinsics", type=Path, default=None,
                       help="tệp ngoại tham đã đo, mặc định configs/rig/camera_rig_extrinsics_v1.json")
    group.add_argument("--roi-dir", type=Path, default=None, help="thư mục roi_p<cổng>.png, mặc định configs/roi/rig_v1")
    group.add_argument("--calibration-dir", type=Path, default=None,
                       help="thư mục nội tham cam_p<cổng>.json, mặc định calibration")
    group.add_argument("--camera-ai-test-rig", action="store_true",
                       help="rig camera TỔNG HỢP (camera ảo) — chỉ để thử, chỉ nhận cùng --cam-replay")


def camera_ai_options(parser: argparse.ArgumentParser, args) -> dict | None:
    """Tham số ngăn AI camera từ dòng lệnh, hoặc None khi không có --camera-ai. Lỗi dùng sai → parser.error (mã 2),
    trước khi mở cửa sổ hay thiết bị nào."""
    given = [name for name in CAMERA_AI_OPTIONS if getattr(args, name) is not None]
    if args.camera_ai_test_rig:
        given.append("camera_ai_test_rig")
    if not args.camera_ai:
        if given:
            parser.error("tùy chọn " + ", ".join("--" + g.replace("_", "-") for g in given)
                         + " chỉ dùng cùng --camera-ai")
        return None
    if args.camera_ai_test_rig and args.cam_replay is None and getattr(args, "session_replay", None) is None:
        parser.error("--camera-ai-test-rig (rig camera TỔNG HỢP) chỉ dùng với --cam-replay <thư mục bản ghi> (hay "
                     "--session-replay), không bao giờ với camera thật")
    return {"ports": tuple(args.cam_ports or (1, 2, 3, 4)), "replay": args.cam_replay, "checkpoint": args.checkpoint,
            "calibration_dir": args.calibration_dir, "extrinsics": args.extrinsics, "roi_dir": args.roi_dir,
            "test_rig": bool(args.camera_ai_test_rig)}


def add_pose_source_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("Nguồn tư thế LiDAR (T2, application/lidar_pose_source.py)")
    group.add_argument("--pose-source", choices=[key for key, _ in POSE_SOURCE_CHOICES], default=None,
                       help="chọn sẵn ô Nguồn tư thế (mặc định sim_truth)")
    group.add_argument("--lidar-map", type=Path, default=None,
                       help="thư mục bản đồ của autopark.lidar.map_builder (hệ sa bàn) cho LiDAR thật")
    group.add_argument("--lidar-config", type=Path, default=None,
                       help="cấu hình định vị LiDAR, mặc định configs/dinh_vi_lidar_v0.json")


def pose_source_options(parser: argparse.ArgumentParser, args):
    """Kiểm các tùy chọn nguồn tư thế TRƯỚC khi mở cửa sổ hay cổng nào (lỗi → parser.error, mã 2). Trả cấu hình định
    vị LiDAR (hoặc None = mặc định)."""
    from autopark.lidar.pose_config import load_lidar_pose_config

    if args.pose_source == "lidar_real" and args.lidar_map is None:
        parser.error("--pose-source lidar_real cần --lidar-map <thư mục bản đồ của autopark.lidar.map_builder>")
    config = None
    if args.lidar_config is not None or args.lidar_map is not None:
        try:
            config = load_lidar_pose_config(args.lidar_config)
        except ValueError as exc:
            parser.error(str(exc))
    if args.lidar_map is not None:
        from autopark.lidar.localize import load_map

        try:
            lidar_map_info(args.lidar_map)
            load_map(args.lidar_map, config.localize)
        except (OSError, ValueError, KeyError) as exc:
            parser.error(f"--lidar-map: {exc}")
    return config


def apply_pose_source_options(window: BenchWindow, args) -> None:
    """Sau khi dựng cửa sổ: nạp bản đồ LiDAR, chọn sẵn nguồn tư thế (không mở cổng bo nào)."""
    if args.lidar_map is not None:
        window.load_lidar_map(args.lidar_map)
    if args.pose_source is not None:
        window.combo_pose.setCurrentIndex(window.combo_pose.findData(args.pose_source))


def main(argv=None) -> int:
    ecoqos = apply_ecoqos_policy("ui.lidar_app")       # trước mọi việc khác (power_throttling.py)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", default=None,
                        help="cổng COM của RPLIDAR C1 (hoặc auto); mặc định lidar_port trong configs/thiet_bi.json")
    parser.add_argument("--recording", type=Path, default=None,
                        help="phát lại LiDAR thay vì cổng COM: .npz hay thư mục bản ghi phiên (mọi phần lidar/part_*.npz)")
    parser.add_argument("--scenario", type=Path, default=None)
    parser.add_argument("--no-connect", action="store_true", help="mở cửa sổ nhưng chưa kết nối (cả LiDAR lẫn AI camera)")
    parser.add_argument("--vehicle-config", type=vehicle_config_arg, default=None,
                        help="tệp cấu hình xe JSON; mặc định configs/vehicle_default.json (hoặc tệp xe của --scenario)")
    parser.add_argument("--session-replay", type=Path, default=None,
                        help="phát lại MỘT thư mục bản ghi phiên cho cả ngăn LiDAR và ngăn AI camera, cùng một đồng hồ "
                             "(T3b); không dùng cùng --recording, --cam-replay, --port")
    add_camera_ai_args(parser)
    add_cusp_args(parser)
    add_record_args(parser)
    add_pose_source_args(parser)
    args = parser.parse_args(argv)
    camera_ai = camera_ai_options(parser, args)
    cusp_policy = cusp_policy_from_args(parser, args)
    record = record_options(parser, args)
    lidar_config = pose_source_options(parser, args)
    session = session_replay_from_args(parser, args)
    app = QApplication.instance() or QApplication(sys.argv)
    vehicle = args.vehicle_config.path if args.vehicle_config is not None else None
    try:
        window, dock = build_window(args.scenario, port=args.port, recording=args.recording, vehicle_config=vehicle,
                                    camera_ai=camera_ai, cusp_policy=cusp_policy, record=record,
                                    lidar_config=lidar_config)
    except (AcceptanceTagError, SessionError) as exc:          # trước show() và connect_source(): chưa mở LiDAR hay camera nào
        parser.error(f"--scenario {args.scenario}: {exc}")
    if session is not None:
        # T3b: ngăn LiDAR biết nó sẽ phát lại TRƯỚC khi nạp --lidar-map (nhãn bằng chứng, không giữ cổng COM nào; sửa
        # 02/10/2026 sau review gộp đợt 2); start_session_replay gắn nguồn sau khi cửa sổ hiện
        window.dock.replay_session = session
    apply_pose_source_options(window, args)
    window.resize(1750, 960)
    window.show()
    add_ecoqos_label(window, ecoqos)
    if session is not None:                     # không mở thiết bị nào: luôn tự bật cả hai ngăn (T3b)
        start_session_replay(window, session)
        return app.exec()
    if not args.no_connect:
        dock.connect_source()
    # bản ghi không mở thiết bị nào nên luôn tự bật; camera thật chỉ tự bật khi không có --no-connect
    if window.camera_dock is not None and (not args.no_connect or args.cam_replay is not None):
        window.camera_dock.start_ai()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
