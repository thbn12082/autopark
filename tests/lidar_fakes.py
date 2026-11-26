"""Dữ liệu LiDAR TỔNG HỢP dùng chung cho test nguồn tư thế LiDAR (T2, thêm 02/10/2026): sa bàn 3 × 2 m trong một
phòng không đối xứng, vật cản, vật di động, bản ghi `.npz` của `ScanRecorder`, bản đồ dựng từ vài chỗ đặt.

Tường phòng và cạnh hộp KHÔNG nằm trên biên ô 5 cm (tường trên biên ô cho dải OCCUPIED dày hai ô và trường khoảng cách
phẳng, xem `build_sim_map`). Không thiết bị, không tệp ngoài git."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from autopark.domain.sensors import LidarScan, SourceStamp
from autopark.domain.types import Bounds, ParkingGoal, Pose, Scenario, VehicleConfig
from autopark.lidar.localize import LocalizationMap
from autopark.lidar.map_builder import MapBuildConfig, build_map_from_poses
from autopark.lidar.pose_config import LidarMount, load_lidar_pose_config
from autopark.lidar.recording import ScanRecorder
from autopark.lidar.synthetic import box_segments, polygon_segments, raycast

BOARD = Bounds(0.0, 0.0, 3.0, 2.0)
# Phòng quanh sa bàn, không đối xứng (một góc khuyết, một hốc); tọa độ lệch lưới 5 cm.
ROOM = [(-1.13, -0.87), (4.06, -0.87), (4.06, 1.42), (3.48, 1.42), (3.48, 2.93), (0.67, 2.93), (0.67, 2.37),
        (-1.13, 2.37)]
BOXES = [(1.93, 0.37, 0.31, 0.58, 0.0), (2.87, 0.33, 0.27, 0.56, 0.0), (0.43, 1.73, 0.42, 0.22, 17.0)]
# Phòng chữ nhật trống (đối xứng 180°) và một phòng khác hẳn (để định vị phải hỏng)
SYMMETRIC_ROOM = [(-1.03, -0.97), (4.03, -0.97), (4.03, 2.97), (-1.03, 2.97)]
OTHER_ROOM = [(-0.38, -0.43), (1.27, -0.43), (1.27, 0.81), (-0.38, 0.81)]
CAR = VehicleConfig("xe_test", 0.19, 0.14, 0.06, 0.06, math.radians(30), 0.3, 0.3, 0.6, math.radians(90))


def scene(room=ROOM, boxes=BOXES) -> np.ndarray:
    parts = [polygon_segments(room)] + [box_segments(cx, cy, w, h, math.radians(yaw)) for cx, cy, w, h, yaw in boxes]
    return np.vstack(parts)


STATIC = scene()


def disc(cx, cy, r=0.15, sides=10) -> np.ndarray:
    return polygon_segments([(cx + r * math.cos(2 * math.pi * k / sides), cy + r * math.sin(2 * math.pi * k / sides))
                             for k in range(sides)])


def movers(t: float, count: int = 2) -> np.ndarray:
    """Vật di động (người đi quanh sa bàn) không có trong bản đồ: chạy vòng tròn quanh tâm sa bàn."""
    out = [disc(1.5 + 1.9 * math.cos(0.4 * t + 2.5 * k), 1.0 + 1.25 * math.sin(0.4 * t + 2.5 * k)) for k in range(count)]
    return np.vstack(out) if out else np.zeros((0, 4))


def scan_at(sensor, rng, *, segments=STATIC, beams=500, noise=0.01, dropout=0.1):
    """(góc, tầm) từ tư thế CẢM BIẾN `sensor` = (x, y, yaw) hoặc Pose."""
    if isinstance(sensor, Pose):
        sensor = (sensor.x, sensor.y, sensor.yaw)
    return raycast(sensor, segments, beams=beams, max_range_m=12.0, noise_m=noise, dropout=dropout, rng=rng)


def bench_scenario(start=Pose(0.5, 1.0, 0.0), obstacles=()) -> Scenario:
    return Scenario("ban_thu_lidar", BOARD, start, ParkingGoal(Pose(2.0, 1.0, 0.0)), obstacles=list(obstacles))


def default_config():
    return load_lidar_pose_config()


MAP_PLACEMENTS = [(0.62, 1.07, 0.2), (1.53, 1.41, 1.1), (2.41, 1.23, 2.3), (1.07, 0.48, -0.9), (2.23, 0.86, 3.0)]


def build_map(placements=MAP_PLACEMENTS, *, segments=STATIC, scans_per=4, seed=11, localize_config=None
              ) -> LocalizationMap:
    """Bản đồ định vị từ vài chỗ đặt cảm biến biết trước (không qua map_builder)."""
    rng = np.random.default_rng(seed)
    items = []
    for pose in placements:
        for _ in range(scans_per):
            items.append((scan_at(pose, rng, segments=segments), pose))
    _, states, grid = build_map_from_poses(items, None, MapBuildConfig(min_range=0.25, max_range=8.0))
    config = localize_config or default_config().localize
    return LocalizationMap(states, grid, config, source="lidar_fakes")


def scan_obj(angles, ranges, t: float, source_id: str = "c1_tong_hop") -> LidarScan:
    return LidarScan(SourceStamp(source_id, float(t), True, "lidar"), tuple(float(a) for a in angles),
                     tuple(float(r) if math.isfinite(r) else math.nan for r in ranges))


def write_recording(path: Path, scans, *, meta: dict | None = None) -> Path:
    """Ghi dãy (góc, tầm, t) thành bản ghi `.npz` + `.json` của `ScanRecorder`. Trả đường dẫn `.npz`."""
    recorder = ScanRecorder(Path(path), dict({"source_id": "c1_tong_hop", "mirror": False}, **(meta or {})))
    for angles, ranges, t in scans:
        recorder.add(scan_obj(angles, ranges, t), t_first=t - 0.1)
    return recorder.close()


def static_slice(sensor, seconds: float, rng, *, t0: float = 0.0, period: float = 0.1, segments=STATIC, **kwargs):
    """Cảm biến đứng yên `seconds` giây: dãy (góc, tầm, t)."""
    out = []
    for k in range(int(round(seconds / period))):
        angles, ranges = scan_at(sensor, rng, segments=segments, **kwargs)
        out.append((angles, ranges, t0 + k * period))
    return out


def sensor_of(vehicle: Pose, mount: LidarMount | None = None) -> Pose:
    mount = mount or default_config().mount
    return mount.sensor_pose(vehicle)
