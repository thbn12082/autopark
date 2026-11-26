"""Công cụ gán nhãn chạy offscreen trên dự án thật nhập từ bộ ảnh giả: nét cọ bằng chuột, đa giác, hoàn tác/làm lại,
phóng/cỡ cọ bằng lăn chuột, tô lại theo AI, duyệt (ghi xuống đĩa) rồi sang ảnh kế, tự lưu khi chuyển ảnh, khung hỏng
phải xác nhận riêng."""
from datetime import timedelta
import json
import os
import stat
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.perception.labels import (BLOCKED, FREE, IGNORE, LabelProject, array_sha256,  # noqa: E402
                                        draft_from_prob)
from autopark.ui.label_app import LabelWindow, fit_to_screen, main, overlay_rgba, stripes  # noqa: E402
from tests.test_labels import PH, PW, T0, write_snapshot  # noqa: E402

RAMP = np.tile(np.linspace(0, 255, PW).round().astype(np.uint8), (PH, 1))      # trái FREE, phải BLOCKED ở ngưỡng 0,5


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "ảnh sa bàn"
    write_snapshot(root, T0, ports=(1, 2), probs={1: RAMP, 2: RAMP})
    write_snapshot(root, T0 + timedelta(minutes=5), ports=(1,), damaged=(1,), probs={1: RAMP}, seed=1)
    project = LabelProject(tmp_path / "dự án nhãn", create=True, who="người gán")
    project.import_snapshots(root, log=None)
    return project


def refuse(*_):
    raise AssertionError("không được hỏi người dùng ở bước này")


def at(window, x, y) -> QPoint:
    return window.canvas.to_widget(x, y).toPoint()


def drag(window, points):
    canvas = window.canvas
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(window, *points[0]))
    for point in points[1:]:
        QTest.mouseMove(canvas, at(window, *point))
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(window, *points[-1]))


def wheel(widget, pos: QPoint, delta: int, modifiers=Qt.KeyboardModifier.NoModifier):
    event = QWheelEvent(QPointF(pos), QPointF(widget.mapToGlobal(pos)), QPoint(0, 0), QPoint(0, delta),
                        Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


def test_overlay_colours_and_ignore_hatching():
    label = np.array([[FREE, BLOCKED, IGNORE, IGNORE]], np.uint8)
    rgba = overlay_rgba(label, np.array([[0, 0, 0, 1]], np.uint8))
    assert rgba[0, 0, :3].tolist() == [60, 190, 60] and rgba[0, 1, :3].tolist() == [230, 50, 50]
    assert rgba[0, 2, :3].tolist() != rgba[0, 3, :3].tolist()                 # hai tông xám: sọc
    s = stripes(12, 12)
    assert set(np.unique(s).tolist()) == {0, 1} and s[0, 0] != s[0, 6]


def test_label_window_paint_undo_review_autosave_and_damaged_frame(qapp, project):
    ids = project.ids()
    clean1, clean2, damaged = ids
    assert project.item(damaged)["status"] == "rejected"
    window = LabelWindow(project)
    window.confirm = refuse
    window.resize(1300, 800)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    try:
        assert window.item_list.count() == 3 and window.current_id == clean1
        assert "cổng 1" in window.info.text() and "WoodScape" in window.info.text()
        editor = window.editor
        assert editor.label[30, 20] == FREE and editor.label[30, 150] == BLOCKED

        window.canvas.setFocus()
        QTest.keyClick(window.canvas, Qt.Key.Key_2)                          # phím 2 = BLOCKED
        assert window.canvas.cls == BLOCKED and window.class_group.checkedId() == BLOCKED
        drag(window, [(15, 30), (40, 30), (60, 30)])
        assert editor.label[30, 40] == BLOCKED and editor.edited[30, 40] == 1 and window.btn_undo.isEnabled()
        window.btn_undo.click()
        assert editor.label[30, 40] == FREE and window.btn_redo.isEnabled()
        QTest.keyClick(window.canvas, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        assert editor.label[30, 40] == BLOCKED

        QTest.keyClick(window.canvas, Qt.Key.Key_3)
        QTest.keyClick(window.canvas, Qt.Key.Key_G)                          # đa giác IGNORE
        assert window.canvas.tool == "polygon" and window.canvas.cls == IGNORE
        for point in ((10, 60), (50, 60)):
            QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(window, *point))
        QTest.mouseDClick(window.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(window, 50, 85))
        assert editor.label[70, 45] == IGNORE and editor.label[66, 12] != IGNORE and not window.canvas.polygon

        scale = window.canvas.scale
        wheel(window.canvas, at(window, 80, 45), 120)
        assert window.canvas.scale == pytest.approx(scale * 1.25) and window.canvas.user_view
        radius = window.canvas.radius
        wheel(window.canvas, at(window, 80, 45), 120, Qt.KeyboardModifier.ControlModifier)
        assert window.canvas.radius > radius and window.radius_slider.value() == window.canvas.radius
        window.opacity_slider.setValue(80)
        QTest.keyClick(window.canvas, Qt.Key.Key_O)
        assert window.canvas.opacity == pytest.approx(0.8) and not window.canvas.show_overlay

        window.notes.setText("một chân bàn")
        painted = editor.label.copy()
        window.btn_review.click()                                           # lưu + duyệt + sang ảnh kế
        assert window.current_id == clean2
        on_disk = LabelProject(project.root)
        item = on_disk.item(clean1)
        assert item["status"] == "reviewed" and item["reviewed_by"] == "người gán" and item["notes"] == "một chân bàn"
        assert np.array_equal(on_disk.label(clean1), painted)
        assert item["reviewed_label_sha256"] == array_sha256(painted) and on_disk.edited(clean1)[70, 45] == 1

        editor2 = window.editor                                             # ảnh 2: tô lại theo AI giữ chỗ đã tô
        window.set_tool("brush")
        window.set_class(FREE)
        window.canvas.paint_stroke([(140, 20), (150, 20)], radius=2)
        assert editor2.label[20, 145] == FREE
        window.thr_slider.setValue(90)
        changed = window.regenerate(keep_edits=True)
        expected = draft_from_prob(RAMP, editor2.shape, 0.9)
        free = editor2.edited == 0
        assert changed > 0 and np.array_equal(editor2.label[free], expected[free]) and editor2.label[20, 145] == FREE
        window.confirm = lambda *_: False
        assert window.regenerate(keep_edits=False) is None and editor2.label[20, 145] == FREE
        window.confirm = lambda *_: True
        window.regenerate(keep_edits=False)
        assert np.array_equal(editor2.label, expected) and editor2.edited.sum() == 0
        window.canvas.paint_stroke([(5, 5)], cls=BLOCKED, radius=3)
        window.confirm = refuse
        window.btn_next.click()                                             # tự lưu, không hỏi
        assert window.current_id == damaged
        saved = LabelProject(project.root)
        assert saved.label(clean2)[5, 5] == BLOCKED and saved.item(clean2)["draft"]["threshold"] == 0.9
        assert saved.item(clean2)["status"] == "draft"

        assert "KHUNG HỎNG" in window.info.text() and "⚠" in window.item_list.item(2).text()
        assert window.btn_damage.isEnabled() and "KHUNG CŨ" not in window.info.text()
        rows = project.item(damaged)["damage"]["truncated_rows"]
        assert rows >= 24 and (window.editor.label[-rows:] != IGNORE).any()        # nháp AI gọi đáy bị tô là FREE/BLOCKED
        window.confirm = lambda *_: False
        assert not window.mark_reviewed() and project.item(damaged)["status"] == "rejected"
        answers = iter([True, False])                    # "Vẫn duyệt?" Có, "Tô IGNORE vùng hỏng rồi duyệt?" Không
        window.confirm = lambda *_: next(answers)
        assert not window.mark_reviewed() and project.item(damaged)["status"] == "rejected"
        assert "vùng hỏng chưa là IGNORE" in window.last_message
        window.confirm = lambda *_: True
        assert window.mark_reviewed() and project.item(damaged)["status"] == "reviewed"
        assert project.item(damaged)["damage_override"]["by"] == "người gán"
        on_disk = LabelProject(project.root)
        assert (on_disk.label(damaged)[-rows:] == IGNORE).all()                     # đã duyệt: đáy hỏng là IGNORE
        assert on_disk.item(damaged)["damage_override"]["damage_region_pixels"] == rows * 160

        window.filter_box.setCurrentIndex(window.filter_box.findData("reviewed"))
        assert window.item_list.count() == 2
        window.filter_box.setCurrentIndex(window.filter_box.findData("draft"))
        assert window.item_list.count() == 1 and window.current_id == clean2
        window.btn_reject.click()
        assert project.item(clean2)["status"] == "rejected" and project.item(clean2)["status_reason"] == "loại tay"
        window.filter_box.setCurrentIndex(0)
        window.item_list.setCurrentRow(0)
        assert window.current_id == clean1
        window.canvas.paint_stroke([(100, 70)], cls=IGNORE, radius=2)       # sửa ảnh đã duyệt rồi đóng cửa sổ
    finally:
        window.close()
    final = LabelProject(project.root)
    assert final.label(clean1)[70, 100] == IGNORE and final.item(clean1)["status"] == "draft"      # phải duyệt lại


def test_failed_save_keeps_the_item_open_and_the_window_open(qapp, project, monkeypatch):
    window = LabelWindow(project)
    window.confirm = refuse
    window.resize(1000, 700)
    window.show()
    qapp.processEvents()
    first = window.current_id
    window.canvas.paint_stroke([(30, 30)], cls=IGNORE, radius=3)

    def disk_full(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(project, "save", disk_full)
    window.btn_next.click()
    assert window.current_id == first and window.item_list.currentRow() == 0      # không bỏ ảnh chưa lưu được
    assert "KHÔNG LƯU ĐƯỢC" in window.last_message and window.editor.label[30, 30] == IGNORE
    assert not window.mark_reviewed() and project.item(first)["status"] == "draft"
    asked = []
    window.confirm = lambda title, text: asked.append(text) or False               # mặc định: ở lại
    assert not window.close() and window.isVisible()                               # đóng bị chặn, nét tô còn
    assert len(asked) == 1 and "BỎ mọi thay đổi" in asked[0] and "No space left" in asked[0]
    assert window.editor.label[30, 30] == IGNORE
    monkeypatch.undo()
    window.confirm = refuse                                                        # lưu được: đóng không hỏi
    assert window.close()
    assert LabelProject(project.root).label(first)[30, 30] == IGNORE


def test_failed_save_can_discard_and_close_and_leaves_no_temp_file(qapp, project, monkeypatch):
    window = LabelWindow(project)
    window.confirm = refuse
    window.resize(1000, 700)
    window.show()
    qapp.processEvents()
    first = window.current_id
    before = project.label(first)
    window.canvas.paint_stroke([(30, 30)], cls=IGNORE, radius=3)
    labels = project.path(first, "labels")
    os.chmod(labels, stat.S_IREAD)                    # dự án chép từ USB/giải nén với thuộc tính chỉ-đọc
    try:
        if sys.platform == "win32":                   # POSIX cho os.replace đè file chỉ-đọc (quyền ở thư mục)
            assert window.save_current() is None and "KHÔNG LƯU ĐƯỢC" in window.last_message
            assert not list(labels.parent.glob("*.tmp"))                            # file tạm được dọn
            window.confirm = lambda *_: False
            assert not window.close() and window.isVisible()
        else:
            monkeypatch.setattr(project, "save", lambda *_a, **_k: (_ for _ in ()).throw(OSError(13, "chỉ-đọc")))
        window.confirm = lambda *_: True                                           # chọn "Có": bỏ thay đổi, đóng
        assert window.close() and not window.isVisible()
    finally:
        os.chmod(labels, stat.S_IREAD | stat.S_IWRITE)
    assert np.array_equal(LabelProject(project.root).label(first), before)       # đĩa không đổi
    assert not list(project.root.rglob("*.tmp"))


def test_navigation_follows_the_list_after_autosave_demotes_a_reviewed_item(qapp, tmp_path):
    root = tmp_path / "ảnh sa bàn"
    write_snapshot(root, T0, ports=(1, 2, 3), probs={1: RAMP, 2: RAMP, 3: RAMP})
    project = LabelProject(tmp_path / "dự án nhãn", create=True, who="người duyệt")
    project.import_snapshots(root, log=None)
    a, b, c = project.ids()
    for item_id in (a, b, c):
        project.set_status(item_id, "reviewed")
    window = LabelWindow(project)
    window.confirm = refuse
    window.resize(1300, 800)
    window.show()
    qapp.processEvents()
    messages = []
    shown = window.notify
    window.notify = lambda text, error=False: (messages.append(text), shown(text, error))
    try:
        window.filter_box.setCurrentIndex(window.filter_box.findData("reviewed"))   # lượt xem lại ảnh đã duyệt
        assert window.item_list.count() == 3 and window.current_id == a
        drag(window, [(15, 30), (40, 30)])
        window.btn_next.click()                                   # tự lưu: A về nháp nhưng vẫn ở dòng 0 của danh sách
        assert window.current_id == b and project.item(a)["status"] == "draft"
        assert "nháp" in window.item_list.item(0).text() and window.item_list.count() == 3
        window.btn_next.click()
        assert window.current_id == c
        window.btn_prev.click()
        window.btn_prev.click()
        assert window.current_id == a and window.item_list.currentRow() == 0
        assert not any("đầu danh sách" in m for m in messages)
        QTest.keyClick(window.canvas, Qt.Key.Key_PageUp)          # đúng ở đầu danh sách thì mới báo
        assert window.current_id == a and "đầu danh sách" in window.last_message
    finally:
        window.close()


@pytest.mark.parametrize("interrupt", ["ctrl_z", "ctrl_y", "regenerate", "editor_undo"])
def test_undo_or_regenerate_during_a_drag_stops_painting(qapp, project, interrupt):
    window = LabelWindow(project)
    window.confirm = refuse
    window.resize(1300, 800)
    window.show()
    qapp.processEvents()
    try:
        editor, canvas = window.editor, window.canvas
        window.set_tool("brush")
        window.set_class(BLOCKED)
        canvas.setFocus()
        if interrupt == "ctrl_y":                                 # có gì đó để làm lại
            canvas.paint_stroke([(5, 80)], radius=2)
            window.undo()
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(window, 15, 30))
        QTest.mouseMove(canvas, at(window, 30, 30))
        assert editor.stroking and canvas._painting and editor.label[30, 30] == BLOCKED
        if interrupt == "ctrl_z":
            QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        elif interrupt == "ctrl_y":
            QTest.keyClick(canvas, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        elif interrupt == "regenerate":
            window.regenerate(keep_edits=True)
        else:
            editor.undo()                                         # đóng nét mà cửa sổ không biết: chỉ canvas tự nhận ra
        assert not editor.stroking
        before = editor.label.copy()
        for x in (45, 60):                                        # FREE trong nháp (nửa trái của RAMP)
            QTest.mouseMove(canvas, at(window, x, 30))            # không được ném "stroke_to trước begin_stroke"
        assert canvas._painting is False and not editor.stroking
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(window, 60, 30))
        assert np.array_equal(editor.label, before) and editor.label[30, 45] == FREE and editor.label[30, 60] == FREE
        drag(window, [(45, 30), (60, 30)])                        # nét kế tiếp vẫn tô bình thường
        assert editor.label[30, 45] == BLOCKED and editor.label[30, 60] == BLOCKED
    finally:
        window.close()


def test_main_reports_missing_project(tmp_path, capsys):
    assert main(["--project", str(tmp_path / "không có")]) == 2
    assert "import" in capsys.readouterr().err


@pytest.mark.parametrize("content", [b"", b"[]", b"\xff"])
def test_main_reports_a_broken_sidecar_by_name(tmp_path, capsys, content):
    root = tmp_path / "ảnh sa bàn"
    write_snapshot(root, T0, ports=(1, 2), probs={1: RAMP, 2: RAMP})
    project = LabelProject(tmp_path / "dự án", create=True)
    project.import_snapshots(root, log=None)
    broken = project.path(project.ids()[1], "items")
    broken.write_bytes(content)
    assert main(["--project", str(project.root)]) == 2
    err = capsys.readouterr().err
    assert broken.name in err and "sidecar" in err and "Traceback" not in err


def click_polygon(window, points):
    for point in points:
        QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(window, *point))


def test_unclosed_polygon_blocks_review_and_is_settled_before_leaving(qapp, project):
    """Ctrl+Enter (duyệt) nằm sát Enter (đóng đa giác): duyệt khi đa giác chưa đóng phải bị từ chối, không chốt nhãn
    thiếu vùng vừa khoanh; rời ảnh / đóng cửa sổ thì đa giác ≥ 3 đỉnh được tô kín, < 3 đỉnh bị bỏ — đều có báo."""
    window = LabelWindow(project)
    window.confirm = refuse
    window.resize(1300, 800)
    window.show()
    qapp.processEvents()
    try:
        first, editor, canvas = window.current_id, window.editor, window.canvas
        assert editor.label[50, 125] == BLOCKED                          # nửa phải của RAMP: nháp BLOCKED
        canvas.setFocus()
        QTest.keyClick(canvas, Qt.Key.Key_1)
        QTest.keyClick(canvas, Qt.Key.Key_G)
        click_polygon(window, ((100, 30), (150, 30), (150, 70), (100, 70)))
        QTest.keyClick(canvas, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)   # nhầm Ctrl+Enter
        assert window.current_id == first and len(canvas.polygon) == 4 and "chưa đóng" in window.last_message
        assert LabelProject(project.root).item(first)["status"] == "draft"
        window.btn_review.click()
        assert window.current_id == first and len(canvas.polygon) == 4 and "chưa đóng" in window.last_message
        assert LabelProject(project.root).item(first)["status"] == "draft"
        QTest.keyClick(canvas, Qt.Key.Key_Return)                         # đóng đa giác -> tô
        assert editor.label[50, 125] == FREE and not canvas.polygon
        QTest.keyClick(canvas, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        disk = LabelProject(project.root)
        assert window.current_id != first and disk.item(first)["status"] == "reviewed"
        assert disk.label(first)[50, 125] == FREE

        second = window.current_id                                        # rời ảnh giữa đa giác: tô kín + báo
        canvas.setFocus()
        click_polygon(window, ((100, 30), (150, 30), (150, 70)))
        QTest.keyClick(canvas, Qt.Key.Key_PageDown)
        assert window.current_id != second and "tô kín" in window.last_message
        disk = LabelProject(project.root)
        assert disk.label(second)[40, 140] == FREE and disk.item(second)["status"] == "draft"

        third = window.current_id                                         # 2 đỉnh: bỏ, có báo
        before = window.editor.label.copy()
        canvas.setFocus()
        click_polygon(window, ((100, 30), (150, 30)))
        window.close()
        assert "bỏ đa giác" in window.last_message and not canvas.polygon
        assert (LabelProject(project.root).label(third) == before).all()
    finally:
        window.close()


def send_mouse(widget, kind, pos: QPoint, button, buttons):
    event = QMouseEvent(kind, QPointF(pos), QPointF(widget.mapToGlobal(pos)), button, buttons,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def test_second_press_of_a_double_click_starts_a_brush_stroke_and_a_pan(qapp, project):
    """Qt giao cho widget Press, Release, DblClick, Release (lần nhấn thứ hai là DblClick): ở chế độ cọ nó phải bắt đầu
    một nét như lần nhấn thường — chấm một nhát rồi nhấn lại ngay để kéo tiếp không được mất nét."""
    window = LabelWindow(project)
    window.confirm = refuse
    window.resize(1300, 800)
    window.show()
    qapp.processEvents()
    try:
        canvas, editor = window.canvas, window.editor
        window.set_tool("brush")
        window.set_class(IGNORE)
        canvas.set_radius(2)
        left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
        send_mouse(canvas, QEvent.Type.MouseButtonPress, at(window, 20, 40), left, left)
        send_mouse(canvas, QEvent.Type.MouseButtonRelease, at(window, 20, 40), left, none)
        send_mouse(canvas, QEvent.Type.MouseButtonDblClick, at(window, 21, 40), left, left)
        send_mouse(canvas, QEvent.Type.MouseMove, at(window, 60, 40), none, left)
        send_mouse(canvas, QEvent.Type.MouseButtonRelease, at(window, 60, 40), left, none)
        assert editor.label[40, 20] == IGNORE and editor.label[40, 40] == IGNORE and editor.label[40, 60] == IGNORE
        assert len(editor.undo_stack) == 2                                 # chấm + nét kéo: hai bước hoàn tác

        right = Qt.MouseButton.RightButton                                 # nhấp đúp chuột phải rồi kéo: kéo khung nhìn
        offset = QPointF(canvas.offset)
        start = QPoint(300, 300)
        send_mouse(canvas, QEvent.Type.MouseButtonPress, start, right, right)
        send_mouse(canvas, QEvent.Type.MouseButtonRelease, start, right, none)
        send_mouse(canvas, QEvent.Type.MouseButtonDblClick, start, right, right)
        send_mouse(canvas, QEvent.Type.MouseMove, start + QPoint(40, 25), none, right)
        send_mouse(canvas, QEvent.Type.MouseButtonRelease, start + QPoint(40, 25), right, none)
        assert canvas.offset - offset == QPointF(40, 25)
    finally:
        window.close()


def test_ctrl_wheel_changes_the_brush_by_notches_not_by_event_count(qapp, project):
    window = LabelWindow(project)
    window.confirm = refuse
    window.resize(1300, 800)
    window.show()
    qapp.processEvents()
    try:
        canvas, ctrl = window.canvas, Qt.KeyboardModifier.ControlModifier
        r0 = canvas.radius
        for _ in range(10):                                               # bánh xe mịn: 10 sự kiện 12 = một nấc
            wheel(canvas, at(window, 80, 45), 12, ctrl)
        r1 = canvas.radius
        assert r1 == r0 + max(1, r0 // 5)
        for _ in range(24):                                               # touchpad chính xác: 24 sự kiện 5 = một nấc
            wheel(canvas, at(window, 80, 45), -5, ctrl)
        assert canvas.radius == r1 - max(1, r1 // 5)
        r2 = canvas.radius
        wheel(canvas, at(window, 80, 45), 60, ctrl)                       # nửa nấc: chưa đổi, phần lẻ giữ lại
        assert canvas.radius == r2
        wheel(canvas, at(window, 80, 45), 60, ctrl)
        assert canvas.radius == r2 + max(1, r2 // 5)
        scale = canvas.scale                                              # phóng to vẫn theo phân số nấc
        for _ in range(10):
            wheel(canvas, at(window, 80, 45), 12)
        assert canvas.scale == pytest.approx(scale * 1.25)
    finally:
        window.close()


def test_hover_coordinates_do_not_overwrite_notifications(qapp, project):
    window = LabelWindow(project)
    window.confirm = refuse
    window.resize(1300, 800)
    window.show()
    qapp.processEvents()
    try:
        window.item_list.setCurrentRow(window.item_list.count() - 1)
        window.go_relative(1)
        QTest.mouseMove(window.canvas, at(window, 20, 20))
        assert window.statusBar().currentMessage() == "Đã ở ảnh cuối danh sách"
        assert window.hover_label.text().startswith("x 20, y 20:")
    finally:
        window.close()


def test_fit_to_screen_shrinks_the_window_on_a_small_laptop_screen(qapp, project):
    window = LabelWindow(project)
    window.confirm = refuse
    try:
        assert (window.width(), window.height()) == (1600, 900)
        small = QRect(0, 0, 1536, 816)                                    # 1920×1080 ở 125 %, trừ thanh tác vụ
        fit_to_screen(window, small)
        assert window.width() <= 1536 - 40 and window.height() <= 816 - 80
        assert window.x() >= 0 and window.y() >= 0
        assert window.x() + window.width() + 40 <= 1536 and window.y() + window.height() + 80 <= 816
        fit_to_screen(window, QRect(0, 0, 2560, 1400))                    # màn hình lớn: giữ 1600×900
        assert (window.width(), window.height()) == (1600, 900)
    finally:
        window.close()


def test_stale_frame_shows_a_camera_frozen_warning(qapp, tmp_path):
    root = tmp_path / "ảnh sa bàn"
    folder = write_snapshot(root, T0, ports=(1, 2), probs={1: RAMP, 2: RAMP})
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    meta["cameras"]["1"].update({"age_ms": 1.79e6, "stale": True})       # camera 1 treo 30 phút
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    project = LabelProject(tmp_path / "dự án", create=True)
    project.import_snapshots(root, log=None)
    window = LabelWindow(project)
    window.confirm = refuse
    window.resize(1300, 800)
    window.show()
    qapp.processEvents()
    try:
        assert window.current_id.endswith("_p1")
        text = window.info.text()
        assert "KHUNG CŨ (camera treo)" in text and "KHUNG HỎNG" not in text
        assert not window.btn_damage.isEnabled()                          # không có vùng nào để tô
    finally:
        window.close()


def test_list_status_colours_are_readable_on_the_current_palette(qapp):
    """Chữ trạng thái phải tương phản với nền danh sách: chữ gần trắng trên nền trắng từng không đọc được (24/09)."""
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QListWidget
    from autopark.ui.label_app import status_color

    for base, text in (("#ffffff", "#000000"), ("#1e1e1e", "#ffffff")):
        widget = QListWidget()
        palette = widget.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(base))
        palette.setColor(QPalette.ColorRole.Text, QColor(text))
        widget.setPalette(palette)
        bg = QColor(base).lightness()
        assert status_color("draft", widget) is None                 # giữ màu chữ mặc định của bảng màu
        for status in ("reviewed", "rejected"):
            assert abs(status_color(status, widget).lightness() - bg) > 90, (base, status)
