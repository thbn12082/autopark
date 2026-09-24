"""Odometry khớp scan (lidar/scan_odometry.py) trên phòng tổng hợp có quỹ đạo biết trước, không cần thiết bị.

Vòng quét mô phỏng kiểu C1 (360°, 500 tia, nhiễu 1 cm, 10 % tia mất phản hồi, vật di động không có trong bản đồ).
Các cận sai số trong test rộng hơn số đo lúc viết test (24/09/2026, máy bàn) khoảng 2–5 lần; số đo ghi cạnh từng cận.
"""
import csv
import json
import math
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.lidar.localize import AMBIGUOUS, FAILED, OK  # noqa: E402
from autopark.lidar.recording import ScanRecorder  # noqa: E402
from autopark.lidar.scan_odometry import (INIT, SCAN_TO_MAP, SCAN_TO_SCAN, OdometryConfig, ScanOdometry,  # noqa: E402
                                          between, between_many, compare_trajectories, compose, dense_points,
                                          expand_drow_inputs, interpolate_odometry, main, output_names,
                                          relative_to_first, run_sequence, scale_motion, static_drift)

DROW_DIR = Path(__file__).resolve().parents[1] / "datasets" / "drow" / "DROWv2-data"

# Phòng sa bàn/phòng nhỏ không đối xứng; tường không nằm trên biên ô 5 cm.
ROOM = [(-3.03, -2.17), (3.12, -2.17), (3.12, 0.62), (2.41, 0.62), (2.41, 2.23), (-1.37, 2.23), (-1.37, 1.51),
        (-3.03, 1.51)]


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


def raycast(pose, segments, n=500, fov=2 * math.pi, max_range=12.0, noise=0.0, dropout=0.0, rng=None):
    """Góc theo quy ước dự án (0 = trước, dương ngược chiều kim đồng hồ); NaN = không phản hồi."""
    if fov >= 2 * math.pi - 1e-9:
        angles = -math.pi + 2 * math.pi * np.arange(n) / n
    else:
        angles = np.linspace(-fov / 2, fov / 2, n)
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


def movers(rng, count=3, box_=(-2.5, 2.0, -1.8, 1.2), avoid=None):
    """Vật di động (người, ghế) đường kính 30 cm không có trong bản đồ; cách cảm biến `avoid` ≥ 0,5 m."""
    segs = []
    while len(segs) < 10 * count:
        cx, cy = rng.uniform(box_[0], box_[1]), rng.uniform(box_[2], box_[3])
        if avoid is None or math.hypot(cx - avoid[0], cy - avoid[1]) >= 0.5:
            segs += disc(cx, cy, 0.15)
    return np.array(segs, np.float64).reshape(-1, 4)


def drive(start, commands, dt=0.1):
    """Quỹ đạo kiểu xe: mỗi lệnh (v m/s, ω rad/s, số vòng quét). Trả mảng (N, 3), vòng đầu là `start`."""
    poses = [np.array(start, np.float64)]
    for v, w, steps in commands:
        for _ in range(steps):
            x, y, th = poses[-1]
            if abs(w) < 1e-12:
                nxt = (x + v * dt * math.cos(th), y + v * dt * math.sin(th), th)
            else:
                r = v / w
                nxt = (x + r * (math.sin(th + w * dt) - math.sin(th)), y - r * (math.cos(th + w * dt) - math.cos(th)),
                       th + w * dt)
            poses.append(np.array(nxt))
    return np.array(poses)


# Đi tới 1,8 m, rẽ trái 90° bán kính 0,6 m, đi tiếp, dừng, lùi rồi lùi cong: ≈ 4,4 m, 10 Hz, 0,3 m/s như xe 1/12 chậm.
CAR_PATH = [(0.3, 0.0, 60), (0.3, 0.5, 31), (0.3, 0.0, 12), (0.0, 0.0, 10), (-0.3, 0.0, 20), (-0.3, -0.4, 25)]
CAR_START = (-2.3, -1.5, 0.0)


def simulate(truth, rng, *, segments=STATIC, n_movers=3, noise=0.01, dropout=0.1, mirror=False, fov=2 * math.pi, n=500,
             max_range=12.0):
    scans = []
    for k, pose in enumerate(truth):
        segs = np.vstack([segments, movers(rng, n_movers, avoid=pose)]) if n_movers else segments
        angles, ranges = raycast(pose, segs, n=n, fov=fov, max_range=max_range, noise=noise, dropout=dropout, rng=rng)
        scans.append((-angles if mirror else angles, ranges, 0.1 * k))
    return scans


def errors_along(est, truth):
    """Sai số của từng tư thế (đã đưa cả hai về hệ tư thế đầu): tịnh tiến (m), quay (độ)."""
    e = between_many(relative_to_first(truth), relative_to_first(est))
    return np.hypot(e[:, 0], e[:, 1]), np.degrees(np.abs(e[:, 2]))


@pytest.fixture(scope="module")
def car_truth():
    return drive(CAR_START, CAR_PATH)


@pytest.fixture(scope="module")
def car_run(car_truth):
    rng = np.random.default_rng(5)
    scans = simulate(car_truth, rng)
    return scans, run_sequence(scans, OdometryConfig())


def test_pose_algebra_round_trips():
    a, b = np.array([0.4, -1.2, 2.9]), np.array([-0.3, 0.8, -2.5])
    assert np.allclose(between(a, compose(a, b)), b, atol=1e-12)
    assert np.allclose(compose(a, between(a, b)), b, atol=1e-12)
    many = between_many(np.array([a, b]), np.array([b, a]))
    assert np.allclose(many[0], between(a, b)) and np.allclose(many[1], between(b, a))
    assert np.allclose(relative_to_first(np.array([a, compose(a, b)]))[1], b, atol=1e-12)


def test_scan_to_map_tracks_a_known_car_trajectory_within_drift_bounds(car_truth, car_run):
    _, odometry = car_run
    statuses = [step.status for step in odometry.steps]
    assert statuses[0] == INIT and all(s == OK for s in statuses[1:]), odometry.summary()["reasons"]
    trans, rot = errors_along(odometry.poses(), car_truth)
    # đo 24/09/2026: lớn nhất 10,6 mm và 0,20°; cuối 4,1 mm, 0,12° sau 4,4 m
    assert trans.max() < 0.03 and rot.max() < 0.6, (trans.max(), rot.max())
    report = compare_trajectories(odometry.poses(), car_truth, segment_lengths=(1.0,))
    assert report["path_ref_m"] == pytest.approx(4.44, abs=0.05)
    assert report["end"]["translation_m"] < 0.02 and report["end"]["rotation_deg"] < 0.3
    seg = report["segments"]["1"]
    assert seg["translation_pct"]["median"] < 1.5 and seg["rotation_deg_per_m"]["p95"] < 0.5    # đo: 0,23 %; 0,10°/m
    assert report["yaw_gain"] == pytest.approx(1.0, abs=0.03)
    assert report["step_ratio"] == pytest.approx(1.0, abs=0.05)
    assert 20 <= odometry.keyframes <= 80                         # một khung khóa mỗi ≈ 10 cm / 5°, không mỗi vòng
    assert odometry.summary()["time_ms"]["median"] < 300.0       # ngân sách rộng; số đo ở tài liệu


def test_static_sensor_scan_to_map_does_not_drift_but_scan_to_scan_does():
    """Cảm biến đứng yên, nhiễu mới mỗi vòng. scan_to_map không thêm khung khóa nào nên không cộng dồn; scan_to_scan
    lấy vòng trước làm tham chiếu nên sai số đi bộ ngẫu nhiên."""
    rng = np.random.default_rng(9)
    scans = simulate([(0.35, -0.4, math.radians(17.0))] * 300, rng)
    mapped = run_sequence(scans, OdometryConfig())
    assert mapped.keyframes == 1 and mapped.summary()["failed"] == 0
    drift = static_drift(mapped.poses(), [s[2] for s in scans])
    # đo 24/09/2026 (600 vòng, cùng cảnh): lệch lớn nhất 7,4 mm và 0,19°, độ dốc 0,2 mm/phút
    assert drift["duration_s"] == pytest.approx(29.9)
    assert drift["max_excursion_m"] < 0.015 and drift["max_excursion_deg"] < 0.4
    assert drift["slope_per_minute"]["translation_m"] < 0.005 and abs(drift["slope_per_minute"]["theta_deg"]) < 0.1
    # Vòng-với-vòng: không có vật di động (vật di động của phép thử nhảy chỗ mỗi vòng, không giống thật, và làm
    # hướng đi bộ ngẫu nhiên ≈ 2° trong 10 s).
    still = simulate([(0.35, -0.4, math.radians(17.0))] * 100, np.random.default_rng(10), n_movers=0)
    chained = run_sequence(still, OdometryConfig(mode=SCAN_TO_SCAN))
    assert chained.keyframes == 100                                  # mỗi vòng chấp nhận là tham chiếu mới
    chain_drift = static_drift(chained.poses(), [s[2] for s in still])
    mapped_drift = static_drift(run_sequence(still, OdometryConfig()).poses(), [s[2] for s in still])
    # đo 24/09/2026 (150 vòng, không vật di động): scan_to_scan lớn nhất 33 mm, 0,41°; scan_to_map 6 mm, 0,15°
    assert chain_drift["max_excursion_m"] < 0.06 and chain_drift["max_excursion_deg"] < 1.0
    assert chain_drift["max_excursion_m"] > 2 * mapped_drift["max_excursion_m"]


def test_mirrored_scans_turn_the_wrong_way(car_truth):
    """Đảo dấu góc (lỗi quy ước trái/phải): odometry vẫn nhất quán với chính nó nhưng quay ngược chiều thật."""
    rng = np.random.default_rng(12)
    scans = simulate(car_truth, rng, n_movers=0, mirror=True)
    mirrored = run_sequence(scans, OdometryConfig())
    report = compare_trajectories(mirrored.poses(), car_truth)
    assert report["yaw_gain"] < -0.9
    assert report["end"]["rotation_deg"] > 40          # quay thật +33°, bản lật gương −33° (đo: 62,9°)


def test_constant_velocity_prediction_keeps_fast_motion_inside_the_window():
    """0,25 m mỗi vòng (> cửa sổ ±0,15 m): mô hình vận tốc không đổi chỉ cần tìm lại ở vòng đầu; mô hình đứng yên
    phải tìm lại gần như mọi vòng."""
    truth = drive((-2.4, -1.2, 0.3), [(2.5, 0.0, 16)])
    rng = np.random.default_rng(13)
    scans = simulate(truth, rng, n_movers=0)
    fast = run_sequence(scans, OdometryConfig())
    still = run_sequence(scans, OdometryConfig(motion_model="zero"))
    retries_fast = sum(step.retried for step in fast.steps)
    retries_still = sum(step.retried for step in still.steps)
    assert retries_fast <= 2 and retries_still >= len(scans) - 3, (retries_fast, retries_still)
    assert all(step.status == OK for step in fast.steps[1:])
    trans, rot = errors_along(fast.poses(), truth)
    assert trans.max() < 0.03 and rot.max() < 0.5


def test_featureless_corridor_is_flagged_degenerate_and_the_axis_is_locked():
    """Hành lang hai tường song song, không có đầu hồi trong tầm: chuyển động dọc hành lang không quan sát được.
    Odometry phải báo AMBIGUOUS/degenerate, có tiên nghiệm kéo thành phần dọc hành lang về dự đoán (ở đây vận tốc ban
    đầu 0, nên tư thế dọc trục gần như đứng yên: đúng là "không biết", không phải "đã đo"); ngang hành lang và hướng
    thì vẫn đúng. Hành lang lý tưởng: đỉnh tìm theo dọc trục rơi vào đâu cũng được, kể cả mép cửa sổ; mép theo dọc trục
    không được làm vòng FAILED (lý do `edge_along_axis`), vì thành phần đó bị bỏ khi đặt điểm xuất phát tinh chỉnh.
    Đo 24/09/2026 (tối, sau khi sửa) trên 41 seed × 60 vòng: 0 vòng FAILED; mép dọc trục trung bình 0,7 lần mỗi chuỗi;
    dọc trục lớn nhất 134 mm (trung vị 20 mm, thật đi 1,8 m); ngang 24 mm; hướng 0,83°. Bản khóa cứng 24/09/2026 (mép
    dọc trục vẫn tính là mép) cho 19/41 seed có vòng FAILED `window_edge`. Cận dọc trục 0,3 m chỉ đúng với cảnh này
    (nhiễu 5 mm): với nhiễu 1 cm và tường ±300 m, khóa mềm để vận tốc dọc trục đi bộ ngẫu nhiên, 14/41 seed > 0,5 m
    (docstring của scan_odometry, bước 5); vì vậy test chỉ giữ việc báo AMBIGUOUS, không giữ độ lớn trôi dọc trục."""
    walls = np.array([(-30.0, -0.8, 30.0, -0.8), (-30.0, 0.8, 30.0, 0.8)], np.float64)
    truth = drive((0.0, 0.1, 0.0), [(0.3, 0.0, 60)])
    ref = relative_to_first(truth)
    edges_along_axis = 0
    for seed in (2, 8, 14, 30):
        scans = simulate(truth, np.random.default_rng(seed), segments=walls, n_movers=0, noise=0.005)
        odometry = run_sequence(scans, OdometryConfig())
        later = odometry.steps[1:]
        assert all(step.status == AMBIGUOUS and "degenerate" in step.reasons and step.locked for step in later), seed
        assert max(step.normal_ratio for step in later) < 0.02, seed               # đo: ≤ 0,0103 với nhiễu 5 mm
        edges_along_axis += sum("edge_along_axis" in step.reasons for step in later)
        est = relative_to_first(odometry.poses())
        assert np.abs(est[:, 0]).max() < 0.3, seed           # dọc trục: gần dự đoán, không theo 1,8 m thật
        assert np.abs(est[:, 1] - ref[:, 1]).max() < 0.05, seed                    # ngang hành lang
        assert np.degrees(np.abs(est[:, 2] - ref[:, 2])).max() < 1.5, seed        # hướng
    assert edges_along_axis > 0                      # nhánh "mép chỉ dọc trục" thật sự được đi qua (đo: 7 lần)


def test_nearly_featureless_corridor_is_caught_by_the_surface_normals():
    """Hành lang có vài cột mảnh: Hessian khớp scan không suy biến, độ lệch chuẩn nhỏ; chỉ phép kiểm pháp tuyến bề
    mặt bắt được. Tắt phép kiểm đó thì odometry báo OK một quỹ đạo dọc trục sai (đo: tỉ lệ bước 0,60)."""
    walls = [(-30.0, -0.8, 30.0, -0.8), (-30.0, 0.8, 30.0, 0.8)]
    for x in (-3.0, 2.5, 7.0):
        walls += box(x, 0.75, 0.04, 0.04)
    walls = np.array(walls, np.float64)
    truth = drive((0.0, 0.1, 0.0), [(0.3, 0.0, 20)])
    rng = np.random.default_rng(15)
    scans = simulate(truth, rng, segments=walls, n_movers=0, noise=0.003, dropout=0.0)
    odometry = run_sequence(scans, OdometryConfig())
    later = odometry.steps[1:]
    assert all(step.std_x_m < 0.05 and step.std_theta_deg < 2.0 for step in later)   # kiểm độ lệch chuẩn không bắt
    assert all(step.normal_ratio < 0.02 and step.status == AMBIGUOUS and step.locked for step in later)
    relaxed = run_sequence(scans, OdometryConfig(min_normal_ratio=0.0))
    assert all(step.status == OK and not step.locked for step in relaxed.steps[1:])
    assert compare_trajectories(relaxed.poses(), truth)["step_ratio"] < 0.9


def _small_pillar_hall():
    """Hội trường 30 × 6 m, dọc hai tường có cột 0,2 × 0,3 m: từ x ≈ 5 m, tường đầu hồi ra ngoài tầm khớp 7 m, còn lại
    hai tường dài và các cột. Cột quá nhỏ để có 7 tia thẳng hàng (không cho pháp tuyến), nên phép kiểm pháp tuyến báo
    suy biến, trong khi cột vẫn cho biết vị trí dọc trục."""
    walls = polygon([(-2.0, -3.0), (28.0, -3.0), (28.0, 3.0), (-2.0, 3.0)])
    for k, x in enumerate(np.arange(0.0, 27.0, 1.7)):
        walls += box(x, 2.6 if k % 2 else -2.6, 0.2, 0.3, 10.0 * k)
    return np.array(walls, np.float64)


def test_degenerate_flag_from_small_pillars_still_lets_scan_matching_track_a_speed_change():
    """Kiểu hỏng 1 của DROW trên bản 24/09/2026: phép kiểm pháp tuyến báo suy biến (cột nhỏ không cho pháp tuyến) và
    khóa CỨNG (σ 2 mm) giữ dọc trục theo vận tốc cũ; robot giảm tốc 1,5 → 0,5 m/s thì ước lượng vượt trước, đỉnh ra mép
    cửa sổ, FAILED rồi lạc (đo 24/09/2026 trên bản đó: 87/120 vòng khóa, 18 FAILED, lệch cuối 1,82 m). Khóa MỀM
    (σ 3 cm) để số đo từ cột thắng tiên nghiệm. Đo 24/09/2026 (tối, sau khi sửa), seed 18: vẫn 87 vòng AMBIGUOUS/khóa,
    0 FAILED, lệch cuối 2,9 cm sau 12 m."""
    truth = drive((0.0, 0.2, 0.0), [(1.5, 0.0, 60), (0.5, 0.0, 60)])
    scans = simulate(truth, np.random.default_rng(18), segments=_small_pillar_hall(), n_movers=0)
    odometry = run_sequence(scans, OdometryConfig())
    locked = [step for step in odometry.steps if step.locked]
    assert len(locked) > len(odometry.steps) // 2                              # phép kiểm vẫn báo suy biến (đo: 87)
    assert all(step.status == AMBIGUOUS and "degenerate" in step.reasons for step in locked)
    assert odometry.summary()["failed"] == 0
    trans, rot = errors_along(odometry.poses(), truth)
    assert trans[-1] < 0.1 and trans.max() < 0.15 and rot.max() < 0.5, (trans[-1], trans.max(), rot.max())


def _doors_corridor():
    """Hành lang rộng 2,4 m, mỗi 2,4 m có một hốc cửa sâu 15 cm rộng 0,8 m ở cả hai bên."""
    walls = []
    for side in (-1.2, 1.2):
        depth = 0.15 if side > 0 else -0.15
        for x in np.arange(-10.0, 40.0, 2.4):
            walls += [(x, side, x + 1.6, side), (x + 1.6, side, x + 1.6, side + depth),
                      (x + 1.6, side + depth, x + 2.4, side + depth), (x + 2.4, side + depth, x + 2.4, side)]
    return np.array(walls, np.float64)


DROW_FOV = math.radians(224.5)


def test_matching_filters_stop_sparse_far_points_pinning_the_motion():
    """Hành lang có hốc cửa, quét kiểu DROW (224,5°, 450 tia), vòng-với-vòng, 1 m/s trong 8 m. Tường xa ở góc sượt chỉ
    là các chấm gắn với tư thế vòng trước, và tường của vòng trước dừng ở tầm tối đa; khớp cả những điểm đó kéo
    chuyển động dọc hành lang về 0. Đo 24/09/2026: có bộ lọc (tầm khớp ≤ tầm bản đồ − 1 m, điểm có kề ≤ 10 cm)
    lệch cuối 3,8 cm; bỏ cả hai bộ lọc 12 cm (120 vòng: 3,6 cm và 22 cm)."""
    truth = drive((0.0, 0.1, 0.0), [(1.0, 0.0, 80)])
    rng = np.random.default_rng(3)
    scans = simulate(truth, rng, segments=_doors_corridor(), n_movers=0, noise=0.01, dropout=0.05, fov=DROW_FOV, n=450,
                     max_range=29.0)
    filtered = compare_trajectories(run_sequence(scans, OdometryConfig(mode=SCAN_TO_SCAN)).poses(), truth)
    raw = compare_trajectories(run_sequence(scans, OdometryConfig(mode=SCAN_TO_SCAN, max_point_spacing_m=math.inf,
                                                                  match_margin_m=0.0)).poses(), truth)
    assert filtered["end"]["translation_m"] < 0.07
    assert raw["end"]["translation_m"] > 0.08 and raw["end"]["translation_m"] > 2 * filtered["end"]["translation_m"]


def test_companion_moving_with_the_sensor_fools_scan_to_scan_but_not_scan_to_map():
    """Một vật (người) đi trước-phải cách 1,3 m cùng tốc độ. Trên DROW run_2015-11-25-10-34-20-a, vòng 140–180,
    có một vật trước-phải ở cách 1,1–1,5 m suốt đoạn trong khi odometry báo đi 2,0 m; các vòng đó không có nhãn nên
    "người đi cùng" là suy luận. Với vòng trước làm tham chiếu, vật đó trông như đứng yên và kéo chuyển động về 0;
    bản đồ tăng dần giữ tường và hốc cửa của nhiều khung khóa nên không bị kéo. Đo 24/09/2026 (80 vòng,
    8 m): scan_to_scan tỉ lệ bước 0,76, lệch cuối 1,89 m; scan_to_map 1,00 và 3,3 cm."""
    truth = drive((0.0, 0.1, 0.0), [(1.0, 0.0, 80)])
    rng = np.random.default_rng(4)
    corridor = _doors_corridor()
    scans = []
    for k, pose in enumerate(truth):
        person = compose(pose, np.array([1.3, -0.5, 0.0]))
        segments = np.vstack([corridor, np.array(disc(person[0], person[1], 0.2, sides=12))])
        angles, ranges = raycast(pose, segments, n=450, fov=DROW_FOV, max_range=29.0, noise=0.01, dropout=0.05, rng=rng)
        scans.append((angles, ranges, 0.1 * k))
    chained = compare_trajectories(run_sequence(scans, OdometryConfig(mode=SCAN_TO_SCAN)).poses(), truth)
    mapped = compare_trajectories(run_sequence(scans, OdometryConfig()).poses(), truth)
    assert chained["step_ratio"] < 0.9 and chained["end"]["translation_m"] > 0.5
    assert mapped["step_ratio"] == pytest.approx(1.0, abs=0.03) and mapped["end"]["translation_m"] < 0.1


def test_dense_points_drop_sparse_grazing_hits_and_far_returns():
    """Tường y = 0,8 m quét 360° mỗi 0,72°: điểm xa trên tường cách nhau hơn 10 cm bị bỏ, điểm gần giữ; điểm có tầm
    trong (tầm bản đồ − 1 m, tầm bản đồ] bị bỏ; điểm mép vật (một bên kề gần, một bên là nền) được giữ."""
    cfg = OdometryConfig()
    angles, ranges = raycast((0.0, 0.0, 0.0), np.array([(-30.0, 0.8, 30.0, 0.8)]))
    kept = dense_points(angles, ranges, cfg)
    hit = np.isfinite(ranges)
    xs = ranges[hit] * np.cos(angles[hit])
    assert np.abs(kept[:, 0]).max() < 3.0                  # ở y = 0,8 m, hai tia kề cách nhau > 10 cm khi |x| ≳ 2,4 m
    assert np.abs(kept[:, 0]).max() > 2.0
    assert len(kept) < (np.abs(xs) <= 7.0).sum()
    assert np.all(np.hypot(kept[:, 0], kept[:, 1]) <= cfg.max_range_m - cfg.match_margin_m + 1e-9)
    # tường vuông góc ở 7,5 m: đủ dày (≈ 9 cm giữa hai tia) nhưng ngoài tầm khớp 8 − 1 = 7 m, nên bị bỏ; bỏ lề thì giữ
    angles, ranges = raycast((0.0, 0.0, 0.0), np.array([(7.5, -2.0, 7.5, 2.0)]))
    assert len(dense_points(angles, ranges, cfg)) == 0
    assert len(dense_points(angles, ranges, OdometryConfig(match_margin_m=0.0))) > 30
    # hộp nhỏ trước nền xa: điểm mép hộp vẫn được giữ
    scene = np.array(box(1.0, 0.0, 0.2, 0.4) + [(4.0, -6.0, 4.0, 6.0)], np.float64)
    angles, ranges = raycast((0.0, 0.0, 0.0), scene)
    kept = dense_points(angles, ranges, cfg)
    on_box = kept[np.abs(kept[:, 0] - 0.9) < 0.02]
    assert len(on_box) >= 10 and on_box[:, 1].max() > 0.17 and on_box[:, 1].min() < -0.17
    # vòng quét 360°: tia đầu và tia cuối kề nhau
    ring_angles = -math.pi + 2 * math.pi * np.arange(500) / 500
    ring = np.full(500, np.nan)
    ring[[0, 499]] = 2.0
    assert len(dense_points(ring_angles, ring, cfg)) == 2
    ring[[0, 499]] = np.nan
    ring[[0, 250]] = 2.0                                    # hai tia không kề nhau: không điểm nào được giữ
    assert len(dense_points(ring_angles, ring, cfg)) == 0


def test_failed_scan_uses_the_prediction_and_leaves_the_map_untouched(car_truth):
    rng = np.random.default_rng(16)
    scans = simulate(car_truth[:60], rng)
    odometry = ScanOdometry(OdometryConfig())
    for angles, ranges, t in scans[:40]:
        odometry.update(angles, ranges, t)
    passes, hits, keyframes = odometry.counts.passes.copy(), odometry.counts.hits.copy(), odometry.keyframes
    # một vòng quét lạ: hội trường tròn đường kính 10 m, hoàn toàn không khớp bản đồ
    ring = np.linspace(0, 2 * math.pi, 40, endpoint=False)
    hall = np.array(polygon([(5 * math.cos(a), 5 * math.sin(a)) for a in ring]))
    angles, ranges = raycast((0.0, 0.0, 0.0), hall, noise=0.01, rng=rng)
    predicted = compose(odometry.pose, odometry.velocity)
    step = odometry.update(angles, ranges, 4.0)
    assert step.status == FAILED and "low_match_fraction" in step.reasons
    assert np.allclose(step.pose, predicted)
    assert odometry.keyframes == keyframes
    assert np.array_equal(odometry.counts.passes, passes) and np.array_equal(odometry.counts.hits, hits)
    nan_step = odometry.update(angles, np.full_like(ranges, np.nan), 4.1)
    assert nan_step.status == FAILED and nan_step.reasons == ("too_few_beams",)
    for angles, ranges, t in scans[42:]:
        odometry.update(angles, ranges, t)
    assert all(s.status == OK for s in odometry.steps[42:])
    trans, rot = errors_along(odometry.poses(), car_truth[:60])
    assert trans.max() < 0.03 and rot.max() < 0.5


def test_lost_tracker_stops_extrapolating():
    """Sau `lost_after` vòng FAILED liên tiếp, thôi ngoại suy vận tốc: tư thế đứng lại thay vì quay tiếp mãi."""
    truth = drive((0.0, -0.5, 0.0), [(0.0, 0.5, 12)])              # quay tại chỗ 2,9° mỗi vòng
    rng = np.random.default_rng(17)
    odometry = ScanOdometry(OdometryConfig(lost_after=3))
    for angles, ranges, t in simulate(truth, rng, n_movers=0):
        odometry.update(angles, ranges, t)
    for k in range(8):
        odometry.update(np.linspace(-math.pi, math.pi, 500, endpoint=False), np.full(500, np.nan), 2.0 + 0.1 * k)
    failed = odometry.steps[-8:]
    assert all(step.status == FAILED for step in failed)
    assert ["lost" in step.reasons for step in failed] == [False, False, True, True, True, True, True, True]
    thetas = [step.theta for step in failed]
    assert thetas[1] - thetas[0] == pytest.approx(math.radians(2.865), abs=math.radians(0.3))   # còn ngoại suy
    assert thetas[-1] == pytest.approx(thetas[2], abs=1e-12)                                       # đã dừng


def test_velocity_after_recapture_is_spread_over_the_blind_scans():
    """Xe đi tới 3 cm/vòng, 17 vòng toàn NaN (30–46, `lost` từ vòng 34, tư thế đứng yên), bắt lại rồi lùi ngay. Vận tốc
    phải là chuyển động từ vòng chấp nhận cuối chia cho số vòng, không phải cả bước nhảy tích lũy dồn vào một vòng. Bản
    đầu 24/09/2026 lấy between(tư thế đứng yên, tư thế mới): vận tốc 0,35 m/vòng ở vòng bắt lại 48, cả 29 vòng sau đó
    FAILED, lệch cuối 2,6 m (đo 24/09/2026 trên bản sao mã cũ). Đo sau khi sửa: vòng 47 FAILED (`window_edge`, tư thế
    đứng yên cách thật 0,39 m), vòng 48 bắt lại, vận tốc 0,027 m/vòng, không FAILED nào nữa, lệch cuối 7,5 mm."""
    truth = drive(CAR_START, [(0.3, 0.0, 47), (-0.3, 0.0, 30)])
    scans = simulate(truth, np.random.default_rng(1), n_movers=0)
    odometry = ScanOdometry(OdometryConfig())
    velocities = []
    for k, (angles, ranges, t) in enumerate(scans):
        odometry.update(angles, np.full_like(ranges, np.nan) if 30 <= k <= 46 else ranges, t)
        velocities.append(odometry.velocity.copy())
    assert "lost" in odometry.steps[46].reasons
    recapture = next(k for k in range(47, len(scans)) if odometry.steps[k].status != FAILED)
    assert recapture <= 49
    assert math.hypot(*velocities[recapture][:2]) < 0.05                 # đo: 0,027 m/vòng (thật 0,03 rồi lùi)
    assert all(step.status != FAILED for step in odometry.steps[recapture + 1:])
    trans, _ = errors_along(odometry.poses(), truth)
    assert trans[-1] < 0.05                                               # đo: 7,5 mm


def test_scale_motion_is_the_constant_twist_fraction():
    """Chia chuyển động cho n vòng: lặp lại phần chia n lần phải về đúng chuyển động (cả khi vừa đi vừa quay)."""
    motion = np.array([0.5, -0.2, 0.7])
    part = scale_motion(motion, 1 / 4)
    pose = np.zeros(3)
    for _ in range(4):
        pose = compose(pose, part)
    assert np.allclose(pose, motion, atol=1e-12)
    assert np.allclose(scale_motion(motion, 1.0), motion)
    assert np.allclose(scale_motion(np.array([0.3, 0.06, 0.0]), 1 / 3), [0.1, 0.02, 0.0], atol=1e-12)
    assert part[2] == pytest.approx(0.7 / 4) and not np.allclose(part[:2], motion[:2] / 4)     # cung, không phải dây


def test_map_grows_when_the_sensor_leaves_the_initial_grid():
    """Hội trường 30 × 6 m có cột 0,8 × 0,6 m (đủ mặt vuông góc để quan sát dọc trục): đi 18,3 m có tăng/giảm tốc
    (1,5 → 0,9 → 1,8 → 1,2 m/s), lưới bền phải tự nới mà vẫn bám bằng khớp scan, không phải bằng tiên nghiệm theo dự
    đoán. (Bản trước của test dùng cột 0,2 × 0,3 m và vận tốc không đổi: 87/120 vòng bị khóa theo dự đoán vận tốc
    không đổi, nên lệch cuối 4,8 cm đo mô hình dự đoán chứ không đo khớp scan.)"""
    walls = polygon([(-2.0, -3.0), (28.0, -3.0), (28.0, 3.0), (-2.0, 3.0)])
    for k, x in enumerate(np.arange(0.0, 27.0, 1.7)):
        walls += box(x, 2.55 if k % 2 else -2.55, 0.8, 0.6, 10.0 * k)
    walls = np.array(walls, np.float64)
    truth = drive((0.0, 0.2, 0.0), [(1.5, 0.0, 40), (0.9, 0.0, 30), (1.8, 0.0, 40), (1.2, 0.0, 20)])
    scans = simulate(truth, np.random.default_rng(18), segments=walls, n_movers=0)
    odometry = run_sequence(scans, OdometryConfig())
    assert odometry.grid_growths >= 1
    assert odometry.counts.grid.x_max > truth[-1, 0] + odometry.config.max_range_m
    assert odometry.summary()["failed"] == 0
    assert sum(step.locked for step in odometry.steps) <= 5            # đo 24/09/2026: 0 (seed 1: 2, seed 2: 1)
    trans, rot = errors_along(odometry.poses(), truth)
    # đo 24/09/2026: 17,8 cm sau 18,3 m, 0,73° (seed 18; seed 1, 2, 3: 3,5–3,6 cm)
    assert trans[-1] < 0.4 and rot.max() < 1.5, (trans[-1], rot.max())


def test_compare_trajectories_known_values():
    """Tham chiếu đi thẳng 10 m; bản ước lượng dài hơn 2 % và lệch hướng 0,1°/m: số liệu phải đúng như tính tay."""
    n = 101
    ref = np.column_stack([np.linspace(0, 10, n), np.zeros(n), np.zeros(n)])
    est = [np.zeros(3)]
    for _ in range(n - 1):
        est.append(compose(est[-1], np.array([0.102, 0.0, math.radians(0.1) * 0.1])))
    est = np.array(est)
    report = compare_trajectories(est, ref, segment_lengths=(1.0, 5.0))
    assert report["path_ref_m"] == pytest.approx(10.0)
    assert report["path_est_m"] == pytest.approx(10.2)
    assert report["step_ratio"] == pytest.approx(1.02)
    assert report["end"]["rotation_deg"] == pytest.approx(1.0, abs=1e-9)
    seg5 = report["segments"]["5"]
    assert seg5["rotation_deg_per_m"]["median"] == pytest.approx(0.1, abs=1e-9)
    assert seg5["translation_pct"]["median"] == pytest.approx(2.0, abs=0.2)
    assert report["segments"]["1"]["translation_m"]["n"] == 91
    # bỏ các cặp có vòng không hợp lệ
    valid = np.ones(n, bool)
    valid[50] = False
    masked = compare_trajectories(est, ref, segment_lengths=(1.0,), valid=valid)
    assert masked["segments"]["1"]["translation_m"]["n"] == 89
    # quay ngược chiều (lật gương) -> yaw_gain = -1
    turn = drive((0, 0, 0), [(0.3, 0.4, 60), (0.3, -0.6, 40)])
    mirrored = turn * np.array([1.0, -1.0, -1.0])
    assert compare_trajectories(mirrored, turn)["yaw_gain"] == pytest.approx(-1.0, abs=1e-9)
    assert compare_trajectories(turn, turn)["yaw_gain"] == pytest.approx(1.0, abs=1e-9)
    with pytest.raises(ValueError):
        compare_trajectories(turn[:10], turn[:11])


def test_yaw_gain_is_taken_over_windows_not_single_steps():
    """Tham chiếu có nhiễu thời gian từng bước (như ghép dòng odometry DROW): Δθ từng bước của tham chiếu = thật +
    nhiễu triệt tiêu dần. Hồi quy từng bước bị kéo về 0 (DROW đo 24/09/2026: 0,88), trên đoạn 10 bước thì ≈ 1."""
    rng = np.random.default_rng(22)
    truth = drive((0, 0, 0), [(0.3, 0.3, 80), (0.3, -0.5, 60), (0.3, 0.2, 60)])
    jitter = rng.normal(0.0, math.radians(0.8), len(truth))
    noisy = truth.copy()
    noisy[:, 2] = truth[:, 2] + jitter                      # nhiễu trên góc tuyệt đối: Δθ từng bước nhiễu gấp đôi
    windowed = compare_trajectories(truth, noisy)["yaw_gain"]
    single = compare_trajectories(truth, noisy, yaw_window=1)["yaw_gain"]
    assert windowed == pytest.approx(1.0, abs=0.05)
    assert single < 0.9


def test_static_drift_metrics_known_values():
    t = np.arange(0, 60.0001, 0.1)
    poses = np.column_stack([0.01 * t / 60.0, np.zeros_like(t), np.radians(0.5 * t / 60.0)])
    drift = static_drift(poses, t)
    assert drift["duration_s"] == pytest.approx(60.0)
    assert drift["end_translation_m"] == pytest.approx(0.01)
    assert drift["per_minute_end_translation_m"] == pytest.approx(0.01)
    assert drift["slope_per_minute"]["x_m"] == pytest.approx(0.01)
    assert drift["slope_per_minute"]["theta_deg"] == pytest.approx(0.5)
    assert drift["max_excursion_deg"] == pytest.approx(0.5)


def test_config_is_validated():
    with pytest.raises(ValueError):
        OdometryConfig(mode="slam")
    with pytest.raises(ValueError):
        OdometryConfig(motion_model="imu")
    with pytest.raises(ValueError):
        OdometryConfig(window_x_m=-0.1)
    with pytest.raises(ValueError):
        OdometryConfig(prior_sigma_xy_m=0.0)
    with pytest.raises(ValueError):
        OdometryConfig(lock_sigma_m=0.0)
    with pytest.raises(ValueError):
        OdometryConfig(min_normal_ratio=-0.01)
    with pytest.raises(SystemExit) as exc:
        main(["--out", "x"])
    assert exc.value.code == 2


def _write_c1_recording(path, scans):
    with ScanRecorder(path, {"source_id": "sim", "name": "tinh"}) as recorder:
        for angles, ranges, t in scans:
            recorder.add(LidarScan(SourceStamp("sim", t, True, "lidar"), tuple(angles.tolist()),
                                   tuple(float(r) for r in ranges)))


def _write_drow(stem, truth, rng, mirror=False):
    """Chuỗi kiểu DROW v2: 450 tia, 0,5°, chỉ số 0 = bên phải; `.odom2` = seq, t, x, y, yaw (tư thế thật + hằng số)."""
    half = (450 - 1) / 2 * 0.5
    angles = np.radians(np.linspace(-half, half, 450))
    rows, odom = [], []
    offset = np.array([3.0, -7.0, 0.4])
    for k, pose in enumerate(truth):
        segments = np.vstack([STATIC, movers(rng, 2, avoid=pose)])
        _, ranges = raycast(pose, segments, n=450, fov=math.radians(2 * half), noise=0.01,
                            rng=rng)
        ranges = np.where(np.isfinite(ranges), ranges, 29.96)
        rows.append(",".join([str(1000 + k), f"{0.08 * k:.3f}"] + [f"{r:.3f}" for r in ranges]))
        world = compose(offset, pose)
        odom.append(f"{5000 + k},{0.08 * k + 0.004:.3f},{world[0]:.4f},{world[1]:.4f},{world[2]:.5f}")
    stem.with_suffix(".csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    stem.with_suffix(".odom2").write_text("\n".join(odom) + "\n", encoding="utf-8")
    return angles


def test_cli_writes_trajectory_summary_and_images_for_c1_and_drow(tmp_path, car_truth):
    folder = tmp_path / "đo thử odometry"
    folder.mkdir()
    rng = np.random.default_rng(21)
    _write_c1_recording(folder / "tĩnh.npz", simulate([(0.2, 0.1, 0.3)] * 30, rng))
    drow = folder / "run_synthetic.bag"
    _write_drow(drow, car_truth[40:100], rng)                        # có đoạn rẽ trái 90°
    out = folder / "kết quả"
    assert main(["--recording", str(folder / "tĩnh.npz"), "--drow", str(drow.with_suffix(".csv")), "--mode", "both",
                 "--out", str(out)]) == 0
    report = json.loads((out / "odometry.json").read_text(encoding="utf-8"))
    assert [(r["kind"], r["mode"]) for r in report["results"]] == [
        ("c1_recording", SCAN_TO_MAP), ("drow", SCAN_TO_MAP), ("c1_recording", SCAN_TO_SCAN), ("drow", SCAN_TO_SCAN)]
    c1 = report["results"][0]
    assert c1["summary"]["scans"] == 30 and c1["static_drift"]["max_excursion_m"] < 0.01
    drow_result = report["results"][1]
    comparison = drow_result["comparison"]["all_steps"]
    assert "KHÔNG phải ground truth" in drow_result["comparison"]["reference"]
    assert comparison["end"]["translation_m"] < 0.05 and comparison["yaw_gain"] == pytest.approx(1.0, abs=0.05)
    # `.odom2` tổng hợp có t + 4 ms so với vòng quét: ghép theo dòng và nội suy theo thời gian phải khác nhau một chút
    # (đo: 1,5 mm cuối chuỗi); = 0 nghĩa là không nội suy gì.
    rows_vs = drow_result["comparison"]["odometry_rows_vs_interpolated"]
    assert 0 < rows_vs["end"]["translation_m"] < 0.01
    for result in report["results"]:
        for name in result["files"].values():
            assert (out / name).exists()
        image = cv2.imdecode(np.fromfile(out / result["files"]["png"], np.uint8), cv2.IMREAD_COLOR)
        assert image is not None and image.shape[0] > 100
    with (out / drow_result["files"]["csv"]).open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 60 and rows[0]["status"] == INIT and rows[-1]["ref_x_m"] != ""
    # đảo dấu góc: quỹ đạo quay ngược odometry. `--drow` nhận thư mục (chỉ lấy .csv có .odom2), hai chế độ chạy
    # song song trong hai tiến trình.
    assert expand_drow_inputs([folder]) == [drow.with_suffix(".csv")]
    mirrored = folder / "gương"
    assert main(["--drow", str(folder), "--mirror", "--no-png", "--mode", "both", "--workers", "2",
                 "--out", str(mirrored)]) == 0
    flipped = json.loads((mirrored / "odometry.json").read_text(encoding="utf-8"))
    assert flipped["workers"] == 2 and [r["mode"] for r in flipped["results"]] == [SCAN_TO_MAP, SCAN_TO_SCAN]
    for result in flipped["results"]:
        assert result["mirror"] is True and result["comparison"]["all_steps"]["yaw_gain"] < -0.5
        assert "png" not in result["files"]
    same = flipped["results"][0]["comparison"]["all_steps"]["yaw_gain"]
    assert main(["--drow", str(drow.with_suffix(".csv")), "--mirror", "--no-png", "--out", str(folder / "một")]) == 0
    serial = json.loads((folder / "một" / "odometry.json").read_text(encoding="utf-8"))["results"][0]
    assert serial["comparison"]["all_steps"]["yaw_gain"] == pytest.approx(same, abs=1e-12)


def test_output_names_are_unique_and_keep_plain_names():
    """Tên không trùng giữ nguyên; trùng thì thêm dần thư mục cha; khác ổ đĩa cùng cây thư mục thì đánh số; cùng một tệp
    hai lần là lỗi."""
    names = output_names([("c1", "runs/may_moi_20260924_may_ban/lidar/l01_tinh.npz"),
                          ("c1", "runs/may_moi_20260924_toi/lidar/l01_tinh.npz"),
                          ("c1", "runs/lidar_bench/20260922/p07_nen_phong.npz"),
                          ("drow", "datasets/val/run_2015-11-25-10-34-20-a.bag.csv")])
    assert names == ["may_moi_20260924_may_ban__lidar__l01_tinh", "may_moi_20260924_toi__lidar__l01_tinh",
                     "p07_nen_phong", "run_2015-11-25-10-34-20-a"]
    assert output_names([("c1", "a/part_0000.npz"), ("drow", "b/part_0000.csv")]) == ["a__part_0000", "b__part_0000"]
    assert output_names([("c1", "C:/x/a.npz"), ("c1", "D:/x/a.npz")]) == ["00__a", "01__a"]
    with pytest.raises(ValueError):
        output_names([("c1", "x/a.npz"), ("c1", "x/../x/a.npz")])


def test_same_named_inputs_in_different_folders_get_separate_outputs(tmp_path):
    """Lệnh ở mục 9 của tài liệu đưa hai `l01_tinh.npz` của hai phiên vào cùng một `--out`: bản 24/09/2026 ghi đè
    `.csv`/`.png` của bản ghi thứ nhất bằng của bản ghi thứ hai, và cả hai mục trong odometry.json trỏ tới cùng một
    tệp."""
    rng = np.random.default_rng(5)
    paths = []
    for session, n in (("phiên_a", 20), ("phiên_b", 35)):
        (tmp_path / session / "lidar").mkdir(parents=True)
        paths.append(tmp_path / session / "lidar" / "l01_tinh.npz")
        _write_c1_recording(paths[-1], simulate([(0.2, 0.1, 0.3)] * n, rng))
    out = tmp_path / "kết quả"
    assert main(["--recording", *map(str, paths), "--no-png", "--workers", "2", "--out", str(out)]) == 0
    results = json.loads((out / "odometry.json").read_text(encoding="utf-8"))["results"]
    assert [r["name"] for r in results] == ["phiên_a__lidar__l01_tinh", "phiên_b__lidar__l01_tinh"]
    assert len({r["files"]["csv"] for r in results}) == 2
    for result, n in zip(results, (20, 35)):
        assert result["summary"]["scans"] == n
        with (out / result["files"]["csv"]).open(encoding="utf-8") as handle:
            assert len(list(csv.DictReader(handle))) == n
    with pytest.raises(SystemExit):
        main(["--recording", str(paths[0]), str(paths[0]), "--out", str(out)])


def test_interpolate_odometry_known_values_and_yaw_wrap():
    """Nội suy odometry DROW theo thời gian vòng quét (mục 3.4): x, y tuyến tính; yaw gỡ quấn qua ±π (nội suy thẳng
    3,1 → −3,0 rad sẽ đi qua 0 thay vì qua π); ngoài khoảng giữ đầu mút."""
    odom_t = np.array([0.0, 1.0, 2.0, 3.0])
    odom_xya = np.array([[0.0, 0.0, 2.9], [1.0, -1.0, 3.1], [2.0, -2.0, -3.0], [3.0, -3.0, -2.8]])
    got = interpolate_odometry(odom_t, odom_xya, np.array([-1.0, 0.5, 1.5, 2.25, 9.0]))
    step = (-3.0 + 2 * math.pi) - 3.1                    # bước yaw 1 → 2 sau khi gỡ quấn ≈ 0,183 rad
    expected = np.array([[0.0, 0.0, 2.9], [0.5, -0.5, 3.0], [1.5, -1.5, math.remainder(3.1 + step / 2, 2 * math.pi)],
                         [2.25, -2.25, math.remainder(3.1 + step + 0.05, 2 * math.pi)], [3.0, -3.0, -2.8]])
    assert got.shape == (5, 3)
    assert np.allclose(got, expected, atol=1e-12)
    assert abs(got[2, 2]) > 3.0                          # qua π, không qua 0


def test_cli_c1_skip_seconds_and_mirror(tmp_path, car_truth):
    """`--skip-seconds` bỏ các vòng đầu của bản ghi C1 (mọi số C1 ở mục 3.5 dùng `--skip-seconds 3`); `--mirror` đảo
    dấu góc vòng quét C1, nên quỹ đạo khớp scan phản chiếu qua trục x (y và hướng đổi dấu)."""
    rng = np.random.default_rng(23)
    path = tmp_path / "rẽ trái.npz"
    _write_c1_recording(path, simulate(car_truth[40:100], rng, n_movers=0))    # t = 0,0 … 5,9 s, có rẽ trái ≈ 89°
    out = tmp_path / "kết quả"

    def run(name, *extra):
        assert main(["--recording", str(path), "--no-png", "--out", str(out / name), *extra]) == 0
        result = json.loads((out / name / "odometry.json").read_text(encoding="utf-8"))["results"][0]
        with (out / name / result["files"]["csv"]).open(encoding="utf-8") as handle:
            return result, list(csv.DictReader(handle))

    skipped, rows = run("bỏ", "--skip-seconds", "0.95")
    assert skipped["skip_seconds"] == 0.95 and skipped["scans_used"] == skipped["summary"]["scans"] == 50
    assert len(rows) == 50 and float(rows[0]["t_s"]) == pytest.approx(1.0)
    plain, plain_rows = run("thường")
    assert plain["scans_used"] == 60 and plain["mirror"] is False
    mirrored, mirrored_rows = run("gương", "--mirror")
    assert mirrored["mirror"] is True and mirrored["files"]["csv"].endswith("__mirror.csv")
    end, end_m = plain_rows[-1], mirrored_rows[-1]
    assert float(end["theta_deg"]) > 80 and float(end_m["theta_deg"]) < -80
    assert float(end_m["theta_deg"]) == pytest.approx(-float(end["theta_deg"]), abs=1.0)
    assert float(end_m["x_m"]) == pytest.approx(float(end["x_m"]), abs=0.03)
    assert float(end_m["y_m"]) == pytest.approx(-float(end["y_m"]), abs=0.03)


# --- cổng chấp nhận: mỗi cổng có một kịch bản mà chỉ nó quyết định kết quả ------------------------------------------

STILL_POSE = (0.35, -0.4, math.radians(17.0))


def _still_room(config, pose=STILL_POSE, n=5, seed=30):
    """Cảm biến đứng yên trong phòng, không vật di động: `n` vòng dựng bản đồ (một khung khóa), vận tốc ≈ 0."""
    rng = np.random.default_rng(seed)
    odometry = ScanOdometry(config)
    for angles, ranges, t in simulate([pose] * n, rng, n_movers=0):
        odometry.update(angles, ranges, t)
    assert odometry.keyframes == 1 and all(step.status == OK for step in odometry.steps[1:])
    return odometry, rng


def _screen(pose, span_deg, dist, pieces=16):
    """Tấm chắn cong (vật mới) cách cảm biến `dist`, che `span_deg` độ quanh hướng nhìn."""
    half = math.radians(span_deg) / 2
    return polygon([(pose[0] + dist * math.cos(pose[2] + a), pose[1] + dist * math.sin(pose[2] + a))
                    for a in np.linspace(-half, half, pieces)], closed=False)


def test_new_object_in_known_free_space_fails_as_conflicting_with_the_map():
    """Vật mới đặt vào vùng bản đồ đã thấy trống: điểm chạm rơi vào ô FREE (mâu thuẫn "short").
    Ngưỡng mặc định (khớp ≥ 0,5; mâu thuẫn ≤ 0,5): mâu thuẫn > 0,5 kéo theo khớp < 0,5, nên lý do mâu thuẫn chỉ đi kèm
    `low_match_fraction`. Với ngưỡng 0,6 / 0,25 thì phép kiểm mâu thuẫn một mình quyết định FAILED."""
    odometry, rng = _still_room(OdometryConfig())
    passes, hits = odometry.counts.passes.copy(), odometry.counts.hits.copy()
    fence = np.array(_screen(STILL_POSE, 360.0, 0.6, pieces=41))          # vòng kín quanh cảm biến
    angles, ranges = raycast(STILL_POSE, np.vstack([STATIC, fence]), noise=0.01, rng=rng)
    step = odometry.update(angles, ranges, 1.0)
    assert step.status == FAILED and "conflicts_with_map" in step.reasons, step.reasons
    assert step.conflicts_short > 50 and step.conflict_fraction > 0.9           # đo 24/09/2026: 119 điểm, 1,00
    assert np.array_equal(odometry.counts.passes, passes) and np.array_equal(odometry.counts.hits, hits)
    strict = OdometryConfig(min_matched_fraction=0.6, max_conflict_fraction=0.25)
    odometry, rng = _still_room(strict)
    screen = np.array(_screen(STILL_POSE, 240.0, 0.5))
    angles, ranges = raycast(STILL_POSE, np.vstack([STATIC, screen]), noise=0.01, rng=rng)
    predicted = compose(odometry.pose, odometry.velocity)
    step = odometry.update(angles, ranges, 1.0)
    assert step.status == FAILED and step.reasons == ("conflicts_with_map",), step.reasons
    assert step.matched_fraction > 0.62 and step.conflict_fraction > 0.28      # đo: 0,670 và 0,327 (71 điểm)
    assert np.allclose(step.pose, predicted, atol=1e-12)                        # tư thế theo dự đoán


def test_peak_at_the_edge_of_the_widened_window_fails_even_if_refinement_recovers():
    """Hướng nhảy 30° giữa hai vòng (> cửa sổ tìm lại 8° × 2,5 = 20°): đỉnh ở mép cửa sổ. Tinh chỉnh vẫn trượt tới tư
    thế khớp tốt (tỉ lệ khớp ≈ 1), nhưng cổng `window_edge` một mình phải loại vòng này (quy ước thận trọng)."""
    odometry, rng = _still_room(OdometryConfig())
    predicted = compose(odometry.pose, odometry.velocity)
    angles, ranges = raycast(compose(np.array(STILL_POSE), np.array([0.0, 0.0, math.radians(30.0)])), STATIC,
                             noise=0.01, dropout=0.1, rng=rng)
    step = odometry.update(angles, ranges, 1.0)
    assert step.retried and step.status == FAILED and step.reasons == ("window_edge",), step.reasons
    assert step.matched_fraction > 0.9                                           # đo 24/09/2026: 1,000
    assert np.allclose(step.pose, predicted, atol=1e-12)


def test_small_patch_of_a_known_corner_fails_as_few_matched():
    """Chỉ còn tia ±40° hướng vào góc phòng cách ≈ 0,45 m (đủ `min_valid_beams`): sau khi tỉa một điểm mỗi ô chỉ còn
    khoảng 20 điểm, đều khớp. Cổng `few_matched` (< 30) một mình phải loại vòng này."""
    pose = (2.8, -1.85, -math.pi / 4)
    odometry, rng = _still_room(OdometryConfig(), pose=pose, n=3, seed=31)
    angles, ranges = raycast(pose, STATIC, noise=0.005, rng=rng)
    ranges = np.where(np.abs(angles) < math.radians(40.0), ranges, np.nan)
    step = odometry.update(angles, ranges, 1.0)
    assert step.status == FAILED and step.reasons == ("few_matched",), step.reasons
    # đo 24/09/2026: 111 tia dùng được, 21 điểm khớp, tỉ lệ khớp 1,00
    assert step.valid_beams >= 50 and step.matched < 30 and step.matched_fraction > 0.9


def test_lost_needs_consecutive_failures():
    """FAILED × 4, OK, FAILED × 5: vòng OK xóa bộ đếm, nên `lost` (lost_after = 5) chỉ đến ở lần FAILED liên tiếp
    thứ 5."""
    odometry, rng = _still_room(OdometryConfig())
    angles = raycast(STILL_POSE, STATIC)[0]
    blank = np.full(len(angles), np.nan)
    steps = [odometry.update(angles, blank, 1.0 + 0.1 * k) for k in range(4)]
    good_angles, good_ranges = raycast(STILL_POSE, STATIC, noise=0.01, dropout=0.1, rng=rng)
    steps.append(odometry.update(good_angles, good_ranges, 1.4))
    steps += [odometry.update(angles, blank, 1.5 + 0.1 * k) for k in range(5)]
    assert [step.status for step in steps] == [FAILED] * 4 + [OK] + [FAILED] * 5
    assert ["lost" in step.reasons for step in steps] == [False] * 9 + [True]


def test_loose_covariance_alone_gives_ambiguous_without_locking():
    """Cổng độ lệch chuẩn tách khỏi cổng pháp tuyến: cảnh không suy biến nhưng ngưỡng độ lệch chuẩn chặt hơn độ lệch
    chuẩn đo được thì AMBIGUOUS/`degenerate`, không khóa trục nào."""
    for config in (OdometryConfig(max_std_xy_m=1e-5), OdometryConfig(max_std_theta_deg=1e-4)):
        odometry, rng = _still_room(config, n=1)
        angles, ranges = raycast(STILL_POSE, STATIC, noise=0.01, dropout=0.1, rng=rng)
        step = odometry.update(angles, ranges, 1.0)
        assert step.status == AMBIGUOUS and step.reasons == ("degenerate",) and not step.locked, step.reasons
        # đo 24/09/2026: tỉ số pháp tuyến 0,95 trên 201 pháp tuyến; độ lệch chuẩn 1,7 mm và 0,04°
        assert step.normal_ratio > config.min_normal_ratio and step.normals >= config.min_normals


def test_few_surface_normals_do_not_trigger_the_geometric_lock():
    """Cảnh chỉ có cột mảnh (không cho pháp tuyến) và một đoạn tường ngắn: ít pháp tuyến, đều song song (tỉ số ≈ 0).
    Dưới `min_normals` = 20 thì không xét suy biến theo hình học: các cột ràng buộc đủ mọi hướng, phải OK, không
    khóa."""
    rng = np.random.default_rng(40)
    posts = []
    for k in range(24):
        a, rad = 2 * math.pi * k / 24 + 0.1, 1.0 + 0.2 * ((k * 7) % 5)
        posts += disc(rad * math.cos(a), rad * math.sin(a), 0.03, sides=8)
    scene = np.array(posts + [(1.8, -0.2, 1.8, 0.2)], np.float64)
    odometry = ScanOdometry(OdometryConfig())
    for k in range(4):
        angles, ranges = raycast((0.0, 0.0, 0.0), scene, noise=0.003, rng=rng)
        odometry.update(angles, ranges, 0.1 * k)
    later = odometry.steps[1:]
    assert all(0 < step.normals < 20 and step.normal_ratio < 0.04 for step in later)   # đo 24/09/2026: 8; ≤ 0,0008
    assert all(step.status == OK and not step.locked for step in later)


# --- dữ liệu thật (bỏ qua nếu máy không có DROW v2) -----------------------------------------------------------------

def test_drow_corridor_slowdown_does_not_fail_with_the_soft_lock():
    """DROW v2 `run_2015-11-25-10-34-20-c`, vòng 300–859 (26,7 m theo odometry DROW, không phải ground truth). Trên bản
    khóa cứng 24/09/2026: 358 vòng FAILED, lạc từ vòng ≈ 490, đoạn 5 m lệch trung vị 98,9 %. Đo 24/09/2026 (tối, sau
    khi sửa, máy bàn): 0 FAILED, 149 AMBIGUOUS, lệch cuối 0,56 m (2,1 %), đoạn 5 m trung vị 1,60 %, tỉ lệ bước 1,007."""
    path = DROW_DIR / "val" / "run_2015-11-25-10-34-20-c.bag.csv"
    if not (path.exists() and path.with_suffix(".odom2").exists()):
        pytest.skip("không có DROW v2 (datasets/drow/DROWv2-data)")
    from autopark.lidar.drow import drow_angles, read_drow_csv
    from autopark.lidar.drow_odom import read_drow_odom

    recording, odom, angles = read_drow_csv(path), read_drow_odom(path.with_suffix(".odom2")), drow_angles()
    indices = list(range(300, 860))
    odometry = run_sequence(((angles, recording.ranges[i], float(recording.t[i] - recording.t[0])) for i in indices),
                            OdometryConfig())
    assert odometry.summary()["failed"] == 0
    report = compare_trajectories(odometry.poses(), odom.xya[indices])
    assert report["path_ref_m"] == pytest.approx(26.7, abs=0.1)
    assert report["end"]["translation_pct_of_path"] < 6.0
    assert report["segments"]["5"]["translation_pct"]["median"] < 4.0
    assert report["step_ratio"] == pytest.approx(1.0, abs=0.05)
