"""CLI/artifact/replay checks, including preserved pre-motion failures."""
from dataclasses import replace
import json

import pytest

from autopark.application.session import Session, SessionState
from autopark.evaluation import maneuver_bench as bench
from autopark.evaluation.maneuver_cases import build_cases
from autopark.evaluation.maneuver_robustness import build_robustness_cases
from autopark.planning.hybrid_astar import PlanResult


def _case(case_id="door_forward_center"):
    return next(c for c in build_cases(0) if c.case_id == case_id)


def _force_status(monkeypatch, status):
    def plan(session):
        result = PlanResult(status, "Test decision with no motion")
        session._apply_plan(result, session.plan_version)
        return result
    monkeypatch.setattr(Session, "plan_sync", plan)


@pytest.mark.parametrize("status,outcome,scope", [
    ("TIMEOUT", "timeout", "planner_budget"), ("NO_PATH", "no_path", None), ("ERROR", "error", None),
])
def test_preserves_and_decision_replays_unplanned_failure(tmp_path, monkeypatch, status, outcome, scope):
    _force_status(monkeypatch, status)
    source = tmp_path / "original"
    result = bench.run_case(_case(), source)
    assert result["actual_outcome"] == outcome
    assert result["verdict"] == "FAIL"
    assert result["legs"][0].get("timeout_scope") == scope
    assert bench.read_json(source / "legs/leg_01/trajectory.json") is None
    report = bench.replay_case(source, tmp_path / "replay")
    assert report["match"] is True
    assert report["decision_only_legs"] == [1]
    assert report["original_verdict"] == report["replayed_verdict"] == "FAIL"


def test_exception_is_preserved_and_replayed_as_archived_error(tmp_path, monkeypatch):
    def broken(session):
        raise RuntimeError("synthetic planner exception")
    monkeypatch.setattr(Session, "plan_sync", broken)
    source = tmp_path / "original"
    result = bench.run_case(_case(), source)
    assert result["verdict"] == "FAIL" and result["actual_outcome"] == "error"
    assert (source / "legs/leg_01/error.json").exists()
    report = bench.replay_case(source, tmp_path / "replay")
    assert report["match"] is True and report["decision_only_legs"] == [1]


def test_replay_detects_tampered_execution(tmp_path, monkeypatch):
    _force_status(monkeypatch, "TIMEOUT")
    source = tmp_path / "original"
    bench.run_case(_case(), source)
    execution = bench.read_json(source / "execution.json")
    execution["legs"][0]["plan"]["status"] = "NO_PATH"
    bench.write_json(source / "execution.json", execution)
    with pytest.raises(ValueError, match="execution fingerprint"):
        bench.replay_case(source, tmp_path / "replay")
    assert not (tmp_path / "replay").exists()


def test_replay_detects_tampered_config(tmp_path, monkeypatch):
    _force_status(monkeypatch, "TIMEOUT")
    source = tmp_path / "original"
    bench.run_case(_case(), source)
    data = bench.read_json(source / "case.json")
    data["scenario"]["seed"] = 7
    bench.write_json(source / "case.json", data)
    with pytest.raises(ValueError, match="input/parameters fingerprint"):
        bench.replay_case(source, tmp_path / "replay")


def test_actual_physics_trace_and_frozen_replay(tmp_path):
    source = tmp_path / "original"
    result = bench.run_case(_case(), source)
    assert result["verdict"] == "PASS", result["reasons"]
    trace = bench.read_json(source / "legs/leg_01/trace.json")
    motion = [r for r in trace if r["phase"] == "motion"]
    holds = [r for r in trace if r["phase"] == "hold"]
    assert len(motion) > 100
    assert all(b["sim_time_s"] - a["sim_time_s"] == pytest.approx(.005) for a, b in zip(motion, motion[1:]))
    assert len(holds) == 200
    assert all(r["sim_time_s"] == motion[-1]["sim_time_s"] for r in holds)
    report = bench.replay_case(source, tmp_path / "replay")
    assert report["match"] is True
    assert report["comparisons"][0]["max_abs_numeric_difference"] == 0


def test_simulation_budget_is_distinct_from_planning_budget(tmp_path):
    case = replace(_case(), sim_timeout_s=.01)
    result = bench.run_case(case, tmp_path / "timeout")
    assert result["actual_outcome"] == "timeout" and result["verdict"] == "FAIL"
    assert result["legs"][0]["timeout_scope"] == "simulation_budget"
    assert "not_infeasibility_proof" in ";".join(result["reasons"])
    assert bench.replay_case(tmp_path / "timeout", tmp_path / "replay")["match"]


def test_campaign_collects_environment_once_and_keeps_failure_denominators(tmp_path, monkeypatch):
    _force_status(monkeypatch, "NO_PATH")
    calls = []
    original_environment = bench.environment_manifest
    def collect():
        calls.append(True)
        return original_environment()
    monkeypatch.setattr(bench, "environment_manifest", collect)
    cases = [_case(), replace(_case("refuse_start_overlap"), scenario=replace(_case("refuse_start_overlap").scenario, seed=1))]
    summary = bench.run_campaign(cases, tmp_path / "campaign")
    assert calls == [True]
    assert summary["overall"]["total"] == summary["overall"]["failed"] == 2
    assert summary["by_expected"]["complete"]["total"] == summary["by_expected"]["refuse"]["total"] == 1
    assert summary["by_expected"]["stop"]["pass_rate"] is None
    assert summary["source_unchanged_during_campaign"]
    assert (tmp_path / "campaign/summary.csv").is_file()
    assert (tmp_path / "campaign/summary_groups.csv").is_file()


def test_existing_destination_is_never_overwritten(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("retain")
    with pytest.raises(FileExistsError):
        bench.run_case(_case(), target)
    assert marker.read_text() == "retain"
    assert not (target / "case.json").exists()


def test_strict_json_unknown_quantities_and_input_rejection(tmp_path):
    path = tmp_path / "diagnostic.json"
    bench.write_json(path, {"unavailable": float("inf"), "invalid": float("nan")})
    assert json.loads(path.read_text()) == {"unavailable": None, "invalid": None}
    path.write_text('{"bad": NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="Nonfinite"):
        bench.read_json(path)


def test_cli_unknown_case_and_bad_case_file_exit_two(tmp_path, capsys):
    assert bench.main(["run", "--case", "no_such_case", "--out", str(tmp_path / "absent")]) == 2
    assert not (tmp_path / "absent").exists()
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    assert bench.main(["run", "--case-file", str(invalid), "--out", str(tmp_path / "absent")]) == 2
    assert "input/artifact error" in capsys.readouterr().err


def test_cli_failure_exit_one_and_existing_artifact_exit_two(tmp_path, monkeypatch):
    _force_status(monkeypatch, "TIMEOUT")
    case_path = tmp_path / "case.json"
    bench.write_json(case_path, _case().to_dict())
    args = ["run", "--case-file", str(case_path), "--out", str(tmp_path / "campaign")]
    assert bench.main(args) == 1
    assert bench.main(args) == 2


def test_cli_rejects_duplicate_seeds():
    with pytest.raises(SystemExit) as error:
        bench.main(["run", "--seeds", "0,0"])
    assert error.value.code == 2


def test_already_stopping_cannot_fabricate_a_new_user_stop_decision(tmp_path, monkeypatch):
    case = next(c for c in build_robustness_cases(0) if c.case_id == "fault_user_stop")
    case = replace(case, fault=replace(case.fault, at_s=.21))
    original_advance = Session.advance
    def preexisting_stop(session, dt):
        if session.world and session.world.time >= .2 - 1e-10 and session.state == SessionState.RUNNING:
            session.request_stop("Unrelated earlier stop")
        return original_advance(session, dt)
    monkeypatch.setattr(Session, "advance", preexisting_stop)
    result = bench.run_case(case, tmp_path / "run")
    assert result["verdict"] == "FAIL"
    events = bench.read_json(tmp_path / "run/legs/leg_01/events.json")
    assert not any(e["kind"] == "fault_applied" for e in events)
    assert any("required_fault_not_applied" in reason for reason in result["reasons"])


def test_data_loss_before_first_motion_can_be_a_valid_stationary_stop(tmp_path):
    case = next(c for c in build_robustness_cases(0) if c.case_id == "fault_data_loss_latched")
    case = replace(case, fault=replace(case.fault, at_s=0.0))
    result = bench.run_case(case, tmp_path / "run")
    assert result["verdict"] == "PASS", result["reasons"]
    assert result["actual_outcome"] == "stopped"
    assert result["metrics"]["stop_delay_s"] == 0
    assert result["metrics"]["total_actual_distance_m"] == 0
