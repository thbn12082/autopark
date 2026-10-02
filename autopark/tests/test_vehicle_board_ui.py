"""Giới hạn bo so với cấu hình xe, bo thật chưa có nguồn tư thế, "Kiểm kết nối bo" và chọn cổng trong giao diện
(thêm 24/09/2026). Nút "Xóa lỗi bo (CLEAR_FAULT)": `VehicleLink.clear_fault`, dòng board_actions.csv và nút trong thẻ
"Bo điều khiển" (T15, thêm 02/10/2026).

Không mở cổng thật nào: bo là `FirmwareModel` sau `FirmwareSerialLoopback` + `ManualClock` (cổng serial GIẢ) hoặc
`SimVehicleIO`; `serial.Serial` bị thay bằng hàm ghi lại lời gọi, `serial.tools.list_ports.comports` bị thay bằng
danh sách giả. Mọi kết quả ở đây là của bản tham chiếu firmware, không phải của ESP32-S3.
"""
from dataclasses import replace
from datetime import datetime
import json
import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from autopark.application.session import Session, SessionError, SessionState  # noqa: E402
from autopark.application.vehicle_link import (BOARD_ACTION_FIELDS, DriveMode, NoPoseSource,  # noqa: E402
                                               SimTruthPose, VehicleLink, VehicleLinkError, probe_board)
from autopark.domain.types import ParkingGoal, Pose, VehicleState  # noqa: E402
from autopark.transport.firmware_model import FirmwareInputs, FirmwareModel  # noqa: E402
from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock  # noqa: E402
from autopark.transport.protocol import (HOST_TO_DEVICE, Action, Command, Fault, FrameParser, Hello,  # noqa: E402
                                         Request, ResetReason, State, StopReason)
from autopark.transport.vehicle_io import (PUMP_MAX_BYTES, SIM_FIRMWARE_DEFAULT, SerialVehicleIO,  # noqa: E402
                                           SimIOConfig, SimVehicleIO)

FAST_FW = replace(SIM_FIRMWARE_DEFAULT, boot_hold_ms=200)


# ---- tiện ích -----------------------------------------------------------------------------------------------------
def straight_session(scenario, cfg) -> Session:
    scenario.obstacles = []
    scenario.start = Pose(0.5, 1.0, 0.0)
    scenario.goal = ParkingGoal(Pose(2.0, 1.0, 0.0))
    session = Session(scenario, cfg)
    assert session.plan_sync().ok
    return session


def sim_io(cfg, pose: Pose, firmware=FAST_FW) -> SimVehicleIO:
    return SimVehicleIO(cfg, SimIOConfig(firmware=firmware), start=VehicleState(pose, 0.0, 0.0, 0.0))


def record_requests(io: SimVehicleIO) -> list[Action]:
    seen = []
    firmware = io.firmware
    original = firmware._handle_request

    def handle(msg, now):
        seen.append(Action(msg.action))
        original(msg, now)

    firmware._handle_request = handle
    return seen


def serial_board(firmware_cfg=FAST_FW, port="COM7"):
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(firmware_cfg, boot_id=0xB007), clock)
    return SerialVehicleIO(loop, clock=clock, rng=random.Random(3), port=port), loop


def host_messages(loop, start: int = 0) -> list:
    """Mọi thông điệp laptop đã ghi ra cổng giả (từ lần ghi thứ `start`)."""
    parser = FrameParser(accept_types=HOST_TO_DEVICE)
    out = []
    for chunk in loop.written[start:]:
        out.extend(parser.feed(chunk))
    return out


def codes_actions(rows) -> list[tuple[str, str]]:
    return [(r["code"], r["action"]) for r in rows]


@pytest.fixture
def no_serial_open(monkeypatch):
    """Mọi lần mở cổng thật bị ghi lại và từ chối: test nào mở cổng sẽ thấy trong danh sách."""
    import serial
    opened = []

    def refuse(*args, **kwargs):
        opened.append(args)
        raise AssertionError("test không được mở cổng thật")

    monkeypatch.setattr(serial, "Serial", refuse)
    return opened


class FakePortInfo:
    def __init__(self, device, description="", vid=None):
        self.device, self.description, self.vid = device, description, vid


@pytest.fixture
def ports(monkeypatch):
    from serial.tools import list_ports
    state = {"ports": [FakePortInfo("COM4", "Silicon Labs CP210x USB to UART Bridge", 0x10C4),
                       FakePortInfo("COM10", "USB Serial Device", 0x303A)], "calls": 0}

    def comports():
        state["calls"] += 1
        return list(state["ports"])

    monkeypatch.setattr(list_ports, "comports", comports)
    return state


# ---- giới hạn bo lúc START ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("override, label", [
    ({"max_speed_mm_s": 400}, "tốc độ lớn nhất"),          # bo cho phép nhanh hơn
    ({"max_steer_mrad": 400}, "góc lái lớn nhất"),         # bo không cho góc lái mà đường đã lập có thể cần
    ({"max_decel_mm_s2": 400}, "giảm tốc khi đang chạy"),  # bo phanh yếu hơn
])
def test_vehicle_io_start_refused_when_board_limits_are_risky(scenario, cfg, override, label):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start, replace(FAST_FW, **override))
    requests = record_requests(io)
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=SimTruthPose(io))
    session.set_vehicle_link(link)
    with pytest.raises(SessionError, match="Giới hạn của bo"):
        session.start_run()
    assert session.state == SessionState.READY and session.world is None and link.runs == 0
    assert Action.ARM not in requests and io.stats.commands_sent == 0 and io.firmware.state == State.DISARMED
    rows = link.start_refusals
    assert codes_actions(rows) == [("LIMITS_MISMATCH", "STOP"), ("START_CHECK", "LOG")]
    assert label in rows[0]["message"] and "TỪ CHỐI START" in rows[0]["message"]
    assert rows[1]["message"].startswith("TỪ CHỐI") and label in rows[1]["message"]
    assert link.limits_check is not None and link.limits_check.risky and link.refused_starts == 1


def test_vehicle_io_board_stricter_only_warns_and_runs(scenario, cfg, tmp_path):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start, replace(FAST_FW, max_speed_mm_s=250))
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=SimTruthPose(io))
    session.set_vehicle_link(link)
    session.start_run()
    try:
        assert session.state == SessionState.RUNNING
        mismatch = [r for r in link.event_rows if r["code"] == "LIMITS_MISMATCH"]
        assert codes_actions(mismatch) == [("LIMITS_MISMATCH", "LOG")] and "chỉ cảnh báo" in mismatch[0]["message"]
        check = next(r for r in link.event_rows if r["code"] == "START_CHECK")
        assert check["message"].startswith("Đạt") and "giới hạn: lệch 1 (0 nguy hiểm)" in check["message"]
        session.advance(0.5)
        assert io.stats.commands_sent > 10 and session.state == SessionState.RUNNING
        info = json.loads(link.write_logs(tmp_path)["link.json"].read_text(encoding="utf-8"))
        assert info["limits_check"]["ok"] is False and info["limits_check"]["risky"] is False
        assert info["limits_check"]["mismatches"][0]["name"] == "max_speed_mps"
    finally:
        session.close()


def test_observe_logs_risky_limits_but_does_not_refuse(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start, replace(FAST_FW, max_speed_mm_s=400))
    link = VehicleLink(DriveMode.OBSERVE, io, pose_source=SimTruthPose(io))
    session.set_vehicle_link(link)
    session.start_run()
    try:
        assert session.state == SessionState.RUNNING and link.start_refusals == []
        mismatch = [r for r in link.event_rows if r["code"] == "LIMITS_MISMATCH"]
        assert codes_actions(mismatch) == [("LIMITS_MISMATCH", "LOG")] and "quan sát" in mismatch[0]["message"]
        assert link.limits_check.risky and io.stats.commands_sent == 0
    finally:
        session.close()


def test_matching_limits_add_no_row_and_are_reported_in_start_check(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=SimTruthPose(io))
    session.set_vehicle_link(link)
    session.start_run()
    try:
        assert not [r for r in link.event_rows if r["code"] == "LIMITS_MISMATCH"]
        check = next(r for r in link.event_rows if r["code"] == "START_CHECK")
        assert "giới hạn: khớp" in check["message"] and link.limits_check.ok
        assert link.describe()["limits_check"]["ok"] is True
    finally:
        session.close()


# ---- bo thật: chưa có nguồn tư thế thật ----------------------------------------------------------------------------
@pytest.mark.parametrize("mode", [DriveMode.VEHICLE_IO, DriveMode.OBSERVE])
def test_real_port_start_is_refused_before_the_port_is_opened(scenario, cfg, no_serial_open, mode):
    session = straight_session(scenario, cfg)
    link = VehicleLink.serial_port(mode, "COM7")
    assert isinstance(link.io, SerialVehicleIO) and link.io.transport is None and link.realtime
    assert isinstance(link.pose_source, NoPoseSource) and not link.pose_simulated
    session.set_vehicle_link(link)
    for _ in range(2):
        with pytest.raises(SessionError, match="nguồn tư thế thật") as info:
            session.start_run()
        assert "COM7" in str(info.value) and "Cổng chưa được mở" in str(info.value)
    assert no_serial_open == [] and link.io.transport is None and link.io.stats.frames_sent == 0
    assert session.state == SessionState.READY and link.runs == 0 and link.refused_starts == 2
    assert [r["code"] for r in link.start_refusals] == ["START_NO_POSE_SOURCE"] * 2
    described = link.describe()
    assert described["port"] == "COM7" and described["pose_source"] == "no_pose_source"
    assert described["evidence"] == "hardware_untested" and described["io"] == "SerialVehicleIO"
    session.close()
    assert no_serial_open == []


def test_sim_truth_pose_is_never_paired_with_another_board(cfg):
    board, _loop = serial_board()
    sim = sim_io(cfg, Pose(0.5, 1.0, 0.0))
    other = sim_io(cfg, Pose(0.5, 1.0, 0.0))
    with pytest.raises(ValueError, match="SimTruthPose"):
        VehicleLink(DriveMode.VEHICLE_IO, board, pose_source=SimTruthPose(sim))
    with pytest.raises(ValueError, match="SimTruthPose"):
        VehicleLink(DriveMode.OBSERVE, other, pose_source=SimTruthPose(sim))
    with pytest.raises(ValueError, match="SimTruthPose"):
        VehicleLink.serial_port(DriveMode.VEHICLE_IO, "COM7", pose_source=SimTruthPose(sim))
    # Sửa theo rà soát (muộn tối 24/09/2026): SimTruthPose dựng quanh CHÍNH bo serial trước đây lọt qua (io trùng),
    # rồi START gửi HELLO và hỏng với AttributeError thay vì bị từ chối rõ ràng khi tạo liên kết.
    for mode in (DriveMode.VEHICLE_IO, DriveMode.OBSERVE):
        with pytest.raises(ValueError, match="SimTruthPose"):
            VehicleLink(mode, board, pose_source=SimTruthPose(board))
    assert board.stats.frames_sent == 0 and not board.connected
    assert VehicleLink(DriveMode.VEHICLE_IO, sim, pose_source=SimTruthPose(sim)).io is sim


class ProxyPose:
    """Nguồn tư thế kiểu Mock/proxy: thuộc tính lạ nào cũng "có", mỗi lần một đối tượng mới. Đếm chung số lần bị hỏi và
    ném sau 100 lần, để vòng bóc lớp bọc không dừng làm test hỏng thay vì treo (và không ngốn bộ nhớ như Mock)."""

    source_id, simulated = "proxy_pose", False
    asked = 0

    def __getattr__(self, name):
        ProxyPose.asked += 1
        if ProxyPose.asked > 100:
            raise RuntimeError(f"hỏi thuộc tính {name!r} quá 100 lần: vòng bóc lớp bọc không dừng")
        return ProxyPose()

    def latest(self):
        return None


class LoopPose:
    """Lớp bọc trỏ vòng về chính nó qua property `fault_inner` (property cũng là lớp bọc phải bóc); ném sau 100 lần."""

    source_id, simulated = "loop_pose", False

    def __init__(self, inner=None):
        self.inner, self.asked = inner, 0

    @property
    def fault_inner(self):
        self.asked += 1
        if self.asked > 100:
            raise RuntimeError("fault_inner bị hỏi quá 100 lần: vòng bóc lớp bọc không dừng")
        return self if self.inner is None else self.inner

    def latest(self):
        return None


def test_pose_wrapper_unwrapping_stops_for_proxies_and_cycles(cfg):
    """Sửa sau review 02/10/2026: VehicleLink bóc lớp bọc tiêm lỗi (`fault_inner`) chỉ qua thuộc tính có thật, tối đa
    MAX_POSE_WRAPPERS lớp. Trước đó getattr(…, "fault_inner") với Mock/proxy (mỗi lần một đối tượng mới) hay lớp bọc trỏ
    vòng làm VehicleLink.__init__ chạy mãi, trên luồng giao diện."""
    from autopark.application.vehicle_link import MAX_POSE_WRAPPERS, unwrap_pose_source

    sim = sim_io(cfg, Pose(0.5, 1.0, 0.0))
    ProxyPose.asked = 0
    proxy = ProxyPose()
    link = VehicleLink(DriveMode.VEHICLE_IO, sim, pose_source=proxy)
    assert link.pose_source is proxy and ProxyPose.asked == 0       # không hỏi fault_inner qua __getattr__
    cyclic = LoopPose()
    with pytest.raises(ValueError, match=f"quá {MAX_POSE_WRAPPERS} lớp fault_inner"):
        VehicleLink(DriveMode.VEHICLE_IO, sim, pose_source=cyclic)
    assert cyclic.asked == MAX_POSE_WRAPPERS
    # Lớp bọc dùng property vẫn được bóc: SimTruthPose của bo khác nằm trong vẫn bị từ chối.
    other = sim_io(cfg, Pose(0.5, 1.0, 0.0))
    with pytest.raises(ValueError, match="SimTruthPose"):
        VehicleLink(DriveMode.VEHICLE_IO, sim, pose_source=LoopPose(SimTruthPose(other)))
    inner = SimTruthPose(sim)
    assert unwrap_pose_source(LoopPose(LoopPose(inner))) is inner and unwrap_pose_source(inner) is inner


# ---- probe_board ---------------------------------------------------------------------------------------------------
def test_probe_board_says_hello_reads_telemetry_and_closes(cfg):
    io, loop = serial_board()
    loop.advance(300)                                            # bo qua boot_hold 200 ms
    report = probe_board(io, cfg, target="COM7")
    assert report.ok and not report.simulated and report.target == "COM7"
    assert report.hello.firmware_version == "1.0" and report.hello.boot_id == 0xB007
    assert len(report.frames) == 5 and all(f.state == State.DISARMED for f in report.frames)
    assert report.limits.ok and report.events == []
    assert report.commands_sent == 0 and report.requests_sent == 0
    assert [type(m) for m in host_messages(loop)] == [Hello]     # đúng một HELLO, không REQUEST/COMMAND nào
    assert loop.closed and io.transport is None and not io.connected
    text = "\n".join(report.lines())
    for needle in ("firmware 1.0", "0000b007", "khớp", "5/5 khung", "300 mm/s", "0 COMMAND"):
        assert needle in text, needle


def test_probe_board_disarms_an_armed_board_and_never_arms(cfg):
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW, boot_id=0xB007), clock)
    other = SerialVehicleIO(loop, clock=clock, rng=random.Random(9))   # chương trình khác đã ARM bo
    other.connect()
    other.wait_ready()
    other.arm()
    assert loop.firmware.state == State.ARMED
    start = len(loop.written)
    report = probe_board(SerialVehicleIO(loop, clock=clock, rng=random.Random(4)), cfg)
    assert report.ok and report.hello.state == State.DISARMED
    assert loop.firmware.state == State.DISARMED and loop.firmware.stop_reason == StopReason.NEW_SESSION
    sent = host_messages(loop, start)
    assert [type(m) for m in sent] == [Hello]
    assert not any(isinstance(m, (Command, Request)) for m in sent)


def test_probe_board_reports_risky_limits(cfg):
    io, loop = serial_board(replace(FAST_FW, max_speed_mm_s=400))
    report = probe_board(io, cfg)
    assert report.ok and report.limits.risky
    assert [(e.code, e.action) for e in report.events] == [("LIMITS_MISMATCH", "STOP")]
    text = "\n".join(report.lines())
    assert "LIMITS_MISMATCH (START ở VEHICLE_IO sẽ bị TỪ CHỐI)" in text and "bo 400.0 mm/s" in text
    assert [type(m) for m in host_messages(loop)] == [Hello] and loop.closed


def test_probe_board_silent_board_times_out_and_still_closes(cfg):
    io, loop = serial_board()
    loop.firmware.receive = lambda data, now: None               # bo không trả lời gì
    report = probe_board(io, cfg, connect_timeout_s=0.3)
    assert not report.ok and "HELLO_ACK" in report.error and report.hello is None
    assert report.commands_sent == 0 and loop.closed
    assert "LỖI:" in report.lines()[-1]
    assert "Không nhận được HELLO_ACK." in report.lines()


def test_probe_board_hello_but_no_telemetry_times_out_disarms_once_and_closes(cfg):
    """Bo trả HELLO_ACK nhưng không gửi telemetry (thêm theo rà soát, muộn tối 24/09/2026): vòng đọc phải dừng đúng hạn
    `frames_timeout_s` theo đồng hồ io; bỏ hạn này thì giao diện treo mãi (TELEMETRY_STALE không xóa `connected`)."""
    io, loop = serial_board()
    firmware = loop.firmware
    original_step = firmware.step

    def step_without_telemetry(now_ms, inputs=None):
        # Chặn treo: nếu vòng đọc bỏ mất hạn thì test báo lỗi thay vì chạy mãi.
        assert now_ms <= 10_000, "probe_board vẫn đọc sau 10 s: vòng chờ telemetry không có hạn"
        firmware.last_tel_ms = now_ms & 0xFFFFFFFF                # luôn "vừa gửi": không bao giờ tới hạn telemetry
        return original_step(now_ms, inputs)

    firmware.step = step_without_telemetry
    loop.advance(300)                                            # bo qua boot_hold, vẫn trả HELLO_ACK bình thường
    report = probe_board(io, cfg, frames_timeout_s=1.0)
    assert not report.ok and report.hello is not None and report.frames == []
    assert "0/5 khung" in report.error and "mất phiên" not in report.error
    assert [(e.code, e.action) for e in report.events] == [("TELEMETRY_STALE", "STOP")]
    assert report.commands_sent == 0 and report.requests_sent == 1
    sent = host_messages(loop)
    assert [type(m) for m in sent] == [Hello, Request] and Action(sent[1].action) == Action.DISARM
    assert not any(isinstance(m, Command) for m in sent)
    assert loop.clock.t_ms <= 300 + 1000 + 100                   # dừng đúng hạn 1 s theo đồng hồ io, không đọc thêm
    assert loop.closed and io.transport is None and not io.connected
    assert "LỖI: Chỉ nhận 0/5 khung" in report.lines()[-1]


def test_probe_board_keeps_hello_when_session_refused_for_long_telemetry_period(cfg):
    """Bo trả HELLO_ACK nhưng chọn chu kỳ telemetry 400 ms (> telemetry_timeout_s / 3): `connect()` từ chối phiên. Báo
    cáo vẫn phải có firmware/boot_id/giới hạn và kết quả so giới hạn (sửa theo rà soát, muộn tối 24/09/2026); trước
    đó nó nói "Không nhận được HELLO_ACK." rồi lại báo lỗi chu kỳ 400 ms của chính HELLO_ACK đó."""
    io, loop = serial_board(replace(FAST_FW, default_telemetry_period_ms=400, max_speed_mm_s=400))
    report = probe_board(io, cfg)
    assert not report.ok and report.hello is not None and report.hello.boot_id == 0xB007
    assert round(report.hello.telemetry_period_s * 1000) == 400
    assert report.limits is not None and report.limits.risky
    assert [(e.code, e.action) for e in report.events] == [("LIMITS_MISMATCH", "STOP")]
    assert "bị từ chối" in report.error and "400 ms" in report.error
    text = "\n".join(report.lines())
    assert "Không nhận được HELLO_ACK" not in text and "0000b007" in text and "chu kỳ telemetry 400 ms" in text
    assert "START ở VEHICLE_IO sẽ bị TỪ CHỐI" in text
    assert report.commands_sent == 0 and report.requests_sent == 0 and loop.closed and not io.connected
    assert [type(m) for m in host_messages(loop)] == [Hello]


def test_probe_board_keeps_hello_when_connect_refuses_the_board_period(cfg):
    io, loop = serial_board(replace(FAST_FW, default_telemetry_period_ms=200))
    report = probe_board(io, cfg, target="COM7")
    assert not report.ok and "200 ms" in report.error and not io.connected
    assert report.hello is not None and report.hello.boot_id == 0xB007
    assert report.hello.telemetry_period_s == pytest.approx(0.2)
    assert report.limits is not None and report.limits.ok and report.events == []
    assert report.commands_sent == 0 and [type(m) for m in host_messages(loop)] == [Hello] and loop.closed
    text = "\n".join(report.lines())
    assert "Không nhận được HELLO_ACK" not in text
    for needle in ("firmware 1.0", "0000b007", "chu kỳ telemetry 200 ms", "Giới hạn bo", "khớp",
                   "LỖI: HELLO_ACK nhận được nhưng phiên bị từ chối: Bo chọn chu kỳ telemetry 200 ms"):
        assert needle in text, needle


def test_probe_board_does_not_report_an_old_hello_when_the_port_is_closed(cfg):
    """Phiên cũ đã có HELLO_ACK, cổng sau đó đóng: lần kiểm mới lỗi "Cổng chưa mở" trước khi gửi HELLO, và không được
    báo HELLO_ACK cũ như của lần kiểm này."""
    io, loop = serial_board()
    old = io.connect()
    io.close()                                                   # cổng đã đóng, io.hello vẫn còn của phiên cũ
    report = probe_board(io, cfg)
    assert io.hello is old and report.hello is None and report.limits is None
    assert report.error == "Cổng chưa mở" and "Không nhận được HELLO_ACK." in report.lines()


def test_probe_board_unplug_after_hello_reports_link_error(cfg):
    io, loop = serial_board()
    original = io.check_limits

    def check_then_unplug(*args, **kwargs):
        result = original(*args, **kwargs)
        loop.unplug()
        return result

    io.check_limits = check_then_unplug
    report = probe_board(io, cfg)
    assert not report.ok and report.hello is not None and report.frames == []
    assert "mất phiên hoặc lỗi cổng" in report.error
    assert "LINK_ERROR" in [e.code for e in report.events] and io.transport is None


def test_probe_board_on_the_simulated_board(cfg):
    report = probe_board(SimVehicleIO(cfg, SimIOConfig(firmware=FAST_FW)), cfg, frames=3)
    assert report.ok and report.simulated and len(report.frames) == 3 and report.limits.ok
    assert "MÔ PHỎNG" in report.lines()[0]
    with pytest.raises(ValueError):
        probe_board(SimVehicleIO(cfg), cfg, frames=0)


# ---- giao diện -----------------------------------------------------------------------------------------------------
@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, ports, no_serial_open):
    from autopark.ui.app import DEFAULT_SCENARIO, build_window
    w = build_window(DEFAULT_SCENARIO)
    yield w
    w.close()


@pytest.fixture
def dialogs(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = {"warning": [], "question": [], "answer": QMessageBox.StandardButton.Yes}

    def warning(*args, **kwargs):
        seen["warning"].append(args)
        return QMessageBox.StandardButton.Ok

    def question(*args, **kwargs):
        seen["question"].append(args)
        return seen["answer"]

    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(QMessageBox, "question", question)
    return seen


def select_port(window, device):
    window._refresh_ports()
    index = window.combo_port.findData(device)
    assert index >= 0, device
    window.combo_port.setCurrentIndex(index)


def test_list_serial_ports_sorts_and_marks_espressif(ports):
    from autopark.ui.main_window import list_serial_ports
    ports["ports"].append(FakePortInfo("COM3"))
    assert list_serial_ports() == [("COM3", ""), ("COM4", "Silicon Labs CP210x USB to UART Bridge"),
                                   ("COM10", "USB Serial Device · Espressif (VID 303A)")]


def test_list_serial_ports_survives_listing_errors(monkeypatch):
    from serial.tools import list_ports
    from autopark.ui.main_window import list_serial_ports

    def broken():
        raise OSError("SetupAPI lỗi")

    monkeypatch.setattr(list_ports, "comports", broken)
    assert list_serial_ports() == []


def test_window_port_choice_defaults_to_sim_and_lists_ports_on_demand(window, ports, no_serial_open):
    from autopark.transport.vehicle_io import SerialVehicleIO as Serial
    combo = window.combo_port
    assert ports["calls"] == 0                                   # dựng cửa sổ không liệt kê cổng
    assert combo.count() == 1 and window.board_port() is None and "Bo mô phỏng" in combo.itemText(0)
    combo.showPopup()                                            # mở danh sách = quét lại
    combo.hidePopup()
    assert ports["calls"] == 1 and combo.count() == 3 and window.board_port() is None
    assert "Espressif" in combo.itemText(combo.findData("COM10"))

    window.combo_drive.setCurrentIndex(window.combo_drive.findData(DriveMode.VEHICLE_IO.value))
    assert window.session.vehicle_link._simulated                  # mặc định vẫn là bo mô phỏng
    select_port(window, "COM10")
    link = window.session.vehicle_link
    assert isinstance(link.io, Serial) and link.io.port == "COM10" and link.io.transport is None
    assert link.mode == DriveMode.VEHICLE_IO and isinstance(link.pose_source, NoPoseSource)
    assert "TỪ CHỐI" in window.lbl_board_hint.text() and no_serial_open == []

    ports["ports"] = []                                          # rút cáp: cổng đã chọn vẫn giữ, có ghi chú
    window._refresh_ports()
    assert window.board_port() == "COM10" and "không thấy" in combo.currentText()
    assert window.session.vehicle_link is link

    combo.setCurrentIndex(0)                                     # về bo mô phỏng
    assert window.session.vehicle_link._simulated and window.board_port() is None
    window.combo_drive.setCurrentIndex(window.combo_drive.findData(DriveMode.SIM.value))
    assert window.session.vehicle_link is None
    assert no_serial_open == []


@pytest.mark.parametrize("mode", [DriveMode.VEHICLE_IO, DriveMode.OBSERVE])
def test_window_real_port_start_is_refused_with_clear_message(window, dialogs, no_serial_open, mode):
    window.combo_drive.setCurrentIndex(window.combo_drive.findData(mode.value))
    select_port(window, "COM4")
    assert window.plan(sync=True).ok
    window.run()
    assert window.session.state == SessionState.READY and window.session.run_link is None
    title, message = dialogs["warning"][-1][1:3]
    assert title == "Không bắt đầu được" and "nguồn tư thế thật" in message and "COM4" in message
    assert no_serial_open == []
    link = window.session.vehicle_link
    assert [r["code"] for r in link.start_refusals] == ["START_NO_POSE_SOURCE"] and link.io.transport is None


def test_window_probe_real_port_sends_only_hello(window, dialogs, no_serial_open):
    io, loop = serial_board(port="COM10")
    calls = []
    window.serial_io_factory = lambda port: calls.append(port) or io
    select_port(window, "COM10")
    window.btn_probe.click()
    assert calls == ["COM10"] and len(dialogs["question"]) == 1 and "COM10" in dialogs["question"][0][2]
    report = window.last_board_probe
    assert report.ok and report.target == "COM10" and report.commands_sent == 0
    text = window.lbl_board_report.text()
    assert "firmware 1.0" in text and "khớp" in text and "5/5 khung" in text
    assert [type(m) for m in host_messages(loop)] == [Hello] and loop.closed
    assert loop.firmware.state in (State.BOOT, State.DISARMED) and no_serial_open == []


def test_window_probe_shows_risky_limits(window, dialogs):
    io, loop = serial_board(replace(FAST_FW, max_steer_mrad=700), port="COM10")
    window.serial_io_factory = lambda port: io
    select_port(window, "COM10")
    window.btn_probe.click()
    text = window.lbl_board_report.text()
    assert "LIMITS_MISMATCH" in text and "TỪ CHỐI" in text and "góc lái lớn nhất" in text
    assert window.last_board_probe.limits.risky


def test_window_probe_cancelled_or_failing_open_sends_nothing(window, dialogs, no_serial_open):
    from PySide6.QtWidgets import QMessageBox
    select_port(window, "COM4")
    calls = []
    window.serial_io_factory = lambda port: calls.append(port)
    dialogs["answer"] = QMessageBox.StandardButton.No
    assert window._probe_board() is None and calls == [] and window.lbl_board_report.text() == ""

    def cannot_open(port):
        raise OSError(f"could not open port '{port}': PermissionError")

    dialogs["answer"] = QMessageBox.StandardButton.Yes
    window.serial_io_factory = cannot_open
    assert window._probe_board() is None
    assert "Không mở được COM4" in window.lbl_board_report.text() and no_serial_open == []


def test_window_probe_simulated_board_asks_nothing(window, dialogs, no_serial_open):
    report = window._probe_board()
    assert report is not None and report.simulated and report.ok and dialogs["question"] == []
    assert "MÔ PHỎNG" in window.lbl_board_report.text() and no_serial_open == []


def test_window_start_shows_limits_warning_or_refusal(window, dialogs, monkeypatch):
    # Bo mô phỏng của giao diện với firmware chặt hơn (250 mm/s < 300): chạy, có cảnh báo LIMITS_MISMATCH.
    monkeypatch.setattr(window, "_sim_io_config", lambda: SimIOConfig(firmware=replace(FAST_FW, max_speed_mm_s=250)))
    window.combo_drive.setCurrentIndex(window.combo_drive.findData(DriveMode.VEHICLE_IO.value))
    assert window.plan(sync=True).ok
    window.run()
    assert window.session.state == SessionState.RUNNING and dialogs["warning"] == []
    assert "LIMITS_MISMATCH (cảnh báo)" in window.statusBar().currentMessage()
    window.stop()
    for _ in range(100):
        window.advance_by(0.1)
        if not window.session.simulating:
            break
    window.reset()
    # Firmware lỏng hơn (400 mm/s > 300): START bị từ chối, hộp thoại nêu giới hạn.
    monkeypatch.setattr(window, "_sim_io_config", lambda: SimIOConfig(firmware=replace(FAST_FW, max_speed_mm_s=400)))
    window.combo_drive.setCurrentIndex(window.combo_drive.findData(DriveMode.SIM.value))
    window.combo_drive.setCurrentIndex(window.combo_drive.findData(DriveMode.VEHICLE_IO.value))
    if window.session.state != SessionState.READY:
        assert window.plan(sync=True).ok
    window.run()
    assert window.session.state == SessionState.READY
    message = dialogs["warning"][-1][2]
    assert "Giới hạn của bo" in message and "tốc độ lớn nhất" in message


def test_window_board_controls_locked_while_running(window, dialogs):
    window.combo_drive.setCurrentIndex(window.combo_drive.findData(DriveMode.VEHICLE_IO.value))
    assert window.plan(sync=True).ok
    window.run()
    assert window.session.state == SessionState.RUNNING
    window._refresh_mode_widgets()
    assert not window.combo_port.isEnabled() and not window.btn_probe.isEnabled()
    assert window._probe_board() is None                         # kể cả gọi thẳng khi đang chạy
    window.stop()
    for _ in range(100):
        window.advance_by(0.1)
        if not window.session.simulating:
            break
    window.reset()
    window._refresh_mode_widgets()
    assert window.combo_port.isEnabled() and window.btn_probe.isEnabled()


# ---- "Xóa lỗi bo (CLEAR_FAULT)" (T15, thêm 02/10/2026) -----------------------------------------------------------
START = Pose(0.5, 1.0, 0.0)                                      # điểm xuất phát của straight_session


def faulted_sim_io(cfg, released: bool = True, pose: Pose = START) -> SimVehicleIO:
    """Bo mô phỏng đã chốt FAULT ESTOP, chưa có phiên: nhấn E-stop 0,5 s, rồi nhả (hoặc giữ nhấn) thêm 0,2 s."""
    io = sim_io(cfg, pose)
    io.set_estop(True)
    io.advance(0.5)
    io.set_estop(not released)
    io.advance(0.2)
    assert io.firmware.state == State.FAULT and io.firmware.fault == Fault.ESTOP and not io.connected
    return io


def faulted_firmware(released: bool = True, fw_cfg=FAST_FW):
    """Bo sau cổng serial GIẢ đã chốt FAULT ESTOP: (FirmwareModel, ManualClock, hàm ngõ vào, dict ngõ vào). Bo chạy bằng
    một FirmwareSerialLoopback dùng một lần (E-stop nhấn 0,5 s, rồi nhả hoặc giữ thêm 0,2 s); cổng của test mở sau."""
    firmware = FirmwareModel(fw_cfg, boot_id=0xB007)
    clock = ManualClock()
    state = {"estop": True}

    def inputs(_t_ms: int) -> FirmwareInputs:
        return FirmwareInputs(estop=state["estop"])

    loop = FirmwareSerialLoopback(firmware, clock, inputs=inputs)
    loop.advance(500)
    state["estop"] = not released
    loop.advance(200)
    assert firmware.state == State.FAULT and firmware.fault == Fault.ESTOP
    return firmware, clock, inputs, state


def fake_opener(firmware, clock, inputs, loops: list):
    """Hàm mở cổng giả: mỗi lần mở là một FirmwareSerialLoopback MỚI tới cùng một bo (như mở lại cùng cổng COM)."""
    def opener():
        loop = FirmwareSerialLoopback(firmware, clock, inputs=inputs)
        loops.append(loop)
        return loop

    return opener


@pytest.mark.parametrize("mode", [DriveMode.VEHICLE_IO, DriveMode.OBSERVE])
def test_clear_fault_after_release_goes_to_disarmed_without_arm_or_command(cfg, mode):
    io = faulted_sim_io(cfg)
    requests = record_requests(io)
    link = VehicleLink(mode, io, pose_source=SimTruthPose(io))
    assert link.clear_fault_blocker is None
    report = link.clear_fault()
    assert report.outcome == "CLEARED" and report.ok and report.ack_result == "OK" and report.sent
    assert report.before.state == State.FAULT and report.before.fault == Fault.ESTOP and not report.before.estop_input
    assert report.after.state == State.DISARMED and report.after.fault == Fault.NONE
    assert requests == [Action.CLEAR_FAULT]                      # không ARM, không DISARM
    assert report.commands_sent == 0 and report.requests_sent == 1 and io.stats.commands_sent == 0
    assert report.hello is not None and report.hello.state == State.FAULT and report.hello_sent   # HELLO giữ FAULT
    assert "VEHICLE_FAULT" in [e.code for e in report.events]
    io.advance(1.0)
    assert io.truth.speed == 0.0 and io.applied_effort_permille == 0 and io.latest().effort == 0.0
    assert io.firmware.state == State.DISARMED                   # vẫn phải ARM rồi có lệnh mới mới chạy
    row = report.to_row()
    assert link.board_actions == [row] and list(row) == BOARD_ACTION_FIELDS
    assert (row["state_before"], row["fault_before"], row["estop_before"]) == ("FAULT", "ESTOP", 0)
    assert (row["state_after"], row["fault_after"], row["outcome"]) == ("DISARMED", "NONE", "CLEARED")
    assert row["request"] == "CLEAR_FAULT" and row["requests_sent"] == 1 and row["commands_sent"] == 0
    assert datetime.fromisoformat(row["wall_time"]).tzinfo is not None
    assert isinstance(row["t_io"], float) and isinstance(row["t_perf"], float)
    assert "sự kiện: VEHICLE_FAULT" in row["message"]
    # Sau review 02/10/2026: sự kiện vào message đủ (action, t_io, lời), và HELLO_ACK của lần bấm ở bốn cột hello_*.
    fault = next(e for e in report.events if e.code == "VEHICLE_FAULT")
    assert f"VEHICLE_FAULT (STOP, t_io {fault.stamp.t:.3f}): {fault.message}" in row["message"]
    hello = report.hello
    assert (row["hello_firmware"], row["hello_boot_id"], row["hello_state"]) == \
        (hello.firmware_version, f"0x{hello.boot_id:08x}", "FAULT")
    assert row["hello_reset_reason"] == ResetReason(hello.reset_reason).name
    assert link.runs == 0 and link.event_rows == [] and link.start_refusals == []
    text = "\n".join(report.lines())
    for needle in ("Đã xóa lỗi", "0 COMMAND, 1 REQUEST", f"boot_id {report.hello.boot_id:08x}", "Trước: #",
                   "nút dừng khẩn", "Đã gửi CLEAR_FAULT lúc t_io", "ACK OK", "Sau: #", "KẾT QUẢ:"):
        assert needle in text, needle


def test_clear_fault_sends_nothing_while_estop_pressed_or_board_not_in_fault(cfg):
    io = faulted_sim_io(cfg, released=False)
    requests = record_requests(io)
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=SimTruthPose(io))
    pressed = link.clear_fault()
    assert pressed.outcome == "ESTOP_PRESSED" and not pressed.ok and not pressed.sent and pressed.before.estop_input
    assert requests == [] and pressed.requests_sent == 0 and io.firmware.state == State.FAULT
    assert "NHẤN" in pressed.summary() and "Không gửi CLEAR_FAULT" in pressed.summary()
    row = link.board_actions[0]
    assert (row["estop_before"], row["ack_result"], row["state_after"]) == (1, "", "")
    # Nhả nút rồi bấm lại trên cùng liên kết: dùng phiên đang có (không HELLO), io không bị đóng. Sau review 02/10/2026:
    # PING chờ ACK trước khi đọc trạng thái (rào "khung mới"), nên REQUEST thứ nhất là PING, không đổi trạng thái bo.
    io.set_estop(False)
    io.advance(0.2)
    cleared = link.clear_fault()
    assert cleared.outcome == "CLEARED" and cleared.hello is None and cleared.session_reused and not cleared.hello_sent
    assert "Dùng phiên đang có" in "\n".join(cleared.lines()) and "PING" in "\n".join(cleared.lines())
    assert requests == [Action.PING, Action.CLEAR_FAULT] and io.connected and io.firmware.state == State.DISARMED
    assert cleared.requests_sent == 2 and cleared.commands_sent == 0
    assert [r["outcome"] for r in link.board_actions] == ["ESTOP_PRESSED", "CLEARED"]
    assert link.board_actions[0]["hello_boot_id"] != "" and link.board_actions[1]["hello_boot_id"] == ""
    # Bo không ở FAULT: không gửi CLEAR_FAULT. Phiên cũ mà laptop đã chốt mất liên lạc (TELEMETRY_STALE) thì không dùng
    # lại: bấm nút mở phiên mới (HELLO), vì bo khởi động lại không gửi telemetry cho phiên cũ.
    fresh = sim_io(cfg, START)
    fresh.connect()
    fresh.set_link(False)
    fresh.advance(0.5)
    fresh.set_link(True)
    assert fresh.connected and fresh.rearm_required
    fresh_requests = record_requests(fresh)
    other = VehicleLink(DriveMode.OBSERVE, fresh, pose_source=SimTruthPose(fresh))
    report = other.clear_fault()
    assert report.outcome == "NOT_NEEDED" and report.ok and not report.sent and report.requests_sent == 0
    assert report.hello_sent and report.hello is not None and not report.session_reused
    assert fresh_requests == [] and "không cần và không gửi CLEAR_FAULT" in report.summary()


def test_clear_fault_estop_pressed_after_the_telemetry_is_refused_by_the_board(cfg):
    """E-stop nhấn lại đúng lúc REQUEST tới bo (sau khung dùng để quyết định): firmware tự kiểm và từ chối."""
    io = faulted_sim_io(cfg)
    firmware = io.firmware
    original = firmware._handle_request

    def press_then_handle(msg, now):
        if Action(msg.action) == Action.CLEAR_FAULT:
            firmware.inputs = replace(firmware.inputs, estop=True)
        original(msg, now)

    firmware._handle_request = press_then_handle
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=SimTruthPose(io))
    report = link.clear_fault()
    assert report.outcome == "REFUSED" and report.ack_result == "ESTOP_ACTIVE" and report.sent and not report.ok
    assert report.after is not None and report.after.state == State.FAULT and firmware.state == State.FAULT
    assert "COMMAND_REJECTED" in [e.code for e in report.events]
    assert "ESTOP_ACTIVE" in report.summary() and "nhả nút" in report.summary()
    assert report.commands_sent == 0 and link.board_actions[0]["ack_result"] == "ESTOP_ACTIVE"


def test_clear_fault_ack_ok_but_fault_again_is_not_confirmed(cfg):
    """Bo trả ACK OK nhưng E-stop nhấn lại ngay sau đó (dây chập chờn): khung sau báo FAULT → NOT_CONFIRMED, báo cáo
    không nói đã xóa."""
    io = faulted_sim_io(cfg)
    original = io.firmware._handle_request

    def handle_then_press(msg, now):
        original(msg, now)
        if Action(msg.action) == Action.CLEAR_FAULT:
            io.set_estop(True)

    io.firmware._handle_request = handle_then_press
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=SimTruthPose(io))
    report = link.clear_fault()
    assert report.outcome == "NOT_CONFIRMED" and report.ack_result == "OK" and not report.ok
    assert report.after.state == State.FAULT and report.after.estop_input
    assert "vẫn báo FAULT, lỗi ESTOP" in report.summary() and "Đã xóa lỗi" not in report.summary()
    assert link.board_actions[0]["state_after"] == "FAULT" and link.board_actions[0]["outcome"] == "NOT_CONFIRMED"


def test_clear_fault_supply_low_refused_until_voltage_is_back_on_fake_serial(cfg):
    clock = ManualClock()
    supply = {"mv": 6000}
    firmware = FirmwareModel(replace(FAST_FW, min_supply_mv=7000), boot_id=0xB007)
    loop = FirmwareSerialLoopback(firmware, clock,
                                  inputs=lambda _t: FirmwareInputs(supply_valid=True, supply_mv=supply["mv"]))
    loop.advance(300)
    assert firmware.state == State.FAULT and firmware.fault == Fault.SUPPLY_LOW
    io = SerialVehicleIO(loop, clock=clock, rng=random.Random(5), port="COM7")
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=NoPoseSource())
    first = link.clear_fault()
    assert first.outcome == "REFUSED" and first.ack_result == "FAULT_ACTIVE" and first.sent and not first.simulated
    assert first.after.fault == Fault.SUPPLY_LOW and "điện áp" in first.summary()
    supply["mv"] = 7400                                          # điện áp đo lại đủ ngưỡng
    second = link.clear_fault()
    assert second.outcome == "CLEARED" and second.session_reused and firmware.state == State.DISARMED
    sent = host_messages(loop)
    assert [type(m) for m in sent] == [Hello, Request, Request, Request]
    # lần bấm thứ hai dùng lại phiên: PING rào "khung mới" trước CLEAR_FAULT (sau review 02/10/2026)
    assert [Action(m.action) for m in sent[1:]] == [Action.CLEAR_FAULT, Action.PING, Action.CLEAR_FAULT]
    assert not loop.closed and io.transport is loop and io.connected    # liên kết không mở cổng này: không đóng
    assert [(r["target"], r["outcome"], r["ack_result"]) for r in link.board_actions] == \
        [("COM7", "REFUSED", "FAULT_ACTIVE"), ("COM7", "CLEARED", "OK")]
    assert [r["commands_sent"] for r in link.board_actions] == [0, 0]


class TickingClock:
    """Đồng hồ io kiểu đồng hồ tường trên cổng serial GIẢ: ManualClock + 1 µs mỗi lần đọc, nên mỗi lần đọc cổng mang dấu
    thời gian riêng. Với ManualClock trần, cổng còn byte thì đồng hồ đứng yên và khung tồn đọng không bao giờ "mới hơn"
    lúc bấm: lỗi bên dưới không hiện ra."""

    def __init__(self, base: ManualClock):
        self.base, self.calls = base, 0

    def __call__(self) -> float:
        self.calls += 1
        return self.base() + self.calls * 1e-6


@pytest.mark.parametrize("estop_at_press", [False, True], ids=["released", "pressed"])
def test_clear_fault_on_a_reused_session_decides_on_a_frame_sent_after_the_press(cfg, estop_at_press):
    """Sửa sau review 02/10/2026: phiên đang mở (cổng giữ mở giữa các lần chạy, T2), laptop không đọc cổng 120 s: hơn
    hai lần đọc PUMP_MAX_BYTES khung DISARMED tồn đọng. Rồi E-stop nhấn 0,5 s và nhả (hay giữ nhấn): bo FAULT ESTOP.
    Quyết định phải theo khung bo gửi SAU lúc bấm (PING chờ ACK làm rào). Trước đó chỉ một lần đọc không chờ: khung
    DISARMED cũ đọc ở lần sau mang dấu thời gian mới, báo NOT_NEEDED (màu xanh) trong khi bo đang FAULT."""
    clock = ManualClock()
    state = {"estop": False}
    firmware = FirmwareModel(FAST_FW, boot_id=0xB007)
    loop = FirmwareSerialLoopback(firmware, clock, inputs=lambda _t: FirmwareInputs(estop=state["estop"]))
    io = SerialVehicleIO(loop, clock=TickingClock(clock), rng=random.Random(8), port="COM7")
    io.connect()
    loop.advance(120_000)                                        # không ai đọc cổng
    state["estop"] = True
    loop.advance(500)
    state["estop"] = estop_at_press
    loop.advance(200)
    assert firmware.state == State.FAULT and loop.in_waiting > 2 * PUMP_MAX_BYTES
    assert io.connected and not io.rearm_required                # laptop chưa đọc gì nên chưa thấy mất liên lạc
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=NoPoseSource())
    written, pressed_ms = len(loop.written), clock.t_ms
    report = link.clear_fault()
    before = report.before
    assert report.session_reused and before.device_time_ms > pressed_ms     # khung bo gửi sau lúc bấm
    assert (before.state, before.fault, before.estop_input) == (State.FAULT, Fault.ESTOP, estop_at_press)
    actions = [Action(m.action) for m in host_messages(loop, written)]
    if estop_at_press:
        assert report.outcome == "ESTOP_PRESSED" and actions == [Action.PING] and firmware.state == State.FAULT
    else:
        assert report.outcome == "CLEARED" and actions == [Action.PING, Action.CLEAR_FAULT]
        assert firmware.state == State.DISARMED and report.requests_sent == 2
    assert report.commands_sent == 0 and link.board_actions[0]["outcome"] == report.outcome


def test_clear_fault_on_a_real_port_link_opens_the_port_then_closes_it(scenario, cfg, no_serial_open):
    firmware, clock, inputs, _state = faulted_firmware()
    loops = []
    io = SerialVehicleIO(None, opener=fake_opener(firmware, clock, inputs, loops), clock=clock,
                         rng=random.Random(6), port="COM7")
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=NoPoseSource())
    first = link.clear_fault()
    assert first.outcome == "CLEARED" and first.hello is not None and first.target == "COM7"
    assert len(loops) == 1 and loops[0].closed and io.transport is None and not io.connected
    sent = host_messages(loops[0])
    assert [type(m) for m in sent] == [Hello, Request] and Action(sent[1].action) == Action.CLEAR_FAULT
    assert firmware.state == State.DISARMED
    second = link.clear_fault()                                  # mở lại cổng (loop mới), HELLO, bo đã hết lỗi
    assert second.outcome == "NOT_NEEDED" and second.hello is not None and len(loops) == 2 and loops[1].closed
    assert [type(m) for m in host_messages(loops[1])] == [Hello]
    assert "FIRMWARE_RESET" not in [e.code for e in second.events] and io.transport is None
    assert [r["outcome"] for r in link.board_actions] == ["CLEARED", "NOT_NEEDED"]
    session = straight_session(scenario, cfg)
    session.set_vehicle_link(link)
    with pytest.raises(SessionError, match="nguồn tư thế thật"):
        session.start_run()                                      # bo thật vẫn bị từ chối trước khi mở cổng (T2)
    assert len(loops) == 2 and [r["code"] for r in link.start_refusals] == ["START_NO_POSE_SOURCE"]
    session.close()
    assert no_serial_open == []


def test_clear_fault_open_failure_and_unplug_are_reported_not_raised(cfg):
    def cannot_open():
        raise OSError("could not open port 'COM7': PermissionError(13, 'Access is denied.', None, 5)")

    io = SerialVehicleIO(None, opener=cannot_open, clock=ManualClock(), port="COM7")
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=NoPoseSource())
    report = link.clear_fault()
    assert report.outcome == "NO_LINK" and not report.sent and report.error.startswith("Không mở được COM7")
    assert io.transport is None and io.stats.frames_sent == 0
    assert len(link.board_actions) == 1 and "PermissionError" in link.board_actions[0]["message"]
    assert "Không có liên lạc với bo" in report.summary() and report.lines()[-1].startswith("LỖI: Không mở được")

    # Rút cáp ngay sau khi bo xử lý CLEAR_FAULT: không có ACK, không treo, không báo đã xóa.
    firmware, clock, inputs, _state = faulted_firmware()
    loops = []
    io = SerialVehicleIO(None, opener=fake_opener(firmware, clock, inputs, loops), clock=clock,
                         rng=random.Random(7), port="COM7")
    original = firmware._handle_request

    def handle_then_unplug(msg, now):
        original(msg, now)
        if Action(msg.action) == Action.CLEAR_FAULT:
            loops[-1].unplug()

    firmware._handle_request = handle_then_unplug
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=NoPoseSource())
    start_ms = clock.t_ms
    report = link.clear_fault()
    assert report.outcome == "NO_ACK" and report.sent and not report.ok and report.ack_result == ""
    assert "Không đọc được cổng" in report.error and report.after is None
    assert "LINK_ERROR" in [e.code for e in report.events] and io.transport is None and not io.connected
    assert clock.t_ms - start_ms < 5000                          # không treo
    assert firmware.state == State.DISARMED and "chưa chắc" in report.summary()   # bo thật ra đã xóa lỗi
    assert "không nhận được ACK" in "\n".join(report.lines())
    assert link.board_actions[0]["outcome"] == "NO_ACK" and "LINK_ERROR" in link.board_actions[0]["message"]


def test_clear_fault_blocked_for_ui_sim_board_open_run_and_closed_link(scenario, cfg, tmp_path):
    ui_link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SimIOConfig(firmware=FAST_FW))
    assert "bo mô phỏng" in ui_link.clear_fault_blocker
    with pytest.raises(VehicleLinkError, match="bo mô phỏng"):
        ui_link.clear_fault()
    assert ui_link.board_actions == []
    written = ui_link.write_logs(tmp_path / "chua_chay")
    assert written["board_actions.csv"].read_text(encoding="utf-8").splitlines() == [",".join(BOARD_ACTION_FIELDS)]

    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    requests = record_requests(io)
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=SimTruthPose(io))
    session.set_vehicle_link(link)
    session.start_run()
    assert session.state == SessionState.RUNNING and "đang có lần chạy" in link.clear_fault_blocker
    with pytest.raises(VehicleLinkError, match="đang có lần chạy"):
        link.clear_fault()
    session.advance(0.3)
    session.request_stop()
    assert session.state == SessionState.STOPPING and "đang có lần chạy" in link.clear_fault_blocker
    for _ in range(100):
        session.advance(0.1)
        if not session.simulating:
            break
    assert session.state == SessionState.STOPPED and link.clear_fault_blocker is None
    assert Action.CLEAR_FAULT not in requests and link.board_actions == []
    session.close()
    assert "đã đóng" in link.clear_fault_blocker
    with pytest.raises(VehicleLinkError, match="đã đóng"):
        link.clear_fault()
    assert link.board_actions == []


def test_window_clear_fault_button_follows_mode_board_and_run_state(window, dialogs, no_serial_open):
    button = window.btn_clear_fault
    session = window.session
    assert session.drive_mode == DriveMode.SIM
    assert not button.isEnabled() and "Mô phỏng giai đoạn 0" in button.toolTip()
    window.combo_drive.setCurrentIndex(window.combo_drive.findData(DriveMode.VEHICLE_IO.value))
    assert not button.isEnabled() and "bo mô phỏng" in button.toolTip()
    assert window._clear_board_fault() is None and window.last_board_clear is None
    assert "không dùng với bo mô phỏng" in window.lbl_board_hint.text()
    select_port(window, "COM10")
    assert button.isEnabled() and "Đang khóa" not in button.toolTip()
    assert session.vehicle_link.io.transport is None and "dùng chính cổng này" in window.lbl_board_hint.text()
    # Liên kết tiêm vào (bo mô phỏng đặt ở điểm xuất phát) để chạy thật một lần.
    io = sim_io(session.cfg, session.scenario.start)
    requests = record_requests(io)
    session.set_vehicle_link(VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=SimTruthPose(io)))
    window._refresh_mode_widgets()
    assert button.isEnabled()
    assert window.plan(sync=True).ok
    window.run()
    assert session.state == SessionState.RUNNING
    window._refresh_mode_widgets()
    assert not button.isEnabled() and "chỉ dùng khi đang chỉnh hoặc sẵn sàng" in button.toolTip()
    assert window._clear_board_fault() is None and Action.CLEAR_FAULT not in requests   # kể cả gọi thẳng
    window.stop()
    for _ in range(100):
        window.advance_by(0.1)
        if not session.simulating:
            break
    assert session.state == SessionState.STOPPED
    window._refresh_mode_widgets()
    assert not button.isEnabled()
    window.reset()
    assert button.isEnabled() and Action.CLEAR_FAULT not in requests
    assert no_serial_open == [] and dialogs["question"] == []


@pytest.mark.parametrize("released", [True, False], ids=["released", "pressed"])
def test_window_clear_fault_on_a_real_port(window, dialogs, no_serial_open, monkeypatch, released):
    from PySide6.QtWidgets import QMessageBox
    from autopark.ui import theme

    firmware, clock, inputs, _state = faulted_firmware(released)
    loops = []
    opener = fake_opener(firmware, clock, inputs, loops)
    monkeypatch.setattr(SerialVehicleIO, "_port_opener", staticmethod(lambda port, b, rt, wt: opener))
    window.combo_drive.setCurrentIndex(window.combo_drive.findData(DriveMode.VEHICLE_IO.value))
    select_port(window, "COM10")
    link = window.session.vehicle_link
    link.io.clock = clock                                        # đồng hồ chung với cổng giả: test xác định
    assert loops == [] and window.btn_clear_fault.isEnabled()   # chọn cổng không mở cổng
    window.btn_clear_fault.click()
    assert len(dialogs["question"]) == 1
    title, text = dialogs["question"][0][1:3]
    assert "CLEAR_FAULT" in title and "COM10" in text and "CLEAR_FAULT" in text
    report = window.last_board_clear
    label = window.lbl_board_report.text()
    assert len(loops) == 1 and loops[0].closed and link.io.transport is None and len(link.board_actions) == 1
    assert window.statusBar().currentMessage().startswith("CLEAR_FAULT COM10")
    sent = host_messages(loops[0])
    assert not any(isinstance(m, Command) for m in sent)
    if released:
        assert report.outcome == "CLEARED"
        assert "Đã xóa lỗi" in label and "DISARMED" in label and theme.OK in label
        assert [type(m) for m in sent] == [Hello, Request] and Action(sent[1].action) == Action.CLEAR_FAULT
        assert firmware.state == State.DISARMED
    else:
        assert report.outcome == "ESTOP_PRESSED"
        assert "NHẤN" in label and theme.WARN in label
        assert [type(m) for m in sent] == [Hello] and firmware.state == State.FAULT
    dialogs["answer"] = QMessageBox.StandardButton.No           # không đồng ý: không mở cổng, không ghi dòng
    assert window._clear_board_fault() is None
    assert len(dialogs["question"]) == 2 and len(loops) == 1 and len(link.board_actions) == 1
    assert no_serial_open == []
