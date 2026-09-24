"""Bảng ô vuông (chessboard) để in, dùng cho hiệu chuẩn camera mắt cá (`autopark.perception.fisheye_calib`).

    .\\.venv\\Scripts\\python.exe -X utf8 -m autopark.perception.calib_board --out calibration/bang --paper A4

Ghi ba tệp cho một bảng: PDF một trang (hình vuông vẽ bằng vector, đúng kích thước vật lý theo điểm PDF 1/72 inch),
PNG cả trang ở một DPI cho trước (có khối pHYs ghi DPI) và JSON mô tả bảng. Không cần thư viện mới: PDF do một bộ ghi
viết tay tối giản ở dưới (không nén, đọc lại được bằng mắt), PNG qua OpenCV.

Cách dùng đúng (ghi cả trên trang in):
- In **100 %, không co giãn** ("Actual size", tắt "Fit to page"). PDF có gợi ý `/PrintScaling /None` cho trình đọc,
  nhưng nhiều trình đọc bỏ qua gợi ý này, nên vẫn phải chọn tay.
- Dán lên tấm phẳng, cứng (bìa foam, gỗ, kính). Bảng cong làm sai hiệu chuẩn mà RMS không nhất thiết lộ ra.
- Đo bằng thước khoảng cách giữa góc trong đầu và góc trong cuối của một hàng (`cols − 1` ô), chia cho số ô; nhập con
  số ĐO ĐƯỢC khi hiệu chuẩn, không nhập cỡ danh định. Đo nhiều ô một lúc sai số tương đối nhỏ hơn đo một ô.
- Cỡ ô KHÔNG ảnh hưởng tới nội tham (K, D) của camera — phép chiếu không đổi khi phóng cả bảng lẫn khoảng cách cùng tỉ lệ;
  nó chỉ quyết định khoảng cách bảng tính ra (và sau này ngoại tham). Độ phẳng và độ vuông của bảng thì có ảnh hưởng.

Bảng mặc định 9×6 góc trong (10×7 ô): số ô lẻ theo một chiều nên bảng không đối xứng khi xoay 180°. Viền trắng quanh
bảng rộng bằng một ô (bộ dò góc của OpenCV cần viền trắng). Chữ trên trang PDF/PNG không dấu vì phông chuẩn của PDF
(Helvetica) và phông Hershey của OpenCV không có chữ tiếng Việt.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import struct
import sys
import unicodedata
import zlib

import numpy as np

PAPERS_MM = {"A4": (210.0, 297.0), "A3": (297.0, 420.0)}      # (ngắn, dài)
PRINT_MARGIN_MM = 6.0      # lề mà máy in thường không in tới; bảng và viền trắng nằm trong phần còn lại
TEXT_BAND_MM = 8.0         # dải chữ hướng dẫn ở đầu trang (bỏ chữ nếu không đủ chỗ)
MM_PER_INCH = 25.4
PT_PER_MM = 72.0 / MM_PER_INCH


@dataclass(frozen=True)
class BoardSpec:
    """Bảng ô vuông: `cols` × `rows` GÓC TRONG (bảng có (cols + 1) × (rows + 1) ô), cạnh ô `square_mm`.

    Góc trong (i, j) nằm ở (i·ô, j·ô, 0) trong hệ tọa độ bảng (mét), thứ tự từng hàng từ trái sang phải — cùng thứ tự
    với `cv2.findChessboardCorners(SB)` khi `patternSize = (cols, rows)`.
    """
    cols: int = 9
    rows: int = 6
    square_mm: float = 20.0

    def __post_init__(self):
        if self.cols < 3 or self.rows < 3:
            raise ValueError("bảng cần ít nhất 3×3 góc trong")
        if not (math.isfinite(self.square_mm) and self.square_mm > 0):
            raise ValueError("cỡ ô phải dương")

    @property
    def pattern_size(self) -> tuple[int, int]:
        return (self.cols, self.rows)

    @property
    def n_corners(self) -> int:
        return self.cols * self.rows

    @property
    def squares(self) -> tuple[int, int]:
        return (self.cols + 1, self.rows + 1)

    def object_points(self) -> np.ndarray:
        """(N, 3) float64, mét."""
        s = self.square_mm / 1000.0
        j, i = np.mgrid[0:self.rows, 0:self.cols]
        return np.column_stack([i.ravel() * s, j.ravel() * s, np.zeros(self.n_corners)]).astype(np.float64)

    def to_dict(self) -> dict:
        return {"cols": self.cols, "rows": self.rows, "square_mm": self.square_mm}

    @classmethod
    def from_dict(cls, data: dict) -> "BoardSpec":
        return cls(int(data["cols"]), int(data["rows"]), float(data["square_mm"]))


@dataclass(frozen=True)
class PageLayout:
    """Vị trí bảng trên trang, đo bằng mm từ góc TRÊN-TRÁI của trang."""
    paper: str
    page_mm: tuple[float, float]           # (rộng, cao) theo hướng đã chọn
    origin_mm: tuple[float, float]         # góc trên-trái của ô (0, 0)
    square_mm: float
    squares: tuple[int, int]               # số ô (ngang, dọc)
    quiet_mm: float                        # viền trắng quanh bảng
    text: bool                             # có dải chữ hướng dẫn ở đầu trang

    @property
    def board_mm(self) -> tuple[float, float]:
        return (self.squares[0] * self.square_mm, self.squares[1] * self.square_mm)

    def black_squares(self) -> list[tuple[int, int]]:
        """(cột, hàng) các ô đen; ô trên-trái đen."""
        nx, ny = self.squares
        return [(ix, iy) for iy in range(ny) for ix in range(nx) if (ix + iy) % 2 == 0]


def page_size_mm(paper: str, orientation: str = "landscape") -> tuple[float, float]:
    if paper not in PAPERS_MM:
        raise ValueError(f"khổ giấy {paper!r} không hỗ trợ; chọn một trong {sorted(PAPERS_MM)}")
    short, long = PAPERS_MM[paper]
    if orientation == "landscape":
        return (long, short)
    if orientation == "portrait":
        return (short, long)
    raise ValueError("orientation phải là landscape hoặc portrait")


def max_square_mm(spec_cols: int, spec_rows: int, paper: str, orientation: str = "landscape", text: bool = True) -> float:
    """Cỡ ô lớn nhất còn vừa trang với viền trắng một ô và lề máy in."""
    w, h = page_size_mm(paper, orientation)
    nx, ny = spec_cols + 1, spec_rows + 1
    usable_w = w - 2 * PRINT_MARGIN_MM
    usable_h = h - 2 * PRINT_MARGIN_MM - (TEXT_BAND_MM if text else 0.0)
    return min(usable_w / (nx + 2), usable_h / (ny + 2))


def default_square_mm(cols: int, rows: int, paper: str, orientation: str = "landscape") -> float:
    """Bội số 5 mm lớn nhất còn vừa trang (A4 ngang, 9×6 → 20 mm; A3 → 30 mm): số tròn dễ so với thước."""
    return max(5.0, 5.0 * math.floor(max_square_mm(cols, rows, paper, orientation) / 5.0))


def layout(spec: BoardSpec, paper: str = "A4", orientation: str = "landscape") -> PageLayout:
    """Đặt bảng giữa trang; báo lỗi (kèm cỡ ô lớn nhất vừa trang) nếu bảng + viền trắng không vừa."""
    w, h = page_size_mm(paper, orientation)
    nx, ny = spec.squares
    sq = spec.square_mm
    quiet = sq
    need_w, need_h = (nx + 2) * sq + 2 * PRINT_MARGIN_MM, (ny + 2) * sq + 2 * PRINT_MARGIN_MM
    if need_w > w + 1e-9 or need_h > h + 1e-9:
        biggest = max_square_mm(spec.cols, spec.rows, paper, orientation, text=False)
        raise ValueError(f"bảng {spec.cols}×{spec.rows} ô {sq:g} mm không vừa {paper} {orientation} (kể cả viền trắng một ô "
                         f"và lề máy in {PRINT_MARGIN_MM:g} mm); cỡ ô lớn nhất vừa trang ≈ {math.floor(biggest * 10) / 10:g} mm")
    text = need_h + TEXT_BAND_MM <= h + 1e-9
    x0 = (w - nx * sq) / 2
    if text:                                     # dải chữ ở trên: đẩy bảng xuống nửa dải
        y0 = (h - ny * sq) / 2 + TEXT_BAND_MM / 2
    else:
        y0 = (h - ny * sq) / 2
    return PageLayout(paper, (w, h), (x0, y0), sq, (nx, ny), quiet, text)


def ascii_fold(text: str) -> str:
    """Bỏ dấu tiếng Việt (phông chuẩn PDF và Hershey không có các chữ này): 'Đo ô' → 'Do o'."""
    text = text.replace("Đ", "D").replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).encode("ascii", "replace").decode("ascii")


def instruction_text(spec: BoardSpec, paper: str) -> str:
    span = spec.cols - 1
    return (f"Bảng hiệu chuẩn {spec.cols}x{spec.rows} góc trong, ô {spec.square_mm:g} mm, {paper}. In 100% (không co giãn). "
            f"Đo {span} ô giữa góc trong đầu và cuối một hàng: danh định {span * spec.square_mm:g} mm; "
            f"nhập cỡ ô ĐO ĐƯỢC.")


# ---- PDF ---------------------------------------------------------------------------------------------------------
def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _num(x: float) -> str:
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def pdf_bytes(lay: PageLayout, text: str | None = None) -> bytes:
    """Một trang PDF 1.6: MediaBox đúng khổ giấy theo điểm (1/72 inch), mỗi ô đen là một hình chữ nhật vector.

    Gốc tọa độ PDF ở góc DƯỚI-trái nên y được lật. Nội dung không nén để kiểm lại được bằng mắt/regex."""
    w_mm, h_mm = lay.page_mm
    k = PT_PER_MM
    ops = ["0 g"]
    sq = lay.square_mm
    for ix, iy in lay.black_squares():
        x = lay.origin_mm[0] + ix * sq
        y_top = lay.origin_mm[1] + iy * sq
        ops.append(f"{_num(x * k)} {_num((h_mm - y_top - sq) * k)} {_num(sq * k)} {_num(sq * k)} re")
    ops.append("f")
    if text and lay.text:
        folded = ascii_fold(text)
        x_pt = PRINT_MARGIN_MM * k + 4
        # bề rộng Helvetica trung bình ≈ 0,5 em cho chữ thường; thu cỡ chữ để dòng không tràn lề phải
        size_pt = max(4.0, min(8.0, (w_mm * k - 2 * x_pt) / (0.52 * max(1, len(folded)))))
        baseline_mm = lay.origin_mm[1] - lay.quiet_mm - TEXT_BAND_MM / 2 + 1.0
        ops.append(f"BT /F1 {_num(size_pt)} Tf {_num(x_pt)} {_num((h_mm - baseline_mm) * k)} Td "
                   f"({_pdf_escape(folded)}) Tj ET")
    content = ("\n".join(ops) + "\n").encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R /ViewerPreferences << /PrintScaling /None >> >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_num(w_mm * k)} {_num(h_mm * k)}] /Contents 4 0 R "
         f"/Resources << /Font << /F1 5 0 R >> >> >>").encode("ascii"),
        f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.6\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii") + b"0000000000 65535 f\r\n"
    for off in offsets:
        out += f"{off:010d} 00000 n\r\n".encode("ascii")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    return bytes(out)


# ---- PNG ---------------------------------------------------------------------------------------------------------
def mm_to_px(mm: float, dpi: float) -> int:
    return int(round(mm * dpi / MM_PER_INCH))


def render_page(lay: PageLayout, dpi: float = 300.0, text: str | None = None) -> tuple[np.ndarray, dict]:
    """Ảnh xám cả trang ở `dpi`. Cạnh ô làm tròn tới số nguyên điểm ảnh; cỡ ô THẬT của PNG ghi trong dict trả về."""
    import cv2

    w_px, h_px = mm_to_px(lay.page_mm[0], dpi), mm_to_px(lay.page_mm[1], dpi)
    sq_px = mm_to_px(lay.square_mm, dpi)
    x0, y0 = mm_to_px(lay.origin_mm[0], dpi), mm_to_px(lay.origin_mm[1], dpi)
    page = np.full((h_px, w_px), 255, np.uint8)
    for ix, iy in lay.black_squares():
        page[y0 + iy * sq_px:y0 + (iy + 1) * sq_px, x0 + ix * sq_px:x0 + (ix + 1) * sq_px] = 0
    if text and lay.text:
        scale = dpi / 300.0 * 1.0
        y_text = mm_to_px(lay.origin_mm[1] - lay.quiet_mm - TEXT_BAND_MM / 2 + 1.0, dpi)
        x_text = mm_to_px(PRINT_MARGIN_MM + 1.5, dpi)
        max_w = w_px - 2 * x_text
        folded = ascii_fold(text)
        (tw, _), _ = cv2.getTextSize(folded, cv2.FONT_HERSHEY_SIMPLEX, scale, max(1, round(2 * dpi / 300)))
        if tw > max_w:
            scale *= max_w / tw
        cv2.putText(page, folded, (x_text, y_text), cv2.FONT_HERSHEY_SIMPLEX, scale, 0, max(1, round(2 * dpi / 300)),
                    cv2.LINE_AA)
    info = {"dpi": dpi, "size_px": [w_px, h_px], "square_px": sq_px, "square_mm_at_dpi": sq_px * MM_PER_INCH / dpi,
            "board_origin_px": [x0, y0]}
    return page, info


def png_with_dpi(image: np.ndarray, dpi: float) -> bytes:
    """Mã hóa PNG rồi chèn khối pHYs (điểm ảnh/mét) ngay sau IHDR để phần mềm in biết DPI (cv2.imencode không ghi)."""
    import cv2

    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("cv2.imencode(.png) thất bại")
    data = buf.tobytes()
    ppm = int(round(dpi / 0.0254))
    body = b"pHYs" + struct.pack(">IIB", ppm, ppm, 1)
    chunk = struct.pack(">I", 9) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    ihdr_end = 8 + 4 + 4 + 13 + 4
    return data[:ihdr_end] + chunk + data[ihdr_end:]


def read_png_dpi(data: bytes) -> float | None:
    """DPI từ khối pHYs của một PNG (None nếu không có hoặc đơn vị không phải mét)."""
    pos = 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"pHYs":
            ppx, ppy, unit = struct.unpack(">IIB", data[pos + 8:pos + 17])
            return ppx * 0.0254 if unit == 1 else None
        if kind == b"IDAT":
            return None
        pos += 12 + length
    return None


# ---- ghi cả bộ ----------------------------------------------------------------------------------------------------
def board_basename(spec: BoardSpec, paper: str) -> str:
    return f"ban_co_{spec.cols}x{spec.rows}_{spec.square_mm:g}mm_{paper}".replace(".", "p")


def write_board(out_dir, spec: BoardSpec, paper: str = "A4", orientation: str = "landscape", dpi: float = 300.0) -> dict:
    """Ghi <tên>.pdf, <tên>.png, <tên>.json vào `out_dir`; trả về nội dung JSON."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lay = layout(spec, paper, orientation)
    text = instruction_text(spec, paper)
    name = board_basename(spec, paper)
    pdf_path, png_path, json_path = out_dir / f"{name}.pdf", out_dir / f"{name}.png", out_dir / f"{name}.json"
    pdf_path.write_bytes(pdf_bytes(lay, text))
    page, png_info = render_page(lay, dpi, text)
    png_path.write_bytes(png_with_dpi(page, dpi))
    span = spec.cols - 1
    meta = {
        "format": "autopark.calib_board/1",
        "pattern": "chessboard",
        "inner_corners": {"cols": spec.cols, "rows": spec.rows},
        "squares": {"x": spec.squares[0], "y": spec.squares[1]},
        "square_mm_nominal": spec.square_mm,
        "paper": paper, "orientation": orientation, "page_mm": list(lay.page_mm),
        "board_origin_mm": [round(v, 4) for v in lay.origin_mm], "board_mm": list(lay.board_mm),
        "quiet_zone_mm": lay.quiet_mm, "print_margin_mm": PRINT_MARGIN_MM, "text_on_page": lay.text,
        "pdf": {"file": pdf_path.name, "square_pt": spec.square_mm * PT_PER_MM, "print_scaling_none_hint": True},
        "png": {"file": png_path.name, **png_info},
        "measure_hint": {"span_squares": span, "span_mm_nominal": span * spec.square_mm,
                         "how": "đo bằng thước từ góc trong đầu tới góc trong cuối của một hàng, chia cho span_squares"},
        "created_local": datetime.now().isoformat(timespec="seconds"),
        "note": ("Kích thước danh định. Sau khi in phải đo lại và dùng cỡ ô ĐO ĐƯỢC khi hiệu chuẩn; PNG làm tròn cạnh ô tới "
                 "số nguyên điểm ảnh nên cỡ ô của PNG là png.square_mm_at_dpi, không đúng hẳn square_mm_nominal."),
    }
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def add_board_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", type=Path, default=Path("calibration/bang_in"), help="thư mục ghi PDF/PNG/JSON")
    p.add_argument("--cols", type=int, default=9, help="số góc trong theo chiều ngang (mặc định 9)")
    p.add_argument("--rows", type=int, default=6, help="số góc trong theo chiều dọc (mặc định 6)")
    p.add_argument("--square-mm", type=float, default=None,
                   help="cỡ ô danh định (mm); mặc định bội số 5 mm lớn nhất vừa khổ giấy")
    p.add_argument("--paper", choices=sorted(PAPERS_MM), default="A4")
    p.add_argument("--orientation", choices=("landscape", "portrait"), default="landscape")
    p.add_argument("--dpi", type=float, default=300.0, help="DPI của bản PNG")


def run_board(args) -> int:
    square = args.square_mm if args.square_mm else default_square_mm(args.cols, args.rows, args.paper, args.orientation)
    try:
        meta = write_board(args.out, BoardSpec(args.cols, args.rows, square), args.paper, args.orientation, args.dpi)
    except ValueError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    print(f"đã ghi {Path(args.out) / meta['pdf']['file']} và .png/.json")
    print(f"bảng {args.cols}×{args.rows} góc trong, ô {square:g} mm, {args.paper} {args.orientation}")
    print(f"IN 100 % (không co giãn), dán lên tấm phẳng, rồi đo {meta['measure_hint']['span_squares']} ô giữa góc trong đầu và "
          f"cuối một hàng (danh định {meta['measure_hint']['span_mm_nominal']:g} mm) và dùng cỡ ô ĐO ĐƯỢC khi hiệu chuẩn.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_board_args(p)
    return run_board(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
