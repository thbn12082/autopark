"""Phiên mô phỏng có snapshot và replay không chạy lại planner theo thời gian thực.

Nhánh SIM (giai đoạn 0: `SimWorld` + phản hồi giả) được đóng gói và phát lại bằng cách TÁI MÔ PHỎNG. Lần chạy qua
`VehicleIO` (`VEHICLE_IO` hoặc quan sát `OBSERVE`; snapshot có khóa `vehicle_link`) không tái mô phỏng được: trạng thái
của nó lấy từ telemetry + nguồn tư thế. (Tối 24/09/2026: `export_run` và `replay_run` từ chối các lần chạy đó bằng
`ReplayNotSupported`.)

Cập nhật 02/10/2026 (T9; chỉ kiểm với bo mô phỏng và cổng serial GIẢ, CHƯA THỬ với bo thật): gói của lần chạy qua
VehicleIO có cùng dạng gói SIM, thêm thư mục vehicle_io/ (log VehicleLink kèm băng phát lại, `VehicleLink.write_logs`);
manifest có `replay_kind` = "vehicle_io_log" (gói SIM không có khóa này: tái mô phỏng). Gói đó được PHÁT LẠI LOG
(`replay_vehicle_run`, `application/vehicle_replay.py`): chạy lại cùng phần mềm trên đầu vào đã ghi và so quyết định với
bản ghi; không chạy lại xe, bo hay định vị. `replay_run` tự chọn cách phát lại theo snapshot; gói và nhánh SIM không
đổi. Gói, log hay snapshot không đủ để phát lại (thiếu log VehicleLink, log ghi trước khi có băng phát lại, snapshot
không khớp liên kết) → `ReplayNotSupported`.
"""
import csv
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

from autopark.power_throttling import ecoqos_state


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def environment() -> dict:
    info = {"os": platform.platform(), "python": sys.version, "cpu": platform.processor(),
            "ecoqos": ecoqos_state(),          # EcoQoS của tiến trình lúc ghi (02/10/2026; power_throttling.py)
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


class ReplayNotSupported(ValueError):
    """Gói/lần chạy không xuất hay không phát lại được (thiếu log VehicleLink, log ghi trước khi có băng phát lại,
    snapshot không khớp liên kết)."""


def _mode_evidence(info) -> tuple[str, str]:
    info = info if isinstance(info, dict) else {}
    return info.get("mode", "?"), info.get("evidence", "?")


def _vehicle_run_link(session):
    """Liên kết VehicleIO mà log của nó thuộc lần chạy cần xuất; None với lần chạy SIM. Log không chắc thuộc đúng lần
    chạy → `ReplayNotSupported`, trước khi tạo thư mục nào."""
    snapshot_link = session.run_snapshot.get("vehicle_link")
    link = getattr(session, "run_link", None)
    if snapshot_link is None and link is None:
        return None
    if link is None:
        mode, evidence = _mode_evidence(snapshot_link)
        raise ReplayNotSupported(f"Không xuất gói phát lại: lần chạy này đi qua VehicleIO (chế độ {mode}, bằng chứng "
                                 f"{evidence}) nhưng phiên không còn log VehicleLink của lần chạy đó.")
    if snapshot_link is None:
        # Lớp phòng thủ thứ hai: snapshot thiếu khóa nhưng phiên vẫn giữ một liên kết VehicleIO.
        mode, evidence = _mode_evidence(link.describe())
        raise ReplayNotSupported(f"Không xuất gói phát lại: phiên có liên kết VehicleIO (chế độ {mode}, bằng chứng "
                                 f"{evidence}) nhưng snapshot của lần chạy không có khóa vehicle_link; không chắc log "
                                 f"VehicleLink thuộc đúng lần chạy này.")
    mode, evidence = _mode_evidence(snapshot_link)
    if mode != link.mode.value:
        raise ReplayNotSupported(f"Không xuất gói phát lại: chế độ trong snapshot ({mode}) khác chế độ của liên kết "
                                 f"({link.mode.value}).")
    if getattr(link, "run_start", None) is None:
        raise ReplayNotSupported(f"Không xuất gói phát lại (chế độ {mode}, bằng chứng {evidence}): liên kết VehicleIO "
                                 f"chưa mở lần chạy nào.")
    return link


def export_run(session, directory: str | Path) -> Path:
    """Ghi gói của lần chạy kín vòng gần nhất. SIM: gói tái mô phỏng (như trước). Qua VehicleIO (T9, 02/10/2026): cùng
    các tệp đó (RunLog, result.json... của thế giới gương) cộng thư mục vehicle_io/ = `run_link.write_logs()`; manifest
    ghi bằng chứng theo snapshot, model "vehicle_io_mirror", replay_kind "vehicle_io_log"."""
    if session.run_snapshot is None or session.world is None:
        raise ValueError("Chưa có phiên chạy tự động để xuất")
    link = _vehicle_run_link(session)              # từ chối trước khi tạo thư mục nào
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
    if link is not None:
        link.write_logs(path / "vehicle_io")       # log VehicleLink kèm băng phát lại (T9)
    root = Path(__file__).resolve().parents[2]
    hashes = {}
    with zipfile.ZipFile(path / "source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for source in sorted((root / "autopark").rglob("*.py")):
            rel = source.relative_to(root).as_posix()
            hashes[rel] = hashlib.sha256(source.read_bytes()).hexdigest()
            archive.write(source, rel)
        archive.write(root / "pyproject.toml", "pyproject.toml")
    manifest = {
        "schema_version": 1, "evidence": "simulation_only",
        "created_utc": datetime.now(timezone.utc).isoformat(), "environment": environment(),
        "source_sha256": hashes, "model": "kinematic_bicycle", "calibration": "not_measured",
        "replay": "python -m autopark.evaluation.replay <run_directory>",
    }
    if link is not None:
        # Thế giới gương (tư thế từ nguồn định vị, tốc độ/góc lái từ telemetry): phát lại bằng log, không tái mô phỏng.
        manifest.update(evidence=_mode_evidence(session.run_snapshot["vehicle_link"])[1], model="vehicle_io_mirror",
                        replay_kind="vehicle_io_log")
    write_json(path / "manifest.json", manifest)
    return path


def _session_from_snapshot(snapshot: dict):
    """Dựng phiên ở READY với đường đã lập trong snapshot (cấu hình xe, planner, bộ bám, phản hồi giả, nhịp)."""
    from autopark.application.session import Session
    from autopark.control.tracker import TrackerParams
    from autopark.domain.types import Pose, Scenario, VehicleConfig
    from autopark.planning.hybrid_astar import PlannerParams, PlanResult
    from autopark.planning.trajectory import Trajectory, TrajectoryPoint
    from autopark.simulation.feedback import FeedbackConfig

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
    return session


def _replay_steps(session, steps: int, events: list[dict]) -> None:
    """Chạy `steps` bước vật lý, chèn lại sự kiện của events.jsonl đúng bước. Mục "stop" mang code/source (lần chạy qua
    VehicleIO, T13) thì chuyển nguyên cho `request_stop`; gói SIM không có hai khóa này nên lời gọi không đổi."""
    from autopark.domain.types import Obstacle

    index = 0
    # Sự kiện xảy ra trên biên bước vật lý, kể cả ngay sau bước cuối của bản ghi.
    for step in range(steps + 1):
        while index < len(events) and events[index]["t"] <= session.world.time + 1e-9:
            event = events[index]
            if event["kind"] == "obstacle":
                session.inject_obstacle(Obstacle.from_dict(event["obstacle"]))
            elif event["kind"] == "data_loss":
                session.inject_data_loss()
            elif event["kind"] == "stop":
                session.request_stop(event["reason"], **{k: event[k] for k in ("code", "source") if k in event})
            else:
                raise ValueError(f"Sự kiện không hỗ trợ: {event['kind']}")
            index += 1
        if step < steps:
            if not session.simulating:
                raise ValueError("Replay kết thúc sớm hơn bản ghi")
            session.advance(session.PHYSICS_DT)
    if index != len(events):
        raise ValueError("Còn sự kiện ngoài thời gian bản ghi")


def is_vehicle_io_package(directory: str | Path) -> bool:
    """True khi snapshot của gói có khóa vehicle_link (lần chạy qua VehicleIO, phát lại bằng log); False với gói SIM, và
    khi không đọc được config_snapshot/run.json (để nhánh SIM báo lỗi như trước)."""
    try:
        snapshot = json.loads((Path(directory) / "config_snapshot/run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(snapshot, dict) and "vehicle_link" in snapshot


def _package_problem(result, events, safety_events) -> str | None:
    """Kiểu dữ liệu của các tệp gói mà phát lại log dùng; None khi đúng. Sai kiểu là gói hỏng (không phát lại được),
    không phải lần phát lại KHÁC bản ghi (sửa sau review 02/10/2026: trước đó thành AttributeError lúc so)."""
    if not isinstance(result, dict):
        return "result.json không phải một đối tượng JSON"
    steps = result.get("steps")
    if not isinstance(steps, int) or isinstance(steps, bool) or steps < 0:
        return f"result.json: steps phải là số nguyên ≥ 0 (có {steps!r})"
    if not isinstance(safety_events, list):
        return "safety_events.json không phải một mảng JSON"
    for number, event in enumerate(events, 1):
        t = event.get("t") if isinstance(event, dict) else None
        if not isinstance(t, (int, float)) or isinstance(t, bool) or not isinstance(event.get("kind"), str):
            return f"events.jsonl dòng {number}: cần một đối tượng có t (số) và kind (chuỗi)"
    return None


def replay_vehicle_run(directory: str | Path, *, tolerance=None):
    """Phát lại log một gói của lần chạy qua VehicleIO (T9, 02/10/2026): dựng phiên từ snapshot, chạy CÙNG phần mềm
    trên băng của vehicle_io/ (`ReplayVehicleLink`), chèn lại sự kiện của events.jsonl, rồi so với bản ghi
    (`compare_vehicle_run`). Trả (phiên, báo cáo) và KHÔNG đóng phiên. Lệch bản ghi, kể cả ngoại lệ trong lúc phát lại,
    nằm trong báo cáo, không ném. Không phát lại được (gói SIM, thiếu vehicle_io/, log hỏng hay ghi trước T9, gói thiếu
    tệp, chế độ không khớp) → `ReplayNotSupported`. Chỉ kiểm với bo mô phỏng và cổng serial GIẢ; CHƯA THỬ với bo
    thật.

    Sau review 02/10/2026: gói hỏng kiểu nào cũng là `ReplayNotSupported`, không thoát ra thành lỗi khác (CLI khi đó in
    traceback, mã 1 = KHÁC): tệp không phải UTF-8 hay lỗi CSV, config_snapshot/run.json thiếu hay hỏng, JSON sai kiểu
    (result.json, safety_events.json, events.jsonl), snapshot không dựng lại được phiên. Tệp CSV có BOM đọc được."""
    from autopark.application.vehicle_replay import (ReplayVehicleLink, VehicleTapeError, compare_vehicle_run,
                                                      read_vehicle_tape)

    path = Path(directory)
    try:
        snapshot = json.loads((path / "config_snapshot/run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReplayNotSupported(f"Không phát lại: gói {path} thiếu hoặc hỏng config_snapshot/run.json "
                                 f"({exc})") from exc
    if not isinstance(snapshot, dict):
        raise ReplayNotSupported(f"Không phát lại: config_snapshot/run.json của gói {path} không phải một đối tượng "
                                 f"JSON")
    if "vehicle_link" not in snapshot:
        raise ReplayNotSupported("Không phát lại bằng log VehicleIO: đây là gói SIM, dùng replay_run (tái mô phỏng)")
    mode, evidence = _mode_evidence(snapshot["vehicle_link"])
    tape_dir = path / "vehicle_io"
    if not tape_dir.is_dir():
        raise ReplayNotSupported(f"Không phát lại: gói này là lần chạy qua VehicleIO (chế độ {mode}, bằng chứng "
                                 f"{evidence}) nhưng thiếu thư mục vehicle_io/ (log VehicleLink). Cách tái mô phỏng "
                                 f"chỉ dùng cho nhánh mô phỏng SIM; lần chạy qua VehicleIO chỉ phát lại được từ log có "
                                 f"băng phát lại (log_format 2).")
    try:
        tape = read_vehicle_tape(tape_dir)
    except VehicleTapeError as exc:
        raise ReplayNotSupported(f"Không phát lại: log VehicleLink ở {tape_dir}: {exc} (log ghi trước khi có phát lại "
                                 f"VehicleIO, hoặc bị sửa tay)") from exc
    if tape.mode.value != mode:
        raise ReplayNotSupported(f"Không phát lại: chế độ trong snapshot ({mode}) khác chế độ của log VehicleLink "
                                 f"({tape.mode.value})")
    try:
        result = json.loads((path / "result.json").read_text(encoding="utf-8"))
        events = [json.loads(line) for line in (path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        safety_events = json.loads((path / "safety_events.json").read_text(encoding="utf-8"))
        with (path / "telemetry.csv").open(encoding="utf-8-sig", newline="") as f:     # -sig: BOM của Excel
            runlog = list(csv.DictReader(f))
    except (OSError, ValueError, csv.Error) as exc:     # ValueError gồm UnicodeDecodeError, lỗi JSON
        raise ReplayNotSupported(f"Không phát lại: gói {path} thiếu hoặc hỏng tệp ({exc})") from exc
    problem = _package_problem(result, events, safety_events)
    if problem is not None:
        raise ReplayNotSupported(f"Không phát lại: gói {path} hỏng: {problem}")
    try:
        session = _session_from_snapshot(snapshot)
    except Exception as exc:  # noqa: BLE001 - snapshot hỏng hay khác phiên bản (KeyError, TypeError...): không phát lại
        raise ReplayNotSupported(f"Không phát lại: snapshot của gói {path} không dựng lại được phiên "
                                 f"({type(exc).__name__}: {exc})") from exc
    link = ReplayVehicleLink(tape)
    session.set_vehicle_link(link)
    failure = None
    try:
        session.start_run()
        _replay_steps(session, result["steps"], events)
    except Exception as exc:          # lệch bản ghi (hoặc gói hỏng): thành một chỗ khác của báo cáo
        failure = exc
    report = compare_vehicle_run(tape, link, session, evidence=evidence, result=result, safety_events=safety_events,
                                 runlog=runlog, tolerance=tolerance, failure=failure)
    return session, report


def replay_run(directory: str | Path):
    """Phát lại một gói. SIM: tái mô phỏng và so kết quả (như trước). Lần chạy qua VehicleIO: phát lại log
    (`replay_vehicle_run`); khác bản ghi thì đóng phiên và ném ValueError nêu chỗ khác đầu tiên."""
    path = Path(directory)
    snapshot = json.loads((path / "config_snapshot/run.json").read_text(encoding="utf-8"))
    if "vehicle_link" in snapshot:
        session, report = replay_vehicle_run(path)
        if not report.ok:
            session.close()
            raise ValueError(f"Phát lại khác bản ghi ({len(report.mismatches)} chỗ); đầu tiên: "
                             f"{report.mismatches[0].describe()}")
        return session
    result = json.loads((path / "result.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    session = _session_from_snapshot(snapshot)
    session.start_run()
    _replay_steps(session, result["steps"], events)
    actual = {"state": session.state.value, "final_state": asdict(session.world.state),
              "collided": session.world.collided, "distance": session.world.distance}
    if any(actual[key] != result[key] for key in actual):
        raise ValueError("Replay khác kết quả đã lưu; kiểm tra phiên bản code và môi trường")
    return session
