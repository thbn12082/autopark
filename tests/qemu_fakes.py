"""Bo ảo QEMU GIẢ cho test (thêm 02/10/2026; mẫu của tests/rig_fakes.py): không chạy QEMU, không mở cổng nào.

`FakeQemuBoard` là một `FirmwareModel(FirmwareConfig(boot_hold_ms=100))` theo `ManualClock`: bản tham chiếu byte-đúng của
firmware trong QEMU (không có ngõ vào nào, trần effort 250 ‰ như bản build esp32s3_qemu). Như QEMU, bo chỉ phục vụ MỘT
client TCP (client thứ hai mở khi client đầu còn mở → AssertionError: lỗi thiết kế phải lộ ra), và khung bo gửi khi
không có client nào bị bỏ. `start()` như `QemuBoard.start()`: HELLO trên một kết nối thử rồi đóng, giữ HELLO_ACK ở
`hello`. Kết quả chạy trên bo giả là của bản tham chiếu Python, không phải của QEMU hay của bo thật.
"""
from __future__ import annotations

from pathlib import Path

from autopark.transport.firmware_model import FirmwareConfig, FirmwareModel
from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock
from autopark.transport.protocol import HOST_TO_DEVICE, FrameParser
from autopark.transport.qemu_board import QemuBoardError, QemuTools
from autopark.transport.vehicle_io import SerialVehicleIO

BOOT_ID = 0xB0A00001
URL = "socket://127.0.0.1:5999"


class FakeClient:
    """Một kết nối TCP giả tới UART0 (kiểu `serial.Serial`). Đọc khi rỗng tiến đồng hồ 10 ms (như chờ timeout đọc);
    QEMU đã thoát → ConnectionResetError như `SocketPort`."""

    def __init__(self, board: "FakeQemuBoard"):
        self.board = board
        self.closed = False

    def _check(self) -> None:
        if self.closed:
            raise OSError("cổng TCP đã đóng")
        if not self.board.alive:
            raise ConnectionResetError("bên kia đã đóng kết nối TCP (QEMU đã thoát)")

    @property
    def in_waiting(self) -> int:
        self._check()
        return len(self.board.loop.rx)

    def read(self, n: int = 1) -> bytes:
        self._check()
        return self.board.loop.read(n)

    def write(self, data) -> int:
        self._check()
        return self.board.loop.write(data)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.board._client_closed(self)


class FakeQemuBoard:
    """Bo ảo giả (một `QemuBoardHandle`): `url`, `hello`, `clock`, `running()`, `transport_opener()`, `describe()`;
    `advance(ms)` cho bo chạy, `stall(ms)` làm QEMU bị bỏ đói (LOOP_OVERRUN), `host_messages()` là mọi thông điệp laptop
    đã ghi. `opened` đếm kết nối do io mở (không tính kết nối thử của `start()`)."""

    url = URL

    def __init__(self, *, boot_id: int = BOOT_ID, firmware_config: FirmwareConfig | None = None):
        self.clock = ManualClock()
        self.firmware = FirmwareModel(firmware_config or FirmwareConfig(boot_hold_ms=100), boot_id=boot_id)
        self.loop = FirmwareSerialLoopback(self.firmware, self.clock)
        self.client: FakeClient | None = None
        self.opened = 0
        self.alive = False
        self.hello = None
        self.starts = 0
        self.stops = 0
        self.problems: list[str] = []
        self.workdir: Path | None = None
        self.exit_code: int | None = None
        self.fail_start: str | None = None         # đặt chữ → start() ném QemuBoardError với chữ đó
        self.refuse_connections = False            # True → mở kết nối hỏng (ConnectionRefusedError)
        self.image_sha256 = "ab" * 32

    # ---- QemuBoardHandle -------------------------------------------------------------------------------------------
    def running(self) -> bool:
        return self.alive

    def transport_opener(self, read_timeout_s: float = 0.01, write_timeout_s: float = 0.05):
        def opener():
            return self._open(count=True)

        return opener

    def describe(self) -> dict:
        hello = self.hello
        return {"url": self.url, "monitor_port": 5998, "image": "gia/qemu_flash.bin", "image_sha256": self.image_sha256,
                "qemu": "gia/qemu-system-xtensa.exe", "pid": 4242, "starts": self.starts,
                "problems": list(self.problems), "workdir": str(self.workdir) if self.workdir else None,
                "hello": None if hello is None else {"firmware": hello.firmware_version,
                                                     "boot_id": f"0x{hello.boot_id:08x}", "reset_reason": "POWER_ON",
                                                     "telemetry_period_ms": round(hello.telemetry_period_s * 1000)}}

    # ---- vòng đời như QemuBoard ------------------------------------------------------------------------------------
    def start(self) -> "FakeQemuBoard":
        self.starts += 1
        if self.workdir is not None:                     # như QemuBoard._launch: bản sao ảnh và các tệp log
            for name in ("flash.bin", "uart0.log", "qemu.err", "qemu.out", "qemu_cmdline.txt"):
                (self.workdir / name).write_bytes(b"\xff" * 64 if name == "flash.bin" else b"")
        if self.fail_start:
            self.problems.append(self.fail_start)
            raise QemuBoardError(self.fail_start)
        self.alive = True
        self.exit_code = None
        self.advance(150)                                # qua thời gian giữ khởi động (100 ms)
        io = SerialVehicleIO(self._open(count=False), clock=self.clock)
        try:
            self.hello = io.connect()
        finally:
            io.close()
        return self

    def stop(self) -> None:
        self.stops += 1
        self.alive = False
        self.exit_code = 0 if self.exit_code is None else self.exit_code

    def die(self, code: int = 3221225477) -> None:
        """QEMU tự thoát (espressif/qemu#175 hay lỗi khác)."""
        self.alive = False
        self.exit_code = code

    def cpu_seconds(self) -> float:
        return 1.25

    # ---- điều khiển bo giả -----------------------------------------------------------------------------------------
    def advance(self, ms: int) -> None:
        """Bo chạy thêm `ms` (đồng hồ tiến). Không có client: khung bo gửi bị bỏ, như QEMU."""
        self.loop.advance(ms)
        if self.client is None:
            self.loop.rx.clear()

    def stall(self, ms: int) -> None:
        """QEMU bị máy chủ bỏ đói `ms`: đồng hồ đi tiếp mà firmware không chạy nhịp nào (> 100 ms → LOOP_OVERRUN)."""
        self.clock.advance_ms(ms)
        self.loop.next_tick_ms = max(self.loop.next_tick_ms, self.clock.t_ms + self.loop.tick_ms)

    def host_messages(self, start: int = 0) -> list:
        """Mọi thông điệp laptop đã ghi ra UART0 (từ lần ghi thứ `start`), qua mọi kết nối."""
        parser = FrameParser(accept_types=HOST_TO_DEVICE)
        out = []
        for chunk in self.loop.written[start:]:
            out.extend(parser.feed(chunk))
        return out

    def _open(self, *, count: bool) -> FakeClient:
        if not self.alive or self.refuse_connections:
            raise ConnectionRefusedError(f"[WinError 10061] không kết nối được {self.url}")
        assert self.client is None or self.client.closed, \
            "QEMU chỉ phục vụ một client: kết nối thứ hai mở khi kết nối đầu còn mở"
        self.loop.rx.clear()                             # byte bo gửi lúc chưa có client đã mất
        self.client = FakeClient(self)
        if count:
            self.opened += 1
        return self.client

    def _client_closed(self, client: FakeClient) -> None:
        if self.client is client:
            self.client = None


class FakeQemuSource:
    """`QemuBoardSource` đơn giản: bo khi nó chạy, không thì (None, `reason`)."""

    def __init__(self, board: FakeQemuBoard | None, reason: str = "bo ảo chưa chạy"):
        self.board = board
        self.reason = reason
        self.calls = 0

    def current_board(self):
        self.calls += 1
        if self.board is not None and self.board.running():
            return self.board, ""
        return None, self.reason


def make_runner(tmp_path: Path, board: FakeQemuBoard, *, tools_error: str | None = None,
                image_error: str | None = None, built: bool = False):
    """`QemuBoardRunner` THẬT với công cụ, `ensure_image` và `board_factory` giả, luồng nền đồng bộ. `runner.calls` đếm
    lời gọi. Không đọc configs/thiet_bi.json, không gọi PlatformIO hay QEMU."""
    from autopark.ui.qemu_runner import QemuBoardRunner

    calls = {"tools": 0, "ensure": 0, "factory": 0}
    tools = QemuTools(tmp_path / "qemu-system-xtensa.exe", tmp_path / "python.exe")

    def tools_loader():
        calls["tools"] += 1
        if tools_error:
            raise QemuBoardError(tools_error)
        return tools

    def ensure_image(_tools, *, log_path=None, **_kwargs):
        calls["ensure"] += 1
        if log_path is not None and (built or image_error):
            Path(log_path).write_text("$ pio run -e esp32s3_qemu (giả)\n" + (image_error or "xong"), encoding="utf-8")
        if image_error:
            raise QemuBoardError(image_error)
        return tmp_path / "qemu_flash.bin", built

    def board_factory(_image, _tools, *, workdir=None, **_kwargs):
        calls["factory"] += 1
        board.workdir = Path(workdir) if workdir is not None else None
        return board

    runner = QemuBoardRunner(runs_dir=tmp_path / "runs", tools_loader=tools_loader, ensure_image=ensure_image,
                             board_factory=board_factory, spawn=lambda fn: fn())
    runner.calls = calls
    return runner
