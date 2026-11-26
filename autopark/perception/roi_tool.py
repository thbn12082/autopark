"""Mặt nạ ROI cho camera của dự án: người dùng vẽ đa giác trên ảnh của từng camera (thân xe, dây, viền ống kính…).

    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.ui.roi_app --port 1 --snapshot runs/rig_snapshots/<ngày_giờ>
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.roi_tool check configs/roi/rig_v1/roi_p1.png --image runs/rig_snapshots/<ngày_giờ>/cam_p1.png
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.roi_tool build configs/roi/rig_v1/roi_p1.json

Mỗi lệnh viết trên MỘT dòng (dán được vào cmd.exe). Hướng dẫn: docs/PHAN_CUNG_VA_HIEU_CHUAN.md#ngoai-tham.

**Định dạng (đúng thứ BEV đọc, xem perception/bev.py::load_rig):** `<thư mục>/roi_p<cổng>.png`, ảnh xám 8 bit ở CỠ GỐC của
khung camera (cỡ đã hiệu chuẩn nội tham, mặc định 640×480), 255 = pixel dùng được, 0 = loại. Cùng quy ước với
configs/roi/woodscape_v1 (perception/roi.py). BEV nhận thư mục qua `--roi-dir`; thư mục đề xuất `configs/roi/rig_v1`.
Cạnh PNG có `roi_p<cổng>.json` (các đa giác, cỡ ảnh, ảnh nguồn, ngày) để sửa lại sau, và `roi_p<cổng>_xem.jpg` (ảnh
xem trước: vùng loại tô đỏ).

**Quy tắc dựng:** không có đa giác "giữ" (include) nào thì mọi pixel dùng được trừ các đa giác "loại" (exclude); có đa giác
"giữ" thì chỉ phần trong chúng dùng được, trừ các đa giác "loại" (loại luôn thắng). Vùng giữ / vùng loại là HỢP các đa
giác cùng kiểu: mỗi đa giác tô riêng bằng `cv2.fillPoly` (một lần tô nhiều đa giác theo quy tắc chẵn-lẻ sẽ đục lỗ chỗ
chúng chồng nhau). Pixel nằm trên biên đa giác cũng bị tô: đa giác loại thì nghiêng về loại nhiều hơn. Một đa giác TỰ
CẮT vẫn tô theo chẵn-lẻ của OpenCV (vẽ đa giác không tự cắt). Sau đó nới vùng loại thêm `margin_px` điểm ảnh
(mặc định 2, ĐỀ XUẤT – CHỜ CHỐT): pixel sát mép thân xe trộn màu thân xe với sàn, AI đọc sai ở đó — lỗi đã thấy với ROI
WoodScape `roi_MVL.png` (docs/KIEN_TRUC.md).

Không bao giờ ghi đè im lặng: `roi_p<cổng>.png` đã có thì từ chối, trừ khi `overwrite` (bản cũ được đổi tên thành
`roi_p<cổng>.bak_<ngày_giờ_micro giây>[_NNN].png/.json`, tên được giữ chỗ độc quyền nên hai lần lưu trong cùng một giây
không đè bản sao lưu của nhau). Sau khi ghi, đọc lại bằng `bev.read_gray` và so từng pixel.

**Tình trạng 24/09/2026:** chưa có ROI nào cho camera dự án (chưa gá camera lên xe, xe MN300 chưa về); công cụ chỉ kiểm
trên ảnh tổng hợp (tests/test_roi_tool.py).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import sys

import cv2
import numpy as np

from .paths import PROJECT, atomic_write_json

ROI_FORMAT = "autopark.roi_polygons/1"
DEFAULT_ROI_DIR = PROJECT / "configs/roi/rig_v1"
DEFAULT_MARGIN_PX = 2                  # ĐỀ XUẤT – CHỜ CHỐT
MODES = ("exclude", "include")
MIN_USABLE_FRACTION = 0.2              # dưới mức này: cảnh báo (ĐỀ XUẤT)


class RoiError(RuntimeError):
    """Đầu vào/đầu ra ROI không dùng được; thông báo tiếng Việt."""


@dataclass
class RoiPolygon:
    points: list                       # [(x, y)] toạ độ điểm ảnh (tâm pixel ở số nguyên)
    mode: str = "exclude"
    label: str = ""

    def __post_init__(self):
        if self.mode not in MODES:
            raise RoiError(f"kiểu đa giác {self.mode!r} không hợp lệ (exclude = loại, include = giữ)")
        self.points = [(float(x), float(y)) for x, y in self.points]

    def to_dict(self) -> dict:
        return {"mode": self.mode, "label": self.label, "points": [[round(x, 2), round(y, 2)] for x, y in self.points]}

    @classmethod
    def from_dict(cls, data: dict) -> "RoiPolygon":
        try:
            return cls([(float(p[0]), float(p[1])) for p in data["points"]], str(data.get("mode", "exclude")),
                       str(data.get("label", "")))
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise RoiError(f"đa giác sai định dạng: {exc}") from exc


@dataclass
class RoiSpec:
    port: int
    width: int
    height: int
    polygons: list = field(default_factory=list)
    margin_px: int = DEFAULT_MARGIN_PX
    source_image: str | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return {"format": ROI_FORMAT, "port": int(self.port), "image_size": [int(self.width), int(self.height)],
                "margin_px": int(self.margin_px), "source_image": self.source_image, "note": self.note,
                "rule": "không có đa giác include: mọi pixel dùng được trừ đa giác exclude; có include: chỉ phần trong "
                        "include, trừ exclude; rồi nới vùng loại margin_px điểm ảnh. PNG: 255 = dùng được, 0 = loại",
                "polygons": [p.to_dict() for p in self.polygons]}

    @classmethod
    def from_dict(cls, data: dict) -> "RoiSpec":
        if not isinstance(data, dict) or data.get("format") != ROI_FORMAT:
            raise RoiError(f"không phải tệp {ROI_FORMAT}")
        try:
            w, h = (int(v) for v in data["image_size"])
            spec = cls(int(data["port"]), w, h, [RoiPolygon.from_dict(p) for p in data.get("polygons") or []],
                       int(data.get("margin_px", DEFAULT_MARGIN_PX)), data.get("source_image"), str(data.get("note", "")))
        except (KeyError, TypeError, ValueError) as exc:
            raise RoiError(f"tệp ROI sai định dạng: {exc}") from exc
        spec.validate()
        return spec

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise RoiError("cỡ ảnh phải dương")
        if self.margin_px < 0 or self.margin_px > 50:
            raise RoiError(f"margin_px = {self.margin_px} vô lý (0..50)")
        for k, p in enumerate(self.polygons):
            if len(p.points) < 3:
                raise RoiError(f"đa giác {k + 1} có {len(p.points)} đỉnh, cần ít nhất 3")
            pts = np.asarray(p.points)
            if not np.all(np.isfinite(pts)):
                raise RoiError(f"đa giác {k + 1} có toạ độ không hữu hạn")


def rasterize(spec: RoiSpec) -> np.ndarray:
    """Đa giác → mặt nạ uint8 (cao, rộng): 255 dùng được, 0 loại (quy tắc ở docstring mô-đun)."""
    spec.validate()
    h, w = spec.height, spec.width
    includes = [p for p in spec.polygons if p.mode == "include"]
    excludes = [p for p in spec.polygons if p.mode == "exclude"]
    mask = np.zeros((h, w), np.uint8) if includes else np.full((h, w), 255, np.uint8)
    shift = 4

    def fixed(p: RoiPolygon) -> np.ndarray:
        return np.round(np.asarray(p.points, np.float64) * (1 << shift)).astype(np.int32).reshape(-1, 1, 2)

    # Tô TỪNG đa giác một: một lần fillPoly với nhiều đa giác dùng quy tắc chẵn-lẻ, nên chỗ hai đa giác cùng kiểu chồng
    # nhau (ví dụ đa giác "bánh xe" nằm trong đa giác "thân xe") bị đục lỗ — vùng loại thành dùng được
    for p in includes:
        cv2.fillPoly(mask, [fixed(p)], 255, cv2.LINE_8, shift)
    for p in excludes:
        cv2.fillPoly(mask, [fixed(p)], 0, cv2.LINE_8, shift)
    if spec.margin_px > 0:
        k = 2 * int(spec.margin_px) + 1
        excluded = cv2.dilate((mask == 0).astype(np.uint8), np.ones((k, k), np.uint8))
        mask[excluded > 0] = 0
    return mask


def overlay(image: np.ndarray, mask: np.ndarray, alpha: float = 0.45, polygons: list | None = None) -> np.ndarray:
    """Ảnh xem trước: vùng loại tô đỏ, biên vùng dùng được viền vàng; đa giác (nếu có) vẽ nét mảnh."""
    img = image if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if img.shape[:2] != mask.shape:
        raise RoiError(f"ảnh {img.shape[1]}×{img.shape[0]} khác cỡ mặt nạ {mask.shape[1]}×{mask.shape[0]}")
    out = img.copy()
    red = np.zeros_like(out)
    red[:] = (0, 0, 230)
    excluded = mask == 0
    out[excluded] = cv2.addWeighted(img, 1.0 - alpha, red, alpha, 0.0)[excluded]
    contours, _ = cv2.findContours((mask > 0).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, contours, -1, (0, 230, 255), 1, cv2.LINE_AA)
    for p in polygons or []:
        pts = np.round(np.asarray(p.points)).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [pts], True, (255, 80, 80) if p.mode == "include" else (40, 40, 255), 1, cv2.LINE_AA)
    return out


# ---- đọc/ghi --------------------------------------------------------------------------------------------------------
def roi_paths(folder, port: int) -> dict:
    folder = Path(folder)
    return {"png": folder / f"roi_p{int(port)}.png", "json": folder / f"roi_p{int(port)}.json",
            "preview": folder / f"roi_p{int(port)}_xem.jpg"}


def _encode(path: Path, image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(path.suffix, image)       # imwrite hỏng với đường dẫn tiếng Việt trên Windows
    if not ok:
        raise RoiError(f"không mã hóa được {path}")
    return buf.tobytes()


def read_mask(path) -> np.ndarray:
    try:
        data = np.fromfile(str(path), np.uint8)
    except OSError as exc:
        raise RoiError(f"không đọc được {path}: {exc}") from exc
    mask = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise RoiError(f"không giải mã được {path}")
    return mask


def read_image(path) -> np.ndarray:
    try:
        image = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    except OSError as exc:
        raise RoiError(f"không đọc được {path}: {exc}") from exc
    if image is None:
        raise RoiError(f"không giải mã được ảnh {path}")
    return image


def load_spec(path) -> RoiSpec:
    try:
        return RoiSpec.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise RoiError(f"không đọc được {path}: {exc}") from exc


def _reserve_backup_group(sources: list) -> list:
    """Giữ chỗ (tạo rỗng độc quyền, mở "xb") cùng một hậu tố .bak_<ngày_giờ_micro giây>[_NNN] CHƯA có cho cả nhóm
    png/json/xem. Hai lần lưu đè liền nhau (bấm đúp 'Lưu ROI') không bao giờ dùng chung tên sao lưu."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    for n in range(1000):
        suffix = stamp + (f"_{n:03d}" if n else "")
        made = []
        try:
            for src in sources:
                target = src.with_name(f"{src.stem}.bak_{suffix}{src.suffix}")
                with open(target, "xb"):
                    pass
                made.append(target)
            return made
        except FileExistsError:
            for target in made:
                target.unlink()
    raise RoiError(f"không tìm được tên sao lưu còn trống cho {sources[0] if sources else '?'}")


def save_roi(spec: RoiSpec, folder=DEFAULT_ROI_DIR, *, image: np.ndarray | None = None, overwrite: bool = False) -> dict:
    """Ghi roi_p<cổng>.png (+ .json, + _xem.jpg nếu có ảnh). Từ chối ghi đè nếu không có `overwrite`; có thì bản cũ đổi
    tên thành roi_p<cổng>.bak_<ngày_giờ_micro giây>[_NNN].* (tên chưa có, không bao giờ đè một bản sao lưu khác). Đọc
    lại PNG bằng bev.read_gray và so từng pixel."""
    from .bev import read_gray

    mask = rasterize(spec)
    if not (mask > 0).any():
        raise RoiError("mặt nạ loại HẾT mọi pixel: camera sẽ không góp gì vào BEV — kiểm lại đa giác")
    if image is not None and image.shape[:2] != (spec.height, spec.width):
        raise RoiError(f"ảnh {image.shape[1]}×{image.shape[0]} khác cỡ ROI {spec.width}×{spec.height}")
    paths = roi_paths(folder, spec.port)
    Path(folder).mkdir(parents=True, exist_ok=True)
    backups = []
    if paths["png"].exists() or paths["json"].exists():
        if not overwrite:
            raise RoiError(f"{paths['png']} đã có: không ghi đè im lặng — bật 'cho phép ghi đè' (bản cũ được giữ lại "
                           f"với hậu tố .bak_<ngày_giờ>)")
        present = [key for key in ("png", "json", "preview") if paths[key].exists()]
        targets = _reserve_backup_group([paths[key] for key in present])
        for key, target in zip(present, targets):
            os.replace(paths[key], target)       # đè lên tệp rỗng vừa giữ chỗ (của chính mình), không đè bản khác
            backups.append(str(target))
    record = spec.to_dict()
    record.update({"created_local": datetime.now().isoformat(timespec="seconds"), "tool": "autopark.perception.roi_tool",
                   "usable_fraction": round(float((mask > 0).mean()), 5), "png": paths["png"].name,
                   "backups": backups})
    paths["png"].write_bytes(_encode(paths["png"], mask))
    atomic_write_json(paths["json"], record)
    if image is not None:
        paths["preview"].write_bytes(_encode(paths["preview"], overlay(image, mask, polygons=spec.polygons)))
    back = read_gray(paths["png"])
    if back.shape != mask.shape or not np.array_equal(back, mask):
        raise RoiError(f"đọc lại {paths['png']} không trùng mặt nạ vừa ghi")
    return {"png": paths["png"], "json": paths["json"], "preview": paths["preview"] if image is not None else None,
            "backups": backups, "usable_fraction": record["usable_fraction"]}


# ---- kiểm một mặt nạ ---------------------------------------------------------------------------------------------------
def check_mask(mask: np.ndarray, expected_size: tuple | None = None) -> dict:
    """Kiểm một mặt nạ như BEV sẽ đọc. Trả {"errors": [...], "warnings": [...], số liệu}."""
    errors, warnings = [], []
    if mask.ndim != 2:
        errors.append(f"mặt nạ có {mask.shape[2] if mask.ndim == 3 else '?'} kênh: cần ảnh xám một kênh (BEV đọc bằng "
                      f"IMREAD_GRAYSCALE nên ảnh màu bị đổi sang xám, dễ sai)")
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY) if mask.ndim == 3 and mask.shape[2] == 3 else mask[..., 0]
    if mask.dtype != np.uint8:
        errors.append(f"kiểu {mask.dtype}, cần uint8")
    h, w = mask.shape
    if expected_size is not None and (w, h) != tuple(expected_size):
        errors.append(f"cỡ {w}×{h} khác cỡ khung camera {expected_size[0]}×{expected_size[1]}: BEV từ chối camera này")
    values = np.unique(mask)
    odd = [int(v) for v in values if v not in (0, 255)]
    if odd:
        warnings.append(f"có {len(odd)} giá trị khác 0/255 (ví dụ {odd[:5]}): BEV coi mọi giá trị > 0 là DÙNG ĐƯỢC")
    usable = mask > 0
    frac = float(usable.mean())
    if frac == 0.0:
        errors.append("loại hết mọi pixel: camera không góp gì vào BEV")
    elif frac == 1.0:
        warnings.append("không loại pixel nào: thân xe/dây/viền ống kính chưa được loại?")
    elif frac < MIN_USABLE_FRACTION:
        warnings.append(f"chỉ {100 * frac:.1f} % pixel dùng được (< {100 * MIN_USABLE_FRACTION:g} %)")
    n, _ = cv2.connectedComponents(usable.astype(np.uint8), connectivity=8)
    components = int(n - 1)
    if components > 1:
        warnings.append(f"vùng dùng được bị chia thành {components} mảnh rời: có mảnh nhỏ sót lại không?")
    return {"size": [int(w), int(h)], "usable_fraction": round(frac, 5), "excluded_fraction": round(1.0 - frac, 5),
            "usable_components": components, "values": [int(v) for v in values[:10]],
            "errors": errors, "warnings": warnings, "ok": not errors}


def _expected_size(args) -> tuple | None:
    if args.size:
        w, h = args.size.lower().replace("×", "x").split("x")
        return int(w), int(h)
    if args.intrinsics:
        from .fisheye_calib import load_calibration

        try:
            return tuple(int(v) for v in load_calibration(args.intrinsics)["image_size"])
        except (OSError, ValueError, KeyError) as exc:
            raise RoiError(f"không đọc được cỡ ảnh từ {args.intrinsics}: {exc}") from exc
    return None


def _cmd_check(args) -> int:
    mask = read_mask(args.mask)
    expected = _expected_size(args)
    image = None
    if args.image:
        image = read_image(args.image)
        if expected is None:
            expected = (image.shape[1], image.shape[0])
    report = check_mask(mask, expected)
    print(f"{args.mask}: {report['size'][0]}×{report['size'][1]}, dùng được {100 * report['usable_fraction']:.1f} %, "
          f"{report['usable_components']} mảnh")
    for e in report["errors"]:
        print(f"  LỖI: {e}")
    for w in report["warnings"]:
        print(f"  CẢNH BÁO: {w}")
    if image is not None and not report["errors"]:
        out = Path(args.preview) if args.preview else Path(args.mask).with_name(Path(args.mask).stem + "_kiem.jpg")
        gray = mask if mask.ndim == 2 else cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
        out.write_bytes(_encode(out, overlay(image, gray)))
        print(f"  ảnh xem trước (vùng loại tô đỏ) -> {out}")
    print("→ " + ("dùng được với bev --roi-dir" if report["ok"] else "KHÔNG dùng được"))
    return 0 if report["ok"] else 2


def _cmd_build(args) -> int:
    spec = load_spec(args.spec)
    image = read_image(args.image) if args.image else None
    out_dir = args.out_dir or Path(args.spec).parent
    # dựng lại vào chính thư mục của tệp đa giác: roi_p<cổng>.png/.json đã có nên save_roi đòi --overwrite
    result = save_roi(spec, out_dir, image=image, overwrite=args.overwrite)
    print(f"đã ghi {result['png']} (dùng được {100 * result['usable_fraction']:.1f} %)"
          + (f"; bản cũ: {', '.join(result['backups'])}" if result["backups"] else ""))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Mặt nạ ROI cho camera dự án (docs/PHAN_CUNG_VA_HIEU_CHUAN.md#ngoai-tham)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="kiểm một roi_p<cổng>.png như BEV sẽ đọc; --image để ghi ảnh xem trước")
    c.add_argument("mask", type=Path)
    c.add_argument("--image", type=Path, help="ảnh của camera đó (ví dụ cam_p1.png của một bộ ảnh)")
    c.add_argument("--size", help="cỡ khung mong đợi, ví dụ 640x480")
    c.add_argument("--intrinsics", type=Path, help="lấy cỡ khung từ tệp nội tham calibration/cam_p<cổng>.json")
    c.add_argument("--preview", type=Path, help="tệp ảnh xem trước (mặc định <mặt nạ>_kiem.jpg)")
    b = sub.add_parser("build", help="dựng lại roi_p<cổng>.png từ tệp đa giác roi_p<cổng>.json")
    b.add_argument("spec", type=Path)
    b.add_argument("--image", type=Path, help="ảnh để ghi ảnh xem trước")
    b.add_argument("--out-dir", type=Path)
    b.add_argument("--overwrite", action="store_true")
    args = p.parse_args(argv)
    try:
        return _cmd_check(args) if args.cmd == "check" else _cmd_build(args)
    except RoiError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
