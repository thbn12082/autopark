import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.domain.types import Obstacle, Pose


def test_manual_transitions(scenario, cfg):
    s = Session(scenario, cfg)
    assert s.state == SessionState.EDITING
    s.start_manual()
    assert s.state == SessionState.MANUAL
    assert s.world is not None
    s.stop_manual()
    assert s.state == SessionState.EDITING
    assert s.world is None


def test_editing_blocked_while_manual(scenario, cfg):
    s = Session(scenario, cfg)
    s.start_manual()
    with pytest.raises(SessionError):
        s.set_start(Pose(1.0, 1.0, 0.0))
    with pytest.raises(SessionError):
        s.add_obstacle()


def test_advance_outside_manual_does_nothing(scenario, cfg):
    s = Session(scenario, cfg)
    assert s.advance(1.0) == []


def test_manual_drive_hits_box_and_stops(scenario, cfg):
    s = Session(scenario, cfg)
    s.start_manual()
    s.set_manual_targets(0.2, 0.0)
    for _ in range(10):
        s.advance(1.0)
    assert s.world.collided
    assert s.world.state.speed == 0.0
    assert "hop_1" in s.world.last_collision.obstacle_ids
    assert s.world.state.pose.x < 1.2  # dừng trước tâm hộp, không xuyên qua
    assert len(s.log) > 0
    # Xuất phát trong sa bàn không bị mô phỏng làm thay đổi
    assert s.scenario.start == Pose(0.5, 1.0, 0.0)


def test_start_manual_refuses_invalid_start(scenario, cfg):
    s = Session(scenario, cfg)
    s.set_start(Pose(1.2, 1.0, 0.0))  # đè lên hop_1
    with pytest.raises(SessionError):
        s.start_manual()
    assert s.state == SessionState.EDITING


def test_goal_check_reports_collision(scenario, cfg):
    s = Session(scenario, cfg)
    assert s.goal_check().ok
    s.set_goal_pose(Pose(1.2, 1.0, 0.0))
    check = s.goal_check()
    assert not check.ok
    assert "hop_1" in check.describe()


def test_advance_caps_steps_and_flags_lagging(scenario, cfg):
    s = Session(scenario, cfg)
    s.start_manual()
    s.advance(100.0)
    assert s.lagging
    assert s.world.step_count == Session.MAX_STEPS_PER_ADVANCE
    s.advance(0.01)
    assert not s.lagging


def test_reset_manual_restores_start(scenario, cfg):
    s = Session(scenario, cfg)
    s.start_manual()
    s.set_manual_targets(0.2, 0.0)
    s.advance(1.0)
    assert s.world.state.pose.x > 0.5
    s.reset_manual()
    assert s.world.state.pose == scenario.start
    assert s.world.distance == 0.0
    assert not s.world.collided
    assert s.targets.speed == 0.0


def test_targets_are_clamped(scenario, cfg):
    s = Session(scenario, cfg)
    s.set_manual_targets(10.0, 5.0)
    assert s.targets.speed == cfg.max_speed
    assert s.targets.steer == cfg.max_steer
    s.nudge_speed(-100.0)
    assert s.targets.speed == -cfg.max_speed


def test_obstacle_editing(scenario, cfg):
    s = Session(scenario, cfg)
    new = s.add_obstacle()
    assert new.id == "hop_2"
    s.update_obstacle(Obstacle("hop_2", 0.5, 0.5, 0.1, 0.1, 0.0))
    assert s.scenario.obstacle_by_id("hop_2").cx == 0.5
    s.remove_obstacle("hop_2")
    assert s.scenario.obstacle_by_id("hop_2") is None
    with pytest.raises(SessionError):
        s.remove_obstacle("khong_co")


def test_log_export(tmp_path, scenario, cfg):
    s = Session(scenario, cfg)
    s.start_manual()
    s.set_manual_targets(0.1, 0.0)
    s.advance(0.5)
    path = s.log.to_csv(tmp_path / "logs" / "run.csv")
    text = path.read_text(encoding="utf-8").splitlines()
    assert text[0].startswith("t,x,y,yaw_deg,speed")
    assert len(text) == len(s.log) + 1
