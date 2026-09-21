"""Bộ lập đường kiểu danh mục: leo thang cấu hình và tự kiểm chứng bằng mô phỏng.

Vì sao lại là kiến trúc này, theo đúng những gì đã đo được:

1. **Góc lái là một mâu thuẫn, không phải một hằng số.** Cắt góc lái cho bộ bám
   đường có dư địa sửa sai thì ô đỗ chật mất nghiệm (duyệt rộng không chạm tới đích
   ở ca `parallel_135` khi chỉ dùng 90% góc lái, nhưng chạm tới khi dùng đủ). Dùng
   hết góc lái thì có nghiệm, nhưng sai số hướng cuối vọt từ 3° lên 5–13° vì bộ bám
   chỉ còn sửa được một phía. Không có giá trị nào đúng cho mọi ca, nên phải thử dần.

2. **Lề an toàn cũng vậy.** Lề 1 cm với khoảng hở 2 cm khiến xe đã nằm trong ô
   không nhúc nhích được: tìm ngược từ đích chết ngay ở nút đầu tiên.

3. **Một đường tồn tại chưa chắc chạy được.** Nên mỗi ứng viên đều được cho xe mô
   phỏng chạy thử kín vòng; chỉ đường nào xe bám tới đích trong dung sai mới được nhận.
   Nếu không nấc nào đạt dung sai nghiệm thu, trả về TRACKING_FAILED; đường ứng
   viên chỉ phục vụ chẩn đoán, không được coi là sẵn sàng chạy.

Mỗi nấc là một bộ lập đường và tham số; có thể chèn thêm bộ lập đường khác
vào thang bằng cách sửa `default_ladder()`.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace
from typing import Callable

from autopark.domain.computation import ComputationTimedOut, current_control
from autopark.planning.computation import controlled_plan
from autopark.control.tracker import TrackerParams
from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario, VehicleConfig
from autopark.planning import cand_lattice_macro as lattice
from autopark.planning import cand_reference as ref
from autopark.planning import cand_rrt_rs as rrt
from autopark.planning.hybrid_astar import PlanResult
from autopark.simulation.rollout import rollout


@dataclass
class Rung:
    """Một nấc trong thang: bộ lập đường, tham số, ngân sách thời gian."""

    name: str
    planner: Callable[..., PlanResult]
    params: object
    budget: float
    note: str = ""


@dataclass
class PortfolioParams:
    time_limit: float = 8.0
    verify: bool = True                     # cho xe mô phỏng chạy thử trước khi nhận đường
    # Hai ngưỡng khác nhau, đừng lẫn:
    #  - `verify_*` là mức "đủ tốt để DỪNG leo thang": chặt hơn, để còn cố tìm đường đẹp hơn;
    #  - `accept_*` là mức "đủ tốt để NHẬN": bằng dung sai nghiệm thu.
    # Trước đây chỉ có một ngưỡng nên đường sai 4,0° bị dán cảnh báo dù vẫn đạt dung sai 5°.
    verify_xy: float = 0.04
    verify_yaw: float = math.radians(4.0)
    accept_xy: float = 0.05
    accept_yaw: float = math.radians(5.0)
    verify_max_time: float = 240.0
    tracker_params: TrackerParams | None = None
    ladder: list[Rung] | None = None


def default_ladder() -> list[Rung]:
    """Thang từ nhanh nhất tới đầy đủ nhất, chọn theo số đo trên 16 ca khó.

    Nấc 1–2 dùng LƯỚI CÓ THAO TÁC GỘP. Mỗi hành động mở rộng là trọn một nhịp đẩy
    tới-lui, nên lưới được phép thô (4,5 cm) mà vẫn biểu diễn được thao tác tinh.
    Đo được: lưới thô cộng nhịp gộp nhanh hơn hẳn lưới mịn cộng nhịp gộp, vì số
    trạng thái nhỏ hơn nhiều. Bản này giải ca cột chắn cửa ô trong 0,04 giây so với
    4,59 giây của bản gốc.

    Nấc 3 dùng RRT-Connect với hàm lái Reeds–Shepp. Nó không có lưới nên không có
    giới hạn biểu diễn, và là bộ duy nhất giải được ca đỗ song song chật
    `parallel_135` (1,14 giây) — ca đã được duyệt rộng chứng minh là có nghiệm.
    Đổi lại nó ngẫu nhiên và cho đường xấu hơn, nên chỉ dùng khi hai nấc trên bó tay.

    Nấc 4 là Hybrid A* mịn có nhịp gộp, giữ làm lưới an toàn cho các hình thế mà
    RRT-Connect gặp khó.
    """
    return [
        Rung("gộp-nhanh", lattice.plan, lattice.LatticeParams(), budget=1.0,
             note="lưới thô + nhịp gộp: xong ngay với phần lớn ca"),
        Rung("gộp-kỹ", lattice.plan, lattice.LatticeParams(), budget=1.5,
             note="cùng bộ lập đường, thêm thời gian để nó tự leo qua các chặng bên trong"),
        Rung("ngẫu nhiên", rrt.plan, rrt.RRTParams(), budget=4.0,
             note="RRT-Connect + Reeds–Shepp: không có lưới nên không kẹt biểu diễn"),
        Rung("lưới mịn", ref.plan,
             ref.RefParams(steer_ratio=0.90, safety_margin=0.012, xy_resolution=0.025,
                           yaw_resolution=math.radians(5.0), step_length=0.04, n_steer=9,
                           heuristic_weight=2.6, use_macros=True),
             budget=1.5, note="lưới mịn: bắt các hình thế mà RRT khó trúng"),
    ]


@dataclass
class Attempt:
    rung: str
    status: str
    seconds: float
    tracked: bool = False
    position_error: float = float("nan")
    heading_error: float = float("nan")
    note: str = ""


def _as_scenario(start: Pose, goal: Pose, obstacles: list[Obstacle], bounds: Bounds) -> Scenario:
    return Scenario(name="portfolio", bounds=bounds, start=start, goal=ParkingGoal(goal),
                    obstacles=list(obstacles))


@controlled_plan(8.0)
def plan(start: Pose, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle],
         bounds: Bounds, params=None, time_limit: float | None = None,
         attempts: list[Attempt] | None = None) -> PlanResult:
    """Thử từng nấc cho tới khi có đường mà xe mô phỏng bám được.

    Truyền một list vào `attempts` để nhận nhật ký từng nấc đã thử.
    """
    p = params if isinstance(params, PortfolioParams) else PortfolioParams()
    if params is not None and not isinstance(params, PortfolioParams) and getattr(params, "time_limit", None):
        p = replace(p, time_limit=params.time_limit)
    if time_limit is not None:
        p = replace(p, time_limit=time_limit)
    ladder = p.ladder or default_ladder()

    t0 = time.perf_counter()
    log: list[Attempt] = attempts if attempts is not None else []
    scenario = _as_scenario(start, goal, obstacles, bounds) if p.verify else None
    if scenario is not None:
        scenario.goal = ParkingGoal(goal, p.accept_xy, p.accept_yaw)
    fallback: PlanResult | None = None
    fallback_note = ""
    fallback_ok = False
    fallback_score = (True, math.inf, math.inf, math.inf, math.inf)
    last_failure: PlanResult | None = None

    # Chia đều phần thời gian dôi ra cho các nấc, giữ đúng tổng ngân sách
    total_budget = sum(r.budget for r in ladder)
    scale = p.time_limit / total_budget if total_budget > 0 else 1.0

    for rung in ladder:
        current_control().check_cancelled()
        remaining = current_control().deadline - time.perf_counter()
        if remaining <= 0.05:
            break
        budget = min(rung.budget * scale, remaining)
        t1 = time.perf_counter()
        result = rung.planner(start, goal, cfg, obstacles, bounds,
                              params=replace(rung.params, time_limit=budget))
        took = time.perf_counter() - t1

        if result.status == "CANCELLED":
            return result

        if result.status in ("GOAL_INVALID", "START_INVALID"):
            log.append(Attempt(rung.name, result.status, took, note=result.message))
            return result                                # sai đầu bài: leo thang cũng vô ích
        if not result.ok or result.trajectory is None:
            log.append(Attempt(rung.name, result.status, took, note=result.message[:90]))
            last_failure = result
            continue
        if not p.verify or scenario is None:
            log.append(Attempt(rung.name, "OK", took, tracked=True, note="không kiểm chứng"))
            return _stamp(result, rung, log, time.perf_counter() - t0)

        try:
            run = rollout(scenario, cfg, result.trajectory, tracker_params=p.tracker_params,
                          max_time=p.verify_max_time)
        except ComputationTimedOut:
            log.append(Attempt(rung.name, "TIMEOUT", time.perf_counter() - t1,
                               note="Hết thời gian kiểm chứng"))
            last_failure = PlanResult("TIMEOUT", "Hết thời gian kiểm chứng đường")
            break
        rep = run.report
        tracked = bool(rep.completed and not rep.collided
                       and rep.position_error <= min(p.verify_xy, p.accept_xy)
                       and abs(rep.heading_error) <= min(p.verify_yaw, p.accept_yaw))
        log.append(Attempt(rung.name, "OK", took, tracked, rep.position_error, rep.heading_error,
                           "" if tracked else rep.describe()[:90]))
        if tracked:
            # Cả hai đều đạt nghiệm thu: không đổi đường ngắn, ít thao tác lấy
            # nhiều nhịp tới/lui chỉ để cải thiện một phần nhỏ sai số góc cuối.
            if fallback_ok and (fallback.trajectory.n_cusps, fallback.trajectory.length) < \
                    (result.trajectory.n_cusps, result.trajectory.length):
                break
            return _stamp(result, rung, log, time.perf_counter() - t0)
        # Đường đạt CẢ HAI dung sai luôn đứng trước đường không đạt, dù lệch hướng ít hơn.
        acceptable = (rep.position_error <= p.accept_xy
                      and abs(rep.heading_error) <= p.accept_yaw)
        score = (not acceptable,
                 result.trajectory.n_cusps if acceptable else math.inf,
                 result.trajectory.length if acceptable else math.inf,
                 abs(rep.heading_error), rep.position_error)
        finished = rep.completed or getattr(rep, "path_finished", False)
        if finished and not rep.collided and (fallback is None or score < fallback_score):
            fallback = result
            fallback_score = score
            fallback_ok = acceptable
            fallback_note = (f"nấc '{rung.name}': xe mô phỏng dừng cách đích "
                             f"{rep.position_error * 100:.1f} cm / {math.degrees(rep.heading_error):+.1f}°")

    elapsed = time.perf_counter() - t0
    if fallback is not None:
        traj = fallback.trajectory
        head = f"Tìm được đường dài {traj.length:.2f} m, {traj.n_cusps} lần đổi chiều"
        tail = (f" [{fallback_note}, trong dung sai]" if fallback_ok
                else f" — CẢNH BÁO: NGOÀI dung sai ({fallback_note})")
        return PlanResult("OK" if fallback_ok else "TRACKING_FAILED", head + tail, traj, elapsed,
                          fallback.expanded, fallback.popped, fallback.rs_tries, fallback.margin_used)
    if last_failure is not None:
        return PlanResult(last_failure.status,
                          f"Đã thử {len(log)} nấc, không nấc nào ra đường. Cuối cùng: {last_failure.message}",
                          None, elapsed, last_failure.expanded, last_failure.popped)
    return PlanResult("TIMEOUT", "Không nấc nào chạy được trong ngân sách thời gian", None, elapsed)


def _stamp(result: PlanResult, rung: Rung, log: list[Attempt], elapsed: float) -> PlanResult:
    traj = result.trajectory
    return PlanResult(
        "OK",
        f"Tìm được đường dài {traj.length:.2f} m, {traj.n_cusps} lần đổi chiều "
        f"[nấc '{rung.name}', {len(log)} lần thử, {elapsed:.2f} s]",
        traj, elapsed, result.expanded, result.popped, result.rs_tries, result.margin_used)
