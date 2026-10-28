"""Ô "Nguồn tư thế" của thẻ Bo điều khiển, bản đồ LiDAR của ui.lidar_app và "Đặt xuất phát theo LiDAR" (T2, thêm
02/10/2026). Offscreen, không cổng COM thật (serial.Serial bị thay bằng hàm từ chối), không LiDAR thật: vòng quét tổng hợp
(tests/lidar_fakes.py) đưa thẳng vào nguồn tư thế (`threaded=False` + `pump()`). Hộp thoại bị thay bằng hàm ghi lại."""
import math
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from autopark.application.lidar_pose_source import LidarPoseSource, LidarSimPoseFactory  # noqa: E402
from autopark.application.session import Session, SessionState  # noqa: E402
from autopark.application.vehicle_link import DriveMode, NoPoseSource, PoseSample  # noqa: E402
from autopark.domain.types import ParkingGoal, Pose  # noqa: E402
from autopark.lidar.map_builder import MapBuildConfig, PlacementSpec, build_static_map, write_map  # noqa: E402
from autopark.storage import run_store  # noqa: E402
from autopark.ui import lidar_app  # noqa: E402
from autopark.ui.main_window import MainWindow  # noqa: E402
from tests.lidar_fakes import CAR, bench_scenario, default_config, scan_at, scan_obj, static_slice  # noqa: E402
from tests.lidar_fakes import write_recording  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def no_hardware(monkeypatch):
    """Không cổng COM thật, không PowerShell; hộp thoại cảnh báo ghi vào danh sách thay vì hiện ra."""
    import serial

    def refuse(*args, **kwargs):
        raise AssertionError("test không được mở cổng thật")

    monkeypatch.setattr(serial, "Serial", refuse)
    monkeypatch.setattr(serial, "serial_for_url", refuse)
    monkeypatch.setattr(run_store, "environment", lambda: {"stub": True})
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text, *a, **k: warnings.append(text))
    return warnings


@pytest.fixture(scope="module")
def lidar_map(tmp_path_factory):
    """Bản đồ của map_builder (hệ sa bàn) từ một chỗ đặt: LiDAR gá trên xe ở điểm xuất phát (0,5; 1,0; 0)."""
    folder = tmp_path_factory.mktemp("ban_do") / "bản đồ sa bàn"
    sensor = default_config().mount.sensor_pose(Pose(0.5, 1.0, 0.0))
    pose = (sensor.x, sensor.y, sensor.yaw)
    rec = write_recording(folder.parent / "chỗ đặt 1", static_slice(pose, 2.0, np.random.default_rng(71)))
    write_map(build_static_map([PlacementSpec(rec)], anchor=pose, config=MapBuildConfig(skip_seconds=0.0)), folder)
    unanchored = folder.parent / "chưa neo"
    write_map(build_static_map([PlacementSpec(rec)], config=MapBuildConfig(skip_seconds=0.0)), unanchored)
    return folder, unanchored


def straight_scenario():
    scenario = bench_scenario()
    scenario.goal = ParkingGoal(Pose(.9, 1.0, 0.0))
    return scenario


def select(combo, data):
    index = combo.findData(data)
    assert index >= 0, data
    combo.setCurrentIndex(index)


def add_port(window, port):
    if window.combo_port.findData(port) < 0:
        window.combo_port.addItem(port, port)


class FakeLidarSource:
    """Nguồn LiDAR thật giả (cho ô chọn): luôn sẵn sàng, tư thế ở điểm xuất phát."""

    source_id = "lidar_c1_localize"
    simulated = False
    available = True
    reason = ""

    def __init__(self):
        self.config = default_config()
        self.clock = None

    def bind_clock(self, io_now):
        self.clock = io_now

    def latest(self):
        return PoseSample(Pose(0.5, 1.0, 0.0), self.clock(), self.source_id, False) if self.clock else None


def feed(source, n, seed=72, vehicle=Pose(0.5, 1.0, 0.0)):
    rng = np.random.default_rng(seed)
    sensor = source.config.mount.sensor_pose(vehicle)
    for _ in range(n):
        source.on_scan(scan_obj(*scan_at(sensor, rng), 0.0), None, None, time.perf_counter())
        source.pump()
        time.sleep(0.002)


def test_pose_combo_choices_and_refusals(qapp, no_hardware):
    window = MainWindow(Session(straight_scenario(), CAR))
    window._timer.stop()
    combo = window.combo_pose
    assert [combo.itemData(k) for k in range(combo.count())] == ["sim_truth", "lidar_sim", "lidar_real"]
    real = combo.model().item(combo.findData("lidar_real"))
    assert not real.isEnabled() and "lidar_app" in real.toolTip() and not window.btn_lidar_map.isEnabled()
    select(window.combo_drive, DriveMode.VEHICLE_IO.value)
    link = window.session.vehicle_link
    assert link.pose_factory is None and link.params.max_pose_age_s is None
    select(combo, "lidar_sim")
    link = window.session.vehicle_link
    assert isinstance(link.pose_factory, LidarSimPoseFactory) and link.params.pose_age_limit_s == 0.25
    assert "LiDAR MÔ PHỎNG" in window.lbl_board_hint.text() and "simulation_only" in window.lbl_board_hint.text()
    add_port(window, "COM7")
    select(window.combo_port, "COM7")                                   # bo COM + LiDAR mô phỏng: cấm
    assert no_hardware[-1] == "LiDAR mô phỏng chỉ dùng với bo mô phỏng"
    assert window.session.vehicle_link is link and window.board_port() is None and window.pose_choice() == "lidar_sim"
    select(combo, "sim_truth")
    select(window.combo_port, "COM7")
    link = window.session.vehicle_link
    assert isinstance(link.pose_source, NoPoseSource) and link.io.port == "COM7" and link.io.transport is None
    window.close()

    bench, dock = lidar_app.build_window(None, port="COM9", recording=None)
    bench._timer.stop()
    dock.timer.stop()
    real = bench.combo_pose.model().item(bench.combo_pose.findData("lidar_real"))
    assert real.isEnabled() and bench.btn_lidar_map.isEnabled()
    select(bench.combo_drive, DriveMode.VEHICLE_IO.value)
    before = bench.session.vehicle_link
    select(bench.combo_pose, "lidar_real")                              # bo mô phỏng + LiDAR thật: cấm
    assert no_hardware[-1].startswith("LiDAR thật không đi cùng bo mô phỏng")
    assert bench.pose_choice() == "sim_truth" and bench.session.vehicle_link is before
    add_port(bench, "COM7")
    select(bench.combo_port, "COM7")
    select(bench.combo_pose, "lidar_real")                              # chưa có bản đồ
    assert "Chưa nạp bản đồ LiDAR" in no_hardware[-1] and bench.pose_choice() == "sim_truth"
    bench.lidar_pose_source = FakeLidarSource()
    select(bench.combo_pose, "lidar_real")
    link = bench.session.vehicle_link
    assert link.pose_source is bench.lidar_pose_source and link.params.max_pose_age_s == 0.25
    assert link.io.port == "COM7" and link.io.transport is None and link.hardware_actuators
    assert "START_POSE_UNVERIFIED" in bench.lbl_board_hint.text() and "CHƯA THỬ" in bench.lbl_board_hint.text()
    bench.lidar_pose_source = None
    dock.shutdown()
    bench.close()


def test_board_port_equal_to_lidar_port_is_refused(qapp, no_hardware):
    bench, dock = lidar_app.build_window(None, port="COM9", recording=None)
    bench._timer.stop()
    dock.timer.stop()
    select(bench.combo_drive, DriveMode.OBSERVE.value)
    add_port(bench, "COM9")
    select(bench.combo_port, "COM9")
    assert no_hardware[-1] == "COM9 là cổng của LiDAR ở ngăn LiDAR, không phải bo ESP32-S3"
    assert bench.board_port() is None and bench.session.vehicle_link.io is None      # vẫn bo mô phỏng
    dock.shutdown()
    bench.close()


def test_load_lidar_map_hook_and_status_label_go_from_init_to_ok(qapp, no_hardware, lidar_map):
    good, unanchored = lidar_map
    bench, dock = lidar_app.build_window(None, port="COM9", recording=None)
    bench._timer.stop()
    dock.timer.stop()
    source = bench.load_lidar_map(good, threaded=False)
    assert isinstance(source, LidarPoseSource) and bench.lidar_pose_source is source
    assert source.map_info["frame"] == "sa_ban" and source.evidence == "device" and good.name in bench.lbl_lidar_map.text()
    assert dock.pose_provider is None and source not in dock.scan_consumers       # chưa chọn LiDAR thật
    select(bench.combo_pose, "lidar_real")
    assert dock.pose_provider is source and dock.scan_consumers == [source]
    bench._refresh_pose_status()
    assert bench.lbl_pose_status.text() == "Định vị LiDAR: Chưa có vòng quét: bấm Kết nối ở ngăn LiDAR"
    feed(source, 1)
    bench._refresh_pose_status()
    assert "đang khởi tạo" in bench.lbl_pose_status.text() and not bench.btn_start_from_lidar.isEnabled()
    feed(source, 8)
    bench._refresh_pose_status()
    assert bench.lbl_pose_status.text().startswith("Định vị LiDAR: OK · (0,5")
    assert bench.lidar_pose_item.isVisible() and bench.lidar_pose_item.pos().x() == pytest.approx(0.5, abs=0.02)
    with pytest.raises(ValueError, match="không phải hệ sa bàn"):
        bench.load_lidar_map(unanchored, threaded=False)
    assert bench.lidar_pose_source is source                            # bản đồ hỏng: nguồn cũ giữ nguyên
    select(bench.combo_pose, "sim_truth")
    assert dock.pose_provider is None and dock.scan_consumers == []
    bench.close()
    assert source.closed


def test_start_from_lidar_sets_start_and_records_start_source(qapp, no_hardware, lidar_map):
    bench, dock = lidar_app.build_window(None, port="COM9", recording=None)
    bench._timer.stop()
    dock.timer.stop()
    source = bench.load_lidar_map(lidar_map[0], threaded=False)
    select(bench.combo_pose, "lidar_real")
    feed(source, 9, vehicle=Pose(0.52, 1.01, math.radians(3)))
    bench._refresh_pose_status()
    assert bench.btn_start_from_lidar.isEnabled()
    bench.btn_start_from_lidar.click()
    start = bench.session.scenario.start
    assert start.distance_to(Pose(0.52, 1.01, 0.0)) < 0.02 and abs(math.degrees(start.yaw) - 3.0) < 1.0
    assert bench.session.start_source == "lidar_localize"
    assert "không còn là kiểm độc lập" in bench.statusBar().currentMessage()
    assert bench.plan(sync=True).ok
    bench.run()                                                          # nhánh SIM: không qua bo nào
    assert bench.session.state == SessionState.RUNNING
    assert bench.session.run_snapshot["start_source"] == "lidar_localize"
    bench.stop()
    for _ in range(40):
        bench.advance_by(0.1)
    dock.shutdown()
    bench.close()


def test_lidar_app_flags_are_validated_before_any_window_or_port(qapp, monkeypatch, lidar_map, tmp_path, capsys):
    good, unanchored = lidar_map

    def no_window(*args, **kwargs):
        raise AssertionError("không được mở cửa sổ hay cổng khi tham số sai")

    monkeypatch.setattr(lidar_app, "build_window", no_window)
    bad_config = tmp_path / "cau_hinh_hong.json"
    bad_config.write_text('{"schema_version": 1, "la": 2}', encoding="utf-8")
    for argv, needle in ((["--pose-source", "lidar_real"], "cần --lidar-map"),
                         (["--pose-source", "lidar_real", "--lidar-map", str(tmp_path / "không có")], "costmap.json"),
                         (["--lidar-map", str(unanchored)], "không phải hệ sa bàn"),
                         (["--lidar-config", str(bad_config)], "khóa lạ"),
                         (["--pose-source", "slam"], "invalid choice")):
        with pytest.raises(SystemExit) as info:
            lidar_app.main(argv + ["--no-connect"])
        assert info.value.code == 2, argv
        assert needle in capsys.readouterr().err, argv
    monkeypatch.undo()
    parser = __import__("argparse").ArgumentParser()
    lidar_app.add_pose_source_args(parser)
    args = parser.parse_args(["--pose-source", "lidar_real", "--lidar-map", str(good)])
    config = lidar_app.pose_source_options(parser, args)
    assert config is not None and config.max_pose_age_s == 0.25
    bench, dock = lidar_app.build_window(None, port="COM9", recording=None, lidar_config=config)
    bench._timer.stop()
    dock.timer.stop()
    lidar_app.apply_pose_source_options(bench, args)
    assert bench.pose_choice() == "lidar_real" and dock.pose_provider is bench.lidar_pose_source
    bench.close()


def test_window_lidar_sim_run_completes_and_export_writes_localization_csv(qapp, no_hardware, tmp_path, monkeypatch):
    window = MainWindow(Session(straight_scenario(), CAR))
    window._timer.stop()
    select(window.combo_drive, DriveMode.VEHICLE_IO.value)
    select(window.combo_pose, "lidar_sim")
    assert window.plan(sync=True).ok
    window.run()
    assert window.session.state == SessionState.RUNNING
    window._refresh_pose_status()
    assert window.lbl_pose_status.text().startswith("MÔ PHỎNG · Định vị LiDAR: OK")
    assert not window.combo_pose.isEnabled() and not window.btn_start_from_lidar.isEnabled()
    for _ in range(300):
        window.advance_by(0.5)
        if not window.session.simulating:
            break
    assert window.session.state == SessionState.COMPLETED, window.session.stop_reason
    out_csv = tmp_path / "lan chay.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out_csv), "CSV (*.csv)"))
    window._export_log()
    folder = tmp_path / "lan chay_vehicle_io"
    for name in ("localization.csv", "tu_the_that_mo_phong.csv", "tu_the_that_mo_phong.json", "poses.csv"):
        assert (folder / name).is_file(), name
    assert window.session.run_link.pose_source.source_id == "lidar_sim_localize"
    window.close()
