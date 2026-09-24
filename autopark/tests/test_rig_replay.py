"""Ghi và phát lại phiên bàn thử bằng nguồn giả (không phần cứng): ghi → phát lại → cùng khung, cùng stamp (tương đối),
cùng sự kiện khung hỏng, cùng vòng LiDAR; bench --record / --replay ra rig.json; giao diện offscreen với "Ghi phiên" và
--replay; hết bản ghi, dừng giữa chừng, hàng đợi đầy và lỗi ghi đều được báo rõ.

Bổ sung 24/09 sau xem xét: một bộ ghi chưa xong tại một thời điểm (bộ ghi đang ghi nốt không bị bỏ quên khi thoát), không
mất khung đầu lúc bắt đầu ghi, dòng CSV bị cắt/tệp ảnh hỏng không làm phát lại kẹt, bench kiểm tham số ghi trước khi mở
thiết bị và trả mã 1 khi phát lại không tới hết bản ghi, lỗi LiDAR và ngoại lệ thường của camera được ghi và phát lại, CSV
được flush trong lúc ghi."""
import csv
import json
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.lidar.recording import read_recording  # noqa: E402
from autopark.rig import bench  # noqa: E402
from autopark.rig.core import Rig, RigConfig  # noqa: E402
from autopark.rig.recording import CameraTap, RigRecorder, event_kind  # noqa: E402
from autopark.rig.replay import END_MESSAGE, ReplayError, ReplaySession, StreamItem, load_lidar  # noqa: E402
from autopark.video.multicam import CameraSpec, MultiCameraManager  # noqa: E402
from autopark.video.sources import FrameReadError, _frame  # noqa: E402
from tests.rig_fakes import FakeCamera, FakeLidar, FakeSegmenter, fake_manager  # noqa: E402

PERIOD = 0.03


def rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_image(path):
    return cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)


def record_fake_session(folder, *, seconds=1.0, image_format="png", ports=(1, 2, 3), lidar=True, broken=(), **cam_kw):
    """Rig thật với camera/LiDAR giả (camera có vân, giữ mọi khung đã trả; khung cũ mỗi 11 lần, khung cắt mỗi 7 lần)."""
    kw = {"textured": True, "keep": True, "trunc_every": 7, "dup_every": 11, **cam_kw}
    cams = fake_manager(ports=ports, period=PERIOD, broken=broken, **kw)
    rig = Rig(cams, RigConfig(ai=False), open_lidar=(lambda: FakeLidar(period=0.1)) if lidar else None)
    rig.start()
    try:
        time.sleep(0.3)
        rig.start_recording(folder, image_format=image_format, notes={"test": "ghi phát lại"})
        time.sleep(seconds)
        status = rig.stop_recording(wait=True)
        originals = {p: list(w.source.kept) for p, w in cams.workers.items() if w.source is not None}
    finally:
        alive = rig.stop()
    assert alive == []
    return status, originals


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    folder = tmp_path_factory.mktemp("ghi") / "phiên thử"          # đường dẫn tiếng Việt: cv2.imwrite sẽ hỏng ở đây
    status, originals = record_fake_session(folder, seconds=1.0, image_format="png")
    return folder, status, originals


def replay_through_rig(folder, rerecord, speed=1.0):
    """Phát lại qua Rig đầy đủ, đồng thời ghi lại chính phiên phát lại (PNG) để so với bản gốc."""
    session = ReplaySession(folder, speed=speed)
    assert 0.5 < session.duration_s < 5.0, session.duration_s        # mọi stamp cùng một đồng hồ (không chờ hàng giờ)
    cams = MultiCameraManager(session.camera_specs(), ring=3, open_source=session.open_camera)
    rig = Rig(cams, RigConfig(ai=False), open_lidar=session.open_lidar if session.has_lidar else None, replay=session)
    rig.start(begin_replay=False)
    try:
        rig.start_recording(rerecord, image_format="png")
        t0 = time.perf_counter()
        session.begin()
        deadline = t0 + session.duration_s / speed + 5.0
        while not session.finished and time.perf_counter() < deadline:
            time.sleep(0.01)
        wall = time.perf_counter() - t0
        time.sleep(0.15)                                               # khung cuối đi hết đường từ nguồn vào bộ đếm
        cam_stats = {c["port"]: c for c in cams.camera_stats()}
        lidar_stats = rig.lidar.stats(rig.clock())
        rig.stop_recording(wait=True)
        status = session.status()
    finally:
        alive = rig.stop()
    return session, status, cam_stats, lidar_stats, wall, alive


# ------------------------------------------------------------------------------------------------------------ ghi

def test_recording_holds_every_good_frame_the_damaged_frame_events_and_the_lidar_revolutions(recorded):
    folder, status, originals = recorded
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["format"] == "autopark.rig_recording" and meta["format_version"] == 1 and meta["status"] == "xong"
    assert meta["ports"] == [1, 2, 3] and [c["port"] for c in meta["cameras"]] == [1, 2, 3]
    assert meta["clock"]["name"] == "perf_counter" and meta["notes"] == {"test": "ghi phát lại"}
    assert meta["image"]["format"] == "png" and "git_commit" in meta and meta["created_utc"]
    assert meta["config"]["max_wait_s"] == pytest.approx(0.06) and meta["policy"]["max_skew_ms"] == 60.0
    assert status["state"] == "xong" and status["error"] is None and status["dropped_total"] == 0
    for port in (1, 2, 3):
        frames = rows(folder / f"cam_p{port}" / "frames.csv")
        assert len(frames) == status["frames"][port] > 15
        assert [int(r["seq"]) for r in frames] == list(range(1, len(frames) + 1))      # không khung nào bị bỏ
        # đúng dãy khung tốt nguồn đã trả trong cửa sổ ghi — không thiếu khung nào ở giữa — và đúng từng pixel (PNG)
        t_rec = [float(r["t_s"]) for r in frames]
        window = [(t, img) for t, img in originals[port] if t_rec[0] - 1e-6 <= t <= t_rec[-1] + 1e-6]
        assert len(window) == len(frames)
        for r, (t, img) in zip(frames, window):
            assert float(r["t_s"]) == pytest.approx(t, abs=1e-8)
            assert (int(r["width"]), int(r["height"])) == (64, 48)
            assert np.array_equal(read_image(folder / f"cam_p{port}" / r["file"]), img)
        # sự kiện khung hỏng: đúng loại, và nằm đúng giữa khung tốt trước (after_seq) và khung tốt sau nó
        events = rows(folder / f"cam_p{port}" / "events.csv")
        kinds = {e["kind"] for e in events}
        assert kinds == {"duplicate", "truncated"}, kinds
        for e in events:
            k = int(e["after_seq"])
            assert k == 0 or float(e["t_s"]) >= t_rec[k - 1]
            assert k == len(t_rec) or float(e["t_s"]) <= t_rec[k]
        assert status["events"][port] == {kind: sum(e["kind"] == kind for e in events) for kind in kinds}
    lidar = meta["lidar"]
    assert lidar["parts"] == ["lidar/part_0000.npz"] and lidar["scans"] == status["lidar_scans"] >= 7
    part = read_recording(folder / "lidar" / "part_0000.npz")
    assert len(part) == lidar["scans"] and part.meta["source_id"] == "fake_lidar"
    assert meta["t_start_s"] - 0.2 < part.t[0] and part.t[-1] < meta["t_stop_s"]     # stamp trên đồng hồ bàn thử
    assert (part.t_first < part.t).all() and part.quality.max() > 0                   # đầu vòng, chất lượng từng tia


def test_recorder_refuses_a_folder_that_already_holds_data(tmp_path):
    (tmp_path / "cũ.txt").write_text("x", encoding="utf-8")
    rec = RigRecorder(tmp_path, ports=[1])
    with pytest.raises(FileExistsError):
        rec.start()
    with pytest.raises(ReplayError):
        ReplaySession(tmp_path)                                        # không có meta.json: không phải bản ghi


def test_event_kinds_follow_the_camera_worker_classification():
    assert event_kind("cam_p1: driver returned the previous frame again") == "duplicate"
    assert event_kind("cam_p1: truncated frame (24 of 48 rows filled by the decoder)") == "truncated"
    assert event_kind("cam_p1: torn frame (1 block rows filled mid-image by the decoder)") == "torn"
    assert event_kind("cam_p1: read failed (3 failures so far)") == "read_failed"


# ------------------------------------------------------------------------------------------------------------ phát lại

def test_replay_through_the_full_rig_reproduces_frames_stamps_events_counters_and_scans(recorded, tmp_path):
    folder, status, _ = recorded
    again = tmp_path / "ghi lại"
    session, st, cam_stats, lidar_stats, wall, alive = replay_through_rig(folder, again)
    assert alive == [] and st["finished"] and st["begun"]
    assert session.duration_s * 0.9 < wall < session.duration_s + 1.0                 # chạy theo thời gian thật
    for port in (1, 2, 3):
        c = st["cameras"][port]
        a_frames = rows(folder / f"cam_p{port}" / "frames.csv")
        a_events = rows(folder / f"cam_p{port}" / "events.csv")
        assert c["delivered"] == len(a_frames) and c["errors_replayed"] == len(a_events) and c["decode_errors"] == 0
        assert c["late_ms"]["median"] < 15.0, c["late_ms"]                           # khung ra đúng lịch
        # bộ đếm của MultiCameraManager ra như lúc ghi: sự kiện được ném lại đúng loại
        assert cam_stats[port]["frames"] == len(a_frames)
        assert cam_stats[port]["duplicates"] == sum(e["kind"] == "duplicate" for e in a_events)
        assert cam_stats[port]["truncated"] == sum(e["kind"] == "truncated" for e in a_events)
        assert cam_stats[port]["read_failures"] == 0
        # ghi lại chính phiên phát lại: cùng ảnh từng pixel, stamp tương đối trùng, sự kiện trùng
        b_frames = rows(again / f"cam_p{port}" / "frames.csv")
        b_events = rows(again / f"cam_p{port}" / "events.csv")
        assert len(b_frames) == len(a_frames) and len(b_events) == len(a_events)
        for a, b in zip(a_frames, b_frames):
            assert (float(b["t_s"]) - session.origin) == pytest.approx(float(a["t_s"]) - session.t_ref, abs=1e-6)
            assert np.array_equal(read_image(again / f"cam_p{port}" / b["file"]), read_image(folder / f"cam_p{port}" / a["file"]))
        for a, b in zip(a_events, b_events):
            assert (a["kind"], a["after_seq"], a["message"]) == (b["kind"], b["after_seq"], b["message"])
            assert (float(b["t_s"]) - session.origin) == pytest.approx(float(a["t_s"]) - session.t_ref, abs=1e-6)
    # LiDAR: cùng vòng, cùng tia, cùng chất lượng, cùng stamp đầu/cuối vòng (tương đối)
    rec_a, _ = load_lidar(folder)
    rec_b, _ = load_lidar(again)
    assert lidar_stats["scans"] == len(rec_a) == len(rec_b) == st["lidar"]["delivered"] and lidar_stats["errors"] == 0
    for key in ("n_beams", "angles", "quality"):
        assert np.array_equal(getattr(rec_a, key), getattr(rec_b, key)), key
    assert np.array_equal(rec_a.ranges, rec_b.ranges, equal_nan=True)
    np.testing.assert_allclose(rec_b.t - session.origin, rec_a.t - session.t_ref, atol=1e-6)
    np.testing.assert_allclose(rec_b.t_first - session.origin, rec_a.t_first - session.t_ref, atol=1e-6)
    meta_b = json.loads((again / "meta.json").read_text(encoding="utf-8"))
    assert meta_b["replay_of"]["folder"] == str(folder) and meta_b["status"] == "xong"


class SlowFirstSegmenter(FakeSegmenter):
    """Lô đầu chậm như khởi tạo CUDA/cuDNN thật (1,46 s trên máy bàn, phiên o04 ngày 24/09)."""

    def infer(self, images, out_size=None):
        if not self.batch_sizes:
            time.sleep(0.5)
        return super().infer(images, out_size)


def test_replay_starts_after_the_ai_warm_up_batch_so_the_first_frames_reach_a_set(recorded):
    folder, _, _ = recorded
    session = ReplaySession(folder)
    cams = MultiCameraManager(session.camera_specs(), ring=3, open_source=session.open_camera)
    rig = Rig(cams, RigConfig(checkpoint="m.pt", display_width=32), make_segmenter=lambda p: SlowFirstSegmenter(p),
              replay=session)
    assert rig.ai.warm_up == (3, rig.cfg.height, rig.cfg.width)
    rig.start()                                            # phát lại tự bắt đầu khi AI nạp xong VÀ làm nóng xong
    try:
        deadline = time.perf_counter() + session.duration_s + 5.0
        while not session.finished and time.perf_counter() < deadline:
            time.sleep(0.01)
        time.sleep(0.2)
        seg, skipped = rig.ai.segmenter, rig.cams.stats()["frames_skipped"]
    finally:
        assert rig.stop() == []
    # làm nóng MỌI cỡ lô 3, 2, 1 trước bộ ảnh đầu: lô thiếu camera sau này không phải trả lại phần khởi tạo
    assert session.finished and seg.batch_sizes[:3] == [3, 2, 1] and rig.ai.first_batch_ms == pytest.approx(3.5)
    assert rig.ai.stats(rig.clock())["warm_up_ms"] == [3.5, 3.5, 3.5]
    # đo khi viết test (24/09): làm nóng → 27 lô, 0 khung không vào bộ nào; bỏ làm nóng → lô đầu 0,5 s nuốt đầu bản
    # ghi: 14 lô, 11 khung một cổng không vào bộ nào
    assert max(skipped.values()) <= 3, skipped
    assert rig.ai.batches >= len(rows(folder / "cam_p1" / "frames.csv")) - 8


def test_jpeg_recording_replays_close_to_the_original_pixels_at_double_speed_and_blocks_at_the_end(tmp_path):
    folder = tmp_path / "jpg"
    status, originals = record_fake_session(folder, seconds=0.6, image_format="jpg", ports=(1,), lidar=False)
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["image"] == {"format": "jpg", "jpeg_quality": 95, "png_compression": None} and meta["lidar"] is None
    files = sorted((folder / "cam_p1").glob("*.jpg"))
    assert len(files) == status["frames"][1] > 8 and files[0].read_bytes()[:2] == b"\xff\xd8"
    session = ReplaySession(folder, speed=2.0)
    src = session.open_camera(CameraSpec(port=1, index=0))
    session.begin()
    t0 = time.perf_counter()
    frames, errors = [], []
    while not src.done:
        try:
            frames.append(src.read())
        except FrameReadError as exc:
            errors.append(exc)
    wall = time.perf_counter() - t0
    assert len(frames) == status["frames"][1] and len(errors) == sum(status["events"][1].values())
    assert all(e.t is not None for e in errors)                                     # lỗi mang thời điểm như nguồn thật
    assert session.duration_s / 2 * 0.9 < wall < session.duration_s / 2 + 0.5        # nhanh gấp đôi
    stamps = np.array([t for t, _ in originals[1]])
    diffs = []
    for f in frames:
        t_rec = session.t_ref + (f.meta.stamp.t - session.origin) * 2.0              # stamp đổi gốc, khoảng cách chia 2
        k = int(np.argmin(np.abs(stamps - t_rec)))
        assert abs(stamps[k] - t_rec) < 1e-6
        original = originals[1][k][1]
        d = np.abs(f.image.astype(int) - original.astype(int))
        diffs.append(d.mean())
        assert abs(int(f.image[3, 3, 0]) - int(original[3, 3, 0])) <= 2              # ô nhận dạng khung giữ đúng
        assert d.max() <= 40
    assert max(diffs) < 3.0 and max(diffs) > 0                                      # JPEG: gần đúng, không trùng khít
    # hết bản ghi: read() chặn (không trả None, không ném liên tục) tới khi dừng, rồi báo rõ
    box = {}

    def reader():
        try:
            src.read()
        except FrameReadError as exc:
            box["message"] = str(exc)

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    th.join(0.3)
    assert th.is_alive() and session.finished
    session.stop()
    th.join(1.0)
    assert not th.is_alive() and END_MESSAGE in box["message"]


def test_end_of_recording_leaves_cameras_stale_and_the_rig_stops_cleanly(recorded):
    folder, _, _ = recorded
    session = ReplaySession(folder, ports=[1, 2])
    assert session.duration_s < 5.0
    cams = MultiCameraManager(session.camera_specs(), ring=3, open_source=session.open_camera)
    rig = Rig(cams, RigConfig(ai=False), replay=session)
    assert [s.port for s in cams.specs] == [1, 2] and rig.lidar is None
    rig.start()                                                        # không có AI: phát ngay
    try:
        deadline = time.perf_counter() + session.duration_s + 3.0
        while not session.finished and time.perf_counter() < deadline:
            time.sleep(0.02)
        time.sleep(0.6)                                                # > STALE_AFTER_S sau khung cuối
        snap = rig.snapshot()
        assert snap["replay"]["finished"] and snap["replay"]["position_s"] == snap["replay"]["duration_s"]
        assert all(c["stale"] and c["frames"] > 15 and c["read_failures"] == 0 for c in snap["cameras"]["cameras"])
        assert cams.latest_set(0.06, max_wait_s=0.06) is None          # hết khung mới: không còn bộ nào
        t = time.perf_counter()
    finally:
        alive = rig.stop()
    assert alive == [] and time.perf_counter() - t < 1.5


def test_stopping_mid_replay_wakes_sources_waiting_on_the_schedule(recorded):
    folder, _, _ = recorded
    session = ReplaySession(folder, speed=0.5)                         # chậm: bản ghi 1 s kéo dài 2 s
    cams = MultiCameraManager(session.camera_specs(), ring=3, open_source=session.open_camera)
    cams.start()
    session.begin()
    time.sleep(0.5)
    t = time.perf_counter()
    alive = cams.stop(2.0)                                             # chỉ dừng manager, KHÔNG gọi session.stop()
    assert alive == [] and time.perf_counter() - t < 0.5
    assert not session.finished and 0 < sum(c["frames"] for c in cams.camera_stats())
    session2 = ReplaySession(folder, speed=0.2)
    rig = Rig(MultiCameraManager(session2.camera_specs(), ring=3, open_source=session2.open_camera), RigConfig(ai=False),
              open_lidar=session2.open_lidar, replay=session2)
    rig.start()
    time.sleep(0.3)
    t = time.perf_counter()
    assert rig.stop() == [] and time.perf_counter() - t < 1.5


def test_a_camera_that_failed_to_open_while_recording_fails_to_open_on_replay(tmp_path):
    folder = tmp_path / "hỏng"
    status, _ = record_fake_session(folder, seconds=0.4, ports=(1, 2), lidar=False, broken=(2,))
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    at_stop = {c["port"]: c for c in meta["cameras_at_stop"]}
    assert status["frames"][2] == 0 and "Cannot open camera" in at_stop[2]["open_error"]
    session = ReplaySession(folder)
    cams = MultiCameraManager(session.camera_specs(), ring=3, open_source=session.open_camera)
    rig = Rig(cams, RigConfig(ai=False), replay=session)
    rig.start()
    try:
        time.sleep(0.3)
        stats = {c["port"]: c for c in cams.camera_stats()}
    finally:
        rig.stop()
    assert "lúc ghi camera cổng 2 không mở được" in stats[2]["open_error"] and stats[1]["open_error"] is None
    assert stats[1]["frames"] > 0


# ------------------------------------------------------------------------------------------------------------ giới hạn

class SlowDisk(RigRecorder):
    def _write_bytes(self, path, data):
        time.sleep(0.03)
        super()._write_bytes(path, data)


class FullDisk(RigRecorder):
    def _write_bytes(self, path, data):
        raise OSError(28, "No space left on device")


def fake_frame(port, t, value):
    image = np.full((48, 64, 3), value, np.uint8)
    return _frame(f"cam_p{port}", t, "x", image)


def test_full_queue_drops_frames_counts_and_logs_them_and_replay_skips_the_gap(tmp_path):
    rec = SlowDisk(tmp_path / "chậm", ports=[1], image_format="png", max_pending_mb=0.02,       # ≈ 2 khung 64×48
                   clock=lambda: 1.0).start()                        # đồng hồ giả cùng hệ với stamp khung dưới đây
    for k in range(30):
        rec.add_frame(1, fake_frame(1, 1.0 + 0.01 * k, k))
    rec.add_event(1, "truncated", 1.305, "cam_p1: truncated frame (24 of 48 rows filled by the decoder)")
    st = rec.stop(wait=True, timeout=10.0)
    assert st["state"] == "xong" and st["error"] is None
    assert st["dropped"][1] > 10 and st["frames"][1] + st["dropped"][1] == 30 and st["pending_frames"] == 0
    events = rows(tmp_path / "chậm" / "cam_p1" / "events.csv")
    dropped = [e for e in events if e["kind"] == "record_dropped"]
    assert len(dropped) == st["dropped"][1] and "hàng đợi ghi đầy" in dropped[0]["message"]
    meta = json.loads((tmp_path / "chậm" / "meta.json").read_text(encoding="utf-8"))
    assert meta["per_port"]["1"]["frames_dropped"] == st["dropped"][1]
    session = ReplaySession(tmp_path / "chậm")
    kinds = [it.kind for it in session.streams[1]]
    assert kinds.count("frame") == st["frames"][1] and kinds.count("truncated") == 1 and "record_dropped" not in kinds
    assert session.status()["missing_in_recording"] == {1: st["dropped"][1]}
    assert kinds[-1] == "truncated"                                    # sự kiện sau khung cuối vẫn đúng chỗ


def test_replay_refuses_a_recording_whose_sources_used_different_clocks(tmp_path):
    rec = RigRecorder(tmp_path / "hai đồng hồ", ports=[1, 2], image_format="png", clock=lambda: 5000.0).start()
    rec.add_frame(1, fake_frame(1, 5000.1, 1))                        # đồng hồ bàn thử
    rec.add_frame(2, fake_frame(2, 0.1, 2))                           # giờ phiên của nguồn, quên cộng t0
    assert rec.stop(wait=True, timeout=5.0)["state"] == "xong"
    with pytest.raises(ReplayError, match="ngoài cửa sổ ghi"):
        ReplaySession(tmp_path / "hai đồng hồ")


def test_disk_error_is_surfaced_in_status_meta_rig_snapshot_metrics_and_bench_exit_code(tmp_path, monkeypatch, capsys):
    rec = FullDisk(tmp_path / "đầy", ports=[1, 2]).start()
    rec.add_frame(1, fake_frame(1, 1.0, 10))
    deadline = time.perf_counter() + 3.0
    while rec.error is None and time.perf_counter() < deadline:
        time.sleep(0.01)
    assert rec.state == "LỖI" and "No space left on device" in rec.error
    rec.add_frame(2, fake_frame(2, 1.01, 10))                          # sau lỗi: bỏ và đếm, không âm thầm
    st = rec.stop(wait=True, timeout=5.0)
    assert st["state"] == "LỖI" and st["dropped"] == {1: 1, 2: 1} and st["frames_total"] == 0
    meta = json.loads((tmp_path / "đầy" / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "lỗi" and "No space left on device" in meta["error"]

    from autopark.ui.rig_app import format_metrics
    monkeypatch.setattr(RigRecorder, "_write_bytes", FullDisk._write_bytes)

    def fake_build(args):
        return Rig(fake_manager(ports=(1, 2), period=PERIOD), RigConfig(ai=False))
    monkeypatch.setattr(bench, "build_rig", fake_build)
    code = bench.main(["--name", "day", "--seconds", "0.6", "--warmup", "0.1", "--out", str(tmp_path / "out"),
                       "--record", str(tmp_path / "bench_day")])
    data = json.loads((tmp_path / "out" / "day.rig.json").read_text(encoding="utf-8"))
    assert code == 1 and data["recording"]["state"] == "LỖI" and "No space left" in data["recording"]["error"]
    assert "không trọn" in capsys.readouterr().out
    snap = {"t_s": 1.0, "cameras": {"cameras": [], "sets_built": 0, "sets_rejected_skew": 0, "sets_partial": 0,
                                    "sets_blocked_not_new": 0, "skew_ms": {"median": None, "p95": None, "max": None},
                                    "skew_window": "x"},
            "lidar": None, "ai": None, "resources": None, "recording": data["recording"]}
    text = format_metrics(snap, 0.5)
    assert "GHI PHIÊN" in text and "LỖI GHI: " in text and "No space left" in text


def test_camera_tap_passes_frames_and_errors_through_and_forwards_attributes():
    class Source:
        check_truncation = True

        def __init__(self):
            self.n = 0

        def read(self):
            self.n += 1
            if self.n == 2:
                raise FrameReadError("cam_p1: torn frame (1 block rows filled mid-image by the decoder)", 5.0)
            return fake_frame(1, float(self.n), 1)

        def close(self):
            self.closed = True

    seen = []

    class Sink:
        def add_frame(self, port, frame):
            seen.append(("frame", port, frame.meta.stamp.t))

        def add_event(self, port, kind, t, message):
            seen.append((kind, port, t))

    sink = [None]
    tap = CameraTap(Source(), 1, lambda: sink[0])
    assert tap.read().meta.stamp.t == 1.0 and seen == []                # không ghi: chỉ chuyển qua
    sink[0] = Sink()
    with pytest.raises(FrameReadError):
        tap.read()
    tap.read()
    assert seen == [("torn", 1, 5.0), ("frame", 1, 3.0)] and tap.check_truncation is True
    tap.close()
    assert tap.inner.closed


# ------------------------------------------------------------------------------------------------------------ bench

def test_bench_record_then_replay_writes_rig_json_with_the_recorded_counts(tmp_path, monkeypatch):
    real_build = bench.build_rig

    def fake_build(args):
        if args.replay is not None:
            return real_build(args)
        cams = fake_manager(ports=(1, 2), period=PERIOD, textured=True, trunc_every=5)
        return Rig(cams, RigConfig(ai=False, max_wait_s=args.max_wait_ms / 1000.0),
                   open_lidar=lambda: FakeLidar(period=0.1))
    monkeypatch.setattr(bench, "build_rig", fake_build)
    folder = tmp_path / "bench ghi"
    out = tmp_path / "out"
    code = bench.main(["--name", "g1", "--seconds", "1.0", "--warmup", "0.3", "--out", str(out), "--record", str(folder)])
    live = json.loads((out / "g1.rig.json").read_text(encoding="utf-8"))
    assert code == 0 and live["recording"]["state"] == "xong" and live["recording"]["dropped_total"] == 0
    recorded = {int(p): n for p, n in live["recording"]["frames"].items()}
    for c in live["cameras"]:                                          # ghi đúng cửa sổ đo (± vài khung ở hai mép)
        assert abs(c["frames"] - recorded[c["port"]]) <= 3
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "xong" and meta["notes"]["name"] == "g1"

    # phát lại bằng build_rig thật: không mở thiết bị nào; AI là bộ phân đoạn giả
    assert ReplaySession(folder).duration_s < 5.0                      # camera và LiDAR cùng một đồng hồ
    monkeypatch.setattr(bench, "segmenter_factory", lambda args: (lambda p: FakeSegmenter(p), "m.pt"))
    code = bench.main(["--replay", str(folder), "--name", "p1", "--out", str(out), "--max-wait-ms", "0"])
    data = json.loads((out / "p1.rig.json").read_text(encoding="utf-8"))
    assert code == 0 and data["replay"]["finished"] and data["warmup_s"] == 0.0
    assert data["config"]["notes"]["replay"] == str(folder) and data["policy"]["max_wait_ms"] is None
    for c in data["cameras"]:                                          # phiên đo phủ trọn bản ghi
        assert c["frames"] == recorded[c["port"]] and c["truncated"] == meta["per_port"][str(c["port"])]["events"]["truncated"]
        assert c["read_failures"] == 0 and c["open_error"] is None
    assert data["lidar"]["scans"] == meta["lidar"]["scans"] and data["lidar"]["vs_set"]["last_minus_anchor_ms"]["n"] > 0
    assert data["ai"]["batches"] > 5 and data["ai"]["load_error"] is None
    assert abs(data["duration_s"] - data["replay"]["duration_s"]) < 1.0
    assert all(v["late_ms"]["median"] < 15.0 for v in data["replay"]["cameras"].values())
    # --ports chọn cổng trong bản ghi; --lidar cùng --replay bị từ chối
    import argparse
    p = argparse.ArgumentParser()
    bench.add_rig_args(p)
    rig = real_build(p.parse_args(["--replay", str(folder), "--ports", "2", "--no-ai"]))
    assert [s.port for s in rig.cams.specs] == [2] and rig.lidar is not None
    assert rig.cfg.width == meta["camera_mode"]["width"] == 1280        # mode lấy từ bản ghi, không từ --width (640)
    with pytest.raises(ValueError):
        real_build(p.parse_args(["--replay", str(folder), "--lidar", "COM4", "--no-ai"]))


# ------------------------------------------------------------------------------------------------------------ giao diện

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def test_gui_record_button_writes_a_session_that_the_gui_replays_to_the_end(qapp, tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from autopark.ui import rig_app

    cams = fake_manager(ports=(1, 2), period=PERIOD, textured=True)
    rig = Rig(cams, RigConfig(checkpoint="m.pt", display_width=32), make_segmenter=lambda p: FakeSegmenter(p),
              open_lidar=lambda: FakeLidar(period=0.1))
    window = rig_app.RigWindow(rig, checkpoints=[], snapshot_dir=tmp_path / "chụp", record_root=tmp_path / "bản ghi")
    try:
        pump(qapp, 0.4)
        window.btn_record.setChecked(True)
        assert rig.recorder is not None and window.btn_record.text() == "Dừng ghi"
        pump(qapp, 0.8)
        window.update_metrics()
        assert "GHI PHIÊN" in window.metrics.text() and "đang ghi" in window.metrics.text()
        window.btn_record.setChecked(False)
        assert rig.recorder is None and window.message.startswith("dừng ghi")
        assert rig.last_recorder.finished.wait(5.0)
        window.update_metrics()
        assert window.message.startswith("đã ghi xong") and "bỏ 0" in window.message
    finally:
        window.close()
    [folder] = list((tmp_path / "bản ghi").iterdir())
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "xong" and meta["notes"] == {"from": "ui.rig_app"} and meta["per_port"]["1"]["frames_written"] > 10

    monkeypatch.setattr(bench, "segmenter_factory", lambda args: (lambda p: FakeSegmenter(p), "m.pt"))
    monkeypatch.setattr(rig_app, "checkpoint_choices", lambda runs: [])
    window = rig_app.build_window(["--replay", str(folder), "--display-width", "32", "--snapshots", str(tmp_path / "chụp2")])
    rig = window.rig
    try:
        assert "PHÁT LẠI" in window.windowTitle() and rig.replay is not None and rig.replay.duration_s < 5.0
        pump(qapp, 0.6)
        window.update_metrics()
        assert window.tiles[1].pixmap is not None and "BLOCKED 50%" in window.tiles[1].detail
        assert "PHÁT LẠI ×1,00  đang phát" in window.metrics.text()
        snap_meta = json.loads((window.snapshot() / "meta.json").read_text(encoding="utf-8"))
        assert snap_meta["replay"]["folder"] == str(folder)            # ảnh chụp từ phát lại được đánh dấu
        deadline = time.monotonic() + rig.replay.duration_s + 3.0
        while not rig.replay.finished and time.monotonic() < deadline:
            pump(qapp, 0.05)
        pump(qapp, 0.2)
        window.tick()
        window.update_metrics()
        for port in (1, 2):
            assert window.tiles[port].detail.startswith("HẾT BẢN GHI phát lại · ") and window.tiles[port].alert
        assert "HẾT BẢN GHI" in window.metrics.text()
    finally:
        window.close()
    assert rig.stop_alive == [] and not any(w.is_alive() for w in rig.cams.workers.values())


# ------------------------------------------------------------------------------------ bổ sung sau xem xét (24/09/2026)

def slow_writes(monkeypatch, seconds):
    """Đĩa chậm giả cho MỌI RigRecorder (kể cả bộ ghi do Rig tạo): mỗi tệp ảnh chờ thêm `seconds`."""
    real = RigRecorder._write_bytes

    def slow(self, path, data):
        time.sleep(seconds)
        real(self, path, data)
    monkeypatch.setattr(RigRecorder, "_write_bytes", slow)


def test_a_new_recording_is_refused_while_the_previous_one_drains_and_rig_stop_waits_for_it(tmp_path, monkeypatch):
    slow_writes(monkeypatch, 0.05)                                     # ≈ 20 tệp/s, camera 2 × 50 khung/s
    rig = Rig(fake_manager(ports=(1, 2), period=0.02, textured=True), RigConfig(ai=False),
              open_lidar=lambda: FakeLidar(period=0.1))
    rig.start()
    try:
        first = rig.start_recording(tmp_path / "a", image_format="png")
        time.sleep(0.4)
        rig.stop_recording(wait=False)                                 # như nút "Dừng ghi"
        assert first.state == "đang ghi nốt" and first.status()["pending_frames"] > 5
        with pytest.raises(RuntimeError, match="còn đang ghi nốt"):
            rig.start_recording(tmp_path / "b")                        # như bấm "Ghi phiên" lại ngay
        assert not (tmp_path / "b").exists() and rig.recorder is None and rig.last_recorder is first
    finally:
        alive = rig.stop()                                             # như đóng cửa sổ: phải chờ bản ghi đầu
    assert alive == [] and first.finished.is_set() and first.state == "xong"
    meta = json.loads((tmp_path / "a" / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "xong" and meta["lidar"]["parts"] and meta["per_port"]["1"]["frames_dropped"] == 0
    assert meta["per_port"]["1"]["frames_written"] == len(rows(tmp_path / "a" / "cam_p1" / "frames.csv"))


def test_gui_greys_out_record_while_the_previous_recording_drains_and_closing_waits_for_it(qapp, tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from autopark.ui import rig_app

    slow_writes(monkeypatch, 0.05)
    rig = Rig(fake_manager(ports=(1, 2), period=0.02, textured=True), RigConfig(ai=False))
    window = rig_app.RigWindow(rig, checkpoints=[], snapshot_dir=tmp_path / "chụp", record_root=tmp_path / "bản ghi",
                               record_options={"image_format": "png"})
    try:
        pump(qapp, 0.2)
        window.btn_record.setChecked(True)
        pump(qapp, 0.4)
        first = rig.last_recorder
        window.btn_record.setChecked(False)
        assert first.state == "đang ghi nốt" and not window.btn_record.isEnabled()
        window.btn_record.setChecked(True)                             # bấm lại (bằng mã) khi nút đang mờ
        assert window.message.startswith("LỖI: không bắt đầu ghi được") and "ghi nốt" in window.message
        assert not window.btn_record.isChecked() and rig.recorder is None and rig.last_recorder is first
        assert len(list((tmp_path / "bản ghi").iterdir())) == 1
    finally:
        window.close()                                                 # closeEvent → rig.stop() chờ ghi nốt
    assert rig.stop_alive == [] and first.finished.is_set()
    meta = json.loads((first.folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "xong"


def test_every_good_frame_stamped_after_t_start_is_recorded_even_when_the_first_meta_json_is_slow(tmp_path, monkeypatch):
    from autopark.rig import recording
    real = recording.write_json_atomic

    def slow_meta(path, value):                                        # Windows: meta.json đầu đo được 3–80 ms
        if value.get("status") == "đang ghi":
            time.sleep(0.05)
        real(path, value)
    monkeypatch.setattr(recording, "write_json_atomic", slow_meta)
    cams = fake_manager(ports=(1, 2, 3, 4), period=0.005, keep=True)
    rig = Rig(cams, RigConfig(ai=False))
    rig.start()
    try:
        time.sleep(0.2)
        rec = rig.start_recording(tmp_path / "đầu", image_format="png")
        time.sleep(0.3)
        st = rig.stop_recording(wait=True)
        kept = {p: [t for t, _ in w.source.kept] for p, w in cams.workers.items()}
    finally:
        assert rig.stop() == []
    assert st["state"] == "xong" and st["dropped_total"] == 0
    for port, stamps in kept.items():
        t_rec = np.array([float(r["t_s"]) for r in rows(tmp_path / "đầu" / f"cam_p{port}" / "frames.csv")])
        expected = [t for t in stamps if rec.t_start <= t <= t_rec[-1]]
        missing = [t for t in expected if np.min(np.abs(t_rec - t)) > 1e-7]
        assert len(expected) > 20 and missing == [], (port, len(missing), len(expected))


def cut_last_row(path, tail: str) -> None:
    """Thay dòng cuối của một CSV bằng `tail` (không xuống dòng): như tiến trình/máy chết giữa lúc ghi dòng đó."""
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\r\n".join(lines[:-1]) + "\r\n" + tail, encoding="utf-8", newline="")


def test_cut_csv_rows_are_skipped_and_counted_and_the_replay_still_reaches_the_end(tmp_path):
    folder = tmp_path / "bị cắt"
    rec = RigRecorder(folder, ports=[1, 2, 3], image_format="png", clock=lambda: 1.0).start()
    for k in range(6):
        for port in (1, 2, 3):
            rec.add_frame(port, fake_frame(port, 1.0 + 0.02 * k, 10 * k + port))
    assert rec.stop(wait=True, timeout=5.0)["frames_total"] == 18
    cut_last_row(folder / "cam_p1" / "frames.csv", "6,1.100000000")                # cắt ngay sau t_s
    cut_last_row(folder / "cam_p2" / "frames.csv", "6,1.100000000,64" + "\x00" * 300)  # cắt, đuôi byte NUL
    with open(folder / "cam_p3" / "frames.csv", "a", encoding="utf-8", newline="") as handle:
        handle.write("\x00" * 64)                                     # dòng toàn NUL sau một dòng nguyên vẹn
    session = ReplaySession(folder)
    assert session.status()["bad_rows"] == {1: 1, 2: 1, 3: 1}
    assert [sum(it.kind == "frame" for it in session.streams[p]) for p in (1, 2, 3)] == [5, 5, 6]
    cams = MultiCameraManager(session.camera_specs(), ring=3, open_source=session.open_camera)
    cams.start()
    try:
        session.begin()
        deadline = time.perf_counter() + session.duration_s + 2.0
        while not session.finished and time.perf_counter() < deadline:
            time.sleep(0.01)
        time.sleep(0.1)
        st = session.status()
        stats = {c["port"]: c for c in cams.camera_stats()}
    finally:
        session.stop()
        assert cams.stop(2.0) == []
    assert st["finished"]
    assert {p: c["delivered"] for p, c in st["cameras"].items()} == {1: 5, 2: 5, 3: 6}
    assert all(stats[p]["read_failures"] == 0 and stats[p]["frames"] == st["cameras"][p]["delivered"] for p in (1, 2, 3))


def test_a_frame_whose_file_cannot_be_read_becomes_a_decode_error_and_the_source_moves_on(tmp_path):
    folder = tmp_path / "ảnh hỏng"
    rec = RigRecorder(folder, ports=[1], image_format="png", clock=lambda: 1.0).start()
    for k in range(4):
        rec.add_frame(1, fake_frame(1, 1.0 + 0.02 * k, 10 * k))
    rec.stop(wait=True, timeout=5.0)
    (folder / "cam_p1" / "0000002.png").write_bytes(b"khong phai anh")        # tệp rác
    (folder / "cam_p1" / "thư mục.png").mkdir()                                 # không đọc được như tệp
    session = ReplaySession(folder)
    src = session.open_camera(CameraSpec(port=1, index=0))
    # mục hỏng không đi qua được read_camera_stream (đã thành bad_rows) nhưng nguồn vẫn phải chịu được: chèn thẳng
    src.items = src.items + [StreamItem(1.07, "frame", 5, None), StreamItem(1.08, "frame", 6, "tên\x00hỏng.png"),
                             StreamItem(1.09, "frame", 7, "thư mục.png")]
    session.begin(lead_s=-10.0)                                        # mọi mục đã tới hạn: đọc ngay
    frames, errors = [], []
    while not src.done and len(frames) + len(errors) < 20:
        try:
            frames.append(src.read())
        except FrameReadError as exc:
            errors.append(str(exc))
    assert src.done and len(frames) == 3 and len(errors) == 4 and src.decode_errors == 4
    assert all("phát lại không đọc/giải mã được" in e for e in errors)
    assert [int(f.image[0, 0, 0]) for f in frames] == [0, 20, 30]


def test_bench_rejects_bad_record_arguments_before_opening_any_device(tmp_path, monkeypatch, capsys):
    def no_devices(args):
        raise AssertionError("không được mở thiết bị")
    monkeypatch.setattr(bench, "build_rig", no_devices)
    used = tmp_path / "g01"
    used.mkdir()
    (used / "meta.json").write_text("{}", encoding="utf-8")
    a_file = tmp_path / "tệp.txt"
    a_file.write_text("x", encoding="utf-8")
    out = tmp_path / "o"
    for extra, needle in ((["--record", str(used)], "--record"), (["--record", str(a_file)], "--record"),
                          (["--record", str(tmp_path / "mới"), "--jpeg-quality", "0"], "--jpeg-quality")):
        with pytest.raises(SystemExit) as info:
            bench.main(["--name", "g", "--out", str(out), *extra])
        assert info.value.code == 2 and needle in capsys.readouterr().err, extra
    assert not out.exists() and not (tmp_path / "mới").exists()
    empty = tmp_path / "rỗng"
    empty.mkdir()
    with pytest.raises(AssertionError, match="không được mở thiết bị"):  # thư mục rỗng: qua được phép kiểm
        bench.main(["--name", "g", "--out", str(out), "--record", str(empty)])
    pytest.importorskip("PySide6")
    from autopark.ui import rig_app
    with pytest.raises(SystemExit) as info:                            # giao diện: báo ngay, không đợi lúc bấm ghi
        rig_app.build_window(["--jpeg-quality", "101"], start=False)
    assert info.value.code == 2


def test_bench_replay_that_never_reaches_the_end_of_the_recording_exits_1(recorded, tmp_path, monkeypatch, capsys):
    folder, _, _ = recorded
    monkeypatch.setattr(ReplaySession, "finished", property(lambda self: False))   # như một nguồn phát lại bị kẹt
    monkeypatch.setattr(bench, "REPLAY_MARGIN_S", 0.3)
    out = tmp_path / "out"
    code = bench.main(["--replay", str(folder), "--no-ai", "--name", "ket", "--out", str(out)])
    data = json.loads((out / "ket.rig.json").read_text(encoding="utf-8"))
    assert code == 1 and data["replay"]["finished"] is False and "tới hạn cứng" in capsys.readouterr().out
    # --seconds ngắn hơn bản ghi: dừng trước khi hết là đúng ý, không phải lỗi
    code = bench.main(["--replay", str(folder), "--no-ai", "--name", "ngan", "--out", str(out), "--seconds", "0.4"])
    assert code == 0 and "tới hạn cứng" not in capsys.readouterr().out


class FlakyLidar(FakeLidar):
    """LiDAR giả ném lỗi ở mỗi lần đọc thứ `every`, thông báo khác nhau từng lần, như ScanReadError giữa phiên."""

    def __init__(self, every=3, **kw):
        super().__init__(**kw)
        self.every, self.calls = every, 0

    def read(self):
        self.calls += 1
        if self.calls % self.every == 0:
            time.sleep(self.period)
            raise RuntimeError(f"giả lập ScanReadError lần {self.calls}")
        return super().read()


def test_lidar_read_errors_are_recorded_and_replayed_through_the_rig(tmp_path):
    folder = tmp_path / "lidar lỗi"
    rig = Rig(fake_manager(ports=(1,), period=PERIOD), RigConfig(ai=False),
              open_lidar=lambda: FlakyLidar(every=3, period=0.05))
    rig.start()
    try:
        time.sleep(0.2)
        rig.start_recording(folder, image_format="png")
        time.sleep(1.2)
        status = rig.stop_recording(wait=True)
    finally:
        assert rig.stop() == []
    a = rows(folder / "lidar" / "events.csv")
    assert len(a) >= 2 and status["lidar_events"] == len(a)
    assert all(e["message"].startswith("RuntimeError: giả lập ScanReadError lần ") for e in a)
    again = tmp_path / "ghi lại"
    session, st, _, lidar_stats, _, alive = replay_through_rig(folder, again)
    assert alive == [] and st["lidar"]["errors_replayed"] == len(a) and lidar_stats["errors"] == len(a)
    b = rows(again / "lidar" / "events.csv")
    # giới hạn đã biết (docs mục 5): phát lại ném RuntimeError(nguyên văn đã ghi), nên lớp bọc lúc ghi lại thêm một
    # tiền tố "RuntimeError: "
    assert [e["message"] for e in b] == ["RuntimeError: " + e["message"] for e in a]
    for x, y in zip(a, b):
        assert float(y["t_s"]) - session.origin == pytest.approx(float(x["t_s"]) - session.t_ref, abs=0.05)


class OddCamera(FakeCamera):
    """Camera giả ném một ngoại lệ thường (không phải FrameReadError) đúng một lần, ở lần đọc thứ `at`."""
    at = 20

    def read(self):
        if self.n + 1 == self.at and not getattr(self, "raised", False):
            self.raised = True
            time.sleep(self.period)
            raise ValueError("giả lập lỗi driver")
        return super().read()


def test_a_plain_exception_from_a_camera_is_recorded_and_replayed_as_a_non_frame_error(tmp_path):
    folder = tmp_path / "ngoại lệ"
    cams = MultiCameraManager([CameraSpec(port=1, index=0)], ring=3,
                              open_source=lambda spec: OddCamera(spec, period=PERIOD, textured=True))
    rig = Rig(cams, RigConfig(ai=False), open_lidar=lambda: FakeLidar(period=0.1))
    rig.start()
    try:
        time.sleep(0.2)                                                # lần đọc thứ 20 ≈ 0,6 s: trong cửa sổ ghi
        rig.start_recording(folder, image_format="png")
        time.sleep(1.0)
        status = rig.stop_recording(wait=True)
    finally:
        assert rig.stop() == []
    events = rows(folder / "cam_p1" / "events.csv")
    assert [(e["kind"], e["message"]) for e in events] == [("exception", "ValueError: giả lập lỗi driver")]
    assert status["events"][1] == {"exception": 1}
    again = tmp_path / "ghi lại"
    _, st, cam_stats, _, _, alive = replay_through_rig(folder, again)
    assert alive == [] and st["cameras"][1]["errors_replayed"] == 1
    assert cam_stats[1]["read_failures"] == 1 and cam_stats[1]["last_error"].startswith("RuntimeError: ")
    assert [e["kind"] for e in rows(again / "cam_p1" / "events.csv")] == ["exception"]
    # nguồn phát lại: KHÔNG ném FrameReadError cho sự kiện 'exception'
    session = ReplaySession(folder)
    src = session.open_camera(CameraSpec(port=1, index=0))
    session.begin(lead_s=-10.0)                                        # mọi mục đã tới hạn: đọc ngay
    raised = []
    while not src.done:
        try:
            src.read()
        except Exception as exc:  # noqa: BLE001
            raised.append(exc)
    assert len(raised) == 1 and not isinstance(raised[0], FrameReadError)
    assert str(raised[0]) == "ValueError: giả lập lỗi driver"


def test_rig_stop_waits_for_the_recorder_to_drain_its_queue(tmp_path, monkeypatch):
    slow_writes(monkeypatch, 0.03)
    rig = Rig(fake_manager(ports=(1, 2), period=0.01), RigConfig(ai=False))
    rig.start()
    try:
        rig.start_recording(tmp_path / "chậm", image_format="png")
        time.sleep(0.5)                                                # ≈ 100 khung tới, ≈ 17 đã ghi
        assert rig.recording_status()["pending_frames"] > 20
    finally:
        alive = rig.stop()                                             # KHÔNG gọi stop_recording trước
    st = rig.recording_status()
    assert alive == [] and st["state"] == "xong" and st["pending_frames"] == 0 and st["dropped_total"] == 0
    meta = json.loads((tmp_path / "chậm" / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "xong"


def test_bench_exits_1_when_the_recording_dropped_frames_without_a_write_error(tmp_path, monkeypatch, capsys):
    slow_writes(monkeypatch, 0.03)
    monkeypatch.setattr(bench, "build_rig", lambda args: Rig(fake_manager(ports=(1, 2), period=PERIOD), RigConfig(ai=False)))
    monkeypatch.setattr(bench, "recording_options", lambda args: {"image_format": "png", "max_pending_mb": 0.02})
    code = bench.main(["--name", "bo", "--seconds", "0.6", "--warmup", "0.1", "--out", str(tmp_path / "out"),
                       "--record", str(tmp_path / "bench_bo")])
    data = json.loads((tmp_path / "out" / "bo.rig.json").read_text(encoding="utf-8"))
    rec = data["recording"]
    assert rec["error"] is None and rec["state"] == "xong" and rec["dropped_total"] > 0
    assert code == 1 and "không trọn" in capsys.readouterr().out


def test_csv_rows_reach_the_disk_while_the_recording_is_still_running(tmp_path):
    rec = RigRecorder(tmp_path / "đang ghi", ports=[1], image_format="png", clock=lambda: 1.0).start()
    try:
        for k in range(5):
            rec.add_frame(1, fake_frame(1, 1.0 + 0.01 * k, k))
        rec.add_event(1, "truncated", 1.045, "cam_p1: truncated frame (24 of 48 rows filled by the decoder)")
        deadline = time.perf_counter() + 3.0
        seen = []
        while time.perf_counter() < deadline:
            seen = rows(tmp_path / "đang ghi" / "cam_p1" / "frames.csv")
            if len(seen) == 5:
                break
            time.sleep(0.02)
        assert rec.active and len(seen) == 5                           # tiến trình chết lúc này: vẫn còn 5 dòng
        assert len(rows(tmp_path / "đang ghi" / "cam_p1" / "events.csv")) == 1
    finally:
        rec.stop(wait=True, timeout=5.0)
