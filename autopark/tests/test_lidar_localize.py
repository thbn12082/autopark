"""Định vị LiDAR trên bản đồ lưới tĩnh (lidar/localize.py) bằng phòng tổng hợp, không cần thiết bị.

Bản đồ được dựng đúng như dữ liệu thật: vòng quét mô phỏng (tia cắt đoạn thẳng) -> `OccupancyCounts` ->
`costmap.json`. Vòng quét để định vị có nhiễu, tia mất phản hồi và vài vật di động không có trong bản đồ.
"""
import csv
import json
import math

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.lidar.localize import (AMBIGUOUS, FAILED, OK, ORIGIN_COLOR, POSE_COLORS, LocalizationMap,  # noqa: E402
                                     LocalizeConfig, decimate, load_map, localize, localize_scan, main,
                                     overlay_caption, render_overlay, run, scan_points, summarize_track, wrap)
from autopark.lidar.occupancy import OccupancyCounts, write_outputs  # noqa: E402
from autopark.lidar.recording import ScanRecorder  # noqa: E402
from autopark.perception.costmap import COLORS, FREE, OCCUPIED, UNKNOWN, GridSpec, to_costmap  # noqa: E402

# Phòng không đối xứng; tường cố ý không nằm trên biên ô 5 cm.
ROOM = [(-3.03, -2.17), (3.12, -2.17), (3.12, 0.62), (2.41, 0.62), (2.41, 2.23), (-1.37, 2.23), (-1.37, 1.51),
        (-3.03, 1.51)]
GRID = GridSpec(-3.5, 3.5, -2.5, 2.5, 0.05)
MAP_POSES = [(0.0, 0.0, 0.0), (1.4, -0.9, 0.3), (-1.6, 0.4, -0.5), (1.2, 1.2, 1.0)]


def polygon(points, closed=True):
    pts = list(points) + ([points[0]] if closed else [])
    return [(a[0], a[1], b[0], b[1]) for a, b in zip(pts[:-1], pts[1:])]


def box(cx, cy, w, h, yaw_deg=0.0):
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return polygon([(cx + c * x - s * y, cy + s * x + c * y) for x, y in corners])


def disc(cx, cy, r, sides=10):
    return polygon([(cx + r * math.cos(2 * math.pi * k / sides), cy + r * math.sin(2 * math.pi * k / sides))
                    for k in range(sides)])


STATIC = np.array(polygon(ROOM) + box(1.17, -1.08, 0.3, 0.3) + box(-1.93, -0.62, 0.52, 0.31, 25.0)
                  + box(0.43, 1.37, 0.8, 0.4, -10.0), np.float64)


def raycast(pose, segments, n=500, max_range=12.0, noise=0.0, dropout=0.0, rng=None):
    """Góc theo quy ước dự án (0 = trước, dương ngược chiều kim đồng hồ); NaN = không phản hồi."""
    angles = -math.pi + 2 * math.pi * np.arange(n) / n
    x, y, th = pose
    dx, dy = np.cos(angles + th)[:, None], np.sin(angles + th)[:, None]
    ax, ay, bx, by = (segments[:, k][None, :] for k in range(4))
    ex, ey = bx - ax, by - ay
    wx, wy = ax - x, ay - y
    denom = dx * ey - dy * ex
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (wx * ey - wy * ex) / denom
        u = (wx * dy - wy * dx) / denom
    hit = (np.abs(denom) > 1e-12) & (t > 1e-6) & (u >= 0) & (u <= 1)
    ranges = np.where(hit, t, np.inf).min(axis=1)
    if rng is not None and noise:
        ranges = ranges + rng.normal(0.0, noise, n)
    ranges[~np.isfinite(ranges) | (ranges > max_range)] = np.nan
    if rng is not None and dropout:
        ranges[rng.random(n) < dropout] = np.nan
    return angles, ranges


def build_map(segments=STATIC, poses=MAP_POSES, grid=GRID, scans=8, seed=0):
    rng = np.random.default_rng(seed)
    counts = OccupancyCounts(grid)
    for pose in poses:
        for i in range(scans):
            angles, ranges = raycast(pose, segments, noise=0.005, rng=rng)
            scan = LidarScan(SourceStamp("sim", 0.1 * i, True, "lidar"), tuple(angles.tolist()),
                             tuple(float(r) for r in ranges))
            counts.add_scan(scan, pose, max_range=12.0)
    return counts, counts.states()


@pytest.fixture(scope="module")
def room_map():
    counts, states = build_map()
    return LocalizationMap(states, GRID)


def movers(rng, count=3):
    """Vật di động (người, ghế) không có trong bản đồ, đặt ngẫu nhiên trong phòng."""
    segs = []
    for _ in range(count):
        segs += disc(rng.uniform(-2.5, 2.0), rng.uniform(-1.8, 1.2), 0.15)
    return np.array(segs, np.float64)


def live_scan(pose, rng, n_movers=3, noise=0.01, dropout=0.1):
    segments = np.vstack([STATIC, movers(rng, n_movers)]) if n_movers else STATIC
    return raycast(pose, segments, noise=noise, dropout=dropout, rng=rng)


def pose_error(result, truth):
    return math.hypot(result.x - truth[0], result.y - truth[1]), \
        abs(math.degrees((result.theta - truth[2] + math.pi) % (2 * math.pi) - math.pi))


TRUE_POSES = [(0.21, -0.14, math.radians(9.0)), (-0.33, 0.27, math.radians(-21.0)), (0.12, 0.31, math.radians(26.0)),
              (0.36, -0.38, math.radians(-4.0)), (-0.07, 0.02, math.radians(0.4)), (1.43, -0.52, math.radians(95.0))]


def test_recovers_known_poses_inside_window_with_noise_dropouts_and_movers(room_map):
    rng = np.random.default_rng(7)
    times = []
    for truth in TRUE_POSES:
        initial = (0.0, 0.0, 0.0) if abs(truth[2]) < math.radians(30) else (1.2, -0.3, math.radians(80.0))
        angles, ranges = live_scan(truth, rng)
        assert np.isnan(ranges).mean() > 0.05                      # tia mất phản hồi có thật trong phép thử
        result = localize(room_map, angles, ranges, initial)
        error_m, error_deg = pose_error(result, truth)
        assert result.status == OK, (truth, result.reasons)
        assert error_m < 0.02 and error_deg < 1.0, (truth, error_m, error_deg)
        assert result.matched >= 150 and result.matched_fraction > 0.8 and result.conflict_fraction < 0.2   # vật di động
        assert result.second_ratio is None or result.second_ratio < 0.9
        assert result.std_x_m < 0.01 and result.std_theta_deg < 0.5
        times.append(result.time_ms)
    assert np.median(times) < 300.0, times                        # ngân sách rộng; số đo thật ở tài liệu


def test_mirrored_scan_is_not_accepted(room_map):
    """Đảo dấu góc (lỗi quy ước trái/phải) phải làm hỏng khớp, không được ra OK."""
    rng = np.random.default_rng(3)
    angles, ranges = live_scan(TRUE_POSES[0], rng, n_movers=0)
    result = localize(room_map, -angles, ranges, (0.0, 0.0, 0.0))
    assert result.status != OK


def test_true_pose_outside_the_window_is_not_reported_ok(room_map):
    rng = np.random.default_rng(11)
    truth = (1.25, -0.85, math.radians(5.0))
    angles, ranges = live_scan(truth, rng)
    small = localize(room_map, angles, ranges, (0.0, 0.0, 0.0), window=(0.3, 0.3, math.radians(20)))
    assert small.status != OK and ("window_edge" in small.reasons or "low_match_fraction" in small.reasons)
    turned = (0.1, 0.1, math.radians(70.0))
    angles, ranges = live_scan(turned, rng)
    rotated = localize(room_map, angles, ranges, (0.0, 0.0, 0.0), window=(0.5, 0.5, math.radians(20)))
    assert rotated.status != OK
    # cùng vòng quét, cửa sổ đủ rộng thì tìm ra
    wide = localize(room_map, angles, ranges, (0.0, 0.0, 0.0), window=(0.5, 0.5, math.radians(90)))
    assert wide.status == OK and pose_error(wide, turned)[0] < 0.02
    # ngay ngoài mép cửa sổ 10 cm: phần lớn tia vẫn "khớp" (sai 10 cm ≈ match_dist) nên chỉ mép cửa sổ tố cáo
    near = (0.45, 0.0, 0.0)
    angles, ranges = live_scan(near, rng, n_movers=0)
    edge = localize(room_map, angles, ranges, (0.0, 0.0, 0.0), window=(0.35, 0.35, math.radians(20)))
    assert edge.status == FAILED and "window_edge" in edge.reasons and edge.matched_fraction > 0.6


def test_symmetric_corridor_is_flagged_ambiguous():
    grid = GridSpec(-4.0, 4.0, -1.5, 1.5, 0.05)
    walls = np.array([(-30.0, 0.62, 30.0, 0.62), (-30.0, -0.63, 30.0, -0.63)], np.float64)
    counts, states = build_map(walls, [(0.0, 0.0, 0.0), (1.5, 0.1, 0.0), (-1.5, -0.1, 0.0)], grid)
    cfg = LocalizeConfig(max_range_m=3.0)
    lmap = LocalizationMap(states, grid, cfg)
    rng = np.random.default_rng(5)
    truth = (0.2, 0.05, math.radians(4.0))
    angles, ranges = raycast(truth, walls, noise=0.01, dropout=0.1, rng=rng)
    result = localize(lmap, angles, ranges, (0.0, 0.0, 0.0))
    assert result.status in (AMBIGUOUS, FAILED) and "second_peak" in result.reasons
    assert result.second_ratio is not None and result.second_ratio > 0.95
    # Hessian thấy hướng dọc hành lang yếu hơn hẳn, dù các lỗ trên tường bản đồ vẫn ràng buộc nó một chút
    assert result.std_x_m > 5 * result.std_y_m
    # ngang hành lang và hướng thì vẫn đúng
    assert abs(result.y - truth[1]) < 0.03 and abs(math.degrees(result.theta) - 4.0) < 1.0

    # Hành lang lý tưởng (tường liền, thẳng theo lưới): Hessian suy biến thật -> "degenerate"
    ideal = np.full(grid.shape, -1, np.int8)
    ideal[grid.index(0.0, -0.6)[0]:grid.index(0.0, 0.6)[0] + 1, :] = FREE
    ideal[grid.index(0.0, 0.62)[0], :] = OCCUPIED
    ideal[grid.index(0.0, -0.63)[0], :] = OCCUPIED
    perfect = localize(LocalizationMap(ideal, grid, cfg), angles, ranges, (0.0, 0.0, 0.0))
    assert perfect.status != OK and "degenerate" in perfect.reasons and "second_peak" in perfect.reasons
    assert not math.isfinite(perfect.std_x_m) and json.dumps(perfect.to_dict(), allow_nan=False)


def test_scene_changed_near_the_sensor_fails_on_conflicts(room_map):
    """Một vật lớn mới xuất hiện trước cảm biến: tư thế vẫn gần đúng nhưng cảnh không còn khớp bản đồ -> FAILED."""
    rng = np.random.default_rng(43)
    truth = (0.1, 0.05, math.radians(3.0))
    segments = np.vstack([STATIC, np.array(box(0.9, 0.0, 0.6, 1.2), np.float64)])
    angles, ranges = raycast(truth, segments, noise=0.01, dropout=0.1, rng=rng)
    result = localize(room_map, angles, ranges, (0.0, 0.0, 0.0))
    assert result.status == FAILED and result.reasons == ("conflicts_with_map",)
    assert result.matched_fraction > 0.6 and result.search["conflicts_short"] > 100
    assert pose_error(result, truth)[0] < 0.02                        # chẩn đoán: tư thế không sai, chỉ là không tin


def test_scan_from_another_room_fails_even_with_global_search(room_map):
    rng = np.random.default_rng(13)
    hall = np.array(disc(0.0, 0.0, 2.3, sides=40) + box(0.9, 0.2, 0.2, 1.2), np.float64)
    angles, ranges = raycast((0.0, 0.0, 0.0), hall, noise=0.01, dropout=0.1, rng=rng)
    local = localize(room_map, angles, ranges, (0.0, 0.0, 0.0))
    assert local.status == FAILED
    cfg = LocalizeConfig(levels=5)
    global_map = LocalizationMap(room_map.states, GRID, cfg)
    result = localize(global_map, angles, ranges, global_search=True)
    assert result.status != OK, result.to_dict()


def test_global_search_finds_a_pose_far_from_the_initial_guess(room_map):
    rng = np.random.default_rng(17)
    truth = (-1.62, -1.21, math.radians(-140.0))
    angles, ranges = live_scan(truth, rng, n_movers=2)
    lmap = LocalizationMap(room_map.states, GRID, LocalizeConfig(levels=5))
    result = localize(lmap, angles, ranges, global_search=True)
    error_m, error_deg = pose_error(result, truth)
    assert result.status == OK and error_m < 0.02 and error_deg < 1.0, (result.reasons, error_m, error_deg)


def test_branch_and_bound_equals_exhaustive_search(room_map):
    rng = np.random.default_rng(19)
    angles, ranges = live_scan((0.17, -0.22, math.radians(12.0)), rng)
    points = decimate(scan_points(angles, ranges, room_map.config), room_map.res)
    window = (0.4, 0.3, math.radians(15.0))
    fast = room_map.search(points, (0.0, 0.0, 0.0), window)
    slow = room_map.brute_force(points, (0.0, 0.0, 0.0), window)
    for key in ("x", "y", "theta", "score", "second", "leaves", "at_edge"):
        assert fast[key] == pytest.approx(slow[key]), key
    assert fast["evaluated"] < slow["evaluated"] / 5                # cắt nhánh thật sự bỏ bớt việc


def test_pyramid_levels_are_upper_bounds(room_map):
    base = room_map.pyramid[0]
    for level, table in enumerate(room_map.pyramid):
        b = 2 ** level
        r, c = 37, 51
        assert table[r, c] == pytest.approx(base[r:r + b, c:c + b].max())
    p = room_map.pad
    assert np.all(room_map.pyramid[-1][:p // 2, :] >= 0)          # đệm ngoài bản đồ = 0, không âm


def test_likelihood_field_rewards_walls_and_penalises_free_space(room_map):
    field = room_map.likelihood
    wall = GRID.index(3.12, -1.0)
    inside = GRID.index(0.0, -0.5)
    assert room_map.states[wall] == OCCUPIED and field[wall] == pytest.approx(1.0)
    assert room_map.states[inside] == FREE and field[inside] < 0
    unknown = np.argwhere(room_map.states == UNKNOWN)[0]
    assert field[tuple(unknown)] >= 0


def test_beams_through_mapped_walls_and_into_free_space_are_conflicts():
    grid = GridSpec(-1.0, 3.0, -1.0, 1.0, 0.05)
    states = np.full(grid.shape, FREE, np.int8)
    wall = grid.index(2.0, 0.0)[1]
    states[:, wall] = OCCUPIED                                         # một bức tường ở x = 2,0..2,05
    states[:, wall + 1:] = UNKNOWN                                     # sau tường bản đồ không nhìn thấy
    lmap = LocalizationMap(states, grid)
    points = np.array([[2.02, 0.0],     # chạm tường: khớp
                       [2.6, 0.3],      # đi xuyên tường rồi mới chạm: mâu thuẫn "xuyên"
                       [1.0, -0.5],     # chạm giữa khoảng trống: mâu thuẫn "ngắn" (vật mới / sai tư thế)
                       [2.1, 0.9]])     # chạm ngay sau tường, trong biên 15 cm: không tính xuyên
    through = lmap.through_walls(points, (0.0, 0.0, 0.0))
    assert through.tolist() == [False, True, False, False]
    ev = lmap.evaluate(points, (0.0, 0.0, 0.0))
    assert ev["matched_mask"].tolist() == [True, False, False, True]
    assert ev["conflict_mask"].tolist() == [False, True, True, False]
    assert (ev["matched"], ev["short"], ev["through"]) == (2, 1, 1)
    # cảm biến ở ngoài bản đồ: mọi điểm rơi ra ngoài lưới -> không khớp, cũng không mâu thuẫn
    outside = lmap.evaluate(points, (-5.0, 0.0, 0.0))
    assert outside["matched"] == outside["conflicts"] == outside["in_grid"] == 0


def test_matched_fraction_counts_beams_that_leave_the_map(room_map):
    """Tia chạm ra ngoài lưới bản đồ vẫn nằm ở mẫu số: không thể đẩy điểm ra ngoài bản đồ để được tỉ lệ đẹp."""
    small = GridSpec(-1.5, 1.5, -1.5, 1.5, 0.05)
    counts, states = build_map(grid=small, scans=3)
    lmap = LocalizationMap(states, small)
    rng = np.random.default_rng(37)
    truth = (0.1, 0.05, math.radians(3.0))
    angles, ranges = live_scan(truth, rng, n_movers=0)
    result = localize(lmap, angles, ranges, (0.0, 0.0, 0.0))
    assert result.in_grid < 0.7 * result.valid_beams
    assert result.matched_fraction == pytest.approx(result.matched / result.valid_beams)
    # tư thế có thể gần đúng và không có mâu thuẫn, nhưng bản đồ giải thích quá ít tia -> không nhận
    assert result.status == FAILED and result.reasons == ("low_match_fraction",) and result.conflict_fraction < 0.1
    full = localize(room_map, angles, ranges, (0.0, 0.0, 0.0))
    assert full.status == OK and full.matched_fraction > result.matched_fraction


def test_map_loading_round_trip_and_refusals(tmp_path):
    counts, states = build_map(scans=2)
    write_outputs(counts, states, tmp_path / "map", source="sim", source_id="sim", t=1.0)
    lmap = load_map(tmp_path / "map")
    assert lmap.grid == GRID and np.array_equal(lmap.states, states)
    assert load_map(tmp_path / "map" / "costmap.json").grid == GRID
    data = json.loads((tmp_path / "map" / "costmap.json").read_text(encoding="utf-8"))
    data["costmap"]["stamp"]["valid"] = False
    (tmp_path / "bad.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="không hợp lệ"):
        load_map(tmp_path / "bad.json")
    data["costmap"]["stamp"]["valid"] = True
    data["costmap"]["origin"]["yaw_deg"] = 10.0
    (tmp_path / "rot.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="thẳng trục"):
        load_map(tmp_path / "rot.json")
    with pytest.raises(ValueError, match="OCCUPIED"):
        LocalizationMap(np.full(GRID.shape, FREE, np.int8), GRID)
    costmap = to_costmap(states, GRID, SourceStamp("sim", 0.0, True, "vehicle"))
    assert LocalizationMap.from_costmap(costmap).grid == GRID


def test_too_few_beams_fails_without_searching(room_map):
    angles = np.linspace(-math.pi, math.pi, 500, endpoint=False)
    ranges = np.full(500, np.nan)
    ranges[:20] = 1.0
    result = localize(room_map, angles, ranges, (0.3, 0.2, 0.1))
    assert result.status == FAILED and result.reasons == ("too_few_beams",)
    assert (result.x, result.y) == (0.3, 0.2)


def test_localize_scan_accepts_the_domain_contract(room_map):
    rng = np.random.default_rng(23)
    truth = (0.05, -0.1, math.radians(3.0))
    angles, ranges = live_scan(truth, rng, n_movers=0)
    scan = LidarScan(SourceStamp("c1", 0.0, True, "lidar"), tuple(angles.tolist()),
                     tuple(float(r) if math.isfinite(r) else math.nan for r in ranges))
    result = localize_scan(room_map, scan)
    assert result.ok and pose_error(result, truth)[0] < 0.02
    assert result.pose.x == result.x and json.dumps(result.to_dict(), allow_nan=False)


def test_cli_localizes_every_revolution_and_writes_track_summary_overlay(tmp_path):
    counts, states = build_map(scans=3)
    write_outputs(counts, states, tmp_path / "map_sim", source="sim", source_id="sim", t=1.0)
    truth = (0.11, -0.07, math.radians(6.0))
    rng = np.random.default_rng(29)
    with ScanRecorder(tmp_path / "phiên_thử", {"source_id": "sim"}) as recorder:     # tên có dấu: kiểm ghi PNG
        for i in range(6):
            angles, ranges = live_scan(truth, rng, n_movers=1)
            recorder.add(LidarScan(SourceStamp("sim", 0.1 * i, True, "lidar"), tuple(angles.tolist()),
                                   tuple(float(r) if math.isfinite(r) else math.nan for r in ranges)))
    out = tmp_path / "kết_quả"
    assert main(["--map", str(tmp_path / "map_sim"), "--recording", str(recorder.path), "--out", str(out),
                 "--skip-seconds", "0.05"]) == 0
    with (out / "track.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [int(r["index"]) for r in rows] == [1, 2, 3, 4, 5]
    for row in rows:
        assert row["status"] == OK
        assert math.hypot(float(row["x_m"]) - truth[0], float(row["y_m"]) - truth[1]) < 0.02
        assert abs(float(row["theta_deg"]) - 6.0) < 1.0
    report = json.loads((out / "localize.json").read_text(encoding="utf-8"))
    assert report["summary"]["scans"] == 5 and report["summary"]["ok"] == 5 and report["mode"] == "independent"
    assert report["summary"]["ok_pose_median"]["x_m"] == pytest.approx(truth[0], abs=0.02)
    assert len(report["track"]) == 5 and report["config"]["min_range_m"] == 0.25
    image = cv2.imdecode(np.fromfile(out / "overlay.png", np.uint8), cv2.IMREAD_COLOR)
    assert image is not None and image.shape[0] > 100


def test_track_mode_follows_a_moving_sensor(tmp_path):
    counts, states = build_map(scans=3)
    write_outputs(counts, states, tmp_path / "map_sim", source="sim", source_id="sim", t=1.0)
    rng = np.random.default_rng(31)
    path = [(0.08 * k, -0.05 * k, math.radians(4.0 * k)) for k in range(12)]   # đi 1,05 m, quay 44°
    with ScanRecorder(tmp_path / "di_chuyen", {"source_id": "sim"}) as recorder:
        for i, pose in enumerate(path):
            angles, ranges = live_scan(pose, rng, n_movers=1)
            recorder.add(LidarScan(SourceStamp("sim", 0.1 * i, True, "lidar"), tuple(angles.tolist()),
                                   tuple(float(r) if math.isfinite(r) else math.nan for r in ranges)))
    window = ["--window", "0.2", "0.2", "10"]
    tracked = main(["--map", str(tmp_path / "map_sim"), "--recording", str(recorder.path), "--out",
                    str(tmp_path / "track"), "--track", *window])
    fixed = main(["--map", str(tmp_path / "map_sim"), "--recording", str(recorder.path), "--out",
                  str(tmp_path / "fixed"), *window])
    assert tracked == fixed == 0
    track = json.loads((tmp_path / "track" / "localize.json").read_text(encoding="utf-8"))
    assert track["summary"]["ok"] == len(path)
    for row, truth in zip(track["track"], path):
        assert math.hypot(row["x"] - truth[0], row["y"] - truth[1]) < 0.02
        assert abs(row["theta_deg"] - math.degrees(truth[2])) < 1.0
    fixed_report = json.loads((tmp_path / "fixed" / "localize.json").read_text(encoding="utf-8"))
    assert fixed_report["summary"]["ok"] < len(path)                 # cửa sổ cố định quanh gốc không theo kịp


# --- Thêm 24/09/2026 sau đợt rà soát: hướng quanh ±180°, tường chéo, cửa sổ sai, không chồng bản đồ, màu overlay,
# --- và các kiểm/tuỳ chọn CLI trước đó không có test nào hỏng khi bị gỡ.

def _record(path, scans):
    """Ghi các cặp (góc, khoảng cách) thành một bản ghi .npz như lidar/recording.py; NaN = không phản hồi."""
    with ScanRecorder(path, {"source_id": "sim"}) as recorder:
        for i, (angles, ranges) in enumerate(scans):
            recorder.add(LidarScan(SourceStamp("sim", 0.1 * i, True, "lidar"), tuple(angles.tolist()),
                                   tuple(float(r) if math.isfinite(r) else math.nan for r in ranges)))
    return recorder.path


def _summary_rows(thetas_deg, status=OK):
    return [{"index": i, "status": status, "reasons": [], "x": 0.1, "y": -0.2, "theta_deg": th, "fit": 0.8,
             "matched_fraction": 0.9, "time_ms": 10.0} for i, th in enumerate(thetas_deg)]


def test_summary_heading_statistics_are_circular():
    """Hướng thật ≈ 180° cho theta hai dấu: trung vị/độ lệch/khoảng phải tính trên vòng tròn, không tuyến tính."""
    seam = [-179.99, 179.985, -179.995, 179.97, 179.99, -179.98, 179.98, -179.97, 179.99, -179.995]
    summary = summarize_track(_summary_rows(seam))
    assert abs(wrap(math.radians(summary["ok_pose_median"]["theta_deg"]) - math.pi)) < math.radians(0.05)
    assert summary["ok_pose_spread"]["theta_std_deg"] < 0.05          # thống kê tuyến tính cho ≈ 180°
    assert summary["ok_pose_spread"]["theta_range_deg"] < 0.1          # thống kê tuyến tính cho ≈ 360°
    # xa mối nối ±180°: đúng như thống kê tuyến tính trước đây
    summary = summarize_track(_summary_rows([5.0, 6.0, 7.0, 6.5]))
    assert summary["ok_pose_median"]["theta_deg"] == pytest.approx(6.25)
    assert summary["ok_pose_spread"]["theta_std_deg"] == pytest.approx(0.7395, abs=1e-4)
    assert summary["ok_pose_spread"]["theta_range_deg"] == pytest.approx(2.0)
    # vòng không OK không vào thống kê tư thế
    summary = summarize_track(_summary_rows([10.0, 11.0]) + _summary_rows([-120.0], status=FAILED))
    assert summary["ok"] == 2 and summary["failed"] == 1 and summary["ok_pose_median"]["theta_deg"] == pytest.approx(10.5)


def test_heading_near_180_localizes_and_summarises_on_the_circle(room_map):
    """Cảm biến quay ≈ 180° so với lúc dựng bản đồ (ví dụ gá ngược trên xe): từng vòng OK, tóm tắt vẫn đúng."""
    rng = np.random.default_rng(71)
    truth = (0.1, -0.05, math.radians(180.06))
    rows = []
    for i in range(8):
        angles, ranges = live_scan(truth, rng, n_movers=1)
        result = localize(room_map, angles, ranges, (0.1, -0.05, math.pi))
        assert result.status == OK and pose_error(result, truth)[0] < 0.02 and pose_error(result, truth)[1] < 1.0
        rows.append({"index": i, "t_s": 0.1 * i, **result.to_dict()})
    thetas = [row["theta_deg"] for row in rows]
    assert min(thetas) < 0 < max(thetas)                   # đúng ca khó: theta của các vòng mang hai dấu
    summary = summarize_track(rows)
    assert abs(wrap(math.radians(summary["ok_pose_median"]["theta_deg"]) - truth[2])) < math.radians(0.2)
    assert summary["ok_pose_spread"]["theta_std_deg"] < 0.2 and summary["ok_pose_spread"]["theta_range_deg"] < 0.2


def _beams_across(d0, normal_deg, behind=0.6, n=701):
    """Tia từ gốc cắt một tường thẳng cách gốc d0 (pháp tuyến hướng normal_deg), trong ±35° quanh pháp tuyến; điểm
    chạm nằm sau tường `behind` m."""
    heads = math.radians(normal_deg) + np.radians(np.linspace(-35.0, 35.0, n))
    r = d0 / np.cos(heads - math.radians(normal_deg)) + behind
    return np.column_stack([r * np.cos(heads), r * np.sin(heads)])


def test_beams_through_a_diagonal_staircase_wall_are_conflicts():
    """Tường 45° dựng tay, dày một ô, các ô chỉ chạm nhau ở góc (8-liên thông): tia nào đi qua cũng là xuyên tường."""
    grid = GridSpec(-2.0, 4.0, -3.0, 3.0, 0.05)
    states = np.full(grid.shape, FREE, np.int8)
    rows, cols = grid.shape
    for c in range(cols):
        x = grid.x_min + (c + 0.5) * grid.resolution
        r = int(math.floor((2.0 - x - grid.y_min) / grid.resolution))      # tâm ô nằm đúng trên x + y = 2
        if 0 <= r < rows:
            states[r, c] = OCCUPIED
            states[r + 1:, c] = UNKNOWN
    lmap = LocalizationMap(states, grid)
    through = lmap.through_walls(_beams_across(2.0 / math.sqrt(2), 45.0), (0.0, 0.0, 0.0))
    assert through.all(), f"chỉ bắt {through.mean():.2f}"          # trước khi sửa: 0,15


def test_beams_through_a_45_degree_mapped_wall_are_conflicts():
    """Tường 45° dựng bằng đường bản đồ thật (tia -> OccupancyCounts), lệch 1,3 cm nên ô tường nối nhau qua góc."""
    grid = GridSpec(-3.0, 3.0, -3.0, 3.0, 0.05)
    n = math.sqrt(0.5)
    d0 = 1.513
    cx, cy = d0 * n, d0 * n
    seg = np.array([(cx - 5 * n, cy + 5 * n, cx + 5 * n, cy - 5 * n)], np.float64)
    _, states = build_map(seg, [(0.0, 0.0, 0.0), (0.2, -0.3, 0.1), (-0.3, 0.2, -0.2)], grid, scans=8)
    lmap = LocalizationMap(states, grid)
    through = lmap.through_walls(_beams_across(d0, 45.0), (0.0, 0.0, 0.0))
    assert through.all(), f"chỉ bắt {through.mean():.2f}"          # trước khi sửa: 0,52


def test_negative_or_non_finite_window_is_rejected(room_map, tmp_path):
    angles, ranges = live_scan(TRUE_POSES[0], np.random.default_rng(3), n_movers=0)
    points = decimate(scan_points(angles, ranges, room_map.config), room_map.res)
    bad_windows = [(-0.3, 0.3, 0.2), (0.3, -0.3, 0.2), (0.3, 0.3, -0.2), (-0.01, 0.3, 0.2), (math.nan, 0.3, 0.2),
                   (0.3, math.inf, 0.2), (0.3, 0.3)]
    for window in bad_windows:
        with pytest.raises(ValueError, match="không âm"):
            localize(room_map, angles, ranges, (0.0, 0.0, 0.0), window=window)
        with pytest.raises(ValueError, match="window"):
            room_map.search(points, (0.0, 0.0, 0.0), window)
    with pytest.raises(ValueError, match="window"):                     # kiểm cả khi quá ít tia
        localize(room_map, angles[:10], ranges[:10], window=(-0.3, 0.3, 0.2))
    # wθ = 0 vẫn hợp lệ: chỉ một hướng
    assert localize(room_map, angles, ranges, (0.0, 0.0, 0.0), window=(0.3, 0.3, 0.0)).search["angles"] == 1
    # run() từ chối trước khi nạp bản đồ / bản ghi và trước khi tạo thư mục kết quả
    out = tmp_path / "ket_qua"
    missing_map, missing_recording = tmp_path / "khong_co_ban_do", tmp_path / "khong_co.npz"
    with pytest.raises(ValueError, match="window"):
        run(missing_map, missing_recording, out, LocalizeConfig(), window=(-0.3, 0.3, 0.2))
    # CLI: thoát mã 2 với thông báo rõ, không traceback, không ghi gì
    for bad in (["--window", "-0.3", "0.3", "10"], ["--window", "0.5", "0.5", "-30"], ["--window", "nan", "0.5", "10"],
                ["--initial", "0", "nan", "0"]):
        with pytest.raises(SystemExit) as exc:
            main(["--map", str(missing_map), "--recording", str(missing_recording), "--out", str(out), *bad])
        assert exc.value.code == 2
    assert not out.exists()


def test_sensor_off_the_map_is_no_overlap_not_a_conflict(room_map):
    """--initial sai hẳn (cảm biến ngoài bản đồ): không tia nào kiểm được -> FAILED vì no_overlap, không phải vì
    mâu thuẫn với bản đồ (0 mâu thuẫn)."""
    angles, ranges = live_scan(TRUE_POSES[0], np.random.default_rng(47), n_movers=0)
    result = localize(room_map, angles, ranges, (30.0, 0.0, 0.0))
    assert result.status == FAILED and "no_overlap" in result.reasons
    assert "conflicts_with_map" not in result.reasons
    assert result.matched == result.conflicts == 0 and result.conflict_fraction == 0.0
    assert result.search["second_peak_checked"] is False and json.dumps(result.to_dict(), allow_nan=False)
    # vẫn FAILED dù nới hết ngưỡng khớp
    lax = LocalizationMap(room_map.states, GRID, LocalizeConfig(min_matched=0, min_matched_fraction=0.0))
    lax_result = localize(lax, angles, ranges, (30.0, 0.0, 0.0), window=(0.1, 0.1, math.radians(5.0)))
    assert lax_result.status == FAILED and "no_overlap" in lax_result.reasons


def test_overlay_pose_colours_differ_from_the_map_and_failed_scans_are_labelled(room_map):
    for pose_color in POSE_COLORS.values():
        for map_color in [*COLORS.values(), ORIGIN_COLOR]:
            assert sum(abs(a - b) for a, b in zip(pose_color, map_color)) >= 150, (pose_color, map_color)

    def count(image, color):
        return int(np.all(image == np.array(color, np.uint8), axis=2).sum())

    scale = max(1, int(640 / max(GRID.shape)))                  # như render_overlay mặc định; x lên trên, y sang trái

    def pixel(x, y):
        return int((GRID.y_max - y) / GRID.resolution * scale), int((GRID.x_max - x) / GRID.resolution * scale)

    angles, ranges = live_scan(TRUE_POSES[0], np.random.default_rng(59), n_movers=0)
    points = scan_points(angles, ranges, room_map.config)
    failed = [{"index": i, "status": FAILED, "x": -1.0 + 0.3 * i, "y": -0.5, "theta_deg": 20.0 * i} for i in range(4)]
    image = render_overlay(room_map, failed, {3: points}, "k01 vs map\nFAILED 4 of 4")
    assert count(image, POSE_COLORS[OK]) == 0 and count(image, POSE_COLORS[FAILED]) > 0
    # vòng FAILED đầu (θ = 0: vạch hướng thẳng lên) là dấu X: bốn nhánh chéo đều mang màu FAILED
    cx, cy = pixel(-1.0, -0.5)
    for dx, dy in ((3, 3), (-3, 3), (3, -3), (-3, -3)):
        assert tuple(image[cy + dy, cx + dx]) == POSE_COLORS[FAILED], (dx, dy)
    caption = overlay_caption(failed, "k01 vs map", {3: points})
    assert caption[0] == "k01 vs map"
    assert any("scan #3 FAILED" in line and "NOT accepted" in line for line in caption)
    assert any("map origin" in line for line in caption)
    rows = failed[:2] + [{"index": 2, "status": OK, "x": 0.21, "y": -0.14, "theta_deg": 9.0}] + failed[3:]
    assert any(line == "points: scan #2 OK" for line in overlay_caption(rows))
    image = render_overlay(room_map, rows, {2: points}, "sim")
    assert count(image, POSE_COLORS[OK]) > 0
    cx, cy = pixel(0.21, -0.14)
    assert tuple(image[cy, cx]) == POSE_COLORS[OK] and tuple(image[cy + 4, cx]) == (0, 0, 0)     # chấm viền đen


def test_track_mode_recentres_only_on_ok_poses(tmp_path):
    """--track: vòng không OK (ở đây: vòng quét từ phòng khác) không được dời tâm cửa sổ của vòng sau."""
    counts, states = build_map(scans=3)
    write_outputs(counts, states, tmp_path / "map_sim", source="sim", source_id="sim", t=1.0)
    rng = np.random.default_rng(53)
    truth = (0.1, -0.05, math.radians(4.0))
    hall = np.array(disc(0.0, 0.0, 2.3, sides=40) + box(0.9, 0.2, 0.2, 1.2), np.float64)
    scans = [live_scan(truth, rng, n_movers=0), live_scan(truth, rng, n_movers=0),
             raycast((0.0, 0.0, 0.0), hall, noise=0.01, dropout=0.1, rng=rng), live_scan(truth, rng, n_movers=0)]
    recording = _record(tmp_path / "lan_canh", scans)
    assert main(["--map", str(tmp_path / "map_sim"), "--recording", str(recording), "--out", str(tmp_path / "out"),
                 "--track", "--window", "0.2", "0.2", "10"]) == 0
    rows = json.loads((tmp_path / "out" / "localize.json").read_text(encoding="utf-8"))["track"]
    assert [row["status"] for row in rows] == [OK, OK, FAILED, OK]
    last_ok, bad, after = rows[1], rows[2], rows[3]
    # vòng hỏng có tư thế khác hẳn vòng OK trước nó: nếu tâm cửa sổ bám theo nó thì phép thử thấy được
    assert (math.hypot(bad["x"] - last_ok["x"], bad["y"] - last_ok["y"]) > 0.05
            or abs(bad["theta_deg"] - last_ok["theta_deg"]) > 2.0)
    assert (after["search"]["center_x"], after["search"]["center_y"], after["search"]["center_theta_deg"]) == \
        pytest.approx((last_ok["x"], last_ok["y"], last_ok["theta_deg"]))


def test_cli_every_and_limit_pick_revolutions(tmp_path):
    counts, states = build_map(scans=2)
    write_outputs(counts, states, tmp_path / "map_sim", source="sim", source_id="sim", t=1.0)
    rng = np.random.default_rng(61)
    truth = (0.11, -0.07, math.radians(6.0))
    recording = _record(tmp_path / "sau_vong", [live_scan(truth, rng, n_movers=0) for _ in range(6)])
    out = tmp_path / "out"
    assert main(["--map", str(tmp_path / "map_sim"), "--recording", str(recording), "--out", str(out),
                 "--skip-seconds", "0.05", "--every", "2", "--limit", "2"]) == 0
    with (out / "track.csv").open(encoding="utf-8") as handle:
        assert [int(row["index"]) for row in csv.DictReader(handle)] == [1, 3]      # [1..5][::2][:2]
    report = json.loads((out / "localize.json").read_text(encoding="utf-8"))
    assert report["every"] == 2 and report["summary"]["scans"] == 2


def test_cli_converts_degrees_and_global_search_uses_five_levels(tmp_path):
    """--initial / --window nhận độ (đổi sang radian đúng một lần); --levels, --min-range, --max-range vào cấu hình;
    --global mặc định 5 mức nhánh-cận."""
    counts, states = build_map(scans=2)
    write_outputs(counts, states, tmp_path / "map_sim", source="sim", source_id="sim", t=1.0)
    rng = np.random.default_rng(73)
    truth = (0.05, 0.03, math.radians(92.0))
    recording = _record(tmp_path / "quay_90", [live_scan(truth, rng, n_movers=0) for _ in range(2)])
    base = ["--map", str(tmp_path / "map_sim"), "--recording", str(recording)]
    assert main([*base, "--out", str(tmp_path / "local"), "--initial", "0", "0", "90", "--window", "0.2", "0.2", "10",
                 "--levels", "3", "--min-range", "0.3", "--max-range", "6.0"]) == 0
    report = json.loads((tmp_path / "local" / "localize.json").read_text(encoding="utf-8"))
    assert report["initial"]["theta_deg"] == pytest.approx(90.0) and report["window"]["theta_deg"] == pytest.approx(10.0)
    assert (report["config"]["levels"], report["config"]["min_range_m"], report["config"]["max_range_m"]) == (3, 0.3, 6.0)
    for row in report["track"]:
        assert row["status"] == OK and abs(row["theta_deg"] - 92.0) < 1.0
        assert row["search"]["center_theta_deg"] == pytest.approx(90.0)
        assert row["search"]["window_theta_deg"] == pytest.approx(10.0)
    assert main([*base, "--out", str(tmp_path / "global"), "--global", "--limit", "1"]) == 0
    report = json.loads((tmp_path / "global" / "localize.json").read_text(encoding="utf-8"))
    assert report["mode"] == "global" and report["config"]["levels"] == 5 and report["window"] == "whole map, 360°"
    assert report["summary"]["ok"] == 1 and report["track"][0]["search"]["global"] is True


def test_orientation_just_outside_the_window_is_caught_only_by_window_edge(room_map):
    """Hướng thật 24°, cửa sổ ±20°, x/y trong cửa sổ: mọi tia vẫn khớp nên chỉ mép cửa sổ theo θ tố cáo."""
    rng = np.random.default_rng(41)
    truth = (0.05, -0.04, math.radians(24.0))
    angles, ranges = live_scan(truth, rng, n_movers=0)
    result = localize(room_map, angles, ranges, (0.0, 0.0, 0.0), window=(0.3, 0.3, math.radians(20.0)))
    assert result.status == FAILED and result.reasons == ("window_edge",)
    assert abs(result.search["discrete_x"]) < 0.25 and abs(result.search["discrete_y"]) < 0.25   # không phải mép x/y
    assert abs(result.search["discrete_theta_deg"]) > 19.5


def test_each_remaining_check_fires_on_its_own(room_map, monkeypatch):
    """few_matched, phần θ của degenerate, search_truncated, refine_unstable: mỗi kiểm tự nó đổi kết luận."""
    rng = np.random.default_rng(43)
    truth = (0.1, -0.05, math.radians(4.0))
    angles, ranges = live_scan(truth, rng, n_movers=0)
    assert localize(room_map, angles, ranges).status == OK

    def with_config(**kwargs):
        return localize(LocalizationMap(room_map.states, GRID, LocalizeConfig(**kwargs)), angles, ranges)

    few = with_config(min_matched=1000)                     # > số tia có thể có (500): chỉ ngưỡng này hỏng
    assert few.status == FAILED and few.reasons == ("few_matched",) and few.matched_fraction > 0.9
    theta = with_config(max_std_theta_deg=1e-4)             # σθ vượt ngưỡng, σx, σy vẫn nhỏ
    assert theta.status == AMBIGUOUS and theta.reasons == ("degenerate",)
    assert theta.std_x_m < 0.01 and theta.std_y_m < 0.01
    truncated = with_config(max_candidates=10)
    assert truncated.status == AMBIGUOUS and truncated.reasons == ("search_truncated",)
    lmap = LocalizationMap(room_map.states, GRID)
    monkeypatch.setattr(lmap, "refine", lambda points, pose: (np.asarray(pose) + [0.3, 0.0, 0.0], np.diag([1e-6] * 3)))
    unstable = localize(lmap, angles, ranges)
    assert unstable.status == AMBIGUOUS and unstable.reasons == ("refine_unstable",)
    assert pose_error(unstable, truth)[0] < 0.1                  # giữ đỉnh rời rạc, không nhận bước tinh chỉnh chạy xa
