"""Fixture geometry and reproducibility, independent of planner success flags."""
import json
import math
import random

import pytest

from autopark.domain.types import Bounds, Pose
from autopark.evaluation.collision_oracle import pose_ok, vehicle_rectangle
from autopark.evaluation.maneuver_cases import build_cases, build_geometric_witnesses
from autopark.evaluation.maneuver_suite_spec import ManeuverCase


def local_bounds(scenario):
    # Reconstruct the configured intersection without using planner geometry.
    b, p, half = scenario.bounds, scenario.start, scenario.maneuver.area_half_extent_m
    return Bounds(max(b.xmin, p.x - half), max(b.ymin, p.y - half),
                  min(b.xmax, p.x + half), min(b.ymax, p.y + half))


@pytest.mark.parametrize("seed", [0, 7, 20261028, -1])
def test_repeat_seed_is_exact_and_snapshots_roundtrip(seed):
    before = random.getstate()
    cases = build_cases(seed)
    snapshots = [c.to_dict() for c in cases]
    assert snapshots == [c.to_dict() for c in build_cases(seed)]
    assert random.getstate() == before
    assert len({c.case_id for c in cases}) == len(cases)
    assert all(c.scenario.seed == seed for c in cases)
    restored = [ManeuverCase.from_dict(s) for s in json.loads(json.dumps(snapshots, allow_nan=False))]
    assert [c.to_dict() for c in restored] == snapshots


def test_seeds_vary_geometry_without_relaxing_limits_or_tolerances():
    nominal, varied = build_cases(0), build_cases(7)
    assert [c.case_id for c in nominal] == [c.case_id for c in varied]
    assert any(a.scenario.obstacles != b.scenario.obstacles for a, b in zip(nominal, varied))
    for a, b in zip(nominal, varied):
        assert a.vehicle == b.vehicle
        assert a.scenario.start == b.scenario.start
        assert a.scenario.goal == b.scenario.goal
        assert a.scenario.maneuver == b.scenario.maneuver
        assert a.criteria == b.criteria
        assert (a.sim_timeout_s, a.plan_time_limit_s) == (b.sim_timeout_s, b.plan_time_limit_s)
        for x, y in zip(a.scenario.obstacles, b.scenario.obstacles):
            # Door wall centers and lengths vary together; the aperture edge
            # still changes at most 2 mm per side.
            assert abs(x.cx - y.cx) <= .002 + 1e-12
            assert abs(x.cy - y.cy) <= .002 + 1e-12
            assert abs(x.width - y.width) <= .002 + 1e-12
            assert abs(x.height - y.height) <= .002 + 1e-12


def test_builds_do_not_share_mutable_scenarios_or_obstacles():
    first, second = build_cases(), build_cases()
    original = second[0].to_dict()
    first[0].scenario.obstacles.clear()
    first[0].scenario.seed = 900
    assert second[0].to_dict() == original
    # Reverse variants of one scene must also own their obstacle list.
    assert second[2].scenario.obstacles
    second[0].scenario.obstacles.clear()
    assert second[2].scenario.obstacles


@pytest.mark.parametrize("seed", [0, 7, 20261028])
def test_complete_objectives_have_collision_free_sampled_witnesses(seed):
    cases = build_cases(seed)
    witnesses = build_geometric_witnesses(seed)
    assert set(witnesses) == {c.case_id for c in cases if c.expected == "complete"}
    for case in cases:
        if case.expected != "complete":
            continue
        s, w = case.scenario, witnesses[case.case_id]
        poses = w.samples()
        assert poses[0] == s.start
        assert poses[-1].distance_to(s.goal.pose) < 1e-12
        assert abs(poses[-1].heading_error_to(s.goal.pose)) < 1e-12
        assert s.start.distance_to(s.goal.pose) <= s.maneuver.max_goal_distance_m
        assert sum(abs(distance) for distance, _ in w.arcs) <= s.maneuver.max_path_length_m
        signs = [math.copysign(1, distance) for distance, _ in w.arcs if distance]
        assert sum(a != b for a, b in zip(signs, signs[1:])) <= s.maneuver.max_cusps
        assert all(abs(steer) <= case.vehicle.max_steer for _, steer in w.arcs)
        assert max(a.distance_to(b) for a, b in zip(poses, poses[1:])) <= .002 + 1e-12
        for index, pose in enumerate(poses):
            assert pose_ok(case.vehicle, pose, s.obstacles, local_bounds(s), margin=.003), (case.case_id, index)


def test_columns_really_block_a_direct_body_sweep():
    cases = {c.case_id: c for c in build_cases()}
    for name in ("columns_left_s", "columns_right_s"):
        case = cases[name]
        s, a, b = case.scenario, case.scenario.start, case.scenario.goal.pose
        direct = [Pose(a.x + (b.x - a.x) * i / 100, a.y + (b.y - a.y) * i / 100, a.yaw)
                  for i in range(101)]
        # Each post independently affects body clearance. This does not imply
        # that linearly interpolated poses are a drivable bicycle trajectory.
        assert all(any(not pose_ok(case.vehicle, pose, [obstacle], s.bounds) for pose in direct)
                   for obstacle in s.obstacles)


def test_right_corner_is_a_geometric_mirror_and_reverse_changes_motion():
    cases = {c.case_id: c for c in build_cases()}
    witnesses = build_geometric_witnesses()
    left, right = cases["turn_left_forward"], cases["turn_right_forward"]
    assert left.scenario.goal.pose.yaw > 0 > right.scenario.goal.pose.yaw
    assert right.scenario.goal.pose.y == pytest.approx(1.5 - left.scenario.goal.pose.y)
    for a, b in zip(left.scenario.obstacles, right.scenario.obstacles):
        assert b.cx == a.cx
        assert b.cy == pytest.approx(1.5 - a.cy)
        assert b.yaw == -a.yaw
    assert all(d > 0 for d, _ in witnesses["turn_left_forward"].arcs)
    assert all(d < 0 for d, _ in witnesses["turn_left_reverse"].arcs)


def test_invalid_cases_have_specific_geometric_or_distance_defects():
    cases = {c.case_id: c for c in build_cases() if c.expected == "refuse"}
    for name, case in cases.items():
        s, cfg, bounds = case.scenario, case.vehicle, local_bounds(case.scenario)
        if name == "refuse_goal_distance":
            assert s.start.distance_to(s.goal.pose) > s.maneuver.max_goal_distance_m
            assert all(pose_ok(cfg, p, s.obstacles, bounds) for p in (s.start, s.goal.pose))
        elif name in ("refuse_start_overlap", "refuse_start_body_outside"):
            assert not pose_ok(cfg, s.start, s.obstacles, bounds)
            assert pose_ok(cfg, s.goal.pose, s.obstacles, bounds)
        else:
            assert pose_ok(cfg, s.start, s.obstacles, bounds)
            assert not pose_ok(cfg, s.goal.pose, s.obstacles, bounds)
        if name.endswith("body_outside"):
            invalid = s.start if "start" in name else s.goal.pose
            assert bounds.contains_point(invalid.x, invalid.y)
            assert any(not bounds.contains_point(z.real, z.imag) for z in vehicle_rectangle(cfg, invalid))
        assert case.fault is None and case.followup_goal is None


def test_followup_is_a_nearby_fixed_world_goal_with_clean_body():
    followups = [c for c in build_cases() if c.followup_goal is not None]
    assert followups
    for case in followups:
        first, second = case.scenario.goal.pose, case.followup_goal
        assert .05 < first.distance_to(second) < case.scenario.maneuver.max_goal_distance_m
        assert pose_ok(case.vehicle, second, case.scenario.obstacles, case.scenario.bounds, margin=.003)
        assert case.expected == "complete"


@pytest.mark.parametrize("seed", [True, .5, "0", None])
def test_seed_must_be_an_integer(seed):
    with pytest.raises(ValueError, match="seed"):
        build_cases(seed)


@pytest.mark.parametrize("step", [0, -1, math.nan, math.inf])
def test_witness_rejects_invalid_sampling_step(step):
    witness = next(iter(build_geometric_witnesses().values()))
    with pytest.raises(ValueError, match="step_m"):
        witness.samples(step)
