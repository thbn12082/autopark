"""Màn hình scan trực tiếp từ RPLIDAR C1, hoặc phát lại một bản ghi `.npz`, với giám sát dữ liệu cũ và ghi phiên.

    python -m autopark.lidar.live_view [--port COMx] [--max-age 0.3] [--record runs/lidar_bench/<ngày>/live] [--mirror]
    python -m autopark.lidar.live_view --recording runs/lidar_bench/20260922/p07_nen_phong.npz [--speed 1]

Không có `--port` lẫn `--recording` thì mở LiDAR ở `lidar_port` của configs/thiet_bi.json (29/09/2026; lidar/port.py).

Luồng đọc chạy ở thread riêng (đọc cổng nối tiếp chặn tới 50 ms) và đẩy scan vào hàng đợi; timer Qt 20 ms lấy
ra, gọi `FreshnessMonitor.observe(now)` rồi `check(now)` trên đồng hồ phiên của nguồn, nên STALE_DATA vẫn được
phát khi driver treo hay cáp rời. Rút cáp là cách thử "mất LiDAR thì báo" trên thiết bị thật. Chỉ hiển thị và
ghi; không có liên hệ tới điều khiển.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import queue
import sys
import threading
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

from autopark.safety.freshness import FreshnessMonitor, SourcePolicy
from autopark.ui.scan_view import ScanView

from .recording import RecordingReplaySource, ScanRecorder, default_meta


class PacedReplay:
    """Replays a recording at wall-clock pace (times `speed`) with the same `read()` / `now()` as the driver."""

    def __init__(self, path, *, speed: float = 1.0, source_id: str | None = None, clock=time.monotonic):
        if speed <= 0:
            raise ValueError("speed must be > 0")
        self.replay = RecordingReplaySource(path, source_id=source_id)
        self.source_id = self.replay.source_id
        self.speed, self.clock = speed, clock
        self.t0 = clock()
        self.last_quality = None
        self.last_revolution = None

    def now(self) -> float:
        return max(0.0, (self.clock() - self.t0) * self.speed)

    def read(self):
        scan = self.replay.read()
        if scan is None:
            raise ScanStreamEnded("hết bản ghi")
        while self.now() < scan.stamp.t:
            time.sleep(min(0.01, (scan.stamp.t - self.now()) / self.speed))
        return scan

    def stats(self) -> dict:
        return {"replayed": self.replay.index}

    def flush(self) -> None:
        """Skip the scans the replay would have delivered while the caller was busy (mirrors the driver)."""
        while self.replay.index < len(self.replay) and self.replay.recording.t[self.replay.index] - self.replay.recording.t[0] < self.now():
            self.replay.index += 1

    def close(self) -> None:
        pass


class ScanStreamEnded(RuntimeError):
    """A replay reached its end (a live driver never raises this)."""


class ScanReader(threading.Thread):
    """Pulls scans from a blocking source into a queue; errors are queued too so the window can show them."""

    def __init__(self, source, out: queue.Queue):
        super().__init__(daemon=True)
        self.source, self.out = source, out
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                scan = self.source.read()
            except Exception as exc:  # noqa: BLE001 - every failure must reach the screen, not kill the thread silently
                self.out.put(exc)
                if isinstance(exc, ScanStreamEnded):
                    return
                time.sleep(0.2)
                continue
            revolution = getattr(self.source, "last_revolution", None)
            self.out.put((scan, getattr(self.source, "last_quality", None),
                          None if revolution is None else revolution.t_first))


class LiveWindow(QMainWindow):
    def __init__(self, source, *, max_age: float = 0.3, expected_period: float = 0.1, recorder: ScanRecorder | None = None,
                 max_range: float = 6.0, start_thread: bool = True):
        super().__init__()
        self.source = source
        self.source_id = source.source_id
        self.setWindowTitle(f"Scan trực tiếp — {self.source_id}")
        self.monitor = FreshnessMonitor({self.source_id: SourcePolicy(max_age_s=max_age, expected_period_s=expected_period)})
        self.recorder = recorder
        self.queue: queue.Queue = queue.Queue()
        self.view = ScanView(max_range=max_range)
        self.status = QLabel()
        self.last_error: str | None = None
        self.ended = False
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self.view)
        layout.addWidget(self.status)
        self.setCentralWidget(root)
        self.reader = ScanReader(source, self.queue)
        if start_thread:
            self.reader.start()
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def now(self) -> float:
        return self.source.now()

    def tick(self) -> None:
        now = self.now()
        events = []
        while True:
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, Exception):
                self.last_error = f"{type(item).__name__}: {item}"
                if isinstance(item, ScanStreamEnded):
                    self.ended = True
                continue
            scan, quality, t_first = item
            rejected = self.monitor.observe(scan.stamp, now=now)
            events += rejected
            if not rejected:
                self.view.set_scan(scan, stale=False)
                if self.recorder is not None:
                    self.recorder.add(scan, quality=quality, t_first=t_first)
        events += self.monitor.check(now)
        stale = any(e.code in ("STALE_DATA", "NO_DATA") for e in events)
        if stale and self.view.scan is not None:
            self.view.set_scan(self.view.scan, self.view.detections, stale=True)
        state = self.monitor.status(now)[self.source_id]
        text = (f"t={now:7.2f}s  vòng={state['count']}  từ chối={state['rejected']}  mất={state['drops']}  "
                f"tuổi={state['age_s'] if state['age_s'] is None else round(state['age_s'], 3)}s  "
                + ("; ".join(e.code for e in events) or "OK"))
        if self.last_error:
            text += f"  — {self.last_error}"
        if self.ended:
            text += "  — hết bản ghi"
        self.status.setText(text)

    def closeEvent(self, event):
        self.timer.stop()
        self.reader.stop_event.set()
        try:
            if self.recorder is not None:
                self.recorder.close({"driver_stats": self.source.stats()})
        finally:
            self.source.close()
        super().closeEvent(event)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--port", help="COM port of the RPLIDAR C1 (or auto); default: lidar_port in configs/thiet_bi.json")
    where.add_argument("--recording", type=Path, help="replay a .npz written by autopark.lidar.recording")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--max-age", type=float, default=0.3, help="STALE_DATA after this many seconds without a scan")
    parser.add_argument("--expected-period", type=float, default=0.1)
    parser.add_argument("--max-range", type=float, default=6.0)
    parser.add_argument("--mirror", action="store_true")
    parser.add_argument("--record", type=Path, default=None, help="file stem to record the live session into")
    args = parser.parse_args(argv)
    recorder = None
    if args.recording is None:
        from .port import LidarPortError, lidar_port
        from .rplidar_c1 import RplidarC1Source

        try:
            port = lidar_port(args.port)
        except LidarPortError as exc:
            parser.error(str(exc))
        source = RplidarC1Source.open(port, mirror=args.mirror)
        source.start()
        if args.record:
            described = source.describe()
            described.pop("source_id", None)
            recorder = ScanRecorder(args.record, default_meta(source.source_id, port=port, **described))
    else:
        source = PacedReplay(args.recording, speed=args.speed)
    app = QApplication.instance() or QApplication(sys.argv)
    window = LiveWindow(source, max_age=args.max_age, expected_period=args.expected_period, recorder=recorder,
                        max_range=args.max_range)
    window.resize(720, 760)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
