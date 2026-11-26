"""Independent geometry and reporting invariants for the maneuver scorer."""
import math

import pytest

from autopark.evaluation.collision_oracle import rectangle
from autopark.evaluation.maneuver_cases import build_cases
from autopark.evaluation.maneuver_score import polygon_distance, score_leg, summarize


@pytest.mark.parametrize("angle", [0, math.pi / 7, -math.pi / 2])
def test_polygon_separation_is_invariant_under_rigid_rotation(angle):
    a = rectangle(0, 0, angle, -1, 1, -1, 1)
    b = rectangle(3 * math.cos(angle), 3 * math.sin(angle), angle, -1, 1, -1, 1)
    assert polygon_distance(a, b) == pytest.approx(1)


def test_polygon_contact_and_overlap_are_not_clearance():
    a = rectangle(0, 0, 0, -1, 1, -1, 1)
    assert polygon_distance(a, rectangle(2, 0, 0, -1, 1, -1, 1)) == 0
    assert polygon_distance(a, rectangle(.3, .5, .2, -1, 1, -1, 1)) == 0


def test_summary_does_not_count_safe_stops_as_completed_maneuvers():
    rows = [
        {"expected": "complete", "actual_outcome": "stopped", "verdict": "FAIL", "family": "corner", "seed": 0},
        {"expected": "stop", "actual_outcome": "stopped", "verdict": "PASS", "family": "fault", "seed": 0},
        {"expected": "refuse", "actual_outcome": "refused", "verdict": "PASS", "family": "invalid", "seed": 1},
    ]
    result = summarize(rows)
    assert result["overall"]["passed"] == 2 and result["overall"]["total"] == 3
    assert result["by_expected"]["complete"]["passed"] == 0
    assert result["by_expected"]["stop"]["passed"] == 1
    assert result["by_expected"]["refuse"]["passed"] == 1
    assert result["by_seed"]["0"]["total"] == 2


@pytest.mark.parametrize("status", ["NO_PATH", "TIMEOUT", "ERROR", "CANCELLED", "TRACKING_FAILED"])
def test_search_failures_cannot_satisfy_expected_refusal(status):
    case = next(c for c in build_cases(0) if c.case_id == "refuse_goal_overlap")
    result = score_leg(case, [], [], plan_status=status)
    assert result["verdict"] == "FAIL"
    assert result["actual_outcome"] != "refused"
