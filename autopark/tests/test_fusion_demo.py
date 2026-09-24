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


# ---- bỏ vòng khởi động mô-tơ C1 (thêm muộn tối 24/09/2026; chỉ nguồn giả, CHƯA chạy với C1 thật) --------------------
class FakeWall:
    """Wall clock for the run loop: each call advances `step` seconds (deterministic, no real waiting)."""

    def __init__(self, step: float = 0.02):
        self.t, self.step = 0.0, step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


class SpinUpLidar(ScriptedLidar):
    """Stamps like the C1 driver's session clock (seconds since SCAN): first revolution after `t_first`, revolutions
    `period` long (p07: the early ones ≈ 0.078 s while the motor is still fast). Every revolution stamped before
    `settled_s` shows a box 0.6 m ahead, standing in for spin-up scans that must not reach the static map."""

    def __init__(self, t_first: float = 2.2, period: float = 0.08, settled_s: float = 4.5):
        super().__init__(quiet=0)
        self.t = t_first - period
        self.period, self.settled_s = period, settled_s
        self.stamps = []

    def read(self):
        self.reads += 1
        self.t += self.period
        self.stamps.append(self.t)
        return scan_with_object(self.t, 0.6 if self.t < self.settled_s else None, half_width_deg=8.0)


def test_warmup_waits_on_the_source_clock_not_only_on_the_revolution_count(cfg):
    # count only: 22 revolutions of 0.08 s after 2.2 s end at ≈ 3.96 s, so spin-up scans build the static map
    counted = run_demo(SpinUpLidar(), seconds=0.2, cfg=cfg, initial_skip=22, initial_scans=5, clock=FakeWall(),
                       log=lambda _line: None)
    assert counted["warmup"]["skipped"] == 22 and counted["warmup"]["first_map_scan_s"] < 4.5
    assert counted["initial_obstacles"] >= 1

    source, logs = SpinUpLidar(), []
    timed = run_demo(source, seconds=0.2, cfg=cfg, initial_skip=22, warmup_s=4.5, initial_scans=5, clock=FakeWall(),
                     log=logs.append)
    warmup = timed["warmup"]
    before = sum(t < 4.5 for t in source.stamps)
    assert warmup["skipped"] == before == 29                              # 2.2 + 28 × 0.08 = 4.44 s < 4.5 s
    assert warmup["first_map_scan_s"] == source.stamps[before] >= 4.5    # first revolution past both thresholds
    assert timed["initial_obstacles"] == 0 and timed["status"] is not None
    assert warmup["map_beams_min"] == warmup["map_beams_max"] == 360
    assert warmup["min_revolutions"] == 22 and warmup["until_s"] == 4.5
    assert any(line.startswith("bỏ 29 vòng khởi động mô-tơ") and "360–360 tia/vòng" in line for line in logs)


def test_revolution_count_still_applies_when_the_source_clock_is_past_the_warmup(cfg):
    source = SpinUpLidar(t_first=100.0, settled_s=0.0)                   # driver started long ago: nothing to wait for
    report = run_demo(source, seconds=0.2, cfg=cfg, initial_skip=22, warmup_s=4.5, initial_scans=5, clock=FakeWall(),
                      log=lambda _line: None)
    assert report["warmup"]["skipped"] == 22 and report["warmup"]["first_map_scan_s"] == source.stamps[22]

    source = SpinUpLidar(settled_s=0.0)
    report = run_demo(source, seconds=0.2, cfg=cfg, initial_skip=0, warmup_s=0.0, initial_scans=5, clock=FakeWall(),
                      log=lambda _line: None)
    assert report["warmup"]["skipped"] == 0 and report["warmup"]["first_map_scan_s"] == source.stamps[0]
    report = run_demo(SpinUpLidar(settled_s=0.0), seconds=0.2, cfg=cfg, initial_scans=5, clock=FakeWall(),
                      log=lambda _line: None)                            # library defaults: 22 revolutions, no wait
    assert report["warmup"]["skipped"] == 22 and report["warmup"]["until_s"] == 0.0
    with pytest.raises(ValueError):
        run_demo(SpinUpLidar(), seconds=0.2, cfg=cfg, initial_scans=0, log=lambda _line: None)


def test_failures_during_a_timed_warmup_end_before_the_run(cfg):
    class Unplugged(SpinUpLidar):
        def read(self):
            if self.reads >= 10:
                raise OSError("ClearCommError failed")                    # cable pulled while the motor spins up
            return super().read()

    report = run_demo(Unplugged(), seconds=1.0, cfg=cfg, initial_skip=22, warmup_s=4.5, log=lambda _line: None)
    assert report["status"] == "LỖI LIDAR TRƯỚC KHI CHẠY" and "trong lúc khởi động" in report["error"]
    assert report["transport_error"] == "OSError: ClearCommError failed" and report["scans"] == 10
    assert report["warmup"]["skipped"] == 10 and report["warmup"]["first_map_scan_s"] is None

    live_view = pytest.importorskip("autopark.lidar.live_view")          # defines ScanStreamEnded (pulls in PySide6)

    class ShortRecording(SpinUpLidar):
        def read(self):
            if self.reads >= 30:
                raise live_view.ScanStreamEnded("hết bản ghi")
            return super().read()

    report = run_demo(ShortRecording(t_first=0.1, period=0.1), seconds=1.0, cfg=cfg, initial_skip=22, warmup_s=4.5,
                      log=lambda _line: None)
    assert report["stream_ended"] is True and report["error"].startswith("bản ghi LiDAR hết trong lúc khởi động")
    assert report["warmup"]["skipped"] == 30 and report["transport_error"] is None            # all 30 read, all skipped


def test_main_passes_the_warmup_options(monkeypatch, capsys):
    from autopark.fusion import demo
    from autopark.lidar.rplidar_c1 import RplidarC1Source

    class Dummy:                                                         # KHÔNG mở cổng thật
        def start(self):
            pass

        def close(self):
            pass

    calls = []

    def fake_run_demo(source, **kwargs):
        calls.append(kwargs)
        return {"status": "COMPLETED", "error": None, "transport_error": None}

    monkeypatch.setattr(RplidarC1Source, "open", classmethod(lambda cls, port, **kwargs: Dummy()))
    monkeypatch.setattr(demo, "run_demo", fake_run_demo)
    assert demo.main(["--port", "CONG_GIA", "--seconds", "1"]) == 0
    assert calls[-1]["initial_skip"] == demo.SPIN_UP_REVOLUTIONS == 22 and calls[-1]["warmup_s"] == 0.0
    assert demo.main(["--port", "CONG_GIA", "--seconds", "1", "--initial-skip", "30", "--warmup", "4.5"]) == 0
    assert calls[-1]["initial_skip"] == 30 and calls[-1]["warmup_s"] == 4.5
    capsys.readouterr()


# ---- tham số khởi động sai (thêm sau rà soát, muộn tối 24/09/2026): từ chối trước khi đọc LiDAR / mở cổng -----------
class NeverRead:
    """Tham số sai phải bị từ chối trước lần đọc đầu tiên: gọi read()/now() là test fail."""

    def read(self):
        pytest.fail("run_demo đọc LiDAR trước khi kiểm tra tham số")

    def now(self) -> float:
        pytest.fail("run_demo hỏi đồng hồ nguồn trước khi kiểm tra tham số")


@pytest.mark.parametrize("kwargs", [{"initial_skip": -1}, {"warmup_s": -0.1}, {"initial_scans": 0},
                                    {"warmup_s": float("nan")}, {"warmup_s": float("inf")}])
def test_bad_warmup_arguments_are_rejected_before_any_read(cfg, kwargs):
    # pytest.fail ném Failed (BaseException): các nhánh except của run_demo không nuốt được nó
    with pytest.raises(ValueError, match="initial_skip >= 0"):
        run_demo(NeverRead(), seconds=0.2, cfg=cfg, log=lambda _line: None, **kwargs)


@pytest.mark.parametrize("extra", [["--initial-skip", "-1"], ["--warmup", "-4.5"], ["--warmup", "nan"],
                                   ["--warmup", "inf"]])
def test_main_rejects_bad_warmup_options_before_opening_the_lidar(monkeypatch, capsys, extra):
    from autopark.fusion import demo
    from autopark.lidar.rplidar_c1 import RplidarC1Source

    opened = []
    monkeypatch.setattr(RplidarC1Source, "open", classmethod(lambda cls, port, **kwargs: opened.append(port)))
    monkeypatch.setattr(demo, "run_demo", lambda *a, **k: pytest.fail("run_demo must not run"))
    with pytest.raises(SystemExit) as info:
        demo.main(["--port", "CONG_GIA", "--seconds", "1", *extra])
    assert info.value.code == 2 and opened == []                          # lỗi argparse, không mở cổng
    err = capsys.readouterr().err
    assert "phải ≥ 0" in err and "Traceback" not in err


def test_main_rejects_bad_warmup_options_for_a_recording_before_opening_it(tmp_path, capsys):
    from autopark.fusion import demo

    for extra in (["--warmup", "-1"], ["--initial-skip", "-1"]):
        with pytest.raises(SystemExit) as info:                         # tệp không tồn tại: lỗi phải tới trước
            demo.main(["--recording", str(tmp_path / "khong_co.npz"), "--seconds", "1", *extra])
        assert info.value.code == 2
    assert "phải là số hữu hạn ≥ 0" in capsys.readouterr().err
