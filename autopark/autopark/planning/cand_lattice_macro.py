"""Ứng viên "Lưới trạng thái có thao tác gộp" (macro-action lattice).

Vì sao cần: bộ lập đường hiện tại vét cạn không gian trạng thái rồi báo NO_PATH
chứ không hết giờ. Lưới 5 cm x 10 độ với bước mở rộng 8 cm không biểu diễn nổi
nhịp đẩy tới-lui: mỗi vòng đẩy chỉ dịch ngang 2-3 cm nên rơi lại đúng ô lưới cũ
và bị tập đóng loại bỏ. Làm nhanh hơn không cứu được; phải đổi cách biểu diễn.

Ý tưởng: đưa vào tập mở rộng các HÀNH ĐỘNG GỘP, mỗi hành động là trọn một nhịp
thao tác chứ không phải một cung ngắn.

1. Nhịp dịch ngang (4 cung, 1 lần đổi chiều) — đây chính là thao tác đỗ song song

       (+k, +d) (-k, +d) (+k, -d) (-k, -d)

   Cung 1-2 là chữ S tiến (đi tới, lệch trái); cung 3-4 là chữ S lùi (đi lui,
   vẫn lệch trái). Cộng lại: Δyaw = 0, Δx = 0, Δy = 4R(1-cos φ) với φ = d/R.
   Xe dịch ngang nguyên khối mà giữ nguyên hướng — thứ lưới cũ không làm được.
   (Chú ý: nhịp 2 cung "tiến trái rồi lùi phải" KHÔNG cho Δyaw = 0 mà cho 2φ;
   muốn dịch ngang thuần phải dùng 4 cung. Đã kiểm tra lại bằng tích phân.)

2. Nhịp xoay tại chỗ (2 cung, 1 lần đổi chiều)

       (+k, +d) (-k, -d)      →  Δyaw = +2φ, dịch chuyển 2R(1-cos φ)

   Lặp lại nhịp này, tâm trục sau chạy trên một đường tròn bán kính ~Rφ/2 → φ
   nhỏ thì gần như xoay tại chỗ. Đây là thao tác quay đầu nhiều nhịp trong hành
   lang hẹp.

Mỗi nhịp được lượng hoá thành vài biến thể (hai chiều xoay, hai thứ tự tiến/lùi
trước, vài độ dài cung) và được kiểm tra va chạm DỌC TOÀN NHỊP (bước ~4 cm),
không chỉ ở hai đầu. Chi phí của nhịp tính đúng quãng đường thật, số lần đổi
chiều bên trong và mức đổi góc lái.

Ngoài ra:
- Kiểm tra va chạm dùng `FastCollisionChecker` (giải tích, nhanh ~17 lần Shapely).
- Nối đích bằng Reeds-Shepp ĐẦY ĐỦ 48 họ (`cand_lattice_macro_rs`), có CCSC /
  CSCC / CCSCC là những họ nối được trong chỗ chật.
- Heuristic Reeds-Shepp được ghi nhớ theo tư thế tương đối đã làm tròn.
- Chạy theo nhiều CHẶNG: chặng đầu dùng đúng lề an toàn của `hybrid_astar`;
  nếu vét cạn mà không có đường, các chặng sau nới lỏng dần tham số tìm kiếm
  (bán kính quay, độ mịn lưới, và cuối cùng là lề an toàn). Xem ghi chú ở
  `_STAGES` về ý nghĩa và giới hạn của việc giảm lề.

Hợp đồng: plan(start, goal, cfg, obstacles, bounds, params=None) -> PlanResult
"""
from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field

from autopark.domain.computation import checkpoint
from autopark.planning.computation import controlled_plan
from autopark.domain.types import Bounds, Obstacle, Pose, VehicleConfig, wrap_angle
from autopark.geometry.fast_collision import FastCollisionChecker
from autopark.geometry.footprint import check_motion, check_pose
from autopark.planning import cand_lattice_macro_rs as rs
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.trajectory import build_trajectory

TWO_PI = 2.0 * math.pi


# ---------------------------------------------------------------- tham số

@dataclass
class LatticeParams:
    # lưới trạng thái
    xy_resolution: float = 0.045
    yaw_resolution: float = math.radians(9.0)
    n_steer: int = 5
    steer_ratio: float = 0.85
    # Tập mở rộng chia hai mức. Độ dài cung ghi bằng MÉT (không bằng góc) vì cái
    # ràng buộc thật trong ô đỗ chật là "còn bao nhiêu xăng-ti-mét để nhích".
    #   thô : bước dài, nhịp lớn — dùng ở chỗ rộng, rẻ.
    #   mịn : bước ngắn 3-4 cm và nhịp lặp nhiều vòng — dùng ở chỗ chật.
    # Mở rộng mịn chỉ được bật khi số nhánh thô đi được ít hơn `fine_threshold`,
    # tức là xe đang bị kẹt. Nhờ vậy chỗ rộng vẫn nhanh.
    coarse_step: float = 0.085
    fine_step: float = 0.035
    coarse_turn_lens: tuple[float, ...] = (0.085, 0.16)
    fine_turn_lens: tuple[float, ...] = (0.035, 0.055)
    coarse_shift_lens: tuple[float, ...] = (0.13,)
    fine_shift_lens: tuple[float, ...] = (0.042,)
    fine_turn_reps: int = 3
    fine_shift_reps: int = 3
    fine_threshold: int = 9
    use_macros: bool = True
    # nhịp gộp tự đo (đi tới khi gần chạm rồi đổi chiều)
    adaptive: bool = True
    adaptive_cap: float = 0.11
    adaptive_step: float = 0.008
    adaptive_min_leg: float = 0.008
    adaptive_reps: int = 3
    # chi phí
    reverse_cost: float = 1.25
    switch_cost: float = 0.35
    steer_cost: float = 0.15
    steer_change_cost: float = 0.20
    heuristic_weight: float = 1.15
    # an toàn
    safety_margin: float = 0.03
    # đích
    goal_xy_tol: float = 0.025
    goal_yaw_tol: float = math.radians(2.5)
    # nối Reeds-Shepp
    rs_radius: float = 1.1
    rs_every: int = 8
    rs_max_candidates: int = 6
    rs_sample_step: float = 0.035
    # lấy mẫu
    check_step: float = 0.04
    path_sample_step: float = 0.02
    heuristic_res: float = 0.035
    # giới hạn
    max_nodes: int = 400_000
    time_limit: float = 8.0
    # hồ sơ tốc độ
    cruise_speed: float = 0.15
    approach_speed: float = 0.08
    approach_distance: float = 0.30


# Các chặng chạy nối tiếp nhau. Mỗi chặng chạy tới khi hàng đợi rỗng (vét cạn)
# hoặc hết phần thời gian của mình.
#
# `margin_cap` là mức trần của lề an toàn dùng TRONG tìm kiếm. Chặng 1 và 2 dùng
# đúng công thức của `hybrid_astar` (0,03 m, chặn trên bởi nửa khoảng hở tại
# xuất phát/đích). Chặng 3 và 4 hạ trần đó xuống. Lý do: `hybrid_astar` vốn đã
# chặn lề theo khoảng hở của hai đầu mút, tinh thần là "lề không được lớn hơn
# nửa chỗ hẹp nhất mà đường buộc phải đi qua"; có ca (ví dụ `zigzag_corridor`)
# chỗ hẹp nhất nằm giữa đường chứ không ở hai đầu — khe 17 cm cho xe rộng 14 cm,
# lề 3 cm làm bài toán VÔ NGHIỆM về mặt hình học. Việc hạ trần lề chỉ nới điều
# kiện của vòng tìm kiếm; đường trả về vẫn phải qua `check_motion` với thân xe
# THẬT (lề 0) và vẫn phải được xe mô phỏng bám tới đích. Đây là điểm cần nói rõ
# khi so với mốc chuẩn: các ca được giải ở chặng 3-4 có lề tìm kiếm nhỏ hơn.
@dataclass
class _Stage:
    name: str
    share: float                 # phần thời gian được cấp
    margin_cap: float
    steer_ratio: float
    xy_resolution: float
    yaw_resolution: float
    heuristic_weight: float
    fine: bool = True            # có bật tập mở rộng mịn không
    overrides: dict = field(default_factory=dict)


# steer_ratio bị chặn ở 0,90: bộ bám cắt góc lái ở `cfg.max_steer`, nên nếu quỹ
# đạo đã lái sát mức tối đa thì số hạng phản hồi hướng bão hòa và sai số hướng
# tích lũy qua từng nhịp (đo được: uturn_w46 lệch 8,7 độ ở sr=0,95 nhưng chỉ
# 1,3-3,4 độ ở sr<=0,90). Chỉ chặng cuối mới dám dùng 0,97.
_STAGES: dict[str, _Stage] = {s.name: s for s in (
    _Stage("tho", 0.0, 0.030, 0.85, 0.050, math.radians(10.0), 1.30, fine=False),
    _Stage("min", 0.0, 0.030, 0.90, 0.040, math.radians(7.5), 1.15),
    _Stage("le-hep", 0.0, 0.015, 0.90, 0.036, math.radians(6.0), 1.10),
    _Stage("le-hep-cuoi", 0.0, 0.008, 0.97, 0.032, math.radians(5.0), 3.00,
           overrides={"fine_step": 0.03, "fine_turn_lens": (0.03, 0.05),
                      "fine_shift_lens": (0.035,), "fine_threshold": 12}),
)}

# Lịch thử: (tên chặng, "ngược?" theo nghĩa ưu tiên, phần thời gian). Hướng ưu
# tiên được chọn lúc chạy: tìm TỪ đầu nào bị nhốt chặt hơn. Lý do: thoát khỏi
# bẫy thì A* làm tự nhiên (mở rộng từ đó), còn CHUI VÀO bẫy thì phải rơi trúng
# ô lưới của đích. Đo được: parallel_135 xuôi mất 10.037 nút / 5,0 s, ngược chỉ
# 32 nút / 0,04 s. Chặng nào vét cạn sớm sẽ trả thời gian lại cho chặng sau
# (ngân sách tính theo mốc tích lũy, không theo lát riêng).
#   True  = chạy theo hướng ưu tiên
#   False = chạy theo hướng còn lại
_SCHEDULE: tuple[tuple[str, bool, float], ...] = (
    ("tho", True, 0.02),
    ("min", True, 0.03),
    ("le-hep", True, 0.04),
    ("min", False, 0.03),
    ("le-hep", False, 0.04),
    ("le-hep-cuoi", True, 0.69),
    ("le-hep-cuoi", False, 0.15),
)


# ---------------------------------------------------------------- nhịp / cung

@dataclass(frozen=True)
class _Motion:
    """Một cung sơ cấp hoặc một nhịp gộp, mô tả trong hệ xe tại điểm xuất phát."""
    segs: tuple[tuple[float, float], ...]          # (độ cong 1/m, quãng đường có dấu m)
    checks: tuple[tuple[float, float, float], ...]  # mẫu (dx, dy, dyaw) để kiểm va chạm
    end: tuple[float, float, float]
    first_dir: int
    first_steer: float
    end_dir: int
    end_steer: float
    length: float
    cost: float
    n_cusps: int
    is_macro: bool


def _integrate_segs(segs, wheelbase: float, step: float):
    """Tích phân từ gốc hệ xe. Trả về [(x, y, yaw, chiều, góc lái)], không có điểm đầu."""
    out = []
    x = y = yaw = 0.0
    for k, L in segs:
        steer = math.atan(k * wheelbase)
        direction = 1 if L > 0.0 else -1
        n = max(1, int(math.ceil(abs(L) / step)))
        sx, sy, syaw = x, y, yaw
        for i in range(1, n + 1):
            s = L * i / n
            if -1e-12 < k < 1e-12:
                px = sx + s * math.cos(syaw)
                py = sy + s * math.sin(syaw)
                pyaw = syaw
            else:
                r = 1.0 / k
                pyaw = syaw + k * s
                px = sx + r * (math.sin(pyaw) - math.sin(syaw))
                py = sy - r * (math.cos(pyaw) - math.cos(syaw))
            out.append((px, py, pyaw, direction, steer))
        x, y, yaw = out[-1][0], out[-1][1], out[-1][2]
    return out


def _make_motion(segs, cfg: VehicleConfig, sp: LatticeParams, is_macro: bool) -> _Motion:
    wb = cfg.wheelbase
    pts = _integrate_segs(segs, wb, sp.check_step)
    # Thứ tự kiểm tra không đổi kết quả (phải qua HẾT mới nhận) nhưng đổi tốc độ:
    # đặt tư thế cuối và tư thế giữa lên trước để loại nhịp bị chặn chỉ sau 1-2 lần.
    n = len(pts)
    order = [n - 1, n // 2] + [i for i in range(n) if i not in (n - 1, n // 2)]
    checks = tuple((pts[i][0], pts[i][1], pts[i][2]) for i in order)
    ex, ey, eyaw, end_dir, end_steer = pts[-1]
    first_steer = math.atan(segs[0][0] * wb)
    first_dir = 1 if segs[0][1] > 0.0 else -1

    length = 0.0
    cost = 0.0
    n_cusps = 0
    prev_dir = 0
    prev_steer = None
    for k, L in segs:
        steer = math.atan(k * wb)
        d = abs(L)
        length += d
        cost += d * (sp.reverse_cost if L < 0.0 else 1.0) * (1.0 + sp.steer_cost * abs(steer))
        direction = 1 if L > 0.0 else -1
        if prev_dir != 0 and direction != prev_dir:
            cost += sp.switch_cost
            n_cusps += 1
        if prev_steer is not None:
            cost += sp.steer_change_cost * abs(steer - prev_steer)
        prev_dir = direction
        prev_steer = steer
    return _Motion(tuple(segs), checks, (ex, ey, eyaw), first_dir, first_steer,
                   end_dir, end_steer, length, cost, n_cusps, is_macro)


def _turn_segs(k: float, d: float, reps: int, forward_first: bool):
    """Nhịp xoay: lặp `reps` lần cặp (+k, +d)(-k, -d) → Δyaw = 2·reps·d/R."""
    segs = []
    a, b = (d, -d) if forward_first else (-d, d)
    for _ in range(reps):
        segs.append((k, a))
        segs.append((-k, b))
    return segs


def _shift_segs(k: float, d: float, reps: int, forward_first: bool):
    """Nhịp dịch ngang: lặp `reps` lần bộ 4 cung → Δyaw = 0, Δy = 4·reps·R(1-cos φ)."""
    segs = []
    for _ in range(reps):
        if forward_first:
            segs += [(k, d), (-k, d), (k, -d), (-k, -d)]
        else:
            segs += [(k, -d), (-k, -d), (k, d), (-k, d)]
    return segs


def _arc_point(x: float, y: float, yaw: float, k: float, s: float):
    if -1e-12 < k < 1e-12:
        return x + s * math.cos(yaw), y + s * math.sin(yaw), yaw
    r = 1.0 / k
    nyaw = yaw + k * s
    return (x + r * (math.sin(nyaw) - math.sin(yaw)),
            y - r * (math.cos(nyaw) - math.cos(yaw)), nyaw)


def _march(x: float, y: float, yaw: float, k: float, sign: float, cap: float,
           step: float, pose_ok) -> float:
    """Quãng đường đi xa nhất mà thân xe còn hợp lệ, trần `cap`, bước `step`.

    Đây là "đi tới khi gần chạm" của người lái thật. Trong ô đỗ chật, quãng đi
    được chỉ 2-3 cm — ngắn hơn mọi bước cố định — nên nhịp gộp phải TỰ ĐO lấy.
    Mọi tư thế trung gian đều được kiểm tra, không chỉ hai đầu.
    """
    r = 1.0 / k
    ks = k * sign
    sin_, cos_ = math.sin, math.cos
    sin_yaw, cos_yaw = sin_(yaw), cos_(yaw)

    def ok(dist):
        nyaw = yaw + ks * dist
        return pose_ok(x + r * (sin_(nyaw) - sin_yaw), y - r * (cos_(nyaw) - cos_yaw), nyaw)

    # Hai pha: quét thô rồi tinh trong khoảng cuối. Cho độ phân giải `step`
    # nhưng chỉ tốn ~cap/(3·step) + 2 lần kiểm tra thay vì cap/step.
    coarse = step * 3.0
    best = 0.0
    s = coarse
    while s <= cap + 1e-12:
        if not ok(s):
            break
        best = s
        s += coarse
    limit = min(cap, best + coarse)
    s = best + step
    while s < limit - 1e-12:
        if not ok(s):
            return best
        best = s
        s += step
    return best


def _reverse_raw(raw):
    """Đảo chiều một đường: đi từ B về A thành đi từ A tới B.

    Nhãn (chiều, góc lái) của mẫu i mô tả CUNG DẪN TỚI mẫu i, nên khi đảo thì
    mẫu j lấy nhãn của mẫu (n-j+1) cũ với chiều đổi dấu; độ cong giữ nguyên.
    """
    n = len(raw) - 1
    out = []
    for j in range(n + 1):
        i = n - j
        lab = n if j == 0 else i + 1
        pose = raw[i][0]
        d, st = raw[lab][1], raw[lab][2]
        out.append((pose, -d, st))
    return out


def _adaptive_turn(x: float, y: float, yaw: float, kmax: float, sgn: float,
                   forward_first: bool, reps: int, cap: float, step: float,
                   min_leg: float, pose_ok):
    """Nhịp xoay tại chỗ TỰ ĐO: mỗi chân đi xa nhất có thể rồi đổi chiều.

    Trả về danh sách kết quả sau MỖI vòng: [(segs, (x, y, yaw)), ...]. Các vòng
    trung gian không tốn thêm lần kiểm tra va chạm nào nên cứ trả hết, cho A*
    chọn mức xoay vừa đủ.
    """
    out = []
    segs = []
    cx, cy, cyaw = x, y, yaw
    k1 = sgn * kmax
    s1 = 1.0 if forward_first else -1.0
    for _ in range(reps):
        d = _march(cx, cy, cyaw, k1, s1, cap, step, pose_ok)
        if d < min_leg:
            break
        cx, cy, cyaw = _arc_point(cx, cy, cyaw, k1, s1 * d)
        segs = segs + [(k1, s1 * d)]
        d = _march(cx, cy, cyaw, -k1, -s1, cap, step, pose_ok)
        if d < min_leg:
            break
        cx, cy, cyaw = _arc_point(cx, cy, cyaw, -k1, -s1 * d)
        segs = segs + [(-k1, -s1 * d)]
        out.append((segs, (cx, cy, cyaw)))
    return out


def _seg_cost(segs, wb: float, sp: LatticeParams):
    cost = 0.0
    prev_dir = 0
    prev_steer = None
    for k, L in segs:
        steer = math.atan(k * wb)
        d = L if L > 0 else -L
        cost += d * (sp.reverse_cost if L < 0.0 else 1.0) * (1.0 + sp.steer_cost * abs(steer))
        direction = 1 if L > 0.0 else -1
        if prev_dir != 0 and direction != prev_dir:
            cost += sp.switch_cost
        if prev_steer is not None:
            cost += sp.steer_change_cost * abs(steer - prev_steer)
        prev_dir = direction
        prev_steer = steer
    return cost


def _build_motions(cfg: VehicleConfig, max_steer: float, sp: LatticeParams):
    """Trả về (thô, mịn): hai mức tập mở rộng."""
    wb = cfg.wheelbase
    kmax = math.tan(max_steer) / wb
    coarse: list[_Motion] = []
    fine: list[_Motion] = []

    n = max(3, sp.n_steer | 1)
    steers = [-max_steer + i * (2.0 * max_steer / (n - 1)) for i in range(n)]

    def add_primitives(dest, step, levels):
        for direction in (1, -1):
            for stv in levels:
                k = math.tan(stv) / wb
                dest.append(_make_motion([(k, direction * step)], cfg, sp, False))

    add_primitives(coarse, sp.coarse_step, steers)
    if sp.use_macros:
        for d in sp.coarse_turn_lens:
            for sgn in (1.0, -1.0):
                coarse.append(_make_motion(_turn_segs(sgn * kmax, d, 1, True), cfg, sp, True))
                coarse.append(_make_motion(_turn_segs(sgn * kmax, d, 1, False), cfg, sp, True))
        for d in sp.coarse_shift_lens:
            for sgn in (1.0, -1.0):
                coarse.append(_make_motion(_shift_segs(sgn * kmax, d, 1, True), cfg, sp, True))
                coarse.append(_make_motion(_shift_segs(sgn * kmax, d, 1, False), cfg, sp, True))

    add_primitives(fine, sp.fine_step, (-max_steer, 0.0, max_steer))
    if sp.use_macros:
        if not sp.adaptive:
            # Khi không bật nhịp tự đo thì mới cần nhịp xoay độ dài cố định;
            # nhịp tự đo bao trùm chúng vì nó đo đúng chỗ trống còn lại.
            for d in sp.fine_turn_lens:
                for sgn in (1.0, -1.0):
                    fine.append(_make_motion(_turn_segs(sgn * kmax, d, 1, True), cfg, sp, True))
                    fine.append(_make_motion(_turn_segs(sgn * kmax, d, 1, False), cfg, sp, True))
            d0 = sp.fine_turn_lens[0]
            for sgn in (1.0, -1.0):
                fine.append(_make_motion(_turn_segs(sgn * kmax, d0, sp.fine_turn_reps, True), cfg, sp, True))
                fine.append(_make_motion(_turn_segs(sgn * kmax, d0, sp.fine_turn_reps, False), cfg, sp, True))
        # nhịp dịch ngang lặp nhiều vòng: một vòng nhỏ dịch chưa tới 1 ô lưới nên
        # sẽ bị tập đóng loại; gộp vài vòng vào một hành động thì mới ra khỏi ô cũ.
        for d in sp.fine_shift_lens:
            for sgn in (1.0, -1.0):
                fine.append(_make_motion(_shift_segs(sgn * kmax, d, sp.fine_shift_reps, True), cfg, sp, True))
                fine.append(_make_motion(_shift_segs(sgn * kmax, d, sp.fine_shift_reps, False), cfg, sp, True))
    return coarse, fine


# ---------------------------------------------------------------- heuristic

class _GridHeuristic:
    """Khoảng cách 2D tới đích trên lưới có vật cản (Dijkstra từ đích, 8 hướng).

    Giống `hybrid_astar.HolonomicHeuristic` về ý nghĩa nhưng dựng lưới bằng công
    thức giải tích (khoảng cách điểm tới hình chữ nhật có hướng) thay vì Shapely,
    nên đủ rẻ để dùng lưới mịn.
    """

    __slots__ = ("res", "xmin", "ymin", "nx", "ny", "dist", "gx", "gy")

    def __init__(self, goal: Pose, bounds: Bounds, obstacles: list[Obstacle],
                 res: float, inflate: float):
        self.res = res
        self.xmin, self.ymin = bounds.xmin, bounds.ymin
        self.gx, self.gy = goal.x, goal.y
        nx = max(1, int(math.ceil(bounds.width / res)))
        ny = max(1, int(math.ceil(bounds.height / res)))
        self.nx, self.ny = nx, ny

        obs = []
        for o in obstacles:
            obs.append((o.cx, o.cy, math.cos(o.yaw), math.sin(o.yaw),
                        o.width / 2.0, o.height / 2.0))
        x0, y0 = bounds.xmin + inflate, bounds.ymin + inflate
        x1, y1 = bounds.xmax - inflate, bounds.ymax - inflate

        blocked = bytearray(nx * ny)
        for i in range(nx):
            checkpoint()
            cx = self.xmin + (i + 0.5) * res
            base = i * ny
            inside_x = x0 <= cx <= x1
            for j in range(ny):
                cy = self.ymin + (j + 0.5) * res
                if not inside_x or not (y0 <= cy <= y1):
                    blocked[base + j] = 1
                    continue
                for ox, oy, c, s, hx, hy in obs:
                    dx = cx - ox
                    dy = cy - oy
                    px = c * dx + s * dy
                    py = -s * dx + c * dy
                    ax = abs(px) - hx
                    ay = abs(py) - hy
                    if ax < 0.0:
                        ax = 0.0
                    if ay < 0.0:
                        ay = 0.0
                    if ax * ax + ay * ay <= inflate * inflate:
                        blocked[base + j] = 1
                        break

        INF = math.inf
        dist = [INF] * (nx * ny)
        gi = min(max(int((goal.x - self.xmin) / res), 0), nx - 1)
        gj = min(max(int((goal.y - self.ymin) / res), 0), ny - 1)
        dist[gi * ny + gj] = 0.0
        heap = [(0.0, gi * ny + gj)]
        diag = res * math.sqrt(2.0)
        push, pop = heapq.heappush, heapq.heappop
        while heap:
            checkpoint()
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
                        step *= 4.0
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
            if d < math.inf:
                return d
        return math.hypot(self.gx - x, self.gy - y)


# ---------------------------------------------------------------- tìm kiếm

def _search(start: Pose, goal: Pose, cfg: VehicleConfig, bounds: Bounds,
            checker: FastCollisionChecker, holo: _GridHeuristic,
            coarse: list[_Motion], fine: list[_Motion], sp: LatticeParams,
            max_steer: float, deadline: float):
    """A* trên lưới trạng thái với cung sơ cấp + nhịp gộp. Trả về (raw, status, popped, expanded)."""
    motions = coarse + fine
    n_coarse = len(coarse)
    n_total = len(motions)
    fine_threshold = sp.fine_threshold if fine else 0
    adaptive = sp.adaptive and bool(fine)
    ad_cap = sp.adaptive_cap
    ad_step = sp.adaptive_step
    ad_min_leg = sp.adaptive_min_leg
    ad_reps = sp.adaptive_reps
    wb = cfg.wheelbase
    maxc = math.tan(max_steer) / wb
    kmax = maxc
    pose_ok = checker.pose_ok
    xy_res = sp.xy_resolution
    yaw_res = sp.yaw_resolution
    n_yaw = max(1, int(round(TWO_PI / yaw_res)))
    bx, by = bounds.xmin, bounds.ymin
    gx, gy, gyaw = goal.x, goal.y, goal.yaw
    hw = sp.heuristic_weight
    rs_r2 = sp.rs_radius * sp.rs_radius
    rs_holo_limit = sp.rs_radius * 1.7      # có tường chắn giữa đường thì đừng thử nối
    rs_max_len = sp.rs_radius * 2.2         # bỏ ứng viên RS dài vô lý
    rs_rate = sp.rs_every / max(1e-6, rs_r2)  # nhịp thử theo bình phương khoảng cách

    # bộ nhớ đệm heuristic Reeds-Shepp theo tư thế tương đối đã làm tròn.
    # Ô nhớ tính trong hệ CHUẨN HÓA (đã nhân maxc): 0,10 đơn vị ~ 3,5 cm.
    rs_cache: dict[tuple[int, int, int], float] = {}
    inv_dxy = 1.0 / 0.10
    inv_da = 1.0 / 0.10

    # Tra lưới heuristic bằng biến cục bộ (gán qua tham số mặc định) thay vì gọi
    # phương thức: hàm này chạy một lần cho MỖI nút con sinh ra, khoảng 25 lần
    # mỗi nút, nên chi phí gọi hàm ở đây đáng kể hơn cả kiểm tra va chạm.
    _hd = holo.dist
    _hres = 1.0 / holo.res
    _hxmin, _hymin, _hnx, _hny = holo.xmin, holo.ymin, holo.nx, holo.ny
    _rs_h_limit = sp.rs_radius
    _INF = math.inf

    def heuristic(x: float, y: float, yaw: float,
                  _hd=_hd, _hres=_hres, _hxmin=_hxmin, _hymin=_hymin,
                  _hnx=_hnx, _hny=_hny, _cos=math.cos, _sin=math.sin,
                  _hypot=math.hypot, _int=int) -> float:
        i = _int((x - _hxmin) * _hres)
        j = _int((y - _hymin) * _hres)
        if 0 <= i < _hnx and 0 <= j < _hny:
            h = _hd[i * _hny + j]
            if h == _INF:
                h = _hypot(gx - x, gy - y)
        else:
            h = _hypot(gx - x, gy - y)
        if h < _rs_h_limit:
            ddx = gx - x
            ddy = gy - y
            c = _cos(yaw)
            s = _sin(yaw)
            nx = (c * ddx + s * ddy) * maxc
            ny = (-s * ddx + c * ddy) * maxc
            nphi = rs.mod2pi(gyaw - yaw)
            key = (_int(nx * inv_dxy), _int(ny * inv_dxy), _int(nphi * inv_da))
            v = rs_cache.get(key)
            if v is None:
                v = rs.shortest_norm_fast(nx, ny, nphi) / maxc
                if v != v or v == _INF:
                    v = 0.0
                rs_cache[key] = v
            if v > h:
                h = v
        return hw * h

    # nút lưu theo mảng song song cho nhanh
    nxs = [start.x]
    nys = [start.y]
    nyaws = [start.yaw]
    ndirs = [0]
    nsteers = [0.0]
    ngs = [0.0]
    nparents = [-1]
    nmotions = [-2]
    nsegs = [None]

    def cell_key(x, y, yaw, direction):
        return (int((x - bx) / xy_res), int((y - by) / xy_res),
                int(((yaw + math.pi) % TWO_PI) / yaw_res) % n_yaw, direction)

    start_key = cell_key(start.x, start.y, start.yaw, 0)
    best = {start_key: 0.0}
    closed: set = set()
    heap = [(heuristic(start.x, start.y, start.yaw), 0, 0)]
    push, pop = heapq.heappush, heapq.heappop
    counter = 1
    popped = expanded = 0
    goal_tol2 = sp.goal_xy_tol * sp.goal_xy_tol
    status = "NO_PATH"

    while heap:
        checkpoint()
        _, _, nid = pop(heap)
        x = nxs[nid]
        y = nys[nid]
        yaw = nyaws[nid]
        direction = ndirs[nid]
        k = cell_key(x, y, yaw, direction)
        if k in closed:
            continue
        closed.add(k)
        popped += 1

        if (popped & 63) == 0 and time.perf_counter() > deadline:
            return None, "TIMEOUT", popped, expanded
        if popped > sp.max_nodes:
            return None, "TIMEOUT", popped, expanded

        dx = gx - x
        dy = gy - y
        d2 = dx * dx + dy * dy
        if d2 < goal_tol2 and abs(wrap_angle(yaw - gyaw)) < sp.goal_yaw_tol:
            return _reconstruct(nid, nparents, nmotions, nsegs, motions, nxs, nys, nyaws,
                                cfg, sp, None, maxc), "OK", popped, expanded

        # Thử nối Reeds-Shepp: càng gần đích càng thử dày. Ở xa mà thử dày thì
        # riêng khâu này ăn hết thời gian mà gần như không bao giờ thành công.
        if d2 < rs_r2 and (popped % (1 + int(d2 * rs_rate)) == 0 or popped == 1) \
                and holo(x, y) < rs_holo_limit:
            tail = _try_rs(x, y, yaw, goal, maxc, wb, checker, sp, rs_max_len)
            if tail is not None:
                return _reconstruct(nid, nparents, nmotions, nsegs, motions, nxs, nys, nyaws,
                                    cfg, sp, tail, maxc), "OK", popped, expanded

        g0 = ngs[nid]
        steer0 = nsteers[nid]
        c = math.cos(yaw)
        s = math.sin(yaw)

        # Mở rộng thô trước. Nếu xe đang kẹt (ít nhánh thô đi được) thì mở rộng
        # thêm bằng tập mịn: bước 3 cm và nhịp lặp nhiều vòng. Trong ô đỗ song
        # song chỉ còn ~4 cm để nhích, bước 8,5 cm không nhúc nhích được — đó
        # chính là lý do mốc chuẩn vét cạn rồi báo NO_PATH.
        free = 0
        for mi in range(n_coarse):
            m = motions[mi]
            ok = True
            for ddx, ddy, ddyaw in m.checks:
                if not pose_ok(x + c * ddx - s * ddy, y + s * ddx + c * ddy, yaw + ddyaw):
                    ok = False
                    break
            if not ok:
                continue
            free += 1
            ex, ey, eyaw = m.end
            wx = x + c * ex - s * ey
            wy = y + s * ex + c * ey
            wyaw = wrap_angle(yaw + eyaw)
            nk = cell_key(wx, wy, wyaw, m.end_dir)
            if nk in closed:
                continue
            cost = m.cost
            if direction != 0 and m.first_dir != direction:
                cost += sp.switch_cost
            cost += sp.steer_change_cost * abs(m.first_steer - steer0)
            g = g0 + cost
            if g >= best.get(nk, math.inf):
                continue
            best[nk] = g
            nxs.append(wx)
            nys.append(wy)
            nyaws.append(wyaw)
            ndirs.append(m.end_dir)
            nsteers.append(m.end_steer)
            ngs.append(g)
            nparents.append(nid)
            nmotions.append(mi)
            nsegs.append(None)
            push(heap, (g + heuristic(wx, wy, wyaw), counter, len(nxs) - 1))
            counter += 1
            expanded += 1

        if free >= fine_threshold:
            continue
        for mi in range(n_coarse, n_total):
            m = motions[mi]
            ok = True
            for ddx, ddy, ddyaw in m.checks:
                if not pose_ok(x + c * ddx - s * ddy, y + s * ddx + c * ddy, yaw + ddyaw):
                    ok = False
                    break
            if not ok:
                continue
            ex, ey, eyaw = m.end
            wx = x + c * ex - s * ey
            wy = y + s * ex + c * ey
            wyaw = wrap_angle(yaw + eyaw)
            nk = cell_key(wx, wy, wyaw, m.end_dir)
            if nk in closed:
                continue
            cost = m.cost
            if direction != 0 and m.first_dir != direction:
                cost += sp.switch_cost
            cost += sp.steer_change_cost * abs(m.first_steer - steer0)
            g = g0 + cost
            if g >= best.get(nk, math.inf):
                continue
            best[nk] = g
            nxs.append(wx)
            nys.append(wy)
            nyaws.append(wyaw)
            ndirs.append(m.end_dir)
            nsteers.append(m.end_steer)
            ngs.append(g)
            nparents.append(nid)
            nmotions.append(mi)
            nsegs.append(None)
            push(heap, (g + heuristic(wx, wy, wyaw), counter, len(nxs) - 1))
            counter += 1
            expanded += 1

        # --- nhịp gộp TỰ ĐO: mỗi chân đi tới khi gần chạm rồi đổi chiều.
        # Cần cho ô đỗ chỉ còn 2-3 cm để nhích, nơi mọi bước cố định đều tắc.
        if not adaptive:
            continue
        for sgn in (1.0, -1.0):
            for forward_first in (True, False):
                for segs, (wx, wy, wyaw) in _adaptive_turn(
                        x, y, yaw, kmax, sgn, forward_first, ad_reps,
                        ad_cap, ad_step, ad_min_leg, pose_ok):
                    wyaw = wrap_angle(wyaw)
                    end_dir = 1 if segs[-1][1] > 0 else -1
                    nk = cell_key(wx, wy, wyaw, end_dir)
                    if nk in closed:
                        continue
                    first_steer = math.atan(segs[0][0] * wb)
                    cost = _seg_cost(segs, wb, sp)
                    if direction != 0 and (1 if segs[0][1] > 0 else -1) != direction:
                        cost += sp.switch_cost
                    cost += sp.steer_change_cost * abs(first_steer - steer0)
                    g = g0 + cost
                    if g >= best.get(nk, math.inf):
                        continue
                    best[nk] = g
                    nxs.append(wx)
                    nys.append(wy)
                    nyaws.append(wyaw)
                    ndirs.append(end_dir)
                    nsteers.append(math.atan(segs[-1][0] * wb))
                    ngs.append(g)
                    nparents.append(nid)
                    nmotions.append(-1)
                    nsegs.append(segs)
                    push(heap, (g + heuristic(wx, wy, wyaw), counter, len(nxs) - 1))
                    counter += 1
                    expanded += 1

    return None, status, popped, expanded


def _try_rs(x: float, y: float, yaw: float, goal: Pose, maxc: float, wb: float,
            checker: FastCollisionChecker, sp: LatticeParams, max_len: float):
    """Thử nối thẳng tới đích bằng Reeds-Shepp đầy đủ, kiểm tra va chạm dọc đường.

    Xếp hạng trước, kiểm tra điểm cuối lười (chỉ với ứng viên định dùng) và bỏ
    ngay ứng viên dài hơn `max_len` — nếu không, riêng khâu này ăn hết thời gian.
    """
    ranked = rs.ranked_words(x, y, yaw, goal.x, goal.y, goal.yaw, maxc, sp.switch_cost)
    pose_ok = checker.pose_ok
    tried = 0
    for _rank, types, lengths, length_m, _cusps in ranked:
        if length_m > max_len:
            break
        if not rs.verify(x, y, yaw, goal.x, goal.y, goal.yaw, types, lengths, maxc):
            continue
        tried += 1
        if tried > sp.rs_max_candidates:
            break
        pts = rs.sample(x, y, yaw, types, lengths, maxc, sp.rs_sample_step, wb)
        good = True
        # tư thế cuối cùng thường là chỗ chật nhất: thử trước để loại nhanh
        px, py, pyaw, _d, _st = pts[-1]
        if not pose_ok(px, py, pyaw):
            continue
        for px, py, pyaw, _d, _st in pts:
            if not pose_ok(px, py, pyaw):
                good = False
                break
        if good:
            return (types, lengths)
    return None


def _reconstruct(nid: int, nparents, nmotions, nsegs, motions, nxs, nys, nyaws,
                 cfg: VehicleConfig, sp: LatticeParams, rs_tail, maxc: float):
    """Dựng lại dãy (Pose, chiều, góc lái) dày đặc từ chuỗi nút."""
    chain = []
    i = nid
    while i >= 0:
        chain.append(i)
        i = nparents[i]
    chain.reverse()

    wb = cfg.wheelbase
    step = sp.path_sample_step
    out: list[tuple[Pose, int, float]] = []

    # điểm đầu: chiều/góc lái lấy theo nhịp đầu tiên (nếu có)
    def segs_of(idx):
        mi = nmotions[idx]
        return motions[mi].segs if mi >= 0 else nsegs[idx]

    if len(chain) > 1:
        s0 = segs_of(chain[1])
        first_dir = 1 if s0[0][1] > 0 else -1
        first_steer = math.atan(s0[0][0] * cfg.wheelbase)
    elif rs_tail is not None:
        first_dir, first_steer = 1, 0.0
    else:
        first_dir, first_steer = 1, 0.0
    out.append((Pose(nxs[chain[0]], nys[chain[0]], nyaws[chain[0]]), first_dir, first_steer))

    for idx in chain[1:]:
        segs = segs_of(idx)
        px, py, pyaw = out[-1][0].x, out[-1][0].y, out[-1][0].yaw
        c, s = math.cos(pyaw), math.sin(pyaw)
        for bxp, byp, byaw, d, st in _integrate_segs(segs, wb, step):
            out.append((Pose(px + c * bxp - s * byp, py + s * bxp + c * byp,
                             wrap_angle(pyaw + byaw)), d, st))

    if rs_tail is not None:
        types, lengths = rs_tail
        last = out[-1][0]
        pts = rs.sample(last.x, last.y, last.yaw, types, lengths, maxc,
                        sp.path_sample_step, cfg.wheelbase)
        if pts and len(out) == 1:
            # cả đường chỉ là một đoạn Reeds-Shepp: sửa nhãn của điểm đầu
            out[0] = (out[0][0], pts[0][3], pts[0][4])
        for px, py, pyaw, d, st in pts:
            out.append((Pose(px, py, wrap_angle(pyaw)), d, st))
    return out


# ---------------------------------------------------------------- API chính

@controlled_plan(8.0)
def plan(start: Pose, goal: Pose, cfg: VehicleConfig, obstacles: list[Obstacle],
         bounds: Bounds, params=None) -> PlanResult:
    t0 = time.perf_counter()
    sp = LatticeParams()
    time_limit = getattr(params, "time_limit", None)
    if time_limit is None or time_limit <= 0:
        time_limit = sp.time_limit
    sp.time_limit = float(time_limit)

    goal_true = check_pose(cfg, goal, obstacles, bounds)
    if not goal_true.ok:
        return PlanResult("GOAL_INVALID", "Đích không hợp lệ: " + goal_true.describe(),
                          None, time.perf_counter() - t0, 0, 0)
    start_true = check_pose(cfg, start, obstacles, bounds)
    if not start_true.ok:
        return PlanResult("START_INVALID", "Xuất phát không hợp lệ: " + start_true.describe(),
                          None, time.perf_counter() - t0, 0, 0)

    base_cap = min(goal_true.min_clearance / 2.0, start_true.min_clearance / 2.0)
    total_popped = total_expanded = 0
    last_status = "NO_PATH"
    last_msg = "Không tìm được đường trong không gian tìm kiếm"
    t_end = t0 + sp.time_limit

    holo_cache: dict[tuple[int, int], _GridHeuristic] = {}
    stage_cache: dict[str, tuple] = {}

    # Hướng ưu tiên: tìm TỪ đầu nào bị nhốt chặt hơn. Đếm số nhánh thô đi được
    # ở mỗi đầu với lề chặt nhất; đầu nào ít nhánh hơn là đầu bị nhốt.
    probe_margin = max(0.0, min(_STAGES["le-hep-cuoi"].margin_cap, base_cap))
    probe_checker = FastCollisionChecker(cfg, obstacles, bounds, probe_margin)
    probe_params = LatticeParams(safety_margin=probe_margin)
    probe_motions, _ = _build_motions(cfg, cfg.max_steer * 0.9, probe_params)
    free_start = _free_count(start, probe_motions, probe_checker)
    free_goal = _free_count(goal, probe_motions, probe_checker)
    prefer_backward = free_goal < free_start

    acc = 0.0
    for stage_name, use_preferred, share in _SCHEDULE:
        checkpoint()
        stage = _STAGES[stage_name]
        backward = prefer_backward if use_preferred else (not prefer_backward)
        acc += share
        now = time.perf_counter()
        if now >= t_end - 0.02:
            break
        slice_end = min(t_end, t0 + sp.time_limit * acc)
        if slice_end <= now + 0.02:
            slice_end = min(t_end, now + 0.05)

        margin = max(0.0, min(stage.margin_cap, base_cap))
        cached = stage_cache.get(stage.name)
        if cached is None:
            st = LatticeParams(
                xy_resolution=stage.xy_resolution,
                yaw_resolution=stage.yaw_resolution,
                steer_ratio=stage.steer_ratio,
                heuristic_weight=stage.heuristic_weight,
                safety_margin=margin,
                time_limit=sp.time_limit,
            )
            for field_name, value in stage.overrides.items():
                setattr(st, field_name, value)
            max_steer = cfg.max_steer * st.steer_ratio
            checker = FastCollisionChecker(cfg, obstacles, bounds, margin)
            coarse, fine = _build_motions(cfg, max_steer, st)
            if not stage.fine:
                fine = []
            stage_cache[stage.name] = (st, max_steer, checker, coarse, fine, margin)
        st, max_steer, checker, coarse, fine, margin = stage_cache[stage.name]

        inflate = min(cfg.width / 2.0, cfg.rear_overhang) + margin
        hkey = (int(round(inflate * 10000)), 1 if backward else 0)
        holo = holo_cache.get(hkey)
        if holo is None:
            target = start if backward else goal
            holo = _GridHeuristic(target, bounds, obstacles, st.heuristic_res, inflate)
            holo_cache[hkey] = holo

        # Tìm NGƯỢC (từ đích về xuất phát) rồi đảo đường. Với bài đỗ xe, đích
        # nằm trong ô chật còn xuất phát ở chỗ rộng: thoát khỏi bẫy thì A* làm
        # tự nhiên, còn CHUI VÀO bẫy thì phải trúng đúng ô lưới. Đo được:
        # parallel_135 xuôi mất 11.619 nút / 6,2 s, ngược chỉ 44 nút / 0,04 s.
        if backward:
            raw_r, status, popped, expanded = _search(
                goal, start, cfg, bounds, checker, holo, coarse, fine, st, max_steer, slice_end)
            raw = _reverse_raw(raw_r) if raw_r is not None else None
        else:
            raw, status, popped, expanded = _search(
                start, goal, cfg, bounds, checker, holo, coarse, fine, st, max_steer, slice_end)
        total_popped += popped
        total_expanded += expanded
        last_status = status
        tag = f"{stage.name}/{'nguoc' if backward else 'xuoi'}"
        if raw is None:
            last_msg = (f"[{tag}] {'hết giờ' if status == 'TIMEOUT' else 'vét cạn'} "
                        f"sau {popped} nút")
            continue

        bad = _verify(raw, cfg, obstacles, bounds)
        if bad is not None:
            last_msg = f"[{tag}] đường vi phạm kiểm tra vùng quét: {bad}"
            last_status = "NO_PATH"
            continue

        trajectory = build_trajectory(raw, goal, cfg, st.cruise_speed, st.approach_speed,
                                      st.approach_distance)
        elapsed = time.perf_counter() - t0
        return PlanResult(
            "OK",
            f"[{tag}, lề {margin * 100:.1f} cm] dài {trajectory.length:.2f} m, "
            f"{trajectory.n_cusps} lần đổi chiều",
            trajectory, elapsed, total_expanded, total_popped, 0, margin)

    elapsed = time.perf_counter() - t0
    status = "TIMEOUT" if last_status == "TIMEOUT" else "NO_PATH"
    return PlanResult(status, last_msg, None, elapsed, total_expanded, total_popped, 0, 0.0)


def _free_count(pose: Pose, motions: list[_Motion], checker: FastCollisionChecker) -> int:
    """Số nhịp đi được từ một tư thế — thước đo "bị nhốt tới mức nào"."""
    c, s = math.cos(pose.yaw), math.sin(pose.yaw)
    x, y, yaw = pose.x, pose.y, pose.yaw
    pose_ok = checker.pose_ok
    n = 0
    for m in motions:
        for dx, dy, dyaw in m.checks:
            if not pose_ok(x + c * dx - s * dy, y + s * dx + c * dy, yaw + dyaw):
                break
        else:
            n += 1
    return n


def _verify(raw, cfg, obstacles, bounds):
    for (pa, _, _), (pb, _, _) in zip(raw, raw[1:]):
        checkpoint()
        col = check_motion(cfg, pa, pb, obstacles, bounds)
        if not col.ok:
            return col.describe()
    return None
