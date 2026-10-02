"""Điểm vào giao diện: nạp kịch bản và cấu hình xe, mở cửa sổ chính.

    python run_app.py [kịch_bản.json] [--max-cusps N] [--warn-cusps N]

Số lần đổi chiều của đường (T12, thêm 02/10/2026; application/cusp_policy.py): `--max-cusps N` từ chối Bắt đầu đỗ khi
đường có hơn N lần đổi chiều (mặc định không chặn: giới hạn CHƯA CHỐT), `--warn-cusps N` cảnh báo khi hơn N (mặc định 7).
Từ đó dòng lệnh được đọc chặt: tham số lạ (trước đây bị bỏ qua) thì báo lỗi và thoát mã 2, trước khi mở cửa sổ.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from autopark.application.cusp_policy import CuspPolicy, add_cusp_args, cusp_policy_from_args
from autopark.application.session import Session
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from autopark.ui.main_window import MainWindow

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO = PROJECT_ROOT / "scenarios" / "bai_do_xe_lon_xon.json"


def build_window(scenario_path: Path, *, cusp_policy: CuspPolicy | None = None) -> MainWindow:
    scenario = load_scenario(scenario_path)
    cfg = load_vehicle_config(scenario.vehicle_config_path)
    return MainWindow(Session(scenario, cfg, cusp_policy=cusp_policy), scenario_path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Đọc `argv` dạng sys.argv (phần tử đầu là tên chương trình): `scenario` (mặc định DEFAULT_SCENARIO) và
    `cusp_policy` (`CuspPolicy`). Sai → mã 2 trước khi có QApplication hay cửa sổ."""
    p = argparse.ArgumentParser(prog=Path(argv[0]).name if argv else None, description=__doc__.split("\n")[0])
    p.add_argument("scenario", nargs="?", type=Path, default=DEFAULT_SCENARIO,
                   help=f"tệp kịch bản JSON (mặc định scenarios/{DEFAULT_SCENARIO.name})")
    add_cusp_args(p)
    args = p.parse_args(argv[1:])
    args.cusp_policy = cusp_policy_from_args(p, args)
    return args


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args = parse_args(argv)
    app = QApplication.instance() or QApplication(argv)
    window = build_window(args.scenario, cusp_policy=args.cusp_policy)
    window.show()
    return app.exec()
