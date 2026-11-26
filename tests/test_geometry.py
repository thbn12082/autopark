import math

import pytest
from pytest import approx

from autopark.domain.types import Obstacle, Pose
from autopark.geometry.footprint import body_corners, check_motion, check_pose


def test_body_corners_at_origin(cfg):
    rl, rr, fr, fl = body_corners(cfg, Pose(0.0, 0.0, 0.0))
    assert rl == approx((-0.06, 0.07))
    assert rr == approx((-0.06, -0.07))
    assert fr == approx((0.25, -0.07))
    assert fl == approx((0.25, 0.07))


def test_body_corners_rotated_90deg(cfg):
    rl, rr, fr, fl = body_corners(cfg, Pose(1.0, 1.0, math.pi / 2))
    # Đầu xe hướng +y: góc trước-trái nằm bên -x, phía trên
    assert fl == approx((0.93, 1.25))
    assert rr == approx((1.07, 0.94))


def test_pose_collides_with_box(cfg, bounds):
    obstacles = [Obstacle("b", 0.5, 1.0, 0.2, 0.2)]  # x 0,40..0,60
    result = check_pose(cfg, Pose(0.3, 1.0, 0.0), obstacles, bounds)  # mũi xe ở 0,55
    assert result.collides
    assert result.obstacle_ids == ["b"]
    assert result.min_clearance == 0.0
    assert not result.ok


def test_pose_clearance_takes_nearest_of_obstacle_and_wall(cfg, bounds):
    obstacles = [Obstacle("b", 0.5, 1.0, 0.2, 0.2)]
    result = check_pose(cfg, Pose(0.1, 1.0, 0.0), obstacles, bounds)  # mũi 0,35 (hở 5 cm), đuôi 0,04 (hở 4 cm)
    assert result.ok
    assert result.min_clearance == approx(0.04)


def test_out_of_bounds(cfg, bounds):
    result = check_pose(cfg, Pose(0.02, 1.0, 0.0), [], bounds)  # đuôi ở -0,04
    assert result.out_of_bounds
    assert not result.ok
    assert result.min_clearance == 0.0


def test_margin_makes_tight_pose_fail(cfg, bounds):
    obstacles = [Obstacle("b", 0.5, 1.0, 0.2, 0.2)]
    pose = Pose(0.13, 1.0, 0.0)  # mũi 0,38: hở 2 cm
    assert check_pose(cfg, pose, obstacles, bounds).ok
    assert not check_pose(cfg, pose, obstacles, bounds, margin=0.03).ok


def test_rotated_obstacle_corners():
    obs = Obstacle("r", 0.0, 0.0, 0.4, 0.2, math.pi / 2)
    xs = [c[0] for c in obs.corners()]
    ys = [c[1] for c in obs.corners()]
    assert max(xs) == approx(0.1) and min(xs) == approx(-0.1)
    assert max(ys) == approx(0.2) and min(ys) == approx(-0.2)


def test_swept_motion_catches_jump_over_thin_obstacle(cfg, bounds):
    obstacles = [Obstacle("thin", 0.5, 1.0, 0.01, 0.4)]
    a = Pose(0.20, 1.0, 0.0)  # mũi ở 0,45
    b = Pose(0.62, 1.0, 0.0)  # đuôi ở 0,56
    assert check_pose(cfg, a, obstacles, bounds).ok
    assert check_pose(cfg, b, obstacles, bounds).ok
    assert check_motion(cfg, a, b, obstacles, bounds).collides


def test_describe_lists_reasons(cfg, bounds):
    obstacles = [Obstacle("b", 0.5, 1.0, 0.2, 0.2)]
    result = check_pose(cfg, Pose(0.3, 1.0, 0.0), obstacles, bounds)
    assert "b" in result.describe()
    assert "ngoài" not in result.describe()


def test_collision_updates_after_editing_cached_scene(cfg, bounds):
    from dataclasses import replace

    pose = Pose(0.5, 1.0, 0.0)
    obstacle = Obstacle("same_id", 1.5, 1.0, 0.2, 0.2)
    assert check_pose(cfg, pose, [obstacle], bounds).ok
    moved = replace(obstacle, cx=0.6)
    assert check_pose(cfg, pose, [moved], bounds).collides
    assert check_pose(cfg, pose, [obstacle], bounds).ok
    smaller = replace(bounds, xmax=0.65)
    assert check_pose(cfg, pose, [], smaller).out_of_bounds
    assert check_pose(cfg, pose, [], bounds).ok
