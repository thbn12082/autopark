"""Bộ ghi camera trên cao (`autopark.video.overhead_record`, thêm 02/10/2026) với NGUỒN GIẢ: không bao giờ mở camera
thật. Kiểm tệp ghi (AVI + frames.csv + events.csv + json), kiểm tham số và ổ đĩa TRƯỚC khi mở camera, Ctrl+C đóng tệp
đúng cách, và tệp ghi được dùng thẳng cho `overhead_ref` (đồng hồ perf_counter). Sửa 02/10/2026 (đợt 2): camera thôi trả
khung tốt thì vẫn dừng đúng hạn / dừng với trạng thái lỗi (không quay tít), `--overwrite` giữ bản cũ thành
`<tên>.bak_<ngày_giờ>.*` (`--force` chỉ còn bỏ qua từ chối ổ đầy), EcoQoS đọc lại lúc ghi JSON. Lớp Win32 của EcoQoS
được thay bằng hàm giả: tiến trình pytest không bị đổi trạng thái."""
import csv
import json
import time

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

import autopark.power_throttling as pt  # noqa: E402
from autopark.evaluation import overhead_ref as R  # noqa: E402
from autopark.evaluation.overhead_synth import camera_stamps  # noqa: E402
from autopark.lidar import recording as lidar_recording  # noqa: E402
from autopark.video import overhead_record as rec  # noqa: E402
from autopark.video.sources import FrameReadError, _frame  # noqa: E402
from tests.overhead_set import floor_fit_path, small_set  # noqa: E402


@pytest.fixture(autouse=True)
def no_git(monkeypatch):
    monkeypatch.setattr(lidar_recording, "git_commit", lambda: "test")
    rec.git_commit.cache_clear()
    yield
    rec.git_commit.cache_clear()


@pytest.fixture
def ecoqos_now(monkeypatch):
    """Trạng thái EcoQoS giả của tiến trình (đổi được giữa chừng); không gọi Win32 thật."""
    state = {"now": "system"}
    monkeypatch.delenv(pt.KEEP_ECOQOS_ENV, raising=False)
    monkeypatch.setattr(pt, "disable_power_throttling", lambda pid=None: state.update(now="off") or True)
    monkeypatch.setattr(pt, "execution_speed_throttling", lambda pid=None: state["now"])
    return state


class FakeCamera:
    """Như UsbCameraSource: read() trả khung có stamp perf_counter; `broken` = các lần đọc ném khung bị cắt; hết khung
    thì trả None, hoặc ném KeyboardInterrupt khi `interrupt` (như Ctrl+C giữa lúc ghi)."""

    buffer_size_applied = True

    def __init__(self, images, stamps, broken=(), interrupt=False, period=0.0):
        self.images, self.stamps, self.broken, self.interrupt, self.period = images, stamps, set(broken), interrupt, period
        self.n, self.closed = 0, False

    def read(self):
        if self.period:
            time.sleep(self.period)
        k = self.n
        self.n += 1
        if k >= len(self.stamps):
            if self.interrupt:
                raise KeyboardInterrupt
            return None
        if k in self.broken:
            raise FrameReadError("cam_tren_cao: truncated frame (120 of 240 rows filled by the decoder)", self.stamps[k])
        return _frame("cam_tren_cao", self.stamps[k], f"gia#{k}", self.images[k % len(self.images)])

    def mode(self):
        h, w = self.images[0].shape[:2]
        return {"width": w, "height": h, "fourcc": "MJPG"}

    def close(self):
        self.closed = True


def images(n=12, size=(320, 240)):
    rng = np.random.default_rng(0)
    return [rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8) for _ in range(n)]


def test_recorder_writes_avi_frames_csv_events_and_meta(tmp_path, ecoqos_now):
    stamps = camera_stamps(12, 5000.0)
    cam = FakeCamera(images(), stamps, broken={5})
    ecoqos_now["now"] = "off"
    meta = rec.record(lambda: cam, tmp_path, "lan1", seconds=60, camera_info={"index": 3, "name": "tren_cao"},
                      ecoqos_policy={"request": "disable", "set_ok": True, "after": "off"})
    assert cam.closed and meta["status"] == "xong" and meta["frames"] == 11
    paths = rec.recording_paths(tmp_path, "lan1")
    with paths["frames"].open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    good = [t for k, t in enumerate(stamps) if k != 5]
    assert [float(r["t_perf"]) for r in rows] == pytest.approx(good) and [int(r["frame"]) for r in rows] == list(range(11))
    assert float(rows[-1]["t_s"]) == pytest.approx(good[-1] - good[0])
    cap = cv2.VideoCapture(str(paths["video"]))
    decoded = 0
    while cap.read()[0]:
        decoded += 1
    cap.release()
    assert decoded == len(rows) == 11
    with paths["events"].open(encoding="utf-8") as f:
        events = list(csv.DictReader(f))
    assert [(e["kind"], e["after_frame"]) for e in events] == [("truncated", "4")]
    saved = json.loads(paths["meta"].read_text(encoding="utf-8"))
    assert saved["format"] == "autopark.overhead_recording/1" and saved["clock"] == "perf_counter"
    assert saved["status"] == "xong" and saved["host"] and isinstance(saved["wall_minus_perf_s"], float)
    assert saved["ecoqos"] == "off" and saved["ecoqos_start"] == "off" and saved["counts"]["truncated"] == 1
    assert saved["ecoqos_policy"] == {"request": "disable", "set_ok": True, "after": "off"}
    assert saved["previous_backup"] == []
    assert saved["camera"]["index"] == 3 and saved["camera"]["mode"]["width"] == 320 and saved["camera"][
        "buffer_size_applied"] is True
    assert set(saved["gap_ms"]) == {"median", "p95", "max"} and saved["fps_real"] > 0 and saved["synthetic"] is False
    with pytest.raises(rec.RecorderError, match="đã có"):
        rec.OverheadRecorder(tmp_path, "lan1")


def test_main_checks_name_and_disk_before_opening_the_camera(tmp_path, monkeypatch, capsys, ecoqos_now):
    opened = []

    def factory(index, w, h, **kw):
        opened.append((index, w, h, kw))
        return FakeCamera(images(size=(w, h)), camera_stamps(8, 7000.0), interrupt=True)

    monkeypatch.setattr(rec, "camera_factory", factory)
    monkeypatch.setattr(rec, "disk_free_gb", lambda path: 100.0)
    base = ["--index", "1", "--size", "320x240", "--seconds", "5", "--out", str(tmp_path)]
    assert rec.main(base + ["--name", "lần 1"]) == 2                           # tên có dấu, khoảng trắng
    assert rec.main(base[:-4] + ["--seconds", "0", "--out", str(tmp_path), "--name", "a"]) == 2
    (tmp_path / "da_co.avi").write_bytes(b"x")
    assert rec.main(base + ["--name", "da_co"]) == 2                            # không ghi đè
    assert rec.main(base + ["--name", "da_co", "--force"]) == 2                 # --force không còn cho ghi đè
    monkeypatch.setattr(rec, "disk_free_gb", lambda path: 1.0)
    assert rec.main(base + ["--name", "lan2"]) == 2                             # ổ còn 1 GB < 5 GB
    assert rec.main(base + ["--name", "lan2", "--overwrite"]) == 2              # --overwrite không bỏ qua ổ đầy
    err = capsys.readouterr().err
    assert err.count("LỖI:") == 6 and err.count("ổ đĩa chỉ còn 1.0 GB") == 2 and err.count("đã có") == 2
    assert "--overwrite" in err and (tmp_path / "da_co.avi").read_bytes() == b"x"
    assert opened == []                                                         # chưa từng mở camera
    monkeypatch.setattr(rec, "disk_free_gb", lambda path: 100.0)
    assert rec.main(base + ["--name", "lan3", "--exposure", "-6"]) == 0          # Ctrl+C sau 8 khung: vẫn đóng tệp
    assert opened == [(1, 320, 240, {"exposure": -6.0, "focus": None, "source_id": "cam_tren_cao"})]
    meta = json.loads((tmp_path / "lan3.json").read_text(encoding="utf-8"))
    assert meta["status"] == "dừng (Ctrl+C)" and meta["frames"] == 8
    # khóa ecoqos: trạng thái đọc lúc ghi (chuỗi, như mọi nơi ghi khác); chính sách lúc khởi động để riêng
    assert meta["ecoqos"] == "off" and meta["ecoqos_policy"] == {"request": "disable", "set_ok": True, "after": "off"}
    video = R.OverheadVideo(tmp_path / "lan3.avi")
    assert video.clock == "perf_counter" and len(video) == 8 and len(list(video)) == 8
    monkeypatch.setattr(rec, "disk_free_gb", lambda path: 1.0)
    assert rec.main(base + ["--name", "lan4", "--force"]) == 0                  # --force: chỉ bỏ qua ổ < 5 GB
    assert len(opened) == 2 and json.loads((tmp_path / "lan4.json").read_text(encoding="utf-8"))["frames"] == 8


def test_recorded_files_feed_track(tmp_path):
    info = small_set()
    stamps = camera_stamps(5, 9000.0)
    rng = np.random.default_rng(7)
    frames = [info["renderer"].frame(info["truth_poses"][-1], info["plate"], rng=rng) for _ in stamps]
    rec.record(lambda: FakeCamera(frames, stamps), tmp_path, "xe_dung", seconds=60)
    video = R.OverheadVideo(tmp_path / "xe_dung.avi")
    assert video.clock == "perf_counter" and len(video) == 5 and video.meta["frames"] == 5
    assert [f.t for f in video] == pytest.approx(stamps)
    fit = R.load_floor_fit(floor_fit_path())
    result = R.extract_track(video, fit, R.load_vehicle_markers(info["markers"]), clock=video.clock)
    assert len(result.frames) == 5 and all(f.valid for f in result.frames)


def test_recording_thread_previews_and_records_on_demand(tmp_path):
    stamps = camera_stamps(400, 100.0)
    cam = FakeCamera(images(4), stamps, broken={3}, period=0.005)
    thread = rec.RecordingThread(lambda: cam)
    thread.start()
    assert thread.opened.wait(2.0) and thread.error is None
    deadline = time.monotonic() + 3.0
    while thread.latest() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert thread.latest() is not None and thread.recording is None
    recorder = rec.OverheadRecorder(tmp_path, "xem_truoc")
    thread.start_recording(recorder)
    while recorder.frames < 10 and time.monotonic() < deadline:
        time.sleep(0.01)
    meta = thread.stop_recording()
    assert meta["status"] == "xong" and meta["frames"] >= 10 and thread.recording is None
    thread.stop()
    assert not thread.is_alive() and cam.closed and thread.counters["truncated"] == 1


# ------------------------------------------------------------------ sửa 02/10/2026 (đợt 2): EcoQoS, ghi đè, camera chết
def test_recording_json_reads_ecoqos_state_at_write_time(tmp_path, ecoqos_now):
    """Khóa `ecoqos` của tệp ghi là trạng thái ĐỌC LẠI lúc ghi JSON (như rig/recording.py), không phải bản chép lúc mở
    ứng dụng; chính sách lúc khởi động nằm riêng ở `ecoqos_policy`."""
    policy = pt.apply_ecoqos_policy("video.overhead_record")             # như main(): đầu tiến trình
    startup = {"request": policy.request, "set_ok": policy.set_ok, "after": policy.state}
    assert startup == {"request": "disable", "set_ok": True, "after": "off"}
    ecoqos_now["now"] = "on"                                             # sau đó: vd. bật Efficiency mode
    recorder = rec.OverheadRecorder(tmp_path, "lan_sau")
    recorder.start(320, 240, {"name": "tren_cao"}, ecoqos_policy=startup)
    first = json.loads(recorder.paths["meta"].read_text(encoding="utf-8"))
    assert first["ecoqos"] == "on" and first["ecoqos_start"] == "on" and first["ecoqos_policy"] == startup
    recorder.add(images(1)[0], 10.0)
    ecoqos_now["now"] = "system"                                         # đổi giữa lúc ghi: JSON cuối đọc lại
    meta = recorder.stop()
    saved = json.loads(recorder.paths["meta"].read_text(encoding="utf-8"))
    assert saved == meta and saved["ecoqos"] == "system" and saved["ecoqos_start"] == "on"
    assert saved["ecoqos_policy"]["after"] == "off"
    plain = rec.OverheadRecorder(tmp_path, "khong_chinh_sach")          # bộ thử tổng hợp: không có chính sách
    plain.start(320, 240)
    assert plain.stop()["ecoqos_policy"] is None


def _recording_set(folder, stem) -> dict:
    return {suffix: folder / f"{stem}{suffix}" for suffix in (".avi", ".frames.csv", ".events.csv", ".json")}


def test_overwrite_moves_the_old_recording_aside_as_a_readable_backup(tmp_path):
    """Ghi đè một tên lần ghi chỉ khi có cờ, và bản cũ luôn được giữ: bốn tệp đổi tên thành `<tên>.bak_<ngày_giờ>.*`
    (cùng gốc tên nên vẫn là một lần ghi đọc lại được); `force` (tên cũ) cũng sao lưu như vậy."""
    first = rec.record(lambda: FakeCamera(images(4), camera_stamps(20, 100.0)), tmp_path, "san_trong", seconds=60)
    assert first["frames"] == 20
    old = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(rec.RecorderError, match="--overwrite"):
        rec.OverheadRecorder(tmp_path, "san_trong")
    with pytest.raises(rec.RecorderError, match="đã có"):
        rec.record(lambda: FakeCamera(images(2), camera_stamps(3, 200.0)), tmp_path, "san_trong", seconds=60)
    second = rec.record(lambda: FakeCamera(images(2), camera_stamps(3, 200.0)), tmp_path, "san_trong", seconds=60,
                        overwrite=True)
    assert second["frames"] == 3 and len(second["previous_backup"]) == 4
    stems = {name.split(".bak_")[1].split(".")[0] for name in second["previous_backup"]}
    assert len(stems) == 1                                               # cùng một gốc tên sao lưu
    backup = _recording_set(tmp_path, f"san_trong.bak_{stems.pop()}")
    for suffix, path in backup.items():
        assert path.read_bytes() == old[f"san_trong{suffix}"], suffix    # đổi tên nguyên vẹn
    video = R.OverheadVideo(backup[".avi"])
    assert video.clock == "perf_counter" and len(video) == 20 and video.meta["frames"] == 20
    assert R.OverheadVideo(tmp_path / "san_trong.avi").meta["frames"] == 3
    # tên cũ của cờ (force=True, overhead_synth và mã gọi cũ còn dùng) cũng sao lưu, không bao giờ xóa video gốc
    rec.record(lambda: FakeCamera(images(2), camera_stamps(2, 300.0)), tmp_path, "san_trong", seconds=60, force=True)
    assert len(list(tmp_path.glob("san_trong.bak_*.avi"))) == 2
    # đổi codec khi ghi đè: video .avi cũ cũng được sao lưu (không còn .avi cũ nằm cạnh .frames.csv mới)
    third = rec.record(lambda: FakeCamera(images(2), camera_stamps(2, 400.0)), tmp_path, "san_trong", seconds=60,
                       codec="mp4v", overwrite=True)
    assert not (tmp_path / "san_trong.avi").exists() and (tmp_path / "san_trong.mp4").exists()
    assert any(name.endswith(".avi") for name in third["previous_backup"])
    assert len(list(tmp_path.glob("san_trong.bak_*.avi"))) == 3


def test_backup_rolls_back_when_an_old_file_cannot_be_renamed(tmp_path, monkeypatch):
    """Một tệp cũ không đổi tên được (đang mở ở trình xem video…): trả các tệp đã đổi về tên cũ, không ghi gì mới."""
    rec.record(lambda: FakeCamera(images(2), camera_stamps(3, 100.0)), tmp_path, "khoa", seconds=60)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    real_replace, calls = rec.os.replace, []

    def flaky(src, dst):
        calls.append(src)
        if len(calls) == 3:                                              # tệp thứ ba (.events.csv) bị khóa
            raise PermissionError(13, "tệp đang mở", str(src))
        return real_replace(src, dst)

    recorder = rec.OverheadRecorder(tmp_path, "khoa", overwrite=True)
    with monkeypatch.context() as m:
        m.setattr(rec.os, "replace", flaky)
        with pytest.raises(rec.RecorderError, match="để nguyên"):
            recorder.start(320, 240)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before and not recorder.started


def test_synthetic_recording_replaces_only_an_old_synthetic_one(tmp_path):
    """Bộ thử tổng hợp ghi lại vào cùng thư mục: bản cũ TỔNG HỢP bị thay (dựng lại được), nhưng một lần ghi thật cùng
    tên thì vẫn được sao lưu."""
    for k in range(2):
        r = rec.OverheadRecorder(tmp_path, "chay_01", synthetic=True, force=True)
        r.start(320, 240)
        r.add(images(1)[0], 10.0 + k)
        assert r.stop()["previous_backup"] == []
    assert not list(tmp_path.glob("*.bak_*"))
    rec.record(lambda: FakeCamera(images(2), camera_stamps(3, 500.0)), tmp_path, "chay_02", seconds=60)
    r = rec.OverheadRecorder(tmp_path, "chay_02", synthetic=True, force=True)
    r.start(320, 240)
    r.add(images(1)[0], 10.0)
    assert len(r.stop()["previous_backup"]) == 4 and len(list(tmp_path.glob("chay_02.bak_*"))) == 4


def test_main_overwrite_keeps_a_backup_of_the_old_recording(tmp_path, monkeypatch, capsys, ecoqos_now):
    monkeypatch.setattr(rec, "camera_factory",
                        lambda index, w, h, **kw: FakeCamera(images(size=(w, h)), camera_stamps(5, 800.0)))
    monkeypatch.setattr(rec, "disk_free_gb", lambda path: 100.0)
    base = ["--index", "1", "--size", "320x240", "--seconds", "60", "--out", str(tmp_path), "--name", "do1_l01"]
    assert rec.main(base) == 0
    assert rec.main(base) == 2 and "--overwrite" in capsys.readouterr().err
    assert rec.main(base + ["--overwrite"]) == 0
    out = capsys.readouterr()
    assert "--overwrite đổi tên" in out.err and "bản cũ cùng tên đã đổi tên" in out.out
    assert len(list(tmp_path.glob("do1_l01.bak_*.avi"))) == 1 and (tmp_path / "do1_l01.avi").exists()


class _Stuck(BaseException):
    """Lối thoát của camera giả cho mã còn lỗi (vòng đọc không bao giờ dừng): test hỏng thay vì treo."""


class DyingCamera:
    """`good` khung tốt rồi mọi lần đọc ném FrameReadError như UsbCameraSource khi rút cáp (read() hỏng trả về ngay).
    Stamp tổng hợp: khung tốt t0 + 0,033·n, lần đọc hỏng tăng `step` mỗi lần; `step=None`: nguồn không ghi stamp cho
    lần đọc hỏng, khi đó stamp khung tốt là perf_counter thật (như UsbCameraSource)."""

    buffer_size_applied = True

    def __init__(self, good=3, t0=100.0, step=0.05, give_up=20000):
        self.good, self.t0, self.step, self.give_up = good, t0, step, give_up
        self.n, self.closed = 0, False
        self.image = images(1)[0]

    def read(self):
        self.n += 1
        if self.n > self.give_up:
            raise _Stuck(f"{self.n} lần đọc")
        if self.n <= self.good:
            time.sleep(0.002)
            t = time.perf_counter() if self.step is None else self.t0 + 0.033 * self.n
            return _frame("cam_tren_cao", t, f"gia#{self.n}", self.image)
        t = None if self.step is None else self.t0 + 0.033 * self.good + self.step * (self.n - self.good)
        raise FrameReadError(f"cam_tren_cao: read failed ({self.n - self.good} failures so far)", t)

    def mode(self):
        return {"width": 320, "height": 240}

    def close(self):
        self.closed = True


def test_record_stops_on_time_when_only_broken_frames_arrive(tmp_path):
    """Hết `--seconds` trong lúc camera chỉ trả khung hỏng: dừng đúng hạn theo stamp của lần đọc hỏng (trước đây hạn
    chỉ được xét sau một khung tốt nên lệnh không bao giờ dừng)."""
    cam = DyingCamera(good=3, step=0.05, give_up=2000)
    t = time.monotonic()
    meta = rec.record(lambda: cam, tmp_path, "het_gio", seconds=0.3)
    assert time.monotonic() - t < 2.0 and cam.closed
    assert meta["status"] == "xong" and meta["frames"] == 3 and cam.n < 20
    with open(tmp_path / "het_gio.events.csv", encoding="utf-8") as f:
        assert {e["kind"] for e in csv.DictReader(f)} == {"read_failed"}


def test_record_gives_up_when_the_camera_stops_delivering(tmp_path, monkeypatch, capsys, ecoqos_now):
    """Camera thôi trả khung tốt mà chưa hết giờ: quá STALL_TIMEOUT_S thì đóng tệp với trạng thái "lỗi", ném
    RecorderError (mã thoát 1); trong lúc chờ, sau vài lần hỏng liên tiếp thì nghỉ ngắn (không quay tít một lõi, không
    làm đầy events.csv)."""
    monkeypatch.setattr(rec, "STALL_TIMEOUT_S", 0.3, raising=False)   # mã cũ: hỏng vì hành vi
    cam = DyingCamera(good=3, step=0.001)                               # stamp lần hỏng không tới hạn 60 s
    t = time.monotonic()
    with pytest.raises(rec.RecorderError, match="không trả khung tốt nào"):
        rec.record(lambda: cam, tmp_path, "rut_cap", seconds=60)
    assert time.monotonic() - t < 3.0 and cam.closed
    saved = json.loads((tmp_path / "rut_cap.json").read_text(encoding="utf-8"))
    assert saved["status"] == "lỗi" and saved["frames"] == 3 and saved["counts"]["read_failed"] == cam.n - 3
    assert cam.n < 500                                                   # trước đây hàng trăm nghìn lần đọc mỗi giây
    with open(tmp_path / "rut_cap.events.csv", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == cam.n - 3
    assert R.OverheadVideo(tmp_path / "rut_cap.avi").meta["frames"] == 3   # 3 khung đã ghi vẫn đọc lại được
    # nguồn không ghi stamp cho lần đọc hỏng: vẫn dừng theo giờ thật
    monkeypatch.setattr(rec, "camera_factory", lambda index, w, h, **kw: DyingCamera(good=2, step=None))
    monkeypatch.setattr(rec, "disk_free_gb", lambda path: 100.0)
    argv = ["--index", "0", "--size", "320x240", "--seconds", "60", "--out", str(tmp_path), "--name", "rut_cap_2"]
    assert rec.main(argv) == 1
    assert "LỖI: camera không trả khung tốt nào" in capsys.readouterr().err
    assert json.loads((tmp_path / "rut_cap_2.json").read_text(encoding="utf-8"))["status"] == "lỗi"


def test_recording_thread_stops_recording_when_the_camera_stalls(tmp_path, monkeypatch):
    """Giao diện (RecordingThread): camera thôi trả khung tốt giữa lúc ghi → dừng ghi với trạng thái "lỗi" và báo
    `record_error`; luồng xem trước vẫn chạy nhưng nghỉ ngắn giữa các lần đọc hỏng."""
    monkeypatch.setattr(rec, "STALL_TIMEOUT_S", 0.3, raising=False)   # mã cũ: hỏng vì hành vi
    cam = DyingCamera(good=60, give_up=10 ** 9)
    thread = rec.RecordingThread(lambda: cam)
    thread.start()
    try:
        assert thread.opened.wait(2.0) and thread.error is None
        deadline = time.monotonic() + 3.0
        while thread.latest() is None and time.monotonic() < deadline:
            time.sleep(0.005)
        recorder = rec.OverheadRecorder(tmp_path, "ui_rut_cap")
        thread.start_recording(recorder)
        deadline = time.monotonic() + 5.0
        while thread.record_error is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert thread.record_error and "không trả khung tốt nào" in thread.record_error
        assert thread.recording is None and thread.is_alive()
        saved = json.loads(recorder.paths["meta"].read_text(encoding="utf-8"))
        assert saved["status"] == "lỗi"
        n0 = cam.n
        time.sleep(0.3)
        assert cam.n - n0 < 200                                          # nghỉ 5 ms giữa các lần đọc hỏng liên tiếp
    finally:
        thread.stop()
    assert not thread.is_alive() and cam.closed
