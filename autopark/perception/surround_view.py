"""Colour view of the ground around the stationary vehicle, for display only."""

from __future__ import annotations

from dataclasses import dataclass, replace

import cv2
import numpy as np

import time

from . import bev, bev_inpaint, ground_memory
from .fisheye_calib import LIVE_SIZE


_PORTS = (1, 2, 3, 4)
_CANVAS_SIZE = 480
# Vùng hiển thị như màn hình quanh xe của ô tô: chừng một chiều dài xe quanh thân (29/11/2026; trước đó 1,6 m làm vật xa bị
# kéo thành vệt dài). Xa hơn thì mặt sàn bị chiếu rất xiên, hình chiếu không còn giúp nhìn.
_GROUND_WIDTH_M = 1.0
_ICON_MARGIN_M = 0.012           # hình xe lớn hơn thân thật chút, che dải sát thân mà không camera nào thấy
# Camera ≈ 98° gắn ở mép xe: sát mỗi góc xe có một hình nêm không camera nào thấy (hai camera chỉ chồng nhau từ
# ≈ 0,6 m ra). Vùng đó được tô bằng màu loang từ hai bên (lấp kiểu kim tự tháp) thay vì để đen; KHÔNG phải hình thật.
_GAIN_LIMITS = (0.75, 1.35)      # cân độ sáng/màu giữa các camera: giới hạn hệ số mỗi kênh
_GAIN_POWER = 0.6                # chỉ kéo một phần về mức chung (cảnh hai bên xe có thể khác màu thật)
_GAIN_RING_M = 0.2               # đo màu trên dải sàn sát thân xe, nơi các camera cùng nhìn một mặt sàn
_GAIN_SMOOTH = 0.25              # trung bình trượt theo khung để hệ số không nhấp nháy
_BODY = bev.EgoBox(-0.047, 0.247, -0.080, 0.080)
_CENTER_X = (_BODY.x_min + _BODY.x_max) / 2
# LiDAR canh vùng AI vẽ (29/11/2026): gá C1 ĐO trên xe (README "Vị trí gá LiDAR C1 đo thực": x 180, y +30, z 160 mm);
# hướng chưa đo nên lấy 0° và nới vùng cảnh báo `_LIDAR_GUARD_M`. configs/dinh_vi_lidar_v0.json vẫn giữ gá giả định cho
# định vị (có kiểm tiên quyết riêng), không dùng ở đây.
LIDAR_MOUNT_XY = (0.18, 0.03)
LIDAR_YAW_DEG = 0.0
_LIDAR_GUARD_M = 0.04            # nới quanh mỗi điểm vật: sai hướng gá chưa đo + bề dày vật
_LIDAR_SELF_M = 0.03             # bỏ điểm sát thân xe (chạm gá camera, dây…)
_WARN_COLOR = np.array([40, 140, 255], np.float32)    # BGR cam
_WARN_ALPHA = 0.55
_MEASURED_RIG = bev.DEFAULT_EXTRINSICS.with_name("camera_rig_extrinsics_v1.json")
_ROI_DIR = bev.PROJECT / "configs/roi/rig_v1"


@dataclass(frozen=True)
class _View:
    map_pixels: np.ndarray
    map_fractions: np.ndarray
    weights: np.ndarray


def _measured_cameras(extrinsics_path, calibration_dir, roi_dir):
    sizes = dict.fromkeys(_PORTS, LIVE_SIZE)
    try:
        cameras, _, _ = bev.load_rig(extrinsics_path, calibration_dir, sizes, roi_dir=roi_dir)
    except (bev.RigConfigError, OSError, ValueError, TypeError, AttributeError, cv2.error):
        return {}
    accepted = {
        port: camera for port in _PORTS if (camera := cameras.get(f"p{port}")) is not None
        and camera.extrinsics_measured and camera.acceptance_all_pass is True and not camera.synthetic
    }
    return accepted if len(accepted) == len(_PORTS) else {}


def _preview_cameras():
    nominal, _ = bev.synthetic_rig(width=LIVE_SIZE[0], height=LIVE_SIZE[1])
    mounts = ((_BODY.x_max, 0), (_BODY.x_min, 0), (_CENTER_X, _BODY.y_max), (_CENTER_X, _BODY.y_min))
    cameras = {}
    for port, (x, y) in zip(_PORTS, mounts):
        camera = nominal.get(f"p{port}")
        if camera is not None:
            calibration = camera.calibration
            pose = replace(calibration.extrinsics, translation=(x, y, calibration.extrinsics.translation[2]))
            cameras[port] = replace(camera, calibration=replace(calibration, extrinsics=pose))
    return cameras


def _view_map(camera, x, y, ground, outside_body, preview):
    calibration = camera.calibration
    u, v, valid = calibration.ground_to_pixel(ground)
    u, v, valid = (values.reshape(x.shape) for values in (u, v, valid))
    x_mount, y_mount, _ = calibration.extrinsics.translation
    dx, dy = x - x_mount, y - y_mount
    valid &= outside_body & (dx * dx + dy * dy <= bev.RIG_MAX_RANGE ** 2)
    if preview:
        # The preview can see out from its mount; do not look back through the chassis.
        optical_axis = calibration.extrinsics.rotation[:, 2]
        valid &= dx * optical_axis[0] + dy * optical_axis[1] >= 0
    map_x = np.where(valid, u, -1).astype(np.float32)
    map_y = np.where(valid, v, -1).astype(np.float32)
    if camera.roi is not None:
        roi = (camera.roi > 0).astype(np.uint8) * 255
        valid &= cv2.remap(roi, map_x, map_y, cv2.INTER_LINEAR) == 255

    width, height = LIVE_SIZE
    edge = np.minimum.reduce((u, v, width - 1 - u, height - 1 - v))
    # Prefer the centre of a lens and the closer of two views in the overlap.
    weights = np.clip(edge / 64, 0.04, 1) ** 2 / (1 + (dx * dx + dy * dy) / 0.16)
    maps = cv2.convertMaps(map_x, map_y, cv2.CV_16SC2)
    return _View(*maps, np.where(valid, weights, 0).astype(np.float32))


BODY = _BODY                     # hộp thân xe đo thật (hệ xe, gốc tâm trục sau), dùng chung với khung 3D


def display_cameras(*, extrinsics_path=_MEASURED_RIG, calibration_dir=bev.DEFAULT_CALIBRATION_DIR,
                    roi_dir=_ROI_DIR) -> tuple[dict, bool, str]:
    """Bốn camera để hiển thị: (camera theo cổng, đang xem thử?, lời báo).

    Đủ bốn camera đã đo ngoại tham và đạt nội tham thì dùng chúng. Không thì xem thử bằng gá giả định ở mép thân xe."""
    cameras = _measured_cameras(extrinsics_path, calibration_dir, roi_dir)
    if cameras:
        return cameras, False, "Hình chiếu mặt sàn đã hiệu chuẩn. Vật cao có thể bị méo."
    try:
        return _preview_cameras(), True, "Hình chiếu ước lượng, chưa hiệu chuẩn đủ bốn camera."
    except (bev.RigConfigError, ValueError, TypeError, AttributeError):
        return {}, True, "Không đọc được cấu hình hình chiếu."


class SurroundViewRenderer:
    """Ảnh mặt sàn quanh xe nhìn từ trên, ghép từ bốn camera (chỉ để xem).

    Giống màn hình 360° trên ô tô: vùng hiển thị chừng một chiều dài xe quanh thân; hai camera trộn mềm ở chỗ chồng nhau
    (trọng số giảm dần về mép ảnh); độ sáng và màu từng camera được kéo về cùng một mức; khe hẹp không camera nào thấy
    được lấp từ hai bên; giữa là hình xe nhìn từ trên. Cân màu và lấp khe chỉ bật khi đã hiệu chuẩn đủ bốn camera.

    Vùng không camera nào thấy được AI (LaMa, `bev_inpaint`) vẽ tiếp mặt sàn khi có GPU; trong lúc chờ hoặc khi không có
    AI thì tô màu loang. Vùng tô như vậy KHÔNG phải hình thật (dòng báo luôn nói rõ; `mark_ai` vẽ thêm sọc mảnh lên đó,
    tab BEV có ô bật/tắt), ảnh này chỉ để người xem.
    `ai_fill_fn(ảnh, mặt nạ) → ảnh` thay mô hình (cho test); `ai_fill=False` tắt AI."""

    def __init__(self, *, extrinsics_path=_MEASURED_RIG, calibration_dir=bev.DEFAULT_CALIBRATION_DIR,
                 roi_dir=_ROI_DIR, ai_fill: bool = True, ai_fill_fn=None):
        cameras, self.is_preview, self._base_notice = display_cameras(
            extrinsics_path=extrinsics_path, calibration_dir=calibration_dir, roi_dir=roi_dir)
        self.notice = self._base_notice
        self._ai_enabled = ai_fill
        self._ai_fill_fn = ai_fill_fn
        self._filler = None
        self.mark_ai = True                    # sọc mảnh trên vùng AI/màu loang; tab BEV cho bật/tắt
        self.lidar_blocked_px = 0

        self._res = _GROUND_WIDTH_M / _CANVAS_SIZE
        offset = (np.arange(_CANVAS_SIZE) + 0.5 - _CANVAS_SIZE / 2) * self._res
        y, x = np.meshgrid(-offset, _CENTER_X - offset)
        icon = bev.EgoBox(_BODY.x_min - _ICON_MARGIN_M, _BODY.x_max + _ICON_MARGIN_M,
                          _BODY.y_min - _ICON_MARGIN_M, _BODY.y_max + _ICON_MARGIN_M)
        hidden = icon.contains(x, y)
        ground = np.column_stack((x.ravel(), y.ravel()))
        self._views = {port: _view_map(camera, x, y, ground, ~hidden, self.is_preview)
                       for port, camera in cameras.items()}
        ring = (np.maximum(np.maximum(_BODY.x_min - x, x - _BODY.x_max), 0) ** 2
                + np.maximum(np.maximum(_BODY.y_min - y, y - _BODY.y_max), 0) ** 2) <= _GAIN_RING_M ** 2
        self._samples = {port: np.flatnonzero(((view.weights > 0) & ring).ravel())[::5]
                         for port, view in self._views.items()}
        self._gains: dict[int, np.ndarray] = {}
        self._background = np.full((*x.shape, 3), (19, 16, 14), dtype=np.uint8)
        plain = self._background.copy()
        _draw_car(self._background, self._pixel, icon)
        self._car_mask = np.any(self._background != plain, axis=2)
        self._hidden = hidden
        covered = np.zeros(x.shape, bool)
        for view in self._views.values():
            covered |= view.weights > 0
        self._gaps = ~covered                     # cả dải dưới hình xe: lấp rồi vẽ hình xe đè lên
        self._fill_gaps = not self.is_preview and bool(self._gaps.any())
        self._feather = bev_inpaint.feather_alpha(self._gaps)
        self._memory = ground_memory.GroundMemory(_CANVAS_SIZE, self._res, _CENTER_X)
        self._memory_epoch = None
        self.memory_fraction = 0.0             # phần vùng mù đang lấy từ ảnh nhớ (ảnh thật cũ) ở khung gần nhất
        self._visible_real = None

    def _pixel(self, x_m: float, y_m: float) -> tuple[float, float]:
        """Điểm hệ xe (m) → (cột, hàng) trên ảnh; x hướng lên trên, y sang trái."""
        return ((-y_m) / self._res + _CANVAS_SIZE / 2 - 0.5, (_CENTER_X - x_m) / self._res + _CANVAS_SIZE / 2 - 0.5)

    def _balance(self, images: dict[int, np.ndarray]) -> dict[int, np.ndarray]:
        """Kéo trung bình từng kênh màu của mỗi camera (trên vùng nó hiện) về trung bình chung của các camera."""
        means = {}
        for port, image in images.items():
            idx = self._samples.get(port)
            if idx is not None and idx.size >= 50:
                means[port] = image.reshape(-1, 3)[idx].mean(axis=0) + 1.0
        if len(means) < 2:
            return images
        target = np.mean(list(means.values()), axis=0)
        out = {}
        for port, image in images.items():
            if port not in means:
                out[port] = image
                continue
            gain = np.clip((target / means[port]) ** _GAIN_POWER, *_GAIN_LIMITS)
            prev = self._gains.get(port)
            gain = gain if prev is None else prev + _GAIN_SMOOTH * (gain - prev)
            self._gains[port] = gain
            out[port] = image * gain.astype(np.float32)
        return out

    def render(self, frames: dict[int, np.ndarray], lidar_xy: np.ndarray | None = None,
               lidar_pose=None, pose_epoch: int | None = None) -> np.ndarray:
        """Render the available 1280x720 BGR sources on a fresh 480x480 BGR canvas.

        `lidar_xy`: điểm LiDAR (N, 2) hệ xe của vòng quét còn mới (`lidar_points`). Chỗ có vật trong vùng AI/màu loang tô
        thì không vẽ sàn mà tô cam cảnh báo."""
        canvas = self._background.copy()
        if not frames:
            return canvas
        width, height = LIVE_SIZE
        images = {}
        for port, view in self._views.items():
            frame = frames.get(port)
            if frame is None or frame.shape != (height, width, 3) or frame.dtype != np.uint8:
                continue
            images[port] = cv2.remap(frame, view.map_pixels, view.map_fractions, cv2.INTER_LINEAR).astype(np.float32)
        if not images:
            return canvas
        if not self.is_preview:
            images = self._balance(images)
        color = np.zeros(canvas.shape, dtype=np.float32)
        total = np.zeros(canvas.shape[:2], dtype=np.float32)
        for port, image in images.items():
            weights = self._views[port].weights
            color += image * weights[:, :, None]
            total += weights
        visible = total > 0
        mixed = color / np.maximum(total, 1e-6)[:, :, None]
        out = (np.where(visible[:, :, None], mixed, canvas) + 0.5).clip(0, 255).astype(np.uint8)   # làm tròn
        if self._fill_gaps and len(images) == len(self._views):
            ai = self._ai_result(out)
            if ai is not None:
                filled = ai
            else:
                # lấp ở nửa độ phân giải: màu loang vốn mờ, nhanh gấp ≈ 4 lần
                small = cv2.resize(out, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA).astype(np.float32)
                known = cv2.resize((visible & ~self._hidden).astype(np.float32), None, fx=0.5, fy=0.5,
                                   interpolation=cv2.INTER_AREA)
                filled = cv2.resize(_push_pull(small, (known > 0.99).astype(np.float32), levels=6),
                                    (out.shape[1], out.shape[0]), interpolation=cv2.INTER_LINEAR)
                filled = filled.clip(0, 255).astype(np.uint8)
            real = out
            alpha = self._feather[:, :, None]
            out = (out * (1.0 - alpha) + filled * alpha + 0.5).astype(np.uint8)
            remembered = self._remember(real, visible, lidar_pose, pose_epoch)
            painted = self._gaps
            if remembered is not None:
                image, mem = remembered
                soft = cv2.GaussianBlur(mem.astype(np.float32), (5, 5), 0)[:, :, None]
                out = (out * (1.0 - soft) + image * soft + 0.5).astype(np.uint8)
                painted = self._gaps & ~mem
                self.notice = f"{self.notice} Ảnh nhớ khi xe chạy: {100 * self.memory_fraction:.0f}% vùng mù là ảnh thật cũ."
            if self.mark_ai:
                out = bev_inpaint.mark_ai_region(out, painted & ~self._car_mask)
            out = self._lidar_guard(out, lidar_xy)
            out[self._car_mask] = self._background[self._car_mask]
        return out

    def _remember(self, real: np.ndarray, visible: np.ndarray, lidar_pose, pose_epoch):
        """Dán phần camera thật thấy vào ảnh nhớ mặt sàn rồi đọc lại cho vùng mù (None khi chưa có tư thế LiDAR)."""
        self.memory_fraction = 0.0
        if lidar_pose is None:
            return None
        if pose_epoch != self._memory_epoch:              # odometry khởi động lại: hệ tọa độ mới, ảnh nhớ cũ bỏ
            self._memory.reset()
            self._memory_epoch = pose_epoch
        pose = ground_memory.vehicle_pose_from_sensor(lidar_pose, LIDAR_MOUNT_XY, np.radians(LIDAR_YAW_DEG))
        now = time.monotonic()
        seen = visible & ~self._hidden & (self._feather <= 0)        # chỉ điểm ảnh camera thật, không lấy dải mép
        self._memory.update(real, seen, pose, now)
        image, valid = self._memory.recall(pose, now)
        valid &= self._gaps & ~self._car_mask
        region = self._gaps & ~self._car_mask
        self.memory_fraction = float(valid.sum()) / max(int(region.sum()), 1)
        return (image, valid) if valid.any() else None

    def _lidar_guard(self, image: np.ndarray, lidar_xy) -> np.ndarray:
        """Tô cam phần vùng tô (không phải hình thật) nằm trong `_LIDAR_GUARD_M` quanh điểm LiDAR.

        LiDAR quét ở độ cao ≈ 16 cm: vật thấp hơn không có điểm nên vẫn có thể bị vẽ thành sàn."""
        self.lidar_blocked_px = 0
        if lidar_xy is None:
            return image
        xy = np.asarray(lidar_xy, np.float64).reshape(-1, 2)
        xy = xy[np.isfinite(xy).all(axis=1)]
        near_body = ((xy[:, 0] > _BODY.x_min - _LIDAR_SELF_M) & (xy[:, 0] < _BODY.x_max + _LIDAR_SELF_M)
                     & (xy[:, 1] > _BODY.y_min - _LIDAR_SELF_M) & (xy[:, 1] < _BODY.y_max + _LIDAR_SELF_M))
        xy = xy[~near_body]
        if not len(xy):
            return image
        cols, rows = self._pixel(xy[:, 0], xy[:, 1])
        cols, rows = np.rint(cols).astype(int), np.rint(rows).astype(int)
        inside = (cols >= 0) & (cols < _CANVAS_SIZE) & (rows >= 0) & (rows < _CANVAS_SIZE)
        if not inside.any():
            return image
        hits = np.zeros(self._gaps.shape, np.uint8)
        hits[rows[inside], cols[inside]] = 255
        radius = max(1, int(round(_LIDAR_GUARD_M / self._res)))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
        blocked = (cv2.dilate(hits, kernel) > 0) & self._gaps & ~self._car_mask
        self.lidar_blocked_px = int(blocked.sum())
        if not self.lidar_blocked_px:
            return image
        out = image.copy()
        out[blocked] = ((1 - _WARN_ALPHA) * out[blocked] + _WARN_ALPHA * _WARN_COLOR).astype(np.uint8)
        edge = blocked & ~cv2.erode(blocked.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        out[edge] = _WARN_COLOR.astype(np.uint8)
        self.notice = f"{self.notice} LiDAR thấy vật trong vùng mù: tô cam."
        return out

    def _ai_result(self, composite: np.ndarray) -> np.ndarray | None:
        """Gửi ảnh ghép mới nhất cho luồng AI (không chờ) và trả lần tô gần nhất nếu có; cập nhật dòng báo."""
        if not self._ai_enabled:
            self.notice = f"{self._base_notice} Vùng mù ở góc xe: tô màu loang, không phải hình thật."
            return None
        if self._filler is None:
            fill_fn = bev_inpaint.TiledFill(self._ai_fill_fn or _shared_lama_fill, self._gaps.shape)
            self._filler = bev_inpaint.BackgroundFiller(fill_fn, self._gaps)
        self._filler.offer(composite)
        result = self._filler.latest()
        if self._filler.error is not None:
            self.notice = f"{self._base_notice} AI tắt ({self._filler.error}); vùng mù ở góc xe tô màu loang."
            return None
        if result is None:
            self.notice = f"{self._base_notice} Đang nạp AI tô vùng mù; tạm tô màu loang."
            return None
        self.notice = f"{self._base_notice} Vùng mù ở góc xe: AI vẽ, không phải hình thật."
        return result.image

    def close(self) -> None:
        if self._filler is not None:
            self._filler.close()

    def __del__(self):
        try:
            self.close()
        except Exception:  # noqa: BLE001 - dọn khi thu gom rác, không được ném
            pass


def _shared_lama_fill(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    inpainter = bev_inpaint.shared_inpainter()
    if inpainter is None:
        raise bev_inpaint.InpaintUnavailable(bev_inpaint.shared_error() or "không có LaMa")
    return inpainter.fill(image, mask)


def _push_pull(image: np.ndarray, known: np.ndarray, levels: int = 7) -> np.ndarray:
    """Lấp chỗ trống bằng màu loang mềm: co ảnh theo trọng số `known` tới khi phủ kín, rồi phóng ngược và chỉ dùng tầng
    thô ở nơi tầng mịn thiếu dữ liệu. Nhanh (vài ms ở 480×480) và không tạo vệt kéo như inpaint."""
    pyramid = []
    color, weight = image * known[..., None], known
    for _ in range(levels):
        pyramid.append((color, weight))
        color, weight = cv2.pyrDown(color), cv2.pyrDown(weight)
    estimate = color / np.maximum(weight, 1e-6)[..., None]
    for color, weight in reversed(pyramid):
        up = cv2.pyrUp(estimate, dstsize=(color.shape[1], color.shape[0]))
        alpha = np.clip(weight * 4.0, 0.0, 1.0)[..., None]
        estimate = alpha * (color / np.maximum(weight, 1e-6)[..., None]) + (1 - alpha) * up
    return estimate


def _draw_car(image: np.ndarray, pixel, box: bev.EgoBox) -> None:
    """Hình xe nhìn từ trên (mũi xe hướng lên) vẽ trong hộp `box` (hệ xe, m); `pixel(x, y)` → (cột, hàng)."""
    def poly(points, color, outline=None):
        arr = np.array([[int(round(v)) for v in pixel(px, py)] for px, py in points], np.int32)
        cv2.fillPoly(image, [arr], color, cv2.LINE_AA)
        if outline is not None:
            cv2.polylines(image, [arr], True, outline, 1, cv2.LINE_AA)

    def rect(xa, xb, ya, yb, color):
        poly([(xa, ya), (xb, ya), (xb, yb), (xa, yb)], color)

    x0, x1, y0, y1 = box.x_min, box.x_max, box.y_min, box.y_max
    length, half = x1 - x0, (y1 - y0) / 2
    wheel_l, wheel_w = 0.074, 0.026                      # lốp Ø74 mm; trục sau x = 0, trục trước x = 0,21 m
    for wx in (0.0, 0.21):
        for side in (1, -1):
            cy = side * (half - wheel_w / 2)
            rect(wx - wheel_l / 2, wx + wheel_l / 2, cy - wheel_w / 2, cy + wheel_w / 2, (24, 24, 26))
    inset, r = 0.012, 0.03
    body = []
    for cx, cy, a0 in ((x1 - r, y0 + inset + r, -90), (x1 - r, y1 - inset - r, 0),
                       (x0 + r, y1 - inset - r, 90), (x0 + r, y0 + inset + r, 180)):
        for a in np.radians(np.linspace(a0, a0 + 90, 7)):
            body.append((cx + r * np.cos(a), cy + r * np.sin(a)))
    poly(body, (96, 88, 82), (190, 178, 165))
    w_in = 0.03
    front_glass, roof_front, roof_rear, rear_glass = x1 - 0.18 * length, x1 - 0.30 * length, x0 + 0.20 * length, x0 + 0.10 * length
    poly([(roof_front, y0 + w_in), (roof_front, y1 - w_in), (front_glass, y1 - w_in - 0.012),
          (front_glass, y0 + w_in + 0.012)], (52, 40, 34))
    poly([(rear_glass, y0 + w_in + 0.01), (rear_glass, y1 - w_in - 0.01), (roof_rear, y1 - w_in),
          (roof_rear, y0 + w_in)], (52, 40, 34))
    rect(roof_rear, roof_front, y0 + w_in, y1 - w_in, (110, 102, 96))
    for side in (1, -1):                                  # đèn pha
        cy = side * (half - inset - 0.016)
        rect(x1 - 0.018, x1 - 0.006, cy - 0.01, cy + 0.01, (170, 225, 240))


def lidar_points(scan) -> np.ndarray:
    """Vòng quét C1 (góc theo quy ước dự án, như `surround_3d.scan_to_vehicle`) → điểm (N, 2) hệ xe theo gá đo
    `LIDAR_MOUNT_XY`, `LIDAR_YAW_DEG`."""
    angles = np.asarray(scan.angles_rad, np.float64)
    ranges = np.asarray(scan.ranges_m, np.float64)
    good = np.isfinite(ranges) & (ranges > 0.02)
    a = angles[good] + np.radians(LIDAR_YAW_DEG)
    r = ranges[good]
    return np.column_stack([LIDAR_MOUNT_XY[0] + r * np.cos(a), LIDAR_MOUNT_XY[1] + r * np.sin(a)])
