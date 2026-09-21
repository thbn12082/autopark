"""Quỹ đạo: dãy tư thế có chiều, đoạn cùng chiều và hồ sơ tốc độ theo giới hạn xe.

Hồ sơ tốc độ hình thang cho từng đoạn cùng chiều: xuất phát từ 0 ở đầu đoạn,
về 0 ở điểm đổi chiều/đích, giới hạn bởi gia tốc và phanh của xe; đoạn cuối
đi chậm hơn trong khoảng tiếp cận. Đây là mục tiêu cho bộ bám đường, không phải
lệnh trực tiếp cho cơ cấu.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from autopark.domain.types import Pose, VehicleConfig


@dataclass(frozen=True)
class TrajectoryPoint:
    pose: Pose
    direction: int      # +1 tiến, -1 lùi
    steer: float        # góc lái danh nghĩa của đoạn sinh ra điểm này (rad)
    s: float            # quãng đường tích lũy từ đầu quỹ đạo (m)
    v: float            # độ lớn tốc độ mục tiêu (m/s)
    segment: int        # chỉ số đoạn cùng chiều


@dataclass
class Trajectory:
    points: list[TrajectoryPoint]
    goal: Pose
    segments: list[tuple[int, int]]   # (chỉ số đầu, chỉ số cuối) của từng đoạn cùng chiều
    source_id: str = "sim_planner"
    t: float = 0.0
    valid: bool = True

    @property
    def length(self) -> float:
        return self.points[-1].s if self.points else 0.0

    @property
    def n_cusps(self) -> int:
        return max(0, len(self.segments) - 1)

    @property
    def end_pose(self) -> Pose:
        return self.points[-1].pose

    def segment_points(self, i: int) -> list[TrajectoryPoint]:
        a, b = self.segments[i]
        return self.points[a:b + 1]


def build_trajectory(
    raw: list[tuple[Pose, int, float]],
    goal: Pose,
    cfg: VehicleConfig,
    cruise_speed: float,
    approach_speed: float,
    approach_distance: float = 0.30,
    creep_speed: float = 0.03,
    min_point_gap: float = 1e-4,
) -> Trajectory:
    """Từ dãy (tư thế, chiều, góc lái) dựng quỹ đạo có đoạn và hồ sơ tốc độ."""
    if not raw:
        raise ValueError("Đường rỗng")

    cleaned: list[tuple[Pose, int, float]] = []
    for pose, direction, steer in raw:
        if cleaned:
            prev_pose, prev_dir, _ = cleaned[-1]
            if prev_dir == direction and math.hypot(pose.x - prev_pose.x, pose.y - prev_pose.y) < min_point_gap:
                continue
        cleaned.append((pose, direction, steer))

    # Chia đoạn theo chiều; điểm đổi chiều xuất hiện ở cả cuối đoạn trước và đầu đoạn sau.
    segments_pts: list[list[tuple[Pose, int, float]]] = []
    for item in cleaned:
        if not segments_pts:
            segments_pts.append([item])
            continue
        if segments_pts[-1][-1][1] != item[1]:
            cusp_pose = segments_pts[-1][-1][0]
            segments_pts.append([(cusp_pose, item[1], item[2]), item])
        else:
            segments_pts[-1].append(item)
    segments_pts = [seg for seg in segments_pts if len(seg) >= 2]
    if not segments_pts:
        # Xuất phát đã ở đích: một đoạn suy biến gồm hai điểm trùng
        pose, direction, steer = cleaned[0]
        segments_pts = [[(pose, direction, steer), (pose, direction, steer)]]

    points: list[TrajectoryPoint] = []
    segments: list[tuple[int, int]] = []
    s_total = 0.0
    n_seg = len(segments_pts)
    for si, seg in enumerate(segments_pts):
        dists = [0.0]
        for (pa, _, _), (pb, _, _) in zip(seg, seg[1:]):
            dists.append(dists[-1] + math.hypot(pb.x - pa.x, pb.y - pa.y))
        seg_len = dists[-1]
        start_idx = len(points)
        last_segment = si == n_seg - 1
        for k, (pose, direction, steer) in enumerate(seg):
            s_from, s_to = dists[k], seg_len - dists[k]
            v = min(cruise_speed,
                    math.sqrt(max(0.0, 2 * cfg.max_accel * s_from)),
                    math.sqrt(max(0.0, 2 * cfg.max_decel * s_to)))
            if last_segment and s_to < approach_distance:
                v = min(v, approach_speed)
            v = 0.0 if s_to <= 1e-9 else min(cfg.max_speed, max(v, creep_speed))
            points.append(TrajectoryPoint(pose, direction, steer, s_total + dists[k], v, si))
        segments.append((start_idx, len(points) - 1))
        s_total += seg_len
    return Trajectory(points, goal, segments)
