"""Generate varied parked-car poses while keeping geometry valid.

This validates placement, not path feasibility. The planner still decides whether
the resulting parking problem can be solved.
"""
from __future__ import annotations

import math
import random
from dataclasses import replace

from shapely.geometry import Polygon

from autopark.domain.types import Obstacle, Scenario, VehicleConfig
from autopark.geometry.footprint import body_polygon, bounds_polygon, obstacle_polygon


def scatter_parked_cars(scenario: Scenario, cfg: VehicleConfig, seed: int,
                        attempts_per_car: int = 200, restarts: int = 5) -> list[Obstacle]:
    cars = [o for o in scenario.obstacles if o.kind == "car"]
    if not cars:
        raise ValueError("Sa bàn chưa có xe đỗ để xáo")
    if attempts_per_car < 1 or restarts < 1:
        raise ValueError("Số lần thử phải lớn hơn 0")
    rng = random.Random(seed)
    bounds = scenario.bounds
    inner = bounds_polygon(bounds).buffer(-0.02)
    goal = (scenario.slot.goal_pose(cfg, scenario.mode, scenario.start.yaw)
            if scenario.slot is not None else scenario.goal.pose)
    reserved = [body_polygon(cfg, scenario.start).buffer(0.08), body_polygon(cfg, goal).buffer(0.08)]
    if scenario.slot is not None:
        reserved.append(Polygon(scenario.slot.corners()).buffer(0.03))
    reserved.extend(obstacle_polygon(o).buffer(0.03) for o in scenario.obstacles if o.kind != "car")
    # Place large bodies first; no part of the input scenario is changed on failure.
    cars.sort(key=lambda o: o.width * o.height, reverse=True)
    for _ in range(restarts):
        occupied = list(reserved)
        placed = {}
        for car in cars:
            for _ in range(attempts_per_car):
                yaw = rng.uniform(-math.pi, math.pi)
                c, s = abs(math.cos(yaw)), abs(math.sin(yaw))
                ex = (c * car.width + s * car.height) / 2 + 0.02
                ey = (s * car.width + c * car.height) / 2 + 0.02
                if 2 * ex >= bounds.width or 2 * ey >= bounds.height:
                    continue
                candidate = replace(car, cx=rng.uniform(bounds.xmin + ex, bounds.xmax - ex),
                                    cy=rng.uniform(bounds.ymin + ey, bounds.ymax - ey), yaw=yaw)
                poly = Polygon(candidate.corners())
                if not inner.contains(poly) or any(poly.intersects(other) for other in occupied):
                    continue
                placed[car.id] = candidate
                occupied.append(poly.buffer(0.03))
                break
            else:
                break
        if len(placed) == len(cars):
            return [placed.get(o.id, o) for o in scenario.obstacles]
    raise ValueError("Chưa xếp được tất cả xe mà không chồng lấn; hãy giảm số xe hoặc chừa thêm khoảng trống")
