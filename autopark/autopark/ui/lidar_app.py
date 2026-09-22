"""Cửa sổ đỗ xe giai đoạn 0 kèm ngăn LiDAR thật (bàn thử giai đoạn 1–3).

    python -m autopark.ui.lidar_app --port COM4
    python -m autopark.ui.lidar_app --recording runs/lidar_bench/20260922/p07_nen_phong.npz
    python -m autopark.ui.lidar_app --port COM4 --scenario scenarios/sa_ban_3x2_hai_hop.json

Mặc định mở sa bàn 3 × 2 m trống, xe ở (0,5; 1,0) hướng +x, đích ở (2,0; 1,0). Trình tự trên màn hình:
Kết nối → vật cản LiDAR hiện ngay và bám theo cảm biến → Tìm đường đỗ (chốt bản đồ) → Bắt đầu đỗ → đưa tay vào trước LiDAR
để thấy xe ảo dừng (MAP_CHANGED). Ngăn LiDAR ở bên phải, kéo ra được.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from autopark.application.session import Session
from autopark.domain.types import Bounds, ParkingGoal, Pose, Scenario
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

    def __init__(self, session: Session, scenario_path: Path | None, *, port: str, recording: Path | None):
        super().__init__(session, scenario_path)
        self.setWindowTitle("Autopark — bàn thử LiDAR")
        self.dock = LidarDock(self, port=port, recording=recording)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

    def closeEvent(self, event) -> None:
        self.dock.shutdown()
        super().closeEvent(event)


def build_window(scenario_path: Path | None, *, port: str, recording: Path | None) -> tuple[BenchWindow, LidarDock]:
    if scenario_path is not None:
        scenario = load_scenario(scenario_path)
        cfg = load_vehicle_config(scenario.vehicle_config_path)
    else:
        scenario = bench_scenario()
        cfg = load_vehicle_config(DEFAULT_VEHICLE)
    window = BenchWindow(Session(scenario, cfg), scenario_path, port=port, recording=recording)
    return window, window.dock


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--recording", type=Path, default=None, help="phát lại bản ghi .npz thay vì cổng COM")
    parser.add_argument("--scenario", type=Path, default=None)
    parser.add_argument("--no-connect", action="store_true", help="mở cửa sổ nhưng chưa kết nối")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv)
    window, dock = build_window(args.scenario, port=args.port, recording=args.recording)
    window.resize(1750, 960)
    window.show()
    if not args.no_connect:
        dock.connect_source()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
