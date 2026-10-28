"""Điểm vào giao diện: nạp kịch bản và cấu hình xe, mở cửa sổ chính.

    python run_app.py [kịch_bản.json] [--max-cusps N] [--warn-cusps N] [--vehicle-config TỆP_XE]
    python run_app.py scenarios\\sa_ban_3x2_hai_hop.json --vehicle-config configs\\vehicle_nghiem_thu.json

Số lần đổi chiều của đường (T12, thêm 02/10/2026; application/cusp_policy.py): `--max-cusps N` từ chối Bắt đầu đỗ khi
đường có hơn N lần đổi chiều (mặc định không chặn: giới hạn CHƯA CHỐT), `--warn-cusps N` cảnh báo khi hơn N (mặc định 7).
Từ đó dòng lệnh được đọc chặt: tham số lạ (trước đây bị bỏ qua) thì báo lỗi và thoát mã 2, trước khi mở cửa sổ.
Tệp sa bàn có trường `acceptance` (02/10/2026, ví dụ scenarios\\nghiem_thu\\do3b.json) dùng giới hạn của kịch bản nghiệm
thu đó trong configs/nguong_nghiem_thu.json (N-D6 (b), ĐỀ XUẤT – CHỜ CHỐT; người dùng giao quyết định 02/10/2026);
`--max-cusps` chỉ siết thêm. Tệp ngưỡng không cho được giới hạn thì báo lỗi và thoát mã 2, trước khi mở cửa sổ.

EcoQoS (02/10/2026, autopark/power_throttling.py): `main()` tự tắt EcoQoS cho tiến trình này trước mọi việc khác (cửa sổ
thu nhỏ làm lập đường hết hạn, docs/VAN_HANH.md) và hiện trạng thái ở thanh trạng thái;
AUTOPARK_KEEP_ECOQOS=1 giữ mặc định của Windows. `build_window` không làm việc đó.

Cấu hình xe (02/10/2026): `--vehicle-config TỆP_XE` thay tệp xe của kịch bản và được giữ khi "Mở…" kịch bản khác (như
`ui.lidar_app`); ô "Cấu hình xe" trong thẻ Xe đổi được khi đang chỉnh hoặc sẵn sàng. Nghiệm thu chạy với
configs/vehicle_nghiem_thu.json (như vehicle_default.json nhưng tối đa 0,10 m/s, N-V1 ĐỀ XUẤT – CHỜ CHỐT; người dùng
giao quyết định 02/10/2026 ('làm hết')); bo mô phỏng tự ghép theo tệp xe (vehicle_io_sim_nghiem_thu.json). Tệp hỏng thì
báo lỗi và thoát mã 2 trước khi mở cửa sổ. Chỉ kiểm bằng test offscreen với bo mô phỏng.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from autopark.application.cusp_policy import (ACCEPTANCE_THRESHOLDS, AcceptanceTagError, CuspPolicy, add_cusp_args,
                                              cusp_policy_from_args)
from autopark.application.session import Session, SessionError
from autopark.power_throttling import apply_ecoqos_policy
from autopark.storage.scenario_store import (load_scenario, load_vehicle_config, load_vehicle_config_file,
                                            vehicle_config_arg)
from autopark.ui.main_window import MainWindow
from autopark.ui.process_status import add_ecoqos_label

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO = PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json"


def build_window(scenario_path: Path, *, cusp_policy: CuspPolicy | None = None,
                 vehicle_config: Path | None = None,
                 acceptance_thresholds: Path | None = ACCEPTANCE_THRESHOLDS) -> MainWindow:
    """`vehicle_config` (nếu có) thay tệp xe của kịch bản, kể cả kịch bản mở sau đó bằng "Mở…"
    (`MainWindow.vehicle_override`). `acceptance_thresholds`: tệp ngưỡng cho tệp sa bàn gắn nghiệm thu (T12); tệp đó
    không cho được giới hạn thì `Session` ném AcceptanceTagError trước khi có cửa sổ."""
    scenario = load_scenario(scenario_path)
    if vehicle_config is None:
        cfg = load_vehicle_config(scenario.vehicle_config_path)
        return MainWindow(Session(scenario, cfg, cusp_policy=cusp_policy, acceptance_thresholds=acceptance_thresholds),
                          scenario_path)
    chosen = load_vehicle_config_file(vehicle_config)
    scenario.vehicle_config_path = chosen.path          # lưu kịch bản thì trỏ đúng tệp xe đang dùng
    session = Session(scenario, chosen.cfg, cusp_policy=cusp_policy, acceptance_thresholds=acceptance_thresholds)
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
    except (AcceptanceTagError, SessionError) as exc:          # tệp sa bàn gắn nghiệm thu mà tệp ngưỡng không cho được giới hạn
        print(f"{Path(argv[0]).name if argv else 'run_app.py'}: lỗi: {exc}", file=sys.stderr)
        return 2
    window.show()
    add_ecoqos_label(window, ecoqos)
    return app.exec()
