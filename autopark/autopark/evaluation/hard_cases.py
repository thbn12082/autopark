"""Bộ ca khó dùng để đo năng lực của bộ lập đường.

Mục đích: tách "dễ" khỏi "khó" bằng số đo, không bằng cảm nhận. Các ca được xếp
theo độ chặt của không gian thao tác:

Nhãn `expected` được ghi theo nhật ký thử nghiệm ngày 08/09/2026:
`feasible` khi đã có ít nhất một bộ lập đường tìm ra đường hợp lệ, hoặc khi duyệt rộng hai
chiều (đồ thị chuyển động là vô hướng nên duyệt rộng chứng minh được cả hai phía) cho hai
mặt sóng gặp nhau; `infeasible` khi mặt sóng xuất phát từ đích chỉ nở ra vài chục trạng
thái và hai mặt sóng không gặp nhau trong 600.000 trạng thái.
Lưu ý: kho mã hiện không kèm chương trình/chứng cứ để tái chạy phép duyệt này.
Vét cạn một đồ thị rời rạc chỉ chứng minh vô nghiệm trên chính đồ thị đó; chưa
đủ để kết luận cho mọi chuyển động liên tục của xe. Các nhãn này là kỳ vọng
kiểm thử đã lưu, cần kiểm chứng độc lập trước khi dùng như chứng minh hình học.

- `easy_*`  : một hoặc hai lần đổi chiều là xong.
- `tight_*` : cần vài lần tiến/lùi (3–7 cusp).
- `xtight_*`: cần rất nhiều lần đẩy tới đẩy lui (shuttle), là loại ca mà tìm kiếm
  theo lưới hay nổ số nút hoặc hết giờ.

Kích thước lấy theo xe mặc định (dài 0,31 m, rộng 0,14 m, chiều dài cơ sở 0,19 m,
lái tối đa 30° → bán kính quay tâm trục sau 0,329 m, bán kính ngoài ≈ 0,47 m).
Không dùng riêng kết quả TIMEOUT/NO_PATH để suy ra bài toán vô nghiệm.
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
        parallel_case("parallel_122", cfg, slot_len=cfg.length * 1.22, street_w=0.42, difficulty="xtight", expected="infeasible"),
        parallel_case("parallel_115", cfg, slot_len=cfg.length * 1.15, street_w=0.40, difficulty="xtight", expected="infeasible"),
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
