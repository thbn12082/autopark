"""Tiny client for the QEMU human monitor (HMP) exposed with -monitor tcp:127.0.0.1:PORT,server=on,wait=off.

Usage:  python qemu_monitor.py [--port 5556] "info qtree" ["system_reset" ...]
Only one client can be connected to the monitor at a time; this opens a connection per command.
"""
from __future__ import annotations

import argparse
import re
import socket
import sys
import time

PROMPT = b"(qemu) "
_ANSI = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]|\x1b[()][A-Za-z0-9]")


def _recv_until(sock: socket.socket, marker: bytes, timeout_s: float) -> bytes:
    data = bytearray()
    deadline = time.monotonic() + timeout_s
    while marker not in data:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        sock.settimeout(left)
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            break
        except OSError:
            break
        if not chunk:
            break
        data += chunk
    return bytes(data)


def hmp(command: str, port: int = 5556, timeout_s: float = 5.0) -> str:
    """Send one HMP command and return its output (ANSI sequences and the echoed command removed)."""
    with socket.create_connection(("127.0.0.1", port), timeout=timeout_s) as sock:
        _recv_until(sock, PROMPT, timeout_s)                    # banner
        sock.sendall(command.encode("ascii") + b"\r\n")
        raw = _recv_until(sock, PROMPT, timeout_s)
    text = _ANSI.sub(b"", raw).decode("utf-8", "replace").replace("\r", "")
    lines = [ln for ln in text.split("\n")]
    if lines and command in lines[0]:
        lines = lines[1:]
    if lines and lines[-1].strip() == "(qemu)":
        lines = lines[:-1]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5556)
    ap.add_argument("commands", nargs="+")
    args = ap.parse_args()
    for cmd in args.commands:
        print(f"### {cmd}")
        print(hmp(cmd, args.port))
    return 0


if __name__ == "__main__":
    sys.exit(main())
