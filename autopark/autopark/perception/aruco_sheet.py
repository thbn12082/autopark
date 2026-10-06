"""Tờ marker ArUco để in, cho tham chiếu trên cao R1 (T4, docs/KICH_BAN_NGHIEM_THU.md mục 3.2–3.3). Thêm 02/10/2026.

    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.aruco_sheet --ids 0-47 --size-mm 100 --out calibration\\bang_in\\aruco
    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.aruco_sheet --ids 48,49 --size-mm 80 --out calibration\\bang_in\\aruco

Ghi `<out>/aruco_<từ điển>_<cỡ>mm_<khổ>_id<mã đầu>-<mã cuối>.pdf` (nhiều trang, mỗi ô của marker là một hình chữ nhật
vector đúng kích thước in, bộ ghi PDF viết tay của `calib_board`), `.json` (định dạng `autopark.aruco_sheet/1`: từ điển,
mã từng trang, vị trí tâm theo mm trên trang, cỡ danh định, vùng trắng, cách đo) và, với `--png`, mỗi trang một `.png`
300 dpi có khối pHYs.

Mỗi ô in gồm: marker; vùng trắng rộng 1,5 ô module quanh marker (bộ dò cần nền trắng); 4 vạch giữa cạnh (8 mm × 0,3 mm)
nằm NGOÀI vùng trắng, sát mép nó, đánh dấu hai đường tâm; dòng chữ không dấu 'ID 17 | 100 mm | DICT_4X4_50 | in 100% |
do tam = giao 2 vach'. Người đo lấy tâm marker là giao của hai đường nối các vạch đối diện, đo bằng thước từ hai cạnh sa
bàn đã kiểm vuông (KICH_BAN mục 3.3), và đo lại cạnh marker bằng thước kẹp sau khi in.

Mặc định (ĐỀ XUẤT – CHỜ CHỐT, người dùng giao quyết định 02/10/2026): `DICT_4X4_50`; mã 0–47 cho mốc sàn, 48 = marker
sau và 49 = marker trước của xe (KICH_BAN mục 3.2); marker sàn 100 mm (để mỗi ô module ≥ 4,5 điểm ảnh, bản thử tổng hợp
bỏ sót marker ở ≈ 3,5 điểm ảnh mỗi ô), marker xe 80 mm. Cần hơn 48 mốc sàn thì dùng `DICT_4X4_100` (giữ nguyên mã 0–49).
Ô in của marker 100 mm rộng 166 mm (vùng trắng 25 mm mỗi bên, vạch 8 mm) nên một trang A4 chỉ chứa MỘT mốc sàn (48 mốc =
48 trang; mỗi mốc dán cả trang xuống sàn, các mốc cách nhau 0,5 m); marker xe 80 mm: hai ô trên một trang A4 ngang. Công
cụ tự chọn hướng giấy chứa nhiều ô nhất (`--orientation auto`) và báo số trang.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import sys

import numpy as np

from .calib_board import (PAPERS_MM, PRINT_MARGIN_MM, PT_PER_MM, mm_to_px, page_size_mm, pdf_document_bytes,
                          png_with_dpi, render_rects_png)
from .paths import PROJECT

FORMAT = "autopark.aruco_sheet/1"
DICTIONARIES = ("DICT_4X4_50", "DICT_4X4_100", "DICT_5X5_100")
DEFAULT_DICTIONARY = "DICT_4X4_50"
CAR_IDS = {48: "sau", 49: "truoc"}           # KICH_BAN mục 3.2; mốc sàn dùng các mã còn lại
FLOOR_SIZE_MM = 100.0
CAR_SIZE_MM = 80.0
QUIET_MODULES = 1.5          # vùng trắng quanh marker, tính theo ô module
TICK_LENGTH_MM = 8.0         # vạch giữa cạnh, ngoài vùng trắng
TICK_WIDTH_MM = 0.3
LABEL_BAND_MM = 7.0          # dải chữ dưới ô
CELL_GAP_MM = 4.0            # khoảng giữa hai ô trên cùng trang
DEFAULT_OUT = PROJECT / "runs" / "bang_in_aruco"
MEASURE_HINT = ("Tâm marker = giao của hai đường nối các vạch đối diện. Đo tọa độ tâm bằng thước từ hai cạnh sa bàn đã "
                "kiểm vuông (KICH_BAN mục 3.3), ghi vào tệp mốc; đo lại cạnh marker bằng thước kẹp sau khi in.")


def get_dictionary(name: str):
    """Từ điển ArUco của OpenCV theo tên trong `DICTIONARIES`; tên khác → ValueError."""
    import cv2

    if name not in DICTIONARIES:
        raise ValueError(f"từ điển {name!r} không hỗ trợ; chọn một trong {', '.join(DICTIONARIES)}")
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


def dictionary_size(name: str) -> int:
    """Số marker của từ điển (DICT_4X4_50 → 50)."""
    return int(get_dictionary(name).bytesList.shape[0])


def marker_bits(name: str, marker_id: int) -> np.ndarray:
    """(n + 2) × (n + 2) ô module của marker, KỂ CẢ viền đen; True = trắng. Hàng 0 là hàng trên khi in."""
    import cv2

    dictionary = get_dictionary(name)
    size = int(dictionary.bytesList.shape[0])
    if not 0 <= int(marker_id) < size:
        raise ValueError(f"mã {marker_id} ngoài từ điển {name} (0..{size - 1})")
    side = int(dictionary.markerSize) + 2
    return cv2.aruco.generateImageMarker(dictionary, int(marker_id), side) > 127


def parse_ids(text: str) -> list[int]:
    """'0-47,48,49' → [0, 1, …, 49] (tăng dần, không trùng). Sai cú pháp hay khoảng ngược → ValueError."""
    ids: set[int] = set()
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        lo, sep, hi = part.partition("-")
        try:
            a = int(lo)
            b = int(hi) if sep else a
        except ValueError as exc:
            raise ValueError(f"mã {part!r} không hiểu: dùng dạng 0-47,48,49") from exc
        if a < 0 or b < a:
            raise ValueError(f"khoảng mã {part!r} sai (cần 0 ≤ đầu ≤ cuối)")
        ids.update(range(a, b + 1))
    if not ids:
        raise ValueError("chưa có mã nào (ví dụ --ids 0-47)")
    return sorted(ids)


def id_label(ids: list[int]) -> str:
    """Tên ngắn của một danh sách mã cho tên tệp: '0-47', '48-49', '3'."""
    return f"{ids[0]}-{ids[-1]}" if len(ids) > 1 else f"{ids[0]}"


# ---- bố cục --------------------------------------------------------------------------------------------------------
def cell_geometry(size_mm: float, dictionary: str = DEFAULT_DICTIONARY) -> dict:
    """Kích thước một ô in (mm): marker, ô module, vùng trắng, vạch, dải chữ."""
    bits = int(get_dictionary(dictionary).markerSize) + 2
    module = size_mm / bits
    quiet = QUIET_MODULES * module
    square = size_mm + 2 * quiet
    return {"bits": bits, "module_mm": module, "quiet_mm": quiet, "square_mm": square,
            "width_mm": square + 2 * TICK_LENGTH_MM, "height_mm": square + 2 * TICK_LENGTH_MM + LABEL_BAND_MM}


def _grid(page_mm, cell) -> tuple[int, int]:
    usable_w = page_mm[0] - 2 * PRINT_MARGIN_MM
    usable_h = page_mm[1] - 2 * PRINT_MARGIN_MM
    cols = int(math.floor((usable_w + CELL_GAP_MM + 1e-9) / (cell["width_mm"] + CELL_GAP_MM)))
    rows = int(math.floor((usable_h + CELL_GAP_MM + 1e-9) / (cell["height_mm"] + CELL_GAP_MM)))
    return max(0, cols), max(0, rows)


def choose_orientation(size_mm: float, paper: str, orientation: str = "auto",
                       dictionary: str = DEFAULT_DICTIONARY) -> tuple[str, tuple[int, int]]:
    """Hướng giấy và lưới (cột, hàng) ô; 'auto' chọn hướng chứa nhiều ô nhất (bằng nhau thì dọc). Không vừa → ValueError."""
    cell = cell_geometry(size_mm, dictionary)
    options = ("portrait", "landscape") if orientation == "auto" else (orientation,)
    best = None
    for name in options:
        cols, rows = _grid(page_size_mm(paper, name), cell)
        if best is None or cols * rows > best[1][0] * best[1][1]:
            best = (name, (cols, rows))
    if best[1][0] * best[1][1] == 0:
        need = f"{cell['width_mm']:.0f} × {cell['height_mm']:.0f} mm"
        raise ValueError(f"marker {size_mm:g} mm không vừa {paper} ({orientation}): một ô in cần {need} (gồm vùng trắng "
                         f"{QUIET_MODULES:g} ô module, vạch {TICK_LENGTH_MM:g} mm và dòng chữ) trong lề máy in "
                         f"{PRINT_MARGIN_MM:g} mm; chọn A3 hoặc cỡ nhỏ hơn")
    return best


def sheet_pages(ids: list[int], size_mm: float, paper: str = "A4", orientation: str = "auto",
                dictionary: str = DEFAULT_DICTIONARY) -> dict:
    """Bố cục các trang: {'orientation', 'page_mm', 'grid', 'cell', 'pages': [[{id, cell_mm, top_left_mm,
    centre_mm}]]}; các ô đặt giữa trang, mm đo từ góc TRÊN-trái."""
    if not (math.isfinite(size_mm) and size_mm > 0):
        raise ValueError("cỡ marker phải dương (mm)")
    limit = dictionary_size(dictionary)
    bad = [i for i in ids if not 0 <= i < limit]
    if bad:
        raise ValueError(f"mã {bad[:5]} ngoài từ điển {dictionary} (0..{limit - 1})")
    name, (cols, rows) = choose_orientation(size_mm, paper, orientation, dictionary)
    page_mm = page_size_mm(paper, name)
    cell = cell_geometry(size_mm, dictionary)
    per_page = cols * rows
    pages = []
    for start in range(0, len(ids), per_page):
        chunk = ids[start:start + per_page]
        used_cols = min(cols, len(chunk))
        used_rows = int(math.ceil(len(chunk) / cols))
        grid_w = used_cols * cell["width_mm"] + (used_cols - 1) * CELL_GAP_MM
        grid_h = used_rows * cell["height_mm"] + (used_rows - 1) * CELL_GAP_MM
        x0, y0 = (page_mm[0] - grid_w) / 2, (page_mm[1] - grid_h) / 2
        page = []
        for k, marker_id in enumerate(chunk):
            r, c = divmod(k, cols)
            cx = x0 + c * (cell["width_mm"] + CELL_GAP_MM)
            cy = y0 + r * (cell["height_mm"] + CELL_GAP_MM)
            top_left = (cx + TICK_LENGTH_MM + cell["quiet_mm"], cy + TICK_LENGTH_MM + cell["quiet_mm"])
            centre = (top_left[0] + size_mm / 2, top_left[1] + size_mm / 2)
            page.append({"id": marker_id, "cell_mm": (cx, cy), "top_left_mm": top_left, "centre_mm": centre})
        pages.append(page)
    return {"orientation": name, "page_mm": page_mm, "grid": (cols, rows), "cell": cell, "pages": pages}


def label_text(marker_id: int, size_mm: float, dictionary: str) -> str:
    role = CAR_IDS.get(marker_id) if dictionary.startswith("DICT_4X4") else None
    return (f"ID {marker_id}" + (f" ({role})" if role else "") + f" | {size_mm:g} mm | {dictionary} | in 100% | "
            f"do tam = giao 2 vach")


def page_content(page: list[dict], size_mm: float, dictionary: str, cell: dict) -> tuple[list, list]:
    """Hình chữ nhật đen (mm) và dòng chữ của một trang: mỗi ô module đen của marker là MỘT hình chữ nhật."""
    rects, texts = [], []
    module = cell["module_mm"]
    for item in page:
        bits = marker_bits(dictionary, item["id"])
        mx, my = item["top_left_mm"]
        for row in range(bits.shape[0]):
            for col in range(bits.shape[1]):
                if not bits[row, col]:
                    rects.append((mx + col * module, my + row * module, module, module))
        cx, cy = item["centre_mm"]
        half, tick, w = cell["square_mm"] / 2, TICK_LENGTH_MM, TICK_WIDTH_MM
        rects += [(cx - w / 2, cy - half - tick, w, tick), (cx - w / 2, cy + half, w, tick),      # trên, dưới
                  (cx - half - tick, cy - w / 2, tick, w), (cx + half, cy - w / 2, tick, w)]      # trái, phải
        text = label_text(item["id"], size_mm, dictionary)
        width_pt = cell["width_mm"] * PT_PER_MM
        size_pt = max(4.0, min(8.0, width_pt / (0.52 * len(text))))
        texts.append((item["cell_mm"][0], cy + half + tick + LABEL_BAND_MM - 2.0, size_pt, text))
    return rects, texts


def sheet_basename(ids: list[int], size_mm: float, dictionary: str, paper: str) -> str:
    return f"aruco_{dictionary}_{size_mm:g}mm_{paper}_id{id_label(ids)}".replace(".", "p")


def write_sheets(out_dir, ids: list[int], size_mm: float, dictionary: str = DEFAULT_DICTIONARY, paper: str = "A4",
                 png: bool = False, dpi: float = 300.0, orientation: str = "auto") -> dict:
    """Ghi PDF (+ PNG mỗi trang khi `png`) và JSON mô tả; trả nội dung JSON."""
    ids = sorted(set(int(i) for i in ids))
    layout = sheet_pages(ids, size_mm, paper, orientation, dictionary)
    cell = layout["cell"]
    contents = [page_content(page, size_mm, dictionary, cell) for page in layout["pages"]]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = sheet_basename(ids, size_mm, dictionary, paper)
    pdf_path = out_dir / f"{name}.pdf"
    pdf_path.write_bytes(pdf_document_bytes([(layout["page_mm"], rects, texts) for rects, texts in contents]))
    png_files = []
    if png:
        for k, (rects, texts) in enumerate(contents, start=1):
            page_png = out_dir / f"{name}_trang{k:02d}.png"
            page_png.write_bytes(png_with_dpi(render_rects_png(layout["page_mm"], rects, texts, dpi), dpi))
            png_files.append(page_png.name)
    meta = {
        "format": FORMAT,
        "dictionary": dictionary,
        "marker_bits": cell["bits"] - 2,
        "size_mm": size_mm,
        "module_mm": round(cell["module_mm"], 4),
        "quiet_zone_modules": QUIET_MODULES,
        "quiet_zone_mm": round(cell["quiet_mm"], 4),
        "tick": {"length_mm": TICK_LENGTH_MM, "width_mm": TICK_WIDTH_MM,
                 "where": "giữa mỗi cạnh, ngoài vùng trắng, sát mép nó: đánh dấu hai đường tâm"},
        "paper": paper, "orientation": layout["orientation"], "page_mm": list(layout["page_mm"]),
        "grid": list(layout["grid"]),
        "ids": ids,
        "pages": [{"page": k, "ids": [item["id"] for item in page],
                   "markers": [{"id": item["id"], "centre_mm": [round(v, 4) for v in item["centre_mm"]],
                                "top_left_mm": [round(v, 4) for v in item["top_left_mm"]]} for item in page]}
                  for k, page in enumerate(layout["pages"], start=1)],
        "pdf": {"file": pdf_path.name, "size_pt": size_mm * PT_PER_MM, "print_scaling_none_hint": True},
        "png": {"files": png_files, "dpi": dpi, "module_px": mm_to_px(cell["module_mm"], dpi)} if png else None,
        "how_to_measure": MEASURE_HINT,
        "roles": {str(k): v for k, v in CAR_IDS.items()} if dictionary.startswith("DICT_4X4") else {},
        "created_local": datetime.now().isoformat(timespec="seconds"),
        "note": ("Kích thước danh định. In 100 % (không co giãn), đo lại cạnh marker bằng thước kẹp. Chữ trên trang không "
                 "dấu vì phông chuẩn PDF không có chữ tiếng Việt. Mặc định ĐỀ XUẤT – CHỜ CHỐT (người dùng giao quyết "
                 "định 02/10/2026)."),
    }
    (out_dir / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"LỖI: {message}", file=sys.stderr)
        raise SystemExit(2)


def main(argv=None) -> int:
    p = _Parser(prog="python -m autopark.perception.aruco_sheet",
                description="In tờ marker ArUco cho tham chiếu trên cao R1 (T4). Mặc định ĐỀ XUẤT – CHỜ CHỐT.")
    p.add_argument("--ids", required=True, help="mã cần in, ví dụ 0-47 (mốc sàn) hoặc 48,49 (xe: sau, trước)")
    p.add_argument("--size-mm", type=float, default=FLOOR_SIZE_MM,
                   help=f"cạnh marker (mm, gồm viền đen); mặc định {FLOOR_SIZE_MM:g} (mốc sàn), xe {CAR_SIZE_MM:g}")
    p.add_argument("--dictionary", default=DEFAULT_DICTIONARY, help=f"một trong {', '.join(DICTIONARIES)}")
    p.add_argument("--paper", choices=sorted(PAPERS_MM), default="A4")
    p.add_argument("--orientation", choices=("auto", "portrait", "landscape"), default="auto")
    p.add_argument("--png", action="store_true", help="ghi thêm mỗi trang một PNG (có DPI) để xem/kiểm")
    p.add_argument("--dpi", type=float, default=300.0)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="thư mục ghi (mặc định runs/bang_in_aruco)")
    try:
        args = p.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        ids = parse_ids(args.ids)
        meta = write_sheets(args.out, ids, args.size_mm, args.dictionary, args.paper, args.png, args.dpi,
                            args.orientation)
    except ValueError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    print(f"đã ghi {Path(args.out) / meta['pdf']['file']} ({len(meta['pages'])} trang {args.paper} "
          f"{meta['orientation']}) và .json" + (", .png" if args.png else ""))
    print(f"{len(ids)} marker {args.dictionary}, cạnh {args.size_mm:g} mm. IN 100 % (không co giãn); {MEASURE_HINT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
