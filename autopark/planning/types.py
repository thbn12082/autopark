"""Kiểu tham số và kết quả dùng chung cho các bộ lập đường.

PlannerParams giữ cấu trúc tham số trong bản ghi cũ để phát lại được. Luồng thao
tác gần dùng time_limit làm ngân sách; các nấc trong portfolio có cấu hình riêng.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from autopark.planning.trajectory import Trajectory


@dataclass
class PlannerParams:
    xy_resolution: float = 0.05
    yaw_resolution: float = math.radians(10.0)
    step_length: float = 0.08          # m mỗi bước mở rộng
    n_steer: int = 5                   # số mức góc lái (lẻ để có 0)
    steer_ratio: float = 0.85          # lập đường với phần này của góc lái tối đa, chừa dư địa cho bộ bám
    reverse_cost: float = 1.3          # hệ số quãng đường lùi
    switch_cost: float = 0.6           # m tương đương cho mỗi lần đổi chiều
    steer_cost: float = 0.15           # theo |góc lái| (rad) nhân quãng đường
    steer_change_cost: float = 0.3     # theo |đổi góc lái| (rad)
    heuristic_weight: float = 1.0
    safety_margin: float = 0.03        # m nới thân xe khi tìm kiếm
    # Lề an toàn là một ĐÁNH ĐỔI, không phải một hằng số đúng:
    #  - lề rộng thì đường chạy xa vật cản, bộ bám đường dễ theo;
    #  - lề hẹp thì ô chật mới có nghiệm, nhưng đường sát vật cản và khó bám hơn.
    # ĐO ĐƯỢC: hạ share từ 0,50 xuống 0,40 làm ca pillar_at_slot_mouth chuyển từ
    # bám được sang bám hỏng. Nên mặc định giữ mức an toàn, và để `portfolio.py`
    # nới dần khi mức an toàn không ra đường.
    margin_floor: float = 0.0
    margin_clearance_share: float = 0.50
    goal_xy_tol: float = 0.03
    goal_yaw_tol: float = math.radians(3.0)
    rs_radius: float = 1.5             # m: gần đích mới thử nối Reeds–Shepp và dùng heuristic RS
    rs_every: int = 3                  # thử nối mỗi N nút lấy ra
    rs_max_candidates: int = 3
    rs_sample_step: float = 0.03
    path_sample_step: float = 0.02
    max_nodes: int = 150_000
    time_limit: float = 8.0
    cruise_speed: float = 0.15
    approach_speed: float = 0.08
    approach_distance: float = 0.30


@dataclass
class PlanResult:
    status: str                       # OK, NO_PATH, TIMEOUT, CANCELLED, ERROR, GOAL_INVALID,
                                      # START_INVALID, TRACKING_FAILED
    message: str
    trajectory: Trajectory | None = None
    elapsed: float = 0.0
    expanded: int = 0
    popped: int = 0
    rs_tries: int = 0
    margin_used: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "OK"
