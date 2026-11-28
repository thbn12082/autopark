"""Bốn tờ A4 hiệu chuẩn ngoại tham (trước, sau, trái, phải): bảng ChArUco + vạch căn theo bánh xe. Thêm 24/11/2026.

    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.rig_sheets --out calibration\\bang_in\\to_ngoai_tham

Thay cách đặt bảng rồi đo tọa độ góc O bằng thước. Mỗi tờ có một bảng ChArUco 6×4 ô 40 mm (marker 30 mm,
DICT_4X4_50). Mỗi tờ dùng một dải mã riêng: trước 0–11, sau 12–23, trái 24–35, phải 36–47. Vì vậy bộ dò biết góc nào
thuộc tờ nào và nằm ở đâu, không cần quy ước góc O, và camera nhìn thấy hai tờ cùng lúc cũng không nhầm.

Cách đặt (in trên từng tờ): mép DƯỚI của tờ là mép phía xe.
- Tờ trước / sau: đẩy mép dưới chạm mặt trước (sau) của HAI lốp trước (sau), bánh lái để thẳng. Xê dịch ngang tới khi
  mặt ngoài hai lốp đọc cùng một số trên hai thang đối xứng → tờ nằm giữa xe.
- Tờ trái / phải: đẩy mép dưới chạm mặt ngoài của lốp trước VÀ lốp sau. Xê dịch dọc tới khi mép trước và mép sau của
  lốp sau đọc cùng một số trên thang quanh vạch TRỤC SAU → vạch nằm đúng tâm trục sau. Thang quanh TRỤC TRƯỚC để kiểm.

Không đọc số nào để nhập. Hệ xe chỉ cần ba kích thước đo một lần (`VEHICLE_KEYS`): chiều dài cơ sở, bán kính lốp và bề
rộng ngoài hai lốp. Tọa độ hệ xe của từng góc ChArUco = `anchor(kích thước) + (u − u_ref)·e_u + (H − v)·e_up`, trong đó
(u, v) là mm trên tờ đo từ góc TRÊN-trái như lúc in và H = 210 mm.

Tờ ghi bằng bộ ghi PDF vector của `calib_board` (in 100 %, không co giãn). Kèm PNG 300 dpi từng trang và JSON
`autopark.rig_sheets/1`. `--check` vẽ lại PNG rồi dò bằng `cv2.aruco.CharucoDetector`, kể cả bản thu nhỏ còn khoảng
3 điểm ảnh mỗi ô module, và báo nếu thiếu góc hoặc lệch vị trí.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

import numpy as np

from .aruco_sheet import get_dictionary, marker_bits
from .calib_board import png_with_dpi, pdf_document_bytes, render_rects_png
from .paths import PROJECT

FORMAT = "autopark.rig_sheets/1"
DICTIONARY = "DICT_4X4_50"
PAGE_MM = (297.0, 210.0)           # A4 ngang (rộng, cao)
SQUARES = (6, 4)                   # ô ChArUco (cột, hàng) → 5×3 = 15 góc trong
SQUARE_MM = 40.0
MARKER_MM = 30.0
BOARD_TOP_MM = 17.0
EDGE_TICK_END_MM = 204.0           # đầu vạch thang, cách mép xe 6 mm (lề máy in)
LINE_MM = 0.3
DEFAULT_OUT = PROJECT / "calibration" / "bang_in" / "to_ngoai_tham"
VEHICLE_FILE = PROJECT / "configs" / "rig" / "to_ngoai_tham_xe.json"

# Kích thước xe cần cho phép biến đổi tờ → hệ xe. Số đo ngày 23/11/2026 (do-kich-thuoc-xe.html): cơ sở 210 mm, bề rộng
# lớn nhất 160 mm; người dùng đo 24/11/2026: lốp Ø 74 mm, bề rộng ngoài hai lốp 160 mm. Số nằm ở tệp
# `VEHICLE_FILE`, không in lên giấy, nên sửa số không phải in lại.
VEHICLE_KEYS = ("wheelbase_m", "tire_radius_m", "tire_outer_width_m")

# u_ref: vị trí (mm, theo u) của điểm neo trên tờ. e_u, e_up: hướng trong hệ xe (x trước, y trái) của +u và của "lên
# trang" (rời xa xe). anchor: điểm neo trong hệ xe theo kích thước xe.
SHEETS = (
    {"key": "front", "title": "TO 1 - TRUOC (camera 1)", "first_id": 0, "u_ref": 148.5,
     "e_u": (0.0, -1.0), "e_up": (1.0, 0.0), "anchor": "front_edge", "scales": "lateral"},
    {"key": "rear", "title": "TO 2 - SAU (camera 2)", "first_id": 12, "u_ref": 148.5,
     "e_u": (0.0, 1.0), "e_up": (-1.0, 0.0), "anchor": "rear_edge", "scales": "lateral"},
    {"key": "left", "title": "TO 3 - TRAI (camera 3)", "first_id": 24, "u_ref": 44.0,
     "e_u": (1.0, 0.0), "e_up": (0.0, 1.0), "anchor": "left_edge", "scales": "axles"},
    {"key": "right", "title": "TO 4 - PHAI (camera 4)", "first_id": 36, "u_ref": 253.0,
     "e_u": (-1.0, 0.0), "e_up": (0.0, -1.0), "anchor": "right_edge", "scales": "axles"},
)


def anchor_xy(anchor: str, vehicle: dict) -> tuple[float, float]:
    """Điểm neo (m, hệ xe) của mép tờ. Tờ trái/phải: neo = tâm trục sau chiếu ra mép (vạch TRỤC SAU, u = u_ref)."""
    L, r, w = (float(vehicle[k]) for k in VEHICLE_KEYS)
    gap = spacer_m(anchor, vehicle)
    return {"front_edge": (L + r + gap, 0.0), "rear_edge": (-r - gap, 0.0),
            "left_edge": (0.0, w / 2 + gap), "right_edge": (0.0, -w / 2 - gap)}[anchor]


def spacer_m(anchor: str, vehicle: dict) -> float:
    """Khoảng kê (m) giữa lốp và mép dưới tờ, đẩy tờ ra xa xe (28/11/2026).

    Camera xe cao ≈ 7 cm nên tờ trước/sau chạm lốp nằm gần như ngay dưới camera, không camera nào thấy đủ góc. Kê một tờ
    A4 trắng gấp đôi theo chiều dài (rộng 105 mm) giữa lốp và tờ ChArUco: `spacer_m` = {"rear": 0.105, ...} trong
    `to_ngoai_tham_xe.json`. Không có khóa nào thì là 0 (tờ chạm lốp như cũ)."""
    return float((vehicle.get("spacer_m") or {}).get(anchor.removesuffix("_edge"), 0.0))


def board_origin_mm() -> tuple[float, float]:
    return ((PAGE_MM[0] - SQUARES[0] * SQUARE_MM) / 2, BOARD_TOP_MM)


def make_board(first_id: int):
    import cv2

    ids = np.arange(first_id, first_id + SQUARES[0] * SQUARES[1] // 2, dtype=np.int32)
    return cv2.aruco.CharucoBoard(SQUARES, SQUARE_MM, MARKER_MM, get_dictionary(DICTIONARY), ids)


def corners_sheet_mm(board) -> np.ndarray:
    """(N, 2) góc trong ChArUco theo mm trên tờ, theo thứ tự id góc của OpenCV."""
    return np.asarray(board.getChessboardCorners(), np.float64)[:, :2] + board_origin_mm()


def corners_vehicle_m(sheet: dict, board, vehicle: dict) -> np.ndarray:
    uv = corners_sheet_mm(board)
    ax, ay = anchor_xy(sheet["anchor"], vehicle)
    eu, eup = np.array(sheet["e_u"]), np.array(sheet["e_up"])
    return np.array([ax, ay]) + ((uv[:, :1] - sheet["u_ref"]) * eu + (PAGE_MM[1] - uv[:, 1:]) * eup) / 1000.0


def board_rects(board) -> list[tuple[float, float, float, float]]:
    """Ô đen và các ô module đen của marker (mm trên tờ). Ô đen = ô không chứa marker; marker in thẳng chiều."""
    ox, oy = board_origin_mm()
    obj = [np.asarray(p, np.float64)[:, :2] for p in board.getObjPoints()]
    centers = [p.mean(axis=0) for p in obj]
    marker_cells = {(int(c[0] // SQUARE_MM), int(c[1] // SQUARE_MM)) for c in centers}
    rects = [(ox + i * SQUARE_MM, oy + j * SQUARE_MM, SQUARE_MM, SQUARE_MM)
             for j in range(SQUARES[1]) for i in range(SQUARES[0]) if (i, j) not in marker_cells]
    for marker_id, pts in zip(board.getIds().ravel(), obj):
        bits = marker_bits(DICTIONARY, int(marker_id))
        n = bits.shape[0]
        m = MARKER_MM / n
        x0, y0 = pts[0]                                    # góc TRÊN-trái của marker
        for r in range(n):
            for c in range(n):
                if not bits[r, c]:
                    rects.append((ox + x0 + c * m, oy + y0 + r * m, m, m))
    return rects


def _hline(x0, x1, y):
    return (min(x0, x1), y - LINE_MM / 2, abs(x1 - x0), LINE_MM)


def _vline(x, y0, y1):
    return (x - LINE_MM / 2, min(y0, y1), LINE_MM, abs(y1 - y0))


def scale_marks(center_u: float, lo: int, hi: int, label: str, rects: list, texts: list) -> None:
    """Thang đối xứng quanh `center_u`: vạch mỗi 1 mm từ lo tới hi mm ở hai bên, số là khoảng cách tới tâm (mm)."""
    base = EDGE_TICK_END_MM
    for side in (-1, 1):
        for d in range(lo, hi + 1):
            u = center_u + side * d
            if not 6.0 <= u <= PAGE_MM[0] - 6.0:       # lề máy in 6 mm; lốp Ø74 cần ±37 mm
                continue
            length = 6.0 if d % 10 == 0 else 4.0 if d % 5 == 0 else 2.5
            rects.append(_vline(u, base - length, base))
            if d % 10 == 0 and d:
                texts.append((u - 2.2, base - 7.5, 6.5, str(d)))
    rects.append((center_u - 0.4, base - 10.0, 0.8, 10.0))
    texts.append((center_u - 1.8 * len(label) / 2 * 1.1, base - 12.5, 7.5, label))


def page_content(sheet: dict, board) -> tuple[list, list]:
    rects = board_rects(board)
    texts = [(8.0, 11.0, 13.0, sheet["title"]),
             (8.0, 15.5, 7.0, f"ChArUco 6x4 o 40 mm, marker 30 mm, {DICTIONARY}, ma {sheet['first_id']}-"
                              f"{sheet['first_id'] + 11}. In 100%, KHONG co gian. Dan phang xuong san.")]
    # thước kiểm tỉ lệ in 100 mm
    x0 = PAGE_MM[0] - 8.0 - 100.0
    rects += [_hline(x0, x0 + 100.0, 8.0), _vline(x0, 5.5, 10.5), _vline(x0 + 100.0, 5.5, 10.5)]
    texts.append((x0 + 18.0, 13.5, 6.5, "kiem tra: vach nay dai dung 100 mm"))
    if sheet["scales"] == "lateral":
        scale_marks(sheet["u_ref"], 40, 110, "TAM", rects, texts)
        texts.append((8.0, 182.5, 7.0, "MEP DUOI = PHIA XE. Day mep duoi cham mat lop cua HAI banh (banh lai de thang). "
                                       "Xe dich ngang toi khi mat ngoai hai lop doc CUNG MOT SO o hai thang."))
    else:
        # khoảng in giữa hai vạch trục = 210 mm (cơ sở đo 23/11/2026); vạch TRỤC TRƯỚC chỉ để kiểm, không vào phép tính
        rear_u = sheet["u_ref"]
        front_u = rear_u + 210.0 * sheet["e_u"][0]
        scale_marks(rear_u, 0, 40, "TRUC SAU", rects, texts)
        scale_marks(front_u, 0, 40, "TRUC TRUOC (kiem)", rects, texts)
        texts.append((8.0, 182.5, 7.0, "MEP DUOI = PHIA XE. Day mep duoi cham mat ngoai lop truoc VA lop sau. "
                                       "Xe dich doc toi khi mep truoc va mep sau lop SAU doc CUNG MOT SO."))
    return rects, texts


def sheet_json(sheet: dict, board) -> dict:
    return {"key": sheet["key"], "title": sheet["title"], "ids": [int(i) for i in board.getIds().ravel()],
            "u_ref_mm": sheet["u_ref"], "e_u": list(sheet["e_u"]), "e_up": list(sheet["e_up"]),
            "anchor": sheet["anchor"],
            "corners_sheet_mm": [[round(float(a), 4) for a in p] for p in corners_sheet_mm(board)]}


def write_sheets(out_dir, dpi: float = 300.0) -> dict:
    import cv2

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pages, info = [], []
    for sheet in SHEETS:
        board = make_board(sheet["first_id"])
        rects, texts = page_content(sheet, board)
        pages.append((PAGE_MM, rects, texts))
        png = render_rects_png(PAGE_MM, rects, texts, dpi)
        (out / f"to_{sheet['key']}.png").write_bytes(png_with_dpi(png, dpi))
        info.append(sheet_json(sheet, board))
    pdf = out / "to_ngoai_tham_A4_4trang.pdf"
    pdf.write_bytes(pdf_document_bytes(pages))
    meta = {"format": FORMAT, "created_local": datetime.now().isoformat(timespec="seconds"),
            "dictionary": DICTIONARY, "squares": list(SQUARES), "square_mm": SQUARE_MM, "marker_mm": MARKER_MM,
            "page_mm": list(PAGE_MM),
            "sheet_frame": "u sang phải, v xuống, mm từ góc TRÊN-trái tờ như lúc in; mép dưới (v = 210) là mép phía xe",
            "vehicle_frame": "x trước, y trái, gốc trên sàn dưới tâm trục sau; mét",
            "to_vehicle": "xy = anchor(xe) + ((u - u_ref_mm)·e_u + (210 - v)·e_up) / 1000",
            "anchors": {"front_edge": "(wheelbase + tire_radius, 0)", "rear_edge": "(-tire_radius, 0)",
                        "left_edge": "(0, tire_outer_width / 2)", "right_edge": "(0, -tire_outer_width / 2)"},
            "vehicle_keys": list(VEHICLE_KEYS), "sheets": info, "pdf": pdf.name}
    (out / "to_ngoai_tham.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    _ = cv2  # cv2 cần cho CharucoBoard; import ở đây để báo lỗi sớm nếu thiếu
    return meta


def check_png(path: Path, sheet: dict, scale: float = 1.0) -> dict:
    """Dò lại ChArUco trên PNG đã vẽ (thu nhỏ theo `scale`); trả số góc tìm được và sai lệch vị trí lớn nhất (mm)."""
    import cv2

    img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)
    dpi = 300.0 * scale
    if scale != 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    board = make_board(sheet["first_id"])
    det = cv2.aruco.CharucoDetector(board)
    ch_corners, ch_ids, _, marker_ids = det.detectBoard(img)
    n = 0 if ch_ids is None else len(ch_ids)
    err = None
    if n:
        expect = corners_sheet_mm(board)[ch_ids.ravel()]
        got = (ch_corners.reshape(-1, 2) + 0.5) / dpi * 25.4      # tâm điểm ảnh ở số nguyên
        err = float(np.max(np.linalg.norm(got - expect, axis=1)))
    ids = sorted(int(i) for i in marker_ids.ravel()) if marker_ids is not None else []
    return {"corners": n, "markers": ids, "max_err_mm": err}  # ngưỡng ở main: 1 điểm ảnh (vẽ làm tròn mép ô về điểm ảnh)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="In bốn tờ A4 hiệu chuẩn ngoại tham (ChArUco + vạch căn theo bánh xe).")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--dpi", type=float, default=300.0)
    p.add_argument("--check", action="store_true", help="dò lại ChArUco trên PNG vừa vẽ (cỡ gốc và thu nhỏ)")
    args = p.parse_args(argv)
    meta = write_sheets(args.out, args.dpi)
    out = Path(args.out)
    print(f"đã ghi {out / meta['pdf']} (4 trang), to_*.png, to_ngoai_tham.json")
    if not args.check:
        return 0
    bad = False
    for sheet in SHEETS:
        for scale in (1.0, 0.15, 0.085):           # 300 dpi; ≈ 8,9 và ≈ 5 điểm ảnh mỗi ô module 5 mm
            r = check_png(out / f"to_{sheet['key']}.png", sheet, scale)
            expect_ids = list(range(sheet["first_id"], sheet["first_id"] + 12))
            ok = r["corners"] == 15 and r["markers"] == expect_ids and r["max_err_mm"] < 25.4 / (300 * scale)
            bad |= not ok
            print(f"  {sheet['key']:5s} ×{scale:<5g} góc {r['corners']}/15, marker {len(r['markers'])}/12, "
                  f"lệch lớn nhất {r['max_err_mm'] if r['max_err_mm'] is None else round(r['max_err_mm'], 3)} mm"
                  f" → {'đạt' if ok else 'CHƯA ĐẠT'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
