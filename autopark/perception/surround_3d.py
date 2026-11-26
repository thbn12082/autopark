"""Cảnh 3D quanh xe từ bốn camera (thêm 26/11/2026), chỉ để hiển thị, không dùng để lái.

```
4 ảnh camera
└── dán lên mặt hình bát quanh xe (đáy = sàn phẳng, thành cong dần lên)
    └── nhìn bát từ một camera ảo (xoay, phóng to)
        └── vẽ chồng: thân xe, điểm LiDAR, ô đỗ, đường đi
```

Cách tính: khi đổi góc nhìn, dựng một **bảng tra** (mỗi pixel màn hình → điểm trên bát → pixel của từng camera và trọng
số trộn). Mỗi khung hình chỉ cần `cv2.remap` theo bảng, vài mili giây. Camera lấy từ `surround_view.display_cameras`:
đủ ngoại tham đã đo thì dùng, không thì xem thử bằng gá giả định.

Giới hạn: mặt bát giả định mọi thứ nằm trên sàn hoặc trên thành bát, nên vật cao sát xe bị kéo méo (như camera 360° của ô
tô). Đúng tỷ lệ chỉ khi có ngoại tham đo bằng bốn tờ ChArUco.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

import cv2
import numpy as np

from . import bev
from .fisheye_calib import DEFAULT_SIZE

SKY_TOP = np.array([46, 33, 24], np.float32)        # BGR: nền trên (tối)
SKY_BOTTOM = np.array([24, 19, 14], np.float32)
BODY_HEIGHT_M = 0.11
LIDAR_HEIGHT_M = 0.16                               # khi cấu hình gá chưa ghi chiều cao


@dataclass(frozen=True)
class Bowl:
    """Mặt bát quanh tâm thân xe: sàn phẳng tới `floor_radius_m`, rồi cao dần z = curvature·(r − floor_radius)²."""

    center_xy: tuple[float, float] = (0.1, 0.0)
    floor_radius_m: float = 0.9
    curvature: float = 0.9
    rim_radius_m: float = 3.0

    def height(self, r: np.ndarray) -> np.ndarray:
        extra = np.clip(r - self.floor_radius_m, 0.0, None)
        return self.curvature * extra * extra


@dataclass(frozen=True)
class View:
    """Camera ảo nhìn về `target`: phương vị (0 = đứng trước xe, 90 = bên trái, 180 = sau xe), góc ngẩng, khoảng cách."""

    azimuth_deg: float = 210.0
    elevation_deg: float = 32.0
    distance_m: float = 1.5
    fov_deg: float = 60.0
    width: int = 960
    height: int = 600
    target: tuple[float, float, float] = (0.1, 0.0, 0.03)

    def clamped(self) -> "View":
        return replace(self, azimuth_deg=self.azimuth_deg % 360.0,
                       elevation_deg=min(max(self.elevation_deg, 8.0), 89.5),
                       distance_m=min(max(self.distance_m, 0.6), 2.6))

    def scaled(self, factor: float) -> "View":
        return replace(self, width=max(32, int(self.width * factor)), height=max(20, int(self.height * factor)))

    def basis(self):
        """(vị trí camera, trục phải, trục xuống, trục nhìn) trong hệ xe."""
        az, el = math.radians(self.azimuth_deg), math.radians(self.elevation_deg)
        target = np.asarray(self.target, np.float64)
        position = target + self.distance_m * np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az),
                                                        math.sin(el)])
        forward = target - position
        forward /= np.linalg.norm(forward)
        up = np.array([0.0, 0.0, 1.0]) if abs(forward[2]) < 0.98 else np.array([math.cos(az + math.pi),
                                                                               math.sin(az + math.pi), 0.0])
        right = np.cross(forward, up)
        right /= np.linalg.norm(right)
        down = np.cross(forward, right)
        return position, right, down, forward

    @property
    def focal_px(self) -> float:
        return (self.width / 2) / math.tan(math.radians(self.fov_deg) / 2)

    def project(self, points: np.ndarray):
        """Điểm (N, 3) hệ xe → (u, v, nhìn thấy?) trên ảnh của camera ảo."""
        position, right, down, forward = self.basis()
        rel = np.asarray(points, np.float64).reshape(-1, 3) - position
        z = rel @ forward
        ok = z > 1e-3
        with np.errstate(divide="ignore", invalid="ignore"):
            u = self.width / 2 - 0.5 + self.focal_px * (rel @ right) / z
            v = self.height / 2 - 0.5 + self.focal_px * (rel @ down) / z
        return u, v, ok


PRESETS: dict[str, tuple[str, View]] = {
    "sau_trai": ("Sau trái", View(azimuth_deg=150.0)),
    "sau": ("Phía sau", View(azimuth_deg=180.0)),
    "sau_phai": ("Sau phải", View(azimuth_deg=210.0)),
    "truoc": ("Phía trước", View(azimuth_deg=0.0, elevation_deg=28.0)),
    "tren": ("Từ trên", View(azimuth_deg=180.0, elevation_deg=89.5, distance_m=2.2)),
}


def _ray_hits(view: View, bowl: Bowl, width: int, height: int, steps: int = 32, refine: int = 8):
    position, right, down, forward = view.basis()
    f = view.focal_px * width / view.width
    us = (np.arange(width, dtype=np.float32) - (width / 2 - 0.5)) / f
    vs = (np.arange(height, dtype=np.float32) - (height / 2 - 0.5)) / f
    gu, gv = np.meshgrid(us, vs)
    rays = (forward[None, None, :] + gu[..., None] * right[None, None, :] + gv[..., None] * down[None, None, :])
    rays = (rays / np.linalg.norm(rays, axis=2, keepdims=True)).astype(np.float32).reshape(-1, 3)
    origin = position.astype(np.float32)
    cx, cy = bowl.center_xy
    points = np.zeros_like(rays)
    hit = np.zeros(len(rays), bool)

    # 1) Tia rơi xuống sàn phẳng (trong bán kính sàn): giao điểm tính thẳng.
    with np.errstate(divide="ignore", invalid="ignore"):
        t_floor = np.where(rays[:, 2] < -1e-6, -origin[2] / rays[:, 2], np.inf)
    p_floor = origin + np.where(np.isfinite(t_floor), t_floor, 0.0)[:, None] * rays
    floor = np.isfinite(t_floor) & (np.hypot(p_floor[:, 0] - cx, p_floor[:, 1] - cy) <= bowl.floor_radius_m)
    points[floor] = p_floor[floor]
    points[floor, 2] = 0.0
    hit[floor] = True

    # 2) Tia còn lại: dò từng bước tới khi chạm thành bát rồi chia đôi cho chính xác.
    rest = np.flatnonzero(~floor)
    if len(rest):
        d = rays[rest]

        def surface(t):
            q = origin + t[:, None] * d
            r = np.hypot(q[:, 0] - cx, q[:, 1] - cy)
            return q[:, 2] - bowl.height(r)

        far = 2.0 * (view.distance_m + bowl.rim_radius_m)
        lo = np.zeros(len(rest), np.float32)
        hi = np.zeros(len(rest), np.float32)
        found = np.zeros(len(rest), bool)
        previous = 0.0
        for t in np.linspace(0.0, far, steps + 1, dtype=np.float32)[1:]:
            crossed = (surface(np.full(len(rest), t, np.float32)) <= 0) & ~found
            lo[crossed], hi[crossed] = previous, t
            found |= crossed
            previous = t
        for _ in range(refine):
            mid = 0.5 * (lo + hi)
            below = surface(mid) <= 0
            hi = np.where(below, mid, hi)
            lo = np.where(below, lo, mid)
        q = origin + (0.5 * (lo + hi))[:, None] * d
        rq = np.hypot(q[:, 0] - cx, q[:, 1] - cy)
        q[:, 2] = bowl.height(rq)                      # đặt đúng lên mặt bát (bỏ sai số chia đôi)
        ok = found & (rq <= bowl.rim_radius_m)
        points[rest[ok]] = q[ok]
        hit[rest[ok]] = True
    return points.reshape(height, width, 3), hit.reshape(height, width)


def bowl_points(view: View, bowl: Bowl, subsample: int = 2):
    """Giao tia của từng pixel camera ảo với mặt bát: điểm (H, W, 3) hệ xe và mặt nạ trúng bát.

    Tính ở độ phân giải giảm `subsample` lần rồi nội suy điểm lên (mặt bát trơn nên sai số nhỏ, chỉ ở mép bát)."""
    if subsample <= 1:
        return _ray_hits(view, bowl, view.width, view.height)
    w, h = max(8, view.width // subsample), max(8, view.height // subsample)
    points, hit = _ray_hits(view, bowl, w, h)
    big = cv2.resize(points, (view.width, view.height), interpolation=cv2.INTER_LINEAR)
    big_hit = cv2.resize(hit.astype(np.uint8), (view.width, view.height), interpolation=cv2.INTER_NEAREST) > 0
    return big, big_hit


@dataclass
class _CameraMap:
    map_pixels: np.ndarray
    map_fractions: np.ndarray
    weights: np.ndarray


def _camera_map(camera, points: np.ndarray, usable: np.ndarray, preview: bool) -> _CameraMap:
    calibration = camera.calibration
    h, w = usable.shape
    flat = points.reshape(-1, 3).astype(np.float64)
    u, v, valid = calibration.intrinsics.project(calibration.extrinsics.vehicle_to_camera(flat))
    u, v, valid = (a.reshape(h, w) for a in (u, v, valid))
    mount = np.asarray(calibration.extrinsics.translation)
    dx, dy = points[..., 0] - mount[0], points[..., 1] - mount[1]
    valid &= usable
    axis = calibration.extrinsics.rotation[:, 2]
    rel = points - mount
    valid &= (rel @ axis) > 0 if preview else valid           # gá giả định: không nhìn xuyên thân xe
    map_x = np.where(valid, u, -1).astype(np.float32)
    map_y = np.where(valid, v, -1).astype(np.float32)
    if camera.roi is not None:
        roi = (camera.roi > 0).astype(np.uint8) * 255
        valid &= cv2.remap(roi, map_x, map_y, cv2.INTER_NEAREST) == 255
    width, height = DEFAULT_SIZE
    edge = np.minimum.reduce((u, v, width - 1 - u, height - 1 - v))
    weights = np.clip(edge / 64, 0.04, 1) ** 2 / (1 + (dx * dx + dy * dy) / 0.16)
    maps = cv2.convertMaps(map_x, map_y, cv2.CV_16SC2)
    return _CameraMap(maps[0], maps[1], np.where(valid, weights, 0).astype(np.float32))


@dataclass(frozen=True)
class Overlays:
    """Những gì vẽ chồng lên cảnh, đều trong hệ xe (gốc tâm trục sau, x trước, y trái)."""

    lidar_xy: np.ndarray | None = None                 # (N, 2) điểm LiDAR
    lidar_z: float = LIDAR_HEIGHT_M
    slots: tuple = ()                                  # mỗi ô: danh sách góc (x, y) trên sàn
    path_xy: np.ndarray | None = None                  # (N, 2) đường đi trên sàn


class Surround3DRenderer:
    """Dựng cảnh 3D: `set_view` dựng lại bảng tra, `render` ghép một khung hình."""

    def __init__(self, cameras: dict | None = None, *, is_preview: bool | None = None, notice: str | None = None,
                 bowl: Bowl | None = None, body: bev.EgoBox | None = None, view: View | None = None):
        from .surround_view import BODY, display_cameras
        if cameras is None:
            cameras, preview, message = display_cameras()
            is_preview = preview if is_preview is None else is_preview
            notice = message if notice is None else notice
        self.cameras = cameras
        self.is_preview = bool(is_preview)
        self.notice = notice or ""
        self.body = body or BODY
        center = ((self.body.x_min + self.body.x_max) / 2, (self.body.y_min + self.body.y_max) / 2)
        self.bowl = bowl or Bowl(center_xy=center)
        self.view: View | None = None
        self._maps: dict[int, _CameraMap] = {}
        self._background: np.ndarray | None = None
        self.set_view(view or PRESETS["sau_phai"][1])

    # ------------------------------------------------------------------ bảng tra
    def set_view(self, view: View) -> None:
        view = view.clamped()
        center = (self.bowl.center_xy[0], self.bowl.center_xy[1], view.target[2])
        view = replace(view, target=center)
        points, hit = bowl_points(view, self.bowl)
        margin = 0.01
        under_body = ((points[..., 0] >= self.body.x_min - margin) & (points[..., 0] <= self.body.x_max + margin)
                      & (points[..., 1] >= self.body.y_min - margin) & (points[..., 1] <= self.body.y_max + margin)
                      & (points[..., 2] < 0.02))
        usable = hit & ~under_body
        self._maps = {port: _camera_map(cam, points, usable, self.is_preview) for port, cam in self.cameras.items()}
        rows = np.linspace(0.0, 1.0, view.height, dtype=np.float32)[:, None, None]
        sky = SKY_TOP * (1 - rows) + SKY_BOTTOM * rows
        background = np.broadcast_to(sky, (view.height, view.width, 3)).copy()
        floor = hit & (points[..., 2] < 1e-3)
        background[hit & ~floor] = (36, 30, 26)                          # thành bát chưa có ảnh
        background[floor] = (30, 26, 22)                                 # sàn chưa có ảnh
        self._background = background.astype(np.uint8)
        self._floor_grid = self._grid_lines(view)
        self.view = view

    def _grid_lines(self, view: View) -> list:
        """Lưới 10 cm trên sàn (đường mờ) để thấy tỷ lệ khi chưa có ảnh."""
        lines = []
        cx, cy = self.bowl.center_xy
        r = self.bowl.floor_radius_m
        for k in np.arange(-r, r + 1e-9, 0.1):
            half = math.sqrt(max(r * r - k * k, 0.0))
            for a, b in (((cx + k, cy - half, 0.0), (cx + k, cy + half, 0.0)),
                         ((cx - half, cy + k, 0.0), (cx + half, cy + k, 0.0))):
                seg = np.linspace(a, b, 24)
                u, v, ok = view.project(seg)
                if ok.all():
                    lines.append(np.column_stack([u, v]).astype(np.int32))
        return lines

    # ------------------------------------------------------------------ khung hình
    def render(self, frames: dict[int, np.ndarray], overlays: Overlays | None = None) -> np.ndarray:
        canvas = self._background.copy()
        color = np.zeros(canvas.shape, np.float32)
        total = np.zeros(canvas.shape[:2], np.float32)
        width, height = DEFAULT_SIZE
        for port, cmap in self._maps.items():
            frame = frames.get(port)
            if frame is None or frame.shape != (height, width, 3) or frame.dtype != np.uint8:
                continue
            image = cv2.remap(frame, cmap.map_pixels, cmap.map_fractions, cv2.INTER_LINEAR)
            color += image * cmap.weights[..., None]
            total += cmap.weights
        visible = total > 0
        if not visible.any():
            cv2.polylines(canvas, self._floor_grid, False, (58, 50, 44), 1, cv2.LINE_AA)
        canvas[visible] = np.rint(color[visible] / total[visible, None]).astype(np.uint8)
        self._draw_overlays(canvas, overlays or Overlays())
        self._draw_body(canvas)
        return canvas

    # ------------------------------------------------------------------ vẽ chồng
    def _floor_polyline(self, canvas, xy, color, thickness, closed):
        xy = np.asarray(xy, np.float64).reshape(-1, 2)
        if len(xy) < 2:
            return
        dense = []
        loop = np.vstack([xy, xy[:1]]) if closed else xy
        for a, b in zip(loop, loop[1:]):
            dense.append(np.linspace(a, b, 12, endpoint=False))
        dense.append(loop[-1:])
        pts = np.vstack(dense)
        u, v, ok = self.view.project(np.column_stack([pts, np.full(len(pts), 0.002)]))
        if ok.all():
            cv2.polylines(canvas, [np.column_stack([u, v]).astype(np.int32)], False, color, thickness, cv2.LINE_AA)

    def _draw_overlays(self, canvas, overlays: Overlays) -> None:
        for corners in overlays.slots:
            self._floor_polyline(canvas, corners, (214, 240, 140), 2, True)
        if overlays.path_xy is not None:
            self._floor_polyline(canvas, overlays.path_xy, (107, 183, 239), 2, False)
        if overlays.lidar_xy is not None and len(overlays.lidar_xy):
            xy = np.asarray(overlays.lidar_xy, np.float64).reshape(-1, 2)
            pts = np.column_stack([xy, np.full(len(xy), overlays.lidar_z)])
            u, v, ok = self.view.project(pts)
            inside = ok & (u >= 0) & (u < canvas.shape[1]) & (v >= 0) & (v < canvas.shape[0])
            for x, y in zip(u[inside].astype(int), v[inside].astype(int)):
                cv2.circle(canvas, (x, y), 2, (102, 209, 255), -1, cv2.LINE_AA)

    def _draw_body(self, canvas) -> None:
        b, h = self.body, BODY_HEIGHT_M
        corners = np.array([[x, y, z] for z in (0.0, h) for x, y in
                            ((b.x_min, b.y_min), (b.x_max, b.y_min), (b.x_max, b.y_max), (b.x_min, b.y_max))])
        u, v, ok = self.view.project(corners)
        if not ok.all():
            return
        pix = np.column_stack([u, v]).astype(np.int32)
        position = self.view.basis()[0]
        faces = [((0, 1, 2, 3), (40, 34, 30)), ((4, 5, 6, 7), (212, 196, 176)),
                 ((0, 1, 5, 4), (150, 132, 112)), ((1, 2, 6, 5), (176, 158, 136)),
                 ((2, 3, 7, 6), (150, 132, 112)), ((3, 0, 4, 7), (120, 104, 88))]
        depth = [np.linalg.norm(corners[list(f)].mean(axis=0) - position) for f, _ in faces]
        for i in np.argsort(depth)[::-1]:
            idx, color = faces[i]
            cv2.fillConvexPoly(canvas, pix[list(idx)], color, cv2.LINE_AA)
            cv2.polylines(canvas, [pix[list(idx)]], True, (235, 228, 214), 1, cv2.LINE_AA)
        # mũi tên chỉ đầu xe trên nóc
        tail = np.array([[b.x_min + 0.06, 0.0, h + 0.001], [b.x_max - 0.03, 0.0, h + 0.001]])
        tu, tv, tok = self.view.project(tail)
        if tok.all():
            cv2.arrowedLine(canvas, (int(tu[0]), int(tv[0])), (int(tu[1]), int(tv[1])), (36, 30, 26), 2,
                            cv2.LINE_AA, tipLength=0.3)


# ---------------------------------------------------------------------------------------------- cảnh mẫu tổng hợp
@dataclass(frozen=True)
class DemoScene:
    """Sa bàn mẫu: sàn kẻ ô 10 cm, vạch ô đỗ trắng, vài hộp màu (như các xe đang đỗ)."""

    boxes: tuple = (
        (bev.SyntheticBox(-0.25, 0.05, 0.42, 0.56, 0.12), (60, 60, 200)),
        (bev.SyntheticBox(0.25, 0.55, 0.42, 0.56, 0.12), (200, 120, 50)),
        (bev.SyntheticBox(0.55, 0.85, -0.62, -0.48, 0.12), (60, 170, 90)),
        (bev.SyntheticBox(-0.70, -0.55, -0.30, 0.30, 0.20), (150, 150, 160)),
    )
    lines: tuple = ((0.075, 0.30, 0.175, 0.80), (0.075, 0.30, 0.225, 0.80))    # (x0, y0, x1, y1) mép ô đỗ trống
    marker: tuple = (0.55, -0.05, 0.65, 0.05)                                   # ô đỏ trên sàn (kiểm vị trí)


def _floor_color(x, y, scene: DemoScene) -> np.ndarray:
    checker = ((np.floor(x / 0.1) + np.floor(y / 0.1)) % 2).astype(bool)
    color = np.where(checker[..., None], np.array([92, 98, 104], np.float32), np.array([70, 76, 82], np.float32))
    for x0, y0, x1, y1 in scene.lines:                                          # vạch trắng dày 1 cm dọc theo y
        for xl in (x0, x1):
            on = (np.abs(x - xl) < 0.006) & (y >= y0) & (y <= y1)
            color[on] = (235, 235, 235)
        on = (np.abs(y - y0) < 0.006) & (x >= x0) & (x <= x1)
        color[on] = (235, 235, 235)
    x0, y0, x1, y1 = scene.marker
    color[(x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)] = (40, 40, 230)
    return color


def demo_frames(cameras: dict, scene: DemoScene | None = None, far_m: float = 6.0) -> dict[int, np.ndarray]:
    """Ảnh giả của bốn camera nhìn sa bàn mẫu (tia qua từng pixel → hộp hay sàn), để xem thử khi chưa có Pi."""
    scene = scene or DemoScene()
    out = {}
    for port, camera in cameras.items():
        calib = camera.calibration
        intr = calib.intrinsics
        u, v = np.meshgrid(np.arange(intr.width, dtype=np.float64), np.arange(intr.height, dtype=np.float64))
        rays = intr.unproject(u.ravel(), v.ravel()) @ calib.extrinsics.rotation.T
        o = np.asarray(calib.extrinsics.translation, np.float64)
        ok = np.all(np.isfinite(rays), axis=1)
        d = np.where(ok[:, None], rays, np.array([0.0, 0.0, 1.0]))
        with np.errstate(divide="ignore", invalid="ignore"):
            t_floor = np.where(d[:, 2] < -1e-9, -o[2] / d[:, 2], np.inf)
        t_floor = np.where(t_floor <= far_m, t_floor, np.inf)
        img = np.empty((len(d), 3), np.float32)
        img[:] = (60, 48, 40)                                                  # xa / trời
        floor = np.isfinite(t_floor)
        p = o + t_floor[floor, None] * d[floor]
        img[floor] = _floor_color(p[:, 0], p[:, 1], scene)
        t_best = np.where(floor, t_floor, np.inf)
        for box, color in scene.boxes:
            t_box = bev._box_hit(o, d, box)
            nearer = t_box < t_best
            if not nearer.any():
                continue
            q = o + t_box[nearer, None] * d[nearer]
            top = np.abs(q[:, 2] - box.height) < 1e-3
            shade = np.where(top, 1.15, 0.8 + 0.2 * (np.abs(q[:, 0] - box.x_min) < 1e-3))
            img[nearer] = np.clip(np.array(color, np.float32)[None, :] * shade[:, None], 0, 255)
            t_best = np.where(nearer, t_box, t_best)
        img[~ok] = (0, 0, 0)
        out[port] = img.reshape(intr.height, intr.width, 3).astype(np.uint8)
    return out


def scan_to_vehicle(scan, mount) -> np.ndarray:
    """Bản quét LiDAR (góc theo quy ước dự án) → điểm (N, 2) hệ xe theo gá `mount` (x_m, y_m, yaw_deg)."""
    angles = np.asarray(scan.angles_rad, np.float64)
    ranges = np.asarray(scan.ranges_m, np.float64)
    good = np.isfinite(ranges) & (ranges > 0.02)
    a = angles[good] + math.radians(mount.yaw_deg)
    r = ranges[good]
    return np.column_stack([mount.x_m + r * np.cos(a), mount.y_m + r * np.sin(a)])
