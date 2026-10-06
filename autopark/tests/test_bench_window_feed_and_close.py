"""Sửa sau review đợt 2 (02/10/2026): `ui.lidar_app` (BenchWindow), `Session`, ngăn LiDAR, nguồn tư thế
LiDAR và ngăn "Ghi cảm biến". Offscreen, không thiết bị: serial.Serial / serial_for_url và cv2.VideoCapture bị thay bằng
hàm từ chối, hộp thoại bị thay bằng hàm ghi lại, LiDAR là vòng quét tổng hợp hay bản ghi giả, bo "thật" là cổng serial
GIẢ (vòng lặp firmware mô phỏng), bo ảo QEMU là bo GIẢ (tests/qemu_fakes.py). Mỗi test hỏng trên mã trước bản sửa.

- "Chọn bản đồ LiDAR…" với thư mục không phải bản đồ: hộp cảnh báo, không NameError (phát hiện 0, 29).
- Đổi xe giữ `start_source` của điểm xuất phát lấy từ LiDAR; kịch bản mới thì về "manual" (1, 13, 33).
- meta.json của bản ghi cảm biến: bo "sim" / "qemu" / cổng COM và giới hạn đổi chiều CÓ HIỆU LỰC (2, 7, 16, 34).
- Vòng quét phát lại không bao giờ đi với bo thật; nhãn bằng chứng theo nguồn ĐANG gắn ở ngăn LiDAR (10, 17, 31).
- Đóng cửa sổ: dừng xe + DISARM (và tắt bo ảo QEMU) trước khi chờ bản ghi ghi nốt (15, 30).
- Lỗi ghi không bị đổ cho hàng đợi đầy (18).
"""
from dataclasses import replace
import json
import os
import random
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from autopark.application.lidar_pose_source import LidarPoseSource, evidence_for_feed  # noqa: E402
from autopark.application.session import Session, SessionState  # noqa: E402
from autopark.application.vehicle_link import DriveMode, LinkParams, VehicleLink, VehicleLinkError  # noqa: E402
from autopark.domain.types import ParkingGoal, Pose  # noqa: E402
from autopark.lidar.live_view import PacedReplay  # noqa: E402
from autopark.lidar.map_builder import MapBuildConfig, PlacementSpec, build_static_map, write_map  # noqa: E402
from autopark.lidar.pose_config import Prerequisite  # noqa: E402
from autopark.lidar.pose_estimator import LidarPoseEstimator  # noqa: E402
from autopark.perception.paths import PROJECT  # noqa: E402
from autopark.rig.core import Rig, RigConfig  # noqa: E402
from autopark.rig.recording import RigRecorder  # noqa: E402
from autopark.rig.session_recording import GB, RecordOptions, SessionSensorRecorder  # noqa: E402
from autopark.storage import run_store  # noqa: E402
from autopark.storage.scenario_store import load_vehicle_config_file  # noqa: E402
from autopark.transport.firmware_model import FirmwareModel  # noqa: E402
from autopark.transport.loopback import FirmwareSerialLoopback, ManualClock  # noqa: E402
from autopark.transport.vehicle_io import SIM_FIRMWARE_DEFAULT, SerialVehicleIO  # noqa: E402
from autopark.ui import lidar_app, theme  # noqa: E402
from autopark.ui.lidar_dock import DockLidarReplay  # noqa: E402
from autopark.ui.main_window import QEMU_BOARD_KEY  # noqa: E402
from autopark.ui.record_dock import status_lines  # noqa: E402
from autopark.video.multicam import RIG_CLOCK  # noqa: E402
from tests.lidar_fakes import CAR, bench_scenario, build_map, default_config, scan_at, scan_obj  # noqa: E402
from tests.lidar_fakes import static_slice, write_recording  # noqa: E402
from tests.qemu_fakes import FakeQemuBoard, make_runner  # noqa: E402
from tests.rig_fakes import DockFakeLidar, fake_manager  # noqa: E402
from tests.test_lidar_dock_ui import FakeSource  # noqa: E402
from tests.test_session_recording import FakeHost, record_session  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def no_devices(monkeypatch):
    """Không cổng COM, không camera thật, không PowerShell; hộp thoại ghi lời vào danh sách thay vì hiện ra."""
    import serial

    def refuse(*args, **kwargs):
        raise AssertionError("test không được mở thiết bị thật")

    monkeypatch.setattr(serial, "Serial", refuse)
    monkeypatch.setattr(serial, "serial_for_url", refuse)
    monkeypatch.setattr(cv2, "VideoCapture", refuse)
    monkeypatch.setattr(run_store, "environment", lambda: {"stub": True})
    shown = []
    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda parent, title, text, *a, **k: shown.append(text)))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    return shown


@pytest.fixture(scope="module")
def lidar_map(tmp_path_factory):
    """Bản đồ của map_builder (hệ sa bàn) từ một chỗ đặt: LiDAR gá trên xe ở điểm xuất phát (0,5; 1,0; 0); kèm bản ghi
    `.npz` của chỗ đặt đó (phát lại được bằng `--recording`)."""
    folder = tmp_path_factory.mktemp("nhom_a") / "ban_do"
    sensor = default_config().mount.sensor_pose(Pose(0.5, 1.0, 0.0))
    pose = (sensor.x, sensor.y, sensor.yaw)
    npz = write_recording(folder.parent / "cho_dat_1", static_slice(pose, 2.0, np.random.default_rng(71)))
    write_map(build_static_map([PlacementSpec(npz)], anchor=pose, config=MapBuildConfig(skip_seconds=0.0)), folder)
    return folder, npz


def open_bench(scenario=None, *, port="COM_GIA", recording=None, tmp_path=None):
    """Cửa sổ ui.lidar_app, mọi timer dừng (test tự gọi nhịp); có tmp_path thì bản ghi, dấu đồng bộ vào đó, đĩa giả."""
    record = None if tmp_path is None else RecordOptions(root=tmp_path / "ghi", image_format="png")
    bench, dock = lidar_app.build_window(scenario, port=port, recording=recording, record=record)
    bench._timer.stop()
    dock.timer.stop()
    bench.record_dock.timer.stop()
    if tmp_path is not None:
        bench.sync_dir = tmp_path / "sync"
        bench.sensor_recording.free_bytes = lambda path: 100 * GB
    return bench, dock


def pump(window, seconds, until=None):
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        window.dock.tick()
        window._poll_state_change()
        window.record_dock.poll_once()
        if until is not None and until():
            return True
        time.sleep(0.02)
    return until is None


def select(combo, data):
    index = combo.findData(data)
    assert index >= 0, data
    combo.setCurrentIndex(index)


def add_port(window, port):
    if window.combo_port.findData(port) < 0:
        window.combo_port.addItem(port, port)


def feed(source, n, seed=72, vehicle=Pose(0.5, 1.0, 0.0)):
    """Vòng quét tổng hợp đưa thẳng vào nguồn tư thế (không luồng): bắt được sau vài vòng."""
    rng = np.random.default_rng(seed)
    sensor = source.config.mount.sensor_pose(vehicle)
    for _ in range(n):
        source.on_scan(scan_obj(*scan_at(sensor, rng), 0.0), None, None, time.perf_counter())
        source.pump()
        time.sleep(0.002)


def ready_config():
    """Cấu hình định vị như khi gá đã đo và đạt p04, DV-2, DV-1 (CHỈ trong test: tệp thật vẫn chưa đạt)."""
    config = default_config()
    return replace(config, mount=replace(config.mount, measured=True, evidence="docs/evidence/ga.json"),
                   prerequisites=tuple(Prerequisite(p.key, True, "docs/evidence/x.json") for p in config.prerequisites))


def serial_io(opened):
    """Bo "thật" qua cổng serial GIẢ (vòng lặp firmware mô phỏng, cổng chưa mở); `opened` đếm lần mở ở bước 0c."""
    clock = ManualClock()
    firmware = FirmwareModel(replace(SIM_FIRMWARE_DEFAULT, boot_hold_ms=200), boot_id=0xB007)

    def opener():
        opened.append(1)
        return FirmwareSerialLoopback(firmware, clock)

    return SerialVehicleIO(None, opener=opener, clock=clock, port="COM7", rng=random.Random(2))


class FeedConsumer:
    """Người tiêu thụ vòng quét chỉ ghi lại loại nguồn ngăn LiDAR báo."""

    def __init__(self):
        self.kinds = []

    def on_scan(self, *args):
        pass

    def set_feed_kind(self, kind):
        self.kinds.append(kind)


# ------------------------------------------------------------------------------------------------ 0, 29
def test_choosing_a_folder_that_is_not_a_map_shows_a_warning(qapp, no_devices, tmp_path, monkeypatch):
    """"Chọn bản đồ LiDAR…" với thư mục không có costmap.json: hộp cảnh báo nói lý do, nguồn cũ giữ nguyên. Trước bản
    sửa: NameError (lidar_app không còn nhập QMessageBox), không hộp thoại nào."""
    bench, dock = open_bench()
    try:
        bad = tmp_path / "không phải bản đồ"
        bad.mkdir()
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(bad)))
        bench._choose_lidar_map()
        assert len(no_devices) == 1 and "Không có costmap.json" in no_devices[0]
        assert bench.lidar_pose_source is None
    finally:
        bench.close()


# ------------------------------------------------------------------------------------------------ 1, 13, 33
def test_changing_the_vehicle_keeps_the_lidar_start_source_and_a_new_scenario_resets_it():
    scenario = bench_scenario()
    scenario.goal = ParkingGoal(Pose(1.6, 1.0, 0.0))
    session = Session(scenario, CAR)
    lidar_pose = Pose(0.52, 1.01, 0.02)
    session.set_start(lidar_pose, source="lidar_localize")              # "Đặt xuất phát theo LiDAR"
    chosen = load_vehicle_config_file(PROJECT / "configs" / "vehicle_nghiem_thu.json")
    session.set_vehicle(chosen.cfg, chosen.path)                         # ô "Cấu hình xe"
    assert session.scenario.start == lidar_pose and session.start_source == "lidar_localize"
    assert session.plan_sync().ok
    session.start_run()                                                  # nhánh SIM: không I/O
    assert session.run_snapshot["start_source"] == "lidar_localize"      # START không được ghi là kiểm độc lập
    session.close()
    other = Session(bench_scenario(), CAR)
    other.set_start(lidar_pose, source="lidar_localize")
    other.replace_scenario(bench_scenario(start=Pose(0.6, 1.0, 0.0)), CAR)    # "Mở kịch bản": điểm của tệp
    assert other.start_source == "manual"
    other.close()


# ------------------------------------------------------------------------------------------------ 2, 7, 16, 34
def test_sensor_recording_meta_names_the_board_and_the_effective_cusp_limit(qapp, no_devices, tmp_path):
    bench, dock = open_bench(PROJECT / "scenarios" / "nghiem_thu" / "do1.json", tmp_path=tmp_path)
    recorder = bench.sensor_recording
    try:
        limit = bench.session.cusp_limit()
        assert limit.policy.max_cusps == 2 and bench.session.cusp_policy.max_cusps is None   # DO-1: từ tệp ngưỡng
        meta = bench.session_meta()
        assert meta["board"] == "sim" and meta["cusp_policy"] == limit.to_dict()
        assert (meta["cusp_policy"]["max_cusps"], meta["cusp_policy"]["key"]) == (2, "DO-1")
        add_port(bench, "COM_BO_GIA")
        select(bench.combo_port, "COM_BO_GIA")
        assert bench.session_meta()["board"] == "COM_BO_GIA"
        bench.attach_qemu_runner(make_runner(tmp_path, FakeQemuBoard()))
        select(bench.combo_port, QEMU_BOARD_KEY)                          # bo ảo QEMU: board_port() là None
        assert bench.board_is_qemu() and bench.board_port() is None and bench.session_meta()["board"] == "qemu"
        dock.attach_source(DockFakeLidar(period=0.05))
        assert pump(bench, 3.0, until=lambda: dock.scans >= 2)
        bench.record_dock.refresh()
        bench.record_dock.btn_record.click()
        assert recorder.active
        pump(bench, 0.3)
        bench.record_dock.btn_record.click()
        assert recorder.wait_finished(20.0)
    finally:
        dock.shutdown()
        bench.close()
    meta = json.loads((recorder.rec.folder / "meta.json").read_text(encoding="utf-8"))
    session = meta["session_recording"]["session"]
    assert session["board"] == "qemu" and session["cusp_policy"] == limit.to_dict()


# ------------------------------------------------------------------------------------------------ 10: cổng START
@pytest.mark.parametrize("evidence, needle", [("recording_replay", "bản ghi phát lại (--recording)"),
                                              ("session_replay", "phát lại một phiên ghi (--session-replay)"),
                                              ("other_source", "không phải driver RPLIDAR C1"),
                                              ("no_feed", "ngăn LiDAR đã ngắt")])
def test_scans_that_are_not_the_live_lidar_never_pass_the_real_board_gate(evidence, needle):
    """Kể cả khi tệp cấu hình ghi đủ điều kiện tiên quyết: bo thật bị từ chối ở VEHICLE_IO lẫn Quan sát; bo mô phỏng /
    bo ảo gắn cờ chỉ có cảnh báo. Trước bản sửa `start_gate` không xem `evidence`: ([], [])."""
    ready = ready_config()
    source = LidarPoseSource(object(), ready, map_info={}, threaded=False, evidence=evidence)
    for mode in ("VEHICLE_IO", "OBSERVE"):
        refusals, warnings = source.start_gate(mode, hardware=True)
        assert len(refusals) == 1 and needle in refusals[0] and f"evidence {evidence}" in refusals[0], mode
        assert warnings == []
        refusals, warnings = source.start_gate(mode, hardware=False)
        assert refusals == [] and len(warnings) == 1 and needle in warnings[0], mode
    live = LidarPoseSource(object(), ready, map_info={}, threaded=False)
    live.set_feed_kind("live")
    assert live.start_gate("VEHICLE_IO", hardware=True) == ([], [])
    assert live.start_gate("OBSERVE", hardware=True) == ([], [])


def test_feed_kind_sets_the_evidence_and_a_run_keeps_its_own_label():
    assert [evidence_for_feed(k) for k in ("live", "recording_replay", "session_replay", "other", None, "lạ")] == \
        ["device", "recording_replay", "session_replay", "other_source", "no_feed", "other_source"]
    source = LidarPoseSource(object(), default_config(), map_info={}, threaded=False)
    assert source.evidence == "device" and source.feed_kind is None      # dựng thẳng (test, công cụ): như trước
    source.set_feed_kind("live")
    source.run_started()                                                 # lần chạy mở khi ngăn nối LiDAR thật
    source.set_feed_kind(None)                                           # rồi ngăn ngắt LiDAR trước khi xuất log
    assert source.evidence == "no_feed" and source.describe()["evidence"] == "device"     # link.json của lần chạy đó
    source.set_feed_kind("recording_replay")
    source.run_started()
    assert source.describe()["evidence"] == "recording_replay"


def test_a_replay_fed_source_is_refused_before_the_port_opens_even_with_every_prerequisite():
    """Như repro của review R: nguồn đã bắt, đủ điều kiện tiên quyết, bo COM chưa gắn cờ. Vòng quét phát lại →
    START_POSE_UNVERIFIED ở bước 0b, cổng KHÔNG mở, ở cả VEHICLE_IO lẫn Quan sát. Cùng nguồn khi ngăn báo LiDAR thật thì
    qua bước 0b, mở cổng (giả) và tới START_CHECK (bo giả không đo tốc độ/góc lái, T8)."""
    ready = ready_config()
    est = LidarPoseEstimator(build_map(), ready.localizer, mount=ready.mount, odometry=ready.odometry,
                             hint=Pose(0.5, 1.0, 0.0))
    source = LidarPoseSource(est, ready, map_info={"mirror": False}, threaded=False, evidence="recording_replay")
    feed(source, 9, seed=41)
    assert source.available and ready.unmet() == []
    scenario = bench_scenario()
    for mode in (DriveMode.VEHICLE_IO, DriveMode.OBSERVE):
        opened = []
        link = VehicleLink(mode, serial_io(opened), pose_source=source, params=LinkParams(max_pose_age_s=0.25))
        assert link.hardware_actuators
        with pytest.raises(VehicleLinkError, match="bản ghi phát lại"):
            link.begin_run(scenario, CAR, 0.01)
        assert [r["code"] for r in link.start_refusals][-1] == "START_POSE_UNVERIFIED" and opened == [], mode
        link.close()
    source.set_feed_kind("live")
    feed(source, 3, seed=42)
    opened = []
    link = VehicleLink(DriveMode.OBSERVE, serial_io(opened), pose_source=source, params=LinkParams(max_pose_age_s=0.25))
    with pytest.raises(VehicleLinkError):
        link.begin_run(scenario, CAR, 0.01)
    codes = [r["code"] for r in link.start_refusals]
    assert "START_POSE_UNVERIFIED" not in codes and "START_CHECK" in codes and len(opened) == 1
    link.close()


# ---------------------------------------------------------------------------------------------- 10, 17, 31: ngăn LiDAR
def test_the_dock_tells_its_consumers_what_feeds_them(qapp, no_devices, lidar_map, monkeypatch):
    from autopark.lidar import rplidar_c1

    class Driver(DockFakeLidar):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.t0 = None                                       # như driver: đồng hồ phiên bắt đầu ở start()

        def start(self):
            self.t0 = self.clock()

    monkeypatch.setattr(rplidar_c1.RplidarC1Source, "open",
                        classmethod(lambda cls, port, **kwargs: Driver(clock=kwargs.get("clock", RIG_CLOCK))))
    bench, dock = open_bench(port="COM_GIA")
    consumer = FeedConsumer()
    source = LidarPoseSource(object(), default_config(), map_info={}, threaded=False)
    try:
        dock.add_scan_consumer(consumer)
        dock.add_scan_consumer(source)
        assert dock.feed_kind() is None and dock.planned_feed_kind() == "live" and consumer.kinds == []
        dock.connect_source()                                    # driver C1 (giả) do chính ngăn mở
        assert dock.feed_kind() == "live" and consumer.kinds == ["live"] and source.evidence == "device"
        old_source, old_reader = dock.source, dock.reader
        dock.attach_source(FakeSource(), start_thread=False)      # gắn thẳng, KHÔNG ngắt trước: không còn là "live"
        old_reader.stop_event.set()
        old_source.close()
        assert dock.source_kind == "other" and consumer.kinds[-1] == "other" and source.evidence == "other_source"
        dock.disconnect_source()
        assert consumer.kinds[-1] is None and source.evidence == "no_feed"
        dock.attach_source(FakeSource(), start_thread=False, kind="live", port="COM_GIA")
        assert source.evidence == "device"
        late = FeedConsumer()
        dock.add_scan_consumer(late)                             # người tiêu thụ mới lúc đang có nguồn: báo ngay
        assert late.kinds == ["live"]
        dock.disconnect_source()
    finally:
        dock.shutdown()
        bench.close()
    bench, dock = open_bench(port=None, recording=lidar_map[1])
    consumer = FeedConsumer()
    try:
        assert dock.planned_feed_kind() == "recording_replay"
        dock.add_scan_consumer(consumer)
        dock.connect_source()                                    # --recording: PacedReplay, luồng đọc thật
        assert isinstance(dock.source, PacedReplay) and dock.feed_kind() == "recording_replay"
        assert consumer.kinds == ["recording_replay"]
    finally:
        dock.shutdown()
        bench.close()


def test_a_recording_replay_never_starts_a_com_board_even_in_observe(qapp, no_devices, lidar_map, monkeypatch):
    """`ui.lidar_app --recording` + "LiDAR thật" + bo COM ở Quan sát: START bị từ chối ở bước 0b, cổng COM7 không mở.
    Trước bản sửa: chỉ cảnh báo, bước 0c mở cổng (ở đây serial.Serial giả từ chối → START_NO_LINK)."""
    from autopark.lidar.live_view import ScanReader

    folder, npz = lidar_map
    bench, dock = open_bench(port=None, recording=npz)
    try:
        select(bench.combo_drive, DriveMode.OBSERVE.value)
        add_port(bench, "COM7")
        select(bench.combo_port, "COM7")
        source = bench.load_lidar_map(folder, threaded=False)
        assert source.evidence == "recording_replay"             # ngăn chưa nối: theo nguồn nó sẽ mở
        select(bench.combo_pose, "lidar_real")
        link = bench.session.vehicle_link
        assert link.pose_source is source and link.hardware_actuators and link.io.transport is None
        monkeypatch.setattr(ScanReader, "start", lambda self: None)    # luồng đọc không chạy: vòng quét do test đưa
        dock.connect_source()                                    # --recording: PacedReplay qua đường thật của ngăn
        assert isinstance(dock.source, PacedReplay) and dock.source_kind == "replay"
        assert bench.plan(sync=True).ok
        feed(source, 9)
        assert source.available and source.describe()["evidence"] == "recording_replay"
        bench.run()
        assert bench.session.state != SessionState.RUNNING
        refusal = link.start_refusals[-1]
        assert refusal["code"] == "START_POSE_UNVERIFIED" and "bản ghi phát lại" in refusal["message"]
        assert link.io.transport is None                         # cổng không mở, không gửi gì tới bo
        assert (source.feed_kind, source.evidence) == ("recording_replay", "recording_replay")
    finally:
        dock.shutdown()
        bench.close()


def test_session_replay_from_the_command_line_is_labelled_as_a_replay(qapp, no_devices, lidar_map, tmp_path,
                                                                      monkeypatch):
    """`--session-replay <bản ghi> --pose-source lidar_real --lidar-map <bản đồ>`: nguồn tư thế mang "session_replay"
    từ lúc nạp bản đồ (main() đặt replay_session trước) tới sau khi gắn DockLidarReplay và khi chọn lại bản đồ; ngăn
    LiDAR không giữ cổng COM nào; bo thật bị từ chối. Trước bản sửa: "device" và cổng của ô nhập."""
    folder, _ = lidar_map
    rec, _, _ = record_session(tmp_path / "goc", seconds=0.6, cameras=False)
    real_start = lidar_app.start_session_replay
    captured = {}

    def capture(window, session, **kwargs):
        captured.update(window=window, session=session, evidence=window.lidar_pose_source.evidence,
                        port=window._dock_lidar_port())
        return False

    class Policy:                                                # không đổi EcoQoS của tiến trình pytest
        windows = False

    monkeypatch.setattr(lidar_app, "start_session_replay", capture)
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(lidar_app, "apply_ecoqos_policy", lambda component: Policy())
    monkeypatch.setattr(lidar_app, "add_ecoqos_label", lambda window, policy: None)
    assert lidar_app.main(["--session-replay", str(rec.folder), "--pose-source", "lidar_real",
                           "--lidar-map", str(folder)]) == 0
    window, session = captured["window"], captured["session"]
    dock = window.dock
    try:
        window._timer.stop()
        dock.timer.stop()
        window.record_dock.timer.stop()
        assert dock.replay_session is session and window.pose_choice() == "lidar_real"
        assert captured["evidence"] == "session_replay" and captured["port"] is None
        real_start(window, session)                              # gắn DockLidarReplay như main()
        assert isinstance(dock.source, DockLidarReplay) and dock.feed_kind() == "session_replay"
        source = window.lidar_pose_source
        assert (source.feed_kind, source.evidence, source.describe()["evidence"]) == ("session_replay",) * 3
        refusals, _ = source.start_gate("OBSERVE", hardware=True)
        assert refusals and "phát lại một phiên ghi" in refusals[0]
        later = window.load_lidar_map(folder, threaded=False)    # "Chọn bản đồ LiDAR…" khi đang phát lại
        assert (later.feed_kind, later.evidence) == ("session_replay", "session_replay")
    finally:
        dock.shutdown()
        window.close()


# ------------------------------------------------------------------------------------------------ 15, 30
def test_closing_the_window_stops_the_car_before_waiting_for_the_recording(qapp, no_devices, tmp_path):
    """Đóng cửa sổ khi xe đang chạy qua VehicleIO (bo mô phỏng): enable=0 + DISARM (VehicleLink.close qua
    session.close()) và tắt bo ảo QEMU đi TRƯỚC lần chờ bản ghi ghi nốt; lần chờ vẫn có hạn RECORD_WAIT_S và đến sau khi
    ngăn LiDAR đã đóng nguồn. Trước bản sửa: chờ trước, liên kết còn mở."""
    bench, dock = open_bench(tmp_path=tmp_path)
    select(bench.combo_drive, DriveMode.VEHICLE_IO.value)
    assert bench.plan(sync=True).ok
    bench.run()
    assert bench.session.state == SessionState.RUNNING
    link = bench.session.run_link
    source = DockFakeLidar(period=0.05)
    dock.attach_source(source)
    order = []
    real_shutdown = bench.qemu_runner.shutdown

    def spy_shutdown(*args, **kwargs):
        order.append(("qemu_shutdown", link._closed))
        return real_shutdown(*args, **kwargs)

    def spy_wait(timeout_s=60.0):
        order.append(("wait", timeout_s, link._closed, source.closed))
        return True

    bench.qemu_runner.shutdown = spy_shutdown
    bench.sensor_recording.wait_finished = spy_wait
    bench.close()
    assert order == [("qemu_shutdown", True), ("wait", lidar_app.RECORD_WAIT_S, True, True)]


# ------------------------------------------------------------------------------------------------ 18
def test_a_write_error_is_not_blamed_on_a_full_queue(tmp_path, monkeypatch):
    error = "ghi khung cổng 1 seq 1: OSError: [Errno 28] No space left on device"
    err = status_lines({"state": "error", "error": error, "dropped_total": 11})
    assert err == [(f"LỖI GHI: {error} · 11 khung bị bỏ", theme.DANGER)]          # không có dòng GHI THIẾU
    for state in ("recording", "draining"):                      # ≤ 1 s trước khi poll() dừng ghi, và lúc ghi nốt
        lines = status_lines({"state": state, "error": "ghi khung: OSError", "dropped_total": 3, "pending_frames": 2})
        assert not any("hàng đợi ghi đầy" in text for text, _ in lines), state
    full_queue = status_lines({"state": "done", "folder": "x", "dropped_total": 37})
    assert ("GHI THIẾU: hàng đợi ghi đầy (đĩa chậm?), 37 khung bị bỏ", theme.WARN) in full_queue

    def disk_full(self, path, data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(RigRecorder, "_write_bytes", disk_full)   # như repro của review S: đĩa đầy GIẢ
    rig = Rig(fake_manager(ports=(1,), period=0.03), RigConfig(ai=False))
    recorder = SessionSensorRecorder(FakeHost(rig, None), RecordOptions(root=tmp_path / "g"),
                                     free_bytes=lambda path: 100 * GB)
    rig.start()
    try:
        rec = recorder.start()
        deadline = time.perf_counter() + 5.0
        while rec.error is None and time.perf_counter() < deadline:
            time.sleep(0.02)
        assert rec.error is not None
        time.sleep(0.3)                                          # khung vẫn tới sau lỗi: bộ ghi bỏ và đếm chung
        recorder.poll()
        assert recorder.wait_finished(10.0)
    finally:
        rig.stop()
    st = recorder.status()
    assert st["state"] == "error" and st["dropped_total"] > 0
    lines = status_lines(st)
    assert lines[0][0].startswith("LỖI GHI: ") and "khung bị bỏ" in lines[0][0] and lines[0][1] == theme.DANGER
    assert not any("hàng đợi ghi đầy" in text for text, _ in lines)
