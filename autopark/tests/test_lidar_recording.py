"""Vendor-independent scan recording: write, read back, replay and summarise."""
import math

import pytest

np = pytest.importorskip("numpy")

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.lidar.recording import (RecordingReplaySource, ScanRecorder, default_meta, read_recording,  # noqa: E402
                                      summarize)


def make_scan(t: float, n: int, base: float = 1.0, source_id: str = "c1") -> LidarScan:
    angles = tuple(-math.pi + 2 * math.pi * i / n for i in range(n))
    ranges = tuple(math.nan if i % 7 == 0 else base + 0.001 * i for i in range(n))
    return LidarScan(SourceStamp(source_id, t, True, "lidar"), angles, ranges)


def test_recorder_round_trip_and_replay(tmp_path):
    path = tmp_path / "session" / "p01"
    meta = default_meta("c1", port="COM4", mirror=False)
    scans = [make_scan(0.5, 10), make_scan(0.6, 12, base=2.0), make_scan(0.75, 9, base=3.0)]
    with ScanRecorder(path, meta) as recorder:
        for i, scan in enumerate(scans):
            recorder.add(scan, quality=[i + 1] * len(scan.angles_rad), t_first=scan.stamp.t - 0.09)
        assert len(recorder) == 3
    assert recorder.path.exists() and recorder.path.with_suffix(".json").exists()

    recording = read_recording(recorder.path)
    assert len(recording) == 3 and recording.n_beams.tolist() == [10, 12, 9]
    assert recording.meta["port"] == "COM4" and recording.meta["scans"] == 3 and recording.meta["source_id"] == "c1"
    angles, ranges, quality = recording.beams(1)
    assert len(angles) == 12 and quality.tolist() == [2] * 12
    assert math.isnan(ranges[0]) and ranges[1] == pytest.approx(2.001, abs=1e-5)
    assert recording.t_first[0] == pytest.approx(0.41)

    replay = RecordingReplaySource(recorder.path, t0=10.0)
    replayed = list(replay)
    assert [s.stamp.t for s in replayed] == pytest.approx([10.0, 10.1, 10.25])   # rebased to the first scan
    assert replayed[0].stamp.source_id == "c1" and len(replayed[2].ranges_m) == 9
    assert math.isnan(replayed[0].ranges_m[0]) and replayed[0].ranges_m[1] == pytest.approx(1.001, abs=1e-5)
    assert replay.read() is None

    summary = summarize(recording)
    assert summary["scans"] == 3 and summary["duration_s"] == pytest.approx(0.25)
    assert summary["rate_hz"] == pytest.approx(8.0) and summary["max_gap_s"] == pytest.approx(0.15)
    assert summary["beams_min"] == 9 and summary["beams_max"] == 12
    assert summary["no_return_fraction"] == pytest.approx(6 / 31)          # beams 0 and 7 of every scan are NaN
    assert recording.meta["summary"]["rate_hz"] == pytest.approx(8.0)


def test_recorder_validates_order_and_quality_length(tmp_path):
    recorder = ScanRecorder(tmp_path / "bad", {})
    recorder.add(make_scan(1.0, 5))
    with pytest.raises(ValueError):
        recorder.add(make_scan(0.5, 5))
    with pytest.raises(ValueError):
        recorder.add(make_scan(1.5, 5), quality=[1, 2])
    recorder.close()
    with pytest.raises(RuntimeError):
        recorder.add(make_scan(2.0, 5))
    assert read_recording(recorder.path).meta["summary"]["rate_hz"] is None   # a single scan has no rate
