"""Giao diện bàn thử, chạy offscreen với nguồn giả: ô camera có ảnh, lớp tô theo ngưỡng, chụp bộ ảnh, AI lỗi, đóng thì dừng."""
import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.rig.core import Rig, RigConfig  # noqa: E402
from autopark.ui.rig_app import RigWindow, format_metrics, overlay  # noqa: E402
from tests.rig_fakes import FakeLidar, FakeSegmenter, fake_manager  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def test_overlay_colours_follow_threshold():
    image = np.zeros((2, 2, 3), np.uint8)
    prob = np.array([[0.2, 0.6], [0.1, 0.9]], np.float32)
    low = overlay(image, prob, 0.5, 1.0)
    assert tuple(low[0, 1]) == (50, 50, 230) and tuple(low[0, 0]) == (60, 190, 60)
    high = overlay(image, prob, 0.95, 1.0)
    assert tuple(high[1, 1]) == (60, 190, 60)
    assert overlay(image, None, 0.5, 0.5) is image


def test_window_shows_cameras_overlay_lidar_and_snapshots_into_unicode_folder(qapp, tmp_path):
    cams = fake_manager(ports=(1, 2, 3, 4), period=0.02, broken=(4,))
    rig = Rig(cams, RigConfig(checkpoint="m.pt", display_width=32), make_segmenter=lambda p: FakeSegmenter(p),
              open_lidar=lambda: FakeLidar(period=0.05))
    window = RigWindow(rig, checkpoints=[], snapshot_dir=tmp_path / "ảnh sa bàn")
    try:
        pump(qapp, 1.2)
        assert window.tiles[1].pixmap is not None and "BLOCKED 50%" in window.tiles[1].detail
        assert window.tiles[1].pixmap.width() == 32 and window.tiles[1].pixmap.height() == 24     # 4:3 không méo
        assert window.tiles[4].pixmap is None and "KHÔNG MỞ ĐƯỢC" in window.tiles[4].detail and window.tiles[4].alert
        assert window.scan_view.scan is not None
        window.thr_slider.setValue(19)                      # 0,95: không pixel nào BLOCKED
        pump(qapp, 0.2)
        assert "BLOCKED 0%" in window.tiles[2].detail and "0,95" in window.thr_label.text() and window.threshold == 0.95
        folder = window.snapshot()
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        for name in ("cam_p1.png", "prob_blocked_p1.png", "overlay_p1.jpg"):
            data = np.frombuffer((folder / name).read_bytes(), np.uint8)
            assert cv2.imdecode(data, cv2.IMREAD_UNCHANGED) is not None
        assert meta["failed_writes"] == [] and meta["source"] == "ai_set" and meta["missing_ports"] == [4]
        assert meta["threshold"] == pytest.approx(0.95) and meta["cameras"]["1"]["blocked_fraction_at_threshold"] == 0.0
        assert meta["cameras"]["1"]["prob_size"] == [32, 24] and "age_ms" in meta["cameras"]["1"] and "age_ms" in meta["lidar"]
        assert meta["lidar"]["age_ms"] >= 0                 # vòng LiDAR lấy cùng lúc với khung, không phải sau khi ghi ảnh
        cam1 = meta["cameras"]["1"]
        assert cam1["truncated_frames_so_far"] == 0 and cam1["torn_frames_so_far"] == 0
        assert isinstance(cam1["bottom_repeat_share"], float) and cam1["source_rejects_damaged"] is None   # nguồn giả
        assert "cắt 0" in window.tiles[1].detail
        window.chk_ai.setChecked(False)                     # tắt AI: vẫn hiện ảnh sống, không có lớp tô
        pump(qapp, 0.3)
        assert "BLOCKED" not in window.tiles[1].detail
        folder2 = window.snapshot()
        assert json.loads((folder2 / "meta.json").read_text(encoding="utf-8"))["source"] == "latest_frames_unsynced"
        window.btn_reset.click()
        text = format_metrics(rig.snapshot(), window.threshold)
        assert "cổng 4" in text and "LỖI MỞ" in text and "Hz" in text and "bộ/s" in text and "TẮT" in text
    finally:
        window.close()
    assert not any(w.is_alive() for w in cams.workers.values())


def test_failing_ai_is_shown_instead_of_a_frozen_overlay(qapp, tmp_path):
    cams = fake_manager(ports=(1, 2), period=0.02)
    rig = Rig(cams, RigConfig(checkpoint="m.pt", display_width=32), make_segmenter=lambda p: FakeSegmenter(p, fail=True))
    window = RigWindow(rig, checkpoints=[], snapshot_dir=tmp_path)
    try:
        pump(qapp, 1.0)
        window.update_metrics()
        assert window.tiles[1].alert and "AI" in window.tiles[1].detail and "hết bộ nhớ" in window.tiles[1].detail
        assert "LỖI SUY LUẬN" in window.metrics.text()
        assert "BLOCKED" not in window.tiles[1].detail                  # không bày lớp tô cũ
    finally:
        window.close()
