"""RPLIDAR C1 protocol and driver against a fake serial port: no hardware needed.

Byte strings marked "captured" were read from the project's own C1 on 2026-09-22 (COM4, model 0x41, fw 1.2).
"""
import math

import pytest

np = pytest.importorskip("numpy")

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.lidar import rplidar_protocol as proto  # noqa: E402
from autopark.lidar.rplidar_c1 import RplidarC1Source, ScanReadError  # noqa: E402

CAPTURED_INFO = bytes.fromhex("a55a1400000004") + bytes.fromhex("41020112f57ffc8bc6e598d1b59598f976dd5762")
CAPTURED_HEALTH_OK = bytes.fromhex("a55a0300000006") + bytes.fromhex("000000")
CAPTURED_SCAN_DESCRIPTOR = bytes.fromhex("a55a0500004081")
CONF_DESCRIPTOR = bytes.fromhex("a55a0600000020")


def conf_answer(payload: bytes) -> bytes:
    """Descriptor with the right length + body (type echo included in `payload`)."""
    return bytes.fromhex("a55a") + len(payload).to_bytes(4, "little") + b"\x20" + payload


def revolution_bytes(n_beams: int, distance_mm: float = 1500.0, quality: int = 15, start_angle: float = 0.0) -> bytes:
    step = 360.0 / n_beams
    return b"".join(proto.encode_node(proto.Node(i == 0, quality, (start_angle + i * step) % 360.0, distance_mm))
                    for i in range(n_beams))


class FakeTransport:
    """Scripted device: each request maps to a queue of responses; SCAN also emits a node stream."""

    def __init__(self, responses: dict[bytes, list[bytes]], stream: bytes = b"", max_chunk: int | None = None):
        self.responses = {key: list(value) for key, value in responses.items()}
        self.stream = stream
        self.max_chunk = max_chunk
        self.buffer = bytearray()
        self.writes: list[bytes] = []
        self.closed = False
        self.timeout = 0.05

    @property
    def in_waiting(self) -> int:
        return len(self.buffer)

    def write(self, data: bytes) -> None:
        data = bytes(data)
        self.writes.append(data)
        queue = self.responses.get(data)
        if queue:
            self.buffer += queue.pop(0) if len(queue) > 1 else queue[0]
        if data == proto.request(proto.CMD_SCAN):
            self.buffer += CAPTURED_SCAN_DESCRIPTOR + self.stream

    def read(self, n: int) -> bytes:
        if self.max_chunk is not None:
            n = min(n, self.max_chunk)
        out = bytes(self.buffer[:n])
        del self.buffer[:n]
        return out

    def reset_input_buffer(self) -> None:
        self.buffer.clear()

    def close(self) -> None:
        self.closed = True


class FakeClock:
    def __init__(self, step: float = 0.001):
        self.t, self.step = 100.0, step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


def test_request_packets_and_checksum():
    assert proto.request(proto.CMD_SCAN) == b"\xa5\x20"
    packet = proto.conf_request(proto.CONF_SCAN_MODE_COUNT)
    assert packet[:3] == b"\xa5\x84\x04" and packet[3:7] == b"\x70\x00\x00\x00"
    checksum = 0
    for byte in packet[:-1]:
        checksum ^= byte
    assert packet[-1] == checksum
    assert proto.conf_request(proto.CONF_SCAN_MODE_NAME, 1)[3:9] == b"\x7f\x00\x00\x00\x01\x00"
    with pytest.raises(ValueError):
        proto.request(0x100)


def test_captured_descriptors_and_bodies_parse():
    assert proto.parse_descriptor(CAPTURED_INFO[:7]) == proto.Descriptor(20, 0, proto.ANS_DEVICE_INFO)
    info = proto.parse_device_info(CAPTURED_INFO[7:])
    assert (info.model, info.firmware, info.hardware) == (0x41, "1.2", 18)
    assert info.serial == "f57ffc8bc6e598d1b59598f976dd5762"
    assert proto.parse_descriptor(CAPTURED_HEALTH_OK[:7]) == proto.Descriptor(3, 0, proto.ANS_DEVICE_HEALTH)
    assert proto.parse_device_health(CAPTURED_HEALTH_OK[7:]) == proto.DeviceHealth(0, 0)
    assert proto.parse_device_health(bytes.fromhex("020300")).name == "ERROR"
    assert proto.parse_descriptor(CAPTURED_SCAN_DESCRIPTOR) == proto.SCAN_DESCRIPTOR
    assert proto.conf_u16(bytes.fromhex("700000000200"), proto.CONF_SCAN_MODE_COUNT) == 2       # captured
    assert proto.conf_u16(bytes.fromhex("7c0000000100"), proto.CONF_SCAN_MODE_TYPICAL) == 1     # captured
    with pytest.raises(proto.ProtocolError):
        proto.conf_u16(bytes.fromhex("7c0000000100"), proto.CONF_SCAN_MODE_COUNT)
    with pytest.raises(proto.ProtocolError):
        proto.parse_descriptor(b"\x00" * 7)
    with pytest.raises(proto.ProtocolError):
        proto.parse_device_info(b"\x00" * 19)


def test_node_decoding_matches_hand_computed_bytes():
    # start flag, quality 47, angle 123.5 deg (q6 = 7904 = 0x1EE0), distance 2345 mm (q2 = 9380 = 0x24A4)
    raw = bytes.fromhex("bdc13da424")
    node = proto.decode_node(raw)
    assert node == proto.Node(True, 47, 123.5, 2345.0) and node.has_return
    assert proto.encode_node(node) == raw
    assert proto.decode_node(bytes.fromhex("bcc13da424")) is None     # S == inverse-S: not a node boundary
    assert proto.decode_node(bytes.fromhex("bdc03da424")) is None     # check bit of byte 1 cleared
    silent = proto.decode_node(proto.encode_node(proto.Node(False, 0, 10.0, 0.0)))
    assert silent is not None and not silent.has_return


def test_decoder_resyncs_after_garbage_and_across_chunks():
    a = proto.encode_node(proto.Node(True, 10, 0.0, 1000.0))
    b = proto.encode_node(proto.Node(False, 11, 0.7, 1001.0))
    decoder = proto.NodeDecoder()
    stream = a + b"\x00\x00\x00" + b
    nodes = decoder.feed(stream[:6]) + decoder.feed(stream[6:])
    assert [n.quality for n in nodes] == [10, 11] and decoder.resync_bytes == 3 and decoder.nodes == 2


def test_assembler_groups_revolutions_by_start_flag():
    assembler = proto.RevolutionAssembler(max_nodes=10)
    mk = lambda start, angle: proto.Node(start, 5, angle, 500.0)  # noqa: E731
    assert assembler.push(mk(False, 350.0), 0.00) is None            # before the first flag: discarded
    assert assembler.push(mk(True, 0.0), 0.01) is None
    assert assembler.push(mk(False, 90.0), 0.02) is None
    assert assembler.push(mk(False, 180.0), 0.03) is None
    revolution = assembler.push(mk(True, 0.0), 0.10)
    assert revolution is not None and len(revolution) == 3
    assert (revolution.t_first, revolution.t_last) == (0.01, 0.03)
    assert assembler.discarded_nodes == 1 and assembler.completed == 1
    for i in range(12):                                                # start flag lost: revolution dropped
        assert assembler.push(mk(False, float(i)), 0.2 + i * 0.001) is None
    assert assembler.dropped == 1
    assert assembler.push(mk(True, 0.0), 0.5) is None                 # nothing to complete after a drop


def test_assembler_splits_on_angle_wrap_when_the_flag_is_missing():
    assembler = proto.RevolutionAssembler(min_nodes_for_wrap=100)
    mk = lambda start, angle: proto.Node(start, 5, angle, 500.0)  # noqa: E731
    assert assembler.push(mk(True, 357.5), 0.0) is None               # flagged node sits just before 0 deg ...
    assert assembler.push(mk(False, 0.3), 0.001) is None              # ... so this wrap must NOT split (too few nodes)
    for i in range(1, 500):
        assert assembler.push(mk(False, 0.3 + i * 0.72), 0.001 + i * 0.0002) is None
    revolution = assembler.push(mk(False, 0.1), 0.1)                  # device forgot the flag: wrap closes the revolution
    assert revolution is not None and len(revolution) == 501 and assembler.wrap_splits == 1
    assert revolution.nodes[0].start and revolution.nodes[-1].angle_deg == pytest.approx(0.3 + 499 * 0.72)
    for i in range(1, 500):
        assert assembler.push(mk(False, 0.1 + i * 0.72), 0.1 + i * 0.0002) is None
    flagged = assembler.push(mk(True, 359.9), 0.2)                    # the next flag closes the wrap-started one
    assert flagged is not None and len(flagged) == 500 and not flagged.nodes[0].start
    assert assembler.completed == 2 and assembler.dropped == 0


def test_revolution_to_scan_uses_project_yaw_convention():
    nodes = [proto.Node(True, 20, 0.0, 1000.0), proto.Node(False, 20, 90.0, 2000.0),
             proto.Node(False, 0, 180.0, 0.0), proto.Node(False, 20, 270.0, 500.0)]
    revolution = proto.Revolution(nodes, 1.0, 1.1)
    scan, quality = proto.revolution_to_scan(revolution, SourceStamp("lidar", 1.1))
    assert isinstance(scan, LidarScan) and quality.tolist() == [20, 20, 0, 20]
    angles = list(scan.angles_rad)
    assert angles[0] == pytest.approx(0.0)
    assert angles[1] == pytest.approx(-math.pi / 2)                    # device 90 deg clockwise = right side
    assert angles[2] == pytest.approx(-math.pi)
    assert angles[3] == pytest.approx(math.pi / 2)                     # device 270 deg clockwise = left side
    assert scan.ranges_m[0] == 1.0 and scan.ranges_m[1] == 2.0 and math.isnan(scan.ranges_m[2]) and scan.ranges_m[3] == 0.5
    mirrored, _ = proto.revolution_to_scan(revolution, SourceStamp("lidar", 1.1), mirror=True)
    assert mirrored.angles_rad[1] == pytest.approx(math.pi / 2)


def scripted_transport(health=CAPTURED_HEALTH_OK, revolutions=3, beams=8, **kwargs) -> FakeTransport:
    stream = b"".join(revolution_bytes(beams, distance_mm=1000.0 + 100 * i) for i in range(revolutions))
    stream += proto.encode_node(proto.Node(True, 15, 0.0, 999.0))      # start of a revolution that never completes
    responses = {proto.request(proto.CMD_GET_INFO): [CAPTURED_INFO],
                 proto.request(proto.CMD_GET_HEALTH): [health] if isinstance(health, bytes) else list(health)}
    return FakeTransport(responses, stream, **kwargs)


def test_source_streams_revolutions_and_reports_timeout():
    transport = scripted_transport(max_chunk=7)                       # partial reads split nodes across chunks
    source = RplidarC1Source(transport, clock=FakeClock(), revolution_timeout_s=0.5, source_id="c1")
    first = source.read()
    assert source.info.model == 0x41 and source.health.status == 0
    assert transport.writes[0] == proto.request(proto.CMD_STOP)       # STOP before anything else
    assert proto.request(proto.CMD_SCAN) in transport.writes
    assert first.stamp.source_id == "c1" and first.stamp.frame_id == "lidar" and first.stamp.t >= 0
    assert len(first.ranges_m) == 8 and first.ranges_m[0] == pytest.approx(1.0)
    second, third = source.read(), source.read()
    assert second.ranges_m[0] == pytest.approx(1.1) and third.ranges_m[0] == pytest.approx(1.2)
    assert first.stamp.t <= second.stamp.t <= third.stamp.t
    assert source.last_quality.tolist() == [15] * 8 and source.revolutions == 3
    with pytest.raises(ScanReadError):
        source.read()
    stats = source.stats()
    assert stats["resync_bytes"] == 0 and stats["revolutions"] == 3 and stats["nodes"] == 25
    source.close()
    assert transport.closed and transport.writes[-1] == proto.request(proto.CMD_STOP)


def test_source_resets_once_when_health_reports_error():
    error = bytes.fromhex("a55a0300000006") + bytes.fromhex("020300")
    transport = scripted_transport(health=[error, CAPTURED_HEALTH_OK])
    source = RplidarC1Source(transport, clock=FakeClock())
    source.start()
    assert proto.request(proto.CMD_RESET) in transport.writes and source.resets == 1 and source.health.status == 0
    stuck = scripted_transport(health=[error, error])
    with pytest.raises(proto.ProtocolError, match="ERROR"):
        RplidarC1Source(stuck, clock=FakeClock()).start()


def test_scan_modes_from_captured_configuration_answers():
    responses = {
        proto.conf_request(proto.CONF_SCAN_MODE_COUNT): [conf_answer(bytes.fromhex("700000000200"))],
        proto.conf_request(proto.CONF_SCAN_MODE_TYPICAL): [conf_answer(bytes.fromhex("7c0000000100"))],
        proto.conf_request(proto.CONF_SCAN_MODE_NAME, 0): [conf_answer(bytes.fromhex("7f000000") + b"Standard\x00")],
        proto.conf_request(proto.CONF_SCAN_MODE_NAME, 1): [conf_answer(bytes.fromhex("7f000000") + b"DenseBoost\x00")],
        proto.conf_request(proto.CONF_SCAN_MODE_US_PER_SAMPLE, 0): [conf_answer(bytes.fromhex("71000000") + (200 * 256).to_bytes(4, "little"))],
        proto.conf_request(proto.CONF_SCAN_MODE_US_PER_SAMPLE, 1): [conf_answer(bytes.fromhex("71000000") + (200 * 256).to_bytes(4, "little"))],
        proto.conf_request(proto.CONF_SCAN_MODE_MAX_DISTANCE, 0): [conf_answer(bytes.fromhex("74000000") + (16 * 256).to_bytes(4, "little"))],
        proto.conf_request(proto.CONF_SCAN_MODE_MAX_DISTANCE, 1): [conf_answer(bytes.fromhex("74000000") + (40 * 256).to_bytes(4, "little"))],
        proto.conf_request(proto.CONF_SCAN_MODE_ANS_TYPE, 0): [conf_answer(bytes.fromhex("75000000") + b"\x81")],
        proto.conf_request(proto.CONF_SCAN_MODE_ANS_TYPE, 1): [conf_answer(bytes.fromhex("75000000") + b"\x85")],
    }
    source = RplidarC1Source(FakeTransport(responses), clock=FakeClock())
    modes = source.scan_modes()
    assert modes["count"] == 2 and modes["typical"] == 1
    assert modes["modes"][0] == {"id": 0, "name": "Standard", "us_per_sample": 200.0, "max_distance_m": 16.0, "answer_type": "0x81"}
    assert modes["modes"][1]["name"] == "DenseBoost" and modes["modes"][1]["max_distance_m"] == 40.0


def test_source_rejects_bad_scan_descriptor_and_missing_answers():
    transport = FakeTransport({proto.request(proto.CMD_GET_INFO): [CAPTURED_INFO],
                               proto.request(proto.CMD_GET_HEALTH): [CAPTURED_HEALTH_OK]})
    transport.responses[proto.request(proto.CMD_SCAN)] = [bytes.fromhex("a55a0500004082")]
    original_write = transport.write

    def write(data):                                                   # answer SCAN with the wrong data type
        original_write(data)
        if bytes(data) == proto.request(proto.CMD_SCAN):
            transport.buffer[:] = bytes.fromhex("a55a0500004082")
    transport.write = write
    with pytest.raises(proto.ProtocolError, match="descriptor"):
        RplidarC1Source(transport, clock=FakeClock()).start()
    silent = RplidarC1Source(FakeTransport({}), clock=FakeClock())
    with pytest.raises(proto.ProtocolError, match="no response"):
        silent.device_info()
