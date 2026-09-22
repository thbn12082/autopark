"""Màn hình scan: vẽ được offscreen, phát lại recording DROW và báo dữ liệu cũ khi tạm dừng."""
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.lidar.drow import N_BEAMS, drow_angles  # noqa: E402
from autopark.lidar.viewer import ReplayWindow  # noqa: E402
from autopark.ui.scan_view import ScanView  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_scan_view_renders_scan_and_stale_state(qapp):
    view = ScanView(max_range=5.0)
    view.resize(320, 320)
    image = view.grab().toImage()
    assert image.width() == 320
    scan = LidarScan(SourceStamp("lidar", 1.0), tuple(drow_angles()), tuple([2.0] * (N_BEAMS - 5) + [math.nan] * 5))
    view.set_scan(scan, detections=[(2.0, 0.0)])
    lit = view.grab().toImage()
    assert lit.pixelColor(160, 160).name() == "#8cf0d6"          # sensor marker drawn at the centre
    scale = (320 / 2 - 12) / 5.0
    ahead = lit.pixelColor(160, int(round(160 - 2.0 * scale)))   # a 2 m return straight ahead is drawn above the centre
    assert ahead.name() == "#ffd166"
    view.set_scan(scan, stale=True)
    stale = view.grab().toImage()
    assert stale.pixelColor(160, int(round(160 - 2.0 * scale))).name() == "#8a6d3b"   # points dimmed when stale


def write_recording(path, scans=6):
    lines = []
    for i in range(scans):
        lines.append(",".join([str(500 + i), f"{0.1 * i:.3f}", *[f"{1.5 + 0.001 * j:.3f}" for j in range(N_BEAMS)]]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.with_suffix(".wp").write_text("501,[[1.5, 0.0]]\n", encoding="utf-8")


def test_replay_window_advances_and_flags_stale_data_when_paused(qapp, tmp_path):
    csv = tmp_path / "run.csv"
    write_recording(csv)
    from autopark.lidar.drow import read_drow_labels
    window = ReplayWindow(csv, read_drow_labels(csv.with_suffix(".wp")), speed=1.0, max_age=0.3)
    window.timer.stop()                                          # drive the clock by hand
    for _ in range(8):                                           # 0.16 s: scans at t = 0 and 0.1 shown
        window.tick()
    assert window.monitor.status(window.clock)["lidar_replay"]["count"] == 2
    assert window.view.scan is not None and not window.view.stale
    assert window.view.detections == [(1.5, 0.0)]                # label of seq 501 shown with its scan
    for _ in range(4):                                           # 0.24 s: third scan, no label
        window.tick()
    assert window.monitor.status(window.clock)["lidar_replay"]["count"] == 3 and window.view.detections == []
    window.paused = True
    for _ in range(25):                                          # +0.5 s without new scans
        window.tick()
    assert window.view.stale and "STALE_DATA" in window.status.text()
    assert window.monitor.status(window.clock)["lidar_replay"]["count"] == 3
    window.paused = False
    window.tick()                                                # resume: scans continue one by one, not in a burst
    assert window.monitor.status(window.clock)["lidar_replay"]["count"] <= 4
    for _ in range(30):
        window.tick()
    status = window.monitor.status(window.clock)["lidar_replay"]
    assert status["count"] == 6 and status["rejected"] == 0 and "hết recording" in window.status.text()
    assert window.view.scan.stamp.t == pytest.approx(0.5 + window.pause_offset)   # last scan re-stamped after the pause
