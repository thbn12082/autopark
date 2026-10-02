"""Dấu đồng bộ video–log (T14, thêm 02/10/2026): nhật ký SYNC_MARK/CLOCK, ô nháy, nút/phím F8 của cockpit (`ui.app`,
`ui.lidar_app`), `rig.bench --sync-mark/--sync-every/--sync-screen` và nút F8 của `ui.rig_app`. Sửa sau review cùng ngày:
cột `time_scale` và khóa "tốc độ chạy" khi xe chạy, tệp sống tự ghi lại đủ sau lỗi ghi, Bắt đầu đỗ chờ ô nháy tắt, thanh
trạng thái có từ đầu, tệp rỗng của `rig.bench` bị xóa, ValueError của `build_rig` thành lỗi dòng lệnh.

Không phần cứng: không mở cổng COM nào (`serial.Serial`/`serial_for_url` bị thay bằng hàm từ chối), không camera thật
(camera giả của tests/rig_fakes.py, LiDAR giả của tests/test_lidar_dock_ui.py), không cửa sổ thật (offscreen). Độ trễ
hiển thị của màn hình thật và hành vi cửa sổ trên Windows thật KHÔNG được kiểm ở đây."""
import contextlib
from datetime import datetime
import csv
import json
import os
import sys
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QLineEdit, QMainWindow, QStatusBar, QWidget  # noqa: E402

from autopark.application.session import SessionState  # noqa: E402
from autopark.application.vehicle_link import DriveMode  # noqa: E402
from autopark.evaluation.sync_marks import (CLOCK, SYNC_FIELDS, SYNC_MARK, SyncMarkLog, read_sync_marks,  # noqa: E402
                                            sync_file_path)
from autopark.ui import sync_flash  # noqa: E402
from autopark.ui.sync_flash import SyncFlash, SyncMarker, disable_window_transitions  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def stub_environment(monkeypatch):
    """export_run gọi PowerShell (hạn 15 s) để đọc phần cứng: thay bằng hàm rỗng cho test nhanh."""
    from autopark.storage import run_store
    monkeypatch.setattr(run_store, "environment", lambda: {"stub": True})


def f8() -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F8, Qt.KeyboardModifier.NoModifier)


class FakeFlash:
    """Ô nháy giả: ghi lại lần hiện và số lần đồng hồ đã được đọc lúc đó."""

    def __init__(self, reads: list | None = None):
        self.on = False
        self.shown = []
        self.reads = reads if reads is not None else []

    def show_mark(self, number, duration_ms):
        self.on = True
        self.shown.append((number, duration_ms, len(self.reads)))

    def lit(self):
        return self.on

    def finish(self):
        self.on = False


# ---- nhật ký ------------------------------------------------------------------------------------------------------
def test_sync_log_buffers_rows_until_the_file_opens_then_appends_each_row(tmp_path):
    log = SyncMarkLog("ui.app")
    c1 = log.add(CLOCK, 10.0, trigger="state_change", state="RUNNING", t_session=0.0, note="READY→RUNNING")
    assert c1["n"] == "" and log.marks == 0 and log.path is None and c1["source"] == "ui.app"
    m1 = log.add(SYNC_MARK, 11.1234567, trigger="button", t_io=None)
    assert m1["n"] == 1 and m1["t_perf"] == 11.123457 and m1["t_io"] == "" and log.marks == 1
    assert datetime.fromisoformat(m1["t_wall"]) and len(m1["t_wall"].split(".")[1]) == 3     # mili giây
    path = tmp_path / "con" / "dau.csv"
    assert log.open(path) == path and log.path == path                  # thư mục cha được tạo
    with path.open(encoding="utf-8", newline="") as f:
        assert next(csv.reader(f)) == SYNC_FIELDS
    assert [(r["kind"], r["n"]) for r in read_sync_marks(path)] == [(CLOCK, ""), (SYNC_MARK, 1)]
    m2 = log.add(SYNC_MARK, 12.0, trigger="key_f8")
    on_disk = read_sync_marks(path)                                     # có trên đĩa ngay, trước khi đóng gì
    assert m2["n"] == 2 and log.last_write_ok is True and len(on_disk) == 3 and on_disk[-1]["t_perf"] == 12.0
    c2 = log.add(CLOCK, 12.5, trigger="state_change")
    assert c2["n"] == "" and log.marks == 2 and len(read_sync_marks(path)) == 4
    assert read_sync_marks(path) == log.rows
    for bad in ({"khong_co": 1}, {"n": 5}, {"source": "x"}, {"t_wall": "x"}):
        with pytest.raises(ValueError):
            log.add(SYNC_MARK, 13.0, **bad)
    with pytest.raises(ValueError):
        log.add("MARK", 13.0)
    assert len(log.rows) == 4 and log.marks == 2 and len(read_sync_marks(path)) == 4   # dòng sai không được thêm

    other = SyncMarkLog("ui.app")
    other.add(SYNC_MARK, 1.0)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):                                # không bao giờ ghi đè tệp của phiên khác
        other.open(path)
    assert path.read_bytes() == before and other.path is None and other.rows

    name = sync_file_path(tmp_path, "ui.lidar_app", now=datetime(2026, 10, 2, 9, 5, 7, 123456))
    assert name == tmp_path / "20261002_090507_123_ui_lidar_app.csv"


def test_sync_log_never_loses_rows_when_the_disk_fails(tmp_path):
    log = SyncMarkLog("rig.bench", tmp_path / "dau.csv")                # có đường dẫn: tạo tệp và tiêu đề ngay
    assert log.path.exists() and read_sync_marks(log.path) == []
    log.add(SYNC_MARK, 1.5, trigger="auto_start", t_rig_s=0.0123, flash_ms=500, paint_ms=1.25, note="phiên x")
    assert log.last_write_ok is True and log.error is None and log.failed_writes == 0
    folder = tmp_path / "thư mục"
    folder.mkdir()
    log.path = folder                                                   # nối vào một thư mục: OSError
    row = log.add(SYNC_MARK, 2.75, trigger="console_key", t_rig_s=1.2623)
    assert row is log.rows[-1] and len(log.rows) == 2 and log.marks == 2 and row["n"] == 2
    assert log.last_write_ok is False and log.failed_writes == 1 and "Error" in log.error
    copy = log.write_csv(tmp_path / "xuất" / "bản đủ.csv")
    back = read_sync_marks(copy)
    assert back == log.rows
    assert isinstance(back[0]["n"], int) and isinstance(back[0]["flash_ms"], int) and back[0]["flash_ms"] == 500
    assert back[0]["t_perf"] == 1.5 and back[0]["paint_ms"] == 1.25 and back[1]["t_rig_s"] == 1.2623
    assert back[1]["t_session"] == "" and back[1]["flash_ms"] == "" and back[0]["note"] == "phiên x"

    # không tạo được tệp sống (đã có): vẫn nháy, dấu vẫn ở bộ nhớ, lỗi nói rõ
    flash = FakeFlash()
    marker = SyncMarker(SyncMarkLog("ui.app"), flash, open_file=lambda: tmp_path / "dau.csv")
    row = marker.mark("button")
    assert row["n"] == 1 and flash.shown and marker.log.path is None
    assert "không tạo được tệp dấu đồng bộ" in marker.log.error and "FileExistsError" in marker.log.error


def test_live_file_is_rewritten_whole_at_the_first_write_that_works_again(tmp_path):
    """Sửa 02/10/2026: lần nối hỏng để lại lỗ trong tệp sống; lần ghi được sau đó ghi lại cả tệp từ bộ nhớ."""
    log = SyncMarkLog("ui.app", tmp_path / "song.csv")
    real = log.path
    log.add(SYNC_MARK, 1.0, trigger="key_f8")
    assert log.unwritten == 0 and log.flush() is True                   # không thiếu gì: flush không ghi gì
    blocked = tmp_path / "khoa"
    blocked.mkdir()
    log.path = blocked                                                  # như tệp bị khóa: mọi lần ghi lỗi
    log.add(CLOCK, 2.0, trigger="state_change", note="READY→RUNNING")
    log.add(CLOCK, 3.0, trigger="state_change", note="RUNNING→STOPPED")
    assert log.unwritten == 2 and log.last_write_ok is False and log.failed_writes == 2
    assert log.flush() is False and log.unwritten == 2 and log.failed_writes == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == ["khoa", "song.csv"]     # tệp tạm đã dọn
    log.path = real                                                     # hết khóa
    assert len(read_sync_marks(real)) == 1                              # tệp sống đang thiếu hai dòng CLOCK
    log.add(SYNC_MARK, 4.0, trigger="key_f8")
    assert log.unwritten == 0 and log.last_write_ok is True and log.error is not None   # lỗi cũ vẫn giữ để báo
    assert read_sync_marks(real) == log.rows and len(log.rows) == 4     # đủ, đúng thứ tự
    log.add(CLOCK, 5.0, trigger="state_change")                         # từ đây lại nối từng dòng
    assert read_sync_marks(real) == log.rows
    log.path = blocked
    log.add(CLOCK, 6.0, trigger="state_change")
    log.path = real
    assert log.flush() is True and log.unwritten == 0 and read_sync_marks(real) == log.rows   # đóng cửa sổ: flush
    assert SyncMarkLog("ui.app").flush() is False                       # chưa có tệp sống


def test_time_scale_is_the_last_column_and_old_files_still_read(tmp_path):
    """Cột time_scale (thêm 02/10/2026, hợp đồng với T5): cột cuối; tệp ghi trước đó (14 cột) vẫn đọc được."""
    assert SYNC_FIELDS[-1] == "time_scale" and SYNC_FIELDS[:14] == [
        "n", "kind", "t_perf", "t_wall", "source", "trigger", "state", "t_session", "t_io", "io_clock", "t_rig_s",
        "flash_ms", "paint_ms", "note"]
    log = SyncMarkLog("ui.app", tmp_path / "moi.csv")
    log.add(CLOCK, 1.5, trigger="state_change", t_session=0.04, time_scale=2.0)
    assert read_sync_marks(log.path)[0]["time_scale"] == 2.0 and read_sync_marks(log.path) == log.rows
    old = tmp_path / "cu.csv"
    old.write_text("n,kind,t_perf,t_wall,source,trigger,state,t_session,t_io,io_clock,t_rig_s,flash_ms,paint_ms,note\n"
                   "1,SYNC_MARK,12.5,2026-10-01T10:00:00.000,ui.app,key_f8,READY,,,,,500,1.25,SIM\n"
                   ",CLOCK,13.0,2026-10-01T10:00:00.500,ui.app,state_change,RUNNING,0.0\n", encoding="utf-8")
    mark, clock = read_sync_marks(old)
    assert mark["n"] == 1 and mark["flash_ms"] == 500 and mark["paint_ms"] == 1.25 and mark["time_scale"] == ""
    assert clock["t_session"] == 0.0 and clock["t_io"] == "" and clock["note"] == "" and clock["time_scale"] == ""
    assert set(mark) == set(clock) == set(SYNC_FIELDS)


# ---- ô nháy -------------------------------------------------------------------------------------------------------
def test_flash_overlay_covers_the_host_with_a_numbered_white_square(qapp):
    host = QMainWindow()
    edit = QLineEdit()
    host.setCentralWidget(edit)
    host.statusBar().showMessage("thanh trạng thái")
    host.resize(640, 400)
    host.show()
    qapp.processEvents()
    edit.setFocus()
    qapp.processEvents()
    focus = qapp.focusWidget()
    flash = SyncFlash(host)
    try:
        assert flash.isHidden() and not flash.lit() and not flash.isWindow()
        flash.show_mark(7, 500)
        assert flash.lit() and not flash.isHidden() and flash.number == 7
        assert flash.geometry() == host.rect()
        assert flash.timer.isActive() and flash.timer.interval() == 500 and flash.timer.isSingleShot()
        assert flash.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert flash.focusPolicy() == Qt.FocusPolicy.NoFocus and qapp.focusWidget() is focus
        widgets = [c for c in host.children() if isinstance(c, QWidget)]
        assert widgets[-1] is flash and host.statusBar() in widgets          # trên mọi widget anh em, cả thanh trạng thái
        image = flash.grab().toImage()
        square = flash.square()
        assert square.width() == int(0.9 * 400) and square.center().x() in (319, 320)
        assert image.pixelColor(square.left() + 3, square.top() + 3).name() == "#ffffff"
        assert image.pixelColor(square.right() - 3, square.bottom() - 3).name() == "#ffffff"
        assert image.pixelColor(2, 2).name() == "#000000" and image.pixelColor(637, 397).name() == "#000000"
    finally:
        flash.finish()
    assert not flash.lit() and flash.isHidden() and not flash.timer.isActive()
    host.close()


def test_console_flash_window_covers_a_screen_and_takes_no_input(qapp):
    screen = QGuiApplication.primaryScreen()
    flash = SyncFlash(None, screen)
    try:
        assert flash.isWindow() and flash.isHidden() and flash.windowType() == Qt.WindowType.Tool
        flags = flash.windowFlags()
        for flag in (Qt.WindowType.FramelessWindowHint, Qt.WindowType.WindowStaysOnTopHint,
                     Qt.WindowType.WindowTransparentForInput, Qt.WindowType.WindowDoesNotAcceptFocus):
            assert flags & flag, flag
        assert flash.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        assert flash.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert flash.focusPolicy() == Qt.FocusPolicy.NoFocus and flash.area() == screen.geometry()
        assert disable_window_transitions(flash) is False and flash.transitions_off is False   # nền offscreen
        parent = QWidget()
        assert disable_window_transitions(QWidget(parent)) is False                          # widget con
        flash.show_mark(3, 200)
        assert flash.lit() and flash.geometry() == screen.geometry() and flash.timer.interval() == 200
        # cửa sổ mới hiện chỉ được vẽ khi đã "expose": show_mark chờ tới lúc đó rồi mới trả về
        assert flash.testAttribute(Qt.WidgetAttribute.WA_Mapped)
    finally:
        flash.finish()
        flash.close()
    assert not flash.lit()


def test_marker_stamps_after_painting_and_refuses_marks_too_close(tmp_path):
    values = iter([5.0, 5.001, 5.0035,      # dấu 1: lúc gọi, trước khi vẽ, sau khi vẽ (t_perf)
                   5.2,                     # ô còn sáng: từ chối
                   5.6,                     # ô đã tắt nhưng chưa đủ 1 s: từ chối
                   6.1, 6.1005, 6.102,      # dấu 2
                   6.5])                    # dòng CLOCK
    reads = []

    def clock():
        reads.append(next(values))
        return reads[-1]

    flash = FakeFlash(reads)
    log = SyncMarkLog("ui.app")
    marker = SyncMarker(log, flash, clock=clock, open_file=lambda: tmp_path / "sống.csv")
    assert marker.flash_ms == 500 and marker.min_gap_s == 1.0 and marker.ready()
    seen = []

    def context(t):
        seen.append(t)
        return {"state": "EDITING", "note": "SIM"}

    row = marker.mark("button", context)
    assert flash.shown == [(1, 500, 2)]                  # vẽ sau lần đọc đồng hồ thứ hai, t_perf đọc sau khi vẽ
    assert row["n"] == 1 and row["t_perf"] == 5.0035 and seen == [5.0035] and row["paint_ms"] == 2.5
    assert row["flash_ms"] == 500 and row["trigger"] == "button" and row["state"] == "EDITING"
    assert log.path == tmp_path / "sống.csv" and read_sync_marks(log.path)[0]["t_perf"] == 5.0035
    assert marker.mark("key_f8") is None                 # ô còn sáng
    flash.finish()
    assert marker.mark("key_f8") is None                 # chưa đủ min_gap_s
    assert len(log.rows) == 1 and log.marks == 1 and len(flash.shown) == 1
    row2 = marker.mark("key_f8", context)
    assert row2["n"] == 2 and row2["t_perf"] == 6.102 and row2["paint_ms"] == 1.5 and flash.shown[-1][0] == 2
    flash.finish()
    clock_row = marker.clock_row("state_change", lambda t: {"t_session": 1.25, "note": f"t={t}"})
    assert clock_row["kind"] == CLOCK and clock_row["n"] == "" and clock_row["t_perf"] == 6.5
    assert clock_row["note"] == "t=6.5" and clock_row["flash_ms"] == "" and len(flash.shown) == 2
    assert [r["kind"] for r in read_sync_marks(log.path)] == [SYNC_MARK, SYNC_MARK, CLOCK]


# ---- cockpit đỗ xe ------------------------------------------------------------------------------------------------
@pytest.fixture
def window(qapp, tmp_path):
    from autopark.ui.app import DEFAULT_SCENARIO, build_window
    w = build_window(DEFAULT_SCENARIO)
    w._timer.stop()
    w.sync_dir = tmp_path / "sync"
    w.sync_marker.min_gap_s = 0.0
    yield w
    w.close()


def drive_to_rest(window, dt=0.1, steps=600):
    """Như nhịp giao diện: tiến mô phỏng rồi xem phiên có đổi trạng thái không."""
    for _ in range(steps):
        window.advance_by(dt)
        window._poll_state_change()
        if not window.session.simulating:
            return


def test_main_window_marks_before_start_and_after_stop_but_never_while_driving(window, tmp_path):
    log = window.sync_marks
    assert window.sync_action.isEnabled() and "F8" in window.sync_action.text()
    assert window._handle_key(f8()) is True
    row = log.rows[-1]
    assert row["kind"] == SYNC_MARK and row["n"] == 1 and row["trigger"] == "key_f8" and row["state"] == "EDITING"
    assert row["source"] == "ui.app" and row["note"] == "SIM" and row["t_io"] == "" and row["io_clock"] == ""
    assert row["t_session"] == "" and row["flash_ms"] == 500
    assert window.sync_flash.lit() and window.sync_flash.geometry() == window.rect()
    image, square = window.sync_flash.grab().toImage(), window.sync_flash.square()   # bảng màu của cockpit không lẫn vào
    assert image.pixelColor(square.left() + 3, square.top() + 3).name() == "#ffffff"
    assert image.pixelColor(3, 3).name() == "#000000"
    assert log.path.parent == tmp_path / "sync" and log.path.name.endswith("_ui_app.csv")
    assert "Dấu đồng bộ #1" in window.statusBar().currentMessage()
    assert window._handle_key(f8()) is True and log.marks == 1             # ô còn sáng: từ chối
    assert "còn đang nháy" in window.statusBar().currentMessage()
    window.sync_flash.finish()
    window.sync_action.click()
    assert log.marks == 2 and log.rows[-1]["trigger"] == "button" and log.rows[-1]["n"] == 2
    window.sync_flash.finish()

    assert window.plan(sync=True).ok
    window._poll_state_change()                                         # READY: chưa vào lần chạy, không có CLOCK
    assert len(log.rows) == 2
    window.run()
    window._poll_state_change()
    clock = log.rows[-1]
    assert clock["kind"] == CLOCK and clock["note"] == "READY→RUNNING" and clock["t_session"] == 0.0
    assert clock["state"] == "RUNNING" and clock["trigger"] == "state_change" and clock["n"] == ""
    assert not window.sync_action.isEnabled()
    window.advance_by(0.5)
    count = len(log.rows)
    assert window._handle_key(f8()) is True                             # đang chạy: phím bị nuốt, không có dấu
    assert len(log.rows) == count and not window.sync_flash.lit()
    assert "trước Bắt đầu đỗ" in window.statusBar().currentMessage()
    assert window.make_sync_mark() is None and len(log.rows) == count
    window.stop()
    window._poll_state_change()
    stopping = log.rows[-1]
    assert stopping["kind"] == CLOCK and stopping["note"].startswith("RUNNING→STOPPING: ")
    assert window.session.stop_reason in stopping["note"]
    assert stopping["t_session"] == round(window.session.world.time, 4) and stopping["t_session"] > 0.4
    assert window._handle_key(f8()) is True and len(log.rows) == count + 1   # STOPPING: vẫn khóa
    drive_to_rest(window)
    assert window.session.state == SessionState.STOPPED
    stopped = log.rows[-1]
    assert stopped["kind"] == CLOCK and stopped["note"] == f"STOPPING→STOPPED: {window.session.stop_reason}"
    assert stopped["t_session"] >= stopping["t_session"] and window.sync_action.isEnabled()
    assert window._handle_key(f8()) is True
    last = log.rows[-1]
    assert last["n"] == 3 and last["state"] == "STOPPED" and last["t_session"] == ""   # đồng hồ phiên đã đứng
    assert [r["kind"] for r in log.rows] == [SYNC_MARK, SYNC_MARK, CLOCK, CLOCK, CLOCK, SYNC_MARK]
    assert read_sync_marks(log.path) == log.rows                         # tệp sống = bộ nhớ


def test_start_waits_until_the_flash_is_off(window):
    """Sửa 02/10/2026 (review 12/23): ô nháy phủ cả cửa sổ nhưng không nhận chuột, nên cú bấm "Bắt đầu đỗ" xuyên qua nó;
    run() từ chối khi ô còn sáng, để xe không chạy khi cockpit còn bị che."""
    assert window.plan(sync=True).ok
    window._poll_state_change()
    assert window.make_sync_mark("button") is not None and window.sync_flash.lit()
    window.primary_action.click()                                       # bấm xuyên qua ô
    assert window.session.state == SessionState.READY and window.sync_flash.lit()
    assert "Ô dấu đồng bộ còn sáng" in window.statusBar().currentMessage()
    assert window.sync_marks.marks == 1 and [r["kind"] for r in window.sync_marks.rows] == [SYNC_MARK]
    window.sync_flash.finish()                                          # ô tự tắt sau 0,5 s
    window.primary_action.click()
    assert window.session.state == SessionState.RUNNING


def test_status_bar_exists_before_the_first_mark_so_the_flash_covers_it(window, qapp):
    """Sửa 02/10/2026 (review 35): QMainWindow chỉ tạo thanh trạng thái ở lần gọi statusBar() đầu tiên; tạo sau khi ô
    nháy đã nâng lên (lời báo của dấu đầu) thì thanh nằm đè lên ô, một dải màu giao diện ở đáy video."""
    bars = [c for c in window.children() if isinstance(c, QStatusBar)]
    assert len(bars) == 1                                               # có sẵn từ lúc dựng cửa sổ
    window.show()
    qapp.processEvents()
    assert window.make_sync_mark("key_f8") is not None
    qapp.processEvents()
    widgets = [c for c in window.children() if isinstance(c, QWidget)]
    assert widgets[-1] is window.sync_flash and window.statusBar() is bars[0] and bars[0].isVisible()
    image = window.grab().toImage()
    assert image.pixelColor(5, window.height() - 5).name() == "#000000"   # đáy cửa sổ: nền đen của ô
    window.sync_flash.finish()


@contextlib.contextmanager
def held_like_excel(path):
    """Giữ tệp mở như Excel: chỉ cho chung quyền đọc (FILE_SHARE_READ), nên tiến trình khác không nối, không thay được."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                     wintypes.DWORD, wintypes.HANDLE)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    generic_read, file_share_read, open_existing, file_attribute_normal = 0x80000000, 0x1, 3, 0x80
    handle = kernel32.CreateFileW(str(path), generic_read, file_share_read, None, open_existing, file_attribute_normal,
                                  None)
    assert handle not in (None, wintypes.HANDLE(-1).value), ctypes.get_last_error()
    try:
        yield
    finally:
        kernel32.CloseHandle(handle)


@pytest.mark.skipif(sys.platform != "win32", reason="khóa chia sẻ tệp kiểu Excel chỉ có trên Windows")
def test_clock_rows_lost_while_the_live_file_is_locked_are_reported_then_written_back(window):
    """Sửa 02/10/2026 (review 11): tệp sống đang mở trong Excel suốt lần chạy làm các dòng CLOCK không nối được. Giao diện
    báo ngay (nối sau lời báo đang hiện, không che nó), và dấu kế tiếp sau khi Excel đóng ghi lại cả tệp từ bộ nhớ."""
    log = window.sync_marks
    assert window.make_sync_mark("key_f8") is not None                  # tạo tệp sống
    window.sync_flash.finish()
    assert window.plan(sync=True).ok
    window._poll_state_change()
    with held_like_excel(log.path):
        window.statusBar().showMessage("LIMITS_MISMATCH (cảnh báo): giả", 15000)
        window.run()
        window._poll_state_change()                                     # READY→RUNNING: không nối được
        message = window.statusBar().currentMessage()
        assert log.unwritten == 1 and log.last_write_ok is False and "PermissionError" in log.error
        assert message.startswith("LIMITS_MISMATCH (cảnh báo): giả") and "Dấu đồng bộ: 1 dòng CHƯA GHI ĐƯỢC" in message
        window.stop()
        window._poll_state_change()
        message = window.statusBar().currentMessage()
        assert log.unwritten == 2 and message.count("Dấu đồng bộ:") == 1 and "2 dòng CHƯA GHI ĐƯỢC" in message
        drive_to_rest(window)
        assert window.session.state == SessionState.STOPPED and log.unwritten == 3
        assert len(read_sync_marks(log.path)) == 1                      # tệp sống chỉ có dấu #1
        window.make_sync_mark("key_f8")
        assert log.unwritten == 4 and "4 dòng CHƯA GHI ĐƯỢC" in window.statusBar().currentMessage()
        window.sync_flash.finish()
    row = window.make_sync_mark("key_f8")                               # Excel đã đóng tệp
    assert row is not None and row["n"] == 3 and log.unwritten == 0
    assert "CHƯA GHI" not in window.statusBar().currentMessage()
    assert read_sync_marks(log.path) == log.rows
    assert [r["kind"] for r in log.rows] == [SYNC_MARK, CLOCK, CLOCK, CLOCK, SYNC_MARK, SYNC_MARK]
    assert not list(log.path.parent.glob("*.tmp"))


def test_closing_the_window_writes_back_rows_the_live_file_missed(window, tmp_path, capsys):
    """Sửa 02/10/2026 (review 11): dòng CLOCK hỏng mà sau đó không có dấu nào nữa thì lúc đóng cửa sổ ghi lại cả tệp;
    vẫn không ghi được thì báo ra stderr (không ném lỗi, không hộp thoại)."""
    from PySide6.QtGui import QCloseEvent

    log = window.sync_marks
    assert window.make_sync_mark("key_f8") is not None
    window.sync_flash.finish()
    real, blocked = log.path, tmp_path / "khoa"
    blocked.mkdir()
    log.path = blocked                                                  # như tệp bị khóa suốt lần chạy
    assert window.plan(sync=True).ok
    window._poll_state_change()
    window.run()
    window._poll_state_change()
    window.stop()
    window._poll_state_change()
    assert log.unwritten == 2 and len(read_sync_marks(real)) == 1
    window.closeEvent(QCloseEvent())                                    # vẫn khóa
    assert "2 dòng dấu đồng bộ chưa ghi được ra đĩa" in capsys.readouterr().err
    log.path = real                                                     # hết khóa
    window.closeEvent(QCloseEvent())
    assert log.unwritten == 0 and read_sync_marks(real) == log.rows and capsys.readouterr().err == ""


def test_manual_drive_marks_carry_session_time_and_the_button_never_takes_focus(window):
    window._start_manual()
    assert window.session.state == SessionState.MANUAL
    window.advance_by(0.25)
    assert window.sync_action.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert window._handle_key(f8()) is True                              # F8 đi trước phím lái tay
    row = window.sync_marks.rows[-1]
    assert row["state"] == "MANUAL" and row["t_session"] == round(window.session.world.time, 4) > 0
    window.sync_flash.finish()
    repeat = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F8, Qt.KeyboardModifier.NoModifier, "", True)
    assert window._handle_key(repeat) is True and window.sync_marks.marks == 1   # giữ phím: không thêm dấu


def test_rows_carry_the_run_speed_factor_and_it_is_locked_while_driving(window):
    """Sửa 02/10/2026: 'tốc độ chạy' ≠ 1× làm thời gian phiên trôi nhanh/chậm hơn perf_counter; cột time_scale ghi hệ số
    và công thức đổi của sync_marks.py (chia cho time_scale) cho lại đúng perf_counter. Đồng hồ perf giả trôi đúng bằng
    real_dt của từng nhịp, như nhịp giao diện không trôi."""
    perf = [1000.0]
    window.sync_marker.clock = lambda: perf[0]

    def tick(real_dt=0.02):
        perf[0] += real_dt
        window.advance_by(real_dt)
        window._poll_state_change()

    window.spin_rt.setValue(2.0)
    assert window.session.realtime_factor == 2.0 and window.spin_rt.isEnabled()
    assert window.make_sync_mark()["time_scale"] == 2.0                  # dấu trước Bắt đầu đỗ
    window.sync_flash.finish()
    assert window.plan(sync=True).ok
    window._poll_state_change()
    window.run()
    assert not window.spin_rt.isEnabled()                               # một lần chạy chỉ một hệ số
    tick()
    start = window.sync_marks.rows[-1]
    assert start["note"] == "READY→RUNNING" and start["time_scale"] == 2.0
    for _ in range(25):
        tick()                                                          # 0,5 s thật = 1 s mô phỏng
    window.stop()
    window._poll_state_change()
    assert window.session.state == SessionState.STOPPING and not window.spin_rt.isEnabled()
    stopping = window.sync_marks.rows[-1]
    assert stopping["note"].startswith("RUNNING→STOPPING") and stopping["time_scale"] == 2.0
    # công thức trong docstring của sync_marks: t_perf ≈ c.t_perf − (c.t_session − t_sự_kiện) / c.time_scale
    elapsed = stopping["t_session"] - start["t_session"]
    assert elapsed == pytest.approx(1.0, abs=0.01)
    assert start["t_perf"] + elapsed / start["time_scale"] == pytest.approx(stopping["t_perf"], abs=0.005)
    assert abs(start["t_perf"] + elapsed - stopping["t_perf"]) > 0.4    # bỏ hệ số: lệch 0,5 s
    for _ in range(300):
        tick(0.1)
        if not window.session.simulating:
            break
    assert window.session.state == SessionState.STOPPED and window.spin_rt.isEnabled()
    assert window.sync_marks.rows[-1]["time_scale"] == 2.0
    window.spin_rt.setValue(0.5)
    window.reset()
    window._start_manual()                                              # lái tay: đổi được, mỗi dấu mang hệ số lúc dấu
    assert window.session.state == SessionState.MANUAL and window.spin_rt.isEnabled()
    window.advance_by(0.2)
    assert window.make_sync_mark()["time_scale"] == 0.5


def test_export_writes_sync_file_only_when_marks_exist(window, tmp_path, monkeypatch, stub_environment):
    out = tmp_path / "log"
    names = iter(["lan1.csv", "lan2.csv"])
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out / next(names)), "CSV (*.csv)"))
    assert window.plan(sync=True).ok
    window._poll_state_change()
    window.run()
    window._poll_state_change()
    drive_to_rest(window, dt=0.5)
    assert window.session.state == SessionState.COMPLETED
    log = window.sync_marks
    assert log.marks == 0 and [r["note"] for r in log.rows] == ["READY→RUNNING", "RUNNING→COMPLETED: Đỗ xong"]
    window._export_log()
    assert (out / "lan1.csv").exists() and len(list(out.glob("lan1_*"))) == 1     # gói export_run như cũ
    assert not list(out.glob("*_sync_marks.csv")) and not (tmp_path / "sync").exists()
    assert "dấu đồng bộ" not in window.statusBar().currentMessage()
    assert window._handle_key(f8()) is True                              # sau khi đỗ xong: được
    window._export_log()
    copy = out / "lan2_sync_marks.csv"
    assert read_sync_marks(copy) == log.rows and [r["kind"] for r in log.rows] == [CLOCK, CLOCK, SYNC_MARK]
    assert "dấu đồng bộ" in window.statusBar().currentMessage()
    assert read_sync_marks(log.path) == log.rows                         # tệp sống có cả dòng CLOCK đã đệm


def test_vehicle_io_rows_carry_the_io_clock_and_a_real_port_is_never_opened(window, tmp_path, monkeypatch):
    import serial
    opened = []

    def refuse(*args, **kwargs):
        opened.append(args)
        raise AssertionError("test không được mở cổng thật")

    monkeypatch.setattr(serial, "Serial", refuse)
    monkeypatch.setattr(serial, "serial_for_url", refuse)
    combo = window.combo_drive
    combo.setCurrentIndex(combo.findData(DriveMode.VEHICLE_IO.value))
    window.spin_rt.setValue(2.0)                                         # bo mô phỏng theo "tốc độ chạy"
    assert window.plan(sync=True).ok
    window._poll_state_change()
    assert window._handle_key(f8()) is True                              # bo mô phỏng chưa dựng trước START: không t_io
    first = window.sync_marks.rows[-1]
    assert first["note"] == "VEHICLE_IO, bo mô phỏng" and first["t_io"] == "" and first["io_clock"] == ""
    window.sync_flash.finish()
    window.run()
    assert window.session.state == SessionState.RUNNING
    window._poll_state_change()
    drive_to_rest(window, dt=0.5)
    assert window.session.state == SessionState.COMPLETED
    clocks = [r for r in window.sync_marks.rows if r["kind"] == CLOCK]
    assert [c["note"].split(":")[0] for c in clocks] == ["READY→RUNNING", "RUNNING→COMPLETED"]
    assert all(c["io_clock"] == "sim" and isinstance(c["t_io"], float) and c["time_scale"] == 2.0 for c in clocks)
    assert clocks[-1]["t_io"] == round(window.session.run_link.io.now(), 6)

    window.reset()
    window.combo_port.addItem("COM_GIA — cổng giả", "COM_GIA")         # bo thật: chọn cổng không mở cổng
    window.combo_port.setCurrentIndex(window.combo_port.findData("COM_GIA"))
    link = window.session.vehicle_link
    assert link.io.port == "COM_GIA" and link.io.transport is None and link.realtime
    rows = []
    for _ in range(2):
        assert window._handle_key(f8()) is True
        window.sync_flash.finish()
        rows.append(window.sync_marks.rows[-1])
        time.sleep(0.02)
    assert all(r["io_clock"] == "realtime" and r["note"] == "VEHICLE_IO, cổng COM_GIA" for r in rows)
    assert all(r["time_scale"] == 1.0 for r in rows)                    # bo thời gian thực bỏ qua "tốc độ chạy" (2×)
    offsets = [r["t_perf"] - r["t_io"] for r in rows]
    assert abs(offsets[0] - offsets[1]) < 1e-3 and rows[1]["t_perf"] - rows[0]["t_perf"] > 0.015
    assert opened == [] and link.io.transport is None

    out = tmp_path / "log" / "vio.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), "CSV (*.csv)"))
    window._export_log()
    assert (out.parent / "vio_vehicle_io" / "events.csv").exists()     # hai thứ nằm cạnh nhau
    assert read_sync_marks(out.parent / "vio_sync_marks.csv") == window.sync_marks.rows
    assert "_vehicle_io" in window.statusBar().currentMessage() and "dấu đồng bộ" in window.statusBar().currentMessage()
    assert opened == []


def test_lidar_app_clock_row_anchors_the_lidar_stop(qapp, tmp_path, monkeypatch, stub_environment):
    pytest.importorskip("numpy")
    from autopark.ui.lidar_app import build_window as build_lidar_window
    from tests.test_lidar_dock_ui import FakeSource, feed

    window, dock = build_lidar_window(None, port="COM9", recording=None)
    dock.timer.stop()
    window._timer.stop()
    window.sync_dir = tmp_path / "sync"
    window.sync_marker.min_gap_s = 0.0
    try:
        source = FakeSource()
        dock.attach_source(source, start_thread=False)
        t = feed(dock, source, 0.0, 1.2, angle_deg=60.0)                  # ngoài đường thẳng tới đích
        first = window.make_sync_mark("key_f8")
        assert first["source"] == "ui.lidar_app" and first["state"] == "EDITING"
        window.sync_flash.finish()
        assert window.plan(sync=True).ok
        window._poll_state_change()
        window.run()
        window._poll_state_change()
        window.advance_by(1.0)
        window._poll_state_change()
        t = feed(dock, source, t, 0.9, times=2)                          # tay trước LiDAR, trên đường
        assert window.session.state == SessionState.STOPPING
        window._poll_state_change()
        clock = window.sync_marks.rows[-1]
        stop = next(e for e in window.session.safety_events if e.code == "MAP_CHANGED")
        assert clock["kind"] == CLOCK and "RUNNING→STOPPING" in clock["note"] and "Vật cản mới" in clock["note"]
        assert clock["t_session"] == round(stop.stamp.t, 4)
        drive_to_rest(window)
        assert window.session.state == SessionState.STOPPED
        assert window.make_sync_mark()["n"] == 2
        out = tmp_path / "log" / "lidar.csv"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), "CSV (*.csv)"))
        window._export_log()
        exported = read_sync_marks(out.parent / "lidar_sync_marks.csv")
        assert [r["kind"] for r in exported] == [SYNC_MARK, CLOCK, CLOCK, CLOCK, SYNC_MARK]
        assert all(r["source"] == "ui.lidar_app" for r in exported)
    finally:
        dock.shutdown()
        window.close()


# ---- rig.bench ----------------------------------------------------------------------------------------------------
@pytest.fixture
def fake_bench(monkeypatch):
    """rig.bench với hai camera giả, không AI, ô nháy ngắn; giữ lại BenchSync đã mở để test xem trạng thái cuối."""
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from autopark.rig import bench
    from autopark.rig.core import Rig, RigConfig
    from tests.rig_fakes import fake_manager

    monkeypatch.setattr(sync_flash, "MIN_GAP_S", 0.1)
    monkeypatch.setattr(sync_flash, "FLASH_MS", 50)
    monkeypatch.setattr(bench, "SYNC_END_LEAD_S", 0.3)
    monkeypatch.setattr(bench, "build_rig", lambda args: Rig(fake_manager(ports=(1, 2), period=0.03), RigConfig(ai=False)))
    opened = []
    real_open = bench.open_bench_sync

    def capture(args, path):
        sync = real_open(args, path)
        opened.append(sync)
        return sync

    monkeypatch.setattr(bench, "open_bench_sync", capture)
    return bench, opened


def key_after(delay_s: float, key: str = "\r"):
    """console_key giả: trả `key` đúng một lần, `delay_s` giây sau lần gọi đầu."""
    state = {"t0": None, "sent": False}

    def console_key():
        now = time.perf_counter()
        if state["t0"] is None:
            state["t0"] = now
        if not state["sent"] and now - state["t0"] >= delay_s:
            state["sent"] = True
            return key
        return None

    return console_key


def test_bench_start_console_key_and_end_marks_stay_inside_the_window(fake_bench, tmp_path, monkeypatch, capsys):
    bench, opened = fake_bench
    monkeypatch.setattr(bench, "console_key", key_after(0.5))
    out = tmp_path / "out"
    code = bench.main(["--name", "s", "--seconds", "1.4", "--warmup", "0.1", "--out", str(out), "--sync-mark"])
    assert code == 0
    rows = read_sync_marks(out / "s.sync.csv")
    assert [r["trigger"] for r in rows] == ["auto_start", "console_key", "auto_end"]
    assert [r["n"] for r in rows] == [1, 2, 3]
    assert all(r["kind"] == SYNC_MARK and r["source"] == "rig.bench" and r["note"] == "phiên s" for r in rows)
    assert all(r["time_scale"] == "" for r in rows)                      # bàn thử: perf_counter, không có hệ số
    t = [r["t_rig_s"] for r in rows]
    assert 0 <= t[0] < t[1] < t[2] < 1.4 and 0.35 < t[1] - t[0] < 0.8 and t[2] >= 1.4 - 0.3 - 0.05
    data = json.loads((out / "s.rig.json").read_text(encoding="utf-8"))
    marks = data["sync_marks"]
    assert marks["marks"] == 3 and marks["clock"] == "perf_counter" and marks["write_error"] is None
    assert marks["flash_ms"] == 50 and marks["file"] == str(out / "s.sync.csv") and len(marks["rows"]) == 3
    assert marks["screen"]["index"] == 0 and marks["screen"]["transitions_off"] is False
    for r in rows:
        assert marks["t_start_perf_s"] == pytest.approx(r["t_perf"] - r["t_rig_s"], abs=2e-4)
    assert data["duration_s"] < 1.6
    sync = opened[0]
    assert sync.closed and not sync.flash.lit() and sync.end_done
    text = capsys.readouterr().out
    assert "DẤU ĐỒNG BỘ #1 (auto_start)" in text and "dấu đồng bộ: 3 dấu" in text


def test_bench_periodic_marks(fake_bench, tmp_path, monkeypatch, capsys):
    bench, opened = fake_bench
    monkeypatch.setattr(bench, "SYNC_EVERY_MIN_S", 0.2)
    monkeypatch.setattr(bench, "console_key", key_after(1.25))       # phím sau t_end − END_LEAD − khoảng cách: bỏ qua
    out = tmp_path / "out"
    code = bench.main(["--name", "p", "--seconds", "1.4", "--warmup", "0.1", "--out", str(out), "--sync-every", "0.3"])
    assert code == 0
    rows = read_sync_marks(out / "p.sync.csv")
    triggers = [r["trigger"] for r in rows]
    assert triggers[0] == "auto_start" and triggers[-1] == "auto_end" and set(triggers[1:-1]) == {"periodic"}
    periodic = [r for r in rows if r["trigger"] == "periodic"]
    assert len(periodic) >= 2
    limit = rows[0]["t_rig_s"] + 1.4 - 0.3 - 0.1 + 0.05                  # t_end − END_LEAD − khoảng cách (+ một nhịp)
    assert all(r["t_rig_s"] <= limit for r in periodic) and rows[-1]["t_rig_s"] < 1.4
    data = json.loads((out / "p.rig.json").read_text(encoding="utf-8"))
    assert data["sync_marks"]["every_s"] == 0.3 and data["sync_marks"]["marks"] == len(rows)
    assert data["duration_s"] < 1.6 and "bỏ qua phím" in capsys.readouterr().out


def test_bench_sync_write_error_exits_1_but_keeps_every_row(fake_bench, tmp_path, monkeypatch, capsys):
    bench, opened = fake_bench
    monkeypatch.setattr(bench, "console_key", lambda: None)
    broken = tmp_path / "đĩa hỏng"
    broken.mkdir()
    capture = bench.open_bench_sync

    def open_then_break(args, path):
        sync = capture(args, path)
        sync.log.path = broken                                          # mọi lần nối dòng sau đó lỗi, như đĩa đầy
        return sync

    monkeypatch.setattr(bench, "open_bench_sync", open_then_break)
    out = tmp_path / "out"
    code = bench.main(["--name", "e", "--seconds", "1.0", "--warmup", "0.1", "--out", str(out), "--sync-mark"])
    assert code == 1
    marks = json.loads((out / "e.rig.json").read_text(encoding="utf-8"))["sync_marks"]
    assert marks["marks"] == 2 and [r["trigger"] for r in marks["rows"]] == ["auto_start", "auto_end"]
    assert "Error" in marks["write_error"] and read_sync_marks(out / "e.sync.csv") == []   # tệp chỉ có tiêu đề
    text = capsys.readouterr().out
    assert "CẢNH BÁO: dấu đồng bộ không trọn" in text and "LỖI GHI" in text and "dấu đồng bộ: 2 dấu" in text


def test_bench_sync_options_are_checked_before_any_device_starts(tmp_path, monkeypatch, capsys):
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from autopark.rig import bench

    def no_devices(args):
        raise AssertionError("không được dựng Rig")

    monkeypatch.setattr(bench, "build_rig", no_devices)
    out = tmp_path / "o"
    used = tmp_path / "đã có"
    used.mkdir()
    (used / "x.sync.csv").write_text("n,kind\n", encoding="utf-8")
    # Dòng usage của argparse có sẵn cả "--replay", "--sync-every", "--sync-screen": chỉ xét phần sau "error:" và một
    # đoạn riêng của từng nhánh kiểm (sửa 02/10/2026).
    for argv, needle in ((["--sync-mark", "--replay", str(tmp_path / "ban_ghi")], "không dùng với --replay"),
                         (["--sync-every", "0.5"], "--sync-every phải là số giây hữu hạn ≥ 2 (đang là 0.5)"),
                         (["--sync-every", "nan"], "--sync-every phải là số giây hữu hạn ≥ 2 (đang là nan)"),
                         (["--sync-screen", "1"], "--sync-screen chỉ dùng cùng --sync-mark"),
                         (["--sync-mark", "--sync-screen", "-1"], "--sync-screen phải ≥ 0 (đang là -1)")):
        with pytest.raises(SystemExit) as info:
            bench.main(["--name", "g", "--out", str(out), *argv])
        message = capsys.readouterr().err.split("error:", 1)[1]
        assert info.value.code == 2 and needle in message, (argv, message)
    with pytest.raises(SystemExit) as info:
        bench.main(["--name", "x", "--out", str(used), "--sync-mark"])
    assert info.value.code == 2 and "không ghi đè" in capsys.readouterr().err
    assert (used / "x.sync.csv").read_text(encoding="utf-8") == "n,kind\n" and not out.exists()

    started = []

    class BuiltButNeverStarted:
        replay = None

        def start(self, *args, **kwargs):
            started.append("start")

        def stop(self, *args, **kwargs):
            started.append("stop")
            return []

    monkeypatch.setattr(bench, "build_rig", lambda args: BuiltButNeverStarted())
    with pytest.raises(SystemExit) as info:                              # màn hình không có: sau build_rig, trước start
        bench.main(["--name", "g", "--out", str(out), "--sync-mark", "--sync-screen", "9"])
    err = capsys.readouterr().err
    assert info.value.code == 2 and "--sync-screen 9" in err and "màn hình" in err
    assert started == [] and not (out / "g.sync.csv").exists()


def test_bench_stopped_before_the_first_mark_leaves_no_sync_file_to_block_a_rerun(fake_bench, tmp_path, monkeypatch):
    """Sửa 02/10/2026 (review 34): Ctrl+C lúc làm nóng (hay rig.start lỗi) để lại <name>.sync.csv chỉ có tiêu đề, làm
    lần chạy lại đúng lệnh đó bị từ chối 'không ghi đè'; nay tệp rỗng được xóa khi đóng."""
    bench, opened = fake_bench
    monkeypatch.setattr(bench, "console_key", lambda: None)
    working = bench.build_rig

    class Interrupted:
        replay = None
        cams = types.SimpleNamespace(specs=[])
        cfg = types.SimpleNamespace(lidar_port=None, checkpoint=None)

        def start(self, *args, **kwargs):
            raise KeyboardInterrupt

        def stop(self, *args, **kwargs):
            return []

    monkeypatch.setattr(bench, "build_rig", lambda args: Interrupted())
    out = tmp_path / "out"
    argv = ["--name", "cb1", "--seconds", "0.5", "--warmup", "0.1", "--out", str(out), "--sync-mark"]
    with pytest.raises(KeyboardInterrupt):
        bench.main(argv)
    assert opened[0].closed and opened[0].log.path is None and not (out / "cb1.sync.csv").exists()
    monkeypatch.setattr(bench, "build_rig", working)
    assert bench.main(argv) == 0                                         # chạy lại đúng lệnh đó: được
    assert [r["trigger"] for r in read_sync_marks(out / "cb1.sync.csv")] == ["auto_start", "auto_end"]


def test_build_rig_value_error_is_a_usage_error_without_traceback(tmp_path, monkeypatch, capsys):
    """Sửa 02/10/2026 (review 9, bước 2): ValueError của build_rig (cổng hub mơ hồ của resolve_ports, --replay cùng
    --index…) thành lỗi dòng lệnh mã 2 ở rig.bench và ui.rig_app, không còn traceback; trước đó chỉ bắt LidarPortError."""
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from autopark.rig import bench
    from autopark.ui import rig_app

    with pytest.raises(SystemExit) as info:                              # build_rig thật, không chạm thiết bị nào
        bench.main(["--replay", str(tmp_path / "ban_ghi"), "--index", "0", "--no-ai", "--name", "g",
                    "--out", str(tmp_path / "o")])
    err = capsys.readouterr().err
    assert info.value.code == 2 and "không dùng cùng --index" in err.split("error:", 1)[1] and "Traceback" not in err

    def ambiguous(args):
        raise ValueError("cổng 2: 2 camera cùng số cổng (hub A, B)")

    monkeypatch.setattr(bench, "build_rig", ambiguous)
    with pytest.raises(SystemExit) as info:
        bench.main(["--ports", "1", "2", "--no-ai", "--name", "g", "--out", str(tmp_path / "o")])
    assert info.value.code == 2 and "cổng 2: 2 camera cùng số cổng" in capsys.readouterr().err.split("error:", 1)[1]
    with pytest.raises(SystemExit) as info:
        rig_app.build_window(["--ports", "1", "2", "--no-ai"], start=False)
    assert info.value.code == 2 and "cổng 2: 2 camera cùng số cổng" in capsys.readouterr().err.split("error:", 1)[1]
    assert not (tmp_path / "o").exists()


def test_bench_without_sync_flags_is_unchanged(fake_bench, tmp_path, monkeypatch):
    bench, opened = fake_bench

    def no_keys():
        raise AssertionError("không bật dấu đồng bộ thì không đọc phím")

    monkeypatch.setattr(bench, "console_key", no_keys)
    out = tmp_path / "out"
    code = bench.main(["--name", "k", "--seconds", "0.5", "--warmup", "0.1", "--out", str(out)])
    assert code == 0 and opened == []
    data = json.loads((out / "k.rig.json").read_text(encoding="utf-8"))
    assert "sync_marks" not in data and not list(out.glob("*.sync.csv"))


def test_console_key_skips_extended_keys_and_survives_no_console(monkeypatch):
    pytest.importorskip("cv2")
    from autopark.rig import bench

    pressed = []
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(kbhit=lambda: bool(pressed),
                                                                     getwch=lambda: pressed.pop(0)))
    assert bench.console_key() is None                                  # chưa nhấn gì
    pressed.extend(["\xe0", "H"])                                       # mũi tên lên: đọc cả hai rồi bỏ
    assert bench.console_key() is None and pressed == []
    pressed.extend(["\x00", ";"])                                       # F1
    assert bench.console_key() is None and pressed == []
    pressed.append("m")
    assert bench.console_key() == "m"

    def no_console():
        raise OSError("không có cửa sổ lệnh")

    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(kbhit=no_console, getwch=no_console))
    assert bench.console_key() is None
    monkeypatch.setitem(sys.modules, "msvcrt", None)                    # ngoài Windows: import msvcrt lỗi
    assert bench.console_key() is None


# ---- ui.rig_app (phần D) ------------------------------------------------------------------------------------------
def test_rig_app_f8_mark_reports_in_metrics(qapp, tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from pathlib import Path

    from autopark.rig.core import Rig, RigConfig
    from autopark.ui.rig_app import RigWindow
    from tests.rig_fakes import fake_manager

    rig = Rig(fake_manager(ports=(1, 2), period=0.03), RigConfig(ai=False))
    window = RigWindow(rig, checkpoints=[], snapshot_dir=tmp_path / "ảnh", start=False)
    window.sync_dir = tmp_path / "sync"
    try:
        assert window.btn_sync.isEnabled() and window.btn_sync.focusPolicy() == Qt.FocusPolicy.NoFocus
        window.keyPressEvent(f8())
        log = window.sync_marks
        row = log.rows[-1]
        assert row["source"] == "ui.rig_app" and row["n"] == 1 and row["trigger"] == "key_f8"
        assert row["t_rig_s"] == "" and row["state"] == "" and row["time_scale"] == ""   # Rig chưa bắt đầu, không ghi
        flash = window.sync_marker.flash
        assert flash.lit() and flash.geometry() == window.rect()
        assert "dấu đồng bộ #1" in window.message and "dấu đồng bộ #1" in window.metrics.text()
        assert log.path.parent == tmp_path / "sync" and log.path.name.endswith("_ui_rig_app.csv")
        window.keyPressEvent(f8())                                       # ô còn sáng
        assert log.marks == 1 and "chưa tạo dấu đồng bộ" in window.message
    finally:
        window.close()

    replay = types.SimpleNamespace(folder=Path("ban_ghi"), speed=1.0, stop=lambda: None)
    played = RigWindow(Rig(fake_manager(ports=(1,), period=0.03), RigConfig(ai=False), replay=replay),
                       checkpoints=[], snapshot_dir=tmp_path / "ảnh", start=False)
    played.sync_dir = tmp_path / "sync2"
    try:
        assert not played.btn_sync.isEnabled() and "phát lại" in played.btn_sync.toolTip()
        played.keyPressEvent(f8())
        assert played.sync_marks.rows == [] and not (tmp_path / "sync2").exists()
    finally:
        played.close()
