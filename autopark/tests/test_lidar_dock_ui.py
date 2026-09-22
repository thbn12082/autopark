"""LiDAR dock inside the phase-0 cockpit, driven by hand offscreen: the board's obstacles follow the live scan,
planning freezes them, and an object appearing on the path stops the virtual car."""
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.application.session import SessionState  # noqa: E402
from autopark.domain.types import Bounds  # noqa: E402
from autopark.ui.items import ObstacleItem  # noqa: E402
from autopark.ui.lidar_app import build_window  # noqa: E402
from autopark.ui.scan_view import ScanView  # noqa: E402
from tests.test_fusion import scan_with_object  # noqa: E402


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


def test_dock_without_source_is_idle(qapp):
    window, dock = build_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()
    dock.tick()
    assert dock.btn_connect.text() == "Kết nối" and not dock.btn_clear.isEnabled()
    dock.connect_source()                                           # COM9 does not exist: reported, not raised
    assert dock.source is None and "Không kết nối được" in dock.lbl_device.text()
    window.close()
