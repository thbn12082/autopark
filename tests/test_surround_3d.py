"""Cảnh 3D quanh xe (autopark.perception.surround_3d) và thẻ giao diện của nó."""
from __future__ import annotations

import math
import os
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("cv2")

from autopark.perception import surround_3d as s3  # noqa: E402


@pytest.fixture(scope="module")
def renderer():
    return s3.Surround3DRenderer()


@pytest.fixture(scope="module")
def demo(renderer):
    return s3.demo_frames(renderer.cameras)


def test_view_orientation_top_and_rear():
    top = s3.PRESETS["tren"][1]
    u, v, ok = top.project(np.array([[top.target[0] + 0.5, 0.0, 0.0], [top.target[0], 0.5, 0.0]]))
    assert ok.all()
    assert v[0] < top.height / 2                      # đầu xe (+x) ở phía trên ảnh
    assert u[1] < top.width / 2                       # bên trái xe (+y) ở bên trái ảnh
    rear = s3.PRESETS["sau"][1]
    position, right, down, forward = rear.basis()
    assert forward[0] > 0.5 and right[1] < -0.9 and down[2] < 0     # đứng sau nhìn tới, phải ảnh = phải xe


def test_behind_camera_is_not_visible():
    view = s3.PRESETS["sau"][1]
    position = view.basis()[0]
    _, _, ok = view.project(np.array([position - np.array([1.0, 0.0, 0.0])]))
    assert not ok.any()


def test_bowl_points_lie_on_floor_and_wall():
    bowl = s3.Bowl()
    view = s3.PRESETS["sau_trai"][1].scaled(0.25)
    points, hit = s3.bowl_points(view, bowl, subsample=1)
    assert hit.mean() > 0.5
    p = points[hit]
    r = np.hypot(p[:, 0] - bowl.center_xy[0], p[:, 1] - bowl.center_xy[1])
    assert np.allclose(p[:, 2], bowl.height(r), atol=0.01)           # mọi điểm nằm đúng trên mặt bát
    assert (r[p[:, 2] == 0.0] <= bowl.floor_radius_m + 1e-3).all()
    assert (p[:, 2] > 0.01).any() and (r <= bowl.rim_radius_m + 1e-3).all()


def test_demo_marker_lands_where_geometry_says(renderer, demo):
    """Ô đỏ trên sàn của cảnh mẫu: ảnh camera ghép lên bát phải hiện màu đỏ đúng chỗ phép chiếu hình học chỉ ra."""
    x0, y0, x1, y1 = s3.DemoScene().marker
    for key in ("tren", "sau_phai"):
        renderer.set_view(s3.PRESETS[key][1])
        image = renderer.render(demo)
        u, v, ok = renderer.view.project(np.array([[(x0 + x1) / 2, (y0 + y1) / 2, 0.0]]))
        assert ok[0]
        b, g, r = image[int(round(v[0])), int(round(u[0]))].astype(int)
        assert r > 150 and b < 110 and g < 110, (key, (b, g, r))


def test_render_without_frames_and_overlays(renderer):
    renderer.set_view(s3.PRESETS["sau"][1])
    empty = renderer.render({})
    assert empty.shape == (renderer.view.height, renderer.view.width, 3) and empty.dtype == np.uint8
    ring = np.column_stack([0.1 + 0.6 * np.cos(np.linspace(0, 2 * math.pi, 90)),
                            0.6 * np.sin(np.linspace(0, 2 * math.pi, 90))])
    slot = [(0.3, 0.3), (0.5, 0.3), (0.5, 0.6), (0.3, 0.6)]
    drawn = renderer.render({}, s3.Overlays(lidar_xy=ring, slots=(slot,), path_xy=np.array([[0.3, 0], [0.4, 0.4]])))
    assert (drawn != empty).any()


def test_scan_to_vehicle_uses_mount():
    scan = SimpleNamespace(angles_rad=(0.0, math.pi / 2, 1.0), ranges_m=(1.0, 2.0, float("nan")))
    mount = SimpleNamespace(x_m=0.18, y_m=0.03, yaw_deg=90.0)
    xy = s3.scan_to_vehicle(scan, mount)
    assert xy.shape == (2, 2)
    assert np.allclose(xy[0], [0.18, 1.03]) and np.allclose(xy[1], [-1.82, 0.03])


def test_panel_shows_demo_then_live(renderer, demo):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from autopark.ui.surround_3d_panel import Surround3DPanel

    app = QApplication.instance() or QApplication([])
    now = [100.0]
    panel = Surround3DPanel(renderer_factory=lambda: renderer, clock=lambda: now[0])
    panel.resize(900, 600)
    panel.show()
    try:
        def settle():
            for _ in range(200):
                panel._tick()
                panel.wait_idle()
                app.processEvents()
                if panel._active is None and not panel._dirty:
                    return

        settle()
        assert panel.canvas.pixmap is not None and panel.using_demo and "Cảnh mẫu" in panel.notice.text()
        panel.submit({port: frame for port, frame in demo.items()})
        settle()
        assert not panel.using_demo and "trực tiếp" in panel.notice.text()
        panel._drag_start()
        panel._drag(40, -20)
        assert panel.quality < 1.0 and panel.view.azimuth_deg != s3.PRESETS["sau_phai"][1].azimuth_deg
        panel._drag_end()
        assert panel.quality == 1.0
        now[0] += 10.0                                  # Pi im lặng quá lâu: quay về cảnh mẫu
        settle()
        assert panel.using_demo
    finally:
        panel.shutdown()
        panel.close()


def test_pi_viewer_has_3d_tab():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from autopark.ui.remote_sensor_view import RemoteSensorWindow

    QApplication.instance() or QApplication([])
    window = RemoteSensorWindow("", camera_count=4)
    try:
        titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert "3D quanh xe" in titles and window.surround_3d is not None
    finally:
        window.close()


@pytest.mark.parametrize("azimuth", [0.0, 90.0, 210.0, 300.0])
@pytest.mark.parametrize("distance", [0.6, 1.5, 2.6])
def test_drag_stops_at_ground_and_keeps_picture(azimuth, distance):
    """Kéo xuống quá tay: camera ảo dừng ở mặt đất (hoặc trên thành bát) và mặt bát vẫn phủ kín khung hình."""
    bowl = s3.Bowl()
    view = s3.limit_view(s3.View(azimuth_deg=azimuth, elevation_deg=-90.0, distance_m=distance).scaled(0.3), bowl)
    position = view.basis()[0]
    r = math.hypot(position[0] - bowl.center_xy[0], position[1] - bowl.center_xy[1])
    assert position[2] >= s3.MIN_CAMERA_HEIGHT_M - 1e-6
    assert position[2] >= float(bowl.height(r)) - 1e-6
    _, hit = s3.bowl_points(view, bowl)
    assert hit.mean() > 0.95
    higher = s3.limit_view(s3.replace(view, elevation_deg=45.0), bowl)
    assert higher.elevation_deg == pytest.approx(45.0)              # trong giới hạn thì giữ nguyên
