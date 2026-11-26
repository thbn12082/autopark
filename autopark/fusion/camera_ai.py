"""AI camera → vật cản trên sa bàn: nguồn vật cản thứ hai bên cạnh LiDAR (25/09/2026, docs/KIEN_TRUC.md).

Mỗi lô AI MỚI của bàn thử (`rig.core.AIResult`: P(BLOCKED) từng camera ở cỡ hiển thị + stamp từng khung) đi qua:

1. **Chặn (gating, an toàn).** Chỉ BEV "dùng được cho lập đường" mới được tạo vật cản: mọi camera có dữ liệu trong lô
   phải có nội tham thật đạt tiêu chí (`acceptance.all_pass` = true của JSON; tệp KHÔNG có kết quả tiêu chí, hay có giá
   trị lạ như chuỗi "false", cũng bị chặn — chặt hơn `bev.unusable_reasons`), ngoại tham `"measured": true`, ROI, và không
   phần nào là dữ liệu TỔNG HỢP (`bev.unusable_reasons`). Không nạp được rig (thiếu hay hỏng tệp nội tham/ngoại tham/ROI,
   cổng không có trong tệp rig, kể cả lỗi lạ của tệp sửa tay) cũng bị chặn, và khung có cỡ khác cỡ ảnh đã hiệu chuẩn
   (mode camera khác) cũng vậy. Thiếu tệp thì lý do kể đủ các tệp chưa có theo đúng trình tự làm: nội tham → ngoại tham
   → ROI (`missing_calibration_files`). Bị chặn thì `update()` trả danh sách lý do tiếng Việt ("AI chưa được dùng để điều
   khiển vì: …", xem `gate_text`) và KHÔNG thêm ô OCCUPIED nào; lớp bản đồ bị đánh dấu không hợp lệ và cửa sổ lọc thời
   gian bị xóa.
   Ngoại lệ duy nhất: rig TỔNG HỢP (`synthetic_camera_rig`: camera ảo của `bev.synthetic_rig`) chỉ để thử với bản ghi
   phát lại hay nguồn giả (`source_kind` "replay"/"fake"); nó luôn mang ghi chú TỔNG HỢP, và bị TỪ CHỐI với camera thật
   (`source_kind` "live").
2. **BEV** bằng `bev.build_bev` (quy tắc ở docs/KIEN_TRUC.md), hộp thân xe = hộp `vehicle_assumed` của tệp rig gộp với
   thân xe của phiên nới `mask_margin`: ô BEV dưới đó luôn UNKNOWN (loại CAT_EGO khi xem).
3. **Hệ xe → hệ bản đồ, bảo thủ.** Costmap hệ xe được đặt vào lưới sa bàn theo tư thế xe (hay tư thế camera cố định
   trên bàn): mỗi ô bản đồ lấy mẫu 3 × 3 điểm; OCCUPIED nếu có điểm rơi vào ô OCCUPIED của BEV, FREE chỉ khi mọi điểm FREE.
   Lưới điểm cách nhau 1/3 ô nên mọi ô OCCUPIED 5 cm của BEV, xoay góc nào, đều có ít nhất một điểm rơi vào (hình vuông
   cạnh 5 cm chứa đường tròn bán kính 2,5 cm > bán kính phủ 1,18 cm của lưới điểm). `CameraSemanticLayer.set_vehicle_frame`
   lấy mẫu MỘT điểm gần nhất nên ở góc xiên có thể làm mất ô OCCUPIED lẻ (tests/test_camera_ai_layer.py chỉ ra một tư
   thế như thế), vì vậy ở đây không dùng nó. Cái giá của lấy mẫu bảo thủ: ô OCCUPIED phình tối đa một ô bản đồ, nên mặt
   nạ ở mục 2 (tâm ô hệ xe) KHÔNG đủ giữ vật cản ra khỏi thân xe. Vì vậy mặt nạ thân xe được áp lần nữa trong HỆ BẢN ĐỒ,
   cho TỪNG LÔ, ở tư thế của lô đó (`ego_cells`): ô bản đồ có phần trong chung với hộp ở mục 2, hay chạm thân xe của
   phiên, thành UNKNOWN trước khi vào cửa sổ lọc. Bảo đảm (kiểm bằng rig tổng hợp, 25/09/2026): hộp AI không có phần
   trong chung với thân xe nới `mask_margin`, tại tư thế của lô, ở mọi góc xoay — như ngăn LiDAR bỏ điểm trong thân xe
   nới lề của từng scan.
4. **Lọc thời gian** (ĐỀ XUẤT – CHỜ CHỐT): ô bản đồ chỉ là OCCUPIED khi OCCUPIED ở ≥ `min_hits` (2) trong `window` (3)
   lô AI gần nhất mà mô-đun đã xử lý — cùng quy tắc 2/3 của LiDAR. Lọc trong HỆ BẢN ĐỒ nên dùng được cả khi xe chạy.
   Hai lô liên tiếp cách nhau quá `max_age_s` thì cửa sổ được xóa (bằng chứng cũ không cộng với bằng chứng mới).
5. **Lớp** `fusion.layers.CameraSemanticLayer` (hệ bản đồ) giữ kết quả; stamp = khung CŨ NHẤT được dùng trong lô mới
   nhất; tuổi quá `max_age_s` thì lớp không tươi (ngăn camera xử lý chuyện dừng xe, ui/camera_dock.py).

Ngưỡng: ngưỡng an toàn 0,15 của docs/DU_LIEU_VA_GIAY_PHEP.md là quy tắc "pixel là vật cản khi P(BLOCKED) ≥ 0,15" (chọn trên val
WoodScape theo F2). Nguồn vật cản chỉ dùng ô OCCUPIED, nên ở đây nó thành `t_blocked` = 0,15 (ĐỀ XUẤT – CHỜ CHỐT);
`t_free` (0,05) không đổi tập OCCUPIED (test kiểm) và FREE của camera không được planner dùng. Mặc định của BEV (t_free
0,15 / t_blocked 0,50) giữ nguyên cho lệnh `bev` — ở đó 0,15 là ngưỡng FREE; dùng nguyên như thế ở đây thì ngưỡng an toàn
không còn tác dụng gì lên vật cản (vật cản chỉ từ p ≥ 0,50).

AI chỉ THÊM vật cản: mô-đun này không xóa gì; ngăn camera nối nó vào `ObstacleBridge` riêng (tiền tố "camera_ai"), nên
FREE/UNKNOWN của camera không bao giờ xóa hay sửa vật cản của LiDAR, của người dùng hay của kịch bản. Planner chỉ dùng
hình chữ nhật vật cản: FREE của camera không có tác dụng gì lên lập đường.

Giấy phép: mô hình AI huấn luyện trên WoodScape (`bev.WOODSCAPE_ATTRIBUTION`, `bev.WOODSCAPE_LICENCE_NOTE`). Dùng nó trong
vòng điều khiển là quyết định 25/09/2026 của người làm khóa luận; Valeo chưa xác nhận cách đọc điều khoản
(docs/DU_LIEU_VA_GIAY_PHEP.md).

Mức bằng chứng: chỉ kiểm bằng rig tổng hợp, nguồn giả và bản ghi phát lại của nguồn giả (tests/test_camera_ai_layer.py,
tests/test_camera_dock_ui.py). CHƯA THỬ trên camera thật: chưa camera nào được hiệu chuẩn nên trên bàn thật mọi lô đều
bị chặn.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
from pathlib import Path
import time
from types import SimpleNamespace

import numpy as np
import shapely
from shapely.geometry import Polygon

from autopark.domain.sensors import SourceStamp
from autopark.domain.types import Pose
from autopark.geometry.footprint import body_polygon
from autopark.perception import bev
from autopark.perception.bev import BevResult, EgoBox, RigConfigError
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec, to_costmap

from .layers import MAP_FRAME, CameraSemanticLayer

# ---- tham số (mọi số là ĐỀ XUẤT – CHỜ CHỐT, chưa kiểm trên sa bàn) ---------------------------------------------------
AI_T_BLOCKED = 0.15        # ngưỡng an toàn docs/DU_LIEU_VA_GIAY_PHEP.md: P(BLOCKED) ≥ 0,15 → pixel vật cản → ô OCCUPIED
AI_T_FREE = 0.05           # không ảnh hưởng tới vật cản; chỉ để BEV có đủ ba mức khi xem
AI_WINDOW = 3              # lọc thời gian: số lô AI gần nhất ...
AI_MIN_HITS = 2            # ... ô phải OCCUPIED ở ít nhất chừng này lô
AI_MAX_AGE_S = 0.5         # tuổi tối đa (khung cũ nhất của lô mới nhất) để lớp còn "tươi"
AI_MASK_MARGIN_M = 0.05    # lề quanh thân xe của phiên: ô trong đó không bao giờ thành vật cản
MAP_SUPERSAMPLE = 3        # số điểm lấy mẫu mỗi chiều khi đặt BEV vào lưới bản đồ
SOURCE_ID = "camera_ai"
GATE_PREFIX = "AI chưa được dùng để điều khiển vì: "

SOURCE_LIVE, SOURCE_REPLAY, SOURCE_FAKE = "live", "replay", "fake"
SOURCE_KINDS = (SOURCE_LIVE, SOURCE_REPLAY, SOURCE_FAKE)
SOURCE_LABELS = {SOURCE_LIVE: "camera thật", SOURCE_REPLAY: "bản ghi phát lại", SOURCE_FAKE: "nguồn giả (thử)"}

SYNTHETIC_NOTE = ("TỔNG HỢP: rig camera ảo (nội tham danh định, ngoại tham GIẢ ĐỊNH của tệp rig) — vật cản chỉ để thử "
                  "phần mềm, không phải số đo")

DEFAULT_EXTRINSICS = bev.PROJECT / "configs/rig/camera_rig_extrinsics_v1.json"
DEFAULT_ROI_DIR = bev.PROJECT / "configs/roi/rig_v1"
DEFAULT_CALIBRATION_DIR = bev.DEFAULT_CALIBRATION_DIR
DEFAULT_CHECKPOINT = bev.PROJECT / "runs/ai_woodscape_rtx4000_v1/best.pt"


def gate_text(reasons) -> str:
    """Một dòng cho giao diện và log: "AI chưa được dùng để điều khiển vì: a; b"."""
    return GATE_PREFIX + "; ".join(reasons)


# ---- rig camera ------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CameraRig:
    """Các camera mà nguồn vật cản dùng. `problems` khác rỗng: không nạp được đủ, mọi lô bị chặn với các lý do đó."""
    cameras: dict = field(compare=False)       # "p<cổng>" → BevCamera; thứ tự = thứ tự bit của BEV
    ego: EgoBox | None = None                  # hộp thân xe `vehicle_assumed` của tệp rig (đã nới ego_margin_m)
    synthetic: bool = False                    # rig TỔNG HỢP (camera ảo): chỉ với phát lại/nguồn giả
    problems: tuple = ()
    description: str = ""

    @property
    def ports(self) -> list[int]:
        return [int(name[1:]) for name in self.cameras]


def load_camera_rig(ports, size=(640, 480), *, extrinsics=DEFAULT_EXTRINSICS, calibration_dir=DEFAULT_CALIBRATION_DIR,
                    roi_dir=DEFAULT_ROI_DIR) -> CameraRig:
    """Rig THẬT: nội tham `calibration/cam_p<cổng>.json` + ngoại tham `extrinsics` + ROI `roi_dir/roi_p<cổng>.png` qua
    `bev.load_rig`, cho đúng các cổng `ports` ở cỡ khung `size`. Không bao giờ ném: thiếu/hỏng tệp (kể cả lỗi lạ của tệp
    sửa tay) thì trả `CameraRig` rỗng có `problems` (nguồn vật cản sẽ chặn mọi lô với các lý do đó). Thiếu tệp ngoại tham
    thì lý do là danh sách tệp chưa có theo trình tự nội tham → ngoại tham → ROI (`missing_calibration_files`), không phải
    lỗi hệ điều hành. Cổng không có trong tệp ngoại tham cũng là một lý do chặn (không lặng lẽ bỏ camera người dùng đã
    chọn)."""
    where = f"{extrinsics} + {calibration_dir} + ROI {roi_dir}"
    try:
        ports = [int(p) for p in ports]
        if not ports:
            return CameraRig({}, None, False, ("chưa chọn camera nào",), where)
        missing = missing_calibration_files(ports, size, extrinsics=extrinsics, calibration_dir=calibration_dir,
                                            roi_dir=roi_dir)
        if not Path(extrinsics).is_file():
            return CameraRig({}, None, False, tuple(missing), where)
        cameras, rig, skipped = bev.load_rig(extrinsics, calibration_dir, {p: tuple(size) for p in ports},
                                             roi_dir=roi_dir)
    except Exception as exc:  # noqa: BLE001 - hợp đồng: không bao giờ ném; tệp hỏng kiểu lạ cũng thành lý do chặn
        text = str(exc) if isinstance(exc, (RigConfigError, OSError, ValueError)) else \
            f"tệp hiệu chuẩn/ngoại tham/ROI hỏng ({type(exc).__name__}: {exc})"
        lines = [line.strip(" -") for line in text.splitlines() if line.strip(" -")]
        if len(lines) > 1 and lines[0].endswith(":"):
            lines = lines[1:]
        try:
            roi_lines = [m for m in missing_calibration_files(ports, size, extrinsics=extrinsics,
                                                              calibration_dir=calibration_dir, roi_dir=roi_dir)
                         if m.startswith("chưa có ROI")]
        except Exception:  # noqa: BLE001 - chỉ là thông tin thêm
            roi_lines = []
        return CameraRig({}, None, False, tuple(lines) + tuple(roi_lines), where)
    problems = tuple(f"{name}: {why}" for name, why in skipped.items())
    return CameraRig(cameras, rig.ego, False, problems, where)


def missing_calibration_files(ports, size=(640, 480), *, extrinsics=DEFAULT_EXTRINSICS,
                              calibration_dir=DEFAULT_CALIBRATION_DIR, roi_dir=DEFAULT_ROI_DIR) -> list[str]:
    """Tệp hiệu chuẩn CHƯA CÓ của các cổng `ports`, theo đúng trình tự làm (docs/KIEN_TRUC.md): nội tham →
    ngoại tham → ROI; mỗi dòng nêu bước và tài liệu. Rỗng khi đủ tệp (tệp có mà hỏng thì `bev.load_rig` báo)."""
    from autopark.perception.fisheye_calib import default_output_path

    width, height = (int(s) for s in size)
    ports = [int(p) for p in ports]
    lines = []
    no_intr = [f"p{p}" for p in ports if not default_output_path(p, (width, height), Path(calibration_dir)).is_file()]
    if no_intr:
        pattern = Path(calibration_dir) / default_output_path(0, (width, height)).name.replace("p0", "p<cổng>", 1)
        lines.append(f"chưa có nội tham của {', '.join(no_intr)} ({pattern}, {width}×{height}) — bước 1: hiệu chuẩn "
                     f"theo docs/PHAN_CUNG_VA_HIEU_CHUAN.md#noi-tham")
    if not Path(extrinsics).is_file():
        lines.append(f"chưa có tệp ngoại tham đã đo {Path(extrinsics)} — bước 2, sau nội tham: đo theo "
                     f"docs/PHAN_CUNG_VA_HIEU_CHUAN.md#ngoai-tham")
    no_roi = [f"p{p}" for p in ports if not (Path(roi_dir) / f"roi_p{p}.png").is_file()]
    if no_roi:
        lines.append(f"chưa có ROI của {', '.join(no_roi)} ({Path(roi_dir) / 'roi_p<cổng>.png'}) — bước 3: dựng theo "
                     f"docs/PHAN_CUNG_VA_HIEU_CHUAN.md#roi")
    return lines


def synthetic_camera_rig(ports=None, size=(640, 480), *, extrinsics=bev.DEFAULT_EXTRINSICS) -> CameraRig:
    """Rig TỔNG HỢP: tư thế camera của tệp rig (mặc định v0, GIẢ ĐỊNH), nội tham danh định `bev.nominal_intrinsics`.
    Chỉ để thử với bản ghi phát lại hay nguồn giả; nguồn vật cản từ chối nó với camera thật. Không bao giờ ném: tệp rig
    thiếu/hỏng (gõ sai tên tệp) thì trả rig rỗng có lý do chặn."""
    description = f"TỔNG HỢP: bev.synthetic_rig({extrinsics})"
    try:
        cameras, ego = bev.synthetic_rig(extrinsics, *size)
    except Exception as exc:  # noqa: BLE001 - hợp đồng: không bao giờ ném
        return CameraRig({}, None, True, (f"không dựng được rig TỔNG HỢP từ {extrinsics}: {exc}",), description)
    problems = []
    if ports is not None:
        wanted = [f"p{int(p)}" for p in ports]
        problems = [f"p{name[1:]}: cổng không có trong tệp rig {extrinsics}" for name in wanted if name not in cameras]
        cameras = {name: cam for name, cam in cameras.items() if name in wanted}
    return CameraRig(cameras, ego, True, tuple(problems), description)


def body_ego_box(cfg, margin: float) -> EgoBox:
    """Thân xe của phiên (hệ xe, gốc tâm trục sau) nới `margin` mỗi phía — như mặt nạ thân xe của ngăn LiDAR."""
    return EgoBox(-cfg.rear_overhang - margin, cfg.wheelbase + cfg.front_overhang + margin,
                  -cfg.width / 2 - margin, cfg.width / 2 + margin)


def union_box(a: EgoBox | None, b: EgoBox | None) -> EgoBox | None:
    """Hộp bao của hai hộp (BEV chỉ nhận một hộp thân xe; hộp bao che nhiều hơn, không bao giờ ít hơn)."""
    if a is None or b is None:
        return a or b
    return EgoBox(min(a.x_min, b.x_min), max(a.x_max, b.x_max), min(a.y_min, b.y_min), max(a.y_max, b.y_max))


# ---- hệ xe → hệ bản đồ -----------------------------------------------------------------------------------------------
def _blocks(a: np.ndarray, k: int) -> np.ndarray:
    rows, cols = a.shape[0] // k, a.shape[1] // k
    return a.reshape(rows, k, cols, k)


def vehicle_states_to_map(states: np.ndarray, vehicle_grid: GridSpec, map_grid: GridSpec, pose: Pose,
                          supersample: int = MAP_SUPERSAMPLE) -> np.ndarray:
    """Trạng thái ô của lưới hệ xe (`states` trên `vehicle_grid`) đặt vào `map_grid`, xe ở `pose` trong hệ bản đồ.

    Mỗi ô bản đồ lấy mẫu `supersample` × `supersample` điểm đều nhau: OCCUPIED nếu có điểm rơi vào ô OCCUPIED, FREE chỉ
    khi MỌI điểm rơi vào ô FREE, còn lại UNKNOWN (điểm ngoài lưới hệ xe là UNKNOWN). Bảo thủ: ô OCCUPIED không bị mất khi
    xoay (xem đầu module), đổi lại vật có thể phình tối đa một ô bản đồ."""
    k = int(supersample)
    if k < 1:
        raise ValueError("supersample phải ≥ 1")
    states = np.asarray(states)
    if states.shape != vehicle_grid.shape:
        raise ValueError(f"lưới hệ xe {vehicle_grid.shape} khác trạng thái {states.shape}")
    rows, cols = map_grid.shape
    step = map_grid.resolution / k
    xs = map_grid.x_min + (np.arange(cols * k) + 0.5) * step
    ys = map_grid.y_min + (np.arange(rows * k) + 0.5) * step
    gx, gy = np.meshgrid(xs, ys)
    c, s = math.cos(pose.yaw), math.sin(pose.yaw)
    dx, dy = gx - pose.x, gy - pose.y
    bx, by = c * dx + s * dy, -s * dx + c * dy                   # điểm trong hệ xe
    vr, vc = vehicle_grid.shape
    r = np.floor((by - vehicle_grid.y_min) / vehicle_grid.resolution).astype(np.int64)
    q = np.floor((bx - vehicle_grid.x_min) / vehicle_grid.resolution).astype(np.int64)
    inside = (r >= 0) & (r < vr) & (q >= 0) & (q < vc)
    sampled = np.full(gx.shape, UNKNOWN, np.int8)
    sampled[inside] = states[r[inside], q[inside]]
    out = np.full((rows, cols), UNKNOWN, np.int8)
    out[_blocks(sampled == FREE, k).all(axis=(1, 3))] = FREE
    out[_blocks(sampled == OCCUPIED, k).any(axis=(1, 3))] = OCCUPIED
    return out


def ego_cells(map_grid: GridSpec, pose: Pose, ego: EgoBox | None, body=None) -> np.ndarray:
    """Ô bản đồ (mảng bool cỡ `map_grid.shape`) bị thân xe che ở `pose`: HÌNH VUÔNG của ô có phần TRONG chung với hộp
    `ego` (hệ xe, đã nới lề) đặt ở `pose`, hoặc giao — kể cả chạm biên, vì `check_pose` tính chạm biên là va chạm — đa
    giác thân xe `body` (hệ bản đồ). Ô chỉ chạm biên hộp nới lề vẫn giữ (nó cách thân xe đúng bằng lề). Chỉ xét các ô
    quanh hộp bao nên rẻ với sa bàn lớn."""
    rows, cols = map_grid.shape
    res = map_grid.resolution
    under = np.zeros((rows, cols), bool)
    box_poly = None
    if ego is not None:
        corners = ((ego.x_min, ego.y_min), (ego.x_max, ego.y_min), (ego.x_max, ego.y_max), (ego.x_min, ego.y_max))
        box_poly = Polygon([pose.to_world(x, y) for x, y in corners])
    polys = [p for p in (box_poly, body) if p is not None and not p.is_empty]
    if not polys:
        return under
    x0 = min(p.bounds[0] for p in polys)
    y0 = min(p.bounds[1] for p in polys)
    x1 = max(p.bounds[2] for p in polys)
    y1 = max(p.bounds[3] for p in polys)
    c0 = max(0, int(math.floor((x0 - map_grid.x_min) / res)) - 1)
    c1 = min(cols, int(math.ceil((x1 - map_grid.x_min) / res)) + 1)
    r0 = max(0, int(math.floor((y0 - map_grid.y_min) / res)) - 1)
    r1 = min(rows, int(math.ceil((y1 - map_grid.y_min) / res)) + 1)
    if c0 >= c1 or r0 >= r1:
        return under
    gx, gy = np.meshgrid(map_grid.x_min + np.arange(c0, c1) * res, map_grid.y_min + np.arange(r0, r1) * res)
    cells = shapely.box(gx, gy, gx + res, gy + res)
    sub = np.zeros(gx.shape, bool)
    if box_poly is not None:
        sub |= shapely.intersects(cells, box_poly) & ~shapely.touches(cells, box_poly)
    if body is not None:
        sub |= shapely.intersects(cells, body)
    under[r0:r1, c0:c1] = sub
    return under


# ---- chặn không cần lô AI ---------------------------------------------------------------------------------------------
def static_gate_reasons(rig: CameraRig, source_kind: str) -> list[str]:
    """Lý do chặn MỌI lô, biết được từ cấu hình: rig không nạp được, rig rỗng, rig TỔNG HỢP với camera thật."""
    reasons = list(rig.problems)
    if not rig.cameras and not reasons:
        reasons.append("rig không có camera nào")
    if rig.synthetic and source_kind == SOURCE_LIVE:
        reasons.append("rig camera TỔNG HỢP (camera ảo, nội tham danh định, ngoại tham GIẢ ĐỊNH) chỉ dùng với bản "
                       "ghi phát lại hoặc nguồn giả, không bao giờ với camera thật")
    return reasons


def _acceptance_missing(rig: CameraRig, names) -> list[str]:
    """Chặt hơn `bev.unusable_reasons` (chỉ chặn `all_pass` = false): chỉ true của JSON mới đạt. None (tệp không có kết
    quả tiêu chí) hay giá trị lạ cũng chặn; False thì `bev.unusable_reasons` đã ghi lý do."""
    reasons = []
    for name in names:
        acc = rig.cameras[name].acceptance_all_pass
        if acc is not True and acc is not False:
            reasons.append(f"{name}: tệp nội tham không có kết quả tiêu chí (acceptance.all_pass) — hiệu chuẩn lại "
                           f"bằng fisheye_calib")
    return reasons


def preflight_reasons(rig: CameraRig, source_kind: str) -> list[str]:
    """Lý do chặn biết được TRƯỚC khi có lô AI nào (nút "Nạp lại hiệu chuẩn" khi AI đang tắt): `static_gate_reasons`,
    rồi với rig thật, lý do của từng camera như `CameraObstacleMapper.gate` khi MỌI camera có dữ liệu (ngoại tham chưa
    đo, thiếu ROI, nội tham chưa đạt, dữ liệu TỔNG HỢP). Rig tổng hợp: các lý do từng camera chỉ là ghi chú, không chặn.
    Rỗng: tệp đủ và đạt — từng lô vẫn được kiểm lại khi chạy (cỡ khung, camera thiếu trong lô)."""
    reasons = static_gate_reasons(rig, source_kind)
    if reasons or rig.synthetic:
        return reasons
    everyone = SimpleNamespace(views=dict.fromkeys(rig.cameras))      # như một BevResult có đủ mọi camera
    return list(bev.unusable_reasons(everyone, rig.cameras)) + _acceptance_missing(rig, rig.cameras)


# ---- nguồn vật cản ---------------------------------------------------------------------------------------------------
@dataclass
class MapperUpdate:
    """Kết quả một lần `update()`. `processed` = có lô AI MỚI được xét ở lần gọi này."""
    processed: bool = False
    usable: bool = False
    reasons: list = field(default_factory=list)        # lý do chặn; rỗng khi lô dùng được
    notes: list = field(default_factory=list)          # ghi chú: TỔNG HỢP, camera thiếu trong lô...
    batch_id: int | None = None
    stamp_t: float | None = None                       # khung cũ nhất được dùng (đồng hồ bàn thử)
    cameras_used: list = field(default_factory=list)
    occupied_batch: int = 0                            # ô bản đồ OCCUPIED của riêng lô này
    occupied_filtered: int = 0                         # ô bản đồ OCCUPIED sau lọc thời gian
    window_fill: int = 0                               # số lô đang có trong cửa sổ lọc
    bev_ms: float | None = None
    bev: BevResult | None = None

    def gate_text(self) -> str:
        return gate_text(self.reasons) if self.reasons else ""


class CameraObstacleMapper:
    """Lô AI mới nhất → lớp `CameraSemanticLayer` (hệ bản đồ) sau chặn, BEV, đặt vào bản đồ, lọc thời gian.

    `source_kind`: "live" (camera thật), "replay" (bản ghi phát lại) hoặc "fake" (nguồn giả trong test). `vehicle_cfg`:
    `VehicleConfig` của phiên (mặt nạ thân xe); None thì chỉ dùng hộp thân xe của tệp rig. Chỉ đọc kết quả AI và ghi lớp
    của chính nó; không đụng tới phiên đỗ xe."""

    def __init__(self, rig: CameraRig, map_grid: GridSpec, *, source_kind: str, vehicle_cfg=None,
                 t_free: float = AI_T_FREE, t_blocked: float = AI_T_BLOCKED, window: int = AI_WINDOW,
                 min_hits: int = AI_MIN_HITS, max_age_s: float = AI_MAX_AGE_S, mask_margin: float = AI_MASK_MARGIN_M,
                 bev_grid: GridSpec | None = None, max_range: float | None = bev.RIG_MAX_RANGE,
                 supersample: int = bev.DEFAULT_SUPERSAMPLE, map_supersample: int = MAP_SUPERSAMPLE,
                 name: str = SOURCE_ID):
        bev.check_thresholds(t_free, t_blocked)
        bev.check_max_range(max_range)
        if source_kind not in SOURCE_KINDS:
            raise ValueError(f"source_kind phải là một trong {SOURCE_KINDS}, nhận {source_kind!r}")
        if int(window) < 1 or not 1 <= int(min_hits) <= int(window):
            raise ValueError(f"cần window ≥ 1 và 1 ≤ min_hits ≤ window (nhận {window}, {min_hits})")
        if not math.isfinite(mask_margin) or mask_margin < 0:
            raise ValueError("mask_margin phải ≥ 0")
        self.rig, self.map_grid, self.source_kind = rig, map_grid, source_kind
        self.t_free, self.t_blocked = float(t_free), float(t_blocked)
        self.window, self.min_hits = int(window), int(min_hits)
        self.max_age_s, self.mask_margin = float(max_age_s), float(mask_margin)
        self.bev_grid = bev_grid or GridSpec(*bev.RIG_GRID)
        self.max_range, self.supersample, self.map_supersample = max_range, int(supersample), int(map_supersample)
        self.vehicle_cfg = vehicle_cfg
        body = None if vehicle_cfg is None else body_ego_box(vehicle_cfg, self.mask_margin)
        self.ego = union_box(rig.ego, body)
        # required=True: trong phép hợp nhất RIÊNG của ngăn camera, lớp cũ/không hợp lệ làm bản đồ không hợp lệ, nên
        # đồng bộ lúc chỉnh sa bàn không làm gì (giữ vật cản) thay vì xóa vật cản vì "không thấy gì"
        self.layer = CameraSemanticLayer(map_grid, max_age_s=self.max_age_s, name=name, required=True)
        self.static_reasons = self._static_gate()
        self._window: deque[np.ndarray] = deque(maxlen=self.window)
        self._last_stamp: float | None = None
        self.last_batch_id: int | None = None
        self.batches = 0              # lô đã xét (dùng được hay bị chặn)
        self.batches_usable = 0
        self.batches_refused = 0
        self.batches_skipped = 0      # lô AI ra giữa hai lần gọi update() nên không được xét (theo số thứ tự lô)
        self.window_resets = 0
        self.processed_times: deque[float] = deque(maxlen=50)
        self.last = MapperUpdate(reasons=list(self.static_reasons))

    # ---- chặn ----
    def _static_gate(self) -> list[str]:
        return static_gate_reasons(self.rig, self.source_kind)

    def gate(self, result: BevResult) -> tuple[list[str], list[str]]:
        """(lý do chặn, ghi chú) cho một BEV. Rig thật: `bev.unusable_reasons` + nội tham không có kết quả tiêu chí.
        Rig tổng hợp (đã qua `_static_gate`, tức không phải camera thật): chỉ chặn khi không camera nào có dữ liệu; các
        lý do của BEV thành ghi chú kèm nhãn TỔNG HỢP."""
        if self.rig.synthetic:
            ignored = [r for r in bev.unusable_reasons(result, self.rig.cameras) if r != "không camera nào có dữ liệu"]
            notes = [SYNTHETIC_NOTE] + [f"(rig tổng hợp, bỏ qua) {r}" for r in ignored]
            return ([] if result.views else ["không camera nào có dữ liệu"]), notes
        reasons = list(bev.unusable_reasons(result, self.rig.cameras))
        reasons += _acceptance_missing(self.rig, result.views)
        return reasons, []

    @property
    def blocked(self) -> bool:
        """Cấu hình bị chặn bất kể dữ liệu (rig không nạp được, rig tổng hợp với camera thật)."""
        return bool(self.static_reasons)

    # ---- trạng thái ----
    def fresh(self, now: float) -> bool:
        """Lớp có dữ liệu hợp lệ và khung cũ nhất của lô mới nhất chưa quá `max_age_s`."""
        return self.layer.fresh(now)

    def age(self, now: float) -> float | None:
        return None if self._last_stamp is None else now - self._last_stamp

    def rate(self) -> float:
        """Số lô được xét mỗi giây (đồng hồ máy, 50 lần gần nhất)."""
        t = list(self.processed_times)
        return (len(t) - 1) / (t[-1] - t[0]) if len(t) >= 2 and t[-1] > t[0] else 0.0

    def filtered_states(self) -> np.ndarray | None:
        if self.layer.costmap is None:
            return None
        return np.array(self.layer.costmap.cells, np.int8)

    def warm_up(self) -> float:
        """Dựng trước bảng hình học của BEV (`bev.view_geometry`, 0,1–0,5 s mỗi camera lần đầu) để lô đầu không làm giao
        diện đứng. Trả thời gian (ms). Không đổi lớp hay cửa sổ lọc."""
        if not self.rig.cameras:
            return 0.0
        t0 = time.perf_counter()
        probs = {name: np.zeros((cam.calibration.intrinsics.height, cam.calibration.intrinsics.width), np.float32)
                 for name, cam in self.rig.cameras.items()}
        bev.build_bev(probs, self.rig.cameras, self.bev_grid, t_free=self.t_free, t_blocked=self.t_blocked,
                      max_range=self.max_range, supersample=self.supersample, ego=self.ego)
        return 1000.0 * (time.perf_counter() - t0)

    def _refuse(self, reasons, stamp_t: float | None, update: MapperUpdate) -> MapperUpdate:
        """Lô bị chặn: không ô OCCUPIED nào, lớp không hợp lệ, cửa sổ lọc xóa (không cộng bằng chứng qua lô bị chặn)."""
        self._window.clear()
        t = max(0.0, stamp_t if stamp_t is not None else (self._last_stamp or 0.0))
        self.layer.set(to_costmap(np.full(self.map_grid.shape, UNKNOWN, np.int8), self.map_grid,
                                  SourceStamp(SOURCE_ID, t, False, MAP_FRAME)))
        self.batches_refused += 1
        update.usable, update.reasons = False, list(reasons)
        update.occupied_filtered = 0
        update.window_fill = 0
        return update

    # ---- một lô ----
    def update(self, result, vehicle_pose: Pose, now: float) -> MapperUpdate:
        """Xét lô AI mới nhất (`AIResult` hay None). Lô đã xét rồi (cùng `batch_id`) thì không làm gì và trả kết quả lần
        trước với `processed` = False. `vehicle_pose`: tư thế xe — hay chỗ đặt camera cố định — trong hệ bản đồ, dùng cho
        CẢ lô (không nội suy theo thời điểm chụp; sai số = tốc độ xe × tuổi lô, xem docs/KIEN_TRUC.md)."""
        if result is None or result.batch_id == self.last_batch_id:
            self.last.processed = False
            if self.static_reasons and not self.last.reasons:
                self.last.reasons = list(self.static_reasons)
            return self.last
        if self.last_batch_id is not None and result.batch_id > self.last_batch_id + 1:
            self.batches_skipped += result.batch_id - self.last_batch_id - 1
        self.last_batch_id = result.batch_id
        self.batches += 1
        self.processed_times.append(time.perf_counter())
        frames = result.frame_set.frames
        update = MapperUpdate(processed=True, batch_id=result.batch_id)
        self.last = update
        if self.static_reasons:
            return self._refuse(self.static_reasons, None, update)
        probs, foreign = {}, []
        for port, prob in result.probs.items():
            name = f"p{int(port)}"
            if name in self.rig.cameras:
                probs[name] = prob
            else:
                foreign.append(int(port))
        if foreign:
            update.notes.append(f"cổng {sorted(foreign)} có kết quả AI nhưng không có trong rig camera: bỏ qua")
        missing = {name: "không có trong lô AI này (camera chậm, lệch pha hay mất khung)"
                   for name in self.rig.cameras if name not in probs}
        if missing:
            update.notes.append("lô thiếu " + ", ".join(sorted(missing)) + ": vùng chỉ camera đó thấy là UNKNOWN")
        if not probs:
            return self._refuse(["lô AI không có camera nào của rig"], None, update)
        # nội tham chỉ đúng cho đúng mode đã hiệu chuẩn: khung cỡ khác (camera trả mode khác mode xin, bản ghi mode khác)
        # thì từ chối, kể cả khi cùng tỉ lệ khung (BEV chỉ từ chối khi khác tỉ lệ)
        wrong_size = []
        for name in probs:
            frame = frames.get(int(name[1:]))
            intr = self.rig.cameras[name].calibration.intrinsics
            if frame is not None and (frame.meta.width, frame.meta.height) != (intr.width, intr.height):
                wrong_size.append(f"{name}: khung {frame.meta.width}×{frame.meta.height} khác cỡ ảnh đã hiệu chuẩn "
                                  f"{intr.width}×{intr.height} (mode camera khác: nội tham không dùng được)")
        if wrong_size:
            return self._refuse(wrong_size, None, update)
        t0 = time.perf_counter()
        try:
            result_bev = bev.build_bev(probs, self.rig.cameras, self.bev_grid, t_free=self.t_free,
                                       t_blocked=self.t_blocked, max_range=self.max_range, supersample=self.supersample,
                                       ego=self.ego, missing=missing)
        except (ValueError, RigConfigError) as exc:            # ví dụ tỉ lệ khung khác hiệu chuẩn (mode camera khác)
            return self._refuse([f"không dựng được BEV: {exc}"], None, update)
        update.bev_ms = 1000.0 * (time.perf_counter() - t0)
        update.bev = result_bev
        update.cameras_used = list(result_bev.views)
        stamps = [frames[int(name[1:])].meta.stamp.t for name in result_bev.views if int(name[1:]) in frames]
        stamp_t = max(0.0, min(stamps)) if stamps else max(0.0, float(result.t_done))
        update.stamp_t = stamp_t
        reasons, notes = self.gate(result_bev)
        update.notes.extend(notes)
        if reasons:
            return self._refuse(reasons, stamp_t, update)
        if self._last_stamp is not None and stamp_t - self._last_stamp > self.max_age_s and self._window:
            self._window.clear()                                 # khoảng trống quá dài: bằng chứng cũ không cộng tiếp
            self.window_resets += 1
            update.notes.append(f"cửa sổ lọc xóa: hai lô cách nhau {stamp_t - self._last_stamp:.2f} s > "
                                f"{self.max_age_s:g} s")
        self._last_stamp = stamp_t
        states_map = vehicle_states_to_map(result_bev.states, self.bev_grid, self.map_grid, vehicle_pose,
                                           self.map_supersample)
        # mặt nạ thân xe trong HỆ BẢN ĐỒ, ở tư thế của lô này: lấy mẫu bảo thủ ở trên làm ô OCCUPIED phình tối đa một ô,
        # nên mặt nạ tâm ô của BEV không đủ giữ vật cản ra khỏi thân xe (xem đầu module, mục 3)
        body = None if self.vehicle_cfg is None else body_polygon(self.vehicle_cfg, vehicle_pose)
        states_map[ego_cells(self.map_grid, vehicle_pose, self.ego, body)] = UNKNOWN
        occupied = states_map == OCCUPIED
        self._window.append(occupied)
        hits = np.sum(np.stack(list(self._window)), axis=0)
        filtered = np.full(self.map_grid.shape, UNKNOWN, np.int8)
        filtered[states_map == FREE] = FREE
        filtered[hits >= self.min_hits] = OCCUPIED
        self.layer.set(to_costmap(filtered, self.map_grid, SourceStamp(SOURCE_ID, stamp_t, True, MAP_FRAME)))
        self.batches_usable += 1
        update.usable = True
        update.occupied_batch = int(occupied.sum())
        update.occupied_filtered = int((filtered == OCCUPIED).sum())
        update.window_fill = len(self._window)
        return update

    def describe(self) -> dict:
        return {"source_kind": self.source_kind, "rig": self.rig.description, "synthetic": self.rig.synthetic,
                "cameras": list(self.rig.cameras), "t_free": self.t_free, "t_blocked": self.t_blocked,
                "window": self.window, "min_hits": self.min_hits, "max_age_s": self.max_age_s,
                "mask_margin_m": self.mask_margin, "ego": None if self.ego is None else self.ego.to_dict(),
                "batches": self.batches, "usable": self.batches_usable, "refused": self.batches_refused,
                "skipped": self.batches_skipped, "window_resets": self.window_resets,
                "attribution": bev.WOODSCAPE_ATTRIBUTION, "licence": bev.WOODSCAPE_LICENCE_NOTE}
