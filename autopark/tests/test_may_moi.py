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


# `policy` như autopark/rig/core.py ghi: mã từ tối 24/09/2026 (có wait_rule) và mã trước đó (không có wait_rule)
POLICY_OWN = {"max_skew_ms": 60.0, "max_wait_ms": 60.0, "wait_rule": "own_cadence", "wait_periods_of_own": 1.5,
              "wait_periods_of_fastest": 1.5, "stale_after_ms": 500.0}
POLICY_OLD = {"max_skew_ms": 60.0, "max_wait_ms": 60.0, "wait_periods_of_fastest": 1.5, "stale_after_ms": 500.0}
WARM = [2950.4, 2811.6, 2700.1, 2600.0]


def rig_json(width, fps, damaged, ai=True, policy=POLICY_OWN, skew=(20.5, 31.0, 44.2), warm_up=WARM):
    cams = [{"port": p, "fps_mean": fps, "frames": 100, "truncated": damaged, "torn": 0, "open_error": None}
            for p in (1, 2, 3, 4)]
    sets = {"sets_built": 99, "sets_partial_wait": 0, "lagging_per_port": {"1": 0, "2": 0, "3": 0, "4": 0}}
    if skew is not None:
        sets["skew_ms"] = {"median": skew[0], "p95": skew[1], "min": 1.0, "max": skew[2], "n": 99}
    rig = {"duration_s": 120.0, "config": {"width": width, "height": 480 if width == 640 else 720}, "cameras": cams,
           "ai": {"sets_per_s_mean": 23.8, "total_ms": {"median": 16.4},
                  "result_age_oldest_frame_ms": {"median": 34.8}} if ai else None,
           "lidar": {"hz_mean": 10.0, "errors": 0}, "resources": {"proc_cpu_cores": {"mean": 0.9}},
           "sets": sets, "stop_alive": []}
    if policy is not None:
        rig["policy"] = dict(policy)
    if ai and warm_up is not None:
        rig["ai"]["warm_up_ms"] = list(warm_up)
    return rig


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


# ---- làm nóng AI, quy tắc chờ, độ lệch bộ ảnh (thêm 24/09/2026) ----

WARM_ROW = "Bàn thử 480p: làm nóng AI theo cỡ lô (ms)"
WARM_TOTAL_ROW = "… tổng làm nóng AI (s)"
RULE_480, RULE_720 = "Bàn thử 480p: quy tắc chờ camera chậm", "720p chỉ camera: quy tắc chờ camera chậm"
SKEW_ROW = "… độ lệch bộ ảnh trung vị / p95 / max (ms)"               # hai dòng: 480p rồi 720p
OWN_LABEL = "nhịp riêng: max(60 ms; 1,5 × chu kỳ của chính từng camera)"
OLD_LABEL = "cũ: max(60 ms; 1,5 × chu kỳ camera nhanh nhất)"
WARN_RULE = "CẢNH BÁO — quy tắc chờ camera chậm khác nhau hoặc không rõ"
WARN_REF_WARM = "CẢNH BÁO — tham chiếu có trước khi bàn thử làm nóng AI"
WARN_MY_WARM = "CẢNH BÁO — lần chạy này không có số làm nóng AI"


def table(text):
    """{nhãn: [(máy này, tham chiếu), …]} theo thứ tự các dòng của bảng trong tom_tat.md."""
    rows = {}
    for line in text.splitlines():
        if line.startswith("| ") and not line.startswith("| Số đo"):
            label, mine, ref = (c.strip() for c in line.strip().strip("|").split("|"))
            rows.setdefault(label, []).append((mine, ref))
    return rows


def make_digest(folder, m01=None, m02=None):
    folder.mkdir(parents=True, exist_ok=True)
    for name, rig in (("m01_480p_lidar_ai.rig.json", m01), ("m02_720p_chi_camera.rig.json", m02)):
        if rig is not None:
            (folder / name).write_text(json.dumps(rig), encoding="utf-8")
    return may_moi.build_digest(folder, {"env": {"ok": True, "value": {"created_local": "t"}}})


def new_shape_reference():
    """Dạng tham_chieu_20260924_toi.json: `policy`, `ai_warm_up_ms` ở tầng ngoài, digest chưa có các khóa mới."""
    return {"note": "máy bàn 19:08.", "policy": dict(POLICY_OWN), "ai_warm_up_ms": [1482.4, 1447.6, 1552.9, 1410.4],
            "digest": {"rig480": {"sets": 2861, "sets_partial_wait": 0, "ai_batch_ms_median": 13.2},
                       "cam720": {"sets": 716, "sets_partial_wait": 0}}}


def old_shape_reference():
    """Dạng tham_chieu_20260924.json (15:25): không có quy tắc chờ, độ lệch bộ ảnh hay làm nóng AI ở đâu cả."""
    return {"note": "máy bàn 15:25", "digest": {"rig480": {"sets": 2861, "sets_partial_wait": 3},
                                                 "cam720": {"sets": 855, "sets_partial_wait": 263}}}


def test_rig_digest_keeps_wait_rule_skew_and_warm_up():
    d = may_moi.rig_digest(rig_json(640, 23.85, 0))
    assert d["wait_rule"] == "own_cadence" and d["policy"]["wait_periods_of_own"] == 1.5
    assert d["skew_ms"] == {"median": 20.5, "p95": 31.0, "max": 44.2} and d["ai_warm_up_ms"] == WARM
    old = may_moi.rig_digest(rig_json(640, 23.85, 0, policy=POLICY_OLD, skew=None, warm_up=None))
    assert old["wait_rule"] == "fastest_camera" and old["skew_ms"] is None and old["ai_warm_up_ms"] is None
    assert may_moi.rig_digest(rig_json(1280, 23.85, 0, ai=False, policy=None))["wait_rule"] is None
    off = dict(POLICY_OWN, max_wait_ms=None, wait_rule=None, wait_periods_of_own=None)
    assert may_moi.wait_rule(off) == "off" and may_moi.wait_rule_label(off) == "tắt: chờ đủ mọi camera"
    assert may_moi.wait_rule_label(POLICY_OWN) == OWN_LABEL and may_moi.wait_rule_label(POLICY_OLD) == OLD_LABEL
    # lô làm nóng chạy theo cỡ n, n−1, …, 1: ba camera thì ba lô
    assert may_moi.warm_up_by_batch([30.0, 20.4, 10.6]) == "3 ảnh 30 / 2 ảnh 20 / 1 ảnh 11"
    assert may_moi.warm_up_by_batch([]) is None


def test_summary_with_new_reference_shape_reads_top_level_policy_and_warm_up(tmp_path):
    digest = make_digest(tmp_path, rig_json(640, 23.85, 0), rig_json(1280, 23.85, 0, ai=False, skew=(16.6, 31.8, 34.4)))
    ref = new_shape_reference()
    before = json.dumps(ref, sort_keys=True)
    text = may_moi.summary_markdown(digest, ref)
    assert json.dumps(ref, sort_keys=True) == before                  # không sửa tệp tham chiếu đã nạp
    rows = table(text)
    assert rows[WARM_ROW] == [("4 ảnh 2950 / 3 ảnh 2812 / 2 ảnh 2700 / 1 ảnh 2600",
                               "4 ảnh 1482 / 3 ảnh 1448 / 2 ảnh 1553 / 1 ảnh 1410")]
    assert rows[WARM_TOTAL_ROW] == [("11,1", "5,9")]
    assert rows[RULE_480] == [(OWN_LABEL, OWN_LABEL)] and rows[RULE_720] == [(OWN_LABEL, OWN_LABEL)]
    assert rows[SKEW_ROW] == [("20,5 / 31,0 / 44,2", "—"), ("16,6 / 31,8 / 34,4", "—")]   # tham chiếu không lưu độ lệch
    assert "CẢNH BÁO" not in text                                      # cùng quy tắc, tham chiếu có làm nóng
    assert "máy bàn 19:08." in text and "19:08.." not in text


def test_summary_with_old_reference_shape_shows_dashes_and_warns(tmp_path):
    digest = make_digest(tmp_path, rig_json(640, 23.85, 0), rig_json(1280, 23.85, 0, ai=False))
    text = may_moi.summary_markdown(digest, old_shape_reference())
    rows = table(text)
    assert rows[WARM_ROW][0][1] == "—" and rows[WARM_TOTAL_ROW] == [("11,1", "—")]
    assert rows[RULE_480] == [(OWN_LABEL, "—")] and rows[RULE_720] == [(OWN_LABEL, "—")]
    assert [r for _, r in rows[SKEW_ROW]] == ["—", "—"]
    assert rows["… bộ thiếu camera chậm"] == [("0", "3"), ("0", "263")]
    warnings = [line for line in text.splitlines() if "CẢNH BÁO" in line]
    assert len(warnings) == 2 and WARN_RULE in warnings[0] and WARN_REF_WARM in warnings[1]
    assert f"bàn thử 480p: máy này «{OWN_LABEL}», tham chiếu «không ghi»" in warnings[0]
    assert "720p chỉ camera: máy này" in warnings[0] and "«không ghi»: json hoặc tệp tham chiếu" in warnings[0]
    assert text.index(WARN_RULE) < text.index("| Số đo")               # cảnh báo đứng trước bảng
    # không có tệp tham chiếu thì không có gì để cảnh báo
    assert "CẢNH BÁO" not in may_moi.summary_markdown(digest, None)


def test_summary_warns_when_this_run_used_another_wait_rule(tmp_path):
    # máy này chạy json của mã cũ (không có wait_rule, không làm nóng), tham chiếu dạng mới
    digest = make_digest(tmp_path, rig_json(640, 23.85, 0, policy=POLICY_OLD, warm_up=None),
                         rig_json(1280, 23.85, 0, ai=False, policy=POLICY_OLD))
    text = may_moi.summary_markdown(digest, new_shape_reference())
    rows = table(text)
    assert rows[RULE_480] == [(OLD_LABEL, OWN_LABEL)] and rows[WARM_ROW][0][0] == "—"
    warnings = [line for line in text.splitlines() if "CẢNH BÁO" in line]
    assert len(warnings) == 2 and WARN_MY_WARM in warnings[0] and WARN_RULE in warnings[1]
    assert f"máy này «{OLD_LABEL}», tham chiếu «{OWN_LABEL}»" in warnings[1] and "«không ghi»" not in warnings[1]
    # chỉ 720p khác quy tắc thì cảnh báo chỉ nêu 720p
    digest = make_digest(tmp_path / "b", rig_json(640, 23.85, 0), rig_json(1280, 23.85, 0, ai=False, policy=POLICY_OLD))
    warn = [line for line in may_moi.summary_markdown(digest, new_shape_reference()).splitlines() if WARN_RULE in line]
    assert len(warn) == 1 and "720p chỉ camera" in warn[0] and "bàn thử 480p" not in warn[0]


def test_reference_digest_keeps_keys_already_in_the_digest():
    # tham chiếu tạo từ may_moi.json của mã này: digest đã có khóa mới, tầng ngoài không được đè lên
    ref = new_shape_reference()
    ref["digest"]["rig480"].update(policy=dict(POLICY_OLD), ai_warm_up_ms=[1000.0, 900.0])
    got = may_moi.reference_digest(ref)
    assert may_moi.wait_rule(got["rig480"]["policy"]) == "fastest_camera"
    assert got["rig480"]["ai_warm_up_ms"] == [1000.0, 900.0]
    assert got["cam720"]["wait_rule"] == "own_cadence"                # cam720 chưa có → lấy policy tầng ngoài
    assert may_moi.reference_digest(None) == {}
    assert may_moi.reference_digest(old_shape_reference())["rig480"].get("policy") is None


def test_both_reference_files_shipped_in_repo_render(tmp_path):
    folder = may_moi.Path(may_moi.__file__).resolve().parents[2] / "docs" / "evidence" / "may_ban"
    old, new = folder / "tham_chieu_20260924.json", folder / "tham_chieu_20260924_toi.json"
    if not (old.exists() and new.exists()):
        pytest.skip("thiếu tệp tham chiếu máy bàn 24/09")
    digest = make_digest(tmp_path, rig_json(640, 23.85, 0), rig_json(1280, 23.85, 0, ai=False))
    text = may_moi.summary_markdown(digest, may_moi.load_json(new))
    rows = table(text)
    assert rows[WARM_ROW][0][1] == "4 ảnh 1482 / 3 ảnh 1448 / 2 ảnh 1553 / 1 ảnh 1410"
    assert rows[RULE_480][0][1] == OWN_LABEL and rows[RULE_720][0][1] == OWN_LABEL
    assert "CẢNH BÁO" not in text
    text = may_moi.summary_markdown(digest, may_moi.load_json(old))
    rows = table(text)
    assert rows[WARM_ROW][0][1] == "—" and rows[RULE_480][0][1] == "—" and rows[SKEW_ROW][0][1] == "—"
    assert WARN_RULE in text and WARN_REF_WARM in text


def _analysis(folder, rate, beams):
    """Tệp phân tích LiDAR như lidar.bench ghi: <folder>/lidar/l01_tinh.analysis.json."""
    (folder / "lidar").mkdir(parents=True, exist_ok=True)
    (folder / "lidar" / "l01_tinh.analysis.json").write_text(
        json.dumps({"summary": {"rate_hz": rate, "beams_median": beams, "no_return_fraction": 0.27}, "passed": True}),
        encoding="utf-8")


def test_main_with_empty_steps_only_resummarizes_existing_files(tmp_path, monkeypatch, capsys):
    out = tmp_path / "kq"
    make_digest(out, rig_json(640, 23.85, 0), rig_json(1280, 23.85, 0, ai=False))
    _analysis(out, 9.99, 508.0)
    # đường dẫn `analysis` lưu lúc đo trên laptop (tương đối với thư mục đứng lúc đó, tên thư mục khác): không dùng
    lidar = {"port": "COM5", "health": "OK", "analysis": "runs\\may_moi_20260925_0930\\lidar\\l01_tinh.analysis.json"}
    (out / "may_moi.json").write_text(json.dumps({"results": {"env": {"ok": True, "value": {"created_local": "lần cũ"}},
                                                              "lidar": {"ok": True, "value": lidar},
                                                              "rig480": {"ok": True, "value": {"exit": 0}}}}),
                                      encoding="utf-8")

    # ghi lại lời gọi thay vì ném lỗi (run_step nuốt lỗi); chặn cả các lệnh chạm thiết bị: camera_bench list
    # (Get-PnpDevice + DirectShow thật), rplidar_c1, lidar.bench, rig.bench
    calls = []

    def record(*a, **k):
        calls.append(a)
    for name in ("env_report", "camera_selection", "find_lidar_port", "ai_latency"):
        monkeypatch.setattr(may_moi, name, record)
    import autopark.lidar.bench as lidar_bench
    import autopark.lidar.rplidar_c1 as rplidar_c1
    import autopark.rig.bench as rig_bench
    import autopark.video.camera_bench as cb
    for module in (cb, rplidar_c1, lidar_bench, rig_bench):
        monkeypatch.setattr(module, "main", record)
    monkeypatch.setattr(may_moi, "find_reference", lambda root: old_shape_reference())
    code = may_moi.main(["--out", str(out), "--steps", "--runs", str(tmp_path / "khong_co_runs")])
    assert calls == [] and code == 0
    text = (out / "tom_tat.md").read_text(encoding="utf-8")
    assert "Kiểm máy mới — lần cũ" in text and WARN_REF_WARM in text
    rows = table(text)
    assert rows[WARM_ROW] == [("4 ảnh 2950 / 3 ảnh 2812 / 2 ảnh 2700 / 1 ảnh 2600", "—")]
    assert rows["LiDAR: tốc độ quay (Hz)"] == [("9,99", "—")] and rows["LiDAR: cổng COM"] == [("COM5", "—")]
    saved = json.loads((out / "may_moi.json").read_text(encoding="utf-8"))
    assert set(saved["results"]) == {"env", "lidar", "rig480"}
    assert saved["digest"]["rig480"]["wait_rule"] == "own_cadence"
    assert saved["digest"]["cam720"]["skew_ms"] == {"median": 20.5, "p95": 31.0, "max": 44.2}
    assert saved["digest"]["lidar"]["beams_median"] == 508.0
    # tóm tắt lại mà không có thư mục kết quả: dừng (mã 2), không tạo thư mục rỗng; thiếu --out và --out sai là hai lỗi
    # khác nhau, lỗi sau in đường dẫn tuyệt đối đã tra và thư mục đang đứng
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        may_moi.main(["--steps", "--runs", str(tmp_path / "khong_co_runs")])
    err = capsys.readouterr().err
    assert exc.value.code == 2 and "cần --out" in err and "không thấy thư mục" not in err
    monkeypatch.chdir(tmp_path)                                    # --out tương đối: lỗi phải in đường dẫn tuyệt đối
    with pytest.raises(SystemExit) as exc:
        may_moi.main(["--steps", "--out", "chua_co", "--runs", str(tmp_path / "khong_co_runs")])
    err = capsys.readouterr().err
    assert exc.value.code == 2 and "không thấy thư mục kết quả" in err
    assert str((tmp_path / "chua_co").resolve()) in err and f"thư mục đang đứng: {may_moi.Path.cwd()}" in err
    assert not (tmp_path / "chua_co").exists() and not (tmp_path / "khong_co_runs").exists()


def test_lidar_step_saves_analysis_path_relative_to_out(tmp_path, monkeypatch):
    # bước lidar với thiết bị giả: cổng, info và bản ghi 15 s đều thay bằng hàm giả, không mở cổng COM nào
    import autopark.lidar.bench as lidar_bench
    import autopark.lidar.rplidar_c1 as rplidar_c1
    out = tmp_path / "kq"
    seen = []

    def fake_info(argv):
        seen.append(("info", argv))
        print("đang đọc…\n" + json.dumps({"health": {"name": "OK"}, "device": {"serial": "abc"}}))
        return 0

    def fake_record(argv):
        seen.append(("record", argv))
        _analysis(out, 10.01, 509.0)
        return 0
    monkeypatch.setattr(may_moi, "find_lidar_port", lambda: "COM9")
    monkeypatch.setattr(rplidar_c1, "main", fake_info)
    monkeypatch.setattr(lidar_bench, "main", fake_record)
    monkeypatch.setattr(may_moi, "find_reference", lambda root: None)
    assert may_moi.main(["--out", str(out), "--steps", "lidar", "--runs", str(tmp_path / "khong_co_runs")]) == 0
    assert [kind for kind, _ in seen] == ["info", "record"] and seen[0][1] == ["info", "--port", "COM9"]
    assert seen[1][1][seen[1][1].index("--out") + 1] == str(out / "lidar")
    saved = json.loads((out / "may_moi.json").read_text(encoding="utf-8"))
    value = saved["results"]["lidar"]["value"]
    # đường dẫn lưu tương đối với thư mục kết quả, không còn phụ thuộc thư mục đứng lúc đo
    assert value["analysis"] == "lidar/l01_tinh.analysis.json" and value["health"] == "OK" and value["serial"] == "abc"
    assert saved["digest"]["lidar"] == {"port": "COM9", "health": "OK", "rate_hz": 10.01, "beams_median": 509.0,
                                        "no_return_fraction": 0.27, "passed": True}
    assert json.loads((out / "lidar_info.json").read_text(encoding="utf-8"))["health"]["name"] == "OK"


def test_resummarize_renamed_folder_reads_its_own_lidar_analysis(tmp_path, monkeypatch):
    # thư mục laptop mang về, đổi tên; may_moi.json lưu đường dẫn tương đối với thư mục đứng lúc đo trên laptop
    out = tmp_path / "laptop_mang_ve"
    _analysis(out, 9.99, 508.0)
    _analysis(tmp_path / "runs" / "may_moi_goc", 5.5, 111.0)          # thư mục mang tên gốc, số khác: không được đọc
    stored = str(may_moi.Path("runs") / "may_moi_goc" / "lidar" / "l01_tinh.analysis.json")
    (out / "may_moi.json").write_text(json.dumps({"results": {
        "env": {"ok": True, "value": {"created_local": "laptop"}},
        "lidar": {"ok": True, "value": {"port": "COM5", "health": "OK", "analysis": stored}}}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(may_moi, "find_reference", lambda root: None)
    assert may_moi.main(["--out", str(out), "--steps", "--runs", str(tmp_path / "khong_co_runs")]) == 0
    text = (out / "tom_tat.md").read_text(encoding="utf-8")
    assert "| LiDAR: tốc độ quay (Hz) | 9,99 | — |" in text
    assert "| LiDAR: số tia mỗi vòng (trung vị) | 508 | — |" in text
    assert "không thấy tệp phân tích" not in text
    saved = json.loads((out / "may_moi.json").read_text(encoding="utf-8"))
    assert saved["digest"]["lidar"]["rate_hz"] == 9.99 and saved["digest"]["lidar"]["port"] == "COM5"
    # đường dẫn lưu trỏ vào chỗ không có (đổi ổ đĩa, --out tuyệt đối trên laptop): vẫn đọc tệp trong thư mục
    results = {"lidar": {"ok": True, "value": {"port": "COM5", "analysis": str(tmp_path / "khong_co" / "x.json")}}}
    assert may_moi.build_digest(out, results)["lidar"]["beams_median"] == 508.0


def test_build_digest_reads_lidar_analysis_inside_out_not_saved_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "kq"
    _analysis(out, 10.0, 508.0)
    _analysis(tmp_path / "goc", 99.0, 1.0)
    other = tmp_path / "goc" / "lidar" / "l01_tinh.analysis.json"
    # đường dẫn tương đối không còn đúng, và đường dẫn tuyệt đối tới thư mục khác có tệp: cả hai đều bỏ qua
    for saved in ("runs\\may_moi_20260925_0930\\lidar\\l01_tinh.analysis.json", str(other)):
        d = may_moi.build_digest(out, {"lidar": {"ok": True, "value": {"port": "COM5", "analysis": saved}}})
        assert d["lidar"]["rate_hz"] == 10.0 and d["lidar"]["beams_median"] == 508.0 and d["lidar"]["port"] == "COM5"
        assert "analysis_missing" not in d["lidar"]
    # bước lidar báo xong mà thư mục không có tệp phân tích: không đọc tệp của thư mục khác, nói rõ thiếu tệp nào
    bare = tmp_path / "chep_thieu"
    bare.mkdir()
    d = may_moi.build_digest(bare, {"env": {"ok": True, "value": {"created_local": "t"}},
                                    "lidar": {"ok": True, "value": {"port": "COM5", "analysis": str(other)}}})
    missing = str(bare / "lidar" / "l01_tinh.analysis.json")
    assert d["lidar"] == {"port": "COM5", "health": None, "analysis_missing": missing}
    text = may_moi.summary_markdown(d, None)
    assert f"không thấy tệp phân tích `{missing}`" in text and table(text)["LiDAR: tốc độ quay (Hz)"] == [("—", "—")]
    # bước lidar lỗi: dòng "Bước lỗi" đã nói, không thêm dòng thiếu tệp
    d = may_moi.build_digest(bare, {"lidar": {"ok": False, "error": "RuntimeError('không thấy CP210x')"}})
    assert "analysis_missing" not in d["lidar"]
    assert "không thấy tệp phân tích" not in may_moi.summary_markdown(d, None)


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


def rule_warnings(text):
    return [line for line in text.splitlines() if WARN_RULE in line]


def test_summary_warns_when_only_wait_parameters_differ(tmp_path):
    ref = new_shape_reference()                                        # tham chiếu: POLICY_OWN cho cả hai bước

    def m01(policy):
        return rig_json(640, 23.85, 0, policy=policy)
    # cùng quy tắc nhịp riêng nhưng sàn và số chu kỳ khác (vd. mã sau chỉnh WAIT_PERIODS): nhãn khác, cảnh báo 480p
    p480 = dict(POLICY_OWN, max_wait_ms=120.0, wait_periods_of_own=2.0, wait_periods_of_fastest=2.0)
    text = may_moi.summary_markdown(make_digest(tmp_path / "a", m01(p480),
                                                rig_json(1280, 23.85, 0, ai=False)), ref)
    assert table(text)[RULE_480] == [("nhịp riêng: max(120 ms; 2,0 × chu kỳ của chính từng camera)", OWN_LABEL)]
    warn = rule_warnings(text)
    assert len(warn) == 1 and "bàn thử 480p" in warn[0] and "720p chỉ camera" not in warn[0] and "(khác" not in warn[0]
    assert "«không ghi»" not in warn[0]
    # chỉ sàn khác; chỉ số chu kỳ của chính camera khác
    text = may_moi.summary_markdown(make_digest(tmp_path / "b", m01(dict(POLICY_OWN, max_wait_ms=90.0))), ref)
    assert len(rule_warnings(text)) == 1
    text = may_moi.summary_markdown(make_digest(tmp_path / "b2", m01(dict(POLICY_OWN, wait_periods_of_own=2.0))), ref)
    assert len(rule_warnings(text)) == 1 and "2,0 × chu kỳ của chính từng camera" in rule_warnings(text)[0]
    # chỉ `max_skew_ms` ở 720p khác: dòng quy tắc hai cột giống hệt, cảnh báo nêu khóa khác
    text = may_moi.summary_markdown(make_digest(tmp_path / "c", rig_json(640, 23.85, 0),
                                                rig_json(1280, 23.85, 0, ai=False,
                                                         policy=dict(POLICY_OWN, max_skew_ms=30.0))), ref)
    assert table(text)[RULE_720] == [(OWN_LABEL, OWN_LABEL)]
    warn = rule_warnings(text)
    assert len(warn) == 1 and "720p chỉ camera" in warn[0] and "bàn thử 480p" not in warn[0]
    assert "(khác `max_skew_ms` 30 / 60)" in warn[0]
    # sàn 60,4 và 60 cùng in '60 ms', `stale_after_ms` khác: nêu cả hai, không làm tròn
    p = dict(POLICY_OWN, max_wait_ms=60.4, stale_after_ms=250.0)
    text = may_moi.summary_markdown(make_digest(tmp_path / "d", m01(p)), ref)
    assert table(text)[RULE_480] == [(OWN_LABEL, OWN_LABEL)]
    assert "(khác `max_wait_ms` 60,4 / 60, `stale_after_ms` 250 / 500)" in rule_warnings(text)[0]
    # nhãn khác và `max_skew_ms` cũng khác: vẫn nêu `max_skew_ms` (không in trong nhãn)
    text = may_moi.summary_markdown(make_digest(tmp_path / "e", m01(dict(POLICY_OLD, max_skew_ms=45.0))), ref)
    assert f"máy này «{OLD_LABEL}», tham chiếu «{OWN_LABEL}» (khác `max_skew_ms` 45 / 60)" in rule_warnings(text)[0]
    # `wait_periods_of_fastest` không dùng trong quy tắc nhịp riêng (chỉ ghi cho trình đọc cũ): không cảnh báo
    digest = make_digest(tmp_path / "f", m01(dict(POLICY_OWN, wait_periods_of_fastest=3.0)))
    assert "CẢNH BÁO" not in may_moi.summary_markdown(digest, ref)
    # hai bên cùng tắt chờ nhưng `max_skew_ms` khác
    off = dict(POLICY_OWN, max_wait_ms=None, wait_rule=None, wait_periods_of_own=None, wait_periods_of_fastest=None)
    assert may_moi.wait_rule_key(off) == ("off", None, None, 60.0, 500.0)
    ref_off = dict(new_shape_reference(), policy=off)
    text = may_moi.summary_markdown(make_digest(tmp_path / "g", m01(dict(off, max_skew_ms=80.0))), ref_off)
    assert "máy này «tắt: chờ đủ mọi camera», tham chiếu «tắt: chờ đủ mọi camera» (khác `max_skew_ms` 80 / 60)" \
        in rule_warnings(text)[0]
    assert may_moi.wait_rule_key(None) is None and may_moi.wait_rule_key({}) is None


def test_my_warm_up_warning_only_when_this_run_had_an_ai_batch(tmp_path):
    ref = new_shape_reference()                                   # cùng quy tắc, có làm nóng: không cảnh báo gì khác
    # bước rig480 lỗi (ví dụ không thấy camera): không có m01 → không được nói "tệp do mã trước tối 24/09/2026 ghi"
    digest = make_digest(tmp_path / "a", None, rig_json(1280, 23.85, 0, ai=False))
    assert digest["rig480"] is None
    assert "CẢNH BÁO" not in may_moi.summary_markdown(digest, ref)
    # bàn thử chạy --no-ai: có m01 nhưng không có lô AI → cũng không cảnh báo làm nóng
    digest = make_digest(tmp_path / "b", rig_json(640, 23.85, 0, ai=False), rig_json(1280, 23.85, 0, ai=False))
    assert digest["rig480"]["ai_batch_ms_median"] is None
    assert "CẢNH BÁO" not in may_moi.summary_markdown(digest, ref)
    # có lô AI nhưng ai.warm_up_ms trống → cảnh báo, kể cả khi chưa có tệp tham chiếu, và đứng trước bảng
    text = may_moi.summary_markdown(make_digest(tmp_path / "c", rig_json(640, 23.85, 0, warm_up=None)), None)
    assert WARN_MY_WARM in text and text.index(WARN_MY_WARM) < text.index("| Số đo")


def test_wait_rule_warning_when_neither_side_recorded_a_policy(tmp_path):
    # json máy này của loạt 20260923 trở về trước (không có `policy`) so với tham_chieu_20260924.json (15:25)
    digest = make_digest(tmp_path, rig_json(640, 23.85, 0, policy=None),
                         rig_json(1280, 23.85, 0, ai=False, policy=None))
    text = may_moi.summary_markdown(digest, old_shape_reference())
    warnings = rule_warnings(text)
    assert len(warnings) == 1
    assert "bàn thử 480p: máy này «không ghi», tham chiếu «không ghi»" in warnings[0]
    assert "720p chỉ camera: máy này «không ghi», tham chiếu «không ghi»" in warnings[0]
    assert "«không ghi»: json hoặc tệp tham chiếu" in warnings[0]


def test_find_reference_takes_last_file_by_name_and_summary_names_it(tmp_path):
    assert may_moi.find_reference(tmp_path) is None
    folder = tmp_path / "docs" / "evidence" / "may_ban"
    folder.mkdir(parents=True)
    old, new = old_shape_reference(), new_shape_reference()
    (folder / "tham_chieu_20260924.json").write_text(json.dumps(old), encoding="utf-8")
    (folder / "tham_chieu_20260924_toi.json").write_text(json.dumps(new), encoding="utf-8")
    ref = may_moi.find_reference(tmp_path)
    assert ref["_file"] == "tham_chieu_20260924_toi.json" and ref["note"] == new["note"]
    digest = make_digest(tmp_path / "kq", rig_json(640, 23.85, 0), rig_json(1280, 23.85, 0, ai=False))
    text = may_moi.summary_markdown(digest, ref)
    assert "- Tham chiếu máy bàn (`tham_chieu_20260924_toi.json`): máy bàn 19:08." in text
    # `_file` đã có trong tệp thì giữ nguyên (setdefault)
    (folder / "tham_chieu_20260925.json").write_text(json.dumps(dict(new, _file="goc.json")), encoding="utf-8")
    assert may_moi.find_reference(tmp_path)["_file"] == "goc.json"
