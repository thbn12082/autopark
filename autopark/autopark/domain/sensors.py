"""Hợp đồng dữ liệu giai đoạn 0. Thời gian: giây trên cùng đồng hồ phiên.

UNKNOWN trong costmap là ô chưa quan sát/không chắc chắn, luôn bị chặn.
Các kiểu này chưa phải driver cảm biến hay kết quả nhận thức thực.
"""
from dataclasses import dataclass
import math

from autopark.domain.types import ParkingGoal, Pose


@dataclass(frozen=True)
class SourceStamp:
    source_id: str
    t: float
    valid: bool = True
    frame_id: str = "map"

    def __post_init__(self):
        if not self.source_id or not self.frame_id or not math.isfinite(self.t) or self.t < 0:
            raise ValueError("Nguồn, hệ tọa độ và thời gian phải hợp lệ")

    def fresh(self, now: float, max_age: float) -> bool:
        return self.valid and 0 <= now - self.t <= max_age


@dataclass(frozen=True)
class GoalPose:
    stamp: SourceStamp
    goal: ParkingGoal


@dataclass(frozen=True)
class CameraFrame:
    stamp: SourceStamp
    image_path: str
    width: int
    height: int
    encoding: str = "BGR8"


@dataclass(frozen=True)
class LidarScan:
    """Góc theo quy ước yaw của dự án (0 = phía trước, dương ngược chiều kim đồng hồ).

    `ranges_m` là NaN khi chùm tia không có phản hồi; NaN không phải bằng chứng vùng trống.
    """

    stamp: SourceStamp
    angles_rad: tuple[float, ...]
    ranges_m: tuple[float, ...]

    def __post_init__(self):
        if len(self.angles_rad) != len(self.ranges_m):
            raise ValueError("Số góc và khoảng cách phải bằng nhau")
        if not all(math.isfinite(a) for a in self.angles_rad):
            raise ValueError("Góc quét phải hữu hạn")
        if not all(math.isnan(r) or (math.isfinite(r) and r >= 0) for r in self.ranges_m):
            raise ValueError("Khoảng cách phải là NaN (không phản hồi) hoặc số hữu hạn >= 0")


@dataclass(frozen=True)
class Telemetry:
    stamp: SourceStamp
    speed_mps: float
    steer_rad: float
    pose: Pose | None = None


@dataclass(frozen=True)
class Costmap:
    stamp: SourceStamp
    resolution_m: float
    origin: Pose
    cells: tuple[tuple[int, ...], ...]  # -1 UNKNOWN, 0 FREE, 1 OCCUPIED

    def __post_init__(self):
        if not math.isfinite(self.resolution_m) or self.resolution_m <= 0:
            raise ValueError("Độ phân giải phải > 0")
        if not self.cells or not self.cells[0] or any(
            len(row) != len(self.cells[0]) or any(v not in (-1, 0, 1) for v in row)
            for row in self.cells
        ):
            raise ValueError("Costmap phải là ma trận UNKNOWN/FREE/OCCUPIED")

    def blocked(self, row: int, col: int) -> bool:
        if not self.stamp.valid or not (0 <= row < len(self.cells) and 0 <= col < len(self.cells[0])):
            return True
        return self.cells[row][col] != 0


@dataclass(frozen=True)
class SafetyEvent:
    stamp: SourceStamp
    code: str
    message: str
    action: str = "STOP"
