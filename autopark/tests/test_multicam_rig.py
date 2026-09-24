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
from autopark.video.multicam import (RIG_CLOCK, CameraSpec, MultiCameraManager, build_set,  # noqa: E402
                                     clock_info, fit_width, pacing_ports)
from autopark.video.sources import _frame  # noqa: E402
from tests.rig_fakes import FakeCamera, FakeLidar, FakeSegmenter, fake_manager  # noqa: E402


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
    # ngưỡng RIÊNG từng camera = max(sàn, 1,5 × chu kỳ của chính nó); chưa rõ chu kỳ: max(sàn, 1,5 × camera nhanh nhất)
    assert cams.wait_limits_s(0.06, {1: 0.04, 2: 0.125, 3: None}) == pytest.approx({1: 0.06, 2: 0.1875, 3: 0.06})
    assert cams.wait_limits_s(0.06, {1: 1 / 15, 2: 1 / 24}) == pytest.approx({1: 0.1, 2: 0.0625})
    assert cams.wait_limits_s(0.06, {1: 1 / 15, 2: None}) == pytest.approx({1: 0.1, 2: 0.1})
    assert cams.wait_limits_s(0.06, {1: None}) == {1: 0.06}


def test_latest_set_docstring_describes_the_per_camera_rule():
    """Docstring của lối vào công khai không được tả lại quy tắc cũ (một ngưỡng chung theo camera nhanh nhất, bỏ 24/09)."""
    doc = MultiCameraManager.latest_set.__doc__
    assert "wait_limits_s" in doc and "CHÍNH nó" in doc and "snapshot_with_arrival" in doc
    assert "camera nhanh nhất), rồi bộ" not in doc


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


@pytest.mark.parametrize("fps", [{1: 24, 2: 24, 3: 24, 4: 12}, {1: 24, 2: 8}, {1: 24, 2: 24, 3: 24, 4: 15}])
def test_healthy_camera_at_a_lower_natural_rate_is_waited_for_and_paces_the_sets(fps):
    """Mỗi camera xét theo nhịp của CHÍNH nó (sửa 24/09, người dùng duyệt): camera khỏe chậm hơn (phơi sáng dài ở chỗ
    tối: 15, 12, 8 khung/s) KHÔNG bị bỏ; nó định nhịp cả chuỗi, khung dư của camera nhanh không vào bộ nào. Bản trước
    (ngưỡng và "nhóm sau" theo camera NHANH nhất), cùng lịch này: bỏ nó ở 37,5 / 50 / 67 % số bộ (15 / 12 / 8 khung/s)
    để giữ 24 bộ/s — cùng loại lỗi đo được ở 720p ngày 24/09, chỉ khác tỉ lệ nhịp (xem test ngay sau)."""
    now = [0.0]
    ports = tuple(fps)
    slow = min(fps, key=fps.get)
    cams = manual_manager(ports, now)
    phases = {p: (0.005 if p == slow else 0.01 * k) for k, p in enumerate(ports)}
    events = schedule({p: 1 / f for p, f in fps.items()}, phases, t_end=6.0, jitter=0.002)
    sets = run_schedule(cams, now, events, t_end=6.0, t_reset=2.0)
    assert 0.95 * fps[slow] * 4.0 <= len(sets) <= 1.05 * fps[slow] * 4.0      # nhịp camera chậm, không phải camera nhanh
    assert all(len(fs.frames) == len(ports) for fs in sets) and cams.sets_partial_wait == 0
    assert set(cams.lagging_per_port.values()) == {0} and cams.sets_regrouped == 0 and cams.sets_rejected_skew == 0
    assert cams.frames_skipped[slow] == 0 and all(cams.frames_skipped[p] > 0 for p in ports if p != slow)
    st = cams.stats(window=None)
    assert st["wait_limit_ms"]["median"] == pytest.approx(1500 / fps[slow], rel=0.03)   # 1,5 × chu kỳ CỦA camera chậm
    by_port = {c["port"]: c for c in st["cameras"]}
    assert by_port[slow]["period_ms"] == pytest.approx(1000 / fps[slow], rel=0.03)
    assert by_port[1]["period_ms"] == pytest.approx(1000 / 24, rel=0.03)
    assert all(fs.wait_limits_s[slow] == pytest.approx(1.5 / fps[slow], rel=0.03) for fs in sets)


# Khoảng cách khung THẬT (ms), cắt từ runs/camera_bench/20260923 (thư mục bị git-ignore nên chép vào đây). Cổng 1 như
# camera 29,3 khung/s (m02_cam0_720p_exp-6, khoảng thứ 100–163, trung bình 34,3 ms); cổng 2–4 như camera 23,85 khung/s
# (n03_4cam_720p_auto_nofilm luồng 1, 2, 3; khoảng 200–247, 400–447, 600–647; trung bình 41,7 / 42,0 / 42,0 ms).
GAPS_29FPS_MS = [32.9, 47.4, 35.0, 30.6, 32.1, 31.7, 30.7, 31.8, 48.2, 32.4, 31.4, 31.8, 31.9, 32.1, 33.8, 47.9, 30.7,
                 31.8, 32.2, 33.8, 29.9, 34.7, 29.4, 48.6, 31.8, 31.9, 32.1, 33.3, 30.4, 34.4, 46.3, 31.5, 32.0, 31.6,
                 32.3, 36.1, 32.3, 27.7, 50.7, 32.4, 29.5, 33.6, 30.0, 31.8, 32.2, 48.0, 33.5, 30.3, 32.2, 34.2, 31.6,
                 32.6, 31.4, 47.7, 33.1, 29.4, 31.8, 32.2, 31.9, 32.6, 47.4, 32.2, 31.6, 32.6]
GAPS_24FPS_MS = {
    2: [32.1, 48.0, 32.2, 47.9, 48.9, 31.1, 47.8, 48.1, 32.0, 47.8, 32.4, 47.6, 48.5, 31.5, 48.1, 47.9, 32.2, 47.9, 31.9,
        47.9, 48.0, 32.2, 47.8, 32.9, 47.4, 48.0, 32.3, 47.5, 47.8, 32.1, 48.0, 33.3, 46.7, 48.2, 32.2, 47.9, 50.7, 29.2,
        48.0, 31.8, 48.0, 48.0, 32.2, 47.9, 47.8, 32.0, 48.1, 31.9],
    3: [48.6, 47.3, 32.2, 48.0, 31.7, 47.9, 47.9, 32.0, 47.8, 49.6, 30.7, 48.1, 32.2, 47.7, 48.0, 32.0, 48.0, 48.0, 32.5,
        47.6, 33.7, 46.4, 49.8, 32.2, 46.0, 47.9, 32.1, 47.9, 32.0, 48.0, 48.2, 31.9, 47.9, 32.2, 48.1, 47.8, 32.4, 48.4,
        49.7, 29.9, 47.9, 32.3, 47.4, 48.0, 33.0, 47.0, 48.4, 31.8],
    4: [48.2, 48.7, 31.1, 48.5, 31.8, 47.7, 48.0, 34.6, 46.1, 47.3, 32.5, 47.6, 33.4, 46.8, 48.0, 32.2, 48.8, 30.8, 48.2,
        47.8, 32.1, 47.8, 48.5, 31.8, 48.2, 31.8, 47.8, 48.2, 31.8, 48.0, 48.0, 32.2, 47.8, 31.9, 48.2, 47.8, 31.8, 48.2,
        47.9, 32.0, 48.5, 32.9, 50.1, 44.6, 32.4, 47.4, 32.4, 47.4]}


def replay_events(gaps_ms, phases, t_end, *, t0=1.0, jitter=0.0, seed=0, start=None, damaged=None):
    """Lịch khung (t, cổng[, "damaged"]) phát lại các dãy khoảng cách `gaps_ms[p]` (lặp vòng, bắt đầu ở chỉ số start[p]).
    `damaged[p]` = tập chỉ số khung bị hỏng mà nguồn báo (cắt/xé: `push_damaged`). Rung stamp 0 … jitter (lấy sau read)."""
    rnd, events = random.Random(seed), []
    for p, gaps in gaps_ms.items():
        t, k = t0 + phases[p], (start or {}).get(p, 0)
        while (t := t + gaps[k % len(gaps)] / 1000) <= t_end:
            stamp = t + (rnd.uniform(0, jitter) if jitter else 0.0)
            events.append((stamp, p, "damaged") if k in (damaged or {}).get(p, ()) else (stamp, p))
            k += 1
    return sorted(events)


@pytest.mark.parametrize("seed", range(4))
def test_real_720p_cadences_of_29_and_24_fps_leave_no_healthy_camera_out(seed):
    """Lỗi đo 24/09 (runs/may_moi_20260924_may_ban/m02_720p_chi_camera.rig.json, quy tắc trước): 720p, cổng 1 29,3
    khung/s, cổng 2–4 23,85 khung/s, cả bốn khỏe (0 khung hỏng) — mà cổng 2–4 bị bỏ "chậm" ở 263 / 855 bộ (106 / 137 /
    106), 28,5 bộ/s. Chính test này chạy với quy tắc trước (bản sao module cũ, 24/09): cổng 2–4 bị bỏ 10–15 % số bộ,
    26–28 bộ/s — cùng cỡ số thật. Quy tắc mới: mỗi cổng bị bỏ hay để dành ≤ 1 % số bộ (mục tiêu), chuỗi theo nhịp camera
    24 khung/s, khung dư của cổng 1 không vào bộ nào."""
    rnd = random.Random(seed)
    phases = {p: rnd.uniform(0, 0.042) for p in PORTS4}
    events = replay_events({1: GAPS_29FPS_MS, **GAPS_24FPS_MS}, phases, 15.0, jitter=0.002, seed=seed,
                           start={p: rnd.randrange(48) for p in PORTS4})
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    sets = run_schedule(cams, now, events, 15.0, 3.0, max_skew_s=0.06)
    left_out = {p: sum(p in fs.lagging or p in fs.deferred for fs in sets) for p in PORTS4}
    assert max(left_out.values()) <= 0.01 * len(sets), left_out
    assert 23.5 <= len(sets) / 12.0 <= 24.3, len(sets)
    assert cams.sets_rejected_skew == 0 and cams.frames_skipped[1] > 0.15 * len(sets)
    st = cams.stats(window=None)
    period = {c["port"]: c["period_ms"] for c in st["cameras"]}
    assert period[1] == pytest.approx(34.3, abs=2.0) and all(period[p] == pytest.approx(41.9, abs=2.0) for p in (2, 3, 4))
    assert st["wait_limit_ms"]["median"] == pytest.approx(63.0, abs=2.0)          # ngưỡng của camera 24 khung/s


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


@pytest.mark.parametrize("reported", [True, False])
def test_camera_whose_due_frame_arrives_damaged_is_left_out_as_soon_as_it_arrives(reported):
    """Hai camera 24 khung/s, cổng 2 trễ 15 ms; khung thứ 30 của cổng 2 hỏng. Nguồn BÁO khung hỏng (cắt/xé, như
    UsbCameraSource; lần tới vẫn được ghi): khung đúng lượt đã tới và hỏng, bộ phát ngay (khung cổng 1 chờ ≈ 15 ms).
    Nguồn không báo (driver bỏ hẳn khung): chờ tới khung dự đoán + P/2 ≈ 15 + 20,8 ms rồi mới bỏ. (Cổng 1 mở sau để
    bộ đầu ghép đúng nhóm: mở cùng lúc thì hai cổng khóa lệch một chu kỳ, độ lệch 26,7 ms, lợi ghép lại 11,7 ms < P/3
    — giới hạn REGROUP_GAIN đã biết, xem test_regroup_needs_a_gain_above_a_third_of_a_period.)"""
    period = 1 / 24
    events = schedule({1: period, 2: period}, {1: 0.0, 2: 0.015}, t_end=3.0, drop={2: {30}}, starts={1: 0.05})
    if reported:
        events = sorted(events + [(1.015 + 30 * period, 2, "damaged")])
    now = [0.0]
    cams = manual_manager((1, 2), now)
    sets = run_schedule(cams, now, events, t_end=3.0, t_reset=1.5)
    partial = [k for k, fs in enumerate(sets) if fs.lagging]
    assert len(partial) == 1 and sets[partial[0]].lagging == [2]
    fs = sets[partial[0]]
    assert stamps_of(fs) == pytest.approx({1: 1.0 + 30 * period})
    assert fs.waited_s == pytest.approx(0.015 if reported else 0.015 + period / 2, abs=0.0025)
    assert stamps_of(sets[partial[0] + 1]) == pytest.approx({1: 1.0 + 31 * period, 2: 1.015 + 31 * period})
    assert all(len(s.frames) == 2 for k, s in enumerate(sets) if k != partial[0]) and cams.frames_skipped == {1: 0, 2: 0}


FAST_720P, SLOW_720P = 1 / 29.3, 1 / 23.85     # nhịp đo 24/09 ở 720p (m02): cổng 1 / cổng 2–4


def grid_events(periods, phases, t_end, *, damaged=None, jitter=0.0, seed=0, t0=1.0):
    """Lịch khung (t, cổng[, "damaged"]) trên lưới đều: khung k của cổng p tới ở t0 + phases[p] + k·periods[p], stamp
    trễ thêm 0 … jitter (lấy sau read). `damaged[p]` = tập chỉ số k hỏng mà nguồn báo (cắt/xé: `push_damaged`)."""
    rnd, events = random.Random(seed), []
    for p, period in periods.items():
        k = 0
        while (t := t0 + phases[p] + k * period) <= t_end:
            stamp = t + (rnd.uniform(0, jitter) if jitter else 0.0)
            events.append((stamp, p, "damaged") if k in (damaged or {}).get(p, ()) else (stamp, p))
            k += 1
    return sorted(events)


def test_due_reference_is_the_oldest_new_frame_of_the_cameras_at_the_same_cadence():
    periods = {1: FAST_720P, 2: SLOW_720P, 3: SLOW_720P, 4: SLOW_720P}
    oldest_new = {1: 1.000, 2: 1.020, 3: 1.023}
    assert MultiCameraManager.due_reference(4, periods, oldest_new) == pytest.approx(1.020)   # không theo cổng 1 nhanh
    assert MultiCameraManager.due_reference(1, periods, {2: 1.020, 3: 1.023}) is None          # không ai cùng nhịp: t_old
    assert MultiCameraManager.due_reference(4, {**periods, 4: None}, oldest_new) is None             # chưa rõ nhịp
    assert MultiCameraManager.due_reference(4, {p: SLOW_720P for p in PORTS4}, oldest_new) == pytest.approx(1.000)


@pytest.mark.parametrize("phase1_ms", [0, 12, 20, 28])
@pytest.mark.parametrize("delay4_ms", [7, 19])
def test_slower_camera_losing_one_frame_among_a_faster_camera_misses_exactly_one_set(phase1_ms, delay4_ms):
    """Cổng 1 29,3 khung/s, cổng 2–4 23,85 khung/s (720p, m02, đo 24/09), cổng 4 tới sau cổng 2 `delay4_ms` (< P/2).
    Khung thứ 44 của cổng 4 hỏng (nguồn báo). Chỉ bộ của khung hỏng được thiếu cổng 4; khung tốt kế của nó đúng hạn
    nên bộ sau đủ, và cổng 4 vẫn ghép đúng nhóm cũ. Bản đoán khung đúng lượt theo t_old (khung mới cũ nhất của MỌI
    camera — thường là khung dư chưa dùng của cổng 1): 6 / 8 bộ tham số bỏ cổng 4 thêm một bộ rồi ghép nó trễ một chu
    kỳ mãi, độ lệch trung vị 19 → 26 ms, (c) không ghép lại vì lợi < P/3 (người kiểm tra, 24/09, đồng hồ giả)."""
    periods = {1: FAST_720P, 2: SLOW_720P, 3: SLOW_720P, 4: SLOW_720P}
    phases = {1: phase1_ms / 1000, 2: 0.0, 3: 0.003, 4: delay4_ms / 1000}
    events = grid_events(periods, phases, 4.0, damaged={4: {44}})
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    sets = run_schedule(cams, now, events, t_end=4.0, t_reset=1.5, max_skew_s=0.06)
    lag = [fs for fs in sets if fs.lagging]
    assert len(lag) == 1 and lag[0].lagging == [4], [(round(fs.t_built, 4), fs.lagging) for fs in lag]
    t_damaged = 1.0 + phases[4] + 44 * SLOW_720P
    assert lag[0].t_built == pytest.approx(t_damaged, abs=0.0025)          # (b'): bỏ ngay khi khung hỏng tới
    later = [fs for fs in sets if fs.t_built > t_damaged + SLOW_720P / 2]
    assert len(later) >= 25 and all(sorted(fs.frames) == [1, 2, 3, 4] for fs in later)
    assert all(0 < fs.frames[4].meta.stamp.t - fs.frames[2].meta.stamp.t < SLOW_720P / 2 for fs in later)
    assert cams.sets_rejected_skew == 0


@pytest.mark.parametrize("delay4_ms", [6, 12])
def test_slower_camera_with_damaged_bursts_among_a_faster_camera_is_left_out_once_per_damaged_frame(delay4_ms):
    """Cổng 1 29,3 + cổng 2–4 23,85 khung/s; cổng 4 hỏng 36 % khung theo đợt 1 s (nguồn báo), rung stamp 0–2 ms. Mỗi
    khung hỏng bỏ cổng 4 ở đúng một bộ (± 2 ở mép cửa sổ đo), không camera nào khác bị bỏ, chuỗi giữ nhịp 23,85 bộ/s.
    Bản đoán khung đúng lượt theo t_old, đúng lịch này (24/09, đồng hồ giả): 52 / 53 bộ bỏ cổng 4 cho 39 / 42 khung
    hỏng, 25,3 / 25,0 bộ/s (cổng 4 bị ghép trễ một chu kỳ nên có thêm bộ ghép khung dư của cổng 1); bản sửa: 39 / 42,
    23,89 / 23,78 bộ/s."""
    periods = {1: FAST_720P, 2: SLOW_720P, 3: SLOW_720P, 4: SLOW_720P}
    phases = {1: 0.011, 2: 0.0, 3: 0.003, 4: 0.003 + delay4_ms / 1000}
    rnd = random.Random(delay4_ms)
    damaged = {k for k in range(300) if (phases[4] + k * SLOW_720P) % 2.0 < 1.0 and rnd.random() < 0.36}
    events = grid_events(periods, phases, 12.0, damaged={4: damaged}, jitter=0.002, seed=delay4_ms)
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    sets = run_schedule(cams, now, events, t_end=12.0, t_reset=3.0, max_skew_s=0.06)
    n_damaged = sum(1 for e in events if len(e) > 2 and 3.0 <= e[0] < 12.0)
    lag = cams.lagging_per_port
    assert n_damaged > 30 and abs(lag[4] - n_damaged) <= 2, (lag, n_damaged)
    assert lag[1] == lag[2] == lag[3] == 0 and cams.sets_rejected_skew == 0
    assert len(sets) / 9.0 == pytest.approx(23.85, abs=0.3)


def test_good_frame_arriving_while_the_set_is_being_built_is_not_taken_for_a_damaged_due_frame(monkeypatch):
    """Luồng camera ghi khung TỐT đúng lượt của cổng 2 SAU khi `latest_set` đã chụp vòng đệm, trước lúc xét (b')
    (`frame_periods` luôn chạy giữa hai lúc đó). Bản đọc lần tới riêng (`last_arrival()` sau ảnh chụp) thấy một lần tới
    mới mà vòng đệm không có khung tốt nào → tưởng khung đúng lượt đã hỏng → bỏ cổng 2 khỏe (tái hiện tất định, người
    kiểm tra 24/09). Chụp vòng đệm và lần tới cùng một khóa: bộ này chờ, bộ kế đủ hai camera."""
    period = 1 / 24
    now = [0.0]
    cams = manual_manager((1, 2), now)
    events = schedule({1: period, 2: period}, {1: 0.0, 2: 0.006}, t_end=1.0 + 24.5 * period)
    run_schedule(cams, now, events, t_end=1.0 + 24.5 * period, t_reset=1.5)
    t1, t2 = 1.0 + 25 * period, 1.006 + 25 * period
    push(cams, 1, t1)
    now[0] = t1 + 0.001
    assert cams.latest_set(0.1, max_wait_s=0.06) is None                   # cổng 2 đúng hạn: chờ
    original = cams.frame_periods
    calls = []

    def racing_frame_periods(ports):
        if not calls:
            push(cams, 2, t2)                                               # khung tốt tới giữa ảnh chụp và (b')
        calls.append(ports)
        return original(ports)

    monkeypatch.setattr(cams, "frame_periods", racing_frame_periods)
    now[0] = t2 + 0.0005
    first = cams.latest_set(0.1, max_wait_s=0.06)
    assert calls and (first is None or (2 in first.frames and first.lagging == [])), first and first.lagging
    fs = first or cams.latest_set(0.1, max_wait_s=0.06)
    assert stamps_of(fs) == pytest.approx({1: t1, 2: t2}) and fs.lagging == []
    assert cams.lagging_per_port == {1: 0, 2: 0} and cams.sets_partial_wait == 0


def test_stalled_slow_camera_is_left_out_by_its_own_cadence_and_the_others_keep_their_rate():
    """Cổng 4 khỏe 15 khung/s định nhịp chuỗi (15 bộ/s), cổng 1–3 24 khung/s. Cổng 4 treo 0,4 s (không có lần tới nào,
    chưa quá stale_after_s): bộ đầu tiên thiếu nó được phát khi khung đúng lượt của nó trễ quá nửa chu kỳ CỦA NÓ — 1,5 ×
    66,7 = 100 ms sau khung tốt cuối, không phải 62,5 ms của camera 24 khung/s; một nhóm nữa còn chờ tới khung dự đoán
    kế + P/2 (2,5 chu kỳ = STALL_PERIODS), sau đó nó là "treo": không chờ nữa, chuỗi chạy theo nhịp 24 khung/s của các
    camera còn lại. Khi nó quay lại, chuỗi lại theo nó."""
    fps = {1: 24, 2: 24, 3: 24, 4: 15}
    events = schedule({p: 1 / f for p, f in fps.items()}, {1: 0.0, 2: 0.01, 3: 0.02, 4: 0.005}, t_end=6.0,
                      drop={4: set(range(30, 36))})              # khung 3,005 … 3,338 của cổng 4 không tới
    t_good, t_back = 1.005 + 29 / 15, 1.005 + 36 / 15              # khung tốt cuối trước khi treo, khung đầu khi quay lại
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    sets = run_schedule(cams, now, events, t_end=6.0, t_reset=2.0)
    lag = [fs for fs in sets if fs.lagging]
    assert all(fs.lagging == [4] for fs in lag) and set(cams.lagging_per_port[p] for p in (1, 2, 3)) == {0}
    assert lag[0].t_built == pytest.approx(t_good + 1.5 / 15, abs=0.003)
    assert lag[1].t_built == pytest.approx(t_good + 2.5 / 15, abs=0.003)
    # từ bộ thiếu thứ hai (t_good + 2,5 P) không nhóm nào còn chờ cổng 4: ≈ 24 bộ/s. Bước lag[1] → lag[2] ghim chính
    # STALL_PERIODS: với 4,0 thay cho 2,5 bước đó là 66 ms (bản sao đổi hệ số, người kiểm tra 24/09).
    during = lag[1:]
    assert all(b.t_built - a.t_built < 0.05 for a, b in zip(during, during[1:])), \
        [round(1000 * (fs.t_built - t_good), 1) for fs in lag[:4]]
    assert len(during) >= int((t_back - (t_good + 2.5 / 15)) * 24) - 1
    assert max(fs.waited_s for fs in lag) <= 1.5 / 15 + 0.003
    steady = [fs for fs in sets if fs.t_built < t_good or fs.t_built > t_back + 0.3]
    assert all(len(fs.frames) == 4 for fs in steady)
    assert len([fs for fs in steady if fs.t_built < t_good]) == pytest.approx((t_good - 2.0) * 15, abs=1.5)


def test_camera_sending_only_damaged_frames_past_the_stall_limit_is_not_stalled():
    """Cổng 2 gửi 6 khung hỏng liền (nguồn báo: cắt/xé), lâu hơn STALL_PERIODS = 2,5 chu kỳ kể từ khung tốt cuối, rồi
    khung tốt đúng lượt. Lần tới hỏng vẫn là "có tới" nên nó không bị coi là treo ((b'') xét lần tới TỐT HAY HỎNG): mỗi
    khung hỏng chỉ bỏ nó ở đúng nhóm đó ((b')), và khung tốt đầu tiên sau đợt hỏng vào đúng nhóm của nó. Nếu quy tắc treo
    chỉ xét khung tốt, khung đó bị bỏ ra một bộ thiếu nữa (bản sao sửa `t_seen = t_last`, người kiểm tra 24/09)."""
    period = 1 / 24
    burst = set(range(30, 36))
    events = schedule({1: period, 2: period}, {1: 0.0, 2: 0.015}, t_end=3.0, drop={2: burst}, starts={1: 0.05})
    events = sorted(events + [(1.015 + k * period, 2, "damaged") for k in burst])
    now = [0.0]
    cams = manual_manager((1, 2), now)
    sets = run_schedule(cams, now, events, t_end=3.0, t_reset=1.5)
    partial = [k for k, fs in enumerate(sets) if fs.lagging]
    assert len(partial) == len(burst) and all(sets[k].lagging == [2] for k in partial)
    assert stamps_of(sets[partial[-1] + 1]) == pytest.approx({1: 1.0 + 36 * period, 2: 1.015 + 36 * period})
    assert all(len(s.frames) == 2 and s.skew_s == pytest.approx(0.015, abs=1e-6)
               for k, s in enumerate(sets) if k not in partial)


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
    mà ghép nhóm tự nó mơ hồ — khắc nghiệt hơn phát lại m04 (ở đó 100 % bộ đủ, 0 lần bỏ). Quy tắc theo nhịp riêng (24/09):
    0 lần bỏ "chậm" ở cả 12 lần chạy (3 bộ pha × hạt 0–3), bị để dành (c) ≤ 3,4 % mỗi cổng — pha trôi qua mép nhóm thật
    thì (c) ghép lại, đó là việc của nó — 95–98 % bộ đủ, 23,7–24,3 bộ/s. Quy tắc trước (ngưỡng và "nhóm sau" theo camera
    nhanh nhất): mỗi cổng khỏe bị bỏ "chậm" 0,7–2,7 %, 90–94 % bộ đủ. Bản trước nữa (lưới + (c) một bộ): 14–25 % mỗi
    cổng, 23–39 % bộ đủ, 29–32 bộ/s — vượt tốc độ camera ≈ 23,9 khung/s (mô phỏng 24/09)."""
    phases = {p: ms / 1000 for p, ms in zip(PORTS4, phases_ms)}
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    events = alternating_events(PORTS4, phases, 9.0, jitter=0.003, seed=seed)
    sets = run_schedule(cams, now, events, 9.0, 3.0, max_wait_s=0.06, max_skew_s=0.06)
    st = cams.stats(window=None)
    assert max(st["lagging_per_port"].values()) <= 0.01 * len(sets), st["lagging_per_port"]
    left_out = {p: sum(p in fs.lagging or p in fs.deferred for fs in sets) for p in PORTS4}
    assert max(left_out.values()) <= 0.04 * len(sets), left_out
    assert sum(len(fs.frames) == 4 for fs in sets) >= 0.9 * len(sets)
    assert len(sets) / 6.0 < 25.0
    # lớn nhất trong các ngưỡng riêng, 1,5 × ≈ 42–43 ms (chu kỳ cửa sổ 25 khoảng của nhịp Markov), không phải sàn 60 ms
    assert st["wait_limit_ms"]["median"] == pytest.approx(64.0, abs=1.5)


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


# ---- camera khỏe khác nhịp: camera chậm nhất "định nhịp" (mốc bộ, quy tắc (c)) ----------------------------------------

def test_pacing_ports_are_the_cameras_at_the_slowest_cadence():
    assert pacing_ports({1: 1 / 24, 2: 1 / 24, 3: 1 / 15, 4: 1 / 15}) == [3, 4]
    assert pacing_ports({1: 0.0343, 2: 0.0419, 3: 0.0419}) == [2, 3]       # 29,3 và 23,85 khung/s (đo 24/09): khác nhịp
    assert pacing_ports({1: 0.0419, 2: 0.0450}) == [1, 2]                  # lệch 7 % (ước lượng rung): cùng nhịp
    assert pacing_ports({1: 1 / 24, 2: None}) is None and pacing_ports({}) is None


def test_build_set_can_take_the_anchor_from_the_pacing_cameras_only():
    """Cổng 4 chậm (định nhịp) vừa có khung 1,00; cổng 1 nhanh có hai khung mới 0,935 và 0,99; cổng 2 nhanh mới có
    0,96. Mốc theo mọi camera (0,96) kéo cổng 1 về khung CŨ 0,935: bộ lệch 65 ms (> max_skew 60 ms). Mốc theo camera định
    nhịp (1,00): cổng 1 chọn 0,99, lệch 40 ms."""
    rings = {1: ring_of(1, [0.935, 0.99]), 2: ring_of(2, [0.96]), 4: ring_of(4, [1.00])}
    fs = build_set(rings, now=1.001)
    assert fs.anchor_t == pytest.approx(0.96) and stamps_of(fs)[1] == pytest.approx(0.935)
    assert fs.skew_s == pytest.approx(0.065)
    fs = build_set(rings, now=1.001, anchor_ports=[4])
    assert fs.anchor_t == pytest.approx(1.00) and stamps_of(fs) == pytest.approx({1: 0.99, 2: 0.96, 4: 1.00})
    assert fs.skew_s == pytest.approx(0.04)
    assert build_set(rings, now=1.001, anchor_ports=[7]).anchor_t == pytest.approx(0.96)   # không cổng nào tươi: như cũ


def test_out_of_phase_regroups_only_the_pacing_cameras():
    """(c) chỉ xét camera định nhịp. (1) 29,3 + 23,85 khung/s (đo 24/09): cổng 1 nhanh tới trước cổng 2–4 30 ms ở mọi bộ
    — xét cả bộ (bản trước: P = chu kỳ camera nhanh nhất, tỉ số 1,22 < 1,25 coi là cùng nhịp) thì để dành oan cổng 2–4;
    xét camera định nhịp thì cổng 2–4 cùng pha, không tách. (2) Hai camera 15 khung/s khóa lệch 50 ms (ghép với khung kế
    của cổng 3 chỉ còn 16,7 ms) cạnh hai camera 24 khung/s: tách cổng 4, không đụng tới camera nhanh. (3) Chỉ một camera
    định nhịp: không có gì để tách."""
    periods = {1: 0.0343, 2: 0.0419, 3: 0.0419, 4: 0.0419}
    hist = [{1: 1.0 + k * 0.0419, 2: 1.03 + k * 0.0419, 3: 1.031 + k * 0.0419, 4: 1.032 + k * 0.0419} for k in range(5)]
    fs = build_set({p: ring_of(p, [t]) for p, t in hist[-1].items()}, now=1.2)
    assert MultiCameraManager.out_of_phase(fs, periods, hist) == []
    P = 1 / 15
    periods = {1: 1 / 24, 2: 1 / 24, 3: P, 4: P}
    hist = [{1: 1.0 + k * P + 0.02 + 0.01 * (k % 3), 2: 1.0 + k * P + 0.035 - 0.012 * (k % 2), 3: 1.0 + k * P,
             4: 1.0 + k * P + 0.05} for k in range(5)]
    fs = build_set({p: ring_of(p, [t]) for p, t in hist[-1].items()}, now=1.4)
    assert MultiCameraManager.out_of_phase(fs, periods, hist) == [4]
    assert MultiCameraManager.out_of_phase(fs, {**periods, 3: 1 / 24}, hist) == []


def test_two_slower_cameras_locked_out_of_phase_are_regrouped_among_themselves():
    """Hai camera 24 khung/s + hai camera 15 khung/s (định nhịp) mà cổng 4 tới sau cổng 3 50 ms. Mở cùng lúc thì bộ đầu
    ghép khung k của cổng 3 với khung k của cổng 4 (lệch 50 ms, cộng camera nhanh thì > 60 ms: bị bỏ) và khóa mãi nếu
    (c) chỉ chạy khi cả bộ cùng nhịp (mô phỏng 24/09: 37 / 75 bộ bị bỏ vì lệch). (c) trên camera định nhịp tách cổng 4 một
    lần, sau đó mọi bộ đủ và không bộ nào bị bỏ."""
    fps = {1: 24, 2: 24, 3: 15, 4: 15}
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    events = schedule({p: 1 / f for p, f in fps.items()}, {1: 0.02, 2: 0.035, 3: 0.0, 4: 0.05}, t_end=8.0, jitter=0.002)
    sets = run_schedule(cams, now, events, 8.0, 3.0, max_skew_s=0.06)
    assert cams.sets_rejected_skew == 0 and all(len(fs.frames) == 4 for fs in sets)
    assert len(sets) == pytest.approx(15 * 5.0, abs=2) and max(fs.skew_s for fs in sets) < 0.05
    assert set(cams.lagging_per_port.values()) == {0}


@pytest.mark.parametrize("seed", range(4))
def test_faster_cameras_pick_the_frame_nearest_the_pacing_camera(seed):
    """Ba camera 24 khung/s (khoảng cách thật n03) + cổng 4 khỏe 15 khung/s định nhịp, max_skew 60 ms. Mốc lấy trong
    camera định nhịp: không bộ nào bị bỏ vì lệch, lệch ≤ 50 ms. Mốc theo mọi camera (như khi các camera cùng nhịp):
    1–25 bộ bị bỏ / 9 s ở 6 hạt, lệch tới 61–72 ms (mô phỏng 24/09)."""
    rnd = random.Random(seed)
    phases = {p: rnd.uniform(0, 0.066) for p in PORTS4}
    gaps = {1: GAPS_24FPS_MS[2], 2: GAPS_24FPS_MS[3], 3: GAPS_24FPS_MS[4], 4: [1000 / 15]}
    events = replay_events(gaps, phases, 12.0, jitter=0.003, seed=seed, start={p: rnd.randrange(48) for p in PORTS4})
    now = [0.0]
    cams = manual_manager(PORTS4, now)
    sets = run_schedule(cams, now, events, 12.0, 3.0, max_skew_s=0.06)
    assert cams.sets_rejected_skew == 0 and max(fs.skew_s for fs in sets) < 0.052
    assert len(sets) == pytest.approx(15 * 9.0, abs=2) and all(len(fs.frames) == 4 for fs in sets)


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


def damaged_camera_manager(damaged_port=4, period=0.02, **damage):
    """Bốn FakeCamera 20 ms; riêng cổng `damaged_port` có khung hỏng mà nguồn BÁO (cắt/xé: nguồn loại khung nhưng lần
    tới vẫn được ghi), như cổng 1 ở 480p ngày 23/09. Ví dụ trunc_every=2, torn_every=3: chỉ lần đọc 1, 5, 7, 11… tốt,
    ≈ 1/3 số khung, khoảng cách khung tốt 80/40 ms trong khi nhịp camera vẫn 20 ms."""
    specs = [CameraSpec(port=p, index=k) for k, p in enumerate(PORTS4)]

    def open_source(spec):
        return FakeCamera(spec, period=period, **(damage if spec.port == damaged_port else {}))

    return MultiCameraManager(specs, open_source=open_source, ring=3)


def rig_rates(cams, max_wait_s):
    """Chạy Rig (AI giả) với `cams`; trả (AI bộ/s, fps khung tốt nhỏ nhất của cổng 1–3, fps khung tốt cổng 4, tổng kết)."""
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


def test_ai_keeps_the_other_cameras_rate_when_one_camera_has_damaged_frames():
    """Luồng thật: cổng 4 chỉ còn ≈ 1/3 khung tốt (nhịp vẫn 20 ms, khung hỏng được báo). Bật chờ: AI theo nhịp ba camera
    kia, cổng 4 bị bỏ ở các bộ mà khung đúng lượt của nó hỏng. Tắt: chuỗi chậm theo khung tốt của cổng 4, như trước.
    (Bản trước của test dùng camera ĐỀU 60 ms làm "camera chậm"; theo quy tắc mới đó là camera khỏe chậm hơn, được chờ —
    test ngay sau.)"""
    on_rate, fast, slow, on = rig_rates(damaged_camera_manager(trunc_every=2, torn_every=3), 0.03)
    off_rate, fast_off, slow_off, off = rig_rates(damaged_camera_manager(trunc_every=2, torn_every=3), None)
    assert slow < 0.5 * fast and slow_off < 0.5 * fast_off           # đúng là cổng 4 có ít khung tốt
    assert on_rate > 0.75 * fast, (on_rate, fast, slow)              # bật chờ: gần tốc độ ba camera kia
    assert off_rate < 1.2 * slow_off, (off_rate, fast_off, slow_off)  # tắt: bằng khung tốt của cổng 4, như trước
    assert on["sets"]["sets_partial_wait"] > 0 and on["sets"]["lagging_per_port"][4] > 0.4 * on["sets"]["sets_built"]
    assert on["sets"]["lagging_per_port"][1] <= 0.1 * on["sets"]["lagging_per_port"][4]
    assert on["ai"]["batches_partial_wait"] > 0 and on["ai"]["images"] < 4 * on["ai"]["batches"]
    assert off["sets"]["sets_partial_wait"] == 0 and off["ai"]["images"] == 4 * off["ai"]["batches"]
    assert on["policy"]["max_wait_ms"] == 30.0 and off["policy"]["max_wait_ms"] is None
    assert sum(row["sets_partial_wait_1s"] for row in on["series"]) > 0
    assert sum(row["cam_lagging_1s"][4] for row in on["series"]) > 0
    assert all(row["sets_partial_wait_1s"] == 0 for row in off["series"])
    cam4 = {c["port"]: c for c in on["cameras"]}[4]
    assert cam4["period_ms"] == pytest.approx(20.0, rel=0.25) and cam4["truncated"] > 0     # nhịp đo từ mọi lần tới


def test_ai_waits_for_a_healthy_slower_camera_instead_of_leaving_it_out():
    """Luồng thật: cổng 4 KHỎE nhưng chậm hơn (đều 60 ms, như phơi sáng dài ở chỗ tối), ba cổng kia 20 ms. Mỗi camera
    xét theo nhịp của chính nó: cổng 4 không bị bỏ, nó định nhịp AI (≈ 16,7 bộ/s, bằng khi tắt chờ), mọi lô đủ bốn
    ảnh. Quy tắc trước bỏ nó ở phần lớn số bộ để giữ nhịp 50 bộ/s của camera nhanh (test cũ ghim đúng điều đó)."""
    on_rate, fast, slow, on = rig_rates(fake_manager(ports=PORTS4, period=0.02, periods={4: 0.06}), 0.03)
    assert slow < 0.5 * fast                                          # đúng là cổng 4 chậm hơn
    assert on_rate == pytest.approx(slow, rel=0.15), (on_rate, fast, slow)
    st = on["sets"]
    assert st["lagging_per_port"][4] <= 0.05 * st["sets_built"], st      # dung sai cho luồng bị trễ khi máy bận
    assert on["ai"]["images"] >= 3.9 * on["ai"]["batches"]
    assert sum(st["frames_skipped"][p] for p in (1, 2, 3)) > st["sets_built"]   # khung dư của camera nhanh không vào bộ
    cam = {c["port"]: c for c in on["cameras"]}
    assert cam[4]["period_ms"] == pytest.approx(60.0, rel=0.15) and cam[1]["period_ms"] == pytest.approx(20.0, rel=0.25)
    assert st["wait_limit_ms"]["median"] == pytest.approx(90.0, rel=0.15)   # 1,5 × 60 ms của CHÍNH cổng 4


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


def set_loop_rates(cams, max_wait_s):
    """AI tắt: luồng nền `_set_loop` tự ghép bộ."""
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
    on_rate, fast, slow, on = set_loop_rates(damaged_camera_manager(trunc_every=2, torn_every=3), 0.03)
    off_rate, fast_off, slow_off, off = set_loop_rates(damaged_camera_manager(trunc_every=2, torn_every=3), None)
    assert on["ai"] is None and slow < 0.5 * fast                       # đúng là cổng 4 ít khung tốt, không có AI
    assert on["sets"]["sets_partial_wait"] > 0 and on["sets"]["lagging_per_port"][4] > 0
    assert on_rate > 0.75 * fast, (on_rate, fast, slow)                 # bật chờ: gần tốc độ ba camera kia
    assert off["sets"]["sets_partial_wait"] == 0 and off_rate < 1.2 * slow_off, (off_rate, slow_off)   # tắt: theo cổng 4
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
        cams = damaged_camera_manager(trunc_every=2, torn_every=3)      # cổng 4: ≈ 1/3 khung tốt, nhịp vẫn 20 ms
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
    assert data["policy"]["wait_periods_of_own"] == 1.5 and data["sets"]["wait_limit_ms"]["n"] > 0
    assert data["policy"]["wait_rule"] == "own_cadence" and data["policy"]["wait_periods_of_fastest"] == 1.5  # khóa cũ
    assert "sets_regrouped" in data["sets"] and "sets_regrouped_1s" in data["series"][0]
    out = capsys.readouterr().out
    assert "chờ camera chậm tối đa max(30.0 ms; 1.5 × chu kỳ của CHÍNH từng camera)" in out
    assert all(c["period_ms"] is not None for c in data["cameras"])   # nhịp từng camera mà quy tắc chờ đã dùng
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
    assert f"ngưỡng lớn nhất trong bộ trung vị {data['sets']['wait_limit_ms']['median']} ms" in out


def test_max_wait_flag_sets_the_rig_policy_and_zero_disables_it():
    import argparse

    p = argparse.ArgumentParser()
    bench.add_rig_args(p)
    assert bench.build_rig(p.parse_args(["--index", "0", "1", "--no-ai"])).cfg.max_wait_s == pytest.approx(0.06)
    assert bench.build_rig(p.parse_args(["--index", "0", "--no-ai", "--max-wait-ms", "25"])).cfg.max_wait_s == pytest.approx(0.025)
    rig = bench.build_rig(p.parse_args(["--index", "0", "--no-ai", "--max-wait-ms", "0"]))
    assert rig.cfg.max_wait_s is None and rig.policy()["max_wait_ms"] is None
    assert rig.policy()["wait_periods_of_fastest"] is None and rig.policy()["wait_periods_of_own"] is None
    assert rig.policy()["wait_rule"] is None
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
