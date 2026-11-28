from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("cv2")

from autopark.perception import bev
from autopark.perception.surround_view import SurroundViewRenderer


def test_preview_projects_four_directions_and_masks_vehicle(tmp_path):
    renderer = SurroundViewRenderer(extrinsics_path=tmp_path / "missing.json")
    assert renderer.is_preview and "ước lượng" in renderer.notice
    colors = {1: (0, 30, 210), 2: (0, 170, 50), 3: (200, 0, 0), 4: (70, 180, 190)}
    frames = {port: np.full((720, 1280, 3), color, dtype=np.uint8) for port, color in colors.items()}
    background = renderer.render({})
    surround = renderer.render(frames)
    assert surround.shape == background.shape == (480, 480, 3)
    assert surround.dtype == np.uint8
    points = {1: (65, 240), 2: (415, 240), 3: (240, 65), 4: (240, 415)}
    for port, at in points.items():
        assert tuple(surround[at]) == colors[port]
    assert np.array_equal(surround[210:269, 223:257], background[210:269, 223:257])

    front_only = renderer.render({1: frames[1], 3: frames[3][::2]})
    assert tuple(front_only[points[1]]) == colors[1]
    for port in (2, 3, 4):
        assert np.array_equal(front_only[points[port]], background[points[port]])


def test_renderer_requires_every_camera_measured_and_accepted(monkeypatch):
    nominal, _ = bev.synthetic_rig()
    cameras = {name: replace(camera, extrinsics_measured=True, acceptance_all_pass=True)
               for name, camera in nominal.items()}
    monkeypatch.setattr(bev, "load_rig", lambda *args, **kwargs: (cameras, None, {}))
    assert not SurroundViewRenderer().is_preview

    cameras["p2"] = replace(cameras["p2"], synthetic=("nội tham",))
    assert SurroundViewRenderer().is_preview


def _measured_renderer(monkeypatch, **kwargs):
    nominal, _ = bev.synthetic_rig(width=1280, height=720)
    cameras = {name: replace(camera, extrinsics_measured=True, acceptance_all_pass=True)
               for name, camera in nominal.items()}
    monkeypatch.setattr(bev, "load_rig", lambda *args, **kw: (cameras, None, {}))
    renderer = SurroundViewRenderer(**kwargs)
    assert not renderer.is_preview and renderer._gaps.any()
    return renderer


def _render_until(renderer, frames, done, timeout_s=5.0):
    import time
    deadline = time.monotonic() + timeout_s
    image = renderer.render(frames)
    while not done() and time.monotonic() < deadline:
        time.sleep(0.02)
        image = renderer.render(frames)
    return renderer.render(frames)


def test_ai_fill_paints_blind_area_and_marks_it(monkeypatch):
    calls = []

    def fake_fill(image, mask):
        calls.append(mask.copy())
        return np.full_like(image, (10, 200, 30))

    renderer = _measured_renderer(monkeypatch, ai_fill_fn=fake_fill)
    frames = {port: np.full((720, 1280, 3), 90, np.uint8) for port in (1, 2, 3, 4)}
    first = renderer.render(frames)
    assert "loang" in renderer.notice                      # chưa có kết quả AI: tạm tô màu loang
    image = _render_until(renderer, frames, lambda: renderer._filler.latest() is not None)
    assert "AI vẽ" in renderer.notice and 1 <= len(calls) <= 4          # mỗi ô góc có vùng thiếu một lần
    region = renderer._gaps & ~renderer._car_mask
    painted = image[region]
    plain = np.all(painted == (10, 200, 30), axis=1)
    assert plain.mean() > 0.7                               # phần lớn vùng mù là màu AI trả về
    assert (~plain).any()                                   # còn lại là sọc đánh dấu
    assert np.array_equal(image[renderer._car_mask], renderer._background[renderer._car_mask])
    assert first.shape == image.shape
    renderer.close()


def test_ai_failure_falls_back_to_blend(monkeypatch):
    def broken(image, mask):
        raise RuntimeError("không có GPU")

    renderer = _measured_renderer(monkeypatch, ai_fill_fn=broken)
    frames = {port: np.full((720, 1280, 3), 90, np.uint8) for port in (1, 2, 3, 4)}
    image = _render_until(renderer, frames, lambda: renderer._filler.error is not None)
    assert "AI tắt" in renderer.notice and "không có GPU" in renderer.notice
    assert image.dtype == np.uint8 and image.shape == (480, 480, 3)


def test_background_filler_refreshes_only_on_change():
    import time
    from autopark.perception import bev_inpaint

    now = [0.0]
    calls = []
    mask = np.zeros((40, 40), bool)
    mask[15:25, 15:25] = True
    filler = bev_inpaint.BackgroundFiller(lambda img, m: calls.append(1) or img, mask, clock=lambda: now[0])

    def wait_idle():
        deadline = time.monotonic() + 2
        while filler._pending is not None and time.monotonic() < deadline:
            time.sleep(0.005)

    grey = np.full((40, 40, 3), 100, np.uint8)
    filler.offer(grey); wait_idle()
    assert len(calls) == 1 and filler.latest() is not None
    now[0] = 1.0
    filler.offer(grey); wait_idle()
    assert len(calls) == 1                                  # cảnh không đổi, kết quả còn mới
    now[0] = 1.1
    filler.offer(np.full((40, 40, 3), 200, np.uint8)); wait_idle()
    assert len(calls) == 2                                  # quanh vùng thiếu đổi rõ: vẽ lại
    now[0] = 1.2
    filler.offer(np.full((40, 40, 3), 30, np.uint8)); wait_idle()
    assert len(calls) == 2                                  # đổi tiếp nhưng chưa đủ REFRESH_S từ lần chạy trước
    now[0] = 1.1 + bev_inpaint.MAX_AGE_S + 0.5
    filler.offer(np.full((40, 40, 3), 30, np.uint8)); wait_idle()
    assert len(calls) == 3                                  # kết quả đã cũ: vẽ lại
    filler.close()


def test_stripes_can_be_turned_off(monkeypatch):
    renderer = _measured_renderer(monkeypatch, ai_fill_fn=lambda image, mask: np.full_like(image, (10, 200, 30)))
    frames = {port: np.full((720, 1280, 3), 90, np.uint8) for port in (1, 2, 3, 4)}
    _render_until(renderer, frames, lambda: renderer._filler.latest() is not None)
    renderer.mark_ai = False
    image = renderer.render(frames)
    region = renderer._gaps & ~renderer._car_mask
    assert np.all(image[region] == (10, 200, 30))          # không sọc: đúng màu AI trả về
    assert "AI vẽ" in renderer.notice                       # dòng báo vẫn nói đó không phải hình thật
    renderer.close()


def test_panel_toggle_is_remembered_and_reaches_renderer(tmp_path):
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from autopark.ui.surround_view_panel import SurroundViewPanel

    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)

    class Fake:
        is_preview, notice, mark_ai = False, "ok", True

        def render(self, frames):
            return np.zeros((480, 480, 3), np.uint8)

    fake = Fake()
    panel = SurroundViewPanel(renderer_factory=lambda: fake, settings=settings)
    assert panel.mark_ai_box.isChecked()
    panel.mark_ai_box.setChecked(False)
    assert settings.value("bev/soc_vung_ai") == "false"
    panel._render({})
    assert fake.mark_ai is False
    panel.shutdown()
    again = SurroundViewPanel(renderer_factory=lambda: fake, settings=settings)
    assert not again.mark_ai_box.isChecked()
    again.shutdown()
    assert app is not None


def test_lidar_point_in_blind_area_turns_it_orange(monkeypatch):
    renderer = _measured_renderer(monkeypatch, ai_fill_fn=lambda image, mask: np.full_like(image, (10, 200, 30)))
    renderer.mark_ai = False
    frames = {port: np.full((720, 1280, 3), 90, np.uint8) for port in (1, 2, 3, 4)}
    _render_until(renderer, frames, lambda: renderer._filler.latest() is not None)
    region = renderer._gaps & ~renderer._car_mask
    rows, cols = np.nonzero(region)
    far = np.argmax((rows - 240) ** 2 + (cols - 240) ** 2)          # một điểm vùng mù xa thân xe
    from autopark.perception import surround_view as sv
    x = sv._CENTER_X - (rows[far] + 0.5 - sv._CANVAS_SIZE / 2) * renderer._res
    y = -(cols[far] + 0.5 - sv._CANVAS_SIZE / 2) * renderer._res
    image = renderer.render(frames, lidar_xy=np.array([[x, y]]))
    assert renderer.lidar_blocked_px > 0 and "LiDAR thấy vật" in renderer.notice
    assert not np.array_equal(image[rows[far], cols[far]], (10, 200, 30))       # không còn sàn AI ở đó
    clean = renderer.render(frames, lidar_xy=np.array([[0.1, 0.0], [5.0, 5.0]]))  # trong thân xe / ngoài khung
    assert renderer.lidar_blocked_px == 0 and np.all(clean[region] == (10, 200, 30))
    renderer.close()


def test_tiled_fill_reuses_unchanged_corners():
    from autopark.perception import bev_inpaint

    now = [0.0]
    calls = []
    tiled = bev_inpaint.TiledFill(lambda img, m: calls.append(m.shape) or np.full_like(img, 50), (100, 100),
                                  overlap=6, clock=lambda: now[0])
    mask = np.zeros((100, 100), bool)
    mask[5:15, 5:15] = True                                  # góc trên-trái
    mask[85:95, 85:95] = True                                # góc dưới-phải
    image = np.full((100, 100, 3), 120, np.uint8)
    out = tiled(image, mask)
    assert len(calls) == 2 and out[10, 10, 0] == 50 and out[90, 10, 0] == 120   # (90, 10): chỉ ô dưới-trái, không thiếu
    now[0] = 0.5
    changed = image.copy(); changed[80:100, 80:100] = 220   # chỉ góc dưới-phải đổi
    tiled(changed, mask)
    assert len(calls) == 3
    tiled(changed, mask)
    assert len(calls) == 3                                   # không đổi gì: không suy luận lại


def test_feather_alpha_ramps_outside_mask():
    from autopark.perception import bev_inpaint

    mask = np.zeros((30, 30), bool)
    mask[10:20, 10:20] = True
    a = bev_inpaint.feather_alpha(mask, 4)
    assert a[15, 15] == 1 and a[15, 22] < 1 and a[15, 22] > 0 and a[15, 28] == 0


def test_moving_car_fills_blind_area_from_memory(monkeypatch):
    renderer = _measured_renderer(monkeypatch, ai_fill=False)
    rng = np.random.default_rng(1)
    frames = {port: rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8) for port in (1, 2, 3, 4)}
    renderer.render(frames, lidar_pose=(0.0, 0.0, 0.0), pose_epoch=1)
    assert renderer.memory_fraction == 0.0                   # đứng yên: vùng mù chưa từng thấy
    for step in range(1, 6):                                  # tiến 5 cm mỗi khung: góc trước vào vùng camera trước đã thấy
        renderer.render(frames, lidar_pose=(0.05 * step, 0.0, 0.0), pose_epoch=1)
    assert renderer.memory_fraction > 0.05 and "Ảnh nhớ" in renderer.notice
    renderer.render(frames, lidar_pose=(0.25, 0.0, 0.0), pose_epoch=2)   # odometry khởi động lại: bỏ ảnh nhớ
    assert renderer.memory_fraction == 0.0
