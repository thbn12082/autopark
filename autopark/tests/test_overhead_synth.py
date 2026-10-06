"""Cảnh TỔNG HỢP của T4 (`autopark.evaluation.overhead_synth`, thêm 02/10/2026): góc marker dựng ra phải nằm đúng chỗ
`cv2.fisheye.projectPoints` chiếu các góc tính tay (không dùng mã của mô-đun đang kiểm), sàn tĩnh được giữ lại, bộ thử
mang nhãn TỔNG HỢP và không bao giờ ghi vào thư mục của dự án. Không mở camera hay cổng nào."""
import csv
import json
import math
from pathlib import Path
import time

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.domain.types import Pose  # noqa: E402
from autopark.evaluation import overhead_synth as synth  # noqa: E402
from autopark.evaluation.overhead_ref import SYNTHETIC_LABEL, OverheadError  # noqa: E402
from autopark.perception.paths import PROJECT  # noqa: E402
from tests.overhead_set import small_set  # noqa: E402


def _detect(image):
    p = cv2.aruco.DetectorParameters()
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_CONTOUR
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), p)
    corners, ids, _ = det.detectMarkers(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image)
    return {} if ids is None else {int(i): c.reshape(4, 2) for c, i in zip(corners, ids.ravel())}


def _project(cam, pts):
    rvec = cv2.Rodrigues(cam.R)[0]
    return cv2.fisheye.projectPoints(np.asarray(pts, np.float64).reshape(1, -1, 3), rvec, cam.t.reshape(3, 1), cam.K,
                                     cam.D.reshape(4, 1))[0].reshape(-1, 2)


def _square(cx, cy, z, side, yaw=0.0):
    """Góc TL, TR, BR, BL của marker in (trục x sang phải, y lên lúc in) trong hệ sa bàn."""
    c, s = math.cos(yaw), math.sin(yaw)
    h = side / 2
    return [(cx + c * dx - s * dy, cy + s * dx + c * dy, z) for dx, dy in ((-h, h), (h, h), (h, -h), (-h, -h))]


def _compare(found: np.ndarray, expected: np.ndarray) -> tuple[float, float, float]:
    """(lệch tâm, lệch góc lớn nhất, độ lõm vào trung bình) px. Góc ArUco (đường viền) nằm lõm vào trong cạnh thật
    ≈ 0,5–0,8 px — điểm ảnh biên của đường viền tính ở tâm điểm ảnh (đo 02/10/2026 trên ảnh tổng hợp); lệch đối xứng nên
    tâm (trung bình 4 góc) không bị ảnh hưởng: tâm mới là phép kiểm chặt của vị trí dựng."""
    centre_err = float(np.linalg.norm(found.mean(axis=0) - expected.mean(axis=0)))
    corner_err = float(np.max(np.linalg.norm(found - expected, axis=1)))
    outward = expected - expected.mean(axis=0)
    inward = float(np.mean(np.sum((expected - found) * outward / np.linalg.norm(outward, axis=1, keepdims=True), 1)))
    return centre_err, corner_err, inward


def test_renderer_places_floor_marker_corners_where_fisheye_projects_them():
    info = small_set()
    image = info["renderer"].floor_image()
    found = _detect(image)
    cam = info["camera"]
    assert len(found) == len(info["floor_markers"])
    for m in info["floor_markers"]:
        centre_err, corner_err, inward = _compare(found[m.marker_id], _project(cam, _square(m.x, m.y, 0.0, m.side)))
        assert centre_err < 0.35 and corner_err < 1.6 and 0.0 < inward < 1.2, m.name


def test_plate_markers_at_height_project_correctly():
    info = small_set()
    renderer, plate, cam = info["renderer"], info["plate"], info["camera"]
    for yaw_deg in (0.0, 75.0, -140.0):
        pose = Pose(0.6, 0.45, math.radians(yaw_deg))              # ≈ 0,75 m từ điểm dưới camera: thị sai ≈ 4 cm
        found = _detect(renderer.frame(pose, plate, noise=0.0))
        for m in plate.markers:
            c, s = math.cos(pose.yaw), math.sin(pose.yaw)
            cx, cy = pose.x + c * m.x - s * m.y, pose.y + s * m.x + c * m.y
            expected = _project(cam, _square(cx, cy, plate.z, m.side, pose.yaw + math.radians(m.yaw_deg)))
            centre_err, corner_err, inward = _compare(found[m.marker_id], expected)
            assert centre_err < 0.35 and corner_err < 1.6 and 0.0 < inward < 1.2, (yaw_deg, m.marker_id)
            wrong = _project(cam, _square(cx, cy, 0.0, m.side, pose.yaw))          # không bù độ cao: lệch xa
            assert np.linalg.norm(found[m.marker_id].mean(axis=0) - wrong.mean(axis=0)) > 3.0


def test_static_floor_is_cached_and_plate_renders_only_its_bbox():
    info = small_set()
    renderer, plate = info["renderer"], info["plate"]
    pose = Pose(0.9, 0.8, 0.4)
    times = []
    for _ in range(3):
        t = time.perf_counter()
        frame = renderer.frame(pose, plate, noise=0.0)
        times.append(time.perf_counter() - t)
    assert min(times) < 0.1                                    # sàn tĩnh đã dựng sẵn: chỉ dựng lại hộp bao của xe
    x0, y0, x1, y1 = renderer.last_bbox
    assert 0 < (x1 - x0) * (y1 - y0) < 0.1 * frame.shape[0] * frame.shape[1]
    floor = renderer.floor_image()
    outside = np.ones(floor.shape, bool)
    outside[y0:y1, x0:x1] = False
    assert np.array_equal(frame[..., 0][outside], floor[outside])
    assert not np.array_equal(frame[..., 0][~outside], floor[~outside])


def test_set_refuses_project_dirs_and_is_labelled_synthetic():
    for folder in (PROJECT / "configs" / "t4_thu", PROJECT / "calibration" / "t4_thu",
                   PROJECT / "docs" / "evidence" / "t4_thu"):
        with pytest.raises(OverheadError, match="không được ghi vào"):
            synth.write_synthetic_set(folder, frames=2, tc1_poses=1, tc1_frames=2)
        assert not folder.exists()
    out = Path(small_set()["out"])
    jsons = sorted(out.rglob("*.json"))
    assert len(jsons) >= 13                                    # nội tham, marker, lần chạy, 10 đoạn TC-1 (+ kết quả)
    for path in jsons:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") in ("autopark.fisheye_intrinsics/1", "autopark.overhead_vehicle_markers/1",
                                  "autopark.overhead_recording/1", "autopark.overhead_floor/1",
                                  "autopark.overhead_tc1/1"):
            assert data["synthetic"] is True, path
    assert (out / "README.txt").read_text(encoding="utf-8").startswith(SYNTHETIC_LABEL)


def test_recording_stamps_follow_the_31_48_ms_pattern_on_a_perf_offset():
    out = Path(small_set()["out"])
    with (out / "chay_01.frames.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    t = [float(r["t_perf"]) for r in rows]
    assert len(rows) == 40 and t[0] == pytest.approx(12345.0)
    gaps = np.round(np.diff(t), 6)
    assert np.allclose(gaps[0::2], 0.031) and np.allclose(gaps[1::2], 0.048)
    assert [int(r["frame"]) for r in rows] == list(range(40))
    assert float(rows[-1]["t_s"]) == pytest.approx(t[-1] - t[0], abs=1e-6)
    assert synth.camera_stamps(4, 10.0) == [10.0, 10.031, 10.079, 10.11]
