"""Ứng viên "Hybrid A* hai chiều": tìm đồng thời từ xuất phát và từ đích.

Ý tưởng
-------
Đích của bài đỗ xe nằm trong túi chật. Tìm một chiều từ ngoài vào phải mò đúng
nhịp đẩy tới/lui mới chui lọt cửa túi; tìm ngược từ đích lập tức dựng ra "xương
sống" của thao tác vì bước đầu tiên của nhánh ngược CHÍNH LÀ bước cuối cùng của
đường đi. Hai cây gặp nhau ở chỗ rộng giữa đường, nơi một đoạn Reeds–Shepp ngắn
nối được. Độ sâu mỗi nhánh giảm còn một nửa, mà số nút của tìm kiếm mù tăng theo
hàm mũ của độ sâu.

Ba thay đổi so với `hybrid_astar.py` (theo chẩn đoán đã đo)
1. Hai cây thay vì một, nối bằng Reeds–Shepp có kiểm tra va chạm.
2. `FastCollisionChecker` giải tích thay Shapely trong vòng trong; các bước mở
   rộng được tính bằng độ dời CỤC BỘ dựng sẵn (mỗi nút chỉ cần một cặp sin/cos).
3. Reeds–Shepp đầy đủ 48 họ (`cand_bidirectional_rs`) thay bản 16 họ, và
   heuristic RS được ghi nhớ theo tư thế tương đối đã làm tròn.

Mở rộng ngược
-------------
Nút b của cây ngược sinh ra từ cha p bằng `integrate_bicycle(p, d·L, steer)`.
Vì cung tròn có nghịch đảo là chính nó với quãng đường đổi dấu, đi THẬT từ b về p
là `integrate_bicycle(b, -d·L, steer)`: cùng góc lái, chiều lật dấu. Khi ghép
đường, mỗi cạnh của nhánh ngược được ghi lại với chiều `-d` và góc lái `steer`.

Ghi chú về độ chặt: lề an toàn dùng đúng công thức của `hybrid_astar.py`
(`min(0.03, hở_đích/2, hở_xuất_phát/2)`), dung sai đích 3 cm / 3° đúng như bản
gốc, và mọi đoạn kết quả vẫn được `footprint.check_motion` (thân xe THẬT) duyệt
lại trước khi trả về.
"""
from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass

from autopark.domain.types import Bounds, Obstacle, Pose, VehicleConfig, wrap_angle
from autopark.geometry.fast_collision import FastCollisionChecker
from autopark.geometry.footprint import check_motion, check_pose
from autopark.planning.cand_bidirectional_rs import (
    min_normalized_length,
    normalized_goal,
    raw_candidates,
    sample_path,
)
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.trajectory import build_trajectory
from autopark.simulation.vehicle import integrate_bicycle

_cos = math.cos
_sin = math.sin
_tan = math.tan
_hypot = math.hypot
_PI = math.pi
_TWO_PI = 2.0 * math.pi


@dataclass
class BiParams:
    """Tham số của ứng viên. `time_limit` là thứ duy nhất bench áp đặt."""

    xy_resolution: float = 0.030
    yaw_resolution: float = math.radians(7.5)
    step_length: float = 0.065
    # Thang co buoc: moi cap (chieu, goc lai) lay BUOC TU DO DAI NHAT con di duoc.
    # Trong khe ket, nhich sat vao vach moi vet duoc cung dai nhat, tuc xoay duoc
    # nhieu nhat moi nhip - do la dieu kien de nhip day toi/lui thoat khoi o luoi.
    step_scales: tuple = (1.0, 0.72, 0.52, 0.37, 0.27, 0.19, 0.14, 0.10)
    n_steer: int = 5
    steer_ratio: float = 0.85
    reverse_cost: float = 1.10
    switch_cost: float = 0.22
    steer_cost: float = 0.10
    steer_change_cost: float = 0.30    # phạt đổi góc lái giữa đoạn (bộ bám chỉ đổi lái 90°/s)
    heuristic_weight: float = 1.5
    safety_margin: float = 0.03
    goal_xy_tol: float = 0.03
    goal_yaw_tol: float = math.radians(3.0)
    rs_radius: float = 1.0             # bán kính dùng heuristic RS
    root_rs_every: int = 4             # thử nối thẳng tới gốc cây kia mỗi N nút
    meet_every: int = 1                # thử gặp nhau mỗi N nút lấy ra
    meet_max_tries: int = 2            # số ứng viên nút đối diện thử mỗi lần
    # Lưới GẶP NHAU tách hẳn khỏi lưới tìm kiếm: khi lưới tìm kiếm mịn tới
    # 6 mm thì xác suất hai cây rơi đúng một ô là gần bằng không, dù chúng đã
    # phủ lên nhau. Ô gặp nhau giữ nguyên cỡ vật lý.
    meet_xy_cell: float = 0.035        # m
    meet_yaw_cell: float = math.radians(9.0)
    meet_bucket: int = 2               # số nút giữ lại mỗi ô gặp nhau
    rs_max_candidates: int = 4
    rs_connect_max_len: float = 2.2    # m: bỏ ứng viên RS quá dài khi nối hai cây
    rs_sample_step: float = 0.022
    # Đoạn cùng chiều NGẮN NHẤT mà bộ bám đường còn chạy được. `tracker.py` dừng
    # đoạn khi quãng còn lại <= stop_distance = 1 cm, nên đoạn 1 cm là đoạn xe
    # KHÔNG hề nhúc nhích; đo trên `pocket_exit_park` cho thấy một đuôi đường gồm
    # 11 nhịp 0,8-1,6 cm làm xe lệch hướng 19,7° so với quỹ đạo. Bộ lập đường
    # phải tự cấm loại đường đó, chứ không phải đẩy sang cho bộ bám.
    min_leg: float = 0.030             # m
    min_leg_edge: float = 0.012        # m: đoạn đầu và đoạn cuối được ngắn hơn
    path_sample_step: float = 0.018
    heur_resolution: float = 0.05      # lưới Dijkstra 2D
    max_nodes: int = 600_000
    time_limit: float = 8.0
    # Tốc độ hành trình 8 cm/s chứ không phải 15: bộ bám đường chỉ đổi lái được
    # 90°/s, nên ở chỗ đổi độ cong đột ngột (biên đoạn Reeds–Shepp) xe càng chạy
    # nhanh càng trôi. Đo trên `perp_aisle_115`: 15 cm/s va chạm, 8 cm/s bám sạch.
    cruise_speed: float = 0.08
    approach_speed: float = 0.05
    approach_distance: float = 0.30


# --------------------------------------------------------------- heuristic 2D

def _build_blocked(bounds: Bounds, obstacles: list[Obstacle], res: float, inflate: float):
    nx = max(1, int(math.ceil(bounds.width / res)))
    ny = max(1, int(math.ceil(bounds.height / res)))
    blocked = bytearray(nx * ny)
    x0, y0 = bounds.xmin, bounds.ymin
    lo_x, hi_x = bounds.xmin + inflate, bounds.xmax - inflate
    lo_y, hi_y = bounds.ymin + inflate, bounds.ymax - inflate
    for i in range(nx):
        cx = x0 + (i + 0.5) * res
        out_x = not (lo_x <= cx <= hi_x)
        base = i * ny
        for j in range(ny):
            if out_x or not (lo_y <= y0 + (j + 0.5) * res <= hi_y):
                blocked[base + j] = 1
    for o in obstacles:
        c, s = _cos(o.yaw), _sin(o.yaw)
        hx, hy = o.width / 2.0 + inflate, o.height / 2.0 + inflate
        r = _hypot(o.width / 2.0, o.height / 2.0) + inflate + res
        i0 = max(0, int((o.cx - r - x0) / res))
        i1 = min(nx - 1, int((o.cx + r - x0) / res))
        j0 = max(0, int((o.cy - r - y0) / res))
        j1 = min(ny - 1, int((o.cy + r - y0) / res))
        for i in range(i0, i1 + 1):
            dx0 = x0 + (i + 0.5) * res - o.cx
            base = i * ny
            for j in range(j0, j1 + 1):
                dy0 = y0 + (j + 0.5) * res - o.cy
                u = dx0 * c + dy0 * s
                if -hx <= u <= hx:
                    v = -dx0 * s + dy0 * c
                    if -hy <= v <= hy:
                        blocked[base + j] = 1
    return blocked, nx, ny


def _dijkstra(blocked: bytearray, nx: int, ny: int, res: float, si: int, sj: int) -> list[float]:
    inf = math.inf
    dist = [inf] * (nx * ny)
    k0 = si * ny + sj
    dist[k0] = 0.0
    heap = [(0.0, k0)]
    push, pop = heapq.heappush, heapq.heappop
    diag = res * math.sqrt(2.0)
    while heap:
        d, k = pop(heap)
        if d > dist[k]:
            continue
        i, j = divmod(k, ny)
        for di in (-1, 0, 1):
            ni = i + di
            if ni < 0 or ni >= nx:
                continue
            nb = ni * ny
            for dj in (-1, 0, 1):
                if di == 0 and dj == 0:
                    continue
                nj = j + dj
                if nj < 0 or nj >= ny:
                    continue
                nk = nb + nj
                step = diag if (di and dj) else res
                if blocked[nk]:
                    step *= 4.0        # đi được nhưng đắt: giữ heuristic hữu hạn ở ô hẹp
                nd = d + step
                if nd < dist[nk]:
                    dist[nk] = nd
                    push(heap, (nd, nk))
    return dist


class _Field:
    """Bảng khoảng cách 2D có vật cản tới một điểm mốc."""

    __slots__ = ("dist", "nx", "ny", "res", "x0", "y0", "tx", "ty")

    def __init__(self, blocked, nx, ny, res, x0, y0, tx, ty):
        self.nx, self.ny, self.res, self.x0, self.y0 = nx, ny, res, x0, y0
        self.tx, self.ty = tx, ty
        si = min(max(int((tx - x0) / res), 0), nx - 1)
        sj = min(max(int((ty - y0) / res), 0), ny - 1)
        self.dist = _dijkstra(blocked, nx, ny, res, si, sj)

    def at(self, x: float, y: float) -> float:
        i = int((x - self.x0) / self.res)
        j = int((y - self.y0) / self.res)
        if 0 <= i < self.nx and 0 <= j < self.ny:
            d = self.dist[i * self.ny + j]
            if d < math.inf:
                return d
        return _hypot(self.tx - x, self.ty - y)


# ------------------------------------------------------------------ hai cây

def _rs_walk(x0: float, y0: float, yaw0: float, path, maxc: float, step: float, pose_ok):
    """Đi dọc đường RS, kiểm tra va chạm TẠI CHỖ, thoát ngay khi chạm.

    Không cấp phát `Pose` nào: đo trên hồ sơ cho thấy việc dựng mẫu chiếm 82%
    thời gian khi hầu hết ứng viên bị loại ở vài mẫu đầu. Trả về tư thế cuối
    (x, y, yaw) nếu sạch, None nếu chạm.
    """
    ox, oy, oyaw = x0, y0, yaw0
    inv = 1.0 / maxc
    smc = step * maxc
    for l, m in zip(path.lengths, path.ctypes):
        al = l if l >= 0.0 else -l
        if al < 1e-12:
            continue
        n = int(al / smc) + 1
        c, s = _cos(oyaw), _sin(oyaw)
        if m == "S":
            dl = l * inv / n
            dx, dy = c * dl, s * dl
            for k in range(1, n + 1):
                if not pose_ok(ox + dx * k, oy + dy * k, oyaw):
                    return None
            ox += dx * n
            oy += dy * n
        else:
            sg = 1.0 if m == "L" else -1.0
            for k in range(1, n + 1):
                p = l * k / n
                ldx = _sin(p) * inv
                ldy = sg * (1.0 - _cos(p)) * inv
                if not pose_ok(ox + c * ldx - s * ldy, oy + s * ldx + c * ldy, oyaw + sg * p):
                    return None
            ldx = _sin(l) * inv
            ldy = sg * (1.0 - _cos(l)) * inv
            ox, oy, oyaw = ox + c * ldx - s * ldy, oy + s * ldx + c * ldy, oyaw + sg * l
    return ox, oy, oyaw


class _Tree:
    """Một nhánh tìm kiếm: kho nút, hàng đợi, tập đóng, bản đồ ô để gặp nhau."""

    __slots__ = ("nodes", "heap", "best", "closed", "cells", "counter",
                 "popped", "expanded", "root", "backward")

    def __init__(self, root_pose: Pose, backward: bool):
        # nút = (x, y, yaw, direction, steer, g, parent)
        # nut = (x, y, yaw, chieu, goc lai, g, cha, do dai buoc da di)
        # nút = (x, y, yaw, chiều, góc lái, g, cha, dài bước, dài đoạn đang chạy, cờ đoạn biên)
        self.nodes: list[tuple] = [(root_pose.x, root_pose.y, root_pose.yaw,
                                    0, 0.0, 0.0, -1, 0.0, 0.0, 1)]
        self.heap: list[tuple] = []
        self.best: dict = {}
        self.closed: set = set()
        self.cells: dict = {}
        self.counter = 0
        self.popped = 0
        self.expanded = 0
        self.root = root_pose
        self.backward = backward


def _plan_once(start: Pose, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle],
               bounds: Bounds, P: BiParams, margin: float, deadline: float):
    """Chạy một lượt tìm hai chiều. Trả về (raw_path | None, popped, expanded, lý do)."""
    checker = FastCollisionChecker(cfg, obstacles, bounds, margin)
    pose_ok = checker.pose_ok
    wb = cfg.wheelbase
    max_steer = cfg.max_steer * P.steer_ratio
    maxc = _tan(max_steer) / wb

    if not pose_ok(goal.x, goal.y, goal.yaw) or not pose_ok(start.x, start.y, start.yaw):
        return None, 0, 0, "lề an toàn không lọt tại đầu hoặc cuối"

    # --- trường khoảng cách 2D cho hai chiều
    inflate = min(cfg.width / 2.0, cfg.rear_overhang) + margin
    blocked, gnx, gny = _build_blocked(bounds, obstacles, P.heur_resolution, inflate)
    f_goal = _Field(blocked, gnx, gny, P.heur_resolution, bounds.xmin, bounds.ymin, goal.x, goal.y)
    f_start = _Field(blocked, gnx, gny, P.heur_resolution, bounds.xmin, bounds.ymin, start.x, start.y)

    # --- heuristic Reeds–Shepp có ghi nhớ
    rs_cache: dict = {}
    rs_radius2 = P.rs_radius * P.rs_radius

    def rs_len(x0, y0, yaw0, x1, y1, yaw1):
        dx, dy = x1 - x0, y1 - y0
        c, s = _cos(yaw0), _sin(yaw0)
        px = (c * dx + s * dy) * maxc
        py = (-s * dx + c * dy) * maxc
        phi = wrap_angle(yaw1 - yaw0)
        k = (int(px * 24.0), int(py * 24.0), int(phi * 12.0))
        v = rs_cache.get(k)
        if v is None:
            v = min_normalized_length(px, py, phi) / maxc
            rs_cache[k] = v
        return v

    gx, gy, gyaw = goal.x, goal.y, goal.yaw
    sx, sy, syaw = start.x, start.y, start.yaw
    w = P.heuristic_weight

    # --- các bước mở rộng dựng sẵn (độ dời trong hệ xe, không phụ thuộc tư thế)
    #
    # Mỗi cặp (chiều, góc lái) có NHIỀU cỡ bước, dùng theo kiểu lùi dần: cỡ dài
    # trước, chạm thì thử cỡ ngắn hơn. Lý do đo được: ở `pocket_exit_park` xe
    # nằm kẹt trong ô 39 cm với thân xe đã nới lề dài 34 cm, chỉ còn 2,5 cm hở
    # mỗi đầu, nên bước 6,5 cm làm cây NGƯỢC không sinh nổi một nút con nào.
    # Cách này giữ nguyên độ rẽ nhánh (một nút con cho mỗi cặp) mà vẫn nhích
    # được trong khe hẹp.
    n = max(3, P.n_steer | 1)
    steers = [-max_steer + i * (2.0 * max_steer / (n - 1)) for i in range(n)]
    L = P.step_length
    scales = P.step_scales
    prims = []
    for d in (1, -1):
        for st in steers:
            variants = []
            for sc in scales:
                ln = L * sc
                if abs(st) < 1e-9:
                    dxf, dyf, dth = d * ln, 0.0, 0.0
                    dxm, dym, dthm = d * ln / 2.0, 0.0, 0.0
                else:
                    k = _tan(st) / wb
                    R = 1.0 / k
                    dth = d * ln * k
                    dxf, dyf = R * _sin(dth), R * (1.0 - _cos(dth))
                    dthm = dth / 2.0
                    dxm, dym = R * _sin(dthm), R * (1.0 - _cos(dthm))
                base = ln * (P.reverse_cost if d < 0 else 1.0) + P.steer_cost * abs(st) * ln
                variants.append((dxf, dyf, dth, dxm, dym, dthm, base, ln))
            prims.append((d, st, tuple(variants)))

    res = P.xy_resolution
    yres = P.yaw_resolution
    n_yaw = max(1, int(round(_TWO_PI / yres)))
    bx, by = bounds.xmin, bounds.ymin
    switch_cost = P.switch_cost
    steer_change_cost = P.steer_change_cost
    min_leg = P.min_leg
    min_leg_edge = P.min_leg_edge

    mres = P.meet_xy_cell
    myres = P.meet_yaw_cell
    m_nyaw = max(1, int(round(_TWO_PI / myres)))
    meet_bucket = P.meet_bucket

    fwd = _Tree(start, False)
    bwd = _Tree(goal, True)
    fwd.heap.append((w * f_goal.at(sx, sy), 0, 0))
    bwd.heap.append((w * f_start.at(gx, gy), 0, 0))
    for tree in (fwd, bwd):
        r = tree.root
        tree.cells[(int((r.x - bx) / mres), int((r.y - by) / mres),
                    int(((r.yaw + _PI) % _TWO_PI) / myres) % m_nyaw)] = [0]
        tree.best[(int((r.x - bx) / res), int((r.y - by) / res),
                   int(((r.yaw + _PI) % _TWO_PI) / yres) % n_yaw, 0)] = 0.0

    push, pop = heapq.heappush, heapq.heappop
    goal_xy_tol = P.goal_xy_tol
    goal_yaw_tol = P.goal_yaw_tol
    meet_every = P.meet_every
    root_rs_every = P.root_rs_every
    max_nodes = P.max_nodes

    result_raw = None        # đường thô đã ghép và đã qua kiểm tra độ dài đoạn
    reason = "vét hết không gian tìm kiếm"
    turn = 0
    checked_pairs: set = set()

    rs_step = P.rs_sample_step
    rs_max_cand = P.rs_max_candidates
    rs_len_cap = P.rs_connect_max_len * maxc      # chuẩn hóa
    end_tol = 1e-6

    def try_rs(qa: Pose, qb: Pose, finish):
        """Duyệt các đường RS từ qa tới qb, trả về kết quả `finish` chấp nhận.

        Kiểm tra điểm cuối được GỘP vào lượt đi kiểm va chạm nên không phải tích
        phân hai lần: đường sai công thức lộ ra ở tư thế cuối. `finish` còn có thể
        loại đường vì đoạn quá ngắn, khi đó ta thử tiếp ứng viên RS sau chứ không
        bỏ luôn cặp nút này.
        """
        px, py, phi = normalized_goal(qa, qb, maxc)
        cands = raw_candidates(px, py, phi)
        if not cands:
            return None
        scored = []
        for p in cands:
            tot = 0.0
            prev = 0.0
            cusps = 0
            for v in p.lengths:
                if v >= 0.0:
                    tot += v
                    if prev < 0.0:
                        cusps += 1
                    if v > 1e-12:
                        prev = v
                else:
                    tot -= v
                    if prev > 0.0:
                        cusps += 1
                    prev = v
            if tot > rs_len_cap:
                continue
            scored.append((tot + cusps * switch_cost * maxc, p))
        if not scored:
            return None
        scored.sort(key=lambda kv: kv[0])
        ax, ay, ayaw = qa.x, qa.y, qa.yaw
        bx_, by_, byaw = qb.x, qb.y, qb.yaw
        for _score, path in scored[:rs_max_cand]:
            end = _rs_walk(ax, ay, ayaw, path, maxc, rs_step, pose_ok)
            if end is None:
                continue
            if (abs(end[0] - bx_) > end_tol or abs(end[1] - by_) > end_tol
                    or abs(wrap_angle(end[2] - byaw)) > end_tol):
                continue                      # công thức không khớp: bỏ ứng viên
            out = finish(path)
            if out is not None:
                return out
        return None

    def accept(nid_f: int, nid_b: int, path):
        """Ghép thử và chỉ nhận nếu mọi đoạn đủ dài để bộ bám đường chạy được."""
        raw = _assemble(fwd, nid_f, bwd, nid_b, path, maxc, max_steer, wb,
                        P.path_sample_step, P.rs_sample_step, goal)
        if not _legs_executable(raw, min_leg, min_leg_edge):
            return None
        return raw

    while True:
        turn ^= 1
        tree = fwd if turn else bwd
        other = bwd if turn else fwd
        if not tree.heap:
            if not other.heap:
                break
            tree, other = other, tree
        if time.perf_counter() > deadline:
            reason = "hết giờ"
            break
        if fwd.popped + bwd.popped > max_nodes:
            reason = "quá số nút cho phép"
            break

        f_pop, _, nid = pop(tree.heap)
        nodes = tree.nodes
        x, y, yaw, ndir, nsteer, g, _parent, _slen, nleg, nedge = nodes[nid]
        ix = int((x - bx) / res)
        iy = int((y - by) / res)
        iyaw = int(((yaw + _PI) % _TWO_PI) / yres) % n_yaw
        k = (ix, iy, iyaw, ndir)
        if k in tree.closed:
            continue

        backward = tree.backward
        root_other = other.root

        # ---- heuristic Reeds–Shepp tính LƯỜI: chỉ khi nút được lấy ra, không
        # phải khi sinh ra. Đo trên hồ sơ: giảm số lần gọi họ RS khoảng 10 lần.
        dxr, dyr = root_other.x - x, root_other.y - y
        d_root2 = dxr * dxr + dyr * dyr
        if d_root2 < rs_radius2:
            r = (rs_len(x, y, yaw, gx, gy, gyaw) if not backward
                 else rs_len(sx, sy, syaw, x, y, yaw))
            f_new = g + w * r
            if f_new > f_pop + 1e-12:
                tree.counter += 1
                push(tree.heap, (f_new, tree.counter, nid))
                continue

        tree.closed.add(k)
        tree.popped += 1
        pose = Pose(x, y, yaw)

        # ---- (a) nối thẳng tới gốc cây kia (chính là mở rộng giải tích cổ điển)
        d_root = math.sqrt(d_root2)
        if d_root < goal_xy_tol and abs(wrap_angle(yaw - root_other.yaw)) < goal_yaw_tol:
            cand = accept(nid, 0, None) if not backward else accept(0, nid, None)
            if cand is not None:
                result_raw = cand
                break
        if d_root < P.rs_radius and (tree.popped % root_rs_every == 0 or d_root < 0.35):
            if not backward:
                cand = try_rs(pose, root_other, lambda pth: accept(nid, 0, pth))
            else:
                cand = try_rs(root_other, pose, lambda pth: accept(0, nid, pth))
            if cand is not None:
                result_raw = cand
                break

        # ---- (b) gặp nhánh kia: tra ô lân cận trong bản đồ ô của cây đối diện
        if tree.popped % meet_every == 0 and other.cells:
            ocells = other.cells
            mi = int((x - bx) / mres)
            mj = int((y - by) / mres)
            mk = int(((yaw + _PI) % _TWO_PI) / myres) % m_nyaw
            cands = []
            for da in (0, -1, 1):
                for db in (0, -1, 1):
                    for dc in (0, -1, 1):
                        bucket = ocells.get((mi + da, mj + db, (mk + dc) % m_nyaw))
                        if bucket:
                            cands.extend(bucket)
            if cands:
                onodes = other.nodes
                if len(cands) > 1:
                    # xếp theo khoảng cách tư thế: lệch hướng quy đổi ra mét bằng
                    # bán kính quay, vì nối hai tư thế lệch hướng luôn tốn cung dài
                    cands.sort(key=lambda i: ((onodes[i][0] - x) ** 2 + (onodes[i][1] - y) ** 2
                                             + (wrap_angle(onodes[i][2] - yaw) / maxc) ** 2))
                tried = 0
                for oid in cands:
                    pair = (nid, oid) if not backward else (oid, nid)
                    if pair in checked_pairs:
                        continue
                    checked_pairs.add(pair)
                    ox_, oy_, oyaw_ = onodes[oid][0], onodes[oid][1], onodes[oid][2]
                    opose = Pose(ox_, oy_, oyaw_)
                    fin = (lambda pth, pf=pair[0], pb=pair[1]: accept(pf, pb, pth))
                    cand = (try_rs(pose, opose, fin) if not backward
                            else try_rs(opose, pose, fin))
                    if cand is not None:
                        result_raw = cand
                        break
                    tried += 1
                    if tried >= P.meet_max_tries:
                        break
                if result_raw is not None:
                    break

        # ---- (c) mở rộng
        c, s = _cos(yaw), _sin(yaw)
        best = tree.best
        closed = tree.closed
        cells = tree.cells
        heap = tree.heap
        field_at = f_goal.at if not backward else f_start.at
        for d, st, variants in prims:
            switching = ndir != 0 and d != ndir
            # Đoạn đầu tiên tính từ gốc cây được nới: với cây NGƯỢC nó chính là
            # đoạn CUỐI CÙNG của đường thật, mà đoạn cuối chỉ cần đủ để xe áp vào
            # đích chứ không phải để bẻ lái.
            if switching and nleg < (min_leg_edge if nedge else min_leg):
                continue          # đoạn quá ngắn, bộ bám đường sẽ bỏ qua
            nx_ = ny_ = nyaw = cbase = 0.0
            seglen = 0.0
            found = False
            for dxf, dyf, dth, dxm, dym, dthm, cb, ln in variants:
                mx = x + c * dxm - s * dym
                my = y + s * dxm + c * dym
                if not pose_ok(mx, my, yaw + dthm):
                    continue
                tx = x + c * dxf - s * dyf
                ty = y + s * dxf + c * dyf
                tyaw = yaw + dth
                if not pose_ok(tx, ty, tyaw):
                    continue
                nx_, ny_, nyaw, cbase, seglen = tx, ty, tyaw, cb, ln
                found = True
                break
            if not found:
                continue
            jx = int((nx_ - bx) / res)
            jy = int((ny_ - by) / res)
            jyaw = int(((nyaw + _PI) % _TWO_PI) / yres) % n_yaw
            nk = (jx, jy, jyaw, d)
            if nk in closed:
                continue
            cost = cbase + steer_change_cost * abs(st - nsteer)
            if switching:
                cost += switch_cost
            ng = g + cost
            if ng >= best.get(nk, math.inf):
                continue
            best[nk] = ng
            nodes.append((nx_, ny_, wrap_angle(nyaw), d, st, ng, nid, seglen,
                          seglen if switching or ndir == 0 else nleg + seglen,
                          1 if ndir == 0 else (0 if switching else nedge)))
            new_id = len(nodes) - 1
            ck = (int((nx_ - bx) / mres), int((ny_ - by) / mres),
                  int(((nyaw + _PI) % _TWO_PI) / myres) % m_nyaw)
            bucket = cells.get(ck)
            if bucket is None:
                cells[ck] = [new_id]
            elif len(bucket) < meet_bucket:
                bucket.append(new_id)
            tree.counter += 1
            push(heap, (ng + w * field_at(nx_, ny_), tree.counter, new_id))
            tree.expanded += 1

    popped = fwd.popped + bwd.popped
    expanded = fwd.expanded + bwd.expanded
    if result_raw is None:
        return None, popped, expanded, reason
    return result_raw, popped, expanded, "ghép được"


# ------------------------------------------------------------------ ghép đường

def _steer_for(mode: str, max_steer: float) -> float:
    return max_steer if mode == "L" else (-max_steer if mode == "R" else 0.0)


def _forward_chain(tree: _Tree, nid: int, wb: float, sub: float):
    """Từ gốc (xuất phát) tới nút nid, theo đúng chiều thời gian."""
    chain = []
    cur = nid
    nodes = tree.nodes
    while cur >= 0:
        chain.append(cur)
        cur = nodes[cur][6]
    chain.reverse()
    r = nodes[chain[0]]
    out = [(Pose(r[0], r[1], r[2]), 1, 0.0)]
    for a, b in zip(chain, chain[1:]):
        pa = nodes[a]
        nb = nodes[b]
        base = Pose(pa[0], pa[1], pa[2])
        d, st, L = nb[3], nb[4], nb[7]
        n_sub = max(1, int(math.ceil(L / sub)))
        for k in range(1, n_sub + 1):
            out.append((integrate_bicycle(base, d * L * k / n_sub, st, 1.0, wb), d, st))
    return out


def _backward_chain(tree: _Tree, nid: int, wb: float, sub: float, goal: Pose):
    """Từ nút nid của cây ngược tới gốc (đích), lật chiều cho đúng thời gian thật.

    Nút b sinh ra từ cha p bằng integrate(p, d·L, steer); nên đi thật từ b về p là
    integrate(b, -d·L, steer): chiều `-d`, GIỮ NGUYÊN góc lái.
    """
    out = []
    nodes = tree.nodes
    cur = nid
    while nodes[cur][6] >= 0:
        x, y, yaw, d, st, _g, parent, L, _leg, _edge = nodes[cur]
        e = -d
        base = Pose(x, y, yaw)
        n_sub = max(1, int(math.ceil(L / sub)))
        for k in range(1, n_sub + 1):
            out.append((integrate_bicycle(base, e * L * k / n_sub, st, 1.0, wb), e, st))
        cur = parent
    if out:
        last_pose, last_d, last_st = out[-1]
        out[-1] = (goal, last_d, last_st)
    return out



def _segment_lengths(raw) -> list[float]:
    """Độ dài từng đoạn cùng chiều của đường thô (giống cách trajectory.py chia)."""
    out: list[float] = []
    acc = 0.0
    cur = raw[1][1] if len(raw) > 1 else raw[0][1]
    for (pa, _da, _sa), (pb, db, _sb) in zip(raw, raw[1:]):
        if db != cur:
            out.append(acc)
            acc = 0.0
            cur = db
        acc += _hypot(pb.x - pa.x, pb.y - pa.y)
    out.append(acc)
    return out


def _legs_executable(raw, min_leg: float, min_edge: float) -> bool:
    """Mọi đoạn giữa phải đủ dài cho bộ bám đường; đoạn đầu/cuối được nới."""
    lens = _segment_lengths(raw)
    if len(lens) <= 2:
        return all(v >= min_edge for v in lens)
    if lens[0] < min_edge or lens[-1] < min_edge:
        return False
    return all(v >= min_leg for v in lens[1:-1])


def _assemble(fwd: _Tree, nid_f: int, bwd: _Tree, nid_b: int, rs_path,
              maxc: float, max_steer: float, wb: float,
              sub: float, rs_sub: float, goal: Pose):
    head = _forward_chain(fwd, nid_f, wb, sub)
    tail = _backward_chain(bwd, nid_b, wb, sub, goal)
    mid = []
    if rs_path is not None:
        qa = head[-1][0]
        samples = sample_path(qa, rs_path, maxc, rs_sub)
        mid = [(p, d, _steer_for(m, max_steer)) for p, d, m in samples[1:]]
    raw = head + mid + tail
    if len(raw) > 1:
        raw[0] = (raw[0][0], raw[1][1], raw[1][2])
    return raw


# ------------------------------------------------- dò khả năng thoát của đích

def _max_free_step(pose_ok, wb, x, y, yaw, d, steer, hi, rounds=0):
    """Quãng đường dài nhất còn đi được từ (x,y,yaw) theo (chiều, góc lái).

    Trả về 0 nếu ngay cả bước ngắn nhất cũng chạm. Với `rounds` > 0 thì tinh
    chỉnh bằng chia đôi sau khi đã tìm được khoảng chặn.
    """
    if abs(steer) < 1e-9:
        def at(t):
            return x + d * t * _cos(yaw), y + d * t * _sin(yaw), yaw
    else:
        k = _tan(steer) / wb
        R = 1.0 / k
        c, sn = _cos(yaw), _sin(yaw)

        def at(t):
            th = d * t * k
            ldx, ldy = R * _sin(th), R * (1.0 - _cos(th))
            return x + c * ldx - sn * ldy, y + sn * ldx + c * ldy, yaw + th

    def free(t):
        ax, ay, ayaw = at(t * 0.5)
        if not pose_ok(ax, ay, ayaw):
            return False
        ax, ay, ayaw = at(t)
        return pose_ok(ax, ay, ayaw)

    if free(hi):
        return hi
    lo = 0.0
    for _ in range(rounds + 6):
        mid = 0.5 * (lo + hi)
        if free(mid):
            lo = mid
        else:
            hi = mid
    return lo * 0.97


def _escape_probe(pose: Pose, pose_ok, wb: float, max_steer: float,
                  node_cap: int = 700, res: float = 0.005,
                  yres: float = math.radians(1.5), step_hi: float = 0.09):
    """Xe đứng ở `pose` có nhích ra khỏi chỗ đứng được không?

    Duyệt rộng trên lưới RẤT mịn (5 mm / 1,5°) với 9 mức lái và LUÔN đi bước dài
    nhất còn được. Nếu hàng đợi cạn sau vài chục nút thì tư thế này nằm trong một
    mảnh không gian tự do bị cô lập — không phải bộ lập đường yếu.

    Đây là ước lượng THIẾU (chỉ đi bước dài nhất, lưới rời rạc) nên "cạn hàng đợi"
    là bằng chứng rất mạnh chứ không phải chứng minh.
    """
    steers = [-max_steer + i * (2.0 * max_steer / 8.0) for i in range(9)]
    n_yaw = max(1, int(round(_TWO_PI / yres)))

    def key(px, py, pyaw):
        return (int(px / res), int(py / res),
                int(((pyaw + _PI) % _TWO_PI) / yres) % n_yaw)

    x0, y0, yaw0 = pose.x, pose.y, pose.yaw
    seen = {key(x0, y0, yaw0)}
    queue = [(x0, y0, yaw0)]
    head = 0
    dmax = 0.0
    amin = amax = 0.0
    while head < len(queue) and head < node_cap:
        x, y, yaw = queue[head]
        head += 1
        for d in (1, -1):
            for st in steers:
                L = _max_free_step(pose_ok, wb, x, y, yaw, d, st, step_hi, rounds=8)
                if L < 0.002:
                    continue
                if abs(st) < 1e-9:
                    nx_ = x + d * L * _cos(yaw)
                    ny_ = y + d * L * _sin(yaw)
                    nyaw = yaw
                else:
                    k = _tan(st) / wb
                    R = 1.0 / k
                    th = d * L * k
                    ldx, ldy = R * _sin(th), R * (1.0 - _cos(th))
                    nx_ = x + _cos(yaw) * ldx - _sin(yaw) * ldy
                    ny_ = y + _sin(yaw) * ldx + _cos(yaw) * ldy
                    nyaw = yaw + th
                kk = key(nx_, ny_, nyaw)
                if kk in seen:
                    continue
                seen.add(kk)
                queue.append((nx_, ny_, nyaw))
                dd = _hypot(nx_ - x0, ny_ - y0)
                if dd > dmax:
                    dmax = dd
                a = wrap_angle(nyaw - yaw0)
                if a < amin:
                    amin = a
                if a > amax:
                    amax = a
    exhausted = head >= len(queue)
    return exhausted, len(seen), dmax, amax - amin


# ------------------------------------------------------------------ hợp đồng

# Danh mục cấu hình chạy lần lượt. Mỗi mục: (tên, phần ngân sách tối đa, chỉnh
# tham số). Đo trên 16 ca cho thấy KHÔNG có một cấu hình nào tốt nhất mọi nơi:
# lưới thô đi rất nhanh ở chỗ rộng nhưng không biểu diễn nổi nhịp đẩy tới-lui
# trong khe hẹp; lưới mịn ngược lại.
_COARSE = ("thô", 0.14, {})
_MEDIUM = ("vừa", 0.42, {"xy_resolution": 0.025, "yaw_resolution": math.radians(2.5),
                         "step_length": 0.064, "n_steer": 5, "steer_ratio": 0.95,
                         "switch_cost": 0.12, "heuristic_weight": 1.5,
                         "meet_every": 3, "root_rs_every": 8})
_FINE = ("mịn", 1.00, {"xy_resolution": 0.010, "yaw_resolution": math.radians(1.5),
                       "step_length": 0.06, "n_steer": 5, "steer_ratio": 0.95,
                       "switch_cost": 0.10, "heuristic_weight": 1.6,
                       "meet_every": 3, "root_rs_every": 8})
_EXTRA = ("mịn+", 1.00, {"xy_resolution": 0.006, "yaw_resolution": math.radians(1.0),
                         "step_length": 0.06, "n_steer": 7, "steer_ratio": 0.95,
                         "switch_cost": 0.10, "heuristic_weight": 1.7,
                         "meet_every": 3, "root_rs_every": 8})

_WEDGE_STEP = 0.045       # m: bước tự do lớn nhất dưới mức này coi là "kẹt"
_ISOLATED_CELLS = 600     # số ô tối đa của một mảnh tự do bị cô lập
_ISOLATED_SPAN = 0.05     # m


def _free_span(pose: Pose, pose_ok, wb: float, max_steer: float, hi: float) -> float:
    """Bước tự do dài nhất trong mọi hướng lái tại một tư thế (đo độ chật)."""
    best = 0.0
    for d in (1, -1):
        for st in (-max_steer, -max_steer / 2, 0.0, max_steer / 2, max_steer):
            v = _max_free_step(pose_ok, wb, pose.x, pose.y, pose.yaw, d, st, hi, rounds=4)
            if v > best:
                best = v
                if best >= hi:
                    return best
    return best


def plan(start: Pose, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle],
         bounds: Bounds, params=None) -> PlanResult:
    t0 = time.perf_counter()
    base = BiParams()
    limit = base.time_limit
    if params is not None:
        v = getattr(params, "time_limit", None)
        if v is not None:
            limit = float(v)
    deadline_all = t0 + limit

    goal_true = check_pose(cfg, goal, obstacles, bounds)
    if not goal_true.ok:
        return PlanResult("GOAL_INVALID", "Đích không hợp lệ: " + goal_true.describe(),
                          None, time.perf_counter() - t0)
    start_true = check_pose(cfg, start, obstacles, bounds)
    if not start_true.ok:
        return PlanResult("START_INVALID", "Xuất phát không hợp lệ: " + start_true.describe(),
                          None, time.perf_counter() - t0)

    # Lề an toàn: đúng công thức của hybrid_astar.py, không nới lỏng.
    margin = min(base.safety_margin, goal_true.min_clearance / 2.0, start_true.min_clearance / 2.0)
    margin = max(margin, 0.0)

    # ---- dò độ chật tại đích và xuất phát (rẻ: vài chục lần thử va chạm)
    probe_checker = FastCollisionChecker(cfg, obstacles, bounds, margin)
    probe_ok = probe_checker.pose_ok
    full_steer = cfg.max_steer
    tight = []
    for tag, pose in (("đích", goal), ("xuất phát", start)):
        span = _free_span(pose, probe_ok, cfg.wheelbase, full_steer, 0.09)
        if span < _WEDGE_STEP:
            tight.append((tag, pose, span))

    wedged = bool(tight)
    for tag, pose, span in tight:
        exhausted, cells, dmax, aspan = _escape_probe(pose, probe_ok, cfg.wheelbase, full_steer)
        if exhausted and cells <= _ISOLATED_CELLS and dmax < _ISOLATED_SPAN:
            el = time.perf_counter() - t0
            return PlanResult(
                "NO_PATH",
                f"Tư thế {tag} bị cô lập: dò rộng ở lưới 5 mm/1,5° với lái hết cỡ chỉ tới "
                f"{cells} tư thế, dịch được nhiều nhất {dmax * 100:.1f} cm và xoay "
                f"{math.degrees(aspan):.0f}°, rồi cạn hàng đợi. Với lề an toàn "
                f"{margin * 100:.1f} cm bắt buộc thì ô này không có lối ra.",
                None, el, 0, cells, 0, margin)

    # Khe hẹp thì vào thẳng cấu hình mịn, khỏi phí ngân sách cho lưới thô.
    if wedged:
        attempts = (_FINE, _MEDIUM, _EXTRA)
    else:
        attempts = (_COARSE, _MEDIUM, _FINE)

    popped = expanded = 0
    reason = ""
    for name, share, tweak in attempts:
        now = time.perf_counter()
        if now >= deadline_all:
            break
        P = BiParams(**{**base.__dict__, **tweak})
        P.time_limit = limit
        deadline = deadline_all if share >= 1.0 else min(deadline_all, now + limit * share)
        raw, p, e, why = _plan_once(start, goal, cfg, obstacles, bounds, P, margin, deadline)
        popped += p
        expanded += e
        reason = f"lưới {name}: {why}"
        if raw is None:
            continue
        bad = _validate(raw, cfg, obstacles, bounds)
        if bad is not None:
            reason = f"lưới {name}: đường vi phạm kiểm tra vùng quét ({bad})"
            continue
        traj = build_trajectory(raw, goal, cfg, P.cruise_speed, P.approach_speed,
                                P.approach_distance)
        elapsed = time.perf_counter() - t0
        return PlanResult("OK", f"Tìm được đường dài {traj.length:.2f} m, "
                                f"{traj.n_cusps} lần đổi chiều (lưới {name})",
                          traj, elapsed, expanded, popped, 0, margin)

    elapsed = time.perf_counter() - t0
    status = "TIMEOUT" if elapsed >= limit * 0.95 else "NO_PATH"
    return PlanResult(status, f"Không nối được hai nhánh ({reason}; {popped} nút, {elapsed:.1f} s)",
                      None, elapsed, expanded, popped, 0, margin)


def _validate(raw, cfg, obstacles, bounds) -> str | None:
    for (pa, _, _), (pb, _, _) in zip(raw, raw[1:]):
        col = check_motion(cfg, pa, pb, obstacles, bounds)
        if not col.ok:
            return col.describe()
    return None
