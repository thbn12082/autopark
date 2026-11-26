"""Tờ marker ArUco để in cho tham chiếu trên cao R1 (T4, `autopark.perception.aruco_sheet`, thêm 02/10/2026).

PDF được đọc lại bằng regex (mỗi ô module đen là một hình chữ nhật đúng cỡ theo điểm PDF), vẽ lại bằng pdfium (QtPdf) rồi
dò bằng cv2.aruco; PNG được kiểm vạch giữa cạnh đánh dấu đúng tâm marker. Không mở camera hay cổng nào.
"""
import json
import math
import os
import re

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.perception import aruco_sheet as sheet  # noqa: E402

PT = 72 / 25.4


def _pdf_pages(data: bytes):
    """[(rộng_pt, cao_pt, [hình chữ nhật (x, y, w, h) pt])] theo thứ tự trang."""
    medias = re.findall(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", data)
    streams = re.findall(rb"stream\n(.*?)endstream", data, re.S)
    out = []
    for (w, h), body in zip(medias, streams):
        rects = [tuple(map(float, m)) for m in re.findall(r"([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re",
                                                          body.decode("ascii"))]
        out.append((float(w), float(h), rects))
    return out


def test_pdf_page_size_cells_and_ticks_are_exact(tmp_path):
    meta = sheet.write_sheets(tmp_path, [48, 49], 80.0)
    data = (tmp_path / meta["pdf"]["file"]).read_bytes()
    pages = _pdf_pages(data)
    assert len(pages) == 1 and meta["orientation"] == "landscape"            # hai ô 136 mm vừa A4 ngang
    w_pt, h_pt, rects = pages[0]
    assert (w_pt, h_pt) == pytest.approx((297 * PT, 210 * PT), abs=1e-3)
    module = 80.0 / 6 * PT
    modules = [r for r in rects if r[2] == pytest.approx(module, abs=2e-3) and r[3] == pytest.approx(module, abs=2e-3)]
    ticks = [r for r in rects if sorted(r[2:]) == pytest.approx(sorted((0.3 * PT, 8.0 * PT)), abs=2e-3)]
    assert len(modules) + len(ticks) == len(rects) and len(ticks) == 8
    for item in meta["pages"][0]["markers"]:
        cx, cy = (v * PT for v in item["centre_mm"])
        cy = h_pt - cy                                                       # PDF: gốc ở góc DƯỚI-trái
        mine = [r for r in modules if abs(r[0] + module / 2 - cx) < 45 * PT and abs(r[1] + module / 2 - cy) < 45 * PT]
        black = int(np.sum(~sheet.marker_bits("DICT_4X4_50", item["id"])))   # ô 0 của bit + toàn bộ viền đen
        assert len(mine) == black
        xs, ys = [r[0] for r in mine], [r[1] for r in mine]
        assert max(xs) + module - min(xs) == pytest.approx(80.0 * PT, abs=1e-3)    # cạnh marker đúng 80 mm
        assert max(ys) + module - min(ys) == pytest.approx(80.0 * PT, abs=1e-3)
        assert (min(xs) + max(xs) + module) / 2 == pytest.approx(cx, abs=1e-3)
        near = [r for r in ticks if math.hypot(r[0] + r[2] / 2 - cx, r[1] + r[3] / 2 - cy) < 70 * PT]
        mine_ticks = [r for r in near if abs(r[0] + r[2] / 2 - cx) < 1e-3 or abs(r[1] + r[3] / 2 - cy) < 1e-3]
        assert len(mine_ticks) == 4                                          # vạch nằm đúng trên hai đường tâm
        quiet = 1.5 * module
        outer = [abs(r[1] - cy) if r[2] < r[3] else abs(r[0] - cx) for r in mine_ticks]
        assert min(outer) >= 40 * PT + quiet - 1e-3                          # vạch ở NGOÀI vùng trắng
    assert "do tam = giao 2 vach" in data.decode("latin-1") and r"ID 48 \(sau\)" in data.decode("latin-1")
    many = sheet.write_sheets(tmp_path / "san", [0, 1, 2], 100.0)
    data = (tmp_path / "san" / many["pdf"]["file"]).read_bytes()
    assert len(_pdf_pages(data)) == 3 and data.count(b"/Type /Page ") == 3   # 100 mm: một mốc mỗi trang A4
    xref = int(re.search(rb"startxref\n(\d+)", data).group(1))
    entries = re.findall(rb"(\d{10}) 00000 n", data[xref:])
    assert len(entries) == 2 + 2 * 3 + 1
    for n, off in enumerate(entries, start=1):
        assert data[int(off):int(off) + 10].startswith(f"{n} 0 obj".encode())
    saved = json.loads((tmp_path / "san" / many["pdf"]["file"].replace(".pdf", ".json")).read_text(encoding="utf-8"))
    assert saved["format"] == "autopark.aruco_sheet/1" and [p["ids"] for p in saved["pages"]] == [[0], [1], [2]]


def test_pdf_rendered_by_qtpdf_is_detectable_with_all_ids_at_scale(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    try:
        from PySide6.QtCore import QSize
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtWidgets import QApplication
    except ImportError:
        pytest.skip("không có QtPdf")
    app = QApplication.instance() or QApplication([])           # noqa: F841 - QtPdf cần một ứng dụng Qt
    meta = sheet.write_sheets(tmp_path, [47, 48, 49], 80.0)
    doc = QPdfDocument()
    assert doc.load(str(tmp_path / meta["pdf"]["file"])) == QPdfDocument.Error.None_
    dpi = 100
    found = {}
    detector = cv2.aruco.ArucoDetector(sheet.get_dictionary("DICT_4X4_50"), cv2.aruco.DetectorParameters())
    for page in range(doc.pageCount()):
        pt = doc.pagePointSize(page)
        img = doc.render(page, QSize(round(pt.width() / 72 * dpi), round(pt.height() / 72 * dpi)))
        img = img.convertToFormat(img.Format.Format_ARGB32)
        bgra = np.array(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width()]
        alpha = bgra[..., 3:4].astype(np.float64) / 255.0
        gray = (bgra[..., :3].mean(axis=2, keepdims=True) * alpha + 255.0 * (1 - alpha))[..., 0].astype(np.uint8)
        corners, ids, _ = detector.detectMarkers(gray)
        for c, i in zip(corners, ids.ravel() if ids is not None else []):
            found[int(i)] = c.reshape(4, 2)
    assert sorted(found) == [47, 48, 49]
    for c in found.values():
        side = np.mean(np.linalg.norm(np.roll(c, -1, axis=0) - c, axis=1))
        assert side == pytest.approx(80.0 / 25.4 * dpi, rel=0.01)           # đúng tỉ lệ in


def test_png_ticks_mark_the_marker_centre_within_one_pixel(tmp_path):
    dpi = 150
    meta = sheet.write_sheets(tmp_path, [48, 49], 80.0, png=True, dpi=dpi)
    # OpenCV imread trên Windows có thể không mở được đường dẫn Unicode.
    page = cv2.imdecode(np.frombuffer((tmp_path / meta["png"]["files"][0]).read_bytes(), dtype=np.uint8),
                        cv2.IMREAD_GRAYSCALE)
    detector = cv2.aruco.ArucoDetector(sheet.get_dictionary("DICT_4X4_50"), cv2.aruco.DetectorParameters())
    corners, ids, _ = detector.detectMarkers(page)
    by_id = {int(i): c.reshape(4, 2) for c, i in zip(corners, ids.ravel())}
    px = dpi / 25.4
    for item in meta["pages"][0]["markers"]:
        centre = by_id[item["id"]].mean(axis=0)
        cx_mm, cy_mm = item["centre_mm"]
        half = (80.0 + 2 * 1.5 * 80.0 / 6) / 2
        band = page[int((cy_mm - half - 7) * px):int((cy_mm - half - 1) * px),
                    int((cx_mm - 10) * px):int((cx_mm + 10) * px)] < 128          # vạch trên
        cols = np.flatnonzero(band.any(axis=0)) + int((cx_mm - 10) * px)
        band = page[int((cy_mm - 10) * px):int((cy_mm + 10) * px),
                    int((cx_mm - half - 7) * px):int((cx_mm - half - 1) * px)] < 128  # vạch trái
        rows = np.flatnonzero(band.any(axis=1)) + int((cy_mm - 10) * px)
        assert len(cols) and len(rows)
        assert cols.mean() == pytest.approx(centre[0], abs=1.0)
        assert rows.mean() == pytest.approx(centre[1], abs=1.0)
    from autopark.perception.calib_board import read_png_dpi
    assert read_png_dpi((tmp_path / meta["png"]["files"][0]).read_bytes()) == pytest.approx(dpi, abs=0.02)


def test_committed_sheets_match_the_generator(tmp_path):
    # Tờ in đã commit trong calibration/bang_in/aruco/ (mốc sàn 0–47 cạnh 100 mm, xe 48–49 cạnh 80 mm, 02/10/2026)
    # phải đúng từng byte với bộ ghi hiện tại: đổi bố cục thì in lại và commit lại.
    from tests.conftest import PROJECT_ROOT

    folder = PROJECT_ROOT / "calibration" / "bang_in" / "aruco"
    for ids, size in ((list(range(48)), 100.0), ([48, 49], 80.0)):
        meta = sheet.write_sheets(tmp_path, ids, size)
        assert (folder / meta["pdf"]["file"]).read_bytes() == (tmp_path / meta["pdf"]["file"]).read_bytes()
        saved = json.loads((folder / meta["pdf"]["file"].replace(".pdf", ".json")).read_text(encoding="utf-8"))
        assert saved["pages"] == meta["pages"] and saved["ids"] == ids


def test_bad_ids_unknown_dictionary_and_oversize_exit_2(tmp_path, capsys):
    out = tmp_path / "ra"
    for argv in (["--ids", "x"], ["--ids", "5-2"], ["--ids", "0-60"], ["--ids", "1", "--dictionary", "DICT_9X9"],
                 ["--ids", "1", "--size-mm", "400"], ["--ids", "1", "--size-mm", "-5"]):
        assert sheet.main(argv + ["--out", str(out)]) == 2
    err = capsys.readouterr().err
    assert err.count("LỖI:") == 6 and "ngoài từ điển DICT_4X4_50" in err and "không vừa A4" in err
    assert not out.exists()
    assert sheet.parse_ids("0-3,7, 48;49") == [0, 1, 2, 3, 7, 48, 49]
