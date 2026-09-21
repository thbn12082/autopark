"""Reeds–Shepp đầy đủ phải phủ mọi cặp tư thế và không bao giờ dài hơn bản rút gọn."""
import math
import random

from pytest import approx

from autopark.domain.types import Pose, wrap_angle
from autopark.planning import reeds_shepp as rs16
from autopark.planning import reeds_shepp_full as rs48

MAXC = 1.0 / 0.329


def random_pair(rng: random.Random) -> tuple[Pose, Pose]:
    return (Pose(rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-math.pi, math.pi)),
            Pose(rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-math.pi, math.pi)))


def test_every_candidate_ends_exactly_at_goal():
    rng = random.Random(11)
    checked = 0
    for _ in range(500):
        q0, q1 = random_pair(rng)
        for path in rs48.candidate_paths(q0, q1, MAXC):
            end = rs48.path_end(q0, path, MAXC)
            assert math.hypot(end.x - q1.x, end.y - q1.y) < 1e-6
            assert abs(wrap_angle(end.yaw - q1.yaw)) < 1e-6
            checked += 1
    assert checked > 2000


def test_covers_every_pair_unlike_the_short_version():
    rng = random.Random(12)
    full_hits = short_hits = 0
    trials = 800
    for _ in range(trials):
        q0, q1 = random_pair(rng)
        if rs48.candidate_paths(q0, q1, MAXC):
            full_hits += 1
        if rs16.candidate_paths(q0, q1, MAXC):
            short_hits += 1
    assert full_hits == trials, f"bản đầy đủ bỏ sót {trials - full_hits} cặp"
    assert short_hits < trials, "bản rút gọn lẽ ra phải bỏ sót một số cặp"


def test_never_longer_than_the_short_version():
    rng = random.Random(13)
    for _ in range(800):
        q0, q1 = random_pair(rng)
        short = rs16.candidate_paths(q0, q1, MAXC)
        full = rs48.candidate_paths(q0, q1, MAXC)
        if short and full:
            assert full[0].length <= short[0].length + 1e-9


def test_finds_words_the_short_version_cannot():
    """Các họ bốn và năm đoạn phải thật sự xuất hiện, không chỉ có trong code."""
    rng = random.Random(14)
    families = set()
    for _ in range(600):
        q0, q1 = random_pair(rng)
        paths = rs48.candidate_paths(q0, q1, MAXC)
        if paths:
            n = len([v for v in paths[0].lengths if abs(v) > 1e-12])
            families.add(n)
    assert 4 in families, "không thấy từ đường bốn đoạn (CCCC/CCSC)"
    assert 5 in families, "không thấy từ đường năm đoạn (CCSCC)"


def test_straight_and_circle_are_exact():
    assert rs48.shortest_length(Pose(0, 0, 0), Pose(1.0, 0, 0), MAXC) == approx(1.0)
    r = 1 / MAXC
    assert rs48.shortest_length(Pose(0, 0, 0), Pose(0.0, 2 * r, math.pi), MAXC) == approx(math.pi * r)
    assert rs48.shortest_length(Pose(0.4, 0.2, 0.7), Pose(0.4, 0.2, 0.7), MAXC) == approx(0.0)


def test_sample_path_reaches_the_goal_with_bounded_steps():
    rng = random.Random(15)
    for _ in range(200):
        q0, q1 = random_pair(rng)
        paths = rs48.candidate_paths(q0, q1, MAXC)
        if not paths:
            continue
        samples = rs48.sample_path(q0, paths[0], MAXC, 0.02)
        last = samples[-1][0]
        assert math.hypot(last.x - q1.x, last.y - q1.y) < 1e-6
        for (a, _, _), (b, _, _) in zip(samples, samples[1:]):
            assert math.hypot(a.x - b.x, a.y - b.y) <= 0.02 + 1e-9


def test_word_string_marks_reverse_segments():
    q0, q1 = Pose(0, 0, 0), Pose(-0.5, 0.0, 0.0)
    best = rs48.candidate_paths(q0, q1, MAXC)[0]
    assert best.word == "s"        # lùi thẳng, chữ thường nghĩa là lùi
    assert best.n_cusps == 0
