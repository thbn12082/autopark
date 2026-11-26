"""Ngoại tham camera từ bốn tờ ChArUco in sẵn (`rig_sheets`), không cần đo bằng thước. Thêm 24/11/2026.

    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.sheet_extrinsics solve --dir runs\\calib\\<phiên>\\to_in
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.sheet_extrinsics solve --dir runs\\calib\\<phiên>\\to_in --out configs\\rig\\camera_rig_extrinsics_v1.json
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.sheet_extrinsics solve --port 1 --images a.png b.png

`--dir` đọc mọi ảnh trong các thư mục con `cam_p1` … `cam_p4` (đúng chỗ cửa sổ quan sát lưu ảnh khi chạy với
`--calibration-dir`). Ảnh không thấy tờ nào bị bỏ qua và báo lý do, nên ảnh bảng Kindle cũ nằm chung thư mục không ảnh
hưởng.

Cách giải:
1. Mỗi ảnh: dò bốn bảng ChArUco (mỗi tờ một dải mã nên không nhầm tờ). Góc tìm được → tọa độ hệ xe trên mặt sàn qua
   `rig_sheets.corners_vehicle_m` với kích thước xe của `configs/rig/to_ngoai_tham_xe.json`.
2. Tư thế xe → camera: `extrinsics_calib.solve_pose` (khởi tạo `cv2.fisheye.solvePnP` + IPPE, tinh chỉnh LM trên sai số
   điểm ảnh qua mô hình Kannala–Brandt của tệp nội tham).
3. Kiểm chéo: ảnh thấy hai tờ thì giải riêng từng tờ và so (tờ đặt lệch lộ ra ở đây). Nhiều ảnh thì giải chung rồi so
   từng ảnh với tư thế chung.
4. Từ chối nếu: RMS chiếu lại > `MAX_RMS_PX`, ít góc, camera dưới sàn hay quá cao, nằm ngoài hộp hợp lý quanh xe, nhìn
   sai hướng của cổng, hoặc các tờ/ảnh không khớp nhau.

Kết quả đạt ghi bằng `extrinsics_calib.write_rig_file` (cùng tệp v1, cùng cách sao lưu và đọc lại bằng BEV). Mọi ngưỡng
là ĐỀ XUẤT – CHỜ CHỐT. Kiểm trên ảnh tổng hợp ở tests/test_sheet_extrinsics.py; chưa thử trên camera thật lúc thêm.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import sys

import cv2
import numpy as np

from . import extrinsics_calib as ec
from . import fisheye_calib as fc
from . import rig_sheets as rs
from .calibration import Extrinsics
from .paths import PROJECT, atomic_write_json

FORMAT = "autopark.sheet_extrinsics/1"
MAX_RMS_PX = 1.0                 # góc ChArUco đúng vị trí in, nên sai số còn lại là dò góc + nội tham + đặt tờ
MIN_CORNERS = 8
MIN_SHEET_CORNERS = 6            # một tờ có ít nhất chừng này góc thì mới giải riêng để kiểm chéo
MAX_SHEET_SPREAD_M = 0.015       # hai tờ trong cùng ảnh: vị trí camera suy từ mỗi tờ lệch tối đa chừng này
MAX_SHEET_SPREAD_DEG = 1.0
MAX_IMAGE_SPREAD_M = 0.01        # mỗi ảnh so với tư thế chung
MAX_IMAGE_SPREAD_DEG = 0.5
CAMERA_HEIGHT_M = (0.02, 0.5)
CAMERA_BOX_M = {"x": (-0.20, 0.45), "y": (-0.20, 0.20)}   # camera phải gắn trên/sát thân xe
EXPECTED_DIRECTION = {1: "front", 2: "rear", 3: "left", 4: "right"}
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp")
THRESHOLDS = {"max_rms_px": MAX_RMS_PX, "min_corners": MIN_CORNERS, "max_sheet_spread_m": MAX_SHEET_SPREAD_M,
              "max_sheet_spread_deg": MAX_SHEET_SPREAD_DEG, "max_image_spread_m": MAX_IMAGE_SPREAD_M,
              "max_image_spread_deg": MAX_IMAGE_SPREAD_DEG, "camera_height_m": list(CAMERA_HEIGHT_M),
              "camera_box_m": CAMERA_BOX_M}


class SheetError(RuntimeError):
    pass


def load_vehicle(path=rs.VEHICLE_FILE) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        vehicle = {k: float(data[k]) for k in rs.VEHICLE_KEYS}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SheetError(f"không đọc được kích thước xe {path}: {exc}") from exc
    if not all(v > 0 for v in vehicle.values()):
        raise SheetError(f"{path}: kích thước xe phải dương")
    vehicle["_path"] = str(path)
    vehicle["_measured"] = data.get("measured") is True
    return vehicle


# ---- dò ---------------------------------------------------------------------------------------------------------------
@dataclass
class SheetHit:
    key: str
    ids: np.ndarray          # (N,) id góc ChArUco
    image_px: np.ndarray     # (N, 2)
    vehicle_m: np.ndarray    # (N, 3), z = 0
    markers: int


_BOARDS: dict = {}


def _board(sheet: dict):
    if sheet["key"] not in _BOARDS:
        _BOARDS[sheet["key"]] = rs.make_board(sheet["first_id"])
    return _BOARDS[sheet["key"]]


def detect_sheets(image: np.ndarray, vehicle: dict) -> list[SheetHit]:
    gray = fc.to_gray(image)
    hits = []
    for sheet in rs.SHEETS:
        board = _board(sheet)
        ch_corners, ch_ids, _, marker_ids = cv2.aruco.CharucoDetector(board).detectBoard(gray)
        if ch_ids is None or len(ch_ids) == 0:
            continue
        ids = ch_ids.ravel().astype(int)
        xy = rs.corners_vehicle_m(sheet, board, vehicle)[ids]
        hits.append(SheetHit(sheet["key"], ids, ch_corners.reshape(-1, 2).astype(np.float64),
                             np.column_stack([xy, np.zeros(len(ids))]), 0 if marker_ids is None else len(marker_ids)))
    return hits


# ---- giải -------------------------------------------------------------------------------------------------------------
def pose_from(obj: np.ndarray, img: np.ndarray, K, D) -> tuple:
    """(R_cv, t_cv, sai số px từng điểm): camera → xe."""
    try:
        rv, tv, err = ec.solve_pose(obj, img, K, D)
    except ec.ExtrinsicsError as exc:
        raise SheetError(str(exc)) from exc
    R = cv2.Rodrigues(rv)[0]
    return R.T, -R.T @ tv, err


def rms(err) -> float:
    return float(np.sqrt(np.mean(np.asarray(err) ** 2)))


@dataclass
class ImageResult:
    path: str
    image: np.ndarray | None
    hits: list = field(default_factory=list)
    used: bool = False
    reason: str | None = None
    R_cv: np.ndarray | None = None
    t_cv: np.ndarray | None = None
    rms_px: float | None = None
    sheet_poses: dict = field(default_factory=dict)      # key → (R_cv, t_cv, rms, n)
    sheet_spread: dict | None = None
    deviation_m: float | None = None
    deviation_deg: float | None = None

    @property
    def n_corners(self) -> int:
        return int(sum(len(h.ids) for h in self.hits))

    def to_dict(self) -> dict:
        r = lambda x, nd=4: None if x is None else round(float(x), nd)
        out = {"image": self.path, "used": self.used, "rejected_reason": self.reason,
               "sheets": {h.key: {"corners": len(h.ids), "markers": h.markers} for h in self.hits},
               "rms_px": r(self.rms_px), "deviation_m": r(self.deviation_m, 5), "deviation_deg": r(self.deviation_deg),
               "sheet_spread": self.sheet_spread}
        if self.t_cv is not None:
            out["camera_from_this_image"] = {"position_m": [r(v, 5) for v in self.t_cv],
                                             **{k: r(v) for k, v in ec.rig_angles(self.R_cv).items()}}
        out["camera_from_each_sheet"] = {
            k: {"position_m": [r(v, 5) for v in t], "rms_px": r(e), "corners": n,
                **{a: r(v) for a, v in ec.rig_angles(R).items()}} for k, (R, t, e, n) in self.sheet_poses.items()}
        return out


def analyse_image(res: ImageResult, vehicle: dict, K, D, size) -> ImageResult:
    try:
        img = res.image
        if img is None:
            raise SheetError("không đọc được ảnh")
        if (img.shape[1], img.shape[0]) != tuple(size):
            raise SheetError(f"ảnh {img.shape[1]}×{img.shape[0]} khác cỡ nội tham {size[0]}×{size[1]}")
        res.hits = detect_sheets(img, vehicle)
        if not res.hits:
            raise SheetError("không thấy tờ ChArUco nào")
        if res.n_corners < MIN_CORNERS:
            raise SheetError(f"chỉ thấy {res.n_corners} góc ChArUco (cần ≥ {MIN_CORNERS}): tờ quá xa, bị che hay lóa")
        obj = np.vstack([h.vehicle_m for h in res.hits])
        pix = np.vstack([h.image_px for h in res.hits])
        res.R_cv, res.t_cv, err = pose_from(obj, pix, K, D)
        res.rms_px = rms(err)
        for h in res.hits:
            if len(h.ids) >= MIN_SHEET_CORNERS:
                try:
                    R, t, e = pose_from(h.vehicle_m, h.image_px, K, D)
                    res.sheet_poses[h.key] = (R, t, rms(e), len(h.ids))
                except SheetError:
                    pass
        if len(res.sheet_poses) >= 2:
            keys = list(res.sheet_poses)
            worst = {"m": 0.0, "deg": 0.0, "pair": None}
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    (Ra, ta, *_), (Rb, tb, *_) = res.sheet_poses[keys[i]], res.sheet_poses[keys[j]]
                    dm, dd = float(np.linalg.norm(ta - tb)), ec.rotation_angle_deg(Ra, Rb)
                    if dd > worst["deg"] or dm > worst["m"]:
                        worst = {"m": max(dm, worst["m"]), "deg": max(dd, worst["deg"]), "pair": [keys[i], keys[j]]}
            res.sheet_spread = {"position_m": round(worst["m"], 5), "angle_deg": round(worst["deg"], 4),
                                "pair": worst["pair"]}
            if worst["m"] > MAX_SHEET_SPREAD_M or worst["deg"] > MAX_SHEET_SPREAD_DEG:
                raise SheetError(f"hai tờ {' và '.join(worst['pair'])} không khớp nhau: lệch {100 * worst['m']:.1f} cm / "
                                 f"{worst['deg']:.2f}° (cho phép {100 * MAX_SHEET_SPREAD_M:g} cm / "
                                 f"{MAX_SHEET_SPREAD_DEG:g}°) — một tờ đặt sai vạch, hoặc kích thước xe sai")
        if res.rms_px > MAX_RMS_PX:
            raise SheetError(f"RMS chiếu lại {res.rms_px:.2f} px > {MAX_RMS_PX:g} px: tờ không phẳng, ảnh mờ, hoặc nội tham "
                             f"không khớp camera này")
        res.used = True
    except SheetError as exc:
        res.used, res.reason = False, str(exc)
    return res


@dataclass
class SheetResult:
    """Kết quả một cổng; có đủ thuộc tính mà `extrinsics_calib.write_rig_file` dùng."""
    port: int
    ok: bool
    refusals: list
    warnings: list
    images: list
    intrinsics: object | None
    vehicle: dict
    R_cv: np.ndarray | None = None
    t_cv: np.ndarray | None = None
    rms_px: float | None = None
    checks: list = field(default_factory=list)
    created_local: str = ""

    @property
    def used(self) -> list:
        return [r for r in self.images if r.used]

    @property
    def synthetic(self) -> bool:
        return self.intrinsics is not None and getattr(self.intrinsics, "synthetic", False)

    def angles(self) -> dict | None:
        return None if self.R_cv is None else ec.rig_angles(self.R_cv)

    def provenance(self, base_entry: dict | None = None) -> dict:
        intr = self.intrinsics
        prov = {"measured_local": self.created_local, "tool": "autopark.perception.sheet_extrinsics",
                "method": "tờ ChArUco in sẵn (autopark.perception.rig_sheets) đặt chạm lốp; không đo bằng thước",
                "software": {"opencv": cv2.__version__, "numpy": np.__version__},
                "intrinsics": None if intr is None else {"path": intr.path, "image_size": list(intr.size),
                                                        "acceptance_all_pass": intr.acceptance_all_pass,
                                                        "synthetic": intr.synthetic},
                "vehicle": {k: self.vehicle[k] for k in rs.VEHICLE_KEYS} | {"file": self.vehicle.get("_path"),
                                                                            "measured": self.vehicle.get("_measured")},
                "sheet": {"dictionary": rs.DICTIONARY, "square_mm": rs.SQUARE_MM, "marker_mm": rs.MARKER_MM},
                "images": [r.to_dict() for r in self.images], "n_images_used": len(self.used),
                "rms_px": None if self.rms_px is None else round(self.rms_px, 4),
                "checks": self.checks, "warnings": list(self.warnings), "thresholds": THRESHOLDS,
                "frame": "hệ xe: x trước, y trái, z lên; gốc trên mặt sàn dưới tâm trục sau"}
        if base_entry:
            prov["replaced_entry"] = {k: base_entry.get(k) for k in ("direction", "measured", "position_m", "yaw_deg",
                                                                      "pitch_down_deg", "roll_deg", "quaternion_xyzw")
                                      if k in base_entry}
        return prov

    def camera_entry(self, base_entry: dict | None = None) -> dict:
        if not self.ok:
            raise ec.ExtrinsicsError("kết quả không đạt, không ghi: " + "; ".join(self.refusals))
        e = Extrinsics.from_matrix(self.R_cv, self.t_cv)
        ang = self.angles()
        d = self.created_local[:10]
        dd = f"{d[8:10]}/{d[5:7]}/{d[:4]}" if len(d) == 10 else d
        n_corners = sum(r.n_corners for r in self.used)
        entry = {"direction": ec.direction_label(ang["yaw_deg"]), "measured": True,
                 "position_m": [round(float(v), 5) for v in e.translation],
                 "quaternion_xyzw": [round(float(q), 8) for q in e.quaternion_xyzw],
                 "angles_deg_derived": {k: round(v, 3) for k, v in ang.items()},
                 "angles_note": "chỉ để đọc; bev.load_rig_extrinsics dùng quaternion_xyzw (camera → xe)",
                 "basis": (f"ĐO ({dd}) bằng autopark.perception.sheet_extrinsics: {len(self.used)} ảnh, {n_corners} góc "
                           f"ChArUco trên tờ in đặt chạm lốp, RMS chiếu lại {self.rms_px:.3f} px"),
                 "provenance": self.provenance(base_entry)}
        if self.synthetic:
            entry["synthetic"] = True
            entry["basis"] = f"{ec.SYNTHETIC_MARK} — KHÔNG PHẢI SỐ ĐO ({dd}): ảnh dựng qua camera ảo"
        return entry


def solve_port(port: int, images: list, intr, vehicle: dict, *, K=None, D=None, size=None) -> SheetResult:
    """`images`: list[(đường dẫn, ảnh)]. `intr`: CameraIntrinsics (hoặc None khi truyền K, D, size cho phép thử)."""
    K = intr.K if K is None else K
    D = intr.D if D is None else D
    size = tuple(intr.size) if size is None else tuple(size)
    res = SheetResult(port, False, [], [], [], intr, vehicle, created_local=datetime.now().isoformat(timespec="seconds"))
    if not vehicle.get("_measured", True):
        res.warnings.append(f"kích thước xe trong {vehicle.get('_path')} chưa ghi measured = true")
    for path, img in images:
        res.images.append(analyse_image(ImageResult(str(path), img), vehicle, K, D, size))
    used = res.used
    if not used:
        res.refusals.append("không ảnh nào dùng được: " + "; ".join(f"{Path(r.path).name}: {r.reason}"
                                                                     for r in res.images) if res.images
                            else "không có ảnh")
        return res
    best = min(used, key=lambda r: r.rms_px)
    obj = np.vstack([h.vehicle_m for r in used for h in r.hits])
    pix = np.vstack([h.image_px for r in used for h in r.hits])
    R_vc = best.R_cv.T
    rv, tv, err = ec.refine_pose(obj, pix, cv2.Rodrigues(R_vc)[0].ravel(), -R_vc @ best.t_cv, K, D, iterations=100)
    R = cv2.Rodrigues(rv)[0]
    res.R_cv, res.t_cv, res.rms_px = R.T, -R.T @ tv, rms(err)
    for r in used:
        r.deviation_m = float(np.linalg.norm(r.t_cv - res.t_cv))
        r.deviation_deg = ec.rotation_angle_deg(r.R_cv, res.R_cv)
    ang = res.angles()
    x, y, z = (float(v) for v in res.t_cv)
    direction = ec.direction_label(ang["yaw_deg"])
    sheets_seen = sorted({h.key for r in used for h in r.hits})
    checks = [
        ("RMS chiếu lại chung (px)", res.rms_px, res.rms_px <= MAX_RMS_PX, f"<= {MAX_RMS_PX:g}"),
        ("độ cao camera (m)", z, CAMERA_HEIGHT_M[0] <= z <= CAMERA_HEIGHT_M[1],
         f"{CAMERA_HEIGHT_M[0]:g}..{CAMERA_HEIGHT_M[1]:g}"),
        ("x camera (m)", x, CAMERA_BOX_M["x"][0] <= x <= CAMERA_BOX_M["x"][1], "{}..{}".format(*CAMERA_BOX_M["x"])),
        ("y camera (m)", y, CAMERA_BOX_M["y"][0] <= y <= CAMERA_BOX_M["y"][1], "{}..{}".format(*CAMERA_BOX_M["y"])),
        ("hướng nhìn", direction, port not in EXPECTED_DIRECTION or direction == EXPECTED_DIRECTION[port],
         EXPECTED_DIRECTION.get(port, "bất kỳ")),
    ]
    if len(used) >= 2:
        pm, pd = max(r.deviation_m for r in used), max(r.deviation_deg for r in used)
        checks += [("lệch vị trí giữa các ảnh (m)", pm, pm <= MAX_IMAGE_SPREAD_M, f"<= {MAX_IMAGE_SPREAD_M:g}"),
                   ("lệch hướng giữa các ảnh (°)", pd, pd <= MAX_IMAGE_SPREAD_DEG, f"<= {MAX_IMAGE_SPREAD_DEG:g}")]
    if not any(r.sheet_spread for r in used) and len(used) < 2:
        res.warnings.append("chưa có kiểm chéo: chỉ một ảnh và chỉ một tờ đủ góc. Chụp thêm một ảnh sau khi nhấc tờ lên "
                            "đặt lại, hoặc để camera thấy cả tờ bên cạnh")
    res.checks = [{"name": n, "value": round(v, 5) if isinstance(v, float) else v, "ok": bool(ok), "need": need}
                  for n, v, ok, need in checks]
    res.refusals = [f"{c['name']}: {c['value']} (cần {c['need']})" for c in res.checks if not c["ok"]]
    if direction != EXPECTED_DIRECTION.get(port, direction):
        res.refusals.append(f"cổng {port} phải nhìn {EXPECTED_DIRECTION[port]}, kết quả nhìn {direction} (tờ: "
                            f"{', '.join(sheets_seen)}): kiểm cổng hub hay ảnh lưu nhầm thư mục")
    res.ok = not res.refusals
    return res


def summary_text(res: SheetResult) -> str:
    lines = [f"camera cổng {res.port} · {len(res.used)}/{len(res.images)} ảnh dùng được"]
    for r in res.images:
        seen = ", ".join(f"{h.key} {len(h.ids)} góc" for h in r.hits) or "không thấy tờ"
        tail = (f"RMS {r.rms_px:.3f} px" if r.used else f"BỎ: {r.reason}")
        if r.sheet_spread:
            tail += f"; kiểm chéo {r.sheet_spread['pair'][0]}/{r.sheet_spread['pair'][1]}: " \
                    f"{100 * r.sheet_spread['position_m']:.2f} cm, {r.sheet_spread['angle_deg']:.2f}°"
        lines.append(f"  {Path(r.path).name}: {seen}; {tail}")
    if res.R_cv is not None:
        a = res.angles()
        lines.append(f"vị trí camera (hệ xe): x {res.t_cv[0]:+.4f} m, y {res.t_cv[1]:+.4f} m, cao {res.t_cv[2]:.4f} m")
        lines.append(f"yaw {a['yaw_deg']:+.2f}° ({ec.direction_label(a['yaw_deg'])}), chúc xuống {a['pitch_down_deg']:+.2f}°, "
                     f"roll {a['roll_deg']:+.2f}°; RMS chung {res.rms_px:.3f} px")
    for c in res.checks:
        lines.append(f"  {'đạt ' if c['ok'] else 'CHƯA'}  {c['name']}: {c['value']} (cần {c['need']})")
    for w in res.warnings:
        lines.append(f"  lưu ý: {w}")
    lines.append("→ ĐẠT" if res.ok else "→ TỪ CHỐI: " + "; ".join(res.refusals))
    return "\n".join(lines)


def draw_image(r: ImageResult, res: SheetResult, K, D, ego=None) -> np.ndarray:
    out = r.image.copy() if r.image.ndim == 3 else cv2.cvtColor(r.image, cv2.COLOR_GRAY2BGR)
    if res.R_cv is not None:
        out = ec.draw_vehicle_grid(out, res.R_cv, res.t_cv, K, D, step_m=0.05, extent_m=0.6, ego=ego)
    for h in r.hits:
        for p in h.image_px:
            cv2.circle(out, (int(round(p[0])), int(round(p[1]))), 3, (0, 220, 0), 1, cv2.LINE_AA)
        if res.R_cv is not None:
            uv, ok = ec._project_vehicle(h.vehicle_m, res.R_cv, res.t_cv, K, D, (out.shape[1], out.shape[0]))
            for p in uv[ok]:
                c = (int(round(p[0])), int(round(p[1])))
                cv2.drawMarker(out, c, (0, 0, 255), cv2.MARKER_CROSS, 7, 1)
        m = h.image_px.mean(axis=0)
        cv2.putText(out, h.key, (int(m[0]), int(m[1])), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
    return out


def write_report(folder, res: SheetResult, K, D, ego=None) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    report = {"format": FORMAT, "port": res.port, "ok": res.ok, "refusals": res.refusals, "summary": summary_text(res),
              "camera": None if res.R_cv is None else {
                  "position_m": [round(float(v), 5) for v in res.t_cv],
                  "quaternion_xyzw": [round(float(q), 8) for q in Extrinsics.from_matrix(res.R_cv, res.t_cv).quaternion_xyzw],
                  **{k: round(v, 4) for k, v in res.angles().items()}},
              "provenance": res.provenance()}
    atomic_write_json(folder / f"ket_qua_p{res.port}.json", report)
    for r in res.images:
        if r.image is not None and r.hits:
            fc.write_image(folder / f"xem_p{res.port}_{Path(r.path).stem}.jpg", draw_image(r, res, K, D, ego))
    return folder


# ---- dòng lệnh --------------------------------------------------------------------------------------------------------
def images_in(folder: Path) -> list:
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_SUFFIXES and p.is_file())


def _cmd_solve(args) -> int:
    vehicle = load_vehicle(args.vehicle)
    jobs = {}
    if args.dir:
        base = Path(args.dir)
        for port in (args.port or [1, 2, 3, 4]):
            sub = base / f"cam_p{port}"
            if sub.is_dir() and images_in(sub):
                jobs[port] = images_in(sub)
        if not jobs:
            print(f"không thấy ảnh trong {base}\\cam_p1..cam_p4", file=sys.stderr)
            return 2
        report_dir = Path(args.report) if args.report else base / "bao_cao_to"
    else:
        if not args.port or len(args.port) != 1 or not args.images:
            print("dùng --dir, hoặc một --port cùng --images", file=sys.stderr)
            return 2
        jobs[args.port[0]] = [Path(p) for p in args.images]
        report_dir = Path(args.report) if args.report else Path(args.images[0]).parent / "bao_cao_to"
    ego = ec.rig_ego(args.base)
    results = []
    for port, paths in sorted(jobs.items()):
        try:
            intr = ec.load_camera_intrinsics(args.intrinsics or ec.default_intrinsics_path(port), port)
        except ec.ExtrinsicsError as exc:
            print(f"cổng {port}: {exc}", file=sys.stderr)
            continue
        images = [(p, fc.read_image(p)) for p in paths]
        res = solve_port(port, images, intr, vehicle)
        write_report(report_dir, res, intr.K, intr.D, ego)
        print(summary_text(res))
        print()
        results.append(res)
    print(f"báo cáo và ảnh kiểm: {report_dir}")
    good = [r for r in results if r.ok]
    if args.out and good:
        try:
            path = ec.write_rig_file(args.out, good, base_path=args.base, overwrite=args.overwrite)
            print(f"đã ghi cổng {', '.join(str(r.port) for r in good)} vào {path}")
        except ec.ExtrinsicsError as exc:
            print(f"không ghi: {exc}", file=sys.stderr)
            return 2
    elif good and not args.out:
        print("chưa ghi tệp rig: thêm --out configs\\rig\\camera_rig_extrinsics_v1.json "
              "(tệp đã có thì thêm --base cùng tệp đó và --overwrite)")
    return 0 if results and len(good) == len(results) else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ngoại tham camera từ tờ ChArUco in sẵn (không đo bằng thước).")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("solve", help="giải ngoại tham các cổng từ ảnh chụp tờ in")
    s.add_argument("--dir", help="thư mục có cam_p1..cam_p4 (ảnh lưu từ cửa sổ quan sát)")
    s.add_argument("--port", type=int, action="append", help="chỉ giải cổng này (lặp lại được)")
    s.add_argument("--images", nargs="+", help="ảnh của một cổng (cùng --port)")
    s.add_argument("--intrinsics", help="tệp nội tham (mặc định calibration/cam_p<cổng>.json)")
    s.add_argument("--vehicle", default=str(rs.VEHICLE_FILE), help="kích thước xe cho tờ in")
    s.add_argument("--report", help="thư mục báo cáo (mặc định <dir>/bao_cao_to)")
    s.add_argument("--out", help="ghi tệp rig, ví dụ configs/rig/camera_rig_extrinsics_v1.json")
    s.add_argument("--base", default=str(ec.DEFAULT_BASE), help="tệp rig gốc để chép các cổng khác")
    s.add_argument("--overwrite", action="store_true")
    args = p.parse_args(argv)
    try:
        return _cmd_solve(args)
    except SheetError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
