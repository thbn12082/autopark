"""Kiểu dữ liệu dùng chung cho toàn dự án.

Quy ước (tài liệu tổng quan, mục 5.5):
- Đơn vị tính toán: mét, giây, radian. Giao diện hiển thị cm và độ.
- Tư thế xe lấy tại tâm trục sau.
- Hệ xe: x hướng tới đầu xe, y sang trái, yaw dương ngược chiều kim đồng hồ nhìn từ trên.
- Góc lái dương là rẽ trái khi tiến.
- Trong file JSON, góc ghi bằng độ với hậu tố `_deg` để người đọc không nhầm; khi nạp đổi sang radian.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


def _finite_float(value: Any, name: str) -> float:
    """Chặn NaN/Infinity ngay khi đọc dữ liệu, trước khi đi tới hình học/mô phỏng."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} phải là số hữu hạn")
    return number


def wrap_angle(angle: float) -> float:
    """Đưa góc về khoảng (-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


@dataclass(frozen=True)
class Pose:
    """Tư thế phẳng: vị trí tâm trục sau (m) và hướng thân xe (rad)."""

    x: float
    y: float
    yaw: float

    def to_world(self, px: float, py: float) -> tuple[float, float]:
        """Điểm trong hệ xe -> hệ bản đồ."""
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        return (self.x + c * px - s * py, self.y + s * px + c * py)

    def to_body(self, wx: float, wy: float) -> tuple[float, float]:
        """Điểm trong hệ bản đồ -> hệ xe."""
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        dx, dy = wx - self.x, wy - self.y
        return (c * dx + s * dy, -s * dx + c * dy)

    def distance_to(self, other: "Pose") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def heading_error_to(self, other: "Pose") -> float:
        return wrap_angle(other.yaw - self.yaw)

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "yaw_deg": math.degrees(self.yaw)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Pose":
        if "yaw_deg" in d:
            yaw = math.radians(_finite_float(d["yaw_deg"], "yaw_deg"))
        else:
            yaw = _finite_float(d.get("yaw", 0.0), "yaw")
        return cls(_finite_float(d["x"], "x"), _finite_float(d["y"], "y"), wrap_angle(yaw))


@dataclass(frozen=True)
class VehicleConfig:
    """Thông số xe dùng cho mô phỏng, kiểm tra va chạm và (sau này) lập đường.

    Mọi số ở đây là giả định cho đến khi đo trên xe thật; xem trường `notes`.
    """

    name: str
    wheelbase: float          # m, trục trước tới trục sau
    width: float              # m, bề rộng thân xe (phần rộng nhất)
    front_overhang: float     # m, trục trước tới mũi xe
    rear_overhang: float      # m, trục sau tới đuôi xe
    max_steer: float          # rad, góc lái tương đương lớn nhất
    max_speed: float          # m/s, độ lớn tốc độ lớn nhất cho phép (cả lùi)
    max_accel: float          # m/s^2, tăng độ lớn tốc độ
    max_decel: float          # m/s^2, giảm độ lớn tốc độ (phanh)
    max_steer_rate: float     # rad/s, tốc độ đổi góc lái
    notes: str = ""

    @property
    def length(self) -> float:
        return self.rear_overhang + self.wheelbase + self.front_overhang

    @property
    def min_turn_radius(self) -> float:
        """Bán kính quay nhỏ nhất tại tâm trục sau (chưa tính phần thân xe quét ra ngoài)."""
        return self.wheelbase / math.tan(self.max_steer)

    def validate(self) -> list[str]:
        problems: list[str] = []
        for name in ("wheelbase", "width", "front_overhang", "rear_overhang",
                     "max_speed", "max_accel", "max_decel", "max_steer_rate"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                problems.append(f"{name} phải hữu hạn và > 0")
        if not (0 < self.max_steer < math.radians(89)):
            problems.append("max_steer phải trong (0, 89) độ")
        return problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "name": self.name,
            "wheelbase_m": self.wheelbase,
            "width_m": self.width,
            "front_overhang_m": self.front_overhang,
            "rear_overhang_m": self.rear_overhang,
            "max_steer_deg": math.degrees(self.max_steer),
            "max_speed_mps": self.max_speed,
            "max_accel_mps2": self.max_accel,
            "max_decel_mps2": self.max_decel,
            "max_steer_rate_deg_s": math.degrees(self.max_steer_rate),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VehicleConfig":
        cfg = cls(
            name=str(d["name"]),
            wheelbase=float(d["wheelbase_m"]),
            width=float(d["width_m"]),
            front_overhang=float(d["front_overhang_m"]),
            rear_overhang=float(d["rear_overhang_m"]),
            max_steer=math.radians(float(d["max_steer_deg"])),
            max_speed=float(d["max_speed_mps"]),
            max_accel=float(d["max_accel_mps2"]),
            max_decel=float(d["max_decel_mps2"]),
            max_steer_rate=math.radians(float(d["max_steer_rate_deg_s"])),
            notes=str(d.get("notes", "")),
        )
        problems = cfg.validate()
        if problems:
            raise ValueError("Cấu hình xe không hợp lệ: " + "; ".join(problems))
        return cfg


OBSTACLE_KINDS = ("box", "car", "wall", "unknown")


@dataclass(frozen=True)
class Obstacle:
    """Vật cản hình chữ nhật: tâm, kích thước, góc xoay. `kind` chỉ ảnh hưởng cách vẽ."""

    id: str
    cx: float
    cy: float
    width: float   # m, theo trục x cục bộ (với xe đỗ: chiều dài xe)
    height: float  # m, theo trục y cục bộ
    yaw: float = 0.0
    kind: str = "box"

    def corners(self) -> list[tuple[float, float]]:
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        hw, hh = self.width / 2, self.height / 2
        out = []
        for px, py in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
            out.append((self.cx + c * px - s * py, self.cy + s * px + c * py))
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "cx": self.cx, "cy": self.cy, "width": self.width,
                "height": self.height, "yaw_deg": math.degrees(self.yaw), "kind": self.kind}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Obstacle":
        yaw = math.radians(_finite_float(d.get("yaw_deg", 0.0), "obstacle.yaw_deg"))
        kind = str(d.get("kind", "box"))
        if kind not in OBSTACLE_KINDS:
            raise ValueError(f"kind vật cản không hợp lệ: {kind}")
        obs = cls(str(d["id"]), _finite_float(d["cx"], "obstacle.cx"),
                  _finite_float(d["cy"], "obstacle.cy"),
                  _finite_float(d["width"], "obstacle.width"),
                  _finite_float(d["height"], "obstacle.height"), wrap_angle(yaw), kind)
        if obs.width <= 0 or obs.height <= 0:
            raise ValueError("Vật cản phải có width và height > 0")
        return obs


class ParkingMode(str, Enum):
    """Kiểu đỗ người dùng chọn trên màn hình."""

    REVERSE_IN = "reverse_in"   # lùi vào ô, đầu xe hướng ra cửa ô
    HEAD_IN = "head_in"         # tiến vào ô, đầu xe hướng vào đáy ô
    PARALLEL = "parallel"       # đỗ song song: xe nằm dọc theo trục ô

    @property
    def label(self) -> str:
        return {"reverse_in": "Lùi vào ô", "head_in": "Tiến vào ô", "parallel": "Đỗ song song"}[self.value]


@dataclass(frozen=True)
class ParkingSlot:
    """Khung ô đỗ người dùng kéo/xoay. Trục x của ô hướng từ cửa ô vào đáy ô."""

    cx: float
    cy: float
    yaw: float
    length: float   # m, theo trục x của ô
    width: float    # m, theo trục y của ô

    def fits_vehicle(self, cfg: VehicleConfig) -> bool:
        """Ở tư thế đích, trục dọc xe song song trục dọc ô trong cả ba kiểu đỗ."""
        return self.length >= cfg.length and self.width >= cfg.width

    def axis(self) -> tuple[float, float]:
        return (math.cos(self.yaw), math.sin(self.yaw))

    def corners(self) -> list[tuple[float, float]]:
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        hl, hw = self.length / 2, self.width / 2
        out = []
        for px, py in ((-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)):
            out.append((self.cx + c * px - s * py, self.cy + s * px + c * py))
        return out

    def goal_pose(self, cfg: "VehicleConfig", mode: ParkingMode, reference_yaw: float | None = None) -> Pose:
        """Tư thế đích (tâm trục sau) khi xe nằm giữa ô theo kiểu đỗ đã chọn.

        Với đỗ song song, hướng xe lấy theo trục ô hoặc ngược lại, chọn hướng gần
        `reference_yaw` (thường là hướng xe hiện tại) hơn.
        """
        ax, ay = self.axis()
        # Khoảng từ điểm giữa thân xe tới tâm trục sau, đo dọc thân xe về phía đuôi
        back = cfg.length / 2 - cfg.rear_overhang
        if mode == ParkingMode.REVERSE_IN:
            yaw = wrap_angle(self.yaw + math.pi)
            return Pose(self.cx + back * ax, self.cy + back * ay, yaw)
        if mode == ParkingMode.HEAD_IN:
            return Pose(self.cx - back * ax, self.cy - back * ay, wrap_angle(self.yaw))
        # PARALLEL
        yaw = wrap_angle(self.yaw)
        if reference_yaw is not None and abs(wrap_angle(reference_yaw - yaw)) > math.pi / 2:
            yaw = wrap_angle(self.yaw + math.pi)
        c, s = math.cos(yaw), math.sin(yaw)
        return Pose(self.cx - back * c, self.cy - back * s, yaw)

    def to_dict(self) -> dict[str, Any]:
        return {"cx": self.cx, "cy": self.cy, "yaw_deg": math.degrees(self.yaw),
                "length": self.length, "width": self.width}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ParkingSlot":
        slot = cls(_finite_float(d["cx"], "slot.cx"), _finite_float(d["cy"], "slot.cy"),
                   wrap_angle(math.radians(_finite_float(d.get("yaw_deg", 0.0), "slot.yaw_deg"))),
                   _finite_float(d["length"], "slot.length"), _finite_float(d["width"], "slot.width"))
        if slot.length <= 0 or slot.width <= 0:
            raise ValueError("Ô đỗ phải có length và width > 0")
        return slot

    @classmethod
    def default_for(cls, cfg: "VehicleConfig", cx: float, cy: float, yaw: float, mode: ParkingMode) -> "ParkingSlot":
        if mode == ParkingMode.PARALLEL:
            return cls(cx, cy, yaw, cfg.length * 1.6, cfg.width + 0.10)
        return cls(cx, cy, yaw, cfg.length + 0.20, cfg.width + 0.20)


@dataclass(frozen=True)
class Bounds:
    """Vùng sa bàn được phép (hình chữ nhật, trục song song bản đồ)."""

    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @property
    def width(self) -> float:
        return self.xmax - self.xmin

    @property
    def height(self) -> float:
        return self.ymax - self.ymin

    @property
    def center(self) -> tuple[float, float]:
        return ((self.xmin + self.xmax) / 2, (self.ymin + self.ymax) / 2)

    def contains_point(self, x: float, y: float) -> bool:
        return self.xmin <= x <= self.xmax and self.ymin <= y <= self.ymax

    def to_dict(self) -> dict[str, float]:
        return {"xmin": self.xmin, "ymin": self.ymin, "xmax": self.xmax, "ymax": self.ymax}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Bounds":
        b = cls(*(_finite_float(d[key], f"bounds.{key}") for key in ("xmin", "ymin", "xmax", "ymax")))
        if b.width <= 0 or b.height <= 0:
            raise ValueError("bounds phải có xmax > xmin và ymax > ymin")
        return b


@dataclass(frozen=True)
class ParkingGoal:
    """Đích đỗ: tư thế và dung sai. Dung sai là mục tiêu thiết kế, chưa phải kết quả."""

    pose: Pose
    tolerance_xy: float = 0.05                 # m
    tolerance_yaw: float = math.radians(5.0)   # rad

    def to_dict(self) -> dict[str, Any]:
        d = self.pose.to_dict()
        d["tolerance_cm"] = self.tolerance_xy * 100
        d["tolerance_deg"] = math.degrees(self.tolerance_yaw)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ParkingGoal":
        goal = cls(
            pose=Pose.from_dict(d),
            tolerance_xy=_finite_float(d.get("tolerance_cm", 5.0), "tolerance_cm") / 100,
            tolerance_yaw=math.radians(_finite_float(d.get("tolerance_deg", 5.0), "tolerance_deg")),
        )
        if goal.tolerance_xy <= 0 or goal.tolerance_yaw <= 0:
            raise ValueError("Dung sai vị trí và góc phải > 0")
        return goal


@dataclass
class Scenario:
    """Một kịch bản sa bàn: vùng, xuất phát, ô đỗ/đích, vật cản, xe dùng, seed.

    Khi có `slot`, `goal.pose` được suy từ ô đỗ và `mode` (gọi `sync_goal`); khi
    không có ô đỗ, `goal` là đích đặt trực tiếp.
    """

    name: str
    bounds: Bounds
    start: Pose
    goal: ParkingGoal
    obstacles: list[Obstacle] = field(default_factory=list)
    slot: ParkingSlot | None = None
    mode: ParkingMode = ParkingMode.REVERSE_IN
    vehicle_config: str = "../configs/vehicle_default.json"   # đường dẫn tương đối so với file kịch bản
    vehicle_config_path: Path | None = None                    # đường dẫn tuyệt đối sau khi nạp
    seed: int = 0
    notes: str = ""

    def sync_goal(self, cfg: VehicleConfig) -> Pose:
        """Cập nhật goal.pose từ ô đỗ (nếu có) và trả về tư thế đích."""
        if self.slot is not None:
            pose = self.slot.goal_pose(cfg, self.mode, reference_yaw=self.start.yaw)
            self.goal = ParkingGoal(pose, self.goal.tolerance_xy, self.goal.tolerance_yaw)
        return self.goal.pose

    def obstacle_by_id(self, obstacle_id: str) -> Obstacle | None:
        for o in self.obstacles:
            if o.id == obstacle_id:
                return o
        return None

    def next_obstacle_id(self) -> str:
        existing = {o.id for o in self.obstacles}
        i = 1
        while f"hop_{i}" in existing:
            i += 1
        return f"hop_{i}"

    def to_dict(self) -> dict[str, Any]:
        data = {
            "schema_version": 1,
            "name": self.name,
            "notes": self.notes,
            "vehicle_config": self.vehicle_config,
            "bounds": self.bounds.to_dict(),
            "start": self.start.to_dict(),
            "goal": self.goal.to_dict(),
            "obstacles": [o.to_dict() for o in self.obstacles],
            "seed": self.seed,
        }
        if self.slot is not None:
            data["slot"] = self.slot.to_dict()
            data["mode"] = self.mode.value
        return data

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Scenario":
        version = int(d.get("schema_version", 0))
        if version != 1:
            raise ValueError(f"schema_version {version} không được hỗ trợ (cần 1)")
        obstacles = [Obstacle.from_dict(o) for o in d.get("obstacles", [])]
        ids = [o.id for o in obstacles]
        if len(ids) != len(set(ids)):
            raise ValueError("id vật cản bị trùng")
        slot = ParkingSlot.from_dict(d["slot"]) if d.get("slot") else None
        mode = ParkingMode(str(d.get("mode", ParkingMode.REVERSE_IN.value)))
        if "goal" in d:
            goal = ParkingGoal.from_dict(d["goal"])
        elif slot is not None:
            goal = ParkingGoal(Pose(slot.cx, slot.cy, slot.yaw))  # tạm; sync_goal(cfg) sẽ tính lại
        else:
            raise ValueError("Kịch bản cần 'goal' hoặc 'slot'")
        return cls(
            name=str(d["name"]),
            bounds=Bounds.from_dict(d["bounds"]),
            start=Pose.from_dict(d["start"]),
            goal=goal,
            obstacles=obstacles,
            slot=slot,
            mode=mode,
            vehicle_config=str(d.get("vehicle_config", "../configs/vehicle_default.json")),
            seed=int(d.get("seed", 0)),
            notes=str(d.get("notes", "")),
        )


@dataclass(frozen=True)
class VehicleState:
    """Trạng thái THẬT của xe mô phỏng.

    Chỉ bộ sinh cảm biến và bộ chấm được đọc; planner/controller sau này chỉ
    được dùng ước lượng (tài liệu mục 6.3).
    """

    pose: Pose
    speed: float   # m/s, có dấu (âm khi lùi)
    steer: float   # rad, góc lái thực đang có
    t: float       # s, đồng hồ mô phỏng
    source_id: str = "sim_vehicle"
    valid: bool = True

    def usable(self) -> bool:
        """Structural validity, separate from freshness and estimator accuracy."""
        return (self.valid and bool(self.source_id) and self.t >= 0
                and all(math.isfinite(v) for v in
                        (self.pose.x, self.pose.y, self.pose.yaw, self.speed, self.steer, self.t)))


@dataclass(frozen=True)
class DriveCommand:
    """Lệnh cấp ứng dụng: mục tiêu chuyển động, không phải PWM."""

    seq: int
    target_speed: float
    target_steer: float
    created_at: float
    valid_for: float = 0.15
