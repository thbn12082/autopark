"""Cổng nối tiếp giả mà đầu kia là `FirmwareModel`: thử `SerialVehicleIO` đúng đường byte của bo thật, không cần bo.

Đồng hồ là `ManualClock` dùng chung cho cả hai đầu: mỗi lần `read()` không có sẵn byte thì đồng hồ tiến
`read_advance_ms` (giống `serial.Serial.read` chờ hết timeout), bo giả chạy các chu kỳ `tick_ms` tới thời điểm mới.
Nhờ vậy test hoàn toàn xác định. `unplug()` làm mọi lần đọc/ghi sau đó ném `OSError` như pyserial khi rút cáp.

Đây KHÔNG phải bằng chứng về bo thật: nó chỉ chứng minh laptop và bản tham chiếu firmware nói cùng một giao thức.
"""
from __future__ import annotations

from typing import Callable

from .firmware_model import FirmwareInputs, FirmwareModel


class ManualClock:
    """Đồng hồ ms nguyên; gọi như hàm trả giây (đồng hồ phiên của `SerialVehicleIO`)."""

    def __init__(self, t_ms: int = 0):
        self.t_ms = int(t_ms)

    def __call__(self) -> float:
        return self.t_ms / 1000.0

    def advance_ms(self, ms: int) -> None:
        if ms < 0:
            raise ValueError("clock cannot go backwards")
        self.t_ms += int(ms)


class FirmwareSerialLoopback:
    """Đối tượng kiểu `serial.Serial` (`write`, `read`, `in_waiting`, `close`) nối tới một `FirmwareModel`."""

    def __init__(self, firmware: FirmwareModel, clock: ManualClock, *, tick_ms: int = 10, read_advance_ms: int = 10,
                 inputs: Callable[[int], FirmwareInputs] | None = None):
        if tick_ms <= 0 or read_advance_ms <= 0:
            raise ValueError("tick_ms and read_advance_ms must be > 0")
        self.firmware = firmware
        self.clock = clock
        self.tick_ms = tick_ms
        self.read_advance_ms = read_advance_ms
        self.inputs = inputs or (lambda t_ms: FirmwareInputs())
        self.next_tick_ms = clock.t_ms + tick_ms
        self.rx = bytearray()               # byte bo đã gửi, laptop chưa đọc
        self.written: list[bytes] = []      # mọi lần laptop ghi (để test kiểm tra byte trên dây)
        self.closed = False
        self.unplugged = False

    def _check(self) -> None:
        if self.unplugged:
            raise OSError("device disconnected (loopback unplugged)")
        if self.closed:
            raise OSError("port closed")

    def run_until(self, t_ms: int) -> None:
        """Chạy các chu kỳ bo tới `t_ms` (không lùi đồng hồ)."""
        while self.next_tick_ms <= t_ms:
            self.clock.t_ms = max(self.clock.t_ms, self.next_tick_ms)
            self.firmware.step(self.next_tick_ms, self.inputs(self.next_tick_ms))
            self.rx += self.firmware.take_tx()
            self.next_tick_ms += self.tick_ms
        self.clock.t_ms = max(self.clock.t_ms, t_ms)

    def advance(self, ms: int) -> None:
        self.run_until(self.clock.t_ms + ms)

    @property
    def in_waiting(self) -> int:
        self._check()
        return len(self.rx)

    def write(self, data: bytes) -> int:
        self._check()
        data = bytes(data)
        self.written.append(data)
        self.firmware.receive(data, self.clock.t_ms)
        self.rx += self.firmware.take_tx()
        return len(data)

    def read(self, n: int = 1) -> bytes:
        self._check()
        if not self.rx:
            self.advance(self.read_advance_ms)
        out = bytes(self.rx[:n])
        del self.rx[:n]
        return out

    def reset_input_buffer(self) -> None:
        self.rx.clear()

    def unplug(self) -> None:
        self.unplugged = True

    def close(self) -> None:
        self.closed = True
