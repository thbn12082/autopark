"""Bản tham chiếu firmware: máy trạng thái, phiên/số thứ tự, watchdog, giới hạn, dốc về trung tính, chốt lỗi,
vòng tốc độ, telemetry — và chạy lại các kịch bản trong vector mẫu dùng chung với firmware C++."""
from dataclasses import replace
import json

import pytest

from autopark.transport.firmware_model import (TX_BUFFER_SIZE, FirmwareConfig, FirmwareInputs, FirmwareModel,
                                               elapsed_ms, tdiv)
from autopark.transport.protocol import (DEVICE_TO_HOST, Ack, Action, Command, Fault, FaultMsg, FrameParser, Hello,
                                         HelloAck, Request, ResetReason, Result, State, StopReason, TelemetryFlag,
                                         TelemetryMsg, encode_frame)
from autopark.transport.vectors import DEFAULT_PATH

SESSION = 0x12345678
OTHER = 0x0BADF00D
CFG = FirmwareConfig(boot_hold_ms=100, link_timeout_ms=300, max_validity_ms=200, default_telemetry_period_ms=50,
                     direction_change_hold_ms=100)


class Bench:
    """Laptop giả nói chuyện trực tiếp với FirmwareModel bằng byte thật."""

    def __init__(self, config: FirmwareConfig = CFG, now: int = 0, **kwargs):
        self.fw = FirmwareModel(config, now_ms=now, boot_id=0xCAFE0001, **kwargs)
        self.cfg = config
        self.t = now & 0xFFFFFFFF
        self.session = SESSION
        self.seq = 0
        self.parser = FrameParser(accept_types=DEVICE_TO_HOST)
        self.inputs = FirmwareInputs()
        self.log: list = []

    def _rx(self) -> list:
        msgs = self.parser.feed(self.fw.take_tx())
        self.log += msgs
        return msgs

    def deliver(self, msg) -> list:
        self.fw.receive(encode_frame(msg), self.t)
        return self._rx()

    def next_seq(self) -> int:
        self.seq = (self.seq + 1) & 0xFFFF
        return self.seq

    def hello(self, session: int | None = None, seq: int | None = None, period: int = 0) -> HelloAck:
        if session is not None:
            self.session = session
        self.seq = self.seq if seq is None else seq
        msgs = self.deliver(Hello(self.session, self.seq, period, 0))
        acks = [m for m in msgs if isinstance(m, HelloAck)]
        assert len(acks) == 1, msgs
        return acks[0]

    def request(self, action: int, **kw) -> Ack:
        msg = Request(kw.get("session", self.session), kw.get("seq", self.next_seq()), int(action))
        acks = [m for m in self.deliver(msg) if isinstance(m, Ack)]
        assert len(acks) == 1
        return acks[0]

    def command(self, speed: int, steer: int = 0, *, enable: bool = True, validity: int = 150, flags: int | None = None,
                seq: int | None = None, session: int | None = None) -> Result:
        flags = (1 if enable else 0) if flags is None else flags
        msg = Command(self.session if session is None else session, self.next_seq() if seq is None else seq,
                      validity, flags, speed, steer)
        acks = [m for m in self.deliver(msg) if isinstance(m, Ack)]
        return Result.OK if not acks else Result(acks[0].result)

    def tick(self, ms: int = 10, inputs: FirmwareInputs | None = None):
        self.t = (self.t + ms) & 0xFFFFFFFF
        if inputs is not None:
            self.inputs = inputs
        out = self.fw.step(self.t, self.inputs)
        self._rx()
        return out

    def run(self, ms: int, inputs: FirmwareInputs | None = None) -> list:
        return [self.tick(10, inputs) for _ in range(ms // 10)]

    def armed(self) -> "Bench":
        self.hello()
        self.run(self.cfg.boot_hold_ms)
        assert self.request(Action.ARM).result == Result.OK
        return self

    def telemetry(self) -> list[TelemetryMsg]:
        return [m for m in self.log if isinstance(m, TelemetryMsg)]


# ---- khởi động và phiên -----------------------------------------------------------------------------------------
def test_boot_is_neutral_silent_without_session_then_disarmed():
    b = Bench()
    outs = b.run(90)
    assert all(o.state == State.BOOT and o.effort_permille == 0 and o.speed_ref_mm_s == 0 for o in outs)
    assert b.log == []                                  # không phiên → không gửi gì
    assert b.tick().state == State.DISARMED             # hết boot_hold 100 ms
    assert b.fw.stop_reason == StopReason.BOOT
    b.run(200)
    assert b.log == []


def test_hello_ack_reports_identity_limits_and_starts_telemetry():
    b = Bench(reset_reason=ResetReason.BROWNOUT)
    ack = b.hello(seq=77, period=5)                     # 5 ms < min → kẹp lên min
    assert (ack.session_id, ack.hello_sequence, ack.boot_id) == (SESSION, 77, 0xCAFE0001)
    assert ack.reset_reason == ResetReason.BROWNOUT and ack.state == State.BOOT
    assert ack.telemetry_period_ms == CFG.min_telemetry_period_ms
    assert ack.limits == CFG.limits()
    b.run(200)
    tel = b.telemetry()
    assert len(tel) == 10                               # 200 ms / 20 ms
    assert [m.sequence for m in b.log] == list(range(len(b.log)))    # một bộ đếm cho mọi khung của bo
    assert all(m.session_id == SESSION for m in b.log)
    assert tel[-1].cmd_age_ms == 0xFFFF and tel[-1].state == State.DISARMED


@pytest.mark.parametrize("period", [20, 25, 33, 50, 55])
def test_telemetry_average_period_equals_hello_ack_even_if_not_multiple_of_tick(period):
    """HELLO_ACK báo chu kỳ bo dùng; bo chỉ gửi ở biên chu kỳ điều khiển 10 ms nên từng khoảng cách là bội của
    10 ms, nhưng trung bình phải đúng giá trị đã báo (FreshnessMonitor dùng nó để đếm khung mất)."""
    b = Bench()
    ack = b.hello(period=period)
    assert ack.telemetry_period_ms == period
    b.run(2000)
    times = [m.sample_time_ms for m in b.telemetry()]
    gaps = [t1 - t0 for t0, t1 in zip(times, times[1:])]
    assert len(gaps) > 30
    assert abs(sum(gaps) / len(gaps) - ack.telemetry_period_ms) <= 1.0
    assert max(gaps) <= ack.telemetry_period_ms + 10 and min(gaps) >= 10
    assert all(g % 10 == 0 for g in gaps)


def test_late_control_tick_sends_one_telemetry_and_resyncs():
    b = Bench()
    b.hello(period=25)
    b.run(100)
    n = len(b.telemetry())
    b.tick(90)                                          # vòng điều khiển trễ (chưa quá max_tick_gap 100 ms)
    assert len(b.telemetry()) == n + 1                  # tối đa một mẫu mỗi step, không gửi dồn
    b.run(200)
    times = [m.sample_time_ms for m in b.telemetry()[n:]]
    gaps = [t1 - t0 for t0, t1 in zip(times, times[1:])]
    assert gaps[0] == 30 and max(gaps[1:]) <= 30        # bắt nhịp lại từ lúc trễ, không bù bằng loạt khung sát nhau


def test_hello_with_session_zero_is_rejected():
    b = Bench()
    acks = [m for m in b.deliver(Hello(0, 0)) if isinstance(m, Ack)]
    assert acks[0].result == Result.BAD_FIELD and b.fw.session_id == 0


def test_messages_before_hello_get_no_session():
    b = Bench()
    b.run(150)
    assert b.command(100, seq=1) == Result.NO_SESSION
    assert b.request(Action.ARM, seq=2).result == Result.NO_SESSION
    assert b.fw.state == State.DISARMED


# ---- ARM / enable -----------------------------------------------------------------------------------------------
def test_command_needs_arm_and_is_not_remembered_across_arm():
    b = Bench()
    b.hello()
    assert b.request(Action.ARM).result == Result.NOT_READY          # còn BOOT
    b.run(100)
    assert b.command(150, 200) == Result.BAD_STATE                    # DISARMED
    assert b.request(Action.ARM).result == Result.OK
    outs = b.run(150)
    assert all(o.state == State.ARMED and o.effort_permille == 0 and o.speed_ref_mm_s == 0 for o in outs)
    assert b.command(150, 200) == Result.OK
    assert b.tick().state == State.RUNNING and b.fw.speed_ref_mm_s > 0


def test_disarm_while_running_disarms_and_ramps_to_neutral():
    cfg = replace(CFG, max_accel_mm_s2=3000)
    b = Bench(cfg).armed()
    for _ in range(4):
        b.command(200, 300)
        b.run(50)
    assert b.fw.state == State.RUNNING and b.fw.speed_ref_mm_s == 200 and b.fw.steer_ref_mrad == 300
    ack = b.request(Action.DISARM)
    assert ack.result == Result.OK and ack.state == State.DISARMED
    assert b.fw.stop_reason == StopReason.HOST_DISARM and not b.fw.cmd_active
    outs = b.run(800)
    assert all(o.state == State.DISARMED for o in outs)
    speeds = [200] + [o.speed_ref_mm_s for o in outs]
    step = cfg.stop_decel_mm_s2 * 10 // 1000
    assert all(a - b_ == min(step, a) for a, b_ in zip(speeds, speeds[1:]) if a > 0)   # dốc stop_decel, không cắt
    zero_at = next(i for i, o in enumerate(outs) if o.speed_ref_mm_s == 0)
    assert zero_at > 10 and all(o.steer_ref_mrad == 300 for o in outs[:zero_at])      # giữ lái tới khi dừng
    assert outs[-1].steer_ref_mrad == 0 and outs[-1].effort_permille == 0
    assert b.command(200, 300) == Result.BAD_STATE                    # lệnh sau DISARM không được nhớ
    assert b.request(Action.ARM).result == Result.OK
    assert all(o.state == State.ARMED and o.speed_ref_mm_s == 0 for o in b.run(100))   # ARM không tự chạy


@pytest.mark.parametrize("action", ["disarm", "hello"])
def test_disarm_or_new_hello_never_shortens_boot_or_clears_fault(action):
    b = Bench()
    b.hello()
    b.run(50)                                                         # còn BOOT (boot_hold 100 ms)
    if action == "disarm":
        ack = b.request(Action.DISARM)
        assert ack.result == Result.OK and ack.state == State.BOOT
    else:
        assert b.hello(session=OTHER, seq=500).state == State.BOOT
    assert b.fw.state == State.BOOT and b.fw.stop_reason == StopReason.BOOT
    assert all(o.state == State.BOOT for o in b.run(40))              # t = 90: vẫn BOOT
    assert b.tick().state == State.DISARMED and b.t == CFG.boot_hold_ms
    assert b.request(Action.ARM).result == Result.OK
    b.command(100, 0)
    b.run(30)
    b.tick(inputs=FirmwareInputs(estop=True))
    b.tick(inputs=FirmwareInputs())                                   # nhả nút: lỗi vẫn chốt
    assert b.fw.state == State.FAULT
    if action == "disarm":
        ack = b.request(Action.DISARM)
        assert ack.result == Result.OK and ack.state == State.FAULT and ack.fault == Fault.ESTOP
    else:
        assert b.hello(session=SESSION, seq=900).state == State.FAULT
    outs = b.run(200)
    assert all(o.state == State.FAULT and o.effort_permille == 0 and o.speed_ref_mm_s == 0 for o in outs)
    assert b.fw.fault == Fault.ESTOP and b.fw.stop_reason == StopReason.FAULT
    assert b.telemetry()[-1].fault == Fault.ESTOP
    assert b.request(Action.ARM).result == Result.FAULT_ACTIVE
    assert b.command(100, 0) == Result.FAULT_ACTIVE
    assert b.request(Action.CLEAR_FAULT).result == Result.OK and b.fw.state == State.DISARMED


def test_enable_zero_returns_to_armed_and_ramps_down():
    b = Bench().armed()
    for _ in range(10):
        b.command(200, 0)
        b.run(20)
    before = b.fw.speed_ref_mm_s
    assert b.command(0, 0, enable=False) == Result.OK
    out = b.tick()
    assert out.state == State.ARMED and b.fw.stop_reason == StopReason.ENABLE_CLEARED
    assert out.speed_ref_mm_s == before - CFG.stop_decel_mm_s2 * 10 // 1000


# ---- số thứ tự ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("start", [0, 100, 32767, 65530, 65535])
def test_sequence_duplicate_old_and_wraparound(start):
    b = Bench()
    b.hello(seq=start)
    b.run(100)
    assert b.request(Action.ARM).result == Result.OK                  # start+1
    for _ in range(8):                                                # đi qua 65535 → 0 khi start gần cuối
        assert b.request(Action.PING).result == Result.OK
    last = b.seq
    assert b.request(Action.PING, seq=last).result == Result.DUPLICATE
    assert b.request(Action.PING, seq=(last - 1) & 0xFFFF).result == Result.OUT_OF_ORDER
    assert b.request(Action.PING, seq=(last - 0x7FFF) & 0xFFFF).result == Result.OUT_OF_ORDER
    assert b.request(Action.PING, seq=(last + 5) & 0xFFFF).result == Result.OK   # khoảng hở (mất gói) được chấp nhận
    assert b.fw.rejects == 3


def test_stale_command_after_newer_one_does_not_change_target():
    b = Bench().armed()
    assert b.command(100, 0, seq=10) == Result.OK
    assert b.command(250, 0, seq=9) == Result.OUT_OF_ORDER
    assert b.fw.cmd_speed_mm_s == 100 and b.fw.last_cmd_seq == 10


def test_new_session_disarms_and_rejects_old_session():
    b = Bench().armed()
    b.command(150, 100)
    b.run(50)
    assert b.fw.state == State.RUNNING
    ack = b.hello(session=OTHER, seq=1000)
    assert ack.state == State.DISARMED and b.fw.stop_reason == StopReason.NEW_SESSION
    assert b.command(150, 100, session=SESSION, seq=1001) == Result.WRONG_SESSION
    assert b.command(150, 100) == Result.BAD_STATE                    # phiên mới phải ARM lại
    outs = b.run(300)
    assert outs[-1].speed_ref_mm_s == 0 and all(o.state == State.DISARMED for o in outs)


# ---- hết hạn lệnh, watchdog, reconnect -------------------------------------------------------------------------
def test_command_timeout_ramps_to_neutral_then_centres_steering():
    cfg = replace(CFG, max_accel_mm_s2=3000)
    b = Bench(cfg).armed()
    for _ in range(4):
        b.command(200, 300)
        b.run(50)
    assert b.fw.speed_ref_mm_s == 200 and b.fw.steer_ref_mrad == 300
    outs = b.run(150)                                                 # lệnh cuối 150 ms → hết hạn
    timeout = next(i for i, o in enumerate(outs) if o.state == State.ARMED)
    assert b.fw.stop_reason == StopReason.COMMAND_TIMEOUT
    tail = outs[timeout:] + b.run(600)
    speeds = [o.speed_ref_mm_s for o in tail]
    steps = [a - b_ for a, b_ in zip(speeds, speeds[1:]) if a > 0]
    assert steps and all(s == cfg.stop_decel_mm_s2 * 10 // 1000 for s in steps[:-1])  # dốc đúng stop_decel
    zero_at = speeds.index(0)
    assert all(o.steer_ref_mrad == 300 for o in tail[:zero_at])      # đang giảm tốc: giữ góc lái
    assert tail[-1].steer_ref_mrad == 0 and tail[-1].effort_permille == 0


def test_link_watchdog_disarms_after_silence_and_ping_keeps_link_but_not_motion():
    b = Bench().armed()
    b.command(100, 0)
    for _ in range(10):                                               # chỉ PING: liên lạc còn, lệnh hết hạn
        b.run(100)
        assert b.request(Action.PING).result == Result.OK
    assert b.fw.state == State.ARMED and b.fw.stop_reason == StopReason.COMMAND_TIMEOUT
    assert b.fw.speed_ref_mm_s == 0
    silent_from = b.t
    outs = b.run(400)
    first = next(i for i, o in enumerate(outs) if o.state == State.DISARMED)
    assert (first + 1) * 10 == CFG.link_timeout_ms and b.t - silent_from == 400
    assert b.fw.stop_reason == StopReason.LINK_TIMEOUT
    assert not b.telemetry()[-1].flags & TelemetryFlag.LINK_OK


def test_reconnect_after_link_loss_does_not_resume_motion():
    b = Bench().armed()
    for _ in range(5):
        b.command(150, 200)
        b.run(50)
    b.run(600)                                                        # mất liên lạc
    assert b.fw.state == State.DISARMED
    b.hello(session=OTHER, seq=0)                                     # kết nối lại
    assert b.fw.state == State.DISARMED and b.fw.cmd_speed_mm_s == 0
    assert b.command(150, 200) == Result.BAD_STATE
    assert b.request(Action.ARM).result == Result.OK
    outs = []
    for _ in range(5):                                                # ARM không tự chạy tiếp lệnh cũ
        outs += b.run(100)
        assert b.request(Action.PING).result == Result.OK
    assert all(o.state == State.ARMED and o.effort_permille == 0 and o.speed_ref_mm_s == 0 for o in outs)
    assert b.command(150, 200) == Result.OK and b.tick().state == State.RUNNING


def test_validity_is_clamped_to_max_validity():
    b = Bench().armed()
    b.command(100, 0, validity=60000)
    outs = b.run(300)
    running = sum(o.state == State.RUNNING for o in outs)
    assert running * 10 == CFG.max_validity_ms - 10                  # hết hạn ở tick thứ 20 sau khi nhận


@pytest.mark.parametrize("kwargs", [{"validity": 0}, {"flags": 0x02}, {"flags": 0x81}])
def test_bad_command_fields_rejected(kwargs):
    b = Bench().armed()
    assert b.command(100, 0, **kwargs) == Result.BAD_FIELD
    assert b.tick().state == State.ARMED


def test_unknown_action_rejected():
    b = Bench().armed()
    assert b.request(99).result == Result.BAD_FIELD


# ---- lỗi và E-stop ------------------------------------------------------------------------------------------------
def test_estop_latches_until_released_and_cleared_then_needs_arm_and_enable():
    b = Bench().armed()
    for _ in range(5):
        b.command(150, 0)
        b.run(20)
    assert b.fw.effort_permille > 0
    out = b.tick(inputs=FirmwareInputs(estop=True))
    assert out.state == State.FAULT and out.effort_permille == 0 and out.speed_ref_mm_s == 0   # ngay, không dốc
    faults = [m for m in b.log if isinstance(m, FaultMsg)]
    assert len(faults) == 1 and faults[0].fault == Fault.ESTOP
    assert b.request(Action.ARM).result == Result.FAULT_ACTIVE
    assert b.request(Action.CLEAR_FAULT).result == Result.ESTOP_ACTIVE
    b.run(100, FirmwareInputs())                                      # nhả nút: vẫn FAULT
    assert b.fw.state == State.FAULT and b.telemetry()[-1].fault == Fault.ESTOP
    assert b.command(150, 0) == Result.FAULT_ACTIVE
    assert b.request(Action.CLEAR_FAULT).result == Result.OK
    assert b.fw.state == State.DISARMED and b.fw.fault == Fault.NONE
    assert b.command(150, 0) == Result.BAD_STATE
    b.request(Action.ARM)
    assert all(o.effort_permille == 0 for o in b.run(100))
    b.command(150, 0)
    assert b.tick().state == State.RUNNING


def test_estop_while_disarmed_also_latches():
    b = Bench()
    b.hello()
    b.run(150)
    assert b.tick(inputs=FirmwareInputs(estop=True)).state == State.FAULT
    assert b.telemetry()[-1].flags & TelemetryFlag.ESTOP_INPUT


def test_loop_overrun_latches_fault():
    b = Bench().armed()
    b.command(100, 0)
    b.tick()
    out = b.tick(150)
    assert out.state == State.FAULT and b.fw.fault == Fault.LOOP_OVERRUN
    assert [m.detail for m in b.log if isinstance(m, FaultMsg)] == [150]
    assert b.request(Action.CLEAR_FAULT).result == Result.OK and b.fw.state == State.DISARMED


def test_supply_low_fault_clears_only_when_supply_recovers():
    b = Bench(replace(CFG, min_supply_mv=6000))
    b.hello()
    b.run(150, FirmwareInputs(supply_valid=True, supply_mv=7400))
    assert b.fw.state == State.DISARMED
    b.tick(inputs=FirmwareInputs(supply_valid=True, supply_mv=5500))
    assert b.fw.fault == Fault.SUPPLY_LOW
    assert b.request(Action.CLEAR_FAULT).result == Result.FAULT_ACTIVE
    b.tick(inputs=FirmwareInputs(supply_valid=True, supply_mv=7000))
    assert b.request(Action.CLEAR_FAULT).result == Result.OK


def test_required_feedback_missing_while_running_faults():
    b = Bench(replace(CFG, require_speed_feedback=True)).armed()
    b.command(100, 0)
    assert b.tick(inputs=FirmwareInputs()).state == State.FAULT
    assert b.fw.fault == Fault.FEEDBACK_LOST


# ---- giới hạn, dốc, đổi chiều ------------------------------------------------------------------------------------
def test_speed_and_steer_are_clamped_and_rate_limited():
    b = Bench().armed()
    refs = []
    for _ in range(80):
        b.command(5000, -9000)
        for o in b.run(20):
            refs.append((o.speed_ref_mm_s, o.steer_ref_mrad))
    speeds, steers = [r[0] for r in refs], [r[1] for r in refs]
    assert max(speeds) == CFG.max_speed_mm_s and min(steers) == -CFG.max_steer_mrad
    accel_step = CFG.max_accel_mm_s2 * 10 // 1000
    assert all(0 <= b_ - a <= accel_step for a, b_ in zip(speeds, speeds[1:]))
    steer_step = CFG.max_steer_rate_mrad_s * 10 / 1000
    assert all(abs(b_ - a) <= steer_step + 1 for a, b_ in zip(steers, steers[1:]))


def test_reverse_waits_for_zero_hold_and_measured_standstill():
    cfg = replace(CFG, max_accel_mm_s2=3000, max_decel_mm_s2=3000)
    b = Bench(cfg).armed()
    moving = FirmwareInputs(speed_valid=True, speed_mm_s=100)
    for _ in range(5):
        b.command(100, 0)
        b.run(20, moving)
    assert b.fw.speed_ref_mm_s == 100
    history = []
    for _ in range(20):                                               # lệnh lùi, xe (giả) vẫn đang trôi 50 mm/s
        b.command(-100, 0)
        history += b.run(20, FirmwareInputs(speed_valid=True, speed_mm_s=50))
    assert min(o.speed_ref_mm_s for o in history) == 0                # không lùi khi phản hồi báo còn chạy
    assert all(o.effort_permille >= 0 for o in history)
    zero_since = next(i for i, o in enumerate(history) if o.speed_ref_mm_s == 0)
    assert all(o.speed_ref_mm_s == 0 for o in history[zero_since:])
    for _ in range(3):                                                # đã dừng: đứng đủ hold → lùi ngay
        b.command(-100, 0)
        history = b.run(20, FirmwareInputs(speed_valid=True, speed_mm_s=0))
    assert b.fw.speed_ref_mm_s < 0 and b.fw.effort_permille < 0


def test_reverse_without_feedback_uses_hold_time_only():
    cfg = replace(CFG, max_accel_mm_s2=3000, max_decel_mm_s2=3000, direction_change_hold_ms=100)
    b = Bench(cfg).armed()
    for _ in range(5):
        b.command(100, 0)
        b.run(20)
    refs = []
    for _ in range(15):
        b.command(-100, 0)
        refs += [o.speed_ref_mm_s for o in b.run(20)]
    first_zero = refs.index(0)
    first_negative = next(i for i, v in enumerate(refs) if v < 0)
    assert all(v == 0 for v in refs[first_zero:first_negative])
    assert (first_negative - first_zero) * 10 == cfg.direction_change_hold_ms


# ---- vòng tốc độ ----------------------------------------------------------------------------------------------------
def test_speed_loop_integrates_error_and_respects_saturation_and_direction():
    cfg = replace(CFG, max_accel_mm_s2=30000, max_effort_permille=1000)   # trần 1000: thử cơ chế PI, không thử trần
    b = Bench(cfg).armed()
    slow = FirmwareInputs(speed_valid=True, speed_mm_s=50)
    efforts = []
    for _ in range(10):
        b.command(200, 0)
        efforts += [o.effort_permille for o in b.run(20, slow)]
    assert efforts[-1] > efforts[3] and all(b_ >= a for a, b_ in zip(efforts[2:], efforts[3:]))   # I tăng dần
    assert b.telemetry()[-1].flags & TelemetryFlag.SPEED_LOOP_CLOSED
    # Chạy nhanh hơn mục tiêu rất nhiều: effort về 0, không đảo dấu (không tự phanh/lùi)
    fast = FirmwareInputs(speed_valid=True, speed_mm_s=2000)
    for _ in range(10):
        b.command(200, 0)
        outs = b.run(20, fast)
    assert all(o.effort_permille == 0 for o in outs)


def test_speed_loop_anti_windup_releases_saturation_immediately():
    # integ_limit lớn để nếu không có chống bão hòa thì tích phân phình tới 800 ‰ và effort kẹt ở 1000. Trần 1000 và
    # tắt STALL: ở đây chỉ thử cơ chế chống bão hòa (bánh kẹt 1 s sẽ chốt STALL, có test riêng bên dưới).
    cfg = replace(CFG, max_accel_mm_s2=30000, integ_limit_permille=800, max_effort_permille=1000, stall_timeout_ms=0)
    b = Bench(cfg).armed()
    stalled = FirmwareInputs(speed_valid=True, speed_mm_s=0)          # bánh bị kẹt: sai số lớn kéo dài
    for _ in range(100):
        b.command(300, 0)
        outs = b.run(20, stalled)
    assert outs[-1].effort_permille == 1000
    ff = cfg.deadzone_comp_permille + cfg.ff_permille_per_mps * 300 // 1000
    p_term = cfg.kp_permille_per_mps * 300 // 1000
    ki_step = cfg.ki_permille_per_m * 300 * 10 // 1_000_000
    assert b.fw.integ // 1_000_000_000 <= 1000 - ff - p_term + ki_step   # ngừng tích khi đã bão hòa
    b.command(300, 0)
    out = b.tick(inputs=FirmwareInputs(speed_valid=True, speed_mm_s=300))  # xe chạy lại đúng tốc độ
    assert out.effort_permille < 1000 and out.effort_permille <= 1000 - p_term + ki_step


def test_open_loop_without_speed_feedback_is_feedforward_only():
    cfg = replace(CFG, max_accel_mm_s2=30000, max_effort_permille=1000)
    b = Bench(cfg).armed()
    b.command(200, 0)
    out = b.run(20)[-1]
    assert out.effort_permille == cfg.deadzone_comp_permille + cfg.ff_permille_per_mps * 200 // 1000
    assert not b.fw.loop_closed and b.fw.integ == 0


# ---- trần effort và kiểm STALL -------------------------------------------------------------------------------------
def test_default_effort_cap_is_below_feedforward_for_max_speed():
    """Kẹp max_speed chỉ áp lên mục tiêu: với hệ số giả định, mạch hở ở max_speed đòi 700 ‰ (≈ 70 % ga). Trần mặc
    định phải nhỏ hơn thế, nếu không lần bật xung đầu tiên (chưa có encoder) chạy ga lớn."""
    cfg = FirmwareConfig()
    ff_at_max_speed = cfg.deadzone_comp_permille + cfg.ff_permille_per_mps * cfg.max_speed_mm_s // 1000
    assert ff_at_max_speed == 700 and cfg.max_effort_permille == 250 < ff_at_max_speed
    assert cfg.stall_effort_permille <= cfg.max_effort_permille and cfg.stall_timeout_ms > 0


@pytest.mark.parametrize("inputs", [FirmwareInputs(),                                        # không encoder: mạch hở
                                    FirmwareInputs(speed_valid=True, speed_mm_s=0),          # encoder kẹt 0
                                    FirmwareInputs(speed_valid=True, speed_mm_s=-300)],      # encoder đảo dấu
                         ids=["open_loop", "stuck_zero", "inverted"])
def test_effort_never_exceeds_cap_open_or_closed_loop(inputs):
    cfg = replace(CFG, max_accel_mm_s2=30000, max_effort_permille=250, stall_timeout_ms=0)
    for speed in (300, -300):                          # ff = ±(100 + 600) = ±700 ‰ > trần; vòng kín còn cộng P và I
        b = Bench(cfg).armed()
        outs = []
        for _ in range(50):
            b.command(speed, 0)
            outs += b.run(20, inputs if speed > 0 or not inputs.speed_valid
                          else replace(inputs, speed_mm_s=-inputs.speed_mm_s))
        efforts = [o.effort_permille for o in outs]
        assert max(abs(e) for e in efforts) == 250 and b.fw.state == State.RUNNING
        assert all(e * speed >= 0 for e in efforts)   # không đẩy ngược chiều mục tiêu
        assert max(abs(m.effort_permille) for m in b.telemetry()) == 250


@pytest.mark.parametrize("measured", [0, -150], ids=["stuck_zero", "inverted"])
def test_stall_latches_fault_when_effort_high_but_car_does_not_follow(measured):
    cfg = replace(CFG, max_accel_mm_s2=30000, stall_timeout_ms=500)
    b = Bench(cfg).armed()
    bad = FirmwareInputs(speed_valid=True, speed_mm_s=measured)
    outs = []
    for _ in range(40):
        b.command(300, 0)
        outs += b.run(20, bad)
    assert b.fw.state == State.FAULT and b.fw.fault == Fault.STALL
    k = next(i for i, o in enumerate(outs) if o.state == State.FAULT)
    assert k * 10 == cfg.stall_timeout_ms and outs[k].effort_permille == 0          # đúng hạn, effort 0 ngay
    assert all(o.effort_permille == cfg.max_effort_permille for o in outs[:k])     # trước đó: ở trần, không quá
    faults = [m for m in b.log if isinstance(m, FaultMsg)]
    assert [(m.fault, m.detail) for m in faults] == [(Fault.STALL, cfg.max_effort_permille)]
    assert b.telemetry()[-1].fault == Fault.STALL
    assert b.command(300, 0) == Result.FAULT_ACTIVE
    assert b.request(Action.CLEAR_FAULT).result == Result.OK and b.fw.state == State.DISARMED   # rồi phải ARM lại


def test_stall_check_needs_continuous_condition_and_does_not_fire_when_car_follows_or_without_feedback():
    cfg = replace(CFG, max_accel_mm_s2=30000, stall_timeout_ms=300)
    for inputs in (FirmwareInputs(speed_valid=True, speed_mm_s=290), FirmwareInputs()):
        b = Bench(cfg).armed()
        for _ in range(40):
            b.command(300, 0)
            b.run(20, inputs)
        assert b.fw.state == State.RUNNING and b.fw.fault == Fault.NONE
    # Kẹt 250 ms, chạy 10 ms, kẹt 250 ms...: không lần nào liên tục đủ 300 ms → không STALL.
    b = Bench(cfg).armed()
    for _ in range(8):
        for _ in range(5):
            b.command(300, 0)
            b.run(50, FirmwareInputs(speed_valid=True, speed_mm_s=0))
        b.run(10, FirmwareInputs(speed_valid=True, speed_mm_s=290))
    assert b.fw.state == State.RUNNING and b.fw.fault == Fault.NONE
    for _ in range(4):                                  # cùng cấu hình, kẹt liên tục ≥ 300 ms thì chốt
        b.command(300, 0)
        b.run(100, FirmwareInputs(speed_valid=True, speed_mm_s=0))
    assert b.fw.state == State.FAULT and b.fw.fault == Fault.STALL


# ---- telemetry ----------------------------------------------------------------------------------------------------
def test_telemetry_marks_invalid_sensors_with_zero_and_clear_flag():
    b = Bench()
    b.hello()
    b.run(100, FirmwareInputs(tof_valid_mask=0b0101, tof_mm=(150, 999, 70000, 5), imu_valid=False, gyro_z_mrad_s=77,
                              speed_valid=False, speed_mm_s=123, supply_valid=True, supply_mv=7400))
    tel = b.telemetry()[-1]
    assert tel.tof_valid_mask == 0b0101 and tel.tof_mm == (150, 0, 65535, 0)
    assert tel.gyro_z_mrad_s == 0 and tel.speed_measured_mm_s == 0 and tel.supply_mv == 7400
    assert not tel.flags & TelemetryFlag.SPEED_VALID and tel.flags & TelemetryFlag.SUPPLY_VALID


def test_telemetry_counts_parser_errors_and_rejects():
    b = Bench()
    b.hello()
    b.fw.receive(b"\x13\x37\x00" + b"\x55" * 300 + b"\x00", b.t)
    b.command(10, 0)
    b.run(60)
    tel = b.telemetry()[-1]
    assert tel.rx_errors == 2 and tel.rejects == 1


def test_tx_overflow_drops_frames_but_sequence_reveals_gap():
    b = Bench(replace(CFG, tx_capacity=60))
    b.fw.receive(encode_frame(Hello(SESSION, 0)), 0)       # HELLO_ACK 39 byte, chưa ai đọc
    b.fw.step(10, FirmwareInputs())                        # telemetry 55 byte: không vừa → bỏ
    b.t = 10
    assert b.fw.tx_overflow == 1
    b.run(60)
    seqs = [m.sequence for m in b.log]
    assert seqs[:2] == [0, 2]                              # khung số 1 bị bỏ: laptop thấy khoảng hở


def test_time_helpers_match_cpp_semantics():
    assert tdiv(-7, 2) == -3 and tdiv(7, -2) == -3 and tdiv(-7, -2) == 3 and tdiv(7, 2) == 3
    assert elapsed_ms(5, 0xFFFFFFF0) == 21


def test_clock_wraparound_keeps_timeouts_correct():
    b = Bench(now=0xFFFFFFFF - 250)
    b.armed()
    b.command(100, 0)
    outs = b.run(400)
    assert b.t < 1000                                       # millis đã quay vòng
    running = sum(o.state == State.RUNNING for o in outs)
    assert running * 10 == 150 - 10                         # hết hạn đúng 150 ms dù qua mốc 2^32


@pytest.mark.parametrize("bad", [{"max_speed_mm_s": 0}, {"max_speed_mm_s": 40000}, {"link_timeout_ms": -1},
                                 {"boot_hold_ms": 1.5}, {"require_speed_feedback": 1},
                                 {"default_telemetry_period_ms": 5}, {"tx_capacity": 0}, {"tx_capacity": 1025},
                                 {"tx_capacity": 2000}, {"max_effort_permille": 0}, {"max_effort_permille": 1001},
                                 {"stall_effort_permille": 0}, {"stall_effort_permille": 251},
                                 {"stall_timeout_ms": -1}])
def test_config_validation(bad):
    with pytest.raises(ValueError):
        replace(FirmwareConfig(), **bad)


def test_tx_capacity_limit_matches_the_cpp_static_buffer():
    """Python không được nhận cấu hình mà firmware C++ không biểu diễn được (bộ đệm gửi tĩnh kTxBufferSize)."""
    import re
    header = (DEFAULT_PATH.parents[1] / "src" / "core" / "vehicle_core.h").read_text(encoding="utf-8")
    match = re.search(r"kTxBufferSize\s*=\s*(\d+)\s*;", header)
    assert match and int(match.group(1)) == TX_BUFFER_SIZE == 1024
    assert FirmwareConfig(tx_capacity=TX_BUFFER_SIZE).tx_capacity == 1024
    with pytest.raises(ValueError, match="1024"):
        FirmwareConfig(tx_capacity=TX_BUFFER_SIZE + 1)
    with pytest.raises(ValueError):
        FirmwareConfig.from_dict({"tx_capacity": 2000})


def test_inputs_validation_rejects_floats():
    with pytest.raises(ValueError):
        FirmwareInputs(speed_valid=True, speed_mm_s=1.5)
    with pytest.raises(ValueError):
        FirmwareInputs(tof_mm=(1, 2, 3))


# ---- vector mẫu --------------------------------------------------------------------------------------------------
def test_vector_scenarios_replay_exactly():
    """Điều mà test C++ làm với firmware thật: chạy lại từng bước và so khớp từng byte gửi đi."""
    vectors = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    assert len(vectors["scenarios"]) >= 10
    for scenario in vectors["scenarios"]:
        fw = FirmwareModel(FirmwareConfig.from_dict(scenario["config"]), now_ms=scenario["boot_ms"],
                           boot_id=scenario["boot_id"], reset_reason=scenario["reset_reason"])
        for k, step in enumerate(scenario["steps"]):
            if step["rx"]:
                fw.receive(bytes.fromhex(step["rx"]), step["t"])
            out = fw.step(step["t"], FirmwareInputs.from_dict(step["in"]))
            got = {"state": int(out.state), "fault": int(fw.fault), "stop_reason": int(fw.stop_reason),
                   "session_id": fw.session_id, "speed_ref_mm_s": out.speed_ref_mm_s,
                   "steer_ref_mrad": out.steer_ref_mrad, "effort_permille": out.effort_permille,
                   "tx_overflow": fw.tx_overflow, "tx": fw.take_tx().hex()}
            assert got == step["expect"], f"{scenario['name']} step {k} t={step['t']}"


def test_vector_scenarios_include_disarm_hello_latches_period_and_overflow():
    vectors = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    by_name = {s["name"]: s for s in vectors["scenarios"]}
    latches = by_name["disarm_and_hello_keep_boot_and_fault"]
    before = int(State.BOOT)
    seen = {"DISARM": set(), "HELLO": set()}
    host = FrameParser()
    for step in latches["steps"]:
        after = step["expect"]["state"]
        for m in host.feed(bytes.fromhex(step["rx"])):
            kind = "HELLO" if isinstance(m, Hello) else "DISARM" if (isinstance(m, Request) and
                                                                    m.action == Action.DISARM) else None
            if kind is None:
                continue
            seen[kind].add(before)
            if before in (State.BOOT, State.FAULT):
                assert after == before, (kind, step["t"])  # không rút ngắn BOOT, không xóa FAULT
                if before == State.FAULT:
                    assert step["expect"]["fault"] == Fault.ESTOP
            else:
                assert after == State.DISARMED
                assert step["expect"]["stop_reason"] == (StopReason.HOST_DISARM if kind == "DISARM"
                                                         else StopReason.NEW_SESSION)
        before = after
    assert {int(State.BOOT), int(State.RUNNING), int(State.FAULT)} <= seen["DISARM"]
    assert {int(State.BOOT), int(State.FAULT)} <= seen["HELLO"]
    period = by_name["telemetry_period_not_multiple_of_tick"]["steps"]
    assert {s["t"] - p["t"] for p, s in zip(period, period[1:])} >= {10, 40, 70}
    overflow = by_name["tx_overflow_gap"]
    assert overflow["config"]["tx_capacity"] == 100 and overflow["steps"][-1]["expect"]["tx_overflow"] >= 2


def test_vector_scenarios_cover_every_state_result_and_stop_reason():
    vectors = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    states, reasons, results, faults = set(), set(), set(), set()
    for scenario in vectors["scenarios"]:
        parser = FrameParser(accept_types=DEVICE_TO_HOST)
        for step in scenario["steps"]:
            states.add(step["expect"]["state"])
            reasons.add(step["expect"]["stop_reason"])
            faults.add(step["expect"]["fault"])
            for m in parser.feed(bytes.fromhex(step["expect"]["tx"])):
                if isinstance(m, Ack):
                    results.add(m.result)
    assert states == {int(s) for s in State}
    assert {int(r) for r in StopReason} - {StopReason.NONE} <= reasons
    assert {int(r) for r in Result} <= results
    assert {Fault.NONE, Fault.ESTOP, Fault.LOOP_OVERRUN, Fault.STALL} <= faults


def test_vector_scenario_checks_default_effort_cap_and_stall_for_cpp():
    """Vector cho C++: trần effort mặc định (250 ‰) cả mạch hở lẫn vòng kín, STALL với encoder kẹt 0 và đảo dấu."""
    vectors = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    scenario = {s["name"]: s for s in vectors["scenarios"]}["effort_cap_and_stall"]
    cfg = FirmwareConfig.from_dict(scenario["config"])
    assert cfg.max_effort_permille == FirmwareConfig().max_effort_permille == 250
    steps = scenario["steps"]
    efforts = [s["expect"]["effort_permille"] for s in steps]
    assert max(efforts) == 250 and min(efforts) >= 0
    open_loop = [s for s in steps if not s["in"] and s["expect"]["state"] == State.RUNNING]
    assert open_loop and max(s["expect"]["speed_ref_mm_s"] for s in open_loop) == 300    # ff 700 ‰ nhưng effort 250
    parser = FrameParser(accept_types=DEVICE_TO_HOST)
    stall_faults = []
    for s in steps:
        stall_faults += [(s["in"].get("speed_mm_s", 0), m.detail) for m in parser.feed(bytes.fromhex(s["expect"]["tx"]))
                         if isinstance(m, FaultMsg) and m.fault == Fault.STALL]
    assert stall_faults == [(0, 250), (-150, 250)]                  # kẹt 0 rồi đảo dấu, detail = |effort|
    # Vector cũ giữ trần 1000 ‰ để số học PI không bị trần che (xem VECTOR_CONFIG).
    assert all(s["config"]["max_effort_permille"] == 1000 for s in vectors["scenarios"] if s is not scenario)
