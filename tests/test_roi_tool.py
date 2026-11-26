"""Mặt nạ ROI cho camera dự án và giao diện roi_app (thẻ ROI + thẻ Ngoại tham), chạy offscreen — chỉ ảnh TỔNG HỢP.

ROI: đa giác → PNG 0/255 ở cỡ gốc, đúng tên/thư mục mà `bev.load_rig(..., roi_dir=...)` đọc; đọc lại trùng từng pixel;
không ghi đè im lặng; pixel ngoài ROI không bao giờ thành FREE trong BEV. Giao diện: bấm chuột vẽ đa giác, lưu, mở lại;
thẻ ngoại tham đi trọn luồng (nạp nội tham, thêm lần đặt, tính, ghi tệp rig) trên ảnh bảng tổng hợp của
tests/test_extrinsics_calib.py; camera sống là nguồn giả (không mở thiết bị thật).
"""
import dataclasses
from datetime import datetime
import json
import os
from pathlib import Path
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from autopark.perception import bev  # noqa: E402
from autopark.perception import extrinsics_calib as ec  # noqa: E402
from autopark.perception import fisheye_calib as fc  # noqa: E402
from autopark.perception import roi_tool as rt  # noqa: E402
from autopark.perception.calib_board import BoardSpec  # noqa: E402
from autopark.perception.costmap import FREE  # noqa: E402
from autopark.ui.roi_app import ExtrinsicsRoiWindow  # noqa: E402
from autopark.video.sources import _frame  # noqa: E402
from tests.test_extrinsics_calib import SPEC, TRUE_R, TRUE_T, board_image, measured, write_intrinsics  # noqa: E402

W, H = 640, 480
BODY = [(0, 400), (639, 400), (639, 479), (0, 479)]          # "thân xe" ở đáy ảnh


def spec_with(polys, margin=0, port=1):
    return rt.RoiSpec(port, W, H, [rt.RoiPolygon(p, m) for p, m in polys], margin)


# ---- dựng mặt nạ ----------------------------------------------------------------------------------------------------
def test_rasterize_exclude_include_and_margin():
    m = rt.rasterize(spec_with([(BODY, "exclude")]))
    assert m.dtype == np.uint8 and m.shape == (H, W) and set(np.unique(m)) == {0, 255}
    assert (m[401:, :] == 0).all() and (m[:399, :] == 255).all()
    # nới vùng loại đúng margin_px điểm ảnh
    m3 = rt.rasterize(spec_with([(BODY, "exclude")], margin=3))
    assert (m3[397:, :] == 0).all() and (m3[:396, :] == 255).all()
    # chỉ có đa giác giữ: ngoài nó là loại
    box = [(100, 100), (300, 100), (300, 200), (100, 200)]
    mi = rt.rasterize(spec_with([(box, "include")]))
    assert mi[150, 200] == 255 and mi[50, 50] == 0 and mi[300, 200] == 0
    # giữ + loại chồng nhau: loại thắng
    hole = [(150, 120), (250, 120), (250, 180), (150, 180)]
    mb = rt.rasterize(spec_with([(box, "include"), (hole, "exclude")]))
    assert mb[150, 200] == 0 and mb[110, 110] == 255
    with pytest.raises(rt.RoiError, match="ít nhất 3"):
        rt.rasterize(spec_with([([(0, 0), (10, 10)], "exclude")]))
    with pytest.raises(rt.RoiError, match="không hợp lệ"):
        rt.RoiPolygon(BODY, "xoa")


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def test_overlapping_polygons_of_one_kind_are_a_union():
    """Vùng loại / vùng giữ là HỢP các đa giác cùng kiểu: chỗ chồng nhau không bị đục lỗ (một lần fillPoly nhiều đa giác
    tô theo chẵn-lẻ — lỗi cũ: chỗ chồng nhau của hai đa giác loại thành DÙNG ĐƯỢC)."""
    small = lambda polys: rt.rasterize(rt.RoiSpec(1, 100, 100, [rt.RoiPolygon(p, m) for p, m in polys], 0))
    ex = small([(rect(10, 10, 60, 60), "exclude"), (rect(40, 40, 90, 90), "exclude")])
    assert ex[50, 50] == 0 and ex[20, 20] == 0 and ex[80, 80] == 0 and ex[5, 95] == 255
    inc = small([(rect(10, 10, 60, 60), "include"), (rect(40, 40, 90, 90), "include")])
    assert inc[50, 50] == 255 and inc[20, 20] == 255 and inc[80, 80] == 255 and inc[5, 95] == 0
    # "bánh xe" vẽ lồng trong "thân xe": cả thân xe vẫn bị loại (lề mặc định 2 px)
    m = rt.rasterize(nested_body())
    assert (m[378:, :] == 0).all() and (m[:377, :] == 255).all()


def nested_body():
    return rt.RoiSpec(1, W, H, [rt.RoiPolygon(rect(0, 380, 639, 479), "exclude", "thân xe"),
                                rt.RoiPolygon(rect(100, 400, 200, 470), "exclude", "bánh")])


def test_nested_exclude_polygons_are_saved_fully_excluded(tmp_path):
    res = rt.save_roi(nested_body(), tmp_path)
    saved = bev.read_gray(res["png"])
    assert (saved[378:, :] == 0).all() and saved[435, 150] == 0
    report = rt.check_mask(saved, (W, H))
    assert report["ok"] and report["usable_components"] == 1 and not report["warnings"]


def test_save_round_trip_is_exactly_what_bev_reads(tmp_path):
    folder = tmp_path / "cấu hình" / "roi"
    spec = spec_with([(BODY, "exclude"), ([(0, 0), (80, 0), (0, 60)], "exclude")], margin=2)
    image = board_image(0)
    out = rt.save_roi(spec, folder, image=image)
    assert out["png"] == folder / "roi_p1.png" and out["preview"].exists() and not out["backups"]
    expect = rt.rasterize(spec)
    assert np.array_equal(bev.read_gray(out["png"]), expect)
    again = rt.load_spec(out["json"])
    assert np.array_equal(rt.rasterize(again), expect) and again.margin_px == 2 and len(again.polygons) == 2
    # đúng thứ bev.load_rig dùng (cần nội tham cổng 1 cỡ 640×480)
    cal = tmp_path / "calibration"
    write_intrinsics(cal)
    cameras, _, _ = bev.load_rig(ec.DEFAULT_BASE, cal, {1: (W, H)}, roi_dir=folder)
    assert np.array_equal(cameras["p1"].roi, expect) and cameras["p1"].roi_source == str(folder / "roi_p1.png")
    # cỡ sai: BEV từ chối camera này
    small = rt.RoiSpec(1, 320, 240, [rt.RoiPolygon([(0, 200), (319, 200), (319, 239)])])
    rt.save_roi(small, tmp_path / "nho")
    with pytest.raises(bev.RigConfigError, match="ROI"):
        bev.load_rig(ec.DEFAULT_BASE, cal, {1: (W, H)}, roi_dir=tmp_path / "nho")


def test_roi_is_never_overwritten_silently(tmp_path):
    a = spec_with([(BODY, "exclude")])
    b = spec_with([([(0, 300), (639, 300), (639, 479), (0, 479)], "exclude")])
    rt.save_roi(a, tmp_path)
    first = (tmp_path / "roi_p1.png").read_bytes()
    with pytest.raises(rt.RoiError, match="không ghi đè im lặng"):
        rt.save_roi(b, tmp_path)
    assert (tmp_path / "roi_p1.png").read_bytes() == first
    res = rt.save_roi(b, tmp_path, overwrite=True)
    assert len(res["backups"]) == 2
    kept = [Path(p) for p in res["backups"] if p.endswith(".png")]
    assert kept and kept[0].read_bytes() == first and kept[0].name.startswith("roi_p1.bak_")
    assert np.array_equal(bev.read_gray(tmp_path / "roi_p1.png"), rt.rasterize(b))
    with pytest.raises(rt.RoiError, match="loại HẾT"):
        rt.save_roi(spec_with([([(0, 0), (639, 0), (639, 479), (0, 479)], "exclude")], port=2), tmp_path)
    assert not (tmp_path / "roi_p2.png").exists()
    with pytest.raises(rt.RoiError, match="khác cỡ"):
        rt.save_roi(spec_with([(BODY, "exclude")], port=3), tmp_path, image=np.zeros((240, 320, 3), np.uint8))


def test_two_roi_overwrites_in_the_same_instant_keep_every_old_version(tmp_path, monkeypatch):
    """Bấm đúp 'Lưu ROI' (có tích ghi đè): hai lần lưu trong cùng một thời điểm không được đè bản sao lưu của nhau."""
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 24, 23, 59, 59, 123456)

    monkeypatch.setattr(rt, "datetime", Frozen)
    versions = [spec_with([(rect(0, y, 639, 479), "exclude")]) for y in (400, 300, 200)]
    rt.save_roi(versions[0], tmp_path, image=board_image(0))
    first = {k: (tmp_path / f"roi_p1{s}").read_bytes() for k, s in (("png", ".png"), ("json", ".json"))}
    r2 = rt.save_roi(versions[1], tmp_path, image=board_image(0), overwrite=True)
    second = {k: (tmp_path / f"roi_p1{s}").read_bytes() for k, s in (("png", ".png"), ("json", ".json"))}
    r3 = rt.save_roi(versions[2], tmp_path, image=board_image(0), overwrite=True)
    assert not set(r2["backups"]) & set(r3["backups"]) and len(r2["backups"]) == len(r3["backups"]) == 3
    for res, expect in ((r2, first), (r3, second)):
        by_ext = {Path(p).suffix: Path(p).read_bytes() for p in res["backups"]}
        assert by_ext[".png"] == expect["png"] and by_ext[".json"] == expect["json"]
    assert len(list(tmp_path.glob("roi_p1*.bak_*"))) == 6
    assert np.array_equal(bev.read_gray(tmp_path / "roi_p1.png"), rt.rasterize(versions[2]))


def test_check_mask_reports_problems():
    good = rt.rasterize(spec_with([(BODY, "exclude")]))
    r = rt.check_mask(good, (W, H))
    assert r["ok"] and not r["warnings"] and r["usable_components"] == 1
    assert r["usable_fraction"] == pytest.approx(400 / 480, abs=0.01)
    assert not rt.check_mask(good, (1280, 720))["ok"]
    assert any("không loại pixel nào" in w for w in rt.check_mask(np.full((H, W), 255, np.uint8))["warnings"])
    grey = good.copy()
    grey[0, 0] = 128
    assert any("khác 0/255" in w for w in rt.check_mask(grey)["warnings"])
    split = good.copy()
    split[:, 300:340] = 0
    assert any("mảnh rời" in w for w in rt.check_mask(split)["warnings"])
    assert not rt.check_mask(np.zeros((H, W), np.uint8))["ok"]
    assert not rt.check_mask(np.dstack([good] * 3))["ok"]


def test_cli_check_and_build(tmp_path, capsys):
    spec = spec_with([(BODY, "exclude")])
    res = rt.save_roi(spec, tmp_path / "roi")
    img_path = tmp_path / "cam_p1.png"
    fc.write_image(img_path, board_image(0))
    assert rt.main(["check", str(res["png"]), "--image", str(img_path)]) == 0
    assert (tmp_path / "roi" / "roi_p1_kiem.jpg").exists() and "dùng được với bev" in capsys.readouterr().out
    assert rt.main(["check", str(res["png"]), "--size", "1280x720"]) == 2
    assert "khác cỡ khung camera" in capsys.readouterr().out
    assert rt.main(["build", str(res["json"]), "--out-dir", str(tmp_path / "khac")]) == 0
    assert np.array_equal(bev.read_gray(tmp_path / "khac" / "roi_p1.png"), rt.rasterize(spec))
    assert rt.main(["build", str(res["json"])]) == 2
    assert "không ghi đè im lặng" in capsys.readouterr().err
    assert rt.main(["build", str(res["json"]), "--overwrite"]) == 0


def test_pixels_outside_roi_never_make_free_cells():
    """Mọi pixel báo FREE (p = 0); ROI loại nửa dưới ảnh camera trước: không ô FREE nào chỉ được thấy qua pixel bị loại."""
    cameras, _ = bev.synthetic_rig()
    cam = cameras["p1"]
    grid = bev.GridSpec(*bev.RIG_GRID)
    prob = np.zeros((480, 640), np.float32)
    free_all = bev.build_bev({"p1": prob}, {"p1": cam}, grid).states == FREE
    roi = rt.rasterize(spec_with([([(0, 240), (639, 240), (639, 479), (0, 479)], "exclude")]))
    with_roi = dataclasses.replace(cam, roi=roi)
    result = bev.build_bev({"p1": prob}, {"p1": with_roi}, grid)
    free = result.states == FREE
    assert free.sum() < free_all.sum() and free.sum() > 0
    gx, gy = grid.centers()
    u, v, valid = with_roi.calibration.ground_to_pixel(np.column_stack([gx[free], gy[free]]))
    assert valid.all() and (v < 240 + 2).all()          # tâm ô FREE rơi vào phần ảnh còn giữ (nửa trên)


# ---- giao diện --------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(app, seconds, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.01)
    app.processEvents()
    return until() if until is not None else None


def make_window(tmp_path, **kw):
    cal = tmp_path / "calibration"
    write_intrinsics(cal)
    args = dict(port=1, spec=SPEC, calibration_dir=cal, rig_out=tmp_path / "rig" / "camera_rig_extrinsics_v1.json",
                roi_dir=tmp_path / "roi dự án", runs_dir=tmp_path / "runs" / "extrinsics",
                roi_runs_dir=tmp_path / "runs" / "roi")
    args.update(kw)
    w = ExtrinsicsRoiWindow(**args)
    w.resize(1500, 900)
    w.show()
    return w


def click(app, canvas, x, y, button=Qt.MouseButton.LeftButton):
    p = canvas.image_to_widget(x, y)
    QTest.mouseClick(canvas, button, Qt.KeyboardModifier.NoModifier, QPoint(round(p.x()), round(p.y())))
    app.processEvents()


def test_gui_roi_draw_save_reload_and_overwrite(qapp, tmp_path):
    img_path = tmp_path / "ảnh" / "cam_p1.png"
    img_path.parent.mkdir()
    fc.write_image(img_path, board_image(1))
    w = make_window(tmp_path)
    try:
        assert w.load_image_file(img_path)
        w.tabs.setCurrentIndex(1)
        pump(qapp, 0.2)
        canvas = w.roi_canvas
        # toạ độ chuột ↔ điểm ảnh khứ hồi
        back = canvas.widget_to_image(canvas.image_to_widget(123.0, 456.0))
        assert back == pytest.approx((123.0, 456.0), abs=1e-6)
        pts = [(0, 380), (639, 380), (639, 479), (0, 479)]
        click(qapp, canvas, 10, 10)
        canvas.setFocus()
        QTest.keyClick(canvas, Qt.Key.Key_Backspace)             # bỏ đỉnh nhấn nhầm
        assert w.current_pts == []
        for x, y in pts[:3]:
            click(qapp, canvas, x, y)
        QTest.keyClick(canvas, Qt.Key.Key_Escape)                # huỷ
        assert w.current_pts == [] and not w.polygons
        for x, y in pts:
            click(qapp, canvas, x, y)
        assert len(w.current_pts) == 4
        click(qapp, canvas, 320, 240, Qt.MouseButton.RightButton)  # chuột phải đóng đa giác
        assert len(w.polygons) == 1 and w.polygons[0].mode == "exclude"
        got = np.array(w.polygons[0].points)
        assert np.abs(got - np.array(pts)).max() < 1.0            # sai số một lần làm tròn toạ độ chuột
        w.margin_spin.setValue(0)
        assert "dùng được" in w.roi_report.text()
        res = w.save_roi()
        assert res is not None and res["png"] == tmp_path / "roi dự án" / "roi_p1.png"
        mask = bev.read_gray(res["png"])
        assert mask.shape == (480, 640) and (mask[390:, :] == 0).all() and (mask[:370, :] == 255).all()
        assert json.loads(res["json"].read_text(encoding="utf-8"))["source_image"] == str(img_path)
        # lưu lần hai không tích ghi đè: từ chối, tệp giữ nguyên
        before = res["png"].read_bytes()
        click(qapp, canvas, 0, 0)
        click(qapp, canvas, 100, 0)
        click(qapp, canvas, 0, 100)
        QTest.keyClick(canvas, Qt.Key.Key_Return)
        assert len(w.polygons) == 2
        assert w.save_roi() is None and "không ghi đè im lặng" in w.message_label.text()
        assert res["png"].read_bytes() == before
        w.chk_roi_overwrite.setChecked(True)
        res2 = w.save_roi()
        assert res2 is not None and res2["backups"] and bev.read_gray(res2["png"])[5, 5] == 0
        # mở lại: đa giác trở về
        w.polygons = []
        assert w.load_roi()
        assert len(w.polygons) == 2 and w.polygons[0].mode == "exclude"
        # đổi cổng: bỏ ảnh + đa giác của camera trước
        w.port_box.setCurrentIndex(w.port_box.findData(2))
        assert w.port == 2 and w.image is None and not w.polygons and "cổng trước" in w.message
    finally:
        w.close()


def test_gui_extrinsics_full_flow_and_session_replays_on_cli(qapp, tmp_path, capsys):
    snaps = tmp_path / "rig_snapshots"
    folders = []
    for k in range(3):
        f = snaps / f"2026092{k}_101010_000"
        f.mkdir(parents=True)
        fc.write_image(f / "cam_p1.png", board_image(k))
        (f / "meta.json").write_text("{}", encoding="utf-8")
        folders.append(f)
    w = make_window(tmp_path)
    try:
        assert w.intr is not None and "TỔNG HỢP" in w.intr_label.text()      # nội tham của test là camera ảo
        w.square_spin.setValue(30.0)
        w.chk_square.setChecked(True)
        for k, f in enumerate(folders):
            assert w.load_snapshot(f)
            pump(qapp, 0.05)
            assert w.ext_note == ""                                  # bảng thấy và đã đánh số O/A/B/C
            m = measured(k, names=("O", "A", "B", "C")).points_dict()
            w.set_points(m, use_b=True, use_c=(k != 1))
            assert w.add_placement(), w.message
        assert w.placement_list.count() == 3 and "RMS" in w.placement_list.item(0).text()
        assert set(w.inputs[0].placement.points_dict()) == {"O", "A", "B", "C"}
        assert set(w.inputs[1].placement.points_dict()) == {"O", "A", "B"}
        assert not w.btn_write.isEnabled()
        res = w.solve()
        assert res is not None and res.ok and "ĐẠT" in w.results.text() and w.btn_write.isEnabled()
        assert np.linalg.norm(res.t_cv - TRUE_T) < 0.002 and ec.rotation_angle_deg(res.R_cv, TRUE_R) < 0.1
        assert w.placement_list.currentRow() == 0                   # ảnh hiện lưới hệ xe của lần đặt 1
        path = w.write_rig()
        assert path is not None and path.exists(), w.message
        rig = bev.load_rig_extrinsics(path)
        assert rig.cameras[1].measured and np.allclose(rig.cameras[1].extrinsics.translation, res.t_cv, atol=1e-4)
        session = w.last_session
        prov = json.loads(path.read_text(encoding="utf-8"))["cameras"]["1"]["provenance"]
        assert all(Path(p["image"]).parent == session for p in prov["placements"])
        assert (session / "dat_bang_p1.json").exists() and (session / "ket_qua.json").exists()
        # ghi lần hai không tích ghi đè: từ chối
        assert w.write_rig() is None and "không ghi đè im lặng" in w.message
        # phiên đã lưu chạy lại được bằng dòng lệnh và cho cùng tư thế
        assert json.loads(path.read_text(encoding="utf-8"))["synthetic"] is True     # nhãn tổng hợp đi theo tệp
        out2 = tmp_path / "rig2.json"
        assert ec.main(["solve", "--placements", str(session / "dat_bang_p1.json"), "--out", str(out2),
                        "--allow-synthetic", "--report", str(tmp_path / "bc")]) == 0
        again = bev.load_rig_extrinsics(out2).cameras[1].extrinsics
        assert np.allclose(again.translation, res.t_cv, atol=1e-5)
        # thay đổi danh sách sau khi tính: phải tính lại mới ghi được
        w.placement_list.setCurrentRow(2)
        w.remove_selected()
        w.chk_overwrite.setChecked(True)
        assert w.write_rig() is None and "Tính ngoại tham" in w.message
    finally:
        w.close()


def test_gui_extrinsics_refuses_without_intrinsics(qapp, tmp_path):
    img_path = tmp_path / "cam_p1.png"
    fc.write_image(img_path, board_image(0))
    w = make_window(tmp_path, calibration_dir=tmp_path / "khong_co")
    try:
        assert w.intr is None and "CHƯA CÓ NỘI THAM" in w.intr_label.text()
        assert w.load_image_file(img_path)
        assert "chưa biết góc nào là O" in w.message_label.text()
        w.set_points(measured(0).points_dict())
        assert not w.add_placement() and "chưa có nội tham" in w.message and not w.inputs
        assert w.solve() is None
    finally:
        w.close()


class FakeCamera:
    def __init__(self, image):
        self.image, self.n, self.closed = image, 0, False

    def read(self):
        time.sleep(0.01)
        self.n += 1
        return _frame("cam_p1", time.perf_counter(), f"fake#{self.n}", self.image)

    def close(self):
        self.closed = True


def test_gui_live_camera_is_a_fake_source_and_grab_freezes_a_frame(qapp, tmp_path):
    opened = []

    def factory(port, width, height):
        cam = FakeCamera(board_image(2))
        opened.append((port, width, height, cam))
        return cam

    w = make_window(tmp_path, open_camera=factory)
    try:
        assert w.chk_live.isEnabled() and not opened                 # không mở camera khi chưa bấm
        w.chk_live.setChecked(True)
        assert pump(qapp, 5, lambda: w.current_image()[0] is not None)
        assert opened[0][:3] == (1, 640, 480)
        w.set_points(measured(2).points_dict())
        assert w.add_placement() and w.inputs[0].image_path is None   # khung sống: chưa có tệp, lưu khi ghi phiên
        assert w.grab_live() and w.live_camera is None and opened[0][3].closed
        assert w.image is not None and w.image_source.startswith("khung sống")
        w.tabs.setCurrentIndex(1)
        for x, y in [(0, 420), (639, 420), (639, 479)]:
            click(qapp, w.roi_canvas, x, y)
        assert w.close_polygon()
        res = w.save_roi()
        assert res is not None
        src = json.loads(res["json"].read_text(encoding="utf-8"))["source_image"]
        assert Path(src).parent == tmp_path / "runs" / "roi" and Path(src).exists()
    finally:
        w.close()


def write_boards(tmp_path, ks=range(3)):
    folder = tmp_path / "ảnh bảng"
    folder.mkdir(exist_ok=True)
    paths = []
    for k in ks:
        fc.write_image(folder / f"dat_{k}.png", board_image(k))
        paths.append(folder / f"dat_{k}.png")
    return paths


def test_gui_board_spec_change_after_solve_blocks_write(qapp, tmp_path):
    """Đổi cỡ ô / 'Đã đo cỡ ô' / số góc SAU khi tính: kết quả cũ không được ghi; phiên lưu ghi đúng thông số đã dùng để
    tính và chạy lại bằng dòng lệnh cho cùng tư thế đã ghi."""
    w = make_window(tmp_path)
    try:
        w.chk_square.setChecked(True)
        for k, p in enumerate(write_boards(tmp_path)):
            assert w.load_image_file(p)
            w.set_points(measured(k).points_dict(), use_b=True)
            assert w.add_placement(), w.message
        rig = Path(w.out_edit.text())
        changes = ((lambda: w.square_spin.setValue(29.0), lambda: w.square_spin.setValue(30.0)),
                   (lambda: w.chk_square.setChecked(False), lambda: w.chk_square.setChecked(True)),
                   (lambda: w.cols_spin.setValue(8), lambda: w.cols_spin.setValue(9)))
        for change, undo in changes:
            res = w.solve()
            assert res is not None and res.ok and w.btn_write.isEnabled()
            change()
            assert not w.btn_write.isEnabled() and "Tính ngoại tham lại" in w.message
            assert w.write_rig() is None and "Tính ngoại tham" in w.message
            assert not rig.exists() and w.last_session is None
            undo()
            assert not w.btn_write.isEnabled()                       # đổi lại cũng phải tính lại
        assert all(a.used for a in w.analyses)                        # đã phân tích lại theo bảng 9×6 ô 30 mm
        # các lần đặt được phân tích lại ngay theo cỡ ô mới: 25 mm không khớp số đo thước của bảng 30 mm
        w.square_spin.setValue(25.0)
        assert all(not a.used and a.spec.square_mm == 25.0 for a in w.analyses)
        assert "không khớp cỡ bảng" in w.placement_list.item(0).text()
        w.square_spin.setValue(30.0)
        assert all(a.used and a.spec == SPEC for a in w.analyses) and "RMS" in w.placement_list.item(0).text()
        res = w.solve()
        path = w.write_rig()
        assert path is not None, w.message
        session = w.last_session
        rec = json.loads((session / "dat_bang_p1.json").read_text(encoding="utf-8"))
        prov = json.loads(path.read_text(encoding="utf-8"))["cameras"]["1"]["provenance"]
        assert rec["board"]["square_mm"] == prov["board"]["square_mm"] == 30.0
        assert rec["board"]["square_mm_measured"] is True and prov["board"]["square_mm_measured"] is True
        out2 = tmp_path / "rig_lai.json"
        assert ec.main(["solve", "--placements", str(session / "dat_bang_p1.json"), "--out", str(out2),
                        "--allow-synthetic", "--report", str(tmp_path / "bc")]) == 0
        assert np.allclose(bev.load_rig_extrinsics(out2).cameras[1].extrinsics.translation,
                           bev.load_rig_extrinsics(path).cameras[1].extrinsics.translation, atol=1e-5)
        # nạp lại nội tham sau khi tính: phải tính lại
        assert w.solve().ok and w.btn_write.isEnabled()
        assert w.load_intrinsics(w.intr_edit.text(), user=True)
        assert not w.btn_write.isEnabled() and w.write_rig() is None
        # mất nội tham rồi đổi số góc: không phân tích lại được — không vẽ nhãn theo bảng cũ, không lỗi
        assert not w.load_intrinsics(tmp_path / "khong_co" / "cam_p1.json", user=True)
        w.placement_list.setCurrentRow(0)
        w.cols_spin.setValue(7)
        assert w.ext_note.startswith("dat_01") and "chưa phân tích lại" in w.ext_note
    finally:
        w.close()


def test_gui_board_size_change_redetects_instead_of_reusing_old_corners(qapp, tmp_path):
    img_path = write_boards(tmp_path, [0])[0]
    w = make_window(tmp_path)
    try:
        assert w.load_image_file(img_path)
        assert w.ext_note == "" and w._orient_cache[0][0] == SPEC and w._orient_cache[1] is not None
        old = np.array(w._orient_cache[1])
        w.cols_spin.setValue(7)                          # 7 + 6 lẻ: bảng hợp lệ, nhưng không phải bảng trên ảnh
        w.tabs.setCurrentIndex(1)
        w.tabs.setCurrentIndex(0)                        # vẽ lại: trước đây ValueError (reshape 54 góc về 6×7)
        assert "7×6" in w.ext_note and w._orient_cache[0][0] == BoardSpec(7, 6, 30.0)
        w.cols_spin.setValue(6)
        w.rows_spin.setValue(9)                          # 6×9: cùng 54 góc — không được dùng lại góc đánh số 9×6
        w.refresh()
        assert w._orient_cache[0][0] == BoardSpec(6, 9, 30.0)
        assert w._orient_cache[1] is None or not np.array_equal(w._orient_cache[1], old)
        w.cols_spin.setValue(9)
        w.rows_spin.setValue(6)
        w.refresh()
        assert w.ext_note == "" and np.allclose(w._orient_cache[1], old)
    finally:
        w.close()


def test_gui_even_board_is_reported_not_raised(qapp, tmp_path):
    img_path = write_boards(tmp_path, [0])[0]
    w = make_window(tmp_path)
    try:
        assert w.load_image_file(img_path)
        w.set_points(measured(0).points_dict(), use_b=True)
        assert w.add_placement()
        w.rows_spin.setValue(5)                          # 9 + 5 chẵn: không xác định được góc O
        assert w.message.startswith("LỖI") and "cols + rows chẵn" in w.message
        assert w.solve() is None and w.result is None
        assert w.message.startswith("LỖI") and "cols + rows chẵn" in w.message
        assert w.message_label.text().startswith("LỖI")
        w.placement_list.setCurrentRow(0)
        assert w.ext_note.startswith("dat_01")
        w.rows_spin.setValue(6)
        w.min_spin.setValue(1)
        res = w.solve()
        assert res is not None and res.ok and not w.message.startswith("LỖI")
    finally:
        w.close()


def test_gui_roi_save_guards_and_intrinsics_follow_image_size(qapp, tmp_path):
    big = write_boards(tmp_path, [0])[0]
    small = tmp_path / "nho.png"
    fc.write_image(small, cv2.resize(board_image(0), (320, 240)))
    w = make_window(tmp_path)
    png = tmp_path / "roi dự án" / "roi_p1.png"
    try:
        assert w.load_image_file(big) and w.intr is not None
        w.tabs.setCurrentIndex(1)
        pump(qapp, 0.05)
        for x, y in [(0, 420), (639, 420), (639, 479)]:
            click(qapp, w.roi_canvas, x, y)
        assert w.save_roi() is None and "vẽ dở" in w.message and not png.exists()
        assert w.close_polygon() and w.save_roi() is not None and png.exists()
        # ảnh đổi cỡ: nội tham được nạp lại theo cỡ mới (chưa có tệp 320×240) — không giữ nội tham 640×480
        assert w.load_image_file(small)
        assert w.intr is None and "CHƯA CÓ NỘI THAM" in w.intr_label.text()
        # người dùng ép nội tham 640×480 cho ảnh 320×240: ROI bị từ chối (BEV sẽ từ chối camera này)
        assert w.load_intrinsics(tmp_path / "calibration" / "cam_p1.json", user=True)
        w.polygons = [rt.RoiPolygon(rect(0, 200, 319, 239))]
        w.chk_roi_overwrite.setChecked(True)
        before = png.read_bytes()
        assert w.save_roi() is None and "khác cỡ nội tham" in w.message and png.read_bytes() == before
    finally:
        w.close()


def test_gui_synthetic_intrinsics_never_default_to_configs(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "SYNTHETIC_FORBIDDEN_DIRS", (tmp_path / "configs",))
    w = make_window(tmp_path, rig_out=ec.DEFAULT_OUT)
    try:
        assert "TỔNG HỢP" in w.intr_label.text()
        assert Path(w.out_edit.text()) == tmp_path / ec.SYNTHETIC_RIG_NAME        # không còn là configs/rig/…_v1.json
        for k, p in enumerate(write_boards(tmp_path, [0, 1])):
            assert w.load_image_file(p)
            w.set_points(measured(k).points_dict(), use_b=True)
            assert w.add_placement()
        res = w.solve()
        assert res.ok and res.synthetic and "KHÔNG PHẢI SỐ ĐO" in w.message
        w.out_edit.setText(str(tmp_path / "configs" / "rig" / "camera_rig_extrinsics_v1.json"))
        assert w.write_rig() is None and "không bao giờ được ghi vào" in w.message
        assert not (tmp_path / "configs").exists()
        w.out_edit.setText(str(tmp_path / ec.SYNTHETIC_RIG_NAME))
        path = w.write_rig()
        assert path is not None and json.loads(path.read_text(encoding="utf-8"))["synthetic"] is True
        assert "bản cũ" not in w.message
        w.chk_overwrite.setChecked(True)
        w.base_edit.setText(str(path))
        assert w.write_rig() is not None and "bản cũ" in w.message
        path.unlink()                                    # tệp ra chưa có, còn bản sao lưu cũ: không báo nhầm "bản cũ"
        w.base_edit.setText(str(ec.DEFAULT_BASE))
        assert w.write_rig() is not None and "bản cũ" not in w.message
    finally:
        w.close()


def test_gui_live_camera_follows_board_size_changes(qapp, tmp_path):
    opened = []

    def factory(port, width, height):
        cam = FakeCamera(board_image(2))
        opened.append(cam)
        return cam

    w = make_window(tmp_path, open_camera=factory)
    try:
        w.chk_live.setChecked(True)
        assert pump(qapp, 5, lambda: w._orient_cache is not None and w._orient_cache[1] is not None)
        w.cols_spin.setValue(7)
        assert w.live_camera.spec == w._spec() == BoardSpec(7, 6, 30.0) and len(opened) == 1   # không mở lại camera
        for _ in range(5):                               # như tick(): vẽ lại trên khung sống — trước đây ValueError
            w.refresh()
            pump(qapp, 0.1)
        assert "7×6" in w.ext_note
        w.rows_spin.setValue(9)
        w.cols_spin.setValue(6)                          # 6×9: cùng 54 góc với khung còn dò theo bảng cũ
        seq = w._orient_cache[0][1][1]
        assert "đang dò lại theo bảng 6×9" in w.ext_note or seq >= w._live_valid_seq, (w.ext_note, seq)
        w.cols_spin.setValue(9)
        w.rows_spin.setValue(6)
        assert pump(qapp, 5, lambda: w._orient_cache is not None and w._orient_cache[0][0] == SPEC
                    and w._orient_cache[1] is not None)
        assert len(opened) == 1
    finally:
        w.close()
