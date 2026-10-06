"""Tham chiếu trên cao R1 (T4, docs/KICH_BAN_NGHIEM_THU.md mục 3): camera trên cao → tư thế tâm trục sau mỗi khung, ghi
đúng hợp đồng `evaluation/reference_pose.py` để công cụ chấm T5 (`score_run`) đọc. Thêm 02/10/2026.

Dùng (mỗi lệnh một dòng, chạy trong thư mục autopark; chỉ `video.overhead_record` và nút "Mở camera" của
`ui.overhead_app` mở camera, các lệnh dưới đây không bao giờ mở camera hay cổng COM):

    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.overhead_ref survey-template --size 3.0x2.0 --step 0.5 --check 8 --out docs\\evidence\\moc_sa_ban_<ngay>.csv
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.overhead_ref floor --intrinsics calibration\\cam_tren_cao_1280x720.json --survey docs\\evidence\\moc_sa_ban_<ngay>.csv --video runs\\tren_cao\\<ngay>\\san_trong.avi --out docs\\evidence\\nghiem_thu\\mat_san_<ngay>.json
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.overhead_ref track --video runs\\tren_cao\\<ngay>\\do1_l01.avi --floor docs\\evidence\\nghiem_thu\\mat_san_<ngay>.json --markers configs\\tham_chieu\\xe_gia_v1.json --tc1 docs\\evidence\\nghiem_thu\\tham_chieu_tren_cao_<ngay>.json --out runs\\nghiem_thu\\<ngay>\\do1_l01\\tu_the_tham_chieu.csv
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.overhead_ref tc1 --floor <mat_san.json> --markers configs\\tham_chieu\\xe_gia_v1.json --poses docs\\evidence\\tc1_<ngay>.csv --kind full --out docs\\evidence\\nghiem_thu\\tham_chieu_tren_cao_<ngay>.json
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.overhead_ref check <tệp bất kỳ của T4>
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.overhead_ref synthetic --out runs\\tren_cao\\tong_hop

Mã thoát: 0 xong; 1 xong nhưng chất lượng chưa đạt (khớp mặt sàn ok = false; camera dịch, < 80 % khung hợp lệ hay không
khung nào hợp lệ — khi đó chỉ ghi tệp chi tiết; TC-1 thiếu yêu cầu); 2 tham số sai hay bị từ chối, không ghi gì; 3 lỗi
bất ngờ (in traceback; tệp ghi qua tệp tạm nên không có tệp dở).

**Hệ tọa độ.** Hệ sa bàn (KICH_BAN mục 3.3): gốc ở một góc, x dọc cạnh dài, y sang TRÁI khi nhìn theo +x, z lên, góc
dương ngược chiều kim đồng hồ. Hệ xe: x trước, y trái, gốc = tâm trục sau trên sàn (`tam_truc_sau`). Camera: trục OpenCV,
X_c = R_cs·X_s + t_cs, tâm C = −R_csᵀ·t_cs, độ cao H = C_z. Ống kính: Kannala–Brandt của tệp nội tham T11
(`calibration/cam_tren_cao[_WxH].json`, `calib_app --index N --camera-name tren_cao`); tâm điểm ảnh ở số nguyên. Điểm
ảnh → mặt z = h: n = khử méo (cv2.fisheye.undistortPoints), d = R_csᵀ·[n, 1] (cần d_z < 0), P = C + (h − C_z)/d_z·d.
Marker in: trục x sang phải, y lên như lúc in; góc TL, TR, BR, BL = (−s/2, s/2), (s/2, s/2), (s/2, −s/2), (−s/2, −s/2);
nhìn từ trên xuống thấy marker không bị lật. Tâm marker sàn trên ảnh = giao hai đường chéo của 4 góc ĐÃ KHỬ MÉO (đúng
với phép chiếu phối cảnh), rồi méo lại; tâm marker xe = trung bình 4 góc đã chiếu lên mặt z = z_m. Mã (DICT_4X4_50,
KICH_BAN mục 3.2): mốc sàn 0–47, xe 48 = 'sau', 49 = 'truoc'.

**Khớp mặt sàn** (`fit_floor`): dò marker trên mọi khung sàn trống, trung vị từng trục; giải tư thế camera từ các mốc
kiểm soát (`extrinsics_calib.solve_pose`: PnP rồi Levenberg–Marquardt theo điểm ảnh), loại dần mốc lệch
> max(10 mm, 3 × trung vị) khi còn ≥ 8 mốc; báo sai số trên ĐIỂM KIỂM TRA riêng (không dùng để khớp), mốc thiếu (ngoài
khung hình, quá nhỏ, không dò được), chẩn đoán homography, xu hướng sai số theo bán kính (mô hình ống kính), điểm ngoại
suy, độ phân giải trên sàn. **Tư thế mỗi khung** (`solve_frame`): hai marker xe chiếu lên mặt z = z_m (bù thị sai, mục
3.6), kiểm cạnh marker (±10 %) và khoảng cách hai marker (±5 mm), hướng từ đường nối hai tâm. Góc ArUco (tinh chỉnh
đường viền) nằm lõm vào trong cạnh thật ≈ 0,5–0,8 px, nên cạnh đo được ngắn hơn ≈ 4–7 % ở ≈ 3,4–4,3 px mỗi ô module
(marker xe 80 mm, ảnh tổng hợp 02/10/2026); phép kiểm cạnh chịu được, còn tâm và hướng không bị ảnh hưởng (lệch đối
xứng). **Camera dịch**
(`FloorShiftMonitor`): trung vị độ lệch tâm các mốc sàn thấy được so với lúc khớp > 0,7 px trong 15 khung đo liên tiếp
thì từ khung đầu của chuỗi đó mọi dòng thành không hợp lệ.

**Đồng hồ** (mục 4.4 thiết kế T4): video của `video.overhead_record` (có `<tên>.frames.csv` + `<tên>.json`) dùng đồng
hồ `perf_counter` của chính laptop (stamp ngay sau `read()`), `sync_error_s` = độ trễ chụp ước lượng `--capture-latency-s`
(0,15 s, ĐỀ XUẤT, CHƯA ĐO) trừ khi có cặp đồng bộ; chép thiếu một trong hai tệp đó (hay `--frames-csv` mà thiếu JSON của
bộ ghi) thì bị từ chối. Video khác dùng đồng hồ `video` (stamp của tệp) và cần cặp `--sync` hay dấu nháy T14
(`--flash-roi`, `--sync-marks`), `sync_error_s` = p95 khoảng cách khung (± một khung, KICH_BAN mục 2.5; độ trễ hiển thị
CHƯA ĐO); tệp chỉ có số khung/s danh định — mọi tệp AVI (container không có thời điểm từng khung), hay tệp khác mà
vị trí khung không tăng ngặt — bị từ chối trừ khi `--allow-nominal-fps` (kèm ghi chú). `--sync-error`,
`--capture-latency-s` phải là số giây hữu hạn ≥ 0 (kiểm trước khi mở video; sửa 02/10/2026).

**Độ chính xác** chỉ chép từ biên bản TC-1 (`evaluation/overhead_tc1.py`) khi cùng tệp khớp mặt sàn (SHA-256), cùng bộ
dò, cùng cờ tổng hợp, đủ yêu cầu, cùng cấu hình marker (hoặc TC-1 rút gọn cùng cấu hình) và cùng ngày với video; không
thì null kèm ghi chú, T5 ghi "không kiểm được" (quy tắc 3). Kết quả TỔNG HỢP (`synthetic`) không bao giờ ghi vào
configs/, calibration/ hay docs/evidence/, luôn mang nhãn "TỔNG HỢP — KHÔNG PHẢI SỐ ĐO", T5 từ chối nó ở mức BT/XT.

Mọi ngưỡng ở `THRESHOLDS` là ĐỀ XUẤT – CHỜ CHỐT (người dùng giao quyết định 02/10/2026). **Tình trạng 02/10/2026:** chỉ
kiểm trên ảnh TỔNG HỢP (`evaluation/overhead_synth.py`, tests/test_overhead_*.py); CHƯA THỬ với camera thật — chưa chọn
camera trên cao (KICH_BAN mục 8), chưa làm TC-1.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field, fields
from datetime import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import sys
import traceback
from typing import Callable, Iterable, Iterator

import cv2
import numpy as np

from autopark.domain.types import Pose, wrap_angle
from autopark.evaluation.reference_pose import (ReferenceAccuracy, ReferenceMeta, ReferenceSample, SyncPair,
                                                sidecar_path, write_reference)
from autopark.lidar import recording as lidar_recording
from autopark.perception import extrinsics_calib as ec
from autopark.perception import fisheye_calib as fc
from autopark.perception.aruco_sheet import CAR_IDS, DICTIONARIES, dictionary_size, get_dictionary
from autopark.perception.paths import PROJECT, atomic_write_json, utc_now

TOOL = "autopark.evaluation.overhead_ref"
FLOOR_FORMAT = "autopark.overhead_floor/1"
MARKERS_FORMAT = "autopark.overhead_vehicle_markers/1"
RECORDING_FORMAT = "autopark.overhead_recording/1"
SYNTHETIC_LABEL = "TỔNG HỢP — KHÔNG PHẢI SỐ ĐO"
PROPOSED = "ĐỀ XUẤT – CHỜ CHỐT"
DELEGATED = "người dùng giao quyết định 02/10/2026"
UNTESTED = "CHƯA THỬ với camera thật"
POINT = "tam_truc_sau"
ROLES = ("kiem_soat", "kiem_tra")
CAR_ROLES = ("sau", "truoc")
DEFAULT_DICTIONARY = "DICT_4X4_50"
DEFAULT_RUNS = PROJECT / "runs" / "tren_cao"
SYNTHETIC_FORBIDDEN_DIRS = (PROJECT / "configs", PROJECT / "calibration", PROJECT / "docs" / "evidence")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

# ---- ngưỡng (ĐỀ XUẤT – CHỜ CHỐT; KICH_BAN khi có ghi) ------------------------------------------------------------------
MIN_CONTROL_USED = 8            # mốc kiểm soát còn dùng để khớp sau khi loại ngoại lai
MIN_CHECK_POINTS = 8            # điểm kiểm tra thấy được (KICH_BAN 3.3: ≥ 8)
CHECK_MAX_M = 0.017             # sai số lớn nhất trên điểm kiểm tra (N-D1 5 cm / 3, KICH_BAN 3.5 bước 4)
CAMERA_HEIGHT_M = (1.0, 4.0)    # độ cao camera hợp lý
SANE_HEIGHT_M = (0.3, 10.0)     # ngoài khoảng này là nhập sai (cm thay vì m, mã đổi chỗ): từ chối luôn
MAX_TILT_DEG = 25.0             # góc giữa trục quang và phương thẳng đứng
OUTLIER_MIN_M = 0.010           # loại mốc lệch > max(10 mm, 3 × trung vị)
OUTLIER_MEDIAN_FACTOR = 3.0
MIN_SEEN_FRACTION = 0.5         # mốc thấy ở < 50 % khung sàn trống thì bỏ
MIN_MODULE_PX = 4.5             # cỡ ô module trên ảnh dưới mức này thì bộ dò hay bỏ sót (bản thử: 3,5 px bị sót)
FLOOR_MARKER_MM = 100.0         # cạnh marker mốc sàn in (dự đoán cỡ ô module của mốc không thấy)
FLOOR_FRAMES = 30               # số khung đầu của video sàn trống dùng để khớp
SIDE_TOLERANCE = 0.10           # cạnh marker xe đo được lệch cấu hình quá 10 % thì bỏ marker đó
PAIR_TOLERANCE_M = 0.005        # khoảng cách hai marker xe lệch cấu hình quá 5 mm thì khung không hợp lệ
EDGE_YAW_TOLERANCE_DEG = 5.0    # hướng cạnh marker lệch hướng hai tâm quá 5° thì đánh dấu (tệp chi tiết)
SHIFT_THRESHOLD_PX = 0.7        # camera dịch: trung vị lệch tâm mốc sàn > 0,7 px …
SHIFT_FRAMES = 15               # … trong 15 khung đo liên tiếp …
SHIFT_MIN_SEEN = 4              # … mỗi khung thấy ≥ 4 mốc sàn
MIN_VALID_FRACTION = 0.8        # dưới 80 % khung hợp lệ thì mã thoát 1
CAPTURE_LATENCY_S = 0.15        # độ trễ chụp ước lượng của stamp perf_counter (CHƯA ĐO)
RADIAL_TREND_PX = 0.5           # |độ dốc × bán kính lớn nhất| của sai số theo bán kính > 0,5 px: nghi mô hình ống kính
MARKER_DISTANCE_M = (0.15, 0.25)   # khoảng cách hai marker xe: tối thiểu / dưới mức này thì cảnh báo (hướng √2·σ/d)
MARKER_Z_RANGE_M = (0.0, 0.5)
MARKER_SIDE_RANGE_M = (0.03, 0.30)
REFERENCE_RATIO = 3.0           # quy tắc 3 của NGUONG: tham chiếu ≤ ngưỡng / 3
FLOOR_USABLE_FOR = (("N-D1", 0.05), ("N-L1", 0.03), ("N-D5", 0.02))   # ngưỡng lớn nhất (m) xét cho phần mặt sàn
THRESHOLDS = {
    "min_control_used": MIN_CONTROL_USED, "min_check_points": MIN_CHECK_POINTS, "check_max_m": CHECK_MAX_M,
    "camera_height_m": list(CAMERA_HEIGHT_M), "max_tilt_deg": MAX_TILT_DEG, "outlier_min_m": OUTLIER_MIN_M,
    "outlier_median_factor": OUTLIER_MEDIAN_FACTOR, "min_seen_fraction": MIN_SEEN_FRACTION,
    "min_module_px": MIN_MODULE_PX, "side_tolerance": SIDE_TOLERANCE, "pair_tolerance_m": PAIR_TOLERANCE_M,
    "edge_yaw_tolerance_deg": EDGE_YAW_TOLERANCE_DEG, "shift_threshold_px": SHIFT_THRESHOLD_PX,
    "shift_frames": SHIFT_FRAMES, "shift_min_seen": SHIFT_MIN_SEEN, "min_valid_fraction": MIN_VALID_FRACTION,
    "capture_latency_s": CAPTURE_LATENCY_S, "radial_trend_px": RADIAL_TREND_PX,
    "marker_distance_m": list(MARKER_DISTANCE_M), "reference_ratio": REFERENCE_RATIO,
    "status": f"{PROPOSED} ({DELEGATED}); chỉ kiểm trên ảnh tổng hợp, {UNTESTED}",
}
REFINE_METHODS = ("contour", "subpix", "apriltag", "none")
EXIT_OK, EXIT_QUALITY, EXIT_USAGE, EXIT_CRASH = 0, 1, 2, 3


class OverheadError(ValueError):
    """Đầu vào không dùng được (tiếng Việt, người dùng sửa được). CLI in 'LỖI: …', mã thoát 2, không ghi gì."""


# ====================================================================== tiện ích
def file_sha256(path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def software() -> dict:
    return {"opencv": cv2.__version__, "numpy": np.__version__, "python": platform.python_version()}


def _num(text, name: str, where: str, *, allow_empty: bool = False) -> float | None:
    text = "" if text is None else str(text).strip()
    if not text:
        if allow_empty:
            return None
        raise OverheadError(f"{where}: thiếu {name}")
    try:
        value = float(text)
    except ValueError:
        hint = " (dùng dấu CHẤM thập phân)" if "," in text else ""
        raise OverheadError(f"{where}: {name} {text!r} không phải số{hint}") from None
    if not math.isfinite(value):
        raise OverheadError(f"{where}: {name} phải hữu hạn ({text!r})")
    return value


def check_seconds(name: str, value) -> float | None:
    """Số giây cho `sync_error_s` (--sync-error, --capture-latency-s): None, hoặc số hữu hạn ≥ 0 — cùng luật với
    `ReferenceMeta` khi đọc, nhưng kiểm TRƯỚC khi mở video (sai → OverheadError, mã thoát 2, không ghi gì)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) \
            or float(value) < 0:
        raise OverheadError(f"{name} phải là số giây hữu hạn ≥ 0 (nhận {value!r})")
    return float(value)


def _vn_date(text: str, where: str) -> str:
    """'dd/mm/yyyy' hợp lệ → chính nó; sai → OverheadError."""
    text = (text or "").strip()
    try:
        if not DATE_RE.match(text):
            raise ValueError
        datetime.strptime(text, "%d/%m/%Y")
    except ValueError:
        raise OverheadError(f"{where}: ngày {text!r} phải dạng dd/mm/yyyy") from None
    return text


def iso_from_vn(text: str) -> str:
    return datetime.strptime(text, "%d/%m/%Y").date().isoformat()


def vn_from_iso(text: str | None) -> str:
    return f"{text[8:10]}/{text[5:7]}/{text[:4]}" if text and len(text) >= 10 else (text or "")


def forbidden_dir(path) -> Path | None:
    """Thư mục cấm ghi kết quả tổng hợp (configs/, calibration/, docs/evidence/ của dự án) chứa `path`, hoặc None."""
    target = Path(path).resolve()
    for folder in SYNTHETIC_FORBIDDEN_DIRS:
        try:
            if target.is_relative_to(Path(folder).resolve()):
                return Path(folder)
        except (OSError, ValueError):
            continue
    return None


def check_output_path(path, synthetic: bool, overwrite: bool) -> Path:
    """Kiểm một tệp ra TRƯỚC khi tính: kết quả tổng hợp không vào thư mục cấm; tệp đã có thì cần `overwrite` (bản cũ
    được sao lưu lúc ghi, `backup_existing`). Không ghi gì."""
    path = Path(path)
    if synthetic:
        folder = forbidden_dir(path)
        if folder is not None:
            raise OverheadError(f"kết quả {SYNTHETIC_LABEL} không được ghi vào {folder}: chọn thư mục thử, ví dụ "
                                f"runs\\tren_cao\\tong_hop")
    if path.exists() and not overwrite:
        raise OverheadError(f"{path} đã có: thêm --overwrite để ghi đè (bản cũ được sao lưu cạnh nó)")
    return path


def backup_existing(path) -> Path | None:
    """Sao lưu tệp sắp bị ghi đè: <tên>.bak_<ngày_giờ>…<đuôi> (tên giữ chỗ độc quyền, `reserve_backup_path`)."""
    path = Path(path)
    if not path.exists():
        return None
    backup = ec.reserve_backup_path(path)
    shutil.copy2(path, backup)
    return backup


def write_text_atomic(path, text: str) -> None:
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="")
    os.replace(temporary, path)


def _jsonable(value):
    """JSON chặt: numpy → Python, số không hữu hạn → None, Path → chuỗi."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, (bool, type(None), str)):
        return value
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _r(value, nd: int = 6):
    return None if value is None or not math.isfinite(float(value)) else round(float(value), nd)


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _rot2(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s], [s, c]])


# ====================================================================== bộ dò ArUco
@dataclass(frozen=True)
class DetectorParams:
    """Bộ dò ArUco. `refine`: cách tinh chỉnh góc (mặc định đường viền: trên ảnh tổng hợp sai số điểm kiểm tra RMS 1,07 mm
    so với 2,39 mm của điểm ảnh con; ĐỀ XUẤT, chỉ bằng chứng tổng hợp). win_size/max_iter/min_accuracy_px chỉ dùng với
    'subpix'. Track phải dùng đúng bộ dò của lần khớp mặt sàn và của TC-1 thì mới chép được độ chính xác."""

    dictionary: str = DEFAULT_DICTIONARY
    refine: str = "contour"
    win_size: int = 5
    max_iter: int = 100
    min_accuracy_px: float = 0.01

    def __post_init__(self):
        if self.dictionary not in DICTIONARIES:
            raise OverheadError(f"từ điển ArUco {self.dictionary!r} không hỗ trợ ({', '.join(DICTIONARIES)})")
        if self.refine not in REFINE_METHODS:
            raise OverheadError(f"cách tinh chỉnh góc {self.refine!r} không hỗ trợ ({', '.join(REFINE_METHODS)})")

    def build(self):
        p = cv2.aruco.DetectorParameters()
        p.cornerRefinementMethod = {"contour": cv2.aruco.CORNER_REFINE_CONTOUR,
                                    "subpix": cv2.aruco.CORNER_REFINE_SUBPIX,
                                    "apriltag": cv2.aruco.CORNER_REFINE_APRILTAG,
                                    "none": cv2.aruco.CORNER_REFINE_NONE}[self.refine]
        p.cornerRefinementWinSize = int(self.win_size)
        p.cornerRefinementMaxIterations = int(self.max_iter)
        p.cornerRefinementMinAccuracy = float(self.min_accuracy_px)
        return cv2.aruco.ArucoDetector(get_dictionary(self.dictionary), p)

    @property
    def bits(self) -> int:
        """Số ô module một cạnh, kể cả viền (4×4 → 6)."""
        return int(get_dictionary(self.dictionary).markerSize) + 2

    def to_dict(self) -> dict:
        return {"dictionary": self.dictionary, "refine": self.refine, "win_size": self.win_size,
                "max_iter": self.max_iter, "min_accuracy_px": self.min_accuracy_px}

    @classmethod
    def from_dict(cls, d) -> "DetectorParams":
        if not isinstance(d, dict) or set(d) - {f.name for f in fields(cls)}:
            raise OverheadError(f"khối detector không hợp lệ: {d!r}")
        return cls(**d)


def detect_markers(image, params: DetectorParams | None = None, *, detector=None,
                   duplicates: list | None = None) -> dict[int, np.ndarray]:
    """Marker trên ảnh (xám hay BGR) → {mã: góc (4, 2) TL, TR, BR, BL}. Mã thấy hai lần trong một khung bị bỏ (nhận nhầm
    hay in trùng) và được thêm vào `duplicates` nếu có."""
    det = detector if detector is not None else (params or DetectorParams()).build()
    corners, ids, _ = det.detectMarkers(to_gray(image))
    out: dict[int, np.ndarray] = {}
    dup: set[int] = set()
    if ids is not None:
        for c, i in zip(corners, ids.ravel()):
            i = int(i)
            if i in out or i in dup:
                dup.add(i)
                out.pop(i, None)
                continue
            out[i] = np.asarray(c, np.float64).reshape(4, 2)
    if duplicates is not None:
        duplicates.extend(sorted(dup))
    return out


# ====================================================================== tệp mốc sa bàn
SURVEY_REQUIRED = ("ten", "vai_tro", "x_m", "y_m", "ma_aruco", "nguoi_do", "ngay")
SURVEY_COLUMNS = ("ten", "vai_tro", "x_m", "y_m", "z_m", "ma_aruco", "nguoi_do", "ngay", "ghi_chu")
SURVEY_OPTIONAL = ("z_m", "ghi_chu", "x_danh_dinh_m", "y_danh_dinh_m")


@dataclass(frozen=True)
class SurveyPoint:
    """Một mốc của tệp mốc: kiểm soát (dùng để khớp) hay kiểm tra (chỉ để đo sai số). x, y None = chưa đo."""

    name: str
    role: str
    x: float | None
    y: float | None
    z: float = 0.0
    marker_id: int | None = None
    measured_by: str = ""
    date: str = ""
    note: str = ""
    line: int = 0

    @property
    def measured(self) -> bool:
        return self.x is not None and self.y is not None

    @property
    def xyz(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], np.float64)

    def to_dict(self) -> dict:
        return {"ten": self.name, "vai_tro": self.role, "x_m": self.x, "y_m": self.y, "z_m": self.z,
                "ma_aruco": self.marker_id, "nguoi_do": self.measured_by, "ngay": self.date, "ghi_chu": self.note}

    @classmethod
    def from_dict(cls, d: dict) -> "SurveyPoint":
        return cls(str(d["ten"]), str(d["vai_tro"]), d.get("x_m"), d.get("y_m"), float(d.get("z_m") or 0.0),
                   d.get("ma_aruco"), str(d.get("nguoi_do", "")), str(d.get("ngay", "")), str(d.get("ghi_chu", "")))


@dataclass
class Survey:
    points: list[SurveyPoint]
    dictionary: str = DEFAULT_DICTIONARY
    path: Path | None = None
    sha256: str | None = None

    def by_name(self) -> dict[str, SurveyPoint]:
        return {p.name: p for p in self.points}

    def by_id(self) -> dict[int, SurveyPoint]:
        return {p.marker_id: p for p in self.points if p.marker_id is not None}

    @property
    def unmeasured(self) -> list[SurveyPoint]:
        return [p for p in self.points if not p.measured]

    def to_dict(self) -> dict:
        return {"path": str(self.path) if self.path else None, "sha256": self.sha256, "dictionary": self.dictionary,
                "points": [p.to_dict() for p in self.points]}


def read_survey(path, dictionary: str = DEFAULT_DICTIONARY) -> Survey:
    """Đọc chặt tệp mốc CSV (UTF-8, nhận BOM, dấu phẩy, dấu CHẤM thập phân). Lỗi → OverheadError('<tệp>: dòng N: …').

    Cột: ten, vai_tro (kiem_soat | kiem_tra), x_m, y_m (trống = chưa đo: dòng được liệt kê nhưng không dùng), z_m (trống
    = 0), ma_aruco (trống = điểm chỉ có dấu băng dính, chấm tay), nguoi_do, ngay (dd/mm/yyyy; bắt buộc ở dòng đã đo),
    ghi_chu; tùy chọn x_danh_dinh_m, y_danh_dinh_m của mẫu (không dùng để khớp)."""
    path = Path(path)
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
    except OSError as exc:
        raise OverheadError(f"không đọc được tệp mốc {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise OverheadError(f"tệp mốc {path} không phải UTF-8 ({exc})") from exc
    rows = list(csv.reader(io.StringIO(text)))
    where = f"tệp mốc {path.name}"
    if not rows:
        raise OverheadError(f"{where}: rỗng")
    header = [h.strip() for h in rows[0]]
    missing = [c for c in SURVEY_REQUIRED if c not in header]
    unknown = [c for c in header if c not in SURVEY_COLUMNS + SURVEY_OPTIONAL]
    if missing or unknown or len(set(header)) != len(header):
        raise OverheadError(f"{where}: dòng 1 (tiêu đề): thiếu cột {missing}, cột lạ {unknown}; cần "
                            f"{','.join(SURVEY_COLUMNS)}")
    limit = dictionary_size(dictionary)
    points: list[SurveyPoint] = []
    names: set[str] = set()
    ids: dict[int, str] = {}
    for line, cells in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in cells):
            continue
        at = f"{where}: dòng {line}"
        if len(cells) > len(header):
            raise OverheadError(f"{at}: có {len(cells)} ô nhưng tiêu đề có {len(header)} (số thập phân phải dùng dấu "
                                f"CHẤM; ô có dấu phẩy phải nằm trong ngoặc kép)")
        row = dict(zip(header, [c.strip() for c in cells] + [""] * (len(header) - len(cells))))
        name = row["ten"]
        if not NAME_RE.match(name):
            raise OverheadError(f"{at}: tên {name!r} phải gồm 1–32 ký tự A-Z a-z 0-9 _ -")
        if name in names:
            raise OverheadError(f"{at}: tên {name!r} trùng")
        names.add(name)
        role = row["vai_tro"]
        if role not in ROLES:
            raise OverheadError(f"{at}: vai_tro {role!r} phải là kiem_soat hoặc kiem_tra")
        x = _num(row["x_m"], "x_m", at, allow_empty=True)
        y = _num(row["y_m"], "y_m", at, allow_empty=True)
        if (x is None) != (y is None):
            raise OverheadError(f"{at}: x_m và y_m phải cùng có hoặc cùng trống (trống = chưa đo)")
        z = _num(row.get("z_m", ""), "z_m", at, allow_empty=True) or 0.0
        marker_id = None
        if row["ma_aruco"]:
            try:
                marker_id = int(row["ma_aruco"])
            except ValueError:
                raise OverheadError(f"{at}: ma_aruco {row['ma_aruco']!r} phải là số nguyên") from None
            if not 0 <= marker_id < limit:
                raise OverheadError(f"{at}: ma_aruco {marker_id} ngoài từ điển {dictionary} (0..{limit - 1})")
            if marker_id in CAR_IDS:
                raise OverheadError(f"{at}: ma_aruco {marker_id} dành cho marker xe ({CAR_IDS[marker_id]}, "
                                    f"KICH_BAN 3.2)")
            if marker_id in ids:
                raise OverheadError(f"{at}: ma_aruco {marker_id} trùng với mốc {ids[marker_id]}")
            ids[marker_id] = name
        measured_by, date = row["nguoi_do"], row["ngay"]
        if x is not None:
            if not measured_by:
                raise OverheadError(f"{at}: dòng đã đo cần nguoi_do")
            date = _vn_date(date, at)
        points.append(SurveyPoint(name, role, x, y, z, marker_id, measured_by, date, row.get("ghi_chu", ""), line))
    if not points:
        raise OverheadError(f"{where}: không có mốc nào")
    return Survey(points, dictionary, path, hashlib.sha256(raw).hexdigest())


def _spread_cells(cells: list[tuple[float, float]], count: int) -> list[tuple[float, float]]:
    """Chọn `count` tâm ô trải đều (lấy điểm xa nhất lần lượt, bắt đầu từ ô gần góc gốc)."""
    chosen = [min(cells, key=lambda c: c[0] + c[1])]
    while len(chosen) < min(count, len(cells)):
        rest = [c for c in cells if c not in chosen]
        chosen.append(max(rest, key=lambda c: min(math.hypot(c[0] - d[0], c[1] - d[1]) for d in chosen)))
    return chosen


def write_survey_template(path, size_m=(3.0, 2.0), step_m: float = 0.5, check_points: int = 8,
                          dictionary: str = DEFAULT_DICTIONARY, overwrite: bool = False) -> dict:
    """Mẫu tệp mốc: mốc kiểm soát mỗi `step_m` trên cả sa bàn (tên K_x050_y100 theo cm danh định), `check_points` điểm
    kiểm tra T01… ở tâm các ô lưới trải đều; mã ArUco theo hàng (y rồi x), bỏ 48/49 của xe; x_m, y_m để trống (đo bằng
    thước rồi điền). Trả {'ids', 'control', 'check', 'path'}."""
    sx, sy = float(size_m[0]), float(size_m[1])
    nx, ny = sx / step_m, sy / step_m
    if step_m <= 0 or abs(nx - round(nx)) > 1e-6 or abs(ny - round(ny)) > 1e-6 or nx < 1 or ny < 1:
        raise OverheadError(f"kích thước {sx:g}×{sy:g} m phải là bội của bước {step_m:g} m")
    nx, ny = int(round(nx)), int(round(ny))
    floor_ids = [i for i in range(dictionary_size(dictionary)) if i not in CAR_IDS]
    needed = (nx + 1) * (ny + 1) + check_points
    if needed > len(floor_ids):
        raise OverheadError(f"cần {needed} mã cho mốc sàn nhưng {dictionary} chỉ có {len(floor_ids)} mã ngoài 48/49 "
                            f"của xe: dùng --dictionary DICT_4X4_100 (giữ nguyên mã 0–49)")
    path = Path(path)
    if path.exists() and not overwrite:
        raise OverheadError(f"{path} đã có: thêm --overwrite để ghi đè")
    rows, ids = [], iter(floor_ids)
    for j in range(ny + 1):
        for i in range(nx + 1):
            x, y = i * step_m, j * step_m
            rows.append({"ten": f"K_x{round(x * 100):03d}_y{round(y * 100):03d}", "vai_tro": "kiem_soat",
                         "ma_aruco": next(ids), "x_danh_dinh_m": f"{x:.3f}", "y_danh_dinh_m": f"{y:.3f}"})
    cells = [((i + 0.5) * step_m, (j + 0.5) * step_m) for j in range(ny) for i in range(nx)]
    for k, (x, y) in enumerate(sorted(_spread_cells(cells, check_points), key=lambda c: (c[1], c[0])), start=1):
        rows.append({"ten": f"T{k:02d}", "vai_tro": "kiem_tra", "ma_aruco": next(ids),
                     "x_danh_dinh_m": f"{x:.3f}", "y_danh_dinh_m": f"{y:.3f}"})
    columns = list(SURVEY_COLUMNS) + ["x_danh_dinh_m", "y_danh_dinh_m"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({"z_m": "0", **row})
    if path.exists():
        backup_existing(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, buf.getvalue())
    used = [r["ma_aruco"] for r in rows]
    return {"ids": used, "control": (nx + 1) * (ny + 1), "check": min(check_points, len(cells)), "path": str(path)}


# ====================================================================== cấu hình marker trên xe
@dataclass(frozen=True)
class CarMarker:
    marker_id: int
    role: str             # sau | truoc
    x: float              # tâm marker trong hệ xe (m)
    y: float
    z: float              # độ cao mặt marker so với sàn (m)
    side: float           # cạnh marker gồm viền đen (m)
    yaw_deg: float = 0.0  # hướng trục x lúc in của marker so với trục x xe


@dataclass
class VehicleMarkers:
    name: str
    dictionary: str
    markers: tuple[CarMarker, CarMarker]          # (sau, trước)
    measured: bool
    synthetic: bool = False
    r2_points: dict | None = None                 # {'sau': (x, y), 'truoc': (x, y)} trong hệ xe
    path: Path | None = None
    sha256: str | None = None
    record: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def rear(self) -> CarMarker:
        return self.markers[0]

    @property
    def front(self) -> CarMarker:
        return self.markers[1]

    @property
    def distance_m(self) -> float:
        return math.hypot(self.front.x - self.rear.x, self.front.y - self.rear.y)

    @property
    def ids(self) -> tuple[int, int]:
        return self.rear.marker_id, self.front.marker_id

    def summary(self) -> dict:
        return {"path": str(self.path) if self.path else None, "sha256": self.sha256, "name": self.name,
                "z_m": [m.z for m in self.markers], "distance_m": round(self.distance_m, 6),
                "measured": self.measured, "synthetic": self.synthetic}


MARKERS_KEYS = {"format", "name", "measured", "synthetic", "dictionary", "point", "markers", "r2_points_m",
                "measured_by", "date", "notes"}
MARKER_KEYS = {"id", "role", "x_m", "y_m", "z_m", "side_m", "yaw_deg"}


def parse_vehicle_markers(data: dict, where: str = "cấu hình marker") -> VehicleMarkers:
    """Kiểm chặt nội dung một cấu hình marker xe (định dạng autopark.overhead_vehicle_markers/1)."""
    def bad(problem: str):
        raise OverheadError(f"{where}: {problem}")

    if not isinstance(data, dict):
        bad("phải là object JSON")
    if data.get("format") != MARKERS_FORMAT:
        bad(f"format phải là {MARKERS_FORMAT!r} (nhận {data.get('format')!r})")
    unknown = sorted(set(data) - MARKERS_KEYS)
    if unknown:
        bad(f"khóa lạ {unknown}")
    if not isinstance(data.get("name"), str) or not data["name"]:
        bad("thiếu name")
    if not isinstance(data.get("measured"), bool):
        bad("measured phải là true/false (false = số GIẢ ĐỊNH, chưa đo)")
    synthetic = data.get("synthetic", False)
    if not isinstance(synthetic, bool):
        bad("synthetic phải là true/false")
    dictionary = data.get("dictionary", DEFAULT_DICTIONARY)
    if dictionary not in DICTIONARIES:
        bad(f"dictionary {dictionary!r} không hỗ trợ")
    if data.get("point", POINT) != POINT:
        bad(f"point phải là {POINT!r} (tâm trục sau)")
    markers = data.get("markers")
    if not isinstance(markers, list) or len(markers) != 2:
        bad("cần ĐÚNG hai marker (tệp tham chiếu chỉ nhận n_markers 0..2)")
    parsed = {}
    limit = dictionary_size(dictionary)
    for k, m in enumerate(markers):
        at = f"markers[{k}]"
        if not isinstance(m, dict) or set(m) - MARKER_KEYS or not {"id", "role", "x_m", "y_m", "z_m", "side_m"} <= set(m):
            bad(f"{at} cần id, role, x_m, y_m, z_m, side_m (và tùy chọn yaw_deg)")
        if isinstance(m["id"], bool) or not isinstance(m["id"], int) or not 0 <= m["id"] < limit:
            bad(f"{at}.id phải là số nguyên trong {dictionary} (0..{limit - 1})")
        if m["role"] not in CAR_ROLES:
            bad(f"{at}.role phải là 'sau' hoặc 'truoc'")
        values = []
        for key in ("x_m", "y_m", "z_m", "side_m", "yaw_deg"):
            v = m.get(key, 0.0)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                bad(f"{at}.{key} phải là số hữu hạn")
            values.append(float(v))
        x, y, z, side, yaw = values
        if not MARKER_Z_RANGE_M[0] <= z <= MARKER_Z_RANGE_M[1]:
            bad(f"{at}.z_m {z:g} ngoài [{MARKER_Z_RANGE_M[0]:g}, {MARKER_Z_RANGE_M[1]:g}] m")
        if not MARKER_SIDE_RANGE_M[0] <= side <= MARKER_SIDE_RANGE_M[1]:
            bad(f"{at}.side_m {side:g} ngoài [{MARKER_SIDE_RANGE_M[0]:g}, {MARKER_SIDE_RANGE_M[1]:g}] m (đơn vị mét)")
        if m["role"] in parsed:
            bad(f"hai marker cùng role {m['role']!r}")
        parsed[m["role"]] = CarMarker(int(m["id"]), m["role"], x, y, z, side, yaw)
    rear, front = parsed["sau"], parsed["truoc"]
    if rear.marker_id == front.marker_id:
        bad("hai marker phải khác mã")
    distance = math.hypot(front.x - rear.x, front.y - rear.y)
    if distance < MARKER_DISTANCE_M[0]:
        bad(f"hai marker cách {distance:.3f} m < {MARKER_DISTANCE_M[0]:g} m: hướng quá kém (√2·σ/d)")
    warnings = []
    if distance < MARKER_DISTANCE_M[1]:
        warnings.append(f"hai marker chỉ cách {distance:.3f} m (< {MARKER_DISTANCE_M[1]:g} m): sai số hướng ≈ √2·σ/d lớn")
    r2 = data.get("r2_points_m")
    r2_points = None
    if r2 is not None:
        if not isinstance(r2, dict) or set(r2) != {"sau", "truoc"}:
            bad("r2_points_m phải có đúng 'sau' và 'truoc' ([x, y] trong hệ xe)")
        r2_points = {}
        for role, xy in r2.items():
            if (not isinstance(xy, list) or len(xy) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in xy)):
                bad(f"r2_points_m.{role} phải là [x, y] hữu hạn")
            r2_points[role] = (float(xy[0]), float(xy[1]))
        if math.dist(r2_points["sau"], r2_points["truoc"]) < 0.1:
            bad("hai điểm R2 (đầu thước) quá gần nhau")
    for key in ("measured_by", "date", "notes"):
        if not isinstance(data.get(key, ""), str):
            bad(f"{key} phải là chuỗi")
    return VehicleMarkers(data["name"], dictionary, (rear, front), data["measured"], synthetic, r2_points,
                          record=data, warnings=warnings)


def load_vehicle_markers(path) -> VehicleMarkers:
    path = Path(path)
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise OverheadError(f"không đọc được cấu hình marker {path}: {exc}") from exc
    car = parse_vehicle_markers(data, f"cấu hình marker {path.name}")
    car.path, car.sha256 = path, hashlib.sha256(raw).hexdigest()
    return car


# ====================================================================== nội tham camera trên cao
@dataclass
class OverheadIntrinsics:
    K: np.ndarray
    D: np.ndarray
    size: tuple[int, int]
    path: Path | None = None
    sha256: str | None = None
    record: dict = field(default_factory=dict)
    synthetic: bool = False
    acceptance_all_pass: bool | None = None
    theta_observed_max_deg: float | None = None

    @property
    def camera(self) -> dict:
        return dict(self.record.get("camera") or {})

    def to_dict(self) -> dict:
        return {"path": str(self.path) if self.path else None, "sha256": self.sha256, "camera": self.camera,
                "image_size": list(self.size), "K": self.K.tolist(), "D": self.D.tolist(),
                "acceptance_all_pass": self.acceptance_all_pass,
                "theta_observed_max_deg": self.theta_observed_max_deg, "synthetic": self.synthetic}


def intrinsics_from_record(record: dict, path=None, sha256=None) -> OverheadIntrinsics:
    """Nội tham từ một bản ghi `autopark.fisheye_intrinsics/1` của camera ngoài hub. Định dạng khác (ví dụ ống kính
    thường, mô hình lỗ kim — chưa có) thì từ chối: hàm phân nhánh theo `format` để thêm mô hình sau."""
    from autopark.perception.bev import acceptance_flag     # nhập muộn như extrinsics_calib

    if record.get("format") != fc.FORMAT:
        raise OverheadError(f"nội tham {path}: định dạng {record.get('format')!r} chưa hỗ trợ (cần {fc.FORMAT}, mô hình "
                            f"Kannala–Brandt của calib_app/fisheye_calib)")
    camera = record.get("camera") or {}
    if camera.get("hub_port") is not None:
        raise OverheadError(f"nội tham {path} là của camera cổng hub {camera.get('hub_port')}: camera trên cao phải là "
                            f"camera riêng, KICH_BAN 3.2 (hiệu chuẩn bằng calib_app --index N --camera-name tren_cao)")
    K, D, size = fc.camera_model(record)
    fov = record.get("field_of_view_deg") or {}
    theta = fov.get("theta_observed_max_deg")
    return OverheadIntrinsics(K, D, (int(size[0]), int(size[1])), Path(path) if path else None, sha256, record,
                              ec.intrinsics_is_synthetic(record), acceptance_flag(record),
                              float(theta) if isinstance(theta, (int, float)) else None)


def load_overhead_intrinsics(path) -> OverheadIntrinsics:
    path = Path(path)
    if not path.exists():
        raise OverheadError(f"chưa có tệp nội tham {path}: hiệu chuẩn camera trên cao trước (calib_app --index N "
                            f"--camera-name tren_cao, docs/HIEU_CHUAN_CAMERA.md)")
    try:
        record = fc.load_calibration(path)
    except (OSError, ValueError, KeyError) as exc:
        raise OverheadError(f"không nạp được nội tham {path}: {exc}") from exc
    return intrinsics_from_record(record, path, file_sha256(path))


# ====================================================================== camera đã khớp
UNDISTORT_CRITERIA = (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 30, 1e-12)


class OverheadCamera:
    """Camera trên cao đã khớp: tư thế (rvec, tvec) hệ sa bàn → camera và nội tham KB."""

    def __init__(self, intr: OverheadIntrinsics, rvec, tvec):
        self.intr = intr
        self.rvec = np.asarray(rvec, np.float64).reshape(3)
        self.tvec = np.asarray(tvec, np.float64).reshape(3)
        self.R = cv2.Rodrigues(self.rvec)[0]
        self.centre = -self.R.T @ self.tvec

    @property
    def height_m(self) -> float:
        return float(self.centre[2])

    @property
    def tilt_deg(self) -> float:
        """Góc giữa trục quang và phương thẳng đứng xuống."""
        axis = self.R[2]                       # trục z camera trong hệ sa bàn
        return math.degrees(math.acos(float(np.clip(-axis[2], -1.0, 1.0))))

    @property
    def heading_deg(self) -> float:
        """Hướng trục x của ảnh (sang phải) trên mặt sàn, độ từ +x sa bàn."""
        return math.degrees(math.atan2(self.R[0, 1], self.R[0, 0]))

    def normalized(self, uv) -> np.ndarray:
        """Điểm ảnh → tọa độ chuẩn hóa đã khử méo (N, 2); NaN khi khử méo không quay lại đúng điểm ảnh (ngoài miền)."""
        uv = np.asarray(uv, np.float64).reshape(-1, 2)
        K, D = self.intr.K, self.intr.D.reshape(4, 1)
        n = cv2.fisheye.undistortPoints(uv.reshape(-1, 1, 2), K, D, criteria=UNDISTORT_CRITERIA).reshape(-1, 2)
        back = cv2.fisheye.distortPoints(n.reshape(-1, 1, 2), K, D).reshape(-1, 2)
        bad = ~np.all(np.isfinite(n), axis=1) | (np.linalg.norm(back - uv, axis=1) > 0.05)
        n[bad] = np.nan
        return n

    def rays(self, uv) -> np.ndarray:
        n = self.normalized(uv)
        return np.column_stack([n, np.ones(len(n))]) @ self.R          # = (R_csᵀ·d_c)ᵀ

    def to_plane(self, uv, z: float = 0.0) -> np.ndarray:
        """Điểm ảnh → (x, y) trên mặt z (N, 2); NaN khi tia không cắt mặt đó phía trước camera."""
        d = self.rays(uv)
        out = np.full((len(d), 2), np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            lam = (z - self.centre[2]) / d[:, 2]
        ok = np.isfinite(lam) & (d[:, 2] < -1e-9) & (lam > 0)
        out[ok] = self.centre[:2] + lam[ok, None] * d[ok, :2]
        return out

    def project(self, xyz) -> np.ndarray:
        """(N, 3) điểm hệ sa bàn → (N, 2) điểm ảnh; NaN với điểm sau camera."""
        xyz = np.asarray(xyz, np.float64).reshape(-1, 3)
        uv = ec.project_points(xyz, self.rvec, self.tvec, self.intr.K, self.intr.D)
        behind = (xyz @ self.R.T + self.tvec)[:, 2] <= 1e-9
        uv[behind] = np.nan
        return uv

    def theta_deg(self, uv) -> np.ndarray:
        n = self.normalized(uv)
        return np.degrees(np.arctan(np.linalg.norm(n, axis=1)))

    def gsd_mm_per_px(self, x: float, y: float, z: float = 0.0) -> float:
        """Cỡ một điểm ảnh trên mặt z tại (x, y), mm (căn bậc hai diện tích, từ Jacobian số của phép chiếu)."""
        h = 1e-3
        p = self.project([[x, y, z], [x + h, y, z], [x, y + h, z]])
        J = np.column_stack([(p[1] - p[0]) / (h * 1000), (p[2] - p[0]) / (h * 1000)])   # px / mm
        det = abs(float(np.linalg.det(J)))
        return 1.0 / math.sqrt(det) if det > 0 and math.isfinite(det) else float("nan")

    def pose_dict(self) -> dict:
        return {"rvec": self.rvec.tolist(), "tvec": self.tvec.tolist(), "R_cs": self.R.tolist(),
                "centre_m": self.centre.tolist(), "height_m": self.height_m, "tilt_deg": self.tilt_deg,
                "heading_deg": self.heading_deg}


# ====================================================================== marker trên ảnh / trên mặt phẳng
def marker_centre_px(corners, intr: OverheadIntrinsics) -> np.ndarray:
    """Ảnh của tâm marker phẳng: giao hai đường chéo của 4 góc đã khử méo (đúng với phép chiếu phối cảnh), méo lại."""
    K, D = intr.K, intr.D.reshape(4, 1)
    n = cv2.fisheye.undistortPoints(np.asarray(corners, np.float64).reshape(-1, 1, 2), K, D,
                                    criteria=UNDISTORT_CRITERIA).reshape(4, 2)
    h = np.column_stack([n, np.ones(4)])
    x = np.cross(np.cross(h[0], h[2]), np.cross(h[1], h[3]))
    if abs(x[2]) < 1e-15:
        return np.asarray(corners, np.float64).reshape(4, 2).mean(axis=0)
    return cv2.fisheye.distortPoints((x[:2] / x[2]).reshape(1, 1, 2), K, D).reshape(2)


def module_px(corners, bits: int) -> float:
    c = np.asarray(corners, np.float64).reshape(4, 2)
    return float(np.mean(np.linalg.norm(np.roll(c, -1, axis=0) - c, axis=1)) / bits)


@dataclass(frozen=True)
class MarkerOnPlane:
    marker_id: int
    centre: np.ndarray          # (2,) m
    corners_xy: np.ndarray      # (4, 2) m
    side_m: float
    edge_yaw: float             # rad, hướng trung bình TL→TR và BL→BR
    module_px: float


def marker_on_plane(corners, cam: OverheadCamera, z: float, marker_id: int = -1, bits: int = 6) -> MarkerOnPlane | None:
    pts = cam.to_plane(corners, z)
    if not np.all(np.isfinite(pts)):
        return None
    sides = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
    e = (pts[1] - pts[0]) + (pts[2] - pts[3])
    return MarkerOnPlane(marker_id, pts.mean(axis=0), pts, float(sides.mean()), math.atan2(e[1], e[0]),
                         module_px(corners, bits))


# ====================================================================== khớp mặt sàn
@dataclass
class FloorFit:
    camera: OverheadCamera
    detector: DetectorParams
    survey: Survey
    detections: list[dict]
    missing: list[dict]
    used: list[str]
    dropped: list[dict]
    residuals: list[dict]
    check: dict
    diagnostics: dict
    ok: bool
    reasons: list[str]
    record: dict
    synthetic: bool
    path: Path | None = None
    sha256: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def intr(self) -> OverheadIntrinsics:
        return self.camera.intr

    @property
    def check_max_m(self) -> float | None:
        return self.check.get("max_m")

    def aruco_reference(self) -> dict[int, np.ndarray]:
        """Tâm (px) của các mốc sàn dò bằng ArUco lúc khớp: mốc của bộ theo dõi camera dịch."""
        return {int(d["ma_aruco"]): np.asarray(d["uv"], np.float64) for d in self.detections
                if d["source"] == "aruco" and d.get("ma_aruco") is not None}

    def gsd_centre_mm(self) -> float | None:
        return (self.diagnostics.get("gsd_mm_per_px") or {}).get("centre")


def _fmt_vn(value: float, nd: int = 1) -> str:
    return f"{value:.{nd}f}".replace(".", ",")


def _residuals(cam: OverheadCamera, points: list[SurveyPoint], uv: dict[str, np.ndarray]) -> list[dict]:
    out = []
    for p in points:
        est = cam.to_plane(uv[p.name], p.z)[0]
        proj = cam.project(p.xyz.reshape(1, 3))[0]
        dx, dy = float(est[0] - p.x), float(est[1] - p.y)
        out.append({"ten": p.name, "dx_m": dx, "dy_m": dy, "err_m": math.hypot(dx, dy) if math.isfinite(dx) else math.inf,
                    "err_px": float(np.linalg.norm(proj - uv[p.name]))})
    return out


def _solve(intr: OverheadIntrinsics, points: list[SurveyPoint], uv: dict[str, np.ndarray]) -> OverheadCamera:
    obj = np.array([p.xyz for p in points])
    img = np.array([uv[p.name] for p in points])
    try:
        rvec, tvec, _ = ec.solve_pose(obj, img, intr.K, intr.D)
    except ec.ExtrinsicsError as exc:
        raise OverheadError(f"không giải được tư thế camera từ {len(points)} mốc kiểm soát ({exc}): kiểm mã ArUco, "
                            f"tọa độ mốc và tệp nội tham") from exc
    return OverheadCamera(intr, rvec, tvec)


def _pose_refusal(cam: OverheadCamera, points: list[SurveyPoint]) -> str | None:
    """Lý do từ chối nghiệm (kèm gợi ý) hoặc None."""
    span = max(max(abs(p.x), abs(p.y)) for p in points)
    if cam.height_m <= 0:
        return ("camera nằm DƯỚI mặt sàn trong nghiệm khớp: trục y phải nằm bên TRÁI trục x khi nhìn từ trên xuống "
                "(KICH_BAN 3.3) — tệp mốc có thể đo theo hệ lật gương (y sang phải), hoặc mã ArUco bị đổi chỗ")
    if not SANE_HEIGHT_M[0] <= cam.height_m <= SANE_HEIGHT_M[1]:
        hint = (" — tọa độ mốc trông như tính bằng cm (x_m, y_m phải là MÉT)" if span > 20 else
                " — kiểm đơn vị tọa độ (mét), mã ArUco đổi chỗ và tệp nội tham đúng camera/kích thước ảnh")
        return f"độ cao camera khớp ra {cam.height_m:.2f} m, vô lý{hint}"
    return None


def _missing_reason(cam: OverheadCamera, p: SurveyPoint, size: tuple[int, int], bits: int,
                    floor_marker_mm: float) -> dict:
    out = {"ten": p.name, "ma_aruco": p.marker_id, "predicted_uv": None, "module_px": None}
    if not p.measured:
        out["reason"] = "chưa đo (x_m, y_m trống)"
        return out
    uv = cam.project(p.xyz.reshape(1, 3))[0]
    w, h = size
    if not np.all(np.isfinite(uv)) or not (0 <= uv[0] <= w - 1 and 0 <= uv[1] <= h - 1):
        out["reason"] = "ngoài khung hình"
        out["predicted_uv"] = uv.tolist() if np.all(np.isfinite(uv)) else None
        return out
    s = floor_marker_mm / 2000.0
    corners = p.xyz + np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]])
    module = module_px(cam.project(corners), bits)
    out.update({"predicted_uv": uv.tolist(), "module_px": module})
    if p.marker_id is None:
        out["reason"] = "chưa chấm tay (điểm không có mã ArUco)"
    elif module < MIN_MODULE_PX:
        out["reason"] = f"quá nhỏ: ≈ {_fmt_vn(module)} px mỗi ô, cần ≥ {_fmt_vn(MIN_MODULE_PX)}"
    else:
        out["reason"] = "không dò được"
    return out


def _homography_check(cam: OverheadCamera, used: list[SurveyPoint], uv: dict[str, np.ndarray]) -> dict:
    """So mô hình camera với một homography (cv2.findHomography, phương pháp 0) khớp trên tâm đã chuẩn hóa của các mốc
    dùng để khớp, trên lưới 0,1 m của bao lồi các mốc. Lệch lớn: mặt sàn không phẳng hoặc mô hình ống kính chưa hợp."""
    src = np.array([[p.x, p.y] for p in used], np.float64)
    dst = cam.normalized(np.array([uv[p.name] for p in used]))
    if len(src) < 4 or not np.all(np.isfinite(dst)):
        return {"max_diff_m": None, "rms_m": None}
    H, _ = cv2.findHomography(src, dst, 0)
    if H is None:
        return {"max_diff_m": None, "rms_m": None}
    hull = cv2.convexHull(src.astype(np.float32))
    (x0, y0), (x1, y1) = src.min(axis=0), src.max(axis=0)
    grid = np.array([(x, y) for x in np.arange(x0, x1 + 1e-9, 0.1) for y in np.arange(y0, y1 + 1e-9, 0.1)
                     if cv2.pointPolygonTest(hull, (float(x), float(y)), True) >= -1e-6])
    if not len(grid):
        return {"max_diff_m": None, "rms_m": None}
    Xc = np.column_stack([grid, np.zeros(len(grid))]) @ cam.R.T + cam.tvec
    n = np.column_stack([Xc[:, :2] / Xc[:, 2:3], np.ones(len(grid))])
    back = n @ np.linalg.inv(H).T
    back = back[:, :2] / back[:, 2:3]
    diff = np.linalg.norm(back - grid, axis=1)
    return {"max_diff_m": float(diff.max()), "rms_m": float(np.sqrt(np.mean(diff ** 2))), "grid_points": len(grid)}


def _radial_trend(cam: OverheadCamera, used: list[SurveyPoint], uv: dict[str, np.ndarray]) -> dict:
    c = cam.intr.K[:2, 2]
    meas = np.array([uv[p.name] for p in used])
    proj = cam.project(np.array([p.xyz for p in used]))
    r = meas - c
    rho = np.linalg.norm(r, axis=1)
    keep = rho > 1.0
    if keep.sum() < 3 or np.ptp(rho[keep]) < 1.0:
        return {"slope_px_per_100px": None, "flagged": False}
    radial = np.sum((meas - proj)[keep] * r[keep] / rho[keep, None], axis=1)
    slope = float(np.polyfit(rho[keep], radial, 1)[0])
    rho_max = float(rho.max())
    return {"slope_px_per_100px": slope * 100.0, "rho_max_px": rho_max,
            "flagged": bool(abs(slope * rho_max) > RADIAL_TREND_PX)}


def _layout_coverage(cam: OverheadCamera, layout) -> dict:
    if layout is None:
        return {"layout": None, "fraction_visible": None}
    b = layout.bounds
    xs, ys = np.arange(b.xmin, b.xmax + 1e-9, 0.05), np.arange(b.ymin, b.ymax + 1e-9, 0.05)
    pts = np.array([(x, y, 0.0) for x in xs for y in ys])
    uv = cam.project(pts)
    w, h = cam.intr.size
    inside = np.all(np.isfinite(uv), axis=1) & (uv[:, 0] >= 2) & (uv[:, 0] <= w - 3) & (uv[:, 1] >= 2) & \
        (uv[:, 1] <= h - 3)
    return {"layout": getattr(layout, "name", None), "fraction_visible": float(inside.mean())}


def usable_floor_for(check_max_m: float | None) -> list[dict]:
    """Quy tắc 3 trên sai số lớn nhất của điểm kiểm tra (chỉ phần mặt sàn; TC-1 mới quyết định)."""
    out = []
    for code, limit in FLOOR_USABLE_FOR:
        needs = limit / REFERENCE_RATIO
        out.append({"check": code, "limit_m": limit, "needs_m": round(needs, 6), "value_m": check_max_m,
                     "ok": None if check_max_m is None else bool(check_max_m <= needs + 1e-12)})
    return out


def fit_floor(frames, intr: OverheadIntrinsics, survey: Survey, *, params: DetectorParams | None = None,
              clicks: dict | None = None, layout=None, image_infos=(), floor_marker_mm: float = FLOOR_MARKER_MM,
              car_ids=tuple(CAR_IDS)) -> FloorFit:
    """Khớp tư thế camera trong hệ sa bàn từ các khung sàn trống và tệp mốc (mục 4.1 thiết kế T4)."""
    params = params or DetectorParams(survey.dictionary)
    frames = list(frames)
    clicks = dict(clicks or {})
    if not frames and not clicks:
        raise OverheadError("chưa có ảnh sàn trống nào")
    for k, img in enumerate(frames):
        if (img.shape[1], img.shape[0]) != tuple(intr.size):
            raise OverheadError(f"ảnh sàn {k + 1} cỡ {img.shape[1]}×{img.shape[0]}, nội tham là {intr.size[0]}×"
                                f"{intr.size[1]}: dùng đúng mode camera đã hiệu chuẩn")
    unknown = sorted(set(clicks) - set(survey.by_name()))
    if unknown:
        raise OverheadError(f"điểm chấm tay không có trong tệp mốc: {unknown}")
    warnings: list[str] = []
    bits = params.bits
    by_id = survey.by_id()
    seen: dict[int, list] = {}
    foreign: set[int] = set()
    duplicates: list[int] = []
    detector = params.build()
    for img in frames:
        for mid, corners in detect_markers(img, params, detector=detector, duplicates=duplicates).items():
            if mid in by_id:
                seen.setdefault(mid, []).append((marker_centre_px(corners, intr), module_px(corners, bits)))
            else:
                foreign.add(mid)
    if duplicates:
        warnings.append(f"mã thấy hai lần trong một khung (bị bỏ ở khung đó): {sorted(set(duplicates))}")
    car_seen = sorted(foreign & set(car_ids))
    if car_seen:
        warnings.append(f"xe/xe giả đang nằm trong ảnh sàn trống (thấy mã {car_seen})")
    detections, missing, uv = [], [], {}
    partial: dict[str, str] = {}
    for p in survey.points:
        if p.name in clicks:
            u, v = clicks[p.name]
            uv[p.name] = np.array([float(u), float(v)])
            detections.append({"ten": p.name, "ma_aruco": p.marker_id, "source": "click", "uv": uv[p.name].tolist(),
                               "n_frames": 0, "spread_px": 0.0, "module_px": None})
            continue
        hits = seen.get(p.marker_id, []) if p.marker_id is not None else []
        if hits and len(hits) >= MIN_SEEN_FRACTION * len(frames):
            pts = np.array([h[0] for h in hits])
            centre = np.median(pts, axis=0)
            uv[p.name] = centre
            detections.append({"ten": p.name, "ma_aruco": p.marker_id, "source": "aruco", "uv": centre.tolist(),
                               "n_frames": len(hits),
                               "spread_px": float(np.max(np.linalg.norm(pts - centre, axis=1))),
                               "module_px": float(np.median([h[1] for h in hits]))})
        elif hits:
            partial[p.name] = f"chỉ thấy ở {len(hits)}/{len(frames)} khung (cần ≥ {MIN_SEEN_FRACTION:.0%})"
    control = [p for p in survey.points if p.role == "kiem_soat" and p.measured and p.name in uv]
    if len(control) < MIN_CONTROL_USED:
        lacking = [p.name for p in survey.points if p.role == "kiem_soat" and p.name not in uv]
        unmeasured = [p.name for p in survey.points if p.role == "kiem_soat" and not p.measured]
        raise OverheadError(f"chỉ có {len(control)} mốc kiểm soát đã đo và thấy được, cần ≥ {MIN_CONTROL_USED}; "
                            f"không thấy: {lacking[:12]}{' …' if len(lacking) > 12 else ''}"
                            + (f"; chưa đo: {unmeasured[:12]}" if unmeasured else ""))
    span = max(max(abs(p.x), abs(p.y)) for p in control)
    if span > 50:
        raise OverheadError(f"tọa độ mốc lớn tới {span:g}: x_m, y_m phải tính bằng MÉT (trông như cm)")
    used = list(control)
    dropped: list[dict] = []
    while True:
        cam = _solve(intr, used, uv)
        refusal = _pose_refusal(cam, used)
        if refusal:
            raise OverheadError(refusal)
        res = _residuals(cam, used, uv)
        errs = [r["err_m"] for r in res]
        worst = int(np.argmax(errs))
        limit = max(OUTLIER_MIN_M, OUTLIER_MEDIAN_FACTOR * statistics.median(errs))
        if errs[worst] > limit and len(used) - 1 >= MIN_CONTROL_USED:
            p = used.pop(worst)
            dropped.append({"ten": p.name, "err_m": errs[worst],
                            "reason": f"lệch {errs[worst] * 1000:.1f} mm: đo thước sai, dán lệch hay nhận nhầm mã"})
            continue
        break
    if dropped:
        warnings.append(f"đã loại {len(dropped)} mốc kiểm soát lệch: {[d['ten'] for d in dropped]}")
    errs_m = np.array([r["err_m"] for r in res])
    errs_px = np.array([r["err_px"] for r in res])
    checks_pts = [p for p in survey.points if p.role == "kiem_tra" and p.measured and p.name in uv]
    check_res = _residuals(cam, checks_pts, uv) if checks_pts else []
    ce = np.array([r["err_m"] for r in check_res])
    check = {"n": len(check_res), "rms_m": float(np.sqrt(np.mean(ce ** 2))) if len(ce) else None,
             "median_m": float(np.median(ce)) if len(ce) else None, "max_m": float(ce.max()) if len(ce) else None,
             "points": check_res}
    for p in survey.points:
        if p.name in uv and p.measured:
            continue
        miss = _missing_reason(cam, p, intr.size, bits, floor_marker_mm)
        if p.name in partial:
            miss["reason"] = partial[p.name]
        missing.append(miss)
    detected_pts = [p for p in survey.points if p.name in uv and p.measured]
    theta_max = intr.theta_observed_max_deg
    extrapolated = []
    if theta_max is not None:
        thetas = cam.theta_deg(np.array([uv[p.name] for p in detected_pts])) if detected_pts else []
        extrapolated = [{"ten": p.name, "theta_deg": float(t)} for p, t in zip(detected_pts, thetas)
                        if math.isfinite(t) and t > theta_max]
    centre_floor = cam.to_plane(intr.K[:2, 2].reshape(1, 2), 0.0)[0]
    gsd_centre = cam.gsd_mm_per_px(*centre_floor) if np.all(np.isfinite(centre_floor)) else None
    gsd_points = [cam.gsd_mm_per_px(p.x, p.y, p.z) for p in survey.points if p.measured]
    gsd_points = [g for g in gsd_points if math.isfinite(g)]
    homography = _homography_check(cam, used, uv)
    radial = _radial_trend(cam, used, uv)
    if radial["flagged"]:
        warnings.append(f"sai số theo bán kính có xu hướng ({radial['slope_px_per_100px']:.2f} px mỗi 100 px): mô hình "
                        f"ống kính (Kannala–Brandt) có thể chưa hợp với camera này")
    if extrapolated:
        warnings.append(f"{len(extrapolated)} mốc ở góc nhìn lớn hơn góc lớn nhất đã thấy lúc hiệu chuẩn nội tham "
                        f"(ngoại suy): {[e['ten'] for e in extrapolated][:8]}")
    if intr.acceptance_all_pass is not True:
        warnings.append("nội tham chưa đạt mọi tiêu chí hiệu chuẩn (acceptance.all_pass không phải true)")
    if missing:
        warnings.append(f"{len(missing)} mốc không dùng được: " + "; ".join(f"{m['ten']}: {m['reason']}"
                                                                           for m in missing[:6]))
    acceptance_checks = [
        {"label": "mốc kiểm soát dùng để khớp", "value": len(used), "op": "≥", "threshold": MIN_CONTROL_USED},
        {"label": "điểm kiểm tra thấy được", "value": check["n"], "op": "≥", "threshold": MIN_CHECK_POINTS},
        {"label": "sai số lớn nhất trên điểm kiểm tra (m)", "value": check["max_m"], "op": "≤", "threshold": CHECK_MAX_M},
        {"label": "độ cao camera (m)", "value": cam.height_m, "op": "trong", "threshold": list(CAMERA_HEIGHT_M)},
        {"label": "độ nghiêng camera (°)", "value": cam.tilt_deg, "op": "≤", "threshold": MAX_TILT_DEG},
    ]
    for c in acceptance_checks:
        v, t = c["value"], c["threshold"]
        c["pass"] = bool(v is not None and (t[0] <= v <= t[1] if c["op"] == "trong" else
                                            (v >= t if c["op"] == "≥" else v <= t + 1e-12)))
    reasons = [f"{c['label']}: {c['value'] if not isinstance(c['value'], float) else round(c['value'], 4)} "
               f"(cần {c['op']} {c['threshold']})" for c in acceptance_checks if not c["pass"]]
    usable = usable_floor_for(check["max_m"])
    diagnostics = {
        "homography_check": homography, "radial_trend": radial, "extrapolated": extrapolated,
        "gsd_mm_per_px": {"centre": gsd_centre, "worst": max(gsd_points) if gsd_points else None},
        "coverage": _layout_coverage(cam, layout),
        "acceptance": {"checks": acceptance_checks, "usable_floor_for": usable},
    }
    ok = not reasons
    synthetic = intr.synthetic
    residual_block = {"used": [p.name for p in used], "dropped": dropped,
                      "rms_m": float(np.sqrt(np.mean(errs_m ** 2))), "max_m": float(errs_m.max()),
                      "rms_px": float(np.sqrt(np.mean(errs_px ** 2))), "max_px": float(errs_px.max()),
                      "residuals": res}
    status = (f"{SYNTHETIC_LABEL}: " if synthetic else "") + (
        f"ĐẠT các phép kiểm ({PROPOSED})" if ok else "CHƯA ĐẠT: " + " | ".join(reasons))
    record = {
        "format": FLOOR_FORMAT, "ok": ok, "status": status, "reasons": reasons, "warnings": warnings,
        "synthetic": synthetic, "created_local": datetime.now().isoformat(timespec="seconds"),
        "tool": f"{TOOL} floor", "git_commit": lidar_recording.git_commit(), "software": software(),
        "thresholds": THRESHOLDS, "detector": params.to_dict(), "floor_marker_mm": floor_marker_mm,
        "intrinsics": intr.to_dict(), "survey": survey.to_dict(), "images": list(image_infos),
        "detections": detections, "missing": missing, "foreign_ids": sorted(foreign),
        "camera_pose": cam.pose_dict(), "fit": residual_block, "check": check, "diagnostics": diagnostics,
        "notes": ([SYNTHETIC_LABEL] if synthetic else []) + [UNTESTED + " (02/10/2026: chỉ kiểm trên ảnh tổng hợp)"],
    }
    return FloorFit(cam, params, survey, detections, missing, [p.name for p in used], dropped, res, check,
                    diagnostics, ok, reasons, _jsonable(record), synthetic, warnings=warnings)


def save_floor_fit(path, fit: FloorFit, *, overwrite: bool = False, image: np.ndarray | None = None,
                   layout=None) -> tuple[Path, Path | None]:
    """Ghi JSON (qua tệp tạm) và, khi có `image`, ảnh xem `<tên>_xem.jpg`. Trả (json, jpg)."""
    path = check_output_path(path, fit.synthetic, overwrite)
    jpg = path.with_name(path.stem + "_xem.jpg") if image is not None else None
    if jpg is not None:
        check_output_path(jpg, fit.synthetic, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_existing(path)
    atomic_write_json(path, fit.record)
    if jpg is not None:
        backup_existing(jpg)
        ok, buf = cv2.imencode(".jpg", draw_floor_overlay(image, fit, layout), [cv2.IMWRITE_JPEG_QUALITY, 92])
        if ok:
            jpg.write_bytes(buf.tobytes())
    fit.path, fit.sha256 = path, file_sha256(path)
    return path, jpg


FLOOR_REQUIRED = ("format", "ok", "synthetic", "detector", "intrinsics", "survey", "detections", "camera_pose", "fit",
                  "check", "diagnostics")


def floor_fit_from_record(record: dict, path=None, sha256=None) -> FloorFit:
    where = f"kết quả khớp mặt sàn {path}" if path else "kết quả khớp mặt sàn"
    if not isinstance(record, dict) or record.get("format") != FLOOR_FORMAT:
        raise OverheadError(f"{where}: không phải tệp {FLOOR_FORMAT}")
    lacking = [k for k in FLOOR_REQUIRED if k not in record]
    if lacking:
        raise OverheadError(f"{where}: thiếu khóa {lacking}")
    try:
        block = record["intrinsics"]
        K, D = np.asarray(block["K"], np.float64), np.asarray(block["D"], np.float64)
        size = tuple(int(v) for v in block["image_size"])
        if K.shape != (3, 3) or D.shape != (4,) or len(size) != 2:
            raise ValueError("K/D/image_size sai hình dạng")
        intr = OverheadIntrinsics(K, D, size, Path(block["path"]) if block.get("path") else None, block.get("sha256"),
                                  {"camera": block.get("camera") or {}}, bool(block.get("synthetic", False)),
                                  block.get("acceptance_all_pass"), block.get("theta_observed_max_deg"))
        pose = record["camera_pose"]
        cam = OverheadCamera(intr, pose["rvec"], pose["tvec"])
        detector = DetectorParams.from_dict(record["detector"])
        survey = Survey([SurveyPoint.from_dict(p) for p in record["survey"]["points"]],
                        record["survey"].get("dictionary", detector.dictionary),
                        Path(record["survey"]["path"]) if record["survey"].get("path") else None,
                        record["survey"].get("sha256"))
        fit_block = record["fit"]
        return FloorFit(cam, detector, survey, list(record["detections"]), list(record.get("missing", [])),
                        list(fit_block["used"]), list(fit_block.get("dropped", [])),
                        list(fit_block.get("residuals", [])), dict(record["check"]), dict(record["diagnostics"]),
                        bool(record["ok"]), list(record.get("reasons", [])), record, bool(record["synthetic"]),
                        Path(path) if path else None, sha256, list(record.get("warnings", [])))
    except OverheadError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise OverheadError(f"{where}: nội dung hỏng ({exc})") from exc


def load_floor_fit(path) -> FloorFit:
    path = Path(path)
    try:
        raw = path.read_bytes()
        record = json.loads(raw.decode("utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise OverheadError(f"không đọc được kết quả khớp mặt sàn {path}: {exc}") from exc
    return floor_fit_from_record(record, path, hashlib.sha256(raw).hexdigest())


def _layout_polys(layout) -> list[tuple[str, np.ndarray]]:
    polys = []
    b = layout.bounds
    polys.append(("bounds", np.array([[b.xmin, b.ymin], [b.xmax, b.ymin], [b.xmax, b.ymax], [b.xmin, b.ymax]])))
    slot = getattr(layout, "slot", None)
    if slot is not None:
        c, s = math.cos(slot.yaw), math.sin(slot.yaw)
        hl, hw = slot.length / 2, slot.width / 2
        polys.append(("slot", np.array([[slot.cx + c * dx - s * dy, slot.cy + s * dx + c * dy]
                                        for dx, dy in ((-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw))])))
    for ob in getattr(layout, "obstacles", []) or []:
        polys.append(("obstacle", np.array(ob.corners())))
    return polys


def _polyline(cam: OverheadCamera, pts_xy: np.ndarray, z: float = 0.0, step: float = 0.02) -> list[np.ndarray]:
    """Đoạn thẳng trên sàn → các đoạn điểm ảnh (bỏ phần sau camera)."""
    dense = []
    for a, b in zip(pts_xy[:-1], pts_xy[1:]):
        n = max(2, int(math.ceil(np.linalg.norm(b - a) / step)) + 1)
        dense += [a + (b - a) * k / (n - 1) for k in range(n)]
    uv = cam.project(np.column_stack([np.array(dense), np.full(len(dense), z)]))
    runs, cur = [], []
    for p in uv:
        if np.all(np.isfinite(p)) and np.all(np.abs(p) < 1e5):
            cur.append(p)
        elif cur:
            runs.append(np.array(cur))
            cur = []
    if cur:
        runs.append(np.array(cur))
    return runs


def draw_floor_overlay(image: np.ndarray, fit: FloorFit, layout=None) -> np.ndarray:
    """Ảnh xem: mốc dùng (xanh lá), điểm kiểm tra (xanh lam), bị loại (đỏ), không thấy (xám, vị trí dự đoán), tên, mũi
    tên sai số ×100 với thước 1 cm, lưới 0,5 m chiếu qua mô hình, và bố trí (biên, ô đỗ, vật cản) nếu có."""
    out = image.copy() if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    cam = fit.camera
    pts = [p for p in fit.survey.points if p.measured]
    if pts:
        xs, ys = [p.x for p in pts], [p.y for p in pts]
        x0, x1 = math.floor(min(xs) * 2) / 2 - 0.5, math.ceil(max(xs) * 2) / 2 + 0.5
        y0, y1 = math.floor(min(ys) * 2) / 2 - 0.5, math.ceil(max(ys) * 2) / 2 + 0.5
        for x in np.arange(x0, x1 + 1e-9, 0.5):
            for run in _polyline(cam, np.array([[x, y0], [x, y1]])):
                cv2.polylines(out, [np.round(run).astype(np.int32)], False, (200, 200, 60), 1, cv2.LINE_AA)
        for y in np.arange(y0, y1 + 1e-9, 0.5):
            for run in _polyline(cam, np.array([[x0, y], [x1, y]])):
                cv2.polylines(out, [np.round(run).astype(np.int32)], False, (200, 200, 60), 1, cv2.LINE_AA)
    if layout is not None:
        colors = {"bounds": (255, 255, 255), "slot": (0, 220, 255), "obstacle": (60, 60, 255)}
        for kind, poly in _layout_polys(layout):
            for run in _polyline(cam, np.vstack([poly, poly[:1]])):
                cv2.polylines(out, [np.round(run).astype(np.int32)], False, colors[kind], 2, cv2.LINE_AA)
    by_name = fit.survey.by_name()
    det_uv = {d["ten"]: np.asarray(d["uv"]) for d in fit.detections}
    used, dropped = set(fit.used), {d["ten"] for d in fit.dropped}
    errors = {r["ten"]: r for r in fit.residuals}
    errors.update({r["ten"]: r for r in fit.check.get("points", [])})

    def mark(uv, color, name):
        if uv is None or not np.all(np.isfinite(uv)):
            return
        c = (int(round(uv[0])), int(round(uv[1])))
        cv2.circle(out, c, 6, color, 2, cv2.LINE_AA)
        cv2.putText(out, name, (c[0] + 7, c[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)

    for name, uv in det_uv.items():
        p = by_name.get(name)
        color = (0, 200, 0) if name in used else (0, 0, 255) if name in dropped else (255, 140, 0) \
            if p is not None and p.role == "kiem_tra" else (180, 180, 180)
        mark(uv, color, name)
        r = errors.get(name)
        if r is not None and p is not None and p.measured and math.isfinite(r.get("err_m", math.inf)):
            tip = p.xyz + 100.0 * np.array([r["dx_m"], r["dy_m"], 0.0])
            a, b = cam.project(np.array([p.xyz, tip]))
            if np.all(np.isfinite(a)) and np.all(np.isfinite(b)):
                cv2.arrowedLine(out, tuple(int(v) for v in np.round(a)), tuple(int(v) for v in np.round(b)), color, 1,
                                cv2.LINE_AA, tipLength=0.2)
    for m in fit.missing:
        if m.get("predicted_uv") is not None:
            mark(np.asarray(m["predicted_uv"]), (128, 128, 128), m["ten"])
    h = out.shape[0]
    centre = cam.to_plane(fit.intr.K[:2, 2].reshape(1, 2), 0.0)[0]
    if np.all(np.isfinite(centre)):
        a, b = cam.project(np.array([[centre[0], centre[1], 0.0], [centre[0] + 1.0, centre[1], 0.0]]))
        if np.all(np.isfinite(a)) and np.all(np.isfinite(b)):
            length = int(round(np.linalg.norm(b - a)))
            cv2.line(out, (10, h - 30), (10 + length, h - 30), (255, 255, 255), 3)
            cv2.putText(out, "1 cm sai so (x100)", (10, h - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
                        cv2.LINE_AA)
    legend = "xanh la: moc kiem soat | xanh lam: diem kiem tra | do: bi loai | xam: khong thay | mui ten: sai so x100"
    cv2.putText(out, legend, (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    if fit.synthetic:
        cv2.putText(out, "TONG HOP - KHONG PHAI SO DO", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2,
                    cv2.LINE_AA)
    return out


def floor_summary_lines(fit: FloorFit) -> list[str]:
    """Tóm tắt một lần khớp (in ra màn hình, ô chữ của giao diện)."""
    cam, f, c = fit.camera, fit.record.get("fit", {}), fit.check
    lines = [("TỔNG HỢP — KHÔNG PHẢI SỐ ĐO. " if fit.synthetic else "")
             + ("ĐẠT các phép kiểm" if fit.ok else "CHƯA ĐẠT") + f" ({PROPOSED})",
             f"camera: cao {cam.height_m:.3f} m, nghiêng {cam.tilt_deg:.1f}°, tâm ({cam.centre[0]:.3f}, "
             f"{cam.centre[1]:.3f}) m",
             f"mốc kiểm soát dùng {len(fit.used)}, bị loại {len(fit.dropped)}"
             + (": " + "; ".join(f"{d['ten']} {d['reason']}" for d in fit.dropped) if fit.dropped else ""),
             f"sai số dư mốc kiểm soát: RMS {f.get('rms_m', 0) * 1000:.2f} mm, lớn nhất {f.get('max_m', 0) * 1000:.2f} mm "
             f"({f.get('rms_px', 0):.2f} / {f.get('max_px', 0):.2f} px)"]
    if c.get("n"):
        lines.append(f"điểm kiểm tra ({c['n']}): RMS {c['rms_m'] * 1000:.2f} mm, trung vị {c['median_m'] * 1000:.2f} mm, "
                     f"lớn nhất {c['max_m'] * 1000:.2f} mm")
    else:
        lines.append("điểm kiểm tra: không thấy điểm nào")
    hc = fit.diagnostics.get("homography_check") or {}
    if hc.get("max_diff_m") is not None:
        lines.append(f"so với homography: lệch lớn nhất {hc['max_diff_m'] * 1000:.2f} mm, RMS {hc['rms_m'] * 1000:.2f} mm")
    gsd = fit.diagnostics.get("gsd_mm_per_px") or {}
    if gsd.get("centre") is not None:
        lines.append(f"độ phân giải trên sàn: {gsd['centre']:.2f} mm/px ở tâm, tệ nhất {gsd.get('worst') or 0:.2f}")
    usable = (fit.diagnostics.get("acceptance") or {}).get("usable_floor_for") or []
    if usable:
        lines.append("Dùng được cho (chỉ phần mặt sàn): " + ", ".join(
            f"{u['check']} {'có' if u['ok'] else 'KHÔNG'} (cần ≤ {u['needs_m'] * 100:.2f} cm)" for u in usable)
            + f" — {PROPOSED}")
    lines += [f"không dùng được: {m['ten']} ({m['reason']})" for m in fit.missing]
    lines += [f"CẢNH BÁO: {w}" for w in fit.warnings]
    lines += [f"chưa đạt: {r}" for r in fit.reasons]
    return lines


# ====================================================================== video và đồng hồ
FRAMES_FIELDS = ["frame", "t_perf", "t_s", "width", "height"]


@dataclass(frozen=True)
class OverheadFrame:
    index: int
    t: float
    image: np.ndarray


def read_frames_csv(path) -> list[tuple[int, float]]:
    """`<tên>.frames.csv` của bộ ghi trên cao → [(frame, t_perf)]; frame phải 0, 1, 2…, t_perf tăng ngặt."""
    path = Path(path)
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or not {"frame", "t_perf"} <= set(reader.fieldnames):
                raise OverheadError(f"{path.name}: cần cột frame, t_perf (tệp của video.overhead_record)")
            rows = list(reader)
    except OSError as exc:
        raise OverheadError(f"không đọc được {path}: {exc}") from exc
    out = []
    for line, row in enumerate(rows, start=2):
        at = f"{path.name}: dòng {line}"
        try:
            k, t = int(row["frame"]), float(row["t_perf"])
        except (TypeError, ValueError):
            raise OverheadError(f"{at}: frame/t_perf không phải số") from None
        if k != len(out) or not math.isfinite(t) or (out and t <= out[-1][1]):
            raise OverheadError(f"{at}: frame phải tăng từng 1 từ 0 và t_perf tăng ngặt")
        out.append((k, t))
    return out


def _open_video_source(path):
    """Nguồn phát lại cho video không có frames.csv (tách riêng để test thay được)."""
    from autopark.video.sources import VideoFileSource

    return VideoFileSource(path, source_id="cam_tren_cao")


NOMINAL_NOTE = "đồng hồ video theo số khung/s danh định"     # đầu mọi ghi chú về đồng hồ danh định (không lặp)


def nominal_fps_container(path) -> bool:
    """Tệp AVI (đầu tệp `RIFF….AVI `): container không có thời điểm từng khung, vị trí khung chỉ là chỉ số / số khung/s
    ghi trong tệp — `VideoFileSource` vẫn báo đồng hồ 'position' tăng ngặt nhưng đó là số danh định (thêm
    02/10/2026)."""
    try:
        with Path(path).open("rb") as f:
            head = f.read(12)
    except OSError:
        return False
    return head[:4] == b"RIFF" and head[8:12] == b"AVI "


class OverheadVideo:
    """Video trên cao: khung + thời điểm.

    - Có `<tên>.frames.csv` + `<tên>.json` (autopark.overhead_recording/1) cạnh video: đồng hồ `perf_counter` (stamp của
      bộ ghi), số dòng phải bằng số khung giải mã được.
    - Chỉ có một trong hai tệp đó (chép thiếu), hay `frames_csv` được chỉ ra mà thiếu JSON của bộ ghi: TỪ CHỐI (sửa
      02/10/2026; trước đây lặng lẽ bỏ stamp thật của frames.csv và mất cờ TỔNG HỢP của JSON).
    - Không có tệp nào của bộ ghi: đồng hồ `video` (stamp của tệp, `VideoFileSource`). Tệp chỉ cho số khung/s danh định
      (mọi tệp AVI, `nominal_fps_container`; hay tệp khác mà vị trí khung không tăng ngặt) bị từ chối trừ khi
      `allow_nominal_fps` (thêm ghi chú). Không có JSON của bộ ghi thì không biết video có phải TỔNG HỢP (ghi chú).

    `need_clock=False` (khớp mặt sàn: chỉ cần ảnh) bỏ qua các luật đồng hồ ở trên."""

    def __init__(self, path, frames_csv=None, allow_nominal_fps: bool = False, *, need_clock: bool = True):
        self.path = Path(path)
        if not self.path.is_file():
            raise OverheadError(f"không có video {self.path}")
        self.allow_nominal_fps = allow_nominal_fps or not need_clock
        self.notes: list[str] = []
        self._sha256: str | None = None
        cap = cv2.VideoCapture(str(self.path))
        if not cap.isOpened():
            raise OverheadError(f"OpenCV không mở được video {self.path}")
        self.size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        cap.release()
        csv_path = Path(frames_csv) if frames_csv else self.path.with_name(self.path.stem + ".frames.csv")
        json_path = self.path.with_suffix(".json")
        self.meta: dict | None = None
        self.rows: list[tuple[int, float]] = []
        self.frames_csv: Path | None = None
        if frames_csv and not csv_path.exists():
            raise OverheadError(f"không có {csv_path}")
        meta = None
        if json_path.exists():
            try:
                meta = json.loads(json_path.read_text(encoding="utf-8-sig"))
            except ValueError as exc:
                raise OverheadError(f"{json_path.name} hỏng: {exc}") from exc
        recorder_json = isinstance(meta, dict) and meta.get("format") == RECORDING_FORMAT
        if csv_path.exists() and recorder_json:
            self.clock, self.meta, self.frames_csv = "perf_counter", meta, csv_path
            self.rows = read_frames_csv(csv_path)
            if self.frame_count > 0 and self.frame_count != len(self.rows):
                raise OverheadError(f"{csv_path.name} có {len(self.rows)} dòng nhưng video có {self.frame_count} khung: "
                                    f"tệp không khớp nhau (ghi dở hay ghép nhầm)")
            if not self.rows:
                raise OverheadError(f"{csv_path.name} không có khung nào")
            return
        self.clock = "video"
        if need_clock and (csv_path.exists() or recorder_json):
            have, lack = ((csv_path.name, f"{json_path.name} của bộ ghi ({RECORDING_FORMAT})") if csv_path.exists()
                          else (json_path.name, csv_path.name))
            raise OverheadError(f"video {self.path.name}: có {have} của video.overhead_record nhưng thiếu {lack}: chép "
                                f"đủ các tệp của lần ghi (.avi, .frames.csv, .events.csv, .json) vào cùng thư mục — "
                                f"stamp perf_counter thật nằm ở .frames.csv, cờ TỔNG HỢP ở .json; không dùng đồng hồ "
                                f"của tệp video thay chúng")
        if need_clock:
            self.notes.append(f"video không kèm {json_path.name} của bộ ghi trên cao: không kiểm được video có phải "
                              f"TỔNG HỢP hay không")
            if nominal_fps_container(self.path):
                if not allow_nominal_fps:
                    raise OverheadError(f"video {self.path.name}: tệp AVI không có thời điểm từng khung, chỉ có số "
                                        f"khung/s danh định ({fps:g}) — không dùng làm đồng hồ (thêm "
                                        f"--allow-nominal-fps để chấp nhận, kèm ghi chú; video của "
                                        f"video.overhead_record thì chép kèm .frames.csv và .json)")
                self.notes.append(f"{NOMINAL_NOTE} ({fps:g} khung/s, tệp AVI không có thời điểm từng khung; "
                                  f"--allow-nominal-fps): thời điểm khung = chỉ số / số khung/s, không phải stamp thật")

    @property
    def host(self) -> str | None:
        return (self.meta or {}).get("host")

    @property
    def t_wall_start(self) -> str | None:
        return (self.meta or {}).get("t_wall_start")

    @property
    def synthetic(self) -> bool:
        return bool((self.meta or {}).get("synthetic", False))

    @property
    def date(self) -> str:
        """Ngày ISO của video: t_wall_start của bộ ghi, không thì ngày sửa tệp (thêm ghi chú)."""
        if self.t_wall_start:
            return str(self.t_wall_start)[:10]
        note = "ngày của video lấy theo ngày sửa tệp (không có t_wall_start của bộ ghi)"
        if note not in self.notes:
            self.notes.append(note)
        return datetime.fromtimestamp(self.path.stat().st_mtime).date().isoformat()

    def sha256(self) -> str:
        if self._sha256 is None:
            self._sha256 = file_sha256(self.path)
        return self._sha256

    def __len__(self) -> int:
        return len(self.rows) if self.clock == "perf_counter" else max(0, self.frame_count)

    def __iter__(self) -> Iterator[OverheadFrame]:
        if self.clock == "perf_counter":
            cap = cv2.VideoCapture(str(self.path))
            try:
                for k, t in self.rows:
                    ok, image = cap.read()
                    if not ok or image is None:
                        raise OverheadError(f"video {self.path.name} hết ở khung {k} nhưng "
                                            f"{self.frames_csv.name} có {len(self.rows)} dòng: tệp không khớp")
                    yield OverheadFrame(k, t, image)
                ok, _ = cap.read()
                if ok:
                    raise OverheadError(f"video {self.path.name} có nhiều khung hơn {len(self.rows)} dòng của "
                                        f"{self.frames_csv.name}: tệp không khớp")
            finally:
                cap.release()
            return
        source = _open_video_source(self.path)
        try:
            k = 0
            while (frame := source.read()) is not None:
                if getattr(source, "clock_source", "position") != "position":
                    if not self.allow_nominal_fps:
                        raise OverheadError(f"video {self.path.name}: từ khung {k} tệp không cho thời điểm khung tăng "
                                            f"ngặt, chỉ còn số khung/s danh định — không dùng làm đồng hồ (thêm "
                                            f"--allow-nominal-fps để chấp nhận, kèm ghi chú)")
                    note = (f"{NOMINAL_NOTE} từ khung {k} (--allow-nominal-fps): thời điểm khung không phải stamp "
                            f"thật")
                    if not any(n.startswith(NOMINAL_NOTE) for n in self.notes):
                        self.notes.append(note)
                yield OverheadFrame(k, float(frame.meta.stamp.t), frame.image)
                k += 1
        finally:
            source.close()

    def source_info(self) -> dict:
        info = {"video": str(self.path), "video_sha256": self.sha256(), "clock": self.clock,
                "size": list(self.size)}
        if self.frames_csv is not None:
            info.update({"frames_csv": str(self.frames_csv), "frames_csv_sha256": file_sha256(self.frames_csv),
                         "recording_json": str(self.path.with_suffix(".json")),
                         "recording_json_sha256": file_sha256(self.path.with_suffix(".json"))})
        if self.meta:
            info.update({"host": self.meta.get("host"), "t_wall_start": self.meta.get("t_wall_start"),
                         "wall_minus_perf_s": self.meta.get("wall_minus_perf_s"),
                         "recording": {k: self.meta.get(k) for k in ("codec", "quality", "status", "frames",
                                                                     "fps_real", "gap_ms", "counts")}})
        return info


# ====================================================================== tư thế từng khung
@dataclass
class FramePose:
    index: int
    t: float
    pose: Pose | None
    n_markers: int
    residual_m: float | None
    reason: str = ""
    markers: dict = field(default_factory=dict)          # role → MarkerOnPlane
    flags: list[str] = field(default_factory=list)
    floor_shift_px: float | None = None
    floor_seen: int = 0
    flash_fraction: float | None = None
    pair_err_m: float | None = None
    side_err: dict = field(default_factory=dict)          # role → (cạnh đo / cạnh cấu hình − 1)
    edge_yaw_err_deg: float | None = None

    @property
    def valid(self) -> bool:
        return self.pose is not None


def solve_frame(detections: dict, fit: FloorFit, car: VehicleMarkers, *, min_markers: int = 2, index: int = 0,
                t: float = 0.0) -> FramePose:
    """Tư thế tâm trục sau từ marker xe của một khung (mục 4.2 thiết kế T4)."""
    cam = fit.camera
    bits = fit.detector.bits
    accepted: dict[str, tuple[CarMarker, MarkerOnPlane]] = {}
    rejects, side_err, planes = [], {}, {}
    detected = 0
    for m in car.markers:
        corners = detections.get(m.marker_id)
        if corners is None:
            continue
        detected += 1
        mp = marker_on_plane(corners, cam, m.z, m.marker_id, bits)
        if mp is None:
            rejects.append(f"marker {m.role}: không chiếu được lên mặt z = {m.z:g} m")
            continue
        planes[m.role] = mp
        err = mp.side_m / m.side - 1.0
        side_err[m.role] = err
        if abs(err) > SIDE_TOLERANCE:
            rejects.append(f"marker {m.role}: cạnh {mp.side_m * 1000:.1f} mm, cấu hình {m.side * 1000:.0f} mm: sai z_m, "
                           f"nhận nhầm, marker cong")
            continue
        accepted[m.role] = (m, mp)
    fp = FramePose(index, t, None, detected, None, markers=planes, side_err=side_err)
    if len(accepted) == 2:
        (mr, pr), (mf, pf) = accepted["sau"], accepted["truoc"]
        v = pf.centre - pr.centre
        mvec = np.array([mf.x - mr.x, mf.y - mr.y])
        d_meas, d_cfg = float(np.linalg.norm(v)), float(np.linalg.norm(mvec))
        fp.pair_err_m = d_meas - d_cfg
        psi = math.atan2(v[1], v[0]) - math.atan2(mvec[1], mvec[0])
        R = _rot2(psi)
        p = 0.5 * ((pr.centre - R @ np.array([mr.x, mr.y])) + (pf.centre - R @ np.array([mf.x, mf.y])))
        edge = [abs(math.degrees(wrap_angle(mp.edge_yaw - psi - math.radians(m.yaw_deg)))) for m, mp in (
            accepted["sau"], accepted["truoc"])]
        fp.edge_yaw_err_deg = max(edge)
        if fp.edge_yaw_err_deg > EDGE_YAW_TOLERANCE_DEG:
            fp.flags.append(f"hướng cạnh marker lệch hướng hai tâm {fp.edge_yaw_err_deg:.1f}°")
        if abs(fp.pair_err_m) > PAIR_TOLERANCE_M:
            fp.reason = (f"khoảng cách hai marker lệch {fp.pair_err_m * 1000:+.1f} mm: kiểm z_m và vị trí marker")
            return fp
        fp.pose = Pose(float(p[0]), float(p[1]), wrap_angle(psi))
        fp.residual_m = abs(fp.pair_err_m) / 2.0
        fp.n_markers = 2
        return fp
    if len(accepted) == 1 and min_markers <= 1:
        m, mp = next(iter(accepted.values()))
        psi = mp.edge_yaw - math.radians(m.yaw_deg)
        p = mp.centre - _rot2(psi) @ np.array([m.x, m.y])
        s = m.side / 2
        predicted = mp.centre + (_rot2(mp.edge_yaw) @ np.array([[-s, s], [s, s], [s, -s], [-s, -s]]).T).T
        fp.pose = Pose(float(p[0]), float(p[1]), wrap_angle(psi))
        fp.residual_m = float(np.sqrt(np.mean(np.sum((predicted - mp.corners_xy) ** 2, axis=1))))
        fp.n_markers = 1
        fp.flags.append(f"chỉ một marker ({m.role}): hướng từ cạnh marker")
        return fp
    if rejects:
        fp.reason = "; ".join(rejects)
    elif detected == 0:
        fp.reason = "không thấy marker"
    else:
        fp.reason = f"chỉ thấy marker {next(iter(accepted))}" if accepted else "không thấy marker"
    return fp


class FloorShiftMonitor:
    """Camera dịch so với lúc khớp: mỗi khung, trung vị |tâm mốc sàn bây giờ − lúc khớp| (px) trên các mốc ArUco thấy
    được, khi thấy ≥ `min_seen` mốc. Lớn hơn `threshold_px` trong `frames` khung ĐO liên tiếp thì coi là đã dịch từ khung
    đầu của chuỗi đó (`moved_at`); khung không đo được (thấy ít mốc) không cắt chuỗi."""

    def __init__(self, fit: FloorFit, threshold_px: float = SHIFT_THRESHOLD_PX, frames: int = SHIFT_FRAMES,
                 min_seen: int = SHIFT_MIN_SEEN):
        self.ref = fit.aruco_reference()
        self.intr = fit.intr
        self.threshold_px, self.frames, self.min_seen = threshold_px, frames, min_seen
        self.values: list[float] = []
        self.moved_at: int | None = None
        self._streak: list[int] = []

    def update(self, index: int, detections: dict) -> tuple[float | None, int, int | None]:
        d = [float(np.linalg.norm(marker_centre_px(c, self.intr) - self.ref[mid]))
             for mid, c in detections.items() if mid in self.ref]
        if len(d) < self.min_seen:
            return None, len(d), self.moved_at
        shift = float(np.median(d))
        self.values.append(shift)
        if self.moved_at is None:
            if shift > self.threshold_px:
                self._streak.append(index)
                if len(self._streak) >= self.frames:
                    self.moved_at = self._streak[0]
            else:
                self._streak = []
        return shift, len(d), self.moved_at

    def stats(self) -> dict:
        v = np.array(self.values)
        return {"measured_frames": len(v), "median_px": float(np.median(v)) if len(v) else None,
                "p95_px": float(np.percentile(v, 95)) if len(v) else None, "max_px": float(v.max()) if len(v) else None,
                "moved_at": self.moved_at, "threshold_px": self.threshold_px, "frames": self.frames,
                "min_seen": self.min_seen,
                "note": None if len(v) else f"không kiểm được camera dịch (thấy < {self.min_seen} mốc sàn)"}


# ====================================================================== trích tư thế cả video
@dataclass(frozen=True)
class TrackOptions:
    min_markers: int = 2
    window: tuple[float, float] | None = None       # giây tính từ khung đầu của video
    flash_roi: tuple[int, int, int, int] | None = None
    preview_every_s: float = 0.2


@dataclass
class TrackResult:
    frames: list[FramePose]
    moved_at: int | None
    shift_stats: dict
    clock: str
    source_info: dict
    flashes: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    stopped: bool = False
    gaps_s: list[float] = field(default_factory=list)
    t_first: float | None = None

    @property
    def valid_fraction(self) -> float:
        return sum(f.valid for f in self.frames) / len(self.frames) if self.frames else 0.0

    @property
    def gap_p95_s(self) -> float | None:
        return float(np.percentile(self.gaps_s, 95)) if self.gaps_s else None


def _moved_reason(shift: float | None, gsd_mm: float | None) -> str:
    mm = f" (≈ {shift * gsd_mm:.0f} mm)" if shift is not None and gsd_mm else ""
    px = f"{shift:.1f}" if shift is not None else "?"
    return f"camera trên cao đã dịch {px} px{mm}: khớp lại mặt sàn"


def extract_track(frames: Iterable[OverheadFrame], fit: FloorFit, car: VehicleMarkers,
                  options: TrackOptions = TrackOptions(), *, params: DetectorParams | None = None,
                  progress: Callable | None = None, stop=None, clock: str = "", source_info: dict | None = None
                  ) -> TrackResult:
    """Mỗi khung giải mã trong cửa sổ cho đúng một FramePose (khung không hợp lệ vẫn giữ số khung và thời điểm).
    `progress(frame_pose, counts)` gọi sau mỗi khung; `stop` (threading.Event) dừng sớm."""
    params = params or fit.detector
    detector = params.build()
    monitor = FloorShiftMonitor(fit)
    flash = None
    if options.flash_roi is not None:
        from autopark.evaluation.sync_video import FlashDetector
        flash = FlashDetector(options.flash_roi)
    out: list[FramePose] = []
    counts = {"decoded": 0, "frames": 0, "valid": 0, "two_marker": 0, "duplicates": 0}
    t_first, stopped, last_t = None, False, None
    gaps: list[float] = []
    for frame in frames:
        if stop is not None and stop.is_set():
            stopped = True
            break
        counts["decoded"] += 1
        if t_first is None:
            t_first = frame.t
        rel = frame.t - t_first
        if options.window is not None:
            if rel < options.window[0] - 1e-9:
                continue
            if rel > options.window[1] + 1e-9:
                break
        gray = to_gray(frame.image)
        dups: list[int] = []
        found = detect_markers(gray, params, detector=detector, duplicates=dups)
        fp = solve_frame(found, fit, car, min_markers=options.min_markers, index=frame.index, t=frame.t)
        if dups:
            counts["duplicates"] += 1
            fp.flags.append(f"mã thấy hai lần: {dups}")
        fp.floor_shift_px, fp.floor_seen, _ = monitor.update(frame.index, found)
        if flash is not None:
            fp.flash_fraction = flash.update(frame.index, frame.t, gray)
        if last_t is not None:
            gaps.append(frame.t - last_t)
        last_t = frame.t
        out.append(fp)
        counts["frames"] += 1
        counts["valid"] += int(fp.valid)
        counts["two_marker"] += int(fp.valid and fp.n_markers == 2)
        if progress is not None:
            progress(fp, counts)
    moved_at = monitor.moved_at
    notes = []
    if moved_at is not None:
        gsd = fit.gsd_centre_mm()
        for fp in out:
            if fp.index >= moved_at:
                if fp.valid:
                    counts["valid"] -= 1
                    counts["two_marker"] -= int(fp.n_markers == 2)
                fp.pose, fp.residual_m = None, None
                fp.reason = _moved_reason(fp.floor_shift_px, gsd)
        notes.append(f"camera trên cao dịch từ khung {moved_at}: các dòng từ đó không hợp lệ, khớp lại mặt sàn")
    stats = monitor.stats()
    if stats["note"]:
        notes.append(stats["note"])
    if stopped:
        notes.append("dừng giữa chừng theo yêu cầu: chỉ có các khung đã xử lý")
    return TrackResult(out, moved_at, stats, clock, dict(source_info or {}),
                       flash.onsets() if flash is not None else [], counts, notes, stopped, gaps, t_first)


DETAIL_FIELDS = ["frame", "t_s", "valid", "reason", "n_markers", "sau_x", "sau_y", "truoc_x", "truoc_y", "pair_err_mm",
                 "side_err_sau_pct", "side_err_truoc_pct", "edge_yaw_err_deg", "floor_shift_px", "floor_seen",
                 "flash_fraction"]


def detail_rows(result: TrackResult) -> list[dict]:
    rows = []
    for fp in result.frames:
        def xy(role, k):
            mp = fp.markers.get(role)
            return "" if mp is None else f"{mp.centre[k]:.5f}"

        def opt(value, fmt):
            return "" if value is None else format(value, fmt)
        rows.append({"frame": fp.index, "t_s": f"{fp.t:.4f}", "valid": int(fp.valid),
                     "reason": "; ".join([fp.reason] * bool(fp.reason) + fp.flags), "n_markers": fp.n_markers,
                     "sau_x": xy("sau", 0), "sau_y": xy("sau", 1), "truoc_x": xy("truoc", 0), "truoc_y": xy("truoc", 1),
                     "pair_err_mm": opt(None if fp.pair_err_m is None else fp.pair_err_m * 1000, ".2f"),
                     "side_err_sau_pct": opt(None if "sau" not in fp.side_err else fp.side_err["sau"] * 100, ".2f"),
                     "side_err_truoc_pct": opt(None if "truoc" not in fp.side_err else fp.side_err["truoc"] * 100,
                                               ".2f"),
                     "edge_yaw_err_deg": opt(fp.edge_yaw_err_deg, ".2f"), "floor_shift_px": opt(fp.floor_shift_px, ".3f"),
                     "floor_seen": fp.floor_seen, "flash_fraction": opt(fp.flash_fraction, ".3f")})
    return rows


def _sync_error(clock: str, gap_p95: float | None, pairs, sync_error_s, capture_latency_s) -> tuple[float | None, str]:
    if sync_error_s is not None:
        return float(sync_error_s), f"sai số đồng bộ {sync_error_s:g} s do người dùng đặt (--sync-error)"
    if clock == "perf_counter" and not pairs:
        return float(capture_latency_s), (f"sai số đồng bộ = độ trễ chụp ước lượng {capture_latency_s:g} s "
                                          f"(--capture-latency-s, {PROPOSED}, CHƯA ĐO)")
    if gap_p95 is None:
        return None, "chưa biết khoảng cách khung: sai số đồng bộ để trống"
    return gap_p95, (f"sai số đồng bộ ± một khung = p95 khoảng cách khung {gap_p95:.3f} s (KICH_BAN 2.5); độ trễ hiển "
                     f"thị L của dấu nháy CHƯA ĐO")


def build_reference(result: TrackResult, fit: FloorFit, car: VehicleMarkers, video: OverheadVideo | None = None, *,
                    tc1=None, tc1_day=None, sync=(), sync_error_s: float | None = None,
                    capture_latency_s: float = CAPTURE_LATENCY_S, allow_flags=(), marks=None,
                    first_mark: int | None = None) -> tuple[list[ReferenceSample], ReferenceMeta, list[dict], list[str]]:
    """Mẫu, tệp mô tả, dòng chi tiết và cảnh báo cho `write_track` (hợp đồng reference_pose không đổi)."""
    sync_error_s = check_seconds("sai số đồng bộ (--sync-error)", sync_error_s)
    capture_latency_s = check_seconds("độ trễ chụp (--capture-latency-s)", capture_latency_s)
    allow = set(allow_flags)
    warnings: list[str] = []
    notes: list[str] = []
    synthetic = bool(fit.synthetic or car.synthetic or (video is not None and video.synthetic))
    if synthetic:
        notes.append(SYNTHETIC_LABEL)
    samples = [ReferenceSample(fp.t, fp.pose, fp.index, fp.n_markers, fp.residual_m) for fp in result.frames]
    # cặp đồng bộ: --sync của người dùng, rồi dấu nháy T14 tìm thấy trong video
    pairs = list(sync)
    flash_offsets = []
    if result.flashes and marks is not None:
        from autopark.evaluation.sync_video import match_flashes
        matched = match_flashes(result.flashes, marks, clock=result.clock, first_mark=first_mark)
        if not pairs:
            pairs = matched
        else:
            warnings.append("có cả --sync lẫn dấu nháy: dùng --sync, bỏ cặp từ dấu nháy")
        if result.clock == "perf_counter":
            by_n = {int(m["n"]): float(m["t_perf"]) for m in marks}
            flash_offsets = [{"mark": int(p.value), "offset_s": p.t_ref - by_n[int(p.value)]} for p in matched]
            if flash_offsets:
                notes.append("flash_offsets = thời điểm khung đầu sáng − t_perf của dấu: cận trên của độ trễ chụp + "
                             "hiển thị")
        notes.append(f"{len(matched)} cặp đồng bộ từ {len(result.flashes)} lần nháy T14 trong video")
    elif result.flashes:
        warnings.append(f"thấy {len(result.flashes)} lần nháy nhưng không có --sync-marks: không ghép được cặp")
    sync_error, sync_note = _sync_error(result.clock, result.gap_p95_s, pairs, sync_error_s, capture_latency_s)
    notes.append(sync_note)
    if result.clock == "video" and not pairs:
        warnings.append("đồng hồ video mà chưa có cặp đồng bộ: T5 cần --sync (hoặc --flash-roi + --sync-marks) để "
                        "đổi sang thời gian phiên")
    # độ chính xác: chỉ chép từ TC-1 theo luật (overhead_tc1.accuracy_for_track)
    from autopark.evaluation import overhead_tc1
    video_date = video.date if video is not None else datetime.now().date().isoformat()
    accuracy, acc_notes = overhead_tc1.accuracy_for_track(fit, car, video_date, tc1, tc1_day, "tc1_chua_du" in allow)
    forced = []
    if not car.measured:
        forced.append("cấu hình marker chưa đo (measured: false)")
    if not fit.ok:
        forced.append("khớp mặt sàn chưa đạt (ok: false)")
    if forced and accuracy.pos_max_m is not None:
        accuracy = ReferenceAccuracy(None, None, "không chép độ chính xác TC-1: " + "; ".join(forced))
    if forced:
        acc_notes.append("độ chính xác để null vì " + "; ".join(forced))
    notes += acc_notes
    tested = tc1 is not None and not getattr(tc1, "synthetic", True) and accuracy.pos_max_m is not None
    if not tested:
        notes.append(UNTESTED)
    if video is not None:
        notes += video.notes
    notes += result.notes
    valid = sum(s.valid for s in samples)
    source = dict(result.source_info)
    source.update({
        "floor": str(fit.path) if fit.path else None, "floor_sha256": fit.sha256,
        "markers": str(car.path) if car.path else None, "markers_sha256": car.sha256,
        "intrinsics_sha256": fit.intr.sha256, "detector": fit.detector.to_dict(),
        "tc1": str(tc1.path) if tc1 is not None and tc1.path else None,
        "tc1_sha256": tc1.sha256 if tc1 is not None else None,
        "tc1_day": str(tc1_day.path) if tc1_day is not None and tc1_day.path else None,
        "tc1_day_sha256": tc1_day.sha256 if tc1_day is not None else None,
        "counts": {"frames": len(samples), "valid": valid, "two_marker": result.counts.get("two_marker", 0),
                   "decoded": result.counts.get("decoded", 0)},
        "camera_shift": {"median_px": result.shift_stats.get("median_px"), "p95_px": result.shift_stats.get("p95_px"),
                         "moved_at": result.moved_at, "measured_frames": result.shift_stats.get("measured_frames")},
        "flash_offsets": flash_offsets, "flashes": [f.to_dict() for f in result.flashes],
        "frame_gap_p95_s": result.gap_p95_s, "synthetic": synthetic, "git_commit": lidar_recording.git_commit(),
        "software": software(), "thresholds": THRESHOLDS, "allow": sorted(allow),
    })
    meta = ReferenceMeta("R1", result.clock, accuracy, tuple(pairs), sync_error, " | ".join(dict.fromkeys(notes)),
                         _jsonable(source), f"{TOOL} track", utc_now())
    if valid < MIN_VALID_FRACTION * max(1, len(samples)):
        warnings.append(f"chỉ {valid}/{len(samples)} khung hợp lệ (< {MIN_VALID_FRACTION:.0%})")
    return samples, meta, detail_rows(result), warnings


def track_paths(out_csv) -> tuple[Path, Path, Path]:
    out_csv = Path(out_csv)
    return out_csv, sidecar_path(out_csv), out_csv.with_name(out_csv.stem + ".chi_tiet.csv")


def write_track(out_csv, samples: list[ReferenceSample], meta: ReferenceMeta, detail: list[dict],
                overwrite: bool = False) -> tuple[Path | None, Path | None, Path]:
    """Ghi `<tên>.csv` + `<tên>.json` (write_reference, qua tên tạm rồi đổi tên) và `<tên>.chi_tiet.csv`. Không khung
    nào hợp lệ thì chỉ ghi tệp chi tiết, trả (None, None, chi tiết).

    Tệp tham chiếu được kiểm và ghi ra tên tạm TRƯỚC khi chạm tới tệp chi tiết (sửa 02/10/2026): tệp mô tả sai luật
    (vd. sync_error_s âm hay nan) thì ném lỗi mà không ghi tệp nào, nên tệp chi tiết mới không bao giờ nằm cạnh tệp
    tham chiếu cũ."""
    csv_path, json_path, detail_path = track_paths(out_csv)
    synthetic = bool(meta.source.get("synthetic"))
    for p in (csv_path, json_path, detail_path):
        check_output_path(p, synthetic, overwrite)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=DETAIL_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(detail)
    temps: tuple[Path, Path] | None = None
    temp_csv = csv_path.with_name(csv_path.stem + f".tmp{os.getpid()}.csv")
    try:
        if any(s.valid for s in samples):
            temps = write_reference(temp_csv, samples, meta)      # kiểm cùng luật như khi đọc; sai thì chưa ghi gì
        backup_existing(detail_path)
        write_text_atomic(detail_path, buf.getvalue())
        if temps is None:
            return None, None, detail_path
        for p in (csv_path, json_path):
            backup_existing(p)
        os.replace(temps[0], csv_path)
        os.replace(temps[1], json_path)
    finally:
        for p in (temp_csv, sidecar_path(temp_csv)):                # tên tạm còn sót khi lỗi giữa chừng
            if p.exists():
                p.unlink()
    return csv_path, json_path, detail_path


# ====================================================================== kiểm một tệp
def check_file(path) -> list[str]:
    """Tóm tắt một tệp đầu vào/đầu ra bất kỳ của T4. Không đọc được → OverheadError."""
    from autopark.evaluation import overhead_tc1
    from autopark.evaluation.reference_pose import read_reference

    path = Path(path)
    if not path.exists():
        raise OverheadError(f"không có {path}")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except ValueError as exc:
            raise OverheadError(f"{path}: JSON hỏng ({exc})") from exc
        fmt = data.get("format") if isinstance(data, dict) else None
        if fmt == FLOOR_FORMAT:
            return [f"khớp mặt sàn {path.name}"] + floor_summary_lines(load_floor_fit(path))
        if fmt == overhead_tc1.TC1_FORMAT:
            return [f"biên bản TC-1 {path.name}"] + overhead_tc1.summary_lines(overhead_tc1.load_tc1(path))
        if fmt == MARKERS_FORMAT:
            car = load_vehicle_markers(path)
            lines = [f"cấu hình marker {car.name}: {'ĐÃ ĐO' if car.measured else 'GIẢ ĐỊNH (chưa đo)'}"
                     + (f", {SYNTHETIC_LABEL}" if car.synthetic else ""),
                     *(f"  {m.role}: mã {m.marker_id}, ({m.x:.3f}, {m.y:.3f}) m, z {m.z:.3f} m, cạnh {m.side * 1000:.0f} "
                       f"mm" for m in car.markers), f"  khoảng cách hai marker {car.distance_m:.3f} m"]
            return lines + [f"CẢNH BÁO: {w}" for w in car.warnings]
        if fmt == RECORDING_FORMAT:
            return [f"bản ghi {path.name}: {data.get('status')}, {data.get('frames')} khung, "
                    f"{data.get('fps_real')} khung/s, khoảng cách khung {data.get('gap_ms')} ms, lỗi {data.get('counts')}"
                    + (f", {SYNTHETIC_LABEL}" if data.get("synthetic") else "")]
        if isinstance(data, dict) and data.get("kind") == "tu_the_tham_chieu":
            return check_file(path.with_suffix(".csv"))
        raise OverheadError(f"{path}: không phải tệp của T4 (format {fmt!r})")
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            header = next(csv.reader(f), [])
        if "x_m" in header and "valid" in header:
            try:
                track = read_reference(path)
            except ValueError as exc:
                raise OverheadError(str(exc)) from exc
            m = track.meta
            return [f"tham chiếu {m.method} {path.name}: {len(track.samples)} dòng, {len(track.valid_samples)} hợp lệ, "
                    f"đồng hồ {m.clock}, sai số đồng bộ {m.sync_error_s}, {len(m.sync)} cặp đồng bộ",
                    f"  độ chính xác: {m.accuracy.to_dict()}", f"  ghi chú: {m.notes}"]
        if "vai_tro" in header:
            survey = read_survey(path)
            roles = {r: sum(p.role == r for p in survey.points) for r in ROLES}
            return [f"tệp mốc {path.name}: {len(survey.points)} mốc ({roles['kiem_soat']} kiểm soát, {roles['kiem_tra']} "
                    f"kiểm tra), {len(survey.unmeasured)} chưa đo"]
        if "tu_the" in header:
            poses = overhead_tc1.read_tc1_poses(path)
            return [f"bảng tư thế TC-1 {path.name}: {len(poses)} tư thế"]
    raise OverheadError(f"{path}: không nhận ra loại tệp")


# ====================================================================== dòng lệnh
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"LỖI: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def _numbers(count: int, kind=float):
    def parse(text: str):
        parts = [p for p in re.split(r"[,;x×]", text.strip()) if p.strip()]
        if len(parts) != count:
            raise argparse.ArgumentTypeError(f"cần {count} số, nhận {text!r}")
        try:
            values = tuple(kind(p) for p in parts)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{text!r} không phải số") from None
        if any(isinstance(v, float) and not math.isfinite(v) for v in values):
            raise argparse.ArgumentTypeError(f"{text!r} không hữu hạn")
        return values
    return parse


def _sync_arg(text: str) -> SyncPair:
    from autopark.evaluation.score_run import parse_sync_side

    ref, sep, side = text.partition("=")
    if not sep:
        raise argparse.ArgumentTypeError(f"cặp đồng bộ {text!r}: cần <t_ref>=<phía log>, ví dụ 18.0=mark:1")
    try:
        value, kind = parse_sync_side(side)
        t_ref = float(ref)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if not math.isfinite(t_ref):                    # nan/inf: hỏng tệp mô tả sau khi đã xử lý cả video
        raise argparse.ArgumentTypeError(f"cặp đồng bộ {text!r}: t_ref phải hữu hạn")
    return SyncPair(t_ref, value, kind, "--sync")


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="python -m autopark.evaluation.overhead_ref",
                description="Tham chiếu trên cao R1 (T4): mẫu tệp mốc, khớp mặt sàn, trích tư thế, TC-1. Ngưỡng "
                            f"{PROPOSED}; {UNTESTED}.")
    sub = p.add_subparsers(dest="command", required=True, parser_class=_Parser)
    s = sub.add_parser("survey-template", help="mẫu tệp mốc sa bàn (x_m, y_m trống để điền số đo thước)")
    s.add_argument("--size", type=_numbers(2), default=(3.0, 2.0), metavar="RxC", help="sa bàn (m), mặc định 3.0x2.0")
    s.add_argument("--step", type=float, default=0.5, help="bước lưới mốc kiểm soát (m)")
    s.add_argument("--check", type=int, default=8, help="số điểm kiểm tra (≥ 8, KICH_BAN 3.3)")
    s.add_argument("--dictionary", default=DEFAULT_DICTIONARY, choices=DICTIONARIES)
    s.add_argument("--out", type=Path, default=None, help="tệp ra; mặc định runs/tren_cao/moc_sa_ban_<ngày>.csv")
    s.add_argument("--overwrite", action="store_true")
    s = sub.add_parser("floor", help="khớp mặt sàn: tư thế camera trong hệ sa bàn")
    s.add_argument("--intrinsics", required=True, type=Path, help="nội tham camera trên cao (T11)")
    s.add_argument("--survey", required=True, type=Path, help="tệp mốc sa bàn")
    s.add_argument("--video", type=Path, help="video sàn trống (dùng các khung đầu)")
    s.add_argument("--image", type=Path, action="append", default=[], help="ảnh sàn trống (lặp được)")
    s.add_argument("--frames", type=int, default=FLOOR_FRAMES, help="số khung đầu của --video")
    s.add_argument("--clicks", type=Path, help='điểm chấm tay: JSON {"points": [{"ten", "u", "v"}]}')
    s.add_argument("--layout", type=Path, help="bố trí tham chiếu để vẽ và kiểm độ phủ")
    s.add_argument("--refine", default="contour", choices=REFINE_METHODS)
    s.add_argument("--dictionary", default=DEFAULT_DICTIONARY, choices=DICTIONARIES)
    s.add_argument("--floor-marker-mm", type=float, default=FLOOR_MARKER_MM, help="cạnh marker mốc sàn đã in (mm)")
    s.add_argument("--out", type=Path, default=None, help="tệp JSON; mặc định runs/tren_cao/<ngày>/mat_san_<giờ>.json")
    s.add_argument("--overwrite", action="store_true")
    s = sub.add_parser("track", help="trích tư thế R1 từ video, ghi tệp tham chiếu cho T5")
    s.add_argument("--video", required=True, type=Path)
    s.add_argument("--frames-csv", type=Path, help="mặc định <tên>.frames.csv cạnh video")
    s.add_argument("--floor", required=True, type=Path, help="kết quả khớp mặt sàn")
    s.add_argument("--markers", required=True, type=Path, help="cấu hình marker trên xe")
    s.add_argument("--tc1", type=Path, help="biên bản TC-1 đầy đủ")
    s.add_argument("--tc1-day", type=Path, help="biên bản TC-1 rút gọn trong ngày")
    s.add_argument("--tc1-chua-du", action="store_true", help="chấp nhận TC-1 thiếu yêu cầu (có ghi chú)")
    s.add_argument("--out", type=Path, required=True, help="tệp tham chiếu <tên>.csv (kèm .json, .chi_tiet.csv)")
    s.add_argument("--window", type=_numbers(2), metavar="A,B", help="chỉ xử lý [A, B] giây tính từ khung đầu")
    s.add_argument("--min-markers", type=int, default=2, choices=(1, 2))
    s.add_argument("--flash-roi", type=_numbers(4, int), metavar="X,Y,W,H", help="vùng ô nháy T14 trên ảnh (px)")
    s.add_argument("--sync-marks", type=Path, help="tệp dấu đồng bộ T14 (ghép với các lần nháy)")
    s.add_argument("--first-mark", type=int, help="số dấu của lần nháy đầu (khi chỉ có một lần nháy)")
    s.add_argument("--sync", type=_sync_arg, action="append", default=[], metavar="REF=PHIÊN",
                   help="cặp đồng bộ như score_run: <t_ref>=mark:<n>|perf:<s>|io:<s>|<s>")
    s.add_argument("--sync-error", type=float, help="sai số đồng bộ (s, hữu hạn ≥ 0) ghi vào tệp mô tả")
    s.add_argument("--capture-latency-s", type=float, default=CAPTURE_LATENCY_S,
                   help=f"độ trễ chụp ước lượng của stamp perf_counter (mặc định {CAPTURE_LATENCY_S:g}, CHƯA ĐO)")
    s.add_argument("--allow-nominal-fps", action="store_true",
                   help="chấp nhận video chỉ có số khung/s danh định (mọi tệp AVI không kèm tệp của bộ ghi), có ghi "
                        "chú")
    s.add_argument("--cho-cau-hinh-chua-do", action="store_true",
                   help="dùng cấu hình marker measured:false (độ chính xác thành null)")
    s.add_argument("--cho-mat-san-chua-dat", action="store_true",
                   help="dùng kết quả khớp mặt sàn ok:false (độ chính xác thành null)")
    s.add_argument("--overwrite", action="store_true")
    s = sub.add_parser("tc1", help="TC-1: so R1 với R2 (thước) trên xe giả đứng yên")
    s.add_argument("--floor", required=True, type=Path)
    s.add_argument("--markers", required=True, type=Path)
    s.add_argument("--poses", required=True, type=Path, help="bảng tư thế TC-1 (CSV)")
    s.add_argument("--kind", choices=("full", "day"), default="full")
    s.add_argument("--compare", default="", help="so thêm cách tinh chỉnh góc, ví dụ contour,subpix")
    s.add_argument("--min-frames", type=int, default=30, help="số khung hợp lệ tối thiểu mỗi tư thế")
    s.add_argument("--thresholds", type=Path, default=None, help="tệp ngưỡng (mặc định configs/nguong_nghiem_thu.json)")
    s.add_argument("--vehicle", type=Path, default=None, help="cấu hình xe (mặc định configs/vehicle_default.json)")
    s.add_argument("--out", type=Path, default=None, help="biên bản JSON; mặc định runs/tren_cao/<ngày>/tc1_<giờ>.json")
    s.add_argument("--overwrite", action="store_true")
    s = sub.add_parser("check", help="tóm tắt một tệp của T4")
    s.add_argument("path", type=Path)
    s = sub.add_parser("synthetic", help=f"bộ thử {SYNTHETIC_LABEL}")
    s.add_argument("--out", type=Path, default=DEFAULT_RUNS / "tong_hop")
    s.add_argument("--size", type=_numbers(2, int), default=(1280, 720), metavar="WxH")
    s.add_argument("--frames", type=int, default=300)
    s.add_argument("--tc1-poses", type=int, default=10)
    s.add_argument("--tc1-frames", type=int, default=60)
    s.add_argument("--seed", type=int, default=1)
    return p


def _today_dir() -> Path:
    return DEFAULT_RUNS / datetime.now().strftime("%Y%m%d")


def _read_clicks(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return {str(p["ten"]): (float(p["u"]), float(p["v"])) for p in data["points"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise OverheadError(f"tệp chấm tay {path}: cần {{\"points\": [{{\"ten\", \"u\", \"v\"}}]}} ({exc})") from exc


def _read_image(path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR) if Path(path).exists() else None
    if image is None:
        raise OverheadError(f"không đọc được ảnh {path}")
    return image


def load_layout(path):
    from autopark.storage.scenario_store import load_scenario

    try:
        return load_scenario(path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise OverheadError(f"không đọc được bố trí {path}: {exc}") from exc


def floor_inputs(images=(), video=None, frames: int = FLOOR_FRAMES) -> tuple[list[np.ndarray], list[dict]]:
    """Khung sàn trống từ các ảnh và/hoặc `frames` khung đầu của một video, kèm thông tin nguồn cho bản ghi."""
    out, infos = [], []
    for p in images:
        out.append(_read_image(p))
        infos.append({"path": str(p), "sha256": file_sha256(p), "frames": 1})
    if video is not None:
        v = OverheadVideo(video, need_clock=False)             # khớp mặt sàn không dùng thời điểm khung
        n = 0
        for frame in v:
            out.append(frame.image)
            n += 1
            if n >= frames:
                break
        infos.append({"path": str(video), "sha256": v.sha256(), "frames": n})
    return out, infos


def _cmd_survey_template(args) -> int:
    out = args.out or DEFAULT_RUNS / f"moc_sa_ban_{datetime.now():%Y%m%d}.csv"
    info = write_survey_template(out, args.size, args.step, args.check, args.dictionary, args.overwrite)
    ids = info["ids"]
    print(f"đã ghi {info['path']}: {info['control']} mốc kiểm soát, {info['check']} điểm kiểm tra")
    print(f"in các mã {ids[0]}-{ids[-1]} ({args.dictionary}): .venv\\Scripts\\python.exe -X utf8 -m "
          f"autopark.perception.aruco_sheet --ids {ids[0]}-{ids[-1]} --size-mm 100 --dictionary {args.dictionary}")
    print("Đo tâm từng marker bằng thước (giao hai vạch), điền x_m, y_m, nguoi_do, ngay (dd/mm/yyyy).")
    return EXIT_OK


def _cmd_floor(args) -> int:
    if not args.image and args.video is None:
        raise OverheadError("cần --video hoặc ít nhất một --image (sàn trống, không có xe)")
    intr = load_overhead_intrinsics(args.intrinsics)
    survey = read_survey(args.survey, args.dictionary)
    out = args.out or _today_dir() / f"mat_san_{datetime.now():%Y%m%d_%H%M}.json"
    check_output_path(out, intr.synthetic, args.overwrite)
    check_output_path(out.with_name(out.stem + "_xem.jpg"), intr.synthetic, args.overwrite)
    clicks = _read_clicks(args.clicks) if args.clicks else {}
    layout = load_layout(args.layout) if args.layout else None
    frames, infos = floor_inputs(args.image, args.video, args.frames)
    fit = fit_floor(frames, intr, survey, params=DetectorParams(args.dictionary, args.refine), clicks=clicks,
                    layout=layout, image_infos=infos, floor_marker_mm=args.floor_marker_mm)
    path, jpg = save_floor_fit(out, fit, overwrite=args.overwrite, image=frames[0] if frames else None, layout=layout)
    for line in floor_summary_lines(fit):
        print(line)
    print(f"đã ghi {path}" + (f" và {jpg}" if jpg else ""))
    return EXIT_OK if fit.ok else EXIT_QUALITY


def check_track_inputs(fit: FloorFit, car: VehicleMarkers, video: OverheadVideo | None = None, *,
                       allow_failed_floor: bool = False, allow_unmeasured: bool = False) -> None:
    """Từ chối (OverheadError) đầu vào không dùng được cho trích tư thế: khớp mặt sàn chưa đạt, cấu hình marker chưa đo
    (trừ bộ thử tổng hợp), khác từ điển, video khác cỡ, trộn dữ liệu tổng hợp với dữ liệu thật. Dòng lệnh và giao
    diện dùng chung."""
    if not fit.ok and not allow_failed_floor:
        raise OverheadError(f"kết quả khớp mặt sàn {fit.path or ''} chưa đạt ({'; '.join(fit.reasons)}): khớp lại, "
                            f"hoặc --cho-mat-san-chua-dat (độ chính xác thành null)")
    if not car.measured and not car.synthetic and not allow_unmeasured:
        raise OverheadError(f"cấu hình marker {car.path or car.name} có measured: false (số GIẢ ĐỊNH): đo vị trí, độ "
                            f"cao, cạnh marker rồi ghi bản _v1, hoặc --cho-cau-hinh-chua-do (độ chính xác thành null)")
    if car.dictionary != fit.detector.dictionary:
        raise OverheadError(f"cấu hình marker dùng {car.dictionary}, khớp mặt sàn dùng {fit.detector.dictionary}")
    clash = sorted(set(car.ids) & set(fit.survey.by_id()))
    if clash:
        raise OverheadError(f"mã marker xe {clash} trùng mã mốc sàn của tệp mốc: đổi mã marker xe (mặc định 48, 49)")
    if video is not None and tuple(video.size) != tuple(fit.intr.size):
        raise OverheadError(f"video cỡ {video.size[0]}×{video.size[1]}, khớp mặt sàn ở {fit.intr.size[0]}×"
                            f"{fit.intr.size[1]}: dùng đúng mode camera")
    flags = {bool(fit.synthetic), bool(car.synthetic)} | (
        {video.synthetic} if video is not None and video.meta else set())
    if len(flags) > 1:
        raise OverheadError("không trộn dữ liệu TỔNG HỢP với dữ liệu thật (khớp mặt sàn, cấu hình marker, video)")


def prepare_track(args) -> tuple:
    """Đọc và kiểm mọi đầu vào của `track` TRƯỚC khi xử lý video (mọi từ chối → OverheadError, không ghi gì)."""
    from autopark.evaluation import overhead_tc1

    check_seconds("--sync-error", args.sync_error)
    check_seconds("--capture-latency-s", args.capture_latency_s)
    fit = load_floor_fit(args.floor)
    car = load_vehicle_markers(args.markers)
    allow = {"allow_failed_floor": args.cho_mat_san_chua_dat, "allow_unmeasured": args.cho_cau_hinh_chua_do}
    check_track_inputs(fit, car, **allow)                   # báo lỗi trước khi mở video
    video = OverheadVideo(args.video, args.frames_csv, args.allow_nominal_fps)
    check_track_inputs(fit, car, video, **allow)
    tc1 = overhead_tc1.load_tc1(args.tc1) if args.tc1 else None
    tc1_day = overhead_tc1.load_tc1(args.tc1_day) if args.tc1_day else None
    marks = None
    if args.flash_roi is not None:
        x, y, w, h = args.flash_roi
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > video.size[0] or y + h > video.size[1]:
            raise OverheadError(f"--flash-roi {args.flash_roi} nằm ngoài ảnh {video.size[0]}×{video.size[1]}")
    if args.sync_marks is not None:
        from autopark.evaluation.sync_marks import read_sync_marks
        try:
            marks = [m for m in read_sync_marks(args.sync_marks) if m.get("kind") == "SYNC_MARK"]
        except (OSError, ValueError, KeyError) as exc:
            raise OverheadError(f"không đọc được tệp dấu đồng bộ {args.sync_marks}: {exc}") from exc
        if args.flash_roi is None:
            raise OverheadError("--sync-marks cần --flash-roi (vùng ô nháy trên ảnh)")
    if args.window is not None and args.window[0] >= args.window[1]:
        raise OverheadError("--window A,B cần A < B")
    synthetic = bool(fit.synthetic or car.synthetic)
    for p in track_paths(args.out):
        check_output_path(p, synthetic, args.overwrite)
    allow = {name for name, on in (("tc1_chua_du", args.tc1_chua_du), ("cau_hinh_chua_do", args.cho_cau_hinh_chua_do),
                                   ("mat_san_chua_dat", args.cho_mat_san_chua_dat),
                                   ("nominal_fps", args.allow_nominal_fps)) if on}
    return fit, car, video, tc1, tc1_day, marks, allow


def _cmd_track(args) -> int:
    fit, car, video, tc1, tc1_day, marks, allow = prepare_track(args)
    options = TrackOptions(args.min_markers, tuple(args.window) if args.window else None,
                           tuple(args.flash_roi) if args.flash_roi else None)

    def progress(fp, counts):
        if counts["frames"] % 100 == 0:
            print(f"  khung {counts['frames']} · hợp lệ {counts['valid']}", file=sys.stderr)
    result = extract_track(video, fit, car, options, progress=progress, clock=video.clock,
                           source_info=video.source_info())
    samples, meta, detail, warnings = build_reference(
        result, fit, car, video, tc1=tc1, tc1_day=tc1_day, sync=args.sync, sync_error_s=args.sync_error,
        capture_latency_s=args.capture_latency_s, allow_flags=allow, marks=marks, first_mark=args.first_mark)
    csv_path, json_path, detail_path = write_track(args.out, samples, meta, detail, args.overwrite)
    valid = sum(s.valid for s in samples)
    print(f"{len(samples)} khung, {valid} hợp lệ ({valid / max(1, len(samples)):.0%}), hai marker "
          f"{result.counts.get('two_marker', 0)}; đồng hồ {meta.clock}, sai số đồng bộ {meta.sync_error_s}")
    acc = meta.accuracy
    print("độ chính xác: " + (f"vị trí ≤ {acc.pos_max_m * 100:.2f} cm, hướng ≤ {acc.yaw_max_deg:.2f}° ({acc.source})"
                              if acc.pos_max_m is not None else f"CHƯA CÓ (T5 sẽ ghi không kiểm được): {acc.source}"))
    for w in warnings:
        print(f"CẢNH BÁO: {w}")
    if csv_path is None:
        print(f"LỖI: không khung nào hợp lệ: chỉ ghi {detail_path}", file=sys.stderr)
        return EXIT_QUALITY
    print(f"đã ghi {csv_path}, {json_path}, {detail_path}")
    if result.moved_at is not None or valid < MIN_VALID_FRACTION * len(samples):
        return EXIT_QUALITY
    return EXIT_OK


def _cmd_tc1(args) -> int:
    from autopark.evaluation import overhead_tc1

    return overhead_tc1.run_cli(args)


def _cmd_check(args) -> int:
    for line in check_file(args.path):
        print(line)
    return EXIT_OK


def _cmd_synthetic(args) -> int:
    from autopark.evaluation.overhead_synth import write_synthetic_set

    info = write_synthetic_set(args.out, size=tuple(args.size), frames=args.frames, tc1_poses=args.tc1_poses,
                               tc1_frames=args.tc1_frames, seed=args.seed)
    print(f"đã ghi bộ thử {SYNTHETIC_LABEL} vào {args.out}; xem {Path(args.out) / 'README.txt'}")
    for key in ("intrinsics", "survey", "markers", "run", "tc1_poses"):
        print(f"  {key}: {info.get(key)}")
    return EXIT_OK


COMMANDS = {"survey-template": _cmd_survey_template, "floor": _cmd_floor, "track": _cmd_track, "tc1": _cmd_tc1,
            "check": _cmd_check, "synthetic": _cmd_synthetic}


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        return COMMANDS[args.command](args)
    except OverheadError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("LỖI: dừng bằng Ctrl+C (không ghi tệp kết quả nào)", file=sys.stderr)
        return EXIT_USAGE
    except Exception:                        # noqa: BLE001 - lỗi bất ngờ: in traceback, mã 3
        traceback.print_exc()
        return EXIT_CRASH


if __name__ == "__main__":
    sys.exit(main())
