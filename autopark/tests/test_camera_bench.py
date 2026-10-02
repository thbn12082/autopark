"""camera_bench và UsbCameraSource không cần phần cứng: đếm khung mới/khung cũ/đọc hỏng, csv mode, json PnP, mở kèm tham số."""
import json

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from autopark.video import camera_bench as cb  # noqa: E402
from autopark.video.sources import FrameReadError, UsbCameraSource  # noqa: E402


class ScriptedCapture:
    """read() trả về theo kịch bản: 'new' = khung mới, 'dup' = khung cũ trả lại, 'fail' = đọc hỏng; mỗi lần đọc tốn `dt` giây."""

    def __init__(self, script, dt=0.01, shape=(4, 6, 3), default="new"):
        self.script, self.dt, self.shape, self.i, self.value = list(script), dt, shape, 0, 0
        self.default = default                                       # loại khung sau khi hết kịch bản
        self.now = 0.0
        self.props = {cv2.CAP_PROP_FRAME_WIDTH: shape[1], cv2.CAP_PROP_FRAME_HEIGHT: shape[0], cv2.CAP_PROP_FPS: 30.0,
                      cv2.CAP_PROP_EXPOSURE: -6.0}
        self.released = False

    def clock(self):
        return self.now

    def isOpened(self):
        return True

    def get(self, prop):
        return self.props.get(prop, 0.0)

    def set(self, prop, value):
        self.props[prop] = value
        return True

    def read(self):
        self.now += self.dt
        if self.i >= len(self.script):
            kind = self.default
        else:
            kind = self.script[self.i]
            self.i += 1
        if kind == "fail":
            return False, None
        if kind == "new":
            self.value += 1
        return True, np.full(self.shape, self.value % 256, np.uint8)

    def release(self):
        self.released = True


def test_measure_stream_counts_new_duplicate_and_failed_reads():
    cap = ScriptedCapture(["new"] * 5 + ["new", "dup", "dup", "fail", "new", "new", "dup", "new"] * 100, dt=0.01)
    stats = cb.measure_stream(cap, seconds=1.0, index=3, clock=cap.clock, warmup_frames=5)
    assert stats.index == 3 and stats.width == 6 and stats.height == 4
    assert stats.reads == stats.new_frames + stats.duplicate_reads + stats.read_failures
    assert stats.duplicate_reads > 0 and stats.read_failures > 0
    # 4 khung mới trên mỗi 8 lần đọc, mỗi lần đọc 10 ms → 50 khung mới/giây, khoảng cách trung bình 20 ms
    assert stats.fps_real == pytest.approx(50.0, rel=0.05)
    assert stats.gap_ms_mean == pytest.approx(20.0, rel=0.05)
    assert stats.gap_ms_max >= stats.gap_ms_p95 >= stats.gap_ms_median > 0
    assert len(stats.gaps_ms) == stats.new_frames and stats.gaps_under_40ms == sum(1 for g in stats.gaps_ms if g < 40.0)
    assert stats.read_ms_median == pytest.approx(10.0, rel=0.01)
    assert stats.mean_intensity is not None


class RaisingCapture(ScriptedCapture):
    def read(self):
        raise cv2.error("giả lập driver ném lỗi")


def test_measure_many_keeps_failed_stream_visible(monkeypatch):
    def fake_open(index, width, height, fourcc=None, fps=None):
        return RaisingCapture([]) if index == 2 else ScriptedCapture(["new"] * 5 + ["new", "dup"] * 100, dt=0.01)

    monkeypatch.setattr(cb, "open_capture", fake_open)
    result = cb.measure_many([0, 1, 2], 640, 480, seconds=0.2)
    assert [s["index"] for s in result["streams"]] == [0, 1, 2]
    assert result["failed_indices"] == [2] and result["streams"][2]["notes"] and result["streams"][2]["fps_real"] == 0.0
    assert result["total_fps_real"] == pytest.approx(result["streams"][0]["fps_real"] + result["streams"][1]["fps_real"], rel=0.01)


def test_record_refuses_when_camera_returns_no_new_frames(tmp_path, monkeypatch):
    # measure_stream dùng đồng hồ thật, capture giả không tốn thời gian thật → phải trả khung cũ mãi mãi
    monkeypatch.setattr(cb, "open_capture", lambda *a, **k: ScriptedCapture(["new"], dt=0.001, default="dup"))
    with pytest.raises(RuntimeError, match="không có khung mới"):
        cb.record(0, 640, 480, seconds=0.3, out_dir=tmp_path, name="treo")
    assert not list(tmp_path.glob("*.avi"))                             # không để lại file hỏng


def test_record_writes_video_frame_times_and_json(tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "open_capture", lambda *a, **k: ScriptedCapture(["new"] * 5 + ["new", "new", "dup"] * 100000, dt=0.002, shape=(48, 64, 3)))
    info = cb.record(0, 64, 48, seconds=0.2, out_dir=tmp_path, name="clip", snapshot_every=0.05)
    assert info["frames_written"] > 0 and info["duplicate_reads"] > 0 and info["read_failures"] == 0
    assert (tmp_path / "clip.avi").exists() and (tmp_path / "clip.json").exists()
    rows = (tmp_path / "clip.frames.csv").read_text(encoding="utf-8").splitlines()
    assert rows[0] == "frame_index,t_s" and len(rows) == 1 + info["frames_written"]
    assert info["probe_new_frames"] > 0 and len(info["snapshots"]) >= 2


def test_measure_stream_with_only_duplicates_reports_zero_fps():
    cap = ScriptedCapture(["new"] + ["dup"] * 1000, dt=0.005)
    stats = cb.measure_stream(cap, seconds=0.5, clock=cap.clock, warmup_frames=1)
    assert stats.new_frames == 0 and stats.fps_real == 0.0 and stats.duplicate_reads == stats.reads


def test_unique_modes_and_csv(tmp_path):
    rows = [{"index": 0, "fourcc": "MJPG", "width": 1280, "height": 720, "fps_min": 30.0, "fps_max": 30.0},
            {"index": 1, "fourcc": "MJPG", "width": 1280, "height": 720, "fps_min": 30.0, "fps_max": 30.0},
            {"index": 2, "fourcc": "YUY2", "width": 1920, "height": 1080, "fps_min": 5.0, "fps_max": 5.0},
            {"index": 3, "fourcc": "MJPG", "width": 1920, "height": 1080, "fps_min": 30.0, "fps_max": 30.0}]
    unique = cb.unique_modes(rows)
    assert [(r["fourcc"], r["width"]) for r in unique] == [("MJPG", 1920), ("MJPG", 1280), ("YUY2", 1920)]
    path = tmp_path / "camera_modes.csv"
    cb.write_modes_csv(path, {0: rows, 1: rows[:1]}, ["HD Camera", "HD Camera"])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "camera_index,device_name,fourcc,width,height,fps_min,fps_max"
    assert len(lines) == 1 + 3 + 1 and lines[1] == "0,HD Camera,MJPG,1920,1080,30,30"


def test_parse_pnp_json_handles_single_object_and_ports():
    single = json.dumps({"instance_id": "USB\\VID_1BCF&PID_0B09&MI_00\\7&1", "friendly_name": "HD Camera", "status": "OK",
                         "parent": "USB\\VID_1BCF&PID_0B09\\6&C&0&3", "parent_location": "Port_#0003.Hub_#0004",
                         "hub": "USB\\VID_05E3&PID_0610\\5&2&0&5", "location_paths": "PCIROOT(0)#USB(5)#USB(3)"})
    rows = cb.parse_pnp_json(single)
    assert len(rows) == 1 and rows[0]["hub_port"] == 3 and rows[0]["hub"].startswith("USB\\VID_05E3")
    many = json.dumps([{"instance_id": "b", "friendly_name": "x", "parent_location": "Port_#0004.Hub_#0004", "hub": "h"},
                       {"instance_id": "a", "friendly_name": "y", "parent_location": "", "hub": "h"}])
    rows = cb.parse_pnp_json(many)
    assert [r["hub_port"] for r in rows] == [4, None]              # cổng không rõ xếp cuối
    assert cb.parse_pnp_json("  ") == [] and cb.parse_pnp_hubs("  ") == [] and cb.parse_pnp_hubs(many) == []
    # dạng mới {cameras, hubs}: camera không composite lấy cổng của chính nó, không lấy của cha
    new = json.dumps({"cameras": [{"instance_id": "USB\\VID_1&PID_2\\5&1&0&2", "friendly_name": "Plain", "location_info": "Port_#0002.Hub_#0004",
                                   "parent_location": "Port_#0005.Hub_#0001", "hub": "h"}],
                      "hubs": {"instance_id": "USB\\VID_05E3&PID_0626\\5&1&0&24", "friendly_name": "Generic SuperSpeed USB Hub",
                               "bus_reported_desc": "USB3.1 Hub", "location_info": "Port_#0024.Hub_#0001"}})
    assert cb.parse_pnp_json(new)[0]["hub_port"] == 2
    hubs = cb.parse_pnp_hubs(new)
    assert len(hubs) == 1 and hubs[0]["root_port"] == 24 and hubs[0]["bus_reported_desc"] == "USB3.1 Hub"


def test_report_cli_handles_empty_and_missing_directory(tmp_path):
    assert cb.main(["report", str(tmp_path)]) == 0
    assert (tmp_path / "report.md").read_text(encoding="utf-8").startswith("| Phiên |")
    with pytest.raises(SystemExit):
        cb.main(["report", str(tmp_path / "khong_co")])


def test_device_path_maps_to_pnp_instance_and_port():
    path = r"\\?\usb#vid_1bcf&pid_0b09&mi_00#7&56b40fb&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
    assert cb.instance_key_from_path(path) == r"USB\VID_1BCF&PID_0B09&MI_00\7&56B40FB&0&0000"
    assert cb.instance_key_from_path("") == ""
    pnp = [{"instance_id": r"USB\VID_1BCF&PID_0B09&MI_00\7&56B40FB&0&0000", "hub": "h", "hub_port": 1},
           {"instance_id": r"USB\VID_1BCF&PID_0B09&MI_00\7&1824F1A0&0&0000", "hub": "h", "hub_port": 2}]
    dshow = [{"index": 0, "name": "HD Camera", "device_path": path, "instance_key": cb.instance_key_from_path(path)},
             {"index": 1, "name": "Virtual", "device_path": "", "instance_key": ""}]
    joined = cb.join_index_to_port(dshow, pnp)
    assert joined[0]["hub_port"] == 1 and joined[0]["instance_id"] == pnp[0]["instance_id"]
    assert joined[1]["hub_port"] is None and joined[1]["instance_id"] is None


def test_report_markdown_lists_every_stream():
    measurement = {"created_utc": "t", "name": "p01", "requested": {"fourcc": "MJPG", "width": 1280, "height": 720, "fps": 30.0, "exposure": None},
                   "process_cpu_cores": 0.6,
                   "streams": [{"index": 0, "width": 1280, "height": 720, "fps_real": 23.9, "duplicate_reads": 0, "read_failures": 0,
                                "gap_ms_median": 47.0, "gap_ms_p95": 49.0, "gap_ms_max": 51.0, "mean_intensity": 90.0},
                               {"index": 2, "width": 1280, "height": 720, "fps_real": 20.5, "duplicate_reads": 34, "read_failures": 0,
                                "gap_ms_median": 48.0, "gap_ms_p95": 96.0, "gap_ms_max": 128.0, "mean_intensity": None}]}
    text = cb.report_markdown([measurement])
    assert text.count("| p01 |") == 2 and "| 34 |" in text and "| — |" in text


def test_usb_source_opens_with_params_and_reports_duplicates(monkeypatch):
    calls = {}

    def fake_capture(index, backend, params=None):
        calls["index"], calls["backend"], calls["params"] = index, backend, params
        return ScriptedCapture(["new", "new", "dup", "fail", "new"], dt=0.02)

    monkeypatch.setattr(cv2, "VideoCapture", fake_capture)
    source = UsbCameraSource(1, width=1280, height=720, fps=30, fourcc="MJPG", exposure=-6, clock=lambda: 7.0)
    assert calls["index"] == 1 and calls["params"] is not None
    assert all(type(v) is int for v in calls["params"]), calls["params"]   # OpenCV từ chối float trong params
    keys = calls["params"][0::2]
    assert cv2.CAP_PROP_FOURCC in keys and cv2.CAP_PROP_FRAME_WIDTH in keys and cv2.CAP_PROP_FRAME_HEIGHT in keys
    assert source.exposure_applied and source.mode()["fourcc"] == "MJPG" and source.mode()["width"] == 6
    assert source.mode_mismatch == {"width": (1280, 6), "height": (720, 4)}
    first, second = source.read(), source.read()
    assert first.meta.stamp.t == 7.0 and second.meta.stamp.source_id == "camera_usb"
    with pytest.raises(FrameReadError):                                # khung cũ trả lại
        source.read()
    with pytest.raises(FrameReadError):                                # đọc hỏng
        source.read()
    assert source.read() is not None and source.failures == 2
    source.close()


def test_open_capture_builds_integer_params(monkeypatch):
    seen = {}

    def fake_capture(index, backend, params=None):
        seen["params"] = params
        return ScriptedCapture(["new"])

    monkeypatch.setattr(cv2, "VideoCapture", fake_capture)
    cb.open_capture(0, 1280, 720, "MJPG", 29.97)
    assert seen["params"] is not None and all(type(v) is int for v in seen["params"])
    assert seen["params"][seen["params"].index(cv2.CAP_PROP_FPS) + 1] == 30


def test_usb_source_without_mode_uses_no_params(monkeypatch):
    seen = {}

    def fake_capture(index, backend, *rest):
        seen["rest"] = rest
        return ScriptedCapture(["new"])

    monkeypatch.setattr(cv2, "VideoCapture", fake_capture)
    source = UsbCameraSource(0, width=None, height=None, fps=None, fourcc=None)
    assert seen["rest"] == () and source.mode()["fourcc"] is None


HUB = r"USB\VID_05E3&PID_0610\5&27BF20E7&0&8"           # hub của bốn camera xe (Genesys 05E3:0610)
ROOT = r"USB\ROOT_HUB30\4&1A2B3C4D&0&0"                  # cổng gốc của máy
ROOT_B = r"USB\ROOT_HUB30\4&5E6F7A8B&0&0"                # root hub thứ hai


def pnp_cam(key, hub_id, port, mi="00"):
    return {"instance_id": rf"USB\VID_1BCF&PID_0B09&MI_{mi}\7&{key}&0&0000", "hub": hub_id, "hub_port": port}


def plug(monkeypatch, cameras):
    """PnP và DirectShow giả (index DirectShow = thứ tự trong `cameras`): không gọi PowerShell hay pygrabber."""
    monkeypatch.setattr(cb, "pnp_cameras", lambda: list(cameras))
    monkeypatch.setattr(cb, "dshow_device_paths", lambda: [
        {"index": i, "name": "HD Camera", "device_path": "", "instance_key": c["instance_id"].upper()}
        for i, c in enumerate(cameras)])


def resolved(ports):
    from autopark.video import multicam

    return [(s.port, s.index) for s in multicam.resolve_ports(ports)]


def refusal(ports) -> str:
    from autopark.video import multicam

    with pytest.raises(ValueError) as exc:
        multicam.resolve_ports(ports)
    return str(exc.value)


def test_resolve_ports_refuses_a_port_number_shared_by_two_cameras(monkeypatch):
    """T11 (02/10/2026): camera trên cao cắm thẳng vào cổng 2 của máy và camera xe ở cổng 2 của hub có cùng SỐ cổng
    (`_port_of` chỉ đọc số). Hỏi MỘT cổng (calib_app --port 2, roi_app) thì không có gì để biết hub camera xe: từ chối thay
    vì chọn một camera theo thứ tự index DirectShow (calib_app có thể ghi đè cam_p2.json bằng camera trên cao). Lời báo
    nêu lý do và cách gỡ cho MỌI công cụ, không chỉ "--index" của calib_app (review 02/10/2026). Bốn camera trên một hub
    (bàn thử hiện nay) cho đúng kết quả cũ."""
    plug(monkeypatch, [pnp_cam("C3", HUB, 3), pnp_cam("AA", ROOT, 2), pnp_cam("C1", HUB, 1), pnp_cam("C4", HUB, 4),
                       pnp_cam("C2", HUB, 2)])
    assert resolved([1]) == [(1, 2)] and resolved([4, 1, 3]) == [(4, 3), (1, 2), (3, 0)]
    text = refusal([2])
    assert text.startswith("cổng 2: 2 hub cùng có camera ở cổng số 2") and "ROOT_HUB30" in text and "PID_0610" in text
    assert "không cổng nào khác trong lần mở này" in text
    assert "cổng của máy có số khác 2" in text and "calib_app --index N" in text and "camera_bench list" in text
    assert "--ports 1 2 3 4" in text and "rig.bench --index" in text and "Device Manager" in text   # webcam gắn sẵn
    # mọi cổng hỏi đều trùng số (camera thứ hai ở cổng gốc 3 của root hub khác): không có hub làm mốc
    plug(monkeypatch, [pnp_cam("C1", HUB, 1), pnp_cam("C2", HUB, 2), pnp_cam("C3", HUB, 3), pnp_cam("AA", ROOT, 2),
                       pnp_cam("BB", ROOT_B, 3)])
    assert "không cổng nào khác trong lần mở này" in refusal([2, 3])
    # cổng không trùng ở hai hub (webcam gắn sẵn ở cổng gốc 7): ports=None từ chối CẢ lời gọi, không bỏ riêng cổng 2
    plug(monkeypatch, [pnp_cam("C1", HUB, 1), pnp_cam("C2", HUB, 2), pnp_cam("AA", ROOT, 2), pnp_cam("WW", ROOT, 7)])
    assert "các cổng còn lại ở nhiều hub" in refusal(None) and "các cổng còn lại ở nhiều hub" in refusal([1, 2, 7])
    assert resolved([1, 2]) == [(1, 0), (2, 1)]                     # gọi rõ cổng camera xe thì được
    # hub làm mốc không có camera ở cổng trùng (camera xe cổng 2 đã rút, hai camera khác ở cổng gốc 2)
    plug(monkeypatch, [pnp_cam("C1", HUB, 1), pnp_cam("AA", ROOT, 2), pnp_cam("BB", ROOT_B, 2)])
    assert f"hub {HUB} của các cổng còn lại không có camera ở cổng 2" in refusal([1, 2])
    # PnP không đọc được hub của cổng làm mốc: không đoán
    plug(monkeypatch, [{**pnp_cam("C1", HUB, 1), "hub": ""}, pnp_cam("C2", HUB, 2), pnp_cam("AA", ROOT, 2)])
    assert "không rõ hub của các cổng còn lại" in refusal([1, 2])
    plug(monkeypatch, [pnp_cam("C3", HUB, 3), pnp_cam("C1", HUB, 1), pnp_cam("C4", HUB, 4), pnp_cam("C2", HUB, 2)])
    assert resolved(None) == [(1, 1), (2, 3), (3, 0), (4, 2)]
    # một camera hai giao diện video ở CÙNG cổng của cùng hub: không mơ hồ, như trước lấy thiết bị DirectShow sau cùng
    plug(monkeypatch, [pnp_cam("C1", HUB, 1), pnp_cam("C1", HUB, 1, mi="02")])
    assert resolved([1]) == [(1, 1)]


@pytest.mark.parametrize("overhead_first", [True, False])
def test_resolve_ports_takes_a_shared_port_number_from_the_hub_of_the_other_ports(monkeypatch, overhead_first):
    """Review 02/10/2026: KICH_BAN_NGHIEM_THU 3.4 bước 4 bảo cắm camera trên cao vào cổng gốc riêng, mà cổng gốc của laptop
    thường mang số 1–4. Bản đầu của T11 từ chối mọi số cổng trùng, nên `rig.bench --ports 1 2 3 4`, dock camera và
    `may_moi` (ports=None) đều dừng. Hỏi nhiều cổng mà các cổng không trùng số cùng ở MỘT hub thì cổng trùng lấy camera
    của nó trên hub đó, bất kể thứ tự index DirectShow (trước T11 thắng là thiết bị DirectShow sau cùng)."""
    from autopark.video import multicam

    vehicle = [pnp_cam("C3", HUB, 3), pnp_cam("C1", HUB, 1), pnp_cam("C4", HUB, 4), pnp_cam("C2", HUB, 2)]
    overhead = pnp_cam("AA", ROOT, 2)
    cameras = [overhead, *vehicle] if overhead_first else [*vehicle, overhead]
    plug(monkeypatch, cameras)
    index = {c["instance_id"]: i for i, c in enumerate(cameras)}
    want = {p: index[pnp_cam(f"C{p}", HUB, p)["instance_id"]] for p in (1, 2, 3, 4)}
    assert resolved([1, 2, 3, 4]) == [(p, want[p]) for p in (1, 2, 3, 4)]
    assert resolved(None) == resolved([1, 2, 3, 4])
    assert resolved([2, 4]) == [(2, want[2]), (4, want[4])]
    assert [s.instance_id for s in multicam.resolve_ports([1, 2])][1] == pnp_cam("C2", HUB, 2)["instance_id"]
    assert "không cổng nào khác" in refusal([2])                    # một cổng: vẫn từ chối
    # cổng trùng mà camera xe ở đó có hai giao diện video: như trước, thiết bị DirectShow sau cùng TRÊN hub đó
    plug(monkeypatch, [pnp_cam("C1", HUB, 1), pnp_cam("C2", HUB, 2), pnp_cam("C2", HUB, 2, mi="02"), overhead])
    assert resolved([1, 2]) == [(1, 0), (2, 2)]
    # hai camera ngoài hub ở cổng gốc 2 và 3 của hai root hub: cổng 1 và 4 làm mốc cho cả hai
    plug(monkeypatch, [*vehicle, pnp_cam("AA", ROOT, 2), pnp_cam("BB", ROOT_B, 3)])
    assert resolved([1, 2, 3, 4]) == [(1, 1), (2, 3), (3, 0), (4, 2)]
