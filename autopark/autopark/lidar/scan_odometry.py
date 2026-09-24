r"""Odometry LiDAR 2D bằng khớp scan, với bản đồ chiếm chỗ tăng dần: thử nghiệm offline (thêm 24/09/2026).

Lệnh (chạy trong `autopark`; mỗi lệnh một dòng, dán được vào cmd.exe; thay `<...>` bằng thư mục thật):

    .venv\Scripts\python.exe -X utf8 -m autopark.lidar.scan_odometry --recording runs/rig_recordings/o03_20260924/lidar/part_0000.npz --skip-seconds 3 --mode both --out <thư mục>
    .venv\Scripts\python.exe -X utf8 -m autopark.lidar.scan_odometry --drow datasets/drow/DROWv2-data/val/run_2015-11-25-10-34-20-a.bag.csv --out <thư mục>
    .venv\Scripts\python.exe -X utf8 -m autopark.lidar.scan_odometry --drow datasets/drow/DROWv2-data/val --limit 3000 --mode both --workers 8 --out <thư mục>

Tùy chọn thêm vào cuối lệnh: [--mode scan_to_map|scan_to_scan|both] [--skip-seconds S] [--start I] [--limit N]
[--mirror] [--resolution M] [--min-range M] [--max-range M] [--min-normal-ratio R] [--lock-sigma M] [--workers N]
[--no-png]. `--recording` và `--drow` nhận nhiều tệp; `--drow` nhận cả thư mục (mọi `*.csv` có `.odom2` cùng tên, vì
cmd.exe không tự mở rộng `*`). `--min-normal-ratio 0` tắt phép kiểm suy biến theo pháp tuyến (và khóa trục), chỉ để so
sánh. Công cụ chạy theo lô, không mở cửa sổ; kết quả là `odometry.json`, một `.csv` và một `.png` cho mỗi bản ghi và chế
độ. Tên tệp kết quả lấy từ tên bản ghi; hai bản ghi cùng tên ở hai thư mục thì tên có thêm thư mục cha
(vd. `may_moi_20260924_toi__lidar__l01_tinh__scan_to_map.csv`) để không ghi đè nhau.

Là gì: ước lượng chuyển động của cảm biến LiDAR từ chính các vòng quét, dùng lại bộ máy của `lidar/localize.py`
(trường khoảng cách, khớp tương quan nhánh-cận, kiểm từng tia) và `lidar/occupancy.py` (đếm đi qua / chạm theo ô):
1. Dự đoán tư thế vòng k theo mô hình vận tốc không đổi, hoặc đứng yên (`motion_model="zero"`). Vận tốc = chuyển động
   từ vòng CHẤP NHẬN gần nhất tới vòng chấp nhận hiện tại, chia đều cho số vòng giữa hai vòng đó (sau các vòng FAILED,
   tư thế chỉ là dự đoán hoặc đứng yên khi đã `lost`; không được dồn cả đoạn đi lúc mù vào một vòng).
2. Chọn điểm để khớp (`dense_points`): tầm ≤ `max_range_m` − `match_margin_m` (bản đồ vẫn nhận tia tới
   `max_range_m`) và có ít nhất một tia kề theo góc chạm cách ≤ `max_point_spacing_m`. Hai bộ lọc này có từ phép thử
   hành lang tổng hợp ngày 24/09/2026: tường của vòng trước dừng ở đúng tầm tối đa, và ở góc sượt tường xa chỉ là các
   chấm gắn với tư thế vòng trước; khớp cả những điểm đó ghim chuyển động dọc hành lang về 0.
3. Khớp với bản đồ tham chiếu trong cửa sổ nhỏ quanh dự đoán (nhánh-cận của `LocalizationMap.search`); đỉnh ở mép cửa
   sổ thì tìm lại một lần với cửa sổ × `retry_scale`.
4. Xét suy biến bằng hình học của chính vòng quét (`surface_normals`, `normal_geometry`): pháp tuyến bề mặt ước lượng
   trên 7 tia liền nhau; λmin/λmax của Σ n·nᵀ < `min_normal_ratio` nghĩa là mọi bề mặt thấy được gần song song (hành
   lang), chuyển động dọc chúng không quan sát được. Hessian của phép khớp KHÔNG dùng được cho việc này: trên hành
   lang tổng hợp, "vân" lượng tử hóa của bản đồ một vòng quét cho Hessian có vẻ tốt (tỉ số trị riêng ≈ 0,6) trong khi
   ước lượng dọc hành lang nhảy tùy ý.
5. Tinh chỉnh Gauss-Newton/LM (trọng số Cauchy như `localize.refine`) cộng số hạng kéo về dự đoán (σ mỗi vòng
   `prior_sigma_*`). Khi suy biến (bước 4): điểm xuất phát bỏ thành phần dọc hướng suy biến u của kết quả tìm, và thêm
   một tiên nghiệm MỀM kéo thành phần tịnh tiến dọc u về dự đoán (σ `lock_sigma_m` = 3 cm); trạng thái AMBIGUOUS với
   lý do `degenerate`. Ngang hành lang và hướng vẫn lấy từ khớp scan. Tiên nghiệm mềm chứ không giữ cứng (sửa đêm
   24/09/2026): phép kiểm pháp tuyến cũng báo suy biến khi vật nhỏ (cột, khung cửa, không đủ 7 tia thẳng để có pháp
   tuyến) vẫn cho biết vị trí dọc u; khi đó số đo khớp scan phải thắng được tiên nghiệm. Giữ cứng (σ 2 mm, bản đầu
   24/09/2026) làm tư thế dọc u chạy theo vận tốc cũ, robot đổi tốc độ là lạc (DROW `13-47-42`, hội trường có cột của
   test). Cái giá, đo 24/09/2026 trên hành lang trơn tổng hợp (nhiễu 1 cm, 60 vòng, thật đi 1,8 m, 41 seed): vận tốc
   dọc u (lấy từ các vòng suy biến) đi bộ ngẫu nhiên, dọc u lớn nhất trung vị 0,15 m, 14/41 seed > 0,5 m, xấu nhất
   3,7 m; khóa cứng ≤ 33 mm; không kéo (σ 1 km) trung vị 0,36 m, 20/41 seed > 0,5 m. Mọi vòng đó vẫn là AMBIGUOUS:
   dọc u ở cảnh suy biến thật là "không biết", với cả ba cách. Đỉnh tìm ra mép cửa sổ chỉ theo hướng u (thành phần sẽ
   bị bỏ ở trên) thì không tính là mép cửa sổ; thêm lý do `edge_along_axis` để thống kê.
6. Kiểm từng điểm ở tư thế cuối (`LocalizationMap.evaluate`, trên tập điểm đã tỉa một điểm mỗi ô): khớp / mâu thuẫn.
   Khớp kém thì FAILED, tư thế lấy theo dự đoán, không cập nhật bản đồ; `lost_after` lần FAILED liên tiếp thì thêm lý
   do `lost` và thôi ngoại suy vận tốc.
7. Bản đồ tham chiếu:
   - `scan_to_map` (mặc định): một lưới đếm bền (hệ odometry = hệ của vòng hợp lệ đầu tiên), thêm vòng quét làm khung
     khóa khi đã đi ≥ `keyframe_dist_m` hoặc quay ≥ `keyframe_angle_deg` kể từ khung khóa trước; lưới tự nới khi cảm
     biến đến gần mép. Cảm biến đứng yên thì không thêm khung khóa nào, nên sai số không cộng dồn.
   - `scan_to_scan`: chỉ vòng quét được chấp nhận ngay trước đó làm tham chiếu (sai số cộng dồn mỗi vòng; vật đi
     cùng tốc độ với cảm biến trông như vật đứng yên).

KHÔNG phải: SLAM đầy đủ (không đóng vòng, không tối ưu đồ thị tư thế, không định vị lại khi đã lạc; bản đồ không bao
giờ được sửa khi phát hiện trôi), không phải odometry bánh xe/IMU (không có đầu vào nào ngoài vòng quét). Tư thế là
của tâm quay LiDAR trong hệ odometry; đổi sang tâm trục sau xe cần phép biến đổi gá LiDAR–xe, CHƯA ĐO. Mới chạy
offline trên dữ liệu lưu sẵn; chưa nối vào phiên đỗ xe, chưa chạy trên cảm biến di chuyển thật.

Mọi ngưỡng (`min_matched_fraction`, `max_conflict_fraction`, `min_normal_ratio`, `max_std_*`, `prior_sigma_*`,
khung khóa, cửa sổ, bộ lọc điểm) là giá trị tạm, CHƯA CHỐT (24/09/2026): mới chọn trên phòng tổng hợp của test và dữ
liệu DROW/C1 lưu sẵn, chưa có xe, chưa có tham chiếu độc lập. Xem docs/SO_SANH_DINH_VI_SLAM.md.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from autopark.perception.costmap import OCCUPIED, GridSpec, render
from autopark.perception.paths import atomic_write_json, utc_now

from .localize import AMBIGUOUS, FAILED, OK, LocalizationMap, LocalizeConfig, decimate, wrap
from .occupancy import OccupancyCounts, states_from_counts

INIT = "INIT"
SCAN_TO_MAP, SCAN_TO_SCAN = "scan_to_map", "scan_to_scan"
MODES = (SCAN_TO_MAP, SCAN_TO_SCAN)
MOTION_MODELS = ("constant_velocity", "zero")
EST_COLOR = (255, 60, 0)      # BGR: xanh dương = quỹ đạo khớp scan
REF_COLOR = (255, 0, 255)     # tím = quỹ đạo tham chiếu (odometry DROW), KHÔNG phải ground truth
FAIL_COLOR = (0, 0, 0)        # dấu X đen = vòng FAILED (tư thế lấy theo dự đoán)


# --- tư thế 2D ------------------------------------------------------------------------------------------------------

def compose(a, b) -> np.ndarray:
    """a ⊕ b: tư thế b (biểu diễn trong hệ của a) đổi sang hệ chứa a."""
    c, s = math.cos(a[2]), math.sin(a[2])
    return np.array([a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], wrap(a[2] + b[2])], np.float64)


def between(a, b) -> np.ndarray:
    """a⁻¹ ⊕ b: tư thế b nhìn từ hệ của a."""
    c, s = math.cos(a[2]), math.sin(a[2])
    dx, dy = b[0] - a[0], b[1] - a[1]
    return np.array([c * dx + s * dy, -s * dx + c * dy, wrap(b[2] - a[2])], np.float64)


def between_many(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """`between` theo hàng cho hai mảng (N, 3)."""
    c, s = np.cos(a[:, 2]), np.sin(a[:, 2])
    dx, dy = b[:, 0] - a[:, 0], b[:, 1] - a[:, 1]
    return np.column_stack([c * dx + s * dy, -s * dx + c * dy, wrap(b[:, 2] - a[:, 2])])


def scale_motion(motion, fraction: float) -> np.ndarray:
    """exp(fraction · log(motion)) trong SE(2): cùng xoắn (vận tốc thẳng và quay) không đổi, chỉ đi `fraction` phần.
    `scale_motion(m, 1 / n)` lặp lại n lần thì bằng m. `fraction` = 1 trả đúng `motion`."""
    if fraction == 1.0:
        return np.asarray(motion, np.float64).copy()
    x, y, th = (float(v) for v in motion)

    def v_matrix(angle: float) -> np.ndarray:
        if abs(angle) < 1e-9:
            return np.eye(2)
        a, b = math.sin(angle) / angle, (1.0 - math.cos(angle)) / angle
        return np.array([[a, -b], [b, a]])

    rho = np.linalg.solve(v_matrix(th), np.array([x, y]))
    return np.array([*(v_matrix(th * fraction) @ (rho * fraction)), th * fraction], np.float64)


def relative_to_first(poses: np.ndarray) -> np.ndarray:
    """Biểu diễn mọi tư thế trong hệ của tư thế đầu (tư thế đầu thành (0, 0, 0))."""
    poses = np.asarray(poses, np.float64)
    return between_many(np.repeat(poses[:1], len(poses), axis=0), poses)


# --- cấu hình -------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class OdometryConfig:
    """Tham số odometry khớp scan. Mọi ngưỡng là giá trị tạm, CHƯA CHỐT (24/09/2026)."""

    mode: str = SCAN_TO_MAP
    resolution_m: float = 0.05
    min_range_m: float = 0.25          # bỏ phản hồi sát cảm biến (dây, gá; C1 có tia 0,09–0,17 m, GIAI_DOAN_1_LIDAR 3b)
    max_range_m: float = 8.0           # tầm tia đưa vào bản đồ
    match_margin_m: float = 1.0        # chỉ khớp điểm có tầm ≤ max_range_m − match_margin_m (docstring, bước 2)
    max_point_spacing_m: float = 0.10  # chỉ khớp điểm có một điểm kề (theo góc) cách ≤ giá trị này; None/inf = tắt
    # cửa sổ tìm quanh tư thế dự đoán; mép cửa sổ thì tìm lại một lần với cửa sổ × retry_scale
    window_x_m: float = 0.15
    window_y_m: float = 0.15
    window_theta_deg: float = 8.0
    retry_scale: float = 2.5
    motion_model: str = "constant_velocity"
    # số hạng kéo về dự đoán trong tinh chỉnh (độ lệch chuẩn cho mỗi vòng)
    prior_sigma_xy_m: float = 0.05
    prior_sigma_theta_deg: float = 2.0
    refine_iterations: int = 20
    # khung khóa (chỉ scan_to_map)
    keyframe_dist_m: float = 0.10
    keyframe_angle_deg: float = 5.0
    # lưới đếm của bản đồ tăng dần
    map_min_hits: int = 1
    map_min_passes: int = 1
    map_occupied_ratio: float = 0.2
    map_grow_m: float = 4.0
    recrop_dist_m: float = 1.0
    # ngưỡng chấp nhận (CHƯA CHỐT)
    min_valid_beams: int = 50
    min_matched: int = 30
    min_matched_fraction: float = 0.5
    max_conflict_fraction: float = 0.5
    max_std_xy_m: float = 0.05
    max_std_theta_deg: float = 2.0
    min_normal_ratio: float = 0.04     # λmin/λmax của Σ n·nᵀ (pháp tuyến bề mặt của vòng quét); dưới ngưỡng = suy biến
    normal_half_window: int = 3        # pháp tuyến ước lượng trên 2·3 + 1 = 7 tia liền nhau
    min_normals: int = 20              # ít pháp tuyến hơn thì không xét suy biến theo hình học (chỉ theo Hessian)
    # khi suy biến: tiên nghiệm MỀM kéo thành phần dọc hướng suy biến về dự đoán (docstring, bước 5). ĐỀ XUẤT – CHỜ CHỐT
    # (đêm 24/09/2026): 3 cm thay cho 2 mm (giữ cứng) của bản đầu 24/09/2026; mới chọn trên DROW và cảnh tổng hợp.
    lock_sigma_m: float = 0.03
    lost_after: int = 5

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"mode phải là một trong {MODES} (nhận {self.mode!r})")
        if self.motion_model not in MOTION_MODELS:
            raise ValueError(f"motion_model phải là một trong {MOTION_MODELS} (nhận {self.motion_model!r})")
        if not self.resolution_m > 0 or not 0 <= self.min_range_m < self.max_range_m - self.match_margin_m:
            raise ValueError("cần resolution_m > 0 và 0 ≤ min_range_m < max_range_m − match_margin_m")
        if not (math.isfinite(self.match_margin_m) and self.match_margin_m >= 0):
            raise ValueError("match_margin_m phải hữu hạn, không âm")
        if not self.max_point_spacing_m > 0:
            raise ValueError("max_point_spacing_m phải > 0 (math.inf = không lọc)")
        values = (self.window_x_m, self.window_y_m, self.window_theta_deg, self.keyframe_dist_m,
                  self.keyframe_angle_deg, self.map_grow_m, self.recrop_dist_m)
        if not all(math.isfinite(v) and v >= 0 for v in values):
            raise ValueError("cửa sổ, ngưỡng khung khóa và kích thước lưới phải hữu hạn, không âm")
        if not (self.prior_sigma_xy_m > 0 and self.prior_sigma_theta_deg > 0 and self.retry_scale >= 1):
            raise ValueError("prior_sigma_* phải > 0 và retry_scale ≥ 1")
        if not (self.lock_sigma_m > 0 and self.min_normal_ratio >= 0):
            raise ValueError("lock_sigma_m phải > 0 và min_normal_ratio ≥ 0 (0 = tắt kiểm suy biến theo pháp tuyến)")

    def localize_config(self) -> LocalizeConfig:
        res = self.resolution_m
        return LocalizeConfig(sigma_m=res, match_dist_m=2 * res, min_range_m=self.min_range_m,
                              max_range_m=self.max_range_m - self.match_margin_m, window_x_m=self.window_x_m,
                              window_y_m=self.window_y_m,
                              window_theta_deg=self.window_theta_deg, levels=3, keep_ratio=1.0,
                              refine_iterations=self.refine_iterations, refine_trunc_m=3 * res,
                              min_valid_beams=self.min_valid_beams, min_matched=self.min_matched,
                              min_matched_fraction=self.min_matched_fraction,
                              max_conflict_fraction=self.max_conflict_fraction, max_std_xy_m=self.max_std_xy_m,
                              max_std_theta_deg=self.max_std_theta_deg)


@dataclass
class OdometryStep:
    index: int
    t: float
    status: str                        # INIT / OK / AMBIGUOUS / FAILED
    reasons: tuple[str, ...]
    x: float
    y: float
    theta: float
    predicted: tuple[float, float, float]
    valid_beams: int = 0
    matched: int = 0
    matched_fraction: float = 0.0
    conflict_fraction: float = 0.0
    std_x_m: float = math.nan          # chỉ từ phần khớp scan (không tính số hạng dự đoán), thường lạc quan
    std_y_m: float = math.nan
    std_theta_deg: float = math.nan
    conflicts_short: int = 0           # điểm chạm rơi vào ô FREE của bản đồ tham chiếu
    conflicts_through: int = 0         # tia đi xuyên ô OCCUPIED của bản đồ tham chiếu
    normal_ratio: float = math.nan     # λmin/λmax của Σ n·nᵀ trên pháp tuyến bề mặt của vòng quét (≈ 0: hành lang)
    normals: int = 0                   # số pháp tuyến dùng được
    locked: bool = False               # thành phần dọc hướng suy biến đã giữ theo dự đoán
    keyframe: bool = False
    retried: bool = False
    time_ms: float = 0.0

    @property
    def pose(self) -> np.ndarray:
        return np.array([self.x, self.y, self.theta])

    def to_dict(self) -> dict:
        out = {}
        for key, value in asdict(self).items():
            if isinstance(value, float) and not math.isfinite(value):
                value = None
            out[key] = value
        out["reasons"] = list(self.reasons)
        out["predicted"] = list(self.predicted)
        out["theta_deg"] = math.degrees(self.theta)
        return out


class _Beams:
    """Đủ cho `OccupancyCounts.add_scan` (chỉ đọc `angles_rad`, `ranges_m`), không phải dựng `LidarScan`."""

    __slots__ = ("angles_rad", "ranges_m")

    def __init__(self, angles, ranges):
        self.angles_rad, self.ranges_m = angles, ranges


def _ordered_endpoints(angles, ranges, config: OdometryConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(x, y, gap_prev, gap_next) theo thứ tự góc; NaN ở tia không dùng được (không phản hồi, ngoài tầm khớp)."""
    angles = np.asarray(angles, np.float64)
    ranges = np.asarray(ranges, np.float64)
    order = np.argsort(angles, kind="stable")
    a, r = angles[order], ranges[order]
    ok = np.isfinite(r) & (r > 0) & (r >= config.min_range_m) & (r <= config.max_range_m - config.match_margin_m)
    x = np.where(ok, r * np.cos(a), np.nan)
    y = np.where(ok, r * np.sin(a), np.nan)
    if len(a) < 2:
        return x, y, np.full(len(a), np.inf), np.full(len(a), np.inf)
    gap = np.hypot(np.diff(x), np.diff(y))                     # NaN khi một trong hai tia không dùng được
    gap = np.where(np.isfinite(gap), gap, np.inf)
    prev = np.concatenate([[np.inf], gap])
    nxt = np.concatenate([gap, [np.inf]])
    if a[-1] - a[0] > 2 * math.pi - 0.05:                      # vòng 360°: tia đầu và tia cuối kề nhau
        wrap_gap = math.hypot(x[0] - x[-1], y[0] - y[-1])
        if math.isfinite(wrap_gap):
            prev[0] = nxt[-1] = wrap_gap
    return x, y, prev, nxt


def surface_normals(angles, ranges, config: OdometryConfig, half_window: int | None = None,
                    max_flatness: float = 0.25) -> np.ndarray:
    """Pháp tuyến đơn vị (M, 2), hệ cảm biến, của những điểm mà 2·half_window + 1 tia liền nhau đều chạm, liền mạch
    (mỗi khoảng ≤ `max_point_spacing_m`) và gần thẳng (phương sai ngang / phương sai dọc ≤ `max_flatness`)."""
    x, y, _, nxt = _ordered_endpoints(angles, ranges, config)
    n, k = len(x), config.normal_half_window if half_window is None else half_window
    if n < 2 * k + 1:
        return np.zeros((0, 2))
    spacing = config.max_point_spacing_m
    link = nxt <= spacing                                       # tia i nối liền với tia i+1
    idx = np.arange(k, n - k)
    win = idx[:, None] + np.arange(-k, k + 1)[None, :]
    good = np.all(link[win[:, :-1]], axis=1)
    if not good.any():
        return np.zeros((0, 2))
    wx, wy = x[win[good]], y[win[good]]
    dx = wx - wx.mean(axis=1, keepdims=True)
    dy = wy - wy.mean(axis=1, keepdims=True)
    sxx, syy, sxy = (dx * dx).mean(axis=1), (dy * dy).mean(axis=1), (dx * dy).mean(axis=1)
    tr, det = sxx + syy, sxx * syy - sxy * sxy
    disc = np.sqrt(np.maximum(tr * tr / 4 - det, 0.0))
    big, small = tr / 2 + disc, tr / 2 - disc
    straight = (big > 0) & (small <= max_flatness * big)
    angle = 0.5 * np.arctan2(2 * sxy, sxx - syy)                # hướng tiếp tuyến (vectơ riêng của trị riêng lớn)
    normals = np.column_stack([-np.sin(angle), np.cos(angle)])
    return normals[straight]


def normal_geometry(normals: np.ndarray) -> tuple[float, np.ndarray | None]:
    """(λmin/λmax của Σ n·nᵀ, hướng ứng với λmin trong hệ cảm biến). Hướng đó là hướng tịnh tiến mà bề mặt nhìn
    thấy không ràng buộc (dọc hành lang). Không có pháp tuyến nào thì (nan, None)."""
    if len(normals) == 0:
        return math.nan, None
    m = normals.T @ normals / len(normals)
    eig, vec = np.linalg.eigh(m)
    ratio = float(eig[0] / eig[1]) if eig[1] > 0 else 0.0
    return ratio, vec[:, 0]


def dense_points(angles, ranges, config: OdometryConfig) -> np.ndarray:
    """Điểm (x, y) hệ cảm biến dùng để khớp: tầm trong [min_range_m, max_range_m − match_margin_m] và có ít nhất một
    tia kề (theo thứ tự góc) chạm cách ≤ `max_point_spacing_m`.

    Vì sao lọc (thấy ngày 24/09/2026 trên hành lang tổng hợp): ở góc tới sượt, tường xa chỉ được lấy mẫu thành các chấm
    cách nhau nhiều ô, và vị trí chấm gắn với tư thế của vòng quét chứ không gắn với tường. Bản đồ dựng từ vòng trước
    có các chấm đó; vòng mới có chấm ở cùng vị trí tương đối với cảm biến, nên khớp chấm với chấm kéo chuyển động dọc
    tường về 0. Chỉ giữ điểm mà bề mặt được lấy mẫu dày ít nhất cỡ ô lưới thì trường khoảng cách của tường là liền, và
    chuyển động dọc tường không còn bị ghim giả. Điểm ở mép vật (một bên kề gần, một bên là nền xa) vẫn được giữ."""
    x, y, prev, nxt = _ordered_endpoints(angles, ranges, config)
    ok = np.isfinite(x) & (np.minimum(prev, nxt) <= config.max_point_spacing_m)
    return np.column_stack([x[ok], y[ok]])


# --- tinh chỉnh có số hạng dự đoán ----------------------------------------------------------------------------------

def refine_with_prior(lmap: LocalizationMap, points: np.ndarray, start, prior, prior_sigma: tuple[float, float, float],
                      iterations: int = 20, lock: tuple[np.ndarray, float] | None = None
                      ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Gauss-Newton/LM trên khoảng cách nội suy của `lmap` (trọng số Cauchy như `localize.refine`) cộng số hạng
    ((p − prior)/σ)². Trả (tư thế, hiệp phương sai 3×3 CHỈ của phần khớp scan theo cách của `localize.refine` (inf
    khi suy biến), ma trận JᵀWJ của phần khớp scan (đơn vị mét, để xét hướng suy biến)). Phần khớp scan đo bằng
    r = d/σ_map nên hai số hạng cùng thang đo. `lock` = (vectơ đơn vị u trong hệ bản đồ, σ): thêm số hạng
    ((p − prior)·u / σ)², giữ thành phần tịnh tiến dọc u theo dự đoán (dùng khi hình học suy biến theo u)."""
    cfg = lmap.config
    sigma, trunc = cfg.sigma_m, cfg.refine_trunc_m
    px, py = points[:, 0], points[:, 1]
    prior = np.asarray(prior, np.float64)
    info = np.diag([1.0 / prior_sigma[0] ** 2, 1.0 / prior_sigma[1] ** 2, 1.0 / prior_sigma[2] ** 2])
    if lock is not None:
        u = np.asarray(lock[0], np.float64)
        info[:2, :2] += np.outer(u, u) / lock[1] ** 2

    def prior_error(p):
        e = p - prior
        e[2] = wrap(e[2])
        return e

    def cost(p) -> float:
        c, s = math.cos(p[2]), math.sin(p[2])
        d, _, _, _ = lmap.distance_at(c * px - s * py + p[0], s * px + c * py + p[1])
        r = np.minimum(d, trunc) / sigma
        e = prior_error(p)
        return float(np.log1p(r * r).sum() + e @ info @ e)

    def linearize(p):
        c, s = math.cos(p[2]), math.sin(p[2])
        d, gx, gy, _ = lmap.distance_at(c * px - s * py + p[0], s * px + c * py + p[1])
        use = d < trunc
        r = d[use]
        w = 1.0 / (1.0 + (r / sigma) ** 2)
        jt = gx[use] * (-s * px[use] - c * py[use]) + gy[use] * (c * px[use] - s * py[use])
        return np.column_stack([gx[use], gy[use], jt]), r, w          # đơn vị mét

    pose = np.array(start, np.float64)
    current = cost(pose)
    lam = 1e-3
    for _ in range(iterations):
        jac, r, w = linearize(pose)
        h = (jac.T @ (jac * w[:, None])) / sigma ** 2 + info
        g = (jac.T @ (w * r)) / sigma ** 2 + info @ prior_error(pose)
        accepted = False
        step = np.zeros(3)
        for _ in range(8):
            try:
                step = -np.linalg.solve(h + lam * np.diag(np.diag(h)) + 1e-12 * np.eye(3), g)
            except np.linalg.LinAlgError:
                break
            candidate = pose + step
            candidate[2] = wrap(candidate[2])
            new_cost = cost(candidate)
            if new_cost < current:
                pose, current, lam, accepted = candidate, new_cost, max(lam / 3, 1e-7), True
                break
            lam *= 5
        if not accepted or np.all(np.abs(step) < 1e-6):
            break
    jac, r, w = linearize(pose)
    cov = np.full((3, 3), np.inf)
    h = jac.T @ (jac * w[:, None]) if len(r) else np.zeros((3, 3))
    if len(r) > 3:
        s2 = float((w * r * r).sum() / max(1.0, w.sum() - 3))
        eig = np.linalg.eigvalsh(h)
        if eig.min() > 1e-9 * max(1.0, eig.max()):
            cov = s2 * np.linalg.inv(h)
    return pose, cov, h


# --- odometry --------------------------------------------------------------------------------------------------------

class ScanOdometry:
    """Gọi `update(angles, ranges, t)` cho từng vòng quét theo thứ tự thời gian; `steps` giữ kết quả từng vòng.

    Hệ odometry = hệ của vòng quét hợp lệ đầu tiên (tư thế (0, 0, 0))."""

    def __init__(self, config: OdometryConfig | None = None):
        self.config = config or OdometryConfig()
        self.lcfg = self.config.localize_config()
        self.steps: list[OdometryStep] = []
        self.pose: np.ndarray | None = None
        self.velocity = np.zeros(3)           # chuyển động mỗi vòng (hệ thân), từ hai vòng chấp nhận gần nhất
        self._accepted_pose: np.ndarray | None = None   # tư thế của vòng chấp nhận (INIT/OK/AMBIGUOUS) gần nhất
        self._accepted_index = 0
        self.counts: OccupancyCounts | None = None
        self.keyframe_pose: np.ndarray | None = None
        self.keyframes = 0
        self.map_rebuilds = 0
        self.grid_growths = 0
        self._lmap: LocalizationMap | None = None
        self._lmap_center: np.ndarray | None = None
        self._dirty = True
        self._failures = 0

    # bản đồ tham chiếu ------------------------------------------------------------------------------------------------

    def _half_size(self) -> float:
        cfg = self.config
        return cfg.max_range_m + cfg.retry_scale * max(cfg.window_x_m, cfg.window_y_m) + 2 * cfg.resolution_m

    def _new_counts(self, center, half: float) -> OccupancyCounts:
        res = self.config.resolution_m
        cx, cy = (math.floor(v / res) * res for v in center[:2])
        cells = int(math.ceil(half / res))
        return OccupancyCounts(GridSpec(cx - cells * res, cx + cells * res, cy - cells * res, cy + cells * res, res))

    def _ensure_extent(self, pose) -> None:
        """Nới lưới bền khi vùng quét quanh `pose` ra ngoài lưới; ô cũ giữ nguyên chỉ số lưới (không lấy mẫu lại)."""
        cfg, g = self.config, self.counts.grid
        res, reach = g.resolution, cfg.max_range_m + 2 * cfg.resolution_m
        need = (pose[0] - reach, pose[0] + reach, pose[1] - reach, pose[1] + reach)
        if need[0] >= g.x_min and need[1] <= g.x_max and need[2] >= g.y_min and need[3] <= g.y_max:
            return
        grow = cfg.map_grow_m
        add_left = int(math.ceil(max(0.0, g.x_min - need[0] + grow) / res)) if need[0] < g.x_min else 0
        add_right = int(math.ceil(max(0.0, need[1] - g.x_max + grow) / res)) if need[1] > g.x_max else 0
        add_bottom = int(math.ceil(max(0.0, g.y_min - need[2] + grow) / res)) if need[2] < g.y_min else 0
        add_top = int(math.ceil(max(0.0, need[3] - g.y_max + grow) / res)) if need[3] > g.y_max else 0
        rows, cols = g.shape
        grid = GridSpec(g.x_min - add_left * res, g.x_min + (cols + add_right) * res,
                        g.y_min - add_bottom * res, g.y_min + (rows + add_top) * res, res)
        bigger = OccupancyCounts(grid)
        bigger.passes[add_bottom:add_bottom + rows, add_left:add_left + cols] = self.counts.passes
        bigger.hits[add_bottom:add_bottom + rows, add_left:add_left + cols] = self.counts.hits
        bigger.scans, bigger.beams_used = self.counts.scans, self.counts.beams_used
        self.counts = bigger
        self.grid_growths += 1

    def _insert(self, angles: np.ndarray, ranges: np.ndarray, pose: np.ndarray) -> None:
        cfg = self.config
        if cfg.mode == SCAN_TO_SCAN or self.counts is None:
            half = self._half_size() if cfg.mode == SCAN_TO_SCAN else self._half_size() + cfg.map_grow_m
            self.counts = self._new_counts(pose, half)
        if cfg.mode == SCAN_TO_MAP:
            self._ensure_extent(pose)
        self.counts.add_scan(_Beams(angles, ranges), tuple(pose), max_range=cfg.max_range_m, min_range=cfg.min_range_m)
        self.keyframe_pose = np.array(pose, np.float64)
        self.keyframes += 1
        self._dirty = True

    def states(self) -> np.ndarray | None:
        """Trạng thái ô của bản đồ tham chiếu hiện tại (lưới `self.counts.grid`)."""
        if self.counts is None:
            return None
        cfg = self.config
        return states_from_counts(self.counts.passes, self.counts.hits, min_passes=cfg.map_min_passes,
                                  min_hits=cfg.map_min_hits, occupied_ratio=cfg.map_occupied_ratio)

    def _matching_map(self, center: np.ndarray) -> LocalizationMap | None:
        if (not self._dirty and self._lmap is not None and self._lmap_center is not None
                and math.hypot(center[0] - self._lmap_center[0], center[1] - self._lmap_center[1])
                <= self.config.recrop_dist_m):
            return self._lmap
        cfg, g = self.config, self.counts.grid
        res, half = g.resolution, self._half_size()
        rows, cols = g.shape
        c0 = max(0, int(math.floor((center[0] - half - g.x_min) / res)))
        c1 = min(cols, int(math.ceil((center[0] + half - g.x_min) / res)))
        r0 = max(0, int(math.floor((center[1] - half - g.y_min) / res)))
        r1 = min(rows, int(math.ceil((center[1] + half - g.y_min) / res)))
        self._dirty, self._lmap_center, self._lmap = False, np.array(center, np.float64), None
        if c1 - c0 < 2 or r1 - r0 < 2:
            return None
        states = states_from_counts(self.counts.passes[r0:r1, c0:c1], self.counts.hits[r0:r1, c0:c1],
                                    min_passes=cfg.map_min_passes, min_hits=cfg.map_min_hits,
                                    occupied_ratio=cfg.map_occupied_ratio)
        if not (states == OCCUPIED).any():
            return None
        grid = GridSpec(g.x_min + c0 * res, g.x_min + c1 * res, g.y_min + r0 * res, g.y_min + r1 * res, res)
        self._lmap = LocalizationMap(states, grid, self.lcfg, source="scan_odometry")
        self.map_rebuilds += 1
        return self._lmap

    # một vòng quét ----------------------------------------------------------------------------------------------------

    def update(self, angles, ranges, t: float | None = None) -> OdometryStep:
        t0 = time.perf_counter()
        cfg = self.config
        index = len(self.steps)
        t = float(index if t is None else t)
        angles = np.asarray(angles, np.float64)
        ranges = np.asarray(ranges, np.float64)
        points = dense_points(angles, ranges, cfg)
        enough = len(points) >= max(3, cfg.min_valid_beams)

        def record(step: OdometryStep) -> OdometryStep:
            step.time_ms = (time.perf_counter() - t0) * 1e3
            self.steps.append(step)
            return step

        if self.pose is None:
            if not enough:
                return record(OdometryStep(index, t, FAILED, ("too_few_beams", "not_initialised"), 0.0, 0.0, 0.0,
                                           (0.0, 0.0, 0.0), valid_beams=len(points)))
            self.pose = np.zeros(3)
            self._accepted_pose, self._accepted_index = self.pose.copy(), index
            self._insert(angles, ranges, self.pose)
            return record(OdometryStep(index, t, INIT, (), 0.0, 0.0, 0.0, (0.0, 0.0, 0.0), valid_beams=len(points),
                                       matched=len(points), matched_fraction=1.0, keyframe=True))

        predicted = compose(self.pose, self.velocity) if cfg.motion_model == "constant_velocity" else self.pose.copy()

        def fail(reasons: list[str], **extra) -> OdometryStep:
            self._failures += 1
            if self._failures >= cfg.lost_after:
                reasons = reasons + ["lost"]
                self.velocity = np.zeros(3)        # lạc: thôi ngoại suy (quay/chạy tiếp mãi theo vận tốc cũ còn tệ hơn)
            self.pose = predicted                  # chạy theo dự đoán; không thêm khung khóa
            return record(OdometryStep(index, t, FAILED, tuple(reasons), float(predicted[0]), float(predicted[1]),
                                       float(predicted[2]), tuple(float(v) for v in predicted),
                                       valid_beams=len(points), **extra))

        if not enough:
            return fail(["too_few_beams"])
        lmap = self._matching_map(predicted)
        if lmap is None:
            return fail(["empty_map"])
        search_points = decimate(points, lmap.res)
        normals = surface_normals(angles, ranges, cfg)
        normal_ratio, weak_dir = normal_geometry(normals)
        geometric_degenerate = len(normals) >= cfg.min_normals and normal_ratio < cfg.min_normal_ratio
        window = (cfg.window_x_m, cfg.window_y_m, math.radians(cfg.window_theta_deg))
        used = window
        found = lmap.search(search_points, tuple(predicted), window, keep_ratio=1.0)
        retried = False
        if found["at_edge"]:
            retried = True
            used = tuple(v * cfg.retry_scale for v in window)
            found = lmap.search(search_points, tuple(predicted), used, keep_ratio=1.0)
        discrete = np.array([found["x"], found["y"], found["theta"]])
        sigma = (cfg.prior_sigma_xy_m, cfg.prior_sigma_xy_m, math.radians(cfg.prior_sigma_theta_deg))
        lock = None
        at_edge, edge_along_axis = bool(found["at_edge"]), False
        if geometric_degenerate:
            c, s = math.cos(predicted[2]), math.sin(predicted[2])
            u = np.array([c * weak_dir[0] - s * weak_dir[1], s * weak_dir[0] + c * weak_dir[1]])
            lock = (u, cfg.lock_sigma_m)
            shift = discrete[:2] - predicted[:2]
            across = shift - (shift @ u) * u
            if at_edge:
                # Đỉnh ở mép cửa sổ: chỉ tính là mép nếu mép theo hướng (θ) hoặc theo thành phần NGANG u. Thành phần
                # dọc u bị bỏ ngay dưới đây (điểm xuất phát tinh chỉnh = dự đoán theo u), nên mép theo u không nói gì.
                step_th = math.radians(found["angle_step_deg"])
                n_half = (found["angles"] - 1) // 2
                theta_edge = found["angles"] > 1 and abs(wrap(found["theta"] - predicted[2])) >= n_half * step_th - 1e-9
                xy_edge = math.hypot(across[0], across[1]) >= min(used[0], used[1]) - lmap.res
                at_edge = bool(theta_edge or xy_edge)
                edge_along_axis = not at_edge
            discrete = np.array([*(predicted[:2] + across), discrete[2]])
        pose, cov, _ = refine_with_prior(lmap, search_points, discrete, predicted, sigma, cfg.refine_iterations,
                                         lock=lock)
        # Kiểm trên tập điểm đã tỉa (một điểm mỗi ô) như khi khớp: mật độ đều theo không gian, và kiểm xuyên tường
        # trên mọi tia chiếm phần lớn thời gian mỗi vòng (đo bằng cProfile 24/09/2026 trên phòng tổng hợp).
        evaluation = lmap.evaluate(search_points, pose)
        matched, conflicts = evaluation["matched"], evaluation["conflicts"]
        matched_fraction = matched / len(search_points)
        conflict_fraction = conflicts / (matched + conflicts) if matched + conflicts else 0.0
        with np.errstate(invalid="ignore"):
            finite = bool(np.all(np.isfinite(cov)))
            std = np.sqrt(np.diag(cov)) if finite else np.full(3, np.inf)
            std_xy = math.sqrt(max(float(np.linalg.eigvalsh(cov[:2, :2]).max()), 0.0)) if finite else math.inf
        quality = dict(matched=matched, matched_fraction=matched_fraction, conflict_fraction=conflict_fraction,
                       std_x_m=float(std[0]), std_y_m=float(std[1]), std_theta_deg=math.degrees(float(std[2])),
                       conflicts_short=evaluation["short"], conflicts_through=evaluation["through"],
                       normal_ratio=normal_ratio, normals=len(normals), locked=lock is not None, retried=retried)
        failures = []
        if at_edge:
            failures.append("window_edge")
        if matched < cfg.min_matched:
            failures.append("few_matched")
        if matched_fraction < cfg.min_matched_fraction:
            failures.append("low_match_fraction")
        if conflicts and conflict_fraction > cfg.max_conflict_fraction:
            failures.append("conflicts_with_map")
        if failures:
            return fail(failures, **quality)
        self._failures = 0
        reasons = []
        weak = not (std_xy <= cfg.max_std_xy_m and std[2] <= math.radians(cfg.max_std_theta_deg))
        if weak or geometric_degenerate:
            reasons.append("degenerate")
        if retried:
            reasons.append("window_retry")
        if edge_along_axis:
            reasons.append("edge_along_axis")
        status = AMBIGUOUS if "degenerate" in reasons else OK
        # Vận tốc từ vòng CHẤP NHẬN gần nhất, chia đều cho số vòng đã qua. Sau các vòng FAILED, `self.pose` chỉ là dự
        # đoán (hoặc đứng yên khi đã `lost`); between(self.pose, pose) sẽ dồn cả đoạn đi lúc mù vào một vòng rồi ngoại
        # suy tiếp (tái hiện 24/09/2026 trên phòng tổng hợp: 0,35 m/vòng thay vì 0,03 m/vòng ngay sau khi bắt lại).
        gap = index - self._accepted_index
        self.velocity = scale_motion(between(self._accepted_pose, pose), 1.0 / gap)
        self._accepted_pose, self._accepted_index = pose.copy(), index
        self.pose = pose
        keyframe = False
        if cfg.mode == SCAN_TO_SCAN:
            keyframe = True
        else:
            moved = between(self.keyframe_pose, pose)
            keyframe = (math.hypot(moved[0], moved[1]) >= cfg.keyframe_dist_m
                        or abs(moved[2]) >= math.radians(cfg.keyframe_angle_deg))
        if keyframe:
            self._insert(angles, ranges, pose)
        return record(OdometryStep(index, t, status, tuple(reasons), float(pose[0]), float(pose[1]), float(pose[2]),
                                   tuple(float(v) for v in predicted), valid_beams=len(points), keyframe=keyframe,
                                   **quality))

    # tiện ích ---------------------------------------------------------------------------------------------------------

    def poses(self) -> np.ndarray:
        return np.array([step.pose for step in self.steps]) if self.steps else np.zeros((0, 3))

    def summary(self) -> dict:
        status = Counter(step.status for step in self.steps)
        reasons = Counter(reason for step in self.steps for reason in step.reasons)
        times = np.array([step.time_ms for step in self.steps]) if self.steps else np.zeros(0)
        matched = [step.matched_fraction for step in self.steps if step.status in (OK, AMBIGUOUS)]
        return {"scans": len(self.steps), "init": status.get(INIT, 0), "ok": status.get(OK, 0),
                "ambiguous": status.get(AMBIGUOUS, 0), "failed": status.get(FAILED, 0), "reasons": dict(reasons),
                "keyframes": self.keyframes, "map_rebuilds": self.map_rebuilds, "grid_growths": self.grid_growths,
                "matched_fraction_median": float(np.median(matched)) if matched else None,
                "time_ms": {"median": float(np.median(times)), "p95": float(np.percentile(times, 95)),
                            "max": float(times.max())} if len(times) else None}


# --- so sánh quỹ đạo ------------------------------------------------------------------------------------------------

def path_length(poses: np.ndarray) -> np.ndarray:
    """Quãng đường cộng dồn (m) theo từng tư thế, bắt đầu 0."""
    poses = np.asarray(poses, np.float64)
    if len(poses) < 2:
        return np.zeros(len(poses))
    return np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(poses[:, 0]), np.diff(poses[:, 1])))])


def _stats(values: np.ndarray) -> dict | None:
    if len(values) == 0:
        return None
    return {"n": int(len(values)), "median": float(np.median(values)), "p95": float(np.percentile(values, 95)),
            "max": float(values.max()), "mean": float(values.mean())}


def compare_trajectories(est, ref, *, segment_lengths=(1.0, 5.0), valid=None, yaw_window: int = 10) -> dict:
    """So hai quỹ đạo cùng số tư thế, cùng gốc (mỗi quỹ đạo biểu diễn tương đối với tư thế đầu của chính nó).

    Đây là **chênh lệch giữa hai ước lượng**, không phải sai số, trừ khi `ref` là ground truth. Gồm:
    - `end`: tư thế cuối của `est` nhìn từ tư thế cuối của `ref` (tịnh tiến, quay), và tịnh tiến / quãng đường `ref`.
    - `segments[L]`: với mỗi i, j đầu tiên mà `ref` đã đi ≥ L mét kể từ i: E = (ref_i⁻¹ref_j)⁻¹(est_i⁻¹est_j); thống
      kê |E.xy| (m và % của L) và |E.θ| (độ, và độ/m). `valid` (mảng bool) bỏ các cặp có vòng không hợp lệ ở hai đầu.
    - `yaw_gain`: hệ số hồi quy qua gốc của Δθ của `est` theo `ref` trên các đoạn liền nhau dài `yaw_window` bước
      (≈ 1 khi cùng chiều quay, ≈ −1 khi một trong hai bị lật gương trái/phải), kèm hệ số tương quan. Không lấy từng
      bước: nhiễu thời gian của tham chiếu làm hệ số hồi quy từng bước bị kéo về 0 (DROW: 0,88 từng bước, 1,00 trên
      đoạn ≥ 5 bước; đo 24/09/2026). `step_ratio` = tổng |Δxy| từng bước của `est` / tổng của `ref`."""
    est = relative_to_first(est)
    ref = relative_to_first(ref)
    if est.shape != ref.shape:
        raise ValueError(f"hai quỹ đạo khác số tư thế ({est.shape} / {ref.shape})")
    n = len(ref)
    valid = np.ones(n, bool) if valid is None else np.asarray(valid, bool)
    cum = path_length(ref)
    out: dict = {"poses": int(n), "path_ref_m": float(cum[-1]) if n else 0.0,
                 "path_est_m": float(path_length(est)[-1]) if n else 0.0}
    rot = np.abs(wrap(np.diff(ref[:, 2]))) if n > 1 else np.zeros(0)
    out["rotation_ref_deg"] = float(np.degrees(rot.sum()))
    if n:
        end = between(ref[-1], est[-1])
        moved = math.hypot(end[0], end[1])
        out["end"] = {"translation_m": float(moved), "rotation_deg": float(abs(math.degrees(end[2]))),
                      "translation_pct_of_path": float(100 * moved / cum[-1]) if cum[-1] > 0 else None}
    if n > 1:
        d_ref = between_many(ref[:-1], ref[1:])
        d_est = between_many(est[:-1], est[1:])
        ok = valid[:-1] & valid[1:]
        w = max(1, int(yaw_window))
        starts = np.arange(0, n - w, w)
        keep = valid[starts] & valid[starts + w]
        a, b = starts[keep], starts[keep] + w
        yaw_ref = np.unwrap(ref[:, 2])
        yaw_est = np.unwrap(est[:, 2])
        dr, de = yaw_ref[b] - yaw_ref[a], yaw_est[b] - yaw_est[a]
        denom = float((dr ** 2).sum())
        out["yaw_window_steps"] = w
        out["yaw_gain"] = float((de * dr).sum() / denom) if denom > 1e-12 else None
        out["yaw_corr"] = float(np.corrcoef(de, dr)[0, 1]) if len(dr) > 2 and dr.std() > 0 and de.std() > 0 else None
        ref_steps = float(np.hypot(d_ref[ok, 0], d_ref[ok, 1]).sum())
        out["step_ratio"] = float(np.hypot(d_est[ok, 0], d_est[ok, 1]).sum() / ref_steps) if ref_steps > 1e-9 else None
    segments = {}
    for length in segment_lengths:
        j = np.searchsorted(cum, cum + length - 1e-12, side="left")
        i = np.nonzero(j < n)[0]
        j = j[i]
        keep = valid[i] & valid[j]
        i, j = i[keep], j[keep]
        if len(i) == 0:
            segments[f"{length:g}"] = None
            continue
        e = between_many(between_many(ref[i], ref[j]), between_many(est[i], est[j]))
        trans = np.hypot(e[:, 0], e[:, 1])
        rot_err = np.degrees(np.abs(e[:, 2]))
        actual = cum[j] - cum[i]
        segments[f"{length:g}"] = {"translation_m": _stats(trans), "translation_pct": _stats(100 * trans / actual),
                                   "rotation_deg": _stats(rot_err), "rotation_deg_per_m": _stats(rot_err / actual)}
    out["segments"] = segments
    return out


def static_drift(poses, t) -> dict:
    """Cho cảm biến đứng yên: tư thế phải giữ nguyên. Trả tư thế cuối, lệch lớn nhất và tốc độ trôi mỗi phút (từ tư
    thế cuối chia thời lượng, và từ độ dốc hồi quy tuyến tính theo thời gian)."""
    poses = relative_to_first(poses)
    t = np.asarray(t, np.float64) - float(t[0])
    duration = float(t[-1]) if len(t) else 0.0
    dist = np.hypot(poses[:, 0], poses[:, 1])
    th = np.degrees(poses[:, 2])
    out = {"poses": int(len(poses)), "duration_s": duration,
           "end_translation_m": float(dist[-1]), "end_rotation_deg": float(th[-1]),
           "max_excursion_m": float(dist.max()), "max_excursion_deg": float(np.abs(th).max()),
           "jitter_std_m": float(math.hypot(poses[:, 0].std(), poses[:, 1].std())), "jitter_std_deg": float(th.std())}
    if duration > 0 and len(t) >= 3:
        scale = 60.0 / duration
        out["per_minute_end_translation_m"] = float(dist[-1] * scale)
        out["per_minute_end_rotation_deg"] = float(abs(th[-1]) * scale)
        sx, sy, sth = (float(np.polyfit(t, v, 1)[0]) * 60.0 for v in (poses[:, 0], poses[:, 1], th))
        out["slope_per_minute"] = {"translation_m": float(math.hypot(sx, sy)), "x_m": sx, "y_m": sy, "theta_deg": sth}
    return out


# --- chạy trên bản ghi ------------------------------------------------------------------------------------------------

def run_sequence(scans, config: OdometryConfig) -> ScanOdometry:
    """`scans` = dãy (angles, ranges, t). Trả đối tượng odometry đã chạy hết dãy."""
    odometry = ScanOdometry(config)
    for angles, ranges, t in scans:
        odometry.update(angles, ranges, t)
    return odometry


def _c1_scans(recording, indices, mirror: bool):
    for index in indices:
        angles, ranges, _ = recording.beams(index)
        angles = np.asarray(angles, np.float64)
        t = float(recording.t[index] - recording.t[0])
        yield (-angles if mirror else angles), np.asarray(ranges, np.float64), t


def _drow_scans(recording, angles, indices):
    for index in indices:
        yield angles, recording.ranges[index], float(recording.t[index] - recording.t[0])


def interpolate_odometry(odom_t: np.ndarray, odom_xya: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Tư thế odometry nội suy tuyến tính tại thời điểm `t` (yaw nội suy sau khi gỡ quấn); ngoài khoảng thì giữ đầu
    mút."""
    yaw = np.unwrap(odom_xya[:, 2])
    order = np.argsort(odom_t, kind="stable")
    ot = odom_t[order]
    return np.column_stack([np.interp(t, ot, odom_xya[order, 0]), np.interp(t, ot, odom_xya[order, 1]),
                            wrap(np.interp(t, ot, yaw[order]))])


def _display_map(scans_for_map, poses: np.ndarray, extra_poses: list[np.ndarray], max_range: float, min_range: float,
                 base_res: float) -> tuple[np.ndarray, GridSpec]:
    """Bản đồ chỉ để vẽ: tia của một số vòng đặt theo tư thế ước lượng (bản đồ nét = quỹ đạo nhất quán)."""
    everything = np.vstack([poses] + [p for p in extra_poses if len(p)])
    lo = everything[:, :2].min(axis=0) - max_range
    hi = everything[:, :2].max(axis=0) + max_range
    res = max(base_res, float(max(hi - lo)) / 700.0)
    res = math.ceil(res / base_res) * base_res
    lo = np.floor(lo / res) * res
    hi = lo + np.ceil((hi - lo) / res) * res
    counts = OccupancyCounts(GridSpec(float(lo[0]), float(hi[0]), float(lo[1]), float(hi[1]), res))
    for (angles, ranges), pose in scans_for_map:
        counts.add_scan(_Beams(angles, ranges), tuple(pose), max_range=max_range, min_range=min_range)
    return counts.states(), counts.grid


def render_trajectories(states: np.ndarray, grid: GridSpec, est: np.ndarray, steps: list[OdometryStep],
                        ref: np.ndarray | None, title: str) -> np.ndarray:
    """Nền = bản đồ dựng từ tư thế ước lượng (x lên trên, y sang trái như costmap). Xanh dương = quỹ đạo khớp scan;
    tím = odometry tham chiếu (DROW, không phải ground truth); X đen = vòng FAILED. Chữ ASCII (phông Hershey)."""
    scale = max(1, int(900 / max(states.shape)))
    canvas = render(states, grid, None, None, scale=scale)

    def px(x, y):
        return int((grid.y_max - y) / grid.resolution * scale), int((grid.x_max - x) / grid.resolution * scale)

    for poses, color in ((ref, REF_COLOR), (est, EST_COLOR)):
        if poses is None or len(poses) < 2:
            continue
        pts = np.array([px(x, y) for x, y in poses[:, :2]], np.int32)
        cv2.polylines(canvas, [pts.reshape(-1, 1, 2)], False, color, 2, cv2.LINE_AA)
    for step, pose in zip(steps, est):
        if step.status == FAILED:
            cv2.drawMarker(canvas, px(pose[0], pose[1]), FAIL_COLOR, cv2.MARKER_TILTED_CROSS, 7, 1)
    legend = "blue = scan matching" + ("   magenta = DROW odometry (NOT ground truth)" if ref is not None else "")
    lines = title.split("\n") + [legend,
                                 "black X = FAILED scan (pose = prediction)"]
    font, size = cv2.FONT_HERSHEY_SIMPLEX, 0.45
    widest = max(cv2.getTextSize(line, font, size, 1)[0][0] for line in lines)
    size = max(0.3, min(size, size * (canvas.shape[1] - 12) / max(widest, 1)))
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1] - 1, 17 * len(lines) + 4), (40, 40, 40), -1)
    for k, line in enumerate(lines):
        cv2.putText(canvas, line, (6, 16 + 17 * k), font, size, (255, 255, 255), 1, cv2.LINE_AA)
    return canvas


def _write_png(path: Path, image: np.ndarray) -> None:
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"không mã hóa được {path.name}")
    path.write_bytes(data.tobytes())


CSV_FIELDS = ("index", "t_s", "status", "reasons", "x_m", "y_m", "theta_deg", "pred_x_m", "pred_y_m", "pred_theta_deg",
              "valid_beams", "matched", "matched_fraction", "conflict_fraction", "conflicts_short", "conflicts_through",
              "std_x_m", "std_y_m", "std_theta_deg", "normal_ratio", "normals", "locked", "keyframe", "time_ms",
              "ref_x_m", "ref_y_m",
              "ref_theta_deg")


def _write_csv(path: Path, steps: list[OdometryStep], ref: np.ndarray | None) -> None:
    def num(value, fmt):
        return "" if value is None or not math.isfinite(value) else format(value, fmt)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_FIELDS)
        for k, step in enumerate(steps):
            r = ref[k] if ref is not None else (None, None, None)
            writer.writerow([step.index, f"{step.t:.3f}", step.status, "+".join(step.reasons), f"{step.x:.4f}",
                             f"{step.y:.4f}", f"{math.degrees(step.theta):.3f}", f"{step.predicted[0]:.4f}",
                             f"{step.predicted[1]:.4f}", f"{math.degrees(step.predicted[2]):.3f}", step.valid_beams,
                             step.matched, f"{step.matched_fraction:.4f}", f"{step.conflict_fraction:.4f}",
                             step.conflicts_short, step.conflicts_through, num(step.std_x_m, ".5f"),
                             num(step.std_y_m, ".5f"), num(step.std_theta_deg, ".4f"), num(step.normal_ratio, ".4f"),
                             step.normals, int(step.locked),
                             int(step.keyframe), f"{step.time_ms:.1f}", num(r[0], ".4f"), num(r[1], ".4f"),
                             "" if r[2] is None or not math.isfinite(r[2]) else f"{math.degrees(r[2]):.3f}"])


def _clean(value):
    if isinstance(value, dict):
        return {key: _clean(v) for key, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, np.generic):
        return _clean(value.item())
    return value


def run_c1(path, out: Path, config: OdometryConfig, *, skip_seconds: float = 0.0, start: int = 0,
           limit: int | None = None, mirror: bool = False, png: bool = True, name: str | None = None) -> dict:
    """Một bản ghi `.npz` của `lidar.recording` (C1). Không có tham chiếu chuyển động: báo độ trôi như cảm biến
    đứng yên (đúng với mọi bản ghi C1 đến 24/09/2026; bản ghi có cảm biến di chuyển thì các số này không có nghĩa).
    `name` = tên gốc tệp kết quả (mặc định `input_stem`; `main` truyền tên từ `output_names` để không trùng)."""
    from .recording import read_recording

    recording = read_recording(path)
    indices = [i for i in range(start, len(recording)) if recording.t[i] - recording.t[0] >= skip_seconds]
    if limit is not None:
        indices = indices[:limit]
    odometry = run_sequence(_c1_scans(recording, indices, mirror), config)
    est = odometry.poses()
    t = np.array([step.t for step in odometry.steps])
    stem = name or input_stem("c1", path)
    tag = f"{stem}__{config.mode}{'__mirror' if mirror else ''}"
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(out / f"{tag}.csv", odometry.steps, None)
    started = next((k for k, step in enumerate(odometry.steps) if step.status == INIT), None)
    result = {"input": str(path), "name": stem, "kind": "c1_recording", "mode": config.mode, "mirror": mirror,
              "recording_meta": {key: recording.meta.get(key) for key in ("source_id", "started_utc", "name", "note",
                                                                          "placement", "rig_recording", "clock")},
              "skip_seconds": skip_seconds, "start": start, "scans_used": len(indices),
              "summary": odometry.summary(),
              "static_drift": (static_drift(est[started:], t[started:])
                               if started is not None and len(est) - started >= 2 else None),
              "files": {"csv": f"{tag}.csv"}}
    if png and started is not None:
        chosen = indices[started::max(1, (len(indices) - started) // 60)]
        pairs = [(recording.beams(i)[:2], est[indices.index(i)]) for i in chosen]
        pairs = [((-np.asarray(a, np.float64) if mirror else np.asarray(a, np.float64), np.asarray(r, np.float64)), p)
                 for (a, r), p in pairs]
        states, grid = _display_map(pairs, est[started:], [], config.max_range_m, config.min_range_m,
                                    config.resolution_m)
        sd = result["static_drift"] or {}
        title = (f"{stem}  {config.mode}  C1, sensor static\n"
                 f"end {1000 * sd.get('end_translation_m', float('nan')):.1f} mm  "
                 f"{sd.get('end_rotation_deg', float('nan')):+.3f} deg"
                 f"  over {sd.get('duration_s', float('nan')):.1f} s")
        image = render_trajectories(states, grid, est[started:], odometry.steps[started:], None, title)
        _write_png(out / f"{tag}.png", image)
        result["files"]["png"] = f"{tag}.png"
    return result


def run_drow(csv_path, out: Path, config: OdometryConfig, *, start: int = 0, limit: int | None = None,
             mirror: bool = False, png: bool = True, name: str | None = None) -> dict:
    """Một chuỗi DROW v2 (`.csv` + `.odom2` cùng tên). So quỹ đạo khớp scan với odometry đi kèm DROW, ghép theo chỉ
    số dòng như loader của tác giả, và thêm một bản nội suy odometry theo thời gian vòng quét để thấy độ nhạy.
    `name` như ở `run_c1`."""
    from .drow import drow_angles, read_drow_csv
    from .drow_odom import read_drow_odom

    csv_path = Path(csv_path)
    recording = read_drow_csv(csv_path)
    odom = read_drow_odom(csv_path.with_suffix(".odom2"))
    if len(odom) != len(recording):
        raise ValueError(f"{csv_path.name}: {len(odom)} dòng odometry cho {len(recording)} vòng quét")
    stop = len(recording) if limit is None else min(len(recording), start + limit)
    indices = list(range(start, stop))
    angles = drow_angles(mirror=mirror)
    odometry = run_sequence(_drow_scans(recording, angles, indices), config)
    est = odometry.poses()
    started = next((k for k, step in enumerate(odometry.steps) if step.status == INIT), None)
    ref_rows = odom.xya[indices]
    ref_interp = interpolate_odometry(odom.t, odom.xya, recording.t[indices])
    stem = name or input_stem("drow", csv_path)
    tag = f"{stem}__{config.mode}{'__mirror' if mirror else ''}"
    out.mkdir(parents=True, exist_ok=True)
    result = {"input": str(csv_path), "name": stem, "kind": "drow", "mode": config.mode, "mirror": mirror,
              "start": start, "scans_used": len(indices),
              "duration_s": float(recording.t[stop - 1] - recording.t[start]) if indices else 0.0,
              "summary": odometry.summary(), "files": {"csv": f"{tag}.csv"}}
    if started is None:
        _write_csv(out / f"{tag}.csv", odometry.steps, None)
        result["comparison"] = None
        return result
    valid = np.array([step.status in (INIT, OK, AMBIGUOUS) for step in odometry.steps[started:]])
    ref_rel = relative_to_first(ref_rows[started:])
    result["comparison"] = {
        "reference": "DROW .odom2 ghép theo dòng (loader tác giả); KHÔNG phải ground truth",
        "all_steps": compare_trajectories(est[started:], ref_rows[started:]),
        "accepted_steps_only": compare_trajectories(est[started:], ref_rows[started:], valid=valid),
        "odometry_interpolated_at_scan_time": compare_trajectories(est[started:], ref_interp[started:]),
        "odometry_rows_vs_interpolated": compare_trajectories(ref_interp[started:], ref_rows[started:])}
    full_ref = np.zeros_like(est)
    full_ref[started:] = ref_rel
    _write_csv(out / f"{tag}.csv", odometry.steps, np.where(np.arange(len(est))[:, None] >= started, full_ref, np.nan))
    if png:
        every = max(1, (len(indices) - started) // 400)
        pairs = [((angles, recording.ranges[indices[k]]), est[k]) for k in range(started, len(indices), every)
                 if odometry.steps[k].status in (INIT, OK, AMBIGUOUS)]
        states, grid = _display_map(pairs, est[started:], [ref_rel], config.max_range_m, config.min_range_m,
                                    max(config.resolution_m, 0.05))
        cmp = result["comparison"]["all_steps"]
        seg = (cmp["segments"].get("5") or {}).get("translation_pct") or {}
        title = (f"{stem}  {config.mode}{'  MIRRORED' if mirror else ''}  DROW v2 (Beyer et al., MIT)\n"
                 f"path {cmp['path_ref_m']:.1f} m  end diff {cmp['end']['translation_m']:.2f} m "
                 f"{cmp['end']['rotation_deg']:.1f} deg  5 m segments median {seg.get('median', float('nan')):.1f} %")
        _write_png(out / f"{tag}.png", render_trajectories(states, grid, est[started:], odometry.steps[started:],
                                                           ref_rel, title))
        result["files"]["png"] = f"{tag}.png"
    return result


def input_stem(kind: str, path) -> str:
    """Tên gốc mặc định của tệp kết quả: `.npz` C1 bỏ đuôi; DROW bỏ `.bag.csv` / `.csv`."""
    path = Path(path)
    return path.stem if kind == "c1" else path.name.replace(".bag.csv", "").replace(".csv", "")


def output_names(inputs) -> list[str]:
    """Tên gốc tệp kết quả cho từng (kind, path), không trùng nhau trong một `--out`.

    Đầu vào trùng tên (vd. hai `l01_tinh.npz` của hai phiên, hay các `part_0000.npz` của bàn thử) thì thêm dần thư mục
    cha, nối bằng `__` (`may_moi_20260924_toi__lidar__l01_tinh`), đến khi khác nhau; tên không trùng giữ nguyên. Không
    dùng ký tự ổ đĩa; vẫn trùng (hai ổ đĩa cùng cây thư mục) thì thêm số thứ tự. Cùng một tệp đưa hai lần → ValueError
    (nếu không, hai việc sẽ ghi cùng một `.csv`/`.png`)."""
    inputs = [(kind, Path(path)) for kind, path in inputs]
    resolved = [path.resolve() for _, path in inputs]
    if len(set(resolved)) < len(resolved):
        raise ValueError("cùng một tệp đầu vào được đưa hai lần")
    stems = [input_stem(kind, path) for kind, path in inputs]
    parents = [list(r.parent.parts[1:]) for r in resolved]           # bỏ gốc ổ đĩa ("D:\\")
    names = list(stems)
    for depth in range(1, max((len(p) for p in parents), default=0) + 1):
        clash = {n for n in names if names.count(n) > 1}
        if not clash:
            break
        names = ["__".join(p[-depth:] + [s]) if n in clash else n for p, s, n in zip(parents, stems, names)]
    if len(set(names)) < len(names):
        names = [f"{k:02d}__{s}" for k, s in enumerate(stems)]
    return names


def expand_drow_inputs(paths) -> list[Path]:
    """Tệp `.csv` giữ nguyên; thư mục thành mọi `*.csv` trong đó có `.odom2` cùng tên (sắp theo tên)."""
    out: list[Path] = []
    for path in map(Path, paths):
        if path.is_dir():
            out += sorted(p for p in path.glob("*.csv") if p.with_suffix(".odom2").exists())
        else:
            out.append(path)
    return out


def _worker_init() -> None:
    cv2.setNumThreads(1)          # nhiều tiến trình song song: tránh mỗi tiến trình lại mở nhiều luồng OpenCV


def _run_job(job: tuple) -> dict:
    kind, path, config, out, options = job
    if kind == "c1":
        return run_c1(path, out, config, **options)
    return run_drow(path, out, config, **options)


def main(argv=None) -> int:
    from .recording import git_commit

    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("--recording", type=Path, nargs="+", default=[], help=".npz của autopark.lidar.recording (C1)")
    parser.add_argument("--drow", type=Path, nargs="+", default=[],
                        help="DROW v2 .bag.csv (cần .odom2 cùng tên) hoặc thư mục chứa chúng")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=(*MODES, "both"), default=SCAN_TO_MAP)
    parser.add_argument("--skip-seconds", type=float, default=0.0,
                        help="chỉ bản ghi C1: bỏ S giây đầu (mô-tơ khởi động)")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--mirror", action="store_true", help="đảo dấu góc vòng quét (phép thử quy ước trái/phải)")
    parser.add_argument("--resolution", type=float, default=OdometryConfig.resolution_m)
    parser.add_argument("--min-range", type=float, default=OdometryConfig.min_range_m)
    parser.add_argument("--max-range", type=float, default=OdometryConfig.max_range_m)
    parser.add_argument("--min-normal-ratio", type=float, default=OdometryConfig.min_normal_ratio,
                        help="ngưỡng suy biến theo pháp tuyến; 0 = tắt phép kiểm và khóa trục (chỉ để so sánh)")
    parser.add_argument("--lock-sigma", type=float, default=OdometryConfig.lock_sigma_m,
                        help="σ (m) của tiên nghiệm kéo thành phần dọc hướng suy biến về dự đoán")
    parser.add_argument("--workers", type=int, default=1, help="số tiến trình chạy song song (mỗi bản ghi một việc)")
    parser.add_argument("--no-png", action="store_true")
    args = parser.parse_args(argv)
    drow_inputs = expand_drow_inputs(args.drow)
    if not args.recording and not drow_inputs:
        parser.error("cần ít nhất một --recording hoặc --drow (thư mục --drow không có .csv kèm .odom2)")
    if args.skip_seconds < 0 or args.start < 0 or (args.limit is not None and args.limit < 1) or args.workers < 1:
        parser.error("--skip-seconds, --start phải ≥ 0; --limit, --workers phải ≥ 1")
    modes = MODES if args.mode == "both" else (args.mode,)
    configs = {}
    for mode in modes:
        try:
            configs[mode] = OdometryConfig(mode=mode, resolution_m=args.resolution, min_range_m=args.min_range,
                                           max_range_m=args.max_range, min_normal_ratio=args.min_normal_ratio,
                                           lock_sigma_m=args.lock_sigma)
        except ValueError as exc:
            parser.error(str(exc))
    inputs = [("c1", path) for path in args.recording] + [("drow", path) for path in drow_inputs]
    try:
        names = output_names(inputs)
    except ValueError as exc:
        parser.error(str(exc))
    jobs = []
    for mode in modes:                                     # thứ tự việc: theo chế độ, C1 trước rồi DROW
        for (kind, path), name in zip(inputs, names):
            options = dict(start=args.start, limit=args.limit, mirror=args.mirror, png=not args.no_png, name=name)
            if kind == "c1":
                options["skip_seconds"] = args.skip_seconds
            jobs.append((kind, path, configs[mode], args.out, options))
    t0 = time.perf_counter()
    if args.workers == 1 or len(jobs) == 1:
        results = [_run_job(job) for job in jobs]
    else:
        from concurrent.futures import ProcessPoolExecutor

        from autopark.lidar import scan_odometry as this      # tham chiếu theo tên mô-đun, không theo __main__

        with ProcessPoolExecutor(max_workers=args.workers, initializer=this._worker_init) as pool:
            results = list(pool.map(this._run_job, jobs))
    report = {"created_utc": utc_now(), "git_commit": git_commit(),
              "method": "scan matching odometry: constant-velocity prediction; match only points within "
                        "max_range - match_margin whose angular neighbour is within max_point_spacing; "
                        "branch-and-bound correlative search + Gauss-Newton with a prior toward the prediction "
                        "(localize.py machinery); degeneracy from the spread of scan surface normals, then a soft "
                        "prior pulls the degenerate translation toward the prediction (lock_sigma_m); velocity "
                        "from the last accepted scan spread over the scans since; incremental occupancy map with "
                        "keyframes "
                        "(scan_to_map) or previous scan (scan_to_scan); no loop closure, no wheel/IMU input; "
                        "thresholds provisional (CHƯA CHỐT)",
              "workers": args.workers, "wall_time_s": time.perf_counter() - t0,
              "configs": {mode: asdict(config) for mode, config in configs.items()},
              "results": results}
    atomic_write_json(args.out / "odometry.json", _clean(report))
    for item in results:
        line = {"input": item["input"], "files": item["files"], "mode": item["mode"],
                **{key: item["summary"][key] for key in ("scans", "ok", "ambiguous", "failed")}}
        if item.get("static_drift"):
            line["per_minute_end_translation_m"] = item["static_drift"].get("per_minute_end_translation_m")
            line["per_minute_end_rotation_deg"] = item["static_drift"].get("per_minute_end_rotation_deg")
        if item.get("comparison"):
            line["end_translation_m"] = item["comparison"]["all_steps"]["end"]["translation_m"]
            line["path_ref_m"] = item["comparison"]["all_steps"]["path_ref_m"]
        print(json.dumps(_clean(line), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
