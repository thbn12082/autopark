"""Mở giao diện thao tác gần.

    python run_app.py [kịch_bản.json] [--max-cusps N] [--warn-cusps N] [--vehicle-config TỆP_XE]
    python run_app.py scenarios/thao_tac_cua_hep.json

Giới hạn lấy từ kịch bản; --max-cusps chỉ siết thêm. Cấu hình xe được giữ khi mở
kịch bản khác. Tham số không hợp lệ bị từ chối trước khi mở cửa sổ.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from autopark.application.cusp_policy import CuspPolicy, add_cusp_args, cusp_policy_from_args
from autopark.application.session import Session, SessionError
from autopark.power_throttling import apply_ecoqos_policy
from autopark.storage.scenario_store import (load_scenario, load_vehicle_config, load_vehicle_config_file,
                                            vehicle_config_arg)
from autopark.ui.main_window import MainWindow
from autopark.ui.process_status import add_ecoqos_label

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO = PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json"


def build_window(scenario_path: Path, *, cusp_policy: CuspPolicy | None = None,
                 vehicle_config: Path | None = None) -> MainWindow:
    """Cấu hình xe được chọn thay cấu hình kịch bản và được giữ khi mở kịch bản khác."""
    scenario = load_scenario(scenario_path)
    if vehicle_config is None:
        cfg = load_vehicle_config(scenario.vehicle_config_path)
        return MainWindow(Session(scenario, cfg, cusp_policy=cusp_policy),
                          scenario_path)
    chosen = load_vehicle_config_file(vehicle_config)
    scenario.vehicle_config_path = chosen.path          # lưu kịch bản thì trỏ đúng tệp xe đang dùng
    session = Session(scenario, chosen.cfg, cusp_policy=cusp_policy)
    return MainWindow(session, scenario_path, vehicle_override=chosen)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Đọc `argv` dạng sys.argv (phần tử đầu là tên chương trình): `scenario` (mặc định DEFAULT_SCENARIO),
    `cusp_policy` (`CuspPolicy`) và `vehicle_config` (`VehicleConfigFile` hay None). Sai → mã 2 trước khi có
    QApplication hay cửa sổ."""
    p = argparse.ArgumentParser(prog=Path(argv[0]).name if argv else None, description=__doc__.split("\n")[0])
    p.add_argument("scenario", nargs="?", type=Path, default=DEFAULT_SCENARIO,
                   help=f"tệp kịch bản JSON (mặc định scenarios/{DEFAULT_SCENARIO.name})")
    add_cusp_args(p)
    p.add_argument("--vehicle-config", type=vehicle_config_arg, default=None, metavar="TỆP_XE",
                   help="tệp cấu hình xe JSON thay tệp xe của kịch bản (giữ khi Mở… kịch bản khác); nghiệm thu: "
                        "configs/vehicle_nghiem_thu.json (tối đa 0,10 m/s, N-V1 ĐỀ XUẤT – CHỜ CHỐT)")
    args = p.parse_args(argv[1:])
    args.cusp_policy = cusp_policy_from_args(p, args)
    return args


def main(argv: list[str] | None = None) -> int:
    ecoqos = apply_ecoqos_policy("ui.app")      # trước mọi việc khác (power_throttling.py)
    argv = list(sys.argv if argv is None else argv)
    args = parse_args(argv)
    app = QApplication.instance() or QApplication(argv)
    try:
        window = build_window(args.scenario, cusp_policy=args.cusp_policy,
                              vehicle_config=args.vehicle_config.path if args.vehicle_config is not None else None)
    except SessionError as exc:
        print(f"{Path(argv[0]).name if argv else 'run_app.py'}: lỗi: {exc}", file=sys.stderr)
        return 2
    window.show()
    add_ecoqos_label(window, ecoqos)
    return app.exec()
