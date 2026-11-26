"""WoodScape fisheye camera model: radial polynomial intrinsics and vehicle-frame extrinsics.

Conventions (checked numerically in tests/test_perception_calibration.py and recorded in
runs/perception_integration/calibration_convention_check.json):
- Camera frame: X right, Y down, Z along the optical axis. theta = angle from the optical axis,
  rho(theta) = k1*theta + k2*theta^2 + k3*theta^3 + k4*theta^4 in pixels.
- Principal point: (width/2 - 0.5 + cx_offset, height/2 - 0.5 + cy_offset); aspect_ratio scales the
  vertical pixel pitch (WoodScape files have 0.99999..1.00062, i.e. at most 0.3 px at the image edge).
- Extrinsics: quaternion (x, y, z, w) rotating CAMERA coordinates into the VEHICLE frame, plus the camera
  position in that frame. Vehicle frame: x forward, y left, z up, origin on the ground, which matches the
  map/vehicle conventions used elsewhere in this project.
Ground projection assumes a flat ground plane z = 0 in the vehicle frame.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np


def quaternion_to_matrix(x: float, y: float, z: float, w: float) -> np.ndarray:
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if not norm or not math.isfinite(norm):
        raise ValueError("Quaternion must be finite and non-zero")
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


@dataclass(frozen=True)
class FisheyeIntrinsics:
    width: int
    height: int
    k: tuple[float, float, float, float]
    cx_offset: float = 0.0
    cy_offset: float = 0.0
    aspect_ratio: float = 1.0
    theta_max: float = math.radians(100.0)   # beyond this the polynomial is extrapolated, not calibrated

    def __post_init__(self):
        if self.width <= 0 or self.height <= 0 or self.aspect_ratio <= 0 or len(self.k) != 4:
            raise ValueError("Invalid intrinsics")
        thetas = np.linspace(0.0, self.theta_max, 2049)
        rhos = self.theta_to_rho(thetas)
        if not np.all(np.diff(rhos) > 0):
            raise ValueError("rho(theta) must increase monotonically up to theta_max")
        object.__setattr__(self, "_inverse_table", (rhos, thetas))

    @property
    def cx(self) -> float:
        return self.width / 2 - 0.5 + self.cx_offset

    @property
    def cy(self) -> float:
        return self.height / 2 - 0.5 + self.cy_offset

    def theta_to_rho(self, theta):
        theta = np.asarray(theta, dtype=np.float64)
        k1, k2, k3, k4 = self.k
        return theta * (k1 + theta * (k2 + theta * (k3 + theta * k4)))

    def rho_to_theta(self, rho):
        rhos, thetas = self._inverse_table
        rho = np.asarray(rho, dtype=np.float64)
        theta = np.interp(rho, rhos, thetas, right=np.nan)
        return np.where(rho < 0, np.nan, theta)

    def project(self, points_cam: np.ndarray):
        """(N, 3) camera-frame points -> (u, v) pixel coordinates and a validity mask.

        Valid means theta <= theta_max and the pixel lies inside the image. Points with theta beyond
        theta_max are invalid even though the polynomial could be extrapolated there.
        """
        p = np.asarray(points_cam, dtype=np.float64).reshape(-1, 3)
        chi = np.hypot(p[:, 0], p[:, 1])
        theta = np.arctan2(chi, p[:, 2])
        rho = self.theta_to_rho(np.minimum(theta, self.theta_max))
        with np.errstate(invalid="ignore", divide="ignore"):
            scale = np.where(chi > 1e-12, rho / chi, 0.0)
        u = self.cx + scale * p[:, 0]
        v = self.cy + scale * p[:, 1] * self.aspect_ratio
        at_centre = (chi <= 1e-12) & (np.abs(p[:, 2]) <= 1e-12)      # the camera centre itself has no direction
        valid = ((theta <= self.theta_max) & ~at_centre & (u >= 0) & (u <= self.width - 1)
                 & (v >= 0) & (v <= self.height - 1))
        return u, v, valid

    def unproject(self, u, v) -> np.ndarray:
        """Pixel coordinates -> unit ray directions (N, 3) in the camera frame (NaN where uncalibrated)."""
        du = np.asarray(u, dtype=np.float64) - self.cx
        dv = (np.asarray(v, dtype=np.float64) - self.cy) / self.aspect_ratio
        rho = np.hypot(du, dv)
        theta = self.rho_to_theta(rho)
        with np.errstate(invalid="ignore", divide="ignore"):
            unit = np.where(rho > 1e-12, 1.0 / rho, 0.0)
        s = np.sin(theta)
        return np.stack([s * du * unit, s * dv * unit, np.cos(theta)], axis=-1)


def matrix_to_quaternion(matrix: np.ndarray) -> tuple[float, float, float, float]:
    """Rotation matrix -> (x, y, z, w); inverse of quaternion_to_matrix up to sign."""
    m = np.asarray(matrix, dtype=np.float64)
    if m.shape != (3, 3) or not np.allclose(m @ m.T, np.eye(3), atol=1e-6) or np.linalg.det(m) < 0:
        raise ValueError("Not a proper rotation matrix")
    trace = np.trace(m)
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        return ((m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s)
    i = int(np.argmax(np.diag(m)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(1.0 + m[i, i] - m[j, j] - m[k, k]) * 2
    q = [0.0, 0.0, 0.0, 0.0]
    q[i] = 0.25 * s
    q[j] = (m[j, i] + m[i, j]) / s
    q[k] = (m[k, i] + m[i, k]) / s
    q[3] = (m[k, j] - m[j, k]) / s
    return tuple(q)


@dataclass(frozen=True)
class Extrinsics:
    quaternion_xyzw: tuple[float, float, float, float]
    translation: tuple[float, float, float]

    @classmethod
    def from_matrix(cls, rotation: np.ndarray, translation) -> "Extrinsics":
        """Build from a camera->vehicle rotation matrix (columns = camera axes in the vehicle frame)."""
        return cls(matrix_to_quaternion(rotation), tuple(float(t) for t in translation))

    @property
    def rotation(self) -> np.ndarray:
        """Camera -> vehicle rotation."""
        return quaternion_to_matrix(*self.quaternion_xyzw)

    def camera_to_vehicle(self, points_cam: np.ndarray) -> np.ndarray:
        return np.asarray(points_cam, dtype=np.float64) @ self.rotation.T + np.asarray(self.translation)

    def vehicle_to_camera(self, points_vehicle: np.ndarray) -> np.ndarray:
        return (np.asarray(points_vehicle, dtype=np.float64) - np.asarray(self.translation)) @ self.rotation


@dataclass(frozen=True)
class CameraCalibration:
    name: str
    intrinsics: FisheyeIntrinsics
    extrinsics: Extrinsics

    @classmethod
    def from_dict(cls, data: dict) -> "CameraCalibration":
        intr, extr = data["intrinsic"], data["extrinsic"]
        if intr.get("model") != "radial_poly" or int(intr.get("poly_order", 4)) != 4:
            raise ValueError(f"Unsupported intrinsic model: {intr.get('model')} order {intr.get('poly_order')}")
        return cls(str(data.get("name", "")),
                   FisheyeIntrinsics(int(intr["width"]), int(intr["height"]),
                                     (float(intr["k1"]), float(intr["k2"]), float(intr["k3"]), float(intr["k4"])),
                                     float(intr.get("cx_offset", 0.0)), float(intr.get("cy_offset", 0.0)),
                                     float(intr.get("aspect_ratio", 1.0)),
                                     # tệp WoodScape không có khóa này (giữ 100°); tệp của fisheye_calib ghi góc lớn nhất
                                     # mà đa thức khớp còn đúng, vượt quá đó là ngoại suy
                                     math.radians(float(intr["theta_max_deg"])) if "theta_max_deg" in intr
                                     else math.radians(100.0)),
                   Extrinsics(tuple(float(q) for q in extr["quaternion"]),
                              tuple(float(t) for t in extr["translation"])))

    @classmethod
    def load(cls, path) -> "CameraCalibration":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def ground_to_pixel(self, xy_vehicle: np.ndarray):
        """Ground points (N, 2) in the vehicle frame (z = 0) -> (u, v, valid)."""
        xy = np.asarray(xy_vehicle, dtype=np.float64).reshape(-1, 2)
        points = np.column_stack([xy, np.zeros(len(xy))])
        return self.intrinsics.project(self.extrinsics.vehicle_to_camera(points))

    def pixel_to_ground(self, u, v, max_range: float | None = None):
        """Pixels -> ground points (N, 2) in the vehicle frame; valid only where the ray hits z = 0 ahead.

        Rays a hair below the horizon hit the plane kilometres away; pass `max_range` (metres from the
        camera's ground position) to reject them.
        """
        rays = self.intrinsics.unproject(u, v) @ self.extrinsics.rotation.T
        origin = np.asarray(self.extrinsics.translation)
        with np.errstate(invalid="ignore", divide="ignore"):
            s = -origin[2] / rays[..., 2]
        valid = np.isfinite(s) & (rays[..., 2] < -1e-9) & (s > 0)
        xy = origin[:2] + s[..., None] * rays[..., :2]
        if max_range is not None:
            valid &= np.hypot(xy[..., 0] - origin[0], xy[..., 1] - origin[1]) <= max_range
        return xy, valid


def load_woodscape_calibration(archive_path, image_id: str) -> CameraCalibration:
    """Read one calibration JSON straight from datasets/woodscape_metadata/calibration.zip."""
    import zipfile

    with zipfile.ZipFile(archive_path) as archive:
        return CameraCalibration.from_dict(json.loads(archive.read(f"calibration/{image_id}.json").decode("utf-8")))
