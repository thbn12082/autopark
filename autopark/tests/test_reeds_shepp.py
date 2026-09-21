import math
import random

from pytest import approx

from autopark.domain.types import Pose, wrap_angle
from autopark.planning.reeds_shepp import candidate_paths, path_end, sample_path, shortest_length

MAXC = 1.0 / 0.33  # R_min = 0,33 m


def test_straight_ahead_is_a_straight_segment():
    paths = candidate_paths(Pose(0, 0, 0), Pose(1.0, 0, 0), MAXC)
    assert paths
    best = paths[0]
    assert best.length / MAXC == approx(1.0)
    assert best.n_cusps == 0


def test_half_circle_left():
    r = 1 / MAXC
    goal = Pose(0.0, 2 * r, math.pi)
    paths = candidate_paths(Pose(0, 0, 0), goal, MAXC)
    assert paths
    assert paths[0].length / MAXC == approx(math.pi * r)


def test_lsr_known_case():
    # L pi/2, S 2, R pi/2 (chuẩn hóa) đi từ gốc tới (2, 4, 0)
    paths = candidate_paths(Pose(0, 0, 0), Pose(2.0, 4.0, 0.0), 1.0)
    lsr = [p.lengths for p in paths if p.ctypes == ("L", "S", "R")]
    assert lsr
    assert any(lengths == approx((math.pi / 2, 2.0, math.pi / 2)) for lengths in lsr)
    assert paths[0].ctypes == ("L", "S", "R")
    assert paths[0].length == approx(math.pi + 2.0)


def test_random_goals_end_exactly_at_goal():
    rng = random.Random(1)
    found = 0
    for _ in range(300):
        q0 = Pose(rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-math.pi, math.pi))
        q1 = Pose(rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-math.pi, math.pi))
        paths = candidate_paths(q0, q1, MAXC)
        if not paths:
            continue
        found += 1
        for path in paths[:4]:
            end = path_end(q0, path, MAXC)
            assert math.hypot(end.x - q1.x, end.y - q1.y) < 1e-6
            assert abs(wrap_angle(end.yaw - q1.yaw)) < 1e-6
            samples = sample_path(q0, path, MAXC, 0.02)
            last = samples[-1][0]
            assert math.hypot(last.x - q1.x, last.y - q1.y) < 1e-6
            # bước mẫu không vượt quá step
            for (a, _, _), (b, _, _) in zip(samples, samples[1:]):
                assert math.hypot(a.x - b.x, a.y - b.y) <= 0.02 + 1e-9
    assert found > 250


def test_sample_directions_follow_sign_of_lengths():
    paths = candidate_paths(Pose(0, 0, 0), Pose(-0.5, 0.0, 0.0), MAXC)
    assert paths
    best = paths[0]
    samples = sample_path(Pose(0, 0, 0), best, MAXC, 0.05)
    assert best.length / MAXC == approx(0.5)
    assert all(d == -1 for _, d, _ in samples)


def test_shortest_length_matches_euclid_when_straight():
    assert shortest_length(Pose(0, 0, 0.7), Pose(2 * math.cos(0.7), 2 * math.sin(0.7), 0.7), MAXC) == approx(2.0)
