"""Tiêm lỗi có kiểm soát (T6): autopark/safety/fault_injection.py, autopark/evaluation/fault_drill.py và hai móc nhỏ
(`SimVehicleIO.pause_host/resume_host`, `VehicleLink` bóc lớp bọc khi kiểm luật SimTruthPose). Thêm 02/10/2026.

Mọi test chạy trên MÔ PHỎNG: bo mô phỏng `SimVehicleIO` + `FirmwareModel`, cổng serial GIẢ (`FirmwareSerialLoopback` với
`ManualClock`; `WallClockSerialPort` theo đồng hồ tường), camera giả (`tests.rig_fakes.FakeCamera`, camera giả của công
cụ), bản ghi phát lại dựng tức thì bằng `RigRecorder` với đồng hồ giả, và `cv2.VideoCapture` giả. Không mở cổng COM,
LiDAR hay camera nào; `git` của repo cũng không chạy (`no_git`). Các test camera và đồng hồ tường chạy luồng thật
(≈ 12 s tổng), giới hạn để rộng vì máy có thể bận.

Sửa 02/10/2026 sau khi gộp T13, T9, T15: cột faults.csv theo EVENT_FIELDS mới (t_perf, call), tệp của lần chạy phiên
lấy từ `VehicleLink.write_logs`, STALL trên bản ghi phát lại không trả dồn khung cũ.
"""
import csv
import json
import math
import random
import threading
import time

import cv2
import numpy as np
import pytest

from autopark.application.session import Session, SessionError, SessionState
from autopark.application.vehicle_link import EVENT_FIELDS, DriveMode, NoPoseSource, SimTruthPose, VehicleLink
from autopark.evaluation import fault_drill
from autopark.evaluation.fault_drill import SessionDrillResult, board_transitions, collect_session_result, judge
from autopark.rig.core import RigConfig
from autopark.rig.recording import RigRecorder
from autopark.safety.fault_injection import (FAULT_FIELDS, REPEAT_MESSAGE, FaultLog, FaultRecord, FreezableFrameSource,
                                             FreezablePoseSource, FreezeMode, FreezeSwitch, PoseFault, RepeatingCapture,
                                             freezable_open_source, hang_control_loop)
from autopark.transport.firmware_model import FirmwareModel
from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock
from autopark.transport.protocol import Action, State, StopReason
from autopark.transport.vehicle_io import SerialVehicleIO, SimVehicleIO
from autopark.video.multicam import CameraSpec, CameraWorker, MultiCameraManager
from autopark.video.sources import FrameReadError, UsbCameraSource, _frame
from tests.rig_fakes import FakeCamera
from tests.test_session_vehicle import (FAST_FW, SIM_CFG, FixedPose, WallClockSerialPort, advance_until, read_csv,
                                        record_commands, record_requests, run_until_done, sim_io, still_inputs,
                                        straight_session)


# ---- log tiêm lỗi ----------------------------------------------------------------------------------------------------
def test_fault_log_rows_share_the_events_csv_columns(tmp_path):
    assert FAULT_FIELDS == EVENT_FIELDS[:2] + ["t_rig"] + EVENT_FIELDS[2:]          # nối/ghép được với events.csv
    empty = FaultLog().write_csv(tmp_path / "trong.csv")
    assert empty.read_text(encoding="utf-8").splitlines() == [",".join(FAULT_FIELDS)]   # luôn có tiêu đề
    log = FaultLog()
    t = time.perf_counter()
    log.add(FaultRecord("FAULT_POSE_HOLD", "fault_injected", "giữ mẫu cũ", t_io=2.43, t_session=1.234567))
    log.add(FaultRecord("FAULT_END", "fault_cleared", "hết", t_rig=5.5))
    rows = read_csv(log.write_csv(tmp_path / "faults.csv"))
    assert list(rows[0]) == FAULT_FIELDS
    assert (rows[0]["t_session"], rows[0]["t_io"], rows[0]["t_rig"]) == ("1.2346", "2.43", "")
    assert (rows[1]["t_session"], rows[1]["t_io"], rows[1]["t_rig"]) == ("", "", "5.5")
    # t_perf (như events.csv, T13): perf_counter() thô lúc tạo bản ghi, ở MỌI dòng; call (T9): luôn trống
    assert all(t <= float(r["t_perf"]) <= time.perf_counter() for r in rows) and {r["call"] for r in rows} == {""}
    assert {r["source"] for r in rows} == {"fault_injection"} and {r["action"] for r in rows} == {"LOG"}
    copy = log.records
    copy.clear()
    assert len(log.records) == 2                                                       # `records` là bản sao


# ---- camera: REPEAT, STALL -------------------------------------------------------------------------------------------
class NoiseCapture:
    """cv2.VideoCapture giả: mỗi lần đọc một ảnh nhiễu MỚI 64×48 (bộ dò khung cắt/xé không bắt); đếm số lần đọc."""

    def __init__(self):
        self.reads = 0
        self.rng = np.random.default_rng(7)
        self.props = {cv2.CAP_PROP_FRAME_WIDTH: 64, cv2.CAP_PROP_FRAME_HEIGHT: 48}

    def isOpened(self):
        return True

    def get(self, prop):
        return self.props.get(prop, 0.0)

    def set(self, prop, value):
        return True

    def read(self):
        self.reads += 1
        return True, self.rng.integers(0, 256, (48, 64, 3), dtype=np.uint8)

    def release(self):
        pass


def test_repeat_on_a_usb_camera_is_caught_by_its_own_duplicate_check(monkeypatch):
    capture = NoiseCapture()
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args: capture)
    usb = UsbCameraSource(0, width=64, height=48, source_id="cam_p3", clock=lambda: 1.0)
    log = FaultLog()
    switch = FreezeSwitch("cam_p3", log=log)
    source = FreezableFrameSource(usb, switch)
    FreezableFrameSource(usb, switch)                                   # bọc lần hai không lồng RepeatingCapture
    assert isinstance(usb.capture, RepeatingCapture) and usb.capture.capture is capture
    assert source.source_id == "cam_p3" and source.mode()["width"] == 64           # thuộc tính khác đi thẳng tới nguồn
    first = source.read()
    switch.freeze(FreezeMode.REPEAT)
    for _ in range(3):
        with pytest.raises(FrameReadError) as info:
            source.read()
        assert str(info.value) == "cam_p3: driver returned the previous frame again"    # chữ của CHÍNH nguồn USB
        assert "tiêm lỗi" not in str(info.value)
    assert usb.duplicates == 3 and capture.reads == 4                   # driver vẫn được đọc mỗi lần (giữ nhịp thật)
    switch.thaw()
    again = source.read()
    assert capture.reads == 5 and usb.duplicates == 3 and not np.array_equal(again.image, first.image)
    rows = [r.row() for r in log.records]
    assert [r["code"] for r in rows] == ["FAULT_CAMERA_REPEAT", "FAULT_END"]
    assert all(r["t_rig"] != "" and r["t_io"] == "" for r in rows)


def test_repeat_on_other_sources_is_counted_as_a_duplicate_by_the_camera_worker():
    assert "previous frame" in REPEAT_MESSAGE                           # chữ CameraWorker._count_error đếm là khung cũ
    spec = CameraSpec(port=2, index=1)
    inner = FakeCamera(spec, period=0.0)
    assert not hasattr(inner, "source_id")
    switch = FreezeSwitch("cam_p2")
    source = FreezableFrameSource(inner, switch)
    assert source.source_id == "cam_p2"                                 # nguồn không có source_id: tên công tắc
    assert source.read() is not None and inner.n == 1
    switch.freeze("repeat")
    with pytest.raises(FrameReadError) as info:
        source.read()
    assert inner.n == 2                                                 # nguồn bên trong vẫn được đọc (giữ nhịp)
    message = str(info.value)
    assert message == f"cam_p2: {REPEAT_MESSAGE}" and info.value.t is not None
    worker = CameraWorker(spec, lambda s: source, ring=3)
    arrivals = list(worker.arrivals)
    with worker.lock:
        worker._count_error(message, info.value.t)
    assert worker.stats.duplicates == 1 and worker.stats.read_failures == 0 and list(worker.arrivals) == arrivals
    switch.release()
    assert source.read() is not None


class InstantSource:
    source_id = "cam_p1"

    def __init__(self):
        self.n = 0

    def read(self):
        self.n += 1
        return _frame(self.source_id, time.perf_counter(), f"giả#{self.n}", np.full((4, 4, 3), self.n % 256, np.uint8))

    def close(self):
        pass


def read_in_thread(source):
    box = {}
    thread = threading.Thread(target=lambda: box.setdefault("frame", source.read()), daemon=True)
    thread.start()
    return thread, box


def test_stall_ends_on_thaw_release_or_the_safety_cap():
    log = FaultLog()
    switch = FreezeSwitch("cam_p1", log=log)
    source = FreezableFrameSource(InstantSource(), switch)
    switch.freeze()                                                     # mặc định STALL
    thread, box = read_in_thread(source)
    thread.join(0.2)
    assert thread.is_alive() and "frame" not in box and source.inner.n == 0      # không có lần tới nào
    switch.thaw()
    thread.join(1.0)
    assert not thread.is_alive() and box["frame"] is not None
    switch.freeze(FreezeMode.STALL)
    thread, box = read_in_thread(source)
    thread.join(0.1)
    assert thread.is_alive()
    t = time.perf_counter()
    switch.release()
    thread.join(0.5)
    assert not thread.is_alive() and box["frame"] is not None and time.perf_counter() - t < 0.5
    with pytest.raises(RuntimeError, match="đã nhả"):
        switch.freeze()
    assert switch.released and switch.mode is None
    capped = FreezeSwitch("cam_p1", log=log, max_stall_s=0.05)
    source = FreezableFrameSource(InstantSource(), capped)
    t = time.perf_counter()
    capped.freeze()
    assert source.read() is not None
    assert time.perf_counter() - t >= 0.05 and capped.mode is None
    last = log.records[-1].row()
    assert last["code"] == "FAULT_END" and "tự hết" in last["message"] and last["t_rig"] != ""


class ScheduledSource:
    """Như `ReplayCameraSource`: mỗi lần đọc trả mục kế tiếp của lịch (khung, hay lỗi khung cắt) với stamp = lịch và
    không chờ khi lịch đã qua — nên không mất mục nào khi không ai đọc."""

    source_id = "cam_p2"

    def __init__(self, items):
        self.items, self.reads = list(items), 0

    def read(self):
        t, kind = self.items[self.reads]
        self.reads += 1
        if kind == "lỗi":
            raise FrameReadError(f"{self.source_id}: truncated frame (giả)", t)
        return _frame(self.source_id, t, f"lịch#{self.reads}", np.full((4, 4, 3), self.reads, np.uint8))

    def close(self):
        pass


def test_items_scheduled_during_a_stall_are_dropped_after_the_thaw_not_delivered_late():
    now = [10.0]
    switch = FreezeSwitch("cam_p2", clock=lambda: now[0], log=FaultLog())
    inner = ScheduledSource([(9.97, "khung"), (10.03, "khung"), (10.2, "lỗi"), (10.47, "khung"), (10.53, "khung"),
                             (10.56, "lỗi"), (10.59, "khung")])
    source = FreezableFrameSource(inner, switch)
    switch.freeze()                                                     # STALL từ t = 10,0
    now[0] = 10.5
    assert switch.thaw().t_rig == 10.5
    assert source.read().meta.stamp.t == 9.97                           # trước đợt STALL: trả như thường
    assert source.read().meta.stamp.t == 10.53                          # 10,03; 10,2 (lỗi); 10,47 lẽ ra ra lúc STALL
    assert switch.skipped_after_stall == 3 and inner.reads == 5
    with pytest.raises(FrameReadError, match="truncated"):              # lỗi sau đợt STALL vẫn ra
        source.read()
    assert source.read().meta.stamp.t == 10.59 and switch.skipped_after_stall == 3
    switch.freeze(FreezeMode.REPEAT)                                    # REPEAT không đổi đợt STALL đã nhớ
    now[0] = 11.0
    switch.thaw()
    assert switch.drop_if_backlog(10.4) and not switch.drop_if_backlog(10.7) and not switch.drop_if_backlog(None)


@pytest.mark.parametrize("mode", [FreezeMode.STALL, FreezeMode.REPEAT])
def test_frozen_camera_is_stale_and_missing_after_half_a_second_and_the_other_keeps_its_rate(mode):
    """Hai FakeCamera 0,03 s, luồng thật, ghép bộ mỗi 5 ms với quy tắc của `RigConfig` (như `Rig._set_loop`); cổng 2
    đóng băng 0,8 s."""
    cfg = RigConfig()
    switch = FreezeSwitch("cam_p2", max_stall_s=5.0)
    specs = [CameraSpec(port=1, index=0), CameraSpec(port=2, index=1)]
    cams = MultiCameraManager(specs, ring=3, open_source=freezable_open_source(
        lambda spec: FakeCamera(spec, period=0.03), {2: switch}))
    sets, stale = [], []

    def poll(seconds):
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            fs = cams.latest_set(cfg.max_skew_s, max_wait_s=cfg.max_wait_s)
            if fs is not None:
                sets.append((fs.t_built, set(fs.frames), set(fs.missing)))
            row = next(c for c in cams.camera_stats() if c["port"] == 2)
            stale.append((time.perf_counter(), row["stale"]))
            time.sleep(0.005)

    def stats2():
        return next(c for c in cams.camera_stats() if c["port"] == 2)

    try:
        cams.start()
        poll(0.6)
        before = stats2()
        t_freeze = switch.freeze(mode).t_rig
        poll(0.8)
        t_thaw = switch.thaw().t_rig
        after = stats2()
        poll(0.3)
    finally:
        switch.release()                                                # TRƯỚC khi dừng luồng camera
        alive = cams.stop()
    assert alive == []
    stale_at = next((t - t_freeze for t, s in stale if t >= t_freeze and s), None)
    missing_at = next((t - t_freeze for t, _, missing in sets if t >= t_freeze and 2 in missing), None)
    assert stale_at is not None and 0.45 <= stale_at <= 0.75, stale_at
    assert missing_at is not None and 0.45 <= missing_at <= 0.75, missing_at
    during = [ports for t, ports, _ in sets if t_freeze <= t < t_thaw]
    assert sum(1 in p for p in during) >= 0.5 * (t_thaw - t_freeze) / 0.03          # camera khỏe giữ nhịp
    back = next((t - t_thaw for t, ports, _ in sets if t >= t_thaw and 2 in ports), None)
    assert back is not None and back <= 0.3, back
    if mode is FreezeMode.REPEAT:
        assert after["duplicates"] - before["duplicates"] >= 10 and after["read_failures"] == before["read_failures"]


# ---- bo mô phỏng: laptop treo hẳn ------------------------------------------------------------------------------------
def test_sim_board_pause_host_keeps_bytes_unread_and_skips_the_stale_check(cfg):
    io = SimVehicleIO(cfg, SIM_CFG)
    io.connect()
    io.wait_ready()
    io.arm()
    io.send(0.1, 0.0)
    io.advance(0.1)
    assert io.firmware.state == State.RUNNING
    io.events()
    io.take_new()
    io.pause_host()
    end = io.now() + 1.0
    while io.now() < end - 1e-9:
        io.service()
    assert io.take_new() == [] and io.events() == []                    # không ai đọc cổng, không TELEMETRY_STALE
    assert not io.rearm_required
    assert io.firmware.state == State.DISARMED and io.firmware.stop_reason == StopReason.LINK_TIMEOUT
    t_resume = io.now()
    io.resume_host()
    frames = io.take_new()
    assert 15 <= len(frames) <= 25 and {f.stamp.t for f in frames} == {t_resume}   # đọc dồn, đóng dấu lúc đọc
    assert io.latest().state == State.DISARMED and not io.rearm_required
    assert "TELEMETRY_STALE" not in [e.code for e in io.events()]
    io.resume_host()                                                    # không treo: không làm gì
    io.advance(0.1)
    assert io.telemetry_fresh()


# ---- nguồn tư thế ngừng (CB-6) ---------------------------------------------------------------------------------------
def settle(io, seconds=0.3):
    end = io.now() + seconds
    while io.now() < end - 1e-9:
        io.service()


def finish(kind, params, session, link, log):
    """Như bước 6–8 của fault_drill: chạy tới hết, chạy bo thêm 0,3 s, gom kết quả."""
    run_until_done(session, step=0.1)
    settle(link.io)
    tel = link.io.latest()
    return collect_session_result(kind, 1, params, session, link, log, board_final=tel.state.name,
                                  board_final_stop_reason=tel.stop_reason.name)


@pytest.mark.parametrize("mode", [PoseFault.HOLD, PoseFault.SILENT])
def test_pose_source_that_stops_updating_stops_the_run_with_stale_pose(scenario, cfg, mode):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    log = FaultLog()
    pose = FreezablePoseSource(SimTruthPose(io), clock=io.now, log=log)
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=pose)
    assert link.describe()["pose_source"] == "sim_truth_pose+fault" and link.pose_simulated
    session.set_vehicle_link(link)
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    pose.stop(mode, t_session=link.session_time_now())
    t_stop = None
    while session.simulating:
        session.advance(0.02)
        if t_stop is None and session.state != SessionState.RUNNING:
            t_stop = session.world.time
        if pose.fault is not None and t_stop is not None and session.world.time >= t_stop + 0.1 - 1e-9:
            pose.resume(t_session=link.session_time_now())             # tư thế có lại khi xe còn phanh: không đổi gì
    assert pose.fault is None
    result = finish("pose", {"mode": mode.value}, session, link, log)
    assert result.first_stop["code"] == "STALE_POSE" and result.stop_codes[0] == "STALE_POSE"
    assert result.detect_s <= (0.175 if mode is PoseFault.HOLD else 0.025)
    assert result.detect_limit_s == pytest.approx(0.175 if mode is PoseFault.HOLD else 0.025)
    assert judge(result) == []
    first_ms = result.first_stop["t_io"] * 1000
    assert not any(enable for t, enable, _, _ in received if t > first_ms)           # không enable nào sau lần dừng
    rows = [r.row() for r in log.records]
    assert [r["code"] for r in rows] == [f"FAULT_POSE_{mode.name}", "FAULT_END"]
    assert all(r["t_io"] != "" and r["t_session"] != "" and r["call"] == "" for r in rows)
    assert all(isinstance(r["t_perf"], float) for r in rows)            # đặt được lên trục perf_counter (T13, T14)
    assert rows[0]["t_perf"] <= rows[1]["t_perf"]
    assert {r["pose_source"] for r in link.command_rows} == {"sim_truth_pose+fault"}


def test_fault_wrapper_does_not_hide_the_sim_truth_pose_rule(scenario, cfg):
    io_a, io_b = sim_io(cfg, scenario.start), sim_io(cfg, scenario.start)
    wrapped = FreezablePoseSource(SimTruthPose(io_a), clock=io_a.now)
    VehicleLink(DriveMode.VEHICLE_IO, io_a, pose_source=wrapped)       # bo của chính nó: được
    with pytest.raises(ValueError, match="SimTruthPose"):
        VehicleLink(DriveMode.VEHICLE_IO, io_b, pose_source=wrapped)
    with pytest.raises(ValueError, match="SimTruthPose"):              # bọc hai lớp cũng không lọt
        VehicleLink(DriveMode.VEHICLE_IO, io_b, pose_source=FreezablePoseSource(wrapped, clock=io_a.now))
    clock = ManualClock()
    loop = FirmwareSerialLoopback(FirmwareModel(FAST_FW, boot_id=0xB007), clock, inputs=still_inputs)
    serial = SerialVehicleIO(loop, clock=clock, rng=random.Random(1))
    with pytest.raises(ValueError, match="SimTruthPose"):
        VehicleLink(DriveMode.VEHICLE_IO, serial, pose_source=FreezablePoseSource(SimTruthPose(io_a), clock=clock))
    blind = FreezablePoseSource(NoPoseSource(), clock=clock)
    assert blind.available is False and "định vị" in blind.reason
    session = straight_session(scenario, cfg)
    link = VehicleLink(DriveMode.VEHICLE_IO, serial, pose_source=blind)
    session.set_vehicle_link(link)
    with pytest.raises(SessionError, match="Chưa có nguồn tư thế thật"):
        session.start_run()
    assert [r["code"] for r in link.start_refusals] == ["START_NO_POSE_SOURCE"]
    assert loop.written == [] and session.state == SessionState.READY            # không một byte nào tới bo


# ---- vòng điều khiển treo (CB-5 (b), L7) -----------------------------------------------------------------------------
def started_sim_run(scenario, cfg):
    session = straight_session(scenario, cfg)
    io = sim_io(cfg, scenario.start)
    received = record_commands(io)
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=SimTruthPose(io))
    session.set_vehicle_link(link)
    session.start_run()
    advance_until(session, lambda: io.truth.speed > 0.1)
    return session, io, link, received


@pytest.mark.parametrize("phase", [0, 1, 2, 3])
@pytest.mark.parametrize("seconds, board, reason, first", [
    (0.3, State.ARMED, StopReason.COMMAND_TIMEOUT, "VEHICLE_STOPPED"),
    (1.0, State.DISARMED, StopReason.LINK_TIMEOUT, "VEHICLE_NOT_ARMED")])
def test_hang_without_heartbeat_on_the_sim_board_matches_the_serial_port(scenario, cfg, seconds, board, reason, first,
                                                                         phase):
    """Cùng mã với cổng serial giả (`test_realtime_hang_without_heartbeat_never_resumes`, CHE_DO_QUAN_SAT.md mục 8)."""
    session, io, link, received = started_sim_run(scenario, cfg)
    log = FaultLog()
    hang = hang_control_loop(session, seconds, phase=phase, log=log)
    assert (hang.io_kind, hang.phase, hang.pings, hang.heartbeat) == ("sim", phase, 0, False)
    assert (hang.board_state_at_end, hang.board_stop_reason_at_end) == (board.name, reason.name)
    assert hang.t_io_end - hang.t_io_start == pytest.approx(seconds, abs=0.011)
    assert not any(t > hang.t_io_start * 1000 for t, _, _, _ in received)    # không lệnh nào trong lúc treo
    assert [r.code for r in log.records] == ["FAULT_HANG", "FAULT_END"]
    assert 0 < log.records[0].t_perf <= log.records[1].t_perf
    result = finish("hang", {"seconds": seconds, "heartbeat": False, "phase": phase}, session, link, log)
    assert result.first_stop["code"] == first and result.session_state == "STOPPED"
    assert "TELEMETRY_STALE" not in [r["code"] for r in link.event_rows] and "STALE_TELEMETRY" not in result.stop_codes
    late = [(t, speed) for t, enable, speed, _ in received if enable and t > hang.t_io_end * 1000]
    assert late == [], f"lệnh enable tới bo sau khi hết treo: {late}"
    assert judge(result) == []


def test_hang_with_heartbeat_keeps_the_link_and_only_the_command_times_out(scenario, cfg):
    session, io, link, received = started_sim_run(scenario, cfg)
    requests = record_requests(io)                                      # sau ARM của START
    log = FaultLog()
    hang = hang_control_loop(session, 1.0, heartbeat=True, phase=0, log=log)
    assert hang.pings >= 8 and requests.count(Action.PING) == hang.pings
    assert (hang.board_state_at_end, hang.board_stop_reason_at_end) == ("ARMED", "COMMAND_TIMEOUT")
    assert io.telemetry_fresh() and not io.rearm_required               # Heartbeat giữ liên lạc: không TELEMETRY_STALE
    result = finish("hang", {"seconds": 1.0, "heartbeat": True, "phase": 0}, session, link, log)
    assert result.first_stop["code"] == "VEHICLE_STOPPED" and result.enable_after_fault_end == 0
    assert result.detect_s < 0                                          # sự kiện đọc lúc treo (Heartbeat đọc cổng)
    assert not any(enable for t, enable, _, _ in received if t > hang.t_io_end * 1000)
    assert "LINK_TIMEOUT" not in {t["stop_reason"] for t in result.board_transitions}
    assert judge(result) == []


@pytest.mark.parametrize("seconds, first", [(0.3, "VEHICLE_STOPPED"), (1.0, "VEHICLE_NOT_ARMED")])
def test_hang_on_the_fake_serial_port_reads_nothing_while_hung(scenario, cfg, seconds, first):
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
        assert firmware.state == State.RUNNING
        seen = []
        original = firmware._handle_command

        def handle(msg, now):
            seen.append((now, bool(msg.enable)))
            original(msg, now)

        firmware._handle_command = handle
        calls = []
        original_advance = loop.advance

        def advance(ms):                                                # mỗi lần bo chạy: (ms, số telemetry đã nhận)
            calls.append((ms, io.stats.telemetry_received))
            original_advance(ms)

        loop.advance = advance
        hang = hang_control_loop(session, seconds, phase=2, log=FaultLog())
        loop.advance = original_advance
        hang_ms, received_before = calls[-1]
        assert hang.io_kind == "loopback" and hang.phase == 2 and hang_ms == round(seconds * 1000)
        assert io.stats.telemetry_received == received_before          # không ai đọc cổng trong lúc treo
        assert hang.board_state_at_end == ("ARMED" if seconds < 0.5 else "DISARMED")
        for _ in range(300):
            loop.advance(16)
            session.advance(0.016)
            if not session.simulating:
                break
        assert session.state == SessionState.STOPPED and session.safety_events[0].code == first
        assert not any(enable for t, enable in seen if t >= hang.t_io_end * 1000)
        assert firmware.state == State.DISARMED
    finally:
        session.close()


def ui_ticks(session, seconds, until_done=False):
    """Nhịp giao diện 16 ms theo đồng hồ tường (như MainWindow._on_tick)."""
    last = time.perf_counter()
    end = last + seconds
    while time.perf_counter() < end:
        time.sleep(0.016)
        now = time.perf_counter()
        session.advance(min(now - last, 0.1))
        last = now
        if until_done and not session.simulating:
            return


@pytest.mark.parametrize("heartbeat", [False, True])
def test_hang_on_a_wall_clock_port_sleeps_with_and_without_the_heartbeat_thread(scenario, cfg, heartbeat):
    """Đồng hồ tường (≈ 1,5 s thật): `time.sleep` trong chính luồng gọi `session.advance`, có/không `Heartbeat`."""
    session = straight_session(scenario, cfg)
    firmware = FirmwareModel(FAST_FW, boot_id=0xB007)
    port = WallClockSerialPort(firmware)
    io = SerialVehicleIO(port, clock=port.now, rng=random.Random(1))
    link = VehicleLink(DriveMode.VEHICLE_IO, io, pose_source=FixedPose(io, scenario.start))
    session.set_vehicle_link(link)
    session.start_run()
    seen = []
    original = firmware._handle_command

    def handle(msg, now):
        seen.append((now, bool(msg.enable)))
        original(msg, now)

    firmware._handle_command = handle
    try:
        ui_ticks(session, 0.3)
        assert session.state == SessionState.RUNNING and firmware.state == State.RUNNING
        with pytest.raises(ValueError, match="đồng hồ tường"):
            hang_control_loop(session, 0.8, heartbeat=heartbeat, phase=0)
        log = FaultLog()
        hang = hang_control_loop(session, 0.8, heartbeat=heartbeat, log=log)
        assert hang.io_kind == "wall_clock" and hang.board_state_at_end is None
        assert hang.t_io_end - hang.t_io_start >= 0.8
        started, ended = log.records                                    # FAULT_HANG, FAULT_END: có t_perf (T13)
        assert ended.t_perf - started.t_perf >= 0.8
        ui_ticks(session, 3.0, until_done=True)
        assert session.state == SessionState.STOPPED
        reasons = {t["stop_reason"] for t in board_transitions(link.telemetry_rows, hang.t_io_start)}
        if heartbeat:
            assert hang.pings >= 5 and session.safety_events[0].code == "VEHICLE_STOPPED"
            assert "COMMAND_TIMEOUT" in reasons and "LINK_TIMEOUT" not in reasons
        else:
            assert hang.pings == 0 and session.safety_events[0].code == "VEHICLE_NOT_ARMED"
            assert "LINK_TIMEOUT" in reasons
        assert not any(enable for t, enable in seen if t >= hang.t_io_end * 1000)
    finally:
        session.close()


def test_hang_is_refused_outside_a_vehicle_io_run(scenario, cfg):
    sim_only = straight_session(type(scenario).from_dict(scenario.to_dict()), cfg)
    with pytest.raises(ValueError, match="đang chạy qua VehicleIO"):
        hang_control_loop(sim_only, 1.0)                                # trước START
    sim_only.start_run()                                                # SIM giai đoạn 0
    with pytest.raises(ValueError, match="đang chạy qua VehicleIO"):
        hang_control_loop(sim_only, 1.0)
    session, io, link, _ = started_sim_run(scenario, cfg)
    t = io.now()
    for bad in (0.0, -0.1, math.nan, math.inf):
        with pytest.raises(ValueError, match="seconds"):
            hang_control_loop(session, bad)
    with pytest.raises(ValueError, match="phase"):
        hang_control_loop(session, 0.3, phase=Session.CONTROL_EVERY)
    assert session.state == SessionState.RUNNING and io.now() == t and not io.host_paused   # không đụng gì


# ---- phán quyết ------------------------------------------------------------------------------------------------------
LIMITS = {"command_validity_s": 0.15, "link_timeout_s": 0.5, "max_state_age_s": 0.15, "control_period_s": 0.02,
          "physics_dt_s": 0.005}


def transition(reason, state="ARMED", t=2.2):
    return {"t_io": t, "device_time_ms": int(t * 1000), "state": state, "stop_reason": reason, "from_state": "RUNNING",
            "from_stop_reason": "BOOT"}


def drill_result(kind="pose", params=None, **changes) -> SessionDrillResult:
    """Kết quả ĐẠT dựng tay (tư thế HOLD, hoặc treo 1 s không Heartbeat), rồi đổi các trường cần thử."""
    pose = kind == "pose"
    values = dict(
        kind=kind, run=1, params=params or ({"mode": "hold"} if pose else {"seconds": 1.0, "heartbeat": False}),
        t_fault_io=2.0, t_fault_end_io=2.3 if pose else 3.0, t_fault_session=1.0,
        first_stop={"code": "STALE_POSE" if pose else "VEHICLE_NOT_ARMED", "source": "vehicle_link", "message": "",
                    "t_session": 1.16, "t_io": 2.16 if pose else 3.0, "t_io_from": "safety_event", "t_world": 1.16},
        stop_codes=["STALE_POSE" if pose else "VEHICLE_NOT_ARMED", "WAIT_REPLAN"], vehicle_io_events=[],
        first_stop_command_t_io=2.16 if pose else None, detect_s=0.16 if pose else 0.0,
        detect_limit_s=0.175 if pose else None, enable_after_stop=0, enable_after_fault_end=0,
        board_transitions=([transition("ENABLE_CLEARED")] if pose else
                           [transition("COMMAND_TIMEOUT", t=3.0), transition("LINK_TIMEOUT", "DISARMED", 3.0)]),
        board_final="DISARMED", board_final_stop_reason="HOST_DISARM", session_state="STOPPED", stop_reason="dừng",
        path_invalidated=True, limits=dict(LIMITS))
    values.update(changes)
    return SessionDrillResult(**values)


def test_judge_flags_each_missing_reaction():
    assert judge(drill_result("pose")) == [] and judge(drill_result("hang")) == []
    cases = [
        (drill_result("hang", first_stop={**drill_result("hang").first_stop, "code": "STALE_POSE"}),
         "cần một trong VEHICLE_STOPPED/VEHICLE_NOT_ARMED/STALE_TELEMETRY"),
        (drill_result("pose", enable_after_stop=2), "Có 2 COMMAND enable=1 gửi tới bo từ lần dừng đầu"),
        (drill_result("hang", enable_after_fault_end=1), "Có 1 COMMAND enable=1 gửi tới bo sau khi hết treo"),
        (drill_result("hang", params={"seconds": 1.0, "heartbeat": True}), "Có Heartbeat mà bo vẫn LINK_TIMEOUT"),
        (drill_result("hang", board_transitions=[transition("COMMAND_TIMEOUT")]), "mà bo không LINK_TIMEOUT"),
        (drill_result("hang", params={"seconds": 0.3, "heartbeat": False}), "mà bo đã LINK_TIMEOUT"),
        (drill_result("hang", board_transitions=[]), "không báo COMMAND_TIMEOUT hay LINK_TIMEOUT"),
        (drill_result("pose", board_transitions=[transition("COMMAND_TIMEOUT")]),
         "watchdog (COMMAND_TIMEOUT) thay vì lệnh enable=0"),
        (drill_result("pose", detect_s=0.2), "quá giới hạn của công cụ 0,175 s"),
        (drill_result("pose", first_stop={**drill_result("pose").first_stop, "code": "STALE_TELEMETRY"}),
         "cần STALE_POSE"),
        (drill_result("pose", first_stop=None), "Mã dừng đầu là không có"),
        (drill_result("pose", session_state="COMPLETED"), "kết thúc ở COMPLETED, cần STOPPED"),
        (drill_result("pose", path_invalidated=False), "không bị hủy"),
        (drill_result("hang", board_final="ARMED"), "Bo cuối cùng ở ARMED, cần DISARMED"),
    ]
    for result, needle in cases:
        problems = judge(result)
        assert any(needle in p for p in problems), (needle, problems)
    # Treo ngắn hơn hạn lệnh: chỉ báo số, kể cả khi lần chạy không dừng
    short = drill_result("hang", params={"seconds": 0.1, "heartbeat": False}, first_stop=None, stop_codes=[],
                         board_transitions=[], session_state="COMPLETED", path_invalidated=False)
    assert judge(short) == []


# ---- công cụ diễn tập ------------------------------------------------------------------------------------------------
@pytest.fixture
def no_git(monkeypatch):
    """`main()` ghi trạng thái git vào tóm tắt: test không chạy git trên repo thật (git add/commit chạy cùng lúc)."""
    monkeypatch.setattr(fault_drill, "_git_state", lambda: {"head": "test", "dirty": False})


def test_git_state_reads_the_repo_without_taking_the_index_lock(monkeypatch):
    calls = []

    def check_output(args, **kwargs):
        calls.append(list(args))
        return b"abc1234\n" if "rev-parse" in args else b""

    monkeypatch.setattr(fault_drill.subprocess, "check_output", check_output)
    assert fault_drill._git_state() == {"head": "abc1234", "dirty": False}
    status = next(c for c in calls if "status" in c)
    assert status[:3] == ["git", "--no-optional-locks", "status"]        # không ghi lại .git/index (index.lock)


def test_drill_pose_and_hang_write_logs_and_pass(tmp_path, capsys, no_git):
    # tệp của một lần chạy phiên lấy từ chính VehicleLink.write_logs (T9, T15 đã thêm tệp), cộng hai tệp của công cụ
    assert {"commands.csv", "events.csv", "board_actions.csv", "poses.csv", "clock.csv", "link.json"} <= set(
        fault_drill.SESSION_FILES) and fault_drill.SESSION_FILES[-2:] == ("faults.csv", "drill.json")
    out = tmp_path / "dien_tap"
    assert fault_drill.main(["pose", "--out", str(out), "--name", "cb6"]) == 0
    assert fault_drill.main(["hang", "--seconds", "1", "--phases", "0", "2", "--out", str(out), "--name", "cb5b"]) == 0
    for name, runs, code in (("cb6", 1, "STALE_POSE"), ("cb5b", 2, "VEHICLE_NOT_ARMED")):
        summary = json.loads((out / f"{name}.drill.json").read_text(encoding="utf-8"))
        assert summary["ok"] is True and summary["evidence"] == "simulation_only" and len(summary["runs"]) == runs
        assert summary["tool"] == "autopark.evaluation.fault_drill" and summary["ecoqos"]
        for k in range(1, runs + 1):
            folder = out / f"{name}_{k:02d}"
            assert sorted(p.name for p in folder.iterdir()) == sorted(fault_drill.SESSION_FILES)
            drill = json.loads((folder / "drill.json").read_text(encoding="utf-8"))
            assert drill["ok"] is True and drill["first_stop"]["code"] == code and drill["enable_after_stop"] == 0
    with open(out / "cb6_01" / "faults.csv", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == FAULT_FIELDS
    with open(out / "cb6_01" / "events.csv", encoding="utf-8", newline="") as f:
        events_fields = csv.DictReader(f).fieldnames
    assert [c for c in reader.fieldnames if c != "t_rig"] == events_fields         # nối được với events.csv
    assert rows[0]["code"] == "FAULT_POSE_HOLD" and rows[0]["t_io"] != "" and rows[0]["t_session"] != ""
    assert rows[0]["t_perf"] != "" and rows[0]["call"] == ""
    link = json.loads((out / "cb6_01" / "link.json").read_text(encoding="utf-8"))
    assert link["pose_source"] == "sim_truth_pose+fault" and link["evidence"] == "simulation_only"
    text = capsys.readouterr().out
    assert "dừng đầu STALE_POSE" in text and "ĐẠT" in text and "pha 2" in text
    for argv in (["pose", "--out", str(out), "--name", "cb6"],                         # tên đã dùng: không ghi đè
                 ["hang", "--phases", "4", "--out", str(out), "--name", "moi"],
                 ["camera", "--ports", "1", "2", "--port", "3", "--out", str(out), "--name", "moi"]):
        with pytest.raises(SystemExit) as info:
            fault_drill.main(argv)
        assert info.value.code == 2
    assert not (out / "moi.drill.json").exists()


def test_drill_camera_on_fake_cameras_reports_when_the_camera_went_stale(tmp_path, no_git):
    out = tmp_path / "camera"
    argv = ["camera", "--mode", "stall", "--seconds", "0.8", "--warmup", "0.5", "--out", str(out), "--name", "cb2"]
    assert fault_drill.main(argv) == 0
    drill = json.loads((out / "cb2_01" / "drill.json").read_text(encoding="utf-8"))
    assert drill["ok"] is True and drill["stale_after_s"] <= 0.75 and drill["stop_alive"] == []
    assert drill["missing_after_s"] <= 0.75 and drill["rejoined_after_s"] <= 1.0
    assert drill["skipped_after_stall"] == 0                            # camera giả không trả dồn khung
    assert sorted(p.name for p in (out / "cb2_01").iterdir()) == sorted(fault_drill.CAMERA_FILES)
    rows = read_csv(out / "cb2_01" / "faults.csv")
    assert [r["code"] for r in rows] == ["FAULT_CAMERA_STALL", "FAULT_END"] and all(r["t_rig"] != "" for r in rows)


def test_drill_camera_stall_on_a_replay_loses_the_frozen_frames_like_a_real_camera(tmp_path, no_git):
    """--replay: bản ghi 2 cổng × 3 s, khung 30 ms (RigRecorder với đồng hồ giả: dựng tức thì). Nguồn phát lại không mất
    mục nào khi không ai đọc; nếu trả dồn khung của lúc STALL với stamp cũ thì khoảng hở chỉ ≈ 30 ms và camera "quay
    lại" bằng khung cũ ≈ 0,47 s. Phải như camera thật: khung đó mất, khoảng hở = lúc đóng băng, quay lại bằng khung
    mới."""
    recording = tmp_path / "ban_ghi"
    rec = RigRecorder(recording, ports=[1, 2], image_format="png", clock=lambda: 1.0).start()
    for k in range(100):
        for port in (1, 2):
            rec.add_frame(port, _frame(f"cam_p{port}", 1.0 + 0.03 * k, f"giả#{k}",
                                       np.full((48, 64, 3), (k * 7 + port * 40) % 256, np.uint8)))
    assert rec.stop(wait=True, timeout=30.0)["state"] == "xong"
    out = tmp_path / "camera"
    argv = ["camera", "--mode", "stall", "--seconds", "0.8", "--warmup", "0.5", "--replay", str(recording),
            "--ports", "1", "2", "--port", "2", "--out", str(out), "--name", "cb2"]
    assert fault_drill.main(argv) == 0
    drill = json.loads((out / "cb2_01" / "drill.json").read_text(encoding="utf-8"))
    frozen = next(c for c in drill["camera_stats_end"] if c["port"] == 2)
    assert drill["ok"] is True and drill["source"].startswith("phát lại") and drill["stop_alive"] == []
    assert frozen["gap_closed_max_ms"] >= 1000 * (0.8 - 0.05), frozen          # lúc đóng băng là một khoảng hở
    assert frozen["age_ms"] < 250, frozen                                      # quay lại bằng khung mới
    assert drill["skipped_after_stall"] >= 20                                  # ≈ 0,8 s / 30 ms khung bị bỏ


def test_drill_exit_code_is_one_when_a_reaction_is_missing(tmp_path, monkeypatch, no_git):
    monkeypatch.setattr(fault_drill, "judge", lambda r: ["giả"])
    out = tmp_path / "hong"
    assert fault_drill.main(["pose", "--mode", "silent", "--out", str(out), "--name", "x"]) == 1
    drill = json.loads((out / "x_01" / "drill.json").read_text(encoding="utf-8"))
    assert drill["ok"] is False and drill["problems"] == ["giả"]
    assert json.loads((out / "x.drill.json").read_text(encoding="utf-8"))["ok"] is False
