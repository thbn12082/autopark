"""LiDAR dock inside the phase-0 cockpit, driven by hand offscreen: the board's obstacles follow the live scan,
planning freezes them, and an object appearing on the path stops the virtual car. Since 2026-10-02 (T3): the driver and
the replay run on the rig clock (perf_counter), only the current reader feeds a sensor recording, and a session recording
folder replays in the dock."""
import math
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from autopark.application.session import SessionState  # noqa: E402
from autopark.application.vehicle_link import EVENT_FIELDS, SESSION_STOP, DriveMode  # noqa: E402
from autopark.domain.types import Bounds  # noqa: E402
from autopark.storage import run_store  # noqa: E402
from autopark.ui.items import ObstacleItem  # noqa: E402
from autopark.ui.lidar_app import build_window  # noqa: E402
from autopark.ui.scan_view import ScanView  # noqa: E402
from tests.test_fusion import scan_with_object  # noqa: E402
from tests.test_session_vehicle import read_csv  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeSource:
    source_id = "c1_fake"

    def __init__(self):
        self.t = 0.0
        self.mirror = False
        self.closed = False

    def now(self) -> float:
        return self.t

    def read(self):                       # never called: scans are pushed into the dock's queue by the test
        raise AssertionError("thread must not be started in this test")

    def flush(self) -> None:
        pass

    def stats(self) -> dict:
        return {"fake": True}

    def close(self) -> None:
        self.closed = True


def push(dock, source, scan):
    source.t = scan.stamp.t
    dock.queue.put((scan, None, None))
    dock.tick()


def feed(dock, source, t, distance, angle_deg=0.0, times=3, half_width_deg=8.0):
    """Several revolutions of the same picture, so the persistence rule accepts it. Returns the new time."""
    for _ in range(times):
        t += 0.1
        push(dock, source, scan_with_object(t, distance, angle_deg=angle_deg, half_width_deg=half_width_deg))
    return t


def test_board_obstacles_follow_the_live_scan(qapp):
    window, dock = build_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()
    source = FakeSource()
    dock.attach_source(source, start_thread=False)
    assert dock.btn_connect.text() == "Ngắt"

    t = feed(dock, source, 0.0, 1.2, angle_deg=45.0)               # an object to the left front of the LiDAR
    owned = dock.bridge.owned()
    assert owned and all(isinstance(window._obstacle_items[o.id], ObstacleItem) for o in owned)
    x, y = window.session.scenario.start.to_world(1.2 * math.cos(math.radians(45)), 1.2 * math.sin(math.radians(45)))
    assert any(abs(o.cx - x) < 0.15 and abs(o.cy - y) < 0.15 for o in owned)
    assert "vật thể" in dock.lbl_map.text() and "hộp" in dock.lbl_map.text()
    assert dock.points_item is not None and len(dock.points_item.points) > 0
    assert "trong sa bàn dùng được" in dock.lbl_points.text()

    t = feed(dock, source, t, 1.2, angle_deg=-45.0)                # the object is moved to the right front
    moved = dock.bridge.owned()
    assert moved and not (set(o.id for o in moved) & set(o.id for o in owned))   # old boxes gone, new ones added
    x2, y2 = window.session.scenario.start.to_world(1.2 * math.cos(math.radians(-45)), 1.2 * math.sin(math.radians(-45)))
    assert any(abs(o.cx - x2) < 0.15 and abs(o.cy - y2) < 0.15 for o in moved)
    assert all(o.id not in window._obstacle_items for o in owned)   # and their scene items were removed
    assert dock.map_updates >= 2

    t = feed(dock, source, t, None)                                 # nothing in sight any more: board empties
    assert dock.bridge.owned() == [] and window.session.scenario.obstacles == []

    dock.chk_live.setChecked(False)                                 # frozen on request
    t = feed(dock, source, t, 1.0)
    assert dock.bridge.owned() == []
    dock.chk_live.setChecked(True)
    dock.shutdown()
    window.close()


def test_planning_freezes_the_map_and_a_new_object_stops_the_car(qapp):
    window, dock = build_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()
    source = FakeSource()
    dock.attach_source(source, start_thread=False)
    t = feed(dock, source, 0.0, 1.2, angle_deg=60.0)               # off the straight path to the goal
    frozen = [o.id for o in dock.bridge.owned()]
    assert frozen

    assert window.plan(sync=True).ok
    assert window.session.state == SessionState.READY
    t = feed(dock, source, t, None)                                 # scene empties, but READY keeps the map
    assert [o.id for o in dock.bridge.owned()] == frozen
    assert not dock.spin_mask.isEnabled() or window.session.state == SessionState.READY

    window.run()
    assert window.session.state == SessionState.RUNNING
    window.advance_by(1.0)
    assert abs(window.session.world.state.speed) > 0.05
    dock.tick()
    for widget in (dock.spin_window, dock.spin_min_hits, dock.spin_mask, dock.chk_mirror):
        assert not widget.isEnabled()                               # settings locked while driving
    t = feed(dock, source, t, 1.2, angle_deg=60.0, times=2)        # the known object again: no stop
    assert window.session.state == SessionState.RUNNING and dock.new_on_path == 0
    t = feed(dock, source, t, 0.9, times=2)                        # a hand in front of the LiDAR: on the path
    assert window.session.state == SessionState.STOPPING and dock.new_on_path >= 1
    assert any(e.code == "MAP_CHANGED" for e in window.session.safety_events)
    assert "Vật mới trên đường" in dock.lbl_track.text()
    for _ in range(50):
        window.advance_by(0.1)
        if not window.session.simulating:
            break
    assert window.session.state == SessionState.STOPPED and not window.session.world.collided
    source.t = t + 1.0                                              # no scans for a second: shown as stale
    dock.tick()
    assert dock.stale and "CŨ" in dock.lbl_rate.text()
    dock.shutdown()
    assert source.closed
    window.close()


def test_losing_the_lidar_while_driving_stops_the_car(qapp):
    window, dock = build_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()
    source = FakeSource()
    dock.attach_source(source, start_thread=False)
    t = feed(dock, source, 0.0, 1.2, angle_deg=60.0)
    assert window.plan(sync=True).ok
    window.run()
    window.advance_by(1.0)
    dock.disconnect_source()                                        # unplugging mid-run must brake
    assert window.session.state == SessionState.STOPPING and dock.stale_stops == 1
    assert "mất LiDAR" in window.session.stop_reason
    window.close()


def start_vehicle_io_run(window, dock, source) -> None:
    """Plan and start a run through VehicleIO on the window's simulated board (no port is opened) until the car
    moves."""
    feed(dock, source, 0.0, 1.2, angle_deg=60.0)
    combo = window.combo_drive
    combo.setCurrentIndex(combo.findData(DriveMode.VEHICLE_IO.value))
    assert window.session.drive_mode == DriveMode.VEHICLE_IO and window.board_port() is None
    assert window.plan(sync=True).ok
    window.run()
    assert window.session.state == SessionState.RUNNING
    for _ in range(30):
        window.advance_by(0.1)
        if abs(window.session.world.state.speed) > 0.05:
            break


def test_lidar_disconnect_in_vehicle_io_is_logged(qapp, tmp_path, monkeypatch):
    """T13 (2026-10-02): through VehicleIO (the simulated board, no port opened) unplugging the LiDAR mid-run becomes
    the first session_stop row of events.csv, with the dock's code and source, and the exported log keeps it."""
    window, dock = build_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()
    source = FakeSource()
    dock.attach_source(source, start_thread=False)
    try:
        start_vehicle_io_run(window, dock, source)
        dock.disconnect_source()
        assert window.session.state == SessionState.STOPPING and source.closed
        for _ in range(50):
            window.advance_by(0.1)
            if not window.session.simulating:
                break
        assert window.session.state == SessionState.STOPPED
        out = tmp_path / "lan.csv"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), "CSV (*.csv)"))
        # T9: _export_log xuất cả gói phát lại của lần chạy qua VehicleIO; không gọi PowerShell trong test.
        monkeypatch.setattr(run_store, "environment", lambda: {"test": True})
        window._export_log()
        rows = read_csv(tmp_path / "lan_vehicle_io" / "events.csv")
        assert list(rows[0]) == EVENT_FIELDS
        first = next(r for r in rows if r["handling"] == SESSION_STOP)
        assert (first["code"], first["source"], first["action"]) == ("LIDAR_DISCONNECTED", "lidar_dock", "STOP")
        assert "mất LiDAR" in first["message"] and first["t_perf"] != ""
    finally:
        dock.shutdown()
        window.close()


@pytest.mark.parametrize("change, code", [("mirror", "LIDAR_MIRROR_CHANGED"), ("mask", "LIDAR_CONFIG_CHANGED")])
def test_lidar_setting_change_in_vehicle_io_is_logged_with_its_code(qapp, change, code):
    """T13 (2026-10-02): the backstop stops (the widgets are locked while driving) carry their own code."""
    window, dock = build_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()
    source = FakeSource()
    dock.attach_source(source, start_thread=False)
    try:
        start_vehicle_io_run(window, dock, source)
        if change == "mirror":
            dock._set_mirror(True)
        else:
            dock.spin_mask.setValue(3)
            dock.tick()
        session = window.session
        assert session.state == SessionState.STOPPING and dock.stale_stops == 1
        first = next(r for r in session.run_link.event_rows if r["handling"] == SESSION_STOP)
        assert (first["code"], first["source"], first["message"]) == (code, "lidar_dock", session.stop_reason)
    finally:
        dock.shutdown()
        window.close()


def test_settings_mirror_and_snapped_bounds(qapp):
    window, dock = build_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()
    source = FakeSource()
    dock.attach_source(source, start_thread=False)
    assert dock.layer.mask_margin == pytest.approx(0.10) and dock.layer.window == 3 and dock.layer.min_hits == 2
    dock.spin_mask.setValue(3)
    dock.tick()
    assert dock.layer.mask_margin == pytest.approx(0.03)            # the live layer follows the setting
    dock.spin_window.setValue(4)
    dock.spin_min_hits.setValue(9)
    dock.tick()
    assert dock.layer.window == 4 and dock.layer.min_hits == 4      # min hits cannot exceed the window

    t = feed(dock, source, 0.0, 1.0, times=4)
    assert dock.bridge.owned()
    dock.chk_mirror.setChecked(True)                                # flips the sign: old boxes are void
    assert source.mirror is True and dock.layer is None and dock.bridge.owned() == []
    dock.tick()
    assert dock.layer is not None

    window.session.scenario.bounds = Bounds(0.0, 0.0, 3.02, 2.0)    # not a multiple of 5 cm: snapped, no error
    grid = dock._bounds_grid()
    assert grid.x_max == pytest.approx(3.0) and grid.y_max == pytest.approx(2.0)
    dock.tick()
    assert dock.grid == grid

    view = ScanView(max_range=5.0, front_up=False)
    view.resize(320, 320)
    ahead = view._to_widget(1.0, 0.0)
    assert ahead.x() > 160 and abs(ahead.y() - 160) < 1e-6          # front = right, like the board
    classic = ScanView(max_range=5.0)
    classic.resize(320, 320)
    up = classic._to_widget(1.0, 0.0)
    assert up.y() < 160 and abs(up.x() - 160) < 1e-6                # default: front = up
    dock.shutdown()
    window.close()


def test_dock_without_source_is_idle(qapp, no_serial):
    window, dock = build_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()
    dock.tick()
    assert dock.btn_connect.text() == "Kết nối" and not dock.btn_clear.isEnabled()
    dock.connect_source()                                           # COM9 does not exist: reported, not raised
    assert dock.source is None and "Không kết nối được" in dock.lbl_device.text()
    window.close()


@pytest.fixture
def no_serial(monkeypatch):
    """No COM port can open: serial.Serial and serial_for_url refuse."""
    import serial

    def refuse(*args, **kwargs):
        raise AssertionError("test không được mở cổng thật")
    monkeypatch.setattr(serial, "Serial", refuse)
    monkeypatch.setattr(serial, "serial_for_url", refuse)


def test_dock_opens_the_driver_and_the_replay_on_the_rig_clock(qapp, tmp_path, monkeypatch, no_serial):
    """T3 (2026-10-02): like rig.bench, the dock opens the C1 driver and the .npz replay with RIG_CLOCK (perf_counter),
    so scan stamps + t0 share the clock of the camera frames and the VehicleIO log."""
    from autopark.lidar import rplidar_c1
    from autopark.lidar.live_view import PacedReplay
    from autopark.lidar.recording import ScanRecorder
    from autopark.video.multicam import RIG_CLOCK
    from tests.rig_fakes import DockFakeLidar

    opened = []

    class Driver(DockFakeLidar):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.t0 = None                                          # like the driver: the session clock starts at start()

        def start(self):
            self.t0 = self.clock()

    def fake_open(cls, port, **kwargs):
        opened.append((port, kwargs))
        return Driver(clock=kwargs.get("clock", time.monotonic))
    monkeypatch.setattr(rplidar_c1.RplidarC1Source, "open", classmethod(fake_open))
    window, dock = build_window(None, port="COM_GIA", recording=None)
    dock.timer.stop()
    window._timer.stop()
    try:
        dock.connect_source()
        assert opened == [("COM_GIA", {"clock": RIG_CLOCK})] and dock.source.clock is RIG_CLOCK
        info = dock.recording_info()
        assert (info["kind"], info["port"], info["clock_ok"], info["why"]) == ("live", "COM_GIA", True, "")
        assert info["describe"]["driver"] == "tests.rig_fakes.DockFakeLidar" and info["settings"]["window"] == 3
        dock.disconnect_source()
        assert dock.recording_info() is None
    finally:
        dock.shutdown()
        window.close()
    with ScanRecorder(tmp_path / "p", {"source_id": "c1"}) as recorder:
        recorder.add(scan_with_object(0.0, 1.2, angle_deg=45.0))
        recorder.add(scan_with_object(0.1, 1.2, angle_deg=45.0))
    window, dock = build_window(None, port=None, recording=recorder.path)
    dock.timer.stop()
    window._timer.stop()
    try:
        dock.connect_source()
        assert isinstance(dock.source, PacedReplay) and dock.source.clock is RIG_CLOCK
        info = dock.recording_info()
        assert (info["kind"], info["recording"], info["clock_ok"]) == ("replay", str(recorder.path), True)
    finally:
        dock.shutdown()
        window.close()


def test_only_the_current_reader_feeds_the_recording(qapp):
    from autopark.rig.recording import LidarTap
    from tests.rig_fakes import DockFakeLidar

    window, dock = build_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()
    sink = object()
    dock.record_sink = lambda: sink
    try:
        first = DockFakeLidar()
        dock.attach_source(first, start_thread=False)
        tap1 = dock.reader.source
        assert isinstance(tap1, LidarTap) and tap1.inner is first and dock.source is first
        assert tap1.sink() is sink and dock.recording_info()["clock_ok"] and dock.recording_info()["kind"] == "other"
        key1 = dock.recording_info()["source_key"]
        dock.disconnect_source()
        assert tap1.sink() is None and dock.recording_info() is None    # a reader still exiting cannot push scans
        second = DockFakeLidar()
        dock.attach_source(second, start_thread=False)
        tap2 = dock.reader.source
        assert tap1.sink() is None and tap2.sink() is sink and dock.recording_info()["source_key"] != key1
        dock.disconnect_source()
        other = FakeSource()                                         # no rig clock, no t0: never feeds a recording
        dock.attach_source(other, start_thread=False)
        info = dock.recording_info()
        assert dock.reader.source.sink() is None and not info["clock_ok"] and "perf_counter" in info["why"]
        dock.chk_mirror.setChecked(True)                             # the mirror still reaches the raw source
        assert other.mirror is True
        stats = dock.recording_stats()
        assert stats["scans"] == 0 and stats["driver"] == {"fake": True}
    finally:
        dock.shutdown()
        window.close()


def test_a_session_recording_folder_replays_in_the_lidar_dock(qapp, tmp_path, no_serial):
    """`ui.lidar_app --recording <thư mục>`: every LiDAR part of a session recording replays in the dock, the board
    follows it, and the end of the replay disconnects (2026-10-02, T3)."""
    from autopark.rig.recording import RigRecorder
    from autopark.video.multicam import RIG_CLOCK

    folder = tmp_path / "phiên"
    t0 = RIG_CLOCK()
    rec = RigRecorder(folder, ports=[], lidar=True, clock=lambda: t0, lidar_scans_per_part=4).start()
    for k in range(10):
        t = t0 + 0.05 * k
        rec.add_scan(scan_with_object(t, 1.2, angle_deg=45.0), t, None)
    assert rec.stop(wait=True, timeout=5.0)["state"] == "xong"
    assert len(list((folder / "lidar").glob("part_*.npz"))) == 3
    window, dock = build_window(None, port=None, recording=folder)
    dock.timer.stop()
    window._timer.stop()
    try:
        dock.connect_source()
        assert dock.source is not None and dock.recording_info()["kind"] == "replay"
        deadline = time.perf_counter() + 5.0
        while dock.source is not None and time.perf_counter() < deadline:
            dock.tick()
            time.sleep(0.02)
        assert dock.source is None and dock.scans == 10 and "hết bản ghi" in dock.last_error
        assert dock.bridge.owned()                                   # the board followed the replayed object
    finally:
        dock.shutdown()
        window.close()


class FakePoseProvider:
    """Nguồn tư thế giả cho ngăn LiDAR (T2): tư thế theo dấu perf của từng vòng, gá theo cấu hình định vị mặc định."""

    def __init__(self):
        from autopark.lidar.pose_config import load_lidar_pose_config

        self.config = load_lidar_pose_config()
        self.answers = {}

    def pose_for_stamp(self, t_perf):
        return self.answers.get(t_perf, ("pending", None))


def test_scans_are_anchored_at_their_localized_pose_or_dropped(qapp):
    """Có pose_provider: vòng quét vào lớp LiveLidar ở tư thế OK của chính nó (gá theo cấu hình), vòng "bad", vòng chờ
    quá 0,3 s và vòng không có dấu perf bị bỏ và đếm; mũi tên = tư thế OK gần nhất; không neo ở điểm xuất phát nữa."""
    import time

    from autopark.domain.types import Pose
    from autopark.fusion.layers import sensor_pose_in_map

    window, dock = build_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()
    source = FakeSource()
    provider = FakePoseProvider()
    dock.pose_provider = provider
    dock.attach_source(source, start_thread=False)
    mount = provider.config.mount.as_tuple()
    assert dock.layer.mount == pytest.approx(mount)
    now = time.perf_counter()
    good, bad, late = now, now + 0.001, now + 0.002
    pose = Pose(0.9, 1.1, math.radians(15))
    provider.answers = {good: ("ok", pose), bad: ("bad", None)}
    source.t = 0.1
    dock.queue.put((scan_with_object(0.1, 1.0), None, None, good))
    dock.tick()
    assert dock.anchor == pose and dock.layer.last_sensor_pose == pytest.approx(sensor_pose_in_map(pose, mount))
    source.t = 0.25
    dock.queue.put((scan_with_object(0.2, 1.0), None, None, bad))
    dock.queue.put((scan_with_object(0.25, 1.0), None, None, late))
    dock.tick()
    assert dock.pose_dropped == 1 and len(dock._pending) == 1                # "late" còn chờ tư thế
    later = Pose(1.0, 1.1, math.radians(15))
    provider.answers[late] = ("ok", later)
    dock.tick()
    assert dock.anchor == later and not dock._pending
    source.t = 0.35
    dock.queue.put((scan_with_object(0.3, 1.0), None, None, time.perf_counter() - 1.0))   # chờ quá 0,3 s: bỏ
    dock.queue.put((scan_with_object(0.35, 1.0), None, None))                            # không có dấu perf: bỏ
    dock.tick()
    assert dock.pose_dropped == 3 and not dock._pending
    assert "bỏ vì chưa có tư thế: 3 vòng" in dock.lbl_points.text()
    assert dock.anchor == later                                              # đang chỉnh: không về điểm xuất phát
    dock.pose_provider = None                                               # không còn nguồn: như trước, gá 0
    dock.tick()
    assert dock.layer.mount == (0.0, 0.0, 0.0) and dock.anchor == window.session.scenario.start
    dock.shutdown()
    window.close()


def test_consumers_get_every_reader_and_a_feed_reset_on_disconnect_or_mirror_change(qapp):
    window, dock = build_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()

    class Consumer:
        def __init__(self):
            self.events = []

        def on_scan(self, *args):
            self.events.append("scan")

        def feed_reset(self, reason):
            self.events.append(("reset", reason))

        def set_lidar_mirror(self, mirror):
            self.events.append(("mirror", mirror))

    consumer = Consumer()
    dock.add_scan_consumer(consumer)
    dock.add_scan_consumer(consumer)
    assert dock.scan_consumers == [consumer]
    source = FakeSource()
    dock.attach_source(source, start_thread=False)
    assert dock.reader.consumers is dock.scan_consumers and consumer.events == [("mirror", False)]
    dock.chk_mirror.setChecked(True)
    assert consumer.events[-2:] == [("reset", "đổi chiều góc"), ("mirror", True)]
    dock.disconnect_source()
    assert consumer.events[-1] == ("reset", "ngắt LiDAR")
    dock.remove_scan_consumer(consumer)
    assert dock.scan_consumers == []
    dock.shutdown()
    window.close()
