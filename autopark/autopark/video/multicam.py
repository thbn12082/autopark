"""Nhiều camera USB chạy song song: mỗi camera một luồng đọc, ghép bộ ảnh theo thời gian, bỏ bộ ảnh lệch quá ngưỡng.

Đây là `MultiCameraManager` mà kế hoạch giai đoạn 2 yêu cầu ("hàng đợi giới hạn và logic bỏ bộ ảnh quá lệch thời
gian"). Không cần torch hay Qt.

- Camera được gọi theo **cổng hub**, không theo index OpenCV: index đổi sau khi khởi động lại máy (đo ngày 23/09,
  docs/usb_topology.md), còn cổng thì không. `resolve_ports()` hỏi Windows (PnP + DirectShow) để đổi cổng → index
  ngay lúc mở.
- Mỗi camera giữ vài khung gần nhất trong một vòng đệm có giới hạn (không hàng đợi vô hạn, không tích lũy độ trễ).
- `latest_set()` ghép một bộ: mốc thời gian = khung mới nhất của camera *chậm nhất*, rồi mỗi camera chọn khung gần
  mốc đó nhất. Độ lệch của bộ (`skew_s`) = stamp lớn nhất − nhỏ nhất. Bộ lệch quá `max_skew_s` bị bỏ và đếm. Một bộ
  chỉ được coi là mới khi MỌI camera trong bộ đều có khung khác bộ trước, nên số bộ mỗi giây ≤ tốc độ camera chậm
  nhất; khi khung đến không đều, quy tắc này bỏ mất một phần khung của camera chậm — đếm ở `frames_skipped` và
  `sets_blocked_not_new` (bản đầu chỉ đòi mốc tiến, nên AI chấm lại 43 bộ/s gần trùng nhau khi camera có 24 khung/s).
- **Đồng hồ:** mọi stamp dùng `RIG_CLOCK = time.perf_counter` (QPC, phân giải 100 ns trên Windows). KHÔNG dùng
  `time.monotonic`: trên Python 3.12 của Windows nó là GetTickCount64, bước 15,6 ms — các số đo độ lệch vài chục ms
  sẽ bị làm tròn thô (lỗi của bản đầu, phát hiện ngày 23/09). Stamp là thời điểm `read()` trả khung về Python, đã gồm
  chờ và giải mã, **không phải** thời điểm phơi sáng; độ lệch đo được là độ lệch lúc đến, không phải lúc chụp.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import threading
import time
from typing import Callable

import numpy as np

from .sources import Frame, FrameReadError, UsbCameraSource

RIG_CLOCK = time.perf_counter
STALE_AFTER_S = 0.5       # camera không có khung mới lâu hơn thế thì bị loại khỏi bộ ảnh và báo "cũ"
LIVE_WINDOW = 3000        # số trực tiếp (giao diện, chuỗi theo giây) chỉ tính trên chừng ấy mẫu cuối


def clock_info() -> dict:
    info = time.get_clock_info("perf_counter")
    return {"name": "perf_counter", "implementation": info.implementation, "resolution_s": info.resolution,
            "monotonic": info.monotonic}


def tail(values, n: int | None) -> np.ndarray:
    """n phần tử cuối của một deque/list (tất cả nếu n None), dạng mảng float."""
    k = len(values)
    if n is None or n >= k:
        return np.fromiter(values, float, k)
    return np.fromiter((values[i] for i in range(k - n, k)), float, n)


def dist(values: np.ndarray, scale: float = 1.0, nd: int = 1) -> dict:
    """Trung vị / p95 / min / max / n (một lần sắp xếp trong numpy, không giữ GIL lâu như sorted())."""
    if values.size == 0:
        return {"median": None, "p95": None, "min": None, "max": None, "n": 0}
    med, p95 = np.percentile(values, [50, 95])
    r = lambda x: round(float(x) * scale, nd)
    return {"median": r(med), "p95": r(p95), "min": r(values.min()), "max": r(values.max()), "n": int(values.size)}


def fit_width(width: int, height: int, max_width: int) -> tuple[int, int]:
    """Cỡ hiển thị giữ tỉ lệ ảnh: bề rộng ≤ max_width (camera 4:3 không bị ép thành 16:9)."""
    w = min(max_width, width)
    return w, max(1, round(w * height / width))


@dataclass
class CameraSpec:
    port: int                                  # cổng hub (danh tính bền)
    index: int                                 # index OpenCV lúc mở (có thể đổi sau khởi động lại)
    instance_id: str | None = None
    name: str = ""                             # vai trò khi đã gá (trước/sau/trái/phải); rỗng khi chưa có gá

    @property
    def source_id(self) -> str:
        return f"cam_p{self.port}"


def resolve_ports(ports: list[int] | None = None) -> list[CameraSpec]:
    """Cổng hub → index OpenCV qua PnP + DirectShow (Windows, cần pygrabber). `ports=None` lấy mọi camera thấy được."""
    from . import camera_bench as cb

    pnp = cb.pnp_cameras()
    mapping = cb.join_index_to_port(cb.dshow_device_paths(), pnp)
    by_port = {m["hub_port"]: m for m in mapping if m["hub_port"] is not None}
    wanted = sorted(by_port) if ports is None else list(ports)
    missing = [p for p in wanted if p not in by_port]
    if missing:
        raise ValueError(f"không thấy camera ở cổng {missing}; đang thấy cổng {sorted(by_port)}")
    return [CameraSpec(port=p, index=by_port[p]["index"], instance_id=by_port[p]["instance_id"]) for p in wanted]


@dataclass
class CameraStats:
    port: int
    index: int
    frames: int = 0
    duplicates: int = 0
    truncated: int = 0                 # khung bị cắt cụt trên đường USB (đáy do bộ giải mã tô), đã loại
    torn: int = 0                      # khung có dải xé giữa ảnh (đáy nguyên), đã loại
    read_failures: int = 0
    open_error: str | None = None
    last_error: str | None = None
    last_stamp: float | None = None
    gap_max_s: float = 0.0
    recent: deque = field(default_factory=lambda: deque(maxlen=240))   # stamp các khung gần đây để tính FPS cửa sổ

    def fps(self, now: float, window_s: float = 2.0, recent: list[float] | None = None) -> float:
        stamps = [t for t in (self.recent if recent is None else recent) if now - t <= window_s]
        if len(stamps) < 2:
            return 0.0
        return (len(stamps) - 1) / max(1e-6, stamps[-1] - stamps[0])

    def age_s(self, now: float) -> float | None:
        return None if self.last_stamp is None else now - self.last_stamp


class CameraWorker(threading.Thread):
    """Một luồng cho một camera: mở nguồn, đọc liên tục, đẩy khung vào vòng đệm. Lỗi được đếm, không làm chết luồng."""

    def __init__(self, spec: CameraSpec, open_source: Callable[[CameraSpec], object], ring: int, clock=RIG_CLOCK):
        super().__init__(daemon=True, name=spec.source_id)
        self.spec, self.open_source, self.clock = spec, open_source, clock
        self.ring: deque[tuple[int, Frame]] = deque(maxlen=ring)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.stats = CameraStats(port=spec.port, index=spec.index)
        self.source = None
        self.seq = 0
        self.opened = threading.Event()

    def run(self) -> None:
        try:
            self.source = self.open_source(self.spec)
        except Exception as exc:  # noqa: BLE001 - lỗi mở phải hiện ra, không làm chết cả hệ
            self.stats.open_error = f"{type(exc).__name__}: {exc}"
            self.opened.set()
            return
        self.opened.set()
        try:
            while not self.stop_event.is_set():
                try:
                    frame = self.source.read()
                except FrameReadError as exc:
                    with self.lock:
                        self._count_error(str(exc))
                    continue
                except Exception as exc:  # noqa: BLE001
                    with self.lock:
                        self.stats.last_error = f"{type(exc).__name__}: {exc}"
                        self.stats.read_failures += 1
                    time.sleep(0.05)
                    continue
                t = frame.meta.stamp.t
                with self.lock:
                    if self.stats.last_stamp is not None:
                        self.stats.gap_max_s = max(self.stats.gap_max_s, t - self.stats.last_stamp)
                    self.seq += 1
                    self.ring.append((self.seq, frame))
                    self.stats.frames += 1
                    self.stats.last_stamp = t
                    self.stats.recent.append(t)
        finally:
            try:
                self.source.close()
            except Exception:  # noqa: BLE001
                pass

    def _count_error(self, message: str) -> None:
        if "previous frame" in message:
            self.stats.duplicates += 1
        elif "truncated frame" in message:
            self.stats.truncated += 1
        elif "torn frame" in message:
            self.stats.torn += 1
        else:
            self.stats.read_failures += 1
            self.stats.last_error = message

    def snapshot(self) -> list[tuple[int, Frame]]:
        with self.lock:
            return list(self.ring)

    def reset_stats(self) -> None:
        with self.lock:
            s = self.stats
            s.frames, s.duplicates, s.truncated, s.torn, s.read_failures, s.gap_max_s = 0, 0, 0, 0, 0, 0.0


@dataclass
class FrameSet:
    frames: dict[int, Frame]              # cổng → khung
    seqs: dict[int, int]
    anchor_t: float                       # mốc: khung mới nhất của camera chậm nhất
    skew_s: float                         # stamp lớn nhất − nhỏ nhất trong bộ
    missing: list[int]                    # cổng bị loại vì không có khung hoặc khung quá cũ
    t_built: float

    @property
    def t_min(self) -> float:
        return min(f.meta.stamp.t for f in self.frames.values())

    @property
    def t_max(self) -> float:
        return max(f.meta.stamp.t for f in self.frames.values())


def build_set(rings: dict[int, list[tuple[int, Frame]]], now: float, stale_after_s: float = STALE_AFTER_S) -> FrameSet | None:
    """Ghép một bộ ảnh từ vòng đệm của từng camera (hàm thuần, để test)."""
    fresh = {port: ring for port, ring in rings.items() if ring and now - ring[-1][1].meta.stamp.t <= stale_after_s}
    missing = sorted(p for p in rings if p not in fresh)
    if not fresh:
        return None
    anchor = min(ring[-1][1].meta.stamp.t for ring in fresh.values())
    frames, seqs = {}, {}
    for port, ring in fresh.items():
        seq, frame = min(ring, key=lambda item: abs(item[1].meta.stamp.t - anchor))
        frames[port], seqs[port] = frame, seq
    stamps = [f.meta.stamp.t for f in frames.values()]
    return FrameSet(frames=frames, seqs=seqs, anchor_t=anchor, skew_s=max(stamps) - min(stamps), missing=missing, t_built=now)


class MultiCameraManager:
    """Mở nhiều camera, mỗi cái một luồng; `latest_set()` trả bộ ảnh đồng bộ mới nhất."""

    def __init__(self, specs: list[CameraSpec], *, width: int = 1280, height: int = 720, fps: float = 30.0,
                 fourcc: str = "MJPG", exposure: float | None = None, ring: int = 3,
                 open_source: Callable[[CameraSpec], object] | None = None, clock=RIG_CLOCK,
                 stale_after_s: float = STALE_AFTER_S):
        if ring < 1:
            raise ValueError("ring must be >= 1")
        self.specs, self.clock, self.stale_after_s = specs, clock, stale_after_s
        self.mode = {"width": width, "height": height, "fps": fps, "fourcc": fourcc, "exposure": exposure}
        if open_source is None:
            def open_source(spec: CameraSpec):
                return UsbCameraSource(spec.index, width=width, height=height, fps=fps, fourcc=fourcc,
                                       exposure=exposure, source_id=spec.source_id, clock=clock)
        self.workers = {s.port: CameraWorker(s, open_source, ring, clock) for s in specs}
        self._lock = threading.Lock()
        self._last_seqs: dict[int, int] | None = None
        self._blocked_key: tuple | None = None
        self.skews: deque[float] = deque(maxlen=200_000)
        self.reset_stats()

    def reset_stats(self) -> None:
        with self._lock:
            self.sets_built = 0
            self.sets_rejected_skew = 0
            self.sets_partial = 0
            self.sets_blocked_not_new = 0          # bộ ứng viên bị chặn vì có camera chưa có khung mới (đếm mỗi bộ một lần)
            self.frames_skipped = {port: 0 for port in self.workers}   # khung không bao giờ vào bộ nào
            self.skews.clear()
        for worker in self.workers.values():
            worker.reset_stats()

    def start(self, open_timeout_s: float = 10.0, sequential: bool = True) -> None:
        """Mở từng camera lần lượt (DirectShow không thích mở song song), rồi để các luồng tự đọc."""
        for worker in self.workers.values():
            worker.start()
            if sequential:
                worker.opened.wait(open_timeout_s)

    def request_stop(self) -> None:
        for worker in self.workers.values():
            worker.stop_event.set()

    def stop(self, join_timeout_s: float = 3.0) -> list[str]:
        """Dừng mọi luồng camera trong một hạn chung; trả tên các luồng chưa dừng."""
        self.request_stop()
        deadline = time.perf_counter() + join_timeout_s
        for worker in self.workers.values():
            if worker.is_alive():
                worker.join(max(0.0, deadline - time.perf_counter()))
        return [w.name for w in self.workers.values() if w.is_alive()]

    def rings(self) -> dict[int, list[tuple[int, Frame]]]:
        return {port: (w.snapshot() if w.stats.open_error is None else []) for port, w in self.workers.items()}

    def latest_set(self, max_skew_s: float | None = None, require_new: bool = True) -> FrameSet | None:
        """Bộ ảnh mới nhất. `require_new`: chỉ trả khi mọi camera trong bộ đều có khung khác bộ trước (kể cả bộ bị bỏ),
        để không suy luận lại khung cũ. Bộ lệch hơn `max_skew_s` bị bỏ (đếm vào `sets_rejected_skew`)."""
        fs = build_set(self.rings(), self.clock(), self.stale_after_s)
        if fs is None:
            return None
        with self._lock:
            last = self._last_seqs
            if require_new and last is not None:
                same = [last.get(port) == seq for port, seq in fs.seqs.items()]
                if all(same):
                    return None                     # đúng bộ trước: không camera nào có khung mới, không đếm
                if any(same):                        # vài camera có khung mới, vài camera chưa: bộ bị chặn
                    key = tuple(sorted(fs.seqs.items()))
                    if key != self._blocked_key:
                        self._blocked_key = key
                        self.sets_blocked_not_new += 1
                    return None
            if last is not None:
                for port, seq in fs.seqs.items():
                    prev = last.get(port)
                    if prev is not None and seq > prev + 1:
                        self.frames_skipped[port] = self.frames_skipped.get(port, 0) + seq - prev - 1
            self._last_seqs = dict(fs.seqs)
            self.skews.append(fs.skew_s)
            if max_skew_s is not None and fs.skew_s > max_skew_s:
                self.sets_rejected_skew += 1
                return None
            self.sets_built += 1
            if fs.missing:
                self.sets_partial += 1
        return fs

    def latest_frames(self) -> dict[int, Frame]:
        """Khung mới nhất của từng camera, không đồng bộ (cho hiển thị khi tắt AI)."""
        out = {}
        for port, ring in self.rings().items():
            if ring:
                out[port] = ring[-1][1]
        return out

    def camera_stats(self) -> list[dict]:
        """Số từng camera (rẻ: không đụng tới thống kê bộ ảnh). Dùng được 25 lần/giây từ giao diện."""
        now = self.clock()
        cams = []
        for port, w in self.workers.items():
            with w.lock:                               # vòng đệm stamp bị luồng camera ghi đồng thời
                s = w.stats
                recent = list(s.recent)
                row = {"port": port, "index": s.index, "frames": s.frames, "duplicates": s.duplicates,
                       "truncated": s.truncated, "torn": s.torn, "read_failures": s.read_failures, "gap_max_ms": round(1000 * s.gap_max_s, 1),
                       "open_error": s.open_error, "last_error": s.last_error}
                age = s.age_s(now)
            row.update({"fps_last2s": round(s.fps(now, recent=recent), 2),
                        "age_ms": None if age is None else round(1000 * age, 1),
                        "stale": age is None or age > self.stale_after_s})
            cams.append(row)
        return cams

    def stats(self, window: int | None = LIVE_WINDOW) -> dict:
        """Số camera + bộ ảnh. `window`: độ lệch tính trên chừng ấy bộ cuối (None = cả phiên, dùng cho tổng kết)."""
        with self._lock:
            skews = tail(self.skews, window)
            counts = {"sets_built": self.sets_built, "sets_rejected_skew": self.sets_rejected_skew,
                      "sets_partial": self.sets_partial, "sets_blocked_not_new": self.sets_blocked_not_new,
                      "frames_skipped": dict(self.frames_skipped)}
        return {"cameras": self.camera_stats(), **counts, "skew_ms": dist(skews, 1000.0),
                "skew_window": "cả phiên" if window is None else f"{window} bộ cuối"}
