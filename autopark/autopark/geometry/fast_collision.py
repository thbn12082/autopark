"""Kiểm tra va chạm giải tích cho vòng trong của bộ lập đường.

Bản dùng Shapely (`geometry/footprint.py`) đúng nhưng chậm: đo trên ca
`parallel_135` cho thấy 248.270 lần gọi `pose_ok` tốn 10,7 s trong tổng 17,4 s,
riêng việc dựng `Polygon` mất 7,7 s. Ở đây thân xe và vật cản đều là hình chữ
nhật, nên chỉ cần định lý trục tách (separating axis theorem) cho hai hình chữ
nhật có hướng: bốn trục cần thử, không cấp phát đối tượng nào.

Quy ước hình học giống `footprint.py`: gốc tọa độ xe ở tâm trục sau, x hướng tới
đầu xe. `margin` nới đều thân xe ra mọi phía.

Lớp này CHỈ dùng trong vòng tìm kiếm. Đường kết quả vẫn phải được kiểm tra lại
bằng `footprint.check_motion` (có xét vùng quét giữa hai mẫu) trước khi dùng.
"""
from __future__ import annotations

import math

from autopark.domain.types import Bounds, Obstacle, Pose, VehicleConfig


class FastCollisionChecker:
    """Thay thế cho `hybrid_astar.CollisionChecker`, cùng giao diện `pose_ok`."""

    __slots__ = ("hl", "hw", "offset", "r_car", "xmin", "ymin", "xmax", "ymax", "obs", "n_obs")

    def __init__(self, cfg: VehicleConfig, obstacles: list[Obstacle], bounds: Bounds, margin: float = 0.0):
        rear = -(cfg.rear_overhang + margin)
        front = cfg.wheelbase + cfg.front_overhang + margin
        self.hl = (front - rear) / 2.0            # nửa chiều dài hình chữ nhật thân xe
        self.hw = cfg.width / 2.0 + margin        # nửa chiều rộng
        self.offset = (front + rear) / 2.0        # tâm hình chữ nhật so với tâm trục sau, dọc trục x xe
        self.r_car = math.hypot(self.hl, self.hw)
        self.xmin, self.ymin, self.xmax, self.ymax = bounds.xmin, bounds.ymin, bounds.xmax, bounds.ymax
        obs = []
        for o in obstacles:
            c, s = math.cos(o.yaw), math.sin(o.yaw)
            hx, hy = o.width / 2.0, o.height / 2.0
            # (tâm x, tâm y, trục u, trục v, nửa cạnh, bán kính bao, bán kính bao cộng xe)
            obs.append((o.cx, o.cy, c, s, -s, c, hx, hy, (math.hypot(hx, hy) + self.r_car) ** 2))
        self.obs = tuple(obs)
        self.n_obs = len(obs)

    def pose_ok(self, x: float, y: float, yaw: float) -> bool:
        """Thân xe ở tư thế này có nằm trong sa bàn và không chạm vật cản không?"""
        c = math.cos(yaw)
        s = math.sin(yaw)
        hl, hw = self.hl, self.hw
        cx = x + c * self.offset
        cy = y + s * self.offset

        # Trong sa bàn: dùng bao chữ nhật thẳng trục của thân xe đã xoay
        ac, as_ = (c if c >= 0.0 else -c), (s if s >= 0.0 else -s)
        ex = hl * ac + hw * as_
        ey = hl * as_ + hw * ac
        if cx - ex < self.xmin or cx + ex > self.xmax or cy - ey < self.ymin or cy + ey > self.ymax:
            return False

        for ox, oy, ux, uy, vx, vy, hx, hy, rr in self.obs:
            dx = ox - cx
            dy = oy - cy
            if dx * dx + dy * dy > rr:          # lọc thô bằng đường tròn bao
                continue
            # A = |cos(lệch hướng)|, B = |sin(lệch hướng)| giữa trục xe và trục vật cản
            t = c * ux + s * uy
            A = t if t >= 0.0 else -t
            t = c * vx + s * vy
            B = t if t >= 0.0 else -t
            # Trục 1: trục dọc xe
            t = dx * c + dy * s
            if (t if t >= 0.0 else -t) > hl + hx * A + hy * B:
                continue
            # Trục 2: trục ngang xe
            t = -dx * s + dy * c
            if (t if t >= 0.0 else -t) > hw + hx * B + hy * A:
                continue
            # Trục 3: trục dọc vật cản
            t = dx * ux + dy * uy
            if (t if t >= 0.0 else -t) > hx + hl * A + hw * B:
                continue
            # Trục 4: trục ngang vật cản
            t = dx * vx + dy * vy
            if (t if t >= 0.0 else -t) > hy + hl * B + hw * A:
                continue
            return False                        # không trục nào tách được → chạm
        return True

    def pose_obj_ok(self, pose: Pose) -> bool:
        return self.pose_ok(pose.x, pose.y, pose.yaw)

    def segment_ok(self, a: Pose, b: Pose, substeps: int = 2) -> bool:
        """Lấy mẫu tuyến tính giữa hai tư thế gần nhau; chỉ đúng khi bước đủ nhỏ.

        Dùng cho các bước mở rộng ngắn trong tìm kiếm. Kiểm tra vùng quét đầy đủ
        vẫn phải do `footprint.check_motion` đảm nhiệm ở khâu xác nhận cuối.
        """
        if not self.pose_ok(b.x, b.y, b.yaw):
            return False
        if substeps <= 1:
            return True
        dyaw = math.atan2(math.sin(b.yaw - a.yaw), math.cos(b.yaw - a.yaw))
        for k in range(1, substeps):
            t = k / substeps
            if not self.pose_ok(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.yaw + dyaw * t):
                return False
        return True
