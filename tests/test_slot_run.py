"""Chạy kín vòng mô phỏng một lần tự đỗ (autopark.simulation.slot_run) và cấu hình xe đo thật."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

pytest.importorskip("cv2")

from autopark.domain.types import ParkingMode, VehicleConfig  # noqa: E402
from autopark.planning import slot_finder as sf  # noqa: E402
from autopark.storage.scenario_store import load_scenario, load_vehicle_config_file  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_measured_vehicle_matches_measurements():
    cfg = load_vehicle_config_file(ROOT / "configs" / "vehicle_measured.json").cfg
    assert cfg.wheelbase == pytest.approx(0.21) and cfg.width == pytest.approx(0.16)
    assert cfg.length == pytest.approx(0.294)                        # mũi x = 0,247, đuôi x = −0,047
    assert sf.DEFAULT_VEHICLE.name == "vehicle_measured.json"


def test_wide_limits_drop_near_maneuver_distance():
    from autopark.domain.types import Bounds
    limits = sf.wide_limits(Bounds(0.0, 0.0, 2.0, 1.5))
    assert limits.max_goal_distance_m == pytest.approx(2.5) and limits.max_goal_distance_m > 0.7


def test_closed_loop_parks_measured_car_in_found_slot(tmp_path):
    from autopark.simulation import slot_run

    scenario = load_scenario(ROOT / "scenarios" / "tim_khe_vuong_goc.json")
    assert Path(scenario.vehicle_config_path).name == "vehicle_measured.json"
    cfg = VehicleConfig.from_dict(json.loads(Path(scenario.vehicle_config_path).read_text(encoding="utf-8")))
    result = slot_run.park_in_found_slot(scenario, cfg, time_limit=15.0, max_try=2)
    assert result.ok, result.summary()
    cand = result.candidates[result.chosen]
    assert cand.kind == sf.PERPENDICULAR and not cand.boundary_unknown
    assert result.mode in (ParkingMode.REVERSE_IN, ParkingMode.HEAD_IN)
    report = result.rollout.report
    assert not report.collided
    assert report.position_error <= scenario.goal.tolerance_xy
    assert abs(report.heading_error) <= scenario.goal.tolerance_yaw
    assert scenario.start.distance_to(result.run_scenario.goal.pose) > 0.7      # không có mức 0,7 m

    data = slot_run.to_dict(result)
    assert data["ok"] and data["chosen_slot"] == result.chosen + 1 and data["run"]["collision"] is None
    img = slot_run.render_run(result, cfg, scenario.start)
    assert img.ndim == 3 and img.shape[2] == 3
