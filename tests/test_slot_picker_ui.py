"""Nút "Tìm ô đỗ" của cửa sổ chính (autopark.ui.slot_picker): tìm, vẽ, bấm chọn ô làm đích, đổi kiểu đỗ."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("cv2")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.application.session import SessionState  # noqa: E402
from autopark.domain.types import Obstacle, ParkingMode  # noqa: E402
from autopark.planning import slot_finder as sf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "tim_khe_vuong_goc.json"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    from autopark.ui.app import build_window
    w = build_window(SCENARIO)
    w._timer.stop()
    w.resize(1440, 900)
    w.show()
    qapp.processEvents()
    yield w
    w.close()


def found(window):
    window.find_slots()
    assert window.slot_picker.busy and not window.find_slots_action.isEnabled()
    assert window.slot_picker.wait(60)
    window.slot_picker.refresh()
    return window.slot_picker


def test_find_and_pick_slot_far_beyond_near_limit(window):
    assert window.session.cfg.width == pytest.approx(0.16)          # tim_khe_* dùng xe đo thật
    picker = found(window)
    assert window.find_slots_action.isEnabled() and window.find_slots_action.text() == "Tìm ô đỗ"
    perp = [i for i, c in enumerate(picker.candidates) if c.kind == sf.PERPENDICULAR and not c.boundary_unknown]
    assert len(perp) >= 2 and len(picker.items) == len(picker.candidates)
    assert all(item.scene() is window.scene for item in picker.items)

    far = max(perp, key=lambda i: picker.candidates[i].distance_m)
    assert picker.candidates[far].distance_m > 0.7
    assert picker.pick(far)
    sc = window.session.scenario
    goal = picker.candidates[far].goal_pose(window.session.cfg, ParkingMode.REVERSE_IN, sc.start.yaw)
    assert sc.goal.pose == goal
    assert sc.maneuver.max_goal_distance_m > sc.start.distance_to(goal) > 0.7     # không còn mức 0,7 m
    assert window.session.goal_check().ok
    assert picker.items[far].chosen and sum(item.chosen for item in picker.items) == 1

    assert picker.pick(far)                                           # bấm lại: đổi sang tiến vào
    assert sc.goal.pose == picker.candidates[far].goal_pose(window.session.cfg, ParkingMode.HEAD_IN, sc.start.yaw)
    assert picker.pick(far)
    assert sc.goal.pose == goal

    result = window.session.plan_sync()
    assert result.ok, result.message
    assert window.session.state == SessionState.READY


def test_click_on_slot_picks_it_instead_of_moving_goal(window, qapp):
    picker = found(window)
    index = 0
    item = picker.items[index]
    window.view.fit_scene()
    qapp.processEvents()
    point = window.view.mapFromScene(item.scenePos())
    QTest.mouseClick(window.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    cand = picker.candidates[index]
    assert picker.chosen == index
    expected = cand.goal_pose(window.session.cfg, cand.modes[0], window.session.scenario.start.yaw)
    assert window.session.scenario.goal.pose == expected


def test_blocked_slot_is_refused_and_vehicle_change_drops_slots(window):
    picker = found(window)
    index = next(i for i, c in enumerate(picker.candidates) if c.kind == sf.PERPENDICULAR)
    sl = picker.candidates[index].slot
    window._edit(lambda: window.session.add_obstacle(Obstacle("chan", sl.cx, sl.cy, 0.1, 0.1, 0.0)))
    assert picker.items, "vật cản đổi: ô vẫn hiện"
    before = window.session.scenario.goal.pose
    assert not picker.pick(index)
    assert window.session.scenario.goal.pose == before
    assert "không còn trống" in window.statusBar().currentMessage()

    window.slot_picker.signature = ("khac",)                          # như vừa đổi xe hay biên sa bàn
    window._refresh_mode_widgets()
    assert not picker.items and not picker.candidates
