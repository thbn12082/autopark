"""BEV chiếm chỗ từ AI nhiều camera (autopark/perception/bev.py).

Rig tổng hợp: bốn camera mắt cá ảo (tư thế của configs/rig/camera_rig_extrinsics_v0.json, nội tham danh định 130° chéo)
quanh một xe 0,40 × 0,20 m nhìn mặt sàn phẳng có hai hộp và một dải "mô hình không chắc". Bản đồ xác suất của từng camera
được dựng bằng cách chiếu SỰ THẬT vào ảnh (tia qua từng pixel → hộp hay mặt sàn), ở cỡ hiển thị 480×360 như bàn thử ghi.
Phép kiểm tầm nhìn dưới đây (`visible_from`) là tính độc lập: đoạn thẳng camera → điểm sàn có cắt hộp không, không dùng
`project_labels`. Không cần dataset, torch hay thiết bị (trừ bài WoodScape: bỏ qua nếu thiếu dữ liệu).
"""
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
