"""Driver RPLIDAR C1 qua UART 460800 (pyserial), chế độ quét Standard, theo hợp đồng `LidarScan`.

    python -m autopark.lidar.rplidar_c1 info --port COM4
    python -m autopark.lidar.rplidar_c1 stream --port COM4 --seconds 5

Đã kiểm chứng trên thiết bị của dự án ngày 22/09/2026 (COM4, model 0x41, firmware 1.2, phần cứng 18):
- Thiết bị công bố hai chế độ quét: 0 "Standard" (200 µs/mẫu, xa nhất 16 m, kiểu trả lời 0x81) và
  1 "DenseBoost" (200 µs/mẫu, 40 m, 0x85, là chế độ "typical"). Driver này chỉ dùng Standard (lệnh 0x20):
  đo được 5,1 kHz, 9,97 Hz, trung vị 508 tia/vòng, bước 0,70°, không lệch byte nào trong 30 nghìn node.
- Mô-tơ tự khởi động khi nhận lệnh SCAN và dừng khi nhận STOP; node đầu tiên đến sau ≈ 2,2 s.
- RESET làm thiết bị khởi động lại và in `RP S2 LIDAR System.\\r\\n` (21 byte) trong ~1 s.
- Không có phản hồi thì khoảng cách 0 và chất lượng 0 đi cùng nhau (0 trường hợp lệch trong 30 nghìn node).

Quy ước thời gian: đồng hồ phiên `clock()` (mặc định `time.monotonic`) trừ mốc lúc `start()`; stamp của một
vòng quét là thời điểm gói byte chứa node cuối của vòng đó về tới máy (trễ tối đa một lần đọc, ≤ 50 ms).
Nguồn trực tiếp không bao giờ trả `None`: hết thời gian chờ thì ném `ScanReadError`, cùng quy ước với
`FrameReadError` của camera, để vòng lặp tiêu thụ không nhầm sự cố với hết dữ liệu.

Lỗi của chính cổng nối tiếp trong `read()` (rút cáp USB: pyserial ném `SerialException`, là `OSError`, từ
`in_waiting`/`read`) được ném lại thành `LidarTransportError` — lớp con của `ScanReadError`, giữ lỗi gốc ở
`__cause__` — để nơi gọi chỉ bắt `ScanReadError` cũng không chết với traceback. Khác với hết thời gian chờ, thử đọc
lại trên cùng cổng không giúp gì: phải đóng rồi mở lại cổng. (Thêm tối 24/09/2026; chỉ thử với cổng GIẢ trong
`tests/test_lidar_unplug.py`, CHƯA THỬ rút cáp C1 thật. `close()` vẫn ném `OSError` khi không gửi được STOP qua
cổng đã chết; nơi gọi tự quyết bỏ qua hay báo.)
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import sys
import time

import numpy as np

from autopark.domain.sensors import LidarScan, SourceStamp

from .rplidar_protocol import (ANS_DEVICE_HEALTH, ANS_DEVICE_INFO, ANS_LIDAR_CONF, CMD_GET_HEALTH, CMD_GET_INFO,
                               CMD_RESET, CMD_SCAN, CMD_STOP, CONF_SCAN_MODE_ANS_TYPE, CONF_SCAN_MODE_COUNT,
                               CONF_SCAN_MODE_MAX_DISTANCE, CONF_SCAN_MODE_NAME, CONF_SCAN_MODE_TYPICAL,
                               CONF_SCAN_MODE_US_PER_SAMPLE, DESCRIPTOR_LENGTH, SCAN_DESCRIPTOR, DeviceHealth,
                               DeviceInfo, ProtocolError, Revolution, ScanQueue, conf_name, conf_request, conf_u16,
                               conf_u32, parse_descriptor, parse_device_health, parse_device_info, request,
                               revolution_to_scan)

DEFAULT_BAUDRATE = 460800
DRIVER_VERSION = "1.0"


class ScanReadError(RuntimeError):
    """The device did not deliver a full revolution in time; the stream is not over, something is wrong."""


class LidarTransportError(ScanReadError):
    """The serial port itself failed inside `read()` (USB cable pulled, driver error). The original `OSError`
    (pyserial's `SerialException`) is the `__cause__`. Retrying on the same port does not help: close and reopen."""


class RplidarC1Source:
    """Reads revolutions from a C1 and returns each as a `LidarScan`.

    `transport` is any object with `write(bytes)`, `read(n) -> bytes` (returning early after its own timeout),
    `in_waiting`, `reset_input_buffer()` and `close()`: a `serial.Serial`, or a fake in tests.
    """

    def __init__(self, transport, *, source_id: str = "rplidar_c1", clock: Callable[[], float] = time.monotonic,
                 mirror: bool = False, first_revolution_timeout_s: float = 8.0, revolution_timeout_s: float = 1.0,
                 chunk_size: int = 4096, settle_s: float = 0.01):
        if first_revolution_timeout_s <= 0 or revolution_timeout_s <= 0 or chunk_size <= 0:
            raise ValueError("timeouts and chunk size must be > 0")
        self.transport = transport
        self.source_id = source_id
        self.clock = clock
        self.mirror = mirror
        self.first_revolution_timeout_s = first_revolution_timeout_s
        self.revolution_timeout_s = revolution_timeout_s
        self.chunk_size = chunk_size
        self.settle_s = settle_s
        self.queue = ScanQueue()
        self.t0: float | None = None
        self.info: DeviceInfo | None = None
        self.health: DeviceHealth | None = None
        self.started = False
        self.revolutions = 0
        self.last_quality: np.ndarray | None = None
        self.last_revolution: Revolution | None = None
        self.resets = 0

    @classmethod
    def open(cls, port: str, *, baudrate: int = DEFAULT_BAUDRATE, read_timeout_s: float = 0.05, **kwargs) -> "RplidarC1Source":
        import serial  # pyserial, optional dependency "lidar"

        transport = serial.Serial(port, baudrate, timeout=read_timeout_s)
        return cls(transport, **kwargs)

    # ---- low level -------------------------------------------------------------------------------------------
    def _sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)

    def _read_exact(self, n: int, timeout_s: float) -> bytes:
        deadline = self.clock() + timeout_s
        out = bytearray()
        while len(out) < n:
            chunk = self.transport.read(n - len(out))
            if chunk:
                out += chunk
            elif self.clock() >= deadline:
                break
        return bytes(out)

    def _query(self, packet: bytes, expected_type: int, timeout_s: float = 1.0) -> bytes:
        self.transport.reset_input_buffer()
        self.transport.write(packet)
        raw = self._read_exact(DESCRIPTOR_LENGTH, timeout_s)
        if len(raw) != DESCRIPTOR_LENGTH:
            raise ProtocolError(f"no response descriptor within {timeout_s} s (got {raw.hex()})")
        descriptor = parse_descriptor(raw)
        if descriptor.data_type != expected_type or descriptor.send_mode != 0:
            raise ProtocolError(f"unexpected descriptor {descriptor} for type 0x{expected_type:02x}")
        body = self._read_exact(descriptor.length, timeout_s)
        if len(body) != descriptor.length:
            raise ProtocolError(f"short response body: {len(body)}/{descriptor.length} bytes")
        return body

    def stop_output(self) -> None:
        """STOP: the device stops sending measurements and the motor stops; wait as the protocol requires."""
        self.transport.write(request(CMD_STOP))
        self._sleep(self.settle_s)
        self.transport.reset_input_buffer()
        self.started = False

    # ---- queries ---------------------------------------------------------------------------------------------
    def device_info(self) -> DeviceInfo:
        self.info = parse_device_info(self._query(request(CMD_GET_INFO), ANS_DEVICE_INFO))
        return self.info

    def device_health(self) -> DeviceHealth:
        self.health = parse_device_health(self._query(request(CMD_GET_HEALTH), ANS_DEVICE_HEALTH))
        return self.health

    def scan_modes(self) -> dict:
        count = conf_u16(self._query(conf_request(CONF_SCAN_MODE_COUNT), ANS_LIDAR_CONF), CONF_SCAN_MODE_COUNT)
        typical = conf_u16(self._query(conf_request(CONF_SCAN_MODE_TYPICAL), ANS_LIDAR_CONF), CONF_SCAN_MODE_TYPICAL)
        modes = []
        for mode in range(count):
            name = conf_name(self._query(conf_request(CONF_SCAN_MODE_NAME, mode), ANS_LIDAR_CONF), CONF_SCAN_MODE_NAME)
            us = conf_u32(self._query(conf_request(CONF_SCAN_MODE_US_PER_SAMPLE, mode), ANS_LIDAR_CONF), CONF_SCAN_MODE_US_PER_SAMPLE)
            distance = conf_u32(self._query(conf_request(CONF_SCAN_MODE_MAX_DISTANCE, mode), ANS_LIDAR_CONF), CONF_SCAN_MODE_MAX_DISTANCE)
            answer = self._query(conf_request(CONF_SCAN_MODE_ANS_TYPE, mode), ANS_LIDAR_CONF)[4]
            modes.append({"id": mode, "name": name, "us_per_sample": us / 256.0, "max_distance_m": distance / 256.0,
                          "answer_type": f"0x{answer:02x}"})
        return {"count": count, "typical": typical, "modes": modes}

    def reset(self, settle_s: float = 1.0) -> bytes:
        """RESET reboots the scanner core; returns the boot banner it prints so a caller can log it."""
        self.transport.reset_input_buffer()
        self.transport.write(request(CMD_RESET))
        self._sleep(settle_s)
        banner = bytearray()
        while True:
            chunk = self.transport.read(max(1, int(getattr(self.transport, "in_waiting", 0))))
            if not chunk:
                break
            banner += chunk
        self.transport.reset_input_buffer()
        self.resets += 1
        self.started = False
        return bytes(banner)

    # ---- streaming -------------------------------------------------------------------------------------------
    def start(self) -> None:
        """STOP, read info and health (reset once on health ERROR), then SCAN and check its descriptor."""
        self.stop_output()
        self.device_info()
        health = self.device_health()
        if health.status == 2:
            self.reset()
            health = self.device_health()
            if health.status == 2:
                raise ProtocolError(f"device health ERROR (code {health.error_code}) persists after reset")
        self.t0 = self.clock()
        self.transport.reset_input_buffer()
        self.transport.write(request(CMD_SCAN))
        raw = self._read_exact(DESCRIPTOR_LENGTH, 1.0)
        if len(raw) != DESCRIPTOR_LENGTH:
            raise ProtocolError("no scan descriptor")
        descriptor = parse_descriptor(raw)
        if descriptor != SCAN_DESCRIPTOR:
            raise ProtocolError(f"unexpected scan descriptor {descriptor}")
        self.queue = ScanQueue()
        self.started = True

    def now(self) -> float:
        if self.t0 is None:
            raise RuntimeError("session clock starts at start()")
        return max(0.0, self.clock() - self.t0)

    def read(self) -> LidarScan:
        """Blocks until one full revolution is available. Raises `ScanReadError` when none arrives in time, and its
        subclass `LidarTransportError` (from the port's `OSError`) when the serial port fails."""
        try:
            return self._read()
        except OSError as exc:
            raise LidarTransportError(f"{self.source_id}: serial port failed ({type(exc).__name__}: {exc}); "
                                      f"cable unplugged? close and reopen the port") from exc

    def _read(self) -> LidarScan:
        if not self.started:
            self.start()
        revolution = self.queue.pop()
        if revolution is None:
            timeout = self.first_revolution_timeout_s if self.revolutions == 0 else self.revolution_timeout_s
            deadline = self.clock() + timeout
            while revolution is None:
                waiting = int(getattr(self.transport, "in_waiting", 0))
                data = self.transport.read(max(1, min(waiting, self.chunk_size)))
                if data:
                    self.queue.feed(data, self.now())
                    revolution = self.queue.pop()
                if revolution is None and self.clock() >= deadline:   # cả khi byte vẫn tới mà không ghép được vòng
                    raise ScanReadError(f"{self.source_id}: no complete revolution within {timeout:.1f} s "
                                        f"(stats {self.queue.stats()})")
        self.revolutions += 1
        stamp = SourceStamp(self.source_id, revolution.t_last, True, "lidar")
        scan, quality = revolution_to_scan(revolution, stamp, mirror=self.mirror)
        self.last_quality = quality
        self.last_revolution = revolution
        return scan

    def flush(self) -> None:
        """Drop everything buffered so far (OS buffer and assembled revolutions) after the caller was busy.

        Revolutions are stamped when their bytes ARRIVE at the host; after a long pause the backlog would be
        returned with fresh stamps although it is old. Flushing makes the next revolution genuinely current.
        """
        self.transport.reset_input_buffer()
        self.queue = ScanQueue()

    def stats(self) -> dict:
        return {"revolutions_returned": self.revolutions, "resets": self.resets, **self.queue.stats()}

    def describe(self) -> dict:
        """Everything a recording's meta file should know about the device and this driver."""
        return {"driver": "autopark.lidar.rplidar_c1", "driver_version": DRIVER_VERSION, "scan_mode": "Standard (0x20)",
                "mirror": self.mirror, "source_id": self.source_id,
                "device": self.info.to_dict() if self.info else None,
                "health": self.health.to_dict() if self.health else None}

    def stop(self) -> None:
        if self.started:
            self.stop_output()

    def close(self) -> None:
        try:
            self.stop()
        finally:
            self.transport.close()

    def __enter__(self) -> "RplidarC1Source":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    info = sub.add_parser("info", help="device info, health and the scan modes the device announces")
    info.add_argument("--port", required=True)
    stream = sub.add_parser("stream", help="print one line per revolution for a few seconds")
    stream.add_argument("--port", required=True)
    stream.add_argument("--seconds", type=float, default=5.0)
    stream.add_argument("--mirror", action="store_true")
    args = parser.parse_args(argv)
    source = RplidarC1Source.open(args.port, mirror=getattr(args, "mirror", False))
    try:
        if args.command == "info":
            source.stop_output()
            print(json.dumps({"device": source.device_info().to_dict(), "health": source.device_health().to_dict(),
                              "scan_modes": source.scan_modes()}, ensure_ascii=False, indent=2))
            return 0
        source.start()
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            scan = source.read()
            ranges = np.asarray(scan.ranges_m)
            valid = np.isfinite(ranges)
            print(f"t={scan.stamp.t:7.3f}s beams={len(ranges):4d} valid={int(valid.sum()):4d} "
                  f"min={np.nanmin(ranges) if valid.any() else float('nan'):6.3f} m "
                  f"max={np.nanmax(ranges) if valid.any() else float('nan'):6.3f} m", flush=True)
        print(json.dumps(source.stats()))
        return 0
    finally:
        source.close()


if __name__ == "__main__":
    sys.exit(main())
