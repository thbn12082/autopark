"""Cổng kiểu `serial.Serial` trên một kết nối TCP (thêm 30/09/2026): URL `socket://host:port` của
`SerialVehicleIO.open()`, dùng cho bo ảo QEMU (`autopark.transport.qemu_board`, docs/PHAN_CUNG_VA_HIEU_CHUAN.md).

Không dùng `socket://` của pyserial 3.5 vì ba điểm đọc được trong mã nguồn của nó (`serial/urlhandler/protocol_socket.py`)
và đo được với bo ảo ngày 29–30/09/2026:
- `in_waiting` chỉ trả 0 hoặc 1 (kết quả `select`), nên `SerialVehicleIO._pump` đọc từng byte;
- `write()` kiểm hạn ghi SAU khi đã gửi xong: tiến trình bị trễ lịch lâu hơn hạn thì báo "Write timeout" dù đã gửi hết;
- `close()` ngủ 0,3 s.
Ở đây `in_waiting` là số byte thật (dồn mọi byte socket đang có vào bộ đệm, không chờ); `read(n)` trả tối đa n byte và
chỉ chờ (tới `timeout`) khi bộ đệm rỗng — khác pyserial ở chỗ không chờ cho đủ n byte; `write()` chỉ báo lỗi khi socket
thật sự không nhận hết dữ liệu trong `write_timeout`. Mọi lỗi là `OSError` như pyserial, kể cả khi bên kia đóng kết nối.
"""
from __future__ import annotations

import select
import socket
from urllib.parse import urlsplit

_FILL_LIMIT = 1 << 20                       # bộ đệm tối đa 1 MB mỗi lần dồn (chặn vòng lặp khi bên kia gửi dồn dập)


class SocketPort:
    def __init__(self, host: str, port: int, *, timeout: float | None = 0.01, write_timeout: float | None = 0.05,
                 connect_timeout: float = 2.0):
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.port = f"socket://{host}:{port}"
        self._buf = bytearray()
        self._sock: socket.socket | None = socket.create_connection((host, port), timeout=connect_timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock.settimeout(None)         # chặn; mỗi thao tác tự giới hạn thời gian bằng select hoặc settimeout

    @classmethod
    def from_url(cls, url: str, **kwargs) -> "SocketPort":
        parts = urlsplit(url)
        if parts.scheme.lower() != "socket" or not parts.hostname or parts.port is None:
            raise ValueError(f"URL phải có dạng socket://host:port (đang là {url!r})")
        return cls(parts.hostname, parts.port, **kwargs)

    def _socket(self) -> socket.socket:
        if self._sock is None:
            raise OSError("cổng TCP đã đóng")
        return self._sock

    def _fill(self) -> None:
        sock = self._socket()
        while len(self._buf) < _FILL_LIMIT:
            readable, _, _ = select.select([sock], [], [], 0)
            if not readable:
                return
            chunk = sock.recv(65536)
            if not chunk:
                raise ConnectionResetError("bên kia đã đóng kết nối TCP")
            self._buf += chunk

    @property
    def in_waiting(self) -> int:
        self._fill()
        return len(self._buf)

    def read(self, size: int = 1) -> bytes:
        self._fill()
        if not self._buf and self.timeout != 0:
            readable, _, _ = select.select([self._socket()], [], [], self.timeout)
            if readable:
                self._fill()
        out = bytes(self._buf[:size])
        del self._buf[:size]
        return out

    def write(self, data) -> int:
        sock = self._socket()
        data = bytes(data)
        sock.settimeout(self.write_timeout)
        try:
            sock.sendall(data)              # hết hạn mà chưa gửi xong: TimeoutError (là OSError)
        finally:
            sock.settimeout(None)
        return len(data)

    def reset_input_buffer(self) -> None:
        self._fill()
        self._buf.clear()

    def close(self) -> None:
        sock, self._sock = self._sock, None
        if sock is not None:
            sock.close()
