import math
from pathlib import Path

import pytest

from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario, VehicleConfig
from autopark.power_throttling import KEEP_ECOQOS_ENV, apply_ecoqos_policy

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Test có hạn giờ (dấu `planner_budget`) phải đo thuật toán, không đo cách Windows xếp lịch. Tiến trình pytest không có
# cửa sổ (mở từ shell chạy nền) có thể bị Windows 11 áp EcoQoS dù máy rảnh: đo 30/09/2026, nhóm `planner_budget` hỏng
# 1–3 test và chậm tới ≈ 3 lần (docs/CHUYEN_MAY_BAN.md mục 8). Nên tắt EcoQoS cho tiến trình pytest (tiến trình con mà
# test mở thì không). Đặt AUTOPARK_KEEP_ECOQOS=1 để giữ mặc định của Windows, ví dụ khi muốn đo đúng điều kiện đó.
# Từ 02/10/2026 dùng chung `apply_ecoqos_policy` với ứng dụng và công cụ đo (cùng biến, cùng quy tắc "đúng bằng 1").
ECOQOS_KEY = pytest.StashKey[str]()


def pytest_configure(config):
    # tắt (trừ khi AUTOPARK_KEEP_ECOQOS=1) rồi đọc lại trạng thái thật: "off" (đã tắt), "system" (Windows tự quyết),
    # "on"; "unknown" ngoài Windows
    config.stash[ECOQOS_KEY] = apply_ecoqos_policy("pytest").state


def pytest_report_header(config):
    return f"EcoQoS của tiến trình pytest: {config.stash[ECOQOS_KEY]} (tests/conftest.py, {KEEP_ECOQOS_ENV})"


@pytest.fixture(scope="session", autouse=True)
def _ecoqos_in_junit(request):
    """Ghi trạng thái EcoQoS vào tệp JUnit (thuộc tính `ecoqos` của testsuite), để tệp bằng chứng tự nói điều kiện đo.
    Không có plugin junitxml (`-p no:junitxml`) thì bỏ qua, không làm lỗi mọi test."""
    if request.config.pluginmanager.hasplugin("junitxml"):
        request.getfixturevalue("record_testsuite_property")("ecoqos", request.config.stash[ECOQOS_KEY])


@pytest.fixture
def cfg() -> VehicleConfig:
    return VehicleConfig(
        name="xe_test",
        wheelbase=0.19,
        width=0.14,
        front_overhang=0.06,
        rear_overhang=0.06,
        max_steer=math.radians(30),
        max_speed=0.3,
        max_accel=0.3,
        max_decel=0.6,
        max_steer_rate=math.radians(90),
    )


@pytest.fixture
def bounds() -> Bounds:
    return Bounds(0.0, 0.0, 3.0, 2.0)


@pytest.fixture
def scenario(bounds: Bounds) -> Scenario:
    return Scenario(
        name="test",
        bounds=bounds,
        start=Pose(0.5, 1.0, 0.0),
        goal=ParkingGoal(Pose(2.4, 0.4, math.pi / 2)),
        obstacles=[Obstacle("hop_1", 1.2, 1.0, 0.2, 0.2, 0.0)],
    )
