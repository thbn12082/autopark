"""Nhiều camera + LiDAR + AI chạy đồng thời, bằng nguồn giả: ghép bộ ảnh, bỏ bộ lệch, đếm lỗi, số đo, lệnh đo."""
import json
import math
import random
import re
import time

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from autopark.rig import bench  # noqa: E402
from autopark.rig.core import AIWorker, Rig, RigConfig  # noqa: E402
from autopark.video.multicam import RIG_CLOCK, CameraSpec, MultiCameraManager, build_set, clock_info, fit_width  # noqa: E402
from autopark.video.sources import _frame  # noqa: E402
from tests.rig_fakes import FakeLidar, FakeSegmenter, fake_manager  # noqa: E402


def ring_of(port, stamps):
    img = np.zeros((4, 4, 3), np.uint8)
    return [(k, _frame(f"cam_p{port}", t, "x", img)) for k, t in enumerate(stamps)]


def manual_manager(ports, now, ring=3):
    """Không start: vòng đệm nạp tay, đồng hồ giả `now[0]`."""
    specs = [CameraSpec(port=p, index=k) for k, p in enumerate(ports)]
    return MultiCameraManager(specs, ring=ring, open_source=lambda s: None, clock=lambda: now[0])


def push(cams, port, t, value=0):
    """Như CameraWorker.run nhận một khung tốt ở stamp t."""
    w = cams.workers[port]
    w.seq += 1
    w.ring.append((w.seq, _frame(f"cam_p{port}", t, "x", np.full((24, 32, 3), value, np.uint8))))
    w.stats.frames += 1
    w.stats.last_stamp = t
    w.stats.recent.append(t)
    w.arrivals.append(t)


def push_damaged(cams, port, t):
    """Như CameraWorker.run nhận một khung cắt cụt ở t: nguồn loại nó (không vào vòng đệm), nhưng camera đã gửi khung."""
    w = cams.workers[port]
    with w.lock:
        w._count_error(f"cam_p{port}: truncated frame (12 of 24 rows filled by the decoder)", t)


def stamps_of(fs):
    return {p: f.meta.stamp.t for p, f in fs.frames.items()}


def schedule(periods, phases, t_end, t0=1.0, starts=None, drop=None, jitter=0.0, loss=None, seed=0):
    """Lịch khung tốt (t, cổng) đã sắp: cổng p tới ở t0 + phases[p] + k·periods[p] (± jitter), bắt đầu từ t0 + starts[p]
    (mở lần lượt), bỏ các chỉ số k trong drop[p] hoặc ngẫu nhiên với xác suất loss[p] (khung hỏng bị nguồn loại)."""
    rnd = random.Random(seed)
    events = []
    for p, period in periods.items():
        k = 0
        while (t := t0 + phases[p] + k * period) <= t_end:
            t += rnd.uniform(-jitter, jitter) if jitter else 0.0
            lost = k in (drop or {}).get(p, ()) or rnd.random() < (loss or {}).get(p, 0.0)
            if t >= t0 + (starts or {}).get(p, 0.0) and not lost:
                events.append((t, p))
            k += 1
    return sorted(events)


# Nhịp khung thật ở phơi sáng tự động (m01/m04, GIAI_DOAN_1_CAMERA.md mục 4.1): khoảng cách xen kẽ ≈ 31,4 / 48,3 ms, sau
# khoảng ngắn luôn là khoảng dài, sau khoảng dài là khoảng ngắn với xác suất 272/443; trung bình 41,9 ms.
SHORT_GAP, LONG_GAP = 0.0314, 0.0483


def alternating_gaps(n, seed):
    rnd, out, prev = random.Random(seed), [], LONG_GAP
    for _ in range(n):
        prev = LONG_GAP if prev == SHORT_GAP or rnd.random() >= 272 / 443 else SHORT_GAP
        out.append(prev)
    return out


def alternating_events(ports, phases, t_end, *, jitter=0.0, loss=None, burst_s=None, damaged=False, seed=0, t0=1.0):
    """Lịch khung (t, cổng[, "damaged"]) theo nhịp xen kẽ ở trên. Stamp lấy sau read() nên rung chỉ làm trễ thêm (0 …
    jitter). `loss[p]`: xác suất một khung của cổng p hỏng — trong đợt dài `burst_s` giây xen kẽ đợt sạch, nếu có
    `burst_s`. Khung hỏng bị bỏ hẳn khỏi lịch, hoặc với `damaged=True` được giữ dưới dạng khung cắt cụt (`push_damaged`:
    nguồn loại, nhưng camera đã gửi)."""
    rnd, events = random.Random(seed), []
    for p in ports:
        t = t0 + phases[p]
        for g in alternating_gaps(int((t_end - t0) / 0.03) + 10, seed * 31 + p):
            t += g
            if t > t_end:
                break
            stamp = t + (rnd.uniform(0, jitter) if jitter else 0.0)
            in_burst = burst_s is None or (t - t0) % (2 * burst_s) < burst_s
            if in_burst and rnd.random() < (loss or {}).get(p, 0.0):
                if damaged:
                    events.append((stamp, p, "damaged"))
                continue
            events.append((stamp, p))
    return sorted(events)


def run_schedule(cams, now, events, t_end, t_reset, max_wait_s=0.06, max_skew_s=0.1, poll=0.002):
    """Nạp khung theo lịch, gọi latest_set mỗi `poll` giây đồng hồ giả (như luồng AI khi chưa có bộ mới); đặt lại số
    đếm ở t_reset và trả các bộ phát sau đó. Sự kiện (t, cổng, "damaged") là khung cắt cụt (`push_damaged`)."""
    sets, i, t, reset = [], 0, events[0][0], False
    while t < t_end:
        while i < len(events) and events[i][0] <= t:
            (push_damaged if len(events[i]) > 2 else push)(cams, events[i][1], events[i][0])
            i += 1
        if not reset and t >= t_reset:
            cams.reset_stats()
            reset = True
        now[0] = t
        fs = cams.latest_set(max_skew_s, max_wait_s=max_wait_s)
        if fs is not None and reset:
            sets.append(fs)
        t += poll
    return sets


def test_frame_interval_is_the_grid_period_despite_an_outage_frame_loss_and_jitter():
    now = [0.0]
    cams = manual_manager((1,), now)
    w = cams.workers[1]
    for t in (1.00, 1.04):
        push(cams, 1, t)
    assert w.frame_interval_s() is None                      # chưa đủ 3 khung
    for t in (1.08, 1.12, 1.73, 1.77, 1.81):                  # một đợt im 610 ms (15,25 chu kỳ) giữa chừng: không tính
        push(cams, 1, t)
    assert w.frame_interval_s() == pytest.approx(0.04)
    assert cams.frame_periods([1]) == {1: pytest.approx(0.04)}
    period = 1 / 24
    lossy = manual_manager((2,), now)                  # mất ≈ nửa số khung: khoảng cách 1–2 chu kỳ, trung vị trần = 2 chu kỳ
    for k in (0, 1, 3, 5, 6, 8, 10, 12, 13, 15, 17):
        push(lossy, 2, 1.0 + k * period)
    assert lossy.workers[2].frame_interval_s() == pytest.approx(period)
    damaged = manual_manager((4,), now)                # 2/3 số khung bị cắt: nguồn loại, nhưng lần tới vẫn được ghi
    for k in range(30):
        (push if k % 3 == 0 else push_damaged)(damaged, 4, 1.0 + k * period)
    w4 = damaged.workers[4]
    assert len(w4.stats.recent) == 10 and w4.stats.truncated == 20 and len(w4.ring) == 3
    assert w4.frame_interval_s() == pytest.approx(period)
    shaky = manual_manager((3,), now)                  # stamp rung ±4 ms: phân vị 25 % trần của khoảng cách lệch thấp
    rnd = random.Random(1)
    stamps = [1.0 + k * period + rnd.uniform(-0.004, 0.004) for k in range(26)]
    for t in stamps:
        push(shaky, 3, t)
    gaps = sorted(b - a for a, b in zip(stamps, stamps[1:]))
    assert gaps[(len(gaps) - 1) // 4] < period - 0.002                  # cách ước lượng bị bỏ: thấp hơn thật > 2 ms
    assert shaky.workers[3].frame_interval_s() == pytest.approx(period, abs=0.0015)
    assert cams.wait_limit_s(0.06, {1: 0.04, 2: 0.125, 3: None}) == pytest.approx(0.06)     # nhanh nhất, không trung vị
    assert cams.wait_limit_s(0.06, {1: 1 / 15, 2: 1 / 15}) == pytest.approx(0.1)
    assert cams.wait_limit_s(0.06, {1: None}) == 0.06


def test_rig_clock_is_high_resolution():
    # time.monotonic trên Python 3.12/Windows có bước 15,6 ms: không dùng được để đo độ lệch vài chục ms
    assert RIG_CLOCK is time.perf_counter and clock_info()["resolution_s"] <= 1e-3


def test_build_set_anchors_on_the_slowest_camera_and_picks_closest_frames():
    rings = {1: ring_of(1, [0.90, 0.94, 0.98]),       # nhanh
             2: ring_of(2, [0.88, 0.92, 0.95]),       # chậm nhất: mốc = 0,95
             3: ring_of(3, [0.93, 0.96, 1.01])}
    fs = build_set(rings, now=1.02)
    assert fs.anchor_t == pytest.approx(0.95)
    assert {p: f.meta.stamp.t for p, f in fs.frames.items()} == pytest.approx({1: 0.94, 2: 0.95, 3: 0.96})
    assert fs.skew_s == pytest.approx(0.02) and fs.missing == []


def test_build_set_drops_stale_and_empty_cameras():
    rings = {1: ring_of(1, [0.9, 1.0]), 2: ring_of(2, [0.1]), 3: []}
    fs = build_set(rings, now=1.05, stale_after_s=0.5)
    assert sorted(fs.frames) == [1] and fs.missing == [2, 3]
    assert build_set({1: []}, now=1.0) is None


def test_fit_width_keeps_aspect():
    assert fit_width(1280, 720, 640) == (640, 360) and fit_width(640, 480, 640) == (640, 480)
    assert fit_width(640, 480, 320) == (320, 240) and fit_width(100, 50, 640) == (100, 50)


def test_manager_streams_sets_counts_duplicates_and_reports_broken_camera():
    cams = fake_manager(ports=(1, 2, 3, 4), period=0.02, broken=(3,), dup_every=5)
    cams.start()
    try:
        time.sleep(0.6)
        fs = cams.latest_set(max_skew_s=0.1)
        assert fs is not None and sorted(fs.frames) == [1, 2, 4] and fs.missing == [3]
        stats = cams.stats()
    finally:
        alive = cams.stop()
    by_port = {c["port"]: c for c in stats["cameras"]}
    assert by_port[3]["open_error"] and by_port[3]["stale"]
    assert by_port[1]["frames"] > 5 and by_port[1]["duplicates"] > 0 and by_port[1]["fps_last2s"] > 10
    assert stats["sets_partial"] >= 1 and alive == []
    assert all(w.source is None or w.source.closed for w in cams.workers.values())


def test_manager_rejects_sets_whose_skew_is_too_large_and_only_returns_new_sets():
    now = [1.0]
    specs = [CameraSpec(port=1, index=0), CameraSpec(port=2, index=1)]
    cams = MultiCameraManager(specs, ring=1, open_source=lambda s: None, clock=lambda: now[0])   # không start: nạp tay
    w1, w2 = cams.workers[1], cams.workers[2]
    img = np.zeros((4, 4, 3), np.uint8)
    w1.ring.append((1, _frame("cam_p1", 0.99, "x", img)))
    w2.ring.append((1, _frame("cam_p2", 0.90, "x", img)))            # lệch 90 ms
    assert cams.latest_set(max_skew_s=0.05) is None and cams.sets_rejected_skew == 1
    assert cams.latest_set(max_skew_s=0.05) is None and cams.sets_rejected_skew == 1   # cùng bộ: không đếm lại
    assert cams.sets_blocked_not_new == 0                             # bộ y hệt bộ trước không phải "bị chặn"
    w2.ring.append((2, _frame("cam_p2", 0.98, "x", img)))            # chỉ camera 2 có khung mới
    assert cams.latest_set(max_skew_s=0.05) is None                   # camera 1 vẫn khung cũ: chưa phải bộ mới
    assert cams.latest_set(max_skew_s=0.05) is None and cams.sets_blocked_not_new == 1   # cùng bộ bị chặn: đếm một lần
    w1.ring.append((2, _frame("cam_p1", 0.99, "x", img)))             # cả hai đều mới, lệch 10 ms
    fs = cams.latest_set(max_skew_s=0.05)
    assert fs is not None and fs.skew_s == pytest.approx(0.01) and cams.sets_built == 1
    assert cams.latest_set(max_skew_s=0.05) is None
    assert cams.latest_set(max_skew_s=0.05, require_new=False) is not None
    w1.ring.append((5, _frame("cam_p1", 1.00, "x", img)))             # camera 1 nhảy seq 2 → 5: 2 khung không vào bộ nào
    w2.ring.append((3, _frame("cam_p2", 1.00, "x", img)))
    assert cams.latest_set(max_skew_s=0.05) is not None and cams.frames_skipped[1] == 2
    st = cams.stats(window=None)
    assert st["skew_ms"]["n"] == 4 and st["skew_ms"]["max"] == pytest.approx(90.0)
    cams.reset_stats()
    assert cams.stats()["sets_built"] == 0 and cams.frames_skipped == {1: 0, 2: 0}


# ---- chờ camera chậm có giới hạn (max_wait_s) ---------------------------------------------------------------------

def test_silent_camera_is_left_out_only_after_the_wait_and_rejoins_with_a_new_frame():
    now = [1.00]
    cams = manual_manager((1, 2), now)
    push(cams, 1, 1.00)
    push(cams, 2, 1.00)
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert sorted(fs.frames) == [1, 2] and fs.lagging == [] and fs.waited_s is None
    push(cams, 1, 1.04)                                  # camera 1 có khung mới, camera 2 chưa
    now[0] = 1.055                                       # khung mới chờ 15 ms, camera 2 im 55 ms: còn trong hạn
    assert cams.latest_set(0.1, max_wait_s=0.06) is None
    now[0] = 1.059
    assert cams.latest_set(0.1, max_wait_s=0.06) is None
    assert cams.sets_blocked_not_new == 1 and cams.sets_partial_wait == 0      # cùng trạng thái chờ: đếm một lần
    now[0] = 1.061                                       # camera 2 im 61 ms > 60: không chờ nữa
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert stamps_of(fs) == {1: 1.04} and fs.lagging == [2] and fs.missing == []
    assert fs.anchor_t == pytest.approx(1.04) and fs.skew_s == 0 and fs.waited_s == pytest.approx(0.021)
    assert cams.sets_partial_wait == 1 and cams.lagging_per_port == {1: 0, 2: 1} and cams.sets_partial == 0
    assert cams.latest_set(0.1, max_wait_s=0.06) is None                      # không phát lại cùng bộ
    push(cams, 1, 1.08)
    now[0] = 1.081                                       # camera 2 vẫn im (81 ms): phát ngay, khung mới chỉ chờ 1 ms
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert stamps_of(fs) == {1: 1.08} and fs.lagging == [2] and fs.waited_s == pytest.approx(0.001)
    push(cams, 2, 1.09)                                  # camera 2 quay lại; camera 1 đã dùng hết khung, mới im 15 ms
    now[0] = 1.095
    assert cams.latest_set(0.1, max_wait_s=0.06) is None and cams.sets_blocked_not_new == 2
    push(cams, 1, 1.12)
    now[0] = 1.121
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    # camera 1 chọn khung MỚI 1,12, không phải 1,08 (gần mốc 1,09 hơn nhưng đã vào bộ trước) → bộ đủ, không bị chặn
    assert stamps_of(fs) == pytest.approx({1: 1.12, 2: 1.09}) and fs.lagging == [] and fs.waited_s is None
    assert fs.skew_s == pytest.approx(0.03)
    assert cams.sets_built == 4 and cams.sets_partial_wait == 2 and cams.lagging_per_port == {1: 0, 2: 2}
    assert cams.frames_skipped == {1: 0, 2: 0} and cams.sets_rejected_skew == 0
    st = cams.stats(window=None)
    assert st["sets_partial_wait"] == 2 and st["lagging_per_port"] == {1: 0, 2: 2}
    assert st["partial_wait_ms"]["n"] == 2 and st["partial_wait_ms"]["max"] == pytest.approx(21.0)
    cams.reset_stats()
    st = cams.stats()
    assert st["sets_partial_wait"] == 0 and st["lagging_per_port"] == {1: 0, 2: 0} and st["partial_wait_ms"]["n"] == 0


def early_anchor_three_cams(now):
    """Camera 3 vừa dùng khung 1,05 trong bộ trước, nhưng khung 1,035 của camera 2 chưa vào bộ nào (mốc bộ trước là 1,00)."""
    cams = manual_manager((1, 2, 3), now)
    now[0] = 1.05
    push(cams, 1, 1.00)
    push(cams, 2, 1.00)
    push(cams, 2, 1.035)
    push(cams, 3, 1.05)
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert stamps_of(fs) == pytest.approx({1: 1.00, 2: 1.00, 3: 1.05})
    push(cams, 1, 1.06)
    return cams


@pytest.mark.parametrize("max_skew_s", [0.1, 0.02])
def test_pending_frame_never_waits_longer_than_max_wait_even_if_the_slow_camera_is_recent(max_skew_s):
    now = [0.0]
    cams = early_anchor_three_cams(now)
    now[0] = 1.094                              # khung 1,035 đã chờ 59 ms; camera 3 mới im 44 ms
    assert cams.latest_set(max_skew_s, max_wait_s=0.06) is None
    now[0] = 1.0965                             # khung 1,035 chờ 61,5 ms > 60; camera 3 im 46,5 ms (chưa quá hạn)
    fs = cams.latest_set(max_skew_s, max_wait_s=0.06)
    if max_skew_s == 0.1:
        assert stamps_of(fs) == pytest.approx({1: 1.06, 2: 1.035}) and fs.lagging == [3]
        assert fs.anchor_t == pytest.approx(1.035) and fs.skew_s == pytest.approx(0.025)   # chỉ trên camera có trong bộ
        assert fs.waited_s == pytest.approx(0.0615) and cams.sets_partial_wait == 1
    else:                                       # bộ thiếu vẫn qua luật lệch: 25 ms > 20 ms → bỏ, đếm, không phát lại
        assert fs is None and cams.sets_rejected_skew == 1
        assert cams.sets_partial_wait == 0 and cams.lagging_per_port == {1: 0, 2: 0, 3: 0} and cams.sets_built == 1
        assert cams.latest_set(max_skew_s, max_wait_s=0.06) is None and cams.sets_rejected_skew == 1


@pytest.mark.parametrize("off", [None, 0, -1.0])
def test_disabled_wait_reproduces_the_old_all_cameras_rule(off):
    now = [1.00]
    cams = manual_manager((1, 2), now)
    push(cams, 1, 1.00)
    push(cams, 2, 1.00)
    assert cams.latest_set(0.1, max_wait_s=off) is not None
    push(cams, 1, 1.04)
    for t in (1.055, 1.061):
        now[0] = t
        assert cams.latest_set(0.1, max_wait_s=off) is None
    push(cams, 1, 1.08)
    now[0] = 1.081                                   # camera 2 im 81 ms: quy tắc cũ vẫn chờ
    assert cams.latest_set(0.1, max_wait_s=off) is None
    push(cams, 2, 1.09)
    now[0] = 1.095                                   # mốc 1,08: camera 1 dùng 1,08, khung 1,04 không vào bộ nào
    fs = cams.latest_set(0.1, max_wait_s=off)
    assert stamps_of(fs) == pytest.approx({1: 1.08, 2: 1.09}) and fs.lagging == []
    push(cams, 1, 1.12)
    now[0] = 1.121                                   # quy tắc cũ chọn lại 1,08 (gần mốc 1,09) → trùng bộ trước → không phát
    assert cams.latest_set(0.1, max_wait_s=off) is None
    assert cams.sets_built == 2 and cams.sets_partial_wait == 0 and cams.lagging_per_port == {1: 0, 2: 0}
    assert cams.frames_skipped == {1: 1, 2: 0} and cams.sets_blocked_not_new == 0


def test_lagging_camera_is_distinct_from_missing_camera():
    now = [1.00]
    cams = manual_manager((1, 2, 3, 4), now)       # cổng 4 không bao giờ có khung
    push(cams, 3, 0.45)                             # cổng 3 im 550 ms > stale_after_s 0,5: "missing"
    push(cams, 1, 1.00)
    push(cams, 2, 1.00)
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert sorted(fs.frames) == [1, 2] and fs.missing == [3, 4] and fs.lagging == []
    push(cams, 1, 1.04)
    now[0] = 1.07                                   # cổng 2 còn khung tươi (70 ms) nhưng không có khung mới: "lagging"
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert sorted(fs.frames) == [1] and fs.missing == [3, 4] and fs.lagging == [2]
    assert cams.sets_partial == 2 and cams.sets_partial_wait == 1
    push(cams, 1, 1.50)
    now[0] = 1.51                                   # cổng 2 im 510 ms: hết là "chậm", thành "missing"
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert sorted(fs.frames) == [1] and fs.missing == [2, 3, 4] and fs.lagging == []
    assert cams.sets_partial_wait == 1 and cams.lagging_per_port == {1: 0, 2: 1, 3: 0, 4: 0}
    push(cams, 1, 1.55)
    push(cams, 2, 1.55)                             # cổng 2 có khung trở lại: vào bộ ngay
    now[0] = 1.56
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert sorted(fs.frames) == [1, 2] and fs.missing == [3, 4] and fs.lagging == []


def test_left_out_only_when_no_waiting_camera_is_still_worth_waiting_for():
    now = [1.00]
    cams = manual_manager((1, 2, 3), now)
    for p in (1, 2, 3):
        push(cams, p, 1.00)
    assert sorted(cams.latest_set(0.1, max_wait_s=0.06).frames) == [1, 2, 3]
    push(cams, 1, 1.04)
    push(cams, 2, 1.04)
    now[0] = 1.061                                       # camera 3 im 61 ms (chưa rõ nhịp: quy tắc "im quá L"): bỏ 3
    assert cams.latest_set(0.1, max_wait_s=0.06).lagging == [3]
    push(cams, 1, 1.08)
    now[0] = 1.085       # cổng 2 im 45 ms (còn đáng chờ), cổng 3 im 85 ms (hết): (b) đòi KHÔNG camera nào còn đáng chờ
    assert cams.latest_set(0.1, max_wait_s=0.06) is None
    push(cams, 2, 1.09)
    now[0] = 1.095
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert stamps_of(fs) == pytest.approx({1: 1.08, 2: 1.09}) and fs.lagging == [3]
    push(cams, 1, 1.12)
    # cổng 2 đã rõ nhịp (3 khung, chu kỳ 45 ms): khung đúng lượt dự đoán 1,135; chưa trễ quá nửa chu kỳ (1,1575) → chờ
    now[0] = 1.155
    assert cams.latest_set(0.1, max_wait_s=0.06) is None
    now[0] = 1.16                                        # khung 1,135 đã trễ quá 22,5 ms: cổng 2 lỡ khung, bỏ cả 2 và 3
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert stamps_of(fs) == pytest.approx({1: 1.12}) and fs.lagging == [2, 3] and fs.waited_s == pytest.approx(0.04)
    assert cams.lagging_per_port == {1: 0, 2: 1, 3: 3} and cams.sets_partial_wait == 3


def test_camera_back_from_missing_does_not_count_frames_from_before_the_outage_as_waiting():
    now = [1.001]
    cams = manual_manager((1, 2), now)                 # vòng đệm 3 khung: cổng 2 còn giữ khung trước đợt im
    push(cams, 1, 1.00)
    push(cams, 2, 0.96)
    push(cams, 2, 1.00)
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert sorted(fs.frames) == [1, 2]
    push(cams, 1, 1.60)
    now[0] = 1.601                                     # cổng 2 im 601 ms > stale_after_s: "missing", seq bị xóa
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert stamps_of(fs) == {1: 1.60} and fs.missing == [2] and fs.lagging == []
    push(cams, 2, 1.63)                                # cổng 2 quay lại; khung cuối cổng 1 mới 31 ms (trong hạn chờ)
    now[0] = 1.631                                     # khung mới của cổng 2 chỉ chờ 1 ms: phải chờ tiếp, không bỏ cổng 1
    assert cams.latest_set(0.1, max_wait_s=0.06) is None
    assert cams.sets_partial_wait == 0 and cams.lagging_per_port == {1: 0, 2: 0}
    push(cams, 1, 1.642)
    now[0] = 1.643
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert stamps_of(fs) == pytest.approx({1: 1.642, 2: 1.63}) and fs.lagging == [] and fs.waited_s is None
    assert cams.stats(window=None)["partial_wait_ms"]["n"] == 0


def test_camera_silent_since_before_the_first_set_rejoins_without_a_bogus_wait():
    now = [1.001]
    cams = manual_manager((1, 2), now)
    push(cams, 2, 0.40)
    push(cams, 2, 0.44)                                # cổng 2 im từ trước bộ đầu: không bao giờ có seq đã dùng
    push(cams, 1, 1.00)
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert stamps_of(fs) == {1: 1.00} and fs.missing == [2]
    push(cams, 2, 1.02)
    now[0] = 1.021
    assert cams.latest_set(0.1, max_wait_s=0.06) is None
    push(cams, 1, 1.04)
    now[0] = 1.041
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert stamps_of(fs) == pytest.approx({1: 1.04, 2: 1.02}) and fs.lagging == [] and fs.waited_s is None


def test_camera_returning_from_missing_does_not_mark_healthy_camera_lagging():
    now = [1.00]
    cams = manual_manager((1, 2), now)
    for t in (0.96, 1.00):
        push(cams, 1, t)
        push(cams, 2, t)
    assert sorted(cams.latest_set(0.1, max_wait_s=0.06).frames) == [1, 2]
    for t in (1.04, 1.08, 1.12, 1.16, 1.20, 1.24, 1.28, 1.32, 1.36, 1.40, 1.44, 1.48, 1.52, 1.56, 1.60):
        push(cams, 1, t)
        now[0] = t + 0.001
        cams.latest_set(0.1, max_wait_s=0.06)        # cổng 2 thành "chậm", rồi "missing" sau 0,5 s
    push(cams, 2, 1.62)                              # cổng 2 quay lại; cổng 1 khỏe (khung 1,60, mới 21 ms)
    now[0] = 1.621
    assert cams.latest_set(0.1, max_wait_s=0.06) is None     # giữ lại, không phải {2} với lagging=[1], waited_s 0,661
    push(cams, 1, 1.64)
    now[0] = 1.641
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    assert sorted(fs.frames) == [1, 2] and fs.lagging == [] and fs.waited_s is None
    assert cams.lagging_per_port[1] == 0 and max(cams.waits) <= 0.06 + 0.005


PORTS4 = (1, 2, 3, 4)


@pytest.mark.parametrize("period, phases_ms, max_skew_s", [
    (1 / 15, (0, 10, 20, 30), 0.1),      # bản đầu: mọi bộ thiếu đúng một camera, luân phiên (người kiểm tra tái hiện)
    (1 / 15, (0, 5, 10, 15), 0.06),
    (1 / 10, (0, 25, 50, 75), 0.1),      # dưới 12,5 fps: (a) với 60 ms cố định cũng tách bộ
])
def test_healthy_cameras_slower_than_the_wait_floor_still_form_full_sets(period, phases_ms, max_skew_s):
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    events = schedule({p: period for p in PORTS4}, {p: ph / 1000 for p, ph in zip(PORTS4, phases_ms)}, t_end=6.0)
    sets = run_schedule(cams, now, events, t_end=6.0, t_reset=2.0, max_skew_s=max_skew_s)
    assert all(len(fs.frames) == 4 for fs in sets), [sorted(fs.frames) for fs in sets[:6]]
    assert len(sets) >= 0.95 * 4.0 / period
    assert cams.sets_partial_wait == 0 and set(cams.lagging_per_port.values()) == {0} and cams.sets_rejected_skew == 0
    assert np.median([fs.skew_s for fs in sets]) == pytest.approx(phases_ms[-1] / 1000, abs=0.002)   # đúng nhóm pha
    assert cams.stats(window=None)["wait_limit_ms"]["median"] == pytest.approx(1500 * period, rel=0.02)


@pytest.mark.parametrize("fps, fast_spread_ms", [({1: 24, 2: 24, 3: 24, 4: 12}, 20), ({1: 24, 2: 8}, 0)])
def test_only_the_slower_camera_is_left_out_and_the_limit_follows_the_fastest(fps, fast_spread_ms):
    now = [0.0]
    ports = tuple(fps)
    slow = min(fps, key=fps.get)
    cams = manual_manager(ports, now)
    phases = {p: (0.005 if p == slow else 0.01 * k) for k, p in enumerate(ports)}
    events = schedule({p: 1 / f for p, f in fps.items()}, phases, t_end=6.0)
    sets = run_schedule(cams, now, events, t_end=6.0, t_reset=2.0)
    assert len(sets) >= 0.95 * 24 * 4.0                                     # tốc độ camera nhanh, không phải camera chậm
    assert cams.lagging_per_port[slow] > 0.4 * len(sets)
    assert all(v == 0 for p, v in cams.lagging_per_port.items() if p != slow)
    assert all(slow in fs.frames or slow in fs.lagging for fs in sets) and cams.sets_regrouped == 0
    st = cams.stats(window=None)
    assert st["wait_limit_ms"]["median"] == pytest.approx(62.5, abs=1.0)   # 1,5 × 41,7 ms: camera chậm không kéo lên
    # nhóm không có khung của camera chậm được phát ngay khi đủ camera nhanh, không chờ camera chậm im hết L
    assert st["partial_wait_ms"]["max"] <= fast_spread_ms + 3.0


def test_camera_that_missed_one_frame_is_still_awaited_when_its_next_frame_is_due():
    now = [0.0]
    cams = manual_manager((1, 2), now)
    events = schedule({1: 1 / 24, 2: 1 / 24}, {1: 0.0, 2: 0.006}, t_end=3.0, drop={2: {30}})   # cổng 2 mất khung 2,256
    sets = run_schedule(cams, now, events, t_end=3.0, t_reset=1.5)
    partial = [k for k, fs in enumerate(sets) if fs.lagging]
    assert len(partial) == 1 and sets[partial[0]].lagging == [2]            # đúng MỘT bộ thiếu cho một khung mất
    after = sets[partial[0] + 1]
    # bộ kế: khung 2,2917 của cổng 2 tới 6 ms sau khung cổng 1 — được chờ dù cổng 2 đã im 77 ms > L (bản đầu bỏ nó)
    assert sorted(after.frames) == [1, 2] and after.skew_s == pytest.approx(0.006, abs=1e-6)
    assert all(fs.skew_s == pytest.approx(0.006, abs=1e-6) for fs in sets if len(fs.frames) == 2)
    assert cams.frames_skipped == {1: 0, 2: 0} and cams.sets_regrouped == 0


def test_camera_joining_at_an_unlucky_phase_is_regrouped_instead_of_locking_one_cycle_off():
    now = [0.0]
    cams = manual_manager((1, 2), now)
    period = 1 / 24
    events = schedule({1: period, 2: period}, {1: 0.0, 2: 0.002}, t_end=1.40, starts={2: 0.08})   # cổng 2 mở sau
    out = []
    for t, p in events:
        push(cams, p, t)
        now[0] = t + 0.001
        fs = cams.latest_set(0.1, max_wait_s=0.06)
        if fs is not None:
            out.append((round(1000 * (t + 0.001)), {q: round(1000 * s) for q, s in stamps_of(fs).items()}, fs.deferred))
    # cổng 2 vào 2 ms sau khung cổng 1 đã dùng: bốn bộ đầu ghép lệch một chu kỳ ((c) cần REGROUP_SETS = 5 bộ đủ cùng
    # thành phần; hai bộ đầu cổng 2 cũng chưa rõ nhịp)
    assert out[3:7] == [(1126, {1: 1125, 2: 1085}, []), (1168, {1: 1167, 2: 1127}, []), (1209, {1: 1208, 2: 1169}, []),
                        (1251, {1: 1250, 2: 1210}, [])]
    # bộ thứ năm: khung 1,2917 của cổng 1 được để dành, bộ phát chỉ có cổng 2; từ đó mọi bộ lệch 2 ms
    assert out[7] == (1293, {2: 1252}, [1])
    assert all(q[2] == [] and set(q[1]) == {1, 2} and abs(q[1][2] - q[1][1] - 2) <= 1 for q in out[8:]), out[8:]
    assert cams.sets_regrouped == 1 and cams.lagging_per_port == {1: 0, 2: 0} and cams.frames_skipped == {1: 0, 2: 0}


def test_regrouped_set_keeps_the_frame_it_chose_for_the_older_cluster():
    now = [0.0]
    cams = manual_manager((1, 2), now)
    period = 1 / 24
    for k in range(3):                                   # cùng pha, đủ 3 khung: cả hai đã rõ nhịp
        t = 1.0 + k * period
        push(cams, 1, t)
        push(cams, 2, t)
        now[0] = t + 0.001
        assert sorted(cams.latest_set(0.1, max_wait_s=0.06).frames) == [1, 2]
    for k in range(3, 5):              # cổng 2 lệch 0,7 chu kỳ sau cổng 1: hai bộ lệch pha, trung vị qua 5 bộ chưa đổi
        t = 1.0 + k * period
        push(cams, 1, t)
        push(cams, 2, t + 0.7 * period)
        now[0] = t + 0.7 * period + 0.001
        fs = cams.latest_set(0.1, max_wait_s=0.06)
        assert sorted(fs.frames) == [1, 2] and fs.deferred == []
    a1 = 1.0 + 5 * period
    push(cams, 1, a1)                                    # cổng 1: khung a1, mất khung kế, rồi a1 + 2 chu kỳ
    push(cams, 2, a1 + 0.7 * period)                     # cổng 2 lệch 0,7 chu kỳ sau a1: bộ {a1, b} phải tách
    push(cams, 1, a1 + 2 * period)
    now[0] = a1 + 2 * period + 0.001                     # lần hỏi tới muộn (AI đang bận): cổng 1 có HAI khung mới
    fs = cams.latest_set(0.1, max_wait_s=0.06)
    # bộ ứng viên chọn a1 cho cổng 1 (gần mốc b hơn); để dành cổng 2 thì bộ phát giữ ĐÚNG a1, không nhảy sang khung mới
    # hơn rồi bỏ qua a1
    assert stamps_of(fs) == pytest.approx({1: a1}) and fs.deferred == [2]
    assert cams.frames_skipped == {1: 0, 2: 0} and cams.sets_regrouped == 1


def test_lossy_camera_with_jitter_never_holds_frames_past_the_limit_and_is_the_only_one_left_out():
    """Cổng 1 mất 33 % khung ngẫu nhiên (không ghi lại: chỉ khung tốt), stamp rung ±4 ms, 10 hạt. Bản có bước để dành cả
    ở bộ phát vì hết hạn chờ bỏ oan cổng 4 ở hạt 9. Phép kiểm `partial_wait_ms ≤ L` chỉ ghim quy tắc (a), đúng theo cấu
    tạo; nó KHÔNG bắt được ước lượng chu kỳ sai (bản trung vị trần chờ tới 61,8 ms ở hạt 4, vẫn dưới L — người kiểm tra,
    24/09). Ước lượng chu kỳ được ghim riêng: phát lại dãy khung tốt của cổng 1, chu kỳ đo được phải trong ±2 ms quanh
    1/24 từ 2,0 s (bản sửa 24/09 lệch ≤ 0,32 ms; trung vị trần lệch 3,4–40 ms ở cả 10 hạt — mô phỏng 24/09)."""
    for seed in range(10):
        now = [0.0]
        cams = manual_manager(PORTS4, now)
        events = schedule({p: 1 / 24 for p in PORTS4}, {1: 0.0, 2: 0.01, 3: 0.02, 4: 0.03}, t_end=6.0, jitter=0.004,
                          loss={1: 0.33}, seed=seed, starts={1: 0.0, 2: 0.3, 3: 0.6, 4: 0.9})
        sets = run_schedule(cams, now, events, t_end=6.0, t_reset=2.0)
        st = cams.stats(window=None)
        assert st["partial_wait_ms"]["max"] <= st["wait_limit_ms"]["max"] + 2.5, (seed, st["partial_wait_ms"])
        assert len(sets) >= 0.95 * 24 * 4.0 and cams.lagging_per_port[1] > 0, seed
        assert cams.lagging_per_port[2] == cams.lagging_per_port[3] == cams.lagging_per_port[4] == 0, seed
        one = manual_manager((1,), now)                  # phát lại đúng dãy khung tốt cổng 1 đã nạp
        for t, p in events:
            if p == 1:
                push(one, 1, t)
                if t >= 2.0:
                    assert one.workers[1].frame_interval_s() == pytest.approx(1 / 24, abs=0.002), (seed, round(t, 3))


@pytest.mark.parametrize("phases_ms", [(0, 2, 4, 6), (6, 4, 2, 0)])
def test_cameras_opened_one_after_another_end_up_grouped_by_phase(phases_ms):
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    events = schedule({p: 1 / 24 for p in PORTS4}, {p: ph / 1000 for p, ph in zip(PORTS4, phases_ms)}, t_end=5.5,
                      starts={1: 0.0, 2: 0.3, 3: 0.6, 4: 0.9})          # như MultiCameraManager.start(sequential=True)
    # camera vào sau ở pha không may: hai bộ ghép lệch một chu kỳ (chưa rõ nhịp nó), rồi một bộ để dành — xong trước 2,1 s
    sets = run_schedule(cams, now, events, t_end=5.5, t_reset=2.5)
    assert len(sets) >= 0.95 * 24 * 3.0 and all(len(fs.frames) == 4 for fs in sets)
    assert max(fs.skew_s for fs in sets) <= 0.0065           # bản đầu: ≈ 40 ms (khung chu kỳ k ghép với chu kỳ k+1)
    assert cams.sets_partial_wait == 0 and cams.sets_regrouped == 0


# ---- nhịp khung thật: khoảng cách xen kẽ ≈ 31 / 48 ms (các test ở trên dùng lưới đều) -------------------------------

@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("loss, damaged", [(0.0, False), (0.2, False), (0.36, True), (0.6, True)])
def test_frame_interval_is_the_mean_period_of_an_alternating_cadence(loss, damaged, seed):
    """Mọi cửa sổ (từ khung thứ 30) lệch < 3,5 ms so với chu kỳ trung bình thật (≈ 41,9 ms). Bộ ước lượng lưới cũ lệch tới
    11–37 ms (xen kẽ đều 48/31 ms ra 24 ms). Khung hỏng mà nguồn báo (cắt/xé) được ghi lần tới nên tỉ lệ hỏng không làm
    lệch (bản sửa: ≤ 2,2 ms cả khi 60 % hỏng). Mất KHÔNG ghi lại (driver bỏ hẳn khung) chỉ thử tới 20 %, ngưỡng 4,5 ms
    (bản sửa: ≤ 4,0 ms); ở 33 % có ≈ 1 % cửa sổ lệch tới 11 ms vì còn quá ít khoảng ngắn để tách "một khoảng" với "hai
    khoảng" — giới hạn đã biết, chưa sửa (mô phỏng 24/09)."""
    now = [0.0]
    cams = manual_manager((1,), now)
    events = alternating_events((1,), {1: 0.0}, 12.0, jitter=0.003, loss={1: loss}, damaged=damaged, seed=seed)
    true_mean = float(np.mean(np.diff([t for t, _ in alternating_events((1,), {1: 0.0}, 12.0, seed=seed)])))
    worst = 0.0
    for i, e in enumerate(events):
        (push_damaged if len(e) > 2 else push)(cams, 1, e[0])
        if i >= 30:
            worst = max(worst, abs(cams.workers[1].frame_interval_s() - true_mean))
    assert true_mean == pytest.approx(0.0419, abs=0.001)
    assert worst < 0.0045 if (loss, damaged) == (0.2, False) else worst < 0.0035, worst


@pytest.mark.parametrize("pattern_ms, mean_ms", [((48, 31), 39.5), ((31.4, 48.3, 48.3, 31.4, 48.3), 41.54),
                                                  ((30, 50), 40.0)])
def test_frame_interval_of_a_strictly_repeating_uneven_cadence_is_its_mean(pattern_ms, mean_ms):
    """30/50 ms (tỉ số 1,67 > SINGLE_SPAN): chỉ có bước nới WIDEN_SPAN mới kéo cụm 50 ms vào "một khoảng"; thiếu nó thì
    khoảng 50 ms bị coi là hai khung và chu kỳ ra ≈ 27 ms."""
    now = [0.0]
    cams = manual_manager((1,), now)
    t = 1.0
    for k in range(40):
        push(cams, 1, t)
        t += pattern_ms[k % len(pattern_ms)] / 1000
    assert 1000 * cams.workers[1].frame_interval_s() == pytest.approx(mean_ms, abs=1.0)     # bản lưới cũ: 24,0 / 24,2 ms


def test_worker_counts_truncated_and_torn_frames_as_arrivals_but_not_repeated_frames():
    """CameraWorker thật với FakeCamera 20 ms: lần đọc 2, 4… bị cắt, 3, 9… bị xé, 5, 10… là khung cũ. Khung tốt chỉ còn
    ≈ 8/30 và cách nhau 40–120 ms; nhịp camera vẫn là 20 ms (khung cắt/xé đã tới), khung cũ thì không phải lần tới."""
    cams = fake_manager(ports=(1,), period=0.02, trunc_every=2, torn_every=3, dup_every=5)
    cams.start()
    try:
        time.sleep(1.0)
    finally:
        cams.stop()
    w = cams.workers[1]
    s = w.stats
    assert s.truncated > 5 and s.torn > 2 and s.duplicates > 2 and s.frames >= 5
    good_gaps = np.diff(list(s.recent))
    assert np.median(good_gaps) > 0.035                          # chỉ khung tốt: không ước lượng nổi 20 ms
    assert len(w.arrivals) > len(s.recent)
    assert w.frame_interval_s() == pytest.approx(0.02, rel=0.2)   # chỉ khung tốt thì ra 40 ms


def test_two_cameras_with_alternating_gaps_form_the_same_full_sets_as_the_old_rule():
    """Tất định, không rung, không mất khung: hai camera khoảng cách xen kẽ đúng 48/31 ms, cổng 2 trễ 5 ms, hỏi mỗi 1 ms.
    Bộ ước lượng lưới cũ cho 31 ms: 30 bộ trong 3,0–3,8 s, chỉ 10 bộ đủ, cổng khỏe bị bỏ "chậm" (người kiểm tra, 24/09)."""
    out = {}
    for max_wait_s in (0.06, None):
        now = [0.0]
        cams = manual_manager((1, 2), now)
        events = []
        for port, phase in ((1, 0.0), (2, 0.005)):
            t = 1.0 + phase
            for k in range(80):
                events.append((round(t, 6), port))
                t += 0.048 if k % 2 == 0 else 0.031
        events.sort()
        sets = run_schedule(cams, now, events, t_end=3.8, t_reset=3.0, max_wait_s=max_wait_s, max_skew_s=0.06,
                            poll=0.001)
        out[max_wait_s] = [(sorted(stamps_of(fs).items()), fs.lagging, fs.deferred) for fs in sets]
        assert cams.lagging_per_port == {1: 0, 2: 0} and cams.sets_regrouped == 0
    assert len(out[0.06]) == 20 and all(len(s) == 2 for s, _, _ in out[0.06])
    assert out[0.06] == out[None]


def quantized_schedule(phases, t_end, tick=0.016, tick_offsets=None, t0=1.0):
    """Khung phơi sáng ở t0 + pha + k/24 nhưng tới Python theo nhịp tick 16 ms của đường USB: khoảng cách 32/48 ms xen
    kẽ như m04, pha giữa các camera GIỮ NGUYÊN (khác `alternating_events`, nơi pha trôi ngẫu nhiên). Mỗi camera một pha
    tick."""
    events = []
    for p, ph in phases.items():
        off = (tick_offsets or {}).get(p, 0.0)
        k = 0
        while (t := t0 + ph + k / 24) <= t_end:
            events.append((off + math.ceil((t - off) / tick) * tick, p))
            k += 1
    return sorted(events)


@pytest.mark.parametrize("forced_period", [True, False])
@pytest.mark.parametrize("phases_ms", [(0, 8, 16, 24), (0, 11, 22, 33), (0, 5, 10, 15), (0, 2, 4, 6)])
def test_healthy_cameras_on_a_usb_quantized_cadence_always_form_full_sets(phases_ms, forced_period):
    """Nhịp gần thật nhất (pha cố định như phát lại m04). Mọi bộ đủ bốn camera, không bỏ, không để dành.
    `forced_period`: ép P = 1/24 để chỉ thử quy tắc (c) — quyết (c) trên MỘT bộ thì stamp của hai camera cùng chu kỳ dao
    động ±8 ms, cỡ ngưỡng P/3, và pha 0/8/16/24, 0/11/22/33 bị tách 50 / 40 lần trong 4 s. Không ép: bộ ước lượng lưới cũ
    ra 24 ms và bỏ camera khỏe ở 14–36 % số bộ (mô phỏng 24/09)."""
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    if forced_period:
        cams.frame_periods = lambda ports: {p: 1 / 24 for p in ports}
    events = quantized_schedule({p: ms / 1000 for p, ms in zip(PORTS4, phases_ms)}, t_end=6.0,
                                tick_offsets={1: 0.0, 2: 0.005, 3: 0.011, 4: 0.003})
    gaps = np.diff([t for t, p in events if p == 1])
    assert gaps.min() < 0.033 and gaps.max() > 0.047                 # đúng là nhịp xen kẽ 32/48 ms
    sets = run_schedule(cams, now, events, t_end=6.0, t_reset=2.0)
    assert len(sets) >= 0.95 * 24 * 4.0 and all(len(fs.frames) == 4 for fs in sets)
    assert cams.sets_regrouped == 0 and cams.sets_partial_wait == 0 and set(cams.lagging_per_port.values()) == {0}
    assert cams.stats(window=None)["wait_limit_ms"]["median"] == pytest.approx(62.5, abs=1.5)


@pytest.mark.parametrize("seed", range(2))
@pytest.mark.parametrize("phases_ms", [(0, 5, 10, 15), (0, 20, 3, 12), (0, 8, 16, 24)])
def test_healthy_cameras_with_drifting_alternating_cadence_are_rarely_left_out(phases_ms, seed):
    """Nhịp Markov 31,4/48,3 ms độc lập từng camera, rung 3 ms: pha giữa các camera TRÔI ngẫu nhiên, đi qua cả những pha
    mà ghép nhóm tự nó mơ hồ — khắc nghiệt hơn phát lại m04 (ở đó 100 % bộ đủ, 0 lần bỏ). Bản sửa: mỗi cổng khỏe bị bỏ
    0,7–2,7 % số bộ (do mép "nhóm sau" của (b): khung của camera cho nhóm này đã vào bộ trước — chưa sửa), 90–94 % bộ đủ,
    24,3–24,7 bộ/s. Bản trước (lưới + (c) một bộ): 14–25 % mỗi cổng, 23–39 % bộ đủ, 29–32 bộ/s — vượt tốc độ camera
    ≈ 23,9 khung/s (mô phỏng 24/09)."""
    phases = {p: ms / 1000 for p, ms in zip(PORTS4, phases_ms)}
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    events = alternating_events(PORTS4, phases, 9.0, jitter=0.003, seed=seed)
    sets = run_schedule(cams, now, events, 9.0, 3.0, max_wait_s=0.06, max_skew_s=0.06)
    st = cams.stats(window=None)
    assert max(st["lagging_per_port"].values()) <= 0.04 * len(sets), st["lagging_per_port"]
    assert sum(len(fs.frames) == 4 for fs in sets) >= 0.85 * len(sets)
    assert len(sets) / 6.0 < 26.0
    assert st["wait_limit_ms"]["median"] == pytest.approx(62.0, abs=2.0)      # 1,5 × ≈ 41 ms, không phải sàn 60 ms


@pytest.mark.parametrize("seed", range(3))
def test_only_the_camera_with_damaged_bursts_lags_on_an_alternating_cadence(seed):
    """Cổng 1 hỏng 36 % khung theo đợt 1 s (như cổng 1 ở 480p, đo 23/09), nguồn loại khung hỏng. Bản sửa: cổng 1 bị bỏ
    ≈ 19–20 % số bộ, mỗi cổng khỏe ≤ 3,4 %."""
    phases = {1: 0.0, 2: 0.005, 3: 0.010, 4: 0.015}
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    events = alternating_events(PORTS4, phases, 9.0, jitter=0.003, loss={1: 0.36}, burst_s=1.0, damaged=True, seed=seed)
    sets = run_schedule(cams, now, events, 9.0, 3.0, max_wait_s=0.06, max_skew_s=0.06)
    lag = cams.lagging_per_port
    assert lag[1] > 0.1 * len(sets) and max(lag[2], lag[3], lag[4]) <= 0.045 * len(sets), lag


def test_regroup_needs_a_gain_above_a_third_of_a_period():
    """Mở lần lượt, pha 0/8/16/24: bộ khóa {8, 16, 24, 41,7} lệch 33,7 ms, ghép lại chỉ còn 24 ms — lợi 9,7 ms < P/3,
    không ghép lại (ghim REGROUP_GAIN; đây là giới hạn đã chọn, không phải tối ưu)."""
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    events = schedule({p: 1 / 24 for p in PORTS4}, {p: ph / 1000 for p, ph in zip(PORTS4, (0, 8, 16, 24))}, t_end=5.0,
                      starts={1: 0.0, 2: 0.3, 3: 0.6, 4: 0.9})
    sets = run_schedule(cams, now, events, t_end=5.0, t_reset=2.0)
    assert cams.sets_regrouped == 0 and all(len(fs.frames) == 4 for fs in sets)
    assert np.median([fs.skew_s for fs in sets]) == pytest.approx(1 / 24 - 0.008, abs=0.001)


def test_out_of_phase_keeps_an_older_cluster_it_cannot_predict():
    """Cụm cũ có camera chậm (chu kỳ > SAME_CADENCE × P) hay chưa rõ nhịp thì không để dành cụm mới (ghim SAME_CADENCE)."""
    fs = build_set({1: ring_of(1, [1.000]), 2: ring_of(2, [1.030])}, now=1.031)
    assert MultiCameraManager.out_of_phase(fs, {1: 1 / 24, 2: 1 / 24}) == [2]
    assert MultiCameraManager.out_of_phase(fs, {1: 2 / 24, 2: 1 / 24}) == []
    assert MultiCameraManager.out_of_phase(fs, {1: None, 2: 1 / 24}) == []


def test_out_of_phase_decides_on_median_offsets_not_one_jittered_set():
    """Bốn camera cùng chu kỳ, pha 0/8/16/24 ms; một bộ rung (camera 4 tới muộn 16 ms) một mình đủ vượt ngưỡng, nhưng
    trung vị độ lệch qua 5 bộ thì không: không tách. Bộ khóa lệch pha thật (camera 4 ở chu kỳ trước của 1–3) ở mọi bộ:
    tách. Bộ khóa mà chính bộ hiện tại rung ngược thứ tự hai cụm: chưa tách."""
    period = 1 / 24
    periods = {p: period for p in PORTS4}
    base = [0.0, 0.008, 0.016, 0.024]
    hist = [{p: 1.0 + k * period + b for p, b in zip(PORTS4, base)} for k in range(4)]
    jittered = {1: 1.0 + 4 * period, 2: 1.0 + 4 * period + 0.008, 3: 1.0 + 4 * period + 0.016, 4: 1.0 + 4 * period + 0.040}
    fs = build_set({p: ring_of(p, [t]) for p, t in jittered.items()}, now=jittered[4] + 0.001)
    assert MultiCameraManager.out_of_phase(fs, periods) == [4]                    # một bộ: tách oan
    assert MultiCameraManager.out_of_phase(fs, periods, hist + [jittered]) == []
    near = [0.0, 0.002, 0.004, 0.006]
    locked = [{p: 1.0 + (k + (p != 4)) * period + b for p, b in zip(PORTS4, near)} for k in range(5)]
    locked[-1][4] += 0.012
    cur = locked[-1]
    fs = build_set({p: ring_of(p, [t]) for p, t in cur.items()}, now=max(cur.values()) + 0.001)
    assert MultiCameraManager.out_of_phase(fs, periods, locked) == [1, 2, 3]
    flipped = [dict(h) for h in locked]
    flipped[-1][4] = flipped[-1][1] + 0.001                                     # bộ hiện tại: camera 4 tới SAU camera 1
    fs = build_set({p: ring_of(p, [t]) for p, t in flipped[-1].items()}, now=max(flipped[-1].values()) + 0.001)
    assert MultiCameraManager.out_of_phase(fs, periods, flipped) == []


def test_ai_batch_holds_only_the_cameras_in_the_set_and_carries_the_last_result_of_a_lagging_camera():
    now = [1.00]
    cams = manual_manager((1, 2, 3), now)
    seg = FakeSegmenter("m.pt", delay=0.0)
    ai = AIWorker(cams, lambda path: seg, "m.pt", 32, 0.1, clock=lambda: now[0], max_wait_s=0.06)
    ai._ensure_model()
    for p in (1, 2, 3):
        push(cams, p, 1.00, value=40 * p)
    assert ai.step() and seg.batch_sizes == [3]
    first = ai.result()
    assert first.batch_id == 0 and first.carried == {} and sorted(first.probs) == [1, 2, 3]
    push(cams, 1, 1.04)
    push(cams, 2, 1.04)
    now[0] = 1.05
    assert not ai.step() and seg.batch_sizes == [3]                 # còn chờ camera 3
    now[0] = 1.065
    assert ai.step() and seg.batch_sizes == [3, 2]                  # lô chỉ có hai camera trong bộ
    r = ai.result()
    assert sorted(r.probs) == [1, 2] and r.frame_set.lagging == [3] and r.batch_id == 1
    held = r.carried[3]                                             # kết quả của camera 3 từ lô 0, đúng khung đã chấm
    assert held.batch_id == 0 and held.t_done == pytest.approx(1.00) and held.checkpoint == "m.pt"
    assert held.frame is first.frame_set.frames[3] and held.prob is first.probs[3]
    assert sorted(r.carried) == [3] and ai.by_port[1].batch_id == 1
    st = ai.stats(now[0], window=None)
    assert st["batches"] == 1 and st["images"] == 2 and st["batches_partial_wait"] == 1 and st["max_wait_ms"] == 60.0
    ai.request_model("n.pt")                                        # đổi mô hình: không mang kết quả của mô hình cũ
    ai._ensure_model()
    assert ai.checkpoint == "n.pt" and ai.by_port == {}
    push(cams, 1, 1.10)
    push(cams, 2, 1.10)
    now[0] = 1.14
    assert ai.step() and ai.result().frame_set.lagging == [3] and ai.result().carried == {}


def slow_camera_rig_rates(max_wait_s):
    """Ba camera 20 ms, cổng 4 chu kỳ 60 ms; trả (AI bộ/s, fps camera nhanh, fps camera chậm, tổng kết)."""
    cams = fake_manager(ports=(1, 2, 3, 4), period=0.02, periods={4: 0.06})
    rig = Rig(cams, RigConfig(checkpoint="m.pt", display_width=16, max_wait_s=max_wait_s),
              make_segmenter=lambda p: FakeSegmenter(p, delay=0.002))
    rig.start()
    try:
        time.sleep(0.5)
        rig.reset_counters()
        time.sleep(2.0)
        s = rig.summary()
        s["series"] = list(rig.series)
    finally:
        rig.stop()
    fps = {c["port"]: c["fps_mean"] for c in s["cameras"]}
    return s["ai"]["sets_per_s_mean"], min(fps[1], fps[2], fps[3]), fps[4], s


def test_ai_keeps_the_fast_cameras_rate_when_one_camera_is_slow():
    on_rate, fast, slow, on = slow_camera_rig_rates(0.03)            # 1,5 chu kỳ của camera nhanh
    off_rate, fast_off, slow_off, off = slow_camera_rig_rates(None)
    assert slow < 0.5 * fast and slow_off < 0.5 * fast_off           # đúng là có một camera chậm
    assert on_rate > 0.75 * fast, (on_rate, fast, slow)              # bật chờ: gần tốc độ camera nhanh
    assert off_rate < 1.2 * slow_off, (off_rate, fast_off, slow_off)  # tắt: bằng camera chậm nhất, như trước
    assert on["sets"]["sets_partial_wait"] > 0 and on["sets"]["lagging_per_port"][4] > 0
    assert on["sets"]["lagging_per_port"][1] <= 0.1 * on["sets"]["lagging_per_port"][4]
    assert on["ai"]["batches_partial_wait"] > 0 and on["ai"]["images"] < 4 * on["ai"]["batches"]
    assert off["sets"]["sets_partial_wait"] == 0 and off["ai"]["images"] == 4 * off["ai"]["batches"]
    assert on["policy"]["max_wait_ms"] == 30.0 and off["policy"]["max_wait_ms"] is None
    assert sum(row["sets_partial_wait_1s"] for row in on["series"]) > 0
    assert sum(row["cam_lagging_1s"][4] for row in on["series"]) > 0
    assert all(row["sets_partial_wait_1s"] == 0 for row in off["series"])


def test_rig_runs_cameras_lidar_and_ai_together():
    cams = fake_manager(period=0.02)
    rig = Rig(cams, RigConfig(checkpoint="m.pt", display_width=32, max_skew_s=0.1),
              make_segmenter=lambda path: FakeSegmenter(path), open_lidar=lambda: FakeLidar(period=0.05, fail_first=1))
    rig.start()
    try:
        time.sleep(1.5)
        result = rig.ai.result()
        snap = rig.snapshot()
        summary = rig.summary()
    finally:
        alive = rig.stop()
    assert alive == [] and summary["clock"]["name"] == "perf_counter"
    assert result is not None and sorted(result.probs) == [1, 2, 3, 4] and result.probs[1].shape == (24, 32)   # 4:3 giữ tỉ lệ
    b, n = summary["ai"]["batches"], summary["ai"]["images"]
    assert b > 5 and 3 * b < n <= 4 * b          # vài lô đầu thiếu camera chưa kịp mở (bộ ảnh thiếu, có đếm)
    assert summary["ai"]["first_batch_ms"] is not None and summary["ai"]["window"] == "cả phiên"
    vs = summary["lidar"]["vs_set"]
    assert vs["last_minus_anchor_ms"]["n"] > 5 and vs["sweep_ms"]["median"] == pytest.approx(50, abs=20)
    assert result.lidar is not None and "last_minus_anchor_ms" in result.lidar
    assert summary["lidar"]["scans"] > 5 and summary["lidar"]["errors"] == 1 and summary["lidar"]["hz_mean"] > 5
    assert summary["sets"]["sets_built"] > 5 and summary["sets"]["skew_ms"]["median"] is not None
    assert snap["cameras"]["cameras"][0]["fps_last2s"] > 10
    row = rig.series[-1]
    assert "cam_frames_1s" in row and row["ai_batches_1s"] >= 0 and 0 < sum(row["cam_frames_1s"].values()) < 400
    assert not any(w.is_alive() for w in cams.workers.values())


def test_set_loop_measures_skew_when_ai_is_off_or_disabled():
    cams = fake_manager(period=0.02)
    rig = Rig(cams, RigConfig(ai=False), open_lidar=lambda: FakeLidar(period=0.05))
    rig.start()
    try:
        time.sleep(0.6)
        s = rig.summary()
        assert rig.ai is None and s["sets"]["skew_ms"]["n"] > 0 and s["lidar"]["vs_set"]["last_minus_anchor_ms"]["n"] > 0
    finally:
        rig.stop()
    cams = fake_manager(period=0.02)
    rig = Rig(cams, RigConfig(checkpoint="a.pt"), make_segmenter=lambda p: FakeSegmenter(p))
    rig.start()
    try:
        time.sleep(0.4)
        rig.ai.enabled.clear()                                         # tắt AI trên giao diện
        time.sleep(0.1)
        built = rig.cams.sets_built
        time.sleep(0.4)
        assert rig.cams.sets_built > built                             # số bộ ảnh vẫn chạy, không đứng yên
    finally:
        rig.stop()


def set_loop_rates(max_wait_s):
    """AI tắt: luồng nền `_set_loop` tự ghép bộ. Ba camera 20 ms, cổng 4 chu kỳ 60 ms."""
    cams = fake_manager(ports=(1, 2, 3, 4), period=0.02, periods={4: 0.06})
    rig = Rig(cams, RigConfig(ai=False, max_wait_s=max_wait_s))
    rig.start()
    try:
        time.sleep(0.5)
        rig.reset_counters()
        time.sleep(1.5)
        s = rig.summary()
    finally:
        rig.stop()
    fps = {c["port"]: c["fps_mean"] for c in s["cameras"]}
    return s["sets"]["sets_built"] / s["duration_s"], min(fps[1], fps[2], fps[3]), fps[4], s


def test_background_set_loop_applies_max_wait_when_ai_is_off():
    on_rate, fast, slow, on = set_loop_rates(0.03)
    off_rate, fast_off, slow_off, off = set_loop_rates(None)
    assert on["ai"] is None and slow < 0.5 * fast                       # đúng là có một camera chậm, không có AI
    assert on["sets"]["sets_partial_wait"] > 0 and on["sets"]["lagging_per_port"][4] > 0
    assert on_rate > 0.75 * fast, (on_rate, fast, slow)                 # bật chờ: gần tốc độ camera nhanh
    assert off["sets"]["sets_partial_wait"] == 0 and off_rate < 1.2 * slow_off, (off_rate, slow_off)   # tắt: theo camera chậm
    assert on["policy"]["max_wait_ms"] == 30.0 and on["sets"]["wait_limit_ms"]["n"] > 0
    assert off["sets"]["wait_limit_ms"]["n"] == 0


def test_rig_with_healthy_cameras_slower_than_the_wait_floor_keeps_full_batches():
    """Bốn FakeCamera khỏe 15 fps (chu kỳ 66,7 ms > sàn 60 ms), luồng thật. Bản đầu: 85/102 bộ thiếu một camera."""
    cams = fake_manager(ports=(1, 2, 3, 4), period=1 / 15)
    rig = Rig(cams, RigConfig(checkpoint="m.pt", display_width=16, max_wait_s=0.06),
              make_segmenter=lambda p: FakeSegmenter(p, delay=0.002))
    rig.start()
    try:
        time.sleep(0.8)
        rig.reset_counters()
        time.sleep(2.5)
        s = rig.summary()
    finally:
        rig.stop()
    a, st = s["ai"], s["sets"]
    assert a["batches"] >= 30 and a["sets_per_s_mean"] < 17.0            # ≈ 15 bộ/s, không "tăng" nhờ bộ thiếu camera
    assert st["sets_partial_wait"] <= 0.1 * a["batches"], st            # dung sai cho luồng bị trễ khi máy đang bận
    assert a["images"] >= 3.9 * a["batches"]
    assert st["wait_limit_ms"]["median"] == pytest.approx(100.0, rel=0.1)


def test_model_switch_during_load_ends_on_the_last_choice():
    def slow(path):
        time.sleep(0.3)
        if path == "bad.pt":
            raise FileNotFoundError(path)
        return FakeSegmenter(path)

    cams = fake_manager(period=0.02)
    rig = Rig(cams, RigConfig(checkpoint="a.pt"), make_segmenter=slow)
    rig.start()
    try:
        time.sleep(0.6)
        rig.ai.request_model("b.pt")
        time.sleep(0.1)
        rig.ai.request_model("c.pt")                                   # chọn C khi B đang nạp
        time.sleep(1.2)
        assert rig.ai.checkpoint == "c.pt" and rig.ai.result().model == "fake:c.pt" and rig.ai.result().checkpoint == "c.pt"
        rig.ai.request_model("bad.pt")
        time.sleep(0.1)
        rig.ai.request_model("d.pt")                                   # chọn D khi bad đang nạp (và sẽ hỏng)
        time.sleep(1.5)
        assert rig.ai.checkpoint == "d.pt" and rig.ai.load_error is None
        rig.ai.request_model("bad.pt")
        time.sleep(0.8)
        assert rig.ai.checkpoint == "d.pt" and rig.ai.requested == "d.pt" and "FileNotFoundError" in rig.ai.load_error
    finally:
        rig.stop()


def test_bench_main_writes_summary_json(tmp_path, monkeypatch, capsys):
    def fake_build(args):
        cams = fake_manager(period=0.02, periods={4: 0.05})
        return Rig(cams, RigConfig(checkpoint="m.pt", display_width=16, max_wait_s=args.max_wait_ms / 1000.0),
                   make_segmenter=lambda p: FakeSegmenter(p), open_lidar=lambda: FakeLidar(period=0.05))
    monkeypatch.setattr(bench, "build_rig", fake_build)
    code = bench.main(["--name", "t1", "--seconds", "1.2", "--warmup", "0.3", "--out", str(tmp_path), "--max-wait-ms", "30"])
    data = json.loads((tmp_path / "t1.rig.json").read_text(encoding="utf-8"))
    assert code == 0 and data["name"] == "t1" and 1.0 < data["duration_s"] < 2.0 and data["stop_alive"] == []
    assert data["ai"]["batches"] > 0 and len(data["cameras"]) == 4 and data["cameras"][0]["fps_mean"] > 5
    assert "resources" in data and "series" in data and data["clock"]["name"] == "perf_counter"
    assert data["config"]["max_wait_s"] == 0.03 and data["policy"]["max_wait_ms"] == 30.0
    assert data["sets"]["sets_partial_wait"] > 0 and data["sets"]["lagging_per_port"]["4"] > 0   # khóa json là chuỗi
    assert data["sets"]["partial_wait_ms"]["n"] > 0 and data["ai"]["batches_partial_wait"] > 0
    assert "sets_partial_wait_1s" in data["series"][0] and "cam_lagging_1s" in data["series"][0]
    assert data["policy"]["wait_periods_of_fastest"] == 1.5 and data["sets"]["wait_limit_ms"]["n"] > 0
    assert "sets_regrouped" in data["sets"] and "sets_regrouped_1s" in data["series"][0]
    out = capsys.readouterr().out
    assert "chờ camera chậm tối đa max(30.0 ms; 1.5 × chu kỳ camera nhanh nhất)" in out
    # Dòng trực tiếp: số bộ cổng 4 bị bỏ và tổng số bộ thiếu camera chậm phải là số thật (> 0), không vượt số cuối cùng
    # (bộ đếm tích lũy từ reset_counters; print_line đọc snapshot trước summary nên ≤, không bằng).
    live = re.search(r"p4 [0-9.]+fps cũ\d+ cắt\d+ xé\d+ chậm(\d+)", out)
    assert live and 0 < int(live.group(1)) <= data["sets"]["lagging_per_port"]["4"]
    total = re.search(r"bộ thiếu cam chậm (\d+) \(ngưỡng chờ [0-9.]+ ms\)", out)
    assert total and 0 < int(total.group(1)) <= data["sets"]["sets_partial_wait"]
    # Tóm tắt: đúng số trong json (print_summary nhận đúng dict đã ghi).
    assert f"{data['sets']['sets_partial_wait']} bộ dùng thiếu camera chậm" in out
    assert f"{data['ai']['batches_partial_wait']} lô thiếu camera chậm" in out
    assert f"{data['sets']['sets_regrouped']} bộ để dành camera lệch pha" in out
    assert f"ngưỡng đã dùng trung vị {data['sets']['wait_limit_ms']['median']} ms" in out


def test_max_wait_flag_sets_the_rig_policy_and_zero_disables_it():
    import argparse

    p = argparse.ArgumentParser()
    bench.add_rig_args(p)
    assert bench.build_rig(p.parse_args(["--index", "0", "1", "--no-ai"])).cfg.max_wait_s == pytest.approx(0.06)
    assert bench.build_rig(p.parse_args(["--index", "0", "--no-ai", "--max-wait-ms", "25"])).cfg.max_wait_s == pytest.approx(0.025)
    rig = bench.build_rig(p.parse_args(["--index", "0", "--no-ai", "--max-wait-ms", "0"]))
    assert rig.cfg.max_wait_s is None and rig.policy()["max_wait_ms"] is None
    assert rig.policy()["wait_periods_of_fastest"] is None
    assert RigConfig().max_wait_s == pytest.approx(0.06)


def test_build_rig_passes_one_clock_to_cameras_lidar_and_rig(monkeypatch):
    import argparse

    import autopark.lidar.rplidar_c1 as rp
    seen = {}

    def fake_open(port, **kwargs):
        seen.update(kwargs)
        return FakeLidar()

    monkeypatch.setattr(rp.RplidarC1Source, "open", staticmethod(fake_open))
    p = argparse.ArgumentParser()
    bench.add_rig_args(p)
    args = p.parse_args(["--index", "0", "1", "--no-ai", "--lidar", "COM9"])
    rig = bench.build_rig(args)
    rig.lidar.open_source()
    assert rig.clock is RIG_CLOCK and rig.cams.clock is RIG_CLOCK and seen["clock"] is RIG_CLOCK
