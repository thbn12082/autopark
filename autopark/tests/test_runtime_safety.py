"""Regression cases for unsafe terminal states and runtime boundary inputs."""
from dataclasses import replace
import math

import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.control.tracker import TrackerParams, TrajectoryTracker
from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario, VehicleState
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.trajectory import build_trajectory
from autopark.simulation.feedback import FeedbackConfig
from autopark.simulation.rollout import rollout
from autopark.simulation.vehicle import SimVehicle
from autopark.simulation.world import SimWorld


def ready(cfg, *, feedback=None):
    raw = [(Pose(i * 0.02, 0, 0), 1, 0) for i in range(21)]
    trajectory = build_trajectory(raw, raw[-1][0], cfg, 0.15, 0.08)
    sc = Scenario("runtime", Bounds(-3, -3, 3, 3), raw[0][0], ParkingGoal(raw[-1][0]))
    s = Session(sc, cfg, feedback_config=feedback)
    s._apply_plan(PlanResult("OK", "analytic straight fixture", trajectory), s.plan_version)
    return s


def finish(s):
    for _ in range(2000):
        s.advance(0.02)
        if not s.simulating:
            return
    pytest.fail("Session did not stop")


@pytest.mark.parametrize("start", ["start_run", "start_manual"])
def test_closed_session_rejects_execution(cfg, start):
    s = ready(cfg)
    s.close()
    with pytest.raises(SessionError, match="đóng"):
        getattr(s, start)()


def test_close_freezes_simulation_and_does_not_report_success(cfg):
    s = ready(cfg)
    s.start_run()
    s.advance(0.5)
    before = s.world.state
    s.close()
    assert not s.simulating
    assert s.advance(1) == []
    assert s.world.state == before
    assert s.report is None or not s.report.completed


def test_timeout_brakes_before_entering_terminal_fault(cfg):
    s = ready(cfg)
    s.MAX_RUN_TIME = 0.5
    s.start_run()
    finish(s)
    assert s.state == SessionState.FAULT
    assert s.world.state.speed == 0
    assert not s.report.completed and not s.report.collided
    assert s.world.time > s.MAX_RUN_TIME
    assert any(e.code == "RUN_TIMEOUT" for e in s.safety_events)


def test_requested_stop_finishes_braking_even_after_run_deadline(cfg):
    s = ready(cfg)
    s.MAX_RUN_TIME = 0.55
    s.start_run()
    s.advance(0.5)
    s.request_stop()
    finish(s)
    assert s.state == SessionState.STOPPED
    assert s.world.state.speed == 0
    assert s.world.time > s.MAX_RUN_TIME


def test_stopped_means_zero_not_a_frozen_residual_speed(cfg):
    s = ready(cfg)
    s.start_run()
    s.world.vehicle.state = replace(s.world.state, speed=0.0035)
    s.request_stop()
    finish(s)
    assert s.world.state.speed == 0


def test_world_starting_inside_obstacle_is_latched_even_if_first_step_escapes(cfg):
    s = ready(cfg)
    s.scenario.obstacles = [Obstacle("inside", 0, 0, 0.01, 0.01)]
    world = SimWorld(s.scenario, cfg, dt=2)
    assert world.collided
    result = world.step(cfg.max_speed, 0)
    assert result.stopped_by_collision and result.state.speed == 0
    assert result.state.pose == s.scenario.start


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_advance_rejected_without_corrupting_session(cfg, value):
    s = ready(cfg)
    s.start_run()
    before = s.world.state
    with pytest.raises(ValueError):
        s.advance(value)
    assert s.world.state == before
    assert math.isfinite(s._accumulator)


@pytest.mark.parametrize("field", ["speed", "steer", "dt"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_vehicle_inputs_rejected_atomically(cfg, field, value):
    vehicle = SimVehicle(cfg, VehicleState(Pose(0, 0, 0), 0, 0, 0))
    args = {"dt": 0.005, "target_speed": 0.1, "target_steer": 0.1}
    args[{"speed": "target_speed", "steer": "target_steer", "dt": "dt"}[field]] = value
    before = vehicle.state
    with pytest.raises(ValueError):
        vehicle.step(**args)
    assert vehicle.state == before


@pytest.mark.parametrize("field", ["x", "yaw", "speed", "steer", "future", "invalid"])
def test_malformed_feedback_stops_without_entering_controller(cfg, monkeypatch, field):
    s = ready(cfg)
    s.start_run()
    s.advance(0.5)
    def bad_sample(truth):
        if field in ("x", "yaw"):
            bad = replace(truth, pose=replace(truth.pose, **{field: math.nan}))
        elif field in ("speed", "steer"):
            bad = replace(truth, **{field: math.inf})
        elif field == "future":
            bad = replace(truth, t=truth.t + 1)
        else:
            bad = replace(truth, valid=False)
        s.feedback.latest = bad
        return bad
    monkeypatch.setattr(s.feedback, "sample", bad_sample)
    monkeypatch.setattr(s.tracker, "update", lambda state: pytest.fail("Bad feedback reached tracker"))
    finish(s)
    assert s.state == SessionState.STOPPED
    assert s.world.state.speed == 0


def test_second_obstacle_and_data_loss_are_accepted_during_braking(cfg):
    s = ready(cfg)
    s.start_run()
    s.advance(0.5)
    s.inject_obstacle(Obstacle("first", 0.8, 0, 0.05, 0.1))
    assert s.state == SessionState.STOPPING
    s.inject_data_loss()
    s.inject_obstacle(Obstacle("second", 0.6, 0.2, 0.05, 0.1))
    finish(s)
    assert s.state == SessionState.STOPPED
    assert len(s.world.scenario.obstacles) == 2
    assert [e["kind"] for e in s.run_events] == ["obstacle", "data_loss", "obstacle"]


def test_preview_must_not_claim_completed_outside_goal_tolerance(cfg):
    s = ready(cfg)
    s.scenario.start = Pose(0, 0.08, 0)
    result = rollout(s.scenario, cfg, s.trajectory, TrackerParams(k_lateral=0, k_heading=0))
    assert result.report.position_error > s.scenario.goal.tolerance_xy
    assert not result.report.completed
    assert "dung sai" in result.report.reason


def test_trajectory_and_controller_respect_small_speed_limit(cfg):
    cfg = replace(cfg, max_speed=0.02)
    s = ready(cfg)
    assert all(p.v <= cfg.max_speed for p in s.trajectory.points)
    tracker = TrajectoryTracker(s.trajectory, cfg)
    out = tracker.update(VehicleState(s.scenario.start, 0, 0, 0))
    assert abs(out.target_speed) <= cfg.max_speed


def test_cusp_does_not_switch_gear_while_still_moving(cfg):
    raw = [(Pose(0, 0, 0), 1, 0), (Pose(.2, 0, 0), 1, 0), (Pose(.1, 0, 0), -1, 0)]
    trajectory = build_trajectory(raw, raw[-1][0], cfg, .1, .05)
    tracker = TrajectoryTracker(trajectory, cfg)
    out = tracker.update(VehicleState(Pose(.2, 0, 0), .003, 0, 1))
    assert out.target_speed == 0
    assert tracker.segment == 0
    tracker.update(VehicleState(Pose(.2, 0, 0), 0, 0, 1.02))
    assert tracker.segment == 1


def test_combined_events_replay_exactly_while_braking(cfg, tmp_path, monkeypatch):
    from autopark.storage.run_store import export_run, replay_run
    monkeypatch.setattr("autopark.storage.run_store.environment", lambda: {})
    s = ready(cfg)
    s.start_run()
    s.advance(.5)
    s.inject_obstacle(Obstacle("first", .8, 0, .05, .1))
    s.advance(.02)
    s.inject_data_loss()
    s.inject_obstacle(Obstacle("second", .6, .2, .05, .1))
    finish(s)
    p = export_run(s, tmp_path / "combined")
    restored = replay_run(p)
    assert restored.log.rows == s.log.rows
    assert restored.run_events == s.run_events
    assert restored.safety_events == s.safety_events


@pytest.mark.parametrize("gap_factor", [.5, 1.5])
@pytest.mark.parametrize("reverse", [False, True])
def test_braking_distance_boundary_reports_collision_honestly(cfg, gap_factor, reverse):
    s = ready(cfg)
    s.start_run()
    direction = -1 if reverse else 1
    s.world.vehicle.state = replace(s.world.state, speed=direction * .15)
    leading = -cfg.rear_overhang if reverse else cfg.wheelbase + cfg.front_overhang
    gap = .15**2 / (2 * cfg.max_decel) * gap_factor
    x = leading + direction * (gap + .005)
    s.inject_obstacle(Obstacle("braking_limit", x, 0, .01, .3))
    finish(s)
    assert s.world.state.speed == 0 and not s.report.completed
    if gap_factor < 1:
        assert s.state == SessionState.FAULT and s.report.collided
    else:
        assert s.state == SessionState.STOPPED and not s.report.collided


@pytest.mark.parametrize("factor", [0, -1, math.nan, math.inf])
def test_invalid_time_scale_rejected(cfg, factor):
    s = ready(cfg)
    s.start_run()
    s.realtime_factor = factor
    with pytest.raises(ValueError):
        s.advance(.1)
    assert s.world.step_count == 0


def test_occupied_goal_remains_invalid_after_safety_reset(cfg):
    s = ready(cfg)
    s.start_run()
    s.advance(.5)
    s.inject_obstacle(Obstacle("goal_taken", .5, 0, .1, .1))
    finish(s)
    s.reset()
    assert s.plan_sync().status == "GOAL_INVALID"
    assert s.trajectory is None


def test_preview_reports_path_end_separately_from_success(cfg):
    s = ready(cfg)
    s.scenario.start = Pose(0, .08, 0)
    result = rollout(s.scenario, cfg, s.trajectory, TrackerParams(k_lateral=0, k_heading=0))
    assert result.report.path_finished and not result.report.completed
