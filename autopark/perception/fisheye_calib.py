"""Hiệu chuẩn nội tham từng camera mắt cá bằng bảng ô vuông (kế hoạch giai đoạn 2, bước 4 "Hiệu chuẩn riêng từng camera").

    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.fisheye_calib board --paper A4
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.fisheye_calib calibrate --images runs/calib/<thư mục> --cols 9 --rows 6 --square-mm <cỡ ô ĐO ĐƯỢC> --port 1 --out calibration/cam_p1.json
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.fisheye_calib check calibration/cam_p1.json
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.fisheye_calib calibrate --images runs/calib/<thư mục> --square-mm <cỡ ô ĐO ĐƯỢC> --camera-name tren_cao

Mỗi lệnh viết trên một dòng để dán được vào cmd.exe lẫn PowerShell; thay `<...>` bằng giá trị thật trước khi chạy
(sửa 24/09/2026: bản trước ngắt lệnh `calibrate` thành hai dòng bằng `^` của cmd.exe). Dòng cuối (T11, thêm 02/10/2026):
camera KHÔNG qua hub 1..4 (camera trên cao) khóa theo tên thay cho cổng — tệp calibration/cam_tren_cao.json, bản ghi có
`camera.hub_port` null; tên không được có dạng p<số> hay kết thúc bằng _<rộng>x<cao> (`camera_name_error`). Ngoại tham
và BEV chỉ dùng tệp của camera xe theo cổng hub. Chỉ kiểm bằng ảnh tổng hợp; với camera trên cao thật CHƯA THỬ.

Mô hình: Kannala–Brandt của `cv2.fisheye` (4 hệ số): với tia có góc θ so với trục quang,
θ_d = θ·(1 + d1·θ² + d2·θ⁴ + d3·θ⁶ + d4·θ⁸), điểm ảnh = (fx·θ_d·cosφ + cx, fy·θ_d·sinφ + cy), skew cố định 0.
Mô hình này chỉ biểu diễn được θ < 90° (OpenCV dùng atan(r)), đủ cho ống kính quảng cáo 130° (chưa đo).

Việc của mô-đun (không cần Qt, không mở camera):
- dò góc bảng (`findChessboardCornersSB`, dự phòng `findChessboardCorners`), LUÔN tinh chỉnh bằng `cornerSubPix` (lý do
  và số đo ở `detect_corners`), kiểm từng ảnh: khung MJPEG hỏng (`truncated_rows`/`torn_bands` của
  `autopark.video.sources`), thấy trọn bảng, độ nét (độ rộng vùng chuyển đen→trắng của `estimateChessboardSharpness`),
  tương phản;
- bản đồ phủ: các góc đã thu rơi vào ô nào của lưới trên ảnh (mép và góc ảnh là nơi méo nhiều nhất, phải có điểm);
- `cv2.fisheye.calibrate` với CALIB_RECOMPUTE_EXTRINSIC | CALIB_FIX_SKEW, loại dần ảnh có RMS riêng quá lớn;
- ước lượng trường nhìn từ mô hình, và chuyển sang mô hình đa thức của dự án (`FisheyeIntrinsics`, dạng WoodScape
  ρ(θ) = k1·θ + k2·θ² + k3·θ³ + k4·θ⁴) bằng bình phương tối thiểu rồi lặp Lawson về nghiệm minimax, có báo sai số
  khớp lớn nhất theo điểm ảnh, nâng theta_max vừa đủ để mọi điểm ảnh (cả bốn góc) nghịch đảo được, và kiểm chéo bằng
  chính `FisheyeIntrinsics.project` / `unproject`;
- ghi một tệp JSON cho mỗi camera, khóa theo CỔNG HUB (index OpenCV đổi sau khởi động lại); camera ngoài hub khóa theo
  tên (T11, xem trên).

Tệp hiệu chuẩn chỉ có NỘI THAM: không có ngoại tham (vị trí/hướng so với xe). Ngoại tham đo bằng
`perception/extrinsics_calib.py` (giao diện `ui/roi_app.py`, từ 24/09/2026) và ghi vào
`configs/rig/camera_rig_extrinsics_v1.json`, xem docs/PHAN_CUNG_VA_HIEU_CHUAN.md#ngoai-tham; công cụ đó cần tệp nội tham này trước.
Các ngưỡng chấp nhận ở dưới là ĐỀ XUẤT, chưa kiểm trên camera thật.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
import json
import math
from pathlib import Path
import platform
import re
import sys
from typing import Sequence

import cv2
import numpy as np

from autopark.perception.calib_board import BoardSpec, add_board_args, run_board
from autopark.perception.calibration import FisheyeIntrinsics
from autopark.video.sources import IMAGE_EXTENSIONS, natural_key, torn_bands, truncated_rows

FORMAT = "autopark.fisheye_intrinsics/1"
DEFAULT_SIZE = (640, 480)          # mode chính thức của bốn camera qua hub (docs/DU_LIEU_VA_GIAY_PHEP.md)

# ---- ngưỡng (ĐỀ XUẤT, chưa kiểm trên camera thật) -------------------------------------------------------------------
MAX_EDGE_WIDTH_PX = 3.0      # độ rộng vùng chuyển đen→trắng; tài liệu OpenCV: "nên dưới ~3 px"
MIN_CONTRAST = 50.0          # độ sáng trung bình ô trắng − ô đen (0..255)
EDGE_MARGIN_PX = 3.0         # mọi góc trong phải cách mép ảnh ít nhất chừng này ("thấy trọn bảng")
COVERAGE_GRID = (8, 6)       # lưới phủ (cột, hàng) trên ảnh
MIN_IMAGES = 8               # dưới số này không hiệu chuẩn
OUTLIER_ABS_PX = 1.0         # một ảnh bị loại khi RMS riêng > max(OUTLIER_ABS_PX, OUTLIER_REL × trung vị) ...
OUTLIER_REL = 3.0            # ... và còn lại ≥ MIN_IMAGES ảnh
FIT_MAX_ERROR_PX = 0.5       # chuyển sang mô hình đa thức dự án: sai số khớp lớn nhất cho phép
ACCEPT = {                   # tiêu chí đề xuất cho một tệp hiệu chuẩn "dùng được"
    "rms_px": 0.5,
    "max_view_rms_px": 1.0,
    "images": 15,
    "coverage": 0.70,
    "corner_blocks": 4,
    "tilted_images": 4,
    "tilt_deg": 20.0,
    "fit_error_px": FIT_MAX_ERROR_PX,
}
MOTION_STILL_PX = 0.8        # tự chụp: dịch chuyển trung bình của các góc giữa hai khung liên tiếp ≤ chừng này
STILL_S = 0.5                # ... liên tục ít nhất chừng này giây
MIN_POSE_DISTANCE = 0.12     # ... và tư thế bảng khác mọi ảnh đã chụp ít nhất chừng này (xem pose_descriptor)
MIN_CAPTURE_INTERVAL_S = 1.0

NOT_ON_RIG_NOTE = ("Chưa gắn lên rig: tệp này chỉ có nội tham (K, D) của một camera, KHÔNG có ngoại tham (vị trí/hướng "
                   "camera so với xe). Ngoại tham đo riêng bằng perception/extrinsics_calib.py sau khi gá camera, ghi "
                   "vào configs/rig/camera_rig_extrinsics_v1.json (docs/PHAN_CUNG_VA_HIEU_CHUAN.md#ngoai-tham).")


def _flag(name: str) -> int:
    """Cờ của cv2.fisheye: OpenCV 4 để ở cv2.fisheye.CALIB_*, OpenCV 5 gộp vào cv2.CALIB_* (giá trị KHÁC nhau)."""
    value = getattr(cv2.fisheye, name, None)
    return int(value if value is not None else getattr(cv2, name))


CALIB_FLAGS = _flag("CALIB_RECOMPUTE_EXTRINSIC") | _flag("CALIB_FIX_SKEW")
CALIB_CRITERIA = (cv2.TERM_CRITERIA_COUNT + cv2.TERM_CRITERIA_EPS, 200, 1e-10)


# ---- dò góc và kiểm chất lượng từng ảnh -----------------------------------------------------------------------------
def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


@dataclass
class Detection:
    found: bool
    corners: np.ndarray | None = None      # (N, 2) float32, thứ tự từng hàng như BoardSpec.object_points
    method: str = ""                       # "sb" | "sb_exhaustive" | "classic", thêm "+subpix" khi đã tinh chỉnh
    reverted: int = 0                      # số góc cornerSubPix kéo đi quá xa nên giữ vị trí ban đầu


def _min_spacing(corners: np.ndarray, cols: int, rows: int) -> float:
    grid = corners.reshape(rows, cols, 2)
    return float(min(np.linalg.norm(np.diff(grid, axis=1), axis=2).min(), np.linalg.norm(np.diff(grid, axis=0), axis=2).min()))


def _subpix_window(corners: np.ndarray, cols: int, rows: int) -> int:
    """Nửa cửa sổ cornerSubPix: 0,4 × khoảng cách góc kề nhỏ nhất, trong [2, 5] — ô nhỏ ở mép ảnh mắt cá không để
    cửa sổ trùm sang góc bên cạnh."""
    return int(max(2, min(5, math.floor(0.4 * _min_spacing(corners, cols, rows)))))


def refine_corners(gray: np.ndarray, corners: np.ndarray, spec: BoardSpec) -> tuple[np.ndarray, int]:
    """cornerSubPix; góc nào bị kéo xa hơn 0,4 × khoảng cách góc kề nhỏ nhất (gần nửa đường tới góc bên cạnh) thì giữ
    vị trí ban đầu. Ngưỡng theo khoảng cách góc, không theo cửa sổ: trên ảnh tổng hợp có bảng nhỏ ở góc ảnh mà SB lệch
    1,5 px và cornerSubPix sửa đúng — chặn ở 1 px thì giữ lại chính các góc sai đó."""
    win = _subpix_window(corners, spec.cols, spec.rows)
    refined = cv2.cornerSubPix(gray, corners.reshape(-1, 1, 2).astype(np.float32).copy(), (win, win), (-1, -1),
                               (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_COUNT, 50, 1e-3)).reshape(-1, 2)
    moved = np.linalg.norm(refined - corners, axis=1)
    bad = ~np.isfinite(moved) | (moved > 0.4 * _min_spacing(corners, spec.cols, spec.rows))
    refined[bad] = corners[bad]
    return refined.astype(np.float32), int(bad.sum())


DETECT_MODES = ("live", "accurate")


def _full(ok, corners, spec: BoardSpec) -> np.ndarray | None:
    if ok and corners is not None and len(corners) == spec.n_corners:
        return corners.reshape(-1, 2).astype(np.float32)
    return None


def detect_corners(image: np.ndarray, spec: BoardSpec, mode: str = "accurate") -> Detection:
    """Tìm đủ `cols × rows` góc trong rồi tinh chỉnh bằng `cornerSubPix`.

    - "live": `findChessboardCornersSB` không EXHAUSTIVE (~14 ms/khung trên ảnh tổng hợp 640×480, máy bàn i9) — xem trực
      tiếp; khung không thấy bảng thì dừng ở đó.
    - "accurate": như "live"; không thấy thì thử SB EXHAUSTIVE | ACCURACY, rồi `findChessboardCorners` — ảnh đã chụp.

    Vì sao luôn tinh chỉnh (đo trên 21 ảnh tổng hợp của tests/test_fisheye_calib.py, camera KB đã biết): góc SB (kể cả
    ACCURACY) lệch trung bình 0,12 px và lệch CÓ HỆ THỐNG — fx ra 352,07 thay vì 351,0 (0,3 %), mô hình sai tới 2,3 px ở
    góc ảnh; thêm cornerSubPix thì góc lệch 0,06 px, fx 351,04, sai số mô hình ≤ 0,49 px (trung vị 0,05). Chưa kiểm trên
    ảnh camera thật (nén MJPEG, mờ thật)."""
    if mode not in DETECT_MODES:
        raise ValueError(f"mode phải là một trong {DETECT_MODES}")
    gray = to_gray(image)
    pattern = spec.pattern_size
    corners, method = _full(*cv2.findChessboardCornersSB(gray, pattern, flags=cv2.CALIB_CB_NORMALIZE_IMAGE), spec), "sb"
    if corners is None and mode == "accurate":
        flags = cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
        corners, method = _full(*cv2.findChessboardCornersSB(gray, pattern, flags=flags), spec), "sb_exhaustive"
        if corners is None:
            flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
            corners, method = _full(*cv2.findChessboardCorners(gray, pattern, flags=flags), spec), "classic"
    if corners is None:
        return Detection(False)
    refined, reverted = refine_corners(gray, corners, spec)
    return Detection(True, refined, method + "+subpix", reverted)


def damage_reason(image: np.ndarray) -> str | None:
    """Khung MJPEG bị cắt cụt hoặc có dải xé (bộ giải mã tô vân khối 8×8) — không được dùng để hiệu chuẩn."""
    rows = truncated_rows(image)
    if rows:
        return f"khung bị cắt cụt ({rows}/{image.shape[0]} dòng đáy do bộ giải mã tô)"
    bands = torn_bands(image)
    if bands:
        return f"khung có {bands} dải xé giữa ảnh"
    return None


@dataclass
class FrameQuality:
    found: bool
    method: str = ""
    damaged: str | None = None
    edge_width_px: float | None = None      # độ rộng vùng chuyển đen→trắng (nhỏ = nét)
    contrast: float | None = None
    min_margin_px: float | None = None      # khoảng cách nhỏ nhất từ góc trong tới mép ảnh
    board_area_frac: float | None = None    # diện tích tứ giác 4 góc ngoài / diện tích ảnh
    subpix_reverted: int = 0                # số góc cornerSubPix kéo quá xa (giữ vị trí SB)
    reasons: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.reasons

    def to_dict(self) -> dict:
        r = lambda x, nd=3: None if x is None else round(float(x), nd)
        return {"found": self.found, "method": self.method, "damaged": self.damaged, "edge_width_px": r(self.edge_width_px),
                "contrast": r(self.contrast, 1), "min_margin_px": r(self.min_margin_px, 1),
                "board_area_frac": r(self.board_area_frac, 4), "subpix_reverted": self.subpix_reverted, "ok": self.ok,
                "reasons": list(self.reasons)}


def _quad_area(corners: np.ndarray, spec: BoardSpec) -> float:
    g = corners.reshape(spec.rows, spec.cols, 2)
    quad = np.array([g[0, 0], g[0, -1], g[-1, -1], g[-1, 0]], np.float64)
    x, y = quad[:, 0], quad[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def assess_frame(image: np.ndarray, spec: BoardSpec, *, mode: str = "accurate", max_edge_width: float = MAX_EDGE_WIDTH_PX,
                 min_contrast: float = MIN_CONTRAST, edge_margin: float = EDGE_MARGIN_PX) -> tuple[Detection, FrameQuality]:
    """Dò bảng và chấm một khung. Khung hỏng không được dò (trả về ngay)."""
    damaged = damage_reason(image)
    if damaged:
        return Detection(False), FrameQuality(False, damaged=damaged, reasons=[damaged])
    det = detect_corners(image, spec, mode=mode)
    if not det.found:
        return det, FrameQuality(False, reasons=[f"không thấy đủ {spec.cols}×{spec.rows} góc trong của bảng"])
    h, w = image.shape[:2]
    c = det.corners
    margin = float(min(c[:, 0].min(), c[:, 1].min(), (w - 1) - c[:, 0].max(), (h - 1) - c[:, 1].max()))
    q = FrameQuality(True, det.method, min_margin_px=margin, board_area_frac=_quad_area(c, spec) / float(w * h),
                     subpix_reverted=det.reverted)
    try:
        stats = cv2.estimateChessboardSharpness(to_gray(image), spec.pattern_size, c.reshape(-1, 1, 2))[0]
        # OpenCV trả 9999 / tương phản 0 khi không dựng được mặt cắt biên nào (thấy với ô ~8 px trên ảnh tổng hợp):
        # đó là "không đo được", không phải "mờ"
        if math.isfinite(stats[0]) and 0 < stats[0] < 1000:
            q.edge_width_px, q.contrast = float(stats[0]), float(stats[2] - stats[1])
    except cv2.error:
        pass                                    # không đo được thì không chặn; trạng thái ghi "không đo được"
    if margin < edge_margin:
        q.reasons.append(f"bảng sát mép ảnh ({margin:.1f} px)")
    if q.edge_width_px is not None and q.edge_width_px > max_edge_width:
        q.reasons.append(f"mờ: biên rộng {q.edge_width_px:.1f} px > {max_edge_width:g}")
    if q.contrast is not None and q.contrast < min_contrast:
        q.reasons.append(f"tương phản thấp ({q.contrast:.0f} < {min_contrast:g})")
    return det, q


# ---- đa dạng tư thế và tự chụp ------------------------------------------------------------------------------------
POSE_WEIGHTS = np.array([1.0, 1.0, 2.0, 2.0, 2.0, 0.5])


def pose_descriptor(corners: np.ndarray, spec: BoardSpec, image_size: tuple[int, int]) -> np.ndarray:
    """Vector thô mô tả bảng TRÊN ẢNH (không cần hiệu chuẩn): tâm (chuẩn hóa theo cỡ ảnh), cỡ (căn diện tích / đường
    chéo ảnh), độ nghiêng phối cảnh theo hai trục (chênh lệch cạnh đối), góc xoay trong mặt phẳng ảnh (chia π).
    Thứ tự góc bị đảo (bảng xoay 180°) được đưa về một chiều để hai lần thấy cùng một tư thế cho cùng vector."""
    w, h = image_size
    g = np.asarray(corners, np.float64).reshape(spec.rows, spec.cols, 2)
    if g[0, -1, 0] < g[0, 0, 0]:                 # hàng đầu chạy sang trái: đảo thứ tự
        g = g[::-1, ::-1]
    tl, tr, bl, br = g[0, 0], g[0, -1], g[-1, 0], g[-1, -1]
    top, bottom = np.linalg.norm(tr - tl), np.linalg.norm(br - bl)
    left, right = np.linalg.norm(bl - tl), np.linalg.norm(br - tr)
    size = math.sqrt(_quad_area(g.reshape(-1, 2).astype(np.float32), spec)) / math.hypot(w, h)
    angle = math.atan2(tr[1] - tl[1], tr[0] - tl[0]) / math.pi
    centre = g.reshape(-1, 2).mean(axis=0)
    return np.array([centre[0] / w, centre[1] / h, size, (top - bottom) / max(top + bottom, 1e-9),
                     (left - right) / max(left + right, 1e-9), angle])


def pose_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm((np.asarray(a) - np.asarray(b)) * POSE_WEIGHTS))


class AutoCaptureGate:
    """Quyết định khi nào tự chụp: bảng đạt chất lượng, đứng yên đủ lâu, khác mọi ảnh đã chụp, cách lần chụp trước đủ lâu.

    `update()` gọi với mỗi khung đã dò; trả (nên chụp?, lý do/trạng thái). Người gọi chụp thì gọi `captured(t)`."""

    def __init__(self, still_px: float = MOTION_STILL_PX, still_s: float = STILL_S,
                 min_pose_distance: float = MIN_POSE_DISTANCE, min_interval_s: float = MIN_CAPTURE_INTERVAL_S):
        self.still_px, self.still_s = still_px, still_s
        self.min_pose_distance, self.min_interval_s = min_pose_distance, min_interval_s
        self._prev: np.ndarray | None = None
        self._still_since: float | None = None
        self._last_capture_t: float | None = None
        self.motion_px: float | None = None

    def reset(self) -> None:
        self._prev, self._still_since, self.motion_px = None, None, None

    def update(self, t: float, corners: np.ndarray | None, quality_ok: bool,
               descriptor: np.ndarray | None, previous: Sequence[np.ndarray]) -> tuple[bool, str]:
        if corners is None:
            self.reset()
            return False, "chưa thấy bảng"
        c = np.asarray(corners, np.float64).reshape(-1, 2)
        if self._prev is not None and self._prev.shape == c.shape:
            self.motion_px = float(np.linalg.norm(c - self._prev, axis=1).mean())
            if self.motion_px > self.still_px:
                self._still_since = None
            elif self._still_since is None:
                self._still_since = t
        else:
            self.motion_px, self._still_since = None, None
        self._prev = c
        if not quality_ok:
            return False, "chất lượng chưa đạt"
        if self._still_since is None or t - self._still_since < self.still_s:
            return False, "chờ bảng đứng yên"
        if self._last_capture_t is not None and t - self._last_capture_t < self.min_interval_s:
            return False, "vừa chụp"
        if descriptor is not None and previous:
            nearest = min(pose_distance(descriptor, p) for p in previous)
            if nearest < self.min_pose_distance:
                return False, f"trùng tư thế đã chụp ({nearest:.2f} < {self.min_pose_distance:g}); đổi vị trí/góc nghiêng"
        return True, "chụp"

    def captured(self, t: float) -> None:
        self._last_capture_t = t
        self._still_since = None


# ---- bản đồ phủ ---------------------------------------------------------------------------------------------------
def coverage_counts(corner_sets: Sequence[np.ndarray], image_size: tuple[int, int],
                    grid: tuple[int, int] = COVERAGE_GRID) -> np.ndarray:
    """Số góc (của mọi ảnh) rơi vào mỗi ô lưới `grid` = (cột, hàng) trên ảnh; mảng (hàng, cột)."""
    w, h = image_size
    gw, gh = grid
    counts = np.zeros((gh, gw), np.int64)
    for corners in corner_sets:
        c = np.asarray(corners, np.float64).reshape(-1, 2)
        ix = np.clip((c[:, 0] + 0.5) * gw / w, 0, gw - 1).astype(int)
        iy = np.clip((c[:, 1] + 0.5) * gh / h, 0, gh - 1).astype(int)
        np.add.at(counts, (iy, ix), 1)
    return counts


def coverage_summary(counts: np.ndarray) -> dict:
    gh, gw = counts.shape
    covered = counts > 0
    border = np.zeros_like(covered)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    bh, bw = max(1, gh // 4), max(1, gw // 4)            # khối góc: 2×1 ô với lưới 8×6 → dùng ≥ 1/4 mỗi chiều
    bh, bw = max(bh, 2 if gh >= 4 else 1), max(bw, 2 if gw >= 4 else 1)
    blocks = {"tl": covered[:bh, :bw].any(), "tr": covered[:bh, -bw:].any(),
              "bl": covered[-bh:, :bw].any(), "br": covered[-bh:, -bw:].any()}
    return {"grid": [gw, gh], "cells_covered": int(covered.sum()), "cells_total": int(covered.size),
            "fraction": round(float(covered.mean()), 4), "border_fraction": round(float(covered[border].mean()), 4),
            "corner_blocks": {k: bool(v) for k, v in blocks.items()}, "counts": counts.astype(int).tolist()}


def draw_coverage(image: np.ndarray, counts: np.ndarray, alpha: float = 0.35, full_at: int = 20) -> np.ndarray:
    """Tô lưới phủ lên ảnh: đỏ = chưa có góc nào, xanh đậm dần theo số góc (bão hòa ở `full_at`)."""
    h, w = image.shape[:2]
    gh, gw = counts.shape
    tint = np.zeros_like(image)
    for iy in range(gh):
        for ix in range(gw):
            y0, y1 = iy * h // gh, (iy + 1) * h // gh
            x0, x1 = ix * w // gw, (ix + 1) * w // gw
            n = int(counts[iy, ix])
            tint[y0:y1, x0:x1] = (40, 40, 220) if n == 0 else (40, int(120 + 135 * min(1.0, n / full_at)), 40)
    out = cv2.addWeighted(image, 1.0 - alpha, tint, alpha, 0.0)
    for iy in range(1, gh):
        cv2.line(out, (0, iy * h // gh), (w - 1, iy * h // gh), (200, 200, 200), 1)
    for ix in range(1, gw):
        cv2.line(out, (ix * w // gw, 0), (ix * w // gw, h - 1), (200, 200, 200), 1)
    return out


# ---- mô hình Kannala–Brandt: θ, trường nhìn ---------------------------------------------------------------------------
def theta_d(theta, D) -> np.ndarray:
    t = np.asarray(theta, np.float64)
    d = np.asarray(D, np.float64).ravel()
    t2 = t * t
    return t * (1 + t2 * (d[0] + t2 * (d[1] + t2 * (d[2] + t2 * d[3]))))


def monotonic_limit(D, samples: int = 20001) -> tuple[np.ndarray, np.ndarray]:
    """Bảng (θ_d, θ) trên đoạn θ ∈ [0, 90°) mà θ_d còn tăng nghiêm ngặt; ngoài đoạn này mô hình không nghịch đảo được."""
    thetas = np.linspace(0.0, math.pi / 2 - 1e-6, samples)
    td = theta_d(thetas, D)
    bad = np.flatnonzero(np.diff(td) <= 0)
    n = samples if not len(bad) else int(bad[0]) + 1
    return td[:n], thetas[:n]


def pixel_theta(u, v, K, D) -> np.ndarray:
    """Góc θ (rad) so với trục quang của tia qua điểm ảnh (u, v); NaN nếu ngoài vùng mô hình nghịch đảo được."""
    K = np.asarray(K, np.float64)
    x = (np.asarray(u, np.float64) - K[0, 2]) / K[0, 0]
    y = (np.asarray(v, np.float64) - K[1, 2]) / K[1, 1]
    td, thetas = monotonic_limit(D)
    return np.interp(np.hypot(x, y), td, thetas, right=np.nan)


def pixel_rays(u, v, K, D) -> np.ndarray:
    """Tia đơn vị (N, 3) trong hệ camera (X phải, Y xuống, Z trước) cho các điểm ảnh."""
    K = np.asarray(K, np.float64)
    x = (np.asarray(u, np.float64).ravel() - K[0, 2]) / K[0, 0]
    y = (np.asarray(v, np.float64).ravel() - K[1, 2]) / K[1, 1]
    rd = np.hypot(x, y)
    theta = pixel_theta(np.asarray(u, np.float64).ravel(), np.asarray(v, np.float64).ravel(), K, D)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where(rd > 1e-12, np.sin(theta) / rd, 0.0)
    return np.column_stack([x * s, y * s, np.cos(theta)])


def _angle_deg(rays: np.ndarray, a: int, b: int) -> float | None:
    if not np.all(np.isfinite(rays[[a, b]])):
        return None
    return math.degrees(math.acos(float(np.clip(rays[a] @ rays[b], -1.0, 1.0))))


def field_of_view(K, D, image_size: tuple[int, int]) -> dict:
    """Trường nhìn suy từ mô hình (không phải đo trực tiếp): góc giữa tia qua hai mép đối diện của ảnh, qua tâm quang
    học theo chiều ngang/dọc, và qua hai góc đối diện theo đường chéo. Ngoài vùng đã thấy bảng là ngoại suy."""
    w, h = image_size
    K = np.asarray(K, np.float64)
    cx, cy = K[0, 2], K[1, 2]
    pts = np.array([[-0.5, cy], [w - 0.5, cy], [cx, -0.5], [cx, h - 0.5],
                    [-0.5, -0.5], [w - 0.5, h - 0.5], [w - 0.5, -0.5], [-0.5, h - 0.5]])
    rays = pixel_rays(pts[:, 0], pts[:, 1], K, D)
    diag = [a for a in (_angle_deg(rays, 4, 5), _angle_deg(rays, 6, 7)) if a is not None]
    corners = np.array([[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]], np.float64)
    theta_c = pixel_theta(corners[:, 0], corners[:, 1], K, D)
    r = lambda x: None if x is None or not np.isfinite(x) else round(float(x), 2)
    return {"horizontal_deg": r(_angle_deg(rays, 0, 1)), "vertical_deg": r(_angle_deg(rays, 2, 3)),
            "diagonal_deg": r(max(diag)) if len(diag) == 2 else None,
            "theta_image_corners_deg": [r(math.degrees(t)) if np.isfinite(t) else None for t in theta_c],
            "model_monotonic_limit_deg": r(math.degrees(monotonic_limit(D)[1][-1]))}


# ---- chuyển sang mô hình đa thức của dự án (FisheyeIntrinsics, dạng WoodScape) -----------------------------------------
def radial_poly(k, theta) -> np.ndarray:
    """ρ(θ) = k1·θ + k2·θ² + k3·θ³ + k4·θ⁴ — cùng công thức `FisheyeIntrinsics.theta_to_rho`."""
    t = np.asarray(theta, np.float64)
    return t * (k[0] + t * (k[1] + t * (k[2] + t * k[3])))


def radial_poly_error(K, D, k, theta_max: float, samples: int = 2001) -> tuple[float, float]:
    """(sai số lớn nhất, sai số RMS) theo điểm ảnh của đa thức `k` so với fx·θ_d(θ) trên θ ∈ [0, theta_max]; sai số
    theo chiều dọc nhân thêm tỉ lệ fy/fx."""
    K = np.asarray(K, np.float64)
    th = np.linspace(0.0, float(theta_max), samples)
    err = np.abs(radial_poly(k, th) - K[0, 0] * theta_d(th, D)) * max(1.0, K[1, 1] / K[0, 0])
    return float(err.max()), float(np.sqrt(np.mean(err ** 2)))


def fit_radial_poly(K, D, theta_max: float, samples: int = 2001,
                    lawson_iterations: int = 60) -> tuple[tuple[float, float, float, float], float, float]:
    """Khớp ρ(θ) = k1·θ + k2·θ² + k3·θ³ + k4·θ⁴ (điểm ảnh) vào fx·θ_d(θ) trên θ ∈ [0, theta_max].

    Bắt đầu bằng bình phương tối thiểu, rồi lặp Lawson (trọng số nhân với |sai số|) để kéo về nghiệm minimax — sai số
    của bình phương tối thiểu dồn ở hai đầu đoạn, mà cái cần chặn là sai số LỚN NHẤT. Trên camera tổng hợp của test
    (θ tới 68,5°): bình phương tối thiểu 0,077 px lớn nhất, sau Lawson 0,035 px. Giữ nghiệm có sai số lớn nhất nhỏ nhất.
    Trả (k, sai số lớn nhất, sai số RMS) theo điểm ảnh; sai số theo chiều dọc nhân thêm tỉ lệ fy/fx."""
    K = np.asarray(K, np.float64)
    th = np.linspace(0.0, float(theta_max), samples)
    target = K[0, 0] * theta_d(th, D)
    A = np.column_stack([th, th ** 2, th ** 3, th ** 4])
    k, *_ = np.linalg.lstsq(A, target, rcond=None)
    best_k, best_max = k, float(np.abs(A @ k - target).max())
    w = np.full(samples, 1.0 / samples)
    for _ in range(lawson_iterations):
        sw = np.sqrt(w)
        k, *_ = np.linalg.lstsq(A * sw[:, None], target * sw, rcond=None)
        e = np.abs(A @ k - target)
        if e.max() < best_max:
            best_k, best_max = k, float(e.max())
        w = w * e
        total = w.sum()
        if not np.isfinite(total) or total <= 0:
            break
        w /= total
    best = tuple(float(x) for x in best_k)
    return (best, *radial_poly_error(K, D, best, theta_max, samples))


def projection_check(intr: FisheyeIntrinsics, K, D, samples: int = 4000, seed: int = 0) -> float | None:
    """Sai lệch lớn nhất (điểm ảnh) giữa `FisheyeIntrinsics.project` và `cv2.fisheye.projectPoints` trên các tia ngẫu
    nhiên θ ∈ [0, theta_max] mà `FisheyeIntrinsics` coi là hợp lệ (trong ảnh)."""
    rng = np.random.default_rng(seed)
    theta = rng.uniform(0.0, intr.theta_max, samples)
    phi = rng.uniform(0.0, 2 * math.pi, samples)
    pts = np.column_stack([np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)])
    uv_cv = cv2.fisheye.projectPoints(pts.reshape(1, -1, 3), np.zeros(3), np.zeros(3), np.asarray(K, np.float64),
                                      np.asarray(D, np.float64).reshape(4, 1))[0].reshape(-1, 2)
    u, v, valid = intr.project(pts)
    if not valid.any():
        return None
    return float(np.hypot(u[valid] - uv_cv[valid, 0], v[valid] - uv_cv[valid, 1]).max())


def _raise_until_reached(k, rho_need: float, theta_lo: float, theta_limit: float, step: float = 1e-3) -> float | None:
    """θ nhỏ nhất (chia đôi, sai tới ~1e-15 rad) trong [theta_lo, theta_limit] mà ρ_poly(θ) ≥ rho_need; None nếu tới
    theta_limit đa thức vẫn chưa đạt."""
    poly = lambda t: float(radial_poly(k, t))
    if poly(theta_lo) >= rho_need:
        return theta_lo
    lo, hi = theta_lo, min(theta_limit, theta_lo + step)
    while poly(hi) < rho_need:
        if hi >= theta_limit:
            return None
        lo, hi = hi, min(theta_limit, hi + step)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if poly(mid) < rho_need else (lo, mid)
    return hi


def woodscape_intrinsics(K, D, image_size: tuple[int, int], *, max_error_px: float = FIT_MAX_ERROR_PX,
                         theta_max: float | None = None) -> dict:
    """Khối "radial_poly" cho `FisheyeIntrinsics` (cùng khóa với tệp WoodScape, thêm theta_max và số kiểm).

    theta_max mặc định: θ (theo mô hình KB) lớn nhất ở bốn điểm ảnh góc (0,0)…(W−1,H−1), rồi NÂNG vừa đủ để ρ_poly(theta_max)
    chạm bán kính của điểm ảnh góc xa nhất (đo đúng như `FisheyeIntrinsics.unproject`). Lý do: nghiệm minimax có thể hụt
    ở đầu đoạn — trên kết quả hiệu chuẩn 21 ảnh tổng hợp, ρ_poly(θ_góc) = 405,506 px trong khi góc ảnh (0, 479) ở bán
    kính 405,522 px, nên điểm ảnh đó ra NaN. Phần nâng thêm ghi ở `theta_max_raise_deg` (cỡ phần nghìn độ khi sai số
    khớp nhỏ); `theta_max_deg` làm tròn LÊN để làm tròn không kéo lại xuống dưới góc ảnh; sai số khớp tính trên đoạn đã
    nâng. Nhờ vậy mọi điểm ảnh trong ảnh đều nghịch đảo được — hàm tự kiểm điều này trên bốn góc ảnh.

    `ok` = đa thức tăng đơn điệu tới theta_max, bốn góc ảnh nghịch đảo được, VÀ sai số khớp lớn nhất ≤ max_error_px;
    không ok thì đừng dùng (`load_intrinsics` từ chối)."""
    w, h = image_size
    K = np.asarray(K, np.float64)
    cx_offset, cy_offset = float(K[0, 2] - (w / 2 - 0.5)), float(K[1, 2] - (h / 2 - 0.5))
    aspect = float(K[1, 1] / K[0, 0])
    corners = np.array([[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]], np.float64)
    # bán kính ρ của điểm ảnh góc tính y như FisheyeIntrinsics.unproject (cx = W/2 − 0,5 + cx_offset, chia tỉ lệ dọc)
    rho_corner = float(np.hypot(corners[:, 0] - (w / 2 - 0.5 + cx_offset), (corners[:, 1] - (h / 2 - 0.5 + cy_offset)) / aspect).max())
    source, theta_corner, reach_reason = "given", None, None
    if theta_max is None:
        tc = pixel_theta(corners[:, 0], corners[:, 1], K, D)
        if np.all(np.isfinite(tc)):
            theta_max, source = float(tc.max()), "image_corners"
            theta_corner = theta_max
        else:
            theta_max, source = float(monotonic_limit(D)[1][-1]), "model_monotonic_limit"
    theta_max = float(theta_max)
    k, max_err, rms_err = fit_radial_poly(K, D, theta_max)
    theta_store = math.ceil(math.degrees(theta_max) * 1e4) / 1e4
    if source == "image_corners":
        raised = _raise_until_reached(k, rho_corner, theta_max, math.pi / 2)
        if raised is None:
            reach_reason = "đa thức không đạt tới bán kính của góc ảnh trước 90°"
        else:
            theta_store = math.ceil(math.degrees(raised) * 1e4) / 1e4
            for _ in range(100):                       # làm tròn dấu phẩy động: tăng từng 1e-4° tới khi chắc chắn chạm
                if float(radial_poly(k, math.radians(theta_store))) >= rho_corner:
                    break
                theta_store = round(theta_store + 1e-4, 4)
            max_err, rms_err = radial_poly_error(K, D, k, math.radians(theta_store))
    block = {"model": "radial_poly", "poly_order": 4, "width": int(w), "height": int(h),
             "k1": k[0], "k2": k[1], "k3": k[2], "k4": k[3],
             "cx_offset": cx_offset, "cy_offset": cy_offset, "aspect_ratio": aspect,
             "theta_max_deg": theta_store, "theta_max_source": source,
             "theta_image_corner_deg": None if theta_corner is None else round(math.degrees(theta_corner), 4),
             "theta_max_raise_deg": None if theta_corner is None else round(theta_store - math.degrees(theta_corner), 5),
             "max_fit_error_px": round(max_err, 4), "rms_fit_error_px": round(rms_err, 4),
             "max_error_allowed_px": max_error_px, "projection_check_max_px": None, "monotonic": False,
             "corners_invertible": False, "ok": False, "reason": None}
    reasons = []
    try:
        intr = intrinsics_from_block(block)
        block["monotonic"] = True
        block["corners_invertible"] = bool(np.all(np.isfinite(intr.unproject(corners[:, 0], corners[:, 1]))))
        check = projection_check(intr, K, D)
        block["projection_check_max_px"] = None if check is None else round(check, 4)
    except ValueError as exc:
        reasons.append(f"đa thức không tăng đơn điệu tới theta_max: {exc}")
    if source == "model_monotonic_limit":
        reasons.append("góc ảnh vượt vùng mô hình KB nghịch đảo được; theta_max lấy theo giới hạn đơn điệu")
    if block["monotonic"] and not block["corners_invertible"]:
        reasons.append(reach_reason or "góc ảnh không nghịch đảo được bằng đa thức (ρ_poly(theta_max) nhỏ hơn bán kính "
                                       "của điểm ảnh góc)")
    if block["monotonic"] and max_err > max_error_px:
        reasons.append(f"sai số khớp {max_err:.3f} px > {max_error_px:g} px")
    block["reason"] = "; ".join(reasons) or None
    block["ok"] = (block["monotonic"] and block["corners_invertible"] and max_err <= max_error_px
                   and source != "model_monotonic_limit")
    return block


def intrinsics_from_block(block: dict) -> FisheyeIntrinsics:
    """Khối "radial_poly" → `FisheyeIntrinsics` (theta_max lấy từ khối; từ 24/09 CameraCalibration.from_dict cũng đọc theta_max_deg khi có)."""
    return FisheyeIntrinsics(int(block["width"]), int(block["height"]),
                             (float(block["k1"]), float(block["k2"]), float(block["k3"]), float(block["k4"])),
                             float(block["cx_offset"]), float(block["cy_offset"]), float(block["aspect_ratio"]),
                             math.radians(float(block["theta_max_deg"])))


# ---- hiệu chuẩn ----------------------------------------------------------------------------------------------------
class CalibrationError(RuntimeError):
    pass


@dataclass
class ViewResult:
    name: str
    used: bool
    rms_px: float | None = None             # RMS chiếu lại của ảnh này (ảnh bị loại: dưới mô hình cuối, qua solvePnP)
    max_error_px: float | None = None
    reason: str | None = None               # lý do bị loại
    distance_m: float | None = None         # khoảng cách camera → tâm bảng (theo cỡ ô đã nhập)
    tilt_deg: float | None = None           # góc giữa pháp tuyến bảng và đường nhìn tới tâm bảng

    def to_dict(self) -> dict:
        r = lambda x, nd=4: None if x is None else round(float(x), nd)
        return {"name": self.name, "used": self.used, "rms_px": r(self.rms_px), "max_error_px": r(self.max_error_px),
                "rejected_reason": self.reason, "distance_m": r(self.distance_m), "tilt_deg": r(self.tilt_deg, 2)}


@dataclass
class FisheyeCalibration:
    image_size: tuple[int, int]
    K: np.ndarray
    D: np.ndarray                            # (4,)
    rms_px: float                            # sqrt(trung bình bình phương khoảng cách chiếu lại) trên mọi góc của ảnh dùng
    opencv_rms: float                        # số cv2.fisheye.calibrate trả về (định nghĩa của OpenCV)
    views: list[ViewResult]
    rounds: int
    flags: int
    used_corners: list[np.ndarray] = field(default_factory=list)

    @property
    def n_used(self) -> int:
        return sum(v.used for v in self.views)

    @property
    def max_view_rms_px(self) -> float:
        return max(v.rms_px for v in self.views if v.used)


def _as_obj(spec: BoardSpec) -> np.ndarray:
    return spec.object_points().reshape(1, -1, 3)           # OpenCV 5 cần (1, N, 3); (N, 1, 3) báo lỗi kích thước


def _view_errors(obj: np.ndarray, corners: np.ndarray, rvec, tvec, K, D) -> np.ndarray:
    proj = cv2.fisheye.projectPoints(obj, np.asarray(rvec, np.float64).reshape(3, 1), np.asarray(tvec, np.float64).reshape(3, 1),
                                     K, D.reshape(4, 1))[0].reshape(-1, 2)
    return np.linalg.norm(proj - corners.reshape(-1, 2), axis=1)


def _pose_stats(spec: BoardSpec, rvec, tvec) -> tuple[float, float]:
    R = cv2.Rodrigues(np.asarray(rvec, np.float64).reshape(3, 1))[0]
    centre_b = np.array([(spec.cols - 1) / 2, (spec.rows - 1) / 2, 0.0]) * spec.square_mm / 1000.0
    centre = R @ centre_b + np.asarray(tvec, np.float64).ravel()
    dist = float(np.linalg.norm(centre))
    cos_tilt = abs(float(R[:, 2] @ centre)) / max(dist, 1e-12)
    return dist, math.degrees(math.acos(min(1.0, cos_tilt)))


def _run_calibrate(obj: np.ndarray, corners: list[np.ndarray], image_size, flags: int):
    imgs = [c.reshape(1, -1, 2).astype(np.float64) for c in corners]
    return cv2.fisheye.calibrate([obj] * len(imgs), imgs, tuple(int(x) for x in image_size), None, None, flags=flags,
                                 criteria=CALIB_CRITERIA)


def calibrate_fisheye(views: Sequence[tuple[str, np.ndarray]], spec: BoardSpec, image_size: tuple[int, int], *,
                      reject_outliers: bool = True, outlier_abs_px: float = OUTLIER_ABS_PX, outlier_rel: float = OUTLIER_REL,
                      min_images: int = MIN_IMAGES, check_cond: bool = True) -> FisheyeCalibration:
    """Hiệu chuẩn Kannala–Brandt trên các ảnh đã dò góc (`views` = [(tên, góc (N, 2))]).

    Vòng lặp: hiệu chuẩn → tính RMS từng ảnh → nếu ảnh tệ nhất > max(outlier_abs_px, outlier_rel × trung vị) và bỏ nó
    vẫn còn ≥ min_images ảnh thì bỏ và hiệu chuẩn lại. Với `check_cond`, ảnh làm ma trận suy biến (OpenCV báo
    "Ill-conditioned matrix for input array k") cũng bị bỏ. Ảnh bị bỏ được chấm lại dưới mô hình cuối (solvePnP)."""
    if len(views) < min_images:
        raise CalibrationError(f"cần ít nhất {min_images} ảnh có bảng, mới có {len(views)}")
    obj = _as_obj(spec)
    names = [str(n) for n, _ in views]
    corners = [np.asarray(c, np.float64).reshape(-1, 2) for _, c in views]
    for n, c in zip(names, corners):
        if len(c) != spec.n_corners:
            raise CalibrationError(f"{n}: {len(c)} góc, cần {spec.n_corners}")
    active = list(range(len(views)))
    reasons: dict[int, str] = {}
    base_flags = CALIB_FLAGS
    use_cond = check_cond
    rounds = 0
    while True:
        rounds += 1
        if len(active) < min_images:
            raise CalibrationError(f"chỉ còn {len(active)} ảnh dùng được (< {min_images}): "
                                   + "; ".join(f"{names[i]}: {r}" for i, r in reasons.items()))
        flags = base_flags | (_flag("CALIB_CHECK_COND") if use_cond else 0)
        try:
            opencv_rms, K, D, rvecs, tvecs = _run_calibrate(obj, [corners[i] for i in active], image_size, flags)
        except cv2.error as exc:
            m = re.search(r"input array (\d+)", str(exc))
            if use_cond and m and int(m.group(1)) < len(active):
                bad = active.pop(int(m.group(1)))
                reasons[bad] = "ma trận suy biến (CALIB_CHECK_COND): bảng gần như song song tia nhìn hoặc quá nhỏ"
                continue
            if use_cond:                                 # lỗi khác: thử một lần không kiểm điều kiện
                use_cond = False
                continue
            raise CalibrationError(f"cv2.fisheye.calibrate lỗi: {str(exc).strip().splitlines()[-1]}") from exc
        D = np.asarray(D, np.float64).ravel()
        if not (np.all(np.isfinite(K)) and np.all(np.isfinite(D)) and K[0, 0] > 0 and K[1, 1] > 0):
            raise CalibrationError("kết quả không hữu hạn (mô hình không hội tụ)")
        errs = [_view_errors(obj, corners[i], rvecs[k], tvecs[k], K, D) for k, i in enumerate(active)]
        rms_each = np.array([math.sqrt(float(np.mean(e ** 2))) for e in errs])
        if reject_outliers and len(active) - 1 >= min_images:
            worst = int(np.argmax(rms_each))
            limit = max(outlier_abs_px, outlier_rel * float(np.median(rms_each)))
            if rms_each[worst] > limit:
                bad = active.pop(worst)
                reasons[bad] = f"RMS riêng {rms_each[worst]:.2f} px > ngưỡng {limit:.2f} px (vòng {rounds})"
                continue
        break
    results: list[ViewResult] = []
    pose_by_index = {i: (rvecs[k], tvecs[k], errs[k]) for k, i in enumerate(active)}
    for i, name in enumerate(names):
        if i in pose_by_index:
            rv, tv, e = pose_by_index[i]
            dist, tilt = _pose_stats(spec, rv, tv)
            results.append(ViewResult(name, True, math.sqrt(float(np.mean(e ** 2))), float(e.max()), None, dist, tilt))
            continue
        vr = ViewResult(name, False, reason=reasons.get(i))
        try:
            ok, rv, tv = cv2.fisheye.solvePnP(obj, corners[i].reshape(1, -1, 2), K, D.reshape(4, 1))
            if ok:
                e = _view_errors(obj, corners[i], rv, tv, K, D)
                vr.rms_px, vr.max_error_px = math.sqrt(float(np.mean(e ** 2))), float(e.max())
                vr.distance_m, vr.tilt_deg = _pose_stats(spec, rv, tv)
        except cv2.error:
            pass
        results.append(vr)
    all_err = np.concatenate([pose_by_index[i][2] for i in active])
    return FisheyeCalibration((int(image_size[0]), int(image_size[1])), np.asarray(K, np.float64), D,
                              math.sqrt(float(np.mean(all_err ** 2))), float(opencv_rms), results, rounds, flags,
                              [corners[i] for i in active])


# ---- nắn ảnh để xem trước -----------------------------------------------------------------------------------------
def undistort_maps(K, D, image_size: tuple[int, int], balance: float = 0.0, new_size: tuple[int, int] | None = None,
                   fov_scale: float = 1.0):
    """Bản đồ remap sang ảnh phối cảnh (pinhole). balance 0 = cắt hết viền đen, 1 = giữ cả trường nhìn (co lại).
    Với ống kính rộng, ảnh phối cảnh kéo giãn mạnh ở mép: chỉ để xem đường thẳng có thẳng lại không."""
    size = tuple(int(x) for x in (new_size or image_size))
    K = np.asarray(K, np.float64)
    D4 = np.asarray(D, np.float64).reshape(4, 1)
    P = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(K, D4, tuple(int(x) for x in image_size), np.eye(3),
                                                               balance=float(balance), new_size=size, fov_scale=float(fov_scale))
    map1, map2 = cv2.fisheye.initUndistortRectifyMap(K, D4, np.eye(3), P, size, cv2.CV_16SC2)
    return map1, map2, P


def undistort_image(image: np.ndarray, K, D, balance: float = 0.0, maps=None) -> np.ndarray:
    if maps is None:
        maps = undistort_maps(K, D, (image.shape[1], image.shape[0]), balance)
    return cv2.remap(image, maps[0], maps[1], interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


# ---- tiêu chí, bản ghi, lưu/đọc ------------------------------------------------------------------------------------
def acceptance(calib: FisheyeCalibration, coverage: dict, woodscape: dict, accept: dict | None = None) -> dict:
    """Tiêu chí ĐỀ XUẤT (chưa kiểm trên camera thật) — để người dùng quyết định, không phải phán quyết cuối."""
    a = dict(ACCEPT, **(accept or {}))
    tilted = sum(1 for v in calib.views if v.used and v.tilt_deg is not None and v.tilt_deg >= a["tilt_deg"])
    corners_ok = sum(coverage["corner_blocks"].values())
    # khối chuyển đổi không ok (đa thức không đơn điệu, góc ảnh ngoài vùng KB nghịch đảo được…) thì load_intrinsics() từ
    # chối tệp, dù sai số khớp nhỏ: tiêu chí này phải CHƯA đạt, và nhãn mang lý do
    ws_ok = bool(woodscape.get("ok"))
    fit_label = "sai số chuyển sang mô hình dự án (px)" + ("" if ws_ok else f" — chuyển đổi KHÔNG ĐẠT: {woodscape.get('reason')}")
    checks = [
        ("rms_px", "RMS chiếu lại toàn bộ (px)", round(calib.rms_px, 4), "<=", a["rms_px"]),
        ("max_view_rms_px", "RMS ảnh tệ nhất còn dùng (px)", round(calib.max_view_rms_px, 4), "<=", a["max_view_rms_px"]),
        ("images", "số ảnh dùng", calib.n_used, ">=", a["images"]),
        ("coverage", f"tỉ lệ ô lưới {coverage['grid'][0]}×{coverage['grid'][1]} có góc", coverage["fraction"], ">=", a["coverage"]),
        ("corner_blocks", "số góc ảnh có điểm", corners_ok, ">=", a["corner_blocks"]),
        ("tilted_images", f"số ảnh bảng nghiêng ≥ {a['tilt_deg']:g}°", tilted, ">=", a["tilted_images"]),
        ("fit_error_px", fit_label, woodscape["max_fit_error_px"], "<=", a["fit_error_px"]),
    ]
    items = []
    for key, label, value, op, thr in checks:
        ok = value <= thr if op == "<=" else value >= thr
        if key == "fit_error_px":
            ok = ok and ws_ok
        items.append({"key": key, "label": label, "value": value, "op": op, "threshold": thr, "pass": bool(ok)})
    return {"status": "đề xuất, chưa kiểm trên camera thật", "all_pass": all(i["pass"] for i in items), "checks": items}


def observed_theta_max_deg(calib: FisheyeCalibration) -> float | None:
    """θ lớn nhất (độ) của các góc bảng ĐÃ DÙNG, theo mô hình vừa tìm: ngoài góc này mô hình là ngoại suy."""
    if not calib.used_corners:
        return None
    c = np.vstack(calib.used_corners)
    th = pixel_theta(c[:, 0], c[:, 1], calib.K, calib.D)
    return round(math.degrees(float(np.nanmax(th))), 2) if np.isfinite(th).any() else None


# ---- camera KHÔNG qua hub 1..4 (camera trên cao, T11, thêm 02/10/2026) ---------------------------------------------
# Camera xe khóa theo cổng hub (cam_p<cổng>.json). Camera ngoài hub (camera trên cao của mục 3.4 KICH_BAN_NGHIEM_THU) khóa
# theo TÊN: tệp cam_<tên>.json, bản ghi có hub_port null. Tên không được trùng dạng tên tệp của camera xe.
CAMERA_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,31}")
_HUB_LIKE_NAME_RE = re.compile(r"p\d")                # cam_p<số>… là tệp của camera xe
_SIZE_SUFFIX_RE = re.compile(r"_\d+x\d+$")            # …_<rộng>x<cao> là hậu tố kích thước của tên tệp


def camera_name_error(name: str | None) -> str | None:
    """None khi `name` dùng được làm tên camera ngoài hub; không thì lý do (tiếng Việt, để in cho người dùng)."""
    if not isinstance(name, str) or CAMERA_NAME_RE.fullmatch(name) is None:
        return ("tên camera chỉ gồm chữ thường không dấu, số và gạch dưới, bắt đầu bằng chữ, tối đa 32 ký tự "
                "(ví dụ tren_cao)")
    if _HUB_LIKE_NAME_RE.match(name):
        return f"tên {name!r} có dạng p<số>, trùng tệp camera xe cam_p<cổng>.json: chọn tên khác, ví dụ tren_cao"
    if _SIZE_SUFFIX_RE.search(name):
        return f"tên {name!r} kết thúc bằng _<rộng>x<cao>, trùng hậu tố kích thước của tên tệp"
    return None


def camera_key(port: int | None = None, name: str | None = None) -> str:
    """Khóa camera trong tên tệp và `source_id`: "p<cổng>" (camera xe qua hub) hoặc tên đã kiểm (camera ngoài hub).
    Phải có đúng một trong hai, không thì ValueError."""
    if (port is None) == (name is None):
        raise ValueError("cần đúng một trong hai: cổng hub (camera xe) hoặc tên (camera ngoài hub)")
    if name is not None:
        error = camera_name_error(name)
        if error:
            raise ValueError(error)
        return name
    return f"p{port}"


def camera_label(camera: dict) -> str:
    """Nhãn camera của một bản ghi để in: "cổng hub N", hay "ngoài hub 'tên' (index N lúc chụp)"."""
    if camera.get("hub_port") is not None:
        return f"cổng hub {camera['hub_port']}"
    index = camera.get("opencv_index")
    return f"ngoài hub {camera.get('name')!r}" + ("" if index is None else f" (index {index} lúc chụp)")


def default_output_path(port: int | None, image_size: tuple[int, int], out_dir=Path("calibration"), *,
                        name: str | None = None) -> Path:
    """calibration/cam_p<cổng>.json cho mode 640×480 (mode chạy bốn camera); mode khác thêm hậu tố kích thước để không
    ghi đè bản 640×480 bằng một mode có thể cắt/co cảm biến khác. Camera ngoài hub (`name`, T11): cam_<tên>[_WxH].json."""
    w, h = image_size
    suffix = "" if (w, h) == DEFAULT_SIZE else f"_{w}x{h}"
    return Path(out_dir) / f"cam_{camera_key(port, name)}{suffix}.json"


def calibration_record(calib: FisheyeCalibration, spec: BoardSpec, *, port: int | None = None,
                       camera_name: str | None = None, camera_index: int | None = None,
                       square_mm_measured: float | None = None, images_dir: str | None = None,
                       frame_reports: list[dict] | None = None, device: str | None = None, accept: dict | None = None,
                       extra: dict | None = None) -> dict:
    """Nội dung tệp hiệu chuẩn một camera (JSON). `spec.square_mm` là cỡ ô dùng để tính (nên là cỡ ĐO ĐƯỢC).

    Camera xe: `port` (cổng hub). Camera ngoài hub (T11): `camera_name` (+ `camera_index` = index OpenCV lúc chụp, chỉ
    để tra lại; index đổi sau khởi động lại) — khối camera có hub_port null, name, opencv_index."""
    key = camera_key(port, camera_name)
    if camera_name is None:
        camera = {"hub_port": int(port), "source_id": f"cam_{key}", "device": device}
    else:
        camera = {"hub_port": None, "name": camera_name, "opencv_index": camera_index, "source_id": f"cam_{key}",
                  "device": device}
    cov = coverage_summary(coverage_counts(calib.used_corners, calib.image_size))
    ws = woodscape_intrinsics(calib.K, calib.D, calib.image_size)
    by_name = {r.get("name"): r for r in (frame_reports or [])}
    views = []
    for v in calib.views:
        entry = v.to_dict()
        if v.name in by_name:
            entry["quality"] = {k: val for k, val in by_name[v.name].items() if k != "name"}
        views.append(entry)
    record = {
        "format": FORMAT,
        "camera": camera,
        "image_size": list(calib.image_size),
        "model": "opencv_fisheye_kannala_brandt",
        "K": np.round(calib.K, 6).tolist(),
        "D": [float(x) for x in calib.D],
        "flags": {"value": int(calib.flags), "names": ["CALIB_RECOMPUTE_EXTRINSIC", "CALIB_FIX_SKEW"]
                  + (["CALIB_CHECK_COND"] if calib.flags & _flag("CALIB_CHECK_COND") else [])},
        "rms_px": round(calib.rms_px, 5),
        "opencv_rms": round(calib.opencv_rms, 5),
        "max_view_rms_px": round(calib.max_view_rms_px, 5),
        "n_images_used": calib.n_used,
        "n_images_total": len(calib.views),
        "rounds": calib.rounds,
        "views": views,
        "board": {**spec.to_dict(), "pattern": "chessboard"},
        "square_mm_measured": square_mm_measured,
        "square_mm_note": ("cỡ ô chỉ ảnh hưởng distance_m của từng ảnh (và ngoại tham sau này), không ảnh hưởng K, D"),
        "coverage": cov,
        "field_of_view_deg": {**field_of_view(calib.K, calib.D, calib.image_size),
                              "theta_observed_max_deg": observed_theta_max_deg(calib)},
        "woodscape_intrinsic": ws,
        "extrinsic": None,
        "rig": None,
        "note": NOT_ON_RIG_NOTE,
        "images_dir": images_dir,
        "created_local": datetime.now().isoformat(timespec="seconds"),
        "software": {"opencv": cv2.__version__, "numpy": np.__version__, "python": platform.python_version()},
    }
    record["acceptance"] = acceptance(calib, cov, ws, accept)
    if extra:
        record.update(extra)
    return record


def save_calibration(path, record: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_calibration(path) -> dict:
    """Đọc và kiểm hình dạng tệp hiệu chuẩn (không kiểm chất lượng — xem record['acceptance'])."""
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if record.get("format") != FORMAT:
        raise ValueError(f"{path}: không phải tệp {FORMAT} (format={record.get('format')!r})")
    K = np.asarray(record["K"], np.float64)
    D = np.asarray(record["D"], np.float64)
    w, h = record["image_size"]
    if K.shape != (3, 3) or D.shape != (4,) or not (np.all(np.isfinite(K)) and np.all(np.isfinite(D))) or w <= 0 or h <= 0:
        raise ValueError(f"{path}: K phải 3×3, D phải 4 số hữu hạn, kích thước ảnh dương")
    if "hub_port" not in record.get("camera", {}):
        raise ValueError(f"{path}: thiếu camera.hub_port")
    return record


def camera_model(record: dict) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    return np.asarray(record["K"], np.float64), np.asarray(record["D"], np.float64), tuple(record["image_size"])


def load_intrinsics(path, *, width: int | None = None, height: int | None = None) -> FisheyeIntrinsics:
    """`FisheyeIntrinsics` của dự án từ tệp hiệu chuẩn; từ chối khi chuyển đổi không đạt hoặc kích thước ảnh khác."""
    record = load_calibration(path)
    block = record.get("woodscape_intrinsic") or {}
    if not block.get("ok"):
        raise ValueError(f"{path}: chuyển sang mô hình đa thức không đạt: {block.get('reason')}")
    if (width, height) != (None, None) and (width, height) != tuple(record["image_size"]):
        raise ValueError(f"{path}: hiệu chuẩn cho ảnh {record['image_size']}, không dùng được cho {width}×{height}")
    return intrinsics_from_block(block)


def _f(x, nd: int = 2) -> str:
    return "—" if x is None else f"{x:.{nd}f}".replace(".", ",")


def summary_text(record: dict) -> str:
    """Tóm tắt một tệp hiệu chuẩn cho người đọc (lệnh `check` và giao diện)."""
    K, D, (w, h) = camera_model(record)
    fov = record.get("field_of_view_deg") or {}
    cov = record.get("coverage") or {}
    ws = record.get("woodscape_intrinsic") or {}
    views = record.get("views") or []
    rejected = [v for v in views if not v.get("used")]
    lines = [f"camera {camera_label(record['camera'])} · ảnh {w}×{h} · tạo {record.get('created_local')} · "
             f"OpenCV {record.get('software', {}).get('opencv')}",
             f"K: fx {_f(K[0, 0])}  fy {_f(K[1, 1])}  cx {_f(K[0, 2])}  cy {_f(K[1, 2])}   "
             f"D: [{', '.join(f'{d:+.5f}' for d in D)}]",
             f"RMS chiếu lại {_f(record['rms_px'], 3)} px trên {record['n_images_used']}/{record['n_images_total']} ảnh; "
             f"ảnh tệ nhất còn dùng {_f(record.get('max_view_rms_px'), 3)} px"]
    for v in rejected:
        lines.append(f"  loại {v['name']}: {v.get('rejected_reason')} (dưới mô hình cuối: {_f(v.get('rms_px'), 2)} px)")
    lines.append(f"trường nhìn suy từ mô hình: ngang {_f(fov.get('horizontal_deg'), 1)}°  dọc {_f(fov.get('vertical_deg'), 1)}°  "
                 f"chéo {_f(fov.get('diagonal_deg'), 1)}°")
    corner_theta = [t for t in fov.get("theta_image_corners_deg") or [] if t is not None]
    lines.append(f"  θ lớn nhất đã thấy bảng {_f(fov.get('theta_observed_max_deg'), 1)}°, ở góc ảnh "
                 f"{_f(max(corner_theta), 1) if corner_theta else '—'}°: phần giữa hai số này là NGOẠI SUY")
    if cov:
        cb = cov.get("corner_blocks", {})
        lines.append(f"phủ ảnh: {cov['cells_covered']}/{cov['cells_total']} ô ({_f(100 * cov['fraction'], 0)} %), viền "
                     f"{_f(100 * cov['border_fraction'], 0)} %, góc ảnh TT/TP/DT/DP: "
                     + "/".join("có" if cb.get(k) else "KHÔNG" for k in ("tl", "tr", "bl", "br")))
    if ws:
        lines.append(f"sang mô hình dự án (ρ(θ) bậc 4, θ ≤ {_f(ws.get('theta_max_deg'), 1)}°): sai số khớp lớn nhất "
                     f"{_f(ws.get('max_fit_error_px'), 3)} px, kiểm chiếu {_f(ws.get('projection_check_max_px'), 3)} px → "
                     + ("ĐẠT" if ws.get("ok") else f"KHÔNG ĐẠT ({ws.get('reason')})"))
    acc = record.get("acceptance")
    if acc:
        lines.append(f"tiêu chí ({acc['status']}):")
        for c in acc["checks"]:
            value = c["value"] if isinstance(c["value"], int) else _f(c["value"], 3)
            lines.append(f"  {'đạt ' if c['pass'] else 'CHƯA'}  {c['label']}: {value} (cần {c['op']} {c['threshold']})")
    sq = record.get("square_mm_measured")
    lines.append(f"cỡ ô dùng {_f(record['board']['square_mm'], 2)} mm"
                 + ("" if sq else " — CHƯA khai cỡ ô đo được (chỉ ảnh hưởng khoảng cách, không ảnh hưởng K, D)"))
    lines.append(record.get("note", NOT_ON_RIG_NOTE))
    return "\n".join(lines)


# ---- ảnh từ thư mục (lệnh calibrate) ---------------------------------------------------------------------------------
def read_image(path: Path) -> np.ndarray | None:
    """Đọc ảnh chịu được đường dẫn Unicode (cv2.imread không đọc được đường dẫn tiếng Việt trên Windows)."""
    try:
        return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    except OSError:
        return None


def write_image(path: Path, image: np.ndarray) -> bool:
    ok, buf = cv2.imencode(Path(path).suffix, image)
    if not ok:
        return False
    try:
        Path(path).write_bytes(buf.tobytes())
    except OSError:
        return False
    return True


def views_from_directory(directory, spec: BoardSpec, *, max_edge_width: float = MAX_EDGE_WIDTH_PX,
                         min_contrast: float = MIN_CONTRAST) -> tuple[list[tuple[str, np.ndarray]], list[dict], tuple[int, int] | None]:
    """Dò bảng trên mọi ảnh của một thư mục; trả (ảnh dùng được, báo cáo từng ảnh, kích thước ảnh)."""
    directory = Path(directory)
    files = sorted((p for p in directory.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS), key=natural_key)
    views, reports, size = [], [], None
    for path in files:
        image = read_image(path)
        if image is None:
            reports.append({"name": path.name, "ok": False, "reasons": ["không đọc được ảnh"]})
            continue
        this = (image.shape[1], image.shape[0])
        if size is None:
            size = this
        if this != size:
            reports.append({"name": path.name, "ok": False, "reasons": [f"kích thước {this} khác ảnh đầu {size}"]})
            continue
        det, q = assess_frame(image, spec, max_edge_width=max_edge_width, min_contrast=min_contrast)
        reports.append({"name": path.name, **q.to_dict()})
        if q.ok:
            views.append((path.name, det.corners))
    return views, reports, size


# ---- dòng lệnh -----------------------------------------------------------------------------------------------------
def _cmd_calibrate(args) -> int:
    if args.camera_name is not None:                 # tên sai thì báo ngay, trước khi dò bảng trên cả thư mục ảnh
        error = camera_name_error(args.camera_name)
        if error:
            print(f"LỖI: --camera-name: {error}", file=sys.stderr)
            return 2
    spec = BoardSpec(args.cols, args.rows, args.square_mm)
    views, reports, size = views_from_directory(args.images, spec, max_edge_width=args.max_edge_width)
    bad = [r for r in reports if not r.get("ok")]
    print(f"{len(reports)} ảnh, {len(views)} dùng được, {len(bad)} bị loại trước hiệu chuẩn")
    for r in bad:
        print(f"  {r['name']}: {'; '.join(r.get('reasons', []))}")
    if size is None:
        print("LỖI: thư mục không có ảnh", file=sys.stderr)
        return 2
    try:
        calib = calibrate_fisheye(views, spec, size, reject_outliers=not args.no_reject, min_images=args.min_images)
    except CalibrationError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    record = calibration_record(calib, spec, port=args.port, camera_name=args.camera_name,
                                square_mm_measured=args.square_mm, images_dir=str(Path(args.images)),
                                frame_reports=reports, device=args.device)
    out = Path(args.out) if args.out else default_output_path(args.port, size, name=args.camera_name)
    save_calibration(out, record)
    print(summary_text(record))
    print(f"đã ghi {out}")
    return 0


def _cmd_check(args) -> int:
    try:
        record = load_calibration(args.file)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    print(summary_text(record))
    if args.image:
        image = read_image(Path(args.image))
        if image is None:
            print(f"LỖI: không đọc được {args.image}", file=sys.stderr)
            return 2
        K, D, size = camera_model(record)
        if (image.shape[1], image.shape[0]) != tuple(size):
            print(f"LỖI: ảnh {image.shape[1]}×{image.shape[0]} khác kích thước hiệu chuẩn {size}", file=sys.stderr)
            return 2
        out = Path(args.preview) if args.preview else Path(args.image).with_name(Path(args.image).stem + "_nan.jpg")
        side = np.hstack([image, undistort_image(image, K, D, args.balance)])
        if not write_image(out, side):
            print(f"LỖI: không ghi được {out}", file=sys.stderr)
            return 2
        print(f"đã ghi ảnh gốc | ảnh nắn (balance {args.balance:g}) vào {out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("board", help="ghi bảng ô vuông để in (PDF, PNG, JSON)")
    add_board_args(b)
    c = sub.add_parser("calibrate", help="hiệu chuẩn từ một thư mục ảnh")
    c.add_argument("--images", type=Path, required=True)
    c.add_argument("--cols", type=int, default=9, help="số góc trong theo chiều ngang")
    c.add_argument("--rows", type=int, default=6, help="số góc trong theo chiều dọc")
    c.add_argument("--square-mm", type=float, required=True, help="cỡ ô ĐO ĐƯỢC trên bản in (mm), không phải cỡ danh định")
    which = c.add_mutually_exclusive_group(required=True)
    which.add_argument("--port", type=int, default=None, help="cổng hub của camera (1..4)")
    which.add_argument("--camera-name", default=None, metavar="TÊN",
                       help="camera KHÔNG qua hub 1..4 (camera trên cao): tên dùng cho tệp và bản ghi, ví dụ tren_cao")
    c.add_argument("--out", type=Path, default=None,
                   help="mặc định calibration/cam_p<cổng>.json hoặc calibration/cam_<tên>.json")
    c.add_argument("--device", default=None, help="mô tả thiết bị ghi vào tệp (tùy chọn)")
    c.add_argument("--min-images", type=int, default=MIN_IMAGES)
    c.add_argument("--max-edge-width", type=float, default=MAX_EDGE_WIDTH_PX, help="ngưỡng mờ (px), đề xuất")
    c.add_argument("--no-reject", action="store_true", help="không loại ảnh ngoại lai theo RMS")
    k = sub.add_parser("check", help="in tóm tắt một tệp hiệu chuẩn; --image để ghi ảnh nắn xem trước")
    k.add_argument("file", type=Path)
    k.add_argument("--image", type=Path, default=None)
    k.add_argument("--preview", type=Path, default=None)
    k.add_argument("--balance", type=float, default=0.3)
    args = p.parse_args(argv)
    if args.cmd == "board":
        return run_board(args)
    if args.cmd == "calibrate":
        return _cmd_calibrate(args)
    return _cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
