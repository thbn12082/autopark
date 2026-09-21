"""Ứng viên đối chứng: Hybrid A* gộp cả bốn cách sửa đã chẩn đoán được, cộng thao tác gộp.

Bốn nguyên nhân đã ĐO ĐƯỢC của bản gốc và cách xử lý ở đây:

1. Không gian trạng thái bị vét cạn vì lưới quá thô so với bước thao tác
   (ca parallel_135: mở hết 11.970 nút rồi hàng đợi rỗng, trong khi còn 13 giây).
   → lưới 2,5 cm × 5°, bước mở rộng 5 cm, 7 mức góc lái.
2. Thông lượng 1.267 nút/giây vì kiểm tra va chạm dựng đa giác Shapely.
   → `FastCollisionChecker` giải tích, đo được 902.000 tư thế/giây.
3. Reeds–Shepp thiếu 32/48 từ đường, đúng các họ nối được trong chỗ chật.
   → `reeds_shepp_full`, phủ 100% cặp tư thế thay vì 98,5%.
4. Heuristic Reeds–Shepp tính lại từ đầu cho từng nút.
   → ghi nhớ theo tư thế tương đối đã làm tròn, dùng cho mọi nút.

Thêm thứ mà lưới không có: **thao tác gộp**. Một hành động mở rộng có thể là trọn
một nhịp đẩy tới-lui thay vì một cung 5 cm. Nhịp xoay giải bài quay đầu trong hành
lang hẹp; nhịp dịch ngang giải bài đỗ song song. Đây chính là thứ mà lưới không
biểu diễn nổi khi mỗi vòng đẩy chỉ dịch được vài xăng-ti-mét.

Ghi chú hiệu năng: vòng trong dùng bộ ba số (x, y, yaw) chứ không tạo đối tượng
`Pose`, và không gọi `wrap_angle` (góc để trôi tự do, chỉ quy về khoảng chuẩn khi
tra ô lưới). Đo cho thấy `integrate_bicycle` và việc tạo đối tượng từng là chi phí
lớn nhất sau khi đã thay bộ va chạm.
"""
from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field

from autopark.domain.computation import checkpoint
from autopark.planning.computation import controlled_plan
from autopark.domain.types import Bounds, Obstacle, Pose, VehicleConfig
from autopark.geometry.fast_collision import FastCollisionChecker
from autopark.geometry.footprint import check_motion, check_pose
from autopark.planning.hybrid_astar import HolonomicHeuristic, PlanResult
from autopark.planning.reeds_shepp_full import candidate_paths, sample_path
from autopark.planning.trajectory import build_trajectory

TWO_PI = 2.0 * math.pi


def _wrap(a: float) -> float:
    """Quy góc về (-pi, pi] bằng fmod; rẻ hơn atan2(sin, cos) khoảng ba lần."""
    v = math.fmod(a, TWO_PI)
    if v > math.pi:
        v -= TWO_PI
    elif v <= -math.pi:
        v += TWO_PI
    return v


def _arc(x: float, y: float, yaw: float, dist: float, k: float, r: float) -> tuple[float, float, float]:
    """Tiến `dist` (mang dấu) trên cung có độ cong k = tan(góc lái)/chiều dài cơ sở."""
    if k == 0.0:
        return x + dist * math.cos(yaw), y + dist * math.sin(yaw), yaw
    yn = yaw + dist * k
    return (x + r * (math.sin(yn) - math.sin(yaw)),
            y - r * (math.cos(yn) - math.cos(yaw)),
            yn)


@dataclass
class RefParams:
    xy_resolution: float = 0.025
    yaw_resolution: float = math.radians(5.0)
    step_length: float = 0.05
    n_steer: int = 9
    steer_ratio: float = 0.92
    # Đây là mâu thuẫn trung tâm của bài toán, đã ĐO ĐƯỢC:
    #  - cắt góc lái nhiều (0,85) thì bộ bám đường có dư địa sửa sai, sai số hướng cuối ~3°,
    #    nhưng ô đỗ chật trở thành VÔ NGHIỆM (duyệt rộng không chạm tới đích);
    #  - dùng hết góc lái (1,00) thì ô chật có nghiệm, nhưng bộ bám chỉ sửa được một phía
    #    nên sai số hướng cuối vọt lên 5–13°, vượt dung sai 5°.
    # 0,92 là điểm cân bằng đo được; khi cần hơn thì leo thang qua `portfolio.py`.
    reverse_cost: float = 1.15
    switch_cost: float = 0.35
    steer_cost: float = 0.10
    steer_change_cost: float = 0.15
    heuristic_weight: float = 2.6      # ĐO ĐƯỢC: 1,15 -> 2,6 rút uturn_w55 từ 3,04 s còn 0,18 s
    safety_margin: float = 0.03
    margin_floor: float = 0.004        # đủ bù sai số xấp xỉ vùng quét (~1 mm ở bước 5 cm)
    margin_clearance_share: float = 0.40
    goal_xy_tol: float = 0.025
    goal_yaw_tol: float = math.radians(2.5)
    rs_radius: float = 2.0             # chỉ thử nối Reeds–Shepp khi heuristic dưới mức này
    rs_every: int = 6
    rs_near: float = 0.35              # dưới khoảng này thì thử mỗi lần
    rs_max_candidates: int = 3
    rs_sample_step: float = 0.035
    path_sample_step: float = 0.02
    heuristic_cell: float = 0.02
    heuristic_yaw_cell: float = math.radians(4.0)
    use_macros: bool = True
    macro_arcs: tuple[float, ...] = (0.07, 0.12)
    max_macros: int = 12               # hệ số phân nhánh: càng nhiều nhịp càng chậm mỗi nút
    macro_arc_steps: int = 4
    max_nodes: int = 600_000
    time_limit: float = 8.0
    cruise_speed: float = 0.15
    approach_speed: float = 0.08
    approach_distance: float = 0.30


# --------------------------------------------------------------------- thao tác gộp

@dataclass(frozen=True)
class Macro:
    """Một nhịp thao tác gồm nhiều cung liên tiếp: [(chiều ±1, góc lái, độ dài cung)].

    `net` là tác dụng thực trong hệ xe (tiến, lệch ngang, đổi hướng), dùng để tính
    ngay điểm cuối mà không phải tích phân lại — nhờ đó loại nhanh nhịp không dùng được.
    `steps` là chuỗi (độ cong, bán kính, quãng đường) đã băm nhỏ để quét va chạm.
    """

    name: str
    segments: tuple[tuple[int, float, float], ...]
    net: tuple[float, float, float] = (0.0, 0.0, 0.0)
    steps: tuple[tuple[float, float, float], ...] = ()
    cost: float = 0.0

    @property
    def lateral(self) -> float:
        return self.net[1]

    @property
    def turn(self) -> float:
        return self.net[2]


def _curvature(steer: float, wheelbase: float) -> tuple[float, float]:
    k = math.tan(steer) / wheelbase
    return (0.0, 0.0) if abs(k) < 1e-9 else (k, 1.0 / k)


def _macro_cost(segments, p: RefParams) -> float:
    cost = 0.0
    prev_dir = None
    for direction, steer, arc in segments:
        cost += arc * (p.reverse_cost if direction < 0 else 1.0)
        cost += p.steer_cost * abs(steer) * arc
        if prev_dir is not None and direction != prev_dir:
            cost += p.switch_cost
        prev_dir = direction
    return cost


def _finish_macro(name: str, segments, cfg: VehicleConfig, p: RefParams) -> Macro:
    x = y = yaw = 0.0
    steps = []
    for direction, steer, arc in segments:
        k, r = _curvature(steer, cfg.wheelbase)
        d = direction * arc / p.macro_arc_steps
        for _ in range(p.macro_arc_steps):
            steps.append((k, r, d))
            x, y, yaw = _arc(x, y, yaw, d, k, r)
    return Macro(name, tuple(segments), (x, y, _wrap(yaw)), tuple(steps), _macro_cost(segments, p))


def _sequences(options, n):
    if n == 1:
        for o in options:
            yield [o]
        return
    for head in options:
        for tail in _sequences(options, n - 1):
            yield [head] + tail


def build_macros(cfg: VehicleConfig, p: RefParams) -> list[Macro]:
    """Sinh nhịp gộp bằng cách LIỆT KÊ mọi tổ hợp rồi chọn theo tác dụng đo được.

    Suy công thức bằng tay dễ sai: chuỗi "tiến lái trái rồi lùi lái trái" quay về
    đúng chỗ cũ, vì đi tới rồi đi lui trên cùng một đường tròn. Nên ở đây máy liệt
    kê mọi chuỗi 2–4 cung với góc lái thuộc {−δ, 0, +δ} và chiều thuộc {tiến, lùi},
    tích phân ra tác dụng thật, rồi chia hai nhóm:

    - nhóm XOAY: đổi hướng đáng kể mà gần như đứng yên → quay đầu nhiều nhịp;
    - nhóm DỊCH NGANG: đổi hướng gần bằng 0 nhưng lệch ngang đáng kể → đỗ song song.

    Trong mỗi ô phân loại chỉ giữ chuỗi rẻ nhất, vì mỗi nhịp làm tăng hệ số phân
    nhánh của tìm kiếm. Nhịp phải có ít nhất một lần đổi chiều, và không được chứa
    hai cung liền nhau triệt tiêu nhau.
    """
    if not p.use_macros:
        return []
    max_steer = cfg.max_steer * p.steer_ratio
    min_shift = p.xy_resolution * 1.4
    min_turn = p.yaw_resolution * 1.4
    flat = math.radians(1.5)
    buckets: dict[tuple, tuple[float, Macro]] = {}
    steers = (-max_steer, 0.0, max_steer)

    for arc in p.macro_arcs:
        options = [(d, s, arc) for d in (1, -1) for s in steers]
        for n_seg in (2, 3, 4):
            for combo in _sequences(options, n_seg):
                checkpoint()
                dirs = [c[0] for c in combo]
                if all(a == b for a, b in zip(dirs, dirs[1:])):
                    continue                        # không đổi chiều: chỉ là một cung dài
                if any(a[0] == b[0] and a[1] == b[1] for a, b in zip(combo, combo[1:])):
                    continue                        # hai cung liền giống hệt: gộp được
                if any(a[0] == -b[0] and a[1] == b[1] for a, b in zip(combo, combo[1:])):
                    continue                        # tới rồi lui trên cùng cung: triệt tiêu
                segs = tuple(combo)
                m = _finish_macro("", segs, cfg, p)
                fwd, lat, turn = m.net
                if abs(turn) >= min_turn:
                    bucket = ("xoay", 1 if turn > 0 else -1,
                              int(round(abs(turn) / math.radians(12.0))),
                              int(round(math.hypot(fwd, lat) / 0.06)))
                elif abs(lat) >= min_shift and abs(turn) < flat:
                    bucket = ("ngang", 1 if lat > 0 else -1,
                              int(round(abs(lat) / 0.025)), int(round(fwd / 0.06)))
                else:
                    continue
                prev = buckets.get(bucket)
                if prev is None or m.cost < prev[0]:
                    name = f"{bucket[0]}{len(segs)}_{int(arc * 100)}_{bucket[1]}{bucket[2]}"
                    buckets[bucket] = (m.cost, _finish_macro(name, segs, cfg, p))

    ordered = [m for _, m in sorted(buckets.values(), key=lambda kv: kv[0])]
    return ordered[:p.max_macros]


# --------------------------------------------------------------------- heuristic

class RSHeuristic:
    """Độ dài Reeds–Shepp không vật cản, ghi nhớ theo tư thế tương đối đã làm tròn.

    Reeds–Shepp chỉ phụ thuộc tư thế tương đối nên bảng ghi nhớ dùng lại rất nhiều
    lần. Làm tròn khiến giá trị lệch, nên trừ đi bán kính ô để không ước lượng vượt.
    """

    __slots__ = ("gx", "gy", "gc", "gs", "maxc", "cell", "yaw_cell", "cache", "slack", "hits", "misses")

    def __init__(self, goal: Pose, maxc: float, p: RefParams):
        self.gx, self.gy = goal.x, goal.y
        self.gc, self.gs = math.cos(goal.yaw), math.sin(goal.yaw)
        self.maxc = maxc
        self.cell = p.heuristic_cell
        self.yaw_cell = p.heuristic_yaw_cell
        self.cache: dict[tuple[int, int, int], float] = {}
        self.slack = math.hypot(p.heuristic_cell, p.heuristic_cell)
        self.hits = self.misses = 0

    def __call__(self, x: float, y: float, yaw: float) -> float:
        dx, dy = x - self.gx, y - self.gy
        rx = self.gc * dx + self.gs * dy
        ry = -self.gs * dx + self.gc * dy
        ryaw = _wrap(yaw - math.atan2(self.gs, self.gc))
        key = (int(round(rx / self.cell)), int(round(ry / self.cell)),
               int(round(ryaw / self.yaw_cell)))
        val = self.cache.get(key)
        if val is not None:
            self.hits += 1
            return val
        self.misses += 1
        q0 = Pose(key[0] * self.cell, key[1] * self.cell, key[2] * self.yaw_cell)
        paths = candidate_paths(q0, Pose(0.0, 0.0, 0.0), self.maxc)
        val = max(0.0, paths[0].length / self.maxc - self.slack) if paths else 0.0
        self.cache[key] = val
        return val


# --------------------------------------------------------------------- tìm kiếm

@controlled_plan(8.0)
def plan(start: Pose, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle],
         bounds: Bounds, params=None, time_limit: float | None = None,
         stats: dict | None = None) -> PlanResult:
    """Truyền một dict vào `stats` để nhận số liệu chẩn đoán của lần tìm kiếm."""
    p = params if isinstance(params, RefParams) else RefParams()
    if params is not None and not isinstance(params, RefParams) and getattr(params, "time_limit", None):
        p.time_limit = params.time_limit
    if time_limit is not None:
        p.time_limit = time_limit
    t0 = time.perf_counter()

    goal_chk = check_pose(cfg, goal, obstacles, bounds)
    if not goal_chk.ok:
        return PlanResult("GOAL_INVALID", "Đích không hợp lệ: " + goal_chk.describe())
    start_chk = check_pose(cfg, start, obstacles, bounds)
    if not start_chk.ok:
        return PlanResult("START_INVALID", "Xuất phát không hợp lệ: " + start_chk.describe())
    # Lề an toàn không được ăn hết khoảng hở tại đích, nếu không xe nằm trong ô sẽ
    # không nhúc nhích được và bài toán thành vô nghiệm. Đo được: lề 1 cm với khoảng
    # hở 2 cm làm ca parallel_135 mất nghiệm hoàn toàn.
    margin = min(p.safety_margin,
                 goal_chk.min_clearance * p.margin_clearance_share,
                 start_chk.min_clearance * p.margin_clearance_share)
    margin = min(max(margin, p.margin_floor), p.safety_margin)

    checker = FastCollisionChecker(cfg, obstacles, bounds, margin)
    pose_ok = checker.pose_ok
    max_steer = cfg.max_steer * p.steer_ratio
    maxc = math.tan(max_steer) / cfg.wheelbase
    inflate = min(cfg.width / 2, cfg.rear_overhang) + margin
    holonomic = HolonomicHeuristic(goal, bounds, obstacles, max(p.xy_resolution, 0.04), inflate)
    rs_h = RSHeuristic(goal, maxc, p)
    macros = build_macros(cfg, p)

    n = max(3, p.n_steer | 1)
    steer_set = [-max_steer + i * (2 * max_steer / (n - 1)) for i in range(n)]
    prims = []                                     # (chiều, góc lái, k, r, chi phí cơ bản)
    for direction in (1, -1):
        for steer in steer_set:
            k, r = _curvature(steer, cfg.wheelbase)
            base = p.step_length * (p.reverse_cost if direction < 0 else 1.0)
            base += p.steer_cost * abs(steer) * p.step_length
            prims.append((direction, steer, k, r, base))
    half = p.step_length / 2

    n_yaw = max(1, int(round(TWO_PI / p.yaw_resolution)))
    inv_xy = 1.0 / p.xy_resolution
    inv_yaw = 1.0 / p.yaw_resolution
    xmin, ymin = bounds.xmin, bounds.ymin
    goal_yaw = goal.yaw

    def key(x, y, yaw, direction):
        return (int((x - xmin) * inv_xy), int((y - ymin) * inv_xy),
                int(((yaw + math.pi) % TWO_PI) * inv_yaw) % n_yaw, direction)

    def heuristic(x, y, yaw):
        return p.heuristic_weight * max(holonomic(x, y), rs_h(x, y, yaw))

    # nút = (x, y, yaw, chiều, góc lái, g, cha, nước đi)
    nodes = [(start.x, start.y, start.yaw, 0, 0.0, 0.0, -1, None)]
    best = {key(start.x, start.y, start.yaw, 0): 0.0}
    closed = set()
    heap = [(heuristic(start.x, start.y, start.yaw), 0, 0)]
    counter = 1
    expanded = popped = rs_tries = pushed = pops_total = 0
    exit_reason = 'hang doi rong'
    raw_path = None
    status = "NO_PATH"
    message = "Không tìm được đường trong không gian tìm kiếm"

    while heap:
        checkpoint()
        _, _, nid = heapq.heappop(heap)
        nx, ny, nyaw, ndir, nsteer, ng, _parent, _move = nodes[nid]
        k0 = key(nx, ny, nyaw, ndir)
        pops_total += 1
        if k0 in closed:
            continue
        closed.add(k0)
        popped += 1
        if (popped & 255) == 0:
            elapsed = time.perf_counter() - t0
            if popped > p.max_nodes or elapsed > p.time_limit:
                status = "TIMEOUT"
                exit_reason = "het gio" if elapsed > p.time_limit else "cham tran so nut"
                message = f"Quá giới hạn tìm kiếm ({popped} nút, {elapsed:.1f} s)"
                break

        if (math.hypot(goal.x - nx, goal.y - ny) < p.goal_xy_tol
                and abs(_wrap(nyaw - goal_yaw)) < p.goal_yaw_tol):
            exit_reason = 'toi dich'
            raw_path = _reconstruct(nodes, nid, cfg, p, macros)
            break

        h_rs = rs_h(nx, ny, nyaw)
        if h_rs < p.rs_radius and ((popped % p.rs_every) == 0 or h_rs < p.rs_near):
            rs_tries += 1
            tail = _try_reeds_shepp(Pose(nx, ny, _wrap(nyaw)), goal, maxc, max_steer, pose_ok, p,
                                    cfg, obstacles, bounds)
            if tail is not None:
                exit_reason = 'noi Reeds-Shepp'
                raw_path = _reconstruct(nodes, nid, cfg, p, macros) + tail
                break

        # Cung ngắn thông thường
        for direction, steer, k, r, base in prims:
            mx, my, myaw = _arc(nx, ny, nyaw, direction * half, k, r)
            if not pose_ok(mx, my, myaw):
                continue
            ex, ey, eyaw = _arc(nx, ny, nyaw, direction * p.step_length, k, r)
            if not pose_ok(ex, ey, eyaw):
                continue
            cost = base + p.steer_change_cost * abs(steer - nsteer)
            if ndir != 0 and direction != ndir:
                cost += p.switch_cost
            g = ng + cost
            nk = key(ex, ey, eyaw, direction)
            if nk in closed or g >= best.get(nk, math.inf):
                continue
            best[nk] = g
            nodes.append((ex, ey, eyaw, direction, steer, g, nid, (0, direction, steer)))
            heapq.heappush(heap, (g + heuristic(ex, ey, eyaw), counter, len(nodes) - 1))
            counter += 1
            expanded += 1
            pushed += 1

        # Nhịp gộp: loại nhanh bằng điểm cuối trước, rồi mới quét dày
        if macros:
            cy = math.cos(nyaw)
            sy = math.sin(nyaw)
            for mi, macro in enumerate(macros):
                mfx, mfy, mturn = macro.net
                ex = nx + cy * mfx - sy * mfy
                ey = ny + sy * mfx + cy * mfy
                eyaw = nyaw + mturn
                if not pose_ok(ex, ey, eyaw):
                    continue
                last_dir = macro.segments[-1][0]
                nk = key(ex, ey, eyaw, last_dir)
                cost = macro.cost + (p.switch_cost if ndir != 0 and macro.segments[0][0] != ndir else 0.0)
                g = ng + cost
                if nk in closed or g >= best.get(nk, math.inf):
                    continue
                cx, cyy, cyaw2 = nx, ny, nyaw
                blocked = False
                for kk, rr, dd in macro.steps:
                    cx, cyy, cyaw2 = _arc(cx, cyy, cyaw2, dd, kk, rr)
                    if not pose_ok(cx, cyy, cyaw2):
                        blocked = True
                        break
                if blocked:
                    continue
                best[nk] = g
                nodes.append((ex, ey, eyaw, last_dir, macro.segments[-1][1], g, nid, (1, mi, 0.0)))
                heapq.heappush(heap, (g + heuristic(ex, ey, eyaw), counter, len(nodes) - 1))
                counter += 1
                expanded += 1
                pushed += 1

    elapsed = time.perf_counter() - t0
    if stats is not None:
        stats.update(popped=popped, pops_total=pops_total, pushed=pushed, heap_left=len(heap),
                     closed=len(closed), best_size=len(best), nodes=len(nodes),
                     exit_reason=exit_reason, rs_tries=rs_tries, macros=len(macros),
                     rs_cache=(rs_h.hits, rs_h.misses), margin=margin)
    if raw_path is None:
        return PlanResult(status, message, None, elapsed, expanded, popped, rs_tries, margin)

    for (pa, _, _), (pb, _, _) in zip(raw_path, raw_path[1:]):
        checkpoint()
        col = check_motion(cfg, pa, pb, obstacles, bounds)
        if not col.ok:
            return PlanResult("NO_PATH", "Đường tìm được vi phạm kiểm tra vùng quét: " + col.describe(),
                              None, elapsed, expanded, popped, rs_tries, margin)

    traj = build_trajectory(raw_path, goal, cfg, p.cruise_speed, p.approach_speed, p.approach_distance)
    msg = (f"Tìm được đường dài {traj.length:.2f} m, {traj.n_cusps} lần đổi chiều "
           f"({popped} nút, bộ nhớ heuristic {rs_h.hits}/{rs_h.hits + rs_h.misses})")
    return PlanResult("OK", msg, traj, elapsed, expanded, popped, rs_tries, margin)


def _try_reeds_shepp(node_pose: Pose, goal: Pose, maxc: float, max_steer: float,
                     pose_ok, p: RefParams, cfg: VehicleConfig,
                     obstacles: list[Obstacle], bounds: Bounds):
    """Thử nối thẳng tới đích bằng Reeds–Shepp.

    Quan trọng: đoạn nối phải qua ĐÚNG phép kiểm tra dùng ở khâu xác nhận cuối
    (vùng quét thật giữa hai mẫu), chứ không chỉ qua phép kiểm tra từng tư thế rời.
    Trước đây hai phép này khác nhau, nên bộ lập đường "tìm được" một đoạn nối rồi
    bị khâu xác nhận bác bỏ, và trả về NO_PATH dù không gian tìm kiếm còn nguyên.
    Nay đoạn nối hỏng chỉ làm hàm này trả None và tìm kiếm chạy tiếp.
    """
    paths = candidate_paths(node_pose, goal, maxc)
    if not paths:
        return None
    paths.sort(key=lambda q: q.length + q.n_cusps * p.switch_cost * maxc)
    for path in paths[:p.rs_max_candidates]:
        checkpoint()
        samples = sample_path(node_pose, path, maxc, p.rs_sample_step)
        if not all(pose_ok(q.x, q.y, q.yaw) for q, _, _ in samples):
            continue
        exact_ok = True
        for (a, _, _), (b, _, _) in zip(samples, samples[1:]):
            if not check_motion(cfg, a, b, obstacles, bounds).ok:
                exact_ok = False
                break
        if exact_ok:
            return [(q, d, _steer_for(m, max_steer)) for q, d, m in samples[1:]]
    return None


def _steer_for(mode: str, max_steer: float) -> float:
    return max_steer if mode == "L" else -max_steer if mode == "R" else 0.0


def _reconstruct(nodes, nid: int, cfg: VehicleConfig, p: RefParams, macros: list[Macro]):
    chain = []
    while nid >= 0:
        chain.append(nodes[nid])
        nid = nodes[nid][6]
    chain.reverse()
    first = chain[1] if len(chain) > 1 else chain[0]
    out = [(Pose(chain[0][0], chain[0][1], _wrap(chain[0][2])), first[3] or 1, first[4])]
    for prev, node in zip(chain, chain[1:]):
        move = node[7]
        x, y, yaw = prev[0], prev[1], prev[2]
        if move is not None and move[0] == 1:
            macro = macros[move[1]]
            for direction, steer, arc in macro.segments:
                k, r = _curvature(steer, cfg.wheelbase)
                sub = max(1, int(math.ceil(arc / p.path_sample_step)))
                d = direction * arc / sub
                for _ in range(sub):
                    x, y, yaw = _arc(x, y, yaw, d, k, r)
                    out.append((Pose(x, y, _wrap(yaw)), direction, steer))
        else:
            direction, steer = node[3], node[4]
            k, r = _curvature(steer, cfg.wheelbase)
            sub = max(1, int(math.ceil(p.step_length / p.path_sample_step)))
            d = direction * p.step_length / sub
            for _ in range(sub):
                x, y, yaw = _arc(x, y, yaw, d, k, r)
                out.append((Pose(x, y, _wrap(yaw)), direction, steer))
    return out
