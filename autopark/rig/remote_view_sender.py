"""Pi-side APW1 sensor viewer, run over SSH with a driver zip prepended in LIDAR_PACKAGE."""

import base64
import json
import math
import os
import re
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


DEFAULT_DURATION = 180.0
CAMERA = Path("/dev/video0")
LIDAR_USB = (0x10C4, 0xEA60)
ESP32_USB = (0x303A, 0x1001)
PAYLOAD_LIMIT = 1024 * 1024


def json_bytes(value):
    return json.dumps(value, allow_nan=False, separators=(",", ":")).encode("ascii")


class ViewerDisconnected(Exception):
    """The SSH consumer closed or stopped reading the sensor stream."""


class Output:
    def __init__(self, fd):
        self.fd = fd
        self.interrupted = False
        os.set_blocking(fd, False)
        self.poller = select.poll()
        self.poller.register(fd, select.POLLOUT)

    def check(self, wait_ms=0):
        if self.interrupted:
            raise ViewerDisconnected("viewer cancelled")
        events = self.poller.poll(wait_ms)
        if any(mask & (select.POLLERR | select.POLLHUP | select.POLLNVAL) for _, mask in events):
            raise ViewerDisconnected("viewer pipe closed")
        return any(mask & select.POLLOUT for _, mask in events)

    def write(self, *parts):
        # Bound a write even when the peer has not closed but is no longer draining SSH.
        deadline = time.monotonic() + 3.0
        for part in parts:
            remaining = memoryview(part)
            while remaining:
                if time.monotonic() >= deadline:
                    raise ViewerDisconnected("viewer is not reading the sensor stream")
                if not self.check(100):
                    continue
                try:
                    written = os.write(self.fd, remaining)
                except BlockingIOError:
                    continue
                except OSError as exc:
                    raise ViewerDisconnected("cannot write to the viewer pipe") from exc
                remaining = remaining[written:]

    def emit(self, kind, payload, **metadata):
        header = {"kind": kind, "nbytes": len(payload), **metadata}
        self.write(json_bytes(header) + b"\n", payload)


class Latest:
    def __init__(self, units):
        self.units = units
        self.condition = threading.Condition()
        self.stop = threading.Event()
        self.slots = {}
        self.last = {}
        self.published = dict.fromkeys(units, 0)
        self.replaced = dict.fromkeys(units, 0)
        self.active = False
        self.errors = []
        self.ffmpeg = {}

    def offer(self, kind, receipt_ns, payload):
        with self.condition:
            if self.stop.is_set():
                return
            self.last[kind] = time.monotonic_ns()
            if self.active:
                self.published[kind] += 1
                if kind in self.slots:
                    self.replaced[kind] += 1
                self.slots[kind] = (self.published[kind], receipt_ns, payload)
            self.condition.notify()

    def take(self):
        with self.condition:
            if not self.slots and not self.stop.is_set():
                self.condition.wait(0.2)
            if self.slots:
                kind = next(iter(self.slots))
                return kind, self.slots.pop(kind)
            return None

    def fail(self, text):
        with self.condition:
            self.errors.append(text)
            self.stop.set()
            self.condition.notify_all()

    def halt(self):
        with self.condition:
            self.stop.set()
            children = tuple(self.ffmpeg.items())
        for kind, child in children:
            try:
                if child.poll() is None:
                    child.terminate()
            except OSError as exc:
                self.fail(f"could not stop FFmpeg for {kind}: {exc}")
        deadline = time.monotonic() + 2
        for kind, child in children:
            try:
                try:
                    child.wait(timeout=max(0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    child.kill()
            except OSError as exc:
                self.fail(f"could not clean up FFmpeg for {kind}: {exc}")


def complete_read(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise EOFError("FFmpeg ended inside a JPEG payload")
        data.extend(chunk)
    return bytes(data)


def mjpeg_packets(pipe):
    while True:
        line = pipe.readline(1024)
        if not line:
            return
        if line in (b"\r\n", b"\n"):
            continue
        if line.rstrip(b"\r\n") != b"--ffmpeg":
            raise ValueError("unexpected MPJPEG boundary")
        headers = {}
        for _ in range(12):
            line = pipe.readline(1024)
            if not line:
                if not headers:
                    return
                raise EOFError("FFmpeg ended inside MPJPEG headers")
            if line in (b"\r\n", b"\n"):
                break
            name, delimiter, value = line.partition(b":")
            if not delimiter or not line.endswith(b"\n"):
                raise ValueError("malformed MPJPEG header")
            headers[name.strip().lower()] = value.strip()
        else:
            raise ValueError("MPJPEG headers did not end")
        length = headers.get(b"content-length", b"")
        size = int(length) if length.isdigit() else 0
        if headers.get(b"content-type", b"").lower() != b"image/jpeg" or not 0 < size <= PAYLOAD_LIMIT:
            raise ValueError("invalid MPJPEG content type or length")
        yield complete_read(pipe, size)


def camera_worker(state, kind, video, fps):
    child = subprocess.Popen(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
         "-f", "v4l2", "-input_format", "mjpeg", "-video_size", "640x480", "-i", str(video),
         "-map", "0:v:0", "-an", "-c:v", "copy", "-f", "mpjpeg",
         "-flush_packets", "1", "pipe:1"],
        stdout=subprocess.PIPE,
    )
    with state.condition:
        state.ffmpeg[kind] = child
    next_slot_ns = 0
    period_ns = 1_000_000_000 // fps
    try:
        if state.stop.is_set():
            return
        for jpeg in mjpeg_packets(child.stdout):
            if state.stop.is_set():
                return
            now = time.monotonic_ns()
            if not next_slot_ns:
                next_slot_ns = now
            if now >= next_slot_ns:
                next_slot_ns += ((now - next_slot_ns) // period_ns + 1) * period_ns
                state.offer(kind, now, jpeg)
        if not state.stop.is_set():
            raise RuntimeError("FFmpeg stopped delivering JPEG images")
    finally:
        if child.poll() is None:
            child.terminate()
        try:
            child.wait(timeout=4)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=4)
        finally:
            child.stdout.close()


def v4l2_info(node, option):
    return subprocess.check_output(["v4l2-ctl", "-d", str(node), option],
                                   text=True, errors="replace", timeout=2)


def advertises_mjpeg(formats):
    mjpeg = False
    for line in formats.splitlines():
        format_line = re.match(r"\s*\[\d+\]:\s*'(.{4})'", line)
        if format_line:
            mjpeg = format_line[1] == "MJPG"
        elif mjpeg and re.search(r"Size:\s*Discrete\s+640x480\b", line):
            return True
    return False


def camera_devices(count, check_open):
    sys_class = Path("/sys/class/video4linux")
    if count == 1:
        usb_path = (sys_class / CAMERA.name / "device").resolve()
        if not CAMERA.is_char_device() or not re.search(r"/usb[0-9]+/", str(usb_path)):
            raise RuntimeError(f"validated USB camera {CAMERA} is unavailable")
        return {"camera": str(CAMERA)}

    by_usb = {}
    for entry in sorted(sys_class.glob("video[0-9]*"), key=lambda path: int(path.name[5:])):
        check_open()
        usb = next((path for path in entry.resolve().parents
                    if (path / "idVendor").is_file() and (path / "idProduct").is_file()), None)
        node = Path("/dev") / entry.name
        if usb is None or usb in by_usb or not node.is_char_device():
            continue
        try:
            caps = re.split(r"^\s*Device Caps\s*:", v4l2_info(node, "--info"), flags=re.M)[-1]
            if re.search(r"^\s*Video Capture(?: Multiplanar)?\s*$", caps, re.M):
                if advertises_mjpeg(v4l2_info(node, "--list-formats-ext")):
                    by_usb[usb] = str(node)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    if len(by_usb) != count:
        raise RuntimeError(f"expected {count} distinct USB cameras supporting MJPG 640x480, found {len(by_usb)}")
    # Numeric bus and port components keep order stable when video nodes are renumbered.
    ordered = sorted(by_usb, key=lambda usb: tuple(map(int, re.findall(r"\d+", usb.name))))
    return {f"camera_{index}": by_usb[usb] for index, usb in enumerate(ordered, 1)}


def lidar_worker(state, port):
    from autopark.lidar.rplidar_c1 import RplidarC1Source

    source = RplidarC1Source.open(port)
    try:
        source.transport.write_timeout = 1.0
        source.stop_output()
        health = source.device_health()
        if health.status != 0:
            raise RuntimeError(f"C1 health status={health.status}, code={health.error_code}")
        if state.stop.is_set():
            return
        source.start()
        while not state.stop.is_set():
            scan = source.read()
            receipt_at = int((source.t0 + scan.stamp.t) * 1_000_000_000)
            payload = json_bytes({
                "angles_rad": scan.angles_rad,
                "ranges_m": [distance if math.isfinite(distance) else None for distance in scan.ranges_m],
            })
            state.offer("lidar", receipt_at, payload)
    finally:
        try:
            source.stop_output()
            print("Pi: C1 STOP sent", file=sys.stderr, flush=True)
        except Exception as exc:
            state.fail(f"C1 STOP failed: {exc}")
        finally:
            source.transport.close()


def guarded(state, label, worker, *args):
    try:
        worker(state, *args)
    except Exception as exc:
        if not state.stop.is_set():
            state.fail(f"{label}: {exc}")


# vcgencmd get_throttled: bit 0–3 = đang sụt áp / đang hạ xung / đang throttle / đang chạm ngưỡng nhiệt; bit 16–19 = các
# trạng thái đó ĐÃ TỪNG xảy ra từ lúc khởi động (chỉ xóa khi reboot). Chỉ chặn theo bit đang xảy ra: trước 29/11/2026 một
# lần sụt áp thoáng qua khóa tab Quan sát Pi tới khi reboot. Giá trị thô vẫn ghi trong gói end (power_start/power_end).
ACTIVE_POWER_MASK = 0xF


def power_flags():
    output = subprocess.check_output(["vcgencmd", "get_throttled"], text=True, timeout=4)
    return int(output.strip().split("=", 1)[-1], 16)


def device_port(vid, pid):
    from serial.tools import list_ports

    matches = [port.device for port in list_ports.comports() if (port.vid, port.pid) == (vid, pid)]
    if len(matches) != 1:
        raise RuntimeError(f"expected one USB {vid:04x}:{pid:04x} device, found {matches}")
    return matches[0]


def esp32_probe(port):
    probe = Path.home() / "autopark_usb_probe.pyz"
    result = subprocess.run([sys.executable, str(probe), port], capture_output=True, text=True, timeout=7)
    boot = re.search(r"boot_id=([a-f0-9]+)", result.stdout)
    if result.returncode or "state=DISARMED" not in result.stdout or not boot:
        raise RuntimeError(f"ESP32 probe failed: {result.stderr.strip() or result.stdout.strip()}")
    return boot[1]


def wait_ready(state, output):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        output.check()
        with state.condition:
            if state.stop.is_set():
                break
            if all(name in state.last for name in state.units):
                state.active = True
                return
            state.condition.wait(0.2)
    raise RuntimeError("camera streams and C1 did not all start successfully")


def send_sensor(output, item, counts):
    kind, (seq, t_ns, payload) = item
    output.emit(kind, payload, seq=seq, t_ns=t_ns, tx_ns=time.monotonic_ns())
    counts[kind] += 1


def main(duration=DEFAULT_DURATION, camera_count=1, check_esp32=True):
    # check_esp32=False (app AutoPark, 27/11/2026): không mở cổng ESP32. Tab Kết nối xe giữ cổng đó (khóa TIOCEXCL)
    # trong lúc lái, và xem camera/LiDAR không cần bo; bước kiểm boot_id chỉ dành cho bài thử nguồn dòng lệnh.
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("view duration must be a positive finite number")
    if type(camera_count) is not int or camera_count not in (1, 4):
        raise ValueError("view requires one or four cameras")
    kinds = ("camera",) if camera_count == 1 else tuple(f"camera_{i}" for i in range(1, 5))
    state = Latest((*kinds, "lidar"))
    target_fps = 10 if camera_count == 1 else 5
    output = Output(sys.stdout.fileno())

    def interrupt(*_):
        # Let the main loop unwind and wait for the camera and LiDAR to close.
        output.interrupted = True

    for signum in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupt)

    sent = dict.fromkeys(state.units, 0)
    power_start = power_end = None
    esp_start = esp_end = None
    started = None
    elapsed = 0.0
    threads = []
    disconnected = False
    try:
        output.write(b"APW1\n")
        start = {
            "duration_s": duration,
            "camera_mode": "MJPG 640x480",
            "target_camera_fps": target_fps,
            "timestamp": "Pi application receipt, monotonic ns",
        }
        if camera_count == 4:
            start.update(camera_count=camera_count, camera_devices={})
        try:
            cameras = camera_devices(camera_count, output.check)
            if camera_count == 4:
                start["camera_devices"] = cameras
        finally:
            output.emit("start", json_bytes(start))
        port = device_port(*LIDAR_USB)
        esp_port = device_port(*ESP32_USB) if check_esp32 else None
        power_start = power_flags()
        if power_start & ACTIVE_POWER_MASK:
            raise RuntimeError(f"Pi power check at start: {power_start:#x}")
        if check_esp32:
            esp_start = esp32_probe(esp_port)
        output.check()
        workers = [(kind, camera_worker, (kind, cameras[kind], target_fps)) for kind in kinds]
        workers.append(("lidar", lidar_worker, (port,)))
        for label, worker, args in workers:
            thread = threading.Thread(target=guarded, args=(state, label, worker, *args), daemon=True)
            thread.start()
            threads.append(thread)
        wait_ready(state, output)
        started = last_power_check = time.monotonic()
        while not state.stop.is_set() and time.monotonic() - started < duration:
            output.check()
            item = state.take()
            if item is not None:
                send_sensor(output, item, sent)
            now = time.monotonic()
            if now - last_power_check >= 2:
                flags = power_flags()
                if flags & ACTIVE_POWER_MASK:
                    raise RuntimeError(f"Pi reported throttled={flags:#x} during streaming")
                last_power_check = now
            with state.condition:
                stale = [name for name in state.units if time.monotonic_ns() - state.last[name] > 3_000_000_000]
            if stale:
                raise RuntimeError(f"sensor intake stopped: {stale}")
    except ViewerDisconnected:
        disconnected = True
    except (ImportError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        state.fail(str(exc))
    finally:
        if started is not None:
            elapsed = time.monotonic() - started
        state.halt()
        cleanup_deadline = time.monotonic() + 12
        for thread in threads:
            thread.join(timeout=max(0, cleanup_deadline - time.monotonic()))
        if any(thread.is_alive() for thread in threads):
            state.fail("sensor worker cleanup timeout")

    if disconnected:
        return 1
    try:
        output.check()
        while state.slots:
            send_sensor(output, state.take(), sent)
        try:
            power_end = power_flags()
            if esp_start is not None:
                esp_end = esp32_probe(device_port(*ESP32_USB))
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            state.fail(str(exc))
        esp_ok = not check_esp32 or (bool(esp_start) and esp_start == esp_end)
        ok = (not state.errors and elapsed >= duration - 0.1 and power_end is not None
              and not power_end & ACTIVE_POWER_MASK
              and esp_ok and all(sent.values()))
        output.emit("end", json_bytes({
            "ok": ok, "sent": sent, "published": state.published, "replaced": state.replaced,
            "duration_s": elapsed, "power_start": power_start, "power_end": power_end,
            "esp32_start": esp_start, "esp32_end": esp_end, "errors": state.errors,
        }))
    except ViewerDisconnected:
        return 1
    return int(not ok)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="autopark-wifi-view-") as directory:
        driver = Path(directory) / "lidar.zip"
        driver.write_bytes(base64.b64decode(LIDAR_PACKAGE, validate=True))
        sys.path.insert(0, str(driver))
        raise SystemExit(main(float(globals().get("VIEW_DURATION", DEFAULT_DURATION)),
                              globals().get("VIEW_CAMERA_COUNT", 1), globals().get("VIEW_CHECK_ESP32", True)))
