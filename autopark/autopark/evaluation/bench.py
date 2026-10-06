"""Chạy bộ ca khó qua một bộ lập đường bất kỳ và in bảng kết quả.

Dùng:
    python -m autopark.evaluation.bench                                  # bộ lập đường mặc định
    python -m autopark.evaluation.bench --planner autopark.planning.x:plan
    python -m autopark.evaluation.bench --time-limit 20 --cases parallel_122,uturn_w55
    python -m autopark.evaluation.bench --json ket_qua.json

Giao diện mà một bộ lập đường ứng viên phải theo:

    plan(start, goal, cfg, obstacles, bounds, params=None) -> PlanResult

`PlanResult` lấy từ `autopark.planning.hybrid_astar`. Nếu hàm nhận thêm tham số
`time_limit` thì bench sẽ truyền vào; nếu không, bench đặt `params.time_limit`
khi ứng viên chấp nhận một đối tượng params có thuộc tính đó.

Mỗi ca được chấm hai lớp:
1. Lập đường: trạng thái, thời gian, độ dài, số lần đổi chiều.
2. Bám đường kín vòng trên xe mô phỏng: có tới đích trong dung sai không, có va chạm không.
Một đường "tìm được" nhưng xe không bám nổi thì không tính là thành công.
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
from pathlib import Path
import math
import sys
import time
from dataclasses import asdict, dataclass, field

from autopark.domain.types import VehicleConfig
from autopark.evaluation.hard_cases import HardCase, build_cases
from autopark.geometry.footprint import check_motion
from autopark.planning.hybrid_astar import PlannerParams
from autopark.power_throttling import apply_ecoqos_policy, ecoqos_state
from autopark.simulation.rollout import rollout
from autopark.storage.scenario_store import load_vehicle_config

DEFAULT_PLANNER = "autopark.planning.portfolio:plan"
DEFAULT_CONFIG = "configs/vehicle_default.json"


@dataclass
class CaseResult:
    name: str
    difficulty: str
    expected: str
    status: str
    elapsed: float
    popped: int = 0
    expanded: int = 0
    length: float = 0.0
    cusps: int = 0
    path_ok: bool = False        # đường không va chạm khi kiểm tra lại độc lập
    tracked: bool = False        # xe mô phỏng bám tới đích trong dung sai
    pos_err: float = float("nan")
    yaw_err: float = float("nan")
    message: str = ""

    @property
    def solved(self) -> bool:
        return self.status == "OK" and self.path_ok and self.tracked


def load_planner(spec: str):
    module_name, _, func_name = spec.partition(":")
    if not func_name:
        raise SystemExit(f"--planner phải có dạng module:ham, nhận được {spec!r}")
    module = importlib.import_module(module_name)
    return getattr(module, func_name)


def _call_planner(func, case: HardCase, cfg: VehicleConfig, time_limit: float):
    sc = case.scenario
    sig = inspect.signature(func)
    kwargs = {}
    if "time_limit" in sig.parameters:
        kwargs["time_limit"] = time_limit
    elif "params" in sig.parameters:
        params = PlannerParams()
        params.time_limit = time_limit
        kwargs["params"] = params
    return func(sc.start, sc.goal.pose, cfg, sc.obstacles, sc.bounds, **kwargs)


def run_case(func, case: HardCase, cfg: VehicleConfig, time_limit: float,
             do_rollout: bool = True) -> CaseResult:
    sc = case.scenario
    t0 = time.perf_counter()
    try:
        result = _call_planner(func, case, cfg, time_limit)
    except Exception as exc:  # noqa: BLE001 - lỗi của ứng viên phải hiện ra, không được nuốt
        return CaseResult(case.name, case.difficulty, case.expected, "ERROR",
                          time.perf_counter() - t0, message=repr(exc))
    elapsed = getattr(result, "elapsed", 0.0) or (time.perf_counter() - t0)
    out = CaseResult(case.name, case.difficulty, case.expected, result.status, elapsed,
                     getattr(result, "popped", 0), getattr(result, "expanded", 0),
                     message=result.message)
    traj = getattr(result, "trajectory", None)
    if result.status != "OK" or traj is None:
        return out
    out.length = traj.length
    out.cusps = traj.n_cusps

    # Kiểm tra lại đường một cách độc lập với bộ lập đường
    out.path_ok = True
    for a, b in zip(traj.points, traj.points[1:]):
        if not check_motion(cfg, a.pose, b.pose, sc.obstacles, sc.bounds).ok:
            out.path_ok = False
            out.message = "Đường vi phạm kiểm tra vùng quét độc lập"
            break
    if not out.path_ok or not do_rollout:
        return out

    run = rollout(sc, cfg, traj, max_time=240.0)
    rep = run.report
    out.pos_err, out.yaw_err = rep.position_error, rep.heading_error
    out.tracked = bool(rep.completed and not rep.collided
                       and rep.position_error <= sc.goal.tolerance_xy
                       and abs(rep.heading_error) <= sc.goal.tolerance_yaw)
    if not out.tracked:
        out.message = "Bám đường không đạt: " + rep.describe()
    return out


def format_table(results: list[CaseResult]) -> str:
    head = f"{'ca':<22}{'mức':<8}{'kỳ vọng':<10}{'kết quả':<12}{'giây':>7}{'nút':>9}{'dài m':>8}{'cusp':>6}  ghi chú"
    lines = [head, "-" * len(head)]
    for r in results:
        verdict = "GIẢI ĐƯỢC" if r.solved else ("bám hỏng" if r.status == "OK" else r.status)
        note = "" if r.solved else r.message[:52]
        lines.append(f"{r.name:<22}{r.difficulty:<8}{r.expected:<10}{verdict:<12}"
                     f"{r.elapsed:>7.2f}{r.popped:>9}{r.length:>8.2f}{r.cusps:>6}  {note}")
    solved = [r for r in results if r.solved]
    lines.append("-" * len(head))
    for level in ("easy", "tight", "xtight"):
        group = [r for r in results if r.difficulty == level]
        if group:
            n = sum(1 for r in group if r.solved)
            lines.append(f"  {level:<8} {n}/{len(group)} giải được")
    lines.append(f"  TỔNG    {len(solved)}/{len(results)} giải được, "
                 f"thời gian lập đường tổng {sum(r.elapsed for r in results):.1f} s")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ecoqos = apply_ecoqos_policy("evaluation.bench")   # trước mọi việc khác: các ca chạy theo hạn giờ đồng hồ thật
    ap = argparse.ArgumentParser(description="Đo bộ lập đường trên bộ ca khó")
    ap.add_argument("--planner", default=DEFAULT_PLANNER)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--time-limit", type=float, default=20.0)
    ap.add_argument("--cases", default="", help="danh sách tên ca, phân cách bằng dấu phẩy")
    ap.add_argument("--difficulty", default="", help="lọc theo mức: easy, tight, xtight")
    ap.add_argument("--no-rollout", action="store_true")
    ap.add_argument("--json", default="", help="ghi kết quả ra file JSON")
    args = ap.parse_args(argv)
    if args.json:
        # Tạo thư mục TRƯỚC khi chạy các ca (25/09/2026): trước đó đường dẫn vào thư mục chưa có chỉ hỏng ở cuối,
        # sau khi đã chạy hết ca (có thể vài phút), và mất kết quả.
        try:
            Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            ap.error(f"--json: không tạo được thư mục cho {args.json}: {exc}")

    cfg = load_vehicle_config(args.config)
    func = load_planner(args.planner)
    cases = build_cases(cfg)
    names = [n.strip() for n in args.cases.split(",") if n.strip()] or list(cases)
    unknown = [n for n in names if n not in cases]
    if unknown:
        raise SystemExit(f"Không có ca: {', '.join(unknown)}. Có: {', '.join(cases)}")
    selected = [cases[n] for n in names]
    if args.difficulty:
        selected = [c for c in selected if c.difficulty == args.difficulty]

    print(f"Bộ lập đường: {args.planner}   giới hạn {args.time_limit:.0f} s/ca   xe: {cfg.name}")
    print(ecoqos.cli_line())
    results = []
    for case in selected:
        r = run_case(func, case, cfg, args.time_limit, do_rollout=not args.no_rollout)
        results.append(r)
        flag = "OK " if r.solved else "HỎNG"
        print(f"  [{flag}] {r.name:<22} {r.status:<12} {r.elapsed:6.2f}s  cusp={r.cusps}  {r.message[:60]}")
        sys.stdout.flush()
    print()
    print(format_table(results))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"planner": args.planner, "ecoqos": ecoqos_state(), "results": [asdict(r) for r in results]}, f,
                      ensure_ascii=False, indent=2)
        print(f"\nĐã ghi {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
