"""Independent truth-trace scoring for simulation-only local maneuvers.

The geometry oracle uses complex rectangle transforms and generic SAT rather
than production footprint/check_motion. Geometry is sampled at PHYSICS_DT;
this is evidence at those samples, not a continuous collision-freedom proof.
No planner/controller completion flag substitutes for measured end pose.
"""
from __future__ import annotations

import math
from collections import Counter

from autopark.domain.types import Bounds, Obstacle, Pose
from autopark.evaluation.collision_oracle import overlaps, rectangle, vehicle_rectangle
from autopark.evaluation.maneuver_suite_spec import ManeuverCase


PHYSICS_DT = 0.005
REFUSAL_STATUSES = frozenset(("START_INVALID", "GOAL_INVALID", "MANEUVER_LIMIT"))
NUMERIC_FIELDS = ("clock_s", "sim_time_s", "x", "y", "yaw_rad", "speed_mps", "steer_rad",
                  "command_speed_mps", "command_steer_rad")
POSE_EPS_M = 1e-5
YAW_EPS_RAD = 1e-4


def _angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def _segment_distance(point, a, b):
    edge = b - a
    fraction = max(0.0, min(1.0, ((point - a) * edge.conjugate()).real / abs(edge) ** 2))
    return abs(point - (a + fraction * edge))


def polygon_distance(a, b):
    """Euclidean polygon separation; touching/overlapping rectangles return 0."""
    if overlaps(a, b):
        return 0.0
    return min(_segment_distance(p, x, y) for one, other in ((a, b), (b, a))
               for p in one for x, y in zip(other, other[1:] + other[:1]))


def _obstacle_rectangle(obstacle):
    return rectangle(obstacle.cx, obstacle.cy, obstacle.yaw, -obstacle.width / 2,
                     obstacle.width / 2, -obstacle.height / 2, obstacle.height / 2)


def _boundary_clearance(body, bounds):
    return min(min(p.real - bounds.xmin, bounds.xmax - p.real,
                   p.imag - bounds.ymin, bounds.ymax - p.imag) for p in body)


def _local_bounds(scenario):
    if scenario.maneuver is None:
        return scenario.bounds
    b, p, r = scenario.bounds, scenario.start, scenario.maneuver.area_half_extent_m
    return Bounds(max(b.xmin, p.x - r), max(b.ymin, p.y - r),
                  min(b.xmax, p.x + r), min(b.ymax, p.y + r))


def refusal_evidence(case, scenario=None):
    """Independently check invalid requests; failure to find a path is not proof."""
    scenario = scenario or case.scenario
    reasons = []
    if scenario.maneuver is None or scenario.slot is not None:
        reasons.append("unsupported_request")
    if scenario.maneuver and math.hypot(scenario.goal.pose.x - scenario.start.x,
                                       scenario.goal.pose.y - scenario.start.y) > scenario.maneuver.max_goal_distance_m:
        reasons.append("goal_distance_exceeds_limit")
    bounds = _local_bounds(scenario)
    obstacles = [_obstacle_rectangle(o) for o in scenario.obstacles]
    for name, pose in (("start", scenario.start), ("goal", scenario.goal.pose)):
        body = vehicle_rectangle(case.vehicle, pose)
        if _boundary_clearance(body, bounds) < -1e-12:
            reasons.append(name + "_outside_allowed_body_bounds")
        if any(overlaps(body, obstacle) for obstacle in obstacles):
            reasons.append(name + "_body_intersects_obstacle")
    return reasons


def _trace_error(trace, case, scenario):
    if not isinstance(trace, list) or len(trace) < 2:
        return "missing_or_short_physics_trace"
    for i, row in enumerate(trace):
        if not isinstance(row, dict) or any(isinstance(row.get(k), bool)
                or not isinstance(row.get(k), (int, float)) or not math.isfinite(row[k]) for k in NUMERIC_FIELDS):
            return f"invalid_numeric_trace_row:{i}"
        if row.get("phase") not in ("motion", "hold") or not isinstance(row.get("state"), str):
            return f"invalid_trace_metadata:{i}"
        if "reported_collision" in row and type(row["reported_collision"]) is not bool:
            return f"invalid_collision_flag:{i}"
        if row["phase"] == "hold" and row["state"] not in ("STOPPED", "COMPLETED", "FAULT"):
            return f"hold_without_terminal_state:{i}"
        if row["clock_s"] < 0 or row["sim_time_s"] < 0:
            return f"negative_trace_time:{i}"
        if abs(row["speed_mps"]) > case.vehicle.max_speed + 1e-9:
            return f"invalid_truth_speed:{i}"
        if abs(row["steer_rad"]) > case.vehicle.max_steer + 1e-9:
            return f"invalid_truth_steer:{i}"
        if i:
            prev = trace[i - 1]
            delta = row["clock_s"] - prev["clock_s"]
            sim_delta = row["sim_time_s"] - prev["sim_time_s"]
            if abs(delta - PHYSICS_DT) > 1e-8 or sim_delta < -1e-10:
                return f"missing_or_nonmonotonic_physics_samples:{i}"
            if row["phase"] == "motion" and abs(sim_delta - PHYSICS_DT) > 1e-8:
                return f"invalid_simulation_step:{i}"
            if row["phase"] == "hold" and abs(sim_delta) > 1e-8:
                return f"hold_did_not_freeze_simulation_clock:{i}"
            distance = math.hypot(row["x"] - prev["x"], row["y"] - prev["y"])
            if distance > case.vehicle.max_speed * delta + 1e-8:
                return f"impossible_position_jump:{i}"
            if not row.get("reported_collision"):
                # A speed column cannot conceal real motion. Bounds allow the
                # tiny chord/arc difference without using production integration.
                travel = abs((row["speed_mps"] + prev["speed_mps"]) / 2) * sim_delta
                if abs(distance - travel) > 1e-8:
                    return f"truth_speed_position_disagree:{i}"
            mid_yaw = prev["yaw_rad"] + _angle(row["yaw_rad"] - prev["yaw_rad"]) / 2
            lateral = -(row["x"] - prev["x"]) * math.sin(mid_yaw) + (row["y"] - prev["y"]) * math.cos(mid_yaw)
            if abs(lateral) > 1e-8:
                return f"impossible_lateral_body_motion:{i}"
            max_yaw = distance * math.tan(case.vehicle.max_steer) / case.vehicle.wheelbase
            if abs(_angle(row["yaw_rad"] - prev["yaw_rad"])) > max_yaw + 1e-8:
                return f"impossible_heading_jump:{i}"
    first = trace[0]
    if first["clock_s"] != 0 or first["sim_time_s"] != 0 or math.hypot(
            first["x"] - scenario.start.x, first["y"] - scenario.start.y) > 1e-8 or abs(
                _angle(first["yaw_rad"] - scenario.start.yaw)) > 1e-8:
        return "trace_does_not_start_at_frozen_initial_state"
    if abs(first["speed_mps"]) > 1e-12:
        return "trace_does_not_start_at_standstill"
    if not any(row["phase"] == "motion" and row["sim_time_s"] > 0 for row in trace):
        return "trace_contains_no_simulation_step"
    return None


def score_leg(case: ManeuverCase, trace: list[dict], events: list[dict], *, plan_status="OK",
              terminal_state="", simulation_timeout=False, error=None, scenario=None,
              expected=None, reported_collision=False) -> dict:
    """Score one leg using SI truth samples and separately recorded decisions.

    A refusal has no motion trace and needs both a precondition status and an
    independently invalid request. An expected stop needs its scheduled fault,
    measured standstill, and a full hold after any recovery. Stops never count
    as completing a goal. Invalid/missing traces fail closed.
    """
    scenario, expected = scenario or case.scenario, expected or case.expected
    result = {"expected": expected, "actual_outcome": "error", "verdict": "FAIL", "reasons": [],
              "plan_status": plan_status, "terminal_state": terminal_state,
              "evidence": {"domain": "simulation_only", "geometry": "independent_complex_rectangles_SAT",
                           "sampling_dt_s": PHYSICS_DT, "continuous_collision_proof": False,
                           "hold_position_epsilon_m": POSE_EPS_M, "hold_yaw_epsilon_rad": YAW_EPS_RAD},
              "metrics": {}}
    reasons, metrics = result["reasons"], result["metrics"]
    if error:
        reasons.append("execution_error:" + str(error))
    if plan_status != "OK":
        if not isinstance(events, list) or any(not isinstance(e, dict) or not isinstance(e.get("kind"), str) for e in events):
            reasons.append("malformed_events_without_accepted_plan")
            return result
        if events:
            reasons.append("execution_events_without_accepted_plan")
            return result
        if trace:
            reasons.append("unexpected_motion_trace_without_accepted_plan")
            return result
        if plan_status in REFUSAL_STATUSES:
            evidence = refusal_evidence(case, scenario)
            metrics["refusal_evidence"] = evidence
            result["actual_outcome"] = "refused"
            if not evidence:
                reasons.append("precondition_refusal_not_independently_supported")
            supported = {"START_INVALID": "start_body_intersects_obstacle" in evidence,
                         "GOAL_INVALID": "goal_body_intersects_obstacle" in evidence,
                         "MANEUVER_LIMIT": any(e not in ("start_body_intersects_obstacle", "goal_body_intersects_obstacle")
                                               for e in evidence)}
            if not supported[plan_status]:
                reasons.append("refusal_status_disagrees_with_independent_precondition")
        elif plan_status == "TIMEOUT":
            result["actual_outcome"] = "timeout"
            result["timeout_scope"] = "planner_budget"
            reasons.append("planner_budget_exhausted_not_infeasibility_proof")
        elif plan_status == "NO_PATH":
            result["actual_outcome"] = "no_path"
            reasons.append("search_returned_no_path_not_infeasibility_proof")
        else:
            reasons.append("planning_failed:" + str(plan_status))
        if expected != "refuse" or result["actual_outcome"] != "refused":
            reasons.append("expected_" + expected + "_but_" + result["actual_outcome"])
        result["verdict"] = "PASS" if not reasons else "FAIL"
        return result
    trace_error = _trace_error(trace, case, scenario)
    if trace_error:
        reasons.append(trace_error)
        return result
    if terminal_state and trace[-1]["state"] != terminal_state:
        reasons.append("terminal_state_disagrees_with_trace")
        return result
    reported_collision = reported_collision or any(row.get("reported_collision", False) for row in trace)
    if not isinstance(events, list):
        reasons.append("malformed_events")
        return result
    for event in events:
        if (not isinstance(event, dict) or not isinstance(event.get("kind"), str)
                or any(isinstance(event.get(k), bool) or not isinstance(event.get(k), (int, float))
                       or not math.isfinite(event[k]) or not 0 <= event[k] <= trace[-1][k] + 1e-8
                       for k in ("clock_s", "sim_time_s"))):
            reasons.append("malformed_event_time_or_kind")
            return result
    criteria = case.criteria
    final = trace[-1]
    pose_error = math.hypot(final["x"] - scenario.goal.pose.x, final["y"] - scenario.goal.pose.y)
    yaw_error = abs(_angle(final["yaw_rad"] - scenario.goal.pose.yaw))
    increments = [0.0] + [math.hypot(b["x"] - a["x"], b["y"] - a["y"])
                           for a, b in zip(trace, trace[1:])]
    directions = []
    for previous, current in zip(trace, trace[1:]):
        mid_yaw = previous["yaw_rad"] + _angle(current["yaw_rad"] - previous["yaw_rad"]) / 2
        longitudinal = ((current["x"] - previous["x"]) * math.cos(mid_yaw)
                        + (current["y"] - previous["y"]) * math.sin(mid_yaw))
        if abs(longitudinal) > 1e-9:
            directions.append(1 if longitudinal > 0 else -1)
    reversals = sum(a != b for a, b in zip(directions, directions[1:]))
    dynamic = [e for e in events if e["kind"] == "fault_applied" and e.get("fault_kind") == "obstacle"]
    try:
        obstacle_shapes = [(0.0, _obstacle_rectangle(o)) for o in scenario.obstacles]
        obstacle_shapes += [(e["clock_s"], _obstacle_rectangle(Obstacle.from_dict(e["obstacle"]))) for e in dynamic]
    except (KeyError, TypeError, ValueError) as exc:
        reasons.append("malformed_obstacle_event:" + str(exc))
        return result
    collision_indices = []
    min_obstacle, min_boundary, min_local = math.inf, math.inf, math.inf
    local = _local_bounds(scenario)
    for index, row in enumerate(trace):
        body = vehicle_rectangle(case.vehicle, Pose(row["x"], row["y"], row["yaw_rad"]))
        boundary = _boundary_clearance(body, scenario.bounds)
        local_clearance = _boundary_clearance(body, local)
        min_boundary, min_local = min(min_boundary, boundary), min(min_local, local_clearance)
        overlap = False
        for at_s, obstacle in obstacle_shapes:
            if row["clock_s"] + 1e-10 >= at_s:
                separation = polygon_distance(body, obstacle)
                min_obstacle = min(min_obstacle, separation)
                overlap |= separation == 0.0
        if overlap or boundary < -1e-10:
            collision_indices.append(index)
    hold = [row for row in trace if row["phase"] == "hold"]
    terminal_samples = [row for row in trace if row["state"] in ("STOPPED", "COMPLETED", "FAULT")]
    anchor = terminal_samples[0] if terminal_samples else None
    hold_duration = final["clock_s"] - anchor["clock_s"] if anchor else 0.0
    held_samples = [row for row in trace if anchor and row["clock_s"] >= anchor["clock_s"]]
    no_motion = bool(anchor and all(abs(row["speed_mps"]) <= criteria.stop_speed_mps
                       and math.hypot(row["x"] - anchor["x"], row["y"] - anchor["y"]) <= POSE_EPS_M
                       and abs(_angle(row["yaw_rad"] - anchor["yaw_rad"])) <= YAW_EPS_RAD
                       and abs(row["command_speed_mps"]) <= criteria.stop_speed_mps for row in held_samples))
    faults = [e for e in events if e["kind"] == "fault_applied"]
    recoveries = [e for e in events if e["kind"] == "feedback_recovered"]
    fault = faults[0] if len(faults) == 1 else None
    stop_delay = stop_distance = stop_time = None
    if fault:
        after_fault = [(i, row) for i, row in enumerate(trace) if row["clock_s"] + 1e-10 >= fault["clock_s"]]
        stationary = [(i, row) for i, row in after_fault if abs(row["speed_mps"]) <= criteria.stop_speed_mps]
        stopped = None
        for i, row in stationary:
            suffix = trace[i:]
            if (all(abs(r["speed_mps"]) <= criteria.stop_speed_mps for r in suffix)
                    and max(math.hypot(r["x"] - row["x"], r["y"] - row["y"]) for r in suffix) <= POSE_EPS_M):
                stopped = i, row
                break
        if stationary:
            first_index, first_stationary = stationary[0]
            if any(abs(r["speed_mps"]) > criteria.stop_speed_mps or math.hypot(
                    r["x"] - first_stationary["x"], r["y"] - first_stationary["y"]) > POSE_EPS_M
                   for r in trace[first_index:]):
                reasons.append("motion_resumed_after_initial_fault_stop")
        if stopped:
            stop_index, stopped_row = stopped
            stop_time = stopped_row["clock_s"]
            stop_delay = stop_time - fault["clock_s"]
            stop_distance = sum(increments[i] for i, row in after_fault
                                if fault["clock_s"] + 1e-10 < row["clock_s"] <= stop_time + 1e-10)
    clearance = min(min_obstacle, min_boundary)
    metrics.update(final_position_error_m=pose_error, final_yaw_error_rad=yaw_error,
                   final_yaw_error_deg=math.degrees(yaw_error), final_speed_mps=final["speed_mps"],
                   min_obstacle_clearance_m=None if math.isinf(min_obstacle) else min_obstacle,
                   min_boundary_clearance_m=min_boundary, min_local_boundary_clearance_m=min_local,
                   min_body_clearance_m=clearance, total_actual_distance_m=sum(increments),
                   actual_reversals=reversals, simulation_elapsed_s=max(row["sim_time_s"] for row in trace),
                   runner_elapsed_s=final["clock_s"], physics_samples=sum(r["phase"] == "motion" for r in trace),
                   sampled_collision_count=len(collision_indices),
                   first_sampled_collision_clock_s=trace[collision_indices[0]]["clock_s"] if collision_indices else None,
                   fault_applied_clock_s=fault["clock_s"] if fault else None,
                   stop_clock_s=stop_time, stop_delay_s=stop_delay, stop_distance_m=stop_distance,
                   hold_duration_s=hold_duration, no_motion_or_drive_after_terminal=no_motion,
                   recovery_clock_s=recoveries[0]["clock_s"] if len(recoveries) == 1 else None)
    if collision_indices or reported_collision:
        result["actual_outcome"] = "collision"
        reasons.append("sampled_body_collision_or_boundary_exit" if collision_indices else "production_collision_without_sampled_oracle_overlap")
    elif simulation_timeout:
        result["actual_outcome"] = "timeout"
        result["timeout_scope"] = "simulation_budget"
        reasons.append("simulation_budget_exhausted_not_infeasibility_proof")
    elif error:
        result["actual_outcome"] = "error"
    elif terminal_state == "FAULT":
        result["actual_outcome"] = "error"
        reasons.append("session_ended_in_fault")
    elif fault and abs(final["speed_mps"]) <= criteria.stop_speed_mps and terminal_state in ("STOPPED", "FAULT"):
        result["actual_outcome"] = "stopped"
    elif terminal_state == "STOPPED":
        result["actual_outcome"] = "stopped"
    elif pose_error <= scenario.goal.tolerance_xy and yaw_error <= scenario.goal.tolerance_yaw and abs(
            final["speed_mps"]) <= criteria.stop_speed_mps and not fault:
        result["actual_outcome"] = "completed"
    else:
        result["actual_outcome"] = "error"
        reasons.append("terminal_truth_does_not_satisfy_goal_or_requested_stop")
    if terminal_state == "COMPLETED" and result["actual_outcome"] != "completed":
        reasons.append("controller_completion_disagrees_with_truth_or_fault")
    if clearance + 1e-10 < criteria.min_clearance_m:
        reasons.append("body_clearance_below_frozen_criterion")
    if min_local < -1e-10:
        reasons.append("body_exited_local_maneuver_area")
    if scenario.maneuver:
        if sum(increments) > scenario.maneuver.max_path_length_m + 1e-8:
            reasons.append("actual_distance_exceeded_maneuver_limit")
        if reversals > scenario.maneuver.max_cusps:
            reasons.append("actual_reversals_exceeded_maneuver_limit")
    if expected in ("complete", "stop") and result["actual_outcome"] in ("completed", "stopped"):
        if hold_duration + 1e-8 < criteria.hold_after_stop_s or not hold:
            reasons.append("insufficient_stationary_hold_evidence")
        if not no_motion:
            reasons.append("motion_or_drive_command_after_terminal")
    if expected == "stop":
        if not fault or case.fault is None or fault.get("fault_kind") != case.fault.kind:
            reasons.append("required_fault_not_applied")
        elif abs(fault["clock_s"] - case.fault.at_s) > PHYSICS_DT + 1e-8:
            reasons.append("fault_not_applied_at_scheduled_time")
        if fault and case.fault:
            if case.fault.kind == "obstacle" and fault.get("obstacle") != case.fault.obstacle.to_dict():
                reasons.append("applied_obstacle_does_not_match_frozen_fault")
            required_code = {"user_stop": "USER_STOP", "data_loss": "STALE_FEEDBACK", "obstacle": "MAP_CHANGED"}[case.fault.kind]
            decisions = [event for event in events if event["kind"] == "stop_decision"
                         and event.get("code") == required_code and event["clock_s"] + 1e-8 >= fault["clock_s"]
                         and anchor is not None and event["clock_s"] <= anchor["clock_s"] + PHYSICS_DT + 1e-8]
            if not decisions:
                reasons.append("missing_matching_stop_decision:" + required_code)
            if terminal_state != "STOPPED":
                reasons.append("requested_stop_did_not_end_in_stopped_state")
        if stop_delay is None:
            reasons.append("standstill_after_fault_not_measured")
        elif criteria.max_stop_delay_s is not None and stop_delay > criteria.max_stop_delay_s + 1e-8:
            reasons.append("stop_delay_exceeds_frozen_criterion")
        if stop_distance is not None and criteria.max_stop_distance_m is not None and stop_distance > criteria.max_stop_distance_m + 1e-8:
            reasons.append("stop_distance_exceeds_frozen_criterion")
        if case.fault and case.fault.recover_after_s is not None:
            if len(recoveries) != 1:
                reasons.append("required_recovery_not_observed")
            elif fault:
                recovery = recoveries[0]
                if abs(recovery["clock_s"] - fault["clock_s"] - case.fault.recover_after_s) > PHYSICS_DT + 1e-8:
                    reasons.append("recovery_not_applied_at_scheduled_time")
                if final["clock_s"] - recovery["clock_s"] + 1e-8 < criteria.hold_after_stop_s:
                    reasons.append("insufficient_hold_after_recovery")
    target = {"complete": "completed", "refuse": "refused", "stop": "stopped"}[expected]
    if result["actual_outcome"] != target:
        reasons.append("expected_" + expected + "_but_" + result["actual_outcome"])
    result["verdict"] = "PASS" if not reasons else "FAIL"
    return result


def summarize(results):
    """Explicit denominators prevent safe stops/refusals inflating completion."""
    def group(rows):
        rows = list(rows)
        passed = sum(r["verdict"] == "PASS" for r in rows)
        return {"total": len(rows), "passed": passed, "failed": len(rows) - passed,
                "pass_rate": passed / len(rows) if rows else None,
                "outcomes": dict(sorted(Counter(r["actual_outcome"] for r in rows).items()))}
    return {"overall": group(results),
            "by_expected": {key: group(r for r in results if r["expected"] == key)
                            for key in ("complete", "refuse", "stop")},
            "by_family": {key: group(r for r in results if r["family"] == key)
                          for key in sorted({r["family"] for r in results})},
            "by_seed": {str(key): group(r for r in results if r["seed"] == key)
                        for key in sorted({r["seed"] for r in results})}}
