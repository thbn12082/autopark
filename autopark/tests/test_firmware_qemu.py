"""Firmware THẬT (env PlatformIO esp32s3_qemu) chạy trong QEMU ESP32-S3; laptop nói chuyện bằng SerialVehicleIO qua
`socket://` (thêm 30/09/2026, docs/PHAN_CUNG_VA_HIEU_CHUAN.md).

Phần đọc cấu hình và phần kiểm cơ chế chạy lại (bo giả `LoopbackBoard`) chạy ở mọi máy. Phần bo ảo bỏ qua khi
configs/thiet_bi.json không có qemu_xtensa/platformio_python hoặc tệp không tồn tại (laptop nộp đồ án). Bo ảo chạy theo
thời gian thực: cả tệp ≈ 9–10 s (chay_lap_test_bo_ao*.txt, 30/09/2026); lần build đầu của env thêm vài phút. Chạy được ở đây KHÔNG chứng minh gì về bo thật: QEMU không
có LEDC, GPIO vào, watchdog kích hoạt, USB-CDC (autopark.transport.qemu_board).

Thêm 02/10/2026: `test_parking_session_through_qemu_board` chạy cả một phiên đỗ qua bo ảo (Session →
VehicleLink.qemu_board, xe mô phỏng phía laptop, `transport/qemu_plant.py`), thêm ≈ 6–10 s; bo ảo GIẢ cho các test phiên
khác ở tests/qemu_fakes.py.
"""
import json
import statistics
import time
import warnings

import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.application.vehicle_link import DriveMode, VehicleLink
from autopark.domain.types import ParkingGoal, Pose
from autopark.transport import qemu_board
from autopark.transport.firmware_model import FirmwareConfig, FirmwareModel
from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock
from autopark.transport.protocol import Fault, ResetReason, State, StopReason, TelemetryFlag
from autopark.transport.vehicle_io import SerialVehicleIO, VehicleIOError


# ---- đọc cấu hình công cụ (mọi máy) ---------------------------------------------------------------------------------
def write_config(tmp_path, data: dict, *, bom: bool = False):
    path = tmp_path / "thiet_bi.json"
    path.write_text(("\ufeff" if bom else "") + json.dumps(data), encoding="utf-8")
    return path


def test_load_tools_reads_the_paths_and_accepts_a_bom(tmp_path):
    qemu = tmp_path / "qemu-system-xtensa.exe"
    python = tmp_path / "python.exe"
    core = tmp_path / "core"
    qemu.write_bytes(b"")
    python.write_bytes(b"")
    core.mkdir()
    path = write_config(tmp_path, {"lidar_port": "COM3", "qemu_xtensa": str(qemu), "platformio_python": str(python),
                                   "platformio_core_dir": str(core)}, bom=True)
    tools = qemu_board.load_tools(path)
    assert (tools.qemu, tools.platformio_python, tools.platformio_core_dir) == (qemu, python, core)
    only_qemu = qemu_board.load_tools(write_config(tmp_path, {"qemu_xtensa": str(qemu), "platformio_python": ""}))
    assert only_qemu.platformio_python is None and only_qemu.platformio_core_dir is None


@pytest.mark.parametrize("data, match", [
    ({"lidar_port": "COM3"}, "qemu_xtensa"),
    ({"qemu_xtensa": "Z:/khong/co/qemu.exe"}, "không thấy QEMU"),
    ({"qemu_xtensa": 5}, "chuỗi"),
])
def test_load_tools_reports_what_is_missing(tmp_path, data, match):
    with pytest.raises(qemu_board.QemuBoardError, match=match):
        qemu_board.load_tools(write_config(tmp_path, data))


def test_load_tools_rejects_missing_platformio_paths_and_a_missing_file(tmp_path):
    qemu = tmp_path / "qemu.exe"
    qemu.write_bytes(b"")
    with pytest.raises(qemu_board.QemuBoardError, match="platformio_python"):
        qemu_board.load_tools(write_config(tmp_path, {"qemu_xtensa": str(qemu), "platformio_python": "Z:/py.exe"}))
    # thư mục core sai thì báo lỗi, không để PlatformIO tự tạo thư mục mới và tải lại ≈ 3 GB
    with pytest.raises(qemu_board.QemuBoardError, match="platformio_core_dir"):
        qemu_board.load_tools(write_config(tmp_path, {"qemu_xtensa": str(qemu), "platformio_core_dir": "Z:/core"}))
    with pytest.raises(qemu_board.QemuBoardError, match="không đọc được"):
        qemu_board.load_tools(tmp_path / "khong_co.json")


# ---- cơ chế chạy lại khi bo ảo trục trặc ----------------------------------------------------------------------------
def fresh_io(board) -> SerialVehicleIO:
    """Phiên mới trên bo. Bo đang chốt LOOP_OVERRUN từ trước (máy bận làm QEMU trễ > 100 ms giữa hai chu kỳ; đúng thiết kế
    của firmware, không phải lỗi của kịch bản sắp chạy) thì cảnh báo, CLEAR_FAULT, rồi mở phiên mới: ACK của CLEAR_FAULT
    về trước telemetry kế tiếp, nên phải có khung mới mới biết trạng thái thật."""
    io = board.open_io()
    try:
        qemu_board.connect_with_retry(io)
        if io.wait_ready() == State.FAULT and io.latest().fault == Fault.LOOP_OVERRUN:
            warnings.warn("bo ảo đang chốt LOOP_OVERRUN từ trước (máy bận); CLEAR_FAULT rồi mở phiên mới")
            io.clear_fault()
            qemu_board.connect_with_retry(io)
            assert io.wait_ready() == State.DISARMED
    except BaseException:
        io.close()
        raise
    return io


def overrun_latched(board) -> bool:
    """Firmware có đang chốt LOOP_OVERRUN không. HELLO không gỡ chốt FAULT, nên hỏi bằng một phiên mới được."""
    io = board.open_io()
    try:
        qemu_board.connect_with_retry(io)
        return io.wait_ready() == State.FAULT and io.latest().fault == Fault.LOOP_OVERRUN
    finally:
        io.close()


def on_board(board, body, attempts: int = 3):
    """Chạy `body(io)` trên một phiên mới. Hỏng (assert, VehicleIOError, lỗi cổng, kể cả lúc mở phiên) do chính bo ảo thì
    kết quả vô nghĩa, chạy lại, tối đa `attempts` lần, có cảnh báo: (1) tiến trình QEMU tự thoát (espressif/qemu#175, hay
    gặp lúc chip khởi động) → khởi động lại bo ảo; (2) firmware đang chốt LOOP_OVERRUN (QEMU bị máy chủ bỏ đói > 100 ms).
    Hỏng mà không có hai dấu hiệu đó thì báo lỗi ngay."""
    for attempt in range(1, attempts + 1):
        if not board.running():
            warnings.warn(f"QEMU đã tự thoát (espressif/qemu#175) trước lần {attempt}/{attempts}; khởi động lại bo ảo")
            board.start()
        io = None
        try:
            io = fresh_io(board)
            return body(io)
        except (AssertionError, VehicleIOError, OSError):
            if io is not None:
                io.close()
            if attempt < attempts and not board.running():
                continue                                             # lần sau khởi động lại QEMU (có cảnh báo)
            if attempt < attempts and overrun_latched(board):
                warnings.warn(f"bo ảo chốt LOOP_OVERRUN (máy bận) ở lần {attempt}/{attempts}; chạy lại kịch bản")
                continue
            raise
        finally:
            if io is not None:
                io.close()


class LoopbackBoard:
    """Bo giả để kiểm `fresh_io`/`on_board` ở mọi máy: `FirmwareModel` (bản tham chiếu) dùng chung qua các phiên, mỗi
    phiên một `FirmwareSerialLoopback` trên cùng đồng hồ tay. `stall_ms` làm như QEMU bị bỏ đói: phiên kế tiếp bắt đầu
    sau một khoảng trống, firmware chốt LOOP_OVERRUN."""

    def __init__(self):
        self.clock = ManualClock()
        self.firmware = FirmwareModel(FirmwareConfig(boot_hold_ms=100), boot_id=0xB007)
        self.loops: list[FirmwareSerialLoopback] = []
        self.alive = True
        self.starts = 0

    def open_io(self) -> SerialVehicleIO:
        loop = FirmwareSerialLoopback(self.firmware, self.clock)
        self.loops.append(loop)
        return SerialVehicleIO(loop, clock=self.clock)

    def stall_ms(self, ms: int) -> None:
        """Bo "đứng" `ms`: đồng hồ đi tiếp nhưng firmware không chạy nhịp nào (loopback mặc định chạy bù mọi nhịp)."""
        self.clock.advance_ms(ms)
        for loop in self.loops:
            loop.next_tick_ms = max(loop.next_tick_ms, self.clock.t_ms + loop.tick_ms)

    def running(self) -> bool:
        return self.alive

    def start(self) -> "LoopbackBoard":
        self.alive = True
        self.starts += 1
        return self


def test_fresh_io_clears_a_latched_loop_overrun():
    board = LoopbackBoard()
    fresh_io(board).close()
    board.stall_ms(200)
    assert overrun_latched(board)
    with pytest.warns(UserWarning, match="LOOP_OVERRUN"):
        io = fresh_io(board)
    assert io.latest().state == State.DISARMED and board.firmware.state == State.DISARMED
    io.arm()                                                         # dùng được ngay
    assert board.firmware.state == State.ARMED


def test_on_board_reruns_only_when_the_board_itself_failed():
    board = LoopbackBoard()
    calls = []

    def starved_once(io):
        calls.append(io)
        if len(calls) == 1:
            board.stall_ms(200)                                      # QEMU bị bỏ đói giữa kịch bản...
            io.poll()                                                # ...firmware chốt LOOP_OVERRUN
            raise AssertionError("kịch bản hỏng vì bo ảo")
        return "ok"

    with pytest.warns(UserWarning):
        assert on_board(board, starved_once) == "ok"
    assert len(calls) == 2

    calls.clear()

    def logic_bug(io):
        calls.append(io)
        assert False, "lỗi logic thật"

    with pytest.raises(AssertionError, match="lỗi logic thật"):
        on_board(board, logic_bug)
    assert len(calls) == 1                                           # không chạy lại lỗi không do bo ảo

    calls.clear()

    def qemu_died_once(io):
        calls.append(io)
        if len(calls) == 1:
            board.alive = False                                      # như QEMU tự thoát (#175)
            raise OSError("mất kết nối")
        return "ok"

    with pytest.warns(UserWarning, match="qemu#175"):
        assert on_board(board, qemu_died_once) == "ok"
    assert len(calls) == 2 and board.starts == 1


# ---- bo ảo QEMU -----------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def board():
    try:
        tools = qemu_board.load_tools()
    except qemu_board.QemuBoardError as exc:
        pytest.skip(f"không có bo ảo trên máy này: {exc}")
    if tools.platformio_python is None:
        pytest.skip("configs/thiet_bi.json không có platformio_python: không build được bo ảo")
    image = qemu_board.build_image(tools)
    with qemu_board.QemuBoard(image, tools) as b:
        yield b


def pump(io, seconds: float, ping_every: float | None = 0.1) -> list:
    frames = []
    end = io.now() + seconds
    while io.now() < end:
        frames += io.poll()
        if ping_every is not None and io.connected and io.now() - io.last_tx_time >= ping_every:
            io.ping()                                                # mất phiên (bo reset) thì thôi PING
    return frames


def device_steps_ms(frames) -> list[int]:
    return [(b.device_time_ms - a.device_time_ms) & 0xFFFFFFFF for a, b in zip(frames, frames[1:])]


def test_hello_ack_matches_the_python_reference(board):
    """Giới hạn, chu kỳ telemetry, phiên bản firmware của bản build thật = của FirmwareModel(FirmwareConfig())."""
    expected = SerialVehicleIO(FirmwareSerialLoopback(FirmwareModel(FirmwareConfig()), ManualClock())).connect()

    def body(io):
        got = io.hello
        assert got.limits == expected.limits
        assert got.telemetry_period_s == expected.telemetry_period_s == 0.05
        assert got.firmware_version == expected.firmware_version
        assert got.reset_reason == ResetReason.POWER_ON
        assert io.latest().state == State.DISARMED

    on_board(board, body)


def test_telemetry_is_20hz_with_clean_frames(board):
    def body(io):
        io.poll()
        errors0 = dict(io.parser.stats.as_dict())
        missed0 = io.stats.device_messages_missed
        frames = pump(io, 1.0)
        assert len(frames) >= 17
        assert statistics.median(device_steps_ms(frames)) == 50
        errors = io.parser.stats.as_dict()
        assert all(errors[k] == errors0[k] for k in ("cobs", "short", "crc", "version", "type", "length", "oversize"))
        assert io.stats.device_messages_missed == missed0

    on_board(board, body)


def test_command_ramps_then_expires_and_host_silence_disarms(board):
    def body(io):
        lim = io.hello.limits
        io.arm()
        io.send(0.2, 0.1, enable=True, validity_s=0.25)
        frames = pump(io, 0.8)
        running = [f for f in frames if f.state == State.RUNNING]
        expired = [f for f in frames if f.state == State.ARMED and f.stop_reason == StopReason.COMMAND_TIMEOUT]
        assert running and expired and expired[0].stamp.t > running[0].stamp.t
        peak = max(f.speed_ref_mps for f in frames)
        assert 0.03 <= peak <= 0.2 + 1e-3                            # có tăng tốc (29/09: 0,075), không vượt lệnh
        for a, b in zip(frames, frames[1:]):                       # dốc tăng tốc theo giới hạn trong HELLO_ACK
            dt = ((b.device_time_ms - a.device_time_ms) & 0xFFFFFFFF) / 1000.0
            assert b.speed_ref_mps - a.speed_ref_mps <= lim.max_accel_mps2 * dt + 0.002
        t_last_tx = io.last_tx_time
        frames = pump(io, 1.0, ping_every=None)                      # laptop im: không PING
        disarmed = [f for f in frames if f.state == State.DISARMED]
        assert disarmed and disarmed[0].stop_reason == StopReason.LINK_TIMEOUT and not disarmed[0].link_ok
        assert disarmed[0].stamp.t - t_last_tx >= lim.link_timeout_s - 0.05

    on_board(board, body)


def test_command_while_disarmed_is_rejected(board):
    def body(io):
        before = io.stats.rejected.get("BAD_STATE", 0)
        io.send(0.1, 0.0, enable=True, validity_s=0.2)
        pump(io, 0.3)
        assert io.stats.rejected.get("BAD_STATE", 0) == before + 1
        assert io.latest().state == State.DISARMED

    on_board(board, body)


def test_nonblocking_control_loop_keeps_up_with_telemetry(board):
    """Vòng 50 Hz kiểu Session (`poll(block=False)` + `send`), chỉ đếm khung nhận TRONG vòng. Trước sửa `_pump`
    30/09/2026, cùng vòng này qua `socket://` của pyserial nhận 2/≈ 40 khung trong 2 s kèm TELEMETRY_STALE
    (evidence/mo_phong_20260930/qemu_espressif_29092026/run2_report.json, `loop.plain`)."""
    def body(io):
        io.arm()
        io.take_new()                                                # bỏ khung đã nhận trong fresh_io/arm
        missed0 = io.stats.device_messages_missed
        got = []
        end = time.perf_counter() + 2.0
        while time.perf_counter() < end:
            t = time.perf_counter()
            got += io.poll(block=False)
            io.send(0.1, 0.0, enable=True, validity_s=0.15)
            rest = 0.02 - (time.perf_counter() - t)
            if rest > 0:
                time.sleep(rest)
        io.stop()
        io.disarm()
        assert len(got) >= 36                                        # ≈ 40 khung trong 2 s
        assert io.stats.device_messages_missed == missed0            # không mất số thứ tự nào
        assert "TELEMETRY_STALE" not in [e.code for e in io.events()]

    on_board(board, body)


class BoardSource:
    """`QemuBoardSource` cho fixture `board`: bo khi QEMU còn chạy."""

    def __init__(self, board):
        self.board = board

    def current_board(self):
        return (self.board, "") if self.board.running() else (None, "QEMU đã tự thoát")


def parking_run(board, scenario, cfg) -> tuple[Session, VehicleLink, float | None]:
    """Một lần đỗ VEHICLE_IO qua bo ảo theo đồng hồ tường (nhịp 16 ms như giao diện, tối đa 20 s). Trả (phiên, liên kết,
    số lõi CPU QEMU dùng trung bình trong lần chạy hoặc None)."""
    session = Session(scenario, cfg)
    assert session.plan_sync().ok
    link = VehicleLink.qemu_board(DriveMode.VEHICLE_IO, BoardSource(board))
    session.set_vehicle_link(link)
    session.start_run()
    cpu0, t0 = board.cpu_seconds(), time.perf_counter()
    deadline = t0 + 20.0
    while session.simulating and time.perf_counter() < deadline:
        time.sleep(0.016)
        session.advance(0.016)
    cpu1, t1 = board.cpu_seconds(), time.perf_counter()
    cores = (cpu1 - cpu0) / (t1 - t0) if cpu0 is not None and cpu1 is not None else None
    return session, link, cores


def test_parking_session_through_qemu_board(board, scenario, cfg, request):
    """Phiên đỗ qua firmware THẬT trong QEMU (thêm 02/10/2026): Session → VehicleLink.qemu_board → QemuPlantVehicleIO →
    SocketPort → bo ảo, theo thời gian thực, đường thẳng 0,6 m. Tốc độ, góc lái, tư thế từ XE MÔ PHỎNG phía laptop;
    telemetry.csv giữ cờ của firmware (SPEED_VALID = 0). Chạy TRƯỚC test reset chip (reset đổi boot_id của chip ảo mà
    `board.hello` không biết). Bo ảo chốt LOOP_OVERRUN (máy bận) hay QEMU tự thoát: cảnh báo, xóa lỗi hoặc khởi động lại,
    chạy lại một lần (cùng luật bằng chứng với `on_board`)."""
    scenario.obstacles = []
    scenario.start, scenario.goal = Pose(0.5, 1.0, 0.0), ParkingGoal(Pose(1.1, 1.0, 0.0))
    for attempt in (1, 2):
        if not board.running():
            warnings.warn(f"QEMU đã tự thoát (espressif/qemu#175) trước lần {attempt}; khởi động lại bo ảo")
            board.start()
        try:
            session, link, cores = parking_run(board, scenario, cfg)
        except SessionError as exc:
            if attempt == 1 and ("LOOP_OVERRUN" in str(exc) or not board.running()):
                warnings.warn(f"bo ảo trục trặc lúc START ({exc}); xóa lỗi hoặc khởi động lại rồi chạy lại một lần")
                if board.running():
                    VehicleLink.qemu_board(DriveMode.VEHICLE_IO, BoardSource(board)).clear_fault()
                continue
            raise
        codes = [e.code for e in session.safety_events]
        board_trouble = not board.running() or any("LOOP_OVERRUN" in e.message for e in session.safety_events)
        if session.state != SessionState.COMPLETED and attempt == 1 and board_trouble:
            warnings.warn(f"bo ảo trục trặc giữa lần chạy ({session.stop_reason}); chạy lại một lần")
            if board.running():
                link.clear_fault()
            session.close()
            continue
        break
    try:
        assert session.state == SessionState.COMPLETED, f"{session.state}: {session.stop_reason}; sự kiện {codes}"
        assert "NO_MEASURED_STATE" not in codes
        rows = link.telemetry_rows
        assert rows and all(not int(r["flags"]) & TelemetryFlag.SPEED_VALID and r["speed_mps"] != "" for r in rows)
        assert link.io.stats.device_messages_missed == 0
        assert link.io.transport is None                          # đóng kết nối sau lần chạy (QEMU chỉ một client)
        assert link.describe()["board"]["hello"]["boot_id"] == f"0x{board.hello.boot_id:08x}"
        if cores is not None:
            print(f"QEMU dùng trung bình {cores:.2f} lõi CPU trong lần đỗ")
            if request.config.pluginmanager.hasplugin("junitxml"):
                # thuộc tính testsuite như `ecoqos` của conftest (record_property cảnh báo với JUnit xunit2)
                request.getfixturevalue("record_testsuite_property")("qemu_cpu_cores", f"{cores:.3f}")
    finally:
        session.close()


def test_chip_reset_is_seen_as_firmware_reset(board):
    """Chạy cuối: reset cả chip ảo (HMP system_reset). QEMU báo lý do POWER_ON; millis() không về 0 (khác chip thật).
    Laptop thấy mất liên lạc (TELEMETRY_STALE hoặc SESSION_LOST, tùy bo khởi động lại nhanh hay chậm hơn 0,3 s)."""
    def body(io):
        boot0 = io.hello.boot_id
        io.arm()
        board.reset()
        pump(io, 1.0)
        assert {"TELEMETRY_STALE", "SESSION_LOST"} & {e.code for e in io.events()}
        info = qemu_board.connect_with_retry(io)
        assert info.boot_id != boot0 and info.reset_reason == ResetReason.POWER_ON
        assert "FIRMWARE_RESET" in [e.code for e in io.events()]
        assert io.wait_ready() == State.DISARMED

    on_board(board, body, attempts=4)                                # mỗi lần reset là một lần khởi động (QEMU#175)
