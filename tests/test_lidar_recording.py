"""Vendor-independent scan recording: write, read back, replay and summarise."""
import math

import pytest

np = pytest.importorskip("numpy")

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.lidar.recording import (RecordingReplaySource, ScanRecorder, default_meta, read_lidar_any,  # noqa: E402
                                      read_recording, summarize)


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


def test_a_recording_folder_replays_every_lidar_part_in_order(tmp_path):
    """T3 (2026-10-02): a session recording folder (rig.recording, several lidar/part_*.npz) replays as ONE recording in
    the LiDAR tools (`read_lidar_any`, `RecordingReplaySource`, `PacedReplay`); a single .npz reads as before."""
    pytest.importorskip("cv2")
    pytest.importorskip("PySide6")
    from autopark.lidar.live_view import PacedReplay, ScanStreamEnded
    from autopark.rig.recording import RigRecorder
    from autopark.video.multicam import RIG_CLOCK

    folder = tmp_path / "phiên"
    t0 = RIG_CLOCK()
    rec = RigRecorder(folder, ports=[], lidar=True, clock=lambda: t0, lidar_scans_per_part=3).start()
    stamps = [t0 + 0.05 * k for k in range(8)]
    for k, t in enumerate(stamps):
        rec.add_scan(make_scan(t, 10 + k, base=1.0 + k), t, t - 0.04, quality=[k + 1] * (10 + k))
    assert rec.stop(wait=True, timeout=5.0)["state"] == "xong"
    parts = sorted((folder / "lidar").glob("part_*.npz"))
    assert len(parts) == 3
    recording = read_lidar_any(folder)
    assert len(recording) == 8 and recording.n_beams.tolist() == list(range(10, 18))
    assert recording.t.tolist() == pytest.approx(stamps) and recording.t_first.tolist() == pytest.approx(
        [t - 0.04 for t in stamps])
    replay = RecordingReplaySource(folder)
    assert len(replay) == 8 and [len(s.ranges_m) for s in replay] == list(range(10, 18))
    assert len(RecordingReplaySource(recording)) == 8                     # an already loaded Recording
    paced = PacedReplay(folder, speed=8, clock=RIG_CLOCK)
    got = []
    with pytest.raises(ScanStreamEnded):
        while len(got) < 20:
            got.append(paced.read().stamp.t)
    assert got == pytest.approx([t - stamps[0] for t in stamps])          # in order, every part, then the end
    one = read_lidar_any(parts[0])                                         # a single part: as read_recording
    assert len(one) == 3 and one.path == parts[0] and len(read_lidar_any(parts[0].with_suffix(""))) == 3
    with pytest.raises(ValueError):
        read_lidar_any(tmp_path)                                           # no meta.json: not a session recording
    empty = RigRecorder(tmp_path / "rỗng", ports=[1], clock=lambda: 1.0).start()
    empty.stop(wait=True, timeout=5.0)
    with pytest.raises(ValueError, match="không có vòng LiDAR"):
        read_lidar_any(tmp_path / "rỗng")
