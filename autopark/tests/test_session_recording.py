"""Bản ghi cảm biến trong phiên đỗ (T3, `rig.session_recording`), không Qt và không phần cứng: camera giả qua `Rig` thật,
LiDAR giả qua `LidarTap` trong một luồng, chủ giả `FakeHost` thay cửa sổ `ui.lidar_app`.

Kiểm: camera + LiDAR + mốc đồng hồ vào MỘT thư mục trên cùng đồng hồ perf_counter và phát lại được bằng `rig.replay`
(cả khi chỉ có LiDAR); LiDAR khác đồng hồ bị loại có lý do; tắt Rig camera giữa chừng chỉ gỡ nó; ngưỡng đĩa; lỗi ghi tự
dừng; mốc ghép perf ↔ thời gian phiên ↔ đồng hồ VehicleIO; dòng lô AI; bảng phụ ra đĩa trong lúc ghi; vòng LiDAR lùi thời
gian bị bỏ và đếm; tệp trỏ của "Xuất log CSV…"."""
import csv
import json
import os
import threading
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from autopark.domain.sensors import LidarScan, SourceStamp  # noqa: E402
from autopark.evaluation.sync_marks import SYNC_FIELDS, SyncMarkLog, read_sync_marks  # noqa: E402
from autopark.lidar.live_view import ScanStreamEnded  # noqa: E402
from autopark.rig import bench  # noqa: E402
from autopark.rig import recording  # noqa: E402
from autopark.rig.core import Rig, RigConfig  # noqa: E402
from autopark.rig.recording import LidarTap, RigRecorder  # noqa: E402
from autopark.rig.replay import ReplaySession, load_lidar  # noqa: E402
from autopark.rig.session_recording import (AI_FIELDS, AI_TABLE, CLOCK_FIELDS, CLOCK_TABLE, GB, SYNC_COPY,  # noqa: E402
                                            RecordOptions, RecordStartError, SessionSensorRecorder, clean_name,
                                            read_session_clock)
from autopark.video.multicam import RIG_CLOCK, MultiCameraManager  # noqa: E402
from tests.rig_fakes import FakeLidar, fake_manager  # noqa: E402

PERIOD = 0.03


def rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class FakeHost:
    """Chủ giả của SessionSensorRecorder (thay BenchWindow): Rig camera, nguồn LiDAR và trạng thái phiên do test đặt."""

    def __init__(self, rig=None, lidar=None, *, camera_dock=True, clock_ok=True, kind="live", state="EDITING"):
        self.rig, self.lidar, self.camera_dock = rig, lidar, camera_dock
        self.lidar_key = 1
        self.clock_ok, self.kind, self.state = clock_ok, kind, state
        self.why = "" if clock_ok else "nguồn không dùng đồng hồ perf_counter của bàn thử (RIG_CLOCK)"
        self.context = lambda t: {"note": "SIM", "time_scale": 1.0}
        self.sync = SyncMarkLog("ui.lidar_app")
        self.window = "normal"

    def anchor_context(self, t_perf):
        return {"state": self.state, **self.context(t_perf)}

    def camera_rig(self):
        return self.rig

    def camera_info(self):
        if not self.camera_dock:
            return None
        ports = [] if self.rig is None else [s.port for s in self.rig.cams.specs]
        return {"on": self.rig is not None, "source_kind": "fake", "ports": ports, "synthetic": False}

    def lidar_info(self):
        if self.lidar is None:
            return None
        return {"source_key": self.lidar_key, "source_id": "fake_lidar", "kind": self.kind, "port": "COM_GIA",
                "recording": None, "describe": {"driver": "tests.rig_fakes"}, "clock_ok": self.clock_ok, "why": self.why,
                "settings": {"window": 3, "min_hits": 2, "mask_m": 0.1, "mirror": False, "anchor": [0.5, 1.0, 0.0]}}

    def lidar_stats(self):
        return None if self.lidar is None else {"scans": getattr(self.lidar, "n", 0)}

    def session_meta(self):
        return {"scenario": "gia", "scenario_path": None, "vehicle_config": "configs/vehicle_default.json",
                "drive_mode": "SIM", "board": "sim", "cusp_policy": {"max_cusps": None, "warn_cusps": 7},
                "state": self.state, "sync_marks_live_file": None}

    def sync_rows(self):
        return list(self.sync.rows)

    def window_state(self):
        return self.window


class TapReader(threading.Thread):
    """Như luồng đọc của ngăn LiDAR: đọc nguồn qua LidarTap, đẩy vòng quét vào bộ ghi mà `sink()` trả."""

    def __init__(self, source, sink):
        super().__init__(daemon=True)
        self.tap = LidarTap(source, sink, RIG_CLOCK)
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.tap.read()
            except Exception:  # noqa: BLE001
                time.sleep(0.01)


def recorder_for(host, root, *, free=100 * GB, **options):
    return SessionSensorRecorder(host, RecordOptions(root=root, **options), free_bytes=lambda path: free)


def run_for(recorder, seconds, step=0.1):
    deadline = time.perf_counter() + seconds
    messages = []
    while time.perf_counter() < deadline:
        messages += recorder.poll()
        time.sleep(step)
    return messages


def record_session(root, *, seconds=1.2, cameras=True, lidar=True, image_format="png"):
    """Rig thật với hai camera giả + LiDAR giả qua LidarTap; một dấu đồng bộ ở cửa sổ giả; ghi `seconds` giây."""
    rig = Rig(fake_manager(ports=(1, 2), period=PERIOD, textured=True), RigConfig(ai=False)) if cameras else None
    source = FakeLidar(period=0.1) if lidar else None
    host = FakeHost(rig, source)
    host.sync.add("SYNC_MARK", time.perf_counter(), trigger="button", state="EDITING", note="SIM")
    recorder = recorder_for(host, root, image_format=image_format)
    reader = TapReader(source, recorder.lidar_sink) if lidar else None
    if rig is not None:
        rig.start()
    if reader is not None:
        reader.start()
    try:
        time.sleep(0.3)
        rec = recorder.start("lần 1")
        run_for(recorder, seconds)
        recorder.stop()
        assert recorder.wait_finished(10.0)
    finally:
        if reader is not None:
            reader.stop_event.set()
        if rig is not None:
            assert rig.stop() == []
    return rec, host, recorder


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    rec, host, recorder = record_session(tmp_path_factory.mktemp("t3") / "gốc")
    return rec.folder, host, recorder


# ------------------------------------------------------------------------------------------------ một thư mục, một đồng hồ

def test_cameras_and_lidar_land_in_one_folder_on_the_perf_counter_clock(recorded):
    folder, host, recorder = recorded
    assert folder.name.endswith("_lần_1") and folder.parent.name == "gốc"
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["format"] == "autopark.rig_recording" and meta["format_version"] == 1 and meta["status"] == "xong"
    assert meta["ports"] == [1, 2] and [c["port"] for c in meta["cameras"]] == [1, 2]
    assert meta["lidar_source"]["clock"] == "perf_counter" and meta["lidar_source"]["port"] == "COM_GIA"
    sr = meta["session_recording"]
    assert sr["version"] == 1 and sr["app"] == "ui.lidar_app" and sr["stopped_by"] == "user"
    assert sr["sources"]["cameras"]["on"] and sr["sources"]["lidar"]["on"] and "perf_counter" in sr["align"]
    assert sr["disk"]["min_free_start_gb"] == 5.0 and sr["disk"]["stop_free_gb"] == 2.0 and sr["runs"] == []
    assert sorted(c["port"] for c in meta["cameras_at_stop"]) == [1, 2] and meta["lidar_at_stop"]["scans"] > 0
    assert meta["tables"][CLOCK_TABLE]["fields"] == list(CLOCK_FIELDS) and meta["files"] == [SYNC_COPY]
    lo, hi = meta["t_start_s"] - 0.2, meta["t_stop_s"] + 0.2
    for port in (1, 2):
        frames = rows(folder / f"cam_p{port}" / "frames.csv")
        assert len(frames) > 15 and all(lo <= float(r["t_s"]) <= hi for r in frames)
    lidar, _ = load_lidar(folder)
    assert len(lidar) >= 8 and meta["lidar"]["scans"] == len(lidar) and meta["lidar"]["out_of_order_dropped"] == 0
    assert ((lidar.t >= lo) & (lidar.t <= hi) & (lidar.t_first >= lo) & (lidar.t_first <= hi)).all()
    anchors = rows(folder / CLOCK_TABLE)
    assert [a["trigger"] for a in anchors][0] == "start" and anchors[-1]["trigger"] == "stop"
    assert sum(a["trigger"] == "periodic" for a in anchors) >= 1
    assert all(lo <= float(a["t_perf"]) <= hi for a in anchors)
    assert read_sync_marks(folder / SYNC_COPY) == host.sync.rows and host.sync.marks == 1   # bản sao; không thêm dòng
    session = ReplaySession(folder)                     # không lỗi "ngoài cửa sổ ghi": mọi nguồn cùng một đồng hồ
    assert session.has_lidar and session.ports == [1, 2] and 0.8 < session.duration_s < 2.5
    assert recorder.poll()[0].startswith("XONG: ")
    assert recorder.poll() == []                        # chỉ báo một lần


def test_session_recording_replays_through_the_rig_with_the_recorded_frames_and_scans(recorded, tmp_path):
    from tests.test_rig_replay import read_image, replay_through_rig

    folder, _, _ = recorded
    again = tmp_path / "ghi lại"
    session, st, cam_stats, lidar_stats, _, alive = replay_through_rig(folder, again)
    assert alive == [] and st["finished"]
    for port in (1, 2):
        a = rows(folder / f"cam_p{port}" / "frames.csv")
        b = rows(again / f"cam_p{port}" / "frames.csv")
        assert st["cameras"][port]["delivered"] == len(a) == len(b) == cam_stats[port]["frames"]
        assert rows(again / f"cam_p{port}" / "events.csv") == []         # camera giả không khung hỏng ở đây
        for x, y in zip(a, b):
            assert float(y["t_s"]) - session.origin == pytest.approx(float(x["t_s"]) - session.t_ref, abs=1e-6)
            assert np.array_equal(read_image(again / f"cam_p{port}" / y["file"]),
                                  read_image(folder / f"cam_p{port}" / x["file"]))
    rec_a, _ = load_lidar(folder)
    rec_b, _ = load_lidar(again)
    assert lidar_stats["scans"] == len(rec_a) == len(rec_b)
    for key in ("n_beams", "angles", "quality"):
        assert np.array_equal(getattr(rec_a, key), getattr(rec_b, key)), key
    assert np.array_equal(rec_a.ranges, rec_b.ranges, equal_nan=True)
    np.testing.assert_allclose(rec_b.t - session.origin, rec_a.t - session.t_ref, atol=1e-6)
    # rig.bench --replay <thư mục>: như bản ghi bàn thử (không AI: .venv không có torch)
    out = tmp_path / "out"
    assert bench.main(["--replay", str(folder), "--no-ai", "--name", "t3", "--out", str(out)]) == 0
    data = json.loads((out / "t3.rig.json").read_text(encoding="utf-8"))
    assert data["replay"]["finished"] and data["lidar"]["scans"] == len(rec_a)
    assert {c["port"]: c["frames"] for c in data["cameras"]} == {p: len(rows(folder / f"cam_p{p}" / "frames.csv"))
                                                                 for p in (1, 2)}


def test_lidar_only_session_recording_replays_without_cameras(tmp_path, monkeypatch, capsys):
    rec, _, _ = record_session(tmp_path / "gốc", seconds=0.8, cameras=False)
    meta = json.loads((rec.folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["ports"] == [] and meta["cameras"] == [] and meta["config"] is None and meta["cameras_at_stop"] == []
    assert meta["session_recording"]["sources"]["cameras"]["why_off"].startswith("AI camera đang tắt")
    session = ReplaySession(rec.folder)
    assert session.ports == [] and session.has_lidar
    rig = Rig(MultiCameraManager(session.camera_specs(), ring=3, open_source=session.open_camera), RigConfig(ai=False),
              open_lidar=session.open_lidar, replay=session)
    rig.start(begin_replay=False)
    try:
        session.begin()
        deadline = time.perf_counter() + session.duration_s + 3.0
        while not session.finished and time.perf_counter() < deadline:
            time.sleep(0.02)
        time.sleep(0.15)
        scans = rig.lidar.stats(rig.clock())["scans"]
    finally:
        assert rig.stop() == []
    assert session.finished and scans == meta["lidar"]["scans"] > 4
    # rig.bench: không AI thì phát lại được; có AI thì từ chối rõ ràng (mã 2) trước khi nạp mô hình
    out = tmp_path / "out"
    assert bench.main(["--replay", str(rec.folder), "--no-ai", "--name", "lidar", "--out", str(out)]) == 0
    data = json.loads((out / "lidar.rig.json").read_text(encoding="utf-8"))
    assert data["cameras"] == [] and data["lidar"]["scans"] == meta["lidar"]["scans"] and data["replay"]["finished"]

    def no_model(args):
        raise AssertionError("không được nạp mô hình cho bản ghi không có camera")
    monkeypatch.setattr(bench, "segmenter_factory", no_model)
    capsys.readouterr()
    with pytest.raises(SystemExit) as info:
        bench.main(["--replay", str(rec.folder), "--name", "ai", "--out", str(out)])
    assert info.value.code == 2 and "bản ghi không có camera" in capsys.readouterr().err


# ------------------------------------------------------------------------------------------------ nguồn

def test_lidar_on_another_clock_is_left_out_and_says_why(tmp_path):
    rig = Rig(fake_manager(ports=(1,), period=PERIOD), RigConfig(ai=False))
    host = FakeHost(rig, object(), clock_ok=False)
    recorder = recorder_for(host, tmp_path / "gốc")
    avail = recorder.availability()
    assert avail.cameras and not avail.lidar and avail.camera_ports == [1]
    assert "perf_counter" in avail.reasons["lidar"]
    rig.start()
    try:
        rec = recorder.start()
        assert recorder.lidar_sink() is None and rec.lidar is False and rig.recorder is rec
        time.sleep(0.3)
        recorder.stop()
        assert recorder.wait_finished(10.0)
    finally:
        assert rig.stop() == []
    meta = json.loads((rec.folder / "meta.json").read_text(encoding="utf-8"))
    lidar = meta["session_recording"]["sources"]["lidar"]
    assert lidar["on"] is False and "perf_counter" in lidar["why_off"] and meta["lidar"] is None
    assert meta["lidar_source"] is None and len(rows(rec.folder / "cam_p1" / "frames.csv")) > 3
    # không còn nguồn nào ghi được: từ chối, không tạo thư mục
    alone = SessionSensorRecorder(FakeHost(None, object(), clock_ok=False), RecordOptions(root=tmp_path / "trống"),
                                  free_bytes=lambda path: 100 * GB)
    with pytest.raises(RecordStartError, match="Không có nguồn để ghi") as info:
        alone.start()
    assert "AI camera đang tắt" in str(info.value) and "perf_counter" in str(info.value)
    assert not (tmp_path / "trống").exists() and alone.rec is None
    with pytest.raises(RecordStartError, match="camera: không chọn"):
        recorder.start(cameras=False)                  # người dùng bỏ chọn camera, LiDAR khác đồng hồ


def test_stopping_the_camera_rig_detaches_it_and_the_lidar_keeps_recording(tmp_path):
    rig = Rig(fake_manager(ports=(1, 2), period=PERIOD), RigConfig(ai=False))
    source = FakeLidar(period=0.05)
    host = FakeHost(rig, source)
    recorder = recorder_for(host, tmp_path / "gốc")
    reader = TapReader(source, recorder.lidar_sink)
    rig.start()
    reader.start()
    try:
        time.sleep(0.2)
        rec = recorder.start()
        run_for(recorder, 0.5)
        t = time.perf_counter()
        assert rig.stop() == [] and time.perf_counter() - t < 2.0      # như "Tắt AI camera": Rig không chờ bộ ghi
        host.rig = None
        assert rec.state == "đang ghi" and rig.recorder is None and recorder.active
        messages = recorder.poll()
        assert any(m.startswith("Camera rời bản ghi") and "LiDAR vẫn ghi" in m for m in messages)
        scans_at_detach = rec.lidar_scans
        time.sleep(0.4)
        assert recorder.poll() == [] and recorder.active
        host.lidar = None                                              # "Ngắt" LiDAR: không còn nguồn nào
        messages = recorder.poll()
        assert any("LiDAR rời bản ghi" in m for m in messages) and any("Không còn nguồn" in m for m in messages)
        assert not recorder.active and recorder.wait_finished(10.0)
    finally:
        reader.stop_event.set()
    meta = json.loads((rec.folder / "meta.json").read_text(encoding="utf-8"))
    sr = meta["session_recording"]
    assert meta["status"] == "xong" and sr["stopped_by"] == "no_sources"
    assert [d["source"] for d in sr["detached"]] == ["cameras", "lidar"]
    assert sorted(c["port"] for c in meta["cameras_at_stop"]) == [1, 2] and meta["cameras_at_stop"][0]["frames"] > 5
    assert meta["lidar"]["scans"] > scans_at_detach                   # vòng sau khi camera rời vẫn được ghi
    triggers = [a["trigger"] for a in rows(rec.folder / CLOCK_TABLE)]
    assert "camera_detached" in triggers and "lidar_detached" in triggers and triggers[-1] == "stop"


def test_a_lidar_reconnect_continues_into_the_recording_and_a_late_lidar_does_not(tmp_path):
    rig = Rig(fake_manager(ports=(1,), period=PERIOD), RigConfig(ai=False))
    source = FakeLidar(period=0.05)
    host = FakeHost(rig, source)
    recorder = recorder_for(host, tmp_path / "gốc")
    reader = TapReader(source, recorder.lidar_sink)
    rig.start()
    reader.start()
    try:
        time.sleep(0.2)
        rec = recorder.start()
        run_for(recorder, 0.3)
        host.lidar_key = 2                                             # "Ngắt" rồi "Kết nối" giữa hai lần kiểm
        messages = recorder.poll()
        assert any(m.startswith("LiDAR rời bản ghi: ngăn LiDAR đổi nguồn") for m in messages)
        assert "LiDAR kết nối lại: vòng quét tiếp tục vào bản ghi" in messages and recorder.active
        scans = rec.lidar_scans
        run_for(recorder, 0.3)
        assert rec.lidar_scans > scans                                 # vẫn vào cùng bản ghi
        host.lidar_key, host.clock_ok, host.why = 3, False, "nguồn không dùng đồng hồ perf_counter"
        messages = recorder.poll()
        assert any("LiDAR kết nối lại nhưng nguồn không dùng đồng hồ perf_counter" in m for m in messages)
        assert recorder.poll() == [] and recorder.active               # báo một lần; camera vẫn ghi
        recorder.stop()
        assert recorder.wait_finished(10.0)
    finally:
        reader.stop_event.set()
        assert rig.stop() == []
    sr = json.loads((rec.folder / "meta.json").read_text(encoding="utf-8"))["session_recording"]
    assert [d["source"] for d in sr["detached"]] == ["lidar", "lidar"] and sr["ignored_late"][0]["source"] == "lidar"
    triggers = [a["trigger"] for a in rows(rec.folder / CLOCK_TABLE)]
    assert triggers.count("lidar_detached") == 2 and triggers.count("lidar_attached") == 1
    # LiDAR không có lúc bắt đầu, bật sau: không vào bản ghi này (báo một lần)
    late = FakeHost(Rig(fake_manager(ports=(1,), period=PERIOD), RigConfig(ai=False)), None)
    recorder = recorder_for(late, tmp_path / "muộn")
    late.rig.start()
    try:
        rec = recorder.start()
        assert rec.lidar is False
        late.lidar = object()
        assert recorder.poll() == ["LiDAR bật sau khi bắt đầu ghi: không vào bản ghi này"]
        assert recorder.poll() == [] and recorder.lidar_sink() is None
        recorder.stop()
        assert recorder.wait_finished(10.0)
    finally:
        assert late.rig.stop() == []


def test_host_errors_never_escape_the_hooks(tmp_path):
    host = FakeHost(None, object())
    recorder = recorder_for(host, tmp_path / "gốc")
    rec = recorder.start()

    def broken(*args, **kwargs):
        raise RuntimeError("hỏng giả")
    host.anchor_context = broken                                       # mốc vẫn ghi, ghi chú nói lý do
    recorder.on_state_change("READY", "RUNNING")
    host.lidar_info = broken
    messages = recorder.poll()                                         # không ném: thành một lời báo
    assert len(messages) == 1 and messages[0].startswith("Lỗi bản ghi cảm biến (kiểm định kỳ): RuntimeError: hỏng giả")
    host.window_state = broken
    host.session_meta = broken
    recorder.stop()
    assert recorder.wait_finished(10.0)
    anchors = rows(rec.folder / CLOCK_TABLE)
    change = next(a for a in anchors if a["trigger"] == "state_change")
    assert "không đọc được ngữ cảnh phiên (RuntimeError: hỏng giả)" in change["note"] and change["run"] == "1"
    assert anchors[-1]["trigger"] == "stop" and anchors[-1]["window"] == "unknown"
    meta = json.loads((rec.folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "xong" and meta["session_recording"]["hook_errors"]


def test_disk_free_bytes_measures_the_nearest_existing_folder(tmp_path):
    import shutil

    from autopark.rig.session_recording import disk_free_bytes, drive_name
    free = disk_free_bytes(tmp_path / "chưa" / "có")
    assert free is not None and abs(free - shutil.disk_usage(tmp_path).free) < 512 * 2**20
    if os.name == "nt":
        assert drive_name(tmp_path).startswith("ổ ") and len(drive_name(tmp_path)) == 3


# ------------------------------------------------------------------------------------------------ đĩa, lỗi ghi

def test_disk_guard_refuses_to_start_below_the_minimum_and_stops_below_the_floor(tmp_path):
    free = [4 * GB]
    host = FakeHost(None, object())
    recorder = SessionSensorRecorder(host, RecordOptions(root=tmp_path / "gốc"), free_bytes=lambda path: free[0])
    with pytest.raises(RecordStartError, match=r"còn 4,0 GB < 5 GB tối thiểu"):
        recorder.start()
    assert not (tmp_path / "gốc").exists()
    free[0] = 10 * GB
    rec = recorder.start()
    assert recorder.poll() == [] and recorder.active
    free[0] = int(1.5 * GB)
    messages = recorder.poll()
    assert len(messages) == 1 and "Dừng ghi tự động" in messages[0] and "còn 1,5 GB < 2 GB" in messages[0]
    assert not recorder.active and recorder.wait_finished(10.0)
    meta = json.loads((rec.folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "xong" and meta["session_recording"]["stopped_by"] == "disk_guard"
    assert meta["session_recording"]["free_gb_stop"] == 1.5
    assert [a["trigger"] for a in rows(rec.folder / CLOCK_TABLE)][-2:] == ["disk_guard", "stop"]
    free[0] = None                                                     # không đọc được dung lượng: vẫn ghi, có cảnh báo
    rec2 = recorder.start()
    recorder.stop()
    assert recorder.wait_finished(10.0)
    meta2 = json.loads((rec2.folder / "meta.json").read_text(encoding="utf-8"))
    assert meta2["session_recording"]["warnings"] and "không đọc được dung lượng" in meta2["session_recording"]["warnings"][0]
    assert meta2["session_recording"]["disk"]["free_gb_start"] is None


def test_a_slow_disk_warns_once_when_less_than_ten_minutes_are_left(tmp_path):
    host = FakeHost(None, object())
    recorder = SessionSensorRecorder(host, RecordOptions(root=tmp_path / "gốc"), free_bytes=lambda path: 3 * GB)
    with pytest.raises(RecordStartError):
        recorder.start()                                               # 3 GB < 5 GB
    recorder.options = RecordOptions(root=tmp_path / "gốc", min_free_gb=2.5, stop_free_gb=0.5)
    rec = recorder.start()
    rec.bytes_written = 2 * 2**30                                      # như đã ghi 2 GB trong vài trăm ms: ≈ vài phút còn lại
    time.sleep(0.2)
    first = recorder.poll()
    assert len(first) == 1 and first[0].startswith("Sắp đầy đĩa") and "phút ghi nữa" in first[0]
    assert recorder.poll() == [] and recorder.active                   # cảnh báo một lần
    recorder.stop()
    assert recorder.wait_finished(10.0)
    assert "disk_warning" in [a["trigger"] for a in rows(rec.folder / CLOCK_TABLE)]


def test_write_error_stops_the_recording_and_keeps_the_error(tmp_path, monkeypatch):
    def full(self, path, data):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(RigRecorder, "_write_bytes", full)
    rig = Rig(fake_manager(ports=(1,), period=PERIOD), RigConfig(ai=False))
    recorder = recorder_for(FakeHost(rig, None), tmp_path / "gốc")
    rig.start()
    try:
        rec = recorder.start()
        deadline = time.perf_counter() + 3.0
        while rec.error is None and time.perf_counter() < deadline:
            time.sleep(0.02)
        messages = recorder.poll()
        assert len(messages) == 1 and messages[0].startswith("LỖI GHI: ") and "No space left" in messages[0]
        assert "đã dừng ghi" in messages[0] and not recorder.active and rig.recorder is None
        assert recorder.wait_finished(10.0)
    finally:
        assert rig.stop() == []
    st = recorder.status()
    assert st["state"] == "error" and "No space left" in st["error"]
    meta = json.loads((rec.folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "lỗi" and "No space left" in meta["error"]
    assert meta["session_recording"]["stopped_by"] == "write_error"
    assert recorder.poll()[0].startswith("LỖI GHI: ")


# ------------------------------------------------------------------------------------------------ mốc đồng hồ

def test_anchor_rows_pair_perf_counter_with_session_and_io_time(tmp_path):
    perf = [1000.0]
    offset = 123.456789
    run = {}
    host = FakeHost(None, object())

    def context(t):
        ctx = {"note": "VEHICLE_IO, cổng COM_GIA", "time_scale": 2.0, "t_io": round(t - offset, 6),
               "io_clock": "realtime"}
        if "t0" in run:                                                # SIM ×2: thời gian phiên đứng sau khi xe dừng
            ctx["t_session"] = round(2.0 * (min(t, run.get("t1", t)) - run["t0"]), 4)
        return ctx
    host.context = context
    recorder = SessionSensorRecorder(host, RecordOptions(root=tmp_path / "gốc"), clock=lambda: perf[0],
                                     free_bytes=lambda path: 100 * GB)
    recorder.on_state_change("EDITING", "READY")                       # chưa ghi: không có mốc, không lần chạy
    rec = recorder.start("mốc")
    perf[0] = 1000.5
    host.state, run["t0"] = "RUNNING", 1000.5
    recorder.on_state_change("READY", "RUNNING")
    while perf[0] < 1002.99:
        perf[0] += 0.25
        recorder.poll()
    perf[0] = 1003.0
    host.state = "STOPPING"
    recorder.on_state_change("RUNNING", "STOPPING", "Người dùng dừng")
    perf[0] = 1003.4
    host.state, run["t1"] = "STOPPED", 1003.4
    recorder.on_state_change("STOPPING", "STOPPED", "Người dùng dừng")
    host.window = "minimized"
    perf[0] = 1004.6
    recorder.poll()
    recorder.stop()
    assert recorder.wait_finished(10.0)
    anchors = rows(rec.folder / CLOCK_TABLE)
    assert [a["trigger"] for a in anchors] == ["start", "state_change", "periodic", "periodic", "state_change",
                                               "state_change", "periodic", "window_state", "stop"]
    change = anchors[1]
    assert (change["state"], change["run"], change["t_session"], change["note"]) == \
        ("RUNNING", "1", "0.0", "VEHICLE_IO, cổng COM_GIA · READY→RUNNING")
    assert anchors[5]["note"].endswith("STOPPING→STOPPED: Người dùng dừng") and anchors[7]["window"] == "minimized"
    clock = read_session_clock(rec.folder)
    assert clock.realtime_offset() == pytest.approx(offset, abs=1e-6)
    assert clock.to_io(1001.234) == pytest.approx(1001.234 - offset, abs=1e-6)
    assert clock.to_session(1001.0) == pytest.approx(1.0, abs=1e-3)   # nội suy trong lần chạy
    assert clock.to_session(1003.2) == pytest.approx(5.4, abs=1e-3)   # giữa STOPPING và STOPPED
    assert clock.to_session(1000.2) is None and clock.to_session(1004.0) is None   # ngoài lần chạy
    meta = json.loads((rec.folder / "meta.json").read_text(encoding="utf-8"))
    [entry] = meta["session_recording"]["runs"]
    assert entry["run"] == 1 and entry["t_perf_start"] == 1000.5 and entry["t_perf_end"] == 1003.4
    assert entry["end_state"] == "STOPPED" and entry["t_session_end"] == pytest.approx(5.8) and entry["stop_reason"]


# ------------------------------------------------------------------------------------------------ lô AI, bảng phụ

def test_ai_rows_carry_the_batch_frames_and_the_decision(tmp_path):
    rig = Rig(fake_manager(ports=(1, 2), period=PERIOD), RigConfig(ai=False))
    recorder = recorder_for(FakeHost(rig, None), tmp_path / "gốc", image_format="png")
    rig.start()
    try:
        rec = recorder.start()
        time.sleep(0.4)
        fs = rig.cams.latest_set(None, require_new=False)
        assert fs is not None and sorted(fs.frames) == [1, 2]
        upd = SimpleNamespace(usable=False, reasons=["p1: chưa có ROI"], notes=["lô thiếu p2"], cameras_used=["p1"],
                              occupied_batch=3, occupied_filtered=0, window_fill=0, bev_ms=1.2345)
        for batch_id in (5, 8):
            result = SimpleNamespace(frame_set=fs, batch_id=batch_id, t_done=fs.t_max + 0.01, checkpoint="gia.pt",
                                     carried={2: object()})
            recorder.add_ai_batch(result, upd, {"state": "EDITING", "ai_boxes": 0, "injected": 0, "stale": False})
        recorder.add_ai_batch(None, upd, {})                           # lỗi trong móc: không bao giờ ném ra ngoài
        assert len(recorder.hook_errors) == 1 and "ghi lô AI" in recorder.hook_errors[0]
        time.sleep(0.2)
        recorder.stop()
        assert recorder.wait_finished(10.0)
    finally:
        assert rig.stop() == []
    ai = rows(rec.folder / AI_TABLE)
    assert list(ai[0]) == list(AI_FIELDS) and [r["batch_id"] for r in ai] == ["5", "8"]
    first = ai[0]
    assert (first["usable"], first["reasons"], first["carried"], first["cameras_used"]) == ("0", "p1: chưa có ROI", "2", "p1")
    assert first["bev_ms"] == "1.23" and first["state"] == "EDITING"
    for item in first["frames"].split(";"):                            # nối được với frames.csv bằng chuỗi stamp
        port, stamp = item.split(":")
        assert stamp in {r["t_s"] for r in rows(rec.folder / f"cam_p{port}" / "frames.csv")}
    meta = json.loads((rec.folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["session_recording"]["ai"] == {"rows": 2, "batches_skipped": 2}
    assert meta["tables"][AI_TABLE]["rows"] == 2 and meta["session_recording"]["hook_errors"]


def test_tables_reach_the_disk_while_recording_and_the_sync_copy_is_written_last(tmp_path, monkeypatch):
    seen = {}
    real = recording.write_json_atomic

    def spy(path, value):
        if value.get("status") == "xong":
            seen["sync_copy_before_final_meta"] = (path.parent / SYNC_COPY).is_file()
        real(path, value)
    monkeypatch.setattr(recording, "write_json_atomic", spy)
    host = FakeHost(None, object())
    host.sync.add("SYNC_MARK", time.perf_counter(), trigger="key_f8", state="EDITING", note="SIM")
    host.sync.add("CLOCK", time.perf_counter(), trigger="state_change", state="RUNNING", note="READY→RUNNING")
    recorder = recorder_for(host, tmp_path / "gốc")
    rec = recorder.start()
    deadline = time.perf_counter() + 3.0
    while len(rows(rec.folder / CLOCK_TABLE)) < 1 and time.perf_counter() < deadline:
        time.sleep(0.02)
    assert rows(rec.folder / CLOCK_TABLE)[0]["trigger"] == "start" and recorder.active   # đã ra đĩa lúc còn ghi
    assert not (rec.folder / SYNC_COPY).exists()
    recorder.stop()
    assert recorder.wait_finished(10.0)
    assert seen == {"sync_copy_before_final_meta": True}
    with open(rec.folder / SYNC_COPY, newline="", encoding="utf-8") as handle:
        assert next(csv.reader(handle)) == SYNC_FIELDS
    assert read_sync_marks(rec.folder / SYNC_COPY) == host.sync.rows


def test_out_of_order_lidar_scan_is_dropped_and_counted_not_fatal(tmp_path):
    rec = RigRecorder(tmp_path / "lùi", ports=[], lidar=True, clock=lambda: 1.0, lidar_scans_per_part=2).start()
    angles = (-1.0, 0.0, 1.0)

    def scan(t):
        return LidarScan(SourceStamp("c1", t, True, "lidar"), angles, (1.0, 2.0, 3.0))
    for t in (1.2, 1.3, 1.25, 1.4):                                    # 1.25 lùi so với 1.3: bỏ và đếm
        rec.add_scan(scan(t), t, None)
    st = rec.stop(wait=True, timeout=5.0)
    assert st["state"] == "xong" and st["lidar_out_of_order"] == 1 and st["error"] is None
    meta = json.loads((tmp_path / "lùi" / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "xong" and meta["lidar"]["out_of_order_dropped"] == 1 and meta["lidar"]["scans"] == 3
    assert meta["warnings"] and "sớm hơn" in meta["warnings"][0]
    lidar, _ = load_lidar(tmp_path / "lùi")                            # các phần nối lại vẫn tăng dần
    assert lidar.t.tolist() == [1.2, 1.3, 1.4] and len(meta["lidar"]["parts"]) == 2


def test_lidar_tap_does_not_record_the_end_of_a_replay():
    class Ended:
        t0 = 1.0

        def read(self):
            raise ScanStreamEnded("hết bản ghi")

    events = []
    sink = SimpleNamespace(add_lidar_event=lambda t, message: events.append(message))
    with pytest.raises(ScanStreamEnded):
        LidarTap(Ended(), lambda: sink, RIG_CLOCK, ignore=(ScanStreamEnded,)).read()
    assert events == []
    with pytest.raises(ScanStreamEnded):
        LidarTap(Ended(), lambda: sink, RIG_CLOCK).read()              # mặc định: mọi lỗi đọc được ghi như trước
    assert events == ["ScanStreamEnded: hết bản ghi"]


# ------------------------------------------------------------------------------------------------ tệp trỏ, tùy chọn

def test_export_refs_list_recordings_and_whether_they_cover_the_last_run(tmp_path):
    host = FakeHost(None, object())
    recorder = recorder_for(host, tmp_path / "gốc")
    assert recorder.export_refs() is None
    recorder.on_state_change("READY", "RUNNING")                       # lần chạy trước khi ghi: không có bản ghi nào
    recorder.on_state_change("RUNNING", "COMPLETED")
    assert recorder.export_refs() is None
    first = recorder.start("phủ")
    host.state = "RUNNING"
    recorder.on_state_change("READY", "RUNNING")
    refs = recorder.export_refs()
    assert refs["format"] == "autopark.sensor_recording_refs" and refs["run"]["t_perf_end"] is None
    [live] = refs["recordings"]
    assert live["status"] == "đang ghi" and live["covers_run"] is True and live["meta_sha256"] is None
    time.sleep(0.05)
    host.state = "STOPPED"
    recorder.on_state_change("RUNNING", "STOPPED", "Vật cản mới")
    recorder.stop()
    assert recorder.wait_finished(10.0)
    second = recorder.start("sau")                                     # bắt đầu SAU lần chạy: không phủ
    refs = recorder.export_refs()
    a, b = refs["recordings"]
    assert refs["run"]["end_state"] == "STOPPED" and refs["run"]["t_perf_end"] > refs["run"]["t_perf_start"]
    assert a["folder"] == str(first.folder) and a["status"] == "xong" and a["covers_run"] is True
    assert a["overlap_s"] == pytest.approx(refs["run"]["t_perf_end"] - refs["run"]["t_perf_start"], abs=1e-3)
    import hashlib
    assert a["meta_sha256"] == hashlib.sha256((first.folder / "meta.json").read_bytes()).hexdigest()
    assert b["folder"] == str(second.folder) and b["status"] == "đang ghi" and b["covers_run"] is False
    assert b["overlap_s"] == 0.0 and b["meta_sha256"] is None
    recorder.stop()
    assert recorder.wait_finished(10.0)


def test_record_options_and_folder_names_are_checked(tmp_path):
    a_file = tmp_path / "tệp.txt"
    a_file.write_text("x", encoding="utf-8")
    for bad, needle in ((RecordOptions(image_format="bmp"), "định dạng ảnh"), (RecordOptions(jpeg_quality=0), "1..100"),
                        (RecordOptions(min_free_gb=1.0), "ngưỡng tự dừng"), (RecordOptions(root=a_file), "là một tệp")):
        with pytest.raises(ValueError, match=needle):
            bad.check()
    assert clean_name("  đỗ 1/lần 3 ") == "đỗ_1_lần_3" and clean_name("a" * 60) == "a" * 40 and clean_name("") == ""
    recorder = recorder_for(FakeHost(None, object()), tmp_path / "gốc")
    from datetime import datetime
    when = datetime(2026, 10, 2, 14, 3, 5, 123456)
    assert recorder.folder_for("do1_l3", when).name == "20261002_140305_123_do1_l3"
    assert recorder.folder_for("", when).name == "20261002_140305_123"
    recorder.start()                                                   # xe đang chạy: từ chối (chốt chặn sau nút khóa)
    recorder.stop()
    assert recorder.wait_finished(10.0)
    host = FakeHost(None, object(), state="RUNNING")
    with pytest.raises(RecordStartError, match="Bắt đầu ghi trước Bắt đầu đỗ"):
        recorder_for(host, tmp_path / "gốc").start()
