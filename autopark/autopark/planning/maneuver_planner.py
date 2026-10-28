"""Lập một thao tác gần, kiểm tra giới hạn và khả năng bám trước khi nhận đường."""
from __future__ import annotations

from dataclasses import replace

from autopark.control.tracker import TrackerParams
from autopark.domain.computation import ComputationControl
from autopark.domain.types import Scenario, VehicleConfig
from autopark.planning import portfolio
from autopark.planning.hybrid_astar import PlannerParams, PlanResult
from autopark.planning.maneuver import maneuver_bounds, request_problem, trajectory_problem


def plan_maneuver(scenario: Scenario, cfg: VehicleConfig,
                 params: PlannerParams | portfolio.PortfolioParams | None = None, *,
                 tracker_params: TrackerParams | None = None,
                 max_run_time: float = 180.0,
                 control: ComputationControl | None = None) -> PlanResult:
    """Lập đường cho một thao tác gần; `params.time_limit` là ngân sách tổng."""
    goal = scenario.goal.pose
    problem = request_problem(scenario, cfg)
    if problem:
        return PlanResult("MANEUVER_LIMIT", problem)
    bounds = maneuver_bounds(scenario)
    p = params if isinstance(params, portfolio.PortfolioParams) else portfolio.PortfolioParams()
    p = replace(p, time_limit=params.time_limit if params is not None else p.time_limit,
                accept_xy=scenario.goal.tolerance_xy, accept_yaw=scenario.goal.tolerance_yaw,
                tracker_params=tracker_params if tracker_params is not None else p.tracker_params,
                verify_max_time=max_run_time, verify_scenario=scenario)
    if scenario.maneuver is not None:
        p = replace(p, max_path_length=scenario.maneuver.max_path_length_m,
                    max_cusps=scenario.maneuver.max_cusps)
    result = portfolio.plan(scenario.start, goal, cfg, scenario.obstacles, bounds, params=p, control=control)
    if result.ok and result.trajectory is not None:
        problem = trajectory_problem(scenario, cfg, result.trajectory)
        if problem:
            return PlanResult("MANEUVER_LIMIT", problem)
    return result
