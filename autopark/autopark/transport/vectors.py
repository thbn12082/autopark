"""Sinh vector mẫu chung Python ↔ C++ cho giao thức và logic firmware.

    python -m autopark.transport.vectors --write     # ghi firmware/esp32_vehicle/test/vectors.json
    python -m autopark.transport.vectors --check     # báo lỗi nếu file khác bản sinh lại

Nguồn sự thật là `protocol.py` + `firmware_model.py`. File JSON chứa: giá trị CRC, cặp COBS, từng loại thông điệp
(trường → byte thông điệp → byte khung), các luồng byte lỗi gửi tới bo cùng số lỗi từng loại mà bộ tách khung phải
đếm, và các kịch bản máy trạng thái: mỗi bước là (thời điểm ms, byte nhận được, ngõ vào) → (trạng thái, lỗi, lý do
dừng, phiên, mục tiêu tốc độ/góc, effort, số khung đã bỏ vì đầy bộ đệm gửi, TOÀN BỘ byte bo gửi đi trong bước đó).
Bộ test C++
(`firmware/esp32_vehicle/test/host/test_main.cpp`) chạy lại đúng các bước này và phải ra cùng byte.

Mọi số trong file là số nguyên (không có số thực), để bộ đọc JSON tối giản phía C++ đủ dùng.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import random
import sys

from .firmware_model import FirmwareConfig, FirmwareInputs, FirmwareModel
from .protocol import (PROTOCOL_VERSION, Ack, Action, Command, FaultMsg, FrameParser, Hello, HelloAck, HOST_TO_DEVICE,
                       Limits, MsgType, Request, ResetReason, TelemetryMsg, cobs_encode, crc16_ccitt_false,
                       encode_frame, encode_message, frame_from_raw, message_fields)

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "firmware" / "esp32_vehicle" / "test" / "vectors.json"
FORMAT = "autopark-vehicle-vectors"
FORMAT_VERSION = 1

# Cấu hình ngắn gọn cho kịch bản (thời gian nhỏ để vector ngắn); các trường khác giữ mặc định. Trần effort 1000 ‰
# để các kịch bản vòng tốc độ kiểm số học PI đầy đủ, không bị trần mặc định (250 ‰) che; trần mặc định và STALL có
# kịch bản riêng (`effort_cap_and_stall`).
VECTOR_CONFIG = FirmwareConfig(boot_hold_ms=100, default_telemetry_period_ms=100, link_timeout_ms=300,
                               max_validity_ms=200, direction_change_hold_ms=100, max_tick_gap_ms=100,
                               max_effort_permille=1000)
SESSION_A = 0xA1B2C3D4
SESSION_B = 0x0BADF00D
BOOT_ID = 0x5EED1234


def _message_vectors() -> list[dict]:
    limits = Limits(300, 524, 1571, 300, 600, 600, 200, 300)
    messages = [
        ("hello_basic", Hello(SESSION_A, 0, 0, 0)),
        ("hello_extremes", Hello(0xFFFFFFFF, 0xFFFF, 0xFFFF, 0xFFFFFFFF)),
        ("request_arm", Request(SESSION_A, 1, int(Action.ARM))),
        ("request_ping_wrap", Request(SESSION_A, 0xFFFF, int(Action.PING))),
        ("command_forward_left", Command(SESSION_A, 2, 150, 1, 120, 250)),
        ("command_reverse_right", Command(SESSION_A, 3, 150, 1, -80, -300)),
        ("command_int16_extremes", Command(SESSION_A, 4, 0xFFFF, 0, -32768, 32767)),
        ("command_zero_bytes", Command(0, 0, 0, 0, 0, 0)),       # thân toàn 0: thử COBS với nhiều byte 0
        ("hello_ack", HelloAck(SESSION_A, 0, 7, 1, 0, BOOT_ID, int(ResetReason.WATCHDOG), 1, 50, limits)),
        ("ack_bad_state", Ack(SESSION_A, 5, int(MsgType.COMMAND), 9, 5, 1, 0)),
        ("telemetry_full", TelemetryMsg(SESSION_A, 6, 123456, 3, 0, 3, 0xBF, 42, 17, 101, -52, 100, -50, 287, 12,
                                        -340, 25, 0b1011, (150, 0, 1200, 65535), 7400, 3, 2)),
        ("telemetry_nothing_valid", TelemetryMsg(SESSION_A, 0xFFFF, 0xFFFFFFFF, 1, 0, 1, 0, 0, 0xFFFF, 0, 0, 0, 0,
                                                 0, 0, 0, 0, 0, (0, 0, 0, 0), 0, 0, 0)),
        ("fault_estop", FaultMsg(SESSION_A, 8, 1, 4, 5000, 0)),
    ]
    out = []
    for name, msg in messages:
        raw = encode_message(msg)
        out.append({"name": name, "type": int(msg.TYPE), "fields": message_fields(msg), "raw": raw.hex(),
                    "frame": frame_from_raw(raw).hex()})
    return out


def _stream_vectors() -> list[dict]:
    """Luồng byte gửi TỚI bo (bộ tách khung phía bo chỉ nhận HELLO/REQUEST/COMMAND)."""
    arm = encode_frame(Request(SESSION_A, 1, int(Action.ARM)))
    cmd = encode_frame(Command(SESSION_A, 2, 150, 1, 120, 250))
    hello = encode_frame(Hello(SESSION_A, 0, 0, 0))
    raw_cmd = encode_message(Command(SESSION_A, 2, 150, 1, 120, 250))
    bad_crc = bytearray(cobs_encode(raw_cmd + bytes(2)) + b"\x00")
    wrong_version = frame_from_raw(bytes([PROTOCOL_VERSION + 1]) + raw_cmd[1:])
    telemetry_to_device = encode_frame(TelemetryMsg(SESSION_A, 1, 0, 1, 0, 0, 0, 0, 0xFFFF, 0, 0, 0, 0, 0, 0, 0, 0,
                                                    0, (0, 0, 0, 0), 0, 0, 0))
    long_raw = raw_cmd + b"\x01"                       # đúng CRC nhưng dài hơn COMMAND một byte
    rng = random.Random(20260924)
    garbage = bytes(rng.randrange(1, 256) for _ in range(40))
    streams = [
        ("clean_three_frames", hello + arm + cmd, 3, {}),
        ("leading_garbage_then_delimiter", garbage + b"\x00" + arm, 1, 1),
        ("garbage_merged_into_frame", garbage[:5] + arm + cmd, 1, 1),
        ("truncated_frame", arm[:-4] + b"\x00" + cmd, 1, 1),
        ("bad_crc", bytes(bad_crc) + arm, 1, {"crc": 1}),
        ("wrong_version", wrong_version + arm, 1, {"version": 1}),
        ("device_type_sent_to_device", telemetry_to_device + arm, 1, {"type": 1}),
        ("wrong_length", frame_from_raw(long_raw) + arm, 1, {"length": 1}),
        ("too_short", frame_from_raw(raw_cmd[:5]) + arm, 1, {"short": 1}),
        ("oversize", bytes([0x11]) * 200 + b"\x00" + arm, 1, {"oversize": 1}),
        ("empty_frames_are_not_errors", b"\x00\x00\x00" + arm + b"\x00" + cmd, 2, {}),
    ]
    out = []
    for name, stream, n_messages, errors in streams:
        parser = FrameParser(accept_types=HOST_TO_DEVICE)
        msgs = parser.feed(stream)
        counts = {k: v for k, v in parser.stats.as_dict().items() if k not in ("frames", "messages", "empty") and v}
        # `errors` là dict {loại: số} khi loại lỗi xác định trước; là số nguyên khi nội dung ngẫu nhiên quyết định
        # loại lỗi (rác có thể là COBS hỏng hoặc sai CRC) — khi đó chỉ kiểm tổng số lỗi.
        expected_ok = counts == errors if isinstance(errors, dict) else sum(counts.values()) == errors
        if len(msgs) != n_messages or not expected_ok:
            raise AssertionError(f"stream {name}: got {len(msgs)} messages and {counts}, expected {n_messages}, {errors}")
        out.append({"name": name, "stream": stream.hex(), "messages": [encode_message(m).hex() for m in msgs],
                    "errors": {k: parser.stats.as_dict()[k] for k in ("cobs", "short", "crc", "version", "type",
                                                                         "length", "oversize")},
                    "empty": parser.stats.empty})
    return out


class _Script:
    """Ghi một kịch bản bằng cách chạy FirmwareModel; kỳ vọng là những gì mô hình tham chiếu tạo ra."""

    def __init__(self, name: str, description: str, *, config: FirmwareConfig = VECTOR_CONFIG, boot_ms: int = 0,
                 boot_id: int = BOOT_ID, reset_reason: ResetReason = ResetReason.POWER_ON):
        self.name, self.description, self.config = name, description, config
        self.boot_ms, self.boot_id, self.reset_reason = boot_ms & 0xFFFFFFFF, boot_id, reset_reason
        self.fw = FirmwareModel(config, now_ms=boot_ms, boot_id=boot_id, reset_reason=reset_reason)
        self.t = boot_ms
        self.inputs = FirmwareInputs()
        self.steps: list[dict] = []

    def step(self, dt: int = 10, rx: bytes = b"", inputs: FirmwareInputs | None = None) -> None:
        self.t = (self.t + dt) & 0xFFFFFFFF
        if inputs is not None:
            self.inputs = inputs
        if rx:
            self.fw.receive(rx, self.t)
        out = self.fw.step(self.t, self.inputs)
        tx = self.fw.take_tx()
        self.steps.append({
            "t": self.t, "rx": rx.hex(), "in": self.inputs.to_dict(),
            "expect": {"state": int(out.state), "fault": int(self.fw.fault), "stop_reason": int(self.fw.stop_reason),
                       "session_id": self.fw.session_id, "speed_ref_mm_s": out.speed_ref_mm_s,
                       "steer_ref_mrad": out.steer_ref_mrad, "effort_permille": out.effort_permille,
                       "tx_overflow": self.fw.tx_overflow, "tx": tx.hex()}})

    def idle(self, duration: int, inputs: FirmwareInputs | None = None) -> None:
        for _ in range(duration // 10):
            self.step(10, inputs=inputs)

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description, "config": self.config.to_dict(),
                "boot_ms": self.boot_ms, "boot_id": self.boot_id, "reset_reason": int(self.reset_reason),
                "steps": self.steps}


def _hello(session: int, seq: int, period: int = 0) -> bytes:
    return encode_frame(Hello(session, seq, period, 0))


def _req(session: int, seq: int, action: int) -> bytes:
    return encode_frame(Request(session, seq, action))


def _cmd(session: int, seq: int, speed: int, steer: int, *, validity: int = 150, flags: int = 1) -> bytes:
    return encode_frame(Command(session, seq, validity, flags, speed, steer))


def _scenario_boot_run_timeout() -> dict:
    s = _Script("boot_arm_run_timeout_link_loss",
                "BOOT từ chối ARM; lệnh trước ARM bị từ chối và KHÔNG được nhớ; chạy; hết hạn lệnh → ARMED, dốc về 0, "
                "trả lái về giữa sau khi tốc độ về 0; im lặng quá link_timeout → DISARMED.")
    s.step(10, _hello(SESSION_A, 100))
    s.step(40, _req(SESSION_A, 101, Action.ARM))            # t=50: NOT_READY
    s.idle(50)                                               # t=100: hết BOOT
    s.step(20, _cmd(SESSION_A, 102, 150, 300))               # DISARMED → BAD_STATE
    s.step(10, _req(SESSION_A, 103, Action.ARM))             # ARMED
    s.step(10)
    s.step(10)
    seq = 104
    for _ in range(5):                                       # 5 lệnh cách 50 ms: chạy liên tục
        s.step(10, _cmd(SESSION_A, seq, 150, 300))
        seq += 1
        s.idle(40)
    s.idle(700)                                              # lệnh hết hạn, rồi mất liên lạc
    return s.to_dict()


def _scenario_sequence_session() -> dict:
    s = _Script("sequence_and_session_rules",
                "NO_SESSION trước HELLO; HELLO session 0 bị từ chối; trùng, cũ, sai phiên; trường sai; quay vòng "
                "uint16 65535 → 0; HELLO phiên mới khi đang chạy → DISARMED và lệnh phiên cũ bị từ chối.")
    s.step(10, _cmd(SESSION_A, 1, 50, 0))                    # NO_SESSION
    s.step(10, _hello(0, 0))                                 # BAD_FIELD
    s.step(10, _hello(SESSION_A, 65530))
    s.idle(100)                                              # qua BOOT
    s.step(10, _req(SESSION_A, 65531, Action.ARM))
    s.step(10, _req(SESSION_A, 65531, Action.PING))          # DUPLICATE
    s.step(10, _req(SESSION_A, 65529, Action.PING))          # OUT_OF_ORDER
    s.step(10, _req(SESSION_B, 65532, Action.PING))          # WRONG_SESSION
    s.step(10, _cmd(SESSION_A, 65532, 50, 0, validity=0))    # BAD_FIELD (validity 0) — số thứ tự vẫn được nhận
    s.step(10, _cmd(SESSION_A, 65533, 50, 0, flags=0x03))    # BAD_FIELD (bit dự trữ)
    s.step(10, _req(SESSION_A, 65534, 9))                    # BAD_FIELD (action lạ)
    s.step(10, _cmd(SESSION_A, 65535, 80, 100))              # RUNNING
    s.step(10, _cmd(SESSION_A, 0, 80, 100))                  # quay vòng: mới hơn
    s.step(10, _cmd(SESSION_A, 1, 80, 100))
    s.step(10, _cmd(SESSION_A, 65535, 80, 100))              # OUT_OF_ORDER sau quay vòng
    s.step(10, _cmd(SESSION_A, 1, 80, 100))                  # DUPLICATE
    s.step(10, _hello(SESSION_B, 500))                       # phiên mới: DISARMED, NEW_SESSION
    s.step(10, _cmd(SESSION_A, 2, 80, 100))                  # WRONG_SESSION
    s.step(10, _cmd(SESSION_B, 501, 80, 100))                # BAD_STATE: phải ARM lại
    s.idle(100)
    s.step(10, _req(SESSION_B, 502, Action.ARM))
    s.step(10, _cmd(SESSION_B, 503, 80, 100))                # RUNNING lại, bắt đầu từ mục tiêu đang dốc
    s.idle(60)
    s.step(10, _cmd(SESSION_B, 504, 0, 0, flags=0))          # enable=0: ARMED, ENABLE_CLEARED
    s.idle(100)
    s.step(10, _req(SESSION_B, 505, Action.DISARM))
    s.idle(30)
    return s.to_dict()


def _scenario_estop() -> dict:
    s = _Script("estop_latch",
                "E-stop khi đang chạy → FAULT, effort 0 ngay, gửi FAULT; nhả nút vẫn FAULT; ARM bị từ chối; "
                "CLEAR_FAULT khi nút còn nhấn bị từ chối; nhả rồi CLEAR → DISARMED; phải ARM và gửi lệnh mới.")
    fb = FirmwareInputs(speed_valid=True, speed_mm_s=0)
    s.step(10, _hello(SESSION_A, 10), fb)
    s.idle(100)
    s.step(10, _req(SESSION_A, 11, Action.ARM))
    seq = 12
    for k in range(6):
        s.step(10, _cmd(SESSION_A, seq, 120, -200), FirmwareInputs(speed_valid=True, speed_mm_s=min(3 * k, 120)))
        seq += 1
        s.step(10)
    pressed = FirmwareInputs(estop=True, speed_valid=True, speed_mm_s=15)
    s.step(10, _cmd(SESSION_A, seq, 120, -200), pressed)
    seq += 1
    s.step(10, _req(SESSION_A, seq, Action.ARM))
    seq += 1
    s.step(10, _req(SESSION_A, seq, Action.CLEAR_FAULT))
    seq += 1
    released = FirmwareInputs(speed_valid=True, speed_mm_s=0)
    s.step(10, inputs=released)
    s.step(10, _cmd(SESSION_A, seq, 120, -200))              # FAULT_ACTIVE
    seq += 1
    s.step(10, _req(SESSION_A, seq, Action.CLEAR_FAULT))     # OK → DISARMED
    seq += 1
    s.step(10, _cmd(SESSION_A, seq, 120, -200))              # BAD_STATE
    seq += 1
    s.step(10, _req(SESSION_A, seq, Action.ARM))
    seq += 1
    s.step(10, _cmd(SESSION_A, seq, 120, -200))              # RUNNING
    s.idle(80)
    return s.to_dict()


def _scenario_limits_reverse_loop() -> dict:
    s = _Script("limits_reverse_interlock_speed_loop",
                "Kẹp tốc độ/góc theo giới hạn, dốc tăng tốc và tốc độ đổi lái; đổi chiều: giảm về 0, đứng 0 đủ "
                "direction_change_hold_ms và phản hồi báo đã dừng mới lùi; vòng PI số nguyên với phản hồi giả; "
                "validity bị kẹp; mất phản hồi tốc độ → feedforward hở.",
                config=replace(VECTOR_CONFIG, max_accel_mm_s2=2000, max_decel_mm_s2=3000, max_steer_rate_mrad_s=6000))
    s.step(10, _hello(SESSION_A, 1, 50))
    s.idle(100)
    s.step(10, _req(SESSION_A, 2, Action.ARM))
    seq = 3
    measured = 0
    for k in range(40):
        target = 1000 if k < 20 else -100                    # 1000 mm/s bị kẹp về max_speed; rồi đổi chiều
        steer = 2000 if k < 20 else -2000                    # bị kẹp về max_steer
        rx = _cmd(SESSION_A, seq, target, steer) if k % 3 == 0 else b""
        if rx:
            seq += 1
        # Phản hồi giả: xe bám mục tiêu trễ 1 bước, chỉ được 80 % (để vòng PI phải bù) — không phải mô hình xe.
        s.step(10, rx, FirmwareInputs(speed_valid=True, speed_mm_s=measured))
        measured = s.fw.speed_ref_mm_s * 4 // 5 if s.fw.speed_ref_mm_s >= 0 else -((-s.fw.speed_ref_mm_s) * 4 // 5)
    for k in range(25):
        rx = _cmd(SESSION_A, seq, -100, -2000) if k % 3 == 0 else b""
        if rx:
            seq += 1
        s.step(10, rx, FirmwareInputs(speed_valid=True, speed_mm_s=measured))
        measured = -((-s.fw.speed_ref_mm_s) * 4 // 5) if s.fw.speed_ref_mm_s < 0 else s.fw.speed_ref_mm_s * 4 // 5
    s.step(10, _cmd(SESSION_A, seq, -100, 0, validity=5000))  # validity bị kẹp về max_validity_ms
    s.idle(260, FirmwareInputs(speed_valid=False))            # mất encoder: feedforward hở, cờ loop = 0
    return s.to_dict()


def _scenario_overrun_wrap() -> dict:
    s = _Script("clock_wrap_and_loop_overrun",
                "millis() quay vòng qua 2^32 giữa lúc đang chạy; rồi một khoảng hở 150 ms giữa hai chu kỳ → "
                "LOOP_OVERRUN; CLEAR_FAULT → DISARMED.", boot_ms=0xFFFFFFFF - 205, reset_reason=ResetReason.WATCHDOG)
    s.step(10, _hello(SESSION_A, 40))
    s.idle(100)
    s.step(10, _req(SESSION_A, 41, Action.ARM))
    seq = 42
    for _ in range(12):
        s.step(10, _cmd(SESSION_A, seq, 60, 50))
        seq += 1
        s.step(10)
    s.step(150)                                              # vòng điều khiển bị treo 150 ms
    s.step(10, _req(SESSION_A, seq, Action.CLEAR_FAULT))
    seq += 1
    s.idle(30)
    return s.to_dict()


def _scenario_garbage_link() -> dict:
    s = _Script("garbage_on_link",
                "Rác, khung quá dài, sai CRC, sai phiên bản xen giữa các khung hợp lệ: bo vẫn nhận khung hợp lệ và "
                "telemetry đếm rx_errors.")
    rng = random.Random(7)
    s.step(10, bytes(rng.randrange(1, 256) for _ in range(30)) + b"\x00" + _hello(SESSION_A, 1))
    s.idle(100)
    raw = encode_message(Request(SESSION_A, 2, int(Action.ARM)))
    s.step(10, bytes([0x55]) * 120 + b"\x00" + cobs_encode(raw + b"\x00\x00") + b"\x00" + _req(SESSION_A, 2, Action.ARM))
    s.step(10, frame_from_raw(bytes([9]) + raw[1:]) + _cmd(SESSION_A, 3, 40, 0))
    s.idle(100)
    return s.to_dict()


def _scenario_disarm_hello_keep_latches() -> dict:
    s = _Script("disarm_and_hello_keep_boot_and_fault",
                "DISARM và HELLO trong BOOT không rút ngắn BOOT; DISARM khi đang chạy → DISARMED (HOST_DISARM), dốc "
                "về 0 theo stop_decel, giữ lái tới khi dừng rồi trả về giữa, lệnh sau đó bị từ chối; DISARM và HELLO "
                "phiên mới trong FAULT KHÔNG xóa lỗi (chỉ CLEAR_FAULT khi hết nguyên nhân mới xóa).",
                config=replace(VECTOR_CONFIG, max_accel_mm_s2=2000, max_steer_rate_mrad_s=6000))
    s.step(10, _hello(SESSION_A, 1))
    s.step(10, _req(SESSION_A, 2, Action.DISARM))            # BOOT: ACK OK, vẫn BOOT
    s.step(10, _hello(SESSION_B, 10))                        # HELLO phiên mới trong BOOT: vẫn BOOT
    s.idle(70)                                               # t=100: hết BOOT
    s.step(10, _req(SESSION_B, 11, Action.ARM))
    seq = 12
    for _ in range(4):
        s.step(10, _cmd(SESSION_B, seq, 120, 200))
        seq += 1
        s.idle(20)
    s.step(10, _req(SESSION_B, seq, Action.DISARM))          # đang RUNNING → DISARMED, dốc về 0
    seq += 1
    s.idle(40)
    s.step(10, _cmd(SESSION_B, seq, 120, 200))               # BAD_STATE: lệnh không được nhớ
    seq += 1
    s.idle(250)
    s.step(10, _req(SESSION_B, seq, Action.ARM))
    seq += 1
    s.step(10, _cmd(SESSION_B, seq, 120, 200))
    seq += 1
    s.idle(30)
    s.step(10, inputs=FirmwareInputs(estop=True))            # FAULT ESTOP
    s.step(10, _req(SESSION_B, seq, Action.DISARM))          # FAULT giữ nguyên
    seq += 1
    s.step(10, _hello(SESSION_A, 500))                       # HELLO phiên mới trong FAULT: FAULT giữ nguyên
    s.step(10, inputs=FirmwareInputs())                      # nhả nút: vẫn FAULT
    s.step(10, _req(SESSION_A, 501, Action.DISARM))
    s.step(10, _req(SESSION_A, 502, Action.ARM))             # FAULT_ACTIVE
    s.step(10, _req(SESSION_A, 503, Action.CLEAR_FAULT))     # → DISARMED
    s.step(10, _cmd(SESSION_A, 504, 120, 200))               # BAD_STATE
    s.idle(30)
    return s.to_dict()


def _scenario_telemetry_period() -> dict:
    s = _Script("telemetry_period_not_multiple_of_tick",
                "HELLO xin chu kỳ 25 ms (không là bội của chu kỳ 10 ms): khoảng cách mẫu xen kẽ 30/20 ms, trung bình "
                "đúng 25 ms như HELLO_ACK báo; chu kỳ điều khiển trễ (40, 70 ms) → mỗi step tối đa một mẫu, bắt nhịp "
                "lại, không gửi dồn.")
    s.step(10, _hello(SESSION_A, 1, 25))
    s.idle(200)
    s.step(40)
    s.step(70)
    s.idle(100)
    return s.to_dict()


def _scenario_tx_overflow() -> dict:
    s = _Script("tx_overflow_gap",
                "Bộ đệm gửi nhỏ (tx_capacity 100 byte): HELLO_ACK + ACK + telemetry trong cùng một chu kỳ không vừa; "
                "khung bị bỏ vẫn tiêu một số thứ tự (laptop thấy khoảng hở), tx_overflow đếm từng khung bị bỏ.",
                config=replace(VECTOR_CONFIG, tx_capacity=100))
    s.step(10, _hello(SESSION_A, 1) + _req(SESSION_A, 2, Action.PING))   # 40 + 17 byte; telemetry 55 → bỏ
    s.idle(100)
    s.step(10, _req(SESSION_A, 3, Action.ARM) + _req(SESSION_A, 4, Action.PING) + _req(SESSION_A, 5, Action.PING))
    s.idle(100)
    s.step(10, b"".join(_req(SESSION_A, seq, Action.PING) for seq in range(6, 13)))  # 7 ACK: bỏ bớt
    s.idle(100)
    return s.to_dict()


def _scenario_effort_cap_stall() -> dict:
    s = _Script("effort_cap_and_stall",
                "Trần effort mặc định (250 ‰) và kiểm STALL: không encoder, lệnh 300 mm/s → feedforward 700 ‰ bị kẹp ở "
                "250 ‰; encoder hợp lệ nhưng kẹt 0 → effort ở trần, sau stall_timeout_ms → FAULT STALL (detail = "
                "|effort|), effort 0 ngay, lệnh sau bị FAULT_ACTIVE; CLEAR_FAULT, ARM, encoder đảo dấu → STALL lần "
                "nữa.",
                config=replace(VECTOR_CONFIG, max_effort_permille=250, max_accel_mm_s2=3000, stall_timeout_ms=200))
    s.step(10, _hello(SESSION_A, 1))
    s.idle(100)
    s.step(10, _req(SESSION_A, 2, Action.ARM))
    seq = 3
    for _ in range(4):                                       # không encoder: mạch hở, effort kẹp ở trần
        s.step(10, _cmd(SESSION_A, seq, 300, 0))
        seq += 1
        s.idle(40)
    stuck = FirmwareInputs(speed_valid=True, speed_mm_s=0)   # encoder kẹt 0 nhưng cờ hợp lệ
    for _ in range(6):                                       # STALL sau 200 ms; lệnh sau đó → FAULT_ACTIVE
        s.step(10, _cmd(SESSION_A, seq, 300, 0), stuck)
        seq += 1
        s.idle(40)
    s.step(10, _req(SESSION_A, seq, Action.CLEAR_FAULT))    # → DISARMED
    seq += 1
    s.step(10, _req(SESSION_A, seq, Action.ARM))
    seq += 1
    inverted = FirmwareInputs(speed_valid=True, speed_mm_s=-150)   # encoder đảo dấu: mục tiêu tiến, số đo lùi
    for _ in range(8):
        s.step(10, _cmd(SESSION_A, seq, 300, 0), inverted)
        seq += 1
        s.idle(40)
    return s.to_dict()


def build_vectors() -> dict:
    crc_inputs = [b"123456789", b"", b"\x00", b"\xff\xff", bytes(range(64))]
    cobs_inputs = [b"", b"\x00", b"\x00\x00", b"\x11\x22\x00\x33", b"\x11\x22\x33\x44", b"\x11\x00\x00\x00",
                   bytes(range(1, 255)), bytes(range(0, 255)), bytes(range(1, 256)), bytes(range(2, 256)) + b"\x00",
                   bytes(range(3, 256)) + b"\x00\x01"]
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "generator": "python -m autopark.transport.vectors --write",
        "note": "Sinh tự động từ autopark/transport/{protocol,firmware_model}.py. Không sửa bằng tay.",
        "crc16": [{"data": data.hex(), "crc": crc16_ccitt_false(data)} for data in crc_inputs],
        "cobs": [{"decoded": data.hex(), "encoded": cobs_encode(data).hex()} for data in cobs_inputs],
        "messages": _message_vectors(),
        "streams_to_device": _stream_vectors(),
        "scenarios": [_scenario_boot_run_timeout(), _scenario_sequence_session(), _scenario_estop(),
                      _scenario_limits_reverse_loop(), _scenario_overrun_wrap(), _scenario_garbage_link(),
                      _scenario_disarm_hello_keep_latches(), _scenario_telemetry_period(), _scenario_tx_overflow(),
                      _scenario_effort_cap_stall()],
    }


def dumps(vectors: dict) -> str:
    """JSON ASCII; mỗi phần tử danh sách (và mỗi bước kịch bản) nằm trên một dòng để diff dễ đọc."""
    def compact(value) -> str:
        return json.dumps(value, ensure_ascii=True, separators=(", ", ": "))

    lines = ["{"]
    items = list(vectors.items())
    for i, (key, value) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if not isinstance(value, list):
            lines.append(f" {compact(key)}: {compact(value)}{comma}")
            continue
        lines.append(f" {compact(key)}: [")
        for j, item in enumerate(value):
            item_comma = "," if j < len(value) - 1 else ""
            if isinstance(item, dict) and "steps" in item:
                head = compact({k: v for k, v in item.items() if k != "steps"})
                lines.append("  " + head[:-1] + ', "steps": [')
                steps = item["steps"]
                lines.extend("   " + compact(step) + ("," if k < len(steps) - 1 else "") for k, step in enumerate(steps))
                lines.append("  ]}" + item_comma)
            else:
                lines.append("  " + compact(item) + item_comma)
        lines.append(" ]" + comma)
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = dumps(build_vectors())
    if args.write:
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.path} ({len(text)} bytes)")
        return 0
    current = args.path.read_text(encoding="utf-8") if args.path.exists() else ""
    if current != text:
        print(f"{args.path} is out of date: run with --write", file=sys.stderr)
        return 1
    print(f"{args.path} is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
