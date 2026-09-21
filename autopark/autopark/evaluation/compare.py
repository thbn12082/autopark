"""Chạy nhiều bộ lập đường trên cùng bộ ca khó và in một bảng so sánh duy nhất.

Dùng:
    python -m autopark.evaluation.compare --planners goc=autopark.planning.hybrid_astar:plan,moi=autopark.planning.cand_x:plan
    python -m autopark.evaluation.compare --all --time-limit 10 --json ket_qua.json

Mỗi ô trong bảng là kết quả của một bộ lập đường trên một ca: dấu chấm nghĩa là
giải được (kèm số giây), còn lại là mã trạng thái. Quy tắc chấm giống `bench.py`:
đường phải qua kiểm tra vùng quét thật và xe mô phỏng phải bám tới đích trong dung sai.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict

from autopark.evaluation.bench import CaseResult, load_planner, run_case
from autopark.evaluation.hard_cases import build_cases
from autopark.storage.scenario_store import load_vehicle_config

KNOWN = {
    "goc": "autopark.planning.hybrid_astar:plan",
    "doi_chung": "autopark.planning.cand_reference:plan",
    "hybrid_fast": "autopark.planning.cand_hybrid_fast:plan",
    "hai_chieu": "autopark.planning.cand_bidirectional:plan",
    "rrt": "autopark.planning.cand_rrt_rs:plan",
    "macro": "autopark.planning.cand_lattice_macro:plan",
    "anytime": "autopark.planning.cand_anytime:plan",
    "roadmap": "autopark.planning.cand_rs_roadmap:plan",
}


def short(r: CaseResult) -> str:
    if r.solved:
        return f"{r.elapsed:5.2f}s"
    return {"NO_PATH": " kh.duong", "TIMEOUT": " het gio", "GOAL_INVALID": " dich xau",
            "START_INVALID": " xp xau", "ERROR": "  LOI  "}.get(r.status, f" {r.status[:7]}") \
        if r.status != "OK" else " bam hong"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="So sánh nhiều bộ lập đường")
    ap.add_argument("--planners", default="", help="ten=module:ham, phân cách bằng dấu phẩy")
    ap.add_argument("--all", action="store_true", help="dùng mọi bộ lập đường đã biết, bỏ qua cái nào chưa có")
    ap.add_argument("--config", default="configs/vehicle_default.json")
    ap.add_argument("--time-limit", type=float, default=10.0)
    ap.add_argument("--cases", default="")
    ap.add_argument("--json", default="")
    args = ap.parse_args(argv)

    cfg = load_vehicle_config(args.config)
    cases = build_cases(cfg)
    names = [n.strip() for n in args.cases.split(",") if n.strip()] or list(cases)

    specs: dict[str, str] = {}
    if args.all:
        specs.update(KNOWN)
    for item in args.planners.split(","):
        item = item.strip()
        if not item:
            continue
        label, _, spec = item.partition("=")
        specs[label if spec else label] = spec or label

    loaded: dict[str, object] = {}
    for label, spec in specs.items():
        try:
            loaded[label] = load_planner(spec)
        except Exception as exc:  # noqa: BLE001 - bỏ qua ứng viên chưa tồn tại
            print(f"bỏ qua {label}: {exc}", file=sys.stderr)
    if not loaded:
        raise SystemExit("không nạp được bộ lập đường nào")

    results: dict[str, dict[str, CaseResult]] = {label: {} for label in loaded}
    for label, func in loaded.items():
        for name in names:
            r = run_case(func, cases[name], cfg, args.time_limit)
            results[label][name] = r
            print(f"  {label:<12} {name:<22} {'OK ' if r.solved else 'HỎNG'} {r.elapsed:6.2f}s", flush=True)

    labels = list(loaded)
    width = max(len(n) for n in names) + 2
    header = "ca".ljust(width) + "mức".ljust(8) + "".join(l.center(11) for l in labels)
    print()
    print(header)
    print("-" * len(header))
    for name in names:
        row = name.ljust(width) + cases[name].difficulty.ljust(8)
        for label in labels:
            row += short(results[label][name]).center(11)
        print(row)
    print("-" * len(header))
    tot = "TỔNG giải được".ljust(width + 8)
    med = "thời gian trung vị".ljust(width + 8)
    worst = "chậm nhất".ljust(width + 8)
    for label in labels:
        rs = [results[label][n] for n in names]
        solved = [r for r in rs if r.solved]
        tot += f"{len(solved)}/{len(rs)}".center(11)
        med += (f"{statistics.median([r.elapsed for r in solved]):.2f}s" if solved else "-").center(11)
        worst += (f"{max(r.elapsed for r in solved):.2f}s" if solved else "-").center(11)
    print(tot)
    print(med)
    print(worst)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({label: {n: asdict(r) for n, r in rows.items()} for label, rows in results.items()},
                      f, ensure_ascii=False, indent=2)
        print(f"\nĐã ghi {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
