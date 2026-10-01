"""Điểm vào lập đường đỗ: từ kịch bản (xuất phát, ô đỗ/đích, vật cản) ra quỹ đạo.

Ứng dụng gọi qua đây, nên đây là chỗ duy nhất cần đổi khi thay bộ lập đường.

Mặc định dùng `portfolio.plan`: một thang nhiều nấc, thử từ bộ nhanh nhất tới bộ
đầy đủ nhất, và cho xe mô phỏng chạy thử từng đường trước khi nhận. Đo ngày 08/09/2026
trên bộ 16 ca khó (`autopark/evaluation/`), chưa đo lại; thời gian phụ thuộc tải máy và EcoQoS
của Windows (docs/CHUYEN_MAY_BAN.md mục 8):

| Bộ lập đường | Giải được | Trung vị | Chậm nhất |
|---|---|---|---|
| `hybrid_astar` (bản gốc) | 9/16 | 0,11 s | 6,15 s |
| `cand_lattice_macro` (lưới + nhịp gộp) | 11/16 | 0,03 s | 1,19 s |
| `cand_rrt_rs` (RRT-Connect + Reeds–Shepp) | 12/16 | 0,25 s | 3,40 s |
| `portfolio` (thang, có kiểm chứng) | 12/16 | 0,63 s | 5,42 s |

Đặt `USE_PORTFOLIO = False` để quay lại bản gốc khi cần so sánh.
"""
from __future__ import annotations

from dataclasses import replace

from autopark.control.tracker import TrackerParams
from autopark.domain.computation import ComputationControl
from autopark.domain.types import Scenario, VehicleConfig
from autopark.planning import portfolio
from autopark.planning.hybrid_astar import PlannerParams, PlanResult
from autopark.planning.hybrid_astar import plan as plan_hybrid_astar

USE_PORTFOLIO = True


def plan_parking(scenario: Scenario, cfg: VehicleConfig,
                 params: PlannerParams | portfolio.PortfolioParams | None = None, *,
                 tracker_params: TrackerParams | None = None,
                 max_run_time: float = 180.0,
                 control: ComputationControl | None = None) -> PlanResult:
    """Lập đường đỗ cho một kịch bản. `params.time_limit` là ngân sách tổng."""
    goal = scenario.sync_goal(cfg)
    if scenario.slot is not None and not scenario.slot.fits_vehicle(cfg):
        return PlanResult("GOAL_INVALID", "Ô đỗ nhỏ hơn thân xe; hãy tăng chiều dài hoặc chiều rộng ô")
    if not USE_PORTFOLIO:
        return plan_hybrid_astar(scenario.start, goal, cfg, scenario.obstacles, scenario.bounds, params,
                                control=control)
    p = params if isinstance(params, portfolio.PortfolioParams) else portfolio.PortfolioParams()
    p = replace(p, time_limit=params.time_limit if params is not None else p.time_limit,
                accept_xy=scenario.goal.tolerance_xy, accept_yaw=scenario.goal.tolerance_yaw,
                tracker_params=tracker_params if tracker_params is not None else p.tracker_params,
                verify_max_time=max_run_time)
    return portfolio.plan(scenario.start, goal, cfg, scenario.obstacles, scenario.bounds, params=p,
                          control=control)
