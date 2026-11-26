"""Bo ảo QEMU chạy từ giao diện (`ui/qemu_runner.py`) và phần build/khóa/ảnh của `transport/qemu_board.py` (thêm
02/10/2026).

Không chạy QEMU hay PlatformIO: runner dùng công cụ, `ensure_image` và bo giả (`tests/qemu_fakes.py`), luồng nền đồng bộ;
phần build dùng thư mục firmware giả trong tmp_path và `subprocess.run` giả.
"""
import json
import os
import subprocess
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from autopark.transport import qemu_board  # noqa: E402
from autopark.transport.qemu_board import QemuBoardError, QemuTools  # noqa: E402
from autopark.transport.qemu_plant import QEMU_EVIDENCE  # noqa: E402
from tests.qemu_fakes import URL, FakeQemuBoard, make_runner  # noqa: E402


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def record_of(runner) -> dict:
    return json.loads((runner.workdir / "bo_ao.json").read_text(encoding="utf-8"))


def fake_firmware(tmp_path, image: bool = True):
    """Thư mục firmware giả: src/, platformio.ini, qemu/*.py và (tùy chọn) ảnh flash đã build."""
    fw = tmp_path / "esp32_vehicle"
    (fw / "src" / "core").mkdir(parents=True)
    (fw / "qemu").mkdir()
    for path in (fw / "src" / "main.cpp", fw / "src" / "core" / "vehicle_core.cpp", fw / "platformio.ini",
                 fw / "qemu" / "tao_anh_flash.py"):
        path.write_text("// nguồn giả\n", encoding="utf-8")
    if image:
        target = qemu_board.image_path(fw)
        target.parent.mkdir(parents=True)
        target.write_bytes(b"\xff" * 32)
    return fw


def set_mtime(path, t):
    os.utime(path, (t, t))


# ---- runner -------------------------------------------------------------------------------------------------------
def test_unavailable_tools_report_reason_without_launch(qapp, tmp_path):
    board = FakeQemuBoard()
    runner = make_runner(tmp_path, board, tools_error="configs/thiet_bi.json không có \"qemu_xtensa\"")
    assert runner.state.value == "STOPPED"                      # dựng runner không đọc tệp nào
    assert runner.calls["tools"] == 0
    reason = runner.availability()
    assert "qemu_xtensa" in reason and runner.state.value == "UNAVAILABLE" and runner.state.label == "chưa cấu hình"
    assert runner.start() is False and runner.calls["ensure"] == runner.calls["factory"] == 0
    assert board.starts == 0 and not (tmp_path / "runs").exists()
    assert runner.current_board() == (None, f"máy này chưa cấu hình bo ảo: {reason}")
    assert "Máy này chưa cấu hình bo ảo" in runner.status_text() and "thiet_bi.json" in runner.status_text()


def test_running_board_is_current_board_and_bo_ao_json_written(qapp, tmp_path):
    board = FakeQemuBoard()
    runner = make_runner(tmp_path, board, built=True)
    seen = []
    runner.changed.connect(lambda: seen.append(runner.state.value))
    assert runner.availability() is None and runner.current_board() == (None, "bo ảo chưa chạy")
    assert runner.start() is True
    assert seen[:3] == ["BUILDING", "STARTING", "RUNNING"] and runner.state.value == "RUNNING"
    assert runner.current_board() == (board, "") and board.workdir == runner.workdir
    assert runner.workdir.parent == tmp_path / "runs" and runner._timer.isActive()
    record = record_of(runner)
    assert record["evidence"] == QEMU_EVIDENCE and record["url"] == URL and record["built"] is True
    assert record["hello"]["boot_id"] == "0xb0a00001" and record["image_sha256"] == board.image_sha256
    assert "KHÔNG phải bo thật" in record["kind"] and record["stopped"] is None
    assert (runner.workdir / "build.log").exists()
    text = runner.status_text()
    assert text.startswith(f"Bo ảo đang chạy: {URL} · firmware 1.0 · QEMU khởi động 1 lần · log")
    assert runner.start() is False                              # đang chạy: không khởi động lần hai
    assert runner.describe()["board"]["url"] == URL
    runner.shutdown()


def test_fresh_image_skips_build_and_stale_or_missing_image_builds(tmp_path, monkeypatch):
    fw = fake_firmware(tmp_path)
    image = qemu_board.image_path(fw)
    now = time.time()
    for path in (fw / "src" / "main.cpp", fw / "src" / "core" / "vehicle_core.cpp", fw / "platformio.ini",
                 fw / "qemu" / "tao_anh_flash.py"):
        set_mtime(path, now - 100)
    set_mtime(image, now - 50)
    builds = []

    def fake_build(tools, firmware_dir, *, timeout_s=900.0, log_path=None):
        builds.append((firmware_dir, log_path))
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"\x00" * 32)
        return image

    monkeypatch.setattr(qemu_board, "build_image", fake_build)
    tools = QemuTools(tmp_path / "qemu.exe", tmp_path / "python.exe")
    assert not qemu_board.firmware_sources_newer(image, fw)
    assert qemu_board.ensure_image(tools, firmware_dir=fw) == (image, False) and builds == []
    set_mtime(fw / "src" / "core" / "vehicle_core.cpp", now)      # sửa mã nguồn sau lần build
    assert qemu_board.firmware_sources_newer(image, fw)
    log = tmp_path / "build.log"
    assert qemu_board.ensure_image(tools, firmware_dir=fw, log_path=log) == (image, True)
    assert builds == [(fw, log)]
    image.unlink()                                              # ảnh thiếu
    assert qemu_board.firmware_sources_newer(image, fw)
    assert qemu_board.ensure_image(tools, firmware_dir=fw)[1] is True and len(builds) == 2


def test_stale_image_without_platformio_is_refused(tmp_path, monkeypatch):
    fw = fake_firmware(tmp_path)
    image = qemu_board.image_path(fw)
    set_mtime(image, time.time() - 100)
    monkeypatch.setattr(qemu_board, "build_image", lambda *a, **k: pytest.fail("không được build"))
    tools = QemuTools(tmp_path / "qemu.exe", None)
    with pytest.raises(QemuBoardError, match="cũ hơn mã nguồn firmware.*không chạy ảnh cũ"):
        qemu_board.ensure_image(tools, firmware_dir=fw)
    image.unlink()
    with pytest.raises(QemuBoardError, match="chưa có"):
        qemu_board.ensure_image(tools, firmware_dir=fw)


def test_build_failure_message_and_build_log_kept(qapp, tmp_path, monkeypatch):
    runner = make_runner(tmp_path, FakeQemuBoard(), image_error="build env esp32s3_qemu hỏng (mã 1)")
    assert runner.start() is True
    assert runner.state.value == "FAILED" and runner.message == "build env esp32s3_qemu hỏng (mã 1)"
    assert runner.calls["factory"] == 0 and (runner.workdir / "build.log").exists()
    assert runner.current_board() == (None, "bo ảo lỗi: build env esp32s3_qemu hỏng (mã 1)")
    record = record_of(runner)
    assert record["stop_reason"] == "failed" and "hỏng" in record["error"]
    assert runner.status_text().startswith("LỖI bo ảo: build env")
    # build_image thật (PlatformIO giả): build.log có ĐỦ đầu ra, lỗi chỉ kèm 25 dòng cuối.
    fw = fake_firmware(tmp_path / "b", image=False)
    lines = [f"dòng {i}" for i in range(60)]

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "\n".join(lines), "lỗi biên dịch")

    monkeypatch.setattr(qemu_board.subprocess, "run", fake_run)
    log = tmp_path / "full_build.log"
    with pytest.raises(QemuBoardError) as err:
        qemu_board.build_image(QemuTools(tmp_path / "q.exe", tmp_path / "py.exe"), fw, log_path=log)
    assert "dòng 0\n" not in str(err.value) and "dòng 59" in str(err.value)
    text = log.read_text(encoding="utf-8")
    assert "dòng 0\n" in text and "dòng 59" in text and "lỗi biên dịch" in text and "mã thoát 1" in text
    assert (fw / ".pio" / qemu_board.BUILD_LOCK_NAME).exists()


def test_start_failure_keeps_workdir_and_message(qapp, tmp_path):
    board = FakeQemuBoard()
    board.fail_start = "QEMU không khởi động được sau 5 lần: QEMU thoát lúc khởi động (mã 1)"
    runner = make_runner(tmp_path, board)
    runner.start()
    assert runner.state.value == "FAILED" and "sau 5 lần" in runner.message
    workdir = runner.workdir
    assert workdir.is_dir() and (workdir / "qemu.err").exists() and not (workdir / "flash.bin").exists()
    assert record_of(runner)["stop_reason"] == "failed"
    board.fail_start = None
    assert runner.start() is True and runner.state.value == "RUNNING"      # thử lại từ FAILED
    assert runner.workdir != workdir
    runner.shutdown()


def test_health_check_detects_qemu_exit(qapp, tmp_path):
    board = FakeQemuBoard()
    runner = make_runner(tmp_path, board)
    runner.start()
    assert runner.check_health() is True
    board.die(3221225477)
    board_now, reason = runner.current_board()
    assert board_now is None and reason.startswith("bo ảo lỗi: QEMU đã tự thoát (mã 3221225477) lúc")
    assert "qemu.err" in reason and runner.state.value == "FAILED" and not runner._timer.isActive()
    assert not (runner.workdir / "flash.bin").exists()
    record = record_of(runner)
    assert (record["stop_reason"], record["exit_code"]) == ("qemu_exited", 3221225477)


def test_stop_and_shutdown_remove_flash_copy_keep_logs(qapp, tmp_path):
    board = FakeQemuBoard()
    runner = make_runner(tmp_path, board)
    runner.start()
    workdir = runner.workdir
    assert (workdir / "flash.bin").exists()
    runner._running_since -= 2.5                                # bo đã chạy 2,5 s
    assert runner.stop() is True
    assert runner.state.value == "STOPPED" and board.stops == 1 and runner.board is None
    assert not (workdir / "flash.bin").exists()
    for name in ("uart0.log", "qemu.err", "qemu.out", "qemu_cmdline.txt", "bo_ao.json"):
        assert (workdir / name).exists(), name
    record = record_of(runner)
    assert record["stop_reason"] == "user" and record["cpu_s"] == 1.25 and record["exit_code"] == 0
    assert record["running_s"] == pytest.approx(2.5, abs=0.2) and record["cpu_cores_avg"] == pytest.approx(0.5, abs=0.05)
    assert runner.stop() is False                               # không có gì để tắt
    runner.start()                                              # đóng cửa sổ khi bo đang chạy: tắt đồng bộ
    second = runner.workdir
    runner.shutdown()
    assert runner.state.value == "STOPPED" and board.stops == 2 and not (second / "flash.bin").exists()
    assert record_of(runner)["stop_reason"] == "window_close"
    runner.shutdown()                                           # lần hai: không làm gì
    assert board.stops == 2


def test_stop_requested_during_start_stops_board_after_start(qapp, tmp_path):
    board = FakeQemuBoard()
    runner = make_runner(tmp_path, board)
    original_start = board.start

    def start_then_user_clicks_stop():
        result = original_start()
        assert runner.state.value == "STARTING"
        assert runner.stop("deselect") is True and runner.state.value == "STOPPING"
        return result

    board.start = start_then_user_clicks_stop
    runner.start()
    assert runner.state.value == "STOPPED" and board.stops == 1 and not board.running()
    assert runner.current_board() == (None, "bo ảo chưa chạy")
    assert not (runner.workdir / "flash.bin").exists() and record_of(runner)["stop_reason"] == "deselect"
    # Hủy khi còn đang build: bo không bao giờ được dựng.
    pending = []
    runner._spawn = pending.append
    board.start = original_start
    runner.start()
    assert runner.state.value == "BUILDING" and len(pending) == 1
    runner.stop("user")
    assert runner.state.value == "STOPPING" and runner.current_board() == (None, "bo ảo đang tắt")
    factory_calls = runner.calls["factory"]
    pending.pop()()
    assert runner.state.value == "STOPPED" and runner.calls["factory"] == factory_calls


def test_old_flash_copies_cleaned_on_next_start(qapp, tmp_path):
    old = tmp_path / "runs" / "20261001_101500"
    old.mkdir(parents=True)
    (old / "flash.bin").write_bytes(b"\xff" * 64)
    (old / "uart0.log").write_text("log cũ", encoding="utf-8")
    runner = make_runner(tmp_path, FakeQemuBoard())
    runner.start()
    assert not (old / "flash.bin").exists() and (old / "uart0.log").exists()
    assert (runner.workdir / "flash.bin").exists()              # bản của lần đang chạy giữ tới khi tắt
    runner.shutdown()


def test_worker_thread_results_arrive_on_the_ui_thread(qapp, tmp_path):
    """Luồng nền thật (mặc định của runner): build/khởi động và tắt ở luồng nền, mọi đổi trạng thái ở luồng giao diện."""
    from PySide6.QtWidgets import QApplication
    from autopark.ui import qemu_runner

    board = FakeQemuBoard()
    runner = make_runner(tmp_path, board)
    runner._spawn = qemu_runner.daemon_thread
    seen = []
    runner.changed.connect(lambda: seen.append((runner.state.value, threading.current_thread() is
                                                threading.main_thread())))

    def wait_for(state: str) -> None:
        deadline = time.monotonic() + 10
        while runner.state.value != state and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.005)
        assert runner.state.value == state, seen

    assert runner.start() is True
    wait_for("RUNNING")
    assert runner.current_board() == (board, "")
    assert runner.stop() is True and runner.state.value == "STOPPING"
    wait_for("STOPPED")
    assert board.stops == 1 and seen and all(on_ui for _state, on_ui in seen)
    assert [state for state, _ in seen][-1] == "STOPPED"


def threaded_runner(tmp_path, board):
    """Runner với luồng nền THẬT (như ứng dụng); trả cả danh sách luồng để test chờ luồng xong mà chưa xử lý sự kiện của
    luồng giao diện (kết quả nằm trong hàng đợi tín hiệu)."""
    runner = make_runner(tmp_path, board)
    threads = []

    def spawn(fn):
        thread = threading.Thread(target=fn, name="bo-ao-qemu-test", daemon=True)
        threads.append(thread)
        thread.start()

    runner._spawn = spawn
    return runner, threads


def process_until(runner, state: str, timeout_s: float = 3.0) -> None:
    from PySide6.QtWidgets import QApplication

    deadline = time.monotonic() + timeout_s
    while runner.state.value != state and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)
    assert runner.state.value == state


def test_stop_after_board_start_returned_but_before_result_handled(qapp, tmp_path):
    """Review 02/10/2026 (Q #4): "Tắt bo ảo" / chọn bo khác tới SAU lần kiểm cờ hủy cuối của luồng nền (bo vừa khởi động
    xong) nhưng TRƯỚC khi luồng giao diện xử lý kết quả. Trước khi sửa: runner vào RUNNING, lệnh tắt bị mất, QEMU chạy
    tiếp dù giao diện đã báo đã tắt."""
    board = FakeQemuBoard()
    runner, threads = threaded_runner(tmp_path, board)
    seen = []
    runner.changed.connect(lambda: seen.append(runner.state.value))
    assert runner.start() is True
    threads[0].join(10)                     # bo đã khởi động; kết quả còn chờ trong hàng đợi của luồng giao diện
    assert board.running() and runner.state.value == "BUILDING"
    assert runner.stop("deselect") is True and runner.state.value == "STOPPING"
    after_stop = len(seen)
    process_until(runner, "STOPPED")
    assert "RUNNING" not in seen[after_stop:]
    assert board.stops == 1 and not board.running() and runner.board is None and not runner._timer.isActive()
    assert runner.current_board() == (None, "bo ảo chưa chạy")
    assert len(threads) == 2                # tắt ở luồng nền: không chặn luồng giao diện
    record = record_of(runner)
    assert record["stop_reason"] == "deselect" and record["url"] == URL and record["stopped"] is not None
    assert (record["cpu_s"], record["exit_code"]) == (1.25, 0)
    assert not (runner.workdir / "flash.bin").exists() and (runner.workdir / "uart0.log").exists()


def test_window_close_after_board_start_returned_but_before_result_handled(qapp, tmp_path):
    """Như trên với đóng cửa sổ: `shutdown()` lúc đó chỉ đặt cờ hủy; kết quả tới sau (vòng sự kiện còn chạy) thì bo bị
    tắt ĐỒNG BỘ như shutdown() với bo đang chạy, bo_ao.json ghi window_close."""
    board = FakeQemuBoard()
    runner, threads = threaded_runner(tmp_path, board)
    assert runner.start() is True
    threads[0].join(10)
    runner.shutdown()
    assert runner.state.value == "BUILDING" and board.running() and not runner._timer.isActive()
    process_until(runner, "STOPPED")
    assert board.stops == 1 and not board.running() and len(threads) == 1 and not runner._timer.isActive()
    assert record_of(runner)["stop_reason"] == "window_close" and not (runner.workdir / "flash.bin").exists()
    # Đóng cửa sổ khi còn đang build: luồng nền thấy cờ hủy, bo không được dựng; bo_ao.json ghi window_close.
    pending = []
    runner._spawn = pending.append
    runner.start()
    runner.shutdown()
    factory_calls = runner.calls["factory"]
    pending.pop()()
    assert runner.state.value == "STOPPED" and runner.calls["factory"] == factory_calls and board.stops == 1
    assert record_of(runner)["stop_reason"] == "window_close"


# ---- khóa build, QemuBoard không chạy QEMU ------------------------------------------------------------------------
def test_build_lock_serializes_builds(tmp_path):
    fw = tmp_path / "firmware"
    entered, release = threading.Event(), threading.Event()

    def hold():
        with qemu_board.build_lock(fw, timeout_s=5):
            entered.set()
            release.wait(5)

    thread = threading.Thread(target=hold)
    thread.start()
    assert entered.wait(5)
    t0 = time.monotonic()
    with pytest.raises(QemuBoardError, match="đang có một lần build env esp32s3_qemu khác"):
        with qemu_board.build_lock(fw, timeout_s=0.3, poll_s=0.05):
            pass
    assert 0.25 <= time.monotonic() - t0 < 2.0
    release.set()
    thread.join(5)
    with qemu_board.build_lock(fw, timeout_s=1) as path:
        assert path == fw / ".pio" / qemu_board.BUILD_LOCK_NAME and path.exists()


def test_qemu_board_handle_without_launching_qemu(tmp_path, monkeypatch):
    image = tmp_path / "qemu_flash.bin"
    image.write_bytes(b"\xff" * 32)
    board = qemu_board.QemuBoard(image, QemuTools(tmp_path / "qemu.exe"), workdir=tmp_path / "w")
    assert board.clock is None and board.exit_code is None and board.cpu_seconds() is None
    info = board.describe()
    assert info["hello"] is None and info["pid"] is None and info["image"] == str(image)
    board.port = 5999
    opener = board.transport_opener()
    board.port = 6001                                           # bo khởi động lại ở cổng khác
    seen = []
    from autopark.transport import socket_port
    monkeypatch.setattr(socket_port.SocketPort, "from_url", classmethod(lambda cls, url, **kw: seen.append(url)))
    opener()
    assert seen == ["socket://127.0.0.1:5999"]                  # URL lấy lúc gọi transport_opener()
    assert qemu_board.file_sha256(image) == __import__("hashlib").sha256(b"\xff" * 32).hexdigest()
    if sys.platform == "win32":
        cpu = qemu_board.process_cpu_seconds(os.getpid())
        assert cpu is not None and cpu > 0
