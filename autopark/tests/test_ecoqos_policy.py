"""Ứng dụng và công cụ tự tắt EcoQoS cho chính tiến trình của mình (02/10/2026, người dùng giao quyết định 02/10/2026;
`autopark/power_throttling.py`, `autopark/ui/process_status.py`; vì sao: docs/CHUYEN_MAY_BAN.md mục 10).

Mọi test đổi AUTOPARK_KEEP_ECOQOS đều thay lớp Win32 bằng hàm giả (`win32`), để trạng thái thật của tiến trình pytest
(tests/conftest.py, kiểm ở tests/test_power_throttling.py) không bao giờ bị đổi. Không mở thiết bị; cửa sổ chỉ
offscreen.
"""
import ast
from concurrent.futures import Future
import importlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

# evaluation/render.py đặt QT_QPA_PLATFORM="windows" lúc nhập nếu chưa có: đặt offscreen TRƯỚC mọi lần nhập
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QStatusBar  # noqa: E402

from autopark import power_throttling  # noqa: E402
from autopark.power_throttling import (KEEP_ECOQOS_ENV, EcoQoSPolicy, apply_ecoqos_policy,  # noqa: E402
                                       ecoqos_state, keep_ecoqos_requested)
from autopark.ui import theme  # noqa: E402
from autopark.ui.process_status import LABEL_NAME, WARNING_MS, add_ecoqos_label  # noqa: E402

PACKAGE = Path(power_throttling.__file__).resolve().parent
TESTS = Path(__file__).resolve().parent
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="EcoQoS chỉ có trên Windows")

# Điểm vào có hành vi thời gian thực: mở thiết bị chạy liên tục, chạy theo hạn giờ đồng hồ thật, hay ghi số đo thời gian
# để so với ngân sách thời gian thực. Tên thành phần truyền cho apply_ecoqos_policy = tên mô-đun dưới autopark/.
INCLUDED = (
    "ui.app", "ui.lidar_app", "ui.rig_app", "ui.calib_app", "ui.roi_app", "lidar.live_view",
    "rig.bench", "rig.may_moi", "video.camera_bench", "lidar.bench", "lidar.rplidar_c1", "lidar.scan_odometry",
    "lidar.localize", "fusion.demo", "transport.qemu_board",
    "evaluation.bench", "evaluation.compare", "evaluation.render", "evaluation.hard_cases", "evaluation.phase0",
    "evaluation.robustness", "evaluation.sensitivity", "evaluation.fault_drill",
    "perception.bev", "perception.export_onnx",
    "ui.overhead_app", "video.overhead_record",
)
OFFLINE = "ngoại tuyến, không chạy theo đồng hồ thật"
EXCLUDED = {
    "evaluation.ecoqos_gui": "công cụ đo EcoQoS tự đặt EcoQoS theo từng biến thể (gui_system phải là mặc định Windows)",
    "evaluation.score_run": OFFLINE, "evaluation.replay": "phát lại không chạy theo đồng hồ thật",
    "evaluation.dataset_audit": OFFLINE,
    "evaluation.acceptance_scenarios": "sinh tệp sa bàn nghiệm thu, không chạy planner (thêm 02/10/2026)",
    "evaluation.overhead_ref": "tính tham chiếu R1 từ video đã ghi (T4)", "lidar.map_builder": OFFLINE,
    "lidar.pose_estimator": "định vị lại một bản ghi, không theo đồng hồ thật (T2)",
    "perception.aruco_sheet": "in tờ ArUco (T4)",
    "ui.label_app": "gán nhãn ảnh tĩnh",
    "lidar.viewer": "chỉ xem lại bản ghi DROW", "lidar.repeatability": OFFLINE, "lidar.occupancy": OFFLINE,
    "perception.costmap": OFFLINE, "perception.calib_board": OFFLINE, "perception.fisheye_calib": OFFLINE,
    "perception.extrinsics_calib": OFFLINE, "perception.roi": OFFLINE, "perception.roi_tool": OFFLINE,
    "perception.evaluate": OFFLINE, "perception.evaluate_external": OFFLINE, "perception.labels": OFFLINE,
    "perception.prepare": OFFLINE, "perception.prepare_extra": OFFLINE, "perception.verify_cache": OFFLINE,
    "perception.predict": OFFLINE,
    "perception.benchmark": "đo GPU cho huấn luyện, không phải ngân sách thời gian thực",
    "perception.train": "huấn luyện, không phải ngân sách thời gian thực",
    "transport.vectors": "sinh vector thử",
}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win32(monkeypatch):
    """Lớp Win32 giả: ghi pid của mỗi lần tắt (None = chính tiến trình), trả trạng thái đặt sẵn. Biến môi trường bị xóa
    (mặc định = tắt EcoQoS); test nào cần thì đặt lại."""
    fake = SimpleNamespace(disable_calls=[], disable_result=True, disable_error=None, state="off", read_error=None)

    def disable(pid=None):
        fake.disable_calls.append(pid)
        if fake.disable_error is not None:
            raise fake.disable_error
        return fake.disable_result

    def read(pid=None):
        if fake.read_error is not None:
            raise fake.read_error
        return fake.state

    monkeypatch.setattr(power_throttling, "disable_power_throttling", disable)
    monkeypatch.setattr(power_throttling, "execution_speed_throttling", read)
    monkeypatch.delenv(KEEP_ECOQOS_ENV, raising=False)
    return fake


# ---------------------------------------------------------------- hàm dùng chung

def test_policy_disables_by_default_and_reads_back(win32):
    policy = apply_ecoqos_policy("thu")
    assert (policy.component, policy.request, policy.set_ok, policy.state) == ("thu", "disable", True, "off")
    assert policy.windows == (sys.platform == "win32")
    assert policy.level == "ok" and policy.short_vi() == "EcoQoS: tắt"
    assert win32.disable_calls == [None]                       # chính tiến trình này, không theo pid
    assert keep_ecoqos_requested() is False


def test_env_1_keeps_windows_default_without_calling_win32(win32, monkeypatch):
    monkeypatch.setenv(KEEP_ECOQOS_ENV, "1")
    win32.state = "system"
    policy = apply_ecoqos_policy("thu")
    assert win32.disable_calls == []
    assert (policy.request, policy.set_ok, policy.state) == ("keep", None, "system")
    assert policy.level == "warn" and keep_ecoqos_requested() is True
    assert "AUTOPARK_KEEP_ECOQOS=1" in policy.short_vi() and "AUTOPARK_KEEP_ECOQOS=1" in policy.cli_line()


@pytest.mark.parametrize("value", ["0", "", "true", "yes", " 1"])
def test_only_exact_1_keeps(win32, monkeypatch, value):
    """Cùng quy tắc với tests/conftest.py: chỉ đúng chuỗi "1" mới giữ mặc định của Windows."""
    monkeypatch.setenv(KEEP_ECOQOS_ENV, value)
    assert keep_ecoqos_requested() is False
    assert apply_ecoqos_policy("thu").request == "disable" and win32.disable_calls == [None]


def test_failures_are_reported_never_raised(win32, monkeypatch):
    monkeypatch.setattr(power_throttling.sys, "platform", "win32")      # "danger" chỉ có trên Windows
    win32.disable_result, win32.state = False, "system"
    policy = apply_ecoqos_policy("thu")
    assert policy.set_ok is False and policy.level == "danger"
    assert policy.short_vi() == "EcoQoS: KHÔNG tắt được (Windows báo: system)"
    win32.disable_result, win32.disable_error = True, OSError("SetProcessInformation hỏng")
    policy = apply_ecoqos_policy("thu")
    assert policy.set_ok is False and policy.level == "danger" and "KHÔNG tắt được" in policy.short_vi()
    win32.disable_error, win32.read_error = None, OSError("GetProcessInformation hỏng")
    assert ecoqos_state() == "unknown" and ecoqos_state(1234) == "unknown"
    policy = apply_ecoqos_policy("thu")                 # tắt được nhưng không đọc lại được: Windows trước bản 22000
    assert (policy.set_ok, policy.state, policy.level) == (True, "unknown", "info")
    assert policy.short_vi() == "EcoQoS: đã yêu cầu tắt (không đọc lại được)"
    win32.read_error, win32.state = None, None          # execution_speed_throttling trả None
    assert ecoqos_state() == "unknown"


def test_off_windows_policy_is_inert(monkeypatch, qapp):
    monkeypatch.setattr(power_throttling.sys, "platform", "linux")
    monkeypatch.delenv(KEEP_ECOQOS_ENV, raising=False)
    policy = apply_ecoqos_policy("thu")                 # hàm Win32 thật: ngoài Windows chúng không làm gì
    monkeypatch.undo()                                  # trả sys.platform trước khi đụng tới Qt
    assert (policy.state, policy.windows, policy.set_ok, policy.level) == ("unknown", False, False, "info")
    assert policy.short_vi() == "EcoQoS: không áp dụng (không phải Windows)"
    window = QMainWindow()
    try:
        assert add_ecoqos_label(window, policy) is None
        assert window.findChild(QLabel, LABEL_NAME) is None
    finally:
        window.deleteLater()


POLICIES = {
    "ok": EcoQoSPolicy("thu", "disable", True, "off", True),
    "warn": EcoQoSPolicy("thu", "keep", None, "system", True),
    "danger": EcoQoSPolicy("thu", "disable", False, "on", True),
    "info": EcoQoSPolicy("thu", "disable", True, "unknown", True),
    "off_windows": EcoQoSPolicy("thu", "disable", False, "unknown", False),
}


def test_vietnamese_texts_per_level():
    assert {name: p.level for name, p in POLICIES.items()} == {
        "ok": "ok", "warn": "warn", "danger": "danger", "info": "info", "off_windows": "info"}
    assert [p.short_vi() for p in POLICIES.values()] == [
        "EcoQoS: tắt", "EcoQoS: Windows tự quyết (AUTOPARK_KEEP_ECOQOS=1)", "EcoQoS: KHÔNG tắt được (Windows báo: on)",
        "EcoQoS: đã yêu cầu tắt (không đọc lại được)", "EcoQoS: không áp dụng (không phải Windows)"]
    for name, policy in POLICIES.items():
        text = policy.explain_vi()
        assert "uturn_w46" in text and "docs/CHUYEN_MAY_BAN.md mục 10" in text, name
        assert ("AUTOPARK_KEEP_ECOQOS" in text) == (name in ("ok", "warn")), name
        assert ("Đừng thu nhỏ cửa sổ" in text) == (name in ("warn", "danger")), name
        assert policy.cli_line().startswith("CẢNH BÁO") == (name == "danger"), name
    assert POLICIES["ok"].cli_line() == ("EcoQoS của tiến trình: off (đã tự tắt; AUTOPARK_KEEP_ECOQOS=1 để giữ mặc "
                                         "định của Windows)")
    assert POLICIES["warn"].cli_line() == ("EcoQoS của tiến trình: system (giữ mặc định của Windows theo "
                                           "AUTOPARK_KEEP_ECOQOS=1)")
    assert "(Windows báo: on)" in POLICIES["danger"].cli_line() and "(đọc lại: on)" in POLICIES["danger"].explain_vi()
    assert POLICIES["info"].cli_line() == "EcoQoS của tiến trình: unknown (không đọc được hoặc không phải Windows)"


# ---------------------------------------------------------------- điểm vào: kiểm tĩnh trên mã nguồn

def _source(module: str) -> str:
    return (PACKAGE / Path(*module.split("."))).with_suffix(".py").read_text(encoding="utf-8")


def _top_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    return next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name), None)


def _func_name(node) -> str | None:
    return node.id if isinstance(node, ast.Name) else (node.attr if isinstance(node, ast.Attribute) else None)


def _calls(node, name: str) -> list[ast.Call]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Call) and _func_name(n.func) == name]


@pytest.mark.parametrize("module", INCLUDED)
def test_every_realtime_entry_point_calls_the_policy_first(module):
    """Câu lệnh đầu tiên của main() (sau docstring và các lệnh nhập cục bộ) là apply_ecoqos_policy("<mô-đun>"): trước
    argparse, trước Qt, trước mọi thiết bị hay tệp."""
    main = _top_function(ast.parse(_source(module)), "main")
    body = list(main.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body.pop(0)                                         # docstring
    while body and isinstance(body[0], (ast.Import, ast.ImportFrom)):
        body.pop(0)
    first = body[0]
    assert isinstance(first, (ast.Assign, ast.Expr)), ast.dump(first)
    call = first.value.value if isinstance(first.value, ast.Attribute) else first.value    # fault_drill: (...).state
    assert isinstance(call, ast.Call) and _func_name(call.func) == "apply_ecoqos_policy", ast.dump(first)
    assert [arg.value for arg in call.args] == [module] and not call.keywords


def test_every_main_is_classified():
    """Mọi `def main` cấp mô-đun dưới autopark/ được xếp vào INCLUDED hoặc EXCLUDED (không trùng). Điểm vào mới (T2, T3,
    T4, đo vòng 50 Hz…): mở thiết bị, chạy theo hạn giờ hay ghi số đo thời gian thì gọi apply_ecoqos_policy đầu main()
    và thêm vào INCLUDED; còn lại thêm vào EXCLUDED kèm lý do."""
    found = set()
    for path in PACKAGE.rglob("*.py"):
        if _top_function(ast.parse(path.read_text(encoding="utf-8")), "main") is not None:
            found.add(".".join(path.relative_to(PACKAGE).with_suffix("").parts))
    assert not set(INCLUDED) & set(EXCLUDED)
    assert len(INCLUDED) == 27 and len(EXCLUDED) == 29
    assert found == set(INCLUDED) | set(EXCLUDED), (f"chưa xếp loại: {sorted(found - set(INCLUDED) - set(EXCLUDED))}; "
                                                  f"không còn main(): {sorted((set(INCLUDED) | set(EXCLUDED)) - found)}")


def test_excluded_and_build_window_do_not_apply_policy():
    """ecoqos_gui đo mặc định của Windows (gui_system) qua `ui.app.build_window`: build_window không được đổi EcoQoS."""
    assert "evaluation.ecoqos_gui" in EXCLUDED
    for module in EXCLUDED:
        assert not _calls(ast.parse(_source(module)), "apply_ecoqos_policy"), module
    checked = []
    for path in PACKAGE.rglob("*.py"):
        build = _top_function(ast.parse(path.read_text(encoding="utf-8")), "build_window")
        if build is not None:
            checked.append(path.relative_to(PACKAGE).as_posix())
            assert not _calls(build, "apply_ecoqos_policy") and not _calls(build, "add_ecoqos_label"), path
    assert {"ui/app.py", "ui/lidar_app.py"} <= set(checked)


def test_own_process_disable_goes_through_the_helper():
    """disable_power_throttling() không pid (chính tiến trình) chỉ được gọi trong power_throttling.py, để mọi nơi cùng
    theo AUTOPARK_KEEP_ECOQOS (fault_drill từng gọi thẳng và bỏ qua biến đó). Gọi theo pid (QEMU, ecoqos_gui) thì
    được."""
    offenders, by_pid = [], set()
    for path in [*PACKAGE.rglob("*.py"), TESTS / "conftest.py"]:
        if path == PACKAGE / "power_throttling.py":
            continue
        for call in _calls(ast.parse(path.read_text(encoding="utf-8")), "disable_power_throttling"):
            if call.args or call.keywords:
                by_pid.add(path.name)
            else:
                offenders.append(f"{path.name}:{call.lineno}")
    assert offenders == []
    assert {"qemu_board.py", "ecoqos_gui.py"} <= by_pid


class _Halt(BaseException):
    """Ném từ lớp Win32 giả ở lần đọc trạng thái: main() phải dừng ngay ở đó, trước argparse, Qt hay thiết bị.
    BaseException nên `except Exception` của apply_ecoqos_policy không nuốt được."""


@pytest.mark.parametrize("keep", [None, "1"], ids=["mac_dinh", "giu_mac_dinh"])
@pytest.mark.parametrize("module", INCLUDED)
def test_entry_point_applies_policy_before_anything_else(module, keep, monkeypatch):
    """Tham số lạ: nếu lời gọi nằm sau argparse thì main() thoát mã 2 trước khi tới đó (test hỏng, không mở gì)."""
    if module == "perception.export_onnx":
        pytest.importorskip("torch")
    mod = importlib.import_module(f"autopark.{module}")
    calls = []

    def disable(pid=None):
        calls.append(pid)
        return True

    def halt(pid=None):
        raise _Halt

    monkeypatch.setattr(power_throttling, "disable_power_throttling", disable)
    monkeypatch.setattr(power_throttling, "execution_speed_throttling", halt)
    if keep is None:
        monkeypatch.delenv(KEEP_ECOQOS_ENV, raising=False)
    else:
        monkeypatch.setenv(KEEP_ECOQOS_ENV, keep)
    argv = ["--tham-so-khong-co"]
    with pytest.raises(_Halt):
        mod.main(["run_app.py", *argv] if module == "ui.app" else argv)
    assert calls == ([] if keep else [None])


# ---------------------------------------------------------------- nhãn ở thanh trạng thái

class _SpyBar(QStatusBar):
    def __init__(self):
        super().__init__()
        self.messages = []

    def showMessage(self, text, timeout=0):  # noqa: N802 - tên của Qt
        self.messages.append((text, timeout))
        super().showMessage(text, timeout)


@pytest.mark.parametrize("name, color", [("ok", None), ("warn", theme.WARN), ("danger", theme.DANGER), ("info", None)])
def test_status_label_levels(qapp, name, color):
    policy = POLICIES[name]
    window = QMainWindow()
    bar = _SpyBar()
    window.setStatusBar(bar)
    title = window.windowTitle()
    try:
        label = add_ecoqos_label(window, policy)
        assert label is window.findChild(QLabel, LABEL_NAME) and label.parent() is bar
        assert label.text() == policy.short_vi() and label.toolTip() == policy.explain_vi()
        assert window.windowTitle() == title                # tiêu đề không đổi (test khác so đúng từng chữ)
        if color is None:
            assert label.styleSheet() == "" and bar.messages == []
        else:
            assert color in label.styleSheet() and "font-weight: 600" in label.styleSheet()
            assert bar.messages == [(f"Cảnh báo: {policy.short_vi()} — đừng thu nhỏ cửa sổ khi đang lập đường hay đang "
                                     "chạy.", WARNING_MS)] and WARNING_MS == 15000
    finally:
        window.deleteLater()


@windows_only
def test_ui_app_main_adds_label(qapp, win32, monkeypatch):
    """run_app.py → ui.app.main: tắt EcoQoS trước, dựng cửa sổ thật (offscreen), có nhãn "EcoQoS: tắt" ở thanh trạng
    thái."""
    from autopark.ui import app as ui_app

    class NoLoop:                                     # QApplication thật có sẵn từ qapp; exec() không chạy vòng sự kiện
        @staticmethod
        def instance():
            return SimpleNamespace(exec=lambda: 0)

    monkeypatch.setattr(ui_app, "QApplication", NoLoop)
    before = set(QApplication.topLevelWidgets())
    assert ui_app.main(["run_app.py"]) == 0
    windows = [w for w in QApplication.topLevelWidgets() if isinstance(w, ui_app.MainWindow) and w not in before]
    try:
        assert len(windows) == 1 and win32.disable_calls == [None]
        label = windows[0].findChild(QLabel, LABEL_NAME)
        assert label is not None and label.text() == "EcoQoS: tắt" and "uturn_w46" in label.toolTip()
    finally:
        for window in windows:
            window.close()
            window.deleteLater()


# ---------------------------------------------------------------- nơi ghi kết quả: khóa "ecoqos" đọc lúc ghi

def test_result_writers_record_the_state(win32, monkeypatch, tmp_path):
    win32.state = "system"
    from autopark.application.vehicle_link import DriveMode, VehicleLink
    from autopark.lidar.recording import default_meta
    from autopark.rig.core import ResourceMonitor
    from autopark.rig.recording import RigRecorder
    from autopark.storage import run_store

    monkeypatch.setitem(sys.modules, "pynvml", None)          # không chạm GPU: ResourceMonitor ghi lỗi nvml
    monitor = ResourceMonitor()
    sample = monitor.sample()
    monitor.samples.append(sample)
    assert sample["ecoqos"] == "system" and monitor.summary()["ecoqos"] == "system"
    assert RigRecorder(tmp_path / "phiên", ports=[1]).meta("đang ghi")["ecoqos"] == "system"
    assert default_meta("c1", port="COM9")["ecoqos"] == "system"

    def no_powershell(*args, **kwargs):
        raise OSError("không chạy PowerShell trong test")
    monkeypatch.setattr(run_store.subprocess, "check_output", no_powershell)
    assert run_store.environment()["ecoqos"] == "system"
    link = VehicleLink.simulated(DriveMode.VEHICLE_IO)
    try:
        info = json.loads(link.write_logs(tmp_path / "log")["link.json"].read_text(encoding="utf-8"))
        assert info["ecoqos"] == "system" and "ecoqos" not in link.describe()     # phát lại log không đổi
    finally:
        link.close()
    assert win32.disable_calls == []                          # chỉ đọc, không tắt gì


def test_camera_bench_measure_json_carries_the_state(win32, monkeypatch, tmp_path, capsys):
    from autopark.video import camera_bench as cb

    win32.state = "off"
    fake = {"streams": [], "total_fps_real": 0.0, "process_cpu_cores": 0.1, "failed_indices": []}
    monkeypatch.setattr(cb, "measure_many", lambda *args, **kwargs: dict(fake))     # không mở camera nào
    assert cb.main(["measure", "--index", "0", "--name", "do_thu", "--out", str(tmp_path)]) == 0
    saved = json.loads((tmp_path / "do_thu.measure.json").read_text(encoding="utf-8"))
    assert saved["ecoqos"] == "off" and "EcoQoS off" in capsys.readouterr().out
    assert win32.disable_calls == [None]


def test_fusion_demo_json_line_carries_the_state(win32, monkeypatch, capsys):
    from autopark.fusion import demo
    from autopark.lidar import live_view

    class FakeReplay:                                       # không đọc bản ghi nào
        def __init__(self, path, **kwargs):
            pass

        def close(self):
            pass

    monkeypatch.setattr(live_view, "PacedReplay", FakeReplay)
    monkeypatch.setattr(demo, "run_demo", lambda source, **kwargs: {"status": "COMPLETED", "error": None,
                                                                    "transport_error": None})
    assert demo.main(["--recording", "khong_co.npz", "--seconds", "1"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["ecoqos"] == "off"       # stdout vẫn đúng một dòng JSON


def test_evaluation_bench_json_carries_the_state(win32, monkeypatch, tmp_path, capsys):
    from autopark.evaluation import bench

    def fake_case(func, case, cfg, time_limit, do_rollout=True):
        return bench.CaseResult(case.name, case.difficulty, case.expected, "OK", 0.5, path_ok=True, tracked=True)
    monkeypatch.setattr(bench, "run_case", fake_case)
    out = tmp_path / "kq.json"
    assert bench.main(["--cases", "reverse_long_corridor", "--no-rollout", "--json", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["ecoqos"] == "off" and [r["name"] for r in data["results"]] == ["reverse_long_corridor"]
    assert POLICIES["ok"].cli_line() in capsys.readouterr().out.splitlines()


# ---------------------------------------------------------------- tiến trình con

class _InlinePool:
    """ProcessPoolExecutor giả: ghi initializer, chạy nó và mọi việc ngay trong tiến trình test (Win32 đã là giả)."""
    seen: dict = {}

    def __init__(self, max_workers=None, initializer=None, initargs=()):
        _InlinePool.seen = {"max_workers": max_workers, "initializer": initializer, "initargs": initargs}
        initializer(*initargs)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        future = Future()
        future.set_result(fn(*args))
        return future


def test_sensitivity_workers_get_policy_initializer_and_rows_carry_state(win32, monkeypatch):
    from autopark.evaluation import sensitivity as sens

    monkeypatch.setattr(sens, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(sens, "evaluate", lambda scene, variant, time_limit, planner: {"scene": scene,
                                                                                       "variant": variant})
    tasks = [("sa_ban_a", "goc", 1.0, sens.APP_PLANNER), ("sa_ban_b", "goc", 1.0, sens.APP_PLANNER)]
    rows = sens._execute(tasks, 2, 7, None)
    assert _InlinePool.seen["initializer"] is power_throttling.apply_ecoqos_policy
    assert _InlinePool.seen["initargs"] == ("evaluation.sensitivity:worker",)
    assert [r["scene"] for r in rows] == ["sa_ban_a", "sa_ban_b"] and all(r["ecoqos"] == "off" for r in rows)
    assert win32.disable_calls == [None]                    # initializer chạy một lần ở pool giả
    assert sens._ecoqos_text({"ecoqos": "off", "ecoqos_rows": {"off": 2}}) == "off (từng ca: off ×2)"
    assert sens._ecoqos_text({}) == "—"                     # ket_qua.json ghi trước 02/10/2026


@pytest.mark.parametrize("keep", [None, "1"], ids=["mac_dinh", "giu_mac_dinh"])
def test_scan_odometry_worker_init_applies_policy(win32, monkeypatch, keep):
    from autopark.lidar import scan_odometry

    threads = []
    monkeypatch.setattr(scan_odometry.cv2, "setNumThreads", threads.append)     # không đổi số luồng của tiến trình test
    if keep:
        monkeypatch.setenv(KEEP_ECOQOS_ENV, keep)
    scan_odometry._worker_init()
    assert threads == [1] and win32.disable_calls == ([] if keep else [None])
    monkeypatch.setattr(scan_odometry, "run_c1", lambda path, out, config, **options: {"input": str(path)})
    assert scan_odometry._run_job(("c1", "a.npz", None, "ra", {}))["ecoqos"] == "off"


def test_fault_drill_honours_keep_env(win32, monkeypatch, tmp_path, capsys):
    """Trước 02/10/2026 fault_drill tắt EcoQoS cho tiến trình của nó dù AUTOPARK_KEEP_ECOQOS=1 (lượt test đầy đủ với
    biến đó thì test_power_throttling.py hỏng). Đặt test ở đây, không ở test_fault_injection.py, để khỏi đụng phần
    track R đang sửa."""
    from autopark.evaluation import fault_drill

    monkeypatch.setattr(fault_drill, "_git_state", lambda: {"head": "test", "dirty": False})
    monkeypatch.setenv(KEEP_ECOQOS_ENV, "1")
    win32.state = "system"
    out = tmp_path / "dien_tap"
    assert fault_drill.main(["pose", "--out", str(out), "--name", "giu_mac_dinh"]) == 0
    summary = json.loads((out / "giu_mac_dinh.drill.json").read_text(encoding="utf-8"))
    assert win32.disable_calls == [] and summary["ecoqos"] == "system"
    assert "EcoQoS: system" in capsys.readouterr().out
