"""Ghi bốn camera + LiDAR TRONG PHIÊN ĐỖ XE (T3 ở docs/KICH_BAN_NGHIEM_THU.md), cùng đồng hồ perf_counter với log VehicleIO
và dấu đồng bộ T14. Không dùng Qt: `ui/record_dock.py` là phần giao diện, cửa sổ `ui.lidar_app` là chủ (`RecordingHost`).

Không gửi gì tới bo, không yêu cầu dừng xe, không chặn Bắt đầu đỗ, không mở thiết bị nào: chỉ gắn vào các nguồn mà ngăn AI
camera và ngăn LiDAR đã mở (thêm 02/10/2026):
- camera: bộ ghi được gắn NGOÀI vào `Rig` của ngăn AI camera (`Rig.attach_recorder`) — mọi khung tốt và sự kiện đọc hỏng
  của các camera của Rig lúc bắt đầu ghi. Rig không bao giờ dừng hay chờ bộ ghi này;
- LiDAR: luồng đọc của ngăn LiDAR bọc nguồn bằng `LidarTap` và đẩy mọi vòng quét vào bộ ghi (`lidar_sink`), CHỈ khi nguồn
  dùng đồng hồ bàn thử (perf_counter) và có `t0` — nguồn khác bị loại, có lý do;
- `session/clock.csv` (`CLOCK_FIELDS`): mốc ghép perf_counter với thời gian phiên và đồng hồ VehicleIO — lúc bắt đầu, mỗi
  giây, mỗi lần phiên đổi trạng thái, khi cửa sổ thu nhỏ/hiện lại, khi nguồn rời/nối lại, khi đĩa sắp đầy, khi dừng;
- `session/ai_batches.csv` (`AI_FIELDS`): quyết định của ngăn AI camera cho mỗi lô nó xét (không có bản đồ xác suất: phát
  lại chạy lại AI như bàn thử); khe hở của `batch_id` là các lô mà timer 50 ms của ngăn không kịp xét;
- `session/sync_marks.csv`: bản sao dấu đồng bộ của cửa sổ (`SYNC_FIELDS`) lúc dừng ghi. Bản ghi KHÔNG BAO GIỜ thêm dòng
  vào nhật ký dấu đồng bộ của cửa sổ (`score_run` tách lần chạy ở mỗi dòng CLOCK có state RUNNING).

Thư mục `<gốc>/<yyyymmdd_hhmmss_mmm>[_<tên>]/` vẫn là định dạng `autopark.rig_recording` v1 (`rig.recording`), nên
`rig.replay`, `rig.bench --replay` và `ui.rig_app --replay` đọc được như bản ghi bàn thử; `ui.lidar_app --recording <thư
mục>` và `lidar.live_view --recording <thư mục>` phát lại mọi phần LiDAR. meta.json có thêm khóa `session_recording`.
Cách đổi đồng hồ: `ALIGN_TEXT` (cũng ghi trong meta.json) và `read_session_clock`.

Ngưỡng đĩa (cần ≥ 5 GB trống để bắt đầu, tự dừng dưới 2 GB, cảnh báo khi còn < 10 phút ghi; GB = 2^30 byte như Windows
Explorer báo), thư mục mặc định, bảng lô AI bật sẵn, khóa "Bắt đầu ghi" khi xe chạy, nguồn tắt/bật giữa chừng: theo mặc
định an toàn của thiết kế, người dùng giao quyết định 02/10/2026 ("làm hết"); các ngưỡng là ĐỀ XUẤT – CHỜ CHỐT. Chỉ kiểm
bằng test offscreen với nguồn giả; CHƯA THỬ với thiết bị thật.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
import functools
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import statistics
from typing import TYPE_CHECKING, Callable, Protocol

from autopark.evaluation.sync_marks import SYNC_FIELDS
from autopark.perception.paths import PROJECT
from autopark.power_throttling import execution_speed_throttling
from autopark.rig.recording import (DEFAULT_JPEG_QUALITY, DEFAULT_MAX_PENDING_MB, IMAGE_FORMATS, LIDAR_SCANS_PER_PART,
                                    META_FILE, RigRecorder)
from autopark.video.multicam import RIG_CLOCK, clock_info

if TYPE_CHECKING:
    from autopark.rig.core import Rig

DEFAULT_ROOT = PROJECT / "runs" / "session_recordings"      # git bỏ qua runs/ (autopark/.gitignore)
CLOCK_TABLE = "session/clock.csv"
AI_TABLE = "session/ai_batches.csv"
SYNC_COPY = "session/sync_marks.csv"
CLOCK_FIELDS = ("t_perf", "t_wall", "trigger", "state", "run", "t_session", "t_io", "io_clock", "time_scale", "window",
                "note")
AI_FIELDS = ("t_perf", "batch_id", "t_done", "anchor_t", "skew_ms", "frames", "lagging", "deferred", "carried",
             "checkpoint", "usable", "reasons", "notes", "cameras_used", "occupied_batch", "occupied_filtered",
             "window_fill", "bev_ms", "ai_boxes", "injected", "state")
# lỗi ghi không có mốc riêng: sau lỗi ghi bộ ghi không ghi thêm dòng nào (như sự kiện camera) — lỗi nằm ở meta.json
# (status "lỗi", error, session_recording.stopped_by "write_error")
CLOCK_TRIGGERS = ("start", "periodic", "state_change", "window_state", "camera_detached", "lidar_detached",
                  "lidar_attached", "disk_warning", "disk_guard", "stop")
STOP_REASONS = ("user", "disk_guard", "write_error", "no_sources", "window_closed")
MIN_FREE_START_GB = 5.0          # ĐỀ XUẤT – CHỜ CHỐT: dưới chừng ấy GB trống thì không bắt đầu ghi
MIN_FREE_STOP_GB = 2.0           # ĐỀ XUẤT – CHỜ CHỐT: dưới chừng ấy GB trống thì tự dừng ghi
LOW_MINUTES_WARN = 10            # ĐỀ XUẤT – CHỜ CHỐT: cảnh báo một lần khi chỉ còn chừng ấy phút ghi
ANCHOR_PERIOD_S = 1.0            # mốc đồng hồ định kỳ
SESSION_RECORDING_VERSION = 1
GB = 2**30
NAME_MAX = 40
DRIVING_STATES = ("RUNNING", "STOPPING")        # SessionState.value của lần chạy đang mở
REFS_FORMAT = "autopark.sensor_recording_refs"
REFS_VERSION = 1
THRESHOLDS_NOTE = "ĐỀ XUẤT – CHỜ CHỐT (người dùng giao quyết định 02/10/2026)"
ALIGN_TEXT = (
    "Mọi t_s (khung, vòng quét, sự kiện) và mọi t_perf của session/*.csv là perf_counter của máy này (QPC; chỉ so được "
    "trong cùng một máy và cùng một lần khởi động; created_utc ứng với t_start_s cho giờ thật). Stamp là lúc dữ liệu tới "
    "máy, không phải lúc phơi sáng hay lúc đo (như bàn thử). "
    "(a) VehicleIO thời gian thực (cổng serial/QEMU, io_clock realtime): t_io = t_perf − (t_perf − t_io), hiệu lấy từ "
    "bất kỳ dòng session/clock.csv nào của liên kết đó hoặc khóa clock của link.json (T13); t_session = t_perf − "
    "t_perf_at_start. "
    "(b) SIM / bo mô phỏng: t_session nội suy tuyến tính giữa hai dòng session/clock.csv của cùng lần chạy ở hai phía t "
    "(cách nhau ≤ 1 s, thêm một dòng mỗi lần đổi trạng thái); sai số ≤ một nhịp giao diện (≈ 16 ms, tới 100 ms khi khựng) "
    "× time_scale; KHÔNG cộng t_session vào giờ START. "
    "(c) Video R1/R3: qua các dòng SYNC_MARK của session/sync_marks.csv (t_perf = a + b·v, KICH_BAN_NGHIEM_THU mục 2.5). "
    "(d) Dấu T13/T14 (cột t_perf) so thẳng.")


class RecordStartError(RuntimeError):
    """Không bắt đầu ghi được (lý do bằng tiếng Việt, hiện nguyên văn ở ngăn "Ghi cảm biến")."""


# ------------------------------------------------------------------------------------------------ tiện ích

def fmt_dec(value: float, nd: int = 1) -> str:
    """Số thập phân kiểu Việt: 5,0."""
    return f"{value:.{nd}f}".replace(".", ",")


def fmt_g(value: float) -> str:
    """Ngưỡng gọn kiểu Việt: 5, 2,5."""
    return f"{value:g}".replace(".", ",")


def fmt_int(value: int) -> str:
    """Số nguyên có dấu chấm ngăn nghìn: 12.100."""
    return f"{int(value):,}".replace(",", ".")


def clean_name(text: str) -> str:
    """Tên do người dùng gõ → phần cuối tên thư mục: chữ (cả chữ Việt), số, '_' và '-' giữ nguyên, ký tự khác thành '_',
    tối đa NAME_MAX ký tự. "đỗ 1/lần 3" → "đỗ_1_lần_3"."""
    cleaned = re.sub(r"[^\w-]+", "_", str(text or "").strip())
    return re.sub(r"_+", "_", cleaned).strip("_")[:NAME_MAX].strip("_")


def disk_free_bytes(path) -> int | None:
    """Byte trống của ổ chứa `path` (đo ở thư mục cha gần nhất đang có); None khi không đọc được. Gọi mỗi giây trên luồng
    giao diện: không dùng Path.resolve() (≈ 0,1 ms mỗi lần trên Windows)."""
    p = Path(os.path.abspath(path))
    for candidate in (p, *p.parents):
        try:
            if candidate.is_dir():
                return int(shutil.disk_usage(candidate).free)
        except OSError:
            return None
    return None


def drive_name(path) -> str:
    """"ổ D" (Windows) hay "ổ đĩa" (không có tên ổ)."""
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    return f"ổ {drive.rstrip(':')}" if drive else "ổ đĩa"


@functools.lru_cache(maxsize=32)
def _outside_runs(root: str) -> bool:
    try:
        target = Path(root).resolve()
        repo, runs = PROJECT.parent.resolve(), (PROJECT / "runs").resolve()
    except OSError:
        return False
    return target.is_relative_to(repo) and not target.is_relative_to(runs)


def outside_ignored_runs(root) -> bool:
    """`root` nằm trong kho git nhưng ngoài autopark/runs/ (thư mục git bỏ qua): ảnh camera có thể lọt vào git. Nhớ kết
    quả theo đường dẫn (ngăn hỏi mỗi giây)."""
    return _outside_runs(os.path.abspath(root))


def _project_rel(path: Path) -> str | None:
    try:
        return Path(path).resolve().relative_to(PROJECT.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _ports(ports) -> str:
    return ";".join(str(int(p)) for p in sorted(ports))


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


# ------------------------------------------------------------------------------------------------ tùy chọn, chủ

@dataclass(frozen=True)
class RecordOptions:
    """Tùy chọn ghi (dòng lệnh `ui.lidar_app`, ô của ngăn "Ghi cảm biến"). `check()` trả chính nó hoặc ném ValueError nói
    rõ bằng tiếng Việt."""
    root: Path = DEFAULT_ROOT
    image_format: str = "jpg"
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    min_free_gb: float = MIN_FREE_START_GB
    stop_free_gb: float = MIN_FREE_STOP_GB
    max_pending_mb: float = DEFAULT_MAX_PENDING_MB
    lidar_scans_per_part: int = LIDAR_SCANS_PER_PART
    ai_rows: bool = True

    def check(self) -> "RecordOptions":
        if self.image_format not in IMAGE_FORMATS:
            raise ValueError(f"định dạng ảnh phải là một trong {', '.join(IMAGE_FORMATS)} (nhận {self.image_format!r})")
        quality = self.jpeg_quality
        if isinstance(quality, bool) or not isinstance(quality, int) or not 1 <= quality <= 100:
            raise ValueError(f"chất lượng JPEG phải là số nguyên trong 1..100 (nhận {quality!r})")
        low, high = float(self.stop_free_gb), float(self.min_free_gb)
        if not (math.isfinite(low) and math.isfinite(high) and 0 < low < high):
            raise ValueError(f"cần 0 < ngưỡng tự dừng ({fmt_g(low)} GB) < ngưỡng trống tối thiểu để bắt đầu ghi "
                             f"({fmt_g(high)} GB)")
        if not self.max_pending_mb > 0 or int(self.lidar_scans_per_part) < 1:
            raise ValueError("hàng đợi ghi phải > 0 MB và mỗi phần LiDAR ≥ 1 vòng")
        root = Path(self.root)
        if root.exists() and not root.is_dir():
            raise ValueError(f"thư mục gốc của bản ghi là một tệp, không phải thư mục: {root}")
        return self


class RecordingHost(Protocol):
    """Cửa sổ chủ của bản ghi (BenchWindow của `ui.lidar_app`); test dùng một lớp giả không Qt.

    - `anchor_context(t_perf)`: cột của một mốc ngoài t_perf — state, note, time_scale, và t_session / t_io / io_clock khi
      có (như `MainWindow._sync_context`, t_session mỗi khi phiên có `world`);
    - `camera_rig()`: `Rig` đang chạy của ngăn AI camera, None khi tắt hay không có ngăn;
    - `camera_info()`: None khi không có ngăn AI camera, không thì dict của `CameraAIDock.recording_info()` (khóa `on`,
      `source_kind`, `ports`, `synthetic`, …);
    - `lidar_info()`: None khi ngăn LiDAR không có nguồn, không thì `LidarDock.recording_info()` (khóa `source_key`,
      `kind`, `port`, `recording`, `describe`, `clock_ok`, `why`, `settings`);
    - `lidar_stats()`: số của ngăn LiDAR lúc dừng ghi; `session_meta()`: kịch bản, xe, nhánh chạy, bo, giới hạn đổi chiều,
      `state`, `sync_marks_live_file`; `sync_rows()`: các dòng dấu đồng bộ của cửa sổ; `window_state()`: normal /
      minimized / hidden."""

    def anchor_context(self, t_perf: float) -> dict: ...

    def camera_rig(self) -> "Rig | None": ...

    def camera_info(self) -> dict | None: ...

    def lidar_info(self) -> dict | None: ...

    def lidar_stats(self) -> dict | None: ...

    def session_meta(self) -> dict: ...

    def sync_rows(self) -> list[dict]: ...

    def window_state(self) -> str: ...


@dataclass
class Availability:
    """Nguồn ghi được lúc này. `reasons`: "cameras"/"lidar" → vì sao nguồn đó không ghi được (hiện ở chú thích ô chọn)."""
    cameras: bool
    lidar: bool
    camera_ports: list[int] = field(default_factory=list)
    lidar_label: str = ""
    reasons: dict[str, str] = field(default_factory=dict)
    draining: bool = False

    @property
    def any(self) -> bool:
        return self.cameras or self.lidar


def lidar_label(info: dict | None) -> str:
    """Tên ngắn của nguồn LiDAR cho dòng trạng thái: cổng COM, tên bản ghi phát lại hay mã nguồn."""
    if not info:
        return ""
    if info.get("kind") == "live" and info.get("port"):
        return str(info["port"])
    if info.get("kind") == "replay" and info.get("recording"):
        return f"phát lại {Path(str(info['recording'])).name}"
    return str(info.get("source_id") or "LiDAR")


@dataclass
class _Live:
    """Trạng thái của MỘT lần ghi (giữ tới lần bắt đầu ghi sau, để dòng trạng thái báo đang ghi nốt / xong / lỗi)."""
    rec: RigRecorder
    rig: object | None                  # Rig của ngăn AI camera đã gắn bộ ghi (None: không ghi camera)
    start_rig: object | None            # Rig có lúc bắt đầu (dù ghi hay không): Rig KHÁC xuất hiện sau = bật muộn
    cameras: bool
    lidar: bool
    ai_table: bool
    lidar_key: object = None
    start_lidar_key: object = None
    lidar_name: str = ""
    cam_attached: bool = False
    lidar_attached: bool = False
    replay: bool = False
    synthetic: bool = False
    cameras_at_stop: list | None = None
    runs: list = field(default_factory=list)
    detached: list = field(default_factory=list)
    ignored_late: list = field(default_factory=list)
    late_seen: set = field(default_factory=set)
    run_count: int = 0
    last_anchor_t: float | None = None
    window: str | None = None
    disk_warned: bool = False
    ai_rows: int = 0
    ai_skipped: int = 0
    last_batch_id: int | None = None
    block: dict = field(default_factory=dict)       # meta.session_recording lúc bắt đầu
    stopping: bool = False
    stopped_by: str | None = None
    reported: bool = False


# ------------------------------------------------------------------------------------------------ bộ ghi trong phiên

class SessionSensorRecorder:
    """Một bản ghi cảm biến tại một thời điểm, do ngăn "Ghi cảm biến" bật tắt (xem đầu module).

    Mọi hàm chạy ở luồng giao diện, trừ `lidar_sink()` (luồng đọc LiDAR, chỉ đọc thuộc tính). Không hàm nào ném lỗi vào
    nhịp của cửa sổ: `on_state_change`, `add_ai_batch`, `poll` bắt mọi lỗi và báo bằng chữ; chỉ `start` ném
    `RecordStartError` (nút "Bắt đầu ghi" hiện lý do). `clock`, `free_bytes`, `ecoqos`, `wall` thay được trong test."""

    def __init__(self, host: RecordingHost, options: RecordOptions | None = None, *, app: str = "ui.lidar_app",
                 clock=RIG_CLOCK, free_bytes: Callable[[Path], int | None] = disk_free_bytes,
                 ecoqos: Callable[[], str | None] = execution_speed_throttling,
                 wall: Callable[[], datetime] = datetime.now):
        self.host = host
        self.options = (options or RecordOptions()).check()
        self.app, self.clock, self.free_bytes, self.ecoqos, self.wall = app, clock, free_bytes, ecoqos, wall
        self.live: _Live | None = None              # lần ghi gần nhất (đang ghi, đang ghi nốt hay đã xong)
        self.history: list[RigRecorder] = []        # mọi lần ghi đã bắt đầu được trong cửa sổ này, cũ trước
        self.last_run: dict | None = None           # lần chạy gần nhất của phiên, theo dõi cả khi không ghi
        self.hook_errors: list[str] = []
        self._pending: list[str] = []                # lời báo từ callback (gỡ camera), trả ở poll() sau

    # ---- trạng thái ----
    @property
    def rec(self) -> RigRecorder | None:
        return None if self.live is None else self.live.rec

    @property
    def active(self) -> bool:
        """Đang nhận dữ liệu."""
        return self.live is not None and self.live.rec.active

    @property
    def draining(self) -> bool:
        """Đã dừng nhận, luồng ghi còn ghi nốt hàng đợi."""
        live = self.live
        return (live is not None and not live.rec.active and live.rec.state != "chưa chạy"
                and not live.rec.finished.is_set())

    def lidar_sink(self) -> RigRecorder | None:
        """Bộ ghi cho vòng quét của ngăn LiDAR (luồng đọc gọi mỗi vòng): bộ ghi hiện hành khi nó ghi LiDAR và đang nhận."""
        live = self.live
        if live is None or not live.lidar:
            return None
        rec = live.rec
        return rec if rec.active else None

    def availability(self) -> Availability:
        reasons: dict[str, str] = {}
        ports: list[int] = []
        cameras = False
        try:
            info, rig = self.host.camera_info(), self.host.camera_rig()
        except Exception as exc:  # noqa: BLE001
            info, rig = None, None
            reasons["cameras"] = f"không đọc được ngăn AI camera ({type(exc).__name__}: {exc})"
        if "cameras" in reasons:
            pass
        elif info is None:
            reasons["cameras"] = "không có ngăn AI camera (mở ui.lidar_app với --camera-ai)"
        elif rig is None:
            reasons["cameras"] = "AI camera đang tắt (bấm \"Bật AI camera\" ở ngăn AI camera)"
        elif info.get("synthetic") and info.get("source_kind") == "live":
            reasons["cameras"] = "rig camera TỔNG HỢP với camera thật: không ghi"
        else:
            ports = [int(s.port) for s in rig.cams.specs]
            cameras = bool(ports)
            if not cameras:
                reasons["cameras"] = "Rig của ngăn AI camera không có camera nào"
        try:
            lidar = self.host.lidar_info()
        except Exception as exc:  # noqa: BLE001
            lidar = None
            reasons["lidar"] = f"không đọc được ngăn LiDAR ({type(exc).__name__}: {exc})"
        lidar_ok = False
        if "lidar" in reasons:
            pass
        elif lidar is None:
            reasons["lidar"] = "LiDAR chưa kết nối (bấm \"Kết nối\" ở ngăn LiDAR)"
        elif not lidar.get("clock_ok"):
            reasons["lidar"] = f"LiDAR không ghi được: {lidar.get('why') or 'nguồn không cùng đồng hồ perf_counter'}"
        else:
            lidar_ok = True
        return Availability(cameras, lidar_ok, ports, lidar_label(lidar), reasons, self.draining)

    def folder_for(self, name: str = "", now: datetime | None = None) -> Path:
        stamp = f"{now or self.wall():%Y%m%d_%H%M%S_%f}"[:-3]
        clean = clean_name(name)
        return Path(self.options.root) / (f"{stamp}_{clean}" if clean else stamp)

    # ---- bắt đầu / dừng ----
    def start(self, name: str = "", *, cameras: bool = True, lidar: bool = True, ai_rows: bool | None = None) -> RigRecorder:
        """Bắt đầu một bản ghi; trả `RigRecorder` đang ghi. Từ chối (RecordStartError, không tạo thư mục nào) khi: đang ghi
        hay bản ghi trước còn ghi nốt; xe đang chạy (RUNNING/STOPPING — nút đã khóa, đây là chốt chặn cuối); không có nguồn
        nào chọn được; ổ còn ít hơn `min_free_gb`. Không đọc được dung lượng trống thì vẫn ghi, kèm cảnh báo."""
        if self.active:
            raise RecordStartError(f"Đang ghi vào {self.rec.folder}")
        if self.draining:
            raise RecordStartError(f"Bản ghi trước {self.rec.folder.name} còn đang ghi nốt "
                                   f"({self.rec.status()['pending_frames']} khung chờ ghi): chờ XONG rồi mới ghi tiếp")
        session = dict(self.host.session_meta() or {})
        state = str(session.get("state") or "")
        if state in DRIVING_STATES:
            raise RecordStartError("Bắt đầu ghi trước Bắt đầu đỗ: lúc xe chạy, luồng giao diện là vòng điều khiển 50 Hz, "
                                   "không ghi đĩa lâu")
        avail = self.availability()
        use_cams, use_lidar = bool(cameras) and avail.cameras, bool(lidar) and avail.lidar
        if not (use_cams or use_lidar):
            why = [("camera: không chọn" if not cameras else f"camera: {avail.reasons.get('cameras', '?')}"),
                   ("LiDAR: không chọn" if not lidar else f"LiDAR: {avail.reasons.get('lidar', '?')}")]
            raise RecordStartError("Không có nguồn để ghi: " + "; ".join(why))
        opts = self.options
        root = Path(opts.root)
        free = self.free_bytes(root)
        warnings = []
        if free is None:
            warnings.append(f"không đọc được dung lượng trống của {drive_name(root)}: lần ghi này không có ngưỡng đĩa")
        elif free < opts.min_free_gb * GB:
            raise RecordStartError(f"Không bắt đầu ghi: {drive_name(root)} còn {fmt_dec(free / GB)} GB < "
                                   f"{fmt_g(opts.min_free_gb)} GB tối thiểu")
        rig = self.host.camera_rig()
        cam_info = self.host.camera_info()
        lid_info = self.host.lidar_info()
        record_rig = rig if use_cams else None
        use_ai = use_cams and (opts.ai_rows if ai_rows is None else bool(ai_rows))
        tables = {CLOCK_TABLE: CLOCK_FIELDS}
        if use_ai:
            tables[AI_TABLE] = AI_FIELDS
        window = self._window_state()
        block = self._start_block(name, session, avail, use_cams, use_lidar, cam_info, lid_info, cameras, lidar,
                                  free, window, warnings)
        meta = self._recording_meta(record_rig, lid_info if use_lidar else None, name, block)
        rec = RigRecorder(self.folder_for(name), ports=avail.camera_ports if use_cams else [], lidar=use_lidar,
                          meta=meta, clock=self.clock, image_format=opts.image_format, jpeg_quality=opts.jpeg_quality,
                          max_pending_mb=opts.max_pending_mb, lidar_scans_per_part=opts.lidar_scans_per_part,
                          tables=tables)
        live = _Live(rec, record_rig, rig, use_cams, use_lidar, use_ai,
                     lidar_key=lid_info.get("source_key") if (use_lidar and lid_info) else None,
                     start_lidar_key=None if lid_info is None else lid_info.get("source_key"),
                     lidar_name=lidar_label(lid_info) if use_lidar else "",
                     replay=bool((use_cams and (cam_info or {}).get("source_kind") == "replay")
                                 or (use_lidar and (lid_info or {}).get("kind") == "replay")),
                     synthetic=bool(use_cams and (cam_info or {}).get("synthetic")),
                     window=window, block=block)
        previous = self.live
        try:
            if record_rig is not None:
                # gắn TRƯỚC khi nhận: lớp bọc camera thấy bộ ghi ngay khi nó bắt đầu nhận (RigRecorder.start)
                record_rig.attach_recorder(rec, on_detach=lambda info, live=live: self._on_camera_detach(live, info))
                live.cam_attached = True
            live.lidar_attached = use_lidar
            self.live = live                          # lidar_sink thấy bộ ghi ngay khi nó bắt đầu nhận
            rec.start()
        except Exception as exc:  # noqa: BLE001 - mọi lỗi (thư mục, đĩa, Rig từ chối) thành lời báo ở ngăn
            live.stopping = True
            if live.cam_attached:
                record_rig.detach_recorder()
                live.cam_attached = False
            self.live = previous
            raise RecordStartError(f"Không bắt đầu ghi được: {type(exc).__name__}: {exc}") from exc
        self.history.append(rec)
        if previous is not None and not previous.reported and previous.rec.finished.is_set():
            previous.reported = True                  # bản ghi trước xong mà poll() chưa kịp báo
            self._pending.append(self._finished_text(previous))
        self._anchor("start", "; ".join(warnings))
        return rec

    def stop(self, reason: str = "user") -> dict | None:
        """Dừng nhận (ngay, không chặn): mốc "stop", gỡ khỏi Rig camera, xếp bản sao dấu đồng bộ, meta cuối, rồi luồng ghi
        ghi nốt hàng đợi và meta.json "xong"/"lỗi" (`wait_finished`). None khi không đang ghi."""
        live = self.live
        if live is None or not live.rec.active or live.stopping:
            return None
        rec = live.rec
        self._anchor("stop", f"dừng ghi: {reason}")
        live.stopping, live.stopped_by = True, reason
        if live.rig is not None and live.cam_attached:
            live.rig.detach_recorder()                  # → _on_camera_detach: chỉ lấy số camera lúc dừng
        notes = []
        try:
            rows = [dict(r) for r in (self.host.sync_rows() or [])]
        except Exception as exc:  # noqa: BLE001
            rows = []
            notes.append(f"không đọc được dấu đồng bộ của cửa sổ ({type(exc).__name__}: {exc})")
        if rows:
            rec.add_csv_file(SYNC_COPY, SYNC_FIELDS, rows)
        try:
            lidar_stats = self.host.lidar_stats() if live.lidar else None
        except Exception as exc:  # noqa: BLE001
            lidar_stats = {"error": f"{type(exc).__name__}: {exc}"}
        rec.set_final_meta(cameras_at_stop=list(live.cameras_at_stop or []), lidar_at_stop=lidar_stats,
                           session_recording=self._final_block(live, reason, len(rows), notes))
        return rec.stop(wait=False)

    def wait_finished(self, timeout_s: float = 60.0) -> bool:
        """Chờ luồng ghi ghi nốt (đóng cửa sổ, test). True khi không còn gì chưa xong."""
        live = self.live
        if live is None or live.rec.state == "chưa chạy":
            return True
        return live.rec.finished.wait(timeout_s)

    # ---- móc của cửa sổ ----
    def on_state_change(self, old: str, new: str, stop_reason: str = "") -> None:
        """Phiên đổi trạng thái (gọi trong nhịp 16 ms, ngay sau MainWindow): theo dõi lần chạy (cả khi không ghi, cho
        `export_refs`); đang ghi thì thêm mốc "state_change". Không bao giờ ném."""
        try:
            self._state_change(getattr(old, "value", str(old)), getattr(new, "value", str(new)), stop_reason or "")
        except Exception as exc:  # noqa: BLE001 - không bao giờ ném vào vòng điều khiển 50 Hz
            self._hook_error("đổi trạng thái phiên", exc)

    def add_ai_batch(self, result, upd, info: dict | None = None) -> None:
        """Một lô AI mà ngăn AI camera vừa xét (`AIResult`, `MapperUpdate`, {state, ai_boxes, injected, stale}), gọi SAU
        mọi quyết định an toàn của ngăn. Một dòng `session/ai_batches.csv` khi đang ghi camera của đúng Rig đó. Không ném."""
        try:
            self._ai_batch(result, upd, info or {})
        except Exception as exc:  # noqa: BLE001 - AI vẫn chạy dù không ghi được dòng này
            self._hook_error("ghi lô AI", exc)

    def poll(self) -> list[str]:
        """Mỗi giây (timer của ngăn): mốc định kỳ và trạng thái cửa sổ, ngưỡng đĩa, lỗi ghi, nguồn rời/nối lại/bật muộn,
        hết nguồn; báo XONG / LỖI khi bản ghi ghi nốt xong. Trả các lời báo mới (ghi vào nhật ký của ngăn). Không ném."""
        out, self._pending = list(self._pending), []
        try:
            out += self._poll()
        except Exception as exc:  # noqa: BLE001
            out.append(self._hook_error("kiểm định kỳ", exc))
        return out

    # ---- trạng thái cho giao diện, tệp trỏ ----
    def status(self) -> dict:
        root = Path(self.options.root)
        live = self.live
        base = {"root": str(root), "drive": drive_name(root), "outside_runs": outside_ignored_runs(root),
                "hook_errors": len(self.hook_errors)}
        if live is None:
            free = self.free_bytes(root)
            return {**base, "state": "idle", "free_gb": None if free is None else free / GB, "minutes_left": None}
        rec = live.rec
        st = rec.status()
        if rec.active:
            state = "recording"
        elif not rec.finished.is_set():
            state = "draining"
        else:
            state = "error" if rec.error else "done"
        free = self.free_bytes(rec.folder if rec.folder.exists() else root)
        return {**base, "state": state, "folder": str(rec.folder), "free_gb": None if free is None else free / GB,
                "minutes_left": self._minutes_left(free, st) if state == "recording" else None,
                "elapsed_s": st["elapsed_s"], "frames_total": st["frames_total"], "dropped_total": st["dropped_total"],
                "pending_frames": st["pending_frames"], "lidar_scans": st["lidar_scans"], "mb_written": st["mb_written"],
                "mb_per_s": st["mb_per_s"], "error": st["error"], "ports": list(rec.ports), "cameras": live.cameras,
                "cam_attached": live.cam_attached, "lidar": live.lidar, "lidar_attached": live.lidar_attached,
                "lidar_label": live.lidar_name, "replay": live.replay, "synthetic": live.synthetic,
                "stopped_by": live.stopped_by, "ai_rows": live.ai_rows, "warnings": list(rec.warnings)}

    def export_refs(self) -> dict | None:
        """Nội dung tệp trỏ `<tên>_sensor_recordings.json` của "Xuất log CSV…": mọi bản ghi của cửa sổ này và chúng có phủ
        lần chạy gần nhất không. None khi cửa sổ chưa ghi gì. Bản ghi không bao giờ được chép vào gói phát lại T9."""
        if not self.history:
            return None
        run = None if self.last_run is None else {k: self.last_run[k] for k in ("t_perf_start", "t_perf_end", "end_state")}
        return {"format": REFS_FORMAT, "version": REFS_VERSION,
                "written_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "app": self.app,
                "clock": "t_perf_start, t_perf_end, t_start_s, t_stop_s: perf_counter của máy này (ALIGN_TEXT ở "
                         "meta.json/session_recording/align)",
                "run": run, "recordings": [self._ref(rec, run) for rec in self.history]}

    # ---- bên trong ----
    def _window_state(self) -> str:
        try:
            return str(self.host.window_state())
        except Exception:  # noqa: BLE001
            return "unknown"

    def _ecoqos(self) -> str | None:
        try:
            return self.ecoqos()
        except Exception:  # noqa: BLE001
            return None

    def _hook_error(self, where: str, exc: BaseException) -> str:
        text = f"Lỗi bản ghi cảm biến ({where}): {type(exc).__name__}: {exc} — xe, AI và LiDAR vẫn chạy"
        if len(self.hook_errors) < 20:
            self.hook_errors.append(text)
        return text

    def _anchor(self, trigger: str, note: str = "", t: float | None = None) -> dict | None:
        """Một dòng `session/clock.csv` (chỉ khi đang nhận): perf_counter cùng ngữ cảnh phiên/VehicleIO của cửa sổ."""
        live = self.live
        if live is None or not live.rec.active:
            return None
        t = self.clock() if t is None else t
        try:
            ctx = dict(self.host.anchor_context(t) or {})
        except Exception as exc:  # noqa: BLE001
            ctx = {"note": f"không đọc được ngữ cảnh phiên ({type(exc).__name__}: {exc})"}
        row = {"t_perf": f"{t:.9f}", "t_wall": self.wall().isoformat(timespec="milliseconds"), "trigger": trigger,
               "state": ctx.get("state"), "run": live.run_count, "t_session": ctx.get("t_session"),
               "t_io": ctx.get("t_io"), "io_clock": ctx.get("io_clock"), "time_scale": ctx.get("time_scale"),
               "window": self._window_state(), "note": " · ".join(str(p) for p in (ctx.get("note"), note) if p)}
        live.rec.add_row(CLOCK_TABLE, row)
        live.last_anchor_t = t
        return row

    def _start_block(self, name, session, avail, use_cams, use_lidar, cam_info, lid_info, want_cams, want_lidar, free,
                     window, warnings) -> dict:
        cam = cam_info or {}
        lid = lid_info or {}
        return {"version": SESSION_RECORDING_VERSION, "app": self.app, "name": name, "clock": clock_info(),
                "sources": {
                    "cameras": {"on": use_cams, "kind": cam.get("source_kind"), "ports": avail.camera_ports if use_cams
                                else [], "synthetic": cam.get("synthetic"),
                                "why_off": None if use_cams else ("người dùng bỏ chọn" if not want_cams
                                                                  else avail.reasons.get("cameras"))},
                    "lidar": {"on": use_lidar, "kind": lid.get("kind"), "port": lid.get("port"),
                              "recording": lid.get("recording"),
                              "why_off": None if use_lidar else ("người dùng bỏ chọn" if not want_lidar
                                                                 else avail.reasons.get("lidar"))}},
                "session": {"scenario": session.get("scenario"), "scenario_path": session.get("scenario_path"),
                            "vehicle_config": session.get("vehicle_config"), "drive_mode": session.get("drive_mode"),
                            "board": session.get("board"), "cusp_policy": session.get("cusp_policy"),
                            "state_at_start": session.get("state")},
                "camera_ai": cam_info, "lidar_dock": lid.get("settings"),
                "sync_marks_live_file": session.get("sync_marks_live_file"),
                "ecoqos_start": self._ecoqos(), "window_start": window,
                "disk": {"root": str(self.options.root), "free_gb_start": None if free is None else round(free / GB, 2),
                         "min_free_start_gb": self.options.min_free_gb, "stop_free_gb": self.options.stop_free_gb,
                         "low_minutes_warn": LOW_MINUTES_WARN, "gb": "2^30 byte", "thresholds": THRESHOLDS_NOTE},
                "warnings": list(warnings), "align": ALIGN_TEXT}

    def _recording_meta(self, rig, lid_info: dict | None, name: str, block: dict) -> dict:
        """Phần meta.json ngoài số của bộ ghi: như bản ghi bàn thử (Rig.recording_meta) để rig.replay / rig.bench đọc
        được; không ghi camera thì khối camera rỗng. `lidar_source` là nguồn của ngăn LiDAR (bench đọc khóa port)."""
        notes = {"from": self.app, "name": name}
        if rig is not None:
            meta = rig.recording_meta(notes)
        else:
            meta = {"config": None, "policy": None, "camera_mode": {}, "cameras": [], "replay_of": None, "notes": notes}
        meta["lidar_source"] = None if lid_info is None else {
            "port": lid_info.get("port"), "kind": lid_info.get("kind"), "recording": lid_info.get("recording"),
            "describe": lid_info.get("describe"), "clock": "perf_counter", "open_error": None}
        meta["session_recording"] = block
        return meta

    def _final_block(self, live: _Live, reason: str, sync_rows: int, notes: list[str]) -> dict:
        free = self.free_bytes(live.rec.folder)
        try:
            live_file = (self.host.session_meta() or {}).get("sync_marks_live_file")
        except Exception:  # noqa: BLE001
            live_file = live.block.get("sync_marks_live_file")
        return {**live.block, "stopped_by": reason, "stopped_wall": self.wall().isoformat(timespec="milliseconds"),
                "ecoqos_stop": self._ecoqos(), "free_gb_stop": None if free is None else round(free / GB, 2),
                "detached": [dict(d) for d in live.detached], "ignored_late": [dict(d) for d in live.ignored_late],
                "runs": [dict(r) for r in live.runs], "ai": {"rows": live.ai_rows, "batches_skipped": live.ai_skipped},
                "sync_marks_live_file": live_file, "sync_rows": sync_rows,
                "warnings": list(live.block.get("warnings", [])) + notes, "hook_errors": list(self.hook_errors)}

    def _on_camera_detach(self, live: _Live, info: dict) -> None:
        """Rig của ngăn AI camera gỡ bộ ghi: khi dừng ghi (chỉ lấy số camera lúc dừng) hay khi ngăn tắt AI giữa chừng (mốc
        camera_detached; LiDAR vẫn ghi; Rig bật lại sau đó KHÔNG được gắn lại)."""
        live.cameras_at_stop = list(info.get("cameras_at_stop") or [])
        live.cam_attached = False
        if live.stopping or not live.rec.active:
            return
        t = self.clock()
        why = "AI camera tắt (Rig của ngăn AI camera dừng)"
        live.detached.append({"source": "cameras", "t_perf": t, "why": why})
        self._anchor("camera_detached", why, t=t)
        self._pending.append(f"Camera rời bản ghi: {why}" + (" — LiDAR vẫn ghi" if live.lidar_attached else ""))

    def _state_change(self, old: str, new: str, stop_reason: str) -> None:
        t = self.clock()
        live = self.live if self.active else None
        ending = False
        if new == "RUNNING" and old != "RUNNING":
            self.last_run = {"t_perf_start": t, "t_perf_end": None, "end_state": None, "stop_reason": ""}
            if live is not None:
                live.run_count += 1
                live.runs.append({"run": live.run_count, "t_perf_start": t, "t_perf_end": None, "t_session_end": None,
                                  "end_state": None, "stop_reason": ""})
        elif new not in DRIVING_STATES and self.last_run is not None and self.last_run["t_perf_end"] is None:
            self.last_run.update(t_perf_end=t, end_state=new, stop_reason=stop_reason)
            ending = True
        if live is None:
            return
        note = f"{old}→{new}" + (f": {stop_reason}" if stop_reason and new != "RUNNING" else "")
        row = self._anchor("state_change", note, t=t)
        if ending and live.runs and live.runs[-1]["t_perf_end"] is None:
            live.runs[-1].update(t_perf_end=t, t_session_end=None if row is None else row["t_session"], end_state=new,
                                 stop_reason=stop_reason)

    def _ai_batch(self, result, upd, info: dict) -> None:
        live = self.live
        if live is None or not live.rec.active or not live.ai_table or not live.cam_attached:
            return
        if self.host.camera_rig() is not live.rig:       # Rig khác (bật lại sau khi tắt): khung không vào bản ghi này
            return
        fs = result.frame_set
        batch_id = int(result.batch_id)
        if live.last_batch_id is not None and batch_id > live.last_batch_id + 1:
            live.ai_skipped += batch_id - live.last_batch_id - 1
        live.last_batch_id = batch_id
        row = {"t_perf": f"{self.clock():.9f}", "batch_id": batch_id, "t_done": f"{float(result.t_done):.9f}",
               "anchor_t": f"{float(fs.anchor_t):.9f}", "skew_ms": round(1000.0 * float(fs.skew_s), 3),
               # cùng định dạng %.9f với cột t_s của cam_p<cổng>/frames.csv: nối bằng stamp
               "frames": ";".join(f"{int(p)}:{fs.frames[p].meta.stamp.t:.9f}" for p in sorted(fs.frames)),
               "lagging": _ports(fs.lagging), "deferred": _ports(fs.deferred), "carried": _ports(result.carried),
               "checkpoint": result.checkpoint, "usable": int(bool(upd.usable)), "reasons": " | ".join(upd.reasons),
               "notes": " | ".join(upd.notes), "cameras_used": ";".join(str(c) for c in upd.cameras_used),
               "occupied_batch": upd.occupied_batch, "occupied_filtered": upd.occupied_filtered,
               "window_fill": upd.window_fill, "bev_ms": None if upd.bev_ms is None else round(float(upd.bev_ms), 2),
               "ai_boxes": info.get("ai_boxes"), "injected": info.get("injected"), "state": info.get("state")}
        live.rec.add_row(AI_TABLE, row)
        live.ai_rows += 1

    def _minutes_left(self, free: int | None, st: dict | None = None) -> float | None:
        live = self.live
        if free is None or live is None:
            return None
        rate = (st or live.rec.status()).get("mb_per_s")
        if not rate or rate <= 0:
            return None
        return free / (rate * 2**20) / 60.0

    def _finished_text(self, live: _Live) -> str:
        st = live.rec.status()
        if live.rec.error:
            return f"LỖI GHI: {live.rec.error} — bản ghi {live.rec.folder.name} dừng ở trạng thái lỗi"
        return (f"XONG: {live.rec.folder.name} · {fmt_int(st['frames_total'])} khung · "
                f"{fmt_int(st['lidar_scans'] or 0)} vòng LiDAR · {fmt_dec(st['mb_written'], 0)} MB")

    def _poll(self) -> list[str]:
        live = self.live
        if live is None:
            return []
        rec, out = live.rec, []
        if not rec.active:
            if rec.finished.is_set() and not live.reported:
                live.reported = True
                out.append(self._finished_text(live))
            return out
        now = self.clock()
        if live.last_anchor_t is None or now - live.last_anchor_t >= ANCHOR_PERIOD_S:
            self._anchor("periodic", t=now)
        window = self._window_state()
        if window != live.window:
            self._anchor("window_state", f"cửa sổ {live.window} → {window}")
            live.window = window
        if rec.error is not None:
            self.stop("write_error")
            out.append(f"LỖI GHI: {rec.error} — đã dừng ghi")
            return out
        free = self.free_bytes(rec.folder)
        if free is not None:
            if free < self.options.stop_free_gb * GB:
                text = (f"Dừng ghi tự động: {drive_name(rec.folder)} còn {fmt_dec(free / GB)} GB < "
                        f"{fmt_g(self.options.stop_free_gb)} GB")
                self._anchor("disk_guard", text)
                self.stop("disk_guard")
                out.append(text)
                return out
            minutes = self._minutes_left(free)
            if minutes is not None and minutes < LOW_MINUTES_WARN and not live.disk_warned:
                live.disk_warned = True
                text = (f"Sắp đầy đĩa: {drive_name(rec.folder)} còn {fmt_dec(free / GB)} GB ≈ {minutes:.0f} phút ghi nữa; "
                        f"tự dừng dưới {fmt_g(self.options.stop_free_gb)} GB")
                self._anchor("disk_warning", text)
                out.append(text)
        out += self._poll_sources(live, now)
        if not ((live.cameras and live.cam_attached) or (live.lidar and live.lidar_attached)):
            self.stop("no_sources")
            out.append("Không còn nguồn nào để ghi (AI camera tắt, LiDAR ngắt): đã dừng ghi")
        return out

    def _poll_sources(self, live: _Live, now: float) -> list[str]:
        out = []
        info = self.host.lidar_info()
        key = None if info is None else info.get("source_key")
        if live.lidar:
            if live.lidar_attached and key != live.lidar_key:
                why = "ngăn LiDAR đã ngắt nguồn" if info is None else "ngăn LiDAR đổi nguồn"
                live.lidar_attached = False
                live.detached.append({"source": "lidar", "t_perf": now, "why": why})
                self._anchor("lidar_detached", why, t=now)
                out.append(f"LiDAR rời bản ghi: {why}"
                           + (" — camera vẫn ghi" if live.cameras and live.cam_attached else ""))
            if not live.lidar_attached and info is not None and key not in live.late_seen:
                if info.get("clock_ok"):
                    live.lidar_attached, live.lidar_key = True, key
                    live.lidar_name = lidar_label(info)
                    self._anchor("lidar_attached", f"{info.get('kind')} {lidar_label(info)}", t=now)
                    out.append("LiDAR kết nối lại: vòng quét tiếp tục vào bản ghi")
                else:
                    live.late_seen.add(key)
                    live.ignored_late.append({"source": "lidar", "t_perf": now, "why": info.get("why")})
                    out.append(f"LiDAR kết nối lại nhưng {info.get('why')}: không vào bản ghi này")
        elif info is not None and key != live.start_lidar_key and "lidar" not in live.late_seen:
            live.late_seen.add("lidar")
            live.ignored_late.append({"source": "lidar", "t_perf": now, "why": "bật sau khi bắt đầu ghi"})
            out.append("LiDAR bật sau khi bắt đầu ghi: không vào bản ghi này")
        rig = self.host.camera_rig()
        if rig is not None and rig is not live.start_rig and "cameras" not in live.late_seen:
            live.late_seen.add("cameras")
            live.ignored_late.append({"source": "cameras", "t_perf": now, "why": "bật sau khi bắt đầu ghi"})
            out.append("AI camera bật sau khi bắt đầu ghi: không vào bản ghi này")
        return out

    def _ref(self, rec: RigRecorder, run: dict | None) -> dict:
        st = rec.status()
        finished = rec.finished.is_set()
        status = ("lỗi" if rec.error else "xong") if finished else ("đang ghi" if rec.active else "đang ghi nốt")
        t0, t1 = rec.t_start, rec.t_stop
        overlap = covers = None
        if run is not None and t0 is not None:
            now = self.clock()
            r0 = run["t_perf_start"]
            r1 = now if run["t_perf_end"] is None else run["t_perf_end"]
            end = now if t1 is None else t1
            overlap = round(max(0.0, min(end, r1) - max(t0, r0)), 3)
            covers = bool(t0 <= r0 and end >= r1)
        return {"folder": str(rec.folder), "folder_rel": _project_rel(rec.folder), "status": status, "t_start_s": t0,
                "t_stop_s": t1, "created_utc": rec.created_utc, "overlap_s": overlap, "covers_run": covers,
                "frames_total": st["frames_total"], "lidar_scans": st["lidar_scans"],
                "meta_sha256": _sha256(rec.folder / META_FILE) if finished else None}


# ------------------------------------------------------------------------------------------------ đọc mốc đồng hồ

def _float(text) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class ClockRow:
    """Một dòng của session/clock.csv (`CLOCK_FIELDS`); ô trống → None."""
    t_perf: float
    t_wall: str = ""
    trigger: str = ""
    state: str = ""
    run: int = 0
    t_session: float | None = None
    t_io: float | None = None
    io_clock: str = ""
    time_scale: float | None = None
    window: str = ""
    note: str = ""

    @classmethod
    def from_csv(cls, row: dict) -> "ClockRow | None":
        t_perf = _float(row.get("t_perf"))
        if t_perf is None:
            return None
        run = _float(row.get("run"))
        return cls(t_perf, row.get("t_wall") or "", row.get("trigger") or "", row.get("state") or "",
                   0 if run is None else int(run), _float(row.get("t_session")), _float(row.get("t_io")),
                   row.get("io_clock") or "", _float(row.get("time_scale")), row.get("window") or "",
                   row.get("note") or "")


class SessionClock:
    """Đổi perf_counter của một bản ghi trong phiên đỗ sang đồng hồ VehicleIO thời gian thực (`to_io`) và thời gian phiên
    (`to_session`) bằng các mốc session/clock.csv — quy tắc (a), (b) của `ALIGN_TEXT`."""

    def __init__(self, rows: list[ClockRow]):
        self.rows = sorted(rows, key=lambda r: r.t_perf)
        self.segments = self._run_segments()

    def realtime_offset(self) -> float | None:
        """Trung vị t_perf − t_io trên các mốc của VehicleIO thời gian thực; None khi không có mốc nào như thế."""
        diffs = [r.t_perf - r.t_io for r in self.rows if r.io_clock == "realtime" and r.t_io is not None]
        return statistics.median(diffs) if diffs else None

    def to_io(self, t_perf: float) -> float | None:
        offset = self.realtime_offset()
        return None if offset is None else t_perf - offset

    def to_session(self, t_perf: float) -> float | None:
        """Thời gian phiên lúc `t_perf`: nội suy tuyến tính giữa hai mốc của CÙNG lần chạy ở hai phía. None ngoài mọi lần
        chạy đã ghi (trước mốc đầu, giữa hai lần chạy, sau mốc cuối)."""
        for seg in self.segments:
            if not seg[0].t_perf <= t_perf <= seg[-1].t_perf:
                continue
            for a, b in zip(seg, seg[1:]):
                if a.t_perf <= t_perf <= b.t_perf:
                    if b.t_perf == a.t_perf:
                        return a.t_session
                    return a.t_session + (t_perf - a.t_perf) * (b.t_session - a.t_session) / (b.t_perf - a.t_perf)
            return seg[0].t_session
        return None

    def _run_segments(self) -> list[list[ClockRow]]:
        """Mỗi lần chạy: các mốc từ mốc đầu ở RUNNING tới mốc đầu tiên đã rời RUNNING/STOPPING (bước chuyển sang
        STOPPED/COMPLETED/FAULT…), chỉ mốc có t_session."""
        segments, current = [], None
        for row in self.rows:
            if row.t_session is None:
                continue
            if row.state in DRIVING_STATES and row.run > 0:
                if current is not None and current[-1].run != row.run:
                    segments.append(current)
                    current = None
                current = [row] if current is None else current + [row]
            elif current is not None:
                if row.run == current[-1].run:
                    current.append(row)
                segments.append(current)
                current = None
        if current:
            segments.append(current)
        return segments


def read_session_clock(folder) -> SessionClock:
    """Mốc session/clock.csv của một bản ghi trong phiên đỗ (dòng hỏng bị bỏ)."""
    path = Path(folder) / CLOCK_TABLE
    with open(path, newline="", encoding="utf-8") as handle:
        rows = [ClockRow.from_csv(r) for r in csv.DictReader(handle)]
    return SessionClock([r for r in rows if r is not None])


__all__ = ["AI_FIELDS", "AI_TABLE", "ALIGN_TEXT", "Availability", "CLOCK_FIELDS", "CLOCK_TABLE", "ClockRow",
           "DEFAULT_ROOT", "RecordOptions", "RecordStartError", "RecordingHost", "SYNC_COPY", "SessionClock",
           "SessionSensorRecorder", "clean_name", "disk_free_bytes", "read_session_clock"]
