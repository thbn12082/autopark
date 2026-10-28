"""Diễn tập tiêm lỗi có kiểm soát (T6, docs/KIEM_THU_VA_LO_TRINH.md; thêm 02/10/2026): CB-6 (nguồn tư thế
ngừng), CB-5 (b) và L7 (vòng điều khiển treo), CB-2 (camera đứng hình) — CHỈ ở mức MÔ PHỎNG. Phiên đỗ xe chạy qua bo mô
phỏng (`SimVehicleIO` + `FirmwareModel`, tư thế `SimTruthPose` bọc `FreezablePoseSource`); camera là camera giả của công
cụ hoặc bản ghi phát lại. Không tùy chọn nào mở cổng COM, LiDAR hay camera; không có đường cho bo thật (chờ T2, T8).

Chạy trong thư mục `autopark` của repo (thư mục có pyproject.toml), ví dụ (mỗi lệnh một dòng):
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.fault_drill pose --mode hold --repeat 10 --out runs\\fault_drill\\<ngày> --name cb6
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.fault_drill hang --seconds 1 --phases 0 1 2 3 --out runs\\fault_drill\\<ngày> --name cb5b
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.fault_drill hang --seconds 1 --heartbeat --out runs\\fault_drill\\<ngày> --name l7_hb
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.fault_drill camera --mode stall --seconds 1 --repeat 10 --out runs\\fault_drill\\<ngày> --name cb2
    (camera từ bản ghi: thêm --replay <thư mục bản ghi> --ports 1 2 3 4 --port 2)

Mỗi lần chạy một thư mục `<out>/<name>_<kk>/`: lần chạy phiên có mọi tệp của `VehicleLink.write_logs` (02/10/2026:
commands.csv, telemetry.csv, events.csv, start_refusals.csv, board_actions.csv (T15), poses.csv và clock.csv (băng phát
lại, T9), link.json), faults.csv (`FaultLog`) và drill.json — `SESSION_FILES`, lấy từ chính `write_logs` nên không lệch
khi lớp nối thêm tệp; lần chạy camera có faults.csv và drill.json (`CAMERA_FILES`). Tóm tắt ở `<out>/<name>.drill.json`.
Không bao giờ ghi đè: dùng lại `--name` trong cùng `--out` thì thoát mã 2. Mã thoát: 0 khi mọi lần ĐẠT, 1 khi có lần
KHÔNG ĐẠT, 2 khi sai tham số.

Thời điểm: mọi độ trễ đo trên `t_io` (đồng hồ VehicleIO); ghép các tệp theo `t_io`, không theo `t_session`.
`t_session` của faults.csv và của dòng VehicleIO/lớp nối trong events.csv (`handling` stop, log, after_run) = t_io − t0;
commands.csv và dòng session_stop của events.csv (T13) mang thời gian thế giới của `Session` (riêng sự kiện lớp nối tới
khi lần chạy đã rời RUNNING: giữ t của lớp nối), sau một lần treo mô phỏng chậm hơn đúng thời lượng treo. Mã dừng đầu =
mã của `Session.safety_events[0]`; thời điểm của nó = `t_io` của dòng events.csv đầu tiên cùng mã có `handling` "stop"
(lớp nối nhận sự kiện của bo hay của chính nó) hoặc "session_stop" (phiên quyết định; mã của phiên như STALE_POSE chỉ có
dòng này). Từ T13 lần chạy qua VehicleIO luôn có dòng đó (`t_io_from` "events.csv"); t0 + stamp của sự kiện
(`t_io_from` "safety_event") chỉ là đường lùi cho log không có nó. Khi xe đã đứng yên lúc sự kiện dừng tới (treo ≥ 1 s),
lần chạy kết thúc ngay bước đó và commands.csv có thể không có dòng STOP nào (`end_run` không ghi gì):
`first_stop_command_t_io` khi đó là None.

Camera từ bản ghi phát lại: khung có lịch rơi vào lúc STALL bị bỏ sau khi hết đóng băng, như camera thật đứng hình
(nguồn phát lại tự nó sẽ trả dồn chúng với stamp cũ); số khung bị bỏ ở `skipped_after_stall` của drill.json.

ĐẠT/KHÔNG ĐẠT là kiểm của công cụ suy từ tham số hiện tại (`judge`, `judge_camera`), KHÔNG phải ngưỡng nghiệm thu: N-T2,
N-T4, N-P7 vẫn ĐỀ XUẤT – CHỜ CHỐT. drill.json ghi cả số đo lẫn giới hạn đã dùng.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np

from autopark.power_throttling import apply_ecoqos_policy
from autopark.safety.fault_injection import (CLEARED, INJECTED, FaultLog, FaultRecord, FreezablePoseSource,
                                             FreezeMode, FreezeSwitch, PoseFault, freezable_open_source,
                                             hang_control_loop)
from autopark.video.multicam import RIG_CLOCK, CameraSpec, MultiCameraManager
from autopark.video.sources import _frame

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO = PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json"
DEFAULT_SIM_CONFIG = PROJECT_ROOT / "configs" / "vehicle_io_sim_nghiem_thu.json"
TOOL = "autopark.evaluation.fault_drill"
EVIDENCE = "simulation_only"
DRILL_FILES = ("faults.csv", "drill.json")          # tệp của chính công cụ trong thư mục mỗi lần chạy
CAMERA_FILES = DRILL_FILES                          # lần chạy camera chỉ có chúng
# SESSION_FILES (tệp của một lần chạy phiên) = tệp của `VehicleLink.write_logs` + DRILL_FILES: tính lần đầu cần tới,
# xem `__getattr__` cuối module.

MARGIN_S = 0.05                     # biên quanh hạn lệnh / watchdog liên lạc khi phán lần treo
HANG_FIRST_CODES = ("VEHICLE_STOPPED", "VEHICLE_NOT_ARMED", "STALE_TELEMETRY")
WATCHDOG_REASONS = ("COMMAND_TIMEOUT", "LINK_TIMEOUT")
STOP_HANDLINGS = ("stop", "session_stop")     # lớp nối nhận sự kiện dừng; phiên quyết định dừng (T13)
TRIGGER_TIMEOUT_S = 30.0            # thời gian phiên tối đa để tới tốc độ kích hoạt
SETTLE_S = 0.3                      # chạy bo thêm sau khi lần chạy kết thúc, rồi đọc trạng thái cuối
REJOIN_WAIT_S = 1.0                 # chờ camera quay lại sau khi hết đóng băng
CAMERA_POLL_S = 0.005               # nhịp ghép bộ ảnh như vòng `_set_loop` của Rig
OTHERS_MIN_RATIO = 0.8              # camera khác phải giữ ≥ chừng ấy tốc độ bộ ảnh của chính nó trước khi gây lỗi
STALE_MARGIN_S = 0.1                # giới hạn "cũ/thiếu" = STALE_AFTER_S + 1,5 chu kỳ khung + chừng ấy


def _vn(value: float | None, nd: int = 3) -> str:
    """Số kiểu Việt Nam cho dòng in ra màn hình (dấu phẩy thập phân)."""
    return "—" if value is None else f"{value:.{nd}f}".replace(".", ",")


# ============================================================================================ phiên qua VehicleIO
@dataclass
class SessionDrillResult:
    """Kết quả một lần chạy phiên (tư thế ngừng hoặc treo vòng điều khiển). Mọi `t_io` trên đồng hồ VehicleIO."""

    kind: str                                   # "pose" | "hang"
    run: int
    params: dict                                # pose: cần "mode"; hang: cần "seconds", "heartbeat"
    t_fault_io: float | None                    # lúc gây lỗi (dòng fault_injected đầu tiên của faults.csv)
    t_fault_end_io: float | None                # lúc hết lỗi (dòng fault_cleared đầu tiên sau đó); None: chưa hết
    t_fault_session: float | None
    first_stop: dict | None                     # {code, source, message, t_session, t_io, t_io_from, t_world}
    stop_codes: list[str]                       # mã của Session.safety_events theo thứ tự
    vehicle_io_events: list[dict]               # dòng events.csv từ lúc gây lỗi
    first_stop_command_t_io: float | None       # dòng STOP đầu của commands.csv (có thể không có, xem đầu module)
    detect_s: float | None                      # first_stop.t_io − t_fault_io (treo: − t_fault_end_io; có thể âm)
    detect_limit_s: float | None                # giới hạn của công cụ (chỉ lần chạy tư thế)
    enable_after_stop: int                      # dòng TRACK đã gửi (enable=1) từ lần dừng đầu trở đi
    enable_after_fault_end: int | None          # dòng TRACK đã gửi từ lúc hết lỗi trở đi; None: lỗi chưa hết
    board_transitions: list[dict]               # đổi (state, stop_reason) trong telemetry.csv từ lúc gây lỗi
    board_final: str | None                     # trạng thái bo sau khi lần chạy kết thúc và chạy thêm SETTLE_S
    board_final_stop_reason: str | None
    session_state: str
    stop_reason: str
    path_invalidated: bool
    limits: dict                                # tham số mà `judge` dùng (hạn lệnh, watchdog liên lạc, ...)
    hang: dict | None = None                    # HangResult.to_dict() của lần treo
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        return {**asdict(self), "ok": self.ok}


def _row_t(row: dict, key: str = "t_io") -> float | None:
    value = row.get(key, "")
    return None if value == "" or value is None else float(value)


def board_transitions(rows: list[dict], since: float | None) -> list[dict]:
    """Các lần (state, stop_reason) đổi so với khung trước, ở khung có `t_io` ≥ `since` (dòng telemetry.csv)."""
    out, prev = [], None
    for row in rows:
        key = (row["state"], row["stop_reason"])
        t = _row_t(row)
        if prev is not None and key != prev and since is not None and t is not None and t >= since - 1e-9:
            out.append({"t_io": t, "device_time_ms": row["device_time_ms"], "state": key[0], "stop_reason": key[1],
                        "from_state": prev[0], "from_stop_reason": prev[1]})
        prev = key
    return out


def _enables_after(rows: list[dict], t: float) -> int:
    """Số dòng TRACK đã gửi (enable=1) có `t_io` ≥ t."""
    return sum(1 for r in rows if r["kind"] == "TRACK" and r["sent"] == 1 and _row_t(r) is not None
               and _row_t(r) >= t - 1e-9)


def _first_stop(session, link, t0: float) -> dict | None:
    if not session.safety_events:
        return None
    ev = session.safety_events[0]
    row = next((r for r in link.event_rows if r["handling"] in STOP_HANDLINGS and r["code"] == ev.code
                and _row_t(r) is not None), None)
    t_io = _row_t(row) if row is not None else t0 + ev.stamp.t
    # t_world: thời gian thế giới của Session (như commands.csv); sau một lần treo mô phỏng nó lệch t_session
    return {"code": ev.code, "source": ev.stamp.source_id, "message": ev.message, "t_session": t_io - t0,
            "t_io": t_io, "t_io_from": "events.csv" if row is not None else "safety_event", "t_world": ev.stamp.t}


def _detect_limit(kind: str, params: dict, limits: dict) -> float | None:
    if kind != "pose":
        return None
    tick = limits["control_period_s"] + limits["physics_dt_s"]       # chờ nhịp điều khiển kế + một bước
    if PoseFault(params["mode"]) is PoseFault.SILENT:
        return tick
    # T2 (02/10/2026): tuổi tư thế tối đa riêng (`LinkParams.pose_age_limit_s`); kết quả cũ không có khóa này
    return limits.get("pose_age_limit_s", limits["max_state_age_s"]) + tick


def collect_session_result(kind: str, run: int, params: dict, session, link,
                           faults: FaultLog | list[FaultRecord], *, board_final: str | None,
                           board_final_stop_reason: str | None) -> SessionDrillResult:
    """Gom kết quả một lần chạy chỉ từ các dòng log của `link` (commands/telemetry/events), `session.safety_events`,
    trạng thái phiên và `faults` — nên test dùng lại được. `problems` để trống: người gọi thêm vấn đề dựng lần chạy và
    `judge`."""
    records = faults.records if isinstance(faults, FaultLog) else list(faults)
    start = next((i for i, r in enumerate(records) if r.handling == INJECTED), None)
    injected = records[start] if start is not None else None
    ended = next((r for r in records[start + 1:] if r.handling == CLEARED), None) if start is not None else None
    t_fault_io = injected.t_io if injected is not None else None
    t_fault_end_io = ended.t_io if ended is not None else None
    io = link.io
    t0 = io.now() - link.session_time_now()
    first = _first_stop(session, link, t0)
    commands = link.command_rows
    stops = [r for r in commands if r["kind"] == "STOP" and _row_t(r) is not None]
    hello = io.hello
    limits = {"command_validity_s": link.params.command_validity_s or io.default_validity_s,
              "link_timeout_s": hello.limits.link_timeout_s if hello is not None else None,
              "max_state_age_s": link.params.max_state_age_s,
              "pose_age_limit_s": link.params.pose_age_limit_s,
              "control_period_s": session.CONTROL_EVERY * session.PHYSICS_DT,
              "physics_dt_s": session.PHYSICS_DT}
    reference = t_fault_end_io if kind == "hang" else t_fault_io
    events = [{"t_io": _row_t(r), "source": r["source"], "code": r["code"], "action": r["action"],
               "handling": r["handling"]}
              for r in link.event_rows
              if t_fault_io is not None and _row_t(r) is not None and _row_t(r) >= t_fault_io - 1e-9]
    return SessionDrillResult(
        kind=kind, run=run, params=dict(params), t_fault_io=t_fault_io, t_fault_end_io=t_fault_end_io,
        t_fault_session=injected.t_session if injected is not None else None, first_stop=first,
        stop_codes=[e.code for e in session.safety_events], vehicle_io_events=events,
        first_stop_command_t_io=_row_t(stops[0]) if stops else None,
        # làm tròn µs: t0 + thời gian thế giới (tổng số thực) lệch io.now() cỡ 1e-12 s, không thành "−0,000 s"
        detect_s=round(first["t_io"] - reference, 6) + 0.0 if first is not None and reference is not None else None,
        detect_limit_s=_detect_limit(kind, params, limits),
        enable_after_stop=_enables_after(commands, first["t_io"]) if first is not None else 0,
        enable_after_fault_end=_enables_after(commands, t_fault_end_io) if t_fault_end_io is not None else None,
        board_transitions=board_transitions(link.telemetry_rows, t_fault_io), board_final=board_final,
        board_final_stop_reason=board_final_stop_reason, session_state=session.state.value,
        stop_reason=session.stop_reason, path_invalidated=bool(session.path_invalidated), limits=limits)


def _end_checks(r: SessionDrillResult) -> list[str]:
    out = []
    if r.session_state != "STOPPED":
        out.append(f"Lần chạy kết thúc ở {r.session_state}, cần STOPPED")
    if not r.path_invalidated:
        out.append("Đường đã lập không bị hủy sau lần dừng (path_invalidated False): phải lập lại đường mới chạy tiếp")
    if r.board_final != "DISARMED":
        out.append(f"Bo cuối cùng ở {r.board_final}, cần DISARMED")
    return out


def judge(r: SessionDrillResult) -> list[str]:
    """Phản ứng dự kiến còn thiếu (câu tiếng Việt; rỗng = ĐẠT). Hàm thuần: chỉ đọc `r`.

    Mọi lần: không COMMAND enable=1 nào từ lần dừng đầu; kết thúc STOPPED; đường bị hủy; bo cuối DISARMED.
    Tư thế: mã dừng đầu STALE_POSE trong giới hạn `detect_limit_s`; bo không tự dừng bằng watchdog (COMMAND_TIMEOUT,
    LINK_TIMEOUT) — enable=0 của laptop phải dừng bo trước.
    Treo: ≤ hạn lệnh + MARGIN_S thì chỉ báo số (chỉ còn kiểm enable sau lần dừng). Dài hơn: mã đầu thuộc
    HANG_FIRST_CODES; không enable nào sau khi hết treo; bo có COMMAND_TIMEOUT hoặc LINK_TIMEOUT; có Heartbeat thì không
    LINK_TIMEOUT; không Heartbeat thì LINK_TIMEOUT khi treo ≥ watchdog liên lạc + MARGIN_S và không LINK_TIMEOUT khi
    treo ≤ watchdog liên lạc − MARGIN_S."""
    out = []
    if r.enable_after_stop:
        out.append(f"Có {r.enable_after_stop} COMMAND enable=1 gửi tới bo từ lần dừng đầu trở đi")
    code = r.first_stop["code"] if r.first_stop else None
    reasons = {t["stop_reason"] for t in r.board_transitions}
    if r.kind == "hang":
        seconds, heartbeat = float(r.params["seconds"]), bool(r.params["heartbeat"])
        if seconds <= r.limits["command_validity_s"] + MARGIN_S + 1e-9:
            return out                          # ngắn hơn hạn lệnh (+ biên): bo có thể không hết hạn lệnh, chỉ báo số
        out += _end_checks(r)
        if code not in HANG_FIRST_CODES:
            out.append(f"Mã dừng đầu sau khi treo là {code or 'không có'}, cần một trong {'/'.join(HANG_FIRST_CODES)}")
        if r.enable_after_fault_end:
            out.append(f"Có {r.enable_after_fault_end} COMMAND enable=1 gửi tới bo sau khi hết treo")
        if not reasons & set(WATCHDOG_REASONS):
            out.append(f"Bo không báo COMMAND_TIMEOUT hay LINK_TIMEOUT sau khi treo {seconds:.3f} s")
        link_timeout = r.limits["link_timeout_s"]
        if heartbeat and "LINK_TIMEOUT" in reasons:
            out.append("Có Heartbeat mà bo vẫn LINK_TIMEOUT: PING không giữ được liên lạc")
        elif not heartbeat and link_timeout is not None:
            if seconds >= link_timeout + MARGIN_S - 1e-9 and "LINK_TIMEOUT" not in reasons:
                out.append(f"Treo {seconds:.3f} s không Heartbeat (≥ watchdog liên lạc {link_timeout:.3f} s + "
                           f"{MARGIN_S:.2f} s) mà bo không LINK_TIMEOUT")
            if seconds <= link_timeout - MARGIN_S + 1e-9 and "LINK_TIMEOUT" in reasons:
                out.append(f"Treo {seconds:.3f} s không Heartbeat (≤ watchdog liên lạc {link_timeout:.3f} s − "
                           f"{MARGIN_S:.2f} s) mà bo đã LINK_TIMEOUT")
        return out
    out += _end_checks(r)
    if code != "STALE_POSE":
        out.append(f"Mã dừng đầu là {code or 'không có'}, cần STALE_POSE")
    elif r.detect_s is None or r.detect_s > r.detect_limit_s + 1e-9:
        out.append(f"STALE_POSE sau {_vn(r.detect_s)} s kể từ lúc nguồn tư thế ngừng, quá giới hạn của công cụ "
                   f"{_vn(r.detect_limit_s)} s")
    watchdog = sorted(reasons & set(WATCHDOG_REASONS))
    if watchdog:
        out.append(f"Bo tự dừng bằng watchdog ({', '.join(watchdog)}) thay vì lệnh enable=0 của laptop")
    return out


def _advance_until_trigger(session, io, at_speed: float) -> bool:
    """Tiến phiên từng 20 ms tới khi tốc độ ĐO (telemetry) đạt `at_speed` (âm: đang lùi nhanh hơn |at_speed|)."""
    from autopark.application.session import SessionState

    while session.state == SessionState.RUNNING and session.world.time < TRIGGER_TIMEOUT_S:
        session.advance(0.02)
        tel = io.latest()
        if session.state != SessionState.RUNNING:
            return False
        if tel is not None and tel.speed_mps is not None and (
                tel.speed_mps >= at_speed if at_speed > 0 else tel.speed_mps <= at_speed):
            return True
    return False


def _inject_pose(session, link, pose: FreezablePoseSource, params: dict) -> None:
    """Nguồn tư thế ngừng; trả lại sau `resume_after_s` kể từ lúc phiên rời RUNNING (xe đang phanh), 0 = không bao giờ.
    Lần chạy kết thúc trước hạn đó thì vẫn trả lại ngay khi kết thúc (faults.csv có FAULT_END)."""
    from autopark.application.session import SessionState

    resume_after = float(params["resume_after_s"])
    pose.stop(PoseFault(params["mode"]), t_session=link.session_time_now())
    cap = session.MAX_RUN_TIME + 10.0
    t_stop = None
    while session.simulating and session.world.time < cap:
        session.advance(0.02)
        if t_stop is None and session.state != SessionState.RUNNING:
            t_stop = session.world.time
        if resume_after > 0 and t_stop is not None and session.world.time >= t_stop + resume_after - 1e-9:
            break
    if resume_after > 0:
        pose.resume(t_session=link.session_time_now())


def _run_to_end(session) -> None:
    cap = session.MAX_RUN_TIME + 10.0
    while session.simulating and session.world.time < cap:
        session.advance(0.1)


def _settle(io) -> None:
    end = io.now() + SETTLE_S
    while io.now() < end - 1e-9:
        io.service()


def run_session(kind: str, run: int, params: dict, folder: Path) -> SessionDrillResult:
    """Một lần chạy phiên trên bo mô phỏng (CB-6: kind "pose"; CB-5 (b)/L7: kind "hang"); ghi các tệp `SESSION_FILES`
    (log của `VehicleLink.write_logs`, faults.csv, drill.json) vào `folder` (phải chưa có). `params`: scenario,
    sim_config, at_speed_mps; pose: mode, resume_after_s; hang: seconds, heartbeat, phase."""
    from autopark.application.session import Session, SessionError
    from autopark.application.vehicle_link import DriveMode, SimTruthPose, VehicleLink
    from autopark.domain.types import VehicleState
    from autopark.storage.scenario_store import load_scenario, load_vehicle_config
    from autopark.transport.vehicle_io import SimVehicleIO, load_sim_io_config

    folder.mkdir(parents=True, exist_ok=False)
    scenario = load_scenario(params["scenario"])
    cfg = load_vehicle_config(scenario.vehicle_config_path)
    sim_cfg, _ = load_sim_io_config(params["sim_config"])
    session = Session(scenario, cfg)
    io = SimVehicleIO(cfg, sim_cfg, start=VehicleState(scenario.start, 0.0, 0.0, 0.0))
    log = FaultLog()
    pose = FreezablePoseSource(SimTruthPose(io), clock=io.now, log=log)
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=pose)
    problems: list[str] = []
    hang = None
    injected = False
    try:
        plan = session.plan_sync()
        if not plan.ok:
            problems.append(f"Không lập được đường: {plan.status} — {plan.message}")
        else:
            session.set_vehicle_link(link)
            try:
                session.start_run()
            except SessionError as exc:
                problems.append(f"Không bắt đầu được lần chạy: {exc}")
        if not problems:
            if not _advance_until_trigger(session, io, float(params["at_speed_mps"])):
                problems.append(f"Không tới tốc độ kích hoạt {float(params['at_speed_mps']):+.3f} m/s (tốc độ đo của "
                                f"telemetry) trong {TRIGGER_TIMEOUT_S:.0f} s hoặc trước khi lần chạy kết thúc "
                                f"({session.state.value}: {session.stop_reason})")
            elif kind == "pose":
                injected = True
                _inject_pose(session, link, pose, params)
            else:
                try:
                    hang = hang_control_loop(session, float(params["seconds"]), heartbeat=bool(params["heartbeat"]),
                                             phase=params.get("phase"), log=log)
                    injected = True
                except RuntimeError as exc:             # lần chạy dừng trong lúc căn pha: không có lần treo nào
                    problems.append(f"Không treo được vòng điều khiển: {exc}")
            _run_to_end(session)
        _settle(io)
        tel = io.latest()
        link.write_logs(folder)
        log.write_csv(folder / "faults.csv")
        result = collect_session_result(kind, run, params, session, link, log,
                                        board_final=tel.state.name if tel is not None else None,
                                        board_final_stop_reason=tel.stop_reason.name if tel is not None else None)
        result.hang = hang.to_dict() if hang is not None else None
        result.problems = problems + (judge(result) if injected else [])
        _write_json(folder / "drill.json", {"tool": TOOL, "evidence": EVIDENCE, **result.to_dict()})
        return result
    finally:
        session.close()                     # VEHICLE_IO còn phiên: enable=0 + DISARM; dừng worker lập đường


def session_line(index: int, total: int, r: SessionDrillResult) -> str:
    p = r.params
    if r.kind == "pose":
        head = f"tư thế {str(p['mode']).upper()} lúc {_vn(float(p['at_speed_mps']))} m/s"
    else:
        head = (f"treo {_vn(float(p['seconds']))} s, {'có' if p['heartbeat'] else 'không'} Heartbeat, "
                f"pha {r.hang['phase'] if r.hang else p.get('phase')}")
    if r.first_stop is None:
        stop = "không có lần dừng nào"
    elif r.kind == "hang" and r.detect_s is not None and r.detect_s < 0:
        stop = (f"dừng đầu {r.first_stop['code']} (sự kiện đọc trong lúc treo, {_vn(-r.detect_s)} s trước khi "
                f"hết treo)")
    else:
        stop = f"dừng đầu {r.first_stop['code']} sau {_vn(r.detect_s)} s"
        if r.detect_limit_s is not None:
            stop += f" (giới hạn {_vn(r.detect_limit_s)} s)"
    reasons: list[str] = []
    for t in r.board_transitions:
        if not reasons or reasons[-1] != t["stop_reason"]:
            reasons.append(t["stop_reason"])
    if r.kind == "hang":
        enable = f"enable sau khi hết treo {r.enable_after_fault_end if r.enable_after_fault_end is not None else '—'}"
    else:
        enable = f"enable sau lần dừng {r.enable_after_stop}"
    verdict = "ĐẠT" if r.ok else "KHÔNG ĐẠT: " + "; ".join(r.problems)
    return (f"[{index}/{total}] {head}: {stop}; bo {' → '.join(reasons) or 'không đổi'}; {enable} → {verdict}")


# =================================================================================================== camera
class _SyntheticCamera:
    """Camera giả của công cụ: ảnh 64×48 nội dung mới mỗi khung, nhịp `period_s` theo lịch (không trôi dần như ngủ một
    chu kỳ mỗi lần), stamp RIG_CLOCK, dựng bằng `sources._frame` như `rig/replay.py`. Đọc trễ hơn một chu kỳ (vừa bị
    chặn bởi STALL) thì nhịp bắt đầu lại từ lúc đọc, như camera thật chụp khung kế, không trả dồn khung."""

    def __init__(self, spec: CameraSpec, period_s: float, clock=RIG_CLOCK):
        self.spec, self.period, self.clock = spec, period_s, clock
        self.source_id = spec.source_id
        self.n = 0
        self.closed = False
        self._due: float | None = None

    def read(self):
        now = self.clock()
        if self._due is None or now - self._due > self.period:
            self._due = now + self.period
        delay = self._due - self.clock()
        if delay > 0:
            time.sleep(delay)
        self._due += self.period
        self.n += 1
        image = np.full((48, 64, 3), (self.n * 7 + self.spec.port * 40) % 256, np.uint8)
        image[0, 0] = (self.n % 256, (self.n // 256) % 256, self.spec.port % 256)
        return _frame(self.source_id, self.clock(), f"fault_drill#{self.n}", image)

    def close(self) -> None:
        self.closed = True


@dataclass
class CameraDrillResult:
    """Kết quả một lần đóng băng camera. Thời điểm trên đồng hồ bàn thử (RIG_CLOCK); "sau" tính từ lúc đóng băng, riêng
    `rejoined_after_s` tính từ lúc hết đóng băng. Tốc độ bộ ảnh theo cổng (khóa là chuỗi)."""

    run: int
    mode: str
    port: int
    ports: list[int]
    source: str
    seconds: float
    warmup_s: float
    t_rig_start: float | None                   # lúc đóng băng
    t_rig_end: float | None                     # lúc hết đóng băng
    period_ms: float | None                     # chu kỳ khung của camera bị đóng băng (giả: tham số; phát lại: đo)
    stale_after_s: float | None                 # camera_stats "stale"
    missing_after_s: float | None               # FrameSet.missing
    lagging_after_s: float | None               # FrameSet.lagging (bộ phát không có nó sau khi chờ)
    rejoined_after_s: float | None              # bộ ảnh đầu tiên có lại nó
    stale_limit_s: float                        # STALE_AFTER_S + 1,5 chu kỳ + STALE_MARGIN_S
    others_sets_per_s_before: dict
    others_sets_per_s_during: dict
    duplicates_during: int
    read_failures_during: int
    skipped_after_stall: int                    # mục phát lại có lịch trong lúc STALL, bị bỏ khi hết (camera giả: 0)
    gap_max_ms: float | None
    camera_stats_end: list[dict]
    stop_alive: list[str]
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        return {**asdict(self), "ok": self.ok}


class _CameraProbe:
    """Ghép bộ mỗi 5 ms như `Rig._set_loop` (max_skew/max_wait của `RigConfig` mặc định) và theo dõi một cổng."""

    def __init__(self, cams: MultiCameraManager, port: int):
        from autopark.rig.core import RigConfig

        cfg = RigConfig()
        self.cams, self.port = cams, port
        self.max_skew_s, self.max_wait_s = cfg.max_skew_s, cfg.max_wait_s
        self.sets: list[tuple[float, frozenset, frozenset, frozenset]] = []   # (t, cổng trong bộ, missing, lagging)
        self.stale: list[tuple[float, bool]] = []

    def poll(self, until: float, done=None) -> bool:
        while True:
            fs = self.cams.latest_set(self.max_skew_s, max_wait_s=self.max_wait_s)
            if fs is not None:
                self.sets.append((fs.t_built, frozenset(fs.frames), frozenset(fs.missing), frozenset(fs.lagging)))
            now = RIG_CLOCK()
            row = self.stats_of(self.cams.camera_stats())
            self.stale.append((now, bool(row["stale"])))
            if done is not None and done():
                return True
            if now >= until:
                return False
            time.sleep(CAMERA_POLL_S)

    def stats_of(self, stats: list[dict], port: int | None = None) -> dict:
        port = self.port if port is None else port
        return next(c for c in stats if c["port"] == port)

    def first_set(self, since: float, test) -> float | None:
        return next((t - since for t, frames, missing, lagging in self.sets
                     if t >= since and test(frames, missing, lagging)), None)

    def rate(self, port: int, t_from: float, t_to: float) -> float:
        if t_to <= t_from:
            return 0.0
        return sum(1 for t, frames, _, _ in self.sets if t_from <= t < t_to and port in frames) / (t_to - t_from)


def camera_freeze_run(cams: MultiCameraManager, switch: FreezeSwitch, *, port: int, mode: FreezeMode | str,
                      seconds: float, warmup: float) -> dict:
    """Trình tự trên một `MultiCameraManager` ĐÃ chạy: làm nóng `warmup` s → đóng băng cổng `port` → `seconds` s → hết
    đóng băng → chờ tối đa REJOIN_WAIT_S cho tới khi cổng đó có lại trong bộ ảnh. Trả các số đo (không phán)."""
    mode = FreezeMode(mode)
    probe = _CameraProbe(cams, port)
    t_begin = RIG_CLOCK()
    probe.poll(t_begin + warmup)
    before = cams.camera_stats()
    t_freeze = switch.freeze(mode).t_rig
    probe.poll(t_freeze + seconds)
    record = switch.thaw()
    t_thaw = record.t_rig if record is not None else RIG_CLOCK()     # None: đã tự hết (giới hạn an toàn)
    after = cams.camera_stats()
    probe.poll(t_thaw + REJOIN_WAIT_S, done=lambda: probe.first_set(t_thaw, lambda f, m, l: port in f) is not None)
    end = cams.camera_stats()
    window = min(warmup, max(0.25, warmup / 2))                      # tốc độ "trước" đo trên cuối phần làm nóng
    others = [p for p in sorted(cams.workers) if p != port]
    stale_t = next((t - t_freeze for t, stale in probe.stale if t >= t_freeze and stale), None)
    return {
        "t_rig_start": t_freeze, "t_rig_end": t_thaw,
        "period_ms": probe.stats_of(before).get("period_ms"),
        "stale_after_s": stale_t,
        "missing_after_s": probe.first_set(t_freeze, lambda f, m, l: port in m),
        "lagging_after_s": probe.first_set(t_freeze, lambda f, m, l: port in l),
        "rejoined_after_s": probe.first_set(t_thaw, lambda f, m, l: port in f),
        "others_sets_per_s_before": {str(q): round(probe.rate(q, t_freeze - window, t_freeze), 2) for q in others},
        "others_sets_per_s_during": {str(q): round(probe.rate(q, t_freeze, t_thaw), 2) for q in others},
        "duplicates_during": probe.stats_of(after)["duplicates"] - probe.stats_of(before)["duplicates"],
        "read_failures_during": probe.stats_of(after)["read_failures"] - probe.stats_of(before)["read_failures"],
        "skipped_after_stall": switch.skipped_after_stall,
        "gap_max_ms": probe.stats_of(end).get("gap_max_ms"),
        "camera_stats_end": end,
    }


def stale_limit_s(period_s: float | None, stale_after_s: float) -> float:
    """Giới hạn của công cụ cho "cũ/thiếu": camera bị coi là cũ sau `stale_after_s` kể từ khung tốt cuối, khung đó có
    thể đã cũ tới một chu kỳ lúc đóng băng; cộng nửa chu kỳ rung và STALE_MARGIN_S cho nhịp lấy mẫu và lịch luồng."""
    return stale_after_s + 1.5 * (period_s or 0.05) + STALE_MARGIN_S


def judge_camera(r: CameraDrillResult) -> list[str]:
    """Phản ứng dự kiến còn thiếu khi đóng băng một camera (rỗng = ĐẠT): báo cũ và vào `missing`, mỗi việc trong
    `stale_limit_s` (chỉ đòi khi đóng băng đủ lâu); camera khác giữ ≥ 80 % tốc độ bộ ảnh của chính nó trước khi gây lỗi;
    camera quay lại trong REJOIN_WAIT_S; REPEAT được đếm là khung cũ; mọi luồng camera dừng được."""
    out = []
    if r.seconds >= r.stale_limit_s:
        for label, value in (("bị báo cũ (camera_stats stale)", r.stale_after_s),
                             ("vào FrameSet.missing", r.missing_after_s)):
            if value is None:
                out.append(f"Camera cổng {r.port} không {label} trong {_vn(r.seconds)} s đóng băng")
            elif value > r.stale_limit_s + 1e-9:
                out.append(f"Camera cổng {r.port} {label} sau {_vn(value)} s, quá giới hạn của công cụ "
                           f"{_vn(r.stale_limit_s)} s")
    for q, before in r.others_sets_per_s_before.items():
        during = r.others_sets_per_s_during.get(q, 0.0)
        if before <= 0:
            out.append(f"Camera cổng {q} không có bộ ảnh nào trước khi gây lỗi")
        elif during < OTHERS_MIN_RATIO * before:
            out.append(f"Camera cổng {q} chậm lại khi cổng {r.port} đóng băng: {_vn(during, 1)} bộ/s so với "
                       f"{_vn(before, 1)} bộ/s trước đó (cần ≥ {OTHERS_MIN_RATIO:.0%})")
    if r.rejoined_after_s is None or r.rejoined_after_s > REJOIN_WAIT_S:
        out.append(f"Camera cổng {r.port} không quay lại bộ ảnh trong {_vn(REJOIN_WAIT_S, 1)} s sau khi hết đóng băng")
    if r.mode == FreezeMode.REPEAT.value and r.duplicates_during <= 0:
        out.append(f"REPEAT không được đếm là khung cũ (duplicates không tăng ở cổng {r.port})")
    if r.stop_alive:
        out.append(f"Luồng camera chưa dừng sau khi nhả công tắc: {', '.join(r.stop_alive)}")
    return out


def run_camera(run: int, params: dict, folder: Path) -> CameraDrillResult:
    """Một lần đóng băng camera (CB-2, phần MP) trên camera giả hay bản ghi phát lại; ghi faults.csv và drill.json vào
    `folder` (phải chưa có). `params`: mode, port, ports, seconds, warmup_s, period_ms, replay (None hoặc thư mục)."""
    from autopark.video.multicam import STALE_AFTER_S

    folder.mkdir(parents=True, exist_ok=False)
    port, ports, mode = int(params["port"]), [int(p) for p in params["ports"]], FreezeMode(params["mode"])
    seconds, warmup = float(params["seconds"]), float(params["warmup_s"])
    log = FaultLog()
    switch = FreezeSwitch(f"cam_p{port}", log=log, max_stall_s=seconds + 5.0)
    replay = None
    if params.get("replay"):
        from autopark.rig.replay import ReplaySession

        replay = ReplaySession(params["replay"], ports=ports)
        specs, opener = replay.camera_specs(), replay.open_camera
        source = f"phát lại {params['replay']}"
    else:
        period_s = float(params["period_ms"]) / 1000.0
        specs = [CameraSpec(port=p, index=k) for k, p in enumerate(ports)]
        opener = lambda spec: _SyntheticCamera(spec, period_s)  # noqa: E731
        source = f"camera giả {_vn(float(params['period_ms']), 0)} ms"
    cams = MultiCameraManager(specs, open_source=freezable_open_source(opener, {port: switch}), ring=3)
    try:
        cams.start()
        if replay is not None:
            replay.begin()
        metrics = camera_freeze_run(cams, switch, port=port, mode=mode, seconds=seconds, warmup=warmup)
    finally:
        switch.release()                   # TRƯỚC khi dừng luồng camera: luồng đang chặn ở STALL được thả
        if replay is not None:
            replay.stop()
        stop_alive = cams.stop()
    period_ms = float(params["period_ms"]) if replay is None else metrics["period_ms"]
    result = CameraDrillResult(run=run, mode=mode.value, port=port, ports=ports, source=source, seconds=seconds,
                               warmup_s=warmup, period_ms=period_ms,
                               stale_limit_s=stale_limit_s(None if period_ms is None else period_ms / 1000.0,
                                                           cams.stale_after_s or STALE_AFTER_S),
                               stop_alive=stop_alive, **{k: v for k, v in metrics.items() if k != "period_ms"})
    result.problems = judge_camera(result)
    log.write_csv(folder / "faults.csv")
    _write_json(folder / "drill.json", {"tool": TOOL, "evidence": EVIDENCE, **result.to_dict()})
    return result


def camera_line(index: int, total: int, r: CameraDrillResult) -> str:
    others = ", ".join(f"cổng {q}: {_vn(b, 1)} → {_vn(r.others_sets_per_s_during.get(q), 1)} bộ/s"
                       for q, b in r.others_sets_per_s_before.items())
    verdict = "ĐẠT" if r.ok else "KHÔNG ĐẠT: " + "; ".join(r.problems)
    return (f"[{index}/{total}] camera cổng {r.port} {r.mode.upper()} {_vn(r.seconds)} s ({r.source}): cũ sau "
            f"{_vn(r.stale_after_s)} s, thiếu sau {_vn(r.missing_after_s)} s, bị bỏ chờ sau "
            f"{_vn(r.lagging_after_s)} s; quay lại sau {_vn(r.rejoined_after_s)} s; "
            f"{others or 'không có camera khác'} → {verdict}")


# ======================================================================================================= CLI
def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def _git_state() -> dict:
    info: dict = {}
    try:
        info["head"] = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, timeout=10,
                                               stderr=subprocess.DEVNULL).decode().strip()
        # --no-optional-locks: `git status` không ghi lại .git/index (index.lock), nên git add/commit chạy cùng lúc
        # (hay trong lúc chạy test) không hỏng vì "index.lock exists"
        status = subprocess.check_output(["git", "--no-optional-locks", "status", "--porcelain"], cwd=PROJECT_ROOT,
                                         timeout=20, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
        info["dirty"] = bool(status.strip())
    except (OSError, subprocess.SubprocessError) as exc:
        info["error"] = str(exc)
    return info


def _number(text: str, *, positive: bool = False, nonnegative: bool = False, nonzero: bool = False) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"cần một số, nhận '{text}'") from exc
    if not math.isfinite(value) or (positive and value <= 0) or (nonnegative and value < 0) or (nonzero and value == 0):
        need = "> 0" if positive else ">= 0" if nonnegative else "khác 0" if nonzero else "hữu hạn"
        raise argparse.ArgumentTypeError(f"cần số hữu hạn {need}, nhận '{text}'")
    return value


def _positive(text: str) -> float:
    return _number(text, positive=True)


def _nonnegative(text: str) -> float:
    return _number(text, nonnegative=True)


def _nonzero(text: str) -> float:
    return _number(text, nonzero=True)


def _count(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"cần số nguyên, nhận '{text}'") from exc
    if value < 1:
        raise argparse.ArgumentTypeError(f"cần số nguyên >= 1, nhận '{text}'")
    return value


def _name(text: str) -> str:
    if not text or any(c in text for c in '/\\:*?"<>|[]') or text.strip(". ") != text:
        raise argparse.ArgumentTypeError(f"tên phải là một tên tệp đơn giản (không /, \\, :, ...), nhận '{text}'")
    return text


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m autopark.evaluation.fault_drill",
                                 description="Diễn tập tiêm lỗi có kiểm soát (T6) trên MÔ PHỎNG: bo mô phỏng, camera "
                                             "giả hoặc bản ghi phát lại. Không mở cổng COM, LiDAR hay camera.")
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repeat", type=_count, default=1, help="số lần lặp (mặc định 1)")
        p.add_argument("--out", type=Path, required=True, help="thư mục kết quả, ví dụ runs\\fault_drill\\<ngày>")
        p.add_argument("--name", type=_name, required=True,
                       help="tên đợt: <out>/<name>_<kk>/ và <out>/<name>.drill.json")

    def session_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO,
                       help="kịch bản sa bàn (mặc định scenarios/thao_tac_cua_hep.json); xe theo cấu hình của "
                            "kịch bản")
        p.add_argument("--sim-config", type=Path, default=DEFAULT_SIM_CONFIG,
                       help="cấu hình bo mô phỏng (mặc định configs/vehicle_io_sim_nghiem_thu.json)")
        p.add_argument("--at-speed", type=_nonzero, default=0.05,
                       help="gây lỗi khi tốc độ ĐO của telemetry đạt chừng ấy m/s (âm: lúc đang lùi), mặc định 0,05")

    pose = sub.add_parser("pose", help="CB-6: nguồn tư thế ngừng cập nhật giữa lúc chạy")
    common(pose)
    session_args(pose)
    pose.add_argument("--mode", choices=[m.value for m in PoseFault], default=PoseFault.HOLD.value,
                      help="hold: giữ mẫu cũ (stamp cũ); silent: không trả mẫu nào")
    pose.add_argument("--resume-after", type=_nonnegative, default=0.1,
                      help="trả lại tư thế chừng ấy giây sau khi phiên dừng (xe đang phanh); 0 = không bao giờ")

    hang = sub.add_parser("hang", help="CB-5 (b), L7: vòng điều khiển của laptop treo, bo vẫn chạy")
    common(hang)
    session_args(hang)
    hang.add_argument("--seconds", type=_positive, default=1.0, help="thời lượng treo (s), mặc định 1")
    hang.add_argument("--heartbeat", action="store_true", help="có Heartbeat (PING giữ liên lạc) trong lúc treo")
    hang.add_argument("--phases", type=int, nargs="+", default=[0],
                      help="pha của nhịp điều khiển lúc treo (0..3; 0 = bước đầu sau khi hết treo là nhịp điều khiển); "
                           "số lần chạy = repeat × số pha")

    camera = sub.add_parser("camera", help="CB-2: một camera đứng hình (camera giả hoặc bản ghi phát lại)")
    common(camera)
    camera.add_argument("--mode", choices=[m.value for m in FreezeMode], default=FreezeMode.STALL.value,
                        help="stall: không trả khung nào; repeat: driver trả lại khung cũ")
    camera.add_argument("--ports", type=int, nargs="+", default=[1, 2], help="các cổng camera (mặc định 1 2)")
    camera.add_argument("--port", type=int, default=2, help="cổng bị đóng băng (mặc định 2)")
    camera.add_argument("--seconds", type=_positive, default=1.0, help="thời lượng đóng băng (s), mặc định 1")
    camera.add_argument("--warmup", type=_positive, default=1.0, help="chạy trước khi đóng băng (s), mặc định 1")
    camera.add_argument("--period-ms", type=_positive, default=33.0,
                        help="chu kỳ khung của camera giả (ms), mặc định 33")
    camera.add_argument("--replay", type=Path, default=None,
                        help="thư mục bản ghi phiên bàn thử (autopark.rig.recording) thay cho camera giả")
    return ap


def _plan_runs(ap: argparse.ArgumentParser, args) -> list[tuple[str, dict]]:
    """(kind, params) của từng lần chạy, theo thứ tự; lỗi tham số → ap.error (mã 2)."""
    if args.command in ("pose", "hang"):
        for label, path in (("--scenario", args.scenario), ("--sim-config", args.sim_config)):
            if not Path(path).is_file():
                ap.error(f"{label}: không thấy tệp '{path}'")
        base = {"scenario": str(Path(args.scenario).resolve()), "sim_config": str(Path(args.sim_config).resolve()),
                "at_speed_mps": args.at_speed}
        if args.command == "pose":
            return [("pose", {**base, "mode": args.mode, "resume_after_s": args.resume_after})
                    for _ in range(args.repeat)]
        from autopark.application.session import Session

        bad = [p for p in args.phases if not 0 <= p < Session.CONTROL_EVERY]
        if bad:
            ap.error(f"--phases: pha phải trong 0..{Session.CONTROL_EVERY - 1}, nhận {bad}")
        return [("hang", {**base, "seconds": args.seconds, "heartbeat": args.heartbeat, "phase": phase})
                for _ in range(args.repeat) for phase in args.phases]
    ports = list(dict.fromkeys(args.ports))
    if args.port not in ports:
        ap.error(f"--port {args.port} không nằm trong --ports {ports}")
    replay = None
    if args.replay is not None:
        from autopark.rig.replay import ReplayError, ReplaySession

        try:
            duration = ReplaySession(args.replay, ports=ports).duration_s
        except (ReplayError, ValueError, OSError) as exc:
            ap.error(f"--replay: {exc}")
        need = args.warmup + args.seconds + REJOIN_WAIT_S
        if duration < need:
            ap.error(f"--replay: bản ghi dài {duration:.2f} s, cần ≥ {need:.2f} s (làm nóng + đóng băng + chờ quay "
                     f"lại)")
        replay = str(Path(args.replay).resolve())
    params = {"mode": args.mode, "port": args.port, "ports": ports, "seconds": args.seconds, "warmup_s": args.warmup,
              "period_ms": args.period_ms, "replay": replay}
    return [("camera", dict(params)) for _ in range(args.repeat)]


def main(argv: list[str] | None = None) -> int:
    # tiến trình không cửa sổ có thể bị EcoQoS làm chậm; AUTOPARK_KEEP_ECOQOS=1 giữ mặc định (power_throttling.py)
    ecoqos = apply_ecoqos_policy("evaluation.fault_drill").state
    ap = build_parser()
    args = ap.parse_args(argv)
    out: Path = args.out
    runs = _plan_runs(ap, args)
    width = max(2, len(str(len(runs))))
    summary_path = out / f"{args.name}.drill.json"
    folders = [out / f"{args.name}_{k:0{width}d}" for k in range(1, len(runs) + 1)]
    taken = [p.name for p in [summary_path, *folders] if p.exists()]
    if taken:
        ap.error(f"--name '{args.name}' đã có kết quả trong '{out}' ({', '.join(taken[:3])}): chọn tên khác, không ghi "
                 f"đè bằng chứng cũ")
    out.mkdir(parents=True, exist_ok=True)
    print(f"Diễn tập tiêm lỗi '{args.command}' ({len(runs)} lần), CHỈ MÔ PHỎNG; EcoQoS: {ecoqos}", flush=True)
    rows, t0 = [], time.perf_counter()
    for k, ((kind, params), folder) in enumerate(zip(runs, folders), start=1):
        try:
            if kind == "camera":
                result = run_camera(k, params, folder)
                line = camera_line(k, len(runs), result)
            else:
                result = run_session(kind, k, params, folder)
                line = session_line(k, len(runs), result)
            row = result.to_dict()
        except Exception as exc:  # noqa: BLE001 - một lần chạy hỏng không được làm mất tóm tắt của các lần khác
            row = {"kind": kind, "run": k, "params": params, "problems": [f"Lỗi khi chạy: {exc!r}"], "ok": False}
            line = f"[{k}/{len(runs)}] {kind}: LỖI {exc!r} → KHÔNG ĐẠT"
        print(line, flush=True)
        rows.append({"folder": folder.name, **row})
    ok = all(r["ok"] for r in rows)
    _write_json(summary_path, {
        "tool": TOOL, "command": args.command, "argv": list(sys.argv[1:] if argv is None else argv),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "evidence": EVIDENCE,
        "note": ("Chỉ mô phỏng: bo mô phỏng (SimVehicleIO + FirmwareModel), camera giả hoặc bản ghi phát lại. ĐẠT là "
                 "kiểm của công cụ suy từ tham số hiện tại, không phải ngưỡng nghiệm thu đã chốt."),
        "ecoqos": ecoqos, "python": sys.version, "platform": platform.platform(), "git": _git_state(),
        "elapsed_s": round(time.perf_counter() - t0, 2), "runs": rows, "ok": ok})
    passed = sum(1 for r in rows if r["ok"])
    print(f"{passed}/{len(rows)} lần ĐẠT; tóm tắt: {summary_path}", flush=True)
    return 0 if ok else 1


def _link_log_files() -> tuple[str, ...]:
    """Tên các tệp `VehicleLink.write_logs` ghi, theo thứ tự, lấy từ chính hàm đó: ghi log của một liên kết mô phỏng
    chưa mở lần chạy nào vào thư mục tạm rồi xóa (hàm luôn ghi đủ mọi tệp, kể cả tệp chỉ có dòng tiêu đề). Danh sách
    viết tay đã lệch một lần (T9 thêm poses.csv, clock.csv; T15 thêm board_actions.csv)."""
    import tempfile

    from autopark.application.vehicle_link import DriveMode, VehicleLink

    with tempfile.TemporaryDirectory(prefix="fault_drill_") as tmp:
        return tuple(VehicleLink.simulated(DriveMode.VEHICLE_IO).write_logs(tmp))


def __getattr__(name: str):
    """`SESSION_FILES` = `_link_log_files()` + DRILL_FILES, tính lần đầu cần tới (PEP 562) rồi giữ lại: không ghi thử
    lúc nạp module, và lệnh camera không phải nạp lớp nối."""
    if name == "SESSION_FILES":
        files = (*_link_log_files(), *DRILL_FILES)
        globals()[name] = files
        return files
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    raise SystemExit(main())
