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
