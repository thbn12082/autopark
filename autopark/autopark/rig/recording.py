"""Ghi một phiên bàn thử — bốn camera + LiDAR — ra thư mục, để phát lại không cần thiết bị (`autopark.rig.replay`).

Bật bằng `python -m autopark.rig.bench --record <thư mục>` hoặc nút "Ghi phiên" của `ui/rig_app.py`. Cách dùng, định dạng
và giới hạn: docs/VAN_HANH.md.

Ghi gì:
- MỌI khung TỐT mà nguồn camera trả cho `CameraWorker` — tức là SAU khi `UsbCameraSource` đã loại khung cũ, khung bị cắt
  và khung xé — kèm stamp trên đồng hồ bàn thử (`RIG_CLOCK`, lúc `read()` trả khung);
- mọi lần đọc hỏng (khung cũ, khung bị cắt, khung xé, đọc lỗi, ngoại lệ khác) thành SỰ KIỆN có stamp và nguyên văn thông
  báo, để lúc phát lại nguồn ném lại đúng lỗi đó đúng lúc: bộ đếm của `MultiCameraManager` và nhịp khung đo trên
  `CameraWorker.arrivals` (gồm cả khung cắt/xé) ra như lúc ghi. Ảnh của khung hỏng KHÔNG được ghi;
- mọi vòng LiDAR theo định dạng npz của `lidar/recording.py` (`ScanRecorder`), stamp đổi sang đồng hồ bàn thử (stamp của
  driver + `t0`), cùng lỗi đọc LiDAR.

Thư mục (format_version 1):
    meta.json                  cấu hình Rig, quy tắc ghép bộ, mode camera, từng camera (cổng, index, instance_id, lỗi mở),
                               đồng hồ, commit git, giờ tạo, ghi chú, trạng thái ("đang ghi" → "xong" / "lỗi"), số đếm
    cam_p<cổng>/frames.csv     seq, t_s, width, height, file, bytes — một dòng cho mỗi khung tốt ĐÃ ghi xuống đĩa
    cam_p<cổng>/events.csv     t_s, kind, after_seq, message — kind: duplicate / truncated / torn / read_failed /
                               exception (như nguồn báo) hoặc record_dropped (bộ ghi bỏ khung vì hàng đợi đầy)
    cam_p<cổng>/0000001.jpg    ảnh; JPEG chất lượng 95 mặc định, PNG (không mất mát, lớn hơn ≈ 4,5 lần) khi chọn
    lidar/part_0000.npz, .json tối đa 600 vòng (≈ 60 s) mỗi phần; mỗi phần đọc được bằng `lidar.recording.read_recording`
    lidar/events.csv           t_s, message — lỗi đọc LiDAR

Luồng: `Rig` bọc nguồn camera và LiDAR (`CameraTap`, `LidarTap`); khi đang ghi, lớp bọc đẩy khung/sự kiện vào hàng đợi
của `RigRecorder` và trả ngay — luồng camera không bao giờ chờ đĩa. MỘT luồng nền mã hóa và ghi (`cv2.imencode` nhả GIL).
Hàng đợi giới hạn theo byte ảnh CHƯA ghi (mặc định 192 MB ≈ 2 s của bốn camera 480p); đầy thì khung bị BỎ, đếm ở
`dropped` và ghi một dòng `record_dropped` — không âm thầm. Lỗi ghi (đĩa đầy, mất quyền, …) được giữ ở `error`, trạng thái
thành "LỖI", mọi khung sau đó bị bỏ và đếm; giao diện báo đỏ, bench trả mã 1. LiDAR giữ trong RAM tối đa một phần (600
vòng × ≈ 510 tia ≈ 2,8 MB). Ghi `cv2.imencode` + `write_bytes` (cv2.imwrite không ghi được vào đường dẫn tiếng Việt).

Cỡ và tốc độ (đo 24/09/2026 trên máy bàn i9-14900, bằng ảnh thật đã chụp ngày 23/09 trong `runs/rig_snapshots/`, camera nằm
trên bàn nhìn thảm hoa văn — KHÔNG phải số đo một phiên ghi trên phần cứng): JPEG q95 640×480 150–174 KB/khung, mã hóa
0,7 ms; 1280×720 430–524 KB, 2,3 ms; PNG 640×480 ≈ 700 KB, 7,7 ms. Bốn camera × ≈ 24 khung tốt/s × ≈ 160 KB ≈ 15 MB/s
≈ 0,9 GB/phút ở 480p — gấp mấy lần ước lượng "vài chục KB/khung" ban đầu; cảnh ít chi tiết thì nhỏ hơn.

Thêm 02/10/2026 cho bản ghi cảm biến trong phiên đỗ (T3, `rig.session_recording`), không đổi gì của bench/rig_app:
- `tables` (đường dẫn CSV tương đối → cột): bảng phụ mở cùng các CSV khác lúc `start()`, nhận dòng bằng `add_row` (không
  chặn, như sự kiện), flush sau mỗi lô; `add_csv_file` ghi trọn một tệp CSV ở luồng ghi (ví dụ bản sao dấu đồng bộ lúc dừng).
  meta.json có thêm `tables` (cột, số dòng), `files`, `warnings`.
- Bộ ghi NGOÀI gắn vào một `Rig` (`Rig.attach_recorder`): Rig chỉ đưa khung camera vào, không bao giờ dừng hay chờ nó.
- Vòng LiDAR có stamp sớm hơn vòng đã ghi trước nó bị BỎ và đếm (`lidar.out_of_order_dropped`, `warnings`) thay vì làm
  hỏng cả bản ghi như trước (ScanRecorder từ chối stamp lùi): nguồn LiDAR của ngăn LiDAR có thể được nối lại giữa chừng.
- `LidarTap(ignore=...)`: ngoại lệ thuộc các loại đó vẫn ném lại nhưng không ghi thành lỗi đọc LiDAR (hết bản ghi phát
  lại không phải lỗi đọc).
"""
from __future__ import annotations

from collections import deque
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import threading
from typing import Callable, Iterable, Mapping, Sequence

import cv2
import numpy as np

from autopark.domain.sensors import LidarScan, SourceStamp
from autopark.lidar.recording import RECORDING_VERSION, ScanRecorder, git_commit
from autopark.power_throttling import ecoqos_state
from autopark.video.multicam import RIG_CLOCK, clock_info
from autopark.video.sources import FrameReadError

FORMAT = "autopark.rig_recording"
FORMAT_VERSION = 1
META_FILE = "meta.json"
FRAMES_CSV = "frames.csv"
EVENTS_CSV = "events.csv"
FRAME_FIELDS = ("seq", "t_s", "width", "height", "file", "bytes")
EVENT_FIELDS = ("t_s", "kind", "after_seq", "message")
LIDAR_DIR = "lidar"
LIDAR_EVENT_FIELDS = ("t_s", "message")
IMAGE_FORMATS = ("jpg", "png")
DEFAULT_JPEG_QUALITY = 95
PNG_COMPRESSION = 1                 # nén nhẹ: PNG chỉ để test / đoạn ngắn cần đúng từng pixel
DEFAULT_MAX_PENDING_MB = 192.0      # ≈ 2 s của bốn camera 640×480 (921 600 byte/khung chưa mã hóa)
LIDAR_SCANS_PER_PART = 600          # ≈ 60 s ở 10 Hz
CAMERA_EVENT_KINDS = ("duplicate", "truncated", "torn", "read_failed", "exception")
RECORD_DROPPED = "record_dropped"


def camera_dir(port: int) -> str:
    return f"cam_p{port}"


def relative_file(relpath: str) -> str:
    """Đường dẫn tệp phụ trong thư mục ghi (bảng `tables`, tệp `add_csv_file`): tương đối, không `..`, dạng a/b.csv."""
    path = Path(str(relpath).replace("\\", "/"))
    if path.is_absolute() or path.drive or not path.parts or ".." in path.parts:
        raise ValueError(f"tệp phụ phải là đường dẫn tương đối trong thư mục ghi, không có '..' (nhận {relpath!r})")
    return path.as_posix()


def event_kind(message: str) -> str:
    """Loại sự kiện theo đúng cách `CameraWorker._count_error` phân loại thông báo của nguồn."""
    if "previous frame" in message:
        return "duplicate"
    if "truncated frame" in message:
        return "truncated"
    if "torn frame" in message:
        return "torn"
    return "read_failed"


def _clean(value):
    """JSON chặt: số không hữu hạn → None, numpy → Python, khóa → chuỗi, còn lại không biết → str."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (bool, type(None), str)):
        return value
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, Path):
        return str(value)
    return str(value)


def write_json_atomic(path: Path, value) -> None:
    """Ghi qua tệp tạm rồi đổi tên: người đọc không bao giờ thấy meta.json dở dang."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(_clean(value), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


class RigRecorder:
    """Ghi khung camera, sự kiện đọc hỏng và vòng LiDAR của một phiên bàn thử (xem đầu module).

    `add_*` được gọi từ luồng camera/LiDAR, không chặn; một luồng nền ghi. `stop()` ngừng nhận, ghi nốt hàng đợi, đóng
    phần LiDAR cuối, ghi meta.json cuối. Lỗi không bao giờ bị nuốt: `error`, `errors`, `state` == "LỖI"."""

    def __init__(self, folder, *, ports, lidar: bool = False, meta: dict | None = None, clock=RIG_CLOCK,
                 image_format: str = "jpg", jpeg_quality: int = DEFAULT_JPEG_QUALITY,
                 max_pending_mb: float = DEFAULT_MAX_PENDING_MB, lidar_scans_per_part: int = LIDAR_SCANS_PER_PART,
                 tables: Mapping[str, Sequence[str]] | None = None):
        """`tables`: bảng phụ (đường dẫn CSV tương đối → cột), nhận dòng bằng `add_row` (T3, 02/10/2026)."""
        if image_format not in IMAGE_FORMATS:
            raise ValueError(f"image_format phải là một trong {IMAGE_FORMATS}")
        if not 1 <= int(jpeg_quality) <= 100:
            raise ValueError("jpeg_quality phải trong 1..100")
        if not max_pending_mb > 0 or lidar_scans_per_part < 1:
            raise ValueError("max_pending_mb phải > 0 và lidar_scans_per_part ≥ 1")
        self.folder = Path(folder)
        self.ports = [int(p) for p in ports]
        self.lidar = bool(lidar)
        self.base_meta = dict(meta or {})
        self.final_meta: dict = {}
        self.clock = clock
        self.image_format, self.jpeg_quality = image_format, int(jpeg_quality)
        self._params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality] if image_format == "jpg" else \
            [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION]
        self.max_pending_bytes = int(max_pending_mb * 2**20)
        self.lidar_scans_per_part = int(lidar_scans_per_part)
        self._cond = threading.Condition()
        self._items: deque = deque()
        self._pending_bytes = 0
        self._pending_frames = 0
        self._accepting = False
        self._stopping = False
        self._thread: threading.Thread | None = None
        self.finished = threading.Event()
        self._seq = {p: 0 for p in self.ports}                    # khung tốt đã THẤY (kể cả khung bị bỏ)
        self.written = {p: 0 for p in self.ports}                 # khung đã ghi xuống đĩa
        self.dropped = {p: 0 for p in self.ports}                 # khung bị bỏ: hàng đợi đầy hoặc sau lỗi ghi
        self.events = {p: {} for p in self.ports}                 # loại sự kiện → số lần
        self.first_t: dict[int, float | None] = {p: None for p in self.ports}
        self.last_t: dict[int, float | None] = {p: None for p in self.ports}
        self.bytes_written = 0
        self.lidar_scans = 0
        self.lidar_events = 0
        self.lidar_parts: list[str] = []
        self.error: str | None = None
        self.errors: list[str] = []
        self.t_start: float | None = None
        self.t_stop: float | None = None
        self.created_utc: str | None = None
        self.created_local: str | None = None
        self.git_commit: str | None = None
        self._files: list = []
        self._frames_csv: dict[int, csv.writer] = {}
        self._events_csv: dict[int, csv.writer] = {}
        self._lidar_csv = None
        self._lidar_part: ScanRecorder | None = None
        # T3 (02/10/2026): bảng phụ, tệp CSV trọn vẹn, cảnh báo, vòng LiDAR lùi thời gian (bỏ và đếm)
        self.tables = {relative_file(name): tuple(fields) for name, fields in (tables or {}).items()}
        self.table_rows = {name: 0 for name in self.tables}
        self._tables_csv: dict[str, csv.writer] = {}
        self.files: list[str] = []
        self.warnings: list[str] = []
        self.lidar_out_of_order = 0
        self._last_scan_t: float | None = None

    # ---- vòng đời ------------------------------------------------------------------------------------------------
    def start(self) -> "RigRecorder":
        if self._thread is not None:
            raise RuntimeError("bộ ghi đã chạy")
        if self.folder.exists() and any(self.folder.iterdir()):
            raise FileExistsError(f"thư mục ghi đã có dữ liệu, không ghi đè: {self.folder}")
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            for port in self.ports:
                d = self.folder / camera_dir(port)
                d.mkdir(exist_ok=True)
                self._frames_csv[port] = self._open_csv(d / FRAMES_CSV, FRAME_FIELDS)
                self._events_csv[port] = self._open_csv(d / EVENTS_CSV, EVENT_FIELDS)
            if self.lidar:
                (self.folder / LIDAR_DIR).mkdir(exist_ok=True)
                self._lidar_csv = self._open_csv(self.folder / LIDAR_DIR / EVENTS_CSV, LIDAR_EVENT_FIELDS)
            for name, fields in self.tables.items():
                (self.folder / name).parent.mkdir(parents=True, exist_ok=True)
                self._tables_csv[name] = self._open_csv(self.folder / name, fields)
            self._flush()
        except BaseException:
            self._close_files()
            raise
        # t_start = lúc bắt đầu NHẬN dữ liệu (ghi meta.json đầu mất vài chục ms trên Windows: làm sau, ở dưới). `Rig` gán
        # bộ ghi cho lớp bọc TRƯỚC khi gọi start(), nên mọi khung tốt có stamp ≥ t_start đều tới đây: được ghi hoặc được
        # đếm là bị bỏ. Bật nhận TRƯỚC khi đọc đồng hồ: khung nào lấy stamp sau t_start thì chắc chắn thấy _accepting.
        now = datetime.now(timezone.utc)
        with self._cond:
            self._accepting = True
            self.t_start = self.clock()
        self.created_utc = now.isoformat(timespec="milliseconds")
        self.created_local = now.astimezone().isoformat(timespec="milliseconds")
        self._thread = threading.Thread(target=self._run, daemon=True, name="rig-recorder")
        self._thread.start()
        try:
            write_json_atomic(self.folder / META_FILE, self.meta("đang ghi"))
        except BaseException:
            self.stop(wait=True, timeout=5.0)       # luồng ghi đóng tệp; meta.json cuối có thể ghi được hay không
            raise
        return self

    def set_final_meta(self, **values) -> None:
        """Thêm vào meta.json cuối (ví dụ số đếm camera lúc dừng, lỗi mở camera) — gọi trước `stop()`."""
        self.final_meta.update(values)

    def stop(self, wait: bool = True, timeout: float | None = None) -> dict:
        """Ngừng nhận khung; luồng nền ghi nốt hàng đợi rồi đóng tệp và ghi meta.json cuối. `wait=False` trả ngay
        (giao diện không đứng hình khi còn nhiều khung chờ ghi); theo dõi bằng `finished` / `status()`."""
        with self._cond:
            if self._thread is None:
                return self.status()
            self._accepting = False
            if self.t_stop is None:
                self.t_stop = self.clock()
            self._stopping = True
            self._cond.notify_all()
        if wait:
            self.finished.wait(timeout)
        return self.status()

    @property
    def active(self) -> bool:
        return self._accepting

    @property
    def state(self) -> str:
        if self._thread is None:
            return "chưa chạy"
        if self.finished.is_set():
            return "LỖI" if self.error else "xong"
        if self.error:
            return "LỖI"
        return "đang ghi nốt" if self._stopping else "đang ghi"

    # ---- nhận dữ liệu (luồng camera / LiDAR) ---------------------------------------------------------------------
    def add_frame(self, port: int, frame) -> None:
        """Một khung tốt. Không chặn: hàng đợi đầy (theo byte ảnh chưa ghi) hay đã lỗi ghi thì bỏ và đếm."""
        if not self._accepting or port not in self._seq:
            return
        nbytes = int(frame.image.nbytes)
        with self._cond:
            if not self._accepting:
                return
            seq = self._seq[port] = self._seq[port] + 1
            if self.error is not None:
                self.dropped[port] += 1
                return
            if self._pending_frames and self._pending_bytes + nbytes > self.max_pending_bytes:
                self.dropped[port] += 1
                self._items.append(("dropped", port, seq, frame.meta.stamp.t, self._pending_bytes))
            else:
                self._pending_bytes += nbytes
                self._pending_frames += 1
                self._items.append(("frame", port, seq, frame))
            self._cond.notify()

    def add_event(self, port: int, kind: str, t: float, message: str) -> None:
        """Một lần đọc hỏng của camera (không có ảnh)."""
        if not self._accepting or port not in self._seq:
            return
        with self._cond:
            if not self._accepting:
                return
            self.events[port][kind] = self.events[port].get(kind, 0) + 1
            self._items.append(("event", port, float(t), kind, self._seq[port], message))
            self._cond.notify()

    def add_scan(self, scan: LidarScan, t_abs: float, t_first_abs: float | None, quality=None) -> None:
        """Một vòng LiDAR; `t_abs`, `t_first_abs` trên đồng hồ bàn thử. Không bao giờ bị bỏ vì hàng đợi (nhỏ: ≈ 4,6 KB);
        chỉ vòng có `t_abs` sớm hơn vòng đã ghi trước bị bỏ và đếm (`lidar_out_of_order`, T3 02/10/2026)."""
        if not self._accepting or not self.lidar:
            return
        with self._cond:
            if self._accepting:
                self._items.append(("scan", scan, float(t_abs), t_first_abs, quality))
                self._cond.notify()

    def add_lidar_event(self, t: float, message: str) -> None:
        if not self._accepting or not self.lidar:
            return
        with self._cond:
            if self._accepting:
                self.lidar_events += 1
                self._items.append(("lidar_event", float(t), message))
                self._cond.notify()

    def add_row(self, table: str, row: Mapping[str, object]) -> None:
        """Một dòng của bảng phụ `table` (khóa của `tables`; cột thiếu hay None ghi ô trống). Không chặn; không bao giờ bị
        bỏ khi bộ ghi đang nhận (dòng nhỏ); bảng lạ hay bộ ghi chưa/không còn nhận thì bỏ qua; sau lỗi ghi thì không ghi
        (như sự kiện camera). Số dòng đã ghi ở `table_rows`."""
        if not self._accepting or table not in self.tables:
            return
        values = dict(row)
        with self._cond:
            if self._accepting:
                self._items.append(("row", table, values))
                self._cond.notify()

    def add_csv_file(self, relpath: str, fields: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
        """Một tệp CSV trọn vẹn (`relpath` tương đối trong thư mục ghi), ghi ở luồng ghi SAU mọi mục đang chờ. Gọi khi bộ
        ghi còn nhận, tức trước `stop()`; sau đó thì bỏ qua. Vẫn thử ghi cả khi đã có lỗi ghi (tệp riêng, như phần LiDAR
        còn trong RAM); ghi được thì tên tệp vào `files`, không được thì vào `errors`."""
        name = relative_file(relpath)
        if not self._accepting:
            return
        item = ("csv_file", name, tuple(fields), [dict(r) for r in rows])
        with self._cond:
            if self._accepting:
                self._items.append(item)
                self._cond.notify()

    # ---- luồng ghi -----------------------------------------------------------------------------------------------
    def _run(self) -> None:
        try:
            # commit git hỏi ở luồng này (tiến trình git mất vài chục ms: hỏi trong start() thì khung tới lúc đó bị mất);
            # meta.json đầu có git_commit = None, meta.json cuối có giá trị
            try:
                self.git_commit = git_commit()
            except Exception as exc:  # noqa: BLE001 - không biết commit không làm hỏng bản ghi; ghi rõ lý do
                self.git_commit = f"không đọc được: {type(exc).__name__}: {exc}"
            while True:
                with self._cond:
                    while not self._items and not self._stopping:
                        self._cond.wait(0.25)
                    if not self._items and self._stopping:
                        break
                    batch = list(self._items)
                    self._items.clear()
                for item in batch:
                    self._handle(item)
                if self.error is None:
                    try:
                        self._flush()
                    except Exception as exc:  # noqa: BLE001 - lỗi đĩa phải hiện ra, không làm chết luồng im lặng
                        self._fail("ghi csv", exc)
        finally:
            self._finish()

    def _handle(self, item: tuple) -> None:
        kind = item[0]
        if kind == "frame":
            _, port, seq, frame = item
            try:
                if self.error is None:
                    self._write_frame(port, seq, frame)
                else:
                    self.dropped[port] += 1
            except Exception as exc:  # noqa: BLE001
                self._fail(f"ghi khung cổng {port} seq {seq}", exc)
                self.dropped[port] += 1
            finally:
                with self._cond:
                    self._pending_bytes -= int(frame.image.nbytes)
                    self._pending_frames -= 1
            return
        if kind == "scan":                      # vào RAM (phần LiDAR hiện hành), đĩa chỉ bị đụng khi đủ một phần
            try:
                self._write_scan(*item[1:])
            except Exception as exc:  # noqa: BLE001
                self._fail("ghi vòng LiDAR", exc)
            return
        if kind == "csv_file":                  # tệp riêng: thử cả sau lỗi ghi
            try:
                self._write_csv_file(*item[1:])
            except Exception as exc:  # noqa: BLE001
                self._fail(f"ghi {item[1]}", exc)
            return
        if self.error is not None:
            return
        try:
            if kind == "row":
                _, table, values = item
                self._tables_csv[table].writerow(["" if values.get(f) is None else values.get(f)
                                                  for f in self.tables[table]])
                self.table_rows[table] += 1
            elif kind == "dropped":
                _, port, seq, t, pending = item
                self._events_csv[port].writerow([f"{t:.9f}", RECORD_DROPPED, seq - 1,
                                                 f"hàng đợi ghi đầy ({pending / 2**20:.0f} MB chưa ghi): bỏ khung seq {seq}"])
            elif kind == "event":
                _, port, t, ev_kind, after_seq, message = item
                self._events_csv[port].writerow([f"{t:.9f}", ev_kind, after_seq, message])
            elif kind == "lidar_event":
                _, t, message = item
                self._lidar_csv.writerow([f"{t:.9f}", message])
        except Exception as exc:  # noqa: BLE001
            self._fail(f"ghi {kind}", exc)

    def _write_frame(self, port: int, seq: int, frame) -> None:
        ok, buf = cv2.imencode("." + self.image_format, frame.image, self._params)
        if not ok:
            raise RuntimeError(f"cv2.imencode không mã hóa được khung cổng {port} seq {seq}")
        name = f"{seq:07d}.{self.image_format}"
        data = buf.tobytes()
        self._write_bytes(self.folder / camera_dir(port) / name, data)
        t = frame.meta.stamp.t
        self._frames_csv[port].writerow([seq, f"{t:.9f}", frame.meta.width, frame.meta.height, name, len(data)])
        self.written[port] += 1
        self.bytes_written += len(data)
        if self.first_t[port] is None:
            self.first_t[port] = t
        self.last_t[port] = t

    def _write_bytes(self, path: Path, data: bytes) -> None:
        path.write_bytes(data)

    def _write_csv_file(self, name: str, fields: tuple, rows: list[dict]) -> None:
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(fields)
            for values in rows:
                writer.writerow(["" if values.get(f) is None else values.get(f) for f in fields])
        self.files.append(name)

    def _warn(self, message: str) -> None:
        if len(self.warnings) < 20:
            self.warnings.append(message)

    def _write_scan(self, scan: LidarScan, t_abs: float, t_first_abs: float | None, quality) -> None:
        if self._last_scan_t is not None and t_abs < self._last_scan_t:
            # stamp lùi so với vòng đã ghi trước (ví dụ nguồn LiDAR được nối lại với đồng hồ khác): ScanRecorder và
            # Recording từ chối stamp giảm, nên bỏ vòng này và đếm, thay vì làm hỏng cả bản ghi (T3, 02/10/2026)
            self.lidar_out_of_order += 1
            if self.lidar_out_of_order == 1:
                self._warn(f"vòng LiDAR có stamp {t_abs:.6f} s sớm hơn vòng đã ghi trước ({self._last_scan_t:.6f} s): "
                           "bỏ và đếm ở lidar.out_of_order_dropped")
            return
        self._last_scan_t = t_abs
        if self._lidar_part is None:
            k = len(self.lidar_parts)
            self._lidar_part = ScanRecorder(self.folder / LIDAR_DIR / f"part_{k:04d}", {
                "recording_version": RECORDING_VERSION, "source_id": scan.stamp.source_id, "part": k,
                "rig_recording": self.folder.name, "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "host": platform.node(), "git_commit": self.git_commit, "clock": clock_info(),
                "stamps": "t, t_first: đồng hồ bàn thử (perf_counter, giây) = stamp driver + t0; không phải giờ phiên driver"})
        n = len(scan.angles_rad)
        q = None if quality is None or len(quality) != n else np.asarray(quality, np.uint8)
        rebased = LidarScan(SourceStamp(scan.stamp.source_id, t_abs, True, "lidar"), scan.angles_rad, scan.ranges_m)
        self._lidar_part.add(rebased, quality=q, t_first=t_abs if t_first_abs is None else float(t_first_abs))
        self.lidar_scans += 1
        if len(self._lidar_part) >= self.lidar_scans_per_part:
            self._close_lidar_part()

    def _close_lidar_part(self) -> None:
        part, self._lidar_part = self._lidar_part, None
        if part is not None and len(part):
            path = part.close()
            self.lidar_parts.append(f"{LIDAR_DIR}/{path.name}")

    def _fail(self, where: str, exc: BaseException) -> None:
        message = f"{where}: {type(exc).__name__}: {exc}"
        if self.error is None:
            self.error = message
        if len(self.errors) < 20:
            self.errors.append(message)

    def _open_csv(self, path: Path, fields) -> csv.writer:
        handle = open(path, "w", newline="", encoding="utf-8")
        self._files.append(handle)
        writer = csv.writer(handle)
        writer.writerow(fields)
        return writer

    def _flush(self) -> None:
        for handle in self._files:
            handle.flush()

    def _close_files(self) -> None:
        for handle in self._files:
            try:
                handle.close()
            except Exception as exc:  # noqa: BLE001
                self._fail("đóng csv", exc)
        self._files.clear()

    def _finish(self) -> None:
        try:                                    # cả khi đã lỗi ghi ảnh: vòng LiDAR còn trong RAM vẫn đáng thử ghi
            self._close_lidar_part()
        except Exception as exc:  # noqa: BLE001
            self._fail("ghi phần LiDAR", exc)
        self._close_files()
        if self.t_stop is None:
            self.t_stop = self.clock()
        try:
            write_json_atomic(self.folder / META_FILE, self.meta("xong" if self.error is None else "lỗi"))
        except Exception as exc:  # noqa: BLE001
            self._fail("ghi meta.json", exc)
        self.finished.set()

    # ---- meta, trạng thái ----------------------------------------------------------------------------------------
    def meta(self, status: str) -> dict:
        per_port = {p: {"folder": camera_dir(p), "frames_seen": self._seq[p], "frames_written": self.written[p],
                        "frames_dropped": self.dropped[p], "events": dict(self.events[p]),
                        "first_t_s": self.first_t[p], "last_t_s": self.last_t[p]} for p in self.ports}
        return {"format": FORMAT, "format_version": FORMAT_VERSION, "status": status,
                "created_utc": self.created_utc, "created_local": self.created_local,
                "host": platform.node(), "python": platform.python_version(), "ecoqos": ecoqos_state(),
                "opencv": cv2.__version__, "git_commit": self.git_commit,
                "clock": clock_info(), "t_start_s": self.t_start, "t_stop_s": self.t_stop,
                "stamps": "đồng hồ bàn thử (perf_counter, giây). Camera: lúc read() trả khung (gồm giải mã), không phải lúc "
                          "phơi sáng. LiDAR: lúc byte cuối của vòng tới máy. created_utc ứng với t_start_s.",
                "image": {"format": self.image_format,
                          "jpeg_quality": self.jpeg_quality if self.image_format == "jpg" else None,
                          "png_compression": PNG_COMPRESSION if self.image_format == "png" else None},
                "ports": self.ports, **self.base_meta,
                "per_port": per_port,
                "lidar": None if not self.lidar else {"folder": LIDAR_DIR, "parts": list(self.lidar_parts),
                                                      "scans": self.lidar_scans, "events": self.lidar_events,
                                                      "scans_per_part": self.lidar_scans_per_part,
                                                      "out_of_order_dropped": self.lidar_out_of_order},
                "writer": {"max_pending_mb": self.max_pending_bytes / 2**20, "bytes_written": self.bytes_written},
                "tables": {name: {"fields": list(fields), "rows": self.table_rows[name]}
                           for name, fields in self.tables.items()},
                "files": list(self.files), "warnings": list(self.warnings),
                "error": self.error, "errors": list(self.errors), **self.final_meta}

    def status(self) -> dict:
        now = self.clock()
        with self._cond:
            pending_frames, pending_bytes = self._pending_frames, self._pending_bytes
            seen = dict(self._seq)
            events = {p: dict(v) for p, v in self.events.items()}
        end = self.t_stop if self.t_stop is not None else now
        elapsed = None if self.t_start is None else max(0.0, end - self.t_start)
        mb = self.bytes_written / 2**20
        return {"folder": str(self.folder), "state": self.state, "error": self.error, "errors": list(self.errors),
                "image_format": self.image_format,
                "jpeg_quality": self.jpeg_quality if self.image_format == "jpg" else None,
                "elapsed_s": None if elapsed is None else round(elapsed, 2),
                "frames": dict(self.written), "frames_seen": seen, "dropped": dict(self.dropped), "events": events,
                "frames_total": sum(self.written.values()), "dropped_total": sum(self.dropped.values()),
                "lidar_scans": self.lidar_scans if self.lidar else None, "lidar_parts": len(self.lidar_parts),
                "lidar_events": self.lidar_events if self.lidar else None,
                "pending_frames": pending_frames, "pending_mb": round(pending_bytes / 2**20, 1),
                "mb_written": round(mb, 2), "mb_per_s": round(mb / elapsed, 2) if elapsed else None,
                "tables": dict(self.table_rows), "lidar_out_of_order": self.lidar_out_of_order if self.lidar else None}


# ------------------------------------------------------------------------------------------------ lớp bọc nguồn

class CameraTap:
    """Bọc nguồn camera của một `CameraWorker`: trả nguyên kết quả `read()` (khung hoặc lỗi), và khi đang ghi thì đẩy
    khung tốt / sự kiện đọc hỏng vào `sink()` (bộ ghi hiện hành hoặc None). Thuộc tính khác (`check_truncation`,
    `mode()`, …) đi thẳng tới nguồn bên trong."""

    def __init__(self, inner, port: int, sink: Callable[[], RigRecorder | None], clock=RIG_CLOCK):
        self.inner, self.port, self.sink, self.clock = inner, port, sink, clock

    def read(self):
        try:
            frame = self.inner.read()
        except FrameReadError as exc:
            rec = self.sink()
            if rec is not None:
                t = getattr(exc, "t", None)
                rec.add_event(self.port, event_kind(str(exc)), self.clock() if t is None else t, str(exc))
            raise
        except Exception as exc:
            rec = self.sink()
            if rec is not None:
                rec.add_event(self.port, "exception", self.clock(), f"{type(exc).__name__}: {exc}")
            raise
        rec = self.sink()
        if rec is not None and frame is not None:
            rec.add_frame(self.port, frame)
        return frame

    def close(self):
        return self.inner.close()

    def __getattr__(self, name):
        inner = self.__dict__.get("inner")
        if inner is None:
            raise AttributeError(name)
        return getattr(inner, name)


class LidarTap:
    """Như `CameraTap` cho nguồn LiDAR của `LidarWorker`: ghi vòng quét với stamp trên đồng hồ bàn thử (stamp driver +
    `t0`, cùng phép đổi mà `LidarWorker` dùng) và `last_revolution.t_first`, `last_quality` nếu nguồn có.

    `ignore` (T3, 02/10/2026): ngoại lệ thuộc các loại này vẫn ném lại nhưng KHÔNG ghi thành lỗi đọc LiDAR — ví dụ
    `ScanStreamEnded` của phát lại `.npz` ở ngăn LiDAR (hết bản ghi không phải lỗi đọc)."""

    def __init__(self, inner, sink: Callable[[], RigRecorder | None], clock=RIG_CLOCK,
                 ignore: tuple[type[BaseException], ...] = ()):
        self.inner, self.sink, self.clock, self.ignore = inner, sink, clock, tuple(ignore)

    def read(self):
        try:
            scan = self.inner.read()
        except Exception as exc:
            rec = None if isinstance(exc, self.ignore) else self.sink()
            if rec is not None:
                rec.add_lidar_event(self.clock(), f"{type(exc).__name__}: {exc}")
            raise
        rec = self.sink()
        if rec is not None and scan is not None:
            t0 = getattr(self.inner, "t0", None) or 0.0
            rev = getattr(self.inner, "last_revolution", None)
            t_first = None if rev is None or getattr(rev, "t_first", None) is None else rev.t_first + t0
            rec.add_scan(scan, scan.stamp.t + t0, t_first, getattr(self.inner, "last_quality", None))
        return scan

    def close(self):
        return self.inner.close()

    def __getattr__(self, name):
        inner = self.__dict__.get("inner")
        if inner is None:
            raise AttributeError(name)
        return getattr(inner, name)
