"""Ứng viên "Hybrid A* làm cho đúng".

Giữ nguyên khung Hybrid A* của `hybrid_astar.py` nhưng sửa hết các điểm yếu đã đo
được trên bộ ca khó.

1. VA CHẠM. Dùng `FastCollisionChecker` giải tích (SAT hai hình chữ nhật) thay cho
   bản Shapely, và đi dọc đường Reeds-Shepp bằng số thực thuần (không dựng đối
   tượng Pose) với một lượt lọc thô trước. Bản cũ ngốn 61% thời gian ở va chạm;
   ở đây riêng việc dựng sẵn toàn bộ mẫu rồi mới kiểm tra từng chiếm 77% và đã bỏ.

2. RỜI RẠC HOÁ THEO ĐỘ HỞ. Đây là chỗ quyết định. Đo trên `parallel_135`: xe nằm
   trong ô đỗ chỉ nhúc nhích được 4,4 cm dọc trục và mỗi vòng đẩy tới-lui chỉ ăn
   ra khoảng 5 mm ngang. Chạy tìm kiếm rộng thuần từ tư thế đích cho thấy ngưỡng
   rất gắt: ô lưới 6 mm thì xe kẹt cứng (39 trạng thái, xoay tối đa 10 độ), ô lưới
   5 mm với bước 4 cm thì thoát hẳn ra đường (hơn 400.000 trạng thái, xoay 117 độ).
   Một lưới đều 5 mm cho cả sa bàn thì nổ, nên lưới ở đây chia BA MỨC theo độ hở
   quanh tâm trục sau: chỗ ngặt 5 mm/2 độ, chỗ vừa 2 cm/4 độ, chỗ thoáng 4 cm/8 độ,
   bước mở rộng cũng đổi theo. Mức được quyết định bởi ô 4 cm chứa điểm nên khoá
   trạng thái vẫn nhất quán. Thêm luật "không nở được nút nào thì thử lại bằng
   bước tí hon" cho các tư thế chỉ còn 1-2 cm dư địa.

3. REEDS-SHEPP ĐẦY ĐỦ. `cand_hybrid_fast_rs.py` có cả 48 từ đường (thêm CCCC,
   CCSC, CCSCC). Đo trên 1500 cặp tư thế ngẫu nhiên: ngắn hơn bản 16 từ ở 56% số
   ca, trung bình 0,34 R; và bản 16 từ có 2% số ca không sinh nổi ứng viên nào.

4. HEURISTIC. Dựng sẵn hai bảng rồi lấy max:
   - Dijkstra 2D có vật cản (numpy, quét Jacobi, không dùng Shapely);
   - độ dài Reeds-Shepp không vật cản cho MỌI ô lưới và mọi hướng, tính một lần
     bằng numpy (~3 us/điểm) thay vì gọi lại ở từng nút và chỉ trong bán kính 1,5 m.

5. HAI CHIỀU TÌM KIẾM. Đầu ngặt hơn được chọn làm điểm XUẤT PHÁT của tìm kiếm, để
   cú nối giải tích Reeds-Shepp rơi vào đầu thoáng hơn. Đo trên `pillar_at_slot_mouth`:
   tìm xuôi hết 20 s không xong, tìm ngược xong trong 0,28 giây với 20 nút.

6. ĐÍCH ĐÚNG LÀ ĐÍCH. Dung sai nhận đích trên lưới đặt rất chặt (1,5 cm / 2 độ);
   đường hợp lệ gần như luôn kết thúc bằng cung Reeds-Shepp rơi đúng vào đích.
   Bản đầu tiên nhận đích ở 3 cm/3 độ và vì thế `parallel_135` lập được đường
   nhưng bám hỏng: một mình sai số của quy hoạch đã ăn 2,8 cm trong ngân sách 5 cm.

Giao diện: `plan(start, goal, cfg, obstacles, bounds, params=None) -> PlanResult`.
`PlanResult`, `build_trajectory`, `check_pose`, `check_motion` lấy nguyên từ các
module dùng chung; file này không sửa gì của chúng.
"""
from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass

import numpy as np

from autopark.domain.types import Bounds, Obstacle, Pose, VehicleConfig, wrap_angle
from autopark.geometry.fast_collision import FastCollisionChecker
from autopark.geometry.footprint import check_motion, check_pose
from autopark.planning import cand_hybrid_fast_rs as rs
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.trajectory import build_trajectory

_PI = math.pi
_TWO_PI = 2.0 * math.pi


@dataclass
class FastParams:
    # --- rời rạc hoá: hai "nấc" thử lần lượt, mỗi nấc lại chia ba mức theo độ hở
    #     quanh tâm trục sau. Ô lưới mức k = base_res * cell_factor[k]; các thừa số
    #     phải là ước của tier_factor để nhãn ô luôn nhất quán giữa các mức.
    #     Nấc thô đủ cho gần hết bộ ca và chạy nhanh; nấc mịn (ô 5 mm) chỉ dùng khi
    #     nấc thô bó tay, vì chỉ các ô đỗ song song mới cần tới nó.
    profiles: tuple = (
        # base_res, tier_factor, cell_factor, yaw_bins, yaw_factor, tier_step, tier_clearance, weight
        (0.025, 2, (1, 1, 2), 72, (1, 1, 2), (0.040, 0.040, 0.100), (0.12, 0.26), 1.0),
        (0.012, 4, (1, 2, 4), 120, (1, 2, 2), (0.025, 0.030, 0.090), (0.12, 0.26), 1.5),
        (0.005, 8, (1, 4, 8), 180, (1, 2, 4), (0.040, 0.030, 0.090), (0.12, 0.26), 2.5),
    )
    tiny_step: float = 0.015             # dùng lại khi một nút không nở được gì

    n_steer: int = 7
    steer_ratio: float = 0.85

    # --- giá
    reverse_cost: float = 1.10
    switch_cost: float = 0.30
    steer_cost: float = 0.10
    steer_change_cost: float = 0.15
    heuristic_weight: float = 1.6

    # --- an toàn và đích
    safety_margin: float = 0.03          # đúng quy tắc của hybrid_astar.py
    goal_xy_tol: float = 0.015
    goal_yaw_tol: float = math.radians(2.0)
    goal_near: float = 0.10
    goal_near_yaw: float = math.radians(25.0)

    # --- heuristic
    dij_resolution: float = 0.03
    rs_table_yaw_bins: int = 24
    rs_table_budget: int = 60_000

    # --- nối đích bằng Reeds-Shepp
    rs_every: int = 4
    rs_max_candidates: int = 8
    rs_sample_step: float = 0.02
    rs_length_factor: float = 4.0
    rs_min_segment: float = 0.05         # m: mọi đoạn cùng chiều của cú nối phải dài hơn
    rs_min_last: float = 0.10            # m: đoạn cùng chiều CUỐI phải dài hơn nữa
    rs_short_penalty: float = 1.50       # m tương đương, khi đã phải chấp nhận đoạn ngắn

    # --- hai chiều tìm kiếm
    two_way: bool = True
    first_share: float = 0.55            # phần thời gian dành cho chiều ưu tiên

    # --- kết quả
    path_sample_step: float = 0.02
    max_nodes: int = 4_000_000
    time_limit: float = 8.0
    cruise_speed: float = 0.15
    approach_speed: float = 0.08
    approach_distance: float = 0.30


# --------------------------------------------------------------------------- lưới trợ giúp

def _rect_dist2(X, Y, o: Obstacle):
    """Bình phương khoảng cách từ các điểm lưới tới hình chữ nhật có hướng `o`."""
    c, s = math.cos(o.yaw), math.sin(o.yaw)
    dx = X - o.cx
    dy = Y - o.cy
    px = np.abs(c * dx + s * dy) - o.width / 2.0
    py = np.abs(-s * dx + c * dy) - o.height / 2.0
    np.maximum(px, 0.0, out=px)
    np.maximum(py, 0.0, out=py)
    return px * px + py * py


def _grid_axes(bounds: Bounds, res: float):
    nx = max(1, int(math.ceil(bounds.width / res)))
    ny = max(1, int(math.ceil(bounds.height / res)))
    xs = bounds.xmin + (np.arange(nx) + 0.5) * res
    ys = bounds.ymin + (np.arange(ny) + 0.5) * res
    return nx, ny, xs[:, None], ys[None, :]


def _clearance_field(bounds: Bounds, obstacles: list[Obstacle], res: float):
    """Khoảng cách từ tâm mỗi ô tới vật cản/mép sa bàn gần nhất, đã trừ nửa đường chéo ô."""
    nx, ny, X, Y = _grid_axes(bounds, res)
    d = np.empty((nx, ny), dtype=float)
    d[:] = np.minimum(X - bounds.xmin, bounds.xmax - X)
    np.minimum(d, Y - bounds.ymin, out=d)
    np.minimum(d, bounds.ymax - Y, out=d)
    for o in obstacles:
        np.minimum(d, np.sqrt(_rect_dist2(X, Y, o)), out=d)
    return nx, ny, np.maximum(d - 0.5 * res * math.sqrt(2.0), 0.0)


def _dijkstra2d(goal: Pose, bounds: Bounds, obstacles: list[Obstacle], res: float, inflate: float):
    """Khoảng cách 2D tới đích trên lưới 8 hướng; ô bị chặn đi được nhưng đắt gấp 4.

    Quét kiểu Jacobi bằng numpy: mỗi vòng lan một ô, dừng khi không đổi nữa.
    """
    nx, ny, X, Y = _grid_axes(bounds, res)
    blocked = np.zeros((nx, ny), dtype=bool)
    blocked |= (X < bounds.xmin + inflate) | (X > bounds.xmax - inflate)
    blocked |= (Y < bounds.ymin + inflate) | (Y > bounds.ymax - inflate)
    r2 = inflate * inflate
    for o in obstacles:
        blocked |= _rect_dist2(X, Y, o) <= r2
    w = np.where(blocked, 4.0, 1.0)          # giá để ĐI VÀO ô
    d = np.full((nx, ny), 1e9)
    gi = min(max(int((goal.x - bounds.xmin) / res), 0), nx - 1)
    gj = min(max(int((goal.y - bounds.ymin) / res), 0), ny - 1)
    d[gi, gj] = 0.0
    diag = res * math.sqrt(2.0)
    steps = ((1, 0, res), (-1, 0, res), (0, 1, res), (0, -1, res),
             (1, 1, diag), (1, -1, diag), (-1, 1, diag), (-1, -1, diag))
    cost = [(di, dj, st * w) for di, dj, st in steps]
    for _ in range(nx + ny + 8):
        prev = d
        cur = d.copy()
        for di, dj, c in cost:
            si = slice(max(di, 0), nx + min(di, 0))
            sj = slice(max(dj, 0), ny + min(dj, 0))
            ti = slice(max(-di, 0), nx + min(-di, 0))
            tj = slice(max(-dj, 0), ny + min(-dj, 0))
            np.minimum(cur[si, sj], prev[ti, tj] + c[si, sj], out=cur[si, sj])
        if np.array_equal(cur, d):
            break
        d = cur
    return nx, ny, d


def _rs_table(goal: Pose, bounds: Bounds, maxc: float, res: float, n_yaw: int):
    """Độ dài Reeds-Shepp không vật cản từ (ô lưới, hướng) tới đích, đơn vị mét."""
    nx, ny, X, Y = _grid_axes(bounds, res)
    bin_w = _TWO_PI / n_yaw
    yaws = -_PI + (np.arange(n_yaw) + 0.5) * bin_w
    dx = (goal.x - X)[:, :, None]
    dy = (goal.y - Y)[:, :, None]
    c = np.cos(yaws)[None, None, :]
    s = np.sin(yaws)[None, None, :]
    xn = (dx * c + dy * s) * maxc
    yn = (-dx * s + dy * c) * maxc
    phi = goal.yaw - yaws
    phi = phi - _TWO_PI * np.rint(phi / _TWO_PI)
    return nx, ny, rs.length_grid(xn, yn, np.broadcast_to(phi[None, None, :], xn.shape)) / maxc


# --------------------------------------------------------------------------- tiện ích

def _resolve_params(params) -> FastParams:
    if isinstance(params, FastParams):
        return params
    p = FastParams()
    if params is not None:
        tl = getattr(params, "time_limit", None)
        if tl is not None:
            p.time_limit = float(tl)
    return p


def _steer_of(mode: str, max_steer: float) -> float:
    return max_steer if mode == "L" else (-max_steer if mode == "R" else 0.0)


def _rel_move(step: float, steer: float, wheelbase: float) -> tuple[float, float, float]:
    """Dịch chuyển tương đối trong hệ xe sau khi đi cung dài `step` (có dấu) với góc lái `steer`."""
    if abs(steer) < 1e-12:
        return step, 0.0, 0.0
    k = math.tan(steer) / wheelbase
    dth = step * k
    r = 1.0 / k
    return r * math.sin(dth), r * (1.0 - math.cos(dth)), dth


def _reverse_raw(raw: list[tuple[Pose, int, float]]) -> list[tuple[Pose, int, float]]:
    """Đảo chiều một đường: đi cung nào ngược lại cũng đúng cung ấy, chỉ đổi dấu chiều.

    Quy ước của `build_trajectory`: phần tử i mang (chiều, góc lái) của CUNG DẪN
    TỚI tư thế i, riêng phần tử 0 mượn của cung 1. Đảo lại thì cung dẫn tới tư thế
    i-1 của đường mới chính là cung i của đường cũ, chạy ngược.
    """
    n = len(raw) - 1
    if n <= 0:
        return list(raw)
    ds = [(-d, st) for _, d, st in raw]
    out = [(raw[n][0], ds[n][0], ds[n][1])]
    for k in range(1, n + 1):
        out.append((raw[n - k][0], ds[n - k + 1][0], ds[n - k + 1][1]))
    return out


# --------------------------------------------------------------------------- nối đích

def _runs(lengths) -> list[float]:
    """Độ dài các đoạn CÙNG CHIỀU (đã gộp các cung liền nhau cùng dấu).

    `build_trajectory` chỉ cắt đoạn theo chiều tiến/lùi, nên hai cung liền nhau
    cùng dấu là một đoạn liền mạch; chỉ chỗ đổi dấu mới bắt xe dừng hẳn rồi chỉnh
    lái, và mỗi lần như thế là một lần bộ bám tích thêm sai số hướng. Đo trên
    `pillar_at_slot_mouth`: cú nối kết thúc bằng ba đoạn 4 cm làm sai số hướng
    cuối cùng là 5,9 độ, vượt dung sai 5 độ, dù đường đi qua hết mọi kiểm tra.
    """
    out: list[float] = []
    total = 0.0
    sign = 0
    for v in lengths:
        a = v if v >= 0.0 else -v
        if a < 1e-12:
            continue
        sg = 1 if v > 0.0 else -1
        if sg != sign:
            if sign != 0:
                out.append(total)
            sign, total = sg, a
        else:
            total += a
    if sign != 0:
        out.append(total)
    return out


def _walk_ok(q0: Pose, path, maxc: float, step: float, pose_ok) -> bool:
    """Đi dọc đường Reeds-Shepp bằng số thực thuần, dừng ngay khi chạm."""
    ox, oy, oyaw = q0.x, q0.y, q0.yaw
    inv = 1.0 / maxc
    span = step * maxc
    for l, m in zip(path.lengths, path.ctypes):
        al = l if l >= 0.0 else -l
        if al < 1e-12:
            continue
        n = int(al / span) + 1
        c0 = math.cos(oyaw)
        s0 = math.sin(oyaw)
        if m == "S":
            d = l * inv / n
            ux, uy = c0 * d, s0 * d
            x, y = ox, oy
            for _ in range(n):
                x += ux
                y += uy
                if not pose_ok(x, y, oyaw):
                    return False
            ox, oy = x, y
        else:
            sgn = 1.0 if m == "L" else -1.0
            x = y = 0.0
            yaw = oyaw
            for k in range(1, n + 1):
                pk = l * k / n
                ldx = math.sin(pk) * inv
                ldy = sgn * (1.0 - math.cos(pk)) * inv
                x = ox + c0 * ldx - s0 * ldy
                y = oy + s0 * ldx + c0 * ldy
                yaw = oyaw + sgn * pk
                if not pose_ok(x, y, yaw):
                    return False
            ox, oy, oyaw = x, y, yaw
    return True


def _try_rs(q0: Pose, goal: Pose, maxc: float, max_steer: float, pose_ok, p: FastParams,
            stats: dict, strict: int = 2):
    """Thử nối q0 -> goal bằng Reeds-Shepp đầy đủ, có kiểm tra va chạm dọc đường."""
    stats["rs_tries"] += 1
    x, y, phi = rs.normalized_goal(q0, goal, maxc)
    cands = rs.raw_candidates(x, y, phi)
    if not cands:
        return None
    straight = math.hypot(goal.x - q0.x, goal.y - q0.y)
    cap = straight * p.rs_length_factor * maxc + 2.0
    pen = p.switch_cost * maxc
    min_seg = p.rs_min_segment * maxc
    min_last = p.rs_min_last * maxc
    short_pen = p.rs_short_penalty * maxc
    keep = []
    for c in cands:
        if c.length > cap:
            continue
        runs = _runs(c.lengths)
        n_short = sum(1 for r in runs if r < min_seg)
        last_short = 1 if runs and runs[-1] < min_last else 0
        bad = n_short + last_short
        # strict = 2: mọi đoạn phải đủ dài; = 1: chỉ đòi đoạn CUỐI đủ dài; = 0: không lọc
        if (strict >= 2 and bad) or (strict == 1 and last_short):
            continue
        keep.append((c.length + c.n_cusps * pen + bad * short_pen, c))
    keep.sort(key=lambda t: t[0])
    coarse = p.rs_sample_step * 3.0
    tried = 0
    for _, path in keep:
        if tried >= p.rs_max_candidates:
            break
        if not rs.verify(q0, goal, path, maxc):
            continue
        tried += 1
        if not _walk_ok(q0, path, maxc, coarse, pose_ok):
            continue
        if not _walk_ok(q0, path, maxc, p.rs_sample_step, pose_ok):
            continue
        samples = rs.sample_path(q0, path, maxc, p.rs_sample_step)
        return [(pose, d, _steer_of(m, max_steer)) for pose, d, m in samples[1:]]
    return None


def _run_bounds(raw) -> list[int]:
    """Chỉ số các mốc đổi chiều trong đường thô (kể cả điểm đầu và điểm cuối)."""
    idx = [0]
    for i in range(1, len(raw)):
        if raw[i][1] != raw[i - 1][1]:
            idx.append(i - 1)
    idx.append(len(raw) - 1)
    return idx


def _arc_len(raw, a: int, b: int) -> float:
    t = 0.0
    for i in range(a, b):
        pa, pb = raw[i][0], raw[i + 1][0]
        t += math.hypot(pb.x - pa.x, pb.y - pa.y)
    return t


def _polish_tail(raw, goal: Pose, maxc: float, max_steer: float, pose_ok, p: FastParams,
                 stats: dict):
    """Thay đoạn cuối của đường bằng một cung Reeds-Shepp "sạch" nếu nối được.

    Khi tìm kiếm chạy NGƯỢC, mấy nhịp đẩy tí hon để chui ra khỏi ô đỗ nằm ở đầu
    đường tìm kiếm, và sau khi đảo lại chúng thành đoạn TIẾP CẬN ĐÍCH - đúng chỗ
    bộ bám cần đường dài để triệt sai số hướng. Đo trên `pillar_at_slot_mouth`:
    ba đoạn 4 cm cuối làm sai số hướng dừng ở 5,9 độ.
    """
    idx = _run_bounds(raw)
    if len(idx) < 3:
        return raw
    min_run = p.rs_min_segment
    short_before = sum(1 for k in range(len(idx) - 1)
                       if _arc_len(raw, idx[k], idx[k + 1]) < min_run)
    if short_before == 0 and _arc_len(raw, idx[-2], idx[-1]) >= p.rs_min_last:
        return raw
    total = _arc_len(raw, 0, len(raw) - 1)
    for level, k in [(lv, kk) for lv in (2, 1) for kk in range(len(idx) - 2, max(-1, len(idx) - 8), -1)]:
        i = idx[k]
        tail = _try_rs(raw[i][0], goal, maxc, max_steer, pose_ok, p, stats, strict=level)
        if tail is None:
            continue
        cand = raw[:i + 1] + tail
        jdx = _run_bounds(cand)
        short_after = sum(1 for m in range(len(jdx) - 1)
                          if _arc_len(cand, jdx[m], jdx[m + 1]) < min_run)
        if short_after < short_before or (short_after == 0 and short_before == 0):
            if _arc_len(cand, 0, len(cand) - 1) <= total + 0.60:
                return cand
    return raw


# --------------------------------------------------------------------------- tìm kiếm

def _search(start: Pose, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle],
            bounds: Bounds, p: FastParams, checker: FastCollisionChecker, margin: float,
            maxc: float, max_steer: float, deadline: float, forward: bool, stats: dict,
            prof, cache: dict, strict: int = 2):
    """Hybrid A* một chiều với một nấc rời rạc hoá. Trả (raw_path|None, status, message)."""
    pose_ok = checker.pose_ok
    r0, tier_factor, cell_factor, base_yaw_bins, yaw_factor, tier_step, tier_clearance, _w = prof

    # ---------------- heuristic (dùng lại giữa các lần thử cùng đích)
    ck = (round(goal.x, 6), round(goal.y, 6), round(goal.yaw, 6))
    if ck in cache:
        nxd, nyd, dij_flat, nxh, nyh, n_yaw_h, h_res, rs_flat = cache[ck]
    else:
        inflate = min(cfg.width / 2, cfg.rear_overhang) + margin
        nxd, nyd, dij = _dijkstra2d(goal, bounds, obstacles, p.dij_resolution, inflate)
        dij_flat = dij.ravel().tolist()
        area = bounds.width * bounds.height
        cells = max(64, p.rs_table_budget // p.rs_table_yaw_bins)
        h_res = max(p.dij_resolution, math.sqrt(area / cells))
        n_yaw_h = p.rs_table_yaw_bins
        nxh, nyh, rstab = _rs_table(goal, bounds, maxc, h_res, n_yaw_h)
        slack = 0.5 * h_res * math.sqrt(2.0) + (_PI / n_yaw_h) / maxc
        rs_flat = np.maximum(rstab - slack, 0.0).ravel().tolist()
        cache[ck] = (nxd, nyd, dij_flat, nxh, nyh, n_yaw_h, h_res, rs_flat)

    # ---------------- mức rời rạc hoá theo độ hở
    tier_res = r0 * tier_factor
    tk = ("clr", round(tier_res, 6))
    if tk in cache:
        nxt, nyt, clr = cache[tk]
    else:
        nxt, nyt, clr = _clearance_field(bounds, obstacles, tier_res)
        cache[tk] = (nxt, nyt, clr)
    c0, c1 = tier_clearance
    tier_grid = np.where(clr < c0, 0, np.where(clr < c1, 1, 2)).ravel().tolist()

    # ---------------- nguyên hàm chuyển động
    n = max(3, p.n_steer | 1)
    steer_set = [-max_steer + i * (2 * max_steer / (n - 1)) for i in range(n)]
    rev_dir = -1 if forward else 1        # chiều bị tính giá đắt (sẽ là "lùi" của đường cuối)

    def make_prims(step: float):
        n_check = max(2, int(math.ceil(step / 0.03)))
        n_fine = max(1, int(math.ceil(step / p.path_sample_step)))
        out = []
        for direction in (1, -1):
            for steer in steer_set:
                s = direction * step
                end = _rel_move(s, steer, cfg.wheelbase)
                checks = tuple(_rel_move(s * k / n_check, steer, cfg.wheelbase)
                               for k in range(n_check - 1, 0, -1))
                fine = tuple(_rel_move(s * k / n_fine, steer, cfg.wheelbase)
                             for k in range(1, n_fine + 1))
                base = step * (p.reverse_cost if direction == rev_dir else 1.0)
                base += p.steer_cost * abs(steer) * step
                out.append((direction, steer, base, end, checks, fine))
        return out

    prims = []
    blocks = []                            # (lo, hi) cho từng mức, phần tử cuối là bước tí hon
    for step in tuple(tier_step) + (p.tiny_step,):
        lo = len(prims)
        prims.extend(make_prims(step))
        blocks.append((lo, len(prims)))
    prims = tuple(prims)
    tiny_lo, tiny_hi = blocks[-1]

    # ---------------- chỉ số ô lưới
    xmin, ymin = bounds.xmin, bounds.ymin
    inv0 = 1.0 / r0
    inv_t = 1.0 / tier_res
    nk0 = base_yaw_bins
    inv_yaw0 = nk0 / _TWO_PI
    ncy = int(bounds.height * inv0) + 2
    qcell = tuple(cell_factor)
    qyaw = tuple(yaw_factor)
    inv_d = 1.0 / p.dij_resolution
    inv_h = 1.0 / h_res
    inv_yh = n_yaw_h / _TWO_PI
    w_h = p.heuristic_weight

    def tier_of(x: float, y: float) -> int:
        i = int((x - xmin) * inv_t)
        j = int((y - ymin) * inv_t)
        if i < 0:
            i = 0
        elif i >= nxt:
            i = nxt - 1
        if j < 0:
            j = 0
        elif j >= nyt:
            j = nyt - 1
        return tier_grid[i * nyt + j]

    def gkey(x: float, y: float, yaw: float, direction: int, t: int) -> int:
        i = int((x - xmin) * inv0)
        j = int((y - ymin) * inv0)
        k = int((yaw + _PI) * inv_yaw0)
        if k >= nk0:
            k -= nk0
        elif k < 0:
            k += nk0
        q = qcell[t]
        if q > 1:
            i -= i % q
            j -= j % q
            qy = qyaw[t]
            k -= k % qy
        return (((i * ncy + j) * nk0 + k) << 2) | ((1 if direction > 0 else 0) << 1)

    def hval(x: float, y: float, yaw: float) -> float:
        i = int((x - xmin) * inv_d)
        j = int((y - ymin) * inv_d)
        if i < 0:
            i = 0
        elif i >= nxd:
            i = nxd - 1
        if j < 0:
            j = 0
        elif j >= nyd:
            j = nyd - 1
        h = dij_flat[i * nyd + j]
        i = int((x - xmin) * inv_h)
        j = int((y - ymin) * inv_h)
        if i < 0:
            i = 0
        elif i >= nxh:
            i = nxh - 1
        if j < 0:
            j = 0
        elif j >= nyh:
            j = nyh - 1
        k = int((yaw + _PI) * inv_yh)
        if k < 0:
            k = 0
        elif k >= n_yaw_h:
            k = n_yaw_h - 1
        r = rs_flat[(i * nyh + j) * n_yaw_h + k]
        return w_h * (h if h > r else r)

    # ---------------- A*
    t_start = tier_of(start.x, start.y)
    nodes: list[tuple] = [(start.x, start.y, start.yaw, 0, 0.0, 0.0, -1, -1)]
    best: dict[int, float] = {}
    closed: set[int] = set()
    heap: list[tuple[float, int, int]] = [(hval(start.x, start.y, start.yaw), 0, 0)]
    counter = 1
    popped = expanded = 0
    best_h = 1e18
    raw_path = None
    status = "NO_PATH"
    message = "Không tìm được đường trong không gian tìm kiếm"

    goal_xy2 = p.goal_xy_tol * p.goal_xy_tol
    goal_yaw_tol = p.goal_yaw_tol
    goal_near2 = p.goal_near * p.goal_near
    goal_near_yaw = p.goal_near_yaw
    gx, gy, gyaw = goal.x, goal.y, goal.yaw
    rs_every = p.rs_every
    max_nodes = p.max_nodes
    switch_cost = p.switch_cost
    steer_change_cost = p.steer_change_cost
    heappush = heapq.heappush
    heappop = heapq.heappop

    while heap:
        _, _, nid = heappop(heap)
        x, y, yaw, ndir, nsteer, g, _parent, _prim = nodes[nid]
        t_here = tier_of(x, y)
        k = gkey(x, y, yaw, ndir, t_here)
        if k in closed:
            continue
        closed.add(k)
        popped += 1

        if (popped & 31) == 0:
            if time.perf_counter() > deadline:
                status = "TIMEOUT"
                message = f"Quá giới hạn thời gian ({popped} nút)"
                break
            if popped > max_nodes:
                status = "TIMEOUT"
                message = f"Quá giới hạn số nút ({popped})"
                break

        dxg = gx - x
        dyg = gy - y
        d2 = dxg * dxg + dyg * dyg
        dyawg = wrap_angle(yaw - gyaw)

        h_here = hval(x, y, yaw)
        fresh = h_here < best_h - 0.005
        if fresh:
            best_h = h_here
        if fresh or (popped % rs_every) == 0 or (d2 < goal_near2 and abs(dyawg) < goal_near_yaw):
            tail = _try_rs(Pose(x, y, yaw), goal, maxc, max_steer, pose_ok, p, stats, strict)
            if tail is not None:
                raw_path = _reconstruct(nodes, nid, prims) + tail
                break

        if d2 < goal_xy2 and abs(dyawg) < goal_yaw_tol:
            raw_path = _reconstruct(nodes, nid, prims)
            break

        c = math.cos(yaw)
        s = math.sin(yaw)
        lo, hi = blocks[t_here]
        n_free = 0
        for attempt in (0, 1):
            for pi in range(lo, hi):
                direction, steer, base, end, checks, _fine = prims[pi]
                dx, dy, dth = end
                px = x + c * dx - s * dy
                py = y + s * dx + c * dy
                pyaw = yaw + dth
                if not pose_ok(px, py, pyaw):
                    continue
                ok = True
                for dx, dy, dth in checks:
                    if not pose_ok(x + c * dx - s * dy, y + s * dx + c * dy, yaw + dth):
                        ok = False
                        break
                if not ok:
                    continue
                n_free += 1
                if pyaw > _PI:
                    pyaw -= _TWO_PI
                elif pyaw < -_PI:
                    pyaw += _TWO_PI
                nk = gkey(px, py, pyaw, direction, tier_of(px, py))
                if nk in closed:
                    continue
                cost = base + steer_change_cost * abs(steer - nsteer)
                if ndir != 0 and direction != ndir:
                    cost += switch_cost
                ng = g + cost
                if ng >= best.get(nk, 1e18):
                    continue
                best[nk] = ng
                nodes.append((px, py, pyaw, direction, steer, ng, nid, pi))
                heappush(heap, (ng + hval(px, py, pyaw), counter, len(nodes) - 1))
                counter += 1
                expanded += 1
            # Tư thế chỉ còn 1-2 cm dư địa: bước thường không đi nổi, thử bước tí hon
            if n_free or attempt or lo == tiny_lo:
                break
            lo, hi = tiny_lo, tiny_hi

    stats["popped"] += popped
    stats["expanded"] += expanded
    return raw_path, status, message


def _reconstruct(nodes: list[tuple], nid: int, prims) -> list[tuple[Pose, int, float]]:
    chain = []
    while nid >= 0:
        chain.append(nodes[nid])
        nid = nodes[nid][6]
    chain.reverse()
    first_dir = chain[1][3] if len(chain) > 1 else 1
    first_steer = chain[1][4] if len(chain) > 1 else 0.0
    out: list[tuple[Pose, int, float]] = [(Pose(chain[0][0], chain[0][1], chain[0][2]),
                                           first_dir, first_steer)]
    for prev, node in zip(chain, chain[1:]):
        px, py, pyaw = prev[0], prev[1], prev[2]
        c = math.cos(pyaw)
        s = math.sin(pyaw)
        direction, steer = node[3], node[4]
        for dx, dy, dth in prims[node[7]][5]:
            out.append((Pose(px + c * dx - s * dy, py + s * dx + c * dy, wrap_angle(pyaw + dth)),
                        direction, steer))
    return out


# --------------------------------------------------------------------------- điểm vào

def plan(start: Pose, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle], bounds: Bounds,
         params=None) -> PlanResult:
    t0 = time.perf_counter()
    p = _resolve_params(params)
    stats = {"popped": 0, "expanded": 0, "rs_tries": 0}

    goal_chk = check_pose(cfg, goal, obstacles, bounds)
    if not goal_chk.ok:
        return PlanResult("GOAL_INVALID", "Đích không hợp lệ: " + goal_chk.describe(),
                          elapsed=time.perf_counter() - t0)
    start_chk = check_pose(cfg, start, obstacles, bounds)
    if not start_chk.ok:
        return PlanResult("START_INVALID", "Xuất phát không hợp lệ: " + start_chk.describe(),
                          elapsed=time.perf_counter() - t0)

    # Lề an toàn theo đúng quy tắc của hybrid_astar.py (không được nới lỏng hơn)
    margin = max(0.0, min(p.safety_margin, goal_chk.min_clearance / 2, start_chk.min_clearance / 2))
    checker = FastCollisionChecker(cfg, obstacles, bounds, margin)
    max_steer = cfg.max_steer * p.steer_ratio
    maxc = math.tan(max_steer) / cfg.wheelbase

    # 1) nối thẳng bằng Reeds-Shepp ngay từ xuất phát (ca dễ xong trong ~1 ms)
    tail = _try_rs(start, goal, maxc, max_steer, checker.pose_ok, p, stats)
    if tail is not None:
        raw = [(start, tail[0][1], tail[0][2])] + tail
        return _finish(raw, goal, cfg, obstacles, bounds, p, t0, stats, margin)

    # 2) tìm kiếm. Thứ tự thử: đầu NGẶT hơn được lấy làm điểm xuất phát của tìm
    #    kiếm để cú nối giải tích Reeds-Shepp rơi vào đầu thoáng hơn; và nấc rời
    #    rạc hoá thô chạy trước, nấc mịn chỉ dùng khi nấc thô bó tay.
    goal_first = goal_chk.min_clearance <= start_chk.min_clearance
    dirs = [(goal, start, False), (start, goal, True)] if goal_first else            [(start, goal, True), (goal, start, False)]
    if not p.two_way:
        dirs = [(start, goal, True)]
    attempts = []
    for prof in p.profiles:
        for a, b, forward in dirs:
            attempts.append((a, b, forward, prof, prof[7], 2))
    # Lượt cuối nới điều kiện "đoạn phải đủ dài" của cú nối Reeds-Shepp: thà có
    # đường mà bộ bám hơi lệch còn hơn không có đường nào.
    a, b, forward = dirs[0]
    attempts.append((a, b, forward, p.profiles[-1], 1.0, 0))

    end_all = t0 + p.time_limit
    cache: dict = {}
    status, message = "NO_PATH", "Không tìm được đường trong không gian tìm kiếm"
    left = sum(t[4] for t in attempts)
    for a, b, forward, prof, w, strict in attempts:
        now = time.perf_counter()
        if now >= end_all - 0.05:
            break
        deadline = now + (end_all - now) * (w / left)
        left -= w
        raw, st, msg = _search(a, b, cfg, obstacles, bounds, p, checker, margin,
                               maxc, max_steer, deadline, forward, stats, prof, cache, strict)
        if raw is not None:
            if not forward:
                raw = _reverse_raw(raw)
            res = _finish(raw, goal, cfg, obstacles, bounds, p, t0, stats, margin,
                          (maxc, max_steer, checker.pose_ok))
            if res.ok:
                return res
            status, message = res.status, res.message
        elif st == "TIMEOUT" or status != "TIMEOUT":
            status, message = st, msg

    return PlanResult(status, message, None, time.perf_counter() - t0,
                      stats["expanded"], stats["popped"], stats["rs_tries"], margin)


def _finish(raw_path, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle], bounds: Bounds,
            p: FastParams, t0: float, stats: dict, margin: float,
            polish=None) -> PlanResult:
    if polish is not None:
        raw_path = _polish_tail(raw_path, goal, polish[0], polish[1], polish[2], p, stats)
    # Kiểm tra lại vùng quét bằng thân xe THẬT (không nới lề), như hybrid_astar.py
    for (pa, _, _), (pb, _, _) in zip(raw_path, raw_path[1:]):
        col = check_motion(cfg, pa, pb, obstacles, bounds)
        if not col.ok:
            return PlanResult("NO_PATH", "Đường tìm được vi phạm kiểm tra vùng quét: " + col.describe(),
                              None, time.perf_counter() - t0, stats["expanded"], stats["popped"],
                              stats["rs_tries"], margin)
    traj = build_trajectory(raw_path, goal, cfg, p.cruise_speed, p.approach_speed, p.approach_distance)
    return PlanResult("OK", f"Tìm được đường dài {traj.length:.2f} m, {traj.n_cusps} lần đổi chiều",
                      traj, time.perf_counter() - t0, stats["expanded"], stats["popped"],
                      stats["rs_tries"], margin)
