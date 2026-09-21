import math

import pytest
from pytest import approx

from autopark.domain.types import Obstacle, ParkingMode, ParkingSlot, Pose, wrap_angle
from autopark.geometry.footprint import check_motion, check_pose
from autopark.planning.hybrid_astar import PlannerParams, plan
from autopark.planning.parking import plan_parking
from autopark.planning.trajectory import build_trajectory
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from tests.conftest import PROJECT_ROOT


def load_default():
    scenario = load_scenario(PROJECT_ROOT / "scenarios" / "bai_do_xe.json")
    cfg = load_vehicle_config(scenario.vehicle_config_path)
    return scenario, cfg


def assert_path_is_collision_free(trajectory, cfg, scenario):
    pts = trajectory.points
    for a, b in zip(pts, pts[1:]):
        col = check_motion(cfg, a.pose, b.pose, scenario.obstacles, scenario.bounds)
        assert col.ok, f"va chạm tại s={b.s:.2f}: {col.describe()}"


def test_slot_goal_pose_reverse_in(cfg):
    slot = ParkingSlot(2.2, 0.35, -math.pi / 2, 0.5, 0.34)
    goal = slot.goal_pose(cfg, ParkingMode.REVERSE_IN)
    assert goal.yaw == approx(math.pi / 2)          # đầu xe hướng ra cửa ô (+y)
    assert goal.x == approx(2.2)
    # thân xe nằm giữa ô: đuôi ở 0,195, mũi ở 0,505
    assert goal.y - cfg.rear_overhang == approx(0.35 - cfg.length / 2)


def test_slot_goal_pose_head_in_and_parallel(cfg):
    slot = ParkingSlot(2.2, 0.35, -math.pi / 2, 0.5, 0.34)
    head = slot.goal_pose(cfg, ParkingMode.HEAD_IN)
    assert head.yaw == approx(-math.pi / 2)
    assert head.y + cfg.rear_overhang == approx(0.35 + cfg.length / 2)
    par = ParkingSlot(1.0, 1.0, 0.0, 0.5, 0.24)
    assert par.goal_pose(cfg, ParkingMode.PARALLEL, reference_yaw=0.1).yaw == approx(0.0)
    assert abs(par.goal_pose(cfg, ParkingMode.PARALLEL, reference_yaw=3.0).yaw) == approx(math.pi)


def test_default_scene_plans_and_reaches_goal():
    scenario, cfg = load_default()
    result = plan_parking(scenario, cfg)
    assert result.ok, result.message
    traj = result.trajectory
    assert traj is not None
    end = traj.end_pose
    goal = scenario.goal.pose
    assert math.hypot(end.x - goal.x, end.y - goal.y) < 0.01
    assert abs(wrap_angle(end.yaw - goal.yaw)) < math.radians(1.0)
    assert traj.n_cusps >= 1                     # phải lùi vào ô
    assert result.elapsed < 15.0
    assert_path_is_collision_free(traj, cfg, scenario)
    # hồ sơ tốc độ: về 0 ở cuối mỗi đoạn và không vượt tốc độ hành trình
    for a, b in traj.segments:
        assert traj.points[b].v == 0.0
        assert traj.points[a].v <= 0.15 + 1e-9
    assert max(p.v for p in traj.points) <= 0.15 + 1e-9


def test_goal_inside_obstacle_is_rejected():
    scenario, cfg = load_default()
    scenario.slot = None
    scenario.goal = type(scenario.goal)(Pose(1.95, 0.35, math.pi / 2))
    result = plan_parking(scenario, cfg)
    assert result.status == "GOAL_INVALID"


def test_walled_off_goal_reports_no_path():
    scenario, cfg = load_default()
    scenario.obstacles.append(Obstacle("tuong", 1.5, 1.0, 0.05, 2.0, 0.0, "wall"))  # tường chia đôi sa bàn
    params = PlannerParams(time_limit=3.0, max_nodes=20000)
    result = plan_parking(scenario, cfg, params)
    assert result.status in ("NO_PATH", "TIMEOUT")


def test_trivial_plan_when_already_at_goal(cfg, bounds):
    goal = Pose(1.0, 1.0, 0.3)
    result = plan(goal, goal, cfg, [], bounds)
    assert result.ok
    assert result.trajectory.length == approx(0.0)


def test_build_trajectory_splits_segments_at_direction_change(cfg):
    raw = [(Pose(0, 0, 0), 1, 0.0), (Pose(0.1, 0, 0), 1, 0.0), (Pose(0.2, 0, 0), 1, 0.0),
           (Pose(0.1, 0, 0), -1, 0.0), (Pose(0.0, 0, 0), -1, 0.0)]
    traj = build_trajectory(raw, Pose(0, 0, 0), cfg, 0.15, 0.08)
    assert len(traj.segments) == 2
    assert traj.n_cusps == 1
    a0, b0 = traj.segments[0]
    a1, b1 = traj.segments[1]
    assert traj.points[b0].pose == traj.points[a1].pose  # điểm đổi chiều nhân đôi
    assert traj.points[b0].v == 0.0
    assert traj.points[a1].direction == -1
    assert traj.length == approx(0.4)
