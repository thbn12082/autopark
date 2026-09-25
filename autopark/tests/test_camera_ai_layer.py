"""AI camera → vật cản (autopark/fusion/camera_ai.py), không Qt, không thiết bị (25/09/2026).

Rig tổng hợp của `bev.synthetic_rig` (camera ảo, tư thế của tệp rig v0) nhìn một cảnh tổng hợp; P(BLOCKED) của từng camera
được dựng bằng `bev.synthetic_prob_map` (tia qua từng pixel → hộp hay sàn), đúng cỡ hiển thị 640×480 của bàn thử. "Rig
thật" trong các bài chặn là tệp nội tham / ngoại tham / ROI viết tay vào thư mục tạm, KHÔNG mang dấu tổng hợp (như camera
đã hiệu chuẩn thật) — chỉ để kiểm nhánh "dùng được", không phải số đo.
"""
import dataclasses
from functools import lru_cache
import json
import math
from pathlib import Path
import random
import re

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("shapely")

from shapely.geometry import Polygon, box  # noqa: E402

from autopark.domain.types import Bounds, Pose  # noqa: E402
from autopark.fusion import camera_ai  # noqa: E402
from autopark.fusion.camera_ai import (GATE_PREFIX, SYNTHETIC_NOTE, CameraObstacleMapper,  # noqa: E402
                                       vehicle_states_to_map)
from autopark.fusion.fuse import fuse  # noqa: E402
from autopark.fusion.layers import resample  # noqa: E402
from autopark.fusion.obstacles import costmap_to_obstacles  # noqa: E402
from autopark.geometry.footprint import body_polygon, obstacle_polygon  # noqa: E402
from autopark.perception import bev  # noqa: E402
from autopark.perception.bev import SyntheticBox, SyntheticPatch, SyntheticScene, synthetic_prob_map  # noqa: E402
from autopark.perception.costmap import FREE, OCCUPIED, UNKNOWN, GridSpec, to_costmap  # noqa: E402
from autopark.domain.sensors import CameraFrame, SourceStamp  # noqa: E402
from autopark.rig.core import AIResult  # noqa: E402
from autopark.storage.scenario_store import load_vehicle_config  # noqa: E402
from autopark.video.multicam import FrameSet  # noqa: E402
from autopark.video.sources import Frame  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CFG = load_vehicle_config(PROJECT_ROOT / "configs" / "vehicle_default.json")
BOUNDS = Bounds(0.0, 0.0, 3.0, 2.0)
MAP = GridSpec(0.0, 3.0, 0.0, 2.0, 0.05)
START = Pose(0.5, 1.0, 0.0)                       # chỗ xuất phát của sa bàn bàn thử (lidar_app.bench_scenario)
SIZE = (640, 480)
BOX = SyntheticBox(0.9, 1.1, -0.1, 0.1, 0.15)     # hộp 20 × 20 cm trước xe (hệ xe), chỉ camera trước thấy
EMPTY = SyntheticScene()
SCENE = SyntheticScene(boxes=(BOX,))
TOL = 0.10                                        # vật cản phải nằm trong hộp nới chừng này (hai ô 5 cm)


@lru_cache(maxsize=None)
def synthetic_rig(ports=(1, 2, 3, 4)):
    return camera_ai.synthetic_camera_rig(ports, SIZE)


@lru_cache(maxsize=None)
def _prob(calibration, scene):
    return synthetic_prob_map(calibration, scene, out_size=SIZE)


def scene_probs(rig, scene, ports=None):
    return {int(name[1:]): _prob(cam.calibration, scene) for name, cam in rig.cameras.items()
            if ports is None or int(name[1:]) in ports}


def ai_result(probs: dict, t: float, batch_id: int, stamps: dict | None = None, frame_size=SIZE) -> AIResult:
    """Một lô AI như AIWorker công bố: khung (chỉ stamp và cỡ khung là quan trọng ở đây, ảnh không được đọc) + xác suất
    theo cổng."""
    stamps = stamps or {}
    frames = {p: Frame(CameraFrame(SourceStamp(f"cam_p{p}", stamps.get(p, t), True, f"cam_p{p}"), "gia", *frame_size),
                       np.zeros((1, 1, 3), np.uint8)) for p in probs}
    fs = FrameSet(frames=frames, seqs={p: batch_id for p in frames}, anchor_t=t, skew_s=0.0, missing=[], t_built=t)
    return AIResult(fs, dict(probs), "gia", "gia.pt", t + 0.03, None, None, batch_id)


def ai_obstacles(mapper, now):
    fused = fuse([mapper.layer], MAP, now)
    return fused, costmap_to_obstacles(fused.costmap, prefix="camera_ai", bounds=BOUNDS)


def footprint_in_map(b: SyntheticBox, pose: Pose = START) -> Polygon:
    corners = [(b.x_min, b.y_min), (b.x_max, b.y_min), (b.x_max, b.y_max), (b.x_min, b.y_max)]
    return Polygon([pose.to_world(x, y) for x, y in corners])


def feed(mapper, rig, scene, batch_ids, t0=10.0, pose=START, ports=None):
    probs = scene_probs(rig, scene, ports)
    upd = None
    for k, b in enumerate(batch_ids):
        t = t0 + 0.05 * k
        upd = mapper.update(ai_result(probs, t, b), pose, now=t + 0.05)
    return upd


def mapper_for(rig, source_kind="replay", **kw):
    return CameraObstacleMapper(rig, MAP, source_kind=source_kind, vehicle_cfg=CFG, **kw)


# ---- vật cản ở đúng chỗ ---------------------------------------------------------------------------------------------
def test_box_in_front_becomes_an_obstacle_at_its_footprint_after_two_batches():
    rig = synthetic_rig()
    mapper = mapper_for(rig)
    first = feed(mapper, rig, SCENE, [0])
    assert first.processed and first.usable and first.occupied_batch > 0
    assert first.occupied_filtered == 0                                    # một lô chưa đủ (2 trong 3)
    assert ai_obstacles(mapper, 10.05)[1] == []
    second = feed(mapper, rig, SCENE, [1], t0=10.05)
    assert second.occupied_filtered > 0 and second.window_fill == 2
    fused, obstacles = ai_obstacles(mapper, 10.1)
    assert fused.valid and obstacles
    zone = footprint_in_map(BOX).buffer(TOL)
    assert all(obstacle_polygon(o).within(zone) for o in obstacles)     # không vật cản nào ngoài hộp ± 10 cm
    near_face = START.to_world(0.925, 0.0)                                 # mặt hộp hướng về camera trước
    assert any(obstacle_polygon(o).buffer(1e-6).contains(box(*near_face, *near_face)) for o in obstacles)
    assert SYNTHETIC_NOTE in second.notes                                  # rig tổng hợp luôn mang nhãn TỔNG HỢP
    assert second.cameras_used == ["p1", "p2", "p3", "p4"] and second.stamp_t == pytest.approx(10.05)


def test_box_is_placed_with_the_vehicle_pose_when_the_cameras_ride_on_the_car():
    rig = synthetic_rig((1,))
    mapper = mapper_for(rig)
    pose = Pose(2.3, 0.2, math.pi / 2)                                     # xe quay về +y của sa bàn
    feed(mapper, rig, SCENE, [0, 1], pose=pose)
    _, obstacles = ai_obstacles(mapper, 10.1)
    zone = footprint_in_map(BOX, pose).buffer(TOL)                         # x 2,2..2,4, y 1,1..1,3 trên sa bàn
    assert obstacles and all(obstacle_polygon(o).within(zone) for o in obstacles)
    assert not any(obstacle_polygon(o).intersects(footprint_in_map(BOX).buffer(TOL)) for o in obstacles)


def test_ai_threshold_maps_the_safe_015_to_t_blocked_and_t_free_does_not_change_occupied():
    rig = synthetic_rig((1,))
    band = SyntheticPatch(0.9, 1.2, -0.15, 0.15, 0.30)                      # "mô hình" nói 0,30 ở vệt sàn này
    patch = SyntheticScene(patches=(band,))
    safe = mapper_for(rig, window=1, min_hits=1)                            # mặc định: t_blocked = 0,15
    argmax = mapper_for(rig, window=1, min_hits=1, t_free=0.15, t_blocked=0.50)      # mặc định của lệnh bev
    other_free = mapper_for(rig, window=1, min_hits=1, t_free=0.10)
    for m in (safe, argmax, other_free):
        feed(m, rig, patch, [0])
    assert safe.t_blocked == camera_ai.AI_T_BLOCKED == 0.15
    occupied = safe.filtered_states() == OCCUPIED
    # 0,30 ≥ 0,15: vật cản. Chỉ hàng ô gần camera là OCCUPIED (phần sau bị che, như mọi vật trong BEV): 6 ô = 30 cm
    assert occupied.sum() >= 5
    zone = footprint_in_map(SyntheticBox(band.x_min, band.x_max, band.y_min, band.y_max, 0.0)).buffer(0.051)
    assert all(p.within(zone) for p in occupied_polygons(safe.filtered_states(), MAP))
    assert not (argmax.filtered_states() == OCCUPIED).any()                 # 0,30 < 0,50: không phải vật cản
    assert np.array_equal(other_free.filtered_states() == OCCUPIED, occupied)   # t_free không đổi tập OCCUPIED


def test_car_body_and_margin_never_become_obstacles():
    rig = synthetic_rig((1,))
    close = SyntheticBox(0.36, 0.56, -0.1, 0.1, 0.15)                       # sát mũi xe (camera trước ở x = 0,33)
    scene = SyntheticScene(boxes=(close,))
    wide = mapper_for(rig, window=1, min_hits=1, mask_margin=0.15)
    assert wide.ego.x_max == pytest.approx(CFG.wheelbase + CFG.front_overhang + 0.15)
    narrow = mapper_for(rig, window=1, min_hits=1, mask_margin=0.0)
    assert narrow.ego.x_max == pytest.approx(rig.ego.x_max)                 # hộp thân xe của tệp rig vẫn giữ
    for m in (wide, narrow):
        feed(m, rig, scene, [0])
    gx, gy = MAP.centers()
    xv, yv = gx - START.x, gy - START.y                                     # hệ xe (xe hướng +x)
    assert (narrow.filtered_states() == OCCUPIED).any()
    for m in (wide, narrow):
        assert not ((m.filtered_states() == OCCUPIED) & m.ego.contains(xv, yv)).any()
    # lề rộng che mặt hộp hướng về camera; phần sau của hộp bị chính mặt đó che nên cũng không thành vật cản: vật nằm
    # trong lề quanh xe là VÔ HÌNH với nguồn AI (giới hạn ghi ở docs/AI_DIEU_KHIEN_XE.md)
    assert (wide.filtered_states() == OCCUPIED).sum() < (narrow.filtered_states() == OCCUPIED).sum()


# mặt nạ thân xe trong HỆ BẢN ĐỒ: lấy mẫu bảo thủ làm ô phình tối đa một ô, nên mặt nạ tâm ô hệ xe của BEV là không đủ
def all_blocked_probs(rig):
    return {int(n[1:]): np.full((SIZE[1], SIZE[0]), 0.9, np.float32) for n in rig.cameras}


def obstacles_after(poses, probs=None, rig=None, margin=camera_ai.AI_MASK_MARGIN_M):
    rig = rig or synthetic_rig()
    probs = probs or all_blocked_probs(rig)
    mapper = mapper_for(rig, mask_margin=margin)
    for k, pose in enumerate(poses):
        t = 10.0 + 0.05 * k
        assert mapper.update(ai_result(probs, t, k), pose, t + 0.05).usable
    return ai_obstacles(mapper, 10.0 + 0.05 * len(poses))[1]


def random_poses(seed, n):
    rnd = random.Random(seed)
    return [Pose(rnd.uniform(1.0, 2.0), rnd.uniform(0.8, 1.2), rnd.uniform(-math.pi, math.pi)) for _ in range(n)]


@pytest.mark.parametrize("pose", random_poses(7, 12) + [Pose(1.5125, 1.0125, 0.0), Pose(1.23, 0.87, 0.4)])
def test_ai_obstacles_never_overlap_the_car_body_and_margin_at_any_pose(pose):
    # P(BLOCKED) = 0,9 ở mọi pixel của cả bốn camera: vật cản sát thân xe ở mọi phía, tư thế không thẳng lưới
    obstacles = obstacles_after([pose, pose])
    assert obstacles, "phải còn vật cản AI ngoài lề (bài kiểm không rỗng)"
    body = body_polygon(CFG, pose)
    grown = body_polygon(CFG, pose, camera_ai.AI_MASK_MARGIN_M)
    assert not [o.id for o in obstacles if obstacle_polygon(o).intersects(body)]
    assert max(obstacle_polygon(o).intersection(grown).area for o in obstacles) < 1e-9


@pytest.mark.parametrize("pose", [Pose(1.06, 1.07, 0.0), Pose(1.56, 0.93, math.pi)])
def test_with_zero_margin_and_no_rig_box_ai_obstacles_do_not_even_touch_the_body(pose):
    # lề 0 (ô "cm quanh xe bỏ" cho phép), tệp rig không có hộp `vehicle_assumed`, thân xe thẳng lưới: ô chỉ CHẠM biên thân
    # xe vẫn phải bị che, vì `check_pose` tính chạm biên là va chạm
    rig = dataclasses.replace(synthetic_rig(), ego=None)
    obstacles = obstacles_after([pose, pose], rig=rig, margin=0.0)
    assert obstacles and not any(obstacle_polygon(o).intersects(body_polygon(CFG, pose)) for o in obstacles)


def test_body_mask_follows_the_car_while_it_moves_between_batches():
    rnd = random.Random(3)
    for _ in range(10):                                  # camera trên xe: ba lô ở ba tư thế (xoay + tịnh tiến ngang)
        x, y, yaw = rnd.uniform(1.0, 2.0), rnd.uniform(0.8, 1.2), rnd.uniform(-math.pi, math.pi)
        poses = [Pose(x + 0.04 * k * math.sin(yaw), y - 0.04 * k * math.cos(yaw), yaw + 0.25 * k) for k in range(3)]
        obstacles = obstacles_after(poses)
        assert obstacles and not any(obstacle_polygon(o).intersects(body_polygon(CFG, poses[-1])) for o in obstacles)


# tường tổng hợp dọc hai hông xe (hệ xe), mặt trong cách hông xe (y = ±0,07) đúng 5 cm
WALLS = (SyntheticBox(-0.05, 0.25, -0.40, -0.12, 0.15), SyntheticBox(-0.05, 0.25, 0.12, 0.40, 0.15))


@pytest.mark.parametrize("start, seen", [
    (Pose(1.5125, 1.0125, 0.0), True), (Pose(1.23, 0.87, 0.4), True), (Pose(1.31, 1.04, -0.9), True),
    # giới hạn đã biết (docs/AI_DIEU_KHIEN_XE.md mục 9): xe thẳng lưới, mặt tường đúng ở biên lề 5 cm nằm trong ô 5 cm
    # chạm vùng lề nên bị che; phần sau của tường bị chính mặt đó che → AI không thấy tường. Chỉ LiDAR bảo vệ ở đó.
    (Pose(0.5, 1.0, 0.0), False),
])
def test_walls_five_cm_beside_the_car_do_not_put_the_start_in_collision(start, seen):
    from autopark.application.session import Session
    from autopark.domain.types import ParkingGoal, Scenario
    from autopark.fusion.bridge import ObstacleBridge

    session = Session(Scenario("tuong_5cm", BOUNDS, start, ParkingGoal(Pose(2.5, 1.0, 0.0)), obstacles=[], slot=None),
                      CFG)
    assert session.start_check().ok
    rig = synthetic_rig()
    mapper = mapper_for(rig)
    bridge = ObstacleBridge(session, prefix=camera_ai.SOURCE_ID, path_margin=0.10)
    probs = scene_probs(rig, SyntheticScene(boxes=WALLS))
    for k in range(2):
        t = 10.0 + 0.05 * k
        assert mapper.update(ai_result(probs, t, k), start, t + 0.05).usable
        bridge.sync_incremental(fuse([mapper.layer], MAP, t + 0.05, source_id=camera_ai.SOURCE_ID))
    assert bool(bridge.owned()) is seen, "AI phải thấy tường" if seen else "đổi giới hạn đã biết: sửa tài liệu"
    check = session.start_check()
    assert check.ok, check.reasons                       # hộp AI không làm chỗ xuất phát "va chạm"


# ---- lọc thời gian và dữ liệu cũ ------------------------------------------------------------------------------------
def test_temporal_filter_needs_two_of_the_last_three_batches():
    rig = synthetic_rig((1,))
    mapper = mapper_for(rig)
    box_probs, empty_probs = scene_probs(rig, SCENE), scene_probs(rig, EMPTY)
    seq = [(box_probs, False), (empty_probs, False), (box_probs, True), (empty_probs, False), (empty_probs, False)]
    for k, (probs, expect) in enumerate(seq):
        t = 10.0 + 0.05 * k
        upd = mapper.update(ai_result(probs, t, k), START, t + 0.05)
        assert upd.processed and upd.usable
        assert (upd.occupied_filtered > 0) is expect, k
    again = mapper.update(ai_result(box_probs, 10.25, 4), START, 10.3)     # cùng số lô: không tính lần hai
    assert not again.processed and mapper.batches == 5
    quick = mapper_for(rig, window=1, min_hits=1)
    assert feed(quick, rig, SCENE, [0]).occupied_filtered > 0              # 1/1: có ngay
    with pytest.raises(ValueError):
        mapper_for(rig, window=3, min_hits=4)


def test_stamp_is_the_oldest_frame_and_old_data_is_stale_and_resets_the_filter():
    rig = synthetic_rig((1, 3))
    mapper = mapper_for(rig)
    probs = scene_probs(rig, SCENE)
    upd = mapper.update(ai_result(probs, 10.04, 0, stamps={1: 10.04, 3: 10.00}), START, 10.06)
    assert upd.stamp_t == pytest.approx(10.00) and mapper.layer.costmap.stamp.t == pytest.approx(10.00)
    assert mapper.fresh(10.45) and not mapper.fresh(10.51)                  # tuổi tính từ khung CŨ nhất, 0,5 s
    assert mapper.age(10.51) == pytest.approx(0.51)
    assert not fuse([mapper.layer], MAP, 10.51).valid                       # lớp bắt buộc của ngăn camera: không hợp lệ
    late = mapper.update(ai_result(probs, 20.0, 1), START, 20.05)            # lô sau 10 s: bằng chứng cũ không cộng
    assert late.usable and late.occupied_filtered == 0 and late.window_fill == 1
    assert mapper.window_resets == 1 and any("cửa sổ lọc xóa" in n for n in late.notes)
    assert mapper.update(ai_result(probs, 20.05, 2), START, 20.1).occupied_filtered > 0
    skipped = mapper.update(ai_result(probs, 20.1, 6), START, 20.15)         # lô 3..5 ra giữa hai lần gọi
    assert skipped.processed and mapper.batches_skipped == 3


def test_batch_notes_missing_and_foreign_cameras_and_no_data_is_not_an_obstacle():
    rig = synthetic_rig((1, 2))
    mapper = mapper_for(rig)
    probs = {1: scene_probs(rig, SCENE)[1], 7: np.zeros((480, 640), np.float32)}
    upd = mapper.update(ai_result(probs, 10.0, 0), START, 10.05)
    assert upd.usable and upd.cameras_used == ["p1"]
    assert any("p2" in n and "UNKNOWN" in n for n in upd.notes) and any("[7]" in n for n in upd.notes)
    none = mapper.update(ai_result({7: probs[7]}, 10.05, 1), START, 10.1)
    assert not none.usable and none.reasons == ["lô AI không có camera nào của rig"]
    assert not (mapper.filtered_states() == OCCUPIED).any() and not mapper.fresh(10.1)
    assert mapper.update(None, START, 10.2).processed is False


# ---- chặn --------------------------------------------------------------------------------------------------------------
def write_real_rig(folder: Path, ports=(1,), *, measured=True, roi=True, all_pass=True, acceptance=True,
                   synthetic_extrinsics=False, intrinsics_ports=None) -> dict:
    """Tệp như camera đã hiệu chuẩn thật (không dấu TỔNG HỢP): tư thế của tệp rig v0, nội tham danh định 640×480."""
    from autopark.perception.fisheye_calib import FORMAT, woodscape_intrinsics
    raw = json.loads((PROJECT_ROOT / "configs/rig/camera_rig_extrinsics_v0.json").read_text(encoding="utf-8"))
    raw["status"] = "đo (TEST)"
    raw["cameras"] = {k: {**c, "measured": measured, **({"synthetic": True} if synthetic_extrinsics else {})}
                      for k, c in raw["cameras"].items() if int(k) in ports}
    folder.mkdir(parents=True, exist_ok=True)
    extrinsics = folder / "camera_rig_extrinsics_v1.json"
    extrinsics.write_text(json.dumps(raw), encoding="utf-8")
    calib, roi_dir = folder / "calibration", folder / "roi"
    calib.mkdir(exist_ok=True)
    roi_dir.mkdir(exist_ok=True)
    f = bev.nominal_intrinsics(*SIZE).k[0]
    K = [[f, 0.0, SIZE[0] / 2 - 0.5], [0.0, f, SIZE[1] / 2 - 0.5], [0.0, 0.0, 1.0]]
    for port in (ports if intrinsics_ports is None else intrinsics_ports):
        record = {"format": FORMAT, "camera": {"hub_port": port, "source_id": f"cam_p{port}", "device": "USB (test)"},
                  "image_size": list(SIZE), "K": K, "D": [0.0] * 4,
                  "woodscape_intrinsic": woodscape_intrinsics(np.array(K), np.zeros(4), SIZE)}
        if acceptance:
            record["acceptance"] = {"all_pass": all_pass, "status": "đề xuất"}
        (calib / f"cam_p{port}.json").write_text(json.dumps(record), encoding="utf-8")
        if roi:
            ok, buf = cv2.imencode(".png", np.full((SIZE[1], SIZE[0]), 255, np.uint8))
            (roi_dir / f"roi_p{port}.png").write_bytes(buf.tobytes())
    return {"extrinsics": extrinsics, "calibration_dir": calib, "roi_dir": roi_dir}


def real_rig(tmp_path, name, ports=(1,), **kw):
    paths = write_real_rig(tmp_path / name, ports, **kw)
    return camera_ai.load_camera_rig(ports, SIZE, **paths)


def test_a_fully_calibrated_rig_creates_obstacles_even_from_live_cameras(tmp_path):
    rig = real_rig(tmp_path, "tot")
    assert not rig.synthetic and not rig.problems and rig.cameras["p1"].roi is not None
    mapper = mapper_for(rig, source_kind="live")
    upd = feed(mapper, rig, SCENE, [0, 1])
    assert upd.usable and upd.reasons == [] and upd.notes == []
    _, obstacles = ai_obstacles(mapper, 10.1)
    zone = footprint_in_map(BOX).buffer(TOL)
    assert obstacles and all(obstacle_polygon(o).within(zone) for o in obstacles)


@pytest.mark.parametrize("change, expected", [
    ({"roi": False}, "p1: chưa có ROI"),
    ({"measured": False}, "p1: ngoại tham GIẢ ĐỊNH — CHƯA ĐO"),
    ({"all_pass": False}, "p1: nội tham chưa đạt tiêu chí đề xuất (acceptance.all_pass = false)"),
    ({"all_pass": "false"}, "p1: nội tham chưa đạt tiêu chí đề xuất"),       # chuỗi, không phải false của JSON
    ({"all_pass": "true"}, "p1: nội tham chưa đạt tiêu chí đề xuất"),        # chỉ true của JSON mới đạt
    ({"all_pass": 1}, "p1: nội tham chưa đạt tiêu chí đề xuất"),
    ({"acceptance": False}, "p1: tệp nội tham không có kết quả tiêu chí"),
    ({"synthetic_extrinsics": True}, "p1: ngoại tham là dữ liệu TỔNG HỢP"),
])
def test_unusable_bev_adds_no_obstacle_and_says_why(tmp_path, change, expected):
    rig = real_rig(tmp_path, "sai", **change)
    mapper = mapper_for(rig, source_kind="live")
    for k in range(4):
        upd = feed(mapper, rig, SCENE, [k], t0=10.0 + 0.05 * k)
        assert upd.processed and not upd.usable
    assert any(r.startswith(expected) for r in upd.reasons), upd.reasons
    assert upd.gate_text().startswith(GATE_PREFIX)
    assert mapper.batches_refused == 4 and mapper.batches_usable == 0
    assert not (mapper.filtered_states() == OCCUPIED).any()
    fused, obstacles = ai_obstacles(mapper, 10.2)
    assert not fused.valid and not mapper.fresh(10.2)


def edit_intrinsics(paths, port=1, **changes):
    """Sửa tay tệp nội tham (như người dùng sửa JSON): đặt các khóa `changes` ở mức gốc của bản ghi."""
    f = Path(paths["calibration_dir"]) / f"cam_p{port}.json"
    record = json.loads(f.read_text(encoding="utf-8"))
    record.update(changes)
    f.write_text(json.dumps(record), encoding="utf-8")


def test_acceptance_block_that_is_not_an_object_is_refused_not_raised(tmp_path):
    paths = write_real_rig(tmp_path / "khoi_hong", (1,))
    edit_intrinsics(paths, acceptance="failed")
    rig = camera_ai.load_camera_rig([1], SIZE, **paths)                     # không ném
    assert rig.cameras["p1"].acceptance_all_pass is False
    mapper = mapper_for(rig, source_kind="live")
    upd = feed(mapper, rig, SCENE, [0, 1])
    assert not upd.usable and any("chưa đạt tiêu chí" in r for r in upd.reasons)
    assert not (mapper.filtered_states() == OCCUPIED).any()


def test_rig_loaders_never_raise_broken_files_become_gate_reasons(tmp_path):
    typo = camera_ai.synthetic_camera_rig([1], SIZE, extrinsics=tmp_path / "khong_co.json")   # gõ sai tên tệp
    assert typo.synthetic and typo.cameras == {} and "khong_co.json" in typo.problems[0]
    paths = write_real_rig(tmp_path / "lo", (1,))
    edit_intrinsics(paths, camera=5)                                        # kiểu lạ: fisheye_calib ném TypeError
    odd = camera_ai.load_camera_rig([1], SIZE, **paths)
    assert odd.cameras == {} and "TypeError" in odd.problems[0]
    for rig, kind in ((typo, "replay"), (odd, "live")):
        mapper = mapper_for(rig, source_kind=kind)
        assert mapper.blocked
        upd = mapper.update(ai_result({1: np.full((480, 640), 0.9, np.float32)}, 10.0, 0), START, 10.05)
        assert not upd.usable and upd.reasons[0] == rig.problems[0]
        assert not (mapper.filtered_states() == OCCUPIED).any()


def test_preflight_reasons_are_known_before_any_ai_batch(tmp_path):
    good = real_rig(tmp_path, "tot")
    assert camera_ai.preflight_reasons(good, "live") == []
    no_roi = real_rig(tmp_path, "khong_roi", roi=False, all_pass="false")
    reasons = camera_ai.preflight_reasons(no_roi, "live")
    assert any(r.startswith("p1: chưa có ROI") for r in reasons) and any("chưa đạt tiêu chí" in r for r in reasons)
    no_acceptance = real_rig(tmp_path, "khong_tieu_chi", acceptance=False)
    assert camera_ai.preflight_reasons(no_acceptance, "live")[0].startswith("p1: tệp nội tham không có kết quả tiêu chí")
    rig = synthetic_rig((1,))
    assert camera_ai.preflight_reasons(rig, "replay") == []                 # rig tổng hợp: lý do từng camera chỉ là ghi chú
    assert "không bao giờ với camera thật" in camera_ai.preflight_reasons(rig, "live")[0]


def problem_heads(problems):
    """Phần đầu mỗi lý do, trước chi tiết trong ngoặc hay sau gạch dài."""
    return [re.split(r" \(| — ", p)[0] for p in problems]


def test_rig_that_cannot_be_loaded_is_refused_with_the_file_problems(tmp_path):
    extrinsics = tmp_path / "khong_co" / "camera_rig_extrinsics_v1.json"
    missing = camera_ai.load_camera_rig([1, 2], SIZE, extrinsics=extrinsics,
                                        calibration_dir=tmp_path / "calibration", roi_dir=tmp_path / "roi")
    # chưa có tệp nào: kể đủ theo đúng trình tự làm (nội tham → ngoại tham → ROI), không phải lỗi hệ điều hành
    assert not missing.cameras
    assert problem_heads(missing.problems) == ["chưa có nội tham của p1, p2", f"chưa có tệp ngoại tham đã đo {extrinsics}",
                                               "chưa có ROI của p1, p2"]
    assert "HIEU_CHUAN_CAMERA" in missing.problems[0] and "NGOAI_THAM_VA_ROI.md mục 1" in missing.problems[1]
    assert "NGOAI_THAM_VA_ROI.md mục 6" in missing.problems[2] and "Errno" not in " ".join(missing.problems)
    broken = tmp_path / "hong.json"
    broken.write_text("{không phải json", encoding="utf-8")                  # tệp có mà hỏng: lỗi đọc của bev
    assert any("không đọc được tệp ngoại tham" in p for p in camera_ai.load_camera_rig([1], SIZE, extrinsics=broken,
                                                                                        calibration_dir=tmp_path).problems)
    no_intrinsics = real_rig(tmp_path, "thieu_noi_tham", ports=(1, 2), intrinsics_ports=(1,))
    assert any("cam_p2.json" in p and "HIEU_CHUAN_CAMERA" in p for p in no_intrinsics.problems)
    assert any(p.startswith("chưa có ROI của p2") for p in no_intrinsics.problems)   # thiếu nội tham kể cả ROI thiếu
    paths = write_real_rig(tmp_path / "thieu_cong", (1,))
    not_in_file = camera_ai.load_camera_rig([1, 3], SIZE, **paths)
    assert any("cổng 3 không có trong tệp ngoại tham" in p for p in not_in_file.problems)
    for rig in (missing, no_intrinsics, not_in_file):
        mapper = mapper_for(rig, source_kind="live")
        assert mapper.blocked
        assert mapper.update(None, START, 10.0).reasons == list(rig.problems)
        upd = mapper.update(ai_result({1: np.full((480, 640), 0.9, np.float32)}, 10.0, 0), START, 10.05)
        assert upd.processed and not upd.usable and upd.reasons == list(rig.problems)
        assert not (mapper.filtered_states() == OCCUPIED).any()


def test_wrong_camera_mode_refuses_the_batch_and_clears_the_filter(tmp_path):
    rig = synthetic_rig((1,))
    mapper = mapper_for(rig)
    feed(mapper, rig, SCENE, [0, 1])
    assert (mapper.filtered_states() == OCCUPIED).any()
    wide = mapper.update(ai_result({1: np.zeros((360, 640), np.float32)}, 10.1, 2), START, 10.15)   # 16:9 ≠ 4:3
    assert not wide.usable and "tỉ lệ khung" in wide.reasons[0]
    assert not (mapper.filtered_states() == OCCUPIED).any() and not mapper.fresh(10.15)
    assert feed(mapper, rig, SCENE, [3], t0=10.2).occupied_filtered == 0     # cửa sổ lọc bắt đầu lại
    # cùng tỉ lệ 4:3 nhưng khung 320×240 (camera trả mode khác mode xin): nội tham 640×480 không dùng được → chặn
    real = real_rig(tmp_path, "mode_khac")
    other = mapper_for(real, source_kind="live", window=1, min_hits=1)
    probs = scene_probs(real, SCENE)
    small = other.update(ai_result(probs, 10.0, 0, frame_size=(320, 240)), START, 10.05)
    assert not small.usable and small.reasons == ["p1: khung 320×240 khác cỡ ảnh đã hiệu chuẩn 640×480 (mode camera "
                                                  "khác: nội tham không dùng được)"]
    assert other.update(ai_result(probs, 10.05, 1), START, 10.1).usable      # đối chứng: khung 640×480 thì dùng được


def test_synthetic_rig_is_refused_with_live_cameras_and_flagged_with_replay():
    rig = synthetic_rig((1,))
    live = mapper_for(rig, source_kind="live")
    upd = feed(live, rig, SCENE, [0, 1, 2])
    assert live.blocked and not upd.usable
    assert any("TỔNG HỢP" in r and "không bao giờ với camera thật" in r for r in upd.reasons)
    assert not (live.filtered_states() == OCCUPIED).any()
    for kind in ("replay", "fake"):
        allowed = mapper_for(rig, source_kind=kind)
        upd = feed(allowed, rig, SCENE, [0, 1])
        assert upd.usable and upd.occupied_filtered > 0 and SYNTHETIC_NOTE in upd.notes
        assert any("ngoại tham GIẢ ĐỊNH" in n for n in upd.notes)           # lý do của BEV vẫn hiện, dạng ghi chú
    with pytest.raises(ValueError):
        mapper_for(rig, source_kind="usb")


# ---- đặt BEV vào lưới bản đồ ----------------------------------------------------------------------------------------
VGRID = GridSpec(-0.5, 0.5, -0.5, 0.5, 0.05)


def one_cell(r=10, c=10):
    states = np.full(VGRID.shape, FREE, np.int8)
    states[r, c] = OCCUPIED
    return states


def cell_polygon_in_map(r, c, pose, grid=VGRID):
    x0, y0, s = grid.x_min + c * grid.resolution, grid.y_min + r * grid.resolution, grid.resolution
    corners = [(x0, y0), (x0 + s, y0), (x0 + s, y0 + s), (x0, y0 + s)]
    return Polygon([pose.to_world(x, y) for x, y in corners])


def occupied_polygons(states, grid):
    rows, cols = np.nonzero(states == OCCUPIED)
    return [box(grid.x_min + c * grid.resolution, grid.y_min + r * grid.resolution,
                grid.x_min + (c + 1) * grid.resolution, grid.y_min + (r + 1) * grid.resolution) for r, c in zip(rows, cols)]


def test_one_occupied_cell_survives_any_rotation_where_nearest_sampling_can_lose_it():
    grid = GridSpec(0.0, 2.0, 0.0, 2.0, 0.05)
    # ô (10, 10) có tâm (0,025; 0,025) hệ xe; xoay 45° nó ở (0; 0,0354) so với xe → đặt xe để tâm đó rơi đúng góc ô bản đồ
    pose = Pose(1.0, 1.0 - 0.025 * math.sqrt(2), math.pi / 4)
    states = one_cell()
    nearest = resample(to_costmap(states, VGRID, SourceStamp("t", 0.0, True, "vehicle")), grid, pose)
    assert not (nearest == OCCUPIED).any()                                 # một điểm gần nhất: ô vật cản biến mất
    ours = vehicle_states_to_map(states, VGRID, grid, pose)
    assert (ours == OCCUPIED).any()
    rng = np.random.default_rng(20260925)
    for _ in range(150):
        r, c = (int(v) for v in rng.integers(2, 18, 2))
        pose = Pose(float(rng.uniform(0.7, 1.3)), float(rng.uniform(0.7, 1.3)), float(rng.uniform(-math.pi, math.pi)))
        out = vehicle_states_to_map(one_cell(r, c), VGRID, grid, pose)
        cell = cell_polygon_in_map(r, c, pose)
        polys = occupied_polygons(out, grid)
        assert polys and any(p.intersection(cell).area > 0 for p in polys)          # không bao giờ mất
        assert all(p.within(cell.buffer(0.05 * math.sqrt(2) + 1e-9)) for p in polys)   # phình tối đa một ô
    free = vehicle_states_to_map(np.full(VGRID.shape, FREE, np.int8), VGRID, grid, Pose(1.0, 1.0, 0.3))
    assert (free[18:22, 18:22] == FREE).all() and (free[0:3, 0:3] == UNKNOWN).all()   # ngoài lưới xe: UNKNOWN
    with pytest.raises(ValueError):
        vehicle_states_to_map(np.zeros((3, 3), np.int8), VGRID, grid, Pose(1.0, 1.0, 0.0))


def test_gate_text_and_attribution_are_in_the_description():
    assert camera_ai.gate_text(["a", "b"]) == GATE_PREFIX + "a; b"
    info = mapper_for(synthetic_rig((1,))).describe()
    assert "WoodScape" in info["attribution"] and "github.com/valeoai/WoodScape" in info["attribution"]
    assert "CHƯA" in info["licence"] and "GIAY_PHEP_DU_LIEU" in info["licence"]
