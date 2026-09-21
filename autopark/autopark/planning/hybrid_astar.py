"""Hybrid A* cho xe lái kiểu ô tô, có tiến/lùi, dùng Reeds–Shepp để nối đích.

Tìm kiếm trên lưới (x, y, yaw, chiều). Mỗi bước mở rộng là một cung ngắn với góc
lái cố định, tiến hoặc lùi, kiểm tra va chạm bằng thân xe đã nới lề an toàn.
Heuristic: max(khoảng cách 2D có vật cản, độ dài Reeds–Shepp không vật cản khi
gần đích). Khi gần đích thử nối thẳng bằng đường Reeds–Shepp có kiểm tra va chạm.
Đường trả về được kiểm tra lại vùng quét với thân xe thật trước khi thành quỹ đạo.
"""
from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep

from autopark.domain.computation import checkpoint
from autopark.planning.computation import controlled_plan
from autopark.domain.types import Bounds, Obstacle, Pose, VehicleConfig, wrap_angle
from autopark.geometry.footprint import check_motion, check_pose, obstacle_polygon
from autopark.planning.reeds_shepp import candidate_paths, sample_path, shortest_length
from autopark.planning.trajectory import Trajectory, build_trajectory
from autopark.simulation.vehicle import integrate_bicycle


@dataclass
class PlannerParams:
    xy_resolution: float = 0.05
    yaw_resolution: float = math.radians(10.0)
    step_length: float = 0.08          # m mỗi bước mở rộng
    n_steer: int = 5                   # số mức góc lái (lẻ để có 0)
    steer_ratio: float = 0.85          # lập đường với phần này của góc lái tối đa, chừa dư địa cho bộ bám
    reverse_cost: float = 1.3          # hệ số quãng đường lùi
    switch_cost: float = 0.6           # m tương đương cho mỗi lần đổi chiều
    steer_cost: float = 0.15           # theo |góc lái| (rad) nhân quãng đường
    steer_change_cost: float = 0.3     # theo |đổi góc lái| (rad)
    heuristic_weight: float = 1.0
    safety_margin: float = 0.03        # m nới thân xe khi tìm kiếm
    # Lề an toàn là một ĐÁNH ĐỔI, không phải một hằng số đúng:
    #  - lề rộng thì đường chạy xa vật cản, bộ bám đường dễ theo;
    #  - lề hẹp thì ô chật mới có nghiệm, nhưng đường sát vật cản và khó bám hơn.
    # ĐO ĐƯỢC: hạ share từ 0,50 xuống 0,40 làm ca pillar_at_slot_mouth chuyển từ
    # bám được sang bám hỏng. Nên mặc định giữ mức an toàn, và để `portfolio.py`
    # nới dần khi mức an toàn không ra đường.
    margin_floor: float = 0.0
    margin_clearance_share: float = 0.50
    goal_xy_tol: float = 0.03
    goal_yaw_tol: float = math.radians(3.0)
    rs_radius: float = 1.5             # m: gần đích mới thử nối Reeds–Shepp và dùng heuristic RS
    rs_every: int = 3                  # thử nối mỗi N nút lấy ra
    rs_max_candidates: int = 3
    rs_sample_step: float = 0.03
    path_sample_step: float = 0.02
    max_nodes: int = 150_000
    time_limit: float = 8.0
    cruise_speed: float = 0.15
    approach_speed: float = 0.08
    approach_distance: float = 0.30


@dataclass
class PlanResult:
    status: str                       # OK, NO_PATH, TIMEOUT, CANCELLED, ERROR, GOAL_INVALID,
                                      # START_INVALID, TRACKING_FAILED
    message: str
    trajectory: Trajectory | None = None
    elapsed: float = 0.0
    expanded: int = 0
    popped: int = 0
    rs_tries: int = 0
    margin_used: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "OK"


class CollisionChecker:
    """Kiểm tra nhanh một tư thế: thân xe (đã nới lề) trong sa bàn và không chạm vật cản."""

    def __init__(self, cfg: VehicleConfig, obstacles: list[Obstacle], bounds: Bounds, margin: float):
        self.rear = -(cfg.rear_overhang + margin)
        self.front = cfg.wheelbase + cfg.front_overhang + margin
        self.half = cfg.width / 2 + margin
        self.bounds = bounds
        polys = [obstacle_polygon(o) for o in obstacles]
        self.prepared = prep(unary_union(polys)) if polys else None

    def pose_ok(self, x: float, y: float, yaw: float) -> bool:
        c, s = math.cos(yaw), math.sin(yaw)
        b = self.bounds
        corners = []
        for px, py in ((self.rear, self.half), (self.rear, -self.half), (self.front, -self.half), (self.front, self.half)):
            wx = x + c * px - s * py
            wy = y + s * px + c * py
            if wx < b.xmin or wx > b.xmax or wy < b.ymin or wy > b.ymax:
                return False
            corners.append((wx, wy))
        if self.prepared is None:
            return True
        return not self.prepared.intersects(Polygon(corners))


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


@dataclass
class _Node:
    x: float
    y: float
    yaw: float
    direction: int
    steer: float
    g: float
    parent: int


def _steer_for(mode: str, max_steer: float) -> float:
    return max_steer if mode == "L" else -max_steer if mode == "R" else 0.0


@controlled_plan(8.0)
def plan(start: Pose, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle], bounds: Bounds,
         params: PlannerParams | None = None) -> PlanResult:
    params = params or PlannerParams()
    t0 = time.perf_counter()

    goal_true = check_pose(cfg, goal, obstacles, bounds)
    if not goal_true.ok:
        return PlanResult("GOAL_INVALID", "Đích không hợp lệ: " + goal_true.describe())
    start_true = check_pose(cfg, start, obstacles, bounds)
    if not start_true.ok:
        return PlanResult("START_INVALID", "Xuất phát không hợp lệ: " + start_true.describe())
    # Lề an toàn không được ăn quá phần khoảng hở tại đích, nếu không xe đã nằm trong ô
    # sẽ không còn một hành động hợp lệ nào, và bài toán thành vô nghiệm vì lề chứ không
    # vì hình học. ĐO ĐƯỢC: ô đỗ hở 2 cm cho ra lề 1 cm, khi đó lập đường ngược từ đích
    # chết ngay ở nút đầu tiên. Sàn 4 mm đủ bù sai số xấp xỉ vùng quét ở bước 5 cm.
    margin = min(params.safety_margin,
                 goal_true.min_clearance * params.margin_clearance_share,
                 start_true.min_clearance * params.margin_clearance_share)
    margin = min(max(margin, params.margin_floor), params.safety_margin)

    checker = CollisionChecker(cfg, obstacles, bounds, margin)
    max_steer = cfg.max_steer * params.steer_ratio
    maxc = math.tan(max_steer) / cfg.wheelbase
    inflate = min(cfg.width / 2, cfg.rear_overhang) + margin
    holonomic = HolonomicHeuristic(goal, bounds, obstacles, params.xy_resolution, inflate)

    n = max(3, params.n_steer | 1)
    steer_set = [-max_steer + i * (2 * max_steer / (n - 1)) for i in range(n)]
    n_yaw = max(1, int(round(2 * math.pi / params.yaw_resolution)))

    def key(x: float, y: float, yaw: float, direction: int) -> tuple[int, int, int, int]:
        return (int((x - bounds.xmin) / params.xy_resolution),
                int((y - bounds.ymin) / params.xy_resolution),
                int(((yaw + math.pi) % (2 * math.pi)) / params.yaw_resolution) % n_yaw,
                direction)

    def heuristic(x: float, y: float, yaw: float) -> float:
        h = holonomic(x, y)
        if math.hypot(goal.x - x, goal.y - y) < params.rs_radius:
            rs = shortest_length(Pose(x, y, yaw), goal, maxc)
            if math.isfinite(rs):
                h = max(h, rs)
        return params.heuristic_weight * h

    nodes: list[_Node] = [_Node(start.x, start.y, start.yaw, 0, 0.0, 0.0, -1)]
    best: dict[tuple[int, int, int, int], float] = {key(start.x, start.y, start.yaw, 0): 0.0}
    closed: set[tuple[int, int, int, int]] = set()
    heap: list[tuple[float, int, int]] = [(heuristic(start.x, start.y, start.yaw), 0, 0)]
    counter = 1
    expanded = popped = rs_tries = 0
    raw_path: list[tuple[Pose, int, float]] | None = None
    status, message = "NO_PATH", "Không tìm được đường trong không gian tìm kiếm"

    while heap:
        checkpoint()
        _, _, nid = heapq.heappop(heap)
        node = nodes[nid]
        k = key(node.x, node.y, node.yaw, node.direction)
        if k in closed:
            continue
        closed.add(k)
        popped += 1
        elapsed = time.perf_counter() - t0
        if popped > params.max_nodes or elapsed > params.time_limit:
            status, message = "TIMEOUT", f"Quá giới hạn tìm kiếm ({popped} nút, {elapsed:.1f} s)"
            break

        node_pose = Pose(node.x, node.y, node.yaw)
        dist_goal = math.hypot(goal.x - node.x, goal.y - node.y)
        if dist_goal < params.goal_xy_tol and abs(wrap_angle(node.yaw - goal.yaw)) < params.goal_yaw_tol:
            raw_path = _reconstruct(nodes, nid, cfg, params)
            break

        if dist_goal < params.rs_radius and (popped % params.rs_every == 0 or dist_goal < 0.3):
            rs_tries += 1
            tail = _try_reeds_shepp(node_pose, goal, maxc, max_steer, checker, params,
                                    cfg, obstacles, bounds)
            if tail is not None:
                raw_path = _reconstruct(nodes, nid, cfg, params) + tail
                break

        for direction in (1, -1):
            for steer in steer_set:
                mid = integrate_bicycle(node_pose, direction * params.step_length / 2, steer, 1.0, cfg.wheelbase)
                if not checker.pose_ok(mid.x, mid.y, mid.yaw):
                    continue
                nxt = integrate_bicycle(node_pose, direction * params.step_length, steer, 1.0, cfg.wheelbase)
                if not checker.pose_ok(nxt.x, nxt.y, nxt.yaw):
                    continue
                nk = key(nxt.x, nxt.y, nxt.yaw, direction)
                if nk in closed:
                    continue
                cost = params.step_length * (params.reverse_cost if direction < 0 else 1.0)
                cost += params.steer_cost * abs(steer) * params.step_length
                cost += params.steer_change_cost * abs(steer - node.steer)
                if node.direction != 0 and direction != node.direction:
                    cost += params.switch_cost
                g = node.g + cost
                if g >= best.get(nk, math.inf):
                    continue
                best[nk] = g
                nodes.append(_Node(nxt.x, nxt.y, nxt.yaw, direction, steer, g, nid))
                heapq.heappush(heap, (g + heuristic(nxt.x, nxt.y, nxt.yaw), counter, len(nodes) - 1))
                counter += 1
                expanded += 1

    elapsed = time.perf_counter() - t0
    if raw_path is None:
        return PlanResult(status, message, None, elapsed, expanded, popped, rs_tries, margin)

    # Kiểm tra lại vùng quét với thân xe thật (không nới lề)
    for (pa, _, _), (pb, _, _) in zip(raw_path, raw_path[1:]):
        checkpoint()
        col = check_motion(cfg, pa, pb, obstacles, bounds)
        if not col.ok:
            return PlanResult("NO_PATH", "Đường tìm được vi phạm kiểm tra vùng quét: " + col.describe(),
                              None, elapsed, expanded, popped, rs_tries, margin)

    trajectory = build_trajectory(raw_path, goal, cfg, params.cruise_speed, params.approach_speed,
                                  params.approach_distance)
    return PlanResult("OK", f"Tìm được đường dài {trajectory.length:.2f} m, {trajectory.n_cusps} lần đổi chiều",
                      trajectory, elapsed, expanded, popped, rs_tries, margin)


def _try_reeds_shepp(node_pose: Pose, goal: Pose, maxc: float, max_steer: float,
                     checker: CollisionChecker, params: PlannerParams, cfg: VehicleConfig,
                     obstacles: list[Obstacle], bounds: Bounds) -> list[tuple[Pose, int, float]] | None:
    """Thử nối thẳng tới đích bằng Reeds–Shepp.

    Đoạn nối phải qua ĐÚNG phép kiểm tra dùng ở khâu xác nhận cuối (vùng quét thật
    giữa hai mẫu), không chỉ phép kiểm tra từng tư thế rời. Trước đây hai phép này
    khác nhau: bộ lập đường "nối được", thoát vòng lặp, khâu xác nhận bác bỏ, rồi hàm
    trả về NO_PATH TRONG KHI HÀNG ĐỢI CÒN NGUYÊN hàng nghìn nút chưa xét. Nay một
    đoạn nối hỏng chỉ làm hàm này trả None và tìm kiếm chạy tiếp.
    """
    paths = candidate_paths(node_pose, goal, maxc)
    if not paths:
        return None
    paths.sort(key=lambda p: p.length + p.n_cusps * params.switch_cost * maxc)
    for path in paths[:params.rs_max_candidates]:
        checkpoint()
        samples = sample_path(node_pose, path, maxc, params.rs_sample_step)
        if not all(checker.pose_ok(p.x, p.y, p.yaw) for p, _, _ in samples):
            continue
        if all(check_motion(cfg, a, b, obstacles, bounds).ok
               for (a, _, _), (b, _, _) in zip(samples, samples[1:])):
            return [(p, d, _steer_for(m, max_steer)) for p, d, m in samples[1:]]
    return None


def _reconstruct(nodes: list[_Node], nid: int, cfg: VehicleConfig, params: PlannerParams) -> list[tuple[Pose, int, float]]:
    chain: list[_Node] = []
    while nid >= 0:
        chain.append(nodes[nid])
        nid = nodes[nid].parent
    chain.reverse()
    first_dir = chain[1].direction if len(chain) > 1 else 1
    first_steer = chain[1].steer if len(chain) > 1 else 0.0
    out: list[tuple[Pose, int, float]] = [(Pose(chain[0].x, chain[0].y, chain[0].yaw), first_dir, first_steer)]
    n_sub = max(1, int(math.ceil(params.step_length / params.path_sample_step)))
    for prev, node in zip(chain, chain[1:]):
        base = Pose(prev.x, prev.y, prev.yaw)
        for k in range(1, n_sub + 1):
            pose = integrate_bicycle(base, node.direction * params.step_length * k / n_sub, node.steer, 1.0, cfg.wheelbase)
            out.append((pose, node.direction, node.steer))
    return out
