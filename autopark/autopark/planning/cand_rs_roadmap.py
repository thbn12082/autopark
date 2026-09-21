"""Ứng viên "Bản đồ đường Reeds–Shepp": đồ thị thưa các tư thế, cạnh là đường RS.

Bài toán của bộ lập đường cũ: Hybrid A* vét cạn lưới 5 cm × 10° rồi báo hết
đường, vì mỗi nhịp đẩy tới–lui chỉ dịch ngang 2–3 cm nên rơi lại đúng ô lưới cũ
và bị tập đóng loại. Cách chữa là ĐỔI CÁCH BIỂU DIỄN: mỗi CẠNH của đồ thị là một
đường Reeds–Shepp ĐẦY ĐỦ 48 họ, tự nó đã chứa nhiều lần đổi chiều — nhịp đẩy tới
đẩy lui nằm sẵn trong họ CCCC (L R L R), thứ mà module RS cũ (chỉ CSC + CCC)
không có. Vì mỗi cạnh dịch xa hơn một ô lượng tử, tập đóng không thể tự khóa mình.

HAI SỐ ĐO ĐÃ ĐỊNH HÌNH THIẾT KẾ NÀY (đo trên `parallel_135`):

1. Bán kính quay là rào chắn tuyệt đối, không phải công sức tìm kiếm.
   Quét toàn sa bàn ở bước 2 cm × 7,5°, thử CẢ 48 họ: với góc lái 0,85 lần tối đa
   (R = 0,398 m) KHÔNG một tư thế nào nối được tới đích. Đích bị cô lập — thêm nút
   hay thêm giờ đều vô ích. Vì vậy mỗi cạnh được thử ở NHIỀU MỨC bán kính: mức
   rộng trước (chừa dư địa cho bộ bám), chỉ khi hỏng mới xuống mức chặt hơn.

2. Lấy mẫu dày rồi chọn "k láng giềng gần nhất" là tự bịt đường.
   Từ đích, một cạnh RS tới được 273 tư thế, nhưng cả cụm ấy chỉ trải ±4 cm dọc,
   ±1 cm ngang, ±15°. Trong một lưới mẫu 1,5 cm thì có hàng trăm nút gần hơn cái
   "cửa" cần đi, nên k gần nhất không bao giờ chọn tới nó. Do đó nút KHÔNG lấy
   mẫu sẵn rồi nối k-gần-nhất, mà SINH THEO YÊU CẦU tại các độ dời tương đối cố
   định trong hệ của chính nút cha — đúng cỡ nhịp đẩy mà chỗ chật cho phép.

Thuật toán:
  - Hai cây mọc đối đầu: cây thuận từ xuất phát, cây nghịch từ đích (phễu chật
    thường nằm ở đích, mọc từ trong phễu ra dễ hơn dò tìm cửa phễu từ ngoài).
  - Mở rộng một nút = thử các độ dời tương đối (bộ độ dời chọn theo độ hở tại chỗ:
    chỗ chật dùng nhịp 3 cm / 1 cm / 6°, chỗ rộng dùng nhịp 28 cm / 10 cm / 30°),
    cộng vài "nút cầu" lấy mẫu sẵn ở gần.
  - Sau mỗi lần mở rộng, thử bắc cầu thẳng sang cây kia bằng một đường RS.
  - Nút cầu (phần "bản đồ đường" theo nghĩa lấy mẫu) rải theo độ hở — thiên vị
    trục giữa khoảng trống — với hướng lấy theo hướng vật cản gần nhất, hướng
    đích và hướng xuất phát.
  - Chi phí = độ dài (lùi đắt hơn) + phạt đổi chiều; heuristic là khoảng cách lưới
    CÓ VẬT CẢN (Dijkstra 8 hướng dựng bằng numpy) tới đích cho cây thuận, tới xuất
    phát cho cây nghịch.
  - Cuối cùng rút ngắn bằng cách nối tắt các nút không liền kề.

Hạt giống ngẫu nhiên cố định. Va chạm trong vòng tìm kiếm dùng
`FastCollisionChecker`; đường trả về được kiểm tra lại bằng
`footprint.check_motion` (thân xe THẬT, có vùng quét) trước khi dựng quỹ đạo.
"""
from __future__ import annotations

import heapq
import math
import random
import time
from dataclasses import dataclass

import numpy as np

from autopark.control.tracker import TrajectoryTracker
from autopark.domain.types import (
    Bounds,
    Obstacle,
    Pose,
    VehicleConfig,
    VehicleState,
    wrap_angle,
)
from autopark.simulation.vehicle import SimVehicle
from autopark.geometry.fast_collision import FastCollisionChecker
from autopark.geometry.footprint import check_motion, check_pose
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.trajectory import build_trajectory
from autopark.planning import cand_rs_roadmap_rs as rs

_TWO_PI = 2.0 * math.pi
D = math.radians


def _first(t):
    return t[0]


def _inverse_offset(ds: float, dl: float, dth: float):
    """Độ dời ngược: từ nút con nhìn về nút cha, viết trong hệ của nút con."""
    c, s = math.cos(dth), math.sin(dth)
    return (-(c * ds + s * dl), s * ds - c * dl, -dth)


# --------------------------------------------------------------------- tham số

@dataclass
class RoadmapParams:
    time_limit: float = 10.0
    seed: int = 20240917

    # An toàn: y hệt hybrid_astar.py (0,03 m, và bị chặn bởi nửa khoảng hở tại
    # đích/xuất phát) — KHÔNG nới lỏng.
    safety_margin: float = 0.03
    # Nhiều mức bán kính quay cho mỗi cạnh, rộng trước chặt sau (xem đầu file).
    steer_ratios: tuple = (0.85, 0.95)
    tight_penalty: float = 0.04        # m tương đương, phạt khi phải dùng mức chặt

    # chi phí
    reverse_cost: float = 1.15
    switch_cost: float = 0.22          # m tương đương cho mỗi lần đổi chiều
    edge_cost: float = 0.015
    heuristic_weight: float = 2.2

    rs_try: int = 8                    # số ứng viên RS thử cho mỗi cặp tư thế
    edge_step: float = 0.025           # m, bước lấy mẫu kiểm tra va chạm trên cạnh

    # lượng tử tập đóng theo mức chật (ô càng nhỏ khi càng chật)
    tight_clear: float = 0.055
    open_clear: float = 0.14
    quant: tuple = ((0.005, D(1.5)), (0.018, D(4.0)), (0.055, D(10.0)))
    # Cung ngắn dùng ở mức chật/vừa: độ dài cung, và các mức lái (tỉ lệ góc lái tối đa).
    # Cung phải NGẮN hơn dư địa dọc của chỗ chật nhất, mà dư địa ấy thay đổi
    # theo từng ca: `parallel_135` hở 5,4 cm mỗi đầu, `parallel_122` 2,4 cm,
    # `parallel_115` chỉ 1,3 cm. Một độ dài cung duy nhất là hỏng — với cung
    # 1,8 cm, cây nghịch của `parallel_115` không đẻ nổi một nút nào. Nên mỗi mức
    # dùng NHIỀU cỡ cung, và ô lượng tử nhỏ hơn cỡ cung nhỏ nhất.
    arc_len: tuple = ((0.010, 0.022, 0.045), (0.030, 0.070))
    arc_steers: tuple = (0.0, 0.45, 0.85, 0.98)
    steer_penalty: float = 0.10        # theo |tỉ lệ lái| × quãng, để ưa cung thoải

    # bắc cầu sang cây kia
    rs_h_radius2: float = 1.10 ** 2      # bán kính (bình phương) dùng heuristic RS
    cross_radius: float = 0.95
    cross_k: int = 3
    portal_k: int = 2
    n_portals: int = 420

    grid_res: float = 0.04
    # Ngưỡng tự kiểm tra bám, chặt hơn 5 cm / 5° của bộ chấm để có biên an toàn.
    track_tol_xy: float = 0.040
    min_end_segment: float = 0.10
    track_tol_yaw: float = D(4.2)
    path_step: float = 0.02
    # Tốc độ THẤP hơn hybrid_astar (0,15/0,08) là có chủ đích: đường ở đây toàn
    # cung khóa lái, chỗ nối L->R đổi lái 51° mà cơ cấu chỉ quay 90°/s, nên xe
    # trượt một quãng trước khi bánh lái theo kịp và sai số HƯỚNG dồn lại quá 5°
    # ở đích. Đo trên `parallel_135` (cùng một đường, chỉ đổi hồ sơ tốc độ):
    #   0,10 m/s -> lệch 6,36° (HỎNG)   0,06 m/s -> 4,31° (ĐẠT)   0,035 -> 4,11°
    # Đổi lại là mô phỏng chạy lâu hơn (18 s -> 25 s), vẫn xa mức 240 s của bench.
    cruise_speed: float = 0.06
    approach_speed: float = 0.035
    approach_distance: float = 0.30


def _time_limit_of(params) -> float:
    if params is None:
        return RoadmapParams.time_limit
    return float(getattr(params, "time_limit", RoadmapParams.time_limit))


# Độ dời tương đối (dọc, ngang, xoay) trong hệ của NÚT CHA, ba mức theo độ hở.
#
# Phải là TÍCH CHÉO chứ không phải chỉ dịch theo từng trục. Đo trên `parallel_135`:
# từ đích, tư thế lệch ngang nhiều nhất mà một cạnh RS với tới được là
# "dọc +3 cm, ngang +1 cm, xoay +12°" — dịch ngang THUẦN 1 cm thì KHÔNG tới được,
# vì nhịp đẩy ngang thuần cần ±9 cm dư địa dọc mà khe đỗ chỉ có 4 cm. Bộ độ dời
# chỉ theo trục làm cây nghịch chết đứng sau 5 nút (đo trên `pocket_exit_park`).

def _cross(ds_vals, dl_vals, dth_vals, extra=()):
    out = []
    for ds in ds_vals:
        for dl in dl_vals:
            for dth in dth_vals:
                if ds == 0.0 and dl == 0.0 and dth == 0.0:
                    continue
                out.append((ds, dl, dth))
    out.extend(extra)
    return tuple(out)


_OFF_TIGHT = _cross((-0.035, 0.0, 0.035), (-0.012, 0.0, 0.012), (-D(10), 0.0, D(10)))
_OFF_MID = _cross((-0.10, 0.0, 0.10), (-0.030, 0.0, 0.030), (-D(20), 0.0, D(20)),
                  extra=((0.035, 0.0, D(8)), (0.035, 0.0, -D(8)),
                         (-0.035, 0.0, D(8)), (-0.035, 0.0, -D(8)),
                         (0.0, 0.012, 0.0), (0.0, -0.012, 0.0)))
_OFF_OPEN = _cross((-0.28, 0.0, 0.28), (-0.10, 0.0, 0.10), (-D(38), 0.0, D(38)),
                   extra=((0.11, 0.0, 0.0), (-0.11, 0.0, 0.0),
                          (0.16, 0.0, D(65)), (0.16, 0.0, -D(65)),
                          (-0.16, 0.0, D(65)), (-0.16, 0.0, -D(65))))
_OFF_SETS = (_OFF_TIGHT, _OFF_MID, _OFF_OPEN)


def _joins(forward: bool, dend: int, edge) -> bool:
    """Nối cạnh mới vào nút cha có sinh thêm một lần đổi chiều không?

    Cây thuận: chiều cuối của cạnh tới cha, so với chiều đầu của cạnh mới.
    Cây nghịch: chiều CUỐI của cạnh mới (con -> cha) so với chiều đầu của cạnh
    mà cha dùng để đi tiếp về đích.
    """
    return dend != (edge[5] if forward else edge[6])


def _dir_ends(lengths):
    """(chiều của đoạn đầu, chiều của đoạn cuối) trên một đường."""
    first = last = 1
    for l in lengths:
        if abs(l) > 1e-12:
            first = 1 if l > 0 else -1
            break
    for l in reversed(lengths):
        if abs(l) > 1e-12:
            last = 1 if l > 0 else -1
            break
    return first, last


# ------------------------------------------------------- lưới nền (numpy nhanh)

class _Field:
    """Lưới thô: ô bị chặn, độ hở tới chỗ bị chặn, khoảng cách có vật cản tới mốc."""

    def __init__(self, bounds: Bounds, obstacles: list[Obstacle], res: float, inflate: float):
        self.res = res
        self.xmin, self.ymin = bounds.xmin, bounds.ymin
        self.nx = max(1, int(math.ceil(bounds.width / res)))
        self.ny = max(1, int(math.ceil(bounds.height / res)))
        xs = bounds.xmin + (np.arange(self.nx) + 0.5) * res
        ys = bounds.ymin + (np.arange(self.ny) + 0.5) * res
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        blocked = np.zeros((self.nx, self.ny), dtype=bool)
        blocked |= (X < bounds.xmin + inflate) | (X > bounds.xmax - inflate)
        blocked |= (Y < bounds.ymin + inflate) | (Y > bounds.ymax - inflate)
        for o in obstacles:
            c, s = math.cos(o.yaw), math.sin(o.yaw)
            dx, dy = X - o.cx, Y - o.cy
            u = c * dx + s * dy
            v = -s * dx + c * dy
            blocked |= (np.abs(u) <= o.width / 2 + inflate) & (np.abs(v) <= o.height / 2 + inflate)
        self.blocked = blocked
        self.clear = _chamfer(blocked, res)

    def cell(self, x: float, y: float) -> tuple[int, int]:
        i = int((x - self.xmin) / self.res)
        j = int((y - self.ymin) / self.res)
        return (min(max(i, 0), self.nx - 1), min(max(j, 0), self.ny - 1))

    def clearance(self, x: float, y: float) -> float:
        i, j = self.cell(x, y)
        return self.clear[i, j]

    def dijkstra_from(self, gx: float, gy: float) -> np.ndarray:
        """Khoảng cách 8 hướng tới (gx, gy); ô bị chặn vẫn đi được nhưng đắt gấp 4."""
        nx, ny, res = self.nx, self.ny, self.res
        blocked = self.blocked
        dist = np.full((nx, ny), math.inf)
        gi, gj = self.cell(gx, gy)
        dist[gi, gj] = 0.0
        diag = res * math.sqrt(2.0)
        heap = [(0.0, gi, gj)]
        push, pop = heapq.heappush, heapq.heappop
        nbr = ((-1, -1, diag), (-1, 0, res), (-1, 1, diag), (0, -1, res),
               (0, 1, res), (1, -1, diag), (1, 0, res), (1, 1, diag))
        while heap:
            d, i, j = pop(heap)
            if d > dist[i, j]:
                continue
            for di, dj, step in nbr:
                ni, nj = i + di, j + dj
                if ni < 0 or ni >= nx or nj < 0 or nj >= ny:
                    continue
                nd = d + (step * 4.0 if blocked[ni, nj] else step)
                if nd < dist[ni, nj]:
                    dist[ni, nj] = nd
                    push(heap, (nd, ni, nj))
        return dist


def _chamfer(blocked: np.ndarray, res: float) -> np.ndarray:
    """Xấp xỉ khoảng cách tới ô bị chặn gần nhất, quét xuôi/ngược bằng numpy."""
    d = np.where(blocked, 0.0, 1e6)
    diag = res * math.sqrt(2.0)
    nx = d.shape[0]
    for _ in range(2):
        for i in range(1, nx):
            prev, cur = d[i - 1], d[i]
            np.minimum(cur, prev + res, out=cur)
            np.minimum(cur[1:], prev[:-1] + diag, out=cur[1:])
            np.minimum(cur[:-1], prev[1:] + diag, out=cur[:-1])
            _scan_row(cur, res)
        for i in range(nx - 2, -1, -1):
            prev, cur = d[i + 1], d[i]
            np.minimum(cur, prev + res, out=cur)
            np.minimum(cur[1:], prev[:-1] + diag, out=cur[1:])
            np.minimum(cur[:-1], prev[1:] + diag, out=cur[:-1])
            _scan_row(cur, res)
    return np.minimum(d, 5.0)


def _scan_row(row: np.ndarray, res: float) -> None:
    n = row.size
    for j in range(1, n):
        v = row[j - 1] + res
        if v < row[j]:
            row[j] = v
    for j in range(n - 2, -1, -1):
        v = row[j + 1] + res
        if v < row[j]:
            row[j] = v


class _Grid:
    """Băm không gian đơn giản: ô -> danh sách chỉ số nút."""

    __slots__ = ("cell", "d")

    def __init__(self, cell: float):
        self.cell = cell
        self.d: dict[tuple[int, int], list[int]] = {}

    def add(self, i: int, x: float, y: float) -> None:
        k = (int(x // self.cell), int(y // self.cell))
        lst = self.d.get(k)
        if lst is None:
            self.d[k] = [i]
        else:
            lst.append(i)

    def near(self, x: float, y: float, r: float) -> list[int]:
        c = self.cell
        i0, j0 = int((x - r) // c), int((y - r) // c)
        i1, j1 = int((x + r) // c), int((y + r) // c)
        out: list[int] = []
        get = self.d.get
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                lst = get((i, j))
                if lst:
                    out.extend(lst)
        return out


# ------------------------------------------------------------- nối hai tư thế

class _Connector:
    """Đường Reeds–Shepp rẻ nhất không va chạm giữa hai tư thế."""

    def __init__(self, checker, levels, p: RoadmapParams):
        self.checker = checker
        self.levels = levels          # [(maxc, góc lái, phạt), ...] rộng -> chặt
        self.p = p
        self.calls = 0

    def precompute_arcs(self, cfg: VehicleConfig):
        """Cung ngắn một đoạn, dùng cho mức chật và mức vừa.

        Ở chỗ chật, tập tư thế với tới được bằng MỘT đường Reeds–Shepp là một dải
        mỏng và cong: đo tại đích `parallel_135`, trong 26 độ dời tương đối cố
        định chỉ 6 cái không va chạm và chỉ 2 cái nối được. Lưới độ dời cố định
        luôn trượt khỏi dải ấy, nên cây nghịch chết đứng sau 3 nút. Cung ngắn thì
        đúng theo dựng — mọi hậu duệ đều đi được — và vì ô lượng tử ở mức chật
        (0,8 cm × 2,5°) nhỏ hơn nhiều một bước cung 3 cm, tập đóng không tự khóa
        như lưới 5 cm × 10° của Hybrid A* cũ.
        """
        p = self.p
        self.arcs = []
        for tier in (0, 1):
            rows = []
            for arc in p.arc_len[tier]:
                self._arc_rows(rows, arc, cfg)
            self.arcs.append(tuple(rows))

    def _arc_rows(self, rows, arc, cfg):
        p = self.p
        if True:
            for f in p.arc_steers:
                signs = (1, -1) if f > 0.0 else (1,)
                for sign in signs:
                    if f == 0.0:
                        maxc = self.levels[0][0]
                        mode, steer = "S", 0.0
                    else:
                        steer = sign * f * cfg.max_steer
                        maxc = math.tan(abs(steer)) / cfg.wheelbase
                        mode = "L" if steer > 0 else "R"
                    for direction in (1, -1):
                        l = direction * arc * maxc
                        cost = arc * (p.reverse_cost if direction < 0 else 1.0)
                        cost += p.steer_penalty * f * arc + p.edge_cost
                        rows.append((cost, (mode,), (l,), maxc, steer, direction, direction))

    def precompute(self, off_sets):
        """Giải sẵn Reeds–Shepp cho từng độ dời tương đối, cả chiều thuận và nghịch.

        Độ dời viết trong hệ của nút cha, nên tư thế đích ĐÃ CHUẨN HÓA
        (nx, ny, nphi) chỉ phụ thuộc độ dời và bán kính quay, KHÔNG phụ thuộc nút
        cha là ai. Vì thế toàn bộ phần đắt (sinh 48 họ, chấm điểm, sắp xếp, kiểm
        tra điểm cuối) chỉ chạy MỘT LẦN cho mỗi độ dời; lúc mở rộng chỉ còn kiểm
        tra va chạm. Bảng nghịch dùng cho cây mọc ngược từ đích, ở đó cạnh phải
        là đường đi TỪ nút con TỚI nút cha.
        """
        p = self.p
        self.tables = []
        self.tables_rev = []
        for offs in off_sets:
            fwd, rev = {}, {}
            for off in offs:
                ds, dl, dth = off
                fwd[off] = self._rows(ds, dl, dth)
                rev[off] = self._rows(*_inverse_offset(ds, dl, dth))
            self.tables.append(fwd)
            self.tables_rev.append(rev)

    def _rows(self, ds, dl, dth):
        rows = []
        for maxc, steer_mag, pen in self.levels:
            for cost, word, lengths in self._rank(ds * maxc, dl * maxc, dth, maxc):
                df, dlast = _dir_ends(lengths)
                rows.append((cost + self.p.edge_cost + pen, word, lengths, maxc,
                             steer_mag, df, dlast))
        return rows

    def expand(self, table, x0, y0, yaw0):
        """Cạnh rẻ nhất không va chạm trong một bảng đã giải sẵn."""
        free = rs.path_free
        step = self.p.edge_step
        for row in table:
            if free(self.checker, x0, y0, yaw0, row[1], row[2], row[3], step):
                return row
        return None

    def connect(self, x0, y0, yaw0, x1, y1, yaw1):
        for maxc, steer_mag, pen in self.levels:
            e = self._at(x0, y0, yaw0, x1, y1, yaw1, maxc, steer_mag, pen)
            if e is not None:
                return e
        return None

    def _at(self, x0, y0, yaw0, x1, y1, yaw1, maxc, steer_mag, pen):
        c, s = math.cos(yaw0), math.sin(yaw0)
        dx, dy = x1 - x0, y1 - y0
        nx = (c * dx + s * dy) * maxc
        ny = (-s * dx + c * dy) * maxc
        nphi = wrap_angle(yaw1 - yaw0)
        free, step = rs.path_free, self.p.edge_step
        for cost, word, lengths in self._rank(nx, ny, nphi, maxc):
            if free(self.checker, x0, y0, yaw0, word, lengths, maxc, step):
                df, dlast = _dir_ends(lengths)
                return (cost + self.p.edge_cost + pen, word, lengths, maxc,
                        steer_mag, df, dlast)
        return None

    def _rank(self, nx: float, ny: float, nphi: float, maxc: float):
        """Ứng viên RS hợp lệ tới (nx, ny, nphi) chuẩn hóa, rẻ nhất trước."""
        self.calls += 1
        cands = rs.all_candidates(nx, ny, nphi)
        if not cands:
            return []
        p = self.p
        rc, sc, inv = p.reverse_cost, p.switch_cost, 1.0 / maxc
        scored = []
        add = scored.append
        for word, lengths in cands:
            fwd = rev = 0.0
            prev = cusps = 0
            for l in lengths:
                if l > 1e-9:
                    fwd += l
                    if prev == -1:
                        cusps += 1
                    prev = 1
                elif l < -1e-9:
                    rev -= l
                    if prev == 1:
                        cusps += 1
                    prev = -1
            add(((fwd + rc * rev) * inv + sc * cusps, word, lengths))
        scored.sort(key=_first)
        out = []
        seen = set()
        err = rs.endpoint_error
        for row in scored:
            cost, word, lengths = row
            sig = (word, int(lengths[0] * 4096.0), int(lengths[-1] * 4096.0))
            if sig in seen:
                continue
            seen.add(sig)
            if err(word, lengths, nx, ny, nphi) > 1e-6:
                continue
            out.append(row)
            if len(out) >= p.rs_try:
                break
        return out


# ------------------------------------------------------------------- cây tìm

class _Tree:
    """Cây tư thế mọc bằng cạnh Reeds–Shepp, tập đóng lượng tử theo mức chật.

    `forward=True`: cạnh lưu ở nút con là đường ĐI TỪ cha TỚI con (cây từ xuất
    phát). `forward=False`: cạnh lưu ở nút con là đường ĐI TỪ con TỚI cha (cây
    ngược từ đích), nên khi ghép lại vẫn ra đúng chiều đi.
    """

    def __init__(self, root: Pose, forward: bool, field: _Field, dist: np.ndarray,
                 p: RoadmapParams, target: Pose = None, maxc: float = 1.0):
        self.forward = forward
        self.target = target
        self.maxc = maxc
        self.hcache: dict = {}
        self.field = field
        self.dist = dist
        self.p = p
        self.xs = [root.x]
        self.ys = [root.y]
        self.yaws = [root.yaw]
        self.parent = [-1]
        self.edge = [None]
        self.g = [0.0]
        # Chiều tại đầu mút mà nút này sẽ nối tiếp: cây thuận là chiều CUỐI của
        # cạnh đi vào nút, cây nghịch là chiều ĐẦU của cạnh đi ra khỏi nút.
        # 0 ở gốc nghĩa là chưa có ràng buộc, không tính phạt đổi chiều.
        self.dend = [0]
        self.grid = _Grid(0.32)
        self.grid.add(0, root.x, root.y)
        self.seen = {self.key(root.x, root.y, root.yaw)}
        self.counter = 1
        self.closed: set[int] = set()
        self.heap = [(p.heuristic_weight * self.h(root.x, root.y, root.yaw), 0, 0)]

    def key(self, x: float, y: float, yaw: float):
        """Ô lượng tử của tập đóng; càng chật thì ô càng nhỏ.

        Mức chật chỉ phụ thuộc VỊ TRÍ nên cùng một chỗ luôn cho cùng một mức,
        không có chuyện hai nút cạnh nhau rơi vào hai cách lượng tử khác nhau.
        """
        t = self.tier(x, y)
        qxy, qyaw = self.p.quant[t]
        return (t, int(x / qxy), int(y / qxy), int((yaw + math.pi) / qyaw))

    def h(self, x: float, y: float, yaw: float = None) -> float:
        """Khoảng cách lưới có vật cản; gần mốc thì lấy thêm độ dài Reeds–Shepp.

        Chỉ dùng lưới thôi là mù HƯỚNG: ngay cạnh đích, mọi hướng đều cho h ~ 0
        nên A* không có độ dốc nào để xoay xe cho đúng chiều. Độ dài Reeds–Shepp
        (bỏ qua vật cản) bù đúng chỗ đó. Nhớ theo tư thế tương đối đã làm tròn
        nên mỗi giá trị chỉ tính một lần.
        """
        f = self.field
        i = int((x - f.xmin) / f.res)
        j = int((y - f.ymin) / f.res)
        if i < 0:
            i = 0
        elif i >= f.nx:
            i = f.nx - 1
        if j < 0:
            j = 0
        elif j >= f.ny:
            j = f.ny - 1
        d = self.dist[i, j]
        base = d if d < 1e17 else 1e6
        t = self.target
        if yaw is None or t is None:
            return base
        dx, dy = t.x - x, t.y - y
        if dx * dx + dy * dy > self.p.rs_h_radius2:
            return base
        c, sn = math.cos(yaw), math.sin(yaw)
        maxc = self.maxc
        nx = (c * dx + sn * dy) * maxc
        ny = (-sn * dx + c * dy) * maxc
        nphi = wrap_angle(t.yaw - yaw)
        key = (int(nx * 25.0), int(ny * 25.0), int(nphi * 12.0))
        hit = self.hcache.get(key)
        if hit is None:
            best = math.inf
            for _, lengths in rs.all_candidates(nx, ny, nphi):
                tot = 0.0
                for l in lengths:
                    tot += l if l >= 0.0 else -l
                if tot < best:
                    best = tot
            hit = 0.0 if best == math.inf else best / maxc
            self.hcache[key] = hit
        return base if base > hit else hit

    def tier(self, x: float, y: float) -> int:
        c = self.field.clearance(x, y)
        if c < self.p.tight_clear:
            return 0
        return 1 if c < self.p.open_clear else 2

    def add(self, x: float, y: float, yaw: float, parent: int, edge, g: float) -> int:
        i = len(self.xs)
        self.xs.append(x)
        self.ys.append(y)
        self.yaws.append(yaw)
        self.parent.append(parent)
        self.edge.append(edge)
        self.g.append(g)
        self.dend.append(edge[6] if self.forward else edge[5])
        self.grid.add(i, x, y)
        heapq.heappush(self.heap, (g + self.p.heuristic_weight * self.h(x, y, yaw), self.counter, i))
        self.counter += 1
        return i

    def pop(self) -> int:
        while self.heap:
            _, _, i = heapq.heappop(self.heap)
            if i in self.closed:
                continue
            self.closed.add(i)
            return i
        return -1

    def top(self) -> float:
        heap, closed = self.heap, self.closed
        while heap and heap[0][2] in closed:
            heapq.heappop(heap)
        return heap[0][0] if heap else math.inf

    def chain(self, i: int) -> list[int]:
        out = []
        while i >= 0:
            out.append(i)
            i = self.parent[i]
        return out


# --------------------------------------------------------------- nút cầu (mẫu)

def _structured_yaws(start: Pose, goal: Pose, obstacles: list[Obstacle]) -> list[float]:
    raw = [goal.yaw, wrap_angle(goal.yaw + math.pi), start.yaw, wrap_angle(start.yaw + math.pi),
           wrap_angle(goal.yaw + math.pi / 2), wrap_angle(goal.yaw - math.pi / 2)]
    for o in obstacles:
        for k in range(4):
            raw.append(wrap_angle(o.yaw + k * math.pi / 2))
    out: list[float] = []
    for y in raw:
        if all(abs(wrap_angle(y - z)) > D(4.0) for z in out):
            out.append(y)
    return out


def _portals(field: _Field, start: Pose, goal: Pose, obstacles, checker,
             rng: random.Random, n: int):
    """Tư thế lấy mẫu: vị trí thiên vị theo độ hở, hướng theo vật cản/đích/xuất phát."""
    yaws = _structured_yaws(start, goal, obstacles)
    w = np.where(~field.blocked, field.clear ** 2 + 1e-4, 0.0).ravel()
    total = w.sum()
    if total <= 0:
        return [], _Grid(0.32)
    cdf = np.cumsum(w) / total
    res = field.res
    xs, ys, yws = [], [], []
    tries = 0
    while len(xs) < n and tries < n * 15:
        tries += 1
        idx = int(np.searchsorted(cdf, rng.random()))
        if idx >= cdf.size:
            idx = cdf.size - 1
        i, j = divmod(idx, field.ny)
        x = field.xmin + (i + 0.5) * res + rng.uniform(-res / 2, res / 2)
        y = field.ymin + (j + 0.5) * res + rng.uniform(-res / 2, res / 2)
        if rng.random() < 0.8:
            yaw = wrap_angle(rng.choice(yaws) + rng.gauss(0.0, D(8.0)))
        else:
            yaw = rng.uniform(-math.pi, math.pi)
        if checker.pose_ok(x, y, yaw):
            xs.append(x)
            ys.append(y)
            yws.append(yaw)
    grid = _Grid(0.32)
    for k in range(len(xs)):
        grid.add(k, xs[k], ys[k])
    return (xs, ys, yws), grid


# ------------------------------------------------------------------ tìm kiếm

def _rank_pick(cands, xs, ys, yaws, x, y, yaw, kyaw, r2, k):
    """k ứng viên rẻ nhất theo (khoảng cách + trọng số lệch hướng)."""
    scored = []
    for j in cands:
        dx = xs[j] - x
        dy = ys[j] - y
        d2 = dx * dx + dy * dy
        if d2 > r2:
            continue
        dw = abs(yaws[j] - yaw)
        if dw > math.pi:
            dw = _TWO_PI - dw
        scored.append((math.sqrt(d2) + kyaw * dw, j))
    scored.sort(key=_first)
    return [j for _, j in scored[:k]]


def _search(fwd: _Tree, bwd: _Tree, conn: _Connector, portals, pgrid,
            p: RoadmapParams, deadline: float):
    """Mọc hai cây đối đầu; mỗi lần bắc được cầu thì YIELD rồi tìm tiếp.

    Trả về từng ứng viên một để bên gọi còn chạy thử bám: đường đầu tiên tìm được
    thường lắt léo (tìm kiếm tham, trọng số heuristic 2,2), bỏ nó rồi tìm tiếp
    rẻ hơn nhiều so với siết chi phí cho mọi cạnh.
    """
    kyaw = 0.45 / conn.levels[0][0]
    r2 = p.cross_radius * p.cross_radius
    pxs, pys, pyaws = portals if portals else ([], [], [])
    used = (set(), set())
    popped = expanded = 0
    tick = 0
    ok = conn.checker.pose_ok
    while True:
        tick += 1
        if (tick & 7) == 0 and time.perf_counter() > deadline:
            return None, popped, expanded
        # Luân phiên NGHIÊM NGẶT hai cây. Chọn theo ngưỡng f là hỏng: cây nghịch
        # bò trong phễu chật nên g tăng nhanh mà h gần như đứng yên, còn cây thuận
        # ở chỗ rộng hạ h rất nhanh — nên cây thuận chiếm hết lượt. Đo trên
        # `parallel_135`: cây thuận 8163 nút, cây nghịch 22 nút.
        a, b, ai = (fwd, bwd, 0) if (tick & 1) else (bwd, fwd, 1)
        i = a.pop()
        if i < 0:
            a, b, ai = (bwd, fwd, 1) if ai == 0 else (fwd, bwd, 0)
            i = a.pop()
            if i < 0:
                return
        popped += 1
        x, y, yaw = a.xs[i], a.ys[i], a.yaws[i]
        gi = a.g[i]
        c, s = math.cos(yaw), math.sin(yaw)

        # --- bắc cầu sang cây kia ----------------------------------------
        targets = _rank_pick(b.grid.near(x, y, p.cross_radius), b.xs, b.ys, b.yaws,
                             x, y, yaw, kyaw, r2, p.cross_k)
        bx0, by0 = b.xs[0], b.ys[0]
        if 0 not in targets and (bx0 - x) ** 2 + (by0 - y) ** 2 < 2.25 * r2:
            targets.append(0)
        for j in targets:
            if a.forward:
                e = conn.connect(x, y, yaw, b.xs[j], b.ys[j], b.yaws[j])
                if e is not None:
                    yield (i, j, e), popped, expanded
            else:
                e = conn.connect(b.xs[j], b.ys[j], b.yaws[j], x, y, yaw)
                if e is not None:
                    yield (j, i, e), popped, expanded

        # --- sinh nút con -------------------------------------------------
        # Mức chật/vừa: cung ngắn (đúng theo dựng, không trượt khỏi dải đi được).
        # Mức rộng: độ dời tương đối nối bằng đường Reeds–Shepp nhiều khúc.
        tier = a.tier(x, y)
        di = a.dend[i]
        if tier < 2:
            for row in conn.arcs[tier]:
                nx, ny, nyaw = rs.interpolate(
                    row[2][0] if a.forward else -row[2][0],
                    row[1][0], row[3], x, y, yaw)
                nyaw = wrap_angle(nyaw)
                if not ok(nx, ny, nyaw):
                    continue
                k = a.key(nx, ny, nyaw)
                if k in a.seen:
                    continue
                if a.forward:
                    if not rs.path_free(conn.checker, x, y, yaw, row[1], row[2],
                                        row[3], p.edge_step):
                        continue
                else:
                    if not rs.path_free(conn.checker, nx, ny, nyaw, row[1], row[2],
                                        row[3], p.edge_step):
                        continue
                cost = row[0]
                if di and _joins(a.forward, di, row):
                    cost += p.switch_cost
                a.seen.add(k)
                a.add(nx, ny, nyaw, i, row, gi + cost)
                expanded += 1
        else:
            table = conn.tables[tier] if a.forward else conn.tables_rev[tier]
            for off in _OFF_SETS[tier]:
                ds, dl, dth = off
                nx = x + c * ds - s * dl
                ny = y + s * ds + c * dl
                nyaw = wrap_angle(yaw + dth)
                if not ok(nx, ny, nyaw):
                    continue
                k = a.key(nx, ny, nyaw)
                if k in a.seen:
                    continue
                rows = table[off]
                if not rows:
                    continue
                # Cây thuận: đường đi từ nút cha; cây nghịch: đường đi từ nút con.
                e = (conn.expand(rows, x, y, yaw) if a.forward
                     else conn.expand(rows, nx, ny, nyaw))
                if e is None:
                    continue
                cost = e[0]
                if di and _joins(a.forward, di, e):
                    cost += p.switch_cost
                a.seen.add(k)
                a.add(nx, ny, nyaw, i, e, gi + cost)
                expanded += 1

        # --- vài nút cầu lấy mẫu ở gần ------------------------------------
        if pxs:
            for j in _rank_pick(pgrid.near(x, y, p.cross_radius), pxs, pys, pyaws,
                                x, y, yaw, kyaw, r2, p.portal_k + 2):
                if j in used[ai]:
                    continue
                px, py, pyaw = pxs[j], pys[j], pyaws[j]
                k = a.key(px, py, pyaw)
                if k in a.seen:
                    continue
                e = (conn.connect(x, y, yaw, px, py, pyaw) if a.forward
                     else conn.connect(px, py, pyaw, x, y, yaw))
                if e is None:
                    continue
                used[ai].add(j)
                a.seen.add(k)
                a.add(px, py, pyaw, i, e, gi + e[0])
                expanded += 1


# ------------------------------------------------------------- ghép và rút gọn

def _collect(fwd: _Tree, bwd: _Tree, bridge):
    """(dãy tư thế nút, dãy cạnh) đi từ xuất phát tới đích."""
    fi, bi, e_bridge = bridge
    fchain = fwd.chain(fi)[::-1]          # gốc -> fi
    poses = [(fwd.xs[i], fwd.ys[i], fwd.yaws[i]) for i in fchain]
    edges = [fwd.edge[i] for i in fchain[1:]]
    poses.append((bwd.xs[bi], bwd.ys[bi], bwd.yaws[bi]))
    edges.append(e_bridge)
    i = bi
    while bwd.parent[i] >= 0:
        pj = bwd.parent[i]
        poses.append((bwd.xs[pj], bwd.ys[pj], bwd.yaws[pj]))
        edges.append(bwd.edge[i])
        i = pj
    return poses, edges


def _shortcut(conn: _Connector, poses, edges, deadline: float, rounds: int = 3):
    costs = [e[0] for e in edges]
    for _ in range(rounds):
        changed = False
        i = 0
        while i < len(poses) - 2:
            if time.perf_counter() > deadline:
                return poses, edges
            best_j = -1
            best_e = None
            for j in range(len(poses) - 1, i + 1, -1):
                cur = sum(costs[i:j])
                cand = conn.connect(poses[i][0], poses[i][1], poses[i][2],
                                    poses[j][0], poses[j][1], poses[j][2])
                if cand is not None and cand[0] < cur - 1e-9:
                    best_j, best_e = j, cand
                    break
            if best_j > 0:
                poses = poses[:i + 1] + poses[best_j:]
                costs = costs[:i] + [best_e[0]] + costs[best_j:]
                edges = edges[:i] + [best_e] + edges[best_j:]
                changed = True
            i += 1
        if not changed:
            break
    return poses, edges


def _trackable(traj, cfg: VehicleConfig, true_checker, goal: Pose,
               tol_xy: float, tol_yaw: float, max_time: float = 240.0) -> bool:
    """Chạy thử bộ bám + xe mô phỏng trên chính quỹ đạo này.

    Tìm được đường CHƯA phải là xong: bộ chấm còn bắt xe mô phỏng bám tới đích
    trong 5 cm / 5°. Đường nhiều khúc ngắn hay lắt léo thì lập được mà bám hỏng —
    đó là kiểu trượt hay gặp nhất ở đây. Chạy thử ngay trong bộ lập đường (dùng
    kiểm tra va chạm giải tích thay Shapely nên chỉ tốn ~50 ms thay vì 0,8 s) để
    còn kịp bỏ đường xấu và tìm tiếp.
    """
    tracker = TrajectoryTracker(traj, cfg)
    veh = SimVehicle(cfg, VehicleState(traj.points[0].pose, 0.0, 0.0, 0.0))
    dt = 0.005
    speed = steer = 0.0
    k = 0
    ok = true_checker.pose_ok
    while veh.state.t < max_time:
        if k % 4 == 0:
            out = tracker.update(veh.state)
            speed, steer = out.target_speed, out.target_steer
            if out.done and abs(veh.state.speed) < 1e-3:
                break
        veh.step(dt, speed, steer)
        k += 1
        pose = veh.state.pose
        if not ok(pose.x, pose.y, pose.yaw):
            return False
    else:
        return False
    pose = veh.state.pose
    if math.hypot(pose.x - goal.x, pose.y - goal.y) > tol_xy:
        return False
    return abs(wrap_angle(pose.yaw - goal.yaw)) <= tol_yaw


def _tail_len(edge) -> float:
    """Độ dài đoạn CÙNG CHIỀU cuối cùng của một cạnh (m)."""
    lengths, maxc = edge[2], edge[3]
    tot = 0.0
    sign = 0
    for l in reversed(lengths):
        if abs(l) < 1e-12:
            continue
        sgn = 1 if l > 0 else -1
        if sign == 0:
            sign = sgn
        elif sgn != sign:
            break
        tot += abs(l)
    return tot / maxc


def _head_len(edge) -> float:
    lengths, maxc = edge[2], edge[3]
    tot = 0.0
    sign = 0
    for l in lengths:
        if abs(l) < 1e-12:
            continue
        sgn = 1 if l > 0 else -1
        if sign == 0:
            sign = sgn
        elif sgn != sign:
            break
        tot += abs(l)
    return tot / maxc


def _polish_ends(conn: _Connector, poses, edges, min_end: float, window: int = 14):
    """Kéo dài đoạn ĐẦU và đoạn CUỐI của đường.

    Cạnh cuối cùng của đường luôn là cạnh gốc của cây nghịch, tức một cung ngắn
    1–4,5 cm; cạnh đầu tiên cũng vậy với cây thuận. Bộ bám cần chừng 10–12 cm để
    triệt tiêu sai số hướng còn lại (δ ≈ 9° mới xoay được 6°), nên đoạn cuối 3 cm
    là bám hỏng chắc chắn — đo trên `pillar_at_slot_mouth`: các đoạn cuối
    5,9 / 3,0 / 3,0 cm cho sai số 5,10° > 5°. Ở đây thay vài cạnh cuối (và đầu)
    bằng MỘT đường Reeds–Shepp duy nhất để đoạn mút dài ra.
    """
    n = len(poses)
    if n < 3:
        return poses, edges
    if _tail_len(edges[-1]) < min_end:
        lo = max(1, n - 1 - window)
        for k in range(n - 2, lo - 1, -1):
            e = conn.connect(poses[k][0], poses[k][1], poses[k][2],
                             poses[-1][0], poses[-1][1], poses[-1][2])
            if e is not None and _tail_len(e) >= min_end:
                poses = poses[:k + 1] + [poses[-1]]
                edges = edges[:k] + [e]
                break
    n = len(poses)
    if n >= 3 and _head_len(edges[0]) < min_end:
        hi = min(n - 1, window)
        for k in range(1, hi + 1):
            e = conn.connect(poses[0][0], poses[0][1], poses[0][2],
                             poses[k][0], poses[k][1], poses[k][2])
            if e is not None and _head_len(e) >= min_end:
                poses = [poses[0]] + poses[k:]
                edges = [e] + edges[k:]
                break
    return poses, edges


def _assemble(poses, edges, p: RoadmapParams) -> list[tuple[Pose, int, float]]:
    out: list[tuple[Pose, int, float]] = []
    for k, e in enumerate(edges):
        x, y, yaw = poses[k]
        samples = rs.path_samples(x, y, yaw, e[1], e[2], e[3], p.path_step, e[4])
        if k > 0:
            samples = samples[1:]
        for sx, sy, syaw, d, st in samples:
            out.append((Pose(sx, sy, wrap_angle(syaw)), d, st))
    return out


# ------------------------------------------------------------------ giao diện

def plan(start: Pose, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle],
         bounds: Bounds, params=None) -> PlanResult:
    t0 = time.perf_counter()
    p = RoadmapParams()
    p.time_limit = _time_limit_of(params)
    deadline = t0 + max(0.2, p.time_limit - 0.25)

    goal_true = check_pose(cfg, goal, obstacles, bounds)
    if not goal_true.ok:
        return PlanResult("GOAL_INVALID", "Đích không hợp lệ: " + goal_true.describe())
    start_true = check_pose(cfg, start, obstacles, bounds)
    if not start_true.ok:
        return PlanResult("START_INVALID", "Xuất phát không hợp lệ: " + start_true.describe())
    margin = max(0.0, min(p.safety_margin, goal_true.min_clearance / 2, start_true.min_clearance / 2))

    checker = FastCollisionChecker(cfg, obstacles, bounds, margin)
    levels = []
    for k, ratio in enumerate(p.steer_ratios):
        sm = cfg.max_steer * ratio
        levels.append((math.tan(sm) / cfg.wheelbase, sm, k * p.tight_penalty))
    conn = _Connector(checker, levels, p)
    conn.precompute(_OFF_SETS)
    conn.precompute_arcs(cfg)

    true_checker = FastCollisionChecker(cfg, obstacles, bounds, 0.0)

    # Nối thẳng xuất phát -> đích: xong ngay các ca dễ.
    direct = conn.connect(start.x, start.y, start.yaw, goal.x, goal.y, goal.yaw)
    if direct is not None:
        poses = [(start.x, start.y, start.yaw), (goal.x, goal.y, goal.yaw)]
        cand = _finish(poses, [direct], cfg, obstacles, bounds, goal, p, t0, 0, 0,
                       conn, 2, None, true_checker)
        if cand is not None and cand[1]:
            return cand[0]

    inflate = min(cfg.width / 2, cfg.rear_overhang) + margin
    field = _Field(bounds, obstacles, p.grid_res, inflate)
    dist_goal = field.dijkstra_from(goal.x, goal.y)
    dist_start = field.dijkstra_from(start.x, start.y)
    rng = random.Random(p.seed)
    portals, pgrid = _portals(field, start, goal, obstacles, checker, rng, p.n_portals)

    mc = levels[0][0]
    fwd = _Tree(start, True, field, dist_goal, p, goal, mc)
    bwd = _Tree(goal, False, field, dist_start, p, start, mc)
    popped = expanded = 0
    best = None
    tried = 0
    for bridge, pp_, ee_ in _search(fwd, bwd, conn, portals, pgrid, p, deadline):
        popped, expanded = pp_, ee_
        tried += 1
        poses, edges = _collect(fwd, bwd, bridge)
        cand = _finish(poses, edges, cfg, obstacles, bounds, goal, p, t0,
                       expanded, popped, conn, len(fwd.xs) + len(bwd.xs),
                       deadline, true_checker)
        if cand is None:
            if time.perf_counter() > deadline:
                break
            continue
        result, tracked = cand
        if tracked:
            result.message += f" (ứng viên thứ {tried})"
            return result
        if best is None:
            best = result
        if time.perf_counter() > deadline:
            break

    elapsed = time.perf_counter() - t0
    n_nodes = len(fwd.xs) + len(bwd.xs)
    if best is not None:
        best.elapsed = elapsed
        best.message += f" — {tried} ứng viên, chưa cái nào bám nổi tới đích"
        return best
    timed_out = time.perf_counter() >= deadline
    return PlanResult("TIMEOUT" if timed_out else "NO_PATH",
                      f"Không nối được: {n_nodes} nút, {conn.calls} lần gọi RS",
                      None, elapsed, expanded, popped)


def _finish(poses, edges, cfg, obstacles, bounds, goal, p, t0, expanded, popped,
            conn, n_nodes, deadline, true_checker):
    """Rút gọn, kiểm tra vùng quét thật, dựng quỹ đạo, rồi chạy thử bám.

    Trả về (PlanResult, bám được hay không), hoặc None nếu đường hỏng hẳn.
    """
    if deadline is not None:
        poses, edges = _shortcut(conn, poses, edges,
                                 min(deadline, time.perf_counter() + 0.5))
    poses, edges = _polish_ends(conn, poses, edges, p.min_end_segment)
    raw = _assemble(poses, edges, p)

    for (pa, _, _), (pb, _, _) in zip(raw, raw[1:]):
        if not check_motion(cfg, pa, pb, obstacles, bounds).ok:
            return None

    traj = build_trajectory(raw, goal, cfg, p.cruise_speed, p.approach_speed,
                            p.approach_distance)
    tracked = _trackable(traj, cfg, true_checker, goal, p.track_tol_xy, p.track_tol_yaw)
    result = PlanResult("OK",
                        f"Bản đồ {n_nodes} nút: dài {traj.length:.2f} m, "
                        f"{traj.n_cusps} lần đổi chiều",
                        traj, time.perf_counter() - t0, expanded, popped)
    return result, tracked
