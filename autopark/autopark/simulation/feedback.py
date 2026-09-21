"""Phản hồi giả có trễ, nhiễu và mất mẫu; seed độc lập với planner."""
from collections import deque
from dataclasses import dataclass, replace
import math
import random

from autopark.domain.types import Pose, VehicleState, wrap_angle


@dataclass(frozen=True)
class FeedbackConfig:
    delay_s: float = 0.0
    position_std_m: float = 0.0
    yaw_std_rad: float = 0.0
    drop_probability: float = 0.0
    stale_after_s: float = 0.15

    def __post_init__(self):
        for value in (self.delay_s, self.position_std_m, self.yaw_std_rad, self.stale_after_s):
            if not math.isfinite(value) or value < 0:
                raise ValueError("Tham số phản hồi phải hữu hạn và không âm")
        if not 0 <= self.drop_probability <= 1 or self.stale_after_s <= 0:
            raise ValueError("Xác suất mất mẫu hoặc thời hạn không hợp lệ")


class SimFeedback:
    def __init__(self, config: FeedbackConfig, seed: int):
        self.config = config
        self.rng = random.Random(seed)
        self.queue = deque()
        self.latest: VehicleState | None = None
        self.lost = False

    def sample(self, truth: VehicleState) -> VehicleState | None:
        c = self.config
        if not self.lost and self.rng.random() >= c.drop_probability:
            pose = Pose(truth.pose.x + self.rng.gauss(0, c.position_std_m),
                        truth.pose.y + self.rng.gauss(0, c.position_std_m),
                        wrap_angle(truth.pose.yaw + self.rng.gauss(0, c.yaw_std_rad)))
            self.queue.append((truth.t + c.delay_s, replace(truth, pose=pose, source_id="sim_feedback")))
        while self.queue and self.queue[0][0] <= truth.t + 1e-12:
            _, self.latest = self.queue.popleft()
        return self.latest

    def fresh(self, now: float) -> bool:
        return (math.isfinite(now) and self.latest is not None and self.latest.usable()
                and 0 <= now - self.latest.t <= self.config.stale_after_s)
