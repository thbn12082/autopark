"""Giao diện tham chiếu trên cao (`autopark.ui.overhead_app`, thêm 02/10/2026), chạy offscreen trên bộ thử TỔNG HỢP và
camera GIẢ: thẻ mặt sàn (dò, chấm tay, khớp, lưu; đổi đầu vào thì kết quả cũ mất hiệu lực), trích tư thế trong luồng nền
(đóng cửa sổ giữa chừng thì luồng dừng ≤ 3 s), TC-1, ghi video (camera chỉ mở khi bấm). Không mở camera thật. Sửa
02/10/2026 (đợt 2): thẻ TC-1 từ chối như dòng lệnh, ô "số khung/s danh định" như --allow-nominal-fps, sai số đồng bộ
phải hữu hạn ≥ 0, tệp ghi mang EcoQoS đọc lúc ghi (lớp Win32 của EcoQoS được thay bằng hàm giả)."""
import csv
import json
import os
from pathlib import Path
import shutil
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import autopark.power_throttling as pt  # noqa: E402
from autopark.evaluation import overhead_ref as R  # noqa: E402
from autopark.evaluation.overhead_synth import camera_stamps  # noqa: E402
from autopark.evaluation.reference_pose import read_reference  # noqa: E402
from autopark.lidar import recording as lidar_recording  # noqa: E402
from autopark.perception.paths import PROJECT  # noqa: E402
from autopark.ui.overhead_app import OverheadWindow  # noqa: E402
from autopark.video.sources import _frame  # noqa: E402
from tests.overhead_set import TC1_MIN_FRAMES, floor_fit_path, small_set  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def no_git(monkeypatch):
    monkeypatch.setattr(lidar_recording, "git_commit", lambda: "test")


@pytest.fixture
def window(qapp, tmp_path):
    made = []

    def make(factory=None, **kw):
        w = OverheadWindow(factory, camera_index=None if factory is None else 7, runs_dir=tmp_path / "runs",
                           track_dir=tmp_path / "nghiem_thu", size=(960, 540), **kw)
        made.append(w)
        return w
    yield make
    for w in made:
        w.close()


def pump(app, seconds, until):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until():
            return True
        time.sleep(0.01)
    app.processEvents()
    return until()


def test_floor_tab_detect_fit_save(window, qapp, tmp_path):
    info = small_set()
    w = window()
    assert w.load_intrinsics(info["intrinsics"]) and w.load_survey(info["survey"])
    assert w.load_floor_images([info["floor_image"]])
    assert w.detect_floor() == 32 and w.floor_table.rowCount() == 32
    assert {w.floor_table.item(r, 3).text() for r in range(32)} == {"ArUco"}
    assert not w.btn_save_floor.isEnabled()
    assert w.fit_floor() and w.fit.ok and w.btn_save_floor.isEnabled()
    assert "ĐẠT các phép kiểm" in w.floor_summary.text() and "Dùng được cho (chỉ phần mặt sàn)" in w.floor_summary.text()
    assert w.floor_table.item(0, 6).text() != ""                         # cột sai số (mm) đã điền
    out = w.save_floor(tmp_path / "mat_san.json")
    assert out is not None and out.exists() and (tmp_path / "mat_san_xem.jpg").exists()
    assert R.load_floor_fit(out).ok and w.track_fit is w.fit
    assert w.save_floor(tmp_path / "mat_san.json") is None and "đã có" in w.message      # không ghi đè im lặng
    assert w.load_survey(info["survey"])                                  # đổi đầu vào: kết quả cũ mất hiệu lực
    assert w.fit is None and not w.btn_save_floor.isEnabled() and w.save_floor(tmp_path / "b.json") is None


def test_manual_click_point_used_in_fit(window, qapp, tmp_path):
    info = small_set()
    with open(info["survey"], encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows[3]["ma_aruco"] = ""
    survey = tmp_path / "moc.csv"
    with survey.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    w = window()
    w.load_intrinsics(info["intrinsics"])
    w.load_survey(survey)
    w.load_floor_images([info["floor_image"]])
    w.detect_floor()
    uv = info["camera"].project([[float(rows[3]["x_m"]), float(rows[3]["y_m"]), 0.0]])[0]
    w.floor_table.selectRow(3)
    assert w.selected_point() == rows[3]["ten"]
    w._toggle_click_mode()
    assert w.click_mode
    w._floor_clicked(float(uv[0]) + 30, float(uv[1]), Qt.MouseButton.LeftButton.value)    # chấm nhầm
    w._floor_clicked(0.0, 0.0, Qt.MouseButton.RightButton.value)                          # xóa
    assert rows[3]["ten"] not in w.clicks
    w._floor_clicked(float(uv[0]), float(uv[1]), Qt.MouseButton.LeftButton.value)
    w._floor_key(Qt.Key.Key_Escape.value)
    assert not w.click_mode and w.floor_table.item(3, 3).text() == "chấm tay"
    assert w.fit_floor()
    det = next(d for d in w.fit.detections if d["ten"] == rows[3]["ten"])
    assert det["source"] == "click" and rows[3]["ten"] in w.fit.used and w.fit.ok


def test_extract_tab_runs_in_background_and_saves_reference(window, qapp, tmp_path):
    info = small_set()
    w = window()
    assert w.load_track_video(info["run"]) and w.load_track_floor(floor_fit_path())
    assert w.load_track_markers(info["markers"])
    assert "Đồng hồ: perf_counter" in w.track_inputs.text()
    assert "CHƯA CÓ (T5 sẽ ghi không kiểm được) vì chưa làm TC-1" in w.accuracy_label.text()
    assert w.start_extraction() and not w.btn_start.isEnabled()
    assert pump(qapp, 30.0, lambda: w.extraction is None)
    assert w.track_output is not None, w.message
    assert w._progress["frames"] == 40 and "Khung 40/40 · hợp lệ 100 %" in w.progress_label.text()
    assert len(w.plot.t) == 40 and w.btn_save_track.isEnabled()
    paths = w.save_track(tmp_path / "ref.csv")
    track = read_reference(paths[0])
    assert len(track.samples) == 40 and track.meta.clock == "perf_counter"
    # đóng cửa sổ giữa lúc trích: luồng nền dừng trong ≤ 3 s, không lưu gì
    w2 = window()
    w2.load_track_video(info["run"])
    w2.load_track_floor(floor_fit_path())
    w2.load_track_markers(info["markers"])
    assert w2.start_extraction()
    worker = w2.extraction
    t = time.monotonic()
    w2.close()
    assert time.monotonic() - t < 3.5 and not worker.is_alive()


def test_tc1_tab_computes_and_saves_and_refuses_docs_evidence_for_synthetic(window, qapp, tmp_path):
    info = small_set()
    w = window()
    assert w.load_tc1_markers(info["markers"]) and w.load_tc1_floor(floor_fit_path())
    assert w.load_tc1_poses(info["tc1_poses"]) and w.tc1_table.rowCount() == 10
    for _ in range(7):
        w.tc1_table.selectRow(3)
        w.remove_tc1_row()
    assert w.tc1_table.rowCount() == 3
    w.min_frames_spin.setValue(TC1_MIN_FRAMES)
    assert w.compute_tc1(kind="day")
    assert pump(qapp, 60.0, lambda: w.tc1_worker is None)
    assert w.tc1_report is not None and w.tc1_report.requirements["met"], w.message
    assert w.tc1_table.item(0, 12).text() not in ("", "LOẠI") and "Dùng được cho" in w.tc1_summary.text()
    target = PROJECT / "docs" / "evidence" / "nghiem_thu" / "tham_chieu_tren_cao_ui_thu.json"
    assert w.save_tc1(target) is None and "không được ghi vào" in w.message and not target.exists()
    out = w.save_tc1(tmp_path / "tc1_ngay.json")
    assert out is not None and out.exists()
    saved = w.save_tc1_poses(tmp_path / "bang" / "tc1.csv")
    with saved.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3 and not Path(rows[0]["video"]).is_absolute()          # video ghi tương đối so với bảng
    assert (saved.parent / rows[0]["video"]).exists()


def test_tc1_tab_refuses_failed_floor_and_unmeasured_markers_like_the_cli(window, qapp, tmp_path):
    """Thẻ TC-1 từ chối như lệnh `overhead_ref tc1` (sửa 02/10/2026): khớp mặt sàn chưa đạt, cấu hình marker thật chưa
    đo (số GIẢ ĐỊNH, như configs/tham_chieu/xe_gia_v0.json); không chạy luồng nền nào, không có biên bản để lưu."""
    info = small_set()
    floor = json.loads(floor_fit_path().read_text(encoding="utf-8"))
    floor.update(synthetic=False, ok=False, reasons=["thử: chưa đạt"])
    (tmp_path / "mat_san_chua_dat.json").write_text(json.dumps(floor, ensure_ascii=False), encoding="utf-8")
    floor.update(ok=True, reasons=[])
    (tmp_path / "mat_san_that.json").write_text(json.dumps(floor, ensure_ascii=False), encoding="utf-8")
    car = json.loads(Path(info["markers"]).read_text(encoding="utf-8"))
    car.update(synthetic=False, measured=False)
    (tmp_path / "xe_gia_v0.json").write_text(json.dumps(car, ensure_ascii=False), encoding="utf-8")
    w = window()
    assert w.load_tc1_markers(tmp_path / "xe_gia_v0.json") and w.load_tc1_floor(tmp_path / "mat_san_chua_dat.json")
    assert w.load_tc1_poses(info["tc1_poses"])
    w.min_frames_spin.setValue(TC1_MIN_FRAMES)
    assert not w.compute_tc1(kind="day") and "khớp lại trước TC-1" in w.message and w.tc1_worker is None
    assert w.load_tc1_floor(tmp_path / "mat_san_that.json")
    assert not w.compute_tc1(kind="day") and "measured: false" in w.message and w.tc1_worker is None
    assert w.tc1_report is None and w.save_tc1(tmp_path / "gui_tc1.json") is None
    assert not (tmp_path / "gui_tc1.json").exists()


def test_extract_tab_refuses_nominal_fps_avi_unless_ticked_and_bad_sync_error(window, qapp, tmp_path):
    """AVI không kèm tệp của bộ ghi: thẻ trích từ chối như dòng lệnh, trừ khi đánh dấu ô 'số khung/s danh định' (như
    --allow-nominal-fps); sai số đồng bộ âm hay nan bị từ chối trước khi chạy luồng nền (sửa 02/10/2026)."""
    info = small_set()
    bare = tmp_path / "quay_tay.avi"
    shutil.copy2(info["run"], bare)
    w = window()
    assert w.load_track_floor(floor_fit_path()) and w.load_track_markers(info["markers"])
    assert not w.load_track_video(bare) and w.video is None
    assert "--allow-nominal-fps" in w.message and "số khung/s danh định" in w.message
    w.chk_nominal_fps.setChecked(True)                                   # nạp lại video theo luật mới
    assert w.video is not None and w.video.clock == "video" and "Đồng hồ: video" in w.track_inputs.text()
    w.chk_nominal_fps.setChecked(False)
    assert w.video is None and not w.start_extraction()
    assert w.load_track_video(info["run"])                               # video của bộ ghi: perf_counter
    for text in ("-0,1", "nan", "inf"):
        w.sync_error_edit.setText(text)
        assert not w.start_extraction() and "hữu hạn ≥ 0" in w.message and w.extraction is None, text


def test_build_window_preloads_inputs_and_rejects_bad_arguments(qapp, monkeypatch):
    from autopark.ui import overhead_app

    made = []
    monkeypatch.setattr(overhead_app, "index_camera_factory",            # chắc chắn không mở camera thật nào
                        lambda index, source_id: made.append((index, source_id)) or (lambda *a: None))
    info = small_set()
    w = overhead_app.build_window(["--intrinsics", info["intrinsics"], "--survey", info["survey"], "--floor",
                                   str(floor_fit_path()), "--markers", info["markers"], "--video", info["run"]])
    try:
        assert w.intr is not None and w.survey is not None and w.track_fit is not None and w.tc1_floor is not None
        assert w.track_car is not None and w.tc1_car is not None and w.video is not None and w.open_camera_factory is None
        assert "Chưa chọn camera" in w.camera_info.text()
    finally:
        w.close()
    w = overhead_app.build_window(["--index", "3", "--camera-name", "tren_cao_2"])
    try:
        assert made == [(3, "cam_tren_cao_2")] and w.camera is None and w.btn_open_cam.isEnabled()
    finally:
        w.close()
    for argv in (["--index", "-1"], ["--camera-name", "p1"], ["--size", "abc"]):
        with pytest.raises(SystemExit) as exc:
            overhead_app.build_window(argv)
        assert exc.value.code == 2


class FakeCamera:
    buffer_size_applied = True

    def __init__(self, image):
        self.image, self.n, self.closed = image, 0, False
        self.stamps = camera_stamps(100000, 50000.0)

    def read(self):
        time.sleep(0.01)
        self.n += 1
        return _frame("cam_tren_cao", self.stamps[self.n], f"gia#{self.n}", self.image)

    def mode(self):
        return {"width": self.image.shape[1], "height": self.image.shape[0]}

    def close(self):
        self.closed = True


def test_record_tab_never_opens_a_camera_until_asked(window, qapp, tmp_path, monkeypatch):
    info = small_set()
    opened = []
    image = cv2.imread(info["floor_image"])

    def factory(port, width, height):
        cam = FakeCamera(image)
        opened.append((port, width, height, cam))
        return cam

    w = window(factory)
    pump(qapp, 0.3, lambda: False)
    assert opened == [] and w.btn_open_cam.isEnabled() and not w.btn_rec.isEnabled()
    assert w.open_camera()
    assert pump(qapp, 5.0, lambda: w.camera is not None and w.camera.latest() is not None)
    assert opened[0][:3] == (None, 960, 540)
    w.refresh()
    assert not w.btn_open_cam.isEnabled() and w.btn_close_cam.isEnabled() and w.btn_rec.isEnabled()
    w.load_track_floor(floor_fit_path())
    assert pump(qapp, 3.0, lambda: "Camera lệch so với lúc khớp" in w.camera_info.text())
    assert w.capture_floor_frames(3)                                    # "Chụp từ camera": sàn trống cho thẻ 1
    assert pump(qapp, 5.0, lambda: w._capture is None and len(w.floor_frames) == 3)
    assert len(list((tmp_path / "runs").rglob("khung_*.png"))) == 3 and "3 khung chụp" in w.floor_source
    # EcoQoS: main() áp chính sách lúc mở ứng dụng (off); về sau trạng thái đổi (vd. Efficiency mode) → tệp ghi phải
    # mang trạng thái đọc LÚC GHI, chính sách lúc khởi động để riêng (sửa 02/10/2026)
    w.ecoqos_policy = {"request": "disable", "set_ok": True, "after": "off"}
    monkeypatch.setattr(pt, "execution_speed_throttling", lambda pid=None: "on")
    assert w.start_recording(tmp_path / "ghi", "lan_ui")
    assert not w.btn_rec.isEnabled() and w.btn_rec_stop.isEnabled()
    assert pump(qapp, 5.0, lambda: w.recorder is not None and w.recorder.frames >= 5)
    meta = w.stop_recording()
    assert meta["status"] == "xong" and meta["frames"] >= 5 and (tmp_path / "ghi" / "lan_ui.avi").exists()
    saved = json.loads((tmp_path / "ghi" / "lan_ui.json").read_text(encoding="utf-8"))
    assert saved["ecoqos"] == "on" and saved["ecoqos_start"] == "on" and saved["ecoqos_policy"]["after"] == "off"
    assert w.btn_rec.isEnabled() and not w.btn_rec_stop.isEnabled()
    assert not w.start_recording(tmp_path / "ghi", "lan_ui") and "--overwrite" in w.message   # không ghi đè tên đã có
    video = R.OverheadVideo(tmp_path / "ghi" / "lan_ui.avi")
    assert video.clock == "perf_counter" and len(video) == meta["frames"]
    w.close_camera()
    assert opened[0][3].closed and len(opened) == 1 and w.btn_open_cam.isEnabled()
    plain = window()
    assert not plain.open_camera() and "--index" in plain.message and not plain.btn_open_cam.isEnabled()
