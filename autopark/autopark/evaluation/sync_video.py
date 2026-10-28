"""Phía video của dấu đồng bộ T14 (docs/KIEM_THU_VA_LO_TRINH.md): tìm các lần nháy ô trắng của
`ui/sync_flash.py` trong một video và ghép chúng với các dòng SYNC_MARK của tệp dấu đồng bộ (`evaluation/sync_marks.py`)
thành cặp đồng bộ `mark` cho tệp tham chiếu (`reference_pose.SyncPair`). Thêm 02/10/2026 cho T4 (camera trên cao), dùng
được cả cho video bên hông R3.

**Khởi đầu nháy** (quy tắc của KICH_BAN mục 2.5): khung ĐẦU TIÊN có ít nhất một nửa vùng ô (ROI do người chọn, nằm trong
ô trắng) sáng hơn nền ≥ 60 mức xám, theo stamp của chính tệp video. Nền = trung vị độ xám vùng đó trên 1 s gần nhất của
các khung không nháy (lúc đầu: trung vị của tối đa 10 khung đầu). Một lần nháy dài 0,2–1,0 s (T14 nháy 500 ms) và bắt
đầu ≥ 0,8 s sau lần trước (T14 cách nhau ≥ 1 s); lần khác bị bỏ.

**Ghép với dấu:**

- Đồng hồ `perf_counter` (video của `video.overhead_record` trên chính laptop chạy phiên): dấu có t_perf trong
  [t_khởi đầu − 0,5 s, t_khởi đầu]; hai dấu cùng lọt cửa sổ thì báo lỗi. Hiệu t_khởi đầu − t_perf của dấu là cận trên
  của độ trễ chụp + hiển thị (`overhead_ref` ghi vào `source.flash_offsets`).
- Đồng hồ `video`: độ lệch hằng c sao cho nhiều lần nháy trùng (± 0,1 s) với t_perf + c nhất, chọn trong mọi hiệu
  khởi đầu − dấu; phải duy nhất và có ≥ 2 lần trùng. Chỉ một lần nháy thì cần `first_mark` (`--first-mark n`).

Sai số: ± một khung (p95 khoảng cách khung), cộng độ trễ hiển thị L CHƯA ĐO. Ngưỡng ĐỀ XUẤT – CHỜ CHỐT (người dùng giao
quyết định 02/10/2026). Mới kiểm trên ảnh tổng hợp (tests/test_sync_video.py); CHƯA THỬ với màn hình và camera thật.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import statistics

import numpy as np

from autopark.evaluation.overhead_ref import OverheadError
from autopark.evaluation.reference_pose import SyncPair

DELTA = 60                 # sáng hơn nền chừng này mức xám
MIN_FRACTION = 0.5         # ≥ nửa vùng ô
MIN_DURATION_S = 0.2
MAX_DURATION_S = 1.0
MIN_GAP_S = 0.8            # giữa hai khởi đầu
BASELINE_S = 1.0
INIT_FRAMES = 10
MAX_LATENCY_S = 0.5        # đồng hồ perf_counter: dấu ở [khởi đầu − 0,5 s, khởi đầu]
MATCH_TOL_S = 0.1          # đồng hồ video: trùng trong ± 0,1 s


@dataclass(frozen=True)
class FlashOnset:
    index: int             # số khung của khung đầu sáng
    t: float               # thời điểm của khung đó (đồng hồ của video)
    duration_s: float
    peak: float            # phần vùng ô sáng lớn nhất trong lần nháy

    def to_dict(self) -> dict:
        return {"frame": self.index, "t": self.t, "duration_s": self.duration_s, "peak": self.peak}


def roi_bright_fraction(image: np.ndarray, roi, baseline: float, delta: float = DELTA) -> float:
    """Phần điểm ảnh trong `roi` = (x, y, rộng, cao) sáng ≥ baseline + delta (ảnh xám hay BGR)."""
    x, y, w, h = (int(v) for v in roi)
    crop = image[y:y + h, x:x + w]
    if crop.ndim == 3:
        crop = crop.mean(axis=2)
    return float(np.mean(crop >= baseline + delta)) if crop.size else 0.0


class FlashDetector:
    """Theo dõi từng khung (`update`) rồi trả các khởi đầu nháy hợp lệ (`onsets`)."""

    def __init__(self, roi, *, delta: float = DELTA, min_fraction: float = MIN_FRACTION, baseline_s: float = BASELINE_S,
                 init_frames: int = INIT_FRAMES):
        self.roi = tuple(int(v) for v in roi)
        self.delta, self.min_fraction, self.baseline_s, self.init_frames = delta, min_fraction, baseline_s, init_frames
        self.samples: list[tuple[int, float, float]] = []      # (khung, t, phần sáng)
        self._init: list[float] = []
        self._history: deque = deque()
        self.baseline: float | None = None

    def update(self, index: int, t: float, image: np.ndarray) -> float:
        x, y, w, h = self.roi
        crop = image[y:y + h, x:x + w]
        if crop.ndim == 3:
            crop = crop.mean(axis=2)
        level = float(np.median(crop)) if crop.size else 0.0
        if len(self._init) < self.init_frames:
            self._init.append(level)
            self.baseline = float(statistics.median(self._init))
        elif self._history:
            self.baseline = float(statistics.median(v for _, v in self._history))
        frac = roi_bright_fraction(image, self.roi, self.baseline, self.delta)
        if frac < self.min_fraction:
            self._history.append((t, level))
            while self._history and self._history[0][0] < t - self.baseline_s:
                self._history.popleft()
        self.samples.append((int(index), float(t), frac))
        return frac

    def onsets(self, *, min_duration_s: float = MIN_DURATION_S, max_duration_s: float = MAX_DURATION_S,
               min_gap_s: float = MIN_GAP_S) -> list[FlashOnset]:
        out: list[FlashOnset] = []
        runs, start = [], None
        for k, (_, _, frac) in enumerate(self.samples):
            lit = frac >= self.min_fraction
            if lit and start is None:
                start = k
            elif not lit and start is not None:
                runs.append((start, k))
                start = None
        if start is not None:
            runs.append((start, len(self.samples)))
        for a, b in runs:
            if a == 0:
                continue                                  # đang sáng từ khung đầu: không biết khởi đầu
            t_on = self.samples[a][1]
            t_off = self.samples[b][1] if b < len(self.samples) else self.samples[-1][1]
            duration = t_off - t_on
            if not min_duration_s <= duration <= max_duration_s:
                continue
            if out and t_on - out[-1].t < min_gap_s:
                continue
            out.append(FlashOnset(self.samples[a][0], t_on, duration, max(s[2] for s in self.samples[a:b])))
        return out


def detect_flashes(samples, roi, *, min_fraction: float = MIN_FRACTION, delta: float = DELTA,
                   min_duration_s: float = MIN_DURATION_S, max_duration_s: float = MAX_DURATION_S,
                   min_gap_s: float = MIN_GAP_S) -> list[FlashOnset]:
    """`samples`: (khung, t, ảnh) theo thứ tự thời gian → các khởi đầu nháy."""
    det = FlashDetector(roi, delta=delta, min_fraction=min_fraction)
    for index, t, image in samples:
        det.update(index, t, image)
    return det.onsets(min_duration_s=min_duration_s, max_duration_s=max_duration_s, min_gap_s=min_gap_s)


def _marks(marks) -> list[tuple[int, float]]:
    out = []
    for m in marks:
        if m.get("kind", "SYNC_MARK") != "SYNC_MARK" or m.get("n") in ("", None) or m.get("t_perf") in ("", None):
            continue
        out.append((int(m["n"]), float(m["t_perf"])))
    return sorted(out, key=lambda x: x[1])


def match_flashes(onsets: list[FlashOnset], marks, *, clock: str, max_latency_s: float = MAX_LATENCY_S,
                  tol_s: float = MATCH_TOL_S, first_mark: int | None = None) -> list[SyncPair]:
    """Cặp đồng bộ `mark` (t_ref = thời điểm khung đầu sáng, value = số dấu). Mơ hồ → OverheadError."""
    rows = _marks(marks)
    if not onsets or not rows:
        return []
    by_n = dict(rows)
    pairs: list[SyncPair] = []
    if clock == "perf_counter":
        used: set[int] = set()
        for o in onsets:
            hits = [n for n, t in rows if o.t - max_latency_s <= t <= o.t]
            if len(hits) > 1:
                raise OverheadError(f"lần nháy ở khung {o.index} (t {o.t:.3f}) khớp nhiều dấu {hits}: không ghép được")
            if not hits:
                continue
            if hits[0] in used:
                raise OverheadError(f"dấu {hits[0]} khớp hai lần nháy: không ghép được")
            used.add(hits[0])
            pairs.append(SyncPair(o.t, float(hits[0]), "mark", f"nháy khung {o.index}, trễ {o.t - by_n[hits[0]]:.3f} s"))
        return pairs
    if first_mark is not None:
        if first_mark not in by_n:
            raise OverheadError(f"--first-mark {first_mark}: tệp dấu không có dấu số đó")
        offsets = [onsets[0].t - by_n[first_mark]]
    elif len(onsets) == 1:
        raise OverheadError("chỉ thấy một lần nháy trong video: cần --first-mark n (số dấu của lần nháy đó)")
    else:
        offsets = [o.t - t for o in onsets for _, t in rows]

    def matches(c: float) -> list[tuple[FlashOnset, int]]:
        out, used = [], set()
        for o in onsets:
            best = min(((abs(o.t - (t + c)), n) for n, t in rows if n not in used), default=None)
            if best is not None and best[0] <= tol_s:
                out.append((o, best[1]))
                used.add(best[1])
        return out

    scored = [(len(matches(c)), c) for c in offsets]
    top = max(s for s, _ in scored)
    winners = sorted(c for s, c in scored if s == top)
    if first_mark is None and (top < 2 or winners[-1] - winners[0] > 2 * tol_s):
        raise OverheadError(f"không ghép được lần nháy với dấu: {top} lần trùng nhiều nhất, "
                            + ("nhiều độ lệch cùng tốt" if top >= 2 else "cần ≥ 2") + "; thêm --first-mark n")
    c = statistics.median(winners)
    for o, n in matches(c):
        pairs.append(SyncPair(o.t, float(n), "mark", f"nháy khung {o.index}, độ lệch video − perf {c:.3f} s"))
    return pairs
