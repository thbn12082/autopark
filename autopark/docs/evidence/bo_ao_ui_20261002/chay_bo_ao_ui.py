"""Chạy ỨNG DỤNG (MainWindow của ui.app, offscreen) với bo ảo QEMU THẬT, không người bấm (02/10/2026):
chọn nhánh VehicleIO và mục "Bo ảo QEMU", "Khởi động bo ảo" (build firmware esp32s3_qemu nếu cần), lập đường, "Bắt đầu đỗ",
để vòng 50 Hz của cửa sổ chạy tới khi phiên xong, ghi tóm tắt rồi đóng cửa sổ (Session.close + tắt QEMU).
Không mở cổng COM, camera hay LiDAR nào. Hộp thoại được trả lời tự động (ghi lại). Đây là bo ẢO với xe MÔ PHỎNG phía
laptop, không phải bo hay xe thật.

Dùng: <python> -X utf8 chay_bo_ao_ui.py <kịch bản .json> <tệp kết quả .json> [số lần chạy]"""
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[3]        # thư mục autopark/ (lần chạy 02/10/2026: từ worktree gộp đợt 2)
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from PySide6.QtCore import QEventLoop  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import autopark  # noqa: E402
from autopark.application.session import SessionState  # noqa: E402
from autopark.application.vehicle_link import DriveMode  # noqa: E402
from autopark.ui import app as ui_app  # noqa: E402
from autopark.ui.main_window import QEMU_BOARD_KEY  # noqa: E402
from autopark.ui.qemu_runner import QemuRunnerState  # noqa: E402

DIALOGS = []


def _answer(kind, default):
    def f(*args, **kwargs):
        DIALOGS.append({"kind": kind, "title": str(args[1]) if len(args) > 1 else "",
                        "text": str(args[2])[:400] if len(args) > 2 else ""})
        return default
    return staticmethod(f)


QMessageBox.warning = _answer("warning", QMessageBox.StandardButton.Ok)
QMessageBox.critical = _answer("critical", QMessageBox.StandardButton.Ok)
QMessageBox.information = _answer("information", QMessageBox.StandardButton.Ok)
QMessageBox.question = _answer("question", QMessageBox.StandardButton.Yes)

scenario = Path(sys.argv[1])
out = Path(sys.argv[2])
runs = int(sys.argv[3]) if len(sys.argv) > 3 else 1
qapp = QApplication.instance() or QApplication(sys.argv)
report = {"tool": "chay_bo_ao_ui.py (02/10/2026)", "package": os.path.dirname(autopark.__file__),
          "scenario": str(scenario), "evidence_note": "bo ảo QEMU + xe mô phỏng phía laptop; KHÔNG phải bo hay xe thật",
          "runs": []}


def pump(seconds, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        if until is not None and until():
            return True
        time.sleep(0.002)
    return bool(until is not None and until())


t_start = time.perf_counter()
w = ui_app.build_window(scenario)
w.show()
w.combo_drive.setCurrentIndex(w.combo_drive.findData(DriveMode.VEHICLE_IO.value))
w.combo_port.setCurrentIndex(w.combo_port.findData(QEMU_BOARD_KEY))
pump(0.5)
link = w.session.vehicle_link
report["link_before_start"] = {"is_qemu": bool(getattr(link, "is_qemu", False)),
                               "virtual_board": getattr(link, "virtual_board", None),
                               "hardware_actuators": getattr(link, "hardware_actuators", None)}
runner = w.qemu_runner
report["availability"] = runner.availability()
t0 = time.perf_counter()
started = runner.start()
ok = pump(1200, lambda: runner.state in (QemuRunnerState.RUNNING, QemuRunnerState.FAILED,
                                         QemuRunnerState.UNAVAILABLE, QemuRunnerState.STOPPED))
report["runner"] = {"start_called": started, "state": runner.state.value, "status": runner.status_text(),
                    "seconds_to_ready": round(time.perf_counter() - t0, 1)}
print("bo ảo:", runner.state.value, f"sau {report['runner']['seconds_to_ready']} s", flush=True)
if runner.state == QemuRunnerState.RUNNING:
    for k in range(runs):
        if w.session.state == SessionState.COMPLETED:
            w.session.reset()
        plan = w.plan(sync=True)
        entry = {"plan_ok": bool(plan is not None and plan.ok), "plan_message": getattr(plan, "message", None)}
        if entry["plan_ok"]:
            t_run = time.perf_counter()
            w.run()
            done = pump(240, lambda: w.session.state in (SessionState.COMPLETED, SessionState.STOPPED,
                                                         SessionState.FAULT))
            run_link = w.session.run_link
            desc = run_link.describe() if run_link is not None else {}
            entry.update({
                "finished": done, "state": w.session.state.value, "stop_reason": w.session.stop_reason,
                "wall_s": round(time.perf_counter() - t_run, 2),
                "evidence": desc.get("evidence"), "io": desc.get("io"), "pose_source": desc.get("pose_source"),
                "virtual_board": desc.get("virtual_board"), "board": desc.get("board"),
                "start_refusals": getattr(run_link, "refused_starts", None) if run_link is not None else None,
                "events": [r.get("code") for r in (getattr(run_link, "event_rows", None) or [])][-15:],
            })
        report["runs"].append(entry)
        print(f"lần {k + 1}:", {k2: entry.get(k2) for k2 in ("plan_ok", "state", "stop_reason", "wall_s", "evidence")},
              flush=True)
        pump(1.0)
report["dialogs"] = DIALOGS
t_close = time.perf_counter()
w.close()
pump(10, lambda: runner.state in (QemuRunnerState.STOPPED, QemuRunnerState.FAILED, QemuRunnerState.UNAVAILABLE))
report["close"] = {"runner_state": runner.state.value, "seconds": round(time.perf_counter() - t_close, 2)}
report["total_s"] = round(time.perf_counter() - t_start, 1)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("đã ghi", out, flush=True)
