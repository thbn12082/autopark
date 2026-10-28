r"""Dựng bản đồ tĩnh từ NHIỀU chỗ đặt LiDAR, trong hệ SA BÀN (thêm 02/10/2026, T2; docs/KIEN_TRUC.md
bước 1). Chưa phải SLAM: mỗi chỗ đặt là một đoạn bản ghi LiDAR ĐỨNG YÊN; chỗ đặt 1 được neo vào sa bàn, các chỗ sau
được ghép vào bản đồ đã có bằng định vị (`lidar/localize.py`), rồi mọi vòng quét được ray-cast vào một lưới đếm chung
(`lidar/occupancy.py`).

    .venv\Scripts\python.exe -X utf8 -m autopark.lidar.map_builder --placement A.npz --anchor X Y YAW_DEG --placement B.npz --scenario scenarios\sa_ban_3x2_hai_hop.json --out runs\lidar_maps\<ngay>_<ten>

Tùy chọn thêm vào cuối lệnh: [--pose K X Y YAW_DEG] (tư thế đo bằng thước của chỗ đặt K ≥ 2) [--hint K X Y YAW_DEG]
(gợi ý tư thế, cửa sổ ±0,5 m/±30°) [--trust-tape] [--anchor-vehicle X Y YAW_DEG] (tư thế XE, cần --lidar-config: cảm
biến = xe ⊕ gá) [--lidar-config configs\dinh_vi_lidar_v0.json] [--self-mask --vehicle-config configs\vehicle_default.json]
[--grid XMIN XMAX YMIN YMAX RES] [--skip-seconds S] [--max-range M] [--min-range M] [--overwrite]. Một chỗ đặt có thể là
một đoạn của bản ghi: `A.npz@T0:T1` (giây tính từ vòng đầu của bản ghi; bỏ trống một đầu là không giới hạn). Mọi tư thế
là tư thế TÂM QUAY LiDAR (m, m, độ) trong hệ sa bàn (gốc, trục như docs/KIEM_THU_VA_LO_TRINH.md).

Cách ghép chỗ đặt k ≥ 2: dựng bản đồ định vị từ các chỗ đặt trước; chọn điểm đoán theo thứ tự `--hint K`, `--pose K`,
odometry khớp scan (`lidar/scan_odometry.py`) qua đoạn bê LiDAR khi chỗ đặt k−1 và k là hai đoạn của CÙNG một bản ghi,
cuối cùng tìm toàn cục; định vị `register_scans` vòng trải đều của đoạn; nhận khi tỉ lệ OK ≥ 0,8 và độ tản quanh trung vị
≤ 2 cm / 0,5°. Có `--pose K` mà lệch kết quả ghép quá 5 cm / 2° thì TỪ CHỐI (trừ `--trust-tape`: dùng tư thế thước và
ghi độ lệch). Sau cùng kiểm "bỏ ra một" (leave-one-out): định vị lại từng chỗ đặt trên bản đồ dựng không có nó; OK mà
lệch quá 2 cm / 1° → từ chối; không OK (ít chồng lấp) → chỉ cảnh báo "không kiểm được". Mọi ngưỡng là ĐỀ XUẤT – CHỜ
CHỐT (`MapBuildConfig`).

Kết quả: costmap.json (khối costmap như `occupancy.py`, valid, gốc yaw 0, thêm khối "map_build": hệ "sa_ban", mốc neo,
từng chỗ đặt và cách ra tư thế, kiểm bỏ-ra-một, cờ mirror, thiết bị, sha256 đầu vào, commit git, cấu hình, sa bàn,
"session_ready"), map.png (vẽ cả chỗ đặt), counts.npz, placements.csv, map_build.json (báo cáo đủ). Bị từ chối: CHỈ ghi
map_build.json với ok = false, mã thoát 1. Dùng sai (mirror khác nhau giữa các bản ghi, `--pose 1`, `--anchor-vehicle`
thiếu `--lidar-config`, thư mục kết quả đã có mà không `--overwrite`, tệp không đọc được): mã thoát 2, không ghi gì.
Không có mốc neo: hệ "cam_bien_cho_dat_1", "session_ready": false (nguồn tư thế của phiên không nhận bản đồ này).

Độ đúng của bản đồ so với sa bàn phụ thuộc mốc neo: lệch 1° ở hướng neo thành 3,5 cm ở 2 m. Hướng neo nên đo bằng
thước thẳng ≥ 0,65 m (cách của N-L2). Mới kiểm trên vòng quét tổng hợp và bản ghi C1 đứng yên; CHƯA dựng bản đồ sa bàn
thật nào (02/10/2026).
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import math
from pathlib import Path
import sys

import cv2
import numpy as np

from autopark.domain.sensors import SourceStamp
from autopark.domain.types import Pose, VehicleConfig
from autopark.perception.costmap import OCCUPIED, GridSpec, costmap_to_dict, render, to_costmap
from autopark.perception.paths import atomic_write_json, utc_now

from .localize import LocalizationMap, LocalizeConfig, localize, wrap
from .occupancy import OccupancyCounts

SA_BAN_FRAME = "sa_ban"
SENSOR_FRAME = "cam_bien_cho_dat_1"
MAP_SOURCE_ID = "lidar_map_builder"


class MapBuildUsageError(ValueError):
    """Dùng sai (mã thoát 2, không ghi gì): đầu vào không đọc được, mirror khác nhau, tùy chọn mâu thuẫn."""


@dataclass(frozen=True)
class PlacementSpec:
    """Một chỗ đặt: bản ghi `.npz` (hoặc đoạn [t0_s, t1_s] của nó, giây từ vòng đầu). `tape_pose`/`hint_pose`: tư thế
    TÂM QUAY LiDAR (x m, y m, yaw rad) trong hệ sa bàn, đo bằng thước / gợi ý."""

    path: Path
    t0_s: float | None = None
    t1_s: float | None = None
    tape_pose: tuple[float, float, float] | None = None
    hint_pose: tuple[float, float, float] | None = None
    name: str = ""


@dataclass(frozen=True)
class MapBuildConfig:
    """Tham số dựng và ghép. Mọi ngưỡng là ĐỀ XUẤT – CHỜ CHỐT (02/10/2026)."""

    resolution: float = 0.05
    max_range: float = 8.0
    min_range: float = 0.25
    skip_seconds: float = 3.0              # bỏ lúc mô-tơ C1 khởi động (≈ 2,2 s tới vòng đầu)
    min_passes: int = 3
    min_hits: int = 2
    occupied_ratio: float = 0.2
    padding: float = 0.5
    register_scans: int = 5
    register_min_ok: float = 0.8
    register_max_spread: tuple[float, float] = (0.02, 0.5)       # m, độ quanh trung vị vòng
    tape_tol: tuple[float, float] = (0.05, 2.0)                  # m, độ: thước so với ghép
    loo_tol: tuple[float, float] = (0.02, 1.0)                   # m, độ: kiểm bỏ-ra-một
    hint_window: tuple[float, float, float] = (0.5, 0.5, 30.0)   # m, m, độ quanh gợi ý / thước
    odo_hint_window: tuple[float, float, float] = (0.3, 0.3, 20.0)

    def __post_init__(self):
        if not (self.resolution > 0 and 0 <= self.min_range < self.max_range and self.padding >= 0
                and self.skip_seconds >= 0 and 0 < self.register_min_ok <= 1):
            raise ValueError("cấu hình dựng bản đồ: resolution > 0, 0 ≤ min_range < max_range, padding ≥ 0, "
                             "skip_seconds ≥ 0, 0 < register_min_ok ≤ 1")
        if self.register_scans < 1 or self.min_passes < 1 or self.min_hits < 1:
            raise ValueError("cấu hình dựng bản đồ: register_scans, min_passes, min_hits phải ≥ 1")


@dataclass
class Registration:
    """Kết quả định vị các vòng của một chỗ đặt trên bản đồ: trung vị, độ tản, tỉ lệ OK."""

    tried: int
    ok: int
    pose: tuple[float, float, float] | None      # trung vị (vòng quanh) các vòng OK
    spread_m: float | None
    spread_deg: float | None
    statuses: list[str]
    reasons: list[str]

    @property
    def ok_share(self) -> float:
        return self.ok / self.tried if self.tried else 0.0

    def to_dict(self) -> dict:
        return {"tried": self.tried, "ok": self.ok, "ok_share": self.ok_share,
                "pose": _pose_dict(self.pose) if self.pose is not None else None,
                "spread_m": self.spread_m, "spread_deg": self.spread_deg, "statuses": self.statuses,
                "reasons": self.reasons}


@dataclass
class PlacementResult:
    index: int                                   # 1 = chỗ đặt neo
    name: str
    path: str
    t0_s: float | None
    t1_s: float | None
    scans: int = 0                               # số vòng của đoạn (sau skip_seconds)
    pose: tuple[float, float, float] | None = None   # tư thế cảm biến dùng để ray-cast (hệ bản đồ)
    pose_source: str = ""                        # anchor / registered / tape
    guess: str = ""                              # hint / tape / odometry_hint / global (chỗ đặt ≥ 2)
    guess_pose: tuple[float, float, float] | None = None
    registration: Registration | None = None
    tape_pose: tuple[float, float, float] | None = None
    tape_gap_m: float | None = None
    tape_gap_deg: float | None = None
    loo: dict | None = None
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"index": self.index, "name": self.name, "path": self.path, "t0_s": self.t0_s, "t1_s": self.t1_s,
                "scans": self.scans, "pose": _pose_dict(self.pose) if self.pose is not None else None,
                "pose_source": self.pose_source, "guess": self.guess,
                "guess_pose": _pose_dict(self.guess_pose) if self.guess_pose is not None else None,
                "registration": self.registration.to_dict() if self.registration is not None else None,
                "tape_pose": _pose_dict(self.tape_pose) if self.tape_pose is not None else None,
                "tape_gap_m": self.tape_gap_m, "tape_gap_deg": self.tape_gap_deg, "loo": self.loo,
                "meta": self.meta}


@dataclass
class MapBuildResult:
    ok: bool
    reasons_vi: list[str]
    warnings_vi: list[str]
    states: np.ndarray | None
    grid: GridSpec | None
    counts: OccupancyCounts | None
    placements: list[PlacementResult]
    frame: str
    anchor: tuple[float, float, float] | None
    meta: dict = field(default_factory=dict)

    @property
    def session_ready(self) -> bool:
        return self.ok and self.frame == SA_BAN_FRAME

    def report(self) -> dict:
        return _clean({"ok": self.ok, "reasons": self.reasons_vi, "warnings": self.warnings_vi, "frame": self.frame,
                       "anchor": _pose_dict(self.anchor) if self.anchor is not None else None,
                       "session_ready": self.session_ready,
                       "placements": [p.to_dict() for p in self.placements],
                       "grid": None if self.grid is None else self.grid.__dict__,
                       "summary": (None if self.counts is None or self.states is None
                                   else self.counts.summary(self.states)), **self.meta})


# ------------------------------------------------------------------------------------------------------- tiện ích
def _pose_dict(pose) -> dict:
    return {"x_m": float(pose[0]), "y_m": float(pose[1]), "yaw_deg": math.degrees(float(pose[2]))}


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_placement(text: str) -> PlacementSpec:
    """`đường_dẫn[@T0:T1]` → `PlacementSpec` (T0, T1 giây tính từ vòng đầu của bản ghi; bỏ trống = không giới hạn)."""
    path, t0, t1 = text, None, None
    if "@" in text:
        path, window = text.rsplit("@", 1)
        if ":" not in window:
            raise ValueError(f"đoạn bản ghi phải có dạng @T0:T1 (nhận {text!r})")
        a, b = window.split(":", 1)
        try:
            t0 = float(a) if a.strip() else None
            t1 = float(b) if b.strip() else None
        except ValueError as exc:
            raise ValueError(f"T0, T1 của {text!r} phải là số giây") from exc
        if (t0 is not None and not math.isfinite(t0)) or (t1 is not None and not math.isfinite(t1)) \
                or (t0 is not None and t1 is not None and t1 <= t0):
            raise ValueError(f"cần T0 < T1 hữu hạn (nhận {text!r})")
    return PlacementSpec(Path(path), t0, t1, name=Path(path).stem + ("" if "@" not in text else "@" + text.rsplit("@", 1)[1]))


def _snap_down(v: float, res: float) -> float:
    return math.floor(v / res + 1e-9) * res


def _snap_up(v: float, res: float) -> float:
    return math.ceil(v / res - 1e-9) * res


def auto_grid(world_points, res: float, padding: float) -> GridSpec:
    """Lưới thẳng trục (gốc yaw 0) bao mọi điểm (N, 2) cộng lề `padding`, mép là bội số của `res`."""
    pts = np.asarray(world_points, np.float64).reshape(-1, 2)
    pts = pts[np.all(np.isfinite(pts), axis=1)]
    if len(pts) == 0:
        raise ValueError("không có điểm nào để dựng lưới")
    lo, hi = pts.min(axis=0) - padding, pts.max(axis=0) + padding
    x0, y0 = _snap_down(lo[0], res), _snap_down(lo[1], res)
    x1, y1 = max(_snap_up(hi[0], res), x0 + res), max(_snap_up(hi[1], res), y0 + res)
    cols, rows = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
    return GridSpec(x0, x0 + cols * res, y0, y0 + rows * res, res)


class _Beams:
    __slots__ = ("angles_rad", "ranges_m")

    def __init__(self, angles, ranges):
        self.angles_rad, self.ranges_m = angles, ranges


def _hit_points(angles, ranges, pose, max_range: float) -> np.ndarray:
    a = np.asarray(angles, np.float64) + float(pose[2])
    r = np.asarray(ranges, np.float64)
    ok = np.isfinite(r) & (r > 0) & (r <= max_range)
    return np.column_stack([pose[0] + r[ok] * np.cos(a[ok]), pose[1] + r[ok] * np.sin(a[ok])])


def build_map_from_poses(scans_with_sensor_poses, grid: GridSpec | None, config: MapBuildConfig
                         ) -> tuple[OccupancyCounts, np.ndarray, GridSpec]:
    """Ray-cast mọi ((góc, tầm), tư thế cảm biến (x, y, yaw)) vào một lưới đếm; `grid` None → `auto_grid` của mọi điểm
    chạm và vị trí cảm biến. Trả (lưới đếm, trạng thái ô, lưới). Dùng cho bản đồ của LiDAR mô phỏng và test DROW."""
    items = [((np.asarray(a, np.float64), np.asarray(r, np.float64)), tuple(float(v) for v in pose))
             for (a, r), pose in scans_with_sensor_poses]
    if grid is None:
        points = [np.array([[p[0], p[1]]]) for _, p in items]
        points += [_hit_points(a, r, p, config.max_range) for (a, r), p in items]
        grid = auto_grid(np.vstack(points), config.resolution, config.padding)
    counts = OccupancyCounts(grid)
    for (angles, ranges), pose in items:
        counts.add_scan(_Beams(angles, ranges), pose, max_range=config.max_range, min_range=config.min_range)
    states = counts.states(min_passes=config.min_passes, min_hits=config.min_hits,
                           occupied_ratio=config.occupied_ratio)
    return counts, states, grid


def _circular_median(poses: np.ndarray) -> tuple[float, float, float]:
    th = poses[:, 2]
    mean = math.atan2(float(np.sin(th).mean()), float(np.cos(th).mean()))
    dev = wrap(th - mean)
    return float(np.median(poses[:, 0])), float(np.median(poses[:, 1])), float(wrap(mean + float(np.median(dev))))


def _gap(a, b) -> tuple[float, float]:
    """(m, độ) giữa hai tư thế."""
    return math.hypot(a[0] - b[0], a[1] - b[1]), abs(math.degrees(float(wrap(a[2] - b[2]))))


# ------------------------------------------------------------------------------------------------- đoạn bản ghi
@dataclass
class _Slice:
    spec: PlacementSpec
    index: int
    recording: object
    indices: list[int]

    def beams(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        angles, ranges, _ = self.recording.beams(i)
        return np.asarray(angles, np.float64), np.asarray(ranges, np.float64)

    @property
    def resolved(self) -> Path:
        return Path(self.recording.path).resolve()

    def picks(self, count: int) -> list[int]:
        if len(self.indices) <= count:
            return list(self.indices)
        positions = np.linspace(0, len(self.indices) - 1, count)
        return [self.indices[int(round(p))] for p in positions]


def _load_slices(specs, config: MapBuildConfig) -> list[_Slice]:
    from .recording import read_recording

    cache: dict[Path, object] = {}
    slices = []
    for k, spec in enumerate(specs, 1):
        path = Path(spec.path)
        try:
            key = path.with_suffix(".npz").resolve()
            recording = cache.get(key)
            if recording is None:
                recording = cache[key] = read_recording(path)
        except (OSError, ValueError, KeyError) as exc:
            raise MapBuildUsageError(f"chỗ đặt {k}: không đọc được {path}: {exc}") from exc
        t = np.asarray(recording.t, np.float64)
        rel = t - t[0] if len(t) else t
        keep = rel >= config.skip_seconds - 1e-9
        if spec.t0_s is not None:
            keep &= rel >= spec.t0_s - 1e-9
        if spec.t1_s is not None:
            keep &= rel <= spec.t1_s + 1e-9
        indices = [int(i) for i in np.nonzero(keep)[0]]
        if not indices:
            raise MapBuildUsageError(f"chỗ đặt {k} ({path.name}): không còn vòng quét nào sau khi bỏ "
                                     f"{config.skip_seconds:g} s đầu và cắt đoạn")
        slices.append(_Slice(spec, k, recording, indices))
    mirrors = {s.index: s.recording.meta.get("mirror") for s in slices}
    if len(set(map(repr, mirrors.values()))) > 1:
        raise MapBuildUsageError("các bản ghi có cờ mirror (đảo chiều góc) khác nhau: " +
                                 ", ".join(f"chỗ đặt {k}: {v!r}" for k, v in mirrors.items()) +
                                 "; ghép như vậy cho bản đồ sai, ghi lại cùng một chiều góc")
    return slices


# ------------------------------------------------------------------------------------------------------ dựng bản đồ
class _Builder:
    """Lưới đếm riêng cho từng chỗ đặt trên một lưới chung; nới lưới (ray-cast lại) khi chỗ đặt mới ra gần mép."""

    def __init__(self, config: MapBuildConfig, localize_config: LocalizeConfig, fixed_grid: GridSpec | None,
                 mask=None):
        self.config, self.lcfg, self.fixed_grid, self.mask = config, localize_config, fixed_grid, mask
        self.grid: GridSpec | None = fixed_grid
        self.placed: list[tuple[_Slice, tuple[float, float, float]]] = []
        self.counts: list[OccupancyCounts] = []

    def _reach(self) -> float:
        return self.config.max_range + self.config.padding

    def _grid_for(self, poses) -> GridSpec:
        pts = np.array([[p[0], p[1]] for p in poses], np.float64)
        return auto_grid(np.vstack([pts - self._reach(), pts + self._reach()]), self.config.resolution, 0.0)

    def _covers(self, pose) -> bool:
        g, r = self.grid, self._reach()
        return (g is not None and g.x_min <= pose[0] - r and pose[0] + r <= g.x_max and g.y_min <= pose[1] - r
                and pose[1] + r <= g.y_max)

    def _raycast(self, sl: _Slice, pose) -> OccupancyCounts:
        cfg = self.config
        counts = OccupancyCounts(self.grid)
        for i in sl.indices:
            angles, ranges = sl.beams(i)
            if self.mask is not None:
                ranges = self.mask(angles, ranges)
            counts.add_scan(_Beams(angles, ranges), pose, max_range=cfg.max_range, min_range=cfg.min_range)
        return counts

    def add(self, sl: _Slice, pose) -> None:
        pose = tuple(float(v) for v in pose)
        self.placed.append((sl, pose))
        if self.fixed_grid is None and not self._covers(pose):
            self.grid = self._grid_for([p for _, p in self.placed])
            self.counts = [self._raycast(s, p) for s, p in self.placed]
        else:
            self.counts.append(self._raycast(sl, pose))

    def counts_without(self, skip: int | None = None) -> OccupancyCounts:
        total = OccupancyCounts(self.grid)
        for k, c in enumerate(self.counts):
            if k != skip:
                total.passes += c.passes
                total.hits += c.hits
                total.scans += c.scans
                total.beams_used += c.beams_used
        return total

    def states(self, counts: OccupancyCounts) -> np.ndarray:
        cfg = self.config
        return counts.states(min_passes=cfg.min_passes, min_hits=cfg.min_hits, occupied_ratio=cfg.occupied_ratio)

    def lmap(self, skip: int | None = None, *, levels: int | None = None) -> LocalizationMap | None:
        states = self.states(self.counts_without(skip))
        if not (states == OCCUPIED).any():
            return None
        lcfg = self.lcfg if levels is None else replace(self.lcfg, levels=levels)
        return LocalizationMap(states, self.grid, lcfg, source="map_builder")


def _register(lmap: LocalizationMap, sl: _Slice, guess, window, config: MapBuildConfig, mask=None) -> Registration:
    """Định vị `register_scans` vòng trải đều của đoạn quanh `guess` trong `window` (m, m, rad)."""
    poses, statuses, reasons = [], [], []
    picks = sl.picks(config.register_scans)
    for i in picks:
        angles, ranges = sl.beams(i)
        if mask is not None:
            ranges = mask(angles, ranges)
        result = localize(lmap, angles, ranges, guess, window=window)
        statuses.append(result.status)
        reasons.append("+".join(result.reasons))
        if result.ok:
            poses.append((result.x, result.y, result.theta))
    if not poses:
        return Registration(len(picks), 0, None, None, None, statuses, reasons)
    arr = np.array(poses, np.float64)
    median = _circular_median(arr)
    spread_m = float(np.max(np.hypot(arr[:, 0] - median[0], arr[:, 1] - median[1])))
    spread_deg = float(np.max(np.abs(np.degrees(wrap(arr[:, 2] - median[2])))))
    return Registration(len(picks), len(poses), median, spread_m, spread_deg, statuses, reasons)


def _accepted(reg: Registration, config: MapBuildConfig) -> bool:
    return (reg.pose is not None and reg.ok_share >= config.register_min_ok - 1e-9
            and reg.spread_m <= config.register_max_spread[0] + 1e-12
            and reg.spread_deg <= config.register_max_spread[1] + 1e-12)


def _window(values) -> tuple[float, float, float]:
    return float(values[0]), float(values[1]), math.radians(float(values[2]))


def _odometry_hint(prev: _Slice, prev_pose, sl: _Slice):
    """Tư thế đoán của chỗ đặt `sl` từ odometry khớp scan qua đoạn bê LiDAR giữa vòng cuối của `prev` và vòng đầu của
    `sl` (cùng một bản ghi); None khi odometry hỏng giữa chừng hay hai đoạn không nối tiếp."""
    from .scan_odometry import FAILED as ODO_FAILED, OdometryConfig, ScanOdometry, compose

    start, stop = prev.indices[-1], sl.indices[0]
    if stop <= start:
        return None
    odometry = ScanOdometry(OdometryConfig(velocity_per="second"))
    recording = sl.recording
    for i in range(start, stop + 1):
        angles, ranges, _ = recording.beams(i)
        step = odometry.update(np.asarray(angles, np.float64), np.asarray(ranges, np.float64),
                               float(recording.t[i] - recording.t[0]))
        if step.status == ODO_FAILED and "lost" in step.reasons:
            return None
    last = odometry.steps[-1]
    if last.status == ODO_FAILED:
        return None
    return tuple(float(v) for v in compose(prev_pose, last.pose))


def build_static_map(specs, *, anchor=None, config: MapBuildConfig | None = None, mount=None,
                     self_mask: VehicleConfig | None = None, mask_margin: float = 0.03,
                     localize_config: LocalizeConfig | None = None, trust_tape: bool = False,
                     grid: GridSpec | None = None, scenario=None) -> MapBuildResult:
    """Dựng bản đồ từ các chỗ đặt `specs` (thứ tự = số chỗ đặt). `anchor`: tư thế CẢM BIẾN (x, y, yaw rad) của chỗ đặt 1
    trong hệ sa bàn; None → hệ của chính chỗ đặt 1 (bản đồ không dùng được cho phiên). `self_mask` + `mount`: bỏ phản hồi
    rơi vào thân xe (gá + thân + lề `mask_margin`). Đầu vào hỏng → `MapBuildUsageError`; không ghép được → kết quả
    ok = False với lý do tiếng Việt."""
    config = config or MapBuildConfig()
    lcfg = localize_config or LocalizeConfig(min_range_m=config.min_range, max_range_m=config.max_range)
    specs = list(specs)
    if not specs:
        raise MapBuildUsageError("cần ít nhất một chỗ đặt")
    if specs[0].tape_pose is not None or specs[0].hint_pose is not None:
        raise MapBuildUsageError("chỗ đặt 1 là mốc neo: dùng --anchor/--anchor-vehicle, không dùng --pose/--hint 1")
    slices = _load_slices(specs, config)
    mask = None
    if self_mask is not None:
        if mount is None:
            raise MapBuildUsageError("mặt nạ thân xe cần gá LiDAR (--lidar-config)")
        from autopark.fusion.layers import body_mask

        mount_tuple = mount.as_tuple()

        def mask(angles, ranges):
            drop = body_mask(angles, ranges, mount_tuple, self_mask, mask_margin)
            out = np.array(ranges, np.float64, copy=True)
            out[drop] = np.nan
            return out

    frame = SA_BAN_FRAME if anchor is not None else SENSOR_FRAME
    anchor_pose = tuple(float(v) for v in anchor) if anchor is not None else (0.0, 0.0, 0.0)
    builder = _Builder(config, lcfg, grid, mask)
    results: list[PlacementResult] = []
    reasons: list[str] = []
    warnings: list[str] = []
    meta = _inputs_meta(slices, config, lcfg, scenario, mount, trust_tape)
    for sl in slices:
        spec = sl.spec
        res = PlacementResult(sl.index, spec.name or Path(spec.path).stem, str(spec.path), spec.t0_s, spec.t1_s,
                              len(sl.indices), tape_pose=spec.tape_pose, meta=_recording_meta(sl.recording))
        results.append(res)
        if sl.index == 1:
            res.pose, res.pose_source = anchor_pose, "anchor"
            builder.add(sl, anchor_pose)
            continue
        lmap = builder.lmap()
        if lmap is None:
            reasons.append(f"Không ghép được chỗ đặt {sl.index}: bản đồ từ các chỗ đặt trước không có ô OCCUPIED nào")
            break
        guess, window, how = None, None, ""
        if spec.hint_pose is not None:
            guess, window, how = spec.hint_pose, _window(config.hint_window), "hint"
        elif spec.tape_pose is not None:
            guess, window, how = spec.tape_pose, _window(config.hint_window), "tape"
        else:
            prev, prev_pose = slices[sl.index - 2], results[sl.index - 2].pose
            if prev.resolved == sl.resolved and prev_pose is not None:
                odo = _odometry_hint(prev, prev_pose, sl)
                if odo is not None:
                    guess, window, how = odo, _window(config.odo_hint_window), "odometry_hint"
        if guess is None:
            gmap = builder.lmap(levels=5)
            first = sl.picks(1)[0]
            angles, ranges = sl.beams(first)
            if mask is not None:
                ranges = mask(angles, ranges)
            found = localize(gmap, angles, ranges, (0.0, 0.0, 0.0), global_search=True)
            how = "global"
            if not found.ok:
                res.guess = how
                reasons.append(f"Không ghép được chỗ đặt {sl.index}: tìm toàn cục không ra tư thế OK "
                               f"({found.status}: {'+'.join(found.reasons) or '—'}); thêm --hint {sl.index} X Y "
                               f"YAW_DEG hoặc --pose {sl.index} …")
                break
            guess, window = (found.x, found.y, found.theta), _window(config.hint_window)
        res.guess, res.guess_pose = how, tuple(float(v) for v in guess)
        reg = _register(lmap, sl, guess, window, config, mask)
        res.registration = reg
        if not _accepted(reg, config):
            detail = (f"{reg.ok}/{reg.tried} vòng OK (cần ≥ {config.register_min_ok:.0%})" if reg.pose is None
                      or reg.ok_share < config.register_min_ok - 1e-9 else
                      f"độ tản {reg.spread_m * 100:.1f} cm / {reg.spread_deg:.2f}° (cho phép "
                      f"{config.register_max_spread[0] * 100:.0f} cm / {config.register_max_spread[1]:g}°)")
            reasons.append(f"Không ghép được chỗ đặt {sl.index}: {detail}; trạng thái {', '.join(reg.statuses)}")
            break
        pose = reg.pose
        res.pose_source = "registered"
        if spec.tape_pose is not None:
            gap_m, gap_deg = _gap(spec.tape_pose, reg.pose)
            res.tape_gap_m, res.tape_gap_deg = gap_m, gap_deg
            if gap_m > config.tape_tol[0] or gap_deg > config.tape_tol[1]:
                if not trust_tape:
                    reasons.append(f"Chỗ đặt {sl.index}: tư thế đo bằng thước lệch kết quả ghép {gap_m * 100:.1f} cm / "
                                   f"{gap_deg:.2f}° (cho phép {config.tape_tol[0] * 100:.0f} cm / "
                                   f"{config.tape_tol[1]:g}°); đo lại, hoặc --trust-tape để dùng tư thế thước")
                    break
                warnings.append(f"Chỗ đặt {sl.index}: dùng tư thế thước (--trust-tape) dù lệch kết quả ghép "
                                f"{gap_m * 100:.1f} cm / {gap_deg:.2f}°")
                pose, res.pose_source = spec.tape_pose, "tape"
        res.pose = tuple(float(v) for v in pose)
        builder.add(sl, res.pose)
    ok = not reasons
    if ok and len(builder.placed) >= 2:
        _leave_one_out(builder, results, config, mask, reasons, warnings)
        ok = not reasons
    counts = builder.counts_without() if builder.counts else None
    states = builder.states(counts) if counts is not None else None
    out_grid = builder.grid
    if ok and counts is not None and grid is None:
        counts, states, out_grid = _crop(counts, states, config)
    return MapBuildResult(ok, reasons, warnings, states if ok else None, out_grid if ok else None,
                          counts if ok else None, results, frame, anchor_pose if anchor is not None else None, meta)


def _leave_one_out(builder: _Builder, results: list[PlacementResult], config: MapBuildConfig, mask,
                   reasons: list[str], warnings: list[str]) -> None:
    """Định vị lại từng chỗ đặt trên bản đồ dựng không có nó. OK mà lệch quá `loo_tol` → từ chối; trừ khi có chỗ đặt
    dùng tư thế thước được tin (`--trust-tape`): khi đó người dùng đã nhận rủi ro, độ lệch thành cảnh báo (bản đồ không
    nhất quán với thước là đúng điều đã biết lúc ghép)."""
    tape_trusted = any(p.pose_source == "tape" for p in results)
    for k, (sl, pose) in enumerate(builder.placed):
        res = results[k]
        lmap = builder.lmap(skip=k)
        if lmap is None:
            res.loo = {"checked": False, "note": "bản đồ không có chỗ đặt này không có ô OCCUPIED nào"}
            warnings.append(f"Chỗ đặt {sl.index}: không kiểm được bỏ-ra-một (bản đồ còn lại rỗng)")
            continue
        reg = _register(lmap, sl, pose, _window(config.hint_window), config, mask)
        if not (reg.pose is not None and reg.ok_share >= config.register_min_ok - 1e-9):
            res.loo = {"checked": False, "registration": reg.to_dict(),
                       "note": "không OK trên bản đồ còn lại (ít chồng lấp): không kiểm được"}
            warnings.append(f"Chỗ đặt {sl.index}: không kiểm được bỏ-ra-một ({reg.ok}/{reg.tried} vòng OK trên bản đồ "
                            f"không có nó)")
            continue
        gap_m, gap_deg = _gap(reg.pose, pose)
        res.loo = {"checked": True, "registration": reg.to_dict(), "gap_m": gap_m, "gap_deg": gap_deg,
                   "ok": gap_m <= config.loo_tol[0] and gap_deg <= config.loo_tol[1]}
        if not res.loo["ok"]:
            text = (f"Bỏ-ra-một: chỗ đặt {sl.index} định vị trên bản đồ không có nó lệch {gap_m * 100:.1f} cm / "
                    f"{gap_deg:.2f}° so với tư thế đã dùng (cho phép {config.loo_tol[0] * 100:.0f} cm / "
                    f"{config.loo_tol[1]:g}°): bản đồ không nhất quán")
            (warnings if tape_trusted else reasons).append(text + (" (--trust-tape: chỉ cảnh báo)" if tape_trusted
                                                                   else ""))


def _crop(counts: OccupancyCounts, states: np.ndarray, config: MapBuildConfig):
    """Cắt lưới về vùng đã quan sát (đi qua hoặc chạm) cộng lề `padding`."""
    observed = (counts.passes + counts.hits) > 0
    if not observed.any():
        return counts, states, counts.grid
    g, res = counts.grid, counts.grid.resolution
    rows, cols = np.nonzero(observed)
    pad = int(math.ceil(config.padding / res - 1e-9))
    r0, r1 = max(0, rows.min() - pad), min(g.shape[0], rows.max() + 1 + pad)
    c0, c1 = max(0, cols.min() - pad), min(g.shape[1], cols.max() + 1 + pad)
    grid = GridSpec(g.x_min + c0 * res, g.x_min + c1 * res, g.y_min + r0 * res, g.y_min + r1 * res, res)
    out = OccupancyCounts(grid)
    out.passes[:] = counts.passes[r0:r1, c0:c1]
    out.hits[:] = counts.hits[r0:r1, c0:c1]
    out.scans, out.beams_used = counts.scans, counts.beams_used
    return out, states[r0:r1, c0:c1].copy(), grid


def _recording_meta(recording) -> dict:
    meta = recording.meta or {}
    keep = ("source_id", "started_utc", "name", "note", "placement", "mirror", "device", "driver", "driver_version",
            "port", "clock")
    return {key: meta.get(key) for key in keep if key in meta}


def _inputs_meta(slices, config, lcfg, scenario, mount, trust_tape) -> dict:
    from .recording import git_commit

    files = {}
    for sl in slices:
        path = Path(sl.recording.path)
        if str(path) not in files:
            files[str(path)] = _sha256(path)
    mirrors = {sl.recording.meta.get("mirror") for sl in slices}
    return {"inputs_sha256": files, "mirror": next(iter(mirrors)) if len(mirrors) == 1 else None,
            "git_commit": git_commit(), "config": asdict(config), "localize_config": asdict(lcfg),
            "trust_tape": trust_tape, "mount": mount.to_dict() if mount is not None else None,
            "scenario": None if scenario is None else {"name": scenario.name, "bounds": scenario.bounds.to_dict()},
            "created_utc": utc_now(),
            "method": "multi-placement static map: placement 1 anchored in the sa_ban frame; later placements "
                      "registered on the map of earlier ones (localize.py correlative search + LM) from a hint, a "
                      "tape pose, scan odometry over the carry, or a global search; ray casting per beam "
                      "(occupancy.py); leave-one-out consistency check; thresholds ĐỀ XUẤT – CHỜ CHỐT; not SLAM"}


# ------------------------------------------------------------------------------------------------------------ ghi
PLACEMENT_FIELDS = ("index", "name", "path", "t0_s", "t1_s", "scans", "pose_source", "guess", "x_m", "y_m", "yaw_deg",
                    "reg_ok", "reg_tried", "reg_spread_m", "reg_spread_deg", "tape_x_m", "tape_y_m", "tape_yaw_deg",
                    "tape_gap_m", "tape_gap_deg", "loo_checked", "loo_gap_m", "loo_gap_deg")


def _placement_row(p: PlacementResult) -> list:
    def num(value, fmt):
        return "" if value is None or not math.isfinite(value) else format(value, fmt)

    reg, loo = p.registration, p.loo or {}
    pose = p.pose or (None, None, None)
    tape = p.tape_pose or (None, None, None)
    return [p.index, p.name, p.path, num(p.t0_s, ".3f"), num(p.t1_s, ".3f"), p.scans, p.pose_source, p.guess,
            num(pose[0], ".4f"), num(pose[1], ".4f"), num(None if pose[2] is None else math.degrees(pose[2]), ".3f"),
            "" if reg is None else reg.ok, "" if reg is None else reg.tried,
            "" if reg is None else num(reg.spread_m, ".4f"), "" if reg is None else num(reg.spread_deg, ".3f"),
            num(tape[0], ".4f"), num(tape[1], ".4f"), num(None if tape[2] is None else math.degrees(tape[2]), ".3f"),
            num(p.tape_gap_m, ".4f"), num(p.tape_gap_deg, ".3f"), "" if not loo else int(bool(loo.get("checked"))),
            num(loo.get("gap_m"), ".4f"), num(loo.get("gap_deg"), ".3f")]


def render_map(result: MapBuildResult) -> np.ndarray:
    """Ảnh bản đồ (như `costmap.render`: x lên trên, y sang trái) kèm chỗ đặt: chấm xanh dương + vạch hướng, số chỗ
    đặt. Chữ ASCII (phông Hershey không có dấu tiếng Việt)."""
    grid, states = result.grid, result.states
    scale = max(1, int(600 / max(states.shape)))
    canvas = render(states, grid, None, None, scale=scale)

    def px(x, y):
        return int((grid.y_max - y) / grid.resolution * scale), int((grid.x_max - x) / grid.resolution * scale)

    for p in result.placements:
        if p.pose is None:
            continue
        x, y, th = p.pose
        tip = px(x + 0.3 * math.cos(th), y + 0.3 * math.sin(th))
        cv2.line(canvas, px(x, y), tip, (255, 60, 0), 2)
        cv2.circle(canvas, px(x, y), 5, (0, 0, 0), -1)
        cv2.circle(canvas, px(x, y), 4, (255, 60, 0), -1)
        cv2.putText(canvas, str(p.index), (px(x, y)[0] + 6, px(x, y)[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (255, 255, 255), 1, cv2.LINE_AA)
    lines = [f"frame {result.frame}  placements {len(result.placements)}  session_ready {result.session_ready}",
             "blue = LiDAR placement (sensor pose), line = sensor +x"]
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1] - 1, 17 * len(lines) + 4), (40, 40, 40), -1)
    for k, line in enumerate(lines):
        cv2.putText(canvas, line, (6, 16 + 17 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    return canvas


def _write_png(path: Path, image: np.ndarray) -> None:
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"không mã hóa được {path.name}")
    path.write_bytes(data.tobytes())


def write_map(result: MapBuildResult, out: Path, *, argv=None, scenario_path=None) -> Path:
    """Ghi kết quả vào `out` (đã kiểm ở `main`). Bị từ chối: chỉ map_build.json. Trả đường dẫn costmap.json (hoặc
    map_build.json khi bị từ chối)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    report = result.report()
    report.update(argv=list(argv) if argv is not None else None,
                  scenario_path=None if scenario_path is None else str(scenario_path))
    atomic_write_json(out / "map_build.json", _clean(report))
    if not result.ok:
        return out / "map_build.json"
    costmap = to_costmap(result.states, result.grid, SourceStamp(MAP_SOURCE_ID, 0.0, True, "map"))
    block = {key: report[key] for key in ("frame", "anchor", "session_ready", "placements", "warnings", "mirror",
                                          "inputs_sha256", "git_commit", "config", "scenario", "created_utc",
                                          "trust_tape", "mount")}
    block["placements"] = [{key: p.get(key) for key in ("index", "name", "path", "t0_s", "t1_s", "scans", "pose",
                                                         "pose_source", "guess", "registration", "tape_pose",
                                                         "tape_gap_m", "tape_gap_deg", "loo", "meta")}
                           for p in report["placements"]]
    atomic_write_json(out / "costmap.json", _clean({
        "created_utc": utc_now(), "source": "autopark.lidar.map_builder", "grid": result.grid.__dict__,
        "summary": result.counts.summary(result.states), "method": report["method"], "map_build": block,
        "costmap": costmap_to_dict(costmap)}))
    _write_png(out / "map.png", render_map(result))
    np.savez_compressed(out / "counts.npz", passes=result.counts.passes, hits=result.counts.hits)
    with (out / "placements.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(PLACEMENT_FIELDS)
        for p in result.placements:
            writer.writerow(_placement_row(p))
    return out / "costmap.json"


def read_map_build(path) -> dict:
    """Khối "map_build" của costmap.json (hoặc của thư mục chứa nó); {} khi bản đồ không do công cụ này dựng."""
    path = Path(path)
    if path.is_dir():
        path = path / "costmap.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    block = data.get("map_build") if isinstance(data, dict) else None
    return block if isinstance(block, dict) else {}


# ------------------------------------------------------------------------------------------------------------- CLI
def _pose_args(values) -> tuple[float, float, float]:
    x, y, yaw_deg = (float(v) for v in values)
    if not all(math.isfinite(v) for v in (x, y, yaw_deg)):
        raise ValueError("tư thế phải hữu hạn")
    return x, y, math.radians(yaw_deg)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("--placement", action="append", default=[], metavar="NPZ[@T0:T1]",
                        help="một chỗ đặt (theo thứ tự: chỗ đặt 1 là mốc neo)")
    anchor = parser.add_mutually_exclusive_group()
    anchor.add_argument("--anchor", type=float, nargs=3, metavar=("X", "Y", "YAW_DEG"),
                        help="tư thế CẢM BIẾN của chỗ đặt 1 trong hệ sa bàn")
    anchor.add_argument("--anchor-vehicle", type=float, nargs=3, metavar=("X", "Y", "YAW_DEG"),
                        help="tư thế XE (tâm trục sau) của chỗ đặt 1; cảm biến = xe ⊕ gá (--lidar-config)")
    parser.add_argument("--pose", type=float, nargs=4, action="append", default=[], metavar=("K", "X", "Y", "YAW_DEG"),
                        help="tư thế cảm biến đo bằng thước của chỗ đặt K ≥ 2")
    parser.add_argument("--hint", type=float, nargs=4, action="append", default=[], metavar=("K", "X", "Y", "YAW_DEG"),
                        help="gợi ý tư thế cảm biến của chỗ đặt K ≥ 2")
    parser.add_argument("--trust-tape", action="store_true", help="dùng tư thế thước kể cả khi lệch kết quả ghép")
    parser.add_argument("--grid", type=float, nargs=5, metavar=("XMIN", "XMAX", "YMIN", "YMAX", "RES"), default=None)
    parser.add_argument("--skip-seconds", type=float, default=MapBuildConfig.skip_seconds)
    parser.add_argument("--max-range", type=float, default=MapBuildConfig.max_range)
    parser.add_argument("--min-range", type=float, default=MapBuildConfig.min_range)
    parser.add_argument("--self-mask", action="store_true", help="bỏ phản hồi rơi vào thân xe (cần --lidar-config, "
                                                                 "--vehicle-config)")
    parser.add_argument("--lidar-config", type=Path, default=None, help="configs/dinh_vi_lidar_v0.json (gá LiDAR)")
    parser.add_argument("--vehicle-config", type=Path, default=None)
    parser.add_argument("--scenario", type=Path, default=None, help="kịch bản sa bàn (ghi tên và biên vào bản đồ)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        specs = [parse_placement(text) for text in args.placement]
    except ValueError as exc:
        parser.error(str(exc))
    if not specs:
        parser.error("cần ít nhất một --placement")
    for option, values in (("--pose", args.pose), ("--hint", args.hint)):
        for item in values:
            k = item[0]
            if k != int(k) or not 1 <= int(k) <= len(specs):
                parser.error(f"{option} K: K phải là số chỗ đặt 1..{len(specs)} (nhận {k:g})")
            if int(k) == 1:
                parser.error(f"{option} 1: chỗ đặt 1 là mốc neo, dùng --anchor hoặc --anchor-vehicle")
            try:
                pose = _pose_args(item[1:])
            except ValueError as exc:
                parser.error(f"{option}: {exc}")
            field_name = "tape_pose" if option == "--pose" else "hint_pose"
            specs[int(k) - 1] = replace(specs[int(k) - 1], **{field_name: pose})
    config_file = None
    if args.anchor_vehicle is not None or args.self_mask:
        if args.lidar_config is None:
            parser.error("--anchor-vehicle và --self-mask cần --lidar-config (gá LiDAR trên xe)")
    if args.self_mask and args.vehicle_config is None:
        parser.error("--self-mask cần --vehicle-config (thân xe)")
    if args.lidar_config is not None:
        from .pose_config import load_lidar_pose_config

        try:
            config_file = load_lidar_pose_config(args.lidar_config)
        except ValueError as exc:
            parser.error(str(exc))
    vehicle = None
    if args.vehicle_config is not None:
        from autopark.storage.scenario_store import load_vehicle_config

        try:
            vehicle = load_vehicle_config(args.vehicle_config)
        except (OSError, ValueError, KeyError) as exc:
            parser.error(f"--vehicle-config: {exc}")
    scenario = None
    if args.scenario is not None:
        from autopark.storage.scenario_store import load_scenario

        try:
            scenario = load_scenario(args.scenario)
        except (OSError, ValueError, KeyError) as exc:
            parser.error(f"--scenario: {exc}")
    try:
        config = MapBuildConfig(skip_seconds=args.skip_seconds, max_range=args.max_range, min_range=args.min_range)
        grid = None if args.grid is None else GridSpec(*args.grid)
    except ValueError as exc:
        parser.error(str(exc))
    if args.grid is not None:
        config = replace(config, resolution=grid.resolution)
    anchor_pose = None
    try:
        if args.anchor is not None:
            anchor_pose = _pose_args(args.anchor)
        elif args.anchor_vehicle is not None:
            vehicle_pose = _pose_args(args.anchor_vehicle)
            sensor = config_file.mount.sensor_pose(Pose(*vehicle_pose))
            anchor_pose = (sensor.x, sensor.y, sensor.yaw)
    except ValueError as exc:
        parser.error(str(exc))
    if args.out.exists() and any(args.out.iterdir()) and not args.overwrite:
        parser.error(f"thư mục kết quả {args.out} đã có tệp: thêm --overwrite hoặc chọn thư mục khác")
    try:
        result = build_static_map(specs, anchor=anchor_pose, config=config,
                                  mount=config_file.mount if config_file is not None else None,
                                  self_mask=vehicle if args.self_mask else None,
                                  mask_margin=(config_file.localizer.self_mask_margin_m if config_file is not None
                                               else 0.03),
                                  trust_tape=args.trust_tape, grid=grid, scenario=scenario)
    except MapBuildUsageError as exc:
        parser.error(str(exc))
    if args.overwrite and args.out.exists():
        for name in ("costmap.json", "map.png", "counts.npz", "placements.csv", "map_build.json"):
            (args.out / name).unlink(missing_ok=True)
    path = write_map(result, args.out, argv=sys.argv[1:] if argv is None else argv, scenario_path=args.scenario)
    summary = {"ok": result.ok, "frame": result.frame, "session_ready": result.session_ready, "out": str(path),
               "reasons": result.reasons_vi, "warnings": result.warnings_vi,
               "placements": [{"index": p.index, "pose": None if p.pose is None else _pose_dict(p.pose),
                               "pose_source": p.pose_source, "guess": p.guess} for p in result.placements]}
    print(json.dumps(_clean(summary), ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
