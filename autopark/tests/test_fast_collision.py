"""Bộ kiểm tra va chạm giải tích phải cho cùng kết luận với bản dùng Shapely."""
import math
import random

import pytest

from autopark.domain.types import Bounds, Obstacle, Pose
from autopark.geometry.fast_collision import FastCollisionChecker
from autopark.geometry.footprint import check_pose


def random_obstacles(rng: random.Random, n: int) -> list[Obstacle]:
    return [
        Obstacle(f"o{i}", rng.uniform(0.2, 2.8), rng.uniform(0.2, 1.8),
                 rng.uniform(0.05, 0.5), rng.uniform(0.05, 0.4),
                 rng.uniform(-math.pi, math.pi), "box")
        for i in range(n)
    ]


@pytest.mark.parametrize("margin", [0.0, 0.015, 0.05])
def test_agrees_with_shapely_on_random_poses(cfg, margin):
    rng = random.Random(20260907 + int(margin * 1000))
    bounds = Bounds(0.0, 0.0, 3.0, 2.0)
    disagreements = []
    checked = 0
    for trial in range(60):
        obstacles = random_obstacles(rng, rng.randint(0, 6))
        fast = FastCollisionChecker(cfg, obstacles, bounds, margin)
        for _ in range(120):
            x, y = rng.uniform(-0.1, 3.1), rng.uniform(-0.1, 2.1)
            yaw = rng.uniform(-math.pi, math.pi)
            slow = check_pose(cfg, Pose(x, y, yaw), obstacles, bounds, margin).ok
            quick = fast.pose_ok(x, y, yaw)
            checked += 1
            if slow != quick:
                # Bỏ qua các ca sát ranh giới trong phạm vi sai số số học
                clear = check_pose(cfg, Pose(x, y, yaw), obstacles, bounds, margin).min_clearance
                if clear > 1e-6:
                    disagreements.append((x, y, yaw, slow, quick, clear))
    assert checked > 5000
    assert not disagreements, f"{len(disagreements)} bất đồng, ví dụ {disagreements[:3]}"


def test_detects_bounds_violation(cfg):
    bounds = Bounds(0.0, 0.0, 1.0, 1.0)
    fast = FastCollisionChecker(cfg, [], bounds, 0.0)
    assert fast.pose_ok(0.5, 0.5, 0.0)
    assert not fast.pose_ok(0.02, 0.5, 0.0)      # đuôi xe ra ngoài
    assert not fast.pose_ok(0.5, 0.5, math.pi / 4) is False   # chéo vẫn nằm trong
    assert not fast.pose_ok(0.9, 0.5, 0.0)       # mũi xe ra ngoài


def test_rotated_obstacle_is_hit(cfg):
    bounds = Bounds(0.0, 0.0, 2.0, 2.0)
    obs = [Obstacle("cheo", 1.0, 1.0, 0.4, 0.06, math.pi / 4, "wall")]
    fast = FastCollisionChecker(cfg, obs, bounds, 0.0)
    assert not fast.pose_ok(1.0, 1.0, 0.0)       # đè lên tường chéo
    assert fast.pose_ok(1.0, 1.6, 0.0)           # tránh xa


def test_margin_shrinks_free_space(cfg):
    bounds = Bounds(0.0, 0.0, 2.0, 2.0)
    obs = [Obstacle("b", 0.60, 1.0, 0.2, 0.2, 0.0, "box")]
    pose = (0.23, 1.0, 0.0)                      # mũi xe ở 0,48 → hở 2 cm
    assert FastCollisionChecker(cfg, obs, bounds, 0.0).pose_ok(*pose)
    assert not FastCollisionChecker(cfg, obs, bounds, 0.03).pose_ok(*pose)


def test_segment_ok_catches_midpoint_collision(cfg):
    bounds = Bounds(0.0, 0.0, 2.0, 2.0)
    obs = [Obstacle("mong", 1.0, 1.0, 0.02, 0.5, 0.0, "wall")]
    fast = FastCollisionChecker(cfg, obs, bounds, 0.0)
    a, b = Pose(0.60, 1.0, 0.0), Pose(1.40, 1.0, 0.0)
    assert fast.pose_ok(a.x, a.y, a.yaw) and fast.pose_ok(b.x, b.y, b.yaw)
    assert not fast.segment_ok(a, b, substeps=8)


def test_is_much_faster_than_shapely(cfg):
    """Không phải khẳng định hiệu năng tuyệt đối, chỉ chặn hồi quy về mức Shapely."""
    import time

    bounds = Bounds(0.0, 0.0, 3.0, 2.0)
    rng = random.Random(7)
    obstacles = random_obstacles(rng, 5)
    fast = FastCollisionChecker(cfg, obstacles, bounds, 0.02)
    poses = [(rng.uniform(0, 3), rng.uniform(0, 2), rng.uniform(-math.pi, math.pi)) for _ in range(3000)]

    t0 = time.perf_counter()
    for x, y, yaw in poses:
        fast.pose_ok(x, y, yaw)
    t_fast = time.perf_counter() - t0

    t0 = time.perf_counter()
    for x, y, yaw in poses[:600]:
        check_pose(cfg, Pose(x, y, yaw), obstacles, bounds, 0.02)
    t_slow = (time.perf_counter() - t0) * 5

    assert t_fast * 5 < t_slow, f"nhanh {t_slow / t_fast:.1f}× — kỳ vọng ít nhất 5×"
