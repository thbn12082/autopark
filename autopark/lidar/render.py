"""Vẽ bản quét 2D thành ảnh (OpenCV) để kiểm tra bằng mắt và ghi hồ sơ; không cần Qt."""
from __future__ import annotations

import math

import cv2
import numpy as np

from autopark.domain.sensors import LidarScan

from .drow import scan_points, valid_mask


def render_scan(scan: LidarScan, *, size: int = 600, max_range: float = 10.0,
                detections: list[tuple[float, float]] | None = None, title: str = "") -> np.ndarray:
    """Top-down picture: sensor at the centre, x (forward) up, y (left) to the left; NaN beams drawn faint."""
    image = np.full((size, size, 3), 25, np.uint8)
    centre = (size // 2, size // 2)
    scale = (size / 2 - 10) / max_range

    def px(x: float, y: float) -> tuple[int, int]:
        return int(round(centre[0] - y * scale)), int(round(centre[1] - x * scale))

    for r in range(1, int(max_range) + 1):
        cv2.circle(image, centre, int(r * scale), (55, 55, 55), 1)
    angles = np.asarray(scan.angles_rad)
    for a in (angles[0], angles[-1]):
        cv2.line(image, centre, px(max_range * math.cos(a), max_range * math.sin(a)), (70, 70, 70), 1)
    ok = valid_mask(scan)
    for a in angles[~ok]:
        cv2.line(image, centre, px(max_range * math.cos(a), max_range * math.sin(a)), (45, 45, 45), 1)
    for x, y in scan_points(scan):
        cv2.circle(image, px(x, y), 2, (0, 220, 255), -1)
    for r, phi in detections or []:
        cv2.circle(image, px(r * math.cos(phi), r * math.sin(phi)), int(0.35 * scale) + 3, (0, 80, 255), 2)
    cv2.circle(image, centre, 5, (255, 255, 0), -1)
    cv2.putText(image, title or f"{scan.stamp.source_id} t={scan.stamp.t:.2f}s valid {int(ok.sum())}/{len(ok)}",
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
    return image
