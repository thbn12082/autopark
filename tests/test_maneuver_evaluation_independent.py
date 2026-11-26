"""Adversarial offline evidence checks, independent of planner and vehicle model.

Synthetic traces integrate an analytic trapezoidal velocity profile. Expected
distances, polygon contacts and invalid requests are calculated directly; no
production collision checker, tracker, planner or world determines the answer.
"""
from copy import deepcopy
from dataclasses import replace
import math

import pytest

from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario
from autopark.evaluation.collision_oracle import pose_ok
from autopark.evaluation.maneuver_cases import build_cases, build_geometric_witnesses
from autopark.evaluation.maneuver_robustness import build_robustness_cases
from autopark.evaluation.maneuver_score import polygon_distance, score_leg
from autopark.evaluation.maneuver_suite_spec import EvaluationCriteria, FaultSpec, ManeuverCase


DT = .005


def _case(*, expected="complete", goal_x=.15, fault=None):
    prototype = build_robustness_cases()[0]
    return ManeuverCase(
        "independent_trace", "independent", "Analytic offline test evidence", expected,
        Scenario("analytic", Bounds(-1, -1, 1, 1), Pose(0, 0, 0),
                 ParkingGoal(Pose(goal_x, 0, 0), .005, math.radians(1)), seed=0),
        prototype.vehicle, fault=fault,
        criteria=EvaluationCriteria(max_stop_delay_s=.6, max_stop_distance_m=.03),
    )


def _event(kind, t, *, sim_t=None, **extra):
    return dict(kind=kind, clock_s=t, sim_time_s=t if sim_t is None else sim_t, **extra)


def _analytic_trace(directions=(1,), terminal="COMPLETED"):
    """Every 2 s leg covers exactly 0.15 m; 1.005 s terminal hold follows.

    v(t)=min(0.2t, 0.1, 0.2(2-t)); trapezoidal integration is exact at
    the sample-aligned corners. This deliberately does not use SimVehicle.
    """
    rows = []
    x, previous_speed = 0.0, 0.0
    motion_steps = 400 * len(directions)
    for i in range(motion_steps + 202):
        clock = i * DT
        if i <= motion_steps:
            local_index = min(i // 400, len(directions) - 1)
            t = clock - 2 * local_index
            speed = directions[local_index] * max(0.0, min(.2 * t, .1, .2 * (2 - t)))
            if i:
                x += (previous_speed + speed) * DT / 2
            previous_speed = speed
            state = terminal if i == motion_steps else "RUNNING"
            sim_t, phase = clock, "motion"
        else:
            speed, sim_t, phase, state = 0.0, motion_steps * DT, "hold", terminal
        rows.append(dict(clock_s=clock, sim_time_s=sim_t, x=x, y=0.0, yaw_rad=0.0,
                         speed_mps=speed, steer_rad=0.0, command_speed_mps=speed,
                         command_steer_rad=0.0, state=state, phase=phase))
    return rows


def _events(*, stop=False):
    events = [_event("explicit_start", 0)]
    if stop:
        events.extend((_event("fault_applied", 1.5, fault_kind="user_stop"),
                       _event("stop_decision", 1.5, code="USER_STOP")))
    events.append(_event("terminal", 2, state="STOPPED" if stop else "COMPLETED"))
    return events


def _stop_case():
    return _case(expected="stop", goal_x=.45, fault=FaultSpec("user_stop", 1.5))


def test_analytic_trace_measures_distance_clearance_and_missing_obstacles():
    result = score_leg(_case(), _analytic_trace(), _events(), terminal_state="COMPLETED")
    assert result["verdict"] == "PASS", result
    metrics = result["metrics"]
    assert metrics["total_actual_distance_m"] == pytest.approx(.15, abs=1e-12)
    assert metrics["min_boundary_clearance_m"] == pytest.approx(.60, abs=1e-12)
    assert metrics["min_local_boundary_clearance_m"] == pytest.approx(.35, abs=1e-12)
    assert metrics["min_obstacle_clearance_m"] is None
    assert metrics["stop_delay_s"] is None
    assert metrics["stop_distance_m"] is None


@pytest.mark.parametrize("offset, expected", [(complex(2, 0), 1.0), (complex(2, 2), math.sqrt(2)),
                                              (complex(1, 0), 0.0), (complex(.5, 0), 0.0)])
def test_polygon_clearance_matches_hand_calculated_unit_squares(offset, expected):
    square = (0j, 1+0j, 1+1j, 1j)
    assert polygon_distance(square, tuple(p+offset for p in square)) == pytest.approx(expected)


@pytest.mark.parametrize("mutate", [
    lambda rows: rows.clear(),
    lambda rows: rows[10].update(x=float("nan")),
    lambda rows: rows[10].update(speed_mps=float("inf")),
    lambda rows: rows[10].update(speed_mps=True),
    lambda rows: rows[10].pop("yaw_rad"),
    lambda rows: rows.pop(10),
    lambda rows: rows[10].update(clock_s=0),
    lambda rows: rows[10].update(phase="unknown"),
    lambda rows: rows.__setitem__(10, None),
])
def test_malformed_truth_never_passes_or_becomes_zero_metrics(mutate):
    rows = _analytic_trace()
    mutate(rows)
    result = score_leg(_case(), rows, _events(), terminal_state="COMPLETED")
    assert result["verdict"] == "FAIL"
    assert result["metrics"].get("total_actual_distance_m") is None


def test_completed_flag_cannot_replace_goal_tolerance():
    result = score_leg(_case(goal_x=.40), _analytic_trace(), _events(), terminal_state="COMPLETED")
    assert result["verdict"] == "FAIL"
    assert result["actual_outcome"] != "completed"


def test_completed_flag_cannot_replace_standstill():
    rows = _analytic_trace()
    for row in rows[400:]:
        row["speed_mps"] = .01
    result = score_leg(_case(), rows, _events(), terminal_state="COMPLETED")
    assert result["verdict"] == "FAIL"


def test_front_corner_contact_is_detected_even_when_rear_axle_path_is_clear():
    case = _case()
    # At x=.15, the nose reaches .40 and side reaches .07. This obstacle
    # occupies x=.36..38, y=.065..085 and therefore clips the front corner.
    obstacle = Obstacle("corner", .37, .075, .02, .02)
    case.scenario.obstacles.append(obstacle)
    assert all(row["y"] < .065 for row in _analytic_trace())
    assert not pose_ok(case.vehicle, case.scenario.goal.pose, [obstacle], case.scenario.bounds)
    result = score_leg(case, _analytic_trace(), _events(), terminal_state="COMPLETED")
    assert result["verdict"] == "FAIL"
    assert result["actual_outcome"] == "collision"
    assert result["metrics"]["min_obstacle_clearance_m"] == 0


def test_whole_body_must_stay_in_bounds_not_just_rear_axle():
    case = _case()
    case.scenario.bounds = Bounds(-1, -1, .39, 1)
    result = score_leg(case, _analytic_trace(), _events(), terminal_state="COMPLETED")
    assert result["verdict"] == "FAIL"
    assert result["metrics"]["min_boundary_clearance_m"] == pytest.approx(-.01)


@pytest.mark.parametrize("status", ["TIMEOUT", "NO_PATH", "ERROR", "CANCELLED"])
def test_search_failure_is_not_expected_refusal(status):
    case = replace(_case(), expected="refuse")
    case.scenario.obstacles.append(Obstacle("start_only", -.05, 0, .02, .02))
    result = score_leg(case, [], [], plan_status=status)
    assert result["verdict"] == "FAIL"
    assert result["actual_outcome"] != "refused"


def test_refusal_code_must_match_independent_invalid_request_evidence():
    case = replace(_case(), expected="refuse")
    case.scenario.obstacles.append(Obstacle("start_only", -.05, 0, .02, .02))
    assert not pose_ok(case.vehicle, case.scenario.start, case.scenario.obstacles, case.scenario.bounds)
    assert pose_ok(case.vehicle, case.scenario.goal.pose, case.scenario.obstacles, case.scenario.bounds)
    assert score_leg(case, [], [], plan_status="START_INVALID")["verdict"] == "PASS"
    assert score_leg(case, [], [], plan_status="GOAL_INVALID")["verdict"] == "FAIL"


def test_invalid_request_status_without_invalid_geometry_fails():
    assert score_leg(replace(_case(), expected="refuse"), [], [], plan_status="GOAL_INVALID")["verdict"] == "FAIL"


@pytest.mark.parametrize("events", [[_event("explicit_start", 0)], [_event("fault_applied", 0, fault_kind="user_stop")],
                                     [{"kind": "unknown", "clock_s": float("nan"), "sim_time_s": 0}]])
def test_refusal_cannot_ignore_contradictory_or_malformed_execution_events(events):
    case = replace(_case(), expected="refuse")
    case.scenario.obstacles.append(Obstacle("start_only", -.05, 0, .02, .02))
    assert score_leg(case, [], events, plan_status="START_INVALID")["verdict"] == "FAIL"


def test_stop_has_analytic_braking_evidence():
    result = score_leg(_stop_case(), _analytic_trace(terminal="STOPPED"), _events(stop=True), terminal_state="STOPPED")
    assert result["verdict"] == "PASS", result
    # Threshold .001 m/s is reached at 1.995 s; integrating the last .005 s
    # adds 2.5 micrometres, hence the measured distance is .025 - .0000025.
    assert result["metrics"]["stop_delay_s"] == pytest.approx(.495)
    assert result["metrics"]["stop_distance_m"] == pytest.approx(.0249975)


@pytest.mark.parametrize("mutation", ["missing_fault", "missing_decision", "wrong_code", "wrong_fault"])
def test_stop_requires_actual_injection_and_matching_decision(mutation):
    events = _events(stop=True)
    if mutation == "missing_fault":
        events = [e for e in events if e["kind"] != "fault_applied"]
    elif mutation == "missing_decision":
        events = [e for e in events if e["kind"] != "stop_decision"]
    elif mutation == "wrong_code":
        next(e for e in events if e["kind"] == "stop_decision")["code"] = "MAP_CHANGED"
    else:
        next(e for e in events if e["kind"] == "fault_applied")["fault_kind"] = "data_loss"
    assert score_leg(_stop_case(), _analytic_trace(terminal="STOPPED"), events, terminal_state="STOPPED")["verdict"] == "FAIL"


def test_stop_metric_cannot_use_initial_zero_before_later_motion():
    case = replace(_stop_case(), fault=FaultSpec("user_stop", 0),
                   criteria=EvaluationCriteria(max_stop_delay_s=.2, max_stop_distance_m=.01))
    events = [_event("explicit_start", 0), _event("fault_applied", 0, fault_kind="user_stop"),
              _event("stop_decision", 0, code="USER_STOP"), _event("terminal", 2, state="STOPPED")]
    result = score_leg(case, _analytic_trace(terminal="STOPPED"), events, terminal_state="STOPPED")
    assert result["verdict"] == "FAIL"
    assert result["metrics"]["stop_delay_s"] > 1.9
    assert result["metrics"]["stop_distance_m"] > .14


def test_obstacle_injection_log_must_match_the_frozen_fault_payload():
    scheduled = Obstacle("scheduled", .55, 0, .05, .2)
    case = replace(_stop_case(), fault=FaultSpec("obstacle", 1.5, obstacle=scheduled))
    events = _events(stop=True)
    next(e for e in events if e["kind"] == "fault_applied").update(
        fault_kind="obstacle", obstacle=replace(scheduled, cx=10).to_dict())
    next(e for e in events if e["kind"] == "stop_decision")["code"] = "MAP_CHANGED"
    assert score_leg(case, _analytic_trace(terminal="STOPPED"), events, terminal_state="STOPPED")["verdict"] == "FAIL"


def test_recovery_cannot_reenable_a_drive_command_during_hold():
    case = replace(_stop_case(), fault=FaultSpec("data_loss", 1.5, recover_after_s=.7),
                   criteria=EvaluationCriteria(hold_after_stop_s=.5))
    events = _events(stop=True)
    next(e for e in events if e["kind"] == "fault_applied")["fault_kind"] = "data_loss"
    next(e for e in events if e["kind"] == "stop_decision")["code"] = "STALE_FEEDBACK"
    events.append(_event("feedback_recovered", 2.2, sim_t=2))
    rows = _analytic_trace(terminal="STOPPED")
    rows[460]["command_speed_mps"] = .01
    result = score_leg(case, rows, events, terminal_state="STOPPED")
    assert result["verdict"] == "FAIL"
    assert "motion_or_drive_command_after_terminal" in result["reasons"]


def test_actual_distance_and_reversals_ignore_declared_metadata():
    case = _case()
    case.scenario.maneuver = replace(case.scenario.maneuver, max_path_length_m=.7)
    rows = _analytic_trace((1, -1, 1, -1, 1))
    for row in rows:
        row.update(reported_length_m=0, reported_cusps=0)
    result = score_leg(case, rows, [], terminal_state="COMPLETED")
    assert result["verdict"] == "FAIL"
    assert result["metrics"]["total_actual_distance_m"] == pytest.approx(.75)
    assert result["metrics"]["actual_reversals"] == 4
    assert "actual_distance_exceeded_maneuver_limit" in result["reasons"]
    assert "actual_reversals_exceeded_maneuver_limit" in result["reasons"]


def test_zero_speed_metadata_cannot_hide_actual_movement():
    rows = _analytic_trace()
    for row in rows:
        row["speed_mps"] = 0.0
    result = score_leg(_case(), rows, _events(), terminal_state="COMPLETED")
    assert result["verdict"] == "FAIL"


def test_reported_collision_in_trace_cannot_bypass_kinematic_sanity_and_pass():
    rows = _analytic_trace()
    for row in rows:
        row.update(speed_mps=0.0, reported_collision=True)
    assert score_leg(_case(), rows, _events(), terminal_state="COMPLETED")["verdict"] == "FAIL"


def test_bicycle_truth_cannot_translate_sideways_without_heading_change():
    case, rows = _case(), _analytic_trace()
    case.scenario.goal = ParkingGoal(Pose(0, .15, 0), .005, math.radians(1))
    for row in rows:
        row["x"], row["y"] = row["y"], row["x"]
    assert score_leg(case, rows, _events(), terminal_state="COMPLETED")["verdict"] == "FAIL"


def test_fault_terminal_state_is_not_completed_even_near_goal():
    assert score_leg(_case(), _analytic_trace(terminal="FAULT"),
                     [_event("explicit_start", 0), _event("terminal", 2, state="FAULT")],
                     terminal_state="FAULT")["verdict"] == "FAIL"


@pytest.mark.parametrize("seed", [0, 7, 113])
def test_fixed_cases_roundtrip_and_sampled_witnesses_are_consistent(seed):
    cases = build_cases(seed) + build_robustness_cases(seed)
    assert len({case.case_id for case in cases}) == len(cases)
    witnesses = build_geometric_witnesses(seed)
    assert {case.family for case in build_cases(seed)} >= {"corner", "doorway", "columns", "slot", "correction"}
    for case in cases:
        assert ManeuverCase.from_dict(case.to_dict()).to_dict() == case.to_dict()
        assert case.scenario.seed == seed
        if case.case_id in witnesses:
            witness = witnesses[case.case_id]
            poses = witness.samples()
            limits, start = case.scenario.maneuver, case.scenario.start
            b = case.scenario.bounds
            local = Bounds(max(b.xmin, start.x-limits.area_half_extent_m), max(b.ymin, start.y-limits.area_half_extent_m),
                           min(b.xmax, start.x+limits.area_half_extent_m), min(b.ymax, start.y+limits.area_half_extent_m))
            assert sum(abs(d) for d, _ in witness.arcs) <= limits.max_path_length_m
            assert all(pose_ok(case.vehicle, pose, case.scenario.obstacles, local, margin=.003) for pose in poses), case.case_id
            assert poses[-1].distance_to(case.scenario.goal.pose) < 1e-10
            assert abs(poses[-1].heading_error_to(case.scenario.goal.pose)) < 1e-10


def test_case_builders_are_fresh_and_seed_reproducible():
    first, second = build_robustness_cases(17), build_robustness_cases(17)
    assert [c.to_dict() for c in first] == [c.to_dict() for c in second]
    snapshot = deepcopy(second[0].to_dict())
    first[0].scenario.obstacles.append(Obstacle("mutation", 10, 10, 1, 1))
    assert second[0].to_dict() == snapshot
    assert all(c.fault is not None for c in second if c.expected == "stop")
    assert len([c for c in second if c.followup_goal is not None]) == 4


def test_robustness_brake_criteria_are_declared_from_dynamics():
    for case in build_robustness_cases():
        if case.fault is None:
            continue
        v, a = case.vehicle.max_speed, case.vehicle.max_decel
        reaction = case.feedback.stale_after_s + .02 if case.fault.kind == "data_loss" else 0
        assert case.criteria.max_stop_delay_s == pytest.approx(reaction + v/a + .01)
        assert case.criteria.max_stop_distance_m == pytest.approx(v * (reaction + .01) + v*v/(2*a))


@pytest.mark.parametrize("case_id", ["next_after_feedback_recovery", "next_after_obstacle_stop"])
def test_followup_uses_actual_stop_requires_new_start_and_exactly_replays(tmp_path, case_id):
    from autopark.evaluation.maneuver_bench import read_json, replay_case, run_case

    case = next(c for c in build_robustness_cases(113) if c.case_id == case_id)
    before = deepcopy(case.to_dict())
    destination = tmp_path / "original"
    result = run_case(case, destination)
    assert result["verdict"] == "PASS", result
    assert result["actual_outcome"] == "stopped"
    assert result["followup_outcome"] == "completed"
    assert case.to_dict() == before
    first = read_json(destination / "legs/leg_01/trace.json")
    second = read_json(destination / "legs/leg_02/trace.json")
    action = read_json(destination / "followup_action.json")
    assert action["kind"] == "prepare_next_maneuver" and action["explicit"]
    assert action["new_start"]["x"] == pytest.approx(first[-1]["x"])
    assert second[0]["x"] == pytest.approx(first[-1]["x"])
    assert abs(second[0]["x"] - case.scenario.goal.pose.x) > .1
    for leg in (1, 2):
        events = read_json(destination / f"legs/leg_{leg:02d}/events.json")
        assert len([e for e in events if e["kind"] == "explicit_start"]) == 1
    if case.fault.kind == "obstacle":
        after = read_json(destination / "legs/leg_02/scenario.json")
        assert any(o["id"] == case.fault.obstacle.id for o in after["obstacles"])
    else:
        events = read_json(destination / "legs/leg_01/events.json")
        recovery = next(e for e in events if e["kind"] == "feedback_recovered")
        assert first[-1]["clock_s"] - recovery["clock_s"] >= case.criteria.hold_after_stop_s - 1e-9
        assert all(abs(r["speed_mps"]) <= case.criteria.stop_speed_mps and r["command_speed_mps"] == 0
                   for r in first if r["clock_s"] >= recovery["clock_s"])
    replay = replay_case(destination, tmp_path / "replayed")
    assert replay["match"], replay
    assert all(c["metrics_match"] and c["events_match"] and c["max_abs_numeric_difference"] == 0
               for c in replay["comparisons"])


def test_untriggered_fault_is_a_retained_reproducible_failure(tmp_path):
    from autopark.evaluation.maneuver_bench import read_json, replay_case, run_case

    case = next(c for c in build_robustness_cases(7) if c.case_id == "fault_user_stop")
    case = replace(case, fault=FaultSpec("user_stop", 10))
    destination = tmp_path / "original"
    result = run_case(case, destination)
    assert result["verdict"] == "FAIL"
    assert any("required_fault_not_applied" in reason for reason in result["reasons"])
    events = read_json(destination / "legs/leg_01/events.json")
    assert not any(e["kind"] == "fault_applied" for e in events)
    assert read_json(destination / "case.json")["fault"]["at_s"] == 10
    replay = replay_case(destination, tmp_path / "replayed")
    assert replay["match"], replay
    assert replay["original_verdict"] == replay["replayed_verdict"] == "FAIL"
