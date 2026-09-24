"""Hiệu chuẩn camera mắt cá không cần phần cứng.

Ảnh bảng ô vuông được dựng qua một camera Kannala–Brandt ĐÃ BIẾT (K, D chọn gần một webcam "130°" 640×480): với mỗi điểm
ảnh con (siêu lấy mẫu 3×3), tia nhìn lấy từ `cv2.fisheye.undistortPoints` (không dùng mã của mô-đun đang kiểm), cắt mặt
phẳng bảng, tô màu theo ô, rồi làm mờ nhẹ và thêm nhiễu. Hiệu chuẩn phải tìm lại K, D đó. Bảng in (PDF/PNG) được kiểm
kích thước vật lý, PDF còn được vẽ lại bằng pdfium (QtPdf) rồi dò bảng trên ảnh vẽ ra.
"""
from functools import lru_cache
import json
import math
import os
import re

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.perception import calib_board as cb  # noqa: E402
from autopark.perception import fisheye_calib as fc  # noqa: E402
from autopark.perception.calib_board import BoardSpec  # noqa: E402

SIZE = (640, 480)
TRUE_K = np.array([[351.0, 0.0, 324.3], [0.0, 349.2, 236.8], [0.0, 0.0, 1.0]])
TRUE_D = np.array([-0.035, 0.018, -0.009, 0.0015])
SPEC = BoardSpec(9, 6, 25.0)


def _rot(axis, angle):
    return cv2.Rodrigues(np.asarray(axis, np.float64) * angle)[0]


class SyntheticCamera:
    """Camera KB đã biết, dựng ảnh bảng bằng ánh xạ ngược: điểm ảnh → tia → mặt phẳng bảng → màu ô."""

    def __init__(self, K=TRUE_K, D=TRUE_D, size=SIZE, supersample=3):
        self.K, self.D, self.size, self.ss = np.asarray(K, float), np.asarray(D, float), size, supersample
        w, h = size
        us = (np.arange(w * supersample) + 0.5) / supersample - 0.5
        vs = (np.arange(h * supersample) + 0.5) / supersample - 0.5
        uu, vv = np.meshgrid(us, vs)
        pts = np.stack([uu.ravel(), vv.ravel()], 1).reshape(-1, 1, 2)
        und = cv2.fisheye.undistortPoints(pts, self.K, self.D.reshape(4, 1),
                                          criteria=(cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 30, 1e-12))
        und = und.reshape(h * supersample, w * supersample, 2)
        self.rays = np.dstack([und, np.ones(und.shape[:2])])
        self.vgrad = vv / (h * supersample)

    def ray(self, u, v):
        p = cv2.fisheye.undistortPoints(np.array([[[u, v]]], float), self.K, self.D.reshape(4, 1)).reshape(2)
        d = np.array([p[0], p[1], 1.0])
        return d / np.linalg.norm(d)

    def project(self, points_b, R, t):
        rv = cv2.Rodrigues(R)[0]
        return cv2.fisheye.projectPoints(np.asarray(points_b, float).reshape(1, -1, 3), rv, t.reshape(3, 1), self.K,
                                         self.D.reshape(4, 1))[0].reshape(-1, 2)

    def pose(self, spec, u, v, tilt_x_deg, tilt_y_deg, roll_deg, margin=3.0):
        """Bảng hướng về camera, tâm trên tia qua (u, v), nghiêng theo góc cho trước; lùi xa dần tới khi CẢ tờ giấy
        (bảng + viền trắng một ô) nằm trong ảnh. None nếu không đặt được."""
        s = spec.square_mm / 1000.0
        d = self.ray(u, v)
        z = np.array([0.0, 0.0, 1.0])
        axis = np.cross(z, d)
        align = np.eye(3) if np.linalg.norm(axis) < 1e-12 else _rot(axis / np.linalg.norm(axis), math.atan2(np.linalg.norm(axis), z @ d))
        R = align @ _rot([1, 0, 0], math.radians(tilt_x_deg)) @ _rot([0, 1, 0], math.radians(tilt_y_deg)) \
            @ _rot([0, 0, 1], math.radians(roll_deg))
        centre = np.array([(spec.cols - 1) / 2 * s, (spec.rows - 1) / 2 * s, 0.0])
        paper = np.array([[x, y, 0.0] for x in (-2 * s, (spec.cols + 1) * s) for y in (-2 * s, (spec.rows + 1) * s)])
        w, h = self.size
        for dist in np.arange(0.18, 1.0, 0.01):
            t = dist * d - R @ centre
            if ((paper @ R.T + t)[:, 2] <= 0.02).any():
                continue
            p = self.project(paper, R, t)
            if (p[:, 0] > margin).all() and (p[:, 0] < w - 1 - margin).all() and (p[:, 1] > margin).all() \
                    and (p[:, 1] < h - 1 - margin).all():
                return R, t
        return None

    def render(self, spec, R, t, rng, blur=0.6, noise=2.0):
        s = spec.square_mm / 1000.0
        n = R[:, 2]
        denom = self.rays @ n
        with np.errstate(divide="ignore", invalid="ignore"):
            k = (n @ t) / np.where(np.abs(denom) < 1e-12, np.nan, denom)
        P = self.rays * k[..., None] - t
        Pb = P @ R
        X, Y = Pb[..., 0], Pb[..., 1]
        ok = np.isfinite(k) & (k > 0)
        img = 70.0 + 25.0 * self.vgrad
        paper = ok & (X >= -2 * s) & (X <= (spec.cols + 1) * s) & (Y >= -2 * s) & (Y <= (spec.rows + 1) * s)
        img = np.where(paper, 225.0, img)
        board = ok & (X >= -s) & (X < spec.cols * s) & (Y >= -s) & (Y < spec.rows * s)
        black = board & ((np.floor(X / s) + np.floor(Y / s)) % 2 == 0)
        img = np.where(black, 25.0, img)
        w, h = self.size
        img = img.reshape(h, self.ss, w, self.ss).mean(axis=(1, 3))
        if blur:
            img = cv2.GaussianBlur(img, (0, 0), blur)
        img = img + rng.normal(0.0, noise, img.shape)
        return cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)

    def true_corners(self, spec, R, t):
        return self.project(spec.object_points(), R, t)


# tâm bảng đặt khắp ảnh, kể cả bốn góc; nghiêng tới ±40° quanh hai trục, xoay trong mặt phẳng tới ±20°
TARGETS = [(110, 90), (320, 90), (530, 90), (110, 240), (320, 240), (530, 240), (110, 390), (320, 390), (530, 390),
           (60, 60), (580, 60), (60, 420), (580, 420), (200, 150), (450, 330), (320, 100), (320, 400), (440, 150),
           (200, 330), (80, 240), (560, 240), (320, 240)]


@lru_cache(maxsize=None)
def synthetic_set(n: int = 22, seed: int = 7):
    """[(ảnh, R, t)] ở các tư thế đa dạng; tính một lần mỗi phiên test."""
    cam = SyntheticCamera()
    rng = np.random.default_rng(seed)
    out = []
    for u, v in TARGETS[:n]:
        tilt_x, tilt_y, roll = rng.uniform(-40, 40), rng.uniform(-40, 40), rng.uniform(-20, 20)
        pose = cam.pose(SPEC, u, v, tilt_x, tilt_y, roll)
        if pose is None:
            continue
        out.append((cam.render(SPEC, *pose, rng), *pose))
    return cam, out


def detected_views(images):
    views = []
    for k, image in enumerate(images):
        det, q = fc.assess_frame(image, SPEC)
        if q.ok:
            views.append((f"v{k:02d}", det.corners))
    return views


# ---- bảng in -------------------------------------------------------------------------------------------------------
def _pdf_parts(data: bytes):
    media = re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", data)
    stream = re.search(rb"stream\n(.*?)endstream", data, re.S).group(1).decode("ascii")
    rects = [tuple(map(float, m)) for m in re.findall(r"([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re", stream)]
    return (float(media.group(1)), float(media.group(2))), rects, stream


def test_board_pdf_has_exact_physical_scale_and_valid_xref(tmp_path):
    meta = cb.write_board(tmp_path / "bảng in", BoardSpec(9, 6, 20.0), "A4")
    data = (tmp_path / "bảng in" / meta["pdf"]["file"]).read_bytes()
    (w_pt, h_pt), rects, stream = _pdf_parts(data)
    assert (w_pt, h_pt) == pytest.approx((297 * 72 / 25.4, 210 * 72 / 25.4), abs=1e-3)       # A4 ngang, đúng điểm PDF
    sq_pt = 20.0 * 72 / 25.4
    assert len(rects) == 35                                                                   # 10×7 ô, 35 ô đen
    assert all(r[2] == pytest.approx(sq_pt, abs=1e-3) and r[3] == pytest.approx(sq_pt, abs=1e-3) for r in rects)
    xs, ys = [r[0] for r in rects], [r[1] for r in rects]
    assert max(xs) + sq_pt - min(xs) == pytest.approx(10 * sq_pt, abs=1e-3)                  # bảng 200 × 140 mm
    assert max(ys) + sq_pt - min(ys) == pytest.approx(7 * sq_pt, abs=1e-3)
    quiet = 20.0 * 72 / 25.4
    assert min(xs) >= quiet and w_pt - (max(xs) + sq_pt) >= quiet and min(ys) >= quiet     # viền trắng ≥ một ô
    assert "/PrintScaling /None" in data.decode("latin-1")
    assert r"In 100% \(khong co gian\)" in stream and "160 mm" in stream                     # chữ không dấu, 8 ô = 160 mm
    # bảng xref: mỗi offset trỏ đúng "n 0 obj"
    xref = int(re.search(rb"startxref\n(\d+)", data).group(1))
    entries = re.findall(rb"(\d{10}) 00000 n", data[xref:])
    assert len(entries) == 5
    for n, off in enumerate(entries, start=1):
        assert data[int(off):int(off) + 10].startswith(f"{n} 0 obj".encode())
    spec_json = json.loads((tmp_path / "bảng in" / meta["png"]["file"].replace(".png", ".json")).read_text(encoding="utf-8"))
    assert spec_json["inner_corners"] == {"cols": 9, "rows": 6} and spec_json["measure_hint"]["span_mm_nominal"] == 160


def test_board_pdf_rendered_by_pdfium_is_a_detectable_board_at_the_printed_scale(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    try:
        from PySide6.QtCore import QSize
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtWidgets import QApplication
    except ImportError:
        pytest.skip("không có QtPdf")
    # QApplication chứ không phải QGuiApplication: test giao diện chạy sau trong cùng tiến trình lấy lại instance này
    # để dựng widget, mà widget cần QApplication (với QGuiApplication tiến trình bị hủy)
    app = QApplication.instance() or QApplication([])           # noqa: F841 - QtPdf cần một ứng dụng Qt
    meta = cb.write_board(tmp_path, BoardSpec(9, 6, 20.0), "A4")
    doc = QPdfDocument()
    assert doc.load(str(tmp_path / meta["pdf"]["file"])) == QPdfDocument.Error.None_
    pt = doc.pagePointSize(0)
    assert (pt.width(), pt.height()) == pytest.approx((297 * 72 / 25.4, 210 * 72 / 25.4), abs=0.01)
    dpi = 100
    img = doc.render(0, QSize(round(297 / 25.4 * dpi), round(210 / 25.4 * dpi)))
    img = img.convertToFormat(img.Format.Format_ARGB32)          # pdfium để nền trong suốt: ghép lên giấy trắng
    bgra = np.array(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width()]
    alpha = bgra[..., 3:4].astype(np.float64) / 255.0
    gray = (bgra[..., :3].mean(axis=2, keepdims=True) * alpha + 255.0 * (1 - alpha))[..., 0].astype(np.uint8)
    ok, corners = cv2.findChessboardCornersSB(gray, (9, 6), flags=cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_ACCURACY)
    assert ok
    g = corners.reshape(6, 9, 2)
    spacing = np.linalg.norm(np.diff(g, axis=1), axis=2).mean()
    assert spacing == pytest.approx(20.0 / 25.4 * dpi, rel=0.01)          # 78,7 px một ô ở 100 DPI: đúng tỉ lệ in


def test_board_png_records_dpi_and_squares_have_the_stated_size(tmp_path):
    meta = cb.write_board(tmp_path, BoardSpec(9, 6, 20.0), "A4", dpi=300)
    data = (tmp_path / meta["png"]["file"]).read_bytes()
    assert cb.read_png_dpi(data) == pytest.approx(300, abs=0.01)
    page = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert page.shape == (round(210 / 25.4 * 300), round(297 / 25.4 * 300))
    sq_px = round(20.0 / 25.4 * 300)
    assert meta["png"]["square_px"] == sq_px and meta["png"]["square_mm_at_dpi"] == pytest.approx(20.0, abs=0.05)
    row = page[meta["png"]["board_origin_px"][1] + sq_px // 2] < 128          # giữa hàng ô đầu tiên
    edges = np.flatnonzero(np.diff(row.astype(np.int8)))
    runs = np.diff(edges)
    assert len(runs) == 9 and np.all(runs == sq_px)                         # 10 ô liền nhau, mỗi ô đúng sq_px điểm ảnh
    small = cv2.resize(page, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    ok, _ = cv2.findChessboardCornersSB(small, (9, 6), flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
    assert ok


def test_board_that_does_not_fit_the_paper_is_refused_with_the_largest_size():
    with pytest.raises(ValueError, match="cỡ ô lớn nhất"):
        cb.layout(BoardSpec(9, 6, 30.0), "A4")
    assert cb.default_square_mm(9, 6, "A4") == 20.0 and cb.default_square_mm(9, 6, "A3") == 30.0
    cb.layout(BoardSpec(9, 6, 30.0), "A3")
    assert cb.ascii_fold("Đo ô ĐƯỢC") == "Do o DUOC"


def test_board_cli(tmp_path, capsys):
    assert fc.main(["board", "--out", str(tmp_path / "in"), "--paper", "A3"]) == 0
    assert (tmp_path / "in" / "ban_co_9x6_30mm_A3.pdf").exists()
    assert "IN 100 %" in capsys.readouterr().out


# ---- dò góc, chất lượng --------------------------------------------------------------------------------------------
def test_detection_finds_corners_at_subpixel_accuracy_on_synthetic_fisheye_views():
    cam, views = synthetic_set()
    errors = []
    for image, R, t in views[:8]:
        det, q = fc.assess_frame(image, SPEC)
        assert det.found and q.ok, q.reasons
        truth = cam.true_corners(SPEC, R, t)
        e = min(np.linalg.norm(det.corners - truth, axis=1).mean(), np.linalg.norm(det.corners[::-1] - truth, axis=1).mean())
        errors.append(e)
        assert q.edge_width_px < fc.MAX_EDGE_WIDTH_PX and q.contrast > 150
    assert max(errors) < 0.35


def test_truncated_and_torn_frames_are_rejected_before_detection():
    from tests.test_truncated_frames import tear, truncate

    _, views = synthetic_set()
    image = views[4][0]
    assert fc.assess_frame(image, SPEC)[1].ok
    for broken, word in ((truncate(image, 300), "cắt cụt"), (tear(image, 20, 200), "dải xé")):
        det, q = fc.assess_frame(broken, SPEC)
        assert not det.found and not q.ok and q.damaged and word in q.damaged and q.reasons == [q.damaged]


def test_blurred_board_and_board_touching_the_edge_are_flagged():
    _, views = synthetic_set()
    image = views[4][0]
    blurred = cv2.GaussianBlur(image, (0, 0), 3.0)
    det, q = fc.assess_frame(blurred, SPEC)
    assert det.found and q.edge_width_px > fc.MAX_EDGE_WIDTH_PX and any("mờ" in r for r in q.reasons)
    det, q = fc.assess_frame(blurred, SPEC, max_edge_width=50.0)          # ngưỡng chỉnh được
    assert not any("mờ" in r for r in q.reasons)
    det, q = fc.assess_frame(image, SPEC, edge_margin=1000.0)
    assert any("sát mép" in r for r in q.reasons)
    blank = np.full((480, 640, 3), 120, np.uint8)
    det, q = fc.assess_frame(blank, SPEC)
    assert not det.found and "không thấy" in q.reasons[0]


def test_coverage_map_shows_regions_without_corners():
    xs, ys = np.meshgrid(np.linspace(5, 300, 9), np.linspace(5, 470, 6))
    left = [np.column_stack([xs.ravel(), ys.ravel()])]                      # mọi góc ở nửa trái ảnh
    counts = fc.coverage_counts(left, SIZE)
    s = fc.coverage_summary(counts)
    assert counts.shape == (6, 8) and counts[:, 4:].sum() == 0 and counts.sum() == 54
    assert s["corner_blocks"] == {"tl": True, "tr": False, "bl": True, "br": False}
    assert 0 < s["fraction"] <= 0.5
    img = fc.draw_coverage(np.zeros((480, 640, 3), np.uint8), counts, alpha=1.0)
    assert img[250, 600, 2] > 200 and img[250, 600, 1] < 60                  # ô trống: đỏ
    assert img[10, 10, 1] > 100 and img[10, 10, 2] < 60                      # ô có góc: xanh
    _, views = synthetic_set()
    full = fc.coverage_summary(fc.coverage_counts([fc.assess_frame(v[0], SPEC)[0].corners for v in views], SIZE))
    assert full["fraction"] >= 0.9 and all(full["corner_blocks"].values())


def test_auto_capture_waits_for_a_still_board_and_refuses_repeated_poses():
    _, views = synthetic_set()
    c1 = fc.detect_corners(views[0][0], SPEC).corners
    c2 = fc.detect_corners(views[5][0], SPEC).corners
    d1, d2 = fc.pose_descriptor(c1, SPEC, SIZE), fc.pose_descriptor(c2, SPEC, SIZE)
    assert fc.pose_distance(d1, fc.pose_descriptor(c1[::-1], SPEC, SIZE)) < 1e-9      # đảo thứ tự góc: cùng tư thế
    assert fc.pose_distance(d1, d2) > fc.MIN_POSE_DISTANCE
    gate = fc.AutoCaptureGate(still_s=0.3, min_interval_s=0.5)
    t = 0.0
    for k in range(10):                                                     # bảng đang chạy: không chụp
        t += 0.05
        assert gate.update(t, c1 + 3.0 * k, True, d1, [])[0] is False
    results = []
    for _ in range(10):                                                     # đứng yên 0,5 s: chụp sau khoảng 0,3 s
        t += 0.05
        results.append(gate.update(t, c1, True, d1, [])[0])
    assert results[:5] == [False] * 5 and any(results)
    gate.captured(t)
    for _ in range(30):                                                     # vẫn tư thế đó: không chụp lại
        t += 0.05
        ok, why = gate.update(t, c1, True, d1, [d1])
        assert not ok
    assert "trùng tư thế" in why
    assert gate.update(t + 0.05, c2, True, d2, [d1])[0] is False              # tư thế mới: phải đứng yên lại
    for _ in range(10):
        t += 0.05
        ok, _ = gate.update(t + 0.05, c2, True, d2, [d1])
    assert ok
    assert gate.update(t + 0.1, c2, False, d2, [d1]) == (False, "chất lượng chưa đạt")


# ---- hiệu chuẩn ----------------------------------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _calibrated():
    _, views = synthetic_set()
    detected = detected_views([v[0] for v in views])
    return detected, fc.calibrate_fisheye(detected, SPEC, SIZE)


def test_calibration_recovers_the_known_fisheye_camera():
    cam, views = synthetic_set()
    detected, calib = _calibrated()
    assert len(views) >= 18 and len(detected) >= 16
    K = calib.K
    assert K[0, 0] == pytest.approx(TRUE_K[0, 0], rel=0.01) and K[1, 1] == pytest.approx(TRUE_K[1, 1], rel=0.01)
    assert abs(K[0, 2] - TRUE_K[0, 2]) < 2.0 and abs(K[1, 2] - TRUE_K[1, 2]) < 2.0
    assert K[0, 1] == 0.0                                                   # CALIB_FIX_SKEW
    assert calib.rms_px < 0.3 and calib.n_used >= 16
    # D: các hệ số tương quan nhau nên so cả MÔ HÌNH: tia thật qua mỗi điểm ảnh (lưới 65×49 phủ cả góc ảnh) chiếu lại
    # bằng mô hình tìm được phải rơi đúng điểm ảnh đó. Bỏ bước cornerSubPix thì trung vị ~0,7 px, lớn nhất ~2,3 px.
    uu, vv = np.meshgrid(np.linspace(0, 639, 65), np.linspace(0, 479, 49))
    rays = fc.pixel_rays(uu.ravel(), vv.ravel(), TRUE_K, TRUE_D)
    back = cv2.fisheye.projectPoints(rays.reshape(1, -1, 3), np.zeros(3), np.zeros(3), K, calib.D.reshape(4, 1))[0].reshape(-1, 2)
    model_err = np.hypot(back[:, 0] - uu.ravel(), back[:, 1] - vv.ravel())
    assert np.median(model_err) < 0.2 and model_err.max() < 1.0
    assert np.abs(calib.D - TRUE_D).max() < 0.02
    fov, true_fov = fc.field_of_view(K, calib.D, SIZE), fc.field_of_view(TRUE_K, TRUE_D, SIZE)
    for key in ("horizontal_deg", "vertical_deg", "diagonal_deg"):
        assert fov[key] == pytest.approx(true_fov[key], abs=1.0)
    assert 100 < true_fov["horizontal_deg"] < 115 and 130 < true_fov["diagonal_deg"] < 140
    # khoảng cách bảng tính theo cỡ ô đã nhập: so với tư thế thật
    used = {v.name: v for v in calib.views}
    k0 = int(detected[0][0][1:])
    true_centre = views[k0][1] @ np.array([4 * 0.025, 2.5 * 0.025, 0]) + views[k0][2]
    assert used[detected[0][0]].distance_m == pytest.approx(np.linalg.norm(true_centre), rel=0.02)


def test_a_bad_view_is_rejected_as_an_outlier_and_the_result_is_better_without_it():
    detected, clean = _calibrated()
    rng = np.random.default_rng(3)
    corrupted = list(detected)
    name, corners = corrupted[3]
    bad = corners.copy()
    bad[::2] += rng.normal(0, 4.0, bad[::2].shape).astype(np.float32)        # nửa số góc lệch vài px: bảng cong/dò sai
    corrupted[3] = (name, bad)
    with_rejection = fc.calibrate_fisheye(corrupted, SPEC, SIZE)
    rejected = [v for v in with_rejection.views if not v.used]
    assert [v.name for v in rejected] == [name] and "RMS riêng" in rejected[0].reason
    assert rejected[0].rms_px > 1.0                                          # chấm lại dưới mô hình cuối
    assert with_rejection.rounds == 2
    without = fc.calibrate_fisheye(corrupted, SPEC, SIZE, reject_outliers=False)
    assert all(v.used for v in without.views)
    assert without.rms_px > 3 * with_rejection.rms_px
    err_with = abs(with_rejection.K[0, 0] - TRUE_K[0, 0])
    assert with_rejection.rms_px == pytest.approx(clean.rms_px, rel=0.2) and err_with < 0.01 * TRUE_K[0, 0]


def test_too_few_views_is_an_error():
    detected, _ = _calibrated()
    with pytest.raises(fc.CalibrationError, match="ít nhất"):
        fc.calibrate_fisheye(detected[:5], SPEC, SIZE)


def test_woodscape_conversion_reproduces_opencv_projection_within_the_reported_error():
    block = fc.woodscape_intrinsics(TRUE_K, TRUE_D, SIZE)
    assert block["ok"] and block["monotonic"] and block["theta_max_source"] == "image_corners"
    true_corner_theta = max(fc.field_of_view(TRUE_K, TRUE_D, SIZE)["theta_image_corners_deg"])
    assert block["theta_max_deg"] == pytest.approx(true_corner_theta, abs=0.02)
    assert block["aspect_ratio"] == pytest.approx(349.2 / 351.0)
    assert block["cx_offset"] == pytest.approx(324.3 - 319.5) and block["cy_offset"] == pytest.approx(236.8 - 239.5)
    assert block["max_fit_error_px"] < 0.05
    # lặp Lawson phải thắng bình phương tối thiểu thường về sai số LỚN NHẤT (0,035 so với 0,077 px trên camera này)
    th = np.linspace(0, math.radians(block["theta_max_deg"]), 2001)
    A = np.column_stack([th, th ** 2, th ** 3, th ** 4])
    target = TRUE_K[0, 0] * fc.theta_d(th, TRUE_D)
    plain = np.abs(A @ np.linalg.lstsq(A, target, rcond=None)[0] - target).max()
    assert block["max_fit_error_px"] < 0.7 * plain
    intr = fc.intrinsics_from_block(block)
    rng = np.random.default_rng(11)
    theta = rng.uniform(0, intr.theta_max, 5000)
    phi = rng.uniform(0, 2 * math.pi, 5000)
    pts = np.column_stack([np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)]) * rng.uniform(0.2, 3, (5000, 1))
    uv = cv2.fisheye.projectPoints(pts.reshape(1, -1, 3), np.zeros(3), np.zeros(3), TRUE_K, TRUE_D.reshape(4, 1))[0].reshape(-1, 2)
    u, v, valid = intr.project(pts)
    assert valid.mean() > 0.5
    diff = np.hypot(u[valid] - uv[valid, 0], v[valid] - uv[valid, 1])
    assert diff.max() <= block["max_fit_error_px"] + 1e-6
    # mọi điểm ảnh trong ảnh đều nghịch đảo được (theta_max phủ tới góc ảnh), và khớp tia của OpenCV
    uu, vv = np.meshgrid(np.linspace(0, 639, 17), np.linspace(0, 479, 13))
    rays = intr.unproject(uu.ravel(), vv.ravel())
    assert np.all(np.isfinite(rays))
    cv_rays = fc.pixel_rays(uu.ravel(), vv.ravel(), TRUE_K, TRUE_D)
    ang = np.degrees(np.arccos(np.clip(np.sum(rays * cv_rays, axis=1), -1, 1)))
    assert ang.max() < 0.05
    # ngưỡng chặt hơn sai số thật: bị cờ không đạt, và load_intrinsics từ chối
    strict = fc.woodscape_intrinsics(TRUE_K, TRUE_D, SIZE, max_error_px=1e-4)
    assert not strict["ok"] and "sai số khớp" in strict["reason"]


def test_calibrated_result_converts_and_passes_the_projection_check():
    _, calib = _calibrated()
    record = fc.calibration_record(calib, SPEC, port=3, square_mm_measured=25.0)
    ws = record["woodscape_intrinsic"]
    assert ws["ok"] and ws["max_fit_error_px"] <= fc.FIT_MAX_ERROR_PX
    assert ws["projection_check_max_px"] <= ws["max_fit_error_px"] + 1e-6


def test_undistortion_straightens_board_rows():
    _, views = synthetic_set()

    def bow(rows_xy):
        """Độ cong lớn nhất của một hàng góc: độ lệch khỏi đường thẳng khớp / chiều dài hàng."""
        worst = 0.0
        for row in rows_xy:                                                  # đường thẳng khớp theo PCA (hàng dốc cũng đúng)
            centred = row - row.mean(axis=0)
            normal = np.linalg.svd(centred)[2][-1]
            length = np.linalg.norm(row[-1] - row[0])
            worst = max(worst, np.abs(centred @ normal).max() / length)
        return worst
    detected = [fc.detect_corners(v[0], SPEC).corners.reshape(6, 9, 2) for v in views]
    k = int(np.argmax([bow(c) for c in detected]))                         # ảnh có hàng góc cong nhất
    corners, image = detected[k], views[k][0]
    map1, map2, P = fc.undistort_maps(TRUE_K, TRUE_D, SIZE, balance=0.5)
    und = cv2.fisheye.undistortPoints(corners.reshape(-1, 1, 2).astype(np.float64), TRUE_K, TRUE_D.reshape(4, 1), P=P)
    before, after = bow(corners), bow(und.reshape(6, 9, 2))
    assert before > 0.015 and after < before / 5
    out = fc.undistort_image(image, TRUE_K, TRUE_D, maps=(map1, map2, P))
    assert out.shape == image.shape and out.mean() > 20
    # ảnh nắn cũng thẳng: dò lại bảng trên ảnh nắn, hàng góc gần như thẳng
    again = fc.detect_corners(out, SPEC)
    assert again.found and bow(again.corners.reshape(6, 9, 2)) < before / 3


# ---- tệp, dòng lệnh -------------------------------------------------------------------------------------------------
def test_default_output_path_is_keyed_by_hub_port_and_does_not_overwrite_other_modes():
    assert fc.default_output_path(2, (640, 480)).as_posix() == "calibration/cam_p2.json"
    assert fc.default_output_path(2, (1280, 720)).as_posix() == "calibration/cam_p2_1280x720.json"


def test_cli_calibrate_and_check_on_a_unicode_folder(tmp_path, capsys):
    from tests.test_truncated_frames import truncate

    _, views = synthetic_set()
    folder = tmp_path / "ảnh hiệu chuẩn"
    folder.mkdir()
    for k, (image, _, _) in enumerate(views):
        assert fc.write_image(folder / f"cap_{k:03d}.png", image)
    assert fc.write_image(folder / "cap_999_hong.png", truncate(views[0][0], 240))
    out = tmp_path / "kết quả" / "cam_p2.json"
    code = fc.main(["calibrate", "--images", str(folder), "--cols", "9", "--rows", "6", "--square-mm", "25.0",
                    "--port", "2", "--out", str(out)])
    text = capsys.readouterr().out
    assert code == 0, text
    assert "cap_999_hong.png: khung bị cắt cụt" in text
    record = fc.load_calibration(out)
    assert record["camera"]["hub_port"] == 2 and record["image_size"] == [640, 480]
    assert record["extrinsic"] is None and record["rig"] is None and "Chưa gắn lên rig" in record["note"]
    assert record["square_mm_measured"] == 25.0 and record["board"]["square_mm"] == 25.0
    assert record["n_images_used"] >= 16 and record["rms_px"] < 0.3
    assert record["software"]["opencv"] == cv2.__version__ and record["created_local"]
    assert record["coverage"]["fraction"] >= 0.9 and record["woodscape_intrinsic"]["ok"]
    assert record["acceptance"]["status"].startswith("đề xuất")
    assert all("quality" in v for v in record["views"])
    intr = fc.load_intrinsics(out, width=640, height=480)
    assert intr.width == 640 and intr.theta_max == pytest.approx(math.radians(record["woodscape_intrinsic"]["theta_max_deg"]))
    with pytest.raises(ValueError, match="không dùng được"):
        fc.load_intrinsics(out, width=1280, height=720)
    preview = tmp_path / "xem trước.jpg"
    assert fc.main(["check", str(out), "--image", str(folder / "cap_000.png"), "--preview", str(preview)]) == 0
    text = capsys.readouterr().out
    assert "cổng hub 2" in text and "RMS" in text and "Chưa gắn lên rig" in text
    shown = cv2.imdecode(np.fromfile(str(preview), np.uint8), cv2.IMREAD_COLOR)
    assert shown.shape == (480, 1280, 3)
    bogus = tmp_path / "khác.json"
    bogus.write_text(json.dumps({"format": "khác"}), encoding="utf-8")
    assert fc.main(["check", str(bogus)]) == 2


def test_record_marks_unconfirmed_square_size_and_failed_conversion(tmp_path):
    _, calib = _calibrated()
    record = fc.calibration_record(calib, SPEC, port=1)
    assert record["square_mm_measured"] is None and "CHƯA khai cỡ ô" in fc.summary_text(record)
    record["woodscape_intrinsic"]["ok"] = False
    record["woodscape_intrinsic"]["reason"] = "thử"
    path = fc.save_calibration(tmp_path / "cam_p1.json", record)
    with pytest.raises(ValueError, match="không đạt"):
        fc.load_intrinsics(path)


# ---- chuyển đổi trên KẾT QUẢ hiệu chuẩn, tiêu chí chấp nhận ---------------------------------------------------------
def test_calibrated_conversion_unprojects_every_image_pixel(tmp_path):
    """K, D tìm được (không phải TRUE_K): nghiệm minimax hụt ở đầu đoạn, ρ_poly(θ_góc) nhỏ hơn bán kính góc (0, 479) ~0,016
    px — trước khi sửa, điểm ảnh đó ra NaN. theta_max phải được nâng vừa đủ; kiểm cả qua tệp và load_intrinsics."""
    _, calib = _calibrated()
    block = fc.woodscape_intrinsics(calib.K, calib.D, SIZE)
    assert block["ok"] and block["corners_invertible"] and block["theta_max_source"] == "image_corners"
    # trường hợp này đúng là cần nâng: dừng ở θ góc ảnh thì góc (0, 479) không nghịch đảo được
    at_corner = fc.intrinsics_from_block({**block, "theta_max_deg": block["theta_image_corner_deg"]})
    assert not np.all(np.isfinite(at_corner.unproject(np.array([0.0]), np.array([479.0]))))
    assert 0 < block["theta_max_raise_deg"] < 0.05
    assert block["theta_max_deg"] == pytest.approx(block["theta_image_corner_deg"] + block["theta_max_raise_deg"], abs=1e-4)
    record = fc.calibration_record(calib, SPEC, port=3, square_mm_measured=25.0)
    path = fc.save_calibration(tmp_path / "hiệu chuẩn" / "cam_p3.json", record)
    for intr in (fc.intrinsics_from_block(block), fc.load_intrinsics(path, width=640, height=480)):
        corners = np.array([[0, 0], [639, 0], [0, 479], [639, 479]], float)
        assert np.all(np.isfinite(intr.unproject(corners[:, 0], corners[:, 1])))
        uu, vv = np.meshgrid(np.arange(640), np.arange(480))
        rays = intr.unproject(uu.ravel(), vv.ravel())
        assert np.all(np.isfinite(rays))
        cv_rays = fc.pixel_rays(uu.ravel(), vv.ravel(), calib.K, calib.D)
        assert np.degrees(np.arccos(np.clip(np.sum(rays * cv_rays, 1), -1, 1))).max() < 0.05
    # sai số khớp báo cáo là trên đoạn ĐÃ nâng
    th_max = math.radians(block["theta_max_deg"])
    assert block["max_fit_error_px"] == pytest.approx(fc.radial_poly_error(calib.K, calib.D, [block[f"k{i}"] for i in
                                                                                              range(1, 5)], th_max)[0], abs=1e-4)
    # theta_max cho trước không phủ tới góc ảnh: khớp tốt, đơn điệu, nhưng góc ảnh ra NaN → không ok
    short = fc.woodscape_intrinsics(TRUE_K, TRUE_D, SIZE, theta_max=math.radians(60.0))
    assert short["monotonic"] and short["max_fit_error_px"] < 0.05 and short["theta_max_source"] == "given"
    assert not short["corners_invertible"] and not short["ok"] and "góc ảnh không nghịch đảo được" in short["reason"]


def _good_record():
    _, calib = _calibrated()
    return calib, fc.calibration_record(calib, SPEC, port=3, square_mm_measured=25.0)


def test_acceptance_fails_when_the_conversion_is_refused_even_with_a_small_fit_error():
    calib, record = _good_record()
    cov = record["coverage"]
    good = fc.acceptance(calib, cov, fc.woodscape_intrinsics(TRUE_K, TRUE_D, SIZE))
    assert good["all_pass"] is True
    # D gập lại trước góc ảnh: sai số khớp chỉ ~0,29 px (< 0,5) nhưng khối không ok, load_intrinsics sẽ từ chối
    ws = fc.woodscape_intrinsics(TRUE_K, np.array([-0.0958, -0.0376, 0.0171, -0.0047]), SIZE)
    assert not ws["ok"] and ws["max_fit_error_px"] <= fc.FIT_MAX_ERROR_PX and ws["reason"]
    acc = fc.acceptance(calib, cov, ws)
    checks = {c["key"]: c for c in acc["checks"]}
    assert checks["fit_error_px"]["pass"] is False and acc["all_pass"] is False
    assert [k for k, c in checks.items() if not c["pass"]] == ["fit_error_px"]            # chỉ tiêu chí này hỏng
    assert "chuyển đổi KHÔNG ĐẠT" in checks["fit_error_px"]["label"] and ws["reason"] in checks["fit_error_px"]["label"]
    text = fc.summary_text({**record, "woodscape_intrinsic": ws, "acceptance": acc})
    assert "CHƯA  sai số chuyển sang mô hình dự án (px) — chuyển đổi KHÔNG ĐẠT" in text


def _true_tilt_deg(R, t):
    """Góc nghiêng thật của bảng (pháp tuyến so với đường nhìn tới tâm bảng) từ tư thế dựng ảnh tổng hợp."""
    centre = R @ (np.array([(SPEC.cols - 1) / 2, (SPEC.rows - 1) / 2, 0.0]) * SPEC.square_mm / 1000.0) + np.ravel(t)
    return math.degrees(math.acos(min(1.0, abs(R[:, 2] @ centre) / np.linalg.norm(centre))))


def test_acceptance_checks_use_the_real_statistics_and_fail_exactly_the_violated_criterion():
    _, views = synthetic_set()
    calib, record = _good_record()
    acc = record["acceptance"]
    checks = {c["key"]: c for c in acc["checks"]}
    assert acc["all_pass"] is True and all(c["pass"] for c in checks.values())
    assert checks["rms_px"]["value"] == pytest.approx(calib.rms_px, abs=1e-4)
    assert checks["max_view_rms_px"]["value"] == pytest.approx(calib.max_view_rms_px, abs=1e-4)
    assert checks["images"]["value"] == calib.n_used
    assert checks["coverage"]["value"] == record["coverage"]["fraction"]
    assert checks["corner_blocks"]["value"] == 4
    assert checks["fit_error_px"]["value"] == record["woodscape_intrinsic"]["max_fit_error_px"]
    # độ nghiêng từng ảnh khớp tư thế thật đã dựng ảnh
    for v in calib.views:
        R, t = views[int(v.name[1:])][1:]
        assert v.tilt_deg == pytest.approx(_true_tilt_deg(R, t), abs=0.5), v.name
    tilted = sum(1 for v in calib.views if v.used and v.tilt_deg >= fc.ACCEPT["tilt_deg"])
    assert checks["tilted_images"]["value"] == tilted and 4 <= tilted < calib.n_used
    # siết một ngưỡng quá giá trị thật: hỏng ĐÚNG tiêu chí đó (cả chiều <= lẫn >=)
    for key, thr in (("rms_px", 0.01), ("max_view_rms_px", 0.01), ("images", calib.n_used + 1),
                     ("tilted_images", tilted + 1), ("fit_error_px", 1e-5)):
        strict = fc.acceptance(calib, record["coverage"], record["woodscape_intrinsic"], {key: thr})
        assert strict["all_pass"] is False and [c["key"] for c in strict["checks"] if not c["pass"]] == [key]
    edge = fc.acceptance(calib, record["coverage"], record["woodscape_intrinsic"], {"images": calib.n_used})
    assert edge["all_pass"] is True                                       # ngưỡng bằng giá trị: đạt
    text = fc.summary_text({**record, "acceptance": fc.acceptance(calib, record["coverage"],
                                                                 record["woodscape_intrinsic"], {"rms_px": 0.01})})
    assert "CHƯA  RMS chiếu lại toàn bộ" in text and "đạt   số ảnh dùng" in text
    # θ lớn nhất đã thấy bảng: theo mô hình thật ~59,8°, nhỏ hơn θ ở góc ảnh (phần ngoại suy)
    fov = record["field_of_view_deg"]
    c = np.vstack(calib.used_corners)
    true_theta = math.degrees(float(np.nanmax(fc.pixel_theta(c[:, 0], c[:, 1], TRUE_K, TRUE_D))))
    assert fov["theta_observed_max_deg"] == pytest.approx(true_theta, abs=0.2)
    assert fov["theta_observed_max_deg"] < min(fov["theta_image_corners_deg"])
