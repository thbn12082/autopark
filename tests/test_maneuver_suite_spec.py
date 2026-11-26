"""Portable evaluation inputs keep their units, fault timing and test intent."""
from dataclasses import replace
import json
import math

import pytest

from autopark.domain.types import Pose
from autopark.evaluation.maneuver_suite_spec import EvaluationCriteria, FaultSpec, ManeuverCase
from autopark.simulation.feedback import FeedbackConfig


def case(scenario, cfg):
    return ManeuverCase("stop_then_continue", "continuation", "Recovery requires a new user action", "stop",
                        scenario, cfg, FeedbackConfig(delay_s=.04, yaw_std_rad=math.radians(.5)),
                        FaultSpec("data_loss", .5, recover_after_s=.6), Pose(1, 1, math.pi / 2),
                        EvaluationCriteria(max_stop_delay_s=.5, max_stop_distance_m=.05))


def test_artifact_roundtrip_preserves_units_and_recovery_contract(scenario, cfg):
    original = case(scenario, cfg)
    raw = json.loads(json.dumps(original.to_dict(), allow_nan=False))
    restored = ManeuverCase.from_dict(raw)
    assert restored.to_dict() == raw
    assert restored.followup_goal.yaw == pytest.approx(math.pi / 2)
    assert restored.feedback.yaw_std_rad == pytest.approx(math.radians(.5))
    assert restored.fault.recover_after_s == .6
    assert restored.criteria.max_stop_distance_m == .05


def test_refusal_input_is_not_mistaken_for_an_invalid_test(scenario, cfg):
    scenario.goal = replace(scenario.goal, pose=Pose(20, 20, 0))
    original = ManeuverCase("far_goal", "refusal", "Reject a goal outside the local scope", "refuse", scenario, cfg)
    assert ManeuverCase.from_dict(original.to_dict()).scenario.goal.pose == Pose(20, 20, 0)


@pytest.mark.parametrize("identifier", ["../escape", "nested/case", "C:drive", ".", "", "a" * 81])
def test_identifiers_cannot_escape_artifact_directory(scenario, cfg, identifier):
    with pytest.raises(ValueError, match="case_id"):
        replace(case(scenario, cfg), case_id=identifier)


def test_misspelled_budget_cannot_silently_fall_back(scenario, cfg):
    raw = case(scenario, cfg).to_dict()
    raw["sim_timeout"] = raw.pop("sim_timeout_s")
    with pytest.raises(ValueError, match="Unknown case fields"):
        ManeuverCase.from_dict(raw)


def test_incomplete_fault_has_actionable_schema_error(scenario, cfg):
    raw = case(scenario, cfg).to_dict()
    del raw["fault"]["at_s"]
    with pytest.raises(ValueError, match="Missing fault fields: at_s"):
        ManeuverCase.from_dict(raw)


def test_zero_hold_is_rejected_instead_of_claiming_unobserved_standstill():
    with pytest.raises(ValueError, match="hold_after_stop_s must be finite and positive"):
        EvaluationCriteria(hold_after_stop_s=0)


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema_version=True),
    lambda d: d["scenario"].update(seed=True),
    lambda d: d["criteria"].update(max_stop_distance_m=float("nan")),
    lambda d: d["fault"].update(kind="serial_port"),
    lambda d: d.update(expected="infeasible"),
])
def test_malformed_artifact_is_rejected_before_execution(scenario, cfg, mutation):
    raw = case(scenario, cfg).to_dict()
    mutation(raw)
    with pytest.raises(ValueError):
        ManeuverCase.from_dict(raw)
