"""Background lifecycle: cancellation, stale results, serialization and preview."""
import threading

import pytest

from autopark.application import session as session_module
from autopark.application.session import Session, SessionError, SessionState
from autopark.domain.computation import ComputationCancelled
from autopark.domain.types import VehicleState
from autopark.planning.hybrid_astar import PlanResult
from autopark.planning.trajectory import build_trajectory
from autopark.simulation.rollout import RolloutResult


@pytest.fixture
def session(scenario, cfg):
    s = Session(scenario, cfg)
    yield s
    s.close()


def ready(s):
    trajectory = build_trajectory([(s.scenario.start, 1, 0.0)], s.scenario.start, s.cfg, 0.15, 0.08)
    s._apply_plan(PlanResult("OK", "test", trajectory), s.plan_version)


def preview_result(s):
    return RolloutResult(states=[VehicleState(s.scenario.start, 0.0, 0.0, 0.0)])


def test_cancel_then_replan_uses_one_worker_and_discards_old_result(monkeypatch, session):
    first_entered, release_first = threading.Event(), threading.Event()
    second_entered, release_second = threading.Event(), threading.Event()
    calls = []
    active = maximum = 0
    lock = threading.Lock()

    def plan(*args, **kwargs):
        nonlocal active, maximum
        with lock:
            calls.append(args[0].start)
            call = len(calls)
            active += 1
            maximum = max(maximum, active)
        try:
            if call == 1:
                first_entered.set()
                assert release_first.wait(3)
                # Deliberately ignores cancellation: this late success must be discarded.
                return PlanResult("OK", "old result")
            second_entered.set()
            assert release_second.wait(3)
            return PlanResult("NO_PATH", "new result")
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(session_module, "plan_parking", plan)
    try:
        session.plan_async()
        assert first_entered.wait(1)
        first = session._plan_future
        session.cancel_plan()
        for _ in range(4):
            session.plan_async()
            queued = session._plan_future
            session.cancel_plan()
            assert queued.cancelled()
        session.plan_async()
        last = session._plan_future
        release_first.set()
        first.result(timeout=2)
        assert second_entered.wait(1)
        assert session.poll_plan() is None
        assert session.state == SessionState.PLANNING
        assert session.plan_result is None
        release_second.set()
        last.result(timeout=2)
        assert session.poll_plan().message == "new result"
        assert session.state == SessionState.EDITING
        assert maximum == 1
        assert len(calls) == 2
    finally:
        release_first.set()
        release_second.set()


def test_cancel_signals_running_planner_and_close_blocks_new_work(monkeypatch, session):
    entered = threading.Event()

    def plan(*args, control, **kwargs):
        entered.set()
        assert control.cancel_event.wait(2)
        control.check()

    monkeypatch.setattr(session_module, "plan_parking", plan)
    session.plan_async()
    future = session._plan_future
    assert entered.wait(1)
    session.close()
    assert future.result(timeout=1).status == "CANCELLED"
    assert session.poll_plan() is None
    with pytest.raises(SessionError, match="đóng"):
        session.plan_async()


@pytest.mark.parametrize("async_mode", [False, True])
def test_planner_exception_recovers_session(monkeypatch, session, async_mode):
    def broken(*args, **kwargs):
        raise RuntimeError("diagnostic failure")

    monkeypatch.setattr(session_module, "plan_parking", broken)
    if async_mode:
        session.plan_async()
        session._plan_future.result(timeout=1)
        result = session.poll_plan()
    else:
        result = session.plan_sync()
    assert result.status == "ERROR"
    assert session.state == SessionState.EDITING
    assert session.trajectory is None


def test_preview_is_cancellable_and_does_not_apply_a_partial_result(monkeypatch, session):
    ready(session)
    entered = threading.Event()

    def run(*args, control, **kwargs):
        entered.set()
        assert control.cancel_event.wait(2)
        control.check()

    monkeypatch.setattr(session_module, "rollout", run)
    session.begin_preview_async()
    assert session.state == SessionState.PREPARING_PREVIEW
    future = session._preview_future
    assert entered.wait(1)
    session.end_preview()
    with pytest.raises(ComputationCancelled):
        future.result(timeout=1)
    assert session.poll_preview() is None
    assert session.state == SessionState.READY
    assert session.preview is None


def test_preview_cache_tracks_controller_settings_and_scene_edits(monkeypatch, session):
    ready(session)
    calls = []

    def run(*args, **kwargs):
        calls.append(1)
        return preview_result(session)

    monkeypatch.setattr(session_module, "rollout", run)
    session.begin_preview_async()
    session._preview_future.result(timeout=1)
    first = session.poll_preview()
    session.end_preview()
    session.begin_preview_async()
    assert session.state == SessionState.PREVIEW
    assert session.preview is first
    assert len(calls) == 1
    session.end_preview()
    session.tracker_params.k_heading += 0.1
    session.begin_preview_async()
    assert session.state == SessionState.PREPARING_PREVIEW
    session._preview_future.result(timeout=1)
    session.poll_preview()
    assert len(calls) == 2
    session.end_preview()
    session.set_start(session.scenario.start)
    assert session.preview is None


def test_preview_error_keeps_valid_path_and_recovers_ready(monkeypatch, session):
    ready(session)
    trajectory = session.trajectory

    def broken(*args, **kwargs):
        raise RuntimeError("preview failure")

    monkeypatch.setattr(session_module, "rollout", broken)
    session.begin_preview_async()
    assert isinstance(session._preview_future.exception(timeout=1), RuntimeError)
    assert session.poll_preview() is None
    assert session.state == SessionState.READY
    assert session.trajectory is trajectory
    assert "preview failure" in session.preview_error


def test_preview_discards_result_if_settings_change_mid_computation(monkeypatch, session):
    ready(session)
    monkeypatch.setattr(session_module, "rollout", lambda *a, **kw: preview_result(session))
    session.begin_preview_async()
    session._preview_future.result(timeout=1)
    session.tracker_params.k_heading += 0.1
    assert session.poll_preview() is None
    assert session.state == SessionState.READY
    assert session.preview is None
