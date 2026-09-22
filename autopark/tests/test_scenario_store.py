import json
import math

import pytest
from pytest import approx

from autopark.domain.types import Scenario, VehicleConfig
from autopark.storage.scenario_store import load_scenario, load_vehicle_config, save_scenario, save_vehicle_config
from tests.conftest import PROJECT_ROOT


def test_default_files_load():
    scenario = load_scenario(PROJECT_ROOT / "scenarios" / "sa_ban_3x2_hai_hop.json")
    cfg = load_vehicle_config(scenario.vehicle_config_path)
    assert cfg.wheelbase == approx(0.19)
    assert cfg.max_steer == approx(math.radians(30))
    assert scenario.goal.pose.yaw == approx(math.pi / 2)
    assert [o.id for o in scenario.obstacles] == ["hop_1", "hop_2"]
    assert scenario.bounds.width == approx(3.0)


def test_round_trip(tmp_path, scenario, cfg):
    cfg_path = save_vehicle_config(cfg, tmp_path / "configs" / "xe.json")
    scenario.vehicle_config_path = cfg_path
    path = save_scenario(scenario, tmp_path / "scenarios" / "kb.json")
    loaded = load_scenario(path)
    assert loaded.to_dict() == scenario.to_dict()
    assert loaded.vehicle_config == "../configs/xe.json"
    assert loaded.vehicle_config_path == cfg_path.resolve()
    assert load_vehicle_config(loaded.vehicle_config_path) == cfg


def test_rejects_unknown_schema(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": 2, "name": "x"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_scenario(path)


def test_rejects_duplicate_obstacle_ids(scenario):
    data = scenario.to_dict()
    data["obstacles"].append(dict(data["obstacles"][0]))
    with pytest.raises(ValueError):
        Scenario.from_dict(data)


def test_invalid_vehicle_config_is_rejected(cfg):
    data = cfg.to_dict()
    data["max_steer_deg"] = 0.0
    with pytest.raises(ValueError):
        VehicleConfig.from_dict(data)


def test_next_obstacle_id_skips_existing(scenario):
    assert scenario.next_obstacle_id() == "hop_2"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("field", ["wheelbase_m", "max_speed_mps", "width_m"])
def test_nonfinite_vehicle_config_is_rejected(cfg, field, value):
    data = cfg.to_dict()
    data[field] = value
    with pytest.raises(ValueError):
        VehicleConfig.from_dict(data)


@pytest.mark.parametrize("section,field,value", [
    ("start", "x", float("nan")),
    ("start", "yaw_deg", float("nan")),
    ("bounds", "xmax", float("inf")),
    ("goal", "tolerance_cm", -1.0),
    ("goal", "tolerance_deg", float("nan")),
])
def test_invalid_scenario_numbers_are_rejected(scenario, section, field, value):
    data = scenario.to_dict()
    data[section][field] = value
    with pytest.raises(ValueError):
        Scenario.from_dict(data)


@pytest.mark.parametrize("field,value", [("width", -0.2), ("height", 0.0),
                                         ("cx", float("nan")), ("yaw_deg", float("nan"))])
def test_invalid_obstacle_numbers_are_rejected(scenario, field, value):
    data = scenario.to_dict()
    data["obstacles"][0][field] = value
    with pytest.raises(ValueError):
        Scenario.from_dict(data)


def test_save_falls_back_to_absolute_posix_path_across_drives(tmp_path, monkeypatch):
    """Windows: kịch bản trên ổ khác cấu hình xe không có đường dẫn tương đối; phải vẫn nạp lại được."""
    import os
    from autopark.storage import scenario_store
    from autopark.storage.scenario_store import load_scenario, save_scenario

    scenario = load_scenario(scenario_store.__file__.rsplit("autopark", 2)[0] + "autopark/scenarios/bai_do_xe.json")
    original = os.path.relpath

    def cross_drive(path, start):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")
    monkeypatch.setattr(scenario_store.os.path, "relpath", cross_drive)
    saved = save_scenario(scenario, tmp_path / "xa.json")
    monkeypatch.setattr(scenario_store.os.path, "relpath", original)
    assert "\\" not in scenario.vehicle_config and scenario.vehicle_config.endswith("vehicle_default.json")
    reloaded = load_scenario(saved)
    assert reloaded.vehicle_config_path.exists() and reloaded.vehicle_config_path.name == "vehicle_default.json"
