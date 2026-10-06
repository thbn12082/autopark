"""TC-1 (docs/KICH_BAN_NGHIEM_THU.md mục 3.7): kiểm tham chiếu trên cao R1 bằng "xe giả" đứng yên, so với R2 — hai đầu
một thước thẳng cứng ≥ 0,65 m gắn trên xe giả, đo bằng thước thép từ các cạnh sa bàn. Thêm 02/10/2026.

    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.overhead_ref tc1 --floor docs\\evidence\\nghiem_thu\\mat_san_<ngay>.json --markers configs\\tham_chieu\\xe_gia_v1.json --poses docs\\evidence\\tc1_<ngay>.csv --kind full --out docs\\evidence\\nghiem_thu\\tham_chieu_tren_cao_<ngay>.json

**Bảng tư thế** `docs/evidence/tc1_<yyyymmdd>.csv` (git chỉ giữ CSV nằm thẳng trong docs/evidence/): cột
`tu_the,video,t_tu_s,t_den_s,x_sau_m,y_sau_m,x_truoc_m,y_truoc_m,x_tam_m,y_tam_m,nguoi_do,ngay,ghi_chu`. `video` tương
đối so với tệp CSV; cửa sổ [t_tu_s, t_den_s] tính bằng giây từ khung đầu của đoạn ghi, để trống = cả đoạn bỏ 0,5 s mỗi
đầu. `x/y_sau`, `x/y_truoc`: hai đầu thước (hệ sa bàn, m); `x_tam/y_tam` (tùy chọn): tâm trục sau đo thẳng để kiểm chéo.
Vị trí hai đầu thước trong hệ xe lấy từ `r2_points_m` của cấu hình marker.

**Mỗi tư thế:** trích R1 trên các khung trong cửa sổ (`overhead_ref.extract_track`, cần ≥ 30 khung hợp lệ), tư thế R1 =
trung vị từng trục (hướng: trung vị hiệu đã gói so với mẫu đầu), độ tản = p95 và lớn nhất của độ lệch; R2 từ hai đầu thước
(ψ = hướng đầu sau → đầu trước − hướng của chúng trong hệ xe, vị trí = trung bình hai điểm sau khi bỏ phần hệ xe); hai đầu
thước đo được cách nhau khác chiều dài thước quá 2·5 + 5 mm thì ghi "kiểm lại số đo thước".

**Yêu cầu:** đầy đủ ≥ 10 tư thế, ≥ 3 hướng cách nhau ≥ 20°, có tư thế cách mỗi góc bao các mốc kiểm soát ≤ 0,5 m; rút
gọn trong ngày ≥ 3 tư thế (KICH_BAN 3.7 bước 5). Thiếu thì vẫn ghi biên bản, liệt kê phần thiếu, mã thoát 1.

**Từ chối** (mã thoát 2, không ghi gì; `run_tc1` kiểm nên dòng lệnh và thẻ TC-1 của giao diện như nhau, sửa 02/10/2026):
khớp mặt sàn chưa đạt (ok: false), cấu hình marker thật chưa đo (measured: false), trộn dữ liệu TỔNG HỢP với dữ liệu
thật (khớp mặt sàn, cấu hình marker, và cờ `synthetic` trong JSON của bộ ghi của từng đoạn ghi tư thế).

**Độ chính xác** `accuracy` = {pos_max_m, yaw_max_deg, pos_median_m, yaw_median_deg, source}, đúng các khóa
`reference_pose.ACCURACY_KEYS` để chép nguyên vào tệp tham chiếu; là CẬN TRÊN (sai số R2 ± 3–5 mm mỗi điểm cộng vào).
TC-1 tĩnh: không đo nhòe chuyển động, màn trập cuộn, độ trễ ghi. `usable_for`: R1 dùng được cho kiểm nào theo quy tắc 3
(ngưỡng / reference_ratio của configs/nguong_nghiem_thu.json; kiểm thân xe tính thêm cánh tay đòn tới góc thân xe như
score_run; N-L1, N-L2, N-L3, N-L5 lấy từ bảng của docs/NGUONG_NGHIEM_THU_DE_XUAT.md vì tệp ngưỡng chỉ nhận mã của
score_run). **Chép độ chính xác** sang một lần chạy: xem `accuracy_for_track` (luật chặt, thà null còn hơn lạc quan).

Ngưỡng ĐỀ XUẤT – CHỜ CHỐT (người dùng giao quyết định 02/10/2026). Mới kiểm trên ảnh TỔNG HỢP; CHƯA THỬ với camera thật.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import statistics

import numpy as np

from autopark.domain.types import Pose, wrap_angle
from autopark.evaluation.overhead_ref import (DELEGATED, EXIT_OK, EXIT_QUALITY, NAME_RE, PROPOSED, SYNTHETIC_LABEL,
                                              DetectorParams, FloorFit, OverheadError, OverheadVideo, TrackOptions,
                                              VehicleMarkers, _num, _rot2, _vn_date, backup_existing,
                                              check_output_path, extract_track, file_sha256, iso_from_vn,
                                              load_floor_fit, load_vehicle_markers, software, vn_from_iso)
from autopark.evaluation.reference_pose import ACCURACY_KEYS, ReferenceAccuracy
from autopark.lidar import recording as lidar_recording
from autopark.perception.paths import PROJECT, atomic_write_json

TC1_FORMAT = "autopark.overhead_tc1/1"
KINDS = ("full", "day")
KIND_LABELS = {"full": "đầy đủ", "day": "rút gọn trong ngày"}
POSE_FIELDS = ["tu_the", "video", "t_tu_s", "t_den_s", "x_sau_m", "y_sau_m", "x_truoc_m", "y_truoc_m", "x_tam_m",
               "y_tam_m", "nguoi_do", "ngay", "ghi_chu"]
POSE_REQUIRED = ("tu_the", "video", "x_sau_m", "y_sau_m", "x_truoc_m", "y_truoc_m", "nguoi_do", "ngay")
MIN_POSES = {"full": 10, "day": 3}
MIN_HEADINGS = 3
HEADING_GAP_DEG = 20.0
CORNER_RADIUS_M = 0.5
MIN_VALID_FRAMES = 30
TRIM_S = 0.5
TAPE_ERROR_M = 0.005
RULER_TOLERANCE_M = 2 * TAPE_ERROR_M + 0.005
Z_MATCH_M = 0.005
DEFAULT_VEHICLE = PROJECT / "configs" / "vehicle_default.json"
POSITION_CHECKS = ("N-D1", "N-P2", "N-P3", "N-P5c", "N-P6", "N-P7", "N-P8")
# N-L* (định vị) không nằm trong configs/nguong_nghiem_thu.json (score_run chỉ nhận mã LIMIT_PARAMS): bảng chép từ
# docs/NGUONG_NGHIEM_THU_DE_XUAT.md (N-L1 lớn nhất 3 cm, N-L2 lớn nhất 2°, N-L3 6 cm / 4°, N-L5 4 cm / 3°).
NGUONG_L = (("N-L1", 0.03, None), ("N-L2", None, 2.0), ("N-L3", 0.06, 4.0), ("N-L5", 0.04, 3.0))
NOTES = ["TC-1 cho cận trên (sai số R2 ±3-5 mm cộng vào)", "TC-1 tĩnh: không đo nhòe chuyển động, màn trập cuộn, trễ ghi"]
TC1_THRESHOLDS = {"min_poses": dict(MIN_POSES), "min_headings": MIN_HEADINGS, "heading_gap_deg": HEADING_GAP_DEG,
                  "corner_radius_m": CORNER_RADIUS_M, "min_valid_frames": MIN_VALID_FRAMES, "trim_s": TRIM_S,
                  "ruler_tolerance_m": RULER_TOLERANCE_M, "z_match_m": Z_MATCH_M,
                  "status": f"{PROPOSED} ({DELEGATED}); KICH_BAN 3.7 cho số tư thế, hướng, góc"}


@dataclass(frozen=True)
class Tc1Pose:
    name: str
    video: Path
    window: tuple[float, float] | None
    rear: tuple[float, float]
    front: tuple[float, float]
    centre: tuple[float, float] | None
    measured_by: str
    date: str
    note: str = ""
    line: int = 0

    def to_dict(self) -> dict:
        return {"tu_the": self.name, "video": str(self.video), "window_s": list(self.window) if self.window else None,
                "sau": list(self.rear), "truoc": list(self.front), "tam": list(self.centre) if self.centre else None,
                "nguoi_do": self.measured_by, "ngay": self.date, "ghi_chu": self.note}


def read_tc1_poses(path) -> list[Tc1Pose]:
    """Đọc chặt bảng tư thế TC-1 (UTF-8, nhận BOM, dấu CHẤM thập phân). Lỗi → OverheadError('<tệp>: dòng N: …')."""
    path = Path(path)
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise OverheadError(f"không đọc được bảng tư thế {path}: {exc}") from exc
    rows = list(csv.reader(io.StringIO(text)))
    where = f"bảng tư thế {path.name}"
    if not rows:
        raise OverheadError(f"{where}: rỗng")
    header = [h.strip() for h in rows[0]]
    missing = [c for c in POSE_REQUIRED if c not in header]
    unknown = [c for c in header if c not in POSE_FIELDS]
    if missing or unknown:
        raise OverheadError(f"{where}: dòng 1 (tiêu đề): thiếu cột {missing}, cột lạ {unknown}; cần {','.join(POSE_FIELDS)}")
    out: list[Tc1Pose] = []
    names: set[str] = set()
    for line, cells in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in cells):
            continue
        at = f"{where}: dòng {line}"
        if len(cells) > len(header):
            raise OverheadError(f"{at}: nhiều ô hơn tiêu đề (số thập phân phải dùng dấu CHẤM)")
        row = dict(zip(header, [c.strip() for c in cells] + [""] * (len(header) - len(cells))))
        name = row["tu_the"]
        if not NAME_RE.match(name) or name in names:
            raise OverheadError(f"{at}: tên tư thế {name!r} sai dạng hoặc trùng")
        names.add(name)
        if not row["video"]:
            raise OverheadError(f"{at}: thiếu video")
        video = (path.parent / row["video"]).resolve()
        a, b = _num(row.get("t_tu_s"), "t_tu_s", at, allow_empty=True), _num(row.get("t_den_s"), "t_den_s", at,
                                                                               allow_empty=True)
        if (a is None) != (b is None) or (a is not None and not 0 <= a < b):
            raise OverheadError(f"{at}: t_tu_s, t_den_s phải cùng trống hoặc 0 ≤ t_tu_s < t_den_s")
        xs = [_num(row[k], k, at) for k in ("x_sau_m", "y_sau_m", "x_truoc_m", "y_truoc_m")]
        cx, cy = _num(row.get("x_tam_m"), "x_tam_m", at, allow_empty=True), _num(row.get("y_tam_m"), "y_tam_m", at,
                                                                                 allow_empty=True)
        if (cx is None) != (cy is None):
            raise OverheadError(f"{at}: x_tam_m, y_tam_m phải cùng có hoặc cùng trống")
        if not row["nguoi_do"]:
            raise OverheadError(f"{at}: thiếu nguoi_do")
        out.append(Tc1Pose(name, video, (a, b) if a is not None else None, (xs[0], xs[1]), (xs[2], xs[3]),
                           (cx, cy) if cx is not None else None, row["nguoi_do"], _vn_date(row["ngay"], at),
                           row.get("ghi_chu", ""), line))
    if not out:
        raise OverheadError(f"{where}: không có tư thế nào")
    return out


def r2_pose(rear, front, car: VehicleMarkers) -> tuple[Pose, float]:
    """Tư thế tâm trục sau từ hai đầu thước đo bằng thước (hệ sa bàn) và vị trí của chúng trong hệ xe; kèm sai lệch
    chiều dài thước (m)."""
    if not car.r2_points:
        raise OverheadError("cấu hình marker thiếu r2_points_m (vị trí hai đầu thước trong hệ xe)")
    a, b = np.array(car.r2_points["sau"]), np.array(car.r2_points["truoc"])
    p1, p2 = np.asarray(rear, np.float64), np.asarray(front, np.float64)
    psi = math.atan2(*(p2 - p1)[::-1]) - math.atan2(*(b - a)[::-1])
    R = _rot2(psi)
    p = 0.5 * ((p1 - R @ a) + (p2 - R @ b))
    return Pose(float(p[0]), float(p[1]), wrap_angle(psi)), abs(float(np.linalg.norm(p2 - p1) - np.linalg.norm(b - a)))


def static_pose(frames) -> tuple[Pose, dict]:
    """Tư thế trung vị của các khung hợp lệ khi xe đứng yên, và độ tản (p95, lớn nhất)."""
    valid = [f.pose for f in frames if f.pose is not None]
    yaw0 = valid[0].yaw
    pose = Pose(statistics.median(p.x for p in valid), statistics.median(p.y for p in valid),
                wrap_angle(yaw0 + statistics.median(wrap_angle(p.yaw - yaw0) for p in valid)))
    dpos = np.array([math.hypot(p.x - pose.x, p.y - pose.y) for p in valid])
    dyaw = np.degrees(np.abs([wrap_angle(p.yaw - pose.yaw) for p in valid]))
    return pose, {"pos_p95_m": float(np.percentile(dpos, 95)), "pos_max_m": float(dpos.max()),
                  "yaw_p95_deg": float(np.percentile(dyaw, 95)), "yaw_max_deg": float(dyaw.max())}


def distinct_headings(yaws_deg: list[float], gap_deg: float = HEADING_GAP_DEG) -> list[float]:
    """Các hướng đôi một cách nhau ≥ gap (tham lam theo thứ tự tăng, khoảng cách vòng tròn)."""
    chosen: list[float] = []
    for y in sorted(v % 360.0 for v in yaws_deg):
        if all(min(abs(y - c), 360.0 - abs(y - c)) >= gap_deg for c in chosen):
            chosen.append(y)
    return chosen


def hull_corners(fit: FloorFit) -> list[tuple[float, float]]:
    """Bốn góc hình bao (trục song song) của các mốc kiểm soát đã đo: góc sa bàn khi lưới mốc phủ cả sa bàn."""
    pts = [(p.x, p.y) for p in fit.survey.points if p.role == "kiem_soat" and p.measured]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]


def _clip_window(video: OverheadVideo, window) -> tuple[float, float] | None:
    if window is not None:
        return window
    if video.clock == "perf_counter":
        duration = video.rows[-1][1] - video.rows[0][1]
    else:
        import cv2
        cap = cv2.VideoCapture(str(video.path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
        duration = max(0.0, (len(video) - 1) / fps)
    if duration - 2 * TRIM_S <= 0:
        return None
    return TRIM_S, duration - TRIM_S


@dataclass
class Tc1Report:
    record: dict
    path: Path | None = None
    sha256: str | None = None

    @property
    def kind(self) -> str:
        return self.record["kind"]

    @property
    def synthetic(self) -> bool:
        return bool(self.record["synthetic"])

    @property
    def date(self) -> str:
        return self.record["date"]

    @property
    def accuracy(self) -> dict:
        return self.record["accuracy"]

    @property
    def requirements(self) -> dict:
        return self.record["requirements"]

    @property
    def floor_sha256(self) -> str | None:
        return self.record["floor"].get("sha256")

    @property
    def markers_sha256(self) -> str | None:
        return self.record["markers"].get("sha256")

    @property
    def detector(self) -> dict:
        return self.record["detector"]


def usable_for(accuracy: dict, thresholds, cfg) -> list[dict]:
    """R1 với độ chính xác này dùng được cho kiểm nào (quy tắc 3, ngưỡng / reference_ratio). Chỉ báo, không quyết."""
    from autopark.evaluation.score_run import LIMIT_PARAMS, footprint_error

    ratio = thresholds.reference_ratio
    pos, yaw = accuracy.get("pos_max_m"), accuracy.get("yaw_max_deg")
    known = pos is not None and yaw is not None
    out = []

    def add(check, kind, limit, needs, value, unit, why=""):
        ok = None if value is None or needs is None else bool(value <= needs + 1e-12)
        out.append({"check": check, "kind": kind, "limit": limit, "needs": needs, "value": value, "unit": unit,
                    "ok": ok, "why": why or (f"tham chiếu ≤ {limit:g} {unit} / {ratio:g}" if needs is not None else "")})

    for code in POSITION_CHECKS:
        if code in thresholds.limits:
            name = LIMIT_PARAMS[code][0]
            limit = thresholds.limit(code, name) / 100.0
            add(code, "pos", limit, limit / ratio, pos, "m")
    if "N-D2" in thresholds.limits:
        limit = thresholds.limit("N-D2", "max_deg")
        add("N-D2", "yaw", limit, limit / ratio, yaw, "°")
    fp = footprint_error(cfg, pos, math.radians(yaw)) if known else None
    if "N-D5" in thresholds.limits:
        limit = thresholds.limit("N-D5", "min_cm") / 100.0
        add("N-D5", "footprint", limit, limit / ratio, fp, "m",
            "vị trí + tầm tới góc thân xe × sin(hướng) ≤ khoảng hở / " + f"{ratio:g} (như score_run)")
    out.append({"check": "N-D3", "kind": "footprint", "limit": None, "needs": None, "value": fp, "unit": "m",
                "ok": None, "why": "N-D3 (trong ô) không có ngưỡng số: chỉ báo sai số góc thân xe"})
    for code, pos_limit, yaw_limit in NGUONG_L:
        parts, ok = [], []
        if pos_limit is not None:
            parts.append(f"vị trí ≤ {pos_limit * 100:g} cm / {ratio:g}")
            ok.append(None if pos is None else pos <= pos_limit / ratio + 1e-12)
        if yaw_limit is not None:
            parts.append(f"hướng ≤ {yaw_limit:g}° / {ratio:g}")
            ok.append(None if yaw is None else yaw <= yaw_limit / ratio + 1e-12)
        out.append({"check": code, "kind": "pos+yaw" if len(parts) == 2 else ("pos" if pos_limit else "yaw"),
                    "limit": {"pos_m": pos_limit, "yaw_deg": yaw_limit},
                    "needs": {"pos_m": None if pos_limit is None else pos_limit / ratio,
                              "yaw_deg": None if yaw_limit is None else yaw_limit / ratio},
                    "value": {"pos_m": pos, "yaw_deg": yaw}, "unit": "m, °",
                    "ok": None if None in ok else all(ok),
                    "why": "; ".join(parts) + " (bảng N-L của docs/NGUONG_NGHIEM_THU_DE_XUAT.md)"})
    return out


def check_tc1_inputs(fit: FloorFit, car: VehicleMarkers) -> None:
    """Từ chối (OverheadError) đầu vào TC-1 không dùng được: khớp mặt sàn chưa đạt (ok: false), cấu hình marker thật
    chưa đo (measured: false, số GIẢ ĐỊNH; bộ thử tổng hợp thì nhận). Dòng lệnh `tc1`, `run_tc1` và thẻ TC-1 của giao
    diện dùng chung (sửa 02/10/2026: trước đây chỉ dòng lệnh kiểm)."""
    if not fit.ok:
        raise OverheadError(f"kết quả khớp mặt sàn {fit.path or ''} chưa đạt ({'; '.join(fit.reasons)}): khớp lại "
                            f"trước TC-1")
    if not car.measured and not car.synthetic:
        raise OverheadError(f"cấu hình marker {car.path or car.name} có measured: false: đo xe giả rồi ghi bản _v1 "
                            f"trước TC-1")


def _measure_pose(pose: Tc1Pose, fit: FloorFit, car: VehicleMarkers, params: DetectorParams, min_valid: int,
                  stop=None) -> dict:
    """Trích R1 của một tư thế; trả mục của biên bản (khóa `excluded` khi bị loại). Đoạn ghi có JSON của bộ ghi mà cờ
    TỔNG HỢP khác khớp mặt sàn thì từ chối (như `check_track_inputs`). TC-1 tĩnh chỉ dùng thời gian để cắt cửa sổ, nên
    nhận video chỉ có số khung/s danh định (ghi chú vào mục của tư thế)."""
    entry = {"tu_the": pose.name, "video": str(pose.video), "line": pose.line}
    video = OverheadVideo(pose.video, allow_nominal_fps=True)
    if video.meta and video.synthetic != bool(fit.synthetic):
        raise OverheadError(f"tư thế {pose.name}: không trộn dữ liệu TỔNG HỢP với dữ liệu thật (khớp mặt sàn, cấu hình "
                            f"marker, video {pose.video.name} có cờ synthetic {video.synthetic})")
    entry["sha256"] = video.sha256()
    if tuple(video.size) != tuple(fit.intr.size):
        raise OverheadError(f"tư thế {pose.name}: video cỡ {video.size}, khớp mặt sàn ở {fit.intr.size}")
    window = _clip_window(video, pose.window)
    entry["window_s"] = list(window) if window else None
    entry["recording"] = {k: (video.meta or {}).get(k) for k in ("codec", "quality", "size", "t_wall_start")}
    if window is None:
        entry["excluded"] = f"đoạn ghi quá ngắn để bỏ {TRIM_S:g} s mỗi đầu: ghi 5–10 s mỗi tư thế (KICH_BAN 3.7)"
        return entry
    result = extract_track(video, fit, car, TrackOptions(2, window), params=params, stop=stop, clock=video.clock)
    valid = [f for f in result.frames if f.valid]
    entry.update({"frames": len(result.frames), "valid": len(valid),
                  "two_marker_fraction": (sum(f.n_markers == 2 for f in valid) / len(valid)) if valid else 0.0,
                  "camera_shift": result.shift_stats, "notes": list(result.notes) + list(video.notes)})
    if len(valid) < min_valid:
        reasons = sorted({f.reason for f in result.frames if not f.valid and f.reason})
        entry["excluded"] = (f"chỉ {len(valid)} khung hợp lệ (cần ≥ {min_valid})"
                             + (f": {'; '.join(reasons[:3])}" if reasons else ""))
        return entry
    r1, spread = static_pose(valid)
    entry["r1"] = {"x_m": r1.x, "y_m": r1.y, "yaw_deg": math.degrees(r1.yaw)}
    entry["spread"] = spread
    entry["_r1"] = r1
    return entry


def run_tc1(poses: list[Tc1Pose], fit: FloorFit, car: VehicleMarkers, *, kind: str = "full", compare=(),
            thresholds_path=None, vehicle_path=None, progress=None, stop=None, poses_path=None,
            min_valid_frames: int = MIN_VALID_FRAMES) -> Tc1Report:
    """Chạy TC-1 trên các tư thế; trả biên bản (chưa ghi). Từ chối như dòng lệnh (`check_tc1_inputs`) trước khi đọc
    video nào."""
    from autopark.evaluation.score_run import DEFAULT_THRESHOLDS, load_thresholds
    from autopark.storage.scenario_store import load_vehicle_config

    if kind not in KINDS:
        raise OverheadError(f"kind {kind!r}: cần full hoặc day")
    check_tc1_inputs(fit, car)
    if not car.r2_points:
        raise OverheadError("cấu hình marker thiếu r2_points_m (hai đầu thước của xe giả trong hệ xe): TC-1 cần nó")
    if car.dictionary != fit.detector.dictionary:
        raise OverheadError(f"cấu hình marker dùng {car.dictionary}, khớp mặt sàn dùng {fit.detector.dictionary}")
    if bool(fit.synthetic) != bool(car.synthetic):
        raise OverheadError("không trộn dữ liệu TỔNG HỢP với dữ liệu thật (khớp mặt sàn và cấu hình marker)")
    thresholds_path = Path(thresholds_path or DEFAULT_THRESHOLDS)
    vehicle_path = Path(vehicle_path or DEFAULT_VEHICLE)
    try:
        thresholds = load_thresholds(thresholds_path)
        cfg = load_vehicle_config(vehicle_path)
    except (OSError, ValueError, KeyError) as exc:
        raise OverheadError(f"không đọc được tệp ngưỡng/cấu hình xe: {exc}") from exc
    entries = []
    for k, pose in enumerate(poses):
        if stop is not None and stop.is_set():
            break
        entry = _measure_pose(pose, fit, car, fit.detector, min_valid_frames, stop)
        if "excluded" not in entry:
            r2, ruler_err = r2_pose(pose.rear, pose.front, car)
            r1 = entry.pop("_r1")
            notes = entry["notes"]
            if ruler_err > RULER_TOLERANCE_M:
                notes.append(f"hai đầu thước đo cách nhau lệch chiều dài thước {ruler_err * 1000:.1f} mm "
                             f"(> {RULER_TOLERANCE_M * 1000:.0f} mm): kiểm lại số đo thước")
            centre_check = None if pose.centre is None else math.hypot(pose.centre[0] - r2.x, pose.centre[1] - r2.y)
            entry["r2"] = {"x_m": r2.x, "y_m": r2.y, "yaw_deg": math.degrees(r2.yaw),
                           "ruler_m": math.dist(pose.rear, pose.front), "ruler_err_m": ruler_err,
                           "centre_check_m": centre_check}
            entry["err_pos_m"] = math.hypot(r1.x - r2.x, r1.y - r2.y)
            entry["err_yaw_deg"] = abs(math.degrees(wrap_angle(r1.yaw - r2.yaw)))
        entries.append(entry)
        if progress is not None:
            progress(k + 1, len(poses), entry)
    used = [e for e in entries if "excluded" not in e]
    pos_errs = [e["err_pos_m"] for e in used]
    yaw_errs = [e["err_yaw_deg"] for e in used]
    headings = distinct_headings([e["r2"]["yaw_deg"] for e in used])
    corners = hull_corners(fit)
    covered = [any(math.hypot(e["r2"]["x_m"] - cx, e["r2"]["y_m"] - cy) <= CORNER_RADIUS_M for e in used)
               for cx, cy in corners]
    summary = {"n_poses": len(used), "n_excluded": len(entries) - len(used), "headings": len(headings),
               "headings_deg": headings, "corners": [list(c) for c in corners], "corners_covered": covered,
               "pos_median_m": statistics.median(pos_errs) if used else None,
               "pos_max_m": max(pos_errs) if used else None,
               "yaw_median_deg": statistics.median(yaw_errs) if used else None,
               "yaw_max_deg": max(yaw_errs) if used else None,
               "spread_pos_p95_m": max(e["spread"]["pos_p95_m"] for e in used) if used else None,
               "spread_yaw_p95_deg": max(e["spread"]["yaw_p95_deg"] for e in used) if used else None}
    missing = []
    if len(used) < MIN_POSES[kind]:
        missing.append(f"cần ≥ {MIN_POSES[kind]} tư thế dùng được, có {len(used)}")
    if kind == "full":
        if len(headings) < MIN_HEADINGS:
            missing.append(f"cần ≥ {MIN_HEADINGS} hướng cách nhau ≥ {HEADING_GAP_DEG:g}°, có {len(headings)}")
        for (cx, cy), ok in zip(corners, covered):
            if not ok:
                missing.append(f"thiếu tư thế cách góc ({round(cx, 2) + 0.0:.2f}, {round(cy, 2) + 0.0:.2f}) ≤ "
                               f"{CORNER_RADIUS_M:g} m")
    missing += [f"tư thế {e['tu_the']} bị loại: {e['excluded']}" for e in entries if "excluded" in e]
    met = len(used) >= MIN_POSES[kind] and not [m for m in missing if not m.startswith("tư thế ")]
    dates = sorted({iso_from_vn(p.date) for p in poses})
    clip_dates = sorted({str(e["recording"]["t_wall_start"])[:10] for e in entries
                         if e.get("recording", {}).get("t_wall_start")})
    date = clip_dates[0] if len(clip_dates) == 1 else dates[-1]
    notes = list(NOTES)
    if clip_dates and dates != clip_dates:
        notes.append(f"ngày ghi trong bảng tư thế {[vn_from_iso(d) for d in dates]} khác ngày của các đoạn ghi "
                     f"{[vn_from_iso(d) for d in clip_dates]}: lấy {vn_from_iso(date)}")
    accuracy = {"pos_max_m": summary["pos_max_m"], "yaw_max_deg": summary["yaw_max_deg"],
                "pos_median_m": summary["pos_median_m"], "yaw_median_deg": summary["yaw_median_deg"], "source": ""}
    alternatives = {}
    for method in [m for m in compare if m]:
        params = replace(fit.detector, refine=method)
        errs_p, errs_y, n = [], [], 0
        for pose in poses:
            if stop is not None and stop.is_set():
                break
            entry = _measure_pose(pose, fit, car, params, min_valid_frames, stop)
            if "excluded" in entry:
                continue
            r2, _ = r2_pose(pose.rear, pose.front, car)
            r1 = entry["_r1"]
            errs_p.append(math.hypot(r1.x - r2.x, r1.y - r2.y))
            errs_y.append(abs(math.degrees(wrap_angle(r1.yaw - r2.yaw))))
            n += 1
        alternatives[method] = {"n_poses": n, "pos_max_m": max(errs_p) if errs_p else None,
                                "yaw_max_deg": max(errs_y) if errs_y else None,
                                "pos_median_m": statistics.median(errs_p) if errs_p else None,
                                "yaw_median_deg": statistics.median(errs_y) if errs_y else None}
    first_rec = next((e["recording"] for e in entries if e.get("recording")), {})
    for e in entries:
        e.pop("_r1", None)
    record = {
        "format": TC1_FORMAT, "kind": kind, "synthetic": bool(fit.synthetic), "date": date,
        "created_local": datetime.now().isoformat(timespec="seconds"), "tool": "autopark.evaluation.overhead_ref tc1",
        "git_commit": lidar_recording.git_commit(), "software": software(),
        "floor": {"path": str(fit.path) if fit.path else None, "sha256": fit.sha256,
                  "camera_height_m": fit.camera.height_m, "check_max_m": fit.check_max_m},
        "markers": {**car.summary()}, "detector": fit.detector.to_dict(),
        "recording": {"codec": first_rec.get("codec"), "quality": first_rec.get("quality"),
                      "size": first_rec.get("size")},
        "poses_input": {"path": str(poses_path) if poses_path else None,
                        "sha256": file_sha256(poses_path) if poses_path else None,
                        "rows": [p.to_dict() for p in poses]},
        "poses": entries, "summary": summary, "accuracy": accuracy,
        "requirements": {"min_poses": MIN_POSES[kind], "min_headings": MIN_HEADINGS if kind == "full" else None,
                         "heading_gap_deg": HEADING_GAP_DEG, "corner_radius_m": CORNER_RADIUS_M if kind == "full"
                         else None, "met": met, "missing": missing,
                         "status": "ĐỦ" if met else "CHƯA ĐỦ: " + "; ".join(missing)},
        "alternatives": alternatives,
        "usable_for": usable_for(accuracy, thresholds, cfg),
        "thresholds": {"path": str(thresholds.path), "sha256": thresholds.sha256, "status": thresholds.status,
                       "reference_ratio": thresholds.reference_ratio, "tc1": TC1_THRESHOLDS},
        "vehicle": {"path": str(vehicle_path), "sha256": file_sha256(vehicle_path)},
        "notes": ([SYNTHETIC_LABEL] if fit.synthetic else []) + notes,
    }
    return Tc1Report(_jsonable_record(record))


def _jsonable_record(record: dict) -> dict:
    from autopark.evaluation.overhead_ref import _jsonable

    return _jsonable(record)


def accuracy_source(record: dict, path: Path | None) -> str:
    n = record["summary"]["n_poses"]
    return (f"TC-1 {KIND_LABELS[record['kind']]} {vn_from_iso(record['date'])} {path.name if path else '(chưa lưu)'}, "
            f"{n} tư thế, cận trên" + (f", {SYNTHETIC_LABEL}" if record["synthetic"] else ""))


def save_tc1(path, report: Tc1Report, overwrite: bool = False) -> Path:
    path = check_output_path(path, report.synthetic, overwrite)
    report.record["accuracy"]["source"] = accuracy_source(report.record, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_existing(path)
    atomic_write_json(path, report.record)
    report.path, report.sha256 = path, file_sha256(path)
    return path


TC1_REQUIRED = ("format", "kind", "synthetic", "date", "floor", "markers", "detector", "poses", "summary", "accuracy",
                "requirements")


def load_tc1(path) -> Tc1Report:
    """Đọc chặt một biên bản TC-1 (kèm SHA-256 của tệp)."""
    path = Path(path)
    try:
        raw = path.read_bytes()
        record = json.loads(raw.decode("utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise OverheadError(f"không đọc được biên bản TC-1 {path}: {exc}") from exc
    if not isinstance(record, dict) or record.get("format") != TC1_FORMAT:
        raise OverheadError(f"{path}: không phải biên bản {TC1_FORMAT}")
    lacking = [k for k in TC1_REQUIRED if k not in record]
    if lacking or record["kind"] not in KINDS:
        raise OverheadError(f"{path}: thiếu khóa {lacking} hoặc kind sai")
    if set(record["accuracy"]) != set(ACCURACY_KEYS):
        raise OverheadError(f"{path}: accuracy phải có đúng các khóa {ACCURACY_KEYS}")
    return Tc1Report(record, path, hashlib.sha256(raw).hexdigest())


def _null(why: str, notes: list[str]) -> tuple[ReferenceAccuracy, list[str]]:
    return ReferenceAccuracy(None, None, why), notes + [f"độ chính xác null: {why}"]


def accuracy_for_track(fit: FloorFit, car: VehicleMarkers, video_date: str, tc1: Tc1Report | None,
                       tc1_day: Tc1Report | None, allow: bool = False) -> tuple[ReferenceAccuracy, list[str]]:
    """Luật chép độ chính xác TC-1 sang một lần chạy (mục 4.6 thiết kế T4; thà null còn hơn lạc quan):

    - không có TC-1 đầy đủ → null ('chưa làm TC-1'), T5 ghi "không kiểm được";
    - mỗi biên bản phải cùng SHA-256 tệp khớp mặt sàn, cùng bộ dò, cùng cờ tổng hợp, đủ yêu cầu (trừ khi `allow` =
      --tc1-chua-du, có ghi chú);
    - cấu hình marker cùng SHA-256 với biên bản đầy đủ; không thì cần TC-1 rút gọn trong ngày cùng cấu hình, z_m lệch
      biên bản đầy đủ ≤ 5 mm;
    - phải có một biên bản cùng NGÀY với video (KICH_BAN 3.7 bước 5);
    - kết quả = lớn nhất từng trường trên các biên bản được nhận."""
    notes: list[str] = []
    if tc1 is None:
        return ReferenceAccuracy(None, None, "chưa làm TC-1"), [
            "chưa có biên bản TC-1 (--tc1): độ chính xác null, T5 ghi 'không kiểm được' (quy tắc 3)"]
    if tc1.kind != "full":
        return _null("--tc1 phải là biên bản TC-1 đầy đủ (kind full); bản rút gọn dùng --tc1-day", notes)
    reports = [r for r in (tc1, tc1_day) if r is not None]
    for r in reports:
        name = r.path.name if r.path else "TC-1"
        if r.floor_sha256 != fit.sha256:
            return _null(f"{name} làm với tệp khớp mặt sàn khác (SHA-256): làm lại TC-1 sau khi khớp lại mặt sàn", notes)
        if r.detector != fit.detector.to_dict():
            return _null(f"{name} dùng bộ dò khác ({r.detector}) với khớp mặt sàn ({fit.detector.to_dict()})", notes)
        if r.synthetic != bool(fit.synthetic):
            return _null(f"{name} có cờ tổng hợp khác tệp khớp mặt sàn", notes)
        if not r.requirements.get("met"):
            if not allow:
                return _null(f"{name} chưa đủ yêu cầu ({'; '.join(r.requirements.get('missing', []))}): thêm tư thế, "
                             f"hoặc --tc1-chua-du", notes)
            notes.append(f"chấp nhận {name} thiếu yêu cầu (--tc1-chua-du): {'; '.join(r.requirements.get('missing', []))}")
        if r.accuracy.get("pos_max_m") is None or r.accuracy.get("yaw_max_deg") is None:
            return _null(f"{name} không có số đo (không tư thế nào dùng được)", notes)
    if tc1.markers_sha256 != car.sha256:
        if tc1_day is None or tc1_day.markers_sha256 != car.sha256:
            return _null("cấu hình marker khác lúc làm TC-1 đầy đủ: cần TC-1 rút gọn trong ngày (--tc1-day) với đúng "
                         "cấu hình này", notes)
        z_full, z_day = tc1.record["markers"].get("z_m") or [], tc1_day.record["markers"].get("z_m") or []
        if len(z_full) != len(z_day) or any(abs(a - b) > Z_MATCH_M + 1e-12 for a, b in zip(z_full, z_day)):
            return _null(f"độ cao marker (z_m {z_day}) khác TC-1 đầy đủ ({z_full}) quá {Z_MATCH_M * 1000:.0f} mm: làm "
                         f"lại TC-1 đầy đủ", notes)
        notes.append("cấu hình marker khác TC-1 đầy đủ: dùng TC-1 rút gọn trong ngày cùng cấu hình")
    if not any(r.date == video_date for r in reports):
        return _null(f"không có TC-1 cùng ngày với video ({vn_from_iso(video_date)}; TC-1: "
                     f"{', '.join(vn_from_iso(r.date) for r in reports)}): làm TC-1 rút gọn đầu ngày (KICH_BAN 3.7 "
                     f"bước 5)", notes)

    def worst(key):
        values = [r.accuracy.get(key) for r in reports if r.accuracy.get(key) is not None]
        return max(values) if values else None
    source = " + ".join(r.accuracy.get("source") or "TC-1" for r in reports)
    return ReferenceAccuracy(worst("pos_max_m"), worst("yaw_max_deg"), source, worst("pos_median_m"),
                             worst("yaw_median_deg")), notes


def summary_lines(report: Tc1Report) -> list[str]:
    r, s, acc = report.record, report.record["summary"], report.accuracy
    lines = [("TỔNG HỢP — KHÔNG PHẢI SỐ ĐO. " if report.synthetic else "")
             + f"TC-1 {KIND_LABELS[r['kind']]} ngày {vn_from_iso(r['date'])}: {s['n_poses']} tư thế dùng được, "
             f"{s['headings']} hướng, góc sa bàn {sum(s['corners_covered'])}/4"]
    if acc.get("pos_max_m") is not None:
        lines.append(f"Vị trí: trung vị {acc['pos_median_m'] * 1000:.1f} mm, lớn nhất {acc['pos_max_m'] * 1000:.1f} mm · "
                     f"Hướng: trung vị {acc['yaw_median_deg']:.2f}°, lớn nhất {acc['yaw_max_deg']:.2f}° · độ tản p95 "
                     f"{(s['spread_pos_p95_m'] or 0) * 1000:.1f} mm, {s['spread_yaw_p95_deg'] or 0:.2f}° (cận trên)")
    ok = [u["check"] for u in r.get("usable_for", []) if u["ok"] is True]
    bad = [u["check"] for u in r.get("usable_for", []) if u["ok"] is False]
    lines.append(f"Dùng được cho: {', '.join(ok) or '—'} · KHÔNG dùng được cho: {', '.join(bad) or '—'} ({PROPOSED})")
    req = r["requirements"]
    lines.append(f"Yêu cầu: {req['status']}")
    for e in r["poses"]:
        if "excluded" in e:
            lines.append(f"  {e['tu_the']}: LOẠI — {e['excluded']}")
        else:
            lines.append(f"  {e['tu_the']}: vị trí {e['err_pos_m'] * 1000:.1f} mm, hướng {e['err_yaw_deg']:.2f}°, "
                         f"{e['valid']}/{e['frames']} khung, tản p95 {e['spread']['pos_p95_m'] * 1000:.1f} mm")
    for method, alt in r.get("alternatives", {}).items():
        if alt.get("pos_max_m") is not None:
            lines.append(f"  so sánh tinh chỉnh '{method}': vị trí lớn nhất {alt['pos_max_m'] * 1000:.1f} mm, hướng "
                         f"{alt['yaw_max_deg']:.2f}° ({alt['n_poses']} tư thế)")
    return lines


def run_cli(args) -> int:
    """Lệnh `overhead_ref tc1`."""
    fit = load_floor_fit(args.floor)
    car = load_vehicle_markers(args.markers)
    check_tc1_inputs(fit, car)                  # từ chối sớm, trước khi đọc bảng tư thế (run_tc1 kiểm lại)
    poses = read_tc1_poses(args.poses)
    out = args.out or (PROJECT / "runs" / "tren_cao" / datetime.now().strftime("%Y%m%d")
                       / f"tc1_{datetime.now():%Y%m%d_%H%M}.json")
    check_output_path(out, fit.synthetic, args.overwrite)
    compare = [m.strip() for m in args.compare.split(",") if m.strip()]
    for m in compare:
        DetectorParams(fit.detector.dictionary, m)          # kiểm tên sớm
    report = run_tc1(poses, fit, car, kind=args.kind, compare=compare, thresholds_path=args.thresholds,
                     vehicle_path=args.vehicle, poses_path=args.poses, min_valid_frames=args.min_frames,
                     progress=lambda k, n, e: print(f"  tư thế {k}/{n}: {e['tu_the']}"))
    path = save_tc1(out, report, args.overwrite)
    for line in summary_lines(report):
        print(line)
    print(f"đã ghi {path}")
    return EXIT_OK if report.requirements["met"] else EXIT_QUALITY
