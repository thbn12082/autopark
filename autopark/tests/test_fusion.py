"""Sensor-fusion layers, fusion rules, rectangle cover and the bridge into the phase-0 session (no hardware)."""
import math

import pytest

np = pytest.importorskip("numpy")

from autopark.application.session import Session, SessionState  # noqa: E402
from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose  # noqa: E402
from autopark.fusion.bridge import ObstacleBridge  # noqa: E402
from autopark.fusion.fuse import fuse  # noqa: E402
from autopark.fusion.layers import (LiveLidarLayer, NearFieldLayer, NearFieldMount, NearFieldReading, ScanUnion,  # noqa: E402
                                    StaticMapLayer, read_costmap_json, resample, sensor_pose_in_map, write_costmap_json)
from autopark.fusion.obstacles import (costmap_to_obstacles, count_objects, label_clusters, new_obstacles,  # noqa: E402
                                       rectangle_cover)
from autopark.lidar.occupancy import OccupancyCounts, write_outputs  # noqa: E402
from autopark.lidar.rplidar_protocol import wrap_angle  # noqa: E402
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec, to_costmap  # noqa: E402

GRID = GridSpec(0.0, 3.0, 0.0, 2.0, 0.05)          # the conftest bounds, 5 cm cells


def scan_with_object(t: float, distance: float | None, angle_deg: float = 0.0, half_width_deg: float = 10.0,
                     n: int = 360, source_id: str = "lidar") -> LidarScan:
    """No returns anywhere except an object of the given angular width; None = nothing seen at all."""
    angles = wrap_angle(-math.pi + 2 * math.pi * np.arange(n) / n)
    ranges = np.full(n, np.nan)
    if distance is not None:
        ranges[np.abs(wrap_angle(angles - math.radians(angle_deg))) <= math.radians(half_width_deg)] = distance
    return LidarScan(SourceStamp(source_id, t, True, "lidar"), tuple(angles.tolist()), tuple(ranges.tolist()))


def finish(session):
    for _ in range(1500):
        session.advance(0.1)
        if not session.simulating:
            return
    pytest.fail("Phiên không kết thúc")


def test_rig_map_transform_with_known_positions():
    pose = Pose(1.0, 0.5, math.pi / 2)                                 # vehicle facing +y, sensor 0.1 m ahead of it
    assert sensor_pose_in_map(pose, (0.1, 0.0, 0.0)) == pytest.approx((1.0, 0.6, math.pi / 2))
    layer = LiveLidarLayer(GRID, mount=(0.1, 0.0, 0.0), max_age_s=0.3, min_hits=1)
    costmap = layer.add_scan(scan_with_object(1.0, 0.98), pose)        # 0.98 m ahead of the sensor: map (1.0, 1.58)
    states = np.array(costmap.cells)
    assert states[GRID.index(1.0, 1.58)] == OCCUPIED
    persistent = LiveLidarLayer(GRID, mount=(0.1, 0.0, 0.0))            # default: a cell needs 2 hits in 3 scans
    assert persistent.min_hits == 2 and LiveLidarLayer(GRID, window=1).min_hits == 1
    once = np.array(persistent.add_scan(scan_with_object(1.0, 0.98), pose).cells)
    assert once[GRID.index(1.0, 1.58)] == UNKNOWN                        # one flickering hit is not an obstacle yet
    twice = np.array(persistent.add_scan(scan_with_object(1.1, 0.98), pose).cells)
    assert twice[GRID.index(1.0, 1.58)] == OCCUPIED
    assert states[GRID.index(1.0, 1.1)] == FREE                          # on the ray between sensor and object
    assert states[GRID.index(0.5, 0.5)] == UNKNOWN and states[GRID.index(1.0, 1.9)] == UNKNOWN
    assert costmap.stamp.frame_id == "map" and layer.fresh(1.2) and not layer.fresh(1.5)
    assert layer.status(1.2)["age_s"] == pytest.approx(0.2)


def test_live_lidar_ignores_blind_zone_and_its_own_vehicle_body(cfg):
    pose = Pose(1.0, 1.0, 0.0)
    body = LiveLidarLayer(GRID, self_mask=cfg, mask_margin=0.05, min_hits=1)      # body: -0.06..0.25 m ahead, ±0.07 m
    scan = scan_with_object(1.0, 0.2, half_width_deg=5.0)                          # a "return" 0.2 m ahead: inside the body
    states = np.array(body.add_scan(scan, pose).cells)
    assert (states == OCCUPIED).sum() == 0 and body.masked_beams > 0
    plain = LiveLidarLayer(GRID, min_hits=1)
    assert (np.array(plain.add_scan(scan, pose).cells) == OCCUPIED).sum() > 0    # without the mask it is an obstacle
    far = np.array(body.add_scan(scan_with_object(1.1, 0.5, half_width_deg=5.0), pose).cells)
    assert far[GRID.index(1.5, 1.0)] == OCCUPIED                                   # 0.5 m ahead: outside body + margin
    blind = np.array(LiveLidarLayer(GRID, min_hits=1).add_scan(scan_with_object(1.2, 0.03, half_width_deg=5.0), pose).cells)
    assert (blind == OCCUPIED).sum() == 0                                          # below the 0.05 m blind zone


def test_scan_union_counts_scans_not_beams():
    union = ScanUnion(GRID)
    pose = (0.5, 1.0, 0.0)
    union.add(scan_with_object(0.0, 1.0, half_width_deg=8.0), pose)          # many beams of ONE scan hit the same cells
    union.add(scan_with_object(0.1, None), pose)
    union.add(scan_with_object(0.2, None), pose)
    assert union.count == 3 and union.scans_hit.max() == 1
    once = union.states(min_hits=2)
    assert (once == OCCUPIED).sum() == 0 and (union.states(min_hits=1) == OCCUPIED).sum() > 0
    union.add(scan_with_object(0.3, 1.0, half_width_deg=8.0), pose)
    twice = union.states(min_hits=2)
    assert twice[GRID.index(1.5, 1.0)] == OCCUPIED and twice[GRID.index(1.0, 1.0)] == FREE
    costmap = union.costmap(SourceStamp("bench_static", 0.3, True, "map"))
    assert costmap.stamp.frame_id == "map" and np.array(costmap.cells).tolist() == twice.tolist()


def test_fusion_rules_and_validity():
    grid = GridSpec(0.0, 1.0, 0.0, 1.0, 0.5)
    static = StaticMapLayer("static")
    static.set(to_costmap(np.array([[FREE, OCCUPIED], [UNKNOWN, FREE]], np.int8), grid, SourceStamp("s", 0.0, True, "map")))
    live = LiveLidarLayer(grid, max_age_s=0.2)
    live.set(to_costmap(np.array([[OCCUPIED, FREE], [FREE, UNKNOWN]], np.int8), grid, SourceStamp("l", 1.0, True, "map")))
    result = fuse([static, live], grid, now=1.1)
    assert result.valid and result.states.tolist() == [[OCCUPIED, OCCUPIED], [FREE, FREE]]
    assert result.counts() == {"free": 2, "occupied": 2, "unknown": 0} and result.costmap.stamp.valid
    stale = fuse([static, live], grid, now=1.5)                          # required live layer too old
    assert not stale.valid and stale.reasons == ["live_lidar: quá cũ (0.500 s > 0.200 s)"]
    assert stale.costmap.blocked(1, 0) and stale.costmap.blocked(0, 0)   # invalid map blocks everything
    assert stale.states.tolist() == [[FREE, OCCUPIED], [UNKNOWN, FREE]]  # what the static layer alone says
    live.required = False
    assert fuse([static, live], grid, now=1.5).valid
    assert fuse([LiveLidarLayer(grid)], grid, now=0.0).reasons == ["live_lidar: chưa có dữ liệu"]
    with pytest.raises(ValueError, match="frame"):
        live.set(to_costmap(np.zeros((2, 2), np.int8), grid, SourceStamp("l", 1.0, True, "vehicle")))
    with pytest.raises(ValueError):
        fuse([], grid, now=0.0)


def test_resample_between_grids_and_frames():
    src_grid = GridSpec(0.0, 1.0, 0.0, 1.0, 0.5)
    src = to_costmap(np.array([[FREE, OCCUPIED], [UNKNOWN, FREE]], np.int8), src_grid, SourceStamp("cam", 0.0, True, "vehicle"))
    dst = GridSpec(0.0, 3.0, 0.0, 3.0, 0.5)
    states = resample(src, dst, pose=Pose(2.0, 1.0, math.pi / 2))     # vehicle at (2, 1) facing +y
    assert states[dst.index(1.75, 1.75)] == OCCUPIED                     # vehicle cell (row 0, col 1) lands here
    assert states[dst.index(1.75, 1.25)] == FREE                         # vehicle cell (row 0, col 0)
    assert states[dst.index(0.25, 0.25)] == UNKNOWN                      # outside the source costmap
    same = resample(src, src_grid)
    assert same.tolist() == [[FREE, OCCUPIED], [UNKNOWN, FREE]]


def test_static_layer_round_trips_through_costmap_json(tmp_path):
    grid = GridSpec(-1.0, 1.0, -1.0, 1.0, 0.25)
    counts = OccupancyCounts(grid)
    counts.add_scan(scan_with_object(0.0, 0.6, half_width_deg=30.0), max_range=5.0)
    states = counts.states(min_passes=1, min_hits=1, occupied_ratio=0.0)
    write_outputs(counts, states, tmp_path / "m", source="synthetic", source_id="lidar", t=1.0)
    layer = StaticMapLayer()
    loaded = layer.load(tmp_path / "m" / "costmap.json")
    assert np.array(loaded.cells).tolist() == states.tolist() and loaded.stamp.frame_id == "map"
    assert layer.fresh(1e9) and layer.status(5.0)["max_age_s"] is None
    again = read_costmap_json(write_costmap_json(tmp_path / "again.json", loaded, {"note": "round trip"}))
    assert again == loaded


def test_rectangle_cover_is_exact_and_disjoint():
    rng = np.random.default_rng(0)
    mask = rng.random((12, 15)) < 0.4
    cover = np.zeros(mask.shape, int)
    for r0, c0, r1, c1 in rectangle_cover(mask):
        cover[r0:r1 + 1, c0:c1 + 1] += 1
    assert (cover == mask.astype(int)).all()                            # each blocked cell exactly once
    assert rectangle_cover(np.array([[1, 1, 0], [1, 0, 0]], bool)) == [(0, 0, 0, 1), (1, 0, 1, 0)]
    assert rectangle_cover(np.ones((3, 2), bool)) == [(0, 0, 2, 1)]
    assert rectangle_cover(np.zeros((2, 2), bool)) == []


def test_clusters_count_objects_not_rectangles():
    mask = np.zeros((6, 8), bool)
    mask[0, 0:5] = True            # a wall along the top row ...
    mask[1, 4] = True              # ... turning down (8-connected corner)
    mask[4, 1] = True              # a lone speck
    mask[3:5, 6:8] = True          # a 2x2 box
    labels, count = label_clusters(mask)
    assert count == 3 and labels[0, 0] == labels[1, 4] and labels[4, 1] != labels[3, 6]
    assert len(rectangle_cover(mask)) == 4                                # the wall alone needs two rectangles
    grid = GridSpec(0.0, 0.8, 0.0, 0.6, 0.1)
    states = np.full(grid.shape, FREE, np.int8)
    states[mask] = OCCUPIED
    costmap = to_costmap(states, grid, SourceStamp("f", 0.0, True, "map"))
    assert count_objects(costmap) == {"cells": 11, "objects": 3, "rectangles": 4}
    assert count_objects(costmap, bounds=Bounds(0.0, 0.0, 0.8, 0.25))["objects"] == 1   # only the wall's rows
    assert label_clusters(np.zeros((2, 2), bool))[1] == 0


def test_costmap_to_obstacles_positions_bounds_and_new_information():
    grid = GridSpec(0.0, 1.0, 0.0, 1.0, 0.1)
    states = np.full(grid.shape, FREE, np.int8)
    states[2:4, 4:7] = OCCUPIED
    states[8, 0] = UNKNOWN
    costmap = to_costmap(states, grid, SourceStamp("f", 0.0, True, "map"))
    obstacles = costmap_to_obstacles(costmap, prefix="lidar")
    assert len(obstacles) == 1
    box = obstacles[0]
    assert (box.cx, box.cy, box.width, box.height) == pytest.approx((0.55, 0.3, 0.3, 0.2))
    assert box.id == "lidar_00000" and box.kind == "box"
    with_unknown = costmap_to_obstacles(costmap, include_unknown=True)
    assert len(with_unknown) == 2 and (with_unknown[1].cx, with_unknown[1].cy) == pytest.approx((0.05, 0.85))
    assert with_unknown[1].kind == "unknown" and with_unknown[1].id == "fused_00001"
    assert costmap_to_obstacles(costmap, bounds=Bounds(0.0, 0.0, 0.3, 1.0)) == []
    other = Obstacle("o", 0.2, 0.2, 0.1, 0.1)
    assert new_obstacles([box], [Obstacle("same", 0.55, 0.3, 0.3, 0.2), other]) == [other]
    assert new_obstacles([], [other]) == [other]
    edge = Obstacle("edge", 0.75, 0.3, 0.1, 0.1)                          # touching the box: flicker, not news
    assert new_obstacles([box], [edge], margin=0.1) == [] and new_obstacles([box], [edge]) == [edge]
    assert new_obstacles([box], [Obstacle("far", 0.95, 0.3, 0.1, 0.1)], margin=0.1) != []


def test_near_field_layer_marks_arc_only_when_valid():
    layer = NearFieldLayer(GRID, {"tof_front": NearFieldMount(0.25, 0.0, 0.0, 25.0)}, required=True)
    pose = Pose(1.0, 1.0, 0.0)
    costmap = layer.add_reading(NearFieldReading(SourceStamp("esp32", 2.0), "tof_front", 0.3, 4.0), pose)
    states = np.array(costmap.cells)
    assert states[GRID.index(1.55, 1.0)] == OCCUPIED                     # 0.25 m mount + 0.3 m range
    assert states[GRID.index(1.4, 1.0)] == UNKNOWN and (states == FREE).sum() == 0   # never FREE from a ToF
    assert fuse([layer], GRID, now=2.1).valid
    invalid = layer.add_reading(NearFieldReading(SourceStamp("esp32", 2.2), "tof_front", math.nan, 4.0, valid=False), pose)
    assert not invalid.stamp.valid and (np.array(invalid.cells) == OCCUPIED).sum() == 0
    result = fuse([layer], GRID, now=2.25)
    assert not result.valid and result.reasons == ["near_field: nguồn báo không hợp lệ"]
    far = layer.add_reading(NearFieldReading(SourceStamp("esp32", 2.3), "tof_front", 5.0, 4.0), pose)
    assert far.stamp.valid and (np.array(far.cells) == OCCUPIED).sum() == 0
    with pytest.raises(KeyError):
        layer.add_reading(NearFieldReading(SourceStamp("esp32", 2.4), "tof_left", 0.5, 4.0), pose)


def straight_session(scenario, cfg):
    scenario.obstacles = []
    scenario.start = Pose(0.5, 1.0, 0.0)
    scenario.goal = ParkingGoal(Pose(2.0, 1.0, 0.0))
    session = Session(scenario, cfg)
    assert session.plan_sync().ok
    return session


def test_live_lidar_obstacle_stops_the_running_session_then_replans(scenario, cfg):
    session = straight_session(scenario, cfg)
    session.start_run()
    session.advance(1)
    before = session.world.state
    assert abs(before.speed) > 0.05
    layer = LiveLidarLayer(GRID, max_age_s=0.3)
    bridge = ObstacleBridge(session, prefix="lidar")
    layer.add_scan(scan_with_object(before.t, None), before.pose)      # sees nothing: no obstacle, no stop
    assert bridge.inject(fuse([layer], GRID, now=before.t)) == [] and session.state == SessionState.RUNNING
    scan = scan_with_object(before.t + 0.1, 0.6, half_width_deg=8.0)  # something 0.6 m ahead of the rear axle
    layer.add_scan(scan, before.pose)
    assert bridge.inject(fuse([layer], GRID, now=scan.stamp.t)) == []  # seen once: not persistent yet, no stop
    scan = scan_with_object(before.t + 0.2, 0.6, half_width_deg=8.0)
    layer.add_scan(scan, before.pose)
    fused = fuse([layer], GRID, now=scan.stamp.t)
    added = bridge.inject(fused)
    assert added and session.state == SessionState.STOPPING and not session.trajectory.valid
    x, y = before.pose.to_world(0.6, 0.0)
    assert any(abs(o.cx - x) < 0.1 and abs(o.cy - y) < 0.1 for o in added)
    assert all(o.id.startswith("lidar_") and o.kind == "box" for o in session.scenario.obstacles)
    assert bridge.inject(fused) == []                                    # same information again adds nothing
    later = scan_with_object(before.t + 0.3, 0.9, angle_deg=-30.0, half_width_deg=8.0)   # another object while braking
    layer.add_scan(later, before.pose)
    layer.add_scan(scan_with_object(before.t + 0.4, 0.9, angle_deg=-30.0, half_width_deg=8.0), before.pose)
    more = bridge.inject(fuse([layer], GRID, now=before.t + 0.4))
    ids = [o.id for o in session.scenario.obstacles]
    assert len(ids) == len(set(ids)) and all(o.id in ids for o in more)  # ids never collide across injections
    finish(session)
    assert session.state == SessionState.STOPPED and not session.world.collided and session.world.state.speed == 0
    assert [e.code for e in session.safety_events] == ["MAP_CHANGED", "WAIT_REPLAN"]
    session.reset()
    assert session.plan_sync().ok                                        # the LiDAR obstacle stays in the scenario


def test_sync_incremental_follows_the_live_scan(scenario, cfg):
    session = straight_session(scenario, cfg)
    session.reset()                                                   # back to EDITING
    layer = LiveLidarLayer(GRID, window=1)                            # window 1: the map is exactly the last scan
    bridge = ObstacleBridge(session, prefix="lidar")
    layer.add_scan(scan_with_object(0.0, 0.8, angle_deg=50.0, half_width_deg=8.0), Pose(0.5, 1.0, 0.0))
    added, removed = bridge.sync_incremental(fuse([layer], GRID, now=0.0))
    assert added and removed == [] and len(bridge.owned()) == len(added)
    first_ids = {o.id for o in added}

    layer.add_scan(scan_with_object(0.1, 0.8, angle_deg=50.0, half_width_deg=8.0), Pose(0.5, 1.0, 0.0))
    again, gone = bridge.sync_incremental(fuse([layer], GRID, now=0.1))
    assert again == [] and gone == []                                 # unchanged scene: the same boxes are kept
    assert {o.id for o in bridge.owned()} == first_ids

    layer.add_scan(scan_with_object(0.2, 0.8, angle_deg=-50.0, half_width_deg=8.0), Pose(0.5, 1.0, 0.0))
    moved, dropped = bridge.sync_incremental(fuse([layer], GRID, now=0.2))
    assert moved and dropped and {o.id for o in dropped} == first_ids
    assert {o.id for o in bridge.owned()} == {o.id for o in moved}
    assert len({o.id for o in session.scenario.obstacles}) == len(session.scenario.obstacles)

    layer.add_scan(scan_with_object(0.3, None), Pose(0.5, 1.0, 0.0))
    empty, cleared = bridge.sync_incremental(fuse([layer], GRID, now=0.3))
    assert empty == [] and cleared and bridge.owned() == []

    stale = fuse([LiveLidarLayer(GRID)], GRID, now=9.0)               # no data: keep what is on the board
    layer.add_scan(scan_with_object(0.4, 0.8, half_width_deg=8.0), Pose(0.5, 1.0, 0.0))
    bridge.sync_incremental(fuse([layer], GRID, now=0.4))
    before = {o.id for o in bridge.owned()}
    assert bridge.sync_incremental(stale) == ([], []) and {o.id for o in bridge.owned()} == before

    session.plan_sync()
    session.start_run()
    with pytest.raises(RuntimeError):
        bridge.sync_incremental(fuse([layer], GRID, now=0.5))


def test_new_obstacle_off_the_path_is_remembered_but_does_not_stop(scenario, cfg):
    session = straight_session(scenario, cfg)
    session.start_run()
    session.advance(1)
    before = session.world.state
    layer = LiveLidarLayer(GRID, max_age_s=0.3, min_hits=1)
    bridge = ObstacleBridge(session, prefix="lidar", path_margin=0.10)
    aside = scan_with_object(before.t, 0.8, angle_deg=40.0, half_width_deg=6.0)   # 0.5 m beside the straight path
    layer.add_scan(aside, before.pose)
    assert bridge.inject(fuse([layer], GRID, now=before.t)) == []
    assert session.state == SessionState.RUNNING and len(bridge.seen) >= 1
    assert bridge.inject(fuse([layer], GRID, now=before.t)) == [] and session.state == SessionState.RUNNING
    ahead = scan_with_object(before.t + 0.1, 0.6, half_width_deg=8.0)          # on the path: stops
    layer.add_scan(ahead, session.world.state.pose)
    added = bridge.inject(fuse([layer], GRID, now=ahead.stamp.t))
    assert added and session.state == SessionState.STOPPING
    finish(session)
    assert session.state == SessionState.STOPPED and not session.world.collided
    everywhere = ObstacleBridge(straight_session(scenario, cfg), prefix="lidar", path_margin=None)
    everywhere.session.start_run()
    everywhere.session.advance(1)
    layer2 = LiveLidarLayer(GRID, max_age_s=0.3, min_hits=1)
    layer2.add_scan(aside, everywhere.session.world.state.pose)
    assert everywhere.inject(fuse([layer2], GRID, now=everywhere.session.world.time)) != []   # no corridor: any new obstacle stops
    assert everywhere.session.state == SessionState.STOPPING


def test_invalid_fused_map_stops_the_run_and_sync_replaces_while_editing(scenario, cfg):
    session = straight_session(scenario, cfg)
    session.start_run()
    session.advance(1)
    bridge = ObstacleBridge(session, prefix="lidar")
    assert bridge.inject(fuse([LiveLidarLayer(GRID)], GRID, now=session.world.time)) == []
    assert session.state == SessionState.STOPPING and bridge.stops == 1 and "không hợp lệ" in session.stop_reason
    finish(session)
    assert session.state == SessionState.STOPPED

    editing = Session(type(scenario).from_dict(scenario.to_dict()), cfg)
    layer = LiveLidarLayer(GRID, window=1)                               # window 1: the map is only the last scan
    layer.add_scan(scan_with_object(0.0, 0.5), Pose(0.5, 1.0, 0.0))
    added = bridge_for(editing).sync(fuse([layer], GRID, now=0.0))
    assert added and all(o.id.startswith("lidar_") for o in editing.scenario.obstacles)
    layer.add_scan(scan_with_object(0.1, None), Pose(0.5, 1.0, 0.0))
    assert bridge_for(editing).sync(fuse([layer], GRID, now=0.1)) == [] and editing.scenario.obstacles == []
    with pytest.raises(RuntimeError):
        bridge_for(session).sync(fuse([layer], GRID, now=0.1))


def bridge_for(session):
    return ObstacleBridge(session, prefix="lidar")
