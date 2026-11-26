r"""Bộ ghép định vị LiDAR cho phiên đỗ xe (thêm 02/10/2026, T2): (a) định vị từng vòng trên bản đồ tĩnh
(`lidar/localize.py`) + (b) odometry khớp scan (`lidar/scan_odometry.py`) làm tâm cửa sổ và kiểm chéo, theo ĐỀ XUẤT mục
7 của docs/KIEN_TRUC.md. Người dùng giao quyết định 02/10/2026 ("làm hết"); mọi ngưỡng (`LocalizerParams`,
configs/dinh_vi_lidar_v0.json) vẫn là ĐỀ XUẤT – CHỜ CHỐT. KHÔNG phải SLAM: bản đồ cố định, không đóng vòng.

Đồng bộ, không luồng, không đồng hồ: mỗi lời gọi `process(angles, ranges, t)` là một vòng quét, `t` là dấu thời gian
của vòng theo đồng hồ của NGƯỜI GỌI (nguồn thật: perf_counter lúc vòng về máy; LiDAR mô phỏng: đồng hồ của bo mô
phỏng). Tư thế trả về là tư thế XE (tâm trục sau) trong hệ của bản đồ, đổi từ tư thế cảm biến qua gá (`LidarMount`).

Mỗi vòng:
1. Bỏ phản hồi rơi vào thân xe (gá + thân + lề, như `LiveLidarLayer.filter_scan`).
2. (b) `ScanOdometry.update`. (b) báo `lost` thì dựng lại (b) và bỏ mốc (a, b).
3. Tâm cửa sổ của (a): lúc khởi tạo là điểm gợi ý (điểm xuất phát của sa bàn) qua gá, cửa sổ `init_window`; khi có mốc
   (a_i, b_i) là a_i ⊕ (b_i⁻¹ ⊕ b) — tư thế (b) dự đoán, cửa sổ `track_window`; không có mốc: tư thế OK gần nhất.
4. (a) `localize`. FAILED chỉ vì `window_edge` thì tìm lại một lần với `init_window`. Lúc khởi tạo, KHÔNG đang chạy,
   tối đa một lần mỗi `global_retry_s`: tìm toàn cục. KHÔNG BAO GIỜ tìm toàn cục khi đang chạy (`arm()`).
5. Kiểm chéo khi (a) OK, có mốc và (b) dùng được: d = (a_i ⊕ (b_i⁻¹ ⊕ b))⁻¹ ⊕ a; (b) khóa trục suy biến u thì bỏ thành
   phần của d dọc u (u xoay sang hệ bản đồ theo a_i.θ − b_i.θ); dung sai = base + per · quãng đi kể từ mốc.
6. Quyết định: khởi tạo cần `init_confirm_scans` vòng OK liên tiếp, tản ≤ `init_confirm_spread` (sau khi bù chuyển động
   (b) giữa các vòng đó, nên khởi tạo được cả khi cảm biến đang đi chậm), rồi mới công bố.
   (a) OK + lệch (b) → chốt POSE_DISAGREE ngay vòng đầu. (a) OK → công bố OK; đang chạy mà `max_unchecked_scans` vòng
   liền không kiểm chéo được → chốt POSE_UNCHECKED. (a) không OK → vòng đầu "BAD" (mẫu công bố giữ nguyên, stamp cũ tiếp
   tục già đi), đủ `max_consecutive_bad` vòng liền → chốt POSE_LOST. Đang chạy thì giữ chốt tới `disarm()`; không chạy
   thì sau `relatch_s` tự khởi tạo lại. `reset_feed` khi đang chạy → POSE_LOST.

CLI offline, cùng đường mã với khi chạy (mỗi lệnh một dòng, dán được vào cmd.exe; thay `<...>`):

    .venv\Scripts\python.exe -X utf8 -m autopark.lidar.pose_estimator --map <thư mục bản đồ> --recording <bản ghi>.npz --out <thư mục> --initial X Y YAW_DEG
    .venv\Scripts\python.exe -X utf8 -m autopark.lidar.pose_estimator --map <thư mục bản đồ> --recording runs\session_recordings\<thư mục> --same-scans-as <thư mục log>\localization.csv --out <thư mục> --initial X Y YAW_DEG

`--recording`: một `.npz` của `lidar.recording`, hoặc (thêm 02/10/2026) một thư mục bản ghi phiên (T3, `rig.recording`):
mọi phần `lidar/part_*.npz` nối lại theo thứ tự (`lidar.recording.read_lidar_any`). Tùy chọn thêm: [--config
configs\dinh_vi_lidar_v0.json] [--sensor-frame] (gá = 0: tư thế là của cảm biến, cho bản ghi C1 trên bàn)
[--vehicle-config <xe>.json] (mặt nạ thân xe) [--skip-seconds 3] [--limit N] [--drop-every N] (bỏ mỗi vòng thứ N: thử
vòng bị rơi) [--same-scans-as <localization.csv>] (xử lý đúng các vòng của một lần chạy đã ghi, so được từng dòng; xem
dưới) [--same-scans-tolerance-ms MS] [--fail-on-stop] (mã thoát 1 khi có mã dừng). Bộ ghép được `arm()` ngay khi bắt
được (như lúc bấm Bắt đầu đỗ), nên mã dừng đầu tiên trong pose_estimator.json là mã mà phiên sẽ dừng. Kết quả:
localization.csv, pose_estimator.json (đếm theo quyết định, mã dừng đầu tiên, độ trễ, sha của bản đồ, cấu hình và bản
ghi (từng phần khi là thư mục), commit), overlay.png.

`--same-scans-as` (sửa 02/10/2026): mỗi dòng của localization.csv ghép với vòng GẦN NHẤT của bản ghi, phải là vòng duy
nhất cách t_perf_scan của dòng không quá dung sai (`SAME_SCANS_TOLERANCE_S` = 10 ms, đổi bằng
--same-scans-tolerance-ms); các dòng ghép theo đúng thứ tự, không hai dòng cùng một vòng. localization.csv của phiên ghi
t_perf của `ScanReader` (đọc perf_counter hai lần), bản ghi T3 ghi stamp + t0 của cùng vòng: hai số lệch vài µs chứ
không bằng nhau (trước đó đòi lệch ≤ 1 µs và chỉ đọc một `.npz`, nên không ghép được lần chạy nào của phiên). Bộ ghép
nhận vòng quét của bản ghi với t_perf_scan, t_first_perf của DÒNG (như bộ ghép lúc chạy), nên localization.csv mới có
cùng t_perf_scan từng dòng; độ lệch lớn nhất và trung vị ghi ở `summary.same_scans`. Dòng không có vòng trong bản ghi
(ví dụ bản ghi bắt đầu sau các dòng before_start: bắt đầu ghi trước khi bấm Bắt đầu đỗ) → mã thoát 2.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import csv
from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import sys

import cv2
import numpy as np

from autopark.domain.types import Pose, VehicleConfig

from .localize import AMBIGUOUS, FAILED, OK, LocalizationMap, localize, wrap
from .pose_config import CrossCheck, LidarMount, LocalizerParams
from .scan_odometry import INIT as ODO_INIT, OdometryConfig, ScanOdometry, between, compose

INIT, TRACKING, DEGRADED, LATCHED = "INIT", "TRACKING", "DEGRADED", "LATCHED"
POSE_OK = "OK"
POSE_LOST, POSE_DISAGREE, POSE_UNCHECKED = "POSE_LOST", "POSE_DISAGREE", "POSE_UNCHECKED"
STOP_CODES = (POSE_LOST, POSE_DISAGREE, POSE_UNCHECKED)
# Quyết định của một vòng (cột decision của localization.csv)
DECISIONS = ("INIT", "OK", "BAD", POSE_LOST, POSE_DISAGREE, POSE_UNCHECKED, "LATCHED", "RESET")
HISTORY = 64                       # số vòng gần nhất giữ cho `pose_for_time` và `health`
FEED_RESET_REASON = "LiDAR ngắt/đổi chiều góc giữa lần chạy"
SAME_SCANS_TOLERANCE_S = 0.010
"""Dung sai ghép một dòng localization.csv với một vòng của bản ghi (`--same-scans-as`, thêm 02/10/2026). Trong phiên,
t_perf_scan = perf_counter lúc `ScanReader` đọc − (source.now() − stamp); bản ghi T3 (`rig.recording.LidarTap`) ghi
stamp + t0 của cùng vòng; hai số lệch đúng khoảng giữa hai lần đọc đồng hồ. Thử 02/10/2026 trên máy bàn với nguồn giả
kiểu C1 qua `LidarTap` và `ScanReader`: trung vị 3,7–5 µs, lớn nhất 24 µs trên 300 vòng (rà soát); lớn nhất 0,55 ms
trên 3000 vòng khi hai luồng tải giành GIL (luồng đọc bị chen giữa hai lần đọc; khoảng chuyển GIL mặc định 5 ms). Chu kỳ
vòng C1 ≈ 100 ms: 10 ms vẫn xa dưới nửa chu kỳ, nên không ghép nhầm sang vòng kề (`match_scan_times` vẫn đòi đúng một
vòng trong dung sai)."""


@dataclass(frozen=True)
class Published:
    """Mẫu đang công bố: trạng thái (OK hoặc mã dừng), tư thế XE, dấu thời gian của vòng quét, lý do (tiếng Việt)."""

    status: str
    vehicle_pose: Pose
    t: float
    reason_vi: str = ""


@dataclass(frozen=True)
class CheckResult:
    """Kết quả kiểm chéo (a)/(b) một vòng (hàm `cross_check`)."""

    dx: float                     # m, hệ bản đồ, sau khi bỏ thành phần dọc trục suy biến (nếu có)
    dy: float
    dyaw_deg: float
    tol_m: float
    tol_deg: float
    travel_m: float
    axis_dropped: bool

    @property
    def disagree(self) -> bool:
        return math.hypot(self.dx, self.dy) > self.tol_m or abs(self.dyaw_deg) > self.tol_deg


def cross_check(anchor_a, anchor_b, b_pose, a_pose, cc: CrossCheck, *, locked: bool = False,
                axis=(math.nan, math.nan)) -> CheckResult:
    """Kiểm chéo thuần (không trạng thái): tư thế (a) `a_pose` so với dự đoán a_i ⊕ (b_i⁻¹ ⊕ b). `axis`: hướng suy biến
    đơn vị của (b) trong hệ odometry khi `locked`; thành phần lệch dọc hướng đó (xoay sang hệ bản đồ theo
    a_i.θ − b_i.θ) bị bỏ, vì (b) không biết nó."""
    rel = between(anchor_b, b_pose)
    pred = compose(anchor_a, rel)
    d = between(pred, a_pose)
    c, s = math.cos(pred[2]), math.sin(pred[2])
    dmap = np.array([c * d[0] - s * d[1], s * d[0] + c * d[1]])
    dropped = False
    if locked and all(math.isfinite(v) for v in axis):
        rot = float(anchor_a[2] - anchor_b[2])
        cr, sr = math.cos(rot), math.sin(rot)
        u = np.array([cr * axis[0] - sr * axis[1], sr * axis[0] + cr * axis[1]])
        norm = float(np.hypot(u[0], u[1]))
        if norm > 1e-9:
            u = u / norm
            dmap = dmap - float(dmap @ u) * u
            dropped = True
    travel = math.hypot(rel[0], rel[1])
    tol_m, tol_deg = cc.tolerance(travel)
    return CheckResult(float(dmap[0]), float(dmap[1]), math.degrees(float(d[2])), tol_m, tol_deg, travel, dropped)


@dataclass
class EstimatorStep:
    """Một vòng đã xử lý (một dòng localization.csv). Tư thế (a), tâm cửa sổ, (b) là của CẢM BIẾN (hệ bản đồ / hệ
    odometry); vehicle_* là tư thế XE của vòng (từ (a) khi OK), truth_* chỉ có ở LiDAR mô phỏng."""

    n: int
    t: float
    t_first: float | None = None
    state: str = INIT
    beams: int = 0
    valid: int = 0
    a_status: str = ""
    a_reasons: str = ""
    a_window: str = ""
    a_x: float = math.nan
    a_y: float = math.nan
    a_yaw: float = math.nan
    a_matched_fraction: float = math.nan
    a_conflict_fraction: float = math.nan
    a_second_ratio: float | None = None
    a_std_x: float = math.nan
    a_std_y: float = math.nan
    a_std_yaw_deg: float = math.nan
    a_ms: float = 0.0
    centre: tuple[float, float, float] | None = None
    b_status: str = ""
    b_reasons: str = ""
    b_x: float = math.nan
    b_y: float = math.nan
    b_yaw: float = math.nan
    b_locked: bool = False
    b_axis_x: float = math.nan
    b_axis_y: float = math.nan
    b_retried: bool = False
    b_ms: float = 0.0
    check_used: bool = False
    check: CheckResult | None = None
    decision: str = ""
    bad_run: int = 0
    unchecked_run: int = 0
    vehicle: Pose | None = None
    reason_vi: str = ""
    truth: Pose | None = None
    # do nguồn tư thế điền (không phải bộ ghép)
    phase: str = ""
    t_io: float | None = None
    t_done: float | None = None
    dropped_before: int = 0

    @property
    def latency_s(self) -> float | None:
        return None if self.t_done is None else self.t_done - self.t

    @property
    def stopped(self) -> bool:
        return self.decision in STOP_CODES


LOCALIZATION_FIELDS = [
    "n", "phase", "t_perf_scan", "t_first_perf", "t_io_scan", "t_done_perf", "latency_ms", "dropped_before", "state",
    "beams", "valid_beams",
    "a_status", "a_reasons", "a_window", "a_x", "a_y", "a_yaw_deg", "a_matched_fraction", "a_conflict_fraction",
    "a_second_ratio", "a_std_x_m", "a_std_y_m", "a_std_yaw_deg", "a_ms",
    "centre_x", "centre_y", "centre_yaw_deg",
    "b_status", "b_reasons", "b_x", "b_y", "b_yaw_deg", "b_locked", "b_axis_x", "b_axis_y", "b_retried", "b_ms",
    "check_used", "check_dx", "check_dy", "check_dyaw_deg", "check_tol_m", "check_tol_deg",
    "decision", "bad_run", "unchecked_run", "vehicle_x", "vehicle_y", "vehicle_yaw_deg", "reason",
    "truth_x", "truth_y", "truth_yaw_deg",
]


def _num(value) -> str | float:
    """Ô số: rỗng khi None/NaN; đủ chữ số (repr) để `--same-scans-as` so được tới 1e-9."""
    if value is None:
        return ""
    value = float(value)
    return "" if not math.isfinite(value) else value


def _deg(value) -> str | float:
    return "" if value is None or not math.isfinite(float(value)) else math.degrees(float(value))


def step_row(step: EstimatorStep, *, time_base: str = "perf") -> dict:
    """Dòng localization.csv của một vòng. `time_base`: "perf" (nguồn thật: t là perf_counter) hoặc "io" (LiDAR mô
    phỏng: t là đồng hồ io của bo mô phỏng; khi đó các cột *_perf để trống)."""
    perf = time_base == "perf"
    centre = step.centre or (None, None, None)
    check = step.check
    vehicle = step.vehicle
    truth = step.truth
    latency = step.latency_s
    return {
        "n": step.n, "phase": step.phase, "t_perf_scan": _num(step.t) if perf else "",
        "t_first_perf": _num(step.t_first) if perf else "",
        "t_io_scan": _num(step.t if not perf else step.t_io), "t_done_perf": _num(step.t_done) if perf else "",
        "latency_ms": "" if latency is None else latency * 1000.0, "dropped_before": step.dropped_before,
        "state": step.state, "beams": step.beams, "valid_beams": step.valid,
        "a_status": step.a_status, "a_reasons": step.a_reasons, "a_window": step.a_window, "a_x": _num(step.a_x),
        "a_y": _num(step.a_y), "a_yaw_deg": _deg(step.a_yaw), "a_matched_fraction": _num(step.a_matched_fraction),
        "a_conflict_fraction": _num(step.a_conflict_fraction), "a_second_ratio": _num(step.a_second_ratio),
        "a_std_x_m": _num(step.a_std_x), "a_std_y_m": _num(step.a_std_y), "a_std_yaw_deg": _num(step.a_std_yaw_deg),
        "a_ms": round(step.a_ms, 3),
        "centre_x": _num(centre[0]), "centre_y": _num(centre[1]), "centre_yaw_deg": _deg(centre[2]),
        "b_status": step.b_status, "b_reasons": step.b_reasons, "b_x": _num(step.b_x), "b_y": _num(step.b_y),
        "b_yaw_deg": _deg(step.b_yaw), "b_locked": int(step.b_locked), "b_axis_x": _num(step.b_axis_x),
        "b_axis_y": _num(step.b_axis_y), "b_retried": int(step.b_retried), "b_ms": round(step.b_ms, 3),
        "check_used": int(step.check_used), "check_dx": "" if check is None else check.dx,
        "check_dy": "" if check is None else check.dy, "check_dyaw_deg": "" if check is None else check.dyaw_deg,
        "check_tol_m": "" if check is None else check.tol_m, "check_tol_deg": "" if check is None else check.tol_deg,
        "decision": step.decision, "bad_run": step.bad_run, "unchecked_run": step.unchecked_run,
        "vehicle_x": "" if vehicle is None else vehicle.x, "vehicle_y": "" if vehicle is None else vehicle.y,
        "vehicle_yaw_deg": "" if vehicle is None else math.degrees(vehicle.yaw), "reason": step.reason_vi,
        "truth_x": "" if truth is None else truth.x, "truth_y": "" if truth is None else truth.y,
        "truth_yaw_deg": "" if truth is None else math.degrees(truth.yaw),
    }


def write_localization_csv(path, rows: list[dict]) -> Path:
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOCALIZATION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _back_to_first(confirm) -> list[np.ndarray]:
    """Các tư thế (a) lúc khởi tạo, đưa về thời điểm vòng xác nhận ĐẦU bằng chuyển động (b) giữa hai vòng: cảm biến đứng
    yên thì không đổi gì; đang chạy chậm thì độ tản vẫn đo được độ nhất quán của (a). Vòng không có (b) giữ nguyên."""
    first_b = confirm[0][1]
    out = []
    for a_pose, b_pose in confirm:
        if first_b is None or b_pose is None:
            out.append(a_pose)
        else:
            rel = between(first_b, b_pose)                      # chuyển động từ vòng đầu tới vòng này (hệ cảm biến)
            out.append(compose(a_pose, between(rel, np.zeros(3))))
    return out


def _spread(poses: list[np.ndarray]) -> tuple[float, float]:
    """(m, độ) lớn nhất quanh trung vị (vòng) của các tư thế."""
    arr = np.array(poses, np.float64)
    mean = math.atan2(float(np.sin(arr[:, 2]).mean()), float(np.cos(arr[:, 2]).mean()))
    dev = wrap(arr[:, 2] - mean)
    med = np.array([np.median(arr[:, 0]), np.median(arr[:, 1]), wrap(mean + float(np.median(dev)))])
    return (float(np.max(np.hypot(arr[:, 0] - med[0], arr[:, 1] - med[1]))),
            float(np.max(np.abs(np.degrees(wrap(arr[:, 2] - med[2]))))))


class LidarPoseEstimator:
    """Bộ ghép (a) + (b); xem docstring mô-đun. Chỉ MỘT luồng được gọi các phương thức (nguồn thật: luồng
    "dinh_vi_lidar"; mô phỏng: luồng của phiên)."""

    def __init__(self, lmap: LocalizationMap, params: LocalizerParams | None = None, *, mount: LidarMount | None = None,
                 odometry: OdometryConfig | None = None, localize_config=None, self_mask: VehicleConfig | None = None,
                 hint: Pose | None = None, localize_fn=localize, odometry_factory=ScanOdometry):
        if localize_config is not None and localize_config != lmap.config:
            lmap = LocalizationMap(lmap.states, lmap.grid, localize_config, source=lmap.source)
        self.lmap = lmap
        self.params = params or LocalizerParams()
        self.mount = mount or LidarMount()
        self.mount_tuple = self.mount.as_tuple()
        self.odometry_config = odometry or OdometryConfig(velocity_per="second")
        self.self_mask = self_mask
        self.hint = hint
        self.localize_fn = localize_fn
        self.odometry_factory = odometry_factory
        self.odom = odometry_factory(self.odometry_config)
        self._gmap: LocalizationMap | None = None
        self.state = INIT
        self.armed = False
        self.anchor: tuple[np.ndarray, np.ndarray] | None = None
        self.last_ok_sensor: np.ndarray | None = None
        self._published: Published | None = None
        self.bad_run = 0
        self.unchecked_run = 0
        self._bad_results: list[str] = []
        self._confirm: list[tuple[np.ndarray, np.ndarray | None]] = []   # (a, b) của các vòng OK lúc khởi tạo
        self.latch_t: float | None = None
        self.last_global_t = -math.inf
        self.last_t: float | None = None
        self.n = 0
        self.history: deque[EstimatorStep] = deque(maxlen=HISTORY)
        self.decisions: Counter = Counter()
        self.global_searches = 0
        self.odometry_restarts = 0

    # ------------------------------------------------------------------------------------------------ điều khiển
    def set_hint(self, vehicle_pose: Pose | None) -> None:
        """Điểm gợi ý (tư thế XE, thường là điểm xuất phát của sa bàn) cho lúc khởi tạo. Đang khởi tạo thì bắt đầu đếm
        xác nhận lại quanh gợi ý mới; đang bám thì không đổi gì."""
        self.hint = vehicle_pose
        if self.state == INIT:
            self._confirm = []
            self.last_global_t = -math.inf

    def arm(self) -> None:
        """Lần chạy bắt đầu: từ giờ không tìm toàn cục, không tự khởi tạo lại; chốt dừng giữ tới `disarm()`."""
        self.armed = True

    def disarm(self) -> None:
        self.armed = False

    def reset_feed(self, reason_vi: str = "") -> None:
        """Nguồn vòng quét bị ngắt hay đổi chiều góc. Đang chạy: chốt POSE_LOST. Không chạy: khởi tạo lại từ đầu."""
        text = FEED_RESET_REASON + (f": {reason_vi}" if reason_vi else "")
        if self.armed:
            if self.state != LATCHED:
                self._latch(POSE_LOST, text, self.last_t if self.last_t is not None else 0.0)
            return
        self._restart(clear_published=True)

    def published(self) -> Published | None:
        return self._published

    # ---------------------------------------------------------------------------------------------------- truy vấn
    def pose_for_time(self, t: float) -> tuple[str, Pose | None]:
        """Tư thế XE của vòng quét có dấu thời gian `t`: ("ok", tư thế) khi vòng đó OK, ("bad", None) khi không OK
        hoặc đã quá cũ để còn trong lịch sử, ("pending", None) khi chưa xử lý tới."""
        if self.last_t is None or t > self.last_t + 1e-9:
            return "pending", None
        for step in reversed(self.history):
            if abs(step.t - t) <= 1e-9:
                return ("ok", step.vehicle) if step.decision == "OK" and step.vehicle is not None else ("bad", None)
            if step.t < t - 1e-9:
                break
        return "bad", None

    def health(self, now_t: float, received_ts) -> tuple[list[str], list[str]]:
        """Điều kiện START của nguồn tư thế (tiếng Việt): (vấn đề, cảnh báo). `received_ts`: dấu thời gian các vòng đã
        NHẬN (kể cả vòng bị bỏ vì hàng đợi đầy), cùng đồng hồ với `now_t`."""
        p = self.params
        problems, warnings = [], []
        if self.state != TRACKING:
            text = {INIT: "định vị LiDAR đang khởi tạo (chưa xác nhận đủ vòng OK quanh điểm xuất phát)",
                    DEGRADED: "vòng gần nhất của định vị LiDAR không OK",
                    LATCHED: f"định vị LiDAR đang chốt {self._published.status if self._published else '?'}: "
                             f"{self._published.reason_vi if self._published else ''}"}[self.state]
            problems.append(text)
        recent = [s.decision for s in self.history if s.decision not in ("RESET",)][-p.start_ok_scans:]
        ok_count = sum(1 for d in recent if d == "OK")
        if len(recent) < p.start_ok_scans or ok_count < p.start_ok_scans:
            problems.append(f"chưa có {p.start_ok_scans} vòng định vị OK liên tiếp ({ok_count}/{len(recent)} vòng "
                            f"gần nhất OK)")
        times = sorted(float(t) for t in received_ts if now_t - 2.0 <= float(t) <= now_t + 1e-9)
        rate = (len(times) - 1) / (times[-1] - times[0]) if len(times) >= 3 and times[-1] > times[0] else 0.0
        if rate < p.min_rate_hz:
            problems.append(f"LiDAR chỉ {rate:.1f} vòng/s trong 2 s gần nhất (cần ≥ {p.min_rate_hz:g})")
        latencies = [s.latency_s for s in list(self.history)[-20:] if s.latency_s is not None]
        if latencies:
            p95 = float(np.percentile(latencies, 95))
            if p95 > p.max_latency_p95_s:
                problems.append(f"xử lý một vòng chậm: p95 {p95 * 1000:.0f} ms > {p.max_latency_p95_s * 1000:.0f} ms")
            elif p95 > p.warn_latency_p95_s:
                warnings.append(f"xử lý một vòng chậm: p95 {p95 * 1000:.0f} ms > {p.warn_latency_p95_s * 1000:.0f} ms")
        if self.anchor is None:
            problems.append("chưa có mốc kiểm chéo (a)/(b): odometry khớp scan chưa bắt được")
        return problems, warnings

    # ------------------------------------------------------------------------------------------------- một vòng
    def _mask(self, angles: np.ndarray, ranges: np.ndarray) -> np.ndarray:
        if self.self_mask is None:
            return ranges
        from autopark.fusion.layers import body_mask

        drop = body_mask(angles, ranges, self.mount_tuple, self.self_mask, self.params.self_mask_margin_m)
        if not drop.any():
            return ranges
        out = ranges.copy()
        out[drop] = np.nan
        return out

    def _global_map(self) -> LocalizationMap:
        if self._gmap is None:
            lmap = self.lmap
            self._gmap = LocalizationMap(lmap.states, lmap.grid, replace(lmap.config, levels=5), source=lmap.source)
        return self._gmap

    def _restart(self, *, clear_published: bool) -> None:
        self.odom = self.odometry_factory(self.odometry_config)
        self.odometry_restarts += 1
        self.anchor = None
        self.state = INIT
        self.bad_run = self.unchecked_run = 0
        self._bad_results = []
        self._confirm = []
        self.latch_t = None
        if clear_published:
            self._published = None

    def _latch(self, code: str, reason: str, t: float) -> None:
        self.state = LATCHED
        self.latch_t = t
        pose = (self._published.vehicle_pose if self._published is not None
                else self.mount.vehicle_pose(Pose(*self.last_ok_sensor)) if self.last_ok_sensor is not None
                else Pose(math.nan, math.nan, math.nan))
        self._published = Published(code, pose, t, reason)

    def _vehicle(self, sensor: np.ndarray) -> Pose:
        return self.mount.vehicle_pose(Pose(float(sensor[0]), float(sensor[1]), float(sensor[2])))

    def _record(self, step: EstimatorStep) -> EstimatorStep:
        step.state = self.state
        step.bad_run, step.unchecked_run = self.bad_run, self.unchecked_run
        self.history.append(step)
        self.decisions[step.decision] += 1
        self.last_t = step.t
        return step

    def process(self, angles, ranges, t: float, *, t_first: float | None = None,
                truth: Pose | None = None) -> EstimatorStep:
        """Xử lý một vòng quét (xem docstring mô-đun). `truth`: tư thế XE thật (chỉ LiDAR mô phỏng, chỉ để ghi log)."""
        p = self.params
        t = float(t)
        angles = np.asarray(angles, np.float64)
        ranges = np.asarray(ranges, np.float64)
        step = EstimatorStep(self.n, t, t_first, beams=len(ranges), valid=int(np.isfinite(ranges).sum()), truth=truth)
        self.n += 1
        if self.state == LATCHED:
            if not self.armed and self.latch_t is not None and t >= self.latch_t + p.relatch_s:
                self._restart(clear_published=True)
            else:
                step.decision = "LATCHED"
                step.reason_vi = self._published.reason_vi if self._published is not None else ""
                return self._record(step)
        ranges = self._mask(angles, ranges)
        # (b) odometry khớp scan
        b = self.odom.update(angles, ranges, t)
        if b.status == FAILED and "lost" in b.reasons:
            self.odom = self.odometry_factory(self.odometry_config)
            self.odometry_restarts += 1
            self.anchor = None
            self._confirm = []                     # hệ odometry mới: không so được với các vòng xác nhận cũ
        b_ok = b.status in (ODO_INIT, OK, AMBIGUOUS)
        step.b_status, step.b_reasons = b.status, "+".join(b.reasons)
        step.b_x, step.b_y, step.b_yaw = b.x, b.y, b.theta
        step.b_locked, step.b_retried, step.b_ms = bool(b.locked), bool(b.retried), b.time_ms
        step.b_axis_x, step.b_axis_y = getattr(b, "axis_x", math.nan), getattr(b, "axis_y", math.nan)
        # tâm cửa sổ của (a)
        centre, window, kind = None, None, ""
        if self.state == INIT:
            if self._confirm:
                last_a, last_b = self._confirm[-1]
                centre = (compose(last_a, between(last_b, b.pose)) if last_b is not None and b_ok else last_a)
            elif self.hint is not None:
                sensor = self.mount.sensor_pose(self.hint)
                centre = np.array([sensor.x, sensor.y, sensor.yaw])
            elif self.last_ok_sensor is not None:
                centre = self.last_ok_sensor
            window, kind = p.window_rad("init_window"), "init"
        elif self.anchor is not None:
            centre = compose(self.anchor[0], between(self.anchor[1], b.pose))
            window, kind = p.window_rad("track_window"), "track"
        else:
            centre, window, kind = self.last_ok_sensor, p.window_rad("track_window"), "track_last_ok"
        a = None
        if centre is not None:
            step.centre = tuple(float(v) for v in centre)
            a = self.localize_fn(self.lmap, angles, ranges, tuple(float(v) for v in centre), window=window)
            if (a.status == FAILED and tuple(a.reasons) == ("window_edge",) and p.retry_on_window_edge
                    and kind != "init"):
                a = self.localize_fn(self.lmap, angles, ranges, tuple(float(v) for v in centre),
                                     window=p.window_rad("init_window"))
                kind += "+retry"
        if (self.state == INIT and (a is None or a.status != OK) and not self.armed and p.allow_global_init
                and t - self.last_global_t >= p.global_retry_s):
            self.last_global_t = t
            self.global_searches += 1
            a = self.localize_fn(self._global_map(), angles, ranges, (0.0, 0.0, 0.0), global_search=True)
            kind = "global"
        step.a_window = kind
        a_pose = None
        if a is not None:
            step.a_status, step.a_reasons = a.status, "+".join(a.reasons)
            step.a_x, step.a_y, step.a_yaw = a.x, a.y, a.theta
            step.a_matched_fraction, step.a_conflict_fraction = a.matched_fraction, a.conflict_fraction
            step.a_second_ratio = a.second_ratio
            step.a_std_x, step.a_std_y, step.a_std_yaw_deg = a.std_x_m, a.std_y_m, a.std_theta_deg
            step.a_ms = a.time_ms
            if a.status == OK:
                a_pose = np.array([a.x, a.y, a.theta], np.float64)
        else:
            step.a_status, step.a_reasons = "", "no_centre"
        # kiểm chéo
        check = None
        if a_pose is not None and self.anchor is not None and b_ok and self.state != INIT:
            check = cross_check(self.anchor[0], self.anchor[1], b.pose, a_pose, p.cross_check, locked=bool(b.locked),
                                axis=(step.b_axis_x, step.b_axis_y))
            step.check_used, step.check = True, check
        return self._record(self._decide(step, a, a_pose, b, b_ok, check, t))

    def _decide(self, step: EstimatorStep, a, a_pose, b, b_ok: bool, check: CheckResult | None,
                t: float) -> EstimatorStep:
        p = self.params
        if self.state == INIT:
            if a_pose is None:
                self._confirm = []
                step.decision = "INIT"
                step.reason_vi = ("đang khởi tạo: chưa có tâm tìm (chưa có điểm xuất phát)" if a is None else
                                  f"đang khởi tạo: (a) {a.status} ({'+'.join(a.reasons) or '—'})")
                return step
            self._confirm = (self._confirm + [(a_pose, b.pose.copy() if b_ok else None)])[-p.init_confirm_scans:]
            spread_m, spread_deg = _spread(_back_to_first(self._confirm))
            if (len(self._confirm) < p.init_confirm_scans or spread_m > p.init_confirm_spread[0]
                    or spread_deg > p.init_confirm_spread[1]):
                step.decision = "INIT"
                step.reason_vi = (f"đang khởi tạo: {len(self._confirm)}/{p.init_confirm_scans} vòng OK, tản "
                                  f"{spread_m * 100:.1f} cm / {spread_deg:.2f}°")
                if spread_m > p.init_confirm_spread[0] or spread_deg > p.init_confirm_spread[1]:
                    self._confirm = self._confirm[-1:]  # tản quá: đếm lại từ vòng này
                return step
            self.state = TRACKING
            self._confirm = []
            self.bad_run = self.unchecked_run = 0
            self.anchor = (a_pose, b.pose.copy()) if b_ok else None
            return self._publish_ok(step, a_pose, t)
        if a_pose is not None:
            if check is not None and check.disagree:
                reason = (f"(a) và (b) lệch {math.hypot(check.dx, check.dy) * 100:.1f} cm / {check.dyaw_deg:+.2f}° "
                          f"(cho phép {check.tol_m * 100:.1f} cm / {check.tol_deg:.1f}° sau {check.travel_m:.2f} m): "
                          f"(a) có thể nhảy sang đỉnh sai hoặc (b) trượt")
                step.vehicle = self._vehicle(a_pose)
                self._latch(POSE_DISAGREE, reason, t)
                step.decision, step.reason_vi = POSE_DISAGREE, reason
                return step
            self.bad_run = 0
            self._bad_results = []
            self.unchecked_run = 0 if check is not None else self.unchecked_run + 1
            if b_ok:
                self.anchor = (a_pose, b.pose.copy())
            self.state = TRACKING
            self._publish_ok(step, a_pose, t)
            if self.armed and self.unchecked_run >= p.max_unchecked_scans:
                reason = (f"{self.unchecked_run} vòng liên tiếp không kiểm chéo được (a)/(b) (vòng này (b) "
                          f"{b.status}: {'+'.join(b.reasons) or '—'})")
                self._latch(POSE_UNCHECKED, reason, t)
                step.decision, step.reason_vi = POSE_UNCHECKED, reason
            return step
        self.bad_run += 1
        self.unchecked_run += 1
        status = "—" if a is None else f"{a.status} ({'+'.join(a.reasons) or '—'})"
        self._bad_results.append(status)
        if self.bad_run < p.max_consecutive_bad:
            self.state = DEGRADED
            step.decision = "BAD"
            step.reason_vi = f"{self.bad_run} vòng không OK: {status}"
            return step
        reason = f"định vị (a) không OK {self.bad_run} vòng liên tiếp: " + "; ".join(self._bad_results[-self.bad_run:])
        self._latch(POSE_LOST, reason, t)
        step.decision, step.reason_vi = POSE_LOST, reason
        return step

    def _publish_ok(self, step: EstimatorStep, a_pose: np.ndarray, t: float) -> EstimatorStep:
        vehicle = self._vehicle(a_pose)
        self.last_ok_sensor = a_pose
        self._published = Published(POSE_OK, vehicle, t, "")
        step.vehicle, step.decision = vehicle, "OK"
        return step


# ------------------------------------------------------------------------------------------------------------- CLI
def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def summarize_steps(steps: list[EstimatorStep]) -> dict:
    """Đếm theo quyết định, mã dừng đầu tiên, độ trễ (khi có), thời gian (a) và (b)."""
    decisions = Counter(s.decision for s in steps)
    first = next((s for s in steps if s.stopped), None)
    latencies = [s.latency_s for s in steps if s.latency_s is not None]
    a_ms = [s.a_ms for s in steps if s.a_status]
    b_ms = [s.b_ms for s in steps if s.b_status]

    def stats(values):
        return None if not values else {"p50": float(np.percentile(values, 50)), "p95": float(np.percentile(values, 95)),
                                        "max": float(np.max(values))}

    return {"scans": len(steps), "decisions": dict(decisions),
            "first_stop": None if first is None else {"n": first.n, "t": first.t, "code": first.decision,
                                                      "reason": first.reason_vi},
            "check_used": sum(1 for s in steps if s.check_used),
            "latency_s": stats(latencies), "a_ms": stats(a_ms), "b_ms": stats(b_ms)}


def render_overlay(lmap: LocalizationMap, steps: list[EstimatorStep], title: str) -> np.ndarray:
    """Bản đồ + tư thế XE từng vòng: xanh dương = OK, cam = BAD/INIT có (a), X đen = mã dừng. Chữ ASCII."""
    from autopark.perception.costmap import render

    grid = lmap.grid
    scale = max(1, int(640 / max(lmap.states.shape)))
    canvas = render(lmap.states, grid, None, None, scale=scale)

    def px(x, y):
        return int((grid.y_max - y) / grid.resolution * scale), int((grid.x_max - x) / grid.resolution * scale)

    for s in steps:
        if s.vehicle is not None and math.isfinite(s.vehicle.x):
            color = (255, 60, 0) if s.decision == "OK" else (0, 0, 0)
            cv2.circle(canvas, px(s.vehicle.x, s.vehicle.y), 2, color, -1)
        elif s.stopped:
            cv2.drawMarker(canvas, px(s.a_x, s.a_y) if math.isfinite(s.a_x) else (5, 5), (0, 0, 0),
                           cv2.MARKER_TILTED_CROSS, 9, 2)
        elif math.isfinite(s.a_x):
            cv2.circle(canvas, px(s.a_x, s.a_y), 2, (0, 140, 255), -1)
    lines = title.split("\n") + ["blue = vehicle pose of an OK scan, orange = sensor pose of a non-OK scan"]
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1] - 1, 17 * len(lines) + 4), (40, 40, 40), -1)
    for k, line in enumerate(lines):
        cv2.putText(canvas, line, (6, 16 + 17 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    return canvas


@dataclass(frozen=True)
class SameScanRow:
    """Một dòng của localization.csv cho `--same-scans-as`: số dòng dữ liệu (từ 1, không kể tiêu đề), t_perf_scan,
    t_first_perf (None khi ô trống)."""

    line: int
    t: float
    t_first: float | None


def _float_cell(path: Path, line: int, key: str, text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"{path.name} dòng {line}: {key} = {text!r} không phải số") from None
    if not math.isfinite(value):
        raise ValueError(f"{path.name} dòng {line}: {key} = {text!r} không hữu hạn")
    return value


def read_same_scans(path) -> list[SameScanRow]:
    """Các dòng của một localization.csv (của phiên đỗ xe, hay của chính CLI này) cho `--same-scans-as`. Dòng không có
    t_perf_scan (LiDAR mô phỏng chỉ có t_io_scan) hay ô thời gian không phải số hữu hạn → ValueError."""
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    out = []
    for k, row in enumerate(rows, 1):
        text = (row.get("t_perf_scan") or "").strip()
        if not text:
            raise ValueError(f"{path.name} dòng {k}: không có t_perf_scan (bản ghi LiDAR mô phỏng không so được)")
        first = (row.get("t_first_perf") or "").strip()
        out.append(SameScanRow(k, _float_cell(path, k, "t_perf_scan", text),
                               _float_cell(path, k, "t_first_perf", first) if first else None))
    return out


def match_scan_times(t_rec, wanted, tolerance_s: float = SAME_SCANS_TOLERANCE_S, *,
                     name: str = "localization.csv") -> tuple[list[int], np.ndarray]:
    """Ghép từng thời gian `wanted` (t_perf_scan của các dòng, theo thứ tự dòng) với một vòng của bản ghi (`t_rec`,
    không giảm): vòng DUY NHẤT cách nó không quá `tolerance_s` (`SAME_SCANS_TOLERANCE_S`). Trả (chỉ số vòng, độ lệch
    t_rec − t của từng dòng, giây). ValueError (tiếng Việt, kèm số dòng) khi: bản ghi rỗng; không có vòng nào trong
    dung sai (kèm độ lệch của vòng gần nhất và khoảng thời gian của bản ghi); có hơn một vòng (dung sai quá rộng so với
    chu kỳ vòng); dòng ghép vào vòng không đứng sau vòng của dòng trước (hai dòng cùng một vòng, dòng lùi thời gian)."""
    t_rec = np.asarray(t_rec, np.float64)
    wanted = np.asarray(wanted, np.float64)
    if not (math.isfinite(tolerance_s) and tolerance_s > 0):
        raise ValueError(f"dung sai ghép vòng phải hữu hạn và > 0 (nhận {tolerance_s!r})")
    if len(wanted) and not len(t_rec):
        raise ValueError("bản ghi không có vòng nào")
    lo = np.searchsorted(t_rec, wanted - tolerance_s, side="left")
    hi = np.searchsorted(t_rec, wanted + tolerance_s, side="right")
    tol_ms = tolerance_s * 1000.0
    indices: list[int] = []
    for line, (value, a, b) in enumerate(zip(wanted.tolist(), lo.tolist(), hi.tolist()), 1):
        if b == a:
            near = int(np.argmin(np.abs(t_rec - value)))
            raise ValueError(f"{name} dòng {line}: vòng t_perf_scan = {value!r} không có trong bản ghi (vòng gần nhất "
                             f"lệch {abs(float(t_rec[near]) - value) * 1000.0:.3f} ms, dung sai {tol_ms:g} ms; bản ghi "
                             f"có {len(t_rec)} vòng, t từ {float(t_rec[0])!r} tới {float(t_rec[-1])!r})")
        if b - a > 1:
            raise ValueError(f"{name} dòng {line}: {b - a} vòng của bản ghi cách t_perf_scan = {value!r} không quá "
                             f"{tol_ms:g} ms: dung sai quá rộng so với chu kỳ vòng")
        if indices and a <= indices[-1]:
            raise ValueError(f"{name} dòng {line}: ghép vào vòng {a} của bản ghi, không sau vòng {indices[-1]} của "
                             f"dòng trước (hai dòng cùng một vòng, hoặc các dòng không theo thứ tự thời gian)")
        indices.append(int(a))
    gaps = t_rec[indices] - wanted if indices else np.zeros(0)
    return indices, gaps


def run_offline(map_dir, recording_path, out: Path, config, *, initial: Pose | None = None, sensor_frame: bool = False,
                self_mask: VehicleConfig | None = None, skip_seconds: float = 3.0, limit: int | None = None,
                drop_every: int | None = None, same_scans_as: Path | None = None,
                same_scans_tolerance_s: float = SAME_SCANS_TOLERANCE_S) -> dict:
    """Chạy bộ ghép trên một bản ghi (cùng đường mã với nguồn tư thế thật), ghi localization.csv, pose_estimator.json,
    overlay.png vào `out`. Trả báo cáo. `recording_path`: `.npz` hoặc thư mục bản ghi phiên (`read_lidar_any`).
    `same_scans_as`: xem docstring mô-đun; khi có, t đưa vào bộ ghép là t_perf_scan / t_first_perf của từng dòng (thiếu
    t_first_perf thì lấy t_first của bản ghi), vòng quét là vòng ghép được của bản ghi."""
    from .localize import load_map
    from .map_builder import read_map_build
    from .recording import git_commit, read_lidar_any
    from autopark.perception.paths import atomic_write_json, utc_now

    lmap = load_map(map_dir, config.localize)
    block = read_map_build(map_dir)
    recording = read_lidar_any(recording_path)
    t = np.asarray(recording.t, np.float64)
    t_first = np.asarray(recording.t_first, np.float64)
    same = None
    if same_scans_as is not None:
        rows = read_same_scans(same_scans_as)
        indices, gaps = match_scan_times(t, [r.t for r in rows], same_scans_tolerance_s, name=Path(same_scans_as).name)
        times = [(r.t, float(t_first[i]) if r.t_first is None else r.t_first) for r, i in zip(rows, indices)]
        gap = np.abs(gaps)
        same = {"rows": len(rows), "tolerance_s": same_scans_tolerance_s,
                "max_gap_s": float(gap.max()) if len(gap) else None,
                "median_gap_s": float(np.median(gap)) if len(gap) else None,
                "time_source": "t_perf_scan, t_first_perf của localization.csv (như bộ ghép lúc chạy); vòng quét của "
                               "bản ghi ghép được"}
    else:
        indices = [i for i in range(len(t)) if t[i] - t[0] >= skip_seconds]
        if drop_every:
            indices = [i for k, i in enumerate(indices, 1) if k % drop_every != 0]
        times = [(float(t[i]), float(t_first[i])) for i in indices]
    if limit is not None:
        indices, times = indices[:limit], times[:limit]
    mount = LidarMount(0.0, 0.0, 0.0, basis="--sensor-frame: tư thế là của cảm biến") if sensor_frame else config.mount
    estimator = LidarPoseEstimator(lmap, config.localizer, mount=mount, odometry=config.odometry, self_mask=self_mask,
                                   hint=initial)
    steps = []
    previous = None
    for i, (t_scan, t_scan_first) in zip(indices, times):
        angles, ranges, _ = recording.beams(i)
        step = estimator.process(angles, ranges, t_scan, t_first=t_scan_first)
        step.phase = "run" if estimator.armed else "before_start"
        step.dropped_before = 0 if previous is None else max(0, i - previous - 1)
        previous = i
        steps.append(step)
        if estimator.state == TRACKING and not estimator.armed:
            estimator.arm()                       # như lúc bấm Bắt đầu đỗ: từ đây chốt dừng là chốt của lần chạy
    out.mkdir(parents=True, exist_ok=True)
    write_localization_csv(out / "localization.csv", [step_row(s) for s in steps])
    summary = summarize_steps(steps)
    summary["same_scans"] = same
    folder = Path(recording_path).is_dir()
    parts = None if not folder else [{"file": f"{recording.path.name}/{name}", "sha256": _sha256(recording.path / name)}
                                     for name in recording.meta.get("parts", [])]
    report = {"created_utc": utc_now(), "git_commit": git_commit(), "map": str(map_dir),
              "map_sha256": _sha256(Path(map_dir) / "costmap.json" if Path(map_dir).is_dir() else Path(map_dir)),
              "map_frame": block.get("frame"), "map_session_ready": block.get("session_ready"),
              "recording": str(recording_path), "recording_kind": "session_folder" if folder else "npz",
              "recording_sha256": None if folder else _sha256(recording.path), "recording_parts": parts,
              "recording_scans": len(recording),
              "config": None if config.path is None else str(config.path), "config_sha256": config.sha256,
              "sensor_frame": sensor_frame, "mount": mount.to_dict(),
              "initial_vehicle_pose": None if initial is None else {"x_m": initial.x, "y_m": initial.y,
                                                                    "yaw_deg": math.degrees(initial.yaw)},
              "skip_seconds": skip_seconds, "limit": limit, "drop_every": drop_every,
              "same_scans_as": None if same_scans_as is None else str(same_scans_as),
              "global_searches": estimator.global_searches, "odometry_restarts": estimator.odometry_restarts,
              "summary": summary,
              "note": "offline: bộ ghép được arm() ngay khi bắt được (như lúc bấm Bắt đầu đỗ); latency_s rỗng vì không "
                      "đo thời gian thực; a_ms, b_ms là thời gian tính của (a), (b)"}
    atomic_write_json(out / "pose_estimator.json", _clean(report))
    title = (f"{Path(recording_path).stem} on {Path(map_dir).name}\n"
             f"{summary['scans']} scans  " + "  ".join(f"{k} {v}" for k, v in sorted(summary["decisions"].items())))
    ok, data = cv2.imencode(".png", render_overlay(lmap, steps, title))
    if ok:
        (out / "overlay.png").write_bytes(data.tobytes())
    return report


def main(argv=None) -> int:
    from .pose_config import load_lidar_pose_config

    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("--map", type=Path, required=True, help="thư mục bản đồ (costmap.json) của map_builder")
    parser.add_argument("--recording", type=Path, required=True,
                        help=".npz của autopark.lidar.recording, hoặc thư mục bản ghi phiên (T3: mọi phần "
                             "lidar/part_*.npz)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=None, help="mặc định configs/dinh_vi_lidar_v0.json")
    parser.add_argument("--initial", type=float, nargs=3, metavar=("X", "Y", "YAW_DEG"), default=None,
                        help="tư thế gợi ý lúc khởi tạo (của XE; với --sensor-frame: của cảm biến)")
    parser.add_argument("--sensor-frame", action="store_true", help="gá = 0: tư thế là của cảm biến (bản ghi trên bàn)")
    parser.add_argument("--vehicle-config", type=Path, default=None, help="bật mặt nạ thân xe với xe này")
    parser.add_argument("--skip-seconds", type=float, default=3.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--drop-every", type=int, default=None)
    parser.add_argument("--same-scans-as", type=Path, default=None,
                        help="localization.csv của một lần chạy: xử lý đúng các vòng của nó, so được từng dòng")
    parser.add_argument("--same-scans-tolerance-ms", type=float, default=None, metavar="MS",
                        help=f"dung sai ghép dòng với vòng của bản ghi (mặc định {SAME_SCANS_TOLERANCE_S * 1000:g} ms)")
    parser.add_argument("--fail-on-stop", action="store_true")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1 or args.drop_every is not None and args.drop_every < 2:
        parser.error("--limit phải ≥ 1, --drop-every phải ≥ 2")
    if args.same_scans_as is not None and args.drop_every is not None:
        parser.error("--same-scans-as và --drop-every không dùng cùng nhau")
    if args.same_scans_tolerance_ms is not None:
        if args.same_scans_as is None:
            parser.error("--same-scans-tolerance-ms chỉ dùng với --same-scans-as")
        if not 0.0 < args.same_scans_tolerance_ms <= 50.0:
            parser.error("--same-scans-tolerance-ms phải trong (0; 50] ms (dưới nửa chu kỳ vòng 10 Hz)")
    tolerance_s = (SAME_SCANS_TOLERANCE_S if args.same_scans_tolerance_ms is None
                   else args.same_scans_tolerance_ms / 1000.0)
    if args.same_scans_as is not None and not args.same_scans_as.is_file():
        parser.error(f"không có tệp {args.same_scans_as}")
    try:
        config = load_lidar_pose_config(args.config)
    except ValueError as exc:
        parser.error(str(exc))
    initial = None
    if args.initial is not None:
        if not all(math.isfinite(v) for v in args.initial):
            parser.error("--initial phải hữu hạn")
        initial = Pose(args.initial[0], args.initial[1], math.radians(args.initial[2]))
    vehicle = None
    if args.vehicle_config is not None:
        from autopark.storage.scenario_store import load_vehicle_config

        try:
            vehicle = load_vehicle_config(args.vehicle_config)
        except (OSError, ValueError, KeyError) as exc:
            parser.error(f"--vehicle-config: {exc}")
    if not (args.map.is_dir() and (args.map / "costmap.json").is_file() or args.map.is_file()):
        parser.error(f"không có bản đồ ở {args.map}")
    if not (args.recording.is_dir() or args.recording.with_suffix(".npz").is_file()):
        parser.error(f"không có bản ghi {args.recording}")
    try:
        report = run_offline(args.map, args.recording, args.out, config, initial=initial, sensor_frame=args.sensor_frame,
                             self_mask=vehicle, skip_seconds=args.skip_seconds, limit=args.limit,
                             drop_every=args.drop_every, same_scans_as=args.same_scans_as,
                             same_scans_tolerance_s=tolerance_s)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(_clean(report["summary"]), ensure_ascii=False))
    stopped = report["summary"]["first_stop"] is not None
    return 1 if (args.fail_on_stop and stopped) else 0


if __name__ == "__main__":
    sys.exit(main())
