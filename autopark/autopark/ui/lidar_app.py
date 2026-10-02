"""Cửa sổ đỗ xe giai đoạn 0 kèm ngăn LiDAR thật (bàn thử giai đoạn 1–3).

    python -m autopark.ui.lidar_app
    python -m autopark.ui.lidar_app --recording runs/lidar_bench/20260922/p07_nen_phong.npz
    python -m autopark.ui.lidar_app --scenario scenarios/sa_ban_3x2_hai_hop.json
    python -m autopark.ui.lidar_app --vehicle-config configs/vehicle_measured.json
    python -m autopark.ui.lidar_app --max-cusps 2

Số lần đổi chiều (T12, 02/10/2026): `--max-cusps N` từ chối Bắt đầu đỗ khi đường có hơn N lần đổi chiều (mặc định không
chặn, giới hạn CHƯA CHỐT), `--warn-cusps N` cảnh báo khi hơn N (mặc định 7), như `run_app.py`; giữ cả khi "Mở kịch bản".

Cổng LiDAR: không có `--port` thì lấy `lidar_port` trong configs/thiet_bi.json (đổi máy chỉ sửa tệp đó, 29/09/2026;
autopark/lidar/port.py); `--port COMx` ghi đè cho một lần chạy.

Cấu hình xe: không có `--vehicle-config` thì như cũ (sa bàn mặc định dùng configs/vehicle_default.json, GIẢ ĐỊNH –
CHƯA ĐO; `--scenario` dùng tệp xe mà kịch bản trỏ tới). Có `--vehicle-config` thì tệp đó thay cho cả hai, và vẫn giữ
khi mở kịch bản khác bằng nút "Mở kịch bản" trong cửa sổ (không dùng tệp xe của kịch bản đó; thanh trạng thái báo
điều này). Tệp hỏng thì báo lỗi và thoát trước khi mở cửa sổ hay cổng COM. Chỉ kiểm bằng test offscreen (không mở cổng
COM, 24/09/2026); CHƯA THỬ với LiDAR thật.

Mặc định mở sa bàn 3 × 2 m trống, xe ở (0,5; 1,0) hướng +x, đích ở (2,0; 1,0). Trình tự trên màn hình:
Kết nối → vật cản LiDAR hiện ngay và bám theo cảm biến → Tìm đường đỗ (chốt bản đồ) → Bắt đầu đỗ → đưa tay vào trước LiDAR
để thấy xe ảo dừng (MAP_CHANGED). Ngăn LiDAR ở bên phải, kéo ra được. Dấu đồng bộ video–log cho video R3 (T14,
02/10/2026): nút "Dấu đồng bộ · F8" hay phím F8 như ở `ui.app`, trước Bắt đầu đỗ và sau khi xe dừng; tệp
runs/sync_marks/<giờ>_ui_lidar_app.csv (chỉ kiểm offscreen).

AI camera làm nguồn vật cản thứ hai (thêm 25/09/2026, docs/AI_DIEU_KHIEN_XE.md; cần .venv-train vì AI dùng torch):

    .venv-train\\Scripts\\python.exe -X utf8 -m autopark.ui.lidar_app --camera-ai --cam-ports 1 2 3 4
    .venv-train\\Scripts\\python.exe -X utf8 -m autopark.ui.lidar_app --no-connect --camera-ai --cam-replay runs/rig_recordings/<phiên>
    .venv-train\\Scripts\\python.exe -X utf8 -m autopark.ui.lidar_app --no-connect --camera-ai --cam-replay runs/rig_recordings/<phiên> --camera-ai-test-rig

Tùy chọn khác: `--checkpoint` (mặc định runs/ai_woodscape_rtx4000_v1/best.pt), `--calibration-dir` (calibration),
`--extrinsics` (configs/rig/camera_rig_extrinsics_v1.json), `--roi-dir` (configs/roi/rig_v1). AI chỉ tạo vật cản khi BEV
dùng được (nội tham đạt + ngoại tham đo + ROI, không tổng hợp); tới 25/09/2026 chưa camera nào được hiệu chuẩn nên trên
bàn thật AI chỉ hiện lý do bị chặn. `--camera-ai-test-rig` (rig TỔNG HỢP) chỉ nhận cùng `--cam-replay`. Các tùy chọn
camera không đi kèm `--camera-ai` bị từ chối. Không có `--camera-ai` thì cửa sổ như trước, không nhập torch hay ngăn
camera (chạy được trong .venv). `--no-connect` không mở LiDAR và không bật camera thật (bấm "Bật AI camera" trong ngăn);
AI từ `--cam-replay` thì luôn tự bật vì không mở thiết bị nào. Bản ghi phiên chỉ cấp ảnh camera: LiDAR của bản ghi không
được phát lại ở đây, nên LiDAR (cổng COM hay `--recording`) và AI từ bản ghi KHÔNG cùng một cảnh.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from autopark.application.cusp_policy import CuspPolicy, add_cusp_args, cusp_policy_from_args
from autopark.application.session import Session
from autopark.domain.types import Bounds, ParkingGoal, Pose, Scenario
from autopark.evaluation.sensitivity import VehicleConfigFile, load_vehicle_config_file, vehicle_config_arg
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from autopark.ui.lidar_dock import LidarDock
from autopark.ui.main_window import MainWindow

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VEHICLE = PROJECT_ROOT / "configs" / "vehicle_default.json"


def bench_scenario() -> Scenario:
    return Scenario("ban_thu_lidar", Bounds(0.0, 0.0, 3.0, 2.0), Pose(0.5, 1.0, 0.0), ParkingGoal(Pose(2.0, 1.0, 0.0)),
                    obstacles=[], slot=None, vehicle_config_path=DEFAULT_VEHICLE)


CAMERA_AI_OPTIONS = ("cam_ports", "cam_replay", "checkpoint", "extrinsics", "roi_dir", "calibration_dir")


class BenchWindow(MainWindow):
    """The phase-0 cockpit plus the LiDAR dock; closing the window stops the LiDAR thread first.

    `camera_ai` (dict tham số của `CameraAIDock`, hay None): thêm ngăn AI camera, xếp thành thẻ cạnh ngăn LiDAR. None thì
    không nhập mô-đun ngăn camera, cửa sổ đúng như trước 25/09/2026."""

    SYNC_SOURCE = "ui.lidar_app"     # dấu đồng bộ video–log (T14): nút và phím F8 kế thừa từ MainWindow

    def __init__(self, session: Session, scenario_path: Path | None, *, port: str | None, recording: Path | None,
                 vehicle_override: VehicleConfigFile | None = None, camera_ai: dict | None = None):
        super().__init__(session, scenario_path)
        self.vehicle_override = vehicle_override    # --vehicle-config: giữ cả khi "Mở kịch bản" trong cửa sổ
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

    def _open_scenario(self) -> None:
        """Như MainWindow; có --vehicle-config thì kịch bản mở ra dùng xe đã chọn, không dùng tệp xe của kịch bản.

        Viết lại cả hàm thay vì gọi super() rồi đặt lại xe: super() nạp tệp xe của kịch bản trước, nên tệp đó thiếu
        hoặc hỏng sẽ hiện hộp lỗi dù xe đã chọn vẫn dùng được."""
        override = self.vehicle_override
        if override is None:
            super()._open_scenario()
            return
        path, _ = QFileDialog.getOpenFileName(self, "Mở kịch bản", str(self._scenario_dir()), "JSON (*.json)")
        if not path:
            return
        try:
            scenario = load_scenario(path)
            scenario.vehicle_config_path = override.path     # lưu lại thì trỏ đúng tệp xe đang dùng
            self.session.replace_scenario(scenario, override.cfg)
        except Exception as exc:  # noqa: BLE001 - báo lỗi cho người dùng
            QMessageBox.critical(self, "Không mở được kịch bản", str(exc))
            return
        self.scenario_path = Path(path)
        self._rebuild_scene()
        self._refresh_all()
        self.statusBar().showMessage(f"Đã mở {path}; xe theo --vehicle-config {override.path.name} "
                                     "(không dùng tệp xe của kịch bản)", 8000)

    def closeEvent(self, event) -> None:
        if self.camera_dock is not None:
            self.camera_dock.shutdown()
        self.dock.shutdown()
        super().closeEvent(event)


def build_window(scenario_path: Path | None, *, port: str | None, recording: Path | None,
                 vehicle_config: Path | None = None, camera_ai: dict | None = None,
                 cusp_policy: CuspPolicy | None = None) -> tuple[BenchWindow, LidarDock]:
    """`vehicle_config` (nếu có) thay cấu hình xe của sa bàn mặc định hoặc của kịch bản, kể cả kịch bản mở sau đó
    bằng "Mở kịch bản" trong cửa sổ. `camera_ai`: tham số của ngăn AI camera (xem `camera_ai_options`), None = không có
    ngăn đó; ngăn ở `window.camera_dock`. `cusp_policy` (T12): giới hạn số lần đổi chiều, giữ cả khi "Mở kịch bản"."""
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
    window = BenchWindow(Session(scenario, cfg, cusp_policy=cusp_policy), scenario_path, port=port, recording=recording,
                         vehicle_override=chosen, camera_ai=camera_ai)
    return window, window.dock


def add_camera_ai_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("AI camera làm nguồn vật cản (docs/AI_DIEU_KHIEN_XE.md, cần .venv-train)")
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
    if args.camera_ai_test_rig and args.cam_replay is None:
        parser.error("--camera-ai-test-rig (rig camera TỔNG HỢP) chỉ dùng với --cam-replay <thư mục bản ghi>, không bao "
                     "giờ với camera thật")
    return {"ports": tuple(args.cam_ports or (1, 2, 3, 4)), "replay": args.cam_replay, "checkpoint": args.checkpoint,
            "calibration_dir": args.calibration_dir, "extrinsics": args.extrinsics, "roi_dir": args.roi_dir,
            "test_rig": bool(args.camera_ai_test_rig)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", default=None,
                        help="cổng COM của RPLIDAR C1 (hoặc auto); mặc định lidar_port trong configs/thiet_bi.json")
    parser.add_argument("--recording", type=Path, default=None, help="phát lại bản ghi .npz thay vì cổng COM")
    parser.add_argument("--scenario", type=Path, default=None)
    parser.add_argument("--no-connect", action="store_true", help="mở cửa sổ nhưng chưa kết nối (cả LiDAR lẫn AI camera)")
    parser.add_argument("--vehicle-config", type=vehicle_config_arg, default=None,
                        help="tệp cấu hình xe JSON; mặc định configs/vehicle_default.json (hoặc tệp xe của --scenario)")
    add_camera_ai_args(parser)
    add_cusp_args(parser)
    args = parser.parse_args(argv)
    camera_ai = camera_ai_options(parser, args)
    cusp_policy = cusp_policy_from_args(parser, args)
    app = QApplication.instance() or QApplication(sys.argv)
    vehicle = args.vehicle_config.path if args.vehicle_config is not None else None
    window, dock = build_window(args.scenario, port=args.port, recording=args.recording, vehicle_config=vehicle,
                                camera_ai=camera_ai, cusp_policy=cusp_policy)
    window.resize(1750, 960)
    window.show()
    if not args.no_connect:
        dock.connect_source()
    # bản ghi không mở thiết bị nào nên luôn tự bật; camera thật chỉ tự bật khi không có --no-connect
    if window.camera_dock is not None and (not args.no_connect or args.cam_replay is not None):
        window.camera_dock.start_ai()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
