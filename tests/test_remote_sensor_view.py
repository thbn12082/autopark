"""Kiểm hướng vẽ và cách cửa sổ xử lý dữ liệu dừng cập nhật."""

import os
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.rig.remote_view_link import RemoteCameraSample  # noqa: E402
from autopark.ui import remote_sensor_view  # noqa: E402
from autopark.ui.remote_sensor_view import RemoteSensorWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeLink:
    def __init__(self, host, *, duration_s, camera_count):
        self.state = SimpleNamespace(status="stopped", detail="", cameras=(None,) * camera_count,
                                     scan=None, scan_seq=None, scan_at=None)
        self.closed = False

    def start(self):
        self.state.status = "connecting"

    def snapshot(self):
        return self.state

    def close(self):
        self.closed = True


def test_view_shows_fresh_sources_and_clears_stale_images(qapp):
    now = [100.0]
    window = RemoteSensorWindow("10.0.0.2", link_factory=FakeLink, clock=lambda: now[0])
    window.timer.stop()
    window.connect_link()
    link = window.link
    try:
        state = link.state
        state.status = "live"
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        state.cameras = (RemoteCameraSample(frame=frame, seq=1, at=100.0),)
        state.scan = LidarScan(SourceStamp("C1", 100.0), (0.0, 0.2, -0.2), (1.0, 1.5, 1.2))
        state.scan_seq = 1
        state.scan_at = 100.0
        window.refresh()
        assert window.camera_tiles[0].pixmap.width() == 1280
        assert window.scan_view.scan is state.scan
        assert window.camera_status[0].text() == window.scan_status.text() == "Trực tiếp"

        now[0] = 101.0
        state.scan_seq = 2
        state.scan_at = 101.0
        window.refresh()
        assert window.camera_tiles[0].pixmap is None
        assert window.camera_status[0].text() == "Dữ liệu cũ"
        assert window.scan_status.text() == "Trực tiếp"

        state.status = "error"
        state.detail = "SSH mất kết nối"
        window.refresh()
        assert window.scan_view.scan is None
        assert window.scan_status.text() == "Dữ liệu cũ"
        assert "SSH mất kết nối" in window.link_status.text()
        assert window.connect_button.isEnabled()
    finally:
        window.close()
    assert link.closed


def test_four_camera_tiles_keep_their_own_frame_and_freshness(qapp):
    now = [100.0]
    window = RemoteSensorWindow("10.0.0.2", camera_count=4, link_factory=FakeLink, clock=lambda: now[0])
    window.timer.stop()
    window.connect_link()
    try:
        state = window.link.state
        state.status = "live"
        frames = [np.full((24, 32, 3), i * 30, dtype=np.uint8) for i in range(1, 5)]
        state.cameras = tuple(RemoteCameraSample(frame=frame, seq=1, at=100.0) for frame in frames)
        window.refresh()
        assert [tile.pixmap.toImage().pixelColor(0, 0).red() for tile in window.camera_tiles] == [30, 60, 90, 120]
        assert "4/4 camera trực tiếp" in window.link_status.text()

        now[0] = 101.0
        state.cameras = (state.cameras[0], *(RemoteCameraSample(frame=frame, seq=2, at=101.0)
                                           for frame in frames[1:]))
        state.scan = LidarScan(SourceStamp("C1", 101.0), (0.0,), (1.0,))
        state.scan_seq = 1
        state.scan_at = 101.0
        window.refresh()
        assert window.camera_tiles[0].pixmap is None
        assert window.camera_status[0].text() == "Dữ liệu cũ"
        assert all(tile.pixmap is not None for tile in window.camera_tiles[1:])
        assert window.scan_view.scan is state.scan
        assert "3/4 camera trực tiếp" in window.link_status.text()
    finally:
        window.close()


def test_orientation_view_draws_front_up_and_vehicle_left_to_screen_left(qapp):
    window = RemoteSensorWindow(link_factory=FakeLink)
    try:
        scan = window.scan_view
        scan.resize(400, 360)
        origin = scan._to_widget(0, 0)
        assert scan._to_widget(1, 0).y() < origin.y()
        assert scan._to_widget(0, 1).x() < origin.x()
        assert scan._to_widget(0, -1).x() > origin.x()
    finally:
        window.close()


def test_bird_eye_tab_uses_only_current_camera_samples(qapp):
    now = [100.0]
    window = RemoteSensorWindow("10.0.0.2", camera_count=4, link_factory=FakeLink, clock=lambda: now[0])
    window.timer.stop()
    window.connect_link()
    submitted = []
    cleared = []
    lidar_seen = []
    window.bird_eye.submit = lambda frames, lidar=None: (submitted.append(frames), lidar_seen.append(lidar))
    window.bird_eye.clear = lambda: cleared.append(True)
    try:
        state = window.link.state
        state.status = "live"
        frames = [np.full((24, 32, 3), i, dtype=np.uint8) for i in range(1, 5)]
        state.cameras = tuple(RemoteCameraSample(frame=frame, seq=1, at=100.0) for frame in frames)
        window.refresh()
        assert not submitted

        window.tabs.setCurrentWidget(window.bird_eye)
        assert list(submitted[-1]) == [1, 2, 3, 4]
        assert all(submitted[-1][i] is frames[i - 1] for i in range(1, 5))

        now[0] = 101.0
        state.cameras = (state.cameras[0], *(RemoteCameraSample(frame=frame, seq=2, at=101.0)
                                           for frame in frames[1:]))
        window.refresh()
        assert cleared and list(submitted[-1]) == [2, 3, 4]

        state.status = "error"
        window.refresh()
        assert len(cleared) == 2
        assert len(submitted) == 2
    finally:
        window.close()


def test_auto_calibration_saves_distinct_held_poses_once(qapp, tmp_path, monkeypatch):
    class ImmediateExecutor:
        def __init__(self, *args, **kwargs):
            pass

        def submit(self, work, *args, **kwargs):
            future = Future()
            future.set_result(work(*args, **kwargs))
            return future

        def shutdown(self, *args, **kwargs):
            pass

    assessed = []
    first_corners = np.array([(100 + 12 * x, 100 + 12 * y) for y in range(6) for x in range(9)],
                             dtype=np.float32)
    second_corners = first_corners + np.array([170, 45], dtype=np.float32)

    def assess(frame, _spec, **_kwargs):
        pose = int(frame[0, 0, 0])
        assessed.append(pose)
        corners = first_corners if pose == 1 else second_corners
        return (remote_sensor_view.fisheye_calib.Detection(True, corners),
                remote_sensor_view.fisheye_calib.FrameQuality(True))

    monkeypatch.setattr(remote_sensor_view, "ThreadPoolExecutor", ImmediateExecutor)
    monkeypatch.setattr(remote_sensor_view.fisheye_calib, "assess_frame", assess)
    now = [100.0]
    window = RemoteSensorWindow("10.0.0.2", calibration_dir=tmp_path, link_factory=FakeLink,
                                clock=lambda: now[0])
    window.timer.stop()
    window.connect_link()
    try:
        state = window.link.state
        state.status = "live"
        first = np.full((720, 1280, 3), 1, dtype=np.uint8)
        second = np.full((720, 1280, 3), 2, dtype=np.uint8)
        state.cameras = (RemoteCameraSample(frame=first, seq=1, at=now[0]),)
        window.calibration_auto.setChecked(True)

        saved_dir = tmp_path / "cam_p1"
        for tick in (100.0, 100.18, 100.36, 100.54, 100.72):
            now[0] = tick
            window.refresh()
            window.refresh()
        assert assessed == [1]
        assert not list(saved_dir.glob("cap_*.png"))

        for seq, frame in enumerate([first] * 12 + [second] * 12, start=2):
            now[0] += 0.25
            state.cameras = (RemoteCameraSample(frame=frame, seq=seq, at=now[0]),)
            window.refresh()
            window.refresh()
            if seq == 13:
                assert len(list(saved_dir.glob("cap_*.png"))) == 1

        assert len(list(saved_dir.glob("cap_*.png"))) == 2
    finally:
        window.close()


class RecordingLink(FakeLink):
    made = []

    def __init__(self, host, *, duration_s, camera_count, check_esp32=True):
        super().__init__(host, duration_s=duration_s, camera_count=camera_count)
        self.host, self.check_esp32 = host, check_esp32
        RecordingLink.made.append(self)


def test_app_viewer_connects_by_itself_and_reconnects(qapp):
    """Trong app (27/11/2026): không ô IP hay nút; tự xem từ lúc dựng bằng IP của tab Kết nối xe (hoặc IP đã lưu),
    tự nối lại khi phiên hỏng, chuyển Pi khi tab Kết nối xe đổi Pi; Pi không mở cổng ESP32."""
    RecordingLink.made.clear()
    now = [0.0]
    conn = SimpleNamespace(mode="pi", target="", io=None)
    window = RemoteSensorWindow("", camera_count=4, link_factory=RecordingLink, connection=conn, check_esp32=False,
                                saved_host=lambda: "192.168.1.50", clock=lambda: now[0])
    window.timer.stop()
    try:
        assert not any(w.isVisibleTo(window) for w in (window.host, window.connect_button, window.stop_button))
        assert len(RecordingLink.made) == 1                                         # tự kết nối ngay khi dựng
        first = RecordingLink.made[0]
        assert first.host == "192.168.1.50" and first.check_esp32 is False

        first.state.status = "error"                                                # Pi tắt / Wi-Fi rớt
        now[0] = 1.0
        window._tick()
        assert len(RecordingLink.made) == 1                                         # chưa đủ RECONNECT_S
        now[0] = 1.0 + remote_sensor_view.RECONNECT_S
        window._tick()
        assert len(RecordingLink.made) == 2 and RecordingLink.made[1].state.status == "connecting"

        conn.target = "192.168.1.60"                                                # tab Kết nối xe nối Pi khác
        window._tick()
        assert RecordingLink.made[1].closed and RecordingLink.made[-1].host == "192.168.1.60"
    finally:
        window.close()


def test_app_viewer_without_ip_waits(qapp):
    RecordingLink.made.clear()
    conn = SimpleNamespace(mode="pi", target="", io=None)
    window = RemoteSensorWindow("", camera_count=4, link_factory=RecordingLink, connection=conn, check_esp32=False)
    window.timer.stop()
    try:
        assert RecordingLink.made == [] and "Kết nối xe" in window.link_status.text()
    finally:
        window.close()


def test_sender_source_passes_esp32_flag():
    from autopark.rig.remote_view_link import _sender_source
    assert b"VIEW_CHECK_ESP32 = False\n" in _sender_source(10.0, 4, False)
    assert b"VIEW_CHECK_ESP32 = True\n" in _sender_source(10.0, 4)


def test_rig_calibration_button_captures_solves_and_rebuilds(qapp, tmp_path):
    """Nút Hiệu chuẩn camera (27/11/2026): gom 3 ảnh/camera, giải bằng 4 tờ in, ghi rig, dựng lại BEV và 3D."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    import test_sheet_extrinsics as tse
    from autopark.perception import extrinsics_calib as ec
    from autopark.perception import rig_sheets as rs
    from autopark.perception.calib_board import render_rects_png

    textures = {}
    for sheet in rs.SHEETS:
        rects, _ = rs.page_content(sheet, rs.make_board(sheet["first_id"]))
        textures[sheet["key"]] = render_rects_png(rs.PAGE_MM, rects, (), tse.DPI)
    images = {port: tse.render(port, textures)[0] for port in (1, 2, 3, 4)}

    now = [100.0]
    window = RemoteSensorWindow("10.0.0.2", camera_count=4, link_factory=FakeLink, clock=lambda: now[0])
    window.timer.stop()
    window.rig_calib_folder = tmp_path / "phien"
    window.rig_calib_out = tmp_path / "rig_v1.json"
    window.rig_calib_kwargs = {"vehicle": dict(tse.VEHICLE), "intrinsics": tse._synth_intrinsics,
                               "allow_synthetic": True}
    try:
        window.connect_link()
        state = window.link.state
        state.status = "live"
        old_3d, old_bev = window.surround_3d, window.bird_eye
        window.start_rig_calibration()
        assert window.rig_calib_button.text() == "Đang chụp ảnh…" and not window.rig_calib_button.isEnabled()
        for seq in range(1, 4):                                      # ba khung mới của mỗi camera
            now[0] += 0.2
            state.cameras = tuple(RemoteCameraSample(frame=images[p], seq=seq, at=now[0]) for p in (1, 2, 3, 4))
            window._advance_rig_calibration()
        assert window._rig_calib["stage"] == "solve"
        window._rig_calib["future"].result(timeout=120)
        window._advance_rig_calibration()
        assert window._rig_calib is None and window.rig_calib_button.isEnabled()
        box = window._rig_calib_box
        assert box.text() == "Hiệu chuẩn xong: cả 4 camera đạt", box.informativeText()
        assert window.rig_calib_out.is_file() and (tmp_path / "phien" / "to_in" / "cam_p2" / "anh_3.png").is_file()
        assert window.surround_3d is not old_3d and window.bird_eye is not old_bev
        assert window.tabs.indexOf(window.surround_3d) == 2 and window.tabs.indexOf(window.bird_eye) == 1
        box.close()
    finally:
        window.close()


def test_rig_calibration_needs_live_cameras(qapp):
    window = RemoteSensorWindow("10.0.0.2", camera_count=4, link_factory=FakeLink)
    window.timer.stop()
    try:
        window.start_rig_calibration()
        assert window._rig_calib is None and window._rig_calib_box.text() == "Chưa có hình từ Pi"
        window._rig_calib_box.close()
    finally:
        window.close()
