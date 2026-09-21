"""Cancellation and deadlines must reach each active planner and verification."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from autopark.domain.computation import (
    ComputationCancelled, ComputationControl, ComputationTimedOut,
    checkpoint, computation_scope, current_control,
)
from autopark.evaluation.hard_cases import build_cases
from autopark.planning import cand_lattice_macro, cand_reference, cand_rrt_rs, hybrid_astar, portfolio
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.trajectory import build_trajectory
from autopark.simulation.rollout import rollout


PLANNERS = [cand_lattice_macro, cand_reference, cand_rrt_rs, hybrid_astar]


@pytest.mark.parametrize("planner", PLANNERS, ids=lambda p: p.__name__.split(".")[-1])
def test_running_planner_observes_cancellation(monkeypatch, planner, cfg):
    scenario = build_cases(cfg)["pocket_exit_park"].scenario
    reached, release = threading.Event(), threading.Event()
    checks = 0

    def gated_checkpoint():
        nonlocal checks
        checks += 1
        if checks == 5:
            reached.set()
            assert release.wait(3)
        checkpoint()

    monkeypatch.setattr(planner, "checkpoint", gated_checkpoint)
    control = ComputationControl().with_timeout(4)
    with ThreadPoolExecutor(max_workers=1) as worker:
        future = worker.submit(planner.plan, scenario.start, scenario.goal.pose, cfg,
                               scenario.obstacles, scenario.bounds, control=control)
        try:
            assert reached.wait(2), "Planner did not check cancellation while working"
            control.cancel()
        finally:
            release.set()
        result = future.result(timeout=1)
    assert result.status == "CANCELLED"
    assert result.trajectory is None
    assert current_control() is None


@pytest.mark.parametrize("planner", PLANNERS + [portfolio], ids=lambda p: p.__name__.split(".")[-1])
def test_expired_deadline_never_returns_a_path(planner, cfg, scenario):
    control = ComputationControl(deadline=time.perf_counter() - 1)
    result = planner.plan(scenario.start, scenario.goal.pose, cfg, scenario.obstacles,
                          scenario.bounds, control=control)
    assert result.status == "TIMEOUT"
    assert result.trajectory is None


def test_nested_computation_cannot_extend_parent_budget():
    control = ComputationControl().with_timeout(5)
    child = control.with_timeout(50)
    assert child.deadline == control.deadline
    with computation_scope(control):
        control.cancel()
        with pytest.raises(ComputationCancelled):
            with computation_scope(child):
                pass
        assert current_control() is control
    assert current_control() is None


def test_rollout_stops_mid_simulation_without_returning_partial_success(monkeypatch, cfg, scenario):
    trajectory = build_trajectory([(scenario.start, 1, 0.0), (scenario.goal.pose, 1, 0.0)],
                                  scenario.goal.pose, cfg, 0.15, 0.08)
    control = ComputationControl()
    from autopark.simulation import rollout as module
    original = module.SimWorld.step

    def step(world, *args):
        result = original(world, *args)
        if world.step_count == 8:
            control.cancel()
        return result

    monkeypatch.setattr(module.SimWorld, "step", step)
    with pytest.raises(ComputationCancelled):
        rollout(scenario, cfg, trajectory, control=control)


def test_portfolio_never_accepts_a_path_after_verification_times_out(monkeypatch, cfg, scenario):
    trajectory = build_trajectory([(scenario.start, 1, 0.0)], scenario.goal.pose, cfg, 0.15, 0.08)

    def candidate(*args, **kwargs):
        return PlanResult("OK", "unverified", trajectory)

    def verify(*args, **kwargs):
        raise ComputationTimedOut()

    monkeypatch.setattr(portfolio, "rollout", verify)
    params = portfolio.PortfolioParams(ladder=[
        portfolio.Rung("test", candidate, portfolio.ref.RefParams(), 1.0)])
    result = portfolio.plan(scenario.start, scenario.goal.pose, cfg, scenario.obstacles,
                            scenario.bounds, params=params)
    assert result.status == "TIMEOUT"
    assert result.trajectory is None
