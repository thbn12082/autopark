"""Regression cases for accepting a path after closed-loop verification."""
import math
import pytest
from dataclasses import replace

from autopark.control.tracker import TrackerParams
from autopark.domain.types import VehicleState
from autopark.planning import maneuver_planner, portfolio
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.trajectory import build_trajectory
from autopark.simulation.rollout import RolloutResult, RunReport


def verified_candidates(monkeypatch, scenario, cfg, errors, **params):
    trajectories = [build_trajectory([(scenario.start, 1, 0.0)], scenario.goal.pose,
                                     cfg, 0.15, 0.08) for _ in errors]
    candidates = iter(trajectories)
    reports = iter(errors)

    def candidate(*args, **kwargs):
        return PlanResult("OK", "candidate", next(candidates))

    def verify(*args, **kwargs):
        xy, yaw = next(reports)
        state = VehicleState(scenario.start, 0.0, 0.0, 1.0)
        return RolloutResult(report=RunReport(True, False, 1.0, 0.0, state, xy, math.radians(yaw)))

    monkeypatch.setattr(portfolio, "rollout", verify)
    ladder = [portfolio.Rung(str(i), candidate, portfolio.ref.RefParams(), 1.0)
              for i in range(len(errors))]
    result = portfolio.plan(scenario.start, scenario.goal.pose, cfg, scenario.obstacles,
                            scenario.bounds, portfolio.PortfolioParams(ladder=ladder, **params))
    return result, trajectories


def test_acceptable_fallback_beats_lower_heading_error(monkeypatch, scenario, cfg):
    result, paths = verified_candidates(monkeypatch, scenario, cfg,
                                       [(0.06, 1.0), (0.03, 4.5)])
    assert result.ok
    assert result.trajectory is paths[1]


def test_outside_tolerance_is_not_ok(monkeypatch, scenario, cfg):
    result, _ = verified_candidates(monkeypatch, scenario, cfg, [(0.06, 1.0)])
    assert result.status == "TRACKING_FAILED"
    assert not result.ok


def test_early_exit_cannot_bypass_acceptance_tolerance(monkeypatch, scenario, cfg):
    result, _ = verified_candidates(monkeypatch, scenario, cfg, [(0.03, 1.0)], accept_xy=0.01)
    assert not result.ok


def test_parking_uses_scenario_tolerances(monkeypatch, scenario, cfg):
    scenario.goal = replace(scenario.goal, tolerance_xy=0.01, tolerance_yaw=math.radians(1))
    captured = {}

    def plan(*args, params=None, **kwargs):
        captured["params"] = params
        return PlanResult("NO_PATH", "test")

    monkeypatch.setattr(portfolio, "plan", plan)
    maneuver_planner.plan_maneuver(scenario, cfg)
    p = captured["params"]
    assert p.accept_xy == scenario.goal.tolerance_xy
    assert p.accept_yaw == scenario.goal.tolerance_yaw
    assert p.verify_max_time == 180.0


def test_parking_verifies_with_the_controller_used_for_execution(monkeypatch, scenario, cfg):
    captured = {}

    def plan(*args, params=None, **kwargs):
        captured["params"] = params
        return PlanResult("NO_PATH", "test")

    monkeypatch.setattr(portfolio, "plan", plan)
    tracker = TrackerParams(k_lateral=0.5)
    maneuver_planner.plan_maneuver(scenario, cfg, tracker_params=tracker, max_run_time=30.0)
    assert captured["params"].tracker_params == tracker
    assert captured["params"].verify_max_time == 30.0


def test_fewer_cusps_wins_between_verified_acceptable_paths(monkeypatch, scenario, cfg):
    from autopark.domain.types import Pose

    paths = []
    for n_cusps in (9, 42):
        raw = [(Pose(0.5 + k * 0.02, 1.0, 0.0), (-1) ** (k // 2), 0.0)
               for k in range(2 * (n_cusps + 1))]
        paths.append(build_trajectory(raw, scenario.goal.pose, cfg, 0.15, 0.08))
    candidates = iter(paths)
    headings = iter([4.04, 1.0])

    def candidate(*args, **kwargs):
        return PlanResult("OK", "test", next(candidates))

    def verify(*args, **kwargs):
        state = VehicleState(scenario.start, 0.0, 0.0, 1.0)
        report = RunReport(True, False, 1.0, 0.0, state, 0.01, math.radians(next(headings)))
        return RolloutResult(report=report)

    monkeypatch.setattr(portfolio, "rollout", verify)
    params = portfolio.PortfolioParams(ladder=[
        portfolio.Rung(str(i), candidate, portfolio.ref.RefParams(), 1.0) for i in range(2)])
    result = portfolio.plan(scenario.start, scenario.goal.pose, cfg, scenario.obstacles,
                            scenario.bounds, params=params)
    assert result.ok
    assert result.trajectory is paths[0]
    assert result.trajectory.n_cusps == 9


@pytest.mark.parametrize("tolerance,expected", [(.10, "OK"), (.05, "TRACKING_FAILED")])
def test_real_rollout_uses_acceptance_tolerance_and_preserves_failed_path(cfg, tolerance, expected):
    from autopark.domain.types import Bounds, Pose
    raw = [(Pose(.5 + i * .02, 1, 0), 1, 0) for i in range(16)]
    trajectory = build_trajectory(raw, raw[-1][0], cfg, .15, .08)
    def candidate(*args, **kwargs):
        return PlanResult("OK", "reference offset path", trajectory)
    params = portfolio.PortfolioParams(
        accept_xy=tolerance, tracker_params=TrackerParams(k_lateral=0, k_heading=0),
        ladder=[portfolio.Rung("reference", candidate, portfolio.ref.RefParams(), 1)])
    result = portfolio.plan(Pose(.5, 1.08, 0), raw[-1][0], cfg, [], Bounds(0, 0, 3, 2), params=params)
    assert result.status == expected
    assert result.trajectory is trajectory
