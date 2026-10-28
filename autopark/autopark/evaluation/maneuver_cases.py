"""Representative local-maneuver fixtures, with independent geometric witnesses.

The witnesses are sampled constant-curvature paths, not planner output or a claim
that a controller can track them. ``expected=complete`` is the test objective;
a timeout remains a failure to solve within budget, never proof of infeasibility.
All sizes and limits here are simulation settings, not measured vehicle limits.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import random

from autopark.domain.types import (
    Bounds, ManeuverLimits, Obstacle, ParkingGoal, Pose, Scenario, VehicleConfig,
)
from autopark.evaluation.collision_oracle import arc_pose
from autopark.evaluation.maneuver_suite_spec import ManeuverCase


@dataclass(frozen=True)
class GeometricWitness:
    """Signed arc distances and steer angles; steering may change at rest."""

    start: Pose
    arcs: tuple[tuple[float, float], ...]

    def samples(self, step_m: float = 0.002) -> list[Pose]:
        if not math.isfinite(step_m) or step_m <= 0:
            raise ValueError("step_m must be finite and positive")
        poses = [self.start]
        for distance, steer in self.arcs:
            start = poses[-1]
            count = max(1, math.ceil(abs(distance) / step_m))
            poses.extend(arc_pose(start, distance * i / count, steer, 0.19)
                         for i in range(1, count + 1))
        return poses

    @property
    def goal(self) -> Pose:
        pose = self.start
        for distance, steer in self.arcs:
            pose = arc_pose(pose, distance, steer, 0.19)
        return pose

    def mirrored(self) -> "GeometricWitness":
        return GeometricWitness(_mirror_pose(self.start),
                                tuple((d, -s) for d, s in self.arcs))

    def reversed(self) -> "GeometricWitness":
        return GeometricWitness(self.goal, tuple((-d, s) for d, s in reversed(self.arcs)))


def _vehicle() -> VehicleConfig:
    # Inline equivalent of vehicle_nghiem_thu.json: no mutable external config dependency.
    return VehicleConfig("maneuver_suite_simulation_assumptions", .19, .14, .06, .06,
                         math.radians(30), .10, .30, .60, math.radians(90),
                         "Simulation assumptions only; not measurements of a physical vehicle.")


def _mirror_pose(pose: Pose) -> Pose:
    return Pose(pose.x, 1.5 - pose.y, -pose.yaw)


def _mirror_obstacles(obstacles: list[Obstacle]) -> list[Obstacle]:
    return [replace(o, cy=1.5 - o.cy, yaw=-o.yaw) for o in obstacles]


def _fixtures(seed: int) -> list[tuple[ManeuverCase, GeometricWitness | None]]:
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    rng = random.Random(seed)
    cfg = _vehicle()
    fixtures: list[tuple[ManeuverCase, GeometricWitness | None]] = []

    def gap_jitter() -> float:
        # Seed zero preserves nominal geometry; other seeds vary obstacle clearance
        # by at most 2 mm, without changing limits or goal tolerances.
        return 0.0 if seed == 0 else rng.uniform(-.002, .002)

    def add(case_id: str, family: str, description: str, witness: GeometricWitness,
            obstacles: list[Obstacle], *, followup_goal: Pose | None = None) -> ManeuverCase:
        scenario = Scenario(description, Bounds(0, 0, 1.5, 1.5), witness.start,
                            ParkingGoal(witness.goal, .03, math.radians(5)), list(obstacles),
                            vehicle_config="inline:maneuver_suite", seed=seed,
                            notes="Analytic sampled witness; controller success is evaluated separately. "
                                  "Seed varies obstacle clearance by at most 0.002 m; limits/tolerances fixed.",
                            maneuver=ManeuverLimits())
        case = ManeuverCase(case_id, family, description, "complete", scenario, cfg,
                            followup_goal=followup_goal)
        fixtures.append((case, witness))
        return case

    # The original two hand-built scenes are represented inline below. A 0.36 m
    # quarter circle exactly joins the two poses of thao_tac_cua_hep.json.
    turn = GeometricWitness(Pose(.5, .52, 0), ((.36 * math.pi / 2, math.atan(.19 / .36)),))
    turn_obstacles = [Obstacle("lower_wall", .6, .34, 1, .08, kind="wall"),
                      Obstacle("outer_wall", 1.06 + gap_jitter(), .87, .08, 1.14, kind="wall"),
                      Obstacle("inner_corner", .36, 1.11, .52, .66, kind="wall")]
    add("turn_left_forward", "corner", "Forward left 90-degree narrow corner (original scene)",
        turn, turn_obstacles)
    add("turn_right_forward", "corner", "Forward right 90-degree narrow corner (mirrored geometry)",
        turn.mirrored(), _mirror_obstacles(turn_obstacles))
    add("turn_left_reverse", "corner", "Reverse through the left corner from its exit pose",
        turn.reversed(), turn_obstacles)
    add("turn_right_reverse", "corner", "Reverse through the right corner from its exit pose",
        turn.mirrored().reversed(), _mirror_obstacles(turn_obstacles))
    wider = [replace(o, cx=o.cx + .025) if o.id == "outer_wall" else o for o in turn_obstacles]
    add("turn_left_outer_clearance", "corner", "Left corner with 25 mm more outer nose clearance",
        turn, wider)
    # Inner corner extension exercises the rear inner corner independently of the outer wall.
    inner = [replace(o, width=o.width + .02) if o.id == "inner_corner" else o for o in turn_obstacles]
    add("turn_right_inner_clearance", "corner", "Right corner with inner wall extended by 10 mm",
        turn.mirrored(), _mirror_obstacles(inner))

    def doorway(width: float) -> list[Obstacle]:
        half_gap = width / 2 + gap_jitter()
        return [Obstacle("door_lower", .76, (.75 - half_gap) / 2, .06, .75 - half_gap, kind="wall"),
                Obstacle("door_upper", .76, (2.25 + half_gap) / 2, .06, .75 - half_gap, kind="wall")]

    straight_door = GeometricWitness(Pose(.40, .75, 0), ((.47, 0),))
    add("door_forward_center", "doorway", "Forward through a 200 mm doorway", straight_door, doorway(.20))
    add("door_reverse_center", "doorway", "Reverse through a 200 mm doorway", straight_door.reversed(), doorway(.20))
    add("door_forward_offset_left", "doorway", "Doorway with 15 mm left body offset",
        GeometricWitness(Pose(.40, .765, 0), ((.47, 0),)), doorway(.20))
    add("door_forward_offset_right", "doorway", "Doorway with 15 mm right body offset",
        GeometricWitness(Pose(.40, .735, 0), ((.47, 0),)), doorway(.20))
    add("door_forward_yaw", "doorway", "Doorway entry offset right 15 mm and yawed left 3 degrees",
        GeometricWitness(Pose(.40, .735, math.radians(3)), ((.47, 0),)), doorway(.22))

    slalom_steer = math.atan(.19 / .45)
    slalom = GeometricWitness(Pose(.42, .62, 0), ((.45 * .55, slalom_steer), (.45 * .55, -slalom_steer)))
    # Both posts intersect a direct interpolated body sweep, while the S witness
    # clears them. They therefore exercise real body routing, not decorative scenery.
    posts = [Obstacle("upper_post", .55, .77 + gap_jitter(), .05, .05),
             Obstacle("lower_post", .84, .60 - gap_jitter(), .05, .05)]
    add("columns_left_s", "columns", "Left-then-right S correction between staggered square columns", slalom, posts)
    add("columns_right_s", "columns", "Right-then-left S correction between mirrored columns",
        slalom.mirrored(), _mirror_obstacles(posts))

    def slot(width: float = .24) -> list[Obstacle]:
        wall_offset = width / 2 + .03 + gap_jitter()
        return [Obstacle("slot_upper", .48, .75 + wall_offset, .6, .06, kind="wall"),
                Obstacle("slot_lower", .48, .75 - wall_offset, .6, .06, kind="wall"),
                Obstacle("slot_back", .2, .75, .06, width + .06, kind="wall")]

    reverse_slot = GeometricWitness(Pose(.9, .75, 0), ((-.4, 0),))
    add("slot_reverse_center", "slot", "Reverse into the original narrow slot", reverse_slot, slot())
    add("slot_forward_exit", "slot", "Forward exit from the original narrow slot", reverse_slot.reversed(), slot())
    add("slot_reverse_offset", "slot", "Reverse into slot with 20 mm left offset",
        GeometricWitness(Pose(.9, .77, 0), ((-.4, 0),)), slot())
    add("slot_reverse_yaw", "slot", "Reverse into slot with 4-degree initial/final yaw",
        GeometricWitness(Pose(.9, .75, math.radians(4)), ((-.4, 0),)), slot(.26))

    # Two cusps, bounded local distance, and both front and rear sweep near walls.
    shuffle = GeometricWitness(Pose(.68, .68, 0),
                               ((.16, math.radians(25)), (-.16, -math.radians(25)), (.12, 0)))
    correction_walls = [Obstacle("rear_edge", .46, .75, .06, .45, kind="wall"),
                        Obstacle("front_edge", 1.18, .75, .06, .45, kind="wall")]
    add("correction_left_two_cusps", "correction", "Two-cusp left heading correction with front/rear walls",
        shuffle, correction_walls)
    add("correction_right_two_cusps", "correction", "Mirrored two-cusp right heading correction with end walls",
        shuffle.mirrored(), _mirror_obstacles(correction_walls))

    followup = GeometricWitness(Pose(.43, .75, 0), ((.28, 0),))
    add("followup_forward_then_reverse", "followup", "Stop after forward step, then select a nearby fixed-world reverse goal",
        followup, [], followup_goal=Pose(.51, .75, 0))

    def refuse(case_id: str, description: str, start: Pose, goal: Pose,
               obstacles: list[Obstacle] | None = None, bounds: Bounds = Bounds(0, 0, 1.5, 1.5),
               limits: ManeuverLimits | None = None) -> None:
        scenario = Scenario(description, bounds, start, ParkingGoal(goal, .03, math.radians(5)),
                            list(obstacles or []), vehicle_config="inline:maneuver_suite", seed=seed,
                            notes="Deliberately invalid request; must refuse without vehicle movement.",
                            maneuver=limits or ManeuverLimits())
        fixtures.append((ManeuverCase(case_id, "invalid_request", description, "refuse", scenario, cfg), None))

    refuse("refuse_goal_overlap", "Goal body overlaps a solid obstacle", Pose(.45, .75, 0), Pose(.85, .75, 0),
           [Obstacle("goal_block", .97, .75, .08, .12)])
    refuse("refuse_start_overlap", "Start body overlaps a solid obstacle", Pose(.45, .75, 0), Pose(.85, .75, 0),
           [Obstacle("start_block", .55, .75, .08, .12)])
    refuse("refuse_goal_body_outside", "Goal rear axle is in bounds but nose crosses the local-area boundary",
           Pose(.45, .75, 0), Pose(1.05, .75, 0))
    refuse("refuse_start_body_outside", "Start rear axle is in bounds but rear body crosses map edge",
           Pose(.04, .75, 0), Pose(.40, .75, 0))
    refuse("refuse_goal_distance", "Collision-free goal exceeds the configured local goal-distance limit",
           Pose(.35, .75, 0), Pose(1.08, .75, 0), limits=ManeuverLimits(area_half_extent_m=1.0))
    refuse("refuse_goal_tail_overlap", "Goal rear corner clips a small obstacle while rear axle remains clear",
           Pose(.45, .70, 0), Pose(.8, .75, math.radians(30)),
           [Obstacle("tail_clip", .735, .775, .025, .025)])
    return fixtures


def build_cases(seed: int = 0) -> list[ManeuverCase]:
    """Return 26 stable-ID inline cases; each call owns its mutable scenarios."""
    return [case for case, _ in _fixtures(seed)]


def build_geometric_witnesses(seed: int = 0) -> dict[str, GeometricWitness]:
    """Return fixture-construction evidence, deliberately separate from scoring."""
    return {case.case_id: witness for case, witness in _fixtures(seed) if witness is not None}
