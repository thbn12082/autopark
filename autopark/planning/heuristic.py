"""Khoảng cách trên lưới vật cản dùng bởi bộ Hybrid A* trong portfolio."""
from __future__ import annotations

import heapq
import math

from shapely.geometry import Point
from shapely.ops import unary_union
from shapely.prepared import prep

from autopark.domain.computation import checkpoint
from autopark.domain.types import Bounds, Obstacle, Pose
from autopark.geometry.footprint import obstacle_polygon


class HolonomicHeuristic:
    """Khoảng cách 2D tới đích trên lưới có vật cản (Dijkstra từ đích, 8 hướng)."""

    def __init__(self, goal: Pose, bounds: Bounds, obstacles: list[Obstacle], res: float, inflate: float):
        self.goal = goal
        self.res = res
        self.xmin, self.ymin = bounds.xmin, bounds.ymin
        self.nx = max(1, int(math.ceil(bounds.width / res)))
        self.ny = max(1, int(math.ceil(bounds.height / res)))
        polys = [obstacle_polygon(o).buffer(inflate) for o in obstacles]
        blocked_union = prep(unary_union(polys)) if polys else None
        inner = (bounds.xmin + inflate, bounds.ymin + inflate, bounds.xmax - inflate, bounds.ymax - inflate)
        self.blocked = [[False] * self.ny for _ in range(self.nx)]
        for i in range(self.nx):
            checkpoint()
            cx = self.xmin + (i + 0.5) * res
            for j in range(self.ny):
                cy = self.ymin + (j + 0.5) * res
                if not (inner[0] <= cx <= inner[2] and inner[1] <= cy <= inner[3]):
                    self.blocked[i][j] = True
                elif blocked_union is not None and blocked_union.intersects(Point(cx, cy)):
                    self.blocked[i][j] = True
        self.dist = [[math.inf] * self.ny for _ in range(self.nx)]
        gi, gj = self.cell(goal.x, goal.y)
        gi = min(max(gi, 0), self.nx - 1)
        gj = min(max(gj, 0), self.ny - 1)
        self.dist[gi][gj] = 0.0
        heap = [(0.0, gi, gj)]
        diag = res * math.sqrt(2.0)
        while heap:
            checkpoint()
            d, i, j = heapq.heappop(heap)
            if d > self.dist[i][j]:
                continue
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if di == 0 and dj == 0:
                        continue
                    ni, nj = i + di, j + dj
                    if not (0 <= ni < self.nx and 0 <= nj < self.ny):
                        continue
                    step = diag if (di and dj) else res
                    if self.blocked[ni][nj]:
                        step *= 4.0  # ô bị chặn: đi được nhưng đắt (giữ heuristic hữu hạn ở ô hẹp)
                    nd = d + step
                    if nd < self.dist[ni][nj]:
                        self.dist[ni][nj] = nd
                        heapq.heappush(heap, (nd, ni, nj))

    def cell(self, x: float, y: float) -> tuple[int, int]:
        return int((x - self.xmin) / self.res), int((y - self.ymin) / self.res)

    def __call__(self, x: float, y: float) -> float:
        i, j = self.cell(x, y)
        if 0 <= i < self.nx and 0 <= j < self.ny and math.isfinite(self.dist[i][j]):
            return self.dist[i][j]
        return math.hypot(self.goal.x - x, self.goal.y - y)
