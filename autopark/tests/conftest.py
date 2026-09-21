import math
from pathlib import Path

import pytest

from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario, VehicleConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg() -> VehicleConfig:
    return VehicleConfig(
        name="xe_test",
        wheelbase=0.19,
        width=0.14,
        front_overhang=0.06,
        rear_overhang=0.06,
        max_steer=math.radians(30),
        max_speed=0.3,
        max_accel=0.3,
        max_decel=0.6,
        max_steer_rate=math.radians(90),
    )


@pytest.fixture
def bounds() -> Bounds:
    return Bounds(0.0, 0.0, 3.0, 2.0)


@pytest.fixture
def scenario(bounds: Bounds) -> Scenario:
    return Scenario(
        name="test",
        bounds=bounds,
        start=Pose(0.5, 1.0, 0.0),
        goal=ParkingGoal(Pose(2.4, 0.4, math.pi / 2)),
        obstacles=[Obstacle("hop_1", 1.2, 1.0, 0.2, 0.2, 0.0)],
    )
