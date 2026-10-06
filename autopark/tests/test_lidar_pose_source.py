"""Nguồn tư thế LiDAR (application/lidar_pose_source.py, T2, thêm 02/10/2026): cấu hình đọc chặt, đổi đồng hồ, luồng xử
lý, cổng START, lý do không dùng được, LiDAR mô phỏng. Không thiết bị: vòng quét tổng hợp (tests/lidar_fakes.py) hoặc
bộ ghép giả."""
from dataclasses import replace
import json
import math
import threading
import time

import pytest

np = pytest.importorskip("numpy")

from autopark.application.lidar_pose_source import (LidarPoseSource, LidarSimPoseFactory,  # noqa: E402
                                                    SimLidarPoseSource)
from autopark.application.vehicle_link import POSE_OK  # noqa: E402
from autopark.domain.types import Obstacle, Pose  # noqa: E402
from autopark.lidar.pose_config import DEFAULT_PATH, LidarMount, Prerequisite, load_lidar_pose_config  # noqa: E402
from autopark.lidar.pose_estimator import (INIT, POSE_LOST, TRACKING, EstimatorStep, LidarPoseEstimator,  # noqa: E402
                                           Published)
from tests.lidar_fakes import CAR, bench_scenario, build_map, default_config, scan_at, scan_obj  # noqa: E402


# ---- cấu hình -----------------------------------------------------------------------------------------------------
def test_config_loads_strictly_and_lists_unmet_prerequisites(tmp_path):
    config = load_lidar_pose_config()
    assert config.path == DEFAULT_PATH and len(config.sha256) == 64 and config.max_pose_age_s == 0.25
    unmet = config.unmet()
    assert len(unmet) == 4 and unmet[0] == "gá LiDAR GIẢ ĐỊNH – CHƯA ĐO (configs/dinh_vi_lidar_v0.json)"
    assert "p04" in unmet[1] and "DV-2" in unmet[2] and "DV-1" in unmet[3]
    assert config.odometry.velocity_per == "second" and config.localizer.max_consecutive_bad == 2
    assert config.localizer.track_window == (0.15, 0.15, 10.0) and config.mount.x_m == 0.095
    data = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))

    def load(changed):
        path = tmp_path / "cau_hinh.json"
        path.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
        return load_lidar_pose_config(path)

    for bad, needle in (({**data, "la": 1}, "khóa lạ"), ({**data, "schema_version": 2}, "schema_version"),
                        ({**data, "localizer": {**data["localizer"], "cua_so": 1}}, "khóa lạ trong localizer"),
                        ({**data, "mount": {**data["mount"], "x_m": "0,095"}}, "phải là số JSON"),
                        ({**data, "odometry": {"velocity_per": "minute"}}, "velocity_per"),
                        ({**data, "localize": {"levels": 9}}, "levels"),
                        ({**data, "max_pose_age_s": 0}, "max_pose_age_s")):
        with pytest.raises(ValueError, match=needle):
            load(bad)
    claimed = {**data, "prerequisites": {**data["prerequisites"], "dau_goc_p04": {"ok": True, "evidence": None}}}
    assert "chưa đạt: dấu góc trái/phải p04 (ghi ok nhưng thiếu bằng chứng)" in load(claimed).unmet()
    done = {**data, "mount": {**data["mount"], "measured": True, "evidence": "docs/evidence/ga/do.json"},
            "prerequisites": {key: {"ok": True, "evidence": f"docs/evidence/{key}.json", "note": ""}
                              for key in data["prerequisites"]}}
    assert load(done).unmet() == []
    partial = load({"schema_version": 1})                                # khóa vắng mặt: mặc định của dataclass
    assert partial.odometry.velocity_per == "second" and len(partial.unmet()) == 4


def test_mount_round_trips_vehicle_and_sensor_poses():
    mount = LidarMount(0.1, -0.02, 30.0)
    vehicle = Pose(1.2, 0.7, math.radians(50))
    sensor = mount.sensor_pose(vehicle)
    back = mount.vehicle_pose(sensor)
    assert back.x == pytest.approx(vehicle.x) and back.y == pytest.approx(vehicle.y)
    assert back.yaw == pytest.approx(vehicle.yaw) and sensor.yaw == pytest.approx(math.radians(80))
    assert mount.as_tuple() == pytest.approx((0.1, -0.02, math.radians(30)))


# ---- nguồn thật (bộ ghép giả) --------------------------------------------------------------------------------------
class FakeEstimator:
    """Bộ ghép giả: mỗi vòng công bố OK ở tư thế cố định với stamp = t của vòng; `gate` chặn luồng xử lý (test luồng)."""

    def __init__(self, gate: threading.Event | None = None):
        self.gate = gate
        self.seen: list[float] = []
        self.state = INIT
        self.armed = False
        self._published = None
        self.commands = []

    def process(self, angles, ranges, t, *, t_first=None, truth=None):
        if self.gate is not None:
            assert self.gate.wait(5.0)
        self.seen.append(t)
        self.state = TRACKING
        self._published = Published(POSE_OK, Pose(0.5, 1.0, 0.0), t, "")
        step = EstimatorStep(len(self.seen) - 1, t, t_first, decision="OK", vehicle=Pose(0.5, 1.0, 0.0))
        return step

    def published(self):
        return self._published

    def health(self, now, received):
        return [], []

    def arm(self):
        self.commands.append("arm")

    def disarm(self):
        self.commands.append("disarm")

    def set_hint(self, pose):
        self.commands.append(("hint", pose))

    def reset_feed(self, reason):
        self.commands.append(("reset", reason))


def fake_scan(t=0.0):
    return scan_obj(np.zeros(3), np.ones(3), t)


def test_clock_conversion_keeps_the_scan_age_and_never_clamps():
    """io.now() = perf − 100 s: t của mẫu = io.now() − (perf() − t_vòng). Vòng ghi trước lúc io bắt đầu (t < 0 theo đồng
    hồ io) giữ t âm, không bị kẹp về 0; tuổi = perf() − t_vòng đúng như thật."""
    perf = [150.0]
    source = LidarPoseSource(FakeEstimator(), default_config(), map_info={"mirror": None}, threaded=False,
                             perf=lambda: perf[0])
    source.on_scan(fake_scan(), None, 49.9, 50.0)
    source.pump()
    assert source.latest() is None                                       # chưa gắn đồng hồ io
    source.bind_clock(lambda: perf[0] - 100.0)
    sample = source.latest()
    assert sample.t == pytest.approx(-50.0) and sample.status == POSE_OK and not sample.simulated
    assert sample.source_id == "lidar_c1_localize" and sample.pose == Pose(0.5, 1.0, 0.0)
    perf[0] = 150.2
    assert (perf[0] - 100.0) - source.latest().t == pytest.approx(100.2)  # tuổi tiếp tục tăng, không đóng dấu lại
    row = source.log_rows()[-1]
    assert row["t_perf_scan"] == 50.0 and row["t_first_perf"] == 49.9 and row["phase"] == "before_start"


def test_threaded_source_processes_the_newest_scan_counts_drops_and_closes():
    gate = threading.Event()
    estimator = FakeEstimator(gate)
    source = LidarPoseSource(estimator, default_config(), map_info={}, threaded=True)
    source.start()
    source.on_scan(fake_scan(), None, None, 1.0)
    deadline = time.monotonic() + 2.0
    while len(source._queue) and time.monotonic() < deadline:
        time.sleep(0.005)                                               # luồng đã lấy vòng 1 và đang chờ ở gate
    for k in range(2, 6):
        source.on_scan(fake_scan(), None, None, float(k))               # hàng đợi 1 vòng: vòng mới nhất thắng
    assert source.drops == 3 and source.scans_received == 5
    gate.set()
    deadline = time.monotonic() + 2.0
    while source.scans_processed < 2 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert estimator.seen == [1.0, 5.0]
    assert source.log_rows()[-1]["dropped_before"] == 3
    source.run_started()
    deadline = time.monotonic() + 2.0
    while "arm" not in estimator.commands and time.monotonic() < deadline:
        time.sleep(0.005)
    assert "arm" in estimator.commands                                   # lệnh đi qua luồng xử lý
    t0 = time.monotonic()
    source.close()
    assert time.monotonic() - t0 < 1.5 and not source._thread.is_alive()
    source.on_scan(fake_scan(), None, None, 9.0)                         # sau khi đóng: bỏ qua
    assert source.scans_received == 5 and not source.available and "đã đóng" in source.reason


def test_start_gate_refuses_only_hardware_vehicle_io():
    config = default_config()
    source = LidarPoseSource(FakeEstimator(), config, map_info={}, threaded=False)
    refusals, warnings = source.start_gate("VEHICLE_IO", hardware=True)
    assert refusals == config.unmet() and warnings == []
    for mode, hardware in (("OBSERVE", True), ("VEHICLE_IO", False), ("OBSERVE", False)):
        refusals, warnings = source.start_gate(mode, hardware=hardware)
        assert refusals == [] and len(warnings) == 4 and all("chưa đủ điều kiện cho bo thật" in w for w in warnings)
    ready = replace(config, mount=replace(config.mount, measured=True, evidence="docs/evidence/ga.json"),
                    prerequisites=tuple(Prerequisite(p.key, True, "docs/evidence/x.json") for p in config.prerequisites))
    assert LidarPoseSource(FakeEstimator(), ready, map_info={}, threaded=False).start_gate(
        "VEHICLE_IO", hardware=True) == ([], [])


def test_unavailable_reasons_are_vietnamese():
    """Lý do thật của bộ ghép thật (vòng quét tổng hợp): chưa có vòng, đang khởi tạo, OK, mất vòng quét, đảo chiều góc,
    chốt POSE_LOST, đã đóng."""
    config = default_config()
    lmap = build_map()
    perf = [10.0]
    est = LidarPoseEstimator(lmap, config.localizer, mount=config.mount, odometry=config.odometry, self_mask=CAR,
                             hint=Pose(0.5, 1.0, 0.0))
    source = LidarPoseSource(est, config, map_info={"mirror": False}, threaded=False, perf=lambda: perf[0])
    assert source.reason == "Chưa có vòng quét: bấm Kết nối ở ngăn LiDAR" and not source.available
    rng = np.random.default_rng(31)
    sensor = config.mount.sensor_pose(Pose(0.5, 1.0, 0.0))

    def feed(n):
        for _ in range(n):
            perf[0] += 0.1
            source.on_scan(scan_obj(*scan_at(sensor, rng), 0.0), None, None, perf[0])
            source.pump()

    feed(1)
    assert source.reason.startswith("đang khởi tạo định vị")
    feed(8)
    assert source.available and source.reason == "" and source.start_problems() == ([], [])
    status = source.status()
    assert status.state == TRACKING and status.text.startswith("Định vị LiDAR: OK · (0,5")
    assert "vòng/s" in status.text and "bỏ 0 vòng" in status.text
    source.set_lidar_mirror(True)
    assert "chiều góc" in source.reason and any("chiều góc" in p for p in source.start_problems()[0])
    source.set_lidar_mirror(False)
    perf[0] += 1.5
    assert source.reason.startswith("Không có vòng quét mới trong 1,5 s")
    assert source.start_problems()[0]
    source.feed_reset("ngắt LiDAR")
    source.run_started()
    source.pump()
    source.feed_reset("đổi chiều góc")
    source.pump()
    feed(1)
    assert source.latest() is None                                      # chưa gắn đồng hồ io
    assert "POSE_LOST" in source.reason and "LiDAR ngắt/đổi chiều góc" in source.reason
    assert source.status().text.startswith("Định vị LiDAR: LẠC (POSE_LOST")
    source.close()
    assert source.reason == "nguồn tư thế LiDAR đã đóng"


def test_worker_error_latches_pose_lost():
    class Broken(FakeEstimator):
        def process(self, *args, **kwargs):
            raise RuntimeError("hỏng")

    source = LidarPoseSource(Broken(), default_config(), map_info={}, threaded=True)
    source.bind_clock(time.perf_counter)
    source.start()
    source.on_scan(fake_scan(), None, None, time.perf_counter())
    deadline = time.monotonic() + 2.0
    while source.worker_error is None and time.monotonic() < deadline:
        time.sleep(0.005)
    assert "hỏng" in source.worker_error and source.latest().status == POSE_LOST
    assert "luồng định vị LiDAR lỗi" in source.reason
    source.close()


# ---- LiDAR mô phỏng ------------------------------------------------------------------------------------------------
def sim_source(scenario, *, seed=0, truth=None, config=None):
    clock = [0.0]
    pose = {"p": truth or scenario.start}
    source = SimLidarPoseSource(lambda: pose["p"], lambda: clock[0], scenario, CAR, config or default_config(),
                                seed=seed)
    return source, clock, pose


def test_sim_source_scans_follow_truth_injected_obstacles_and_blocked_flag():
    scenario = bench_scenario()
    source, clock, pose = sim_source(scenario)
    assert source.simulated and source.source_id == "lidar_sim_localize" and source.map_info["frame"] == "sa_ban"
    first = source.latest()
    assert first is None and source.scans_processed == 1 and source.estimator.state == INIT
    clock[0] = 0.05
    source.latest()
    assert source.scans_processed == 1                                   # chưa tới hạn vòng sau (10 Hz)
    for k in range(1, 9):
        clock[0] = 0.1 * k
        sample = source.latest()
    assert source.estimator.state == TRACKING and sample.status == POSE_OK and sample.simulated
    assert sample.pose.distance_to(scenario.start) < 0.02 and sample.t == pytest.approx(0.8)
    clock[0] = 1.05                                                     # tới hạn hai vòng (0,9 và 1,0 s): chỉ làm vòng mới
    source.latest()
    assert source.drops == 1 and source.log_rows()[-1]["dropped_before"] == 1
    pose["p"] = Pose(0.53, 1.0, 0.0)                                    # xe đi 3 cm: vòng sau theo tư thế thật mới
    clock[0] = 1.1
    moved = source.latest()
    assert moved.pose.x == pytest.approx(0.53, abs=0.015)
    sensor = source.config.mount.sensor_pose(pose["p"])
    angles, ranges = source.scanner.scan(pose["p"])
    ahead = int(np.argmin(np.abs(angles)))
    assert ranges[ahead] == pytest.approx(3.0 - sensor.x, abs=0.05) or math.isnan(ranges[ahead])
    scenario.obstacles.append(Obstacle("hop_moi", sensor.x + 0.6, sensor.y, 0.1, 0.3))    # đọc lại mỗi lần quét
    hits = [source.scanner.scan(pose["p"])[1][ahead] for _ in range(5)]
    assert any(abs(h - 0.55) < 0.05 for h in hits if math.isfinite(h))
    source.scanner.blocked = True
    assert np.isnan(source.scanner.scan(pose["p"])[1]).all()


def test_sim_source_warm_up_is_deterministic_for_a_seed():
    scenario = bench_scenario()
    runs = []
    for seed in (5, 5, 6):
        source, clock, _ = sim_source(scenario, seed=seed)

        def advance(seconds, clock=clock):
            clock[0] = round(clock[0] + seconds, 9)
            return []

        source.warm_up(advance)
        assert source.start_problems() == ([], []) and source.available
        assert clock[0] <= source.config.sim.warmup_max_s
        runs.append(([(r["n"], r["decision"], r["a_x"], r["b_x"]) for r in source.log_rows()], clock[0]))
    assert runs[0] == runs[1] and runs[0][0] != runs[2][0]
    factory = LidarSimPoseFactory(default_config(), seed=5)
    assert factory.source_id == "lidar_sim_localize" and factory.simulated
