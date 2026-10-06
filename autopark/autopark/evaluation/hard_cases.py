r"""Bộ ca khó dùng để đo năng lực của bộ lập đường.

Mục đích: tách "dễ" khỏi "khó" bằng số đo, không bằng cảm nhận. Các ca được xếp
theo độ chặt của không gian thao tác:

- `easy_*`  : một hoặc hai lần đổi chiều là xong.
- `tight_*` : cần vài lần tiến/lùi (3–7 cusp).
- `xtight_*`: cần rất nhiều lần đẩy tới đẩy lui (shuttle), là loại ca mà tìm kiếm
  theo lưới hay nổ số nút hoặc hết giờ.

Mức `difficulty` đặt theo cảm nhận lúc dựng ca, CHƯA CHỐT bằng số đo (24/09/2026): ví dụ
`parallel_122` mang mức `xtight` nhưng nay đã có đường chứng 5 lần đổi chiều, tức nằm trong
khoảng của `tight`. Chưa đổi mức vì mức còn phụ thuộc lề an toàn và góc lái mà planner được dùng.

Kích thước lấy theo xe mặc định (dài 0,31 m, rộng 0,14 m, chiều dài cơ sở 0,19 m,
lái tối đa 30° → bán kính quay tâm trục sau 0,329 m, bán kính ngoài ≈ 0,47 m). Đây là
thông số GIẢ ĐỊNH của `configs/vehicle_default.json`, chưa phải số đo MN300.

Nhãn `expected` (định nghĩa lại ngày 24/09/2026)
------------------------------------------------
Nhãn nói về SỰ TỒN TẠI của đường trong mô hình mà các planner của dự án dùng: xe kiểu
Reeds–Shepp (tiến và lùi, |độ cong| ≤ tan(δ_max)/L, đổi góc lái tức thời hoặc khi đứng
yên), thân xe là hình chữ nhật đúng kích thước cấu hình, lề 0, vật cản và biên như trong ca,
tới đúng tư thế đích (lệch ≤ 1 mm, ≤ 0,1°). Nhãn KHÔNG nói đường đó có hợp lý với xe thật hay
không: giới hạn tốc độ đánh lái, sai số bám và số lần đổi chiều chịu được CHƯA XÉT.

- `feasible`: đã có đường chứng (witness) kiểm độc lập. `tests/test_hard_cases_labels.py`
  tích phân lại từng cung và kiểm va chạm bằng `evaluation/collision_oracle.py` (không dùng bộ
  kiểm va chạm của planner), với bước mẫu h và lề (1 + κ_max·r_max)·h/2 — đủ để suy ra thân xe
  không chạm cả ở khoảng giữa hai mẫu. Đường chứng lấy từ
  `docs/evidence/hard_cases/witness_20260924.json` (planner tìm, 24/09/2026),
  `docs/evidence/hard_cases/witness_ngan_song_song_20260924.json` (dựng riêng, xem dưới), hoặc
  dựng giải tích bằng `parallel_shuffle_witness` (các ca đỗ song song).
- `infeasible`: chỉ dùng khi có chứng minh hình học. Hiện không ca nào mang nhãn này.
- `unknown`: chưa có đường chứng, cũng chưa có chứng minh vô nghiệm.

Lịch sử: bản đầu ghi nhãn theo nhật ký 08/09/2026 (duyệt rộng hai chiều trên một đồ thị
chuyển động RỜI RẠC; kho mã không kèm chương trình để tái chạy). `parallel_122` và
`parallel_115` khi đó bị ghi `infeasible` vì mặt sóng từ đích chỉ nở vài chục trạng thái. Vét
cạn một đồ thị rời rạc chỉ chứng minh vô nghiệm trên chính đồ thị đó. Ngày 24/09/2026 cả hai
ca đã có đường chứng hợp lệ nên đổi sang `feasible`.

Số lần đổi chiều của các đường đã có cho hai ca này (24/09/2026, máy bàn):
- planner, `parallel_122`: portfolio 104 lần (nấc 'ngẫu nhiên', lưu trong witness_20260924.json);
  nấc RRT chạy riêng 136 và 150 lần (không lưu đường). Planner chưa ra đường nào cho `parallel_115`.
- `parallel_shuffle_witness`: 121 lần (122) và 279 lần (115) với tham số mặc định; 79 và 145 lần
  khi lái đủ δ_max với hở thiết kế 1 mm.
- Đường chứng ngắn, dựng ở vòng rà soát tối 24/09/2026 bằng script nháp (không có trong kho mã):
  từ đích "gỡ" xe khỏi ô một cách tham lam (lùi thẳng, rồi luân phiên tiến lái trái / lùi lái
  phải ở 0,90·κ_max, mỗi nhịp đi tới khi còn hở 1,5 mm, cho tới khi thân xe ra khỏi hàng xe đỗ),
  đảo ngược đoạn đó, rồi nối từ xuất phát bằng Reeds–Shepp. Kết quả: 5 lần đổi chiều, 1,23 m
  (122) và 13 lần, 1,32 m (115); góc lái ≤ 27,46° (0,90·κ_max, tức 0,915·δ_max); hở Euclid nhỏ
  nhất ≈ 1,6 / 1,75 mm, nhỏ hơn lề tìm kiếm của mọi planner (0,8–1 cm ở hai ca này). Lưu ở
  `docs/evidence/hard_cases/witness_ngan_song_song_20260924.json`.
Các con số trên là của từng đường, KHÔNG phải cận dưới: số lần đổi chiều tối thiểu CHƯA BIẾT.
"Không thực dụng" là nhận xét về các đường planner trả về (104–150 lần, nhiều nhịp dưới 2 cm),
không phải tính chất của ca. Planner hết giờ hoặc báo NO_PATH ở hai ca này là giới hạn của
planner (lề tìm kiếm, trần góc lái, tìm kiếm không đầy đủ), không phải bằng chứng rằng ca vốn
cần nhiều lần đổi chiều như vậy. Bằng chứng: `docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md` mục 6.

Không dùng riêng kết quả TIMEOUT/NO_PATH để suy ra bài toán vô nghiệm. `portfolio` báo
NO_PATH khi nấc cuối ('lưới mịn') vét cạn lưới của nó. Ví dụ `zigzag_corridor`: portfolio báo
NO_PATH ở 60 s (24/09/2026) dù ca này có đường chứng.

Sinh lại đường chứng từ planner (thêm 24/09/2026): chạy module này, xem `main()`. Ví dụ, một
dòng trong cmd.exe, trong thư mục `autopark`:
    .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.hard_cases --witness-out runs\witness_moi.json --time-limit 30
Planner có hạn giờ theo đồng hồ thật nên chạy lại dưới tải khác có thể ra đường khác (vẫn hợp
lệ) hoặc TIMEOUT. Test chỉ đọc hai tệp witness_*.json trong `docs/evidence/hard_cases/`, không
đọc tệp mới sinh.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from autopark.domain.types import (
    Bounds,
    Obstacle,
    ParkingGoal,
    ParkingMode,
    ParkingSlot,
    Pose,
    Scenario,
    VehicleConfig,
)


@dataclass(frozen=True)
class HardCase:
    name: str
    scenario: Scenario
    difficulty: str          # easy | tight | xtight
    expected: str            # feasible | infeasible | unknown
    note: str = ""


def _parked(id_: str, cx: float, cy: float, cfg: VehicleConfig, vertical: bool = False) -> Obstacle:
    """Một xe đang đỗ, kích thước bằng xe của ta."""
    return Obstacle(id_, cx, cy, cfg.length, cfg.width, math.pi / 2 if vertical else 0.0, "car")


def _wall(id_: str, cx: float, cy: float, w: float, h: float, yaw: float = 0.0) -> Obstacle:
    return Obstacle(id_, cx, cy, w, h, yaw, "wall")


def _scenario(name: str, bounds: Bounds, start: Pose, cfg: VehicleConfig,
              obstacles: list[Obstacle], slot: ParkingSlot | None = None,
              mode: ParkingMode = ParkingMode.REVERSE_IN, goal: Pose | None = None,
              notes: str = "") -> Scenario:
    sc = Scenario(
        name=name,
        bounds=bounds,
        start=start,
        goal=ParkingGoal(goal if goal is not None else Pose(0.0, 0.0, 0.0)),
        obstacles=obstacles,
        slot=slot,
        mode=mode,
        notes=notes,
    )
    sc.sync_goal(cfg)
    return sc


# ---------------------------------------------------------------- đỗ song song

def parallel_case(name: str, cfg: VehicleConfig, slot_len: float, street_w: float,
                  difficulty: str, expected: str) -> HardCase:
    """Đỗ song song giữa hai xe, xuất phát ở làn đường phía trên và đã đi quá ô.

    `slot_len` tính theo mét; tỉ lệ so với chiều dài xe ghi trong ghi chú.
    """
    car_l, car_w = cfg.length, cfg.width
    y_park = 0.02 + car_w / 2                    # xe đỗ sát lề y = 0
    y_curb_top = 0.02 + car_w                    # mép trên hàng xe đỗ
    slot_cx = 0.30 + slot_len / 2 + car_l        # chừa chỗ cho xe A phía sau
    x1, x2 = slot_cx - slot_len / 2, slot_cx + slot_len / 2
    xmax = x2 + car_l + 0.62
    ymax = y_curb_top + street_w
    obstacles = [
        _parked("xe_sau", x1 - car_l / 2, y_park, cfg),
        _parked("xe_truoc", x2 + car_l / 2, y_park, cfg),
    ]
    start = Pose(x2 + car_l + 0.30, y_curb_top + street_w / 2, 0.0)
    slot = ParkingSlot(slot_cx, y_park, 0.0, slot_len, car_w + 0.06)
    sc = _scenario(name, Bounds(0.0, 0.0, xmax, ymax), start, cfg, obstacles, slot,
                   ParkingMode.PARALLEL,
                   notes=f"Đỗ song song, ô dài {slot_len * 100:.0f} cm = {slot_len / car_l:.2f}× thân xe, "
                         f"làn rộng {street_w * 100:.0f} cm. Xe đã đi quá ô nên phải lùi vào.")
    return HardCase(name, sc, difficulty, expected, sc.notes)


# ---------------------------------------------------------------- đường chứng dựng giải tích

Arc = tuple[float, float]
"""Một cung của đường chứng: (quãng có dấu tính theo tâm trục sau, m, + tiến / − lùi; độ cong 1/m, + rẽ trái)."""


def shuffle_cycle(phi: float, kappa: float, side: int = -1) -> list[Arc]:
    """Một chu kỳ "nhích ngang" gồm bốn cung cùng độ dài ε = φ/κ.

    Thứ tự: tiến lái về `side`, tiến lái ngược, lùi lái về `side`, lùi lái ngược. Tích phân đúng
    (không xấp xỉ), trong hệ xe lúc bắt đầu chu kỳ: x và hướng trở về giá trị ban đầu, còn y dịch
    đúng 4·(1 − cos φ)/κ về phía `side` (−1: bên phải xe, +1: bên trái). Trong chu kỳ, tâm trục
    sau chỉ đi trong đoạn [0, 2·sin φ/κ] dọc thân xe, hướng nằm trong [−φ, φ]. Vì vậy một ô dài
    hơn thân xe bất kỳ một khoảng dương vẫn cho xe dịch ngang: chọn φ đủ nhỏ, chấp nhận rất nhiều
    chu kỳ. Chu kỳ có hai lần đổi chiều (tiến→lùi và lùi→tiến của chu kỳ sau).
    """
    if not (0.0 < phi < math.pi / 2) or not (kappa > 0.0) or side not in (-1, 1):
        raise ValueError("cần 0 < phi < π/2, kappa > 0 và side là −1 hoặc +1")
    e = phi / kappa
    k = side * kappa
    return [(e, k), (e, -k), (-e, k), (-e, -k)]


def parallel_shuffle_witness(case: HardCase, cfg: VehicleConfig, steer_ratio: float = 0.85,
                             clearance: float = 0.006) -> list[Arc]:
    """Dựng một đường chứng cho ca của `parallel_case`: lùi hình chữ S xuống sát hàng xe đỗ, lùi
    thẳng tới ngay trên ô, nhích ngang bằng `shuffle_cycle` cho tới khi vào hàng, rồi tiến thẳng
    một đoạn ngắn về đúng tư thế đích.

    Đường này cố ý không tối ưu: nó chỉ để chứng minh ca CÓ đường, không phải để chạy trên xe.
    Góc lái dùng `steer_ratio` × δ_max (mặc định 0,85, bằng mức nấc 'ngẫu nhiên' của portfolio).
    `clearance` là khoảng hở thiết kế theo chiều dọc ô, tới lề đường, và tới nóc hàng xe đỗ lúc
    xe còn đi trên làn. Hàm chỉ dựng đường, không tự kiểm va chạm; tính hợp lệ do
    `tests/test_hard_cases_labels.py` kiểm bằng oracle độc lập.
    Chỉ nhận hình thế của `parallel_case`: ô và xe đỗ nằm dọc trục x, lề đường là `bounds.ymin`,
    xe xuất phát hướng +x trên làn và đã đi quá ô.
    """
    sc = case.scenario
    goal = sc.goal.pose
    cars = sorted((o for o in sc.obstacles if o.kind == "car"), key=lambda o: o.cx)
    if (sc.mode != ParkingMode.PARALLEL or sc.slot is None or len(cars) != 2
            or any(abs(o.yaw) > 1e-9 for o in cars) or abs(sc.slot.yaw) > 1e-9
            or abs(goal.yaw) > 1e-9 or abs(sc.start.yaw) > 1e-9 or sc.start.x <= goal.x):
        raise ValueError(f"{case.name}: không phải hình thế của parallel_case")
    if not (0.0 < steer_ratio <= 1.0) or clearance < 0.0:
        raise ValueError("cần 0 < steer_ratio ≤ 1 và clearance ≥ 0")
    kappa = math.tan(steer_ratio * cfg.max_steer) / cfg.wheelbase
    back, front, hw = cfg.rear_overhang, cfg.wheelbase + cfg.front_overhang, cfg.width / 2
    x_lo = cars[0].cx + cars[0].width / 2          # đầu xe phía sau ô
    x_hi = cars[1].cx - cars[1].width / 2          # đuôi xe phía trước ô
    row_top = max(o.cy + o.height / 2 for o in cars)

    # Góc nhích lớn nhất: (1) dọc ô, trục sau đi 2·sin φ/κ và hai góc thân xe quay thêm tối đa
    # w/2·sin φ mỗi đầu; (2) góc trước lúc chúc xuống không được chạm lề đường.
    slack = (x_hi - x_lo) - cfg.length - 2 * clearance
    to_curb = goal.y - hw - sc.bounds.ymin - clearance
    if slack <= 0.0 or to_curb <= 0.0:
        raise ValueError(f"{case.name}: ô không dài hơn thân xe + 2 × clearance, hoặc đích sát lề")
    phi_max = math.asin(min(slack / (2 / kappa + 2 * hw), to_curb / front, 0.5))

    # Cuối cung thứ hai của chữ S, góc sau phía dưới võng xuống thấp hơn lúc xe đã thẳng một
    # đoạn `dip` (cực tiểu của (1 − cos θ)/κ − back·sin θ − hw·(cos θ − 1)).
    th = math.atan(back / (1 / kappa + hw))
    dip = max(0.0, back * math.sin(th) + hw * math.cos(th) - hw - (1 - math.cos(th)) / kappa)
    y_lane = row_top + hw + clearance + dip
    drop = sc.start.y - y_lane
    if not (0.0 < drop < 2 / kappa):
        raise ValueError(f"{case.name}: làn quá hẹp hoặc xe xuất phát quá thấp để lùi chữ S")
    th_s = math.acos(1 - drop * kappa / 2)
    arcs: list[Arc] = [(-th_s / kappa, -kappa), (-th_s / kappa, kappa)]
    x_after_s = sc.start.x - 2 * math.sin(th_s) / kappa

    n = math.ceil((y_lane - goal.y) / (4 * (1 - math.cos(phi_max)) / kappa))
    phi = math.acos(1 - (y_lane - goal.y) / n * kappa / 4)
    x_cycle = goal.x - math.sin(phi) / kappa        # đoạn đi của trục sau đối xứng quanh đích
    if x_after_s <= x_cycle:
        raise ValueError(f"{case.name}: xe xuất phát chưa đi quá ô đủ xa")
    arcs.append((-(x_after_s - x_cycle), 0.0))
    for _ in range(n):
        arcs += shuffle_cycle(phi, kappa, side=-1)
    arcs.append((math.sin(phi) / kappa, 0.0))
    return arcs


def _pair_arc(a: Pose, b: Pose) -> Arc | None:
    """Cung tròn đi từ tư thế `a`, đổi hướng đúng bằng hướng của `b` và có dây dài bằng |ab|.

    Trả (quãng có dấu, độ cong); None khi hai điểm trùng nhau (dây < 1e-9 m). Nếu `b` không nằm
    trên cung tròn nào từ `a` thì cung trả về không đi qua `b`: xem `_pair_fit_error`.
    """
    dx, dy = b.x - a.x, b.y - a.y
    chord = math.hypot(dx, dy)
    if chord < 1e-9:
        return None
    along = math.cos(a.yaw) * dx + math.sin(a.yaw) * dy
    dth = math.atan2(math.sin(b.yaw - a.yaw), math.cos(b.yaw - a.yaw))
    half = dth / 2
    factor = half / math.sin(half) if abs(half) > 1e-12 else 1.0
    length = math.copysign(chord * factor, along)
    return length, dth / length


def _arc_end(a: Pose, length: float, kappa: float) -> Pose:
    """Tư thế cuối khi tâm trục sau đi quãng có dấu `length` với độ cong `kappa` từ `a`."""
    dth = length * kappa
    half = dth / 2
    sinc = math.sin(half) / half if abs(half) > 1e-12 else 1.0
    heading = a.yaw + half
    yaw = a.yaw + dth
    return Pose(a.x + length * sinc * math.cos(heading), a.y + length * sinc * math.sin(heading),
                math.atan2(math.sin(yaw), math.cos(yaw)))


def _pair_fit_error(points) -> float:
    """Sai lệch vị trí lớn nhất (m) giữa điểm kế tiếp của quỹ đạo và đầu cung `_pair_arc` dựng tới nó."""
    poses = [getattr(p, "pose", p) for p in points]
    worst = 0.0
    for a, b in zip(poses, poses[1:]):
        arc = _pair_arc(a, b)
        if arc is not None:
            end = _arc_end(a, *arc)
            worst = max(worst, math.hypot(end.x - b.x, end.y - b.y))
    return worst


def trajectory_to_arcs(points) -> list[Arc]:
    """Đổi dãy điểm quỹ đạo của planner thành dãy cung của đường chứng (thêm 24/09/2026).

    `points` là các `TrajectoryPoint` (lấy `.pose`) hoặc `Pose`. Mỗi cặp điểm liền nhau (a, b) được
    coi là một cung tròn: đưa b về hệ của a, quãng có dấu s = ±dây·(Δθ/2)/sin(Δθ/2) (dấu theo thành
    phần dọc thân xe), độ cong κ = Δθ/s. Cặp trùng nhau (điểm lặp ở chỗ đổi chiều) bị bỏ. Cung cùng
    chiều với cung trước và độ cong lệch dưới 1e-6 1/m được gộp vào cung trước.

    Hàm không tự kiểm: nếu planner nối hai điểm bằng thứ không phải cung tròn thì dãy cung sai.
    `main()` in sai lệch lớn nhất (`_pair_fit_error`) và kiểm lại đường bằng oracle trước khi ghi.
    """
    poses = [getattr(p, "pose", p) for p in points]
    arcs: list[Arc] = []
    for a, b in zip(poses, poses[1:]):
        arc = _pair_arc(a, b)
        if arc is None:
            continue
        length, kappa = arc
        if arcs and (arcs[-1][0] > 0) == (length > 0) and abs(arcs[-1][1] - kappa) < 1e-6:
            total = arcs[-1][0] + length
            arcs[-1] = (total, (arcs[-1][1] * arcs[-1][0] + kappa * length) / total)
        else:
            arcs.append((length, kappa))
    return arcs


# ---------------------------------------------------------------- quay đầu trong hành lang

def corridor_uturn(name: str, cfg: VehicleConfig, width: float, length: float,
                   difficulty: str, expected: str) -> HardCase:
    """Hành lang cụt: xe vào theo +x, phải quay đầu để hướng ra -x."""
    start = Pose(0.34, width / 2, 0.0)
    goal = Pose(0.34, width / 2, math.pi)
    sc = _scenario(name, Bounds(0.0, 0.0, length, width), start, cfg, [], None,
                   ParkingMode.REVERSE_IN, goal,
                   notes=f"Quay đầu tại chỗ trong hành lang rộng {width * 100:.0f} cm "
                         f"({width / cfg.length:.2f}× thân xe), dài {length * 100:.0f} cm.")
    return HardCase(name, sc, difficulty, expected, sc.notes)


def dead_end_turn_and_park(cfg: VehicleConfig) -> HardCase:
    """Ngõ cụt: đi tới cuối ngõ, quay đầu, rồi lùi vào ô bên hông gần cửa ngõ."""
    car_l, car_w = cfg.length, cfg.width
    width = 0.62
    length = 1.50
    slot_depth = 0.38
    slot_w = car_w + 0.08
    gap_half = slot_w / 2 + 0.01
    ymax = width + slot_depth
    obstacles = [
        # tường ngăn hành lang với dãy ô, chừa đúng một khoảng trống làm cửa ô
        _wall("tuong_trai", (0.75 - gap_half) / 2, width, 0.75 - gap_half, 0.03),
        _wall("tuong_phai", (0.75 + gap_half + length) / 2, width, length - 0.75 - gap_half, 0.03),
    ]
    slot = ParkingSlot(0.75, width + slot_depth / 2, math.pi / 2, slot_depth, slot_w)
    start = Pose(0.34, width / 2, 0.0)
    sc = _scenario("deadend_turn_park", Bounds(0.0, 0.0, length, ymax), start, cfg,
                   obstacles, slot, ParkingMode.REVERSE_IN,
                   notes="Ngõ cụt rộng 62 cm: phải quay đầu rồi lùi vào ô trên tường bên.")
    return HardCase("deadend_turn_park", sc, "xtight", "feasible", sc.notes)


# ---------------------------------------------------------------- đỗ vuông góc, lối đi hẹp

def perpendicular_case(name: str, cfg: VehicleConfig, aisle_w: float, slot_w_extra: float,
                       difficulty: str, expected: str) -> HardCase:
    """Lùi vào ô vuông góc từ một lối đi hẹp, hai bên ô đều có xe."""
    car_l, car_w = cfg.length, cfg.width
    slot_depth = car_l + 0.09
    slot_cx = 1.00
    slot_w = car_w + slot_w_extra
    y_row_c = 0.04 + car_l / 2          # tâm xe đỗ dọc theo y
    y_row_top = 0.04 + car_l
    obstacles = [
        _parked("xe_trai", slot_cx - slot_w / 2 - car_w / 2, y_row_c, cfg, vertical=True),
        _parked("xe_phai", slot_cx + slot_w / 2 + car_w / 2, y_row_c, cfg, vertical=True),
        _parked("xe_trai2", slot_cx - slot_w / 2 - car_w * 1.6, y_row_c, cfg, vertical=True),
        _parked("xe_phai2", slot_cx + slot_w / 2 + car_w * 1.6, y_row_c, cfg, vertical=True),
    ]
    ymax = y_row_top + aisle_w
    slot = ParkingSlot(slot_cx, slot_depth / 2, -math.pi / 2, slot_depth, slot_w)
    start = Pose(0.30, y_row_top + aisle_w / 2, 0.0)
    sc = _scenario(name, Bounds(0.0, 0.0, 1.90, ymax), start, cfg, obstacles, slot,
                   ParkingMode.REVERSE_IN,
                   notes=f"Lùi vào ô vuông góc, lối đi rộng {aisle_w * 100:.0f} cm "
                         f"({aisle_w / car_l:.2f}× thân xe), ô rộng {slot_w * 100:.0f} cm.")
    return HardCase(name, sc, difficulty, expected, sc.notes)


# ---------------------------------------------------------------- ra khỏi ngách và các ca khác

def pocket_exit(cfg: VehicleConfig) -> HardCase:
    """Xe đang nằm sâu trong ngách quay mặt vào trong; phải lùi ra rồi đỗ chỗ khác."""
    car_l, car_w = cfg.length, cfg.width
    pocket_w = car_w + 0.07
    ymax = 1.06
    slot_len = 0.39
    obstacles = [
        # ngách cụt ở phía trên, chỉ hở xuống dưới; đáy ngách là mép trên sa bàn
        _wall("ngach_trai", 0.35 - pocket_w / 2 - 0.02, 0.84, 0.04, 0.44, 0.0),
        _wall("ngach_phai", 0.35 + pocket_w / 2 + 0.02, 0.84, 0.04, 0.44, 0.0),
        _parked("xe_a", 1.10, 0.14, cfg),
        _parked("xe_b", 1.80, 0.14, cfg),
    ]
    start = Pose(0.35, 0.78, math.pi / 2)     # đầu xe chúi vào đáy ngách
    slot = ParkingSlot(1.45, 0.14, 0.0, slot_len, car_w + 0.06)
    sc = _scenario("pocket_exit_park", Bounds(0.0, 0.0, 2.10, ymax), start, cfg,
                   obstacles, slot, ParkingMode.PARALLEL,
                   notes=f"Xuất phát chúi đầu trong ngách cụt hẹp, phải lùi ra rồi đỗ song song "
                         f"vào ô {slot_len / car_l:.2f}× thân xe.")
    return HardCase("pocket_exit_park", sc, "xtight", "feasible", sc.notes)


def zigzag_corridor(cfg: VehicleConfig) -> HardCase:
    """Hành lang gấp khúc chữ Z, mỗi khúc chỉ rộng hơn thân xe một chút."""
    w = 0.40
    obstacles = [
        _wall("t1", 0.62, 0.94, 1.24, 0.04),
        _wall("t2", 1.42, 0.40, 0.04, 0.84),
        _wall("t3", 0.78, 0.40, 0.90, 0.04),
        _wall("t4", 0.32, 0.72, 0.04, 0.60),
    ]
    start = Pose(0.16, 0.16, 0.0)
    goal = Pose(1.72, 0.72, math.pi / 2)
    sc = _scenario("zigzag_corridor", Bounds(0.0, 0.0, 1.92, 1.12), start, cfg, obstacles,
                   None, ParkingMode.REVERSE_IN, goal,
                   notes="Hành lang chữ Z, mỗi khúc rộng ~40 cm; phải bẻ nhiều nhịp ở mỗi góc.")
    return HardCase("zigzag_corridor", sc, "tight", "feasible", sc.notes)


def reverse_along_corridor(cfg: VehicleConfig) -> HardCase:
    """Ô nằm ngay sau lưng xe trong hành lang quá hẹp để quay đầu: phải lùi thẳng một quãng dài."""
    start = Pose(1.30, 0.20, 0.0)
    goal = Pose(0.30, 0.20, 0.0)
    sc = _scenario("reverse_long_corridor", Bounds(0.0, 0.0, 1.70, 0.40), start, cfg, [],
                   None, ParkingMode.REVERSE_IN, goal,
                   notes="Hành lang rộng 40 cm (1,29× thân xe): không quay đầu được, buộc lùi thẳng 1 m.")
    return HardCase("reverse_long_corridor", sc, "tight", "feasible", sc.notes)


def lateral_shift(cfg: VehicleConfig) -> HardCase:
    """Dịch ngang trong hành lang hẹp: cùng hướng, lệch ngang 18 cm. Chỉ giải được bằng nhiều nhịp đẩy."""
    start = Pose(0.55, 0.13, 0.0)
    goal = Pose(0.55, 0.31, 0.0)
    sc = _scenario("lateral_shift", Bounds(0.0, 0.0, 1.30, 0.44), start, cfg, [],
                   None, ParkingMode.REVERSE_IN, goal,
                   notes="Dịch ngang 18 cm trong hành lang 44 cm, giữ nguyên hướng: bài toán đẩy tới lui kinh điển.")
    return HardCase("lateral_shift", sc, "xtight", "feasible", sc.notes)


def pillar_at_slot_mouth(cfg: VehicleConfig) -> HardCase:
    """Ca người dùng gặp: cột 12 cm đứng ngay cửa ô đỗ, ô nằm ở đầu dãy.

    Dựng lại từ `scenarios/bai_do_xe.json` với ô đỗ được kéo xuống dưới cột.
    Bản gốc trong ứng dụng báo hết giờ sau 8 s.
    """
    obstacles = [
        _parked("xe_1", 1.45, 0.35, cfg, vertical=True),
        _parked("xe_2", 1.95, 0.35, cfg, vertical=True),
        _parked("xe_3", 2.45, 0.35, cfg, vertical=True),
        _parked("xe_4", 2.95, 0.35, cfg, vertical=True),
        Obstacle("cot", 0.90, 0.50, 0.12, 0.12, 0.0, "box"),
    ]
    slot = ParkingSlot(0.87, 0.25, -math.pi / 2, 0.50, 0.34)
    start = Pose(0.60, 1.45, 0.0)
    sc = _scenario("pillar_at_slot_mouth", Bounds(0.0, 0.0, 3.0, 2.0), start, cfg,
                   obstacles, slot, ParkingMode.REVERSE_IN,
                   notes="Cột 12 cm chắn ngay cửa ô; phải lách quanh cột rồi lùi vào. "
                         "Bản trong ứng dụng hết giờ sau 8 s.")
    return HardCase("pillar_at_slot_mouth", sc, "xtight", "feasible", sc.notes)


def build_cases(cfg: VehicleConfig) -> dict[str, HardCase]:
    cases = [
        parallel_case("parallel_160", cfg, slot_len=cfg.length * 1.60, street_w=0.52, difficulty="easy", expected="feasible"),
        parallel_case("parallel_135", cfg, slot_len=cfg.length * 1.35, street_w=0.46, difficulty="tight", expected="feasible"),
        # 122 và 115: trước 24/09/2026 ghi "infeasible" theo phép duyệt đồ thị rời rạc; nay có đường chứng
        # (xem docstring đầu module). Đường chứng ít lần đổi chiều nhất đã có: 5 lần (122), 13 lần (115);
        # các đường planner tìm được nhiều hơn hẳn (122: 104–150). Số lần tối thiểu CHƯA BIẾT.
        parallel_case("parallel_122", cfg, slot_len=cfg.length * 1.22, street_w=0.42, difficulty="xtight", expected="feasible"),
        parallel_case("parallel_115", cfg, slot_len=cfg.length * 1.15, street_w=0.40, difficulty="xtight", expected="feasible"),
        perpendicular_case("perp_aisle_170", cfg, aisle_w=cfg.length * 1.70, slot_w_extra=0.09, difficulty="easy", expected="feasible"),
        perpendicular_case("perp_aisle_135", cfg, aisle_w=cfg.length * 1.35, slot_w_extra=0.07, difficulty="tight", expected="feasible"),
        perpendicular_case("perp_aisle_115", cfg, aisle_w=cfg.length * 1.15, slot_w_extra=0.06, difficulty="xtight", expected="feasible"),
        corridor_uturn("uturn_w70", cfg, width=0.70, length=1.30, difficulty="tight", expected="feasible"),
        corridor_uturn("uturn_w55", cfg, width=0.55, length=1.30, difficulty="xtight", expected="feasible"),
        corridor_uturn("uturn_w46", cfg, width=0.46, length=1.40, difficulty="xtight", expected="feasible"),
        reverse_along_corridor(cfg),
        lateral_shift(cfg),
        zigzag_corridor(cfg),
        dead_end_turn_and_park(cfg),
        pocket_exit(cfg),
        pillar_at_slot_mouth(cfg),
    ]
    return {c.name: c for c in cases}


# ---------------------------------------------------------------- sinh lại đường chứng từ planner

_RUNGS = {"gop-nhanh": "gộp-nhanh", "gop-ky": "gộp-kỹ", "ngau-nhien": "ngẫu nhiên", "luoi-min": "lưới mịn"}
"""Tên ASCII (gõ được trong cmd.exe) của các nấc trong `portfolio.default_ladder()`."""

WITNESS_STEP = 0.0005                  # m, bước mẫu khi kiểm, bằng STEP của tests/test_hard_cases_labels.py
WITNESS_END_XY = 0.001                 # m, lệch đích tối đa của đường chứng
WITNESS_END_YAW = math.radians(0.1)
WITNESS_GEOMETRY_KEYS = ("wheelbase_m", "width_m", "front_overhang_m", "rear_overhang_m", "max_steer_deg")
"""Các trường của `VehicleConfig.to_dict()` quyết định đường chứng có hợp lệ hay không; tên, ghi chú,
giới hạn tốc độ/gia tốc không ảnh hưởng."""


def same_witness_geometry(a: dict, b: dict, tol: float = 1e-9) -> bool:
    """Hai khối "vehicle" có cùng kích thước và góc lái tối đa (các trường `WITNESS_GEOMETRY_KEYS`)."""
    try:
        return all(abs(float(a[k]) - float(b[k])) <= tol for k in WITNESS_GEOMETRY_KEYS)
    except (KeyError, TypeError, ValueError):
        return False


_WITNESS_FIELDS = {
    "nguon": "lệnh và nấc sinh ra đường (tự điền từ tham số dòng lệnh)",
    "cusps": "số lần đổi chiều, đếm lại từ dãy cung",
    "length_m": "tổng quãng đường tâm trục sau",
    "max_steer_deg": "góc lái lớn nhất, tính từ độ cong lớn nhất",
    "shortest_run_m": "nhịp cùng chiều ngắn nhất",
    "min_clearance_m": ("khoảng hở nhỏ nhất tại các mẫu cách 0,5 mm, đo bằng lề hình chữ nhật của "
                        "collision_oracle (cận dưới của khoảng hở Euclid), chặn trên ở 0,03 m"),
    "end_error_m / end_error_deg": "lệch cuối đường so với tư thế đích của ca",
    "arcs": "[quãng có dấu m, độ cong 1/m], nối tiếp nhau từ tư thế xuất phát",
}


def witness_stats(cfg: VehicleConfig, scenario: Scenario, arcs: list[Arc], step: float = WITNESS_STEP) -> dict:
    """Số đo của một dãy cung, kiểm bằng `collision_oracle` (không dùng bộ kiểm của planner).

    `valid` chỉ đúng khi: không chạm, hở tại mọi mẫu ≥ (1 + κ_max·r_max)·h/2, |κ| ≤ κ_max, và cuối đường
    lệch đích ≤ 1 mm / 0,1°, cùng ngưỡng với test. Đây là phép kiểm để lệnh sinh đường không ghi đường
    hỏng; phán quyết cuối vẫn là `tests/test_hard_cases_labels.py`.
    """
    from autopark.evaluation import collision_oracle as oracle

    kappa_max = math.tan(cfg.max_steer) / cfg.wheelbase
    r_max = max(math.hypot(cfg.wheelbase + cfg.front_overhang, cfg.width / 2),
                math.hypot(cfg.rear_overhang, cfg.width / 2))
    need = (1 + kappa_max * r_max) * step / 2
    min_clear, touched, short = 0.03, False, False
    pose = scenario.start
    for length, kappa in arcs:
        steer = math.atan(kappa * cfg.wheelbase)
        n = max(1, math.ceil(abs(length) / step))
        for j in range(n + 1):
            p = oracle.arc_pose(pose, length * j / n, steer, cfg.wheelbase)
            if oracle.pose_ok(cfg, p, scenario.obstacles, scenario.bounds, max(min_clear, need)):
                continue                         # hở ít nhất bằng lề mẫu và mức nhỏ nhất đã thấy
            if not oracle.pose_ok(cfg, p, scenario.obstacles, scenario.bounds, need):
                short = True                     # kiểm đúng như test, không qua số chia đôi đã làm tròn
            if oracle.pose_ok(cfg, p, scenario.obstacles, scenario.bounds, min_clear):
                continue
            if not oracle.pose_ok(cfg, p, scenario.obstacles, scenario.bounds, 0.0):
                touched, min_clear = True, 0.0
                continue
            lo, hi = 0.0, min_clear
            for _ in range(12):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if oracle.pose_ok(cfg, p, scenario.obstacles, scenario.bounds, mid) else (lo, mid)
            min_clear = lo
        pose = oracle.arc_pose(pose, length, steer, cfg.wheelbase)
    goal = scenario.goal.pose
    end_xy = math.hypot(pose.x - goal.x, pose.y - goal.y)
    end_yaw = abs(math.atan2(math.sin(pose.yaw - goal.yaw), math.cos(pose.yaw - goal.yaw)))
    runs: list[float] = []
    for i, (length, _) in enumerate(arcs):
        if i and (length > 0) == (arcs[i - 1][0] > 0):
            runs[-1] += abs(length)
        else:
            runs.append(abs(length))
    k_used = max((abs(k) for _, k in arcs), default=0.0)
    return {
        "cusps": max(0, len(runs) - 1),
        "length_m": round(sum(abs(s) for s, _ in arcs), 4),
        "max_steer_deg": round(math.degrees(math.atan(k_used * cfg.wheelbase)), 3),
        "shortest_run_m": round(min(runs), 4) if runs else 0.0,
        "min_clearance_m": round(min_clear, 4),
        "end_error_m": float(f"{end_xy:.3g}"),
        "end_error_deg": float(f"{math.degrees(end_yaw):.3g}"),
        "valid": bool(arcs) and not touched and not short and k_used <= kappa_max * (1 + 1e-9)
                 and end_xy <= WITNESS_END_XY and end_yaw <= WITNESS_END_YAW,
    }


def main(argv: list[str] | None = None) -> int:
    r"""Chạy planner trên các ca, đổi đường ra dãy cung, kiểm bằng oracle và ghi tệp đường chứng JSON.

    Ví dụ (mỗi lệnh một dòng, cmd.exe, trong thư mục `autopark`):
        .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.hard_cases --witness-out runs\witness_moi.json --time-limit 30
        .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.hard_cases --witness-out runs\witness_rrt7.json --cases parallel_122 --rung ngau-nhien --seed 7 --time-limit 60 --merge
        .venv\Scripts\python.exe -X utf8 -m autopark.evaluation.hard_cases --witness-out runs\witness_zigzag.json --cases zigzag_corridor --rung gop-ky --time-limit 30

    `--rung portfolio` gọi `portfolio.plan` như `plan_parking` (dung sai đích của ca, có bám mô
    phỏng); tên nấc khác gọi riêng bộ lập đường của nấc đó với tham số của nấc và toàn bộ
    `--time-limit` (không bám mô phỏng). 'gộp-nhanh' và 'gộp-kỹ' cùng bộ lập đường, cùng tham số,
    chỉ khác ngân sách trong thang, nên khi chạy riêng thì như nhau. `--seed` chỉ đổi hạt giống của
    nấc 'ngẫu nhiên'; biến môi trường AUTOPARK_RRT_SEED, nếu có, ghi đè nó.
    Mã thoát 0 khi mọi ca được chọn đều ghi được đường chứng hợp lệ, 1 nếu có ca không.
    """
    import argparse
    import json
    import os
    import time
    from dataclasses import replace
    from datetime import date
    from pathlib import Path

    from autopark.planning import portfolio
    from autopark.power_throttling import apply_ecoqos_policy
    from autopark.storage.scenario_store import load_vehicle_config

    ecoqos = apply_ecoqos_policy("evaluation.hard_cases")     # trước mọi việc khác: planner chạy theo hạn giờ
    ap = argparse.ArgumentParser(description="Sinh đường chứng (witness) cho bộ ca khó bằng planner")
    ap.add_argument("--witness-out", required=True, help="tệp JSON ghi ra, cùng dạng witness_20260924.json")
    ap.add_argument("--config", default="configs/vehicle_default.json")
    ap.add_argument("--cases", default="", help="tên ca, phân cách bằng dấu phẩy; bỏ trống là mọi ca")
    ap.add_argument("--time-limit", type=float, default=30.0, help="giây cho mỗi ca")
    ap.add_argument("--rung", default="portfolio", choices=["portfolio", *_RUNGS])
    ap.add_argument("--seed", type=int, default=None, help="hạt giống RRT của nấc 'ngẫu nhiên'")
    ap.add_argument("--merge", action="store_true", help="cập nhật các ca đã chọn trong tệp có sẵn, giữ các ca khác")
    args = ap.parse_args(argv)
    if args.seed is not None and args.rung not in ("portfolio", "ngau-nhien"):
        ap.error("--seed chỉ dùng với --rung portfolio hoặc ngau-nhien")

    cfg = load_vehicle_config(args.config)
    cases = build_cases(cfg)
    names = [n.strip() for n in args.cases.split(",") if n.strip()] or list(cases)
    unknown = [n for n in names if n not in cases]
    if unknown:
        ap.error(f"không có ca: {', '.join(unknown)}. Có: {', '.join(cases)}")
    env_seed = os.environ.get("AUTOPARK_RRT_SEED")
    if env_seed:
        print(f"CHÚ Ý: AUTOPARK_RRT_SEED={env_seed} ghi đè hạt giống của nấc 'ngẫu nhiên'.")

    out_path = Path(args.witness_out)
    if args.merge and out_path.exists():
        doc = json.loads(out_path.read_text(encoding="utf-8"))
        if not same_witness_geometry(doc.get("vehicle", {}), cfg.to_dict()):
            raise SystemExit(f"{out_path}: kích thước/góc lái của xe trong tệp khác {args.config}; "
                             "không gộp được, hãy ghi tệp mới")
    else:
        doc = {
            "mo_ta": ("Đường chứng (witness) cho nhãn 'feasible' của evaluation/hard_cases.py, sinh bằng "
                      "`python -m autopark.evaluation.hard_cases`. Mỗi đường là dãy cung [quãng có dấu m "
                      "(+ tiến, − lùi), độ cong 1/m (+ rẽ trái)] tính từ tư thế xuất phát của ca, mô hình "
                      "Reeds–Shepp (đổi góc lái tức thời). Planner có hạn giờ theo đồng hồ thật nên thời gian "
                      "và việc kịp hay hết giờ phụ thuộc tải máy, không phải số đo. Kiểm lại bằng "
                      "tests/test_hard_cases_labels.py (test chỉ đọc tệp trong docs/evidence/hard_cases/)."),
            "ngay": date.today().strftime("%d/%m/%Y"),
            "truong": _WITNESS_FIELDS,
            "vehicle": cfg.to_dict(),
            "cases": {},
        }

    ladder = portfolio.default_ladder()
    if args.seed is not None:
        ladder = [replace(r, params=replace(r.params, seed=args.seed)) if r.name == "ngẫu nhiên" else r
                  for r in ladder]
    seed_text = env_seed or (str(args.seed) if args.seed is not None else "mặc định")
    missing: list[str] = []
    print(f"Nấc: {args.rung}   giới hạn {args.time_limit:.0f} s/ca   xe: {cfg.name}")
    print(ecoqos.cli_line())
    for name in names:
        sc = cases[name].scenario
        goal = sc.goal.pose
        log: list = []
        t0 = time.perf_counter()
        if args.rung == "portfolio":
            params = portfolio.PortfolioParams(time_limit=args.time_limit, accept_xy=sc.goal.tolerance_xy,
                                               accept_yaw=sc.goal.tolerance_yaw, ladder=ladder)
            result = portfolio.plan(sc.start, goal, cfg, sc.obstacles, sc.bounds, params=params, attempts=log)
            source = f"portfolio.plan {args.time_limit:g} s, hạt giống RRT {seed_text}"
        else:
            rung = next(r for r in ladder if r.name == _RUNGS[args.rung])
            result = rung.planner(sc.start, goal, cfg, sc.obstacles, sc.bounds,
                                  params=replace(rung.params, time_limit=args.time_limit))
            source = (f"bộ lập đường của nấc '{rung.name}' chạy riêng {args.time_limit:g} s"
                      + (f", hạt giống {seed_text}" if args.rung == "ngau-nhien" else "")
                      + "; CHƯA qua bám mô phỏng")
        wall = time.perf_counter() - t0
        print(f"  {name:<22} {result.status:<16} {wall:6.1f} s  {result.message[:110]}")
        for a in log:
            tracked = "đạt" if a.tracked else "không"
            print(f"      nấc '{a.rung}': {a.status} {a.seconds:.2f} s, bám={tracked} {a.note[:80]}")
        traj = result.trajectory
        if traj is None:
            print("    -> không có đường, không ghi. Nếu ca không còn đường chứng nào khác thì nhãn phải về 'unknown'.")
            missing.append(name)
            continue
        arcs = [(float(f"{s:.12g}"), float(f"{k:.12g}")) for s, k in trajectory_to_arcs(traj.points)]
        stats = witness_stats(cfg, sc, arcs)
        fit = _pair_fit_error(traj.points)
        print(f"    -> {stats['cusps']} lần đổi chiều, {stats['length_m']} m, "
              f"hở nhỏ nhất {stats['min_clearance_m']} m, lệch đích {stats['end_error_m']} m / "
              f"{stats['end_error_deg']}°, sai lệch cung tròn ≤ {fit:.1e} m")
        if not stats.pop("valid"):
            print("    -> KHÔNG đạt ngưỡng đường chứng (chạm, hở dưới lề mẫu, lái quá góc, "
                  "hoặc lệch đích > 1 mm / 0,1°); không ghi.")
            missing.append(name)
            continue
        doc["cases"][name] = {"nguon": f"{source}; trạng thái {result.status}: {result.message[:120]}; "
                                       f"sinh ngày {date.today():%d/%m/%Y}",
                              **stats, "arcs": [list(a) for a in arcs]}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"Đã ghi {out_path} ({len(doc['cases'])} ca).")
    if missing:
        print(f"Không có đường chứng mới cho: {', '.join(missing)}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
