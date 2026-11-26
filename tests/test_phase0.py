from dataclasses import asdict, replace
import math

import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.domain.sensors import Costmap, SourceStamp
from autopark.domain.types import Obstacle, ParkingGoal, Pose, VehicleState
from autopark.geometry.footprint import check_motion
from autopark.simulation.feedback import FeedbackConfig, SimFeedback
from autopark.storage.run_store import export_run, replay_run


def straight_session(scenario, cfg, reverse=False, feedback=None):
    scenario.obstacles = []
    scenario.start = Pose(1.0 if reverse else 0.5, 1.0, 0)
    scenario.goal = ParkingGoal(Pose(0.5 if reverse else 1.0, 1.0, 0))
    session = Session(scenario, cfg, feedback_config=feedback)
    assert session.plan_sync().ok
    return session


def finish(session):
    for _ in range(1500):
        session.advance(0.1)
        if not session.simulating:
            return
    pytest.fail("Phiên không kết thúc")


@pytest.mark.parametrize("reverse", [False, True])
def test_new_obstacle_brakes_invalidates_and_replans_from_stopped_pose(scenario, cfg, reverse):
    session = straight_session(scenario, cfg, reverse)
    session.start_run()
    session.advance(1)
    before = session.world.state
    assert abs(before.speed) > 0.05
    ahead = -0.5 if reverse else 0.6
    x, y = before.pose.to_world(ahead, 0)
    session.inject_obstacle(Obstacle("new", x, y, 0.10, 0.15))
    assert session.state == SessionState.STOPPING
    assert not session.trajectory.valid
    assert session.world.state == before  # Không dịch chuyển/teleport để né vật.
    with pytest.raises(SessionError):
        session.plan_sync()
    with pytest.raises(SessionError):
        session.reset()
    finish(session)
    assert session.state == SessionState.STOPPED
    assert not session.world.collided
    assert session.world.state.speed == 0
    assert [e.code for e in session.safety_events] == ["MAP_CHANGED", "WAIT_REPLAN"]
    stopped_pose = session.world.state.pose
    session.reset()
    assert session.scenario.start == stopped_pose
    assert session.trajectory is None
    with pytest.raises(SessionError):
        session.start_run()
    session.remove_obstacle("new")  # người lái đã xác nhận vật cản được dọn
    result = session.plan_sync()
    assert result.ok, result.message
    session.start_run()
    assert session.world.state.pose == stopped_pose
    finish(session)
    assert session.state == SessionState.COMPLETED


def test_lost_feedback_stops_within_timeout_and_braking(scenario, cfg):
    session = straight_session(scenario, cfg)
    session.start_run()
    session.advance(1)
    t = session.world.time
    session.inject_data_loss()
    finish(session)
    assert session.state == SessionState.STOPPED
    assert session.safety_events[0].code == "STALE_FEEDBACK"
    assert session.safety_events[0].stamp.t - t <= session.feedback_config.stale_after_s + 0.025
    assert session.world.time - t < 0.5
    session.reset()
    assert session.trajectory is None


def test_delay_noise_and_loss_are_seeded_and_timestamp_is_acquisition_time():
    cfg = FeedbackConfig(delay_s=0.04, position_std_m=0.002, drop_probability=0.1)
    a, b = SimFeedback(cfg, 13), SimFeedback(cfg, 13)
    states = [VehicleState(Pose(1, 1, 0), 0.1, 0, i * 0.02) for i in range(100)]
    samples = [a.sample(s) for s in states]
    assert samples == [b.sample(s) for s in states]
    assert samples[0] is None
    assert samples[-1].t <= states[-1].t - 0.039
    assert samples[-1].pose != states[-1].pose


def test_no_feedback_at_start_never_moves(scenario, cfg):
    session = straight_session(scenario, cfg, feedback=FeedbackConfig(drop_probability=1))
    session.start_run()
    finish(session)
    assert session.state == SessionState.STOPPED
    assert session.world.distance == 0


@pytest.mark.parametrize("event", ["obstacle", "data_loss", "stop", "complete"])
def test_run_bundle_replays_exactly(tmp_path, scenario, cfg, event, monkeypatch):
    import autopark.storage.run_store as store
    monkeypatch.setattr(store, "environment", lambda: {"test": True})
    session = straight_session(scenario, cfg, feedback=FeedbackConfig(
        delay_s=0.04, position_std_m=0.001, yaw_std_rad=0.001, drop_probability=0.02))
    session.start_run()
    session.advance(1)
    if event == "obstacle":
        session.inject_obstacle(Obstacle("new", 1.4, 1, 0.1, 0.2))
    elif event == "data_loss":
        session.inject_data_loss()
    elif event == "stop":
        session.request_stop()
    finish(session)
    directory = export_run(session, tmp_path / "run")
    replay = replay_run(directory)
    assert asdict(replay.world.state) == asdict(session.world.state)
    assert replay.log.rows == session.log.rows
    assert replay.safety_events == session.safety_events


def test_preview_isolated_from_runtime_and_faults(scenario, cfg):
    session = straight_session(scenario, cfg, feedback=FeedbackConfig(drop_probability=1))
    preview = session.begin_preview()
    assert preview.report.completed
    assert session.world is None and session.feedback is None
    assert not session.run_events and len(session.log) == 0


def test_unknown_region_is_blocked_and_roundtrips(scenario, cfg):
    scenario.obstacles = [Obstacle("unknown", 0.8, 1.0, 0.15, 0.15, kind="unknown")]
    session = Session(type(scenario).from_dict(scenario.to_dict()), cfg)
    session.set_goal_pose(Pose(0.8, 1.0, 0))
    assert not session.goal_check().ok
    assert session.plan_sync().status == "GOAL_INVALID"
    stamp = SourceStamp("map", 1.0)
    grid = Costmap(stamp, 0.1, Pose(0, 0, 0), ((-1, 0, 1),))
    assert grid.blocked(0, 0) and not grid.blocked(0, 1) and grid.blocked(0, 2)
    assert grid.blocked(-1, 1)
    assert replace(grid, stamp=replace(stamp, valid=False)).blocked(0, 1)
    assert not stamp.fresh(0.5, 0.2) and not stamp.fresh(1.3, 0.2)


def test_rotating_corner_sweep_detected(cfg, bounds):
    # Mũi ngoài ở góc trung gian vượt bao lồi hai footprint đầu/cuối.
    radius = math.hypot(cfg.wheelbase + cfg.front_overhang, cfg.width / 2)
    obstacle = Obstacle("corner", 1 + radius - 0.001, 1, 0.001, 0.001)
    assert not check_motion(cfg, Pose(1, 1, -math.pi / 4), Pose(1, 1, math.pi / 4),
                            [obstacle], bounds).ok


def test_avm_mapping_keeps_ego_and_unrecognized_colors_unknown():
    import numpy as np
    from autopark.evaluation.dataset_audit import avm_to_project
    rgb = np.array([[(0, 0, 255), (255, 255, 255), (255, 0, 0), (0, 255, 0),
                     (0, 0, 0), (1, 2, 3)]], dtype=np.uint8)
    assert avm_to_project(rgb).tolist() == [[0, 0, 1, 1, 255, 255]]
