"""Độ lặp lại khoảng cách của LiDAR trên cảnh tĩnh, tính offline từ bản ghi `.npz` (thêm tối 24/09/2026).

    .venv\\Scripts\\python.exe -X utf8 -m autopark.lidar.repeatability runs/lidar_bench/20260922/p07_nen_phong.npz runs/lidar_bench/20260924_kiem/k01_kiem_suc_khoe.npz --out runs/lidar_bench/do_lap_lai

Mỗi bản ghi cho `<tên>.repeatability.json` và `<tên>.repeatability.png` trong `--out`; thêm
`repeatability_summary.json` gộp mọi bản ghi của lệnh (kèm lệnh, tham số, hash mã của tệp này). Không mở thiết bị nào.
Hai bản ghi khác thư mục mà trùng tên tệp (vd. `lidar/part_0000.npz` của hai phiên bàn thử) thì tên tệp ra được thêm
dần tên thư mục cha, vd. `o03_20260924__lidar__part_0000.repeatability.json`; mỗi mục của tệp gộp ghi đường dẫn bản ghi
(`path`) và tên hai tệp ra (`outputs`). Cùng một bản ghi nêu hai lần thì báo lỗi dòng lệnh. (Sửa sau rà soát, muộn
tối 24/09/2026.)

Bộ lọc chung: chỉ tia CÓ phản hồi (NaN = không phản hồi, bị bỏ, không tính là 0); khoảng cách trong
[`range_min_m`, `range_max_m`] (mặc định 0,2–4 m như phép tính tạm ngày 24/09); chất lượng ≥ `min_quality` (mặc định 0
= không lọc); bỏ `skip_s` giây đầu tính từ vòng đầu CỦA BẢN GHI (mặc định 3 s, như `bench analyze --skip`: mô-tơ C1
còn tăng tốc ở các vòng đầu, GIAI_DOAN_1_LIDAR.md mục 3b).

Hai phép tính:

1. Theo tia, giữa hai vòng liên tiếp (tái lập phép tính tạm ngày 24/09 chưa từng lưu): mỗi tia của vòng i ghép với tia
   gần góc nhất của vòng i−1 (xét cả vòng qua ±180°); chỉ nhận cặp lệch góc < `tol` và cả hai tia qua bộ lọc; thống
   kê |Δr| qua mọi cặp (trung vị, p75, p90, p95, trung bình). Mặc định hai dung sai 0,1° và 0,2°.
2. Theo ô góc: chia 360° thành ô `bin_deg` (mặc định 0,5°) và gom mọi tia qua bộ lọc của các vòng đã chọn vào ô chứa
   góc của nó. Góc tia xê dịch giữa các vòng (bước ≈ 0,70°, điểm bắt đầu đổi mỗi vòng), nên trên mặt nghiêng khoảng
   cách đổi theo góc ngay trong một ô: khử bằng hồi quy tuyến tính r theo góc trong ô, rồi lấy độ lệch chuẩn phần dư
   (`std_detrended`) và 1,4826 × MAD phần dư (`mad_sigma`, bền với mép vật lúc có lúc không). Độ lệch chuẩn thô
   (`std_raw`) được giữ để so. Ô chỉ được tính khi có ≥ `min_bin_samples` mẫu và ≥ `min_bin_return_fraction` số tia
   rơi vào ô qua bộ lọc. Tóm tắt qua các ô bằng trung vị, p75, p90 để vài ô ở mép vật không kéo cả số.

Đây là độ LẶP LẠI giữa các vòng trên cùng một cảnh, KHÔNG phải sai số so với thước (chưa đo, GIAI_DOAN_1_LIDAR.md
mục 6). C1 gửi khoảng cách theo bước 1/4 mm (`distance_q2`), nên phân vị của |Δr| đi theo bậc 0,25 mm
(`range_step_mm` trong JSON cho biết bản ghi có đúng bước đó không).
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import sys
import unicodedata

import cv2
import numpy as np

from autopark.perception.paths import atomic_write_json, utc_now

from .recording import Recording, git_commit, read_recording

MAD_TO_SIGMA = 1.4826          # 1 / Φ⁻¹(0,75): MAD của phân bố chuẩn → độ lệch chuẩn
RANGE_STEP_MM = 0.25           # bước khoảng cách của node Standard (distance_q2 / 4 mm)


@dataclass(frozen=True)
class RepeatabilityConfig:
    range_min_m: float = 0.2
    range_max_m: float = 4.0
    skip_s: float = 3.0
    tolerances_deg: tuple[float, ...] = (0.1, 0.2)
    bin_deg: float = 0.5
    min_quality: int = 0
    min_bin_samples: int = 10
    min_bin_return_fraction: float = 0.5

    def __post_init__(self):
        if not (0.0 <= self.range_min_m < self.range_max_m):
            raise ValueError("need 0 <= range_min_m < range_max_m")
        if self.skip_s < 0:
            raise ValueError("skip_s must be >= 0")
        if not self.tolerances_deg or any(not (0.0 < tol < 180.0) for tol in self.tolerances_deg):
            raise ValueError("each tolerance must be in (0, 180) degrees")
        if not (0.0 < self.bin_deg <= 45.0) or abs(360.0 / self.bin_deg - round(360.0 / self.bin_deg)) > 1e-9:
            raise ValueError("bin_deg must divide 360 and be in (0, 45]")
        if self.min_bin_samples < 3:
            raise ValueError("min_bin_samples must be >= 3 (a line fit needs a residual)")


def selected_revolutions(recording: Recording, skip_s: float) -> np.ndarray:
    """Indices of the revolutions at or after `skip_s` seconds from the recording's first revolution."""
    if len(recording) == 0:
        return np.zeros(0, np.int64)
    return np.flatnonzero(recording.t >= recording.t[0] + skip_s - 1e-9)


def _usable(recording: Recording, index: int, config: RepeatabilityConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Angles (rad, wrapped to [0, 2π)), ranges (m) and the filter mask of one revolution."""
    angles, ranges, quality = recording.beams(index)
    angles = np.mod(angles.astype(np.float64), 2.0 * math.pi)
    ranges = ranges.astype(np.float64)
    finite = np.isfinite(ranges)
    ok = finite & (quality.astype(np.int64) >= config.min_quality)
    ok[finite] &= (ranges[finite] >= config.range_min_m) & (ranges[finite] <= config.range_max_m)
    return angles, ranges, ok


def nearest_by_angle(reference: np.ndarray, query: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For each query angle (rad) the index of the reference beam nearest in angle, going round ±180°, and the
    absolute angular offset (rad). `reference` must not be empty."""
    reference = np.mod(np.asarray(reference, np.float64), 2.0 * math.pi)
    query = np.mod(np.asarray(query, np.float64), 2.0 * math.pi)
    order = np.argsort(reference, kind="stable")
    ring = reference[order]
    extended = np.concatenate([ring[-1:] - 2.0 * math.pi, ring, ring[:1] + 2.0 * math.pi])
    index = np.concatenate([order[-1:], order, order[:1]])
    right = np.clip(np.searchsorted(extended, query), 1, len(extended) - 1)
    left = right - 1
    take_left = (query - extended[left]) <= (extended[right] - query)
    chosen = np.where(take_left, left, right)
    return index[chosen], np.abs(query - extended[chosen])


def consecutive_differences(recording: Recording, indices: np.ndarray, tolerance_deg: float,
                            config: RepeatabilityConfig) -> np.ndarray:
    """Signed range differences (m) of beam pairs from consecutive selected revolutions (i and i−1 both selected)."""
    tolerance = math.radians(tolerance_deg)
    selected = set(int(i) for i in indices)
    out: list[np.ndarray] = []
    previous = None
    for index in sorted(selected):
        current = _usable(recording, index, config)
        if previous is not None and previous[0] == index - 1:
            _, (p_angles, p_ranges, p_ok) = previous
            angles, ranges, ok = current
            if len(p_angles) and len(angles):
                match, offset = nearest_by_angle(p_angles, angles)
                pair = ok & p_ok[match] & (offset < tolerance)
                out.append(ranges[pair] - p_ranges[match][pair])
        previous = (index, current)
    return np.concatenate(out) if out else np.zeros(0, np.float64)


@dataclass
class AngleBins:
    centre_deg: np.ndarray          # project convention, (−180, 180]
    samples: np.ndarray             # beams in the bin that passed the filter
    beams: np.ndarray               # all beams whose angle fell in the bin (incl. no return / out of range)
    used: np.ndarray                # bool: enough samples and enough returns
    mean_m: np.ndarray
    std_raw_m: np.ndarray
    std_detrended_m: np.ndarray
    mad_sigma_m: np.ndarray


def angle_bin_statistics(recording: Recording, indices: np.ndarray, config: RepeatabilityConfig) -> AngleBins:
    count = int(round(360.0 / config.bin_deg))
    width = math.radians(config.bin_deg)
    all_bins, keep_bins, keep_angles, keep_ranges = [], [], [], []
    for index in indices:
        angles, ranges, ok = _usable(recording, int(index), config)
        bins = np.minimum((angles // width).astype(np.int64), count - 1)
        all_bins.append(bins)
        keep_bins.append(bins[ok])
        keep_angles.append(angles[ok])
        keep_ranges.append(ranges[ok])
    cat = (lambda parts, dtype: np.concatenate(parts) if parts else np.zeros(0, dtype))
    all_bins_a, bins_a = cat(all_bins, np.int64), cat(keep_bins, np.int64)
    angles_a, ranges_a = cat(keep_angles, np.float64), cat(keep_ranges, np.float64)
    beams = np.bincount(all_bins_a, minlength=count)
    samples = np.bincount(bins_a, minlength=count)
    nan = np.full(count, np.nan)
    mean, std_raw, std_detrended, mad_sigma = nan.copy(), nan.copy(), nan.copy(), nan.copy()
    used = (samples >= config.min_bin_samples) & (samples >= config.min_bin_return_fraction * np.maximum(beams, 1))
    order = np.argsort(bins_a, kind="stable")
    bins_sorted, angles_sorted, ranges_sorted = bins_a[order], angles_a[order], ranges_a[order]
    starts = np.searchsorted(bins_sorted, np.arange(count + 1))
    for b in np.flatnonzero(used):
        y = ranges_sorted[starts[b]:starts[b + 1]]
        x = angles_sorted[starts[b]:starts[b + 1]] - (b + 0.5) * width
        mean[b] = y.mean()
        std_raw[b] = y.std(ddof=1)
        design = np.stack([np.ones_like(x), x], axis=1)
        coef, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)   # rank 1 when every beam hit the same angle
        residual = y - design @ coef
        std_detrended[b] = math.sqrt(float((residual ** 2).sum()) / (len(y) - rank))
        mad_sigma[b] = MAD_TO_SIGMA * float(np.median(np.abs(residual - np.median(residual))))
    centre = np.degrees((np.arange(count) + 0.5) * width)
    centre = np.where(centre > 180.0, centre - 360.0, centre)
    return AngleBins(centre, samples, beams, used, mean, std_raw, std_detrended, mad_sigma)


def robust_summary(values_mm: np.ndarray) -> dict:
    """Median/p75/p90/p95/mean/max of finite values in mm; None everywhere when there is nothing to summarise."""
    values = np.asarray(values_mm, np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return {"count": 0, "median": None, "p75": None, "p90": None, "p95": None, "mean": None, "max": None}
    p = np.percentile(values, [50, 75, 90, 95])
    # 4 chữ số sau dấu phẩy (0,1 µm): bản ghi lưu khoảng cách dạng float32 (m), phần sau đó chỉ là nhiễu làm tròn
    r = (lambda v: round(float(v), 4))
    return {"count": int(len(values)), "median": r(p[0]), "p75": r(p[1]), "p90": r(p[2]), "p95": r(p[3]),
            "mean": r(values.mean()), "max": r(values.max())}


def observed_range_step_mm(recording: Recording) -> float | None:
    """0.25 when every finite range is a whole number of quarter millimetres (the C1 Standard node), else None."""
    ranges = recording.ranges[np.isfinite(recording.ranges)].astype(np.float64) * 1000.0 / RANGE_STEP_MM
    if not len(ranges):
        return None
    return RANGE_STEP_MM if float(np.abs(ranges - np.round(ranges)).max()) < 0.02 else None


def analyze_repeatability(recording: Recording, config: RepeatabilityConfig = RepeatabilityConfig()
                          ) -> tuple[dict, AngleBins, np.ndarray]:
    """JSON-ready result, the per-bin statistics and the |Δr| (m) of the first tolerance (for the picture)."""
    indices = selected_revolutions(recording, config.skip_s)
    consecutive, first_abs = [], np.zeros(0)
    for tolerance in config.tolerances_deg:
        diffs = consecutive_differences(recording, indices, tolerance, config)
        if not consecutive:
            first_abs = np.abs(diffs)
        consecutive.append({"tolerance_deg": tolerance, "pairs": int(len(diffs)),
                            "abs_diff_mm": robust_summary(np.abs(diffs) * 1000.0),
                            "signed_mean_mm": round(float(diffs.mean() * 1000.0), 4) if len(diffs) else None})
    bins = angle_bin_statistics(recording, indices, config)
    used = bins.used
    t0 = float(recording.t[0]) if len(recording) else 0.0
    meta = recording.meta
    result = {
        "file": recording.path.name,
        "analyzed_utc": utc_now(),
        "recording": {"scans": int(len(recording)), "started_utc": meta.get("started_utc"),
                      "recorded_with_commit": meta.get("git_commit"), "warmup_s_in_meta": meta.get("warmup_s"),
                      "first_revolution_s_after_start": round(t0, 4) if len(recording) else None,
                      "duration_s": round(float(recording.t[-1] - t0), 4) if len(recording) > 1 else 0.0},
        "config": asdict(config),
        "revolutions_used": int(len(indices)),
        "used_from_s": round(float(recording.t[indices[0]] - t0), 4) if len(indices) else None,
        "used_to_s": round(float(recording.t[indices[-1]] - t0), 4) if len(indices) else None,
        "beams_per_revolution_used": None if not len(indices) else
        {"min": int(recording.n_beams[indices].min()), "median": float(np.median(recording.n_beams[indices])),
         "max": int(recording.n_beams[indices].max())},
        "range_step_mm": observed_range_step_mm(recording),
        "consecutive": consecutive,
        "angle_bins": {"bin_deg": config.bin_deg, "bins_total": int(len(used)), "bins_used": int(used.sum()),
                       "samples_in_used_bins": int(bins.samples[used].sum()),
                       "std_raw_mm": robust_summary(bins.std_raw_m[used] * 1000.0),
                       "std_detrended_mm": robust_summary(bins.std_detrended_m[used] * 1000.0),
                       "mad_sigma_mm": robust_summary(bins.mad_sigma_m[used] * 1000.0)},
        "note": "độ lặp lại giữa các vòng trên cảnh tĩnh, không phải sai số so với thước",
    }
    return result, bins, first_abs


# ---- hình ------------------------------------------------------------------------------------------------------------
def _ascii(text: str) -> str:
    """cv2.putText only draws ASCII: fold Vietnamese diacritics (đ → d)."""
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def render_repeatability(result: dict, bins: AngleBins, abs_diffs_m: np.ndarray, *, y_max_mm: float = 10.0,
                         width: int = 1100, height: int = 520) -> np.ndarray:
    """Left: per-bin detrended std against angle (clipped at `y_max_mm`, clipped bins drawn as triangles at the top).
    Right: histogram of |Δr| of consecutive revolutions at the first tolerance, 0.25 mm bins up to `y_max_mm`."""
    image = np.full((height, width, 3), 255, np.uint8)
    font, grey, dark = cv2.FONT_HERSHEY_SIMPLEX, (170, 170, 170), (40, 40, 40)
    blue, red, orange = (180, 90, 20), (40, 40, 200), (0, 140, 255)
    top, bottom = 70, height - 45
    lx0, lx1, rx0, rx1 = 60, 640, 700, width - 20

    def ly(v_mm: float) -> int:
        return int(round(bottom - (bottom - top) * min(v_mm, y_max_mm) / y_max_mm))

    first = result["consecutive"][0] if result["consecutive"] else None
    stats = result["angle_bins"]["std_detrended_mm"]
    head = [f"{result['file']}: {result['revolutions_used']} vong (bo {result['config']['skip_s']:g} s dau), "
            f"phan hoi {result['config']['range_min_m']:g}-{result['config']['range_max_m']:g} m, "
            f"do lap lai giua cac vong - KHONG phai sai so so voi thuoc"]
    if first and first["abs_diff_mm"]["median"] is not None:
        head.append(f"|dr| vong lien tiep (lech goc < {first['tolerance_deg']:g} deg, {first['pairs']} cap): "
                    f"trung vi {first['abs_diff_mm']['median']:.2f} mm, p90 {first['abs_diff_mm']['p90']:.2f} mm")
    if stats["median"] is not None:
        head[-1] += (f" | std theo o {result['angle_bins']['bin_deg']:g} deg (khu doc): "
                     f"trung vi {stats['median']:.2f} mm, p90 {stats['p90']:.2f} mm, "
                     f"{result['angle_bins']['bins_used']} o")
    for row, line in enumerate(head):
        cv2.putText(image, _ascii(line), (10, 20 + 20 * row), font, 0.45, dark, 1, cv2.LINE_AA)

    # left panel: std per angle bin
    for v in range(0, int(y_max_mm) + 1, 2):
        cv2.line(image, (lx0, ly(v)), (lx1, ly(v)), (230, 230, 230), 1)
        cv2.putText(image, f"{v}", (lx0 - 25, ly(v) + 4), font, 0.4, dark, 1, cv2.LINE_AA)
    for a in range(-180, 181, 45):
        x = int(round(lx0 + (lx1 - lx0) * (a + 180) / 360))
        cv2.line(image, (x, top), (x, bottom), (230, 230, 230), 1)
        cv2.putText(image, f"{a}", (x - 12, bottom + 16), font, 0.4, dark, 1, cv2.LINE_AA)
    cv2.rectangle(image, (lx0, top), (lx1, bottom), grey, 1)
    for centre, value, used in zip(bins.centre_deg, bins.std_detrended_m * 1000.0, bins.used):
        if not used:
            continue
        x = int(round(lx0 + (lx1 - lx0) * (centre + 180) / 360))
        if value > y_max_mm:
            cv2.drawMarker(image, (x, top + 4), red, cv2.MARKER_TRIANGLE_UP, 7, 1)
        else:
            cv2.circle(image, (x, ly(value)), 2, blue, -1)
    if stats["median"] is not None:
        cv2.line(image, (lx0, ly(stats["median"])), (lx1, ly(stats["median"])), orange, 1)
    cv2.putText(image, _ascii("std khoang cach theo o goc (mm), da khu doc; tam giac do = vuot khung"),
                (lx0, top - 8), font, 0.42, dark, 1, cv2.LINE_AA)
    cv2.putText(image, _ascii("goc (do, quy uoc du an: 0 = truoc, duong = trai)"), (lx0 + 120, bottom + 34), font,
                0.42, dark, 1, cv2.LINE_AA)

    # right panel: histogram of |Δr|
    edges = np.arange(0.0, y_max_mm + RANGE_STEP_MM, RANGE_STEP_MM)
    values_mm = np.asarray(abs_diffs_m, np.float64) * 1000.0
    # half-step offset so the quarter-millimetre values fall inside a bin, not on its edge
    counts = (np.histogram(values_mm, bins=edges - RANGE_STEP_MM / 2)[0] if len(values_mm)
              else np.zeros(len(edges) - 1, np.int64))
    over = int((values_mm > edges[-1] - RANGE_STEP_MM / 2).sum()) if len(values_mm) else 0
    cv2.rectangle(image, (rx0, top), (rx1, bottom), grey, 1)
    peak = max(int(counts.max()) if len(counts) else 0, 1)
    bar = (rx1 - rx0) / len(counts)
    for k, c in enumerate(counts):
        x0 = int(round(rx0 + k * bar))
        x1 = max(x0 + 1, int(round(rx0 + (k + 1) * bar)) - 1)
        cv2.rectangle(image, (x0, int(round(bottom - (bottom - top) * c / peak))), (x1, bottom), blue, -1)
    for v in range(0, int(y_max_mm) + 1, 2):
        x = int(round(rx0 + (rx1 - rx0) * v / y_max_mm))
        cv2.putText(image, f"{v}", (x - 5, bottom + 16), font, 0.4, dark, 1, cv2.LINE_AA)
    if first:
        cv2.putText(image, _ascii(f"|dr| hai vong lien tiep (mm), lech goc < {first['tolerance_deg']:g} deg"),
                    (rx0, top - 8), font, 0.42, dark, 1, cv2.LINE_AA)
    cv2.putText(image, _ascii(f"cot cao nhat = {peak} cap; > {y_max_mm:g} mm: {over} cap (khong ve)"),
                (rx0, bottom + 34), font, 0.42, dark, 1, cv2.LINE_AA)
    return image


def write_png(path: Path, image: np.ndarray) -> Path:
    """cv2.imwrite fails on non-ASCII Windows paths: encode in memory and write the bytes."""
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"could not encode {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.tobytes())
    return path


def output_stems(paths) -> list[str]:
    """Tên tệp ra (không đuôi) cho từng bản ghi, không trùng nhau: tên bản ghi; nếu hai bản ghi khác thư mục trùng tên
    thì thêm dần tên thư mục cha, nối bằng `__` (vd. `o03_20260924__lidar__part_0000`). Cùng một tệp nêu hai lần (kể cả
    `a` và `a.npz`) → ValueError."""
    resolved = [Path(p).with_suffix(".npz").resolve() for p in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("một bản ghi được nêu hai lần")
    names = [p.stem for p in resolved]
    depth = 1
    deepest = max((len(p.parent.parts) for p in resolved), default=0)
    while len(set(names)) != len(names) and depth <= deepest:
        names = ["__".join([*p.parent.parts[-depth:], p.stem]).replace(":", "").replace("\\", "").replace("/", "")
                 if names.count(n) > 1 else n for p, n in zip(resolved, names)]
        depth += 1
    if len(set(names)) != len(names):             # dự phòng, vd. hai đường dẫn chỉ khác ổ đĩa
        names = [f"{i:02d}_{p.stem}" for i, p in enumerate(resolved)]
    return names


def code_sha256(path: Path | None = None) -> str:
    """sha256 của mã nguồn (mặc định chính tệp này) sau khi đổi CRLF → LF.

    Git for Windows mặc định `core.autocrlf=true`: cùng một blob có thể ra tệp LF hoặc CRLF tùy lần checkout. Chuẩn hóa
    về LF để hash không đổi giữa các máy và trùng `git show <commit>:autopark/autopark/lidar/repeatability.py` rồi
    sha256 (blob trong git lưu LF)."""
    data = Path(__file__ if path is None else path).read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("recordings", nargs="+", type=Path, help=".npz recordings of a static scene")
    parser.add_argument("--out", type=Path, required=True, help="output directory (JSON + PNG)")
    parser.add_argument("--skip", type=float, default=RepeatabilityConfig.skip_s,
                        help="ignore the first seconds of each recording (motor spin-up); 0 keeps everything")
    parser.add_argument("--range-min", type=float, default=RepeatabilityConfig.range_min_m)
    parser.add_argument("--range-max", type=float, default=RepeatabilityConfig.range_max_m)
    parser.add_argument("--tol", type=float, action="append", default=None,
                        help="angle tolerance (deg) for pairing beams of consecutive revolutions; repeatable")
    parser.add_argument("--bin", type=float, default=RepeatabilityConfig.bin_deg, help="angle bin width (deg)")
    parser.add_argument("--min-quality", type=int, default=RepeatabilityConfig.min_quality)
    parser.add_argument("--min-bin-samples", type=int, default=RepeatabilityConfig.min_bin_samples)
    args = parser.parse_args(argv)
    try:
        config = RepeatabilityConfig(range_min_m=args.range_min, range_max_m=args.range_max, skip_s=args.skip,
                                     tolerances_deg=tuple(args.tol) if args.tol else RepeatabilityConfig.tolerances_deg,
                                     bin_deg=args.bin, min_quality=args.min_quality,
                                     min_bin_samples=args.min_bin_samples)
    except ValueError as exc:
        parser.error(str(exc))
    missing = [str(path) for path in args.recordings if not path.with_suffix(".npz").exists()]
    if missing:
        parser.error("không có bản ghi: " + ", ".join(missing))
    try:
        stems = output_stems(args.recordings)
    except ValueError as exc:
        parser.error(f"{exc}: " + ", ".join(str(path) for path in args.recordings))
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for path, stem in zip(args.recordings, stems):
        recording = read_recording(path)
        result, bins, first_abs = analyze_repeatability(recording, config)
        # `file` chỉ là tên tệp; `path` (như đã gõ) và `outputs` phân biệt hai bản ghi cùng tên ở hai thư mục
        result["path"] = recording.path.as_posix()
        result["outputs"] = {"json": f"{stem}.repeatability.json", "png": f"{stem}.repeatability.png"}
        atomic_write_json(out / result["outputs"]["json"], result)
        write_png(out / result["outputs"]["png"], render_repeatability(result, bins, first_abs))
        results.append(result)
        line = [f"{recording.path.as_posix()}: {result['revolutions_used']} vòng"]
        for row in result["consecutive"]:
            s = row["abs_diff_mm"]
            line.append(f"|Δr| lệch góc < {row['tolerance_deg']:g}°: " + (
                "không có cặp" if s["median"] is None else
                f"trung vị {s['median']:.2f} mm, p90 {s['p90']:.2f} mm ({row['pairs']} cặp)"))
        s = result["angle_bins"]["std_detrended_mm"]
        line.append(f"std theo ô {config.bin_deg:g}° (khử dốc): " + (
            "không có ô" if s["median"] is None else
            f"trung vị {s['median']:.2f} mm, p90 {s['p90']:.2f} mm ({result['angle_bins']['bins_used']} ô)"))
        print("; ".join(line))
    # git_commit = HEAD của repo lúc chạy; tệp này có thể chưa được commit, nên kèm hash của chính nó (sau CRLF → LF)
    summary = {"tool": "autopark.lidar.repeatability", "analyzed_utc": utc_now(), "git_commit": git_commit(),
               "code_sha256": code_sha256(),
               "code_sha256_of": "autopark/autopark/lidar/repeatability.py sau khi đổi CRLF -> LF (như blob trong git)",
               "command": "python -X utf8 -m autopark.lidar.repeatability " + " ".join(
                   str(a) for a in (sys.argv[1:] if argv is None else argv)),
               "config": asdict(config), "recordings": results,
               "note": "độ lặp lại giữa các vòng trên cảnh tĩnh, không phải sai số so với thước; "
                       "offline, không mở thiết bị"}
    atomic_write_json(out / "repeatability_summary.json", summary)
    print(f"đã ghi {out / 'repeatability_summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
