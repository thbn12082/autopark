"""Giới hạn động phải giống nhau khi kiểm chứng, xem trước và chạy."""
from dataclasses import replace

import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.domain.types import Obstacle
from autopark.simulation.rollout import rollout
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from tests.conftest import PROJECT_ROOT


def test_rollout_and_runtime_stop_for_same_distance_limit():
    scenario = load_scenario(PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json")
    cfg = load_vehicle_config(scenario.vehicle_config_path)
    session = Session(scenario, cfg)
    try:
        result = session.plan_sync()
        assert result.ok, result.message
        session.start_run()
        # Siết sau khi chạy để tái hiện bộ bám đi quá quãng còn lại; trước START
        # giới hạn đường hình học được kiểm riêng.
        scenario.maneuver = replace(scenario.maneuver, max_path_length_m=0.25)
        preview = rollout(scenario, cfg, result.trajectory).report
        for _ in range(400):
            session.advance(.25)
            if not session.simulating:
                break
        assert session.state == SessionState.STOPPED
        assert any(event.code == "MANEUVER_DISTANCE" for event in session.safety_events)
        assert not preview.completed
        assert preview.reason == session.stop_reason
        assert abs(preview.distance - session.report.distance) < 1e-6
    finally:
        session.close()


def test_portfolio_rejects_candidate_that_rollout_must_stop():
    from autopark.planning import cand_reference, portfolio
    scenario = load_scenario(PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json")
    cfg = load_vehicle_config(scenario.vehicle_config_path)
    session = Session(scenario, cfg)
    try:
        original = session.plan_sync()
        assert original.ok, original.message
        scenario.maneuver = replace(scenario.maneuver, max_path_length_m=0.25)
        rung = portfolio.Rung("candidate", lambda *args, **kwargs: original,
                              cand_reference.RefParams(), 1.0)
        # Không đặt max_path_length ở đây để kiểm riêng đường kiểm chứng động:
        # quỹ đạo đến được đích nếu bỏ qua giới hạn chạy, nhưng rollout phải dừng.
        params = portfolio.PortfolioParams(ladder=[rung], verify_scenario=scenario)
        result = portfolio.plan(scenario.start, scenario.goal.pose, cfg, scenario.obstacles,
                                scenario.bounds, params=params)
        assert not result.ok
    finally:
        session.close()


def test_historical_replay_refused_with_clear_reason(tmp_path, capsys):
    import json
    from autopark.evaluation.replay import EXIT_NOT_SUPPORTED, main

    scenario = load_scenario(PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json").to_dict()
    scenario.pop("maneuver")
    (tmp_path / "config_snapshot").mkdir()
    (tmp_path / "config_snapshot" / "run.json").write_text(
        json.dumps({"scenario": scenario}), encoding="utf-8")
    (tmp_path / "result.json").write_text("{}", encoding="utf-8")
    (tmp_path / "events.jsonl").write_text("", encoding="utf-8")
    assert main([str(tmp_path)]) == EXIT_NOT_SUPPORTED
    assert "gói lịch sử" in capsys.readouterr().out


@pytest.mark.parametrize("change", ["start", "goal", "obstacle"])
def test_start_refuses_stale_trajectory_before_vehicle_io(change):
    scenario = load_scenario(PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json")
    cfg = load_vehicle_config(scenario.vehicle_config_path)
    session = Session(scenario, cfg)
    try:
        assert session.plan_sync().ok
        class Link:
            def record_refused_start(self, code, message):
                self.code = code
            def begin_run(self, *args):
                pytest.fail("stale trajectory must be refused before vehicle I/O")
            def close(self):
                pass
        link = Link()
        session.set_vehicle_link(link)
        if change == "start":
            scenario.start = replace(scenario.start, x=scenario.start.x + .01)
        elif change == "goal":
            scenario.goal = replace(scenario.goal, pose=replace(scenario.goal.pose, x=scenario.goal.pose.x + .01))
        else:
            p = session.trajectory.points[len(session.trajectory.points) // 2].pose
            scenario.obstacles.append(Obstacle("new", p.x, p.y, .02, .02, 0))
        with pytest.raises(SessionError):
            session.start_run()
        if change != "obstacle":
            assert link.code == "START_MANEUVER_LIMIT"
    finally:
        session.close()
