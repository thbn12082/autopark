"""Live scan window driven by hand (no thread, no hardware): scans shown, recorded, and flagged stale."""
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.lidar.live_view import LiveWindow, PacedReplay, ScanStreamEnded  # noqa: E402
from autopark.lidar.recording import ScanRecorder, read_recording  # noqa: E402
from autopark.lidar.rplidar_c1 import ScanReadError  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeSource:
    source_id = "c1"

    def __init__(self):
        self.t = 0.0
        self.closed = False

    def now(self) -> float:
        return self.t

    def stats(self) -> dict:
        return {"fake": True}

    def close(self) -> None:
        self.closed = True


def scan(t: float, n: int = 12) -> LidarScan:
    angles = tuple(-math.pi + 2 * math.pi * i / n for i in range(n))
    return LidarScan(SourceStamp("c1", t, True, "lidar"), angles, tuple([1.0 + 0.1 * i for i in range(n)]))


def test_live_window_shows_records_and_flags_stale(qapp, tmp_path):
    source = FakeSource()
    recorder = ScanRecorder(tmp_path / "live", {"source_id": "c1"})
    window = LiveWindow(source, max_age=0.3, expected_period=0.1, recorder=recorder, start_thread=False)
    window.timer.stop()
    window.tick()
    assert "NO_DATA" in window.status.text() and window.view.scan is None
    source.t = 0.10
    window.queue.put((scan(0.10), np.full(12, 9, np.uint8), 0.01))
    window.tick()
    assert window.view.scan is not None and not window.view.stale and window.status.text().endswith("OK")
    source.t = 0.25
    window.queue.put((scan(0.20), None, None))
    window.queue.put(ScanReadError("no complete revolution within 1.0 s"))
    window.tick()
    assert window.monitor.status(0.25)["c1"]["count"] == 2 and "ScanReadError" in window.status.text()
    source.t = 0.70                                                       # 0.5 s without scans: stale
    window.tick()
    assert window.view.stale and "STALE_DATA" in window.status.text()
    window.queue.put((scan(0.10), None, None))                             # an old scan arriving late is rejected
    window.tick()
    assert window.monitor.status(0.70)["c1"]["rejected"] == 1 and window.monitor.status(0.70)["c1"]["count"] == 2
    window.close()
    assert source.closed and recorder.closed
    recording = read_recording(recorder.path)
    assert len(recording) == 2 and recording.quality[:12].tolist() == [9] * 12 and recording.meta["driver_stats"] == {"fake": True}


def test_paced_replay_uses_recording_time_and_ends(tmp_path):
    with ScanRecorder(tmp_path / "r", {"source_id": "c1"}) as recorder:
        recorder.add(scan(0.0))
        recorder.add(scan(0.02))
    clock = [0.0]
    replay = PacedReplay(recorder.path, speed=4.0, clock=lambda: clock[0])
    clock[0] = 0.1                                                        # 0.1 s wall clock = 0.4 s replay time
    assert replay.read().stamp.t == 0.0 and replay.read().stamp.t == pytest.approx(0.02)
    assert replay.now() == pytest.approx(0.4)
    with pytest.raises(ScanStreamEnded):
        replay.read()
    with pytest.raises(ValueError):
        PacedReplay(recorder.path, speed=0.0)


class ScriptedSource:
    """Nguồn đọc được (cho ScanReader): mỗi vòng có dấu `now() − age_s` theo đồng hồ của nguồn, rồi hết bản ghi."""

    source_id = "c1"

    def __init__(self, count: int, age_s: float, speed: float = 1.0):
        self.count, self.age_s, self.speed = count, age_s, speed
        self.t = 10.0
        self.last_quality = None
        self.last_revolution = None

    def now(self) -> float:
        return self.t

    def read(self):
        if self.count == 0:
            raise ScanStreamEnded("hết bản ghi")
        self.count -= 1
        self.t += 0.1
        return scan(self.t - self.age_s)


def test_reader_feeds_consumers_with_perf_time_and_survives_consumer_errors():
    """T2 (02/10/2026): mỗi vòng tới mọi người tiêu thụ với t_perf = perf_counter lúc đọc − tuổi theo đồng hồ nguồn (chia
    cho `speed` khi phát lại nhanh); người tiêu thụ ném lỗi thành ScanConsumerError trên hàng đợi, luồng đọc vẫn chạy."""
    import queue as queue_module
    import time

    from autopark.lidar.live_view import ScanConsumerError, ScanReader

    class Recorder:
        def __init__(self):
            self.calls = []

        def on_scan(self, scan_, quality, t_first_perf, t_perf):
            self.calls.append((scan_.stamp.t, quality, t_first_perf, t_perf, time.perf_counter()))

    class Broken:
        def on_scan(self, *args):
            raise RuntimeError("hỏng")

    for speed in (1.0, 2.0):
        good = Recorder()
        out = queue_module.Queue()
        reader = ScanReader(ScriptedSource(3, age_s=0.05, speed=speed), out, [Broken(), good])
        reader.start()
        reader.join(timeout=5.0)
        assert not reader.is_alive()
        items = [out.get_nowait() for _ in range(out.qsize())]
        scans = [item for item in items if isinstance(item, tuple)]
        errors = [item for item in items if isinstance(item, ScanConsumerError)]
        assert len(scans) == 3 and len(errors) == 3 and isinstance(items[-1], ScanStreamEnded)
        assert all(len(item) == 4 for item in scans) and "Broken.on_scan" in str(errors[0])
        assert len(good.calls) == 3
        for (_stamp, quality, t_first_perf, t_perf, called_at), item in zip(good.calls, scans):
            assert quality is None and t_first_perf is None and item[3] == t_perf
            assert 0.05 / speed - 0.01 <= called_at - t_perf <= 0.05 / speed + 0.5


def test_live_window_accepts_four_tuples(qapp):
    source = FakeSource()
    window = LiveWindow(source, start_thread=False)
    window.timer.stop()
    source.t = 0.1
    window.queue.put((scan(0.1), None, None, 123.0))
    window.tick()
    assert window.view.scan is not None and window.monitor.status(0.1)["c1"]["count"] == 1
    window.close()
