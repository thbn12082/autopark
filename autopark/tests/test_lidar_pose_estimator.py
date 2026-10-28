"""Bộ ghép định vị LiDAR (a) + (b) (lidar/pose_estimator.py, T2, thêm 02/10/2026) trên vòng quét tổng hợp có quỹ đạo
biết trước, và trên dữ liệu thật khi máy có (bỏ qua khi thiếu).

Cảnh tổng hợp: sa bàn 3 × 2 m trong phòng không đối xứng, 3 hộp, 2 vật di động không có trong bản đồ, nhiễu 1 cm,
10 % tia mất phản hồi, 500 tia/vòng, 10 Hz (tests/lidar_fakes.py). Mọi ngưỡng của bộ ghép là ĐỀ XUẤT – CHỜ CHỐT
(configs/dinh_vi_lidar_v0.json). Cận trong test rộng hơn số đo lúc viết test (02/10/2026, máy bàn đang có tải khác)
khoảng 2–5 lần; số đo ghi cạnh từng cận."""
from dataclasses import replace
import csv
import json
import math
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from autopark.domain.types import Pose  # noqa: E402
from autopark.lidar.localize import localize  # noqa: E402
from autopark.lidar.map_builder import MapBuildConfig, PlacementSpec, build_static_map  # noqa: E402
from autopark.lidar.pose_config import CrossCheck, LidarMount  # noqa: E402
from autopark.lidar.pose_estimator import (INIT, LATCHED, POSE_DISAGREE, POSE_LOST, POSE_UNCHECKED,  # noqa: E402
                                           TRACKING, LidarPoseEstimator, cross_check, main)
from autopark.lidar.scan_odometry import FAILED as ODO_FAILED, OdometryStep  # noqa: E402
from autopark.lidar.synthetic import drive  # noqa: E402
from tests.lidar_fakes import (CAR, OTHER_ROOM, STATIC, SYMMETRIC_ROOM, build_map, default_config, movers,  # noqa: E402
                               scan_at, scan_obj, scene, static_slice, write_recording)

PROJECT = Path(__file__).resolve().parents[1]
RUNS = PROJECT / "runs"
DROW_DIR = PROJECT / "datasets" / "drow" / "DROWv2-data"
START = (0.5, 1.0, 0.0)
# Đỗ có đổi chiều ở 0,12 m/s: đứng 0,5 s, tiến 0,6 m, rẽ trái, dừng, lùi thẳng, lùi rẽ phải
MANOEUVRE = [(0.0, 0.0, 5), (0.12, 0.0, 50), (0.12, 0.25, 30), (0.0, 0.0, 5), (-0.12, 0.0, 30), (-0.12, -0.3, 20)]


@pytest.fixture(scope="module")
def config():
    return default_config()


@pytest.fixture(scope="module")
def lmap():
    return build_map()


def estimator(lmap, config, **kwargs):
    kwargs.setdefault("hint", Pose(*START))
    return LidarPoseEstimator(lmap, kwargs.pop("params", config.localizer), mount=config.mount,
                              odometry=kwargs.pop("odometry", config.odometry), self_mask=kwargs.pop("self_mask", CAR),
                              **kwargs)


def run(est, truth, rng, *, mount, t0=0.0, period=0.1, n_movers=2, segments=STATIC, skip=(), arm_when_tracking=True,
        beams=500, segments_at=None):
    """Đưa từng vòng quét của quỹ đạo `truth` (tư thế XE) vào bộ ghép; `skip`: chỉ số vòng bị rơi."""
    steps = []
    for k, pose in enumerate(truth):
        t = t0 + k * period
        if k in skip:
            continue
        segs = segments_at(k) if segments_at is not None else segments
        if n_movers:
            segs = np.vstack([segs, movers(t, n_movers)])
        vehicle = Pose(*pose)
        steps.append(est.process(*scan_at(mount.sensor_pose(vehicle), rng, segments=segs, beams=beams), t,
                                 truth=vehicle))
        if arm_when_tracking and est.state == TRACKING and not est.armed:
            est.arm()
    return steps


def errors(steps):
    ok = [s for s in steps if s.decision == "OK"]
    pos = np.array([math.hypot(s.vehicle.x - s.truth.x, s.vehicle.y - s.truth.y) for s in ok])
    yaw = np.array([abs(math.degrees(math.atan2(math.sin(s.vehicle.yaw - s.truth.yaw),
                                                math.cos(s.vehicle.yaw - s.truth.yaw)))) for s in ok])
    return pos, yaw


# ---- quỹ đạo tổng hợp ----------------------------------------------------------------------------------------------
def test_tracks_a_parking_manoeuvre_with_cusps_in_a_sa_ban_room(lmap, config):
    """Đo 02/10/2026: 2 vòng INIT rồi 139/139 OK; sai số xe trung vị 4,2 mm, lớn nhất 7,0 mm, hướng ≤ 0,14°; kiểm chéo
    dùng ở 138/138 vòng sau vòng xác nhận."""
    truth = drive(START, MANOEUVRE)
    est = estimator(lmap, config)
    steps = run(est, truth, np.random.default_rng(1), mount=config.mount)
    first_ok = next(k for k, s in enumerate(steps) if s.decision == "OK")
    assert first_ok == config.localizer.init_confirm_scans - 1
    after = steps[first_ok:]
    assert all(s.decision == "OK" for s in after), [(s.n, s.decision, s.reason_vi) for s in after if s.decision != "OK"]
    assert not any(s.stopped for s in steps)
    pos, yaw = errors(after)
    assert np.median(pos) < 0.01 and pos.max() < 0.03 and yaw.max() < 1.0
    assert sum(s.check_used for s in after[1:]) >= 0.95 * len(after[1:])
    assert not any(p > 0.06 or y > 4.0 for p, y in zip(pos, yaw))      # không có "OK sai"
    assert est.global_searches == 0 and est.armed


def test_one_bad_scan_is_tolerated_two_latch_pose_lost(lmap, config):
    truth = drive(START, [(0.0, 0.0, 30)])
    other = scene(OTHER_ROOM, [])
    k = 12
    est = estimator(lmap, config)
    rng = np.random.default_rng(2)
    steps = run(est, truth[:k], rng, mount=config.mount)
    assert est.state == TRACKING and est.armed
    before = est.published()
    bad = run(est, truth[k:k + 1], rng, mount=config.mount, t0=k * 0.1, segments=other, n_movers=0)[0]
    assert bad.decision == "BAD" and est.published() is before            # mẫu cũ giữ nguyên, stamp tiếp tục già
    assert est.published().t == pytest.approx((k - 1) * 0.1) and est.bad_run == 1
    lost = run(est, truth[k + 1:k + 2], rng, mount=config.mount, t0=(k + 1) * 0.1, segments=other, n_movers=0)[0]
    assert lost.decision == POSE_LOST and est.state == LATCHED
    pub = est.published()
    assert pub.status == POSE_LOST and pub.t == pytest.approx((k + 1) * 0.1)
    assert "không OK 2 vòng liên tiếp" in pub.reason_vi and "FAILED" in pub.reason_vi
    # Đang chạy: chốt giữ dù cảnh đã đúng lại
    later = run(est, truth[k + 2:k + 20], rng, mount=config.mount, t0=(k + 2) * 0.1, arm_when_tracking=False)
    assert {s.decision for s in later} == {"LATCHED"} and est.published().status == POSE_LOST
    # Hết lần chạy: sau relatch_s tự khởi tạo lại rồi bắt lại
    est.disarm()
    again = run(est, truth[:10], rng, mount=config.mount, t0=4.0, arm_when_tracking=False)
    assert again[0].decision in ("INIT", "LATCHED") and again[-1].decision == "OK" and est.state == TRACKING
    assert steps[-1].decision == "OK"


def test_wrong_peak_jump_is_caught_as_disagreement(lmap, config):
    truth = drive(START, [(0.0, 0.0, 6), (0.12, 0.0, 20)])

    def shifted(offset, at):
        count = {"n": 0}

        def localize_fn(lmap_, angles, ranges, initial=(0.0, 0.0, 0.0), **kwargs):
            result = localize(lmap_, angles, ranges, initial, **kwargs)
            count["n"] += 1
            if count["n"] >= at and result.ok:
                result.x += offset                    # (a) "nhảy" sang đỉnh lệch offset theo x
            return result

        return localize_fn

    est = estimator(lmap, config, localize_fn=shifted(0.10, 15))
    steps = run(est, truth, np.random.default_rng(3), mount=config.mount)
    codes = [s.decision for s in steps]
    assert POSE_DISAGREE in codes and est.state == LATCHED
    first = steps[codes.index(POSE_DISAGREE)]
    assert first.n == 14 and first.check.disagree and abs(first.check.dx) > first.check.tol_m
    assert "lệch" in est.published().reason_vi
    est2 = estimator(lmap, config, localize_fn=shifted(0.02, 15))
    steps2 = run(est2, truth, np.random.default_rng(3), mount=config.mount)
    assert all(s.decision in ("INIT", "OK") for s in steps2) and est2.state == TRACKING


def test_cross_check_ignores_the_degenerate_axis_of_b():
    """Hàm thuần: (b) khóa trục suy biến u (hệ odometry). Lệch 10 cm dọc u bị bỏ qua; lệch 10 cm ngang u bị bắt. Mốc
    (a) quay 90° so với hệ (b), nên u = +x (odometry) là +y trên bản đồ."""
    cc = CrossCheck()
    anchor_a = np.array([1.0, 1.0, math.pi / 2])
    anchor_b = np.array([0.0, 0.0, 0.0])
    b_pose = np.array([0.5, 0.0, 0.0])                          # (b): đi 0,5 m theo +x của nó
    pred = np.array([1.0, 1.5, math.pi / 2])                    # = a_i ⊕ (b_i⁻¹ ⊕ b)
    along = pred + np.array([0.0, 0.10, 0.0])                   # lệch dọc u (trên bản đồ: +y)
    across = pred + np.array([0.10, 0.0, 0.0])
    free = cross_check(anchor_a, anchor_b, b_pose, along, cc)
    assert free.disagree and not free.axis_dropped and free.travel_m == pytest.approx(0.5)
    assert free.tol_m == pytest.approx(0.04 + 0.03 * 0.5) and free.tol_deg == pytest.approx(2.0 + 2.0 * 0.5)
    locked = cross_check(anchor_a, anchor_b, b_pose, along, cc, locked=True, axis=(1.0, 0.0))
    assert locked.axis_dropped and not locked.disagree and math.hypot(locked.dx, locked.dy) < 1e-9
    caught = cross_check(anchor_a, anchor_b, b_pose, across, cc, locked=True, axis=(1.0, 0.0))
    assert caught.disagree and caught.dx == pytest.approx(0.10)
    turned = cross_check(anchor_a, anchor_b, b_pose, pred + np.array([0.0, 0.0, math.radians(4)]), cc)
    assert turned.disagree and turned.dyaw_deg == pytest.approx(4.0)


class FailingOdometry:
    """(b) luôn hỏng: không kiểm chéo được vòng nào."""

    def __init__(self, config=None):
        self.n = 0

    def update(self, angles, ranges, t=None):
        self.n += 1
        return OdometryStep(self.n, float(t), ODO_FAILED, ("few_matched",), 0.0, 0.0, 0.0, (0.0, 0.0, 0.0))


def test_unchecked_scans_latch_pose_unchecked_only_when_armed(lmap, config):
    truth = drive(START, [(0.0, 0.0, 20)])
    rng = np.random.default_rng(4)
    est = estimator(lmap, config, odometry_factory=FailingOdometry)
    steps = run(est, truth, rng, mount=config.mount, arm_when_tracking=False)
    assert est.state == TRACKING and est.anchor is None and est.unchecked_run >= 10
    assert all(s.decision in ("INIT", "OK") for s in steps) and not any(s.check_used for s in steps)
    problems, _ = est.health(2.0, [0.1 * k for k in range(21)])
    assert any("chưa có mốc kiểm chéo" in p for p in problems)          # START bị từ chối trước khi chạy
    est.arm()
    step = run(est, truth[:1], rng, mount=config.mount, t0=2.1, arm_when_tracking=False)[0]
    assert step.decision == POSE_UNCHECKED and est.state == LATCHED
    assert "không kiểm chéo được" in est.published().reason_vi


def test_time_based_velocity_survives_dropped_scans(lmap, config):
    """Vòng bị rơi trước khi tới bộ ghép (mỗi vòng thứ hai, rồi 30 % ngẫu nhiên), 0,25 m/s. Cửa sổ (b) thu còn ±4 cm để
    lộ sai số dự đoán: theo vòng, sau một khoảng hở dài hơn khoảng trước, dự đoán thiếu đúng phần quãng đi đó. Đo
    02/10/2026: rơi đều cho 1 / 1 lần (b) tìm lại (khoảng hở đều nên "theo vòng" cũng đúng, trừ lúc bắt đầu rơi); rơi
    ngẫu nhiên cho 0 lần theo giây, 11 lần theo vòng. Mọi vòng sau khởi tạo vẫn OK nhờ (a)."""
    truth = drive(START, [(0.0, 0.0, 5), (0.25, 0.0, 40), (0.25, 0.4, 20)])
    rng = np.random.default_rng(5)
    patterns = (set(range(6, len(truth), 2)), {k for k in range(6, len(truth)) if rng.random() < 0.3})
    for n, skip in enumerate(patterns):
        retries = {}
        for basis in ("second", "scan"):
            odometry = replace(config.odometry, velocity_per=basis, window_x_m=0.04, window_y_m=0.04)
            est = estimator(lmap, config, odometry=odometry)
            steps = run(est, truth, np.random.default_rng(6), mount=config.mount, skip=skip, n_movers=0)
            after = steps[next(k for k, s in enumerate(steps) if s.decision == "OK"):]
            assert all(s.decision == "OK" for s in after), (basis, [s.reason_vi for s in after if s.decision != "OK"])
            retries[basis] = sum(s.b_retried for s in steps)
        assert retries["second"] <= retries["scan"], retries
        if n == 1:
            assert retries["second"] < retries["scan"], retries


def test_init_uses_start_hint_then_global_search_and_rejects_ambiguous_rooms(lmap, config):
    truth = drive((1.4, 1.3, 0.6), [(0.0, 0.0, 6)])
    est = estimator(lmap, config, hint=Pose(0.4, 1.3, 0.6))              # gợi ý lệch 1 m: cửa sổ ±0,5 m không tới
    steps = run(est, truth, np.random.default_rng(7), mount=config.mount, arm_when_tracking=False, n_movers=0)
    assert steps[0].a_window == "global" and est.global_searches == 1
    assert [s.decision for s in steps[:3]] == ["INIT", "INIT", "OK"] and est.state == TRACKING
    assert steps[2].vehicle.distance_to(Pose(*truth[2])) < 0.02
    # Phòng chữ nhật trống: tìm toàn cục ra hai đỉnh đối xứng → AMBIGUOUS, không bao giờ công bố
    room = scene(SYMMETRIC_ROOM, [])
    sym = build_map([(1.5, 1.0, 0.0), (0.7, 0.6, 1.0), (2.3, 1.4, 2.0)], segments=room)
    est2 = estimator(sym, config, hint=Pose(0.4, 1.3, 0.6),
                     params=replace(config.localizer, global_retry_s=0.25))
    steps2 = run(est2, truth, np.random.default_rng(8), mount=config.mount, segments=room, n_movers=0,
                 arm_when_tracking=False)
    assert est2.global_searches >= 2 and est2.published() is None and est2.state == INIT
    assert all(s.decision == "INIT" for s in steps2)
    assert any("AMBIGUOUS" in s.reason_vi for s in steps2)


def test_no_global_search_while_armed(lmap, config):
    truth = drive(START, [(0.0, 0.0, 12)])
    rng = np.random.default_rng(9)
    est = estimator(lmap, config)
    run(est, truth[:8], rng, mount=config.mount)
    assert est.armed and est.global_searches == 0
    other = scene(OTHER_ROOM, [])
    run(est, truth[8:12], rng, mount=config.mount, t0=0.8, segments=other, n_movers=0)
    assert est.state == LATCHED and est.global_searches == 0
    est.reset_feed("ngắt LiDAR")                                          # đang chạy: vẫn chốt, không khởi tạo lại
    assert est.state == LATCHED and est.published().status == POSE_LOST


def test_reset_feed_while_armed_latches_pose_lost_and_resets_when_idle(lmap, config):
    truth = drive(START, [(0.0, 0.0, 8)])
    est = estimator(lmap, config)
    run(est, truth, np.random.default_rng(10), mount=config.mount)
    est.reset_feed("đổi chiều góc")
    assert est.state == LATCHED and est.published().status == POSE_LOST
    assert "LiDAR ngắt/đổi chiều góc giữa lần chạy" in est.published().reason_vi
    est.disarm()
    est.reset_feed("ngắt LiDAR")
    assert est.state == INIT and est.published() is None and est.anchor is None


def test_start_health_problems_are_vietnamese(lmap, config):
    truth = drive(START, [(0.0, 0.0, 12)])
    est = estimator(lmap, config)
    steps = run(est, truth, np.random.default_rng(11), mount=config.mount, arm_when_tracking=False)
    received = [0.1 * k for k in range(12)]
    for s in steps:
        s.t_done = s.t + 0.02
    assert est.health(1.1, received) == ([], [])
    problems, _ = est.health(1.1, received[::2])                          # 5 Hz
    assert any("vòng/s" in p for p in problems)
    for s in steps[-3:]:
        s.t_done = s.t + 0.07                                            # p95 > 50 ms: cảnh báo
    assert est.health(1.1, received)[1] and not est.health(1.1, received)[0]
    for s in steps[-3:]:
        s.t_done = s.t + 0.2                                             # p95 > 100 ms: từ chối
    assert any("chậm" in p for p in est.health(1.1, received)[0])
    young = estimator(lmap, config)
    run(young, truth[:4], np.random.default_rng(12), mount=config.mount, arm_when_tracking=False)
    problems, _ = young.health(0.3, received[:4])
    assert any("vòng định vị OK liên tiếp" in p for p in problems)
    assert any("vòng/s" in p for p in young.health(0.1, received[:1])[0])


def test_self_mask_drops_body_returns(lmap, config):
    """Dây cáp/thân xe ngay trước cảm biến (trong thân xe nới 3 cm) bị bỏ trước (a) và (b)."""
    est = estimator(lmap, config)
    angles = np.radians(np.arange(-180, 180, 1.0))
    ranges = np.full(len(angles), 2.0)
    ranges[:10] = 0.06                    # sau cảm biến 6 cm: vẫn trong thân xe (gá 9,5 cm trước trục sau)
    ranges[180:185] = 0.12                # trước cảm biến 12 cm: trong mũi xe
    masked = est._mask(angles, ranges)
    assert np.isnan(masked[:10]).all() and np.isnan(masked[180:185]).all()
    assert np.isfinite(masked[10:180]).all() and masked[90] == 2.0     # tia xa (ngoài thân) giữ nguyên
    bare = estimator(lmap, config, self_mask=None)
    assert bare._mask(angles, ranges) is ranges


# ---- CLI offline ---------------------------------------------------------------------------------------------------
def test_cli_writes_localization_csv_summary_overlay_and_same_scans_as_reproduces_rows(config, tmp_path):
    folder = tmp_path / "định vị thử"
    rng = np.random.default_rng(13)
    sensor0 = config.mount.sensor_pose(Pose(*START))
    still = static_slice((sensor0.x, sensor0.y, sensor0.yaw), 4.0, rng)
    map_rec = write_recording(folder / "chỗ đặt 1", still)
    result = build_static_map([PlacementSpec(map_rec)], anchor=(sensor0.x, sensor0.y, sensor0.yaw),
                              config=MapBuildConfig(skip_seconds=0.0))
    from autopark.lidar.map_builder import write_map

    write_map(result, folder / "bản đồ")
    truth = drive(START, [(0.0, 0.0, 30), (0.1, 0.0, 30)])
    scans = []
    for k, pose in enumerate(truth):
        sensor = config.mount.sensor_pose(Pose(*pose))
        scans.append((*scan_at((sensor.x, sensor.y, sensor.yaw), rng), 100.0 + 0.1 * k))
    rec = write_recording(folder / "lần chạy", scans)
    out1, out2 = folder / "kết quả 1", folder / "kết quả 2"
    args = ["--map", str(folder / "bản đồ"), "--recording", str(rec), "--initial", "0.5", "1.0", "0",
            "--skip-seconds", "0", "--vehicle-config", str(PROJECT / "configs" / "vehicle_default.json")]
    assert main(args + ["--out", str(out1), "--drop-every", "2"]) == 0
    for name in ("localization.csv", "pose_estimator.json", "overlay.png"):
        assert (out1 / name).is_file(), name
    report = json.loads((out1 / "pose_estimator.json").read_text(encoding="utf-8"))
    summary = report["summary"]
    kept = (len(truth) + 1) // 2                                          # bỏ mỗi vòng thứ hai: 31 trong 61
    assert summary["scans"] == kept and summary["first_stop"] is None and summary["decisions"]["OK"] >= kept - 3
    rows1 = list(csv.DictReader((out1 / "localization.csv").open(encoding="utf-8")))
    assert len(rows1) == kept and all(int(r["dropped_before"]) == (0 if k == 0 else 1) for k, r in enumerate(rows1))
    assert rows1[-1]["phase"] == "run" and rows1[0]["phase"] == "before_start"
    assert main(args + ["--out", str(out2), "--same-scans-as", str(out1 / "localization.csv")]) == 0
    rows2 = list(csv.DictReader((out2 / "localization.csv").open(encoding="utf-8")))
    assert [r["t_perf_scan"] for r in rows2] == [r["t_perf_scan"] for r in rows1]
    for a, b in zip(rows1, rows2):
        assert a["decision"] == b["decision"]
        for key in ("vehicle_x", "vehicle_y", "vehicle_yaw_deg"):
            if a[key]:
                assert abs(float(a[key]) - float(b[key])) <= 1e-9
    with pytest.raises(SystemExit) as info:
        main(args + ["--out", str(folder / "x"), "--drop-every", "1"])
    assert info.value.code == 2


def test_match_scan_times_takes_the_one_scan_within_tolerance():
    """`--same-scans-as` (sửa sau rà soát 02/10/2026): dòng của phiên mang t_perf của ScanReader, lệch t của bản ghi vài
    µs; ghép với vòng DUY NHẤT trong dung sai, đúng thứ tự, trả độ lệch. Không có vòng, nhiều vòng, hai dòng cùng một
    vòng, dòng lùi thời gian, bản ghi rỗng → ValueError tiếng Việt kèm số dòng."""
    from autopark.lidar.pose_estimator import SAME_SCANS_TOLERANCE_S, match_scan_times

    assert SAME_SCANS_TOLERANCE_S == pytest.approx(0.010)
    t_rec = [100.0, 100.1, 100.2, 100.3, 100.4]
    idx, gaps = match_scan_times(t_rec, [100.0 - 4e-6, 100.2 - 23.8e-6, 100.4])     # lệch như đo lúc rà soát
    assert idx == [0, 2, 4] and gaps.tolist() == pytest.approx([4e-6, 23.8e-6, 0.0], abs=1e-9)
    assert match_scan_times(t_rec, [100.1 - 0.009])[0] == [1]                      # 9 ms: vẫn trong dung sai
    with pytest.raises(ValueError, match=r"localization.csv dòng 1: vòng t_perf_scan = 100.15 không có trong bản ghi "
                                         r"\(vòng gần nhất lệch 50.000 ms, dung sai 10 ms; bản ghi có 5 vòng"):
        match_scan_times(t_rec, [100.15])
    with pytest.raises(ValueError, match="dòng 2: vòng .* không có trong bản ghi"):
        match_scan_times(t_rec, [100.1, 100.2 + 0.011])
    with pytest.raises(ValueError, match="dòng 1: 2 vòng của bản ghi .* dung sai quá rộng"):
        match_scan_times(t_rec, [100.05], 0.06)
    with pytest.raises(ValueError, match=r"dòng 2: ghép vào vòng 1 .*\(hai dòng cùng một vòng"):
        match_scan_times(t_rec, [100.1, 100.1 + 2e-6])
    with pytest.raises(ValueError, match="dòng 2: ghép vào vòng 0 .* không sau vòng 2"):
        match_scan_times(t_rec, [100.2, 100.0])
    with pytest.raises(ValueError, match="bản ghi không có vòng nào"):
        match_scan_times([], [1.0])
    with pytest.raises(ValueError, match="dung sai"):
        match_scan_times(t_rec, [100.0], 0.0)
    assert match_scan_times([], [])[0] == []


class _C1Gia:
    """Nguồn giả kiểu `RplidarC1Source` mở với RIG_CLOCK (như ngăn LiDAR): stamp = now() lúc vòng tới, `t0`,
    `last_revolution.t_first`; một vòng sau ít nhất 30 ms. `now()` đọc đồng hồ sau ≈ 20 µs bận (như driver bận / luồng
    đọc bị chen giữa hai lần đọc đồng hồ; rà soát 02/10/2026 đo tới 23,8 µs), nên t_perf của ScanReader chắc chắn lệch
    stamp + t0 của bản ghi hơn 1 µs."""

    source_id = "c1_gia"

    def __init__(self, scans, clock):
        self.clock, self.t0 = clock, clock()
        self.scans = list(scans)
        self.last_revolution = None
        self.last_quality = None

    def now(self) -> float:
        import time

        het = time.perf_counter() + 20e-6
        while time.perf_counter() < het:
            pass
        return max(0.0, self.clock() - self.t0)

    def read(self):
        import time
        from types import SimpleNamespace

        from autopark.lidar.live_view import ScanStreamEnded

        if not self.scans:
            raise ScanStreamEnded("hết vòng giả")
        time.sleep(0.030)
        angles, ranges = self.scans.pop(0)
        stamp = max(0.0, self.clock() - self.t0)
        self.last_revolution = SimpleNamespace(t_first=stamp - 0.09)
        return scan_obj(angles, ranges, stamp, self.source_id)


def test_same_scans_as_live_localization_csv_against_session_recording_parts(config, tmp_path, capsys):
    """DV-3 / tái hiện (sửa sau rà soát 02/10/2026): localization.csv do chính `LidarPoseSource` ghi trong phiên (t_perf
    của `ScanReader`, lệch µs so với bản ghi) và bản ghi phiên T3 (`LidarTap` → `RigRecorder`, LiDAR chia 4 phần) cùng
    lấy từ MỘT luồng đọc. `--recording <thư mục> --same-scans-as` ghép được mọi dòng, giữ nguyên t_perf_scan, báo độ
    lệch; bộ ghép offline ra đúng quyết định và tư thế của phiên (cùng t, cùng vòng). localization.csv chỉ còn đuôi
    (bộ ghép offline khởi tạo lại): vẫn chạy, tư thế OK gần tư thế của phiên. Dòng lệch quá dung sai → mã 2."""
    pytest.importorskip("PySide6")                       # lidar.live_view (ScanReader) nhập Qt
    import queue

    from autopark.application.lidar_pose_source import LidarPoseSource
    from autopark.lidar.live_view import ScanReader, ScanStreamEnded
    from autopark.lidar.localize import load_map
    from autopark.lidar.map_builder import write_map
    from autopark.lidar.pose_estimator import write_localization_csv
    from autopark.lidar.recording import read_lidar_any
    from autopark.rig.recording import LidarTap, RigRecorder
    from autopark.storage.scenario_store import load_vehicle_config
    from autopark.video.multicam import RIG_CLOCK

    folder = tmp_path / "tái hiện"
    rng = np.random.default_rng(14)
    sensor0 = config.mount.sensor_pose(Pose(*START))
    still = static_slice((sensor0.x, sensor0.y, sensor0.yaw), 4.0, rng)
    result = build_static_map([PlacementSpec(write_recording(folder / "chỗ đặt 1", still))],
                              anchor=(sensor0.x, sensor0.y, sensor0.yaw), config=MapBuildConfig(skip_seconds=0.0))
    write_map(result, folder / "bản đồ")
    vehicle_path = PROJECT / "configs" / "vehicle_default.json"
    truth = drive(START, [(0.0, 0.0, 10), (0.1, 0.0, 30)])                 # 41 vòng: đứng yên rồi tiến chậm
    scans = []
    for pose in truth:
        sensor = config.mount.sensor_pose(Pose(*pose))
        angles, ranges = scan_at((sensor.x, sensor.y, sensor.yaw), rng)
        # số float32 đúng như bản ghi lưu: bộ ghép trong phiên và offline nhận cùng một vòng quét
        scans.append(tuple(np.asarray(v, np.float32).astype(np.float64) for v in (angles, ranges)))

    # phiên: luồng đọc của ngăn LiDAR = ScanReader(LidarTap(nguồn)), người tiêu thụ = nguồn tư thế LiDAR
    estimator = LidarPoseEstimator(load_map(folder / "bản đồ", config.localize), config.localizer, mount=config.mount,
                                   odometry=config.odometry, self_mask=load_vehicle_config(vehicle_path),
                                   hint=Pose(*START))
    source = LidarPoseSource(estimator, config, map_info={}, threaded=False)
    started = []

    class Consumer:
        def on_scan(self, scan, quality, t_first_perf, t_perf):
            source.on_scan(scan, quality, t_first_perf, t_perf)
            source.pump()
            if estimator.state == TRACKING and not started:              # bấm Bắt đầu đỗ ngay khi bắt được
                source.run_started()
                started.append(t_perf)

    recording_dir = folder / "phiên 20261002"
    recorder = RigRecorder(recording_dir, ports=[], lidar=True, lidar_scans_per_part=12).start()
    reader = ScanReader(LidarTap(_C1Gia(scans, RIG_CLOCK), lambda: recorder, RIG_CLOCK, ignore=(ScanStreamEnded,)),
                        queue.Queue(), [Consumer()])
    reader.start()
    reader.join(120.0)
    assert not reader.is_alive()
    assert recorder.stop(wait=True, timeout=10.0)["state"] == "xong"
    assert len(sorted((recording_dir / "lidar").glob("part_*.npz"))) == 4                # 12 + 12 + 12 + 5
    rows = source.log_rows()
    assert started and len(rows) == len(truth) and rows[0]["n"] == 0                   # 3 dòng before_start + 38
    live_csv = write_localization_csv(folder / "phiên.csv", rows)
    t_rec = read_lidar_any(recording_dir).t
    gaps = [row["t_perf_scan"] - t for row, t in zip(rows, t_rec)]
    assert max(gaps) < -1e-6                     # t_perf sớm hơn stamp + t0 vài chục µs: cách cũ (≤ 1 µs) từ chối

    args = ["--map", str(folder / "bản đồ"), "--recording", str(recording_dir), "--initial", "0.5", "1.0", "0",
            "--vehicle-config", str(vehicle_path), "--same-scans-as"]
    out = folder / "định vị lại"
    assert main(args + [str(live_csv), "--out", str(out)]) == 0
    report = json.loads((out / "pose_estimator.json").read_text(encoding="utf-8"))
    same = report["summary"]["same_scans"]
    assert same["rows"] == len(rows) and same["tolerance_s"] == pytest.approx(0.010)
    assert 1e-6 < same["max_gap_s"] < 0.010 and 1e-6 < same["median_gap_s"] <= same["max_gap_s"]
    assert (report["recording_kind"], report["recording_sha256"], report["recording_scans"]) == ("session_folder",
                                                                                                    None, len(truth))
    assert [p["file"] for p in report["recording_parts"]] == [f"lidar/part_{k:04d}.npz" for k in range(4)]
    assert all(len(p["sha256"]) == 64 for p in report["recording_parts"])
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["same_scans"]["rows"] == len(rows)
    again = list(csv.DictReader((out / "localization.csv").open(encoding="utf-8")))
    timing = {"t_done_perf", "latency_ms", "a_ms", "b_ms"}                # thời gian thật: khác giữa hai lần
    assert len(again) == len(rows)
    for live, offline in zip(rows, again):
        assert (offline["t_perf_scan"], offline["t_first_perf"]) == (repr(live["t_perf_scan"]),
                                                                    repr(live["t_first_perf"]))
        for key in set(live) - timing:
            a, b = live[key], offline[key]
            if isinstance(a, float):
                assert abs(a - float(b)) <= 1e-9, (live["n"], key, a, b)
            else:
                assert str(a) == b, (live["n"], key, a, b)
    assert {r["decision"] for r in again} == {"INIT", "OK"} and sum(r["decision"] == "OK" for r in again) >= 35

    # chỉ còn đuôi của localization.csv (như 5 dòng before_start của một lần đứng chờ lâu): offline khởi tạo lại
    tail_csv = write_localization_csv(folder / "đuôi.csv", rows[8:])
    out_tail = folder / "định vị lại đuôi"
    assert main(args + [str(tail_csv), "--out", str(out_tail)]) == 0
    tail = list(csv.DictReader((out_tail / "localization.csv").open(encoding="utf-8")))
    assert [r["t_perf_scan"] for r in tail] == [repr(r["t_perf_scan"]) for r in rows[8:]]
    assert [r["decision"] for r in tail[:2]] == ["INIT", "INIT"] and {r["decision"] for r in tail[2:]} == {"OK"}
    for live, offline in zip(rows[8 + 2:], tail[2:]):
        assert math.hypot(live["vehicle_x"] - float(offline["vehicle_x"]),
                          live["vehicle_y"] - float(offline["vehicle_y"])) < 0.01
        assert abs(live["vehicle_yaw_deg"] - float(offline["vehicle_yaw_deg"])) < 0.5

    # một dòng nằm giữa hai vòng của bản ghi (≥ 15 ms mỗi bên: không phải vòng nào): mã 2, nói rõ dòng nào; dung sai
    # 1 µs (như trước khi sửa): mã 2 ngay dòng đầu
    assert t_rec[6] - t_rec[5] > 0.030
    shifted = [dict(r) for r in rows]
    shifted[5]["t_perf_scan"] = float(t_rec[5] + t_rec[6]) / 2.0
    bad_csv = write_localization_csv(folder / "lệch.csv", shifted)
    for extra, text in (([str(bad_csv)], "lệch.csv dòng 6: vòng t_perf_scan"),
                        ([str(live_csv), "--same-scans-tolerance-ms", "0.001"], "phiên.csv dòng 1: vòng t_perf_scan"),
                        ([str(live_csv), "--same-scans-tolerance-ms", "60"], "(0; 50] ms")):
        with pytest.raises(SystemExit) as info:
            main(args + extra + ["--out", str(folder / "hỏng")])
        assert info.value.code == 2 and text in capsys.readouterr().err, extra
    with pytest.raises(SystemExit) as info:
        main(args[:-1] + ["--same-scans-tolerance-ms", "5", "--out", str(folder / "hỏng")])
    assert info.value.code == 2 and "chỉ dùng với --same-scans-as" in capsys.readouterr().err
    assert not (folder / "hỏng").exists()


# ---- dữ liệu thật (bỏ qua nếu máy không có) ------------------------------------------------------------------------
def _c1_map_from(recording, t1: float, tmp_path, name: str, skip: float = 3.0):
    spec = PlacementSpec(recording, None, t1)
    result = build_static_map([spec], anchor=(0.0, 0.0, 0.0), config=MapBuildConfig(skip_seconds=skip))
    assert result.ok, result.reasons_vi
    from autopark.lidar.map_builder import write_map
    from autopark.lidar.localize import load_map

    write_map(result, tmp_path / name)
    return load_map(tmp_path / name, default_config().localize)


def _c1_steps(lmap, recording_path, *, skip: float, limit: int | None, allow_global: bool = True):
    from autopark.lidar.recording import read_recording

    cfg = default_config()
    params = replace(cfg.localizer, allow_global_init=allow_global)
    est = LidarPoseEstimator(lmap, params, mount=LidarMount(0.0, 0.0, 0.0), odometry=cfg.odometry,
                             hint=Pose(0.0, 0.0, 0.0))
    rec = read_recording(recording_path)
    indices = [i for i in range(len(rec)) if rec.t[i] - rec.t[0] >= skip][:limit]
    steps = []
    for i in indices:
        angles, ranges, _ = rec.beams(i)
        steps.append(est.process(angles, ranges, float(rec.t[i])))
        if est.state == TRACKING and not est.armed:
            est.arm()
    return est, steps


def test_real_c1_static_recordings_track_without_alarms(tmp_path):
    """C1 đứng yên, không phải phép đo độ đúng (không có tham chiếu độc lập): p07 dựng bản đồ từ 3–10 s đầu, live_headless
    (lần bật khác, lệch +4,33°) định vị trên đó; o03 trên bản đồ từ 3–10 s đầu của chính nó. Đo 02/10/2026: live_headless
    2 INIT rồi 26/26 OK, khoảng tản (max − min) 4,8 mm / 9,3 mm / 0,21°, trung vị (−1,0 mm; −4,8 mm; +4,31°) (DINH_VI_LIDAR
    mục 5: −1,1 mm; −6,8 mm; +4,33°); o03 2 INIT rồi 148/148 OK, khoảng tản 7,5 mm / 6,3 mm / 0,26°."""
    p07 = RUNS / "lidar_bench" / "20260922" / "p07_nen_phong.npz"
    live = RUNS / "lidar_bench" / "20260922" / "live_headless.npz"
    o03 = RUNS / "rig_recordings" / "o03_20260924" / "lidar" / "part_0000.npz"
    if not (p07.exists() and live.exists()):
        pytest.skip("không có bản ghi C1 runs/lidar_bench/20260922")
    lmap = _c1_map_from(p07, 10.0, tmp_path, "p07")
    est, steps = _c1_steps(lmap, live, skip=3.0, limit=120)
    after = steps[next(k for k, s in enumerate(steps) if s.decision == "OK"):]
    assert all(s.decision == "OK" for s in after) and not any(s.stopped for s in steps)
    poses = np.array([[s.vehicle.x, s.vehicle.y, s.vehicle.yaw] for s in after])
    assert np.ptp(poses[:, 0]) < 0.02 and np.ptp(poses[:, 1]) < 0.025 and np.degrees(np.ptp(poses[:, 2])) < 0.6
    assert math.degrees(np.median(poses[:, 2])) == pytest.approx(4.33, abs=0.3)
    assert math.hypot(np.median(poses[:, 0]) + 0.0011, np.median(poses[:, 1]) + 0.0068) < 0.01
    if o03.exists():
        own = _c1_map_from(o03, 10.0, tmp_path, "o03")
        _, steps = _c1_steps(own, o03, skip=3.0, limit=150)
        after = steps[next(k for k, s in enumerate(steps) if s.decision == "OK"):]
        assert all(s.decision == "OK" for s in after) and not any(s.stopped for s in steps)
        poses = np.array([[s.vehicle.x, s.vehicle.y, s.vehicle.yaw] for s in after])
        assert np.ptp(poses[:, 0]) < 0.025 and np.ptp(poses[:, 1]) < 0.025 and np.degrees(np.ptp(poses[:, 2])) < 0.8


def test_real_c1_other_place_never_reports_ok(tmp_path):
    """k01 (C1 đã dời đi chỗ khác) trên bản đồ p07, không tìm toàn cục: không bao giờ công bố tư thế."""
    p07 = RUNS / "lidar_bench" / "20260922" / "p07_nen_phong.npz"
    k01 = RUNS / "lidar_bench" / "20260924_kiem" / "k01_kiem_suc_khoe.npz"
    if not (p07.exists() and k01.exists()):
        pytest.skip("không có bản ghi C1 p07 / k01")
    lmap = _c1_map_from(p07, 10.0, tmp_path, "p07")
    est, steps = _c1_steps(lmap, k01, skip=3.0, limit=40, allow_global=False)
    assert est.published() is None and all(s.decision == "INIT" for s in steps)


def test_drow_corridor_segment():
    """DROW v2 (Beyer et al., giấy phép MIT; docs/DU_LIEU_VA_GIAY_PHEP.md) `run_2015-11-25-10-34-20-c`, vòng 300–459, SICK
    S300 225°: bản đồ dựng từ tư thế odometry .odom2 của DROW (KHÔNG phải ground truth), gá 0, không mặt nạ, không arm()
    (chốt dừng tự khởi tạo lại sau 1 s như ngoài lần chạy). Độ lệch so với .odom2 chỉ báo cáo, không coi là sai số. Đo
    02/10/2026: 2 INIT, 134/160 OK, hai lần POSE_LOST do (a) FAILED conflicts_with_map (người đi lại trong cảnh, cả lúc dựng
    bản đồ), 0 POSE_DISAGREE trên 132 vòng kiểm chéo; lệch so với .odom2 trung vị 2,5 cm, lớn nhất 6,3 cm trên 7,8 m.
    Chạy ≈ 20 s (bản đồ 17 × 12 m)."""
    path = DROW_DIR / "val" / "run_2015-11-25-10-34-20-c.bag.csv"
    if not (path.exists() and path.with_suffix(".odom2").exists()):
        pytest.skip("không có DROW v2 (datasets/drow/DROWv2-data)")
    from autopark.lidar.drow import drow_angles, read_drow_csv
    from autopark.lidar.drow_odom import read_drow_odom
    from autopark.lidar.localize import LocalizationMap
    from autopark.lidar.map_builder import build_map_from_poses
    from autopark.lidar.scan_odometry import relative_to_first

    recording, odom, angles = read_drow_csv(path), read_drow_odom(path.with_suffix(".odom2")), drow_angles()
    indices = list(range(300, 460))
    poses = relative_to_first(odom.xya[indices])
    items = [((angles, recording.ranges[i]), tuple(p)) for i, p in zip(indices, poses)]
    _, states, grid = build_map_from_poses(items, None, MapBuildConfig(max_range=8.0, min_range=0.25))
    cfg = default_config()
    lmap = LocalizationMap(states, grid, cfg.localize, source="drow")
    est = LidarPoseEstimator(lmap, cfg.localizer, mount=LidarMount(0.0, 0.0, 0.0), odometry=cfg.odometry,
                             hint=Pose(0.0, 0.0, 0.0))
    steps = [est.process(angles, recording.ranges[i], float(recording.t[i] - recording.t[0]), truth=Pose(*p))
             for i, p in zip(indices, poses)]
    first = next(k for k, s in enumerate(steps) if s.decision == "OK")
    after = steps[first:]
    ok = [s for s in after if s.decision == "OK"]
    checked = [s for s in after if s.check_used]
    assert len(ok) >= 0.8 * len(after), {s.decision for s in after}
    assert sum(s.decision == POSE_DISAGREE for s in checked) <= max(1, 0.01 * len(checked))
    dev = np.array([math.hypot(s.vehicle.x - s.truth.x, s.vehicle.y - s.truth.y) for s in ok])
    print(f"DROW: {len(ok)}/{len(after)} OK, lệch so với .odom2 trung vị {np.median(dev) * 100:.1f} cm, "
          f"lớn nhất {dev.max() * 100:.1f} cm (không phải sai số)")
