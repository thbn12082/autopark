import math

import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.domain.types import ParkingMode, ParkingSlot, Pose
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from tests.conftest import PROJECT_ROOT


def make_session() -> Session:
    scenario = load_scenario(PROJECT_ROOT / "scenarios" / "bai_do_xe.json")
    cfg = load_vehicle_config(scenario.vehicle_config_path)
    return Session(scenario, cfg)


def drive_until_done(session: Session, max_calls: int = 600) -> None:
    for _ in range(max_calls):
        session.advance(0.5)
        if not session.simulating:
            return
    raise AssertionError(f"Mô phỏng không kết thúc, trạng thái {session.state}")


def test_goal_is_derived_from_slot_and_mode():
    s = make_session()
    assert s.scenario.goal.pose.yaw == pytest.approx(math.pi / 2)
    s.set_mode(ParkingMode.HEAD_IN)
    assert s.scenario.goal.pose.yaw == pytest.approx(-math.pi / 2)
    s.set_slot(ParkingSlot(2.2, 0.35, -math.pi / 2, 0.5, 0.34))
    assert s.state == SessionState.EDITING


def test_plan_sync_then_run_completes():
    s = make_session()
    result = s.plan_sync()
    assert result.ok, result.message
    assert s.state == SessionState.READY
    assert s.trajectory is not None
    s.start_run()
    assert s.state == SessionState.RUNNING
    drive_until_done(s)
    assert s.state == SessionState.COMPLETED, s.report.describe() if s.report else s.state
    assert s.report is not None and s.report.completed
    assert s.report.position_error < 0.03
    assert abs(s.report.heading_error) < math.radians(3)
    assert s.footprint_inside_slot(s.report.final_state.pose)
    assert len(s.log) > 0
    s.reset()
    assert s.state == SessionState.READY


def test_stop_during_run_ends_in_stopped():
    s = make_session()
    assert s.plan_sync().ok
    s.start_run()
    s.advance(3.0)
    assert s.state == SessionState.RUNNING
    s.request_stop()
    assert s.state == SessionState.STOPPING
    drive_until_done(s)
    assert s.state == SessionState.STOPPED
    assert s.report is not None and not s.report.completed
    assert abs(s.world.state.speed) < 1e-3


def test_editing_after_plan_invalidates_trajectory():
    s = make_session()
    assert s.plan_sync().ok
    s.set_start(Pose(0.7, 1.45, 0.0))
    assert s.state == SessionState.EDITING
    assert s.trajectory is None
    with pytest.raises(SessionError):
        s.start_run()


def test_async_plan_and_poll():
    s = make_session()
    s.plan_async()
    assert s.state == SessionState.PLANNING
    result = None
    s._plan_future.result(timeout=30)
    for _ in range(600):
        result = s.poll_plan()
        if s.state != SessionState.PLANNING:
            break
    assert result is not None and result.ok
    assert s.state == SessionState.READY
    s.close()


def test_stale_async_result_is_discarded():
    s = make_session()
    s.plan_async()
    future = s._plan_future
    s.cancel_plan()               # người dùng sửa sa bàn trong lúc tính
    assert s.state == SessionState.EDITING
    if not future.cancelled():
        future.result(timeout=3)
    assert s.poll_plan() is None
    assert s.trajectory is None
    assert s.state == SessionState.EDITING
    s.close()


def test_preview_then_ready():
    s = make_session()
    assert s.plan_sync().ok
    pv = s.begin_preview()
    assert s.state == SessionState.PREVIEW
    assert pv.report is not None and pv.report.completed
    assert len(pv.states) > 10
    s.end_preview()
    assert s.state == SessionState.READY


def test_goal_invalid_reports_without_planning():
    s = make_session()
    s.set_slot(ParkingSlot(1.95, 0.35, -math.pi / 2, 0.5, 0.34))  # trùng xe_2
    assert not s.goal_check().ok
    result = s.plan_sync()
    assert result.status == "GOAL_INVALID"
    assert s.state == SessionState.EDITING


def test_finishing_path_outside_goal_tolerance_is_a_fault(scenario, cfg):
    from autopark.control.tracker import TrackerParams
    from autopark.domain.types import ParkingGoal
    from autopark.planning.hybrid_astar import PlanResult
    from autopark.planning.trajectory import build_trajectory

    scenario.obstacles = []
    scenario.start = Pose(0.5, 1.08, 0.0)
    scenario.goal = ParkingGoal(Pose(0.6, 1.0, 0.0))
    s = Session(scenario, cfg, tracker_params=TrackerParams(k_lateral=0.0, k_heading=0.0))
    raw = [(Pose(0.5 + k * 0.02, 1.0, 0.0), 1, 0.0) for k in range(6)]
    traj = build_trajectory(raw, scenario.goal.pose, cfg, 0.15, 0.08)
    s._apply_plan(PlanResult("OK", "test", traj), s.plan_version)
    s.start_run()
    drive_until_done(s)
    assert s.report.position_error > scenario.goal.tolerance_xy
    assert s.state == SessionState.FAULT
    assert not s.report.completed
    assert "dung sai" in s.report.describe()


@pytest.mark.parametrize("length,width", [(0.10, 0.30), (0.50, 0.10)])
def test_slot_smaller_than_vehicle_is_invalid(scenario, cfg, length, width):
    scenario.obstacles = []
    s = Session(scenario, cfg)
    s.set_slot(ParkingSlot(2.0, 1.0, 0.0, length, width))
    assert not s.goal_check().ok
    assert "nhỏ hơn thân xe" in s.goal_check().describe()
    assert s.plan_sync().status == "GOAL_INVALID"
    assert s.state == SessionState.EDITING
