"""Tờ ChArUco in sẵn → ngoại tham (autopark.perception.rig_sheets, sheet_extrinsics), trên ảnh TỔNG HỢP.

Dựng ảnh camera mắt cá ảo nhìn bốn tờ đặt đúng vạch quanh xe, rồi kiểm bộ giải tìm lại đúng tư thế camera, phát hiện tờ
đặt lệch, và từ chối cổng nhìn sai hướng."""
from __future__ import annotations

import json
import math

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from autopark.perception import extrinsics_calib as ec
from autopark.perception import rig_sheets as rs
from autopark.perception import sheet_extrinsics as se
from autopark.perception.bev import rig_rotation
from autopark.perception.calib_board import render_rects_png

VEHICLE = {"wheelbase_m": 0.21, "tire_radius_m": 0.037, "tire_outer_width_m": 0.16}
DPI = 200.0

POSES = {   # cổng → (vị trí camera hệ xe, yaw, pitch_down, roll): gần với kết quả đo thật của cổng 1 ngày 24/11/2026
    1: ((0.235, 0.0, 0.07), 0.0, 9.0, 2.0),
    2: ((-0.045, 0.0, 0.08), 180.0, 12.0, -1.0),
    3: ((0.11, 0.075, 0.09), 90.0, 30.0, 1.5),
    4: ((0.11, -0.075, 0.09), -90.0, 30.0, -1.0),
}


@pytest.fixture(scope="module")
def textures():
    out = {}
    for sheet in rs.SHEETS:
        rects, texts = rs.page_content(sheet, rs.make_board(sheet["first_id"]))
        out[sheet["key"]] = render_rects_png(rs.PAGE_MM, rects, (), DPI)
    return out


def render(port, textures, sheets_vehicle=VEHICLE, shift=None, rng=None, pose=None, K=ec.SYNTH_K):
    """Ảnh 640×480 của cổng `port`; `shift` = {tên tờ: (dx, dy, dyaw_độ)} để đặt lệch một tờ."""
    t, yaw, pitch, roll = pose or POSES[port]
    R_cv, t_cv = rig_rotation(yaw, pitch, roll), np.array(t, float)
    fr = ec.FloorRenderer(K=K, supersample=2)
    d = fr.rays @ R_cv.T
    with np.errstate(divide="ignore", invalid="ignore"):
        k = np.where(d[:, 2] < -1e-9, -t_cv[2] / d[:, 2], np.inf)
    hit = np.isfinite(k)
    gx = np.where(hit, t_cv[0] + np.where(hit, k, 0) * d[:, 0], np.nan)
    gy = np.where(hit, t_cv[1] + np.where(hit, k, 0) * d[:, 1], np.nan)
    img = np.where(hit, 90.0, 150.0)
    for sheet in rs.SHEETS:
        ax, ay = rs.anchor_xy(sheet["anchor"], sheets_vehicle)
        px, py = gx - ax, gy - ay
        dx, dy, dth = (shift or {}).get(sheet["key"], (0.0, 0.0, 0.0))
        if dx or dy or dth:          # tờ bị dịch/xoay quanh điểm neo: đưa điểm sàn về khung tờ đúng vạch
            c, s = math.cos(math.radians(-dth)), math.sin(math.radians(-dth))
            qx, qy = px - dx, py - dy
            px, py = c * qx - s * qy, s * qx + c * qy
        eu, eup = np.array(sheet["e_u"]), np.array(sheet["e_up"])
        u = sheet["u_ref"] + 1000.0 * (px * eu[0] + py * eu[1])
        v = rs.PAGE_MM[1] - 1000.0 * (px * eup[0] + py * eup[1])
        on = hit & (u >= 0) & (u < rs.PAGE_MM[0]) & (v >= 0) & (v < rs.PAGE_MM[1])
        tex = textures[sheet["key"]]
        iu = np.clip((u[on] / 25.4 * DPI).astype(int), 0, tex.shape[1] - 1)
        iv = np.clip((v[on] / 25.4 * DPI).astype(int), 0, tex.shape[0] - 1)
        img[on] = 30.0 + tex[iv, iu] * (215.0 / 255.0)
    w, h = fr.size
    img = img.reshape(h, fr.ss, w, fr.ss).mean(axis=(1, 3))
    img = cv2.GaussianBlur(img, (0, 0), 0.6)
    if rng is not None:
        img = img + rng.normal(0.0, 2.0, img.shape)
    return cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR), R_cv, t_cv


def solve(port, images, K=ec.SYNTH_K):
    return se.solve_port(port, [(f"p{port}_{i}.png", im) for i, im in enumerate(images)], None, dict(VEHICLE),
                         K=K, D=ec.SYNTH_D, size=(640, 480))


@pytest.mark.parametrize("port", [1, 2, 3, 4])
def test_recovers_camera_pose(port, textures):
    rng = np.random.default_rng(port)
    img, R_true, t_true = render(port, textures, rng=rng)
    res = solve(port, [img])
    assert res.ok, se.summary_text(res)
    assert np.linalg.norm(res.t_cv - t_true) < 0.003
    assert ec.rotation_angle_deg(res.R_cv, R_true) < 0.3
    assert res.rms_px < 0.5


def test_sheet_corner_ids_map_to_vehicle_sides():
    """Góc tờ trước nằm trước mũi xe, tờ sau sau đuôi, tờ trái bên trái, tờ phải bên phải."""
    for sheet in rs.SHEETS:
        xy = rs.corners_vehicle_m(sheet, rs.make_board(sheet["first_id"]), VEHICLE)
        if sheet["key"] == "front":
            assert xy[:, 0].min() > 0.21 + 0.037 and abs(xy[:, 1].mean()) < 1e-9
        elif sheet["key"] == "rear":
            assert xy[:, 0].max() < -0.037 and abs(xy[:, 1].mean()) < 1e-9
        elif sheet["key"] == "left":
            assert xy[:, 1].min() > 0.08
        else:
            assert xy[:, 1].max() < -0.08


CORNER_POSE = ((0.25, 0.08, 0.15), 60.0, 45.0, 0.0)    # camera trái nhìn chéo lên trước: thấy tờ trước VÀ tờ trái
WIDE_K = np.array([[230.0, 0.0, 320.0], [0.0, 230.0, 240.0], [0.0, 0.0, 1.0]])   # mắt cá góc rộng hơn SYNTH_K


def test_two_sheets_agree_when_placed_right(textures):
    img, R_true, t_true = render(3, textures, pose=CORNER_POSE, K=WIDE_K)
    res = solve(3, [img], K=WIDE_K)
    seen = {h.key for h in res.images[0].hits if len(h.ids) >= se.MIN_SHEET_CORNERS}
    assert seen == {"front", "left"}, se.summary_text(res)
    assert res.ok, se.summary_text(res)
    assert res.images[0].sheet_spread["angle_deg"] < 0.3
    assert np.linalg.norm(res.t_cv - t_true) < 0.003


def test_misplaced_sheet_is_caught_by_cross_check(textures):
    """Tờ trái lệch 3 cm dọc xe: hai tờ không khớp nhau → từ chối, không ra số sai."""
    bad, *_ = render(3, textures, pose=CORNER_POSE, K=WIDE_K, shift={"left": (0.03, 0.0, 0.0)})
    res = solve(3, [bad], K=WIDE_K)
    assert not res.ok
    assert any("không khớp" in (r.reason or "") for r in res.images), se.summary_text(res)


def test_wrong_vehicle_size_shows_up_between_images(textures):
    """Hai lần chụp, lần hai tờ trước lệch 2 cm (đặt không chạm lốp): lệch giữa các ảnh vượt ngưỡng → từ chối."""
    a, *_ = render(1, textures)
    b, *_ = render(1, textures, shift={"front": (0.02, 0.0, 0.0)})
    res = solve(1, [a, b])
    assert not res.ok
    assert any("giữa các ảnh" in r for r in res.refusals), se.summary_text(res)


def test_wrong_direction_refused(textures):
    img, *_ = render(1, textures)                  # ảnh camera trước, khai là cổng 2 (sau)
    res = solve(2, [img])
    assert not res.ok and any("phải nhìn rear" in r for r in res.refusals)


def test_image_without_sheet_is_skipped(textures):
    blank = np.full((480, 640, 3), 120, np.uint8)
    img, *_ = render(1, textures)
    res = solve(1, [blank, img])
    assert res.ok, se.summary_text(res)
    assert [r.used for r in res.images] == [False, True]


def test_writes_rig_file_readable_by_bev(textures, tmp_path):
    from autopark.perception import bev

    results = []
    for port in (1, 2, 3, 4):
        img, *_ = render(port, textures)
        a, *_ = render(port, textures, rng=np.random.default_rng(10 + port))
        res = solve(port, [img, a])
        assert res.ok, se.summary_text(res)
        results.append(res)
    out = ec.write_rig_file(tmp_path / "rig_v1.json", results)
    rig = bev.load_rig_extrinsics(out)
    for res in results:
        pose = rig.cameras[res.port]
        assert pose.measured
        assert np.allclose(pose.extrinsics.translation, res.t_cv, atol=1e-4)


def _synth_intrinsics(port):
    record = ec.synthetic_intrinsics_record(port)
    return ec.CameraIntrinsics(port, f"tong_hop_p{port}.json", ec.SYNTH_K, ec.SYNTH_D, (640, 480), record, True, None)


def test_calibrate_from_frames_one_click(textures, tmp_path):
    """Nút Hiệu chuẩn của app: ảnh vừa lấy của bốn camera → lưu ảnh, báo cáo, ghi tệp rig đủ bốn cổng."""
    frames = {port: [render(port, textures)[0] for _ in range(2)] for port in (1, 2, 3, 4)}
    rig = tmp_path / "rig_v1.json"
    run = se.calibrate_from_frames(frames, tmp_path / "phien", vehicle=dict(VEHICLE), rig_out=rig,
                                   intrinsics=_synth_intrinsics, allow_synthetic=True)
    assert run.ok_ports == [1, 2, 3, 4] and run.all_ok and run.rig_path == rig, run.to_text()
    assert all(line.startswith("✓") for line in run.short_lines())
    assert (tmp_path / "phien" / "to_in" / "cam_p3" / "anh_2.png").is_file()
    assert (tmp_path / "phien" / "bao_cao_to" / "ket_qua_p4.json").is_file()
    assert "ĐẠT" in (tmp_path / "phien" / "ket_qua.txt").read_text(encoding="utf-8")
    from autopark.perception import bev
    cams = bev.load_rig_extrinsics(rig).cameras
    for port in (1, 2, 3, 4):
        cam = cams[port]
        assert cam.measured
        assert np.allclose(cam.extrinsics.translation, POSES[port][0], atol=0.01)


def test_calibrate_from_frames_reports_camera_without_sheet(textures, tmp_path):
    blank = np.full((480, 640, 3), 120, np.uint8)
    frames = {1: [blank], 2: [render(2, textures)[0]], 3: [], 4: [render(4, textures)[0]]}
    rig = tmp_path / "rig_v1.json"
    run = se.calibrate_from_frames(frames, tmp_path / "phien", vehicle=dict(VEHICLE), rig_out=rig,
                                   intrinsics=_synth_intrinsics, allow_synthetic=True)
    assert run.ok_ports == [2, 4] and not run.all_ok and run.rig_path == rig     # cổng đạt vẫn được ghi
    lines = run.short_lines()
    assert lines[0].startswith("✗ Camera 1") and "không" in lines[0]
    assert lines[2] == "✗ Camera 3 · Trái: không có ảnh"


def test_spacer_pushes_sheet_away_from_tire():
    """Khoảng kê đẩy tờ ra xa xe đúng bằng spacer theo hướng ra ngoài; tờ không kê giữ nguyên."""
    spaced = dict(VEHICLE, spacer_m={"rear": 0.105, "front": 0.05})
    for sheet in rs.SHEETS:
        board = rs.make_board(sheet["first_id"])
        delta = rs.corners_vehicle_m(sheet, board, spaced) - rs.corners_vehicle_m(sheet, board, VEHICLE)
        expect = {"front": (0.05, 0.0), "rear": (-0.105, 0.0), "left": (0.0, 0.0), "right": (0.0, 0.0)}[sheet["key"]]
        assert np.allclose(delta, expect)


def test_load_vehicle_reads_spacer(tmp_path):
    path = tmp_path / "xe.json"
    path.write_text(json.dumps({"wheelbase_m": 0.21, "tire_radius_m": 0.037, "tire_outer_width_m": 0.16,
                                "spacer_m": {"rear": 0.105, "_ghi_chu": "x"}}), encoding="utf-8")
    assert se.load_vehicle(path)["spacer_m"] == {"rear": 0.105}
    path.write_text(json.dumps({"wheelbase_m": 0.21, "tire_radius_m": 0.037, "tire_outer_width_m": 0.16,
                                "spacer_m": {"back": 0.1}}), encoding="utf-8")
    with pytest.raises(se.SheetError):
        se.load_vehicle(path)
