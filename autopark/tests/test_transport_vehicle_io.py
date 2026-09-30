"""VehicleIO hai nhánh: mô phỏng (vòng kín có vùng chết, trễ, nhiễu) và serial (qua cổng giả nối FirmwareModel).
Không mở cổng nối tiếp thật nào; ba test mở cổng TCP cục bộ 127.0.0.1 qua `SocketPort` của dự án (URL `socket://`),
không test nào dùng `socket://` của pyserial."""
from dataclasses import replace
import json
import math
from pathlib import Path
import random
import socket
import statistics
import threading
import time

import pytest

from autopark.transport.firmware_model import FirmwareConfig, FirmwareInputs, FirmwareModel
from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock
from autopark.transport.protocol import (Command, DEVICE_TO_HOST, Fault, FrameParser, Result, State, StopReason,
                                         TelemetryFlag, TelemetryMsg, encode_frame)
from autopark.transport.socket_port import SocketPort
from autopark.transport.vehicle_io import (PUMP_MAX_S, SIM_FIRMWARE_DEFAULT, Heartbeat, SerialVehicleIO,
                                           SimActuatorConfig, SimIOConfig, SimSensorConfig, SimVehicleIO, VehicleIO,
                                           VehicleIOError, VehicleTelemetry, load_sim_io_config, round_half_away,
                                           speed_to_wire, steer_to_wire)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Mặc định firmware của mô phỏng (trần effort 1000 ‰ vì cơ cấu chấp hành giả định cần effort cao; số của mô phỏng).
FAST_FW = replace(SIM_FIRMWARE_DEFAULT, boot_hold_ms=200)


def sim(cfg, **overrides) -> SimVehicleIO:
    return SimVehicleIO(cfg, SimIOConfig(firmware=FAST_FW, **overrides))


def armed_sim(cfg, **overrides) -> SimVehicleIO:
    io = sim(cfg, **overrides)
    io.connect()
    assert io.wait_ready() == State.DISARMED
    io.arm()
    return io


def drive(io: SimVehicleIO, speed: float, steer: float, seconds: float, period: float = 0.05) -> list[float]:
    """Vòng ứng dụng: gửi lệnh mỗi `period` giây; trả tốc độ THẬT sau mỗi chu kỳ (chỉ để chấm)."""
    speeds = []
    for _ in range(round(seconds / period)):
        io.send(speed, steer)
        io.advance(period)
        speeds.append(io.truth.speed)
    return speeds


def codes(events) -> list[str]:
    return [e.code for e in events]


# ---- đơn vị dùng chung -------------------------------------------------------------------------------------------
def test_units_are_shared_and_out_of_range_is_rejected():
    assert speed_to_wire(0.1234) == 123 and speed_to_wire(-0.1235) == -124 and speed_to_wire(-0.0005) == -1
    assert steer_to_wire(math.radians(30)) == 524 and steer_to_wire(-math.radians(30)) == -524
    assert round_half_away(2.5) == 3 and round_half_away(-2.5) == -3
    for bad in (40.0, -33.0, math.nan, math.inf):
        with pytest.raises(ValueError):
            speed_to_wire(bad)


def test_both_branches_expose_the_same_interface():
    public = {name for name in dir(VehicleIO) if not name.startswith("_")}
    for cls in (SimVehicleIO, SerialVehicleIO):
        assert public <= set(dir(cls))
    assert {"connect", "arm", "disarm", "clear_fault", "send", "stop", "poll", "service", "latest", "events",
            "telemetry_fresh", "close"} <= public


def test_same_command_gives_identical_wire_bytes_on_both_branches(cfg):
    sent = []
    io_sim = SimVehicleIO(cfg, SimIOConfig(firmware=FAST_FW), rng=random.Random(5))
    original = io_sim._write
    io_sim._write = lambda data: (sent.append(bytes(data)), original(data))[1]
    io_sim.connect()
    io_sim.send(0.1234, -0.2, validity_s=0.15)

    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW), clock)
    io_ser = SerialVehicleIO(loop, clock=clock, rng=random.Random(5))
    io_ser.connect()
    io_ser.send(0.1234, -0.2, validity_s=0.15)

    assert sent == loop.written                                     # HELLO + COMMAND giống từng byte
    cmd = FrameParser().feed(sent[-1])[0]
    assert isinstance(cmd, Command) and (cmd.speed_mm_s, cmd.steer_mrad, cmd.validity_ms) == (123, -200, 150)


# ---- nhánh mô phỏng ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_sim_closed_loop_follows_speed_step_despite_deadzone_latency_noise(cfg, seed):
    io = armed_sim(cfg, seed=seed)
    a, s = io.config.actuator, io.config.sensors
    assert a.effort_deadzone_permille > io.config.firmware.deadzone_comp_permille    # bù vùng chết cố ý sai
    assert a.latency_ms > 0 and s.speed_latency_ms > 0 and s.speed_noise_std_mps > 0
    speeds = drive(io, 0.10, 0.0, 4.0)
    settled = speeds[40:]                                           # sau 2 s
    errors = [v - 0.10 for v in settled]
    assert abs(statistics.mean(errors)) < 0.005
    assert max(abs(e) for e in errors) < 0.02
    tel = io.latest()
    assert tel.state == State.RUNNING and tel.flags & TelemetryFlag.SPEED_LOOP_CLOSED
    assert tel.speed_mps is not None and abs(tel.speed_mps - 0.10) < 0.05   # số đo (nhiễu, trễ) vẫn gần đúng


def test_sim_open_loop_without_encoder_has_large_steady_error(cfg):
    """Đối chứng cho test trên: cùng cơ cấu chấp hành, không có phản hồi tốc độ → sai số xác lập lớn, và tốc độ xác
    lập đúng bằng giá trị mà công thức vùng chết của mô hình cơ cấu chấp hành cho."""
    io = armed_sim(cfg, sensors=SimSensorConfig(speed_available=False))
    speeds = drive(io, 0.10, 0.0, 4.0)
    fw, a = io.config.firmware, io.config.actuator
    effort = fw.deadzone_comp_permille + fw.ff_permille_per_mps * 0.10                   # 300 ‰
    expected = a.speed_at_full_effort_mps * (effort - a.effort_deadzone_permille) / (1000 - a.effort_deadzone_permille)
    assert statistics.mean(speeds[40:]) == pytest.approx(expected, abs=0.005)            # ≈ 0,141 m/s
    assert abs(statistics.mean(speeds[40:]) - 0.10) > 0.03
    assert not io.latest().flags & TelemetryFlag.SPEED_LOOP_CLOSED and io.latest().speed_mps is None


def test_sim_effort_inside_deadzone_does_not_move_car(cfg):
    io = armed_sim(cfg, sensors=SimSensorConfig(speed_available=False))
    speeds = drive(io, 0.02, 0.0, 3.0)                                 # ff = 100 + 40 = 140 ‰ < vùng chết 150 ‰
    tel = io.latest()
    assert tel.state == State.RUNNING and 0 < tel.effort * 1000 < io.config.actuator.effort_deadzone_permille
    assert all(v == 0.0 for v in speeds)


@pytest.mark.parametrize("latency_ms", [0, 30, 60])
def test_sim_actuator_latency_delays_motion_after_effort(cfg, latency_ms):
    """Vùng chết = 0 để thời điểm xe bắt đầu chạy chỉ phụ thuộc trễ cơ cấu chấp hành."""
    io = armed_sim(cfg, actuator=SimActuatorConfig(latency_ms=latency_ms, effort_deadzone_permille=0))
    tick = io.config.tick_ms
    t_effort = t_move = None
    for _ in range(100):
        io.send(0.10, 0.0)
        io.advance(tick / 1000)
        if t_effort is None and io.firmware.effort_permille != 0:
            t_effort = io.t_ms
        if t_move is None and io.truth.speed > 0:
            t_move = io.t_ms
    assert t_effort is not None and t_move is not None
    assert t_move - t_effort == latency_ms + tick


def test_sim_speed_sensor_lags_truth_by_configured_latency(cfg):
    io = armed_sim(cfg, sensors=SimSensorConfig(speed_noise_std_mps=0.0))
    lag = io.config.sensors.speed_latency_ms
    truth_at, measured = {io.t_ms: io.truth.speed}, []
    for _ in range(150):
        io.send(0.15, 0.0)
        io.advance(io.config.tick_ms / 1000)
        truth_at[io.t_ms] = io.truth.speed
        measured.append((io.t_ms, io.firmware.inputs.speed_mm_s))
    checked = [(t, m) for t, m in measured if t - lag in truth_at]
    assert len(checked) > 100
    assert all(m == round_half_away(truth_at[t - lag] * 1000) for t, m in checked)
    assert any(m != round_half_away(truth_at[t] * 1000) for t, m in checked)   # lúc tăng tốc, trễ phân biệt được


def test_sim_speed_sensor_noise_matches_configured_std(cfg):
    io = sim(cfg)
    io.connect()
    io.wait_ready()
    samples = []
    for _ in range(300):
        io.advance(io.config.tick_ms / 1000)
        assert io.truth.speed == 0.0
        samples.append(io.firmware.inputs.speed_mm_s / 1000)
    std = io.config.sensors.speed_noise_std_mps
    assert abs(statistics.mean(samples)) < 0.3 * std
    assert 0.8 * std < statistics.pstdev(samples) < 1.2 * std


def test_take_new_returns_queued_telemetry_without_advancing_io(cfg):
    """`take_new()` (tối 24/09/2026, dùng bởi `VehicleLink.refresh`): lấy khung đã nhận — kể cả khung do `service()` của
    luồng kiểu `Heartbeat` đọc — mà KHÔNG tiến đồng hồ mô phỏng hay đọc thêm; khung đã lấy không trả lại lần nữa."""
    io = sim(cfg)
    io.connect()
    io.wait_ready()
    io.poll()                                                    # xả hàng đợi tới đây
    for _ in range(40):                                          # 40 nhịp mô phỏng, chỉ service(): khung ở lại hàng đợi
        io.service()
    t = io.now()
    frames = io.take_new()
    assert frames and all(f.stamp.t <= t for f in frames) and io.now() == t
    assert io.take_new() == [] and io.now() == t                 # không tiến, không đọc thêm
    assert all(f.sequence not in {g.sequence for g in frames} for f in io.poll())


def test_sim_does_not_move_when_not_armed(cfg):
    io = sim(cfg)
    io.connect()
    io.wait_ready()
    start = io.truth
    speeds = drive(io, 0.2, 0.3, 2.0)
    assert all(v == 0.0 for v in speeds)
    assert (io.truth.pose, io.truth.steer) == (start.pose, start.steer)
    assert io.latest().state == State.DISARMED and io.latest().effort == 0.0
    assert io.stats.rejected.get("BAD_STATE", 0) >= 30
    assert codes(io.events()).count("COMMAND_REJECTED") == 1        # báo một lần, đếm mọi lần


def test_sim_stops_by_itself_when_the_app_stops_sending(cfg):
    io = armed_sim(cfg)
    drive(io, 0.15, 0.0, 2.0)
    assert io.truth.speed > 0.1
    t_last = io.now()
    stopped_at = None
    for _ in range(100):
        io.advance(0.01)
        if stopped_at is None and io.truth.speed == 0.0:
            stopped_at = io.now()
    assert stopped_at is not None and stopped_at - t_last < 0.6      # validity 0,15 s + dốc + trễ chấp hành
    x = io.truth.pose.x
    io.advance(1.0)
    assert io.truth.pose.x == x
    stops = [e for e in io.events() if e.code == "VEHICLE_STOPPED"]
    assert stops and "COMMAND_TIMEOUT" in stops[0].message


def test_sim_link_loss_stops_car_and_reconnect_requires_rearm(cfg):
    io = armed_sim(cfg)
    drive(io, 0.15, 0.1, 1.5)
    io.set_link(False)
    io.advance(1.0)
    assert "TELEMETRY_STALE" in codes(io.events()) and not io.telemetry_fresh()
    assert io.truth.speed == 0.0
    assert io.firmware.state == State.DISARMED and io.firmware.stop_reason == StopReason.LINK_TIMEOUT
    io.set_link(True)
    info = io.connect()
    assert info.state == State.DISARMED
    x = io.truth.pose.x
    speeds = drive(io, 0.15, 0.0, 1.0)
    assert all(v == 0.0 for v in speeds) and io.truth.pose.x == x   # reconnect không tự chạy tiếp
    io.arm()
    assert max(drive(io, 0.15, 0.0, 1.0)) > 0.05


def test_sim_link_gap_shorter_than_board_watchdog_still_requires_rearm(cfg):
    """Mất liên lạc dài hơn thời hạn lệnh nhưng ngắn hơn link_timeout của bo: bo chỉ về ARMED (COMMAND_TIMEOUT).
    Laptop đã báo TELEMETRY_STALE nên phải chốt: cắm lại mà ứng dụng vẫn gửi lệnh cũ thì xe KHÔNG được chạy lại."""
    io = armed_sim(cfg)
    drive(io, 0.15, 0.0, 1.5)
    assert io.truth.speed > 0.1
    io.events()
    io.set_link(False)
    for _ in range(8):                                               # 0,4 s: giữa validity 0,15 s và link_timeout 0,5 s
        try:
            io.send(0.15, 0.0)                                       # ứng dụng vẫn gửi như thường
        except VehicleIOError:
            pass
        io.advance(0.05)
    assert "TELEMETRY_STALE" in codes(io.events()) and io.rearm_required
    assert io.firmware.state == State.ARMED and io.firmware.stop_reason == StopReason.COMMAND_TIMEOUT
    io.set_link(True)                                                # cắm lại, KHÔNG connect()
    speeds = []
    for _ in range(20):                                              # 1 s
        with pytest.raises(VehicleIOError, match="arm"):
            io.send(0.15, 0.0)
        io.advance(0.05)
        speeds.append(io.truth.speed)
    assert io.connected and "TELEMETRY_RESUMED" in codes(io.events())
    assert all(b <= a for a, b in zip(speeds, speeds[1:]))         # không bao giờ tăng tốc lại
    assert io.truth.speed == 0.0 and io.firmware.state != State.RUNNING
    x = io.truth.pose.x
    for _ in range(10):
        with pytest.raises(VehicleIOError):
            io.send(0.15, 0.0)
        io.advance(0.05)
    assert io.truth.pose.x == x and io.truth.speed == 0.0
    io.stop()                                                        # enable=0 vẫn gửi được
    io.arm()                                                         # thao tác cho phép mới
    assert not io.rearm_required
    assert max(drive(io, 0.15, 0.0, 1.0)) > 0.05


def test_sim_loss_of_board_to_laptop_direction_only_stops_car(cfg):
    """Chỉ mất chiều bo → laptop: bo vẫn nhận lệnh. Laptop báo STALE, chốt, gửi DISARM → bo DISARMED ngay."""
    io = armed_sim(cfg)
    drive(io, 0.15, 0.0, 1.5)
    assert io.truth.speed > 0.1
    io.events()
    original = io.firmware.take_tx
    until = io.t_ms + 1000

    def lossy_take_tx():
        data = original()                                            # byte bị lấy khỏi bộ đệm rồi mất trên đường
        return b"" if io.t_ms < until else data

    io.firmware.take_tx = lossy_take_tx
    stale_at, trace = None, []
    for _ in range(150):                                             # 1,5 s, ứng dụng gửi mỗi 10 ms
        try:
            io.send(0.15, 0.0)
        except VehicleIOError:
            pass
        io.advance(0.01)
        if stale_at is None and "TELEMETRY_STALE" in codes(io.events()):
            stale_at = io.t_ms
        trace.append((io.t_ms, io.truth.speed))
    assert stale_at is not None and stale_at < until
    stopped = [t for t, v in trace if v == 0.0]
    assert stopped and stopped[0] - stale_at <= 600
    assert all(v == 0.0 for t, v in trace if t >= stopped[0])
    assert io.firmware.state == State.DISARMED and io.firmware.stop_reason == StopReason.HOST_DISARM
    assert io.latest().state == State.DISARMED                      # telemetry đã có lại
    with pytest.raises(VehicleIOError):
        io.send(0.15, 0.0)
    io.arm()
    assert max(drive(io, 0.15, 0.0, 1.0)) > 0.05


def test_sim_firmware_reset_is_detected_and_never_resumes(cfg):
    io = armed_sim(cfg)
    drive(io, 0.1, 0.0, 1.0)
    old_boot = io.hello.boot_id
    io.reset_firmware()
    io.advance(0.5)
    events = codes(io.events())
    # Lúc STALE laptop gửi DISARM; bo mới khởi động chưa có phiên nên trả NO_SESSION → laptop bỏ phiên.
    assert "TELEMETRY_STALE" in events and "SESSION_LOST" in events and not io.connected
    assert events.index("TELEMETRY_STALE") < events.index("SESSION_LOST")
    with pytest.raises(VehicleIOError):
        io.send(0.1, 0.0)
    with pytest.raises(VehicleIOError):
        io.stop()
    info = io.connect()
    assert info.boot_id != old_boot and "FIRMWARE_RESET" in codes(io.events())
    assert io.wait_ready() == State.DISARMED
    assert max(abs(v) for v in drive(io, 0.1, 0.0, 0.5)) == 0.0
    io.arm()
    assert max(drive(io, 0.1, 0.0, 1.0)) > 0.05


@pytest.mark.parametrize("hold_ms", [0, 400])
def test_sim_firmware_reset_hold_models_cpu_reset_that_keeps_last_pulse(cfg, hold_ms):
    """Reset CPU của ESP32-S3 (panic/watchdog/esp_restart) không dừng LEDC. hold_ms = 0: firmware có hook kéo chân
    ESC xuống thấp → cơ cấu chấp hành thôi kéo ngay, xe chỉ còn quán tính. hold_ms > 0: trường hợp xấu không có hook
    → ga cuối cùng giữ nguyên suốt khoảng đó dù bo đang BOOT."""
    io = armed_sim(cfg)
    drive(io, 0.15, 0.0, 2.0)
    effort_before = io.applied_effort_permille
    assert effort_before > 0 and io.truth.speed > 0.1
    io.reset_firmware(hold_last_output_ms=hold_ms)
    trace = []
    for _ in range(100):
        io.advance(0.01)
        trace.append((io.applied_effort_permille, io.truth.speed, io.firmware.state))
    assert all(state in (State.BOOT, State.DISARMED) for _, _, state in trace)
    held = [effort for effort, _, _ in trace[:hold_ms // 10 - 1]] if hold_ms else []
    assert held == [effort_before] * (hold_ms // 10 - 1 if hold_ms else 0)   # trong khoảng giữ: ga cũ, bo đã BOOT
    assert all(effort == 0 for effort, _, _ in trace[hold_ms // 10:])
    assert trace[-1][1] == 0.0                          # cuối cùng xe dừng (quán tính theo mô hình xe)
    moving_at_300ms = trace[29][1]
    assert (moving_at_300ms > 0.1) if hold_ms else (moving_at_300ms == 0.0)
    with pytest.raises(ValueError):
        io.reset_firmware(hold_last_output_ms=-1)


def test_sim_effort_cap_limits_speed_and_stall_faults_when_esc_deadzone_exceeds_cap(cfg):
    """Trần effort mặc định của firmware (250 ‰) trong cả chuỗi mô phỏng: lệnh 0,3 m/s nhưng xe chỉ đạt tốc độ mà cơ
    cấu chấp hành giả định cho ở 250 ‰; nếu vùng chết ESC lớn hơn trần thì xe đứng yên và bo chốt STALL (laptop
    nhận mã 5) thay vì ngồi im ở RUNNING."""
    capped = replace(FAST_FW, max_effort_permille=250)

    def armed(**overrides) -> SimVehicleIO:
        io = SimVehicleIO(cfg, SimIOConfig(firmware=capped, **overrides))
        io.connect()
        assert io.wait_ready() == State.DISARMED
        io.arm()
        return io

    for sensors in (SimSensorConfig(), SimSensorConfig(speed_available=False)):
        io = armed(sensors=sensors)
        speeds = drive(io, 0.30, 0.0, 3.0)
        a = io.config.actuator
        v_cap = a.speed_at_full_effort_mps * (250 - a.effort_deadzone_permille) / (1000 - a.effort_deadzone_permille)
        assert max(speeds) <= v_cap + 1e-9 and max(speeds) > 0.05             # ≈ 0,094 m/s, không phải 0,3
        assert io.latest().effort == pytest.approx(0.25) and io.latest().state == State.RUNNING
    io = armed(actuator=SimActuatorConfig(effort_deadzone_permille=300),
               sensors=SimSensorConfig(speed_noise_std_mps=0.0))
    speeds = drive(io, 0.30, 0.0, 2.0)
    assert all(v == 0.0 for v in speeds)
    assert io.latest().fault == Fault.STALL and io.latest().effort == 0.0
    assert "VEHICLE_FAULT" in codes(io.events())


def test_sim_estop_latches_and_requires_clear_arm_and_new_command(cfg):
    io = armed_sim(cfg)
    drive(io, 0.15, 0.0, 1.5)
    io.set_estop(True)
    io.advance(0.3)
    assert io.truth.speed == 0.0 and io.latest().fault == Fault.ESTOP and io.latest().estop_input
    assert "VEHICLE_FAULT" in codes(io.events())
    with pytest.raises(VehicleIOError) as err:
        io.clear_fault()
    assert err.value.result == Result.ESTOP_ACTIVE
    io.set_estop(False)
    io.advance(0.1)
    with pytest.raises(VehicleIOError) as err:
        io.arm()
    assert err.value.result == Result.FAULT_ACTIVE
    io.clear_fault()
    io.arm()
    io.advance(0.3)
    assert io.truth.speed == 0.0 and io.latest().state == State.ARMED
    assert max(drive(io, 0.15, 0.0, 1.0)) > 0.05


@pytest.mark.parametrize("one_way_ms", [4, 40])
def test_sim_latency_is_measured_not_assumed(cfg, one_way_ms):
    """Độ trễ là thứ đo được (ack_rtt, cmd_echo), cùng cách đo với nhánh serial; nó đổi theo cấu hình liên kết."""
    from autopark.transport.vehicle_io import SimLinkConfig
    io = armed_sim(cfg, link=SimLinkConfig(one_way_ms, one_way_ms))
    drive(io, 0.1, 0.0, 1.0)
    tick = io.config.tick_ms / 1000
    eps = 1e-9
    assert 2 * one_way_ms / 1000 - eps <= io.stats.ack_rtt_s <= 2 * one_way_ms / 1000 + 2 * tick + eps
    assert io.stats.cmd_echo_s >= one_way_ms / 1000 - eps


def test_sim_config_file_matches_defaults_and_round_trips():
    sim_cfg, vehicle = load_sim_io_config(PROJECT_ROOT / "configs" / "vehicle_io_sim.json")
    assert vehicle.name == "xe_mo_phong_giai_doan_0_gia_dinh"
    assert sim_cfg.firmware == SIM_FIRMWARE_DEFAULT                 # file khớp mặc định firmware của mô phỏng,
    assert SIM_FIRMWARE_DEFAULT == replace(FirmwareConfig(), max_effort_permille=1000)   # khác tham chiếu ở trần
    assert sim_cfg.actuator.effort_deadzone_permille == 150 and sim_cfg.sensors.speed_latency_ms == 20
    assert SimIOConfig.from_dict(sim_cfg.to_dict()) == sim_cfg
    io = SimVehicleIO.from_files(PROJECT_ROOT / "configs" / "vehicle_io_sim.json")
    io.connect()
    assert io.hello.limits.max_speed_mps == pytest.approx(0.3)


def test_sim_config_rejects_bad_values():
    with pytest.raises(ValueError):
        SimIOConfig(tick_ms=0)
    with pytest.raises(ValueError):
        SimIOConfig.from_dict({"schema_version": 2})
    with pytest.raises(ValueError):
        SimIOConfig.from_dict({"schema_version": 1, "firmware": {"no_such_key": 1}})
    with pytest.raises(ValueError):
        SimIOConfig.from_dict({"schema_version": 1, "firmware": {"tx_capacity": 2000}})   # vượt bộ đệm firmware
    with pytest.raises(ValueError):
        SimIOConfig.from_dict({"schema_version": 1, "actuator": [30]})


@pytest.mark.parametrize("section, key, value", [("actuator", "latncy_ms", 80), ("sensors", "speed_noise_std", 0.05),
                                                 ("link", "drop_prob", 0.5), ("", "tick_msec", 5),
                                                 ("sensors", "steer_noise_std_rad", 0.01)])
def test_sim_config_rejects_unknown_or_misspelled_keys(section, key, value):
    """Gõ sai tên khóa không được âm thầm rơi về giá trị mặc định giả định."""
    path = PROJECT_ROOT / "configs" / "vehicle_io_sim.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    (data[section] if section else data)[key] = value
    with pytest.raises(ValueError, match="unknown"):
        SimIOConfig.from_dict(data)
    assert load_sim_io_config(path)[0].actuator.latency_ms == 30      # file gốc vẫn nạp được


def test_sim_config_missing_keys_use_dataclass_defaults():
    assert SimIOConfig.from_dict({"schema_version": 1}) == SimIOConfig()
    # Mục firmware thiếu khóa: lấy mặc định của mô phỏng (không rơi về trần 250 ‰ của xe thật); khóa có thì giữ.
    partial = SimIOConfig.from_dict({"schema_version": 1, "firmware": {"boot_hold_ms": 200}})
    assert partial.firmware == FAST_FW
    capped = SimIOConfig.from_dict({"schema_version": 1, "firmware": {"max_effort_permille": 250}})
    assert capped.firmware == FirmwareConfig() and capped.firmware.max_effort_permille == 250
    with pytest.raises(ValueError):
        SimIOConfig.from_dict({"schema_version": 1, "firmware": [1]})


# ---- nhánh serial (cổng giả nối FirmwareModel) -------------------------------------------------------------------
def serial_bench(config: FirmwareConfig = FAST_FW, seed: int = 1):
    clock = ManualClock()
    firmware = FirmwareModel(config, boot_id=0xB007)
    loop = FirmwareSerialLoopback(firmware, clock)
    return SerialVehicleIO(loop, clock=clock, rng=random.Random(seed)), loop, clock


def test_serial_connect_arm_send_and_receive_telemetry():
    io, loop, clock = serial_bench()
    info = io.connect()
    assert info.boot_id == 0xB007 and info.limits.max_speed_mps == pytest.approx(FAST_FW.max_speed_mm_s / 1000)
    assert info.limits.link_timeout_s == pytest.approx(FAST_FW.link_timeout_ms / 1000)
    io.wait_ready()
    io.arm()
    seq = io.send(0.1, 0.2)
    for _ in range(10):
        io.poll()
    tel = io.latest()
    assert tel.state == State.RUNNING and tel.last_cmd_seq == seq and tel.speed_ref_mps > 0
    assert tel.speed_mps is None and tel.to_domain() is None         # loopback không có encoder: None, không phải 0
    assert io.telemetry_fresh() and io.stats.ack_rtt_s is not None and io.stats.cmd_echo_s is not None
    assert io.stats.stale_or_duplicate == 0 and io.stats.device_messages_missed == 0


def test_serial_ignores_duplicate_old_and_foreign_frames():
    io, loop, clock = serial_bench()
    io.connect()
    io.wait_ready()
    latest = io.latest()
    replay = TelemetryMsg(io.session_id, latest.sequence, 0, int(State.RUNNING), 0, 0, 0, 0, 0xFFFF, 0, 0, 999, 0, 0,
                          0, 0, 0, 0, (0, 0, 0, 0), 0, 0, 0)
    loop.rx += encode_frame(replay)                                  # trùng số thứ tự: bỏ
    loop.rx += encode_frame(replace(replay, sequence=(latest.sequence - 3) & 0xFFFF))   # cũ: bỏ
    loop.rx += encode_frame(replace(replay, session_id=io.session_id ^ 1, sequence=latest.sequence + 1))  # phiên khác
    loop.rx += b"\x01\x02\x03\x00"                                   # rác
    for _ in range(3):
        io.poll()
    assert io.stats.stale_or_duplicate == 2 and io.stats.foreign_session >= 1
    assert io.parser.stats.errors == 1
    assert io.latest().speed_ref_mps == 0.0 and io.latest().state == State.DISARMED


def test_serial_unplug_raises_link_error_and_reconnect_stays_disarmed():
    io, loop, clock = serial_bench()
    io.connect()
    io.wait_ready()
    io.arm()
    io.send(0.1, 0.0)
    loop.advance(50)
    assert loop.firmware.state == State.RUNNING
    io.poll()                                                        # lấy hết telemetry đã nhận
    loop.unplug()
    assert io.poll() == []                                           # lỗi cổng không ném ra khỏi poll()
    assert "LINK_ERROR" in codes(io.events()) and not io.connected
    with pytest.raises(VehicleIOError):
        io.send(0.1, 0.0)
    loop.advance(1000)                                               # bo vẫn chạy, không còn nhận gì
    assert loop.firmware.state == State.DISARMED and loop.firmware.stop_reason == StopReason.LINK_TIMEOUT
    new_loop = FirmwareSerialLoopback(loop.firmware, clock)
    new_loop.next_tick_ms = loop.next_tick_ms
    io._opener = lambda: new_loop
    io.reopen()
    info = io.connect()
    assert info.state == State.DISARMED
    io.send(0.1, 0.0)
    for _ in range(10):
        io.poll()
    assert io.latest().state == State.DISARMED and io.stats.rejected.get("BAD_STATE") == 1
    io.arm()
    io.send(0.1, 0.0)
    for _ in range(10):
        io.poll()
    assert io.latest().state == State.RUNNING


def test_reconnect_uses_new_session_so_late_frames_from_old_connection_are_rejected():
    io, loop, clock = serial_bench()
    io.connect()
    io.wait_ready()
    io.arm()
    io.send(0.1, 0.0)
    old_frame, old_session = loop.written[-1], io.session_id
    io.stop()
    io.connect()                                                     # kết nối lại: phiên mới, số thứ tự bắt đầu lại
    assert io.session_id != old_session
    io.arm()
    rejects = loop.firmware.rejects
    loop.firmware.receive(old_frame, clock.t_ms)                     # khung lệnh cũ tới muộn (bộ đệm, tiến trình cũ)
    assert loop.firmware.rejects == rejects + 1
    assert loop.firmware.state == State.ARMED and not loop.firmware.cmd_active


def test_serial_detects_silent_board_as_stale():
    io, loop, clock = serial_bench()
    io.connect()
    io.wait_ready()
    loop.firmware.step = lambda now_ms, inputs=None: None             # bo treo nhưng USB vẫn còn
    for _ in range(40):
        io.poll()
    assert "TELEMETRY_STALE" in codes(io.events()) and not io.telemetry_fresh()
    assert io.source_policy().max_age_s == io.telemetry_timeout_s


def test_heartbeat_keeps_link_alive_but_never_repeats_motion():
    io, loop, clock = serial_bench(replace(FAST_FW, link_timeout_ms=300))
    io.connect()
    io.wait_ready()
    io.arm()
    io.send(0.1, 0.0)
    hb = Heartbeat(io, period_s=0.1, idle_sleep_s=0.0005)
    hb.start()
    deadline = time.monotonic() + 10.0
    try:
        while clock.t_ms < 3000 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        hb.stop()
    assert clock.t_ms >= 3000, "heartbeat thread did not make progress"
    fw = loop.firmware
    assert fw.state == State.ARMED and fw.stop_reason == StopReason.COMMAND_TIMEOUT   # lệnh không bị lặp lại
    assert hb.pings >= 20                                            # và liên lạc được giữ (không LINK_TIMEOUT)
    assert fw.speed_ref_mm_s == 0 and fw.effort_permille == 0


def test_heartbeat_does_not_steal_telemetry_from_the_app_poll():
    """Heartbeat chỉ tiến I/O; poll() của ứng dụng (vòng 50 Hz ở đây) vẫn nhận MỌI khung, theo đúng thứ tự."""
    io, loop, clock = serial_bench()
    io.connect()
    io.wait_ready()
    io.arm()
    io.poll()
    base = io.stats.telemetry_received
    seqs = []
    hb = Heartbeat(io, period_s=0.1, idle_sleep_s=0.0005)
    hb.start()
    start_ms = clock.t_ms
    deadline = time.monotonic() + 10.0
    try:
        while clock.t_ms - start_ms < 2000 and time.monotonic() < deadline:
            io.send(0.1, 0.0)
            seqs += [t.sequence for t in io.poll()]
            time.sleep(0.02)
    finally:
        hb.stop()
    seqs += [t.sequence for t in io.poll()]
    assert clock.t_ms - start_ms >= 2000, "vòng test không tiến được"
    assert len(seqs) == io.stats.telemetry_received - base > 20
    assert all(0 < (b - a) & 0xFFFF < 0x8000 for a, b in zip(seqs, seqs[1:]))   # tăng dần, không trùng
    assert io.stats.device_messages_missed == 0 and io.stats.telemetry_unpolled_dropped == 0


def test_unpolled_telemetry_queue_is_bounded_and_counts_drops():
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW), clock)
    io = SerialVehicleIO(loop, clock=clock, rng=random.Random(1), new_telemetry_limit=5)
    io.connect()
    io.wait_ready()
    for _ in range(100):                                             # 1 s: ≈ 20 khung, không ai poll()
        io.service()
    received = io.stats.telemetry_received
    assert received > 10 and len(io._new) == 5
    assert io.stats.telemetry_unpolled_dropped == received - 5
    out = io.poll()
    assert len(out) == 5 and out[-1] is io.latest()                  # giữ 5 khung MỚI nhất
    assert io.stats.telemetry_unpolled_dropped == io.stats.telemetry_received - 5
    assert len(io._new) == 0
    with pytest.raises(ValueError):
        SerialVehicleIO(loop, clock=clock, new_telemetry_limit=0)


def test_telemetry_timeout_must_cover_three_telemetry_periods():
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW), clock)
    with pytest.raises(ValueError, match="3 lần"):
        SerialVehicleIO(loop, clock=clock, telemetry_period_ms=500)  # 0,3 s < 3 × 500 ms
    with pytest.raises(ValueError):
        SerialVehicleIO(loop, clock=clock, telemetry_period_ms=101)
    with pytest.raises(ValueError):
        SerialVehicleIO(loop, clock=clock, telemetry_period_ms=70000)
    SerialVehicleIO(loop, clock=clock, telemetry_period_ms=100)       # 3 × 100 ms = 0,3 s: đúng biên, không lỗi số thực


@pytest.mark.parametrize("period_ms, timeout_s", [(500, 1.5), (100, 0.3), (50, 0.3)])
def test_healthy_link_never_reports_stale_with_consistent_period(period_ms, timeout_s):
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW), clock)
    io = SerialVehicleIO(loop, clock=clock, rng=random.Random(3), telemetry_period_ms=period_ms,
                         telemetry_timeout_s=timeout_s)
    assert io.connect().telemetry_period_s == pytest.approx(period_ms / 1000)
    io.wait_ready()
    start = clock.t_ms
    while clock.t_ms - start < 5000:
        io.poll()
        if clock.t_ms - io.last_tx_time * 1000 >= 100:
            io.ping()
    events = codes(io.events())
    assert "TELEMETRY_STALE" not in events and not io.rearm_required
    assert io.telemetry_fresh()


def test_connect_refuses_board_period_longer_than_stale_threshold():
    """Laptop xin 0 (= mặc định của bo) nhưng bo mặc định 200 ms: 3 × 200 ms > 0,3 s → không nhận phiên."""
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(replace(FAST_FW, default_telemetry_period_ms=200)), clock)
    io = SerialVehicleIO(loop, clock=clock, rng=random.Random(2))
    with pytest.raises(VehicleIOError, match="200 ms"):
        io.connect()
    assert not io.connected
    with pytest.raises(VehicleIOError):
        io.send(0.1, 0.0)
    ok = SerialVehicleIO(loop, clock=clock, rng=random.Random(2), telemetry_timeout_s=0.6)
    assert ok.connect().telemetry_period_s == pytest.approx(0.2) and ok.connected


# ---- cổng kiểu socket:// (bo ảo QEMU; thêm 30/09/2026, docs/MO_PHONG_FIRMWARE.md) ---------------------------------
class SocketLikePort:
    """Như `socket://` của pyserial 3.5: `in_waiting` chỉ báo 0 hoặc 1 (select), `read(n)` chờ tới `timeout` cho đủ n
    byte. Đầu kia là `FirmwareSerialLoopback`. `waiting_reads`: số lần `read(n)` với n lớn hơn số byte đang có (pyserial
    sẽ chờ ở đó). `fail_after`: số byte đã giao, quá thì `in_waiting` ném OSError (rút cáp)."""

    def __init__(self, inner: FirmwareSerialLoopback):
        self.inner = inner
        self.fail_after: int | None = None
        self.delivered = 0
        self.waiting_reads = 0

    @property
    def in_waiting(self) -> int:
        if self.fail_after is not None and self.delivered >= self.fail_after:
            raise OSError("connection reset (test)")
        return min(1, self.inner.in_waiting)

    def read(self, n: int = 1) -> bytes:
        if n > len(self.inner.rx):
            self.waiting_reads += 1
        out = self.inner.read(n)
        self.delivered += len(out)
        return out

    def write(self, data: bytes) -> int:
        return self.inner.write(data)

    def close(self) -> None:
        self.inner.close()


def test_serial_pump_drains_port_that_reports_in_waiting_as_one():
    """Trước 30/09/2026 mỗi `_pump` đọc đúng `in_waiting` = 1 byte: vòng 50 Hz `poll(block=False)` tụt lại xa sau bo."""
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW, boot_id=0xB007), clock)
    port = SocketLikePort(loop)
    io = SerialVehicleIO(port, clock=clock, rng=random.Random(4))
    io.connect()
    io.wait_ready()
    io.arm()
    io.poll()
    base, waiting0 = io.stats.telemetry_received, port.waiting_reads
    lags = []
    for _ in range(100):                                             # 2 s, nhịp 20 ms như vòng giao diện
        loop.advance(20)
        for tel in io.poll(block=False):
            lags.append(clock.t_ms - tel.device_time_ms)
        io.send(0.1, 0.0)
    assert io.stats.telemetry_received - base >= 38                  # 20 Hz trong 2 s
    assert max(lags) <= 20                                           # không dồn: khung đến ngay trong nhịp của nó
    assert port.waiting_reads == waiting0                            # và không lần đọc nào phải chờ
    assert "TELEMETRY_STALE" not in codes(io.events())


def test_serial_pump_keeps_bytes_read_before_a_port_error():
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW, boot_id=0xB007), clock)
    port = SocketLikePort(loop)
    io = SerialVehicleIO(port, clock=clock, rng=random.Random(4))
    io.connect()
    io.wait_ready()
    io.poll()
    loop.advance(50)                                                 # đúng một khung telemetry đang chờ
    assert loop.rx
    port.fail_after = port.delivered + len(loop.rx)                  # đọc hết khung đó rồi cổng mới lỗi
    before = io.stats.telemetry_received
    got = io.poll(block=False)
    assert len(got) == 1 and io.stats.telemetry_received == before + 1
    assert "LINK_ERROR" in codes(io.events()) and io.transport is None and not io.connected


class EndlessSlowPort:
    """Cổng luôn còn byte (`in_waiting` 1) và đọc mỗi byte mất 1 ms: bên kia gửi nhanh hơn tốc độ đọc từng byte."""

    def __init__(self):
        self.reads = 0

    @property
    def in_waiting(self) -> int:
        return 1

    def read(self, n: int = 1) -> bytes:
        self.reads += 1
        time.sleep(0.001)
        return b"\x00"

    def write(self, data: bytes) -> int:
        return len(data)

    def close(self) -> None:
        pass


def test_serial_pump_is_bounded_in_time_on_an_endless_stream():
    io = SerialVehicleIO(EndlessSlowPort(), rng=random.Random(4))
    t0 = time.perf_counter()
    io.poll(block=False)
    elapsed = time.perf_counter() - t0
    assert io.transport.reads >= 2                                   # có đọc cạn (không dừng sau một byte)
    assert elapsed < PUMP_MAX_S + 0.1                                # nhưng không giữ vòng giao diện quá lâu


def test_serial_open_picks_the_transport_from_the_port_name(monkeypatch):
    serial = pytest.importorskip("serial")
    from autopark.transport import socket_port

    calls = []

    class Dummy:
        def close(self):
            pass

    monkeypatch.setattr(socket_port.SocketPort, "from_url",
                        classmethod(lambda cls, url, **kw: calls.append(("tcp", url, (), kw)) or Dummy()))
    monkeypatch.setattr(serial, "serial_for_url", lambda url, *a, **kw: calls.append(("url", url, a, kw)) or Dummy())
    monkeypatch.setattr(serial, "Serial", lambda port, *a, **kw: calls.append(("com", port, a, kw)) or Dummy())
    SerialVehicleIO.open("socket://127.0.0.1:5555")
    SerialVehicleIO.open("RFC2217://127.0.0.1:2217")
    SerialVehicleIO.open("COM7")
    assert [(c[0], c[1]) for c in calls] == [("tcp", "socket://127.0.0.1:5555"), ("url", "RFC2217://127.0.0.1:2217"),
                                            ("com", "COM7")]
    assert [c[3]["write_timeout"] for c in calls] == [0.05, None, 0.05]   # rfc2217 của pyserial không nhận nó
    assert all(c[3]["timeout"] == 0.01 for c in calls) and calls[1][2] == calls[2][2] == (115200,)


# ---- SocketPort: cổng TCP của dự án (thay socket:// của pyserial) --------------------------------------------------
def tcp_pair():
    server = socket.create_server(("127.0.0.1", 0))
    port = SocketPort("127.0.0.1", server.getsockname()[1], timeout=0.05)
    peer, _ = server.accept()
    server.close()
    return port, peer


def test_socket_port_reports_real_in_waiting_and_does_not_wait_when_bytes_are_buffered():
    data = bytes(range(256)) * 3
    port, peer = tcp_pair()
    try:
        peer.sendall(data)
        deadline = time.perf_counter() + 2.0
        while port.in_waiting < len(data) and time.perf_counter() < deadline:
            time.sleep(0.001)
        assert port.in_waiting == len(data)                          # số byte thật, không phải 0/1 như pyserial
        t0 = time.perf_counter()
        assert port.read(700) == data[:700]
        assert port.read(1000) == data[700:]                         # có bao nhiêu trả bấy nhiêu, không chờ đủ 1000
        assert time.perf_counter() - t0 < 0.03
        t0 = time.perf_counter()
        assert port.read(1) == b""                                   # rỗng: chờ tới timeout (0,05 s) rồi trả rỗng
        assert 0.03 <= time.perf_counter() - t0 < 1.0
        assert port.write(b"\x00hello") == 6 and peer.recv(16) == b"\x00hello"
    finally:
        port.close()
        peer.close()


def test_socket_port_peer_close_and_closed_port_are_oserrors():
    port, peer = tcp_pair()
    peer.close()
    with pytest.raises(OSError):
        deadline = time.perf_counter() + 2.0
        while time.perf_counter() < deadline:
            port.in_waiting
            time.sleep(0.005)
    port.close()
    with pytest.raises(OSError):
        port.write(b"x")
    with pytest.raises(ValueError):
        SocketPort.from_url("socket://127.0.0.1")                    # thiếu cổng


class TcpFirmware(threading.Thread):
    """`FirmwareModel` sau một cổng TCP THẬT trên 127.0.0.1, nhịp 10 ms theo đồng hồ tường: như bo ảo QEMU, nhưng
    không cần QEMU. Laptop mở nó bằng `socket://` (SocketPort)."""

    def __init__(self, firmware: FirmwareModel):
        super().__init__(daemon=True)
        self.firmware = firmware
        self.server = socket.create_server(("127.0.0.1", 0))
        self.server.settimeout(5.0)
        self.url = f"socket://127.0.0.1:{self.server.getsockname()[1]}"
        self.done = threading.Event()

    def run(self) -> None:
        try:
            conn, _ = self.server.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(0.001)
            t0 = time.perf_counter()
            next_tick = 10
            while not self.done.is_set():
                now_ms = int((time.perf_counter() - t0) * 1000)
                try:
                    data = conn.recv(4096)
                except TimeoutError:
                    data = None
                except OSError:
                    return                  # laptop đóng kết nối (Windows: ConnectionResetError, WinError 10054)
                if data == b"":
                    return
                if data:
                    self.firmware.receive(data, now_ms)
                while next_tick <= now_ms:
                    self.firmware.step(next_tick, FirmwareInputs())
                    next_tick += 10
                out = self.firmware.take_tx()
                if out:
                    try:
                        conn.sendall(out)
                    except OSError:
                        return

    def stop(self) -> None:
        self.done.set()
        self.server.close()
        self.join(timeout=2.0)


def test_serial_over_a_real_socket_url_keeps_up_with_20hz_telemetry():
    """Thời gian thực (~1,5 s): `SerialVehicleIO.open("socket://…")` (SocketPort) với vòng 50 Hz `poll(block=False)`.
    Ngưỡng mất liên lạc 2 s để máy bận không làm hỏng test; thứ đang kiểm là số khung và thứ tự của chúng."""
    board = TcpFirmware(FirmwareModel(FAST_FW, boot_id=0xB007))
    board.start()
    io = SerialVehicleIO.open(board.url, telemetry_timeout_s=2.0)
    try:
        assert isinstance(io.transport, SocketPort)
        io.connect()
        io.wait_ready()
        io.arm()
        io.poll()
        got = []
        end = time.perf_counter() + 1.0
        while time.perf_counter() < end:
            got += io.poll(block=False)
            io.send(0.1, 0.0)
            time.sleep(0.02)
        assert len(got) >= 17                                        # 20 Hz trong 1 s
        assert "TELEMETRY_STALE" not in codes(io.events())
        assert all(0 < (b.sequence - a.sequence) & 0xFFFF < 0x8000 for a, b in zip(got, got[1:]))
    finally:
        io.close()
        board.stop()


# ---- chuyển đổi telemetry ----------------------------------------------------------------------------------------
def test_telemetry_conversion_keeps_invalid_values_as_none():
    msg = TelemetryMsg(1, 5, 1234, int(State.RUNNING), 0, 0, int(TelemetryFlag.STEER_VALID | TelemetryFlag.LINK_OK),
                       4, 30, 77, -100, 150, 50, 400, 11, 22, 33, 0b0010, (0, 250, 0, 0), 0, 0, 0)
    tel = VehicleTelemetry.from_message(msg, 2.5, "esp32_vehicle")
    assert tel.speed_mps is None and tel.steer_rad == pytest.approx(-0.1)
    assert tel.tof_m == (None, 0.25, None, None) and tel.imu is None and tel.supply_v is None
    assert tel.cmd_age_s == pytest.approx(0.03) and tel.effort == pytest.approx(0.4) and tel.link_ok
    assert tel.to_domain() is None and tel.stamp.t == 2.5
    full = VehicleTelemetry.from_message(replace(msg, flags=int(TelemetryFlag.SPEED_VALID | TelemetryFlag.STEER_VALID)),
                                         3.0, "x")
    domain = full.to_domain()
    assert domain.speed_mps == pytest.approx(0.077) and domain.steer_rad == pytest.approx(-0.1)
    with pytest.raises(ValueError):
        VehicleTelemetry.from_message(replace(msg, state=9), 0.0, "x")


def test_unknown_codes_are_counted_not_crashing():
    io, loop, clock = serial_bench()
    io.connect()
    io.wait_ready()
    seq = io.latest().sequence
    bad = TelemetryMsg(io.session_id, (seq + 1) & 0xFFFF, 0, 42, 0, 0, 0, 0, 0xFFFF, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                       (0, 0, 0, 0), 0, 0, 0)
    loop.rx += encode_frame(bad)
    io.poll()
    assert io.stats.bad_values == 1
    parser = FrameParser(accept_types=DEVICE_TO_HOST)
    assert parser.feed(encode_frame(bad)) == [bad]                  # hợp lệ về khung, sai về nghĩa


# ---- giới hạn HELLO_ACK so với VehicleConfig (thêm 24/09/2026; chỉ FirmwareModel, không bo thật) -----------------
from autopark.transport.vehicle_io import VehicleLimits, compare_limits  # noqa: E402


def board_limits(**overrides_si) -> VehicleLimits:
    """Giới hạn đúng như FirmwareConfig mặc định báo (khớp conftest `cfg`), đè một số trường (đơn vị SI)."""
    base = dict(max_speed_mps=0.300, max_steer_rad=0.524, max_steer_rate_rad_s=1.571, max_accel_mps2=0.300,
                max_decel_mps2=0.600, stop_decel_mps2=0.600, max_validity_s=0.3, link_timeout_s=0.5)
    base.update(overrides_si)
    return VehicleLimits(**base)


def test_compare_limits_tolerates_wire_rounding_only(cfg):
    # 30° = 523,6 mrad → 524 và 90°/s = 1570,8 → 1571 trên dây: lệch < 1 đơn vị, không phải mismatch.
    check = compare_limits(board_limits(), cfg)
    assert check.ok and not check.risky and len(check.compared) == 6
    assert "khớp" in check.describe()
    assert compare_limits(board_limits(max_speed_mps=0.301), cfg).ok          # đúng 1 mm/s
    assert compare_limits(board_limits(max_steer_rad=0.5245), cfg).ok          # 0,9 mrad so với 523,6
    for name, value in (("max_speed_mps", 0.302), ("max_steer_rad", 0.5255), ("max_accel_mps2", 0.2985)):
        check = compare_limits(board_limits(**{name: value}), cfg)
        assert [m.name for m in check.mismatches] == [name], name


@pytest.mark.parametrize("field_name, value, risky", [
    ("max_speed_mps", 0.40, True),            # bo cho phép nhanh hơn planner
    ("max_speed_mps", 0.25, False),           # bo kẹp chặt hơn
    ("max_steer_rad", 0.60, True),            # bo cho lái gắt hơn
    ("max_steer_rad", 0.40, True),            # đường đã lập cần góc lái bo không cho
    ("max_steer_rate_rad_s", 2.0, True),
    ("max_steer_rate_rad_s", 1.0, False),
    ("max_accel_mps2", 0.5, True),
    ("max_accel_mps2", 0.2, False),
    ("max_decel_mps2", 0.4, True),            # bo phanh yếu hơn hồ sơ tốc độ
    ("max_decel_mps2", 0.9, False),
    ("stop_decel_mps2", 0.4, True),           # dốc dừng yếu hơn max_decel của cấu hình
    ("stop_decel_mps2", 0.9, False),
])
def test_compare_limits_classifies_the_dangerous_direction(cfg, field_name, value, risky):
    check = compare_limits(board_limits(**{field_name: value}), cfg)
    assert len(check.mismatches) == 1
    mismatch = check.mismatches[0]
    assert mismatch.name == field_name and mismatch.risky is risky and mismatch.board == pytest.approx(value)
    assert bool(check.risky) is risky
    assert ("NGUY HIỂM" in check.describe()) is risky


def test_check_limits_after_connect_emits_limits_mismatch_event(cfg):
    io, loop, clock = serial_bench()
    with pytest.raises(VehicleIOError):
        io.check_limits(cfg)                                     # chưa có HELLO_ACK
    io.connect()
    assert io.check_limits(cfg).ok and codes(io.events()) == [] and io.limits_check.ok
    frames_before = len(loop.written)
    for fw_speed, action in ((400, "STOP"), (250, "LOG")):
        io, loop, clock = serial_bench(replace(FAST_FW, max_speed_mm_s=fw_speed))
        io.connect()
        check = io.check_limits(cfg)
        events = io.events()
        assert codes(events) == ["LIMITS_MISMATCH"] and events[0].action == action
        assert "tốc độ lớn nhất" in events[0].message and f"bo {fw_speed:.1f} mm/s" in events[0].message
        assert io.limits_check is check and bool(check.risky) is (action == "STOP")
        assert io.check_limits(cfg, emit_event=False) == check and io.events() == []
        io.connect()                                             # phiên mới: kết quả cũ bị xóa
        assert io.limits_check is None
    assert frames_before == 1                                    # so giới hạn không gửi gì (chỉ có HELLO)


def test_deferred_serial_io_does_not_open_the_port_until_reopen(monkeypatch):
    import serial
    opened = []

    def fake_serial(port, baudrate, timeout, write_timeout):
        opened.append((port, baudrate, timeout, write_timeout))
        return FirmwareSerialLoopback(FirmwareModel(FAST_FW), ManualClock())

    monkeypatch.setattr(serial, "Serial", fake_serial)
    io = SerialVehicleIO.deferred("COM99")
    assert opened == [] and io.transport is None and io.port == "COM99" and not io.connected
    with pytest.raises(VehicleIOError, match="Cổng chưa mở"):
        io.connect()
    assert opened == []
    io.close()                                                   # đóng khi chưa mở: không lỗi
    io.reopen()
    assert opened == [("COM99", 115200, 0.01, 0.05)] and io.transport is not None
    io.close()
    assert SerialVehicleIO.open("COM98").port == "COM98" and opened[-1][0] == "COM98"
