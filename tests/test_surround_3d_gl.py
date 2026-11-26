"""Bản GPU của cảnh 3D (autopark.ui.surround_3d_gl).

Phần hình học luôn chạy. Phần vẽ OpenGL cần màn hình và GPU thật: chỉ chạy khi đặt AUTOPARK_GL_TEST=1 và không ép Qt
chạy ngoài màn hình (ví dụ: set AUTOPARK_GL_TEST=1 && .venv\\Scripts\\python.exe -m pytest tests/test_surround_3d_gl.py).
"""
from __future__ import annotations

import os

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("cv2")

GL_RUN = os.environ.get("AUTOPARK_GL_TEST") == "1"
if not GL_RUN:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from autopark.perception import surround_3d as s3  # noqa: E402
from autopark.ui import surround_3d_gl as g  # noqa: E402


def test_bowl_mesh_lies_on_bowl():
    bowl = s3.Bowl()
    tris = g.bowl_mesh(bowl, rings_floor=6, rings_wall=6, segments=24)
    assert tris.shape[1] == 3 and len(tris) % 3 == 0
    r = np.hypot(tris[:, 0] - bowl.center_xy[0], tris[:, 1] - bowl.center_xy[1])
    assert np.allclose(tris[:, 2], bowl.height(r), atol=1e-5)
    assert r.max() == pytest.approx(bowl.rim_radius_m, abs=1e-4)


def test_car_mesh_fits_measured_body_and_overlays():
    from autopark.perception.surround_view import BODY
    mesh = g.car_mesh(BODY)
    assert mesh.ndim == 2 and mesh.shape[1] == 10 and len(mesh) % 3 == 0
    xyz, normals = mesh[:, :3], mesh[:, 3:6]
    assert xyz[:, 0].min() >= BODY.x_min - 0.005 and xyz[:, 0].max() <= BODY.x_max + 0.005
    assert xyz[:, 1].min() >= BODY.y_min - 0.001 and xyz[:, 1].max() <= BODY.y_max + 0.001
    assert xyz[:, 2].min() == pytest.approx(0.0, abs=1e-6)            # bánh chạm sàn
    assert 0.10 < xyz[:, 2].max() < 0.13
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-4)
    tris, points = g.overlay_geometry(s3.Overlays(lidar_xy=np.zeros((5, 2)), slots=([(0, 0), (1, 0), (1, 1)],),
                                                  path_xy=np.array([[0, 0], [1, 1], [2, 1]])))
    assert len(points) == 5 and len(tris) == 6 * 3 + 6 * 2           # mỗi đoạn là một dải 2 tam giác
    empty_tris, empty_points = g.overlay_geometry(None)
    assert empty_tris.shape == (0, 7) and empty_points.shape == (0, 7)


def test_gl_unavailable_offscreen_falls_back_to_cpu():
    if GL_RUN:
        pytest.skip("đang chạy phần GPU")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    assert not g.gl_available()
    from autopark.ui.surround_3d_panel import Surround3DPanel
    panel = Surround3DPanel()
    try:
        assert not panel.gl and not isinstance(panel.canvas, g.Surround3DGLWidget)
    finally:
        panel.shutdown()


@pytest.mark.skipif(not GL_RUN, reason="cần GPU thật: đặt AUTOPARK_GL_TEST=1")
def test_gl_render_matches_geometry_and_is_fast():
    import time
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from autopark.perception.surround_view import display_cameras

    app = QApplication.instance() or QApplication([])
    assert g.gl_available()
    cams, preview, _ = display_cameras()
    widget = g.Surround3DGLWidget(cams, is_preview=preview)
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.resize(960, 600)
    widget.show()
    app.processEvents()
    try:
        widget.set_frames(s3.demo_frames(cams))
        x0, y0, x1, y1 = s3.DemoScene().marker
        for key in ("tren", "sau_phai", "truoc"):
            widget.set_view(s3.PRESETS[key][1])
            img = widget.grabFramebuffer()
            view = s3.replace(widget.view, width=img.width(), height=img.height(),
                              target=(*widget.bowl.center_xy, widget.view.target[2]))
            u, v, ok = view.project(np.array([[(x0 + x1) / 2, (y0 + y1) / 2, 0.0]]))
            if not ok[0] or not (0 <= u[0] < img.width() and 0 <= v[0] < img.height()):
                continue
            c = img.pixelColor(int(u[0]), int(v[0]))
            assert c.red() > 150 and c.green() < 110 and c.blue() < 110, (key, c.getRgb())
        t0 = time.perf_counter()
        for _ in range(30):
            widget.set_view(s3.replace(widget.view, azimuth_deg=widget.view.azimuth_deg + 12))
            widget.repaint()
        widget.context().functions().glFinish()
        assert 30 / (time.perf_counter() - t0) > 30          # xoay ít nhất 30 khung/giây
    finally:
        widget.close()
