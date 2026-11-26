"""Vòng quét LiDAR TỔNG HỢP dựng từ sa bàn (thêm 02/10/2026, T2): nguồn "LiDAR mô phỏng" của phiên đỗ xe và dữ liệu cho
test. MÔ PHỎNG, không phải phép đo: số tia, nhiễu, mất phản hồi, tầm đo là GIẢ ĐỊNH kiểu RPLIDAR C1
(configs/dinh_vi_lidar_v0.json, khối "sim").

Cảnh 2D là tập đoạn thẳng (N, 4) = (ax, ay, bx, by) trong hệ sa bàn:

- `scenario_segments`: biên sa bàn làm tường (`walls_from_bounds`), mọi vật cản (`Obstacle.corners()`), và tường phòng
  bao quanh sa bàn cách `room_margin_m`, có MỘT khấc ở một góc để phòng trống không đối xứng 180°. Khi biên sa bàn là
  tường thì tường phòng bị che (tia 2D không xuyên tường): cảnh chỉ còn sa bàn và vật cản; sa bàn trống là hình chữ nhật
  đối xứng 180°, nên định vị phải khởi tạo quanh điểm xuất phát (tìm toàn cục sẽ AMBIGUOUS).
- `raycast`: cùng phép toán với hàm trợ giúp của tests/test_scan_odometry.py: góc theo quy ước dự án (0 = phía trước, dương
  ngược chiều kim đồng hồ), NaN = không phản hồi (ngoài tầm, mất phản hồi ngẫu nhiên).
- `SyntheticScanner`: vòng quét từ tâm quay LiDAR gá trên xe (`LidarMount`) ở tư thế xe cho trước. Đọc lại
  `scenario.obstacles` mỗi lần quét, nên vật cản chèn giữa lần chạy hiện ra. Ba móc cho test: `blocked` (LiDAR bị che:
  mọi tia NaN), `silent` (nguồn không quét nữa; người gọi kiểm cờ này), `extra_segments` (vật chỉ LiDAR thấy, không có
  trong sa bàn).
"""
from __future__ import annotations

import math

import numpy as np

from autopark.domain.types import Pose, Scenario

from .pose_config import LidarMount, SimLidarParams


def polygon_segments(points, closed: bool = True) -> np.ndarray:
    """Đoạn thẳng nối các đỉnh liên tiếp (khép kín khi `closed`), mảng (N, 4)."""
    pts = [tuple(float(v) for v in p) for p in points]
    if closed:
        pts = pts + [pts[0]]
    segs = [(a[0], a[1], b[0], b[1]) for a, b in zip(pts[:-1], pts[1:])]
    return np.array(segs, np.float64).reshape(-1, 4)


def box_segments(cx: float, cy: float, w: float, h: float, yaw: float = 0.0) -> np.ndarray:
    """Bốn cạnh của hình chữ nhật tâm (cx, cy), dài `w` theo trục x cục bộ, rộng `h`, xoay `yaw` (rad)."""
    c, s = math.cos(yaw), math.sin(yaw)
    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return polygon_segments([(cx + c * x - s * y, cy + s * x + c * y) for x, y in corners])


def room_outline(xmin: float, ymin: float, xmax: float, ymax: float, notch: float) -> np.ndarray:
    """Tường phòng chữ nhật có một khấc vuông cạnh `notch` ở góc (xmax, ymax): phòng không đối xứng 180°."""
    n = min(notch, 0.4 * (xmax - xmin), 0.4 * (ymax - ymin))
    return polygon_segments([(xmin, ymin), (xmax, ymin), (xmax, ymax - n), (xmax - n, ymax - n), (xmax - n, ymax),
                             (xmin, ymax)])


def scenario_segments(scenario: Scenario, *, walls_from_bounds: bool = True, room_margin_m: float = 1.0,
                      extra=()) -> np.ndarray:
    """Cảnh 2D của sa bàn (xem docstring mô-đun). `extra`: đoạn thêm (N, 4) hoặc danh sách đoạn."""
    b = scenario.bounds
    parts = []
    if walls_from_bounds:
        parts.append(polygon_segments([(b.xmin, b.ymin), (b.xmax, b.ymin), (b.xmax, b.ymax), (b.xmin, b.ymax)]))
    for obstacle in scenario.obstacles:
        parts.append(polygon_segments(obstacle.corners()))
    if room_margin_m > 0:
        m = room_margin_m
        parts.append(room_outline(b.xmin - m, b.ymin - m, b.xmax + m, b.ymax + m, max(0.3, 0.5 * m)))
    extra = np.asarray(extra, np.float64).reshape(-1, 4) if len(extra) else np.zeros((0, 4))
    parts.append(extra)
    return np.vstack(parts) if parts else np.zeros((0, 4))


def raycast(sensor_pose, segments, *, beams: int, fov_rad: float = 2 * math.pi, max_range_m: float = 12.0,
            min_range_m: float = 0.0, noise_m: float = 0.0, dropout: float = 0.0,
            rng: np.random.Generator | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(góc rad, tầm m) của một vòng quét từ `sensor_pose` = (x, y, yaw) trên các đoạn `segments` (N, 4). Vòng 360°:
    góc từ −π, bước 2π/beams; nhỏ hơn: trải đều trong ±fov/2. NaN = không phản hồi (ngoài [min, max], mất ngẫu nhiên)."""
    if fov_rad >= 2 * math.pi - 1e-9:
        angles = -math.pi + 2 * math.pi * np.arange(beams) / beams
    else:
        angles = np.linspace(-fov_rad / 2, fov_rad / 2, beams)
    segments = np.asarray(segments, np.float64).reshape(-1, 4)
    if len(segments) == 0:
        return angles, np.full(beams, np.nan)
    x, y, th = (float(v) for v in sensor_pose)
    dx, dy = np.cos(angles + th)[:, None], np.sin(angles + th)[:, None]
    ax, ay, bx, by = (segments[:, k][None, :] for k in range(4))
    ex, ey = bx - ax, by - ay
    wx, wy = ax - x, ay - y
    denom = dx * ey - dy * ex
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (wx * ey - wy * ex) / denom
        u = (wx * dy - wy * dx) / denom
    hit = (np.abs(denom) > 1e-12) & (t > 1e-6) & (u >= 0) & (u <= 1)
    ranges = np.where(hit, t, np.inf).min(axis=1)
    if rng is not None and noise_m:
        ranges = ranges + rng.normal(0.0, noise_m, beams)
    ranges[~np.isfinite(ranges) | (ranges > max_range_m) | (ranges < min_range_m)] = np.nan
    if rng is not None and dropout:
        ranges[rng.random(beams) < dropout] = np.nan
    return angles, ranges


class SyntheticScanner:
    """LiDAR MÔ PHỎNG gá trên xe: `scan(tư thế xe)` → (góc, tầm) trong hệ cảm biến."""

    def __init__(self, scenario: Scenario, params: SimLidarParams, mount: LidarMount, *,
                 rng: np.random.Generator | None = None):
        self.scenario = scenario
        self.params = params
        self.mount = mount
        self.rng = rng if rng is not None else np.random.default_rng(params.seed)
        self.blocked = False              # móc test: LiDAR bị che, mọi tia NaN
        self.silent = False               # móc test: nguồn ngừng quét (người gọi không gọi scan())
        self.extra_segments = np.zeros((0, 4))   # móc test: vật chỉ LiDAR thấy
        self.scans = 0

    def segments(self) -> np.ndarray:
        p = self.params
        return scenario_segments(self.scenario, walls_from_bounds=p.walls_from_bounds, room_margin_m=p.room_margin_m,
                                 extra=self.extra_segments)

    def scan_from_sensor(self, sensor: Pose) -> tuple[np.ndarray, np.ndarray]:
        p = self.params
        angles, ranges = raycast((sensor.x, sensor.y, sensor.yaw), self.segments(), beams=p.beams,
                                 fov_rad=math.radians(p.fov_deg), max_range_m=p.max_range_m,
                                 min_range_m=p.min_range_m, noise_m=p.noise_m, dropout=p.dropout, rng=self.rng)
        self.scans += 1
        if self.blocked:
            ranges = np.full(len(angles), np.nan)
        return angles, ranges

    def scan(self, vehicle_pose: Pose) -> tuple[np.ndarray, np.ndarray]:
        return self.scan_from_sensor(self.mount.sensor_pose(vehicle_pose))


def drive(start, commands, dt: float = 0.1) -> np.ndarray:
    """Quỹ đạo kiểu xe: mỗi lệnh (v m/s, ω rad/s, số bước dt). Trả mảng (N, 3), hàng đầu là `start`."""
    poses = [np.array(start, np.float64)]
    for v, w, steps in commands:
        for _ in range(int(steps)):
            x, y, th = poses[-1]
            if abs(w) < 1e-12:
                nxt = (x + v * dt * math.cos(th), y + v * dt * math.sin(th), th)
            else:
                r = v / w
                nxt = (x + r * (math.sin(th + w * dt) - math.sin(th)), y - r * (math.cos(th + w * dt) - math.cos(th)),
                       th + w * dt)
            poses.append(np.array(nxt))
    return np.array(poses)
