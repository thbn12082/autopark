"""Phiên đỗ xe với nguồn tư thế LiDAR (T2, thêm 02/10/2026; application/lidar_pose_source.py, VehicleLink).

Chuỗi MÔ PHỎNG: Session → VehicleLink → SimVehicleIO → FirmwareModel, tư thế từ LiDAR MÔ PHỎNG (vòng quét dựng từ sa bàn
quanh tư thế thật của xe) qua bộ ghép (a) + (b); và cổng serial GIẢ (FirmwareSerialLoopback) cho bước 0b/0c với bo
"thật". Không mở cổng nào, không cần bo hay LiDAR. Bằng chứng ở mức MP (simulation_only); với bo thật mọi đường này
CHƯA THỬ. Tuổi tư thế tối đa 0,25 s (LinkParams.max_pose_age_s, N-T2, ĐỀ XUẤT; người dùng giao quyết định 02/10/2026).
Sửa sau review 02/10/2026: liên kết dựng như giao diện, `LinkParams.for_lidar(0.25)` (thêm dự đoán tư thế tới io.now();
test của phần dự đoán ở tests/test_pose_prediction.py)."""
from dataclasses import replace
import csv
import json
import math
import random
import time

import pytest

np = pytest.importorskip("numpy")

from autopark.application.lidar_pose_source import LidarPoseSource, LidarSimPoseFactory  # noqa: E402
from autopark.application.session import Session, SessionError, SessionState  # noqa: E402
from autopark.application.vehicle_link import (POSE_FIELDS, DriveMode, LinkParams, PoseSample,  # noqa: E402
                                               VehicleLink)
from autopark.domain.types import ParkingGoal, Pose, VehicleState  # noqa: E402
from autopark.evaluation.reference_pose import read_reference  # noqa: E402
from autopark.lidar.pose_estimator import LidarPoseEstimator, localize  # noqa: E402
from autopark.lidar.synthetic import polygon_segments  # noqa: E402
from autopark.storage import run_store  # noqa: E402
from autopark.storage.run_store import export_run, replay_vehicle_run  # noqa: E402
from autopark.transport.firmware_model import FirmwareModel  # noqa: E402
from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock  # noqa: E402
from autopark.transport.protocol import State  # noqa: E402
from autopark.transport.vehicle_io import SIM_FIRMWARE_DEFAULT, SerialVehicleIO, SimIOConfig, SimVehicleIO  # noqa: E402
from tests.lidar_fakes import build_map, default_config, scan_at, scan_obj  # noqa: E402

FAST_FW = replace(SIM_FIRMWARE_DEFAULT, boot_hold_ms=200)
SIM_CFG = SimIOConfig(firmware=FAST_FW)
PARAMS = LinkParams.for_lidar(0.25)          # như MainWindow dựng "LiDAR mô phỏng" / "LiDAR thật" (sau review 02/10)


def straight_session(scenario, cfg, goal_x=2.0) -> Session:
    scenario.obstacles = []
    scenario.start = Pose(0.5, 1.0, 0.0)
    scenario.goal = ParkingGoal(Pose(goal_x, 1.0, 0.0))
    session = Session(scenario, cfg)
    assert session.plan_sync().ok
    return session


class RecordingFactory(LidarSimPoseFactory):
    """Nhà máy LiDAR mô phỏng giữ lại mọi nguồn đã tạo; `tweak(source, k)` sửa nguồn thứ k ngay khi tạo."""

    def __init__(self, tweak=None):
        super().__init__(default_config())
        self.sources = []
        self.tweak = tweak

    def __call__(self, io, scenario, cfg):
        source = super().__call__(io, scenario, cfg)
        if self.tweak is not None:
            self.tweak(source, len(self.sources))
        self.sources.append(source)
        return source


def lidar_link(mode=DriveMode.VEHICLE_IO, factory=None) -> VehicleLink:
    return VehicleLink.simulated(mode, SIM_CFG, params=PARAMS, pose_factory=factory or RecordingFactory())


def run_until_done(session, step=0.5, max_calls=400):
    for _ in range(max_calls):
        session.advance(step)
        if not session.simulating:
            return
    raise AssertionError(f"Phiên không kết thúc, trạng thái {session.state}")


def advance_for(session, seconds, step=0.05):
    for _ in range(int(round(seconds / step))):
        session.advance(step)


def first_stop_t(link, code):
    return next(float(r["t_session"]) for r in link.event_rows if r["code"] == code and r["handling"] == "session_stop")


def enables_after(link, t_session):
    return [r for r in link.command_rows if r["kind"] == "TRACK" and r["sent"] == 1 and r["t_session"] > t_session]


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---- MP: bo mô phỏng + LiDAR mô phỏng -----------------------------------------------------------------------------
def test_vehicle_io_parks_with_simulated_lidar_localization(scenario, cfg, tmp_path):
    """Đo 02/10/2026 (đường thẳng 1,5 m): COMPLETED; tư thế THẬT cuối lệch đích 4,7 mm / 0,03° (N-D1, N-D2 ở mức MP:
    ≤ 5 cm / 5°); 132/134 vòng OK (2 INIT); mọi mẫu poses.csv OK. Đo lại sau review 02/10/2026 với dự đoán tư thế
    (`for_lidar`): 4,7 mm / 0,02°, 125/125 vòng của lần chạy OK."""
    session = straight_session(scenario, cfg)
    factory = RecordingFactory()
    link = lidar_link(factory=factory)
    session.set_vehicle_link(link)
    session.start_run()
    source = link.pose_source
    assert source is factory.sources[0] and source.estimator.armed
    codes = [r["code"] for r in link.event_rows]
    assert codes.count("POSE_SOURCE_WARNING") == 4 and "START_CHECK" in codes
    check = next(r for r in link.event_rows if r["code"] == "START_CHECK")
    assert check["message"].startswith("Đạt") and "lidar_sim_localize, MÔ PHỎNG" in check["message"]
    run_until_done(session)
    assert session.state == SessionState.COMPLETED, session.stop_reason
    truth = link.io.truth.pose
    goal = session.scenario.goal.pose
    assert truth.distance_to(goal) <= 0.05 and abs(math.degrees(truth.yaw - goal.yaw)) <= 5.0
    assert session.safety_events == [] and link.io.firmware.state == State.DISARMED
    rows = [r for r in link.pose_rows if r["available"] == 1]
    assert rows and all(r["status"] == "OK" and r["source_id"] == "lidar_sim_localize" for r in rows)
    written = link.write_logs(tmp_path / "lan")
    assert {"localization.csv", "tu_the_that_mo_phong.csv", "tu_the_that_mo_phong.json"} <= set(written)
    localization = read_csv(written["localization.csv"])
    assert localization[0]["phase"] == "before_start" and localization[-1]["phase"] == "run"
    assert all(r["decision"] == "OK" for r in localization if r["phase"] == "run")
    assert all(r["truth_x"] != "" and r["t_io_scan"] != "" and r["t_perf_scan"] == "" for r in localization)
    reference = read_reference(written["tu_the_that_mo_phong.csv"])
    assert reference.meta.method == "MP" and reference.meta.clock == "t_session" and reference.samples[0].t == 0.0
    assert reference.samples[-1].pose.distance_to(truth) < 1e-4                  # tệp ghi 5 chữ số thập phân
    info = json.loads(written["link.json"].read_text(encoding="utf-8"))
    assert info["pose_source"] == "lidar_sim_localize" and info["pose_simulated"] is True
    assert info["params"]["max_pose_age_s"] == 0.25 and info["pose_source_info"]["evidence"] == "simulation_only"
    assert info["params"]["predict_pose"] is True and all(r["pred_dt_s"] != "" for r in rows if r["use"] == "observe")
    assert session.run_snapshot["vehicle_link"]["pose_source_info"]["map"]["frame"] == "sa_ban"
    assert session.run_snapshot["start_source"] == "manual"
    session.close()


def test_observe_with_simulated_lidar_and_human_driver_sends_no_command(scenario, cfg):
    session = straight_session(scenario, cfg)
    link = lidar_link(DriveMode.OBSERVE)
    session.set_vehicle_link(link)
    session.start_run()
    link.human.set(0.12, 0.0)
    advance_for(session, 2.0)
    assert session.state == SessionState.RUNNING and link.io.truth.pose.x > 0.65
    session.request_stop()
    run_until_done(session)
    assert link.io.stats.commands_sent == 0 and link.io.firmware.state == State.DISARMED
    rows = link.pose_source.log_rows()
    run_rows = [r for r in rows if r["phase"] == "run"]
    assert len(run_rows) >= 15 and all(r["decision"] == "OK" for r in run_rows)
    errors = [math.hypot(float(r["vehicle_x"]) - float(r["truth_x"]), float(r["vehicle_y"]) - float(r["truth_y"]))
              for r in run_rows]
    assert max(errors) < 0.03
    session.close()


def test_object_only_the_lidar_sees_stops_with_pose_lost(scenario, cfg):
    """Vật chỉ LiDAR thấy (không có trong sa bàn, không qua inject_obstacle — hàm đó dừng MAP_CHANGED trước): vòng
    quanh cảm biến che gần hết tầm nhìn → (a) không OK hai vòng liền → POSE_LOST, không lệnh enable nào sau đó."""
    session = straight_session(scenario, cfg)
    link = lidar_link()
    session.set_vehicle_link(link)
    session.start_run()
    advance_for(session, 1.0)
    source = link.pose_source
    sensor = source.config.mount.sensor_pose(link.io.truth.pose)
    ring = [(sensor.x + 0.4 * math.cos(a), sensor.y + 0.4 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 13)[:-1]]
    source.scanner.extra_segments = polygon_segments(ring)
    run_until_done(session, step=0.1)
    first = session.safety_events[0]
    assert first.code == "POSE_LOST" and first.stamp.source_id == "lidar_sim_localize"
    assert "Định vị LiDAR" in first.message and session.state == SessionState.STOPPED
    assert enables_after(link, first_stop_t(link, "POSE_LOST")) == []
    assert link.io.firmware.state == State.DISARMED
    session.close()


def test_lidar_blocked_gives_pose_lost_and_silent_gives_stale_pose_within_limits(scenario, cfg):
    """Đo 02/10/2026: che LiDAR → POSE_LOST sau 0,16 s (hai vòng không OK); nguồn im → STALE_POSE sau 0,18 s (tuổi
    mẫu cuối vượt 0,25 s). Có dự đoán tư thế (sau review 02/10/2026) vẫn 0,16 s và 0,18 s: STALE_POSE theo tuổi THÔ."""
    delays = {}
    for flag, code in (("blocked", "POSE_LOST"), ("silent", "STALE_POSE")):
        session = straight_session(scenario, cfg)
        link = lidar_link()
        session.set_vehicle_link(link)
        session.start_run()
        advance_for(session, 1.0)
        t_fault = session.world.time
        setattr(link.pose_source.scanner, flag, True)
        run_until_done(session, step=0.05)
        assert session.safety_events[0].code == code, [e.code for e in session.safety_events]
        delays[code] = first_stop_t(link, code) - t_fault
        assert enables_after(link, first_stop_t(link, code)) == []
        assert link.io.firmware.state == State.DISARMED
        session.close()
    period, latency = 0.1, 0.04
    assert 0 < delays["POSE_LOST"] <= 2 * period + latency + 0.03
    assert 0 < delays["STALE_POSE"] <= 0.25 + 0.03


def test_disagreement_mid_run_stops_with_pose_disagree(scenario, cfg):
    def jump(source, _k):
        est = source.estimator

        def localize_fn(lmap, angles, ranges, initial=(0.0, 0.0, 0.0), **kwargs):
            result = localize(lmap, angles, ranges, initial, **kwargs)
            if est.armed and est.n >= 18 and result.ok:
                result.y += 0.10                     # (a) nhảy 10 cm sang ngang đường
            return result

        est.localize_fn = localize_fn

    session = straight_session(scenario, cfg)
    link = lidar_link(factory=RecordingFactory(jump))
    session.set_vehicle_link(link)
    session.start_run()
    run_until_done(session, step=0.1)
    first = session.safety_events[0]
    assert first.code == "POSE_DISAGREE" and "(a) và (b) lệch" in first.message
    assert enables_after(link, first_stop_t(link, "POSE_DISAGREE")) == []
    status = [r for r in link.pose_rows if r["status"] not in ("", "OK")]
    assert status and status[0]["status"] == "POSE_DISAGREE"
    session.close()


def test_replay_of_a_lidar_run_matches_and_old_tapes_without_status_still_replay(scenario, cfg, tmp_path,
                                                                                  monkeypatch):
    monkeypatch.setattr(run_store, "environment", lambda: {"test": True})
    session = straight_session(scenario, cfg, goal_x=1.2)
    link = lidar_link()
    session.set_vehicle_link(link)
    session.start_run()
    run_until_done(session)
    assert session.state == SessionState.COMPLETED
    bundle = export_run(session, tmp_path / "goi")
    assert (bundle / "vehicle_io" / "localization.csv").is_file()
    _, report = replay_vehicle_run(bundle)
    assert report.ok, report.lines()
    assert any("localization.csv" in item for item in report.not_compared)
    # Băng cũ (trước T2) không có cột status, reason: mẫu coi là OK, phát lại vẫn khớp
    path = bundle / "vehicle_io" / "poses.csv"
    rows = read_csv(path)
    old = [f for f in POSE_FIELDS if f not in ("status", "reason")]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=old, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    _, report = replay_vehicle_run(bundle)
    assert report.ok, report.lines()
    session.close()
    # Lần chạy dừng vì POSE_LOST: phát lại dựng lại đúng mã dừng từ cột status
    session = straight_session(scenario, cfg)
    link = lidar_link()
    session.set_vehicle_link(link)
    session.start_run()
    advance_for(session, 1.0)
    link.pose_source.scanner.blocked = True
    run_until_done(session, step=0.1)
    assert session.safety_events[0].code == "POSE_LOST"
    bundle = export_run(session, tmp_path / "goi_lac")
    replayed, report = replay_vehicle_run(bundle)
    assert report.ok, report.lines()
    assert replayed.safety_events[0].code == "POSE_LOST"
    session.close()


class FixedPose:
    """Tư thế cố định, cũ `age_s` giây."""

    source_id = "fixed_pose"
    simulated = True

    def __init__(self, io, pose, age_s=0.0):
        self.io, self.pose, self.age_s = io, pose, age_s

    def latest(self):
        return PoseSample(self.pose, self.io.now() - self.age_s, self.source_id, True)


def test_max_pose_age_applies_only_to_the_pose(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = SimVehicleIO(cfg, SIM_CFG, start=VehicleState(scenario.start, 0.0, 0.0, 0.0))
    session.set_vehicle_link(VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FixedPose(io, scenario.start, 0.2)))
    with pytest.raises(SessionError, match="Chưa có tư thế mới"):
        session.start_run()                                              # mặc định: tư thế 0,2 s là cũ (0,15 s)
    session = straight_session(scenario, cfg)
    io = SimVehicleIO(cfg, SIM_CFG, start=VehicleState(scenario.start, 0.0, 0.0, 0.0))
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FixedPose(io, scenario.start, 0.2), params=PARAMS)
    assert PARAMS.pose_age_limit_s == 0.25 and LinkParams().pose_age_limit_s == 0.15
    session.set_vehicle_link(link)
    session.start_run()
    advance_for(session, 0.3)
    assert session.state == SessionState.RUNNING and session.safety_events == []
    io.set_link(False)                                                   # telemetry vẫn theo 0,15 s
    t_cut = session.world.time
    run_until_done(session, step=0.05)
    assert session.safety_events[0].code == "STALE_TELEMETRY"
    assert first_stop_t(link, "STALE_TELEMETRY") - t_cut <= 0.15 + 0.03
    with pytest.raises(ValueError, match="max_pose_age_s"):
        LinkParams(max_pose_age_s=0.0)


# ---- bo "thật" qua cổng serial GIẢ --------------------------------------------------------------------------------
def ready_lidar_source(config=None):
    """LidarPoseSource (không luồng) đã bắt được: vòng quét tổng hợp ở điểm xuất phát, dấu perf_counter thật."""
    config = config or default_config()
    est = LidarPoseEstimator(build_map(), config.localizer, mount=config.mount, odometry=config.odometry,
                             hint=Pose(0.5, 1.0, 0.0))
    source = LidarPoseSource(est, config, map_info={"mirror": False}, threaded=False)
    feed(source, 9)
    return source


def feed(source, n, seed=41):
    rng = np.random.default_rng(seed)
    sensor = source.config.mount.sensor_pose(Pose(0.5, 1.0, 0.0))
    for _ in range(n):
        source.on_scan(scan_obj(*scan_at(sensor, rng), 0.0), None, None, time.perf_counter())
        source.pump()
        time.sleep(0.002)


def counting_opener(calls, firmware=None, clock=None, inputs=None):
    def opener():
        calls.append(1)
        if firmware is None:
            raise AssertionError("không được mở cổng")
        return FirmwareSerialLoopback(firmware, clock, inputs=inputs)

    return opener


def test_serial_board_with_ready_lidar_source_refuses_vehicle_io_before_any_open(scenario, cfg):
    session = straight_session(scenario, cfg)
    calls = []
    io = SerialVehicleIO(None, opener=counting_opener(calls), port="COM7", rng=random.Random(1))
    source = ready_lidar_source()
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=source, params=PARAMS)
    assert link.hardware_actuators and source.available
    session.set_vehicle_link(link)
    with pytest.raises(SessionError, match="START_POSE_UNVERIFIED|Không bắt đầu được với bo thật") as info:
        session.start_run()
    assert "COM7" in str(info.value) and "GIẢ ĐỊNH – CHƯA ĐO" in str(info.value) and "Cổng chưa được mở" in str(info.value)
    assert calls == [] and io.transport is None and io.stats.frames_sent == 0
    assert [r["code"] for r in link.start_refusals] == ["START_POSE_UNVERIFIED"]
    flagged = VehicleLink(DriveMode.VEHICLE_IO, SerialVehicleIO(None, opener=counting_opener(calls), port="COM8"),
                          pose_source=source, params=PARAMS, virtual_board=True)
    assert not flagged.hardware_actuators and flagged.describe()["virtual_board"] is True
    session.close()


def test_observe_with_lidar_source_reopens_the_deferred_port_once_and_reaches_start_check(scenario, cfg):
    """Quan sát với nguồn LiDAR: cảnh báo POSE_SOURCE_WARNING, mở cổng một lần (bước 0c), tới START_CHECK; bo giả không
    đọc cảm biến nên START_CHECK từ chối (T8: telemetry không có tốc độ/góc lái đo). Cổng giữ mở cho lần START sau;
    `close()` đóng."""
    session = straight_session(scenario, cfg)
    calls = []
    clock = ManualClock()
    firmware = FirmwareModel(FAST_FW, boot_id=0xB007)
    io = SerialVehicleIO(None, opener=counting_opener(calls, firmware, clock), clock=clock, port="COM7",
                         rng=random.Random(2))
    source = ready_lidar_source()
    link = VehicleLink(DriveMode.OBSERVE, io, pose_source=source, params=PARAMS)
    session.set_vehicle_link(link)
    for attempt in range(2):
        feed(source, 3, seed=50 + attempt)
        with pytest.raises(SessionError, match="Telemetry không có tốc độ hoặc góc lái đo được"):
            session.start_run()
        assert len(calls) == 1 and io.transport is not None
    codes = [r["code"] for r in link.start_refusals]
    assert codes.count("POSE_SOURCE_WARNING") == 8 and codes.count("START_CHECK") == 2
    assert "START_POSE_UNVERIFIED" not in codes and "START_NO_LINK" not in codes
    loop = io.transport
    link.close()
    assert io.transport is None and loop.closed
    session.close()


def test_step_0a_refusal_names_the_port_state_and_release_port_closes_it(scenario, cfg):
    """Sửa sau review 02/10/2026: lần START trước đã mở cổng ở bước 0c (Quan sát, START_CHECK từ chối vì T8) và liên kết
    giữ cổng; LiDAR im 1,5 s nên lần sau bị từ chối ở bước 0a. Lời từ chối nói cổng ĐANG MỞ (trước đó: "Cổng chưa được
    mở" và chỉ tới "Kiểm kết nối bo", vốn mở cổng lần hai). `release_port()` đóng cổng liên kết giữ (không I/O nào
    khác); sau đó bước 0a lại nói "Cổng chưa được mở"."""
    session = straight_session(scenario, cfg)
    calls = []
    clock = ManualClock()
    io = SerialVehicleIO(None, opener=counting_opener(calls, FirmwareModel(FAST_FW, boot_id=0xB007), clock),
                         clock=clock, port="COM7", rng=random.Random(2))
    config = default_config()
    perf = [100.0]
    est = LidarPoseEstimator(build_map(), config.localizer, mount=config.mount, odometry=config.odometry,
                             hint=Pose(0.5, 1.0, 0.0))
    source = LidarPoseSource(est, config, map_info={"mirror": False}, threaded=False, perf=lambda: perf[0])
    rng = np.random.default_rng(41)
    sensor = config.mount.sensor_pose(Pose(0.5, 1.0, 0.0))
    for _ in range(25):
        perf[0] += 0.1
        source.on_scan(scan_obj(*scan_at(sensor, rng), 0.0), None, None, perf[0])
        source.pump()
    assert source.available
    link = VehicleLink(DriveMode.OBSERVE, io, pose_source=source, params=PARAMS)
    session.set_vehicle_link(link)
    with pytest.raises(SessionError, match="Telemetry không có tốc độ hoặc góc lái đo được"):
        session.start_run()                                     # bước 0c mở COM7; START_CHECK từ chối (T8)
    loop = io.transport
    assert loop is not None and len(calls) == 1
    perf[0] += 1.5                                              # LiDAR im 1,5 s: nguồn không dùng được
    assert not source.available
    with pytest.raises(SessionError, match="Cổng đang mở") as info:
        session.start_run()
    assert "Cổng chưa được mở" not in str(info.value) and "đóng cổng này của liên kết" in str(info.value)
    row = link.start_refusals[-1]
    assert row["code"] == "START_NO_POSE_SOURCE" and "Cổng đang mở" in row["message"] and "COM7" in row["message"]
    assert io.transport is loop and len(calls) == 1 and not loop.closed      # bước 0a: không I/O nào
    assert link.release_port() == "COM7" and loop.closed and io.transport is None and not io.connected
    assert link.release_port() is None                          # không còn gì để đóng
    with pytest.raises(SessionError, match="Cổng chưa được mở") as info:
        session.start_run()
    assert "'Kiểm kết nối bo' để kiểm liên lạc" in str(info.value) and len(calls) == 1
    link.close()
    assert link.release_port() is None
    session.close()


def test_simulated_link_builds_a_fresh_lidar_source_each_start_and_keeps_the_previous_on_refusal(scenario, cfg):
    def block_second(source, k):
        if k == 1:
            source.scanner.blocked = True            # lần START thứ hai: LiDAR mô phỏng bị che, không bắt được

    session = straight_session(scenario, cfg, goal_x=1.0)
    factory = RecordingFactory(block_second)
    link = lidar_link(factory=factory)
    session.set_vehicle_link(link)
    session.start_run()
    run_until_done(session)
    first_io, first_source = link.io, link.pose_source
    session.reset()
    with pytest.raises(SessionError, match="nguồn tư thế lidar_sim_localize chưa dùng được"):
        session.start_run()
    assert link.io is first_io and link.pose_source is first_source and len(factory.sources) == 2
    assert link.start_refusals[-1]["code"] == "START_NO_POSE_SOURCE"
    session.start_run()
    assert link.pose_source is factory.sources[2] and link.pose_source is not first_source
    assert link.io is not first_io and link.runs == 2
    session.request_stop()
    run_until_done(session)
    session.close()
