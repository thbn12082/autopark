"""Các lớp bản đồ cho hợp nhất cảm biến (kế hoạch mục 7, "Khi chưa có IMU, ToF hoặc ESP32").

Bốn lớp mang tên trong kế hoạch, cùng một giao diện: mỗi lớp giữ một `Costmap` trong HỆ BẢN ĐỒ (hoặc chưa có),
stamp của lần cập nhật cuối và chính sách tuổi (`SourcePolicy` của `safety.freshness`). `fresh(now)` là điều
kiện để lớp được dùng khi hợp nhất; lớp bắt buộc mà không tươi thì toàn bộ bản đồ hợp nhất không hợp lệ và
mọi ô bị chặn (`Costmap.blocked`). Phép biến đổi rig–map = tư thế cảm biến trong hệ xe ∘ tư thế xe trong hệ
bản đồ; thử bằng vị trí biết trước trong `tests/test_fusion.py`.

- `StaticMapLayer`: bản đồ tĩnh nạp từ `costmap.json` (ví dụ bản đồ LiDAR đứng yên của `lidar/occupancy.py`);
  không hết hạn theo thời gian, chỉ thay khi nạp bản khác.
- `LiveLidarLayer`: N vòng quét LiDAR mới nhất ray-cast vào lưới bản đồ theo tư thế xe tại lúc quét.
- `CameraSemanticLayer`: costmap FREE/BLOCKED của camera (`perception/costmap.py`, hệ xe) đặt vào hệ bản đồ.
- `NearFieldLayer`: số đo ToF gần xe; mỗi số đo chỉ đánh dấu một cung nhỏ ở khoảng cách đo được, không suy ra
  FREE, và số đo không hợp lệ không biến thành khoảng cách "an toàn". Mới chỉ được nạp bằng dữ liệu giả có
  cùng cấu trúc `NearFieldReading`; chưa có ToF thật nào được đọc.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np

from autopark.domain.sensors import Costmap, LidarScan, SourceStamp
from autopark.domain.types import Pose
from autopark.lidar.occupancy import OccupancyCounts
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec, costmap_to_dict, to_costmap
from autopark.perception.paths import atomic_write_json, utc_now
from autopark.safety.freshness import SourcePolicy

MAP_FRAME = "map"


# ---------------------------------------------------------------- costmap helpers
def costmap_states(costmap: Costmap) -> np.ndarray:
    return np.array(costmap.cells, dtype=np.int8)


def costmap_grid(costmap: Costmap) -> GridSpec:
    rows, cols = len(costmap.cells), len(costmap.cells[0])
    res = costmap.resolution_m
    return GridSpec(costmap.origin.x, costmap.origin.x + cols * res, costmap.origin.y, costmap.origin.y + rows * res, res)


def read_costmap_json(path) -> Costmap:
    """Load a costmap written by `write_costmap_json` or by lidar/occupancy.py / perception/costmap.py."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    body = data["costmap"] if "costmap" in data else data
    stamp = body["stamp"]
    return Costmap(SourceStamp(stamp["source_id"], float(stamp["t"]), bool(stamp.get("valid", True)), stamp.get("frame_id", MAP_FRAME)),
                   float(body["resolution_m"]), Pose.from_dict(body["origin"]),
                   tuple(tuple(int(v) for v in row) for row in body["cells"]))


def write_costmap_json(path, costmap: Costmap, extra: dict | None = None) -> Path:
    path = Path(path)
    atomic_write_json(path, {"created_utc": utc_now(), **(extra or {}), "costmap": costmap_to_dict(costmap)})
    return path


def resample(costmap: Costmap, grid: GridSpec, pose: Pose | None = None) -> np.ndarray:
    """States of `costmap` looked up at the cell centres of `grid` (nearest cell).

    `pose` is where the costmap's own frame sits in the grid frame (None: both share a frame). Grid cells
    that fall outside the costmap are UNKNOWN: no data is not free space.
    """
    gx, gy = grid.centers()
    if pose is None:
        bx, by = gx, gy
    else:
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        dx, dy = gx - pose.x, gy - pose.y
        bx, by = c * dx + s * dy, -s * dx + c * dy
    source, sgrid = costmap_states(costmap), costmap_grid(costmap)
    rows, cols = source.shape
    r = np.floor((by - sgrid.y_min) / sgrid.resolution).astype(np.int64)
    k = np.floor((bx - sgrid.x_min) / sgrid.resolution).astype(np.int64)
    inside = (r >= 0) & (r < rows) & (k >= 0) & (k < cols)
    out = np.full(gx.shape, UNKNOWN, np.int8)
    out[inside] = source[r[inside], k[inside]]
    return out


def sensor_pose_in_map(vehicle_pose: Pose, mount: tuple[float, float, float]) -> tuple[float, float, float]:
    """rig–map transform: a sensor mounted at `mount` = (x, y, yaw) in the vehicle frame, vehicle at `vehicle_pose`."""
    x, y = vehicle_pose.to_world(mount[0], mount[1])
    return x, y, vehicle_pose.yaw + mount[2]


# ---------------------------------------------------------------- layers
class MapLayer:
    """A costmap in the map frame plus the rule that says whether it may be used at time `now`."""

    def __init__(self, name: str, policy: SourcePolicy | None, *, required: bool = True):
        self.name = name
        self.policy = policy          # None: never expires (static data)
        self.required = required
        self.costmap: Costmap | None = None
        self.updates = 0

    def set(self, costmap: Costmap) -> None:
        if costmap.stamp.frame_id != MAP_FRAME:
            raise ValueError(f"{self.name}: layer costmaps must be in the '{MAP_FRAME}' frame, got {costmap.stamp.frame_id!r}")
        self.costmap = costmap
        self.updates += 1

    def fresh(self, now: float) -> bool:
        if self.costmap is None or not self.costmap.stamp.valid:
            return False
        if self.policy is None:
            return True
        return self.costmap.stamp.fresh(now, self.policy.max_age_s)

    def states_on(self, grid: GridSpec) -> np.ndarray:
        if self.costmap is None:
            return np.full(grid.shape, UNKNOWN, np.int8)
        return resample(self.costmap, grid)

    def status(self, now: float) -> dict:
        stamp = None if self.costmap is None else self.costmap.stamp
        return {"has_data": stamp is not None, "valid": None if stamp is None else stamp.valid,
                "age_s": None if stamp is None else now - stamp.t, "fresh": self.fresh(now),
                "required": self.required, "updates": self.updates,
                "max_age_s": None if self.policy is None else self.policy.max_age_s}


class StaticMapLayer(MapLayer):
    def __init__(self, name: str = "static_map", *, required: bool = True):
        super().__init__(name, None, required=required)
        self.source: str | None = None

    def load(self, path) -> Costmap:
        costmap = read_costmap_json(path)
        if costmap.stamp.frame_id != MAP_FRAME:      # occupancy.py writes "vehicle" for a sensor that never moved
            costmap = Costmap(SourceStamp(costmap.stamp.source_id, costmap.stamp.t, costmap.stamp.valid, MAP_FRAME),
                              costmap.resolution_m, costmap.origin, costmap.cells)
        self.set(costmap)
        self.source = str(path)
        return costmap


class LiveLidarLayer(MapLayer):
    """The last `window` scans, ray-cast into the map grid from where the vehicle was when each scan was taken."""

    def __init__(self, grid: GridSpec, *, mount: tuple[float, float, float] = (0.0, 0.0, 0.0), window: int = 3,
                 max_age_s: float = 0.3, expected_period_s: float | None = 0.1, max_range: float = 12.0,
                 min_range: float = 0.05, self_mask=None, mask_margin: float = 0.05,
                 min_passes: int = 1, min_hits: int | None = None, name: str = "live_lidar", required: bool = True):
        """`min_hits` (default 2, or 1 when the window is 1) is the persistence rule: a cell is OCCUPIED only when
        hit in that many of the last `window` scans. Measured on the real C1 (2026-09-22): with a single hit a
        static desk scene produced a few flickering "new" cells every scan, which stopped the simulated car at
        once; requiring 2 of 3 removes that at the cost of one extra revolution (~0.1 s) of latency.

        `min_range` drops returns inside the datasheet blind zone (0.05 m). `self_mask` (a `VehicleConfig`) drops
        every return whose hit point lies inside the vehicle body grown by `mask_margin`: a mounted LiDAR sees
        the car's own body and cables, and on the bench the adapter board 9 cm away landed inside the virtual
        car and made the start pose "in collision". Masked beams count as no return (never FREE)."""
        super().__init__(name, SourcePolicy(max_age_s=max_age_s, expected_period_s=expected_period_s), required=required)
        if window < 1:
            raise ValueError("window must be >= 1")
        self.grid = grid
        self.mount = mount
        self.max_range = max_range
        self.min_range = min_range
        self.self_mask = self_mask
        self.mask_margin = mask_margin
        self.window = window
        self.min_passes = min_passes
        self.min_hits = min(2, window) if min_hits is None else min_hits
        self._window: deque[OccupancyCounts] = deque(maxlen=window)
        self.last_sensor_pose: tuple[float, float, float] | None = None
        self.masked_beams = 0

    def filter_scan(self, scan: LidarScan) -> LidarScan:
        """Blind-zone and self-body filtering in the SENSOR frame (mount known, vehicle pose not needed)."""
        angles = np.asarray(scan.angles_rad, np.float64)
        ranges = np.asarray(scan.ranges_m, np.float64).copy()
        drop = np.isfinite(ranges) & (ranges < self.min_range)
        if self.self_mask is not None:
            mx, my, myaw = self.mount
            c, s = math.cos(myaw), math.sin(myaw)
            hx = ranges * np.cos(angles)                      # hit points in the sensor frame ...
            hy = ranges * np.sin(angles)
            vx = mx + c * hx - s * hy                         # ... then in the vehicle frame
            vy = my + s * hx + c * hy
            cfg, m = self.self_mask, self.mask_margin
            inside = ((vx >= -cfg.rear_overhang - m) & (vx <= cfg.wheelbase + cfg.front_overhang + m)
                      & (np.abs(vy) <= cfg.width / 2 + m))
            drop |= np.isfinite(ranges) & inside
        if not drop.any():
            return scan
        self.masked_beams += int(drop.sum())
        ranges[drop] = np.nan
        return LidarScan(scan.stamp, scan.angles_rad, tuple(ranges.tolist()))

    def add_scan(self, scan: LidarScan, vehicle_pose: Pose) -> Costmap:
        counts = OccupancyCounts(self.grid)
        self.last_sensor_pose = sensor_pose_in_map(vehicle_pose, self.mount)
        counts.add_scan(self.filter_scan(scan), self.last_sensor_pose, max_range=self.max_range)
        self._window.append(counts)
        # persistence counts SCANS, not beams: several beams of one scan hitting the same cell are one hit
        scans_hit = sum((c.hits > 0).astype(np.int32) for c in self._window)
        scans_passed = sum((c.passes > 0).astype(np.int32) for c in self._window)
        # a cell hit in fewer scans than `min_hits` is suspicious, not free: it stays UNKNOWN, never FREE
        states = np.full(self.grid.shape, UNKNOWN, np.int8)
        states[(scans_passed >= self.min_passes) & (scans_hit == 0)] = FREE
        states[scans_hit >= self.min_hits] = OCCUPIED
        costmap = to_costmap(states, self.grid, SourceStamp(scan.stamp.source_id, scan.stamp.t, scan.stamp.valid, MAP_FRAME))
        self.set(costmap)
        return costmap


class ScanUnion:
    """Baseline builder: how many SCANS hit / passed each cell (one scan counts once however many beams land in
    a cell), so `states(min_hits=2)` means "seen in at least two scans". Beam-count persistence would call a
    cell occupied after a single scan whenever several beams of that scan fall into it."""

    def __init__(self, grid: GridSpec):
        self.grid = grid
        self.scans_hit = np.zeros(grid.shape, np.int32)
        self.scans_passed = np.zeros(grid.shape, np.int32)
        self.count = 0

    def add(self, scan: LidarScan, sensor_pose: tuple[float, float, float], *, max_range: float = 12.0) -> None:
        counts = OccupancyCounts(self.grid)
        counts.add_scan(scan, sensor_pose, max_range=max_range)
        self.scans_hit += (counts.hits > 0).astype(np.int32)
        self.scans_passed += (counts.passes > 0).astype(np.int32)
        self.count += 1

    def states(self, *, min_hits: int = 2) -> np.ndarray:
        states = np.full(self.grid.shape, UNKNOWN, np.int8)
        states[(self.scans_passed >= 1) & (self.scans_hit == 0)] = FREE
        states[self.scans_hit >= max(1, min_hits)] = OCCUPIED
        return states

    def costmap(self, stamp: SourceStamp, *, min_hits: int = 2) -> Costmap:
        return to_costmap(self.states(min_hits=min_hits), self.grid, stamp)


class CameraSemanticLayer(MapLayer):
    """FREE/BLOCKED costmap from the camera pipeline (vehicle frame) placed into the map by the vehicle pose."""

    def __init__(self, grid: GridSpec, *, max_age_s: float = 0.5, name: str = "camera_semantic", required: bool = False):
        super().__init__(name, SourcePolicy(max_age_s=max_age_s), required=required)
        self.grid = grid

    def set_vehicle_frame(self, costmap_vehicle: Costmap, vehicle_pose: Pose) -> Costmap:
        states = resample(costmap_vehicle, self.grid, pose=vehicle_pose)
        stamp = costmap_vehicle.stamp
        costmap = to_costmap(states, self.grid, SourceStamp(stamp.source_id, stamp.t, stamp.valid, MAP_FRAME))
        self.set(costmap)
        return costmap


@dataclass(frozen=True)
class NearFieldReading:
    """One ToF measurement with the structure the real telemetry will carry: source, time, value, validity."""

    stamp: SourceStamp
    sensor_id: str
    range_m: float          # NaN when the sensor reported nothing usable
    max_range_m: float
    valid: bool = True


@dataclass(frozen=True)
class NearFieldMount:
    x: float
    y: float
    yaw: float
    fov_deg: float = 25.0   # VL53L1X-class field of view; only the measured arc is marked, never the whole cone


class NearFieldLayer(MapLayer):
    """Near-field ranging (ToF). A valid in-range reading marks a small arc OCCUPIED at the measured distance;
    nothing is ever marked FREE from it, and an invalid reading contributes no cells and makes the layer stale."""

    def __init__(self, grid: GridSpec, mounts: dict[str, NearFieldMount], *, max_age_s: float = 0.3,
                 name: str = "near_field", required: bool = False):
        super().__init__(name, SourcePolicy(max_age_s=max_age_s), required=required)
        if not mounts:
            raise ValueError("at least one ToF mount is required")
        self.grid = grid
        self.mounts = dict(mounts)
        self.readings: dict[str, tuple[NearFieldReading, Pose]] = {}

    def add_reading(self, reading: NearFieldReading, vehicle_pose: Pose) -> Costmap:
        if reading.sensor_id not in self.mounts:
            raise KeyError(f"no mount for ToF sensor {reading.sensor_id!r}")
        self.readings[reading.sensor_id] = (reading, vehicle_pose)
        states = np.full(self.grid.shape, UNKNOWN, np.int8)
        rows, cols = self.grid.shape
        for sensor_id, (r, pose) in self.readings.items():
            mount = self.mounts[sensor_id]
            if not r.valid or not math.isfinite(r.range_m) or not 0 < r.range_m < r.max_range_m:
                continue
            sx, sy, syaw = sensor_pose_in_map(pose, (mount.x, mount.y, mount.yaw))
            half = math.radians(mount.fov_deg) / 2
            for a in np.linspace(syaw - half, syaw + half, 9):
                x, y = sx + r.range_m * math.cos(a), sy + r.range_m * math.sin(a)
                row = int(math.floor((y - self.grid.y_min) / self.grid.resolution))
                col = int(math.floor((x - self.grid.x_min) / self.grid.resolution))
                if 0 <= row < rows and 0 <= col < cols:            # arcs outside the grid are simply not mapped
                    states[row, col] = OCCUPIED
        valid = all(r.valid for r, _ in self.readings.values())
        costmap = to_costmap(states, self.grid, SourceStamp(reading.stamp.source_id, reading.stamp.t, valid, MAP_FRAME))
        self.set(costmap)
        return costmap
