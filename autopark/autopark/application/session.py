"""Phiên làm việc: chỉnh sa bàn, lập đường, xem trước, chạy kín vòng, lái tay.

Máy trạng thái theo tài liệu mục 5.4, thêm COMPLETED (đỗ xong) và MANUAL (lái tay P2). Sơ đồ dưới là nhánh chính;
đủ các nhánh (RUN_TIMEOUT, dừng ngoài dung sai, va chạm khi phanh, VehicleIO...) ở docs/SO_DO_HE_THONG.md:

    EDITING --plan--> PLANNING --ok--> READY --start--> RUNNING --xong--> COMPLETED
                               --lỗi--> EDITING          |      --va chạm--> FAULT
    READY --sửa sa bàn--> EDITING (kết quả lập đường cũ bị hủy)   --dừng--> STOPPING --> STOPPED
    READY --xem trước--> PREPARING_PREVIEW --xong--> PREVIEW --> READY
                         --hủy/lỗi/hết giờ--> READY

Mô phỏng chạy trên bản sao kịch bản; xuất phát trong sa bàn không bị thay đổi.
Lập đường và chuẩn bị xem trước dùng chung một worker; hủy tác vụ phát tín hiệu
tới vòng tìm kiếm/mô phỏng. Kết quả trễ của tác vụ cũ không được áp dụng vào phiên mới.
Phản hồi giả có thể thêm trễ/nhiễu/mất mẫu; cấu hình mặc định là lý tưởng.
Đóng phiên ngừng đồng hồ mô phỏng; đây không phải phép thử phanh phần cứng.

Nhánh chạy (24/09/2026, `application/vehicle_link.py`, docs/CHE_DO_QUAN_SAT.md): mặc định SIM là hành vi giai
đoạn 0 ở trên, không đổi. `set_vehicle_link()` chọn VEHICLE_IO (lệnh bám quỹ đạo đi qua `VehicleIO`, sự kiện dừng
của VehicleIO → dừng an toàn) hoặc OBSERVE (tính đường/lệnh và ghi log, không gửi lệnh nào; người lái cầm lái).
Khi đó `world` là thế giới gương: trạng thái lấy từ telemetry + nguồn tư thế, không tích phân lệnh. Xem trước và
lái tay luôn là mô phỏng giai đoạn 0.

Sự kiện dừng trong log (02/10/2026, T13; chỉ kiểm với bo mô phỏng và cổng serial GIẢ): qua VehicleIO, mọi quyết định
dừng của phiên (mỗi phần tử của `safety_events`, yêu cầu dừng khi đang chạy kèm mã và nguồn, đặt lại khi đang chạy, va
chạm hình học) còn thành một dòng ``session_stop`` trong events.csv của `run_link` (`VehicleLink.log_session_event`),
ghi trước `end_run`. Không gửi gì thêm tới bo. Nhánh SIM không có log VehicleIO và không đổi.

Giới hạn đổi chiều theo kịch bản (02/10/2026, T12; application/cusp_policy.py): có `acceptance_thresholds` (run_app.py,
ui.lidar_app) thì tệp sa bàn có trường `acceptance` nhận giới hạn của kịch bản nghiệm thu đó trong tệp ngưỡng, đọc một
lần lúc dựng phiên hay `replace_scenario` (tệp ngưỡng hỏng → AcceptanceTagError, phiên giữ nguyên); `cusp_policy` (cờ)
chỉ siết thêm. Mặc định None: bỏ qua thẻ, như trước (phát lại, công cụ, test cũ).
"""
from __future__ import annotations

import copy
import math
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path

from autopark.control.tracker import TrackerOutput, TrackerParams, TrajectoryTracker
from autopark.application.cusp_policy import (AcceptanceCuspRule, CuspCheck, CuspLimit, CuspPolicy, check_cusps,
                                              read_acceptance_rule, resolve_cusp_limit)
from autopark.application.layouts import scatter_parked_cars
from autopark.application.vehicle_link import DriveMode, VehicleLink, VehicleLinkError
from autopark.domain.computation import ComputationCancelled, ComputationControl, ComputationTimedOut
from autopark.domain.types import Obstacle, ParkingMode, ParkingSlot, Pose, Scenario, VehicleConfig, clamp
from autopark.evaluation.logger import RunLog
from autopark.geometry.footprint import CollisionResult, body_polygon, check_pose
from autopark.planning.hybrid_astar import PlannerParams, PlanResult
from autopark.planning.parking import plan_parking
from autopark.planning.trajectory import Trajectory
from autopark.simulation.rollout import RolloutResult, RunReport, pose_error, rollout
from autopark.simulation.world import SimWorld, StepResult
from autopark.simulation.feedback import FeedbackConfig, SimFeedback
from autopark.domain.sensors import SafetyEvent, SourceStamp

from shapely.geometry import Polygon


class SessionState(str, Enum):
    EDITING = "EDITING"
    PLANNING = "PLANNING"
    READY = "READY"
    PREPARING_PREVIEW = "PREPARING_PREVIEW"
    PREVIEW = "PREVIEW"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    FAULT = "FAULT"
    MANUAL = "MANUAL"

    @property
    def label(self) -> str:
        return {
            "EDITING": "Đang chỉnh sa bàn", "PLANNING": "Đang tính đường", "READY": "Sẵn sàng",
            "PREPARING_PREVIEW": "Đang chuẩn bị xem trước", "PREVIEW": "Xem trước",
            "RUNNING": "Đang đỗ", "STOPPING": "Đang dừng", "STOPPED": "Đã dừng",
            "COMPLETED": "Đỗ xong", "FAULT": "Lỗi", "MANUAL": "Lái tay",
        }[self.value]


class SessionError(RuntimeError):
    pass


@dataclass
class ManualTargets:
    speed: float = 0.0
    steer: float = 0.0


@dataclass(frozen=True)
class PoseCheck:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    collision: CollisionResult | None = None

    def describe(self) -> str:
        if self.ok:
            return "Hợp lệ" + (f" (hở {self.collision.min_clearance * 100:.1f} cm)" if self.collision else "")
        return "; ".join(self.reasons)


EDITABLE_STATES = (SessionState.EDITING, SessionState.READY)


class Session:
    PHYSICS_DT = 0.005            # s (tài liệu 6.2: 5–10 ms)
    CONTROL_EVERY = 4             # 50 Hz bám đường
    MAX_STEPS_PER_ADVANCE = 400   # tối đa 2 s mô phỏng mỗi lần gọi advance()
    LOG_EVERY_STEPS = 4
    MAX_RUN_TIME = 180.0          # s mô phỏng
    PREVIEW_TIME_LIMIT = 15.0     # s thời gian thực, cho phép hủy trong lúc chuẩn bị

    def __init__(self, scenario: Scenario, cfg: VehicleConfig,
                 planner_params: PlannerParams | None = None,
                 tracker_params: TrackerParams | None = None,
                 feedback_config: FeedbackConfig | None = None, *,
                 cusp_policy: CuspPolicy | None = None, acceptance_thresholds: str | Path | None = None):
        self.scenario = scenario
        self.cfg = cfg
        self.scenario.sync_goal(cfg)
        self.planner_params = planner_params or PlannerParams()
        self.tracker_params = tracker_params or TrackerParams()
        self.state = SessionState.EDITING
        self.world: SimWorld | None = None
        self.targets = ManualTargets()
        self.realtime_factor = 1.0
        self.lagging = False
        self.log = RunLog()
        self._accumulator = 0.0
        self.speed_step = 0.02
        self.steer_step = math.radians(2.0)
        # lập đường
        self.trajectory: Trajectory | None = None
        self.plan_result: PlanResult | None = None
        self.plan_version = 0
        self._executor: ThreadPoolExecutor | None = None
        self._closed = False
        self._plan_future: Future | None = None
        self._plan_control: ComputationControl | None = None
        self._pending_plan_version = 0
        # xem trước / chạy
        self.preview: RolloutResult | None = None
        self.preview_error = ""
        self._preview_future: Future | None = None
        self._preview_control: ComputationControl | None = None
        self._preview_key: tuple | None = None
        self._pending_preview_key: tuple | None = None
        self.tracker: TrajectoryTracker | None = None
        self.last_output: TrackerOutput | None = None
        self.report: RunReport | None = None
        self.stop_reason = ""
        self.feedback_config = feedback_config or FeedbackConfig()
        # số lần đổi chiều: giới hạn và mức cảnh báo (T12, application/cusp_policy.py; mặc định không chặn)
        self.cusp_policy = cusp_policy or CuspPolicy()
        # giới hạn theo kịch bản nghiệm thu mà tệp sa bàn gắn (02/10/2026); None = bỏ qua thẻ (phát lại, công cụ)
        self.acceptance_thresholds = None if acceptance_thresholds is None else Path(acceptance_thresholds)
        self.acceptance_rule: AcceptanceCuspRule | None = self._acceptance_rule_for(self.scenario)
        self.feedback: SimFeedback | None = None
        self.safety_events: list[SafetyEvent] = []
        self.run_events: list[dict] = []
        self.run_snapshot: dict | None = None
        self.path_invalidated = False
        self._stop_outcome = SessionState.STOPPED
        # nhánh chạy: None = SIM (giai đoạn 0); run_link = liên kết của lần chạy kín vòng gần nhất mà log hiện tại
        # thuộc về (giữ để xuất log; None sau lái tay hoặc chạy SIM)
        self.vehicle_link: VehicleLink | None = None
        self.run_link: VehicleLink | None = None
        self.start_source = "manual"      # T2: điểm xuất phát do người đặt hay lấy từ định vị LiDAR (set_start)

    # ------------------------------------------------------------------ nhánh chạy
    @property
    def drive_mode(self) -> DriveMode:
        return DriveMode.SIM if self.vehicle_link is None else self.vehicle_link.mode

    def set_vehicle_link(self, link: VehicleLink | None) -> None:
        """Chọn nhánh chạy cho lần Bắt đầu đỗ tới: None = SIM (mặc định). Chỉ đổi khi đang chỉnh hoặc sẵn sàng."""
        self._require_editable()
        old = self.vehicle_link
        if old is not None and old is not link:
            old.close()                   # log trong bộ nhớ vẫn còn để xuất (run_link)
        self.vehicle_link = link

    # ------------------------------------------------------------------ chỉnh sa bàn
    def _require_editable(self) -> None:
        if self._closed:
            raise SessionError("Phiên đã đóng")
        if self.state not in EDITABLE_STATES:
            raise SessionError(f"Chỉ chỉnh sa bàn khi đang chỉnh hoặc sẵn sàng (đang {self.state.label})")

    def _invalidate(self) -> None:
        self.plan_version += 1
        self.trajectory = None
        self.plan_result = None
        self.preview = None
        self._preview_key = None
        self.preview_error = ""
        self.report = None
        if self.state == SessionState.READY:
            self.state = SessionState.EDITING

    def replace_scenario(self, scenario: Scenario, cfg: VehicleConfig) -> None:
        self._require_editable()
        # T12 theo kịch bản: giới hạn của tệp mới đọc TRƯỚC, lỗi (AcceptanceTagError) thì phiên giữ nguyên. Đổi xe
        # (`set_vehicle`) đưa lại chính kịch bản đang mở: giữ giới hạn đã đọc, không đọc lại tệp ngưỡng.
        new = scenario is not self.scenario
        rule = self._acceptance_rule_for(scenario) if new else self.acceptance_rule
        self.scenario = scenario
        self.cfg = cfg
        if new:
            # T2: kịch bản mới mang điểm xuất phát của tệp. Đổi xe giữ nguyên điểm xuất phát nên giữ cả nguồn của nó
            # (sửa 02/10/2026 sau review gộp đợt 2: trước đó đổi xe ghi "manual" cho điểm lấy từ định vị LiDAR).
            self.start_source = "manual"
        self.scenario.sync_goal(cfg)
        self.log.clear()
        self._invalidate()
        self.acceptance_rule = rule

    def set_vehicle(self, cfg: VehicleConfig, path: str | Path | None = None) -> None:
        """Đổi cấu hình xe của phiên (thêm 02/10/2026, ô "Cấu hình xe" của giao diện; xe nghiệm thu 0,10 m/s). Chỉ khi
        đang chỉnh hoặc sẵn sàng; cấu hình hỏng → SessionError. `path`: tệp xe, ghi vào kịch bản để Lưu trỏ đúng tệp.
        Như `replace_scenario`: đích tính lại cho xe mới, đường và xem trước bị hủy, log xóa. Điểm xuất phát và nguồn
        của nó (`start_source`, T2) giữ nguyên. Không đụng `vehicle_link` (giao diện tự chọn lại bo mô phỏng theo tệp
        xe)."""
        self._require_editable()
        problems = cfg.validate()
        if problems:
            raise SessionError("Cấu hình xe không hợp lệ: " + "; ".join(problems))
        if path is not None:
            self.scenario.vehicle_config_path = Path(path).resolve()
        self.replace_scenario(self.scenario, cfg)

    def set_start(self, pose: Pose, *, source: str = "manual") -> None:
        """`source` (T2, 02/10/2026): "manual" (người đặt) hoặc "lidar_localize" (lấy từ định vị LiDAR; khi đó kiểm
        START so tư thế đo với điểm xuất phát không còn là kiểm độc lập). Ghi vào `run_snapshot["start_source"]`."""
        self._require_editable()
        if not (source == "manual" and pose == self.scenario.start):
            self.start_source = source        # đặt lại đúng điểm cũ (vd. "Chọn lại vị trí") không đổi nguồn
        self.scenario.start = pose
        self.scenario.sync_goal(self.cfg)   # đỗ song song chọn hướng theo hướng xe
        self._invalidate()

    def set_goal_pose(self, pose: Pose) -> None:
        self._require_editable()
        self.scenario.slot = None
        self.scenario.goal = replace(self.scenario.goal, pose=pose)
        self._invalidate()

    def set_slot(self, slot: ParkingSlot) -> None:
        self._require_editable()
        self.scenario.slot = slot
        self.scenario.sync_goal(self.cfg)
        self._invalidate()

    def set_mode(self, mode: ParkingMode) -> None:
        self._require_editable()
        self.scenario.mode = mode
        self.scenario.sync_goal(self.cfg)
        self._invalidate()

    def add_obstacle(self, obstacle: Obstacle | None = None) -> Obstacle:
        self._require_editable()
        if obstacle is None:
            cx, cy = self.scenario.bounds.center
            obstacle = Obstacle(self.scenario.next_obstacle_id(), cx, cy, 0.3, 0.3, 0.0)
        if self.scenario.obstacle_by_id(obstacle.id) is not None:
            raise SessionError(f"Vật cản {obstacle.id} đã tồn tại")
        self.scenario.obstacles.append(obstacle)
        self._invalidate()
        return obstacle

    def update_obstacle(self, obstacle: Obstacle) -> None:
        self._require_editable()
        for i, o in enumerate(self.scenario.obstacles):
            if o.id == obstacle.id:
                self.scenario.obstacles[i] = obstacle
                self._invalidate()
                return
        raise SessionError(f"Không có vật cản {obstacle.id}")

    def remove_obstacle(self, obstacle_id: str) -> None:
        self._require_editable()
        before = len(self.scenario.obstacles)
        self.scenario.obstacles = [o for o in self.scenario.obstacles if o.id != obstacle_id]
        if len(self.scenario.obstacles) == before:
            raise SessionError(f"Không có vật cản {obstacle_id}")
        self._invalidate()

    def scatter_cars(self, seed: int | None = None) -> None:
        """Atomically replace parked-car poses and invalidate the old trajectory."""
        self._require_editable()
        seed = self.scenario.seed + 1 if seed is None else seed
        try:
            obstacles = scatter_parked_cars(self.scenario, self.cfg, seed)
        except ValueError as exc:
            raise SessionError(str(exc)) from exc
        self.scenario.obstacles = obstacles
        self.scenario.seed = seed
        self._invalidate()

    # ------------------------------------------------------------------ kiểm tra
    def _check_pose(self, pose: Pose, label: str) -> PoseCheck:
        col = check_pose(self.cfg, pose, self.scenario.obstacles, self.scenario.bounds)
        reasons = []
        if col.out_of_bounds:
            reasons.append(f"{label} ra ngoài sa bàn")
        if col.collides:
            reasons.append(f"{label} chạm " + ", ".join(col.obstacle_ids))
        return PoseCheck(ok=not reasons, reasons=reasons, collision=col)

    def start_check(self) -> PoseCheck:
        return self._check_pose(self.scenario.start, "Xuất phát")

    def goal_check(self) -> PoseCheck:
        """Đích không hợp lệ và không tìm được đường là hai kết quả riêng (mục 5.2)."""
        check = self._check_pose(self.scenario.goal.pose, "Đích")
        if self.scenario.slot is not None and not self.scenario.slot.fits_vehicle(self.cfg):
            return PoseCheck(False, [*check.reasons, "Ô đỗ nhỏ hơn thân xe"], check.collision)
        return check

    def footprint_inside_slot(self, pose: Pose, tolerance: float = 0.01) -> bool | None:
        if self.scenario.slot is None:
            return None
        slot_poly = Polygon(self.scenario.slot.corners()).buffer(tolerance)
        return slot_poly.contains(body_polygon(self.cfg, pose))

    # ------------------------------------------------------------------ lập đường
    def _worker(self) -> ThreadPoolExecutor:
        if self._closed:
            raise SessionError("Phiên đã đóng")
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autopark")
        return self._executor

    @staticmethod
    def _calculate_plan(scenario, cfg, planner_params, tracker_params, max_run_time,
                        control: ComputationControl) -> PlanResult:
        try:
            control.check()
            return plan_parking(scenario, cfg, planner_params, tracker_params=tracker_params,
                                max_run_time=max_run_time, control=control)
        except ComputationCancelled:
            return PlanResult("CANCELLED", "Đã hủy tính đường")
        except ComputationTimedOut:
            return PlanResult("TIMEOUT", "Đã hết thời gian tính đường")
        except Exception as exc:  # lỗi thuật toán phải khác với không tìm được đường
            return PlanResult("ERROR", f"Lỗi lập đường: {exc!r}")

    def plan_sync(self) -> PlanResult:
        self._require_editable()
        control = ComputationControl().with_timeout(self.planner_params.time_limit)
        self._invalidate()
        version = self.plan_version
        self.state = SessionState.PLANNING
        result = self._calculate_plan(copy.deepcopy(self.scenario), self.cfg,
                                      copy.deepcopy(self.planner_params), copy.deepcopy(self.tracker_params),
                                      self.MAX_RUN_TIME, control)
        self._apply_plan(result, version)
        return result

    def plan_async(self) -> None:
        """Lập đường trong luồng nền; gọi `poll_plan()` định kỳ để nhận kết quả."""
        self._require_editable()
        control = ComputationControl().with_timeout(self.planner_params.time_limit)
        self._invalidate()
        version = self.plan_version
        snapshot = copy.deepcopy(self.scenario)
        cfg = self.cfg
        planner_params = copy.deepcopy(self.planner_params)
        tracker_params = copy.deepcopy(self.tracker_params)
        max_run_time = self.MAX_RUN_TIME
        self._plan_control = control
        self._pending_plan_version = version
        self._plan_future = self._worker().submit(self._calculate_plan, snapshot, cfg, planner_params,
                                                tracker_params, max_run_time, control)
        self.state = SessionState.PLANNING

    def poll_plan(self) -> PlanResult | None:
        if self.state != SessionState.PLANNING or self._plan_future is None:
            return None
        if not self._plan_future.done():
            return None
        result = self._plan_future.result()
        self._plan_future = None
        self._plan_control = None
        return self._apply_plan(result, self._pending_plan_version)

    def _apply_plan(self, result: PlanResult, version: int) -> PlanResult | None:
        if version != self.plan_version:
            # Người dùng đã sửa sa bàn trong lúc tính: bỏ kết quả cũ (mục 5.2)
            return None
        self.plan_result = result
        if result.ok:
            self.trajectory = result.trajectory
            self.path_invalidated = False
            self.state = SessionState.READY
        else:
            self.trajectory = None
            self.state = SessionState.EDITING
        return result

    def cancel_plan(self) -> None:
        if self.state == SessionState.PLANNING:
            if self._plan_control is not None:
                self._plan_control.cancel()
            if self._plan_future is not None:
                self._plan_future.cancel()  # bỏ cả việc còn đang đợi worker
            self._plan_future = None
            self._plan_control = None
            self.plan_version += 1   # kết quả về sau sẽ bị bỏ
            self.state = SessionState.EDITING

    # ------------------------------------------------------------------ xem trước
    def _preview_settings(self) -> tuple:
        return (self.plan_version, id(self.trajectory), self.cfg, copy.deepcopy(self.tracker_params),
                self.PHYSICS_DT, self.CONTROL_EVERY, self.MAX_RUN_TIME)

    def _prepare_preview(self) -> tuple:
        if self._closed or self.state != SessionState.READY or self.trajectory is None:
            raise SessionError("Chưa có đường để xem trước")
        self.preview_error = ""
        return self._preview_settings()

    def begin_preview(self) -> RolloutResult:
        """Bản đồng bộ cho mã ngoại tuyến; giao diện dùng begin_preview_async()."""
        key = self._prepare_preview()
        if self.preview is None or key != self._preview_key:
            self.preview = rollout(self.scenario, self.cfg, self.trajectory, self.tracker_params,
                                   dt=self.PHYSICS_DT, control_every=self.CONTROL_EVERY,
                                   max_time=self.MAX_RUN_TIME,
                                   control=ComputationControl().with_timeout(self.PREVIEW_TIME_LIMIT))
            self._preview_key = key
        self.state = SessionState.PREVIEW
        return self.preview

    def begin_preview_async(self) -> None:
        key = self._prepare_preview()
        if self.preview is not None and key == self._preview_key:
            self.state = SessionState.PREVIEW
            return
        self.preview = None
        self._preview_key = None
        control = ComputationControl().with_timeout(self.PREVIEW_TIME_LIMIT)
        self._preview_control = control
        self._pending_preview_key = key
        self._preview_future = self._worker().submit(
            rollout, copy.deepcopy(self.scenario), self.cfg, copy.deepcopy(self.trajectory),
            copy.deepcopy(self.tracker_params), dt=self.PHYSICS_DT, control_every=self.CONTROL_EVERY,
            max_time=self.MAX_RUN_TIME, control=control)
        self.state = SessionState.PREPARING_PREVIEW

    def poll_preview(self) -> RolloutResult | None:
        if self.state != SessionState.PREPARING_PREVIEW or self._preview_future is None:
            return None
        if not self._preview_future.done():
            return None
        future, key = self._preview_future, self._pending_preview_key
        self._preview_future = None
        self._preview_control = None
        self.state = SessionState.READY
        try:
            result = future.result()
        except (ComputationCancelled, ComputationTimedOut) as exc:
            self.preview_error = str(exc)
            return None
        except Exception as exc:
            self.preview_error = f"Không tính được xem trước: {exc!r}"
            return None
        if key != self._preview_settings():
            self.preview_error = "Cấu hình đã thay đổi; hãy xem trước lại"
            return None
        self.preview = result
        self._preview_key = key
        self.state = SessionState.PREVIEW
        return result

    def end_preview(self) -> None:
        if self.state in (SessionState.PREVIEW, SessionState.PREPARING_PREVIEW):
            if self._preview_control is not None:
                self._preview_control.cancel()
            if self._preview_future is not None:
                self._preview_future.cancel()
            self._preview_future = None
            self._preview_control = None
            self.state = SessionState.READY

    def close(self) -> None:
        """Dừng tác vụ khi đóng cửa sổ; không chặn luồng giao diện để join worker."""
        self.cancel_plan()
        self.end_preview()
        self._closed = True
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
        links = [self.vehicle_link] + ([self.run_link] if self.run_link is not self.vehicle_link else [])
        for link in links:
            if link is not None:
                link.close()              # VEHICLE_IO còn phiên: gửi enable=0 + DISARM trước khi đóng

    # ------------------------------------------------------------------ chạy kín vòng
    def _acceptance_rule_for(self, scenario: Scenario) -> AcceptanceCuspRule | None:
        """Giới hạn của kịch bản nghiệm thu mà `scenario` gắn (trường acceptance), đọc từ `acceptance_thresholds`; None
        khi phiên không có tệp ngưỡng hay kịch bản không gắn. Tệp ngưỡng hỏng hay thiếu khóa → AcceptanceTagError."""
        if self.acceptance_thresholds is None or scenario.acceptance is None:
            return None
        return read_acceptance_rule(scenario.acceptance, self.acceptance_thresholds)

    def cusp_limit(self) -> CuspLimit:
        """Giới hạn đổi chiều có hiệu lực (T12): `cusp_policy` (cờ, hàm dựng) gộp với `acceptance_rule`; cờ chỉ siết."""
        return resolve_cusp_limit(self.cusp_policy, self.acceptance_rule)

    def cusp_check(self) -> CuspCheck | None:
        """Số lần đổi chiều của đường đang có so với giới hạn có hiệu lực (`cusp_limit`, T12); None khi chưa có
        đường."""
        if self.trajectory is None:
            return None
        limit = self.cusp_limit()
        return check_cusps(self.trajectory, limit.policy, origin=limit.origin)

    def start_run(self) -> None:
        if self._closed:
            raise SessionError("Phiên đã đóng")
        if self.state != SessionState.READY or self.trajectory is None or not self.trajectory.valid or self.path_invalidated:
            raise SessionError("Chưa có đường để chạy")
        chk = self.start_check()
        if not chk.ok:
            raise SessionError("Không bắt đầu được: " + chk.describe())
        link = self.vehicle_link
        limit = self.cusp_limit()
        cusps = check_cusps(self.trajectory, limit.policy, origin=limit.origin)
        if cusps.refused:
            # T12: đường đổi chiều quá giới hạn — từ chối TRƯỚC mọi I/O với bo; giữ READY và đường (xem trước vẫn được)
            if link is not None:
                link.record_refused_start("START_TOO_MANY_CUSPS", cusps.describe())
            raise SessionError("Không bắt đầu được: " + cusps.describe())
        if link is not None:
            # "Trước START kiểm tra lại trạng thái thực" (kế hoạch mục 9): lỗi → không đổi gì, bo không bị ARM.
            try:
                world = link.begin_run(copy.deepcopy(self.scenario), self.cfg, self.PHYSICS_DT)
            except VehicleLinkError as exc:
                raise SessionError(f"Không bắt đầu được ({link.mode.label}): {exc}") from exc
            if self.run_link is not None and self.run_link is not link:
                self.run_link.close()
            self.world = world
        else:
            self.world = SimWorld(copy.deepcopy(self.scenario), self.cfg, dt=self.PHYSICS_DT)
        self.run_link = link
        self.tracker = TrajectoryTracker(self.trajectory, self.cfg, self.tracker_params)
        self.targets = ManualTargets()
        self.last_output = None
        self.report = None
        self.stop_reason = ""
        self._stop_outcome = SessionState.STOPPED
        self._accumulator = 0.0
        self.lagging = False
        self.log.clear()
        from dataclasses import asdict
        # Phản hồi giả chỉ dùng ở SIM; qua VehicleIO trạng thái đến từ telemetry + nguồn tư thế.
        self.feedback = SimFeedback(self.feedback_config, self.scenario.seed) if link is None else None
        self.safety_events.clear()
        self.run_events.clear()
        self.run_snapshot = copy.deepcopy({
            "scenario": self.scenario.to_dict(), "vehicle": self.cfg.to_dict(),
            "planner": asdict(self.planner_params), "tracker": asdict(self.tracker_params),
            "feedback": asdict(self.feedback_config), "trajectory": asdict(self.trajectory),
            "physics_dt": self.PHYSICS_DT, "control_every": self.CONTROL_EVERY,
            "max_run_time": self.MAX_RUN_TIME,
            "cusps": cusps.to_dict(),            # T12: số lần đổi chiều đã lập và chính sách lúc bắt đầu
            "start_source": self.start_source,   # T2: "manual" hoặc "lidar_localize"
        })
        if self.acceptance_rule is not None:
            # T12 theo kịch bản: nguồn giới hạn, khóa, tệp ngưỡng (đường dẫn, sha256) đã dùng; tệp không gắn thì không có
            self.run_snapshot["cusp_rule"] = limit.to_dict()
        if link is not None:
            # Khóa này đánh dấu lần chạy qua VehicleIO: gói của nó phát lại bằng log (T9, replay_vehicle_run), không tái
            # mô phỏng như nhánh SIM.
            self.run_snapshot["vehicle_link"] = copy.deepcopy(link.describe())
        self.state = SessionState.RUNNING

    def _log_session_event(self, t: float, source: str, code: str, message: str, action: str = "STOP") -> None:
        """T13: ghi một quyết định dừng của phiên thành dòng session_stop trong events.csv của lần chạy qua VehicleIO.
        Nhánh SIM (run_link None) không có log VehicleIO: không làm gì. Không gửi gì tới bo, không ném lỗi."""
        if self.run_link is not None:
            self.run_link.log_session_event(t, source, code, message, action=action)

    def _add_safety_event(self, event: SafetyEvent, detail: str = "") -> None:
        """Thêm vào `safety_events` và ghi đúng sự kiện đó thành dòng session_stop (cùng mã, nguồn, t, action).
        `detail` chỉ nối vào message của dòng log; SafetyEvent giữ nguyên, nên gói replay SIM không đổi."""
        self.safety_events.append(event)
        self._log_session_event(event.stamp.t, event.stamp.source_id, event.code, event.message + detail, event.action)

    def _safety_stop(self, code: str, message: str, source: str = "sim_safety", *, detail: str = "") -> None:
        # "sim_safety": tên cũ (giai đoạn 0) của lớp an toàn trong Session, dùng cả khi chạy qua VehicleIO; không có
        # nghĩa là sự kiện mô phỏng.
        assert self.world is not None
        self._add_safety_event(SafetyEvent(SourceStamp(source, self.world.time), code, message), detail)
        self.path_invalidated = True
        if self.trajectory is not None:
            self.trajectory.valid = False
        self.preview = None
        self._preview_key = None
        self.plan_version += 1
        self.request_stop(message, record=False)

    def inject_obstacle(self, obstacle: Obstacle) -> None:
        """Nguồn map giả: mọi vật cản mới đều buộc phanh rồi chờ lập lại đường."""
        if self._closed or self.state not in (SessionState.RUNNING, SessionState.STOPPING) or self.world is None:
            raise SessionError("Chỉ chèn vật cản giả khi đang chạy")
        obstacle = Obstacle.from_dict(obstacle.to_dict())
        if self.scenario.obstacle_by_id(obstacle.id) is not None:
            raise SessionError("ID vật cản đã tồn tại")
        # STOP trước, cập nhật map sau; không gọi planner trong lúc phanh. Mô tả vật chỉ vào dòng log VehicleIO.
        self._safety_stop("MAP_CHANGED", "Vật cản mới: dừng, cập nhật và chờ lập lại đường",
                          detail=f" (vật {obstacle.id} tại ({obstacle.cx:.2f}, {obstacle.cy:.2f}) m, "
                                 f"{obstacle.width * 100:.0f}×{obstacle.height * 100:.0f} cm)")
        self.scenario.obstacles.append(obstacle)
        self.world.scenario.obstacles.append(obstacle)
        self.run_events.append({"t": self.world.time, "kind": "obstacle", "obstacle": obstacle.to_dict()})

    def inject_data_loss(self) -> None:
        if self.run_link is not None and self.state in (SessionState.RUNNING, SessionState.STOPPING):
            raise SessionError("Đang chạy qua VehicleIO: không có phản hồi giả để ngắt")
        if self._closed or self.state not in (SessionState.RUNNING, SessionState.STOPPING) or self.feedback is None or self.world is None:
            raise SessionError("Chỉ ngắt phản hồi giả khi đang chạy")
        self.feedback.lost = True
        self.run_events.append({"t": self.world.time, "kind": "data_loss"})

    def request_stop(self, reason: str = "Người dùng yêu cầu dừng", *, record: bool = True, code: str = "USER_STOP",
                     source: str = "user") -> None:
        """Đang chạy: sang STOPPING với lý do `reason`; lái tay: phanh. `record=False` khi gọi từ `_safety_stop` (sự
        kiện đã vào `safety_events` và đã ghi log).

        T13 (02/10/2026): `code`/`source` là mã và nguồn của dòng session_stop ghi vào events.csv của lần chạy qua
        VehicleIO; mặc định USER_STOP/user (nút Dừng, phím Esc). Yêu cầu dừng không vào `safety_events`. Đang STOPPING
        thì không ghi gì, nên yêu cầu lặp lại không làm dội dòng. Qua VehicleIO, mục "stop" của `run_events` mang thêm
        code/source khi khác mặc định, để phát lại log (T9) dựng lại đúng dòng; dừng của người dùng và mọi lần chạy SIM
        giữ nguyên {t, kind, reason}."""
        if self.state == SessionState.RUNNING:
            if record and self.world is not None:
                entry = {"t": self.world.time, "kind": "stop", "reason": reason}
                if self.run_link is not None and (code, source) != ("USER_STOP", "user"):
                    entry.update(code=code, source=source)
                self.run_events.append(entry)
                self._log_session_event(self.world.time, source, code, reason)
            self.stop_reason = reason
            self.state = SessionState.STOPPING
        elif self.state == SessionState.MANUAL:
            self.brake()

    def reset(self) -> None:
        """Bỏ lần chạy hiện tại; về READY nếu đường còn hợp lệ, không thì về EDITING."""
        if self.state == SessionState.PLANNING:
            self.cancel_plan()
            return
        if self.state == SessionState.PREPARING_PREVIEW:
            self.end_preview()
            return
        if self.state == SessionState.STOPPING or (self.simulating and self.world is not None
                                                  and abs(self.world.state.speed) > 1e-9):
            raise SessionError("Phải dừng hẳn trước khi đặt lại")
        if self.state == SessionState.RUNNING and self.run_link is not None and self.world is not None:
            self._log_session_event(self.world.time, "user", "USER_RESET", "Đặt lại khi đang chạy")   # trước end_run
            self.run_link.end_run(self.world.time, "RESET", "Đặt lại khi đang chạy")   # VEHICLE_IO: DISARM
        if self.path_invalidated and self.world is not None:
            self.scenario.start = self.world.state.pose
            self._invalidate()
        self.world = None
        self.tracker = None
        self.last_output = None
        self.targets = ManualTargets()
        self.state = SessionState.READY if self.trajectory is not None else SessionState.EDITING

    def _finish_run(self, state: SessionState, reason: str, completed: bool, collision: CollisionResult | None = None) -> None:
        assert self.world is not None and self.trajectory is not None
        pe, he = pose_error(self.world.state, self.trajectory.goal)
        self.report = RunReport(completed, collision is not None and not collision.ok, self.world.time,
                                self.world.distance, self.world.state, pe, he, collision, reason,
                                bool(self.last_output and self.last_output.done))
        self.stop_reason = reason
        self.state = state
        if self.path_invalidated:
            self._add_safety_event(SafetyEvent(SourceStamp("sim_safety", self.world.time), "WAIT_REPLAN", reason,
                                               "WAIT"))
        if self.run_link is not None:
            self.run_link.end_run(self.world.time, state.value, reason)   # VEHICLE_IO: enable=0 + DISARM

    def _control_through_link(self, link: VehicleLink) -> None:
        """Một nhịp điều khiển qua VehicleIO: trạng thái ĐO (telemetry + nguồn tư thế) → bộ bám → gửi (VEHICLE_IO)
        hoặc chỉ ghi log (OBSERVE). Trạng thái cũ/thiếu → dừng an toàn như STALE_FEEDBACK của giai đoạn 0."""
        t = self.world.time
        observed, problem = link.observe(t)
        if observed is None:
            self.targets = ManualTargets(0.0, self.targets.steer)
            self._safety_stop(problem.code, problem.message, problem.stamp.source_id)
            return
        out = self.tracker.update(observed)
        self.last_output = out
        self.targets = ManualTargets(out.target_speed, out.target_steer)
        problem = link.command(t, out, observed)
        if problem is not None:
            self.targets = ManualTargets(0.0, self.targets.steer)
            self._safety_stop(problem.code, problem.message, problem.stamp.source_id)

    def _step_closed_loop(self) -> StepResult:
        assert self.world is not None and self.tracker is not None
        link = self.run_link
        if link is not None:
            if self.state == SessionState.RUNNING:
                # Telemetry/sự kiện ĐÃ tới được lấy TRƯỚC nhịp điều khiển (VehicleLink.refresh, sửa tối 24/09/2026):
                # không gửi enable=1 khi bo đã báo dừng mà sự kiện chưa được gom.
                link.refresh()
            for event in link.take_events():
                if self.state == SessionState.RUNNING:
                    self._safety_stop(event.code, event.message, event.stamp.source_id)
                else:
                    self._add_safety_event(event)
        if self.state == SessionState.RUNNING and self.world.time >= self.MAX_RUN_TIME:
            self._stop_outcome = SessionState.FAULT
            self._safety_stop("RUN_TIMEOUT", f"Quá {self.MAX_RUN_TIME:.0f} s mô phỏng mà chưa tới đích")
        control_tick = self.world.step_count % self.CONTROL_EVERY == 0
        if self.state == SessionState.RUNNING and control_tick and link is not None:
            self._control_through_link(link)
        elif self.state == SessionState.RUNNING and control_tick:
            assert self.feedback is not None
            observed = self.feedback.sample(self.world.state)
            if not self.feedback.fresh(self.world.time):
                self.targets = ManualTargets(0.0, self.targets.steer)
                malformed = observed is not None and (not observed.usable() or observed.t > self.world.time)
                if malformed:
                    self._safety_stop("INVALID_FEEDBACK", "Phản hồi không hợp lệ: dừng và chờ đánh giá lại")
                elif self.world.time >= self.feedback_config.stale_after_s:
                    self._safety_stop("STALE_FEEDBACK", "Mất hoặc cũ phản hồi: dừng và chờ đánh giá lại")
            else:
                out = self.tracker.update(observed)
                self.last_output = out
                self.targets = ManualTargets(out.target_speed, out.target_steer)
        if self.state == SessionState.STOPPING:
            self.targets = ManualTargets(0.0, self.targets.steer)
            if link is not None and control_tick:
                link.command_stop(self.world.time)
        result = self.world.step(self.targets.speed, self.targets.steer)
        # Qua VehicleIO, "đã dừng" phải là số đo MỚI (telemetry không cũ), không phải giá trị giữ lại.
        standstill = result.state.speed == 0.0 and (link is None or link.telemetry_fresh())
        if result.stopped_by_collision:
            reason = "Va chạm: " + result.collision.describe()
            # Va chạm không vào safety_events (như trước); qua VehicleIO vẫn thành một dòng session_stop.
            self._log_session_event(self.world.time, "sim_safety", "COLLISION", reason)
            self._finish_run(SessionState.FAULT, reason, False, result.collision)
        elif self.state == SessionState.STOPPING and link is not None and link.observe_only:
            # Quan sát: phần mềm không điều khiển xe nên không chờ xe dừng; kết thúc quan sát ngay.
            self._finish_run(self._stop_outcome, self.stop_reason, False)
        elif self.state == SessionState.STOPPING and standstill:
            self._finish_run(self._stop_outcome, self.stop_reason, False)
        elif self.state == SessionState.STOPPING and link is not None and link.stop_timed_out(self.world.time):
            reason = (f"Không xác nhận được xe đã dừng sau {link.params.stop_confirm_timeout_s:.1f} s kể từ lệnh "
                      f"dừng (telemetry mất/cũ hoặc xe vẫn chạy); lý do dừng: {self.stop_reason}")
            self._add_safety_event(SafetyEvent(SourceStamp("vehicle_link", self.world.time), "STOP_NOT_CONFIRMED",
                                               reason))
            self._finish_run(SessionState.FAULT, reason, False)
        elif self.state == SessionState.RUNNING and self.last_output is not None and self.last_output.done \
                and standstill:
            pe, he = pose_error(result.state, self.scenario.goal.pose)
            goal = self.scenario.goal
            if pe <= goal.tolerance_xy and abs(he) <= goal.tolerance_yaw:
                self._finish_run(SessionState.COMPLETED, "Đỗ xong", True)
            else:
                self._finish_run(SessionState.FAULT,
                                 f"Xe dừng ngoài dung sai: {pe * 100:.1f} cm / {math.degrees(he):+.1f}°",
                                 False)
        return result

    # ------------------------------------------------------------------ lái tay (P2)
    def start_manual(self) -> None:
        if self._closed:
            raise SessionError("Phiên đã đóng")
        if self.state not in EDITABLE_STATES:
            raise SessionError(f"Không lái tay khi đang {self.state.label}")
        chk = self.start_check()
        if not chk.ok:
            raise SessionError("Không bắt đầu được: " + chk.describe())
        self.world = SimWorld(copy.deepcopy(self.scenario), self.cfg, dt=self.PHYSICS_DT)
        self.targets = ManualTargets()
        self._accumulator = 0.0
        self.lagging = False
        self.log.clear()
        self.run_snapshot = None
        # Log mới là của lần lái tay (SIM giai đoạn 0): bỏ liên kết của lần chạy trước để không xuất nhầm log VehicleIO
        # của lần đó cùng log lái tay. Liên kết đang được chọn (vehicle_link) không đóng: lần Bắt đầu đỗ tới dùng lại.
        if self.run_link is not None and self.run_link is not self.vehicle_link:
            self.run_link.close()
        self.run_link = None
        self.state = SessionState.MANUAL

    def stop_manual(self) -> None:
        if self.state != SessionState.MANUAL:
            raise SessionError("Không ở chế độ lái tay")
        self.world = None
        self.targets = ManualTargets()
        self.state = SessionState.READY if self.trajectory is not None else SessionState.EDITING

    def reset_manual(self) -> None:
        if self.state != SessionState.MANUAL or self.world is None:
            raise SessionError("Không ở chế độ lái tay")
        self.world.reset()
        self.targets = ManualTargets()
        self._accumulator = 0.0
        self.log.clear()

    def set_manual_targets(self, speed: float, steer: float) -> None:
        if not all(math.isfinite(v) for v in (speed, steer)):
            raise ValueError("Lệnh phải là số hữu hạn")
        self.targets.speed = clamp(speed, -self.cfg.max_speed, self.cfg.max_speed)
        self.targets.steer = clamp(steer, -self.cfg.max_steer, self.cfg.max_steer)

    def nudge_speed(self, delta: float) -> None:
        self.set_manual_targets(self.targets.speed + delta, self.targets.steer)

    def nudge_steer(self, delta: float) -> None:
        self.set_manual_targets(self.targets.speed, self.targets.steer + delta)

    def brake(self) -> None:
        self.set_manual_targets(0.0, self.targets.steer)

    def center_steer(self) -> None:
        self.set_manual_targets(self.targets.speed, 0.0)

    # ------------------------------------------------------------------ nhịp mô phỏng
    @property
    def simulating(self) -> bool:
        return not self._closed and self.state in (SessionState.MANUAL, SessionState.RUNNING, SessionState.STOPPING)

    def advance(self, real_dt: float) -> list[StepResult]:
        """Tiến mô phỏng theo thời gian thực đã trôi (nhân realtime_factor), bước cố định. Lần chạy qua VehicleIO
        theo thời gian thực (`run_link.realtime`): bỏ qua real_dt, tiến tới `run_link.session_time_now()`."""
        if not self.simulating or self.world is None:
            return []
        if not math.isfinite(real_dt) or real_dt < 0:
            raise ValueError("real_dt phải hữu hạn và >= 0")
        if (not math.isfinite(self.realtime_factor) or self.realtime_factor <= 0
                or not math.isfinite(self.PHYSICS_DT) or self.PHYSICS_DT <= 0):
            raise ValueError("Nhịp mô phỏng và hệ số thời gian phải hữu hạn và > 0")
        link = self.run_link
        if self.state != SessionState.MANUAL and link is not None and link.realtime:
            # VehicleIO theo thời gian thực (bo thật): thời gian phiên bám đồng hồ của VehicleIO (io.now() - t0),
            # không theo real_dt của giao diện và không tua nhanh. Mỗi bước chỉ đọc byte đã có (poll không chờ), nên
            # nhịp điều khiển, hạn xác nhận dừng, MAX_RUN_TIME và t_session của log cùng bám io.now().
            self._accumulator = max(0.0, link.session_time_now() - self.world.time)
        else:
            self._accumulator += real_dt * self.realtime_factor
        results: list[StepResult] = []
        steps = 0
        while self._accumulator >= self.PHYSICS_DT and steps < self.MAX_STEPS_PER_ADVANCE and self.simulating:
            if self.state == SessionState.MANUAL:
                result = self.world.step(self.targets.speed, self.targets.steer)
            else:
                result = self._step_closed_loop()
            results.append(result)
            self._accumulator -= self.PHYSICS_DT
            steps += 1
            if self.world.step_count % self.LOG_EVERY_STEPS == 0 or not self.simulating:
                self.log.add(result.state, self.targets.speed, self.targets.steer,
                             result.collision, self.world.distance)
        self.lagging = steps >= self.MAX_STEPS_PER_ADVANCE
        if self.lagging or not self.simulating:
            self._accumulator = 0.0
        return results
