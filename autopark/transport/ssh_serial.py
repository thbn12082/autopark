"""Cổng kiểu `serial.Serial` tới ESP32 cắm USB vào Pi, đi qua SSH (thêm 26/11/2026 cho trang Lái tay).

```
laptop: SerialVehicleIO ── SshSerialPort ── ssh stdin/stdout ──► Pi: BRIDGE_SOURCE ── /dev/ttyACM0 ── ESP32-S3
```

Laptop chạy `ssh -T xe@<ip> python3 -u -c '<cầu nối>'`. Cầu nối trên Pi (`BRIDGE_SOURCE`, Python thuần + pyserial có sẵn
trên Pi) mở cổng USB của ESP32 (VID:PID 303A:1001), gửi một dòng chào `APB1 <cổng>\\n`, rồi chuyển nguyên byte hai chiều:
stdin → ESP32, ESP32 → stdout. Không dịch, không lọc gì: phiên, số thứ tự, CRC và mọi kiểm tra an toàn vẫn là của
`vehicle_io` và firmware. Lỗi trước lời chào (không thấy ESP32, cổng bận) đi về bằng dòng `APB0 <lý do>\\n`.

An toàn khi đứt giữa chừng: laptop đóng hoặc Wi-Fi rớt thì lệnh cuối hết hạn (≤ 300 ms) và bo tự về trung tính, rồi
DISARMED sau `link_timeout` 500 ms (firmware), không cần cầu nối làm gì. SSH thấy stdin hết (EOF) thì cầu nối thoát và
đóng cổng.

Cầu nối khóa cổng bằng TIOCEXCL: trong lúc lái, tiến trình khác trên Pi (ví dụ bước kiểm ESP32 của trang Quan sát Pi)
không mở được cổng, nên không chen HELLO làm mất phiên lái. Vì vậy mở Quan sát Pi TRƯỚC rồi mới kết nối lái tay.

Mật khẩu SSH (Pi chỉ cho đăng nhập bằng mật khẩu) được hỏi trong cửa sổ dòng lệnh đã mở app, như trang Quan sát Pi;
stderr của ssh để nguyên ra cửa sổ đó.
"""
from __future__ import annotations

import base64
import subprocess
import threading
import time
from typing import Callable, Sequence

READY_MAGIC = b"APB1 "
ERROR_MAGIC = b"APB0 "
MAX_BANNER = 512
DEFAULT_READY_TIMEOUT_S = 120.0          # đủ thời gian gõ mật khẩu SSH

BRIDGE_SOURCE = r'''
import fcntl, glob, os, select, sys, termios

ESP32_USB = (0x303A, 0x1001)


def say(prefix, text):
    os.write(1, prefix + text.encode("utf-8", "replace").replace(b"\n", b" ") + b"\n")


def find_port():
    try:
        from serial.tools import list_ports
        found = [p.device for p in list_ports.comports() if (p.vid, p.pid) == ESP32_USB]
    except ImportError:
        found = []
    if not found:
        found = sorted(glob.glob("/dev/ttyACM*"))
    if len(found) != 1:
        raise RuntimeError("cần đúng một ESP32 (USB 303a:1001) cắm vào Pi, đang thấy %s" % (found or "không có"))
    return found[0]


def main():
    try:
        import serial
        port = find_port()
        ser = serial.Serial(port, 115200, timeout=0, write_timeout=0.5)
        try:
            fcntl.ioctl(ser.fileno(), termios.TIOCEXCL)
        except OSError:
            pass
        ser.reset_input_buffer()
    except Exception as exc:
        say(b"APB0 ", "Pi không mở được ESP32: %s" % exc)
        return 2
    say(b"APB1 ", port)
    fd_in, fd_ser = 0, ser.fileno()
    try:
        while True:
            ready, _, _ = select.select([fd_in, fd_ser], [], [], 1.0)
            if fd_in in ready:
                data = os.read(fd_in, 4096)
                if not data:
                    return 0                      # laptop đóng: thoát, đóng cổng
                ser.write(data)
            if fd_ser in ready:
                data = ser.read(ser.in_waiting or 1)
                if data:
                    view = memoryview(data)
                    while view:
                        view = view[os.write(1, view):]
    except (OSError, serial.SerialException) as exc:
        sys.stderr.write("cau noi ESP32 dung: %s\n" % exc)
        return 1
    finally:
        ser.close()


sys.exit(main())
'''


def bridge_command(host: str, *, user: str = "xe", host_key_alias: str = "10.12.194.1") -> list[str]:
    """Lệnh ssh chạy cầu nối trên Pi. Mã cầu nối đi bằng base64 trong một tham số, nên stdin còn trống cho byte lệnh."""
    from autopark.rig.remote_view_link import _USER, _host_name   # cùng kiểm tra tên máy/người dùng với Quan sát Pi

    host = _host_name(host)
    host_key_alias = _host_name(host_key_alias)
    if not isinstance(user, str) or not _USER.fullmatch(user):
        raise ValueError("Tên đăng nhập SSH không hợp lệ")
    code = base64.b64encode(BRIDGE_SOURCE.encode("utf-8")).decode("ascii")
    remote = f"python3 -u -c 'import base64;exec(base64.b64decode(\"{code}\"))'"
    return ["ssh", "-T", "-o", f"HostKeyAlias={host_key_alias}", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=2", "-o", "ServerAliveCountMax=3",
            f"{user}@{host}", remote]


class SshSerialPort:
    """Phía laptop của cầu nối: đủ phần `serial.Serial` mà `SerialVehicleIO` dùng (`in_waiting`, `read`, `write`,
    `reset_input_buffer`, `close`). Mọi lỗi là `OSError`, kể cả khi SSH kết thúc, để `SerialVehicleIO` chuyển thành
    sự kiện LINK_ERROR như rút cáp USB.

    Tạo đối tượng chỉ khởi chạy ssh, không chờ; `wait_ready()` chờ dòng chào (người dùng gõ mật khẩu trong lúc đó).
    `close()` từ luồng khác làm `wait_ready()` thoát ngay với `OSError`."""

    def __init__(self, command: Sequence[str], *, timeout: float | None = 0.01, write_timeout: float | None = 0.05,
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen, label: str = "Pi"):
        self.timeout = timeout
        self.write_timeout = write_timeout        # pipe không có hạn ghi; giữ thuộc tính cho giống pyserial
        self.label = label
        self.port = ""                            # cổng ESP32 trên Pi, biết sau dòng chào
        self._cond = threading.Condition()
        self._buf = bytearray()
        self._banner = bytearray()
        self._ready = False
        self._ended: str | None = None            # lý do luồng đã hết (None: còn chạy)
        self._closed = False
        self._process = popen(list(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        self._reader = threading.Thread(target=self._read_loop, name="autopark-ssh-serial", daemon=True)
        self._reader.start()

    @classmethod
    def to_pi(cls, host: str, *, user: str = "xe", host_key_alias: str = "10.12.194.1", **kwargs) -> "SshSerialPort":
        return cls(bridge_command(host, user=user, host_key_alias=host_key_alias), label=f"{user}@{host}", **kwargs)

    # ---- luồng đọc ---------------------------------------------------------------------------------------------
    def _read_loop(self) -> None:
        stdout = self._process.stdout
        reason = f"SSH tới {self.label} đã kết thúc"
        try:
            while True:
                chunk = stdout.read(4096)
                if not chunk:
                    break
                with self._cond:
                    if self._ready:
                        self._buf += chunk
                    else:
                        self._take_banner(chunk)
                    self._cond.notify_all()
                    if self._ended is not None:
                        return
        except (OSError, ValueError) as exc:
            reason = f"SSH tới {self.label} lỗi: {exc}"
        code = None
        try:
            code = self._process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass
        with self._cond:
            if self._ended is None:
                self._ended = reason + (f" (mã {code})" if code not in (None, 0) else "")
            self._cond.notify_all()

    def _take_banner(self, chunk: bytes) -> None:
        self._banner += chunk
        line, sep, rest = bytes(self._banner).partition(b"\n")
        if not sep:
            if len(self._banner) > MAX_BANNER:
                self._ended = f"{self.label} không gửi lời chào cầu nối APB1"
            return
        text = line[len(READY_MAGIC):].decode("utf-8", "replace").strip()
        if line.startswith(READY_MAGIC):
            self._ready = True
            self.port = text
            self._buf += rest
        elif line.startswith(ERROR_MAGIC):
            self._ended = text or "Pi báo lỗi cầu nối"
        else:
            self._ended = f"{self.label} không gửi lời chào cầu nối APB1 (nhận {line[:60]!r})"

    # ---- dùng như serial.Serial -------------------------------------------------------------------------------
    def wait_ready(self, timeout_s: float = DEFAULT_READY_TIMEOUT_S) -> str:
        """Chờ cầu nối trên Pi mở xong ESP32; trả tên cổng trên Pi. Hết giờ, lỗi, hay `close()`: `OSError`."""
        deadline = time.monotonic() + timeout_s
        with self._cond:
            while not self._ready:
                if self._ended is not None:
                    raise OSError(self._ended)
                left = deadline - time.monotonic()
                if left <= 0:
                    raise OSError(f"Hết {timeout_s:.0f} s chờ {self.label} (đã gõ mật khẩu SSH chưa?)")
                self._cond.wait(min(left, 0.2))
            return self.port

    def _check(self) -> None:
        if self._closed:
            raise OSError("cổng SSH đã đóng")
        if not self._ready:
            raise OSError(self._ended or "cầu nối chưa sẵn sàng")
        if self._ended is not None and not self._buf:
            raise OSError(self._ended)

    @property
    def in_waiting(self) -> int:
        with self._cond:
            self._check()
            return len(self._buf)

    def read(self, size: int = 1) -> bytes:
        with self._cond:
            self._check()
            if not self._buf and self.timeout != 0 and self._ended is None:
                self._cond.wait(self.timeout)
            out = bytes(self._buf[:size])
            del self._buf[:size]
            return out

    def write(self, data) -> int:
        with self._cond:
            self._check()
            if self._ended is not None:
                raise OSError(self._ended)
        data = bytes(data)
        try:
            view = memoryview(data)
            while view:
                written = self._process.stdin.write(view)
                if written is None:
                    raise OSError("pipe SSH không nhận dữ liệu")
                view = view[written:]
            self._process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise OSError(f"Không gửi được tới {self.label}: {exc}") from exc
        return len(data)

    def reset_input_buffer(self) -> None:
        with self._cond:
            self._buf.clear()

    def close(self) -> None:
        with self._cond:
            if self._closed:
                return
            self._closed = True
            if self._ended is None:
                self._ended = "cổng SSH đã đóng"
            self._cond.notify_all()
        process = self._process
        try:
            process.stdin.close()                 # cầu nối trên Pi thấy EOF, đóng cổng ESP32 rồi thoát
        except OSError:
            pass
        try:
            process.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
        if process.stdout is not None:
            try:
                process.stdout.close()
            except OSError:
                pass
