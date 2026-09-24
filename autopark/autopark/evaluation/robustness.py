"""Seeded phase-0 campaign, with independent geometry checks and explicit outcomes.

python -m autopark.evaluation.robustness --out runs/robustness --runs 240
Safety invariants decide pass/fail. Completion, safe stops, unavoidable collisions
and planner rejection are counted separately; a safe rejection is not a parking success.

Xe gốc của chiến dịch lấy từ `--vehicle-config` (mặc định configs/vehicle_default.json, GIẢ ĐỊNH – CHƯA ĐO), ví dụ
(một dòng, chạy trong D:/ap/autopark):
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.robustness --out runs\\robustness_do --vehicle-config configs\\vehicle_measured.json
Lưu ý (24/09/2026): chỉ một phần xe lấy từ tệp.
- Ca pose/swept/runtime (`varied_config`): giữ TỈ LỆ footprint của tệp (chiều dài cơ sở, bề rộng, nhô trước/sau) nhưng
  nhân chung một hệ số ngẫu nhiên 0,7–1,4; còn max_steer (22–38°), max_speed (0,06–0,30 m/s), max_accel
  (0,15–0,45 m/s²), max_decel (0,25–0,90 m/s²), max_steer_rate (35–140°/s) rút từ khoảng TUYỆT ĐỐI, KHÔNG theo tệp.
- Ca planner (`planner_case`): bề rộng và chiều dài cơ sở của tệp nhân 0,85–1,15; nhô trước/sau, max_steer, max_accel,
  max_steer_rate giữ theo tệp; max_speed (0,10–0,30 m/s) và max_decel (0,40–0,90 m/s²) rút từ khoảng tuyệt đối; sa bàn
  dựng bằng `build_cases(cfg)` với xe đã đổi cỡ, tức một phần sa bàn phóng theo xe.
Vì vậy `base_vehicle` trong manifest.json là xe GỐC trước khi đổi, không phải xe của từng ca (xem `input.vehicle` trong
cases.jsonl); chiến dịch KHÔNG kiểm giới hạn lái/tốc độ đo được của xe. Phép thử xe từ tệp trên sa bàn cố định là
`autopark.evaluation.sensitivity --plan-config`.
"""
from collections import Counter
import copy
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import random
import time
import zipfile

from autopark.application.session import Session, SessionError, SessionState
from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario
from autopark.evaluation import collision_oracle as oracle
from autopark.evaluation.hard_cases import build_cases
from autopark.evaluation.sensitivity import vehicle_config_arg
from autopark.geometry.footprint import check_motion, check_pose
from autopark.geometry.fast_collision import FastCollisionChecker
from autopark.planning.hybrid_astar import PlanResult, PlannerParams
from autopark.planning.trajectory import build_trajectory
from autopark.simulation.feedback import FeedbackConfig
from autopark.storage.run_store import environment, write_json

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VEHICLE_CONFIG = PROJECT_ROOT / "configs" / "vehicle_default.json"


def varied_config(base, rng):
    scale = rng.uniform(.7, 1.4)
    return replace(base, wheelbase=base.wheelbase * scale, width=base.width * scale,
                   front_overhang=base.front_overhang * scale, rear_overhang=base.rear_overhang * scale,
                   max_steer=math.radians(rng.uniform(22, 38)), max_speed=rng.uniform(.06, .3),
                   max_accel=rng.uniform(.15, .45), max_decel=rng.uniform(.25, .9),
                   max_steer_rate=math.radians(rng.uniform(35, 140)))


def analytic_session(base, index, seed):
    rng = random.Random(seed)
    cfg = varied_config(base, rng)
    events = ("none", "ahead_safe", "close", "side", "goal", "loss", "combined", "cusp")
    event = events[index % len(events)]
    route = ("forward", "reverse", "left", "reverse_right", "cusp")[(index // 8) % 5]
    if event == "cusp":
        route = "cusp"
    paths = {"forward": [(1.0, 0)], "reverse": [(-1.0, 0)],
             "left": [(.85, .55 * cfg.max_steer)], "reverse_right": [(-.85, -.55 * cfg.max_steer)],
             "cusp": [(.65, .4 * cfg.max_steer), (-.85, -.35 * cfg.max_steer)]}
    pose = Pose(0, 0, rng.uniform(-math.pi, math.pi))
    start = pose
    raw = []
    for distance, steer in paths[route]:
        count = math.ceil(abs(distance) / .01)
        for i in range(count + 1):
            raw.append((oracle.arc_pose(pose, distance * i / count, steer, cfg.wheelbase),
                        1 if distance > 0 else -1, steer))
        pose = raw[-1][0]
    sc = Scenario(f"runtime_{index}", Bounds(-4, -4, 4, 4), start, ParkingGoal(pose), seed=seed)
    profile = ("ideal", "mild", "moderate", "stale")[(index // 40) % 4]
    if profile == "stale" and event != "none":
        profile = "moderate"
    profiles = {"ideal": FeedbackConfig(),
                "mild": FeedbackConfig(.04, .002, math.radians(.2), .02),
                "moderate": FeedbackConfig(.08, .005, math.radians(.5), .05),
                "stale": FeedbackConfig(.25, .005, math.radians(.5), .1)}
    s = Session(sc, cfg, feedback_config=profiles[profile])
    s.PHYSICS_DT = (.0025, .005, .01)[index % 3]
    s.CONTROL_EVERY = round(.02 / s.PHYSICS_DT)
    s.MAX_RUN_TIME = 55
    trajectory = build_trajectory(raw, pose, cfg, min(.15, cfg.max_speed), min(.08, cfg.max_speed))
    s._apply_plan(PlanResult("OK", "independently generated reference arc", trajectory), s.plan_version)
    return s, {"route": route, "event": event, "profile": profile, "seed": seed, "index": index}


def inject(s, kind):
    if kind == "loss":
        s.inject_data_loss()
        return
    if kind == "combined":
        s.inject_data_loss()
    state, cfg = s.world.state, s.cfg
    direction = -1 if state.speed < 0 else 1
    stop_distance = state.speed**2 / (2 * cfg.max_decel)
    leading = cfg.wheelbase + cfg.front_overhang if direction > 0 else -cfg.rear_overhang
    gap = .5 * stop_distance if kind == "close" else stop_distance + .1
    x, y = state.pose.to_world(leading + direction * (max(gap, .0001) + .02), 0)
    if kind == "side":
        x, y = state.pose.to_world(.1, cfg.width / 2 + .2)
    if kind == "goal":
        x, y = s.scenario.goal.pose.to_world(.1, 0)
    s.inject_obstacle(Obstacle("new", x, y, .04, .04, state.pose.yaw))


def runtime_case(base, index, seed):
    s, case = analytic_session(base, index, seed)
    violations, triggered, collided_oracle = [], False, False
    min_speed_at_switch, previous_segment = None, 0
    input_description = {"scenario": s.scenario.to_dict(), "vehicle": s.cfg.to_dict(),
                         "feedback": asdict(s.feedback_config), "dt": s.PHYSICS_DT}
    s.start_run()
    previous = s.world.state
    requested_t = None
    try:
        while s.simulating:
            if not triggered and case["event"] != "none" and s.state == SessionState.RUNNING:
                at_cusp = s.last_output is not None and s.last_output.phase == "STOP_AT_CUSP"
                eligible = at_cusp if case["event"] == "cusp" else s.world.time >= 2
                if eligible:
                    inject(s, case["event"])
                    triggered, requested_t = True, s.world.time
                    if case["event"] != "loss":
                        if s.trajectory.valid or s.state != SessionState.STOPPING:
                            violations.append("map_change_did_not_invalidate_and_stop")
                        try:
                            s.plan_sync()
                            violations.append("planner_allowed_while_braking")
                        except SessionError:
                            pass
                    if case["event"] == "goal" and s.goal_check().ok:
                        violations.append("occupied_goal_accepted")
            steps = s.advance(.02)
            for step in steps:
                st = step.state
                if not st.usable():
                    violations.append("nonfinite_state")
                if abs(st.speed) > s.cfg.max_speed + 1e-10 or abs(st.steer) > s.cfg.max_steer + 1e-10:
                    violations.append("vehicle_limit_exceeded")
                if abs(st.steer - previous.steer) > s.cfg.max_steer_rate * s.PHYSICS_DT + 1e-10:
                    violations.append("steering_rate_exceeded")
                if not step.stopped_by_collision:
                    if st.speed * previous.speed < 0:
                        required_time = abs(previous.speed) / s.cfg.max_decel + abs(st.speed) / s.cfg.max_accel
                        if required_time > s.PHYSICS_DT + 1e-9:
                            violations.append("direction_change_without_braking")
                    else:
                        rate = s.cfg.max_accel if abs(st.speed) > abs(previous.speed) else s.cfg.max_decel
                        if abs(st.speed - previous.speed) > rate * s.PHYSICS_DT + 1e-9:
                            violations.append("acceleration_limit_exceeded")
                if previous.pose.distance_to(st.pose) > s.cfg.max_speed * s.PHYSICS_DT + 1e-9:
                    violations.append("position_jump")
                if not oracle.pose_ok(s.cfg, st.pose, s.world.scenario.obstacles, s.scenario.bounds):
                    collided_oracle = True
                    if case["event"] != "close":
                        violations.append("unexpected_collision_independent_oracle")
                previous = st
            if s.last_output is not None:
                out = s.last_output
                if not math.isfinite(out.target_speed) or abs(out.target_speed) > s.cfg.max_speed + 1e-10:
                    violations.append("controller_speed_limit_exceeded")
                if s.tracker.segment != previous_segment:
                    min_speed_at_switch = abs(s.world.state.speed)
                    previous_segment = s.tracker.segment
            if len(violations) > 10:
                break
        if s.state in (SessionState.STOPPED, SessionState.FAULT, SessionState.COMPLETED) and s.world.state.speed != 0:
            violations.append("terminal_state_still_moving")
        if triggered and s.report is not None and s.report.completed:
            violations.append("completed_despite_safety_stop")
        if s.report is not None and s.report.completed:
            if (s.report.position_error > s.scenario.goal.tolerance_xy
                    or abs(s.report.heading_error) > s.scenario.goal.tolerance_yaw or collided_oracle):
                violations.append("false_completion")
        if case["event"] != "none" and not triggered:
            violations.append("requested_event_not_reached")
        if case["profile"] == "ideal" and case["event"] == "none" and s.state != SessionState.COMPLETED:
            violations.append("ideal_reference_not_completed")
        if triggered and s.state == SessionState.RUNNING:
            violations.append("resumed_without_replan")
        report = s.report
        if s.state == SessionState.STOPPED and s.path_invalidated:
            stopped = s.world.state.pose
            s.reset()
            if s.scenario.start != stopped or s.trajectory is not None:
                violations.append("reset_reuses_stale_path_or_start")
            # Keep reporting the terminal result, not the post-reset editor state.
            state = "STOPPED"
        else:
            state = s.state.value
        return {"kind": "runtime", **case, "input": input_description,
                "status": state, "violations": sorted(set(violations)), "event_triggered": triggered,
                "event_t": requested_t, "oracle_collision": collided_oracle,
                "switch_speed": min_speed_at_switch,
                "report": asdict(report) if report is not None else None,
                "events": s.run_events, "safety_events": [asdict(e) for e in s.safety_events]}
    finally:
        s.close()


def geometry_case(base, index, seed, motion=False):
    rng = random.Random(seed)
    cfg = varied_config(base, rng)
    bounds = Bounds(-2, -2, 2, 2)
    pose = Pose(rng.uniform(-2.2, 2.2), rng.uniform(-2.2, 2.2), rng.uniform(-math.pi, math.pi))
    margin = rng.choice([0, .01, .04])
    distance, steer = rng.uniform(-.6, .6), rng.uniform(-cfg.max_steer, cfg.max_steer)
    anchor = oracle.arc_pose(pose, distance * rng.random(), steer, cfg.wheelbase) if motion else pose
    obstacles = [Obstacle("probe", anchor.x + rng.uniform(-.3, .3), anchor.y + rng.uniform(-.3, .3),
                          rng.uniform(.001, .5), rng.uniform(.001, .5), rng.uniform(-math.pi, math.pi))]
    if motion:
        reference = oracle.arc_ok(cfg, pose, distance, steer, obstacles, bounds, samples=81)
        endpoint = oracle.arc_pose(pose, distance, steer, cfg.wheelbase)
        actual = check_motion(cfg, pose, endpoint, obstacles, bounds).ok
        violations = ["missed_sampled_swept_collision"] if actual and not reference else []
        kind = "swept"
    else:
        reference = oracle.pose_ok(cfg, pose, obstacles, bounds, margin)
        actual = check_pose(cfg, pose, obstacles, bounds, margin).ok
        fast = FastCollisionChecker(cfg, obstacles, bounds, margin).pose_obj_ok(pose)
        violations = ["pose_checker_disagrees"] if actual != reference or fast != reference else []
        kind = "pose"
    return {"kind": kind, "index": index, "seed": seed, "violations": violations,
            "reference_clear": reference, "production_clear": actual,
            "input": {"vehicle": cfg.to_dict(), "pose": pose.to_dict(), "bounds": bounds.to_dict(),
                      "obstacles": [o.to_dict() for o in obstacles], "margin": margin,
                      "signed_distance": distance, "steer_rad": steer}}


def planner_case(base, index, seed):
    rng = random.Random(seed)
    # Vary footprint and actuator limits; do not relabel a timeout as geometrically infeasible.
    scale = rng.uniform(.85, 1.15)
    cfg = replace(base, width=base.width * scale, wheelbase=base.wheelbase * scale,
                  max_speed=rng.uniform(.10, .3), max_decel=rng.uniform(.4, .9))
    name = ("parallel_160", "perp_aisle_170", "reverse_long_corridor", "lateral_shift")[index % 4]
    sc = build_cases(cfg)[name].scenario
    sc.seed = seed
    s = Session(copy.deepcopy(sc), cfg, PlannerParams(time_limit=6))
    violations = []
    try:
        plan = s.plan_sync()
        run_state = None
        if plan.ok:
            if not oracle.pose_ok(cfg, sc.start, sc.obstacles, sc.bounds):
                violations.append("accepted_invalid_start")
            for point in plan.trajectory.points:
                if (not oracle.pose_ok(cfg, point.pose, sc.obstacles, sc.bounds)
                        or abs(point.steer) > cfg.max_steer + 1e-10):
                    violations.append("accepted_invalid_path")
            # Independent dense interpolation between waypoints for thin obstacles.
            for a, b in zip(plan.trajectory.points, plan.trajectory.points[1:]):
                dyaw = math.atan2(math.sin(b.pose.yaw-a.pose.yaw), math.cos(b.pose.yaw-a.pose.yaw))
                for fraction in (.25, .5, .75):
                    p = Pose(a.pose.x + fraction*(b.pose.x-a.pose.x),
                             a.pose.y + fraction*(b.pose.y-a.pose.y), a.pose.yaw + fraction*dyaw)
                    if not oracle.pose_ok(cfg, p, sc.obstacles, sc.bounds):
                        violations.append("accepted_invalid_intermediate_footprint")
            s.start_run()
            while s.simulating:
                for step in s.advance(.1):
                    if not oracle.pose_ok(cfg, step.state.pose, sc.obstacles, sc.bounds):
                        violations.append("execution_collision")
            run_state = s.state.value
            if not s.report.completed:
                violations.append("accepted_plan_not_executable")
        return {"kind": "planner", "index": index, "seed": seed, "scene": name,
                "status": plan.status, "execution": run_state, "elapsed_s": plan.elapsed,
                "violations": sorted(set(violations)),
                "input": {"scenario": sc.to_dict(), "vehicle": cfg.to_dict(), "time_limit_s": 6},
                "trajectory": asdict(plan.trajectory) if plan.trajectory is not None else None}
    finally:
        s.close()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--vehicle-config", type=vehicle_config_arg, default=str(DEFAULT_VEHICLE_CONFIG),
                        help="cấu hình xe gốc (JSON như configs/vehicle_default.json, mặc định tệp đó); chỉ lấy tỉ lệ "
                             "footprint (và ở ca planner: nhô, max_steer, max_accel, max_steer_rate); tốc độ/lái/gia "
                             "tốc còn lại rút từ khoảng cố định, xem docstring")
    parser.add_argument("--seed", type=int, default=20260920)
    parser.add_argument("--poses", type=int, default=2000)
    parser.add_argument("--motions", type=int, default=600)
    parser.add_argument("--runs", type=int, default=240)
    parser.add_argument("--plans", type=int, default=40)
    parser.add_argument("--case", help="Reproduce one input, e.g. runtime:137 or swept:25")
    args = parser.parse_args(argv)
    single = None
    if args.case:
        try:
            kind, index = args.case.split(":")
            single = (kind, int(index))
            if kind not in ("pose", "swept", "runtime", "planner") or single[1] < 0:
                raise ValueError
        except ValueError:
            parser.error("--case must be KIND:NONNEGATIVE_INDEX")
    args.out.mkdir(parents=True, exist_ok=False)
    root = PROJECT_ROOT
    vehicle = args.vehicle_config
    base = vehicle.cfg
    write_json(args.out / "manifest.json", {"arguments": {**vars(args), "out": str(args.out),
                                                          "vehicle_config": str(vehicle.path)},
               "environment": environment(), "base_vehicle": base.to_dict(), "evidence": "simulation_only",
               "vehicle_config": {"path": str(vehicle.path), "sha256": vehicle.sha256},
               "source_sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (root / "autopark").rglob("*.py")}})
    with zipfile.ZipFile(args.out / "source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for folder in ("autopark", "tests"):
            for path in (root / folder).rglob("*.py"):
                archive.write(path, path.relative_to(root).as_posix())
        for name in ("pyproject.toml", "requirements-phase0.lock"):
            archive.write(root / name, name)
    totals, outcomes, failures = Counter(), Counter(), []
    start = time.perf_counter()
    with (args.out / "cases.jsonl").open("w", encoding="utf-8") as stream:
        for kind, count, fn, offset in (
            ("pose", args.poses, lambda i, seed: geometry_case(base, i, seed), 0),
            ("swept", args.motions, lambda i, seed: geometry_case(base, i, seed, True), 100000),
            ("runtime", args.runs, lambda i, seed: runtime_case(base, i, seed), 200000),
            ("planner", args.plans, lambda i, seed: planner_case(base, i, seed), 300000),
        ):
            if single is not None and single[0] != kind:
                continue
            indices = [single[1]] if single else range(count)
            for index in indices:
                seed = args.seed + offset + index
                try:
                    result = fn(index, seed)
                except Exception as exc:
                    result = {"kind": kind, "index": index, "seed": seed,
                              "violations": ["exception"], "exception": repr(exc)}
                stream.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                totals[kind] += 1
                outcomes[f"{kind}:{result.get('status', 'checked')}"] += 1
                if result["violations"]:
                    failures.append(result)
                if (index + 1) % (20 if kind in ("runtime", "planner") else 500) == 0:
                    print(kind, index + 1, "/", count, "failures", len(failures), flush=True)
    summary = {"counts": totals, "outcomes": outcomes, "violations": len(failures),
               "elapsed_s": time.perf_counter() - start,
               "note": "Planner rejection, safe stop and collision after too-close insertion are not parking success."}
    write_json(args.out / "summary.json", summary)
    write_json(args.out / "failures.json", failures)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
