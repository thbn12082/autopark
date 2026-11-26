"""Định vị lại một vòng quét LiDAR trên bản đồ lưới tĩnh đã lưu (kế hoạch v3.1 mục 5 "Khi nhận LiDAR", bước 6).

    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.lidar.localize --map runs/lidar_bench/20260922/map_p07 --recording runs/lidar_bench/20260922/live_headless.npz --out <thư mục>

Tùy chọn thêm vào cuối lệnh: [--initial X Y THETA_DEG] [--window DX DY DTHETA_DEG | --global] [--track]
[--skip-seconds S]. Lệnh viết trên một dòng để dán được vào cmd.exe lẫn PowerShell; thay `<...>` bằng thư mục thật
(sửa 24/09/2026: bản trước xuống dòng bằng `\\` của bash và gọi `python` trần).

KHÔNG phải SLAM, KHÔNG phải odometry: bản đồ cố định (`costmap.json` do `lidar/occupancy.py` ghi), mỗi vòng quét
được đặt lên bản đồ độc lập quanh tư thế ban đầu (hoặc quanh tư thế OK của vòng trước với `--track`). Ba kết quả
"đọc scan được" (driver, `recording.py`), "tạo map được" (`occupancy.py`) và "định vị lại được" (module này) tách
riêng như kế hoạch yêu cầu. Tư thế trả về là tư thế tâm quay LiDAR (x, y, θ) trong hệ của bản đồ; với bản đồ từ
`occupancy.py` ở chế độ cảm biến cố định thì hệ bản đồ là hệ cảm biến lúc ghi bản đồ.

Cách làm:
1. Trường khả năng: khoảng cách Euclid từ tâm mỗi ô tới tâm ô OCCUPIED gần nhất (distance transform), giá trị
   exp(-d²/2σ²). Ô FREE cách vật cản quá `match_dist_m` nhận `-free_penalty` (bản đồ đã nhìn xuyên qua ô đó nên
   một điểm chạm ở đó là bằng chứng ngược). Ô UNKNOWN và vùng ngoài lưới không cộng, không trừ.
2. Khớp tương quan (correlative scan matching) trên lưới rời rạc (x, y, θ) trong cửa sổ tìm: bước tịnh tiến = độ
   phân giải bản đồ, bước góc sao cho điểm xa nhất dịch không quá một ô. Nhánh-cận nhiều mức kiểu Cartographer:
   mức thô dùng trường đã lấy max theo khối 2^k × 2^k, nên điểm của một khối là cận trên đúng cho mọi tư thế con
   và cắt nhánh không làm mất nghiệm. Mọi tư thế rời rạc có điểm ≥ `keep_ratio` × điểm tốt nhất đều được liệt kê
   đủ, để tìm đỉnh thứ hai.
3. Tinh chỉnh cục bộ Gauss-Newton (giảm chấn Levenberg-Marquardt, trọng số Cauchy) trên trường khoảng cách nội
   suy song tuyến, cho tư thế dưới một ô.
4. Đánh giá độ tin: số tia khớp (≤ `match_dist_m` tới ô OCCUPIED), tỉ lệ tia mâu thuẫn (rơi vào ô FREE), tỉ số
   đỉnh thứ hai / đỉnh nhất (đỉnh cách xa hơn `peak_sep_*`), độ lệch chuẩn từ Hessian s²·(JᵀWJ)⁻¹ và nghiệm có nằm
   ở mép cửa sổ không. Kết quả OK / AMBIGUOUS / FAILED kèm lý do: khớp xấu phải ra FAILED hoặc AMBIGUOUS, không
   được ra một tư thế sai mà tự tin.

Giới hạn (24/09/2026): bản đồ chỉ giữ ô chứ không giữ điểm, nên mỗi bức tường có thể lệch tới ±½ ô so với vị trí
thật; độ lệch chuẩn Hessian chỉ phản ánh nhiễu khớp, không phản ánh sai số bản đồ, nên thường lạc quan và chỉ dùng
để phát hiện hướng suy biến (hành lang). Mọi ngưỡng chấp nhận là giá trị tạm, CHƯA CHỐT: chưa có tham chiếu độc lập
(thước dây, các lần đặt hộp) để chốt. Xem docs/DU_LIEU_VA_GIAY_PHEP.md.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, dataclass, field, replace
import json
import math
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from autopark.domain.sensors import Costmap, LidarScan
from autopark.domain.types import Pose
from autopark.perception.costmap import FREE, OCCUPIED, GridSpec, render
from autopark.perception.paths import atomic_write_json, utc_now
from autopark.power_throttling import apply_ecoqos_policy, ecoqos_state

OK, AMBIGUOUS, FAILED = "OK", "AMBIGUOUS", "FAILED"
_OUTSIDE_M = 1e3          # khoảng cách gán cho điểm ngoài lưới (không khớp, không mâu thuẫn)
# Màu tư thế trên overlay.png (BGR), sửa 24/09/2026: phải khác hẳn màu ô của costmap.render() (xám / xanh lá / đỏ)
# và chấm gốc bản đồ. Bản trước dùng xanh lơ cho OK (gần trùng chấm gốc) và đỏ cho FAILED (trùng ô OCCUPIED).
POSE_COLORS = {OK: (255, 60, 0), AMBIGUOUS: (0, 140, 255), FAILED: (0, 0, 0)}   # xanh dương / cam / đen
ORIGIN_COLOR = (255, 255, 0)   # chấm xanh lơ costmap.render() vẽ ở gốc (0, 0) bản đồ, không phải một tư thế
_CAPTION_BAND = (40, 40, 40)   # nền dải chữ: không trùng màu tư thế nào (để đếm điểm ảnh tư thế trong test)


def wrap(angle):
    """Về [-pi, pi). Dùng được cho số thực và mảng numpy."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _check_window(window) -> tuple[float, float, float]:
    """Cửa sổ tìm (wx m, wy m, wθ rad): đúng 3 số hữu hạn, không âm. wθ = 0 là chỉ một hướng, wθ ≥ π là cả vòng.
    Thêm 24/09/2026: trước đó wx/wy âm làm phép tìm hỏng giữa chừng với lỗi numpy khó hiểu, còn wθ âm lặng lẽ tắt
    phép tìm góc."""
    try:
        values = tuple(float(v) for v in window)
    except (TypeError, ValueError):
        values = ()
    if len(values) != 3 or not all(math.isfinite(v) and v >= 0 for v in values):
        raise ValueError(f"cửa sổ tìm (window) phải gồm 3 số hữu hạn và không âm (nhận {window!r})")
    return values


@dataclass(frozen=True)
class LocalizeConfig:
    """Tham số định vị. Các ngưỡng chấp nhận (nhóm cuối) là giá trị tạm, CHƯA CHỐT (24/09/2026)."""

    # trường khả năng
    sigma_m: float = 0.05
    free_penalty: float = 0.5
    match_dist_m: float = 0.10
    # tia dùng được: bỏ phản hồi rất gần (dây, thân gá, thân xe) và rất xa (ngoài tầm tin cậy)
    min_range_m: float = 0.25
    max_range_m: float = 8.0
    # cửa sổ tìm quanh tư thế ban đầu
    window_x_m: float = 0.5
    window_y_m: float = 0.5
    window_theta_deg: float = 30.0
    angle_step_deg: float | None = None      # None: điểm xa nhất dịch ≤ một ô
    levels: int = 4                          # khối 1, 2, 4, 8 ô
    keep_ratio: float = 0.8
    peak_sep_m: float = 0.15
    peak_sep_deg: float = 5.0
    max_candidates: int = 300_000
    # tinh chỉnh cục bộ
    refine_iterations: int = 30
    refine_trunc_m: float = 0.15
    # kiểm tia xuyên tường bản đồ (chỉ ở bước đánh giá, không ở bước tìm)
    through_margin_m: float = 0.15
    # ngưỡng chấp nhận (CHƯA CHỐT)
    min_valid_beams: int = 50
    min_matched: int = 50
    min_matched_fraction: float = 0.6
    max_conflict_fraction: float = 0.25
    ambiguous_ratio: float = 0.9
    max_std_xy_m: float = 0.05
    max_std_theta_deg: float = 2.0

    def __post_init__(self):
        if self.sigma_m <= 0 or self.match_dist_m <= 0 or self.free_penalty < 0:
            raise ValueError("sigma_m, match_dist_m phải > 0 và free_penalty ≥ 0")
        if not 0 <= self.min_range_m < self.max_range_m:
            raise ValueError("cần 0 ≤ min_range_m < max_range_m")
        if min(self.window_x_m, self.window_y_m, self.window_theta_deg) < 0:
            raise ValueError("cửa sổ tìm không được âm")
        if not 1 <= self.levels <= 8 or not 0 < self.keep_ratio <= 1:
            raise ValueError("levels trong 1..8, keep_ratio trong (0, 1]")


@dataclass
class LocalizationResult:
    status: str
    reasons: tuple[str, ...]
    x: float
    y: float
    theta: float
    fit: float                   # trung bình exp(-d²/2σ²) trên mọi tia hợp lệ, ngoài lưới tính 0
    valid_beams: int
    in_grid: int                 # tia hợp lệ có điểm chạm nằm trong lưới bản đồ
    matched: int                 # điểm chạm cách ô OCCUPIED ≤ match_dist_m
    conflicts: int               # điểm chạm rơi vào ô FREE, hoặc tia xuyên ô OCCUPIED của bản đồ
    matched_fraction: float      # matched / valid_beams (tia ra ngoài bản đồ cũng tính ở mẫu số)
    conflict_fraction: float     # conflicts / (matched + conflicts); 0 khi không tia nào kiểm được (xem no_overlap)
    second_ratio: float | None   # None: không có đỉnh tách biệt ≥ keep_ratio × đỉnh nhất, hoặc không xét (FAILED)
    std_x_m: float
    std_y_m: float
    std_theta_deg: float
    search: dict = field(default_factory=dict)
    time_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == OK

    @property
    def pose(self) -> Pose:
        return Pose(self.x, self.y, self.theta)

    def to_dict(self) -> dict:
        def clean(value):
            if isinstance(value, float) and not math.isfinite(value):
                return None
            return value

        out = {key: clean(value) for key, value in asdict(self).items() if key not in ("search", "theta")}
        out["reasons"] = list(self.reasons)
        out["theta_deg"] = math.degrees(self.theta)
        out["search"] = {key: clean(value) for key, value in self.search.items()}
        return out


class LocalizationMap:
    """Bản đồ lưới tĩnh + trường khoảng cách + trường khả năng + tháp max theo khối cho nhánh-cận."""

    def __init__(self, states: np.ndarray, grid: GridSpec, config: LocalizeConfig | None = None, *, source: str = ""):
        self.config = config or LocalizeConfig()
        states = np.asarray(states, np.int8)
        if states.shape != grid.shape:
            raise ValueError(f"lưới trạng thái {states.shape} không khớp GridSpec {grid.shape}")
        occupied = states == OCCUPIED
        if not occupied.any():
            raise ValueError("bản đồ không có ô OCCUPIED nào: không có gì để khớp")
        self.states, self.grid, self.source = states, grid, source
        self.occupied = occupied
        self.res = grid.resolution
        mask = np.where(occupied, 0, 255).astype(np.uint8)
        self.distance = cv2.distanceTransform(mask, cv2.DIST_L2, cv2.DIST_MASK_PRECISE).astype(np.float64) * self.res
        cfg = self.config
        likelihood = np.exp(-0.5 * (self.distance / cfg.sigma_m) ** 2)
        likelihood[(states == FREE) & (self.distance > cfg.match_dist_m)] = -cfg.free_penalty
        self.likelihood = likelihood.astype(np.float32)
        self.pad = 2 ** (cfg.levels - 1)
        self.pyramid = self._pyramid()

    @classmethod
    def from_costmap(cls, costmap: Costmap, config: LocalizeConfig | None = None, *, source: str = "") -> "LocalizationMap":
        if not costmap.stamp.valid:
            raise ValueError("costmap bị đánh dấu không hợp lệ (stamp.valid = False): không định vị trên nó")
        if abs(costmap.origin.yaw) > 1e-9:
            raise ValueError("chỉ hỗ trợ lưới thẳng trục (origin yaw = 0)")
        states = np.asarray(costmap.cells, np.int8)
        rows, cols = states.shape
        res = costmap.resolution_m
        grid = GridSpec(costmap.origin.x, costmap.origin.x + cols * res, costmap.origin.y, costmap.origin.y + rows * res, res)
        return cls(states, grid, config, source=source)

    def _pyramid(self) -> list[np.ndarray]:
        """Mức L: F_L[i, j] = max của trường gốc trên khối [i, i+2^L) × [j, j+2^L) (chỉ số đã đệm `pad` ô 0)."""
        p = self.pad
        rows, cols = self.states.shape
        base = np.zeros((rows + 2 * p, cols + 2 * p), np.float32)
        base[p:p + rows, p:p + cols] = self.likelihood
        levels = [base]
        for level in range(1, self.config.levels):
            h = 2 ** (level - 1)
            prev = levels[-1]
            cur = prev.copy()
            shifted = np.zeros_like(prev)
            shifted[:-h, :] = prev[h:, :]
            np.maximum(cur, shifted, out=cur)
            shifted = np.zeros_like(cur)
            shifted[:, :-h] = cur[:, h:]
            np.maximum(cur, shifted, out=cur)
            levels.append(cur)
        return levels

    # --- tra cứu -------------------------------------------------------------------------------------------------

    def _lookup(self, level: int, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
        table = self.pyramid[level]
        r = np.clip(rows + self.pad, 0, table.shape[0] - 1)
        c = np.clip(cols + self.pad, 0, table.shape[1] - 1)
        return table[r, c]          # ô kẹp về biên đệm luôn bằng 0 (ngoài bản đồ)

    def distance_at(self, x: np.ndarray, y: np.ndarray):
        """Khoảng cách tới ô OCCUPIED gần nhất (nội suy song tuyến giữa các tâm ô) và gradient; ngoài lưới -> 1e3 m."""
        rows, cols = self.states.shape
        u = (x - self.grid.x_min) / self.res - 0.5
        v = (y - self.grid.y_min) / self.res - 0.5
        c0, r0 = np.floor(u), np.floor(v)
        inside = (c0 >= 0) & (c0 < cols - 1) & (r0 >= 0) & (r0 < rows - 1)
        fu, fv = u - c0, v - r0
        ci = np.clip(c0, 0, cols - 2).astype(np.int64)
        ri = np.clip(r0, 0, rows - 2).astype(np.int64)
        dist = self.distance
        d00, d01, d10, d11 = dist[ri, ci], dist[ri, ci + 1], dist[ri + 1, ci], dist[ri + 1, ci + 1]
        d = (1 - fv) * ((1 - fu) * d00 + fu * d01) + fv * ((1 - fu) * d10 + fu * d11)
        gx = ((1 - fv) * (d01 - d00) + fv * (d11 - d10)) / self.res
        gy = ((1 - fu) * (d10 - d00) + fu * (d11 - d01)) / self.res
        d = np.where(inside, d, _OUTSIDE_M)
        return d, np.where(inside, gx, 0.0), np.where(inside, gy, 0.0), inside

    def _core_distance(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Như `distance_at` nhưng hai ô OCCUPIED chéo nhau (chỉ chạm góc) được nối bằng đoạn giữa hai tâm, để tường
        chéo (bậc thang 8-liên thông) không có khe: nội suy song tuyến cho 0,5 ô ở góc chung của hai ô đó."""
        d, _, _, inside = self.distance_at(x, y)
        rows, cols = self.states.shape
        u = (x - self.grid.x_min) / self.res - 0.5
        v = (y - self.grid.y_min) / self.res - 0.5
        fu, fv = u - np.floor(u), v - np.floor(v)
        ci = np.clip(np.floor(u), 0, cols - 2).astype(np.int64)
        ri = np.clip(np.floor(v), 0, rows - 2).astype(np.int64)
        occ = self.occupied
        main = inside & occ[ri, ci] & occ[ri + 1, ci + 1]
        anti = inside & occ[ri, ci + 1] & occ[ri + 1, ci]
        d = np.where(main, np.minimum(d, np.abs(fu - fv) * self.res / math.sqrt(2)), d)
        return np.where(anti, np.minimum(d, np.abs(fu + fv - 1) * self.res / math.sqrt(2)), d)

    def cell_states(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        rows, cols = self.states.shape
        r = np.floor((y - self.grid.y_min) / self.res).astype(np.int64)
        c = np.floor((x - self.grid.x_min) / self.res).astype(np.int64)
        inside = (r >= 0) & (r < rows) & (c >= 0) & (c < cols)
        out = np.full(len(r), -2, np.int8)
        out[inside] = self.states[r[inside], c[inside]]
        return out, inside

    # --- khớp tương quan nhánh-cận ------------------------------------------------------------------------------

    def search(self, points: np.ndarray, center: tuple[float, float, float], window: tuple[float, float, float], *,
               global_xy: bool = False, keep_ratio: float | None = None, lower_bound: float | None = None) -> dict:
        """Tư thế rời rạc tốt nhất trong cửa sổ (±wx, ±wy, ±wθ) quanh `center` và đỉnh thứ hai tách biệt.

        Kết quả chính xác trên lưới rời rạc (nhánh-cận không cắt mất nghiệm), trừ khi `truncated` = True. Mọi tư
        thế rời rạc có điểm ≥ `keep_ratio` × tốt nhất được liệt kê (mặc định theo cấu hình; 1.0 = chỉ tìm đỉnh
        nhất, cắt nhánh mạnh nhất). `lower_bound` = điểm thật của một tư thế trong cửa sổ đã biết trước."""
        cfg = self.config
        keep_ratio = cfg.keep_ratio if keep_ratio is None else keep_ratio
        res = self.res
        x0, y0, th0 = (float(v) for v in center)
        wx, wy, wth = _check_window(window)
        radius = max(float(np.max(np.hypot(points[:, 0], points[:, 1]))), res)
        if cfg.angle_step_deg:
            step = math.radians(cfg.angle_step_deg)
        else:
            step = math.acos(max(-1.0, 1.0 - res * res / (2 * radius * radius)))
        step = min(max(step, math.radians(0.05)), math.radians(2.0))
        full_circle = wth >= math.pi - 1e-9
        if full_circle:
            n_half = int(math.ceil(math.pi / step))
            step = math.pi / n_half
            thetas = th0 + np.arange(-n_half, n_half) * step
        else:
            n_half = int(math.ceil(wth / step - 1e-9)) if wth > 0 else 0
            thetas = th0 + np.arange(-n_half, n_half + 1) * step
        wxc = int(math.ceil(wx / res - 1e-9))
        wyc = int(math.ceil(wy / res - 1e-9))
        cos, sin = np.cos(thetas)[:, None], np.sin(thetas)[:, None]
        px, py = points[:, 0][None, :], points[:, 1][None, :]
        cb = np.floor((cos * px - sin * py + x0 - self.grid.x_min) / res).astype(np.int32)
        rb = np.floor((sin * px + cos * py + y0 - self.grid.y_min) / res).astype(np.int32)
        n = points.shape[0]
        chunk = max(1, 2_000_000 // n)
        evaluated = 0

        def score(level: int, k: np.ndarray, i: np.ndarray, j: np.ndarray) -> np.ndarray:
            nonlocal evaluated
            out = np.empty(len(k), np.float64)
            for a in range(0, len(k), chunk):
                b = a + chunk
                out[a:b] = self._lookup(level, rb[k[a:b]] + j[a:b, None], cb[k[a:b]] + i[a:b, None]).sum(axis=1)
            evaluated += len(k)
            return out

        def children(level: int, k, i, j):
            h = 2 ** (level - 1)
            k4 = np.repeat(k, 4)
            i4 = (i[:, None] + np.array([0, h, 0, h])[None, :]).ravel()
            j4 = (j[:, None] + np.array([0, 0, h, h])[None, :]).ravel()
            keep = (i4 <= wxc) & (j4 <= wyc)
            return k4[keep], i4[keep], j4[keep]

        top = self.config.levels - 1
        block = 2 ** top
        ii, jj = np.arange(-wxc, wxc + 1, block), np.arange(-wyc, wyc + 1, block)
        k = np.repeat(np.arange(len(thetas)), len(ii) * len(jj))
        i = np.tile(np.repeat(ii, len(jj)), len(thetas))
        j = np.tile(jj, len(thetas) * len(ii))
        ub = score(top, k, i, j)

        def descend(level: int, k, i, j, ub, starts: int = 32) -> float:
            """Đi tham lam từ vài ứng viên tốt nhất xuống lá; điểm lá là điểm thật của một tư thế (cận dưới)."""
            if level == 0:
                return float(ub.max())
            pick = np.argsort(-ub)[:starts]
            gk, gi, gj = k[pick], i[pick], j[pick]
            for lev in range(level, 0, -1):
                h = 2 ** (lev - 1)
                ck = np.repeat(gk, 4)
                ci = (gi[:, None] + np.array([0, h, 0, h])[None, :]).ravel()
                cj = (gj[:, None] + np.array([0, 0, h, h])[None, :]).ravel()
                inside = (ci <= wxc) & (cj <= wyc)          # con (0, 0) luôn nằm trong cửa sổ
                s = np.full(len(ck), -np.inf)
                s[inside] = score(lev - 1, ck[inside], ci[inside], cj[inside])
                pick = np.arange(len(gk)) * 4 + s.reshape(-1, 4).argmax(axis=1)
                gk, gi, gj, gs = ck[pick], ci[pick], cj[pick], s[pick]
            return float(gs.max())

        def threshold(lb: float) -> float:
            return keep_ratio * lb if lb > 0 else lb

        best_lb = descend(top, k, i, j, ub)
        if lower_bound is not None:
            best_lb = max(best_lb, float(lower_bound))
        truncated = False
        for level in range(top, 0, -1):
            keep = ub >= threshold(best_lb) - 1e-9
            k, i, j, ub = k[keep], i[keep], j[keep], ub[keep]
            if len(ub) > cfg.max_candidates:
                order = np.argpartition(-ub, cfg.max_candidates)[:cfg.max_candidates]
                k, i, j, ub = k[order], i[order], j[order], ub[order]
                truncated = True
            k, i, j = children(level, k, i, j)
            ub = score(level - 1, k, i, j)
            best_lb = max(best_lb, descend(level - 1, k, i, j, ub))
        keep = ub >= threshold(best_lb) - 1e-9
        k, i, j, s = k[keep], i[keep], j[keep], ub[keep]
        b = int(np.argmax(s))
        kb, ib, jb, best = int(k[b]), int(i[b]), int(j[b]), float(s[b])
        dxy = np.hypot((i - ib) * res, (j - jb) * res)
        dth = np.abs(wrap(thetas[k] - thetas[kb]))
        distinct = (dxy > cfg.peak_sep_m) | (dth > math.radians(cfg.peak_sep_deg))
        second = float(s[distinct].max()) if distinct.any() else None
        at_edge = (not full_circle and len(thetas) > 1 and kb in (0, len(thetas) - 1)) or \
                  (not global_xy and ((wxc > 0 and abs(ib) >= wxc) or (wyc > 0 and abs(jb) >= wyc)))
        return {"x": x0 + ib * res, "y": y0 + jb * res, "theta": float(thetas[kb]), "score": best,
                "score_per_point": best / n, "second": second,
                "second_ratio": (second / best) if (second is not None and best > 0) else None,
                "leaves": int(len(s)), "evaluated": int(evaluated), "angles": int(len(thetas)),
                "angle_step_deg": math.degrees(step), "points": int(n), "truncated": truncated, "at_edge": bool(at_edge)}

    def brute_force(self, points: np.ndarray, center, window, *, global_xy: bool = False) -> dict:
        """Cùng phép tìm nhưng duyệt hết mọi tư thế rời rạc ở mức 0, không cắt nhánh (để kiểm nhánh-cận)."""
        flat = LocalizationMap.__new__(LocalizationMap)
        flat.__dict__.update(self.__dict__)
        flat.config = replace(self.config, levels=1, max_candidates=10 ** 12)
        return flat.search(points, center, window, global_xy=global_xy)

    # --- tinh chỉnh + đánh giá ---------------------------------------------------------------------------------

    def _cost(self, points: np.ndarray, pose) -> float:
        cfg = self.config
        c, s = math.cos(pose[2]), math.sin(pose[2])
        d, _, _, _ = self.distance_at(c * points[:, 0] - s * points[:, 1] + pose[0], s * points[:, 0] + c * points[:, 1] + pose[1])
        r = np.minimum(d, cfg.refine_trunc_m) / cfg.sigma_m
        return float(np.log1p(r * r).sum())

    def refine(self, points: np.ndarray, pose) -> tuple[np.ndarray, np.ndarray]:
        """Gauss-Newton/LM trên khoảng cách nội suy. Trả (tư thế, hiệp phương sai 3×3; inf khi suy biến)."""
        cfg = self.config
        pose = np.array(pose, np.float64)
        px, py = points[:, 0], points[:, 1]
        lam = 1e-3
        cost = self._cost(points, pose)

        def linearize(p):
            c, s = math.cos(p[2]), math.sin(p[2])
            d, gx, gy, _ = self.distance_at(c * px - s * py + p[0], s * px + c * py + p[1])
            use = d < cfg.refine_trunc_m
            r = d[use]
            w = 1.0 / (1.0 + (r / cfg.sigma_m) ** 2)
            jt = gx[use] * (-s * px[use] - c * py[use]) + gy[use] * (c * px[use] - s * py[use])
            jac = np.column_stack([gx[use], gy[use], jt])
            return jac, r, w

        for _ in range(cfg.refine_iterations):
            jac, r, w = linearize(pose)
            if len(r) < 3:
                break
            h = jac.T @ (jac * w[:, None])
            g = jac.T @ (w * r)
            accepted = False
            for _ in range(8):
                try:
                    step = -np.linalg.solve(h + lam * np.diag(np.diag(h)) + 1e-12 * np.eye(3), g)
                except np.linalg.LinAlgError:
                    break
                candidate = pose + step
                new_cost = self._cost(points, candidate)
                if new_cost < cost:
                    pose, cost, lam, accepted = candidate, new_cost, max(lam / 3, 1e-7), True
                    break
                lam *= 5
            if not accepted or (abs(step[0]) < 1e-5 and abs(step[1]) < 1e-5 and abs(step[2]) < 1e-5):
                break
        pose[2] = wrap(pose[2])
        jac, r, w = linearize(pose)
        cov = np.full((3, 3), np.inf)
        if len(r) > 3:
            h = jac.T @ (jac * w[:, None])
            s2 = float((w * r * r).sum() / max(1.0, w.sum() - 3))
            eig = np.linalg.eigvalsh(h)
            if eig.min() > 1e-9 * max(1.0, eig.max()):
                cov = s2 * np.linalg.inv(h)
        return pose, cov

    def through_walls(self, points: np.ndarray, pose) -> np.ndarray:
        """Tia nào đi xuyên lõi một ô OCCUPIED của bản đồ trước điểm chạm hơn `through_margin_m` (bản đồ có vật ở
        đó mà tia vẫn đi qua). Lõi = khoảng cách nội suy < ¼ ô, để tia sượt mép tường không bị tính; hai ô OCCUPIED
        chéo nhau được nối tâm-tâm (`_core_distance`) để tường chéo không có khe. Lấy mẫu mỗi ¼ ô vì dải lõi chỉ
        rộng ≈ 0,35 ô gần tâm ô (sửa 24/09/2026: trước đó ½ ô và không nối ô chéo, tia qua tường 45° chỉ bị bắt
        15–52 %). Bắt đầu từ `min_range_m` vì bản đồ có thể có ô OCCUPIED sát cảm biến (dây, gá) lúc ghi."""
        cfg = self.config
        r = np.hypot(points[:, 0], points[:, 1])
        step = self.res / 4
        length = r - cfg.through_margin_m - cfg.min_range_m
        counts = np.maximum(np.floor(length / step).astype(np.int64) + 1, 0)
        out = np.zeros(len(points), bool)
        total = int(counts.sum())
        if total == 0:
            return out
        beam = np.repeat(np.arange(len(points)), counts)
        k = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
        dist = cfg.min_range_m + k * step
        heading = np.arctan2(points[:, 1], points[:, 0])[beam] + pose[2]
        d = self._core_distance(pose[0] + dist * np.cos(heading), pose[1] + dist * np.sin(heading))
        out[np.unique(beam[d < 0.25 * self.res])] = True
        return out

    def evaluate(self, points: np.ndarray, pose) -> dict:
        """Phân loại từng tia hợp lệ ở tư thế `pose`: khớp / chạm vào ô FREE / xuyên tường bản đồ / không kiểm được."""
        cfg = self.config
        c, s = math.cos(pose[2]), math.sin(pose[2])
        x = c * points[:, 0] - s * points[:, 1] + pose[0]
        y = s * points[:, 0] + c * points[:, 1] + pose[1]
        d, _, _, _ = self.distance_at(x, y)
        states, in_grid = self.cell_states(x, y)
        matched = in_grid & (d <= cfg.match_dist_m)
        short = in_grid & ~matched & (states == FREE)
        through = ~matched & ~short & self.through_walls(points, pose)
        conflicts = short | through
        fit = np.where(d < _OUTSIDE_M, np.exp(-0.5 * (np.minimum(d, 10.0) / cfg.sigma_m) ** 2), 0.0)
        return {"fit": float(fit.mean()) if len(fit) else 0.0, "in_grid": int(in_grid.sum()),
                "matched": int(matched.sum()), "short": int(short.sum()), "through": int(through.sum()),
                "conflicts": int(conflicts.sum()), "matched_mask": matched, "conflict_mask": conflicts}


def load_map(path, config: LocalizeConfig | None = None) -> LocalizationMap:
    """Nạp `costmap.json` do `lidar/occupancy.py` ghi (hoặc thư mục chứa nó, hoặc một costmap dict trần)."""
    from autopark.domain.sensors import SourceStamp

    path = Path(path)
    if path.is_dir():
        path = path / "costmap.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("costmap", data)
    stamp = raw.get("stamp", {})
    origin = raw["origin"]
    costmap = Costmap(SourceStamp(stamp.get("source_id", "map"), float(stamp.get("t", 0.0)), bool(stamp.get("valid", True)),
                                  stamp.get("frame_id", "map")),
                      float(raw["resolution_m"]), Pose(float(origin["x"]), float(origin["y"]), math.radians(float(origin.get("yaw_deg", 0.0)))),
                      tuple(tuple(int(v) for v in row) for row in raw["cells"]))
    return LocalizationMap.from_costmap(costmap, config, source=str(path))


def scan_points(angles, ranges, config: LocalizeConfig) -> np.ndarray:
    """Điểm (x, y) trong hệ cảm biến của các tia có phản hồi trong [min_range, max_range]."""
    angles = np.asarray(angles, np.float64)
    ranges = np.asarray(ranges, np.float64)
    ok = np.isfinite(ranges) & (ranges >= config.min_range_m) & (ranges <= config.max_range_m) & (ranges > 0)
    return np.column_stack([ranges[ok] * np.cos(angles[ok]), ranges[ok] * np.sin(angles[ok])])


def decimate(points: np.ndarray, cell: float) -> np.ndarray:
    """Giữ một điểm mỗi ô `cell` (điểm gần cảm biến dày hơn nhiều; không để chúng áp đảo tổng điểm)."""
    if len(points) == 0:
        return points
    keys = np.floor(points / cell).astype(np.int64)
    _, first = np.unique(keys, axis=0, return_index=True)
    return points[np.sort(first)]


def localize(lmap: LocalizationMap, angles, ranges, initial=(0.0, 0.0, 0.0), *, window=None,
             global_search: bool = False) -> LocalizationResult:
    """Định vị một vòng quét. `initial` = (x, y, θ rad) tâm cửa sổ; `window` = (wx m, wy m, wθ rad) hoặc mặc định
    theo cấu hình (3 số hữu hạn, không âm; sai thì ValueError); `global_search` = cả bản đồ, mọi hướng (chậm hơn
    nhiều, `window` bị bỏ qua)."""
    t0 = time.perf_counter()
    cfg = lmap.config
    if window is not None and not global_search:
        window = _check_window(window)          # kiểm trước cả khi thiếu tia, để lỗi gọi hàm không bị che
    points = scan_points(angles, ranges, cfg)
    initial = tuple(float(v) for v in initial)
    nan = math.nan

    def failed(reason: str) -> LocalizationResult:
        return LocalizationResult(FAILED, (reason,), initial[0], initial[1], initial[2], 0.0, len(points), 0, 0, 0,
                                  0.0, 0.0, None, nan, nan, nan, {}, (time.perf_counter() - t0) * 1e3)

    if len(points) < max(3, cfg.min_valid_beams):
        return failed("too_few_beams")
    search_points = decimate(points, lmap.res)
    if global_search:
        g = lmap.grid
        center = ((g.x_min + g.x_max) / 2, (g.y_min + g.y_max) / 2, initial[2])
        window = ((g.x_max - g.x_min) / 2 + lmap.res, (g.y_max - g.y_min) / 2 + lmap.res, math.pi)
    else:
        center = initial
        if window is None:
            window = (cfg.window_x_m, cfg.window_y_m, math.radians(cfg.window_theta_deg))
    # Pha 1: chỉ tìm đỉnh nhất (cắt nhánh mạnh nhất). Pha 2 (bên dưới) mới liệt kê các đỉnh gần bằng.
    found = lmap.search(search_points, center, window, global_xy=global_search, keep_ratio=1.0)
    discrete = np.array([found["x"], found["y"], found["theta"]])
    pose, cov = lmap.refine(search_points, discrete)
    # Đỉnh rời rạc có thể lệch cỡ một ô và vài bước góc (tra ô gần nhất, tịnh tiến và quay bù nhau), nên chỉ coi
    # là bất ổn khi tinh chỉnh rời khỏi vùng mà phép tìm đỉnh thứ hai coi là "cùng một đỉnh".
    unstable = (np.hypot(pose[0] - discrete[0], pose[1] - discrete[1]) > cfg.peak_sep_m
                or abs(wrap(pose[2] - discrete[2])) > math.radians(cfg.peak_sep_deg))
    if unstable:
        pose = discrete          # tinh chỉnh chạy sang vùng khác: giữ đỉnh rời rạc, báo không chắc
    evaluation = lmap.evaluate(points, pose)
    matched, conflicts, in_grid = evaluation["matched"], evaluation["conflicts"], evaluation["in_grid"]
    matched_fraction = matched / len(points)
    # Không tia nào kiểm được (khớp + mâu thuẫn = 0): tỉ lệ mâu thuẫn lấy 0 (không phải 1, không phải NaN: NaN thành
    # None trong JSON và làm hỏng định dạng CSV) và báo riêng bằng lý do no_overlap (sửa 24/09/2026: trước đó lấy
    # 1,0 nên báo "conflicts_with_map" khi 0 mâu thuẫn).
    conflict_fraction = conflicts / (matched + conflicts) if matched + conflicts else 0.0
    with np.errstate(invalid="ignore"):
        std = np.sqrt(np.diag(cov)) if np.all(np.isfinite(cov)) else np.full(3, np.inf)
        std_xy = math.sqrt(max(np.linalg.eigvalsh(cov[:2, :2]).max(), 0.0)) if np.all(np.isfinite(cov)) else math.inf
    failures = []
    if matched + conflicts == 0:
        failures.append("no_overlap")     # không tia nào kiểm được với bản đồ: --initial sai, nhầm bản đồ, bản đồ trống ở đó
    if matched < cfg.min_matched:
        failures.append("few_matched")
    if matched_fraction < cfg.min_matched_fraction:
        failures.append("low_match_fraction")
    if conflicts and conflict_fraction > cfg.max_conflict_fraction:
        failures.append("conflicts_with_map")
    if found["at_edge"]:
        failures.append("window_edge")
    # Pha 2: tìm đỉnh thứ hai, bắt đầu với cận dưới = điểm đỉnh nhất. Bỏ qua khi tư thế đã hỏng vì không khớp bản
    # đồ (kết quả đằng nào cũng FAILED; cảnh không khớp làm mặt điểm phẳng và phép liệt kê rất chậm).
    peaks_checked = not ({"no_overlap", "few_matched", "low_match_fraction", "conflicts_with_map"} & set(failures))
    second_ratio, truncated, evaluated, leaves = None, found["truncated"], found["evaluated"], None
    if peaks_checked:
        peaks = lmap.search(search_points, center, window, global_xy=global_search, lower_bound=found["score"])
        second_ratio, leaves = peaks["second_ratio"], peaks["leaves"]
        truncated, evaluated = truncated or peaks["truncated"], evaluated + peaks["evaluated"]
    ambiguous = []
    if second_ratio is not None and second_ratio >= cfg.ambiguous_ratio:
        ambiguous.append("second_peak")
    if not (std_xy <= cfg.max_std_xy_m and std[2] <= math.radians(cfg.max_std_theta_deg)):
        ambiguous.append("degenerate")
    if truncated:
        ambiguous.append("search_truncated")
    if unstable:
        ambiguous.append("refine_unstable")
    reasons = failures + ambiguous
    status = FAILED if failures else (AMBIGUOUS if ambiguous else OK)
    search = {key: found[key] for key in ("score_per_point", "angles", "angle_step_deg", "points", "at_edge")}
    search.update({"evaluated": int(evaluated), "truncated": bool(truncated), "second_peak_checked": peaks_checked,
                   "leaves": leaves,"discrete_x": float(discrete[0]), "discrete_y": float(discrete[1]),
                   "discrete_theta_deg": math.degrees(discrete[2]), "global": bool(global_search),
                   "center_x": center[0], "center_y": center[1], "center_theta_deg": math.degrees(center[2]),
                   "window_x_m": float(window[0]), "window_y_m": float(window[1]),
                   "window_theta_deg": math.degrees(window[2]),
                   "conflicts_short": evaluation["short"], "conflicts_through": evaluation["through"]})
    return LocalizationResult(status, tuple(reasons), float(pose[0]), float(pose[1]), float(wrap(pose[2])),
                              evaluation["fit"], int(len(points)), in_grid, matched, conflicts, matched_fraction,
                              conflict_fraction, second_ratio, float(std[0]), float(std[1]),
                              math.degrees(float(std[2])), search, (time.perf_counter() - t0) * 1e3)


def localize_scan(lmap: LocalizationMap, scan: LidarScan, initial=(0.0, 0.0, 0.0), **kwargs) -> LocalizationResult:
    return localize(lmap, scan.angles_rad, np.array(scan.ranges_m, np.float64), initial, **kwargs)


# --- CLI: định vị từng vòng của một bản ghi ------------------------------------------------------------------------

CSV_FIELDS = ("index", "t_s", "status", "reasons", "x_m", "y_m", "theta_deg", "fit", "valid_beams", "in_grid",
              "matched", "matched_fraction", "conflicts", "conflict_fraction", "second_ratio", "std_x_m", "std_y_m",
              "std_theta_deg", "time_ms")


def summarize_track(rows: list[dict]) -> dict:
    status = Counter(row["status"] for row in rows)
    reasons = Counter(reason for row in rows for reason in row["reasons"])
    ok = [row for row in rows if row["status"] == OK]
    times = np.array([row["time_ms"] for row in rows]) if rows else np.zeros(0)
    out = {"scans": len(rows), "ok": status.get(OK, 0), "ambiguous": status.get(AMBIGUOUS, 0),
           "failed": status.get(FAILED, 0), "reasons": dict(reasons),
           "time_ms": {"median": float(np.median(times)), "p95": float(np.percentile(times, 95)),
                       "max": float(times.max())} if len(times) else None}
    if ok:
        xs, ys = np.array([r["x"] for r in ok]), np.array([r["y"] for r in ok])
        th = np.radians(np.array([r["theta_deg"] for r in ok], np.float64))
        # Hướng là đại lượng vòng (sửa 24/09/2026): theta quấn về [-180°, 180°) nên hướng thật ≈ 180° cho giá trị hai
        # dấu, và thống kê tuyến tính trên theta thô ra trung vị ≈ 0° với độ lệch ≈ 160°. Thống kê trên độ lệch đã
        # quấn quanh trung bình vòng; khi các hướng không nằm quanh ±180° thì kết quả như thống kê tuyến tính.
        th_mean = math.atan2(float(np.sin(th).mean()), float(np.cos(th).mean()))
        th_dev = np.degrees(wrap(th - th_mean))
        th_median = math.degrees(wrap(th_mean + math.radians(float(np.median(th_dev)))))
        out["ok_pose_median"] = {"x_m": float(np.median(xs)), "y_m": float(np.median(ys)), "theta_deg": th_median}
        out["ok_pose_spread"] = {"x_std_m": float(xs.std()), "y_std_m": float(ys.std()),
                                 "theta_std_deg": float(th_dev.std()),
                                 "x_range_m": float(np.ptp(xs)), "y_range_m": float(np.ptp(ys)),
                                 "theta_range_deg": float(np.ptp(th_dev))}
        out["ok_fit_median"] = float(np.median([r["fit"] for r in ok]))
        out["ok_matched_fraction_median"] = float(np.median([r["matched_fraction"] for r in ok]))
    all_fit = [row["fit"] for row in rows]
    out["fit_median_all"] = float(np.median(all_fit)) if all_fit else None
    out["matched_fraction_median_all"] = float(np.median([row["matched_fraction"] for row in rows])) if rows else None
    return out


def _write_png(path: Path, image: np.ndarray) -> None:
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"không mã hóa được {path.name}")
    path.write_bytes(data.tobytes())


def _shown_row(rows: list[dict]) -> dict | None:
    """Vòng có điểm được vẽ lên overlay: vòng OK cuối cùng, không có thì vòng cuối."""
    return next((row for row in reversed(rows) if row["status"] == OK), rows[-1] if rows else None)


def overlay_caption(rows: list[dict], title: str = "", points_by_index: dict | None = None) -> list[str]:
    """Các dòng chữ của overlay.png: tiêu đề, điểm vẽ là của vòng nào (số vòng + trạng thái), chú giải màu. Chữ
    Hershey của OpenCV không vẽ được dấu tiếng Việt nên phần chữ thêm vào là ASCII."""
    lines = title.split("\n") if title else []
    shown = _shown_row(rows)
    if shown is None or (points_by_index is not None and shown["index"] not in points_by_index):
        lines.append("points: none")
    else:
        note = "" if shown["status"] == OK else "  (no OK scan: pose NOT accepted)"
        lines.append(f"points: scan #{shown['index']} {shown['status']}{note}")
    lines.append("pose: blue=OK  orange=AMBIGUOUS  black X=FAILED")
    lines.append("cyan disc = map origin (0,0), not a pose")
    return lines


def render_overlay(lmap: LocalizationMap, rows: list[dict], points_by_index: dict[int, np.ndarray], title: str,
                   scale: int | None = None) -> np.ndarray:
    """Bản đồ (x lên trên, y sang trái như costmap; xám UNKNOWN, xanh lá FREE, đỏ OCCUPIED; chấm xanh lơ lớn = gốc
    bản đồ, không phải tư thế). Điểm của vòng OK cuối cùng, không có thì của vòng cuối, đặt theo tư thế của vòng đó
    (vàng = khớp, tím = mâu thuẫn: rơi vào ô FREE hoặc xuyên tường bản đồ, trắng = không kiểm được); dòng chữ ghi số
    vòng và trạng thái. Tư thế mọi vòng: chấm xanh dương viền đen = OK, chấm cam viền đen = AMBIGUOUS, dấu X đen =
    FAILED; vạch = hướng +x cảm biến. Màu đổi ngày 24/09/2026 (xem POSE_COLORS)."""
    grid = lmap.grid
    scale = scale or max(1, int(640 / max(lmap.states.shape)))
    canvas = render(lmap.states, grid, None, None, scale=scale)

    def px(x, y):
        return int((grid.y_max - y) / grid.resolution * scale), int((grid.x_max - x) / grid.resolution * scale)

    shown = _shown_row(rows)
    if shown is not None and shown["index"] in points_by_index:
        pts = points_by_index[shown["index"]]
        th = math.radians(shown["theta_deg"])
        c, s = math.cos(th), math.sin(th)
        x = c * pts[:, 0] - s * pts[:, 1] + shown["x"]
        y = s * pts[:, 0] + c * pts[:, 1] + shown["y"]
        ev = lmap.evaluate(pts, (shown["x"], shown["y"], th))
        for k in range(len(x)):
            color = (0, 230, 255) if ev["matched_mask"][k] else ((255, 0, 255) if ev["conflict_mask"][k] else (235, 235, 235))
            cv2.circle(canvas, px(x[k], y[k]), max(1, scale // 2), color, -1)
    for row in rows:
        cx, cy = px(row["x"], row["y"])
        th = math.radians(row["theta_deg"])
        tip = px(row["x"] + 0.25 * math.cos(th), row["y"] + 0.25 * math.sin(th))
        color = POSE_COLORS[row["status"]]
        cv2.line(canvas, (cx, cy), tip, color, 1)
        if row["status"] == FAILED:
            cv2.drawMarker(canvas, (cx, cy), color, cv2.MARKER_TILTED_CROSS, 9, 2)
        else:
            cv2.circle(canvas, (cx, cy), 4, (0, 0, 0), -1)
            cv2.circle(canvas, (cx, cy), 3, color, -1)
    lines = overlay_caption(rows, title, points_by_index)
    # Chữ trắng trên dải nền tối (không dùng viền chữ đen dày: độ rộng ký tự Hershey tăng theo độ dày, để lại bóng
    # chữ). Thu nhỏ chữ khi bản đồ hẹp để dòng không bị cắt.
    font, size = cv2.FONT_HERSHEY_SIMPLEX, 0.45
    widest = max(cv2.getTextSize(line, font, size, 1)[0][0] for line in lines)
    size = max(0.3, min(size, size * (canvas.shape[1] - 12) / max(widest, 1)))
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1] - 1, 17 * len(lines) + 4), _CAPTION_BAND, -1)
    y0 = 16
    for line in lines:
        cv2.putText(canvas, line, (6, y0), font, size, (255, 255, 255), 1, cv2.LINE_AA)
        y0 += 17
    return canvas


def run(map_path, recording_path, out: Path, config: LocalizeConfig, *, initial=(0.0, 0.0, 0.0), window=None,
        global_search: bool = False, track: bool = False, skip_seconds: float = 0.0, every: int = 1,
        limit: int | None = None) -> dict:
    from .recording import git_commit, read_lidar_any

    if window is not None and not global_search:
        window = _check_window(window)          # trước khi nạp gì và trước khi tạo thư mục kết quả
    lmap = load_map(map_path, config)
    recording = read_lidar_any(recording_path)  # .npz, hay thư mục bản ghi phiên (T3: mọi phần LiDAR, 02/10/2026)
    rows: list[dict] = []
    points_by_index: dict[int, np.ndarray] = {}
    center = tuple(float(v) for v in initial)
    indices = [i for i in range(len(recording)) if recording.t[i] - recording.t[0] >= skip_seconds][::max(1, every)]
    if limit is not None:
        indices = indices[:limit]
    for index in indices:
        angles, ranges, _ = recording.beams(index)
        result = localize(lmap, angles, ranges, center, window=window, global_search=global_search)
        row = {"index": index, "t_s": float(recording.t[index] - recording.t[0]), **result.to_dict()}
        rows.append(row)
        points_by_index[index] = scan_points(angles, ranges, config)
        if track and result.ok:
            center = (result.x, result.y, result.theta)
    out.mkdir(parents=True, exist_ok=True)
    summary = summarize_track(rows)
    with (out / "track.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_FIELDS)
        for row in rows:
            writer.writerow([row["index"], f"{row['t_s']:.3f}", row["status"], "+".join(row["reasons"]),
                             f"{row['x']:.4f}", f"{row['y']:.4f}", f"{row['theta_deg']:.3f}", f"{row['fit']:.4f}",
                             row["valid_beams"], row["in_grid"], row["matched"], f"{row['matched_fraction']:.4f}",
                             row["conflicts"], f"{row['conflict_fraction']:.4f}",
                             "" if row["second_ratio"] is None else f"{row['second_ratio']:.4f}",
                             *("" if row[key] is None else f"{row[key]:.5f}" for key in ("std_x_m", "std_y_m")),
                             "" if row["std_theta_deg"] is None else f"{row['std_theta_deg']:.4f}",
                             f"{row['time_ms']:.1f}"])
    mode = "global" if global_search else ("track" if track else "independent")
    report = {"created_utc": utc_now(), "git_commit": git_commit(), "ecoqos": ecoqos_state(),     # time_ms phụ thuộc nó
              "map": str(map_path), "recording": str(recording_path),
              "recording_meta": {key: recording.meta.get(key) for key in ("source_id", "started_utc", "name", "note", "placement")},
              "mode": mode, "initial": {"x_m": float(initial[0]), "y_m": float(initial[1]),
                                        "theta_deg": math.degrees(float(initial[2]))},
              "window": "whole map, 360°" if global_search else (
                  {"x_m": window[0], "y_m": window[1], "theta_deg": math.degrees(window[2])} if window is not None else
                  {"x_m": config.window_x_m, "y_m": config.window_y_m, "theta_deg": config.window_theta_deg}),
              "skip_seconds": skip_seconds, "every": every, "config": asdict(config),
              "map_info": {"grid": lmap.grid.__dict__, "occupied_cells": int((lmap.states == OCCUPIED).sum()),
                           "free_cells": int((lmap.states == FREE).sum())},
              "method": "likelihood field (distance transform) + branch-and-bound correlative search + LM refinement; "
                        "no SLAM, no odometry; thresholds provisional (CHƯA CHỐT)",
              "summary": summary,
              "track": rows}
    atomic_write_json(out / "localize.json", report)
    title = (f"{Path(recording_path).stem} vs {Path(map_path).name}  mode {mode}\n"
             f"OK {summary['ok']}  AMBIGUOUS {summary['ambiguous']}  FAILED {summary['failed']}  of {summary['scans']}")
    _write_png(out / "overlay.png", render_overlay(lmap, rows, points_by_index, title))
    return report


def main(argv=None) -> int:
    apply_ecoqos_policy("lidar.localize")              # trước mọi việc khác (power_throttling.py)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--map", type=Path, required=True, help="costmap.json của lidar/occupancy.py hoặc thư mục chứa nó")
    parser.add_argument("--recording", type=Path, required=True,
                        help=".npz của autopark.lidar.recording, hay thư mục bản ghi phiên (mọi phần lidar/part_*.npz)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--initial", type=float, nargs=3, metavar=("X", "Y", "THETA_DEG"), default=(0.0, 0.0, 0.0))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--window", type=float, nargs=3, metavar=("DX", "DY", "DTHETA_DEG"), default=None,
                       help="nửa cửa sổ tìm, ≥ 0 (DTHETA_DEG 0 = một hướng, ≥ 180 = cả vòng)")
    group.add_argument("--global", dest="global_search", action="store_true", help="tìm trên cả bản đồ, mọi hướng")
    parser.add_argument("--track", action="store_true", help="tâm cửa sổ = tư thế OK của vòng trước")
    parser.add_argument("--skip-seconds", type=float, default=0.0)
    parser.add_argument("--every", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--levels", type=int, default=None, help="số mức nhánh-cận (mặc định 4, --global: 5)")
    parser.add_argument("--min-range", type=float, default=LocalizeConfig.min_range_m)
    parser.add_argument("--max-range", type=float, default=LocalizeConfig.max_range_m)
    args = parser.parse_args(argv)
    # Từ chối trước khi nạp gì và trước khi tạo thư mục kết quả (thoát mã 2, không có traceback).
    if args.window is not None and not all(math.isfinite(v) and v >= 0 for v in args.window):
        parser.error("--window DX DY DTHETA_DEG phải hữu hạn và không âm")
    if not all(math.isfinite(v) for v in args.initial):
        parser.error("--initial X Y THETA_DEG phải hữu hạn")
    levels = args.levels or (5 if args.global_search else LocalizeConfig.levels)
    config = LocalizeConfig(levels=levels, min_range_m=args.min_range, max_range_m=args.max_range)
    initial = (args.initial[0], args.initial[1], math.radians(args.initial[2]))
    window = None if args.window is None else (args.window[0], args.window[1], math.radians(args.window[2]))
    report = run(args.map, args.recording, args.out, config, initial=initial, window=window,
                 global_search=args.global_search, track=args.track, skip_seconds=args.skip_seconds,
                 every=args.every, limit=args.limit)
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
