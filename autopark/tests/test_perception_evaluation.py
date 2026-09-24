"""Evaluation helpers: decision threshold, F2 selection, ROI application, external label mapping and curves (CPU)."""
import json

import pytest

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("cv2")
pytest.importorskip("PIL")

from autopark.perception.engine import decide, evaluate_split  # noqa: E402
from autopark.perception.evaluate import f_beta, threshold_sweep_report  # noqa: E402
from autopark.perception.evaluate_external import (build_lut, confusion, per_source_class, score_curves,  # noqa: E402
                                                    source_class_report, variant_luts)
from autopark.perception.roi import apply_roi, roi_to_model_size  # noqa: E402
from tests.conftest import PROJECT_ROOT  # noqa: E402


def test_decide_thresholds_and_sends_ties_to_blocked():
    logits = torch.zeros(1, 2, 2, 2)                    # P(BLOCKED) = 0.5 everywhere
    assert decide(logits, 0.5).sum() == 4               # a tie is never resolved towards FREE
    logits[0, 1] = torch.tensor([[2.0, -2.0], [0.0, 0.5]])
    probs = logits.softmax(1)[0, 1]
    for t in (0.15, 0.5, 0.9):
        assert torch.equal(decide(logits, t)[0], (probs >= t).long())
    with pytest.raises(ValueError):
        decide(logits, 1.0)


def test_f_beta_and_sweep_selection_rules(tmp_path):
    assert f_beta(1.0, 1.0, 2.0) == 1.0 and f_beta(None, 1.0, 2.0) is None and f_beta(0.0, 0.0, 2.0) is None
    assert f_beta(0.5, 1.0, 2.0) == pytest.approx(5 * 0.5 / (4 * 0.5 + 1.0))
    sweep = {0.2: {"mIoU": 0.90, "iou_free": 0.9, "iou_blocked": 0.9, "blocked_precision": 0.85, "blocked_recall": 0.995,
                   "blocked_as_free_rate": 0.01, "free_as_blocked_rate": 0.1},
             0.5: {"mIoU": 0.95, "iou_free": 0.95, "iou_blocked": 0.95, "blocked_precision": 0.95, "blocked_recall": 0.95,
                   "blocked_as_free_rate": 0.05, "free_as_blocked_rate": 0.02}}
    report = threshold_sweep_report(sweep, tmp_path / "best.pt")
    assert report["selection"] == {"max_mIoU": 0.5, "max_blocked_F2": 0.2} and report["split"] == "val"
    assert [r["threshold"] for r in report["rows"]] == [0.2, 0.5]


def test_apply_roi_never_turns_excluded_pixels_into_free():
    labels = np.array([[0, 1, 255], [0, 0, 1]], np.uint8)
    roi = np.array([[255, 0, 255], [0, 255, 255]], np.uint8)
    out = apply_roi(labels, roi)
    assert out.tolist() == [[0, 255, 255], [255, 0, 1]]
    with pytest.raises(ValueError):
        apply_roi(labels, roi[:, :2])
    native = np.full((100, 200), 255, np.uint8)
    native[:, :50] = 0
    small = roi_to_model_size(native, 384, 512)
    assert small.shape == (384, 512) and (small[:64] == 0).all() and (small[320:] == 0).all()   # letterbox bars excluded
    assert (small[64:320, :128] == 0).all() and (small[64:320, 200:] == 255).all()


def test_acdc_mapping_builds_a_consistent_lut_and_variants():
    mapping = json.loads((PROJECT_ROOT / "configs/acdc_cityscapes_to_binary_v1.json").read_text(encoding="utf-8"))
    lut = build_lut(mapping)
    assert lut[7] == 0 and lut[9] == 0 and lut[26] == 1 and lut[24] == 1 and lut[23] == 255 and lut[8] == 255
    assert set(np.unique(lut).tolist()) <= {0, 1, 255}
    variants = variant_luts(mapping, lut)
    assert variants["sidewalk_terrain_blocked"][8] == 1 and variants["sidewalk_terrain_blocked"][7] == 0
    with pytest.raises(ValueError):
        build_lut({"free": {"7": "road"}, "blocked": {"7": "also road"}, "ignore": {}})
    with pytest.raises(ValueError):
        variant_luts({"variants": {"bad": {"23": 2}}}, lut)


def test_confusion_and_per_source_class_ignore_255():
    raw = np.array([[7, 7, 26, 23], [26, 8, 24, 24]], np.uint8)         # road, road, car, sky / car, sidewalk, person x2
    lut = build_lut({"free": {"7": "road"}, "blocked": {"26": "car", "24": "person"}, "ignore": {"23": "sky", "8": "sidewalk"}})
    truth = lut[raw]
    pred = np.array([[0, 1, 1, 0], [0, 0, 1, 0]], np.uint8)
    matrix = confusion(pred, truth)
    assert matrix.tolist() == [[1, 1], [2, 2]]                          # sky and sidewalk pixels never counted
    counts = per_source_class(raw, truth, pred)
    assert counts[23].sum() == 0 and counts[8].sum() == 0
    report = source_class_report(counts, lut, {"26": "car", "24": "person", "7": "road"})
    assert report["per_class"]["24"]["predicted_blocked_rate"] == 0.5     # one of two person pixels called FREE
    assert report["per_class"]["7"]["predicted_blocked_rate"] == 0.5      # false alarm on one road pixel
    assert report["groups"]["persons_and_riders"]["pixels"] == 2


def test_score_curves_match_brute_force():
    rng = np.random.default_rng(0)
    pos = rng.beta(5, 2, 4000)
    neg = rng.beta(2, 5, 6000)
    bins = 1000
    pos_hist = np.bincount(np.minimum((pos * bins).astype(int), bins - 1), minlength=bins)
    neg_hist = np.bincount(np.minimum((neg * bins).astype(int), bins - 1), minlength=bins)
    curves = score_curves(pos_hist, neg_hist)
    scores = np.concatenate([pos, neg])
    labels = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))])
    order = np.argsort(-scores)
    tp = np.cumsum(labels[order])
    fp = np.cumsum(1 - labels[order])
    precision, recall = tp / (tp + fp), tp / len(pos)
    ap = float(np.sum(np.diff(np.concatenate([[0.0], recall])) * precision))
    auroc = float(np.trapezoid(np.concatenate([[0.0], recall]), np.concatenate([[0.0], fp / len(neg)])))
    assert curves["average_precision"] == pytest.approx(ap, abs=2e-3)
    assert curves["auroc"] == pytest.approx(auroc, abs=2e-3)
    assert 0 < curves["fpr_at_95_tpr"] < 0.5
    assert score_curves(np.zeros(bins, int), neg_hist)["average_precision"] is None


def test_evaluate_split_sweep_accumulates_per_threshold(tmp_path):
    from autopark.perception.model import build_model
    from tests.test_perception_training import _make_cache
    from autopark.perception.dataset import PreparedCache, SplitData
    cache = PreparedCache.open(_make_cache(tmp_path / "cache"))
    data = SplitData(cache, "val")
    result = evaluate_split(build_model(2, pretrained=False), data, batch_size=4, device=torch.device("cpu"), amp=False,
                            threshold=0.3, sweep_thresholds=[0.1, 0.3, 0.9])
    assert result["report"]["threshold"] == 0.3
    sweep = result["sweep"]
    assert set(sweep) == {0.1, 0.3, 0.9} and sweep[0.3]["confusion_matrix"] == result["report"]["confusion_matrix"]
    assert sweep[0.1]["blocked_recall"] >= sweep[0.3]["blocked_recall"] >= sweep[0.9]["blocked_recall"]


# ---------------------------------------------------------------- chặn chấm trên ảnh đã huấn luyện (evaluate.py, 24/09/2026)
def test_find_overlap_flags_each_kind_of_match_on_its_own():
    """Mỗi ảnh chấm trùng tham chiếu theo ĐÚNG MỘT cách, nên bỏ một phép so thì đúng một khẳng định hỏng."""
    from autopark.perception.evaluate import find_overlap
    reference = [{"id": "a", "image_sha256": "s1"},
                 {"id": "b", "cache": "acdc_binary_v1"},                                  # bản ghi của cache ghép
                 {"id": "c"},                                                             # cache thường: tên thư mục
                 {"id": "x", "snapshot": "20260923_100000_000", "captured_local": "2026-09-23T10:00:00.000"},
                 {"id": "y", "captured_local": "2026-09-23T12:00:00.000", "frame_captured_local": "2026-09-23T11:00:00"}]
    evaluated = [{"id": "sha", "image_sha256": "s1"},
                 {"id": "b"},                                                             # trong acdc_binary_v1
                 {"id": "c", "cache": "khac"},                                            # cùng mã, khác cache gốc
                 {"id": "c2", "cache": "ref_cache", "image_sha256": "s9"},
                 {"id": "snap", "snapshot": "20260923_100000_000", "captured_local": "2026-09-23T15:00:00"},
                 {"id": "gan", "captured_local": "2026-09-23T10:00:45+07:00"},            # múi giờ: đổi về giờ máy
                 {"id": "gan_khung", "captured_local": "2026-09-23T13:00:00", "frame_captured_local": "2026-09-23T11:00:59"},
                 {"id": "xa", "captured_local": "2026-09-23T10:01:01"}]
    import datetime as dt
    local_offset = dt.datetime(2026, 9, 23, 10).astimezone().utcoffset()
    if local_offset != dt.timedelta(hours=7):                                             # máy không ở GMT+7: bỏ mốc có múi giờ
        evaluated[5]["captured_local"] = "2026-09-23T10:00:45"
    result = find_overlap(evaluated, "acdc_binary_v1", reference, "ref_cache", session_gap_s=60.0)
    flagged = {e["id"]: e["matched_by"] for e in result["examples"]}
    assert flagged == {"sha": ["image_sha256"], "b": ["cache_id"], "snap": ["snapshot"], "gan": ["session_gap"],
                       "gan_khung": ["session_gap"]}
    assert result["overlapping_images"] == 5 and result["evaluated_images"] == 8
    assert result["by_check"] == {"image_sha256": 1, "cache_id": 1, "snapshot": 1, "session_gap": 2}
    assert find_overlap([{"id": "c"}], "ref_cache", reference, "ref_cache")["overlapping_images"] == 1
    assert find_overlap(evaluated, "acdc_binary_v1", reference, "ref_cache", max_examples=2)["examples"][1]["id"] == "b"


def _cache_with_shas(root, shas):
    """Cache giả của test huấn luyện, thêm image_sha256 cho từng bản ghi (như cache WoodScape / sa bàn)."""
    from tests.test_perception_training import _make_cache
    manifest_path = _make_cache(root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for record, sha in zip(manifest["records"], shas):
        record["image_sha256"] = sha
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _fake_checkpoint(tmp_path, manifest_path):
    from autopark.perception.dataset import PreparedCache, file_sha256
    from autopark.perception.train import DEFAULTS
    cache = PreparedCache.open(manifest_path)
    state = {"config": {**DEFAULTS, "prepared_manifest": str(manifest_path), "height": 64, "width": 64},
             "epoch": 0, "model": {}, "split_sha256": cache.split_sha256, "mapping_sha256": "test-mapping",
             "manifest_sha256": file_sha256(manifest_path)}
    path = tmp_path / "best.pt"
    torch.save(state, path)
    return path, state


def test_train_overlap_report_is_clean_overlap_or_unverifiable(tmp_path):
    from autopark.perception.evaluate import train_overlap_report
    train_manifest = _cache_with_shas(tmp_path / "cache_a", [f"a{i}" for i in range(24)])   # train 0..15, val 16..19
    _, state = _fake_checkpoint(tmp_path, train_manifest)
    manifest = json.loads(train_manifest.read_text(encoding="utf-8"))
    own_val = [manifest["records"][i] for i in manifest["splits"]["val"]]
    report = train_overlap_report(state, own_val, train_manifest, eval_split="val", cross_domain=False, policy="refuse")
    assert report["status"] == "clean" and report["train_images"] == 16 and "selection_overlap" not in report

    other = _cache_with_shas(tmp_path / "cache_b", ["b0"] * 16 + ["a3", "b17", "a17", "a5"] + ["b"] * 4)
    other_val = [json.loads(other.read_text(encoding="utf-8"))["records"][i] for i in range(16, 20)]
    report = train_overlap_report(state, other_val, other, eval_split="val", cross_domain=True, policy="warn")
    assert report["status"] == "overlap" and report["overlapping_images"] == 2
    assert [e["id"] for e in report["examples"]] == [other_val[0]["id"], other_val[3]["id"]]
    assert report["selection_overlap"]["overlapping_images"] == 1                      # a17 là ảnh val của cache_a
    assert report["train_manifest_sha256"] == state["manifest_sha256"] and report["policy"] == "warn"

    train_manifest.write_text(train_manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")  # cache bị ghi lại
    report = train_overlap_report(state, own_val, train_manifest, eval_split="val", cross_domain=False, policy="refuse")
    assert report["status"] == "unverifiable" and "sha256" in report["reason"]
    missing = {**state, "config": {**state["config"], "prepared_manifest": str(tmp_path / "khong_co" / "manifest.json")}}
    report = train_overlap_report(missing, own_val, train_manifest, eval_split="val", cross_domain=True, policy="refuse")
    assert report["status"] == "unverifiable" and "không thấy" in report["reason"]


def test_evaluate_refuses_or_warns_on_train_overlap_before_it_needs_cuda(tmp_path, monkeypatch, capsys):
    from autopark.perception import evaluate
    monkeypatch.setattr(evaluate.torch.cuda, "is_available", lambda: False)
    train_manifest = _cache_with_shas(tmp_path / "cache_a", [f"a{i}" for i in range(24)])
    checkpoint, _ = _fake_checkpoint(tmp_path, train_manifest)
    base = ["--checkpoint", str(checkpoint), "--split", "val", "--out", str(tmp_path / "out")]
    with pytest.raises(SystemExit, match="CUDA unavailable"):                           # cache của chính nó: sạch, qua chốt
        evaluate.main(base)

    leaked = _cache_with_shas(tmp_path / "cache_b", ["b"] * 16 + ["a0", "b1", "b2", "b3"] + ["b"] * 4)
    with pytest.raises(SystemExit) as refused:
        evaluate.main(base + ["--manifest", str(leaked)])
    message = str(refused.value)
    assert "Từ chối chấm" in message and "TRÙNG" in message and "1/4" in message and "--train-overlap warn" in message
    assert not (tmp_path / "out").exists()
    with pytest.raises(SystemExit, match="CUDA unavailable"):                           # warn: chấm tiếp, có cảnh báo
        evaluate.main(base + ["--manifest", str(leaked), "--train-overlap", "warn"])
    assert "CẢNH BÁO" in capsys.readouterr().err

    clean = _cache_with_shas(tmp_path / "cache_c", [f"c{i}" for i in range(24)])       # chấm chéo không trùng: qua chốt
    with pytest.raises(SystemExit, match="CUDA unavailable"):
        evaluate.main(base + ["--manifest", str(clean)])

    train_manifest.write_text(train_manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(SystemExit, match="KHÔNG KIỂM ĐƯỢC"):                           # manifest huấn luyện đã đổi
        evaluate.main(base + ["--manifest", str(clean)])


def test_evaluate_warn_records_train_overlap_in_metrics_jsonl_and_warns_on_selection_split(tmp_path, monkeypatch,
                                                                                            capsys):
    """Chạy hết main trên CPU (giả CUDA chỉ trong module evaluate, mô hình không tham số): `--train-overlap warn` ghi
    train_overlap vào metrics.json, trạng thái vào test_evaluations.jsonl, và in câu trùng split chọn mô hình."""
    import types
    from autopark.perception import evaluate

    class Net(torch.nn.Module):                         # không tham số: load_state_dict({}) của checkpoint giả vẫn qua
        def forward(self, x):
            red = x[:, :1]
            return {"out": torch.cat([-red, red], 1)}

    class CpuAsCuda:                                    # chỉ evaluate thấy "có CUDA"; tensor vẫn ở CPU
        cuda = types.SimpleNamespace(is_available=lambda: True)
        device = staticmethod(lambda _name: torch.device("cpu"))

        def __getattr__(self, name):
            return getattr(torch, name)

    monkeypatch.setattr(evaluate, "torch", CpuAsCuda())
    monkeypatch.setattr(evaluate, "build_model", lambda num_classes, pretrained=False: Net())
    train_manifest = _cache_with_shas(tmp_path / "cache_a", [f"a{i}" for i in range(24)])   # train 0..15, val 16..19
    checkpoint, _ = _fake_checkpoint(tmp_path, train_manifest)
    leaked = _cache_with_shas(tmp_path / "cache_b", [f"b{i}" for i in range(20)] + ["a1", "a17", "b22", "b23"])
    out = tmp_path / "out_test"
    assert evaluate.main(["--checkpoint", str(checkpoint), "--split", "test", "--final-test", "--out", str(out),
                          "--manifest", str(leaked), "--train-overlap", "warn"]) == 0
    captured = capsys.readouterr()
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    overlap = metrics["train_overlap"]
    assert overlap["status"] == "overlap" and overlap["policy"] == "warn" and overlap["overlapping_images"] == 1
    assert overlap["selection_split"] == "val" and overlap["selection_overlap"]["overlapping_images"] == 1  # a17
    assert metrics["cross_domain"] is True and metrics["images"] == 4
    lines = (tmp_path / "test_evaluations.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["train_overlap"] == "overlap"
    assert "1/4 ảnh chấm" in captured.err and "1 ảnh chấm trùng ảnh split 'val'" in captured.err
    assert "chọn mô hình" in captured.err and captured.out.startswith("[CẢNH BÁO train_overlap = overlap]")

    # Cache của chính nó, chấm test: không trùng train (sạch, không chặn) nhưng một ảnh test trùng ảnh val đã chọn mô hình.
    own = _cache_with_shas(tmp_path / "own" / "cache_e", [f"e{i}" for i in range(20)] + ["e16", "e21", "e22", "e23"])
    own_checkpoint, _ = _fake_checkpoint(tmp_path / "own", own)
    assert evaluate.main(["--checkpoint", str(own_checkpoint), "--split", "test", "--final-test",
                          "--out", str(tmp_path / "own" / "out")]) == 0
    captured = capsys.readouterr()
    metrics = json.loads((tmp_path / "own" / "out" / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["cross_domain"] is False and metrics["train_overlap"]["status"] == "clean"
    assert metrics["train_overlap"]["selection_overlap"]["overlapping_images"] == 1
    assert "1 ảnh chấm trùng ảnh split 'val'" in captured.err and not captured.out.startswith("[CẢNH BÁO")
    line = (tmp_path / "own" / "test_evaluations.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    assert json.loads(line)["train_overlap"] == "clean"


def test_overlap_guard_uses_the_same_session_gap_and_record_fields_as_labels_export(tmp_path):
    """Cache sa bàn thật do labels export ghi: trường image_sha256 / snapshot / captured_local phải đúng tên mà chốt đọc."""
    pytest.importorskip("cv2")
    from datetime import timedelta
    import shutil
    from autopark.perception import labels as L
    from autopark.perception.evaluate import SESSION_GAP_S, find_overlap
    from tests.test_labels import T0, write_snapshot
    assert SESSION_GAP_S == L.SESSION_GAP_S
    shots = tmp_path / "rig_snapshots"
    for k in range(3):
        write_snapshot(shots, T0 + timedelta(hours=k), seed=k)
    train = L.LabelProject(tmp_path / "huan_luyen", create=True)
    train.import_snapshots(shots, log=None)
    for item_id in train.ids("draft"):
        train.set_status(item_id, "reviewed")
    train.export(tmp_path / "sa_ban_v1", log=lambda *_: None)
    cham_src = tmp_path / "cham"
    shutil.copytree(sorted(shots.iterdir())[0], cham_src / sorted(shots.iterdir())[0].name)  # lỡ chép bộ huấn luyện
    write_snapshot(cham_src, T0 + timedelta(hours=1, seconds=40), seed=40)                  # 40 s sau một bộ huấn luyện
    write_snapshot(cham_src, T0 + timedelta(hours=9), seed=41)                              # phiên riêng
    cham = L.LabelProject(tmp_path / "du_an_cham", create=True)
    cham.import_snapshots(cham_src, draft=False, log=None)
    for item_id in cham.ids("draft"):
        label = cham.label(item_id)
        label[:] = L.FREE
        cham.save(item_id, label)
        cham.set_status(item_id, "reviewed")
    cham.export(tmp_path / "sa_ban_cham_v1", ratios=(0, 1, 0), log=lambda *_: None)          # không --disjoint-from
    load = lambda p: json.loads((p / "manifest.json").read_text(encoding="utf-8"))             # noqa: E731
    train_m, cham_m = load(tmp_path / "sa_ban_v1"), load(tmp_path / "sa_ban_cham_v1")
    result = find_overlap([cham_m["records"][i] for i in cham_m["splits"]["val"]], "sa_ban_cham_v1",
                          [train_m["records"][i] for i in train_m["splits"]["train"] + train_m["splits"]["val"]
                           + train_m["splits"]["test"]], "sa_ban_v1")
    assert result["overlapping_images"] == 4 and result["evaluated_images"] == 6
    assert result["by_check"]["image_sha256"] == 2 and result["by_check"]["snapshot"] == 2
    assert result["by_check"]["session_gap"] == 4 and result["by_check"]["cache_id"] == 0


# ---------------------------------------------------------------- chốt theo phân nhóm của export (sửa tối 24/09/2026)
def _sa_ban_checkpoint(folder, manifest_path):
    """Checkpoint giả cho cache sa bàn do labels export ghi (384×512, mapping của chính cache), lưu ở folder/best.pt."""
    from autopark.perception.dataset import PreparedCache, file_sha256
    from autopark.perception.train import DEFAULTS
    cache = PreparedCache.open(manifest_path)
    state = {"config": {**DEFAULTS, "prepared_manifest": str(manifest_path), "height": 384, "width": 512},
             "epoch": 0, "model": {}, "split_sha256": cache.split_sha256,
             "mapping_sha256": cache.manifest["mapping_sha256"], "manifest_sha256": file_sha256(manifest_path)}
    folder.mkdir(parents=True, exist_ok=True)
    torch.save(state, folder / "best.pt")
    return folder / "best.pt", state


def _split_records(manifest_path, name):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [manifest["records"][i] for i in manifest["splits"][name]]


def test_find_overlap_own_cache_checks_use_the_group_and_skip_snapshot_and_time():
    from autopark.perception.evaluate import OWN_CACHE_CHECKS, find_overlap
    reference = [{"id": "t1", "group": "g1", "snapshot": "S", "captured_local": "2026-09-23T10:00:00",
                  "image_sha256": "s1"},
                 {"id": "t2", "group": 0}]
    evaluated = [{"id": "cung_nhom", "group": "g1"},
                 {"id": "nhom_so_0", "group": 0},                                    # nhóm 0 (số) vẫn là một nhóm
                 {"id": "cung_bo_anh", "group": "g2", "snapshot": "S", "captured_local": "2026-09-23T10:00:05"},
                 {"id": "chep", "group": "g3", "image_sha256": "s1"},
                 {"id": "t2", "group": "g4"}]                                        # cùng mã ảnh, cùng cache
    own = find_overlap(evaluated, "c", reference, "c", checks=OWN_CACHE_CHECKS)
    assert {e["id"]: e["matched_by"] for e in own["examples"]} == {
        "cung_nhom": ["group"], "nhom_so_0": ["group"], "chep": ["image_sha256"], "t2": ["cache_id"]}
    assert own["by_check"] == {"image_sha256": 1, "cache_id": 1, "group": 2}
    cross = find_overlap(evaluated, "c", reference, "c")                    # mặc định (chấm chéo): không so nhóm
    assert {e["id"]: e["matched_by"] for e in cross["examples"]} == {
        "cung_bo_anh": ["snapshot", "session_gap"], "chep": ["image_sha256"], "t2": ["cache_id"]}
    assert "group" not in cross["by_check"]
    with pytest.raises(ValueError, match="khong_co"):
        find_overlap(evaluated, "c", reference, "c", checks=("image_sha256", "khong_co"))


def test_own_cache_guard_follows_the_session_gap_the_cache_was_split_with(tmp_path, monkeypatch):
    """Cache sa bàn chia với `labels export --session-gap 30`, bộ ảnh cách nhau 45 s: mỗi bộ một phiên, val/test là
    ảnh chưa học. Chốt không so lại với 60 s cố định (bản đầu từ chối val/test, báo 'trùng ảnh train')."""
    from datetime import timedelta
    from autopark.perception import evaluate, labels as L
    from tests.test_labels import QUIET, T0, review_all, write_snapshot
    for k in range(8):
        write_snapshot(tmp_path / "snaps", T0 + timedelta(seconds=45 * k), seed=k)
    project = L.LabelProject(tmp_path / "du_an", create=True)
    project.import_snapshots(tmp_path / "snaps", log=None)
    review_all(project)
    project.export(tmp_path / "sa_ban_v1", session_gap_s=30.0, log=QUIET)
    manifest_path = tmp_path / "sa_ban_v1" / "manifest.json"
    grouping = json.loads(manifest_path.read_text(encoding="utf-8"))["grouping"]
    assert grouping["sessions"] == 8 and grouping["session_gap_s"] == 30.0
    checkpoint, state = _sa_ban_checkpoint(tmp_path / "ck", manifest_path)
    train = _split_records(manifest_path, "train")
    fixed_60s = 0
    for split in ("val", "test"):
        evaluated = _split_records(manifest_path, split)
        assert evaluated
        report = evaluate.train_overlap_report(state, evaluated, manifest_path, eval_split=split, cross_domain=False,
                                               policy="refuse")
        assert report["status"] == "clean", report
        assert report["checks"] == list(evaluate.OWN_CACHE_CHECKS) and report["session_gap_s"] is None
        assert not report.get("selection_overlap", {}).get("overlapping_images")
        fixed_60s += evaluate.find_overlap(evaluated, "sa_ban_v1", train, "sa_ban_v1")["overlapping_images"]
    assert fixed_60s > 0                          # đúng tình huống mà phép so 60 s cố định (bản đầu) từ chối nhầm
    monkeypatch.setattr(evaluate.torch.cuda, "is_available", lambda: False)
    with pytest.raises(SystemExit, match="CUDA unavailable"):                           # qua chốt, không bị từ chối
        evaluate.main(["--checkpoint", str(checkpoint), "--split", "val", "--out", str(tmp_path / "out")])

    # Phép so với split chọn mô hình (chấm test) cũng theo phân nhóm: tìm một cách chia có bộ ảnh test cách bộ ảnh val
    # 45 s (khác phiên theo 30 s) — không được cảnh báo "trùng ảnh val đã chọn mô hình".
    for seed in range(40):
        manifest_path = tmp_path / f"chia_{seed}" / "manifest.json"
        project.export(manifest_path.parent, seed=seed, session_gap_s=30.0, resplit=True, log=QUIET)
        test, val = _split_records(manifest_path, "test"), _split_records(manifest_path, "val")
        if evaluate.find_overlap(test, "x", val, "x")["by_check"]["session_gap"]:
            break
    else:
        pytest.fail("không seed nào đặt bộ ảnh test cạnh bộ ảnh val")
    _, state = _sa_ban_checkpoint(tmp_path / f"ck_chia_{seed}", manifest_path)
    report = evaluate.train_overlap_report(state, test, manifest_path, eval_split="test", cross_domain=False,
                                           policy="refuse")
    assert report["status"] == "clean" and report["selection_split"] == "val"
    assert report["selection_overlap"]["overlapping_images"] == 0, report


def test_own_cache_guard_accepts_a_reviewed_stale_frame_that_export_put_in_another_split(tmp_path):
    """Khung cũ (camera treo) đã duyệt được export xếp phiên theo GIỜ KHUNG, nên có thể nằm khác split với camera cùng
    bộ ảnh — cố ý, không phải rò rỉ. Chấm val/test của chính cache đó không bị từ chối, theo cả hai chiều. Chấm chéo
    (coi cache đó là cache khác) thì vẫn chặt như `export --disjoint-from`: cùng tên bộ ảnh là trùng."""
    from datetime import timedelta
    from autopark.perception import evaluate, labels as L
    from tests.test_labels import QUIET, T0, review_all, set_camera_meta, write_snapshot
    shots = tmp_path / "snaps"
    write_snapshot(shots, T0, seed=1)
    s3 = write_snapshot(shots, T0 + timedelta(minutes=30), seed=3)
    set_camera_meta(s3, 1, age_ms=1.79e6, stale=True)                    # giờ khung 10:00:10: chung phiên với bộ T0
    for k in range(1, 6):
        write_snapshot(shots, T0 + timedelta(hours=k), seed=10 + k)
    project = L.LabelProject(tmp_path / "du_an", create=True)
    project.import_snapshots(shots, log=None)
    stale_id, sibling_id = f"{s3.name}_p1", f"{s3.name}_p2"
    project.set_status(stale_id, "reviewed", override_damage=True)
    review_all(project)
    seen = set()
    for seed in range(60):
        out = tmp_path / f"cache_{seed}"
        project.export(out, seed=seed, resplit=True, log=QUIET)
        manifest_path = out / "manifest.json"
        split = {r["id"]: r["split"] for r in json.loads(manifest_path.read_text(encoding="utf-8"))["records"]}
        pair = (split[stale_id], split[sibling_id])
        if pair[0] == pair[1] or "train" not in pair:
            continue
        direction = "khung_cu_ngoai_train" if pair[1] == "train" else "khung_cu_trong_train"
        if direction in seen:
            continue
        seen.add(direction)
        evaluated_split = pair[0] if pair[1] == "train" else pair[1]
        _, state = _sa_ban_checkpoint(tmp_path / f"ck_{seed}", manifest_path)
        evaluated = _split_records(manifest_path, evaluated_split)
        own = evaluate.train_overlap_report(state, evaluated, manifest_path, eval_split=evaluated_split,
                                            cross_domain=False, policy="refuse")
        assert own["status"] == "clean", (direction, own)
        cross = evaluate.train_overlap_report(state, evaluated, manifest_path, eval_split=evaluated_split,
                                              cross_domain=True, policy="refuse")
        assert cross["status"] == "overlap" and cross["by_check"]["snapshot"] >= 1, (direction, cross)
        if len(seen) == 2:
            break
    assert seen == {"khung_cu_ngoai_train", "khung_cu_trong_train"}, seen


def test_cross_cache_session_gap_comes_from_disjoint_from_then_from_the_training_cache(tmp_path, monkeypatch):
    """Chấm cache sa bàn KHÁC: khoảng phiên là của `export --disjoint-from` khi cache chấm đã được tách rời khỏi đúng
    cache huấn luyện này; không thì của cache huấn luyện (`grouping.session_gap_s`). Khoảng phiên riêng của cache chấm
    (export --session-gap 10 mà quên --disjoint-from) không nới được chốt."""
    from datetime import datetime, timedelta
    from autopark.perception import evaluate, labels as L
    from tests.test_labels import QUIET, T0, review_all, write_snapshot
    for k in range(3):
        write_snapshot(tmp_path / "tr", T0 + timedelta(hours=k), seed=k)
    train = L.LabelProject(tmp_path / "du_an_train", create=True)
    train.import_snapshots(tmp_path / "tr", log=None)
    review_all(train)
    train.export(tmp_path / "sa_ban_v1", log=QUIET)                                     # khoảng phiên mặc định 60 s
    m60 = tmp_path / "sa_ban_v1" / "manifest.json"
    checkpoint, state = _sa_ban_checkpoint(tmp_path / "ck60", m60)
    trained_at = datetime.fromisoformat(_split_records(m60, "train")[0]["captured_local"])
    write_snapshot(tmp_path / "ch", trained_at + timedelta(seconds=45), seed=40)      # 45 s sau một bộ ảnh train
    cham = L.LabelProject(tmp_path / "du_an_cham", create=True)
    cham.import_snapshots(tmp_path / "ch", log=None)
    review_all(cham)
    cham.export(tmp_path / "cham30", session_gap_s=30.0, ratios=(0, 1, 0), disjoint_from=[m60], log=QUIET)
    cham.export(tmp_path / "cham10", session_gap_s=10.0, ratios=(0, 1, 0), resplit=True, log=QUIET)
    c30, c10 = tmp_path / "cham30" / "manifest.json", tmp_path / "cham10" / "manifest.json"

    def report(st, manifest_path):
        return evaluate.train_overlap_report(st, _split_records(manifest_path, "val"), manifest_path, eval_split="val",
                                             cross_domain=True, policy="refuse")

    r = report(state, c30)
    assert r["status"] == "clean" and r["session_gap_s"] == 30.0 and "disjoint_from" in r["session_gap_source"], r
    r = report(state, c10)
    assert r["status"] == "overlap" and r["by_check"]["session_gap"] == 2 and r["session_gap_s"] == 60.0, r
    assert "grouping" in r["session_gap_source"] and r["checks"] == list(evaluate.OVERLAP_CHECKS)
    monkeypatch.setattr(evaluate.torch.cuda, "is_available", lambda: False)
    base = ["--checkpoint", str(checkpoint), "--split", "val", "--out", str(tmp_path / "out")]
    with pytest.raises(SystemExit, match="CUDA unavailable"):
        evaluate.main(base + ["--manifest", str(c30)])
    with pytest.raises(SystemExit, match="Từ chối chấm"):
        evaluate.main(base + ["--manifest", str(c10)])

    train.export(tmp_path / "sa_ban_v2", session_gap_s=30.0, resplit=True, log=QUIET)  # cache huấn luyện chia với 30 s
    m30 = tmp_path / "sa_ban_v2" / "manifest.json"
    assert trained_at in [datetime.fromisoformat(x["captured_local"]) for x in _split_records(m30, "train")]
    _, state30 = _sa_ban_checkpoint(tmp_path / "ck30", m30)
    r = report(state30, c10)
    assert r["status"] == "clean" and r["session_gap_s"] == 30.0 and "grouping" in r["session_gap_source"], r
    r = report(state30, c30)                                     # disjoint_from của c30 là của sa_ban_v1, không phải v2
    assert r["status"] == "clean" and "grouping" in r["session_gap_source"]


def test_cross_cache_session_gap_falls_back_to_60_s_and_ignores_bad_values():
    from autopark.perception.evaluate import SESSION_GAP_S, cross_cache_session_gap
    sha = "a" * 64
    for train in ({}, {"grouping": {"note": "split chính thức của ACDC"}}, {"grouping": "không phải dict"},
                  {"grouping": {"session_gap_s": True}}, {"grouping": {"session_gap_s": -1}},
                  {"grouping": {"session_gap_s": float("nan")}}, {"grouping": {"session_gap_s": "30"}}):
        gap, source = cross_cache_session_gap(train, sha, {})
        assert gap == SESSION_GAP_S and "mặc định" in source, train
    assert cross_cache_session_gap({"grouping": {"session_gap_s": 0}}, sha, {})[0] == 0.0
    grouped = {"grouping": {"session_gap_s": 45}}
    for eval_manifest, expected in (({"disjoint_from": [{"manifest_sha256": "b" * 64, "session_gap_s": 5}]}, 45.0),
                                    ({"disjoint_from": [{"manifest_sha256": sha, "session_gap_s": 5}]}, 5.0),
                                    ({"disjoint_from": [{"manifest_sha256": sha, "session_gap_s": None}]}, 45.0),
                                    ({"disjoint_from": ["không phải dict"]}, 45.0), ({"disjoint_from": None}, 45.0)):
        assert cross_cache_session_gap(grouped, sha, eval_manifest)[0] == expected, eval_manifest


REAL_PREPARED = PROJECT_ROOT / "datasets" / "prepared"


@pytest.mark.skipif(not all((REAL_PREPARED / n / "manifest.json").exists() for n in
                            ("woodscape_binary_v1", "ws_avm_v1", "ws_avm_acdc_v1", "acdc_binary_v1")),
                    reason="cần các cache thật trong datasets/prepared (không có trong repo)")
def test_find_overlap_on_the_real_caches():
    """Trên manifest thật (máy bàn, 24/09/2026): cache ghép chứa đúng ảnh train của cache con, val không lẫn train."""
    from autopark.perception.evaluate import find_overlap

    def records(name, split):
        manifest = json.loads((REAL_PREPARED / name / "manifest.json").read_text(encoding="utf-8"))
        return [manifest["records"][i] for i in manifest["splits"][split]]

    ws_train = records("woodscape_binary_v1", "train")
    both = find_overlap(records("ws_avm_v1", "train"), "ws_avm_v1", ws_train, "woodscape_binary_v1")
    assert both["overlapping_images"] == len(ws_train)
    assert both["by_check"]["image_sha256"] == both["by_check"]["cache_id"] == len(ws_train)
    acdc_train = records("acdc_binary_v1", "train")                                         # ACDC không ghi sha256
    acdc = find_overlap(acdc_train, "acdc_binary_v1", records("ws_avm_acdc_v1", "train"), "ws_avm_acdc_v1")
    assert acdc["overlapping_images"] == len(acdc_train) and acdc["by_check"]["image_sha256"] == 0
    for name, split in (("woodscape_binary_v1", "val"), ("woodscape_binary_v1", "test"), ("acdc_binary_v1", "val")):
        clean = find_overlap(records(name, split), name, records("ws_avm_acdc_v1", "train"), "ws_avm_acdc_v1")
        assert clean["overlapping_images"] == 0, (name, split)
