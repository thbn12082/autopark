"""BEV chiếm chỗ từ AI nhiều camera (autopark/perception/bev.py).

Rig tổng hợp: bốn camera mắt cá ảo (tư thế của configs/rig/camera_rig_extrinsics_v0.json, nội tham danh định 130° chéo)
quanh một xe 0,40 × 0,20 m nhìn mặt sàn phẳng có hai hộp và một dải "mô hình không chắc". Bản đồ xác suất của từng camera
được dựng bằng cách chiếu SỰ THẬT vào ảnh (tia qua từng pixel → hộp hay mặt sàn), ở cỡ hiển thị 480×360 như bàn thử ghi.
Phép kiểm tầm nhìn dưới đây (`visible_from`) là tính độc lập: đoạn thẳng camera → điểm sàn có cắt hộp không, không dùng
`project_labels`. Không cần dataset, torch hay thiết bị (trừ bài WoodScape: bỏ qua nếu thiếu dữ liệu).
"""
from functools import lru_cache
import json
import math
from pathlib import Path
import time

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.domain.sensors import SourceStamp  # noqa: E402
from autopark.perception import bev  # noqa: E402
from autopark.perception.bev import (CAT_EGO, CAT_OCCLUDED, CAT_UNCERTAIN, CAT_UNSEEN, RigConfigError,  # noqa: E402
                                     SyntheticBox, SyntheticPatch, SyntheticScene, build_bev, evidence_labels,
                                     load_rig, load_rig_extrinsics, nominal_intrinsics, resize_probability,
                                     rig_rotation, synthetic_prob_map, synthetic_rig)
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRID = GridSpec(-3.0, 3.0, -3.0, 3.0, 0.05)
MAX_RANGE = 2.0
FRONT_BOX = SyntheticBox(1.0, 1.3, -0.15, 0.15, 0.15)       # chỉ camera trước (p1) thấy
RIGHT_BOX = SyntheticBox(-0.3, 0.3, -1.0, -0.8, 0.10)       # camera phải (p4) thấy
BAND = SyntheticPatch(-1.3, -1.0, -0.6, 0.6, 0.30)          # 0,15 < 0,30 < 0,50: không chắc chắn
SCENE = SyntheticScene(boxes=(FRONT_BOX, RIGHT_BOX), patches=(BAND,))
DISPLAY = (480, 360)


# ---- dựng cảnh -------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def rig():
    return synthetic_rig()


@pytest.fixture(scope="module")
def probs(rig):
    cameras, _ = rig
    return {name: np.round(synthetic_prob_map(cam.calibration, SCENE, out_size=DISPLAY) * 255).astype(np.uint8)
            for name, cam in cameras.items()}


@pytest.fixture(scope="module")
def full(rig, probs):
    cameras, ego = rig
    return build_bev(probs, cameras, GRID, max_range=MAX_RANGE, ego=ego)


def centers():
    return GRID.centers()


def inside(rect, gx, gy, shrink=0.0):
    return ((gx >= rect.x_min + shrink) & (gx <= rect.x_max - shrink)
            & (gy >= rect.y_min + shrink) & (gy <= rect.y_max - shrink))


def dilate(mask, n=1):
    return cv2.dilate(mask.astype(np.uint8), np.ones((2 * n + 1, 2 * n + 1), np.uint8)).astype(bool)


def erode(mask, n=1):
    return cv2.erode(mask.astype(np.uint8), np.ones((2 * n + 1, 2 * n + 1), np.uint8),
                     borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)


def segment_blocked(origin, points_xy, box):
    """Đoạn origin → (x, y, 0) có đi qua hộp trước khi tới điểm không (slab trên t ∈ [0, 1))."""
    o = np.asarray(origin, float)
    d = np.column_stack([points_xy, np.zeros(len(points_xy))]) - o
    d = np.where(np.abs(d) < 1e-12, 1e-12, d)
    lo, hi = np.array([box.x_min, box.y_min, 0.0]), np.array([box.x_max, box.y_max, box.height])
    t1, t2 = (lo - o) / d, (hi - o) / d
    near, far = np.minimum(t1, t2).max(axis=1), np.maximum(t1, t2).min(axis=1)
    return (near <= far) & (far > 0) & (near < 1.0 - 1e-9)


def visible_from(camera, gx, gy, boxes=SCENE.boxes, max_range=MAX_RANGE):
    """Sự thật độc lập: trong trường nhìn (mô hình camera), trong tầm, đoạn nhìn không bị hộp nào chắn."""
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    _, _, fov = camera.calibration.ground_to_pixel(pts)
    t = camera.calibration.extrinsics.translation
    ok = fov & (np.hypot(pts[:, 0] - t[0], pts[:, 1] - t[1]) <= max_range)
    for box in boxes:
        ok &= ~segment_blocked(t, pts, box)
    return ok.reshape(gx.shape)


def cell(x, y):
    return GRID.index(x, y)


# ---- xác suất → bằng chứng -------------------------------------------------------------------------------------------
def test_two_thresholds_make_three_kinds_of_evidence():
    p = np.array([[0.0, 0.15, 0.1501, 0.3, 0.4999, 0.5, 1.0, np.nan]], np.float32)
    labels, uncertain = evidence_labels(p, 0.15, 0.5)
    assert labels.tolist() == [[0, 0, 255, 255, 255, 1, 1, 255]]          # bằng ngưỡng: FREE / BLOCKED
    assert uncertain.tolist() == [[False, False, True, True, True, False, False, False]]   # NaN: không phải "không chắc"
    q = np.array([[38, 39, 127, 128]], np.uint8)                            # P×255: 38/255 = 0,149; 39/255 = 0,153
    labels, uncertain = evidence_labels(q, 0.15, 0.5)
    assert labels.tolist() == [[0, 255, 255, 1]] and uncertain.tolist() == [[False, True, True, False]]
    roi = np.array([[0, 255, 255, 0]], np.uint8)                            # ngoài ROI: không có bằng chứng nào
    labels, uncertain = evidence_labels(q, 0.15, 0.5, roi)
    assert labels.tolist() == [[255, 255, 255, 255]] and uncertain.tolist() == [[False, True, True, False]]
    for bad in ((0.5, 0.5), (0.6, 0.4), (-0.1, 0.5), (0.1, 1.1)):
        with pytest.raises(ValueError):
            evidence_labels(p, *bad)
    with pytest.raises(ValueError):
        evidence_labels(q, 0.15, 0.5, np.zeros((2, 4), np.uint8))


def test_probability_any_resolution_but_same_aspect():
    small = np.full((360, 480), 0.2, np.float32)
    assert resize_probability(small, 640, 480).shape == (480, 640)
    assert resize_probability(np.zeros((417, 557), np.float32), 640, 480).shape == (480, 640)   # làm tròn cỡ hiển thị
    with pytest.raises(ValueError, match="tỉ lệ khung"):
        resize_probability(np.zeros((360, 640), np.float32), 640, 480)                        # 16:9 so với 4:3


def test_display_size_probabilities_give_same_bev_as_native(rig, full):
    cameras, ego = rig
    native = {n: synthetic_prob_map(c.calibration, SCENE) for n, c in cameras.items()}
    result = build_bev(native, cameras, GRID, max_range=MAX_RANGE, ego=ego)
    assert (result.states == full.states).mean() > 0.98


# ---- tư thế camera và tệp rig ----------------------------------------------------------------------------------------
def test_rig_rotation_follows_vehicle_and_woodscape_conventions():
    r = rig_rotation(0.0, 30.0)
    assert np.allclose(r[:, 2], [math.cos(math.radians(30)), 0.0, -0.5])     # trục quang: trước và chúc xuống
    assert np.allclose(r[:, 0], [0.0, -1.0, 0.0])                            # phải của ảnh = phải của xe (−y)
    assert r[2, 1] < 0 and np.isclose(np.linalg.det(r), 1.0)                 # xuống của ảnh hướng xuống sàn
    assert np.allclose(rig_rotation(90.0, 45.0)[:, 2], [0.0, math.sqrt(0.5), -math.sqrt(0.5)])
    rolled = rig_rotation(0.0, 30.0, 90.0)
    assert np.allclose(rolled[:, 2], r[:, 2]) and np.allclose(rolled[:, 0], r[:, 1])
    cameras, _ = synthetic_rig()
    front = cameras["p1"].calibration
    u, v, ok = front.ground_to_pixel([[1.0, 0.0], [1.0, 0.5]])
    assert ok.all() and abs(u[0] - front.intrinsics.cx) < 1.0                # thẳng trước: cột giữa ảnh
    assert u[1] < front.intrinsics.cx                                        # +y (trái) ở nửa trái ảnh


def test_extrinsics_config_is_marked_assumed_not_measured():
    path = PROJECT_ROOT / "configs/rig/camera_rig_extrinsics_v0.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["status"] == "GIẢ ĐỊNH — CHƯA ĐO"
    assert all(c["measured"] is False and c["basis"].startswith("GIẢ ĐỊNH — CHƯA ĐO") for c in raw["cameras"].values())
    rig = load_rig_extrinsics(path)
    assert sorted(rig.cameras) == [1, 2, 3, 4] and not any(p.measured for p in rig.cameras.values())
    assert {p.direction for p in rig.cameras.values()} == {"front", "rear", "left", "right"}
    assert rig.ego.contains(0.13, 0.0) and not rig.ego.contains(0.40, 0.0)
    assert rig.ego.x_max - rig.ego.x_min == pytest.approx(0.44) and rig.ego.y_max - rig.ego.y_min == pytest.approx(0.24)
    for pose in rig.cameras.values():                                        # camera trên sàn, nhìn xuống
        assert pose.extrinsics.translation[2] > 0 and pose.extrinsics.rotation[2, 2] < 0


def _write_intrinsics(folder, port, size=(640, 480), all_pass=True):
    from autopark.perception.fisheye_calib import FORMAT, woodscape_intrinsics
    f = nominal_intrinsics(*size).k[0]
    K = [[f, 0.0, size[0] / 2 - 0.5], [0.0, f, size[1] / 2 - 0.5], [0.0, 0.0, 1.0]]
    record = {"format": FORMAT, "camera": {"hub_port": port, "source_id": f"cam_p{port}"}, "image_size": list(size),
              "K": K, "D": [0.0, 0.0, 0.0, 0.0],
              "woodscape_intrinsic": woodscape_intrinsics(np.array(K), np.zeros(4), size),
              "acceptance": {"all_pass": all_pass}, "extrinsic": None}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"cam_p{port}.json").write_text(json.dumps(record), encoding="utf-8")


def test_load_rig_refuses_without_intrinsics(tmp_path):
    with pytest.raises(RigConfigError) as info:
        load_rig(calibration_dir=tmp_path)
    message = str(info.value)
    assert all(f"cam_p{p}.json" in message for p in (1, 2, 3, 4)) and "HIEU_CHUAN_CAMERA" in message
    cameras, _, skipped = load_rig(calibration_dir=tmp_path, skip_uncalibrated=True)
    assert cameras == {} and sorted(skipped) == ["p1", "p2", "p3", "p4"]


def test_load_rig_combines_intrinsics_file_with_extrinsics(tmp_path):
    _write_intrinsics(tmp_path, 1)
    cameras, rig, skipped = load_rig(calibration_dir=tmp_path, sizes={1: (640, 480)})
    cam = cameras["p1"]
    assert skipped == {} and cam.extrinsics_measured is False and cam.direction == "front"
    assert cam.calibration.intrinsics.k[0] == pytest.approx(nominal_intrinsics().k[0])
    assert cam.calibration.extrinsics == rig.cameras[1].extrinsics
    assert cam.acceptance_all_pass is True and cam.intrinsics_source.endswith("cam_p1.json")
    with pytest.raises(RigConfigError, match="cam_p1_1280x720.json"):     # mode khác: tệp riêng, không dùng K của 640×480
        load_rig(calibration_dir=tmp_path, sizes={1: (1280, 720)})


# ---- BEV trên rig tổng hợp -------------------------------------------------------------------------------------------
def test_occupied_only_at_the_box_base_not_a_smear(full):
    gx, gy = centers()
    boxes = inside(FRONT_BOX, gx, gy) | inside(RIGHT_BOX, gx, gy)
    occupied = full.states == OCCUPIED
    assert occupied.any()
    # vật cao chiếu xuống sàn trải dài theo tia; quy tắc che khuất phải cắt phần đó: OCCUPIED chỉ trong hộp ± 1 ô
    assert not (occupied & ~dilate(boxes)).any()
    near_front = (np.abs(gx - 1.025) < 1e-6) & (np.abs(gy) < 0.15)          # mặt hộp hướng về camera trước
    near_right = (np.abs(gy + 0.825) < 1e-6) & (np.abs(gx) < 0.25)          # mặt hộp hướng về camera phải
    assert occupied[near_front].mean() >= 0.8 and occupied[near_right].mean() >= 0.8
    assert not (full.states[boxes] == FREE).any()                           # không ô nào trong hộp là FREE


def test_free_only_where_truly_free_and_visible(rig, full):
    cameras, ego = rig
    gx, gy = centers()
    visible = np.zeros(GRID.shape, bool)
    for cam in cameras.values():
        visible |= visible_from(cam, gx, gy)
    blocked_truth = inside(FRONT_BOX, gx, gy) | inside(RIGHT_BOX, gx, gy)
    band = inside(BAND, gx, gy)
    free = full.states == FREE
    assert not (free & blocked_truth).any()
    assert not (free & inside(BAND, gx, gy, shrink=0.05)).any()             # dải không chắc: không ô FREE nào
    assert not (free & ~dilate(visible)).any()                              # FREE phải được camera nào đó thấy (± 1 ô)
    core = erode(visible & ~dilate(blocked_truth | band) & ~ego.contains(gx, gy))
    assert core.sum() > 2000
    assert free[core].mean() >= 0.95                                        # mặt sàn trống thấy rõ: gần hết là FREE


def test_uncertain_band_stays_unknown(full):
    gx, gy = centers()
    band = inside(BAND, gx, gy, shrink=0.05)
    assert band.sum() > 50
    assert (full.states[band] == UNKNOWN).all()
    assert (full.category[band] == CAT_UNCERTAIN).mean() >= 0.9             # thấy nhưng không chắc, không phải "không thấy"


def test_cell_is_free_only_if_every_subcell_is_free(rig):
    cameras, ego = rig
    front = {"p1": cameras["p1"]}
    # dải không chắc bắt đầu 5 mm sau giữa ô x ∈ [0,80; 0,85]: nửa sau ô không chắc, nửa trước trống. Ở ~0,5 m trước
    # camera một pixel phủ ≈ 6 mm, nên hai ô con của ô đó thấy hai nhãn khác nhau, và góc của pixel không chắc đầu tiên
    # (≥ 0,827) không chạm nửa trước (xem test_blocked_pixel_footprint_straddling_a_subcell_removes_its_free).
    scene = SyntheticScene(patches=(SyntheticPatch(0.830, 1.0, -0.3, 0.3, 0.30),))
    result = build_bev({"p1": synthetic_prob_map(cameras["p1"].calibration, scene)}, front, GRID, max_range=MAX_RANGE,
                       ego=ego)
    for y in (-0.125, -0.025, 0.075):
        assert result.states[cell(0.775, y)] == FREE
        assert result.states[cell(0.825, y)] == UNKNOWN and result.category[cell(0.825, y)] == CAT_UNCERTAIN
        assert result.states[cell(0.875, y)] == UNKNOWN
        assert result.free_by[cell(0.825, y)] == 1                           # p1 thấy một phần ô trống: nguồn gốc vẫn ghi


def test_blocked_pixel_footprint_straddling_a_subcell_removes_its_free(rig):
    from autopark.perception.costmap import project_labels
    cameras, _ = rig
    cam = cameras["p1"]
    calib = cam.calibration
    fine = bev.fine_grid(GRID, 2)
    intr = calib.intrinsics
    u = int(round(intr.cx))
    vs = np.arange(0, intr.height - 1, dtype=np.float64)      # trục quang chạm sàn ≈ 0,21 m: 0,3–0,6 m ở nửa trên ảnh

    def sub(xy):
        return (np.floor((xy[:, 1] - fine.y_min) / fine.resolution).astype(int),
                np.floor((xy[:, 0] - fine.x_min) / fine.resolution).astype(int))

    centre, ok_c = calib.pixel_to_ground(np.full(vs.shape, float(u)), vs)
    corner, ok_k = calib.pixel_to_ground(np.full(vs.shape, u - 0.5), vs + 0.5)     # góc gần camera (dưới-trái)
    dist = np.hypot(centre[:, 0] - calib.extrinsics.translation[0], centre[:, 1])
    (rc, cc), (rk, ck) = sub(centre), sub(corner)
    # một pixel ~0,3–0,6 m trước camera có tâm trong ô con A nhưng góc gần rơi sang ô con B (gần camera hơn)
    pick = np.flatnonzero(ok_c & ok_k & (dist > 0.3) & (dist < 0.6) & (cc != ck))
    assert len(pick)
    i = int(pick[0])
    v = int(vs[i])
    a, b = (rc[i], cc[i]), (rk[i], ck[i])
    prob = np.zeros((intr.height, intr.width), np.float32)
    prob[v, u] = 1.0                                                         # một pixel BLOCKED duy nhất
    labels, _ = evidence_labels(prob)
    before = project_labels(labels, calib, fine, max_range=MAX_RANGE)
    assert before[b] == FREE                                                 # tâm ô con B đọc một pixel khác, trống
    view = bev.project_camera(prob, cam, GRID, max_range=MAX_RANGE)
    assert view.state_fine[b] == UNKNOWN and view.state_fine[a] != FREE     # góc chạm B → B không còn FREE
    side = (a[0] + 3, a[1])                                                  # lệch ngang 3 ô con: không bị gỡ
    assert before[side] == FREE and view.state_fine[side] == FREE
    assert (view.state_fine == FREE).sum() >= (before == FREE).sum() - 5    # tâm + 4 góc: gỡ tối đa 5 ô con


def test_blocked_pixel_just_beyond_range_still_removes_free_of_a_cell_inside_range(rig):
    # ô con có TÂM trong tầm nhưng mép xa nằm ngoài tầm: pixel BLOCKED mà tâm và bốn góc đều rơi vào phần ngoài tầm
    # của ô con đó vẫn phải gỡ FREE của nó (bảng pixel → ô con nới tầm thêm một cạnh ô con). Không nới thì ô vẫn FREE dù
    # camera thấy vật trong ô (kiểm đột biến tối 24/09: phép so ngẫu nhiên không gặp trường hợp này).
    from autopark.perception.costmap import project_labels
    cameras, _ = rig
    cam = cameras["p1"]
    calib, intr = cam.calibration, cam.calibration.intrinsics
    fine = bev.fine_grid(GRID, 2)
    reach = 0.6                                                              # ~0,3 m trước camera: pixel ≈ 1 cm < ô con
    cx, cy = calib.extrinsics.translation[:2]
    u, v = (a.ravel() for a in np.meshgrid(np.arange(intr.width, dtype=np.float64),
                                            np.arange(intr.height, dtype=np.float64)))

    def ground(du, dv):
        xy, ok = calib.pixel_to_ground(u + du, v + dv)
        return xy, np.where(ok, np.hypot(xy[:, 0] - cx, xy[:, 1] - cy), np.inf)

    centre, d_centre = ground(0.0, 0.0)
    beyond = np.isfinite(d_centre) & (d_centre > reach)                    # tia của tâm pixel chạm sàn, ngoài tầm
    for du in (-0.5, 0.5):
        for dv in (-0.5, 0.5):
            beyond &= ground(du, dv)[1] > reach                              # cả bốn góc cũng ngoài tầm
    row = np.floor((centre[:, 1] - fine.y_min) / fine.resolution)
    col = np.floor((centre[:, 0] - fine.x_min) / fine.resolution)
    gx, gy = fine.x_min + (col + 0.5) * fine.resolution, fine.y_min + (row + 0.5) * fine.resolution
    candidates = np.flatnonzero(beyond & (np.hypot(gx - cx, gy - cy) <= reach))  # ...nhưng trong ô con có tâm trong tầm
    assert len(candidates)
    checked = 0
    for i in candidates[:: max(1, len(candidates) // 10)]:
        prob = np.zeros((intr.height, intr.width), np.float32)
        prob[int(v[i]), int(u[i])] = 1.0                                     # một pixel BLOCKED duy nhất
        target = (int(row[i]), int(col[i]))
        before = project_labels(evidence_labels(prob)[0], calib, fine, max_range=reach)
        if before[target] != FREE:                                           # pixel đó là pixel tâm của chính ô con
            continue
        assert bev.project_camera(prob, cam, GRID, max_range=reach).state_fine[target] == UNKNOWN, target
        checked += 1
    assert checked >= 5


def test_thin_obstacle_between_subcell_centres_does_not_leave_its_cell_free(rig):
    cameras, ego = rig
    front = {"p1": cameras["p1"]}
    calib = cameras["p1"].calibration
    # cột 2 × 2 cm cao 20 cm trong ô tâm (0,575; 0,025), ≈ 0,25 m trước camera: rộng ≈ 25 px trong ảnh, camera thấy rõ.
    # Trước bản sửa 24/09 ô này là FREE (project_labels chỉ đọc pixel ở tâm các ô con, cột nằm giữa các tâm) và OCCUPIED
    # rơi sang ô xa hơn một ô.
    scene = SyntheticScene(boxes=(SyntheticBox(0.572, 0.592, 0.015, 0.035, 0.20),))
    result = build_bev({"p1": synthetic_prob_map(calib, scene)}, front, GRID, max_range=MAX_RANGE, ego=ego)
    assert result.states[cell(0.575, 0.025)] != FREE
    assert result.category[cell(0.575, 0.025)] == CAT_UNCERTAIN              # thấy nhưng không chắc trống
    assert result.states[cell(0.625, 0.025)] == OCCUPIED
    assert result.states[cell(0.575, -0.025)] == FREE and result.states[cell(0.575, 0.075)] == FREE   # không gỡ tràn
    # quét cột 1–2 cm ở nhiều vị trí trong ô: ô chứa cột không bao giờ FREE (trước bản sửa: 44/75 vị trí với cột 1 cm)
    target = cell(0.575, 0.025)
    for size in (0.010, 0.015, 0.020):
        for x0 in np.linspace(0.551, 0.599 - size, 4):
            box = SyntheticBox(x0, x0 + size, 0.012, 0.012 + size, 0.20)
            prob = synthetic_prob_map(calib, SyntheticScene(boxes=(box,)))
            states = build_bev({"p1": prob}, front, GRID, max_range=MAX_RANGE, ego=ego).states
            assert states[target] != FREE, f"cột {100 * size:.1f} cm ở x0 = {x0:.3f}: ô chứa cột vẫn FREE"


def test_behind_obstacle_under_car_and_out_of_range_are_unknown(rig, full):
    cameras, _ = rig
    gx, gy = centers()
    behind = (gx > 1.45) & (gx < 1.9) & (np.abs(gy) < 0.05)                 # sau hộp trước, nhìn từ camera trước
    visible_any = np.zeros(GRID.shape, bool)
    for cam in cameras.values():
        visible_any |= visible_from(cam, gx, gy)
    assert behind.sum() >= 8 and not visible_any[behind].any()             # sự thật độc lập: không camera nào thấy
    assert (full.states[behind] == UNKNOWN).all() and (full.category[behind] == CAT_OCCLUDED).all()
    assert full.in_view_by[behind].all()                                    # trong trường nhìn — bị che, không phải ngoài tầm
    r, c = cell(0.13, 0.0)
    assert full.states[r, c] == UNKNOWN and full.category[r, c] == CAT_EGO   # dưới thân xe
    assert (full.states[full.category == CAT_EGO] == UNKNOWN).all()
    r, c = cell(2.8, 2.8)
    assert full.states[r, c] == UNKNOWN and full.category[r, c] == CAT_UNSEEN


def test_ego_box_is_unknown_even_where_a_camera_sees_clear_ground(rig, probs):
    # với tư thế v0 không camera nào thấy trọn một ô dưới thân xe, nên ở rig thật quy tắc này không đổi trạng thái ô nào;
    # đặt một hộp "thân xe" giả trước camera trước, nơi p1 thấy sàn trống, để kiểm chính quy tắc
    cameras, _ = rig
    box = bev.EgoBox(0.6, 0.8, -0.1, 0.1)
    no_box = build_bev(probs, cameras, GRID, max_range=MAX_RANGE, ego=None)
    with_box = build_bev(probs, cameras, GRID, max_range=MAX_RANGE, ego=box)
    gx, gy = centers()
    under = box.contains(gx, gy)
    assert under.sum() >= 12 and (no_box.states[under] == FREE).all()
    assert (with_box.states[under] == UNKNOWN).all() and (with_box.category[under] == CAT_EGO).all()
    assert (with_box.states[~under] == no_box.states[~under]).all()


def test_missing_camera_leaves_its_area_unknown(rig, probs, full):
    cameras, ego = rig
    degraded = build_bev({**probs, "p2": None}, cameras, GRID, max_range=MAX_RANGE, ego=ego)
    gx, gy = centers()
    rear = (gx > -0.9) & (gx < -0.3) & (np.abs(gy) < 0.1)
    assert (full.states[rear] == FREE).all()
    assert (full.free_by[rear] & (1 << full.cameras.index("p2"))).all()     # nguồn gốc: p2 thấy trống
    assert (degraded.states[rear] == UNKNOWN).all() and (degraded.category[rear] == CAT_UNSEEN).all()
    assert "p2" in degraded.missing and "p2" not in degraded.views
    ahead = gx > 0.5
    assert (degraded.states[ahead] == full.states[ahead]).all()             # phần còn lại không đổi


def test_overlap_conflict_is_occupied(rig, probs, full):
    cameras, ego = rig
    b1, b3 = 1 << full.cameras.index("p1"), 1 << full.cameras.index("p3")
    both = (full.states == FREE) & ((full.free_by & b1) != 0) & ((full.free_by & b3) != 0)
    assert both.sum() >= 5                                                  # có vùng chồng lấn trước–trái
    rows, cols = np.nonzero(both)
    gx, gy = centers()
    margins = []                                                            # ô nằm sâu nhất trong ảnh của cả hai camera
    for r, c in zip(rows, cols):
        m = math.inf
        for name in ("p1", "p3"):
            intr = cameras[name].calibration.intrinsics
            u, v, ok = cameras[name].calibration.ground_to_pixel([[gx[r, c], gy[r, c]]])
            m = min(m, u[0], intr.width - 1 - u[0], v[0], intr.height - 1 - v[0]) if ok[0] else -1.0
        margins.append(m)
    k = int(np.argmax(margins))
    x, y, h = gx[rows[k], cols[k]], gy[rows[k], cols[k]], 1.5 * GRID.resolution
    # p1 báo nhầm: một mảng PHẲNG 3 × 3 ô trên sàn bị gọi là BLOCKED (vật giả không có chiều cao). Với p1, cạnh gần của
    # mảng là OCCUPIED và che phần sau; p3 vẫn thấy cả mảng trống. Ở ~1,6 m một pixel của p1 phủ ≈ 6 cm theo bán kính,
    # nên cạnh OCCUPIED có thể lệch sang ô bên cạnh: kiểm theo ĐÚNG các ô con xung đột, không theo một ô định trước.
    fake_scene = SyntheticScene(boxes=SCENE.boxes, patches=SCENE.patches + (SyntheticPatch(x - h, x + h, y - h, y + h, 0.98),))
    fake = synthetic_prob_map(cameras["p1"].calibration, fake_scene)
    result = build_bev({**probs, "p1": fake}, cameras, GRID, max_range=MAX_RANGE, ego=ego)
    kk = result.params["supersample"]
    fine_conflict = (result.views["p1"].state_fine == OCCUPIED) & (result.views["p3"].state_fine == FREE)
    cells = fine_conflict.reshape(GRID.shape[0], kk, GRID.shape[1], kk).any(axis=(1, 3))
    assert cells.any()
    assert (full.states[cells] == FREE).any()                               # trước khi p1 báo nhầm: ô đó FREE
    assert (result.states[cells] == OCCUPIED).all()                         # xung đột → OCCUPIED
    assert ((result.occupied_by[cells] & b1) != 0).all() and ((result.free_by[cells] & b3) != 0).all()
    assert np.array_equal(result.conflict, cells)
    assert result.conflict_pairs == {"p1 OCCUPIED / p3 FREE": int(cells.sum())}
    r, c = np.argwhere(cells)[0]
    assert result.camera_bits(result.occupied_by[r, c]) == ["p1"] and "p3" in result.camera_bits(result.free_by[r, c])
    assert not full.conflict.any()                                          # cảnh nhất quán: không xung đột


def test_merge_rules_on_hand_made_views():
    # hợp nhất kiểm trực tiếp trên hai "camera" dựng tay (lưới 2 × 4 ô, 2 × 2 ô con), không qua phép chiếu: test xung đột
    # ở trên phụ thuộc vào việc camera kia thấy trống đủ mọi ô con, điều mà hình học của rig không bảo đảm
    grid = GridSpec(0.0, 0.2, 0.0, 0.1, 0.05)
    k = 2
    shape = (grid.shape[0] * k, grid.shape[1] * k)
    a, b = np.full(shape, UNKNOWN, np.int8), np.full(shape, UNKNOWN, np.int8)
    seen_a, seen_b = np.zeros(shape, bool), np.zeros(shape, bool)
    a[0:2, 0:2], b[0:2, 0:2] = OCCUPIED, FREE           # ô (0,0): a OCCUPIED, b FREE cả ô → OCCUPIED, xung đột
    seen_a[0:2, 2:4], b[0:2, 2:4] = True, FREE           # ô (0,1): a thấy nhưng không chắc, b FREE → FREE
    a[0:2, 4], b[0:2, 5] = FREE, FREE                    # ô (0,2): mỗi camera thấy trống một nửa → FREE
    a[0:2, 6], a[0, 7] = FREE, FREE                      # ô (0,3): một ô con không ai thấy → UNKNOWN
    a[2, 0], b[2:4, 0:2] = OCCUPIED, FREE                # ô (1,0): a OCCUPIED một ô con, b FREE cả ô → OCCUPIED
    seen_a |= a != UNKNOWN
    seen_b |= b != UNKNOWN

    def view(name, state, seen):
        return bev.CameraView(name, state, seen, seen.copy(), np.zeros(grid.shape, np.int8), {}, (0, 0), 0.0)

    merged = bev.merge_views([view("a", a, seen_a), view("b", b, seen_b)], grid, ["a", "b"], k)
    states = merged["states"]
    assert states[0, 0] == OCCUPIED and states[1, 0] == OCCUPIED            # OCCUPIED thắng FREE
    assert states[0, 1] == FREE and merged["category"][0, 1] == bev.CAT_FREE   # "không chắc" không phủ quyết FREE
    assert states[0, 2] == FREE                                             # hợp nhất ở lưới mịn
    assert states[0, 3] == UNKNOWN and merged["category"][0, 3] == CAT_UNCERTAIN   # FREE cần mọi ô con
    assert states[1, 1] == UNKNOWN and merged["category"][1, 1] == CAT_UNSEEN
    assert merged["conflict"][0, 0] and merged["conflict"][1, 0] and merged["conflict"].sum() == 2
    assert merged["conflict_pairs"] == {"a OCCUPIED / b FREE": 2}
    assert merged["occupied_by"][0, 0] == 1 and merged["free_by"][0, 0] == 2 and merged["seen_by"][0, 1] == 3


def test_provenance_and_states_agree(full):
    assert full.cameras == ["p1", "p2", "p3", "p4"]
    free, occ = full.states == FREE, full.states == OCCUPIED
    assert (full.free_by[free] != 0).all() and (full.occupied_by[free] == 0).all()
    assert (full.occupied_by[occ] != 0).all()
    assert ((full.seen_by != 0) | ~(free | occ)).all()
    assert (full.in_view_by[full.seen_by != 0] != 0).all()                  # đã thấy thì phải trong vùng hình học
    assert (full.states[full.category == CAT_UNSEEN] == UNKNOWN).all()
    assert full.counts()["free"] == int(free.sum())


def test_costmap_contract_and_fusion_layer(full):
    from autopark.domain.types import Pose
    from autopark.fusion.layers import CameraSemanticLayer
    costmap = bev.bev_costmap(full, SourceStamp("bev_cameras", 1.0, True, "vehicle"))
    assert np.array_equal(np.array(costmap.cells, np.int8), full.states)
    assert costmap.origin.x == GRID.x_min and costmap.resolution_m == GRID.resolution
    r, c = cell(0.13, 0.0)
    assert costmap.blocked(r, c)                                            # UNKNOWN luôn bị chặn
    layer = CameraSemanticLayer(GRID)
    placed = layer.set_vehicle_frame(costmap, Pose(0.0, 0.0, 0.0))
    assert np.array_equal(np.array(placed.cells, np.int8), full.states)
    invalid = bev.bev_costmap(full, SourceStamp("bev_cameras", 1.0, False, "vehicle"))
    free_cell = tuple(int(i) for i in np.argwhere(full.states == FREE)[0])
    assert not costmap.blocked(*free_cell) and invalid.blocked(*free_cell)  # stamp không hợp lệ: mọi ô bị chặn


def test_four_cameras_6x6m_at_5cm_timing(rig, probs):
    cameras, ego = rig
    best = math.inf
    for _ in range(3):
        t0 = time.perf_counter()
        result = build_bev(probs, cameras, GRID, max_range=MAX_RANGE, ego=ego)
        best = min(best, time.perf_counter() - t0)
    assert GRID.shape == (120, 120) and len(result.views) == 4
    assert best < 1.0, f"4 camera, lưới 6×6 m ô 5 cm: {1000 * best:.0f} ms"   # đo máy bàn 24/09: ≈ 70 ms
    assert set(result.timing_ms["per_camera_ms"]) == {"p1", "p2", "p3", "p4"}


def test_build_bev_rejects_probability_without_calibration(rig, probs):
    cameras, _ = rig
    with pytest.raises(ValueError, match="không có hiệu chuẩn"):
        build_bev({**probs, "p9": probs["p1"]}, cameras, GRID)


# ---- tăng tốc (tối 24/09/2026): đường nhanh phải trùng TỪNG BIT với bản cũ -------------------------------------------
# Bản THAM CHIẾU dưới đây chép nguyên văn từ bev.py ở commit 9bcc30c (trước khi tăng tốc): mỗi khung, mỗi camera gọi
# costmap.project_labels HAI lượt (tính lại tâm ô → pixel, khoảng cách, phương vị) và tính vùng nhìn riêng; chỉ bảng
# pixel → ô con của lượt gỡ FREE được nhớ (lru_cache). Nó gọi thẳng costmap.project_labels, nên nếu ai sửa
# project_labels mà không sửa bảng dựng sẵn của bev.py thì test so sánh dưới đây hỏng. Dùng để (1) so kết quả trên đầu
# vào ngẫu nhiên, (2) đo tỉ lệ tăng tốc trên cùng máy, cùng tiến trình.
def _ref_as_probability(prob):
    a = np.asarray(prob)
    if a.ndim != 2:
        raise ValueError(f"bản đồ xác suất phải là ảnh một kênh (H, W), được {a.shape}")
    if a.dtype == np.uint8:
        return a.astype(np.float32) / 255.0
    a = a.astype(np.float32)
    finite = a[np.isfinite(a)]
    if finite.size and (finite.min() < 0.0 or finite.max() > 1.0):
        raise ValueError("xác suất số thực phải nằm trong [0, 1]")
    return a


def _ref_resize_probability(prob, width, height, *, aspect_tolerance=0.01):
    h, w = prob.shape
    if (w, h) == (width, height):
        return prob
    if abs((w / h) / (width / height) - 1.0) > aspect_tolerance:
        raise ValueError(f"bản đồ xác suất {w}×{h} khác tỉ lệ khung của hiệu chuẩn {width}×{height}: "
                         f"nhiều khả năng là mode camera khác, không dùng nội tham này được")
    interpolation = cv2.INTER_AREA if w > width else cv2.INTER_LINEAR
    return cv2.resize(prob.astype(np.float32), (width, height), interpolation=interpolation)


def _ref_evidence_labels(prob, t_free=bev.DEFAULT_T_FREE, t_blocked=bev.DEFAULT_T_BLOCKED, roi=None):
    bev.check_thresholds(t_free, t_blocked)
    p = _ref_as_probability(prob)
    finite = np.isfinite(p)
    free = finite & (p <= t_free)
    blocked = finite & (p >= t_blocked)
    uncertain = finite & ~free & ~blocked
    if roi is not None:
        if roi.shape != p.shape:
            raise ValueError(f"ROI {roi.shape} khác cỡ bản đồ xác suất {p.shape}")
        inside = roi > 0
        free &= inside
        blocked &= inside
        uncertain &= inside
    labels = np.full(p.shape, bev.LABEL_NONE, np.uint8)
    labels[free] = bev.LABEL_FREE
    labels[blocked] = bev.LABEL_BLOCKED
    return labels, uncertain


def _ref_any(a, k):
    return a.reshape(a.shape[0] // k, k, a.shape[1] // k, k).any(axis=(1, 3))


def _ref_all(a, k):
    return a.reshape(a.shape[0] // k, k, a.shape[1] // k, k).all(axis=(1, 3))


@lru_cache(maxsize=16)
def _ref_pixel_ground_cells(calib, fine, range_limit):
    intr = calib.intrinsics
    rows, cols = fine.shape

    def cells(u, v):
        xy, ok = calib.pixel_to_ground(u.ravel(), v.ravel(), max_range=range_limit)
        with np.errstate(invalid="ignore"):
            ci = np.floor((xy[:, 0] - fine.x_min) / fine.resolution)
            ri = np.floor((xy[:, 1] - fine.y_min) / fine.resolution)
            inside_ = ok & (ci >= 0) & (ci < cols) & (ri >= 0) & (ri < rows)
        index = np.full(u.size, -1, np.int32)
        index[inside_] = (ri[inside_] * cols + ci[inside_]).astype(np.int32)
        index = index.reshape(u.shape)
        index.flags.writeable = False
        return index

    center = cells(*np.meshgrid(np.arange(intr.width, dtype=np.float64), np.arange(intr.height, dtype=np.float64)))
    corner = cells(*np.meshgrid(np.arange(intr.width + 1, dtype=np.float64) - 0.5,
                                np.arange(intr.height + 1, dtype=np.float64) - 0.5))
    return center, corner


def _ref_not_free_hits(labels, uncertain, calib, fine, max_range):
    mask = (labels == bev.LABEL_BLOCKED) | uncertain
    rows, cols = fine.shape
    hit = np.zeros(rows * cols, bool)
    if mask.any():
        limit = None if max_range is None else float(max_range) + fine.resolution
        center, corner = _ref_pixel_ground_cells(calib, fine, limit)
        touched = np.zeros(corner.shape, bool)
        touched[:-1, :-1] |= mask
        touched[:-1, 1:] |= mask
        touched[1:, :-1] |= mask
        touched[1:, 1:] |= mask
        index = np.concatenate([center[mask], corner[touched]])
        hit[index[index >= 0]] = True
    return hit.reshape(rows, cols)


def _ref_project_camera(prob, camera, grid, *, t_free, t_blocked, max_range, supersample, azimuth_bin_deg):
    from autopark.perception.costmap import project_labels
    calib = camera.calibration
    intr = calib.intrinsics
    raw = _ref_as_probability(prob)
    p = _ref_resize_probability(raw, intr.width, intr.height)
    labels, uncertain = _ref_evidence_labels(p, t_free, t_blocked, camera.roi)
    fine = bev.fine_grid(grid, supersample)
    state_f = project_labels(labels, calib, fine, max_range=max_range, azimuth_bin_deg=azimuth_bin_deg)
    state_f[_ref_not_free_hits(labels, uncertain, calib, fine, max_range) & (state_f == FREE)] = UNKNOWN
    seen_labels = labels.copy()
    seen_labels[uncertain] = bev.LABEL_FREE
    seen_f = project_labels(seen_labels, calib, fine, max_range=max_range, azimuth_bin_deg=azimuth_bin_deg) != UNKNOWN
    gx, gy = fine.centers()
    u, v, valid = calib.ground_to_pixel(np.column_stack([gx.ravel(), gy.ravel()]))
    usable_px = (labels != bev.LABEL_NONE) | uncertain
    in_view_f = valid.copy()
    in_view_f[valid] = usable_px[np.rint(v[valid]).astype(np.int64), np.rint(u[valid]).astype(np.int64)]
    if max_range is not None:
        cx, cy = calib.extrinsics.translation[:2]
        in_view_f &= np.hypot(gx.ravel() - cx, gy.ravel() - cy) <= max_range
    in_view_f = in_view_f.reshape(fine.shape)
    k = int(supersample)
    state = np.full(grid.shape, UNKNOWN, np.int8)
    state[_ref_all(state_f == FREE, k)] = FREE
    state[_ref_any(state_f == OCCUPIED, k)] = OCCUPIED
    total = labels.size
    fractions = {"free": float((labels == bev.LABEL_FREE).sum() / total),
                 "uncertain": float(uncertain.sum() / total),
                 "blocked": float((labels == bev.LABEL_BLOCKED).sum() / total),
                 "no_evidence": float(((labels == bev.LABEL_NONE) & ~uncertain).sum() / total)}
    return bev.CameraView(camera.name, state_f, seen_f, in_view_f, state, fractions,
                          (int(raw.shape[1]), int(raw.shape[0])), 0.0)


def _ref_merge_views(views, grid, names, supersample, ego=None):
    k = int(supersample)
    rows, cols = grid.shape
    fine_shape = (rows * k, cols * k)
    seen_by, free_by, occupied_by, in_view_by = (np.zeros((rows, cols), np.uint16) for _ in range(4))
    occupied_f = np.zeros(fine_shape, bool)
    free_f = np.zeros(fine_shape, bool)
    for view in views:
        bit = np.uint16(1 << names.index(view.name))
        occ, fr = view.state_fine == OCCUPIED, view.state_fine == FREE
        occupied_by[_ref_any(occ, k)] |= bit
        free_by[_ref_any(fr, k)] |= bit
        seen_by[_ref_any(view.seen_fine, k)] |= bit
        in_view_by[_ref_any(view.in_view_fine, k)] |= bit
        occupied_f |= occ
        free_f |= fr
    conflict_f = np.zeros(fine_shape, bool)
    pairs = {}
    for a in views:
        for b in views:
            if a is not b:
                both = (a.state_fine == OCCUPIED) & (b.state_fine == FREE)
                if both.any():
                    conflict_f |= both
                    pairs[f"{a.name} OCCUPIED / {b.name} FREE"] = int(_ref_any(both, k).sum())
    states = np.full((rows, cols), UNKNOWN, np.int8)
    states[_ref_all(free_f & ~occupied_f, k)] = FREE
    states[_ref_any(occupied_f, k)] = OCCUPIED
    category = np.full((rows, cols), CAT_UNSEEN, np.uint8)
    category[in_view_by != 0] = CAT_OCCLUDED
    category[seen_by != 0] = CAT_UNCERTAIN
    under = None
    if ego is not None:
        gx, gy = grid.centers()
        under = ego.contains(gx, gy)
        states[under] = UNKNOWN
    category[states == FREE] = bev.CAT_FREE
    category[states == OCCUPIED] = bev.CAT_OCCUPIED
    if under is not None:
        category[under] = CAT_EGO
    return {"states": states, "category": category, "seen_by": seen_by, "free_by": free_by,
            "occupied_by": occupied_by, "in_view_by": in_view_by, "conflict": _ref_any(conflict_f, k),
            "conflict_pairs": pairs}


def _ref_build_bev(probs, cameras, grid, *, t_free=bev.DEFAULT_T_FREE, t_blocked=bev.DEFAULT_T_BLOCKED,
                   max_range=bev.RIG_MAX_RANGE, supersample=bev.DEFAULT_SUPERSAMPLE,
                   azimuth_bin_deg=bev.DEFAULT_AZIMUTH_BIN_DEG, ego=None):
    names = list(cameras)
    views = [_ref_project_camera(probs[n], cameras[n], grid, t_free=t_free, t_blocked=t_blocked, max_range=max_range,
                                 supersample=supersample, azimuth_bin_deg=azimuth_bin_deg)
             for n in names if probs.get(n) is not None]
    return views, _ref_merge_views(views, grid, names, supersample, ego)


def _outcome(fn):
    try:
        return "ok", fn()
    except ValueError as exc:
        return "ValueError", str(exc)


def _assert_same_as_reference(probs, cameras, grid, ego=None, **kw):
    """Chạy build_bev (đường nhanh) và bản tham chiếu; mọi mảng phải trùng dtype, cỡ và từng phần tử. Trả True nếu chạy
    được, False nếu cả hai cùng từ chối với cùng thông báo."""
    fast = _outcome(lambda: build_bev(probs, cameras, grid, ego=ego, **kw))
    ref = _outcome(lambda: _ref_build_bev(probs, cameras, grid, ego=ego, **kw))
    assert fast[0] == ref[0], (fast, ref)
    if fast[0] != "ok":
        assert fast[1] == ref[1]
        return False
    result, (ref_views, ref_merged) = fast[1], ref[1]
    for key, expected in ref_merged.items():
        got = getattr(result, key)
        if isinstance(expected, np.ndarray):
            assert got.dtype == expected.dtype and got.shape == expected.shape and np.array_equal(got, expected), key
        else:
            assert got == expected and list(got) == list(expected), key          # cùng cả thứ tự cặp xung đột
    assert list(result.views) == [v.name for v in ref_views]
    for ref_view in ref_views:
        view = result.views[ref_view.name]
        for key in ("state_fine", "seen_fine", "in_view_fine", "state"):
            got, expected = getattr(view, key), getattr(ref_view, key)
            assert got.dtype == expected.dtype and got.shape == expected.shape, (ref_view.name, key)
            assert np.array_equal(got, expected), (ref_view.name, key, int((got != expected).sum()))
        assert view.pixel_fractions == ref_view.pixel_fractions and view.prob_size == ref_view.prob_size
    return True


def _random_camera(rng, name, size):
    from autopark.perception.calibration import CameraCalibration, Extrinsics, FisheyeIntrinsics
    w, h = size
    base = nominal_intrinsics(w, h, float(rng.uniform(100.0, 200.0)))
    k1 = base.k[0]
    k = (k1, float(k1 * rng.uniform(-0.05, 0.05)), float(k1 * rng.uniform(-0.02, 0.02)),
         float(k1 * rng.uniform(-0.005, 0.005)))
    try:
        intr = FisheyeIntrinsics(w, h, k, float(rng.uniform(-3, 3)), float(rng.uniform(-3, 3)),
                                 float(rng.uniform(0.999, 1.001)), math.radians(float(rng.uniform(80.0, 100.0))))
    except ValueError:                                                      # đa thức không đơn điệu tới theta_max
        intr = base
    rotation = rig_rotation(float(rng.uniform(-180, 180)), float(rng.uniform(5, 88)), float(rng.uniform(-15, 15)))
    position = (float(rng.uniform(-0.5, 0.5)), float(rng.uniform(-0.5, 0.5)), float(rng.uniform(0.05, 0.4)))
    roi = None if rng.random() < 0.7 else (rng.random((h, w)) < 0.8).astype(np.uint8) * 255
    return bev.BevCamera(name, CameraCalibration(name, intr, Extrinsics.from_matrix(rotation, position)), roi)


def _random_probability(rng, calibration, out_size):
    """Bản đồ xác suất đủ kiểu: nhiễu đều (nhiều ô OCCUPIED lẻ, che khuất dày), cảnh hộp tổng hợp, khối có NaN, P×255
    quanh hai ngưỡng; thêm giá trị đúng bằng ngưỡng và +inf; cỡ khác cỡ hiệu chuẩn (phóng to / thu nhỏ)."""
    w, h = out_size
    kind = int(rng.integers(0, 4))
    if kind == 0:
        p = rng.random((h, w)).astype(np.float32)
    elif kind == 1:
        boxes = tuple(SyntheticBox(x, x + rng.uniform(0.01, 0.3), y, y + rng.uniform(0.01, 0.3), rng.uniform(0.0, 0.3))
                      for x, y in rng.uniform(-1.5, 1.5, (int(rng.integers(0, 5)), 2)))
        patches = tuple(SyntheticPatch(x, x + 0.3, y, y + 0.3, float(rng.choice([0.3, 0.15, 0.5, 0.98])))
                        for x, y in rng.uniform(-1.5, 1.5, (int(rng.integers(0, 3)), 2)))
        p = synthetic_prob_map(calibration, SyntheticScene(boxes, patches), out_size=(w, h))
    elif kind == 2:
        p = np.kron(rng.random((h // 8 + 1, w // 8 + 1)), np.ones((8, 8)))[:h, :w]      # float64
        p[rng.random((h, w)) < 0.05] = np.nan
    else:
        return rng.choice(np.array([0, 38, 39, 127, 128, 200, 255, 10], np.uint8), (h, w))
    if rng.random() < 0.3:
        p[rng.random((h, w)) < 0.02] = 0.15
        p[rng.random((h, w)) < 0.02] = 0.5
    if rng.random() < 0.15:
        p[rng.random((h, w)) < 0.01] = np.inf                                # không hữu hạn: không có bằng chứng
    return p


def test_fast_path_matches_reference_bit_for_bit_on_random_inputs(rig):
    rng = np.random.default_rng(20260925)
    ran = 0
    # (1) camera ngẫu nhiên (ảnh nhỏ cho nhanh): nội tham, tư thế, ROI, ngưỡng, lưới, supersample, tầm, bin phương vị,
    # hộp thân xe, camera thiếu dữ liệu — đều ngẫu nhiên
    for trial in range(45):
        cameras = {f"c{i}": _random_camera(rng, f"c{i}", [(160, 120), (97, 73), (120, 90)][int(rng.integers(0, 3))])
                   for i in range(int(rng.integers(1, 5)))}
        probs = {}
        for name, cam in cameras.items():
            intr = cam.calibration.intrinsics
            scale = float(rng.choice([1.0, 0.75, 0.5, 1.5]))
            size = (max(2, round(intr.width * scale)), max(2, round(intr.height * scale)))
            probs[name] = None if rng.random() < 0.1 else _random_probability(rng, cam.calibration, size)
        res = float(rng.choice([0.05, 0.1, 0.04]))
        half = res * int(rng.integers(10, 30))
        grid = GridSpec(-half, half + res * int(rng.integers(0, 8)), -half, half, res)
        kw = dict(t_free=float(rng.choice([0.15, 0.1, 0.3, 0.0])), t_blocked=float(rng.choice([0.5, 0.6, 1.0])),
                  max_range=[None, 2.0, 1.0, 3.5][int(rng.integers(0, 4))], supersample=int(rng.integers(1, 4)),
                  azimuth_bin_deg=float(rng.choice([0.5, 1.0, 0.25, 2.0])))
        ego = None if rng.random() < 0.5 else bev.EgoBox(-0.1, 0.3, -0.1, 0.1)
        ran += _assert_same_as_reference(probs, cameras, grid, ego, **kw)
    assert ran >= 35                                                        # phần lớn chạy được, không chỉ cùng từ chối
    # (2) rig tổng hợp 640×480, bản đồ cỡ hiển thị 480×360 của các cảnh ngẫu nhiên (supersample 3 đã có ở phần (1);
    # ở rig nó chỉ làm test chậm vì phải dựng bảng mới cho cả hai bản)
    cameras, ego = rig
    for supersample, max_range in ((2, MAX_RANGE), (2, MAX_RANGE), (1, None)):
        probs = {n: _random_probability(rng, c.calibration, DISPLAY) for n, c in cameras.items()}
        assert _assert_same_as_reference(probs, cameras, GRID, ego, max_range=max_range, supersample=supersample)
    # (3) camera nhìn gần thẳng xuống từ đúng tâm một ô con, mọi pixel BLOCKED: ô chứa camera che MỌI phương vị
    from autopark.perception.calibration import CameraCalibration, Extrinsics
    grid = GridSpec(-1.0, 1.0, -1.0, 1.0, 0.05)
    down = bev.BevCamera("down", CameraCalibration("down", nominal_intrinsics(120, 90), Extrinsics.from_matrix(
        rig_rotation(0.0, 89.0), (0.0125, 0.0125, 0.2))))
    blocked = {"down": np.ones((90, 120), np.float32)}
    assert _assert_same_as_reference(blocked, {"down": down}, grid, max_range=None)
    view = build_bev(blocked, {"down": down}, grid, max_range=None).views["down"]
    assert (view.state_fine == OCCUPIED).sum() == 1 and view.seen_fine.sum() == 1 and view.in_view_fine.sum() > 100
    # (4) từ chối như bản cũ, cùng thông báo: xác suất ngoài [0, 1], ROI sai cỡ
    cam = _random_camera(rng, "e", (120, 90))
    bad = np.full((90, 120), 0.2, np.float32)
    bad[3, 4] = 1.5
    assert not _assert_same_as_reference({"e": bad}, {"e": cam}, grid)
    wrong_roi = bev.BevCamera("r", cam.calibration, np.full((45, 60), 255, np.uint8))
    assert not _assert_same_as_reference({"r": np.zeros((90, 120), np.float32)}, {"r": wrong_roi}, grid)
    # (5) as_probability vẫn trả mảng MỚI (không trùng bộ nhớ đầu vào) và cùng giá trị với bản cũ ở cả 256 mức P×255
    src = np.zeros((2, 3), np.float32)
    out = bev.as_probability(src)
    out[0, 0] = 1.0
    assert src[0, 0] == 0.0
    levels = np.arange(256, dtype=np.uint8).reshape(16, 16)
    assert np.array_equal(bev.as_probability(levels), _ref_as_probability(levels))
    # (6) hai ngưỡng trùng nhau sau khi làm tròn về float32: pixel p = 0,5 vừa ≤ t_free vừa ≥ t_blocked, bản cũ gọi là
    # BLOCKED (không phải "không chắc"); đường nhanh phải cho cùng kết quả
    edge = np.array([[0.5, 0.4, 0.6, 0.5000001]], np.float32)
    for t_free, t_blocked in ((0.5, 0.5 + 1e-9), (0.4, 0.4 + 1e-12), (0.15, 0.5)):
        fast, ref = evidence_labels(edge, t_free, t_blocked), _ref_evidence_labels(edge, t_free, t_blocked)
        assert np.array_equal(fast[0], ref[0]) and np.array_equal(fast[1], ref[1]), (t_free, t_blocked)
    assert evidence_labels(edge, 0.5, 0.5 + 1e-9)[0][0, 0] == bev.LABEL_BLOCKED


def test_geometry_tables_are_built_once_and_read_only(rig, probs):
    cameras, ego = rig
    build_bev(probs, cameras, GRID, max_range=MAX_RANGE, ego=ego)         # dựng (hoặc đã có) bảng của bốn camera
    before = bev.view_geometry.cache_info()
    build_bev(probs, cameras, GRID, max_range=MAX_RANGE, ego=ego)
    after = bev.view_geometry.cache_info()
    assert after.misses == before.misses and after.hits == before.hits + 4   # khung sau: không dựng lại gì
    fine = bev.fine_grid(GRID, bev.DEFAULT_SUPERSAMPLE)
    geometry = bev.view_geometry(cameras["p1"].calibration, fine, MAX_RANGE, bev.DEFAULT_AZIMUTH_BIN_DEG)
    # khóa gồm tầm và bin phương vị (và hiệu chuẩn, lưới): đổi một thứ là bảng khác
    assert bev.view_geometry(cameras["p1"].calibration, fine, 1.0, bev.DEFAULT_AZIMUTH_BIN_DEG) is not geometry
    assert bev.view_geometry(cameras["p1"].calibration, fine, MAX_RANGE, 1.0) is not geometry
    with pytest.raises(ValueError):
        geometry.cells[0] = 0                                               # bảng dùng chung giữa các khung: chỉ đọc
    assert geometry.nbytes() < 8e6                                          # tối 24/09: ≈ 2,9 MB (640×480, tầm 2 m)


def test_invalid_max_range_is_rejected_at_every_entry_point(rig, probs, tmp_path, capsys):
    # (25/09/2026) max_range NaN từng chạy qua: bỏ giới hạn tầm, tắt lượt gỡ FREE vật mảnh (pixel_to_ground loại mọi
    # pixel) và vùng nhìn khác bản cũ 9bcc30c (in_view_fine khác 11 431–16 428 ô con mỗi camera của rig) — nay bị từ chối
    # ở mọi lối vào công khai, cùng ≤ 0 (vùng nhìn rỗng) và giá trị không phải số
    cameras, ego = rig
    cam = cameras["p1"]
    fine = bev.fine_grid(GRID, bev.DEFAULT_SUPERSAMPLE)
    for bad in (float("nan"), math.nan, np.float32("nan"), 0.0, -1.0, "abc"):
        with pytest.raises(ValueError, match="max_range"):
            build_bev(probs, cameras, GRID, max_range=bad, ego=ego)
        with pytest.raises(ValueError, match="max_range"):
            build_bev({}, cameras, GRID, max_range=bad, ego=ego)       # kiểm trước mọi camera, kể cả khi không chiếu gì
        with pytest.raises(ValueError, match="max_range"):
            bev.project_camera(probs["p1"], cam, GRID, max_range=bad)
        with pytest.raises(ValueError, match="max_range"):                  # kiểm tầm trước cả bản đồ xác suất
            bev.project_camera(np.zeros((2, 2, 3), np.float32), cam, GRID, max_range=bad)
        for _ in range(2):          # lỗi không được lru_cache nhớ; math.nan là cùng một đối tượng nên khóa trùng nhau
            with pytest.raises(ValueError, match="max_range"):
                bev.view_geometry(cam.calibration, fine, bad, bev.DEFAULT_AZIMUTH_BIN_DEG)
    # bộ ảnh: từ chối trước khi đọc thư mục (thư mục không tồn tại vẫn ra lỗi tầm, không phải lỗi thiếu tệp)
    with pytest.raises(ValueError, match="max_range"):
        bev.bev_from_snapshot(tmp_path / "khong_co", max_range=math.nan)
    # None và +inf vẫn nhận, +inf cho đúng kết quả như None (không giới hạn tầm)
    front = {"p1": cam}
    unlimited = build_bev({"p1": probs["p1"]}, front, GRID, max_range=None, ego=ego)
    infinite = build_bev({"p1": probs["p1"]}, front, GRID, max_range=math.inf, ego=ego)
    for key in ("states", "category", "seen_by", "free_by", "occupied_by", "in_view_by", "conflict"):
        assert np.array_equal(getattr(infinite, key), getattr(unlimited, key)), key
    assert np.array_equal(infinite.views["p1"].in_view_fine, unlimited.views["p1"].in_view_fine)
    assert infinite.views["p1"].in_view_fine.sum() > build_bev({"p1": probs["p1"]}, front, GRID, max_range=MAX_RANGE,
                                                               ego=ego).views["p1"].in_view_fine.sum()
    # dòng lệnh: từ chối lúc đọc tham số (mã 2), trước khi tính — kể cả ±inf vì stats.json không ghi được inf
    for command, value in (("bench", "nan"), ("synthetic", "nan"), ("bench", "inf"), ("bench", "-inf"),
                           ("bench", "0"), ("bench", "-2"), ("bench", "hai")):
        out = tmp_path / f"cli_{command}_{value}"
        with pytest.raises(SystemExit) as stop:
            bev.main([command, "--max-range", value, "--out", str(out)])
        assert stop.value.code == 2 and not out.exists(), (command, value)
        assert "--max-range" in capsys.readouterr().err, (command, value)


def test_bench_cli_writes_timing_report(tmp_path, capsys):
    out = tmp_path / "bench"
    assert bev.main(["bench", "--repeat", "2", "--out", str(out)]) == 0
    report = json.loads((out / "bench.json").read_text(encoding="utf-8"))
    assert report["kind"] == "autopark_bev_bench_v0" and report["warm_ms"]["repeat"] == 2
    assert 0 < report["warm_ms"]["best"] <= report["warm_ms"]["median"] <= report["warm_ms"]["max"]
    assert report["first_call_ms"] > 0 and sorted(report["warm_best_per_camera_ms"]) == ["p1", "p2", "p3", "p4"]
    assert report["params"]["grid"]["shape_rows_cols"] == [120, 120] and report["params"]["supersample"] == 2
    assert all(n > 0 for n in report["geometry_table_bytes"].values())
    assert "KHÔNG phải ảnh thật" in report["input"]["kind"]
    assert "bench.json" in capsys.readouterr().out
    bad = tmp_path / "bad"
    assert bev.main(["bench", "--repeat", "0", "--out", str(bad)]) == 2 and not bad.exists()
    assert "--repeat" in capsys.readouterr().err


@pytest.mark.planner_budget           # đo thời gian thật: chạy ngoài lượt coverage, như các test ngân sách thời gian
def test_fast_path_speedup_over_reference(rig, probs):
    # tỉ lệ đo trên CÙNG máy, cùng tiến trình, xen kẽ hai bản, lấy lần nhanh nhất: bền hơn một cận tuyệt đối khi máy
    # chậm hay bận. Máy bàn tối 24/09 (tác tử khác chạy song song), lần nhanh nhất: bản cũ ≈ 60–104 ms, đường nhanh
    # ≈ 7–9 ms (≈ 8–12 lần; docs/BEV.md mục 6).
    cameras, ego = rig
    kw = dict(max_range=MAX_RANGE, supersample=2, ego=ego)
    _ref_build_bev(probs, cameras, GRID, **kw)                              # làm nóng bộ nhớ đệm của cả hai bản
    build_bev(probs, cameras, GRID, **kw)
    best_ref = best_fast = math.inf
    for _ in range(5):
        t0 = time.perf_counter()
        _ref_build_bev(probs, cameras, GRID, **kw)
        t1 = time.perf_counter()
        build_bev(probs, cameras, GRID, **kw)
        t2 = time.perf_counter()
        best_ref, best_fast = min(best_ref, t1 - t0), min(best_fast, t2 - t1)
    assert best_ref / best_fast >= 3.0, f"bản cũ {1000 * best_ref:.1f} ms, đường nhanh {1000 * best_fast:.1f} ms"
    assert best_fast < 0.25, f"4 camera, lưới 6×6 m ô 5 cm: {1000 * best_fast:.1f} ms"


# ---- dòng lệnh: bộ ảnh bàn thử ---------------------------------------------------------------------------------------
def _write_png(path, image):
    ok, buf = cv2.imencode(".png", image)
    assert ok
    path.write_bytes(buf.tobytes())


def _snapshot(folder, probs, meta_cameras):
    folder.mkdir(parents=True)
    for name, prob in probs.items():
        _write_png(folder / f"prob_blocked_{name}.png", prob)
    meta = {"created_local": "2026-09-24T10:00:00.000", "clock": {"name": "perf_counter"}, "t_capture_s": 100.5,
            "threshold": 0.15, "source": "ai_set", "model": "tong_hop", "checkpoint": None,
            "camera_mode": {"width": 640, "height": 480, "fps": 30.0, "fourcc": "MJPG"}, "cameras": meta_cameras}
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _meta_cameras(**changes):
    cams = {str(p): {"stamp_s": 100.0 + 0.004 * p, "width": 640, "height": 480, "bottom_repeat_share": 0.05,
                     "prob_size": list(DISPLAY)} for p in (1, 2, 3, 4)}
    for port, update in changes.items():
        cams[port[1:]].update(update)
    return cams


def test_snapshot_cli_end_to_end(tmp_path, probs, full):
    from autopark.fusion.layers import read_costmap_json
    calib = tmp_path / "calibration"
    for port in (1, 2, 3, 4):
        _write_intrinsics(calib, port)
    snap = tmp_path / "rig_snapshots" / "20260924_100000_000"
    _snapshot(snap, probs, _meta_cameras())
    out = tmp_path / "bev_out"
    assert bev.main(["snapshot", str(snap), "--calibration-dir", str(calib), "--out", str(out)]) == 0
    assert {p.name for p in out.iterdir()} == {"bev.png", "costmap.json", "stats.json"}
    costmap = read_costmap_json(out / "costmap.json")
    states = np.array(costmap.cells, np.int8)
    assert (states == full.states).mean() > 0.99                            # cùng hình học với rig tổng hợp
    assert costmap.stamp.valid is False and costmap.stamp.frame_id == "vehicle" and costmap.stamp.t == pytest.approx(100.004)
    stats = json.loads((out / "stats.json").read_text(encoding="utf-8"))
    assert stats["usable_for_planning"] is False
    assert any("GIẢ ĐỊNH — CHƯA ĐO" in r for r in stats["unusable_reasons"])
    assert any("chưa có ROI" in r for r in stats["unusable_reasons"])
    assert all(stats["cameras"][f"p{p}"]["used"] for p in (1, 2, 3, 4))
    provenance = json.loads((out / "costmap.json").read_text(encoding="utf-8"))["provenance"]
    assert provenance["cameras"] == ["p1", "p2", "p3", "p4"] and len(provenance["seen_by"]) == GRID.shape[0]
    image = cv2.imdecode(np.fromfile(str(out / "bev.png"), np.uint8), cv2.IMREAD_COLOR)
    assert image is not None and image.shape[1] > 2 * GRID.shape[1]

    # camera khung nghi hỏng (p3) và lệch thời gian (p4) bị bỏ; p1, p2 cùng nhóm đồng bộ được dùng
    snap2 = tmp_path / "rig_snapshots" / "20260924_100100_000"
    _snapshot(snap2, probs, _meta_cameras(p3={"bottom_repeat_share": 0.9}, p4={"stamp_s": 100.5}))
    out2 = tmp_path / "bev_out2"
    assert bev.main(["snapshot", str(snap2), "--calibration-dir", str(calib), "--out", str(out2)]) == 0
    cams = json.loads((out2 / "stats.json").read_text(encoding="utf-8"))["cameras"]
    assert cams["p1"]["used"] and cams["p2"]["used"] and not cams["p3"]["used"] and not cams["p4"]["used"]
    assert "bottom_repeat_share" in cams["p3"]["reason"] and "lệch +49" in cams["p4"]["reason"]

    # thiếu xác suất của p2 (AI tắt / camera ngoài bộ): vùng chỉ p2 thấy là UNKNOWN
    snap3 = tmp_path / "rig_snapshots" / "20260924_100200_000"
    _snapshot(snap3, {k: v for k, v in probs.items() if k != "p2"}, _meta_cameras())
    out3 = tmp_path / "bev_out3"
    assert bev.main(["snapshot", str(snap3), "--calibration-dir", str(calib), "--out", str(out3)]) == 0
    cams = json.loads((out3 / "stats.json").read_text(encoding="utf-8"))["cameras"]
    assert not cams["p2"]["used"] and "prob_blocked" in cams["p2"]["reason"]
    assert all(cams[n]["used"] for n in ("p1", "p3", "p4"))
    states3 = np.array(read_costmap_json(out3 / "costmap.json").cells, np.int8)
    gx, gy = centers()
    rear = (gx > -0.9) & (gx < -0.3) & (np.abs(gy) < 0.1)
    assert (states3[rear] == UNKNOWN).all() and (full.states[rear] == FREE).all()


def test_failed_intrinsics_acceptance_alone_blocks_planning(tmp_path, probs):
    from autopark.fusion.layers import read_costmap_json
    raw = json.loads((PROJECT_ROOT / "configs/rig/camera_rig_extrinsics_v0.json").read_text(encoding="utf-8"))
    for c in raw["cameras"].values():
        c["measured"] = True          # CHỈ trong test: tách lý do acceptance khỏi lý do ngoại tham chưa đo
    extrinsics = tmp_path / "rig_measured.json"
    extrinsics.write_text(json.dumps(raw), encoding="utf-8")
    roi_dir, calib = tmp_path / "roi", tmp_path / "calibration"
    roi_dir.mkdir()
    for port in (1, 2, 3, 4):
        _write_png(roi_dir / f"roi_p{port}.png", np.full((480, 640), 255, np.uint8))
        _write_intrinsics(calib, port)
    snap = tmp_path / "snap"
    _snapshot(snap, probs, _meta_cameras())
    args = ["snapshot", str(snap), "--calibration-dir", str(calib), "--extrinsics", str(extrinsics),
            "--roi-dir", str(roi_dir)]
    good = tmp_path / "good"          # đối chứng: đo + ROI + all_pass true → dùng được
    assert bev.main([*args, "--out", str(good)]) == 0
    stats = json.loads((good / "stats.json").read_text(encoding="utf-8"))
    assert stats["unusable_reasons"] == [] and stats["usable_for_planning"] is True
    assert read_costmap_json(good / "costmap.json").stamp.valid is True
    _write_intrinsics(calib, 2, all_pass=False)   # chỉ đổi acceptance của p2
    bad = tmp_path / "bad"
    assert bev.main([*args, "--out", str(bad)]) == 0
    stats = json.loads((bad / "stats.json").read_text(encoding="utf-8"))
    assert stats["usable_for_planning"] is False and stats["cameras"]["p2"]["intrinsics_acceptance_all_pass"] is False
    assert stats["unusable_reasons"] == ["p2: nội tham chưa đạt tiêu chí đề xuất (acceptance.all_pass = false)"]
    assert read_costmap_json(bad / "costmap.json").stamp.valid is False


def _noise_frame(rng, shape=(480, 640, 3)):
    return rng.integers(0, 256, shape, dtype=np.uint8)


def _paint_repeating(image, rows, col0, rng):
    """Như bộ giải mã tô phần thiếu của khung MJPEG: một khối 8×8 lặp theo chiều ngang từ cột col0 tới mép phải."""
    tile = np.repeat(rng.integers(0, 256, (len(range(*rows.indices(image.shape[0]))), 8, 1), dtype=np.uint8), 3, axis=2)
    width = image.shape[1] - col0
    image[rows, col0:] = np.tile(tile, (1, width // 8 + 1, 1))[:, :width]
    return image


def _damage_snapshot(tmp_path, probs, frames, meta_changes):
    calib = tmp_path / "calibration"
    for port in (1, 2, 3, 4):
        _write_intrinsics(calib, port)
    snap = tmp_path / "snap"
    meta = _meta_cameras()
    for name, drop_keys in meta_changes.items():
        for key in drop_keys:
            meta[name[1:]].pop(key)
    _snapshot(snap, probs, meta)
    for name, frame in frames.items():
        _write_png(snap / f"cam_{name}.png", frame)
    return snap, calib


def test_snapshot_old_format_frames_are_checked_on_the_image(tmp_path, probs):
    # bộ ảnh trước 24/09 (như runs/rig_snapshots/20260923_145753_910): meta.json KHÔNG ghi bottom_repeat_share. Trước bản
    # sửa, camera đó được dùng mà không xét gì, dù đáy khung bị bộ giải mã tô (AI gọi vùng đó gần hết là FREE).
    rng = np.random.default_rng(7)
    frames = {name: _noise_frame(rng) for name in ("p1", "p2", "p3", "p4")}
    _paint_repeating(frames["p3"], slice(304, None), 0, rng)                  # đáy tô từ dòng 304
    snap, calib = _damage_snapshot(tmp_path, probs, frames, {n: ["bottom_repeat_share"] for n in ("p1", "p2", "p3", "p4")})
    result, _, _, extra = bev.bev_from_snapshot(snap, calibration_dir=calib)
    assert sorted(result.views) == ["p1", "p2", "p4"]
    assert "truncated_rows" in result.missing["p3"] and "tính lại trên khung" in result.missing["p3"]
    checks = extra["frame_damage_check"]
    assert checks["p1"]["bottom_repeat_share_from"] == "tính lại trên khung" and checks["p1"]["image_checked"] is True
    assert checks["p3"]["truncated_rows"] >= 170 and checks["p3"]["bottom_repeat_share"] > 0.9
    # không còn ảnh lẫn số trong meta: không kiểm được → bỏ camera (vùng của nó UNKNOWN), không mặc định "khung tốt"
    (snap / "cam_p2.png").unlink()
    result, _, _, _ = bev.bev_from_snapshot(snap, calibration_dir=calib)
    assert sorted(result.views) == ["p1", "p4"]
    assert "không kiểm được" in result.missing["p2"] and "cam_p2.png" in result.missing["p2"]


def test_snapshot_torn_band_is_dropped_even_with_low_bottom_share(tmp_path, probs):
    # dải xé giữa ảnh (mất gói giữa khung, đáy nguyên vẹn): bottom_repeat_share của meta thấp (0,05) nhưng khung vẫn hỏng
    rng = np.random.default_rng(11)
    frames = {name: _noise_frame(rng) for name in ("p1", "p2", "p3", "p4")}
    _paint_repeating(frames["p2"], slice(200, 208), 300, rng)
    snap, calib = _damage_snapshot(tmp_path, probs, frames, {})
    result, _, _, extra = bev.bev_from_snapshot(snap, calibration_dir=calib)
    assert sorted(result.views) == ["p1", "p3", "p4"]
    assert "torn_bands" in result.missing["p2"] and "khung nghi hỏng" in result.missing["p2"]
    assert extra["frame_damage_check"]["p2"]["bottom_repeat_share_from"] == "meta.json"
    assert extra["frame_damage_check"]["p1"]["torn_bands"] == 0 and extra["frame_damage_check"]["p1"]["truncated_rows"] == 0


def test_snapshot_cli_refuses_without_calibration(tmp_path, probs, capsys):
    snap = tmp_path / "20260924_100000_000"
    _snapshot(snap, probs, _meta_cameras())
    out = tmp_path / "out"
    assert bev.main(["snapshot", str(snap), "--calibration-dir", str(tmp_path / "trong"), "--out", str(out)]) == 2
    err = capsys.readouterr().err
    assert "cam_p1.json" in err and "nội tham giả định" in err
    assert not out.exists()
    missing_meta = tmp_path / "do_dang"
    missing_meta.mkdir()
    assert bev.main(["snapshot", str(missing_meta), "--out", str(out)]) == 2
    assert "meta.json" in capsys.readouterr().err


def test_synthetic_cli_writes_outputs(tmp_path, full, capsys):
    # cảnh của lệnh synthetic = SCENE ở cỡ hiển thị 480×360, lưới và tầm mặc định: số ô so được với `full` (đủ 4 camera)
    for drop in ("p2", "2"):                                                 # tên hoặc số cổng như --ports 1 2 3 4
        out = tmp_path / f"s_{drop}"
        assert bev.main(["synthetic", "--out", str(out), "--drop", drop]) == 0
        stats = json.loads((out / "stats.json").read_text(encoding="utf-8"))
        assert stats["usable_for_planning"] is False and stats["cameras"]["p2"]["used"] is False
        assert "2" not in stats["cameras"] and all(stats["cameras"][n]["used"] for n in ("p1", "p3", "p4"))
        assert stats["counts"]["occluded"] > 0 and stats["counts"]["uncertain"] > 0
        assert 0 < stats["counts"]["free"] < full.counts()["free"]          # thật sự thiếu camera sau
    capsys.readouterr()
    bad = tmp_path / "bad"
    assert bev.main(["synthetic", "--out", str(bad), "--drop", "x9"]) == 2  # tên lạ: từ chối, không "bỏ" giả
    assert "LỖI" in capsys.readouterr().err and not bad.exists()


def test_bad_extrinsics_vehicle_block_is_a_clean_error(tmp_path, capsys):
    raw = json.loads((PROJECT_ROOT / "configs/rig/camera_rig_extrinsics_v0.json").read_text(encoding="utf-8"))
    broken = {"thieu_rear": {k: v for k, v in raw["vehicle_assumed"].items() if k != "rear_overhang_m"},
              "danh_sach": [0.4, 0.2], "chu": {**raw["vehicle_assumed"], "length_m": "dai"},
              "am": {**raw["vehicle_assumed"], "width_m": -0.2}}
    for name, vehicle in broken.items():
        path = tmp_path / f"rig_{name}.json"
        path.write_text(json.dumps({**raw, "vehicle_assumed": vehicle}), encoding="utf-8")
        with pytest.raises(RigConfigError, match="vehicle_assumed"):
            load_rig_extrinsics(path)
        out = tmp_path / f"out_{name}"
        assert bev.main(["synthetic", "--extrinsics", str(path), "--out", str(out)]) == 2
        assert "LỖI" in capsys.readouterr().err and not out.exists()
    top = tmp_path / "rig_list.json"
    top.write_text(json.dumps([raw]), encoding="utf-8")
    with pytest.raises(RigConfigError, match="không phải tệp"):
        load_rig_extrinsics(top)


def test_woodscape_bad_id_or_archive_is_a_clean_error(tmp_path, capsys):
    import zipfile
    prob = tmp_path / "p.png"
    _write_png(prob, np.zeros((60, 80), np.uint8))
    archive = tmp_path / "calibration.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("calibration/x.json", "{}")
        z.writestr("calibration/00001_FV.json", json.dumps({"name": "FV", "intrinsic": {"model": "radial_poly"}}))
    not_zip = tmp_path / "khong_phai_zip.zip"
    not_zip.write_bytes(b"day khong phai zip")
    cases = [("anh_sa_ban.png", archive, "anh_sa_ban"),                     # mã ảnh không có trong kho
             ("00001_FV.png", archive, "00001_FV"),                           # tệp hiệu chuẩn thiếu trường
             ("00000_FV.png", tmp_path / "khong_co.zip", "khong_co.zip"),     # kho không tồn tại
             ("00000_FV.png", not_zip, "khong_phai_zip.zip")]                 # không phải zip
    for i, (image, source, expected) in enumerate(cases):
        out = tmp_path / f"out_{i}"
        assert bev.main(["woodscape", "--image", image, "--prob", str(prob), "--no-roi",
                         "--calibration-archive", str(source), "--out", str(out)]) == 2
        err = capsys.readouterr().err
        assert "LỖI" in err and expected in err and "Traceback" not in err and not out.exists()


def test_documented_commands_paste_into_powershell():
    # dấu nối dòng `^` chỉ chạy trong cmd.exe; PowerShell báo lỗi "Missing expression after unary operator '--'"
    texts = {"docs/BEV.md": (PROJECT_ROOT / "docs/BEV.md").read_text(encoding="utf-8"), "bev.__doc__": bev.__doc__}
    for name, text in texts.items():
        assert not [line for line in text.splitlines() if line.rstrip().endswith(" ^")], name


# ---- WoodScape (hiệu chuẩn thật của Valeo; bỏ qua nếu thiếu dữ liệu) ---------------------------------------------------
WOODSCAPE_ARCHIVE = PROJECT_ROOT / "datasets/woodscape_metadata/calibration.zip"
WOODSCAPE_IMAGE = PROJECT_ROOT / "datasets/training/woodscape/rgb_images/00000_FV.png"


@pytest.mark.skipif(not (WOODSCAPE_ARCHIVE.exists() and WOODSCAPE_IMAGE.exists()), reason="thiếu dữ liệu WoodScape")
def test_woodscape_demo_uses_the_image_calibration(tmp_path):
    from autopark.perception.calibration import load_woodscape_calibration
    calibration = load_woodscape_calibration(WOODSCAPE_ARCHIVE, "00000_FV")
    w, h = calibration.intrinsics.width, calibration.intrinsics.height
    prob = np.zeros((h // 2, w // 2), np.uint8)                             # "mọi pixel trống", nửa cỡ gốc
    prob_path = tmp_path / "prob.png"
    _write_png(prob_path, prob)
    out = tmp_path / "ws"
    assert bev.main(["woodscape", "--image", str(WOODSCAPE_IMAGE), "--prob", str(prob_path), "--out", str(out)]) == 0
    stats = json.loads((out / "stats.json").read_text(encoding="utf-8"))
    assert stats["usable_for_planning"] is False and stats["cameras"]["00000_FV"]["used"]
    assert stats["cameras"]["00000_FV"]["roi"].endswith("roi_FV.png")
    grid = GridSpec(*bev.WOODSCAPE_GRID)

    def free_cells(folder):
        states = np.array(json.loads((folder / "costmap.json").read_text(encoding="utf-8"))["costmap"]["cells"], np.int8)
        assert (states == OCCUPIED).sum() == 0                              # không pixel nào BLOCKED
        return states == FREE

    free = free_cells(out)
    gx, gy = grid.centers()
    cam = np.asarray(calibration.extrinsics.translation)
    assert free.sum() > 1000
    assert (np.hypot(gx[free] - cam[0], gy[free] - cam[1]) <= bev.WOODSCAPE_MAX_RANGE + grid.resolution).all()
    # tính tay: góc giữa trục quang và tia tới tâm ô FREE ≤ theta_max (100°) — mắt cá ≈ 190° thấy cả hai bên hông
    rel = np.column_stack([gx[free], gy[free], np.zeros(free.sum())]) - cam
    in_cam = rel @ calibration.extrinsics.rotation
    theta = np.degrees(np.arctan2(np.hypot(in_cam[:, 0], in_cam[:, 1]), in_cam[:, 2]))
    assert theta.max() <= 101.0
    # ROI: tâm ô FREE rơi vào vùng dùng được của ROI (nắp capô, viền ống kính bị loại)
    roi = cv2.imdecode(np.fromfile(str(PROJECT_ROOT / "configs/roi/woodscape_v1/roi_FV.png"), np.uint8), 0)
    u, v, ok = calibration.ground_to_pixel(np.column_stack([gx[free], gy[free]]))
    assert ok.all() and (roi[np.rint(v).astype(int), np.rint(u).astype(int)] > 0).mean() > 0.99
    out_no_roi = tmp_path / "ws_no_roi"
    assert bev.main(["woodscape", "--image", str(WOODSCAPE_IMAGE), "--prob", str(prob_path), "--no-roi",
                     "--out", str(out_no_roi)]) == 0
    assert free_cells(out_no_roi).sum() > free.sum()                        # bỏ ROI thì pixel thân xe cũng thành "trống"
    reasons = json.loads((out_no_roi / "stats.json").read_text(encoding="utf-8"))["unusable_reasons"]
    assert any("chưa có ROI" in r for r in reasons)
