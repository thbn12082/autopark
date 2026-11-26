"""Bo ảo QEMU trong phiên đỗ với xe mô phỏng phía laptop (thêm 02/10/2026; `transport/qemu_plant.py`, phần QEMU của
`application/vehicle_link.py`).

Mọi test ở đây dùng bo ảo GIẢ (`tests/qemu_fakes.py`: FirmwareModel = bản tham chiếu byte-đúng của firmware trong QEMU,
`ManualClock`): không chạy QEMU, không mở cổng nào. Phiên đỗ qua QEMU thật nằm ở tests/test_firmware_qemu.py.
"""
from dataclasses import replace
import json
import math
import random

import pytest

from autopark.application.session import SessionError, SessionState
from autopark.application.vehicle_link import (DriveMode, NoPoseSource, PlantHumanDriver, QemuPlantPose, SimTruthPose,
                                               VehicleLink, VehicleLinkError)
from autopark.domain.types import Pose, wrap_angle
from autopark.safety.fault_injection import FreezablePoseSource
from autopark.storage import run_store
from autopark.storage.run_store import export_run, replay_vehicle_run
from autopark.transport.loopback import ManualClock
from autopark.transport.protocol import Action, Command, Fault, Hello, Request, State, StopReason, TelemetryFlag
from autopark.transport.qemu_plant import (QEMU_EVIDENCE, PlantConfig, QemuPlantVehicleIO, check_emulator_url,
                                           load_plant_config)
from autopark.transport.vehicle_io import SerialVehicleIO, SimVehicleIO, VehicleIOError
from tests.qemu_fakes import BOOT_ID, URL, FakeQemuBoard, FakeQemuSource
from tests.test_session_vehicle import FixedPose, straight_session

MEASURED = TelemetryFlag.SPEED_VALID | TelemetryFlag.STEER_VALID


def plant_io(board: FakeQemuBoard, **kwargs) -> QemuPlantVehicleIO:
    io = QemuPlantVehicleIO(board, rng=random.Random(4), **kwargs)
    io.reopen()
    return io


def pump(io, board: FakeQemuBoard, ms: int, step_ms: int = 20, send=None) -> list:
    """Bo chạy `ms` theo từng `step_ms`; mỗi bước (tùy chọn) gửi một lệnh rồi đọc không chờ, như vòng 50 Hz."""
    frames = []
    for _ in range(ms // step_ms):
        if send is not None:
            send()
        board.advance(step_ms)
        frames += io.poll(block=False)
    return frames


def qemu_session(scenario, cfg, mode=DriveMode.VEHICLE_IO, board: FakeQemuBoard | None = None):
    session = straight_session(scenario, cfg)
    board = board or FakeQemuBoard().start()
    link = VehicleLink.qemu_board(mode, FakeQemuSource(board), clock=board.clock)
    session.set_vehicle_link(link)
    return session, link, board


def drive(session, board: FakeQemuBoard, *, step_ms: int = 20, max_steps: int = 3000) -> None:
    """Thời gian thực trên đồng hồ tay: bo chạy một nhịp giao diện rồi `Session.advance` (real_dt bị bỏ qua)."""
    for _ in range(max_steps):
        board.advance(step_ms)
        session.advance(step_ms / 1000)
        if not session.simulating:
            return
    raise AssertionError(f"Phiên không kết thúc, trạng thái {session.state}")


# ---- cấu hình và URL ------------------------------------------------------------------------------------------------
def test_plant_config_round_trip_and_rejects_unknown_keys():
    config = PlantConfig(telemetry_period_ms=25, step_ms=4, speed_noise_std_mps=0.01,
                         steer_noise_std_rad=math.radians(0.3), seed=7, notes="thử")
    again = PlantConfig.from_dict(json.loads(json.dumps(config.to_dict())))
    assert replace(again, steer_noise_std_rad=config.steer_noise_std_rad) == config
    assert again.steer_noise_std_rad == pytest.approx(config.steer_noise_std_rad, rel=1e-12)
    assert config.to_dict()["plant"]["steer_noise_std_deg"] == pytest.approx(0.3)
    shipped = load_plant_config()                              # configs/bo_ao_qemu.json của repo
    assert (shipped.telemetry_period_ms, shipped.step_ms, shipped.speed_noise_std_mps, shipped.steer_noise_std_rad,
            shipped.seed) == (20, 5, 0.0, 0.0, 0) and "GIẢ ĐỊNH" in shipped.notes
    good = config.to_dict()
    for broken in ({**good, "telemetry_period": 20}, {**good, "plant": {**good["plant"], "step": 5}},
                   {**good, "schema_version": 2}, {k: v for k, v in good.items() if k != "schema_version"},
                   {**good, "telemetry_period_ms": 10}, {**good, "telemetry_period_ms": "20"},
                   {**good, "plant": {**good["plant"], "step_ms": 0}},
                   {**good, "plant": {**good["plant"], "speed_noise_std_mps": -0.1}},
                   {**good, "plant": {**good["plant"], "steer_noise_std_deg": "0.3"}}, {**good, "plant": []}):
        with pytest.raises(ValueError):
            PlantConfig.from_dict(broken)


@pytest.mark.parametrize("url", ["COM5", "rfc2217://127.0.0.1:1", "socket://192.168.1.5:5555",
                                 "socket://localhost:5555", "socket://127.0.0.1:0", "socket://127.0.0.1",
                                 "socket://127.0.0.1:70000", "socket://127.0.0.1:5555\n", None])
def test_plant_io_refuses_non_emulator_urls(url):
    board = FakeQemuBoard()
    board.url = url
    opened = []
    board.transport_opener = lambda *a, **k: opened.append("opener") or (lambda: opened.append("open"))
    with pytest.raises(ValueError, match="socket://127.0.0.1:<cổng>"):
        QemuPlantVehicleIO(board)
    with pytest.raises(ValueError):
        check_emulator_url(url)
    assert opened == []                                        # không hỏi hàm mở, không mở gì
    assert check_emulator_url(URL) == 5999


# ---- io với xe mô phỏng ---------------------------------------------------------------------------------------------
def test_frames_before_placement_have_no_measured_state():
    board = FakeQemuBoard().start()
    io = plant_io(board)
    info = io.connect()
    assert info.boot_id == BOOT_ID and info.telemetry_period_s == 0.02     # chu kỳ xin trong HELLO: 20 ms
    io.wait_ready()
    frames = pump(io, board, 200)
    assert len(frames) >= 9 and io.plant_sample() is None
    for tel in frames:
        assert tel.speed_mps is None and tel.steer_rad is None and not tel.flags & MEASURED
        assert tel.stamp.source_id == "qemu_board" and tel.to_domain() is None
    io.close()
    assert board.client is None


def test_plant_follows_reference_and_keeps_raw_flags(cfg):
    board = FakeQemuBoard().start()
    io = plant_io(board)
    start = Pose(0.5, 1.0, 0.0)
    io.place_vehicle(cfg, start)
    io.connect()
    io.wait_ready()
    io.arm()
    lim, period = io.hello.limits, io.hello.telemetry_period_s
    assert period == 0.02
    io.take_new()
    frames = pump(io, board, 1000, send=lambda: io.send(0.2, 0.1, validity_s=0.15))
    assert len(frames) >= 45 and any(f.state == State.RUNNING for f in frames)
    for tel in frames:
        assert tel.speed_mps is not None and tel.steer_rad is not None
        assert not tel.flags & MEASURED                        # cờ của firmware giữ nguyên: firmware không đo gì
        assert abs(tel.speed_mps - tel.speed_ref_mps) <= lim.max_accel_mps2 * period + 1e-3
        assert abs(tel.steer_rad - tel.steer_ref_rad) <= lim.max_steer_rate_rad_s * period + 1e-3
    assert max(f.speed_mps for f in frames) == pytest.approx(0.2, abs=1e-3)
    pose, t_last = io.plant_sample()
    assert t_last == frames[-1].stamp.t                         # tư thế theo khung cuối, không ngoại suy
    travelled = sum(0.5 * (a.speed_mps + b.speed_mps) * (b.stamp.t - a.stamp.t) for a, b in zip(frames, frames[1:]))
    chord = math.hypot(pose.x - start.x, pose.y - start.y)
    assert chord == pytest.approx(travelled, abs=0.002) and chord > 0.05
    assert wrap_angle(pose.yaw - start.yaw) > 0                 # lái dương (trái) khi tiến: hướng tăng
    io.close()


def test_plant_stops_when_command_expires(cfg):
    board = FakeQemuBoard().start()
    io = plant_io(board)
    io.place_vehicle(cfg, Pose(0.5, 1.0, 0.0))
    io.connect()
    io.wait_ready()
    io.arm()
    pump(io, board, 600, send=lambda: io.send(0.2, 0.0, validity_s=0.15))
    assert io.latest().speed_mps > 0.1
    frames = pump(io, board, 800, send=io.ping)                 # không gửi lệnh nữa; PING giữ liên lạc
    expired = [f for f in frames if f.state == State.ARMED and f.stop_reason == StopReason.COMMAND_TIMEOUT]
    assert expired and frames[-1].speed_ref_mps == 0.0 and frames[-1].speed_mps == 0.0
    still = [io.plant_sample()[0]]
    pump(io, board, 200, send=io.ping)
    still.append(io.plant_sample()[0])
    assert still[0] == still[1]                                 # xe mô phỏng đứng yên
    io.close()


def test_connect_refuses_foreign_boot_id():
    board = FakeQemuBoard().start()
    board.hello = replace(board.hello, boot_id=0x12345678)      # bo ảo đã khởi động lại / thiết bị khác chiếm cổng
    io = plant_io(board)
    with pytest.raises(VehicleIOError) as err:
        io.connect()
    assert "12345678" in str(err.value) and f"{BOOT_ID:08x}" in str(err.value) and not io.connected
    with pytest.raises(VehicleIOError):
        io.arm()                                                # không có phiên: không ARM được
    io.close()
    board.hello = None
    io = plant_io(board)
    written = len(board.loop.written)
    with pytest.raises(VehicleIOError, match="boot_id"):
        io.connect()
    assert not io.connected and len(board.loop.written) == written     # không gửi cả HELLO
    io.close()


def test_qemu_pose_binding_rules(cfg):
    board = FakeQemuBoard().start()
    io, other = QemuPlantVehicleIO(board), QemuPlantVehicleIO(board)
    with pytest.raises(ValueError, match="QemuPlantPose chỉ dùng"):
        VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=QemuPlantPose(other))
    sim = SimVehicleIO(cfg)
    for pose_source in (SimTruthPose(sim), FixedPose(io, Pose(0.5, 1.0, 0.0)), NoPoseSource()):
        with pytest.raises(ValueError):
            VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=pose_source)
    wrapped = FreezablePoseSource(QemuPlantPose(io), clock=io.now)   # lớp bọc tiêm lỗi vẫn được nhận
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=wrapped)
    assert link.pose_source is wrapped
    with pytest.raises(ValueError, match="QemuPlantPose"):
        VehicleLink(DriveMode.VEHICLE_IO, SerialVehicleIO(None, port="COM7"), pose_source=QemuPlantPose(io))
    with pytest.raises(ValueError, match="QemuPlantPose"):
        VehicleLink(DriveMode.OBSERVE, sim, pose_source=QemuPlantPose(io))


def test_explicit_qemu_io_link_is_labelled_and_closed_like_qemu_board(scenario, cfg):
    """Sửa sau review 02/10/2026: liên kết dựng thẳng với `QemuPlantVehicleIO` (luật ghép cho phép, ví dụ lớp bọc tiêm
    lỗi quanh `QemuPlantPose`) là liên kết bo ảo như `qemu_board()`: `is_qemu`, `virtual_board`, không phải phần cứng
    chấp hành, bằng chứng qemu_firmware_simulated_vehicle, khóa board/plant của bo ảo, đóng socket sau lần chạy và sau
    lần START bị từ chối. Trước đó nó tự nhận là bo thật chưa thử (hardware_untested) và giữ socket một client mở."""
    session = straight_session(scenario, cfg)
    board = FakeQemuBoard().start()
    io = QemuPlantVehicleIO(board, rng=random.Random(4))
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FreezablePoseSource(QemuPlantPose(io), clock=io.now))
    assert link.is_qemu and link.virtual_board and not link.hardware_actuators and link._close_after_run
    info = link.describe()
    assert (info["evidence"], info["io"], info["virtual_board"], info["pose_simulated"]) == \
        (QEMU_EVIDENCE, "QemuPlantVehicleIO", True, True)
    assert info["board"]["kind"] == "qemu" and info["board"]["hello"]["boot_id"] == f"0x{BOOT_ID:08x}"
    assert info["plant"] == PlantConfig().to_dict() and info["port"] == URL
    session.set_vehicle_link(link)
    board.stall(200)                                            # LOOP_OVERRUN: START bị từ chối sau khi mở socket
    board.advance(20)
    with pytest.raises(SessionError) as err:
        session.start_run()
    assert "bo ảo QEMU: máy bận" in str(err.value) and board.opened == 1
    assert board.client is None and io.transport is None        # không để kết nối nào mở sau lần bị từ chối
    report = link.clear_fault()
    assert report.outcome == "CLEARED" and link.board_actions[-1]["target"] == f"bo ảo QEMU {URL}"
    assert "KHÔNG phải bo thật" in "\n".join(report.lines()) and board.client is None
    io.place_vehicle(cfg, session.scenario.start)               # liên kết dựng thẳng: người dùng tự đặt xe mô phỏng
    session.start_run()
    assert session.state == SessionState.RUNNING and board.opened == 3 and board.client is not None
    assert link.release_port() is None and board.client is not None     # đang chạy: không bao giờ đóng cổng
    drive(session, board)
    assert session.state == SessionState.COMPLETED, session.stop_reason
    assert board.client is None and io.transport is None        # QEMU chỉ một client: đóng sau lần chạy
    assert session.run_snapshot["vehicle_link"]["evidence"] == QEMU_EVIDENCE
    session.close()


# ---- phiên đỗ qua bo ảo giả ----------------------------------------------------------------------------------------
def test_session_parks_through_fake_qemu_board(scenario, cfg):
    session, link, board = qemu_session(scenario, cfg)
    assert link.is_qemu and link.realtime and link.io is None
    before = link.describe()
    assert (before["io"], before["pose_source"], before["board"], before["evidence"]) == \
        ("QemuPlantVehicleIO", "qemu_plant_pose", {"kind": "qemu"}, QEMU_EVIDENCE)
    session.start_run()
    assert session.state == SessionState.RUNNING and board.opened == 1
    check = next(r for r in link.event_rows if r["code"] == "START_CHECK")
    assert check["message"].startswith("Đạt:") and "giới hạn: khớp" in check["message"]
    assert link.limits_check.ok
    drive(session, board)
    assert session.state == SessionState.COMPLETED, session.stop_reason
    messages = board.host_messages()
    assert {type(m) for m in messages} <= {Hello, Request, Command}
    assert sum(isinstance(m, Command) for m in messages) == link.io.stats.commands_sent > 50
    rows = link.telemetry_rows
    assert rows and all(not int(r["flags"]) & MEASURED and r["speed_mps"] != "" for r in rows)
    assert "NO_MEASURED_STATE" not in [e.code for e in session.safety_events]
    info = link.describe()
    assert (info["evidence"], info["io"], info["io_source_id"], info["pose_source"]) == \
        (QEMU_EVIDENCE, "QemuPlantVehicleIO", "qemu_board", "qemu_plant_pose")
    assert info["pose_simulated"] is True and info["io_simulated"] is False and info["port"] == URL
    assert info["board"]["kind"] == "qemu" and info["board"]["hello"]["boot_id"] == f"0x{BOOT_ID:08x}"
    assert info["plant"]["telemetry_period_ms"] == 20 and session.run_snapshot["vehicle_link"]["board"]["kind"] == "qemu"
    assert link.io.transport is None and board.client is None   # đóng sau lần chạy: QEMU chỉ một client
    assert [r["pose_simulated"] for r in link.command_rows[:1]] == [1]
    assert {e.stamp.source_id for e in session.safety_events} <= {"qemu_board", "vehicle_link", "sim_safety"}
    first_io = link.io
    session.reset()
    session.start_run()                                         # lần START thứ hai: mở lại, xe về điểm xuất phát
    assert board.opened == 2 and link.io is first_io and link.io.transport is not None
    assert link.io.plant_sample()[0] == scenario.start
    session.request_stop()
    drive(session, board)
    assert session.state == SessionState.STOPPED and link.runs == 2 and board.client is None
    session.close()


def test_start_refused_before_any_io_when_board_not_running(scenario, cfg):
    session, link, board = qemu_session(scenario, cfg)
    session.start_run()
    for _ in range(25):
        board.advance(20)
        session.advance(0.02)
    session.request_stop()
    drive(session, board)
    assert session.state == SessionState.STOPPED and link.command_rows
    logs = (list(link.command_rows), list(link.telemetry_rows), dict(link.result))
    io, opened, written = link.io, board.opened, len(board.loop.written)
    board.stop()                                                # QEMU đã tắt
    session.reset()
    with pytest.raises(SessionError, match="Khởi động bo ảo"):
        session.start_run()
    assert [r["code"] for r in link.start_refusals] == ["START_NO_QEMU_BOARD"] and link.refused_starts == 1
    assert link.start_refusals[0]["t_io"] == board.clock()      # đồng hồ của liên kết
    assert "Chưa mở kết nối, không gửi gì" in link.start_refusals[0]["message"]
    assert board.opened == opened and len(board.loop.written) == written     # không I/O nào
    assert (link.command_rows, link.telemetry_rows, link.result) == logs and link.io is io
    # Liên kết mới, chưa chạy lần nào: t_io vẫn là đồng hồ của liên kết.
    fresh = VehicleLink.qemu_board(DriveMode.VEHICLE_IO, FakeQemuSource(None), clock=ManualClock(7250))
    session.set_vehicle_link(fresh)
    with pytest.raises(SessionError, match="bo ảo chưa chạy"):
        session.start_run()
    assert fresh.io is None and fresh.start_refusals[0]["t_io"] == 7.25
    session.close()


def test_start_refused_when_socket_cannot_open(scenario, cfg):
    session, link, board = qemu_session(scenario, cfg)
    board.refuse_connections = True
    with pytest.raises(SessionError, match="Không mở được kết nối tới bo ảo socket://127.0.0.1:5999"):
        session.start_run()
    assert [r["code"] for r in link.start_refusals] == ["START_NO_LINK"]
    assert link.io is None and board.client is None and board.opened == 0
    board.refuse_connections = False
    session.start_run()
    assert session.state == SessionState.RUNNING
    session.close()
    assert board.client is None


def test_loop_overrun_refuses_start_then_clear_fault_then_start(scenario, cfg):
    session, link, board = qemu_session(scenario, cfg)
    board.stall(200)                                            # QEMU bị máy chủ bỏ đói 200 ms
    board.advance(20)
    assert board.firmware.state == State.FAULT and board.firmware.fault == Fault.LOOP_OVERRUN
    with pytest.raises(SessionError) as err:
        session.start_run()
    assert "LOOP_OVERRUN" in str(err.value) and "bo ảo QEMU: máy bận" in str(err.value)
    assert board.client is None and link.io is None
    assert link.clear_fault_blocker is None
    report = link.clear_fault()
    assert report.outcome == "CLEARED" and report.commands_sent == 0 and board.client is None
    row = link.board_actions[-1]
    assert row["target"] == f"bo ảo QEMU {URL}" and row["outcome"] == "CLEARED"
    text = "\n".join(report.lines())
    assert "bo ảo QEMU" in text and "KHÔNG phải bo thật" in text and "bo thật qua" not in text
    session.start_run()
    assert session.state == SessionState.RUNNING
    session.request_stop()
    drive(session, board)
    assert session.state == SessionState.STOPPED
    board.stop()
    assert "bo ảo QEMU chưa chạy" in link.clear_fault_blocker
    with pytest.raises(VehicleLinkError, match="bo ảo QEMU chưa chạy"):
        link.clear_fault()
    session.close()


def test_observe_through_fake_qemu_board_human_drives_plant(scenario, cfg):
    session, link, board = qemu_session(scenario, cfg, DriveMode.OBSERVE)
    written = len(board.loop.written)
    session.start_run()
    human = link.human
    assert isinstance(human, PlantHumanDriver)
    start = link.io.plant_sample()[0]
    human.set(0.1, 0.2)
    assert link.io.human_targets == (0.1, 0.2)
    for _ in range(60):
        board.advance(20)
        session.advance(0.02)
    pose = link.io.plant_sample()[0]
    assert pose.distance_to(start) > 0.05 and wrap_angle(pose.yaw - start.yaw) > 0
    human.set(5.0, -5.0)                                        # kẹp theo giới hạn cấu hình xe
    assert (human.speed, human.steer) == (cfg.max_speed, -cfg.max_steer)
    assert not any(isinstance(m, Command) for m in board.host_messages(written))
    assert link.telemetry_rows and all(r["state"] == "DISARMED" for r in link.telemetry_rows)
    session.request_stop()
    drive(session, board)
    assert session.state == SessionState.STOPPED and board.client is None
    session.close()


def test_close_mid_run_sends_stop_and_disarm_and_closes_socket(scenario, cfg):
    session, link, board = qemu_session(scenario, cfg)
    session.start_run()
    for _ in range(40):
        board.advance(20)
        session.advance(0.02)
    assert session.state == SessionState.RUNNING and board.firmware.state == State.RUNNING
    written = len(board.loop.written)
    session.close()
    tail = board.host_messages(written)
    assert isinstance(tail[-2], Command) and not tail[-2].enable
    assert isinstance(tail[-1], Request) and Action(tail[-1].action) == Action.DISARM
    assert board.firmware.state == State.DISARMED and board.client is None and link.io.transport is None
    assert board.running()                                      # đóng phiên không tắt bo ảo


def test_qemu_run_exports_and_replays_identically(scenario, cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(run_store, "environment", lambda: {"test": True})   # không gọi PowerShell
    session, link, board = qemu_session(scenario, cfg)
    session.start_run()
    drive(session, board)
    assert session.state == SessionState.COMPLETED
    bundle = export_run(session, tmp_path / "goi_qemu")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert (manifest["evidence"], manifest["replay_kind"]) == (QEMU_EVIDENCE, "vehicle_io_log")
    replayed, report = replay_vehicle_run(bundle)
    try:
        assert report.ok, "\n".join(report.lines())
        assert report.max_clock_diff_s <= 0.005
        info = json.loads((bundle / "vehicle_io" / "link.json").read_text(encoding="utf-8"))
        assert info["board"]["kind"] == "qemu" and info["plant"]["telemetry_period_ms"] == 20
        described = replayed.run_link.describe()
        assert described["replay"] and (described["board"], described["plant"]) == (info["board"], info["plant"])
        assert described["evidence"] == QEMU_EVIDENCE and described["pose_source"] == "qemu_plant_pose"
    finally:
        replayed.close()
        session.close()


def test_com_port_links_unchanged(scenario, cfg, monkeypatch):
    import serial

    monkeypatch.setattr(serial, "Serial", lambda *a, **k: pytest.fail("không được mở cổng thật"))
    session = straight_session(scenario, cfg)
    link = VehicleLink.serial_port(DriveMode.VEHICLE_IO, "COM7")
    assert not link.is_qemu and not link._close_after_run
    session.set_vehicle_link(link)
    with pytest.raises(SessionError, match="nguồn tư thế thật"):
        session.start_run()
    assert [r["code"] for r in link.start_refusals] == ["START_NO_POSE_SOURCE"] and link.io.transport is None
    info = link.describe()
    assert (info["evidence"], info["board"], info["plant"]) == ("hardware_untested", None, None)
    simulated = VehicleLink.simulated(DriveMode.VEHICLE_IO).describe()
    assert (simulated["evidence"], simulated["board"], simulated["plant"]) == ("simulation_only", None, None)
    session.close()
