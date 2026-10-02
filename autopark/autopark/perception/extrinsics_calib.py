"""Ngoại tham camera mắt cá: bảng ô vuông nằm PHẲNG trên sàn ở vị trí đo bằng thước trong hệ xe (kế hoạch giai đoạn 2).

    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.ui.roi_app --port 1
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.extrinsics_calib solve --placements runs/extrinsics/dat_bang_p1.json --out configs/rig/camera_rig_extrinsics_v1.json
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.extrinsics_calib solve --port 1 --place runs/rig_snapshots/<ngày_giờ>/cam_p1.png 0.45 0.15 0.45 -0.09 --square-mm <cỡ ô ĐO ĐƯỢC>
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.extrinsics_calib check configs/rig/camera_rig_extrinsics_v1.json
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.extrinsics_calib synthetic --out runs/extrinsics/tong_hop
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.extrinsics_calib solve --placements runs/extrinsics/tong_hop/dat_bang_p1.json --out runs/extrinsics/tong_hop/camera_rig_tong_hop.json --allow-synthetic

Mỗi lệnh viết trên MỘT dòng (dán được vào cmd.exe); thay `<...>` bằng giá trị thật. Số trên dòng lệnh viết dấu chấm hay
dấu phẩy thập phân đều được (`0.45` hay `0,45`). Cách đo từng bước: docs/NGOAI_THAM_VA_ROI.md.

**Hệ xe** (như configs/rig/camera_rig_extrinsics_v0.json và perception/bev.py): x hướng trước, y sang trái, z lên; gốc
trên mặt sàn, dưới tâm trục sau. **Hệ bảng**: gốc ở góc trong O = góc trong (0, 0) — góc trong sát ô ĐEN ở góc trên-trái
của tờ in (dòng chữ in ở trên, đọc xuôi); trục x dọc hàng `cols` góc trong sang phải, trục y dọc `rows` góc trong xuống
dưới, z = x × y chỉ VÀO tờ giấy — nên khi bảng nằm ngửa trên sàn, z của bảng chỉ xuống sàn và nhìn từ trên xuống trục y
của bảng nằm bên PHẢI trục x (quay −90°). Các góc trong có tên: O (0, 0), A (cols−1, 0), B (0, rows−1), C (cols−1, rows−1).

**Đầu vào mỗi lần đặt bảng:** một ảnh tĩnh của camera (ảnh sống chụp từ giao diện, hay `cam_p<cổng>.png` của một bộ ảnh
`runs/rig_snapshots/<ngày_giờ>`) và tọa độ (x, y) trong hệ xe, đo bằng thước, của ÍT NHẤT HAI góc trong (thường là O và A;
thêm B để kiểm), hoặc O cộng hướng trục x của bảng (`yaw_deg`). Mặt in cao `board_z_m` trên sàn (bảng dán trên tấm xốp
5 mm thì 0,005). Tư thế bảng → xe tính bằng khớp cứng 2D (Procrustes) các điểm đo với vị trí danh định của chúng; sai
lệch sau khớp lớn hơn `TAPE_TOLERANCE_M` thì TỪ CHỐI lần đặt đó (số đo thước không khớp cỡ bảng).

**Cách giải:**
1. Dò góc bằng `fisheye_calib.detect_corners` (cùng bộ dò + `cornerSubPix` với hiệu chuẩn nội tham), bỏ khung MJPEG hỏng.
2. Thứ tự góc do OpenCV trả có thể bắt đầu ở một trong hai đầu bảng (trên ảnh tổng hợp bảng nằm trên sàn, OpenCV 5.0.0
   trả thứ tự NGƯỢC ở mọi ảnh đã thử, 24/09/2026). Thử cả 4 cách đánh số (giữ, xoay 180°, lật hàng, lật cột); với mỗi
   cách giải tư thế bảng → camera, bỏ cách nào đặt camera DƯỚI mặt bảng, rồi chọn theo màu: chiếu tâm mọi ô của bảng in
   lên ảnh, ô (ix, iy) phải ĐEN khi ix + iy chẵn (ô góc trên-trái đen). Hai phép kiểm cần nhau: màu ô không đổi khi lật
   thứ tự hàng (rows chẵn), còn xoay 180° đảo màu khi `cols + rows` lẻ (9 × 6 được; bảng có cols + rows chẵn bị từ
   chối). Ảnh LẬT GƯƠNG (driver bật mirror/flip) KHÔNG phát hiện được từ một lần đặt (một bảng phản chiếu vẫn khớp một
   khung bảng hợp lệ); nhiều lần đặt ở vị trí/hướng khác nhau thì không khớp nhau và bị từ chối ở bước 4 (kiểm trên ảnh
   tổng hợp).
3. Tư thế bảng → camera: khởi tạo bằng `cv2.fisheye.solvePnP` (có trong OpenCV 5.0.0 của cả hai môi trường, kiểm
   24/09/2026; nó chỉ khử méo điểm rồi gọi `cv2.solvePnP`, sai số tính trong mặt phẳng chuẩn hóa) và cả hai nghiệm IPPE
   trên điểm đã khử méo (bảng phẳng có thể có hai nghiệm), rồi tinh chỉnh Levenberg–Marquardt để cực tiểu sai số chiếu
   lại TÍNH BẰNG ĐIỂM ẢNH qua `cv2.fisheye.projectPoints` (mô hình Kannala–Brandt của tệp nội tham). Không có
   `cv2.fisheye.solvePnP` thì chỉ dùng nhánh khử méo + IPPE. Trên ảnh tổng hợp lợi ích của bước tinh chỉnh nhỏ (một
   cảnh thử: RMS 0,5802 → 0,5799 px với nhiễu góc 0,4 px); lợi ích ở θ lớn (mép ảnh mắt cá) CHƯA ĐO.
4. Camera → xe = (bảng → xe) ∘ (camera → bảng) cho từng lần đặt; rồi giải CHUNG một tư thế camera trên mọi lần đặt (điểm
   góc của mọi lần đặt đã đưa sang hệ xe). Lần đặt nào lệch tư thế chung quá `MAX_POSITION_SPREAD_M` / `MAX_ANGLE_SPREAD_DEG`
   thì bị loại dần (lần tệ nhất trước, khi còn ≥ 3 lần); còn lệch mà không loại được thì TỪ CHỐI.
5. Báo: RMS chiếu lại (px), RMS qua mô hình đa thức của dự án (`FisheyeIntrinsics`, đúng mô hình BEV dùng), vị trí, độ cao,
   yaw / pitch_down / roll theo quy ước của tệp rig, độ lệch giữa các lần đặt, các phép kiểm. Mọi ngưỡng dưới đây là
   ĐỀ XUẤT – CHỜ CHỐT, chưa kiểm trên camera thật.

**Ghi tệp rig:** `write_rig_file` chép tệp gốc (mặc định v0), thay camera đã đo bằng `quaternion_xyzw` + `position_m` +
`"measured": true` + nguồn gốc (ngày, các lần đặt bảng, RMS), rồi đọc lại bằng `bev.load_rig_extrinsics` và so từng số.
Không bao giờ ghi đè im lặng: tệp ra đã có thì từ chối, trừ khi có `overwrite` (bản cũ được sao lưu cạnh nó, tên sao lưu
giữ chỗ độc quyền nên không đè một bản sao lưu khác). Không ghi vào tệp v0 (hồ sơ giả định).

**Kết quả TỔNG HỢP** (nội tham của camera ảo `synthetic`, `"synthetic": true` hay `device` = "TỔNG HỢP") không bao giờ
được ghi như số đo: mặc định từ chối; có `allow_synthetic` (`--allow-synthetic`) thì ghi được nhưng camera và cả tệp mang
`"synthetic": true`, `basis`/`status` mở đầu "TỔNG HỢP — KHÔNG PHẢI SỐ ĐO", và tệp ra không được nằm trong `configs/` hay
`calibration/` của dự án (luôn từ chối). `"measured": true` vẫn giữ để thử nối trọn BEV trên ảnh tổng hợp — nên chỉ nhãn
và chỗ ghi ngăn nhầm; từ 25/09/2026 bev.py còn đọc khóa `synthetic` và ghi lý do "không dùng được". Tệp gốc có camera
tổng hợp cũng cần `allow_synthetic`.

**Tình trạng 24/09/2026:** chỉ kiểm trên ảnh TỔNG HỢP (tests/test_extrinsics_calib.py). Chưa có camera nào được hiệu
chuẩn nội tham (`calibration/cam_p*.json` chưa có), chưa có xe MN300, chưa gá camera: công cụ CHƯA THỬ trên camera thật.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
import json
import math
from pathlib import Path
import shutil
import sys

import cv2
import numpy as np

from . import fisheye_calib as fc
from .calib_board import BoardSpec
from .calibration import Extrinsics
from .paths import PROJECT, atomic_write_json

PLACEMENTS_FORMAT = "autopark.extrinsics_placements/1"
DEFAULT_BASE = PROJECT / "configs/rig/camera_rig_extrinsics_v0.json"
DEFAULT_OUT = PROJECT / "configs/rig/camera_rig_extrinsics_v1.json"
DEFAULT_RUNS = PROJECT / "runs/extrinsics"
SYNTHETIC_MARK = "TỔNG HỢP"
SYNTHETIC_FORBIDDEN_DIRS = (PROJECT / "configs", PROJECT / "calibration")   # kết quả tổng hợp không bao giờ ghi vào đây
SYNTHETIC_RIG_NAME = "camera_rig_tong_hop.json"

# ---- ngưỡng (ĐỀ XUẤT – CHỜ CHỐT, chưa kiểm trên camera thật) --------------------------------------------------------
TAPE_TOLERANCE_M = 0.005        # sai lệch lớn nhất của một điểm đo thước sau khớp cứng với cỡ bảng
MAX_PLACEMENT_RMS_PX = 1.0      # RMS chiếu lại của một lần đặt dưới tư thế riêng của nó
MAX_JOINT_RMS_PX = 4.0          # RMS dưới tư thế chung: phần lớn là sai số thước (±2,5 mm → trung vị 1,3 px, tổng hợp)
MIN_CAMERA_HEIGHT_M = 0.02      # camera phải ở trên mặt sàn ít nhất chừng này
MAX_CAMERA_HEIGHT_M = 1.0       # xe 1/12: camera cao hơn thế này là nhập sai số đo / sai cỡ ô
BOARD_DISTANCE_M = (0.08, 2.5)  # khoảng cách camera → tâm bảng hợp lý
MAX_POSITION_SPREAD_M = 0.02    # vị trí camera suy từ một lần đặt lệch tư thế chung tối đa chừng này
MAX_ANGLE_SPREAD_DEG = 1.0      # góc quay giữa hướng camera của một lần đặt và hướng chung tối đa chừng này
MIN_PLACEMENTS = 2              # một lần đặt không kiểm chéo được số đo thước
MIN_COLOR_CONTRAST = 30.0       # ô trắng − ô đen (0..255) để chọn hướng đánh số bảng
MIN_EDGE_MARGIN_PX = 3.0        # góc trong cách mép ảnh ít nhất chừng này
THRESHOLDS = {"tape_tolerance_m": TAPE_TOLERANCE_M, "max_placement_rms_px": MAX_PLACEMENT_RMS_PX,
              "max_joint_rms_px": MAX_JOINT_RMS_PX,
              "camera_height_m": [MIN_CAMERA_HEIGHT_M, MAX_CAMERA_HEIGHT_M],
              "board_distance_m": list(BOARD_DISTANCE_M), "max_position_spread_m": MAX_POSITION_SPREAD_M,
              "max_angle_spread_deg": MAX_ANGLE_SPREAD_DEG, "min_placements": MIN_PLACEMENTS,
              "min_color_contrast": MIN_COLOR_CONTRAST, "status": "ĐỀ XUẤT – CHỜ CHỐT, chưa kiểm trên camera thật"}

NAMED_CORNERS = ("O", "A", "B", "C")
DIRECTIONS = {"front": 0.0, "left": 90.0, "rear": 180.0, "right": -90.0}


class ExtrinsicsError(RuntimeError):
    """Đầu vào không dùng được: báo bằng tiếng Việt, người dùng sửa được."""


def named_corner(name: str, spec: BoardSpec) -> tuple[int, int]:
    """Tên góc trong → chỉ số (i, j) (i dọc hàng `cols`, j dọc `rows`)."""
    table = {"O": (0, 0), "A": (spec.cols - 1, 0), "B": (0, spec.rows - 1), "C": (spec.cols - 1, spec.rows - 1)}
    key = str(name).strip().upper()
    if key in table:
        return table[key]
    try:
        i, j = (int(v) for v in key.replace(";", ",").split(","))
    except ValueError as exc:
        raise ExtrinsicsError(f"tên góc {name!r} không hiểu: dùng O, A, B, C hoặc 'i,j'") from exc
    if not (0 <= i < spec.cols and 0 <= j < spec.rows):
        raise ExtrinsicsError(f"góc ({i}, {j}) ngoài bảng {spec.cols}×{spec.rows} góc trong")
    return i, j


def check_spec(spec: BoardSpec) -> None:
    if (spec.cols + spec.rows) % 2 == 0:
        raise ExtrinsicsError(f"bảng {spec.cols}×{spec.rows} góc trong có cols + rows chẵn: xoay 180° cho cùng màu ô, không "
                              f"xác định được góc O. Dùng bảng 9×6 (bảng in sẵn trong calibration/bang_in/)")


# ---- tư thế bảng trên sàn (đo bằng thước) ----------------------------------------------------------------------------
@dataclass(frozen=True)
class BoardPlacement:
    """Tư thế một lần đặt bảng, đo bằng thước trong hệ xe (mét).

    `points`: {tên góc ("O", "A", "B", "C" hoặc "i,j"): (x, y)} — ít nhất hai điểm; hoặc một điểm "O" cùng `yaw_deg`
    (hướng trục x của bảng, từ +x của xe, dương ngược chiều kim đồng hồ). `board_z_m`: độ cao mặt in trên sàn."""
    points: tuple = ()                 # ((tên, x, y), ...) — tuple để dataclass băm được
    yaw_deg: float | None = None
    board_z_m: float = 0.0

    @classmethod
    def from_points(cls, points: dict, yaw_deg: float | None = None, board_z_m: float = 0.0) -> "BoardPlacement":
        return cls(tuple((str(k), float(v[0]), float(v[1])) for k, v in points.items()), yaw_deg, float(board_z_m))

    def points_dict(self) -> dict:
        return {name: (x, y) for name, x, y in self.points}

    def to_dict(self) -> dict:
        out = {"points_xy_m": {name: [x, y] for name, x, y in self.points}, "board_z_m": self.board_z_m}
        if self.yaw_deg is not None:
            out["yaw_deg"] = self.yaw_deg
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "BoardPlacement":
        points = dict(data.get("points_xy_m") or {})
        for key, name in (("origin_xy_m", "O"), ("x_axis_point_xy_m", "A"), ("check_point_xy_m", "B")):
            if key in data and data[key] is not None:
                points[name] = data[key]
        try:
            return cls.from_points({k: (float(v[0]), float(v[1])) for k, v in points.items()},
                                   None if data.get("yaw_deg") is None else float(data["yaw_deg"]),
                                   float(data.get("board_z_m", 0.0)))
        except (TypeError, ValueError, IndexError) as exc:
            raise ExtrinsicsError(f"tư thế bảng sai định dạng ({exc}): cần points_xy_m "
                                  f"{{\"O\": [x, y], \"A\": [x, y]}}") from exc


@dataclass
class BoardPose:
    """Bảng → xe: R (cột = trục x, y, z của bảng trong hệ xe), t = vị trí góc O."""
    R: np.ndarray
    t: np.ndarray
    yaw_deg: float
    residuals_m: dict            # tên điểm → sai lệch sau khớp (m)
    span_check: str

    @property
    def max_residual_m(self) -> float:
        return max(self.residuals_m.values()) if self.residuals_m else 0.0


def board_rotation(yaw_deg: float) -> np.ndarray:
    """Bảng nằm ngửa trên sàn, trục x của bảng quay `yaw_deg` từ +x của xe: trục y của bảng = x quay −90°, z xuống."""
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    return np.array([[c, s, 0.0], [s, -c, 0.0], [0.0, 0.0, -1.0]])


def board_pose(placement: BoardPlacement, spec: BoardSpec, tolerance_m: float = TAPE_TOLERANCE_M) -> BoardPose:
    """Khớp cứng 2D các điểm đo với vị trí danh định (i·ô, −j·ô) (trục y của bảng nằm bên phải trục x khi nhìn từ trên
    xuống). Từ chối khi thiếu điểm, điểm trùng, hay sai lệch sau khớp > tolerance_m."""
    s = spec.square_mm / 1000.0
    pts = placement.points_dict()
    if not all(math.isfinite(v) for xy in pts.values() for v in xy) or not math.isfinite(placement.board_z_m):
        raise ExtrinsicsError("số đo thước phải là số hữu hạn")
    if not 0.0 <= placement.board_z_m <= 0.05:
        raise ExtrinsicsError(f"board_z_m = {placement.board_z_m} m vô lý (độ dày tấm dán bảng, 0..0,05 m)")
    idx = {name: named_corner(name, spec) for name in pts}
    if len(set(idx.values())) != len(idx):
        raise ExtrinsicsError("hai tên điểm trỏ cùng một góc trong")
    if placement.yaw_deg is not None:
        if "O" not in pts and (0, 0) not in idx.values():
            raise ExtrinsicsError("khai yaw_deg thì phải có tọa độ góc O")
        yaw = float(placement.yaw_deg)
        R = board_rotation(yaw)
        o_name = next(n for n, v in idx.items() if v == (0, 0))
        origin = np.array(pts[o_name], np.float64)
        residuals = {}
        for name, (i, j) in idx.items():
            pred = origin + R[:2, :2] @ np.array([i * s, j * s])
            residuals[name] = float(np.linalg.norm(pred - np.array(pts[name])))
        span_check = "yaw_deg khai tay" + ("" if len(pts) == 1 else f" + {len(pts) - 1} điểm kiểm")
    else:
        if len(pts) < 2:
            raise ExtrinsicsError("cần tọa độ ít nhất hai góc trong (ví dụ O và A), hoặc O cùng yaw_deg")
        names = list(pts)
        q = np.array([[idx[n][0] * s, -idx[n][1] * s] for n in names])        # hệ 2D thuận: y của bảng lật dấu
        m = np.array([pts[n] for n in names], np.float64)
        if np.linalg.norm(q - q[0], axis=1).max() < 1e-9:
            raise ExtrinsicsError("các điểm đo trùng nhau trên bảng")
        qc, mc = q - q.mean(axis=0), m - m.mean(axis=0)
        yaw_rad = math.atan2(float(np.sum(qc[:, 0] * mc[:, 1] - qc[:, 1] * mc[:, 0])), float(np.sum(qc * mc)))
        c, sn = math.cos(yaw_rad), math.sin(yaw_rad)
        rot = np.array([[c, -sn], [sn, c]])
        origin = m.mean(axis=0) - rot @ q.mean(axis=0)
        residuals = {n: float(np.linalg.norm(origin + rot @ q[k] - m[k])) for k, n in enumerate(names)}
        yaw = math.degrees(yaw_rad)
        R = board_rotation(yaw)
        spans = []
        for a in range(len(names)):
            for b in range(a + 1, len(names)):
                spans.append(f"{names[a]}{names[b]} đo {1000 * np.linalg.norm(m[a] - m[b]):.1f} mm / danh định "
                             f"{1000 * np.linalg.norm(q[a] - q[b]):.1f} mm")
        span_check = "; ".join(spans)
    worst = max(residuals.values()) if residuals else 0.0
    if worst > tolerance_m:
        raise ExtrinsicsError(
            f"số đo thước không khớp cỡ bảng: sai lệch lớn nhất sau khớp {1000 * worst:.1f} mm > {1000 * tolerance_m:g} mm "
            f"({span_check}). Kiểm lại: đúng góc trong O/A/B chưa, cỡ ô ĐO ĐƯỢC đúng chưa, bảng có bị xê dịch khi đo")
    t = np.array([origin[0], origin[1], placement.board_z_m], np.float64)
    return BoardPose(R, t, (yaw + 180.0) % 360.0 - 180.0, residuals, span_check)


# ---- chiếu và giải tư thế ----------------------------------------------------------------------------------------------
def project_points(points: np.ndarray, rvec, tvec, K, D) -> np.ndarray:
    """(N, 3) điểm trong hệ vật → (N, 2) điểm ảnh qua mô hình Kannala–Brandt của cv2.fisheye."""
    pts = np.asarray(points, np.float64).reshape(1, -1, 3)
    return cv2.fisheye.projectPoints(pts, np.asarray(rvec, np.float64).reshape(3, 1),
                                     np.asarray(tvec, np.float64).reshape(3, 1), np.asarray(K, np.float64),
                                     np.asarray(D, np.float64).reshape(4, 1))[0].reshape(-1, 2)


def refine_pose(obj: np.ndarray, img: np.ndarray, rvec, tvec, K, D, iterations: int = 50) -> tuple:
    """Levenberg–Marquardt trên sai số chiếu lại TÍNH BẰNG ĐIỂM ẢNH (Jacobian số). Trả (rvec, tvec, sai số từng điểm)."""
    obj = np.asarray(obj, np.float64)
    img = np.asarray(img, np.float64).reshape(-1, 2)
    p = np.r_[np.asarray(rvec, np.float64).ravel(), np.asarray(tvec, np.float64).ravel()]

    def resid(q):
        with np.errstate(all="ignore"):
            r = (project_points(obj, q[:3], q[3:], K, D) - img).ravel()
        return r if np.all(np.isfinite(r)) else np.full(r.shape, 1e6)

    r = resid(p)
    cost = float(r @ r)
    lam = 1e-3
    for _ in range(iterations):
        J = np.empty((r.size, 6))
        for k in range(6):
            h = 1e-7 * max(1.0, abs(p[k]))
            q = p.copy()
            q[k] += h
            J[:, k] = (resid(q) - r) / h
        A, g = J.T @ J, J.T @ r
        improved = False
        while lam < 1e12:
            try:
                step = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-12), -g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            q = p + step
            rq = resid(q)
            cq = float(rq @ rq)
            if cq < cost:
                p, r, improved = q, rq, True
                done = cost - cq < 1e-14 * max(1.0, cost) or np.linalg.norm(step) < 1e-12
                cost = cq
                lam = max(lam / 10, 1e-12)
                break
            lam *= 10
        if not improved or done:
            break
    err = np.linalg.norm(r.reshape(-1, 2), axis=1)
    return p[:3].copy(), p[3:].copy(), err


def _initial_poses(obj: np.ndarray, img: np.ndarray, K, D) -> list:
    """Các điểm khởi tạo: cv2.fisheye.solvePnP (nếu có) và hai nghiệm IPPE trên điểm đã khử méo."""
    out = []
    K = np.asarray(K, np.float64)
    D4 = np.asarray(D, np.float64).reshape(4, 1)
    if hasattr(cv2.fisheye, "solvePnP"):
        try:          # OpenCV 5.0.0 nhận (1, N, 3) / (1, N, 2); (N, 3) báo lỗi kích thước (kiểm 24/09/2026)
            ok, rv, tv = cv2.fisheye.solvePnP(obj.reshape(1, -1, 3), img.reshape(1, -1, 2).astype(np.float64), K, D4)
            if ok:
                out.append((rv.ravel(), tv.ravel()))
        except cv2.error:
            pass
    und = cv2.fisheye.undistortPoints(img.reshape(-1, 1, 2).astype(np.float64), K, D4).reshape(-1, 2)
    if np.all(np.isfinite(und)):
        planar = np.ptp(obj[:, 2]) < 1e-9
        try:
            if planar:
                n, rvs, tvs, _ = cv2.solvePnPGeneric(obj - np.array([0, 0, obj[0, 2]]), und, np.eye(3), None,
                                                     flags=cv2.SOLVEPNP_IPPE)
                shift = np.array([0.0, 0.0, obj[0, 2]])
                for rv, tv in zip(rvs[:n], tvs[:n]):     # bù phần dịch z đã trừ để IPPE nhận mặt z = 0
                    R = cv2.Rodrigues(rv)[0]
                    out.append((rv.ravel(), (tv.ravel() - R @ shift)))
            else:
                ok, rv, tv = cv2.solvePnP(obj, und, np.eye(3), None, flags=cv2.SOLVEPNP_SQPNP)
                if ok:
                    out.append((rv.ravel(), tv.ravel()))
        except cv2.error:
            pass
    return out


def solve_pose(obj: np.ndarray, img: np.ndarray, K, D) -> tuple:
    """Tư thế vật → camera cực tiểu sai số chiếu lại (px). Trả (rvec, tvec, sai số từng điểm) hoặc ném ExtrinsicsError."""
    best = None
    for rv, tv in _initial_poses(obj, img, K, D):
        rv2, tv2, err = refine_pose(obj, img, rv, tv, K, D)
        R = cv2.Rodrigues(rv2)[0]
        cam_z = (np.asarray(obj) @ R.T + tv2)[:, 2]
        if np.any(cam_z <= 0):                 # điểm sau camera: nghiệm vô nghĩa
            continue
        cost = float(np.mean(err ** 2))
        if best is None or cost < best[0]:
            best = (cost, rv2, tv2, err)
    if best is None:
        raise ExtrinsicsError("không giải được tư thế bảng (PnP không hội tụ)")
    return best[1], best[2], best[3]


# ---- đánh số góc bảng theo màu ô ---------------------------------------------------------------------------------------
ORDERINGS = ("identity", "rot180", "flip_rows", "flip_cols")


def reorder(corners: np.ndarray, spec: BoardSpec, ordering: str) -> np.ndarray:
    g = np.asarray(corners).reshape(spec.rows, spec.cols, 2)
    if ordering == "rot180":
        g = g[::-1, ::-1]
    elif ordering == "flip_rows":
        g = g[::-1, :]
    elif ordering == "flip_cols":
        g = g[:, ::-1]
    elif ordering != "identity":
        raise ValueError(ordering)
    return g.reshape(-1, 2).copy()


def square_centres(spec: BoardSpec) -> tuple[np.ndarray, np.ndarray]:
    """Tâm mọi ô của bảng in (hệ bảng, mét) và màu mong đợi (True = đen): ô (ix, iy) đen khi ix + iy chẵn — ô góc
    trên-trái đen, như `calib_board.PageLayout.black_squares`."""
    s = spec.square_mm / 1000.0
    iy, ix = np.mgrid[0:spec.rows + 1, 0:spec.cols + 1]
    centres = np.column_stack([(ix.ravel() - 0.5) * s, (iy.ravel() - 0.5) * s, np.zeros(ix.size)])
    return centres, ((ix + iy).ravel() % 2 == 0)


def _sample(gray: np.ndarray, uv: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    u, v = uv[:, 0], uv[:, 1]
    ok = np.isfinite(u) & np.isfinite(v) & (u >= 0) & (u <= w - 1) & (v >= 0) & (v <= h - 1)
    out = np.full(len(uv), np.nan)
    out[ok] = cv2.remap(gray.astype(np.float32), u[ok].astype(np.float32).reshape(-1, 1),
                        v[ok].astype(np.float32).reshape(-1, 1), cv2.INTER_LINEAR).ravel()
    return out


@dataclass
class OrientedBoard:
    corners: np.ndarray              # (N, 2) theo thứ tự BoardSpec.object_points (O đầu tiên)
    ordering: str
    rvec: np.ndarray                 # bảng → camera
    tvec: np.ndarray
    errors_px: np.ndarray
    color_contrast: float            # ô trắng − ô đen theo cách đánh số đã chọn
    candidates: dict                 # cách đánh số → {camera_above_board, color_contrast, rms_px}


def orient_board(image: np.ndarray, corners: np.ndarray, spec: BoardSpec, K, D) -> OrientedBoard:
    check_spec(spec)
    gray = fc.to_gray(image)
    obj = spec.object_points()
    centres, black = square_centres(spec)
    found, info = [], {}
    for ordering in ORDERINGS:
        c = reorder(corners, spec, ordering)
        try:
            rv, tv, err = solve_pose(obj, c, K, D)
        except ExtrinsicsError:
            info[ordering] = {"solved": False}
            continue
        R = cv2.Rodrigues(rv)[0]
        cam_in_board = -R.T @ tv
        above = bool(cam_in_board[2] < 0)          # z của bảng chỉ vào tờ giấy: camera nhìn mặt in thì z < 0
        vals = _sample(gray, project_points(centres, rv, tv, K, D))
        ok = np.isfinite(vals)
        contrast = (float(np.mean(vals[ok & ~black]) - np.mean(vals[ok & black]))
                    if (ok & black).any() and (ok & ~black).any() else float("nan"))
        info[ordering] = {"solved": True, "camera_above_board": above, "color_contrast": round(contrast, 1),
                          "rms_px": round(float(np.sqrt(np.mean(err ** 2))), 4)}
        found.append((ordering, c, rv, tv, err, above, contrast))
    # Hai phép kiểm bổ sung nhau: màu ô KHÔNG đổi khi lật thứ tự hàng (rows chẵn) hoặc cột (cols chẵn) — nên phải lọc
    # "camera ở trên mặt bảng" TRƯỚC (cách lật đặt camera dưới bảng), rồi mới chọn theo màu (xoay 180° đảo màu ô vì
    # cols + rows lẻ). Còn lại đúng một cách đánh số.
    above = [f for f in found if f[5] and math.isfinite(f[6])]
    if not above:
        raise ExtrinsicsError("mọi cách đánh số góc đều đặt camera DƯỚI mặt bảng: bảng nằm úp, hoặc nội tham không phải "
                              "của camera này")
    best = max(above, key=lambda f: f[6])
    if best[6] < MIN_COLOR_CONTRAST:
        raise ExtrinsicsError(f"không xác định được góc O của bảng: tương phản ô trắng − ô đen {best[6]:.0f} < "
                              f"{MIN_COLOR_CONTRAST:g} (ảnh tối/lóa, hoặc bảng in không phải bảng ô vuông đen-trắng)")
    return OrientedBoard(best[1], best[0], best[2], best[3], best[4], float(best[6]), info)


# ---- góc camera theo quy ước tệp rig -----------------------------------------------------------------------------------
def rig_angles(R_cv: np.ndarray) -> dict:
    """camera → xe → yaw_deg, pitch_down_deg, roll_deg theo quy ước `bev.rig_rotation` (nghịch đảo của hàm đó)."""
    R = np.asarray(R_cv, np.float64)
    z, x = R[:, 2], R[:, 0]
    pitch = math.asin(float(np.clip(-z[2], -1.0, 1.0)))
    yaw = math.atan2(float(z[1]), float(z[0])) if math.hypot(z[0], z[1]) > 1e-9 else 0.0
    x0 = np.array([math.sin(yaw), -math.cos(yaw), 0.0])
    y0 = np.cross(z, x0)
    roll = math.atan2(float(x @ y0), float(x @ x0))
    return {"yaw_deg": math.degrees(yaw), "pitch_down_deg": math.degrees(pitch), "roll_deg": math.degrees(roll)}


def direction_label(yaw_deg: float) -> str:
    return min(DIRECTIONS, key=lambda d: abs((yaw_deg - DIRECTIONS[d] + 180.0) % 360.0 - 180.0))


def rotation_angle_deg(Ra: np.ndarray, Rb: np.ndarray) -> float:
    c = (np.trace(np.asarray(Ra).T @ np.asarray(Rb)) - 1.0) / 2.0
    return math.degrees(math.acos(float(np.clip(c, -1.0, 1.0))))


# ---- nội tham -------------------------------------------------------------------------------------------------------
def intrinsics_is_synthetic(record: dict | None) -> bool:
    """Tệp nội tham của camera ẢO (lệnh `synthetic`, hay test): `"synthetic": true`, camera.device = "TỔNG HỢP", hoặc
    acceptance.status / note mở đầu bằng "TỔNG HỢP"."""
    if not isinstance(record, dict):
        return False
    if record.get("synthetic") is True:
        return True
    camera = record.get("camera") if isinstance(record.get("camera"), dict) else {}
    if str(camera.get("device", "")).strip().upper() == SYNTHETIC_MARK:
        return True
    acceptance = record.get("acceptance") if isinstance(record.get("acceptance"), dict) else {}
    return any(str(text).strip().upper().startswith(SYNTHETIC_MARK)
               for text in (acceptance.get("status", ""), record.get("note", "")))


@dataclass
class CameraIntrinsics:
    port: int
    path: str
    K: np.ndarray
    D: np.ndarray
    size: tuple
    record: dict
    acceptance_all_pass: bool | None
    theta_observed_max_deg: float | None

    @property
    def synthetic(self) -> bool:
        return intrinsics_is_synthetic(self.record)

    def project_model(self):
        """`FisheyeIntrinsics` (đa thức của dự án — mô hình BEV dùng)."""
        return fc.load_intrinsics(self.path, width=self.size[0], height=self.size[1])


def load_camera_intrinsics(path, port: int | None = None) -> CameraIntrinsics:
    path = Path(path)
    if not path.exists():
        raise ExtrinsicsError(f"chưa có tệp nội tham {path}: hiệu chuẩn nội tham camera này trước "
                              f"(docs/HIEU_CHUAN_CAMERA.md) — ngoại tham không có nghĩa khi chưa có nội tham")
    try:
        record = fc.load_calibration(path)
        fc.load_intrinsics(path)            # cùng phép kiểm BEV dùng (khối đa thức phải ok)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        raise ExtrinsicsError(f"không nạp được nội tham {path}: {exc}") from exc
    if record["camera"]["hub_port"] is None:         # tệp cam_<tên>.json của camera ngoài hub (T11, 02/10/2026)
        raise ExtrinsicsError(f"{path} là nội tham của camera ngoài hub ({record['camera'].get('name')!r}): ngoại tham "
                              "và ROI chỉ dành cho camera xe theo cổng hub 1..4")
    hub = int(record["camera"]["hub_port"])
    if port is not None and hub != int(port):
        raise ExtrinsicsError(f"{path} là nội tham của camera cổng {hub}, không phải cổng {port}")
    K, D, size = fc.camera_model(record)
    fov = record.get("field_of_view_deg") or {}
    # cùng quy tắc với BEV (25/09/2026): chỉ true của JSON là đạt; chuỗi "false", 1, khối lạ… là CHƯA đạt
    from .bev import acceptance_flag     # nhập muộn như các chỗ khác: bev nhập lại mô-đun này
    acc = acceptance_flag(record)
    return CameraIntrinsics(hub, str(path), K, D, (int(size[0]), int(size[1])), record,
                            acc, fov.get("theta_observed_max_deg"))


def default_intrinsics_path(port: int, size=fc.DEFAULT_SIZE, calibration_dir=PROJECT / "calibration") -> Path:
    return fc.default_output_path(port, tuple(size), Path(calibration_dir))


# ---- một lần đặt bảng -------------------------------------------------------------------------------------------------
@dataclass
class PlacementInput:
    name: str
    image: np.ndarray
    placement: BoardPlacement
    image_path: str | None = None


@dataclass
class PlacementResult:
    name: str
    image_path: str | None
    placement: BoardPlacement
    used: bool = False
    reason: str | None = None
    corners: np.ndarray | None = None        # đã đánh số (O đầu tiên)
    ordering: str | None = None
    board: BoardPose | None = None
    rms_px: float | None = None              # dưới tư thế riêng của lần đặt này
    max_px: float | None = None
    R_cv: np.ndarray | None = None           # camera → xe suy từ riêng lần đặt này
    t_cv: np.ndarray | None = None
    board_distance_m: float | None = None
    corner_theta_max_deg: float | None = None
    min_margin_px: float | None = None
    color_contrast: float | None = None
    rms_joint_px: float | None = None        # dưới tư thế chung
    deviation_m: float | None = None         # vị trí camera của lần này − vị trí chung
    deviation_deg: float | None = None
    vehicle_points: np.ndarray | None = None  # góc trong bảng trong hệ xe (N, 3)
    spec: BoardSpec | None = None             # thông số bảng đã dùng để dò/giải lần đặt này

    def to_dict(self) -> dict:
        r = lambda x, nd=4: None if x is None else round(float(x), nd)
        out = {"name": self.name, "image": self.image_path, "used": self.used, "rejected_reason": self.reason,
               "measured": self.placement.to_dict(), "ordering": self.ordering,
               "rms_px": r(self.rms_px), "max_px": r(self.max_px), "rms_joint_px": r(self.rms_joint_px),
               "deviation_m": r(self.deviation_m, 5), "deviation_deg": r(self.deviation_deg, 4),
               "board_distance_m": r(self.board_distance_m), "corner_theta_max_deg": r(self.corner_theta_max_deg, 2),
               "min_margin_px": r(self.min_margin_px, 1), "color_contrast": r(self.color_contrast, 1)}
        if self.board is not None:
            out["board_fit"] = {"origin_xy_m": [r(self.board.t[0], 5), r(self.board.t[1], 5)],
                                "yaw_deg": r(self.board.yaw_deg, 4),
                                "tape_residual_m": {k: r(v, 5) for k, v in self.board.residuals_m.items()},
                                "span_check": self.board.span_check}
        if self.t_cv is not None:
            out["camera_from_this_placement"] = {"position_m": [r(v, 5) for v in self.t_cv],
                                                 **{k: r(v, 4) for k, v in rig_angles(self.R_cv).items()}}
        return out


def _compose(board: BoardPose, rvec, tvec) -> tuple[np.ndarray, np.ndarray]:
    """(bảng → xe) ∘ (camera → bảng) = camera → xe."""
    R_bc = cv2.Rodrigues(np.asarray(rvec, np.float64))[0]
    R_cv = board.R @ R_bc.T
    t_cv = board.t - R_cv @ np.asarray(tvec, np.float64).ravel()
    return R_cv, t_cv


def analyse_placement(inp: PlacementInput, spec: BoardSpec, intr: CameraIntrinsics) -> PlacementResult:
    """Dò, đánh số, giải một lần đặt bảng. Lần đặt không dùng được thì `used` = False và `reason` ghi lý do."""
    res = PlacementResult(inp.name, inp.image_path, inp.placement, spec=spec)
    image = inp.image
    try:
        if image is None or image.ndim not in (2, 3):
            raise ExtrinsicsError("không có ảnh")
        size = (int(image.shape[1]), int(image.shape[0]))
        if size != tuple(intr.size):
            raise ExtrinsicsError(f"ảnh {size[0]}×{size[1]} khác cỡ đã hiệu chuẩn nội tham {intr.size[0]}×{intr.size[1]} "
                                  f"({intr.path}): mode camera khác thì nội tham này không dùng được")
        if image.ndim == 3:
            damaged = fc.damage_reason(image)
            if damaged:
                raise ExtrinsicsError(f"khung MJPEG hỏng: {damaged}; chụp lại")
        res.board = board_pose(inp.placement, spec)
        det = fc.detect_corners(image, spec, mode="accurate")
        if not det.found:
            raise ExtrinsicsError(f"không thấy đủ {spec.cols}×{spec.rows} góc trong của bảng: bảng phải nằm trọn trong "
                                  f"ảnh (cả viền trắng), đủ sáng, không lóa; bảng quá xa thì ô quá dẹt — đặt gần hơn")
        c = det.corners
        w, h = size
        res.min_margin_px = float(min(c[:, 0].min(), c[:, 1].min(), (w - 1) - c[:, 0].max(), (h - 1) - c[:, 1].max()))
        if res.min_margin_px < MIN_EDGE_MARGIN_PX:
            raise ExtrinsicsError(f"bảng sát mép ảnh ({res.min_margin_px:.1f} px): dời bảng vào trong")
        ob = orient_board(image, c, spec, intr.K, intr.D)
        res.corners, res.ordering, res.color_contrast = ob.corners, ob.ordering, ob.color_contrast
        res.rms_px = float(np.sqrt(np.mean(ob.errors_px ** 2)))
        res.max_px = float(ob.errors_px.max())
        R_bc = cv2.Rodrigues(ob.rvec)[0]
        centre_b = np.array([(spec.cols - 1) / 2, (spec.rows - 1) / 2, 0.0]) * spec.square_mm / 1000.0
        res.board_distance_m = float(np.linalg.norm(R_bc @ centre_b + ob.tvec))
        theta = fc.pixel_theta(res.corners[:, 0], res.corners[:, 1], intr.K, intr.D)
        res.corner_theta_max_deg = float(np.degrees(np.nanmax(theta))) if np.isfinite(theta).any() else None
        res.R_cv, res.t_cv = _compose(res.board, ob.rvec, ob.tvec)
        res.vehicle_points = spec.object_points() @ res.board.R.T + res.board.t
        if res.rms_px > MAX_PLACEMENT_RMS_PX:
            raise ExtrinsicsError(f"RMS chiếu lại {res.rms_px:.2f} px > {MAX_PLACEMENT_RMS_PX:g} px: bảng cong/không phẳng, "
                                  f"ảnh mờ, hoặc nội tham không khớp camera")
        lo, hi = BOARD_DISTANCE_M
        if not lo <= res.board_distance_m <= hi:
            raise ExtrinsicsError(f"bảng cách camera {res.board_distance_m:.2f} m, ngoài khoảng hợp lý {lo:g}–{hi:g} m: "
                                  f"kiểm cỡ ô đã nhập (mm, cỡ ĐO ĐƯỢC)")
        z = float(res.t_cv[2])
        if z < MIN_CAMERA_HEIGHT_M:
            raise ExtrinsicsError(f"lần đặt này đặt camera ở độ cao {z:.3f} m (dưới/sát mặt sàn): kiểm board_z_m, cỡ ô, "
                                  f"và nội tham có đúng camera này")
        if z > MAX_CAMERA_HEIGHT_M:
            raise ExtrinsicsError(f"lần đặt này đặt camera cao {z:.2f} m > {MAX_CAMERA_HEIGHT_M:g} m: vô lý với xe 1/12 — "
                                  f"kiểm cỡ ô (mm) và số đo thước (m)")
        res.used = True
    except ExtrinsicsError as exc:
        res.used, res.reason = False, str(exc)
    return res


# ---- nhiều lần đặt: tư thế chung --------------------------------------------------------------------------------------
@dataclass
class ExtrinsicsResult:
    port: int
    ok: bool
    refusals: list
    warnings: list
    placements: list
    intrinsics: CameraIntrinsics | None
    spec: BoardSpec
    R_cv: np.ndarray | None = None
    t_cv: np.ndarray | None = None
    rms_px: float | None = None
    max_px: float | None = None
    rms_model_px: float | None = None            # qua FisheyeIntrinsics (mô hình BEV)
    checks: list = field(default_factory=list)
    square_mm_measured: bool | None = None
    created_local: str = ""

    @property
    def used(self) -> list:
        return [p for p in self.placements if p.used]

    @property
    def synthetic(self) -> bool:
        """Giải bằng nội tham của camera ẢO: kết quả chỉ để thử, KHÔNG PHẢI SỐ ĐO."""
        return self.intrinsics is not None and self.intrinsics.synthetic

    def angles(self) -> dict | None:
        return None if self.R_cv is None else rig_angles(self.R_cv)

    def extrinsics(self) -> Extrinsics:
        if self.R_cv is None:
            raise ExtrinsicsError("chưa có ngoại tham")
        return Extrinsics.from_matrix(self.R_cv, self.t_cv)

    def spread(self) -> dict:
        used = self.used
        return {"position_max_m": None if not used else round(max(p.deviation_m for p in used), 5),
                "angle_max_deg": None if not used else round(max(p.deviation_deg for p in used), 4)}

    def camera_entry(self, base_entry: dict | None = None) -> dict:
        """Khối camera cho tệp rig (bev.load_rig_extrinsics đọc `quaternion_xyzw`, `position_m`, `measured`)."""
        if not self.ok:
            raise ExtrinsicsError("kết quả không đạt, không ghi: " + "; ".join(self.refusals))
        e = self.extrinsics()
        ang = self.angles()
        derived = direction_label(ang["yaw_deg"])
        date = self.created_local[:10]
        dd = f"{date[8:10]}/{date[5:7]}/{date[:4]}" if len(date) == 10 else date
        entry = {
            "direction": derived,
            "measured": True,
            "position_m": [round(float(v), 5) for v in e.translation],
            "quaternion_xyzw": [round(float(q), 8) for q in e.quaternion_xyzw],
            "angles_deg_derived": {k: round(v, 3) for k, v in ang.items()},
            "angles_note": "chỉ để đọc; bev.load_rig_extrinsics dùng quaternion_xyzw (camera → xe)",
            "basis": (f"ĐO ({dd}) bằng autopark.perception.extrinsics_calib: {len(self.used)} lần đặt bảng "
                      f"{self.spec.cols}×{self.spec.rows} ô {self.spec.square_mm:g} mm trên sàn, RMS chiếu lại "
                      f"{self.rms_px:.3f} px; tư thế bảng đo bằng thước"),
            "provenance": self.provenance(base_entry),
        }
        if self.synthetic:
            entry["synthetic"] = True
            entry["basis"] = (f"{SYNTHETIC_MARK} — KHÔNG PHẢI SỐ ĐO ({dd}): camera ảo của extrinsics_calib synthetic "
                              f"(nội tham {self.intrinsics.path}), {len(self.used)} ảnh dựng, RMS chiếu lại "
                              f"{self.rms_px:.3f} px")
        return entry

    def provenance(self, base_entry: dict | None = None) -> dict:
        intr = self.intrinsics
        prov = {
            "measured_local": self.created_local,
            "tool": "autopark.perception.extrinsics_calib",
            "software": {"opencv": cv2.__version__, "numpy": np.__version__},
            "intrinsics": None if intr is None else {"path": intr.path, "image_size": list(intr.size),
                                                    "created_local": intr.record.get("created_local"),
                                                    "acceptance_all_pass": intr.acceptance_all_pass,
                                                    "synthetic": intr.synthetic},
            "board": {**self.spec.to_dict(), "square_mm_measured": self.square_mm_measured},
            "placements": [p.to_dict() for p in self.placements],
            "n_placements_used": len(self.used),
            "rms_px": None if self.rms_px is None else round(self.rms_px, 4),
            "max_px": None if self.max_px is None else round(self.max_px, 4),
            "rms_project_model_px": None if self.rms_model_px is None else round(self.rms_model_px, 4),
            "spread": self.spread(),
            "checks": self.checks,
            "warnings": list(self.warnings),
            "thresholds": THRESHOLDS,
            "frame": "hệ xe: x trước, y trái, z lên; gốc trên mặt sàn dưới tâm trục sau",
        }
        if base_entry:
            prov["replaced_entry"] = {k: base_entry.get(k) for k in ("direction", "measured", "position_m", "yaw_deg",
                                                                      "pitch_down_deg", "roll_deg", "quaternion_xyzw")
                                      if k in base_entry}
        return prov


def _joint_solve(used: list, intr: CameraIntrinsics, R0: np.ndarray, t0: np.ndarray) -> tuple:
    obj = np.vstack([p.vehicle_points for p in used])
    img = np.vstack([p.corners for p in used])
    R_vc = R0.T                              # xe → camera
    rvec0 = cv2.Rodrigues(R_vc)[0].ravel()
    tvec0 = -R_vc @ t0
    rv, tv, err = refine_pose(obj, img, rvec0, tvec0, intr.K, intr.D, iterations=100)
    R_vc = cv2.Rodrigues(rv)[0]
    R_cv = R_vc.T
    t_cv = -R_cv @ tv
    return R_cv, t_cv, rv, tv, err


def _mean_rotation(rotations: list) -> np.ndarray:
    M = np.sum(rotations, axis=0)
    U, _, Vt = np.linalg.svd(M)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1
        R = U @ Vt
    return R


def solve_extrinsics(inputs: list, spec: BoardSpec, intr: CameraIntrinsics, *, min_placements: int = MIN_PLACEMENTS,
                     square_mm_measured: bool | None = None) -> ExtrinsicsResult:
    """Mọi lần đặt → một tư thế camera → xe, có loại lần đặt lệch và các phép kiểm (xem docstring của mô-đun)."""
    check_spec(spec)
    created = datetime.now().isoformat(timespec="seconds")
    result = ExtrinsicsResult(intr.port, False, [], [], [], intr, spec, square_mm_measured=square_mm_measured,
                              created_local=created)
    if not inputs:
        result.refusals.append("chưa có lần đặt bảng nào")
        return result
    result.placements = [analyse_placement(inp, spec, intr) for inp in inputs]
    used = [p for p in result.placements if p.used]
    if not used:
        result.refusals.append("không lần đặt nào dùng được: "
                               + "; ".join(f"{p.name}: {p.reason}" for p in result.placements))
        return result
    # tư thế chung, loại dần lần đặt lệch nhất (khi còn ≥ 3 lần: với 2 lần không biết lần nào sai)
    while True:
        R0 = _mean_rotation([p.R_cv for p in used])
        t0 = np.mean([p.t_cv for p in used], axis=0)
        R_cv, t_cv, rv, tv, err = _joint_solve(used, intr, R0, t0)
        offset = 0
        for p in used:
            n = len(p.corners)
            e = err[offset:offset + n]
            offset += n
            p.rms_joint_px = float(np.sqrt(np.mean(e ** 2)))
            p.deviation_m = float(np.linalg.norm(p.t_cv - t_cv))
            p.deviation_deg = rotation_angle_deg(p.R_cv, R_cv)
        bad = [p for p in used if p.deviation_m > MAX_POSITION_SPREAD_M or p.deviation_deg > MAX_ANGLE_SPREAD_DEG]
        if not bad or len(used) < 3:
            break
        worst = max(used, key=lambda p: max(p.deviation_m / MAX_POSITION_SPREAD_M, p.deviation_deg / MAX_ANGLE_SPREAD_DEG))
        worst.used = False
        worst.reason = (f"lệch tư thế chung của các lần đặt khác: vị trí {100 * worst.deviation_m:.1f} cm, hướng "
                        f"{worst.deviation_deg:.2f}° (ngưỡng {100 * MAX_POSITION_SPREAD_M:g} cm / "
                        f"{MAX_ANGLE_SPREAD_DEG:g}°) — "
                        f"thường do số đo thước của lần này sai")
        used = [p for p in used if p.used]
    # lần đặt bị loại vì lệch: số liệu so với tư thế CUỐI (không phải tư thế của vòng nó còn được tính)
    R_vc = R_cv.T
    for p in result.placements:
        if not p.used and p.R_cv is not None:
            e = np.linalg.norm(project_points(p.vehicle_points, cv2.Rodrigues(R_vc)[0], -R_vc @ t_cv, intr.K, intr.D)
                               - p.corners, axis=1)
            p.rms_joint_px = float(np.sqrt(np.mean(e ** 2)))
            p.deviation_m = float(np.linalg.norm(p.t_cv - t_cv))
            p.deviation_deg = rotation_angle_deg(p.R_cv, R_cv)
    result.R_cv, result.t_cv = R_cv, t_cv
    result.rms_px = float(np.sqrt(np.mean(err ** 2)))
    result.max_px = float(err.max())
    # kiểm chéo qua mô hình đa thức của dự án (đúng mô hình BEV dùng để chiếu)
    try:
        model = intr.project_model()
        pts_cam = (np.vstack([p.vehicle_points for p in used]) - t_cv) @ R_cv
        u, v, valid = model.project(pts_cam)
        img = np.vstack([p.corners for p in used])
        d = np.hypot(u - img[:, 0], v - img[:, 1])
        result.rms_model_px = float(np.sqrt(np.mean(d[valid] ** 2))) if valid.any() else None
        if not valid.all():
            result.warnings.append(f"{int((~valid).sum())} góc bảng ngoài vùng hợp lệ của mô hình đa thức (θ > theta_max)")
    except (ValueError, OSError) as exc:
        result.warnings.append(f"không kiểm được qua mô hình đa thức: {exc}")
    ang = rig_angles(R_cv)
    spread = result.spread()
    checks = [
        ("placements", "số lần đặt bảng dùng được", len(used), ">=", min_placements),
        ("camera_height_min_m", "độ cao camera (m)", round(float(t_cv[2]), 4), ">=", MIN_CAMERA_HEIGHT_M),
        ("camera_height_max_m", "độ cao camera (m)", round(float(t_cv[2]), 4), "<=", MAX_CAMERA_HEIGHT_M),
        ("rms_px", "RMS chiếu lại chung (px)", round(result.rms_px, 4), "<=", MAX_JOINT_RMS_PX),
        ("position_spread_m", "độ lệch vị trí lớn nhất giữa các lần đặt (m)", spread["position_max_m"], "<=",
         MAX_POSITION_SPREAD_M),
        ("angle_spread_deg", "độ lệch hướng lớn nhất giữa các lần đặt (°)", spread["angle_max_deg"], "<=",
         MAX_ANGLE_SPREAD_DEG),
    ]
    for key, label, value, op, thr in checks:
        passed = value is not None and (value >= thr if op == ">=" else value <= thr)
        result.checks.append({"key": key, "label": label, "value": value, "op": op, "threshold": thr, "pass": bool(passed)})
        if not passed:
            result.refusals.append(_refusal_text(key, value, thr, len(used)))
    if intr.acceptance_all_pass is False:
        result.warnings.append("nội tham chưa đạt tiêu chí đề xuất (acceptance.all_pass = false): BEV vẫn đánh dấu costmap "
                               "không dùng được")
    theta_obs = intr.theta_observed_max_deg
    worst_theta = max((p.corner_theta_max_deg or 0.0) for p in used)
    if theta_obs is not None and worst_theta > float(theta_obs):
        result.warnings.append(f"góc bảng tới θ = {worst_theta:.1f}° vượt θ lớn nhất đã thấy bảng khi hiệu chuẩn nội tham "
                               f"({float(theta_obs):.1f}°): phần đó của mô hình là ngoại suy")
    if len(used) == 1 and min_placements <= 1:
        result.warnings.append("chỉ một lần đặt bảng: không kiểm chéo được số đo thước")
    if abs(ang["roll_deg"]) > 10.0:
        result.warnings.append(f"roll {ang['roll_deg']:.1f}° lớn: camera gá nghiêng? (hàng ảnh không song song mặt sàn)")
    rejected = [p for p in result.placements if not p.used]
    if rejected:
        result.warnings.append(f"{len(rejected)} lần đặt bị loại: " + "; ".join(f"{p.name}: {p.reason}" for p in rejected))
    if square_mm_measured is False:
        result.warnings.append("cỡ ô CHƯA xác nhận là cỡ ĐO ĐƯỢC bằng thước: khoảng cách bảng (và độ cao camera) tỉ lệ "
                               "thuận với cỡ ô đã nhập")
    result.ok = not result.refusals
    return result


def _refusal_text(key: str, value, thr, n_used: int) -> str:
    if key == "placements":
        return (f"mới có {value} lần đặt bảng dùng được, cần ≥ {thr}: đặt bảng thêm ở chỗ khác (một lần đặt không kiểm "
                f"chéo được số đo thước)")
    if key == "camera_height_min_m":
        return f"camera ở độ cao {value} m, dưới/sát mặt sàn: số đo hay nội tham sai"
    if key == "camera_height_max_m":
        return f"camera cao {value} m > {thr} m: vô lý với xe 1/12 — kiểm cỡ ô (mm) và số đo thước (m)"
    if key == "rms_px":
        return f"RMS chiếu lại chung {value} px > {thr} px: số đo thước của các lần đặt không nhất quán"
    if key in ("position_spread_m", "angle_spread_deg"):
        what = "vị trí" if key == "position_spread_m" else "hướng"
        return (f"các lần đặt bảng không khớp nhau về {what} camera ({value} > {thr}); với {n_used} lần đặt không biết "
                f"lần nào sai — đo lại, hoặc thêm lần đặt để công cụ loại được lần lệch (lệch lớn ở MỌI lần đặt: kiểm ảnh "
                f"có bị lật gương, nội tham có đúng camera này)")
    return f"{key}: {value} (cần {thr})"


def summary_text(result: ExtrinsicsResult) -> str:
    lines = [f"camera cổng {result.port} · bảng {result.spec.cols}×{result.spec.rows} ô {result.spec.square_mm:g} mm · "
             f"{len(result.used)}/{len(result.placements)} lần đặt dùng được"]
    if result.intrinsics is not None:
        lines.append(f"nội tham: {result.intrinsics.path} ({result.intrinsics.size[0]}×{result.intrinsics.size[1]})"
                     + (f" — {SYNTHETIC_MARK} (camera ảo, không phải hiệu chuẩn thật)" if result.synthetic else ""))
    for p in result.placements:
        if p.used:
            lines.append(f"  {p.name}: RMS riêng {p.rms_px:.3f} px, dưới tư thế chung {p.rms_joint_px:.3f} px; lệch "
                         f"{100 * p.deviation_m:.2f} cm / {p.deviation_deg:.2f}°; bảng cách {p.board_distance_m:.2f} m; "
                         f"sai lệch thước {1000 * p.board.max_residual_m:.1f} mm")
        else:
            lines.append(f"  {p.name}: LOẠI — {p.reason}")
    if result.t_cv is not None:
        a = result.angles()
        x, y, z = result.t_cv
        lines.append(f"vị trí camera (hệ xe): x {x:+.4f} m, y {y:+.4f} m, cao z {z:.4f} m")
        lines.append(f"yaw {a['yaw_deg']:+.2f}° ({direction_label(a['yaw_deg'])}), chúc xuống {a['pitch_down_deg']:+.2f}°, "
                     f"roll {a['roll_deg']:+.2f}°")
        lines.append(f"RMS chiếu lại chung {result.rms_px:.3f} px (lớn nhất {result.max_px:.3f} px); qua mô hình đa thức "
                     f"của dự án {('—' if result.rms_model_px is None else f'{result.rms_model_px:.3f} px')}")
    for c in result.checks:
        lines.append(f"  {'đạt ' if c['pass'] else 'CHƯA'}  {c['label']}: {c['value']} (cần {c['op']} {c['threshold']})")
    for w in result.warnings:
        lines.append(f"CẢNH BÁO: {w}")
    if result.ok and result.synthetic:
        lines.append(f"→ ĐẠT các phép kiểm trên ảnh {SYNTHETIC_MARK} (camera ảo): chỉ để thử, KHÔNG PHẢI SỐ ĐO — chỉ ghi "
                     f"được với allow_synthetic, ngoài configs/ và calibration/")
    elif result.ok:
        lines.append("→ ĐẠT các phép kiểm (ngưỡng ĐỀ XUẤT – CHỜ CHỐT); ghi được vào tệp rig với \"measured\": true")
    else:
        lines.append("→ TỪ CHỐI: " + " | ".join(result.refusals))
    return "\n".join(lines)


# ---- tệp rig ---------------------------------------------------------------------------------------------------------
def _date_vn(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if len(iso) >= 10 else iso


def _forbidden_dir_of(path: Path) -> Path | None:
    """Thư mục cấm ghi kết quả tổng hợp (configs/, calibration/ của dự án) chứa `path`, hoặc None."""
    target = Path(path).resolve()
    for folder in SYNTHETIC_FORBIDDEN_DIRS:
        try:
            if target.is_relative_to(Path(folder).resolve()):
                return Path(folder)
        except (OSError, ValueError):
            continue
    return None


def reserve_backup_path(path, stamp: str | None = None) -> Path:
    """Giữ chỗ một tên sao lưu CHƯA có: <tên>.bak_<ngày_giờ_micro giây>[_NNN]<đuôi>, tạo rỗng độc quyền (mở "xb") nên hai
    lần ghi đè liền nhau (bấm đúp 'Ghi tệp rig') không bao giờ dùng chung một tên sao lưu."""
    path = Path(path)
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    for n in range(1000):
        candidate = path.with_name(f"{path.stem}.bak_{stamp}{f'_{n:03d}' if n else ''}{path.suffix}")
        try:
            with open(candidate, "xb"):
                return candidate
        except FileExistsError:
            continue
    raise ExtrinsicsError(f"không tìm được tên sao lưu còn trống cho {path}")


def write_rig_file(out_path, results: list, *, base_path=DEFAULT_BASE, overwrite: bool = False,
                   allow_synthetic: bool = False) -> Path:
    """Ghi tệp rig mới: chép `base_path`, thay các camera đã đo. Đọc lại bằng bev.load_rig_extrinsics và so từng số.

    Kết quả giải bằng nội tham TỔNG HỢP (camera ảo) chỉ ghi được khi `allow_synthetic`, mang nhãn `"synthetic": true`, và
    không bao giờ vào configs/ hay calibration/ của dự án (xem docstring mô-đun)."""
    from . import bev

    out_path, base_path = Path(out_path), Path(base_path)
    if not results:
        raise ExtrinsicsError("không có kết quả ngoại tham nào để ghi")
    for r in results:
        if not r.ok:
            raise ExtrinsicsError(f"cổng {r.port}: kết quả không đạt, không ghi (\"measured\": true chỉ cho kết quả đạt): "
                                  + "; ".join(r.refusals))
    synthetic_results = sorted(int(r.port) for r in results if r.synthetic)
    if synthetic_results and not allow_synthetic:
        raise ExtrinsicsError(f"cổng {', '.join(map(str, synthetic_results))}: nội tham là {SYNTHETIC_MARK} (camera ảo), "
                              f"không ghi như số đo; chỉ để thử luồng ghi: thêm --allow-synthetic và ghi ra ngoài configs/ "
                              f"(ví dụ runs\\extrinsics\\tong_hop\\{SYNTHETIC_RIG_NAME})")
    if out_path.resolve() == DEFAULT_BASE.resolve():
        raise ExtrinsicsError(f"không ghi vào {DEFAULT_BASE.name}: tệp v0 là hồ sơ GIẢ ĐỊNH; ghi sang tệp mới, ví dụ "
                              f"{DEFAULT_OUT.name}")
    if out_path.exists() and not overwrite:
        raise ExtrinsicsError(f"{out_path} đã có: không ghi đè im lặng. Muốn thêm/đổi camera trong tệp này thì chạy lại với "
                              f"--base {out_path} --overwrite (bản cũ được sao lưu cạnh nó)")
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExtrinsicsError(f"không đọc được tệp gốc {base_path}: {exc}") from exc
    if not isinstance(base, dict) or base.get("format") != bev.EXTRINSICS_FORMAT:
        raise ExtrinsicsError(f"{base_path}: không phải tệp {bev.EXTRINSICS_FORMAT}")
    writing_ports = {int(r.port) for r in results}
    synthetic_base = sorted(int(k) for k, c in (base.get("cameras") or {}).items()
                            if isinstance(c, dict) and c.get("synthetic") is True and int(k) not in writing_ports)
    if synthetic_base and not allow_synthetic:
        raise ExtrinsicsError(f"tệp gốc {base_path} có camera {SYNTHETIC_MARK} (cổng {', '.join(map(str, synthetic_base))}, "
                              f"camera ảo): không chép chúng vào tệp rig như số đo — chọn tệp gốc khác (ví dụ "
                              f"{DEFAULT_BASE.name})")
    if synthetic_results or synthetic_base:
        forbidden = _forbidden_dir_of(out_path)
        if forbidden is not None:
            raise ExtrinsicsError(f"tệp rig có camera {SYNTHETIC_MARK} (camera ảo) không bao giờ được ghi vào {forbidden}: "
                                  f"ghi ra thư mục thử, ví dụ runs\\extrinsics\\tong_hop\\{SYNTHETIC_RIG_NAME}")
    if out_path.exists():
        # ghi đè từ một tệp gốc KHÁC (ví dụ v0) sẽ xoá số đo của camera đã đo trong tệp ra: từ chối, chỉ cách giữ chúng
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
        writing = {int(r.port) for r in results}
        base_cams = base.get("cameras") or {}
        lost = sorted(int(k) for k, c in (existing.get("cameras") or {}).items()
                      if isinstance(c, dict) and c.get("measured") is True and int(k) not in writing
                      and (base_cams.get(k) or {}).get("measured") is not True)
        if lost:
            raise ExtrinsicsError(f"ghi đè {out_path} từ tệp gốc {base_path} sẽ MẤT số đo của cổng "
                                  f"{', '.join(map(str, lost))} (đã đo trong {out_path.name}, tệp gốc không có): dùng "
                                  f"--base {out_path} (giao diện: 'Chép từ' = tệp ra)")
    data = json.loads(json.dumps(base))
    cameras = data.setdefault("cameras", {})
    now = datetime.now().isoformat(timespec="seconds")
    history = list(data.get("history") or [])
    for r in results:
        key = str(int(r.port))
        cameras[key] = r.camera_entry(cameras.get(key))
        history.append({"local": now, "port": r.port, "action": "đo ngoại tham", "placements_used": len(r.used),
                        "rms_px": round(r.rms_px, 4)})
    measured = sorted(int(k) for k, c in cameras.items() if c.get("measured") is True)
    assumed = sorted(int(k) for k, c in cameras.items() if c.get("measured") is not True)
    synthetic = sorted(int(k) for k, c in cameras.items() if isinstance(c, dict) and c.get("synthetic") is True)
    data["status"] = ("ĐÃ ĐO mọi camera" if not assumed else
                      f"ĐO MỘT PHẦN: cổng {', '.join(map(str, measured))} đã đo; cổng {', '.join(map(str, assumed))} "
                      f"GIẢ ĐỊNH — CHƯA ĐO (chép từ tệp gốc)")
    data.pop("synthetic", None)
    if synthetic:
        data["synthetic"] = True
        data["status"] = (f"{SYNTHETIC_MARK} — KHÔNG PHẢI SỐ ĐO (cổng {', '.join(map(str, synthetic))}: camera ảo, chỉ để "
                          f"thử công cụ); " + data["status"])
    data["created_local"] = now
    data["base_file"] = str(base_path)
    data["history"] = history
    if "ghi_chu_tu_tep_goc" not in data:
        data["ghi_chu_tu_tep_goc"] = list(base.get("ghi_chu", []))
    data["ghi_chu"] = [
        f"({_date_vn(now)}) Tệp do autopark.perception.extrinsics_calib ghi. Camera có \"measured\": true được đo bằng "
        f"bảng ô vuông đặt trên sàn ở vị trí đo bằng thước (docs/NGOAI_THAM_VA_ROI.md); nguồn gốc từng camera ở khóa "
        f"provenance. Camera còn \"measured\": false giữ nguyên số GIẢ ĐỊNH của tệp gốc.",
        "Khối vehicle_assumed (kích thước xe, hộp thân xe) chép từ tệp gốc: vẫn là GIẢ ĐỊNH cho tới khi đo MN300 "
        "(giai đoạn 4).",
        "Các ngưỡng kiểm (thresholds) là ĐỀ XUẤT – CHỜ CHỐT, chưa kiểm trên camera thật.",
    ]
    if synthetic:
        data["ghi_chu"].insert(0, f"{SYNTHETIC_MARK}: camera có \"synthetic\": true được giải trên ảnh dựng qua camera ảo "
                                  f"(extrinsics_calib synthetic), KHÔNG PHẢI SỐ ĐO. \"measured\": true chỉ để thử nối trọn "
                                  f"BEV trên ảnh tổng hợp; không dùng tệp này cho xe thật.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        backup = reserve_backup_path(out_path)
        shutil.copy2(out_path, backup)       # chép lên tệp rỗng vừa giữ chỗ (của chính mình), không đè bản khác
    atomic_write_json(out_path, data)
    # đọc lại bằng chính bộ nạp của BEV: tư thế phải trùng từng số với kết quả vừa tính
    rig = bev.load_rig_extrinsics(out_path)
    for r in results:
        pose = rig.cameras.get(int(r.port))
        if pose is None or not pose.measured:
            raise ExtrinsicsError(f"đọc lại {out_path}: cổng {r.port} không có hoặc không có measured = true")
        if not (np.allclose(pose.extrinsics.rotation, r.R_cv, atol=1e-6)
                and np.allclose(pose.extrinsics.translation, r.t_cv, atol=1e-4)):
            raise ExtrinsicsError(f"đọc lại {out_path}: tư thế cổng {r.port} khác kết quả vừa tính")
    return out_path


def last_backup(out_path) -> Path | None:
    out_path = Path(out_path)
    found = sorted(out_path.parent.glob(f"{out_path.stem}.bak_*{out_path.suffix}"))
    return found[-1] if found else None


# ---- tệp danh sách lần đặt ---------------------------------------------------------------------------------------------
def _cli_number(text, what: str) -> float:
    """Số trên dòng lệnh / trong tệp JSON: nhận cả dấu chấm lẫn dấu phẩy thập phân kiểu Việt ('0,60' = 0.60)."""
    if isinstance(text, bool):
        raise ExtrinsicsError(f"{what} = {text!r} không phải số")
    try:
        value = float(str(text).strip().replace(",", "."))
    except ValueError:
        raise ExtrinsicsError(f"{what} = {text!r} không phải số (viết 0.60 hoặc 0,60)") from None
    if not math.isfinite(value):
        raise ExtrinsicsError(f"{what} = {text!r} phải là số hữu hạn")
    return value


def read_image(path) -> np.ndarray:
    image = fc.read_image(Path(path))
    if image is None:
        raise ExtrinsicsError(f"không đọc được ảnh {path}")
    return image


def resolve_image(entry: dict, port: int, base_dir: Path) -> Path:
    """"image": tệp ảnh; hoặc "snapshot": thư mục runs/rig_snapshots/<ngày_giờ> → cam_p<cổng>.png."""
    if entry.get("snapshot"):
        candidates = [Path(entry["snapshot"]), base_dir / entry["snapshot"]]
        for c in candidates:
            if c.is_dir():
                path = c / f"cam_p{port}.png"
                if not path.exists():
                    raise ExtrinsicsError(f"bộ ảnh {c} không có cam_p{port}.png")
                return path
        raise ExtrinsicsError(f"không thấy thư mục bộ ảnh {entry['snapshot']}")
    if not entry.get("image"):
        raise ExtrinsicsError("mỗi lần đặt cần \"image\" (tệp ảnh) hoặc \"snapshot\" (thư mục bộ ảnh)")
    for c in (Path(entry["image"]), base_dir / entry["image"]):
        if c.exists():
            return c
    raise ExtrinsicsError(f"không thấy ảnh {entry['image']}")


def load_placements_file(path) -> dict:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExtrinsicsError(f"không đọc được {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != PLACEMENTS_FORMAT:
        raise ExtrinsicsError(f"{path}: không phải tệp {PLACEMENTS_FORMAT}")
    if "port" not in data or not isinstance(data.get("placements"), list):
        raise ExtrinsicsError(f"{path}: cần \"port\" và danh sách \"placements\"")
    return data


def placements_record(port: int, spec: BoardSpec, entries: list, *, square_mm_measured: bool | None = None,
                      board_z_m: float = 0.0, intrinsics: str | None = None) -> dict:
    """entries: [{"name", "image", "points_xy_m" {...}, (tùy chọn) "yaw_deg"}]."""
    return {"format": PLACEMENTS_FORMAT, "port": int(port),
            "board": {**spec.to_dict(), "square_mm_measured": square_mm_measured, "board_z_m": board_z_m},
            "intrinsics": intrinsics, "created_local": datetime.now().isoformat(timespec="seconds"),
            "frame": "hệ xe: x trước, y trái, z lên; gốc trên sàn dưới tâm trục sau; mét",
            "corner_names": "O = góc trong (0,0) sát ô đen góc trên-trái tờ in; A = (cols-1, 0); B = (0, rows-1); "
                            "C = (cols-1, rows-1)",
            "placements": entries}


def inputs_from_record(data: dict, base_dir: Path) -> tuple[int, BoardSpec, list, dict]:
    port = int(data["port"])
    board = data.get("board") or {}
    try:
        spec = BoardSpec(int(board.get("cols", 9)), int(board.get("rows", 6)), _cli_number(board["square_mm"], "square_mm"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ExtrinsicsError(f"khối board cần square_mm (cỡ ô ĐO ĐƯỢC, mm): {exc}") from exc
    board_z = _cli_number(board.get("board_z_m", 0.0), "board_z_m")
    inputs = []
    for k, entry in enumerate(data["placements"]):
        name = str(entry.get("name") or f"dat_{k + 1:02d}")
        path = resolve_image(entry, port, base_dir)
        placement = BoardPlacement.from_dict({"board_z_m": board_z, **entry})
        inputs.append(PlacementInput(name, read_image(path), placement, str(path)))
    return port, spec, inputs, board


# ---- vẽ kiểm ----------------------------------------------------------------------------------------------------------
def _project_vehicle(points_v: np.ndarray, R_cv, t_cv, K, D, size) -> tuple[np.ndarray, np.ndarray]:
    pts_c = (np.asarray(points_v, np.float64) - t_cv) @ R_cv
    ok = pts_c[:, 2] > 1e-3
    uv = np.full((len(pts_c), 2), np.nan)
    if ok.any():
        uv[ok] = project_points(pts_c[ok], np.zeros(3), np.zeros(3), K, D)
    w, h = size
    ok &= np.isfinite(uv).all(axis=1) & (uv[:, 0] >= -w) & (uv[:, 0] <= 2 * w) & (uv[:, 1] >= -h) & (uv[:, 1] <= 2 * h)
    # chỉ trong vùng θ mô hình KB còn nghịch đảo được (ngoài đó điểm chiếu vô nghĩa)
    theta = np.degrees(np.arctan2(np.hypot(pts_c[:, 0], pts_c[:, 1]), pts_c[:, 2]))
    ok &= theta < 89.0
    return uv, ok


def _polyline(img, uv, ok, color, thickness=1):
    run = []
    for p, good in zip(uv, ok):
        if good:
            run.append((int(round(p[0] * 16)), int(round(p[1] * 16))))
        elif run:
            if len(run) > 1:
                cv2.polylines(img, [np.array(run, np.int32)], False, color, thickness, cv2.LINE_AA, 4)
            run = []
    if len(run) > 1:
        cv2.polylines(img, [np.array(run, np.int32)], False, color, thickness, cv2.LINE_AA, 4)


def draw_board_labels(image: np.ndarray, corners: np.ndarray, spec: BoardSpec) -> np.ndarray:
    """Góc đã đánh số: vẽ O, A, B, C và mũi tên trục x (đỏ), y (xanh lá) của bảng. Chữ ASCII (cv2)."""
    out = image.copy() if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    g = np.asarray(corners).reshape(spec.rows, spec.cols, 2)
    cv2.drawChessboardCorners(out, spec.pattern_size, np.asarray(corners, np.float32).reshape(-1, 1, 2), True)
    o, a, b = g[0, 0], g[0, -1], g[-1, 0]
    cv2.arrowedLine(out, tuple(int(v) for v in o), tuple(int(v) for v in a), (0, 0, 255), 2, tipLength=0.08)
    cv2.arrowedLine(out, tuple(int(v) for v in o), tuple(int(v) for v in b), (0, 200, 0), 2, tipLength=0.12)
    for name, (i, j) in (("O", (0, 0)), ("A", (spec.cols - 1, 0)), ("B", (0, spec.rows - 1)),
                         ("C", (spec.cols - 1, spec.rows - 1))):
        p = g[j, i]
        cv2.putText(out, name, (int(p[0]) + 5, int(p[1]) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(out, name, (int(p[0]) + 5, int(p[1]) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)
    return out


def draw_vehicle_grid(image: np.ndarray, R_cv, t_cv, K, D, *, step_m: float = 0.1, extent_m: float = 1.5,
                      ego=None) -> np.ndarray:
    """Lưới mặt sàn của hệ xe chiếu qua tư thế vừa đo: đường mỗi `step_m` (xám); trục x của xe (đường y = 0) đỏ, trục y
    của xe (đường x = 0) xanh lá — cùng quy ước màu với mũi tên trục x/y của bảng trong `draw_board_labels`; hộp thân xe
    `ego` (trắng, nếu có: `bev.EgoBox`, GIẢ ĐỊNH từ vehicle_assumed). Lưới phải nằm đúng lên vạch băng dính trên sàn —
    phép kiểm bằng mắt."""
    out = image.copy() if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    size = (out.shape[1], out.shape[0])
    cx, cy = float(t_cv[0]), float(t_cv[1])
    xs = np.arange(math.floor((cx - extent_m) / step_m), math.ceil((cx + extent_m) / step_m) + 1) * step_m
    ys = np.arange(math.floor((cy - extent_m) / step_m), math.ceil((cy + extent_m) / step_m) + 1) * step_m
    dense = np.linspace(-extent_m, extent_m, 300)
    for x in xs:                     # đường x = hằng; x = 0 là TRỤC Y của xe → xanh lá
        pts = np.column_stack([np.full_like(dense, x), cy + dense, np.zeros_like(dense)])
        uv, ok = _project_vehicle(pts, R_cv, t_cv, K, D, size)
        _polyline(out, uv, ok, (0, 200, 0) if abs(x) < 1e-9 else (150, 150, 150), 2 if abs(x) < 1e-9 else 1)
    for y in ys:                     # đường y = hằng; y = 0 là TRỤC X của xe → đỏ
        pts = np.column_stack([cx + dense, np.full_like(dense, y), np.zeros_like(dense)])
        uv, ok = _project_vehicle(pts, R_cv, t_cv, K, D, size)
        _polyline(out, uv, ok, (0, 0, 230) if abs(y) < 1e-9 else (150, 150, 150), 2 if abs(y) < 1e-9 else 1)
    if ego is not None:
        corners = [(ego.x_min, ego.y_min), (ego.x_max, ego.y_min), (ego.x_max, ego.y_max), (ego.x_min, ego.y_max),
                   (ego.x_min, ego.y_min)]
        for (x0, y0), (x1, y1) in zip(corners[:-1], corners[1:]):
            tt = np.linspace(0, 1, 60)
            pts = np.column_stack([x0 + tt * (x1 - x0), y0 + tt * (y1 - y0), np.zeros_like(tt)])
            uv, ok = _project_vehicle(pts, R_cv, t_cv, K, D, size)
            _polyline(out, uv, ok, (255, 255, 255), 1)
    return out


def rig_ego(path):
    """Hộp thân xe GIẢ ĐỊNH (vehicle_assumed của tệp rig, đã nới ego_margin_m) để vẽ kiểm; None nếu không đọc được."""
    from . import bev

    if path is None:
        return None
    try:
        return bev.load_rig_extrinsics(path).ego
    except (bev.RigConfigError, OSError, ValueError):
        return None


def draw_result(image: np.ndarray, placement: PlacementResult, result: ExtrinsicsResult, spec: BoardSpec,
                ego=None) -> np.ndarray:
    """Ảnh kiểm của một lần đặt: lưới hệ xe + hộp thân xe `ego` (nếu có) chiếu qua tư thế chung, góc bảng dự đoán (vòng
    tím), góc đã đánh số O, A, B, C."""
    out = image.copy()
    if result.R_cv is not None and result.intrinsics is not None:
        out = draw_vehicle_grid(out, result.R_cv, result.t_cv, result.intrinsics.K, result.intrinsics.D, ego=ego)
        if placement.vehicle_points is not None:
            uv, ok = _project_vehicle(placement.vehicle_points, result.R_cv, result.t_cv, result.intrinsics.K,
                                      result.intrinsics.D, (out.shape[1], out.shape[0]))
            for p, good in zip(uv, ok):
                if good:
                    cv2.circle(out, (int(round(p[0])), int(round(p[1]))), 4, (255, 0, 255), 1, cv2.LINE_AA)
    label_spec = placement.spec if placement.spec is not None else spec    # góc được đánh số theo bảng lúc giải
    if placement.corners is not None and len(placement.corners) == label_spec.n_corners:
        out = draw_board_labels(out, placement.corners, label_spec)
    return out


# ---- cảnh tổng hợp (demo và kiểm thử; KHÔNG phải số đo) ------------------------------------------------------------------
SYNTH_K = np.array([[351.0, 0.0, 324.3], [0.0, 349.2, 236.8], [0.0, 0.0, 1.0]])   # như tests/test_fisheye_calib.py
SYNTH_D = np.array([-0.035, 0.018, -0.009, 0.0015])


class FloorRenderer:
    """Dựng ảnh một bảng in nằm trên sàn qua camera KB đã biết: điểm ảnh con → tia (cv2.fisheye.undistortPoints) →
    mặt sàn → màu (sàn xám, giấy trắng, ô đen khi ⌊X/ô⌋ + ⌊Y/ô⌋ chẵn). CHỈ để thử công cụ khi chưa có camera."""

    def __init__(self, K=SYNTH_K, D=SYNTH_D, size=(640, 480), supersample: int = 3):
        self.K, self.D = np.asarray(K, np.float64), np.asarray(D, np.float64)
        self.size, self.ss = tuple(size), int(supersample)
        w, h = self.size
        us = (np.arange(w * self.ss) + 0.5) / self.ss - 0.5
        vs = (np.arange(h * self.ss) + 0.5) / self.ss - 0.5
        uu, vv = np.meshgrid(us, vs)
        und = cv2.fisheye.undistortPoints(np.stack([uu.ravel(), vv.ravel()], 1).reshape(-1, 1, 2), self.K,
                                          self.D.reshape(4, 1),
                                          criteria=(cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 30, 1e-12))
        und = und.reshape(-1, 2)
        rays = np.column_stack([und, np.ones(len(und))])
        self.rays = rays / np.linalg.norm(rays, axis=1, keepdims=True)

    def render(self, R_cv, t_cv, boards: list, spec: BoardSpec, rng=None, blur: float = 0.6, noise: float = 2.0,
               floor: float = 95.0, sky: float = 150.0) -> np.ndarray:
        """boards: [(R_bv, t_bv)] (bảng → xe). Sàn z = 0; mặt in ở z = t_bv[2]."""
        s = spec.square_mm / 1000.0
        d = self.rays @ np.asarray(R_cv, np.float64).T
        o = np.asarray(t_cv, np.float64)
        img = np.full(len(d), sky)
        with np.errstate(divide="ignore", invalid="ignore"):
            k_floor = np.where(d[:, 2] < -1e-9, -o[2] / d[:, 2], np.inf)
        hit = np.isfinite(k_floor)
        gx, gy = o[0] + k_floor * d[:, 0], o[1] + k_floor * d[:, 1]
        img[hit] = floor + 12.0 * (((np.floor(gx[hit] / 0.25) + np.floor(gy[hit] / 0.25)) % 2) - 0.5)
        for R_bv, t_bv in boards:
            R_bv, t_bv = np.asarray(R_bv, np.float64), np.asarray(t_bv, np.float64)
            with np.errstate(divide="ignore", invalid="ignore"):
                k = np.where(d[:, 2] < -1e-9, (t_bv[2] - o[2]) / d[:, 2], np.inf)
            ok = np.isfinite(k) & (k > 0)
            with np.errstate(invalid="ignore"):
                P = o + np.where(ok, k, 0.0)[:, None] * d
                B = (P - t_bv) @ R_bv
            X, Y = B[:, 0], B[:, 1]
            paper = ok & (X >= -2 * s) & (X <= (spec.cols + 1) * s) & (Y >= -2 * s) & (Y <= (spec.rows + 1) * s)
            img[paper] = 225.0
            board = ok & (X >= -s) & (X < spec.cols * s) & (Y >= -s) & (Y < spec.rows * s)
            black = board & ((np.floor(X / s) + np.floor(Y / s)) % 2 == 0)
            img[black] = 25.0
        w, h = self.size
        img = img.reshape(h, self.ss, w, self.ss).mean(axis=(1, 3))
        if blur:
            img = cv2.GaussianBlur(img, (0, 0), blur)
        if noise and rng is not None:
            img = img + rng.normal(0.0, noise, img.shape)
        return cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def synthetic_intrinsics_record(port: int, K=SYNTH_K, D=SYNTH_D, size=(640, 480)) -> dict:
    """Tệp nội tham dạng fisheye_calib cho camera tổng hợp (không có ảnh hiệu chuẩn thật)."""
    ws = fc.woodscape_intrinsics(K, D, size)
    return {"format": fc.FORMAT, "synthetic": True,
            "camera": {"hub_port": int(port), "source_id": f"cam_p{port}", "device": SYNTHETIC_MARK},
            "image_size": list(size), "model": "opencv_fisheye_kannala_brandt", "K": np.asarray(K).tolist(),
            "D": [float(x) for x in D], "rms_px": 0.0, "woodscape_intrinsic": ws,
            "field_of_view_deg": fc.field_of_view(K, D, size),
            "acceptance": {"status": "TỔNG HỢP — không phải hiệu chuẩn thật", "all_pass": True, "checks": []},
            "note": "TỔNG HỢP: camera ảo của extrinsics_calib synthetic, không phải camera thật",
            "created_local": datetime.now().isoformat(timespec="seconds")}


def synthetic_demo(out_dir, *, port: int = 1, seed: int = 3) -> dict:
    """Ghi một bộ thử TỔNG HỢP: nội tham, 3 ảnh bảng trên sàn trước camera trước (tư thế v0 lệch nhẹ), tệp lần đặt."""
    from .bev import rig_rotation

    out = Path(out_dir)
    forbidden = _forbidden_dir_of(out / "calibration" / f"cam_p{port}.json")
    if forbidden is not None:           # nội tham của camera ảo không bao giờ nằm cạnh nội tham thật
        raise ExtrinsicsError(f"bộ thử {SYNTHETIC_MARK} không được ghi vào {forbidden}: chọn thư mục thử, ví dụ "
                              f"runs\\extrinsics\\tong_hop")
    (out / "calibration").mkdir(parents=True, exist_ok=True)
    spec = BoardSpec(9, 6, 30.0)
    R_cv = rig_rotation(1.5, 31.0, -0.8)
    t_cv = np.array([0.33, 0.01, 0.125])
    renderer = FloorRenderer()
    rng = np.random.default_rng(seed)
    intr_path = out / "calibration" / f"cam_p{port}.json"
    intr_path.write_text(json.dumps(synthetic_intrinsics_record(port), ensure_ascii=False, indent=1), encoding="utf-8")
    # bảng nằm ngang trước camera, hàng gần cách chân camera ≈ 0,1 m (camera thấp: xa hơn ≈ 0,3 m thì ô quá dẹt,
    # không dò được — thử tổng hợp 24/09/2026)
    boards = [((0.60, 0.13), -90.0), ((0.57, 0.20), -75.0), ((0.62, 0.06), -100.0)]
    entries = []
    for k, (origin, yaw) in enumerate(boards):
        R_bv = board_rotation(yaw)
        t_bv = np.array([origin[0], origin[1], 0.0])
        img = renderer.render(R_cv, t_cv, [(R_bv, t_bv)], spec, rng)
        name = f"dat_{k + 1:02d}.png"
        fc.write_image(out / name, img)
        s = spec.square_mm / 1000.0
        a = t_bv + R_bv @ np.array([(spec.cols - 1) * s, 0.0, 0.0])
        b = t_bv + R_bv @ np.array([0.0, (spec.rows - 1) * s, 0.0])
        entries.append({"name": f"dat_{k + 1:02d}", "image": name,
                        "points_xy_m": {"O": [round(origin[0], 4), round(origin[1], 4)],
                                        "A": [round(float(a[0]), 4), round(float(a[1]), 4)],
                                        "B": [round(float(b[0]), 4), round(float(b[1]), 4)]}})
    record = placements_record(port, spec, entries, square_mm_measured=True, intrinsics=str(intr_path))
    record["note"] = "TỔNG HỢP: ảnh dựng qua camera ảo, không phải số đo"
    record["truth"] = {"position_m": t_cv.tolist(), **rig_angles(R_cv)}
    (out / f"dat_bang_p{port}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


# ---- dòng lệnh -------------------------------------------------------------------------------------------------------
def write_report(folder, result: ExtrinsicsResult, inputs: list, ego=None) -> Path:
    """ket_qua.json + ảnh kiểm xem_<lần đặt>.jpg (lưới hệ xe, hộp thân xe `ego` nếu có, góc bảng)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    report = {"port": result.port, "ok": result.ok, "refusals": result.refusals, "summary": summary_text(result),
              "camera": None if result.R_cv is None else {
                  "position_m": [round(float(v), 5) for v in result.t_cv],
                  "quaternion_xyzw": [round(float(q), 8) for q in result.extrinsics().quaternion_xyzw],
                  **{k: round(v, 4) for k, v in result.angles().items()}},
              "provenance": result.provenance()}
    atomic_write_json(folder / "ket_qua.json", report)
    for inp, pr in zip(inputs, result.placements):
        fc.write_image(folder / f"xem_{pr.name}.jpg", draw_result(inp.image, pr, result, result.spec, ego=ego))
    return folder


def _cmd_solve(args) -> int:
    if args.placements:
        data = load_placements_file(args.placements)
        port, spec, inputs, board = inputs_from_record(data, Path(args.placements).parent)
        if args.port is not None and int(args.port) != port:
            raise ExtrinsicsError(f"--port {args.port} khác port {port} trong {args.placements}")
        measured = board.get("square_mm_measured")
        intr_path = args.intrinsics or data.get("intrinsics")
    else:
        if args.port is None or not args.place or args.square_mm is None:
            raise ExtrinsicsError("cần --placements <tệp.json>, hoặc --port, --square-mm và ít nhất một --place")
        port = int(args.port)
        try:
            spec = BoardSpec(args.cols, args.rows, _cli_number(args.square_mm, "--square-mm"))
        except ValueError as exc:
            raise ExtrinsicsError(f"bảng --cols {args.cols} --rows {args.rows} --square-mm {args.square_mm}: {exc}") from exc
        board_z = _cli_number(args.board_z_m, "--board-z-m")
        inputs = []
        for k, (image, ox, oy, ax, ay) in enumerate(args.place):
            tag = f"--place thứ {k + 1}"
            o = (_cli_number(ox, f"{tag} OX"), _cli_number(oy, f"{tag} OY"))
            a = (_cli_number(ax, f"{tag} AX"), _cli_number(ay, f"{tag} AY"))
            placement = BoardPlacement.from_points({"O": o, "A": a}, board_z_m=board_z)
            inputs.append(PlacementInput(f"dat_{k + 1:02d}", read_image(image), placement, str(image)))
        measured = True if args.square_mm_measured else None
        intr_path = args.intrinsics
    if not inputs:
        raise ExtrinsicsError("chưa có lần đặt bảng nào")
    size = (inputs[0].image.shape[1], inputs[0].image.shape[0])
    intr_path = Path(intr_path) if intr_path else default_intrinsics_path(port, size)
    intr = load_camera_intrinsics(intr_path, port)
    result = solve_extrinsics(inputs, spec, intr, min_placements=args.min_placements, square_mm_measured=measured)
    print(summary_text(result))
    folder = DEFAULT_RUNS / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_p{port}"
    write_report(args.report or folder, result, inputs, ego=rig_ego(args.base))
    print(f"báo cáo + ảnh kiểm (lưới hệ xe chiếu lên ảnh) -> {args.report or folder}")
    if not result.ok:
        return 3
    if args.out:
        existed = Path(args.out).exists()
        path = write_rig_file(args.out, [result], base_path=args.base, overwrite=args.overwrite,
                              allow_synthetic=args.allow_synthetic)
        backup = last_backup(path) if existed else None
        print(f"đã ghi {path} (đọc lại bằng bev.load_rig_extrinsics: khớp)" + (f"; bản cũ: {backup}" if backup else ""))
    elif result.synthetic:
        where = (Path(args.placements).parent if args.placements else Path(args.report or folder)) / SYNTHETIC_RIG_NAME
        print(f"chưa ghi tệp rig. Nội tham {SYNTHETIC_MARK} (camera ảo): chỉ ghi để thử, ngoài configs/: --out {where} "
              f"--allow-synthetic")
    else:
        print("chưa ghi tệp rig (thêm --out configs\\rig\\camera_rig_extrinsics_v1.json để ghi)")
    return 0


def _cmd_check(args) -> int:
    from . import bev

    try:
        rig = bev.load_rig_extrinsics(args.file)
    except bev.RigConfigError as exc:
        raise ExtrinsicsError(str(exc)) from exc
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    print(f"{rig.path}: {rig.status}")
    for port, pose in sorted(rig.cameras.items()):
        a = rig_angles(pose.extrinsics.rotation)
        x, y, z = pose.extrinsics.translation
        entry = (data.get("cameras") or {}).get(str(port), {})
        prov = entry.get("provenance") or {}
        kind = (f"{SYNTHETIC_MARK} — KHÔNG PHẢI SỐ ĐO" if entry.get("synthetic") is True
                else "ĐO" if pose.measured else "GIẢ ĐỊNH — CHƯA ĐO")
        line = (f"  cổng {port} ({pose.direction or '?'}): {kind}; "
                f"x {x:+.3f} y {y:+.3f} cao {z:.3f} m; yaw {a['yaw_deg']:+.1f}° chúc {a['pitch_down_deg']:+.1f}° "
                f"roll {a['roll_deg']:+.1f}°")
        if prov:
            line += (f"; {prov.get('n_placements_used')} lần đặt, RMS {prov.get('rms_px')} px, đo lúc "
                     f"{prov.get('measured_local')}")
        print(line)
    if rig.ego is not None:
        print(f"  hộp thân xe (từ vehicle_assumed, GIẢ ĐỊNH): {rig.ego.to_dict()}")
    return 0


def _cmd_synthetic(args) -> int:
    record = synthetic_demo(args.out)
    print(f"đã ghi bộ thử TỔNG HỢP vào {args.out}: {len(record['placements'])} ảnh, dat_bang_p1.json, "
          f"calibration/cam_p1.json")
    print(f"thử: .venv\\Scripts\\python.exe -X utf8 -m autopark.perception.extrinsics_calib solve --placements "
          f"{Path(args.out) / 'dat_bang_p1.json'} --out {Path(args.out) / SYNTHETIC_RIG_NAME} --allow-synthetic")
    print(f"(kết quả trên bộ thử này là {SYNTHETIC_MARK}, KHÔNG PHẢI SỐ ĐO: không bao giờ ghi được vào configs\\ hay "
          f"calibration\\)")
    print(f"tư thế thật (để so): {record['truth']}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ngoại tham camera bằng bảng đặt trên sàn (docs/NGOAI_THAM_VA_ROI.md)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("solve", help="giải ngoại tham một camera từ các lần đặt bảng")
    s.add_argument("--placements", type=Path, help="tệp danh sách lần đặt (giao diện roi_app ghi, hoặc viết tay)")
    s.add_argument("--port", type=int, help="cổng hub của camera")
    s.add_argument("--place", nargs=5, action="append", metavar=("ẢNH", "OX", "OY", "AX", "AY"),
                   help="một lần đặt: ảnh + tọa độ (m, hệ xe) của góc O và góc A (dấu chấm hay dấu phẩy thập phân đều "
                        "được: 0.60 hay 0,60); lặp lại cho mỗi lần đặt")
    s.add_argument("--cols", type=int, default=9)
    s.add_argument("--rows", type=int, default=6)
    s.add_argument("--square-mm", help="cỡ ô ĐO ĐƯỢC bằng thước (mm), ví dụ 29.9 hay 29,9")
    s.add_argument("--square-mm-measured", action="store_true", help="xác nhận --square-mm là cỡ đo bằng thước")
    s.add_argument("--board-z-m", default="0", help="độ cao mặt in trên sàn (m), ví dụ 0.005 (hay 0,005) với tấm xốp 5 mm")
    s.add_argument("--intrinsics", type=Path, help="mặc định calibration/cam_p<cổng>.json theo cỡ ảnh")
    s.add_argument("--min-placements", type=int, default=MIN_PLACEMENTS)
    s.add_argument("--out", type=Path, help="tệp rig để ghi (ví dụ configs/rig/camera_rig_extrinsics_v1.json)")
    s.add_argument("--base", type=Path, default=DEFAULT_BASE, help="tệp rig gốc để chép các camera khác (mặc định v0)")
    s.add_argument("--overwrite", action="store_true", help="cho ghi đè --out đã có (bản cũ được sao lưu)")
    s.add_argument("--allow-synthetic", action="store_true",
                   help="cho ghi kết quả của nội tham TỔNG HỢP (camera ảo) để thử luồng ghi: tệp mang nhãn "
                        "\"synthetic\": true, không bao giờ vào configs/ hay calibration/")
    s.add_argument("--report", type=Path, help="thư mục báo cáo (mặc định runs/extrinsics/<ngày_giờ>_p<cổng>)")
    c = sub.add_parser("check", help="đọc một tệp rig bằng bev.load_rig_extrinsics và in tư thế từng camera")
    c.add_argument("file", type=Path)
    y = sub.add_parser("synthetic", help="ghi một bộ thử TỔNG HỢP (không cần camera)")
    y.add_argument("--out", type=Path, default=DEFAULT_RUNS / "tong_hop")
    args = p.parse_args(argv)
    try:
        if args.cmd == "solve":
            return _cmd_solve(args)
        if args.cmd == "check":
            return _cmd_check(args)
        return _cmd_synthetic(args)
    except ExtrinsicsError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
