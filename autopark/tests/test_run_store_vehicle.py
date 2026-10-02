"""Gói lần chạy (`storage/run_store.py`) và phát lại log của lần chạy qua VehicleIO (T9).

Tối 24/09/2026: gói replay chỉ dành cho nhánh SIM, lần chạy qua VehicleIO bị từ chối rõ ràng. Cập nhật 02/10/2026 (T9):
lần chạy qua VehicleIO (VEHICLE_IO, OBSERVE) xuất được gói có thêm vehicle_io/ (log VehicleLink kèm băng phát lại), và
gói đó được PHÁT LẠI LOG: chạy lại cùng phần mềm trên đầu vào đã ghi, so lệnh, sự kiện (cả dòng session_stop của T13),
kết quả với bản ghi. Gói SIM vẫn tái mô phỏng như trước.

Chạy trên chuỗi MÔ PHỎNG (SimVehicleIO + FirmwareModel) hoặc cổng serial GIẢ (FirmwareSerialLoopback + ManualClock);
không mở cổng nào, không camera, không LiDAR thật.
"""
import csv
import json
import os
import random
import re
import shutil
import sys
from dataclasses import replace

import pytest

from autopark.application.session import SessionError, SessionState
from autopark.application.vehicle_link import (CLOCK_FIELDS, EVENT_FIELDS, LOG_FORMAT, POSE_FIELDS, SESSION_STOP,
                                               TELEMETRY_FIELDS, DriveMode, VehicleLink)
from autopark.application.vehicle_replay import ReplayVehicleLink
from autopark.domain.types import Obstacle
from autopark.fusion.bridge import ObstacleBridge
from autopark.storage import run_store
from autopark.storage.run_store import ReplayNotSupported, export_run, replay_run, replay_vehicle_run
from autopark.transport.firmware_model import FirmwareModel
from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock
from autopark.transport.protocol import Result
from autopark.transport.vehicle_io import SIM_FIRMWARE_DEFAULT, SerialVehicleIO, SimIOConfig
from tests.test_session_stop_log import invalid_lidar_map
from tests.test_session_vehicle import (FAST_FW, FixedPose, FlakyPose, advance_until, drop_sensor, link_for, read_csv,
                                        run_until_done, sim_io, still_inputs, straight_session)

SIM_CFG = SimIOConfig(firmware=replace(SIM_FIRMWARE_DEFAULT, boot_hold_ms=200))


@pytest.fixture(autouse=True)
def no_hardware_probe(monkeypatch):
    monkeypatch.setattr(run_store, "environment", lambda: {"test": True})   # không gọi PowerShell


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def simulated_run(scenario, cfg, mode=DriveMode.VEHICLE_IO):
    """Lần chạy đường thẳng qua bo mô phỏng của `VehicleLink.simulated`; quan sát: người lái mô phỏng chạy 0,5 s rồi
    người dùng bấm Dừng."""
    session = straight_session(scenario, cfg)
    link = VehicleLink.simulated(mode, SIM_CFG)
    session.set_vehicle_link(link)
    session.start_run()
    if mode == DriveMode.OBSERVE:
        link.human.set(0.1, 0.0)
        session.advance(0.5)
        session.request_stop()
    run_until_done(session)
    assert session.state in (SessionState.COMPLETED, SessionState.STOPPED)
    return session


def session_stops(link: VehicleLink) -> list[tuple]:
    """Dòng session_stop (T13) của events.csv, trừ hai cột đồng hồ (t_io, t_perf)."""
    return [(r["t_session"], r["source"], r["code"], r["action"], r["message"]) for r in link.event_rows
            if r["handling"] == SESSION_STOP]


def replay_package(session, tmp_path, name="goi"):
    """Xuất gói của lần chạy rồi phát lại log; trả (gói, phiên phát lại, báo cáo)."""
    bundle = export_run(session, tmp_path / name)
    replayed, report = replay_vehicle_run(bundle)
    return bundle, replayed, report


def shift_observed_pose(bundle, index: int = 49, dx: float = 0.02) -> dict:
    """Sửa tay poses.csv của gói: dời x của mẫu 'observe' thứ index + 1. Trả dòng đã sửa."""
    path = bundle / "vehicle_io" / "poses.csv"
    rows = read_csv(path)
    target = [r for r in rows if r["use"] == "observe"][index]
    target["x"] = repr(float(target["x"]) + dx)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=POSE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return target


# ---- xuất gói và phát lại ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", [DriveMode.VEHICLE_IO, DriveMode.OBSERVE])
def test_vehicle_io_run_exports_a_package_that_replays_exactly(scenario, cfg, tmp_path, mode):
    session = simulated_run(scenario, cfg, mode)
    assert session.run_snapshot["vehicle_link"]["mode"] == mode.value
    bundle, replayed, report = replay_package(session, tmp_path)
    try:
        snapshot = json.loads((bundle / "config_snapshot" / "run.json").read_text(encoding="utf-8"))
        assert snapshot["vehicle_link"]["mode"] == mode.value
        for name in ("result.json", "events.jsonl", "safety_events.json", "source.zip", "telemetry.csv"):
            assert (bundle / name).exists(), name
        tape = bundle / "vehicle_io"
        for name in ("commands.csv", "telemetry.csv", "events.csv", "start_refusals.csv", "board_actions.csv",
                     "poses.csv", "clock.csv", "link.json"):
            assert (tape / name).exists(), name
        info = json.loads((tape / "link.json").read_text(encoding="utf-8"))
        assert info["log_format"] == LOG_FORMAT == 2 and info["run_start"]["t_io0"] == session.run_link._io_t0
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        assert (manifest["evidence"], manifest["model"], manifest["replay_kind"]) == \
            ("simulation_only", "vehicle_io_mirror", "vehicle_io_log")
        assert report.ok, "\n".join(report.lines())
        assert report.max_clock_diff_s == 0.0 and report.mode == mode.value
        assert report.compared["commands.csv"] == len(session.run_link.command_rows) > 0
        assert replayed.state == session.state and isinstance(replayed.run_link, ReplayVehicleLink)
        assert [e.code for e in replayed.safety_events] == [e.code for e in session.safety_events]
        assert session_stops(replayed.run_link) == session_stops(session.run_link)
        assert "KHỚP" in report.lines()[0] and "KHÔNG chạy lại xe, bo hay định vị" in report.lines()[-1]
        assert json.loads(json.dumps(report.to_dict()))["compared"] == report.compared
        assert replay_run(bundle).state == session.state
        if mode == DriveMode.OBSERVE:
            assert replayed.run_link.io.send_calls == 0               # quan sát: phát lại cũng không gửi gì
            assert session_stops(session.run_link)[0][1:3] == ("user", "USER_STOP")
    finally:
        replayed.close()
        session.close()


def test_export_refuses_when_the_run_link_is_set_even_without_the_snapshot_key(scenario, cfg, tmp_path):
    session = straight_session(scenario, cfg)
    session.set_vehicle_link(VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG))
    session.start_run()
    run_until_done(session)
    del session.run_snapshot["vehicle_link"]                     # lớp phòng thủ thứ hai: dựa vào run_link
    with pytest.raises(ReplayNotSupported, match="VEHICLE_IO"):
        export_run(session, tmp_path / "goi")
    assert not (tmp_path / "goi").exists()


def test_replay_refuses_a_bundle_whose_snapshot_came_through_vehicle_io(scenario, cfg, tmp_path):
    session = straight_session(scenario, cfg)                    # nhánh SIM: đóng gói và phát lại được
    session.start_run()
    run_until_done(session)
    bundle = export_run(session, tmp_path / "sim")
    assert replay_run(bundle).state == session.state
    run_json = bundle / "config_snapshot" / "run.json"
    snapshot = json.loads(run_json.read_text(encoding="utf-8"))
    snapshot["vehicle_link"] = {"mode": "VEHICLE_IO", "evidence": "hardware_untested"}   # như gói do bản cũ ghi
    run_json.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(ReplayNotSupported, match="Không phát lại") as info:
        replay_run(bundle)
    assert "hardware_untested" in str(info.value) and "nhánh mô phỏng SIM" in str(info.value)


def test_export_refuses_a_vehicle_io_snapshot_without_its_link(scenario, cfg, tmp_path):
    session = simulated_run(scenario, cfg)
    link, session.run_link = session.run_link, None              # phiên không còn log VehicleLink của lần chạy
    with pytest.raises(ReplayNotSupported, match="không còn log VehicleLink") as info:
        export_run(session, tmp_path / "goi")
    assert "chế độ VEHICLE_IO" in str(info.value) and "simulation_only" in str(info.value)
    assert isinstance(info.value, ValueError)                    # nơi gọi cũ bắt ValueError vẫn bắt được
    assert not (tmp_path / "goi").exists()
    session.run_link = link
    session.close()


def test_export_refuses_a_link_that_does_not_match_the_snapshot(scenario, cfg, tmp_path):
    session = simulated_run(scenario, cfg)
    session.run_snapshot["vehicle_link"]["mode"] = "OBSERVE"
    with pytest.raises(ReplayNotSupported, match=r"chế độ trong snapshot \(OBSERVE\) khác chế độ của liên kết"):
        export_run(session, tmp_path / "goi")
    session.run_snapshot["vehicle_link"]["mode"] = "VEHICLE_IO"
    session.run_link.run_start = None
    with pytest.raises(ReplayNotSupported, match="chưa mở lần chạy nào"):
        export_run(session, tmp_path / "goi")
    assert not (tmp_path / "goi").exists()
    session.close()


# ---- băng phát lại trong log VehicleLink ---------------------------------------------------------------------------
def test_link_logs_record_every_io_read_and_pose_sample(scenario, cfg, tmp_path):
    session = straight_session(scenario, cfg)
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG)
    session.set_vehicle_link(link)
    session.start_run()
    run_until_done(session)
    assert session.state == SessionState.COMPLETED               # không qua STOPPING: bước nào cũng có refresh
    steps = session.world.step_count
    clock = link.clock_rows
    assert [r["kind"] for r in clock] == ["refresh", "pump"] * steps
    assert [r["call"] for r in clock] == list(range(2 * steps))
    # refresh đầu bước ghi world.time lúc đầu bước = t của pump bước trước
    assert clock[0]["t_session"] == 0.0
    assert all(clock[2 * k + 1]["t_session"] == clock[2 * k + 2]["t_session"] for k in range(steps - 1))
    calls = [r["call"] for r in link.telemetry_rows]
    assert calls[0] == 0 and calls == sorted(calls) and calls[-1] < len(clock)   # khung lúc START: lần đọc đầu
    uses = [r["use"] for r in link.pose_rows]
    assert uses.count("estimate") == steps
    assert uses.count("observe") == sum(r["kind"] == "TRACK" for r in link.command_rows) > 0
    assert [r["n"] for r in link.pose_rows] == list(range(len(uses)))
    assert all(r["available"] == 1 and r["source_id"] == "sim_truth_pose" for r in link.pose_rows)
    assert [r["call"] for r in link.event_rows] == [""] * len(link.event_rows)   # START_CHECK: dòng của lớp nối
    written = link.write_logs(tmp_path / "lan")
    for name, fields in (("poses.csv", POSE_FIELDS), ("clock.csv", CLOCK_FIELDS),
                         ("telemetry.csv", TELEMETRY_FIELDS), ("events.csv", EVENT_FIELDS)):
        assert written[name].read_text(encoding="utf-8").splitlines()[0].split(",") == fields
    assert TELEMETRY_FIELDS[-1] == EVENT_FIELDS[-1] == "call"
    info = json.loads(written["link.json"].read_text(encoding="utf-8"))
    start = info["run_start"]
    assert info["log_format"] == 2 and start["t_io0"] == link._io_t0 and info["io_source_id"] == "sim_vehicle_io"
    assert (start["x"], start["y"], start["yaw_rad"]) == (0.5, 1.0, 0.0)
    assert start["state_source"] == "sim_vehicle_io+sim_truth_pose"
    session.close()


def test_link_json_has_no_run_start_before_any_run(tmp_path):
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG)
    info = json.loads(link.write_logs(tmp_path / "chua_chay")["link.json"].read_text(encoding="utf-8"))
    assert info["run_start"] is None and info["log_format"] == 2 and info["io_source_id"] is None
    assert read_csv(tmp_path / "chua_chay" / "poses.csv") == [] and read_csv(tmp_path / "chua_chay" / "clock.csv") == []


# ---- phát lại các kiểu dừng ----------------------------------------------------------------------------------------
def moving(scenario, cfg, *, mode=DriveMode.VEHICLE_IO, pose_factory=None, io=None):
    """Lần chạy đường thẳng qua `SimVehicleIO` tiêm vào, tiến tới khi xe thật sự chạy (> 0,1 m/s); quan sát thì người
    lái không có, chỉ tiến 0,5 s."""
    session = straight_session(scenario, cfg)
    io = io or sim_io(cfg, scenario.start)
    pose = pose_factory(io) if pose_factory is not None else None
    session.set_vehicle_link(link_for(mode, io, pose))
    session.start_run()
    if mode == DriveMode.OBSERVE:
        session.advance(0.5)
    else:
        advance_until(session, lambda: io.truth.speed > 0.1)
    return session, io, pose


def armed_elsewhere(scenario, cfg):
    """Quan sát với bo đã ARM từ trước; giữa lúc quan sát, bên khác ARM và gửi lệnh: lớp nối gửi DISARM ngay trong
    lần đọc io (chờ ACK bên trong lần đọc)."""
    io = sim_io(cfg, scenario.start)
    io.connect()
    io.wait_ready()
    io.arm()
    session, io, _ = moving(scenario, cfg, mode=DriveMode.OBSERVE, io=io)
    io.arm()
    io.send(0.1, 0.0)
    return session, io


def reject_commands(io) -> None:
    firmware = io.firmware
    firmware._handle_command = lambda msg, now: firmware._ack(msg, Result.BAD_FIELD)


# tên: (gây lỗi giữa lúc chạy, mã sự kiện an toàn đầu tiên (None: không có), (nguồn, mã) của dòng session_stop đầu)
STOPS = {
    "stale_pose": (lambda s, io, pose: setattr(pose, "dead", True), "STALE_POSE", ("vehicle_link", "STALE_POSE")),
    "estop": (lambda s, io, pose: io.set_estop(True), "VEHICLE_FAULT", ("sim_vehicle_io", "VEHICLE_FAULT")),
    "link_cut": (lambda s, io, pose: io.set_link(False), "STALE_TELEMETRY", ("vehicle_link", "STALE_TELEMETRY")),
    "obstacle": (lambda s, io, pose: s.inject_obstacle(Obstacle("vat_moi", io.truth.pose.x + 0.35, 1.0, 0.05, 0.05)),
                 "MAP_CHANGED", ("sim_safety", "MAP_CHANGED")),
    # vật chèn vào đè lên mũi xe: MAP_CHANGED rồi va chạm hình học ở bước sau (dòng session_stop COLLISION, FAULT)
    "collision": (lambda s, io, pose: s.inject_obstacle(Obstacle("vat_cham", *s.world.state.pose.to_world(0.25, 0.0),
                                                                 0.05, 0.30)),
                  "MAP_CHANGED", ("sim_safety", "MAP_CHANGED")),
    "user_stop": (lambda s, io, pose: s.request_stop(), None, ("user", "USER_STOP")),
    "bridge_stop": (lambda s, io, pose: ObstacleBridge(s, prefix="lidar").inject(invalid_lidar_map(s)), None,
                    ("lidar_bridge", "FUSED_MAP_INVALID")),
    "command_rejected": (lambda s, io, pose: reject_commands(io), "COMMAND_REJECTED",
                         ("sim_vehicle_io", "COMMAND_REJECTED")),
    "steer_lost": (lambda s, io, pose: drop_sensor(io, steer_available=False), "NO_MEASURED_STATE",
                   ("vehicle_link", "NO_MEASURED_STATE")),
    "observe_armed_elsewhere": (None, "OBSERVE_NOT_DISARMED", ("vehicle_link", "OBSERVE_NOT_DISARMED")),
}


@pytest.mark.parametrize("case", list(STOPS))
def test_replay_reproduces_the_stop(scenario, cfg, tmp_path, case):
    act, first_code, first_stop = STOPS[case]
    if act is None:
        session, io = armed_elsewhere(scenario, cfg)
    else:
        session, io, pose = moving(scenario, cfg, pose_factory=FlakyPose)
        act(session, io, pose)
    run_until_done(session, step=0.1)
    link = session.run_link
    codes = [e.code for e in session.safety_events]
    assert (codes[0] if codes else None) == first_code
    assert session_stops(link)[0][1:3] == first_stop
    if case == "link_cut":
        assert {"TELEMETRY_STALE", "STOP_NOT_CONFIRMED"} <= set(codes) and session.state == SessionState.FAULT
    if case == "collision":
        assert "COLLISION" in [s[2] for s in session_stops(link)] and session.state == SessionState.FAULT
    # Sự kiện VehicleIO do một lần đọc io trả mang số lần đọc; dòng của lớp nối và của phiên thì không.
    for row in link.event_rows:
        from_io = row["source"] == io.source_id and row["handling"] in ("stop", "log", "after_run")
        assert (row["call"] != "") == from_io, row
    bundle, replayed, report = replay_package(session, tmp_path)
    try:
        assert report.ok, "\n".join(report.lines())
        assert report.max_clock_diff_s == 0.0
        assert [e.code for e in replayed.safety_events] == codes and replayed.state == session.state
        assert session_stops(replayed.run_link) == session_stops(link)      # dòng session_stop dựng lại đúng
        assert replayed.run_events == session.run_events
    finally:
        replayed.close()
        session.close()


def test_replay_of_a_realtime_serial_link_follows_the_recorded_io_clock(scenario, cfg, tmp_path):
    """Cổng serial GIẢ, ManualClock: thời gian phiên bám io.now(); vòng điều khiển treo 300 ms. Phát lại không theo thời
    gian thực, đồng hồ io lấy từ băng."""
    session = straight_session(scenario, cfg)
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW, boot_id=0xB007), clock, inputs=still_inputs)
    io = SerialVehicleIO(loop, clock=clock, rng=random.Random(1))
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FixedPose(io, scenario.start))
    session.set_vehicle_link(link)
    session.start_run()
    assert link.realtime
    for _ in range(6):
        loop.advance(50)
        session.advance(0.016)
    loop.advance(300)                                            # giao diện treo: không đọc gì trong 300 ms
    for _ in range(300):
        loop.advance(16)
        session.advance(0.016)
        if not session.simulating:
            break
    assert session.state == SessionState.STOPPED
    bundle, replayed, report = replay_package(session, tmp_path)
    try:
        assert report.ok, "\n".join(report.lines())
        assert isinstance(replayed.run_link, ReplayVehicleLink) and not replayed.run_link.realtime
        assert replayed.run_link.io.extra_reads == 0
        t0 = link.run_start["t_io0"]
        assert any(abs((r["t_io"] - t0) - r["t_session"]) > 0.001 for r in link.clock_rows)   # đồng hồ từ băng
        assert [r["t_io"] for r in replayed.run_link.clock_rows] == [r["t_io"] for r in link.clock_rows]
    finally:
        replayed.close()
        session.close()


def test_replay_names_the_first_divergence_of_a_tampered_pose_log(scenario, cfg, tmp_path):
    session = simulated_run(scenario, cfg)
    bundle = export_run(session, tmp_path / "goi")
    target = shift_observed_pose(bundle)
    replayed, report = replay_vehicle_run(bundle)
    try:
        assert not report.ok and "KHÁC" in report.lines()[0]
        first = report.mismatches[0]
        assert first.file == "commands.csv" and first.t_session == float(target["t_session"])
        assert first.describe().startswith(f"commands.csv dòng {first.row} (t_session")
    finally:
        replayed.close()
    with pytest.raises(ValueError, match="Phát lại khác bản ghi"):
        replay_run(bundle)
    session.close()


def test_replay_reports_frames_taken_outside_the_link(scenario, cfg, tmp_path):
    """Giới hạn đã ghi: khung bị lấy khỏi hàng đợi của VehicleIO ngoài lớp nối (ở đây `io.advance()` lúc treo, kết quả
    bỏ đi) không có trên băng, nên bản phát lại KHÁC; quyết định dừng vẫn như bản ghi."""
    session, io, _ = moving(scenario, cfg)
    io.advance(0.25)
    run_until_done(session, step=0.1)
    bundle, replayed, report = replay_package(session, tmp_path)
    try:
        assert not report.ok
        assert any(m.file == "commands.csv" and m.column == "telemetry_age_s" for m in report.mismatches)
        assert [e.code for e in replayed.safety_events] == [e.code for e in session.safety_events]
        assert replayed.state == session.state
    finally:
        replayed.close()
        session.close()


@pytest.mark.parametrize("damage", ["poses.csv", "clock.csv", "log_format"])
def test_replay_refuses_logs_without_the_replay_tape(scenario, cfg, tmp_path, damage):
    session = simulated_run(scenario, cfg)
    bundle = export_run(session, tmp_path / "goi")
    session.close()
    tape = bundle / "vehicle_io"
    if damage == "log_format":                                   # như log ghi trước T9
        info = json.loads((tape / "link.json").read_text(encoding="utf-8"))
        del info["log_format"]
        (tape / "link.json").write_text(json.dumps(info), encoding="utf-8")
    else:
        (tape / damage).unlink()
    for replay in (replay_vehicle_run, replay_run):
        with pytest.raises(ReplayNotSupported, match=damage) as info:
            replay(bundle)
        assert "Không phát lại: log VehicleLink" in str(info.value)


def test_replay_refuses_a_tape_with_a_broken_row_or_no_call_column(scenario, cfg, tmp_path):
    session = simulated_run(scenario, cfg)
    bundle = export_run(session, tmp_path / "goi")
    session.close()
    clock_csv = bundle / "vehicle_io" / "clock.csv"
    lines = clock_csv.read_text(encoding="utf-8").splitlines()
    call, kind, t_session, _t_io = lines[3].split(",")
    lines[3] = ",".join((call, kind, t_session, "khong_phai_so"))   # dòng dữ liệu thứ 3
    clock_csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ReplayNotSupported, match="clock.csv dòng 3: ValueError"):
        replay_vehicle_run(bundle)
    events_csv = bundle / "vehicle_io" / "events.csv"
    rows = read_csv(events_csv)
    with events_csv.open("w", newline="", encoding="utf-8") as f:            # như events.csv ghi trước T9
        writer = csv.DictWriter(f, fieldnames=EVENT_FIELDS[:-1], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ReplayNotSupported, match="events.csv thiếu cột call"):
        replay_vehicle_run(bundle)


def test_replay_refuses_a_damaged_package_instead_of_escaping(scenario, cfg, tmp_path, capsys):
    """Sửa sau review 02/10/2026: gói hỏng kiểu nào cũng là ReplayNotSupported (CLI: mã 2), không thoát ra thành lỗi
    khác (CLI: traceback, mã 1 như một lần phát lại KHÁC). Tệp mở rồi lưu bằng Excel theo bảng mã ANSI bị từ chối nói rõ
    tệp; lưu thành "CSV UTF-8" (có BOM) thì đọc được và phát lại KHỚP."""
    from autopark.evaluation import replay as replay_cli

    session = simulated_run(scenario, cfg)
    bundle = export_run(session, tmp_path / "goi")
    session.close()

    def edit_text(path, change, encoding="utf-8"):
        path.write_bytes(change(path.read_text(encoding="utf-8")).encode(encoding, errors="replace"))

    def edit_json(path, change):
        path.write_text(json.dumps(change(json.loads(path.read_text(encoding="utf-8"))), ensure_ascii=False),
                        encoding="utf-8")

    def huge_cell(text):                                         # ô dài hơn giới hạn của mô-đun csv → csv.Error
        lines = text.splitlines()
        lines[1] += "x" * 200_000
        return "\n".join(lines) + "\n"

    cases = {
        "ansi": (lambda p: edit_text(p / "vehicle_io" / "events.csv", str, "cp1258"),
                 "events.csv không đọc được: UnicodeDecodeError"),
        "o_qua_dai": (lambda p: edit_text(p / "vehicle_io" / "clock.csv", huge_cell), "clock.csv không đọc được"),
        "result_mang": (lambda p: edit_json(p / "result.json", lambda r: [r]),
                        "result.json không phải một đối tượng JSON"),
        "steps_chu": (lambda p: edit_json(p / "result.json", lambda r: dict(r, steps=str(r["steps"]))),
                      "steps phải là số nguyên"),
        "su_kien_thieu_t": (lambda p: (p / "events.jsonl").write_text('{"kind": "stop"}\n', encoding="utf-8"),
                            "events.jsonl dòng 1"),
        "snapshot_hong": (lambda p: edit_json(p / "config_snapshot" / "run.json",
                                              lambda s: dict(s, planner={"khong_co_khoa_nay": 1})),
                          "không dựng lại được phiên"),
        "ket_qua_link": (lambda p: edit_json(p / "vehicle_io" / "link.json", lambda i: dict(i, result="hỏng")),
                         "result của link.json không phải"),
        "thieu_run_json": (lambda p: (p / "config_snapshot" / "run.json").unlink(), "config_snapshot/run.json"),
    }
    for name, (damage, message) in cases.items():
        copy = shutil.copytree(bundle, tmp_path / name)
        damage(copy)
        with pytest.raises(ReplayNotSupported, match=message):
            replay_vehicle_run(copy)
    assert replay_cli.main([str(tmp_path / "ansi")]) == replay_cli.EXIT_NOT_SUPPORTED == 2
    assert "events.csv không đọc được" in capsys.readouterr().out
    # run.json thiếu hay không phải JSON: dòng lệnh vẫn nhận ra gói VehicleIO qua vehicle_io/link.json → mã 2, không rơi
    # xuống nhánh SIM rồi thoát bằng traceback, mã 1 như KHÁC (sửa sau kiểm tài liệu 02/10/2026).
    assert replay_cli.main([str(tmp_path / "thieu_run_json")]) == 2
    assert "config_snapshot/run.json" in capsys.readouterr().out
    run_json_hong = shutil.copytree(bundle, tmp_path / "run_json_hong")
    (run_json_hong / "config_snapshot" / "run.json").write_text("{khong phai json", encoding="utf-8")
    assert replay_cli.main([str(run_json_hong)]) == 2
    assert "config_snapshot/run.json" in capsys.readouterr().out
    # Excel "CSV UTF-8": BOM ở đầu tệp CSV của băng và RunLog của gói; trước đó báo nhầm "thiếu cột t_session".
    bom = shutil.copytree(bundle, tmp_path / "bom")
    for path in (bom / "vehicle_io" / "events.csv", bom / "vehicle_io" / "telemetry.csv", bom / "telemetry.csv"):
        edit_text(path, str, "utf-8-sig")
    replayed, report = replay_vehicle_run(bom)
    try:
        assert report.ok, "\n".join(report.lines())
    finally:
        replayed.close()


def test_replay_cli_keeps_exit_code_1_for_differ_only(scenario, cfg, tmp_path, monkeypatch, capsys):
    """Sửa sau review 02/10/2026: lỗi bất ngờ khi phát lại → mã 3 (không phải 1 = KHÁC), in tên lỗi; báo cáo tiếng Việt
    in được cả khi stdout là cp1252 (chuyển hướng ra tệp, không có -X utf8): CLI đổi luồng sang UTF-8, thay ký tự lạ."""
    from io import BytesIO, TextIOWrapper

    from autopark.evaluation import replay as replay_cli

    session = simulated_run(scenario, cfg)
    bundle = export_run(session, tmp_path / "goi")
    session.close()
    raw = BytesIO()
    stdout = TextIOWrapper(raw, encoding="cp1252")              # không mã hóa được "Ớ" của "KHỚP"
    monkeypatch.setattr(sys, "stdout", stdout)
    assert replay_cli.main([str(bundle)]) == replay_cli.EXIT_MATCH
    stdout.flush()
    assert "Phát lại log lần chạy qua VehicleIO" in raw.getvalue().decode("utf-8") and "KHỚP" in raw.getvalue().decode()
    monkeypatch.undo()

    def broken(_path):
        raise RuntimeError("lỗi giả của mã phát lại")

    monkeypatch.setattr(replay_cli, "replay_vehicle_run", broken)
    assert replay_cli.main([str(bundle)]) == replay_cli.EXIT_ERROR == 3
    captured = capsys.readouterr()
    assert "lỗi bất ngờ" in captured.out and "RuntimeError: lỗi giả của mã phát lại" in captured.out
    assert "Traceback" in captured.err


def test_replay_compares_seconds_printed_in_a_message_like_a_clock_column(scenario, cfg, tmp_path):
    """Sửa sau review 02/10/2026: tuổi telemetry in trong lời STALE_TELEMETRY ("Telemetry cũ (0.160 s, …)") tính từ một
    lần đọc io.now() không có trên băng; với đồng hồ tường (bo thật) chữ số ms cuối của bản phát lại có thể khác bản
    ghi. Lời đó nằm ở safety_events.json, lý do dừng (result.json, kết quả của link.json) và dòng session_stop
    (events.csv): số giây trong lời so như cột đồng hồ (lệch ≤ 5 ms là khớp); bo mô phỏng không lệch nên ở đây sửa tay
    bản ghi."""
    session, io, _ = moving(scenario, cfg, pose_factory=FlakyPose)
    io.set_link(False)
    run_until_done(session, step=0.1)
    first = session.safety_events[0]
    assert first.code == "STALE_TELEMETRY"
    age = re.search(r"Telemetry cũ \((\d+\.\d{3}) s", first.message).group(1)
    bundle = export_run(session, tmp_path / "goi")
    session.close()
    texts = ("safety_events.json", "result.json", "vehicle_io/link.json", "vehicle_io/events.csv")

    def shifted(name, delta_s):
        copy = shutil.copytree(bundle, tmp_path / name)
        old, new = f"Telemetry cũ ({age} s", f"Telemetry cũ ({float(age) + delta_s:.3f} s"
        for rel in texts:
            path = copy / rel
            text = path.read_text(encoding="utf-8")
            assert old in text, rel
            path.write_text(text.replace(old, new), encoding="utf-8")
        return copy

    replayed, report = replay_vehicle_run(shifted("lech_1ms", 0.001))
    try:
        assert report.ok, "\n".join(report.lines())
    finally:
        replayed.close()
    replayed, report = replay_vehicle_run(shifted("lech_10ms", 0.010))
    try:
        assert not report.ok
        assert {m.file for m in report.mismatches} == {"safety_events.json", "result.json", "link.json", "events.csv"}
    finally:
        replayed.close()


def test_seconds_in_text_compare_with_the_clock_tolerance_only():
    from autopark.application.vehicle_replay import ReplayTolerance, compare_rows, compare_values

    tol = ReplayTolerance()
    stale = "Telemetry cũ ({} s, ngưỡng 0.15 s): dừng và chờ đánh giá lại"
    assert compare_values("result.json", stale.format("0.152"), stale.format("0.151"), tol, column="reason") == []
    assert compare_values("result.json", stale.format("-0.001"), stale.format("0.001"), tol) == []
    found = compare_values("result.json", stale.format("0.152"), stale.format("0.160"), tol, column="reason")
    assert [m.column for m in found] == ["reason"]                               # 8 ms > 5 ms
    assert compare_values("x", stale.format("0.152"), stale.format("0.152").replace("dừng", "chạy"), tol)   # chữ khác
    assert compare_values("x", "sau 2.0 s", "sau 2.0 s nữa", tol) and compare_values("x", "1.0 s", "1.0 m", tol)
    _, found, max_clock = compare_rows("events.csv", [{"t_session": "1.0", "message": stale.format("0.152")}],
                                       [{"t_session": 1.0, "message": stale.format("0.153")}], tol)
    assert found == [] and max_clock == 0.0


def test_compare_rows_uses_the_clock_tolerance_and_reports_the_first_extra_row():
    from autopark.application.vehicle_replay import ReplayTolerance, compare_rows

    tol = ReplayTolerance()
    recorded = [{"t_session": "0.0", "t_io": "1.0", "x": "0.5", "note": ""},
                {"t_session": "0.02", "t_io": "1.02", "x": "0.6", "note": "a"},
                {"t_session": "0.04", "t_io": "1.04", "x": "0.7", "note": ""}]
    replayed = [{"t_session": 0.0, "t_io": 1.001, "x": 0.5 + 1e-12, "note": None},
                {"t_session": 0.02, "t_io": 1.02, "x": 0.6, "note": "b"}]
    n, found, max_clock = compare_rows("commands.csv", recorded, replayed, tol, clock_columns=frozenset({"t_io"}))
    assert n == 2 and max_clock == pytest.approx(0.001)                     # 1 ms ≤ 5 ms: khớp
    assert [(m.row, m.column, m.recorded, m.replayed, m.t_session) for m in found] == [
        (2, "note", "a", "b", 0.02), (3, "(số dòng)", "3 dòng", "2 dòng", 0.04)]
    _, found, _ = compare_rows("commands.csv", recorded[:1], [dict(replayed[0], t_io=1.01)], tol,
                               clock_columns=frozenset({"t_io"}))
    assert [m.column for m in found] == ["t_io"]                             # 10 ms > 5 ms
    _, found, _ = compare_rows("commands.csv", recorded[:1], [dict(replayed[0], t_io=1.0, x=0.5 + 1e-6)], tol)
    assert [m.column for m in found] == ["x"] and found[0].describe().startswith(
        "commands.csv dòng 1 (t_session 0.0000 s), cột x: ghi '0.5'")


def test_export_after_a_refused_start_replays_the_previous_run(scenario, cfg, tmp_path):
    """E-stop → dừng; "Xóa lỗi bo" khi nút còn nhấn (dòng board_actions.csv, T15); gói của lần chạy phát lại khớp. Đặt
    lại, lập đường, START bị từ chối (bo FAULT): log ghi lại sau đó vẫn mang đúng băng của lần chạy trước, cộng dòng
    từ chối ở start_refusals.csv. (Sau khi đặt lại phiên không còn thế giới để xuất gói mới, nên log được ghi đè vào
    vehicle_io/ của gói đã xuất.)"""
    session, io, _ = moving(scenario, cfg)
    io.set_estop(True)
    run_until_done(session, step=0.1)
    assert session.state == SessionState.STOPPED and session.safety_events[0].code == "VEHICLE_FAULT"
    link = session.run_link
    assert link.clear_fault().outcome == "ESTOP_PRESSED"         # không gửi gì; một dòng board_actions
    tape_before = (list(link.pose_rows), list(link.clock_rows), dict(link.run_start))
    bundle, replayed, report = replay_package(session, tmp_path)
    assert report.ok, "\n".join(report.lines())
    replayed.close()
    actions = read_csv(bundle / "vehicle_io" / "board_actions.csv")
    assert [(r["request"], r["outcome"]) for r in actions] == [("CLEAR_FAULT", "ESTOP_PRESSED")]
    session.reset()
    assert session.plan_sync().ok
    with pytest.raises(SessionError, match="FAULT"):
        session.start_run()
    assert link.refused_starts == 1 and (list(link.pose_rows), list(link.clock_rows), link.run_start) == tape_before
    link.write_logs(bundle / "vehicle_io")
    refusals = read_csv(bundle / "vehicle_io" / "start_refusals.csv")
    assert any(r["code"] == "START_CHECK" and r["message"].startswith("TỪ CHỐI") for r in refusals)
    replayed, report = replay_vehicle_run(bundle)
    try:
        assert report.ok, "\n".join(report.lines())
        assert replayed.state == SessionState.STOPPED
    finally:
        replayed.close()
        session.close()


def test_replay_cli_exit_codes(scenario, cfg, tmp_path, monkeypatch, capsys):
    from autopark.evaluation import replay as replay_cli

    def run_cli(path):
        monkeypatch.setattr(sys, "argv", ["replay", str(path)])
        code = replay_cli.main()
        return code, capsys.readouterr().out

    session = simulated_run(scenario, cfg)
    bundle = export_run(session, tmp_path / "goi")
    session.close()
    code, out = run_cli(bundle)
    assert code == 0 and "KHỚP" in out and "bằng chứng simulation_only" in out
    tampered = shutil.copytree(bundle, tmp_path / "sua_tay")
    shift_observed_pose(tampered)
    code, out = run_cli(tampered)
    assert code == 1 and "KHÁC" in out and "commands.csv" in out
    missing = shutil.copytree(bundle, tmp_path / "thieu_log")
    shutil.rmtree(missing / "vehicle_io")
    code, out = run_cli(missing)
    assert code == 2 and "thiếu thư mục vehicle_io/" in out
    sim = straight_session(scenario, cfg)                        # gói SIM: in như trước
    sim.start_run()
    run_until_done(sim)
    code, out = run_cli(export_run(sim, tmp_path / "sim"))
    assert code == 0 and out.startswith("Replay OK: COMPLETED")


# ---- giao diện -----------------------------------------------------------------------------------------------------
def test_window_save_run_writes_a_replayable_vehicle_io_package(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QFileDialog
    from autopark.ui.app import DEFAULT_SCENARIO, build_window

    def key(code):
        window._handle_key(QKeyEvent(QEvent.Type.KeyPress, code, Qt.KeyboardModifier.NoModifier))

    window = build_window(DEFAULT_SCENARIO)
    try:
        combo = window.combo_drive
        combo.setCurrentIndex(combo.findData(DriveMode.OBSERVE.value))
        assert window.plan(sync=True).ok
        window.run()
        for _ in range(5):
            key(Qt.Key.Key_Up)                                   # người lái mô phỏng (phím) chạy xe
        window.advance_by(1.0)
        key(Qt.Key.Key_Escape)
        window.advance_by(0.05)
        assert window.session.state == SessionState.STOPPED
        out = tmp_path / "lan.csv"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), "CSV (*.csv)"))
        window._export_log()
        assert out.exists() and (tmp_path / "lan_vehicle_io" / "commands.csv").exists()   # như trước T9
        packages = [p for p in tmp_path.iterdir() if p.is_dir() and p.name != "lan_vehicle_io"]
        assert len(packages) == 1 and packages[0].name.startswith("lan_")
        package = packages[0]
        assert (package / "vehicle_io" / "link.json").exists()
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["replay_kind"] == "vehicle_io_log"
        replayed = replay_run(package)
        assert replayed.state == SessionState.STOPPED
        replayed.close()
        message = window.statusBar().currentMessage()
        assert "gói phát lại" in message and package.name in message
    finally:
        window.close()
