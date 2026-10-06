"""Ngăn "Ghi cảm biến" của `ui.lidar_app` (T3, 02/10/2026), offscreen và không phần cứng: serial.Serial,
serial.serial_for_url và cv2.VideoCapture bị thay bằng hàm từ chối; camera giả qua Rig của ngăn AI camera, LiDAR giả
(`DockFakeLidar`) qua luồng đọc thật của ngăn LiDAR; `run_store.environment` không gọi PowerShell; dung lượng đĩa giả.

Kiểm: ngăn xếp thẻ cạnh ngăn LiDAR và chỉ cho bắt đầu khi có nguồn; một thư mục giữ camera của ngăn AI camera, LiDAR của
ngăn LiDAR, mốc đồng hồ và lô AI; "Bắt đầu ghi" khóa khi xe chạy còn "Dừng ghi" thì không (và không chặn); lần chạy
trong bản ghi có mốc ghép thời gian phiên, bản sao dấu đồng bộ, tệp trỏ khi xuất log, và không thêm dòng nào vào dấu đồng
bộ của cửa sổ; đồng hồ VehicleIO thời gian thực; nguồn tắt giữa chừng; đóng cửa sổ; dòng lệnh sai."""
import csv
import hashlib
import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from autopark.application.session import SessionState  # noqa: E402
from autopark.application.vehicle_link import DriveMode  # noqa: E402
from autopark.evaluation.sync_marks import CLOCK, SYNC_MARK, read_sync_marks  # noqa: E402
from autopark.perception.paths import PROJECT  # noqa: E402
from autopark.rig.core import Rig, RigConfig  # noqa: E402
from autopark.rig.replay import ReplaySession, load_lidar  # noqa: E402
from autopark.rig.session_recording import (AI_TABLE, CLOCK_TABLE, GB, SYNC_COPY, RecordOptions,  # noqa: E402
                                            RecordStartError, read_session_clock)
from autopark.storage import run_store  # noqa: E402
from autopark.ui import lidar_app, theme  # noqa: E402
from autopark.ui.lidar_app import build_window  # noqa: E402
from autopark.ui.record_dock import LOCKED_WHILE_DRIVING, NO_SOURCE, NOT_IGNORED, status_lines  # noqa: E402
from tests.rig_fakes import DockFakeLidar, FakeSegmenter, fake_manager  # noqa: E402
from tests.test_lidar_dock_ui import FakeSource  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def no_devices(monkeypatch):
    """Không cổng COM, không camera thật, không PowerShell."""
    import serial

    def refuse(*args, **kwargs):
        raise AssertionError("test không được mở thiết bị thật")
    monkeypatch.setattr(serial, "Serial", refuse)
    monkeypatch.setattr(serial, "serial_for_url", refuse)
    monkeypatch.setattr(cv2, "VideoCapture", refuse)
    monkeypatch.setattr(run_store, "environment", lambda: {"stub": True})


def open_window(tmp_path, *, camera=False, free=100 * GB):
    """Cửa sổ ui.lidar_app có ngăn ghi, mọi timer dừng (test tự gọi nhịp), bản ghi vào tmp_path, đĩa giả."""
    options = RecordOptions(root=tmp_path / "ghi", image_format="png")
    window, dock = build_window(None, port="COM_GIA", recording=None, camera_ai={"ports": (1,)} if camera else None,
                                record=options)
    window._timer.stop()
    dock.timer.stop()
    window.record_dock.timer.stop()
    if window.camera_dock is not None:
        window.camera_dock.timer.stop()
    window.sync_dir = tmp_path / "sync"
    window.sync_marker.min_gap_s = 0.0
    window.sensor_recording.free_bytes = lambda path: free
    window.record_dock.refresh()
    return window, dock, window.record_dock


def fake_rig():
    return Rig(fake_manager(ports=(1,), period=0.03), RigConfig(checkpoint="gia.pt"),
               make_segmenter=lambda path: FakeSegmenter(path, delay=0.002))


def pump(window, seconds, *, advance=0.0, until=None, poll_every=0.25):
    """Như các timer: nhịp ngăn LiDAR / AI camera, tiến mô phỏng (`advance` giây mỗi nhịp), đổi trạng thái, kiểm bản ghi."""
    deadline = time.perf_counter() + seconds
    next_poll = 0.0
    while time.perf_counter() < deadline:
        window.dock.tick()
        if window.camera_dock is not None:
            window.camera_dock.tick()
        if advance:
            window.advance_by(advance)
        window._poll_state_change()
        if time.perf_counter() >= next_poll:
            window.record_dock.poll_once()
            next_poll = time.perf_counter() + poll_every
        if until is not None and until():
            return True
        time.sleep(0.02)
    return until is None


def drive_to_rest(window, dt=0.1, steps=600):
    for _ in range(steps):
        window.advance_by(dt)
        window._poll_state_change()
        if not window.session.simulating:
            return


def rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def log_lines(dock):
    return [dock.log.item(k).text() for k in range(dock.log.count())]


# ------------------------------------------------------------------------------------------------ ngăn, nguồn

def test_record_dock_is_tabbed_and_start_needs_a_source(qapp, tmp_path, no_devices):
    window, dock, rd = open_window(tmp_path)
    try:
        assert rd.objectName() == "sensorRecordDock" and window.tabifiedDockWidgets(dock) == [rd]
        assert not rd.btn_record.isEnabled() and rd.btn_record.toolTip() == NO_SOURCE
        assert not rd.chk_cameras.isEnabled() and "không có ngăn AI camera" in rd.chk_cameras.toolTip()
        assert not rd.chk_lidar.isEnabled() and "LiDAR chưa kết nối" in rd.chk_lidar.toolTip()
        assert rd.badge.isHidden() and window.header.layout().indexOf(rd.badge) == \
            window.header.layout().indexOf(window.sync_action) - 1   # ngay trước nút dấu đồng bộ
        assert rd.lbl_status.text() == f"Chưa ghi. {NO_SOURCE}. Ổ {rd.recorder.status()['drive'][2:]}: còn 100,0 GB."
        dock.attach_source(FakeSource(), start_thread=False)          # nguồn không cùng đồng hồ: vẫn không ghi được
        rd.refresh()
        assert not rd.btn_record.isEnabled() and "perf_counter" in rd.chk_lidar.toolTip()
        dock.disconnect_source()
        dock.attach_source(DockFakeLidar(), start_thread=False)
        rd.refresh()
        assert rd.btn_record.isEnabled() and rd.chk_lidar.isEnabled() and rd.btn_record.text() == "Bắt đầu ghi"
        assert "Sẽ ghi: LiDAR dock_fake_lidar" in rd.lbl_status.text()
        rd.chk_lidar.setChecked(False)                                 # bỏ chọn nguồn duy nhất
        assert not rd.btn_record.isEnabled() and "Chọn ít nhất một nguồn" in rd.btn_record.toolTip()
        rd.chk_lidar.setChecked(True)
        rd.edit_root.setText(str(PROJECT / "docs" / "ghi_thu"))       # trong kho git, ngoài runs/
        assert rd.lbl_root_warning.text() == NOT_IGNORED
        rd.edit_root.setText(str(PROJECT / "runs" / "session_recordings"))
        assert rd.lbl_root_warning.text() == ""
        rd.edit_root.setText(str(tmp_path / "ghi"))
    finally:
        dock.shutdown()
        window.close()


def test_status_lines_say_what_is_recorded_and_what_went_wrong():
    st = {"state": "recording", "drive": "ổ D", "free_gb": 58.04, "minutes_left": 190.2, "elapsed_s": 42.4,
          "cameras": True, "cam_attached": True, "ports": [1, 2, 3, 4], "frames_total": 4040, "dropped_total": 0,
          "lidar": True, "lidar_attached": True, "lidar_scans": 420, "mb_written": 210.3, "mb_per_s": 5.0,
          "pending_frames": 3}
    [(text, tone)] = status_lines(st)
    assert text == ("ĐANG GHI 00:42 · camera 4 cổng, 4.040 khung (bỏ 0) · LiDAR 420 vòng · 210 MB, 5,0 MB/s · "
                    "chờ ghi 3 khung · ổ còn 58,0 GB ≈ 190 phút") and tone == theme.ACCENT
    assert status_lines({"state": "draining", "pending_frames": 120})[0][0] == "ĐANG GHI NỐT: còn 120 khung chờ ghi"
    done = status_lines({"state": "done", "folder": "runs/session_recordings/x", "elapsed_s": 123.0,
                         "frames_total": 12100, "lidar_scans": 1230, "mb_written": 610.2, "dropped_total": 37,
                         "replay": True, "synthetic": True, "stopped_by": "disk_guard"})
    assert done[0] == ("XONG: runs/session_recordings/x · 2 phút 03 s · 12.100 khung · 1.230 vòng LiDAR · 610 MB",
                       theme.OK)
    assert ("GHI THIẾU: hàng đợi ghi đầy (đĩa chậm?), 37 khung bị bỏ", theme.WARN) in done
    assert ("GHI LẠI TỪ BẢN GHI PHÁT LẠI", theme.WARN) in done and ("RIG TỔNG HỢP", theme.WARN) in done
    assert ("Đã tự dừng: disk_guard", theme.WARN) in done
    assert status_lines({"state": "error", "error": "ghi khung: OSError"})[0] == ("LỖI GHI: ghi khung: OSError", theme.DANGER)
    assert status_lines({"state": "idle", "drive": "ổ D", "free_gb": 58.24}, "camera 1 2 3 4 · LiDAR COM3")[0][0] == \
        "Chưa ghi. Sẽ ghi: camera 1 2 3 4 · LiDAR COM3. Ổ D: còn 58,2 GB."


def test_one_folder_holds_the_camera_dock_and_the_lidar_dock(qapp, tmp_path, no_devices):
    window, dock, rd = open_window(tmp_path, camera=True)
    cam = window.camera_dock
    source = DockFakeLidar(period=0.05)
    try:
        cam.attach_rig(fake_rig(), "fake")
        dock.attach_source(source)                                     # luồng đọc thật của ngăn LiDAR
        assert pump(window, 5.0, until=lambda: dock.scans >= 2 and cam.mapper is not None and cam.mapper.batches >= 2)
        rd.refresh()
        assert rd.btn_record.isEnabled() and "Sẽ ghi: camera 1 · LiDAR dock_fake_lidar" in rd.lbl_status.text()
        rd.btn_record.click()
        recorder = window.sensor_recording
        assert recorder.active and rd.btn_record.text() == "Dừng ghi" and not rd.badge.isHidden()
        assert not rd.edit_root.isEnabled() and not rd.chk_cameras.isEnabled()      # cài đặt khóa khi đang ghi
        pump(window, 1.3)
        assert "ĐANG GHI" in rd.lbl_status.text() and "camera 1 cổng" in rd.lbl_status.text()
        rd.btn_record.click()
        assert not recorder.active and rd.badge.isHidden()
        assert recorder.wait_finished(20.0)
        rd.poll_once()
        assert "XONG: " in rd.lbl_status.text() and any(t.startswith("XONG: ") for t in log_lines(rd))
    finally:
        dock.shutdown()
        cam.shutdown()
        window.close()
    folder = recorder.rec.folder
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    sr = meta["session_recording"]
    assert meta["status"] == "xong" and sr["sources"]["cameras"]["on"] and sr["sources"]["lidar"]["on"]
    assert sr["sources"]["cameras"]["kind"] == "fake" and sr["camera_ai"]["ports"] == [1]
    assert sr["lidar_dock"]["window"] == 3 and sr["session"]["board"] == "sim" and sr["stopped_by"] == "user"
    assert len(rows(folder / "cam_p1" / "frames.csv")) > 10
    lidar, _ = load_lidar(folder)
    assert len(lidar) >= 8 and meta["lidar"]["parts"]
    triggers = [a["trigger"] for a in rows(folder / CLOCK_TABLE)]
    assert triggers[0] == "start" and "periodic" in triggers and triggers[-1] == "stop"
    ai = rows(folder / AI_TABLE)
    ids = [int(r["batch_id"]) for r in ai]
    assert len(ai) >= 3 and ids == sorted(set(ids)) and all(r["state"] == "EDITING" for r in ai)
    assert sr["ai"]["rows"] == len(ai)
    session = ReplaySession(folder)                                    # camera và LiDAR cùng một đồng hồ
    assert session.ports == [1] and session.has_lidar and session.duration_s < 4.0


# ------------------------------------------------------------------------------------------------ khi xe chạy

def test_start_is_locked_while_driving_and_stop_is_not(qapp, tmp_path, no_devices):
    window, dock, rd = open_window(tmp_path)
    source = DockFakeLidar(period=0.05)
    recorder = window.sensor_recording
    try:
        dock.attach_source(source)
        assert pump(window, 3.0, until=lambda: dock.scans >= 2)
        rd.btn_record.click()
        assert recorder.active
        assert window.plan(sync=True).ok
        pump(window, 0.2)
        window.run()
        assert pump(window, 0.6, advance=0.02, until=lambda: window.session.state == SessionState.RUNNING)
        assert rd.btn_record.text() == "Dừng ghi" and rd.btn_record.isEnabled()      # dừng ghi luôn bấm được
        t = time.perf_counter()
        rd.btn_record.click()                                          # giữa lần chạy: không chặn (đo 1–5 ms offscreen)
        took = time.perf_counter() - t
        assert took < 0.25, took                                       # rộng tay: máy chạy test có thể đang bận
        assert not recorder.active and window.session.state == SessionState.RUNNING
        assert rd.btn_record.text() == "Bắt đầu ghi" and not rd.btn_record.isEnabled()
        assert rd.btn_record.toolTip() == LOCKED_WHILE_DRIVING
        assert recorder.wait_finished(20.0)
        with pytest.raises(RecordStartError, match="Bắt đầu ghi trước Bắt đầu đỗ"):
            recorder.start()                                           # chốt chặn sau nút khóa
        window.stop()
        drive_to_rest(window)
        window.record_dock.refresh()
        assert rd.btn_record.isEnabled()                               # xe đã dừng: ghi lại được
    finally:
        dock.shutdown()
        window.close()
    meta = json.loads((recorder.rec.folder / "meta.json").read_text(encoding="utf-8"))
    [run] = meta["session_recording"]["runs"]
    assert run["run"] == 1 and run["t_perf_start"] is not None and run["t_perf_end"] is None   # lần chạy còn mở
    assert meta["session_recording"]["session"]["state_at_start"] == "EDITING"


def test_a_run_inside_the_recording_is_anchored_and_the_export_points_to_it(qapp, tmp_path, monkeypatch, no_devices):
    window, dock, rd = open_window(tmp_path)
    source = DockFakeLidar(period=0.05)
    recorder = window.sensor_recording
    try:
        dock.attach_source(source)
        assert pump(window, 3.0, until=lambda: dock.scans >= 3)
        assert window.make_sync_mark("key_f8") is not None             # dấu đầu (T14), trước Bắt đầu ghi
        window.sync_flash.finish()
        rd.btn_record.click()
        assert recorder.active
        pump(window, 0.3)
        assert window.plan(sync=True).ok
        pump(window, 0.2)
        window.run()
        window._poll_state_change()                                    # mốc READY→RUNNING trước nhịp mô phỏng đầu
        assert window.session.state == SessionState.RUNNING
        pump(window, 1.1, advance=0.02)                                # có mốc định kỳ trong lần chạy
        assert window.session.state == SessionState.RUNNING
        source.obstacle = (0.9, 0.0)                                   # tay trước LiDAR, trên đường đi
        assert pump(window, 3.0, advance=0.02, until=lambda: window.session.state != SessionState.RUNNING)
        assert window.session.state == SessionState.STOPPING and "Vật cản mới" in window.session.stop_reason
        drive_to_rest(window)
        assert window.session.state == SessionState.STOPPED
        assert window.make_sync_mark("key_f8") is not None             # dấu cuối, sau khi xe dừng
        window.sync_flash.finish()
        pump(window, 0.3)
        rd.btn_record.click()
        assert recorder.wait_finished(20.0)
        folder = recorder.rec.folder
        # export: tệp trỏ cạnh CSV và trong gói phát lại (gói không chép bản ghi)
        out = tmp_path / "log" / "lan.csv"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), "CSV (*.csv)"))
        window._export_log()
        assert "(+ trỏ tới 1 bản ghi cảm biến)" in window.statusBar().currentMessage()
    finally:
        dock.shutdown()
        window.close()
    anchors = rows(folder / CLOCK_TABLE)
    changes = [a for a in anchors if a["trigger"] == "state_change"]
    start = next(a for a in changes if a["note"].endswith("READY→RUNNING"))
    stopping = next(a for a in changes if "RUNNING→STOPPING" in a["note"])
    stopped = next(a for a in changes if "STOPPING→STOPPED" in a["note"])
    assert "Vật cản mới" in stopping["note"] and start["run"] == stopping["run"] == stopped["run"] == "1"
    assert float(start["t_session"]) == 0.0 and float(stopped["t_session"]) >= float(stopping["t_session"]) > 0
    assert any(a["trigger"] == "periodic" and a["state"] == "RUNNING" for a in anchors)
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    [run] = meta["session_recording"]["runs"]
    assert run["end_state"] == "STOPPED" and "Vật cản mới" in run["stop_reason"]
    clock = read_session_clock(folder)                                 # vòng quét trong lần chạy → thời gian phiên
    t0, t1 = float(start["t_perf"]), float(stopped["t_perf"])
    lidar, _ = load_lidar(folder)
    inside = [float(t) for t in lidar.t if t0 < t < t1]
    values = [clock.to_session(t) for t in inside]
    assert len(inside) > 10 and all(v is not None and 0.0 <= v <= run["t_session_end"] + 1e-9 for v in values)
    assert values == sorted(values) and clock.to_session(t0 - 0.2) is None
    # bản sao dấu đồng bộ = nhật ký của cửa sổ; bản ghi KHÔNG thêm dòng nào vào nhật ký đó (score_run tách lần chạy ở
    # mỗi dòng CLOCK có state RUNNING)
    assert read_sync_marks(folder / SYNC_COPY) == window.sync_marks.rows
    assert [r["kind"] for r in window.sync_marks.rows] == [SYNC_MARK, CLOCK, CLOCK, CLOCK, SYNC_MARK]
    refs = json.loads((out.parent / "lan_sensor_recordings.json").read_text(encoding="utf-8"))
    [ref] = refs["recordings"]
    assert refs["format"] == "autopark.sensor_recording_refs" and refs["run"]["end_state"] == "STOPPED"
    assert ref["folder"] == str(folder) and ref["status"] == "xong" and ref["covers_run"] is True
    assert ref["meta_sha256"] == hashlib.sha256((folder / "meta.json").read_bytes()).hexdigest()
    [bundle] = [p for p in out.parent.iterdir() if p.is_dir() and p.name.startswith("lan_")]
    assert json.loads((bundle / "sensor_recordings.json").read_text(encoding="utf-8")) == refs
    assert not list(bundle.rglob("*.png")) and not list(bundle.rglob("part_*.npz"))   # bản ghi không vào gói T9


def test_vehicle_io_anchors_keep_a_constant_perf_minus_io_offset(qapp, tmp_path, monkeypatch, no_devices):
    import serial
    opened = []

    def refuse(*args, **kwargs):
        opened.append(args)
        raise AssertionError("test không được mở cổng thật")
    monkeypatch.setattr(serial, "Serial", refuse)
    window, dock, rd = open_window(tmp_path)
    source = DockFakeLidar(period=0.05)
    recorder = window.sensor_recording
    try:
        combo = window.combo_drive
        combo.setCurrentIndex(combo.findData(DriveMode.VEHICLE_IO.value))
        window.combo_port.addItem("COM_BO_GIA — cổng giả", "COM_BO_GIA")    # bo thật (khác cổng LiDAR COM_GIA)
        window.combo_port.setCurrentIndex(window.combo_port.findData("COM_BO_GIA"))
        link = window.session.vehicle_link
        assert link.io.port == "COM_BO_GIA" and link.io.transport is None and link.realtime
        dock.attach_source(source)
        assert pump(window, 3.0, until=lambda: dock.scans >= 2)
        rd.btn_record.click()
        pump(window, 1.3)
        rd.btn_record.click()
        assert recorder.wait_finished(20.0)
    finally:
        dock.shutdown()
        window.close()
    anchors = rows(recorder.rec.folder / CLOCK_TABLE)
    assert len(anchors) >= 3 and all(a["io_clock"] == "realtime" and a["t_io"] for a in anchors)
    assert all(a["note"].startswith("VEHICLE_IO, cổng COM_BO_GIA") and a["time_scale"] == "1.0" for a in anchors)
    offsets = [float(a["t_perf"]) - float(a["t_io"]) for a in anchors]
    assert max(offsets) - min(offsets) < 1e-3
    assert read_session_clock(recorder.rec.folder).realtime_offset() == pytest.approx(offsets[0], abs=1e-3)
    meta = json.loads((recorder.rec.folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["session_recording"]["session"]["board"] == "COM_BO_GIA"
    assert meta["session_recording"]["session"]["drive_mode"] == "VEHICLE_IO"
    assert opened == [] and link.io.transport is None


# ------------------------------------------------------------------------------------------------ nguồn tắt, đóng cửa sổ

def test_turning_sources_off_mid_recording_is_logged_and_the_last_one_stops_it(qapp, tmp_path, no_devices):
    window, dock, rd = open_window(tmp_path, camera=True)
    cam = window.camera_dock
    source = DockFakeLidar(period=0.05)
    recorder = window.sensor_recording
    try:
        cam.attach_rig(fake_rig(), "fake")
        dock.attach_source(source)
        assert pump(window, 5.0, until=lambda: dock.scans >= 2 and cam.mapper is not None and cam.mapper.batches >= 1)
        rd.btn_record.click()
        pump(window, 0.5)
        cam.btn_start.click()                                          # "Tắt AI camera"
        assert cam.rig is None and recorder.active
        pump(window, 0.3)
        assert any(t.startswith("Camera rời bản ghi") for t in log_lines(rd))
        assert "camera đã rời" in rd.lbl_status.text()
        cam.attach_rig(fake_rig(), "fake")                             # bật lại: Rig mới KHÔNG được gắn lại
        pump(window, 0.3)
        assert any("AI camera bật sau khi bắt đầu ghi: không vào bản ghi này" in t for t in log_lines(rd))
        assert recorder.active
        dock.btn_connect.click()                                       # "Ngắt" LiDAR: không còn nguồn nào
        pump(window, 0.3)
        lines = log_lines(rd)
        assert any("LiDAR rời bản ghi" in t for t in lines) and any("Không còn nguồn" in t for t in lines)
        assert not recorder.active and recorder.wait_finished(20.0)
    finally:
        dock.shutdown()
        cam.shutdown()
        window.close()
    meta = json.loads((recorder.rec.folder / "meta.json").read_text(encoding="utf-8"))
    sr = meta["session_recording"]
    assert meta["status"] == "xong" and sr["stopped_by"] == "no_sources"
    assert [d["source"] for d in sr["detached"]] == ["cameras", "lidar"]
    assert [d["source"] for d in sr["ignored_late"]] == ["cameras"]
    assert meta["cameras_at_stop"][0]["port"] == 1 and meta["cameras_at_stop"][0]["frames"] > 3
    triggers = [a["trigger"] for a in rows(recorder.rec.folder / CLOCK_TABLE)]
    assert "camera_detached" in triggers and "lidar_detached" in triggers


def test_closing_the_window_stops_and_waits_for_the_recording(qapp, tmp_path, no_devices):
    window, dock, rd = open_window(tmp_path)
    source = DockFakeLidar(period=0.05)
    recorder = window.sensor_recording
    dock.attach_source(source)
    assert pump(window, 3.0, until=lambda: dock.scans >= 2)
    rd.btn_record.click()
    pump(window, 0.4)
    rec = recorder.rec
    window.close()                                                     # dừng ghi, tắt nguồn, chờ ghi nốt
    assert rec.finished.is_set() and source.closed and rd.badge.isHidden()
    meta = json.loads((rec.folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "xong" and meta["session_recording"]["stopped_by"] == "window_closed"
    assert meta["lidar"]["scans"] > 0


def test_cli_rejects_bad_record_options_before_opening_a_window(tmp_path, monkeypatch, capsys):
    def no_window(*args, **kwargs):
        raise AssertionError("đã mở cửa sổ dù tùy chọn ghi sai")
    monkeypatch.setattr(lidar_app, "build_window", no_window)
    a_file = tmp_path / "tệp.txt"
    a_file.write_text("x", encoding="utf-8")
    for argv, needle in ((["--jpeg-quality", "0"], "1..100"), (["--record-min-free-gb", "1"], "ngưỡng tự dừng"),
                         (["--record-root", str(a_file)], "là một tệp"), (["--record-format", "bmp"], "--record-format")):
        with pytest.raises(SystemExit) as info:
            lidar_app.main(argv)
        assert info.value.code == 2 and needle in capsys.readouterr().err, argv
    parser = lidar_app.argparse.ArgumentParser()
    lidar_app.add_record_args(parser)
    options = lidar_app.record_options(parser, parser.parse_args(
        ["--record-root", str(tmp_path / "gốc"), "--record-format", "png", "--jpeg-quality", "80",
         "--record-min-free-gb", "7.5"]))
    assert options == RecordOptions(root=tmp_path / "gốc", image_format="png", jpeg_quality=80, min_free_gb=7.5)
    default = lidar_app.record_options(parser, parser.parse_args([]))
    assert default.root == PROJECT / "runs" / "session_recordings" and default.image_format == "jpg"
