"""Phát lại một phiên bàn thử đã ghi (`autopark.rig.recording`) qua đúng các giao diện nguồn mà bàn thử dùng với thiết bị
thật, để `Rig` (ghép bộ ảnh, chờ camera chậm, AI, LiDAR so với bộ ảnh), `rig.bench` và giao diện chạy lặp lại được mà
không cần camera, LiDAR hay cổng COM. Cách dùng và giới hạn: docs/VAN_HANH.md.

- `ReplaySession.open_camera(spec)` là `open_source` cho `MultiCameraManager`: `read()` CHẶN tới đúng thời điểm của khung
  theo bản ghi (tính từ lúc `begin()`, chia cho `speed`) rồi trả `Frame` có stamp = thời điểm đó trên đồng hồ phát lại.
  Sự kiện đọc hỏng đã ghi (khung cũ, khung bị cắt, khung xé, đọc lỗi) được NÉM LẠI đúng lúc và đúng nguyên văn
  (`FrameReadError` có `t`), nên bộ đếm `duplicates/truncated/torn/read_failures` và nhịp khung đo trên `arrivals` ra như
  lúc ghi. Khung mà bộ ghi đã bỏ (`record_dropped`) không có ảnh: lúc phát lại đó là một khoảng trống (đếm ở
  `status()["missing_in_recording"]`).
- `ReplaySession.open_lidar()` là `open_lidar` cho `Rig`: giống `RplidarC1Source` ở những gì `LidarWorker` dùng (`t0`,
  `last_revolution.t_first`, `last_quality`, `stats()`, `describe()`, `close()`); stamp = giờ phiên so với `t0` = lúc
  bắt đầu phát.
- Stamp được ĐỔI GỐC: t_phát = t_bắt_đầu + (t_ghi − t_gốc) / speed, t_gốc = điểm sớm nhất của bản ghi. Khoảng cách giữa
  các khung, giữa các camera, giữa camera và LiDAR giữ nguyên (chia cho speed); giá trị tuyệt đối thì không. Ở speed ≠ 1
  mọi nhịp đo được (fps, chu kỳ khung, ngưỡng chờ L) đổi theo, còn các ngưỡng tuyệt đối (STALE_AFTER_S = 0,5 s,
  max_skew 60 ms) thì không — kết quả ghép bộ ở speed ≠ 1 KHÔNG so được với phiên gốc.
- Ảnh được giải mã TRƯỚC khi chờ, nên khung ra gần đúng stamp; độ trễ thực so với lịch (`late_ms`) được đo và báo trong
  `status()`. Máy bận thì khung ra muộn hơn lịch nhưng stamp vẫn là giờ theo lịch (tuổi khung trông lớn hơn — đúng là nó
  muộn).
- Chưa `begin()` thì `read()` chờ: `Rig` chỉ bắt đầu đồng hồ phát lại sau khi AI nạp xong mô hình, để AI thấy bản ghi
  từ đầu.
- HẾT BẢN GHI: nguồn ngừng trả khung — `read()` chặn tới khi dừng (`stop()`, `close()`, hoặc luồng đang gọi nó bị yêu cầu
  dừng qua `stop_event` của `CameraWorker`/`LidarWorker`) rồi mới ném "hết bản ghi phát lại". Không lặp lại. Sau
  STALE_AFTER_S camera thành "cũ", bộ ảnh và AI ngừng; `finished` thành True; `rig.bench` tự dừng, giao diện ghi
  "HẾT BẢN GHI".
- Bản ghi dở hay hỏng không làm phát lại kẹt (sửa 24/09): dòng `frames.csv` thiếu cột / có số không đọc được bị bỏ, đếm
  ở `status()["bad_rows"]`; khung có tệp ảnh không đọc hay không giải mã được thành `FrameReadError` "phát lại không
  đọc/giải mã được …" (đếm ở `decode_errors`) và nguồn đi tiếp tới hết bản ghi.
- Khung trong bản ghi là khung đã qua bộ dò khung hỏng lúc ghi (chỉ khung tốt có ảnh), và là JPEG mã hóa lại (q95: sai
  khác trung bình ≈ 1 mức xám so với khung gốc, đo trên ảnh thật 23/09) — phát lại không thử được bộ dò khung hỏng, và AI
  chấm trên ảnh hơi khác ảnh gốc.
"""
from __future__ import annotations

from collections import deque
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import threading
import time

import cv2
import numpy as np

from autopark.domain.sensors import LidarScan, SourceStamp
from autopark.lidar.recording import Recording, read_recording
from autopark.rig.recording import (EVENTS_CSV, FORMAT, FORMAT_VERSION, FRAME_FIELDS, FRAMES_CSV, LIDAR_DIR, META_FILE,
                                    RECORD_DROPPED, camera_dir)
from autopark.video.multicam import RIG_CLOCK, CameraSpec, dist
from autopark.video.sources import FrameReadError, _frame

SLICE_S = 0.02            # bước ngủ tối đa khi chờ lịch: nguồn dừng được trong ≤ 20 ms
CLOCK_SLACK_S = 5.0       # stamp được phép lệch khỏi cửa sổ ghi [t_start_s; t_stop_s] tối đa chừng ấy
END_MESSAGE = "hết bản ghi phát lại (replay over)"
STOPPED_MESSAGE = "phát lại đã dừng (replay stopped)"


class ReplayError(ValueError):
    """Thư mục không phải bản ghi phiên bàn thử đọc được."""


def read_meta(folder) -> dict:
    folder = Path(folder)
    path = folder / META_FILE
    if not path.is_file():
        raise ReplayError(f"không phải thư mục ghi phiên bàn thử (thiếu {META_FILE}): {folder}")
    meta = json.loads(path.read_text(encoding="utf-8"))
    if meta.get("format") != FORMAT:
        raise ReplayError(f"{path}: format {meta.get('format')!r}, cần {FORMAT!r}")
    if meta.get("format_version") != FORMAT_VERSION:
        raise ReplayError(f"{path}: format_version {meta.get('format_version')!r}, bản đọc này hiểu {FORMAT_VERSION}")
    return meta


@dataclass(frozen=True)
class StreamItem:
    """Một mục của dòng camera: khung (`kind` == "frame") hoặc sự kiện đọc hỏng (loại như lúc ghi)."""
    t: float
    kind: str
    seq: int | None = None
    file: str | None = None
    message: str = ""


def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_camera_stream(folder, port: int) -> tuple[list[StreamItem], dict]:
    """Khung và sự kiện của một camera đúng thứ tự lúc ghi (sự kiện có `after_seq` = khung tốt cuối cùng trước nó).
    Dòng không đọc được (bản ghi bị ngắt giữa chừng) bị bỏ và đếm ở `bad_rows`. Một dòng khung chỉ hợp lệ khi ĐỦ mọi
    cột và mọi số đọc được: dòng cuối bị cắt (còn "seq,t_s" — DictReader điền None cho cột thiếu) hay có đuôi byte NUL
    phải thành `bad_rows`, không được thành một khung không có tệp (sửa 24/09: trước đó nguồn đọc lại mục đó mãi)."""
    d = Path(folder) / camera_dir(port)
    info = {"bad_rows": 0, "record_dropped": 0}
    frames, events = [], []
    for row in _rows(d / FRAMES_CSV):
        try:
            # cột thừa (DictReader để ở khóa None) hay cột thiếu/rỗng = dòng hỏng
            if None in row or any(not row.get(k) for k in FRAME_FIELDS):
                raise ValueError("dòng frames.csv thiếu cột")
            int(row["width"]), int(row["height"]), int(row["bytes"])
            frames.append(StreamItem(float(row["t_s"]), "frame", int(row["seq"]), row["file"]))
        except (KeyError, TypeError, ValueError):
            info["bad_rows"] += 1
    for order, row in enumerate(_rows(d / EVENTS_CSV)):
        try:
            item = StreamItem(float(row["t_s"]), row["kind"], int(row["after_seq"]), None, row.get("message") or "")
        except (KeyError, TypeError, ValueError):
            info["bad_rows"] += 1
            continue
        if item.kind == RECORD_DROPPED:
            info["record_dropped"] += 1
            continue
        events.append((item.seq, order, item))
    frames.sort(key=lambda it: it.seq)
    events.sort(key=lambda e: (e[0], e[1]))
    out, k = [], 0
    for frame in frames:
        while k < len(events) and events[k][0] < frame.seq:
            out.append(events[k][2])
            k += 1
        out.append(frame)
    out.extend(e[2] for e in events[k:])
    return out, info


def load_lidar(folder) -> tuple[Recording | None, list[tuple[float, str]]]:
    """Mọi phần `lidar/part_*.npz` nối thành một `Recording` (None nếu không có vòng nào) và lỗi đọc LiDAR đã ghi."""
    d = Path(folder) / LIDAR_DIR
    parts = sorted(d.glob("part_*.npz")) if d.is_dir() else []
    events = []
    for row in _rows(d / EVENTS_CSV):
        try:
            events.append((float(row["t_s"]), row.get("message") or ""))
        except (KeyError, TypeError, ValueError):
            continue
    if not parts:
        return None, events
    recs = [read_recording(p) for p in parts]
    cat = lambda key: np.concatenate([getattr(r, key) for r in recs])  # noqa: E731
    meta = {**recs[0].meta, "parts": [p.name for p in parts]}
    return Recording(d, cat("t"), cat("t_first"), cat("n_beams"), cat("angles"), cat("ranges"), cat("quality"),
                     meta=meta), events


def _late_stats(values) -> dict:
    return dist(np.fromiter(values, float, len(values)), 1000.0)


class ReplaySession:
    """Một lần phát lại: đồng hồ chung (gốc đặt ở `begin()`), nguồn camera và LiDAR, trạng thái."""

    def __init__(self, folder, *, speed: float = 1.0, ports: list[int] | None = None, clock=RIG_CLOCK):
        if not isinstance(speed, (int, float)) or not math.isfinite(speed) or speed <= 0:
            raise ValueError("speed phải hữu hạn và > 0")
        self.folder = Path(folder)
        self.meta = read_meta(self.folder)
        self.speed, self.clock = float(speed), clock
        recorded = {int(c["port"]): dict(c) for c in self.meta.get("cameras", [])}
        for p in self.meta.get("ports", []):             # bộ ghi dùng riêng (không qua Rig) chỉ biết danh sách cổng
            recorded.setdefault(int(p), {"port": int(p)})
        for c in self.meta.get("cameras_at_stop", []):
            if int(c["port"]) in recorded and c.get("open_error"):
                recorded[int(c["port"])]["open_error"] = c["open_error"]
        wanted = sorted(recorded) if not ports else [int(p) for p in ports]
        unknown = [p for p in wanted if p not in recorded]
        if unknown:
            raise ReplayError(f"cổng {unknown} không có trong bản ghi (có {sorted(recorded)})")
        self.cameras = {p: recorded[p] for p in wanted}
        self.streams: dict[int, list[StreamItem]] = {}
        self.stream_info: dict[int, dict] = {}
        for p in wanted:
            self.streams[p], self.stream_info[p] = read_camera_stream(self.folder, p)
        self.lidar_recording, self.lidar_events = load_lidar(self.folder)
        firsts = [items[0].t for items in self.streams.values() if items] + [t for t, _ in self.lidar_events[:1]]
        lasts = [items[-1].t for items in self.streams.values() if items] + [t for t, _ in self.lidar_events[-1:]]
        if self.lidar_recording is not None:
            firsts.append(float(self.lidar_recording.t[0]))
            lasts.append(float(self.lidar_recording.t[-1]))
        if not firsts:
            raise ReplayError(f"bản ghi không có khung camera hay vòng LiDAR nào: {self.folder}")
        t_start, t_stop = self.meta.get("t_start_s"), self.meta.get("t_stop_s")
        if t_start is not None and t_stop is not None:
            # stamp nằm ngoài cửa sổ ghi = có nguồn dùng đồng hồ khác (ví dụ giờ phiên của driver chưa cộng t0): phát lại
            # sẽ "chờ" hàng giờ giữa hai nguồn. Báo lỗi ngay thay vì chạy im lặng.
            lo, hi = float(t_start) - CLOCK_SLACK_S, float(t_stop) + CLOCK_SLACK_S
            outside = [t for t in firsts + lasts if not lo <= t <= hi]
            if outside:
                raise ReplayError(f"{self.folder}: stamp {outside[0]:.3f} s nằm ngoài cửa sổ ghi [{t_start:.3f}; {t_stop:.3f}] "
                                  "— các nguồn không cùng một đồng hồ?")
        self.t_ref = min(firsts + ([float(t_start)] if t_start is not None else []))
        self.t_last = max(lasts)
        self.duration_s = self.t_last - self.t_ref
        self.origin: float | None = None
        self._begun = threading.Event()
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self._sources: list = []

    # ---- mô tả ---------------------------------------------------------------------------------------------------
    @property
    def ports(self) -> list[int]:
        return list(self.cameras)

    @property
    def has_lidar(self) -> bool:
        return self.lidar_recording is not None or bool(self.lidar_events)

    def camera_specs(self) -> list[CameraSpec]:
        return [CameraSpec(port=p, index=int(c.get("index", -1)), instance_id=c.get("instance_id"), name=c.get("name") or "")
                for p, c in self.cameras.items()]

    def camera_mode(self) -> dict:
        mode = dict(self.meta.get("camera_mode") or {})
        cfg = self.meta.get("config") or {}
        for key in ("width", "height", "fps", "fourcc", "exposure"):
            mode.setdefault(key, cfg.get(key))
        return mode

    def describe(self) -> dict:
        return {"folder": str(self.folder), "speed": self.speed, "format_version": self.meta.get("format_version"),
                "created_utc": self.meta.get("created_utc"), "git_commit": self.meta.get("git_commit"),
                "recording_status": self.meta.get("status"), "image": self.meta.get("image"),
                "duration_s": round(self.duration_s, 3), "ports": self.ports, "lidar": self.has_lidar}

    # ---- đồng hồ -------------------------------------------------------------------------------------------------
    def begin(self, lead_s: float = 0.0) -> float:
        """Đặt gốc đồng hồ phát lại (một lần): mục có t_ghi = t_gốc ra ở `clock() + lead_s`."""
        with self._lock:
            if self.origin is None:
                self.origin = self.clock() + lead_s
                self._begun.set()
            return self.origin

    @property
    def begun(self) -> bool:
        return self._begun.is_set()

    def stop(self) -> None:
        """Mọi `read()` đang chờ (lịch, `begin()`, hết bản ghi) trả về trong ≤ SLICE_S."""
        self._stopped.set()

    def rel(self, t_rec: float) -> float:
        return (t_rec - self.t_ref) / self.speed

    def due(self, t_rec: float) -> float:
        return self.origin + self.rel(t_rec)

    def end_t(self) -> float | None:
        """Cuối bản ghi trên đồng hồ phát lại (cùng đồng hồ với stamp khung phát lại): mốc cuối phiên của khoảng hở cuối
        từng camera (T10, 02/10/2026; `MultiCameraManager.camera_stats`). Hết bản ghi không phải camera ngừng: đo tới
        "bây giờ" thì mọi camera có một khoảng hở giả bằng lúc chờ sau mục cuối (bench chờ thêm REPLAY_END_GRACE_S, đo
        thử ≈ 0,3–0,6 s). Mốc = max(mục cuối của bản ghi, `t_stop_s` của meta.json = lúc ngừng ghi). None khi chưa
        `begin()`."""
        if self.origin is None:
            return None
        t_stop = self.meta.get("t_stop_s")
        return self.due(self.t_last if t_stop is None else max(self.t_last, float(t_stop)))

    def should_stop(self, source) -> bool:
        if self._stopped.is_set() or source.closed:
            return True
        worker_stop = getattr(threading.current_thread(), "stop_event", None)
        return worker_stop is not None and worker_stop.is_set()

    def wait_begun(self, source) -> bool:
        while not self._begun.is_set():
            if self.should_stop(source):
                return False
            self._begun.wait(SLICE_S)
        return True

    def wait_until(self, due: float, source) -> bool:
        """Ngủ tới `due` theo đồng hồ phát lại (time.sleep: ≈ 1 ms trên Windows với Python ≥ 3.11); False = phải dừng."""
        while True:
            if self.should_stop(source):
                return False
            remaining = due - self.clock()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, SLICE_S))

    def wait_end(self, source) -> None:
        while not self.should_stop(source):
            time.sleep(SLICE_S)

    @property
    def finished(self) -> bool:
        """Đã qua thời điểm của mục cuối và mọi nguồn đã mở đều đã trả hết."""
        if self.origin is None or self.clock() < self.due(self.t_last):
            return False
        with self._lock:
            sources = list(self._sources)
        return all(s.done for s in sources)

    # ---- nguồn ---------------------------------------------------------------------------------------------------
    def open_camera(self, spec: CameraSpec) -> "ReplayCameraSource":
        cam = self.cameras.get(spec.port)
        if cam is None:
            raise ValueError(f"cổng {spec.port} không có trong bản ghi {self.folder}")
        items = self.streams[spec.port]
        if cam.get("open_error") and not items:
            raise ValueError(f"lúc ghi camera cổng {spec.port} không mở được: {cam['open_error']}")
        source = ReplayCameraSource(self, spec.port, items, spec.source_id, cam.get("source_rejects_damaged"))
        with self._lock:
            self._sources.append(source)
        return source

    def open_lidar(self) -> "ReplayLidarSource":
        if not self.has_lidar:
            raise ValueError(f"bản ghi không có LiDAR: {self.folder}")
        source = ReplayLidarSource(self)
        with self._lock:
            self._sources.append(source)
        return source

    def status(self) -> dict:
        now = self.clock()
        with self._lock:
            sources = list(self._sources)
        position = None if self.origin is None else max(0.0, min(self.duration_s, (now - self.origin) * self.speed))
        cams, lidar = {}, None
        for s in sources:
            row = {"delivered": s.delivered, "errors_replayed": s.errors_replayed, "total": s.total, "done": s.done,
                   "late_ms": _late_stats(list(s.late))}
            if isinstance(s, ReplayCameraSource):
                cams[s.port] = {**row, "decode_errors": s.decode_errors,
                                "missing_in_recording": self.stream_info[s.port]["record_dropped"]}
            else:
                lidar = row
        return {"folder": str(self.folder), "speed": self.speed, "begun": self.begun, "finished": self.finished,
                "position_s": None if position is None else round(position, 2), "duration_s": round(self.duration_s, 2),
                "recording_status": self.meta.get("status"), "image": self.meta.get("image"),
                "cameras": cams, "lidar": lidar,
                "missing_in_recording": {p: i["record_dropped"] for p, i in self.stream_info.items()},
                "bad_rows": {p: i["bad_rows"] for p, i in self.stream_info.items()}}


class ReplayCameraSource:
    """Nguồn camera phát lại (một cổng) — cùng hợp đồng với `UsbCameraSource`: trả `Frame` hoặc ném `FrameReadError`,
    không bao giờ trả None (xem đầu module về hết bản ghi)."""

    def __init__(self, session: ReplaySession, port: int, items: list[StreamItem], source_id: str,
                 check_truncation=None):
        self.session, self.port, self.items, self.source_id = session, port, items, source_id
        # như nguồn lúc ghi (UsbCameraSource: True — khung hỏng đã bị loại lúc ghi, ảnh ở đây chỉ là khung tốt)
        self.check_truncation = check_truncation
        self.folder = session.folder / camera_dir(port)
        self.index = 0
        self.delivered = 0
        self.errors_replayed = 0
        self.decode_errors = 0
        self.closed = False
        self.late: deque[float] = deque(maxlen=20_000)     # lúc trả thực − lịch (s)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def done(self) -> bool:
        return self.index >= len(self.items)

    def read(self):
        s = self.session
        if not s.wait_begun(self):
            raise FrameReadError(f"{self.source_id}: {STOPPED_MESSAGE}", s.clock())
        if self.done:
            s.wait_end(self)
            raise FrameReadError(f"{self.source_id}: {END_MESSAGE}", s.clock())
        item = self.items[self.index]
        image, path, why = None, None, ""
        if item.kind == "frame":                     # giải mã TRƯỚC khi chờ: khung ra gần đúng stamp
            try:
                path = self.folder / item.file
                data = np.fromfile(path, np.uint8)
                image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
            except Exception as exc:  # noqa: BLE001 - tệp thiếu/hỏng, tên hỏng, cv2.error: một mục hỏng không được
                image, why = None, f" ({type(exc).__name__}: {exc})"   # làm nguồn đọc lại nó mãi — đếm và đi tiếp
        due = s.due(item.t)
        if not s.wait_until(due, self):
            raise FrameReadError(f"{self.source_id}: {STOPPED_MESSAGE}", s.clock())
        self.index += 1
        self.late.append(s.clock() - due)
        if item.kind == "frame":
            if image is None:
                self.decode_errors += 1
                raise FrameReadError(f"{self.source_id}: phát lại không đọc/giải mã được {item.file}{why}", due)
            self.delivered += 1
            return _frame(self.source_id, due, str(path), image)
        self.errors_replayed += 1
        if item.kind == "exception":
            raise RuntimeError(item.message)
        raise FrameReadError(item.message, due)

    def close(self) -> None:
        self.closed = True


@dataclass(frozen=True)
class ReplayRevolution:
    t_first: float
    t_last: float


class ReplayLidarSource:
    """Nguồn LiDAR phát lại, như `RplidarC1Source` ở những gì `LidarWorker` dùng; lỗi đọc đã ghi được ném lại
    (`RuntimeError` với nguyên văn thông báo), hết bản ghi thì chặn tới khi dừng."""

    def __init__(self, session: ReplaySession):
        self.session = session
        self.recording = session.lidar_recording
        self.source_id = (self.recording.meta.get("source_id") if self.recording is not None else None) or "lidar_replay"
        items = [] if self.recording is None else [(float(t), 0, i, "") for i, t in enumerate(self.recording.t)]
        items += [(t, 1, None, message) for t, message in session.lidar_events]
        items.sort(key=lambda it: (it[0], it[1]))
        self.items = items
        self.t0: float | None = None
        self.last_revolution: ReplayRevolution | None = None
        self.last_quality: np.ndarray | None = None
        self.index = 0
        self.delivered = 0
        self.errors_replayed = 0
        self.closed = False
        self.late: deque[float] = deque(maxlen=20_000)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def done(self) -> bool:
        return self.index >= len(self.items)

    def read(self) -> LidarScan:
        s = self.session
        if not s.wait_begun(self):
            raise RuntimeError(f"{self.source_id}: {STOPPED_MESSAGE}")
        self.t0 = s.origin
        if self.done:
            s.wait_end(self)
            raise RuntimeError(f"{self.source_id}: {END_MESSAGE}")
        t_rec, _, index, message = self.items[self.index]
        due = s.due(t_rec)
        if not s.wait_until(due, self):
            raise RuntimeError(f"{self.source_id}: {STOPPED_MESSAGE}")
        self.index += 1
        self.late.append(s.clock() - due)
        if index is None:
            self.errors_replayed += 1
            raise RuntimeError(message)
        angles, ranges, quality = self.recording.beams(index)
        t_rel = s.rel(t_rec)
        self.last_revolution = ReplayRevolution(s.rel(float(self.recording.t_first[index])), t_rel)
        self.last_quality = np.array(quality, np.uint8)
        self.delivered += 1
        return LidarScan(SourceStamp(self.source_id, t_rel, True, "lidar"), tuple(angles.astype(float).tolist()),
                         tuple(ranges.astype(float).tolist()))

    def stats(self) -> dict:
        return {"revolutions_returned": self.delivered, "errors_replayed": self.errors_replayed}

    def describe(self) -> dict:
        recorded = (self.session.meta.get("lidar_source") or {}).get("describe")
        return {"driver": "autopark.rig.replay", "replay_of": str(self.session.folder), "recorded": recorded}

    def close(self) -> None:
        self.closed = True
