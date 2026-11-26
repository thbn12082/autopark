"""Sự kiện dừng của phiên trong log VehicleIO (T13, thêm 02/10/2026).

Qua `VehicleIO`, mọi quyết định dừng của `Session` thành một dòng ``session_stop`` trong events.csv: đúng
`Session.safety_events` (cùng thứ tự, mã, nguồn, t_session, action), cộng yêu cầu dừng khi đang chạy (USER_STOP, mã của
cầu nối hợp nhất), USER_RESET và COLLISION. Mọi dòng events.csv/start_refusals.csv có cột t_perf; link.json có khóa
"clock". Nhánh SIM không đổi.

Mọi test chạy trên chuỗi MÔ PHỎNG (SimVehicleIO + FirmwareModel) hoặc cổng serial GIẢ (FirmwareSerialLoopback +
ManualClock); test giao diện dùng bo mô phỏng của cửa sổ. Không mở cổng nào, không camera, không LiDAR thật.
"""
import json
import os
import random
import time

import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.application.vehicle_link import EVENT_FIELDS, SESSION_STOP, DriveMode, LinkParams, VehicleLink
from autopark.domain.types import Obstacle
from autopark.fusion.bridge import ObstacleBridge
from autopark.fusion.fuse import fuse
from autopark.fusion.layers import LiveLidarLayer
from autopark.storage import run_store
from autopark.transport.firmware_model import FirmwareModel
from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock
from autopark.transport.vehicle_io import SerialVehicleIO
from tests.test_fusion import GRID
from tests.test_session_vehicle import (FAST_FW, SIM_CFG, FixedPose, FlakyPose, advance_until, drop_sensor, link_for,
                                        read_csv, run_until_done, sim_io, still_inputs, straight_session)

MAP_CHANGED_MESSAGE = "Vật cản mới: dừng, cập nhật và chờ lập lại đường"


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def session_rows(link: VehicleLink) -> list[dict]:
    return [r for r in link.event_rows if r["handling"] == SESSION_STOP]


def start_moving(scenario, cfg, *, mode=DriveMode.VEHICLE_IO, pose_source=None):
    """Lần chạy đường thẳng qua bo mô phỏng, tiến tới khi xe thật sự chạy (> 0,1 m/s)."""
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    pose = pose_source(io) if pose_source is not None else None
    session.set_vehicle_link(link_for(mode, io, pose))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    return session, io, pose


def invalid_lidar_map(session):
    """Bản đồ hợp nhất KHÔNG hợp lệ: lớp LiDAR bắt buộc chưa có vòng quét nào."""
    fused = fuse([LiveLidarLayer(GRID)], GRID, now=session.world.time)
    assert not fused.valid
    return fused


# tên: (gây lỗi giữa lúc chạy, (mã, nguồn) của dòng session_stop đầu tiên)
FAULTS = {
    "estop": (lambda s, io, pose: io.set_estop(True), ("VEHICLE_FAULT", "sim_vehicle_io")),
    "map_changed": (lambda s, io, pose: s.inject_obstacle(Obstacle("lidar_00001", 1.6, 1.0, 0.05, 0.05)),
                    ("MAP_CHANGED", "sim_safety")),
    "no_measured_state": (lambda s, io, pose: drop_sensor(io, steer_available=False),
                          ("NO_MEASURED_STATE", "vehicle_link")),
    "stale_pose": (lambda s, io, pose: setattr(pose, "dead", True), ("STALE_POSE", "vehicle_link")),
    "stale_telemetry": (lambda s, io, pose: io.set_link(False), ("STALE_TELEMETRY", "vehicle_link")),
}


@pytest.mark.parametrize("case", sorted(FAULTS))
def test_session_stop_rows_mirror_safety_events(scenario, cfg, case):
    act, first = FAULTS[case]
    session, io, pose = start_moving(scenario, cfg, pose_source=FlakyPose)
    act(session, io, pose)
    run_until_done(session, step=0.1)
    link = session.run_link
    rows = session_rows(link)
    events = session.safety_events
    assert [(r["code"], r["source"], r["t_session"], r["action"]) for r in rows] == \
        [(e.code, e.stamp.source_id, round(e.stamp.t, 4), e.action) for e in events]
    assert all(r["message"].startswith(e.message) for r, e in zip(rows, events))
    assert (rows[0]["code"], rows[0]["source"], rows[0]["action"]) == (*first, "STOP")
    assert all(isinstance(r["t_io"], float) and isinstance(r["t_perf"], float) for r in rows)
    t_io = [r["t_io"] for r in rows]
    assert t_io == sorted(t_io)
    # Quyết định dừng của phiên có trước (hoặc cùng bước với) lệnh dừng đầu tiên gửi tới bo.
    first_stop = next(r for r in link.command_rows if r["kind"] == "STOP")
    assert rows[0]["t_io"] <= first_stop["t_io"] and rows[0]["t_session"] <= first_stop["t_session"]
    if case == "map_changed":
        # mô tả vật chỉ có ở dòng log; SafetyEvent (và gói replay) giữ nguyên văn cũ
        assert "lidar_00001" in rows[0]["message"] and events[0].message == MAP_CHANGED_MESSAGE


def test_user_stop_is_logged_but_not_added_to_safety_events(scenario, cfg):
    session, io, _ = start_moving(scenario, cfg)
    session.request_stop()
    session.request_stop()                                       # đang STOPPING: không thêm dòng nào
    run_until_done(session, step=0.1)
    rows = session_rows(session.run_link)
    assert [(r["code"], r["source"], r["message"]) for r in rows] == [("USER_STOP", "user", "Người dùng yêu cầu dừng")]
    assert session.safety_events == [] and session.state == SessionState.STOPPED
    assert [set(e) for e in session.run_events] == [{"t", "kind", "reason"}]   # dừng của người dùng: như cũ


def test_fused_map_invalid_stop_from_bridge_is_logged(scenario, cfg):
    session, io, _ = start_moving(scenario, cfg)
    bridge = ObstacleBridge(session, prefix="lidar")
    fused = invalid_lidar_map(session)
    assert bridge.inject(fused) == [] and session.state == SessionState.STOPPING
    bridge.inject(fused)                                         # đang STOPPING: cầu nối đếm, phiên không ghi thêm
    run_until_done(session, step=0.1)
    rows = session_rows(session.run_link)
    assert [(r["code"], r["source"]) for r in rows] == [("FUSED_MAP_INVALID", "lidar_bridge")]
    assert rows[0]["message"].startswith("Bản đồ hợp nhất không hợp lệ") and bridge.stops == 2
    # Qua VehicleIO, mục "stop" của run_events mang mã và nguồn khác mặc định (để phát lại log dựng lại đúng dòng).
    assert [(e["kind"], e.get("code"), e.get("source")) for e in session.run_events] == \
        [("stop", "FUSED_MAP_INVALID", "lidar_bridge")]


def test_reset_while_running_logs_user_reset(scenario, cfg):
    session = straight_session(scenario, cfg)
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG)
    session.set_vehicle_link(link)
    session.start_run()
    assert session.world.state.speed == 0.0                     # vừa START, xe đứng yên: đặt lại được
    session.reset()
    assert [(r["code"], r["source"], r["action"]) for r in session_rows(link)] == [("USER_RESET", "user", "STOP")]
    assert link.result["outcome"] == "RESET" and session.safety_events == []


def test_collision_in_mirrored_world_is_logged(scenario, cfg):
    session, io, _ = start_moving(scenario, cfg)
    # Lỗi giả: một vật "đã biết" ngay trước xe, chỉ có trong thế giới gương (sa bàn lệch thực tế). Kiểm hình học của
    # MirroredWorld báo va chạm; xe trong bo mô phỏng không đụng gì.
    x, y = session.world.state.pose.to_world(0.30, 0.0)
    session.world.scenario.obstacles.append(Obstacle("hop_truoc", x, y, 0.10, 0.30))
    run_until_done(session, step=0.1)
    rows = session_rows(session.run_link)
    assert session.state == SessionState.FAULT and session.stop_reason.startswith("Va chạm")
    assert [(r["code"], r["source"], r["message"]) for r in rows] == \
        [("COLLISION", "sim_safety", session.stop_reason)]
    assert session.safety_events == []                           # va chạm không vào safety_events, như trước


def test_observe_mode_logs_session_stops_without_sending(scenario, cfg):
    session = straight_session(scenario, cfg)
    link = VehicleLink.simulated(DriveMode.OBSERVE, SIM_CFG)
    session.set_vehicle_link(link)
    session.start_run()
    link.human.set(0.1, 0.0)                                     # người lái mô phỏng chạy xe
    session.advance(0.5)
    session.request_stop()
    run_until_done(session)
    assert [(r["code"], r["source"]) for r in session_rows(link)] == [("USER_STOP", "user")]
    assert link.io.stats.commands_sent == 0 and session.state == SessionState.STOPPED


def test_realtime_session_stop_row_uses_the_io_clock(scenario, cfg):
    """Cổng serial GIẢ, ManualClock: t_io của dòng session_stop là io.now() lúc yêu cầu dừng, không phải
    t0 + t_session."""
    session = straight_session(scenario, cfg)
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW, boot_id=0xB007), clock, inputs=still_inputs)
    io = SerialVehicleIO(loop, clock=clock, rng=random.Random(1))
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FixedPose(io, scenario.start))
    session.set_vehicle_link(link)
    session.start_run()
    try:
        for _ in range(5):
            loop.advance(100)
            session.advance(0.016)
        loop.advance(30)                                         # đồng hồ io tiến 30 ms, phiên chưa bước
        session.request_stop()
        row = session_rows(link)[0]
        assert (row["code"], row["source"]) == ("USER_STOP", "user")
        assert row["t_io"] == io.now() and row["t_session"] == round(session.world.time, 4)
        lead = (row["t_io"] - link._io_t0) - session.world.time
        assert 0.030 - 1e-9 <= lead <= 0.030 + Session.PHYSICS_DT + 1e-9
    finally:
        session.close()


def test_write_logs_has_t_perf_and_clock(scenario, cfg, tmp_path):
    session, io, _ = start_moving(scenario, cfg)
    session.request_stop()
    run_until_done(session, step=0.1)
    link = session.run_link
    session.reset()
    assert session.plan_sync().ok
    link.params = LinkParams(fresh_timeout_s=0.001, start_samples=50)   # START bị từ chối: có dòng start_refusals
    with pytest.raises(SessionError, match="liên lạc"):
        session.start_run()
    written = link.write_logs(tmp_path / "lan_vehicle_io")
    assert EVENT_FIELDS.index("t_perf") == EVENT_FIELDS.index("t_io") + 1
    for name in ("events.csv", "start_refusals.csv"):
        assert written[name].read_text(encoding="utf-8").splitlines()[0].split(",") == EVENT_FIELDS
    events = read_csv(written["events.csv"])
    refusals = read_csv(written["start_refusals.csv"])
    assert [r["code"] for r in refusals] == ["START_NO_LINK"]
    assert all(float(r["t_perf"]) > 0 for r in events + refusals)
    stops = [r for r in events if r["handling"] == SESSION_STOP]
    assert [(r["code"], r["source"]) for r in stops] == [("USER_STOP", "user")]
    info = json.loads(written["link.json"].read_text(encoding="utf-8"))
    clock = info["clock"]
    assert set(clock) == {"t_io_at_start", "t_perf_at_start"} and "clock" not in link.describe()
    assert clock["t_io_at_start"] == link._io_t0 and isinstance(clock["t_perf_at_start"], float)
    assert all(clock["t_perf_at_start"] <= float(r["t_perf"]) for r in stops)
    assert info["io_simulated"] is True                          # t_io là đồng hồ mô phỏng: không đổi sang perf


def test_link_json_clock_converts_io_time_to_perf_counter_on_a_wall_clock_board(scenario, cfg, tmp_path):
    """Sau review 02/10/2026: phép đổi mà khóa "clock" của link.json phục vụ, t_perf = t_io + (t_perf_at_start −
    t_io_at_start), với io chạy theo đồng hồ tường: cổng serial GIẢ, đồng hồ io = perf_counter() − t0 + 500 s (như đồng
    hồ mặc định của SerialVehicleIO, dời 500 s để phép đổi sai dấu hay sai gốc lệch cỡ trăm giây)."""
    t0 = time.perf_counter()
    session = straight_session(scenario, cfg)
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW, boot_id=0xB007), ManualClock(), inputs=still_inputs)
    io = SerialVehicleIO(loop, clock=lambda: time.perf_counter() - t0 + 500.0, rng=random.Random(2))
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FixedPose(io, scenario.start))
    session.set_vehicle_link(link)
    try:
        session.start_run()
        session.request_stop()
        clock = json.loads(link.write_logs(tmp_path / "dong_ho")["link.json"].read_text(encoding="utf-8"))["clock"]
        offset = clock["t_perf_at_start"] - clock["t_io_at_start"]
        assert offset == pytest.approx(t0 - 500.0, abs=0.05)
        row = session_rows(link)[0]
        assert row["code"] == "USER_STOP" and row["t_io"] > 500.0
        # Lệch chỉ do luồng bị ngắt giữa hai lần đọc đồng hồ khi máy bận (thường vài µs), không phải do phép đổi.
        assert abs(row["t_io"] + offset - row["t_perf"]) < 0.05
    finally:
        session.close()


def test_nothing_is_logged_after_the_run_has_ended(scenario, cfg):
    """Sau review 02/10/2026: mọi dòng session_stop ghi trước end_run; sau đó không thêm dòng nào: bấm Dừng lần nữa,
    cầu nối báo bản đồ hỏng, chèn vật (bị từ chối), đặt lại. Bất biến này đứng nhờ các kiểm trạng thái của Session (lớp
    nối không tự chặn), nên được ghim ở đây."""
    session, io, _ = start_moving(scenario, cfg)
    session.request_stop()
    run_until_done(session, step=0.1)
    link = session.run_link
    assert session.state == SessionState.STOPPED and link.result is not None
    rows, safety = list(link.event_rows), list(session.safety_events)
    session.request_stop()
    assert ObstacleBridge(session, prefix="lidar").inject(invalid_lidar_map(session)) == []
    with pytest.raises(SessionError):
        session.inject_obstacle(Obstacle("muon", 1.6, 1.0, 0.05, 0.05))
    session.reset()
    assert session.state == SessionState.READY
    assert link.event_rows == rows and session.safety_events == safety
    assert [(r["code"], r["handling"]) for r in rows if r["handling"] == SESSION_STOP] == [("USER_STOP", SESSION_STOP)]
    session.close()


def test_a_failing_io_clock_never_blocks_the_stop(scenario, cfg):
    """Sửa sau review 02/10/2026: lời hứa "không ném lỗi" của `log_session_event` được bảo đảm. Đồng hồ io hỏng đúng lúc
    yêu cầu dừng: phiên vẫn sang STOPPING; dòng session_stop vẫn có, t_io trống, lời lỗi trong message. Lỗi khác khi ghi
    thì mất dòng, không ném."""
    session, io, _ = start_moving(scenario, cfg)
    link = session.run_link

    def broken_clock():
        raise OSError("đồng hồ hỏng giả")

    io.now = broken_clock
    try:
        session.request_stop()
    finally:
        del io.now                                               # đồng hồ của lớp trở lại
    assert session.state == SessionState.STOPPING
    row = session_rows(link)[0]
    assert (row["code"], row["source"], row["t_io"]) == ("USER_STOP", "user", "") and isinstance(row["t_perf"], float)
    assert row["message"].startswith("Người dùng yêu cầu dừng (không đọc được io.now(): ")
    assert "đồng hồ hỏng giả" in row["message"]
    run_until_done(session, step=0.1)
    assert session.state == SessionState.STOPPED
    count = len(link.event_rows)
    link.log_session_event("không phải số", "user", "USER_STOP", "t_session hỏng")        # round() ném TypeError
    assert len(link.event_rows) == count
    session.close()


def test_link_json_clock_is_null_before_any_run(tmp_path):
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG)
    info = json.loads(link.write_logs(tmp_path / "chua_chay")["link.json"].read_text(encoding="utf-8"))
    assert info["clock"] == {"t_io_at_start": None, "t_perf_at_start": None} and info["runs"] == 0


def test_sim_branch_safety_events_unchanged(scenario, cfg):
    session = straight_session(scenario, cfg)
    session.start_run()
    session.advance(1.0)
    session.inject_obstacle(Obstacle("new", 1.6, 1.0, 0.05, 0.05))
    run_until_done(session)
    assert session.run_link is None
    assert [e.code for e in session.safety_events] == ["MAP_CHANGED", "WAIT_REPLAN"]
    assert session.safety_events[0].message == MAP_CHANGED_MESSAGE


def test_sim_branch_stop_request_keeps_the_old_run_events(scenario, cfg):
    session = straight_session(scenario, cfg)
    session.start_run()
    session.advance(0.5)
    ObstacleBridge(session, prefix="lidar").inject(invalid_lidar_map(session))
    assert session.state == SessionState.STOPPING and session.run_link is None
    assert [set(e) for e in session.run_events] == [{"t", "kind", "reason"}]   # SIM: không thêm code/source


def test_window_stop_in_vehicle_io_logs_user_stop_and_exports(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from autopark.ui.app import DEFAULT_SCENARIO, build_window

    window = build_window(DEFAULT_SCENARIO)
    try:
        combo = window.combo_drive
        combo.setCurrentIndex(combo.findData(DriveMode.VEHICLE_IO.value))
        assert window.session.drive_mode == DriveMode.VEHICLE_IO and window.board_port() is None   # bo mô phỏng
        assert window.plan(sync=True).ok
        window.run()
        io = window.session.run_link.io
        for _ in range(100):
            window.advance_by(0.1)
            if io.truth.speed > 0.05:
                break
        window.stop()                                            # nút Dừng (cũng là phím Esc)
        for _ in range(100):
            window.advance_by(0.1)
            if not window.session.simulating:
                break
        assert window.session.state == SessionState.STOPPED
        assert [(r["code"], r["source"]) for r in session_rows(window.session.run_link)] == [("USER_STOP", "user")]
        out = tmp_path / "lan.csv"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), "CSV (*.csv)"))
        # T9: _export_log xuất cả gói phát lại của lần chạy qua VehicleIO; không gọi PowerShell trong test.
        monkeypatch.setattr(run_store, "environment", lambda: {"test": True})
        window._export_log()
        events = read_csv(tmp_path / "lan_vehicle_io" / "events.csv")
        assert list(events[0]) == EVENT_FIELDS
        stops = [r for r in events if r["handling"] == SESSION_STOP]
        assert [(r["code"], r["source"]) for r in stops] == [("USER_STOP", "user")] and float(stops[0]["t_perf"]) > 0
    finally:
        window.close()
