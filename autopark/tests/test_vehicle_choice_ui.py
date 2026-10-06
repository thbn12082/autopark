"""Ô "Cấu hình xe", cờ --vehicle-config của run_app.py và bo mô phỏng chọn theo tệp xe (thêm 02/10/2026; người dùng
giao quyết định 02/10/2026 ('làm hết'): xe nghiệm thu configs/vehicle_nghiem_thu.json, 0,10 m/s, tệp mặc định không đổi;
N-V1 vẫn ĐỀ XUẤT – CHỜ CHỐT).

Offscreen, không mở cổng nào: `serial.Serial` bị thay bằng hàm từ chối và `serial.tools.list_ports.comports` trả danh
sách giả (như tests/test_vehicle_board_ui.py). Chỉ bo mô phỏng (SimVehicleIO + FirmwareModel); tệp ghi trong tmp_path.
"""
import os
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from autopark.application.session import SessionState  # noqa: E402
from autopark.application.vehicle_link import DriveMode  # noqa: E402
from autopark.storage.scenario_store import (ACCEPTANCE_VEHICLE_CONFIG, CONFIGS_DIR,  # noqa: E402
                                            DEFAULT_VEHICLE_CONFIG, load_scenario, path_key)
from tests.conftest import PROJECT_ROOT  # noqa: E402

BAI_DO_XE = PROJECT_ROOT / "scenarios" / "bai_do_xe.json"
ACC_KEY, DEFAULT_KEY = path_key(ACCEPTANCE_VEHICLE_CONFIG), path_key(DEFAULT_VEHICLE_CONFIG)


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def no_serial_open(monkeypatch):
    """Mọi lần mở cổng thật bị ghi lại và từ chối."""
    import serial
    opened = []

    def refuse(*args, **kwargs):
        opened.append(args)
        raise AssertionError("test không được mở cổng thật")

    monkeypatch.setattr(serial, "Serial", refuse)
    return opened


@pytest.fixture
def ports(monkeypatch):
    from serial.tools import list_ports
    monkeypatch.setattr(list_ports, "comports", lambda: [])


@pytest.fixture
def dialogs(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = {"warning": [], "question": [], "critical": [], "answer": QMessageBox.StandardButton.Yes}

    def record(kind, answer=None):
        def show(*args, **kwargs):
            seen[kind].append(args)
            return seen["answer"] if answer is None else answer
        return show

    monkeypatch.setattr(QMessageBox, "warning", record("warning", QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "critical", record("critical", QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "question", record("question"))
    return seen


def open_dialog(monkeypatch, path):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "JSON (*.json)")))


def stop_and_wait(window) -> None:
    window.stop()
    for _ in range(100):
        window.advance_by(0.1)
        if not window.session.simulating:
            break


def test_run_app_vehicle_config_arg(tmp_path, capsys, monkeypatch):
    from autopark.ui import app
    args = app.parse_args(["run_app.py", str(BAI_DO_XE), "--vehicle-config", str(ACCEPTANCE_VEHICLE_CONFIG)])
    assert args.vehicle_config.path == ACCEPTANCE_VEHICLE_CONFIG and args.scenario == BAI_DO_XE
    assert args.vehicle_config.cfg.max_speed == pytest.approx(0.10) and len(args.vehicle_config.sha256) == 64
    assert app.parse_args(["run_app.py"]).vehicle_config is None

    def must_not_open(*args, **kwargs):
        raise AssertionError("không được mở cửa sổ khi tệp xe hỏng")

    monkeypatch.setattr(app, "build_window", must_not_open)
    bad = tmp_path / "hong.json"
    bad.write_text('{"name": "thieu_khoa"}', encoding="utf-8")
    with pytest.raises(SystemExit) as info:
        app.main(["run_app.py", "--vehicle-config", str(bad)])
    assert info.value.code == 2 and "thiếu khóa" in capsys.readouterr().err
    with pytest.raises(SystemExit) as info:
        app.main(["run_app.py", "--vehicle-config", str(tmp_path / "khong_co.json")])
    assert info.value.code == 2 and "không thấy tệp cấu hình xe" in capsys.readouterr().err


def test_window_acceptance_vehicle_pairs_board_and_starts(qapp, ports, no_serial_open, dialogs):
    from autopark.ui.app import build_window
    window = build_window(BAI_DO_XE, vehicle_config=ACCEPTANCE_VEHICLE_CONFIG)
    session = window.session
    try:
        assert session.cfg.max_speed == pytest.approx(0.10) and window.vehicle_override.path == ACCEPTANCE_VEHICLE_CONFIG
        assert session.scenario.vehicle_config_path == ACCEPTANCE_VEHICLE_CONFIG
        text = window.lbl_vehicle.text()
        assert "xe_nghiem_thu_gia_dinh" in text and "(vehicle_nghiem_thu.json)" in text and "0.10 m/s" in text
        assert window.combo_vehicle.currentData() == ACC_KEY
        assert window.combo_vehicle.currentText() == "vehicle_nghiem_thu.json — tối đa 0.10 m/s"
        hint = window.lbl_board_hint.text()
        assert "theo vehicle_io_sim_nghiem_thu.json (khớp tệp xe vehicle_nghiem_thu.json)" in hint
        assert "không dùng với bo mô phỏng" in hint
        report = window._probe_board()                              # "Kiểm kết nối bo" trên bo mô phỏng ghép đúng
        assert report.ok and report.limits.ok and dialogs["question"] == []
        window.combo_drive.setCurrentIndex(window.combo_drive.findData(DriveMode.VEHICLE_IO.value))
        assert session.vehicle_link.sim_config.firmware.max_speed_mm_s == 100
        assert window.plan(sync=True).ok
        window.run()
        assert session.state == SessionState.RUNNING and dialogs["warning"] == []
        assert session.run_link.limits_check.ok and window.instrument.full_scale_mps == pytest.approx(0.10)
        stop_and_wait(window)
        assert session.state == SessionState.STOPPED
        window.reset()
        assert no_serial_open == []
    finally:
        window.close()


def test_vehicle_combo_switch_invalidates_pins_and_follows_open(qapp, ports, no_serial_open, dialogs, monkeypatch,
                                                                 tmp_path):
    from autopark.ui.app import DEFAULT_SCENARIO, build_window
    window = build_window(DEFAULT_SCENARIO)
    session = window.session
    combo = window.combo_vehicle
    try:
        assert window.vehicle_override is None and combo.currentData() == DEFAULT_KEY
        assert [combo.itemData(i) for i in range(2)] == [DEFAULT_KEY, ACC_KEY]   # mặc định trước, nghiệm thu sau
        window.combo_drive.setCurrentIndex(window.combo_drive.findData(DriveMode.VEHICLE_IO.value))
        link = session.vehicle_link
        assert link.sim_config.firmware.max_speed_mm_s == 300
        assert window.plan(sync=True).ok and session.state == SessionState.READY
        combo.setCurrentIndex(combo.findData(ACC_KEY))
        assert session.state == SessionState.EDITING and session.trajectory is None
        assert session.cfg.max_speed == pytest.approx(0.10) and window.vehicle_override.path == ACCEPTANCE_VEHICLE_CONFIG
        assert session.scenario.vehicle_config_path == ACCEPTANCE_VEHICLE_CONFIG
        assert session.vehicle_link is link and link.sim_config.firmware.max_speed_mm_s == 100   # cùng liên kết, bo mới
        assert "vehicle_io_sim_nghiem_thu.json" in window.lbl_board_hint.text()
        assert window.statusBar().currentMessage().startswith("Đã chọn xe xe_nghiem_thu_gia_dinh (vehicle_nghiem_thu.json)")
        assert dialogs["question"] == [] and dialogs["warning"] == []              # chưa có log: không hỏi
        # "Mở…" kịch bản khác: giữ xe đã chọn, không đọc tệp xe của kịch bản
        opened = PROJECT_ROOT / "scenarios" / "sa_ban_3x2_hai_hop.json"
        open_dialog(monkeypatch, opened)
        window._open_scenario()
        assert window.scenario_path == opened and session.scenario.name == load_scenario(opened).name
        assert session.cfg.max_speed == pytest.approx(0.10)
        assert session.scenario.vehicle_config_path == ACCEPTANCE_VEHICLE_CONFIG
        assert "xe theo vehicle_nghiem_thu.json" in window.statusBar().currentMessage()
        assert combo.currentData() == ACC_KEY and link.sim_config.firmware.max_speed_mm_s == 100
        # Lưu ghi tệp xe đang dùng vào kịch bản (bản sao trong tmp_path; không ghi đè scenarios/*.json)
        window.scenario_path = tmp_path / "ban_sao.json"
        window._save_scenario()
        assert window.statusBar().currentMessage().endswith("(xe: vehicle_nghiem_thu.json)")
        assert load_scenario(tmp_path / "ban_sao.json").vehicle_config_path == ACCEPTANCE_VEHICLE_CONFIG
        # Về xe mặc định: bo mô phỏng 300 mm/s lại, xe mặc định cũng được giữ
        combo.setCurrentIndex(combo.findData(DEFAULT_KEY))
        assert session.cfg.max_speed == pytest.approx(0.3) and link.sim_config.firmware.max_speed_mm_s == 300
        assert window.vehicle_override.path == DEFAULT_VEHICLE_CONFIG and dialogs["critical"] == []
    finally:
        window.close()


def test_vehicle_combo_locked_while_running_and_confirms_log_drop(qapp, ports, no_serial_open, dialogs):
    from PySide6.QtWidgets import QMessageBox
    from autopark.ui.app import DEFAULT_SCENARIO, build_window
    window = build_window(DEFAULT_SCENARIO)
    session = window.session
    combo = window.combo_vehicle
    acc_index = combo.findData(ACC_KEY)
    try:
        assert window.plan(sync=True).ok
        window.run()                                                 # nhánh SIM giai đoạn 0
        assert session.state == SessionState.RUNNING
        window._refresh_mode_widgets()
        assert not combo.isEnabled()
        combo.setCurrentIndex(acc_index)                             # gọi thẳng khi đang chạy: không đổi gì
        assert session.cfg.max_speed == pytest.approx(0.3) and combo.currentData() == DEFAULT_KEY
        assert "Chỉ đổi xe khi đang chỉnh hoặc sẵn sàng" in window.statusBar().currentMessage()
        window.advance_by(0.5)
        stop_and_wait(window)
        window.reset()
        assert session.state == SessionState.READY and len(session.log) > 0 and combo.isEnabled()
        dialogs["answer"] = QMessageBox.StandardButton.No
        combo.setCurrentIndex(acc_index)
        assert len(dialogs["question"]) == 1 and "vehicle_nghiem_thu.json" in dialogs["question"][0][2]
        assert session.cfg.max_speed == pytest.approx(0.3) and len(session.log) > 0
        assert session.state == SessionState.READY and combo.currentData() == DEFAULT_KEY
        dialogs["answer"] = QMessageBox.StandardButton.Yes
        combo.setCurrentIndex(acc_index)
        assert len(dialogs["question"]) == 2 and session.cfg.max_speed == pytest.approx(0.10)
        assert len(session.log) == 0 and session.state == SessionState.EDITING and combo.currentData() == ACC_KEY
    finally:
        window.close()


def test_acceptance_vehicle_without_paired_board_refuses_start(qapp, ports, no_serial_open, dialogs, monkeypatch,
                                                               tmp_path):
    """Thư mục cấu hình không có bo nào trỏ xe nghiệm thu: dùng bo mặc định (300 mm/s), gợi ý nói rõ, và START ở
    VehicleIO bị LIMITS_MISMATCH từ chối (việc chọn bo không nới kiểm tra nào)."""
    from autopark.ui import main_window
    from autopark.ui.app import build_window
    folder = tmp_path / "configs"
    folder.mkdir()
    shutil.copy(CONFIGS_DIR / "vehicle_io_sim.json", folder)
    shutil.copy(DEFAULT_VEHICLE_CONFIG, folder)
    monkeypatch.setattr(main_window, "CONFIGS_DIR", folder)
    window = build_window(BAI_DO_XE, vehicle_config=ACCEPTANCE_VEHICLE_CONFIG)
    session = window.session
    try:
        hint = window.lbl_board_hint.text()
        assert "không có tệp vehicle_io_sim*.json nào có vehicle_config trỏ vehicle_nghiem_thu.json" in hint
        assert "TỪ CHỐI (LIMITS_MISMATCH)" in hint
        assert window.combo_vehicle.currentText().startswith("vehicle_nghiem_thu.json (ngoài configs/)")
        window.combo_drive.setCurrentIndex(window.combo_drive.findData(DriveMode.VEHICLE_IO.value))
        link = session.vehicle_link
        assert link.sim_config.firmware.max_speed_mm_s == 300
        assert window.plan(sync=True).ok
        window.run()
        assert session.state == SessionState.READY and session.run_link is None
        title, message = dialogs["warning"][-1][1:3]
        assert title == "Không bắt đầu được" and "Giới hạn của bo" in message and "tốc độ lớn nhất" in message
        assert ("LIMITS_MISMATCH", "STOP") in [(r["code"], r["action"]) for r in link.start_refusals]
        assert no_serial_open == []
    finally:
        window.close()
