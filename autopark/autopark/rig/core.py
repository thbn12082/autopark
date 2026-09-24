"""Chạy đồng thời bốn camera, LiDAR và AI trên cùng một đồng hồ, đo từng luồng.

Kế hoạch giai đoạn 2, bước 2: "Ghi FPS/độ trễ/mất hình riêng từng camera; chạy đồng thời với LiDAR và AI, không chỉ
thử mở bốn cửa sổ." Bước 5: "Đồng bộ ở mức phần mềm và ghi sai lệch thời gian còn lại." Giai đoạn 1, bước 3 "Khi
nhận một camera": "Đo FPS nhận, thời gian suy luận, độ trễ, mất hình, CPU/GPU và nhiệt trong một phiên thử."

Luồng chạy (mọi stamp dùng `RIG_CLOCK = time.perf_counter`, xem `video.multicam`):
- mỗi camera một luồng (`video.multicam.MultiCameraManager`);
- một luồng LiDAR giữ vòng quét mới nhất (stamp của driver là giờ phiên, đổi về đồng hồ chung bằng `t0` của driver —
  driver PHẢI được mở với cùng đồng hồ, `bench.build_rig` làm điều đó);
- một luồng AI: lấy bộ ảnh đồng bộ mới nhất, suy luận cả lô, công bố kết quả mới nhất (không xếp hàng). Với
  `RigConfig.max_wait_s` (mặc định 60 ms; là SÀN — từ tối 24/09 mỗi camera có ngưỡng RIÊNG L = max(max_wait_s, 1,5 ×
  chu kỳ khung TRUNG BÌNH đo được của CHÍNH camera đó), ≈ 63 ms ở 24 fps (nhịp xen kẽ 31/48 ms, trung bình 41,9 ms),
  ≈ 100 ms ở 15 fps; trước đó là một ngưỡng chung theo camera nhanh nhất, bỏ nhầm camera khỏe khi các camera khác nhịp
  (docs/GIAI_DOAN_2_BAN_THU.md mục 10.1), xem `video.multicam`), camera lỡ nhịp của chính nó chỉ được chờ có giới hạn: bộ được
  chấm không có nó (`FrameSet.lagging`, xem `video.multicam`), cỡ lô thay đổi theo số camera có trong bộ. Camera có khung
  mới thuộc chu kỳ sau cũng có thể được để dành cho bộ sau để sửa lệch pha (`FrameSet.deferred`). Với cả hai, kết quả
  mới nhất CỦA TỪNG camera được giữ lại (`AIResult.carried`) để giao diện vẫn tô lớp AI cũ, có ghi tuổi;
- một luồng ghép bộ: khi AI tắt, chưa nạp xong hoặc không có, vẫn ghép bộ để đo độ lệch giữa các camera;
- một luồng tài nguyên (1 Hz): CPU tiến trình và máy, RAM, GPU (tải, VRAM, nhiệt độ, công suất qua NVML);
- một luồng chuỗi số đo mỗi giây, ghi số CỦA TỪNG GIÂY (khung, lô AI, vòng LiDAR trong giây đó), không phải số tích lũy.

Độ lệch LiDAR − bộ ảnh được lấy NGAY LÚC GHÉP BỘ (trước suy luận): vòng quét mới nhất lúc đó so với mốc bộ ảnh (mốc chỉ
tính trên các camera có trong bộ, kể cả bộ thiếu camera chậm). Cả hai
stamp đều là lúc dữ liệu TỚI MÁY (camera: lúc `read()` trả về, đã gồm giải mã; LiDAR: lúc gói chứa điểm cuối của vòng
tới máy — vòng quét kéo dài ≈ 100 ms trước đó), không phải lúc phơi sáng hay lúc đo. Độ trễ từ sự kiện thật tới lúc
dữ liệu tới máy KHÔNG đo được ở đây (cần LED nháy hoặc đồng hồ quay bằng camera).

Số "trực tiếp" (giao diện, chuỗi theo giây) tính trên cửa sổ `LIVE_WINDOW` mẫu cuối; `summary()` tính cả phiên kể từ
lần đặt lại cuối (`reset_counters`). Đổi mô hình AI thì số AI tự đặt lại và lô đầu (khởi tạo CUDA/cuDNN) được tách riêng.

Ghi và phát lại (từ 24/09, docs/GHI_PHAT_LAI_BAN_THU.md): `Rig` bọc nguồn của từng camera và của LiDAR
(`rig.recording.CameraTap`, `LidarTap`); `start_recording()` / `stop_recording()` bật tắt việc ghi mọi khung tốt, sự kiện
đọc hỏng và vòng LiDAR ra thư mục lúc đang chạy. `Rig(..., replay=ReplaySession)` chạy từ một bản ghi thay cho thiết bị:
đồng hồ phát lại chỉ bắt đầu khi AI đã nạp xong mô hình (hoặc nạp lỗi), và `stop()` đánh thức mọi nguồn phát lại đang chờ.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import threading
import time
from typing import Callable

import numpy as np

from autopark.rig.recording import CameraTap, LidarTap, RigRecorder
from autopark.video.multicam import (LIVE_WINDOW, RIG_CLOCK, WAIT_PERIODS, FrameSet, MultiCameraManager, clock_info, dist,
                                     fit_width, tail)
from autopark.video.sources import Frame

REPLAY_AI_WAIT_S = 180.0      # phát lại: chờ AI nạp mô hình tối đa chừng ấy trước khi chạy đồng hồ phát lại
RECORD_FINISH_S = 60.0        # stop(): chờ bộ ghi ghi nốt hàng đợi tối đa chừng ấy


def _r(x, nd=1):
    return None if x is None else round(float(x), nd)


# ------------------------------------------------------------------------------------------------------------ LiDAR

class LidarWorker(threading.Thread):
    """Giữ vòng quét mới nhất. Lỗi đọc được đếm và hiện ra, không làm chết luồng."""

    def __init__(self, open_source: Callable[[], object], clock=RIG_CLOCK):
        super().__init__(daemon=True, name="lidar")
        self.open_source, self.clock = open_source, clock
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.source = None
        self.latest = None                   # (scan, t_last_abs, t_first_abs | None)
        self.open_error: str | None = None
        self.last_error: str | None = None
        self.recent: deque[float] = deque(maxlen=100)
        self.opened = threading.Event()
        self.reset_stats()

    def reset_stats(self) -> None:
        driver = self._driver_stats()
        with self.lock:
            self.scans = 0
            self.errors = 0
            self.gap_max_s = 0.0
            self.since = self.clock()
            self.driver_at_reset = driver

    def _driver_stats(self) -> dict:
        if self.source is not None and hasattr(self.source, "stats"):
            try:
                return dict(self.source.stats())
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def run(self) -> None:
        try:
            self.source = self.open_source()
        except Exception as exc:  # noqa: BLE001
            self.open_error = f"{type(exc).__name__}: {exc}"
            self.opened.set()
            return
        self.opened.set()
        try:
            while not self.stop_event.is_set():
                try:
                    scan = self.source.read()
                except Exception as exc:  # noqa: BLE001 - ScanReadError, lỗi giao thức: đếm và thử tiếp
                    with self.lock:
                        self.errors += 1
                        self.last_error = f"{type(exc).__name__}: {exc}"
                    if self.stop_event.wait(0.2):
                        break
                    continue
                t0 = getattr(self.source, "t0", None) or 0.0
                t_abs = scan.stamp.t + t0
                rev = getattr(self.source, "last_revolution", None)
                t_first = None if rev is None or getattr(rev, "t_first", None) is None else rev.t_first + t0
                with self.lock:
                    if self.recent:
                        self.gap_max_s = max(self.gap_max_s, t_abs - self.recent[-1])
                    self.latest = (scan, t_abs, t_first)
                    self.scans += 1
                    self.recent.append(t_abs)
        finally:
            try:
                self.source.close()          # RplidarC1Source.close() gửi STOP rồi đóng cổng
            except Exception:  # noqa: BLE001
                pass

    def shutdown_stuck(self) -> bool:
        """Luồng còn kẹt trong read() sau khi hết hạn: đóng cổng từ luồng này để mô-tơ dừng và read() ném lỗi."""
        if not self.is_alive() or self.source is None:
            return False
        try:
            self.source.close()
        except Exception:  # noqa: BLE001
            pass
        return True

    def snapshot(self):
        with self.lock:
            return self.latest, list(self.recent)

    def stats(self, now: float) -> dict:
        with self.lock:
            latest, recent = self.latest, list(self.recent)
            scans, errors, gap, since, base = self.scans, self.errors, self.gap_max_s, self.since, self.driver_at_reset
        window = [t for t in recent if now - t <= 3.0]
        hz = (len(window) - 1) / (window[-1] - window[0]) if len(window) >= 2 and window[-1] > window[0] else 0.0
        driver = self._driver_stats()
        delta = {k: v - base.get(k, 0) for k, v in driver.items() if isinstance(v, (int, float))}
        n_valid = None
        if latest is not None:
            n_valid = int(np.isfinite(np.asarray(latest[0].ranges_m, dtype=float)).sum())
        return {"scans": scans, "hz_mean": round(scans / (now - since), 3) if now > since else None,
                "hz_last3s": round(hz, 2), "errors": errors, "open_error": self.open_error, "last_error": self.last_error,
                "gap_max_ms": round(1000 * gap, 1), "age_ms": None if latest is None else round(1000 * (now - latest[1]), 1),
                "beams_valid_last": n_valid, "driver_since_reset": delta}


def lidar_vs_set(lidar: LidarWorker | None, fs: FrameSet) -> dict | None:
    """LiDAR so với bộ ảnh, lấy ngay lúc ghép bộ: stamp cuối vòng − mốc (âm = vòng đã xong trước mốc). Mốc của bộ thiếu
    camera chậm chỉ tính trên các camera có trong bộ, nên số này vẫn là "LiDAR so với đúng các ảnh được chấm"."""
    if lidar is None:
        return None
    latest, _ = lidar.snapshot()
    if latest is None:
        return None
    _, t_last, t_first = latest
    out = {"last_minus_anchor_ms": 1000.0 * (t_last - fs.anchor_t)}
    if t_first is not None:
        out["mid_minus_anchor_ms"] = 1000.0 * ((t_first + t_last) / 2 - fs.anchor_t)
        out["sweep_ms"] = 1000.0 * (t_last - t_first)
    return out


# ------------------------------------------------------------------------------------------------------------ AI

@dataclass
class CameraAI:
    """Kết quả AI của MỘT camera trong một lô đã chấm: đúng khung đã đưa vào mạng và xác suất của nó."""
    frame: Frame
    prob: np.ndarray
    batch_id: int
    t_done: float
    checkpoint: str


@dataclass
class AIResult:
    frame_set: FrameSet
    probs: dict[int, np.ndarray]              # cổng → xác suất BLOCKED ở cỡ hiển thị (giữ tỉ lệ từng camera)
    model: str
    checkpoint: str
    t_done: float
    timing: object
    lidar: dict | None                        # lidar_vs_set lúc ghép bộ
    batch_id: int = -1                        # số thứ tự lô của luồng AI (tăng dần, gồm cả lô đầu)
    # camera chậm (frame_set.lagging) hoặc để dành cho bộ sau (frame_set.deferred) → kết quả gần nhất của nó từ một lô
    # TRƯỚC, cùng mô hình; thiếu nếu camera đó chưa từng được chấm với mô hình này
    carried: dict[int, CameraAI] = field(default_factory=dict)


class AIWorker(threading.Thread):
    """Lấy bộ ảnh đồng bộ mới nhất, suy luận cả lô, công bố kết quả mới nhất. Đổi mô hình được lúc đang chạy.

    Lô chỉ gồm camera có trong bộ (bộ thiếu camera chậm hay để dành camera lệch pha → lô nhỏ hơn). `by_port` giữ kết quả
    mới nhất của từng camera; bị xóa khi đổi mô hình, để lớp tô mang sang không bao giờ đến từ mô hình khác."""

    def __init__(self, cams: MultiCameraManager, make_segmenter: Callable[[str], object], checkpoint: str,
                 display_width: int, max_skew_s: float | None, on_set: Callable[[FrameSet], dict | None] | None = None,
                 clock=RIG_CLOCK, max_wait_s: float | None = None):
        super().__init__(daemon=True, name="ai")
        self.cams, self.make_segmenter, self.display_width, self.max_skew_s = cams, make_segmenter, display_width, max_skew_s
        self.on_set, self.clock, self.max_wait_s = on_set, clock, max_wait_s
        self.stop_event = threading.Event()
        self.enabled = threading.Event()
        self.enabled.set()
        self.lock = threading.Lock()
        self.latest: AIResult | None = None
        self.by_port: dict[int, CameraAI] = {}
        self._next_batch = 0
        self.segmenter = None
        self.checkpoint: str | None = None
        self._requested = checkpoint
        self.load_error: str | None = None
        self.load_ms: float | None = None
        self.first_batch_ms: float | None = None
        self.last_error: str | None = None
        self._skip_first = True
        # (số camera n, cao, rộng): ngay sau khi nạp mô hình, TRƯỚC khi nhận bộ ảnh, chạy một lô ảnh đen cho MỖI cỡ lô n,
        # n−1, …, 1. Đo 24/09 trên máy bàn (RTX 4000 Ada, LiveSegmenter 640×480): lần ĐẦU gặp một cỡ lô mất 1,2–1,7 s
        # (4 ảnh 1665 ms, rồi 3 ảnh 1444, 2 ảnh 1431, 1 ảnh 1265), các lần sau 14–18 ms. Không làm nóng thì lần đầu một
        # camera bị bỏ khỏi bộ (lô 3 ảnh) AI đứng ≈ 1,4 s — đúng lúc quy tắc chờ camera chậm muốn AI chạy tiếp; khi phát
        # lại thì phần đầu bản ghi trôi qua không được chấm (o04: 34 khung mỗi camera). Rig đặt giá trị này; None = tắt.
        self.warm_up: tuple[int, int, int] | None = None
        self.warm_up_ms: list[float] = []             # thời gian lô làm nóng theo cỡ lô n, n−1, …, 1 (lần nạp gần nhất)
        self._warm = threading.Event()
        self.reset_stats()

    # ---- mô hình ----
    @property
    def requested(self) -> str:
        with self.lock:
            return self._requested

    def request_model(self, checkpoint: str) -> None:
        with self.lock:
            self._requested = checkpoint

    def ready(self) -> bool:
        return self.segmenter is not None and self.enabled.is_set()

    def warmed(self) -> bool:
        """Mô hình đã nạp và (nếu có `warm_up`) đã chạy xong các lô làm nóng; hoặc nạp lỗi."""
        return (self.segmenter is not None and (self.warm_up is None or self._warm.is_set())) or self.load_error is not None

    def _ensure_model(self) -> None:
        with self.lock:
            want = self._requested
        if self.segmenter is not None and want == self.checkpoint:
            return
        t = time.perf_counter()
        try:
            seg = self.make_segmenter(want)
        except Exception as exc:  # noqa: BLE001
            self.load_error = f"{type(exc).__name__}: {exc}"
            with self.lock:
                newer = self._requested != want                 # người dùng đã chọn mô hình khác trong lúc nạp
                if self.segmenter is not None and not newer:
                    self._requested = self.checkpoint
            if not newer:
                self.stop_event.wait(1.0)                       # tránh nạp lại liên tục cùng một file hỏng
            return
        load_ms = 1000 * (time.perf_counter() - t)
        self._warm.clear()
        warm_ms = self._run_warm_up(seg)
        with self.lock:
            self.segmenter, self.checkpoint = seg, want
            self.load_error = None
            self.load_ms = load_ms
            self.warm_up_ms = warm_ms or []
            self.by_port = {}                                   # kết quả mang sang phải cùng mô hình
        self.reset_stats()
        # lô làm nóng đã gánh phần khởi tạo: lô thật đầu tiên được tính như mọi lô; làm nóng lỗi thì tách lô đầu như cũ
        self._skip_first = not warm_ms
        if warm_ms:
            self.first_batch_ms = warm_ms[0]
        self._warm.set()

    def _run_warm_up(self, seg) -> list[float] | None:
        """Một lô ảnh đen cho mỗi cỡ lô n, n−1, …, 1; trả thời gian từng lô (ms), None nếu tắt/lỗi/đang dừng."""
        if self.warm_up is None:
            return None
        n, h, w = self.warm_up
        size = fit_width(w, h, self.display_width)
        out = []
        try:
            for k in range(n, 0, -1):
                if self.stop_event.is_set():
                    return None
                _, timing = seg.infer([np.zeros((h, w, 3), np.uint8) for _ in range(k)], [size] * k)
                out.append(timing.total_ms)
        except Exception as exc:  # noqa: BLE001
            with self.lock:
                self.last_error = f"làm nóng: {type(exc).__name__}: {exc}"
            return None
        return out

    # ---- số đo ----
    def reset_stats(self) -> None:
        with self.lock:
            self.batches = self.images = self.errors = 0
            self.batches_partial_wait = 0                          # lô của bộ thiếu camera chậm
            self.since = self.clock()
            self.total_ms: deque[float] = deque(maxlen=200_000)
            self.model_ms: deque[float] = deque(maxlen=200_000)
            self.pre_ms: deque[float] = deque(maxlen=200_000)
            self.post_ms: deque[float] = deque(maxlen=200_000)
            self.age_oldest_ms: deque[float] = deque(maxlen=200_000)   # t_done − stamp khung CŨ nhất trong bộ
            self.age_newest_ms: deque[float] = deque(maxlen=200_000)   # t_done − stamp khung MỚI nhất trong bộ
            self.done_times: deque[float] = deque(maxlen=500)
            self._interval: list[float] = []

    def drain_interval(self) -> list[float]:
        with self.lock:
            out, self._interval = self._interval, []
            return out

    def run(self) -> None:
        while not self.stop_event.is_set():
            self._ensure_model()
            if self.segmenter is None or not self.enabled.is_set():
                self.stop_event.wait(0.05)
                continue
            if not self.step():
                time.sleep(0.002)

    def step(self) -> bool:
        """Một vòng: lấy bộ mới (theo max_skew_s / max_wait_s), chấm các camera CÓ trong bộ, công bố. False khi chưa có
        bộ mới. Tách khỏi `run()` để test gọi từng bước với đồng hồ giả."""
        fs = self.cams.latest_set(self.max_skew_s, max_wait_s=self.max_wait_s)
        if fs is None:
            return False
        lidar = self.on_set(fs) if self.on_set is not None else None
        ports = sorted(fs.frames)
        images = [fs.frames[p].image for p in ports]
        sizes = [fit_width(img.shape[1], img.shape[0], self.display_width) for img in images]
        seg, checkpoint = self.segmenter, self.checkpoint
        try:
            probs, timing = seg.infer(images, sizes)
        except Exception as exc:  # noqa: BLE001
            with self.lock:
                self.errors += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
            self.stop_event.wait(0.1)
            return True
        t_done = self.clock()
        probs = dict(zip(ports, probs))
        with self.lock:
            batch_id, self._next_batch = self._next_batch, self._next_batch + 1
            # mô hình chỉ đổi trong _ensure_model, chạy trên chính luồng này giữa hai bước (và xóa by_port): kết quả
            # mang sang cho camera chậm luôn cùng mô hình với lô này
            carried = {p: self.by_port[p] for p in (*fs.lagging, *fs.deferred) if p in self.by_port}
            for p in ports:
                self.by_port[p] = CameraAI(fs.frames[p], probs[p], batch_id, t_done, str(checkpoint))
            self.latest = AIResult(fs, probs, getattr(seg, "name", str(checkpoint)), str(checkpoint), t_done, timing,
                                   lidar, batch_id, carried)
            if self._skip_first:                            # lô đầu gồm khởi tạo CUDA/cuDNN: ghi riêng
                self.first_batch_ms = timing.total_ms
                self._skip_first = False
                return True
            self.batches += 1
            self.images += len(ports)
            if fs.lagging:
                self.batches_partial_wait += 1
            self.total_ms.append(timing.total_ms)
            self.model_ms.append(timing.model_ms)
            self.pre_ms.append(timing.pre_ms)
            self.post_ms.append(timing.post_ms)
            self.age_oldest_ms.append(1000.0 * (t_done - fs.t_min))
            self.age_newest_ms.append(1000.0 * (t_done - fs.t_max))
            self.done_times.append(t_done)
            self._interval.append(timing.total_ms)
        return True

    def result(self) -> AIResult | None:
        with self.lock:
            return self.latest

    def stats(self, now: float, window: int | None = LIVE_WINDOW) -> dict:
        with self.lock:
            batches, images, errors, since = self.batches, self.images, self.errors, self.since
            partial_wait = self.batches_partial_wait
            done = [t for t in self.done_times if now - t <= 3.0]
            arrays = {k: tail(getattr(self, k), window) for k in
                      ("total_ms", "model_ms", "pre_ms", "post_ms", "age_oldest_ms", "age_newest_ms")}
            latest = self.latest
            checkpoint, requested = self.checkpoint, self._requested
        rate = (len(done) - 1) / (done[-1] - done[0]) if len(done) >= 2 and done[-1] > done[0] else 0.0
        if done and now - done[-1] > 1.0:
            rate = 0.0
        return {"model": getattr(self.segmenter, "name", None), "checkpoint": checkpoint, "requested": requested,
                "device": str(getattr(self.segmenter, "device", "")), "amp": getattr(self.segmenter, "amp", None),
                "enabled": self.enabled.is_set(), "load_error": self.load_error, "load_ms": _r(self.load_ms),
                "first_batch_ms": _r(self.first_batch_ms), "warm_up_ms": [_r(x) for x in self.warm_up_ms],
                "batches": batches, "images": images,
                "batches_partial_wait": partial_wait, "max_wait_ms": None if not self.max_wait_s or self.max_wait_s <= 0
                else _r(1000 * self.max_wait_s),
                "sets_per_s_mean": round(batches / (now - since), 3) if now > since else None,
                "sets_per_s_last3s": round(rate, 2), "errors": errors, "last_error": self.last_error,
                "last_result_age_ms": None if latest is None else _r(1000 * (now - latest.t_done)),
                "window": "cả phiên" if window is None else f"{window} lô cuối",
                "total_ms": dist(arrays["total_ms"]), "model_ms": dist(arrays["model_ms"]),
                "pre_ms": dist(arrays["pre_ms"]), "post_ms": dist(arrays["post_ms"]),
                "result_age_oldest_frame_ms": dist(arrays["age_oldest_ms"]),
                "result_age_newest_frame_ms": dist(arrays["age_newest_ms"])}


# ------------------------------------------------------------------------------------------------------------ tài nguyên

class ResourceMonitor(threading.Thread):
    """1 Hz: CPU tiến trình (đơn vị lõi) và của máy, RAM tiến trình, GPU qua NVML. Thiếu thư viện thì ghi None."""

    def __init__(self, period_s: float = 1.0, clock=RIG_CLOCK):
        super().__init__(daemon=True, name="resources")
        self.period_s, self.clock = period_s, clock
        self.stop_event = threading.Event()
        self.samples: deque[dict] = deque(maxlen=20_000)
        self.errors: list[str] = []
        try:
            import psutil
            self._proc = psutil.Process()
            self._psutil = psutil
            self._proc.cpu_percent(None)
            psutil.cpu_percent(None)
        except Exception as exc:  # noqa: BLE001
            self._psutil = None
            self.errors.append(f"psutil: {exc}")
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml = pynvml
            self._gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.gpu_name = pynvml.nvmlDeviceGetName(self._gpu)
        except Exception as exc:  # noqa: BLE001
            self._nvml = None
            self.gpu_name = None
            self.errors.append(f"nvml: {exc}")

    def sample(self) -> dict:
        s: dict = {"t": self.clock()}
        if self._psutil is not None:
            s["proc_cpu_cores"] = round(self._proc.cpu_percent(None) / 100.0, 3)   # % của một lõi / 100 = số lõi
            s["sys_cpu_pct"] = round(self._psutil.cpu_percent(None), 1)
            s["proc_rss_mb"] = round(self._proc.memory_info().rss / 2**20, 1)
            s["proc_threads"] = self._proc.num_threads()
        if self._nvml is not None:
            n = self._nvml
            try:
                util = n.nvmlDeviceGetUtilizationRates(self._gpu)
                mem = n.nvmlDeviceGetMemoryInfo(self._gpu)
                s["gpu_util_pct"] = util.gpu
                s["gpu_mem_used_mb"] = round(mem.used / 2**20)
                s["gpu_temp_c"] = n.nvmlDeviceGetTemperature(self._gpu, n.NVML_TEMPERATURE_GPU)
                s["gpu_power_w"] = round(n.nvmlDeviceGetPowerUsage(self._gpu) / 1000.0, 1)
            except Exception as exc:  # noqa: BLE001
                s["gpu_error"] = str(exc)
        return s

    def run(self) -> None:
        while not self.stop_event.wait(self.period_s):
            self.samples.append(self.sample())

    def latest(self) -> dict | None:
        return self.samples[-1] if self.samples else None

    def summary(self) -> dict:
        samples = list(self.samples)
        out: dict = {"n": len(samples), "gpu_name": self.gpu_name, "errors": self.errors,
                     "cpu_temperature": "không đo (Windows không cho đọc nhiệt độ CPU khi không có quyền admin)"}
        for key in ("proc_cpu_cores", "sys_cpu_pct", "proc_rss_mb", "gpu_util_pct", "gpu_mem_used_mb", "gpu_temp_c", "gpu_power_w"):
            values = [s[key] for s in samples if key in s]
            if values:
                out[key] = {"mean": _r(float(np.mean(values)), 3), "max": _r(max(values), 2),
                            "first": _r(values[0], 2), "last": _r(values[-1], 2)}
        return out


# ------------------------------------------------------------------------------------------------------------ Rig

@dataclass
class RigConfig:
    width: int = 640                     # 720p qua hub: khung bị cắt cụt ở vài camera (xem rig/bench.py add_rig_args)
    height: int = 480
    fps: float = 30.0
    fourcc: str = "MJPG"
    exposure: float | None = None
    max_skew_s: float | None = 0.060          # bộ ảnh lệch hơn thế bị bỏ (≈ 1,5 chu kỳ khung ở 24 fps)
    # SÀN của ngưỡng chờ camera chưa có khung mới; ngưỡng thực RIÊNG từng camera L = max(max_wait_s, 1,5 × chu kỳ khung
    # TRUNG BÌNH đo được của CHÍNH camera đó): ≈ 63 ms ở 24 fps (nhịp xen kẽ 31/48 ms, trung bình 41,9 ms), ≈ 100 ms ở
    # 15 fps. Camera khỏe mà chậm hơn định nhịp cả chuỗi, không bị bỏ. Hết hạn thì chấm bộ không có nó. Sàn 60 ms và hệ
    # số 1,5 là lựa chọn thiết kế, kiểm bằng mô phỏng đồng hồ giả và phát lại khoảng cách khung đo được ngày 24/09
    # (docs/GIAI_DOAN_2_BAN_THU.md mục 10.1–10.2). None hoặc ≤ 0 = quy tắc cũ: chờ mọi camera, cả chuỗi chậm theo camera
    # chậm nhất.
    max_wait_s: float | None = 0.060
    display_width: int = 640                  # xác suất AI trả về ở bề rộng này, giữ tỉ lệ từng camera
    ai: bool = True
    checkpoint: str | None = None
    lidar_port: str | None = None
    notes: dict = field(default_factory=dict)


class Rig:
    def __init__(self, cams: MultiCameraManager, cfg: RigConfig, *, make_segmenter: Callable[[str], object] | None = None,
                 open_lidar: Callable[[], object] | None = None, monitor: ResourceMonitor | None = None,
                 clock=RIG_CLOCK, replay=None):
        self.cams, self.cfg, self.clock = cams, cfg, clock
        self.replay = replay                              # rig.replay.ReplaySession khi chạy từ bản ghi
        self.recorder: RigRecorder | None = None          # bộ ghi đang nhận dữ liệu (None: không ghi)
        self.last_recorder: RigRecorder | None = None     # lần ghi gần nhất, kể cả đang ghi nốt hay đã xong
        # Bọc nguồn TRƯỚC khi luồng camera chạy (CameraWorker gọi open_source trong run()): mọi khung/sự kiện đi qua
        # lớp bọc, lớp bọc chỉ đẩy vào bộ ghi khi self.recorder khác None (tốn một lần đọc thuộc tính mỗi khung khi tắt).
        for port, worker in cams.workers.items():
            worker.open_source = self._tap_camera(port, worker.open_source)
        if open_lidar is not None:
            inner_lidar = open_lidar
            open_lidar = lambda: LidarTap(inner_lidar(), lambda: self.recorder, clock)  # noqa: E731
        self.lidar = LidarWorker(open_lidar, clock) if open_lidar is not None else None
        self._lidar_lock = threading.Lock()
        self.lidar_offsets: dict[str, deque] = {k: deque(maxlen=200_000) for k in
                                                ("last_minus_anchor_ms", "mid_minus_anchor_ms", "sweep_ms")}
        self.ai = None
        if cfg.ai and make_segmenter is not None and cfg.checkpoint:
            self.ai = AIWorker(cams, make_segmenter, cfg.checkpoint, cfg.display_width, cfg.max_skew_s,
                               on_set=self._record_set, clock=clock, max_wait_s=cfg.max_wait_s)
            self.ai.warm_up = (len(cams.specs), cfg.height, cfg.width)     # mọi cỡ lô, trước bộ ảnh đầu (xem AIWorker)
        self.monitor = monitor if monitor is not None else ResourceMonitor(clock=clock)
        self.series: list[dict] = []
        self.t_start: float | None = None
        self.stop_alive: list[str] = []
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._last_counts: dict = {}
        self._count_lock = threading.Lock()      # đặt lại số đo và dòng chuỗi theo giây không được xen nhau

    def _tap_camera(self, port: int, open_source: Callable) -> Callable:
        def open_tapped(spec):
            return CameraTap(open_source(spec), port, lambda: self.recorder, self.clock)
        return open_tapped

    # ---- vòng đời ----
    def start(self, begin_replay: bool = True) -> None:
        """`begin_replay` (khi chạy từ bản ghi): bắt đầu đồng hồ phát lại ngay khi AI nạp xong mô hình (luồng nền, không
        chặn giao diện). False: người gọi tự gọi `self.replay.begin()` (bench: sau phần làm nóng và `reset_counters`)."""
        self.t_start = self.clock()
        self.cams.start()
        for worker in (self.lidar, self.ai, self.monitor):
            if worker is not None:
                worker.start()
        self._last_counts = self._counts()
        for name, target in (("series", self._series_loop), ("sets", self._set_loop)):
            t = threading.Thread(target=target, daemon=True, name=name)
            t.start()
            self._threads.append(t)
        if self.replay is not None and begin_replay:
            if self.ai is None:
                self.replay.begin()
            else:
                t = threading.Thread(target=self._begin_replay_when_model_ready, daemon=True, name="replay-begin")
                t.start()
                self._threads.append(t)

    def model_ready(self) -> bool:
        """AI đã nạp xong một mô hình và chạy xong lô làm nóng (hoặc nạp lỗi, hoặc không có AI): không còn gì phải chờ
        trước khi phát lại."""
        return self.ai is None or self.ai.warmed()

    def wait_model(self, timeout_s: float = REPLAY_AI_WAIT_S) -> bool:
        deadline = time.perf_counter() + timeout_s
        while not self.model_ready() and not self._stop.is_set() and time.perf_counter() < deadline:
            time.sleep(0.02)
        return self.model_ready()

    def _begin_replay_when_model_ready(self) -> None:
        self.wait_model()
        if not self._stop.is_set():
            self.replay.begin()

    # ---- ghi phiên ----
    def recording_meta(self, notes: dict | None = None) -> dict:
        """Phần meta.json do Rig biết: cấu hình, quy tắc ghép bộ, mode, từng camera (cổng, index, lỗi mở), LiDAR."""
        stats = {c["port"]: c for c in self.cams.camera_stats()}
        cameras = []
        for spec in self.cams.specs:
            source = self.cams.workers[spec.port].source
            cameras.append({"port": spec.port, "index": spec.index, "instance_id": spec.instance_id, "name": spec.name,
                            "source_id": spec.source_id,
                            "source_rejects_damaged": None if source is None else getattr(source, "check_truncation", None),
                            "open_error": stats.get(spec.port, {}).get("open_error")})
        lidar = None
        if self.lidar is not None:
            describe = getattr(self.lidar.source, "describe", None) if self.lidar.source is not None else None
            try:
                desc = describe() if callable(describe) else None
            except Exception as exc:  # noqa: BLE001
                desc = {"error": f"{type(exc).__name__}: {exc}"}
            lidar = {"port": self.cfg.lidar_port, "describe": desc, "open_error": self.lidar.open_error}
        return {"config": dict(self.cfg.__dict__), "policy": self.policy(), "camera_mode": dict(self.cams.mode),
                "cameras": cameras, "lidar_source": lidar,
                "replay_of": None if self.replay is None else self.replay.describe(), "notes": dict(notes or {})}

    def start_recording(self, folder, *, notes: dict | None = None, **options) -> RigRecorder:
        """Bắt đầu ghi phiên vào `folder` (phải chưa có hoặc rỗng). `options`: image_format ("jpg"/"png"), jpeg_quality,
        max_pending_mb, lidar_scans_per_part — xem `rig.recording.RigRecorder`.

        Chỉ MỘT bộ ghi chưa xong tại một thời điểm: bộ ghi trước còn ghi nốt hàng đợi (sau `stop_recording(wait=False)`)
        thì từ chối (RuntimeError, không tạo thư mục mới). Nhờ vậy `last_recorder` luôn là bộ ghi duy nhất có thể chưa
        xong — `stop()` chờ đúng nó, giao diện và bench báo đúng trạng thái cuối của nó (xem xét 24/09: trước đó bộ ghi
        cũ bị "bỏ quên", tiến trình thoát giết luồng ghi nền và bản ghi cũ mất đuôi mà không ai báo)."""
        if self.recorder is not None:
            raise RuntimeError(f"đang ghi vào {self.recorder.folder}")
        prev = self.last_recorder
        if prev is not None and not prev.finished.is_set():
            raise RuntimeError(f"bản ghi trước {prev.folder.name} còn đang ghi nốt ({prev.status()['pending_frames']} "
                               "khung chờ ghi): chờ xong rồi mới ghi phiên mới")
        rec = RigRecorder(folder, ports=[s.port for s in self.cams.specs], lidar=self.lidar is not None,
                          meta=self.recording_meta(notes), clock=self.clock, **options)
        # Gán TRƯỚC start(): lớp bọc thấy bộ ghi ngay khi nó bắt đầu nhận (t_start), không mất khung trong lúc start()
        # ghi meta.json đầu (3–80 ms đo 24/09). add_* tự bỏ qua dữ liệu khi bộ ghi chưa nhận.
        self.recorder = rec
        try:
            rec.start()
        except BaseException:
            self.recorder = None
            raise
        self.last_recorder = rec
        return rec

    def stop_recording(self, wait: bool = True, timeout: float | None = RECORD_FINISH_S) -> dict | None:
        """Ngừng đưa dữ liệu vào bộ ghi (ngay), rồi để nó ghi nốt; trả trạng thái (None nếu chưa từng ghi)."""
        rec, self.recorder = self.recorder, None
        if rec is None:
            return None if self.last_recorder is None else self.last_recorder.status()
        rec.set_final_meta(cameras_at_stop=self.cams.camera_stats(),
                           lidar_at_stop=None if self.lidar is None else self.lidar.stats(self.clock()))
        return rec.stop(wait=wait, timeout=timeout)

    def _set_loop(self) -> None:
        """Ghép bộ khi AI không tiêu thụ (không có, tắt, đang nạp), để độ lệch giữa các camera luôn được đo."""
        while not self._stop.wait(0.005):
            if self.ai is None or not self.ai.ready():
                fs = self.cams.latest_set(self.cfg.max_skew_s, max_wait_s=self.cfg.max_wait_s)
                if fs is not None:
                    self._record_set(fs)

    def _record_set(self, fs: FrameSet) -> dict | None:
        rel = lidar_vs_set(self.lidar, fs)
        if rel is not None:
            with self._lidar_lock:
                for k, v in rel.items():
                    self.lidar_offsets[k].append(v)
        return rel

    def reset_counters(self) -> None:
        """Bỏ phần khởi động (mở camera, quay mô-tơ LiDAR, nạp mô hình) khỏi số đo."""
        with self._count_lock:
            self.t_start = self.clock()
            self.series.clear()
            self.cams.reset_stats()
            if self.lidar is not None:
                self.lidar.reset_stats()
            with self._lidar_lock:
                for d in self.lidar_offsets.values():
                    d.clear()
            if self.ai is not None:
                self.ai.reset_stats()
            self.monitor.samples.clear()
            self._last_counts = self._counts()

    def stop(self, budget_s: float = 6.0, record_timeout_s: float = RECORD_FINISH_S) -> list[str]:
        """Dừng mọi luồng trong một hạn chung; LiDAR kẹt thì bị đóng cổng cưỡng bức. Trả tên các luồng chưa dừng.
        Đang ghi thì ngừng nhận ngay, rồi chờ bộ ghi ghi nốt tối đa `record_timeout_s` ("rig-recorder" nếu chưa xong)."""
        self._stop.set()
        # cả bộ ghi đã được stop_recording(wait=False) mà chưa ghi nốt xong; start_recording bảo đảm không có bộ ghi chưa
        # xong nào khác ngoài nó
        rec = self.last_recorder
        if self.recorder is not None:
            self.stop_recording(wait=False)
        for worker in (self.ai, self.lidar, self.monitor):
            if worker is not None:
                worker.stop_event.set()
        self.cams.request_stop()
        if self.replay is not None:
            self.replay.stop()                   # nguồn phát lại đang chờ lịch / hết bản ghi trả về ngay
        deadline = time.perf_counter() + budget_s
        alive = self.cams.stop(max(0.5, deadline - time.perf_counter()))
        for worker in [self.ai, self.lidar, self.monitor, *self._threads]:
            if worker is not None and worker.is_alive():
                worker.join(max(0.0, deadline - time.perf_counter()))
        if self.lidar is not None and self.lidar.shutdown_stuck():
            self.lidar.join(2.0)
        alive += [w.name for w in [self.ai, self.lidar, self.monitor, *self._threads] if w is not None and w.is_alive()]
        if rec is not None and not rec.finished.wait(record_timeout_s):
            alive.append("rig-recorder")
        self.stop_alive = alive
        return alive

    # ---- số đo ----
    def _series_loop(self) -> None:
        while not self._stop.wait(1.0):
            with self._count_lock:
                self.series.append(self._series_row())

    def _counts(self) -> dict:
        cams = self.cams.camera_stats()
        return {"frames": {c["port"]: c["frames"] for c in cams}, "dups": {c["port"]: c["duplicates"] for c in cams},
                "trunc": {c["port"]: c["truncated"] for c in cams}, "torn": {c["port"]: c["torn"] for c in cams},
                "sets": self.cams.sets_built, "rejected": self.cams.sets_rejected_skew,
                "partial_wait": self.cams.sets_partial_wait, "lagging": dict(self.cams.lagging_per_port),
                "regrouped": self.cams.sets_regrouped,
                "scans": None if self.lidar is None else self.lidar.scans}

    def _series_row(self) -> dict:
        """Số CỦA GIÂY VỪA QUA (hiệu bộ đếm), không phải tích lũy."""
        now = self.clock()
        counts = self._counts()
        last = self._last_counts or counts
        row = {"t_s": _r(now - (self.t_start or now), 2),
               "cam_frames_1s": {p: counts["frames"][p] - last["frames"].get(p, 0) for p in counts["frames"]},
               "cam_dups_1s": {p: counts["dups"][p] - last["dups"].get(p, 0) for p in counts["dups"]},
               "cam_truncated_1s": {p: counts["trunc"][p] - last.get("trunc", {}).get(p, 0) for p in counts["trunc"]},
               "cam_torn_1s": {p: counts["torn"][p] - last.get("torn", {}).get(p, 0) for p in counts["torn"]},
               "sets_built_1s": counts["sets"] - last["sets"], "sets_rejected_1s": counts["rejected"] - last["rejected"],
               "sets_partial_wait_1s": counts["partial_wait"] - last.get("partial_wait", 0),
               "cam_lagging_1s": {p: counts["lagging"][p] - last.get("lagging", {}).get(p, 0) for p in counts["lagging"]},
               "sets_regrouped_1s": counts["regrouped"] - last.get("regrouped", 0),
               "lidar_scans_1s": None if counts["scans"] is None else counts["scans"] - (last["scans"] or 0),
               "resources": self.monitor.latest()}
        if self.ai is not None:
            interval = np.asarray(self.ai.drain_interval(), float)
            row["ai_batches_1s"] = int(interval.size)
            row["ai_total_ms_median_1s"] = _r(np.median(interval)) if interval.size else None
            row["ai_total_ms_max_1s"] = _r(interval.max()) if interval.size else None
        self._last_counts = counts
        return row

    def _lidar_offset_stats(self, window: int | None) -> dict:
        with self._lidar_lock:
            return {k: dist(tail(d, window)) for k, d in self.lidar_offsets.items()}

    def policy(self) -> dict:
        """Ngưỡng ghép bộ đang dùng (ms; None = tắt), để bảng số đo ghi rõ số đi kèm quy tắc nào. `max_wait_ms` là SÀN;
        ngưỡng thực RIÊNG từng camera là max(sàn, wait_periods_of_own × chu kỳ của chính camera đó); `sets.wait_limit_ms`
        là ngưỡng lớn nhất trong bộ, `period_ms` của từng camera nằm ở bảng camera. `wait_rule` ghi quy tắc nào: json ghi
        trước tối 24/09 không có khóa này, và ở đó `wait_periods_of_fastest` là số chu kỳ của camera NHANH NHẤT. Khóa cũ
        vẫn được ghi (cùng giá trị với `wait_periods_of_own`) để trình đọc cũ không hỏng."""
        ms = lambda s: None if s is None or s <= 0 else _r(1000 * s)
        wait = ms(self.cfg.max_wait_s)
        periods = None if wait is None else WAIT_PERIODS
        return {"max_skew_ms": ms(self.cfg.max_skew_s), "max_wait_ms": wait,
                "wait_rule": None if wait is None else "own_cadence",
                "wait_periods_of_own": periods, "wait_periods_of_fastest": periods,
                "stale_after_ms": ms(self.cams.stale_after_s)}

    def recording_status(self) -> dict | None:
        return None if self.last_recorder is None else self.last_recorder.status()

    def replay_status(self) -> dict | None:
        return None if self.replay is None else self.replay.status()

    def snapshot(self, window: int | None = LIVE_WINDOW) -> dict:
        now = self.clock()
        return {"t_s": _r(now - (self.t_start or now), 2), "policy": self.policy(), "cameras": self.cams.stats(window),
                "lidar": None if self.lidar is None else {**self.lidar.stats(now), "vs_set": self._lidar_offset_stats(window)},
                "ai": None if self.ai is None else self.ai.stats(now, window), "resources": self.monitor.latest(),
                "recording": self.recording_status(), "replay": self.replay_status()}

    def summary(self) -> dict:
        now = self.clock()
        duration = now - (self.t_start or now)
        cams = self.cams.stats(window=None)
        per_cam = [{**c, "fps_mean": round(c["frames"] / duration, 2) if duration > 0 else None} for c in cams["cameras"]]
        return {"duration_s": round(duration, 2), "clock": clock_info(),
                "stamps": "camera: lúc read() trả khung (gồm giải mã); LiDAR: lúc gói chứa điểm cuối của vòng tới máy",
                "config": dict(self.cfg.__dict__),
                "camera_specs": [{"port": s.port, "index": s.index, "instance_id": s.instance_id} for s in self.cams.specs],
                "cameras": per_cam,
                "policy": self.policy(),
                "sets": {k: cams[k] for k in ("sets_built", "sets_rejected_skew", "sets_partial", "sets_blocked_not_new",
                                             "sets_partial_wait", "lagging_per_port", "partial_wait_ms", "wait_limit_ms",
                                             "sets_regrouped", "frames_skipped", "skew_ms")},
                "lidar": None if self.lidar is None else {**self.lidar.stats(now), "vs_set": self._lidar_offset_stats(None)},
                "ai": None if self.ai is None else self.ai.stats(now, window=None),
                "resources": self.monitor.summary(), "stop_alive": self.stop_alive,
                "recording": self.recording_status(), "replay": self.replay_status()}
