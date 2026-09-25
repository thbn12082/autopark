"""Ngoại tham camera bằng bảng đặt trên sàn — chỉ trên ảnh TỔNG HỢP (chưa có camera nào được hiệu chuẩn, 24/09/2026).

Ảnh dựng qua một camera Kannala–Brandt đã biết (K, D như tests/test_fisheye_calib.py) gắn ở tư thế đã biết trong hệ xe
(dựng bằng `bev.rig_rotation`, không dùng mã góc của mô-đun đang kiểm); bảng in nằm trên sàn ở tư thế đã biết. Góc bảng
"thật" được tính TAY ở đây (trục y của bảng nằm bên phải trục x khi nhìn từ trên xuống — bảng nằm ngửa) rồi chiếu bằng
`cv2.fisheye.projectPoints`, để kiểm cả bộ dựng ảnh lẫn quy ước hướng bảng độc lập với mô-đun.
"""
from datetime import datetime
from functools import lru_cache
import dataclasses
import json
import math
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.perception import bev  # noqa: E402
from autopark.perception import calib_board as cb  # noqa: E402
from autopark.perception import extrinsics_calib as ec  # noqa: E402
from autopark.perception import fisheye_calib as fc  # noqa: E402
from autopark.perception import roi_tool  # noqa: E402
from autopark.perception.calib_board import BoardSpec  # noqa: E402
from autopark.perception.calibration import CameraCalibration  # noqa: E402
from tests.test_fisheye_calib import TRUE_D, TRUE_K  # noqa: E402
from tests.test_truncated_frames import truncate  # noqa: E402

SPEC = BoardSpec(9, 6, 30.0)
TRUE_ANGLES = (2.0, 31.0, -1.2)                      # yaw, pitch_down, roll (°)
TRUE_R = bev.rig_rotation(*TRUE_ANGLES)
TRUE_T = np.array([0.33, 0.012, 0.125])
# (gốc O (x, y), hướng trục x của bảng yaw°): hàng góc gần cách chân camera ≈ 0,1 m (camera thấp 0,125 m)
BOARDS = [((0.60, 0.13), -90.0), ((0.57, 0.20), -75.0), ((0.62, 0.06), -100.0), ((0.56, 0.12), -92.0)]


def hand_corners(origin, yaw_deg, spec=SPEC, z=0.0):
    """Góc trong (i, j) của bảng nằm NGỬA trên sàn: O + i·ô·(cos ψ, sin ψ) + j·ô·(sin ψ, −cos ψ) — viết tay, không
    dùng mô-đun."""
    s = spec.square_mm / 1000.0
    c, sn = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    pts = []
    for j in range(spec.rows):
        for i in range(spec.cols):
            pts.append([origin[0] + i * s * c + j * s * sn, origin[1] + i * s * sn - j * s * c, z])
    return np.array(pts)


def hand_board_transform(origin, yaw_deg, z=0.0):
    c, sn = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    R = np.array([[c, sn, 0.0], [sn, -c, 0.0], [0.0, 0.0, -1.0]])     # cột: x, y, z của bảng trong hệ xe
    return R, np.array([origin[0], origin[1], z])


def project_vehicle(points_v, R_cv=TRUE_R, t_cv=TRUE_T, K=TRUE_K, D=TRUE_D):
    pc = (np.asarray(points_v) - t_cv) @ R_cv
    return cv2.fisheye.projectPoints(pc.reshape(1, -1, 3), np.zeros((3, 1)), np.zeros((3, 1)), K,
                                     np.asarray(D).reshape(4, 1))[0].reshape(-1, 2)


@lru_cache(maxsize=None)
def renderer():
    return ec.FloorRenderer(TRUE_K, TRUE_D, (640, 480))


@lru_cache(maxsize=None)
def board_image(k: int, z: float = 0.0, mirror: bool = False):
    origin, yaw = BOARDS[k]
    R_bv, t_bv = hand_board_transform(origin, yaw, z)
    img = renderer().render(TRUE_R, TRUE_T, [(R_bv, t_bv)], SPEC, np.random.default_rng(100 + k))
    return np.ascontiguousarray(img[:, ::-1]) if mirror else img


def measured(k: int, names=("O", "A", "B"), noise=None, shift=(0.0, 0.0), z=0.0, board_z_m=None):
    """Số đo thước (hệ xe) của các góc có tên; `noise` (m) cộng vào từng điểm; `shift` dời cả lần đo."""
    origin, yaw = BOARDS[k]
    pts = hand_corners(origin, yaw, z=z)
    index = {"O": 0, "A": SPEC.cols - 1, "B": (SPEC.rows - 1) * SPEC.cols, "C": SPEC.rows * SPEC.cols - 1}
    out = {}
    for n, name in enumerate(names):
        x, y = pts[index[name], :2] + np.asarray(shift)
        if noise is not None:
            x, y = x + noise[n][0], y + noise[n][1]
        out[name] = (float(x), float(y))
    return ec.BoardPlacement.from_points(out, board_z_m=z if board_z_m is None else board_z_m)


def write_intrinsics(folder: Path, port: int = 1, K=TRUE_K, D=TRUE_D) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"cam_p{port}.json"
    path.write_text(json.dumps(ec.synthetic_intrinsics_record(port, K, D)), encoding="utf-8")
    return path


@pytest.fixture
def intr(tmp_path):
    return ec.load_camera_intrinsics(write_intrinsics(tmp_path / "calibration"), 1)


def inputs(ks, **kw):
    return [ec.PlacementInput(f"dat_{k}", board_image(k), measured(k, **kw)) for k in ks]


def pose_error(result):
    a = ec.rig_angles(result.R_cv)
    dt = float(np.linalg.norm(result.t_cv - TRUE_T))
    return dt, ec.rotation_angle_deg(result.R_cv, TRUE_R), a


# ---- quy ước bảng -------------------------------------------------------------------------------------------------------
def test_board_frame_convention_matches_the_print_and_is_right_handed():
    R = ec.board_rotation(0.0)
    assert np.allclose(R[:, 0], [1, 0, 0]) and np.allclose(R[:, 1], [0, -1, 0]) and np.allclose(R[:, 2], [0, 0, -1])
    assert np.isclose(np.linalg.det(R), 1.0)
    for yaw in (-100.0, -37.0, 0.0, 64.0, 181.0):
        Rh, _ = hand_board_transform((0, 0), yaw)
        assert np.allclose(ec.board_rotation(yaw), Rh)
    # ô góc trên-trái của tờ in là ô ĐEN, và tâm của nó nằm ở (−ô/2, −ô/2) trong hệ bảng
    lay = cb.layout(SPEC, "A3")
    assert (0, 0) in lay.black_squares() and (SPEC.cols, 0) not in lay.black_squares()
    centres, black = ec.square_centres(SPEC)
    s = SPEC.square_mm / 1000.0
    assert np.allclose(centres[0], [-s / 2, -s / 2, 0.0]) and black[0]
    printed = {(ix, iy) for ix, iy in lay.black_squares()}
    iy, ix = np.mgrid[0:SPEC.rows + 1, 0:SPEC.cols + 1]
    assert all(((int(a), int(b)) in printed) == bool(k) for a, b, k in zip(ix.ravel(), iy.ravel(), black))


def test_board_pose_from_tape_points_two_three_and_yaw():
    s = SPEC.square_mm / 1000.0
    pose = ec.board_pose(measured(0, names=("O", "A")), SPEC)
    assert pose.yaw_deg == pytest.approx(-90.0, abs=1e-9)
    assert np.allclose(pose.t, [0.60, 0.13, 0.0]) and pose.max_residual_m < 1e-9
    # B (0, rows−1) phải nằm bên PHẢI trục x của bảng: với ψ = −90° (x của bảng chỉ sang phải xe) B nằm phía SAU O
    b = ec.board_pose(measured(0, names=("O", "B")), SPEC)
    assert b.yaw_deg == pytest.approx(-90.0, abs=1e-9)
    assert hand_corners(*BOARDS[0])[(SPEC.rows - 1) * SPEC.cols][0] == pytest.approx(0.60 - (SPEC.rows - 1) * s)
    yaw_only = ec.board_pose(ec.BoardPlacement.from_points({"O": (0.60, 0.13)}, yaw_deg=-90.0), SPEC)
    assert np.allclose(yaw_only.R, pose.R) and np.allclose(yaw_only.t, pose.t)
    # ba điểm có nhiễu nhỏ: khớp vẫn nhận, sai lệch được báo
    noisy = ec.board_pose(measured(1, noise=[(0.002, 0.0), (-0.001, 0.002), (0.0, -0.002)]), SPEC)
    assert 0.0 < noisy.max_residual_m < ec.TAPE_TOLERANCE_M
    assert noisy.yaw_deg == pytest.approx(-75.0, abs=1.0)


def test_board_pose_refuses_inconsistent_tape_measurements():
    s = SPEC.square_mm / 1000.0
    origin, yaw = BOARDS[0]
    good = hand_corners(origin, yaw)
    # A đo xa hơn thật 2 cm (đếm nhầm một ô, hoặc cỡ ô nhập sai)
    far = ec.BoardPlacement.from_points({"O": tuple(good[0, :2]), "A": (good[8, 0], good[8, 1] - 0.02)})
    with pytest.raises(ec.ExtrinsicsError, match="không khớp cỡ bảng"):
        ec.board_pose(far, SPEC)
    # B ghi ở bên TRÁI trục x (bảng như bị lật): khớp cứng không lật được → sai lệch lớn → từ chối
    mirrored = ec.BoardPlacement.from_points({"O": tuple(good[0, :2]), "A": tuple(good[8, :2]),
                                              "B": (origin[0] + (SPEC.rows - 1) * s, origin[1])})
    with pytest.raises(ec.ExtrinsicsError, match="không khớp cỡ bảng"):
        ec.board_pose(mirrored, SPEC)
    with pytest.raises(ec.ExtrinsicsError, match="ít nhất hai"):
        ec.board_pose(ec.BoardPlacement.from_points({"O": (0.5, 0.1)}), SPEC)
    with pytest.raises(ec.ExtrinsicsError, match="board_z_m"):
        ec.board_pose(ec.BoardPlacement.from_points({"O": (0.5, 0.1), "A": (0.5, -0.14)}, board_z_m=0.3), SPEC)
    with pytest.raises(ec.ExtrinsicsError, match="cols \\+ rows chẵn"):
        ec.check_spec(BoardSpec(8, 6, 30.0))


def test_rig_angles_inverts_bev_rig_rotation():
    rng = np.random.default_rng(5)
    for _ in range(200):
        yaw, pitch, roll = rng.uniform(-179, 179), rng.uniform(-80, 80), rng.uniform(-60, 60)
        a = ec.rig_angles(bev.rig_rotation(yaw, pitch, roll))
        assert a["yaw_deg"] == pytest.approx(yaw, abs=1e-7)
        assert a["pitch_down_deg"] == pytest.approx(pitch, abs=1e-7)
        assert a["roll_deg"] == pytest.approx(roll, abs=1e-7)
    assert ec.direction_label(178.0) == "rear" and ec.direction_label(-95.0) == "right" and ec.direction_label(3) == "front"


# ---- ảnh tổng hợp: dò, đánh số, giải ----------------------------------------------------------------------------------
def test_rendered_board_and_orientation_match_hand_computed_corners(intr):
    for k in range(len(BOARDS)):
        img = board_image(k)
        det = fc.detect_corners(img, SPEC)
        assert det.found, f"không dò được bảng {k}"
        ob = ec.orient_board(img, det.corners, SPEC, intr.K, intr.D)
        truth = project_vehicle(hand_corners(*BOARDS[k]))
        err = np.linalg.norm(ob.corners - truth, axis=1)
        assert err.max() < 0.35, (k, ob.ordering, err.max())        # góc O là góc trong sát ô đen trên-trái
        assert ob.color_contrast > 100
        # OpenCV trả thứ tự ngược (bắt đầu từ đầu kia) ở ít nhất một ảnh: bước đánh số theo màu là cần thiết
    orders = {ec.orient_board(board_image(k), fc.detect_corners(board_image(k), SPEC).corners, SPEC, intr.K,
                              intr.D).ordering for k in range(len(BOARDS))}
    assert orders != {"identity"}


def test_pose_is_refined_in_pixels_not_in_the_undistorted_plane():
    """cv2.fisheye.solvePnP cực tiểu sai số trên mặt phẳng đã khử méo; solve_pose cực tiểu sai số ĐIỂM ẢNH nên RMS điểm
    ảnh phải nhỏ hơn (thật sự, dù ít: ở cảnh này 0,5802 → 0,5799 px với nhiễu góc 0,4 px — lợi ích lớn hơn chỉ khi góc bảng
    ở θ lớn, chưa đo), và nghiệm phải là cực tiểu sai số điểm ảnh: tinh chỉnh thêm từ nó không giảm được nữa."""
    rng = np.random.default_rng(3)
    obj = SPEC.object_points()
    R = TRUE_R.T @ ec.board_rotation(-90.0)           # bảng → camera của lần đặt 0 = (xe → camera)(bảng → xe)
    t_bv = np.array([0.60, 0.13, 0.0])
    img = project_vehicle(obj @ ec.board_rotation(-90.0).T + t_bv) + rng.normal(0, 0.4, (SPEC.n_corners, 2))
    ok, rv0, tv0 = cv2.fisheye.solvePnP(obj.reshape(1, -1, 3), img.reshape(1, -1, 2), TRUE_K, TRUE_D.reshape(4, 1))
    assert ok
    e0 = np.linalg.norm(ec.project_points(obj, rv0, tv0, TRUE_K, TRUE_D) - img, axis=1)
    rv, tv, e = ec.solve_pose(obj, img, TRUE_K, TRUE_D)
    assert np.sqrt(np.mean(e ** 2)) < np.sqrt(np.mean(e0 ** 2)) - 1e-5
    _, _, e_more = ec.refine_pose(obj, img, rv, tv, TRUE_K, TRUE_D)
    assert np.mean(e_more ** 2) > np.mean(e ** 2) - 1e-9
    _, _, e_from0 = ec.refine_pose(obj, img, rv0, tv0, TRUE_K, TRUE_D)       # phép kiểm có độ nhạy: từ nghiệm của
    assert np.mean(e_from0 ** 2) < np.mean(e0 ** 2) - 1e-6                   # OpenCV thì tinh chỉnh còn giảm được
    R_bc = cv2.Rodrigues(rv)[0]
    assert ec.rotation_angle_deg(R_bc, R) < 0.5


def test_orientation_does_not_depend_on_detector_order(intr):
    img = board_image(1)
    det = fc.detect_corners(img, SPEC)
    ref = ec.orient_board(img, det.corners, SPEC, intr.K, intr.D).corners
    for ordering in ec.ORDERINGS:
        ob = ec.orient_board(img, ec.reorder(det.corners, SPEC, ordering), SPEC, intr.K, intr.D)
        assert np.allclose(ob.corners, ref)


def test_mirrored_images_are_refused_only_through_several_placements(tmp_path):
    # camera có ảnh lật gương: điểm chính cũng lật (cx' = W − 1 − cx); nội tham "hiệu chuẩn" trên ảnh lật
    K = TRUE_K.copy()
    K[0, 2] = 639 - TRUE_K[0, 2]
    intr = ec.load_camera_intrinsics(write_intrinsics(tmp_path / "cal", 1, K), 1)
    ins = [ec.PlacementInput(f"m{k}", board_image(k, mirror=True), measured(k)) for k in range(4)]
    # một lần đặt: bảng phản chiếu vẫn khớp một khung bảng hợp lệ — KHÔNG phát hiện được (giới hạn đã ghi trong tài liệu)
    single = ec.solve_extrinsics(ins[:1], SPEC, intr, min_placements=1)
    assert single.placements[0].used
    # nhiều lần đặt ở hướng khác nhau: tư thế camera suy ra không khớp nhau → từ chối, không ghi được
    for group in (ins, ins[:2]):
        res = ec.solve_extrinsics(group, SPEC, intr)
        assert not res.ok and any("không khớp nhau" in r for r in res.refusals), ec.summary_text(res)
        assert any("lật gương" in r for r in res.refusals)


def test_recovers_camera_pose_from_several_exact_placements(intr):
    res = ec.solve_extrinsics(inputs(range(3)), SPEC, intr, square_mm_measured=True)
    assert res.ok, ec.summary_text(res)
    dt, dang, a = pose_error(res)
    assert dt < 0.002 and dang < 0.1, (dt, dang)                 # yêu cầu của việc: < 1 cm / 0,5°
    assert a["yaw_deg"] == pytest.approx(TRUE_ANGLES[0], abs=0.1)
    assert a["pitch_down_deg"] == pytest.approx(TRUE_ANGLES[1], abs=0.1)
    assert a["roll_deg"] == pytest.approx(TRUE_ANGLES[2], abs=0.1)
    assert res.t_cv[2] == pytest.approx(TRUE_T[2], abs=0.001)
    assert res.rms_px < 0.3 and res.rms_model_px is not None and res.rms_model_px < 0.4
    assert all(p.used for p in res.placements) and len(res.used) == 3
    assert "ĐẠT" in ec.summary_text(res)


def test_tape_noise_is_averaged_over_placements(intr):
    rng = np.random.default_rng(11)
    ins = [ec.PlacementInput(f"dat_{k}", board_image(k), measured(k, noise=rng.uniform(-0.0025, 0.0025, (3, 2))))
           for k in range(4)]
    res = ec.solve_extrinsics(ins, SPEC, intr)
    assert res.ok, ec.summary_text(res)
    dt, dang, _ = pose_error(res)
    assert dt < 0.01 and dang < 0.5, (dt, dang)
    # từng lần đặt một mình lệch nhiều hơn tư thế chung ít nhất ở một lần: gộp nhiều lần có ích
    singles = [float(np.linalg.norm(p.t_cv - TRUE_T)) for p in res.placements]
    assert max(singles) > dt


def test_one_mismeasured_placement_among_four_is_rejected(intr):
    ins = inputs(range(3)) + [ec.PlacementInput("dat_lech", board_image(3), measured(3, shift=(0.04, 0.0)))]
    res = ec.solve_extrinsics(ins, SPEC, intr)
    assert res.ok, ec.summary_text(res)
    bad = res.placements[-1]
    assert not bad.used and "lệch tư thế chung" in bad.reason and bad.deviation_m > 0.03
    dt, dang, _ = pose_error(res)
    assert dt < 0.002 and dang < 0.1
    assert any("bị loại" in w for w in res.warnings)


def test_moderate_tape_errors_pass_spread_checks_but_fail_joint_rms(intr):
    """Mỗi lần đặt lệch 6 mm theo một hướng khác nhau (nhất quán trong lần đó nên khớp thước vẫn nhận): độ lệch tư thế
    giữa các lần đặt < 2 cm / 1° nhưng RMS chung ≈ 5,7 px > 4 px → từ chối (đo 24/09/2026 trên ảnh tổng hợp)."""
    shifts = [(0.006, 0.0), (-0.006, 0.0), (0.0, 0.006)]
    res = ec.solve_extrinsics([ec.PlacementInput(f"d{k}", board_image(k), measured(k, shift=s))
                               for k, s in enumerate(shifts)], SPEC, intr)
    assert not res.ok
    assert {c["key"] for c in res.checks if not c["pass"]} == {"rms_px"}
    assert res.rms_px > ec.MAX_JOINT_RMS_PX


def test_two_disagreeing_placements_are_refused_not_averaged(intr):
    ins = [ec.PlacementInput("dat_0", board_image(0), measured(0)),
           ec.PlacementInput("dat_1", board_image(1), measured(1, shift=(0.04, 0.0)))]
    res = ec.solve_extrinsics(ins, SPEC, intr)
    assert not res.ok and any("không khớp nhau" in r for r in res.refusals)
    with pytest.raises(ec.ExtrinsicsError, match="không đạt"):
        res.camera_entry()


def test_board_thickness_is_used(intr):
    z = 0.005
    img = renderer().render(TRUE_R, TRUE_T, [hand_board_transform(*BOARDS[0], z)], SPEC, np.random.default_rng(1))
    img2 = renderer().render(TRUE_R, TRUE_T, [hand_board_transform(*BOARDS[2], z)], SPEC, np.random.default_rng(2))
    right = ec.solve_extrinsics([ec.PlacementInput("a", img, measured(0, z=z)),
                                 ec.PlacementInput("b", img2, measured(2, z=z))], SPEC, intr)
    assert right.ok and abs(right.t_cv[2] - TRUE_T[2]) < 0.001
    forgot = ec.solve_extrinsics([ec.PlacementInput("a", img, measured(0, z=z, board_z_m=0.0)),
                                  ec.PlacementInput("b", img2, measured(2, z=z, board_z_m=0.0))], SPEC, intr)
    assert forgot.t_cv[2] == pytest.approx(TRUE_T[2] - z, abs=0.001)          # quên độ dày tấm → thấp đi đúng chừng đó


def test_bad_inputs_are_refused_with_reasons(intr, tmp_path, monkeypatch):
    img = board_image(0)
    cases = {
        "khác cỡ": cv2.resize(img, (320, 240)),
        "khung MJPEG hỏng": truncate(img, 300),
        "không thấy đủ": np.full_like(img, 110),
    }
    for expect, image in cases.items():
        res = ec.solve_extrinsics([ec.PlacementInput("x", image, measured(0))], SPEC, intr, min_placements=1)
        assert not res.ok and expect in res.placements[0].reason, res.placements[0].reason
    one = ec.solve_extrinsics(inputs([0]), SPEC, intr)
    assert not one.ok and any("cần ≥ 2" in r for r in one.refusals)
    alone = ec.solve_extrinsics(inputs([0]), SPEC, intr, min_placements=1)
    assert alone.ok and any("không kiểm chéo" in w for w in alone.warnings)
    monkeypatch.setattr(ec, "MAX_CAMERA_HEIGHT_M", 0.10)
    high = ec.solve_extrinsics(inputs([0, 1]), SPEC, intr)
    assert not high.ok and all("cao" in p.reason for p in high.placements)
    monkeypatch.undo()
    with pytest.raises(ec.ExtrinsicsError, match="chưa có tệp nội tham"):
        ec.load_camera_intrinsics(tmp_path / "khong_co" / "cam_p1.json", 1)
    with pytest.raises(ec.ExtrinsicsError, match="cổng 1, không phải cổng 2"):
        ec.load_camera_intrinsics(Path(intr.path), 2)
    assert not ec.solve_extrinsics([], SPEC, intr).ok


# ---- tệp rig ------------------------------------------------------------------------------------------------------------
@pytest.fixture
def good_result(intr):
    res = ec.solve_extrinsics(inputs(range(3)), SPEC, intr, square_mm_measured=True)
    assert res.ok
    return res


def test_rig_file_loads_through_bev_unchanged(good_result, tmp_path):
    out = tmp_path / "cấu hình" / "camera_rig_extrinsics_v1.json"
    ec.write_rig_file(out, [good_result], allow_synthetic=True)          # nội tham của test là camera ảo (TỔNG HỢP)
    rig = bev.load_rig_extrinsics(out)
    pose = rig.cameras[1]
    assert pose.measured and pose.direction == "front"
    assert np.allclose(pose.extrinsics.rotation, good_result.R_cv, atol=1e-6)
    assert np.allclose(pose.extrinsics.translation, good_result.t_cv, atol=1e-4)
    assert np.allclose(pose.extrinsics.rotation, TRUE_R, atol=2e-3)
    base = bev.load_rig_extrinsics(ec.DEFAULT_BASE)
    for port in (2, 3, 4):                                 # camera chưa đo: chép nguyên từ tệp gốc, vẫn measured false
        assert not rig.cameras[port].measured
        assert np.allclose(rig.cameras[port].extrinsics.rotation, base.cameras[port].extrinsics.rotation)
        assert rig.cameras[port].extrinsics.translation == base.cameras[port].extrinsics.translation
    assert rig.ego == base.ego
    data = json.loads(out.read_text(encoding="utf-8"))
    entry = data["cameras"]["1"]
    prov = entry["provenance"]
    assert prov["n_placements_used"] == 3 and len(prov["placements"]) == 3 and prov["rms_px"] < 0.3
    assert prov["measured_local"][:4] == "2026" or prov["measured_local"][:2] == "20"
    assert prov["board"]["square_mm"] == 30.0 and prov["board"]["square_mm_measured"] is True
    assert all(p["board_fit"]["tape_residual_m"] for p in prov["placements"])
    # camera ảo: nhãn TỔNG HỢP ở camera, ở status và ở cả tệp — không bao giờ trông như một số đo
    assert entry["basis"].startswith("TỔNG HỢP — KHÔNG PHẢI SỐ ĐO") and "tư thế bảng đo bằng thước" not in entry["basis"]
    assert entry["synthetic"] is True and prov["intrinsics"]["synthetic"] is True
    assert data["synthetic"] is True and data["status"].startswith("TỔNG HỢP") and "GIẢ ĐỊNH" in data["status"]
    assert prov["replaced_entry"]["measured"] is False


def test_rig_file_is_never_overwritten_silently(good_result, tmp_path, intr):
    out = tmp_path / "rig_v1.json"
    ec.write_rig_file(out, [good_result], allow_synthetic=True)
    before = out.read_bytes()
    with pytest.raises(ec.ExtrinsicsError, match="không ghi đè im lặng"):
        ec.write_rig_file(out, [good_result], allow_synthetic=True)
    assert out.read_bytes() == before
    ec.write_rig_file(out, [good_result], base_path=out, overwrite=True, allow_synthetic=True)
    backup = ec.last_backup(out)
    assert backup is not None and backup.read_bytes() == before
    assert len(json.loads(out.read_text(encoding="utf-8"))["history"]) == 2
    with pytest.raises(ec.ExtrinsicsError, match="hồ sơ GIẢ ĐỊNH"):
        ec.write_rig_file(ec.DEFAULT_BASE, [good_result], overwrite=True, allow_synthetic=True)
    bad = ec.solve_extrinsics(inputs([0]), SPEC, intr)
    with pytest.raises(ec.ExtrinsicsError, match="không đạt"):
        ec.write_rig_file(tmp_path / "khac.json", [bad])
    assert not (tmp_path / "khac.json").exists()


def test_overwrite_from_another_base_cannot_drop_measured_cameras(good_result, tmp_path):
    out = tmp_path / "rig_v1.json"
    ec.write_rig_file(out, [good_result], allow_synthetic=True)            # cổng 1 đã đo
    intr2 = ec.load_camera_intrinsics(write_intrinsics(tmp_path / "cal2", 2), 2)
    res2 = ec.solve_extrinsics(inputs(range(3)), SPEC, intr2)              # "camera cổng 2" (cùng ảnh, chỉ để kiểm tệp)
    assert res2.ok
    before = out.read_bytes()
    with pytest.raises(ec.ExtrinsicsError, match="MẤT số đo của cổng 1"):
        ec.write_rig_file(out, [res2], base_path=ec.DEFAULT_BASE, overwrite=True, allow_synthetic=True)
    assert out.read_bytes() == before and ec.last_backup(out) is None
    ec.write_rig_file(out, [res2], base_path=out, overwrite=True, allow_synthetic=True)
    rig = bev.load_rig_extrinsics(out)
    assert rig.cameras[1].measured and rig.cameras[2].measured and not rig.cameras[3].measured
    assert "cổng 1, 2 đã đo" in json.loads(out.read_text(encoding="utf-8"))["status"]


def test_bev_projects_board_corners_where_the_camera_saw_them(good_result, tmp_path):
    """Nối trọn: nội tham + tệp rig mới + ROI → bev.load_rig → CameraCalibration của BEV chiếu góc bảng (z = 0) về đúng
    chỗ ảnh thấy chúng."""
    cal_dir = tmp_path / "calibration"
    write_intrinsics(cal_dir)
    out = tmp_path / "rig_v1.json"
    ec.write_rig_file(out, [good_result], allow_synthetic=True)
    roi_spec = roi_tool.RoiSpec(1, 640, 480, [roi_tool.RoiPolygon([(0, 440), (639, 440), (639, 479), (0, 479)])])
    roi_tool.save_roi(roi_spec, tmp_path / "roi")
    cameras, rig, skipped = bev.load_rig(out, cal_dir, {1: (640, 480)}, roi_dir=tmp_path / "roi")
    cam = cameras["p1"]
    assert cam.extrinsics_measured and cam.roi is not None and not skipped
    calib: CameraCalibration = cam.calibration
    for k in range(3):
        pts = hand_corners(*BOARDS[k])
        u, v, valid = calib.ground_to_pixel(pts[:, :2])
        det = good_result.placements[k].corners
        assert valid.all() and np.hypot(u - det[:, 0], v - det[:, 1]).max() < 0.6
    # đủ ba điều kiện (ngoại tham đo, ROI, nội tham đạt): lý do "không dùng được" không còn nhắc ngoại tham giả định.
    # Nhưng nội tham và tệp rig ở đây là camera ẢO (allow_synthetic): từ 25/09/2026 BEV vẫn báo "không dùng được" với
    # đúng MỘT lý do — dữ liệu TỔNG HỢP — để tệp tổng hợp không bao giờ lọt thành BEV "dùng được".
    result = bev.build_bev({"p1": np.zeros((480, 640), np.float32)}, {"p1": cam}, bev.GridSpec(*bev.RIG_GRID))
    reasons = [r for r in bev.unusable_reasons(result, {"p1": cam}) if "p1" in r]
    assert cam.synthetic == ("ngoại tham", "nội tham")
    assert reasons == ["p1: ngoại tham và nội tham là dữ liệu TỔNG HỢP — không phải số đo"]
    real = dataclasses.replace(cam, synthetic=())                          # như camera thật đã đo đủ
    assert not any("p1" in r for r in bev.unusable_reasons(result, {"p1": real}))


# ---- dòng lệnh ----------------------------------------------------------------------------------------------------------
def test_cli_synthetic_solve_check_and_overwrite(tmp_path, capsys, monkeypatch):
    demo = tmp_path / "bộ thử"
    assert ec.main(["synthetic", "--out", str(demo)]) == 0
    assert "--allow-synthetic" in capsys.readouterr().out                 # lệnh gợi ý không ghi vào configs/
    placements = demo / "dat_bang_p1.json"
    out = tmp_path / "rig_v1.json"
    report = tmp_path / "bao_cao"
    # kết quả của camera ảo: không có cờ thì không ghi (mã 2), và lệnh không gợi ý ghi vào configs/
    assert ec.main(["solve", "--placements", str(placements), "--out", str(out), "--report", str(report)]) == 2
    assert "TỔNG HỢP" in capsys.readouterr().err and not out.exists()
    assert ec.main(["solve", "--placements", str(placements), "--report", str(report)]) == 0
    text = capsys.readouterr().out
    assert "KHÔNG PHẢI SỐ ĐO" in text and "--allow-synthetic" in text and "camera_rig_extrinsics_v1" not in text
    # có cờ mà tệp ra nằm trong configs/: luôn từ chối (thư mục cấm đổi sang tmp để không đụng configs/ thật)
    assert {ec.PROJECT / "configs", ec.PROJECT / "calibration"} <= set(ec.SYNTHETIC_FORBIDDEN_DIRS)
    with monkeypatch.context() as m:
        m.setattr(ec, "SYNTHETIC_FORBIDDEN_DIRS", (tmp_path / "configs", tmp_path / "du_an" / "calibration"))
        forbidden = tmp_path / "configs" / "rig" / "camera_rig_extrinsics_v1.json"
        assert ec.main(["solve", "--placements", str(placements), "--out", str(forbidden), "--allow-synthetic",
                        "--report", str(report)]) == 2
        assert "không bao giờ được ghi vào" in capsys.readouterr().err and not forbidden.exists()
        # bộ thử cũng không được đặt nội tham ảo vào thư mục calibration/ của dự án
        assert ec.main(["synthetic", "--out", str(tmp_path / "du_an")]) == 2
        assert "không được ghi vào" in capsys.readouterr().err and not (tmp_path / "du_an").exists()
    assert ec.main(["solve", "--placements", str(placements), "--out", str(out), "--allow-synthetic",
                    "--report", str(report)]) == 0
    text = capsys.readouterr().out
    assert "ĐẠT" in text and "khớp" in text and (report / "ket_qua.json").exists() and "bản cũ" not in text
    assert len(list(report.glob("xem_*.jpg"))) == 3
    truth = json.loads(placements.read_text(encoding="utf-8"))["truth"]
    pose = bev.load_rig_extrinsics(out).cameras[1]
    assert np.allclose(pose.extrinsics.translation, truth["position_m"], atol=0.002)
    assert json.loads(out.read_text(encoding="utf-8"))["synthetic"] is True
    assert ec.main(["check", str(out)]) == 0
    checked = capsys.readouterr().out
    assert "cổng 1 (front): TỔNG HỢP — KHÔNG PHẢI SỐ ĐO" in checked and "cổng 2 (rear): GIẢ ĐỊNH" in checked
    before = out.read_bytes()
    assert ec.main(["solve", "--placements", str(placements), "--out", str(out), "--allow-synthetic",
                    "--report", str(report)]) == 2
    assert "không ghi đè im lặng" in capsys.readouterr().err and out.read_bytes() == before
    assert ec.main(["solve", "--placements", str(placements), "--out", str(out), "--base", str(out), "--overwrite",
                    "--allow-synthetic", "--report", str(report)]) == 0
    assert "bản cũ" in capsys.readouterr().out
    assert ec.last_backup(out) is not None and ec.last_backup(out).read_bytes() == before
    out.unlink()                                  # tệp ra chưa có, nhưng còn bản sao lưu cũ cạnh nó
    assert ec.main(["solve", "--placements", str(placements), "--out", str(out), "--allow-synthetic",
                    "--report", str(report)]) == 0
    assert "bản cũ" not in capsys.readouterr().out   # không báo nhầm một bản sao lưu cũ không liên quan
    # --place: một lần đặt trên dòng lệnh → thiếu lần đặt thứ hai → từ chối, mã 3, không ghi
    rec = json.loads(placements.read_text(encoding="utf-8"))
    first = rec["placements"][0]
    o, a = first["points_xy_m"]["O"], first["points_xy_m"]["A"]
    code = ec.main(["solve", "--port", "1", "--square-mm", "30", "--intrinsics", str(demo / "calibration" / "cam_p1.json"),
                    "--place", str(demo / first["image"]), str(o[0]), str(o[1]), str(a[0]), str(a[1]),
                    "--out", str(tmp_path / "mot_lan.json"), "--report", str(report)])
    assert code == 3 and not (tmp_path / "mot_lan.json").exists()


def test_placements_file_reads_snapshot_folders(tmp_path):
    snap = tmp_path / "rig_snapshots" / "20260925_101010_000"
    snap.mkdir(parents=True)
    fc.write_image(snap / "cam_p1.png", board_image(0))
    (snap / "meta.json").write_text("{}", encoding="utf-8")
    rec = ec.placements_record(1, SPEC, [{"name": "a", "snapshot": str(snap),
                                          "points_xy_m": {k: list(v) for k, v in measured(0).points_dict().items()}}],
                               square_mm_measured=True, board_z_m=0.0)
    path = tmp_path / "dat.json"
    path.write_text(json.dumps(rec), encoding="utf-8")
    port, spec, ins, board = ec.inputs_from_record(ec.load_placements_file(path), tmp_path)
    assert port == 1 and spec == SPEC and ins[0].image_path.endswith("cam_p1.png")
    assert np.array_equal(ins[0].image, board_image(0))
    bad = dict(rec, placements=[{"name": "b", "snapshot": str(snap), "points_xy_m": {"O": [0, 0]}}])
    with pytest.raises(ec.ExtrinsicsError, match="cam_p2.png"):
        ec.inputs_from_record(dict(bad, port=2), tmp_path)
    with pytest.raises(ec.ExtrinsicsError, match="không phải tệp"):
        path.write_text(json.dumps({"format": "khac"}), encoding="utf-8")
        ec.load_placements_file(path)


def test_cli_numbers_accept_vietnamese_decimal_comma(tmp_path, capsys):
    """Tài liệu viết số kiểu Việt ('0,005'): dòng lệnh phải nhận '0,60' như '0.60', và báo lỗi tiếng Việt (mã 2, không
    traceback) khi số sai."""
    assert ec.main(["solve", "--port", "1", "--square-mm", "0", "--place", "x.png", "0.6", "0.1", "0.6", "-0.1"]) == 2
    err = capsys.readouterr().err
    assert "LỖI" in err and "cỡ ô" in err
    assert ec.main(["solve", "--port", "1", "--square-mm", "3o", "--place", "x.png", "0.6", "0.1", "0.6", "-0.1"]) == 2
    assert "không phải số" in capsys.readouterr().err
    demo = tmp_path / "bộ thử"
    assert ec.main(["synthetic", "--out", str(demo)]) == 0
    rec = json.loads((demo / "dat_bang_p1.json").read_text(encoding="utf-8"))
    intr = str(demo / "calibration" / "cam_p1.json")

    def place_args(fmt):
        args = []
        for entry in rec["placements"][:2]:
            o, a = entry["points_xy_m"]["O"], entry["points_xy_m"]["A"]
            args += ["--place", str(demo / entry["image"])] + [fmt(v) for v in (o[0], o[1], a[0], a[1])]
        return args

    codes, poses = [], []
    for name, fmt, square, z in (("cham", lambda v: repr(float(v)), "30", "0"),
                                 ("phay", lambda v: repr(float(v)).replace(".", ","), "30,0", "0,0")):
        if name == "phay":
            assert any("," in a for a in place_args(fmt))
        codes.append(ec.main(["solve", "--port", "1", "--square-mm", square, "--board-z-m", z, "--intrinsics", intr,
                              *place_args(fmt), "--report", str(tmp_path / name)]))
        poses.append(json.loads((tmp_path / name / "ket_qua.json").read_text(encoding="utf-8"))["camera"])
    assert codes == [0, 0] and poses[0] == poses[1] and poses[0] is not None
    capsys.readouterr()
    # dấu phẩy được hiểu (không vấp ở bước đọc số): lỗi kế tiếp là thiếu ảnh
    assert ec.main(["solve", "--port", "1", "--square-mm", "30", "--intrinsics", intr, "--place",
                    str(tmp_path / "khong_co.png"), "0,60", "0,13", "0,60", "-0,11"]) == 2
    assert "không đọc được ảnh" in capsys.readouterr().err
    # tệp danh sách lần đặt viết tay với chuỗi dấu phẩy
    comma = dict(rec, board=dict(rec["board"], square_mm="30,0", board_z_m="0,005"))
    _, spec, ins, _ = ec.inputs_from_record(comma, demo)
    assert spec.square_mm == 30.0 and all(i.placement.board_z_m == pytest.approx(0.005) for i in ins)
    with pytest.raises(ec.ExtrinsicsError, match="board_z_m"):
        ec.inputs_from_record(dict(rec, board=dict(rec["board"], board_z_m="năm mm")), demo)


# ---- kết quả tổng hợp không bao giờ thành "số đo" ----------------------------------------------------------------------
def real_like_record(port=1):
    """Tệp nội tham KHÔNG mang dấu tổng hợp (đóng vai hiệu chuẩn thật — chỉ để kiểm nhánh 'thật' của bước ghi)."""
    rec = ec.synthetic_intrinsics_record(port, TRUE_K, TRUE_D)
    rec.pop("synthetic")
    rec["camera"]["device"] = "USB camera (thử)"
    rec["acceptance"]["status"] = "đề xuất, chưa kiểm trên camera thật"
    rec["note"] = "chưa gá trên xe"
    return rec


def real_like_intrinsics(folder: Path, port=1):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"cam_p{port}.json"
    path.write_text(json.dumps(real_like_record(port)), encoding="utf-8")
    return ec.load_camera_intrinsics(path, port)


def test_intrinsics_synthetic_markers():
    assert ec.synthetic_intrinsics_record(1)["synthetic"] is True
    assert ec.intrinsics_is_synthetic(ec.synthetic_intrinsics_record(1))
    assert not ec.intrinsics_is_synthetic(real_like_record()) and not ec.intrinsics_is_synthetic(None)
    for mark in ({"synthetic": True}, {"camera": {"hub_port": 1, "device": "TỔNG HỢP"}},
                 {"acceptance": {"status": "TỔNG HỢP — không phải hiệu chuẩn thật"}}, {"note": "TỔNG HỢP: camera ảo"}):
        assert ec.intrinsics_is_synthetic({**real_like_record(), **mark}), mark


def test_synthetic_result_never_lands_as_measurement(good_result, tmp_path, monkeypatch, capsys):
    assert good_result.synthetic and "KHÔNG PHẢI SỐ ĐO" in ec.summary_text(good_result)
    out = tmp_path / "rig_v1.json"
    with pytest.raises(ec.ExtrinsicsError, match="TỔNG HỢP"):           # mặc định: từ chối
        ec.write_rig_file(out, [good_result])
    assert not out.exists()
    monkeypatch.setattr(ec, "SYNTHETIC_FORBIDDEN_DIRS", (tmp_path / "configs", tmp_path / "calibration"))
    for bad in (tmp_path / "configs" / "rig" / "camera_rig_extrinsics_v1.json", tmp_path / "calibration" / "rig.json"):
        with pytest.raises(ec.ExtrinsicsError, match="không bao giờ được ghi vào"):
            ec.write_rig_file(bad, [good_result], allow_synthetic=True)   # có cờ vẫn cấm configs/, calibration/
        assert not bad.exists()
    synth = tmp_path / "thu" / ec.SYNTHETIC_RIG_NAME
    ec.write_rig_file(synth, [good_result], allow_synthetic=True)
    # kết quả "thật" (nội tham không có dấu tổng hợp): ghi được không cần cờ, basis "ĐO (", không có nhãn tổng hợp
    real2 = ec.solve_extrinsics(inputs(range(3)), SPEC, real_like_intrinsics(tmp_path / "cal_that", 2))
    assert real2.ok and not real2.synthetic and "KHÔNG PHẢI SỐ ĐO" not in ec.summary_text(real2)
    # ... nhưng không được chép camera tổng hợp của tệp gốc sang (kể cả khi tệp ra ở ngoài configs/)
    with pytest.raises(ec.ExtrinsicsError, match="có camera TỔNG HỢP"):
        ec.write_rig_file(tmp_path / "that.json", [real2], base_path=synth)
    with pytest.raises(ec.ExtrinsicsError, match="không bao giờ được ghi vào"):
        ec.write_rig_file(tmp_path / "configs" / "that.json", [real2], base_path=synth, allow_synthetic=True)
    assert not (tmp_path / "that.json").exists() and not (tmp_path / "configs" / "that.json").exists()
    path = ec.write_rig_file(tmp_path / "configs" / "rig" / "that.json", [real2])      # từ v0: được
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["cameras"]["2"]["basis"].startswith("ĐO (") and "synthetic" not in data["cameras"]["2"]
    assert "synthetic" not in data and not data["status"].startswith("TỔNG HỢP")
    assert data["cameras"]["2"]["provenance"]["intrinsics"]["synthetic"] is False
    capsys.readouterr()
    assert ec.main(["check", str(path)]) == 0
    assert "cổng 2 (front): ĐO;" in capsys.readouterr().out
    # kết quả thật thay đúng cổng tổng hợp của tệp gốc: nhãn tổng hợp biến mất khỏi tệp ra
    real1 = ec.solve_extrinsics(inputs(range(3)), SPEC, real_like_intrinsics(tmp_path / "cal_that1", 1))
    replaced = json.loads(ec.write_rig_file(tmp_path / "thay.json", [real1], base_path=synth).read_text(encoding="utf-8"))
    assert "synthetic" not in replaced and "synthetic" not in replaced["cameras"]["1"]
    assert json.loads(synth.read_text(encoding="utf-8"))["synthetic"] is True


def test_two_overwrites_in_the_same_instant_keep_every_old_version(good_result, tmp_path, monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 24, 23, 59, 59, 123456)

    monkeypatch.setattr(ec, "datetime", Frozen)
    out = tmp_path / "rig_v1.json"
    ec.write_rig_file(out, [good_result], allow_synthetic=True)
    a = out.read_bytes()
    ec.write_rig_file(out, [good_result], base_path=out, overwrite=True, allow_synthetic=True)
    b = out.read_bytes()
    ec.write_rig_file(out, [good_result], base_path=out, overwrite=True, allow_synthetic=True)
    backups = sorted(tmp_path.glob("rig_v1.bak_*.json"))
    assert len(backups) == 2 and [p.read_bytes() for p in backups] == [a, b]   # bản A không bị bản B đè
    assert ec.last_backup(out).read_bytes() == b and len({a, b, out.read_bytes()}) == 3


# ---- ảnh kiểm: hộp thân xe và màu trục --------------------------------------------------------------------------------
REAR_R = bev.rig_rotation(180.0, 31.0, 0.0)          # camera nhìn về phía SAU, đặt trước xe: thấy mép trước hộp thân xe
REAR_T = np.array([0.8, 0.0, 0.3])                   # và trục y của xe (x = 0)


def posed_result(intr):
    placement = ec.PlacementResult("dat_01", None, measured(0))
    return ec.ExtrinsicsResult(1, True, [], [], [placement], intr, SPEC, R_cv=REAR_R, t_cv=REAR_T, rms_px=0.1,
                               max_px=0.2, created_local="2026-09-24T23:00:00")


def _near(img, uv, radius=1):
    u, v = int(round(uv[0])), int(round(uv[1]))
    return img[max(v - radius, 0):v + radius + 1, max(u - radius, 0):u + radius + 1].reshape(-1, 3).astype(int)


def _projected(points):
    uv, ok = ec._project_vehicle(np.asarray(points, float), REAR_R, REAR_T, TRUE_K, TRUE_D, (640, 480))
    inside = ok & (uv[:, 0] >= 2) & (uv[:, 0] <= 637) & (uv[:, 1] >= 2) & (uv[:, 1] <= 477)
    return uv[inside]


def test_check_image_draws_the_assumed_body_box(intr, tmp_path):
    ego = bev.load_rig_extrinsics(ec.DEFAULT_BASE).ego
    assert ec.rig_ego(ec.DEFAULT_BASE) == ego and ec.rig_ego(tmp_path / "khong_co.json") is None
    res = posed_result(intr)
    black = np.zeros((480, 640, 3), np.uint8)
    with_ego = ec.draw_result(black, res.placements[0], res, SPEC, ego=ego)
    without = ec.draw_result(black, res.placements[0], res, SPEC)
    assert not np.array_equal(with_ego, without)
    edge = _projected([(ego.x_max, y, 0.0) for y in np.linspace(ego.y_min + 0.01, ego.y_max - 0.01, 15)])
    assert len(edge) >= 10
    for uv in edge:                                    # cạnh x_max: trắng (lưới chỉ xám ≤ 150, trục đỏ/xanh lá)
        assert _near(with_ego, uv).min(axis=1).max() >= 200 and _near(without, uv).min(axis=1).max() <= 150
    # báo cáo dòng lệnh: ảnh xem_*.jpg có hộp thân xe khi truyền ego
    inp = [ec.PlacementInput("dat_01", black, measured(0))]
    ec.write_report(tmp_path / "co", res, inp, ego=ego)
    ec.write_report(tmp_path / "khong", res, inp)
    assert (tmp_path / "co" / "xem_dat_01.jpg").read_bytes() != (tmp_path / "khong" / "xem_dat_01.jpg").read_bytes()


def test_check_image_axis_colours_match_the_board_arrows():
    """Trục x của xe (đường y = 0) đỏ, trục y của xe (đường x = 0) xanh lá — như mũi tên x (đỏ) / y (xanh lá) của bảng."""
    img = ec.draw_vehicle_grid(np.zeros((480, 640, 3), np.uint8), REAR_R, REAR_T, TRUE_K, TRUE_D)
    red_pts = _projected([(x, 0.0, 0.0) for x in (0.05, 0.15, 0.25, 0.45, 0.55)])
    green_pts = _projected([(0.0, y, 0.0) for y in (-0.25, -0.15, -0.05, 0.05, 0.15, 0.25)])
    assert len(red_pts) >= 4 and len(green_pts) >= 4
    for uv in red_pts:
        px = _near(img, uv)
        best = px[px[:, 2].argmax()]                   # BGR
        assert best[2] >= 150 and best[0] <= 60 and best[1] <= 60 and px[:, 1].max() <= 60, (uv, best)
    for uv in green_pts:
        px = _near(img, uv)
        best = px[px[:, 1].argmax()]
        assert best[1] >= 150 and best[0] <= 60 and best[2] <= 60 and px[:, 2].max() <= 60, (uv, best)
    board = ec.draw_board_labels(np.zeros((480, 640, 3), np.uint8), project_vehicle(hand_corners(*BOARDS[0])), SPEC)
    assert (board[..., 2] > 200).any() and (board[..., 1] > 150).any()      # mũi tên x đỏ, y xanh lá của bảng


# ---- từng phép loại lần đặt (bảng mục 5.2 của docs/NGOAI_THAM_VA_ROI.md) ----------------------------------------------
def test_each_placement_check_refuses_with_its_own_reason(intr, tmp_path, monkeypatch):
    """Mỗi phép loại lần đặt có ca riêng — gỡ hay đảo phép kiểm thì ca đó đỏ."""
    # nội tham lệch f_x 10 % (đầu vào thật, không vá ngưỡng): RMS riêng > 1 px
    K = TRUE_K.copy()
    K[0, 0] *= 1.1
    wrong_k = ec.load_camera_intrinsics(write_intrinsics(tmp_path / "lech_fx", 1, K), 1)
    res = ec.solve_extrinsics(inputs([0, 1]), SPEC, wrong_k)
    assert not res.ok and all(not p.used and "RMS chiếu lại" in p.reason for p in res.placements), res.refusals
    # ảnh xám mờ (tương phản ô nhỏ): dò được góc nhưng không xác định được góc O
    low = np.clip(board_image(0).astype(np.float32) * 0.1 + 100, 0, 255).astype(np.uint8)
    assert fc.detect_corners(low, SPEC).found
    res = ec.solve_extrinsics([ec.PlacementInput("mo", low, measured(0))], SPEC, intr, min_placements=1)
    assert not res.ok and "tương phản" in res.placements[0].reason, res.placements[0].reason
    # ba phép còn lại: ảnh tổng hợp khó chạm đúng một phép mà không chạm phép khác → hẹp ngưỡng lại cho ảnh chuẩn
    for name, value, expect in (("MIN_EDGE_MARGIN_PX", 1000.0, "sát mép ảnh"),
                                ("BOARD_DISTANCE_M", (0.08, 0.1), "bảng cách camera"),
                                ("MIN_CAMERA_HEIGHT_M", 0.5, "lần đặt này đặt camera ở độ cao")):
        with monkeypatch.context() as m:
            m.setattr(ec, name, value)
            res = ec.solve_extrinsics(inputs([0, 1]), SPEC, intr)
        assert not res.ok and all(not p.used and expect in p.reason for p in res.placements), (name, res.refusals)
    assert ec.solve_extrinsics(inputs([0, 1]), SPEC, intr).ok          # ngưỡng thật: cùng ảnh được nhận


def test_corner_theta_beyond_intrinsics_coverage_warns(intr, tmp_path):
    ref = ec.solve_extrinsics(inputs([0, 1]), SPEC, intr)
    worst = max(p.corner_theta_max_deg for p in ref.used)
    assert not any("vượt θ" in w for w in ref.warnings)            # tệp nội tham tổng hợp không ghi θ đã thấy
    for theta_obs, warned in ((worst - 5.0, True), (worst + 5.0, False)):
        rec = ec.synthetic_intrinsics_record(1, TRUE_K, TRUE_D)
        rec["field_of_view_deg"]["theta_observed_max_deg"] = theta_obs
        path = tmp_path / f"theta_{theta_obs:.0f}" / "cam_p1.json"
        path.parent.mkdir()
        path.write_text(json.dumps(rec), encoding="utf-8")
        res = ec.solve_extrinsics(inputs([0, 1]), SPEC, ec.load_camera_intrinsics(path, 1))
        assert res.ok and any("vượt θ lớn nhất" in w for w in res.warnings) == warned, (theta_obs, worst, res.warnings)


@pytest.mark.parametrize("value, expected", [(True, True), (False, False), (None, None), ("false", False), (1, False)])
def test_intrinsics_acceptance_flag_is_read_strictly_like_bev(tmp_path, value, expected):
    """25/09/2026: như `bev.acceptance_flag` — chỉ true của JSON là đạt; trước đó bool("false") thành True."""
    path = write_intrinsics(tmp_path / "calibration")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["acceptance"]["all_pass"] = value
    path.write_text(json.dumps(record), encoding="utf-8")
    assert ec.load_camera_intrinsics(path, 1).acceptance_all_pass is expected
