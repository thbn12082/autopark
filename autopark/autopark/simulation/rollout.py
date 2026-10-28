"""Chạy kín vòng ngoại tuyến: quỹ đạo + bộ bám đường + xe mô phỏng, dùng cho xem trước và kiểm thử."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

from autopark.control.tracker import TrackerOutput, TrackerParams, TrajectoryTracker
from autopark.domain.computation import ComputationControl, checkpoint, computation_scope
from autopark.domain.types import Pose, Scenario, VehicleConfig, VehicleState, wrap_angle
from autopark.geometry.footprint import CollisionResult
from autopark.planning.maneuver import runtime_problem
from autopark.planning.trajectory import Trajectory
from autopark.simulation.world import SimWorld


@dataclass
class RunReport:
    completed: bool
    collided: bool
    sim_time: float
    distance: float
    final_state: VehicleState
    position_error: float      # m tới đích
    heading_error: float       # rad
    collision: CollisionResult | None = None
    reason: str = ""
    path_finished: bool = False   # reached path end; distinct from meeting goal tolerances

    def describe(self) -> str:
        if self.collided and self.collision is not None:
            return f"Va chạm: {self.collision.describe()}"
        if not self.completed:
            return self.reason or "Chưa hoàn tất"
        return (f"Đỗ xong sau {self.sim_time:.1f} s, đi {self.distance * 100:.0f} cm; "
                f"sai số {self.position_error * 100:.1f} cm / {math.degrees(self.heading_error):+.1f}°")


@dataclass
class RolloutResult:
    states: list[VehicleState] = field(default_factory=list)      # mẫu ở nhịp điều khiển
    outputs: list[TrackerOutput] = field(default_factory=list)
    report: RunReport | None = None


def pose_error(state: VehicleState, goal: Pose) -> tuple[float, float]:
    return (math.hypot(state.pose.x - goal.x, state.pose.y - goal.y),
            wrap_angle(state.pose.yaw - goal.yaw))


def _rollout(scenario: Scenario, cfg: VehicleConfig, trajectory: Trajectory,
            tracker_params: TrackerParams | None = None, dt: float = 0.005,
            control_every: int = 4, max_time: float = 120.0) -> RolloutResult:
    world = SimWorld(copy.deepcopy(scenario), cfg, dt)
    tracker = TrajectoryTracker(trajectory, cfg, tracker_params)
    result = RolloutResult()
    target_speed = target_steer = 0.0
    completed = collided = False
    collision = None
    reason = ""
    stopping = False
    while True:
        if not stopping:
            problem = runtime_problem(scenario, cfg, world.state, world.distance, dt)
            if problem:
                stopping = True
                reason = problem[1]
        if stopping:
            target_speed = 0.0
        elif world.step_count % control_every == 0:
            checkpoint()
            out = tracker.update(world.state)
            target_speed, target_steer = out.target_speed, out.target_steer
            result.states.append(world.state)
            result.outputs.append(out)
            if out.done and abs(world.state.speed) < 1e-3:
                completed = True
                break
        step = world.step(target_speed, target_steer)
        if step.stopped_by_collision:
            collided = True
            collision = step.collision
            result.states.append(world.state)
            break
        if stopping and world.state.speed == 0.0:
            result.states.append(world.state)
            break
        if world.time >= max_time:
            reason = f"Quá {max_time:.0f} s mô phỏng mà chưa tới đích"
            break
    pe, he = pose_error(world.state, trajectory.goal)
    path_finished = completed
    if completed and (pe > scenario.goal.tolerance_xy or abs(he) > scenario.goal.tolerance_yaw):
        completed = False
        reason = f"Xe dừng ngoài dung sai: {pe * 100:.1f} cm / {math.degrees(he):+.1f}°"
    result.report = RunReport(completed, collided, world.time, world.distance, world.state, pe, he,
                              collision, reason, path_finished)
    checkpoint()
    return result


def rollout(scenario: Scenario, cfg: VehicleConfig, trajectory: Trajectory,
            tracker_params: TrackerParams | None = None, dt: float = 0.005,
            control_every: int = 4, max_time: float = 120.0, *,
            control: ComputationControl | None = None) -> RolloutResult:
    """Run offline; interruption raises so a partial rollout cannot be accepted."""
    with computation_scope(control):
        return _rollout(scenario, cfg, trajectory, tracker_params, dt, control_every, max_time)
