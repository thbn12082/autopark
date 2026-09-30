"""QEMU ESP32-S3 feasibility probe for the autopark firmware (UART0 build), using the project's own transport code.

QEMU must be started with the emulated UART0 on a TCP server, e.g.
  qemu-system-xtensa -machine esp32s3 -display none -drive file=img\\flash_uart0.bin,if=mtd,format=raw ^
      -serial tcp:127.0.0.1:5555,server=on,wait=on -monitor tcp:127.0.0.1:5556,server=on,wait=off
(wait=on: the guest does not start before this script connects, so the ROM output is captured too).

Phases (one run, one QEMU instance):
  boot       raw capture of ROM / 2nd-stage bootloader / app output
  proto      SerialVehicleIO(serial_for_url('socket://...')): HELLO/HELLO_ACK, telemetry, ARM, COMMAND with a short
             validity (RUNNING -> ARMED on COMMAND_TIMEOUT), silence (-> DISARMED on LINK_TIMEOUT), a rejected
             COMMAND, a 20 Hz command stream, stop, DISARM
  loop       Session-style loop: poll(block=False) + send() at 50 Hz, plain socket:// vs a counting adapter
  reconnect  close + reopen the socket, new session: same boot_id expected
  reset      HMP system_reset while connected: stale telemetry, reboot text, new session with a new boot_id

Run from the repo root so autopark is importable; -B keeps Python from writing .pyc files into the repo:
  cd /d D:\\xetulai\\autopark\\autopark
  .venv\\Scripts\\python.exe -B D:\\xetulai\\_platformio\\kiem_qemu\\qemu_probe.py --tag uart0
Everything is written to D:\\xetulai\\_platformio\\kiem_qemu\\logs.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import statistics
import sys
import time

import serial

from autopark.transport.protocol import ResetReason, State, TelemetryFlag
from autopark.transport.vehicle_io import SerialVehicleIO, VehicleIOError

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from qemu_monitor import hmp  # noqa: E402

LOGS = HERE / "logs"


def say(*args) -> None:
    print(*args, flush=True)


# ---- raw UART capture -----------------------------------------------------------------------------------------------
def render(data: bytes) -> str:
    out = []
    for b in data:
        if b in (9, 10) or 32 <= b < 127:
            out.append(chr(b))
        elif b != 13:
            out.append(f"\\x{b:02x}")
    return "".join(out)


def open_port(url: str, retry_s: float = 30.0):
    deadline = time.monotonic() + retry_s
    while True:
        try:
            return serial.serial_for_url(url, timeout=0.01)
        except serial.SerialException:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


def capture(ser, max_s: float, quiet_s: float, min_s: float = 0.0):
    """Read raw bytes until max_s, or quiet_s of silence after the first byte (and at least min_s)."""
    t0 = time.perf_counter()
    data = bytearray()
    lines: list[tuple[float, str]] = []
    cur = bytearray()
    cur_t = None
    t_first = t_last = None
    while True:
        now = time.perf_counter() - t0
        if now >= max_s:
            break
        if t_last is not None and now - t_last >= quiet_s and now >= min_s:
            break
        chunk = ser.read(4096)
        if not chunk:
            continue
        t = time.perf_counter() - t0
        t_first = t if t_first is None else t_first
        t_last = t
        data += chunk
        for b in chunk:
            if cur_t is None:
                cur_t = t
            if b == 10:
                lines.append((cur_t, render(bytes(cur))))
                cur.clear()
                cur_t = None
            else:
                cur.append(b)
    if cur:
        lines.append((cur_t, render(bytes(cur))))
    return bytes(data), lines, t_first, t_last


def write_capture(tag: str, name: str, data: bytes, lines) -> Path:
    (LOGS / f"{tag}_{name}.bin").write_bytes(data)
    path = LOGS / f"{tag}_{name}.txt"
    path.write_text("".join(f"[{t:8.3f}] {s}\n" for t, s in lines), encoding="utf-8")
    return path


# ---- project transport with a raw tap -------------------------------------------------------------------------------
class TeeIO(SerialVehicleIO):
    """SerialVehicleIO that also keeps every received byte, to see non-protocol output such as a reboot log."""

    def __init__(self, transport, **kwargs):
        super().__init__(transport, **kwargs)
        self.rx = bytearray()
        self.rx_bursts: list[tuple[float, int]] = []    # (host time, rx offset) when bytes arrive after a 0.2 s pause
        self._last_rx_t = None
        self.pumps = 0

    def _pump(self, block: bool = True) -> None:
        self.pumps += 1
        super()._pump(block)

    def _on_bytes(self, data: bytes, t: float) -> None:
        if self._last_rx_t is None or t - self._last_rx_t > 0.2:
            self.rx_bursts.append((round(t, 4), len(self.rx)))
        self._last_rx_t = t
        self.rx += data
        super()._on_bytes(data, t)


class CountingPort:
    """pyserial's socket:// reports in_waiting as 0 or 1 (select() readability), so SerialVehicleIO._pump reads one
    byte per call. This adapter drains the socket without blocking and reports the real count, like a COM port."""

    def __init__(self, inner):
        self.inner = inner
        self.buf = bytearray()

    def _fill(self) -> None:
        saved = self.inner.timeout
        self.inner.timeout = 0
        try:
            while True:
                chunk = self.inner.read(4096)
                if not chunk:
                    break
                self.buf += chunk
        finally:
            self.inner.timeout = saved

    @property
    def in_waiting(self) -> int:
        self._fill()
        return len(self.buf)

    def read(self, n: int = 1) -> bytes:
        if not self.buf:
            return self.inner.read(n)
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def write(self, data: bytes):
        return self.inner.write(data)

    def close(self) -> None:
        self.inner.close()


# ---- helpers --------------------------------------------------------------------------------------------------------
def flag_names(flags) -> str:
    names = [f.name for f in TelemetryFlag if flags & f]
    return "|".join(names) if names else "0"


def row(tel) -> dict:
    return {"t": round(tel.stamp.t, 4), "dev_ms": tel.device_time_ms, "seq": tel.sequence, "state": tel.state.name,
            "fault": tel.fault.name, "stop": tel.stop_reason.name, "flags": flag_names(tel.flags),
            "speed_ref": tel.speed_ref_mps, "steer_ref": tel.steer_ref_rad, "effort": tel.effort,
            "last_cmd": tel.last_cmd_seq, "cmd_age_s": tel.cmd_age_s, "rx_err": tel.rx_errors, "rejects": tel.rejects}


def transitions(tels) -> list[dict]:
    out, key = [], None
    for tel in tels:
        k = (tel.state.name, tel.stop_reason.name, tel.fault.name, flag_names(tel.flags))
        if k != key:
            out.append({"t": round(tel.stamp.t, 4), "dev_ms": tel.device_time_ms, "state": k[0], "stop": k[1],
                        "fault": k[2], "flags": k[3]})
            key = k
    return out


def quantile(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))]


def timing(tels) -> dict:
    if len(tels) < 3:
        return {"n": len(tels)}
    ts = [x.stamp.t for x in tels]
    ds = [x.device_time_ms for x in tels]
    host_dt = [(b - a) * 1000.0 for a, b in zip(ts, ts[1:])]
    dev_dt = [(b - a) & 0xFFFFFFFF for a, b in zip(ds, ds[1:])]
    n = len(ts)
    mx, my = sum(ts) / n, sum(ds) / n
    sxx = sum((x - mx) ** 2 for x in ts)
    sxy = sum((x - mx) * (y - my) for x, y in zip(ts, ds))
    offs = [t * 1000.0 - d for t, d in zip(ts, ds)]
    return {"n": n, "host_span_s": round(ts[-1] - ts[0], 4), "dev_span_ms": (ds[-1] - ds[0]) & 0xFFFFFFFF,
            "rate_hz_host": round((n - 1) / (ts[-1] - ts[0]), 3),
            "host_dt_ms": {"min": round(min(host_dt), 2), "p50": round(statistics.median(host_dt), 2),
                           "p95": round(quantile(host_dt, 0.95), 2), "max": round(max(host_dt), 2)},
            "dev_dt_ms": {"min": min(dev_dt), "p50": statistics.median(dev_dt), "max": max(dev_dt)},
            "device_ms_per_host_ms": round(sxy / sxx / 1000.0, 5),
            "host_minus_dev_offset_spread_ms": round(max(offs) - min(offs), 2)}


def pump_for(io, seconds: float, ping_every: float | None = None, block: bool = True) -> list:
    tels = []
    end = io.now() + seconds
    while io.now() < end:
        tels.extend(io.poll(block=block))
        if ping_every is not None and io.connected and io.now() - io.last_tx_time >= ping_every:
            io.ping(wait=False)
    return tels


def connect_retry(io, tries: int = 4, timeout_s: float = 1.5):
    last = None
    for i in range(tries):
        t_send = io.now()
        try:
            info = io.connect(timeout_s=timeout_s)
            return info, (info.received_at - t_send) * 1000.0, i + 1
        except VehicleIOError as exc:
            last = exc
    raise last


def hello_dict(info, rtt_ms, attempts) -> dict:
    rr = ResetReason(info.reset_reason).name if info.reset_reason in ResetReason._value2member_map_ else "?"
    return {"session_id": f"{info.session_id:08x}", "boot_id": f"{info.boot_id:08x}", "fw": info.firmware_version,
            "reset_reason": f"{info.reset_reason} ({rr})", "state": info.state.name,
            "telemetry_period_s": info.telemetry_period_s, "limits": asdict(info.limits),
            "hello_ack_rtt_ms": round(rtt_ms, 2), "attempts": attempts}


def events_list(io) -> list[dict]:
    return [{"t": round(e.stamp.t, 4), "code": e.code, "action": e.action, "message": e.message} for e in io.events()]


def stats_dict(io) -> dict:
    d = asdict(io.stats)
    d["parser"] = io.parser.stats.as_dict()
    return d


# ---- phases ---------------------------------------------------------------------------------------------------------
def phase_proto(io, report: dict) -> None:
    info, rtt, attempts = connect_retry(io)
    report["hello"] = hello_dict(info, rtt, attempts)
    say("HELLO_ACK:", json.dumps(report["hello"]))
    report["wait_ready_state"] = io.wait_ready(timeout_s=3.0).name
    first = io.latest()
    report["first_telemetry"] = row(first) if first else None

    steps = {}
    # A: DISARMED, PING every 100 ms, 2 s
    tels = pump_for(io, 2.0, ping_every=0.1)
    steps["A_idle_disarmed_2s"] = {"timing": timing(tels), "transitions": transitions(tels)}
    say("A idle:", json.dumps(steps["A_idle_disarmed_2s"]["timing"]))

    # B: ARM
    io.arm()
    arm_rtt = io.stats.ack_rtt_s
    tels = pump_for(io, 0.3, ping_every=0.1)
    steps["B_arm"] = {"ack_rtt_ms": round(arm_rtt * 1000, 2), "transitions": transitions(tels)}
    say("B arm:", json.dumps(steps["B_arm"]))

    # C: one COMMAND, validity 250 ms, then only PINGs (PING keeps the link, does not renew the command)
    seq = io.send(0.2, 0.1, enable=True, validity_s=0.25)
    t_cmd = io.now()
    tels = pump_for(io, 0.8, ping_every=0.1)
    running = [x for x in tels if x.state == State.RUNNING]
    after = [x for x in tels if x.state == State.ARMED and x.last_cmd_seq == seq]
    cmd_rx_dev = None
    for x in tels:
        if x.last_cmd_seq == seq and x.cmd_age_s is not None:
            cmd_rx_dev = x.device_time_ms - round(x.cmd_age_s * 1000)
            break
    first_armed = next((x for x in tels if x.state == State.ARMED and x.stop_reason.name == "COMMAND_TIMEOUT"), None)
    steps["C_command_validity_250ms"] = {
        "cmd_seq": seq, "cmd_echo_ms": None if io.stats.cmd_echo_s is None else round(io.stats.cmd_echo_s * 1000, 2),
        "running_frames": len(running), "armed_after_frames": len(after),
        "device_ms_cmd_rx": cmd_rx_dev,
        "device_ms_first_armed_telemetry": first_armed.device_time_ms if first_armed else None,
        "host_s_after_send_first_armed": round(first_armed.stamp.t - t_cmd, 4) if first_armed else None,
        "max_speed_ref": max((x.speed_ref_mps for x in tels), default=None),
        "max_effort": max((x.effort for x in tels), default=None),
        "transitions": transitions(tels), "rows": [row(x) for x in tels]}
    say("C cmd:", json.dumps({k: v for k, v in steps["C_command_validity_250ms"].items() if k != "rows"}))

    # D: host silent (no PING) -> firmware link timeout 500 ms -> DISARMED
    t_last_tx = io.last_tx_time
    tels = pump_for(io, 1.2, ping_every=None)
    first_dis = next((x for x in tels if x.state == State.DISARMED), None)
    first_nolink = next((x for x in tels if not x.link_ok), None)
    steps["D_link_timeout"] = {
        "host_s_last_tx_to_first_disarmed_telemetry": round(first_dis.stamp.t - t_last_tx, 4) if first_dis else None,
        "host_s_last_tx_to_first_link_ok_cleared": round(first_nolink.stamp.t - t_last_tx, 4) if first_nolink else None,
        "transitions": transitions(tels)}
    say("D link timeout:", json.dumps(steps["D_link_timeout"]))

    # E: COMMAND while DISARMED -> firmware rejects with an ACK (BAD_STATE expected)
    io.send(0.1, 0.0, enable=True, validity_s=0.2)
    tels = pump_for(io, 0.3, ping_every=0.1)
    steps["E_reject_when_disarmed"] = {"rejected": dict(io.stats.rejected), "transitions": transitions(tels)}
    say("E reject:", json.dumps(steps["E_reject_when_disarmed"]))

    # F: ARM, 20 Hz command stream for 1.5 s (0.25 m/s, 0.2 rad), stop(), DISARM
    io.arm()
    tels = []
    t_end = io.now() + 1.5
    next_send = io.now()
    sent = 0
    while io.now() < t_end:
        if io.now() >= next_send:
            io.send(0.25, 0.2, enable=True, validity_s=0.15)
            sent += 1
            next_send += 0.05
        tels.extend(io.poll(block=True))
    io.stop()
    tels_stop = pump_for(io, 0.4, ping_every=0.1)
    io.disarm()
    tels_dis = pump_for(io, 0.3, ping_every=0.1)
    allf = tels + tels_stop + tels_dis
    steps["F_stream_20hz"] = {
        "commands_sent": sent, "timing_during_stream": timing(tels),
        "cmd_echo_last_ms": None if io.stats.cmd_echo_s is None else round(io.stats.cmd_echo_s * 1000, 2),
        "cmd_echo_max_ms": None if io.stats.cmd_echo_max_s is None else round(io.stats.cmd_echo_max_s * 1000, 2),
        "speed_ref_last_in_stream": tels[-1].speed_ref_mps if tels else None,
        "steer_ref_last_in_stream": tels[-1].steer_ref_rad if tels else None,
        "effort_last_in_stream": tels[-1].effort if tels else None,
        "transitions": transitions(allf), "rows": [row(x) for x in allf]}
    say("F stream:", json.dumps({k: v for k, v in steps["F_stream_20hz"].items() if k != "rows"}))
    report["steps"] = steps
    report["events"] = events_list(io)
    report["stats"] = stats_dict(io)
    report["pumps"] = io.pumps


def phase_loop(url_port, make_io, label: str, seconds: float = 2.0) -> dict:
    """50 Hz loop like Session: poll(block=False) then send(); counts what reaches the laptop."""
    io = make_io(url_port)
    info, rtt, attempts = connect_retry(io)
    io.wait_ready(3.0)
    io.arm()
    got = []
    errors = []
    t_end = io.now() + seconds
    cycles = 0
    while io.now() < t_end:
        t_cycle = io.now()
        got.extend(io.poll(block=False))
        try:
            io.send(0.1, 0.0, enable=True, validity_s=0.15)
        except VehicleIOError as exc:
            errors.append(str(exc)[:120])
        cycles += 1
        rest = 0.02 - (io.now() - t_cycle)
        if rest > 0:
            time.sleep(rest)
    try:
        io.stop()
        io.disarm(timeout_s=1.0)
    except VehicleIOError as exc:
        errors.append("cleanup: " + str(exc)[:120])
    res = {"label": label, "cycles": cycles, "telemetry_received": len(got), "expected_approx": int(seconds * 20),
           "send_errors": len(errors), "first_errors": errors[:3], "events": [e["code"] for e in events_list(io)],
           "pumps": io.pumps, "timing": timing(got), "stats": stats_dict(io)}
    say(f"loop[{label}]:", json.dumps({k: v for k, v in res.items() if k not in ("stats",)}))
    return res, io


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="uart0")
    ap.add_argument("--url", default="socket://127.0.0.1:5555")
    ap.add_argument("--monitor-port", type=int, default=5556)
    ap.add_argument("--phases", default="boot,proto,loop,reconnect,reset")
    args = ap.parse_args()
    phases = set(args.phases.split(","))
    LOGS.mkdir(exist_ok=True)
    report: dict = {"tag": args.tag, "url": args.url, "started": time.strftime("%Y-%m-%d %H:%M:%S")}

    say(f"connecting {args.url} ...")
    t_open = time.perf_counter()
    ser = open_port(args.url)
    report["port_open_s"] = round(time.perf_counter() - t_open, 3)

    if "boot" in phases:
        data, lines, t_first, t_last = capture(ser, max_s=20.0, quiet_s=2.0, min_s=3.0)
        path = write_capture(args.tag, "boot", data, lines)
        report["boot"] = {"bytes": len(data), "lines": len(lines), "first_byte_s": t_first, "last_byte_s": t_last,
                          "file": str(path)}
        say(f"boot: {len(data)} bytes, {len(lines)} lines, first {t_first}, last {t_last} -> {path}")
        for t, s in lines:
            say(f"  [{t:7.3f}] {s}")

    io = None
    if "hello" in phases:                      # light check for variants: HELLO_ACK + 1 s of telemetry
        io = TeeIO(CountingPort(ser))
        try:
            info, rtt, attempts = connect_retry(io, tries=3, timeout_s=1.5)
            report["hello"] = hello_dict(info, rtt, attempts)
            say("HELLO_ACK:", json.dumps(report["hello"]))
            tels = pump_for(io, 1.0, ping_every=0.1)
            report["hello_timing"] = timing(tels)
            report["hello_transitions"] = transitions(tels)
            say("telemetry:", json.dumps(report["hello_timing"]), json.dumps(report["hello_transitions"]))
        except VehicleIOError as exc:
            report["hello_error"] = str(exc)
            say("HELLO failed:", exc)
        finally:
            (LOGS / f"{args.tag}_hello_rx.bin").write_bytes(bytes(io.rx))
            report["hello_rx_bytes"] = len(io.rx)
            report["hello_stats"] = stats_dict(io)
            say("rx bytes:", len(io.rx), "parser:", json.dumps(io.parser.stats.as_dict()))
        io.close()
        phases.discard("proto")
    if "proto" in phases:
        io = TeeIO(ser)
        try:
            phase_proto(io, report)
        finally:
            (LOGS / f"{args.tag}_proto_rx.bin").write_bytes(bytes(io.rx))
            report.setdefault("stats", stats_dict(io))
            report.setdefault("events", events_list(io))
            report["rx_bytes"] = len(io.rx)
            report["rx_bursts"] = io.rx_bursts[:20]
        known_boot = io.known_boot_id
        io.close()
    else:
        ser.close()
        known_boot = None

    if "loop" in phases:
        plain, io_a = phase_loop(args.url, lambda url: TeeIO(open_port(url)), "plain socket://")
        io_a.close()
        counted, io_b = phase_loop(args.url, lambda url: TeeIO(CountingPort(open_port(url))), "CountingPort adapter")
        io_b.close()
        report["loop"] = {"plain": plain, "counting": counted}

    if "reconnect" in phases or "reset" in phases:
        io2 = TeeIO(CountingPort(open_port(args.url)))
        io2.known_boot_id = known_boot
        info2, rtt2, att2 = connect_retry(io2)
        rec = {"hello": hello_dict(info2, rtt2, att2), "events": events_list(io2)}
        tels = pump_for(io2, 0.5, ping_every=0.1)
        rec["timing"] = timing(tels)
        report["reconnect"] = rec
        say("reconnect:", json.dumps(rec))

        if "reset" in phases:
            io2.arm()
            tels_before = pump_for(io2, 0.3, ping_every=0.1)
            rx_before = len(io2.rx)
            t_reset = io2.now()
            mon = hmp("system_reset", args.monitor_port)
            tels = pump_for(io2, 4.0, ping_every=0.1)
            reboot_text = bytes(io2.rx[rx_before:])
            (LOGS / f"{args.tag}_reset_rx.bin").write_bytes(reboot_text)
            (LOGS / f"{args.tag}_reset_rx.txt").write_text(render(reboot_text), encoding="utf-8")
            ev1 = events_list(io2)
            info3, rtt3, att3 = connect_retry(io2)
            ev2 = events_list(io2)
            tels_after = pump_for(io2, 0.5, ping_every=0.1)
            report["reset"] = {
                "monitor_reply": mon.strip(), "state_before": transitions(tels_before),
                "last_telemetry_after_reset_cmd_s": round(max(x.stamp.t for x in tels) - t_reset, 4) if tels else None,
                "telemetry_after_reset_cmd": len(tels), "reboot_rx_bytes": len(reboot_text),
                "rx_bursts": [b for b in io2.rx_bursts if b[0] >= t_reset],
                "events_while_waiting": ev1, "hello_after_reset": hello_dict(info3, rtt3, att3),
                "events_on_connect": ev2, "timing_after": timing(tels_after),
                "stats": stats_dict(io2)}
            say("reset:", json.dumps({k: v for k, v in report["reset"].items() if k != "stats"}))
        io2.close()

    report["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    out = LOGS / f"{args.tag}_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    say(f"report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
