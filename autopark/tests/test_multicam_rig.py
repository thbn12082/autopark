"""Nhiều camera + LiDAR + AI chạy đồng thời, bằng nguồn giả: ghép bộ ảnh, bỏ bộ lệch, đếm lỗi, số đo, lệnh đo."""
import json
import time

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from autopark.rig import bench  # noqa: E402
from autopark.rig.core import Rig, RigConfig  # noqa: E402
from autopark.video.multicam import RIG_CLOCK, CameraSpec, MultiCameraManager, build_set, clock_info, fit_width  # noqa: E402
from autopark.video.sources import _frame  # noqa: E402
from tests.rig_fakes import FakeLidar, FakeSegmenter, fake_manager  # noqa: E402


def ring_of(port, stamps):
    img = np.zeros((4, 4, 3), np.uint8)
    return [(k, _frame(f"cam_p{port}", t, "x", img)) for k, t in enumerate(stamps)]


def test_rig_clock_is_high_resolution():
    # time.monotonic trên Python 3.12/Windows có bước 15,6 ms: không dùng được để đo độ lệch vài chục ms
    assert RIG_CLOCK is time.perf_counter and clock_info()["resolution_s"] <= 1e-3


def test_build_set_anchors_on_the_slowest_camera_and_picks_closest_frames():
    rings = {1: ring_of(1, [0.90, 0.94, 0.98]),       # nhanh
             2: ring_of(2, [0.88, 0.92, 0.95]),       # chậm nhất: mốc = 0,95
             3: ring_of(3, [0.93, 0.96, 1.01])}
    fs = build_set(rings, now=1.02)
    assert fs.anchor_t == pytest.approx(0.95)
    assert {p: f.meta.stamp.t for p, f in fs.frames.items()} == pytest.approx({1: 0.94, 2: 0.95, 3: 0.96})
    assert fs.skew_s == pytest.approx(0.02) and fs.missing == []


def test_build_set_drops_stale_and_empty_cameras():
    rings = {1: ring_of(1, [0.9, 1.0]), 2: ring_of(2, [0.1]), 3: []}
    fs = build_set(rings, now=1.05, stale_after_s=0.5)
    assert sorted(fs.frames) == [1] and fs.missing == [2, 3]
    assert build_set({1: []}, now=1.0) is None


def test_fit_width_keeps_aspect():
    assert fit_width(1280, 720, 640) == (640, 360) and fit_width(640, 480, 640) == (640, 480)
    assert fit_width(640, 480, 320) == (320, 240) and fit_width(100, 50, 640) == (100, 50)


def test_manager_streams_sets_counts_duplicates_and_reports_broken_camera():
    cams = fake_manager(ports=(1, 2, 3, 4), period=0.02, broken=(3,), dup_every=5)
    cams.start()
    try:
        time.sleep(0.6)
        fs = cams.latest_set(max_skew_s=0.1)
        assert fs is not None and sorted(fs.frames) == [1, 2, 4] and fs.missing == [3]
        stats = cams.stats()
    finally:
        alive = cams.stop()
    by_port = {c["port"]: c for c in stats["cameras"]}
    assert by_port[3]["open_error"] and by_port[3]["stale"]
    assert by_port[1]["frames"] > 5 and by_port[1]["duplicates"] > 0 and by_port[1]["fps_last2s"] > 10
    assert stats["sets_partial"] >= 1 and alive == []
    assert all(w.source is None or w.source.closed for w in cams.workers.values())


def test_manager_rejects_sets_whose_skew_is_too_large_and_only_returns_new_sets():
    now = [1.0]
    specs = [CameraSpec(port=1, index=0), CameraSpec(port=2, index=1)]
    cams = MultiCameraManager(specs, ring=1, open_source=lambda s: None, clock=lambda: now[0])   # không start: nạp tay
    w1, w2 = cams.workers[1], cams.workers[2]
    img = np.zeros((4, 4, 3), np.uint8)
    w1.ring.append((1, _frame("cam_p1", 0.99, "x", img)))
    w2.ring.append((1, _frame("cam_p2", 0.90, "x", img)))            # lệch 90 ms
    assert cams.latest_set(max_skew_s=0.05) is None and cams.sets_rejected_skew == 1
    assert cams.latest_set(max_skew_s=0.05) is None and cams.sets_rejected_skew == 1   # cùng bộ: không đếm lại
    assert cams.sets_blocked_not_new == 0                             # bộ y hệt bộ trước không phải "bị chặn"
    w2.ring.append((2, _frame("cam_p2", 0.98, "x", img)))            # chỉ camera 2 có khung mới
    assert cams.latest_set(max_skew_s=0.05) is None                   # camera 1 vẫn khung cũ: chưa phải bộ mới
    assert cams.latest_set(max_skew_s=0.05) is None and cams.sets_blocked_not_new == 1   # cùng bộ bị chặn: đếm một lần
    w1.ring.append((2, _frame("cam_p1", 0.99, "x", img)))             # cả hai đều mới, lệch 10 ms
    fs = cams.latest_set(max_skew_s=0.05)
    assert fs is not None and fs.skew_s == pytest.approx(0.01) and cams.sets_built == 1
    assert cams.latest_set(max_skew_s=0.05) is None
    assert cams.latest_set(max_skew_s=0.05, require_new=False) is not None
    w1.ring.append((5, _frame("cam_p1", 1.00, "x", img)))             # camera 1 nhảy seq 2 → 5: 2 khung không vào bộ nào
    w2.ring.append((3, _frame("cam_p2", 1.00, "x", img)))
    assert cams.latest_set(max_skew_s=0.05) is not None and cams.frames_skipped[1] == 2
    st = cams.stats(window=None)
    assert st["skew_ms"]["n"] == 4 and st["skew_ms"]["max"] == pytest.approx(90.0)
    cams.reset_stats()
    assert cams.stats()["sets_built"] == 0 and cams.frames_skipped == {1: 0, 2: 0}


def test_rig_runs_cameras_lidar_and_ai_together():
    cams = fake_manager(period=0.02)
    rig = Rig(cams, RigConfig(checkpoint="m.pt", display_width=32, max_skew_s=0.1),
              make_segmenter=lambda path: FakeSegmenter(path), open_lidar=lambda: FakeLidar(period=0.05, fail_first=1))
    rig.start()
    try:
        time.sleep(1.5)
        result = rig.ai.result()
        snap = rig.snapshot()
        summary = rig.summary()
    finally:
        alive = rig.stop()
    assert alive == [] and summary["clock"]["name"] == "perf_counter"
    assert result is not None and sorted(result.probs) == [1, 2, 3, 4] and result.probs[1].shape == (24, 32)   # 4:3 giữ tỉ lệ
    b, n = summary["ai"]["batches"], summary["ai"]["images"]
    assert b > 5 and 3 * b < n <= 4 * b          # vài lô đầu thiếu camera chưa kịp mở (bộ ảnh thiếu, có đếm)
    assert summary["ai"]["first_batch_ms"] is not None and summary["ai"]["window"] == "cả phiên"
    vs = summary["lidar"]["vs_set"]
    assert vs["last_minus_anchor_ms"]["n"] > 5 and vs["sweep_ms"]["median"] == pytest.approx(50, abs=20)
    assert result.lidar is not None and "last_minus_anchor_ms" in result.lidar
    assert summary["lidar"]["scans"] > 5 and summary["lidar"]["errors"] == 1 and summary["lidar"]["hz_mean"] > 5
    assert summary["sets"]["sets_built"] > 5 and summary["sets"]["skew_ms"]["median"] is not None
    assert snap["cameras"]["cameras"][0]["fps_last2s"] > 10
    row = rig.series[-1]
    assert "cam_frames_1s" in row and row["ai_batches_1s"] >= 0 and 0 < sum(row["cam_frames_1s"].values()) < 400
    assert not any(w.is_alive() for w in cams.workers.values())


def test_set_loop_measures_skew_when_ai_is_off_or_disabled():
    cams = fake_manager(period=0.02)
    rig = Rig(cams, RigConfig(ai=False), open_lidar=lambda: FakeLidar(period=0.05))
    rig.start()
    try:
        time.sleep(0.6)
        s = rig.summary()
        assert rig.ai is None and s["sets"]["skew_ms"]["n"] > 0 and s["lidar"]["vs_set"]["last_minus_anchor_ms"]["n"] > 0
    finally:
        rig.stop()
    cams = fake_manager(period=0.02)
    rig = Rig(cams, RigConfig(checkpoint="a.pt"), make_segmenter=lambda p: FakeSegmenter(p))
    rig.start()
    try:
        time.sleep(0.4)
        rig.ai.enabled.clear()                                         # tắt AI trên giao diện
        time.sleep(0.1)
        built = rig.cams.sets_built
        time.sleep(0.4)
        assert rig.cams.sets_built > built                             # số bộ ảnh vẫn chạy, không đứng yên
    finally:
        rig.stop()


def test_model_switch_during_load_ends_on_the_last_choice():
    def slow(path):
        time.sleep(0.3)
        if path == "bad.pt":
            raise FileNotFoundError(path)
        return FakeSegmenter(path)

    cams = fake_manager(period=0.02)
    rig = Rig(cams, RigConfig(checkpoint="a.pt"), make_segmenter=slow)
    rig.start()
    try:
        time.sleep(0.6)
        rig.ai.request_model("b.pt")
        time.sleep(0.1)
        rig.ai.request_model("c.pt")                                   # chọn C khi B đang nạp
        time.sleep(1.2)
        assert rig.ai.checkpoint == "c.pt" and rig.ai.result().model == "fake:c.pt" and rig.ai.result().checkpoint == "c.pt"
        rig.ai.request_model("bad.pt")
        time.sleep(0.1)
        rig.ai.request_model("d.pt")                                   # chọn D khi bad đang nạp (và sẽ hỏng)
        time.sleep(1.5)
        assert rig.ai.checkpoint == "d.pt" and rig.ai.load_error is None
        rig.ai.request_model("bad.pt")
        time.sleep(0.8)
        assert rig.ai.checkpoint == "d.pt" and rig.ai.requested == "d.pt" and "FileNotFoundError" in rig.ai.load_error
    finally:
        rig.stop()


def test_bench_main_writes_summary_json(tmp_path, monkeypatch):
    def fake_build(args):
        cams = fake_manager(period=0.02)
        return Rig(cams, RigConfig(checkpoint="m.pt", display_width=16), make_segmenter=lambda p: FakeSegmenter(p),
                   open_lidar=lambda: FakeLidar(period=0.05))
    monkeypatch.setattr(bench, "build_rig", fake_build)
    code = bench.main(["--name", "t1", "--seconds", "0.6", "--warmup", "0.3", "--out", str(tmp_path)])
    data = json.loads((tmp_path / "t1.rig.json").read_text(encoding="utf-8"))
    assert code == 0 and data["name"] == "t1" and 0.5 < data["duration_s"] < 1.5 and data["stop_alive"] == []
    assert data["ai"]["batches"] > 0 and len(data["cameras"]) == 4 and data["cameras"][0]["fps_mean"] > 5
    assert "resources" in data and "series" in data and data["clock"]["name"] == "perf_counter"


def test_build_rig_passes_one_clock_to_cameras_lidar_and_rig(monkeypatch):
    import argparse

    import autopark.lidar.rplidar_c1 as rp
    seen = {}

    def fake_open(port, **kwargs):
        seen.update(kwargs)
        return FakeLidar()

    monkeypatch.setattr(rp.RplidarC1Source, "open", staticmethod(fake_open))
    p = argparse.ArgumentParser()
    bench.add_rig_args(p)
    args = p.parse_args(["--index", "0", "1", "--no-ai", "--lidar", "COM9"])
    rig = bench.build_rig(args)
    rig.lidar.open_source()
    assert rig.clock is RIG_CLOCK and rig.cams.clock is RIG_CLOCK and seen["clock"] is RIG_CLOCK
