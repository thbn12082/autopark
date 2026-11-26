"""Bo ảo QEMU trong thẻ "Bo điều khiển" của giao diện (thêm 02/10/2026; `ui/main_window.py`, `ui/qemu_runner.py`).

Không chạy QEMU, PlatformIO hay cổng thật: `subprocess.Popen` và `serial.Serial` bị thay bằng hàm báo lỗi; cửa sổ dùng
runner thật với bo ảo GIẢ (`tests/qemu_fakes.py`: FirmwareModel sau một client TCP giả, `ManualClock`), luồng nền đồng bộ.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from autopark.application.session import SessionState  # noqa: E402
from autopark.application.vehicle_link import DriveMode  # noqa: E402
from autopark.storage import run_store  # noqa: E402
from autopark.transport.protocol import Command, Fault, State  # noqa: E402
from autopark.transport.qemu_plant import QEMU_EVIDENCE, QEMU_KIND  # noqa: E402
from tests.qemu_fakes import URL, FakeQemuBoard, make_runner  # noqa: E402
from tests.test_session_vehicle import straight_session  # noqa: E402


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def no_launch(monkeypatch):
    """Mọi lần chạy tiến trình con (QEMU, PlatformIO, PowerShell) hay mở cổng serial thật bị ghi lại và từ chối."""
    import subprocess

    import serial

    calls = []

    def refuse(*args, **kwargs):
        calls.append(args)
        raise AssertionError("test không được chạy tiến trình con hay mở cổng thật")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(serial, "Serial", refuse)
    monkeypatch.setattr(run_store, "environment", lambda: {"test": True})
    return calls


@pytest.fixture
def dialogs(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = {"warning": [], "question": []}

    def warning(*args, **kwargs):
        seen["warning"].append(args)
        return QMessageBox.StandardButton.Ok

    def question(*args, **kwargs):
        seen["question"].append(args)
        raise AssertionError("bo ảo QEMU không được hỏi xác nhận kiểu ESP32/DTR")

    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(QMessageBox, "question", question)
    return seen


@pytest.fixture
def window(qapp, scenario, cfg, tmp_path, no_launch, dialogs):
    from autopark.ui.main_window import MainWindow

    w = MainWindow(straight_session(scenario, cfg), None)
    w.sync_dir = tmp_path / "sync"
    board = FakeQemuBoard()
    w.attach_qemu_runner(make_runner(tmp_path, board))
    w.fake_board = board
    yield w
    w.close()


def select(window, key: str) -> None:
    index = window.combo_port.findData(key)
    assert index >= 0, key
    window.combo_port.setCurrentIndex(index)


def set_drive(window, mode: DriveMode) -> None:
    window.combo_drive.setCurrentIndex(window.combo_drive.findData(mode.value))


def start_board(window) -> FakeQemuBoard:
    select(window, "qemu")
    window.btn_qemu.click()
    assert window.qemu_runner.state.value == "RUNNING"
    return window.fake_board


def drive(window, board: FakeQemuBoard, max_steps: int = 3000) -> None:
    for _ in range(max_steps):
        board.advance(20)
        window.advance_by(0.02)
        if not window.session.simulating:
            return
    raise AssertionError(f"Phiên không kết thúc, trạng thái {window.session.state}")


# ---- chọn bo, nút, nhãn --------------------------------------------------------------------------------------------
def test_board_combo_lists_qemu_second_and_selecting_starts_nothing(window, no_launch):
    from autopark.ui.main_window import QEMU_BOARD_LABEL
    combo = window.combo_port
    assert combo.count() == 2 and combo.itemData(1) == "qemu" and combo.itemText(1) == QEMU_BOARD_LABEL
    runner = window.qemu_runner
    assert runner.calls == {"tools": 0, "ensure": 0, "factory": 0}            # dựng cửa sổ không đọc tệp nào
    set_drive(window, DriveMode.VEHICLE_IO)
    select(window, "qemu")
    link = window.session.vehicle_link
    assert link.is_qemu and link.io is None and link.mode == DriveMode.VEHICLE_IO
    assert window.board_port() is None and window.board_key() == "qemu" and window.board_is_qemu()
    assert runner.state.value == "STOPPED" and runner.calls["tools"] == 1      # chỉ đọc thiet_bi.json (giả)
    assert runner.calls["ensure"] == runner.calls["factory"] == 0 and window.fake_board.starts == 0
    window._refresh_ports()                                      # quét lại cổng: vẫn giữ mục bo ảo
    assert window.board_is_qemu() and window.session.vehicle_link is link
    assert no_launch == []


def test_qemu_row_visible_only_when_selected_and_locked_while_running(window):
    assert window.qemu_row.isHidden()
    select(window, "qemu")
    assert not window.qemu_row.isHidden() and window.btn_qemu.isEnabled()
    assert not window.btn_probe.isEnabled()                      # Kiểm kết nối cần bo ảo đang chạy
    board = start_board(window)
    assert window.btn_probe.isEnabled() and window.btn_qemu.text() == "Tắt bo ảo"
    set_drive(window, DriveMode.VEHICLE_IO)
    window.run()
    assert window.session.state == SessionState.RUNNING
    assert not window.btn_qemu.isEnabled() and not window.combo_port.isEnabled() and not window.btn_probe.isEnabled()
    window.stop()
    drive(window, board)
    window.reset()
    assert window.btn_qemu.isEnabled() and window.combo_port.isEnabled() and window.btn_probe.isEnabled()
    select(window, "")
    assert window.qemu_row.isHidden()


def test_start_button_runs_board_and_hint_and_cockpit_tag_say_simulation(window):
    select(window, "qemu")
    hint = window.lbl_board_hint.text()
    assert "KHÔNG phải bo thật" in hint and "XE MÔ PHỎNG" in hint and "mức MP" in hint
    assert window.btn_qemu.text() == "Khởi động bo ảo" and "một lõi CPU" in window.btn_qemu.toolTip()
    assert "Bo ảo: chưa chạy." in window.lbl_qemu.text()
    start_board(window)
    assert window.btn_qemu.text() == "Tắt bo ảo"
    assert f"Bo ảo đang chạy: {URL}" in window.lbl_qemu.text()
    assert window.board_tag.isHidden()                           # nhánh SIM: không có nhãn
    set_drive(window, DriveMode.VEHICLE_IO)
    assert not window.board_tag.isHidden() and window.board_tag.text() == "BO ẢO QEMU · XE MÔ PHỎNG"
    window.btn_qemu.click()                                      # "Tắt bo ảo"
    assert window.qemu_runner.state.value == "STOPPED" and window.fake_board.stops == 1
    assert window.btn_qemu.text() == "Khởi động bo ảo"


def test_unavailable_tools_disable_start_button_with_reason(window, tmp_path):
    window.attach_qemu_runner(make_runner(tmp_path / "khac", FakeQemuBoard(),
                                          tools_error="configs/thiet_bi.json không có \"qemu_xtensa\""))
    select(window, "qemu")
    assert window.qemu_runner.state.value == "UNAVAILABLE" and not window.btn_qemu.isEnabled()
    assert "Máy này chưa cấu hình bo ảo" in window.lbl_qemu.text() and "qemu_xtensa" in window.lbl_qemu.text()


# ---- chạy, từ chối, đổi bo, đóng cửa sổ ----------------------------------------------------------------------------
def test_vehicle_io_run_through_fake_qemu_board_completes_and_exports(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    board = start_board(window)
    set_drive(window, DriveMode.VEHICLE_IO)
    window.run()
    assert window.session.state == SessionState.RUNNING
    status = window.statusBar().currentMessage()
    assert "BO ẢO QEMU" in status and URL in status and "XE MÔ PHỎNG" in status and "không phải bo hay xe thật" in status
    assert window._sync_context(0.0)["note"] == f"VEHICLE_IO, bo ảo QEMU {URL}"
    drive(window, board)
    assert window.session.state == SessionState.COMPLETED, window.session.stop_reason
    assert board.client is None                                  # đóng kết nối sau lần chạy
    out = tmp_path / "xuat" / "lan.csv"
    out.parent.mkdir()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), "CSV (*.csv)"))
    window._export_log()
    info = json.loads((tmp_path / "xuat" / "lan_vehicle_io" / "link.json").read_text(encoding="utf-8"))
    assert info["evidence"] == QEMU_EVIDENCE and info["board"]["kind"] == "qemu" and info["port"] == URL
    bundles = [p for p in out.parent.iterdir() if p.is_dir() and p.name.startswith("lan_2")]
    assert len(bundles) == 1
    manifest = json.loads((bundles[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence"] == QEMU_EVIDENCE


def test_start_refused_dialog_when_board_not_running(window, dialogs):
    select(window, "qemu")
    set_drive(window, DriveMode.VEHICLE_IO)
    window.run()
    assert window.session.state == SessionState.READY and window.session.run_link is None
    title, message = dialogs["warning"][-1][1:3]
    assert title == "Không bắt đầu được" and "Khởi động bo ảo" in message and "bo ảo chưa chạy" in message
    link = window.session.vehicle_link
    assert [r["code"] for r in link.start_refusals] == ["START_NO_QEMU_BOARD"]
    assert window.btn_export.isEnabled() and window.fake_board.opened == 0


def test_switching_to_another_board_stops_the_runner(window):
    board = start_board(window)
    set_drive(window, DriveMode.VEHICLE_IO)
    select(window, "")                                           # về bo mô phỏng
    assert window.qemu_runner.state.value == "STOPPED" and board.stops == 1 and not board.running()
    assert window.statusBar().currentMessage() == "Đã tắt bo ảo QEMU (đã chọn bo khác)"
    assert window.session.vehicle_link._simulated
    record = json.loads((window.qemu_runner.workdir / "bo_ao.json").read_text(encoding="utf-8"))
    assert record["stop_reason"] == "deselect"


def test_close_window_closes_session_before_runner_shutdown(window, monkeypatch):
    board = start_board(window)
    set_drive(window, DriveMode.VEHICLE_IO)
    window.run()
    for _ in range(20):
        board.advance(20)
        window.advance_by(0.02)
    assert board.firmware.state == State.RUNNING
    order = []
    session_close, runner_shutdown = window.session.close, window.qemu_runner.shutdown
    monkeypatch.setattr(window.session, "close", lambda: (order.append("session"), session_close())[1])
    monkeypatch.setattr(window.qemu_runner, "shutdown", lambda: (order.append("runner"), runner_shutdown())[1])
    window.close()
    assert order == ["session", "runner"]
    assert board.firmware.state == State.DISARMED and board.stops == 1 and board.client is None


# ---- kiểm kết nối, xóa lỗi --------------------------------------------------------------------------------------
def test_probe_qemu_uses_board_without_confirmation(window, dialogs):
    select(window, "qemu")
    assert window._probe_board() is None and "Bo ảo chưa chạy" in window.lbl_board_report.text()
    board = start_board(window)
    window.btn_probe.click()
    report = window.last_board_probe
    assert report is not None and report.ok and dialogs["question"] == []
    assert report.kind == QEMU_KIND and report.target == f"bo ảo QEMU {URL}" and report.commands_sent == 0
    assert report.lines()[0].startswith(f"Kiểm kết nối: bo ảo QEMU {URL} — bo ảo QEMU")
    text = window.lbl_board_report.text()
    assert "KHÔNG phải bo thật" in text and "firmware chưa đọc cảm biến" in text and "bo thật qua" not in text
    assert board.client is None and not any(isinstance(m, Command) for m in board.host_messages())


def test_clear_fault_on_qemu_link_has_no_esp32_dialog(window, dialogs):
    select(window, "qemu")
    set_drive(window, DriveMode.VEHICLE_IO)
    assert not window.btn_clear_fault.isEnabled()                # bo ảo chưa chạy
    assert "bo ảo QEMU chưa chạy" in window.btn_clear_fault.toolTip()
    board = start_board(window)
    assert window.btn_clear_fault.isEnabled()
    board.stall(200)                                             # máy bận: firmware chốt LOOP_OVERRUN
    board.advance(20)
    assert board.firmware.fault == Fault.LOOP_OVERRUN
    window.btn_clear_fault.click()
    report = window.last_board_clear
    assert report is not None and report.outcome == "CLEARED" and dialogs["question"] == []
    assert report.target == f"bo ảo QEMU {URL}" and report.kind == QEMU_KIND
    assert "KHÔNG phải bo thật" in window.lbl_board_report.text()
    assert board.firmware.state == State.DISARMED and board.client is None
    link = window.session.vehicle_link
    assert link.board_actions[0]["target"] == f"bo ảo QEMU {URL}"
