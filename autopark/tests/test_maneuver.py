"""Thao tác gần: giới hạn hình học, tổng quãng đường và quyền chọn lượt tiếp."""
from dataclasses import replace
import os

import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.domain.types import Bounds, ManeuverLimits, ParkingGoal, Pose, Scenario
from autopark.planning.maneuver import maneuver_bounds, trajectory_problem
from autopark.planning.maneuver_planner import plan_maneuver
from autopark.planning.trajectory import build_trajectory
from autopark.storage.scenario_store import load_scenario, load_vehicle_config, save_scenario
from tests.conftest import PROJECT_ROOT


def load_local(name="thao_tac_cua_hep.json"):
    scenario = load_scenario(PROJECT_ROOT / "scenarios" / name)
    return scenario, load_vehicle_config(scenario.vehicle_config_path)


@pytest.mark.parametrize("name", ["thao_tac_cua_hep.json", "thao_tac_lui_vao_khe.json"])
def test_short_maneuver_runs_stops_and_next_starts_at_actual_pose(name):
    scenario, cfg = load_local(name)
    session = Session(scenario, cfg)
    try:
        result = session.plan_sync()
        assert result.ok, result.message
        assert result.trajectory.length <= scenario.maneuver.max_path_length_m
        assert result.trajectory.n_cusps <= scenario.maneuver.max_cusps
        session.start_run()
        for _ in range(400):
            session.advance(0.25)
            if not session.simulating:
                break
        assert session.state == SessionState.COMPLETED, session.stop_reason
        assert not session.report.collided
        assert abs(session.world.state.speed) <= session.tracker_params.stop_speed
        stopped = session.world.state.pose
        assert stopped.distance_to(scenario.goal.pose) <= scenario.goal.tolerance_xy
        assert abs(stopped.heading_error_to(scenario.goal.pose)) <= scenario.goal.tolerance_yaw
        session.prepare_next_maneuver()
        assert session.state == SessionState.EDITING
        assert session.scenario.start == stopped
        assert session.trajectory is None
        with pytest.raises(SessionError, match="Chưa có đường"):
            session.start_run()
    finally:
        session.close()


def test_far_goal_refused_before_search(monkeypatch):
    from autopark.planning import portfolio
    scenario, cfg = load_local()
    scenario.goal = ParkingGoal(Pose(1.3, 1.3, 0))
    monkeypatch.setattr(portfolio, "plan", lambda *a, **kw: pytest.fail("must reject before search"))
    result = plan_maneuver(scenario, cfg)
    assert result.status == "MANEUVER_LIMIT" and result.trajectory is None
    assert "đích gần hơn" in result.message
    assert not Session(scenario, cfg).goal_check().ok


def test_near_goal_cannot_hide_long_detour(cfg):
    scenario = Scenario("local", Bounds(-3, -3, 3, 3), Pose(0, 0, 0), ParkingGoal(Pose(.1, 0, 0)),
                        maneuver=ManeuverLimits(max_path_length_m=.5))
    trajectory = build_trajectory([(Pose(0, 0, 0), 1, 0), (Pose(.4, 0, 0), 1, 0),
                                   (Pose(.4, 0, 0), -1, 0), (Pose(.1, 0, 0), -1, 0)],
                                  scenario.goal.pose, cfg, .1, .05)
    # Hỏng metadata s không được làm đường dài trở thành đường ngắn.
    trajectory.points = [replace(p, s=0) for p in trajectory.points]
    assert "0.50 m" in trajectory_problem(scenario, cfg, trajectory)


def test_whole_body_must_stay_in_local_area(cfg):
    scenario = Scenario("local", Bounds(-3, -3, 3, 3), Pose(0, 0, 0), ParkingGoal(Pose(.1, 0, 0)),
                        maneuver=ManeuverLimits(max_path_length_m=3))
    trajectory = build_trajectory([(Pose(0, 0, 0), 1, 0), (Pose(.6, 0, 0), 1, 0),
                                   (Pose(.1, 0, 0), -1, 0)], scenario.goal.pose, cfg, .1, .05)
    assert maneuver_bounds(scenario).contains_point(.6, 0)
    assert "rời vùng" in trajectory_problem(scenario, cfg, trajectory)


@pytest.mark.parametrize("cli, expected", [(None, 3), (1, 1), (10, 3)])
def test_cli_can_only_tighten_local_cusp_budget(cli, expected):
    from autopark.application.cusp_policy import CuspPolicy
    scenario, cfg = load_local()
    session = Session(scenario, cfg, cusp_policy=CuspPolicy(max_cusps=cli))
    assert session.cusp_limit().policy.max_cusps == expected


def test_many_short_shuffles_are_refused(cfg):
    scenario = Scenario("local", Bounds(-3, -3, 3, 3), Pose(0, 0, 0), ParkingGoal(Pose(.1, 0, 0)),
                        maneuver=ManeuverLimits(max_cusps=1))
    trajectory = build_trajectory([(Pose(0, 0, 0), 1, 0), (Pose(.1, 0, 0), 1, 0),
                                   (Pose(0, 0, 0), -1, 0), (Pose(.1, 0, 0), 1, 0)],
                                  scenario.goal.pose, cfg, .1, .05)
    assert trajectory.length < scenario.maneuver.max_path_length_m
    assert "1 lần đổi chiều" in trajectory_problem(scenario, cfg, trajectory)


def test_search_tries_another_candidate_after_a_long_detour(monkeypatch, cfg):
    from autopark.planning import portfolio
    from autopark.planning.hybrid_astar import PlanResult
    from autopark.domain.types import VehicleState
    from autopark.simulation.rollout import RolloutResult, RunReport

    start, goal = Pose(0, 0, 0), Pose(.1, 0, 0)
    long = build_trajectory([(start, 1, 0), (Pose(.65, 0, 0), 1, 0), (goal, -1, 0)], goal, cfg, .1, .05)
    short = build_trajectory([(start, 1, 0), (goal, 1, 0)], goal, cfg, .1, .05)
    candidates = iter([long, short])
    checked = []
    def candidate(*args, **kwargs):
        return PlanResult("OK", "candidate", next(candidates))
    def verify(scenario, vehicle, trajectory, **kwargs):
        checked.append(trajectory)
        return RolloutResult(report=RunReport(True, False, 1, trajectory.length,
                                             VehicleState(goal, 0, 0, 1), 0, 0))
    monkeypatch.setattr(portfolio, "rollout", verify)
    params = portfolio.PortfolioParams(max_path_length=.5, max_cusps=1,
        ladder=[portfolio.Rung(str(i), candidate, portfolio.ref.RefParams(), 1) for i in range(2)])
    result = portfolio.plan(start, goal, cfg, [], Bounds(-2, -2, 2, 2), params)
    assert result.ok and result.trajectory is short
    assert checked == [short]


def test_start_rechecks_limits_before_vehicle_io():
    scenario, cfg = load_local()
    session = Session(scenario, cfg)
    try:
        assert session.plan_sync().ok
        scenario.maneuver = replace(scenario.maneuver, max_path_length_m=.1)
        class Link:
            def record_refused_start(self, code, message):
                self.code = code
            def begin_run(self, *a):
                pytest.fail("rejected maneuver must not arm a vehicle")
            def close(self):
                pass
        link = Link()
        session.set_vehicle_link(link)
        with pytest.raises(SessionError, match="giới hạn"):
            session.start_run()
        assert link.code == "START_MANEUVER_LIMIT"
        assert session.state == SessionState.READY
    finally:
        session.close()


@pytest.mark.parametrize("kind, code", [("distance", "MANEUVER_DISTANCE"), ("area", "MANEUVER_AREA")])
def test_runtime_stops_at_local_limits(kind, code):
    scenario, cfg = load_local()
    session = Session(scenario, cfg)
    try:
        assert session.plan_sync().ok
        session.start_run()
        if kind == "distance":
            session.world.distance = scenario.maneuver.max_path_length_m
        else:
            session.world.vehicle.state = replace(session.world.state, pose=Pose(1.4, .5, 0))
        session.advance(.005)
        assert session.state in (SessionState.STOPPING, SessionState.STOPPED, SessionState.FAULT)
        assert any(event.code == code for event in session.safety_events)
    finally:
        session.close()


def test_limits_survive_save_reload(tmp_path):
    scenario, cfg = load_local()
    path = tmp_path / "maneuver.json"
    save_scenario(scenario, path)
    restored = load_scenario(path)
    assert restored.maneuver == scenario.maneuver
    assert Scenario.from_dict(scenario.to_dict()).maneuver == scenario.maneuver


@pytest.mark.parametrize("values", [{"max_goal_distance_m": float("nan")}, {"area_half_extent_m": 0},
                                    {"max_path_length_m": True}, {"max_cusps": 1.5}, {"max_cusps": -1},
                                    {"max_path_length_m": "1.4"}, {"unknown": 1}])
def test_invalid_limits_rejected(values):
    with pytest.raises(ValueError):
        ManeuverLimits.from_dict(values)


def test_default_ui_selects_near_pose_and_finishes_without_restarting():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from autopark.ui.app import DEFAULT_SCENARIO, build_window
    app = QApplication.instance() or QApplication([])
    window = build_window(DEFAULT_SCENARIO)
    try:
        assert window.session.scenario.maneuver is not None
        assert window.goal_item.isVisible()
        assert window.primary_action.text() == "Tính thao tác   →"
        assert window.plan(sync=True).ok
        window.preview()
        window.session._preview_future.result(timeout=15)
        window._on_tick()
        assert window.session.state == SessionState.PREVIEW
        assert window.session.preview.report.completed
        window.stop()
        window.run()
        for _ in range(400):
            window.advance_by(.25)
            if not window.session.simulating:
                break
        assert window.session.state == SessionState.COMPLETED
        pose = window.session.world.state.pose
        window.primary_action.click()
        assert window.session.state == SessionState.EDITING
        assert window.session.scenario.start == pose
        assert window.session.trajectory is None
    finally:
        window.close()


def test_old_scenarios_are_refused_by_session_and_planner():
    from autopark.ui.app import main
    path = PROJECT_ROOT / "scenarios" / "bai_do_xe.json"
    old = load_scenario(path)
    cfg = load_vehicle_config(old.vehicle_config_path)
    with pytest.raises(SessionError, match="giới hạn thao tác gần"):
        Session(old, cfg)
    assert plan_maneuver(old, cfg).status == "MANEUVER_LIMIT"
    assert main(["run_app.py", str(path)]) == 2


def test_missing_limits_are_refused_even_after_planning():
    scenario, cfg = load_local()
    session = Session(scenario, cfg)
    try:
        assert session.plan_sync().ok
        scenario.maneuver = None
        with pytest.raises(SessionError, match="giới hạn thao tác gần"):
            session.start_run()
    finally:
        session.close()
