"""Phiên đỗ xe chạy qua VehicleIO (kế hoạch mục 9: giai đoạn 5 VehicleIO, giai đoạn 9 chế độ quan sát).

Mọi test ở đây chạy trên chuỗi MÔ PHỎNG: Session → VehicleLink → SimVehicleIO → byte giao thức → FirmwareModel →
cơ cấu chấp hành giả định → SimVehicle. Tư thế lấy từ mô phỏng (SimTruthPose) hoặc là tư thế cố định (FixedPose).
Hai test đồng hồ dùng `SerialVehicleIO` với cổng serial GIẢ (FirmwareModel sau cổng giả). Không mở cổng nào, không
cần bo.
"""
from dataclasses import replace
import copy
import csv
import json
import math
import os
import random
import time

import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.application.vehicle_link import (BOARD_ACTION_FIELDS, COMMAND_FIELDS, EVENT_FIELDS, TELEMETRY_FIELDS,
                                               DriveMode, LinkParams, MirroredWorld, PoseSample, SimHumanDriver,
                                               SimTruthPose, VehicleLink, VehicleLinkError)
from autopark.domain.types import Obstacle, ParkingGoal, Pose, VehicleState
from autopark.simulation.world import SimWorld
from autopark.storage import run_store
from autopark.storage.scenario_store import load_scenario, load_vehicle_config
from autopark.transport.firmware_model import FirmwareInputs, FirmwareModel
from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock
from autopark.transport.protocol import Action, Result, State, StopReason
from autopark.transport.vehicle_io import (SIM_FIRMWARE_DEFAULT, SerialVehicleIO, SimIOConfig, SimSensorConfig,
                                           SimVehicleIO, speed_to_wire, steer_to_wire)
from tests.conftest import PROJECT_ROOT

FAST_FW = replace(SIM_FIRMWARE_DEFAULT, boot_hold_ms=200)
SIM_CFG = SimIOConfig(firmware=FAST_FW)


def parking_session() -> Session:
    scenario = load_scenario(PROJECT_ROOT / "scenarios" / "thao_tac_cua_hep.json")
    session = Session(scenario, load_vehicle_config(PROJECT_ROOT / "configs" / "vehicle_default.json"))
    assert session.plan_sync().ok
    return session


def straight_session(scenario, cfg) -> Session:
    scenario.obstacles = []
    scenario.start = Pose(0.5, 1.0, 0.0)
    scenario.goal = ParkingGoal(Pose(1.0, 1.0, 0.0))
    session = Session(scenario, cfg)
    assert session.plan_sync().ok
    return session


def sim_io(cfg, pose: Pose) -> SimVehicleIO:
    return SimVehicleIO(cfg, SIM_CFG, start=VehicleState(pose, 0.0, 0.0, 0.0))


def record_commands(io: SimVehicleIO) -> list[tuple[int, bool, int, int]]:
    """Mọi COMMAND tới được FirmwareModel (sau khung, CRC, phiên): (ms của bo, enable, mm/s, mrad)."""
    seen = []
    firmware = io.firmware
    original = firmware._handle_command

    def handle(msg, now):
        seen.append((now, bool(msg.enable), msg.speed_mm_s, msg.steer_mrad))
        original(msg, now)

    firmware._handle_command = handle
    return seen


def record_requests(io: SimVehicleIO) -> list[Action]:
    """Mọi REQUEST (ARM/DISARM/PING...) tới được FirmwareModel."""
    seen = []
    firmware = io.firmware
    original = firmware._handle_request

    def handle(msg, now):
        seen.append(Action(msg.action))
        original(msg, now)

    firmware._handle_request = handle
    return seen


def link_for(mode: DriveMode, io: SimVehicleIO, pose_source=None) -> VehicleLink:
    return VehicleLink(mode, io, pose_source=pose_source or SimTruthPose(io))


def run_until_done(session: Session, step: float = 0.5, max_calls: int = 400) -> None:
    for _ in range(max_calls):
        session.advance(step)
        if not session.simulating:
            return
    raise AssertionError(f"Phiên không kết thúc, trạng thái {session.state}")


def advance_until(session: Session, predicate, step: float = 0.1, max_calls: int = 200) -> None:
    for _ in range(max_calls):
        session.advance(step)
        if predicate():
            return
    raise AssertionError("Điều kiện không xảy ra")


def path_deviation(session: Session, pose: Pose) -> float:
    return min(math.hypot(p.pose.x - pose.x, p.pose.y - pose.y) for p in session.trajectory.points)


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def link_logs(link: VehicleLink) -> tuple:
    return (list(link.command_rows), list(link.telemetry_rows), list(link.event_rows),
            dict(link.result) if link.result is not None else None)


class FixedPose:
    """Tư thế báo về cố định, tách khỏi xe của mô phỏng; age_s > 0: mẫu cũ, < 0: mẫu ở tương lai."""

    source_id = "fixed_pose"
    simulated = True

    def __init__(self, io, pose, age_s=0.0):
        self.io, self.pose, self.age_s = io, pose, age_s

    def latest(self):
        return PoseSample(self.pose, self.io.now() - self.age_s, self.source_id, True)


# ---- SIM: mặc định, không đổi --------------------------------------------------------------------------------------
def test_sim_is_default_and_keeps_phase0_world(scenario, cfg):
    session = straight_session(scenario, cfg)
    assert session.drive_mode == DriveMode.SIM and session.vehicle_link is None
    session.start_run()
    assert type(session.world) is SimWorld and session.feedback is not None and session.run_link is None
    run_until_done(session)
    assert session.state == SessionState.COMPLETED
    assert "vehicle_link" not in session.run_snapshot
    # Chọn SIM tường minh (None) cho kết quả giống hệt mặc định.
    again = Session(type(scenario).from_dict(scenario.to_dict()), cfg)
    assert again.plan_sync().ok
    again.set_vehicle_link(None)
    again.start_run()
    run_until_done(again)
    assert again.log.rows == session.log.rows


def test_sim_link_mode_is_rejected():
    with pytest.raises(ValueError):
        VehicleLink.simulated(DriveMode.SIM)


# ---- VEHICLE_IO: vòng kín qua giao thức ---------------------------------------------------------------------------
def test_vehicle_io_follows_planned_path_through_the_firmware_model():
    session = parking_session()
    io = sim_io(session.cfg, session.scenario.start)
    received = record_commands(io)
    link = link_for(DriveMode.VEHICLE_IO, io)
    session.set_vehicle_link(link)
    session.start_run()
    assert isinstance(session.world, MirroredWorld) and session.feedback is None
    assert io.firmware.state == State.ARMED                     # START = thao tác ARM
    start_pose = io.truth.pose
    worst = 0.0
    for _ in range(600):
        session.advance(0.1)
        worst = max(worst, path_deviation(session, io.truth.pose))
        if not session.simulating:
            break
    assert session.state == SessionState.COMPLETED, session.stop_reason
    assert session.report.position_error < 0.03 and abs(session.report.heading_error) < math.radians(3)
    assert worst < 0.05                                          # bám đường: lệch tối đa so với các điểm quỹ đạo
    assert io.truth.pose.distance_to(start_pose) > 0.3           # xe trong bo giả đã thật sự chạy
    assert session.world.state.pose == io.truth.pose             # thế giới gương = tư thế từ nguồn (mô phỏng)
    assert io.firmware.state == State.DISARMED                   # kết thúc lần chạy: DISARM
    sent = [r for r in link.command_rows if r["kind"] == "TRACK"]
    assert len(sent) > 200 and all(r["sent"] == 1 for r in sent)
    # Cùng đơn vị: lệnh bộ bám (m/s, rad) tới bo đúng bằng số nguyên trên dây (mm/s, mrad).
    enabled = [(speed, steer) for _, enable, speed, steer in received if enable]
    assert len(enabled) == len(sent)
    assert enabled == [(speed_to_wire(r["target_speed_mps"]), steer_to_wire(r["target_steer_rad"])) for r in sent]
    assert any(speed < 0 for speed, _ in enabled) and any(speed > 0 for speed, _ in enabled)   # có đổi chiều
    assert link.telemetry_rows and all(r["speed_mps"] != "" for r in link.telemetry_rows)


def test_vehicle_io_stale_telemetry_stops_and_reconnect_never_resumes(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    t_cut = session.world.time
    io.set_link(False)                                           # rút cáp giả: mất mọi byte hai chiều
    run_until_done(session, step=0.1)
    codes = [e.code for e in session.safety_events]
    assert codes[0] == "STALE_TELEMETRY"
    assert session.safety_events[0].stamp.t - t_cut <= session.run_link.params.max_state_age_s + 0.03
    assert "TELEMETRY_STALE" in codes                            # sự kiện của VehicleIO cũng được ghi
    # Không có telemetry thì không xác nhận được xe đã dừng: FAULT chứ không phải STOPPED.
    assert session.state == SessionState.FAULT and "STOP_NOT_CONFIRMED" in codes
    assert session.path_invalidated and not session.trajectory.valid
    assert io.truth.speed == 0.0                                 # bo tự dừng: lệnh hết hạn, watchdog liên lạc
    enabled_before = sum(1 for c in received if c[1])

    io.set_link(True)                                            # cắm lại: telemetry có lại
    parked = io.truth.pose
    io.advance(1.0)
    assert io.rearm_required and io.latest().state == State.DISARMED
    assert session.advance(1.0) == [] and session.state == SessionState.FAULT
    io.connect()                                                 # kết nối lại: phiên mới, bo DISARMED
    io.advance(1.0)
    assert io.firmware.state == State.DISARMED and io.truth.pose == parked and io.truth.speed == 0.0
    assert sum(1 for c in received if c[1]) == enabled_before    # không một lệnh enable nào sau khi dừng

    # Chỉ một START mới (sau khi lập lại đường từ chỗ xe đứng) mới ARM lại.
    session.reset()
    assert session.state == SessionState.EDITING and session.scenario.start == parked
    assert session.plan_sync().ok
    session.start_run()
    run_until_done(session)
    assert session.state == SessionState.COMPLETED
    assert sum(1 for c in received if c[1]) > enabled_before


def test_vehicle_io_fault_stops_and_start_is_refused_until_cleared(scenario, cfg, tmp_path):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    io.set_estop(True)
    run_until_done(session, step=0.1)
    link = session.run_link
    assert session.state == SessionState.STOPPED                 # telemetry vẫn có: xác nhận được đã dừng
    assert session.safety_events[0].code == "VEHICLE_FAULT"
    assert io.firmware.state == State.FAULT and io.truth.speed == 0.0
    # Từ lúc laptop NHẬN báo lỗi: không còn lệnh enable nào tới bo (trễ đường truyền 4 ms + một nhịp 10 ms).
    learned_ms = next(r["t_io"] for r in link.event_rows if r["code"] == "VEHICLE_FAULT") * 1000
    assert not any(enable for t, enable, _, _ in received if t > learned_ms + 15)
    first_stop = next(i for i, r in enumerate(link.command_rows) if r["kind"] == "STOP")
    assert all(r["kind"] == "STOP" for r in link.command_rows[first_stop:])
    io.set_estop(False)
    io.advance(1.0)
    assert io.firmware.state == State.FAULT and io.truth.speed == 0.0   # FAULT chốt, không tự chạy lại
    session.reset()
    assert session.plan_sync().ok
    before = link_logs(link)
    session_rows = len(session.log)
    assert before[0] and before[1] and before[3]["outcome"] == "STOPPED"
    with pytest.raises(SessionError, match="FAULT"):
        session.start_run()
    assert session.state == SessionState.READY and io.firmware.state == State.FAULT
    # START bị từ chối không xóa bằng chứng của lần chạy trước: Session.log và run_link vẫn trỏ cùng một lần chạy.
    assert session.run_link is link and len(session.log) == session_rows
    assert link_logs(link) == before
    assert [r["code"] for r in link.start_refusals] == ["START_CHECK"]
    assert link.start_refusals[0]["message"].startswith("TỪ CHỐI") and link.refused_starts == 1
    written = link.write_logs(tmp_path / "x")
    assert len(read_csv(written["commands.csv"])) == len(before[0])
    info = json.loads(written["link.json"].read_text(encoding="utf-8"))
    assert info["result"]["outcome"] == "STOPPED" and info["refused_starts"] == 1 and info["runs"] == 1
    refusals = read_csv(written["start_refusals.csv"])
    assert len(refusals) == 1 and list(refusals[0]) == EVENT_FIELDS
    with pytest.raises(SessionError, match="FAULT"):
        session.start_run()
    assert len(link.start_refusals) == 2 and link.refused_starts == 2 and link_logs(link) == before
    io.clear_fault()
    session.start_run()
    assert session.state == SessionState.RUNNING and io.firmware.state == State.ARMED
    # Chỉ khi lần mới đã mở, log của lần trước mới được thay.
    assert link.command_rows == [] and link.result is None and link.runs == 2
    assert any(r["code"] == "START_CHECK" and r["message"].startswith("Đạt") for r in link.event_rows)
    assert len(link.start_refusals) == 2


def test_refused_start_keeps_the_previous_simulated_board_and_logs(scenario, cfg):
    session = straight_session(scenario, cfg)
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG)
    session.set_vehicle_link(link)
    session.start_run()
    run_until_done(session)
    assert session.state == SessionState.COMPLETED
    session.reset()
    old_io = link.io
    sent = old_io.stats.commands_sent
    before = link_logs(link)
    link.params = LinkParams(fresh_timeout_s=0.001, start_samples=50)   # không thể đủ 50 khung trong 1 ms
    with pytest.raises(SessionError, match="liên lạc"):
        session.start_run()
    assert session.state == SessionState.READY
    assert link.io is old_io and old_io.connected                  # bo mô phỏng của lần trước giữ nguyên
    assert old_io.stats.commands_sent == sent and link_logs(link) == before
    assert link.result["outcome"] == "COMPLETED"
    assert [r["code"] for r in link.start_refusals] == ["START_NO_LINK"]
    link.params = LinkParams()
    session.start_run()
    assert session.state == SessionState.RUNNING
    assert link.io is not old_io and not old_io.connected          # lần mới đã mở: tới đây mới thay bo mô phỏng


def test_start_is_refused_when_the_real_state_disagrees(scenario, cfg):
    session = straight_session(scenario, cfg)
    off = Pose(scenario.start.x + 0.10, scenario.start.y, scenario.start.yaw)
    io = sim_io(cfg, off)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    with pytest.raises(SessionError, match="lệch"):
        session.start_run()
    assert session.state == SessionState.READY and session.world is None
    assert io.firmware.state == State.DISARMED                   # bị từ chối trước khi ARM

    session.set_vehicle_link(None)
    io = sim_io(cfg, scenario.start)
    io.set_estop(True)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    with pytest.raises(SessionError, match="dừng khẩn"):
        session.start_run()
    assert io.firmware.state == State.FAULT


# ---- từng điều kiện kiểm trước START -------------------------------------------------------------------------------
def assert_refused(session, io, match, board_before=State.DISARMED):
    link = session.vehicle_link
    with pytest.raises(SessionError, match=match):
        session.start_run()
    assert session.state == SessionState.READY and session.world is None and link.runs == 0
    assert io.firmware.state == board_before and link.command_rows == []


def test_start_refused_heading_off(scenario, cfg):
    session = straight_session(scenario, cfg)
    s = scenario.start
    io = sim_io(cfg, Pose(s.x, s.y, s.yaw + math.radians(10)))
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    assert_refused(session, io, "lệch")


def test_start_refused_vehicle_rolling(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    SimHumanDriver(io).set(0.1, 0.0)                              # xe còn lăn (tốc độ đo khác 0)
    io.advance(0.5)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io, FixedPose(io, scenario.start)))
    assert_refused(session, io, "chuyển động")


def test_observe_start_refused_while_board_still_references_speed(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    SimHumanDriver(io).set(0.0, 0.0)                              # xe đứng yên, nhưng bo còn tham chiếu tốc độ
    io.connect()
    io.wait_ready()
    io.arm()
    io.send(0.1, 0.0, validity_s=0.3)
    io.advance(0.02)
    session.set_vehicle_link(link_for(DriveMode.OBSERVE, io))
    link = session.vehicle_link
    with pytest.raises(SessionError, match="chuyển động"):
        session.start_run()
    assert link.runs == 0 and link.command_rows == []


def test_start_refused_board_already_running(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    io.connect()
    io.wait_ready()
    io.arm()
    io.send(0.0, 0.0, validity_s=0.3)                             # RUNNING, tham chiếu 0: chỉ kiểm RUNNING bắt được
    io.advance(0.02)
    assert io.firmware.state == State.RUNNING
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    link = session.vehicle_link
    with pytest.raises(SessionError, match="RUNNING"):
        session.start_run()
    assert session.state == SessionState.READY and session.world is None and link.runs == 0


@pytest.mark.parametrize("age_s", [0.5, -0.5])                   # mẫu cũ và mẫu lệch đồng hồ
def test_start_refused_pose_not_fresh(scenario, cfg, age_s):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io, FixedPose(io, scenario.start, age_s)))
    assert_refused(session, io, "tư thế mới")


def test_start_refused_measured_pose_in_obstacle(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    link = link_for(DriveMode.VEHICLE_IO, io)
    blocked = copy.deepcopy(session.scenario)
    s = blocked.start
    blocked.obstacles = [Obstacle("hop_x", s.x + 0.1, s.y, 0.1, 0.1, 0.0)]
    with pytest.raises(VehicleLinkError, match="chạm vật cản"):
        link.begin_run(blocked, cfg, session.PHYSICS_DT)
    assert io.firmware.state == State.DISARMED and link.runs == 0


def test_start_refused_without_measured_speed(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = SimVehicleIO(cfg, replace(SIM_CFG, sensors=SimSensorConfig(speed_available=False)),
                      start=VehicleState(scenario.start, 0.0, 0.0, 0.0))
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    assert_refused(session, io, "encoder")


def test_start_fault_refused_by_link_check(scenario, cfg):
    # Lớp nối tự từ chối bo FAULT, không dựa vào việc firmware từ chối ARM.
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    io.set_estop(True)
    io.advance(1.0)
    io.set_estop(False)
    io.advance(0.2)
    assert io.firmware.state == State.FAULT
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    assert_refused(session, io, "CLEAR_FAULT", board_before=State.FAULT)


def test_fault_refused_start_then_link_clear_fault_then_start(scenario, cfg, tmp_path):
    """AT-2 / DI-4 (d) ở mức mô phỏng (T15, thêm 02/10/2026): E-stop giữa lúc chạy → STOPPED; nhả nút, START vẫn bị từ
    chối vì bo FAULT; `VehicleLink.clear_fault()` (nút "Xóa lỗi bo") đưa bo về DISARMED mà không ARM, không COMMAND;
    chỉ START sau đó mới ARM và gửi lệnh mới. Tên khớp cả `-k fault` lẫn `-k refused`."""
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    link = link_for(DriveMode.VEHICLE_IO, io)
    session.set_vehicle_link(link)
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    io.set_estop(True)
    run_until_done(session, step=0.1)
    assert session.state == SessionState.STOPPED and io.firmware.state == State.FAULT
    io.set_estop(False)
    io.advance(0.5)
    session.reset()
    assert session.plan_sync().ok
    with pytest.raises(SessionError, match="Xóa lỗi bo"):
        session.start_run()
    assert session.state == SessionState.READY and io.firmware.state == State.FAULT
    refusal = next(r for r in link.start_refusals if r["code"] == "START_CHECK")
    requests = record_requests(io)
    enabled = sum(1 for c in received if c[1])
    report = link.clear_fault()
    assert report.outcome == "CLEARED" and report.hello is None and report.session_reused
    # Dùng lại phiên của lần chạy: PING chờ ACK làm rào "khung mới" trước khi đọc trạng thái (sau review 02/10/2026).
    assert requests == [Action.PING, Action.CLEAR_FAULT] and report.commands_sent == 0 and report.requests_sent == 2
    io.advance(1.0)
    assert io.truth.speed == 0.0 and io.firmware.state == State.DISARMED
    assert sum(1 for c in received if c[1]) == enabled          # không lệnh enable nào sau CLEAR_FAULT
    session.start_run()
    assert session.state == SessionState.RUNNING and requests == [Action.PING, Action.CLEAR_FAULT, Action.ARM]
    advance_until(session, lambda: io.truth.speed > 0.05)
    assert sum(1 for c in received if c[1]) > enabled            # chỉ sau ARM của START mới có lệnh chạy mới
    check = next(r for r in link.event_rows if r["code"] == "START_CHECK")
    assert check["message"].startswith("Đạt")
    row = link.board_actions[0]
    assert refusal["t_io"] < row["t_io"] < check["t_io"]         # cùng đồng hồ io của liên kết
    written = link.write_logs(tmp_path / "at2")
    rows = read_csv(written["board_actions.csv"])
    assert len(rows) == 1 and list(rows[0]) == BOARD_ACTION_FIELDS
    assert (rows[0]["outcome"], rows[0]["state_before"], rows[0]["state_after"]) == ("CLEARED", "FAULT", "DISARMED")
    session.close()


# ---- sau ARM/DISARM: lỗi phải đóng an toàn -------------------------------------------------------------------------
class PoseOnlyOnce:
    """Trả tư thế hợp lệ ở lần gọi đầu (lúc kiểm trước ARM), sau đó None (nguồn định vị mất đúng lúc ARM)."""

    source_id = "pose_once"
    simulated = True

    def __init__(self, io):
        self.inner = SimTruthPose(io)
        self.calls = 0

    def latest(self):
        self.calls += 1
        return self.inner.latest() if self.calls == 1 else None


def test_pose_lost_after_arm_disarms_and_refuses_start(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    link = link_for(DriveMode.VEHICLE_IO, io, PoseOnlyOnce(io))
    session.set_vehicle_link(link)
    requests = record_requests(io)
    with pytest.raises(SessionError, match="tư thế mới"):
        session.start_run()
    assert session.state == SessionState.READY and session.world is None
    assert link._running is False and link.runs == 0
    assert Action.ARM in requests and Action.DISARM in requests[requests.index(Action.ARM) + 1:]
    assert io.firmware.state == State.DISARMED and io.firmware.stop_reason == StopReason.HOST_DISARM
    io.advance(0.1)                                              # << link_timeout 500 ms: không phải watchdog
    assert io.latest().state == State.DISARMED
    assert [r["code"] for r in link.start_refusals] == ["START_CHECK", "START_ABORTED"]


def test_observe_refuses_when_frame_after_disarm_has_no_steer(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    link = link_for(DriveMode.OBSERVE, io)
    session.set_vehicle_link(link)
    original = link._new_telemetry
    calls = []

    def frames_without_steer_after_disarm(after, count):
        frames = original(after, count)
        calls.append(count)
        if len(calls) == 2:                                      # khung đọc sau DISARM
            frames = [replace(f, steer_rad=None) for f in frames]
        return frames

    link._new_telemetry = frames_without_steer_after_disarm
    with pytest.raises(SessionError, match="góc lái"):
        session.start_run()
    assert len(calls) == 2
    assert session.state == SessionState.READY and session.world is None and link.runs == 0
    assert io.stats.commands_sent == 0 and io.firmware.state == State.DISARMED


class FlakyPose:
    source_id = "flaky_pose"
    simulated = True

    def __init__(self, io):
        self.inner = SimTruthPose(io)
        self.dead = False

    def latest(self):
        return None if self.dead else self.inner.latest()


def test_stale_pose_source_stops_the_run(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    pose = FlakyPose(io)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io, pose))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    pose.dead = True
    run_until_done(session, step=0.1)
    assert session.state == SessionState.STOPPED
    assert session.safety_events[0].code == "STALE_POSE"
    assert io.truth.speed == 0.0 and io.firmware.state == State.DISARMED


# ---- VEHICLE_IO: các mã dừng riêng ----------------------------------------------------------------------------------
def test_vehicle_io_board_disarmed_elsewhere_stops_with_vehicle_not_armed(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    io.disarm()                                                  # DISARM từ nơi khác giữa lần chạy
    run_until_done(session, step=0.1)
    link = session.run_link
    assert session.safety_events[0].code == "VEHICLE_NOT_ARMED"  # kiểm của lớp nối bắt trước VEHICLE_STOPPED
    assert session.state == SessionState.STOPPED and io.firmware.state == State.DISARMED
    learned_ms = next(r["t_io"] for r in link.event_rows if r["code"] == "VEHICLE_NOT_ARMED") * 1000
    assert not any(enable for t, enable, _, _ in received if t > learned_ms + 15)


def test_vehicle_io_command_timeout_after_freeze_never_resumes(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    io.advance(0.25)       # laptop treo 0,25 s: > thời hạn lệnh 0,15 s, < link_timeout 0,5 s
    resumed_ms = io.now() * 1000
    assert io.firmware.state == State.ARMED                      # COMMAND_TIMEOUT: bo vẫn ARMED, guard không bắt
    run_until_done(session, step=0.1)
    first = session.safety_events[0]
    assert first.code == "VEHICLE_STOPPED" and "COMMAND_TIMEOUT" in first.message
    assert session.state == SessionState.STOPPED
    assert not any(enable for t, enable, _, _ in received if t > resumed_ms)   # không chạy lại sau khi hết treo


def test_vehicle_io_command_rejected_stops_the_run(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    firmware = io.firmware
    firmware._handle_command = lambda msg, now: firmware._ack(msg, Result.BAD_FIELD)   # bo từ chối mọi COMMAND
    run_until_done(session, step=0.1)
    assert session.safety_events[0].code == "COMMAND_REJECTED"
    assert session.state == SessionState.STOPPED


def test_drive_mode_cannot_change_while_running(scenario, cfg):
    session = straight_session(scenario, cfg)
    session.set_vehicle_link(VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG))
    session.start_run()
    with pytest.raises(SessionError):
        session.set_vehicle_link(None)
    assert session.drive_mode == DriveMode.VEHICLE_IO


def test_close_while_running_vehicle_io_stops_then_disarms(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.05)
    assert session.state == SessionState.RUNNING and io.firmware.state == State.RUNNING
    before = len(received)
    session.close()                      # như đóng cửa sổ giữa lúc tự đỗ
    io.advance(0.05)                     # << hạn lệnh 0,15 s và link_timeout 0,5 s: không phải watchdog
    assert len(received) > before and received[-1][1] is False   # lệnh cuối bo nhận: enable=0
    assert io.firmware.state == State.DISARMED


def test_manual_after_vehicle_io_run_drops_old_link(scenario, cfg):
    session = straight_session(scenario, cfg)
    session.set_vehicle_link(VehicleLink.simulated(DriveMode.VEHICLE_IO, SIM_CFG))
    session.start_run()
    run_until_done(session)
    assert session.state == SessionState.COMPLETED and session.run_link is not None
    session.reset()
    session.start_manual()
    # Log hiện tại là của lần lái tay: không còn liên kết của lần chạy trước để xuất kèm.
    assert session.run_link is None and session.vehicle_link is not None
    session.stop_manual()
    session.start_run()                  # liên kết đang chọn không bị đóng: lần Bắt đầu đỗ tới vẫn dùng được
    assert session.run_link is session.vehicle_link and session.state == SessionState.RUNNING


# ---- bo thật theo thời gian thực: dùng cổng serial GIẢ -------------------------------------------------------------
def still_inputs(_t_ms: int) -> FirmwareInputs:
    """Ngõ vào của bo giả: có encoder và AS5600, xe đứng yên (xe không thật sự chạy trong các test đồng hồ)."""
    return FirmwareInputs(speed_valid=True, speed_mm_s=0, steer_valid=True, steer_mrad=0)


def test_realtime_link_session_clock_follows_io_clock_without_blocking_reads(scenario, cfg):
    """Xác định: ManualClock chỉ tiến khi test gọi loop.advance() (hoặc khi một lần đọc cổng rỗng phải chờ)."""
    session = straight_session(scenario, cfg)
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW, boot_id=0xB007), clock, inputs=still_inputs)
    io = SerialVehicleIO(loop, clock=clock, rng=random.Random(1))
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FixedPose(io, scenario.start))
    assert link.realtime
    session.set_vehicle_link(link)
    session.realtime_factor = 4.0                                # không có tác dụng với bo thời gian thực
    session.start_run()
    empty = [0]
    original_read = loop.read

    def read(n=1):
        if not loop.rx:
            empty[0] += 1                                        # đọc cổng rỗng = chờ timeout đọc của pyserial
        return original_read(n)

    loop.read = read
    sent0 = io.stats.commands_sent
    try:
        for _ in range(10):
            loop.advance(100)                                    # bo chạy 100 ms
            session.advance(0.016)                               # một nhịp giao diện: real_dt bị bỏ qua
            assert empty[0] == 0
            assert abs((io.now() - link._io_t0) - session.world.time) <= Session.PHYSICS_DT + 1e-9
        assert session.state == SessionState.RUNNING
        assert 45 <= io.stats.commands_sent - sent0 <= 55        # 50 Hz theo đồng hồ io
    finally:
        session.close()


class WallClockSerialPort:
    """Cổng serial GIẢ theo đồng hồ tường: đầu kia là `FirmwareModel` chạy nhịp 10 ms theo time.perf_counter();
    `read()` khi chưa có byte chờ tới `timeout` như pyserial (timeout=0,01 s của `SerialVehicleIO.open`)."""

    def __init__(self, firmware: FirmwareModel, timeout: float = 0.01, tick_ms: int = 10):
        self.firmware = firmware
        self.timeout = timeout
        self.tick_ms = tick_ms
        self.t0 = time.perf_counter()
        self.next_tick_ms = tick_ms
        self.rx = bytearray()
        self.reads = 0
        self.empty_reads = 0

    def now(self) -> float:
        return time.perf_counter() - self.t0

    def _run(self) -> None:
        now_ms = int(self.now() * 1000)
        while self.next_tick_ms <= now_ms:
            self.firmware.step(self.next_tick_ms, still_inputs(self.next_tick_ms))
            self.rx += self.firmware.take_tx()
            self.next_tick_ms += self.tick_ms

    @property
    def in_waiting(self) -> int:
        self._run()
        return len(self.rx)

    def write(self, data: bytes) -> int:
        self._run()
        self.firmware.receive(bytes(data), int(self.now() * 1000))
        self.rx += self.firmware.take_tx()
        return len(data)

    def read(self, n: int = 1) -> bytes:
        self.reads += 1
        self._run()
        if not self.rx:
            self.empty_reads += 1
            deadline = time.perf_counter() + self.timeout
            while not self.rx and time.perf_counter() < deadline:
                time.sleep(0.001)
                self._run()
        out = bytes(self.rx[:n])
        del self.rx[:n]
        return out

    def close(self) -> None:
        pass


def test_realtime_serial_link_does_not_block_the_ui_tick(scenario, cfg):
    """Thời gian thực (~1 s): nhịp giao diện 16 ms, cổng giả chờ 10 ms khi đọc rỗng."""
    session = straight_session(scenario, cfg)
    port = WallClockSerialPort(FirmwareModel(FAST_FW, boot_id=0xB007))
    io = SerialVehicleIO(port, clock=port.now, rng=random.Random(1))
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FixedPose(io, scenario.start))
    session.set_vehicle_link(link)
    session.start_run()
    try:
        empty0, sent0, io0 = port.empty_reads, io.stats.commands_sent, io.now()
        walls = []
        last = time.perf_counter()
        end = last + 1.0
        while time.perf_counter() < end:
            time.sleep(0.016)                                    # QTimer 16 ms
            now = time.perf_counter()
            real_dt = min(now - last, 0.1)                       # như MainWindow._on_tick
            last = now
            before = io.now() - link._io_t0
            session.advance(real_dt)
            after = io.now() - link._io_t0
            walls.append(time.perf_counter() - now)
            # Thời gian phiên = đồng hồ io lúc advance() tính, trễ tối đa một bước 5 ms.
            assert before - Session.PHYSICS_DT - 1e-6 <= session.world.time <= after + 1e-6
        assert session.state == SessionState.RUNNING
        assert port.empty_reads == empty0                        # vòng điều khiển không một lần đọc chờ
        assert sum(walls) / len(walls) < 0.012                   # trước khi sửa: ≈ 2 × real_dt
        rate = (io.stats.commands_sent - sent0) / (io.now() - io0)
        assert 45 <= rate <= 55                                  # 50 Hz theo thời gian thực
    finally:
        session.close()


def test_serial_default_clock_is_fine_grained():
    # Thời gian phiên đi theo io.now(): đồng hồ mặc định phải mịn hơn nhiều so với bước 5 ms. time.monotonic() trên
    # Windows chỉ đổi mỗi 15,625 ms (≈ 4 giá trị trong 50 ms); perf_counter cho hàng nghìn giá trị.
    io = SerialVehicleIO(FirmwareSerialLoopback(FirmwareModel(FAST_FW), ManualClock()))
    values = set()
    end = time.perf_counter() + 0.05
    while time.perf_counter() < end:
        values.add(io.now())
    assert len(values) > 50


# ---- OBSERVE: tính và ghi lệnh, không gửi --------------------------------------------------------------------------
def test_observe_logs_commands_and_never_enables_the_board(tmp_path):
    session = parking_session()
    io = sim_io(session.cfg, session.scenario.start)
    human = SimHumanDriver(io)
    received = record_commands(io)
    link = link_for(DriveMode.OBSERVE, io)
    session.set_vehicle_link(link)
    session.start_run()
    start_pose = io.truth.pose
    for _ in range(3000):
        session.advance(0.02)
        firmware = io.firmware
        assert firmware.state == State.DISARMED and not firmware.cmd_active and firmware.effort_permille == 0
        out = session.last_output
        if out is not None:
            human.set(out.target_speed, out.target_steer)        # người lái làm theo lệnh gợi ý
        if not session.simulating:
            break
    assert session.state == SessionState.COMPLETED, session.stop_reason
    assert io.truth.pose.distance_to(start_pose) > 0.3           # người lái đã chạy xe
    assert received == [] and io.stats.commands_sent == 0        # không một COMMAND nào, kể cả enable=0
    assert not io.firmware.has_cmd
    rows = link.command_rows
    assert len(rows) > 200 and all(r["sent"] == 0 for r in rows)
    assert max(abs(r["target_speed_mps"]) for r in rows) > 0.1   # lệnh thật sự được tính
    assert {"PRESET_STEER", "TRACK", "STOP_AT_CUSP"} <= {r["phase"] for r in rows}

    written = link.write_logs(tmp_path / "quan_sat")
    commands = read_csv(written["commands.csv"])
    telemetry = read_csv(written["telemetry.csv"])
    assert list(commands[0]) == COMMAND_FIELDS and len(commands) == len(rows)
    assert {r["mode"] for r in commands} == {"OBSERVE"} and {r["sent"] for r in commands} == {"0"}
    assert list(telemetry[0]) == TELEMETRY_FIELDS and len(telemetry) > 100
    during = [r for r in telemetry if float(r["t_session"]) >= 0]  # t_session < 0: khung nhận trước START (BOOT...)
    assert {r["state"] for r in during} == {"DISARMED"} and {r["cmd_active"] for r in during} == {"0"}
    assert {r["effort"] for r in during} == {"0.0"}
    assert any(abs(float(r["speed_mps"])) > 0.1 for r in telemetry)   # tốc độ đo khi người lái chạy
    assert read_csv(written["start_refusals.csv"]) == []           # tệp luôn có, lần này không có từ chối


def test_observe_disarms_a_board_found_armed(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    io.connect()
    io.wait_ready()
    io.arm()
    assert io.firmware.state == State.ARMED
    link = link_for(DriveMode.OBSERVE, io)
    session.set_vehicle_link(link)
    session.start_run()
    assert io.firmware.state == State.DISARMED
    assert any(r["code"] == "OBSERVE_DISARM" for r in link.event_rows)
    session.advance(0.5)
    # Một chương trình khác (hoặc lỗi) ARM bo và gửi lệnh chạy giữa lúc quan sát.
    io.arm()
    io.send(0.1, 0.0)
    requests = record_requests(io)                               # chỉ ghi từ sau ARM của "chương trình khác"
    run_until_done(session, step=0.05)
    assert session.state == SessionState.STOPPED
    assert session.safety_events[0].code == "OBSERVE_NOT_DISARMED"
    # Ngay lúc kết thúc, trước khi watchdog liên lạc 500 ms của bo kịp tác động: chính lớp nối đã DISARM.
    assert requests == [Action.DISARM]
    assert io.firmware.state == State.DISARMED and io.firmware.stop_reason == StopReason.HOST_DISARM
    io.advance(0.5)
    assert io.firmware.state == State.DISARMED and io.firmware.effort_permille == 0


def test_observe_stop_ends_without_waiting_for_the_driver(scenario, cfg):
    session = straight_session(scenario, cfg)
    link = VehicleLink.simulated(DriveMode.OBSERVE, SIM_CFG)
    session.set_vehicle_link(link)
    session.start_run()
    received = record_commands(link.io)                          # io do begin_run() tạo lúc START
    link.human.set(0.1, 0.0)                                     # người lái vẫn chạy
    session.advance(1.0)
    # Bước STOPPING đầu tiên phải rơi vào nhịp điều khiển để command_stop() thật sự chạy
    # (advance(1.0) có thể chỉ cho 199 bước vì sai số dấu phẩy động của bộ tích lũy).
    for _ in range(Session.CONTROL_EVERY):
        if session.world.step_count % Session.CONTROL_EVERY == 0:
            break
        session.advance(Session.PHYSICS_DT)
    assert session.world.step_count % Session.CONTROL_EVERY == 0
    session.request_stop()
    session.advance(0.05)
    assert session.state == SessionState.STOPPED and link.io.truth.speed > 0.05
    stops = [r for r in link.command_rows if r["kind"] == "STOP"]
    assert stops and all(r["sent"] == 0 for r in stops)         # nhánh dừng đã chạy, ghi log, không gửi
    assert received == [] and link.io.stats.commands_sent == 0   # không COMMAND nào, kể cả enable=0


# ---- giao diện ------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_window_drive_mode_selector(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QFileDialog
    from autopark.ui.app import DEFAULT_SCENARIO, build_window

    window = build_window(DEFAULT_SCENARIO)
    combo = window.combo_drive
    assert combo.count() == 3 and combo.currentData() == DriveMode.SIM.value
    assert window.session.drive_mode == DriveMode.SIM
    assert "KHÔNG gửi" in combo.itemText(combo.findData(DriveMode.OBSERVE.value))

    combo.setCurrentIndex(combo.findData(DriveMode.OBSERVE.value))
    assert window.session.drive_mode == DriveMode.OBSERVE and "DISARMED" in window.lbl_drive_hint.text()
    assert window.plan(sync=True).ok
    window.run()
    assert window.session.state == SessionState.RUNNING
    window._refresh_mode_widgets()
    assert not combo.isEnabled()                                 # khóa trong lúc chạy
    link = window.session.run_link
    for _ in range(5):
        window._handle_key(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier))
    assert link.human.speed == pytest.approx(5 * window.session.speed_step)
    before = window.session.world.state.pose
    window.advance_by(1.0)
    assert window.session.world.state.pose.distance_to(before) > 0.02   # người lái (phím) chạy xe mô phỏng
    assert link.io.stats.commands_sent == 0 and link.io.firmware.state == State.DISARMED
    assert "không gửi" in window.lbl_step.text()
    out_csv = tmp_path / "log.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out_csv), "CSV (*.csv)"))
    # T9: _export_log xuất cả gói phát lại của lần chạy qua VehicleIO; không gọi PowerShell trong test.
    monkeypatch.setattr(run_store, "environment", lambda: {"test": True})
    window._handle_key(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    window.advance_by(0.05)
    assert window.session.state == SessionState.STOPPED
    window._export_log()
    assert (tmp_path / "log_vehicle_io" / "commands.csv").exists()
    assert (tmp_path / "log_vehicle_io" / "start_refusals.csv").exists()
    window.reset()
    window._refresh_mode_widgets()
    assert combo.isEnabled()

    combo.setCurrentIndex(combo.findData(DriveMode.VEHICLE_IO.value))
    assert window.session.drive_mode == DriveMode.VEHICLE_IO
    if window.session.state != SessionState.READY:
        assert window.plan(sync=True).ok
    window.run()
    for _ in range(200):
        window.advance_by(0.5)
        if not window.session.simulating:
            break
    assert window.session.state == SessionState.COMPLETED
    assert window.session.run_link.io.stats.commands_sent > 100

    window.reset()
    combo.setCurrentIndex(combo.findData(DriveMode.SIM.value))
    assert window.session.vehicle_link is None
    window.close()


def test_window_manual_export_after_vehicle_io_run_has_no_old_link_logs(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from autopark.ui.app import DEFAULT_SCENARIO, build_window

    window = build_window(DEFAULT_SCENARIO)
    combo = window.combo_drive
    combo.setCurrentIndex(combo.findData(DriveMode.VEHICLE_IO.value))
    assert window.plan(sync=True).ok
    window.run()
    io = window.session.run_link.io
    for _ in range(100):
        window.advance_by(0.1)
        if io.truth.speed > 0.05:
            break
    window.stop()
    for _ in range(100):
        window.advance_by(0.1)
        if not window.session.simulating:
            break
    old_link = window.session.run_link
    assert window.session.state == SessionState.STOPPED and old_link is not None
    window.reset()
    window._start_manual()
    assert window.session.state == SessionState.MANUAL and window.session.run_link is None
    window.advance_by(1.0)
    assert len(window.session.log) > 0
    out = tmp_path / "m.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), "CSV (*.csv)"))
    window._export_log()
    assert out.exists() and not (tmp_path / "m_vehicle_io").exists()   # log lái tay không kèm log VehicleIO cũ
    # Lớp phòng thủ của giao diện: kể cả khi phiên còn giữ liên kết cũ, log không có snapshot VehicleIO thì không kèm.
    window.session.run_link = old_link
    out2 = tmp_path / "m2.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out2), "CSV (*.csv)"))
    window._export_log()
    assert out2.exists() and not (tmp_path / "m2_vehicle_io").exists()
    window.session.run_link = None
    window.reset()
    window.close()


def test_window_close_while_running_vehicle_io_disarms(qapp):
    from autopark.ui.app import DEFAULT_SCENARIO, build_window

    window = build_window(DEFAULT_SCENARIO)
    combo = window.combo_drive
    combo.setCurrentIndex(combo.findData(DriveMode.VEHICLE_IO.value))
    assert window.plan(sync=True).ok
    window.run()
    io = window.session.run_link.io
    received = record_commands(io)
    for _ in range(100):
        window.advance_by(0.1)
        if io.truth.speed > 0.05:
            break
    assert window.session.state == SessionState.RUNNING and io.firmware.state == State.RUNNING
    before = len(received)
    window.close()                       # closeEvent -> Session.close() -> VehicleLink.close()
    io.advance(0.05)
    assert len(received) > before and received[-1][1] is False
    assert io.firmware.state == State.DISARMED


# ---- bổ sung (tối 24/09/2026): mất số đo giữa lần chạy, thiếu AS5600 lúc khởi động, vòng điều khiển treo -------------
# Vẫn chỉ mô phỏng (SimVehicleIO + FirmwareModel), không mở cổng nào.
def drop_sensor(io: SimVehicleIO, **flags) -> None:
    """Giữa lần chạy, bo mô phỏng thôi báo một số đo (encoder/AS5600 hỏng): cờ hợp lệ = 0, số = 0."""
    io.config = replace(io.config, sensors=replace(io.config.sensors, **flags))


def test_measured_speed_lost_mid_run_stops_and_standstill_is_not_assumed(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    drop_sensor(io, speed_available=False)
    run_until_done(session, step=0.1)
    link = session.run_link
    codes = [e.code for e in session.safety_events]
    assert codes[0] == "NO_MEASURED_STATE"
    # Không có tốc độ đo thì không xác nhận được xe đã dừng: FAULT, không phải STOPPED.
    assert session.state == SessionState.FAULT and "STOP_NOT_CONFIRMED" in codes
    assert session.path_invalidated and not session.trajectory.valid
    first_stop = next(i for i, r in enumerate(link.command_rows) if r["kind"] == "STOP")
    assert all(r["kind"] == "STOP" for r in link.command_rows[first_stop:])
    stop_ms = link.command_rows[first_stop]["t_io"] * 1000
    assert not any(enable for t, enable, _, _ in received if t > stop_ms + 15)   # 4 ms đường truyền + một nhịp 10 ms
    assert io.truth.speed == 0.0 and io.firmware.state == State.DISARMED


def test_measured_steer_lost_mid_run_stops(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    drop_sensor(io, steer_available=False)
    run_until_done(session, step=0.1)
    link = session.run_link
    assert session.safety_events[0].code == "NO_MEASURED_STATE"
    assert session.state == SessionState.STOPPED                 # tốc độ vẫn đo được: xác nhận được đã đứng yên
    stop_ms = next(r["t_io"] for r in link.command_rows if r["kind"] == "STOP") * 1000
    assert not any(enable for t, enable, _, _ in received if t > stop_ms + 15)
    assert io.truth.speed == 0.0 and io.firmware.state == State.DISARMED


@pytest.mark.parametrize("mode", [DriveMode.VEHICLE_IO, DriveMode.OBSERVE])
def test_start_refused_without_measured_steer(scenario, cfg, mode):
    session = straight_session(scenario, cfg)
    io = SimVehicleIO(cfg, replace(SIM_CFG, sensors=SimSensorConfig(steer_available=False)),
                      start=VehicleState(scenario.start, 0.0, 0.0, 0.0))
    requests = record_requests(io)
    session.set_vehicle_link(link_for(mode, io))
    assert_refused(session, io, "góc lái")
    assert io.stats.commands_sent == 0
    assert Action.ARM not in requests                            # bị từ chối trước khi ARM (và trước DISARM của quan sát)
    link = session.vehicle_link
    assert [r["code"] for r in link.start_refusals] == ["START_CHECK"]
    assert "AS5600" in link.start_refusals[0]["message"]


def heartbeat_only(io: SimVehicleIO, seconds: float, period_s: float = 0.1) -> int:
    """Như luồng `Heartbeat` khi vòng điều khiển của ứng dụng treo: chỉ `service()` (đọc telemetry, KHÔNG lấy hàng
    đợi của `poll()`) và PING khi laptop im quá `period_s`; không gửi lệnh chuyển động nào. Trả số PING."""
    end = io.now() + seconds
    pings = 0
    while io.now() < end - 1e-9:
        io.service()
        if io.connected and io.now() - io.last_tx_time >= period_s:
            io.ping(wait=False)
            pings += 1
    return pings


# Pha 0 từng là KHOẢNG TRỐNG AN TOÀN (tìm thấy tối 24/09/2026, chỉ trên mô phỏng): sau khi vòng điều khiển treo lâu
# hơn hạn lệnh mà Heartbeat vẫn PING, bo ở ARMED (COMMAND_TIMEOUT); nếu bước đầu tiên sau khi hết treo là nhịp điều
# khiển, Session gửi MỘT COMMAND enable=1 trước khi lấy sự kiện VEHICLE_STOPPED (VehicleLink chỉ gom sự kiện trong
# pump(), chạy SAU nhịp điều khiển), nên bo ARMED → RUNNING thêm một lần. Đã sửa cùng tối bằng VehicleLink.refresh()
# gọi đầu mỗi bước, TRƯỚC nhịp điều khiển; pha 0 nay là test thường (trước đó xfail strict).
@pytest.mark.parametrize("phase", [0, 1, 2, 3])
def test_command_timeout_while_heartbeat_keeps_link_stops_and_never_resumes(scenario, cfg, phase):
    """Vòng điều khiển treo 1 s (> hạn lệnh 0,15 s, > watchdog liên lạc 0,5 s) trong khi Heartbeat vẫn PING và đọc
    telemetry: bo KHÔNG bị watchdog DISARM, chỉ về ARMED (COMMAND_TIMEOUT), telemetry luôn mới. Lần chạy phải dừng và
    không được chạy lại bằng COMMAND kế tiếp. `phase` = số bước 5 ms từ nhịp điều khiển gần nhất tới lúc treo, để bước
    đầu tiên sau khi hết treo rơi vào nhịp điều khiển (phase 0) hoặc không (1–3)."""
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    requests = record_requests(io)                               # sau ARM của START
    advance_until(session, lambda: io.truth.speed > 0.1)
    while session.world.step_count % Session.CONTROL_EVERY != phase:
        session.advance(Session.PHYSICS_DT)
    assert session.state == SessionState.RUNNING and io.firmware.state == State.RUNNING
    hang_ms = io.now() * 1000
    pings = heartbeat_only(io, 1.0)
    resumed_ms = io.now() * 1000
    assert pings >= 8 and requests.count(Action.PING) == pings
    assert io.firmware.state == State.ARMED and io.firmware.stop_reason == StopReason.COMMAND_TIMEOUT
    assert io.telemetry_fresh() and not io.rearm_required       # không có TELEMETRY_STALE: chốt phía laptop không giúp
    assert not any(t > hang_ms for t, _, _, _ in received)       # đúng là không lệnh nào trong lúc treo
    run_until_done(session, step=0.1)
    first = session.safety_events[0]
    assert first.code == "VEHICLE_STOPPED" and "COMMAND_TIMEOUT" in first.message
    assert session.state == SessionState.STOPPED and session.path_invalidated
    assert io.truth.speed == 0.0 and io.firmware.state == State.DISARMED
    assert Action.ARM not in requests                            # không ai ARM lại sau START
    # Điều kiện chính (để cuối): sau khi hết treo, không một COMMAND enable=1 nào tới bo.
    late = [(t, speed) for t, enable, speed, _ in received if enable and t > resumed_ms]
    assert late == [], f"lệnh enable tới bo sau khi hết treo: {late}"


@pytest.mark.parametrize("phase", [0, 1, 2, 3])
@pytest.mark.parametrize("hang_ms", [300, 1000])                  # giữa hạn lệnh và watchdog 0,5 s; và quá watchdog
def test_realtime_hang_without_heartbeat_never_resumes(scenario, cfg, hang_ms, phase):
    """Cổng serial GIẢ, `ManualClock`: giao diện treo mà KHÔNG có luồng nào đọc cổng hay PING (phiên hiện không dùng
    `Heartbeat`). Hết treo, ở mọi pha của nhịp điều khiển: lần chạy dừng và không COMMAND enable=1 nào tới bo."""
    session = straight_session(scenario, cfg)
    clock = ManualClock()
    firmware = FirmwareModel(FAST_FW, boot_id=0xB007)
    loop = FirmwareSerialLoopback(firmware, clock, inputs=still_inputs)
    io = SerialVehicleIO(loop, clock=clock, rng=random.Random(1))
    session.set_vehicle_link(VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FixedPose(io, scenario.start)))
    session.start_run()
    try:
        for _ in range(6):
            loop.advance(50)
            session.advance(0.016)
        while session.world.step_count % Session.CONTROL_EVERY != phase:
            loop.advance(5)
            session.advance(0.0)
        assert session.state == SessionState.RUNNING and firmware.state == State.RUNNING
        seen = []
        original = firmware._handle_command

        def handle(msg, now):
            seen.append((now, bool(msg.enable)))
            original(msg, now)

        firmware._handle_command = handle
        loop.advance(hang_ms)                                     # bo chạy tiếp; laptop không đọc, không gửi gì
        assert firmware.state == (State.ARMED if hang_ms < 500 else State.DISARMED)
        resumed_ms = clock.t_ms
        for _ in range(300):
            loop.advance(16)
            session.advance(0.016)
            if not session.simulating:
                break
        assert session.state == SessionState.STOPPED
        assert session.safety_events[0].code in ("STALE_TELEMETRY", "VEHICLE_STOPPED", "VEHICLE_NOT_ARMED")
        assert not any(enable for t, enable in seen if t >= resumed_ms)
        assert firmware.state == State.DISARMED
    finally:
        session.close()


# Pha 0 cùng khoảng trống ở trên (io.advance(0,25) vẫn đọc telemetry lúc treo, như Heartbeat); sửa tối 24/09/2026.
@pytest.mark.parametrize("phase", [0, 1, 2, 3])
def test_vehicle_io_command_timeout_after_freeze_by_phase(scenario, cfg, phase):
    """Như `test_vehicle_io_command_timeout_after_freeze_never_resumes` (treo 0,25 s bằng `SimVehicleIO.advance`, tức
    laptop vẫn đọc telemetry lúc treo; test gốc tình cờ rơi vào pha 3), nhưng ép pha của nhịp điều khiển lúc treo."""
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    while session.world.step_count % Session.CONTROL_EVERY != phase:
        session.advance(Session.PHYSICS_DT)
    assert session.state == SessionState.RUNNING and io.firmware.state == State.RUNNING
    io.advance(0.25)       # laptop treo 0,25 s: > thời hạn lệnh 0,15 s, < link_timeout 0,5 s
    resumed_ms = io.now() * 1000
    assert io.firmware.state == State.ARMED and io.firmware.stop_reason == StopReason.COMMAND_TIMEOUT
    run_until_done(session, step=0.1)
    first = session.safety_events[0]
    assert first.code == "VEHICLE_STOPPED" and "COMMAND_TIMEOUT" in first.message
    assert session.state == SessionState.STOPPED and io.firmware.state == State.DISARMED
    # Điều kiện chính (để cuối): sau khi hết treo, không một COMMAND enable=1 nào tới bo.
    late = [(t, speed) for t, enable, speed, _ in received if enable and t > resumed_ms]
    assert late == [], f"lệnh enable tới bo sau khi hết treo: {late}"


# Hai test dưới từng GHI LẠI hành vi của khoảng trống ở pha 0 (một enable=1 rồi enable=0 sau khi hết treo; với bo chạy
# thêm 10/20/40 ms trước lệnh dừng, effort lên 107/115/130 ‰ trên mô hình bo). Sau bản sửa tối 24/09/2026 chúng ghim
# hành vi đúng: không enable=1 nào, effort 0 ở mọi khoảng trễ.
def fw_effort_log(firmware: FirmwareModel) -> list[tuple[int, str, int]]:
    """Mọi `step()` của bo: (ms của bo, trạng thái sau bước, effort ‰)."""
    seen = []
    original = firmware.step

    def step(now_ms, inputs=None):
        out = original(now_ms, inputs)
        seen.append((now_ms, firmware.state.name, firmware.effort_permille))
        return out

    firmware.step = step
    return seen


def test_resume_after_hang_sends_no_enable_to_the_sim_board(scenario, cfg):
    """Bo mô phỏng (`SimVehicleIO`), pha 0, treo 1 s với vòng giống `Heartbeat`: sau khi hết treo, lệnh đầu tiên tới bo
    là enable=0, không có enable=1 nào, effort luôn 0. (Trước bản sửa: enable=1 và enable=0 tới cùng một mili giây vì
    `SimVehicleIO` đã đi trước thời gian phiên ≈ 1 s.)"""
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    while session.world.step_count % Session.CONTROL_EVERY != 0:
        session.advance(Session.PHYSICS_DT)
    heartbeat_only(io, 1.0)
    resumed_ms = io.now() * 1000
    ahead_s = session.run_link.session_time_now() - session.world.time    # đồng hồ io đi trước thời gian phiên
    steps = fw_effort_log(io.firmware)
    run_until_done(session, step=0.1)
    after = [(t, enable) for t, enable, _, _ in received if t > resumed_ms]
    assert after and after[0][1] is False and not any(enable for _, enable in after)
    assert max(abs(effort) for _, _, effort in steps) == 0
    assert 0.9 < ahead_s < 1.1


@pytest.mark.parametrize("gap_ms", [0, 10, 20, 40])
def test_resume_after_hang_keeps_effort_zero_whatever_the_gap_before_the_stop(scenario, cfg, gap_ms):
    """Cổng serial GIẢ, `ManualClock`, pha 0, treo 1 s trong khi một vòng đọc telemetry và PING (như `Heartbeat`). Cho
    bo chạy thêm `gap_ms` trước lệnh dừng đầu tiên (như thời gian tính + trễ USB trên máy thật). Sau bản sửa: không
    enable=1 nào tới bo, effort 0 ở mọi khoảng trễ. Trước bản sửa: một enable=1 tới trước và effort lên 0/107/115/130 ‰
    (mô hình bo hiện tại với đầu vào đứng yên, không phải số đo)."""
    session = straight_session(scenario, cfg)
    clock = ManualClock()
    firmware = FirmwareModel(FAST_FW, boot_id=0xB007)
    loop = FirmwareSerialLoopback(firmware, clock, inputs=still_inputs)
    io = SerialVehicleIO(loop, clock=clock, rng=random.Random(1))
    session.set_vehicle_link(VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FixedPose(io, scenario.start)))
    session.start_run()
    try:
        for _ in range(6):
            loop.advance(50)
            session.advance(0.016)
        while session.world.step_count % Session.CONTROL_EVERY != 0:
            loop.advance(5)
            session.advance(0.0)
        assert session.state == SessionState.RUNNING and firmware.state == State.RUNNING
        end = clock.t_ms + 1000
        while clock.t_ms < end:                                   # vòng điều khiển treo; vòng đọc vẫn chạy
            loop.advance(10)
            io.service(block=False)
            if io.connected and io.now() - io.last_tx_time >= 0.1:
                io.ping(wait=False)
        assert firmware.state == State.ARMED and firmware.stop_reason == StopReason.COMMAND_TIMEOUT
        resumed_ms = clock.t_ms
        seen = []
        original_handle = firmware._handle_command

        def handle(msg, now):
            seen.append((now, bool(msg.enable)))
            original_handle(msg, now)

        firmware._handle_command = handle
        steps = fw_effort_log(firmware)
        original_stop = io.stop
        delayed = []

        def stop(*args, **kwargs):
            if not delayed:
                delayed.append(True)
                loop.advance(gap_ms)                              # bo chạy thêm trước lệnh dừng đầu tiên
            return original_stop(*args, **kwargs)

        io.stop = stop
        for _ in range(300):
            loop.advance(16)
            session.advance(0.016)
            if not session.simulating:
                break
        assert session.state == SessionState.STOPPED and firmware.state == State.DISARMED
        after = [c for c in seen if c[0] >= resumed_ms]
        assert after and after[0][1] is False and not any(enable for _, enable in after)
        assert delayed                                            # lệnh dừng đầu tiên đúng là đi sau gap_ms
        assert max(abs(effort) for t, _, effort in steps if t >= resumed_ms) == 0
    finally:
        session.close()


def test_command_refuses_enable_while_a_stop_event_is_pending(scenario, cfg):
    """Lớp chặn thứ hai (tối 24/09/2026): còn sự kiện dừng chưa được Session lấy thì `command()` không gửi enable."""
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    session.set_vehicle_link(link_for(DriveMode.VEHICLE_IO, io))
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    link = session.run_link
    sent = io.stats.commands_sent
    t = session.world.time
    link._pending.append(link._link_event(t, "TEST_STOP", "sự kiện dừng giả, chưa được Session lấy"))
    problem = link.command(t, session.last_output, link.estimate(t, session.world.state))
    assert problem is not None and problem.code == "HALTED"
    assert io.stats.commands_sent == sent and link.command_rows[-1]["sent"] == 0
    session.close()
