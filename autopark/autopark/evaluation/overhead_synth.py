"""Cảnh TỔNG HỢP cho tham chiếu trên cao R1 (T4): dựng ảnh camera trên cao (Kannala–Brandt ĐÃ BIẾT) nhìn sàn có các
marker ArUco làm mốc, và một tấm "xe giả" mang hai marker ở độ cao h. Thêm 02/10/2026. KHÔNG phải số đo.

Dùng cho mọi test của T4 và cho lệnh `overhead_ref synthetic --out runs\\tren_cao\\tong_hop` (bộ thử có README.txt liệt
kê chuỗi floor → tc1 → track). Cách dựng độc lập với mô-đun đang kiểm: với mỗi điểm ảnh con (siêu lấy mẫu), tia nhìn lấy
từ `cv2.fisheye.undistortPoints` MỘT lần; mặt sàn tĩnh được dựng một lần rồi giữ lại (tia → điểm sàn → lưới nhãn 5 mm →
chỉ tính ô module của đúng marker sở hữu ô lưới đó), mỗi khung chỉ dựng lại hộp bao của tấm xe (và vật che) trên ảnh, rồi
làm mờ, thêm nhiễu, nén JPEG nếu cần. `camera_offset` (độ, quay quanh trục camera) giả lập camera bị va lệch; mỗi độ lệch
có một bản sàn riêng trong bộ nhớ đệm.

Bản thử 02/10/2026 (script tạm, 960×540, KB, camera 2,30 m nghiêng 2,5°, 43 marker sàn 80 mm, xe 0,10 m với hai marker
100 mm cách 0,25 m): tinh chỉnh góc kiểu đường viền cho sai số điểm kiểm tra RMS/lớn nhất 1,07/1,73 mm, xe 0,44 mm và
0,002°; không bù độ cao thì lệch 61–63 mm. Mọi con số đó là TỔNG HỢP: hình học lý tưởng, không có nhòe chuyển động,
màn trập cuộn, giấy cong hay ánh sáng thật.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path

import cv2
import numpy as np

from autopark.domain.types import Pose
from autopark.evaluation.overhead_ref import (DEFAULT_DICTIONARY, MARKERS_FORMAT, SYNTHETIC_LABEL, OverheadError,
                                              forbidden_dir, parse_vehicle_markers, write_text_atomic)
from autopark.perception import fisheye_calib as fc
from autopark.perception.aruco_sheet import CAR_IDS, marker_bits
from autopark.video.overhead_record import OverheadRecorder

SYNTH_D = np.array([-0.02, 0.006, -0.002, 0.0003])
QUIET_MODULES = 1.5
LABEL_CELL_M = 0.005
FLOOR_GREY, FLOOR_CHECKER, PAPER, INK, PLATE_GREY, OCCLUDER, SCREEN_OFF, SCREEN_ON, SKY = (
    110.0, 10.0, 235.0, 20.0, 200.0, 60.0, 30.0, 250.0, 150.0)
UNDISTORT_CRITERIA = (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 30, 1e-12)
STAMP_PATTERN = (0.031, 0.048)          # khoảng cách khung xen kẽ (s): giống camera tự đổi nhịp 24–30 khung/s
CAR_NAME = "xe_gia_tong_hop"
CAMERA_NAME = "tren_cao_tong_hop"
CAR_GEOMETRY = {"z_m": 0.10, "rear_x": 0.0, "front_x": 0.30, "r2": {"sau": [-0.15, 0.05], "truoc": [0.55, 0.05]}}
HEADINGS_DEG = (0.0, 35.0, 90.0, -60.0, 150.0, 120.0, -20.0, 60.0, 180.0, -120.0)


def rot_x(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], np.float64)


def rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], np.float64)


def default_K(size: tuple[int, int], f: float | None = None) -> np.ndarray:
    w, h = size
    s = w / 960.0
    f = 600.0 * s if f is None else float(f)
    return np.array([[f, 0.0, w / 2 - 3.2 * s], [0.0, f * 1.002, h / 2 + 2.1 * s], [0.0, 0.0, 1.0]])


@dataclass
class SynthCamera:
    """Camera ảo: X_c = R·X_s + t (hệ sa bàn → camera), nội tham KB (K, D)."""

    K: np.ndarray
    D: np.ndarray
    size: tuple[int, int]
    R: np.ndarray
    t: np.ndarray

    @classmethod
    def looking_down(cls, centre, heading_deg: float = 0.0, tilt_deg: float = 0.0, size=(1280, 720), K=None,
                     D=None) -> "SynthCamera":
        """Nhìn thẳng xuống từ `centre` (m): trục x ảnh theo +x sa bàn, trục y ảnh theo −y; xoay ảnh `heading_deg`
        quanh trục quang và nghiêng `tilt_deg` quanh trục x camera."""
        base = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], np.float64)
        R = rot_x(math.radians(tilt_deg)) @ rot_z(math.radians(heading_deg)) @ base
        centre = np.asarray(centre, np.float64)
        return cls(default_K(size) if K is None else np.asarray(K, np.float64),
                   SYNTH_D.copy() if D is None else np.asarray(D, np.float64), tuple(size), R, -R @ centre)

    @property
    def centre(self) -> np.ndarray:
        return -self.R.T @ self.t

    @property
    def rvec(self) -> np.ndarray:
        return cv2.Rodrigues(self.R)[0].ravel()

    def project(self, xyz) -> np.ndarray:
        xyz = np.asarray(xyz, np.float64).reshape(-1, 3)
        uv = cv2.fisheye.projectPoints(xyz.reshape(1, -1, 3), self.rvec.reshape(3, 1), self.t.reshape(3, 1), self.K,
                                       self.D.reshape(4, 1))[0].reshape(-1, 2)
        uv[(xyz @ self.R.T + self.t)[:, 2] <= 1e-9] = np.nan
        return uv

    def offset(self, rot_deg) -> "SynthCamera":
        """Cùng tâm, quay thêm `rot_deg` (độ, quanh trục x, y, z của camera; một số = quanh trục x)."""
        r = np.radians(np.broadcast_to(np.asarray(rot_deg, np.float64), (3,)) if np.ndim(rot_deg) else
                       np.array([float(rot_deg), 0.0, 0.0]))
        R = cv2.Rodrigues(r)[0] @ self.R
        return SynthCamera(self.K, self.D, self.size, R, -R @ self.centre)


@dataclass(frozen=True)
class FloorMarker:
    name: str
    marker_id: int
    x: float
    y: float
    side: float
    yaw_deg: float = 0.0


@dataclass(frozen=True)
class PlateMarker:
    marker_id: int
    x: float              # hệ xe (m)
    y: float
    side: float
    yaw_deg: float = 0.0


@dataclass(frozen=True)
class CarPlate:
    """Tấm phẳng nằm ngang ở độ cao `z`, mang các marker; `extent_xy` = (x0, x1, y0, y1) trong hệ xe."""

    markers: tuple[PlateMarker, ...]
    extent_xy: tuple[float, float, float, float]
    z: float
    shade: float = PLATE_GREY

    @classmethod
    def from_vehicle(cls, car) -> "CarPlate":
        markers = tuple(PlateMarker(m.marker_id, m.x, m.y, m.side, m.yaw_deg) for m in car.markers)
        margin = max(m.side * (0.5 + 2.0 * QUIET_MODULES / 6.0) for m in markers)
        xs, ys = [m.x for m in markers], [m.y for m in markers]
        return cls(markers, (min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin),
                   float(np.mean([m.z for m in car.markers])))


@dataclass(frozen=True)
class Occluder:
    """Hộp nằm ngang che khuất (tay, dây) ở độ cao `z`, hệ sa bàn."""

    x0: float
    x1: float
    y0: float
    y1: float
    z: float


def _shade_markers(lx, ly, idx, sides, bits_all, values) -> None:
    """Tô vùng trắng và ô module cho các điểm (lx, ly) đã ở hệ của marker `idx` (mảng cùng độ dài)."""
    nb = bits_all.shape[1]
    side = sides[idx]
    half = side / 2
    quiet = half + QUIET_MODULES * side / nb
    in_quiet = (np.abs(lx) < quiet) & (np.abs(ly) < quiet)
    values[in_quiet] = PAPER
    in_marker = (np.abs(lx) < half) & (np.abs(ly) < half)
    if np.any(in_marker):
        cell = side[in_marker] / nb
        col = np.clip(np.floor((lx[in_marker] + half[in_marker]) / cell), 0, nb - 1).astype(np.int64)
        row = np.clip(np.floor((half[in_marker] - ly[in_marker]) / cell), 0, nb - 1).astype(np.int64)
        values[in_marker] = np.where(bits_all[idx[in_marker], row, col], PAPER, INK)


class OverheadRenderer:
    """Dựng khung camera trên cao; mặt sàn tĩnh dựng một lần cho mỗi độ lệch camera."""

    def __init__(self, camera: SynthCamera, dictionary: str = DEFAULT_DICTIONARY, floor_markers=(),
                 supersample: int = 2):
        self.camera, self.dictionary, self.ss = camera, dictionary, int(supersample)
        w, h = camera.size
        us = (np.arange(w * self.ss) + 0.5) / self.ss - 0.5
        vs = (np.arange(h * self.ss) + 0.5) / self.ss - 0.5
        uu, vv = np.meshgrid(us, vs)
        und = cv2.fisheye.undistortPoints(np.stack([uu.ravel(), vv.ravel()], 1).reshape(-1, 1, 2), camera.K,
                                          camera.D.reshape(4, 1), criteria=UNDISTORT_CRITERIA)
        self.und = und.reshape(h * self.ss, w * self.ss, 2).astype(np.float64)
        self.floor_markers = list(floor_markers)
        self._floor_cache: dict = {}
        self.last_bbox: tuple[int, int, int, int] | None = None
        self._bits_cache: dict[int, np.ndarray] = {}
        self._build_labels()

    def bits(self, marker_id: int) -> np.ndarray:
        if marker_id not in self._bits_cache:
            self._bits_cache[marker_id] = marker_bits(self.dictionary, marker_id)
        return self._bits_cache[marker_id]

    def _build_labels(self) -> None:
        ms = self.floor_markers
        if not ms:
            self._labels = None
            return
        self._centres = np.array([[m.x, m.y] for m in ms])
        self._cos_sin = np.array([[math.cos(math.radians(m.yaw_deg)), math.sin(math.radians(m.yaw_deg))] for m in ms])
        self._sides = np.array([m.side for m in ms])
        self._bits_all = np.array([self.bits(m.marker_id) for m in ms])
        reach = self._sides * (0.5 + QUIET_MODULES / self._bits_all.shape[1]) * math.sqrt(2) + LABEL_CELL_M
        x0, y0 = (self._centres - reach[:, None]).min(axis=0)
        x1, y1 = (self._centres + reach[:, None]).max(axis=0)
        nx, ny = int(math.ceil((x1 - x0) / LABEL_CELL_M)) + 1, int(math.ceil((y1 - y0) / LABEL_CELL_M)) + 1
        labels = np.full((ny, nx), -1, np.int32)
        for k, ((cx, cy), r) in enumerate(zip(self._centres, reach)):
            i0, i1 = int((cx - r - x0) // LABEL_CELL_M), int(math.ceil((cx + r - x0) / LABEL_CELL_M)) + 1
            j0, j1 = int((cy - r - y0) // LABEL_CELL_M), int(math.ceil((cy + r - y0) / LABEL_CELL_M)) + 1
            labels[max(0, j0):j1, max(0, i0):i1] = k
        self._labels, self._label_origin = labels, (x0, y0)

    def _world_rays(self, cam: SynthCamera, und: np.ndarray) -> np.ndarray:
        und = und.reshape(-1, 2)
        return und @ cam.R[:2] + cam.R[2]                  # R_csᵀ·[nx, ny, 1]

    def _shade_floor(self, fx: np.ndarray, fy: np.ndarray, hit: np.ndarray) -> np.ndarray:
        values = np.full(fx.shape, SKY)
        values[hit] = FLOOR_GREY + FLOOR_CHECKER * (((np.floor(fx[hit] / 0.1) + np.floor(fy[hit] / 0.1)) % 2) - 0.5)
        if self._labels is None:
            return values
        ny, nx = self._labels.shape
        gi = np.floor((fx - self._label_origin[0]) / LABEL_CELL_M)
        gj = np.floor((fy - self._label_origin[1]) / LABEL_CELL_M)
        inside = hit & (gi >= 0) & (gi < nx) & (gj >= 0) & (gj < ny)
        sel = np.flatnonzero(inside)
        lab = self._labels[gj[sel].astype(np.int64), gi[sel].astype(np.int64)]
        keep = lab >= 0
        sel, lab = sel[keep], lab[keep]
        if not len(sel):
            return values
        dx, dy = fx[sel] - self._centres[lab, 0], fy[sel] - self._centres[lab, 1]
        c, s = self._cos_sin[lab, 0], self._cos_sin[lab, 1]
        sub = values[sel]
        _shade_markers(c * dx + s * dy, -s * dx + c * dy, lab, self._sides, self._bits_all, sub)
        values[sel] = sub
        return values

    def _floor(self, key, cam: SynthCamera) -> tuple[np.ndarray, np.ndarray]:
        if key not in self._floor_cache:
            hs, ws = self.und.shape[:2]
            floor_ss = np.empty((hs, ws), np.float32)
            step = 128
            o = cam.centre
            for r0 in range(0, hs, step):
                d = self._world_rays(cam, self.und[r0:r0 + step])
                hit = d[:, 2] < -1e-9
                with np.errstate(divide="ignore", invalid="ignore"):
                    k = np.where(hit, -o[2] / d[:, 2], 0.0)
                floor_ss[r0:r0 + step] = self._shade_floor(o[0] + k * d[:, 0], o[1] + k * d[:, 1],
                                                           hit).reshape(-1, ws)
            w, h = cam.size
            image = floor_ss.reshape(h, self.ss, w, self.ss).mean(axis=(1, 3)).astype(np.float32)
            self._floor_cache[key] = (floor_ss, image)
        return self._floor_cache[key]

    def floor_image(self, camera_offset=None, blur: float = 0.6) -> np.ndarray:
        """Sàn trống đã làm mờ, chưa nhiễu (xám uint8): phần ảnh ngoài hộp bao của xe phải trùng từng điểm ảnh."""
        cam, key = self._camera(camera_offset)
        img = self._floor(key, cam)[1]
        if blur:
            img = cv2.GaussianBlur(img, (0, 0), blur)
        return np.clip(np.rint(img), 0, 255).astype(np.uint8)

    def _camera(self, camera_offset) -> tuple[SynthCamera, tuple | None]:
        if camera_offset is None or not np.any(np.asarray(camera_offset, np.float64)):
            return self.camera, None
        key = tuple(np.broadcast_to(np.asarray(camera_offset, np.float64), (3,))) if np.ndim(camera_offset) else (
            float(camera_offset), 0.0, 0.0)
        return self.camera.offset(key), key

    def _bbox(self, cam: SynthCamera, outlines: list[np.ndarray]) -> tuple[int, int, int, int] | None:
        pts = np.vstack([cam.project(o) for o in outlines])
        pts = pts[np.all(np.isfinite(pts), axis=1)]
        if not len(pts):
            return None
        w, h = cam.size
        x0, y0 = np.floor(pts.min(axis=0) - 2).astype(int)
        x1, y1 = np.ceil(pts.max(axis=0) + 3).astype(int)
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None

    @staticmethod
    def _outline(corners_xy: np.ndarray, z: float, per_edge: int = 8) -> np.ndarray:
        pts = []
        for a, b in zip(corners_xy, np.roll(corners_xy, -1, axis=0)):
            pts += [a + (b - a) * k / per_edge for k in range(per_edge)]
        return np.column_stack([np.array(pts), np.full(len(pts), z)])

    def frame(self, car_pose: Pose | None = None, plate: CarPlate | None = None, *, rng=None, noise: float = 2.0,
              blur: float = 0.6, occluders=(), flash=None, camera_offset=None, jpeg_quality: int | None = None
              ) -> np.ndarray:
        """Một khung BGR uint8. `flash` = (x, y, rộng, cao, phần sáng 0..1) điểm ảnh: ô màn hình T14, phần trên sáng."""
        cam, key = self._camera(camera_offset)
        floor_ss, floor_img = self._floor(key, cam)
        img = floor_img.copy()
        outlines = []
        if car_pose is not None and plate is not None:
            x0, x1, y0, y1 = plate.extent_xy
            c, s = math.cos(car_pose.yaw), math.sin(car_pose.yaw)
            local = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
            world = local @ np.array([[c, s], [-s, c]]) + np.array([car_pose.x, car_pose.y])
            outlines.append(self._outline(world, plate.z))
        for occ in occluders:
            outlines.append(self._outline(np.array([[occ.x0, occ.y0], [occ.x1, occ.y0], [occ.x1, occ.y1],
                                                    [occ.x0, occ.y1]]), occ.z))
        bbox = self._bbox(cam, outlines) if outlines else None
        if bbox is not None:
            bx0, by0, bx1, by1 = bbox
            ss = self.ss
            region = floor_ss[by0 * ss:by1 * ss, bx0 * ss:bx1 * ss].copy().ravel().astype(np.float64)
            d = self._world_rays(cam, self.und[by0 * ss:by1 * ss, bx0 * ss:bx1 * ss])
            o = cam.centre
            down = d[:, 2] < -1e-9
            if car_pose is not None and plate is not None:
                with np.errstate(divide="ignore", invalid="ignore"):
                    k = np.where(down, (plate.z - o[2]) / d[:, 2], np.nan)
                hx, hy = o[0] + k * d[:, 0] - car_pose.x, o[1] + k * d[:, 1] - car_pose.y
                c, s = math.cos(car_pose.yaw), math.sin(car_pose.yaw)
                lx, ly = c * hx + s * hy, -s * hx + c * hy
                x0, x1, y0, y1 = plate.extent_xy
                on = down & (k > 0) & (lx > x0) & (lx < x1) & (ly > y0) & (ly < y1)
                sel = np.flatnonzero(on)
                sub = np.full(len(sel), plate.shade)
                for m in plate.markers:
                    cm, sm = math.cos(math.radians(m.yaw_deg)), math.sin(math.radians(m.yaw_deg))
                    mx, my = lx[sel] - m.x, ly[sel] - m.y
                    idx = np.zeros(len(sel), np.int64)
                    _shade_markers(cm * mx + sm * my, -sm * mx + cm * my, idx, np.array([m.side]),
                                   self.bits(m.marker_id)[None], sub)
                region[sel] = sub
            for occ in occluders:
                with np.errstate(divide="ignore", invalid="ignore"):
                    k = np.where(down, (occ.z - o[2]) / d[:, 2], np.nan)
                px, py = o[0] + k * d[:, 0], o[1] + k * d[:, 1]
                region[down & (k > 0) & (px > occ.x0) & (px < occ.x1) & (py > occ.y0) & (py < occ.y1)] = OCCLUDER
            h, w = by1 - by0, bx1 - bx0
            img[by0:by1, bx0:bx1] = region.reshape(h, ss, w, ss).mean(axis=(1, 3))
        if flash is not None:
            fx, fy, fw, fh, lit = flash
            img[fy:fy + fh, fx:fx + fw] = SCREEN_OFF
            img[fy:fy + int(round(fh * float(lit))), fx:fx + fw] = SCREEN_ON
            bbox = (min(fx, bbox[0]), min(fy, bbox[1]), max(fx + fw, bbox[2]), max(fy + fh, bbox[3])) if bbox else (
                fx, fy, fx + fw, fy + fh)
        margin = int(math.ceil(4 * blur)) + 1 if blur else 0
        w, h = cam.size
        self.last_bbox = None if bbox is None else (max(0, bbox[0] - margin), max(0, bbox[1] - margin),
                                                    min(w, bbox[2] + margin), min(h, bbox[3] + margin))
        if blur:
            img = cv2.GaussianBlur(img, (0, 0), blur)
        if noise and rng is not None:
            img = img + rng.standard_normal(img.shape, dtype=np.float32) * np.float32(noise)
        out = np.clip(np.rint(img), 0, 255).astype(np.uint8)
        if jpeg_quality:
            ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)])
            out = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
        return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


# ====================================================================== bộ thử ghi ra đĩa
def synthetic_intrinsics_record(name: str, K, D, size) -> dict:
    """Tệp nội tham dạng fisheye_calib của camera ảo ngoài hub: "synthetic": true, hub_port null, device "TỔNG HỢP"."""
    K, D = np.asarray(K, np.float64), np.asarray(D, np.float64)
    fov = fc.field_of_view(K, D, tuple(size))
    corners = [t for t in fov.get("theta_image_corners_deg") or [] if t is not None]
    return {"format": fc.FORMAT, "synthetic": True,
            "camera": {"hub_port": None, "name": name, "opencv_index": None, "source_id": f"cam_{name}",
                       "device": "TỔNG HỢP"},
            "image_size": [int(size[0]), int(size[1])], "model": "opencv_fisheye_kannala_brandt",
            "K": K.tolist(), "D": [float(x) for x in D], "rms_px": 0.0,
            "field_of_view_deg": {**fov, "theta_observed_max_deg": max(corners) if corners else None},
            "acceptance": {"status": "TỔNG HỢP — không phải hiệu chuẩn thật", "all_pass": True, "checks": []},
            "note": "TỔNG HỢP: camera ảo của overhead_synth, không phải camera thật",
            "created_local": datetime.now().isoformat(timespec="seconds")}


def camera_stamps(n: int, t0: float = 12345.0, pattern=STAMP_PATTERN) -> list[float]:
    """Stamp perf_counter tổng hợp: t0 rồi các khoảng `pattern` xen kẽ (31 / 48 ms)."""
    out, t = [], float(t0)
    for k in range(n):
        out.append(round(t, 6))
        t += pattern[k % len(pattern)]
    return out


def survey_layout(sandbox=(3.0, 2.0), step: float = 0.5, check_points: int = 8) -> list[dict]:
    """Mốc như `write_survey_template`: lưới kiểm soát mỗi `step`, điểm kiểm tra ở tâm các ô trải đều."""
    from autopark.evaluation.overhead_ref import _spread_cells

    sx, sy = sandbox
    nx, ny = int(round(sx / step)), int(round(sy / step))
    ids = iter(i for i in range(100) if i not in CAR_IDS)
    rows = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            x, y = i * step, j * step
            rows.append({"ten": f"K_x{round(x * 100):03d}_y{round(y * 100):03d}", "vai_tro": "kiem_soat",
                         "ma_aruco": next(ids), "x": x, "y": y})
    cells = [((i + 0.5) * step, (j + 0.5) * step) for j in range(ny) for i in range(nx)]
    for k, (x, y) in enumerate(sorted(_spread_cells(cells, check_points), key=lambda c: (c[1], c[0])), start=1):
        rows.append({"ten": f"T{k:02d}", "vai_tro": "kiem_tra", "ma_aruco": next(ids), "x": x, "y": y})
    return rows


def write_survey_csv(path, rows: list[dict], rng, *, tape_sigma_m: float = 0.0005, date: str | None = None) -> None:
    """Tệp mốc của bộ thử: tọa độ thật + nhiễu thước (σ 0,5 mm, cắt ở 3σ)."""
    date = date or datetime.now().strftime("%d/%m/%Y")
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["ten", "vai_tro", "x_m", "y_m", "z_m", "ma_aruco", "nguoi_do", "ngay", "ghi_chu"])
        for r in rows:
            dx, dy = np.clip(rng.normal(0.0, tape_sigma_m, 2), -3 * tape_sigma_m, 3 * tape_sigma_m)
            w.writerow([r["ten"], r["vai_tro"], f"{r['x'] + dx:.4f}", f"{r['y'] + dy:.4f}", "0", r["ma_aruco"],
                        "TONG_HOP", date, "tổng hợp"])


def vehicle_markers_record(*, measured: bool = True, synthetic: bool = True, side: float = 0.08,
                           z: float = CAR_GEOMETRY["z_m"], name: str = CAR_NAME) -> dict:
    g = CAR_GEOMETRY
    return {"format": MARKERS_FORMAT, "name": name, "measured": measured, "synthetic": synthetic,
            "dictionary": DEFAULT_DICTIONARY, "point": "tam_truc_sau",
            "markers": [{"id": 48, "role": "sau", "x_m": g["rear_x"], "y_m": 0.0, "z_m": z, "side_m": side,
                         "yaw_deg": 0.0},
                        {"id": 49, "role": "truoc", "x_m": g["front_x"], "y_m": 0.0, "z_m": z, "side_m": side,
                         "yaw_deg": 0.0}],
            "r2_points_m": g["r2"], "measured_by": "TONG_HOP", "date": datetime.now().strftime("%d/%m/%Y"),
            "notes": f"{SYNTHETIC_LABEL}: xe giả ảo của overhead_synth" if synthetic else ""}


def auto_focal(size, sandbox, height: float, margin_m: float = 0.12) -> float:
    """Tiêu cự (px) để cả sa bàn + `margin_m` nằm trong ảnh khi camera ở giữa, cao `height`."""
    w, h = size
    fx = (w / 2 - 6) / ((sandbox[0] / 2 + margin_m) / height)
    fy = (h / 2 - 6) / ((sandbox[1] / 2 + margin_m) / height)
    return 0.97 * min(fx, fy)


def run_motion(stamps: list[float], sandbox, *, speed: float = 0.1, stand_s: float = 1.5) -> list[Pose]:
    """Quỹ đạo của lần chạy tổng hợp: thẳng theo +x rồi rẽ trái (cung bán kính 1 m), đứng yên `stand_s` giây cuối."""
    t0 = stamps[0]
    move_end = max(0.0, stamps[-1] - t0 - stand_s)
    sx, sy = sandbox
    start = (0.30 * sx, 0.40 * sy)
    out = []
    for t in stamps:
        s = speed * min(t - t0, move_end)
        straight = 0.25 * sx
        if s <= straight:
            x, y, yaw = start[0] + s, start[1], 0.0
        else:
            a = (s - straight) / 1.0
            x, y, yaw = start[0] + straight + math.sin(a), start[1] + 1.0 - math.cos(a), a
        out.append(Pose(x, y, yaw))
    return out


def tc1_pose_set(sandbox, count: int = 10, inset: float = 0.28) -> list[Pose]:
    """Tư thế xe giả cho TC-1: tâm trục sau cách mỗi góc sa bàn `inset` theo hai trục (≈ 0,4 m, KICH_BAN 3.7 cần
    ≤ 0,5 m) với đầu xe hướng vào giữa sa bàn; các tư thế còn lại trải đều bên trong, hướng luân phiên."""
    sx, sy = sandbox
    poses = []
    for x, y in ((inset, inset), (sx - inset, inset), (sx - inset, sy - inset), (inset, sy - inset)):
        poses.append(Pose(x, y, math.atan2(sy / 2 - y, sx / 2 - x)))
    inner = [(0.5 * sx, 0.5 * sy), (0.3 * sx, 0.55 * sy), (0.7 * sx, 0.45 * sy), (0.5 * sx, 0.3 * sy),
             (0.5 * sx, 0.7 * sy), (0.35 * sx, 0.35 * sy), (0.65 * sx, 0.65 * sy), (0.6 * sx, 0.3 * sy)]
    for k, (x, y) in enumerate(inner):
        yaw = math.radians(HEADINGS_DEG[k % len(HEADINGS_DEG)])
        # tâm tấm xe (x xe ≈ 0,15) đặt ở chỗ đã chọn: tâm trục sau lùi lại nửa khoảng hai marker
        poses.append(Pose(x - 0.15 * math.cos(yaw), y - 0.15 * math.sin(yaw), yaw))
    return poses[:count]


def write_synthetic_set(out_dir, *, size=(1280, 720), sandbox=(3.0, 2.0), height: float = 2.3, frames: int = 300,
                        tc1_poses: int = 10, tc1_frames: int = 60, seed: int = 1,
                        floor_marker_m: float = 0.100, car_marker_m: float = 0.080, focal: float | None = None,
                        overwrite: bool = True) -> dict:
    """Ghi một bộ thử TỔNG HỢP vào `out_dir` (không bao giờ vào configs/, calibration/, docs/evidence/ của dự án).

    Gồm: `calibration/cam_tren_cao_tong_hop_<WxH>.json`, `moc_sa_ban.csv`, `san_trong.png`, `xe_gia_tong_hop.json`,
    `chay_01.{avi,frames.csv,events.csv,json}` (qua OverheadRecorder với stamp tổng hợp), `chay_01.truth.csv`,
    `tc1/*.avi` + `tc1_tong_hop.csv`, `README.txt`."""
    out = Path(out_dir)
    folder = forbidden_dir(out / "x")
    if folder is not None:
        raise OverheadError(f"bộ thử {SYNTHETIC_LABEL} không được ghi vào {folder}: chọn thư mục thử, ví dụ "
                            f"runs\\tren_cao\\tong_hop")
    if (out / "README.txt").exists() and not overwrite:
        raise OverheadError(f"{out} đã có bộ thử (README.txt): chọn thư mục khác")
    rng = np.random.default_rng(seed)
    size = (int(size[0]), int(size[1]))
    f = focal or auto_focal(size, sandbox, height)
    cam = SynthCamera.looking_down((sandbox[0] / 2 + 0.02, sandbox[1] / 2 - 0.03, height), heading_deg=1.2,
                                   tilt_deg=2.5, size=size, K=default_K(size, f))
    (out / "calibration").mkdir(parents=True, exist_ok=True)
    (out / "tc1").mkdir(parents=True, exist_ok=True)
    intr_path = out / "calibration" / f"cam_{CAMERA_NAME}_{size[0]}x{size[1]}.json"
    intr_path.write_text(json.dumps(synthetic_intrinsics_record(CAMERA_NAME, cam.K, cam.D, size), ensure_ascii=False,
                                    indent=1), encoding="utf-8")
    rows = survey_layout(sandbox)
    survey_path = out / "moc_sa_ban.csv"
    write_survey_csv(survey_path, rows, rng)
    floor = [FloorMarker(r["ten"], r["ma_aruco"], r["x"], r["y"], floor_marker_m) for r in rows]
    renderer = OverheadRenderer(cam, DEFAULT_DICTIONARY, floor)
    empty = renderer.frame(rng=rng)
    cv2.imwrite(str(out / "san_trong.png"), empty)
    car_record = vehicle_markers_record(side=car_marker_m)
    markers_path = out / f"{CAR_NAME}.json"
    markers_path.write_text(json.dumps(car_record, ensure_ascii=False, indent=1), encoding="utf-8")
    car = parse_vehicle_markers(car_record)
    plate = CarPlate.from_vehicle(car)
    # lần chạy: qua bộ ghi thật, stamp tổng hợp
    stamps = camera_stamps(frames)
    truth = run_motion(stamps, sandbox, stand_s=min(1.5, 0.7 * (stamps[-1] - stamps[0])))
    recorder = OverheadRecorder(out, "chay_01", synthetic=True, overwrite=True)
    recorder.start(size[0], size[1], {"name": CAMERA_NAME, "index": None, "device": "TỔNG HỢP"})
    for t, pose in zip(stamps, truth):
        recorder.add(renderer.frame(pose, plate, rng=rng), t)
    recorder.stop()
    with (out / "chay_01.truth.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["frame", "t_perf", "x_m", "y_m", "yaw_deg"])
        for k, (t, p) in enumerate(zip(stamps, truth)):
            w.writerow([k, f"{t:.6f}", f"{p.x:.6f}", f"{p.y:.6f}", f"{math.degrees(p.yaw):.4f}"])
    # TC-1: mỗi tư thế một đoạn ghi đứng yên, R2 = hai đầu thước + nhiễu thước (σ 1 mm, cắt ±2 mm)
    poses = tc1_pose_set(sandbox, tc1_poses)
    t1 = 20000.0
    pose_rows = []
    for k, pose in enumerate(poses, start=1):
        name = f"tu_the_{k:02d}"
        clip = camera_stamps(tc1_frames, t1)
        t1 = clip[-1] + 5.0
        rec = OverheadRecorder(out / "tc1", name, synthetic=True, overwrite=True)
        rec.start(size[0], size[1], {"name": CAMERA_NAME, "index": None, "device": "TỔNG HỢP"})
        for t in clip:
            rec.add(renderer.frame(pose, plate, rng=rng), t)
        rec.stop()
        ends = {}
        for role, (qx, qy) in car.r2_points.items():
            c, s = math.cos(pose.yaw), math.sin(pose.yaw)
            noise = np.clip(rng.normal(0.0, 0.001, 2), -0.002, 0.002)
            ends[role] = (pose.x + c * qx - s * qy + noise[0], pose.y + s * qx + c * qy + noise[1])
        duration = clip[-1] - clip[0]
        window = ("", "") if duration >= 2.5 else ("0", f"{duration + 0.001:.3f}")
        pose_rows.append([name, f"tc1/{name}.avi", *window, f"{ends['sau'][0]:.4f}", f"{ends['sau'][1]:.4f}",
                          f"{ends['truoc'][0]:.4f}", f"{ends['truoc'][1]:.4f}", "", "", "TONG_HOP",
                          datetime.now().strftime("%d/%m/%Y"), "tổng hợp"])
    tc1_path = out / "tc1_tong_hop.csv"
    with tc1_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["tu_the", "video", "t_tu_s", "t_den_s", "x_sau_m", "y_sau_m", "x_truoc_m", "y_truoc_m", "x_tam_m",
                    "y_tam_m", "nguoi_do", "ngay", "ghi_chu"])
        w.writerows(pose_rows)
    py = r".venv\Scripts\python.exe -X utf8 -m autopark.evaluation.overhead_ref"
    readme = "\n".join([
        f"{SYNTHETIC_LABEL}", "",
        f"Bộ thử T4 do autopark.evaluation.overhead_synth ghi ngày {datetime.now():%d/%m/%Y}: camera ảo {size[0]}×{size[1]} "
        f"(Kannala–Brandt đã biết, f ≈ {f:.0f} px) cao {height:g} m, sa bàn {sandbox[0]:g} × {sandbox[1]:g} m, "
        f"{len(floor)} marker sàn {floor_marker_m * 1000:.0f} mm, xe giả hai marker {car_marker_m * 1000:.0f} mm ở "
        f"{car.rear.z:g} m. Không phải số đo; không chép vào configs/, calibration/ hay docs/evidence/.", "",
        "Chuỗi lệnh (chạy trong thư mục autopark, mỗi lệnh một dòng):",
        f"{py} floor --intrinsics {intr_path} --survey {survey_path} --image {out / 'san_trong.png'} --out "
        f"{out / 'mat_san.json'}",
        f"{py} tc1 --floor {out / 'mat_san.json'} --markers {markers_path} --poses {tc1_path} --kind full --out "
        f"{out / 'tc1_tong_hop.json'}",
        f"{py} track --video {out / 'chay_01.avi'} --floor {out / 'mat_san.json'} --markers {markers_path} --tc1 "
        f"{out / 'tc1_tong_hop.json'} --out {out / 'chay_01_tham_chieu.csv'}",
        "", "So với tư thế thật: chay_01.truth.csv (frame, t_perf, x_m, y_m, yaw_deg của tâm trục sau).", ""])
    write_text_atomic(out / "README.txt", readme)
    return {"out": str(out), "intrinsics": str(intr_path), "survey": str(survey_path),
            "floor_image": str(out / "san_trong.png"), "markers": str(markers_path), "run": str(out / "chay_01.avi"),
            "truth": str(out / "chay_01.truth.csv"), "tc1_poses": str(tc1_path), "tc1_dir": str(out / "tc1"),
            "readme": str(out / "README.txt"), "focal_px": f, "camera": cam, "renderer": renderer, "plate": plate,
            "car": car, "truth_poses": truth, "stamps": stamps, "tc1_truth": poses, "floor_markers": floor}
