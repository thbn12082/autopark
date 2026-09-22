"""Phase-1 groundwork: replayed camera/LiDAR sources and the freshness monitor (no hardware, no torch)."""
import json
import math

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.lidar.drow import (N_BEAMS, DrowReplaySource, drow_angles, read_drow_csv,  # noqa: E402
                                 read_drow_labels, scan_points, valid_mask)
from autopark.lidar.render import render_scan  # noqa: E402
from autopark.safety.freshness import FreshnessMonitor, SourcePolicy  # noqa: E402
from autopark.video.sources import ImageSequenceSource, VideoFileSource, natural_key, open_source  # noqa: E402


def write_drow(path, rows=5, no_return_at=(0, 1)):
    lines = []
    for i in range(rows):
        ranges = [f"{2.0 + 0.01 * j:.2f}" for j in range(N_BEAMS)]
        if i == 0:
            for j in no_return_at:
                ranges[j] = "29.96"
            ranges[2] = "29.98"                   # above the documented magic value: still no evidence of space
        lines.append(",".join([str(100 + i), f"{0.441 + 0.1 * i:.3f}", *ranges]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_drow_csv_parsing_and_no_return_handling(tmp_path):
    csv = tmp_path / "run.csv"
    write_drow(csv)
    recording = read_drow_csv(csv)
    assert recording.ranges.shape == (5, N_BEAMS) and recording.seq.tolist() == [100, 101, 102, 103, 104]
    assert np.isnan(recording.ranges[0, :3]).all() and not np.isnan(recording.ranges[0, 3:]).any()
    assert recording.t[1] - recording.t[0] == pytest.approx(0.1)


def test_drow_rejects_wrong_column_count_and_time_regression(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("1,0.0," + ",".join(["1.0"] * 10) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_drow_csv(bad)
    back = tmp_path / "back.csv"
    back.write_text("\n".join([",".join(["1", "1.0", *["1.0"] * N_BEAMS]), ",".join(["2", "0.5", *["1.0"] * N_BEAMS])]) + "\n",
                    encoding="utf-8")
    with pytest.raises(ValueError):
        read_drow_csv(back)
    dup = tmp_path / "dup.csv"
    dup.write_text("\n".join([",".join(["5", "1.0", *["1.0"] * N_BEAMS]), ",".join(["5", "1.1", *["1.0"] * N_BEAMS])]) + "\n",
                    encoding="utf-8")
    with pytest.raises(ValueError):
        read_drow_csv(dup)
    nan = tmp_path / "nan.csv"
    nan.write_text(",".join(["1", "1.0", "nan", *["1.0"] * (N_BEAMS - 1)]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_drow_csv(nan)


def test_drow_range_edges_and_all_nan_summary(tmp_path):
    csv = tmp_path / "edges.csv"
    ranges = ["1.0"] * N_BEAMS
    ranges[0], ranges[1], ranges[2] = "0.04", "29.90", "29.95"           # below RANGE_MIN, exactly at and above the cut-off
    csv.write_text(",".join(["1", "0.0", *ranges]) + "\n", encoding="utf-8")
    recording = read_drow_csv(csv)
    assert np.isnan(recording.ranges[0, :3]).all() and recording.far_returns_discarded == 2
    csv.write_text(",".join(["1", "0.0", *["29.96"] * N_BEAMS]) + "\n", encoding="utf-8")
    summary = DrowReplaySource(csv).summary()
    assert summary["range_min_m"] is None and summary["no_return_fraction"] == 1.0
    json.dumps(summary, allow_nan=False)


def test_drow_labels_distinguish_empty_from_missing(tmp_path):
    label = tmp_path / "run.wp"
    label.write_text("101,[]\n102,[[5.7397, -0.0917], [1.2, 0.3]]\n", encoding="utf-8")
    labels = read_drow_labels(label)
    assert labels[101] == [] and labels[102][0] == pytest.approx((5.7397, -0.0917))
    assert 100 not in labels
    assert read_drow_labels(label, mirror=True)[102][0] == pytest.approx((5.7397, 0.0917))
    label.write_text("101,[]\n101,[[1.0, 0.0]]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        read_drow_labels(label)
    label.write_text("101,[[1.0,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="run.wp:1"):
        read_drow_labels(label)


def test_lidar_scan_contract_rejects_negative_or_infinite_ranges():
    angles = tuple(drow_angles())
    LidarScan(SourceStamp("s", 0.0), angles, tuple([1.0] * (N_BEAMS - 1) + [math.nan]))
    with pytest.raises(ValueError):
        LidarScan(SourceStamp("s", 0.0), angles, tuple([1.0] * (N_BEAMS - 1) + [-2.0]))
    with pytest.raises(ValueError):
        LidarScan(SourceStamp("s", 0.0), angles, tuple([1.0] * (N_BEAMS - 1) + [math.inf]))
    with pytest.raises(ValueError):
        LidarScan(SourceStamp("s", 0.0), tuple([math.nan] + list(angles[1:])), tuple([1.0] * N_BEAMS))


def test_drow_replay_yields_lidar_scans_with_rebased_stamps(tmp_path):
    csv = tmp_path / "run.csv"
    write_drow(csv)
    source = DrowReplaySource(csv, t0=10.0, source_id="lidar_replay")
    scans = list(source)
    assert len(scans) == 5 and all(isinstance(s, LidarScan) for s in scans)
    assert scans[0].stamp.t == pytest.approx(10.0) and scans[4].stamp.t == pytest.approx(10.4)
    assert scans[0].stamp.source_id == "lidar_replay" and len(scans[0].ranges_m) == N_BEAMS
    assert math.isnan(scans[0].ranges_m[0]) and valid_mask(scans[0]).sum() == N_BEAMS - 3
    angles = drow_angles()
    assert angles[0] == pytest.approx(math.radians(-112.25)) and angles[-1] == pytest.approx(math.radians(112.25))
    assert drow_angles(mirror=True)[0] == pytest.approx(math.radians(112.25))
    points = scan_points(scans[1])
    assert points.shape == (N_BEAMS, 2)
    forward = points[N_BEAMS // 2]
    assert forward[0] > 0 and abs(forward[1]) < 0.02          # the middle beam looks straight ahead
    assert source.summary()["no_return_fraction"] == pytest.approx(3 / (5 * N_BEAMS))
    assert source.summary()["far_returns_discarded"] == 0 and source.summary()["fov_deg"] == pytest.approx(224.5)
    assert DrowReplaySource(csv, mirror=True).summary()["fov_deg"] == pytest.approx(224.5)
    assert source.read() is None


def test_render_scan_places_returns_and_omits_no_return_beams():
    angles = tuple(drow_angles())
    forward = N_BEAMS // 2                                       # angle +0.25 deg: straight ahead
    ranges = [math.nan] * N_BEAMS
    ranges[forward] = 2.0
    ranges[angles.index(min(angles, key=lambda a: abs(a - math.radians(90))))] = 2.0   # one beam to the left
    scan = LidarScan(SourceStamp("s", 0.0), angles, tuple(ranges))
    image = render_scan(scan, size=200, max_range=5.0)
    scale = (100 - 10) / 5.0
    point = (0, 220, 255)
    assert tuple(image[int(round(100 - 2.0 * scale)), 100]) == point       # 2 m ahead: above the centre
    assert tuple(image[100, int(round(100 - 2.0 * scale))]) == point       # 2 m left: left of the centre
    empty = render_scan(LidarScan(SourceStamp("s", 0.0), angles, tuple([math.nan] * N_BEAMS)), size=200, max_range=5.0)
    assert not (np.all(empty == point, axis=2)).any()                      # no return -> no point drawn


def test_image_sequence_source_reads_in_natural_order_with_fps_stamps(tmp_path):
    for i in (1, 2, 10):                                         # unpadded names: lexical order would be 1, 10, 2
        cv2.imwrite(str(tmp_path / f"frame_{i}.png"), np.full((20, 30, 3), i * 20, np.uint8))
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    source = ImageSequenceSource(tmp_path, fps=10.0, t0=5.0, source_id="cam_replay")
    frames = list(source)
    assert [f.meta.stamp.t for f in frames] == pytest.approx([5.0, 5.1, 5.2])
    assert [int(f.image[0, 0, 0]) for f in frames] == [20, 40, 200]
    assert frames[1].meta.width == 30 and frames[1].meta.height == 20
    assert natural_key(tmp_path / "a10b2.png") == ["a", 10, "b", 2, ".png"]
    assert frames[0].meta.stamp.source_id == "cam_replay" and frames[0].meta.encoding == "BGR8"
    assert source.read() is None
    with pytest.raises(ValueError):
        ImageSequenceSource(tmp_path / "empty_dir_that_does_not_exist_yet", fps=10.0)


def test_video_file_source_reads_frames_with_increasing_stamps(tmp_path):
    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48))
    if not writer.isOpened():
        pytest.skip("this OpenCV build cannot write MJPG AVI")
    for i in range(6):
        writer.write(np.full((48, 64, 3), 30 * i, np.uint8))
    writer.release()
    source = open_source(str(path), t0=1.0)
    assert isinstance(source, VideoFileSource)
    frames = list(source)
    source.close()
    assert len(frames) == 6 and frames[0].meta.width == 64
    stamps = [f.meta.stamp.t for f in frames]
    assert stamps[0] == pytest.approx(1.0) and all(b > a for a, b in zip(stamps, stamps[1:]))
    assert stamps[-1] == pytest.approx(1.5, abs=0.06)


class FakeCapture:
    """Mimics cv2.VideoCapture with a scripted CAP_PROP_POS_MSEC sequence."""

    def __init__(self, positions_ms, fps=25.0):
        self.positions, self.fps, self.i = positions_ms, fps, 0

    def isOpened(self):
        return True

    def get(self, prop):
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return len(self.positions)
        if prop == cv2.CAP_PROP_POS_MSEC:
            return self.positions[min(self.i, len(self.positions)) - 1]
        return 0.0

    def read(self):
        if self.i >= len(self.positions):
            return False, None
        self.i += 1
        return True, np.zeros((4, 4, 3), np.uint8)

    def release(self):
        pass


def test_video_source_falls_back_to_index_clock_when_position_is_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: FakeCapture([0.0, 33.3, 33.3, 33.3, 133.3], fps=25.0))
    source = VideoFileSource(tmp_path / "fake.mp4")
    stamps = [f.meta.stamp.t for f in source]
    assert stamps[0] == 0.0 and stamps[1] == pytest.approx(0.0333)
    assert all(b > a for a, b in zip(stamps, stamps[1:]))          # never equal, never decreasing
    assert source.clock_source == "index"
    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: FakeCapture([0.0, 40.0, 80.0, 120.0], fps=float("nan")))
    source = VideoFileSource(tmp_path / "fake2.mp4")
    assert source.fps == 30.0 and [f.meta.stamp.t for f in source] == pytest.approx([0.0, 0.04, 0.08, 0.12])


def test_freshness_monitor_reports_missing_stale_and_bad_samples():
    monitor = FreshnessMonitor({"cam": SourcePolicy(max_age_s=0.2, expected_period_s=0.05),
                                "lidar": SourcePolicy(max_age_s=0.5),
                                "optional": SourcePolicy(max_age_s=1.0, required=False)})
    assert {e.code for e in monitor.check(0.0)} == {"NO_DATA"}
    assert sum(1 for e in monitor.check(0.0)) == 2                       # optional source never blocks
    assert monitor.observe(SourceStamp("cam", 1.00)) == []
    assert monitor.observe(SourceStamp("lidar", 1.00)) == []
    assert monitor.fresh("cam", 1.15) and not monitor.fresh("cam", 1.25)
    assert [e.code for e in monitor.check(1.10)] == []
    events = monitor.check(1.30)
    assert [e.code for e in events] == ["STALE_DATA"] and events[0].action == "STOP"
    assert monitor.observe(SourceStamp("cam", 1.20)) == []
    # a sample flagged invalid, one going backwards and one from the future are all rejected
    assert monitor.observe(SourceStamp("cam", 1.40, valid=False))[0].code == "INVALID_DATA"
    assert monitor.observe(SourceStamp("cam", 0.90))[0].code == "STAMP_REGRESSION"
    assert monitor.observe(SourceStamp("cam", 5.00), now=1.50)[0].code == "CLOCK_SKEW"
    assert monitor.observe(SourceStamp("cam", 1.45), now=1.50) == []
    status = monitor.status(1.50)
    assert status["cam"]["rejected"] == 3 and status["cam"]["count"] == 3 and status["cam"]["fresh"]
    assert status["cam"]["drops"] == 7 and status["cam"]["max_gap_s"] == pytest.approx(0.25)   # gaps 0.20 s + 0.25 s
    tolerant = FreshnessMonitor({"imu": SourcePolicy(max_age_s=0.5, future_tolerance_s=0.1)})
    assert tolerant.observe(SourceStamp("imu", 1.05), now=1.0) == []
    assert tolerant.observe(SourceStamp("imu", 1.30), now=1.0)[0].code == "CLOCK_SKEW"
    # already too old when it arrives: rejected, not counted as fresh data
    late = monitor.observe(SourceStamp("cam", 1.50), now=2.00)
    assert [e.code for e in late] == ["STALE_ON_ARRIVAL"] and monitor.status(2.0)["cam"]["count"] == 3
    # device clock ahead of the session clock is reported as skew, not as "old"
    monitor.observe(SourceStamp("lidar", 3.05))
    assert [e.code for e in monitor.check(3.0) if e.code != "STALE_DATA"] == ["CLOCK_SKEW"]
    with pytest.raises(KeyError):
        monitor.observe(SourceStamp("unknown", 1.0))
    with pytest.raises(ValueError):
        SourcePolicy(max_age_s=0.0)
    with pytest.raises(ValueError):
        monitor.observe(SourceStamp("cam", 2.5), now=float("nan"))
    with pytest.raises(ValueError):
        monitor.check(-1.0)


def test_freshness_events_are_serialisable_safety_events():
    monitor = FreshnessMonitor({"cam": SourcePolicy(max_age_s=0.1)})
    event = monitor.check(2.0)[0]
    payload = json.loads(json.dumps({"code": event.code, "t": event.stamp.t, "source": event.stamp.source_id}))
    assert payload == {"code": "NO_DATA", "t": 2.0, "source": "freshness_monitor"}
