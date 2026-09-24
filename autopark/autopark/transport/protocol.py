"""Giao thức laptop ↔ ESP32-S3 phiên bản 1: mã hóa, giải mã và bộ tách khung (đặc tả: docs/GIAO_THUC_XE.md).

Khung trên dây: ``COBS(thông điệp ‖ CRC) ‖ 0x00``. CRC là CRC-16/CCITT-FALSE (đa thức 0x1021, khởi tạo 0xFFFF,
không đảo bit, không XOR cuối) tính trên toàn bộ thông điệp, ghi little-endian. Mọi số nguyên trong thông điệp là
little-endian. Mỗi thông điệp bắt đầu bằng phần đầu 8 byte ``version u8, type u8, session_id u32, sequence u16``;
phần thân có độ dài CỐ ĐỊNH theo loại (thừa hay thiếu một byte đều bị loại).

Mọi trường trên dây là số nguyên theo đơn vị đã ghi (mm/s, mrad, ms, mV...); đổi sang m/s, rad, giây là việc của
`vehicle_io`, dùng chung một bộ hàm cho cả nhánh mô phỏng và nhánh phần cứng. Mô-đun này là Python thuần (không cần
numpy) và là bản tham chiếu mà `firmware/esp32_vehicle/src/core/protocol.cpp` phải khớp từng byte; vector mẫu
chung nằm ở `firmware/esp32_vehicle/test/vectors.json` (sinh bởi `autopark.transport.vectors`).

Bộ tách khung `FrameParser` chịu được rác, khung cụt, khung quá dài, sai CRC, sai phiên bản, loại lạ và sai độ
dài: không bao giờ ném lỗi khi nhận byte, mỗi loại lỗi có một bộ đếm riêng, và chỉ trả ra thông điệp đã qua đủ các
kiểm tra. CRC-16 không bảo đảm tuyệt đối: một khung bị hỏng ngẫu nhiên vẫn có xác suất cỡ 1/65536 lọt qua CRC; các
kiểm tra phiên bản/loại/độ dài và kiểm tra phiên/số thứ tự ở tầng trên giảm thêm khả năng này nhưng không về 0.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from enum import IntEnum, IntFlag
import struct
from typing import Iterable, Union

PROTOCOL_VERSION = 1
HEADER = struct.Struct("<BBIH")          # version, type, session_id, sequence
HEADER_SIZE = HEADER.size                # 8
CRC_SIZE = 2
MAX_ENCODED_SIZE = 80                    # byte COBS tối đa của một khung (không kể 0x00); khung dài nhất thật: 54
N_TOF = 4
COMMAND_FLAG_ENABLE = 0x01
NO_COMMAND_AGE = 0xFFFF                  # cmd_age_ms khi phiên hiện tại chưa có lệnh nào được nhận


class MsgType(IntEnum):
    HELLO = 0x01        # laptop → bo: mở/đặt lại phiên
    REQUEST = 0x02      # laptop → bo: ARM / DISARM / CLEAR_FAULT / PING
    COMMAND = 0x03      # laptop → bo: lệnh chuyển động có thời hạn
    HELLO_ACK = 0x81    # bo → laptop: nhận phiên, báo phiên bản firmware, boot_id và giới hạn
    ACK = 0x82          # bo → laptop: kết quả một REQUEST, hoặc lý do từ chối một COMMAND/REQUEST
    TELEMETRY = 0x83    # bo → laptop: số đo + trạng thái, theo chu kỳ
    FAULT = 0x84        # bo → laptop: một lỗi vừa bị chốt


HOST_TO_DEVICE = frozenset({MsgType.HELLO, MsgType.REQUEST, MsgType.COMMAND})
DEVICE_TO_HOST = frozenset({MsgType.HELLO_ACK, MsgType.ACK, MsgType.TELEMETRY, MsgType.FAULT})


class State(IntEnum):
    BOOT = 0
    DISARMED = 1
    ARMED = 2
    RUNNING = 3
    FAULT = 4


class Fault(IntEnum):
    NONE = 0
    ESTOP = 1            # ngõ vào E-stop tích cực
    LOOP_OVERRUN = 2     # hai lần gọi vòng điều khiển cách nhau quá max_tick_gap_ms
    SUPPLY_LOW = 3       # điện áp đo được dưới ngưỡng (ngưỡng CHƯA CHỐT, mặc định tắt)
    FEEDBACK_LOST = 4    # đang chạy mà mất phản hồi tốc độ (chỉ khi cấu hình bắt buộc phản hồi)
    STALL = 5            # vòng kín: |effort| ≥ stall_effort mà số đo không đi theo chiều mục tiêu quá stall_timeout_ms


class StopReason(IntEnum):
    NONE = 0
    BOOT = 1
    HOST_DISARM = 2
    COMMAND_TIMEOUT = 3
    LINK_TIMEOUT = 4
    NEW_SESSION = 5
    ENABLE_CLEARED = 6
    FAULT = 7


class Result(IntEnum):
    OK = 0
    NO_SESSION = 1       # bo chưa có phiên (vừa khởi động lại): laptop phải gửi HELLO
    WRONG_SESSION = 2
    DUPLICATE = 3
    OUT_OF_ORDER = 4     # số thứ tự cũ hơn số đã nhận (tính vòng uint16)
    BAD_STATE = 5        # ví dụ COMMAND khi chưa ARM
    FAULT_ACTIVE = 6
    ESTOP_ACTIVE = 7
    BAD_FIELD = 8        # validity 0, bit cờ dự trữ, action lạ, session 0 trong HELLO
    NOT_READY = 9        # còn trong BOOT


class Action(IntEnum):
    ARM = 1
    DISARM = 2
    CLEAR_FAULT = 3
    PING = 4


class ResetReason(IntEnum):
    UNKNOWN = 0
    POWER_ON = 1
    SOFTWARE = 2
    WATCHDOG = 3
    BROWNOUT = 4
    OTHER = 5


class TelemetryFlag(IntFlag):
    ESTOP_INPUT = 0x01
    LINK_OK = 0x02
    CMD_ACTIVE = 0x04
    SPEED_VALID = 0x08
    STEER_VALID = 0x10
    IMU_VALID = 0x20
    SUPPLY_VALID = 0x40
    SPEED_LOOP_CLOSED = 0x80


class ProtocolError(ValueError):
    """A byte string is not a valid v1 message. `kind` is one of FrameParser's error counters."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


# ---- checksums and byte stuffing ------------------------------------------------------------------------------
def crc16_ccitt_false(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE; giá trị kiểm tra chuẩn: crc16_ccitt_false(b"123456789") == 0x29B1."""
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    """COBS chuẩn (Cheshire & Baker 1999), cùng kết quả với bộ mã tham chiếu: khối 254 byte khác 0 ở cuối dữ liệu
    không kèm mã 0x01 thừa. Kết quả không chứa byte 0; không kèm dấu phân cách."""
    out = bytearray(b"\x00")
    code_index: int | None = 0
    code = 1
    last = len(data) - 1
    for i, byte in enumerate(data):
        if byte:
            out.append(byte)
            code += 1
        if not byte or code == 0xFF:
            out[code_index] = code
            code = 1
            if not byte or i < last:
                code_index = len(out)
                out.append(0)
            else:
                code_index = None
    if code_index is not None:
        out[code_index] = code
    return bytes(out)


def cobs_decode(encoded: bytes) -> bytes:
    """Giải COBS chặt: rỗng, byte 0 bên trong, hoặc khối chạy quá cuối đều là lỗi (ProtocolError kind 'cobs')."""
    if not encoded:
        raise ProtocolError("cobs", "empty COBS block")
    out = bytearray()
    i, n = 0, len(encoded)
    while i < n:
        code = encoded[i]
        if code == 0:
            raise ProtocolError("cobs", "zero byte inside a COBS frame")
        end = i + code
        if end > n:
            raise ProtocolError("cobs", "COBS block runs past the end of the frame")
        block = encoded[i + 1:end]
        if 0 in block:
            raise ProtocolError("cobs", "zero byte inside a COBS frame")
        out += block
        i = end
        if code != 0xFF and i < n:
            out.append(0)
    return bytes(out)


# ---- messages -------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Hello:
    session_id: int
    sequence: int
    telemetry_period_ms: int = 0        # 0 = để firmware dùng mặc định; firmware kẹp vào [min, max]
    host_time_ms: int = 0               # chỉ để ghi log/đối chiếu, firmware không dùng
    TYPE = MsgType.HELLO
    BODY = struct.Struct("<HI")


@dataclass(frozen=True)
class Request:
    session_id: int
    sequence: int
    action: int
    TYPE = MsgType.REQUEST
    BODY = struct.Struct("<B")


@dataclass(frozen=True)
class Command:
    session_id: int
    sequence: int
    validity_ms: int                    # thời hạn của lệnh tính từ lúc bo nhận; 0 bị từ chối
    flags: int                          # bit0 ENABLE; các bit khác dự trữ, phải = 0
    speed_mm_s: int                     # tốc độ mục tiêu có dấu (âm = lùi)
    steer_mrad: int                     # góc lái mục tiêu tương đương (dương = rẽ trái khi tiến)
    TYPE = MsgType.COMMAND
    BODY = struct.Struct("<HBhh")

    @property
    def enable(self) -> bool:
        return bool(self.flags & COMMAND_FLAG_ENABLE)


@dataclass(frozen=True)
class Limits:
    max_speed_mm_s: int
    max_steer_mrad: int
    max_steer_rate_mrad_s: int
    max_accel_mm_s2: int
    max_decel_mm_s2: int
    stop_decel_mm_s2: int
    max_validity_ms: int
    link_timeout_ms: int
    FORMAT = struct.Struct("<8H")

    def values(self) -> tuple[int, ...]:
        return tuple(getattr(self, f.name) for f in fields(self))


@dataclass(frozen=True)
class HelloAck:
    session_id: int
    sequence: int
    hello_sequence: int                 # số thứ tự của HELLO được trả lời
    fw_major: int
    fw_minor: int
    boot_id: int                        # ngẫu nhiên mỗi lần khởi động: đổi = bo đã khởi động lại
    reset_reason: int
    state: int
    telemetry_period_ms: int            # chu kỳ telemetry bo thực sự dùng
    limits: Limits
    TYPE = MsgType.HELLO_ACK
    BODY = struct.Struct("<HBBIBBH8H")


@dataclass(frozen=True)
class Ack:
    session_id: int                     # lặp lại session_id của thông điệp được trả lời
    sequence: int
    acked_type: int
    acked_sequence: int
    result: int
    state: int
    fault: int
    TYPE = MsgType.ACK
    BODY = struct.Struct("<BHBBB")


@dataclass(frozen=True)
class TelemetryMsg:
    session_id: int
    sequence: int
    sample_time_ms: int                 # đồng hồ bo (millis) lúc lấy mẫu
    state: int
    fault: int                          # lỗi đang chốt (0 = không có)
    stop_reason: int                    # lý do gần nhất đầu ra về trung tính
    flags: int                          # TelemetryFlag
    last_cmd_seq: int                   # số thứ tự COMMAND gần nhất được nhận
    cmd_age_ms: int                     # tuổi của COMMAND đó; 0xFFFF = chưa có lệnh trong phiên
    speed_measured_mm_s: int            # 0 khi SPEED_VALID = 0
    steer_measured_mrad: int            # 0 khi STEER_VALID = 0
    speed_ref_mm_s: int                 # mục tiêu sau giới hạn + dốc (đang đưa vào vòng tốc độ)
    steer_ref_mrad: int
    effort_permille: int                # đầu ra chuẩn hóa cho ESC, -1000..1000 (ánh xạ xung CHƯA CHỐT)
    gyro_z_mrad_s: int
    accel_x_mm_s2: int
    accel_y_mm_s2: int
    tof_valid_mask: int                 # bit i = tof_mm[i] hợp lệ
    tof_mm: tuple[int, int, int, int]   # 0 khi không hợp lệ; KHÔNG BAO GIỜ dùng giá trị lớn để báo "không thấy"
    supply_mv: int                      # 0 khi SUPPLY_VALID = 0
    rx_errors: int                      # tổng lỗi bộ tách khung phía bo (bão hòa 65535)
    rejects: int                        # tổng thông điệp bị từ chối (bão hòa 65535)
    TYPE = MsgType.TELEMETRY
    BODY = struct.Struct("<IBBBBHH8hB4HHHH")


@dataclass(frozen=True)
class FaultMsg:
    session_id: int
    sequence: int
    fault: int
    state: int
    time_ms: int
    detail: int                         # LOOP_OVERRUN: khoảng hở ms; SUPPLY_LOW: mV; còn lại 0
    TYPE = MsgType.FAULT
    BODY = struct.Struct("<BBIH")


Message = Union[Hello, Request, Command, HelloAck, Ack, TelemetryMsg, FaultMsg]
MESSAGE_CLASSES = {cls.TYPE: cls for cls in (Hello, Request, Command, HelloAck, Ack, TelemetryMsg, FaultMsg)}
MESSAGE_SIZES = {t: HEADER_SIZE + cls.BODY.size for t, cls in MESSAGE_CLASSES.items()}


def _body_values(msg: Message) -> tuple:
    if isinstance(msg, HelloAck):
        return (msg.hello_sequence, msg.fw_major, msg.fw_minor, msg.boot_id, msg.reset_reason, msg.state,
                msg.telemetry_period_ms) + msg.limits.values()
    if isinstance(msg, TelemetryMsg):
        if len(msg.tof_mm) != N_TOF:
            raise ValueError(f"tof_mm needs {N_TOF} values")
        return (msg.sample_time_ms, msg.state, msg.fault, msg.stop_reason, msg.flags, msg.last_cmd_seq,
                msg.cmd_age_ms, msg.speed_measured_mm_s, msg.steer_measured_mrad, msg.speed_ref_mm_s,
                msg.steer_ref_mrad, msg.effort_permille, msg.gyro_z_mrad_s, msg.accel_x_mm_s2, msg.accel_y_mm_s2,
                msg.tof_valid_mask, *msg.tof_mm, msg.supply_mv, msg.rx_errors, msg.rejects)
    return tuple(getattr(msg, f.name) for f in fields(msg))[2:]


def encode_message(msg: Message) -> bytes:
    """Thông điệp → byte (chưa CRC/COBS). Trường ngoài miền của kiểu số nguyên → ValueError, không cắt ngầm."""
    try:
        return HEADER.pack(PROTOCOL_VERSION, int(msg.TYPE), msg.session_id, msg.sequence) + msg.BODY.pack(*_body_values(msg))
    except struct.error as exc:
        raise ValueError(f"{type(msg).__name__}: field out of range ({exc})") from exc


def decode_message(raw: bytes, accept_types: Iterable[int] | None = None) -> Message:
    """Byte (đã bỏ CRC) → thông điệp. Lỗi → ProtocolError với kind 'short' | 'version' | 'type' | 'length'."""
    if len(raw) < HEADER_SIZE:
        raise ProtocolError("short", f"message shorter than the {HEADER_SIZE}-byte header")
    version, msg_type, session_id, sequence = HEADER.unpack_from(raw)
    if version != PROTOCOL_VERSION:
        raise ProtocolError("version", f"protocol version {version}, expected {PROTOCOL_VERSION}")
    allowed = MESSAGE_CLASSES.keys() if accept_types is None else accept_types
    if msg_type not in MESSAGE_CLASSES or msg_type not in allowed:
        raise ProtocolError("type", f"unexpected message type 0x{msg_type:02x}")
    cls = MESSAGE_CLASSES[MsgType(msg_type)]
    if len(raw) != MESSAGE_SIZES[cls.TYPE]:
        raise ProtocolError("length", f"{cls.__name__}: {len(raw)} bytes, expected {MESSAGE_SIZES[cls.TYPE]}")
    values = cls.BODY.unpack_from(raw, HEADER_SIZE)
    if cls is HelloAck:
        return HelloAck(session_id, sequence, *values[:7], limits=Limits(*values[7:]))
    if cls is TelemetryMsg:
        head, tof, tail = values[:16], tuple(values[16:16 + N_TOF]), values[16 + N_TOF:]
        return TelemetryMsg(session_id, sequence, *head, tof, *tail)
    return cls(session_id, sequence, *values)


def frame_from_raw(raw: bytes) -> bytes:
    """Byte thông điệp → khung trên dây (thêm CRC little-endian, nhồi COBS, thêm 0x00)."""
    crc = crc16_ccitt_false(raw)
    return cobs_encode(raw + bytes((crc & 0xFF, crc >> 8))) + b"\x00"


def encode_frame(msg: Message) -> bytes:
    return frame_from_raw(encode_message(msg))


def raw_from_encoded(encoded: bytes) -> bytes:
    """Một khung COBS (không có 0x00) → byte thông điệp đã kiểm CRC. Lỗi → ProtocolError('cobs'|'short'|'crc')."""
    decoded = cobs_decode(encoded)
    if len(decoded) < HEADER_SIZE + CRC_SIZE:
        raise ProtocolError("short", f"frame of {len(decoded)} bytes is shorter than header + CRC")
    raw, crc = decoded[:-CRC_SIZE], decoded[-CRC_SIZE] | (decoded[-1] << 8)
    if crc16_ccitt_false(raw) != crc:
        raise ProtocolError("crc", "CRC mismatch")
    return raw


ERROR_KINDS = ("cobs", "short", "crc", "version", "type", "length", "oversize")


@dataclass
class ParserStats:
    frames: int = 0          # khung đã kết thúc bằng 0x00 và có nội dung (kể cả khung lỗi)
    messages: int = 0        # thông điệp hợp lệ đã trả ra
    empty: int = 0           # 0x00 liên tiếp: dùng để đồng bộ, không phải lỗi
    cobs: int = 0
    short: int = 0
    crc: int = 0
    version: int = 0
    type: int = 0
    length: int = 0
    oversize: int = 0

    @property
    def errors(self) -> int:
        return sum(getattr(self, kind) for kind in ERROR_KINDS)

    def as_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in ("frames", "messages", "empty") + ERROR_KINDS}


class FrameParser:
    """Tách khung từ luồng byte. Byte 0x00 kết thúc một khung; khung dài hơn `max_encoded` byte bị bỏ đến 0x00 kế
    tiếp và đếm một lỗi `oversize`. Mở cổng giữa dòng thì khung dở đầu tiên thành một lỗi (thường là cobs/crc);
    khung kế tiếp đọc bình thường. `accept_types` giới hạn loại được nhận (phía bo chỉ nhận HOST_TO_DEVICE)."""

    def __init__(self, accept_types: Iterable[int] | None = None, max_encoded: int = MAX_ENCODED_SIZE):
        if max_encoded < 4:
            raise ValueError("max_encoded too small")
        self.accept_types = frozenset(accept_types) if accept_types is not None else None
        self.max_encoded = max_encoded
        self.buffer = bytearray()
        self.overflow = False
        self.stats = ParserStats()

    def reset(self) -> None:
        """Bỏ khung dở (ví dụ khi mở lại cổng); giữ nguyên bộ đếm."""
        self.buffer.clear()
        self.overflow = False

    def feed(self, data: bytes) -> list[Message]:
        out: list[Message] = []
        for byte in bytes(data):
            if byte == 0:
                if self.overflow:
                    self.stats.oversize += 1
                    self.overflow = False
                    self.buffer.clear()
                    continue
                if not self.buffer:
                    self.stats.empty += 1
                    continue
                self.stats.frames += 1
                encoded = bytes(self.buffer)
                self.buffer.clear()
                try:
                    msg = decode_message(raw_from_encoded(encoded), self.accept_types)
                except ProtocolError as exc:
                    setattr(self.stats, exc.kind, getattr(self.stats, exc.kind) + 1)
                    continue
                self.stats.messages += 1
                out.append(msg)
                continue
            if self.overflow:
                continue
            if len(self.buffer) >= self.max_encoded:
                self.overflow = True
                self.buffer.clear()
                continue
            self.buffer.append(byte)
        return out


def message_fields(msg: Message) -> dict:
    """Trường của thông điệp dạng dict phẳng (limits trải ra, tof_mm là list) — dùng cho vector mẫu và log."""
    out: dict = {}
    for f in fields(msg):
        value = getattr(msg, f.name)
        if isinstance(value, Limits):
            out.update({lf.name: getattr(value, lf.name) for lf in fields(value)})
        elif isinstance(value, tuple):
            out[f.name] = list(value)
        else:
            out[f.name] = int(value)
    return out


def message_from_fields(msg_type: int, values: dict) -> Message:
    """Ngược của `message_fields`."""
    cls = MESSAGE_CLASSES[MsgType(msg_type)]
    if cls is HelloAck:
        limit_names = [f.name for f in fields(Limits)]
        base = {k: v for k, v in values.items() if k not in limit_names}
        return HelloAck(**base, limits=Limits(**{k: values[k] for k in limit_names}))
    if cls is TelemetryMsg:
        return TelemetryMsg(**{**values, "tof_mm": tuple(values["tof_mm"])})
    return cls(**values)
