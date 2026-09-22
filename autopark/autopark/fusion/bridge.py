"""Cầu nối bản đồ hợp nhất → phiên giai đoạn 0 (`application.session.Session`).

Đang chỉnh sa bàn: `sync()` thay toàn bộ vật cản do cầu nối tạo bằng ô bị chặn hiện tại. Đang chạy: `inject()`
chỉ đưa vào những hình chữ nhật mang THÔNG TIN MỚI (không nằm trọn trong vật cản đã biết, nới một ô) VÀ chạm
hành lang thân xe dọc phần quỹ đạo còn lại (nới `path_margin`); vật mới ngoài hành lang được ghi nhớ trong
`seen` chứ không làm dừng xe, đúng nghĩa "vật mới làm đường mất hiệu lực" của kế hoạch. Vật cản mới trên đường
đầu tiên làm phiên phát MAP_CHANGED → phanh → chờ lập lại đường, logic đã có của giai đoạn 0. Bản đồ hợp nhất
không hợp lệ (lớp bắt buộc cũ/mất) khi đang chạy → yêu cầu dừng với lý do; đây là "dữ liệu cũ thì không dùng".
Cầu nối không gọi planner và không sửa tư thế xe. Đo trên bàn 22/09: không có hành lang, cảnh tĩnh vẫn dừng
xe ảo trong vòng một giây vì vài ô lẻ tẻ cách đường 40 cm trở lên.
"""
from __future__ import annotations

from dataclasses import replace

from shapely.ops import unary_union

from autopark.application.session import Session, SessionState
from autopark.domain.types import Obstacle
from autopark.geometry.footprint import body_polygon, obstacle_polygon

from .fuse import FusionResult
from .obstacles import costmap_to_obstacles, new_obstacles, owned_by


def path_corridor(trajectory, cfg, *, margin: float, start_index: int = 0, spacing: float = 0.03):
    """Union of the vehicle body (grown by `margin`) along the trajectory from `start_index`; None if empty."""
    points = trajectory.points[start_index:]
    if not points:
        return None
    chosen, last_s = [], None
    for point in points:
        if last_s is None or point.s - last_s >= spacing:
            chosen.append(point)
            last_s = point.s
    if chosen[-1] is not points[-1]:
        chosen.append(points[-1])
    return unary_union([body_polygon(cfg, p.pose, margin) for p in chosen])


class ObstacleBridge:
    def __init__(self, session: Session, *, prefix: str = "fused", include_unknown: bool = False,
                 new_margin: float | None = None, path_margin: float | None = 0.10):
        """`new_margin` (default: one cell of the fused grid) is how far outside known obstacles a blocked cell
        must lie to count as new information; `path_margin` grows the body corridor along the remaining path
        (None: every new obstacle stops the car, wherever it is)."""
        self.session = session
        self.prefix = prefix
        self.include_unknown = include_unknown
        self.new_margin = new_margin
        self.path_margin = path_margin
        self.counter = 0
        self.stops = 0
        self.seen: list[Obstacle] = []      # new but off the path: remembered, not injected

    def _candidates(self, fused: FusionResult) -> list[Obstacle]:
        return costmap_to_obstacles(fused.costmap, include_unknown=self.include_unknown, prefix=self.prefix,
                                    bounds=self.session.scenario.bounds)

    def _numbered(self, obstacles: list[Obstacle]) -> list[Obstacle]:
        """Fresh, never reused ids for the obstacles that really enter the scenario."""
        out = []
        for obstacle in obstacles:
            out.append(replace(obstacle, id=f"{self.prefix}_{self.counter:05d}"))
            self.counter += 1
        return out

    def owned(self) -> list[Obstacle]:
        return [o for o in self.session.scenario.obstacles if owned_by(o, self.prefix)]

    def sync(self, fused: FusionResult) -> list[Obstacle]:
        """While the scenario is editable: replace this bridge's obstacles with the current blocked cells."""
        if self.session.state not in (SessionState.EDITING, SessionState.READY):
            raise RuntimeError("sync() only while editing; use inject() during a run")
        for obstacle in self.owned():
            self.session.remove_obstacle(obstacle.id)
        self.seen = []
        added = self._numbered(self._candidates(fused)) if fused.valid else []
        for obstacle in added:
            self.session.add_obstacle(obstacle)
        return added

    @staticmethod
    def _key(obstacle: Obstacle) -> tuple:
        return (round(obstacle.cx, 4), round(obstacle.cy, 4), round(obstacle.width, 4), round(obstacle.height, 4), obstacle.kind)

    def sync_incremental(self, fused: FusionResult) -> tuple[list[Obstacle], list[Obstacle]]:
        """Live map while editing: keep rectangles that are still blocked, drop the ones that vanished, add the new
        ones. Returns (added, removed). An invalid fused map changes nothing (no evidence is not free space)."""
        if self.session.state not in (SessionState.EDITING, SessionState.READY):
            raise RuntimeError("sync_incremental() only while editing; use inject() during a run")
        if not fused.valid:
            return [], []
        wanted = {self._key(c): c for c in self._candidates(fused)}
        owned = {self._key(o): o for o in self.owned()}
        removed = [o for key, o in owned.items() if key not in wanted]
        for obstacle in removed:
            self.session.remove_obstacle(obstacle.id)
        added = self._numbered([c for key, c in wanted.items() if key not in owned])
        for obstacle in added:
            self.session.add_obstacle(obstacle)
        self.seen = []
        return added, removed

    def inject(self, fused: FusionResult) -> list[Obstacle]:
        """During a run: stop on an invalid map, otherwise inject only rectangles that add blocked area."""
        if self.session.state not in (SessionState.RUNNING, SessionState.STOPPING):
            return []
        if not fused.valid:
            self.stops += 1
            self.session.request_stop("Bản đồ hợp nhất không hợp lệ: " + "; ".join(fused.reasons))
            return []
        margin = fused.costmap.resolution_m if self.new_margin is None else self.new_margin
        fresh = new_obstacles(self.session.scenario.obstacles + self.seen, self._candidates(fused), margin=margin)
        if not fresh:
            return []
        corridor = None
        trajectory = self.session.trajectory
        if self.path_margin is not None and trajectory is not None and trajectory.points:
            start = self.session.tracker.index if self.session.tracker is not None else 0
            corridor = path_corridor(trajectory, self.session.cfg, margin=self.path_margin, start_index=start)
        if corridor is None:
            on_path, off_path = fresh, []
        else:
            on_path = [o for o in fresh if obstacle_polygon(o).intersects(corridor)]
            off_path = [o for o in fresh if o not in on_path]
        self.seen.extend(self._numbered(off_path))
        on_path = self._numbered(on_path)
        for obstacle in on_path:
            self.session.inject_obstacle(obstacle)
        return on_path
