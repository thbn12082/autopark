"""Ứng viên "Anytime nhiều độ phân giải" cho bài toán lập đường đỗ xe.

Ý TƯỞNG
-------
Bộ lập đường chạy Hybrid A* NHIỀU LẦN, mỗi lần một "mức" khác nhau, từ thô
tới mịn dần; luôn trả về nghiệm TỐT NHẤT đã tìm được khi hết ngân sách.

    mức 0: ô 10 cm / 15°, bước 12 cm, epsilon 3.0    -> nghiệm dùng tạm sau ~0,05 s
    mức 3: ô 1,2 cm / 2,5°, bước 2,2 cm              -> quay đầu 20 nhịp (uturn_w46)
    mức 4: ô 0,5 cm / 1,5°, bước 1,2 cm              -> đỗ song song chật (parallel_135)
    mức 5: ô 0,25 cm / 0,8°, bước 0,6 cm             -> ra khỏi ngách cực chật

Mức thô trả lời gần như tức thì (người dùng không bao giờ phải chờ tay trắng);
mức mịn mới đủ sức biểu diễn nhịp đẩy tới–lui trong ô chật. Đây chính là điểm
tắc của bộ lập đường cũ: lưới 5 cm với bước 8 cm làm mỗi vòng đẩy (dịch ngang
2–3 cm) rơi lại đúng ô lưới cũ và bị tập đóng loại bỏ. Không thể sửa bằng cách
chạy nhanh hơn — phải đổi độ phân giải.

Nghiệm của mức trước được dùng cho mức sau theo hai cách:
  1. làm cận trên chi phí (cắt nhánh kiểu ARA*),
  2. làm "hành lang ưu tiên": nút nằm gần đường cũ được giảm nhẹ f, giúp mức mịn
     đi lại vết cũ rất nhanh rồi mới toả ra chỗ khác.

Năm cải tiến kỹ thuật đi kèm (đều đo được, không phải phỏng đoán):
  * NHẬN Ô LƯỚI THEO LẦN CHẠM ĐẦU thay vì theo chi phí `g` nhỏ nhất. Đây là thay
    đổi quan trọng NHẤT. Với cách nhận theo `g`, một nút "lười" (đi thẳng, g nhỏ)
    cướp ô của nút đang giữa chuỗi đẩy tới–lui và làm đứt chuỗi. Đo ở mức mịn
    nhất trên `parallel_135`: nhận-theo-g mở được 181 nút rồi hàng đợi rỗng;
    nhận-lần-đầu mở được hơn 120.000 nút và thoát ra khỏi ô đỗ. Cùng ca đó,
    nhận-lần-đầu tìm ra đường sau 578 nút (0,06 s).
  * `FastCollisionChecker` giải tích thay Shapely trong vòng trong (nhanh ~17×).
  * Reeds–Shepp ĐẦY ĐỦ (`cand_anytime_rs`, 44 từ đường gồm CCCC/CCSC/CCSCC)
    thay bản 16 từ; đây là những họ nối được hai tư thế trong chỗ chật. Cú thử
    nối được kiểm va chạm theo kiểu "sinh tới đâu kiểm tới đó, chạm là bỏ" và có
    một bộ lọc rẻ đi trước (so quãng đường 2D có vật cản với đường chim bay):
    trước khi tối ưu, 95 % thời gian nằm ở đây.
  * Heuristic Reeds–Shepp có NHỚ (memoize theo tư thế tương đối đã làm tròn),
    thay vì tính lại từ đầu cho mỗi nút.
  * Mỗi độ phân giải chạy cả hai chiều: NGƯỢC (đích → xuất phát, rồi đảo đường)
    trước, rồi xuôi. Với bài đỗ xe, đích nằm trong chỗ chật còn xuất phát ở chỗ
    thoáng, nên cú bắn Reeds–Shepp từ phía đích ra chỗ thoáng dễ thành công hơn
    nhiều. Đo trên `pillar_at_slot_mouth`: chạy ngược 0,06 s, chạy xuôi 10 s.

Sau khi có đường, một bước "làm sạch đuôi" (`_polish`) thử thay phần cuối bằng
một đường Reeds–Shepp mà mọi đoạn cùng chiều đều đủ dài. Không có bước này, tìm
kiếm hay kết thúc bằng vài nhịp bẻ 4 cm hết lái: hình học hợp lệ nhưng bộ bám
dừng sớm ở mỗi nhịp và về đích lệch quá dung sai.

HỢP ĐỒNG
--------
    plan(start, goal, cfg, obstacles, bounds, params=None) -> PlanResult

Tôn trọng `params.time_limit`. Đường trả về luôn được kiểm tra lại bằng
`footprint.check_motion` với thân xe THẬT trước khi dựng quỹ đạo.
"""
from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field

from autopark.domain.types import (
    Bounds,
    Obstacle,
    ParkingGoal,
    Pose,
    Scenario,
    VehicleConfig,
    wrap_angle,
)
from autopark.geometry.fast_collision import FastCollisionChecker
from autopark.geometry.footprint import check_motion, check_pose
from autopark.simulation.rollout import rollout
from autopark.planning.cand_anytime_rs import (
    RSPath,
    normalized_goal,
    path_end,
    raw_candidates,
    sample_path,
    shortest_length_fast,
)
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.trajectory import build_trajectory

_cos = math.cos
_sin = math.sin
_hypot = math.hypot
_atan2 = math.atan2
_INF = math.inf
TWO_PI = 2.0 * math.pi


# --------------------------------------------------------------------------- tham số

@dataclass
class AnytimeParams:
    """Tham số của ứng viên. Bench truyền `PlannerParams`; chỉ `time_limit` được đọc."""

    time_limit: float = 8.0
    safety_margin: float = 0.03        # giống hybrid_astar.py, không được nới lỏng
    steer_ratio: float = 0.85          # giống hybrid_astar.py
    goal_xy_tol: float = 0.02          # chặt hơn mốc chuẩn (0,03) — không làm bài dễ đi
    goal_yaw_tol: float = math.radians(2.0)
    reverse_cost: float = 1.25
    switch_cost: float = 0.55
    steer_cost: float = 0.15
    steer_change_cost: float = 0.25
    hol_resolution: float = 0.03       # lưới heuristic 2D
    collision_sample: float = 0.035    # khoảng cách mẫu kiểm va chạm trong bước mở rộng
    path_sample: float = 0.015         # khoảng cách mẫu của đường trả về
    rs_sample: float = 0.02
    rs_max_candidates: int = 6
    min_segment: float = 0.06         # m: đoạn cùng chiều ngắn hơn mức này rất khó bám
    max_nodes_per_level: int = 400_000
    refine_after_first: float = 2.0    # s: sau khi có nghiệm đầu, còn cải thiện tối đa chừng này
    refine_slice: float = 0.55         # s: trần cho MỖI mức trong giai đoạn cải thiện
    cruise_speed: float = 0.15
    approach_speed: float = 0.08
    approach_distance: float = 0.30


@dataclass(frozen=True)
class _Level:
    xy_res: float
    yaw_res: float
    steps: tuple                # ((độ dài bước, số mức lái), ...) — đa độ phân giải trong KHÔNG GIAN ĐIỀU KHIỂN
    eps: float
    rs_radius: float
    rs_every: int
    cap: float                  # >0: trần thời gian (giây); <0: |cap| lần thời gian CÒN LẠI
    backward: bool              # True: tìm từ đích ngược về xuất phát


def _default_levels() -> list[_Level]:
    """Bậc thang độ phân giải.

    Ràng buộc rút ra từ đo đạc (xem ghi chú đầu file): tập đóng chỉ không nuốt
    mất nhịp đẩy tới–lui khi Ô LƯỚI NHỎ HƠN bước đi, cả về vị trí lẫn về góc:

        xy_res  <~ bước,        yaw_res <~ bước / bán_kính_quay

    Với xe này (R = 0,398 m) bước 1,2 cm đổi hướng 1,73°, nên mức mịn nhất phải
    dùng ô 0,5 cm và 1,5°. Ở mức mịn vẫn giữ thêm một bước DÀI (ít mức lái) để
    còn băng qua chỗ thoáng nhanh, nếu không tìm kiếm sẽ bò từng centimet.

    Thứ tự: hai mức thô CHẠY XUÔI trước (trả lời tức thì cho ca dễ), rồi cả thang
    độ phân giải CHẠY NGƯỢC (từ đích ra), rồi lại cả thang chạy xuôi. Chạy ngược
    được ưu tiên vì với bài đỗ xe, đích nằm trong chỗ chật còn xuất phát ở chỗ
    thoáng: cú bắn Reeds–Shepp từ phía đích ra chỗ thoáng dễ thành công hơn nhiều.
    Đo trên `pillar_at_slot_mouth`: mức mịn chạy ngược xong trong 0,06 s, cùng mức
    chạy xuôi mất 10 s.
    """
    d = math.radians
    return [
        # --- thô, chạy xuôi: nghiệm dùng tạm gần như tức thì
        _Level(0.100, d(15.0), ((0.120, 5),), 3.0, 1.2, 3, 0.30, False),
        _Level(0.050, d(8.0), ((0.070, 7),), 2.2, 1.0, 2, 0.45, False),
        # --- thang độ phân giải, chạy NGƯỢC
        _Level(0.0250, d(5.00), ((0.040, 7),), 1.8, 0.9, 2, 0.50, True),
        # mức này là mức giải được `uturn_w46` (quay đầu 20 nhịp), cần ~10 s
        _Level(0.0120, d(2.50), ((0.022, 7), (0.088, 3)), 1.7, 0.8, 2, -0.60, True),
        _Level(0.0050, d(1.50), ((0.012, 7), (0.072, 3)), 1.7, 0.7, 2, -0.40, True),
        # ô 2,5 mm / 0,8°: đo được là ngưỡng để xe RA ĐƯỢC khỏi ngách của
        # `pocket_exit_park` (134 ô đạt tới ở mức trên, 636.651 ô ở mức này)
        _Level(0.0025, d(0.80), ((0.006, 7), (0.060, 3)), 1.7, 0.6, 2, -0.45, True),
        # --- thang độ phân giải, chạy xuôi
        _Level(0.0250, d(5.00), ((0.040, 7),), 1.6, 0.9, 2, 0.40, False),
        _Level(0.0120, d(2.50), ((0.022, 7), (0.088, 3)), 1.5, 0.8, 2, -0.40, False),
        _Level(0.0050, d(1.50), ((0.012, 7), (0.072, 3)), 1.4, 0.7, 2, -0.50, False),
        _Level(0.0025, d(0.80), ((0.006, 7), (0.060, 3)), 1.4, 0.6, 2, -1.00, False),
    ]


# --------------------------------------------------------------- heuristic 2D có vật cản

class _GridHeuristic:
    """Khoảng cách 2D tới một điểm đích trên lưới có vật cản (Dijkstra 8 hướng).

    Dựng bằng phép thử điểm-trong-hình-chữ-nhật giải tích, không dùng Shapely,
    nên rẻ hơn bản trong `hybrid_astar.py` nhiều lần.
    """

    __slots__ = ("res", "xmin", "ymin", "nx", "ny", "dist", "tx", "ty")

    def __init__(self, target: Pose, bounds: Bounds, obstacles: list[Obstacle],
                 res: float, inflate: float):
        self.res = res
        self.xmin, self.ymin = bounds.xmin, bounds.ymin
        self.tx, self.ty = target.x, target.y
        nx = max(1, int(math.ceil(bounds.width / res)))
        ny = max(1, int(math.ceil(bounds.height / res)))
        self.nx, self.ny = nx, ny

        rects = []
        for o in obstacles:
            rects.append((o.cx, o.cy, _cos(o.yaw), _sin(o.yaw),
                          o.width / 2.0 + inflate, o.height / 2.0 + inflate))
        ix0, iy0 = bounds.xmin + inflate, bounds.ymin + inflate
        ix1, iy1 = bounds.xmax - inflate, bounds.ymax - inflate

        blocked = bytearray(nx * ny)
        for i in range(nx):
            cx = self.xmin + (i + 0.5) * res
            inside_x = ix0 <= cx <= ix1
            base = i * ny
            for j in range(ny):
                cy = self.ymin + (j + 0.5) * res
                if not inside_x or not (iy0 <= cy <= iy1):
                    blocked[base + j] = 1
                    continue
                for ox, oy, c, s, hx, hy in rects:
                    dx, dy = cx - ox, cy - oy
                    if abs(c * dx + s * dy) <= hx and abs(-s * dx + c * dy) <= hy:
                        blocked[base + j] = 1
                        break

        dist = [_INF] * (nx * ny)
        gi = min(max(int((target.x - self.xmin) / res), 0), nx - 1)
        gj = min(max(int((target.y - self.ymin) / res), 0), ny - 1)
        g0 = gi * ny + gj
        dist[g0] = 0.0
        heap = [(0.0, g0)]
        push, pop = heapq.heappush, heapq.heappop
        diag = res * math.sqrt(2.0)
        while heap:
            d, idx = pop(heap)
            if d > dist[idx]:
                continue
            i, j = divmod(idx, ny)
            for di in (-1, 0, 1):
                ni = i + di
                if ni < 0 or ni >= nx:
                    continue
                for dj in (-1, 0, 1):
                    if di == 0 and dj == 0:
                        continue
                    nj = j + dj
                    if nj < 0 or nj >= ny:
                        continue
                    nidx = ni * ny + nj
                    step = diag if (di and dj) else res
                    if blocked[nidx]:
                        step *= 4.0    # đi được nhưng đắt: giữ heuristic hữu hạn ở chỗ hẹp
                    nd = d + step
                    if nd < dist[nidx]:
                        dist[nidx] = nd
                        push(heap, (nd, nidx))
        self.dist = dist

    def __call__(self, x: float, y: float) -> float:
        i = int((x - self.xmin) / self.res)
        j = int((y - self.ymin) / self.res)
        if 0 <= i < self.nx and 0 <= j < self.ny:
            d = self.dist[i * self.ny + j]
            if d < _INF:
                return d
        return _hypot(self.tx - x, self.ty - y)


# --------------------------------------------------------------------- ngữ cảnh chung

class _Ctx:
    def __init__(self, cfg: VehicleConfig, obstacles: list[Obstacle], bounds: Bounds,
                 margin: float, p: AnytimeParams):
        self.cfg = cfg
        self.bounds = bounds
        self.obstacles = obstacles
        self.p = p
        self.margin = margin
        self.checker = FastCollisionChecker(cfg, obstacles, bounds, margin)
        self.max_steer = cfg.max_steer * p.steer_ratio
        self.maxc = math.tan(self.max_steer) / cfg.wheelbase
        self.inflate = min(cfg.width / 2.0, cfg.rear_overhang) + margin
        self._hol: dict[tuple[int, int], _GridHeuristic] = {}
        self.rs_cache: dict[tuple[int, int, int], float] = {}
        self.prim_cache: dict[tuple[float, int], list] = {}

    def holonomic(self, target: Pose) -> _GridHeuristic:
        key = (int(target.x * 1000), int(target.y * 1000))
        h = self._hol.get(key)
        if h is None:
            h = _GridHeuristic(target, self.bounds, self.obstacles,
                               self.p.hol_resolution, self.inflate)
            self._hol[key] = h
        return h

    def primitives(self, steps: tuple) -> list:
        """(dir, steer, cost_base, mẫu-va-chạm, mẫu-đường, (dx, dy, dyaw) cuối).

        `steps` là bộ ((độ dài, số mức lái), ...): mức mịn dùng một bước ngắn với
        nhiều mức lái để lách, kèm một bước dài với ít mức lái để băng chỗ thoáng.
        """
        key = steps
        got = self.prim_cache.get(key)
        if got is not None:
            return got
        p = self.p
        ms = self.max_steer
        L = self.cfg.wheelbase
        out = []
        seen = set()
        for step, n_steer in steps:
            n = max(3, n_steer | 1)
            steers = [-ms + i * (2.0 * ms / (n - 1)) for i in range(n)]
            n_col = max(1, int(math.ceil(step / p.collision_sample)))
            n_path = max(1, int(math.ceil(step / p.path_sample)))
            for direction in (1, -1):
                for steer in steers:
                    tag = (direction, round(steer, 9), round(step, 9))
                    if tag in seen:
                        continue
                    seen.add(tag)
                    k = math.tan(steer) / L
                    s_signed = direction * step
                    cost = step * (p.reverse_cost if direction < 0 else 1.0)
                    cost += p.steer_cost * abs(steer) * step

                    def offs(count, k=k, s_signed=s_signed):
                        res = []
                        for m in range(1, count + 1):
                            s = s_signed * m / count
                            if abs(k) < 1e-9:
                                res.append((s, 0.0, 0.0))
                            else:
                                dyaw = s * k
                                r = 1.0 / k
                                res.append((r * _sin(dyaw), r * (1.0 - _cos(dyaw)), dyaw))
                        return res

                    col = offs(n_col)
                    pth = offs(n_path)
                    out.append((direction, steer, cost, col, pth, col[-1]))
        self.prim_cache[key] = out
        return out


# ------------------------------------------------------------------------ cú bắn RS

def _steer_of(mode: str, max_steer: float) -> float:
    return max_steer if mode == "L" else (-max_steer if mode == "R" else 0.0)


def _walk_ok(ok, lengths, ctypes, maxc, x0, y0, yaw0, step) -> bool:
    """Đi dọc đường RS, kiểm va chạm NGAY khi sinh từng mẫu và bỏ cuộc ở lần chạm đầu.

    Bản cũ dựng cả danh sách mẫu rồi mới kiểm; đo bằng cProfile cho thấy 95 % thời
    gian nằm ở đó vì phần lớn ứng viên chạm ngay mẫu thứ vài.
    """
    x, y, yaw = x0, y0, yaw0
    inv = 1.0 / maxc
    for l, m in zip(lengths, ctypes):
        al = l if l >= 0.0 else -l
        if al < 1e-12:
            continue
        n = int(al / (step * maxc)) + 1
        c, s = _cos(yaw), _sin(yaw)
        if m == "S":
            d = l * inv
            for k in range(1, n + 1):
                t = d * k / n
                if not ok(x + c * t, y + s * t, yaw):
                    return False
            x += c * d
            y += s * d
        else:
            sgn = 1.0 if m == "L" else -1.0
            for k in range(1, n + 1):
                p = l * k / n
                ldx = _sin(p) * inv
                ldy = sgn * (1.0 - _cos(p)) * inv
                if not ok(x + c * ldx - s * ldy, y + s * ldx + c * ldy, yaw + sgn * p):
                    return False
            ldx = _sin(l) * inv
            ldy = sgn * (1.0 - _cos(l)) * inv
            x, y, yaw = x + c * ldx - s * ldy, y + s * ldx + c * ldy, yaw + sgn * l
    return True


def _min_run(lengths, maxc: float):
    """(đoạn cùng chiều ngắn nhất, đoạn cùng chiều CUỐI) tính bằng mét.

    Bộ bám đường dừng hẳn ở mỗi lần đổi chiều rồi chỉnh lái tại chỗ; một đoạn chỉ
    vài centimet không đủ cho nó chỉnh xong hướng. Đo trên `pillar_at_slot_mouth`:
    đuôi RS gồm ba đoạn 4 cm làm xe mô phỏng về đích lệch 5,2° (quá dung sai 5°)
    dù đường hình học hoàn toàn hợp lệ. Vì vậy ưu tiên đường có đoạn đủ dài.
    """
    best = _INF
    run = 0.0
    prev = 0.0
    for v in lengths:
        av = v if v >= 0.0 else -v
        if av < 1e-12:
            continue
        if prev != 0.0 and (v > 0.0) != (prev > 0.0):
            if run < best:
                best = run
            run = 0.0
        run += av
        prev = v
    if run < best:
        best = run
    if best >= _INF:
        return _INF, _INF
    return best / maxc, run / maxc


def _try_rs(ctx: _Ctx, pose: Pose, target: Pose, max_len: float = _INF, strict: bool = False):
    """Nối `pose` tới `target` bằng một đường Reeds–Shepp không va chạm; None nếu không được.

    `strict=True` chỉ nhận đường mà mọi đoạn cùng chiều đều đủ dài cho bộ bám.
    """
    maxc = ctx.maxc
    x, y, phi = normalized_goal(pose, target, maxc)
    raw = raw_candidates(x, y, phi)
    if not raw:
        return None
    sw = ctx.p.switch_cost * maxc
    lim = max_len * maxc
    scored = []
    for lengths, types in raw:
        tot = 0.0
        cusp = 0
        prev = 0.0
        bad = False
        for v in lengths:
            av = v if v >= 0.0 else -v
            if av != av or av > 1e6:
                bad = True
                break
            tot += av
            if av > 1e-12:
                if prev != 0.0 and (v > 0.0) != (prev > 0.0):
                    cusp += 1
                prev = v
        if bad or tot > lim:
            continue
        # Phạt nặng đường có đoạn cùng chiều quá ngắn: hình học đúng nhưng bộ bám
        # đường không chạy nổi (xem `_min_run`).
        mn, last = _min_run(lengths, maxc)
        short = mn < ctx.p.min_segment
        if short and strict:
            continue
        pen = (6.0 * sw if short else 0.0) + (10.0 * sw if last < ctx.p.min_segment else 0.0)
        scored.append((tot + cusp * sw + pen, tot, lengths, types))
    if not scored:
        return None
    scored.sort(key=lambda it: it[0])
    ok = ctx.checker.pose_ok
    rs_step = ctx.p.rs_sample
    px, py, pyaw = pose.x, pose.y, pose.yaw
    for _, _, lengths, types in scored[:ctx.p.rs_max_candidates]:
        if not _walk_ok(ok, lengths, types, maxc, px, py, pyaw, rs_step):
            continue
        path = RSPath(lengths, types)
        end = path_end(pose, path, maxc)
        if (_hypot(end.x - target.x, end.y - target.y) * maxc > 1e-6
                or abs(wrap_angle(end.yaw - target.yaw)) > 1e-6):
            continue
        samples = sample_path(pose, path, maxc, ctx.p.path_sample)
        ms = ctx.max_steer
        return [(q, d, _steer_of(m, ms)) for q, d, m in samples[1:]]
    return None


# -------------------------------------------------------------------------- tìm kiếm

def _search(ctx: _Ctx, q_start: Pose, q_goal: Pose, lv: _Level, deadline: float,
            cost_bound: float, corridor: set | None):
    """Một lần chạy Hybrid A* ở độ phân giải của `lv`.

    Trả về (raw_path, cost, popped, expanded, status) với status trong
    {"OK", "EXHAUSTED", "TIMEOUT", "BOUND"}.
    """
    p = ctx.p
    b = ctx.bounds
    ok = ctx.checker.pose_ok
    maxc = ctx.maxc
    hol = ctx.holonomic(q_goal)
    rs_cache = ctx.rs_cache

    res = lv.xy_res
    yaw_res = lv.yaw_res
    n_yaw = max(1, int(round(TWO_PI / yaw_res)))
    ny_cells = max(1, int(b.height / res) + 2)
    prims = ctx.primitives(lv.steps)
    short_step = min(st for st, _ in lv.steps)
    eps = lv.eps
    switch_cost = p.switch_cost
    steer_change = p.steer_change_cost
    rs_r2 = lv.rs_radius * lv.rs_radius
    gx, gy, gyaw = q_goal.x, q_goal.y, q_goal.yaw
    xy_tol2 = p.goal_xy_tol * p.goal_xy_tol
    yaw_tol = p.goal_yaw_tol

    # --- heuristic Reeds–Shepp có nhớ (làm tròn tư thế tương đối rồi tra bảng)
    QP = 20.0                      # bước lưới nhớ: 0,05 đơn vị chuẩn hoá
    QA = 24.0 / math.pi            # ~7,5°
    h_rs_r2 = max(rs_r2, 1.44)     # dùng heuristic RS rộng hơn bán kính thử nối

    def h_of(x, y, yaw):
        h = hol(x, y)
        dx = gx - x
        dy = gy - y
        if dx * dx + dy * dy < h_rs_r2:
            c = _cos(yaw)
            s = _sin(yaw)
            nx_ = (c * dx + s * dy) * maxc
            ny_ = (-s * dx + c * dy) * maxc
            nphi = gyaw - yaw
            if nphi > math.pi:
                nphi -= TWO_PI
            elif nphi < -math.pi:
                nphi += TWO_PI
            # Làm tròn XUỐNG rồi tính tại TÂM Ô: giá trị nhớ không phụ thuộc
            # điểm hỏi đầu tiên, nên heuristic (và cả kết quả) tất định.
            kx = int(nx_ * QP // 1.0)
            ky = int(ny_ * QP // 1.0)
            ka = int(nphi * QA // 1.0)
            key = (kx, ky, ka)
            v = rs_cache.get(key)
            if v is None:
                v = shortest_length_fast((kx + 0.5) / QP, (ky + 0.5) / QP,
                                         (ka + 0.5) / QA) / maxc
                rs_cache[key] = v
            if v > h:
                h = v
        return h

    # --- kho nút (danh sách song song cho nhanh)
    NX, NY, NYAW, NDIR, NSTEER, NG, NPAR, NPRIM = [], [], [], [], [], [], [], []
    NX.append(q_start.x); NY.append(q_start.y); NYAW.append(q_start.yaw)
    NDIR.append(0); NSTEER.append(0.0); NG.append(0.0); NPAR.append(-1); NPRIM.append(-1)

    xmin, ymin = b.xmin, b.ymin

    def key_of(x, y, yaw, direction):
        iy = int((yaw + math.pi) % TWO_PI / yaw_res)
        if iy >= n_yaw:
            iy = n_yaw - 1
        return ((int((x - xmin) / res) * ny_cells + int((y - ymin) / res)) * n_yaw + iy) * 2 + (
            1 if direction > 0 else 0)

    # NHẬN Ô THEO LẦN CHẠM ĐẦU, không theo `g` nhỏ nhất. Đây là điểm khác cốt lõi
    # so với Hybrid A* thông thường và là thứ làm chỗ chật giải được — xem chú
    # thích ở đầu hàm.
    claimed = {key_of(q_start.x, q_start.y, q_start.yaw, 0)}
    heap = [(eps * h_of(q_start.x, q_start.y, q_start.yaw), 0, 0)]
    push, pop = heapq.heappush, heapq.heappop
    counter = 1
    popped = expanded = 0
    max_nodes = p.max_nodes_per_level
    check_clock = 0

    # thử nối thẳng từ xuất phát trước khi tìm kiếm
    tail = _try_rs(ctx, q_start, q_goal)
    if tail is not None:
        raw = [(q_start, tail[0][1], tail[0][2])] + tail
        cost = sum(_hypot(a[0].x - c[0].x, a[0].y - c[0].y) for a, c in zip(raw, raw[1:]))
        return raw, cost, 0, 0, "OK"

    corridor_bonus = 0.25 * short_step if corridor else 0.0

    while heap:
        f, _, nid = pop(heap)
        x = NX[nid]; y = NY[nid]; yaw = NYAW[nid]; d0 = NDIR[nid]
        popped += 1

        check_clock += 1
        if check_clock >= 128:
            check_clock = 0
            if time.perf_counter() > deadline:
                return None, _INF, popped, expanded, "TIMEOUT"
            if popped > max_nodes:
                return None, _INF, popped, expanded, "TIMEOUT"

        g0 = NG[nid]
        st0 = NSTEER[nid]
        dxg = gx - x
        dyg = gy - y
        d2 = dxg * dxg + dyg * dyg

        if d2 < xy_tol2:
            dyw = gyaw - yaw
            if dyw > math.pi:
                dyw -= TWO_PI
            elif dyw < -math.pi:
                dyw += TWO_PI
            if abs(dyw) < yaw_tol:
                return _rebuild(ctx, NX, NY, NYAW, NPAR, NPRIM, nid, prims), g0, popped, expanded, "OK"

        # Lọc rẻ trước khi thử nối Reeds–Shepp: nếu quãng đường 2D CÓ VẬT CẢN dài
        # hơn hẳn đường chim bay thì giữa hai đầu có vật chắn, đường RS gần như
        # chắc chắn va chạm — bỏ qua, đỡ ~0,4 ms mỗi lần thử.
        if d2 < rs_r2 and (popped % lv.rs_every == 0 or d2 < 0.09):
            dg = math.sqrt(d2)
            tail = None if hol(x, y) > 1.6 * dg + 0.05 else _try_rs(
                ctx, Pose(x, y, yaw), q_goal, 3.0 * dg + 0.45)
            if tail is not None:
                raw = _rebuild(ctx, NX, NY, NYAW, NPAR, NPRIM, nid, prims)
                raw = raw + tail
                return raw, g0 + len(tail) * p.rs_sample, popped, expanded, "OK"

        cyaw = _cos(yaw)
        syaw = _sin(yaw)
        for pi, (direction, steer, cost_base, col, _pth, fin) in enumerate(prims):
            bad = False
            for dx, dy, dyaw in col:
                if not ok(x + cyaw * dx - syaw * dy, y + syaw * dx + cyaw * dy, yaw + dyaw):
                    bad = True
                    break
            if bad:
                continue
            fdx, fdy, fdyaw = fin
            nx2 = x + cyaw * fdx - syaw * fdy
            ny2 = y + syaw * fdx + cyaw * fdy
            nyaw2 = yaw + fdyaw
            if nyaw2 > math.pi:
                nyaw2 -= TWO_PI
            elif nyaw2 < -math.pi:
                nyaw2 += TWO_PI
            nk = key_of(nx2, ny2, nyaw2, direction)
            if nk in claimed:
                continue
            g = g0 + cost_base + steer_change * abs(steer - st0)
            if d0 != 0 and direction != d0:
                g += switch_cost
            h = h_of(nx2, ny2, nyaw2)
            if g + h >= cost_bound:
                continue
            claimed.add(nk)
            NX.append(nx2); NY.append(ny2); NYAW.append(nyaw2)
            NDIR.append(direction); NSTEER.append(steer); NG.append(g)
            NPAR.append(nid); NPRIM.append(pi)
            fv = g + eps * h
            if corridor_bonus and (int(nx2 / 0.05), int(ny2 / 0.05)) in corridor:
                fv -= corridor_bonus
            push(heap, (fv, counter, len(NX) - 1))
            counter += 1
            expanded += 1

    return None, _INF, popped, expanded, "EXHAUSTED"


def _rebuild(ctx, NX, NY, NYAW, NPAR, NPRIM, nid, prims):
    """Dựng lại dãy (tư thế, chiều, góc lái) dày ~`path_sample` từ chuỗi nút."""
    chain = []
    i = nid
    while i >= 0:
        chain.append(i)
        i = NPAR[i]
    chain.reverse()
    if len(chain) == 1:
        return [(Pose(NX[chain[0]], NY[chain[0]], NYAW[chain[0]]), 1, 0.0)]
    first = prims[NPRIM[chain[1]]]
    out = [(Pose(NX[chain[0]], NY[chain[0]], NYAW[chain[0]]), first[0], first[1])]
    for a, bnode in zip(chain, chain[1:]):
        pr = prims[NPRIM[bnode]]
        direction, steer = pr[0], pr[1]
        x, y, yaw = NX[a], NY[a], NYAW[a]
        c, s = _cos(yaw), _sin(yaw)
        for dx, dy, dyaw in pr[4]:
            out.append((Pose(x + c * dx - s * dy, y + s * dx + c * dy,
                             wrap_angle(yaw + dyaw)), direction, steer))
    return out


# ------------------------------------------------------------------------ tiện ích

def _reverse_raw(raw):
    """Đảo chiều một đường: cùng hình học, chiều chạy đổi dấu, góc lái giữ nguyên.

    Mô hình xe đạp đối xứng theo thời gian (v -> -v, δ giữ nguyên), nên đường đi
    từ đích về xuất phát chạy ngược lại chính là đường từ xuất phát tới đích.
    """
    n = len(raw)
    out = []
    for j in range(n):
        i = n - 1 - j
        k = i + 1 if i + 1 < n else i
        out.append((raw[i][0], -raw[k][1], raw[k][2]))
    return out


def _validate(cfg, raw, obstacles, bounds) -> bool:
    for (pa, _, _), (pb, _, _) in zip(raw, raw[1:]):
        if not check_motion(cfg, pa, pb, obstacles, bounds).ok:
            return False
    return True


def _raw_length(raw) -> float:
    s = 0.0
    for (pa, _, _), (pb, _, _) in zip(raw, raw[1:]):
        s += _hypot(pb.x - pa.x, pb.y - pa.y)
    return s


def _short_segments(raw, min_len: float) -> int:
    """Số đoạn cùng chiều ngắn hơn `min_len` — chỉ số "khó bám" của một đường."""
    n = 0
    run = 0.0
    for a, b in zip(raw, raw[1:]):
        run += _hypot(b[0].x - a[0].x, b[0].y - a[0].y)
        if a[1] != b[1]:
            if run < min_len:
                n += 1
            run = 0.0
    if run < min_len:
        n += 1
    return n


def _last_run(raw) -> float:
    run = 0.0
    for a, b in zip(reversed(raw[:-1]), reversed(raw[1:])):
        if a[1] != b[1]:
            break
        run += _hypot(b[0].x - a[0].x, b[0].y - a[0].y)
    return run


def _path_cost(raw, p: AnytimeParams) -> float:
    """Chi phí dùng để CHỌN giữa các nghiệm — không phải chi phí trong tìm kiếm.

    Ngoài độ dài và số lần đổi chiều, phạt hai thứ làm bộ bám sai số:
    đoạn cùng chiều quá ngắn, và ĐẶC BIỆT đoạn CUỐI quá ngắn. Đoạn cuối quyết
    định sai số về đích: bộ bám dừng cách điểm cuối 1 cm, nếu đoạn cuối đang hết
    lái thì 1 cm đó đã là 1,4° sai hướng.
    """
    c = (_raw_length(raw) + _raw_cusps(raw) * p.switch_cost
         + 1.5 * _short_segments(raw, p.min_segment))
    if _last_run(raw) < p.min_segment:
        c += 3.0
    return c


def _polish(ctx: _Ctx, raw, target: Pose):
    """Cắt ngắn phần đuôi bằng một đường Reeds–Shepp "sạch" nối thẳng tới đích.

    Tìm kiếm trên lưới hay kết thúc bằng vài nhịp bẻ 4 cm hết lái: hình học hợp
    lệ nhưng bộ bám dừng sớm ở mỗi nhịp và tích luỹ sai số hướng (đo trên
    `pillar_at_slot_mouth`: 5,2° > dung sai 5°). Ở đây thử nối từ từng điểm dọc
    đường tới đích bằng một đường RS mà MỌI đoạn cùng chiều đều đủ dài, rồi giữ
    phương án rẻ nhất. Chi phí ~50 ms, chạy một lần cho mỗi nghiệm.
    """
    n = len(raw)
    if n < 3:
        return raw
    stride = max(1, n // 140)
    best = raw
    best_cost = _path_cost(raw, ctx.p)
    for i in range(0, n - 1, stride):
        tail = _try_rs(ctx, raw[i][0], target, _INF, strict=True)
        if tail is None:
            continue
        cand = raw[:i + 1] + tail
        c = _path_cost(cand, ctx.p)
        if c < best_cost:
            best_cost = c
            best = cand
    return best


def _trackable(ctx: _Ctx, traj, start: Pose, goal: Pose) -> bool:
    """Chạy thử kín vòng: xe mô phỏng + bộ bám đường có đi hết được quỹ đạo không?

    LÝ DO. Một đường hợp lệ về hình học vẫn có thể không chạy được. Bộ bám dừng
    cách điểm cuối mỗi đoạn 1 cm; khi đang hết lái, 1 cm đó là 1,4° sai hướng, và
    trên đường quay đầu 20 nhịp sai số cộng dồn tới 60°. Đo được trên `uturn_w46`:
    hai đường cùng 20 nhịp, cùng chi phí hình học 33,6 và 33,7 — một đường về đích
    lệch 1,8°, đường kia lệch 57,7°. Không có đại lượng hình học rẻ tiền nào tách
    được hai trường hợp đó, nên ở đây mô phỏng thẳng.

    Đây là bước TỰ KIỂM của bộ lập đường, không phải nới lỏng kiểm tra: dung sai
    dùng ở đây (4 cm / 4°) CHẶT HƠN dung sai chấm điểm (5 cm / 5°).
    """
    sc = Scenario(name="_check", bounds=ctx.bounds, start=start,
                  goal=ParkingGoal(goal), obstacles=list(ctx.obstacles))
    rep = rollout(sc, ctx.cfg, traj, max_time=ctx.p.track_max_time).report
    return bool(rep.completed and not rep.collided
                and rep.position_error <= ctx.p.track_tol_xy
                and abs(rep.heading_error) <= ctx.p.track_tol_yaw)


def _raw_cusps(raw) -> int:
    n = 0
    for a, b in zip(raw, raw[1:]):
        if a[1] != b[1]:
            n += 1
    return n


def _corridor_of(raw, cell=0.05) -> set:
    out = set()
    for pose, _, _ in raw:
        i = int(pose.x / cell)
        j = int(pose.y / cell)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                out.add((i + di, j + dj))
    return out


# ------------------------------------------------------------------------ điểm vào

@dataclass
class AnytimeReport:
    """Thông tin riêng của ứng viên: đã chạy tới mức nào, nghiệm đầu tiên lúc nào."""

    first_solution_time: float = _INF
    first_solution_time_abs: float = _INF
    first_solution_level: int = -1
    first_length: float = 0.0
    first_cusps: int = 0
    final_level: int = -1
    final_length: float = 0.0
    final_cusps: int = 0
    levels_run: int = 0
    improved: int = 0
    per_level: list = field(default_factory=list)


LAST_REPORT = AnytimeReport()


def plan(start: Pose, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle],
         bounds: Bounds, params=None) -> PlanResult:
    global LAST_REPORT
    t0 = time.perf_counter()
    p = AnytimeParams()
    if params is not None:
        tl = getattr(params, "time_limit", None)
        if tl is not None:
            p.time_limit = float(tl)
        for name in ("safety_margin", "steer_ratio", "cruise_speed", "approach_speed",
                     "approach_distance"):
            v = getattr(params, name, None)
            if v is not None:
                setattr(p, name, float(v))
    rep = AnytimeReport()
    LAST_REPORT = rep

    goal_true = check_pose(cfg, goal, obstacles, bounds)
    if not goal_true.ok:
        return PlanResult("GOAL_INVALID", "Đích không hợp lệ: " + goal_true.describe())
    start_true = check_pose(cfg, start, obstacles, bounds)
    if not start_true.ok:
        return PlanResult("START_INVALID", "Xuất phát không hợp lệ: " + start_true.describe())

    margin = min(p.safety_margin, goal_true.min_clearance / 2, start_true.min_clearance / 2)
    margin = max(margin, 0.0)

    ctx = _Ctx(cfg, obstacles, bounds, margin, p)
    deadline_all = t0 + p.time_limit
    levels = _default_levels()

    best_raw = None
    best_cost = _INF
    total_pop = total_exp = 0
    exhausted_all = True
    last_status = "NO_PATH"

    for li, lv in enumerate(levels):
        now = time.perf_counter()
        if now >= deadline_all:
            break
        if best_raw is not None:
            # đã có nghiệm: chỉ còn cải thiện trong ngân sách ngắn
            if now - rep.first_solution_time_abs > p.refine_after_first:
                break
        remain = deadline_all - now
        if best_raw is None:
            cap = lv.cap if lv.cap > 0 else -lv.cap * remain
            cap = max(0.05, min(remain, cap))
            if li == len(levels) - 1:
                cap = remain
        else:
            # đã có nghiệm: mỗi mức chỉ được một lát mỏng, để quét được nhiều mức
            cap = min(remain, p.refine_slice)
        sub_deadline = now + cap

        q_a, q_b = (goal, start) if lv.backward else (start, goal)
        # Gợi ý từ nghiệm thô: nút nằm trong "hành lang" quanh đường cũ được giảm
        # nhẹ f, nên mức mịn đi lại vết cũ rất nhanh rồi mới toả ra chỗ khác.
        corridor = _corridor_of(best_raw) if best_raw is not None else None
        raw, cost, pops, exps, st = _search(ctx, q_a, q_b, lv, sub_deadline,
                                            best_cost * 1.02 if best_raw is not None else _INF,
                                            corridor)
        total_pop += pops
        total_exp += exps
        rep.levels_run += 1
        rep.per_level.append((li, st, round(time.perf_counter() - now, 3), pops))
        if st != "EXHAUSTED":
            exhausted_all = False
        last_status = st
        if raw is None:
            continue
        if lv.backward:
            raw = _reverse_raw(raw)
        raw = _polish(ctx, raw, goal)
        if not _validate(cfg, raw, obstacles, bounds):
            continue
        c = _path_cost(raw, p)
        if c < best_cost:
            best_cost = c
            best_raw = raw
            if rep.first_solution_level < 0:
                rep.first_solution_level = li
                rep.first_solution_time = time.perf_counter() - t0
                rep.first_solution_time_abs = time.perf_counter()
                rep.first_length = _raw_length(raw)
                rep.first_cusps = _raw_cusps(raw)
            else:
                rep.improved += 1
            rep.final_level = li
            rep.final_length = _raw_length(raw)
            rep.final_cusps = _raw_cusps(raw)

    elapsed = time.perf_counter() - t0
    if best_raw is None:
        status = "NO_PATH" if exhausted_all else "TIMEOUT"
        msg = ("Vét cạn không gian tìm kiếm ở mọi độ phân giải"
               if exhausted_all else f"Hết ngân sách {elapsed:.1f} s ({last_status})")
        return PlanResult(status, msg, None, elapsed, total_exp, total_pop, 0, margin)

    traj = build_trajectory(best_raw, goal, cfg, p.cruise_speed, p.approach_speed,
                            p.approach_distance)
    msg = (f"dài {traj.length:.2f} m, {traj.n_cusps} lần đổi chiều; "
           f"nghiệm đầu {rep.first_solution_time:.2f} s ở mức {rep.first_solution_level}, "
           f"chốt ở mức {rep.final_level}")
    return PlanResult("OK", msg, traj, elapsed, total_exp, total_pop, 0, margin)
