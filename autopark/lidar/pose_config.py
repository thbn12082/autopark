"""Cấu hình nguồn tư thế LiDAR của phiên đỗ xe (thêm 02/10/2026, T2): gá LiDAR trên xe, điều kiện tiên quyết cho bo
thật, ngưỡng của bộ ghép định vị (a) + giám sát (b) và LiDAR mô phỏng. Đọc `configs/dinh_vi_lidar_v0.json`.

Người dùng giao quyết định 02/10/2026 ("làm hết"): làm theo ĐỀ XUẤT mục 7 của docs/KIEN_TRUC.md; mọi ngưỡng
ở đây vẫn là ĐỀ XUẤT – CHỜ CHỐT, dùng cho nghiệm thu tới khi chốt; gá LiDAR GIẢ ĐỊNH – CHƯA ĐO.

Đọc chặt theo kiểu `SimIOConfig.from_dict`: schema_version phải là 1; khóa lạ ở bất kỳ mức nào → ValueError tiếng Việt
nêu khóa; khóa vắng mặt lấy mặc định của dataclass (một bộ mặc định duy nhất, bằng tệp mặc định).

Hệ tọa độ của gá (như configs/tof_mounts_v0.json): gốc tại tâm trục sau, x hướng tiến, y sang trái, yaw ngược chiều
kim đồng hồ. Tư thế cảm biến trong hệ sa bàn = tư thế xe ⊕ gá (`LidarMount.sensor_pose`).

`unmet()` liệt kê điều còn thiếu để được chạy bo THẬT ở VehicleIO: gá chưa đo, điều kiện tiên quyết chưa đạt hoặc đạt
mà không có bằng chứng. `LidarPoseSource.start_gate` dùng danh sách này để từ chối (START_POSE_UNVERIFIED) trước mọi I/O.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
import hashlib
import json
import math
from pathlib import Path

from autopark.domain.types import Pose, wrap_angle
from autopark.perception.paths import PROJECT

from .localize import LocalizeConfig
from .scan_odometry import OdometryConfig

DEFAULT_PATH = PROJECT / "configs" / "dinh_vi_lidar_v0.json"
SCHEMA_VERSION = 1
# Ba điều kiện tiên quyết của SO_SANH mục 7 cho bo thật, theo thứ tự hiển thị → nhãn tiếng Việt
PREREQUISITE_LABELS = {
    "dau_goc_p04": "dấu góc trái/phải p04",
    "huong_goc_dv2": "hướng góc DV-2 (nguyên nhân lệch +4,3°)",
    "dinh_vi_tinh_dv1": "định vị tĩnh DV-1 so với thước",
}
# Odometry (b) của nguồn tư thế: vận tốc dự đoán theo GIÂY (vòng bị rơi không làm hỏng dự đoán, SO_SANH mục 3.3 phát
# hiện 6); mặc định của `OdometryConfig` (theo vòng) giữ nguyên cho công cụ offline cũ.
DEFAULT_ODOMETRY = OdometryConfig(velocity_per="second")
MOUNT_BASIS_DEFAULT = ("GIẢ ĐỊNH – CHƯA ĐO: tâm quay C1 giữa hai trục của xe giả định vehicle_default.json (trục cách "
                       "0,19 m), trên trục dọc, 0° = phía trước xe; chưa có MN300 và gá")


def _fail(where: str, problem: str):
    raise ValueError(f"Cấu hình định vị LiDAR{f' {where}' if where else ''}: {problem}")


def _number(value, name: str, where: str, *, positive: bool = False, minimum: float | None = None) -> float:
    """Số JSON hữu hạn (không nhận bool, chuỗi, null)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(where, f"{name} phải là số JSON (nhận {value!r})")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0) or (minimum is not None and number < minimum):
        _fail(where, f"{name} phải hữu hạn" + (" và > 0" if positive else "")
              + (f" và ≥ {minimum:g}" if minimum is not None else "") + f" (nhận {value!r})")
    return number


def _integer(value, name: str, where: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(where, f"{name} phải là số nguyên ≥ {minimum} (nhận {value!r})")
    return value


def _check_keys(data, allowed, section: str, where: str) -> dict:
    if not isinstance(data, dict):
        _fail(where, f"{section} phải là một đối tượng JSON")
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        _fail(where, f"khóa lạ trong {section}: {unknown}")
    return data


# ---------------------------------------------------------------------------------------------------- gá LiDAR
@dataclass(frozen=True)
class LidarMount:
    """Tâm quay LiDAR trong hệ xe (m, m, độ). `measured` = False: GIẢ ĐỊNH – CHƯA ĐO."""

    x_m: float = 0.095
    y_m: float = 0.0
    yaw_deg: float = 0.0
    z_m: float | None = None
    measured: bool = False
    measured_on: str | None = None
    evidence: str | None = None
    basis: str = MOUNT_BASIS_DEFAULT

    def __post_init__(self):
        for name in ("x_m", "y_m", "yaw_deg"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"gá LiDAR: {name} phải hữu hạn")

    @property
    def pose(self) -> Pose:
        return Pose(self.x_m, self.y_m, math.radians(self.yaw_deg))

    def as_tuple(self) -> tuple[float, float, float]:
        """(x, y, yaw rad) như tham số `mount` của `LiveLidarLayer`."""
        return self.x_m, self.y_m, math.radians(self.yaw_deg)

    def sensor_pose(self, vehicle: Pose) -> Pose:
        """Tư thế tâm quay LiDAR trong hệ sa bàn khi xe (tâm trục sau) ở `vehicle`: vehicle ⊕ gá."""
        x, y = vehicle.to_world(self.x_m, self.y_m)
        return Pose(x, y, wrap_angle(vehicle.yaw + math.radians(self.yaw_deg)))

    def vehicle_pose(self, sensor: Pose) -> Pose:
        """Phép ngược của `sensor_pose`: tư thế tâm trục sau khi LiDAR ở `sensor` (sensor ⊕ gá⁻¹)."""
        yaw = wrap_angle(sensor.yaw - math.radians(self.yaw_deg))
        c, s = math.cos(yaw), math.sin(yaw)
        return Pose(sensor.x - (c * self.x_m - s * self.y_m), sensor.y - (s * self.x_m + c * self.y_m), yaw)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Prerequisite:
    """Một điều kiện tiên quyết của SO_SANH mục 7 cho bo thật: đạt (`ok`) chỉ được tính khi có bằng chứng."""

    key: str
    ok: bool = False
    evidence: str | None = None
    note: str = ""

    @property
    def met(self) -> bool:
        return bool(self.ok) and bool(self.evidence)

    @property
    def label(self) -> str:
        return PREREQUISITE_LABELS.get(self.key, self.key)


# ------------------------------------------------------------------------------------------- ngưỡng bộ ghép (a)+(b)
@dataclass(frozen=True)
class CrossCheck:
    """Dung sai kiểm chéo (a)/(b): base + per · quãng đi kể từ mốc (m và độ). ĐỀ XUẤT – CHỜ CHỐT."""

    base_m: float = 0.04
    per_m: float = 0.03
    base_deg: float = 2.0
    per_m_deg: float = 2.0

    def tolerance(self, travel_m: float) -> tuple[float, float]:
        """(dung sai m, dung sai độ) sau quãng đi `travel_m` kể từ mốc (a, b)."""
        return self.base_m + self.per_m * travel_m, self.base_deg + self.per_m_deg * travel_m


@dataclass(frozen=True)
class LocalizerParams:
    """Tham số của `LidarPoseEstimator` (lidar/pose_estimator.py). Đều là ĐỀ XUẤT – CHỜ CHỐT (02/10/2026)."""

    track_window: tuple[float, float, float] = (0.15, 0.15, 10.0)    # m, m, độ quanh tư thế dự đoán từ (b)
    init_window: tuple[float, float, float] = (0.5, 0.5, 30.0)       # m, m, độ quanh điểm xuất phát
    retry_on_window_edge: bool = True
    allow_global_init: bool = True
    global_retry_s: float = 10.0
    init_confirm_scans: int = 3
    init_confirm_spread: tuple[float, float] = (0.02, 1.0)           # m, độ
    max_consecutive_bad: int = 2
    cross_check: CrossCheck = field(default_factory=CrossCheck)
    max_unchecked_scans: int = 5
    relatch_s: float = 1.0
    start_ok_scans: int = 5
    min_rate_hz: float = 8.0
    warn_latency_p95_s: float = 0.05
    max_latency_p95_s: float = 0.10
    self_mask_margin_m: float = 0.03
    queue_size: int = 1

    def __post_init__(self):
        for name in ("track_window", "init_window"):
            value = getattr(self, name)
            if len(value) != 3 or not all(math.isfinite(v) and v > 0 for v in value):
                raise ValueError(f"{name} phải gồm 3 số hữu hạn > 0 (m, m, độ)")
        spread = self.init_confirm_spread
        if len(spread) != 2 or not all(math.isfinite(v) and v > 0 for v in spread):
            raise ValueError("init_confirm_spread phải gồm 2 số hữu hạn > 0 (m, độ)")
        for name in ("global_retry_s", "relatch_s", "min_rate_hz", "warn_latency_p95_s", "max_latency_p95_s"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} phải hữu hạn và > 0")
        if not math.isfinite(self.self_mask_margin_m) or self.self_mask_margin_m < 0:
            raise ValueError("self_mask_margin_m phải hữu hạn và ≥ 0")
        cc = self.cross_check
        if not all(math.isfinite(v) and v >= 0 for v in (cc.base_m, cc.per_m, cc.base_deg, cc.per_m_deg)) \
                or cc.base_m <= 0 or cc.base_deg <= 0:
            raise ValueError("cross_check: base_m, base_deg phải > 0; per_m, per_m_deg phải ≥ 0")
        for name in ("init_confirm_scans", "max_consecutive_bad", "max_unchecked_scans", "start_ok_scans", "queue_size"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} phải là số nguyên ≥ 1")
        if self.warn_latency_p95_s > self.max_latency_p95_s:
            raise ValueError("warn_latency_p95_s phải ≤ max_latency_p95_s")

    def window_rad(self, name: str) -> tuple[float, float, float]:
        """Cửa sổ `name` ("track_window" hoặc "init_window") theo đơn vị của `localize` (m, m, rad)."""
        wx, wy, wdeg = getattr(self, name)
        return wx, wy, math.radians(wdeg)


@dataclass(frozen=True)
class SimLidarParams:
    """LiDAR MÔ PHỎNG (lidar/synthetic.py): vòng quét dựng từ sa bàn, kiểu C1. Toàn bộ là GIẢ ĐỊNH."""

    period_s: float = 0.1
    beams: int = 510
    fov_deg: float = 360.0
    noise_m: float = 0.01
    dropout: float = 0.1
    max_range_m: float = 12.0
    min_range_m: float = 0.05
    latency_s: float = 0.04
    warmup_max_s: float = 2.0
    walls_from_bounds: bool = True
    room_margin_m: float = 1.0
    map_placements: int = 5
    map_scans_per_placement: int = 5
    seed: int = 0

    def __post_init__(self):
        if not (math.isfinite(self.period_s) and self.period_s > 0 and math.isfinite(self.warmup_max_s)
                and self.warmup_max_s > 0):
            raise ValueError("sim: period_s, warmup_max_s phải hữu hạn và > 0")
        if not 0 < self.fov_deg <= 360 or not 0 <= self.dropout < 1:
            raise ValueError("sim: fov_deg trong (0, 360], dropout trong [0, 1)")
        if not (0 <= self.min_range_m < self.max_range_m and math.isfinite(self.max_range_m)):
            raise ValueError("sim: cần 0 ≤ min_range_m < max_range_m hữu hạn")
        if not (math.isfinite(self.noise_m) and self.noise_m >= 0 and math.isfinite(self.latency_s)
                and self.latency_s >= 0 and math.isfinite(self.room_margin_m) and self.room_margin_m >= 0):
            raise ValueError("sim: noise_m, latency_s, room_margin_m phải hữu hạn và ≥ 0")
        for name in ("beams", "map_placements", "map_scans_per_placement"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"sim: {name} phải là số nguyên ≥ 1")


# ------------------------------------------------------------------------------------------------- cả tệp cấu hình
@dataclass(frozen=True)
class LidarPoseConfig:
    mount: LidarMount = field(default_factory=LidarMount)
    prerequisites: tuple[Prerequisite, ...] = tuple(Prerequisite(key) for key in PREREQUISITE_LABELS)
    localizer: LocalizerParams = field(default_factory=LocalizerParams)
    localize: LocalizeConfig = field(default_factory=LocalizeConfig)
    odometry: OdometryConfig = field(default_factory=lambda: DEFAULT_ODOMETRY)
    sim: SimLidarParams = field(default_factory=SimLidarParams)
    max_pose_age_s: float = 0.25
    notes: str = ""
    status: str = "GIA_DINH_VA_DE_XUAT"
    vehicle_config: str = "vehicle_default.json"
    path: Path | None = None
    sha256: str | None = None

    def __post_init__(self):
        if not math.isfinite(self.max_pose_age_s) or self.max_pose_age_s <= 0:
            raise ValueError("max_pose_age_s phải hữu hạn và > 0")

    def unmet(self) -> list[str]:
        """Điều còn thiếu để chạy bo THẬT ở VehicleIO (tiếng Việt); rỗng = đủ. Đạt mà không có bằng chứng vẫn là thiếu."""
        where = self.path.name if self.path is not None else DEFAULT_PATH.name
        out = []
        if not (self.mount.measured and self.mount.evidence):
            out.append(f"gá LiDAR GIẢ ĐỊNH – CHƯA ĐO (configs/{where})")
        for item in self.prerequisites:
            if not item.met:
                out.append(f"chưa đạt: {item.label}" + (" (ghi ok nhưng thiếu bằng chứng)" if item.ok else ""))
        return out

    def to_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, "status": self.status, "notes": self.notes,
                "vehicle_config": self.vehicle_config, "mount": self.mount.to_dict(),
                "prerequisites": {p.key: {"ok": p.ok, "evidence": p.evidence, "note": p.note}
                                  for p in self.prerequisites},
                "max_pose_age_s": self.max_pose_age_s,
                "localizer": {**asdict(self.localizer), "track_window": list(self.localizer.track_window),
                              "init_window": list(self.localizer.init_window),
                              "init_confirm_spread": list(self.localizer.init_confirm_spread)},
                "localize": _changed_fields(self.localize, LocalizeConfig()),
                "odometry": _changed_fields(self.odometry, OdometryConfig()),
                "sim": asdict(self.sim), "path": None if self.path is None else str(self.path),
                "sha256": self.sha256}

    @classmethod
    def from_dict(cls, data, *, path: Path | None = None, sha256: str | None = None) -> "LidarPoseConfig":
        where = path.name if path is not None else ""
        top = ("schema_version", "status", "notes", "vehicle_config", "mount", "prerequisites", "max_pose_age_s",
               "localizer", "localize", "odometry", "sim")
        data = _check_keys(data, top, "tệp", where)
        if data.get("schema_version") != SCHEMA_VERSION:
            _fail(where, f"schema_version {data.get('schema_version')!r} không được hỗ trợ (cần {SCHEMA_VERSION})")
        for key in ("status", "notes", "vehicle_config"):
            if key in data and not isinstance(data[key], str):
                _fail(where, f"{key} phải là chuỗi")
        kwargs: dict = {key: data[key] for key in ("status", "notes", "vehicle_config") if key in data}
        if "max_pose_age_s" in data:
            kwargs["max_pose_age_s"] = _number(data["max_pose_age_s"], "max_pose_age_s", where, positive=True)
        if "mount" in data:
            kwargs["mount"] = _mount_from_dict(data["mount"], where)
        if "prerequisites" in data:
            kwargs["prerequisites"] = _prerequisites_from_dict(data["prerequisites"], where)
        if "localizer" in data:
            kwargs["localizer"] = _localizer_from_dict(data["localizer"], where)
        if "localize" in data:
            kwargs["localize"] = _dataclass_overrides(LocalizeConfig(), data["localize"], "localize", where)
        if "odometry" in data:
            kwargs["odometry"] = _dataclass_overrides(DEFAULT_ODOMETRY, data["odometry"], "odometry", where)
        if "sim" in data:
            kwargs["sim"] = _dataclass_overrides(SimLidarParams(), data["sim"], "sim", where)
        try:
            return cls(**kwargs, path=path, sha256=sha256)
        except ValueError as exc:
            _fail(where, str(exc))


def _changed_fields(value, default) -> dict:
    """Các trường của dataclass `value` khác mặc định (khối "localize"/"odometry" của tệp chỉ ghi phần ghi đè)."""
    return {f.name: getattr(value, f.name) for f in fields(value) if getattr(value, f.name) != getattr(default, f.name)}


def _mount_from_dict(data, where: str) -> LidarMount:
    keys = ("x_m", "y_m", "yaw_deg", "z_m", "measured", "measured_on", "evidence", "basis")
    data = _check_keys(data, keys, "mount", where)
    kwargs = {}
    for key in ("x_m", "y_m", "yaw_deg"):
        if key in data:
            kwargs[key] = _number(data[key], f"mount.{key}", where)
    if data.get("z_m") is not None:
        kwargs["z_m"] = _number(data["z_m"], "mount.z_m", where)
    if "measured" in data:
        if not isinstance(data["measured"], bool):
            _fail(where, "mount.measured phải là true/false")
        kwargs["measured"] = data["measured"]
    for key in ("measured_on", "evidence", "basis"):
        if data.get(key) is not None:
            if not isinstance(data[key], str):
                _fail(where, f"mount.{key} phải là chuỗi hoặc null")
            kwargs[key] = data[key]
    return LidarMount(**kwargs)


def _prerequisites_from_dict(data, where: str) -> tuple[Prerequisite, ...]:
    data = _check_keys(data, PREREQUISITE_LABELS, "prerequisites", where)
    out = []
    for key in PREREQUISITE_LABELS:
        item = _check_keys(data.get(key, {}), ("ok", "evidence", "note"), f"prerequisites.{key}", where)
        ok = item.get("ok", False)
        if not isinstance(ok, bool):
            _fail(where, f"prerequisites.{key}.ok phải là true/false")
        evidence = item.get("evidence")
        if evidence is not None and not isinstance(evidence, str):
            _fail(where, f"prerequisites.{key}.evidence phải là chuỗi hoặc null")
        note = item.get("note", "")
        if not isinstance(note, str):
            _fail(where, f"prerequisites.{key}.note phải là chuỗi")
        out.append(Prerequisite(key, ok, evidence, note))
    return tuple(out)


def _localizer_from_dict(data, where: str) -> LocalizerParams:
    names = [f.name for f in fields(LocalizerParams)]
    data = _check_keys(data, names, "localizer", where)
    kwargs = {}
    for key, value in data.items():
        name = f"localizer.{key}"
        if key in ("track_window", "init_window", "init_confirm_spread"):
            size = 2 if key == "init_confirm_spread" else 3
            if not isinstance(value, list) or len(value) != size:
                _fail(where, f"{name} phải là danh sách {size} số")
            kwargs[key] = tuple(_number(v, name, where, positive=True) for v in value)
        elif key == "cross_check":
            cc = _check_keys(value, [f.name for f in fields(CrossCheck)], name, where)
            kwargs[key] = CrossCheck(**{k: _number(v, f"{name}.{k}", where, minimum=0.0) for k, v in cc.items()})
        elif key in ("retry_on_window_edge", "allow_global_init"):
            if not isinstance(value, bool):
                _fail(where, f"{name} phải là true/false")
            kwargs[key] = value
        elif key in ("init_confirm_scans", "max_consecutive_bad", "max_unchecked_scans", "start_ok_scans",
                     "queue_size"):
            kwargs[key] = _integer(value, name, where)
        else:
            kwargs[key] = _number(value, name, where)
    return LocalizerParams(**kwargs)


def _dataclass_overrides(defaults, data, section: str, where: str):
    """Ghi đè từng trường của dataclass `defaults` (bản mặc định của khối: LocalizeConfig, OdometryConfig với
    velocity_per "second", SimLidarParams); khóa lạ → lỗi. Kiểu theo giá trị mặc định: bool, int, float, str; trường mặc
    định None nhận số hoặc null."""
    names = [f.name for f in fields(defaults)]
    data = _check_keys(data, names, section, where)
    kwargs = {}
    for key, value in data.items():
        default = getattr(defaults, key)
        name = f"{section}.{key}"
        if isinstance(default, bool):
            if not isinstance(value, bool):
                _fail(where, f"{name} phải là true/false")
        elif isinstance(default, int):
            value = _integer(value, name, where, minimum=0)
        elif isinstance(default, float) or default is None:
            if value is not None:
                value = _number(value, name, where)
        elif isinstance(default, str):
            if not isinstance(value, str):
                _fail(where, f"{name} phải là chuỗi")
        kwargs[key] = value
    try:
        return replace(defaults, **kwargs)
    except ValueError as exc:
        _fail(where, f"{section}: {exc}")


def load_lidar_pose_config(path=None) -> LidarPoseConfig:
    """Nạp tệp cấu hình (mặc định `DEFAULT_PATH`). Tệp không đọc được, JSON hỏng hay sai luật → ValueError tiếng Việt."""
    path = Path(path) if path is not None else DEFAULT_PATH
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cấu hình định vị LiDAR {path}: không đọc được ({exc})") from exc
    return LidarPoseConfig.from_dict(data, path=path, sha256=hashlib.sha256(raw).hexdigest())
