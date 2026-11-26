"""Fixed, simulation-only perturbations of simple local maneuvers.

Inputs and acceptance criteria are declared before running. Vehicle dimensions,
noise levels and braking parameters are assumptions, not hardware measurements.
The builder neither imports the runner nor changes expectations after a result.
"""
from __future__ import annotations

from dataclasses import replace
import math

from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario, VehicleConfig
from autopark.evaluation.maneuver_suite_spec import EvaluationCriteria, FaultSpec, ManeuverCase
from autopark.simulation.feedback import FeedbackConfig


def _vehicle() -> VehicleConfig:
    return VehicleConfig(
        name="robustness_simulation_assumptions", wheelbase=.19, width=.14,
        front_overhang=.06, rear_overhang=.06, max_steer=math.radians(30),
        max_speed=.10, max_accel=.30, max_decel=.60,
        max_steer_rate=math.radians(90),
        notes="Simulation assumptions only; dimensions and dynamics have not been measured on the vehicle.",
    )


def _stop_criteria(vehicle: VehicleConfig, feedback: FeedbackConfig,
                   kind: str) -> EvaluationCriteria:
    # Injection -> stale detection includes one 50 Hz controller period. The
    # extra 10 ms covers two 5 ms physics samples, not an empirical relaxation.
    reaction = feedback.stale_after_s + .02 if kind == "data_loss" else 0.0
    brake_time = vehicle.max_speed / vehicle.max_decel
    brake_distance = vehicle.max_speed ** 2 / (2 * vehicle.max_decel)
    return EvaluationCriteria(
        min_clearance_m=.02, stop_speed_mps=.001,
        max_stop_delay_s=reaction + brake_time + .01,
        max_stop_distance_m=vehicle.max_speed * (reaction + .01) + brake_distance,
        hold_after_stop_s=1.0,
    )


def build_robustness_cases(seed: int = 0) -> list[ManeuverCase]:
    """Return 18 reproducible cases; the seed controls feedback RNG, not geometry.

    Each trajectory is a simple straight segment before the injected failure.
    Follow-ups require the runner to hold, prepare a new maneuver at the actual
    stopped pose, plan again, and issue another explicit start. Recovery alone
    must never resume the interrupted maneuver.
    """
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    vehicle = _vehicle()
    cases: list[ManeuverCase] = []

    def add(case_id: str, family: str, description: str, *,
            feedback: FeedbackConfig = FeedbackConfig(),
            start: Pose = Pose(0, 0, 0), goal: Pose = Pose(.45, 0, 0),
            bounds: Bounds = Bounds(-1, -1, 1, 1),
            obstacles: tuple[Obstacle, ...] = (), fault: FaultSpec | None = None,
            followup: Pose | None = None, cfg: VehicleConfig = vehicle,
            clearance: float = .02) -> None:
        criteria = (_stop_criteria(cfg, feedback, fault.kind) if fault is not None
                    else EvaluationCriteria(min_clearance_m=clearance))
        scenario = Scenario(
            name=case_id, bounds=bounds, start=start,
            goal=ParkingGoal(goal, tolerance_xy=.03, tolerance_yaw=math.radians(5)),
            obstacles=list(obstacles), seed=seed,
            notes=description + " Simulation only; no hardware acceptance claim.",
        )
        cases.append(ManeuverCase(
            case_id=case_id, family=family, description=description,
            expected="stop" if fault else "complete", scenario=scenario, vehicle=cfg,
            feedback=feedback, fault=fault, followup_goal=followup, criteria=criteria,
            sim_timeout_s=20, plan_time_limit_s=8,
        ))

    mild = FeedbackConfig(position_std_m=.001, yaw_std_rad=math.radians(.3))
    mixed = FeedbackConfig(delay_s=.02, position_std_m=.001,
                           yaw_std_rad=math.radians(.2), drop_probability=.02)
    add("robust_position_noise", "feedback_noise",
        "1 mm position standard deviation on a straight, open maneuver.",
        feedback=FeedbackConfig(position_std_m=.001))
    add("robust_heading_noise", "feedback_noise",
        "0.3 degree yaw standard deviation on a straight, open maneuver.",
        feedback=FeedbackConfig(yaw_std_rad=math.radians(.3)))
    add("robust_delay_40ms", "feedback_delay",
        "40 ms feedback delay remains below the declared 150 ms stale threshold.",
        feedback=FeedbackConfig(delay_s=.04))
    add("robust_sparse_dropouts", "feedback_dropout",
        "Independent 3 percent sample loss; a realized stale sequence must fail completion.",
        feedback=FeedbackConfig(drop_probability=.03))
    add("robust_combined_feedback", "feedback_combined",
        "20 ms delay, 1 mm/0.2 degree noise and 2 percent sample loss.", feedback=mixed)
    add("robust_reverse_feedback", "feedback_combined",
        "The same combined perturbation while reversing 35 cm.",
        feedback=mixed, goal=Pose(-.35, 0, 0))
    angle = math.radians(30)
    add("robust_rotated_feedback", "feedback_noise",
        "A 30 degree world-frame straight maneuver with mild pose noise.",
        feedback=mild, start=Pose(0, 0, angle),
        goal=Pose(.40 * math.cos(angle), .40 * math.sin(angle), angle))
    walls = (Obstacle("upper", .25, .15, 1.20, .06, kind="wall"),
             Obstacle("lower", .25, -.15, 1.20, .06, kind="wall"))
    add("robust_corridor_clearance", "clearance_perturbation",
        "5 cm nominal body-side clearance; require at least 3 cm with mild pose noise.",
        feedback=mild, obstacles=walls, clearance=.03)
    add("robust_close_map_boundary", "boundary_perturbation",
        "4 cm nominal lateral body-to-map clearance; require at least 2.5 cm.",
        feedback=mild, bounds=Bounds(-.20, -.11, .80, .11), clearance=.025)

    add("fault_data_loss_latched", "fault_data_loss",
        "Lose feedback at 0.6 s; stale feedback must cause a bounded, latched stop.",
        fault=FaultSpec("data_loss", .6))
    add("fault_data_loss_recovery", "fault_recovery",
        "Restore feedback 0.7 s after loss; observe a full hold after recovery without resuming.",
        fault=FaultSpec("data_loss", .6, recover_after_s=.7))
    blocker = Obstacle("appeared", .40, 0, .08, .30)
    add("fault_obstacle_midrun", "fault_obstacle",
        "Insert a path blocker ahead of the moving body; map change must stop before contact.",
        fault=FaultSpec("obstacle", .6, obstacle=blocker))
    add("fault_user_stop", "fault_user_stop",
        "Explicit stop at 0.6 s must brake and hold despite the unfinished goal.",
        fault=FaultSpec("user_stop", .6))
    add("fault_user_stop_slow_brake", "braking_sensitivity",
        "Repeat explicit stop with assumed deceleration reduced from 0.60 to 0.25 m/s2.",
        fault=FaultSpec("user_stop", .6), cfg=replace(vehicle, max_decel=.25))

    add("next_after_completion", "next_maneuver",
        "Finish a 30 cm move, hold, then explicitly plan and start toward 55 cm.",
        goal=Pose(.30, 0, 0), followup=Pose(.55, 0, 0))
    add("next_after_user_stop", "next_maneuver",
        "Stop the first maneuver; a separately authorized move uses the actual stopped pose.",
        fault=FaultSpec("user_stop", .6), followup=Pose(.35, 0, 0))
    add("next_after_feedback_recovery", "next_maneuver",
        "Recovery cannot resume motion; only prepare, replan and a new explicit start may do so.",
        fault=FaultSpec("data_loss", .6, recover_after_s=.7), followup=Pose(.35, 0, 0))
    add("next_after_obstacle_stop", "next_maneuver",
        "After stopping for a new obstacle, explicitly plan a reverse move with the new map retained.",
        fault=FaultSpec("obstacle", .6, obstacle=blocker), followup=Pose(-.15, 0, 0))
    return cases
