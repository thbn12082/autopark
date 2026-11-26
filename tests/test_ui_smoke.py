"""Kiểm tra giao diện dựng được và luồng tính đường → xem trước → tự đỗ chạy được (offscreen)."""
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.application.session import SessionState  # noqa: E402
from autopark.domain.types import Pose  # noqa: E402
from autopark.ui.app import PROJECT_ROOT, build_window  # noqa: E402

# Các ca này kiểm luồng ô đỗ cũ; luồng mặc định thao tác gần ở test_maneuver.py.
DEFAULT_SCENARIO = PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_window_plans_previews_and_parks(qapp):
    window = build_window(DEFAULT_SCENARIO)
    assert window.session.state == SessionState.EDITING
    assert len(window._obstacle_items) == 3
    assert window.goal_item.isVisible()

    result = window.plan(sync=True)
    assert result is not None and result.ok
    assert window.session.state == SessionState.READY
    assert not window.path_item.boundingRect().isEmpty()

    window.preview()
    assert window.session.state == SessionState.PREPARING_PREVIEW
    window.session._preview_future.result(timeout=10)
    window._on_tick()
    assert window.session.state == SessionState.PREVIEW
    for _ in range(50):
        window._advance_preview(1.0)
    assert window._preview_index == len(window.session.preview.states) - 1
    window.stop()
    assert window.session.state == SessionState.READY

    window.run()
    assert window.session.state == SessionState.RUNNING
    for _ in range(400):
        window.advance_by(0.5)
        if not window.session.simulating:
            break
    assert window.session.state == SessionState.COMPLETED
    goal = window.session.scenario.goal.pose
    assert math.hypot(window.sim_item.pos().x() - goal.x, window.sim_item.pos().y() - goal.y) < 0.03
    assert window.bar.value() == 1000
    window._refresh_mode_widgets()
    assert window.primary_action.isEnabled()
    window.primary_action.click()
    assert window.session.state == SessionState.EDITING
    assert window.session.trajectory is None
    window.close()


def test_goal_drag_updates_pose_and_invalidates_plan(qapp):
    window = build_window(DEFAULT_SCENARIO)
    try:
        assert window.plan(sync=True).ok
        pose = Pose(.82, .84, 0)
        window.goal_item.set_pose(pose)
        window._on_goal_item_changed()
        assert window.session.state == SessionState.EDITING
        assert window.session.trajectory is None
        assert window.session.scenario.goal.pose == pose
    finally:
        window.close()


def test_add_and_remove_obstacle_via_window(qapp):
    window = build_window(DEFAULT_SCENARIO)
    window.combo_kind.setCurrentIndex(1)  # hộp
    window._add_obstacle()
    new_id = window.list_obstacles.currentItem().text()
    assert new_id in window._obstacle_items
    assert window.session.scenario.obstacle_by_id(new_id).kind == "box"
    window._remove_selected_obstacle()
    assert new_id not in window._obstacle_items
    window.close()


def test_manual_drive_still_available(qapp):
    window = build_window(DEFAULT_SCENARIO)
    window._start_manual()
    assert window.session.state == SessionState.MANUAL
    window.session.set_manual_targets(0.1, 0.0)
    for _ in range(20):
        window.advance_by(0.1)
    assert window.session.world.state.pose.x > window.session.scenario.start.x
    window.stop()
    assert window.session.state == SessionState.EDITING
    window.close()


def test_preview_keeps_qt_responsive_and_escape_cancels(qapp, monkeypatch):
    import threading
    from PySide6.QtCore import QEvent, QTimer, Qt
    from PySide6.QtGui import QKeyEvent
    from autopark.application import session as session_module
    from autopark.domain.computation import ComputationCancelled

    entered = threading.Event()

    def preview(*args, control, **kwargs):
        entered.set()
        assert control.cancel_event.wait(3)
        control.check()

    window = build_window(DEFAULT_SCENARIO)
    try:
        assert window.plan(sync=True).ok
        monkeypatch.setattr(session_module, "rollout", preview)
        window.preview()
        future = window.session._preview_future
        assert entered.wait(1)
        assert window.session.state == SessionState.PREPARING_PREVIEW
        assert window.primary_action.isEnabled()
        assert "Hủy" in window.primary_action.text()
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        qapp.processEvents()
        assert heartbeat, "Qt event loop was blocked by preview computation"
        assert not future.done()
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        assert window._handle_key(event)
        assert window.session.state == SessionState.READY
        with pytest.raises(ComputationCancelled):
            future.result(timeout=1)
        assert window.session.preview is None
    finally:
        window.close()


def test_cockpit_primary_action_follows_the_parking_flow(qapp):
    window = build_window(DEFAULT_SCENARIO)
    try:
        assert "Tính thao tác" in window.primary_action.text()
        window.primary_action.click()
        assert window.session.state == SessionState.PLANNING
        assert "Hủy" in window.primary_action.text()
        window.session._plan_future.result(timeout=10)
        window._on_tick()
        assert window.session.state == SessionState.READY
        assert "Thực hiện" in window.primary_action.text()
        window.primary_action.click()
        assert window.session.state == SessionState.RUNNING
        assert "Dừng" in window.primary_action.text()
        window.primary_action.click()
        assert window.session.state == SessionState.STOPPING
    finally:
        window.close()


def test_clicking_floor_places_goal_and_escape_closes_inspector(qapp):
    from PySide6.QtCore import QPointF, QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    window = build_window(DEFAULT_SCENARIO)
    try:
        window.show()
        qapp.processEvents()
        assert window._place_goal(QPointF(.75, .8))
        assert window.session.scenario.goal.pose.x == pytest.approx(.75)
        assert not window._place_goal(QPointF(-1, -1))
        window.settings_action.click()
        assert window.drawer.isVisible()
        assert window._handle_key(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        assert window.drawer.isHidden()
    finally:
        window.close()


def test_runtime_fault_controls_and_recovery(qapp):
    window = build_window(DEFAULT_SCENARIO)
    try:
        assert window.plan(sync=True).ok
        window.run()
        window.advance_by(0.5)
        window.btn_inject.click()
        assert window.session.state == SessionState.STOPPING
        assert window.path_item.boundingRect().isEmpty()
        for _ in range(30):
            window.advance_by(0.1)
            if not window.session.simulating:
                break
        assert window.session.state == SessionState.STOPPED
        window._refresh_mode_widgets()
        assert not window.btn_save_run.isHidden()
        pose = window.session.world.state.pose
        window.primary_action.click()
        assert window.session.state == SessionState.EDITING
        assert window.session.scenario.start == pose
        assert window.start_item.pose() == pose
    finally:
        window.close()
