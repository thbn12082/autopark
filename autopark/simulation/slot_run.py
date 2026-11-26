"""Chạy kín vòng mô phỏng một lần tự đỗ (thêm 26/11/2026): quét LiDAR → bản đồ → tìm ô → lập đường → bám đường.

Đây là bản tập dượt của lần chạy đỗ thật (việc 3), toàn bộ trong mô phỏng:

1. LiDAR ảo quét sa bàn từ chỗ xe đứng và vài chỗ đặt khác, ra bản đồ lưới (`slot_finder.sim_map`).
2. `slot_finder.find_slots` tìm các ô đỗ trên bản đồ đó.
3. Bộ lập quỹ đạo chỉ thấy **bản đồ** (ô có vật và ô chưa thấy đều chặn), không thấy vật cản thật của sa bàn, giống xe
   thật chỉ biết những gì LiDAR quét được. Ô được chọn là ô gần nhất lập được đường, ưu tiên ô có thành thấy rõ.
4. Bộ bám đường lái xe mô phỏng theo quỹ đạo trong sa bàn **thật**. Va chạm được kiểm với vật cản thật, và kết quả
   chấm theo dung sai đích của sa bàn.

Không giới hạn khoảng cách tới ô: giới hạn thao tác nới theo cỡ sa bàn (`slot_finder.wide_limits`).

    .venv\\Scripts\\python.exe -X utf8 -m autopark.simulation.slot_run --scenario scenarios\\tim_khe_vuong_goc.json --out <thư mục>

Tùy chọn: [--vehicle configs\\vehicle_measured.json] [--slot N] [--mode reverse_in|head_in|parallel]
[--time-limit 15] [--max-try 6] [--resolution 0.02].
Ghi `ket_qua.json` và `ket_qua.png` vào thư mục `--out`.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
import json
import math
from pathlib import Path
import time

import numpy as np

from autopark.domain.types import ParkingMode, Pose, Scenario, VehicleConfig
from autopark.perception.costmap import GridSpec
from autopark.planning import slot_finder as sf
from autopark.planning.types import PlanResult
from autopark.simulation.rollout import RolloutResult, rollout


@dataclass
class SlotRunResult:
    states: np.ndarray
    grid: GridSpec
    candidates: list[sf.SlotCandidate]
    chosen: int | None = None                  # chỉ số trong `candidates`
    mode: ParkingMode | None = None
    plan: PlanResult | None = None
    run_scenario: Scenario | None = None       # sa bàn thật với đích là ô đã chọn
    rollout: RolloutResult | None = None
    attempts: list[dict] = field(default_factory=list)
    timings: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.rollout is not None and self.rollout.report is not None and self.rollout.report.completed

    def summary(self) -> str:
        if not self.candidates:
            return "Không tìm thấy ô đỗ nào trên bản đồ."
        if self.chosen is None:
            return f"Tìm được {len(self.candidates)} ô nhưng không lập được đường vào ô nào."
        cand = self.candidates[self.chosen]
        head = f"Ô {self.chosen + 1} ({sf.KIND_LABEL[cand.kind]}, {self.mode.value})"
        report = self.rollout.report if self.rollout else None
        if report is None:
            return f"{head}: chưa chạy bám đường."
        return f"{head}: {report.describe()}"


def choose_order(cands: list[sf.SlotCandidate]) -> list[int]:
    """Thứ tự thử: ô có thành thấy rõ trước, rồi theo thứ tự của find_slots (gần xe trước)."""
    return sorted(range(len(cands)), key=lambda i: (cands[i].boundary_unknown, i))


def park_in_found_slot(scenario: Scenario, cfg: VehicleConfig, *, resolution: float = 0.02,
                       time_limit: float = 15.0, max_try: int = 6, slot_index: int | None = None,
                       mode: ParkingMode | None = None, map_seed: int = 0) -> SlotRunResult:
    """Chạy cả chuỗi trên `scenario`. `slot_index` (đếm từ 0) và `mode` ép chọn ô và kiểu đỗ; None = tự chọn."""
    start = scenario.start
    t0 = time.perf_counter()
    states, grid = sf.sim_map(scenario, resolution=resolution, seed=map_seed)
    t1 = time.perf_counter()
    cands = sf.find_slots(states, grid, cfg, vehicle_pose=start)
    t2 = time.perf_counter()
    result = SlotRunResult(states, grid, cands, timings={"map_s": round(t1 - t0, 2), "find_s": round(t2 - t1, 2)})
    if not cands:
        return result

    obstacles = sf.map_obstacles(states, grid, cfg, start)
    plan_bounds = sf.Bounds(grid.x_min, grid.y_min, grid.x_max, grid.y_max)
    if slot_index is not None:
        if not 0 <= slot_index < len(cands):
            raise ValueError(f"không có ô {slot_index + 1}; bản đồ có {len(cands)} ô")
        order = [slot_index]
    else:
        order = choose_order(cands)[:max_try]
    for i in order:
        cand = cands[i]
        modes = cand.modes if mode is None else tuple(m for m in cand.modes if m == mode)
        for m in modes:
            tp = time.perf_counter()
            planned, plan = sf.plan_to_slot(cand, m, cfg, start, obstacles, plan_bounds, time_limit=time_limit,
                                            goal_template=scenario.goal)
            entry = {"slot": i + 1, "mode": m.value, **sf.plan_entry(planned.goal.pose, plan, time.perf_counter() - tp)}
            cand.verify[m.value] = {k: v for k, v in entry.items() if k not in ("slot", "mode")}
            result.attempts.append(entry)
            if plan.ok and plan.trajectory is not None:
                result.chosen, result.mode, result.plan = i, m, plan
                break
        if result.chosen is not None:
            break
    t3 = time.perf_counter()
    result.timings["plan_s"] = round(t3 - t2, 2)
    if result.plan is None:
        return result

    # Bám đường trong sa bàn THẬT: va chạm kiểm với vật cản thật, không phải với bản đồ LiDAR.
    truth = replace(scenario, goal=replace(scenario.goal, pose=result.plan.trajectory.goal),
                    maneuver=sf.wide_limits(scenario.bounds), slot=None)
    result.run_scenario = truth
    result.rollout = rollout(truth, cfg, result.plan.trajectory)
    result.timings["rollout_s"] = round(time.perf_counter() - t3, 2)
    return result


# --------------------------------------------------------------------------------------------------------------- vẽ
def render_run(result: SlotRunResult, cfg: VehicleConfig, start: Pose, scale: int = 4) -> np.ndarray:
    """Ảnh của `slot_finder.render_slots` thêm quỹ đạo (xanh = tiến, cam = lùi), vệt xe đã chạy và tư thế cuối."""
    import cv2
    from autopark.geometry.footprint import body_polygon

    img = sf.render_slots(result.states, result.grid, result.candidates, cfg, start, scale=scale)
    g = result.grid

    def px(x, y):
        return (int(round((x - g.x_min) / g.resolution * scale)), int(round((g.y_max - y) / g.resolution * scale)))

    if result.plan is not None and result.plan.trajectory is not None:
        pts = result.plan.trajectory.points
        for a, b in zip(pts, pts[1:]):
            color = (60, 170, 30) if b.direction > 0 else (40, 140, 240)
            cv2.line(img, px(a.pose.x, a.pose.y), px(b.pose.x, b.pose.y), color, 2, cv2.LINE_AA)
    if result.rollout is not None and result.rollout.states:
        trail = np.array([px(s.pose.x, s.pose.y) for s in result.rollout.states], np.int32)
        cv2.polylines(img, [trail], False, (200, 0, 200), 1, cv2.LINE_AA)
        final = result.rollout.states[-1].pose
        report = result.rollout.report
        color = (0, 140, 0) if result.ok else (0, 0, 220)
        if report is not None and report.collided:
            color = (0, 0, 255)
        corners = list(body_polygon(cfg, final).exterior.coords)[:-1]
        cv2.polylines(img, [np.array([px(*q) for q in corners], np.int32)], True, color, 2, cv2.LINE_AA)
    return img


def to_dict(result: SlotRunResult) -> dict:
    report = result.rollout.report if result.rollout is not None else None
    traj = result.plan.trajectory if result.plan is not None else None
    return {
        "ok": result.ok,
        "summary": result.summary(),
        "chosen_slot": None if result.chosen is None else result.chosen + 1,
        "mode": None if result.mode is None else result.mode.value,
        "path_length_m": None if traj is None else round(float(traj.length), 3),
        "cusps": None if traj is None else int(traj.n_cusps),
        "run": None if report is None else {
            "completed": report.completed, "collided": report.collided, "reason": report.reason,
            "sim_time_s": round(report.sim_time, 2), "distance_m": round(report.distance, 3),
            "position_error_m": round(report.position_error, 4),
            "heading_error_deg": round(math.degrees(report.heading_error), 2),
            "collision": None if report.collision is None or report.collision.ok else report.collision.describe(),
        },
        "attempts": result.attempts,
        "timings": result.timings,
        "candidates": [c.to_dict() for c in result.candidates],
    }


# --------------------------------------------------------------------------------------------------------- dòng lệnh
def main(argv=None) -> int:
    from autopark.image_io import imwrite
    from autopark.perception.paths import atomic_write_json, utc_now
    from autopark.storage.scenario_store import load_scenario

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--scenario", type=Path, required=True, help="sa bàn JSON (vật cản thật của mô phỏng)")
    ap.add_argument("--vehicle", type=Path, default=None, help="cấu hình xe; mặc định theo sa bàn hoặc vehicle_measured")
    ap.add_argument("--slot", type=int, default=None, help="ép chọn ô số N (đếm từ 1, theo thứ tự in ra)")
    ap.add_argument("--mode", choices=[m.value for m in ParkingMode], default=None, help="ép kiểu đỗ")
    ap.add_argument("--time-limit", type=float, default=15.0, help="giây cho mỗi lần lập đường")
    ap.add_argument("--max-try", type=int, default=6, help="số ô thử lập đường tối đa")
    ap.add_argument("--resolution", type=float, default=0.02)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    scenario = load_scenario(a.scenario)
    cfg_path = a.vehicle or scenario.vehicle_config_path or sf.DEFAULT_VEHICLE
    cfg = VehicleConfig.from_dict(json.loads(Path(cfg_path).read_text(encoding="utf-8")))
    result = park_in_found_slot(scenario, cfg, resolution=a.resolution, time_limit=a.time_limit, max_try=a.max_try,
                                slot_index=None if a.slot is None else a.slot - 1,
                                mode=None if a.mode is None else ParkingMode(a.mode))
    a.out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(a.out / "ket_qua.json", {"created_utc": utc_now(), "scenario": str(a.scenario),
                                               "vehicle_config": str(cfg_path), **to_dict(result)})
    imwrite(a.out / "ket_qua.png", render_run(result, cfg, scenario.start))
    print(f"{len(result.candidates)} ô đỗ trên bản đồ LiDAR mô phỏng · xe {Path(cfg_path).name}")
    for att in result.attempts:
        extra = f" · {att['path_length_m']:.2f} m, {att['cusps']} lần đổi chiều" if "path_length_m" in att else ""
        print(f"  thử ô {att['slot']} {att['mode']}: {att['status']}{extra}")
    print(result.summary())
    print(f"Đã ghi {a.out / 'ket_qua.json'} và {a.out / 'ket_qua.png'}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
