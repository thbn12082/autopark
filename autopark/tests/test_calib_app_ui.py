"""Giao diện hiệu chuẩn camera, chạy offscreen với camera giả phát ảnh bảng tổng hợp (camera mắt cá đã biết, xem
tests/test_fisheye_calib.py): chụp tay, tự chụp mỗi tư thế một lần, khung hỏng bị đếm và không được chụp, hiệu chuẩn
trong luồng nền, lưu vào thư mục tên tiếng Việt, đổi cổng/mode thì mở lại camera và bỏ ảnh cũ — kể cả kết quả của một
lần hiệu chuẩn đang chạy; lưới phủ và ảnh nắn so theo từng điểm ảnh; phím cách chụp cả khi ô nhập số giữ focus."""
import dataclasses
import json
import os
from pathlib import Path
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.perception import fisheye_calib as fc  # noqa: E402
from autopark.ui.calib_app import CalibWindow, parse_size  # noqa: E402
from autopark.video.sources import FrameReadError, _frame  # noqa: E402
from tests.test_fisheye_calib import SPEC, TRUE_K, synthetic_set  # noqa: E402
from tests.test_truncated_frames import truncate  # noqa: E402


class FakeBoardCamera:
    """Như UsbCameraSource: read() chặn một chu kỳ rồi trả khung. `pose` chọn ảnh đang phát; `hold` > 0 thì tự chuyển
    ảnh sau mỗi `hold` lần đọc (bảng đứng yên rồi đổi chỗ); mỗi `broken_every` lần ném lỗi khung bị cắt như nguồn thật."""

    def __init__(self, frames, period=0.01, hold=0, broken_every=0):
        self.frames, self.period, self.hold, self.broken_every = frames, period, hold, broken_every
        self.pose, self.n, self.closed = 0, 0, False

    def read(self):
        time.sleep(self.period)
        self.n += 1
        if self.broken_every and self.n % self.broken_every == 0:
            raise FrameReadError("cam_p1: truncated frame (240 of 480 rows filled by the decoder)")
        pose = (self.n // self.hold) % len(self.frames) if self.hold else self.pose
        return _frame("cam_p1", time.perf_counter(), f"pose{pose}#{self.n}", self.frames[pose])

    def close(self):
        self.closed = True


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(app, seconds, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.01)
    app.processEvents()
    return until() if until is not None else None


def showing(window, pose):
    live = window.live_camera.latest()
    return live is not None and live.source_path.startswith(f"pose{pose}#") and window._last_seq == live.seq


def test_manual_capture_calibrate_and_save_into_unicode_folders(qapp, tmp_path):
    _, views = synthetic_set()
    blank = np.full((480, 640, 3), 110, np.uint8)
    frames = [v[0] for v in views[:12]] + [blank]
    opened = []

    def factory(port, w, h):
        cam = FakeBoardCamera(frames)
        opened.append((port, w, h, cam))
        return cam

    window = CalibWindow(factory, port=1, spec=SPEC, out_dir=tmp_path / "hiệu chuẩn", runs_dir=tmp_path / "ảnh chụp")
    try:
        cam = opened[0][3]
        assert opened[0][:3] == (1, 640, 480)
        cam.pose = 12
        assert pump(qapp, 10, lambda: showing(window, 12))
        assert not window.capture() and "không thấy" in window.message
        assert "Không thấy bảng 9×6" in window.status.text()
        assert not window.btn_calib.isEnabled() and not window.btn_save.isEnabled()
        for k in range(12):
            cam.pose = k
            assert pump(qapp, 10, lambda: showing(window, k)), k
            assert window.capture(), window.message
        assert len(window.captures) == 12 and window.capture_list.count() == 12
        assert pump(qapp, 2, lambda: "TRÙNG" in window.status.text())             # đang đứng đúng tư thế vừa chụp
        assert "→ ĐẠT" in window.status.text()
        assert window.live_view.pixmap is not None and "đã chụp 12" in window.cam_line.text()
        window.square_spin.setValue(25.0)
        window.chk_measured.setChecked(True)
        assert window.btn_calib.isEnabled() and not window.btn_save.isEnabled()
        assert window.start_calibration()
        assert pump(qapp, 60, lambda: window.calib is not None), window.message
        calib = window.calib
        assert calib.K[0, 0] == pytest.approx(TRUE_K[0, 0], rel=0.01) and calib.K[1, 1] == pytest.approx(TRUE_K[1, 1], rel=0.01)
        assert calib.rms_px < 0.3
        text = window.results.text()
        assert "RMS chiếu lại" in text and "trường nhìn" in text and "sang mô hình dự án" in text and "Chưa gắn lên rig" in text
        assert "RMS" in window.capture_list.item(0).text()
        assert pump(qapp, 5, lambda: window.undist_view.pixmap is not None)            # ảnh nắn bên cạnh ảnh sống
        assert window.btn_save.isEnabled()
        # đổi cỡ ô sau khi hiệu chuẩn: không cho lưu kết quả tính bằng cỡ ô cũ, và chưa ghi tệp nào
        window.square_spin.setValue(24.9)
        assert window.save() is None and "cỡ ô đã đổi" in window.message
        assert not any((tmp_path / "hiệu chuẩn").glob("*.json"))
        window.square_spin.setValue(25.0)
        path = window.save()
        assert path == tmp_path / "hiệu chuẩn" / "cam_p1.json" and path.exists()
        record = fc.load_calibration(path)
        assert record["camera"]["hub_port"] == 1 and record["image_size"] == [640, 480]
        assert record["square_mm_measured"] == 25.0 and record["extrinsic"] is None and record["n_images_used"] == 12
        assert record["capture"]["tool"] == "autopark.ui.calib_app" and record["capture"]["failed_writes"] == []
        folder = Path(record["images_dir"])
        assert folder.parent == tmp_path / "ảnh chụp" and folder.name.endswith("_p1")
        names = sorted(p.name for p in folder.glob("cap_*.png"))
        assert len(names) == 12 and (folder / "cam_p1.json").exists()
        first = cv2.imdecode(np.fromfile(str(folder / names[0]), np.uint8), cv2.IMREAD_COLOR)
        assert np.array_equal(first, frames[0])                                           # ảnh gốc, không nén mất
        caps = json.loads((folder / "captures.json").read_text(encoding="utf-8"))
        assert len(caps["captures"]) == 12 and len(caps["captures"][0]["corners"]) == 54
        # thư mục đã lưu hiệu chuẩn lại được bằng dòng lệnh, ra cùng K
        again_path = tmp_path / "hiệu chuẩn lại.json"
        assert fc.main(["calibrate", "--images", str(folder), "--square-mm", "25", "--port", "1", "--out", str(again_path)]) == 0
        assert np.allclose(fc.load_calibration(again_path)["K"], record["K"], atol=0.05)
        # đổi danh sách ảnh sau khi hiệu chuẩn: không cho lưu kết quả cũ
        window.capture_list.setCurrentRow(0)
        window.delete_selected()
        assert len(window.captures) == 11
        assert window.save() is None and "Hiệu chuẩn lại" in window.message and not window.btn_save.isEnabled()
    finally:
        window.close()
    assert cam.closed and not window.live_camera.is_alive()


def test_auto_capture_takes_each_distinct_still_pose_once(qapp, tmp_path):
    _, views = synthetic_set()
    frames = [v[0] for v in views[:6]]
    cams = []

    def factory(port, w, h):
        cams.append(FakeBoardCamera(frames, period=0.01, hold=12))
        return cams[-1]

    gate = fc.AutoCaptureGate(still_s=0.08, min_interval_s=0.05)
    window = CalibWindow(factory, port=2, spec=SPEC, out_dir=tmp_path, runs_dir=tmp_path, gate=gate)
    try:
        window.chk_auto.setChecked(True)
        assert pump(qapp, 60, lambda: cams[0].n >= 2 * 6 * 12 + 12)          # hai vòng đủ sáu tư thế
        caps = window.captures
        assert 4 <= len(caps) <= 6, [c.name for c in caps]                    # vòng hai không chụp lại tư thế cũ
        assert all(c.auto for c in caps)
        for i in range(len(caps)):
            for j in range(i):
                assert fc.pose_distance(caps[i].descriptor, caps[j].descriptor) >= gate.min_pose_distance
        assert "tự" in window.capture_list.item(0).text()
    finally:
        window.close()


def test_damaged_frames_are_counted_not_captured_and_switching_camera_reopens(qapp, tmp_path):
    _, views = synthetic_set()
    good = views[4][0]
    frames = [good, truncate(good, 300)]
    opened = []

    def factory(port, w, h):
        if port == 4:
            raise ValueError("không thấy camera ở cổng [4]")
        cam = FakeBoardCamera(frames, broken_every=3)
        opened.append((port, w, h, cam))
        return cam

    window = CalibWindow(factory, port=1, spec=SPEC, out_dir=tmp_path, runs_dir=tmp_path)
    try:
        cam = opened[0][3]
        assert pump(qapp, 10, lambda: showing(window, 0))
        assert pump(qapp, 5, lambda: window.live_camera.counters.truncated >= 2)
        assert window.capture()
        cam.pose = 1                                                           # khung bị cắt lọt qua nguồn (không kiểm)
        assert pump(qapp, 10, lambda: showing(window, 1))
        assert "KHUNG HỎNG" in window.status.text() and "cắt cụt" in window.status.text()
        assert not window.capture() and "cắt cụt" in window.message and len(window.captures) == 1
        line = window.cam_line.text()
        assert "khung hỏng nguồn đã loại" in line and window.live_camera.counters.damaged_seen >= 1
        window.size_box.setCurrentIndex(window.size_box.findData("1280x720"))
        assert opened[-1][:3] == (1, 1280, 720) and cam.closed
        assert window.captures == [] and window.capture_list.count() == 0 and "bỏ 1 ảnh" in window.message
        window.port_box.setCurrentIndex(window.port_box.findData(3))
        assert opened[-1][:3] == (3, 1280, 720) and "cổng 3" in window.windowTitle()
        window.port_box.setCurrentIndex(window.port_box.findData(4))
        assert pump(qapp, 5, lambda: "KHÔNG MỞ ĐƯỢC CAMERA cổng 4" in window.status.text())
    finally:
        window.close()


def test_parse_size():
    assert parse_size("1280x720") == (1280, 720) and parse_size("640×480") == (640, 480)


def capture_poses(qapp, window, cam, poses):
    for k in poses:
        cam.pose = k
        assert pump(qapp, 10, lambda: showing(window, k)), k
        assert window.capture(), window.message


@pytest.mark.parametrize("switch", ["port", "size_and_back"])
def test_calibration_still_running_when_the_camera_or_mode_changes_is_discarded(qapp, tmp_path, switch):
    """Kết quả của camera/mode trước không được gán cho camera vừa mở (nhãn cổng mới, ảnh sống mới nắn bằng K, D cũ) —
    kể cả khi quay lại đúng mode cũ: ảnh của lần mở trước đã bị bỏ, nên kết quả đó không còn ứng với ảnh nào."""
    _, views = synthetic_set()
    frames = [v[0] for v in views[:12]]
    opened = []

    def factory(port, w, h):
        opened.append((port, w, h, FakeBoardCamera(frames)))
        return opened[-1][3]

    window = CalibWindow(factory, port=1, spec=SPEC, out_dir=tmp_path / "hiệu chuẩn", runs_dir=tmp_path / "ảnh")
    try:
        capture_poses(qapp, window, opened[0][3], range(12))
        assert window.start_calibration()
        assert not window.port_box.isEnabled() and not window.size_box.isEnabled()      # khoá ô chọn khi đang chạy
        # đổi ngay, trước khi vòng giao diện kịp lấy kết quả (ô bị khoá vẫn đổi được bằng mã, reopen là hàm công khai)
        if switch == "port":
            window.port_box.setCurrentIndex(window.port_box.findData(3))
            want = (3, 640, 480)
        else:
            window.size_box.setCurrentIndex(window.size_box.findData("1280x720"))
            window.size_box.setCurrentIndex(window.size_box.findData("640x480"))
            want = (1, 640, 480)
        assert opened[-1][:3] == want and "sẽ bị bỏ" in window.message
        assert pump(qapp, 60, lambda: window._calib_thread is None), window.message
        assert window.calib is None and window.record is None and window.results.text() == "chưa hiệu chuẩn"
        assert "bỏ kết quả hiệu chuẩn" in window.message
        assert pump(qapp, 5, lambda: window._last_seq > 0)
        pump(qapp, 0.3)                                                          # thêm vài khung sống: vẫn không nắn
        assert window.undist_view.pixmap is None
        assert not window.btn_save.isEnabled() and window.port_box.isEnabled() and window.size_box.isEnabled()
        assert window.save() is None and not (tmp_path / "hiệu chuẩn").exists()
        # camera mới: chụp đủ lại thì hiệu chuẩn được, và kết quả mang đúng cổng
        capture_poses(qapp, window, opened[-1][3], range(12))
        assert window.btn_calib.isEnabled() and window.start_calibration()
        assert pump(qapp, 60, lambda: window.calib is not None), window.message
        assert window.record["camera"]["hub_port"] == want[0]
    finally:
        window.close()


def view_bgr(view):
    """Ảnh BGR đang hiện trên một ImageView (pixmap giữ nguyên độ phân giải khung)."""
    img = view.pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    rgb = np.frombuffer(bytes(img.constBits()), np.uint8, count=bpl * h).reshape(h, bpl)[:, :3 * w].reshape(h, w, 3)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def test_overlay_preview_square_size_measured_flag_size_guard_and_reopen(qapp, tmp_path):
    _, views = synthetic_set()
    blank = np.full((480, 640, 3), 110, np.uint8)
    frames = [v[0] for v in views[:12]] + [blank]
    opened = []

    def factory(port, w, h):
        opened.append(FakeBoardCamera(frames))
        return opened[-1]

    window = CalibWindow(factory, port=1, spec=SPEC, out_dir=tmp_path / "hiệu chuẩn", runs_dir=tmp_path / "ảnh chụp")
    try:
        cam = opened[0]
        # lưới phủ: chưa chụp ảnh nào → mọi ô đỏ; tắt "Lưới phủ" → ảnh gốc
        cam.pose = 12
        assert pump(qapp, 10, lambda: showing(window, 12))
        expected = fc.draw_coverage(blank, np.zeros((fc.COVERAGE_GRID[1], fc.COVERAGE_GRID[0]), np.int64))
        shown = view_bgr(window.live_view)
        assert np.abs(shown.astype(int) - expected.astype(int)).max() <= 1
        assert shown[200, 300, 2] > shown[200, 300, 0] + 40
        window.chk_cov.setChecked(False)
        seq = window._last_seq
        assert pump(qapp, 5, lambda: window._last_seq != seq)
        assert np.array_equal(view_bgr(window.live_view), blank)
        window.chk_cov.setChecked(True)
        capture_poses(qapp, window, cam, range(12))
        # khung đạt nhưng khác cỡ các ảnh đã chụp → không chụp (nguồn giả chỉ phát 640×480 nên dựng LiveFrame)
        live = window.live_camera.latest()
        bigger = dataclasses.replace(live, image=cv2.resize(live.image, (1280, 720)))
        assert not window.capture(bigger) and "khác cỡ" in window.message and len(window.captures) == 12
        window.square_spin.setValue(25.0)
        assert not window.chk_measured.isChecked()
        assert window.start_calibration()
        assert pump(qapp, 60, lambda: window.calib is not None), window.message
        calib = window.calib
        # ảnh nắn = undistort_image của đúng khung đang phát, không phải ảnh sống
        assert pump(qapp, 5, lambda: window.undist_view.pixmap is not None)
        maps = fc.undistort_maps(calib.K, calib.D, (640, 480), window.balance_slider.value() / 100.0)
        want = fc.undistort_image(frames[11], calib.K, calib.D, maps=maps)
        got = view_bgr(window.undist_view)
        assert got.shape == want.shape and np.abs(got.astype(int) - want.astype(int)).max() <= 1
        assert not np.array_equal(got, frames[11])
        # đổi cỡ ô sau khi hiệu chuẩn → không lưu; trả lại đúng cỡ → lưu được
        window.square_spin.setValue(25.5)
        assert window.save() is None and "cỡ ô đã đổi" in window.message
        window.square_spin.setValue(25.0)
        # chưa tích "Đã đo cỡ ô" → square_mm_measured = null; tích rồi lưu lại → 25.0
        path = window.save()
        assert path is not None and fc.load_calibration(path)["square_mm_measured"] is None
        window.chk_measured.setChecked(True)
        assert fc.load_calibration(window.save())["square_mm_measured"] == 25.0
        # đổi cổng: bỏ hiệu chuẩn của camera cũ
        window.port_box.setCurrentIndex(window.port_box.findData(2))
        assert window.calib is None and window.record is None and window.results.text() == "chưa hiệu chuẩn"
        assert pump(qapp, 5, lambda: window._last_seq > 0)
        assert window.undist_view.pixmap is None and not window.btn_save.isEnabled()
    finally:
        window.close()


def test_auto_capture_respects_min_interval_after_a_capture(qapp, tmp_path):
    """min_pose_distance = 0 để chỉ còn khoảng cách thời gian chặn chụp lại: bảng đứng yên một tư thế → đúng một ảnh."""
    _, views = synthetic_set()
    cams = []

    def factory(port, w, h):
        cams.append(FakeBoardCamera([views[3][0]], period=0.01))
        return cams[-1]

    gate = fc.AutoCaptureGate(still_s=0.05, min_interval_s=30.0, min_pose_distance=0.0)
    window = CalibWindow(factory, port=1, spec=SPEC, out_dir=tmp_path, runs_dir=tmp_path, gate=gate)
    try:
        window.chk_auto.setChecked(True)
        assert pump(qapp, 20, lambda: len(window.captures) >= 1), window.status.text()
        n0 = cams[0].n
        assert pump(qapp, 10, lambda: cams[0].n >= n0 + 30)
        assert len(window.captures) == 1, [c.name for c in window.captures]
    finally:
        window.close()


def test_space_captures_even_while_a_number_box_has_focus(qapp, tmp_path):
    """Ô số (QLineEdit bên trong) nuốt phím cách qua ShortcutOverride: đúng lúc vừa gõ cỡ ô đo được (chưa Enter) mà
    bấm phím cách thì không chụp, không báo gì. Phím cách phải chụp, và không lọt vào ô số."""
    _, views = synthetic_set()
    cams = []

    def factory(port, w, h):
        cams.append(FakeBoardCamera([v[0] for v in views[:3]]))
        return cams[-1]

    window = CalibWindow(factory, port=1, spec=SPEC, out_dir=tmp_path, runs_dir=tmp_path)
    try:
        window.show()
        window.activateWindow()
        assert QTest.qWaitForWindowActive(window)
        # ngưỡng mờ 6,5 chứ không 2,5: ở 2,5 ảnh tổng hợp bị từ chối "mờ" và phép thử không còn đo phím cách
        for pose, (spin, text, value) in enumerate(((window.square_spin, "19{dec}95", 19.95),
                                                    (window.edge_spin, "6{dec}5", 6.5))):
            typed = text.format(dec=spin.locale().decimalPoint())
            QTest.mouseClick(spin.lineEdit(), Qt.MouseButton.LeftButton)
            spin.selectAll()
            QTest.keyClicks(spin.lineEdit(), typed)                                  # gõ dở, chưa Enter
            assert qapp.focusWidget() is spin
            cams[0].pose = pose
            assert pump(qapp, 10, lambda: showing(window, pose))
            n = len(window.captures)
            QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Space)
            assert len(window.captures) == n + 1, window.message
            assert spin.value() == pytest.approx(value) and spin.lineEdit().text() == typed + spin.suffix()
        cams[0].pose = 2
        assert pump(qapp, 10, lambda: showing(window, 2))
        QTest.mouseClick(window.btn_capture, Qt.MouseButton.LeftButton)
        assert len(window.captures) == 3
    finally:
        window.close()
