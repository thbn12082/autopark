"""Nhãn `expected` của bộ ca khó phải khớp với bằng chứng hình học (định nghĩa ở đầu
`autopark/evaluation/hard_cases.py`, sửa ngày 24/09/2026).

Test không chạy planner nên kết quả không phụ thuộc tải CPU (test lệnh sinh đường chứng thay planner
bằng hàm giả). Mỗi đường chứng là một dãy cung (quãng có dấu, độ cong) nối nhau từ tư thế xuất phát.
Test tích phân lại bằng `collision_oracle.arc_pose` và kiểm va chạm bằng `collision_oracle.pose_ok`
(SAT số phức; không dùng Shapely hay FastCollisionChecker của planner). Bước mẫu h = 0,5 mm, và tại
mỗi mẫu thân xe phải còn hở ít nhất (1 + κ_max·r_max)·h/2. Giữa hai mẫu liên tiếp, một điểm bất kỳ
trên thân xe đi được nhiều nhất (1 + κ_max·r_max)·h, nên mọi tư thế xen giữa đều nằm trong vùng đã
kiểm. Nhờ vậy phép kiểm đủ để kết luận không va chạm liên tục, không chỉ tại các mẫu. Công thức lề
và ngưỡng lệch đích (1 mm / 0,1°) được chốt bằng các test riêng (24/09/2026): bổ đề dời góc thân
xe, va chạm nằm giữa hai mẫu, đích lệch hướng 0,2° hoặc lệch 2 mm. Mô hình: thân chữ nhật, vật cản
hình hộp, bỏ qua sai số dấu phẩy động. Thông số xe là giả định của `configs/vehicle_default.json`,
chưa phải số đo MN300.
"""
import dataclasses
import json
import math

import pytest

from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario
from autopark.evaluation import collision_oracle as oracle
from autopark.evaluation import hard_cases
from autopark.evaluation.hard_cases import (build_cases, parallel_case, parallel_shuffle_witness, shuffle_cycle,
                                            trajectory_to_arcs)
from autopark.planning.trajectory import build_trajectory
from autopark.storage.scenario_store import load_vehicle_config
from tests.conftest import PROJECT_ROOT

EVIDENCE_DIR = PROJECT_ROOT / "docs" / "evidence" / "hard_cases"
WITNESS_FILE = EVIDENCE_DIR / "witness_20260924.json"                    # đường từ các lần chạy planner
SHORT_WITNESS_FILE = EVIDENCE_DIR / "witness_ngan_song_song_20260924.json"  # đường ngắn dựng riêng, 122/115
STEP = 0.0005                      # m, bước mẫu dọc tâm trục sau
END_TOL_XY = 0.001                 # m, chặt hơn nhiều so với dung sai nghiệm thu 5 cm
END_TOL_YAW = math.radians(0.1)
GEOMETRY_KEYS = ("wheelbase_m", "width_m", "front_overhang_m", "rear_overhang_m", "max_steer_deg")
"""Chỉ các trường này của `VehicleConfig.to_dict()` quyết định đường chứng còn hợp lệ hay không."""

_CFG = load_vehicle_config(PROJECT_ROOT / "configs" / "vehicle_default.json")
_CASES = build_cases(_CFG)
_PARALLEL = [name for name in _CASES if name.startswith("parallel_")]


@pytest.fixture(scope="module")
def evidence() -> dict:
    return json.loads(WITNESS_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def short_evidence() -> dict:
    return json.loads(SHORT_WITNESS_FILE.read_text(encoding="utf-8"))


def _wrap(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def _sample_margin(cfg, step: float) -> float:
    """Lề phải hở tại mỗi mẫu: (1 + κ_max·r_max)·h/2, r_max = khoảng cách xa nhất từ tâm trục sau tới góc thân."""
    kappa_max = math.tan(cfg.max_steer) / cfg.wheelbase
    r_max = max(math.hypot(cfg.wheelbase + cfg.front_overhang, cfg.width / 2),
                math.hypot(cfg.rear_overhang, cfg.width / 2))
    return (1 + kappa_max * r_max) * step / 2


def _check_witness(cfg, scenario, arcs, step: float = STEP) -> list[str]:
    """Tích phân dãy cung từ xuất phát của ca; trả danh sách vi phạm (rỗng: đường chứng hợp lệ)."""
    kappa_max = math.tan(cfg.max_steer) / cfg.wheelbase
    margin = _sample_margin(cfg, step)
    problems: list[str] = []
    pose = scenario.start
    for i, (s, kappa) in enumerate(arcs):
        if not (math.isfinite(s) and math.isfinite(kappa)) or s == 0.0:
            problems.append(f"cung {i}: giá trị không hợp lệ ({s}, {kappa})")
            continue
        if abs(kappa) > kappa_max * (1 + 1e-9):
            problems.append(f"cung {i}: |độ cong| {abs(kappa):.4f} > {kappa_max:.4f} 1/m")
        steer = math.atan(kappa * cfg.wheelbase)
        n = max(1, math.ceil(abs(s) / step))
        for j in range(n + 1):
            p = oracle.arc_pose(pose, s * j / n, steer, cfg.wheelbase)
            if not oracle.pose_ok(cfg, p, scenario.obstacles, scenario.bounds, margin):
                problems.append(f"cung {i}, mẫu {j}/{n}: chạm hoặc hở dưới {margin * 1000:.2f} mm tại "
                                f"({p.x:.4f}, {p.y:.4f}, {math.degrees(p.yaw):.1f}°)")
                break
        pose = oracle.arc_pose(pose, s, steer, cfg.wheelbase)
    goal = scenario.goal.pose
    err_xy, err_yaw = math.hypot(pose.x - goal.x, pose.y - goal.y), abs(_wrap(pose.yaw - goal.yaw))
    if err_xy > END_TOL_XY or err_yaw > END_TOL_YAW:
        problems.append(f"cuối đường lệch đích {err_xy * 1000:.2f} mm / {math.degrees(err_yaw):.3f}°")
    return problems


def _cusps(arcs) -> int:
    signs = [s > 0 for s, _ in arcs]
    return sum(1 for a, b in zip(signs, signs[1:]) if a != b)


def _runs(arcs) -> list[float]:
    """Độ dài các nhịp cùng chiều."""
    runs: list[float] = []
    for i, (s, _) in enumerate(arcs):
        if i and (s > 0) == (arcs[i - 1][0] > 0):
            runs[-1] += abs(s)
        else:
            runs.append(abs(s))
    return runs


def _geometry_mismatch(vehicle: dict, cfg) -> list[str]:
    """Các trường hình học của khối "vehicle" khác với `cfg` (rỗng: đường chứng còn dùng được cho `cfg`)."""
    ref = cfg.to_dict()
    return [key for key in GEOMETRY_KEYS if key not in vehicle or abs(vehicle[key] - ref[key]) > 1e-9]


def _witnesses(name: str, evidence: dict, short: dict) -> list[tuple[str, list]]:
    found = []
    if name in evidence["cases"]:
        found.append(("planner, " + WITNESS_FILE.name, evidence["cases"][name]["arcs"]))
    if name in short["cases"]:
        found.append(("dựng riêng, " + SHORT_WITNESS_FILE.name, short["cases"][name]["arcs"]))
    if name in _PARALLEL:
        found.append(("nhích ngang giải tích", parallel_shuffle_witness(_CASES[name], _CFG)))
    return found


def test_tep_bang_chung_khop_xe_va_bo_ca(evidence, short_evidence):
    """Đường chứng chỉ có nghĩa với đúng kích thước xe và đúng bộ ca đã sinh ra nó."""
    for path, doc in ((WITNESS_FILE, evidence), (SHORT_WITNESS_FILE, short_evidence)):
        bad = _geometry_mismatch(doc["vehicle"], _CFG)
        assert not bad, (f"{path.name}: {', '.join(bad)} trong configs/vehicle_default.json đã đổi: sinh lại đường "
                         "chứng bằng lệnh ở docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md mục 6")
        assert set(doc["cases"]) <= set(_CASES), f"{path.name} có ca không còn trong bộ"
    for name, case in _CASES.items():
        assert case.expected in ("feasible", "infeasible", "unknown"), name


def test_so_xe_chi_xet_truong_hinh_hoc():
    """Đổi tên, ghi chú hay giới hạn tốc độ không làm hỏng đường chứng; đổi kích thước hay góc lái thì có."""
    harmless = dataclasses.replace(_CFG, name="xe_khac", notes="ghi chú khác", max_speed=_CFG.max_speed * 2)
    assert _geometry_mismatch(harmless.to_dict(), _CFG) == []
    assert hard_cases.same_witness_geometry(harmless.to_dict(), _CFG.to_dict())
    wider = dataclasses.replace(_CFG, width=_CFG.width + 0.001)
    assert _geometry_mismatch(wider.to_dict(), _CFG) == ["width_m"]
    assert not hard_cases.same_witness_geometry(wider.to_dict(), _CFG.to_dict())
    steer = dataclasses.replace(_CFG, max_steer=_CFG.max_steer + math.radians(0.1))
    assert _geometry_mismatch(steer.to_dict(), _CFG) == ["max_steer_deg"]
    assert not hard_cases.same_witness_geometry(steer.to_dict(), _CFG.to_dict())
    assert hard_cases.WITNESS_GEOMETRY_KEYS == GEOMETRY_KEYS    # lệnh sinh đường và test cùng một tiêu chí


@pytest.mark.parametrize("name", list(_CASES))
def test_nhan_khop_voi_duong_chung(name, evidence, short_evidence):
    """`feasible` phải có đường chứng hợp lệ; có đường chứng hợp lệ thì nhãn phải là `feasible`."""
    case = _CASES[name]
    found = _witnesses(name, evidence, short_evidence)
    if case.expected == "feasible":
        assert found, f"{name}: nhãn feasible nhưng không có đường chứng"
    for label, arcs in found:
        problems = _check_witness(_CFG, case.scenario, arcs)
        assert not problems, f"{name} ({label}): " + "; ".join(problems[:3])
    if found:
        assert case.expected == "feasible", f"{name}: có đường chứng hợp lệ nhưng nhãn là {case.expected!r}"


def test_hai_ca_song_song_chat_da_doi_nhan(evidence, short_evidence):
    """parallel_122 / parallel_115 từng ghi `infeasible` (duyệt đồ thị rời rạc, 08/09/2026).

    Đường OK mà planner trả cho parallel_122 (24/09/2026) là đường thật, không phải lỗi bộ kiểm: nó qua
    `_check_witness`. Đường planner 104 lần đổi chiều đó không thực dụng, nhưng đó là tính chất của đường,
    không phải của ca: đã có đường chứng 5 lần (122) / 13 lần (115), dựng riêng ở vòng rà soát
    24/09/2026. Số lần đổi chiều tối thiểu CHƯA BIẾT. Planner chưa ra đường nào cho parallel_115.
    """
    assert _CASES["parallel_122"].expected == "feasible"
    assert _CASES["parallel_115"].expected == "feasible"
    stored = evidence["cases"]["parallel_122"]
    assert _cusps(stored["arcs"]) == stored["cusps"] == 104
    assert "parallel_115" not in evidence["cases"]         # tệp đó chỉ chứa đường planner
    assert _cusps(parallel_shuffle_witness(_CASES["parallel_122"], _CFG)) == 121
    assert _cusps(parallel_shuffle_witness(_CASES["parallel_115"], _CFG)) == 279

    short = short_evidence["cases"]
    for name, expect in (("parallel_122", 5), ("parallel_115", 13)):
        arcs = short[name]["arcs"]
        assert _cusps(arcs) == short[name]["cusps"] == expect, name
        assert not _check_witness(_CFG, _CASES[name].scenario, arcs), name
        # Số nhỏ nhất trong các đường chứng mà test nhãn dùng: phải là đường ngắn này.
        assert min(_cusps(a) for _, a in _witnesses(name, evidence, short_evidence)) == expect, name
    assert max(abs(k) for name in short for _, k in short[name]["arcs"]) == pytest.approx(
        0.90 * math.tan(_CFG.max_steer) / _CFG.wheelbase, rel=1e-5)


def test_so_lan_doi_chieu_da_ghi_khong_phai_can_duoi():
    """Cùng hàm dựng giải tích, lái đủ δ_max và hở thiết kế 1 mm cho đường hợp lệ ít đổi chiều hơn số mặc
    định (79 < 121, 145 < 279): các con số trong tài liệu là của từng đường, không phải cận dưới."""
    for name, expect in (("parallel_122", 79), ("parallel_115", 145)):
        arcs = parallel_shuffle_witness(_CASES[name], _CFG, steer_ratio=1.0, clearance=0.001)
        assert not _check_witness(_CFG, _CASES[name].scenario, arcs), name
        assert _cusps(arcs) == expect, name


def test_so_ghi_trong_tep_khop_voi_day_cung(evidence, short_evidence):
    for path, doc in ((WITNESS_FILE, evidence), (SHORT_WITNESS_FILE, short_evidence)):
        for name, entry in doc["cases"].items():
            arcs = entry["arcs"]
            where = f"{path.name}:{name}"
            assert _cusps(arcs) == entry["cusps"], where
            assert math.isclose(sum(abs(s) for s, _ in arcs), entry["length_m"], abs_tol=1e-3), where
            steer = math.degrees(math.atan(max(abs(k) for _, k in arcs) * _CFG.wheelbase))
            assert steer == pytest.approx(entry["max_steer_deg"], abs=0.006), where
            assert min(_runs(arcs)) == pytest.approx(entry["shortest_run_m"], abs=1e-4), where


@pytest.mark.parametrize("phi, kappa, side, start", [
    (0.05, 2.51, -1, Pose(0.0, 0.0, 0.0)),
    (0.30, 3.04, +1, Pose(1.2, -0.4, 2.5)),
    (0.01, 1.00, -1, Pose(-3.0, 7.0, -1.1)),
])
def test_chu_ky_nhich_ngang_dung_cong_thuc(phi, kappa, side, start):
    """Luận cứ hình học: bốn cung trả x và hướng về như cũ, dịch ngang đúng 4(1 − cos φ)/κ."""
    arcs = shuffle_cycle(phi, kappa, side)
    assert [math.copysign(1, s) for s, _ in arcs] == [1, 1, -1, -1]
    assert all(abs(k) == kappa for _, k in arcs)
    c, s_ = math.cos(start.yaw), math.sin(start.yaw)
    pose = start
    for s, k in arcs:
        steer = math.atan(k * _CFG.wheelbase)
        for j in range(201):
            p = oracle.arc_pose(pose, s * j / 200, steer, _CFG.wheelbase)
            lx = c * (p.x - start.x) + s_ * (p.y - start.y)
            assert -1e-12 <= lx <= 2 * math.sin(phi) / kappa + 1e-12
            assert abs(_wrap(p.yaw - start.yaw)) <= phi + 1e-12
        pose = oracle.arc_pose(pose, s, steer, _CFG.wheelbase)
    lx = c * (pose.x - start.x) + s_ * (pose.y - start.y)
    ly = -s_ * (pose.x - start.x) + c * (pose.y - start.y)
    assert abs(lx) < 1e-12
    assert abs(_wrap(pose.yaw - start.yaw)) < 1e-12
    assert ly == pytest.approx(side * 4 * (1 - math.cos(phi)) / kappa, abs=1e-12)


def test_chu_ky_nhich_ngang_tu_choi_tham_so_sai():
    for args in ((0.0, 2.0, -1), (2.0, 2.0, -1), (0.1, 0.0, -1), (0.1, 2.0, 0)):
        with pytest.raises(ValueError):
            shuffle_cycle(*args)


def test_duong_nhich_ngang_chi_dung_085_goc_lai_va_tu_choi_o_qua_ngan():
    kappa_085 = math.tan(0.85 * _CFG.max_steer) / _CFG.wheelbase
    for name in _PARALLEL:
        arcs = parallel_shuffle_witness(_CASES[name], _CFG)
        assert max(abs(k) for _, k in arcs) <= kappa_085 * (1 + 1e-12), name
    too_short = parallel_case("o_ngan", _CFG, slot_len=_CFG.length + 0.01, street_w=0.42,
                              difficulty="xtight", expected="unknown")
    with pytest.raises(ValueError):
        parallel_shuffle_witness(too_short, _CFG)          # 1 cm < 2 × clearance 6 mm
    with pytest.raises(ValueError):
        parallel_shuffle_witness(_CASES["zigzag_corridor"], _CFG)


def test_bo_kiem_duong_chung_bat_duoc_duong_sai(evidence):
    """Chốt chặn: bộ kiểm phải bắt được đường chạm vật, đường không tới đích, đường lái quá góc, và đường
    tới đúng vị trí nhưng sai hướng 0,2° (hoặc lệch 2 mm)."""
    case = _CASES["parallel_122"]
    touching = parallel_shuffle_witness(case, _CFG, clearance=0.0)
    assert any("chạm" in p for p in _check_witness(_CFG, case.scenario, touching)), \
        "đường thiết kế hở 0 mm phải bị bắt"

    zig = _CASES["zigzag_corridor"]
    arcs = evidence["cases"]["zigzag_corridor"]["arcs"]
    problems = _check_witness(_CFG, zig.scenario, arcs[:-1])
    assert len(problems) == 1 and "lệch đích" in problems[0], problems

    over = [(s, k * 1.2) for s, k in arcs]
    assert any("độ cong" in p for p in _check_witness(_CFG, zig.scenario, over))

    g = zig.scenario.goal.pose
    for bad in (Pose(g.x, g.y, g.yaw + math.radians(0.2)), Pose(g.x + 0.002, g.y, g.yaw)):
        shifted = dataclasses.replace(zig.scenario, goal=ParkingGoal(bad))
        problems = _check_witness(_CFG, shifted, arcs)
        assert len(problems) == 1 and "lệch đích" in problems[0], problems


def test_bo_kiem_bat_va_cham_giua_hai_mau():
    """Một cung duy nhất, kiểm với bước thô h = 5 cm: hộp 1 mm đặt ở góc trước-ngoài của tư thế giữa cung chỉ
    bị chạm GIỮA hai mẫu (tại cả hai mẫu thân xe hở hơn 1 cm). Bộ kiểm phải bắt được nhờ lề tỉ lệ với h.
    Không chốt được hệ số κ·r bằng cách này: với xe mặc định, khoảng hở lấy mẫu lớn nhất của một va chạm
    giữa hai mẫu chỉ ≈ 0,44–0,47·h < h/2 (phân tích nháp của vòng rà soát, 24/09/2026); hệ số đó do test
    bổ đề bên dưới chốt."""
    h = 0.05
    kappa = math.tan(_CFG.max_steer) / _CFG.wheelbase
    steer = math.atan(kappa * _CFG.wheelbase)
    start = Pose(0.0, 0.0, 0.0)
    mid, end = oracle.arc_pose(start, h / 2, steer, _CFG.wheelbase), oracle.arc_pose(start, h, steer, _CFG.wheelbase)
    corner = complex(mid.x, mid.y) + complex(_CFG.wheelbase + _CFG.front_overhang, -_CFG.width / 2) * complex(
        math.cos(mid.yaw), math.sin(mid.yaw))
    box = Obstacle("hop", corner.real, corner.imag, 0.001, 0.001, 0.0)
    bounds = Bounds(-2.0, -2.0, 2.0, 2.0)
    assert not oracle.pose_ok(_CFG, mid, [box], bounds)
    assert oracle.pose_ok(_CFG, start, [box], bounds, 0.01) and oracle.pose_ok(_CFG, end, [box], bounds, 0.01)
    scenario = Scenario("giua_hai_mau", bounds, start, ParkingGoal(end), [box])
    problems = _check_witness(_CFG, scenario, [(h, kappa)], step=h)
    assert len(problems) == 1 and "chạm" in problems[0], problems


@pytest.mark.parametrize("step", [STEP, 0.01, 0.05])
@pytest.mark.parametrize("kappa_frac, direction", [(1.0, 1), (-1.0, 1), (1.0, -1), (0.5, -1)])
def test_le_mau_phu_quang_duong_moi_diem_than_xe(step, kappa_frac, direction):
    """Bổ đề của lập luận liên tục: đi h/2 dọc cung, mọi góc thân xe (điểm xa tâm quay nhất) dời không quá lề
    `_sample_margin`. Ở κ_max góc trước-ngoài dời hơn 1,3·h/2, nên bỏ số hạng κ·r là sai.

    Vì sao đúng: góc thân xe cách tâm quay R_c ≤ 1/κ + r, dời theo dây cung 2·R_c·sin(κh/4) ≤ R_c·κ·h/2
    ≤ (1 + κ_max·r_max)·h/2.
    """
    kappa = kappa_frac * math.tan(_CFG.max_steer) / _CFG.wheelbase
    steer = math.atan(kappa * _CFG.wheelbase)
    corners = [complex(a, b) for a in (-_CFG.rear_overhang, _CFG.wheelbase + _CFG.front_overhang)
               for b in (-_CFG.width / 2, _CFG.width / 2)]
    start = Pose(0.3, -0.2, 0.7)
    worst = 0.0
    for t in (0.0, 0.25, 0.5):
        a = oracle.arc_pose(start, direction * t, steer, _CFG.wheelbase)
        b = oracle.arc_pose(a, direction * step / 2, steer, _CFG.wheelbase)
        for c in corners:
            pa = complex(a.x, a.y) + c * complex(math.cos(a.yaw), math.sin(a.yaw))
            pb = complex(b.x, b.y) + c * complex(math.cos(b.yaw), math.sin(b.yaw))
            worst = max(worst, abs(pb - pa))
    assert worst <= _sample_margin(_CFG, step) * (1 + 1e-9)
    if abs(kappa_frac) == 1.0:
        assert worst > step / 2 * 1.3


def _sampled_trajectory(start: Pose, arcs, step: float = 0.01):
    """Lấy mẫu dãy cung như planner (mỗi `step` một điểm) và dựng Trajectory; trả kèm quãng tích lũy của mỗi mẫu."""
    raw, stations = [], []
    pose, travelled = start, 0.0
    for s, k in arcs:
        steer = math.atan(k * _CFG.wheelbase)
        n = max(1, math.ceil(abs(s) / step))
        for j in range(0 if not raw else 1, n + 1):
            raw.append((oracle.arc_pose(pose, s * j / n, steer, _CFG.wheelbase), 1 if s > 0 else -1, steer))
            stations.append(travelled + abs(s) * j / n)
        pose = oracle.arc_pose(pose, s, steer, _CFG.wheelbase)
        travelled += abs(s)
    return build_trajectory(raw, pose, _CFG, 0.15, 0.08, 0.30), raw, stations


def _pose_at(start: Pose, arcs, station: float) -> Pose:
    """Tư thế sau khi đi `station` mét (không dấu) dọc dãy cung."""
    pose = start
    for s, k in arcs:
        steer = math.atan(k * _CFG.wheelbase)
        if station <= abs(s) + 1e-12:
            return oracle.arc_pose(pose, math.copysign(station, s), steer, _CFG.wheelbase)
        pose = oracle.arc_pose(pose, s, steer, _CFG.wheelbase)
        station -= abs(s)
    return pose


def test_doi_quy_dao_ra_day_cung_tai_tich_phan_dung():
    """`trajectory_to_arcs` (lệnh sinh đường chứng dùng nó) phải khôi phục đúng dãy cung từ quỹ đạo lấy mẫu:
    đủ tiến/lùi, cả hai dấu độ cong, một đoạn thẳng, điểm lặp ở chỗ đổi chiều; tái tích phân khớp mọi
    điểm mẫu trong 1 µm và giữ nguyên số lần đổi chiều."""
    start = Pose(0.4, 0.3, 0.2)
    arcs = [(0.12, 2.5), (0.05, 0.0), (-0.08, -3.0), (-0.03, 1.2), (0.2, -1.5), (0.1, 1.5)]
    traj, raw, stations = _sampled_trajectory(start, arcs)
    assert len(traj.points) > len(raw)                     # build_trajectory lặp điểm ở chỗ đổi chiều
    got = trajectory_to_arcs(traj.points)
    assert _cusps(got) == _cusps(arcs) == 2
    assert len(got) == len(arcs)
    for (s0, k0), (s1, k1) in zip(arcs, got):
        assert s1 == pytest.approx(s0, abs=1e-9) and k1 == pytest.approx(k0, abs=1e-6)
    for (pose, _, _), station in zip(raw, stations):
        p = _pose_at(start, got, station)
        assert math.hypot(p.x - pose.x, p.y - pose.y) < 1e-6
        assert abs(_wrap(p.yaw - pose.yaw)) < 1e-6
    assert trajectory_to_arcs([pt.pose for pt in traj.points]) == got     # nhận cả Pose trần
    assert hard_cases._pair_fit_error(traj.points) < 1e-9


def test_so_do_cua_lenh_sinh_duong_chung_khop_bo_kiem(evidence, short_evidence):
    """`hard_cases.witness_stats` (lệnh sinh đường dùng để quyết định có ghi hay không) phải cho cùng số đo
    với tệp đã lưu, và từ chối đúng những gì `_check_witness` từ chối: hở dưới lề mẫu, lệch đích."""
    for doc, name in ((evidence, "parallel_160"), (short_evidence, "parallel_122")):
        entry = doc["cases"][name]
        st = hard_cases.witness_stats(_CFG, _CASES[name].scenario, entry["arcs"])
        assert st["valid"], name
        assert st["cusps"] == entry["cusps"] and st["length_m"] == pytest.approx(entry["length_m"], abs=1e-4)
        assert st["shortest_run_m"] == pytest.approx(entry["shortest_run_m"], abs=1e-4)
    assert st["min_clearance_m"] == pytest.approx(short_evidence["cases"]["parallel_122"]["min_clearance_oracle_m"])
    # Bước 4 mm cần lề mẫu ≈ 3,6 mm > hở 1,6 mm của đường ngắn: cả hai bộ kiểm cùng từ chối, dù không chạm.
    arcs = short_evidence["cases"]["parallel_122"]["arcs"]
    assert not hard_cases.witness_stats(_CFG, _CASES["parallel_122"].scenario, arcs, step=0.004)["valid"]
    assert _check_witness(_CFG, _CASES["parallel_122"].scenario, arcs, step=0.004)
    assert not hard_cases.witness_stats(_CFG, _CASES["parallel_122"].scenario, arcs[:-1])["valid"]


def test_lenh_sinh_duong_chung_ghi_tep_ma_test_chap_nhan(tmp_path, monkeypatch, evidence):
    """Lệnh `python -m autopark.evaluation.hard_cases`, với planner thay bằng hàm giả (không phụ thuộc tải):
    đường hợp lệ được ghi đúng dạng và qua `_check_witness`; ca không có đường hoặc đường lệch đích thì
    không ghi và mã thoát là 1; `--merge` giữ các ca cũ."""
    from autopark.planning import portfolio
    from autopark.planning.hybrid_astar import PlanResult

    case = _CASES["parallel_160"]
    arcs = evidence["cases"]["parallel_160"]["arcs"]
    good, _, _ = _sampled_trajectory(case.scenario.start, arcs)
    short_of_goal, _, _ = _sampled_trajectory(case.scenario.start, arcs[:-1])
    calls = []
    mode = {"traj": good}

    def fake_plan(start, goal, cfg, obstacles, bounds, params=None, attempts=None):
        calls.append(params)
        if attempts is not None:
            attempts.append(portfolio.Attempt("giả", "OK", 0.0, True))
        if goal == case.scenario.goal.pose and mode["traj"] is not None:
            return PlanResult("OK", "đường giả", mode["traj"])
        return PlanResult("NO_PATH", "không có đường (giả)")

    monkeypatch.setattr(portfolio, "plan", fake_plan)
    out = tmp_path / "w.json"
    config = str(PROJECT_ROOT / "configs" / "vehicle_default.json")
    base = ["--witness-out", str(out), "--config", config, "--time-limit", "7"]

    assert hard_cases.main(base + ["--cases", "parallel_160,uturn_w70"]) == 1      # uturn_w70: NO_PATH
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert set(doc["cases"]) == {"parallel_160"}
    assert not _geometry_mismatch(doc["vehicle"], _CFG)
    entry = doc["cases"]["parallel_160"]
    assert not _check_witness(_CFG, case.scenario, entry["arcs"])
    assert entry["cusps"] == _cusps(entry["arcs"]) == _cusps(arcs)
    assert entry["length_m"] == pytest.approx(sum(abs(s) for s, _ in arcs), abs=1e-4)
    assert "portfolio.plan 7 s" in entry["nguon"]
    assert all(isinstance(p, portfolio.PortfolioParams) and p.time_limit == 7.0
               and p.accept_xy == case.scenario.goal.tolerance_xy for p in calls)

    assert hard_cases.main(base + ["--cases", "uturn_w70", "--merge"]) == 1
    assert set(json.loads(out.read_text(encoding="utf-8"))["cases"]) == {"parallel_160"}

    mode["traj"] = short_of_goal                             # đường thiếu cung cuối: lệch đích, không được ghi
    assert hard_cases.main(base + ["--cases", "parallel_160"]) == 1
    assert json.loads(out.read_text(encoding="utf-8"))["cases"] == {}

    with pytest.raises(SystemExit):
        hard_cases.main(base + ["--rung", "gop-ky", "--seed", "3"])       # hạt giống chỉ dành cho nấc ngẫu nhiên


def test_khe_zigzag_chan_moi_le_tim_kiem_tu_15_cm():
    """Khe giữa đầu tường t3 và tường t2 rộng 17 cm, xe rộng 14 cm (giả định).

    Khi tâm hình học của thân xe nằm trên đường giữa khe, dây cung qua tâm dài ít nhất bằng bề
    rộng xe, nên nới thân xe thêm 1,5 cm + 0,5 mm thì mọi hướng đều chạm (test lấy mẫu hướng mỗi
    2°, vị trí mỗi 1 mm); nới 1,4 cm thì còn tư thế lọt. Suy luận trong tài liệu (mục 6 của
    docs/KIEM_THU_DO_BEN_GIAI_DOAN_0.md): đường nào tới đích cũng phải qua khe này, nên tìm kiếm
    dùng lề từ 1,5 cm trở lên không thể ra đường cho ca này. Test chỉ chốt phần cục bộ ở khe.
    """
    zig = _CASES["zigzag_corridor"].scenario
    walls = {o.id: o for o in zig.obstacles}
    left = walls["t3"].cx + walls["t3"].width / 2
    right = walls["t2"].cx - walls["t2"].width / 2
    y_mid = walls["t3"].cy
    assert right - left == pytest.approx(0.17, abs=1e-9)
    assert (right - left) - _CFG.width == pytest.approx(0.03, abs=1e-9)
    to_center = _CFG.length / 2 - _CFG.rear_overhang

    def free_somewhere(margin: float) -> bool:
        for deg in range(0, 360, 2):
            yaw = math.radians(deg)
            for i in range(0, 171):
                cx = left + i / 1000
                pose = Pose(cx - to_center * math.cos(yaw), y_mid - to_center * math.sin(yaw), yaw)
                if oracle.pose_ok(_CFG, pose, zig.obstacles, zig.bounds, margin):
                    return True
        return False

    assert not free_somewhere(0.0155)
    assert free_somewhere(0.0140)
