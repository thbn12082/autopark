"""Bo ảo: firmware THẬT của xe (env PlatformIO `esp32s3_qemu`) chạy trong QEMU ESP32-S3 của Espressif (thêm 30/09/2026).

Laptop nói chuyện với nó qua `socket://127.0.0.1:<cổng>` (UART0 của chip ảo) bằng đúng `SerialVehicleIO`, như với bo
thật qua COMx. Dùng cho test tự động (`tests/test_firmware_qemu.py`) và để thử phần mềm laptop khi chưa có bo:

    python -X utf8 -m autopark.transport.qemu_board chay   # build nếu cần, chạy ở socket://127.0.0.1:5555 tới Ctrl+C
    python -X utf8 -m autopark.transport.qemu_board kiem   # build, chạy, HELLO + 2 s telemetry, in kết quả rồi tắt

Công cụ lấy từ `configs/thiet_bi.json` (đổi máy chỉ sửa tệp đó): `qemu_xtensa` (qemu-system-xtensa của Espressif),
`platformio_python` (python có gói platformio; chỉ cần để build), `platformio_core_dir` (PLATFORMIO_CORE_DIR; tùy chọn).

Bản firmware này khác bản nạp vào xe đúng hai chỗ (platformio.ini): Serial qua UART0 và flash DIO. Giới hạn của bo ảo
(đo 29/09/2026 với QEMU esp-develop-9.2.2-20260417, docs/PHAN_CUNG_VA_HIEU_CHUAN.md): KHÔNG có LEDC (xung ESC/servo), GPIO
vào (E-stop), I2C/SPI/ADC, USB-Serial-JTAG nối ra ngoài; watchdog phần cứng không bao giờ kích hoạt; thời gian bám đồng
hồ máy (chậm ≈ 0,1 %) nên máy bận có thể làm firmware chốt LOOP_OVERRUN; millis() không về 0 khi reset; đôi khi QEMU
tự thoát lúc khởi động (espressif/qemu#175) nên `QemuBoard.start()` thử lại. Chạy được ở đây KHÔNG chứng minh gì về bo
thật.

Thêm 02/10/2026 (bo ảo trong phiên đỗ của giao diện, `transport/qemu_plant.py`, `ui/qemu_runner.py`): `QemuBoard` là một
`QemuBoardHandle` (`transport_opener()`, `describe()`, `clock`, `image_sha256`); `build_lock` cho mọi lần build env
esp32s3_qemu (test, dòng lệnh, giao diện) chạy lần lượt; `ensure_image` build khi ảnh thiếu hoặc cũ hơn mã nguồn và
không bao giờ trả ảnh cũ; `process_cpu_seconds` đọc thời gian CPU của QEMU.
"""
from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from autopark.power_throttling import apply_ecoqos_policy, disable_power_throttling, ecoqos_state

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "thiet_bi.json"
FIRMWARE_DIR = ROOT / "firmware" / "esp32_vehicle"
ENV_NAME = "esp32s3_qemu"
IMAGE_NAME = "qemu_flash.bin"            # do firmware/esp32_vehicle/qemu/tao_anh_flash.py tạo sau khi build
DEFAULT_PORT = 5555
DEFAULT_MONITOR_PORT = 5556
BUILD_LOCK_NAME = "autopark_esp32s3_qemu.lock"   # trong firmware/esp32_vehicle/.pio (git bỏ qua)
_ANSI = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]|\x1b[()][A-Za-z0-9]")


class QemuBoardError(RuntimeError):
    """Thiếu công cụ, build hỏng, hoặc QEMU không khởi động được."""


@dataclass(frozen=True)
class QemuTools:
    qemu: Path
    platformio_python: Path | None = None
    platformio_core_dir: Path | None = None


def load_tools(path: Path | str | None = None) -> QemuTools:
    """Đọc đường dẫn công cụ từ `configs/thiet_bi.json`. Thiếu `qemu_xtensa`, hoặc tệp không tồn tại → QemuBoardError."""
    path = CONFIG_PATH if path is None else Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))    # utf-8-sig: tệp lưu bằng Notepad có BOM
    except (OSError, ValueError) as exc:
        raise QemuBoardError(f"không đọc được {path} ({type(exc).__name__}: {exc})") from None
    if not isinstance(data, dict):
        raise QemuBoardError(f"{path}: phải là một đối tượng JSON")

    def optional_path(key: str) -> Path | None:
        value = data.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if not isinstance(value, str):
            raise QemuBoardError(f"{path}: \"{key}\" phải là chuỗi đường dẫn (đang là {value!r})")
        return Path(value.strip())

    qemu = optional_path("qemu_xtensa")
    if qemu is None:
        raise QemuBoardError(f"{path} không có \"qemu_xtensa\" (đường dẫn qemu-system-xtensa của Espressif, "
                             f"docs/PHAN_CUNG_VA_HIEU_CHUAN.md)")
    if not qemu.is_file():
        raise QemuBoardError(f"không thấy QEMU ở {qemu} (khóa \"qemu_xtensa\" trong {path})")
    python = optional_path("platformio_python")
    if python is not None and not python.is_file():
        raise QemuBoardError(f"không thấy {python} (khóa \"platformio_python\" trong {path})")
    core = optional_path("platformio_core_dir")
    if core is not None and not core.is_dir():
        # Sai đường dẫn thì PlatformIO tạo thư mục mới và tải lại toàn bộ nền tảng (≈ 3 GB) vào đó: báo lỗi thay vì vậy.
        raise QemuBoardError(f"không thấy thư mục {core} (khóa \"platformio_core_dir\" trong {path}); bỏ khóa này thì "
                             f"PlatformIO dùng biến môi trường PLATFORMIO_CORE_DIR hoặc thư mục mặc định")
    return QemuTools(qemu, python, core)


def image_path(firmware_dir: Path = FIRMWARE_DIR) -> Path:
    return Path(firmware_dir) / ".pio" / "build" / ENV_NAME / IMAGE_NAME


def build_image(tools: QemuTools, firmware_dir: Path = FIRMWARE_DIR, *, timeout_s: float = 900.0,
                log_path: Path | str | None = None) -> Path:
    """`pio run -e esp32s3_qemu`; trả ảnh flash ghép sẵn. Lần đầu trên một máy mất vài phút, sau đó vài giây.

    Thêm 02/10/2026: chạy trong `build_lock` (test, dòng lệnh và giao diện không build song song vào cùng .pio), và ghi
    ĐỦ stdout, stderr của PlatformIO vào `log_path` khi có (lỗi vẫn chỉ kèm 25 dòng cuối)."""
    if tools.platformio_python is None:
        raise QemuBoardError("thiếu \"platformio_python\" trong configs/thiet_bi.json: không build được bo ảo")
    env = dict(os.environ)
    if tools.platformio_core_dir is not None:
        env["PLATFORMIO_CORE_DIR"] = str(tools.platformio_core_dir)
    cmd = [str(tools.platformio_python), "-m", "platformio", "run", "-e", ENV_NAME, "-d", str(firmware_dir)]
    with build_lock(firmware_dir, timeout_s):
        try:
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=timeout_s)
        except (OSError, subprocess.TimeoutExpired) as exc:
            _write_build_log(log_path, cmd, f"{type(exc).__name__}: {exc}")
            raise QemuBoardError(f"không chạy được PlatformIO ({type(exc).__name__}: {exc})") from None
        _write_build_log(log_path, cmd, f"mã thoát {proc.returncode}", proc.stdout, proc.stderr)
    image = image_path(firmware_dir)
    if proc.returncode != 0 or not image.is_file():
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-25:])
        raise QemuBoardError(f"build env {ENV_NAME} hỏng (mã {proc.returncode}) hoặc thiếu {image}:\n{tail}")
    return image


def _write_build_log(log_path: Path | str | None, cmd: list[str], outcome: str, stdout: str = "",
                     stderr: str = "") -> None:
    """build.log: dòng lệnh, kết quả, rồi toàn bộ stdout và stderr của PlatformIO. Không ghi được thì bỏ qua (log phụ)."""
    if log_path is None:
        return
    text = (f"$ {' '.join(cmd)}\n# {outcome}\n\n---- stdout ----\n{stdout}\n---- stderr ----\n{stderr}\n")
    try:
        Path(log_path).write_text(text, encoding="utf-8")
    except OSError:
        pass


@contextlib.contextmanager
def build_lock(firmware_dir: Path = FIRMWARE_DIR, timeout_s: float = 900.0, *, poll_s: float = 0.5):
    """Khóa giữa các tiến trình cho MỘT lần build env esp32s3_qemu (thêm 02/10/2026): fixture `board` của pytest, dòng
    lệnh `qemu_board` và nút "Khởi động bo ảo" của giao diện không build song song vào cùng thư mục .pio (hai lần SCons
    cùng lúc có thể làm hỏng cơ sở dữ liệu .sconsign). Tệp khóa `.pio/autopark_esp32s3_qemu.lock` (tạo cả thư mục nếu
    thiếu); khóa một byte bằng `msvcrt.locking` (Windows) hay `fcntl.flock` (nơi khác), hỏi lại mỗi `poll_s`. Hệ điều
    hành tự nhả khóa khi tiến trình giữ nó chết. Chờ quá `timeout_s` → QemuBoardError."""
    path = Path(firmware_dir) / ".pio" / BUILD_LOCK_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        deadline = time.monotonic() + timeout_s
        while not _try_lock(fd):
            left = deadline - time.monotonic()
            if left <= 0:
                raise QemuBoardError(f"đang có một lần build env {ENV_NAME} khác (pytest, dòng lệnh hay cửa sổ khác) "
                                     f"quá {timeout_s:g} s (khóa {path})")
            time.sleep(min(poll_s, left))
        try:
            yield path
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


def _try_lock(fd: int) -> bool:
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(fd: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def firmware_sources_newer(image: Path | str, firmware_dir: Path = FIRMWARE_DIR) -> bool:
    """True khi ảnh flash `image` không có, hoặc CŨ hơn mã nguồn của nó: tệp mới nhất (mtime) trong src/**,
    platformio.ini và qemu/*.py (thêm 02/10/2026). So mtime nên lần lấy mã (git checkout) chạm tệp mà không đổi nội dung
    cũng tính là cũ: lần build sau đó là lần build "không có gì để làm" của PlatformIO."""
    image = Path(image)
    if not image.is_file():
        return True
    firmware_dir = Path(firmware_dir)
    sources = [p for p in (firmware_dir / "src").rglob("*") if p.is_file()]
    sources += [firmware_dir / "platformio.ini", *(firmware_dir / "qemu").glob("*.py")]
    newest = max((p.stat().st_mtime for p in sources if p.is_file()), default=0.0)
    return newest > image.stat().st_mtime


def ensure_image(tools: QemuTools, *, firmware_dir: Path = FIRMWARE_DIR, log_path: Path | str | None = None,
                 timeout_s: float = 900.0) -> tuple[Path, bool]:
    """Ảnh flash dùng được của env esp32s3_qemu (thêm 02/10/2026, nút "Khởi động bo ảo"): (ảnh, đã build hay không).
    Ảnh mới hơn mã nguồn → dùng luôn. Thiếu hoặc cũ → build (`build_image`, trong `build_lock`, log đủ ở `log_path`).
    Thiếu hoặc cũ mà máy không có "platformio_python" → QemuBoardError: KHÔNG BAO GIỜ chạy ảnh cũ hơn mã nguồn."""
    image = image_path(firmware_dir)
    if not firmware_sources_newer(image, firmware_dir):
        return image, False
    if tools.platformio_python is None:
        what = "chưa có" if not image.is_file() else "cũ hơn mã nguồn firmware"
        raise QemuBoardError(f"ảnh flash {image} {what} mà configs/thiet_bi.json không có \"platformio_python\" để build "
                             f"env {ENV_NAME}; không chạy ảnh cũ")
    return build_image(tools, firmware_dir, timeout_s=timeout_s, log_path=log_path), True


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_cpu_seconds(pid: int) -> float | None:
    """Thời gian CPU (người dùng + nhân) của tiến trình `pid`, giây (thêm 02/10/2026, để ghi QEMU tốn bao nhiêu lõi).
    Windows: GetProcessTimes; Linux: /proc/<pid>/stat. Không đọc được → None."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        handle = kernel32.OpenProcess(0x1000, False, pid)      # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            times = [wintypes.FILETIME() for _ in range(4)]   # tạo, thoát, nhân, người dùng (đơn vị 100 ns)
            if not kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                return None
            return sum((t.dwHighDateTime << 32 | t.dwLowDateTime) for t in times[2:]) / 1e7
        finally:
            _close_handle(handle)
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class QemuBoard:
    """Một tiến trình QEMU chạy ảnh flash `image`. UART0 ở `url` (TCP, không chờ ai kết nối mới chạy), monitor HMP ở
    `monitor_port`; khi có client, mọi byte UART0 cũng được chép vào `uart_log` (QEMU bỏ byte UART lúc chưa ai kết nối,
    nên chữ ROM/bootloader thường không có). `start()` chỉ trả về khi firmware đã trả HELLO_ACK (`hello`).

    Là một `QemuBoardHandle` (`transport/qemu_plant.py`, 02/10/2026): `clock` = None (io dùng đồng hồ của liên kết),
    `transport_opener()`, `describe()`. QEMU chỉ phục vụ MỘT client TCP: client thứ hai treo ở HELLO."""

    clock = None                             # QemuBoardHandle: None = io theo đồng hồ của liên kết (perf_counter)

    def __init__(self, image: Path | str, tools: QemuTools | None = None, *, port: int = 0, monitor_port: int = 0,
                 attempts: int = 5, boot_timeout_s: float = 15.0, boost: bool = True,
                 qemu_args: tuple[str, ...] = (), workdir: Path | str | None = None):
        self.image = Path(image)
        self.tools = tools or load_tools()
        self.port = port
        self.monitor_port = monitor_port
        self._auto_ports = (port == 0, monitor_port == 0)   # cổng tự chọn thì mỗi lần thử chọn lại
        self.attempts = attempts
        self.boot_timeout_s = boot_timeout_s
        self.qemu_args = tuple(qemu_args)   # thêm vào dòng lệnh QEMU (ví dụ chế độ TCG)
        self.boost = boost                   # Windows: ưu tiên trên mức thường + tắt EcoQoS cho QEMU (xem _launch)
        self.hello = None                    # HelloInfo của phiên thử trong start()
        self._own_workdir = workdir is None
        self.workdir = Path(tempfile.mkdtemp(prefix="bo_ao_qemu_")) if workdir is None else Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.proc: subprocess.Popen | None = None
        self._job = None                     # Windows: Job Object giữ QEMU chết theo tiến trình Python
        self.starts = 0                      # số lần khởi động QEMU (thử lại khi QEMU chết lúc khởi động)
        self.problems: list[str] = []        # lý do từng lần khởi động hỏng (để báo cáo)
        self.image_sha256: str | None = None     # SHA-256 của ảnh nguồn, tính một lần trong start() (≈ 10–20 ms)

    @property
    def url(self) -> str:
        return f"socket://127.0.0.1:{self.port}"

    @property
    def exit_code(self) -> int | None:
        """Mã thoát của QEMU; None khi chưa chạy hoặc còn đang chạy."""
        return None if self.proc is None else self.proc.poll()

    def transport_opener(self, read_timeout_s: float = 0.01, write_timeout_s: float = 0.05):
        """Hàm mở MỘT kết nối TCP mới tới UART0 (`SocketPort`, như `SerialVehicleIO.open` với URL `socket://`). URL lấy
        lúc gọi hàm này: io dựng cho lần khởi động này không bao giờ nối sang cổng của lần khởi động khác."""
        from .socket_port import SocketPort

        url = self.url

        def opener():
            return SocketPort.from_url(url, timeout=read_timeout_s, write_timeout=write_timeout_s)

        return opener

    def describe(self) -> dict:
        """Bo ảo này cho log (khóa "board" của link.json, bo_ao.json): cổng, ảnh và SHA-256, QEMU, pid, số lần khởi
        động và lý do hỏng, thư mục log, HELLO_ACK lúc khởi động."""
        from .protocol import ResetReason

        hello = self.hello
        info = None
        if hello is not None:
            reason = hello.reset_reason
            info = {"firmware": hello.firmware_version, "boot_id": f"0x{hello.boot_id:08x}",
                    "reset_reason": ResetReason(reason).name if reason in ResetReason._value2member_map_ else str(reason),
                    "telemetry_period_ms": round(hello.telemetry_period_s * 1000)}
        return {"url": self.url, "monitor_port": self.monitor_port, "image": str(self.image),
                "image_sha256": self.image_sha256, "qemu": str(self.tools.qemu),
                "pid": self.proc.pid if self.proc is not None else None, "starts": self.starts,
                "problems": list(self.problems), "workdir": str(self.workdir), "hello": info}

    def cpu_seconds(self) -> float | None:
        """Thời gian CPU QEMU đã dùng (`process_cpu_seconds`); None khi chưa chạy hoặc không đọc được."""
        return None if self.proc is None else process_cpu_seconds(self.proc.pid)

    @property
    def uart_log(self) -> Path:
        return self.workdir / "uart0.log"

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> "QemuBoard":
        if not self.image.is_file():
            raise QemuBoardError(f"không thấy ảnh flash {self.image}")
        try:
            self.image_sha256 = file_sha256(self.image)
        except OSError as exc:
            raise QemuBoardError(f"không đọc được ảnh flash {self.image} ({exc})") from None
        problems = []
        for _ in range(self.attempts):
            self.starts += 1
            try:
                self._launch()
                self._wait_ready()
                return self
            except QemuBoardError as exc:
                problems.append(str(exc))
                self.problems.append(str(exc))
                self._kill()
            except BaseException:
                # Ctrl+C hay lỗi lạ: `__enter__` hỏng thì `__exit__` không chạy, nên phải dọn ngay ở đây.
                self._kill()
                (self.workdir / "flash.bin").unlink(missing_ok=True)
                raise
        (self.workdir / "flash.bin").unlink(missing_ok=True)      # giữ log để xem lỗi, bỏ bản sao ảnh 8 MB
        raise QemuBoardError(f"QEMU không khởi động được sau {self.attempts} lần: " + " | ".join(problems))

    def _launch(self) -> None:
        # QEMU ghi ngược vào ảnh (NVS, core dump): mỗi lần chạy một bản sao mới, ảnh build giữ nguyên.
        flash = self.workdir / "flash.bin"
        shutil.copyfile(self.image, flash)
        if self._auto_ports[0] or not self.port:
            self.port = free_port()
        if self._auto_ports[1] or not self.monitor_port:
            self.monitor_port = free_port()
        uart = (f"socket,id=uart0,host=127.0.0.1,port={self.port},server=on,wait=off,"
                f"logfile={self.uart_log},logappend=on")
        cmd = [str(self.tools.qemu), "-machine", "esp32s3", "-display", "none",
               "-drive", f"file={flash},if=mtd,format=raw",
               "-chardev", uart, "-serial", "chardev:uart0",
               "-monitor", f"tcp:127.0.0.1:{self.monitor_port},server=on,wait=off", *self.qemu_args]
        (self.workdir / "qemu_cmdline.txt").write_text(" ".join(cmd), encoding="utf-8")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)    # Windows: không bật cửa sổ console khi gọi từ giao diện
        if self.boost:
            flags |= getattr(subprocess, "ABOVE_NORMAL_PRIORITY_CLASS", 0)
        with open(self.workdir / "qemu.out", "ab") as out, open(self.workdir / "qemu.err", "ab") as err:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=err, creationflags=flags)
        self._job = _kill_with_parent(self.proc.pid)
        if self.boost:
            # QEMU bị hạ xung/dồn sang lõi E thì trễ nhịp, firmware chốt LOOP_OVERRUN. Đo A/B 30/09/2026 lúc máy bớt bận:
            # chưa thấy khác biệt (docs/PHAN_CUNG_VA_HIEU_CHUAN.md); giữ vì vô hại. Không làm được thì QEMU vẫn chạy.
            disable_power_throttling(self.proc.pid)

    def _wait_ready(self) -> None:
        """Sẵn sàng = firmware trả HELLO_ACK qua UART0 (mở một phiên thử rồi đóng; phiên sau của laptop là phiên mới).
        QEMU không chép UART khi chưa có client, nên không dựa vào chữ ROM được. QEMU chết lúc khởi động → lỗi, thử lại."""
        from .vehicle_io import SerialVehicleIO, VehicleIOError

        deadline = time.monotonic() + self.boot_timeout_s
        last: Exception | None = None
        while time.monotonic() < deadline:
            if not self.running():
                raise QemuBoardError(f"QEMU thoát lúc khởi động (mã {self.proc.returncode}){self._stderr_tail()}")
            try:
                io = SerialVehicleIO.open(self.url)
            except OSError as exc:                            # QEMU chưa mở cổng (ConnectionRefusedError)
                last = exc
                time.sleep(0.1)
                continue
            try:
                self.hello = io.connect(timeout_s=0.5)
            except VehicleIOError as exc:                     # app chưa chạy xong setup(): HELLO mất, thử lại
                last = exc
                continue
            finally:
                io.close()
            if not self.running():                            # HELLO_ACK của tiến trình khác đang giữ cổng này
                raise QemuBoardError(f"QEMU vừa khởi động đã thoát (mã {self.proc.returncode}) nhưng cổng {self.port} "
                                     f"vẫn trả HELLO_ACK: một bo ảo khác đang dùng cổng đó{self._stderr_tail()}")
            return
        raise QemuBoardError(f"quá {self.boot_timeout_s:.0f} s không nhận được HELLO_ACK ({last}){self._stderr_tail()}")

    def _stderr_tail(self, chars: int = 300) -> str:
        try:
            tail = (self.workdir / "qemu.err").read_text(encoding="utf-8", errors="replace").strip()[-chars:]
        except OSError:
            tail = ""
        return f"; qemu.err: {tail!r}; xem {self.workdir}" if tail else f"; xem {self.workdir}"

    def open_io(self, **kwargs):
        """`SerialVehicleIO` mới nối vào UART0 của bo ảo (chưa có phiên: gọi `connect()` hoặc `connect_with_retry()`)."""
        from .vehicle_io import SerialVehicleIO

        return SerialVehicleIO.open(self.url, **kwargs)

    def monitor(self, command: str, timeout_s: float = 5.0) -> str:
        """Một lệnh monitor HMP của QEMU (`system_reset`, `info status`, `xp /4wx 0x6001f048`...); trả phần in ra."""
        with socket.create_connection(("127.0.0.1", self.monitor_port), timeout=timeout_s) as sock:
            _recv_until(sock, b"(qemu) ", timeout_s)                 # lời chào
            sock.sendall(command.encode("ascii") + b"\r\n")
            raw = _recv_until(sock, b"(qemu) ", timeout_s)
        lines = _ANSI.sub(b"", raw).decode("utf-8", "replace").replace("\r", "").split("\n")
        return "\n".join(line for line in lines[1:] if line.strip() != "(qemu)").strip()

    def reset(self) -> None:
        """Reset cả chip ảo như bật lại nguồn (HMP system_reset); firmware báo lý do reset POWER_ON."""
        self.monitor("system_reset")

    def stop(self) -> None:
        try:
            if self.running():
                try:
                    self.monitor("quit", timeout_s=2.0)
                except OSError:
                    pass
                try:
                    self.proc.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            self._kill()
            if self._own_workdir:
                shutil.rmtree(self.workdir, ignore_errors=True)

    def _kill(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()                                  # kill trước wait: Ctrl+C lần hai vẫn không bỏ sót QEMU
            try:
                self.proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                pass
        job, self._job = self._job, None
        _close_handle(job)

    def __enter__(self) -> "QemuBoard":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


def _kill_with_parent(pid: int):
    """Windows: gắn QEMU vào một Job Object có JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, nên QEMU chết theo tiến trình Python
    (Ctrl+C, đóng cửa sổ, bị kill, lỗi giữa chừng), không bị bỏ lại chạy ngầm (thêm 30/09/2026 sau review). Trả handle
    của job (giữ tới `_kill`), hoặc None nếu không làm được; khi đó QEMU vẫn chạy, chỉ mất lớp bảo vệ này."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job_extended_limits, kill_on_close, set_quota_and_terminate = 9, 0x2000, 0x0100 | 0x0001
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = ExtendedLimits()
    info.BasicLimitInformation.LimitFlags = kill_on_close
    process = kernel32.OpenProcess(set_quota_and_terminate, False, pid)
    ok = bool(process) and bool(kernel32.SetInformationJobObject(job, job_extended_limits, ctypes.byref(info),
                                                                   ctypes.sizeof(info)))
    ok = ok and bool(kernel32.AssignProcessToJobObject(job, process))
    _close_handle(process)
    if not ok:
        _close_handle(job)
        return None
    return job


def _close_handle(handle) -> None:
    if handle and sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(handle)


def _recv_until(sock: socket.socket, marker: bytes, timeout_s: float) -> bytes:
    data = bytearray()
    deadline = time.monotonic() + timeout_s
    while marker not in data:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        sock.settimeout(left)
        try:
            chunk = sock.recv(65536)
        except OSError:
            break
        if not chunk:
            break
        data += chunk
    return bytes(data)


def connect_with_retry(io, *, attempts: int = 5, timeout_s: float = 1.0):
    """`io.connect()` vài lần: HELLO gửi lúc app chưa chạy xong setup() thì mất. Trả HelloInfo."""
    from .vehicle_io import VehicleIOError

    last: Exception | None = None
    for _ in range(attempts):
        try:
            return io.connect(timeout_s=timeout_s)
        except VehicleIOError as exc:
            last = exc
    raise last


# ---- dòng lệnh ------------------------------------------------------------------------------------------------------
def _prepare(args) -> tuple[QemuTools, Path]:
    tools = load_tools()
    if args.no_build:
        image = image_path()
        if not image.is_file():
            raise QemuBoardError(f"chưa có {image}: bỏ --no-build")
        return tools, image
    print(f"build env {ENV_NAME} ...", flush=True)
    return tools, build_image(tools)


def _cmd_chay(args) -> int:
    tools, image = _prepare(args)
    board = QemuBoard(image, tools, port=args.port, monitor_port=args.monitor_port, workdir=args.workdir)
    with board:
        print(f"Bo ảo đang chạy: {board.url}   (monitor HMP: 127.0.0.1:{board.monitor_port}; log UART0: "
              f"{board.uart_log})")
        print("Dùng URL đó làm tên cổng cho SerialVehicleIO.open(). Ctrl+C để tắt.", flush=True)
        try:
            while board.running():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        code = 0 if board.running() else 1
    if code:
        print("QEMU đã tự thoát.", file=sys.stderr)
    return code


def _cmd_kiem(args) -> int:
    from .protocol import ResetReason
    from .vehicle_io import SerialVehicleIO

    tools, image = _prepare(args)
    with QemuBoard(image, tools) as board:
        qemu_ecoqos = ecoqos_state(board.proc.pid)     # QemuBoard(boost=True) tắt theo pid, không theo biến môi trường
        io = SerialVehicleIO.open(board.url)
        try:
            info = connect_with_retry(io)
            state = io.wait_ready()
            # Khung nhận trong lúc connect() và chờ bo ra khỏi BOOT: tách khỏi cửa sổ đo. Hai lượt ghi ở
            # docs/evidence/mo_phong_20260930/bo_ao_30092026/kiem_bo_ao*.txt (30/09/2026 10:13, 13:47) chạy bản đếm gộp,
            # nên "55 khung trong 2 s" ở đó gồm cả các khung này.
            before = len(io.take_new())
            frames = []
            end = io.now() + 2.0
            while io.now() < end:
                frames += io.poll()
                if io.now() - io.last_tx_time >= 0.1:
                    io.ping()
        finally:
            io.close()
    reason = ResetReason(info.reset_reason).name if info.reset_reason in ResetReason._value2member_map_ else "?"
    print(f"HELLO_ACK: boot_id {info.boot_id:08x}, firmware {info.firmware_version}, lý do reset {reason}, "
          f"trạng thái {state.name}, chu kỳ telemetry {info.telemetry_period_s * 1000:.0f} ms")
    print(f"Telemetry: {len(frames)} khung trong 2 s (≈ {len(frames) / 2:.1f} Hz), cộng {before} khung nhận trước đó lúc "
          f"kết nối và chờ bo ra khỏi BOOT; QEMU khởi động {board.starts} lần")
    print(f"EcoQoS: tiến trình này {ecoqos_state()}, QEMU {qemu_ecoqos}")
    return 0 if len(frames) >= 30 else 1                 # 20 Hz → ≈ 40 khung; ≥ 30 chừa chỗ cho máy bận


def main(argv: list[str] | None = None) -> int:
    apply_ecoqos_policy("transport.qemu_board")        # tiến trình này; QEMU vẫn do QemuBoard tắt theo pid
    parser = argparse.ArgumentParser(prog="python -m autopark.transport.qemu_board", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    chay = sub.add_parser("chay", help="chạy bo ảo ở một cổng cố định tới khi Ctrl+C")
    chay.add_argument("--port", type=int, default=DEFAULT_PORT)
    chay.add_argument("--monitor-port", type=int, default=DEFAULT_MONITOR_PORT)
    chay.add_argument("--workdir", help="thư mục giữ bản sao ảnh flash và log (mặc định: thư mục tạm, xóa khi tắt)")
    kiem = sub.add_parser("kiem", help="build, chạy, HELLO + 2 s telemetry, in kết quả rồi tắt")
    for p in (chay, kiem):
        p.add_argument("--no-build", action="store_true", help="dùng ảnh đã build, không gọi PlatformIO")
    args = parser.parse_args(argv)
    try:
        return _cmd_chay(args) if args.command == "chay" else _cmd_kiem(args)
    except QemuBoardError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
