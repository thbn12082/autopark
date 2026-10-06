r"""Sinh tệp sa bàn gắn kịch bản nghiệm thu (DO-1 … DO-6, mức MP) cho giao diện và công cụ chấm (thêm 02/10/2026, T12).

Mỗi tệp là một kịch bản có sẵn (scenarios/sa_ban_3x2_hai_hop.json hay một ca khó của evaluation/hard_cases.py mà
docs/KICH_BAN_NGHIEM_THU.md mục 5.1 chỉ tới) cộng trường `acceptance` (domain/types.py `AcceptanceTag`). Mở tệp bằng
`run_app.py` hay `ui.lidar_app` thì Bắt đầu đỗ dùng giới hạn đổi chiều của kịch bản đó trong
configs/nguong_nghiem_thu.json (N-D6 (b): ≤ 2 ở DO-1/2/3a/4a, ≤ 7 ở DO-3b/4b/5/6, DO-3c chỉ báo số; ĐỀ XUẤT – CHỜ
CHỐT, người dùng giao quyết định 02/10/2026 ('làm hết')), và `score_run --layout` chấm với đúng bố trí đó. Tên kịch bản
thêm mã ở đầu ('DO-3b perp_aisle_135'), nên tên sa bàn trên giao diện cho thấy kịch bản. Kích thước lấy theo xe GIẢ
ĐỊNH (ca khó dựng theo xe): xe đo khác thì sinh lại với `--vehicle-config`. DO-2: do2.json là tư thế P1; P2 … P5 người
thử dời xuất phát rồi "Lưu thành…" (trường acceptance được giữ).

    .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.acceptance_scenarios --dry-run
    .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.acceptance_scenarios
    .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.acceptance_scenarios --out scenarios\nghiem_thu --force

Mặc định ghi vào runs\sa_ban_nghiem_thu (không vào Git); bộ tệp trong kho ở scenarios\nghiem_thu (lệnh thứ ba). Xe
mặc định configs/vehicle_nghiem_thu.json (như vehicle_default.json nhưng tối đa 0,10 m/s; cùng kích thước nên cùng
hình học). Mọi thẻ được tra trong tệp ngưỡng TRƯỚC khi ghi; thẻ không tra được hay tệp đích đã có (thiếu `--force`)
thì không ghi tệp nào, mã thoát 2. Ghi xong nạp lại từng tệp để kiểm trường acceptance. Không chạy planner, không mở
thiết bị nào.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import sys

from autopark.application.cusp_policy import (ACCEPTANCE_THRESHOLDS, PROJECT_ROOT, AcceptanceCuspRule,
                                              AcceptanceTagError, read_acceptance_rule)
from autopark.domain.types import AcceptanceTag, Scenario
from autopark.evaluation.hard_cases import build_cases
from autopark.storage.scenario_store import (ACCEPTANCE_VEHICLE_CONFIG, VehicleConfigError, load_scenario,
                                            load_vehicle_config_file, save_scenario, vehicle_config_arg)

SCENARIOS_DIR = PROJECT_ROOT / "scenarios"
COMMITTED_DIR = SCENARIOS_DIR / "nghiem_thu"                 # bộ tệp trong kho (mức MP)
DEFAULT_OUT = PROJECT_ROOT / "runs" / "sa_ban_nghiem_thu"    # mặc định của dòng lệnh: ngoài Git

# Tên tệp → (thẻ, nguồn). Nguồn có đuôi .json là tệp trong scenarios/, còn lại là tên ca của hard_cases.build_cases;
# các ca theo dòng "Bố trí" của KICH_BAN_NGHIEM_THU.md mục 5.1. DI-2 không có tệp: N-D6 (b) không cho DI-2 số nào,
# DI-2 (b) vẫn dùng --max-cusps N.
ACCEPTANCE_FILES: dict[str, tuple[AcceptanceTag, str]] = {
    "do1.json": (AcceptanceTag("DO-1"), "sa_ban_3x2_hai_hop.json"),
    "do2.json": (AcceptanceTag("DO-2"), "sa_ban_3x2_hai_hop.json"),
    "do3a.json": (AcceptanceTag("DO-3", "a"), "perp_aisle_170"),
    "do3b.json": (AcceptanceTag("DO-3", "b"), "perp_aisle_135"),
    "do3c.json": (AcceptanceTag("DO-3", "c"), "perp_aisle_115"),
    "do4a.json": (AcceptanceTag("DO-4", "a"), "parallel_160"),
    "do4b.json": (AcceptanceTag("DO-4", "b"), "parallel_135"),
    "do5.json": (AcceptanceTag("DO-5"), "reverse_long_corridor"),
    "do6.json": (AcceptanceTag("DO-6"), "uturn_w70"),
}


class AcceptanceFilesError(ValueError):
    """Không ghi được bộ tệp (tệp đích đã có mà thiếu --force, nạp lại không đúng); thông điệp nói đã ghi gì chưa."""


def _project_label(path: Path) -> str:
    """Đường dẫn tương đối so với thư mục dự án (posix) khi nằm trong dự án, không thì tuyệt đối: ghi chú không đổi
    theo máy."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def build_acceptance_scenarios(cfg_path: str | Path = ACCEPTANCE_VEHICLE_CONFIG) -> dict[str, Scenario]:
    """Các kịch bản của ACCEPTANCE_FILES (bản sao sâu của nguồn, xe `cfg_path`), đã gắn thẻ, tên thêm mã ở đầu và thêm
    một câu ghi chú cố định (không ngày): nguồn, tệp xe, kích thước theo xe GIẢ ĐỊNH, khóa trong tệp ngưỡng. Tệp xe hỏng
    → VehicleConfigError."""
    chosen = load_vehicle_config_file(cfg_path)
    cases = build_cases(chosen.cfg)
    sources: dict[str, Scenario] = {}
    out: dict[str, Scenario] = {}
    for name, (tag, source) in ACCEPTANCE_FILES.items():
        if source.endswith(".json"):
            if source not in sources:
                sources[source] = load_scenario(SCENARIOS_DIR / source)
            scenario = copy.deepcopy(sources[source])
            origin = f"scenarios/{source}"
        else:
            scenario = copy.deepcopy(cases[source].scenario)
            origin = f"ca khó {source} của evaluation/hard_cases.py"
        scenario.vehicle_config_path = chosen.path
        scenario.acceptance = tag
        scenario.name = f"{tag.label} {scenario.name}"
        sentence = (f"Tệp nghiệm thu {tag.label} (mức MP) sinh bằng autopark.evaluation.acceptance_scenarios từ "
                    f"{origin}, xe {_project_label(chosen.path)}: kích thước theo xe GIẢ ĐỊNH; xe đo khác thì sinh lại. "
                    f"Giới hạn đổi chiều lúc Bắt đầu đỗ theo trường acceptance (khóa {tag.label} của "
                    "configs/nguong_nghiem_thu.json, N-D6 (b), ĐỀ XUẤT – CHỜ CHỐT).")
        scenario.notes = f"{scenario.notes} {sentence}" if scenario.notes else sentence
        out[name] = scenario
    return out


def write_acceptance_scenarios(out_dir: str | Path, cfg_path: str | Path = ACCEPTANCE_VEHICLE_CONFIG, *,
                               thresholds: str | Path = ACCEPTANCE_THRESHOLDS, force: bool = False,
                               dry_run: bool = False) -> list[tuple[Path, AcceptanceCuspRule]]:
    """Ghi bộ tệp vào `out_dir` bằng `save_scenario` và trả (đường dẫn, giới hạn) theo thứ tự ACCEPTANCE_FILES.

    Trước khi ghi: tra mọi thẻ trong `thresholds` (lỗi → AcceptanceTagError), rồi từ chối khi tệp đích đã có mà thiếu
    `force` (AcceptanceFilesError); cả hai trường hợp đều chưa ghi tệp nào. `dry_run`: chỉ kiểm và trả danh sách, không
    tạo thư mục hay tệp nào. Ghi xong nạp lại từng tệp bằng `load_scenario` để kiểm trường acceptance."""
    out = Path(out_dir)
    scenarios = build_acceptance_scenarios(cfg_path)
    planned = [(out / name, read_acceptance_rule(scenario.acceptance, thresholds))
               for name, scenario in scenarios.items()]
    existing = [path.name for path, _ in planned if path.exists()]
    if existing and not force:
        raise AcceptanceFilesError(f"{out}: đã có {', '.join(existing)}; thêm --force để ghi đè (chưa ghi tệp nào)")
    if dry_run:
        return planned
    for path, _ in planned:
        save_scenario(scenarios[path.name], path)
    for path, _ in planned:
        loaded = load_scenario(path).acceptance
        if loaded != scenarios[path.name].acceptance:
            raise AcceptanceFilesError(f"{path}: nạp lại được acceptance {loaded!r}, cần "
                                       f"{scenarios[path.name].acceptance!r}")
    return planned


def describe_file(path: Path, rule: AcceptanceCuspRule) -> str:
    """Một dòng in ra cho mỗi tệp, ví dụ 'do3b.json  DO-3b  đổi chiều ≤ 7  ← perp_aisle_135'."""
    limit = "đổi chiều: chỉ báo số" if rule.max_cusps is None else f"đổi chiều ≤ {rule.max_cusps}"
    return f"{path.name}  {rule.tag.label}  {limit}  ← {ACCEPTANCE_FILES[path.name][1]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m autopark.evaluation.acceptance_scenarios",
                                     description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="thư mục ghi (mặc định runs/sa_ban_nghiem_thu; bộ tệp trong kho: scenarios/nghiem_thu)")
    parser.add_argument("--vehicle-config", type=vehicle_config_arg, default=None, metavar="TỆP_XE",
                        help="tệp xe để dựng kích thước và ghi vào kịch bản (mặc định configs/vehicle_nghiem_thu.json)")
    parser.add_argument("--thresholds", type=Path, default=ACCEPTANCE_THRESHOLDS,
                        help="tệp ngưỡng để tra thẻ (mặc định configs/nguong_nghiem_thu.json)")
    parser.add_argument("--force", action="store_true", help="ghi đè tệp đã có")
    parser.add_argument("--dry-run", action="store_true", help="chỉ kiểm và in danh sách, không ghi gì")
    args = parser.parse_args(argv)
    cfg_path = args.vehicle_config.path if args.vehicle_config is not None else ACCEPTANCE_VEHICLE_CONFIG
    try:
        planned = write_acceptance_scenarios(args.out, cfg_path, thresholds=args.thresholds, force=args.force,
                                             dry_run=args.dry_run)
    except (AcceptanceTagError, AcceptanceFilesError, VehicleConfigError) as exc:
        print(f"acceptance_scenarios: lỗi: {exc}", file=sys.stderr)
        return 2
    for path, rule in planned:
        print(describe_file(path, rule))
    verb = "Sẽ ghi (--dry-run, chưa ghi gì)" if args.dry_run else "Đã ghi"
    print(f"{verb} {len(planned)} tệp vào {args.out}; xe {_project_label(Path(cfg_path))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
