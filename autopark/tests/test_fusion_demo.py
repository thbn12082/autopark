"""Bench demo loop with a scripted LiDAR source: an object appearing mid-run stops the simulated car."""
import math

import pytest

np = pytest.importorskip("numpy")

from autopark.fusion.demo import run_demo  # noqa: E402
from autopark.lidar.rplidar_c1 import ScanReadError  # noqa: E402
from tests.test_fusion import scan_with_object  # noqa: E402


class ScriptedLidar:
    """Nothing seen for the first `quiet` reads, then a box 0.6 m ahead of the (fixed) sensor, then an outage."""

    def __init__(self, quiet: int = 8, outage_after: int | None = None):
        self.reads = 0
        self.quiet = quiet
        self.outage_after = outage_after
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def read(self):
        self.reads += 1
        self.t += 0.1
        if self.outage_after is not None and self.reads > self.outage_after:
            self.t += 0.5                                              # time passes, no scan arrives
            raise ScanReadError("no complete revolution within 1.0 s")
        distance = None if self.reads <= self.quiet else 0.6
        return scan_with_object(self.t, distance, half_width_deg=8.0)

    def flush(self) -> None:
        self.flushed = True

    def close(self) -> None:
        pass


def test_object_appearing_during_the_run_stops_the_car(cfg):
    logs = []
    report = run_demo(ScriptedLidar(quiet=8), seconds=20.0, cfg=cfg, initial_skip=0, initial_scans=5, log=logs.append)
    assert report["initial_obstacles"] == 0 and report["new_obstacles"] >= 1
    # cells may still be added while braking (persistence completes a scan later): several MAP_CHANGED are
    # allowed while STOPPING, then exactly one WAIT_REPLAN once the car stands still
    events = report["events"]
    assert report["status"] == "STOPPED" and events[0] == "MAP_CHANGED" and events[-1] == "WAIT_REPLAN"
    assert set(events) == {"MAP_CHANGED", "WAIT_REPLAN"} and events.count("WAIT_REPLAN") == 1
    assert report["collided"] is False and report["read_errors"] == 0
    assert any("vật cản mới" in line for line in logs)


def test_lidar_outage_during_the_run_stops_the_car(cfg):
    report = run_demo(ScriptedLidar(quiet=10 ** 6, outage_after=7), seconds=20.0, cfg=cfg, initial_skip=0, initial_scans=5, log=lambda _: None)
    assert report["status"] == "STOPPED" and report["read_errors"] >= 1 and report["bridge_stops"] >= 1
    assert "không hợp lệ" in report["stop_reason"] and report["events"] == []


def test_objects_seen_before_planning_become_scenario_obstacles(cfg):
    class Wall(ScriptedLidar):
        def read(self):
            self.reads += 1
            self.t += 0.1
            return scan_with_object(self.t, 1.2, half_width_deg=60.0)   # a wide wall 1.2 m ahead, inside the 3 m board

    report = run_demo(Wall(), seconds=1.0, cfg=cfg, initial_skip=2, initial_scans=5, log=lambda _: None)
    assert report["initial_obstacles"] >= 1
    assert report["status"] is not None                                  # planned around it or reported no path
