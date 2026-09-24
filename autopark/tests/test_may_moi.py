"""Lệnh kiểm máy mới (rig/may_moi.py) không cần phần cứng: tìm cổng LiDAR, chọn camera theo cổng hub hoặc index, đo thời
gian AI với bộ phân đoạn giả, tóm tắt từ các tệp kết quả, chạy cả lệnh với mọi bước lỗi mà không dừng giữa chừng."""
import json
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")

from autopark.rig import may_moi  # noqa: E402
from autopark.video.multicam import CameraSpec  # noqa: E402


def test_finds_the_cp210x_port_and_ignores_others():
    ports = [SimpleNamespace(device="COM1", vid=None, pid=None), SimpleNamespace(device="COM7", vid=0x10C4, pid=0xEA60),
             SimpleNamespace(device="COM9", vid=0x2341, pid=0x0043)]
    assert may_moi.find_lidar_port(ports) == "COM7"
    assert may_moi.find_lidar_port(ports[:1]) is None


def test_camera_selection_prefers_hub_ports_and_falls_back_to_directshow_index():
    via_hub = may_moi.camera_selection(resolve=lambda _: [CameraSpec(port=p, index=i) for i, p in enumerate((1, 2, 3, 4))],
                                       dshow=lambda: [])
    assert via_hub["mode"] == "ports" and via_hub["argv"] == ["--ports", "1", "2", "3", "4"]
    rows = [{"name": "Integrated Webcam"}, {"name": "HD Camera"}, {"name": "HD Camera"}]
    direct = may_moi.camera_selection(resolve=lambda _: [], dshow=lambda: rows)
    assert direct["mode"] == "index" and direct["argv"] == ["--index", "1", "2"]      # bỏ webcam của laptop
    # webcam gắn sẵn cũng tên "HD Camera": chỉ lấy camera Sunplus 1BCF:0B09 theo DevicePath
    rows = [{"name": "HD Camera", "device_path": "\\\\?\\usb#vid_04f2&pid_b6d9&mi_00#6&1"},
            {"name": "HD Camera", "device_path": "\\\\?\\usb#vid_1bcf&pid_0b09&mi_00#7&2"},
            {"name": "HD Camera", "device_path": "\\\\?\\usb#vid_1bcf&pid_0b09&mi_00#7&3"}]
    assert may_moi.camera_selection(resolve=lambda _: [], dshow=lambda: rows)["argv"] == ["--index", "1", "2"]

    def broken(_):
        raise ValueError("không thấy camera ở cổng")
    fallback = may_moi.camera_selection(resolve=broken, dshow=lambda: [{"name": "X"}])
    assert fallback["argv"] == ["--index", "0"] and "không thấy camera ở cổng" in fallback["note"]
    with pytest.raises(RuntimeError):
        may_moi.camera_selection(resolve=lambda _: [], dshow=lambda: [])


class FakeSegmenter:
    device, amp, name = "cpu", False, "gia"

    def __init__(self):
        self.calls = 0

    def infer(self, images, out_size=None):
        self.calls += 1
        assert len(images) == 4 and images[0].shape == (480, 640, 3) and out_size == (640, 480)
        return [np.zeros((480, 640), np.float32)] * 4, SimpleNamespace(total_ms=10.0 + self.calls % 3, model_ms=6.0)


def test_ai_latency_measures_batches_after_warmup():
    seg = FakeSegmenter()
    r = may_moi.ai_latency(lambda: seg, batches=12, warmup=3)
    assert seg.calls == 15 and r["batches"] == 12 and r["batch"] == 4 and r["size"] == [640, 480]
    assert 10.0 <= r["total_ms"]["median"] <= 12.0 and r["model_ms"]["median"] == 6.0 and r["device"] == "cpu"


def rig_json(width, fps, damaged, ai=True):
    cams = [{"port": p, "fps_mean": fps, "frames": 100, "truncated": damaged, "torn": 0, "open_error": None}
            for p in (1, 2, 3, 4)]
    return {"duration_s": 120.0, "config": {"width": width, "height": 480 if width == 640 else 720}, "cameras": cams,
            "ai": {"sets_per_s_mean": 23.8, "total_ms": {"median": 16.4},
                   "result_age_oldest_frame_ms": {"median": 34.8}} if ai else None,
            "lidar": {"hz_mean": 10.0, "errors": 0}, "resources": {"proc_cpu_cores": {"mean": 0.9}},
            "stop_alive": []}


def test_summary_compares_with_reference_and_lists_failed_steps(tmp_path):
    (tmp_path / "m01_480p_lidar_ai.rig.json").write_text(json.dumps(rig_json(640, 23.85, 0)), encoding="utf-8")
    (tmp_path / "m02_720p_chi_camera.rig.json").write_text(json.dumps(rig_json(1280, 12.0, 300, ai=False)), encoding="utf-8")
    (tmp_path / "usb_topology.json").write_text(json.dumps({"dshow_index_to_port": [{"hub_port": 1}, {"hub_port": None}],
                                                            "hubs": [{"friendly_name": "USB2.1 Hub"}]}), encoding="utf-8")
    results = {"env": {"ok": True, "value": {"processor": "i7", "gpu": "RTX 3050 Ti", "created_local": "t"}},
               "ai": {"ok": True, "value": {"total_ms": {"median": 30.0, "p95": 40.0}, "model_ms": {"median": 20.0},
                                              "peak_vram_mb": 300.0, "device": "cuda"}},
               "lidar": {"ok": False, "error": "RuntimeError('không thấy bộ chuyển CP210x')"}}
    digest = may_moi.build_digest(tmp_path, results)
    assert digest["usb"] == {"cameras": 2, "with_hub_port": 1, "hubs": ["USB2.1 Hub"]}
    assert digest["rig480"]["good_fps"] == [23.85] * 4 and digest["cam720"]["damaged"] == [300] * 4
    assert digest["errors"] == {"lidar": "RuntimeError('không thấy bộ chuyển CP210x')"}
    reference = {"note": "máy bàn 24/09", "digest": {"ai": {"total_ms_median": 12.0}}}
    text = may_moi.summary_markdown(digest, reference)
    assert "| AI: một lô 4 ảnh 480p, trung vị (ms) | 30,0 | 12,0 |" in text
    assert "lidar (RuntimeError" in text and "máy bàn 24/09" in text and "RTX 3050 Ti" in text
    assert "| 720p chỉ camera: khung hỏng | 300 / 300 / 300 / 300 | — |" in text


def test_reference_file_shipped_in_repo_is_readable():
    ref = may_moi.find_reference(may_moi.Path(may_moi.__file__).resolve().parents[2])
    if ref is None:
        pytest.skip("chưa có tệp tham chiếu máy bàn")
    assert "digest" in ref and "note" in ref


def test_main_keeps_going_when_every_step_fails(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("không có thiết bị")
    monkeypatch.setattr(may_moi, "env_report", boom)
    monkeypatch.setattr(may_moi, "find_lidar_port", lambda: None)
    monkeypatch.setattr(may_moi, "camera_selection", boom)
    import autopark.video.camera_bench as cb
    monkeypatch.setattr(cb, "main", lambda argv: 2)
    code = may_moi.main(["--out", str(tmp_path / "kq"), "--runs", str(tmp_path / "khong_co_runs")])
    assert code == 1
    saved = json.loads((tmp_path / "kq" / "may_moi.json").read_text(encoding="utf-8"))
    assert set(saved["results"]) == set(may_moi.STEPS) and not any(v["ok"] for v in saved["results"].values())
    assert "không có checkpoint" in saved["results"]["ai"]["error"]
    assert (tmp_path / "kq" / "tom_tat.md").exists()


def test_dry_run_touches_nothing(tmp_path):
    assert may_moi.main(["--dry-run", "--out", str(tmp_path / "kq")]) == 0
    assert not (tmp_path / "kq").exists()
