"""Cửa sổ đỗ xe giai đoạn 0 kèm ngăn LiDAR thật (bàn thử giai đoạn 1–3).

    python -m autopark.ui.lidar_app --port COM4
    python -m autopark.ui.lidar_app --recording runs/lidar_bench/20260922/p07_nen_phong.npz
    python -m autopark.ui.lidar_app --port COM4 --scenario scenarios/sa_ban_3x2_hai_hop.json
    python -m autopark.ui.lidar_app --port COM4 --vehicle-config configs/vehicle_measured.json

Cấu hình xe: không có `--vehicle-config` thì như cũ (sa bàn mặc định dùng configs/vehicle_default.json, GIẢ ĐỊNH –
CHƯA ĐO; `--scenario` dùng tệp xe mà kịch bản trỏ tới). Có `--vehicle-config` thì tệp đó thay cho cả hai, và vẫn giữ
khi mở kịch bản khác bằng nút "Mở kịch bản" trong cửa sổ (không dùng tệp xe của kịch bản đó; thanh trạng thái báo
điều này). Tệp hỏng thì báo lỗi và thoát trước khi mở cửa sổ hay cổng COM. Chỉ kiểm bằng test offscreen (không mở cổng
COM, 24/09/2026); CHƯA THỬ với LiDAR thật.

Mặc định mở sa bàn 3 × 2 m trống, xe ở (0,5; 1,0) hướng +x, đích ở (2,0; 1,0). Trình tự trên màn hình:
Kết nối → vật cản LiDAR hiện ngay và bám theo cảm biến → Tìm đường đỗ (chốt bản đồ) → Bắt đầu đỗ → đưa tay vào trước LiDAR
để thấy xe ảo dừng (MAP_CHANGED). Ngăn LiDAR ở bên phải, kéo ra được.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

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


class BenchWindow(MainWindow):
    """The phase-0 cockpit plus the LiDAR dock; closing the window stops the LiDAR thread first."""

    def __init__(self, session: Session, scenario_path: Path | None, *, port: str, recording: Path | None,
                 vehicle_override: VehicleConfigFile | None = None):
        super().__init__(session, scenario_path)
        self.vehicle_override = vehicle_override    # --vehicle-config: giữ cả khi "Mở kịch bản" trong cửa sổ
        self.setWindowTitle("Autopark — bàn thử LiDAR")
        self.dock = LidarDock(self, port=port, recording=recording)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

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
        self.dock.shutdown()
        super().closeEvent(event)


def build_window(scenario_path: Path | None, *, port: str, recording: Path | None,
                 vehicle_config: Path | None = None) -> tuple[BenchWindow, LidarDock]:
    """`vehicle_config` (nếu có) thay cấu hình xe của sa bàn mặc định hoặc của kịch bản, kể cả kịch bản mở sau đó
    bằng "Mở kịch bản" trong cửa sổ."""
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
    window = BenchWindow(Session(scenario, cfg), scenario_path, port=port, recording=recording,
                         vehicle_override=chosen)
    return window, window.dock


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--recording", type=Path, default=None, help="phát lại bản ghi .npz thay vì cổng COM")
    parser.add_argument("--scenario", type=Path, default=None)
    parser.add_argument("--no-connect", action="store_true", help="mở cửa sổ nhưng chưa kết nối")
    parser.add_argument("--vehicle-config", type=vehicle_config_arg, default=None,
                        help="tệp cấu hình xe JSON; mặc định configs/vehicle_default.json (hoặc tệp xe của --scenario)")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv)
    vehicle = args.vehicle_config.path if args.vehicle_config is not None else None
    window, dock = build_window(args.scenario, port=args.port, recording=args.recording, vehicle_config=vehicle)
    window.resize(1750, 960)
    window.show()
    if not args.no_connect:
        dock.connect_source()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
