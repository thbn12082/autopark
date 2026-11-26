"""Phía video của dấu đồng bộ T14 (`autopark.evaluation.sync_video`, thêm 02/10/2026): khởi đầu nháy = khung đầu có
≥ nửa ô sáng, lọc lần nháy quá ngắn/dài/sát nhau, ghép với dòng SYNC_MARK theo hai đồng hồ, và `overhead_ref track`
ghi cặp `mark` để T5 (`score_run`) đổi đồng hồ mà không cần --sync. Ảnh tổng hợp; không mở camera hay cổng nào."""
import csv
import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from autopark.domain.types import Pose  # noqa: E402
from autopark.evaluation import overhead_ref as R  # noqa: E402
from autopark.evaluation import score_run  # noqa: E402
from autopark.evaluation.overhead_synth import camera_stamps  # noqa: E402
from autopark.evaluation.reference_pose import read_reference  # noqa: E402
from autopark.evaluation.sync_marks import SYNC_FIELDS  # noqa: E402
from autopark.evaluation.sync_video import FlashOnset, detect_flashes, match_flashes  # noqa: E402
from autopark.lidar import recording as lidar_recording  # noqa: E402
from autopark.video.overhead_record import OverheadRecorder  # noqa: E402
from tests.overhead_set import floor_fit_path, small_set  # noqa: E402

ROI = (10, 10, 40, 30)


@pytest.fixture(autouse=True)
def no_git(monkeypatch):
    monkeypatch.setattr(lidar_recording, "git_commit", lambda: "test")


def screen(lit: float, rng, size=(80, 60)) -> np.ndarray:
    """Ảnh xám: ô màn hình tối, `lit` phần trên của ô sáng (phần dưới chưa kịp sáng: màn trập cuộn / phơi sáng)."""
    img = np.full((size[1], size[0]), 40.0) + rng.normal(0, 2.0, (size[1], size[0]))
    x, y, w, h = ROI
    img[y:y + int(round(h * lit)), x:x + w] = 235.0
    return np.clip(img, 0, 255).astype(np.uint8)


def test_onset_is_the_first_frame_with_half_the_square_bright():
    rng = np.random.default_rng(0)
    stamps = camera_stamps(60, 100.0)
    lit = [0.0] * 60
    lit[20], lit[21], lit[33] = 0.3, 0.7, 0.4                       # sáng dần, rồi tắt dần
    for k in range(22, 33):
        lit[k] = 1.0
    onsets = detect_flashes([(k, t, screen(lit[k], rng)) for k, t in enumerate(stamps)], ROI)
    assert len(onsets) == 1
    on = onsets[0]
    assert on.index == 21 and on.t == stamps[21] and on.peak == 1.0
    assert on.duration_s == pytest.approx(stamps[33] - stamps[21])


def test_flashes_shorter_longer_or_too_close_are_ignored():
    rng = np.random.default_rng(1)
    lit = np.zeros(200)
    lit[15:18] = 1.0          # 0,1 s: quá ngắn
    lit[40:55] = 1.0          # 0,5 s: nhận
    lit[62:75] = 1.0          # bắt đầu 0,73 s sau lần trước: quá sát
    lit[100:152] = 1.0        # 1,7 s: quá dài
    lit[170:185] = 1.0        # nhận
    samples = [(k, k / 30.0, screen(lit[k], rng)) for k in range(200)]
    assert [o.index for o in detect_flashes(samples, ROI)] == [40, 170]


def _marks(*pairs):
    return [{"n": n, "kind": "SYNC_MARK", "t_perf": t} for n, t in pairs] + [{"n": "", "kind": "CLOCK", "t_perf": 1.0}]


def test_matching_video_clock_by_interval_pattern_and_perf_clock_by_latency_window():
    marks = _marks((1, 5000.0), (2, 5003.7), (3, 5009.1))
    onsets = [FlashOnset(k, t, 0.5, 1.0) for k, t in ((360, 12.08), (471, 15.79), (632, 21.17))]
    pairs = match_flashes(onsets, marks, clock="video")
    assert [(p.t_ref, int(p.value), p.side) for p in pairs] == [(12.08, 1, "mark"), (15.79, 2, "mark"),
                                                                 (21.17, 3, "mark")]
    with pytest.raises(R.OverheadError, match="--first-mark"):
        match_flashes(onsets[1:2], marks, clock="video")
    assert int(match_flashes(onsets[1:2], marks, clock="video", first_mark=2)[0].value) == 2
    periodic = _marks((1, 5000.0), (2, 5001.0), (3, 5002.0))
    with pytest.raises(R.OverheadError, match="nhiều độ lệch"):
        match_flashes([FlashOnset(0, 10.0, 0.5, 1.0), FlashOnset(30, 11.0, 0.5, 1.0)], periodic, clock="video")
    perf = [FlashOnset(0, 5000.08, 0.5, 1.0), FlashOnset(1, 5003.79, 0.5, 1.0), FlashOnset(2, 5009.7, 0.5, 1.0)]
    pairs = match_flashes(perf, marks, clock="perf_counter")
    assert [int(p.value) for p in pairs] == [1, 2]                  # dấu 3 sớm 0,6 s: ngoài cửa sổ 0,5 s
    with pytest.raises(R.OverheadError, match="nhiều dấu"):
        match_flashes(perf, marks + _marks((4, 5003.5)), clock="perf_counter")


def test_track_with_flash_roi_writes_mark_pairs_and_one_frame_sync_error(tmp_path):
    from tests.test_score_run import vio_log, write_csv

    info = small_set()
    stamps = camera_stamps(50, 40000.0)
    rec = OverheadRecorder(tmp_path, "nhay", synthetic=True)
    rec.start(960, 540, {"name": "tren_cao_tong_hop"})
    rng = np.random.default_rng(2)
    square = (20, 440, 80, 60)                                       # màn hình laptop trong ảnh, ô nháy T14
    for k, t in enumerate(stamps):
        lit = 1.0 if 6 <= k <= 18 or 32 <= k <= 44 else 0.3 if k in (5, 31) else 0.0
        rec.add(info["renderer"].frame(Pose(1.2, 0.7, 0.3), info["plate"], rng=rng, flash=(*square, lit)), t)
    rec.stop()
    marks = tmp_path / "nhay_sync_marks.csv"
    rows = [{"n": "", "kind": "CLOCK", "t_perf": 39999.0, "state": "RUNNING", "t_session": 0.016,
             "trigger": "state_change", "source": "ui.app", "note": "READY→RUNNING"},
            {"n": 1, "kind": "SYNC_MARK", "t_perf": round(stamps[6] - 0.08, 6), "source": "ui.app", "trigger": "key_f8"},
            {"n": 2, "kind": "SYNC_MARK", "t_perf": round(stamps[32] - 0.08, 6), "source": "ui.app",
             "trigger": "key_f8"},
            {"n": "", "kind": "CLOCK", "t_perf": 40004.584, "state": "STOPPED", "t_session": 5.6,
             "trigger": "state_change", "source": "ui.app", "note": "RUNNING→STOPPED"}]
    write_csv(marks, SYNC_FIELDS, rows)
    out = tmp_path / "tu_the_tham_chieu.csv"
    assert R.main(["track", "--video", str(tmp_path / "nhay.avi"), "--floor", str(floor_fit_path()), "--markers",
                   info["markers"], "--flash-roi", "25,445,70,50", "--sync-marks", str(marks), "--out",
                   str(out)]) == 0
    meta = read_reference(out).meta
    assert [(p.t_ref, int(p.value), p.side) for p in meta.sync] == [(stamps[6], 1, "mark"), (stamps[32], 2, "mark")]
    assert meta.sync_error_s == pytest.approx(0.048, abs=1e-6)       # ± một khung: p95 khoảng cách khung
    assert [o["offset_s"] for o in meta.source["flash_offsets"]] == pytest.approx([0.08, 0.08], abs=1e-6)
    with open(out.with_name("tu_the_tham_chieu.chi_tiet.csv"), encoding="utf-8") as f:
        fractions = [float(r["flash_fraction"]) for r in csv.DictReader(f)]
    assert fractions[5] < 0.5 <= fractions[6] and fractions[20] < 0.1
    # T5 đổi đồng hồ nhờ cặp trong tệp mô tả (không --sync), qua dòng CLOCK của tệp dấu (bo mô phỏng, mức MP)
    log = vio_log(tmp_path, name="lan_vehicle_io", t_end=5.6, evidence="simulation_only", port=None,
                  pose_source="sim_truth_pose", io_simulated=True, t13=False)
    args = score_run.build_parser().parse_args(["--scenario", "DI-1", "--attempt", "1", "--level", "MP", "--log",
                                                str(log), "--reference", str(out), "--sync-marks", str(marks),
                                                "--dry-run"])
    report = score_run.score(args)
    cmap = report.detail["clock_map"]
    assert cmap is not None and "sync của tệp mô tả" in cmap["source"] and len(report.detail["sync_pairs"]) == 2
    # cặp nháy coi khung đầu sáng là lúc dấu: độ trễ dấu → khung (0,08 s ở đây) nằm trong phép đổi, chỉ báo ở
    # flash_offsets (độ trễ hiển thị L CHƯA ĐO, KICH_BAN 2.5)
    assert cmap["offset"] == pytest.approx(-(39999.0 - 0.016) - 0.08, abs=1e-3)
    assert "R7" in report.row["phuong_phap_do"]
    assert json.loads(Path(out).with_suffix(".json").read_text(encoding="utf-8"))["source"]["synthetic"] is True
