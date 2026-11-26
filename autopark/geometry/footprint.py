"""Đa giác thân xe, vật cản, vùng sa bàn và kiểm tra va chạm.

Kiểm tra toàn bộ thân xe kể cả phần nhô đầu/đuôi (tài liệu mục 8.4). Với chuyển
động giữa hai mẫu, dùng bao lồi của hai footprint làm xấp xỉ vùng quét; xấp xỉ
này đúng khi bước chuyển động nhỏ so với kích thước xe (bước vật lý 5 ms ở
tốc độ < 0,5 m/s cho dịch chuyển < 2,5 mm).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from autopark.domain.types import Bounds, Obstacle, Pose, VehicleConfig


def body_corners(cfg: VehicleConfig, pose: Pose) -> list[tuple[float, float]]:
    """Bốn góc thân xe trong hệ bản đồ: sau-trái, sau-phải, trước-phải, trước-trái."""
    rear = -cfg.rear_overhang
    front = cfg.wheelbase + cfg.front_overhang
    half = cfg.width / 2
    local = [(rear, half), (rear, -half), (front, -half), (front, half)]
    return [pose.to_world(px, py) for px, py in local]


def body_polygon(cfg: VehicleConfig, pose: Pose, margin: float = 0.0) -> Polygon:
    poly = Polygon(body_corners(cfg, pose))
    if margin > 0:
        # join_style=2 (mitre) giữ góc vuông khi nới thân xe
        poly = poly.buffer(margin, join_style=2)
    return poly


@lru_cache(maxsize=1024)
def obstacle_polygon(obs: Obstacle) -> Polygon:
    # Obstacle là dataclass frozen; sửa vị trí/kích thước tạo khóa mới.
    # Shapely 2 dùng geometry bất biến. Cache có giới hạn, dùng chung giữa các lượt mô phỏng.
    return Polygon(obs.corners())


@lru_cache(maxsize=128)
def bounds_polygon(bounds: Bounds) -> Polygon:
    return box(bounds.xmin, bounds.ymin, bounds.xmax, bounds.ymax)


@dataclass(frozen=True)
class CollisionResult:
    collides: bool
    obstacle_ids: list[str] = field(default_factory=list)
    out_of_bounds: bool = False
    min_clearance: float = math.inf   # m, tới vật cản hoặc mép sa bàn gần nhất; 0 khi đang chạm

    @property
    def ok(self) -> bool:
        return not self.collides and not self.out_of_bounds

    def describe(self) -> str:
        parts = []
        if self.obstacle_ids:
            parts.append("va chạm " + ", ".join(self.obstacle_ids))
        if self.out_of_bounds:
            parts.append("ra ngoài sa bàn")
        if not parts:
            return f"hở {self.min_clearance * 100:.1f} cm"
        return "; ".join(parts)


def _evaluate(body: Polygon, obstacles: list[Obstacle], bounds: Bounds) -> CollisionResult:
    hit_ids: list[str] = []
    clearance = math.inf
    for obs in obstacles:
        op = obstacle_polygon(obs)
        if body.intersects(op):
            hit_ids.append(obs.id)
            clearance = 0.0
        else:
            clearance = min(clearance, body.distance(op))
    bp = bounds_polygon(bounds)
    inside = bp.contains(body)
    if inside:
        clearance = min(clearance, body.distance(bp.exterior))
    else:
        clearance = 0.0
    return CollisionResult(
        collides=bool(hit_ids),
        obstacle_ids=hit_ids,
        out_of_bounds=not inside,
        min_clearance=clearance,
    )


def check_pose(cfg: VehicleConfig, pose: Pose, obstacles: list[Obstacle],
               bounds: Bounds, margin: float = 0.0) -> CollisionResult:
    """Kiểm tra một tư thế: thân xe (đã nới `margin`) có chạm vật cản hoặc ra ngoài không."""
    return _evaluate(body_polygon(cfg, pose, margin), obstacles, bounds)


def swept_polygon(cfg: VehicleConfig, pose_a: Pose, pose_b: Pose, margin: float = 0.0) -> Polygon:
    """Xấp xỉ vùng thân xe quét giữa hai tư thế bằng bao lồi của hai footprint."""
    a = body_polygon(cfg, pose_a, margin)
    b = body_polygon(cfg, pose_b, margin)
    hull = unary_union([a, b]).convex_hull
    # Bao lồi hai đầu có thể bỏ sót góc thân xe quét ra ngoài khi quay.
    # Nới theo độ võng cung của góc thân và tâm trục sau (cung xe đạp).
    angle = abs(math.atan2(math.sin(pose_b.yaw - pose_a.yaw), math.cos(pose_b.yaw - pose_a.yaw)))
    radius = math.hypot(max(cfg.rear_overhang, cfg.wheelbase + cfg.front_overhang) + margin,
                        cfg.width / 2 + margin)
    padding = radius * (1 - math.cos(angle / 2)) + pose_a.distance_to(pose_b) / 2 * math.tan(angle / 4)
    return hull.buffer(padding, quad_segs=16) if padding > 1e-12 else hull


def check_motion(cfg: VehicleConfig, pose_a: Pose, pose_b: Pose, obstacles: list[Obstacle],
                 bounds: Bounds, margin: float = 0.0) -> CollisionResult:
    """Kiểm tra chuyển động giữa hai mẫu liên tiếp (không chỉ hai điểm đầu/cuối)."""
    return _evaluate(swept_polygon(cfg, pose_a, pose_b, margin), obstacles, bounds)
