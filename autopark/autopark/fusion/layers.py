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

ToF từ telemetry xe (thêm 24/09/2026): `TofMountConfig` (nạp `configs/tof_mounts_v0.json`) gán chỉ số 0–3 của
`VehicleTelemetry.tof_m` với `sensor_id`, vị trí gá trên xe, tầm đo; `tof_to_near_field` đổi một khung telemetry thành
các `NearFieldReading` (None = bit mặt nạ 0, NaN, ≤ 0, dưới tầm tối thiểu → `valid=False`, kèm lý do; từ tầm tối đa
trở lên mà bit hợp lệ → vẫn `valid=True` nhưng không đánh dấu ô nào); `NearFieldLayer.add_telemetry` nạp cả khung một
lần. Vị trí gá và tầm đo trong tệp cấu hình là GIẢ ĐỊNH – CHƯA ĐO. Mới thử với khung telemetry do `FirmwareModel` sinh
(cổng serial giả), chưa có VL53L1X thật nào được đọc.

Tính hợp lệ của lớp gần xe (sửa muộn tối 24/09/2026 theo rà soát): một ToF không dùng được (bit mặt nạ 0 — "không có
vật trong tầm" hoặc lỗi cảm biến, giao thức v1 chưa phân biệt được) chỉ mất CUNG CỦA NÓ: không thêm ô nào, không bao
giờ ra FREE, và được ghi vào `invalid_sensors`/`sensor_notes` (có trong `status()`). Với khung telemetry, lớp chỉ
không hợp lệ khi stamp của KHUNG không hợp lệ (hoặc một cảm biến trong `required_sensors` không dùng được). Trước bản
sửa, một ToF không thấy gì làm cả lớp không hợp lệ và `fuse()` bỏ luôn các cung OCCUPIED của ToF khác (mất vật cản
một cách im lặng khi lớp là tùy chọn).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Iterable, Protocol

import numpy as np

from autopark.domain.sensors import Costmap, LidarScan, SourceStamp
from autopark.domain.types import Pose
from autopark.lidar.occupancy import OccupancyCounts
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec, costmap_to_dict, to_costmap
from autopark.perception.paths import atomic_write_json, utc_now
from autopark.safety.freshness import SourcePolicy
from autopark.transport.protocol import N_TOF

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
    # lý do không hợp lệ (tof_to_near_field); với số đo hợp lệ: "ngoài tầm dùng được..." khi ≥ max_range_m (không
    # đánh dấu ô nào), còn lại rỗng
    note: str = ""


@dataclass(frozen=True)
class NearFieldMount:
    x: float
    y: float
    yaw: float
    fov_deg: float = 25.0   # VL53L1X-class field of view; only the measured arc is marked, never the whole cone


# ---------------------------------------------------------------- ToF telemetry → NearFieldReading (24/09/2026)
class TofTelemetry(Protocol):
    """Phần của `transport.vehicle_io.VehicleTelemetry` mà phép đổi cần (không import tầng transport ở đây)."""

    stamp: SourceStamp
    tof_m: tuple[float | None, ...]


_TOF_TOP_KEYS = {"schema_version", "notes", "frame", "vehicle_config", "sensors"}
_TOF_SENSOR_KEYS = {"index", "sensor_id", "x_m", "y_m", "yaw_deg", "fov_deg", "min_range_m", "max_range_m", "note"}
_TOF_REQUIRED_KEYS = {"index", "sensor_id", "x_m", "y_m", "yaw_deg", "fov_deg", "min_range_m", "max_range_m"}
_TOF_NUMBER_KEYS = ("x_m", "y_m", "yaw_deg", "fov_deg", "min_range_m", "max_range_m")


def _tof_config_number(sensor_id: str, key: str, value) -> float:
    """Một trường số của bảng gá ToF: chỉ nhận số JSON (int/float, không nhận bool). null, true/false, chuỗi ("0.25",
    "0,25"), danh sách → ValueError nêu cảm biến và khóa, thay vì TypeError/ValueError tiếng Anh của `float()`."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"mục ToF {sensor_id}: {key} phải là số JSON (dấu chấm thập phân, không để trong ngoặc kép), "
                         f"nhận {value!r}")
    return float(value)


@dataclass(frozen=True)
class TofSensorMount:
    """Chỉ số ToF trên dây → cảm biến: tên, vị trí gá trong HỆ XE (gốc tâm trục sau, x tiến, y trái, yaw ngược chiều
    kim đồng hồ), tầm đo dùng được [min_range_m, max_range_m)."""

    index: int
    sensor_id: str
    mount: NearFieldMount
    min_range_m: float
    max_range_m: float
    note: str = ""


@dataclass(frozen=True)
class TofMountConfig:
    """Bảng gán chỉ số `VehicleTelemetry.tof_m` → vị trí gá (`configs/tof_mounts_v0.json`). Chỉ số không có trong
    bảng thì số đo của nó bị bỏ (xem `unmapped_tof_indices`)."""

    sensors: tuple[TofSensorMount, ...]
    notes: str = ""
    source: str | None = None

    def __post_init__(self):
        if not self.sensors:
            raise ValueError("cần ít nhất một cảm biến ToF")
        indices = [s.index for s in self.sensors]
        ids = [s.sensor_id for s in self.sensors]
        if len(set(indices)) != len(indices) or len(set(ids)) != len(ids):
            raise ValueError("chỉ số và sensor_id của ToF phải khác nhau")
        for s in self.sensors:
            if isinstance(s.index, bool) or not isinstance(s.index, int) or not 0 <= s.index < N_TOF:
                raise ValueError(f"{s.sensor_id}: index phải là số nguyên trong [0, {N_TOF - 1}] "
                                 f"(tof_mm[{N_TOF}] trên dây)")
            if not s.sensor_id or not isinstance(s.sensor_id, str):
                raise ValueError("sensor_id phải là chuỗi khác rỗng")
            m = s.mount
            if not all(math.isfinite(v) for v in (m.x, m.y, m.yaw, m.fov_deg, s.min_range_m, s.max_range_m)):
                raise ValueError(f"{s.sensor_id}: số phải hữu hạn")
            if not 0 < m.fov_deg < 180:
                raise ValueError(f"{s.sensor_id}: fov_deg phải trong (0, 180)")
            if not 0 < s.min_range_m < s.max_range_m:
                raise ValueError(f"{s.sensor_id}: cần 0 < min_range_m < max_range_m")

    def by_index(self) -> dict[int, TofSensorMount]:
        return {s.index: s for s in self.sensors}

    def near_field_mounts(self) -> dict[str, NearFieldMount]:
        return {s.sensor_id: s.mount for s in self.sensors}

    @classmethod
    def from_dict(cls, data: dict, source: str | None = None) -> "TofMountConfig":
        """Khóa lạ hoặc thiếu, sensor_id không phải chuỗi, index không phải số nguyên, trường số không phải số JSON
        (null, true/false, chuỗi như "0,25") → ValueError nêu mục và khóa (không âm thầm rơi về vị trí mặc định)."""
        if not isinstance(data, dict):
            raise ValueError("cấu hình ToF phải là một đối tượng JSON")
        unknown = set(data) - _TOF_TOP_KEYS
        if unknown:
            raise ValueError(f"khóa lạ trong cấu hình ToF: {sorted(unknown)}")
        if data.get("schema_version") != 1:
            raise ValueError(f"schema_version {data.get('schema_version')!r} không được hỗ trợ (cần 1)")
        rows = data.get("sensors")
        if not isinstance(rows, list):
            raise ValueError("sensors phải là danh sách")
        sensors = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("mỗi mục sensors phải là đối tượng JSON")
            unknown, missing = set(row) - _TOF_SENSOR_KEYS, _TOF_REQUIRED_KEYS - set(row)
            if unknown or missing:
                raise ValueError(f"mục ToF {row.get('sensor_id', '?')}: khóa lạ {sorted(unknown)}, "
                                 f"thiếu {sorted(missing)}")
            sensor_id = row["sensor_id"]
            if not isinstance(sensor_id, str) or not sensor_id:
                raise ValueError(f"mục ToF: sensor_id phải là chuỗi khác rỗng, nhận {sensor_id!r}")
            index = row["index"]
            if isinstance(index, bool) or not isinstance(index, int):
                raise ValueError(f"mục ToF {sensor_id}: index phải là số nguyên")
            num = {key: _tof_config_number(sensor_id, key, row[key]) for key in _TOF_NUMBER_KEYS}
            sensors.append(TofSensorMount(
                index, sensor_id,
                NearFieldMount(num["x_m"], num["y_m"], math.radians(num["yaw_deg"]), num["fov_deg"]),
                num["min_range_m"], num["max_range_m"], str(row.get("note", ""))))
        return cls(tuple(sorted(sensors, key=lambda s: s.index)), str(data.get("notes", "")), source)

    @classmethod
    def load(cls, path) -> "TofMountConfig":
        path = Path(path)
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")), str(path))


def _tof_problem(value, mount: TofSensorMount) -> str | None:
    """Lý do một số đo ToF không dùng được; None khi dùng được. Số đo không dùng được KHÔNG BAO GIỜ thành khoảng
    cách "an toàn" (lớn) hay FREE: nó thành `valid=False`, không thêm ô nào (chỉ cung của chính cảm biến đó bị mất)
    và được ghi vào `NearFieldLayer.invalid_sensors`. Chỉ stamp KHUNG không hợp lệ mới làm cả lớp không hợp lệ.
    Số đo từ tầm tối đa trở lên có bit hợp lệ KHÔNG phải lỗi ở đây (xem `tof_to_near_field`)."""
    if value is None:
        return "bo báo không hợp lệ (bit mặt nạ = 0: không có vật trong tầm hoặc lỗi cảm biến)"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return f"kiểu lạ {type(value).__name__}"
    if not math.isfinite(value):
        return f"không hữu hạn ({value})"
    if value <= 0:
        return f"≤ 0 ({value:.3f} m) dù bit hợp lệ"
    if value < mount.min_range_m:
        return f"{value:.3f} m dưới tầm tối thiểu {mount.min_range_m:.3f} m"
    return None


def tof_to_near_field(telemetry: TofTelemetry, config: TofMountConfig) -> list[NearFieldReading]:
    """Một khung telemetry → một `NearFieldReading` cho MỖI cảm biến trong bảng gá (theo thứ tự chỉ số).

    Cả khung dùng chung stamp của telemetry (thời điểm laptop nhận, giờ bo không dùng ở đây); `frame_id` là
    `sensor_id` (khoảng cách đo dọc trục cảm biến). Số đo hợp lệ: `range_m` = số đo, `valid=True`. Từ tầm tối đa trở
    lên mà bit hợp lệ: vẫn `valid=True`, `range_m` giữ nguyên, `note` "ngoài tầm dùng được..." — `NearFieldLayer` bỏ
    qua số đo này (không OCCUPIED, không bao giờ FREE), như hợp đồng cũ của lớp (`tests/test_fusion.py`). Trần vật lý
    của VL53L1X (số lớn hơn thì chắc chắn là lỗi) cần tra datasheet, CHƯA dùng. Không dùng được (None, NaN/vô cực,
    ≤ 0, dưới tầm tối thiểu, stamp của khung không hợp lệ): `range_m` NaN, `valid=False`, `note` ghi lý do. Chỉ số
    không có trong bảng bị bỏ."""
    stamp = telemetry.stamp
    values = tuple(telemetry.tof_m)
    out = []
    for mount in config.sensors:
        value = values[mount.index] if mount.index < len(values) else None
        problem = _tof_problem(value, mount)
        if problem is None and not stamp.valid:
            problem = "khung telemetry không hợp lệ"
        beyond = problem is None and value >= mount.max_range_m
        note = problem or (f"ngoài tầm dùng được ({value:.3f} m ≥ tầm tối đa {mount.max_range_m:.3f} m), "
                           f"không đánh dấu" if beyond else "")
        out.append(NearFieldReading(
            SourceStamp(stamp.source_id, stamp.t, problem is None, mount.sensor_id), mount.sensor_id,
            float(value) if problem is None else math.nan, mount.max_range_m, problem is None, note))
    return out


def unmapped_tof_indices(telemetry: TofTelemetry, config: TofMountConfig) -> list[int]:
    """Chỉ số có số đo (khác None) mà bảng gá không có: firmware và cấu hình không khớp, cần xem lại."""
    mapped = config.by_index()
    return [k for k, value in enumerate(telemetry.tof_m) if value is not None and k not in mapped]


class NearFieldLayer(MapLayer):
    """Near-field ranging (ToF). A valid in-range reading marks a small arc OCCUPIED at the measured distance;
    nothing is ever marked FREE from it. An unusable reading (mask bit 0, NaN, below the minimum range...) adds no
    cells, so only that sensor's arc is missing; it is listed in `invalid_sensors` (reason) and `sensor_notes`
    (every note, including valid readings beyond `max_range_m`, which also mark nothing).

    Layer validity (sửa muộn tối 24/09/2026): với khung telemetry (`add_telemetry`, hoặc `add_readings(...,
    frame_stamp=...)`) lớp hợp lệ theo stamp của KHUNG, nên một ToF không thấy gì không xóa cung OCCUPIED của ToF
    khác khi `fuse()`. Không có khung (`add_reading`/`add_readings` từ nguồn chung): lớp không hợp lệ khi KHÔNG còn số
    đo nào hợp lệ (một cảm biến duy nhất báo không hợp lệ → lớp không hợp lệ, như `tests/test_fusion.py`). Ở cả hai
    đường, một cảm biến trong `required_sensors` không dùng được hoặc chưa có số đo cũng làm lớp không hợp lệ.

    `required_sensors` mặc định rỗng và CHƯA NÊN BẬT với giao thức v1: bit mặt nạ 0 vừa là "không có vật trong tầm"
    vừa là "lỗi cảm biến", nên một ToF bắt buộc nhìn vào khoảng trống sẽ làm lớp không hợp lệ (lớp bắt buộc → chặn cả
    bản đồ; lớp tùy chọn → mất cung của ToF khác). Chỉ có nghĩa khi giao thức phân biệt được hai trường hợp (mặt nạ sức
    khỏe riêng, ĐỀ XUẤT – CHỜ CHỐT trong docs/GIAO_THUC_XE.md mục 12)."""

    def __init__(self, grid: GridSpec, mounts: dict[str, NearFieldMount], *, max_age_s: float = 0.3,
                 name: str = "near_field", required: bool = False, required_sensors: Iterable[str] = ()):
        super().__init__(name, SourcePolicy(max_age_s=max_age_s), required=required)
        if not mounts:
            raise ValueError("at least one ToF mount is required")
        self.grid = grid
        self.mounts = dict(mounts)
        self.required_sensors = frozenset(required_sensors)
        unknown = self.required_sensors - set(self.mounts)
        if unknown:
            raise ValueError(f"required_sensors không có trong bảng gá: {sorted(unknown)}")
        self.readings: dict[str, tuple[NearFieldReading, Pose]] = {}
        self.invalid_sensors: dict[str, str] = {}     # cảm biến không dùng được ở lần dựng cuối → lý do
        self.sensor_notes: dict[str, str] = {}        # mọi ghi chú (kể cả số đo hợp lệ ngoài tầm)

    @classmethod
    def from_tof_config(cls, grid: GridSpec, config: TofMountConfig, **kwargs) -> "NearFieldLayer":
        """Lớp gần xe với vị trí gá lấy từ bảng ToF (24/09/2026)."""
        return cls(grid, config.near_field_mounts(), **kwargs)

    def add_telemetry(self, telemetry: TofTelemetry, vehicle_pose: Pose, config: TofMountConfig) -> Costmap:
        """Nạp mọi ToF của một khung telemetry (qua `tof_to_near_field`) rồi dựng bản đồ một lần; lớp hợp lệ theo
        stamp của khung (xem docstring lớp)."""
        return self.add_readings(tof_to_near_field(telemetry, config), vehicle_pose, frame_stamp=telemetry.stamp)

    def add_readings(self, readings: Iterable[NearFieldReading], vehicle_pose: Pose, *,
                     frame_stamp: SourceStamp | None = None) -> Costmap:
        """Nạp nhiều số đo rồi dựng bản đồ một lần. `frame_stamp`: stamp của khung telemetry chứa các số đo (lớp hợp
        lệ theo nó); None: nguồn chung, lớp hợp lệ khi còn ít nhất một số đo hợp lệ."""
        readings = list(readings)
        if not readings:
            raise ValueError("không có số đo ToF nào")
        for reading in readings:
            if reading.sensor_id not in self.mounts:
                raise KeyError(f"no mount for ToF sensor {reading.sensor_id!r}")
        for reading in readings:
            self.readings[reading.sensor_id] = (reading, vehicle_pose)
        return self._rebuild(readings[-1], frame_stamp)

    def add_reading(self, reading: NearFieldReading, vehicle_pose: Pose) -> Costmap:
        if reading.sensor_id not in self.mounts:
            raise KeyError(f"no mount for ToF sensor {reading.sensor_id!r}")
        self.readings[reading.sensor_id] = (reading, vehicle_pose)
        return self._rebuild(reading)

    def status(self, now: float) -> dict:
        return {**super().status(now), "invalid_sensors": dict(self.invalid_sensors),
                "sensor_notes": dict(self.sensor_notes), "required_sensors": sorted(self.required_sensors)}

    def _rebuild(self, reading: NearFieldReading, frame_stamp: SourceStamp | None = None) -> Costmap:
        self.invalid_sensors = {sid: (r.note or "không hợp lệ") for sid, (r, _) in self.readings.items() if not r.valid}
        missing = sorted(self.required_sensors - set(self.readings))
        self.invalid_sensors.update({sid: "chưa có số đo" for sid in missing})
        self.sensor_notes = {**{sid: r.note for sid, (r, _) in self.readings.items() if r.note}, **self.invalid_sensors}
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
        if frame_stamp is None:   # nguồn chung (add_reading/add_readings): còn ít nhất một số đo hợp lệ
            src, t = reading.stamp.source_id, reading.stamp.t
            valid = any(r.valid for r, _ in self.readings.values())
        else:                     # khung telemetry: hợp lệ theo khung; ToF hỏng/không có đích chỉ mất cung của nó
            src, t, valid = frame_stamp.source_id, frame_stamp.t, frame_stamp.valid
        valid = valid and not (self.required_sensors & set(self.invalid_sensors))
        costmap = to_costmap(states, self.grid, SourceStamp(src, t, valid, MAP_FRAME))
        self.set(costmap)
        return costmap
