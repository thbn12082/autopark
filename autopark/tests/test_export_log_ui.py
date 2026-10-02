""""Xuất log CSV…" / "Lưu phiên…" của cockpit (`MainWindow._export_log`), sửa sau review 02/10/2026.

- Review 7/19: khi lần chạy còn mở (RUNNING/STOPPING), xuất log không gọi `export_run` (PowerShell, nén mã nguồn,
  ≈ 1,4 s trên luồng giao diện, cũng là luồng của vòng điều khiển 50 Hz); CSV và thư mục `_vehicle_io` vẫn ghi. Hai nút
  bị khóa trong lúc đó; lời gọi thẳng vẫn được chặn (lớp phòng thủ thứ hai).
- Review 26: START bị từ chối qua VehicleIO khi liên kết chưa chạy lần nào (ví dụ `--max-cusps`, dòng
  START_TOO_MANY_CUSPS là bằng chứng GD2) xuất được: nút bật, thư mục `_vehicle_io` có `start_refusals.csv`.

Không phần cứng: bo mô phỏng của giao diện (không mở cổng COM nào; `serial.Serial` bị thay bằng hàm từ chối), không cửa sổ
thật (offscreen), `run_store.environment` thay bằng hàm rỗng (không gọi PowerShell)."""
import csv
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from autopark.application.cusp_policy import CuspPolicy  # noqa: E402
from autopark.application.session import SessionState  # noqa: E402
from autopark.application.vehicle_link import BOARD_ACTION_FIELDS, DriveMode  # noqa: E402
from autopark.storage import run_store  # noqa: E402
from tests.test_cusp_policy import apply_path  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def no_hardware(monkeypatch):
    """Không cổng COM thật, không PowerShell; ghi lại mỗi lần export_run được gọi."""
    import serial

    def refuse(*args, **kwargs):
        raise AssertionError("test không được mở cổng thật")

    monkeypatch.setattr(serial, "Serial", refuse)
    monkeypatch.setattr(serial, "serial_for_url", refuse)
    monkeypatch.setattr(run_store, "environment", lambda: {"stub": True})
    calls = []
    real_export = run_store.export_run

    def export_run(session, directory):
        calls.append(session.state)
        return real_export(session, directory)

    monkeypatch.setattr(run_store, "export_run", export_run)
    return calls


@pytest.fixture
def window(qapp, tmp_path, no_hardware):
    from autopark.ui.app import DEFAULT_SCENARIO, build_window

    w = build_window(DEFAULT_SCENARIO, cusp_policy=CuspPolicy(max_cusps=1))
    w._timer.stop()
    w.sync_dir = tmp_path / "sync"
    yield w
    w.close()


def save_to(monkeypatch, path):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), "CSV (*.csv)"))


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def drive_to_rest(window, dt=0.1, steps=600):
    for _ in range(steps):
        window.advance_by(dt)
        window._poll_state_change()
        if not window.session.simulating:
            return


@pytest.mark.parametrize("mode", [DriveMode.SIM, DriveMode.VEHICLE_IO])
def test_export_while_the_run_is_open_skips_only_the_replay_package(window, tmp_path, monkeypatch, no_hardware, mode):
    """Review 7/19: trước đây bấm "Lưu phiên…" giữa lần chạy qua VehicleIO chặn luồng điều khiển ≈ 1,46 s (export_run)
    và gói tả một lần chạy chưa xong (result.json RUNNING)."""
    combo = window.combo_drive
    combo.setCurrentIndex(combo.findData(mode.value))
    window.session.cusp_policy = CuspPolicy()                           # đường mặc định không bị chặn
    assert window.plan(sync=True).ok
    window._poll_state_change()
    window.run()
    window._poll_state_change()
    window.advance_by(0.5)
    assert window.session.state == SessionState.RUNNING and len(window.session.log) > 0
    out = tmp_path / "log"
    save_to(monkeypatch, out / "giua.csv")
    window._export_log()                                                # lời gọi thẳng (nút đã khóa, xem dưới)
    assert no_hardware == [] and window.session.state == SessionState.RUNNING      # không đóng gói giữa lần chạy
    assert (out / "giua.csv").exists() and len(read_rows(out / "giua.csv")) == len(window.session.log)
    folders = sorted(p.name for p in out.iterdir() if p.is_dir())
    vehicle_io = mode == DriveMode.VEHICLE_IO
    assert folders == (["giua_vehicle_io"] if vehicle_io else [])      # _vehicle_io vẫn ghi như trước T9
    if vehicle_io:
        assert (out / "giua_vehicle_io" / "commands.csv").exists()
    message = window.statusBar().currentMessage()
    assert "KHÔNG xuất gói phát lại: lần chạy chưa kết thúc" in message and ("_vehicle_io" in message) == vehicle_io
    window.advance_by(0.1)                                              # mỗi nhịp làm mới nút: vẫn khóa
    for button in (window.btn_export, window.btn_save_run):            # khóa trong lúc chạy, "Lưu phiên…" vẫn hiện
        assert not button.isEnabled() and "xe dừng" in button.toolTip()
    assert not window.btn_save_run.isHidden()

    window.stop()
    window._poll_state_change()
    assert window.session.state == SessionState.STOPPING and not window.btn_export.isEnabled()
    drive_to_rest(window)
    assert window.session.state == SessionState.STOPPED
    assert window.btn_export.isEnabled() and window.btn_save_run.isEnabled() and window.btn_export.toolTip() == ""
    save_to(monkeypatch, out / "sau.csv")
    window.btn_save_run.click()                                         # xe đã dừng: gói phát lại như cũ
    assert no_hardware == [SessionState.STOPPED]
    packages = [p for p in out.iterdir() if p.is_dir() and p.name.startswith("sau_") and p.name != "sau_vehicle_io"]
    assert len(packages) == 1
    result = json.loads((packages[0] / "result.json").read_text(encoding="utf-8"))
    assert result["state"] == "STOPPED"


def test_refused_start_without_any_run_is_exported_with_the_link_logs(window, tmp_path, monkeypatch, no_hardware):
    """Review 26 (cách 1): trước đây nút Xuất log khóa khi log phiên rỗng và chỉ ghi log VehicleLink cùng một lần chạy
    qua VehicleIO, nên dòng START_TOO_MANY_CUSPS (bằng chứng GD2 của DI-2 (b)) không xuất được từ giao diện."""
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))
    combo = window.combo_drive
    combo.setCurrentIndex(combo.findData(DriveMode.VEHICLE_IO.value))
    s = window.session
    window._after_plan(apply_path(s, 2))                                # 2 lần đổi chiều > --max-cusps 1
    assert s.state == SessionState.READY and len(s.log) == 0
    assert not window.btn_export.isEnabled() and window.btn_save_run.isHidden()
    window.run()
    assert len(warnings) == 1 and "2 lần đổi chiều" in warnings[0][2] and s.state == SessionState.READY
    link = s.vehicle_link
    assert link.runs == 0 and link.refused_starts == 1 and link.io is None      # chưa dựng bo, chưa I/O nào
    assert window.btn_export.isEnabled() and not window.btn_save_run.isHidden()  # bật ngay, không đợi nhịp sau
    out = tmp_path / "tu_choi.csv"
    save_to(monkeypatch, out)
    window._export_log()
    refusals = read_rows(tmp_path / "tu_choi_vehicle_io" / "start_refusals.csv")
    assert [(r["code"], r["source"], r["handling"]) for r in refusals] == [("START_TOO_MANY_CUSPS", "session",
                                                                           "before_start")]
    assert read_rows(tmp_path / "tu_choi_vehicle_io" / "commands.csv") == []    # không lẫn log lần chạy nào
    info = json.loads((tmp_path / "tu_choi_vehicle_io" / "link.json").read_text(encoding="utf-8"))
    assert info["runs"] == 0 and info["refused_starts"] == 1
    assert out.exists() and read_rows(out) == [] and no_hardware == []          # log phiên rỗng, không gói phát lại
    message = window.statusBar().currentMessage()
    assert "Đã ghi 0 dòng" in message and "1 lần START bị từ chối" in message and "chưa chạy lần nào" in message

    # Liên kết đã chạy một lần: dòng từ chối xuất cùng log của lần chạy đó (như trước); sau lái tay thì log lái tay
    # không kèm log VehicleIO cũ, kể cả khi liên kết có dòng từ chối.
    s.cusp_policy = CuspPolicy(max_cusps=2)
    window.run()
    assert s.state == SessionState.RUNNING and link.runs == 1
    drive_to_rest(window, dt=0.5)
    save_to(monkeypatch, tmp_path / "chay.csv")
    window._export_log()
    refusals = read_rows(tmp_path / "chay_vehicle_io" / "start_refusals.csv")
    assert [r["code"] for r in refusals] == ["START_TOO_MANY_CUSPS"]
    window.reset()
    window._start_manual()
    assert s.state == SessionState.MANUAL and len(warnings) == 1
    window.advance_by(0.5)
    window.stop()
    assert link.start_refusals and link.runs == 1 and window.btn_export.isEnabled()
    save_to(monkeypatch, tmp_path / "lai_tay.csv")
    window._export_log()
    assert (tmp_path / "lai_tay.csv").exists() and not (tmp_path / "lai_tay_vehicle_io").exists()


def test_board_action_rows_alone_also_enable_the_export(window):
    """T15: lần bấm "Xóa lỗi bo" của liên kết chưa chạy (board_actions.csv) cũng chỉ liên kết đó giữ."""
    combo = window.combo_drive
    combo.setCurrentIndex(combo.findData(DriveMode.OBSERVE.value))
    link = window.session.vehicle_link
    assert window._refusal_link() is None and not window.btn_export.isEnabled()
    link.board_actions.append(dict.fromkeys(BOARD_ACTION_FIELDS, ""))
    window._refresh_export_buttons()
    assert window._refusal_link() is link and window.btn_export.isEnabled()
    combo.setCurrentIndex(combo.findData(DriveMode.SIM.value))         # nhánh SIM: không có liên kết nào
    assert window._refusal_link() is None and not window.btn_export.isEnabled()
