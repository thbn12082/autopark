"""Thế giới mô phỏng: xe + sa bàn + vật cản, đồng hồ mô phỏng riêng.

Trạng thái thật chỉ đi tới bộ chấm và (sau này) bộ sinh cảm biến. Ở P2, va chạm
làm xe dừng và cờ `collided` được giữ tới khi `reset()`.
"""
from __future__ import annotations

import random
import math
from dataclasses import dataclass

from autopark.domain.types import Scenario, VehicleConfig, VehicleState
from autopark.geometry.footprint import CollisionResult, check_motion, check_pose
from autopark.simulation.vehicle import SimVehicle


@dataclass(frozen=True)
class StepResult:
    state: VehicleState
    collision: CollisionResult
    stopped_by_collision: bool


class SimWorld:
    def __init__(self, scenario: Scenario, cfg: VehicleConfig, dt: float = 0.005, seed: int | None = None):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt phải hữu hạn và > 0")
        self.scenario = scenario
        self.cfg = cfg
        self.dt = dt
        self.seed = scenario.seed if seed is None else seed
        self.rng = random.Random(self.seed)  # dành cho nhiễu/mất gói ở P4, lưu seed để lặp lại
        self.vehicle = SimVehicle(cfg, VehicleState(scenario.start, 0.0, 0.0, 0.0))
        self.last_collision = check_pose(cfg, scenario.start, scenario.obstacles, scenario.bounds)
        self.collided = not self.last_collision.ok
        self.distance = 0.0
        self.step_count = 0

    def reset(self) -> None:
        """Về trạng thái ban đầu với cùng seed."""
        self.__init__(self.scenario, self.cfg, self.dt, self.seed)

    @property
    def state(self) -> VehicleState:
        return self.vehicle.state

    @property
    def time(self) -> float:
        return self.vehicle.state.t

    def step(self, target_speed: float, target_steer: float) -> StepResult:
        if self.collided:
            # Sau va chạm xe đứng yên; vẫn tiến đồng hồ để log nhất quán.
            self.vehicle.state = VehicleState(self.state.pose, 0.0, self.state.steer, self.state.t + self.dt)
            self.step_count += 1
            return StepResult(self.state, self.last_collision, True)

        prev = self.state
        new = self.vehicle.step(self.dt, target_speed, target_steer)
        self.step_count += 1
        self.distance += abs(new.speed) * self.dt
        collision = check_motion(self.cfg, prev.pose, new.pose, self.scenario.obstacles, self.scenario.bounds)
        self.last_collision = collision
        if not collision.ok:
            self.collided = True
            self.vehicle.force_stop()
            return StepResult(self.state, collision, True)
        return StepResult(new, collision, False)
