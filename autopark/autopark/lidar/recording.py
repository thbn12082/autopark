"""Ghi và phát lại phiên quét LiDAR theo hợp đồng `LidarScan`, không phụ thuộc hãng cảm biến.

Một phiên = `<tên>.npz` (mảng thời gian, số tia mỗi vòng, góc/khoảng cách/chất lượng nối phẳng) + `<tên>.json`
(meta: nguồn, thiết bị, cổng, cờ mirror, giờ UTC, máy, commit git, thống kê driver và tóm tắt). Số tia mỗi
vòng được giữ nguyên như đo, không nội suy về lưới cố định; NaN là "không có phản hồi". `RecordingReplaySource`
phát lại cùng `LidarScan` để màn hình scan, giám sát dữ liệu cũ và bản đồ chạy y hệt trên dữ liệu ghi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import platform
import subprocess
from typing import Iterator

import numpy as np

from autopark.domain.sensors import LidarScan, SourceStamp
from autopark.perception.paths import PROJECT, atomic_write_json, utc_now

RECORDING_VERSION = 1


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT, capture_output=True, text=True,
                              timeout=5, check=False).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def default_meta(source_id: str, **extra) -> dict:
    return {"recording_version": RECORDING_VERSION, "source_id": source_id, "started_utc": utc_now(),
            "host": platform.node(), "python": platform.python_version(), "git_commit": git_commit(), **extra}


class ScanRecorder:
    """Collects scans in memory and writes them once on `close()` (a bench session is seconds, not hours)."""

    def __init__(self, path, meta: dict | None = None):
        self.path = Path(path).with_suffix(".npz")
        self.meta = dict(meta or {})
        self.meta.setdefault("recording_version", RECORDING_VERSION)
        self._t: list[float] = []
        self._t_first: list[float] = []
        self._n: list[int] = []
        self._angles: list[np.ndarray] = []
        self._ranges: list[np.ndarray] = []
        self._quality: list[np.ndarray] = []
        self.closed = False

    def __len__(self) -> int:
        return len(self._t)

    def add(self, scan: LidarScan, quality=None, t_first: float | None = None) -> None:
        if self.closed:
            raise RuntimeError("recorder already closed")
        n = len(scan.angles_rad)
        if self._t and scan.stamp.t < self._t[-1]:
            raise ValueError(f"scan stamp {scan.stamp.t} is earlier than the previous {self._t[-1]}")
        q = np.zeros(n, np.uint8) if quality is None else np.asarray(quality, dtype=np.uint8)
        if q.shape != (n,):
            raise ValueError("quality must have one value per beam")
        self._t.append(float(scan.stamp.t))
        self._t_first.append(float(scan.stamp.t if t_first is None else t_first))
        self._n.append(n)
        self._angles.append(np.asarray(scan.angles_rad, dtype=np.float32))
        self._ranges.append(np.asarray(scan.ranges_m, dtype=np.float32))
        self._quality.append(q)

    def arrays(self) -> dict:
        return {"t": np.array(self._t, np.float64), "t_first": np.array(self._t_first, np.float64),
                "n_beams": np.array(self._n, np.int32),
                "angles": np.concatenate(self._angles) if self._angles else np.zeros(0, np.float32),
                "ranges": np.concatenate(self._ranges) if self._ranges else np.zeros(0, np.float32),
                "quality": np.concatenate(self._quality) if self._quality else np.zeros(0, np.uint8)}

    def close(self, extra_meta: dict | None = None) -> Path:
        if self.closed:
            return self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        arrays = self.arrays()
        np.savez_compressed(self.path, **arrays)
        self.meta.update(extra_meta or {})
        self.meta["scans"] = len(self._t)
        self.meta["summary"] = summarize_arrays(arrays)
        atomic_write_json(self.path.with_suffix(".json"), self.meta)
        self.closed = True
        return self.path

    def __enter__(self) -> "ScanRecorder":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


@dataclass
class Recording:
    path: Path
    t: np.ndarray
    t_first: np.ndarray
    n_beams: np.ndarray
    angles: np.ndarray
    ranges: np.ndarray
    quality: np.ndarray
    meta: dict = field(default_factory=dict)
    offsets: np.ndarray = field(init=False)

    def __post_init__(self):
        self.offsets = np.concatenate([[0], np.cumsum(self.n_beams)])
        if self.offsets[-1] != len(self.angles) or len(self.ranges) != len(self.angles) or len(self.quality) != len(self.angles):
            raise ValueError(f"{self.path.name}: beam arrays do not match n_beams")
        if (np.diff(self.t) < 0).any():
            raise ValueError(f"{self.path.name}: timestamps decrease")

    def __len__(self) -> int:
        return len(self.t)

    def beams(self, index: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        a, b = self.offsets[index], self.offsets[index + 1]
        return self.angles[a:b], self.ranges[a:b], self.quality[a:b]

    def scan(self, index: int, *, source_id: str | None = None, time_offset: float = 0.0) -> LidarScan:
        angles, ranges, _ = self.beams(index)
        stamp = SourceStamp(source_id or self.meta.get("source_id", "lidar_replay"),
                            float(self.t[index] - self.t[0] + time_offset), True, "lidar")
        return LidarScan(stamp, tuple(float(a) for a in angles),
                         tuple(float(r) if math.isfinite(r) else math.nan for r in ranges))


def read_recording(path) -> Recording:
    path = Path(path).with_suffix(".npz")
    with np.load(path) as data:
        arrays = {key: data[key] for key in ("t", "t_first", "n_beams", "angles", "ranges", "quality")}
    meta_path = path.with_suffix(".json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return Recording(path, **arrays, meta=meta)


class RecordingReplaySource:
    """Same interface as the DROW replay: `read()` returns scans in order, `None` when the recording is over."""

    def __init__(self, path, *, source_id: str | None = None, t0: float = 0.0):
        self.recording = read_recording(path)
        self.source_id = source_id or self.recording.meta.get("source_id", "lidar_replay")
        self.t0 = t0
        self.index = 0

    def __len__(self) -> int:
        return len(self.recording)

    def read(self) -> LidarScan | None:
        if self.index >= len(self.recording):
            return None
        scan = self.recording.scan(self.index, source_id=self.source_id, time_offset=self.t0)
        self.index += 1
        return scan

    def __iter__(self) -> Iterator[LidarScan]:
        while (scan := self.read()) is not None:
            yield scan

    def summary(self) -> dict:
        return {"file": self.recording.path.name, **summarize(self.recording)}


def summarize_arrays(arrays: dict) -> dict:
    t, n = np.asarray(arrays["t"], np.float64), np.asarray(arrays["n_beams"])
    ranges = np.asarray(arrays["ranges"], np.float64)
    dt = np.diff(t)
    finite = np.isfinite(ranges)
    duration = float(t[-1] - t[0]) if len(t) > 1 else 0.0
    return {"scans": int(len(t)), "duration_s": duration,
            "rate_hz": float((len(t) - 1) / duration) if duration > 0 else None,
            "median_period_s": float(np.median(dt)) if len(dt) else None,
            "max_gap_s": float(dt.max()) if len(dt) else None,
            "beams_median": float(np.median(n)) if len(n) else None,
            "beams_min": int(n.min()) if len(n) else None, "beams_max": int(n.max()) if len(n) else None,
            "no_return_fraction": float((~finite).mean()) if len(ranges) else None,
            "range_min_m": float(ranges[finite].min()) if finite.any() else None,
            "range_max_m": float(ranges[finite].max()) if finite.any() else None}


def summarize(recording: Recording) -> dict:
    return summarize_arrays({"t": recording.t, "n_beams": recording.n_beams, "ranges": recording.ranges})
