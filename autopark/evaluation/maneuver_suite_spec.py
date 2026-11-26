"""Shared input contract for the simulation-only maneuver evaluation suite.

Cases contain snapshots, not hardware paths. Expectations describe the test's
purpose; a planner timeout is never evidence that a task is infeasible.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
import re

from autopark.domain.types import Obstacle, Pose, Scenario, VehicleConfig
from autopark.simulation.feedback import FeedbackConfig


SCHEMA_VERSION = 1
EXPECTED = ("complete", "refuse", "stop")
FAULT_KINDS = ("data_loss", "obstacle", "user_stop")


def _number(value, name: str, *, positive: bool = False) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (positive and value == 0)):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")


def _object(data, fields, name: str, required=()) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{name} must be an object")
    unknown = set(data) - set(fields)
    if unknown:
        raise ValueError(f"Unknown {name} fields: {', '.join(sorted(unknown))}")
    missing = set(required) - set(data)
    if missing:
        raise ValueError(f"Missing {name} fields: {', '.join(sorted(missing))}")


@dataclass(frozen=True)
class EvaluationCriteria:
    """Configured simulation criteria, not measured hardware acceptance limits."""

    min_clearance_m: float = 0.0
    stop_speed_mps: float = 0.001
    max_stop_delay_s: float | None = None
    max_stop_distance_m: float | None = None
    hold_after_stop_s: float = 1.0

    def __post_init__(self):
        for name in ("min_clearance_m", "stop_speed_mps"):
            _number(getattr(self, name), name)
        # A positive observation interval is required to assess no automatic
        # motion/drive after a stop; zero cannot provide that evidence.
        _number(self.hold_after_stop_s, "hold_after_stop_s", positive=True)
        for name in ("max_stop_delay_s", "max_stop_distance_m"):
            value = getattr(self, name)
            if value is not None:
                _number(value, name)


@dataclass(frozen=True)
class FaultSpec:
    kind: str
    at_s: float
    obstacle: Obstacle | None = None
    recover_after_s: float | None = None

    def __post_init__(self):
        if self.kind not in FAULT_KINDS:
            raise ValueError(f"Unsupported simulation fault: {self.kind}")
        _number(self.at_s, "fault.at_s")
        if (self.kind == "obstacle") != (self.obstacle is not None):
            raise ValueError("Only an obstacle fault must include an obstacle")
        if self.obstacle is not None and not isinstance(self.obstacle, Obstacle):
            raise ValueError("fault.obstacle must be an Obstacle")
        if self.recover_after_s is not None:
            _number(self.recover_after_s, "fault.recover_after_s", positive=True)
            if self.kind != "data_loss":
                raise ValueError("Only data_loss supports recovery")

    def to_dict(self) -> dict:
        return {"kind": self.kind, "at_s": self.at_s,
                "obstacle": None if self.obstacle is None else self.obstacle.to_dict(),
                "recover_after_s": self.recover_after_s}

    @classmethod
    def from_dict(cls, data: dict) -> "FaultSpec":
        _object(data, cls.__dataclass_fields__, "fault", ("kind", "at_s"))
        return cls(data["kind"], data["at_s"],
                   None if data.get("obstacle") is None else Obstacle.from_dict(data["obstacle"]),
                   data.get("recover_after_s"))


@dataclass(frozen=True)
class ManeuverCase:
    case_id: str
    family: str
    description: str
    expected: str
    scenario: Scenario
    vehicle: VehicleConfig
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    fault: FaultSpec | None = None
    followup_goal: Pose | None = None
    criteria: EvaluationCriteria = field(default_factory=EvaluationCriteria)
    sim_timeout_s: float = 30.0
    plan_time_limit_s: float = 8.0

    def __post_init__(self):
        for name, kind in (("scenario", Scenario), ("vehicle", VehicleConfig),
                           ("feedback", FeedbackConfig), ("criteria", EvaluationCriteria)):
            if not isinstance(getattr(self, name), kind):
                raise ValueError(f"{name} must be a {kind.__name__}")
        if self.fault is not None and not isinstance(self.fault, FaultSpec):
            raise ValueError("fault must be a FaultSpec")
        if self.followup_goal is not None and not isinstance(self.followup_goal, Pose):
            raise ValueError("followup_goal must be a Pose")
        if not isinstance(self.case_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", self.case_id):
            raise ValueError("case_id must be a safe lowercase identifier (1–80 characters)")
        if not isinstance(self.family, str) or not self.family.strip():
            raise ValueError("family must be nonempty")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be nonempty")
        if self.expected not in EXPECTED:
            raise ValueError(f"expected must be one of {EXPECTED}")
        if type(self.scenario.seed) is not int:
            raise ValueError("scenario.seed must be an integer")
        if self.vehicle.validate():
            raise ValueError("Invalid vehicle configuration")
        _number(self.sim_timeout_s, "sim_timeout_s", positive=True)
        _number(self.plan_time_limit_s, "plan_time_limit_s", positive=True)
        if self.fault is not None and self.fault.at_s >= self.sim_timeout_s:
            raise ValueError("Fault must be scheduled before the simulation timeout")
        if self.expected == "refuse" and (self.fault is not None or self.followup_goal is not None):
            raise ValueError("Refusal cases cannot require runtime faults or a follow-up")
        if self.followup_goal is not None and not all(math.isfinite(v) for v in
                                                     (self.followup_goal.x, self.followup_goal.y, self.followup_goal.yaw)):
            raise ValueError("followup_goal must be finite")

    def to_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, "case_id": self.case_id,
                "family": self.family, "description": self.description, "expected": self.expected,
                "scenario": self.scenario.to_dict(), "vehicle": self.vehicle.to_dict(),
                "feedback": asdict(self.feedback),
                "fault": None if self.fault is None else self.fault.to_dict(),
                "followup_goal": None if self.followup_goal is None else self.followup_goal.to_dict(),
                "criteria": asdict(self.criteria), "sim_timeout_s": self.sim_timeout_s,
                "plan_time_limit_s": self.plan_time_limit_s}

    @classmethod
    def from_dict(cls, data: dict) -> "ManeuverCase":
        _object(data, {*cls.__dataclass_fields__, "schema_version"}, "case",
                ("schema_version", "case_id", "family", "description", "expected", "scenario", "vehicle"))
        if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Unsupported maneuver case schema")
        _object(data.get("feedback", {}), FeedbackConfig.__dataclass_fields__, "feedback")
        _object(data.get("criteria", {}), EvaluationCriteria.__dataclass_fields__, "criteria")
        if not isinstance(data.get("scenario"), dict) or type(data["scenario"].get("seed", 0)) is not int:
            raise ValueError("scenario must be an object with an integer seed")
        return cls(case_id=data["case_id"], family=data["family"], description=data["description"],
                   expected=data["expected"], scenario=Scenario.from_dict(data["scenario"]),
                   vehicle=VehicleConfig.from_dict(data["vehicle"]),
                   feedback=FeedbackConfig(**data.get("feedback", {})),
                   fault=None if data.get("fault") is None else FaultSpec.from_dict(data["fault"]),
                   followup_goal=None if data.get("followup_goal") is None else Pose.from_dict(data["followup_goal"]),
                   criteria=EvaluationCriteria(**data.get("criteria", {})),
                   sim_timeout_s=data.get("sim_timeout_s", 30.0),
                   plan_time_limit_s=data.get("plan_time_limit_s", 8.0))
