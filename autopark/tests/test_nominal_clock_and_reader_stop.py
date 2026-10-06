"""Các sửa nhỏ của lead sau đợt sửa lỗi đợt 2 (02/10/2026): không mở thiết bị nào."""
import queue
import threading

import pytest

from autopark.evaluation import score_run
from autopark.evaluation.reference_pose import ReferenceAccuracy, ReferenceMeta, ReferenceTrack, SyncPair
from autopark.lidar.live_view import ScanReader


def _track(clock: str, notes: str = "", allow=()) -> ReferenceTrack:
    meta = ReferenceMeta("R1", clock, ReferenceAccuracy(0.01, 1.0, "giả"), notes=notes,
                         source={"allow": list(allow)})
    return ReferenceTrack([], meta)


@pytest.mark.parametrize("notes, allow", [
    (f"{score_run.NOMINAL_VIDEO_NOTE} (30 khung/s, tệp AVI không có thời điểm từng khung)", ()),
    ("", ("nominal_fps",)),
])
def test_a_nominal_fps_video_clock_needs_two_sync_pairs(notes, allow):
    """Đồng hồ video theo số khung/s danh định: một cặp đồng bộ chỉ cho độ lệch (hệ số 1), nên sai tốc độ của số khung/s
    danh định đổi im lặng sang t_session; cần ≥ 2 cặp để _fit_pairs kiểm hệ số (lệch ≤ 1 %)."""
    track = _track("video", notes, allow)
    with pytest.raises(score_run.ScoreError, match="cần ≥ 2 cặp đồng bộ"):
        score_run.clock_map(track, [SyncPair(1.0, 5.0)], log=None, perf=None, marks=None, time_error=0.01)
    cmap, err, pairs, _ = score_run.clock_map(track, [SyncPair(1.0, 5.0), SyncPair(11.0, 15.0)], log=None,
                                              perf=None, marks=None, time_error=0.01)
    assert cmap.scale == pytest.approx(1.0) and len(pairs) == 2
    with pytest.raises(score_run.ScoreError, match="lệch 1 quá 1 %"):         # 30 khung/s ghi cho camera chạy ≈ 25,5
        score_run.clock_map(track, [SyncPair(1.0, 5.0), SyncPair(11.0, 16.8)], log=None, perf=None, marks=None,
                            time_error=0.01)


def test_a_real_video_clock_still_accepts_one_pair():
    track = _track("video", "đồng hồ video (stamp của tệp)")
    cmap, _, pairs, _ = score_run.clock_map(track, [SyncPair(1.0, 5.0)], log=None, perf=None, marks=None,
                                            time_error=0.01)
    assert cmap.scale == 1.0 and cmap.offset == pytest.approx(4.0) and len(pairs) == 1


class _BlockingSource:
    """Nguồn giả: read() chờ tới khi test cho phép, rồi trả một vòng; trong lúc chờ, test bảo luồng dừng."""

    def __init__(self):
        self.release = threading.Event()
        self.reads = 0

    def read(self):
        self.release.wait(5.0)
        self.reads += 1
        from autopark.domain.sensors import LidarScan, SourceStamp
        return LidarScan(SourceStamp("gia", 0.1, True, "lidar"), (0.0, 0.1), (1.0, 1.0))

    def now(self):
        return 0.1


def test_a_stopping_reader_hands_no_scan_to_the_shared_consumers():
    """Ngăn LiDAR đổi nguồn: luồng đọc cũ đang thoát không được đưa thêm vòng nào tới người tiêu thụ chung (T2, T3)."""
    seen = []

    class Consumer:
        def on_scan(self, *args):
            seen.append(args)

    source, out = _BlockingSource(), queue.Queue()
    reader = ScanReader(source, out, [Consumer()])
    reader.start()
    reader.stop_event.set()                                       # dừng trong lúc read() còn đang chờ vòng quét
    source.release.set()
    reader.join(2.0)
    assert not reader.is_alive() and source.reads == 1
    assert seen == [] and out.empty()
