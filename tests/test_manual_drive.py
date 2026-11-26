"""Trang Lái tay (ui.manual_drive) và cầu nối SSH tới ESP32 trên Pi (transport.ssh_serial)."""
from __future__ import annotations

import base64
import os
import shlex
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.transport import protocol as P  # noqa: E402
from autopark.transport.protocol import State  # noqa: E402
from autopark.transport.ssh_serial import BRIDGE_SOURCE, SshSerialPort, bridge_command  # noqa: E402
from autopark.transport.vehicle_io import SerialVehicleIO  # noqa: E402
from autopark.ui import manual_drive as md  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------------------------------------------ phần tính thuần
def test_drive_command_keys_and_limits():
    inp = md.DriveInput(speed_mps=0.1, steer_frac=0.5)
    assert md.drive_command(inp, 0.3, 0.3) == (0.0, 0.15)                 # không phím: đứng yên, vẫn giữ góc lái
    inp.forward = True
    assert md.drive_command(inp, 0.3, 0.3)[0] == pytest.approx(0.1)        # Space: tiến
    inp.reverse = True
    assert md.drive_command(inp, 0.3, 0.3)[0] == 0.0                       # cả hai phím: dừng
    inp.forward = False
    assert md.drive_command(inp, 0.3, 0.3)[0] == pytest.approx(-0.1)       # W: lùi
    inp.speed_mps, inp.steer_frac = 5.0, -3.0
    assert md.drive_command(inp, 0.3, 0.25) == (pytest.approx(-0.25), pytest.approx(-0.3))   # kẹp theo bo


def test_real_car_steer_limited_by_bench_servo():
    assert md.steer_limit(None, "pi") == pytest.approx(md.SERVO_LIMIT_RAD)


def test_wheel_left_is_positive(qapp):
    wheel = md.SteeringWheel()
    seen = []
    wheel.changed.connect(seen.append)
    wheel.rotate_by(-md.WHEEL_MAX_DEG / 2)              # ngược chiều kim đồng hồ = rẽ trái
    assert wheel.value == pytest.approx(0.5) and seen[-1] == pytest.approx(0.5)
    wheel.rotate_by(10 * md.WHEEL_MAX_DEG)              # kẹp ở hết lái phải
    assert wheel.value == pytest.approx(-1.0)
    wheel.set_value(0.0)
    assert wheel.value == 0.0


# ------------------------------------------------------------------------------------------------ cầu nối SSH
def test_bridge_command_carries_bridge_source():
    cmd = bridge_command("192.168.1.50")
    assert cmd[0] == "ssh" and "-T" in cmd and cmd[-2] == "xe@192.168.1.50"
    remote = shlex.split(cmd[-1])                                         # remote shell của Pi tách như sh
    assert remote[:3] == ["python3", "-u", "-c"]
    code = remote[3].split('b64decode("', 1)[1].split('"', 1)[0]
    assert base64.b64decode(code).decode("utf-8") == BRIDGE_SOURCE
    compile(BRIDGE_SOURCE, "bridge", "exec")
    with pytest.raises(ValueError):
        bridge_command("pi; rm -rf /")


ECHO = ("import os,sys\n"
        "os.write(1, b'APB1 /dev/ttyACM0\\n')\n"
        "while True:\n"
        "    d = os.read(0, 4096)\n"
        "    if not d: break\n"
        "    os.write(1, d)\n")


def test_ssh_port_banner_echo_and_end():
    port = SshSerialPort([sys.executable, "-u", "-c", ECHO], timeout=0.2)
    assert port.wait_ready(10.0) == "/dev/ttyACM0"
    port.write(b"abc\x00")
    got = b""
    deadline = time.monotonic() + 5
    while len(got) < 4 and time.monotonic() < deadline:
        got += port.read(port.in_waiting or 1)
    assert got == b"abc\x00"
    port.close()
    with pytest.raises(OSError):
        port.in_waiting


def test_ssh_port_reports_pi_error_line():
    script = "import os; os.write(1, 'APB0 Pi không mở được ESP32: busy\\n'.encode())"
    port = SshSerialPort([sys.executable, "-u", "-c", script])
    with pytest.raises(OSError, match="busy"):
        port.wait_ready(10.0)
    port.close()


def test_ssh_port_close_cancels_wait():
    port = SshSerialPort([sys.executable, "-c", "import time; time.sleep(30)"])
    port.close()
    t0 = time.monotonic()
    with pytest.raises(OSError):
        port.wait_ready(20.0)
    assert time.monotonic() - t0 < 2.0


BOARD = r'''
import os, sys
sys.path.insert(0, sys.argv[1])
from autopark.transport.firmware_model import FirmwareModel
from autopark.transport.protocol import ResetReason
import threading, time
fw = FirmwareModel(now_ms=0, boot_id=0x1234, reset_reason=ResetReason.POWER_ON)
t0 = time.monotonic()
lock = threading.Lock()
os.write(1, b"APB1 /dev/ttyACM0\n")
def pump():
    while True:
        with lock:
            fw.step(int((time.monotonic() - t0) * 1000))
            out = fw.take_tx()
        if out:
            os.write(1, out)
        time.sleep(0.005)
threading.Thread(target=pump, daemon=True).start()
while True:
    d = os.read(0, 4096)
    if not d:
        break
    with lock:
        fw.receive(d, int((time.monotonic() - t0) * 1000))
'''


def test_vehicle_io_over_ssh_pipe_arms_and_drives():
    """SerialVehicleIO đi qua SshSerialPort tới firmware tham chiếu trong một tiến trình khác (giống Pi + ESP32)."""
    from pathlib import Path
    root = str(Path(__file__).resolve().parents[1])
    port = SshSerialPort([sys.executable, "-u", "-c", BOARD, root])
    port.wait_ready(20.0)
    io = SerialVehicleIO(port, telemetry_timeout_s=0.5)
    try:
        io.connect(timeout_s=3.0)
        io.wait_ready(timeout_s=3.0)
        io.arm()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            io.send(0.1, 0.2, validity_s=0.25)
            io.poll(block=False)
            t = io.latest()
            if t is not None and t.state == State.RUNNING and t.steer_ref_rad > 0.1:
                break
            time.sleep(0.02)
        assert io.latest().state == State.RUNNING
    finally:
        io.close()


# ------------------------------------------------------------------------------------------------ trang (mô phỏng)
class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def sim_window(qapp, clock):
    def factory(mode, target):
        return _SyncConnector(mode, target)

    w = md.ManualDriveWindow(connector_factory=factory, clock=clock)
    w.timer.stop()                                  # test tự gọi tick()
    w.mode_box.setCurrentIndex(w.mode_box.findData("sim"))
    w.keys_live = lambda: True
    return w


class _SyncConnector(md.Connector):
    def start(self):
        self.run_now()
        return self


def run(w, clock, seconds):
    for _ in range(int(seconds / 0.02)):
        clock.t += 0.02
        w.tick()


def test_page_drives_sim_car_with_space_w_and_wheel(qapp):
    clock = Clock()
    w = sim_window(qapp, clock)
    try:
        w.connect_link()
        run(w, clock, 0.1)
        assert w.io is not None and w.status.text() == "Sẵn sàng lái"
        assert w.io.latest().state in (State.ARMED, State.RUNNING)

        def key(k, press):
            ev = QKeyEvent(QEvent.Type.KeyPress if press else QEvent.Type.KeyRelease, k, Qt.KeyboardModifier.NoModifier)
            return w.eventFilter(w, ev)

        x0 = w.io.truth.pose.x
        assert key(Qt.Key.Key_Space, True)
        run(w, clock, 1.5)
        assert w.forward_tile.property("on") is True
        assert w.io.latest().speed_ref_mps > 0.05 and w.io.truth.pose.x > x0 + 0.03
        key(Qt.Key.Key_Space, False)
        run(w, clock, 1.0)
        assert w.io.latest().speed_ref_mps == 0.0

        x1 = w.io.truth.pose.x
        key(Qt.Key.Key_W, True)
        run(w, clock, 1.5)
        assert w.io.latest().speed_ref_mps < -0.05 and w.io.truth.pose.x < x1 - 0.03
        key(Qt.Key.Key_W, False)

        w.wheel.set_value(1.0)                                    # vô lăng hết trái
        run(w, clock, 1.0)
        assert w.io.latest().steer_ref_rad == pytest.approx(md.steer_limit(w.io, "sim"), abs=0.01)

        key(Qt.Key.Key_Escape, True)                              # dừng khẩn: DISARM, không gửi lệnh chạy nữa
        run(w, clock, 0.3)
        assert w.io.latest().state == State.DISARMED and w.arm_button.isEnabled()
        key(Qt.Key.Key_Space, True)
        run(w, clock, 0.5)
        assert w.io.latest().speed_ref_mps == 0.0
        key(Qt.Key.Key_Space, False)

        w.rearm()
        run(w, clock, 0.2)
        assert w.status.text() == "Sẵn sàng lái"
    finally:
        w.close()
    assert w.io is None


def test_focus_loss_releases_keys(qapp):
    clock = Clock()
    w = sim_window(qapp, clock)
    try:
        w.set_key(Qt.Key.Key_Space, True)
        w.set_key(Qt.Key.Key_Left, True)
        w.eventFilter(w, QEvent(QEvent.Type.ApplicationDeactivate))
        assert not w.drive.forward and not any(w.steer_keys.values())
    finally:
        w.close()


def test_keys_ignored_when_page_not_active(qapp):
    w = md.ManualDriveWindow()
    try:
        w.timer.stop()
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        assert w.eventFilter(w, ev) is False and not w.drive.forward      # trang chưa hiện: không bắt phím
    finally:
        w.close()


def test_shell_has_manual_drive_page():
    from autopark.ui import shell
    assert "lai_tay" in [p.key for p in shell.PAGES]
    assert shell.parse_args(["--page", "lai_tay"]).page == "lai_tay"


def test_protocol_ids_match_bridge_usb():
    assert "0x303A, 0x1001" in BRIDGE_SOURCE and P.PROTOCOL_VERSION == 1
