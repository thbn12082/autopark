"""Thao tác gần tự quy định giới hạn; dữ liệu nghiệm thu cũ không đổi hành vi chạy."""
from dataclasses import replace

import pytest

from autopark.application.cusp_policy import CuspPolicy, SOURCE_CLI, SOURCE_MANEUVER, resolve_cusp_limit
from autopark.application.session import Session
from autopark.domain.types import AcceptanceTag
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from tests.conftest import PROJECT_ROOT


@pytest.mark.parametrize("local,cli,expected,source,ignored", [
    (3, None, 3, SOURCE_MANEUVER, False),
    (3, 9, 3, SOURCE_MANEUVER, True),
    (3, 3, 3, SOURCE_MANEUVER, False),
    (3, 2, 2, SOURCE_CLI, False),
    (3, 0, 0, SOURCE_CLI, False),
    (0, 3, 0, SOURCE_MANEUVER, True),
])
def test_user_limit_can_only_tighten_the_maneuver(local, cli, expected, source, ignored):
    limit = resolve_cusp_limit(CuspPolicy(cli, 1), local)
    assert limit.policy == CuspPolicy(expected, 1)
    assert limit.source == source and limit.cli_ignored == ignored
    assert limit.to_dict()["max_cusps"] == expected


def test_legacy_acceptance_tag_is_metadata_only(scenario, cfg):
    scenario.acceptance = AcceptanceTag("DO-9")  # Không tồn tại trong bảng nghiệm thu cũ.
    session = Session(scenario, cfg)
    try:
        assert session.cusp_limit().policy.max_cusps == scenario.maneuver.max_cusps == 3
        changed = replace(scenario, maneuver=replace(scenario.maneuver, max_cusps=1))
        session.replace_scenario(changed, cfg)
        assert session.cusp_limit().policy.max_cusps == 1
    finally:
        session.close()


@pytest.mark.parametrize("path", sorted((PROJECT_ROOT / "scenarios").glob("*.json")), ids=lambda p: p.stem)
def test_public_scenarios_support_the_current_application(path):
    scenario = load_scenario(path)
    session = Session(scenario, load_vehicle_config(scenario.vehicle_config_path))
    try:
        assert scenario.maneuver is not None and scenario.slot is None
        assert session.start_check().ok and session.goal_check().ok
    finally:
        session.close()
