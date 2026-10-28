"""Phạm vi cục bộ của một thao tác, dùng chung khi lập đường và trước START."""
from __future__ import annotations

import math

from autopark.domain.types import Bounds, Scenario, VehicleConfig, VehicleState
from autopark.geometry.footprint import check_motion, check_pose
from autopark.planning.trajectory import Trajectory


def maneuver_bounds(scenario: Scenario) -> Bounds:
    limits = scenario.maneuver
    if limits is None:
        return scenario.bounds
    b, p, r = scenario.bounds, scenario.start, limits.area_half_extent_m
    return Bounds(max(b.xmin, p.x - r), max(b.ymin, p.y - r),
                  min(b.xmax, p.x + r), min(b.ymax, p.y + r))


def runtime_problem(scenario: Scenario, cfg: VehicleConfig, state: VehicleState,
                    distance: float, dt: float) -> tuple[str, str] | None:
    """Cùng quyết định phanh cho chạy thật, xem trước và kiểm chứng ứng viên."""
    limits = scenario.maneuver
    if limits is None:
        return None
    speed = abs(state.speed)
    # The next check is one physics step away, during which the tracker may
    # still accelerate. Reserve that step AND the braking distance at its end.
    next_speed = max(speed, min(cfg.max_speed, speed + cfg.max_accel * dt))
    braking = (speed + next_speed) * dt / 2 + next_speed * next_speed / (2 * cfg.max_decel)
    if distance + braking >= limits.max_path_length_m:
        return ("MANEUVER_DISTANCE", "Đã tới giới hạn quãng đường của thao tác; dừng để chọn lại đích")
    # A turning corner travels farther than the rear axle. At body point (x,y),
    # its velocity per axle speed is (1 - curvature*y, curvature*x). The maximum
    # over the body and allowed steering bounds every corner's stopping sweep.
    curvature = math.tan(cfg.max_steer) / cfg.wheelbase
    front = max(cfg.rear_overhang, cfg.wheelbase + cfg.front_overhang)
    body_speed_ratio = math.hypot(1 + curvature * cfg.width / 2, curvature * front)
    if not check_pose(cfg, state.pose, [], maneuver_bounds(scenario), margin=braking * body_speed_ratio).ok:
        return ("MANEUVER_AREA", "Đã tới mép vùng thao tác gần; dừng để người lái đánh giá lại")
    return None


def request_problem(scenario: Scenario, cfg: VehicleConfig) -> str | None:
    limits = scenario.maneuver
    if limits is None or scenario.slot is not None:
        return "Kịch bản phải có giới hạn thao tác gần và đích trực tiếp; không hỗ trợ ô đỗ."
    distance = scenario.start.distance_to(scenario.goal.pose)
    if distance > limits.max_goal_distance_m:
        return (f"Đích cách xe {distance * 100:.0f} cm; thao tác gần chỉ nhận đích trong "
                f"{limits.max_goal_distance_m * 100:.0f} cm. Hãy chọn đích gần hơn.")
    bounds = maneuver_bounds(scenario)
    for label, pose in (("Xuất phát", scenario.start), ("Đích", scenario.goal.pose)):
        if not check_pose(cfg, pose, [], bounds).ok:
            return f"{label}: toàn thân xe phải nằm trong vùng thao tác gần."
    return None


def trajectory_problem(scenario: Scenario, cfg: VehicleConfig, trajectory: Trajectory) -> str | None:
    limits = scenario.maneuver
    problem = request_problem(scenario, cfg)
    if problem:
        return problem
    if not trajectory.valid or not trajectory.points:
        return "Thao tác chưa có quỹ đạo hợp lệ."
    # Đo lại hình học, không chỉ tin tổng s của bộ lập đường.
    points = trajectory.points
    if (not all(math.isfinite(v) for v in (trajectory.goal.x, trajectory.goal.y, trajectory.goal.yaw))
            or any(not all(math.isfinite(v) for v in (p.pose.x, p.pose.y, p.pose.yaw, p.s, p.steer, p.v))
                   for p in points)):
        return "Quỹ đạo chứa tư thế hoặc quãng đường không hợp lệ."
    if (points[0].pose.distance_to(scenario.start) > 1e-6
            or abs(points[0].pose.heading_error_to(scenario.start)) > 1e-6
            or trajectory.goal.distance_to(scenario.goal.pose) > 1e-6
            or abs(trajectory.goal.heading_error_to(scenario.goal.pose)) > 1e-6
            or points[-1].pose.distance_to(scenario.goal.pose) > scenario.goal.tolerance_xy
            or abs(points[-1].pose.heading_error_to(scenario.goal.pose)) > scenario.goal.tolerance_yaw):
        return "Quỹ đạo không còn khớp tư thế xuất phát hoặc đích đã chọn."
    length = sum(a.pose.distance_to(b.pose) for a, b in zip(points, points[1:]))
    if not math.isfinite(trajectory.length) or max(length, trajectory.length) > limits.max_path_length_m:
        return f"Đường vượt giới hạn {limits.max_path_length_m:.2f} m cho một thao tác gần."
    if any(type(p.direction) is not int or p.direction not in (-1, 1)
           or type(p.segment) is not int or p.segment < 0 or p.s < 0
           or not 0 <= p.v <= cfg.max_speed + 1e-9 or abs(p.steer) > cfg.max_steer + 1e-9 for p in points):
        return "Quỹ đạo chứa chiều, tốc độ hoặc góc lái không hợp lệ."
    # The tracker indexes by segments and uses s to decide where to brake.
    # Geometry alone is insufficient: corrupt metadata must fail before ARM.
    if not trajectory.segments:
        return "Quỹ đạo chưa có các đoạn tiến/lùi hợp lệ."
    expected_start = 0
    for si, segment in enumerate(trajectory.segments):
        if (len(segment) != 2 or any(type(i) is not int for i in segment)
                or segment[0] != expected_start or not segment[0] <= segment[1] < len(points)):
            return "Các đoạn tiến/lùi không phủ liên tục quỹ đạo."
        a, b = segment
        if any(p.segment != si or p.direction != points[a].direction for p in points[a:b + 1]):
            return "Chiều của điểm không khớp đoạn tiến/lùi."
        if si and (points[a - 1].direction == points[a].direction
                   or points[a - 1].pose.distance_to(points[a].pose) > 1e-6
                   or abs(points[a - 1].pose.heading_error_to(points[a].pose)) > 1e-6):
            return "Các đoạn tiến/lùi không nối tại cùng tư thế đổi chiều."
        expected_start = b + 1
    if expected_start != len(points):
        return "Các đoạn tiến/lùi không phủ liên tục quỹ đạo."
    cumulative = 0.0
    for i, point in enumerate(points):
        if i:
            cumulative += points[i - 1].pose.distance_to(point.pose)
        if abs(point.s - cumulative) > 1e-6:
            return "Quãng đường tích lũy không khớp hình học quỹ đạo."
    cusps = sum(a.direction != b.direction for a, b in zip(points, points[1:]))
    if max(cusps, trajectory.n_cusps) > limits.max_cusps:
        return f"Thao tác vượt giới hạn {limits.max_cusps} lần đổi chiều."
    bounds = maneuver_bounds(scenario)
    if not check_pose(cfg, points[0].pose, scenario.obstacles, bounds).ok:
        return "Đường chạm vật cản hoặc rời vùng thao tác gần."
    for a, b in zip(points, points[1:]):
        if not check_motion(cfg, a.pose, b.pose, scenario.obstacles, bounds).ok:
            return "Đường chạm vật cản hoặc rời vùng thao tác gần."
    return None
