"""Từ ô bị chặn của một `Costmap` sang các `Obstacle` hình chữ nhật mà planner và phiên giai đoạn 0 hiểu.

Phủ chính xác: các ô bị chặn được chia thành hình chữ nhật không chồng nhau (tham lam theo hàng, kéo xuống khi
cùng dải cột), nên hợp của các vật cản đúng bằng tập ô bị chặn, không phình ra ô trống. Mặc định chỉ lấy
OCCUPIED; `include_unknown=True` chặn cả UNKNOWN đúng theo hợp đồng (an toàn hơn, nhưng vùng chưa quan sát
sẽ không đi được). Tường xiên thành bậc thang nhiều hình chữ nhật nhỏ: đủ đúng, chưa tối ưu tốc độ planner.
"""
from __future__ import annotations

import numpy as np
from shapely.ops import unary_union

from autopark.domain.sensors import Costmap
from autopark.domain.types import Bounds, Obstacle
from autopark.geometry.footprint import obstacle_polygon
from autopark.perception.costmap import OCCUPIED, UNKNOWN

from .layers import costmap_grid, costmap_states


def rectangle_cover(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Non-overlapping rectangles (row0, col0, row1, col1), inclusive, whose union is exactly `mask`."""
    mask = np.asarray(mask, bool)
    rows, cols = mask.shape
    covered = np.zeros_like(mask)
    rectangles = []
    for r in range(rows):
        c = 0
        while c < cols:
            if not mask[r, c] or covered[r, c]:
                c += 1
                continue
            c1 = c
            while c1 + 1 < cols and mask[r, c1 + 1] and not covered[r, c1 + 1]:
                c1 += 1
            r1 = r
            while r1 + 1 < rows and mask[r1 + 1, c:c1 + 1].all() and not covered[r1 + 1, c:c1 + 1].any():
                r1 += 1
            covered[r:r1 + 1, c:c1 + 1] = True
            rectangles.append((r, c, r1, c1))
            c = c1 + 1
    return rectangles


def label_clusters(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """8-connected components of `mask`: (labels int32 with 0 = background, count). One cluster ≈ one object."""
    mask = np.asarray(mask, bool)
    rows, cols = mask.shape
    labels = np.zeros(mask.shape, np.int32)
    count = 0
    for r0 in range(rows):
        for c0 in range(cols):
            if not mask[r0, c0] or labels[r0, c0]:
                continue
            count += 1
            labels[r0, c0] = count
            stack = [(r0, c0)]
            while stack:
                r, c = stack.pop()
                for rr in (r - 1, r, r + 1):
                    if rr < 0 or rr >= rows:
                        continue
                    for cc in (c - 1, c, c + 1):
                        if 0 <= cc < cols and mask[rr, cc] and not labels[rr, cc]:
                            labels[rr, cc] = count
                            stack.append((rr, cc))
    return labels, count


def blocked_mask(costmap: Costmap, *, include_unknown: bool = False, bounds: Bounds | None = None) -> np.ndarray:
    """Cells that count as blocked, restricted to those whose centre lies inside `bounds`."""
    states, grid = costmap_states(costmap), costmap_grid(costmap)
    mask = states == OCCUPIED
    if include_unknown:
        mask |= states == UNKNOWN
    if bounds is not None:
        gx, gy = grid.centers()
        mask &= (gx >= bounds.xmin) & (gx <= bounds.xmax) & (gy >= bounds.ymin) & (gy <= bounds.ymax)
    return mask


def count_objects(costmap: Costmap, *, include_unknown: bool = False, bounds: Bounds | None = None) -> dict:
    """How many blocked cells, how many connected objects and how many cover rectangles they need."""
    mask = blocked_mask(costmap, include_unknown=include_unknown, bounds=bounds)
    _, clusters = label_clusters(mask)
    return {"cells": int(mask.sum()), "objects": clusters, "rectangles": len(rectangle_cover(mask))}


def costmap_to_obstacles(costmap: Costmap, *, include_unknown: bool = False, prefix: str = "fused",
                         bounds: Bounds | None = None, start_index: int = 0) -> list[Obstacle]:
    """OCCUPIED cells become `box` obstacles, UNKNOWN cells (when included) `unknown` ones; ids are `<prefix>_<n>`.

    The rectangles are an exact cover of the blocked cells, so one physical object usually needs several of
    them (a wall seen at an angle becomes a staircase): the number of obstacles is NOT the number of objects,
    use `count_objects` for that. `Obstacle.kind` only accepts the phase-0 kinds, so ownership is carried by
    the id prefix, not the kind.
    """
    states, grid = costmap_states(costmap), costmap_grid(costmap)
    res = grid.resolution
    obstacles = []
    index = start_index
    kinds = [("box", False)] + ([("unknown", True)] if include_unknown else [])
    for kind, unknown in kinds:
        mask = blocked_mask(costmap, include_unknown=False, bounds=bounds) if not unknown else (
            blocked_mask(costmap, include_unknown=True, bounds=bounds) & (states == UNKNOWN))
        for r0, c0, r1, c1 in rectangle_cover(mask):
            cx = grid.x_min + (c0 + c1 + 1) / 2 * res
            cy = grid.y_min + (r0 + r1 + 1) / 2 * res
            obstacles.append(Obstacle(f"{prefix}_{index:05d}", cx, cy, (c1 - c0 + 1) * res, (r1 - r0 + 1) * res, 0.0, kind))
            index += 1
    return obstacles


def owned_by(obstacle: Obstacle, prefix: str) -> bool:
    return obstacle.id.startswith(prefix + "_")


def new_obstacles(existing: list[Obstacle], candidates: list[Obstacle], *, min_area: float = 1e-9,
                  margin: float = 0.0) -> list[Obstacle]:
    """Candidates that add blocked area outside `existing` grown by `margin` (new information only).

    `margin` of one cell absorbs the edge flicker of a static object seen by a real LiDAR; a genuinely new
    object farther than one cell from everything known still counts.
    """
    if not existing:
        return list(candidates)
    union = unary_union([obstacle_polygon(o) for o in existing])
    if margin > 0:
        union = union.buffer(margin, join_style="mitre")
    return [c for c in candidates if obstacle_polygon(c).difference(union).area > min_area]
