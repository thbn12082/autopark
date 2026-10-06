"""Sửa sau review đợt 2 (02/10/2026): `application/vehicle_link.py` và `ui/main_window.py`.

- Dự đoán tư thế tới io.now() (`LinkParams.predict_pose`, bật bởi `LinkParams.for_lidar`): mẫu OK của
  nguồn tư thế được dời từ dấu thời gian của mẫu tới io.now() bằng tốc độ, góc lái ĐO (mô hình xe đạp động học, chiều
  dài cơ sở của cấu hình xe) trước khi vào bộ bám (`observe`) và thế giới gương (`estimate`). Kiểm tuổi vẫn trên tuổi
  THÔ; poses.csv có các cột pred_*; phát lại log tái hiện đúng; tắt theo mặc định (SimTruthPose, bo ảo QEMU, băng cũ).
- "Kiểm kết nối bo" sau một lần Bắt đầu đỗ đã mở cổng: nhánh chạy giữ cổng mở giữa các lần chạy (bước
  0c), nên "Kiểm kết nối bo" đóng cổng đó trước khi mở (`VehicleLink.release_port`); lần Bắt đầu đỗ sau mở lại.

Không thiết bị: bo mô phỏng (SimVehicleIO + FirmwareModel), LiDAR MÔ PHỎNG (vòng quét dựng từ sa bàn), vòng quét tổng
hợp, cổng serial GIẢ (FirmwareSerialLoopback + ManualClock; `serial.Serial` bị thay). Bằng chứng mức MP; bo thật CHƯA
THỬ.
"""
from collections import deque
from dataclasses import replace
import csv
import json
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from autopark.application.session import Session, SessionState  # noqa: E402
from autopark.application.vehicle_link import (POSE_FIELDS, DriveMode, LinkParams, PoseSample,  # noqa: E402
                                               SimTruthPose, VehicleLink)
from autopark.domain.types import ParkingGoal, Pose, VehicleState, wrap_angle  # noqa: E402
from autopark.transport.vehicle_io import SIM_FIRMWARE_DEFAULT, SimIOConfig, SimVehicleIO  # noqa: E402

FAST_FW = replace(SIM_FIRMWARE_DEFAULT, boot_hold_ms=200)
SIM_CFG = SimIOConfig(firmware=FAST_FW)
LIDAR = LinkParams.for_lidar(0.25)


# ---- tiện ích -----------------------------------------------------------------------------------------------------
def straight_session(scenario, cfg, goal_x=2.0) -> Session:
    scenario.obstacles = []
    scenario.start = Pose(0.5, 1.0, 0.0)
    scenario.goal = ParkingGoal(Pose(goal_x, 1.0, 0.0))
    session = Session(scenario, cfg)
    assert session.plan_sync().ok
    return session


def run_until_done(session, step=0.5, max_calls=400):
    for _ in range(max_calls):
        session.advance(step)
        if not session.simulating:
            return
    raise AssertionError(f"Phiên không kết thúc, trạng thái {session.state}")


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class ScriptedPose:
    """Nguồn tư thế giả: mẫu `pose` đóng dấu io.now() − `age_s`, trạng thái `status`."""

    source_id = "lidar_gia"
    simulated = True

    def __init__(self, io, pose, age_s=0.0, status="OK", reason=""):
        self.io, self.pose, self.age_s, self.status, self.reason = io, pose, age_s, status, reason

    def latest(self):
        return PoseSample(self.pose, self.io.now() - self.age_s, self.source_id, True, self.status, self.reason)


def opened_link(scenario, cfg, params=LIDAR):
    """Liên kết VehicleIO qua bo mô phỏng tiêm vào, nguồn `ScriptedPose`, đã mở lần chạy (`begin_run`) ở điểm xuất
    phát."""
    scenario.obstacles = []
    io = SimVehicleIO(cfg, SIM_CFG, start=VehicleState(scenario.start, 0.0, 0.0, 0.0))
    source = ScriptedPose(io, scenario.start)
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=source, params=params)
    world = link.begin_run(scenario, cfg, 0.005)
    return link, io, source, world


def measured(io, speed, steer, age_s=0.0):
    """Khung telemetry mới nhất của bo mô phỏng với tốc độ, góc lái ĐO cho trước, nhận cách đây `age_s` (thay
    `io.latest`); steer None = khung không có góc lái đo."""
    tel = io.latest()
    tel = replace(tel, speed_mps=speed, steer_rad=steer, speed_ref_mps=speed or 0.0,
                  stamp=replace(tel.stamp, t=io.now() - age_s))
    io.latest = lambda: tel
    return tel


def arc(pose: Pose, speed: float, steer: float, dt: float, wheelbase: float) -> Pose:
    """Cung tròn của xe đạp động học, viết độc lập với `integrate_bicycle`: tâm quay cách trục sau R = L / tan(δ) về
    bên trái (R < 0: bên phải), xe quay quanh tâm đó một góc s / R với s = v·dt (s < 0: lùi)."""
    s = speed * dt
    if steer == 0.0:
        return Pose(pose.x + s * math.cos(pose.yaw), pose.y + s * math.sin(pose.yaw), pose.yaw)
    radius = wheelbase / math.tan(steer)
    cx, cy = pose.x - radius * math.sin(pose.yaw), pose.y + radius * math.cos(pose.yaw)
    yaw = pose.yaw + s / radius
    return Pose(cx + radius * math.sin(yaw), cy - radius * math.cos(yaw), wrap_angle(yaw))


# ---- dự đoán tư thế: một mẫu --------------------------------------------------------------------------------------
@pytest.mark.parametrize("speed, steer", [(0.10, 0.0), (0.10, 0.4), (-0.08, -0.3)],
                         ids=["thang", "re_trai", "lui_re_phai"])
def test_prediction_moves_an_old_ok_sample_along_the_measured_motion(scenario, cfg, speed, steer):
    """Mẫu OK cũ 0,12 s, telemetry mới có tốc độ, góc lái đo: bộ bám và thế giới gương nhận tư thế của mẫu dời tới
    io.now() theo cung tròn của mô hình xe đạp (thẳng, rẽ trái, lùi rẽ phải); poses.csv giữ mẫu THÔ và ghi phần dời."""
    link, io, source, world = opened_link(scenario, cfg)
    raw = Pose(1.2, 0.8, math.radians(35))
    source.pose, source.age_s = raw, 0.12
    measured(io, speed, steer)
    state, event = link.observe(0.0)
    assert event is None
    want = arc(raw, speed, steer, 0.12, cfg.wheelbase)
    assert (state.pose.x, state.pose.y, state.pose.yaw) == pytest.approx((want.x, want.y, want.yaw), abs=1e-12)
    assert (state.speed, state.steer) == (speed, steer)
    travelled = math.hypot(state.pose.x - raw.x, state.pose.y - raw.y)
    if steer == 0.0:
        assert travelled == pytest.approx(abs(speed) * 0.12, abs=1e-12) and state.pose.yaw == raw.yaw
    else:                                       # dây cung của cung dài |v|·dt trên đường tròn bán kính L / tan(δ)
        radius = cfg.wheelbase / math.tan(abs(steer))
        assert travelled == pytest.approx(2 * radius * math.sin(abs(speed) * 0.12 / (2 * radius)), abs=1e-12)
        assert math.copysign(1, wrap_angle(state.pose.yaw - raw.yaw)) == math.copysign(1, speed * steer)
    row = link.pose_rows[-1]
    assert row["use"] == "observe" and (row["x"], row["y"], row["yaw_rad"]) == (raw.x, raw.y, raw.yaw)
    assert row["pred_dt_s"] == pytest.approx(0.12) and (row["pred_speed_mps"], row["pred_steer_rad"]) == (speed, steer)
    assert (row["pred_x"], row["pred_y"], row["pred_yaw_rad"]) == (state.pose.x, state.pose.y, state.pose.yaw)
    mirrored = link.estimate(0.0, world.state)  # thế giới gương: cùng phép dời, cùng khung telemetry
    assert (mirrored.pose.x, mirrored.pose.y, mirrored.pose.yaw) == pytest.approx((want.x, want.y, want.yaw), abs=1e-12)
    assert link.pose_rows[-1]["use"] == "estimate" and link.pose_rows[-1]["pred_dt_s"] == pytest.approx(0.12)


def test_prediction_keeps_the_raw_age_checks_and_needs_a_fresh_measured_state(scenario, cfg):
    """Tuổi THÔ quyết định STALE_POSE (dự đoán không làm mẫu cũ thành mới); mẫu không OK không được dời; thiếu góc lái
    đo, telemetry cũ hay mẫu tuổi 0 thì tư thế nguyên vẹn và các cột pred_* để trống."""
    link, io, source, world = opened_link(scenario, cfg)
    raw = Pose(1.0, 1.0, 0.0)
    source.pose = raw
    measured(io, 0.1, 0.2)
    source.age_s = 0.26                                         # quá 0,25 s: dừng, dù dời được
    state, event = link.observe(0.0)
    assert state is None and event.code == "STALE_POSE" and link.pose_rows[-1]["pred_dt_s"] == ""
    source.age_s = 0.25                                         # đúng ngưỡng: còn dùng, dời đủ 0,25 s
    state, event = link.observe(0.0)
    assert event is None and state.pose.x > raw.x and link.pose_rows[-1]["pred_dt_s"] == pytest.approx(0.25)
    source.age_s, source.status, source.reason = 0.1, "POSE_LOST", "định vị (a) không OK 2 vòng liên tiếp"
    state, event = link.observe(0.0)
    assert state is None and event.code == "POSE_LOST" and link.pose_rows[-1]["pred_dt_s"] == ""
    mirrored = link.estimate(0.0, world.state)                  # thế giới gương giữ tư thế trước, không dời
    assert mirrored.pose == world.state.pose and link.pose_rows[-1]["pred_x"] == ""
    source.status, source.reason = "OK", ""
    source.age_s = 0.0                                          # tuổi 0 (như SimTruthPose): nguyên vẹn
    state, _ = link.observe(0.0)
    assert state.pose == raw and link.pose_rows[-1]["pred_dt_s"] == ""
    source.age_s = 0.1
    measured(io, 0.1, None)                                     # không có góc lái đo
    assert link.estimate(0.0, world.state).pose == raw and link.pose_rows[-1]["pred_x"] == ""
    measured(io, 0.1, 0.2, age_s=0.2)                           # telemetry cũ hơn 0,15 s
    assert link.estimate(0.0, world.state).pose == raw and link.pose_rows[-1]["pred_x"] == ""
    measured(io, 0.005, 0.2)                                    # đứng yên trong ngưỡng nhiễu (tham chiếu ≠ 0 vẫn dời)
    assert link.estimate(0.0, world.state).pose != raw


def test_prediction_is_off_by_default_and_recorded_in_link_json(scenario, cfg, tmp_path):
    """Mặc định tắt (LinkParams(), cả với max_pose_age_s riêng): tư thế của mẫu nguyên vẹn. `for_lidar` bật và ghi
    `predict_pose` vào params của link.json; băng cũ không có khóa này đọc lại thành tắt."""
    assert LinkParams().predict_pose is False and LinkParams(max_pose_age_s=0.25).predict_pose is False
    assert LIDAR.predict_pose is True and LIDAR.pose_age_limit_s == 0.25 and LIDAR.max_state_age_s == 0.15
    with pytest.raises(ValueError, match="predict_pose"):
        LinkParams(predict_pose=1)
    link, io, source, _ = opened_link(scenario, cfg, LinkParams(max_pose_age_s=0.25))
    source.pose, source.age_s = Pose(1.0, 1.0, 0.0), 0.12
    measured(io, 0.1, 0.2)
    state, event = link.observe(0.0)
    assert event is None and state.pose == source.pose and link.pose_rows[-1]["pred_dt_s"] == ""
    link.end_run(0.0, "STOPPED", "thử")
    info = json.loads(link.write_logs(tmp_path / "tat")["link.json"].read_text(encoding="utf-8"))
    assert info["params"]["predict_pose"] is False
    params = dict(info["params"])
    del params["predict_pose"]                                  # link.json ghi trước bản sửa
    assert LinkParams(**params).predict_pose is False
    link, *_ = opened_link(scenario, cfg)
    link.end_run(0.0, "STOPPED", "thử")
    written = link.write_logs(tmp_path / "bat")
    assert json.loads(written["link.json"].read_text(encoding="utf-8"))["params"]["predict_pose"] is True
    with open(written["poses.csv"], encoding="utf-8", newline="") as f:
        assert next(csv.reader(f)) == POSE_FIELDS
    assert POSE_FIELDS[-6:] == ["pred_dt_s", "pred_speed_mps", "pred_steer_rad", "pred_x", "pred_y", "pred_yaw_rad"]


def test_sim_truth_pose_is_never_moved(scenario, cfg):
    """SimTruthPose đóng dấu io.now() (tuổi 0): bật dự đoán cũng không đổi gì; lần chạy vẫn COMPLETED."""
    session = straight_session(scenario, cfg, goal_x=1.2)
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG, params=LIDAR)
    session.set_vehicle_link(link)
    session.start_run()
    assert isinstance(link.pose_source, SimTruthPose)
    run_until_done(session)
    assert session.state == SessionState.COMPLETED, session.stop_reason
    rows = [r for r in link.pose_rows if r["available"] == 1]
    assert rows and all(r["pred_dt_s"] == "" and float(r["t_io"]) == r["sample_t_io"] for r in rows)
    session.close()


# ---- dự đoán tư thế: cả lần chạy (MP) -------------------------------------------------------------------------------
class DelayedTruthPose:
    """MÔ PHỎNG nguồn tư thế trễ: tư thế THẬT của xe trong `SimVehicleIO` cách đây ít nhất `delay_s`, đóng dấu đúng lúc
    đó (như vòng quét LiDAR tới muộn, không nhiễu). Ghi tư thế thật theo io.now() của mỗi lần đọc (`truth_at`)."""

    source_id = "tre_gia"
    simulated = True

    def __init__(self, io, delay_s):
        self.io, self.delay_s = io, delay_s
        self.history = deque()
        self.truth_at = {}

    def latest(self):
        now, truth = self.io.now(), self.io.truth
        self.history.append((now, truth.pose))
        self.truth_at[now] = truth
        while len(self.history) > 1 and self.history[1][0] <= now - self.delay_s:
            self.history.popleft()
        t, pose = self.history[0]
        return PoseSample(pose, t, self.source_id, True)


def handed_pose_errors(link, source, use):
    """|tư thế giao cho bộ bám (use = observe) hay thế giới gương (estimate) − tư thế thật cùng lúc| (m), lúc xe chạy
    nhanh hơn 0,05 m/s."""
    out = []
    for row in link.pose_rows:
        truth = source.truth_at.get(row["t_io"])
        if row["use"] != use or row["available"] != 1 or truth is None or abs(truth.speed) < 0.05:
            continue
        x, y = (row["pred_x"], row["pred_y"]) if row["pred_x"] != "" else (row["x"], row["y"])
        out.append(math.hypot(x - truth.pose.x, y - truth.pose.y))
    return out


def test_delayed_pose_is_moved_to_now_during_a_run(scenario, cfg):
    """MP, đường thẳng, nguồn tư thế trễ 0,10 s (tuổi THÔ 0,02–0,11 s, như LiDAR mô phỏng 0,04–0,13 s). Đo 02/10/2026
    (575 lần observe, 2298 lần estimate lúc xe chạy): không dự đoán, tư thế giao cho bộ bám lệch tư thế thật tới 2,30 cm
    (trung bình 1,29 cm), thế giới gương cũng vậy; có dự đoán (`for_lidar`) lệch tới 0,34 cm (trung bình 0,08 cm), thế
    giới gương tới 0,34 cm. Phần còn lại là sai số của tốc độ, góc lái đo (trễ 20/10 ms, nhiễu 0,01 m/s: số GIẢ ĐỊNH của
    SimVehicleIO). Cả hai lần COMPLETED. Ngưỡng dưới đây rộng hơn số đo 2–4 lần."""
    result = {}
    for params in (LinkParams(max_pose_age_s=0.25), LIDAR):
        session = straight_session(scenario, cfg)
        io = SimVehicleIO(cfg, SIM_CFG, start=VehicleState(session.scenario.start, 0.0, 0.0, 0.0))
        source = DelayedTruthPose(io, 0.10)
        link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=source, params=params)
        session.set_vehicle_link(link)
        session.start_run()
        run_until_done(session)
        assert session.state == SessionState.COMPLETED, session.stop_reason
        observe, estimate = handed_pose_errors(link, source, "observe"), handed_pose_errors(link, source, "estimate")
        assert len(observe) > 100 and len(estimate) > 500
        result[params.predict_pose] = (max(observe), sum(observe) / len(observe), max(estimate))
        session.close()
    assert result[False][1] > 0.006 and result[False][0] > 0.012     # trễ 0,1 s ở tới ≈ 0,2 m/s: tới ≈ 2 cm
    assert result[True][0] < 0.008 and result[True][1] < 0.003 and result[True][2] < 0.008
    assert result[True][0] < result[False][0] / 3


def test_simulated_lidar_run_with_prediction_completes_logs_and_replays(scenario, cfg, tmp_path, monkeypatch):
    """Bo mô phỏng + LiDAR MÔ PHỎNG dựng như giao diện ("LiDAR mô phỏng": `for_lidar`): COMPLETED; poses.csv ghi phần
    dời của mỗi lần đọc trong lần chạy; lệnh trong commands.csv dùng đúng tư thế đã dời; phát lại log dựng lại đúng mọi
    quyết định (cùng mã dự đoán trên mẫu thô của băng). Đo 02/10/2026 (đường thẳng 0,7 m): 353/353 lần observe và
    1409/1409 lần estimate có dời, khoảng dời = tuổi thô 0,02–0,13 s (0,02 s ở nhịp đầu: vòng quét khởi động ngay trước
    START)."""
    pytest.importorskip("numpy")
    from autopark.application.lidar_pose_source import LidarSimPoseFactory
    from autopark.storage import run_store
    from autopark.storage.run_store import export_run, replay_vehicle_run
    from tests.lidar_fakes import default_config

    monkeypatch.setattr(run_store, "environment", lambda: {"test": True})
    session = straight_session(scenario, cfg, goal_x=1.2)
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG, params=LIDAR,
                                 pose_factory=LidarSimPoseFactory(default_config()))
    session.set_vehicle_link(link)
    session.start_run()
    run_until_done(session)
    assert session.state == SessionState.COMPLETED, session.stop_reason
    observe = [r for r in link.pose_rows if r["use"] == "observe" and r["available"] == 1]
    moved = [r for r in observe if r["pred_dt_s"] != ""]
    assert len(moved) >= 0.9 * len(observe) > 50
    assert all(0 < r["pred_dt_s"] <= 0.25 and r["pred_dt_s"] == pytest.approx(r["t_io"] - r["sample_t_io"])
               for r in moved)
    assert max(r["pred_dt_s"] for r in moved) > 0.09            # mẫu cũ tới gần một chu kỳ quét + trễ xử lý
    tracked = [r for r in link.command_rows if r["kind"] == "TRACK"]
    by_t = {r["t_session"]: r for r in moved}
    pairs = [(c, by_t[c["t_session"]]) for c in tracked if c["t_session"] in by_t]
    assert pairs and all((c["obs_x"], c["obs_y"]) == (p["pred_x"], p["pred_y"]) for c, p in pairs)
    bundle = export_run(session, tmp_path / "goi")
    rows = read_csv(bundle / "vehicle_io" / "poses.csv")
    assert list(rows[0])[-6:] == POSE_FIELDS[-6:] and any(r["pred_dt_s"] for r in rows)
    info = json.loads((bundle / "vehicle_io" / "link.json").read_text(encoding="utf-8"))
    assert info["params"]["predict_pose"] is True and info["params"]["max_pose_age_s"] == 0.25
    replayed, report = replay_vehicle_run(bundle)
    try:
        assert report.ok, "\n".join(report.lines())
        assert replayed.run_link.params.predict_pose is True
    finally:
        replayed.close()
        session.close()


# ---- "Kiểm kết nối bo" sau bước 0c -----------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def lidar_map(tmp_path_factory):
    """Như tests/test_pose_source_ui.py: bản đồ của map_builder ở hệ sa bàn, một chỗ đặt ở điểm xuất phát."""
    np = pytest.importorskip("numpy")
    from autopark.lidar.map_builder import MapBuildConfig, PlacementSpec, build_static_map, write_map
    from tests.lidar_fakes import default_config, static_slice, write_recording

    folder = tmp_path_factory.mktemp("ban_do") / "bản đồ sa bàn"
    sensor = default_config().mount.sensor_pose(Pose(0.5, 1.0, 0.0))
    pose = (sensor.x, sensor.y, sensor.yaw)
    rec = write_recording(folder.parent / "chỗ đặt 1", static_slice(pose, 2.0, np.random.default_rng(71)))
    write_map(build_static_map([PlacementSpec(rec)], anchor=pose, config=MapBuildConfig(skip_seconds=0.0)), folder)
    return folder


def test_probe_after_a_refused_observe_start_releases_the_port_the_link_holds(qapp, monkeypatch, lidar_map):
    """ui.lidar_app, bo COM7 + "LiDAR thật" + Quan sát: Bắt đầu đỗ mở COM7 ở bước 0c rồi START_CHECK từ chối (bo giả
    không đọc cảm biến, T8); liên kết GIỮ cổng mở. Cổng giả từ chối mở lần hai khi lần đầu còn mở, như Windows
    ("Access is denied"). Trước bản sửa "Kiểm kết nối bo" báo không mở được COM7; nay nó đóng cổng của liên kết (thanh
    trạng thái nói rõ), kiểm được bo, và lần Bắt đầu đỗ sau mở lại cổng (bước 0c)."""
    pytest.importorskip("numpy")
    import serial
    from PySide6.QtWidgets import QMessageBox

    from autopark.transport.firmware_model import FirmwareModel
    from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock
    from autopark.ui import lidar_app
    from tests.test_pose_source_ui import add_port, feed, select

    opened = []

    def exclusive_serial(port, *args, **kwargs):
        if any(p == port and not loop.closed for p, loop in opened):
            raise serial.SerialException(f"could not open port '{port}': PermissionError(13, 'Access is denied.', "
                                         f"None, 5)")
        loop = FirmwareSerialLoopback(FirmwareModel(replace(FAST_FW), boot_id=0xB0B0), ManualClock())
        opened.append((port, loop))
        return loop

    def refuse(*args, **kwargs):
        raise AssertionError("không được mở thiết bị thật")

    warnings = []
    monkeypatch.setattr(serial, "Serial", exclusive_serial)
    monkeypatch.setattr(serial, "serial_for_url", refuse)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: warnings.append(a)))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    bench, dock = lidar_app.build_window(None, port="COM9", recording=None)
    bench._timer.stop()
    dock.timer.stop()
    try:
        select(bench.combo_drive, DriveMode.OBSERVE.value)
        add_port(bench, "COM7")
        select(bench.combo_port, "COM7")
        source = bench.load_lidar_map(lidar_map, threaded=False)
        select(bench.combo_pose, "lidar_real")
        link = bench.session.vehicle_link
        assert link.pose_source is source and link.io.port == "COM7" and link.io.transport is None
        assert link.params.predict_pose is True                 # LiDAR thật: dựng bằng LinkParams.for_lidar
        assert bench.plan(sync=True).ok
        feed(source, 9)
        bench.run()                                             # bước 0c mở COM7, START_CHECK từ chối
        assert bench.session.state == SessionState.READY and warnings
        assert "START_CHECK" in [r["code"] for r in link.start_refusals]
        held = link.io.transport
        assert held is not None and len(opened) == 1            # liên kết giữ cổng mở
        report = bench._probe_board()                           # "Kiểm kết nối bo"
        assert report is not None and report.ok, bench.lbl_board_report.text()
        assert held.closed and link.io.transport is None and len(opened) == 2 and opened[1][1].closed
        assert "đã đóng COM7" in bench.statusBar().currentMessage()
        assert "Trước khi kiểm đã đóng COM7" in bench.lbl_board_report.text()
        feed(source, 3, seed=73)
        bench.run()                                             # lần sau: bước 0c mở lại cổng, START_CHECK lại từ chối
        assert len(opened) == 3 and link.io.transport is opened[2][1] and not opened[2][1].closed
        assert [r["code"] for r in link.start_refusals].count("START_CHECK") == 2
    finally:
        dock.shutdown()
        bench.close()
