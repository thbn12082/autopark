"""Run, list, and replay the simulation-only local-maneuver campaign.

python -m autopark.evaluation.maneuver_bench run --out runs/maneuver_suite_example
python -m autopark.evaluation.maneuver_bench replay runs/maneuver_suite_example/cases/ID_seed_0

Replay uses frozen trajectories and trigger steps, not a new wall-clock-budgeted
search. A pre-motion failure with no trajectory is a decision replay; --replan
explicitly reruns the frozen input and makes no timeout reproducibility promise.
"""
from __future__ import annotations

import argparse
import copy
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

from autopark.application.session import Session, SessionState
from autopark.control.tracker import TrackerParams
from autopark.domain.types import Pose, Scenario
from autopark.evaluation.maneuver_score import NUMERIC_FIELDS, score_leg, summarize
from autopark.evaluation.maneuver_suite_spec import ManeuverCase
from autopark.planning.hybrid_astar import PlannerParams, PlanResult
from autopark.planning.trajectory import Trajectory, TrajectoryPoint


SCHEMA_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRACE_FIELDS = [*NUMERIC_FIELDS, "state", "phase", "world_step", "reported_collision"]


def _finite_json(value):
    """Unknown/nonfinite diagnostic quantities are JSON null, never NaN/Infinity."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _finite_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite_json(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_finite_json(value), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path):
    def reject(value):
        raise ValueError("Nonfinite JSON constant: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def _csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(_finite_json(rows))


def _hash_json(value):
    return hashlib.sha256(json.dumps(_finite_json(value), sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def source_fingerprint():
    """One cheap source hash per campaign/replay; no source zip or PowerShell."""
    digest = hashlib.sha256()
    files = sorted((PROJECT_ROOT / "autopark").rglob("*.py"))
    for path in files:
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {"algorithm": "sha256_sorted_python_sources", "sha256": digest.hexdigest(), "file_count": len(files)}


def environment_manifest():
    """Collect environment and code provenance once, including uncommitted code."""
    git = {}
    for key, args in (("commit", ["rev-parse", "HEAD"]), ("status", ["status", "--porcelain"])):
        try:
            proc = subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=5,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            git[key] = proc.stdout.strip() if proc.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            git[key] = None
    packages = {}
    for name in ("numpy", "shapely", "pytest", "PySide6"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    from autopark.power_throttling import ecoqos_state
    return {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
            "machine": platform.machine(), "processor": platform.processor(), "packages": packages,
            "ecoqos": ecoqos_state(), "git": git, "source": source_fingerprint()}


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")


def _params(case):
    return {"planner": asdict(PlannerParams(time_limit=case.plan_time_limit_s)),
            "tracker": asdict(TrackerParams()), "physics_dt_s": Session.PHYSICS_DT,
            "control_every": Session.CONTROL_EVERY, "session_max_run_time_s": Session.MAX_RUN_TIME,
            "trace_units": {"x": "m", "y": "m", "yaw_rad": "rad", "speed_mps": "m/s",
                            "steer_rad": "rad", "clock_s": "s", "sim_time_s": "s",
                            "command_speed_mps": "m/s", "command_steer_rad": "rad"}}


def _trajectory(data):
    return Trajectory([TrajectoryPoint(**dict(point, pose=Pose(**point["pose"]))) for point in data["points"]],
                      Pose(**data["goal"]), [tuple(pair) for pair in data["segments"]],
                      data.get("source_id", "sim_planner"), data.get("t", 0.0), data.get("valid", True))


def _trace_row(session, clock_s, phase):
    state = session.world.state
    return {"clock_s": clock_s, "sim_time_s": state.t, "x": state.pose.x, "y": state.pose.y,
            "yaw_rad": state.pose.yaw, "speed_mps": state.speed, "steer_rad": state.steer,
            "command_speed_mps": session.targets.speed, "command_steer_rad": session.targets.steer,
            "state": session.state.value, "phase": phase, "world_step": session.world.step_count,
            "reported_collision": session.world.collided}


def _event(session, clock_s, kind, **data):
    return {"kind": kind, "clock_s": clock_s,
            "sim_time_s": session.world.time if session.world else 0.0, **data}


def _run_leg(session, case, out_dir, leg_index, expected, *, frozen=None):
    out_dir.mkdir(parents=True, exist_ok=False)
    scenario = copy.deepcopy(session.scenario)
    write_json(out_dir / "scenario.json", scenario.to_dict())
    trace, events = [], []
    simulation_timeout, error, reported_collision = False, None, False
    plan_data = {"status": "ERROR", "message": "Execution did not reach planning", "wall_elapsed_s": 0.0}
    trajectory_data = None
    frozen_execution = "live_plan"
    motion_wall = time.perf_counter()
    try:
        if frozen is None:
            began = time.perf_counter()
            plan = session.plan_sync()
            elapsed = time.perf_counter() - began
            plan_data = {k: v for k, v in asdict(plan).items() if k != "trajectory"}
            plan_data["wall_elapsed_s"] = elapsed
            trajectory_data = asdict(plan.trajectory) if plan.trajectory else None
        else:
            plan_data = copy.deepcopy(frozen["plan"])
            trajectory_data = copy.deepcopy(frozen.get("trajectory"))
            frozen_execution = "frozen_trajectory" if trajectory_data is not None else "frozen_decision_only"
            plan = PlanResult(plan_data["status"], plan_data.get("message", "Frozen decision"),
                              None if trajectory_data is None else _trajectory(trajectory_data))
            session._apply_plan(plan, session.plan_version)
            if trajectory_data is None:
                error = frozen.get("error")
        # Freeze the plan before safety handling can invalidate its Trajectory.
        write_json(out_dir / "plan.json", plan_data)
        write_json(out_dir / "trajectory.json", trajectory_data)
        motion_wall = time.perf_counter()
        if plan.ok:
            session.start_run()
            clock_s, ticks = 0.0, 0
            events.append(_event(session, clock_s, "explicit_start", leg=leg_index))
            trace.append(_trace_row(session, clock_s, "motion"))
            fault = case.fault if leg_index == 1 else None
            fault_applied, recovered = False, False
            fault_clock = None
            terminal_clock = None
            recorded_safety = 0
            fault_at = fault.at_s if fault else None
            recovery_at = None
            if frozen is not None:
                frozen_fault = next((e for e in frozen["events"] if e["kind"] == "fault_applied"), None)
                # A fault not triggered in the original run must not be invented.
                fault_at = frozen_fault["clock_s"] if frozen_fault else None
                frozen_recovery = next((e for e in frozen["events"] if e["kind"] == "feedback_recovered"), None)
                recovery_at = frozen_recovery["clock_s"] if frozen_recovery else None
            # The runner clock advances while Session deliberately remains stopped;
            # world.t is separate and stays frozen throughout the hold.
            max_ticks = math.ceil(case.sim_timeout_s / session.PHYSICS_DT)
            while True:
                if (fault and fault_at is not None and not fault_applied and clock_s + 1e-10 >= fault_at
                        and session.state == SessionState.RUNNING):
                    if fault.kind == "data_loss":
                        session.inject_data_loss()
                    elif fault.kind == "obstacle":
                        session.inject_obstacle(fault.obstacle)
                    else:
                        session.request_stop("Maneuver benchmark user stop")
                    fault_applied, fault_clock = True, clock_s
                    events.append(_event(session, clock_s, "fault_applied", fault_kind=fault.kind,
                                         scheduled_at_s=fault.at_s,
                                         obstacle=None if fault.obstacle is None else fault.obstacle.to_dict()))
                    if fault.kind == "user_stop":
                        events.append(_event(session, clock_s, "stop_decision", code="USER_STOP", action="STOP"))
                    if frozen is None and fault.recover_after_s is not None:
                        recovery_at = clock_s + fault.recover_after_s
                if recovery_at is not None and fault_applied and not recovered and clock_s + 1e-10 >= recovery_at:
                    if session.feedback is None:
                        raise RuntimeError("Data-loss recovery has no SIM feedback")
                    session.feedback.lost = False
                    recovered = True
                    events.append(_event(session, clock_s, "feedback_recovered", fault_kind="data_loss"))
                if session.simulating and ticks >= max_ticks:
                    simulation_timeout = True
                    events.append(_event(session, clock_s, "simulation_budget_exhausted", budget_s=case.sim_timeout_s))
                    break
                if not session.simulating:
                    if terminal_clock is None:
                        terminal_clock = clock_s
                        events.append(_event(session, clock_s, "terminal", state=session.state.value,
                                             stop_reason=session.stop_reason))
                    hold_until = terminal_clock + case.criteria.hold_after_stop_s
                    if recovery_at is not None:
                        hold_until = max(hold_until, recovery_at + case.criteria.hold_after_stop_s)
                    if clock_s + 1e-10 >= hold_until:
                        break
                was_active = session.simulating
                session.advance(session.PHYSICS_DT)
                ticks += 1
                clock_s = ticks * session.PHYSICS_DT
                trace.append(_trace_row(session, clock_s, "motion" if was_active else "hold"))
                reported_collision |= session.world.collided
                for safety in session.safety_events[recorded_safety:]:
                    events.append(_event(session, clock_s, "stop_decision" if safety.action == "STOP" else "safety_decision", code=safety.code,
                                         message=safety.message, action=safety.action,
                                         decision_sim_time_s=safety.stamp.t))
                recorded_safety = len(session.safety_events)
                if any(e.code == "RUN_TIMEOUT" for e in session.safety_events):
                    simulation_timeout = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        write_json(out_dir / "error.json", {"error": error, "traceback": traceback.format_exc()})
    execution_elapsed = time.perf_counter() - motion_wall
    result = score_leg(case, trace, events, plan_status=plan_data["status"], terminal_state=session.state.value,
                       simulation_timeout=simulation_timeout, error=error, scenario=scenario,
                       expected=expected, reported_collision=reported_collision)
    result.update(leg=leg_index, planning_wall_elapsed_s=plan_data["wall_elapsed_s"],
                  execution_wall_elapsed_s=execution_elapsed, replay_mode=frozen_execution)
    write_json(out_dir / "plan.json", plan_data)
    write_json(out_dir / "trajectory.json", trajectory_data)
    write_json(out_dir / "trace.json", trace)
    _csv(out_dir / "trace.csv", trace, TRACE_FIELDS)
    write_json(out_dir / "events.json", events)
    write_json(out_dir / "session_events.json", {"run_events": session.run_events,
                                                "safety_events": [asdict(e) for e in session.safety_events]})
    session.log.to_csv(out_dir / "session_log.csv")
    write_json(out_dir / "result.json", result)
    frozen_record = {"scenario": scenario.to_dict(), "plan": plan_data, "trajectory": trajectory_data,
                     "events": events, "expected": expected, "error": error,
                     "simulation_timeout": simulation_timeout}
    return result, frozen_record


def run_case(case: ManeuverCase, out_dir, *, frozen_legs=None, parameters=None, provenance=None):
    """Run one frozen input, always retain its artifacts, and return its result."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    write_json(out_dir / "case.json", case.to_dict())
    parameters = copy.deepcopy(parameters or _params(case))
    write_json(out_dir / "parameters.json", parameters)
    write_json(out_dir / "provenance.json", provenance or {})
    legs, records, case_errors = [], [], []
    session = None
    began = time.perf_counter()
    try:
        session = Session(copy.deepcopy(case.scenario), case.vehicle, PlannerParams(**parameters["planner"]),
                          TrackerParams(**parameters["tracker"]), case.feedback)
        session.PHYSICS_DT = parameters["physics_dt_s"]
        session.CONTROL_EVERY = parameters["control_every"]
        session.MAX_RUN_TIME = parameters["session_max_run_time_s"]
        if abs(session.PHYSICS_DT - 0.005) > 1e-12:
            raise ValueError("Maneuver scorer requires the frozen 0.005 s physics step")
        first, record = _run_leg(session, case, out_dir / "legs" / "leg_01", 1, case.expected,
                                 frozen=None if frozen_legs is None else frozen_legs[0])
        legs.append(first)
        records.append(record)
        if case.followup_goal is not None:
            if session.state not in (SessionState.STOPPED, SessionState.COMPLETED):
                case_errors.append("followup_not_started_because_first_leg_not_stopped_or_completed")
            elif frozen_legs is not None and len(frozen_legs) < 2:
                case_errors.append("followup_not_started_in_original_recording")
            else:
                # Explicit user action, never automatic recovery of the old path.
                session.prepare_next_maneuver()
                session.set_goal_pose(case.followup_goal)
                write_json(out_dir / "followup_action.json", {"kind": "prepare_next_maneuver",
                           "explicit": True, "new_start": session.scenario.start.to_dict(),
                           "new_goal": case.followup_goal.to_dict()})
                second, record = _run_leg(session, case, out_dir / "legs" / "leg_02", 2, "complete",
                                          frozen=None if frozen_legs is None else frozen_legs[1])
                legs.append(second)
                records.append(record)
    except Exception as exc:
        case_errors.append(f"case_execution_error:{type(exc).__name__}:{exc}")
        write_json(out_dir / "error.json", {"error": case_errors[-1], "traceback": traceback.format_exc()})
    finally:
        if session is not None:
            session.close()
    execution = {"schema_version": SCHEMA_VERSION, "legs": records}
    result = {"schema_version": SCHEMA_VERSION, "case_id": case.case_id, "family": case.family,
              "seed": case.scenario.seed, "description": case.description, "expected": case.expected,
              "actual_outcome": legs[0]["actual_outcome"] if legs else "error",
              "verdict": "PASS" if legs and all(leg["verdict"] == "PASS" for leg in legs) and not case_errors else "FAIL",
              "reasons": case_errors + [f"leg_{i + 1}:{reason}" for i, leg in enumerate(legs) for reason in leg["reasons"]],
              "followup_outcome": legs[1]["actual_outcome"] if len(legs) > 1 else None,
              "followup_required": case.followup_goal is not None,
              "planning_wall_elapsed_s": sum(leg["planning_wall_elapsed_s"] for leg in legs),
              "execution_wall_elapsed_s": sum(leg["execution_wall_elapsed_s"] for leg in legs),
              "total_wall_elapsed_s": time.perf_counter() - began,
              "metrics": legs[0]["metrics"] if legs else {}, "legs": legs,
              "case_fingerprint": _hash_json(case.to_dict()), "parameters_fingerprint": _hash_json(parameters),
              "execution_fingerprint": _hash_json(execution),
              "artifact_dir": str(out_dir.resolve()), "domain": "simulation_only"}
    write_json(out_dir / "execution.json", execution)
    write_json(out_dir / "result.json", result)
    return result


def build_suite(seeds=(0,), selected=None):
    from autopark.evaluation.maneuver_cases import build_cases
    from autopark.evaluation.maneuver_robustness import build_robustness_cases
    all_cases = []
    for seed in seeds:
        cases = [*build_cases(seed), *build_robustness_cases(seed)]
        ids = [case.case_id for case in cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Builders returned duplicate case IDs")
        all_cases.extend(cases)
    if selected:
        requested = set(selected)
        missing = requested - {case.case_id for case in all_cases}
        if missing:
            raise ValueError("Unknown case IDs: " + ", ".join(sorted(missing)))
        all_cases = [case for case in all_cases if case.case_id in requested]
    if not all_cases:
        raise ValueError("The campaign selection is empty")
    return all_cases


def run_campaign(cases, out_dir, *, arguments=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    environment = environment_manifest()
    manifest = {"schema_version": SCHEMA_VERSION, "created_utc": datetime.now(timezone.utc).isoformat(),
                "domain": "simulation_only", "hardware_acceptance": False, "environment": environment,
                "arguments": arguments or {}, "case_count": len(cases), "cases": [],
                "sampling": {"physics_dt_s": Session.PHYSICS_DT,
                             "hold_clock": "runner clock advances; stopped world clock remains fixed"},
                "interpretation": "NO_PATH and TIMEOUT do not prove infeasibility; safe stop is not completion."}
    identifiers = [(case.case_id, case.scenario.seed) for case in cases]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate case/seed pairs")
    for case in cases:
        manifest["cases"].append({"case_id": case.case_id, "seed": case.scenario.seed, "family": case.family,
                                  "expected": case.expected, "case_fingerprint": _hash_json(case.to_dict()),
                                  "parameters": _params(case)})
    write_json(out_dir / "manifest.json", manifest)
    results = []
    for index, case in enumerate(cases, 1):
        destination = out_dir / "cases" / f"{case.case_id}_seed_{case.scenario.seed}"
        print(f"[{index}/{len(cases)}] {case.case_id} seed={case.scenario.seed}", flush=True)
        result = run_case(case, destination, provenance={"source": environment["source"],
                          "campaign_manifest": "../../manifest.json"})
        results.append(result)
        print(f"  {result['verdict']} {result['actual_outcome']}" +
              (f"; followup={result['followup_outcome']}" if result["followup_required"] else ""), flush=True)
        # Save after every case, so interrupted campaigns retain all completed failures.
        summary = {"schema_version": SCHEMA_VERSION, "domain": "simulation_only", "requested_cases": len(cases),
                   "finished_cases": len(results), "campaign_complete": len(results) == len(cases),
                   **summarize(results), "results": results}
        write_json(out_dir / "summary.json", summary)
        fields = ["case_id", "family", "seed", "expected", "actual_outcome", "verdict", "followup_outcome",
                  "planning_wall_elapsed_s", "execution_wall_elapsed_s", "final_position_error_m",
                  "final_yaw_error_deg", "min_body_clearance_m", "min_boundary_clearance_m",
                  "total_actual_distance_m", "actual_reversals", "stop_delay_s", "stop_distance_m",
                  "no_motion_or_drive_after_terminal", "reasons", "artifact_dir"]
        _csv(out_dir / "summary.csv", [{**r, **r["metrics"], "reasons": ";".join(r["reasons"])} for r in results], fields)
        groups = [{"group_type": "overall", "group": "all", **summary["overall"], **summary["overall"]["outcomes"]}]
        for category in ("by_expected", "by_family", "by_seed"):
            groups.extend({"group_type": category, "group": key, **counts, **counts["outcomes"]}
                          for key, counts in summary[category].items())
        _csv(out_dir / "summary_groups.csv", groups,
             ["group_type", "group", "total", "passed", "failed", "pass_rate",
              "completed", "refused", "stopped", "timeout", "no_path", "error", "collision"])
    manifest["source_at_campaign_end"] = source_fingerprint()
    manifest["source_unchanged_during_campaign"] = manifest["source_at_campaign_end"] == environment["source"]
    summary["source_unchanged_during_campaign"] = manifest["source_unchanged_during_campaign"]
    write_json(out_dir / "manifest.json", manifest)
    write_json(out_dir / "summary.json", summary)
    return summary


def _compare_trace(original, replayed):
    if len(original) != len(replayed):
        return {"match": False, "reason": "sample_count_differs", "original": len(original), "replayed": len(replayed)}
    max_difference = 0.0
    for index, (old, new) in enumerate(zip(original, replayed)):
        for key in NUMERIC_FIELDS:
            if old.get(key) is None or new.get(key) is None:
                return {"match": False, "reason": "invalid_numeric_sample", "sample": index, "field": key}
            delta = abs(old[key] - new[key])
            max_difference = max(max_difference, delta)
            if delta > 1e-10:
                return {"match": False, "reason": "numeric_sample_differs", "sample": index, "field": key,
                        "difference": delta}
        for key in ("state", "phase", "world_step", "reported_collision"):
            if old.get(key) != new.get(key):
                return {"match": False, "reason": "sample_metadata_differs", "sample": index, "field": key}
    return {"match": True, "samples": len(original), "max_abs_numeric_difference": max_difference}


def replay_case(case_dir, out_dir=None, *, replan=False):
    case_dir = Path(case_dir)
    case_data = read_json(case_dir / "case.json")
    case = ManeuverCase.from_dict(case_data)
    original = read_json(case_dir / "result.json")
    execution = read_json(case_dir / "execution.json")
    parameters = read_json(case_dir / "parameters.json")
    provenance = read_json(case_dir / "provenance.json")
    required = {"case_fingerprint", "parameters_fingerprint", "execution_fingerprint", "legs", "actual_outcome", "verdict"}
    if not isinstance(original, dict) or required - original.keys():
        raise ValueError("Unsupported/incomplete result.json: required replay fields or fingerprints are missing")
    if not isinstance(execution, dict) or execution.get("schema_version") != SCHEMA_VERSION or not isinstance(execution.get("legs"), list):
        raise ValueError("Unsupported/incomplete execution.json")
    if _hash_json(case_data) != original["case_fingerprint"] or _hash_json(parameters) != original["parameters_fingerprint"]:
        raise ValueError("Frozen input/parameters fingerprint mismatch; replay input has changed")
    if _hash_json(execution) != original["execution_fingerprint"]:
        raise ValueError("Frozen execution fingerprint mismatch; decisions/trajectories/triggers have changed")
    if not execution.get("legs"):
        if not replan:
            raise ValueError("No recorded planning decision; use replay --replan to rerun this frozen input")
    destination = Path(out_dir) if out_dir else case_dir.parent / (case_dir.name + ("_replan_" if replan else "_replay_") + _timestamp())
    current_source = source_fingerprint()
    result = run_case(case, destination, frozen_legs=None if replan else execution["legs"], parameters=parameters,
                      provenance={"source": current_source, "replayed_from": str(case_dir.resolve())})
    comparisons = []
    if not replan:
        for i in range(min(len(original["legs"]), len(result["legs"]))):
            old_path, new_path = case_dir / "legs" / f"leg_{i + 1:02d}", destination / "legs" / f"leg_{i + 1:02d}"
            comparison = _compare_trace(read_json(old_path / "trace.json"), read_json(new_path / "trace.json"))
            comparison["leg"] = i + 1
            comparison["metrics_match"] = original["legs"][i]["metrics"] == result["legs"][i]["metrics"]
            comparison["events_match"] = read_json(old_path / "events.json") == read_json(new_path / "events.json")
            comparisons.append(comparison)
    outcome_match = all(original.get(key) == result.get(key)
                        for key in ("actual_outcome", "verdict", "followup_outcome", "reasons"))
    match = (not replan and len(original["legs"]) == len(result["legs"]) == len(comparisons)
             and outcome_match and all(c["match"] and c["metrics_match"] and c["events_match"] for c in comparisons))
    source_before = provenance.get("source")
    report = {"schema_version": SCHEMA_VERSION, "mode": "replan_frozen_input" if replan else "replay_frozen_execution",
              "match": match if not replan else None, "outcome_match": outcome_match, "comparisons": comparisons,
              "original_outcome": original["actual_outcome"], "replayed_outcome": result["actual_outcome"],
              "original_verdict": original["verdict"], "replayed_verdict": result["verdict"],
              "source_changed": source_before != current_source, "original_source": source_before,
              "current_source": current_source, "frozen_config_match": True,
              "decision_only_legs": [i + 1 for i, leg in enumerate(execution["legs"]) if leg.get("trajectory") is None],
              "scope": "Frozen decisions without trajectories are archived/rescored, not re-searched. Planning wall time is not replayed.",
              "artifact_dir": str(destination.resolve())}
    write_json(destination / "replay_report.json", report)
    return report


def _seeds(value):
    try:
        seeds = [int(piece.strip()) for piece in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seeds must be comma-separated integers") from exc
    if not seeds or len(seeds) != len(set(seeds)):
        raise argparse.ArgumentTypeError("seeds must be a nonempty list without duplicates")
    return seeds


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run base and robustness cases in SIM")
    run.add_argument("--out", type=Path)
    run.add_argument("--seeds", type=_seeds, default=[0])
    run.add_argument("--case", action="append", dest="selected", help="Exact case ID; may be repeated")
    run.add_argument("--case-file", type=Path, help="Run one frozen case.json; seed/selection options do not apply")
    listing = sub.add_parser("list", help="List every fixture and its frozen expectation")
    listing.add_argument("--seeds", type=_seeds, default=[0])
    listing.add_argument("--json", action="store_true")
    replay = sub.add_parser("replay", help="Replay frozen trajectories and trigger steps")
    replay.add_argument("case_directory", type=Path)
    replay.add_argument("--out", type=Path)
    replay.add_argument("--replan", action="store_true", help="Rerun frozen input through current planner; timing may differ")
    args = parser.parse_args(argv)
    try:
        from autopark.power_throttling import apply_ecoqos_policy
        apply_ecoqos_policy("maneuver_bench")
        if args.command == "list":
            cases = build_suite(args.seeds)
            rows = [{"case_id": c.case_id, "family": c.family, "seed": c.scenario.seed,
                     "expected": c.expected, "description": c.description} for c in cases]
            if args.json:
                print(json.dumps(rows, ensure_ascii=True, indent=2, allow_nan=False))
            else:
                for row in rows:
                    print(f"{row['case_id']}\tseed={row['seed']}\t{row['family']}\t{row['expected']}")
            return 0
        if args.command == "replay":
            report = replay_case(args.case_directory, args.out, replan=args.replan)
            print(json.dumps(report, ensure_ascii=True, allow_nan=False))
            return (0 if report["replayed_verdict"] == "PASS" else 1) if args.replan else (0 if report["match"] else 1)
        if args.case_file and (args.selected or args.seeds != [0]):
            raise ValueError("--case-file cannot be combined with --case or nondefault --seeds")
        cases = [ManeuverCase.from_dict(read_json(args.case_file))] if args.case_file else build_suite(args.seeds, args.selected)
        out_dir = args.out or Path("runs") / ("maneuver_suite_" + _timestamp())
        summary = run_campaign(cases, out_dir, arguments=vars(args))
        print(json.dumps({"artifact_dir": str(out_dir.resolve()), **summary["overall"]}, allow_nan=False))
        return 0 if summary["overall"]["failed"] == 0 and summary["source_unchanged_during_campaign"] else 1
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"maneuver_bench input/artifact error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
