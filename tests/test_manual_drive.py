"""Tab Kết nối xe (ui.car_connection), tab Lái tay (ui.manual_drive) và cầu nối SSH tới ESP32 trên Pi."""
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
from autopark.ui import car_connection as cc  # noqa: E402
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


def test_steer_limit_and_servo_pulse_follow_board(qapp):
    conn = cc.CarConnection(auto_tick=False)
    assert conn.steer_limit() == pytest.approx(cc.DEFAULT_STEER_LIMIT_RAD)        # chưa kết nối
    assert conn.servo_us(0.1) == 1600 and conn.servo_us(-5.0) == 1200             # 1 mrad ≈ 1 µs, kẹp theo giới hạn


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


# ------------------------------------------------------------------------------------------------ tab (mô phỏng)
class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class _SyncConnector(cc.Connector):
    def start(self):
        self.run_now()
        return self


class Rig:
    """Kết nối chung + tab Kết nối xe + tab Lái tay, đồng hồ giả, test tự gọi tick()."""

    def __init__(self):
        self.clock = Clock()
        self.conn = cc.CarConnection(connector_factory=_SyncConnector, clock=self.clock, auto_tick=False)
        self.page = cc.CarConnectionPage(self.conn)
        self.page.timer.stop()
        self.drive = md.ManualDriveWindow(self.conn, clock=self.clock)
        self.drive.timer.stop()
        self.drive.keys_live = lambda: True

    def connect_sim(self):
        self.page.mode_box.setCurrentIndex(self.page.mode_box.findData("sim"))
        self.page.toggle()
        self.run(0.1)

    def run(self, seconds):
        for _ in range(int(round(seconds / 0.02))):
            self.clock.t += 0.02
            self.conn.tick()
            self.drive.tick()
        self.page.refresh()
        self.drive._refresh_ui(force=True)

    def key(self, k, press):
        ev = QKeyEvent(QEvent.Type.KeyPress if press else QEvent.Type.KeyRelease, k, Qt.KeyboardModifier.NoModifier)
        return self.drive.eventFilter(self.drive, ev)

    def close(self):
        self.drive.close()
        self.page.close()


def test_connection_tab_connects_and_drive_tab_drives(qapp):
    rig = Rig()
    try:
        assert rig.drive.banner.isVisibleTo(rig.drive)                    # chưa kết nối: tab lái chỉ đường sang
        rig.connect_sim()
        conn, page, w = rig.conn, rig.page, rig.drive
        assert conn.connected and conn.status() == ("Đã kết nối · sẵn sàng lái", "ok")
        assert [icon.text() for icon, _ in page.step_rows] == ["✓"] * 4
        assert page.connect_button.text() == "Ngắt kết nối" and not page.mode_box.isEnabled()
        assert page.board["firmware"].text() != "—" and page.limit_values["speed"].text() == "0.30 m/s"
        assert not w.banner.isVisibleTo(w)

        x0 = conn.io.truth.pose.x
        assert rig.key(Qt.Key.Key_Space, True)
        rig.run(1.5)
        assert w.forward_tile.property("on") is True
        assert conn.io.latest().speed_ref_mps > 0.05 and conn.io.truth.pose.x > x0 + 0.03
        rig.key(Qt.Key.Key_Space, False)
        rig.run(1.0)
        assert conn.io.latest().speed_ref_mps == 0.0

        x1 = conn.io.truth.pose.x
        rig.key(Qt.Key.Key_W, True)
        rig.run(1.5)
        assert conn.io.latest().speed_ref_mps < -0.05 and conn.io.truth.pose.x < x1 - 0.03
        rig.key(Qt.Key.Key_W, False)

        w.wheel.set_value(1.0)                                    # vô lăng hết trái
        rig.run(1.0)
        assert conn.io.latest().steer_ref_rad == pytest.approx(conn.steer_limit(), abs=0.01)

        rig.key(Qt.Key.Key_Escape, True)                          # dừng khẩn: DISARM, không gửi lệnh chạy nữa
        rig.run(0.3)
        assert conn.io.latest().state == State.DISARMED
        assert page.arm_button.isEnabled() and w.arm_button.isVisibleTo(w)
        rig.key(Qt.Key.Key_Space, True)
        rig.run(0.5)
        assert conn.io.latest().speed_ref_mps == 0.0
        rig.key(Qt.Key.Key_Space, False)

        page.arm_button.click()                                   # Bật lái ở tab Kết nối xe
        rig.run(0.2)
        assert conn.can_drive()

        page.toggle()                                             # Ngắt ở tab Kết nối xe
        rig.run(0.1)
        assert conn.io is None and conn.status() == ("Chưa kết nối xe", "")
        assert w.banner.isVisibleTo(w)
    finally:
        rig.close()


def test_drive_tab_closed_stops_commanding(qapp):
    rig = Rig()
    try:
        rig.connect_sim()
        rig.drive.close()
        assert rig.conn.command_source is None                     # không còn nguồn lệnh: chỉ PING, xe đứng yên
        rig.run(0.5)
        assert rig.conn.connected and rig.conn.io.latest().speed_ref_mps == 0.0
    finally:
        rig.close()
    assert rig.conn.io is None                                    # đóng tab Kết nối xe (thoát app): ngắt


def test_connect_failure_marks_step(qapp):
    class Failing(cc.Connector):
        def start(self):
            self.step = 1
            self.result = (None, "Pi không mở được ESP32: busy")
            return self

    clock = Clock()
    conn = cc.CarConnection(connector_factory=Failing, clock=clock, auto_tick=False)
    page = cc.CarConnectionPage(conn)
    try:
        page.host.setText("192.168.1.50")
        page.toggle()
        conn.tick()
        page.refresh()
        assert conn.status() == ("Không kết nối được", "bad")
        assert [icon.text() for icon, _ in page.step_rows][:2] == ["✓", "✗"]
        assert "busy" in page.error.text()
    finally:
        page.close()


def test_pi_mode_needs_host(qapp):
    conn = cc.CarConnection(auto_tick=False)
    assert conn.connect_to("pi", "") is False and not conn.connecting


def test_focus_loss_releases_keys(qapp):
    rig = Rig()
    try:
        rig.drive.set_key(Qt.Key.Key_Space, True)
        rig.drive.set_key(Qt.Key.Key_Left, True)
        rig.drive.eventFilter(rig.drive, QEvent(QEvent.Type.ApplicationDeactivate))
        assert not rig.drive.drive.forward and not any(rig.drive.steer_keys.values())
    finally:
        rig.close()


def test_keys_ignored_when_page_not_active(qapp):
    conn = cc.CarConnection(auto_tick=False)
    w = md.ManualDriveWindow(conn)
    try:
        w.timer.stop()
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        assert w.eventFilter(w, ev) is False and not w.drive.forward      # tab chưa hiện: không bắt phím
    finally:
        w.close()


def test_shell_has_connection_and_drive_tabs():
    from autopark.ui import shell
    keys = [p.key for p in shell.PAGES]
    assert keys.index("ket_noi_xe") + 1 == keys.index("lai_tay")
    assert shell.parse_args(["--page", "ket_noi_xe"]).page == "ket_noi_xe"


def test_protocol_ids_match_bridge_usb():
    assert "0x303A, 0x1001" in BRIDGE_SOURCE and P.PROTOCOL_VERSION == 1
