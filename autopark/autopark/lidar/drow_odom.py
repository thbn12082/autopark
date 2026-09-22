"""Odometry DROW v2 (`.odom2`): mỗi dòng `seq, t, x, y, yaw` theo loader của tác giả (`load_odom`: dtype
seq u4, t f4, xya f4×3). Đơn vị suy từ dữ liệu và cách dùng trong `cutout()` của tác giả: x, y mét, yaw radian,
yaw dương cùng chiều với góc quét (ngược chiều kim đồng hồ). Không có tài liệu chính thức về hệ quy chiếu;
kiểm tra bằng độ sắc nét của bản đồ ghép (`occupancy.py --odom`) chứ không coi là đã xác minh.

Ghép với scan THEO CHỈ SỐ DÒNG, không theo seq: trên `val/run_2015-11-25-10-34-20-a` file scan có seq
9796–11030 còn file odom có seq 14767–16628 (không giao nhau) nhưng cùng 1.235 dòng, và loader của tác giả
cũng chỉ số hóa `odoms[iseq][iscan]` theo vị trí. Seq trong `.odom2` có thể lặp (23 dòng trùng trong file
trên), không giảm.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .drow import DrowRecording


@dataclass(frozen=True)
class DrowOdometry:
    path: Path
    seq: np.ndarray     # (N,) int
    t: np.ndarray       # (N,) float seconds
    xya: np.ndarray     # (N, 3) x, y, yaw

    def __len__(self) -> int:
        return len(self.seq)


def read_drow_odom(path) -> DrowOdometry:
    path = Path(path)
    data = np.loadtxt(path, delimiter=",", dtype=np.float64, ndmin=2)
    if data.shape[1] != 5:
        raise ValueError(f"{path.name}: expected 5 columns (seq, t, x, y, yaw), got {data.shape[1]}")
    if not np.isfinite(data).all():
        raise ValueError(f"{path.name}: non-finite values")
    seq = data[:, 0].astype(np.int64)
    if (seq != data[:, 0]).any() or (np.diff(seq) < 0).any():
        raise ValueError(f"{path.name}: sequence ids must be non-decreasing integers")
    if (np.diff(data[:, 1]) < 0).any():
        raise ValueError(f"{path.name}: timestamps decrease")
    return DrowOdometry(path, seq, data[:, 1], data[:, 2:5])


def scan_poses(recording: DrowRecording, odom: DrowOdometry) -> np.ndarray:
    """(N, 3) pose per scan of `recording`, row i of the odometry belonging to scan i (same row count required)."""
    if len(odom) != len(recording):
        raise ValueError(f"{odom.path.name}: {len(odom)} odometry rows for {len(recording)} scans; "
                         "DROW pairs them by row, so the counts must match")
    return odom.xya.copy()
