"""Giao thức SLAMTEC RPLIDAR cho C1 ở chế độ quét Standard: gói lệnh, mô tả phản hồi, node 5 byte, gom vòng quét.

Không có I/O ở đây; mọi hàm nhận bytes và trả cấu trúc, để test được bằng luồng byte giả và để driver
(`rplidar_c1.py`) chỉ lo cổng nối tiếp. Đối chiếu với `sl_lidar_cmd.h` của SDK chính thức và đã kiểm chứng
trên thiết bị của dự án ngày 22/09/2026 (model 0x41, firmware 1.2):

- Lệnh: `A5 <cmd>`; lệnh có payload: `A5 <cmd> <len> <payload> <xor của mọi byte trước>`.
- Mô tả phản hồi 7 byte: `A5 5A`, 4 byte little-endian gồm 30 bit độ dài và 2 bit chế độ gửi
  (0 một gói, 1 nhiều gói), 1 byte kiểu dữ liệu.
- Node đo 5 byte: byte 0 bit 0 = cờ bắt đầu vòng S, bit 1 = đảo của S, 6 bit trên = chất lượng; byte 1 bit 0
  luôn 1, 7 bit trên = phần thấp của góc; byte 2 = phần cao của góc; byte 3–4 = khoảng cách. Góc = giá trị / 64
  (độ), khoảng cách = giá trị / 4 (mm). Khoảng cách 0 là "không có phản hồi" (trên thiết bị này luôn đi kèm
  chất lượng 0). Góc của thiết bị tăng theo chiều kim đồng hồ, 0° là phía trước theo datasheet; dự án dùng
  góc dương ngược chiều kim đồng hồ nên `revolution_to_scan` đổi dấu (tham số `mirror` giữ dấu thiết bị nếu
  phép đo trên bàn nói ngược).
- Giá trị ngoài 0,05–12 m vẫn được thiết bị xuất nhưng datasheet ghi "chỉ để tham khảo"; ở đây giữ nguyên,
  lớp dùng dữ liệu tự quyết định.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import struct

import numpy as np

from autopark.domain.sensors import LidarScan, SourceStamp

SYNC_BYTE = 0xA5
SYNC_BYTE2 = 0x5A
CMD_STOP = 0x25
CMD_RESET = 0x40
CMD_SCAN = 0x20
CMD_GET_INFO = 0x50
CMD_GET_HEALTH = 0x52
CMD_GET_LIDAR_CONF = 0x84
CONF_SCAN_MODE_COUNT = 0x70
CONF_SCAN_MODE_US_PER_SAMPLE = 0x71
CONF_SCAN_MODE_MAX_DISTANCE = 0x74
CONF_SCAN_MODE_ANS_TYPE = 0x75
CONF_SCAN_MODE_TYPICAL = 0x7C
CONF_SCAN_MODE_NAME = 0x7F
ANS_DEVICE_INFO = 0x04
ANS_DEVICE_HEALTH = 0x06
ANS_LIDAR_CONF = 0x20
ANS_MEASUREMENT = 0x81
DESCRIPTOR_LENGTH = 7
NODE_LENGTH = 5
HEALTH_NAMES = {0: "OK", 1: "WARNING", 2: "ERROR"}
MAX_NODES_PER_REVOLUTION = 4096       # a revolution longer than this means the start flag was lost


class ProtocolError(RuntimeError):
    """The device answered with something the protocol does not allow."""


def request(command: int, payload: bytes = b"") -> bytes:
    if not 0 <= command <= 0xFF:
        raise ValueError("command must be one byte")
    if not payload:
        return bytes([SYNC_BYTE, command])
    if len(payload) > 0xFF:
        raise ValueError("payload too long")
    packet = bytes([SYNC_BYTE, command, len(payload)]) + payload
    checksum = 0
    for byte in packet:
        checksum ^= byte
    return packet + bytes([checksum])


def conf_request(conf_type: int, mode: int | None = None) -> bytes:
    payload = struct.pack("<I", conf_type) + (b"" if mode is None else struct.pack("<H", mode))
    return request(CMD_GET_LIDAR_CONF, payload)


@dataclass(frozen=True)
class Descriptor:
    length: int
    send_mode: int        # 0 = one response, 1 = a stream of responses
    data_type: int


def parse_descriptor(raw: bytes) -> Descriptor:
    if len(raw) != DESCRIPTOR_LENGTH or raw[0] != SYNC_BYTE or raw[1] != SYNC_BYTE2:
        raise ProtocolError(f"bad response descriptor {bytes(raw).hex()}")
    value = struct.unpack("<I", raw[2:6])[0]
    return Descriptor(value & 0x3FFFFFFF, value >> 30, raw[6])


SCAN_DESCRIPTOR = Descriptor(NODE_LENGTH, 1, ANS_MEASUREMENT)


@dataclass(frozen=True)
class DeviceInfo:
    model: int
    firmware_major: int
    firmware_minor: int
    hardware: int
    serial: str

    @property
    def firmware(self) -> str:
        return f"{self.firmware_major}.{self.firmware_minor}"

    def to_dict(self) -> dict:
        return {"model": self.model, "model_hex": f"0x{self.model:02x}", "firmware": self.firmware,
                "hardware": self.hardware, "serial": self.serial}


def parse_device_info(body: bytes) -> DeviceInfo:
    if len(body) != 20:
        raise ProtocolError(f"device info must be 20 bytes, got {len(body)}")
    return DeviceInfo(body[0], body[2], body[1], body[3], bytes(body[4:20]).hex())


@dataclass(frozen=True)
class DeviceHealth:
    status: int
    error_code: int

    @property
    def name(self) -> str:
        return HEALTH_NAMES.get(self.status, f"UNKNOWN({self.status})")

    def to_dict(self) -> dict:
        return {"status": self.status, "name": self.name, "error_code": self.error_code}


def parse_device_health(body: bytes) -> DeviceHealth:
    if len(body) != 3:
        raise ProtocolError(f"device health must be 3 bytes, got {len(body)}")
    return DeviceHealth(body[0], struct.unpack("<H", body[1:3])[0])


def conf_payload(body: bytes, conf_type: int) -> bytes:
    """Strip the 4-byte echo of the configuration type; refuse an answer for another type."""
    if len(body) < 4 or struct.unpack("<I", body[:4])[0] != conf_type:
        raise ProtocolError(f"configuration answer does not echo type 0x{conf_type:02x}: {bytes(body).hex()}")
    return bytes(body[4:])


def conf_u16(body: bytes, conf_type: int) -> int:
    return struct.unpack("<H", conf_payload(body, conf_type)[:2])[0]


def conf_u32(body: bytes, conf_type: int) -> int:
    return struct.unpack("<I", conf_payload(body, conf_type)[:4])[0]


def conf_name(body: bytes, conf_type: int) -> str:
    return conf_payload(body, conf_type).split(b"\x00")[0].decode("ascii", errors="replace")


@dataclass(frozen=True)
class Node:
    start: bool
    quality: int
    angle_deg: float
    distance_mm: float

    @property
    def has_return(self) -> bool:
        return self.distance_mm > 0 and self.quality > 0


def decode_node(raw) -> Node | None:
    """5 bytes -> Node, or None when the two check bits say the bytes are not aligned to a node."""
    b0, b1, b2, b3, b4 = raw[0], raw[1], raw[2], raw[3], raw[4]
    start = b0 & 1
    if start == ((b0 >> 1) & 1) or (b1 & 1) != 1:
        return None
    angle_q6 = (b2 << 7) | (b1 >> 1)
    distance_q2 = (b4 << 8) | b3
    return Node(bool(start), b0 >> 2, angle_q6 / 64.0, distance_q2 / 4.0)


def encode_node(node: Node) -> bytes:
    """Inverse of decode_node, for tests and simulated devices."""
    angle_q6 = int(round(node.angle_deg * 64.0)) & 0x7FFF
    distance_q2 = int(round(node.distance_mm * 4.0)) & 0xFFFF
    start = 1 if node.start else 0
    b0 = ((node.quality & 0x3F) << 2) | ((1 - start) << 1) | start
    b1 = ((angle_q6 & 0x7F) << 1) | 1
    b2 = angle_q6 >> 7
    return bytes([b0, b1, b2, distance_q2 & 0xFF, distance_q2 >> 8])


class NodeDecoder:
    """Byte stream -> nodes. When the check bits fail the decoder skips ONE byte and tries again (resync)."""

    def __init__(self):
        self._buffer = bytearray()
        self.resync_bytes = 0
        self.nodes = 0

    def feed(self, data: bytes) -> list[Node]:
        self._buffer += data
        out: list[Node] = []
        buffer, i, n = self._buffer, 0, len(self._buffer)
        while i + NODE_LENGTH <= n:
            node = decode_node(buffer[i:i + NODE_LENGTH])
            if node is None:
                self.resync_bytes += 1
                i += 1
                continue
            out.append(node)
            i += NODE_LENGTH
        del buffer[:i]
        self.nodes += len(out)
        return out


@dataclass
class Revolution:
    nodes: list[Node]
    t_first: float        # session time when the first node arrived
    t_last: float         # session time when the last node arrived

    def __len__(self) -> int:
        return len(self.nodes)


class RevolutionAssembler:
    """Groups nodes into revolutions delimited by the start flag. Nodes before the first flag are discarded.

    The device occasionally omits the flag (observed once in 130 revolutions on 2026-09-22): a revolution
    that already holds `min_nodes_for_wrap` nodes is therefore also closed when the angle wraps from ~360°
    back to ~0° (a backwards jump of more than `wrap_deg`). The threshold keeps the wrap that normally
    follows the flagged node (flagged at ~357°, next nodes from ~0°) from splitting a revolution.
    """

    def __init__(self, max_nodes: int = MAX_NODES_PER_REVOLUTION, min_nodes_for_wrap: int = 100, wrap_deg: float = 180.0):
        self.max_nodes = max_nodes
        self.min_nodes_for_wrap = min_nodes_for_wrap
        self.wrap_deg = wrap_deg
        self._nodes: list[Node] | None = None
        self._t_first = 0.0
        self._t_last = 0.0
        self.completed = 0
        self.dropped = 0          # revolutions discarded because the start flag never came
        self.discarded_nodes = 0  # nodes before the first start flag
        self.wrap_splits = 0      # revolutions closed by the angle wrap instead of the flag

    def push(self, node: Node, t: float) -> Revolution | None:
        completed = None
        wrapped = (self._nodes is not None and len(self._nodes) >= self.min_nodes_for_wrap
                   and node.angle_deg < self._nodes[-1].angle_deg - self.wrap_deg)
        if wrapped and not node.start:
            self.wrap_splits += 1
        if node.start or wrapped:
            if self._nodes:
                completed = Revolution(self._nodes, self._t_first, self._t_last)
                self.completed += 1
            self._nodes = [node]
            self._t_first = t
        elif self._nodes is None:
            self.discarded_nodes += 1
        else:
            self._nodes.append(node)
            if len(self._nodes) > self.max_nodes:
                self.dropped += 1
                self._nodes = None
        self._t_last = t
        return completed


def wrap_angle(angles: np.ndarray) -> np.ndarray:
    """Into [-pi, pi)."""
    return (angles + math.pi) % (2 * math.pi) - math.pi


def revolution_to_scan(revolution: Revolution, stamp: SourceStamp, *, mirror: bool = False) -> tuple[LidarScan, np.ndarray]:
    """One revolution -> (`LidarScan` in the project's yaw convention, per-beam quality uint8).

    Device angles grow clockwise, so they are negated; `mirror=True` keeps the device sign. A beam with
    distance 0 or quality 0 is NaN: no return, not evidence of free space.
    """
    angle_deg = np.array([node.angle_deg for node in revolution.nodes], dtype=np.float64)
    quality = np.array([node.quality for node in revolution.nodes], dtype=np.uint8)
    ranges = np.array([node.distance_mm for node in revolution.nodes], dtype=np.float64) / 1000.0
    ranges[(ranges <= 0) | (quality == 0)] = np.nan
    sign = 1.0 if mirror else -1.0
    angles = wrap_angle(np.radians(sign * angle_deg))
    return LidarScan(stamp, tuple(angles.tolist()), tuple(ranges.tolist())), quality


class ScanQueue:
    """Nodes in, completed revolutions out, preserving order across chunk boundaries."""

    def __init__(self):
        self.decoder = NodeDecoder()
        self.assembler = RevolutionAssembler()
        self.pending: deque[Revolution] = deque()

    def feed(self, data: bytes, t: float) -> int:
        added = 0
        for node in self.decoder.feed(data):
            revolution = self.assembler.push(node, t)
            if revolution is not None:
                self.pending.append(revolution)
                added += 1
        return added

    def pop(self) -> Revolution | None:
        return self.pending.popleft() if self.pending else None

    def stats(self) -> dict:
        return {"nodes": self.decoder.nodes, "resync_bytes": self.decoder.resync_bytes,
                "revolutions": self.assembler.completed, "dropped_revolutions": self.assembler.dropped,
                "discarded_nodes": self.assembler.discarded_nodes, "wrap_splits": self.assembler.wrap_splits}
