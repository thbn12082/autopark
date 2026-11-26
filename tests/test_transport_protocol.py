"""Giao thức laptop ↔ ESP32 v1: CRC, COBS, mã hóa từng thông điệp, bộ tách khung với rác/cụt/quá dài/sai CRC,
fuzz với seed cố định, và vector mẫu dùng chung với firmware C++."""
import json
import random

import pytest

from autopark.transport import protocol as p
from autopark.transport.vectors import DEFAULT_PATH, build_vectors, dumps

SESSION = 0xA1B2C3D4


def sample_messages() -> list:
    limits = p.Limits(300, 524, 1571, 300, 600, 600, 300, 500)
    return [
        p.Hello(SESSION, 0, 50, 123456),
        p.Hello(0xFFFFFFFF, 0xFFFF, 0xFFFF, 0xFFFFFFFF),
        p.Request(SESSION, 1, int(p.Action.ARM)),
        p.Command(SESSION, 2, 150, p.COMMAND_FLAG_ENABLE, 120, -250),
        p.Command(SESSION, 3, 1, 0, -32768, 32767),
        p.Command(0, 0, 0, 0, 0, 0),
        p.HelloAck(SESSION, 0, 7, 1, 0, 0xDEADBEEF, int(p.ResetReason.BROWNOUT), 1, 50, limits),
        p.Ack(SESSION, 5, int(p.MsgType.COMMAND), 9, int(p.Result.BAD_STATE), 1, 0),
        p.TelemetryMsg(SESSION, 6, 0xFFFFFFFF, 3, 0, 3, 0xFF, 42, 17, -101, 52, 100, -50, -1000, 12, -340, 25, 0x0F,
                       (150, 0, 1200, 65535), 7400, 65535, 3),
        p.FaultMsg(SESSION, 8, int(p.Fault.ESTOP), int(p.State.FAULT), 5000, 0),
    ]


# ---- CRC và COBS ------------------------------------------------------------------------------------------------
def test_crc16_ccitt_false_check_values():
    assert p.crc16_ccitt_false(b"123456789") == 0x29B1          # giá trị kiểm tra chuẩn của CRC-16/CCITT-FALSE
    assert p.crc16_ccitt_false(b"") == 0xFFFF
    assert p.crc16_ccitt_false(b"\x00") != p.crc16_ccitt_false(b"\x00\x00")


@pytest.mark.parametrize("decoded, encoded", [
    (b"", "01"),
    (b"\x00", "0101"),
    (b"\x00\x00", "010101"),
    (b"\x11\x22\x00\x33", "0311220233"),
    (b"\x11\x22\x33\x44", "0511223344"),
    (b"\x11\x00\x00\x00", "0211010101"),
    (bytes(range(1, 255)), "ff" + bytes(range(1, 255)).hex()),                      # 254 byte khác 0: không có 01 thừa
    (bytes(range(0, 255)), "01ff" + bytes(range(1, 255)).hex()),
    (bytes(range(1, 256)), "ff" + bytes(range(1, 255)).hex() + "02ff"),
    (bytes(range(2, 256)) + b"\x00", "ff" + bytes(range(2, 256)).hex() + "0101"),
    (bytes(range(3, 256)) + b"\x00\x01", "fe" + bytes(range(3, 256)).hex() + "0201"),
])
def test_cobs_matches_reference_examples(decoded, encoded):
    assert p.cobs_encode(decoded).hex() == encoded
    assert p.cobs_decode(bytes.fromhex(encoded)) == decoded


def test_cobs_round_trip_random_and_never_emits_zero():
    rng = random.Random(1)
    for _ in range(500):
        data = bytes(rng.choice((0, 0, rng.randrange(256))) for _ in range(rng.randrange(0, 600)))
        encoded = p.cobs_encode(data)
        assert 0 not in encoded
        assert p.cobs_decode(encoded) == data


@pytest.mark.parametrize("bad", [b"", b"\x00", b"\x05\x11\x22", b"\x03\x11\x00"])
def test_cobs_decode_rejects_malformed(bad):
    with pytest.raises(p.ProtocolError) as err:
        p.cobs_decode(bad)
    assert err.value.kind == "cobs"


# ---- mã hóa thông điệp ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("msg", sample_messages(), ids=lambda m: type(m).__name__)
def test_message_round_trip_and_fixed_size(msg):
    raw = p.encode_message(msg)
    assert len(raw) == p.MESSAGE_SIZES[msg.TYPE]
    assert raw[0] == p.PROTOCOL_VERSION and raw[1] == int(msg.TYPE)
    assert p.decode_message(raw) == msg
    frame = p.encode_frame(msg)
    assert frame.endswith(b"\x00") and 0 not in frame[:-1]
    assert p.FrameParser().feed(frame) == [msg]
    assert p.message_from_fields(int(msg.TYPE), p.message_fields(msg)) == msg


def test_wire_layout_is_little_endian_with_documented_offsets():
    raw = p.encode_message(p.Command(0x04030201, 0x0605, 0x0807, 0x01, -2, 0x0A09))
    assert raw.hex() == "01" "03" "01020304" "0506" "0708" "01" "feff" "090a"
    assert p.MESSAGE_SIZES == {p.MsgType.HELLO: 14, p.MsgType.REQUEST: 9, p.MsgType.COMMAND: 15,
                               p.MsgType.HELLO_ACK: 36, p.MsgType.ACK: 14, p.MsgType.TELEMETRY: 51,
                               p.MsgType.FAULT: 16}


@pytest.mark.parametrize("msg", [
    p.Command(SESSION, 1, 150, 1, 32768, 0),          # tốc độ tràn int16
    p.Command(SESSION, 1, 65536, 1, 0, 0),            # validity tràn uint16
    p.Hello(2 ** 32, 0),                              # session tràn uint32
    p.Request(SESSION, -1, 1),
])
def test_encode_rejects_out_of_range_instead_of_wrapping(msg):
    with pytest.raises(ValueError):
        p.encode_message(msg)


def test_decode_rejects_bad_version_type_and_length():
    raw = p.encode_message(p.Request(SESSION, 1, 1))
    for mutated, kind in ((bytes([2]) + raw[1:], "version"), (raw[:1] + b"\x7f" + raw[2:], "type"),
                          (raw + b"\x00", "length"), (raw[:-1], "length"), (raw[:5], "short")):
        with pytest.raises(p.ProtocolError) as err:
            p.decode_message(mutated)
        assert err.value.kind == kind
    with pytest.raises(p.ProtocolError) as err:
        p.decode_message(p.encode_message(sample_messages()[8]), p.HOST_TO_DEVICE)   # telemetry gửi nhầm tới bo
    assert err.value.kind == "type"


# ---- bộ tách khung ----------------------------------------------------------------------------------------------
def test_parser_handles_byte_by_byte_and_chunked_input():
    msgs = sample_messages()
    stream = b"".join(p.encode_frame(m) for m in msgs)
    parser = p.FrameParser()
    out = []
    for byte in stream:
        out += parser.feed(bytes([byte]))
    assert out == msgs
    rng = random.Random(3)
    parser, out, i = p.FrameParser(), [], 0
    while i < len(stream):
        n = rng.randrange(1, 40)
        out += parser.feed(stream[i:i + n])
        i += n
    assert out == msgs and parser.stats.errors == 0


def test_parser_counts_each_error_kind_and_recovers():
    good = p.Request(SESSION, 9, int(p.Action.PING))
    raw = p.encode_message(p.Command(SESSION, 2, 150, 1, 10, 10))
    cases = {
        "crc": p.cobs_encode(raw + b"\x00\x00") + b"\x00",
        "version": p.frame_from_raw(bytes([9]) + raw[1:]),
        "type": p.frame_from_raw(raw[:1] + b"\x55" + raw[2:]),
        "length": p.frame_from_raw(raw + b"\x01"),
        "short": p.frame_from_raw(raw[:4]),
        "oversize": b"\x42" * (p.MAX_ENCODED_SIZE + 1) + b"\x00",
        "cobs": b"\x09\x11\x22\x00",
    }
    for kind, bad in cases.items():
        parser = p.FrameParser()
        assert parser.feed(bad + p.encode_frame(good)) == [good], kind
        assert getattr(parser.stats, kind) == 1 and parser.stats.errors == 1, (kind, parser.stats)


def test_parser_truncated_frame_is_dropped_and_next_frame_survives():
    good = p.Request(SESSION, 9, int(p.Action.PING))
    frame = p.encode_frame(p.Command(SESSION, 2, 150, 1, 10, 10))
    for cut in range(1, len(frame) - 1):
        parser = p.FrameParser()
        out = parser.feed(frame[:cut] + b"\x00" + p.encode_frame(good))
        assert out == [good] and parser.stats.errors == 1


def test_parser_frame_at_size_limit_is_kept_and_one_over_is_dropped():
    msg = p.Request(SESSION, 1, 1)
    encoded_len = len(p.encode_frame(msg)) - 1        # không kể 0x00
    assert p.FrameParser(max_encoded=encoded_len).feed(p.encode_frame(msg)) == [msg]
    parser = p.FrameParser(max_encoded=encoded_len - 1)
    assert parser.feed(p.encode_frame(msg) + p.encode_frame(msg)[:3]) == [] and parser.stats.oversize == 1
    # Mọi thông điệp thật (lớn nhất là TELEMETRY) vừa giới hạn mặc định.
    assert max(len(p.encode_frame(m)) - 1 for m in sample_messages()) <= p.MAX_ENCODED_SIZE


def test_parser_accept_types_filters_direction():
    tel = sample_messages()[8]
    device_side = p.FrameParser(accept_types=p.HOST_TO_DEVICE)
    assert device_side.feed(p.encode_frame(tel)) == [] and device_side.stats.type == 1
    host_side = p.FrameParser(accept_types=p.DEVICE_TO_HOST)
    assert host_side.feed(p.encode_frame(tel)) == [tel]


@pytest.mark.parametrize("seed", range(12))
def test_fuzz_parser_never_raises_and_never_yields_corrupted_message(seed):
    """Luồng: khung hợp lệ xen rác ngẫu nhiên, khung bị lật bit, khung cụt. Parser không bao giờ ném lỗi; mọi
    thông điệp nó trả ra đều là một trong các thông điệp gốc; mọi khung hợp lệ đứng sau một 0x00 đều được nhận."""
    rng = random.Random(seed)
    originals = sample_messages() + [p.Command(SESSION, k, 150, 1, rng.randrange(-300, 300), rng.randrange(-500, 500))
                                     for k in range(40)]
    stream = bytearray()
    expected = []
    for _ in range(400):
        roll = rng.random()
        msg = rng.choice(originals)
        frame = bytearray(p.encode_frame(msg))
        if roll < 0.45:
            stream += frame
            expected.append(msg)
        elif roll < 0.65:
            stream += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 120))) + b"\x00"
        elif roll < 0.85:
            k = rng.randrange(len(frame) - 1)
            frame[k] ^= 1 << rng.randrange(8)       # có thể tạo 0x00 giữa khung: tách thành hai mảnh hỏng
            stream += frame
        else:
            stream += frame[:rng.randrange(1, len(frame) - 1)] + b"\x00"
    parser = p.FrameParser()
    out = []
    i = 0
    while i < len(stream):
        n = rng.randrange(1, 64)
        out += parser.feed(bytes(stream[i:i + n]))
        i += n
    allowed = set(originals)
    assert all(m in allowed for m in out)
    # Mỗi khung hợp lệ được chèn nguyên vẹn (và luôn đứng sau một 0x00) phải được nhận.
    remaining = list(out)
    for msg in expected:
        assert msg in remaining
        remaining.remove(msg)
    assert parser.stats.errors > 0


# ---- vector mẫu chung với firmware C++ -------------------------------------------------------------------------
def test_vectors_file_is_up_to_date_with_reference():
    assert DEFAULT_PATH.read_text(encoding="utf-8") == dumps(build_vectors()), \
        "chạy: python -m autopark.transport.vectors --write"


def test_vectors_file_is_self_consistent():
    vectors = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    assert vectors["format"] == "autopark-vehicle-vectors" and vectors["protocol_version"] == p.PROTOCOL_VERSION
    for item in vectors["crc16"]:
        assert p.crc16_ccitt_false(bytes.fromhex(item["data"])) == item["crc"]
    for item in vectors["cobs"]:
        assert p.cobs_encode(bytes.fromhex(item["decoded"])).hex() == item["encoded"]
    for item in vectors["messages"]:
        msg = p.message_from_fields(item["type"], item["fields"])
        assert p.encode_message(msg).hex() == item["raw"]
        assert p.encode_frame(msg).hex() == item["frame"]
        assert p.FrameParser().feed(bytes.fromhex(item["frame"])) == [msg]
    kinds = set()
    for item in vectors["streams_to_device"]:
        parser = p.FrameParser(accept_types=p.HOST_TO_DEVICE)
        msgs = parser.feed(bytes.fromhex(item["stream"]))
        assert [p.encode_message(m).hex() for m in msgs] == item["messages"], item["name"]
        assert {k: getattr(parser.stats, k) for k in item["errors"]} == item["errors"], item["name"]
        kinds |= {k for k, v in item["errors"].items() if v}
    assert kinds == set(p.ERROR_KINDS)                 # mỗi loại lỗi có ít nhất một vector
