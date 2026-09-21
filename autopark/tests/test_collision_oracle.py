import math
import random
from dataclasses import replace

import pytest

from autopark.domain.types import Bounds, Obstacle, Pose
from autopark.evaluation.collision_oracle import arc_pose, arc_ok, pose_ok, overlaps, rectangle
from autopark.geometry.footprint import check_motion, check_pose
from autopark.geometry.fast_collision import FastCollisionChecker


def test_oracle_contact_rotation_and_containment():
    square = rectangle(0, 0, 0, -1, 1, -1, 1)
    assert overlaps(square, rectangle(2, 0, 0, -1, 1, -1, 1))
    assert not overlaps(square, rectangle(2.001, 0, 0, -1, 1, -1, 1))
    assert overlaps(square, rectangle(0, 0, math.pi / 4, -.1, .1, -.1, .1))


@pytest.mark.parametrize("seed", [20260920, 42, 917, 8008])
def test_both_pose_checkers_match_independent_oracle(cfg, seed):
    rng = random.Random(seed)
    bounds = Bounds(-2, -2, 2, 2)
    for index in range(100):
        scale = rng.uniform(.5, 2)
        vehicle = replace(cfg, wheelbase=cfg.wheelbase * scale, width=cfg.width * scale,
                          rear_overhang=cfg.rear_overhang * scale, front_overhang=cfg.front_overhang * scale)
        pose = Pose(rng.uniform(-2.2, 2.2), rng.uniform(-2.2, 2.2), rng.uniform(-math.pi, math.pi))
        obstacles = [Obstacle(str(i), rng.uniform(-2, 2), rng.uniform(-2, 2),
                              rng.uniform(.001, .8), rng.uniform(.001, .8), rng.uniform(-math.pi, math.pi))
                     for i in range(4)]
        margin = rng.choice([0, .01, .05])
        expected = pose_ok(vehicle, pose, obstacles, bounds, margin)
        assert check_pose(vehicle, pose, obstacles, bounds, margin).ok == expected, (seed, index)
        assert FastCollisionChecker(vehicle, obstacles, bounds, margin).pose_obj_ok(pose) == expected, (seed, index)


@pytest.mark.parametrize("seed", [114, 210, 311, 812])
def test_swept_region_does_not_miss_independently_sampled_arc_collision(cfg, seed):
    rng = random.Random(seed)
    bounds = Bounds(-3, -3, 3, 3)
    for index in range(50):
        start = Pose(rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-math.pi, math.pi))
        distance = rng.uniform(-.7, .7)
        steer = rng.uniform(-cfg.max_steer, cfg.max_steer)
        middle = arc_pose(start, distance * rng.random(), steer, cfg.wheelbase)
        obstacle = Obstacle("probe", middle.x + rng.uniform(-.2, .2), middle.y + rng.uniform(-.2, .2),
                            rng.uniform(.001, .1), rng.uniform(.001, .1), rng.uniform(-math.pi, math.pi))
        end = arc_pose(start, distance, steer, cfg.wheelbase)
        reference_clear = arc_ok(cfg, start, distance, steer, [obstacle], bounds)
        if not reference_clear:
            assert not check_motion(cfg, start, end, [obstacle], bounds).ok, (seed, index)
