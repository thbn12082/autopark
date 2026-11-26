"""Bản đồ lưới tĩnh từ nhiều vòng quét bằng ray casting, xuất theo hợp đồng `Costmap` (bước 5, chưa phải SLAM).

    python -m autopark.lidar.occupancy --recording runs/lidar_bench/20260922/p07_nen_phong.npz --out <dir> \
        [--grid -4 4 -4 4 0.05] [--max-range 6]
    python -m autopark.lidar.occupancy --drow datasets/drow/DROWv2-data/val/<run>.bag.csv --odom \
        --start 0 --scans 300 --out <dir> [--mirror]

Mỗi tia có phản hồi: các ô từ cảm biến tới trước điểm chạm được đếm là "đi qua", ô chứa điểm chạm được đếm
là "chạm". Tia không phản hồi không đóng góp gì (NaN không phải bằng chứng trống). Tia dài hơn `max_range`
chỉ đếm "đi qua" tới `max_range`. Trạng thái ô: OCCUPIED khi số chạm ≥ `min_hits` và chiếm ≥ `occupied_ratio`
số lần quan sát; FREE khi đi qua ≥ `min_passes` lần mà không đủ chạm; còn lại UNKNOWN (bị chặn khi lập
đường). Cùng bố cục lưới với costmap camera (`perception/costmap.py`): row theo y (trái +), col theo x
(trước +), gốc `Pose(x_min, y_min, 0)`.

Tư thế cảm biến `(x, y, yaw)` trong hệ lưới cho từng vòng quét: cố định (0, 0, 0) khi cảm biến đứng yên,
hoặc lấy từ odometry đã ghi (DROW `.odom2`) để thử ghép nhiều vòng. Không ước lượng tư thế ở đây.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import sys

import numpy as np

from autopark.domain.sensors import Costmap, LidarScan, SourceStamp
from autopark.image_io import imwrite
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec, costmap_to_dict, render, to_costmap
from autopark.perception.paths import atomic_write_json, utc_now


@dataclass
class OccupancyCounts:
    grid: GridSpec
    passes: np.ndarray = field(init=False)
    hits: np.ndarray = field(init=False)
    scans: int = 0
    beams_used: int = 0

    def __post_init__(self):
        rows, cols = self.grid.shape
        self.passes = np.zeros((rows, cols), np.int32)
        self.hits = np.zeros((rows, cols), np.int32)

    def _cells(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rows, cols = self.grid.shape
        r = np.floor((y - self.grid.y_min) / self.grid.resolution).astype(np.int64)
        c = np.floor((x - self.grid.x_min) / self.grid.resolution).astype(np.int64)
        inside = (r >= 0) & (r < rows) & (c >= 0) & (c < cols)
        return r, c, inside

    def add_scan(self, scan: LidarScan, pose=(0.0, 0.0, 0.0), *, max_range: float = 12.0, min_range: float = 0.0) -> int:
        """Ray-cast one scan taken from `pose` = (x, y, yaw) in the grid frame. Returns the number of beams used."""
        px, py, yaw = float(pose[0]), float(pose[1]), float(pose[2])
        angles = np.asarray(scan.angles_rad, np.float64) + yaw
        ranges = np.asarray(scan.ranges_m, np.float64)
        ok = np.isfinite(ranges) & (ranges >= min_range) & (ranges > 0)
        if not ok.any():
            self.scans += 1
            return 0
        angles, ranges = angles[ok], ranges[ok]
        step = self.grid.resolution / 2.0
        cos, sin = np.cos(angles), np.sin(angles)
        reach = np.minimum(ranges, max_range)
        # pass samples: from 0 to (reach - step), exclusive of the hit cell neighbourhood
        counts = np.maximum(np.floor((reach - step) / step).astype(np.int64) + 1, 0)
        total = int(counts.sum())
        if total:
            starts = np.cumsum(counts) - counts
            k = np.arange(total) - np.repeat(starts, counts)
            ray = np.repeat(np.arange(len(reach)), counts)
            d = k * step
            r, c, inside = self._cells(px + d * cos[ray], py + d * sin[ray])
            if inside.any():
                key = np.unique(np.stack([ray[inside], r[inside], c[inside]], axis=1), axis=0)
                np.add.at(self.passes, (key[:, 1], key[:, 2]), 1)
        hit = ranges <= max_range
        if hit.any():
            r, c, inside = self._cells(px + ranges[hit] * cos[hit], py + ranges[hit] * sin[hit])
            if inside.any():
                np.add.at(self.hits, (r[inside], c[inside]), 1)
        self.scans += 1
        self.beams_used += int(ok.sum())
        return int(ok.sum())

    def states(self, *, min_passes: int = 3, min_hits: int = 2, occupied_ratio: float = 0.2) -> np.ndarray:
        return states_from_counts(self.passes, self.hits, min_passes=min_passes, min_hits=min_hits,
                                  occupied_ratio=occupied_ratio)

    def summary(self, states: np.ndarray) -> dict:
        observed = (self.passes + self.hits) > 0
        return {"scans": self.scans, "beams_used": self.beams_used,
                "cells_free": int((states == FREE).sum()), "cells_occupied": int((states == OCCUPIED).sum()),
                "cells_unknown": int((states == UNKNOWN).sum()),
                "sharpness": float((states[observed] == OCCUPIED).sum() / max(1, (self.hits[observed] > 0).sum()))}


def states_from_counts(passes: np.ndarray, hits: np.ndarray, *, min_passes: int = 3, min_hits: int = 2,
                       occupied_ratio: float = 0.2) -> np.ndarray:
    """Cell states from pass/hit counts: OCCUPIED needs `min_hits` hits and a hit share >= `occupied_ratio`,
    FREE needs `min_passes` passes without qualifying as OCCUPIED, everything else is UNKNOWN."""
    observed = passes + hits
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(observed > 0, hits / np.maximum(observed, 1), 0.0)
    out = np.full(passes.shape, UNKNOWN, np.int8)
    occupied = (hits >= min_hits) & (ratio >= occupied_ratio)
    free = (passes >= min_passes) & ~occupied
    out[free] = FREE
    out[occupied] = OCCUPIED
    return out


def relative_poses(poses: np.ndarray) -> np.ndarray:
    """Express (x, y, yaw) rows relative to the first row: the grid is centred on the first scan."""
    x0, y0, yaw0 = poses[0]
    c, s = math.cos(-yaw0), math.sin(-yaw0)
    dx, dy = poses[:, 0] - x0, poses[:, 1] - y0
    out = np.column_stack([c * dx - s * dy, s * dx + c * dy, poses[:, 2] - yaw0])
    out[:, 2] = (out[:, 2] + math.pi) % (2 * math.pi) - math.pi
    return out


def build_costmap(counts: OccupancyCounts, states: np.ndarray, source_id: str, t: float) -> Costmap:
    return to_costmap(states, counts.grid, SourceStamp(source_id, max(0.0, t), True, "vehicle"))


def write_outputs(counts: OccupancyCounts, states: np.ndarray, out: Path, *, source: str, source_id: str, t: float,
                  extra: dict | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    costmap = build_costmap(counts, states, source_id, t)
    summary = counts.summary(states)
    atomic_write_json(out / "costmap.json", {
        "created_utc": utc_now(), "source": source, "grid": counts.grid.__dict__, "summary": summary,
        "method": "ray casting per beam; passes vs hits per cell; NaN beams ignored; no pose estimation",
        **(extra or {}), "costmap": costmap_to_dict(costmap)})
    imwrite(out / "map.png", render(states, counts.grid, None, None, scale=max(1, int(400 / max(states.shape)))))
    np.savez_compressed(out / "counts.npz", passes=counts.passes, hits=counts.hits)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--recording", type=Path, help="a .npz written by autopark.lidar.recording")
    src.add_argument("--drow", type=Path, help="a DROW v2 .csv (with --odom the matching .odom2 gives poses)")
    parser.add_argument("--odom", action="store_true", help="DROW only: move the sensor by the recorded odometry")
    parser.add_argument("--mirror", action="store_true", help="DROW only: flip the scan angle sign")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--scans", type=int, default=None, help="how many scans to accumulate (default: all)")
    parser.add_argument("--grid", type=float, nargs=5, metavar=("XMIN", "XMAX", "YMIN", "YMAX", "RES"),
                        default=(-4.0, 4.0, -4.0, 4.0, 0.05))
    parser.add_argument("--max-range", type=float, default=12.0)
    parser.add_argument("--min-passes", type=int, default=3)
    parser.add_argument("--min-hits", type=int, default=2)
    parser.add_argument("--occupied-ratio", type=float, default=0.2)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    grid = GridSpec(*args.grid)
    counts = OccupancyCounts(grid)
    extra: dict = {}
    if args.recording is not None:
        from .recording import read_recording

        recording = read_recording(args.recording)
        stop = len(recording) if args.scans is None else min(len(recording), args.start + args.scans)
        for index in range(args.start, stop):
            counts.add_scan(recording.scan(index), max_range=args.max_range)
        source, source_id, t = str(args.recording), recording.meta.get("source_id", "lidar"), float(recording.t[stop - 1] - recording.t[0])
        extra["pose"] = "fixed (0, 0, 0)"
    else:
        from .drow import DrowReplaySource
        from .drow_odom import read_drow_odom, scan_poses

        replay = DrowReplaySource(args.drow, mirror=args.mirror)
        stop = len(replay) if args.scans is None else min(len(replay), args.start + args.scans)
        poses = np.zeros((len(replay), 3))
        if args.odom:
            poses = scan_poses(replay.recording, read_drow_odom(args.drow.with_suffix(".odom2")))
            poses = relative_poses(np.where(np.isfinite(poses), poses, np.nan)[args.start:stop])
        used = 0
        for k, index in enumerate(range(args.start, stop)):
            pose = poses[k] if args.odom else (0.0, 0.0, 0.0)
            if args.odom and not np.all(np.isfinite(pose)):
                continue
            replay.index = index
            counts.add_scan(replay.read(), pose, max_range=args.max_range)
            used += 1
        source, source_id, t = str(args.drow), "drow_replay", float(replay.recording.t[stop - 1] - replay.recording.t[0])
        extra.update({"pose": "DROW odometry relative to the first scan" if args.odom else "fixed (0, 0, 0)",
                      "mirror": args.mirror, "scans_with_pose": used})
    states = counts.states(min_passes=args.min_passes, min_hits=args.min_hits, occupied_ratio=args.occupied_ratio)
    summary = write_outputs(counts, states, args.out, source=source, source_id=source_id, t=t, extra=extra)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
