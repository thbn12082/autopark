"""Bám quỹ đạo: feedforward góc lái từ quỹ đạo + phản hồi sai số ngang và sai số hướng.

Luật lái (tâm trục sau là điểm tham chiếu, dùng cho cả tiến và lùi):

    δ = δ_ff + dir·k_θ·e_θ − atan(k_y·e_y / (|v| + v_ε))

- δ_ff: góc lái danh nghĩa của quỹ đạo tại điểm gần nhất (độ cong của cung Hybrid A*
  hoặc Reeds–Shepp). Không có số hạng này, Pure Pursuit thuần cắt cua trên cung bán
  kính nhỏ và tích lũy sai số hướng.
- e_θ = hướng quỹ đạo − hướng xe; e_y = độ lệch ngang của xe trong hệ điểm quỹ đạo
  (dương = xe ở bên trái quỹ đạo).
- Khi lùi (dir = −1) số hạng hướng đổi dấu vì đánh lái trái làm hướng xe giảm;
  số hạng ngang giữ nguyên dấu vì lùi với bánh lái phải vẫn đưa đuôi xe sang phải.

Tốc độ theo hồ sơ của quỹ đạo, giới hạn thêm bởi quãng còn lại tới cuối đoạn; dừng
hẳn ở điểm đổi chiều rồi mới sang đoạn kế. Bộ này chỉ dùng trạng thái được cấp vào
`update()`; ở mốc P3 đó là trạng thái thật (chế độ lý tưởng), sau này thay bằng ước lượng.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from autopark.domain.types import Pose, VehicleConfig, VehicleState, clamp, wrap_angle
from autopark.planning.trajectory import Trajectory


@dataclass
class TrackerParams:
    k_heading: float = 1.5
    k_lateral: float = 1.2
    v_eps: float = 0.08
    creep_speed: float = 0.03
    stop_distance: float = 0.01
    stop_speed: float = 0.005
    search_window: int = 40
    lookahead: float = 0.15          # chỉ để hiển thị điểm phía trước
    ff_preview_time: float = 0.3     # s: lấy góc lái danh nghĩa ở điểm xe sẽ tới sau khoảng này, bù trễ đổi lái
    preset_steer: bool = True        # đứng yên chỉnh lái ở đầu đoạn (cần phần cứng cho phép đánh lái tại chỗ)
    preset_tolerance: float = math.radians(3.0)


@dataclass(frozen=True)
class TrackerOutput:
    target_speed: float      # có dấu
    target_steer: float
    segment: int
    index: int
    distance_to_end: float
    lateral_error: float
    heading_error: float
    lookahead: Pose | None
    done: bool
    phase: str               # PRESET_STEER, TRACK, STOP_AT_CUSP, DONE


class TrajectoryTracker:
    def __init__(self, trajectory: Trajectory, cfg: VehicleConfig, params: TrackerParams | None = None):
        self.traj = trajectory
        self.cfg = cfg
        self.p = params or TrackerParams()
        self.segment = 0
        self.index = trajectory.segments[0][0]
        self.done = False
        self.presetting = self.p.preset_steer

    def _nearest(self, state: VehicleState) -> int:
        a, b = self.traj.segments[self.segment]
        lo = max(self.index, a)
        hi = min(lo + self.p.search_window, b)
        best_i, best_d = lo, math.inf
        pts = self.traj.points
        for i in range(lo, hi + 1):
            d = math.hypot(pts[i].pose.x - state.pose.x, pts[i].pose.y - state.pose.y)
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    def update(self, state: VehicleState) -> TrackerOutput:
        if self.done:
            return TrackerOutput(0.0, 0.0, self.segment, self.index, 0.0, 0.0, 0.0, None, True, "DONE")
        pts = self.traj.points
        a, b = self.traj.segments[self.segment]
        self.index = self._nearest(state)
        idx = self.index
        ref = pts[idx]
        direction = ref.direction

        # Sai số trong hệ điểm quỹ đạo gần nhất
        e_x, e_y = ref.pose.to_body(state.pose.x, state.pose.y)
        e_theta = wrap_angle(ref.pose.yaw - state.pose.yaw)
        # Quãng còn lại tới cuối đoạn, trừ phần xe đã vượt qua điểm gần nhất theo chiều chạy
        d_end = max(0.0, pts[b].s - ref.s - e_x * direction)

        # Feedforward lấy ở điểm xe sẽ tới sau ff_preview_time để bù tốc độ đổi lái hữu hạn
        preview = max(abs(state.speed), ref.v) * self.p.ff_preview_time
        f = idx
        while f < b and pts[f].s - ref.s < preview:
            f += 1
        steer_ff = pts[f].steer

        steer = (steer_ff
                 + direction * self.p.k_heading * e_theta
                 - math.atan(self.p.k_lateral * e_y / (abs(state.speed) + self.p.v_eps)))
        steer = clamp(steer, -self.cfg.max_steer, self.cfg.max_steer)

        j = idx
        while j < b and pts[j].s - ref.s < self.p.lookahead:
            j += 1
        lookahead = pts[j].pose

        # Đầu đoạn: đứng yên chỉnh lái tới góc danh nghĩa rồi mới chạy
        if self.presetting:
            if abs(state.steer - steer) > self.p.preset_tolerance:
                return TrackerOutput(0.0, steer, self.segment, idx, d_end, e_y, e_theta, lookahead, False, "PRESET_STEER")
            self.presetting = False

        v_cmd = min(ref.v, math.sqrt(max(0.0, 2.0 * self.cfg.max_decel * (d_end - self.p.stop_distance))))
        phase = "TRACK"
        if d_end > self.p.stop_distance:
            v_cmd = max(v_cmd, self.p.creep_speed)
        else:
            v_cmd = 0.0
            phase = "STOP_AT_CUSP"
            # Stop-speed tolerance alone allowed changing gear with residual motion.
            # The phase-0 actuator reaches exact zero; wait for it before switching.
            if abs(state.speed) < self.p.stop_speed and state.speed == 0.0:
                if self.segment + 1 < len(self.traj.segments):
                    self.segment += 1
                    self.index = self.traj.segments[self.segment][0]
                    self.presetting = self.p.preset_steer
                else:
                    self.done = True
                    phase = "DONE"
        return TrackerOutput(direction * min(v_cmd, self.cfg.max_speed), steer, self.segment, idx, d_end, e_y, e_theta,
                             lookahead, self.done, phase)
