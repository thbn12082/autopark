"""Mô hình xe đạp động học có giới hạn cơ cấu chấp hành (tài liệu mục 6.1).

Mỗi bước:
1. Bão hòa mục tiêu theo giới hạn xe.
2. Góc lái tiến về mục tiêu với tốc độ đổi lái tối đa.
3. Tốc độ tiến về mục tiêu với gia tốc/phanh tối đa; đổi chiều phải qua 0 bằng phanh.
4. Tích phân tư thế theo cung tròn chính xác với tốc độ và góc lái trung bình của bước.

Không gán trực tiếp v = target_speed, δ = target_steer (mục 6.1).
"""
from __future__ import annotations

import math
from dataclasses import replace

from autopark.domain.types import Pose, VehicleConfig, VehicleState, clamp, wrap_angle


def integrate_bicycle(pose: Pose, speed: float, steer: float, dt: float, wheelbase: float) -> Pose:
    """Tích phân chính xác mô hình xe đạp với v, δ không đổi trong dt."""
    if abs(steer) < 1e-9 or abs(speed) < 1e-12:
        d = speed * dt
        return Pose(pose.x + d * math.cos(pose.yaw), pose.y + d * math.sin(pose.yaw), pose.yaw)
    curvature = math.tan(steer) / wheelbase
    dtheta = speed * curvature * dt
    radius = 1.0 / curvature
    yaw_new = pose.yaw + dtheta
    x_new = pose.x + radius * (math.sin(yaw_new) - math.sin(pose.yaw))
    y_new = pose.y - radius * (math.cos(yaw_new) - math.cos(pose.yaw))
    return Pose(x_new, y_new, wrap_angle(yaw_new))


class SimVehicle:
    """Xe mô phỏng: giữ trạng thái thật và tiến một bước theo mục tiêu."""

    def __init__(self, cfg: VehicleConfig, state: VehicleState):
        if cfg.validate() or not state.usable():
            raise ValueError("Cấu hình hoặc trạng thái xe không hợp lệ")
        self.cfg = cfg
        self.state = state

    def _next_steer(self, target_steer: float, dt: float) -> float:
        target = clamp(target_steer, -self.cfg.max_steer, self.cfg.max_steer)
        max_delta = self.cfg.max_steer_rate * dt
        return self.state.steer + clamp(target - self.state.steer, -max_delta, max_delta)

    def _next_speed(self, target_speed: float, dt: float) -> float:
        target = clamp(target_speed, -self.cfg.max_speed, self.cfg.max_speed)
        v = self.state.speed
        remaining = dt
        # Đổi chiều: phanh về 0 trước, phần thời gian còn lại mới tăng tốc theo chiều mới.
        if v * target < 0:
            t_to_zero = abs(v) / self.cfg.max_decel
            if t_to_zero >= remaining:
                return v - math.copysign(self.cfg.max_decel * remaining, v)
            v = 0.0
            remaining -= t_to_zero
        if remaining <= 0:
            return v
        increasing = abs(target) > abs(v)
        rate = self.cfg.max_accel if increasing else self.cfg.max_decel
        return v + clamp(target - v, -rate * remaining, rate * remaining)

    def step(self, dt: float, target_speed: float, target_steer: float) -> VehicleState:
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt phải hữu hạn và > 0")
        if not all(math.isfinite(v) for v in (target_speed, target_steer)) or not self.state.usable():
            raise ValueError("Lệnh hoặc trạng thái xe không hợp lệ")
        steer_new = self._next_steer(target_steer, dt)
        speed_new = self._next_speed(target_speed, dt)
        speed_avg = 0.5 * (self.state.speed + speed_new)
        steer_avg = 0.5 * (self.state.steer + steer_new)
        pose_new = integrate_bicycle(self.state.pose, speed_avg, steer_avg, dt, self.cfg.wheelbase)
        self.state = VehicleState(pose=pose_new, speed=speed_new, steer=steer_new, t=self.state.t + dt)
        return self.state

    def force_stop(self) -> VehicleState:
        """Dừng tức thời (chỉ dùng cho mô phỏng sau va chạm; xe thật không dừng tức thời)."""
        self.state = replace(self.state, speed=0.0)
        return self.state
