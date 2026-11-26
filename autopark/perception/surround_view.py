"""Colour view of the ground around the stationary vehicle, for display only."""

from __future__ import annotations

from dataclasses import dataclass, replace

import cv2
import numpy as np

from . import bev
from .fisheye_calib import DEFAULT_SIZE


_PORTS = (1, 2, 3, 4)
_CANVAS_SIZE = 480
_GROUND_WIDTH_M = 1.6
_BODY = bev.EgoBox(-0.047, 0.247, -0.080, 0.080)
_CENTER_X = (_BODY.x_min + _BODY.x_max) / 2
_MEASURED_RIG = bev.DEFAULT_EXTRINSICS.with_name("camera_rig_extrinsics_v1.json")
_ROI_DIR = bev.PROJECT / "configs/roi/rig_v1"


@dataclass(frozen=True)
class _View:
    map_pixels: np.ndarray
    map_fractions: np.ndarray
    weights: np.ndarray


def _measured_cameras(extrinsics_path, calibration_dir, roi_dir):
    sizes = dict.fromkeys(_PORTS, DEFAULT_SIZE)
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
    nominal, _ = bev.synthetic_rig()
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

    width, height = DEFAULT_SIZE
    edge = np.minimum.reduce((u, v, width - 1 - u, height - 1 - v))
    # Prefer the centre of a lens and the closer of two views in the overlap.
    weights = np.clip(edge / 64, 0.04, 1) ** 2 / (1 + (dx * dx + dy * dy) / 0.16)
    maps = cv2.convertMaps(map_x, map_y, cv2.CV_16SC2)
    return _View(*maps, np.where(valid, weights, 0).astype(np.float32))


class SurroundViewRenderer:
    def __init__(self, *, extrinsics_path=_MEASURED_RIG, calibration_dir=bev.DEFAULT_CALIBRATION_DIR,
                 roi_dir=_ROI_DIR):
        cameras = _measured_cameras(extrinsics_path, calibration_dir, roi_dir)
        self.is_preview = not cameras
        self.notice = "Hình chiếu mặt sàn đã hiệu chuẩn. Vật cao có thể bị méo."
        if self.is_preview:
            self.notice = "Hình chiếu ước lượng, chưa hiệu chuẩn đủ bốn camera."
            try:
                cameras = _preview_cameras()
            except (bev.RigConfigError, ValueError, TypeError, AttributeError):
                self.notice = "Không đọc được cấu hình hình chiếu."

        offset = (np.arange(_CANVAS_SIZE) + 0.5 - _CANVAS_SIZE / 2) * (_GROUND_WIDTH_M / _CANVAS_SIZE)
        y, x = np.meshgrid(-offset, _CENTER_X - offset)
        body = _BODY.contains(x, y)
        ground = np.column_stack((x.ravel(), y.ravel()))
        self._views = {port: _view_map(camera, x, y, ground, ~body, self.is_preview)
                       for port, camera in cameras.items()}
        self._background = np.full((*x.shape, 3), (19, 16, 14), dtype=np.uint8)
        rows, columns = np.nonzero(body)
        left, right = int(columns.min()), int(columns.max())
        top, bottom = int(rows.min()), int(rows.max())
        cv2.rectangle(self._background, (left, top), (right, bottom), (54, 42, 34), -1)
        cv2.rectangle(self._background, (left, top), (right, bottom), (183, 163, 135), 1)
        centre = (left + right) // 2
        cv2.arrowedLine(self._background, (centre, bottom - 20), (centre, top + 17),
                        (222, 213, 195), 2, cv2.LINE_AA, tipLength=0.28)

    def render(self, frames: dict[int, np.ndarray]) -> np.ndarray:
        """Render the available 640x480 BGR sources on a fresh 480x480 BGR canvas."""
        canvas = self._background.copy()
        if not frames:
            return canvas
        color = np.zeros(canvas.shape, dtype=np.float32)
        total = np.zeros(canvas.shape[:2], dtype=np.float32)
        width, height = DEFAULT_SIZE
        for port, view in self._views.items():
            frame = frames.get(port)
            if frame is None or frame.shape != (height, width, 3) or frame.dtype != np.uint8:
                continue
            image = cv2.remap(frame, view.map_pixels, view.map_fractions, cv2.INTER_LINEAR)
            color += image * view.weights[:, :, None]
            total += view.weights
        visible = total > 0
        canvas[visible] = np.rint(color[visible] / total[visible, None]).astype(np.uint8)
        return canvas
