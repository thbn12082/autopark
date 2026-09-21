"""Điểm vào giao diện: nạp kịch bản và cấu hình xe, mở cửa sổ chính."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from autopark.application.session import Session
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from autopark.ui.main_window import MainWindow

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO = PROJECT_ROOT / "scenarios" / "bai_do_xe_lon_xon.json"


def build_window(scenario_path: Path) -> MainWindow:
    scenario = load_scenario(scenario_path)
    cfg = load_vehicle_config(scenario.vehicle_config_path)
    return MainWindow(Session(scenario, cfg), scenario_path)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication.instance() or QApplication(argv)
    scenario_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_SCENARIO
    window = build_window(scenario_path)
    window.show()
    return app.exec()
