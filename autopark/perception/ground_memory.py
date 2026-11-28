"""Ảnh nhớ mặt sàn theo chuyển động: lấp vùng mù quanh xe bằng ảnh THẬT camera đã chụp vài giây trước (29/11/2026).

Ô tô dùng cách này cho "nắp capo trong suốt". Mỗi khung, các điểm ảnh BEV mà camera thật thấy được dán vào một tấm ảnh
cố định theo mặt đất (`GroundMemory.update`), theo tư thế xe lúc đó (odometry khớp scan LiDAR,
`lidar.scan_odometry.ScanOdometry`). Khi một góc xe đi vào vùng mù, phần sàn đó lấy lại từ tấm ảnh (`recall`) thay vì để
AI đoán. Chỉ phần chưa từng thấy (hoặc đã quá `MAX_AGE_S`) mới cho LaMa vẽ.

Giới hạn: ảnh nhớ là sàn của vài giây trước, vật tự di chuyển vào vùng mù sau đó không hiện (LiDAR vẫn canh, xem
`SurroundViewRenderer._lidar_guard`); sai số tư thế (hướng gá C1 chưa đo, trượt bánh) làm ảnh nhớ lệch vài cm; vật cao
bị chiếu như sàn nên để lại vệt. Chỉ để xem.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

RES_M = 0.004                  # 4 mm mỗi điểm ảnh nhớ (BEV hiển thị ≈ 2 mm; vùng mù vốn ở xa camera, ảnh đã mờ hơn)
SIZE_M = 4.0                   # tấm ảnh nhớ 4 × 4 m, tự dời khi xe tới gần mép
RECENTER_MARGIN_M = 1.0
MAX_AGE_S = 20.0               # ảnh nhớ cũ hơn thế này không dùng


def compose_pose(a, b) -> np.ndarray:
    """Tư thế a ∘ b (x, y, góc) trong mặt phẳng."""
    c, s = math.cos(a[2]), math.sin(a[2])
    return np.array([a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], a[2] + b[2]])


def vehicle_pose_from_sensor(sensor_pose, mount_xy, mount_yaw_rad: float = 0.0) -> np.ndarray:
    """Tư thế xe từ tư thế cảm biến: T_xe = T_cảm_biến ∘ T_gá⁻¹ (gá = vị trí, hướng cảm biến trong hệ xe)."""
    c, s = math.cos(mount_yaw_rad), math.sin(mount_yaw_rad)
    inv = np.array([-(c * mount_xy[0] + s * mount_xy[1]), -(-s * mount_xy[0] + c * mount_xy[1]), -mount_yaw_rad])
    return compose_pose(np.asarray(sensor_pose, np.float64), inv)


class GroundMemory:
    """`canvas_to_vehicle(c, r) → (x, y)` là phép affine của ảnh BEV hiển thị (cột, hàng) sang hệ xe (m)."""

    def __init__(self, canvas_size: int, canvas_res_m: float, center_x_m: float, *, res_m: float = RES_M,
                 size_m: float = SIZE_M, max_age_s: float = MAX_AGE_S):
        self.n = int(canvas_size)
        self.canvas_res = float(canvas_res_m)
        self.center_x = float(center_x_m)
        self.res = float(res_m)
        self.cells = int(round(size_m / res_m))
        self.max_age = float(max_age_s)
        self.reset()

    def reset(self) -> None:
        self.image = np.zeros((self.cells, self.cells, 3), np.uint8)
        self.stamp = np.full((self.cells, self.cells), -np.inf, np.float32)   # lúc mỗi ô được camera thấy gần nhất
        self.origin: np.ndarray | None = None      # tọa độ thế giới (m) của góc ô (0, 0)

    # ---- phép biến đổi ------------------------------------------------------------------------------------------------
    def _canvas_to_vehicle(self, c, r):
        half = self.n / 2
        return self.center_x - (np.asarray(r, float) + 0.5 - half) * self.canvas_res, \
            -(np.asarray(c, float) + 0.5 - half) * self.canvas_res

    def _affine(self, pose) -> np.ndarray:
        """Ma trận 2×3: (cột, hàng) ảnh BEV → (u, v) ô ảnh nhớ, theo tư thế xe `pose` (thế giới)."""
        pts = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        x, y = self._canvas_to_vehicle(pts[:, 0], pts[:, 1])
        c, s = math.cos(pose[2]), math.sin(pose[2])
        wx = pose[0] + c * x - s * y
        wy = pose[1] + s * x + c * y
        uv = np.column_stack([(wx - self.origin[0]) / self.res, (wy - self.origin[1]) / self.res])
        return cv2.getAffineTransform(pts.astype(np.float32), uv.astype(np.float32)).astype(np.float64)

    def _ensure_origin(self, pose) -> None:
        half = self.cells * self.res / 2
        if self.origin is None:
            self.origin = np.array([pose[0] - half, pose[1] - half])
            return
        rel = np.asarray(pose[:2]) - self.origin
        if (rel < RECENTER_MARGIN_M).any() or (rel > 2 * half - RECENTER_MARGIN_M).any():
            new = np.array([pose[0] - half, pose[1] - half])
            shift = np.rint((new - self.origin) / self.res).astype(int)       # dời theo số ô nguyên
            self.image = _shift(self.image, shift, 0)
            self.stamp = _shift(self.stamp, shift, -np.inf)
            self.origin = self.origin + shift * self.res

    # ---- ghi / đọc ----------------------------------------------------------------------------------------------------
    def update(self, canvas: np.ndarray, visible: np.ndarray, pose, t: float) -> None:
        """Dán các điểm ảnh camera thật thấy được (`visible`) của ảnh BEV `canvas` vào ảnh nhớ ở tư thế `pose`."""
        pose = np.asarray(pose, np.float64)
        self._ensure_origin(pose)
        A = self._affine(pose)
        corners = np.array([[0, 0, 1], [self.n, 0, 1], [0, self.n, 1], [self.n, self.n, 1]], np.float64) @ A.T
        u0, v0 = np.floor(corners.min(axis=0)).astype(int) - 1
        u1, v1 = np.ceil(corners.max(axis=0)).astype(int) + 1
        u0, v0 = max(u0, 0), max(v0, 0)
        u1, v1 = min(u1, self.cells), min(v1, self.cells)
        if u1 <= u0 or v1 <= v0:
            return
        local = A.copy()
        local[0, 2] -= u0
        local[1, 2] -= v0
        size = (u1 - u0, v1 - v0)
        warped = cv2.warpAffine(canvas, local, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        seen = cv2.warpAffine(visible.astype(np.uint8) * 255, local, size, flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT) >= 250            # chỉ ô nằm trọn trong vùng thấy
        region = self.image[v0:v1, u0:u1]
        region[seen] = warped[seen]
        self.stamp[v0:v1, u0:u1][seen] = t

    def recall(self, pose, t: float) -> tuple[np.ndarray, np.ndarray]:
        """Ảnh nhớ chiếu về khung BEV ở tư thế `pose`: (ảnh BGR, mặt nạ ô có ảnh nhớ còn mới)."""
        if self.origin is None:
            return np.zeros((self.n, self.n, 3), np.uint8), np.zeros((self.n, self.n), bool)
        A = self._affine(np.asarray(pose, np.float64))
        flags = cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP
        image = cv2.warpAffine(self.image, A, (self.n, self.n), flags=flags, borderMode=cv2.BORDER_CONSTANT)
        stamp = cv2.warpAffine(self.stamp, A, (self.n, self.n), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=-np.inf)
        return image, np.isfinite(stamp) & (t - stamp <= self.max_age)


def _shift(array: np.ndarray, shift, fill) -> np.ndarray:
    """Dời ảnh nhớ khi gốc dời `shift` ô (cột u, hàng v): ô (u, v) mới = ô (u + du, v + dv) cũ."""
    du, dv = int(shift[0]), int(shift[1])
    out = np.full_like(array, fill)
    h, w = array.shape[:2]
    src_u0, src_v0 = max(du, 0), max(dv, 0)
    dst_u0, dst_v0 = max(-du, 0), max(-dv, 0)
    cw, ch = w - abs(du), h - abs(dv)
    if cw > 0 and ch > 0:
        out[dst_v0:dst_v0 + ch, dst_u0:dst_u0 + cw] = array[src_v0:src_v0 + ch, src_u0:src_u0 + cw]
    return out
