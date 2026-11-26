"""RoadAnomaly21 (SegmentMeIfYouCan AnomalyTrack) trong evaluate_external: bộ nạp, ánh xạ nhãn, số đo chỉ trên vật bất
thường, chặn định dạng lạ. Chạy trên dữ liệu tổng hợp với `predict` giả (không cần CUDA, checkpoint); thêm một test đọc
bản thật trong datasets/training/road_anomaly nếu máy có (thư mục đó không vào git)."""
import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("torch")
cv2 = pytest.importorskip("cv2")

from autopark.perception import evaluate_external as E  # noqa: E402
from tests.conftest import PROJECT_ROOT  # noqa: E402

H, W = 36, 64


def _write(path, array, ext=".png"):
    ok, buffer = cv2.imencode(ext, array)            # imwrite hỏng trên đường dẫn tiếng Việt ở Windows
    assert ok
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.tobytes())


def _label(seed):
    """Vật bất thường (1) là một khối ở giữa, viền void (255) quanh nó, còn lại nền (0) — như nhãn SMIYC."""
    rng = np.random.default_rng(seed)
    label = np.zeros((H, W), np.uint8)
    y0, x0 = int(rng.integers(4, 12)), int(rng.integers(8, 30))
    label[y0 - 2:y0 + 14, x0 - 2:x0 + 22] = 255
    label[y0:y0 + 12, x0:x0 + 20] = 1
    return label


def _anomaly_track(root, n=3, unlabelled=("cow0000.jpg", "sheep0003.jpg")):
    labels = {}
    for i in range(n):
        stem = f"validation{i:04d}"
        labels[stem] = _label(i)
        _write(root / "labels_masks" / f"{stem}_labels_semantic.png", labels[stem])
        colour = np.where(labels[stem][..., None] == 1, (0, 102, 255), (255, 255, 255)).astype(np.uint8)
        _write(root / "labels_masks" / f"{stem}_labels_semantic_color.png", colour)     # phải bị bỏ qua
        _write(root / "images" / f"{stem}.jpg", np.random.default_rng(10 + i).integers(0, 256, (H, W, 3), np.uint8),
               ".jpg")
    for name in unlabelled:
        _write(root / "images" / name, np.zeros((H, W, 3), np.uint8), ".jpg")
    _write(root / "labels_masks" / "khong_anh_labels_semantic.png", _label(9))           # nhãn không có ảnh: bỏ
    return labels


def _left_half_predictor(image):
    """BLOCKED ở nửa trái, P(BLOCKED) = 0,9 ở đó và 0,1 ở nửa phải."""
    prob = np.full(image.shape[:2], 0.1, np.float32)
    prob[:, : image.shape[1] // 2] = 0.9
    return (prob >= 0.5).astype(np.uint8), prob


def test_road_anomaly_items_pairs_labels_with_jpg_images_and_counts_unlabelled(tmp_path):
    root = tmp_path / "dữ liệu" / "dataset_AnomalyTrack"                                 # đường dẫn tiếng Việt
    _anomaly_track(root)
    items = E.road_anomaly_items(root)
    assert [it["id"] for it in items] == ["validation0000", "validation0001", "validation0002"]
    assert all(it["image"].suffix == ".jpg" and it["invalid"] is None for it in items)
    assert E.road_anomaly_unlabelled(root, items) == ["cow0000.jpg", "sheep0003.jpg"]
    raw, invalid = E._ground_truth(items[0])                                            # đọc được trên đường dẫn Unicode
    assert invalid is None and set(np.unique(raw).tolist()) == {0, 1, 255}
    with pytest.raises(SystemExit, match="CHƯA CHẤM"):
        E.road_anomaly_items(tmp_path / "khong_co")


def test_only_anomaly_pixels_are_scored_and_background_is_never_free_truth(tmp_path):
    root = tmp_path / "dataset_AnomalyTrack"
    labels = _anomaly_track(root)
    items = E.road_anomaly_items(root)
    lut = E.road_anomaly_lut()
    assert lut[0] == 255 and lut[1] == 1 and lut[255] == 255                            # nền KHÔNG là FREE
    body, rows = E.evaluate_items("road_anomaly", items, _left_half_predictor, lut, progress=None)

    left = np.zeros((H, W), bool)
    left[:, : W // 2] = True
    anomaly = sum(int((lab == 1).sum()) for lab in labels.values())
    hit = sum(int(((lab == 1) & left).sum()) for lab in labels.values())
    background = sum(int((lab == 0).sum()) for lab in labels.values())
    background_blocked = sum(int(((lab == 0) & left).sum()) for lab in labels.values())
    overall = body["overall"]
    assert overall["valid_pixels"] == anomaly                                           # chỉ pixel vật bất thường
    assert overall["confusion_matrix"][0] == [0, 0]
    assert overall["blocked_recall"] == pytest.approx(hit / anomaly)
    assert overall["blocked_as_free_rate"] == pytest.approx(1 - hit / anomaly)
    assert overall["mIoU"] is None and overall["iou_blocked"] is None and overall["blocked_precision"] is None
    report = body["anomaly"]
    assert report["anomaly_pixels"] == anomaly and report["anomaly_recall"] == pytest.approx(hit / anomaly)
    assert report["background_pixels"] == background
    assert report["background_predicted_blocked_rate"] == pytest.approx(background_blocked / background)
    assert report["anomaly_recall_by_threshold"]["0.50"] == pytest.approx(hit / anomaly)
    assert report["anomaly_recall_by_threshold"]["0.95"] == 0.0                         # P tối đa 0,9
    assert body["score_curves_blocked_probability"]["negatives"] == 0
    assert body["score_curves_blocked_probability"]["average_precision"] is None
    assert body["label_values_seen"] == [0, 1, 255] and body["images"] == 3
    assert body["anomaly_images"]["with_obstacle_pixels"] == 3
    assert [r["iou_free"] for r in rows] == [None] * 3
    for row, lab in zip(rows, labels.values()):
        assert row["blocked_pixels"] == int((lab == 1).sum())


def test_unknown_label_values_stop_the_scoring(tmp_path):
    root = tmp_path / "dataset_AnomalyTrack"
    _anomaly_track(root, n=1, unlabelled=())
    odd = _label(0)
    odd[0, 0] = 2                                                                       # định dạng khác tài liệu SMIYC
    _write(root / "labels_masks" / "validation0000_labels_semantic.png", odd)
    with pytest.raises(ValueError, match="ngoài"):
        E.evaluate_items("road_anomaly", E.road_anomaly_items(root), _left_half_predictor, E.road_anomaly_lut(),
                         progress=None)


def test_anomaly_summary_refuses_free_truth_and_recall_by_threshold_matches_brute_force():
    with pytest.raises(ValueError):
        E.anomaly_summary(np.array([[1, 0], [2, 3]]))
    rng = np.random.default_rng(1)
    prob = rng.random(20000).astype(np.float32)
    hist = np.bincount(np.minimum((prob * E.HIST_BINS).astype(np.int64), E.HIST_BINS - 1), minlength=E.HIST_BINS)
    by_threshold = E.recall_by_threshold(hist)
    assert set(by_threshold) == {f"{t:.2f}" for t in E.RECALL_THRESHOLDS}
    for t in (0.15, 0.5, 0.85):
        assert by_threshold[f"{t:.2f}"] == pytest.approx(float((prob >= t).mean()), abs=1e-4)
    assert E.recall_by_threshold(np.zeros(E.HIST_BINS, np.int64))["0.50"] is None


def test_other_datasets_keep_their_summary(tmp_path):
    """RoadObstacle21 vẫn dùng metrics.summarize (có mIoU) và không có khối 'anomaly'."""
    root = tmp_path / "dataset_AnomalyTrack"
    labels = _anomaly_track(root, n=1, unlabelled=())
    items = E.road_anomaly_items(root)
    lut = np.full(256, 255, np.uint8)
    lut[0], lut[1] = 0, 1
    body, _ = E.evaluate_items("road_obstacle", items, _left_half_predictor, lut, progress=None)
    assert body["overall"]["mIoU"] is not None and "anomaly" not in body and "obstacle_images" in body
    assert body["overall"]["valid_pixels"] == int((labels["validation0000"] != 255).sum())
    with pytest.raises(ValueError):
        E.evaluate_items("khong_co", items, _left_half_predictor, lut)


def test_cli_without_data_says_not_scored_before_looking_for_cuda(tmp_path, monkeypatch):
    monkeypatch.setattr(E.torch.cuda, "is_available", lambda: False)
    with pytest.raises(SystemExit, match="CHƯA CHẤM"):
        E.main(["--checkpoint", str(tmp_path / "best.pt"), "--dataset", "road_anomaly", "--out", str(tmp_path / "o"),
                "--road-anomaly-root", str(tmp_path / "khong_co")])
    root = tmp_path / "dataset_AnomalyTrack"
    _anomaly_track(root, n=1)
    with pytest.raises(SystemExit, match="CUDA unavailable"):                           # có dữ liệu: tới bước cần GPU
        E.main(["--checkpoint", str(tmp_path / "best.pt"), "--dataset", "road_anomaly", "--out", str(tmp_path / "o"),
                "--road-anomaly-root", str(root)])


REAL_ROOT = PROJECT_ROOT / "datasets" / "training" / "road_anomaly" / "dataset_AnomalyTrack"


@pytest.mark.skipif(not (REAL_ROOT / "labels_masks").is_dir(),
                    reason="cần bản RoadAnomaly21 đã giải nén trong datasets/training (không có trong repo)")
def test_real_road_anomaly21_copy_matches_the_documented_format():
    """Bản trong máy (kiểm 24/09/2026): 10 ảnh validation có nhãn 1280×720 giá trị {0, 1, 255}, 100 ảnh không nhãn.
    Chấm bằng predict giả 'mọi pixel BLOCKED': recall phải đúng 1 và nền gọi BLOCKED 100 % — chỉ kiểm đường nạp/đếm."""
    items = E.road_anomaly_items(REAL_ROOT)
    assert len(items) == 10 and len(E.road_anomaly_unlabelled(REAL_ROOT, items)) == 100

    def everything_blocked(image):
        return np.ones(image.shape[:2], np.uint8), np.ones(image.shape[:2], np.float32)

    body, rows = E.evaluate_items("road_anomaly", items, everything_blocked, E.road_anomaly_lut(), progress=None)
    assert body["label_values_seen"] == [0, 1, 255]
    assert body["anomaly"]["anomaly_recall"] == 1.0 and body["anomaly"]["background_predicted_blocked_rate"] == 1.0
    assert body["anomaly_images"]["with_obstacle_pixels"] == 10 and body["anomaly_images"]["fully_missed"] == 0
    assert all(r["valid_pixels"] > 0 for r in rows)
