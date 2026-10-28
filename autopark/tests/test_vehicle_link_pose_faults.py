"""Pose-source failures must stop the maneuver; only simulated I/O is used."""
from dataclasses import replace
import math

import pytest

from autopark.application.session import SessionError, SessionState
from autopark.application.vehicle_link import DriveMode, PoseSample, VehicleLink
from autopark.storage import run_store
from autopark.transport.protocol import State
from tests.test_session_vehicle import run_until_done, sim_io, straight_session


class OneBadPose:
    source_id = "pose_fault_test"
    simulated = True

    def __init__(self, io):
        self.io = io
        self.fault = None

    def latest(self):
        sample = PoseSample(self.io.truth.pose, self.io.now(), self.source_id, True)
        fault, self.fault = self.fault, None
        if fault == "exception":
            raise RuntimeError("localizer failed")
        if fault == "nan_x":
            return replace(sample, pose=replace(sample.pose, x=math.nan))
        if fault == "inf_yaw":
            return replace(sample, pose=replace(sample.pose, yaw=math.inf))
        if fault == "nan_time":
            return replace(sample, t=math.nan)
        if fault == "wrong_type":
            return object()
        return sample


def opened_session(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    source = OneBadPose(io)
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=source)
    session.set_vehicle_link(link)
    session.start_run()
    return session, link, source


@pytest.mark.parametrize("fault", ["exception", "nan_x", "inf_yaw", "nan_time", "wrong_type"])
@pytest.mark.parametrize("read_at", ["observe", "estimate"])
def test_transient_bad_pose_stops_without_polluting_world(scenario, cfg, fault, read_at):
    session, link, source = opened_session(scenario, cfg)
    try:
        session.advance(0.2)
        wanted_tick = 0 if read_at == "observe" else 1
        while session.world.step_count % session.CONTROL_EVERY != wanted_tick:
            session.advance(session.PHYSICS_DT)
        assert session.world.state.speed > 0
        before = len(link.command_rows)
        before_poses = len(link.pose_rows)
        source.fault = fault
        run_until_done(session, step=0.05)
        assert session.state == SessionState.STOPPED
        assert session.world.state.usable()
        assert link.pose_rows[before_poses]["use"] == read_at
        assert any(e.code in ("POSE_SOURCE_ERROR", "INVALID_POSE") for e in session.safety_events)
        # The source recovers after one bad read, but the maneuver stays stopped.
        assert not any(r["kind"] == "TRACK" and r["sent"] for r in link.command_rows[before:])
        assert link.io.firmware.state == State.DISARMED
        session.advance(0.5)
        assert session.state == SessionState.STOPPED
    finally:
        session.close()


@pytest.mark.parametrize("fault", ["nan_x", "inf_yaw", "nan_time", "wrong_type"])
def test_start_refuses_malformed_pose_before_arm(scenario, cfg, fault):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    source = OneBadPose(io)
    source.fault = fault
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=source)
    session.set_vehicle_link(link)
    try:
        with pytest.raises(SessionError):
            session.start_run()
        assert io.latest().state == State.DISARMED
        assert io.stats.commands_sent == 0
    finally:
        session.close()


def test_pose_failure_export_replays_same_stop(scenario, cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(run_store, "environment", lambda: {"test": True})
    session, link, source = opened_session(scenario, cfg)
    replayed = None
    try:
        session.advance(0.205)
        source.fault = "exception"
        run_until_done(session, step=0.05)
        bundle = run_store.export_run(session, tmp_path / "pose_failure")
        replayed, report = run_store.replay_vehicle_run(bundle)
        assert report.ok, "\n".join(report.lines())
        assert replayed.state == SessionState.STOPPED
    finally:
        session.close()
        if replayed is not None:
            replayed.close()
