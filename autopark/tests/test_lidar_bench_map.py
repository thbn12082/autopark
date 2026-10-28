"""Static-bench analysis, ray-cast occupancy and DROW odometry on synthetic data (no hardware)."""
import json
import math

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.lidar.bench import analyze, render_placement, report  # noqa: E402
from autopark.lidar.drow import N_BEAMS, read_drow_csv  # noqa: E402
from autopark.lidar.drow_odom import read_drow_odom, scan_poses  # noqa: E402
from autopark.lidar.occupancy import OccupancyCounts, relative_poses  # noqa: E402
from autopark.lidar.recording import ScanRecorder, read_recording  # noqa: E402
from autopark.lidar.rplidar_protocol import wrap_angle  # noqa: E402
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec  # noqa: E402


def room_scan(t: float, n: int = 500, half: float = 2.0, box=None, noise: float = 0.0, rng=None,
              source_id: str = "c1") -> LidarScan:
    """Square room of half-size `half` around the sensor; `box` = (distance, angle_deg, half_width_deg)."""
    angles = wrap_angle(-math.pi + 2 * math.pi * np.arange(n) / n)
    ranges = half / np.maximum(np.abs(np.cos(angles)), np.abs(np.sin(angles)))
    if box is not None:
        distance, angle_deg, half_width = box
        mask = np.abs(wrap_angle(angles - math.radians(angle_deg))) <= math.radians(half_width)
        ranges[mask] = distance
    if noise and rng is not None:
        ranges = ranges + rng.normal(0.0, noise, n)
    return LidarScan(SourceStamp(source_id, t, True, "lidar"), tuple(angles.tolist()), tuple(ranges.tolist()))


def write_room_recording(path, scans: int = 20, box=(1.0, 0.0, 10.0), noise: float = 0.002):
    rng = np.random.default_rng(1)
    with ScanRecorder(path, {"source_id": "c1"}) as recorder:
        for i in range(scans):
            recorder.add(room_scan(0.1 * i, box=box, noise=noise, rng=rng))
    return recorder.path


def test_bench_analysis_passes_on_a_box_at_the_expected_place(tmp_path):
    path = write_room_recording(tmp_path / "p01_truoc_1m")
    recording = read_recording(path)
    result = analyze(recording, 1.0, 0.0)
    target = result["target"]
    assert target["scans_with_target"] == 20 and abs(target["error_mm"]) < 5
    assert abs(target["nearest_point_angle_deg"]) < 2 and abs(target["direction_error_deg"]) < 2
    assert target["spread_within_scan_mm"] < 5 and target["spread_between_scans_mm"] < 5
    assert result["summary"]["rate_hz"] == pytest.approx(10.0) and result["summary"]["beams_median"] == 500
    assert result["checks"] == {"rate_8_12_hz": True, "beams_within_5pct_of_5khz": True, "no_gap_over_3_periods": True,
                                "error_within_30mm": True, "direction_within_5deg": True}
    assert result["passed"] is True
    png = render_placement(recording, tmp_path / "p01_truoc_1m.png", 1.0, 0.0)
    assert png.exists() and cv2.imdecode(np.frombuffer(png.read_bytes(), np.uint8), cv2.IMREAD_COLOR).shape == (700, 700, 3)


def test_bench_analysis_fails_when_the_box_is_elsewhere(tmp_path):
    path = write_room_recording(tmp_path / "p04_trai_1m")
    result = analyze(read_recording(path), 1.0, 90.0)          # box is straight ahead, the wall is at 2 m on the left
    assert result["target"]["error_mm"] == pytest.approx(1000.0, abs=20)
    assert result["checks"]["error_within_30mm"] is False and result["passed"] is False
    (tmp_path / "p04_trai_1m.analysis.json").write_text(json.dumps(result), encoding="utf-8")
    text = report(tmp_path)
    assert "p04_trai_1m" in text and "KHÔNG" in text and "error_within_30mm" in text
    assert (tmp_path / "report.md").exists()


def test_analysis_without_target_only_checks_timing(tmp_path):
    path = write_room_recording(tmp_path / "p07_nen", box=None)
    result = analyze(read_recording(path))
    assert result["target"] is None and set(result["checks"]) == {"rate_8_12_hz", "beams_within_5pct_of_5khz", "no_gap_over_3_periods"}
    assert result["passed"] is True


def test_occupancy_marks_room_free_walls_occupied_outside_unknown():
    grid = GridSpec(-3.0, 3.0, -3.0, 3.0, 0.1)
    counts = OccupancyCounts(grid)
    for i in range(10):
        used = counts.add_scan(room_scan(0.1 * i, box=(1.0, 0.0, 5.0)), max_range=12.0)
        assert used == 500
    states = counts.states()
    assert states.shape == grid.shape and counts.scans == 10
    assert states[grid.index(0.0, 0.0)] == FREE and states[grid.index(0.5, 0.5)] == FREE
    assert states[grid.index(2.0, 0.5)] == OCCUPIED                     # front wall (x = 2)
    assert states[grid.index(-2.0, 0.0)] == OCCUPIED and states[grid.index(0.0, 2.0)] == OCCUPIED
    assert states[grid.index(1.0, 0.0)] == OCCUPIED                     # the box face at 1 m straight ahead
    assert states[grid.index(1.5, 0.0)] == UNKNOWN                      # behind the box: never observed
    assert states[grid.index(2.5, 0.0)] == UNKNOWN and states[grid.index(-2.6, 2.6)] == UNKNOWN
    summary = counts.summary(states)
    assert summary["cells_occupied"] > 100 and summary["cells_free"] > 1000 and 0 < summary["sharpness"] <= 1


def test_occupancy_applies_sensor_pose_and_ignores_no_returns():
    grid = GridSpec(-3.0, 3.0, -3.0, 3.0, 0.1)
    counts = OccupancyCounts(grid)
    scan = room_scan(0.0, box=(1.0, 0.0, 5.0))
    ranges = list(scan.ranges_m)
    ranges[10] = math.nan                                              # a beam without return contributes nothing
    scan = LidarScan(scan.stamp, scan.angles_rad, tuple(ranges))
    for _ in range(5):
        counts.add_scan(scan, pose=(0.0, 0.0, math.pi / 2))             # sensor turned left: its front is +y
    states = counts.states()
    assert states[grid.index(0.0, 1.0)] == OCCUPIED and states[grid.index(1.0, 0.0)] == FREE
    assert counts.beams_used == 5 * 499
    shifted = OccupancyCounts(grid)
    for _ in range(5):
        shifted.add_scan(scan, pose=(-1.0, 0.0, 0.0), max_range=1.5)    # sensor 1 m back, short max range
    s = shifted.states()
    assert s[grid.index(0.0, 0.0)] == OCCUPIED                          # the box face is now at x = 0
    assert s[grid.index(-1.0, 1.0)] == FREE and s[grid.index(-1.0, 1.8)] == UNKNOWN   # beyond max range: not seen
    assert grid.index(-3.0, -3.0) == (0, 0)


def test_relative_poses_are_expressed_in_the_first_frame():
    poses = np.array([[10.0, 5.0, math.pi / 2], [10.0, 6.0, math.pi / 2], [9.0, 6.0, math.pi]])
    rel = relative_poses(poses)
    assert rel[0] == pytest.approx([0.0, 0.0, 0.0])
    assert rel[1] == pytest.approx([1.0, 0.0, 0.0])                     # moved forward 1 m
    assert rel[2] == pytest.approx([1.0, 1.0, math.pi / 2])             # then 1 m to the left, turned left


def test_drow_odometry_pairs_with_scans_by_row(tmp_path):
    csv = tmp_path / "run.csv"
    csv.write_text("\n".join(",".join([str(s), f"{0.1 * i:.3f}", *["2.0"] * N_BEAMS]) for i, s in enumerate((100, 101, 103))) + "\n",
                   encoding="utf-8")
    odom = tmp_path / "run.odom2"
    odom.write_text("900,0.0,1.0,2.0,0.5\n900,0.1,1.1,2.0,0.5\n902,0.2,1.2,2.0,0.6\n", encoding="utf-8")   # other ids, one repeat
    poses = scan_poses(read_drow_csv(csv), read_drow_odom(odom))
    assert poses.shape == (3, 3) and poses[0] == pytest.approx([1.0, 2.0, 0.5]) and poses[2] == pytest.approx([1.2, 2.0, 0.6])
    odom.write_text("900,0.0,1.0,2.0,0.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="by row"):
        scan_poses(read_drow_csv(csv), read_drow_odom(odom))
    odom.write_text("900,0.0,1.0\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_drow_odom(odom)
    odom.write_text("901,0.0,1.0,2.0,0.5\n900,0.1,1.1,2.0,0.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-decreasing"):
        read_drow_odom(odom)
