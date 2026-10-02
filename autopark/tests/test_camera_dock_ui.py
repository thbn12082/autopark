"""Ngăn AI camera trong cửa sổ đỗ xe (autopark/ui/camera_dock.py), offscreen, không thiết bị (25/09/2026).

Nguồn: bản ghi phiên của nguồn giả (tests/test_rig_replay.record_fake_session) phát lại qua `rig.replay`, hoặc camera
giả (`tests.rig_fakes.fake_manager`) chạy liên tục. Bộ phân đoạn giả `SceneSegmenter` không đọc ảnh: nó trả P(BLOCKED)
của một cảnh tổng hợp nhìn từ camera trước của rig tổng hợp (`bev.synthetic_prob_map`), và cảnh đổi được lúc đang chạy
để "đặt" một hộp lên đường. Rig camera là rig TỔNG HỢP — chỉ được phép với nguồn giả/phát lại, và bị từ chối với camera
thật (có bài riêng).
"""
import importlib.util
import json
import math
import os
import subprocess
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
pytest.importorskip("PySide6")
pytest.importorskip("shapely")

from PySide6.QtWidgets import QApplication, QDockWidget  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

from autopark.application.session import SessionState  # noqa: E402
from autopark.application.vehicle_link import SESSION_STOP, DriveMode  # noqa: E402
from autopark.domain.types import Obstacle  # noqa: E402
from autopark.fusion import camera_ai  # noqa: E402
from autopark.geometry.footprint import obstacle_polygon  # noqa: E402
from autopark.perception.bev import SyntheticBox, SyntheticScene, synthetic_prob_map  # noqa: E402
from autopark.rig.core import Rig, RigConfig  # noqa: E402
from autopark.ui import lidar_app, theme  # noqa: E402
from autopark.ui.camera_dock import POSE_BENCH, POSE_CAR  # noqa: E402
from autopark.ui.lidar_app import build_window  # noqa: E402
from autopark.video.multicam import CameraSpec, MultiCameraManager  # noqa: E402
from tests.rig_fakes import FakeCamera, FakeSegmenter, FakeTiming, fake_manager  # noqa: E402

SIZE = (640, 480)
ON_PATH = SyntheticBox(0.9, 1.1, -0.1, 0.1, 0.15)          # hệ xe/camera: ngay trên đường thẳng tới đích
OFF_PATH = SyntheticBox(0.8, 1.0, 0.45, 0.6, 0.15)         # lệch trái 45 cm: không chạm hành lang
TOL = 0.10


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def front_calibration():
    return camera_ai.synthetic_camera_rig((1,), SIZE).cameras["p1"].calibration


class SceneSegmenter(FakeSegmenter):
    """P(BLOCKED) của `scene` nhìn từ camera trước tổng hợp; ảnh vào không được đọc. Đổi `scene` lúc đang chạy được."""

    def __init__(self, path, calibration, scene):
        super().__init__(path, delay=0.002)
        self.calibration, self.scene = calibration, scene
        self._cache = {}

    def infer(self, images, out_size=None):
        self.batch_sizes.append(len(images))
        time.sleep(self.delay)
        scene, out = self.scene, []
        for k, image in enumerate(images):
            size = (image.shape[1], image.shape[0]) if out_size is None else \
                tuple(out_size[k] if isinstance(out_size, list) else out_size)
            if (scene, size) not in self._cache:
                self._cache[(scene, size)] = synthetic_prob_map(self.calibration, scene, out_size=size)
            out.append(self._cache[(scene, size)])
        return out, FakeTiming(len(images))


def open_window(**camera):
    window, dock = build_window(None, port="COM9", recording=None, camera_ai={"ports": (1,), **camera})
    window._timer.stop()
    dock.timer.stop()
    window.camera_dock.timer.stop()
    return window, window.camera_dock


def fake_rig(seg):
    cams = fake_manager(ports=(1,), period=0.03, size=SIZE)
    return Rig(cams, RigConfig(checkpoint="gia.pt"), make_segmenter=lambda path: seg)


def record_fake_camera_session(folder, seconds=1.5):
    """Như tests/test_rig_replay.record_fake_session (Rig thật, camera giả, ghi PNG) nhưng mode ghi trong meta khớp khung
    giả 640×480 — `fake_manager` để mode mặc định 1280×720, và nguồn AI từ chối khung khác cỡ hiệu chuẩn."""
    cams = MultiCameraManager([CameraSpec(port=1, index=0)], width=SIZE[0], height=SIZE[1], ring=3,
                              open_source=lambda spec: FakeCamera(spec, period=0.03, size=SIZE))
    rig = Rig(cams, RigConfig(ai=False))
    rig.start()
    try:
        time.sleep(0.3)
        rig.start_recording(folder, image_format="png", notes={"test": "AI camera"})
        time.sleep(seconds)
        status = rig.stop_recording(wait=True)
    finally:
        assert rig.stop() == []
    assert status["frames"][1] > 20
    return status


def pump(dock, until, timeout=10.0):
    """Gọi tick() như timer 50 ms tới khi `until()` đúng (AI chạy trong luồng riêng của Rig)."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        dock.tick()
        if until():
            return True
        time.sleep(0.02)
    return False


def zone(box, pose, tol=TOL):
    corners = [(box.x_min, box.y_min), (box.x_max, box.y_min), (box.x_max, box.y_max), (box.x_min, box.y_max)]
    return Polygon([pose.to_world(x, y) for x, y in corners]).buffer(tol)


def ai_ids(window):
    return [o.id for o in window.session.scenario.obstacles if o.id.startswith("camera_ai_")]


# ---- chỉnh sa bàn: bản ghi phát lại → vật cản trên sa bàn -----------------------------------------------------------
def test_replayed_session_puts_the_ai_obstacle_on_the_board_and_never_touches_other_obstacles(qapp, tmp_path,
                                                                                                front_calibration):
    folder = tmp_path / "phiên AI"
    record_fake_camera_session(folder)
    window, dock = open_window(replay=folder, test_rig=True)
    session = window.session
    lidar_box = Obstacle("lidar_00007", 2.5, 0.4, 0.1, 0.1)                # chỗ camera trước thấy sàn trống
    user_box = Obstacle("obs_9", 2.5, 1.6, 0.1, 0.1)
    session.add_obstacle(lidar_box)
    session.add_obstacle(user_box)
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(ON_PATH,)))
    assert dock.start_ai(make_segmenter=lambda path: seg)
    assert dock.source_kind == camera_ai.SOURCE_REPLAY and dock.camera_rig.synthetic
    assert "RIG TỔNG HỢP" in dock.lbl_source.text() and dock.lbl_synthetic.isVisibleTo(dock)
    assert pump(dock, lambda: bool(dock.bridge.owned())), dock.lbl_gate.text()
    owned = dock.bridge.owned()
    assert all(obstacle_polygon(o).within(zone(ON_PATH, session.scenario.start)) for o in owned)
    assert camera_ai.SYNTHETIC_NOTE in dock.lbl_gate.text() and "BEV dùng được" in dock.lbl_gate.text()
    assert f"; {len(owned)} hộp AI trên sa bàn" in dock.lbl_gate.text()        # số hộp SAU khi đồng bộ, không trễ một nhịp
    assert all(o.id in window._obstacle_items for o in owned) and "vật thể từ AI" in dock.lbl_map.text()
    # camera thấy sàn TRỐNG ở chỗ hộp LiDAR và hộp người dùng: FREE của camera không xóa hay sửa gì của nguồn khác
    pump(dock, lambda: dock.rig.replay.finished, timeout=6.0)
    pump(dock, lambda: dock.stale, timeout=2.0)                              # hết bản ghi → AI cũ
    ids = [o.id for o in session.scenario.obstacles]
    assert "lidar_00007" in ids and "obs_9" in ids
    assert session.scenario.obstacle_by_id("lidar_00007") == lidar_box
    assert dock.bridge.owned(), "AI cũ lúc chỉnh sa bàn: giữ hộp AI đã có, không xóa"
    assert "HẾT BẢN GHI" in dock.lbl_rate.text() and "CŨ" in dock.lbl_rate.text()
    dock.clear_ai_obstacles()                                                # chỉ hộp AI bị xóa
    assert ai_ids(window) == [] and {"lidar_00007", "obs_9"} <= {o.id for o in session.scenario.obstacles}
    dock.shutdown()
    assert dock.rig is None
    window.close()


# ---- đang chạy: vật mới trên đường → MAP_CHANGED --------------------------------------------------------------------
def test_new_ai_obstacle_on_the_path_stops_the_run_and_the_known_one_does_not(qapp, front_calibration):
    window, dock = open_window(test_rig=True)
    session = window.session
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(OFF_PATH,)))
    dock.attach_rig(fake_rig(seg), camera_ai.SOURCE_FAKE)
    try:
        assert pump(dock, lambda: bool(dock.bridge.owned())), dock.lbl_gate.text()
        known = ai_ids(window)
        assert all(obstacle_polygon(session.scenario.obstacle_by_id(i)).within(zone(OFF_PATH, session.scenario.start))
                   for i in known)
        assert window.plan(sync=True).ok                                    # planner tránh hộp AI
        pump(dock, lambda: False, timeout=0.3)
        assert ai_ids(window) == known                                       # READY: bản đồ giữ cố định
        window.run()
        assert session.state == SessionState.RUNNING
        window.advance_by(1.0)
        assert abs(session.world.state.speed) > 0.05
        dock.tick()
        for widget in (dock.spin_threshold, dock.spin_window, dock.spin_min_hits, dock.spin_mask, dock.combo_pose):
            assert not widget.isEnabled()                                    # khóa khi chạy
        pump(dock, lambda: False, timeout=0.4)                               # vật đã biết vẫn đó: không dừng
        assert session.state == SessionState.RUNNING and dock.new_on_path == 0
        seg.scene = SyntheticScene(boxes=(OFF_PATH, ON_PATH))                # "đặt" một hộp lên đường
        assert pump(dock, lambda: session.state != SessionState.RUNNING), dock.lbl_gate.text()
        assert session.state == SessionState.STOPPING and dock.new_on_path >= 1
        assert any(e.code == "MAP_CHANGED" for e in session.safety_events)
        injected = [i for i in ai_ids(window) if i not in known]
        assert injected and all(obstacle_polygon(session.scenario.obstacle_by_id(i)).within(
            zone(ON_PATH, session.scenario.start)) for i in injected)
        assert "Vật mới từ AI trên đường" in dock.lbl_track.text()
        for _ in range(50):
            window.advance_by(0.1)
            if not session.simulating:
                break
        assert session.state == SessionState.STOPPED and not session.world.collided
    finally:
        dock.shutdown()
        window.close()


def test_stale_ai_while_driving_warns_by_default_and_stops_only_when_required(qapp, front_calibration):
    window, dock = open_window(test_rig=True)
    session = window.session
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(OFF_PATH,)))
    rig = fake_rig(seg)
    dock.attach_rig(rig, camera_ai.SOURCE_FAKE)
    try:
        assert pump(dock, lambda: bool(dock.bridge.owned()))
        known = ai_ids(window)
        assert window.plan(sync=True).ok
        window.run()
        window.advance_by(0.5)
        dock.tick()
        assert not dock.stale and session.state == SessionState.RUNNING
        dock._now = lambda: rig.clock() + 5.0                                 # 5 s không có lô mới
        dock.tick()
        dock.tick()
        assert dock.stale and "CŨ" in dock.lbl_rate.text()
        assert session.state == SessionState.RUNNING and dock.stale_warnings == 1   # cảnh báo MỘT lần, xe vẫn chạy
        assert ai_ids(window) == known                                       # giữ vật cản đã có
        assert any("giữ vật cản đã có" in dock.log.item(k).text() for k in range(dock.log.count()))
        dock.chk_required.setChecked(True)
        dock.tick()
        assert session.state == SessionState.STOPPING and dock.stale_stops == 1
        assert "AI camera" in session.stop_reason and "AI bắt buộc" in session.stop_reason
    finally:
        dock.shutdown()
        window.close()


def running_in_vehicle_io(front_calibration):
    """Như `running_with_known_box` nhưng chạy qua nhánh 'VehicleIO: gửi lệnh tới bo' với bo mô phỏng của cửa sổ (không
    mở cổng nào); trả về khi xe đang chạy và AI đang mới."""
    window, dock = open_window(test_rig=True)
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(OFF_PATH,)))
    rig = fake_rig(seg)
    dock.attach_rig(rig, camera_ai.SOURCE_FAKE)
    assert pump(dock, lambda: bool(dock.bridge.owned())), dock.lbl_gate.text()
    combo = window.combo_drive
    combo.setCurrentIndex(combo.findData(DriveMode.VEHICLE_IO.value))
    assert window.session.drive_mode == DriveMode.VEHICLE_IO and window.board_port() is None
    assert window.plan(sync=True).ok
    window.run()
    window.advance_by(0.5)
    # Test bật 'AI bắt buộc' sau bước này: nhịp đầu sau lúc luồng giao diện bận chạy mô phỏng có thể thấy AI cũ (AI
    # không bắt buộc thì chỉ cảnh báo), nên chờ tới khi AI mới để mã dừng đúng là mã test gây ra.
    assert pump(dock, lambda: not dock.stale, timeout=3.0) and window.session.state == SessionState.RUNNING
    return window, dock, rig


def broken_update(*a, **k):
    raise RuntimeError("hỏng giả")


@pytest.mark.parametrize("case, code", [("stale", "CAMERA_AI_STALE"), ("disabled", "CAMERA_AI_DISABLED"),
                                        ("error", "CAMERA_AI_ERROR"), ("config", "CAMERA_AI_CONFIG_CHANGED"),
                                        ("unknown_kind", "CAMERA_AI_UNUSABLE")])
def test_ai_stop_in_vehicle_io_is_logged_with_its_code(qapp, front_calibration, case, code):
    """T13 (02/10/2026): qua VehicleIO, yêu cầu dừng của ngăn AI camera thành dòng session_stop đầu tiên của events.csv
    với mã của nó và nguồn camera_dock: AI quá cũ, tắt AI, lỗi bất ngờ khi xử lý lô (ba trường hợp có 'AI bắt buộc'), và
    đổi cấu hình trong lúc chạy (chốt chặn cuối, ô bị khóa). Sau review 02/10/2026: loại "không dùng được" chưa có trong
    bảng mã vẫn dừng xe, với mã chung CAMERA_AI_UNUSABLE (trước đó KeyError trong timer và xe không dừng)."""
    window, dock, rig = running_in_vehicle_io(front_calibration)
    session = window.session
    try:
        dock.chk_required.setChecked(True)
        if case == "stale":
            dock._now = lambda: rig.clock() + 5.0                             # 5 s không có lô mới
            dock.tick()
        elif case == "disabled":
            dock.stop_ai()
        elif case == "error":
            dock.mapper.update = broken_update
            dock.tick()
        elif case == "unknown_kind":
            dock._unusable_while_driving("dong_bang", "camera đứng hình")       # loại mới quên thêm vào bảng mã
        else:
            dock.spin_threshold.setValue(0.20)
            dock.tick()
        assert session.state == SessionState.STOPPING and dock.stale_stops == 1
        first = next(r for r in session.run_link.event_rows if r["handling"] == SESSION_STOP)
        assert (first["code"], first["source"], first["action"]) == (code, "camera_dock", "STOP")
        assert first["message"] == session.stop_reason
        if case == "stale":
            assert "quá cũ" in first["message"]
    finally:
        dock.shutdown()
        window.close()


def test_every_unusable_kind_used_by_the_dock_has_its_own_stop_code():
    """Sau review 02/10/2026: mọi loại `kind` mà ngăn truyền cho `_unusable_while_driving` có mã dừng riêng trong
    `_UNUSABLE_CODES` (mã chung CAMERA_AI_UNUSABLE chỉ là lưới an toàn khi quên)."""
    import inspect
    import re

    from autopark.ui import camera_dock

    kinds = set(re.findall(r'_unusable_while_driving\(\s*"(\w+)"', inspect.getsource(camera_dock)))
    assert {"error", "blocked", "none", "stale"} <= kinds <= set(camera_dock._UNUSABLE_CODES)
    assert camera_dock._UNUSABLE_DEFAULT_CODE not in camera_dock._UNUSABLE_CODES.values()


def test_frozen_camera_makes_the_ai_stale_then_required_ai_stops_the_run(qapp, front_calibration):
    """T6 (CB-2, phần MP; thêm 02/10/2026): camera giả duy nhất THẬT SỰ ngừng trả khung (STALL của `FreezeSwitch`, cài
    trước khi dựng Rig) giữa lúc xe ảo chạy — không dời đồng hồ như test trên. AI cũ sau ≈ 0,5 s: cảnh báo một lần, xe
    vẫn chạy, giữ hộp AI; bật 'AI bắt buộc' thì dừng."""
    from autopark.safety.fault_injection import FaultLog, FreezeMode, FreezeSwitch, freezable_open_source

    window, dock = open_window(test_rig=True)
    session = window.session
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(OFF_PATH,)))
    log = FaultLog()
    switch = FreezeSwitch("cam_p1", log=log)
    cams = fake_manager(ports=(1,), period=0.03, size=SIZE)
    worker = cams.workers[1]
    worker.open_source = freezable_open_source(worker.open_source, {1: switch})
    rig = Rig(cams, RigConfig(checkpoint="gia.pt"), make_segmenter=lambda path: seg)
    dock.attach_rig(rig, camera_ai.SOURCE_FAKE)
    try:
        assert pump(dock, lambda: bool(dock.bridge.owned()))
        known = ai_ids(window)
        assert window.plan(sync=True).ok
        window.run()
        window.advance_by(0.5)
        dock.tick()
        assert not dock.stale and session.state == SessionState.RUNNING
        t_freeze = switch.freeze(FreezeMode.STALL).t_rig
        assert pump(dock, lambda: dock.stale, timeout=1.5), dock.lbl_rate.text()
        assert rig.clock() - t_freeze >= 0.45                               # tuổi lô AI phải quá 0,5 s mới "cũ"
        assert "CŨ" in dock.lbl_rate.text()
        assert session.state == SessionState.RUNNING and dock.stale_warnings == 1   # cảnh báo MỘT lần, xe vẫn chạy
        assert ai_ids(window) == known                                       # giữ vật cản đã có
        dock.chk_required.setChecked(True)
        dock.tick()
        assert session.state == SessionState.STOPPING and dock.stale_stops == 1
        assert "AI camera" in session.stop_reason and "quá cũ" in session.stop_reason
        assert [r.code for r in log.records] == ["FAULT_CAMERA_STALL"]
    finally:
        switch.release()                                                     # TRƯỚC khi dừng luồng camera
        dock.shutdown()
        window.close()


# ---- chặn --------------------------------------------------------------------------------------------------------------
def test_synthetic_rig_is_refused_with_live_cameras(qapp, front_calibration, monkeypatch):
    import autopark.video.multicam as multicam

    def no_devices(*a, **k):
        raise AssertionError("không được mở camera thật")
    monkeypatch.setattr(multicam, "resolve_ports", no_devices)
    window, dock = open_window(test_rig=True)
    assert dock.start_ai(make_segmenter=lambda path: FakeSegmenter(path)) is False   # không có bản ghi: từ chối
    assert dock.rig is None and "TỔNG HỢP" in dock.lbl_source.text()
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(ON_PATH,)))
    dock.attach_rig(fake_rig(seg), camera_ai.SOURCE_LIVE)                   # nguồn khai là camera thật
    try:
        assert dock.mapper.blocked
        pump(dock, lambda: dock.mapper.batches >= 4)
        assert dock.mapper.batches >= 4 and dock.mapper.batches_usable == 0
        assert dock.bridge.owned() == [] and ai_ids(window) == []
        text = dock.lbl_gate.text()
        assert text.startswith(camera_ai.GATE_PREFIX) and "TỔNG HỢP" in text and "camera thật" in text
    finally:
        dock.shutdown()
        window.close()


def test_real_rig_without_calibration_files_adds_nothing_and_says_why(qapp, tmp_path, front_calibration):
    window, dock = open_window(calibration_dir=tmp_path / "calibration", roi_dir=tmp_path / "roi",
                               extrinsics=tmp_path / "camera_rig_extrinsics_v1.json")
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(ON_PATH,)))
    dock.attach_rig(fake_rig(seg), camera_ai.SOURCE_LIVE)
    try:
        assert not dock.camera_rig.synthetic and dock.mapper.blocked and dock.lbl_synthetic is None
        pump(dock, lambda: dock.mapper.batches >= 3)
        assert ai_ids(window) == []
        text = dock.lbl_gate.text()
        # thiếu tệp: kể đủ theo trình tự làm (nội tham → ngoại tham → ROI) kèm tài liệu, không phải lỗi hệ điều hành
        assert text.startswith(camera_ai.GATE_PREFIX) and "chưa có tệp ngoại tham đã đo" in text and "Errno" not in text
        assert text.index("HIEU_CHUAN_CAMERA") < text.index("NGOAI_THAM_VA_ROI.md mục 1") < text.index("mục 6")
        assert any(dock.log.item(k).text().startswith(camera_ai.GATE_PREFIX) for k in range(dock.log.count()))
    finally:
        dock.shutdown()
        window.close()


# ---- tệp hiệu chuẩn hỏng, lỗi bất ngờ: ngăn không bao giờ giữ Rig mà không có nguồn vật cản -------------------------
def break_intrinsics(paths, **changes):
    f = paths["calibration_dir"] / "cam_p1.json"
    record = json.loads(f.read_text(encoding="utf-8"))
    record.update(changes)
    f.write_text(json.dumps(record), encoding="utf-8")


def run_with_required(window, dock):
    dock.chk_required.setChecked(True)
    assert window.plan(sync=True).ok
    window.run()
    window.advance_by(0.5)
    assert window.session.state == SessionState.RUNNING
    dock.tick()


@pytest.mark.parametrize("case", ["synthetic_typo", "odd_intrinsics", "loader_raises"])
def test_attach_rig_with_broken_camera_rig_keeps_a_blocked_mapper_and_required_stops(qapp, front_calibration, tmp_path,
                                                                                    monkeypatch, case):
    from tests.test_camera_ai_layer import write_real_rig

    if case == "synthetic_typo":                        # gõ sai tên tệp ngoại tham của rig tổng hợp
        window, dock = open_window(test_rig=True, extrinsics=tmp_path / "khong_co.json")
        kind = camera_ai.SOURCE_FAKE
    else:
        paths = write_real_rig(tmp_path / "r", (1,))
        if case == "odd_intrinsics":                    # tệp nội tham sửa tay kiểu lạ: fisheye_calib ném TypeError
            break_intrinsics(paths, camera=5)
        else:                                           # lỗi bất ngờ ngay trong hàm nạp
            def boom(*a, **k):
                raise RuntimeError("hỏng giả khi nạp")
            monkeypatch.setattr(camera_ai, "load_camera_rig", boom)
        window, dock = open_window(**paths)
        kind = camera_ai.SOURCE_LIVE
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(OFF_PATH,)))
    try:
        dock.attach_rig(fake_rig(seg), kind)                                 # không ném
        assert dock.rig is not None and dock.mapper is not None and dock.mapper.blocked
        assert dock.btn_start.text() == "Tắt AI camera"
        assert dock.lbl_gate.text().startswith(camera_ai.GATE_PREFIX)
        dock.tick()                                                          # không ném
        assert ai_ids(window) == []
        run_with_required(window, dock)
        assert window.session.state == SessionState.STOPPING and dock.stale_stops == 1
        assert "AI bắt buộc" in window.session.stop_reason
    finally:
        dock.shutdown()
        window.close()


def test_unexpected_error_in_tick_is_unusable_ai_and_stops_only_when_required(qapp, front_calibration):
    window, dock = open_window(test_rig=True)
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(OFF_PATH,)))
    dock.attach_rig(fake_rig(seg), camera_ai.SOURCE_FAKE)
    try:
        assert pump(dock, lambda: bool(dock.bridge.owned()))
        assert window.plan(sync=True).ok
        window.run()
        window.advance_by(0.5)

        def boom(*a, **k):
            raise RuntimeError("hỏng giả")
        dock.mapper.update = boom
        dock.tick()
        dock.tick()                                                          # không ném; cảnh báo MỘT lần
        assert window.session.state == SessionState.RUNNING and dock.stale_warnings == 1
        assert dock.lbl_gate.text().startswith(camera_ai.GATE_PREFIX) and "hỏng giả" in dock.lbl_gate.text()
        dock.chk_required.setChecked(True)
        dock.tick()
        assert window.session.state == SessionState.STOPPING and dock.stale_stops == 1
    finally:
        dock.shutdown()
        window.close()


# ---- nhịp: đồng hồ, cửa sổ lọc, cảnh báo ----------------------------------------------------------------------------
def test_tick_reads_the_clock_after_the_batch_so_a_fresh_batch_is_never_stale(qapp, front_calibration):
    window, dock = open_window(test_rig=True)
    session = window.session
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(OFF_PATH,)))
    rig = fake_rig(seg)
    dock.attach_rig(rig, camera_ai.SOURCE_FAKE)
    original = rig.ai.result
    try:
        assert pump(dock, lambda: bool(dock.bridge.owned()))
        assert window.plan(sync=True).ok
        window.run()
        window.advance_by(0.5)
        dock.tick()
        assert session.state == SessionState.RUNNING
        dock.chk_required.setChecked(True)

        def late_result():
            """Luồng giao diện 'đứng' giữa hai dòng: trả lô mới mà khung cũ nhất chụp SAU lúc gọi."""
            t_call = rig.clock()
            deadline = time.perf_counter() + 2.0
            while time.perf_counter() < deadline:
                r = original()
                if r is not None and r.frame_set.t_min > t_call:
                    return r
                time.sleep(0.002)
            raise AssertionError("không có lô mới trong 2 s")
        rig.ai.result = late_result
        dock.tick()
        upd = dock.last_update
        assert upd.processed and upd.usable
        assert not dock.stale and session.state == SessionState.RUNNING and dock.stale_stops == 0
        assert "tuổi -" not in dock.lbl_rate.text()                          # tuổi không bao giờ âm
    finally:
        rig.ai.result = original
        dock.shutdown()
        window.close()


def test_filter_window_reset_while_editing_keeps_the_ai_boxes(qapp, front_calibration):
    window, dock = open_window(test_rig=True)
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(ON_PATH,)))
    dock.attach_rig(fake_rig(seg), camera_ai.SOURCE_FAKE)
    try:
        assert pump(dock, lambda: bool(dock.bridge.owned()))
        pump(dock, lambda: False, timeout=0.3)
        known = ai_ids(window)
        assert known
        # giao diện đứng 0,7 s (> 0,5 s: cửa sổ lọc xóa), rồi đổi ngưỡng (nguồn vật cản dựng lại)
        for disturb in (lambda: time.sleep(0.7), lambda: dock.spin_threshold.setValue(0.20)):
            resets, mapper = dock.mapper.window_resets, dock.mapper
            disturb()
            fills = []
            for _ in range(8):
                dock.tick()
                if dock.last_update.processed:
                    fills.append(dock.last_update.window_fill)
                assert ai_ids(window) == known, fills                        # không biến mất rồi hiện lại với id mới
                time.sleep(0.04)
            assert fills and fills[0] == 1
            assert dock.mapper.window_resets > resets or dock.mapper is not mapper
        assert "Cửa sổ lọc đang đầy lại" in dock.lbl_map.text() or "vật thể từ AI" in dock.lbl_map.text()
        seg.scene = SyntheticScene(boxes=())                                 # vật mất thật: hộp AI vẫn được bỏ
        assert pump(dock, lambda: not ai_ids(window), timeout=3.0)
    finally:
        dock.shutdown()
        window.close()


def test_ai_warnings_are_given_once_per_kind_per_run(qapp, front_calibration):
    window, dock = open_window(test_rig=True)
    session = window.session
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(OFF_PATH,)))
    rig = fake_rig(seg)
    dock.attach_rig(rig, camera_ai.SOURCE_FAKE)
    try:
        assert pump(dock, lambda: bool(dock.bridge.owned()))
        assert window.plan(sync=True).ok
        window.run()
        window.advance_by(0.5)
        for _ in range(3):                                                   # cũ → mới lại → cũ lại, ba đợt
            dock._now = lambda: rig.clock() + 5.0
            dock.tick()
            dock.tick()
            assert dock.stale
            dock._now = rig.clock
            assert pump(dock, lambda: not dock.stale, timeout=3.0)
        assert session.state == SessionState.RUNNING and dock.stale_warnings == 1
        warnings = [dock.log.item(k).text() for k in range(dock.log.count())
                    if dock.log.item(k).text().startswith("Cảnh báo: AI camera không dùng được")]
        assert len(warnings) == 1 and "quá cũ" in warnings[0]

        def boom(*a, **k):
            raise RuntimeError("hỏng giả")
        dock.mapper.update = boom                                            # loại khác: cảnh báo riêng, một lần
        dock.tick()
        dock.tick()
        assert dock.stale_warnings == 2 and session.state == SessionState.RUNNING
    finally:
        dock.shutdown()
        window.close()


def test_min_hits_box_never_shows_more_than_the_window_it_filters(qapp):
    window, dock = open_window(test_rig=True)
    try:
        assert (dock.spin_window.value(), dock.spin_min_hits.value()) == (camera_ai.AI_WINDOW, camera_ai.AI_MIN_HITS)
        dock.spin_window.setValue(1)                                         # "1 lô gộp", để nguyên "2 lần thấy"
        assert dock.spin_min_hits.value() == 1 == dock._settings()[3]        # ô hiện đúng luật đang dùng: 1/1
        dock.spin_window.setValue(3)
        assert dock.spin_min_hits.maximum() == 3
        dock.spin_min_hits.setValue(3)
        dock.spin_window.setValue(2)
        assert dock.spin_min_hits.value() == 2 == dock._settings()[3]
    finally:
        dock.shutdown()
        window.close()


# ---- cách đặt camera: trên bàn / trên xe ----------------------------------------------------------------------------
@pytest.mark.parametrize("mode", [POSE_CAR, POSE_BENCH])
def test_new_ai_obstacle_is_placed_by_the_camera_mounting_mode(qapp, front_calibration, mode):
    window, dock = open_window(test_rig=True)
    session = window.session
    assert dock.combo_pose.currentIndex() == POSE_BENCH                      # mặc định: camera cố định trên bàn
    dock.combo_pose.setCurrentIndex(mode)
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(OFF_PATH,)))
    dock.attach_rig(fake_rig(seg), camera_ai.SOURCE_FAKE)
    try:
        assert pump(dock, lambda: bool(dock.bridge.owned())), dock.lbl_gate.text()
        known = ai_ids(window)
        start = session.scenario.start
        # chỉnh sa bàn: cả hai chế độ đặt theo chỗ xuất phát
        assert all(obstacle_polygon(session.scenario.obstacle_by_id(i)).within(zone(OFF_PATH, start)) for i in known)
        assert window.plan(sync=True).ok
        window.run()
        for _ in range(60):                                                  # xe đi hẳn > 40 cm (hộp ± 10 cm tách hẳn)
            window.advance_by(0.1)
            if session.world.state.pose.x - start.x > 0.40:
                break
        pose = session.world.state.pose
        assert session.state == SessionState.RUNNING and pose.x - start.x > 0.40, pose
        pump(dock, lambda: False, timeout=0.4)                               # hộp lệch trái: ngoài hành lang, không dừng
        assert session.state == SessionState.RUNNING and dock.new_on_path == 0
        seg.scene = SyntheticScene(boxes=(OFF_PATH, ON_PATH))                # "đặt" một hộp trước camera
        assert pump(dock, lambda: session.state != SessionState.RUNNING), dock.lbl_gate.text()
        assert any(e.code == "MAP_CHANGED" for e in session.safety_events)
        injected = [i for i in ai_ids(window) if i not in known]
        assert injected
        polys = [obstacle_polygon(session.scenario.obstacle_by_id(i)) for i in injected]
        right, wrong = (pose, start) if mode == POSE_CAR else (start, pose)
        assert all(p.within(zone(ON_PATH, right)) for p in polys)            # trên xe: theo tư thế xe; trên bàn: chỗ xuất phát
        assert not any(p.within(zone(ON_PATH, wrong)) for p in polys)
    finally:
        dock.shutdown()
        window.close()


# ---- ô và nút của ngăn -----------------------------------------------------------------------------------------------
KHOA_KHI_CHAY = ("spin_threshold", "spin_window", "spin_min_hits", "spin_mask", "combo_pose", "btn_reload",
                 "edit_calib", "edit_extr", "edit_roi")


def running_with_known_box(front_calibration):
    """Rig tổng hợp + camera giả thấy OFF_PATH; lập đường, chạy 0,5 s. Kiểm các ô mở lúc chỉnh sa bàn."""
    window, dock = open_window(test_rig=True)
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(OFF_PATH,)))
    dock.attach_rig(fake_rig(seg), camera_ai.SOURCE_FAKE)
    assert pump(dock, lambda: bool(dock.bridge.owned())), dock.lbl_gate.text()
    known = ai_ids(window)
    for name in KHOA_KHI_CHAY:
        assert getattr(dock, name).isEnabled(), name                        # EDITING: mở
    assert window.plan(sync=True).ok
    window.run()
    window.advance_by(0.5)
    dock.tick()
    assert window.session.state == SessionState.RUNNING
    return window, dock, seg, known


def test_switching_ai_off_while_driving_stops_only_when_required(qapp, front_calibration):
    window, dock, seg, known = running_with_known_box(front_calibration)
    session = window.session
    try:
        for name in KHOA_KHI_CHAY:
            assert not getattr(dock, name).isEnabled(), name                # RUNNING: khóa, cả ô hiệu chuẩn
        dock.stop_ai()                                                       # mặc định: AI không bắt buộc
        assert dock.rig is None and session.state == SessionState.RUNNING and dock.stale_stops == 0
        assert ai_ids(window) == known
        assert any("AI không bắt buộc" in dock.log.item(k).text() for k in range(dock.log.count()))
        dock.attach_rig(fake_rig(seg), camera_ai.SOURCE_FAKE)               # bật lại giữa lần chạy
        dock.chk_required.setChecked(True)
        dock.stop_ai()
        assert session.state == SessionState.STOPPING and dock.stale_stops == 1
        assert "tắt AI camera" in session.stop_reason and "AI bắt buộc" in session.stop_reason
    finally:
        dock.shutdown()
        window.close()


def test_track_box_off_a_new_box_on_the_path_does_not_stop_the_run(qapp, front_calibration):
    window, dock, seg, known = running_with_known_box(front_calibration)
    session = window.session
    try:
        dock.chk_track.setChecked(False)
        seg.scene = SyntheticScene(boxes=(OFF_PATH, ON_PATH))
        start = dock.mapper.batches_usable
        assert pump(dock, lambda: dock.mapper.batches_usable >= start + 6)
        assert session.state == SessionState.RUNNING and dock.new_on_path == 0 and ai_ids(window) == known
        assert not any(e.code == "MAP_CHANGED" for e in session.safety_events)
        dock.chk_track.setChecked(True)                                      # đối chứng: AI có thấy hộp trên đường
        assert pump(dock, lambda: session.state != SessionState.RUNNING)
        assert session.state == SessionState.STOPPING and dock.new_on_path >= 1
    finally:
        dock.shutdown()
        window.close()


def test_live_box_off_freezes_the_ai_boxes_while_editing(qapp, front_calibration):
    window, dock = open_window(test_rig=True)
    session = window.session
    seg = SceneSegmenter("gia.pt", front_calibration, SyntheticScene(boxes=(OFF_PATH,)))
    dock.attach_rig(fake_rig(seg), camera_ai.SOURCE_FAKE)
    try:
        assert pump(dock, lambda: bool(dock.bridge.owned()))
        frozen = [session.scenario.obstacle_by_id(i) for i in ai_ids(window)]
        dock.chk_live.setChecked(False)
        seg.scene = SyntheticScene(boxes=(ON_PATH,))                         # AI giờ thấy vật ở chỗ khác
        start = dock.mapper.batches_usable
        assert pump(dock, lambda: dock.mapper.batches_usable >= start + 6)
        assert session.state == SessionState.EDITING
        assert [session.scenario.obstacle_by_id(i) for i in ai_ids(window)] == frozen
        dock.chk_live.setChecked(True)                                       # đối chứng: bật lại thì hộp bám theo AI
        on_path = zone(ON_PATH, session.scenario.start)
        assert pump(dock, lambda: bool(ai_ids(window)) and all(
            obstacle_polygon(session.scenario.obstacle_by_id(i)).within(on_path) for i in ai_ids(window)))
    finally:
        dock.shutdown()
        window.close()


def test_synthetic_label_is_shown_red_at_the_top_of_the_dock(qapp):
    window, dock = open_window(test_rig=True)
    try:
        label = dock.lbl_synthetic
        assert label is not None and dock.isAncestorOf(label) and label.isVisibleTo(dock)
        assert "TỔNG HỢP" in label.text() and theme.DANGER in label.styleSheet()
        assert dock.widget().widget().layout().indexOf(label) == 1          # ngay sau dòng ghi công
    finally:
        dock.shutdown()
        window.close()


def test_real_start_without_torch_or_model_file_says_why_and_opens_nothing(qapp, tmp_path, monkeypatch):
    """AI_DIEU_KHIEN_XE.md mục 7: không có torch → "AI camera cần torch"; có torch mà thiếu tệp mô hình → "Không có tệp
    mô hình". Cả hai: trả False, không dựng Rig, không mở nguồn camera nào. Giả find_spec nên hai nhánh chạy trong CẢ
    .venv lẫn .venv-train."""
    import autopark.rig.replay as replay
    import autopark.video.multicam as multicam

    def no_source(*a, **k):
        raise AssertionError("không được mở nguồn camera khi thiếu torch hay thiếu mô hình")
    monkeypatch.setattr(multicam, "resolve_ports", no_source)
    monkeypatch.setattr(replay, "ReplaySession", no_source)
    real_find_spec = importlib.util.find_spec
    missing = tmp_path / "khong_co.pt"
    for has_torch, needle in ((False, "cần torch"), (True, f"Không có tệp mô hình {missing}")):
        def find_spec(name, *a, _has=has_torch, **k):
            if name == "torch":
                return real_find_spec("importlib") if _has else None
            return real_find_spec(name, *a, **k)
        monkeypatch.setattr(importlib.util, "find_spec", find_spec)
        window, dock = open_window(checkpoint=missing)
        try:
            assert dock.start_ai() is False
            assert dock.rig is None and needle in dock.lbl_source.text()
            assert any(needle in dock.log.item(k).text() for k in range(dock.log.count()))
            assert dock.btn_start.text() == "Bật AI camera" and dock.edit_checkpoint.isEnabled()
        finally:
            dock.shutdown()
            window.close()


def test_reload_calibration_with_ai_off_checks_the_files_and_opens_nothing(qapp, tmp_path, monkeypatch):
    import autopark.video.multicam as multicam
    from tests.test_camera_ai_layer import write_real_rig

    def no_devices(*a, **k):
        raise AssertionError("không được mở camera thật")
    monkeypatch.setattr(multicam, "resolve_ports", no_devices)
    no_roi = write_real_rig(tmp_path / "khong_roi", (1,), roi=False)
    good = write_real_rig(tmp_path / "tot", (1,))
    window, dock = open_window(**no_roi)
    try:
        assert dock.rig is None and dock.btn_reload.isEnabled()

        def check(**paths):
            for key, edit in (("calibration_dir", dock.edit_calib), ("extrinsics", dock.edit_extr),
                              ("roi_dir", dock.edit_roi)):
                if key in paths:
                    edit.setText(str(paths[key]))
            before = dock.log.count()
            dock.btn_reload.click()
            assert dock.rig is None and dock.mapper is None and dock.log.count() == before + 1
            assert "Kiểm hiệu chuẩn (AI đang tắt)" in dock.log.item(dock.log.count() - 1).text()
            return dock.lbl_gate.text()
        text = check()
        assert text.startswith(camera_ai.GATE_PREFIX) and "p1: chưa có ROI" in text
        assert "Hiệu chuẩn đọc được và đạt cho camera [1]" in check(**good)
        text = check(extrinsics=tmp_path / "khong_co.json")
        assert text.startswith(camera_ai.GATE_PREFIX) and "chưa có tệp ngoại tham đã đo" in text
    finally:
        dock.shutdown()
        window.close()


# ---- lidar_app không có tùy chọn camera: như cũ ---------------------------------------------------------------------
def test_lidar_app_without_camera_options_is_unchanged(qapp, capsys, monkeypatch):
    window, dock = build_window(None, port="COM9", recording=None)
    window._timer.stop()
    dock.timer.stop()
    assert window.camera_dock is None and window.windowTitle() == "Autopark — bàn thử LiDAR"
    assert window.findChildren(QDockWidget) == [dock]
    window.close()
    code = ("import sys, autopark.ui.lidar_app as a; print('torch' in sys.modules, "
            "'autopark.ui.camera_dock' in sys.modules, 'autopark.fusion.camera_ai' in sys.modules)")
    out = subprocess.run([sys.executable, "-X", "utf8", "-c", code], capture_output=True, text=True, encoding="utf-8",
                         env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["False", "False", "False"]

    def no_window(*a, **k):                  # dùng sai phải bị từ chối TRƯỚC khi mở cửa sổ (không treo ở app.exec())
        raise AssertionError("đã mở cửa sổ dù tùy chọn sai")
    monkeypatch.setattr(lidar_app, "build_window", no_window)
    for argv, needle in ((["--cam-ports", "1"], "chỉ dùng cùng --camera-ai"),
                         (["--camera-ai-test-rig"], "chỉ dùng cùng --camera-ai"),
                         (["--camera-ai", "--camera-ai-test-rig"], "chỉ dùng với --cam-replay")):
        with pytest.raises(SystemExit) as info:
            lidar_app.main(argv)
        assert info.value.code == 2 and needle in capsys.readouterr().err


def test_camera_options_build_a_tabbed_camera_dock(qapp, tmp_path):
    parser = lidar_app.argparse.ArgumentParser()
    lidar_app.add_camera_ai_args(parser)
    args = parser.parse_args(["--camera-ai", "--cam-ports", "2", "3", "--cam-replay", str(tmp_path),
                              "--camera-ai-test-rig"])
    options = lidar_app.camera_ai_options(parser, args)
    assert options["ports"] == (2, 3) and options["replay"] == tmp_path and options["test_rig"] is True
    assert lidar_app.camera_ai_options(parser, parser.parse_args([])) is None
    window, dock = build_window(None, port="COM9", recording=None, camera_ai=options)
    window._timer.stop()
    dock.timer.stop()
    cam = window.camera_dock
    cam.timer.stop()
    assert cam is not None and window.tabifiedDockWidgets(dock) == [cam]
    assert "RIG TỔNG HỢP" in window.windowTitle() and cam.edit_ports.text() == "2 3"
    assert cam.edit_extr.text().endswith("camera_rig_extrinsics_v0.json")   # rig tổng hợp: tư thế giả định v0
    text = cam.lbl_attribution.text()                                       # ghi công hiện ở đầu ngăn
    assert "WoodScape" in text and "github.com/valeoai/WoodScape" in text and "chưa xác nhận" in text
    window.close()
    plain = build_window(None, port="COM9", recording=None, camera_ai={"ports": (1, 2, 3, 4)})[0]
    assert plain.camera_dock.edit_extr.text().endswith("camera_rig_extrinsics_v1.json")
    assert plain.camera_dock.edit_roi.text().replace("\\", "/").endswith("configs/roi/rig_v1")
    assert math.isclose(plain.camera_dock.spin_threshold.value(), 0.15)
    plain.close()
