import math

from autopark.domain.types import Pose
from autopark.planning.maneuver_planner import plan_maneuver
from autopark.planning.trajectory import build_trajectory
from autopark.simulation.rollout import rollout
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from tests.conftest import PROJECT_ROOT


def load_default():
    scenario = load_scenario(PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json")
    cfg = load_vehicle_config(scenario.vehicle_config_path)
    return scenario, cfg


def test_closed_loop_parks_in_default_scene():
    scenario, cfg = load_default()
    result = plan_maneuver(scenario, cfg)
    assert result.ok, result.message
    run = rollout(scenario, cfg, result.trajectory)
    report = run.report
    assert report is not None
    assert not report.collided, report.describe()
    assert report.completed, report.describe()
    assert report.position_error < 0.03, report.describe()
    assert abs(report.heading_error) <= scenario.goal.tolerance_yaw, report.describe()
    assert report.sim_time < 90.0


def test_tracker_converges_from_lateral_offset(cfg, scenario):
    # Quỹ đạo thẳng 0,4 m; xe xuất phát lệch ngang 3 cm và lệch hướng 5°.
    raw = [(Pose(0.5 + 0.02 * k, 1.0, 0.0), 1, 0.0) for k in range(21)]
    traj = build_trajectory(raw, Pose(0.9, 1.0, 0.0), cfg, 0.15, 0.08)
    scenario.obstacles = []
    scenario.start = Pose(0.5, 1.03, math.radians(5))
    scenario.goal = type(scenario.goal)(traj.goal)
    run = rollout(scenario, cfg, traj)
    report = run.report
    assert report.completed and not report.collided, report.describe()
    assert report.position_error < 0.02
    assert abs(report.heading_error) < abs(scenario.start.yaw)
    assert abs(report.heading_error) <= scenario.goal.tolerance_yaw


def test_tracker_reverses_along_straight_line(cfg, scenario):
    raw = [(Pose(1.0 - 0.02 * k, 1.0, 0.0), -1, 0.0) for k in range(26)]
    traj = build_trajectory(raw, Pose(0.5, 1.0, 0.0), cfg, 0.15, 0.08)
    scenario.obstacles = []
    scenario.start = Pose(1.0, 1.03, 0.0)
    run = rollout(scenario, cfg, traj)
    report = run.report
    assert report.completed and not report.collided, report.describe()
    assert report.position_error < 0.02
    assert abs(report.heading_error) < math.radians(2.0)
    assert min(s.speed for s in run.states) < 0
