"""Hợp nhất các lớp bản đồ thành một `Costmap` trên lưới chung.

Quy tắc từng ô: OCCUPIED nếu bất kỳ lớp tươi nào nói OCCUPIED; nếu không, FREE nếu có lớp tươi nói FREE; còn
lại UNKNOWN (bị chặn khi lập đường). Một lớp bắt buộc không tươi (chưa có dữ liệu, bị đánh dấu không hợp lệ,
hoặc quá tuổi) làm bản đồ hợp nhất KHÔNG HỢP LỆ: stamp.valid = False nên `Costmap.blocked` trả True cho mọi ô,
và `reasons` nói vì sao. Lớp tùy chọn không tươi chỉ bị bỏ qua. Không có bộ nhớ thời gian ở đây: mỗi lần gọi
là một ảnh chụp tại `now`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from autopark.domain.sensors import Costmap, SourceStamp
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec, to_costmap

from .layers import MAP_FRAME, MapLayer


@dataclass
class FusionResult:
    costmap: Costmap
    states: np.ndarray
    valid: bool
    reasons: list[str] = field(default_factory=list)
    layers: dict[str, dict] = field(default_factory=dict)

    def counts(self) -> dict:
        return {"free": int((self.states == FREE).sum()), "occupied": int((self.states == OCCUPIED).sum()),
                "unknown": int((self.states == UNKNOWN).sum())}


def fuse(layers: list[MapLayer], grid: GridSpec, now: float, *, source_id: str = "fusion") -> FusionResult:
    if not layers:
        raise ValueError("at least one layer is required")
    occupied = np.zeros(grid.shape, bool)
    free = np.zeros(grid.shape, bool)
    reasons: list[str] = []
    status: dict[str, dict] = {}
    for layer in layers:
        info = layer.status(now)
        status[layer.name] = info
        if not layer.fresh(now):
            if layer.required:
                if not info["has_data"]:
                    why = "chưa có dữ liệu"
                elif not info["valid"]:
                    why = "nguồn báo không hợp lệ"
                else:
                    why = f"quá cũ ({info['age_s']:.3f} s > {info['max_age_s']:.3f} s)"
                reasons.append(f"{layer.name}: {why}")
            continue
        states = layer.states_on(grid)
        occupied |= states == OCCUPIED
        free |= states == FREE
    states = np.full(grid.shape, UNKNOWN, np.int8)
    states[free] = FREE
    states[occupied] = OCCUPIED
    valid = not reasons
    costmap = to_costmap(states, grid, SourceStamp(source_id, max(0.0, now), valid, MAP_FRAME))
    return FusionResult(costmap, states, valid, reasons, status)
