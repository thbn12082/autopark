"""Sửa sau review đợt 2 (02/10/2026): xe mô phỏng phía laptop của bo ảo QEMU (`transport/qemu_plant.py`).

- Mỗi khung telemetry của CÙNG một lần đọc cổng có thời điểm riêng theo đồng hồ bo, kết thúc ở lúc nhận; xe theo tham
  chiếu của CHÍNH khung đó. Trước đó cả lần đọc chung một t: khung cũ nhất kéo xe suốt khoảng trễ.
- Mở lại socket neo lại thời gian của xe: khoảng socket đóng không được tích phân. Trước đó "Xóa lỗi bo"
  sau một lúc nghỉ tích phân cả lúc nghỉ theo bước 5 ms trên luồng giao diện.
- Chu kỳ telemetry của configs/bo_ao_qemu.json chỉ trong khoảng io nhận, 20..100 ms. Trước đó tệp nhận
  tới 1000 ms và mọi START với 101..1000 ms hỏng (START_ABORTED).

Bo ảo GIẢ (`tests/qemu_fakes.py`: FirmwareModel + ManualClock): không chạy QEMU, không mở cổng nào. Test của runner
ở tests/test_qemu_runner.py.
"""
import random

import pytest

from autopark.application.session import SessionState
from autopark.application.vehicle_link import DriveMode, VehicleLink
from autopark.domain.types import Pose
from autopark.simulation.vehicle import SimVehicle
from autopark.transport.protocol import NO_COMMAND_AGE, State, StopReason, TelemetryMsg
from autopark.transport.qemu_plant import (MAX_TELEMETRY_PERIOD_MS, MIN_TELEMETRY_PERIOD_MS, LaptopPlant, PlantConfig,
                                           QemuPlantVehicleIO)
from tests.qemu_fakes import FakeQemuBoard, FakeQemuSource
from tests.test_session_vehicle import straight_session


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


def armed_and_driving(cfg, ms: int = 1000):
    """Bo ảo giả, io đã đặt xe, kết nối, ARM, rồi chạy `ms` ở 0,2 m/s (lệnh mỗi 20 ms)."""
    board = FakeQemuBoard().start()
    io = plant_io(board)
    io.place_vehicle(cfg, Pose(0.5, 1.0, 0.0))
    io.connect()
    io.wait_ready()
    io.arm()
    pump(io, board, ms, send=lambda: io.send(0.2, 0.0, validity_s=0.15))
    return board, io


def count_calls(monkeypatch, cls, name: str) -> list:
    """Ghi đối số đầu (sau self) của mọi lời gọi `cls.name`, vẫn gọi hàm thật."""
    calls, original = [], getattr(cls, name)

    def spy(self, first, *args):
        calls.append(first)
        return original(self, first, *args)

    monkeypatch.setattr(cls, name, spy)
    return calls


def telemetry_msg(session_id: int, sequence: int, sample_time_ms: int) -> TelemetryMsg:
    return TelemetryMsg(session_id, sequence, sample_time_ms, int(State.ARMED), 0, 0, 0, 0, NO_COMMAND_AGE, 0, 0, 0, 0,
                        0, 0, 0, 0, 0, (0, 0, 0, 0), 0, 0, 0)


# ---- khung của một lần đọc, mỗi khung một thời điểm ---------------------------------------------------
def test_frames_of_one_read_each_follow_their_own_reference(cfg, monkeypatch):
    board, io = armed_and_driving(cfg)
    before, t_before = io.plant_sample()
    advanced = count_calls(monkeypatch, LaptopPlant, "advance_to")
    board.advance(600)              # vòng đọc trễ 600 ms: lệnh hết hạn, firmware dốc về 0 rồi DISARM (LINK_TIMEOUT)
    batch = io.poll(block=False)
    t_read = io.now()
    assert len(batch) >= 25 and {f.stamp.t for f in batch} == {t_read}     # dấu thời gian: vẫn là lúc nhận
    newest = batch[-1]
    assert (newest.state, newest.stop_reason, newest.speed_ref_mps) == (State.DISARMED, StopReason.LINK_TIMEOUT, 0.0)
    assert any(f.state == State.ARMED and f.stop_reason == StopReason.COMMAND_TIMEOUT for f in batch)
    lim, period = io.hello.limits, io.hello.telemetry_period_s
    for tel in batch:               # mỗi khung: tốc độ xe mô phỏng theo tham chiếu của CHÍNH khung đó
        assert abs(tel.speed_mps - tel.speed_ref_mps) <= lim.stop_decel_mps2 * period + 1e-3, tel
    assert batch[0].speed_mps == pytest.approx(0.2) and newest.speed_mps == 0.0
    # Thời điểm của xe: khung cuối ở đúng lúc nhận, khung trước lùi theo đồng hồ bo; không bao giờ quá lúc nhận.
    expected = [t_read - (newest.device_time_ms - f.device_time_ms) / 1000 for f in batch]
    assert advanced == pytest.approx(expected, abs=1e-9) and max(advanced) == t_read
    after, t_after = io.plant_sample()
    assert t_after == t_read                    # tư thế theo khung cuối, không ngoại suy
    # Quãng đường trong lúc trễ = tích phân tham chiếu của firmware theo đồng hồ bo + đoạn trước khung đầu (0,2 m/s).
    ref_travel = sum(0.5 * (a.speed_ref_mps + b.speed_ref_mps) * (b.device_time_ms - a.device_time_ms) / 1000
                     for a, b in zip(batch, batch[1:]))
    assert after.x - before.x == pytest.approx(ref_travel + 0.2 * (advanced[0] - t_before), abs=1e-3)
    assert after.x - before.x < 0.07                # trước khi sửa: 0,12 m (0,2 m/s suốt 600 ms)
    io.close()


def test_frame_times_follow_device_clock_and_never_pass_the_receive_time():
    board = FakeQemuBoard()
    io = QemuPlantVehicleIO(board)
    io.session_id = 7
    t = 100.0
    frames = [telemetry_msg(7, 1, 1000), telemetry_msg(9, 2, 1010), telemetry_msg(7, 3, 1020),
              telemetry_msg(7, 4, 1040)]
    times = io._frame_times(frames, t)          # khung của phiên khác (9) bị bỏ, như `_on_message`
    assert times == pytest.approx({id(frames[0]): 99.96, id(frames[2]): 99.98, id(frames[3]): t}, abs=1e-9)
    assert times[id(frames[3])] == t
    # Đồng hồ bo (u32 ms) quay vòng giữa lần đọc: vẫn lùi đúng 20 ms.
    wrap = [telemetry_msg(7, 5, 0xFFFFFFF0), telemetry_msg(7, 6, 4)]
    assert io._frame_times(wrap, t) == pytest.approx({id(wrap[0]): 99.98, id(wrap[1]): t}, abs=1e-9)
    # Đồng hồ bo lùi (bo khởi động lại giữa lần đọc): khung đó lấy t, không bao giờ sau t.
    reboot = [telemetry_msg(7, 7, 5000), telemetry_msg(7, 8, 120)]
    assert io._frame_times(reboot, t) == {id(reboot[0]): t, id(reboot[1]): t}
    assert io._frame_times([telemetry_msg(7, 9, 50)], t) == {}       # một khung: lấy t như trước


# ---- mở lại socket không tích phân khoảng socket đóng -------------------------------------------------
def test_reopen_reanchors_plant_so_closed_socket_gap_is_not_integrated(cfg, monkeypatch):
    board, io = armed_and_driving(cfg, ms=400)
    io.close()                                  # socket đóng khi xe mô phỏng còn chạy 0,2 m/s
    sample = io.plant_sample()
    assert io.plant.state.speed > 0.1
    steps = count_calls(monkeypatch, SimVehicle, "step")
    advanced = count_calls(monkeypatch, LaptopPlant, "advance_to")
    board.stall(60_000)                         # một phút socket đóng (QEMU bị bỏ đói: firmware chốt LOOP_OVERRUN)
    board.advance(20)
    io.reopen()
    assert io.plant_sample() == sample          # mở lại chưa đổi gì: t vẫn là t của khung cuối đã tiến tới
    io.connect()
    io.wait_ready()
    frames = pump(io, board, 100)
    t_first = advanced[0]                       # khung đầu sau khi mở: chỉ ghi t (đồng hồ io), không bước nào
    assert t_first > sample[1] + 60 and frames and io.plant.t == frames[-1].stamp.t
    assert sum(steps) == pytest.approx(io.plant.t - t_first) and len(steps) <= 40     # trước khi sửa: ≥ 12 000 bước
    assert io.plant_sample()[0].distance_to(sample[0]) <= 0.2 * (io.plant.t - t_first) + 1e-6
    io.close()


def test_clear_fault_after_idle_period_does_not_integrate_the_idle_gap(scenario, cfg, monkeypatch):
    """Đường của review: lần chạy qua bo ảo xong, nghỉ lâu, firmware chốt LOOP_OVERRUN, bấm "Xóa lỗi bo"."""
    session = straight_session(scenario, cfg)
    board = FakeQemuBoard().start()
    link = VehicleLink.qemu_board(DriveMode.VEHICLE_IO, FakeQemuSource(board), clock=board.clock)
    session.set_vehicle_link(link)
    session.start_run()
    for _ in range(3000):
        board.advance(20)
        session.advance(0.02)
        if not session.simulating:
            break
    assert session.state == SessionState.COMPLETED and link.io.transport is None
    steps = count_calls(monkeypatch, SimVehicle, "step")
    board.stall(600_000)                        # mười phút nghỉ
    board.advance(20)
    report = link.clear_fault()                 # nút "Xóa lỗi bo" gọi trên luồng giao diện
    assert report.outcome == "CLEARED" and link.io.transport is None
    assert len(steps) <= 50                     # trước khi sửa: 120 010 bước 5 ms
    session.close()


# ---- chu kỳ telemetry trong khoảng io nhận ------------------------------------------------------------
def test_plant_config_period_limited_to_what_the_io_accepts(scenario, cfg):
    assert (MIN_TELEMETRY_PERIOD_MS, MAX_TELEMETRY_PERIOD_MS) == (20, 100)
    for period in (101, 200, 1000):             # firmware nhận tới 1000 ms, io chỉ tới 100 ms
        with pytest.raises(ValueError, match=r"telemetry_period_ms phải trong \[20, 100\] ms"):
            PlantConfig(telemetry_period_ms=period)
        with pytest.raises(ValueError, match="telemetry_period_ms"):
            PlantConfig.from_dict({"schema_version": 1, "telemetry_period_ms": period})
    for period in (MIN_TELEMETRY_PERIOD_MS, 50, MAX_TELEMETRY_PERIOD_MS):     # tệp nhận chu kỳ nào thì io cũng nhận
        io = QemuPlantVehicleIO(FakeQemuBoard(), plant_config=PlantConfig(telemetry_period_ms=period))
        assert io.telemetry_period_ms == period and io.transport is None
    # START qua bo ảo giả với chu kỳ lớn nhất chạy được, không TELEMETRY_STALE hay STALE_TELEMETRY.
    session = straight_session(scenario, cfg)
    board = FakeQemuBoard().start()
    link = VehicleLink.qemu_board(DriveMode.VEHICLE_IO, FakeQemuSource(board), clock=board.clock,
                                  plant_config=PlantConfig(telemetry_period_ms=MAX_TELEMETRY_PERIOD_MS))
    session.set_vehicle_link(link)
    session.start_run()
    assert session.state == SessionState.RUNNING and link.io.hello.telemetry_period_s == 0.1
    for _ in range(50):
        board.advance(20)
        session.advance(0.02)
    codes = [e.code for e in session.safety_events]
    assert session.state == SessionState.RUNNING and "STALE_TELEMETRY" not in codes and "TELEMETRY_STALE" not in codes
    session.close()
