"""Phát lại bản quét laser 2D từ DROW v2 (SICK S300) theo hợp đồng `LidarScan`.

Định dạng (đã kiểm tra trên dữ liệu, xem datasets/TAI_VA_KIEM_TRA.md): mỗi dòng CSV có 452 cột — cột 0 là
sequence ID (tăng 1 mỗi dòng trong một file), cột 1 là thời gian (giây, gốc tùy ý), 450 cột còn lại là
khoảng cách (m). Cảm biến quét 224,5° với bước 0,5°; loader v2 của tác giả đặt phi = 0 thẳng phía trước,
chỉ số 0 ứng với góc âm nhất. README gốc lại nói "giá trị đầu là bên trái"; hai tài liệu mâu thuẫn, ở đây
theo mã loader (chỉ số 0 = bên phải, góc dương ngược chiều kim đồng hồ, cùng quy ước yaw của dự án) và có
tham số `mirror` để đảo khi đối chiếu với thiết bị thật.

Giá trị 29,96 được tác giả ghi là N/A; 29,98 và 29,99 cũng xuất hiện hàng chục nghìn lần (giá trị canh gác của
thiết bị), 29,97 không bao giờ có, còn 29,90–29,95 có vài trăm lần trên val+test và có thể là phản hồi xa thật.
Đây chọn cắt bảo thủ: mọi giá trị >= NO_RETURN_MIN (29,9) thành NaN — vài trăm phản hồi xa bị bỏ theo hướng
an toàn; `summary()` đếm riêng chúng. NaN không phải bằng chứng vùng trống.

Nhãn `.wp/.wc/.wa` là dòng `seq,[[r, phi], ...]`: danh sách rỗng nghĩa là đã gán nhãn nhưng không có đối tượng;
thiếu seq nghĩa là chưa gán nhãn. Đây là laser trong nhà ở cấu hình khác RPLIDAR C1.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Iterator

import numpy as np

from autopark.domain.sensors import LidarScan, SourceStamp

N_BEAMS = 450
ANGLE_INCREMENT_DEG = 0.5
NO_RETURN_MIN = 29.9
RANGE_MIN = 0.05


def drow_angles(n_beams: int = N_BEAMS, increment_deg: float = ANGLE_INCREMENT_DEG, mirror: bool = False) -> np.ndarray:
    half = (n_beams - 1) / 2 * increment_deg
    angles = np.radians(np.linspace(-half, half, n_beams))
    return -angles if mirror else angles


@dataclass(frozen=True)
class DrowRecording:
    path: Path
    seq: np.ndarray        # (N,) int
    t: np.ndarray          # (N,) float seconds, recording clock
    ranges: np.ndarray     # (N, 450) float, NaN where no return
    far_returns_discarded: int = 0   # values in [NO_RETURN_MIN, 29.96): treated as no return, counted here

    def __len__(self) -> int:
        return len(self.seq)


def read_drow_csv(path) -> DrowRecording:
    path = Path(path)
    data = np.loadtxt(path, delimiter=",", dtype=np.float64, ndmin=2)
    if data.shape[1] != N_BEAMS + 2:
        raise ValueError(f"{path.name}: expected {N_BEAMS + 2} columns, got {data.shape[1]}")
    if not np.isfinite(data).all():
        raise ValueError(f"{path.name}: non-finite values")
    seq = data[:, 0].astype(np.int64)
    if (seq != data[:, 0]).any() or (np.diff(seq) <= 0).any():
        raise ValueError(f"{path.name}: sequence ids must be increasing integers")
    t = data[:, 1]
    if (np.diff(t) < 0).any():
        raise ValueError(f"{path.name}: timestamps decrease")
    ranges = data[:, 2:].copy()
    far_returns = int(((ranges >= NO_RETURN_MIN) & (ranges < 29.96)).sum())   # possibly real, discarded on purpose
    ranges[(ranges >= NO_RETURN_MIN) | (ranges < RANGE_MIN)] = np.nan
    return DrowRecording(path, seq, t, ranges, far_returns)


def read_drow_labels(path, mirror: bool = False) -> dict[int, list[tuple[float, float]]]:
    """`.wp/.wc/.wa` -> {seq: [(r, phi), ...]}; phi follows the same convention (and `mirror`) as the scan angles."""
    path = Path(path)
    labels: dict[int, list[tuple[float, float]]] = {}
    sign = -1.0 if mirror else 1.0
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        seq_text, _, payload = line.partition(",")
        try:
            seq = int(seq_text)
            detections = [(float(r), sign * float(phi)) for r, phi in json.loads(payload)]
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{path.name}:{number}: cannot parse label line ({exc})") from exc
        if seq in labels:
            raise ValueError(f"{path.name}:{number}: duplicate sequence id {seq}")
        labels[seq] = detections
    return labels


def to_lidar_scan(recording: DrowRecording, index: int, *, source_id: str, angles: np.ndarray,
                  time_offset: float = 0.0) -> LidarScan:
    ranges = recording.ranges[index]
    stamp = SourceStamp(source_id, float(recording.t[index] - recording.t[0] + time_offset), True, "lidar")
    return LidarScan(stamp, tuple(float(a) for a in angles),
                     tuple(float(r) if math.isfinite(r) else math.nan for r in ranges))


def valid_mask(scan: LidarScan) -> np.ndarray:
    return np.isfinite(np.asarray(scan.ranges_m, dtype=np.float64))


def scan_points(scan: LidarScan) -> np.ndarray:
    """(N, 2) points in the sensor frame (x forward, y left) for beams with a return."""
    angles = np.asarray(scan.angles_rad, dtype=np.float64)
    ranges = np.asarray(scan.ranges_m, dtype=np.float64)
    ok = np.isfinite(ranges)
    return np.column_stack([ranges[ok] * np.cos(angles[ok]), ranges[ok] * np.sin(angles[ok])])


class DrowReplaySource:
    """Iterates the scans of one recording as `LidarScan`, timestamps rebased so the first scan is at `t0`."""

    def __init__(self, csv_path, *, source_id: str = "drow_replay", t0: float = 0.0, mirror: bool = False):
        self.recording = read_drow_csv(csv_path)
        self.source_id = source_id
        self.angles = drow_angles(mirror=mirror)
        self.t0 = t0
        self.index = 0

    def __len__(self) -> int:
        return len(self.recording)

    def read(self) -> LidarScan | None:
        if self.index >= len(self.recording):
            return None
        scan = to_lidar_scan(self.recording, self.index, source_id=self.source_id, angles=self.angles,
                             time_offset=self.t0)
        self.index += 1
        return scan

    def __iter__(self) -> Iterator[LidarScan]:
        while (scan := self.read()) is not None:
            yield scan

    def summary(self) -> dict:
        r = self.recording.ranges
        dt = np.diff(self.recording.t)
        return {"file": self.recording.path.name, "scans": len(self.recording), "beams": r.shape[1],
                "duration_s": float(self.recording.t[-1] - self.recording.t[0]),
                "median_period_s": float(np.median(dt)) if len(dt) else None,
                "max_gap_s": float(dt.max()) if len(dt) else None,
                "no_return_fraction": float(np.isnan(r).mean()),
                "far_returns_discarded": self.recording.far_returns_discarded,
                "range_min_m": float(np.nanmin(r)) if np.isfinite(r).any() else None,
                "range_max_m": float(np.nanmax(r)) if np.isfinite(r).any() else None,
                "fov_deg": abs(float(math.degrees(self.angles[-1] - self.angles[0])))}
