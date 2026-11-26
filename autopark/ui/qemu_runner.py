"""Bo ảo QEMU chạy từ giao diện (thêm 02/10/2026; người dùng giao quyết định 02/10/2026).

Nút "Khởi động bo ảo" ở thẻ "Bo điều khiển" build env esp32s3_qemu khi ảnh flash thiếu hoặc cũ hơn mã nguồn
(`qemu_board.ensure_image`, khóa build chung với pytest và dòng lệnh), rồi chạy firmware THẬT của xe trong QEMU ở một
cổng TCP tự chọn trên 127.0.0.1 (`qemu_board.QemuBoard`). `QemuBoardRunner.current_board()` là nguồn bo của
`VehicleLink.qemu_board`: mỗi lần Bắt đầu đỗ liên kết hỏi bo đang chạy ở đây.

- Không bao giờ tự khởi động (chọn mục bo ảo chỉ đọc configs/thiet_bi.json). Tự tắt khi chọn bo khác, khi bấm "Tắt bo
  ảo" và khi đóng cửa sổ; QEMU nằm trong Job Object nên cũng chết theo tiến trình Python.
- Build và khởi động chạy ở luồng nền; kết quả về luồng giao diện qua tín hiệu Qt, mọi đổi trạng thái ở luồng giao diện.
- Mỗi lần khởi động một thư mục runs/bo_ao_qemu/<YYYYmmdd_HHMMSS>/ (git bỏ qua): bo_ao.json, build.log, uart0.log,
  qemu.err, qemu.out, qemu_cmdline.txt. Bản sao ảnh flash 8 MB (flash.bin) bị xóa khi tắt; bản sót lại (ứng dụng chết
  giữa chừng) xóa ở lần khởi động sau.
- QEMU giữ bận khoảng một lõi CPU tới khi tắt (vòng Arduino chờ bận; ước lượng, xem cpu_s trong bo_ao.json).
- Đây là bo ẢO: firmware xe trong giả lập, KHÔNG phải bo thật; mọi nhãn và log nói rõ như vậy.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from pathlib import Path
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from autopark.transport import qemu_board
from autopark.transport.qemu_plant import QEMU_EVIDENCE, QEMU_KIND

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_DIR = ROOT / "runs" / "bo_ao_qemu"
RECORD_NAME = "bo_ao.json"
FLASH_COPY = "flash.bin"                 # bản sao ảnh flash mà QemuBoard chạy (8 MB)
RECORD_SCHEMA_VERSION = 1
TICK_MS = 1000                           # kiểm QEMU còn chạy; đếm giây khi đang build/khởi động


class QemuRunnerState(str, Enum):
    STOPPED = "STOPPED"
    BUILDING = "BUILDING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"

    @property
    def label(self) -> str:
        return {"STOPPED": "chưa chạy", "BUILDING": "đang build firmware", "STARTING": "đang khởi động QEMU",
                "RUNNING": "đang chạy", "STOPPING": "đang tắt", "FAILED": "lỗi",
                "UNAVAILABLE": "chưa cấu hình"}[self.value]


S = QemuRunnerState
BUSY_STATES = (S.BUILDING, S.STARTING, S.RUNNING)       # "Tắt bo ảo" có tác dụng; rời mục bo ảo thì tắt


def daemon_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="bo-ao-qemu", daemon=True).start()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _remove_flash(workdir: Path | None) -> None:
    if workdir is not None:
        try:
            (workdir / FLASH_COPY).unlink(missing_ok=True)
        except OSError:
            pass                         # tệp đang dùng (QEMU chưa thoát hẳn): lần khởi động sau xóa


class QemuBoardRunner(QObject):
    """Vòng đời MỘT bo ảo QEMU của cửa sổ: STOPPED → BUILDING → STARTING → RUNNING → STOPPING → STOPPED; lỗi → FAILED,
    máy thiếu công cụ → UNAVAILABLE. `changed` phát mỗi khi trạng thái hay chữ trạng thái đổi (luồng giao diện).

    Test truyền `spawn=lambda fn: fn()` (đồng bộ), `tools_loader`, `ensure_image`, `board_factory` giả."""

    changed = Signal()
    _progress = Signal(int, str)         # (lần, trạng thái mới) từ luồng nền
    _finished = Signal(object)           # dict kết quả từ luồng nền

    def __init__(self, parent: QObject | None = None, *, runs_dir: Path | str = DEFAULT_RUNS_DIR,
                 tools_loader: Callable = qemu_board.load_tools, ensure_image: Callable = qemu_board.ensure_image,
                 board_factory: Callable = qemu_board.QemuBoard, spawn: Callable = daemon_thread):
        super().__init__(parent)
        self.runs_dir = Path(runs_dir)
        self._tools_loader = tools_loader
        self._ensure_image = ensure_image
        self._board_factory = board_factory
        self._spawn = spawn
        self.state = S.STOPPED
        self.message = ""                # lý do lỗi (FAILED) hay chưa cấu hình (UNAVAILABLE)
        self.board = None                # bo đang chạy (RUNNING) hay đang tắt (STOPPING)
        self.workdir: Path | None = None     # thư mục log của lần khởi động gần nhất
        self.record: dict | None = None      # nội dung bo_ao.json của lần khởi động gần nhất
        self._since = time.monotonic()
        self._running_since: float | None = None
        self._job = 0                    # số của việc nền mới nhất; kết quả của việc cũ hơn bị bỏ
        self._cancel: threading.Event | None = None
        self._stop_reason = ""
        self._closing = False            # đã gọi shutdown() (đóng cửa sổ); start() đặt lại
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)

    # ------------------------------------------------------------------ hỏi trạng thái
    def availability(self) -> str | None:
        """Lý do máy này chưa chạy được bo ảo; None = có đủ công cụ. CHỈ đọc configs/thiet_bi.json. Đang rảnh thì đổi
        qua lại STOPPED ↔ UNAVAILABLE theo kết quả."""
        try:
            self._tools_loader()
        except qemu_board.QemuBoardError as exc:
            if self.state in (S.STOPPED, S.UNAVAILABLE):
                self._set(S.UNAVAILABLE, str(exc))
            return str(exc)
        if self.state == S.UNAVAILABLE:
            self._set(S.STOPPED)
        return None

    def current_board(self):
        """`QemuBoardSource` của `VehicleLink.qemu_board`: (bo, "") khi đang chạy, không thì (None, lý do)."""
        if self.state == S.RUNNING and self.check_health():
            return self.board, ""
        return None, self.reason()

    def reason(self) -> str:
        """Vì sao chưa có bo để dùng, theo trạng thái (câu ghép vào lời từ chối START, "Xóa lỗi bo")."""
        return {S.STOPPED: "bo ảo chưa chạy",
                S.BUILDING: f"bo ảo đang build firmware (env {qemu_board.ENV_NAME})",
                S.STARTING: "bo ảo đang khởi động QEMU",
                S.RUNNING: "bo ảo đang chạy",
                S.STOPPING: "bo ảo đang tắt",
                S.FAILED: f"bo ảo lỗi: {self.message}",
                S.UNAVAILABLE: f"máy này chưa cấu hình bo ảo: {self.message}"}[self.state]

    def status_text(self) -> str:
        """Dòng trạng thái của thẻ Bo điều khiển (chữ thường, không HTML)."""
        st = self.state
        elapsed = int(time.monotonic() - self._since)
        if st == S.STOPPED:
            return "Bo ảo: chưa chạy."
        if st == S.BUILDING:
            return f"Đang build firmware env {qemu_board.ENV_NAME}… {elapsed} s (lần đầu trên máy mới mất vài phút)"
        if st == S.STARTING:
            return f"Đang khởi động QEMU… {elapsed} s (tự thử lại tối đa 5 lần, espressif/qemu#175)"
        if st == S.RUNNING:
            board = self.board
            hello = getattr(board, "hello", None)
            version = hello.firmware_version if hello is not None else "?"
            return (f"Bo ảo đang chạy: {board.url} · firmware {version} · QEMU khởi động {getattr(board, 'starts', '?')} "
                    f"lần · log {self.workdir}")
        if st == S.STOPPING:
            return "Đang tắt bo ảo…" + (f" ({self.message})" if self.message else "")
        if st == S.FAILED:
            return f"LỖI bo ảo: {self.message}"
        return f"Máy này chưa cấu hình bo ảo: {self.message} (configs/thiet_bi.json, docs/PHAN_CUNG_VA_HIEU_CHUAN.md)"

    def describe(self) -> dict:
        board = self.board
        return {"state": self.state.value, "label": self.state.label, "message": self.message,
                "workdir": str(self.workdir) if self.workdir is not None else None, "kind": QEMU_KIND,
                "board": board.describe() if board is not None else None}

    # ------------------------------------------------------------------ khởi động
    def start(self) -> bool:
        """"Khởi động bo ảo": chỉ từ STOPPED, FAILED hay UNAVAILABLE; trả False khi không bắt đầu. Đọc công cụ ngay (thiếu
        → UNAVAILABLE), tạo thư mục log, rồi build (nếu cần) và khởi động QEMU ở luồng nền."""
        if self.state not in (S.STOPPED, S.FAILED, S.UNAVAILABLE):
            return False
        try:
            tools = self._tools_loader()
        except qemu_board.QemuBoardError as exc:
            self._set(S.UNAVAILABLE, str(exc))
            return False
        try:
            workdir = self._new_workdir()
        except OSError as exc:
            self._set(S.FAILED, f"không tạo được thư mục log trong {self.runs_dir} ({exc})")
            return False
        self._clean_old_flash(workdir)
        self.workdir = workdir
        self.board = None
        self.record = self._new_record(tools)
        self._write_record()
        self._job += 1
        job, cancel = self._job, threading.Event()
        self._cancel = cancel
        self._stop_reason = ""
        self._closing = False
        self._set(S.BUILDING)
        self._spawn(lambda: self._start_worker(job, tools, workdir, cancel))
        return True

    def _start_worker(self, job: int, tools, workdir: Path, cancel: threading.Event) -> None:
        """Luồng nền: ensure_image (build nếu cần, build.log) → STARTING → QemuBoard.start() (cổng tự chọn). Không đổi
        trạng thái ở đây: kết quả về luồng giao diện qua `_finished`."""
        result: dict = {"job": job, "kind": "start"}
        try:
            t0 = time.perf_counter()
            image, built = self._ensure_image(tools, log_path=workdir / "build.log")
            result.update(image=str(image), built=bool(built), build_s=round(time.perf_counter() - t0, 3))
            if cancel.is_set():
                result["cancelled"] = True
                return
            self._emit(self._progress, job, S.STARTING.value)
            t1 = time.perf_counter()
            board = self._board_factory(image, tools, workdir=workdir)     # cổng 0: tự chọn, không dùng 5555/5556
            board.start()
            result.update(board=board, start_s=round(time.perf_counter() - t1, 3))
            if cancel.is_set():
                result.update(cancelled=True, cpu_s=_cpu_seconds(board))
                board.stop()
                result["exit_code"] = getattr(board, "exit_code", None)
        except qemu_board.QemuBoardError as exc:
            result["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - lỗi lạ của build/QEMU: thành FAILED, không làm treo giao diện
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if result.get("cancelled") or result.get("error"):
                _remove_flash(workdir)
            self._emit(self._finished, result)

    # ------------------------------------------------------------------ tắt
    def stop(self, reason: str = "user") -> bool:
        """"Tắt bo ảo" (`reason`: user / deselect / failed). Đang build hay khởi động: đặt cờ hủy, bo bị tắt ngay khi
        `start()` trả về (kể cả khi lệnh tắt tới sau lần kiểm cờ cuối của luồng nền: `_on_finished`). Đang chạy: tắt ở
        luồng nền, xóa flash.bin, giữ log. Trả False khi không có gì để tắt."""
        if self.state in (S.BUILDING, S.STARTING):
            waiting = ("chờ lần build firmware đang chạy xong: PlatformIO không dừng giữa chừng"
                       if self.state == S.BUILDING else "chờ QEMU khởi động xong rồi tắt")
            self._stop_reason = reason
            if self._cancel is not None:
                self._cancel.set()
            self._set(S.STOPPING, waiting)
            return True
        if self.state != S.RUNNING:
            return False
        self._stop_in_background(reason)
        return True

    def _stop_in_background(self, reason: str) -> None:
        """Tắt bo đang giữ (`self.board`) ở luồng nền: STOPPING; kết quả (kind "stop") về `_on_finished` → STOPPED."""
        board, workdir = self.board, self.workdir
        self._stop_reason = reason
        self._job += 1
        job = self._job
        self._set(S.STOPPING)
        self._spawn(lambda: self._stop_worker(job, board, workdir))

    def _stop_worker(self, job: int, board, workdir: Path | None) -> None:
        result: dict = {"job": job, "kind": "stop"}
        try:
            result["cpu_s"] = _cpu_seconds(board)
            board.stop()
            result["exit_code"] = getattr(board, "exit_code", None)
        except Exception as exc:  # noqa: BLE001 - tắt hỏng vẫn phải về STOPPED; Job Object giết QEMU khi thoát
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            _remove_flash(workdir)
            self._emit(self._finished, result)

    def shutdown(self) -> None:
        """Đóng cửa sổ (gọi SAU `Session.close()`): bo đang chạy thì tắt ĐỒNG BỘ (≤ ≈ 7 s khi QEMU không trả lời monitor),
        xóa flash.bin, ghi bo_ao.json (window_close). Build hay khởi động còn dở thì chỉ đặt cờ hủy: QEMU chết theo tiến
        trình nhờ Job Object; PlatformIO build xong một mình rồi nhả khóa. Bo khởi động xong mà kết quả tới SAU lúc này
        (vòng sự kiện còn chạy) cũng bị tắt đồng bộ (`_on_finished`)."""
        self._closing = True
        self._timer.stop()
        if self._cancel is not None:
            self._cancel.set()
        if self.state != S.RUNNING or self.board is None:
            return
        self._stop_now("window_close")

    def _stop_now(self, reason: str) -> None:
        """Tắt ĐỒNG BỘ bo đang giữ (`self.board`; đóng cửa sổ): bỏ mọi kết quả nền tới sau, xóa flash.bin, ghi
        bo_ao.json với `reason`, STOPPED."""
        board = self.board
        self._job += 1                   # bỏ mọi kết quả nền tới sau
        cpu = _cpu_seconds(board)
        try:
            board.stop()
        except Exception:  # noqa: BLE001 - đang đóng cửa sổ: không chặn
            pass
        _remove_flash(self.workdir)
        self._finish_record(reason, getattr(board, "exit_code", None), cpu)
        self.board = None
        self._set(S.STOPPED)

    def check_health(self) -> bool:
        """Đang RUNNING mà QEMU đã tự thoát → FAILED (ghi bo_ao.json, qemu_exited). Trả True khi bo còn chạy."""
        if self.state != S.RUNNING or self.board is None:
            return False
        board = self.board
        if board.running():
            return True
        code = getattr(board, "exit_code", None)
        when = datetime.now().strftime("%H:%M:%S")
        message = f"QEMU đã tự thoát (mã {code}) lúc {when}; xem {self.workdir / 'qemu.err'}"
        try:
            board.stop()                 # đóng Job Object; QEMU đã chết nên rất nhanh
        except Exception:  # noqa: BLE001
            pass
        _remove_flash(self.workdir)
        self._finish_record("qemu_exited", code, None)
        self.board = None
        self._set(S.FAILED, message)
        return False

    # ------------------------------------------------------------------ luồng giao diện
    def _emit(self, signal, *args) -> None:
        try:
            signal.emit(*args)
        except RuntimeError:
            pass                         # cửa sổ (và runner) đã bị hủy trong lúc luồng nền chạy

    def _on_progress(self, job: int, state: str) -> None:
        if job == self._job and self.state in (S.BUILDING, S.STARTING) and not self._closing:
            self._set(S(state))

    def _requested_stop_reason(self) -> str:
        """Lý do tắt đã xin trong lúc build hay khởi động: của `stop()`, không thì đóng cửa sổ hay "user"."""
        return self._stop_reason or ("window_close" if self._closing else "user")

    def _on_finished(self, result: dict) -> None:
        board = result.get("board")
        if result["job"] != self._job:
            if board is not None and not result.get("cancelled"):
                try:
                    board.stop()         # kết quả của việc đã bị thay (không thể xảy ra theo luật trạng thái)
                except Exception:  # noqa: BLE001
                    pass
            return
        record = self.record if self.record is not None else {}
        if result["kind"] == "stop":
            self._finish_record(self._stop_reason or "user", result.get("exit_code"), result.get("cpu_s"),
                                result.get("error"))
            self.board = None
            self._set(S.STOPPED)
            return
        for key in ("image", "built", "build_s", "start_s"):
            if key in result:
                record[key] = result[key]
        if board is not None:
            record.update(_board_fields(board))
        if result.get("error"):
            self._finish_record("failed", None, None, result["error"])
            self._set(S.FAILED, result["error"])
        elif result.get("cancelled"):
            self._finish_record(self._requested_stop_reason(), result.get("exit_code"), result.get("cpu_s"))
            self._set(S.STOPPED)
        else:
            self.board = board
            self._running_since = time.monotonic()
            self._write_record()
            if self._cancel is not None and self._cancel.is_set():
                # Lệnh tắt (Tắt bo ảo, chọn bo khác, đóng cửa sổ) tới SAU lần kiểm cờ hủy cuối của luồng nền: bo đã khởi
                # động xong, kết quả còn chờ trong hàng đợi tín hiệu. Sửa 02/10/2026 theo review: trước đó runner vào
                # RUNNING và lệnh tắt bị mất (QEMU chạy tiếp, giao diện đã báo đã tắt). Nay tắt ngay, không qua RUNNING.
                if self._closing:
                    self._stop_now(self._requested_stop_reason())       # cửa sổ đang đóng: tắt đồng bộ như shutdown()
                else:
                    self._stop_in_background(self._requested_stop_reason())
            else:
                self._set(S.RUNNING)

    def _tick(self) -> None:
        if self.state == S.RUNNING:
            self.check_health()
        elif self.state in (S.BUILDING, S.STARTING):
            self.changed.emit()          # đếm giây trên dòng trạng thái

    def _set(self, state: QemuRunnerState, message: str = "") -> None:
        if state != self.state:
            self._since = time.monotonic()
        self.state = state
        self.message = message
        if state in BUSY_STATES:
            self._timer.start()
        else:
            self._timer.stop()
        self.changed.emit()

    # ------------------------------------------------------------------ thư mục log, bo_ao.json
    def _new_workdir(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path, n = self.runs_dir / stamp, 1
        while path.exists():
            n += 1
            path = self.runs_dir / f"{stamp}_{n}"
        path.mkdir(parents=True)
        return path

    def _clean_old_flash(self, keep: Path) -> None:
        """Bản sao ảnh flash sót ở thư mục của lần khởi động trước (ứng dụng chết khi bo đang chạy): xóa; tệp đang dùng
        (một cửa sổ khác còn chạy bo ảo) thì để nguyên."""
        try:
            folders = [p for p in self.runs_dir.iterdir() if p.is_dir() and p != keep]
        except OSError:
            return
        for folder in folders:
            _remove_flash(folder)

    def _new_record(self, tools) -> dict:
        return {"schema_version": RECORD_SCHEMA_VERSION, "created": _now_iso(), "kind": QEMU_KIND,
                "tools": {"qemu": str(tools.qemu),
                          "platformio_python": str(tools.platformio_python) if tools.platformio_python else None,
                          "platformio_core_dir": str(tools.platformio_core_dir) if tools.platformio_core_dir else None},
                "image": None, "image_sha256": None, "built": None, "build_s": None, "start_s": None, "url": None,
                "monitor_port": None, "pid": None, "starts": None, "problems": [], "hello": None, "stopped": None,
                "exit_code": None, "stop_reason": None, "running_s": None, "cpu_s": None, "cpu_cores_avg": None,
                "error": None, "evidence": QEMU_EVIDENCE,
                "note": ("Bo ảo QEMU: firmware THẬT của xe trong giả lập, KHÔNG phải bo thật. cpu_s là thời gian CPU của "
                         "lần chạy QEMU cuối (gồm lúc khởi động); cpu_cores_avg = cpu_s / running_s là ước lượng.")}

    def _finish_record(self, reason: str, exit_code, cpu_s, error: str | None = None) -> None:
        record = self.record
        if record is None:
            return
        running_s = (time.monotonic() - self._running_since) if self._running_since is not None else None
        record.update(stopped=_now_iso(), stop_reason=reason, exit_code=exit_code,
                      running_s=round(running_s, 3) if running_s is not None else None,
                      cpu_s=round(cpu_s, 3) if cpu_s is not None else None,
                      cpu_cores_avg=round(cpu_s / running_s, 3) if cpu_s is not None and running_s else None)
        if error:
            record["error"] = error
        self._running_since = None
        self._write_record()

    def _write_record(self) -> None:
        if self.workdir is None or self.record is None:
            return
        try:
            (self.workdir / RECORD_NAME).write_text(json.dumps(self.record, ensure_ascii=False, indent=2, default=str),
                                                    encoding="utf-8")
        except OSError:
            pass                         # log phụ: không chặn bo ảo


def _cpu_seconds(board) -> float | None:
    reader = getattr(board, "cpu_seconds", None)
    try:
        return reader() if callable(reader) else None
    except Exception:  # noqa: BLE001 - chỉ để ghi log
        return None


def _board_fields(board) -> dict:
    """Các khóa của bo_ao.json lấy từ `describe()` của bo."""
    info = board.describe()
    return {key: info.get(key) for key in ("image_sha256", "url", "monitor_port", "pid", "starts", "problems", "hello")}
