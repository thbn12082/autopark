"""Tự tìm ô đỗ trên bản đồ lưới (autopark.planning.slot_finder), trên bản đồ vẽ thẳng từ hình chữ nhật."""
from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("cv2")

from autopark.domain.types import ParkingMode, Pose, VehicleConfig
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec
from autopark.planning import slot_finder as sf

CFG = VehicleConfig(name="thu", wheelbase=0.19, width=0.14, front_overhang=0.06, rear_overhang=0.06,
                    max_steer=math.radians(30), max_speed=0.3, max_accel=0.3, max_decel=0.6,
                    max_steer_rate=math.radians(90))
RES = 0.02


def raster(xmax, ymax, boxes, *, walls=True, unknown_boxes=()):
    """Sa bàn [0, xmax] × [0, ymax] trống, tường biên dày một ô, hộp (xmin, ymin, xmax, ymax) OCCUPIED."""
    grid = GridSpec(-2 * RES, round(xmax + 2 * RES, 6), -2 * RES, round(ymax + 2 * RES, 6), RES)
    gx, gy = grid.centers()
    states = np.full(grid.shape, UNKNOWN, np.int8)
    inside = (gx >= 0) & (gx <= xmax) & (gy >= 0) & (gy <= ymax)
    states[inside] = FREE
    if walls:
        edge = inside & ((gx < RES) | (gx > xmax - RES) | (gy < RES) | (gy > ymax - RES))
        states[edge] = OCCUPIED
    for value, rects in ((OCCUPIED, boxes), (UNKNOWN, unknown_boxes)):
        for x0, y0, x1, y1 in rects:
            states[(gx >= x0) & (gx <= x1) & (gy >= y0) & (gy <= y1)] = value
    return states, grid


def perpendicular_map():
    # ba "xe" vuông góc sát tường trên (y = 1.0): khe A rộng 0.26 m quanh x = 0.6, khe B rộng 0.11 m quanh x = 0.935
    cars = [(0.33, 0.68, 0.47, 1.0), (0.73, 0.68, 0.87, 1.0), (0.98, 0.68, 1.12, 1.0)]
    return raster(1.4, 1.0, cars)


def test_perpendicular_slot_centred_against_wall():
    states, grid = perpendicular_map()
    slots = [c for c in sf.find_slots(states, grid, CFG, kinds=(sf.PERPENDICULAR,))
             if 0.4 < c.slot.cx < 1.2]
    assert len(slots) == 1, [c.to_dict() for c in slots]
    slot = slots[0].slot
    assert abs(slot.cx - 0.60) < 0.02
    assert abs(math.degrees(slot.yaw) - 90) < 1           # trục ô hướng từ miệng vào đáy (tường y = 1.0)
    assert 1.0 - RES - (slot.cy + slot.length / 2) < 0.03  # đáy ô áp sát tường
    assert slots[0].modes == (ParkingMode.REVERSE_IN, ParkingMode.HEAD_IN)
    assert 0.0 <= slots[0].slack_width_m <= 0.08
    assert not slots[0].boundary_unknown


def test_parallel_slot_against_kerb():
    # lề là tường dưới (y = 0); hai xe dọc lề, khe dài 0.51 m giữa x = 0.45 và 0.96
    states, grid = raster(1.6, 1.0, [(0.14, 0.0, 0.45, 0.17), (0.96, 0.0, 1.27, 0.17)])
    slots = [c for c in sf.find_slots(states, grid, CFG, kinds=(sf.PARALLEL,)) if 0.45 < c.slot.cx < 0.96]
    assert len(slots) == 1, [c.to_dict() for c in slots]
    c = slots[0]
    assert abs(c.slot.cx - 0.705) < 0.02
    assert c.slot.cy - c.slot.width / 2 < 0.05                 # áp sát lề
    assert abs(math.sin(c.slot.yaw)) < 0.02                    # dọc lề
    assert 0.08 <= c.slack_length_m <= 0.16
    assert c.modes == (ParkingMode.PARALLEL,)


def test_open_floor_has_no_slot():
    states, grid = raster(1.5, 1.5, [])
    assert sf.find_slots(states, grid, CFG) == []


def test_slot_bounded_only_by_unknown_is_flagged():
    cars = [(0.33, 0.68, 0.47, 1.0)]
    states, grid = raster(1.4, 1.0, cars, unknown_boxes=[(0.73, 0.68, 0.87, 1.0)])
    slots = [c for c in sf.find_slots(states, grid, CFG, kinds=(sf.PERPENDICULAR,)) if 0.45 < c.slot.cx < 0.75]
    assert slots and all(c.boundary_unknown for c in slots)


def test_sorted_by_distance_without_range_limit():
    states, grid = perpendicular_map()
    start = Pose(1.25, 0.35, math.pi)
    slots = sf.find_slots(states, grid, CFG, vehicle_pose=start)
    assert slots
    dist = [c.distance_m for c in slots if not c.boundary_unknown]
    assert dist == sorted(dist)
    assert any(d > 0.7 for d in dist)                           # không bỏ ô xa hơn 0,7 m


def test_clear_vehicle_frees_unknown_under_car():
    states, grid = raster(1.0, 1.0, [], unknown_boxes=[(0.3, 0.4, 0.7, 0.6)])
    out = sf.clear_vehicle(states, grid, CFG, Pose(0.4, 0.5, 0.0))
    r, c = grid.index(0.5, 0.5)
    assert states[r, c] == UNKNOWN and out[r, c] == FREE
    r, c = grid.index(0.69, 0.59)                               # ngoài thân xe
    assert out[r, c] == UNKNOWN


def test_planner_reaches_found_slot():
    states, grid = perpendicular_map()
    start = Pose(1.2, 0.35, math.pi)
    slots = [c for c in sf.find_slots(states, grid, CFG, kinds=(sf.PERPENDICULAR,), vehicle_pose=start)
             if 0.4 < c.slot.cx < 1.2]
    sf.verify_with_planner(slots, states, grid, CFG, start, time_limit=8.0, max_candidates=1)
    results = slots[0].verify
    assert set(results) == {"reverse_in", "head_in"}
    assert any(v["status"] == "OK" for v in results.values()), results
