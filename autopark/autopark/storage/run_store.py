"""Phiên mô phỏng có snapshot và replay không chạy lại planner theo thời gian thực."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import platform
import subprocess
import sys
import zipfile


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def environment() -> dict:
    info = {"os": platform.platform(), "python": sys.version, "cpu": platform.processor(),
            "packages": {d.metadata["Name"]: d.version for d in distributions()}}
    if sys.platform == "win32":
        command = ("$c = Get-CimInstance Win32_Processor; $m = Get-CimInstance Win32_ComputerSystem; "
                   "$g = Get-CimInstance Win32_VideoController; "
                   "@{cpu=@($c.Name); ram_bytes=$m.TotalPhysicalMemory; gpu=@($g.Name)} | ConvertTo-Json -Compress")
        try:
            raw = subprocess.check_output(["powershell", "-NoProfile", "-Command", command],
                                          timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
            info["hardware"] = json.loads(raw.decode("utf-8", errors="replace"))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            info["hardware_error"] = str(exc)
    return info


def export_run(session, directory: str | Path) -> Path:
    if session.run_snapshot is None or session.world is None:
        raise ValueError("Chưa có phiên chạy tự động để xuất")
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=False)
    snapshots = path / "config_snapshot"
    snapshots.mkdir()
    snapshot = session.run_snapshot
    write_json(snapshots / "run.json", snapshot)
    write_json(snapshots / "vehicle.json", snapshot["vehicle"])
    scenario = dict(snapshot["scenario"], vehicle_config="vehicle.json")
    write_json(snapshots / "scenario.json", scenario)
    session.log.to_csv(path / "telemetry.csv")
    with (path / "events.jsonl").open("w", encoding="utf-8") as f:
        for event in session.run_events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    write_json(path / "safety_events.json", [asdict(e) for e in session.safety_events])
    write_json(path / "result.json", {"state": session.state.value, "reason": session.stop_reason,
                                     "steps": session.world.step_count,
                                     "final_state": asdict(session.world.state),
                                     "collided": session.world.collided,
                                     "distance": session.world.distance})
    root = Path(__file__).resolve().parents[2]
    hashes = {}
    with zipfile.ZipFile(path / "source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for source in sorted((root / "autopark").rglob("*.py")):
            rel = source.relative_to(root).as_posix()
            hashes[rel] = hashlib.sha256(source.read_bytes()).hexdigest()
            archive.write(source, rel)
        archive.write(root / "pyproject.toml", "pyproject.toml")
    write_json(path / "manifest.json", {
        "schema_version": 1, "evidence": "simulation_only",
        "created_utc": datetime.now(timezone.utc).isoformat(), "environment": environment(),
        "source_sha256": hashes, "model": "kinematic_bicycle", "calibration": "not_measured",
        "replay": "python -m autopark.evaluation.replay <run_directory>",
    })
    return path


def replay_run(directory: str | Path):
    from autopark.application.session import Session
    from autopark.control.tracker import TrackerParams
    from autopark.domain.types import Obstacle, Pose, Scenario, VehicleConfig
    from autopark.planning.hybrid_astar import PlannerParams, PlanResult
    from autopark.planning.trajectory import Trajectory, TrajectoryPoint
    from autopark.simulation.feedback import FeedbackConfig

    path = Path(directory)
    snapshot = json.loads((path / "config_snapshot/run.json").read_text(encoding="utf-8"))
    result = json.loads((path / "result.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    sc = Scenario.from_dict(snapshot["scenario"])
    session = Session(sc, VehicleConfig.from_dict(snapshot["vehicle"]),
                      PlannerParams(**snapshot["planner"]), TrackerParams(**snapshot["tracker"]),
                      FeedbackConfig(**snapshot["feedback"]))
    session.PHYSICS_DT = snapshot["physics_dt"]
    session.CONTROL_EVERY = snapshot["control_every"]
    session.MAX_RUN_TIME = snapshot["max_run_time"]
    data = snapshot["trajectory"]
    points = [TrajectoryPoint(**dict(p, pose=Pose(**p["pose"]))) for p in data["points"]]
    trajectory = Trajectory(points, Pose(**data["goal"]), [tuple(s) for s in data["segments"]])
    session._apply_plan(PlanResult("OK", "Replay snapshot", trajectory), session.plan_version)
    session.start_run()
    index = 0
    # Sự kiện xảy ra trên biên bước vật lý, kể cả ngay sau bước cuối của bản ghi.
    for step in range(result["steps"] + 1):
        while index < len(events) and events[index]["t"] <= session.world.time + 1e-9:
            event = events[index]
            if event["kind"] == "obstacle":
                session.inject_obstacle(Obstacle.from_dict(event["obstacle"]))
            elif event["kind"] == "data_loss":
                session.inject_data_loss()
            elif event["kind"] == "stop":
                session.request_stop(event["reason"])
            else:
                raise ValueError(f"Sự kiện không hỗ trợ: {event['kind']}")
            index += 1
        if step < result["steps"]:
            if not session.simulating:
                raise ValueError("Replay kết thúc sớm hơn bản ghi")
            session.advance(session.PHYSICS_DT)
    if index != len(events):
        raise ValueError("Còn sự kiện ngoài thời gian bản ghi")
    actual = {"state": session.state.value, "final_state": asdict(session.world.state),
              "collided": session.world.collided, "distance": session.world.distance}
    if any(actual[key] != result[key] for key in actual):
        raise ValueError("Replay khác kết quả đã lưu; kiểm tra phiên bản code và môi trường")
    return session
