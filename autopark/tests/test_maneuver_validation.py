"""Reject corrupt control data before I/O and preserve the whole stopping envelope."""
from dataclasses import replace
import math

import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.domain.types import Bounds, ManeuverLimits, ParkingGoal, Pose, Scenario, VehicleState
from autopark.geometry.footprint import body_corners, check_motion
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.maneuver import maneuver_bounds, runtime_problem
from autopark.planning.trajectory import build_trajectory
from autopark.simulation.vehicle import SimVehicle
from autopark.simulation.world import SimWorld


def local_scenario():
    return Scenario("validation", Bounds(-3, -3, 3, 3), Pose(0, 0, 0), ParkingGoal(Pose(.1, 0, 0)))


@pytest.mark.parametrize("corruption", [
    "empty_segments", "missing_start", "past_end", "split_same_direction",
    "bad_direction", "mixed_direction", "wrong_segment", "nonfinite_steer",
    "excess_steer", "negative_speed", "nonfinite_speed", "decreasing_s", "false_s", "nonfinite_goal",
])
def test_corrupt_trajectory_is_refused_before_vehicle_io(cfg, corruption):
    scenario = local_scenario()
    raw = [(Pose(i * .025, 0, 0), 1, 0) for i in range(5)]
    trajectory = build_trajectory(raw, scenario.goal.pose, cfg, .1, .05)
    if corruption == "empty_segments":
        trajectory.segments = []
    elif corruption == "missing_start":
        trajectory.segments = [(1, 4)]
    elif corruption == "past_end":
        trajectory.segments = [(0, 5)]
    elif corruption == "split_same_direction":
        trajectory.segments = [(0, 2), (3, 4)]
    elif corruption == "nonfinite_goal":
        trajectory.goal = replace(trajectory.goal, x=math.nan)
    else:
        fields = {
            "bad_direction": {"direction": 0},
            "mixed_direction": {"direction": -1},
            "wrong_segment": {"segment": 4},
            "nonfinite_steer": {"steer": math.nan},
            "excess_steer": {"steer": cfg.max_steer + .1},
            "negative_speed": {"v": -.1},
            "nonfinite_speed": {"v": math.inf},
            "decreasing_s": {"s": -.01},
            "false_s": {"s": .08},
        }[corruption]
        trajectory.points[1] = replace(trajectory.points[1], **fields)
    session = Session(scenario, cfg)
    session._apply_plan(PlanResult("OK", "fixture", trajectory), session.plan_version)

    class Link:
        started = False

        def record_refused_start(self, code, message):
            self.refusal = code

        def begin_run(self, scenario, cfg, dt):
            self.started = True
            return SimWorld(scenario, cfg, dt)

        def close(self):
            pass

        def describe(self):
            return {}

    link = Link()
    session.set_vehicle_link(link)
    try:
        with pytest.raises(SessionError):
            session.start_run()
        assert not link.started
        assert session.state == SessionState.READY
        assert session.world is None
    finally:
        session.close()


def test_turning_vehicle_stops_with_its_whole_body_inside_maneuver_area(cfg):
    scenario = local_scenario()
    # Valid in-flight state: initially 30 cm between the body and the local edge.
    yaw = math.radians(-40)
    front_x = max(x for x, _ in body_corners(cfg, Pose(0, 0, yaw)))
    vehicle = SimVehicle(cfg, VehicleState(Pose(.75 - front_x - .3, 0, yaw),
                                          cfg.max_speed, cfg.max_steer, 0))
    assert runtime_problem(scenario, cfg, vehicle.state, 0, .005) is None
    stopping = False
    distance = 0.0
    for _ in range(1000):
        stopping = stopping or runtime_problem(scenario, cfg, vehicle.state, distance, .005) is not None
        previous = vehicle.state.pose
        vehicle.step(.005, 0 if stopping else cfg.max_speed, cfg.max_steer)
        distance += previous.distance_to(vehicle.state.pose)
        assert check_motion(cfg, previous, vehicle.state.pose, [], maneuver_bounds(scenario)).ok
        if stopping and vehicle.state.speed == 0:
            break
    assert stopping and vehicle.state.speed == 0


def test_acceleration_before_next_guard_cannot_exceed_total_distance(cfg):
    cfg = replace(cfg, max_accel=2, max_decel=.1)
    scenario = local_scenario()
    scenario.maneuver = ManeuverLimits(max_path_length_m=.02)
    vehicle = SimVehicle(cfg, VehicleState(scenario.start, 0, 0, 0))
    distance = 0.0
    stopping = False
    for _ in range(1000):
        stopping = stopping or runtime_problem(scenario, cfg, vehicle.state, distance, .005) is not None
        previous = vehicle.state.pose
        vehicle.step(.005, 0 if stopping else cfg.max_speed, 0)
        distance += previous.distance_to(vehicle.state.pose)
        if stopping and vehicle.state.speed == 0:
            break
    assert stopping and vehicle.state.speed == 0
    assert 0 < distance <= scenario.maneuver.max_path_length_m


@pytest.mark.parametrize("trigger", ["runtime_limit", "user_stop"])
def test_first_vehicle_stop_does_not_wait_for_next_control_tick(cfg, tmp_path, monkeypatch, trigger):
    from autopark.application.vehicle_link import DriveMode, VehicleLink
    from autopark.storage import run_store
    from tests.test_session_vehicle import SIM_CFG

    scenario = local_scenario()
    trajectory = build_trajectory([(Pose(i * .025, 0, 0), 1, 0) for i in range(5)],
                                  scenario.goal.pose, cfg, .1, .05)
    session = Session(scenario, cfg)
    session._apply_plan(PlanResult("OK", "fixture", trajectory), session.plan_version)
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG)
    session.set_vehicle_link(link)
    try:
        session.start_run()
        session.advance(.2)
        while session.world.step_count % session.CONTROL_EVERY != 1:
            session.advance(session.PHYSICS_DT)
        assert session.world.state.speed > 0
        assert not any(row["kind"] == "STOP" for row in link.command_rows)
        t = session.world.time
        if trigger == "runtime_limit":
            session.world.distance = scenario.maneuver.max_path_length_m
            session.advance(session.PHYSICS_DT)
        else:
            session.request_stop()
        first_stop = next(row for row in link.command_rows if row["kind"] == "STOP")
        assert first_stop["sent"] == 1
        assert first_stop["t_session"] == pytest.approx(t, abs=1e-4)
        assert session.state == SessionState.STOPPING
        for _ in range(400):
            session.advance(.02)
            if not session.simulating:
                break
        assert session.state == SessionState.STOPPED
        if trigger == "user_stop":
            monkeypatch.setattr(run_store, "environment", lambda: {})
            directory = run_store.export_run(session, tmp_path / "off_tick_stop")
            restored, report = run_store.replay_vehicle_run(directory)
            try:
                assert report.ok, report.to_dict()
            finally:
                restored.close()
    finally:
        session.close()
