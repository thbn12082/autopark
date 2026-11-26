"""Phát lại một recording DROW v2 lên màn hình scan với giám sát dữ liệu cũ.

    python -m autopark.lidar.viewer datasets/drow/DROWv2-data/val/run_2015-11-25-10-34-20-a.bag.csv --labels wp

Tốc độ phát theo chu kỳ ghi trong file (nhân `--speed`). Nhấn Space để tạm dừng: bộ giám sát sẽ báo dữ liệu
cũ sau `--max-age` giây và tiêu đề đổi màu — đây là cách thử logic "dữ liệu cũ thì không dùng" mà không cần
cảm biến. Chỉ hiển thị; không có liên hệ tới điều khiển.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

from autopark.lidar.drow import DrowReplaySource, read_drow_labels
from autopark.safety.freshness import FreshnessMonitor, SourcePolicy
from autopark.ui.scan_view import ScanView


class ReplayWindow(QMainWindow):
    def __init__(self, csv_path: Path, labels: dict | None, speed: float, max_age: float, mirror: bool = False):
        super().__init__()
        if not speed > 0:
            raise ValueError("speed must be > 0")
        self.setWindowTitle(f"Scan replay — {csv_path.name}")
        self.source = DrowReplaySource(csv_path, source_id="lidar_replay", mirror=mirror)
        self.labels = labels or {}
        self.monitor = FreshnessMonitor({"lidar_replay": SourcePolicy(max_age_s=max_age, expected_period_s=0.1)})
        self.speed = speed
        self.clock = 0.0                      # đồng hồ phiên (giây), tiến theo timer kể cả khi tạm dừng
        self.pause_offset = 0.0               # thời gian đã tạm dừng: cộng vào stamp phát lại để dòng thời gian liền mạch
        self.paused = False
        self.next_scan = self.source.read()
        self.view = ScanView(max_range=10.0)
        self.status = QLabel()
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self.view)
        layout.addWidget(self.status)
        self.setCentralWidget(root)
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def keyPressEvent(self, event):
        if event.text() == " ":
            self.paused = not self.paused
        super().keyPressEvent(event)

    def tick(self) -> None:
        step = 0.02 * self.speed
        self.clock += step
        if self.paused:
            self.pause_offset += step         # scans are held, not batched: they resume where they stopped
        events = []
        while not self.paused and self.next_scan is not None and self.next_scan.stamp.t + self.pause_offset <= self.clock:
            scan = replace(self.next_scan, stamp=replace(self.next_scan.stamp, t=self.next_scan.stamp.t + self.pause_offset))
            rejected = self.monitor.observe(scan.stamp, now=self.clock)
            events += rejected
            if not rejected:
                seq = int(self.source.recording.seq[self.source.index - 1])
                self.view.set_scan(scan, self.labels.get(seq), stale=False)
            self.next_scan = self.source.read()
        events += self.monitor.check(self.clock)
        stale = any(e.code in ("STALE_DATA", "NO_DATA") for e in events)
        if stale and self.view.scan is not None:
            self.view.set_scan(self.view.scan, self.view.detections, stale=True)
        state = self.monitor.status(self.clock)["lidar_replay"]
        text = f"t={self.clock:6.2f}s  scans={state['count']}  drops={state['drops']}  " \
               f"{'TẠM DỪNG' if self.paused else 'đang phát'}  " + ("; ".join(e.code for e in events) or "OK")
        self.status.setText(text)
        if self.next_scan is None and not self.paused:
            self.status.setText(text + "  — hết recording")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("csv", type=Path)
    parser.add_argument("--labels", choices=("wp", "wc", "wa"), default=None)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--max-age", type=float, default=0.3)
    parser.add_argument("--mirror", action="store_true", help="đảo chiều góc (scan và nhãn) khi đối chiếu thiết bị")
    args = parser.parse_args(argv)
    labels = read_drow_labels(args.csv.with_suffix("." + args.labels), mirror=args.mirror) if args.labels else None
    app = QApplication.instance() or QApplication(sys.argv)
    window = ReplayWindow(args.csv, labels, args.speed, args.max_age, mirror=args.mirror)
    window.resize(720, 760)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
