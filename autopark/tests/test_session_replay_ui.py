"""Phát lại chung một đồng hồ (T3b, `ui.lidar_app --session-replay`, 02/10/2026), offscreen và không phần cứng: MỘT
`ReplaySession` cấp cả ngăn LiDAR (`DockLidarReplay`) lẫn ngăn AI camera (Rig phát lại), nên vòng quét và khung camera giữ
đúng độ lệch như lúc ghi; không có ngăn AI camera thì đồng hồ bắt đầu ngay khi gắn LiDAR; dòng lệnh dùng sai bị từ chối
(mã 2) trước khi mở cửa sổ. Bản ghi dùng ở đây là bản ghi cảm biến trong phiên đỗ (T3) của camera giả + LiDAR giả."""
import csv
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.lidar.live_view import ScanStreamEnded  # noqa: E402
from autopark.rig.replay import ReplaySession, load_lidar  # noqa: E402
from autopark.ui import lidar_app  # noqa: E402
from autopark.ui.lidar_dock import DockLidarReplay, lidar_clock_ok  # noqa: E402
from tests.rig_fakes import FakeSegmenter  # noqa: E402
from tests.test_session_recording import record_session  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def no_devices(monkeypatch):
    import serial

    def refuse(*args, **kwargs):
        raise AssertionError("test không được mở thiết bị thật")
    monkeypatch.setattr(serial, "Serial", refuse)
    monkeypatch.setattr(serial, "serial_for_url", refuse)
    monkeypatch.setattr(cv2, "VideoCapture", refuse)


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    rec, _, _ = record_session(tmp_path_factory.mktemp("t3b") / "gốc", seconds=1.0)
    return rec.folder


def rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def open_window(camera=True):
    window, dock = lidar_app.build_window(None, port=None, recording=None,
                                          camera_ai={"ports": (1, 2)} if camera else None)
    window._timer.stop()
    dock.timer.stop()
    window.record_dock.timer.stop()
    if window.camera_dock is not None:
        window.camera_dock.timer.stop()
    return window, dock


def pump(window, until, timeout=15.0):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        window.dock.tick()
        if window.camera_dock is not None:
            window.camera_dock.tick()
        if until():
            return True
        time.sleep(0.02)
    return False


def test_session_replay_feeds_both_docks_from_one_clock(qapp, recorded, no_devices):
    window, dock = open_window()
    cam = window.camera_dock
    session = ReplaySession(recorded)
    scans, frames = [], {}
    real_handle = dock._handle_scan

    def spy(scan, quality, t_first, *rest):                           # rest: t_perf của ScanReader (T2)
        scans.append(scan.stamp.t + session.origin)                   # stamp phiên + t0 = giờ trên đồng hồ phát lại
        real_handle(scan, quality, t_first, *rest)
    dock._handle_scan = spy

    def on_batch(result, upd, info):
        for port, frame in result.frame_set.frames.items():
            frames.setdefault(port, set()).add(frame.meta.stamp.t)
    cam.on_batch = on_batch
    try:
        assert lidar_app.start_session_replay(window, session, make_segmenter=lambda p: FakeSegmenter(p, delay=0.002))
        assert isinstance(dock.source, DockLidarReplay) and cam.rig.replay is session
        info = dock.recording_info()
        assert (info["kind"], info["recording"]) == ("replay", str(recorded)) and cam.edit_replay.text() == str(recorded)
        assert pump(window, lambda: session.finished and dock.source is None), session.status()
        assert "hết bản ghi phát lại" in dock.last_error              # hết bản ghi: ngăn LiDAR tự ngắt
        status = session.status()
    finally:
        cam.shutdown()
        dock.shutdown()
        window.close()
    lidar, _ = load_lidar(recorded)
    assert len(scans) == len(lidar) and session.begun
    # MỘT gốc cho cả hai ngăn: mọi stamp phát lại = gốc + (stamp ghi − t_ref), nên độ lệch camera − LiDAR như lúc ghi
    np.testing.assert_allclose(np.array(scans) - session.origin, lidar.t - session.t_ref, atol=1e-6)
    assert sorted(frames) == [1, 2] and all(len(v) >= 3 for v in frames.values())
    for port, stamps in frames.items():
        recorded_t = np.array([float(r["t_s"]) for r in rows(recorded / f"cam_p{port}" / "frames.csv")])
        for t in stamps:
            assert np.min(np.abs(recorded_t - (session.t_ref + t - session.origin))) < 1e-6
    # và ra đúng lịch (cùng đồng hồ thật): trễ so với lịch nhỏ cho cả camera lẫn LiDAR
    assert status["lidar"]["late_ms"]["median"] < 50.0
    assert all(c["late_ms"]["median"] < 50.0 for c in status["cameras"].values())


def test_without_the_camera_dock_the_replay_clock_starts_with_the_lidar(qapp, recorded, no_devices):
    session = ReplaySession(recorded)
    source = DockLidarReplay(session)
    assert source.t0 is None and source.now() == 0.0
    assert lidar_clock_ok(source) == (False, "nguồn chưa có mốc t0 (driver chưa start())")   # trước begin()
    source.close()
    with pytest.raises(ScanStreamEnded):
        source.read()                                                  # đã đóng: hết bản ghi, không chặn
    window, dock = open_window(camera=False)
    session = ReplaySession(recorded)
    try:
        assert lidar_app.start_session_replay(window, session) is False and session.begun
        assert isinstance(dock.source, DockLidarReplay) and dock.source.t0 == session.origin
        assert pump(window, lambda: dock.source is None)
        lidar, _ = load_lidar(recorded)
        assert dock.scans == len(lidar)
    finally:
        dock.shutdown()
        window.close()


def test_session_replay_cli_conflicts(recorded, tmp_path, monkeypatch, capsys):
    class NoWindow(Exception):
        pass

    seen = {}

    def no_window(*args, **kwargs):
        seen.update(kwargs)
        raise NoWindow
    monkeypatch.setattr(lidar_app, "build_window", no_window)
    folder = str(recorded)
    for argv, needle in ((["--session-replay", folder, "--recording", folder], "--recording"),
                         (["--session-replay", folder, "--port", "COM5"], "--port"),
                         (["--session-replay", folder, "--camera-ai", "--cam-replay", folder], "--cam-replay"),
                         (["--session-replay", str(tmp_path / "không có")], "không phải thư mục ghi phiên"),
                         (["--session-replay", folder, "--camera-ai", "--cam-ports", "9"], "cổng [9]")):
        with pytest.raises(SystemExit) as info:
            lidar_app.main(argv)
        assert info.value.code == 2 and needle in capsys.readouterr().err, argv
    assert seen == {}                                                  # trước khi dựng cửa sổ
    with pytest.raises(NoWindow):                                      # rig TỔNG HỢP nhận cùng bản ghi phát lại chung
        lidar_app.main(["--session-replay", folder, "--camera-ai", "--camera-ai-test-rig"])
    assert seen["camera_ai"]["test_rig"] is True and seen["recording"] is None and seen["port"] is None
