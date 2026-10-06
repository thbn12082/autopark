"""Ghi video camera trên cao cho tham chiếu R1 (T4) với stamp `perf_counter` tuyệt đối của từng khung. Thêm 02/10/2026.

    .venv\\Scripts\\python.exe -X utf8 -m autopark.video.overhead_record --index N --size 1280x720 --seconds 20 --out runs\\tren_cao\\<ngay> --name san_trong

Đây là mã T4 DUY NHẤT mở camera (cùng nút "Mở camera" của `ui.overhead_app`); N tra mỗi lần bằng
`python -m autopark.video.camera_bench list`. Camera trên cao cắm vào CỔNG GỐC RIÊNG của laptop, không qua hub của bốn
camera xe (KICH_BAN_NGHIEM_THU.md mục 3.4 bước 4).

Ghi vào `<out>/<tên>.*`:

- `.avi` (MJPG, `VIDEOWRITER_PROP_QUALITY` 90) hoặc `.mp4` (mp4v): ảnh đã giải mã được nén lại, mỗi khung tốt một khung
  video. Khung camera trả hỏng (khung cũ, bị cắt, bị xé, đọc lỗi; `UsbCameraSource`) KHÔNG được ghi, chỉ được ghi ở
  `.events.csv`.
- `.frames.csv`: `frame,t_perf,t_s,width,height`; `t_perf` = stamp của nguồn (perf_counter ngay sau `read()`, gồm cả
  chờ khung và giải mã), `t_s` = t_perf − t_perf của khung đầu. Số dòng = số khung trong video.
- `.events.csv`: `t_perf,kind,after_frame,message`, `kind` theo `rig.recording.event_kind` (duplicate, truncated, torn,
  read_failed).
- `.json` (`autopark.overhead_recording/1`), ghi lúc bắt đầu và lúc kết thúc, qua tệp tạm: trạng thái (đang ghi / xong /
  lỗi / dừng (Ctrl+C)), đồng hồ `perf_counter`, máy, `wall_minus_perf_s` (giờ máy − perf_counter lúc bắt đầu),
  `t_wall_start`, camera (index, tên, yêu cầu, mode thật, phơi sáng, nét, `buffer_size_applied`), codec, chất lượng, số
  khung, khung/s thật, khoảng cách khung (trung vị, p95, lớn nhất, ms), số khung hỏng theo loại, EcoQoS, dung lượng ổ
  trống lúc bắt đầu, commit git, `synthetic`, `previous_backup` (bản cũ cùng tên đã đổi tên, xem dưới).
  EcoQoS (sửa 02/10/2026): `ecoqos` = `power_throttling.ecoqos_state()` ĐỌC LẠI mỗi lần ghi JSON (off / system / on /
  unknown, như mọi nơi ghi kết quả khác; lần ghi cuối ghi đè lần đầu), `ecoqos_start` = trạng thái lúc bắt đầu ghi,
  `ecoqos_policy` = chính sách áp lúc tiến trình khởi động `{request, set_ok, after}` (hay null).

`perf_counter` (QPC) chung một gốc cho mọi tiến trình của MỘT máy trong một lần khởi động, nên video ghi trên chính laptop
chạy phiên khớp thẳng với log và dấu T14 (`overhead_ref track`, đồng hồ `perf_counter`). Độ trễ từ lúc chụp tới stamp
(phơi sáng, truyền USB, giải mã) CHƯA ĐO; `overhead_ref` ghi nó vào `sync_error_s` (mặc định 0,15 s, ĐỀ XUẤT).

Trước khi mở camera: kiểm tham số, tên lần ghi, ổ đĩa (cảnh báo dưới 20 GB, từ chối dưới 5 GB trừ khi `--force`; ≈
0,4–0,55 GB mỗi phút ở 720p MJPG q90, ƯỚC TÍNH). Tên đã có thì từ chối trừ khi `--overwrite` (tách khỏi `--force` ngày
02/10/2026): khi đó mọi tệp cũ của tên đó (.avi/.mp4, .frames.csv, .events.csv, .json) được ĐỔI TÊN thành
`<tên>.bak_<ngày_giờ>.*` ngay trước khi ghi tệp mới, nên mọi video gốc R1 được giữ và bộ sao lưu vẫn là một lần ghi đọc
lại được (`overhead_ref` nhận); chỉ khi bản TỔNG HỢP mới thay bản cũ cũng TỔNG HỢP thì bản cũ bị xóa (dựng lại được).
Đang ghi mà camera thôi trả khung tốt (rút cáp USB…): hết `--seconds` thì vẫn dừng đúng hạn theo stamp của lần đọc hỏng;
quá 5 s không có khung tốt nào thì dừng, trạng thái "lỗi", mã thoát 1; sau 5 lần đọc hỏng liên tiếp nghỉ 5 ms trước lần
đọc kế (không quay tít một lõi, không làm đầy events.csv). Tiến trình tự tắt EcoQoS (`power_throttling`). Ctrl+C đóng
tệp đúng cách (trạng thái "dừng (Ctrl+C)"). Mã thoát: 0 xong; 1 lỗi đĩa, không có khung nào hay camera thôi trả khung;
2 tham số sai hay bị từ chối. Mặc định ĐỀ XUẤT – CHỜ CHỐT (người dùng giao quyết định 02/10/2026). Chỉ kiểm bằng nguồn
giả (tests/test_overhead_record.py); CHƯA THỬ với camera thật.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import threading
import time

import cv2
import numpy as np

from autopark.perception.paths import PROJECT, atomic_write_json
from autopark.power_throttling import ecoqos_state
from autopark.rig.recording import event_kind

FORMAT = "autopark.overhead_recording/1"
FRAMES_FIELDS = ["frame", "t_perf", "t_s", "width", "height"]
EVENTS_FIELDS = ["t_perf", "kind", "after_frame", "message"]
CODECS = {"MJPG": ".avi", "mp4v": ".mp4"}
EVENT_KINDS = ("duplicate", "truncated", "torn", "read_failed")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DEFAULT_QUALITY = 90
DEFAULT_SIZE = (1280, 720)
WARN_FREE_GB = 20.0
MIN_FREE_GB = 5.0
DEFAULT_OUT = PROJECT / "runs" / "tren_cao"
STATUS_RECORDING, STATUS_DONE, STATUS_ERROR, STATUS_INTERRUPTED = "đang ghi", "xong", "lỗi", "dừng (Ctrl+C)"
FIRST_FRAME_TIMEOUT_S = 5.0
# camera thôi trả khung tốt giữa lúc ghi (rút cáp USB: read() hỏng trả về ngay) — thêm 02/10/2026, ĐỀ XUẤT – CHỜ CHỐT,
# CHƯA THỬ với camera thật: quá STALL_TIMEOUT_S không có khung tốt nào thì dừng ghi với trạng thái "lỗi"; sau
# FAIL_BACKOFF_AFTER lần đọc hỏng liên tiếp nghỉ FAIL_BACKOFF_S trước lần đọc kế (≤ 200 dòng events.csv mỗi giây thay vì
# hàng trăm nghìn; chỉ khi đã hỏng liên tiếp nên stamp của khung tốt kế tiếp trễ thêm tối đa 5 ms)
STALL_TIMEOUT_S = 5.0
FAIL_BACKOFF_AFTER = 5
FAIL_BACKOFF_S = 0.005
SYNTHETIC_LABEL = "TỔNG HỢP — KHÔNG PHẢI SỐ ĐO"


class RecorderError(RuntimeError):
    """Không ghi được (tên, ổ đĩa, bộ ghi video): báo tiếng Việt."""


def name_error(name: str) -> str | None:
    if not NAME_RE.match(name or ""):
        return f"tên lần ghi {name!r} phải gồm 1–64 ký tự A-Z a-z 0-9 _ - (không dấu, không khoảng trắng)"
    return None


def disk_free_gb(path) -> float:
    """Dung lượng trống (GB) của ổ chứa `path` (thư mục gần nhất đã có)."""
    p = Path(path).resolve()
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(p).free / 1e9


def recording_paths(out_dir, name: str, codec: str = "MJPG") -> dict[str, Path]:
    out = Path(out_dir)
    return {"video": out / f"{name}{CODECS[codec]}", "frames": out / f"{name}.frames.csv",
            "events": out / f"{name}.events.csv", "meta": out / f"{name}.json"}


RECORDING_SUFFIXES = (*CODECS.values(), ".frames.csv", ".events.csv", ".json")


def existing_recording_files(out_dir, name: str) -> list[Path]:
    """Các tệp đã có của lần ghi `name` (video của MỌI codec, .frames.csv, .events.csv, .json)."""
    out = Path(out_dir)
    return [out / f"{name}{suffix}" for suffix in RECORDING_SUFFIXES if (out / f"{name}{suffix}").exists()]


def overwrite_hint(name: str) -> str:
    return (f"đặt tên khác, hoặc cho ghi đè (--overwrite): bản cũ được đổi tên thành {name}.bak_<ngày_giờ>.*, không "
            f"mất video gốc")


def is_synthetic_recording(meta_path) -> bool:
    """JSON của bộ ghi này có `"synthetic": true` (bản ghi TỔNG HỢP của overhead_synth)."""
    try:
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    return isinstance(meta, dict) and meta.get("format") == FORMAT and meta.get("synthetic") is True


def backup_recording(out_dir, name: str) -> list[Path]:
    """Đổi tên MỌI tệp đã có của lần ghi `name` thành `<name>.bak_<ngày_giờ_micro giây>.*` (cùng một gốc tên, nên bộ sao
    lưu vẫn là một lần ghi đọc lại được: `overhead_ref` ghép `.avi` với `.frames.csv` và `.json` cùng gốc). Đổi tên chứ
    không chép: không tốn thêm chỗ trên ổ. Trả các tệp sao lưu."""
    from autopark.perception.extrinsics_calib import reserve_backup_path

    out = Path(out_dir)
    old = existing_recording_files(out, name)
    if not old:
        return []
    try:
        anchor = reserve_backup_path(out / f"{name}.json")         # giữ chỗ độc quyền <name>.bak_<…>.json
    except (OSError, RuntimeError) as exc:
        raise RecorderError(f"không giữ được tên sao lưu cho lần ghi {name!r}: {exc}") from exc
    stem = anchor.name[:-len(".json")]
    targets = [out / f"{stem}{p.name[len(name):]}" for p in old]
    clash = [t for t in targets if t != anchor and t.exists()]
    if clash:
        anchor.unlink(missing_ok=True)
        raise RecorderError(f"tên sao lưu {clash[0]} đã có: không ghi đè lần ghi {name!r}")
    moved: list[tuple[Path, Path]] = []
    try:
        for src, dst in zip(old, targets):
            os.replace(src, dst)
            moved.append((src, dst))
    except OSError as exc:
        for src, dst in reversed(moved):          # trả lại tên cũ: lần ghi cũ không bị tách làm hai tên
            try:
                os.replace(dst, src)
            except OSError:
                pass
        anchor.unlink(missing_ok=True)
        raise RecorderError(f"không đổi tên được {exc.filename} để sao lưu ({exc}): tệp đang mở ở chương trình khác? "
                            f"lần ghi {name!r} cũ để nguyên") from exc
    if anchor not in targets:                                       # lần ghi cũ không có .json: bỏ tệp giữ chỗ rỗng
        anchor.unlink(missing_ok=True)
    return targets


def _backoff(streak: int, stop_event: threading.Event | None = None) -> None:
    """Nghỉ FAIL_BACKOFF_S sau FAIL_BACKOFF_AFTER lần đọc hỏng liên tiếp (read() hỏng trả về ngay: không quay tít)."""
    if streak >= FAIL_BACKOFF_AFTER:
        if stop_event is not None:
            stop_event.wait(FAIL_BACKOFF_S)
        else:
            time.sleep(FAIL_BACKOFF_S)


def _stall_message(streak: int, last_error, frames: int) -> str:
    return (f"camera không trả khung tốt nào trong {STALL_TIMEOUT_S:g} s ({streak} lần đọc hỏng liên tiếp, lần cuối: "
            f"{last_error}): đã dừng ghi, trạng thái \"{STATUS_ERROR}\", giữ {frames} khung đã ghi")


@lru_cache(maxsize=1)
def git_commit() -> str | None:
    """Commit git của mã đang chạy (hỏi git một lần mỗi tiến trình: bộ thử tổng hợp ghi nhiều đoạn liền nhau)."""
    from autopark.lidar.recording import git_commit as commit

    return commit()


class OverheadRecorder:
    """Ghi một lần: `start(rộng, cao, camera_info)`, `add(ảnh, t_perf)` mỗi khung tốt, `event(t_perf, thông báo)` mỗi khung
    hỏng, `stop(trạng thái)` → nội dung JSON cuối.

    Tên đã có thì từ chối, trừ khi `overwrite`: khi đó `start()` (ngay trước khi tạo tệp mới) đổi tên mọi tệp cũ của tên
    đó thành `<tên>.bak_<ngày_giờ>.*` (`backup_recording`; ghi vào khóa `previous_backup`), trừ một trường hợp: bản cũ
    TỔNG HỢP bị thay bằng bản TỔNG HỢP mới thì xóa (dựng lại được bằng overhead_synth). `force` là tên cũ của
    `overwrite` (overhead_synth còn gọi), cũng sao lưu như vậy; cờ dòng lệnh `--force` từ 02/10/2026 chỉ còn nghĩa bỏ
    qua từ chối khi ổ còn < 5 GB (main)."""

    def __init__(self, out_dir, name: str, *, codec: str = "MJPG", quality: int = DEFAULT_QUALITY,
                 fps_hint: float = 30.0, synthetic: bool = False, overwrite: bool = False, force: bool = False):
        if err := name_error(name):
            raise RecorderError(err)
        if codec not in CODECS:
            raise RecorderError(f"codec {codec!r} không hỗ trợ ({', '.join(CODECS)})")
        if not 1 <= int(quality) <= 100:
            raise RecorderError("chất lượng phải trong 1..100")
        self.out_dir, self.name, self.codec, self.quality = Path(out_dir), name, codec, int(quality)
        self.fps_hint, self.synthetic = float(fps_hint), synthetic
        self.overwrite = bool(overwrite or force)
        self.paths = recording_paths(out_dir, name, codec)
        self._refuse_existing()
        self.backups: list[Path] = []
        self.started = False
        self.frames = 0
        self.size: tuple[int, int] | None = None
        self.t_first: float | None = None
        self.t_last: float | None = None
        self.gaps: list[float] = []
        self.counts = dict.fromkeys(EVENT_KINDS, 0)
        self.meta: dict = {}
        self.write_error: str | None = None
        self._writer = None
        self._frames_file = None
        self._events_file = None

    def _refuse_existing(self) -> list[Path]:
        existing = existing_recording_files(self.out_dir, self.name)
        if existing and not self.overwrite:
            raise RecorderError(f"lần ghi {self.name!r} đã có ({existing[0]}): {overwrite_hint(self.name)}")
        return existing

    def _clear_old_files(self) -> None:
        """Dọn tên lần ghi trước khi tạo tệp mới: sao lưu bản cũ (giữ mọi video gốc R1), trừ bản cũ TỔNG HỢP bị thay
        bằng bản TỔNG HỢP mới (xóa)."""
        existing = self._refuse_existing()          # kiểm lại: tệp có thể vừa xuất hiện sau __init__
        if not existing:
            return
        if self.synthetic and is_synthetic_recording(self.paths["meta"]):
            for p in existing:
                p.unlink()
            return
        self.backups = backup_recording(self.out_dir, self.name)

    def start(self, width: int, height: int, camera_info: dict | None = None, *,
              ecoqos_policy: dict | None = None) -> None:
        """Tạo tệp và ghi JSON đầu. `ecoqos_policy`: chính sách EcoQoS áp lúc tiến trình khởi động
        ({request, set_ok, after}); trạng thái EcoQoS (`ecoqos`) thì đọc lại mỗi lần ghi JSON."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        free = disk_free_gb(self.out_dir)
        self._clear_old_files()
        writer = cv2.VideoWriter(str(self.paths["video"]), cv2.VideoWriter_fourcc(*self.codec), self.fps_hint,
                                 (int(width), int(height)))
        if not writer.isOpened():
            raise RecorderError(f"OpenCV không ghi được {self.codec} vào {self.paths['video']}")
        writer.set(cv2.VIDEOWRITER_PROP_QUALITY, float(self.quality))
        self._writer = writer
        self.size = (int(width), int(height))
        self._frames_file = self.paths["frames"].open("w", newline="", encoding="utf-8")
        self._frames = csv.writer(self._frames_file, lineterminator="\n")
        self._frames.writerow(FRAMES_FIELDS)
        self._events_file = self.paths["events"].open("w", newline="", encoding="utf-8")
        self._events = csv.writer(self._events_file, lineterminator="\n")
        self._events.writerow(EVENTS_FIELDS)
        state = ecoqos_state()
        self.meta = {
            "format": FORMAT, "status": STATUS_RECORDING, "clock": "perf_counter",
            "host": platform.node(),
            "wall_minus_perf_s": None if self.synthetic else time.time() - time.perf_counter(),
            "t_wall_start": datetime.now().isoformat(timespec="milliseconds"),
            "camera": dict(camera_info or {}), "codec": self.codec, "quality": self.quality,
            "size": list(self.size), "frames": 0, "fps_real": None, "gap_ms": None, "counts": dict(self.counts),
            # EcoQoS của tiến trình ghi: đọc lại lúc ghi JSON (như rig/recording.py), chính sách lúc khởi động để riêng
            "ecoqos": state, "ecoqos_start": state,
            "ecoqos_policy": dict(ecoqos_policy) if ecoqos_policy else None,
            "disk_free_gb_start": round(free, 2), "git_commit": git_commit(),
            "software": {"opencv": cv2.__version__, "numpy": np.__version__, "python": platform.python_version()},
            "synthetic": self.synthetic, "files": {k: p.name for k, p in self.paths.items()},
            "previous_backup": [p.name for p in self.backups],
            "note": (SYNTHETIC_LABEL + ": stamp tổng hợp, không phải camera thật. " if self.synthetic else "")
            + "t_perf = perf_counter ngay sau read() (gồm chờ khung và giải mã); độ trễ chụp CHƯA ĐO.",
        }
        self.started = True
        self._write_meta()

    def _write_meta(self) -> None:
        atomic_write_json(self.paths["meta"], self.meta)

    def add(self, image: np.ndarray, t_perf: float) -> None:
        if not self.started:
            raise RecorderError("bộ ghi chưa start()")
        h, w = image.shape[:2]
        if (w, h) != self.size:
            raise RecorderError(f"khung {w}×{h} khác cỡ đã mở {self.size[0]}×{self.size[1]}")
        if self.t_last is not None and not t_perf > self.t_last:
            raise RecorderError(f"t_perf không tăng ngặt ({t_perf} sau {self.t_last})")
        frame = image if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        self._writer.write(frame)
        if self.t_first is None:
            self.t_first = t_perf
        if self.t_last is not None:
            self.gaps.append(t_perf - self.t_last)
        self.t_last = t_perf
        self._frames.writerow([self.frames, f"{t_perf:.6f}", f"{t_perf - self.t_first:.6f}", w, h])
        self.frames += 1
        if self.frames % 30 == 0:
            self._frames_file.flush()

    def event(self, t_perf: float | None, message: str, kind: str | None = None) -> None:
        if not self.started:
            return
        kind = kind or event_kind(message)
        self.counts[kind] = self.counts.get(kind, 0) + 1
        self._events.writerow(["" if t_perf is None else f"{t_perf:.6f}", kind,
                               self.frames - 1 if self.frames else "", message])
        self._events_file.flush()

    def stop(self, status: str = STATUS_DONE) -> dict:
        if not self.started:
            return dict(self.meta)
        for closer in (self._writer.release, self._frames_file.close, self._events_file.close):
            try:
                closer()
            except (OSError, cv2.error) as exc:
                self.write_error = str(exc)
                status = STATUS_ERROR
        gaps = np.array(self.gaps) * 1000.0
        span = (self.t_last - self.t_first) if self.frames >= 2 else None
        self.meta.update({
            "status": status, "frames": self.frames,
            "fps_real": round((self.frames - 1) / span, 3) if span else None,
            "gap_ms": {"median": round(float(np.median(gaps)), 3), "p95": round(float(np.percentile(gaps, 95)), 3),
                       "max": round(float(gaps.max()), 3)} if len(gaps) else None,
            "counts": dict(self.counts), "t_perf_first": self.t_first, "t_perf_last": self.t_last,
            "t_wall_end": datetime.now().isoformat(timespec="milliseconds"),
            "disk_free_gb_end": round(disk_free_gb(self.out_dir), 2), "write_error": self.write_error,
            "ecoqos": ecoqos_state(),                   # đọc lại lúc ghi JSON cuối (ecoqos_start giữ lúc bắt đầu)
        })
        self.started = False
        self._write_meta()
        return dict(self.meta)


class RecordingThread(threading.Thread):
    """Một luồng đọc camera liên tục: giữ khung mới nhất cho xem trước, đếm khung hỏng, và khi đang ghi thì chuyển từng
    khung vào `OverheadRecorder` (stamp của nguồn). `open_source()` chạy TRONG luồng (camera chỉ mở khi luồng chạy).
    Camera thôi trả khung tốt: nghỉ ngắn sau các lần đọc hỏng liên tiếp (`_backoff`), và đang ghi mà quá STALL_TIMEOUT_S
    không có khung tốt thì dừng ghi với trạng thái "lỗi" (`record_error` báo lên giao diện); xem trước vẫn chạy."""

    def __init__(self, open_source, *, preview: bool = True, clock=time.perf_counter):
        super().__init__(daemon=True, name="overhead_camera")
        self.open_source, self.preview, self.clock = open_source, preview, clock
        self.counters = {"frames": 0, **dict.fromkeys(EVENT_KINDS, 0)}
        self.error: str | None = None
        self.record_error: str | None = None
        self.opened = threading.Event()
        self.camera_info: dict = {}
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest = None
        self._recorder: OverheadRecorder | None = None
        self._last_good = time.monotonic()        # lúc có khung tốt gần nhất (đồng hồ thật, canh camera thôi trả khung)

    def run(self) -> None:
        from autopark.video.sources import FrameReadError

        try:
            source = self.open_source()
        except Exception as exc:                 # noqa: BLE001 - lỗi mở camera báo lên giao diện
            self.error = f"không mở được camera: {exc}"
            self.opened.set()
            return
        mode = getattr(source, "mode", None)
        self.camera_info = {"mode": mode() if callable(mode) else None,
                            "buffer_size_applied": getattr(source, "buffer_size_applied", None),
                            "exposure_applied": getattr(source, "exposure_applied", None)}
        self.opened.set()
        streak = 0
        try:
            while not self._stop_event.is_set():
                try:
                    frame = source.read()
                except FrameReadError as exc:
                    kind = event_kind(str(exc))
                    streak += 1
                    with self._lock:
                        self.counters[kind] += 1
                        if self._recorder is not None:
                            self._recorder.event(exc.t if exc.t is not None else self.clock(), str(exc), kind)
                            if time.monotonic() - self._last_good > STALL_TIMEOUT_S:
                                message = _stall_message(streak, exc, self._recorder.frames)
                                self._recorder.stop(STATUS_ERROR)
                                self._recorder = None
                                self.record_error = message       # báo SAU khi tệp đã đóng và bộ ghi đã tách
                    _backoff(streak, self._stop_event)
                    continue
                if frame is None:
                    break
                streak = 0
                with self._lock:
                    self._latest = frame
                    self._last_good = time.monotonic()
                    self.counters["frames"] += 1
                    if self._recorder is not None:
                        try:
                            self._recorder.add(frame.image, float(frame.meta.stamp.t))
                        except (RecorderError, OSError, cv2.error) as exc:
                            self._recorder.stop(STATUS_ERROR)
                            self._recorder = None
                            self.record_error = f"ghi hỏng: {exc}"
        finally:
            with self._lock:
                if self._recorder is not None:
                    self._recorder.stop(STATUS_INTERRUPTED)
                    self._recorder = None
            source.close()

    def latest(self):
        with self._lock:
            return self._latest

    @property
    def recording(self) -> OverheadRecorder | None:
        return self._recorder

    def start_recording(self, recorder: OverheadRecorder, camera_info: dict | None = None,
                        ecoqos_policy: dict | None = None) -> None:
        """Bắt đầu ghi từ khung kế tiếp; cỡ ảnh lấy theo khung mới nhất (cần đã có ít nhất một khung). Hạn "không có
        khung tốt" tính từ lúc này."""
        frame = self.latest()
        if frame is None:
            raise RecorderError("chưa có khung nào từ camera")
        h, w = frame.image.shape[:2]
        recorder.start(w, h, {**self.camera_info, **(camera_info or {})}, ecoqos_policy=ecoqos_policy)
        with self._lock:
            self.record_error = None
            self._last_good = time.monotonic()
            self._recorder = recorder

    def stop_recording(self, status: str = STATUS_DONE) -> dict | None:
        with self._lock:
            recorder, self._recorder = self._recorder, None
            return recorder.stop(status) if recorder is not None else None

    def stop(self, timeout: float = 3.0) -> None:
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout)


def record(open_source, out_dir, name: str, seconds: float, *, codec: str = "MJPG", quality: int = DEFAULT_QUALITY,
           camera_info: dict | None = None, ecoqos_policy: dict | None = None, synthetic: bool = False,
           overwrite: bool = False, force: bool = False, progress=None) -> dict:
    """Mở nguồn, ghi `seconds` giây (theo stamp của nguồn, kể cả stamp của lần đọc hỏng) rồi đóng. Ctrl+C: đóng tệp,
    trạng thái "dừng (Ctrl+C)" và ném lại KeyboardInterrupt sau khi đã ghi JSON. Quá STALL_TIMEOUT_S (đồng hồ thật)
    không có khung tốt nào: đóng tệp với trạng thái "lỗi" rồi ném RecorderError. `overwrite` (`force` là tên cũ): xem
    OverheadRecorder — bản cũ cùng tên được sao lưu, không bao giờ mất."""
    from autopark.video.sources import FrameReadError

    recorder = OverheadRecorder(out_dir, name, codec=codec, quality=quality, synthetic=synthetic,
                                overwrite=overwrite or force)
    source = open_source()
    status, interrupted = STATUS_ERROR, False
    try:
        first, deadline, pending, streak = None, time.perf_counter() + FIRST_FRAME_TIMEOUT_S, [], 0
        while first is None and time.perf_counter() < deadline:
            try:
                first = source.read()
                if first is None:
                    break
            except FrameReadError as exc:
                pending.append((exc.t, str(exc)))
                streak += 1
                _backoff(streak)
        if first is None:
            raise RecorderError("không nhận được khung nào từ camera")
        info = dict(camera_info or {})
        mode = getattr(source, "mode", None)
        info.setdefault("mode", mode() if callable(mode) else None)
        info.setdefault("buffer_size_applied", getattr(source, "buffer_size_applied", None))
        h, w = first.image.shape[:2]
        recorder.start(w, h, info, ecoqos_policy=ecoqos_policy)
        for t, message in pending:
            recorder.event(t, message)
        recorder.add(first.image, float(first.meta.stamp.t))
        t_end = float(first.meta.stamp.t) + seconds
        last_good, streak = time.perf_counter(), 0
        while True:
            try:
                frame = source.read()
            except FrameReadError as exc:
                recorder.event(exc.t, str(exc))
                streak += 1
                now = time.perf_counter()
                # hạn ghi xét cả ở lần đọc hỏng: stamp của nguồn (perf_counter như UsbCameraSource), không có thì
                # giờ thật perf_counter
                if (exc.t if exc.t is not None else now) >= t_end:
                    break
                if now - last_good > STALL_TIMEOUT_S:
                    raise RecorderError(_stall_message(streak, exc, recorder.frames)
                                        + f" ({recorder.paths['video']} + .frames.csv, .events.csv, .json)")
                _backoff(streak)
                continue
            if frame is None:
                break
            streak, last_good = 0, time.perf_counter()
            recorder.add(frame.image, float(frame.meta.stamp.t))
            if progress is not None:
                progress(recorder)
            if frame.meta.stamp.t >= t_end:
                break
        status = STATUS_DONE
    except KeyboardInterrupt:
        status, interrupted = STATUS_INTERRUPTED, True
    finally:
        source.close()
        meta = recorder.stop(status) if recorder.started else {"status": status, "frames": 0}
    if interrupted:
        raise KeyboardInterrupt(meta)
    return meta


def camera_factory(index: int, width: int, height: int, *, exposure: float | None = None,
                   focus: float | None = None, source_id: str = "cam_tren_cao"):
    """Camera thật theo index OpenCV (MJPG ở kích thước yêu cầu). Test thay hàm này bằng nguồn giả."""
    from autopark.video.sources import UsbCameraSource

    source = UsbCameraSource(index, width=width, height=height, fps=30, fourcc="MJPG", exposure=exposure,
                             source_id=source_id)
    if source.mode_mismatch:
        source.close()
        raise ValueError(f"camera index {index} không nhận {width}×{height}: {source.mode_mismatch}")
    if focus is not None:
        source.focus_applied = bool(source.capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)) and \
            bool(source.capture.set(cv2.CAP_PROP_FOCUS, float(focus)))
    return source


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"LỖI: {message}", file=sys.stderr)
        raise SystemExit(2)


def _size(text: str) -> tuple[int, int]:
    try:
        w, h = (int(v) for v in text.lower().replace("×", "x").split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"cỡ {text!r}: cần dạng 1280x720") from None
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError("cỡ phải dương")
    return w, h


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="python -m autopark.video.overhead_record",
                description="Ghi video camera trên cao (R1, T4) với stamp perf_counter từng khung. Mở camera THẬT.")
    p.add_argument("--index", type=int, required=True, help="index OpenCV của camera trên cao (camera_bench list)")
    p.add_argument("--size", type=_size, default=DEFAULT_SIZE, help="mặc định 1280x720")
    p.add_argument("--seconds", type=float, required=True, help="thời lượng ghi (s)")
    p.add_argument("--out", type=Path, default=None, help="thư mục ghi; mặc định runs/tren_cao/<yyyymmdd>")
    p.add_argument("--name", required=True, help="tên lần ghi, ví dụ san_trong, do1_l01")
    p.add_argument("--camera-name", default="tren_cao", help="tên camera ghi vào tệp (như calib_app --camera-name)")
    p.add_argument("--exposure", type=float, default=None, help="phơi sáng thủ công (giá trị DirectShow)")
    p.add_argument("--focus", type=float, default=None, help="nét thủ công (tắt tự động lấy nét)")
    p.add_argument("--quality", type=int, default=DEFAULT_QUALITY)
    p.add_argument("--codec", choices=sorted(CODECS), default="MJPG")
    p.add_argument("--overwrite", action="store_true",
                   help="ghi lại tên đã có: mọi tệp cũ của tên đó được đổi tên thành <tên>.bak_<ngày_giờ>.* (giữ video "
                        "gốc)")
    p.add_argument("--force", action="store_true", help="bỏ qua từ chối khi ổ còn < 5 GB (KHÔNG cho ghi đè tên đã có)")
    return p


def main(argv=None) -> int:
    from autopark.perception import fisheye_calib as fc
    from autopark.power_throttling import apply_ecoqos_policy

    policy = apply_ecoqos_policy("video.overhead_record")     # trước mọi việc khác (power_throttling.py)
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    out = args.out or DEFAULT_OUT / datetime.now().strftime("%Y%m%d")
    problems = []
    if args.index < 0:
        problems.append("--index phải ≥ 0")
    if not (math.isfinite(args.seconds) and args.seconds > 0):
        problems.append("--seconds phải > 0")
    if not 1 <= args.quality <= 100:
        problems.append("--quality phải trong 1..100")
    if err := name_error(args.name):
        problems.append(err)
    if err := fc.camera_name_error(args.camera_name):
        problems.append(f"--camera-name: {err}")
    existing = []
    if not problems:
        existing = existing_recording_files(out, args.name)
        if existing and not args.overwrite:
            problems.append(f"lần ghi {args.name!r} đã có ({existing[0]}): {overwrite_hint(args.name)}")
    free = None
    if not problems:
        free = disk_free_gb(out)
        if free < MIN_FREE_GB and not args.force:
            problems.append(f"ổ đĩa chỉ còn {free:.1f} GB (< {MIN_FREE_GB:g} GB; ≈ 0,5 GB mỗi phút): dọn ổ hoặc --force")
    if problems:
        for problem in problems:
            print(f"LỖI: {problem}", file=sys.stderr)
        return 2
    if free < WARN_FREE_GB:
        print(f"CẢNH BÁO: ổ đĩa còn {free:.1f} GB (< {WARN_FREE_GB:g} GB)", file=sys.stderr)
    if existing:
        print(f"CẢNH BÁO: lần ghi {args.name!r} đã có ({len(existing)} tệp): --overwrite đổi tên chúng thành "
              f"{args.name}.bak_<ngày_giờ>.* lúc bắt đầu ghi", file=sys.stderr)
    # chính sách EcoQoS áp lúc khởi động (yêu cầu disable, hay keep khi AUTOPARK_KEEP_ECOQOS=1; set_ok; đọc lại ngay
    # sau đó) ghi vào khóa ecoqos_policy; khóa ecoqos của tệp ghi thì đọc lại ecoqos_state() lúc ghi
    ecoqos_policy = {"request": policy.request, "set_ok": policy.set_ok, "after": policy.state}
    w, h = args.size
    info = {"index": args.index, "name": args.camera_name,
            "requested": {"width": w, "height": h, "exposure": args.exposure, "focus": args.focus},
            "exposure": args.exposure, "focus": args.focus}

    def open_source():
        return camera_factory(args.index, w, h, exposure=args.exposure, focus=args.focus,
                              source_id=f"cam_{args.camera_name}")

    def progress(rec):
        if rec.frames % 150 == 0:
            print(f"  {rec.frames} khung", file=sys.stderr)
    try:
        meta = record(open_source, out, args.name, args.seconds, codec=args.codec, quality=args.quality,
                      camera_info=info, ecoqos_policy=ecoqos_policy, overwrite=args.overwrite, progress=progress)
    except KeyboardInterrupt as exc:
        meta = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {"status": STATUS_INTERRUPTED}
        print(f"dừng bằng Ctrl+C: đã đóng tệp ({meta.get('frames', 0)} khung)", file=sys.stderr)
    except (RecorderError, ValueError, OSError, cv2.error) as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 1
    paths = recording_paths(out, args.name, args.codec)
    print(f"{meta.get('status')}: {meta.get('frames', 0)} khung, {meta.get('fps_real')} khung/s thật, khoảng cách khung "
          f"{meta.get('gap_ms')} ms, khung hỏng {meta.get('counts')}, EcoQoS {meta.get('ecoqos', '—')}")
    print(f"đã ghi {paths['video']} (+ .frames.csv, .events.csv, .json)")
    if meta.get("previous_backup"):
        print(f"bản cũ cùng tên đã đổi tên: {', '.join(meta['previous_backup'])}")
    return 0 if meta.get("frames", 0) > 0 and meta.get("status") != STATUS_ERROR else 1


if __name__ == "__main__":
    sys.exit(main())
