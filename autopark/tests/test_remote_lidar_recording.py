"""Nút Ghi LiDAR của cửa sổ quan sát Pi: luồng nhận ghi mọi vòng C1 theo định dạng lidar/recording.py."""
from __future__ import annotations

import io
import json
import math
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.lidar.recording import read_lidar_any  # noqa: E402
from autopark.rig.remote_view_link import _MAGIC, RemoteSensorLink  # noqa: E402


def packet(kind: str, payload: dict, **header) -> bytes:
    body = json.dumps(payload).encode()
    return json.dumps({"kind": kind, "nbytes": len(body), **header}).encode() + b"\n" + body


def lidar_stream(n: int) -> io.BytesIO:
    parts = [_MAGIC, packet("start", {})]
    for i in range(1, n + 1):
        t_ns = 5_000_000_000 + i * 100_000_000            # đồng hồ Pi, 10 Hz
        parts.append(packet("lidar", {"angles_rad": [0.0, 1.0, 2.0], "ranges_m": [1.0 + i, None, 0.5]},
                            seq=i, t_ns=t_ns, tx_ns=t_ns + 1000))
    return io.BytesIO(b"".join(parts))


def test_link_records_every_scan_with_pi_clock(tmp_path):
    link = RemoteSensorLink("10.0.0.2", camera_count=1)
    path = link.start_lidar_recording(tmp_path / "c1_thu", {"note": "chỗ đặt 1"})
    with pytest.raises(ValueError, match="đóng trước"):
        link._read(lidar_stream(12))                       # luồng thử không có gói kết thúc
    assert link.lidar_recording_count() == 12
    saved, scans = link.stop_lidar_recording()
    assert saved == path and scans == 12
    assert link.stop_lidar_recording() is None

    rec = read_lidar_any(saved)
    assert len(rec) == 12
    assert np.allclose(rec.t, 5.0 + 0.1 * np.arange(1, 13))
    angles, ranges, _ = rec.beams(0)
    assert np.allclose(angles, [0, 1, 2]) and ranges[0] == pytest.approx(2.0) and math.isnan(ranges[1])
    assert rec.meta["mirror"] is False and rec.meta["note"] == "chỗ đặt 1" and rec.meta["scans"] == 12


def test_close_still_writes_open_recording(tmp_path):
    link = RemoteSensorLink("10.0.0.2", camera_count=1)
    path = link.start_lidar_recording(tmp_path / "c1_dong")
    with pytest.raises(ValueError):
        link._read(lidar_stream(3))
    link.close()
    assert len(read_lidar_any(path)) == 3


def test_window_button_records_and_stops(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from autopark.ui.remote_sensor_view import RemoteSensorWindow

    QApplication.instance() or QApplication([])

    class FakeLink:
        def __init__(self, host, *, duration_s, camera_count):
            self.state = SimpleNamespace(status="stopped", detail="", cameras=(None,) * camera_count,
                                         scan=None, scan_seq=None, scan_at=None)
            self.recording, self.count, self.closed = None, 0, False

        def start(self):
            self.state.status = "live"

        def snapshot(self):
            return self.state

        def close(self):
            self.closed = True

        def start_lidar_recording(self, path, meta=None):
            self.recording = path.with_suffix(".npz")
            return self.recording

        def stop_lidar_recording(self):
            done, self.recording = self.recording, None
            return None if done is None else (done, self.count)

        def lidar_recording_count(self):
            return None if self.recording is None else self.count

    now = [100.0]
    window = RemoteSensorWindow("10.0.0.2", camera_count=1, link_factory=FakeLink, clock=lambda: now[0],
                                lidar_dir=tmp_path)
    window.timer.stop()
    try:
        window.connect_link()
        link = window.link
        window.refresh()
        assert not window.lidar_record_button.isEnabled()          # chưa có bản quét trực tiếp
        link.state.scan = LidarScan(SourceStamp("C1", 100.0), (0.0,), (1.0,))
        link.state.scan_seq, link.state.scan_at = 1, 100.0
        window.refresh()
        assert window.lidar_record_button.isEnabled()
        window.lidar_record_button.setChecked(True)
        assert link.recording is not None and link.recording.parent == tmp_path
        link.count = 37
        window.refresh()
        assert "37 vòng" in window.lidar_record_status.text()
        window.lidar_record_button.setChecked(False)
        assert link.recording is None and "Đã ghi 37 vòng" in window.lidar_record_status.text()

        window.lidar_record_button.setChecked(True)                 # mất kết nối khi đang ghi: tự ghi tệp
        link.state.status = "error"
        window.refresh()
        assert link.recording is None and not window.lidar_record_button.isChecked()
    finally:
        window.close()
