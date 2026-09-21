"""Log một lần chạy: trạng thái thật, mục tiêu, va chạm. Xuất CSV để đối chiếu sau."""
from __future__ import annotations

import csv
import math
from pathlib import Path

from autopark.domain.types import VehicleState
from autopark.geometry.footprint import CollisionResult


class RunLog:
    FIELDS = ["t", "x", "y", "yaw_deg", "speed", "steer_deg", "target_speed",
              "target_steer_deg", "collided", "min_clearance", "distance"]

    def __init__(self) -> None:
        self.rows: list[dict[str, float | int]] = []

    def clear(self) -> None:
        self.rows.clear()

    def add(self, state: VehicleState, target_speed: float, target_steer: float,
            collision: CollisionResult, distance: float) -> None:
        clearance = collision.min_clearance
        self.rows.append({
            "t": round(state.t, 4),
            "x": state.pose.x,
            "y": state.pose.y,
            "yaw_deg": math.degrees(state.pose.yaw),
            "speed": state.speed,
            "steer_deg": math.degrees(state.steer),
            "target_speed": target_speed,
            "target_steer_deg": math.degrees(target_steer),
            "collided": int(not collision.ok),
            "min_clearance": clearance if math.isfinite(clearance) else -1.0,
            "distance": distance,
        })

    def __len__(self) -> int:
        return len(self.rows)

    def to_csv(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)
        return path
