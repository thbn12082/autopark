"""Chốt lại các kết quả đã đo trên bộ ca khó, để lần sửa sau không âm thầm làm hỏng.

Các ngưỡng ở đây rộng hơn số đo thật khá nhiều, vì thời gian chạy phụ thuộc máy.
Số đo ngày 08/09/2026 ghi trong ngoặc ở từng test.
"""
import math

import pytest

# These tests include real-time search budgets; tracing changes the search outcome.
pytestmark = pytest.mark.planner_budget

from autopark.evaluation.bench import run_case
from autopark.evaluation.hard_cases import build_cases
from autopark.planning import portfolio
from autopark.planning.hybrid_astar import PlannerParams
from autopark.planning.parking import plan_parking
from autopark.storage.scenario_store import load_vehicle_config
from tests.conftest import PROJECT_ROOT


@pytest.fixture(scope="module")
def real_cfg():
    return load_vehicle_config(PROJECT_ROOT / "configs" / "vehicle_default.json")


@pytest.fixture(scope="module")
def cases(real_cfg):
    return build_cases(real_cfg)


def test_bo_ca_kho_van_hop_le(cases, real_cfg):
    """Mọi ca phải có xuất phát và đích hợp lệ, nếu không phép đo mất ý nghĩa."""
    from autopark.geometry.footprint import check_pose

    assert len(cases) == 16
    for name, case in cases.items():
        sc = case.scenario
        assert check_pose(real_cfg, sc.start, sc.obstacles, sc.bounds).ok, f"{name}: xuất phát xấu"
        assert check_pose(real_cfg, sc.goal.pose, sc.obstacles, sc.bounds).ok, f"{name}: đích xấu"
        assert case.expected in ("feasible", "infeasible", "unknown")


def test_ca_cot_chan_cua_o_giai_duoc_nhanh(cases, real_cfg):
    """Ca người dùng gặp: bản gốc mất 6,15 s, bản danh mục đo được 0,69 s."""
    result = run_case(portfolio.plan, cases["pillar_at_slot_mouth"], real_cfg, time_limit=8.0)
    assert result.solved, result.message
    assert result.elapsed < 4.0
    assert result.cusps <= 3


def test_duong_di_qua_ung_dung_cung_giai_duoc(cases, real_cfg):
    """Ứng dụng gọi qua `plan_parking`, nên đường đó phải cho cùng kết quả."""
    sc = cases["pillar_at_slot_mouth"].scenario
    params = PlannerParams()
    params.time_limit = 8.0
    result = plan_parking(sc, real_cfg, params)
    assert result.ok, result.message
    assert result.trajectory is not None


@pytest.mark.parametrize("name", ["parallel_135", "perp_aisle_115", "uturn_w46"])
def test_ca_truoc_day_bo_tay_nay_giai_duoc(cases, real_cfg, name):
    """Ba ca mà bản gốc trả về NO_PATH; đã đo lần lượt 5,42 s / 0,61 s / 3,70 s."""
    result = run_case(portfolio.plan, cases[name], real_cfg, time_limit=8.0)
    assert result.solved, f"{name}: {result.status} — {result.message}"


@pytest.mark.parametrize("name", ["parallel_122", "parallel_115"])
def test_ca_vo_nghiem_khong_bao_thanh_cong_gia(cases, real_cfg, name):
    """Hai ca có kỳ vọng không tìm được đường trong bộ thử đã lưu.

    Kỳ vọng này không phải chứng minh vô nghiệm liên tục. Nếu tìm được đường,
    cần kiểm tra độc lập hình học và cập nhật kỳ vọng thay vì mặc định planner sai.
    """
    assert cases[name].expected == "infeasible"
    result = run_case(portfolio.plan, cases[name], real_cfg, time_limit=4.0)
    assert not result.solved


def test_khong_hoi_quy_o_cac_ca_de(cases, real_cfg):
    """Bốn ca dễ và vừa phải luôn nhanh: đo được 0,29 s / 0,58 s / 0,33 s / 0,41 s."""
    for name in ("parallel_160", "perp_aisle_170", "reverse_long_corridor", "lateral_shift"):
        result = run_case(portfolio.plan, cases[name], real_cfg, time_limit=8.0)
        assert result.solved, f"{name}: {result.status} — {result.message}"
        assert result.elapsed < 3.0, f"{name} chậm bất thường: {result.elapsed:.2f} s"


def test_nhat_ky_leo_thang_ghi_lai_tung_nac(cases, real_cfg):
    """Danh mục phải ghi lại đã thử nấc nào, để giải thích được vì sao chậm hay hỏng."""
    sc = cases["parallel_160"].scenario
    log: list[portfolio.Attempt] = []
    result = portfolio.plan(sc.start, sc.goal.pose, real_cfg, sc.obstacles, sc.bounds,
                            time_limit=6.0, attempts=log)
    assert result.ok
    assert log, "không ghi được nấc nào"
    assert log[-1].tracked, "nấc cuối cùng phải là nấc được nhận"
    assert all(a.rung for a in log)
