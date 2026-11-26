import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from autopark.application.session import SessionState
from autopark.domain.types import Obstacle
from autopark.storage.scenario_store import load_scenario, save_scenario
from autopark.ui.app import PROJECT_ROOT, build_window

# Bộ xe đỗ phục vụ kiểm kéo/xoay; không phụ thuộc tình huống khởi động ứng dụng.
DEFAULT_SCENARIO = PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json"


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    w = build_window(DEFAULT_SCENARIO)
    w.session.add_obstacle(Obstacle("xe_1", 0.15, 1.3, 0.15, 0.10, kind="car"))
    w._rebuild_scene()
    w._refresh_all()
    w.show()
    app.processEvents()
    yield w
    w.close()


def select_car(window, name="xe_1"):
    item = window._obstacle_items[name]
    point = window.view.mapFromScene(item.scenePos())
    QTest.mouseClick(window.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert item.isSelected()
    assert window.list_obstacles.currentItem().text() == name
    assert window.object_editor.isVisible()
    return item


def test_numeric_pose_edits_update_geometry_invalidate_path_and_survive_save(window, tmp_path):
    assert window.plan(sync=True).ok
    item = select_car(window)
    window.quick_yaw.setValue(37.5)
    assert window.session.state == SessionState.EDITING
    assert window.session.trajectory is None
    assert math.degrees(window.session.scenario.obstacle_by_id("xe_1").yaw) == pytest.approx(37.5)
    assert item.rotation() == pytest.approx(37.5)
    assert window.obs_yaw.value() == pytest.approx(37.5)
    window.obs_x.setValue(15.0)
    window.obs_y.setValue(130.0)
    assert item.pos() == QPointF(0.15, 1.3)
    saved = save_scenario(window.session.scenario, tmp_path / "mixed.json")
    restored = load_scenario(saved).obstacle_by_id("xe_1")
    assert restored.cx == 0.15 and restored.cy == 1.3
    assert math.degrees(restored.yaw) == pytest.approx(37.5)


def test_dragging_rotation_handle_changes_only_the_car_angle(window):
    item = select_car(window)
    original_position = item.pos()
    handle = item._rotation_handle
    assert handle.isVisible()
    start = window.view.mapFromScene(handle.scenePos())
    radius = handle.pos().x()
    target = original_position + QPointF(radius * math.cos(math.radians(35)),
                                        radius * math.sin(math.radians(35)))
    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.view.viewport(), window.view.mapFromScene(target), delay=10)
    QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton,
                       pos=window.view.mapFromScene(target))
    assert item.pos() == original_position
    assert math.degrees(window.session.scenario.obstacle_by_id("xe_1").yaw) == pytest.approx(35, abs=1.5)
    assert window.quick_yaw.value() == pytest.approx(35, abs=1.5)
    assert window.view.transform().m12() == window.view.transform().m21() == 0


def test_keyboard_rotation_and_drive_lock(window):
    item = select_car(window)
    angle = item.rotation()
    assert window._handle_key(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_E, Qt.KeyboardModifier.ShiftModifier))
    assert item.rotation() == pytest.approx(angle + 1)
    before = window.session.scenario.obstacle_by_id("xe_1")
    window._start_manual()
    assert window.object_editor.isHidden()
    assert not item._rotation_handle.isVisible()
    window._rotate_selected(30)
    assert window.session.scenario.obstacle_by_id("xe_1") == before
