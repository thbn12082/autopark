"""Giao diện bàn thử, chạy offscreen với nguồn giả: ô camera có ảnh, lớp tô theo ngưỡng, chụp bộ ảnh, AI lỗi, đóng thì dừng."""
import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("PySide6")

from PySide6.QtGui import QFontMetrics, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.rig.core import Rig, RigConfig  # noqa: E402
from autopark.ui.rig_app import CameraTile, RigWindow, format_metrics, overlay  # noqa: E402
from autopark.video.multicam import CameraSpec, MultiCameraManager  # noqa: E402
from autopark.video.sources import _frame  # noqa: E402
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
        meta2 = json.loads((folder2 / "meta.json").read_text(encoding="utf-8"))
        assert meta2["source"] == "latest_frames_unsynced" and "unsynced_ports" not in meta2
        assert meta2["cameras"] and all(c["frame_from"] == "live_unsynced" for c in meta2["cameras"].values())
        assert meta["cameras"]["1"]["frame_from"] == "this_set"
        window.btn_reset.click()
        text = format_metrics(rig.snapshot(), window.threshold)
        assert "cổng 4" in text and "LỖI MỞ" in text and "Hz" in text and "bộ/s" in text and "TẮT" in text
    finally:
        window.close()
    assert not any(w.is_alive() for w in cams.workers.values())


def push(cams, port, t, value):
    """Như CameraWorker nhận một khung tốt ở stamp t (luồng camera không chạy: nạp tay, đồng hồ giả)."""
    w = cams.workers[port]
    w.seq += 1
    w.ring.append((w.seq, _frame(f"cam_p{port}", t, "x", np.full((24, 32, 3), value, np.uint8))))
    w.stats.frames += 1
    w.stats.last_stamp = t
    w.stats.recent.append(t)
    w.arrivals.append(t)


def test_lagging_camera_keeps_its_last_overlay_marked_slow_and_snapshot_records_its_source(qapp, tmp_path):
    now = [1.00]
    clock = lambda: now[0]  # noqa: E731
    specs = [CameraSpec(port=p, index=k) for k, p in enumerate((1, 2, 3))]
    cams = MultiCameraManager(specs, ring=3, open_source=lambda s: None, clock=clock)
    rig = Rig(cams, RigConfig(checkpoint="m.pt", display_width=32, max_wait_s=0.06),
              make_segmenter=lambda p: FakeSegmenter(p, delay=0.0), clock=clock)
    window = RigWindow(rig, checkpoints=[], snapshot_dir=tmp_path, start=False)
    try:
        rig.ai._ensure_model()
        for p in (1, 2, 3):
            push(cams, p, 1.00, 100)
        assert rig.ai.step()                                         # lô 0: đủ ba camera
        push(cams, 1, 1.04, 100)
        push(cams, 2, 1.04, 100)
        now[0] = 1.065                                               # camera 3 im 65 ms > 60: lô 1 không có nó
        assert rig.ai.step() and rig.ai.result().frame_set.lagging == [3]
        window.tick()
        t3, t1 = window.tiles[3], window.tiles[1]
        assert t3.pixmap is not None and t3.alert
        # ghi chú "chậm" đứng ĐẦU dải chữ (ô hẹp: phần số đo phía sau mới là phần bị rút gọn)
        assert t3.detail.startswith("chậm: lớp tô của lô #0, cách đây 65 ms · ")
        assert "BLOCKED 50%" in t3.detail and "tuổi 65 ms" in t3.detail     # lớp tô cũ trên đúng khung đã chấm (1,00)
        img = t3.pixmap.toImage()
        top, bottom = img.pixelColor(16, 2), img.pixelColor(16, 20)   # FakeSegmenter: nửa trên BLOCKED, nửa dưới FREE
        assert top.red() > top.green() + 40 and bottom.green() > bottom.red() + 40
        assert "chậm" not in t1.detail and not t1.alert and "BLOCKED 50%" in t1.detail
        folder = window.snapshot()
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        assert meta["lagging_ports"] == [3] and meta["result_batch_id"] == 1 and meta["missing_ports"] == []
        c1, c3 = meta["cameras"]["1"], meta["cameras"]["3"]
        assert c3["lagging"] and c3["ai_prob_from"] == "earlier_batch" and c3["prob_batch_id"] == 0
        assert c3["stamp_s"] == pytest.approx(1.00) and c3["prob_age_ms"] == pytest.approx(65.0)
        assert not c1["lagging"] and c1["ai_prob_from"] == "this_set" and c1["prob_batch_id"] == 1
        # nguồn của TỪNG ảnh: cổng 3 là khung đã chấm ở lô 0, không phải khung của bộ AI này
        assert c3["frame_from"] == "earlier_batch" and c1["frame_from"] == "this_set" and meta["unsynced_ports"] == []
        assert (folder / "prob_blocked_p3.png").exists() and meta["set_skew_ms"] == 0.0
        # kết quả cũ của camera 3 quá AI_STALE_S (bộ 1,50 do luồng nền ghép, không chấm): ảnh sống, không tô, nói rõ
        now[0] = 1.50
        for p in (1, 2, 3):
            push(cams, p, 1.50, 100)
        assert cams.latest_set(0.1, max_wait_s=0.06) is not None
        push(cams, 1, 1.54, 100)
        push(cams, 2, 1.54, 100)
        now[0] = 1.57
        assert rig.ai.step() and rig.ai.result().carried[3].batch_id == 0
        window.tick()
        assert t3.detail.startswith("chậm: chưa có kết quả AI mới, ảnh sống không tô · ")
        assert "BLOCKED" not in t3.detail and t3.alert
        meta = json.loads((window.snapshot() / "meta.json").read_text(encoding="utf-8"))
        assert meta["cameras"]["3"]["ai_prob_from"] is None and meta["cameras"]["3"]["lagging"]
        assert meta["cameras"]["3"]["stamp_s"] == pytest.approx(1.50) and not meta["cameras"]["3"]["deferred"]
        # ảnh cổng 3 là khung SỐNG (1,50), MỚI hơn không ít so với khung chấm được của bộ cũ: ghi rõ, không để người đọc
        # tưởng là khung của bộ AI (meta["source"] vẫn là "ai_set" cho cả lần chụp — giá trị cũ giữ để tương thích)
        assert meta["cameras"]["3"]["frame_from"] == "live_unsynced" and meta["unsynced_ports"] == [3]
        assert meta["cameras"]["1"]["frame_from"] == "this_set" and meta["source"] == "ai_set"
        text = format_metrics(rig.snapshot(), window.threshold)
        assert "chờ camera chậm tối đa max(60 ms; 1,5 chu kỳ) = 60 ms" in text
        assert "bộ thiếu cam chậm 2" in text and "hỏng 0  chậm 2" in text and "để dành lệch pha 0" in text
    finally:
        window.close()


def test_tile_caption_keeps_the_note_whole_and_elides_the_stats(qapp):
    tile = CameraTile(4)
    note = "chậm: lớp tô của lô #12345, cách đây 450 ms"
    tile.set_image(None, f"{note} · 16,6 fps · cũ 1234 · cắt 567 · tuổi 62 ms · BLOCKED 50%", True)
    fm = QFontMetrics(CameraTile.band_font())
    # phông của nền offscreen rộng hơn Segoe UI nhiều: lấy bề rộng ô từ chính phông đang dùng — vừa ghi chú, thiếu chỗ số đo
    width = fm.horizontalAdvance(f"cổng 4   {note} · 16,6 fps") + 16
    tile.resize(width, 200)
    img = QImage(tile.size(), QImage.Format.Format_ARGB32)
    tile.render(img)
    assert tile.shown_text.startswith(f"cổng 4   {note}") and tile.shown_text.endswith("…"), tile.shown_text
    assert fm.horizontalAdvance(tile.shown_text) <= width - 16
    assert "BLOCKED" not in tile.shown_text                         # phần số đo phía sau là phần bị rút gọn


def test_camera_deferred_for_phase_keeps_its_last_overlay_without_a_slow_alarm(qapp, tmp_path):
    now = [0.0]
    clock = lambda: now[0]  # noqa: E731
    specs = [CameraSpec(port=p, index=k) for k, p in enumerate((1, 2))]
    cams = MultiCameraManager(specs, ring=3, open_source=lambda s: None, clock=clock)
    rig = Rig(cams, RigConfig(checkpoint="m.pt", display_width=32, max_wait_s=0.06),
              make_segmenter=lambda p: FakeSegmenter(p, delay=0.0), clock=clock)
    window = RigWindow(rig, checkpoints=[], snapshot_dir=tmp_path, start=False)
    period = 1 / 24
    # cổng 2 mở sau, 2 ms sau khung cổng 1 (như test_multicam_rig: bốn bộ ghép lệch một chu kỳ rồi một bộ để dành)
    events = sorted([(1.0 + k * period, 1) for k in range(8)] + [(1.002 + k * period, 2) for k in range(2, 7)])
    try:
        rig.ai._ensure_model()
        for t, p in events:
            push(cams, p, t, 100)
            now[0] = t + 0.001
            rig.ai.step()
        r = rig.ai.result()
        assert r.frame_set.deferred == [1] and sorted(r.probs) == [2] and r.frame_set.lagging == []
        held = r.carried[1]                                          # lô trước, đúng khung cổng 1 đã chấm (1,25)
        assert held.batch_id == r.batch_id - 1 and held.frame.meta.stamp.t == pytest.approx(1.0 + 6 * period)
        window.tick()
        t1, t2 = window.tiles[1], window.tiles[2]
        assert t1.detail.startswith(f"lệch pha, chấm ở bộ sau: lớp tô của lô #{held.batch_id}, cách đây 42 ms · ")
        assert "BLOCKED 50%" in t1.detail and not t1.alert and "chậm:" not in t1.detail
        assert not t2.alert and "BLOCKED 50%" in t2.detail
        meta = json.loads((window.snapshot() / "meta.json").read_text(encoding="utf-8"))
        assert meta["deferred_ports"] == [1] and meta["lagging_ports"] == []
        c1 = meta["cameras"]["1"]
        assert c1["deferred"] and not c1["lagging"] and c1["ai_prob_from"] == "earlier_batch"
        assert c1["prob_batch_id"] == held.batch_id
        assert c1["frame_from"] == "earlier_batch" and meta["cameras"]["2"]["frame_from"] == "this_set"
        assert meta["unsynced_ports"] == []
        assert "để dành lệch pha 1" in format_metrics(rig.snapshot(), window.threshold)
    finally:
        window.close()


def test_live_window_with_a_slow_camera_never_drops_its_tile_to_raw_frames(qapp, tmp_path):
    cams = fake_manager(ports=(1, 2, 3, 4), period=0.02, periods={4: 0.06})
    rig = Rig(cams, RigConfig(checkpoint="m.pt", display_width=32, max_wait_s=0.03), make_segmenter=lambda p: FakeSegmenter(p))
    window = RigWindow(rig, checkpoints=[], snapshot_dir=tmp_path)
    try:
        pump(qapp, 1.0)
        slow_ticks = 0
        for _ in range(25):
            pump(qapp, 0.03)
            window.tick()
            assert "BLOCKED" in window.tiles[4].detail, window.tiles[4].detail   # luôn có lớp tô (bộ này hoặc lô trước)
            slow_ticks += "chậm: lớp tô của lô" in window.tiles[4].detail
            assert "BLOCKED" in window.tiles[1].detail
        assert slow_ticks > 0 and rig.cams.sets_partial_wait > 0 and rig.cams.lagging_per_port[4] > 0
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
