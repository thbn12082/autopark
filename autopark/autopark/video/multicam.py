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
- **Chờ camera chậm có giới hạn (`max_wait_s`, mặc định tắt ở lớp này; `RigConfig` bật 60 ms).** Đo 23/09: cổng 1 ở
  480p có đợt 26–36 % khung hỏng (còn ≈ 15–18 khung tốt/s so với 24), và vì quy tắc trên, cả chuỗi chậm theo nó. Khi
  bật, `max_wait_s` là SÀN; ngưỡng chờ thực L = max(`max_wait_s`, 1,5 × chu kỳ khung của camera NHANH nhất) — chu kỳ
  khung là chu kỳ TRUNG BÌNH đo từ 26 lần khung tới gần nhất, gồm cả khung cắt/xé mà nguồn đã loại
  (`CameraWorker.frame_interval_s`, `CameraWorker.arrivals`; chưa đủ 3 lần thì chưa rõ; không camera nào rõ thì
  L = `max_wait_s`). Nhịp camera đo được ở 24 fps KHÔNG đều: khoảng cách xen kẽ ≈ 31/48 ms, trung bình 41,9 ms
  (GIAI_DOAN_1_CAMERA.md mục 4.1), nên L ≈ 1,5 × 41,9 ≈ 63 ms (phát lại m04: 62,4 ms); ở 15 fps ≈ 100 ms. Nếu vài camera
  đã có khung mới mà camera khác chưa, bộ vẫn chờ, nhưng được phát KHÔNG CÓ các camera chưa có khung mới ngay khi
  (a) khung mới cũ nhất đang chờ đã chờ quá L, hoặc
  (b) không camera nào đang chờ còn đáng chờ (`worth_waiting`): camera đã rõ chu kỳ P của chính nó thì khung "đúng
      lượt" của nó cho nhóm đang chờ được dự đoán từ khung cuối + m·P; không đáng chờ khi khung đó đã trễ quá P/2 (nó
      lỡ khung) hoặc tới sau khung mới cũ nhất quá một chu kỳ của camera nhanh nhất (nó thuộc nhóm sau: camera chậm
      đều). Camera chưa rõ chu kỳ: như bản đầu — không đáng chờ khi đã im quá L.
  Sau đó (c) sửa "khóa lệch pha" (`out_of_phase`): độ lệch pha của từng camera = trung vị, qua REGROUP_SETS = 5 bộ ứng
  viên đủ liên tiếp cùng thành phần, của stamp camera đó trừ stamp trung bình của bộ; nếu các độ lệch này chia hai cụm
  — khe lớn nhất g đủ lớn để bộ sau lệch ≈ P − g, ít hơn độ lệch S hiện tại quá P/3 — và trong chính bộ sắp phát mọi
  khung của cụm mới tới sau mọi khung của cụm cũ, thì cụm mới được để dành cho bộ sau (`FrameSet.deferred`, đếm ở
  `sets_regrouped`; chỉ ở bộ không có camera đang chờ, và khi mọi camera của cụm cũ đã rõ nhịp và cùng nhịp — camera mới
  vào được sửa sau 5 bộ). Bản trước quyết trên MỘT bộ: với nhịp xen kẽ 31/48 ms, stamp của hai camera cùng chu kỳ dao
  động ±8 ms, cỡ ngưỡng P/3, nên (c) tách liên tục những bộ vốn đúng nhóm (người kiểm tra, 24/09).
  Vì sao như vậy (bản đầu ngày 24/09 dùng L cố định và (b) = "mọi camera đang chờ im quá L"; người kiểm tra và mô
  phỏng tìm ra ba lỗi): (1) camera KHỎE chạy dưới 1/`max_wait_s` (dưới 16,7 fps với 60 ms — `--fps 15`, hay phơi sáng
  tự động chỗ tối) im quá 60 ms giữa hai khung bình thường, nên (b) bỏ luân phiên một camera khỏe ở mọi bộ; (2) camera
  vừa lỡ một khung đã "im quá L" dù khung kế chỉ còn 2 ms nữa, nên bị bỏ thêm một bộ; (3) mỗi camera chỉ chọn trong
  khung chưa dùng, nên khi một camera vào sau (mở lần lượt, hay quay lại sau khi mất) ở pha không may, bộ ghép khung
  chu kỳ k của camera này với chu kỳ k+1 của camera kia và cứ thế mãi: bốn camera 24 fps gần cùng pha cho độ lệch
  trung vị ≈ 40 ms thay vì ≈ 6 ms của quy tắc cũ. Lấy camera nhanh nhất (không phải trung vị) cho L để chính camera
  chậm không nâng ngưỡng của nó.
  Mô phỏng bằng đồng hồ giả ngày 24/09 (camera mở lần lượt cách nhau 0,3 s, ghép bộ mỗi 2 ms, tính 6 s sau 2 s khởi
  động, rung stamp ±1–4 ms, 3 hạt ngẫu nhiên; KHÔNG đo trên phần cứng): bốn camera khỏe 24, 15, 12 hay 10 fps → mọi
  bộ đủ bốn camera, độ lệch trung vị chênh quy tắc cũ tối đa 5,3 ms (24 fps gần cùng pha: 5,9–6,0 ms so với 5,9); ba
  camera 24 fps + một camera đều 12 hoặc 8 fps → 24 bộ/s, chỉ camera chậm bị bỏ, độ lệch trung vị ≈ 20 ms (quy tắc
  cũ: 12 hoặc 8 bộ/s, ≈ 47 ms); một camera mất 30–33 % khung ngẫu nhiên ở 24 fps → ≈ 24 bộ/s (quy tắc cũ 15–16 bộ/s),
  chỉ camera đó bị bỏ, khung mới chờ tối đa 50 ms. Chỗ còn TỆ HƠN quy tắc cũ: pha bốn camera trải rộng đúng bằng
  `max_skew_s` (12 fps, pha 0/20/40/60 ms) → phần lớn bộ bị bỏ vì lệch ở cả hai quy tắc, bật chờ còn 1,5–2,3 bộ/s so
  với 3,8 bộ/s khi tắt — giới hạn của `max_skew_s` cố định 60 ms, chưa sửa. Chỗ còn mơ hồ: pha bốn camera trải gần hết
  một chu kỳ (0/10/20/30 ms ở 24 fps) và stamp rung ±4 ms thì khung "đúng lượt" của camera cuối nhóm rơi sát mép "một
  chu kỳ sau khung cũ nhất", nên thỉnh thoảng một camera khỏe bị bỏ một bộ (mô phỏng: 1 trong 60 hạt × 4 s, thêm một
  camera mất 33 % khung). Sàn 60 ms và các hệ số 1,5, P/2, P/3, 1,25 là lựa chọn thiết kế, CHƯA đo trên phần cứng.
  Mô phỏng trên chỉ dùng LƯỚI ĐỀU. Với nhịp đo được, bản trước ngày 24/09 (chu kỳ theo "một lưới" ra ≈ 24–33 ms thay vì
  41,9; (c) quyết trên một bộ) KHÔNG đúng với câu "chỉ camera đó bị bỏ": phát lại khoảng cách khung thật của m04 (bốn
  camera 480p, không mất khung; 4 bộ pha × rung 0/3 ms, AI 15 ms mỗi lô, max_skew 60 ms) chỉ 43–78 % bộ đủ bốn camera,
  mỗi camera khỏe bị bỏ 3–17 % số bộ, 26–30 bộ/s (vượt 23,9 khung/s của camera), L = 60 ms. Sau bản sửa (chu kỳ trung
  bình trên `arrivals`, (c) trên trung vị 5 bộ), cùng phép phát lại: 100 % bộ đủ, không lần bỏ hay để dành nào,
  23,8–23,9 bộ/s (tắt chờ: 21,4–23,9), L trung vị 62,4 ms; nhịp tới theo tick USB 16 ms (pha cố định) cũng vậy. Nhịp
  Markov 31,4/48,3 ms độc lập từng camera (pha giữa các camera TRÔI ngẫu nhiên, khắc nghiệt hơn m04), 20 s × 20 lần
  chạy: mỗi camera khỏe bị bỏ 0,2–2,1 % số bộ (bản trước 18–24 %), 92–96 % bộ đủ, 3–15 lần để dành — phần bỏ còn lại do
  mép "nhóm sau" của (b) (khung của camera cho nhóm này đã vào bộ trước), chưa sửa. Mọi số `lagging_per_port`,
  `sets_partial_wait`, `partial_wait_ms`, `wait_limit_ms`, `sets_regrouped`, `skew_ms` của phiên BẬT chờ chạy trước bản
  sửa này KHÔNG dùng được (24/09: runs/rig_bench chỉ có loạt 20260923, chạy quy tắc cũ, nên chưa có phiên nào như thế).
  Các camera bị bỏ vì chờ nằm ở `FrameSet.lagging`, KHÁC `missing` (không có khung nào trong `stale_after_s`, hoặc không
  mở được) và khác `deferred` (có khung mới nhưng để bộ sau). Khi bật, khung "mới" = CHƯA vào bộ nào VÀ còn tươi
  (≤ `stale_after_s`): nếu chọn cả khung đã dùng, lúc camera chậm quay lại khung của nó gần khung nhanh đã dùng hơn và
  bộ bị chặn tiếp; nếu tính cả khung cũ, camera quay lại sau khi "missing" mang theo khung trước đợt im trong vòng đệm,
  "đã chờ" bị đo từ khung cũ hàng trăm ms và (a) bỏ ngay một camera khỏe. Độ lệch và mốc chỉ tính trên các camera có
  trong bộ. Vì đổi cả cách chọn khung, số đo cũ (trước 24/09) chỉ so được với phiên chạy tắt chờ.
- **Đồng hồ:** mọi stamp dùng `RIG_CLOCK = time.perf_counter` (QPC, phân giải 100 ns trên Windows). KHÔNG dùng
  `time.monotonic`: trên Python 3.12 của Windows nó là GetTickCount64, bước 15,6 ms — các số đo độ lệch vài chục ms
  sẽ bị làm tròn thô (lỗi của bản đầu, phát hiện ngày 23/09). Stamp là thời điểm `read()` trả khung về Python, đã gồm
  chờ và giải mã, **không phải** thời điểm phơi sáng; độ lệch đo được là độ lệch lúc đến, không phải lúc chụp.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from itertools import islice
import threading
import time
from typing import Callable

import numpy as np

from .sources import Frame, FrameReadError, UsbCameraSource

RIG_CLOCK = time.perf_counter
STALE_AFTER_S = 0.5       # camera không có khung mới lâu hơn thế thì bị loại khỏi bộ ảnh và báo "cũ"
LIVE_WINDOW = 3000        # số trực tiếp (giao diện, chuỗi theo giây) chỉ tính trên chừng ấy mẫu cuối
WAIT_PERIODS = 1.5        # ngưỡng chờ camera chậm ≥ chừng ấy chu kỳ khung của camera nhanh nhất (xem đầu module)
CADENCE_FRAMES = 25       # chu kỳ khung đo trên chừng ấy khoảng cách giữa các lần khung tới gần nhất (tốt + cắt/xé)
SEED_SPAN = 1.3           # chu kỳ khung: hạt giống = trung bình các khoảng ≤ chừng ấy × phân vị 25 % (xem frame_interval_s)
WIDEN_SPAN = 1.75         # một bước nới: kéo nhóm khoảng dài (48–52 ms) của nhịp 31/48 ms vào nhóm "một khoảng"
SINGLE_SPAN = 1.6         # "một khoảng" = ≤ chừng ấy × chu kỳ (khoảng gộp ≥ 76 ms của nhịp 31/48, hay 2P của nhịp đều, ở ngoài)
OUTAGE_PERIODS = 4        # khoảng dài hơn chừng ấy chu kỳ là đợt im, không dùng để ước lượng chu kỳ
REGROUP_GAIN = 1 / 3      # chỉ ghép lại pha khi độ lệch bộ giảm hơn chừng ấy chu kỳ (rung stamp không làm đảo qua lại)
SAME_CADENCE = 1.25       # "cùng nhịp": chu kỳ đo được ≤ chừng ấy × chu kỳ camera nhanh nhất
REGROUP_SETS = 5          # (c) quyết trên trung vị độ lệch từng camera qua chừng ấy bộ ứng viên đủ, cùng thành phần


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
        # thời điểm tới của mọi khung MỚI của camera — khung tốt VÀ khung cắt cụt/xé (camera đã gửi một khung, nó chỉ hỏng
        # trên đường USB) — để đo nhịp camera (`frame_interval_s`) cả khi phần lớn khung hỏng. Không ghi "khung cũ"
        # (driver trả lại bộ đệm trước) hay lần đọc hỏng: đó không phải một khung mới.
        self.arrivals: deque[float] = deque(maxlen=CADENCE_FRAMES + 1)
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
                    # UsbCameraSource gắn thời điểm đọc vào lỗi (`exc.t`, từ 24/09). Nguồn không gắn (nguồn giả, nguồn khác)
                    # thì lấy đồng hồ ngay khi lỗi tới, tức trễ hơn bằng thời gian nguồn kiểm khung: khoảng trước khung
                    # hỏng dài ra và khoảng sau ngắn lại đúng bằng nhau, nên chu kỳ TRUNG BÌNH không đổi.
                    t_err = getattr(exc, "t", None)
                    t_err = self.clock() if t_err is None else t_err
                    with self.lock:
                        self._count_error(str(exc), t_err)
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
                    self.arrivals.append(t)
        finally:
            try:
                self.source.close()
            except Exception:  # noqa: BLE001
                pass

    def _count_error(self, message: str, t: float | None = None) -> None:
        """Đếm một lần đọc hỏng (gọi trong `self.lock`). Khung cắt cụt/xé là một khung MỚI đã tới ở `t`: ghi vào
        `arrivals` để nhịp camera vẫn đo đúng khi nhiều khung hỏng."""
        if "previous frame" in message:
            self.stats.duplicates += 1
        elif "truncated frame" in message:
            self.stats.truncated += 1
            if t is not None:
                self.arrivals.append(t)
        elif "torn frame" in message:
            self.stats.torn += 1
            if t is not None:
                self.arrivals.append(t)
        else:
            self.stats.read_failures += 1
            self.stats.last_error = message

    def snapshot(self) -> list[tuple[int, Frame]]:
        with self.lock:
            return list(self.ring)

    def frame_interval_s(self, n: int = CADENCE_FRAMES) -> float | None:
        """Chu kỳ khung TRUNG BÌNH của camera, đo từ n + 1 lần khung tới gần nhất (`arrivals`: khung tốt và khung
        cắt/xé). None khi chưa có 3 lần.

        Nhịp thật KHÔNG đều: ở phơi sáng tự động khoảng cách xen kẽ ≈ 31 / 48 ms, không bao giờ hai khoảng ngắn liền
        nhau, trung bình 41,9 ms (GIAI_DOAN_1_CAMERA.md mục 4.1). Bản trước coi khung nằm trên MỘT lưới chu kỳ (gốc =
        phân vị 25 %, g / round(g / gốc), trung vị): gốc rơi vào cụm 31 ms, khoảng 48 ms bị chia đôi, chu kỳ ra ≈ 24–34 ms
        (có lúc nhảy lên ≈ 47 ms), và quy tắc (b) bỏ camera KHỎE: phát lại m04 chỉ 43–78 % bộ đủ bốn camera (người kiểm
        tra, tái hiện 24/09). Cách tính bây giờ:
        (1) b = trung bình các khoảng ≤ SEED_SPAN × phân vị 25 %; (2) một bước nới: b = trung bình các khoảng
        ≤ WIDEN_SPAN × b (cụm 31 ms rung xuống 26 ms vẫn kéo cụm 48–52 ms vào); (3) lặp b = trung bình các khoảng
        ≤ SINGLE_SPAN × b tới khi đứng (khoảng gộp hai khung ≥ 76 ms của nhịp 31/48, hay 2P của nhịp đều, bị đẩy ra);
        (4) P = Σg / Σk trên các khoảng có k = max(1, round(g / b)) ≤ OUTAGE_PERIODS (đợt im dài hơn không tính), lặp ba
        lần — khoảng gộp vì khung không tới (driver bỏ hẳn, hay chỉ có khung tốt khi nguồn không báo khung hỏng) được
        tính đúng số khung. Các hệ số là lựa chọn thiết kế, kiểm bằng mô phỏng đồng hồ giả và chuỗi khoảng cách đo được
        (m04), CHƯA đo trực tiếp trên bàn thử."""
        with self.lock:                                # luồng camera ghi `arrivals` đồng thời
            arrivals = self.arrivals
            if len(arrivals) < 3:
                return None
            stamps = list(islice(reversed(arrivals), n + 1))
        gaps = [a - b for a, b in zip(stamps, stamps[1:])]          # stamps mới → cũ: a − b > 0
        base = sorted(gaps)[(len(gaps) - 1) // 4]
        if base <= 0:
            return None

        def mean_upto(cap: float) -> float:                         # luôn khác rỗng: cap ≥ base, mà base là một khoảng
            sel = [g for g in gaps if g <= cap]
            return sum(sel) / len(sel)

        b = mean_upto(WIDEN_SPAN * mean_upto(SEED_SPAN * base))
        for _ in range(8):
            nb = mean_upto(SINGLE_SPAN * b)
            if nb == b:
                break
            b = nb
        for _ in range(3):
            ks = [(g, max(1, round(g / b))) for g in gaps]
            ks = [(g, k) for g, k in ks if k <= OUTAGE_PERIODS]
            b = sum(g for g, _ in ks) / sum(k for _, k in ks)
        return b

    def reset_stats(self) -> None:
        with self.lock:
            s = self.stats
            s.frames, s.duplicates, s.truncated, s.torn, s.read_failures, s.gap_max_s = 0, 0, 0, 0, 0, 0.0


@dataclass
class FrameSet:
    frames: dict[int, Frame]              # cổng → khung (chỉ các camera CÓ trong bộ)
    seqs: dict[int, int]
    anchor_t: float                       # mốc: khung mới nhất của camera chậm nhất trong số camera có trong bộ
    skew_s: float                         # stamp lớn nhất − nhỏ nhất trong bộ
    missing: list[int]                    # cổng bị loại vì không có khung hoặc khung quá cũ (> stale_after_s)
    t_built: float
    lagging: list[int] = field(default_factory=list)   # cổng còn khung tươi nhưng chưa có khung mới, bị bỏ sau khi chờ
    waited_s: float | None = None         # bộ thiếu camera chậm: khung mới cũ nhất đã chờ bao lâu lúc phát bộ
    wait_limit_s: float | None = None     # bật chờ: ngưỡng hiệu dụng L lúc phát bộ = max(max_wait_s, 1,5 × chu kỳ nhanh nhất)
    # bật chờ: cổng CÓ khung mới nhưng khung đó thuộc chu kỳ sau so với các camera còn lại → để dành cho bộ sau (sửa lệch
    # pha, xem đầu module). Khác `lagging`: camera không chậm; AI và giao diện vẫn dùng kết quả gần nhất của nó.
    deferred: list[int] = field(default_factory=list)

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
        # stamp các bộ ứng viên ĐỦ (không camera đang chờ) gần nhất, cùng thành phần, cho quy tắc (c) `out_of_phase`
        self._phase_hist: deque[dict[int, float]] = deque(maxlen=REGROUP_SETS)
        self.skews: deque[float] = deque(maxlen=200_000)
        self.waits: deque[float] = deque(maxlen=200_000)    # FrameSet.waited_s của các bộ thiếu camera chậm đã phát
        self.wait_limits: deque[float] = deque(maxlen=200_000)   # FrameSet.wait_limit_s của mọi bộ đã phát khi bật chờ
        self.reset_stats()

    def reset_stats(self) -> None:
        with self._lock:
            self.sets_built = 0
            self.sets_rejected_skew = 0
            self.sets_partial = 0
            # bộ ứng viên bị chặn vì có camera chưa có khung mới (đếm mỗi bộ một lần). Khi bật chờ: mỗi trạng thái "khung
            # mới nhất của từng camera" bị giữ lại được đếm một lần; một phần sau đó được phát thành bộ thiếu camera chậm.
            self.sets_blocked_not_new = 0
            self.sets_partial_wait = 0            # bộ đã phát thiếu camera chậm sau khi chờ (max_wait_s)
            self.lagging_per_port = {port: 0 for port in self.workers}  # số bộ đã phát mà cổng này bị bỏ vì chậm
            self.sets_regrouped = 0               # bộ đã phát sau khi để dành camera lệch pha cho bộ sau (FrameSet.deferred)
            self.frames_skipped = {port: 0 for port in self.workers}   # khung không bao giờ vào bộ nào
            self.skews.clear()
            self.waits.clear()
            self.wait_limits.clear()
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

    def latest_set(self, max_skew_s: float | None = None, require_new: bool = True,
                   max_wait_s: float | None = None) -> FrameSet | None:
        """Bộ ảnh mới nhất. `require_new`: chỉ trả khi mọi camera trong bộ đều có khung khác bộ trước (kể cả bộ bị bỏ),
        để không suy luận lại khung cũ. Bộ lệch hơn `max_skew_s` bị bỏ (đếm vào `sets_rejected_skew`).

        `max_wait_s` (None hoặc ≤ 0 = tắt, đúng quy tắc cũ): SÀN của ngưỡng chờ. Camera chưa có khung mới được chờ tối
        đa L = max(max_wait_s, 1,5 × chu kỳ khung của camera nhanh nhất), rồi bộ được phát không có nó
        (`FrameSet.lagging`, đếm ở `sets_partial_wait` và `lagging_per_port`; L ghi ở `FrameSet.wait_limit_s`) — xem
        đầu module."""
        rings = self.rings()
        fs = build_set(rings, self.clock(), self.stale_after_s)
        if fs is None:
            return None
        with self._lock:
            last = self._last_seqs
            if require_new and last is not None:
                if max_wait_s is not None and max_wait_s > 0:
                    fs = self._new_frames_set(rings, fs, last, max_wait_s)
                    if fs is None:
                        return None
                else:
                    same = [last.get(port) == seq for port, seq in fs.seqs.items()]
                    if all(same):
                        return None                     # đúng bộ trước: không camera nào có khung mới, không đếm
                    if any(same):                        # vài camera có khung mới, vài camera chưa: bộ bị chặn
                        self._count_blocked(tuple(sorted(fs.seqs.items())))
                        return None
            if last is not None:
                for port, seq in fs.seqs.items():
                    prev = last.get(port)
                    if prev is not None and seq > prev + 1:
                        self.frames_skipped[port] = self.frames_skipped.get(port, 0) + seq - prev - 1
            # camera chậm hay để dành (lagging/deferred) vẫn giữ seq đã dùng lần cuối (để khung đã dùng của nó không bị coi
            # là mới, còn khung để dành vẫn mới); camera "missing" bị xóa seq như quy tắc cũ — khung trước đợt im của nó bị
            # loại ở `_new_frames_set` bằng ngưỡng tuổi stale_after_s. Khi tắt chờ, lagging/deferred luôn rỗng: kết quả
            # đúng bằng dict(fs.seqs) (số đo cũ so được).
            kept = set(fs.lagging) | set(fs.deferred)
            seqs = {} if last is None else {p: s for p, s in last.items() if p in kept}
            seqs.update(fs.seqs)
            self._last_seqs = seqs
            self.skews.append(fs.skew_s)
            if max_skew_s is not None and fs.skew_s > max_skew_s:
                self.sets_rejected_skew += 1
                return None
            self.sets_built += 1
            if fs.wait_limit_s is not None:
                self.wait_limits.append(fs.wait_limit_s)
            if fs.deferred:
                self.sets_regrouped += 1
            if fs.missing:
                self.sets_partial += 1
            if fs.lagging:
                self.sets_partial_wait += 1
                for port in fs.lagging:
                    self.lagging_per_port[port] = self.lagging_per_port.get(port, 0) + 1
                if fs.waited_s is not None:
                    self.waits.append(fs.waited_s)
        return fs

    def _count_blocked(self, key: tuple) -> None:
        if key != self._blocked_key:
            self._blocked_key = key
            self.sets_blocked_not_new += 1

    def frame_periods(self, ports) -> dict[int, float | None]:
        """Chu kỳ khung đo được của từng cổng (None: chưa đủ 3 khung tốt)."""
        return {p: self.workers[p].frame_interval_s() for p in ports}

    def wait_limit_s(self, max_wait_s: float, periods: dict[int, float | None]) -> float:
        """Ngưỡng chờ hiệu dụng L = max(max_wait_s, WAIT_PERIODS × chu kỳ khung của camera NHANH nhất).
        Nhanh nhất, không phải trung vị: với hai–ba camera, trung vị bị chính camera chậm kéo lên."""
        known = [iv for iv in periods.values() if iv is not None]
        return max(max_wait_s, WAIT_PERIODS * min(known)) if known else max_wait_s

    @staticmethod
    def worth_waiting(t_last: float, t_old: float, now: float, period: float | None, limit: float,
                      fastest: float | None) -> bool:
        """Quy tắc (b): camera chưa có khung mới còn đáng chờ không.

        Chu kỳ chưa rõ (< 3 khung tốt): như bản đầu — đáng chờ khi nó im chưa quá L. Đã rõ chu kỳ P của CHÍNH nó: khung
        "đúng lượt" cho nhóm khung đang chờ là khung dự đoán t_last + m·P gần khung mới cũ nhất t_old nhất (m ≥ 1, vì
        khung t_last đã dùng). Đáng chờ khi khung đó thuộc nhóm đang chờ — tới trước t_old + một chu kỳ của camera nhanh
        nhất (muộn hơn thì khung kế của camera nhanh đã tới, nhóm sau mới là nhóm của nó) và trong hạn (a) — và chưa trễ
        quá nửa chu kỳ P. Nhờ vậy camera vừa lỡ MỘT khung vẫn được chờ nếu khung kế của nó sắp tới (chỉ đo "im bao lâu"
        thì bỏ nó 2 ms trước khung kế — mô phỏng 24/09), còn camera chậm đều thì bị bỏ ngay ở những nhóm không có khung
        của nó, không phải chờ hết L."""
        if period is None:
            return now - t_last <= limit
        slot = t_last + max(1, round((t_old - t_last) / period)) * period
        horizon = t_old + min(limit, fastest if fastest is not None else limit)
        return slot < horizon and now <= slot + 0.5 * period

    @staticmethod
    def out_of_phase(fs: FrameSet, periods: dict[int, float | None],
                     history: list[dict[int, float]] | None = None) -> list[int]:
        """Cổng nên để dành cho bộ sau vì bộ `fs` ghép khung của hai chu kỳ khác nhau ("khóa lệch pha").

        Độ lệch pha của từng camera = trung vị, qua các bộ trong `history` ({cổng: stamp}, gồm cả bộ `fs`), của stamp
        camera đó trừ stamp trung bình của bộ; không có `history` thì chỉ dùng bộ `fs` (như bản đầu). Sắp các camera theo
        độ lệch đó, tìm khe lớn nhất g: cụm cũ (trước khe) và cụm mới (sau khe). Nếu phát cụm cũ bây giờ và để cụm mới
        ghép với khung KẾ TIẾP của cụm cũ (tới sau ≈ một chu kỳ P), độ lệch bộ sau ≈ P − g, thay vì độ lệch hiện tại S
        (trải của các độ lệch). Chỉ làm khi S − (P − g) > REGROUP_GAIN × P, mọi camera của cụm cũ đã đo được chu kỳ
        ≤ SAME_CADENCE × P (camera chậm hay chưa rõ nhịp thì không đoán được khung kế của nó tới lúc nào), và trong CHÍNH
        bộ `fs` mọi khung của cụm mới tới sau mọi khung của cụm cũ.

        Vì sao cần trung vị: nhịp thật xen kẽ ≈ 31/48 ms, nên stamp của hai camera cùng chu kỳ lệch nhau dao động ±8 ms
        — cỡ ngưỡng P/3 ≈ 14 ms. Quyết trên từng bộ thì (c) tách liên tục những bộ vốn đúng nhóm (phát lại nhịp m04, P
        đúng, pha 0/8/16/24 ms: 165 lần tách trong ≈ 24 s, chỉ 76 % bộ đủ bốn camera; pha 0/11/22/33: 47 lần, 92 % —
        người kiểm tra, tái hiện 24/09). Trung vị qua 5 bộ, cùng phép phát lại: 0 lần tách, 100 % bộ đủ."""
        known = [iv for iv in periods.values() if iv is not None]
        if len(fs.frames) < 2 or not known:
            return []
        period = min(known)
        cur = {p: f.meta.stamp.t for p, f in fs.frames.items()}
        hist = history or [cur]
        offs = {p: float(np.median([h[p] - sum(h.values()) / len(h) for h in hist])) for p in cur}
        order = sorted(cur, key=lambda p: (offs[p], cur[p]))
        ts = [offs[p] for p in order]
        k = max(range(1, len(ts)), key=lambda i: ts[i] - ts[i - 1])
        gap, spread = ts[k] - ts[k - 1], ts[-1] - ts[0]
        if spread - (period - gap) <= REGROUP_GAIN * period:
            return []
        if any(periods.get(p) is None or periods[p] > SAME_CADENCE * period for p in order[:k]):
            return []
        if min(cur[p] for p in order[k:]) <= max(cur[p] for p in order[:k]):
            return []                                   # bộ này rung ngược thứ tự hai cụm: chưa tách
        return sorted(order[k:])

    def _new_frames_set(self, rings: dict[int, list[tuple[int, Frame]]], fs: FrameSet, last: dict[int, int],
                        max_wait_s: float) -> FrameSet | None:
        """Quy tắc chờ có giới hạn (gọi trong `self._lock`; khóa từng camera chỉ được giữ ngắn bên trong, không ai giữ
        khóa camera rồi xin khóa này). `fs` là bộ ứng viên đủ camera tươi, chỉ dùng để biết camera nào tươi và camera nào
        "missing"; bộ trả về chỉ gồm khung CHƯA vào bộ nào VÀ còn tươi (≤ stale_after_s)."""
        now = fs.t_built
        fresh = sorted(fs.frames)
        # Khung mới = chưa vào bộ nào VÀ còn tươi. Camera từng "missing" bị xóa seq khỏi _last_seqs (hoặc chưa từng có seq
        # vì đã im từ trước bộ đầu); lúc nó quay lại, vòng đệm còn khung trước đợt im, luôn cũ hơn stale_after_s. Tính
        # chúng là khung đang chờ thì `waited` đo từ khung cũ hàng trăm ms, (a) bắn ngay và bỏ một camera khỏe.
        new = {p: [item for item in rings[p]
                   if (last.get(p) is None or item[0] > last[p]) and now - item[1].meta.stamp.t <= self.stale_after_s]
               for p in fresh}
        ready = [p for p in fresh if new[p]]
        waiting = [p for p in fresh if not new[p]]
        if not ready:
            return None                                 # không camera nào có khung mới: không đếm, như quy tắc cũ
        periods = self.frame_periods(fresh)
        limit = self.wait_limit_s(max_wait_s, periods)
        t_old = min(new[p][0][1].meta.stamp.t for p in ready)      # khung mới cũ nhất đang chờ
        waited = now - t_old
        if waiting:
            # (a) khung mới cũ nhất đã chờ quá L; (b) KHÔNG camera nào đang chờ còn đáng chờ (xem `worth_waiting`)
            known = [iv for iv in periods.values() if iv is not None]
            fastest = min(known) if known else None
            expected = [p for p in waiting
                        if self.worth_waiting(rings[p][-1][1].meta.stamp.t, t_old, now, periods[p], limit, fastest)]
            if waited <= limit and expected:
                self._count_blocked(("wait",) + tuple((p, rings[p][-1][0]) for p in fresh))
                return None                             # còn trong hạn chờ
        out = build_set({p: new[p] for p in ready}, now, self.stale_after_s)
        # (c) chỉ khi không camera nào đang chờ: khóa lệch pha là trạng thái ổn định của bộ ĐỦ; bộ phát vì hết hạn chờ đã
        # xáo nhóm, để dành thêm ở đó làm mất khung cũ còn chưa dùng của chính camera được để dành (mô phỏng 24/09).
        # Quyết trên REGROUP_SETS bộ ứng viên đủ liên tiếp cùng thành phần (xem `out_of_phase`). Bộ phát vì hết hạn chờ
        # KHÔNG xóa lịch sử: bộ đủ và bộ thiếu xen kẽ nhau thì (c) không bao giờ gom đủ bộ (người kiểm tra thử, 24/09).
        deferred = []
        if not waiting:
            cur = {p: f.meta.stamp.t for p, f in out.frames.items()}
            if self._phase_hist and set(self._phase_hist[-1]) != set(cur):
                self._phase_hist.clear()                # đổi thành phần bộ (camera mất / quay lại): đo lại từ đầu
            self._phase_hist.append(cur)
            if len(self._phase_hist) == REGROUP_SETS:
                deferred = self.out_of_phase(out, periods, list(self._phase_hist))
                if deferred:
                    self._phase_hist.clear()            # nhóm đã đổi: độ lệch cũ không còn đúng
        if deferred:                                    # khung mới của các cổng này để nguyên (vẫn "mới") cho bộ sau
            # cụm cũ giữ ĐÚNG khung đã chọn: ghép lại từ cả vòng đệm thì mốc đổi và camera có hai khung mới nhảy sang khung
            # mới hơn, khung cũ của nó bị bỏ qua (mô phỏng 24/09)
            out = build_set({p: [(out.seqs[p], out.frames[p])] for p in out.frames if p not in deferred}, now,
                            self.stale_after_s)
        out.missing, out.lagging, out.deferred = list(fs.missing), waiting, deferred
        out.waited_s = waited if waiting else None
        out.wait_limit_s = limit
        return out

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
            waits = tail(self.waits, window)
            limits = tail(self.wait_limits, window)
            counts = {"sets_built": self.sets_built, "sets_rejected_skew": self.sets_rejected_skew,
                      "sets_partial": self.sets_partial, "sets_blocked_not_new": self.sets_blocked_not_new,
                      "sets_partial_wait": self.sets_partial_wait, "lagging_per_port": dict(self.lagging_per_port),
                      "sets_regrouped": self.sets_regrouped,
                      "frames_skipped": dict(self.frames_skipped)}
        return {"cameras": self.camera_stats(), **counts, "skew_ms": dist(skews, 1000.0),
                "partial_wait_ms": dist(waits, 1000.0), "wait_limit_ms": dist(limits, 1000.0),
                "skew_window": "cả phiên" if window is None else f"{window} bộ cuối"}
