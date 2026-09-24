"""BEV (nhìn từ trên xuống) chiếm chỗ từ kết quả AI của nhiều camera — kế hoạch giai đoạn 2, bước 7.

    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.bev synthetic
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.bev snapshot runs/rig_snapshots/<ngày_giờ>
    .\\.venv-train\\Scripts\\python.exe -X utf8 -m autopark.perception.bev woodscape --image datasets/training/woodscape/rgb_images/00000_FV.png --checkpoint runs/ai_woodscape_rtx4000_v1/best.pt

Hướng dẫn, quy tắc và giới hạn: docs/BEV.md. Mỗi lệnh viết trên một dòng để dán được vào PowerShell.

**Đầu vào mỗi camera:** bản đồ xác suất P(BLOCKED) (độ phân giải bất kỳ, nhưng cùng tỉ lệ khung với ảnh đã hiệu chuẩn;
bàn thử ghi `prob_blocked_p<cổng>.png` = P×255 ở cỡ hiển thị) + một `CameraCalibration` (nội tham + ngoại tham trong
hệ xe: x trước, y trái, z lên, gốc trên mặt sàn dưới tâm trục sau). Mọi camera dùng chung một `GridSpec`.

**Quy tắc:**
1. Xác suất → bằng chứng theo HAI ngưỡng: p ≤ t_free → FREE; p ≥ t_blocked → OCCUPIED; ở giữa → không chắc chắn
   (UNKNOWN). Pixel ngoài ROI hoặc NaN → không có bằng chứng. Xác suất được phóng về cỡ ảnh đã hiệu chuẩn TRƯỚC khi
   so ngưỡng (nội suy tuyến tính khi phóng to, INTER_AREA khi thu nhỏ); tệp PNG lưu P×255 nên lệch ≤ 1/510 quanh ngưỡng.
2. Chiếu xuống mặt sàn bằng `costmap.project_labels` (không sửa mô-đun đó): tâm ô → pixel; theo từng phương vị nhìn từ
   camera, mọi ô sau ô OCCUPIED đầu tiên là UNKNOWN (che khuất); ô xa hơn `max_range` là UNKNOWN. Chiếu trên lưới mịn
   hơn `supersample` lần rồi gộp BẢO THỦ: ô là OCCUPIED nếu có ô con OCCUPIED, FREE chỉ khi MỌI ô con FREE.
   `project_labels` chỉ đọc pixel ở tâm ô con, nên thêm một lượt ngược (pixel → sàn): ô con có tâm hoặc góc của một pixel
   BLOCKED/không chắc rơi vào thì KHÔNG được FREE ở camera đó (thành UNKNOWN, không thành OCCUPIED) — vật mảnh nằm giữa
   các tâm ô con không còn để ô của nó FREE.
3. Hợp nhất các camera: OCCUPIED nếu có camera nói OCCUPIED; FREE chỉ khi ít nhất một camera thấy FREE chắc chắn và
   không camera nào nói OCCUPIED; còn lại UNKNOWN. Ô dưới thân xe luôn UNKNOWN. Camera thiếu dữ liệu không góp gì: vùng
   chỉ nó thấy giữ UNKNOWN, không bao giờ mặc định FREE.
4. Mỗi ô giữ nguồn gốc (bitmask theo thứ tự camera): camera nào thấy nó (`seen_by`), nói FREE (`free_by`), nói
   OCCUPIED (`occupied_by`), có nó trong vùng hình học — trường nhìn, tầm, ROI — kể cả khi bị che (`in_view_by`). Ô
   UNKNOWN được phân loại: không chắc chắn (có camera thấy nhưng không đủ chắc, hoặc chỉ thấy một phần ô), bị che,
   ngoài tầm nhìn, dưới thân xe.

**Giả định và giới hạn** (chi tiết ở docs/BEV.md): mặt sàn phẳng z = 0 trong hệ xe; phép chiếu chỉ đúng cho điểm
thuộc mặt sàn. Pixel của vật cao (mặt bên, nóc) chiếu xuống sàn sẽ rơi XA hơn chân vật; quy tắc che khuất cắt phần đó
thành UNKNOWN nên chỉ phía chân vật hướng về camera là OCCUPIED. Đó KHÔNG phải footprint chính xác: vật nhô ra (mặt bàn,
cản xe) hay chân vật bị che vẫn lệch. Sai số hiệu chuẩn, sàn nghiêng và lỗi của mô hình AI đều đi thẳng vào lưới này.

**Tình trạng 24/09/2026:** chưa có camera nào được hiệu chuẩn (`calibration/cam_p*.json` chưa có), ngoại tham trong
`configs/rig/camera_rig_extrinsics_v0.json` là GIẢ ĐỊNH — CHƯA ĐO, chưa có mặt nạ ROI cho camera dự án. Lệnh `snapshot`
vì vậy từ chối chạy trên bộ ảnh thật; chỉ có bài tổng hợp và bài trên ảnh WoodScape (hiệu chuẩn của Valeo). Mô hình AI
chưa từng được chấm trên ảnh sa bàn, và giấy phép WoodScape chưa được chốt cho việc nối AI vào costmap/lập đường
(docs/GIAY_PHEP_DU_LIEU.md): costmap ra đây chỉ để kiểm tọa độ và quy tắc.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from functools import lru_cache
import json
import math
from pathlib import Path
import sys
import time
import unicodedata
import zipfile

import cv2
import numpy as np

from autopark.domain.sensors import Costmap, SourceStamp
from autopark.video.sources import bottom_repeat_share, torn_bands, truncated_rows

from .calibration import CameraCalibration, Extrinsics, FisheyeIntrinsics, load_woodscape_calibration
from .costmap import FREE, OCCUPIED, UNKNOWN, GridSpec, costmap_to_dict, project_labels, to_costmap
from .paths import PROJECT, atomic_write_json, utc_now

# ---- tham số mặc định ------------------------------------------------------------------------------------------------
# t_free = 0,15 là ngưỡng thiên về an toàn chọn trên val WoodScape theo F2 (HUAN_LUYEN.md mục 10): chỉ pixel mà mô hình
# cho P(BLOCKED) ≤ 0,15 mới được gọi là trống. t_blocked = 0,50 là argmax. Cả hai CHƯA kiểm trên ảnh sa bàn.
DEFAULT_T_FREE = 0.15
DEFAULT_T_BLOCKED = 0.50
DEFAULT_SUPERSAMPLE = 2
DEFAULT_AZIMUTH_BIN_DEG = 0.5
# Lưới 6 × 6 m, ô 5 cm quanh gốc hệ xe; tầm 2 m. Tính trên rig giả định (camera trước cao 0,12 m, chúc 30°, ống danh
# định 130° chéo): dọc hướng nhìn một pixel phủ ≈ 2,4 cm mặt sàn theo bán kính ở 1 m, 5,4 cm ở 1,5 m, 9,5 cm ở 2 m, 21 cm
# ở 3 m — quá 2 m một pixel quyết định nhiều ô 5 cm. Đây là số TÍNH, chưa đo trên camera thật (docs/BEV.md mục 4).
RIG_GRID = (-3.0, 3.0, -3.0, 3.0, 0.05)
RIG_MAX_RANGE = 2.0
WOODSCAPE_GRID = (-10.0, 15.0, -10.0, 10.0, 0.1)     # như costmap.py
WOODSCAPE_MAX_RANGE = 12.0
DEFAULT_EXTRINSICS = PROJECT / "configs/rig/camera_rig_extrinsics_v0.json"
DEFAULT_CALIBRATION_DIR = PROJECT / "calibration"
DEFAULT_OUT_ROOT = PROJECT / "runs/bev"
EXTRINSICS_FORMAT = "autopark.camera_rig_extrinsics/0"
MAX_CAMERAS = 16                    # bitmask uint16
# bộ ảnh bàn thử: camera lệch quá mức này so với trung vị stamp của các camera dùng được thì bị bỏ (vùng của nó UNKNOWN).
# Độ lệch trong bộ đo được 23/09 (u01): trung vị 15,0 ms, p95 24,1 ms; ngưỡng chờ camera chậm ≈ 62 ms.
MAX_SKEW_MS = 100.0
# như labels.BOTTOM_REPEAT_LIMIT: khung sạch ≤ 0,13, đáy bị bộ giải mã tô ≈ 1. Khung hỏng mà tới AI thì vùng vân xám bị
# gọi gần hết là FREE (GIAI_DOAN_2_BAN_THU.md) — lỗi theo hướng không an toàn, nên camera đó bị bỏ khỏi BEV.
BOTTOM_REPEAT_LIMIT = 0.2

LABEL_FREE, LABEL_BLOCKED, LABEL_NONE = 0, 1, 255

# phân loại ô để thống kê và vẽ (costmap chỉ có -1/0/1; mọi loại UNKNOWN đều bị chặn khi lập đường)
CAT_FREE, CAT_OCCUPIED, CAT_UNCERTAIN, CAT_OCCLUDED, CAT_UNSEEN, CAT_EGO = 0, 1, 2, 3, 4, 5
CATEGORY_NAMES = {CAT_FREE: "free", CAT_OCCUPIED: "occupied", CAT_UNCERTAIN: "uncertain", CAT_OCCLUDED: "occluded",
                  CAT_UNSEEN: "unseen", CAT_EGO: "ego"}
CATEGORY_MEANING = {
    "free": "FREE: ít nhất một camera thấy trống chắc chắn (p ≤ t_free ở mọi ô con, không pixel BLOCKED/không chắc nào "
            "của camera đó rơi vào ô con), không camera nào nói OCCUPIED",
    "occupied": "OCCUPIED: ít nhất một camera có pixel p ≥ t_blocked chiếu vào ô (chỉ phần chân vật hướng về camera)",
    "uncertain": "UNKNOWN — có camera thấy ô nhưng không đủ chắc (t_free < p < t_blocked) hoặc chỉ thấy một phần ô",
    "occluded": "UNKNOWN — ô nằm trong trường nhìn/tầm/ROI của camera nhưng bị vật OCCUPIED gần hơn che",
    "unseen": "UNKNOWN — ngoài trường nhìn, quá tầm, ngoài ROI của mọi camera, hoặc camera thấy nó thiếu dữ liệu",
    "ego": "UNKNOWN — dưới thân xe (camera trên xe không nhìn được)",
}
CATEGORY_COLORS = {CAT_FREE: (0, 170, 0), CAT_OCCUPIED: (40, 40, 220), CAT_UNCERTAIN: (0, 150, 235),
                   CAT_OCCLUDED: (100, 100, 100), CAT_UNSEEN: (45, 45, 45), CAT_EGO: (150, 100, 40)}


class RigConfigError(RuntimeError):
    """Cấu hình/đầu vào không dùng được (thiếu nội tham, sai định dạng…): người dùng sửa được, báo rõ và dừng."""


# ---- ảnh ------------------------------------------------------------------------------------------------------------
def read_gray(path) -> np.ndarray:
    """Ảnh xám uint8; chịu được đường dẫn tiếng Việt (cv2.imread không đọc được trên Windows)."""
    try:
        data = np.fromfile(str(path), np.uint8)
    except OSError as exc:
        raise RigConfigError(f"không đọc được {path}: {exc}") from exc
    image = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RigConfigError(f"không giải mã được ảnh {path}")
    return image


def read_color(path) -> np.ndarray:
    try:
        image = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    except OSError as exc:
        raise RigConfigError(f"không đọc được {path}: {exc}") from exc
    if image is None:
        raise RigConfigError(f"không giải mã được ảnh {path}")
    return image


def write_image(path, image: np.ndarray) -> None:
    ok, buf = cv2.imencode(Path(path).suffix, image)       # imwrite hỏng trên đường dẫn tiếng Việt ở Windows
    if not ok:
        raise ValueError(f"không mã hóa được {path}")
    Path(path).write_bytes(buf.tobytes())


# ---- xác suất → bằng chứng -------------------------------------------------------------------------------------------
def check_thresholds(t_free: float, t_blocked: float) -> None:
    if not (0.0 <= t_free < t_blocked <= 1.0):
        raise ValueError(f"cần 0 ≤ t_free < t_blocked ≤ 1 (được t_free={t_free}, t_blocked={t_blocked})")


def as_probability(prob) -> np.ndarray:
    """uint8 (P×255, như prob_blocked_p*.png) hoặc số thực trong [0, 1] → float32 (H, W); NaN giữ nguyên."""
    a = np.asarray(prob)
    if a.ndim != 2:
        raise ValueError(f"bản đồ xác suất phải là ảnh một kênh (H, W), được {a.shape}")
    if a.dtype == np.uint8:
        return a.astype(np.float32) / 255.0
    a = a.astype(np.float32)
    finite = a[np.isfinite(a)]
    if finite.size and (finite.min() < 0.0 or finite.max() > 1.0):
        raise ValueError("xác suất số thực phải nằm trong [0, 1]")
    return a


def resize_probability(prob: np.ndarray, width: int, height: int, *, aspect_tolerance: float = 0.01) -> np.ndarray:
    """Phóng bản đồ xác suất về cỡ ảnh đã hiệu chuẩn. Tỉ lệ khung khác (ví dụ 16:9 so với 4:3) là mode khác: từ chối."""
    h, w = prob.shape
    if (w, h) == (width, height):
        return prob
    if abs((w / h) / (width / height) - 1.0) > aspect_tolerance:
        raise ValueError(f"bản đồ xác suất {w}×{h} khác tỉ lệ khung của hiệu chuẩn {width}×{height}: "
                         f"nhiều khả năng là mode camera khác, không dùng nội tham này được")
    interpolation = cv2.INTER_AREA if w > width else cv2.INTER_LINEAR
    return cv2.resize(prob.astype(np.float32), (width, height), interpolation=interpolation)


def evidence_labels(prob, t_free: float = DEFAULT_T_FREE, t_blocked: float = DEFAULT_T_BLOCKED,
                    roi: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """→ (nhãn uint8 cho project_labels: 0 FREE, 1 BLOCKED, 255 không có bằng chứng; mặt nạ pixel KHÔNG CHẮC CHẮN).

    Bằng ngưỡng: p == t_free là FREE, p == t_blocked là BLOCKED. Pixel ngoài ROI (roi == 0) hay NaN không thuộc loại nào.
    """
    check_thresholds(t_free, t_blocked)
    p = as_probability(prob)
    finite = np.isfinite(p)
    free = finite & (p <= t_free)
    blocked = finite & (p >= t_blocked)
    uncertain = finite & ~free & ~blocked
    if roi is not None:
        if roi.shape != p.shape:
            raise ValueError(f"ROI {roi.shape} khác cỡ bản đồ xác suất {p.shape}")
        inside = roi > 0
        free &= inside
        blocked &= inside
        uncertain &= inside
    labels = np.full(p.shape, LABEL_NONE, np.uint8)
    labels[free] = LABEL_FREE
    labels[blocked] = LABEL_BLOCKED
    return labels, uncertain


# ---- camera, xe ------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class EgoBox:
    """Hình chữ nhật thân xe trong hệ xe (đã nới lề); ô có tâm nằm trong là UNKNOWN."""
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    def contains(self, x, y) -> np.ndarray:
        x, y = np.asarray(x), np.asarray(y)
        return (x >= self.x_min) & (x <= self.x_max) & (y >= self.y_min) & (y <= self.y_max)

    def to_dict(self) -> dict:
        return {"x_min": self.x_min, "x_max": self.x_max, "y_min": self.y_min, "y_max": self.y_max}


@dataclass(frozen=True)
class BevCamera:
    name: str
    calibration: CameraCalibration
    roi: np.ndarray | None = field(default=None, compare=False)   # cỡ ảnh đã hiệu chuẩn, > 0 = dùng được
    extrinsics_measured: bool = False
    direction: str = ""
    intrinsics_source: str = ""
    roi_source: str | None = None
    acceptance_all_pass: bool | None = None      # tiêu chí ĐỀ XUẤT của fisheye_calib; None = không áp dụng

    def describe(self) -> dict:
        e = self.calibration.extrinsics
        return {"direction": self.direction, "extrinsics_measured": self.extrinsics_measured,
                "position_m": [round(float(t), 4) for t in e.translation],
                "quaternion_xyzw": [round(float(q), 6) for q in e.quaternion_xyzw],
                "optical_axis_vehicle": [round(float(a), 4) for a in e.rotation[:, 2]],
                "image_size": [self.calibration.intrinsics.width, self.calibration.intrinsics.height],
                "intrinsics_source": self.intrinsics_source, "roi": self.roi_source,
                "intrinsics_acceptance_all_pass": self.acceptance_all_pass}


def rig_rotation(yaw_deg: float, pitch_down_deg: float, roll_deg: float = 0.0) -> np.ndarray:
    """Ma trận quay camera → xe (cột = trục x phải, y xuống, z quang của camera trong hệ xe).

    yaw: hướng trục quang chiếu xuống sàn, từ +x, dương ngược chiều kim đồng hồ; pitch_down: chúc xuống dưới mặt phẳng
    ngang; roll: quay quanh trục quang, dương = trục phải của ảnh quay về phía trục xuống của ảnh.
    """
    yaw, pitch, roll = (math.radians(a) for a in (yaw_deg, pitch_down_deg, roll_deg))
    z = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), -math.sin(pitch)])
    x0 = np.array([math.sin(yaw), -math.cos(yaw), 0.0])          # phải của ảnh, nằm ngang khi roll = 0
    y0 = np.cross(z, x0)                                          # xuống của ảnh
    x = math.cos(roll) * x0 + math.sin(roll) * y0
    y = -math.sin(roll) * x0 + math.cos(roll) * y0
    return np.column_stack([x, y, z])


@dataclass(frozen=True)
class RigCameraPose:
    port: int
    direction: str
    extrinsics: Extrinsics
    measured: bool
    basis: str = ""


@dataclass(frozen=True)
class RigExtrinsics:
    path: str
    status: str
    cameras: dict
    ego: EgoBox | None
    notes: tuple = ()


def load_rig_extrinsics(path=DEFAULT_EXTRINSICS) -> RigExtrinsics:
    """Đọc configs/rig/camera_rig_extrinsics_*.json. Camera ghi `quaternion_xyzw` thì dùng thẳng, không thì dựng từ
    yaw/pitch/roll. `measured` phải ghi rõ true mới được tính là đã đo."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RigConfigError(f"không đọc được tệp ngoại tham {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != EXTRINSICS_FORMAT:
        found = data.get("format") if isinstance(data, dict) else type(data).__name__
        raise RigConfigError(f"{path}: không phải tệp {EXTRINSICS_FORMAT} (format={found!r})")
    if not isinstance(data.get("cameras") or {}, dict):
        raise RigConfigError(f"{path}: khóa cameras phải là đối tượng {{cổng: tư thế}}")
    cameras = {}
    for key, c in (data.get("cameras") or {}).items():
        try:
            port = int(key)
            position = tuple(float(t) for t in c["position_m"])
            if len(position) != 3 or not all(math.isfinite(t) for t in position):
                raise ValueError("position_m phải là 3 số hữu hạn")
            if position[2] <= 0:
                raise ValueError("camera phải ở trên mặt sàn (z > 0)")
            if "quaternion_xyzw" in c:
                extrinsics = Extrinsics(tuple(float(q) for q in c["quaternion_xyzw"]), position)
                extrinsics.rotation            # kiểm quaternion hợp lệ
            else:
                extrinsics = Extrinsics.from_matrix(
                    rig_rotation(float(c["yaw_deg"]), float(c["pitch_down_deg"]), float(c.get("roll_deg", 0.0))),
                    position)
        except (KeyError, TypeError, ValueError) as exc:
            raise RigConfigError(f"{path}: camera {key!r} sai định dạng: {exc}") from exc
        cameras[port] = RigCameraPose(port, str(c.get("direction", "")), extrinsics, c.get("measured") is True,
                                      str(c.get("basis", "")))
    if not cameras:
        raise RigConfigError(f"{path}: không có camera nào")
    ego = None
    vehicle = data.get("vehicle_assumed") or data.get("vehicle")
    if vehicle:
        try:
            length, width = float(vehicle["length_m"]), float(vehicle["width_m"])
            rear, margin = float(vehicle["rear_overhang_m"]), float(vehicle.get("ego_margin_m", 0.0))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise RigConfigError(f"{path}: khối vehicle_assumed sai định dạng (cần length_m, width_m, rear_overhang_m "
                                 f"là số; ego_margin_m tùy chọn): {exc!r}") from exc
        if not all(math.isfinite(a) for a in (length, width, rear, margin)) or length <= 0 or width <= 0 \
                or not 0.0 <= rear <= length or margin < 0:
            raise RigConfigError(f"{path}: khối vehicle_assumed vô lý (cần length_m, width_m > 0; 0 ≤ rear_overhang_m ≤ "
                                 f"length_m; ego_margin_m ≥ 0; được {length}, {width}, {rear}, {margin})")
        ego = EgoBox(-rear - margin, length - rear + margin, -width / 2 - margin, width / 2 + margin)
    return RigExtrinsics(str(path), str(data.get("status", "")), cameras, ego, tuple(data.get("ghi_chu", ())))


def load_rig(extrinsics_path=DEFAULT_EXTRINSICS, calibration_dir=DEFAULT_CALIBRATION_DIR,
             sizes: dict | None = None, *, roi_dir=None,
             skip_uncalibrated: bool = False) -> tuple[dict, RigExtrinsics, dict]:
    """Ghép nội tham `calibration/cam_p<cổng>[_<W>x<H>].json` (fisheye_calib.load_intrinsics) với ngoại tham của tệp rig.

    `sizes`: {cổng: (rộng, cao)} của khung — chỉ nạp các cổng này (None = mọi cổng trong tệp rig, cỡ 640×480). Thiếu tệp
    nội tham, hay tệp không nạp được, thì TỪ CHỐI (RigConfigError liệt kê mọi tệp) — không có nội tham giả định cho camera
    thật. `skip_uncalibrated=True`: bỏ camera đó (vùng của nó UNKNOWN) và ghi lý do.
    Trả (camera theo tên "p<cổng>", cấu hình rig, {tên: lý do} của camera bị bỏ).
    """
    from .fisheye_calib import DEFAULT_SIZE, default_output_path, load_calibration, load_intrinsics

    rig = load_rig_extrinsics(extrinsics_path)
    if sizes is None:
        sizes = {port: DEFAULT_SIZE for port in rig.cameras}
    cameras, skipped, errors = {}, {}, []
    for port in sorted(sizes):
        name = f"p{port}"
        pose = rig.cameras.get(port)
        if pose is None:
            skipped[name] = f"cổng {port} không có trong tệp ngoại tham {rig.path}"
            continue
        width, height = (int(s) for s in sizes[port])
        intr_path = default_output_path(port, (width, height), Path(calibration_dir))
        if not intr_path.exists():
            errors.append((name, f"chưa có tệp nội tham {intr_path} cho camera cổng {port} ({width}×{height}): hiệu chuẩn "
                                 f"trước (docs/HIEU_CHUAN_CAMERA.md); BEV không dùng nội tham giả định cho camera thật"))
            continue
        try:
            intrinsics = load_intrinsics(intr_path, width=width, height=height)
            acceptance = (load_calibration(intr_path).get("acceptance") or {}).get("all_pass")
        except (OSError, ValueError, KeyError) as exc:
            errors.append((name, f"không nạp được nội tham {intr_path}: {exc}"))
            continue
        roi, roi_source = None, None
        if roi_dir is not None:
            roi_path = Path(roi_dir) / f"roi_p{port}.png"
            if roi_path.exists():
                roi = read_gray(roi_path)
                if roi.shape != (height, width):
                    errors.append((name, f"ROI {roi_path} cỡ {roi.shape[1]}×{roi.shape[0]}, cần {width}×{height}"))
                    continue
                roi_source = str(roi_path)
        cameras[name] = BevCamera(name, CameraCalibration(name, intrinsics, pose.extrinsics), roi, pose.measured,
                                  pose.direction, str(intr_path), roi_source,
                                  None if acceptance is None else bool(acceptance))
    if errors and not skip_uncalibrated:
        raise RigConfigError("không dựng được rig camera:\n" + "\n".join(f"  - {msg}" for _, msg in errors))
    skipped.update({name: msg for name, msg in errors})
    return cameras, rig, skipped


# ---- chiếu một camera ------------------------------------------------------------------------------------------------
@dataclass
class CameraView:
    """Kết quả chiếu của MỘT camera. Mảng *_fine ở lưới mịn (supersample); `state` ở lưới ra, gộp riêng cho camera này
    (OCCUPIED nếu có ô con OCCUPIED, FREE nếu mọi ô con FREE) — để thống kê và kiểm, không dùng để hợp nhất."""
    name: str
    state_fine: np.ndarray     # int8 UNKNOWN / FREE / OCCUPIED
    seen_fine: np.ndarray      # bool: camera thật sự thấy ô con (FREE, OCCUPIED hoặc không chắc), không bị che
    in_view_fine: np.ndarray   # bool: ô con trong trường nhìn + tầm + ROI (chưa xét che khuất)
    state: np.ndarray          # int8 ở lưới ra
    pixel_fractions: dict      # tỉ lệ pixel FREE / không chắc / BLOCKED / không có bằng chứng (ROI, NaN)
    prob_size: tuple
    time_ms: float


def fine_grid(grid: GridSpec, supersample: int) -> GridSpec:
    if int(supersample) != supersample or supersample < 1:
        raise ValueError("supersample phải là số nguyên ≥ 1")
    return GridSpec(grid.x_min, grid.x_max, grid.y_min, grid.y_max, grid.resolution / supersample)


def _blocks(a: np.ndarray, k: int) -> np.ndarray:
    rows, cols = a.shape[0] // k, a.shape[1] // k
    return a.reshape(rows, k, cols, k)


def _any(a: np.ndarray, k: int) -> np.ndarray:
    return _blocks(a, k).any(axis=(1, 3))


def _all(a: np.ndarray, k: int) -> np.ndarray:
    return _blocks(a, k).all(axis=(1, 3))


@lru_cache(maxsize=8)
def _pixel_ground_cells(calib: CameraCalibration, fine: GridSpec, range_limit: float | None) -> tuple:
    """(tâm (H, W), góc (H+1, W+1)): chỉ số phẳng hàng·số_cột + cột của ô con lưới mịn mà tâm pixel (u, v) và góc pixel
    (u ± 0,5, v ± 0,5) rơi xuống mặt sàn; −1 khi tia không chạm sàn, quá `range_limit`, ra ngoài lưới hay ngoài vùng hiệu
    chuẩn (θ > theta_max: `unproject` trả NaN, không ngoại suy). Chỉ phụ thuộc hiệu chuẩn + lưới + tầm nên được nhớ giữa
    các khung (mảng chỉ đọc; 640×480 ≈ 2,5 MB mỗi camera)."""
    intr = calib.intrinsics
    rows, cols = fine.shape

    def cells(u: np.ndarray, v: np.ndarray) -> np.ndarray:
        xy, ok = calib.pixel_to_ground(u.ravel(), v.ravel(), max_range=range_limit)
        with np.errstate(invalid="ignore"):
            ci = np.floor((xy[:, 0] - fine.x_min) / fine.resolution)
            ri = np.floor((xy[:, 1] - fine.y_min) / fine.resolution)
            inside = ok & (ci >= 0) & (ci < cols) & (ri >= 0) & (ri < rows)
        index = np.full(u.size, -1, np.int32)
        index[inside] = (ri[inside] * cols + ci[inside]).astype(np.int32)
        index = index.reshape(u.shape)
        index.flags.writeable = False
        return index

    center = cells(*np.meshgrid(np.arange(intr.width, dtype=np.float64), np.arange(intr.height, dtype=np.float64)))
    corner = cells(*np.meshgrid(np.arange(intr.width + 1, dtype=np.float64) - 0.5,
                                np.arange(intr.height + 1, dtype=np.float64) - 0.5))
    return center, corner


def not_free_hits(labels: np.ndarray, uncertain: np.ndarray, calib: CameraCalibration, fine: GridSpec,
                  max_range: float | None) -> np.ndarray:
    """bool (lưới mịn): ô con có tâm hoặc một góc của pixel BLOCKED/không chắc (trong ROI, không NaN) rơi vào.

    Điểm sàn của một pixel là điểm XA NHẤT tia của nó có thể chạm, nên pixel BLOCKED không chứng minh được mặt sàn ở đó
    trống: gỡ FREE ở đó luôn an toàn. Không dùng để đặt OCCUPIED (pixel mặt bên vật cao sẽ kéo vệt theo tia)."""
    mask = (labels == LABEL_BLOCKED) | uncertain
    rows, cols = fine.shape
    hit = np.zeros(rows * cols, bool)
    if mask.any():
        # ô con có tâm trong max_range có thể có góc xa hơn tới 0,71 × cạnh ô con: nới tầm một cạnh để không sót pixel
        limit = None if max_range is None else float(max_range) + fine.resolution
        center, corner = _pixel_ground_cells(calib, fine, limit)
        touched = np.zeros(corner.shape, bool)             # góc (i, j) thuộc các pixel (i-1..i, j-1..j)
        touched[:-1, :-1] |= mask
        touched[:-1, 1:] |= mask
        touched[1:, :-1] |= mask
        touched[1:, 1:] |= mask
        index = np.concatenate([center[mask], corner[touched]])
        hit[index[index >= 0]] = True
    return hit.reshape(rows, cols)


def project_camera(prob, camera: BevCamera, grid: GridSpec, *, t_free: float = DEFAULT_T_FREE,
                   t_blocked: float = DEFAULT_T_BLOCKED, max_range: float | None = RIG_MAX_RANGE,
                   supersample: int = DEFAULT_SUPERSAMPLE,
                   azimuth_bin_deg: float = DEFAULT_AZIMUTH_BIN_DEG) -> CameraView:
    t0 = time.perf_counter()
    calib = camera.calibration
    intr = calib.intrinsics
    raw = as_probability(prob)
    p = resize_probability(raw, intr.width, intr.height)
    labels, uncertain = evidence_labels(p, t_free, t_blocked, camera.roi)
    fine = fine_grid(grid, supersample)
    state_f = project_labels(labels, calib, fine, max_range=max_range, azimuth_bin_deg=azimuth_bin_deg)
    # FREE chỉ khi MỌI pixel rơi vào ô con là FREE: project_labels chỉ đọc pixel ở tâm ô con, nên vật mảnh nằm giữa các
    # tâm (cột 2 cm cách camera 0,25 m ≈ 25 px) từng để ô của nó FREE và vệt OCCUPIED rơi sang ô xa hơn (đo 24/09: 5/75
    # vị trí với cột 2 cm, 14/75 với 1,5 cm, 44/75 với 1 cm; docs/BEV.md mục 2). Pixel BLOCKED/không chắc gỡ FREE (→ UNKNOWN)
    # ở ô con nó rơi vào; không đặt OCCUPIED nên tập OCCUPIED và phép che khuất của project_labels giữ nguyên. Mỗi camera
    # gỡ FREE của riêng nó: "không chắc" của camera này không phủ quyết FREE chắc chắn của camera khác.
    state_f[not_free_hits(labels, uncertain, calib, fine, max_range) & (state_f == FREE)] = UNKNOWN
    # lượt thứ hai: pixel không chắc coi như FREE. Tập OCCUPIED (nên phép che khuất) giữ nguyên, nên ô khác UNKNOWN ở
    # lượt này = ô camera thật sự thấy, không bị che, trong tầm và trong ROI.
    seen_labels = labels.copy()
    seen_labels[uncertain] = LABEL_FREE
    seen_f = project_labels(seen_labels, calib, fine, max_range=max_range, azimuth_bin_deg=azimuth_bin_deg) != UNKNOWN
    # vùng hình học (không xét che khuất): chiếu hợp lệ, pixel có dữ liệu (trong ROI, không NaN), trong tầm
    gx, gy = fine.centers()
    u, v, valid = calib.ground_to_pixel(np.column_stack([gx.ravel(), gy.ravel()]))
    usable_px = (labels != LABEL_NONE) | uncertain
    in_view_f = valid.copy()
    in_view_f[valid] = usable_px[np.rint(v[valid]).astype(np.int64), np.rint(u[valid]).astype(np.int64)]
    if max_range is not None:
        cx, cy = calib.extrinsics.translation[:2]
        in_view_f &= np.hypot(gx.ravel() - cx, gy.ravel() - cy) <= max_range
    in_view_f = in_view_f.reshape(fine.shape)

    k = int(supersample)
    state = np.full(grid.shape, UNKNOWN, np.int8)
    state[_all(state_f == FREE, k)] = FREE
    state[_any(state_f == OCCUPIED, k)] = OCCUPIED
    total = labels.size
    fractions = {"free": float((labels == LABEL_FREE).sum() / total),
                 "uncertain": float(uncertain.sum() / total),
                 "blocked": float((labels == LABEL_BLOCKED).sum() / total),
                 "no_evidence": float(((labels == LABEL_NONE) & ~uncertain).sum() / total)}
    return CameraView(camera.name, state_f, seen_f, in_view_f, state, fractions, (int(raw.shape[1]), int(raw.shape[0])),
                      1000.0 * (time.perf_counter() - t0))


# ---- hợp nhất --------------------------------------------------------------------------------------------------------
@dataclass
class BevResult:
    grid: GridSpec
    states: np.ndarray          # int8 UNKNOWN / FREE / OCCUPIED — nội dung của Costmap
    category: np.ndarray        # uint8 CAT_*
    cameras: list               # thứ tự bit của các bitmask
    seen_by: np.ndarray         # uint16: camera thấy ít nhất một ô con (không bị che)
    free_by: np.ndarray         # uint16: camera nói FREE ở ít nhất một ô con
    occupied_by: np.ndarray     # uint16: camera nói OCCUPIED ở ít nhất một ô con
    in_view_by: np.ndarray      # uint16: ô trong vùng hình học của camera (kể cả khi bị che)
    conflict: np.ndarray        # bool: có ô con mà một camera nói OCCUPIED, camera khác nói FREE
    conflict_pairs: dict        # "a OCCUPIED / b FREE" → số ô
    views: dict
    missing: dict               # camera không góp dữ liệu → lý do
    ego: EgoBox | None
    params: dict
    timing_ms: dict

    def camera_bits(self, mask) -> list:
        """Tên các camera có bit trong một giá trị bitmask."""
        return [name for i, name in enumerate(self.cameras) if int(mask) >> i & 1]

    def counts(self) -> dict:
        return {name: int((self.category == cat).sum()) for cat, name in CATEGORY_NAMES.items()}

    def overlap(self) -> dict:
        n_seen = _popcount(self.seen_by)
        return {"cells_seen_by_2_or_more": int((n_seen >= 2).sum()),
                "cells_by_camera_count": {str(n): int((n_seen == n).sum()) for n in range(len(self.cameras) + 1)},
                "conflict_cells": int(self.conflict.sum()),
                "conflicts_by_pair": dict(self.conflict_pairs),
                "note": "ô xung đột (ở cùng một ô con, một camera nói OCCUPIED, camera khác nói FREE) là OCCUPIED; nhiều "
                        "ô xung đột dọc biên chồng lấn thường là dấu hiệu ngoại tham/nội tham lệch"}

    def provenance_dict(self) -> dict:
        return {"cameras": list(self.cameras),
                "bit_rule": "bit i (giá trị 1 << i) = cameras[i]",
                "layout": "cells[row][col] như costmap",
                "meaning": {"seen_by": "camera thấy ít nhất một ô con, không bị che",
                            "free_by": "camera nói FREE ở ít nhất một ô con",
                            "occupied_by": "camera nói OCCUPIED ở ít nhất một ô con",
                            "in_view_by": "ô trong trường nhìn + tầm + ROI của camera, kể cả khi bị che"},
                "seen_by": self.seen_by.tolist(), "free_by": self.free_by.tolist(),
                "occupied_by": self.occupied_by.tolist(), "in_view_by": self.in_view_by.tolist()}


def _popcount(a: np.ndarray) -> np.ndarray:
    n = np.zeros(a.shape, np.int64)
    for i in range(MAX_CAMERAS):
        n += (a >> i) & 1
    return n


def merge_views(views: list, grid: GridSpec, names: list, supersample: int, ego: EgoBox | None = None) -> dict:
    """Hợp nhất ở LƯỚI MỊN rồi gộp: ô con OCCUPIED nếu có camera nói OCCUPIED; ô con FREE nếu có camera nói FREE và
    không camera nào nói OCCUPIED. Ô ra OCCUPIED nếu có ô con OCCUPIED; FREE chỉ khi MỌI ô con FREE; còn lại UNKNOWN.
    Hợp nhất ở lưới mịn để ô nằm trên biên trường nhìn của hai camera (mỗi camera thấy một phần) vẫn là FREE khi mọi
    phần đều được thấy trống; gộp riêng từng camera trước thì các ô đó thành UNKNOWN thừa."""
    k = int(supersample)
    rows, cols = grid.shape
    fine_shape = (rows * k, cols * k)
    seen_by, free_by, occupied_by, in_view_by = (np.zeros((rows, cols), np.uint16) for _ in range(4))
    occupied_f = np.zeros(fine_shape, bool)
    free_f = np.zeros(fine_shape, bool)
    for view in views:
        bit = np.uint16(1 << names.index(view.name))
        occ, fr = view.state_fine == OCCUPIED, view.state_fine == FREE
        occupied_by[_any(occ, k)] |= bit
        free_by[_any(fr, k)] |= bit
        seen_by[_any(view.seen_fine, k)] |= bit
        in_view_by[_any(view.in_view_fine, k)] |= bit
        occupied_f |= occ
        free_f |= fr
    conflict_f = np.zeros(fine_shape, bool)
    pairs = {}
    for a in views:
        for b in views:
            if a is not b:
                both = (a.state_fine == OCCUPIED) & (b.state_fine == FREE)
                if both.any():
                    conflict_f |= both
                    pairs[f"{a.name} OCCUPIED / {b.name} FREE"] = int(_any(both, k).sum())
    states = np.full((rows, cols), UNKNOWN, np.int8)
    states[_all(free_f & ~occupied_f, k)] = FREE
    states[_any(occupied_f, k)] = OCCUPIED
    category = np.full((rows, cols), CAT_UNSEEN, np.uint8)
    category[in_view_by != 0] = CAT_OCCLUDED
    category[seen_by != 0] = CAT_UNCERTAIN
    under = None
    if ego is not None:
        gx, gy = grid.centers()
        under = ego.contains(gx, gy)
        states[under] = UNKNOWN
    category[states == FREE] = CAT_FREE
    category[states == OCCUPIED] = CAT_OCCUPIED
    if under is not None:
        category[under] = CAT_EGO
    return {"states": states, "category": category, "seen_by": seen_by, "free_by": free_by,
            "occupied_by": occupied_by, "in_view_by": in_view_by, "conflict": _any(conflict_f, k),
            "conflict_pairs": pairs}


def build_bev(probs: dict, cameras: dict, grid: GridSpec, *, t_free: float = DEFAULT_T_FREE,
              t_blocked: float = DEFAULT_T_BLOCKED, max_range: float | None = RIG_MAX_RANGE,
              supersample: int = DEFAULT_SUPERSAMPLE, azimuth_bin_deg: float = DEFAULT_AZIMUTH_BIN_DEG,
              ego: EgoBox | None = None, missing: dict | None = None) -> BevResult:
    """probs: {tên camera: bản đồ P(BLOCKED) hoặc None}; cameras: {tên: BevCamera} — thứ tự này là thứ tự bit.
    Camera có trong `cameras` mà không có xác suất thì không góp gì (lý do ở `missing`)."""
    check_thresholds(t_free, t_blocked)
    names = list(cameras)
    if len(names) > MAX_CAMERAS:
        raise ValueError(f"tối đa {MAX_CAMERAS} camera")
    stray = sorted(set(probs) - set(names))
    if stray:
        raise ValueError(f"có xác suất cho camera không có hiệu chuẩn: {stray}")
    t0 = time.perf_counter()
    missing = dict(missing or {})
    views = []
    for name in names:
        prob = probs.get(name)
        if prob is None:
            missing.setdefault(name, "không có bản đồ xác suất")
            continue
        views.append(project_camera(prob, cameras[name], grid, t_free=t_free, t_blocked=t_blocked,
                                    max_range=max_range, supersample=supersample, azimuth_bin_deg=azimuth_bin_deg))
    t1 = time.perf_counter()
    merged = merge_views(views, grid, names, supersample, ego)
    t2 = time.perf_counter()
    params = {"t_free": t_free, "t_blocked": t_blocked, "max_range_m": max_range, "supersample": int(supersample),
              "azimuth_bin_deg": azimuth_bin_deg,
              "grid": {"x_min": grid.x_min, "x_max": grid.x_max, "y_min": grid.y_min, "y_max": grid.y_max,
                       "resolution_m": grid.resolution, "shape_rows_cols": list(grid.shape)}}
    timing = {"cameras_ms": round(1000.0 * (t1 - t0), 2), "merge_ms": round(1000.0 * (t2 - t1), 2),
              "total_ms": round(1000.0 * (t2 - t0), 2),
              "per_camera_ms": {v.name: round(v.time_ms, 2) for v in views}}
    return BevResult(grid=grid, cameras=names, views={v.name: v for v in views}, missing=missing, ego=ego,
                     params=params, timing_ms=timing, **merged)


def bev_costmap(result: BevResult, stamp: SourceStamp) -> Costmap:
    return to_costmap(result.states, result.grid, stamp)


# ---- vẽ --------------------------------------------------------------------------------------------------------------
def _canvas(values: np.ndarray, colors: dict, scale: int) -> np.ndarray:
    rows, cols = values.shape
    canvas = np.zeros((cols, rows, 3), np.uint8)          # hàng ảnh = x (lật: trước ở trên), cột ảnh = y (lật: trái ở trái)
    flipped = values.T[::-1, ::-1]
    for value, color in colors.items():
        canvas[flipped == value] = color
    return cv2.resize(canvas, (rows * scale, cols * scale), interpolation=cv2.INTER_NEAREST)


def render_bev(result: BevResult, cameras: dict | None = None, *, scale: int = 4, title: str = "",
               truth: np.ndarray | None = None) -> np.ndarray:
    """Hai ô (thêm ô sự thật nếu có `truth` theo mã CAT_*): phân loại ô, và số camera thấy mỗi ô. Chữ ASCII (cv2
    không vẽ được dấu tiếng Việt)."""
    grid = result.grid
    n_cam = max(1, len(result.cameras))
    ramp = {n: tuple(int(c) for c in cv2.applyColorMap(np.uint8([[40 + 215 * n // n_cam]]), cv2.COLORMAP_VIRIDIS)[0, 0])
            for n in range(1, n_cam + 1)}
    ramp[0] = (30, 30, 30)
    panels = [(title or "BEV", _canvas(result.category, CATEGORY_COLORS, scale)),
              ("cameras seeing each cell", _canvas(_popcount(result.seen_by), ramp, scale))]
    if truth is not None:
        panels.insert(0, ("ground truth", _canvas(truth, CATEGORY_COLORS, scale)))

    def px(x, y):
        return int(round((grid.y_max - y) / grid.resolution * scale)), int(round((grid.x_max - x) / grid.resolution * scale))

    span = max(grid.x_max - grid.x_min, grid.y_max - grid.y_min)
    step = 1.0 if span <= 12 else 5.0
    drawn = []
    for label, canvas in panels:
        for x in np.arange(math.ceil(grid.x_min / step) * step, grid.x_max + 1e-9, step):
            cv2.line(canvas, px(x, grid.y_min), px(x, grid.y_max), (80, 80, 80), 1)
        for y in np.arange(math.ceil(grid.y_min / step) * step, grid.y_max + 1e-9, step):
            cv2.line(canvas, px(grid.x_min, y), px(grid.x_max, y), (80, 80, 80), 1)
        if result.ego is not None:
            e = result.ego
            cv2.rectangle(canvas, px(e.x_max, e.y_max), px(e.x_min, e.y_min), (255, 255, 255), 1)
        for name, cam in (cameras or {}).items():
            t = cam.calibration.extrinsics.translation
            axis = cam.calibration.extrinsics.rotation[:, 2]
            heading = np.array(axis[:2]) / (np.linalg.norm(axis[:2]) or 1.0)
            tip = (t[0] + 0.25 * step * heading[0], t[1] + 0.25 * step * heading[1])
            color = (0, 255, 255) if name in result.views else (0, 0, 255)
            cv2.arrowedLine(canvas, px(t[0], t[1]), px(*tip), color, 1, tipLength=0.3)
            cv2.circle(canvas, px(t[0], t[1]), 3, color, -1)
            cv2.putText(canvas, _ascii(name)[:10], (px(*tip)[0] + 2, px(*tip)[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                        color, 1, cv2.LINE_AA)
        header = np.full((22, canvas.shape[1], 3), 20, np.uint8)
        cv2.putText(header, _ascii(label)[: canvas.shape[1] // 7], (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (230, 230, 230), 1, cv2.LINE_AA)
        drawn.append(np.vstack([header, canvas]))
    height = max(p.shape[0] for p in drawn)
    drawn = [np.vstack([p, np.zeros((height - p.shape[0], p.shape[1], 3), np.uint8)]) for p in drawn]
    body = np.hstack([np.hstack([p, np.full((height, 4, 3), 255, np.uint8)]) for p in drawn])[:, :-4]
    legend = np.full((44, body.shape[1], 3), 20, np.uint8)
    x = 6
    for cat, name in CATEGORY_NAMES.items():
        cv2.rectangle(legend, (x, 6), (x + 12, 18), CATEGORY_COLORS[cat], -1)
        cv2.putText(legend, name, (x + 16, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (230, 230, 230), 1, cv2.LINE_AA)
        x += 22 + 8 * len(name)
    cv2.putText(legend, f"x forward = up, y left = left; grid lines every {step:g} m; cell {grid.resolution:g} m; "
                        f"camera count 0..{len(result.cameras)} dark->bright",
                (6, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1, cv2.LINE_AA)
    return np.vstack([body, legend])


def _ascii(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


# ---- ghi kết quả -----------------------------------------------------------------------------------------------------
ASSUMPTIONS = [
    "mặt sàn phẳng z = 0 trong hệ xe; phép chiếu chỉ đúng cho điểm thuộc mặt sàn",
    "vật cao: chỉ phía chân vật hướng về camera là OCCUPIED (phần sau bị che là UNKNOWN); đây KHÔNG phải footprint chính "
    "xác; vật nhô ra (mặt bàn, cản xe) hay có chân bị che thì biên OCCUPIED lệch",
    "OCCUPIED/FREE của mỗi ô con lấy từ pixel gần tâm ô con; thêm vào đó ô con có tâm hoặc góc của pixel BLOCKED/không "
    "chắc rơi vào thì không được FREE (không tích phân đủ diện tích pixel: pixel phủ hơn hai ô con ở xa có thể sót ô "
    "giữa, nhưng khi đó tâm ô con đó thường đọc chính pixel ấy)",
    "không lọc theo thời gian; một bộ ảnh cho một BEV",
    "AI chưa từng được chấm trên ảnh sa bàn; lỗi của mô hình đi thẳng vào BEV",
]


def unusable_reasons(result: BevResult, cameras: dict) -> list:
    reasons = []
    if not result.views:
        reasons.append("không camera nào có dữ liệu")
    for name in result.views:
        cam = cameras[name]
        if not cam.extrinsics_measured:
            reasons.append(f"{name}: ngoại tham GIẢ ĐỊNH — CHƯA ĐO")
        if cam.roi is None:
            reasons.append(f"{name}: chưa có ROI (thân xe/viền ống kính chưa bị loại khỏi ảnh)")
        if cam.acceptance_all_pass is False:
            reasons.append(f"{name}: nội tham chưa đạt tiêu chí đề xuất (acceptance.all_pass = false)")
    return reasons


def result_stats(result: BevResult, cameras: dict, *, extra: dict | None = None) -> dict:
    per_camera = {}
    k = int(result.params["supersample"])
    for name in result.cameras:
        view = result.views.get(name)
        if view is None:        # camera không dùng: chỉ ghi hướng và lý do (nội tham của nó có thể chưa từng được nạp)
            cam = cameras.get(name)
            entry = {"direction": None if cam is None else cam.direction,
                     "extrinsics_measured": None if cam is None else cam.extrinsics_measured,
                     "used": False, "reason": result.missing.get(name, "không có dữ liệu")}
        else:
            entry = cameras[name].describe()
            entry.update({"used": True, "prob_size": list(view.prob_size),
                          "pixel_fractions": {k: round(v, 5) for k, v in view.pixel_fractions.items()},
                          "cells": {"free": int((view.state == FREE).sum()), "occupied": int((view.state == OCCUPIED).sum()),
                                    "seen": int(_any(view.seen_fine, k).sum()),
                                    "in_view": int(_any(view.in_view_fine, k).sum())},
                          "time_ms": round(view.time_ms, 2)})
        per_camera[name] = entry
    for name, reason in result.missing.items():
        per_camera.setdefault(name, {"used": False, "reason": reason})
    counts = result.counts()
    counts["unknown_total"] = sum(counts[k] for k in ("uncertain", "occluded", "unseen", "ego"))
    stats = {"created_utc": utc_now(), "kind": "autopark_bev_v0", "params": result.params,
             "rules": {"evidence": "p ≤ t_free → FREE; p ≥ t_blocked → OCCUPIED; ở giữa → không chắc (UNKNOWN); "
                                   "ngoài ROI/NaN → không có bằng chứng",
                       "projection": "costmap.project_labels trên lưới mịn (supersample); sau ô OCCUPIED đầu tiên theo "
                                     "phương vị là UNKNOWN; quá max_range là UNKNOWN; ô con có tâm/góc của pixel BLOCKED "
                                     "hay không chắc rơi vào thì không FREE (→ UNKNOWN) ở camera đó; gộp ô con: OCCUPIED "
                                     "nếu có ô con OCCUPIED, FREE chỉ khi mọi ô con FREE",
                       "merge": "OCCUPIED nếu có camera nói OCCUPIED; FREE chỉ khi ≥ 1 camera thấy FREE chắc chắn và "
                                "không camera nào nói OCCUPIED; còn lại UNKNOWN; dưới thân xe luôn UNKNOWN"},
             "category_meaning": CATEGORY_MEANING, "counts": counts, "overlap": result.overlap(),
             "cameras": per_camera, "ego": None if result.ego is None else result.ego.to_dict(),
             "timing_ms": result.timing_ms, "assumptions": ASSUMPTIONS}
    stats.update(extra or {})
    return stats


def write_outputs(out_dir, result: BevResult, cameras: dict, stamp: SourceStamp, *, extra: dict | None = None,
                  title: str = "", truth: np.ndarray | None = None) -> dict:
    """Ghi bev.png, costmap.json (Costmap + nguồn gốc từng ô + phân loại), stats.json."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    costmap = bev_costmap(result, stamp)
    stats = result_stats(result, cameras, extra={"usable_for_planning": stamp.valid, **(extra or {})})
    atomic_write_json(out / "costmap.json", {
        "created_utc": utc_now(), "kind": "autopark_bev_v0", "usable_for_planning": stamp.valid,
        "unusable_reasons": stats.get("unusable_reasons", []),
        "costmap": costmap_to_dict(costmap), "provenance": result.provenance_dict(),
        "category": {"codes": {str(k): v for k, v in CATEGORY_NAMES.items()}, "meaning": CATEGORY_MEANING,
                     "cells": result.category.tolist()}})
    atomic_write_json(out / "stats.json", stats)
    write_image(out / "bev.png", render_bev(result, cameras, title=title, truth=truth))
    return {"costmap": out / "costmap.json", "stats": out / "stats.json", "image": out / "bev.png"}


# ---- bộ ảnh của bàn thử ----------------------------------------------------------------------------------------------
def read_snapshot(folder) -> tuple[dict, dict]:
    """meta.json + {cổng: P×255 uint8} của một thư mục "Chụp bộ ảnh" (runs/rig_snapshots/<ngày_giờ>)."""
    folder = Path(folder)
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        raise RigConfigError(f"{folder}: thiếu meta.json (bàn thử ghi meta sau cùng: lần chụp dở dang hoặc sai thư mục)")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise RigConfigError(f"{meta_path}: không đọc được: {exc}") from exc
    probs = {}
    for key in (meta.get("cameras") or {}):
        path = folder / f"prob_blocked_p{int(key)}.png"
        if path.exists():
            probs[int(key)] = read_gray(path)
    return meta, probs


def snapshot_frame_damage(folder, port: int, entry: dict, bottom_repeat_limit: float = BOTTOM_REPEAT_LIMIT) -> dict:
    """Khung `cam_p<cổng>.png` của bộ ảnh có dấu hiệu hỏng không — cùng bộ dò với nguồn camera và labels.frame_damage:
    `truncated_rows` (đáy do bộ giải mã tô), `torn_bands` (dải xé giữa ảnh, đáy có thể nguyên), `bottom_repeat_share` >
    ngưỡng (số của meta.json; bộ ảnh trước 24/09 không ghi thì tính lại trên khung bằng cùng hàm của bàn thử).
    Không có ảnh (hoặc không giải mã được) mà meta.json cũng không ghi số: KHÔNG kiểm được → coi là hỏng (bỏ camera),
    không mặc định "khung tốt". Có số trong meta mà không có ảnh: chỉ xét được số đó (`image_checked` = false)."""
    folder = Path(folder)
    recorded = entry.get("bottom_repeat_share")
    from_meta = (isinstance(recorded, (int, float)) and not isinstance(recorded, bool)
                 and math.isfinite(float(recorded)))
    share = float(recorded) if from_meta else None
    share_from = "meta.json" if from_meta else None
    image_path = folder / f"cam_p{port}.png"
    image, image_note = None, None
    if image_path.exists():
        try:
            image = read_color(image_path)
        except RigConfigError as exc:
            image_note = str(exc)
    else:
        image_note = f"không có {image_path.name}"
    reasons, rows, bands = [], None, None
    if image is not None:
        rows = int(truncated_rows(image))
        bands = int(torn_bands(image, exclude_bottom_rows=rows))
        if share is None:
            share, share_from = float(bottom_repeat_share(image)), "tính lại trên khung"
        if rows:
            reasons.append(f"{rows}/{image.shape[0]} dòng đáy do bộ giải mã tô (truncated_rows)")
        if bands:
            reasons.append(f"{bands} hàng khối có dải xé giữa ảnh (torn_bands)")
    if share is not None and share > bottom_repeat_limit:
        reasons.append(f"bottom_repeat_share {share:.3f} ({share_from}) > {bottom_repeat_limit:g}")
    if image is None and share is None:
        reasons.append(f"không kiểm được khung hỏng: meta.json không ghi bottom_repeat_share và {image_note}")
    return {"damaged": bool(reasons), "reasons": reasons, "image_checked": image is not None, "image_note": image_note,
            "truncated_rows": rows, "torn_bands": bands,
            "bottom_repeat_share": None if share is None else round(share, 4), "bottom_repeat_share_from": share_from,
            "bottom_repeat_limit": float(bottom_repeat_limit)}


def synchronous_group(stamps: dict, max_skew_s: float) -> set:
    """Tập camera đông nhất mà mọi stamp nằm trong một cửa sổ dài max_skew_s; bằng nhau thì lấy cửa sổ MỚI hơn."""
    best_key, best = None, set()
    for t0 in sorted(stamps.values()):
        members = {n for n, t in stamps.items() if t0 <= t <= t0 + max_skew_s}
        key = (len(members), t0)
        if best_key is None or key > best_key:
            best_key, best = key, members
    return best


def bev_from_snapshot(folder, *, extrinsics=DEFAULT_EXTRINSICS, calibration_dir=DEFAULT_CALIBRATION_DIR,
                      roi_dir=None, grid: GridSpec | None = None, t_free: float = DEFAULT_T_FREE,
                      t_blocked: float = DEFAULT_T_BLOCKED, max_range: float | None = RIG_MAX_RANGE,
                      supersample: int = DEFAULT_SUPERSAMPLE, max_skew_ms: float = MAX_SKEW_MS,
                      bottom_repeat_limit: float = BOTTOM_REPEAT_LIMIT, skip_uncalibrated: bool = False):
    """→ (BevResult, cameras, SourceStamp, thông tin thêm cho stats.json)."""
    grid = grid or GridSpec(*RIG_GRID)
    folder = Path(folder)
    meta, probs_by_port = read_snapshot(folder)
    entries = {int(k): v for k, v in (meta.get("cameras") or {}).items()}
    mode = meta.get("camera_mode") or {}
    sizes, missing = {}, {}
    for port, e in entries.items():
        if port not in probs_by_port:
            continue
        w, h = e.get("width") or mode.get("width"), e.get("height") or mode.get("height")
        if not w or not h:
            missing[f"p{port}"] = "meta.json không ghi cỡ khung của camera này"
            continue
        sizes[port] = (int(w), int(h))
    cameras, rig, skipped = load_rig(extrinsics, calibration_dir, sizes, roi_dir=roi_dir,
                                     skip_uncalibrated=skip_uncalibrated)
    missing.update(skipped)
    for port in sorted(set(rig.cameras) | set(entries)):
        name = f"p{port}"
        if port not in entries:
            missing.setdefault(name, "camera không có trong bộ ảnh")
        elif port not in probs_by_port:
            missing.setdefault(name, "không có prob_blocked (AI tắt lúc chụp hoặc camera ngoài bộ AI)")
    # khung hỏng: bỏ camera. Xét trên chính cam_p<cổng>.png (bộ ảnh trước 24/09 không ghi bottom_repeat_share; dải xé
    # giữa ảnh không làm bottom_repeat_share cao). Không kiểm được thì bỏ, không mặc định "khung tốt".
    damage_checks = {}
    for name in list(cameras):
        port = int(name[1:])
        check = snapshot_frame_damage(folder, port, entries[port], bottom_repeat_limit)
        damage_checks[name] = check
        if check["damaged"]:
            missing[name] = ("khung nghi hỏng: " + "; ".join(check["reasons"])
                             + " (vùng hỏng bị AI gọi là FREE — lỗi không an toàn)")
            del cameras[name]
    # lệch thời gian: giữ nhóm đông nhất có mọi stamp trong một cửa sổ max_skew_ms, bỏ các camera còn lại
    stamps = {name: entries[int(name[1:])].get("stamp_s") for name in cameras}
    keep = synchronous_group({n: s for n, s in stamps.items() if s is not None}, max_skew_ms / 1000.0)
    if keep:
        lo, hi = min(stamps[n] for n in keep), max(stamps[n] for n in keep)
        for name, s in stamps.items():
            if s is not None and name not in keep:
                off = s - hi if s > hi else s - lo
                missing[name] = (f"khung lệch {1000.0 * off:+.1f} ms so với nhóm đồng bộ {sorted(keep)} "
                                 f"(cửa sổ {max_skew_ms:g} ms)")
                del cameras[name]
    # thứ tự bit = mọi cổng của tệp rig (load_rig chỉ trả cổng có trong tệp đó); camera không dùng vẫn giữ bit của nó
    # (bit không bao giờ bật) và một chỗ giữ tư thế để vẽ — nội tham của chỗ giữ không bao giờ được chiếu
    ordered = {}
    for port in sorted(rig.cameras):
        name, pose = f"p{port}", rig.cameras[port]
        ordered[name] = cameras.get(name) or BevCamera(
            name, CameraCalibration(name, _placeholder_intrinsics(), pose.extrinsics), None, pose.measured,
            pose.direction, "(không nạp: camera không dùng)")
    probs = {name: probs_by_port[int(name[1:])] for name in cameras}
    result = build_bev(probs, ordered, grid, t_free=t_free, t_blocked=t_blocked, max_range=max_range,
                       supersample=supersample, ego=rig.ego, missing=missing)
    reasons = unusable_reasons(result, ordered)
    used_stamps = [entries[int(n[1:])].get("stamp_s") for n in result.views]
    used_stamps = [s for s in used_stamps if s is not None]
    t = min(used_stamps) if used_stamps else float(meta.get("t_capture_s") or 0.0)
    stamp = SourceStamp("bev_cameras", max(0.0, float(t)), not reasons, "vehicle")
    extra = {"input": {"snapshot": str(folder), "created_local": meta.get("created_local"),
                       "model": meta.get("model"), "checkpoint": meta.get("checkpoint"),
                       "snapshot_threshold": meta.get("threshold"), "camera_mode": mode,
                       "stamp_clock": (meta.get("clock") or {}).get("name"),
                       "stamp_t_s": stamp.t, "stamp_rule": "stamp = khung CŨ NHẤT trong các camera được dùng"},
             "extrinsics": {"path": rig.path, "status": rig.status},
             "calibration_dir": str(calibration_dir), "roi_dir": None if roi_dir is None else str(roi_dir),
             "max_skew_ms": max_skew_ms, "bottom_repeat_limit": bottom_repeat_limit,
             "frame_damage_check": damage_checks,
             "unusable_reasons": reasons,
             "caveats": ["AI chưa từng được chấm trên ảnh sa bàn",
                         "giấy phép WoodScape chưa chốt cho việc nối AI vào costmap/lập đường (GIAY_PHEP_DU_LIEU.md)"]}
    return result, ordered, stamp, extra


def _placeholder_intrinsics() -> FisheyeIntrinsics:
    """Chỉ để giữ chỗ thứ tự bit cho camera KHÔNG được dùng (không bao giờ chiếu)."""
    return nominal_intrinsics()


# ---- WoodScape -------------------------------------------------------------------------------------------------------
def woodscape_camera(image_id: str, archive, roi_dir=None) -> BevCamera:
    """Hiệu chuẩn riêng của một ảnh WoodScape. Mã ảnh không có trong kho, kho thiếu/không phải zip, tệp hiệu chuẩn
    thiếu trường → RigConfigError (dòng lệnh in "LỖI: …", thoát mã 2), không để traceback."""
    try:
        calibration = load_woodscape_calibration(archive, image_id)
    except KeyError as exc:
        raise RigConfigError(
            f"không có hiệu chuẩn cho {image_id!r} trong {archive}, hoặc tệp hiệu chuẩn thiếu trường ({exc}); --image "
            f"phải là ảnh WoodScape đặt tên theo mã khung (ví dụ 00000_FV.png) — ảnh sa bàn/camera thật dùng lệnh "
            f"`snapshot`") from exc
    except (OSError, zipfile.BadZipFile) as exc:
        raise RigConfigError(
            f"không mở được kho hiệu chuẩn {archive}: {exc} (cần datasets/woodscape_metadata/calibration.zip hoặc "
            f"--calibration-archive trỏ tới tệp zip đúng)") from exc
    except (ValueError, TypeError) as exc:
        raise RigConfigError(f"tệp hiệu chuẩn của {image_id!r} trong {archive} sai định dạng: {exc}") from exc
    view = image_id.rsplit("_", 1)[-1]
    roi, roi_source = None, None
    if roi_dir is not None:
        roi_path = Path(roi_dir) / f"roi_{view}.png"
        if not roi_path.exists():
            raise RigConfigError(f"ROI {roi_path} không có; dựng bằng `python -m autopark.perception.roi build` hoặc "
                                 f"chạy --no-roi (costmap bị đánh dấu không dùng được)")
        roi = read_gray(roi_path)
        roi_source = str(roi_path)
    return BevCamera(image_id, CameraCalibration(image_id, calibration.intrinsics, calibration.extrinsics), roi, True,
                     view, "datasets/woodscape_metadata/calibration.zip", roi_source, None)


def woodscape_probabilities(images: list, checkpoint) -> list:
    """P(BLOCKED) ở cỡ gốc bằng LiveSegmenter (cùng tiền xử lý với predict.py). Cần torch (.venv-train)."""
    try:
        from .live import LiveSegmenter
    except ImportError as exc:
        raise RigConfigError(f"chạy mô hình cần torch (dùng .venv-train) hoặc truyền --prob: {exc}") from exc
    segmenter = LiveSegmenter(checkpoint)
    probs, _ = segmenter.infer(images)
    return probs


# ---- cảnh tổng hợp (kiểm thử và minh họa; KHÔNG phải số đo) --------------------------------------------------------
@dataclass(frozen=True)
class SyntheticBox:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    height: float


@dataclass(frozen=True)
class SyntheticPatch:
    """Vùng mặt sàn mà "mô hình" trả một xác suất cố định (ví dụ dải không chắc chắn)."""
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    prob: float


@dataclass(frozen=True)
class SyntheticScene:
    boxes: tuple = ()
    patches: tuple = ()
    p_ground: float = 0.02
    p_box: float = 0.98
    p_no_hit: float = 1.0          # tia lên trời / quá xa / ngoài vùng hiệu chuẩn
    far_m: float = 30.0


DEFAULT_SCENE = SyntheticScene(
    boxes=(SyntheticBox(1.0, 1.3, -0.15, 0.15, 0.15),          # hộp trước xe: chỉ camera trước thấy
           SyntheticBox(-0.3, 0.3, -1.0, -0.8, 0.10)),          # hộp bên phải
    patches=(SyntheticPatch(-1.3, -1.0, -0.6, 0.6, 0.30),)       # dải không chắc chắn sau xe
)


def nominal_intrinsics(width: int = 640, height: int = 480, diagonal_fov_deg: float = 130.0) -> FisheyeIntrinsics:
    """Ống kính mắt cá đẳng cự ρ = f·θ, góc CHÉO `diagonal_fov_deg` — CHỈ cho cảnh tổng hợp (130° là số nhà bán)."""
    f = math.hypot(width / 2, height / 2) / math.radians(diagonal_fov_deg / 2)
    return FisheyeIntrinsics(width, height, (f, 0.0, 0.0, 0.0))


def synthetic_rig(extrinsics=DEFAULT_EXTRINSICS, width: int = 640, height: int = 480) -> tuple[dict, EgoBox | None]:
    """Bốn camera ảo: tư thế lấy từ tệp rig (giả định), nội tham danh định `nominal_intrinsics`."""
    rig = load_rig_extrinsics(extrinsics)
    intr = nominal_intrinsics(width, height)
    cameras = {f"p{port}": BevCamera(f"p{port}", CameraCalibration(f"p{port}", intr, pose.extrinsics), None,
                                     pose.measured, pose.direction, "nominal_intrinsics (tổng hợp)")
               for port, pose in sorted(rig.cameras.items())}
    return cameras, rig.ego


def _box_hit(o: np.ndarray, d: np.ndarray, box: SyntheticBox) -> np.ndarray:
    """Tham số t ≥ 0 của lần chạm đầu tiên vào hộp (slab), inf nếu không chạm. o (3,), d (N, 3)."""
    lo = np.array([box.x_min, box.y_min, 0.0])
    hi = np.array([box.x_max, box.y_max, box.height])
    safe = np.where(np.abs(d) < 1e-12, 1e-12, d)
    t1, t2 = (lo - o) / safe, (hi - o) / safe
    t_near = np.minimum(t1, t2).max(axis=1)
    t_far = np.maximum(t1, t2).min(axis=1)
    hit = (t_near <= t_far) & (t_far > 0)
    return np.where(hit, np.maximum(t_near, 0.0), np.inf)


def synthetic_prob_map(calibration: CameraCalibration, scene: SyntheticScene = DEFAULT_SCENE,
                       out_size: tuple | None = None) -> np.ndarray:
    """Chiếu sự thật của cảnh vào ảnh (tia qua từng pixel → hộp hay mặt sàn trước): P(BLOCKED) float32.

    Đường tính này đi từ PIXEL ra cảnh (unproject + giao tia–hộp), ngược chiều với BEV (tâm ô → pixel), nên kiểm được
    phép chiếu của BEV bằng một phép tính độc lập.
    """
    intr = calibration.intrinsics
    u, v = np.meshgrid(np.arange(intr.width, dtype=np.float64), np.arange(intr.height, dtype=np.float64))
    rays = intr.unproject(u.ravel(), v.ravel()) @ calibration.extrinsics.rotation.T
    o = np.asarray(calibration.extrinsics.translation, dtype=np.float64)
    ok = np.all(np.isfinite(rays), axis=1)
    d = np.where(ok[:, None], rays, np.array([0.0, 0.0, 1.0]))
    with np.errstate(divide="ignore", invalid="ignore"):
        t_ground = np.where(d[:, 2] < -1e-9, -o[2] / d[:, 2], np.inf)
    t_ground = np.where(t_ground <= scene.far_m, t_ground, np.inf)
    t_box = np.full(len(d), np.inf)
    for box in scene.boxes:
        t_box = np.minimum(t_box, _box_hit(o, d, box))
    prob = np.full(len(d), scene.p_no_hit, np.float32)
    ground = np.isfinite(t_ground) & (t_ground < t_box)
    prob[ground] = scene.p_ground
    gp = o[:2] + t_ground[ground, None] * d[ground, :2]
    ground_idx = np.flatnonzero(ground)
    for patch in scene.patches:
        inside = ((gp[:, 0] >= patch.x_min) & (gp[:, 0] <= patch.x_max) & (gp[:, 1] >= patch.y_min)
                  & (gp[:, 1] <= patch.y_max))
        prob[ground_idx[inside]] = patch.prob
    prob[np.isfinite(t_box) & (t_box <= t_ground)] = scene.p_box
    prob[~ok] = scene.p_no_hit
    prob = prob.reshape(intr.height, intr.width)
    if out_size is not None and tuple(out_size) != (intr.width, intr.height):
        prob = cv2.resize(prob, tuple(out_size), interpolation=cv2.INTER_AREA)
    return prob


def synthetic_truth(scene: SyntheticScene, grid: GridSpec, t_free: float = DEFAULT_T_FREE,
                    t_blocked: float = DEFAULT_T_BLOCKED, ego: EgoBox | None = None) -> np.ndarray:
    """Sự thật theo mã CAT_* để vẽ: hộp → occupied, dải có xác suất giữa hai ngưỡng → uncertain, còn lại free."""
    gx, gy = grid.centers()
    truth = np.full(grid.shape, CAT_FREE, np.uint8)
    for patch in scene.patches:
        inside = (gx >= patch.x_min) & (gx <= patch.x_max) & (gy >= patch.y_min) & (gy <= patch.y_max)
        truth[inside] = (CAT_FREE if patch.prob <= t_free else CAT_OCCUPIED if patch.prob >= t_blocked
                         else CAT_UNCERTAIN)
    for box in scene.boxes:
        truth[(gx >= box.x_min) & (gx <= box.x_max) & (gy >= box.y_min) & (gy <= box.y_max)] = CAT_OCCUPIED
    if ego is not None:
        truth[ego.contains(gx, gy)] = CAT_EGO
    return truth


# ---- dòng lệnh -------------------------------------------------------------------------------------------------------
def _common_args(p: argparse.ArgumentParser, grid_default, range_default) -> None:
    p.add_argument("--out", type=Path, help="thư mục ra (mặc định runs/bev/<tên>)")
    p.add_argument("--grid", type=float, nargs=5, metavar=("XMIN", "XMAX", "YMIN", "YMAX", "RES"), default=grid_default)
    p.add_argument("--t-free", type=float, default=DEFAULT_T_FREE, help="p ≤ ngưỡng này là FREE (mặc định %(default)s)")
    p.add_argument("--t-blocked", type=float, default=DEFAULT_T_BLOCKED,
                   help="p ≥ ngưỡng này là OCCUPIED (mặc định %(default)s)")
    p.add_argument("--max-range", type=float, default=range_default, help="m tính từ camera (mặc định %(default)s)")
    p.add_argument("--supersample", type=int, default=DEFAULT_SUPERSAMPLE)


def _print_summary(result: BevResult, stamp: SourceStamp, paths: dict, reasons: list) -> None:
    c = result.counts()
    print(f"BEV {result.grid.shape[0]}×{result.grid.shape[1]} ô: free {c['free']}, occupied {c['occupied']}, "
          f"không chắc {c['uncertain']}, bị che {c['occluded']}, ngoài tầm nhìn {c['unseen']}, thân xe {c['ego']}; "
          f"{len(result.views)} camera dùng, {result.timing_ms['total_ms']:.1f} ms", flush=True)
    for name, why in result.missing.items():
        print(f"  camera {name} không dùng: {why}")
    print("  dùng được cho lập đường: " + ("CÓ" if stamp.valid else "KHÔNG — " + "; ".join(reasons)))
    print(f"  -> {paths['image']}\n  -> {paths['costmap']}\n  -> {paths['stats']}")


def _cmd_synthetic(args) -> int:
    grid = GridSpec(*args.grid)
    cameras, ego = synthetic_rig(args.extrinsics)
    scene = DEFAULT_SCENE
    # chấp nhận số cổng như phần còn lại của dự án (--ports 1 2 3 4): "2" → "p2"; tên lạ thì từ chối, không để một
    # camera "bị bỏ" giả trong stats.json trong khi cả bốn camera vẫn được dùng
    drop = {f"p{int(d)}" if str(d).strip().isdecimal() else str(d).strip().lower() for d in (args.drop or [])}
    unknown = sorted(drop - set(cameras))
    if unknown:
        raise RigConfigError(f"--drop có tên không phải camera của rig: {unknown}; hợp lệ: {sorted(cameras)} "
                             f"(hoặc số cổng, ví dụ 2)")
    probs ={name: (None if name in drop else synthetic_prob_map(cam.calibration, scene, out_size=(480, 360)))
             for name, cam in cameras.items()}
    result = build_bev(probs, cameras, grid, t_free=args.t_free, t_blocked=args.t_blocked, max_range=args.max_range,
                       supersample=args.supersample, ego=ego,
                       missing={n: "bỏ theo --drop (thử camera thiếu)" for n in drop})
    reasons = ["dữ liệu TỔNG HỢP (camera ảo, nội tham danh định, ngoại tham giả định), không phải cảnh thật"]
    reasons += unusable_reasons(result, cameras)
    stamp = SourceStamp("bev_synthetic", 0.0, False, "vehicle")
    extra = {"input": {"kind": "synthetic", "scene": {"boxes": [b.__dict__ for b in scene.boxes],
                                                      "patches": [p.__dict__ for p in scene.patches],
                                                      "p_ground": scene.p_ground, "p_box": scene.p_box},
                       "prob_size": [480, 360], "intrinsics": "nominal_intrinsics(640, 480, 130° chéo)"},
             "extrinsics": {"path": str(args.extrinsics)}, "unusable_reasons": reasons}
    out = args.out or DEFAULT_OUT_ROOT / "tong_hop"
    paths = write_outputs(out, result, cameras, stamp, extra=extra, title="BEV synthetic (not measured)",
                          truth=synthetic_truth(scene, grid, args.t_free, args.t_blocked, ego))
    _print_summary(result, stamp, paths, reasons)
    return 0


def _cmd_snapshot(args) -> int:
    grid = GridSpec(*args.grid)
    result, cameras, stamp, extra = bev_from_snapshot(
        args.folder, extrinsics=args.extrinsics, calibration_dir=args.calibration_dir, roi_dir=args.roi_dir, grid=grid,
        t_free=args.t_free, t_blocked=args.t_blocked, max_range=args.max_range, supersample=args.supersample,
        max_skew_ms=args.max_skew_ms, skip_uncalibrated=args.skip_uncalibrated)
    out = args.out or DEFAULT_OUT_ROOT / Path(args.folder).name
    paths = write_outputs(out, result, cameras, stamp, extra=extra, title=f"BEV {Path(args.folder).name}")
    _print_summary(result, stamp, paths, extra["unusable_reasons"])
    return 0


def _cmd_woodscape(args) -> int:
    grid = GridSpec(*args.grid)
    if args.prob and len(args.prob) != len(args.image):
        raise RigConfigError("--prob phải có đúng một tệp cho mỗi --image, cùng thứ tự")
    if not args.prob and args.checkpoint is None:
        raise RigConfigError("cần --checkpoint (chạy mô hình, .venv-train) hoặc --prob (P×255 đã có)")
    ids = [Path(p).stem for p in args.image]
    if len(set(ids)) != len(ids):
        raise RigConfigError("mỗi ảnh chỉ được đưa vào một lần")
    cameras = {i: woodscape_camera(i, args.calibration_archive, None if args.no_roi else args.roi) for i in ids}
    if args.prob:
        probs = {i: read_gray(p) for i, p in zip(ids, args.prob)}
        prob_source = [str(p) for p in args.prob]
    else:
        images = [read_color(p) for p in args.image]
        probs = dict(zip(ids, woodscape_probabilities(images, args.checkpoint)))
        prob_source = f"LiveSegmenter({args.checkpoint})"
    result = build_bev(probs, cameras, grid, t_free=args.t_free, t_blocked=args.t_blocked, max_range=args.max_range,
                       supersample=args.supersample, ego=None)
    reasons = ["ảnh WoodScape: minh họa trên xe của Valeo, không phải cảnh quanh xe dự án"]
    reasons += unusable_reasons(result, cameras)
    if len(ids) > 1:
        reasons.append("các ảnh là những khung KHÁC thời điểm (WoodScape mỗi mã khung chỉ có một camera): không phải một "
                       "cảnh đồng bộ, chỉ để thử luồng hợp nhất")
    stamp = SourceStamp("bev_woodscape", 0.0, False, "vehicle")
    extra = {"input": {"kind": "woodscape", "images": [str(p) for p in args.image], "prob_source": prob_source,
                       "calibration_archive": str(args.calibration_archive),
                       "roi": None if args.no_roi else str(args.roi),
                       "ego": "không có hộp thân xe (ROI loại pixel thân xe trong ảnh)"},
             "unusable_reasons": reasons,
             "license": "Valeo WoodScape Dataset (https://woodscape.valeo.com): điều khoản cấm dùng mô hình huấn luyện "
                        "trên nó để vận hành phương tiện — xem docs/GIAY_PHEP_DU_LIEU.md"}
    out = args.out or DEFAULT_OUT_ROOT / ("woodscape_" + "_".join(ids))
    paths = write_outputs(out, result, cameras, stamp, extra=extra, title="BEV WoodScape " + " ".join(ids))
    _print_summary(result, stamp, paths, reasons)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BEV chiếm chỗ từ AI của nhiều camera (docs/BEV.md)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("synthetic", help="cảnh tổng hợp: 4 camera ảo, hộp và dải không chắc chắn đã biết")
    _common_args(p, RIG_GRID, RIG_MAX_RANGE)
    p.add_argument("--extrinsics", type=Path, default=DEFAULT_EXTRINSICS)
    p.add_argument("--drop", nargs="*", help="camera coi như thiếu: số cổng (2) hoặc tên (p2)")
    p.set_defaults(func=_cmd_synthetic)

    p = sub.add_parser("snapshot", help="một thư mục runs/rig_snapshots/<ngày_giờ> (prob_blocked_p*.png + meta.json)")
    p.add_argument("folder", type=Path)
    _common_args(p, RIG_GRID, RIG_MAX_RANGE)
    p.add_argument("--extrinsics", type=Path, default=DEFAULT_EXTRINSICS)
    p.add_argument("--calibration-dir", type=Path, default=DEFAULT_CALIBRATION_DIR)
    p.add_argument("--roi-dir", type=Path, help="thư mục có roi_p<cổng>.png (cỡ ảnh gốc, 255 = dùng được)")
    p.add_argument("--max-skew-ms", type=float, default=MAX_SKEW_MS)
    p.add_argument("--skip-uncalibrated", action="store_true",
                   help="bỏ camera chưa có nội tham (vùng của nó UNKNOWN) thay vì từ chối")
    p.set_defaults(func=_cmd_snapshot)

    p = sub.add_parser("woodscape", help="ảnh WoodScape với hiệu chuẩn riêng của từng ảnh")
    p.add_argument("--image", type=Path, nargs="+", required=True, help="datasets/training/woodscape/rgb_images/<id>.png")
    p.add_argument("--prob", type=Path, nargs="+", help="P(BLOCKED)×255 cùng thứ tự với --image")
    p.add_argument("--checkpoint", type=Path, help="chạy mô hình (cần torch: .venv-train)")
    p.add_argument("--calibration-archive", type=Path, default=PROJECT / "datasets/woodscape_metadata/calibration.zip")
    p.add_argument("--roi", type=Path, default=PROJECT / "configs/roi/woodscape_v1")
    p.add_argument("--no-roi", action="store_true")
    _common_args(p, WOODSCAPE_GRID, WOODSCAPE_MAX_RANGE)
    p.set_defaults(func=_cmd_woodscape)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RigConfigError, ValueError) as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
