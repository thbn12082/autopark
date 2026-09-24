r"""Evaluate a WoodScape checkpoint on data it was never trained on: ACDC, RoadObstacle21 and RoadAnomaly21.

    .venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/<run>/best.pt --dataset acdc --split val --out <dir>
    .venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/<run>/best.pt --dataset road_obstacle --out <dir>
    .venv-train\Scripts\python.exe -X utf8 -m autopark.perception.evaluate_external --checkpoint runs/<run>/best.pt --dataset road_anomaly --out <dir>

Images go through exactly the deployment path of predict.py (letterbox to the training size, un-letterbox,
resize back), and metrics are computed at the ORIGINAL label resolution. ACDC ground truth is Cityscapes
labelIds mapped with configs/acdc_cityscapes_to_binary_v1.json; pixels flagged invalid by ACDC are IGNORE.
Because BLOCKED on ACDC is dominated by vegetation and buildings, metrics are also broken down per source
class and per class group, so "obstacle -> FREE" can be read for people and vehicles separately.
RoadObstacle21 labels are already 0 = road, 1 = obstacle, 255 = outside the road, so only the road surface
is scored there. Both datasets differ from WoodScape in lens (pinhole), aspect ratio (16:9), country and
conditions: the numbers measure domain shift, not the model's in-distribution accuracy.

RoadAnomaly21 (SegmentMeIfYouCan, nhánh AnomalyTrack; thêm 24/09/2026): nhãn `labels_masks/<mã>_labels_semantic.png`
là 0 = KHÔNG phải vật bất thường (mọi thứ còn lại: đường, nhà, cây, trời, xe khác), 1 = vật bất thường, 255 = void.
Nhãn 0 KHÔNG phải FREE với mô hình này (nhà, cây đúng là BLOCKED), nên chỉ pixel vật bất thường được chấm: recall
BLOCKED trên vật bất thường và tỉ lệ vật bất thường bị gọi FREE (lỗi nguy hiểm). mIoU, IoU, precision, báo động giả
không định nghĩa được (không có pixel FREE thật nào) nên ghi None. Tỉ lệ pixel nền bị gọi BLOCKED chỉ để tham khảo,
KHÔNG phải tỉ lệ báo động giả. Các chỉ số chính thức của SMIYC (AP, FPR95, sIoU/PPV/F1 theo thành phần) cần một điểm
bất thường theo pixel; mô hình chỉ cho P(BLOCKED), nên không tính và số ở đây không so được với bảng xếp hạng SMIYC.
Chỉ ảnh validation có nhãn công khai; ảnh test (không có nhãn công khai) được đếm, không chấm. Định dạng đã kiểm trên
bản trong máy ngày 24/09/2026 (`datasets/training/road_anomaly/dataset_AnomalyTrack`: 10 nhãn 1280×720, giá trị
{0, 1, 255}, 100 ảnh không nhãn); lúc chấm, nhãn có giá trị ngoài {0, 1, 255} thì dừng, không chấm sai định dạng.
"""
import argparse
import csv
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import torch

from .checkpoint import atomic_write_json, load_checkpoint
from .data import read_image
from .dataset import file_sha256
from .evaluate import panel
from .metrics import summarize
from .model import build_model
from .predict import predict_image
from .train import PROJECT, utc_now

CONDITIONS = ("fog", "night", "rain", "snow")
HIST_BINS = 1000
DATASETS = ("acdc", "road_obstacle", "road_anomaly")
ROAD_ANOMALY_IMAGE_SUFFIXES = (".jpg", ".png", ".webp")
ROAD_ANOMALY_VALUES = (0, 1, 255)             # định dạng SMIYC; giá trị khác thì dừng, không chấm
RECALL_THRESHOLDS = tuple(round(0.05 * i, 2) for i in range(1, 20))
CITYSCAPES_GROUPS = {
    "road_and_parking": (7, 9), "vehicles": (26, 27, 28, 29, 30, 31), "two_wheelers": (32, 33),
    "persons_and_riders": (24, 25), "structures": (11, 12, 13, 14, 15, 16), "poles_and_signs": (17, 18, 19, 20),
    "vegetation": (21,),
}


def acdc_items(root: Path, split: str) -> list[dict]:
    """(image, labelIds, invIds or None, condition) for one ACDC split; *_ref splits have no invalid masks."""
    ref = split.endswith("_ref")
    rgb_suffix = "_rgb_ref_anon.png" if ref else "_rgb_anon.png"
    gt_root, gt_suffix = ("gt_ref/gt", "_gt_ref_labelIds.png") if ref else ("gt/gt", "_gt_labelIds.png")
    items = []
    for condition in CONDITIONS:
        for image in sorted((root / "rgb/rgb_anon" / condition / split).glob(f"*/*{rgb_suffix}")):
            label = root / gt_root / condition / split / image.parent.name / (image.name[:-len(rgb_suffix)] + gt_suffix)
            if not label.exists():
                continue                      # only part of the *_ref splits is annotated
            invalid = None if ref else label.with_name(label.name.replace("_gt_labelIds.png", "_gt_invIds.png"))
            items.append({"id": f"{condition}/{image.parent.name}/{image.stem}", "condition": condition,
                          "image": image, "label": label, "invalid": invalid})
    if not items:
        raise SystemExit(f"No annotated ACDC images for split {split!r} under {root}")
    return items


def road_obstacle_items(root: Path) -> list[dict]:
    items = []
    for label in sorted((root / "labels_masks").glob("*_labels_semantic.png")):
        stem = label.name[:-len("_labels_semantic.png")]
        image = root / "images" / f"{stem}.webp"
        if image.exists():
            items.append({"id": stem, "condition": "validation", "image": image, "label": label, "invalid": None})
    if not items:
        raise SystemExit(f"No labelled RoadObstacle21 images under {root}")
    return items


def road_anomaly_items(root: Path) -> list[dict]:
    """Ảnh RoadAnomaly21 CÓ NHÃN: `labels_masks/<mã>_labels_semantic.png` + `images/<mã>.<jpg|png|webp>`.

    Bản trong máy (kiểm 24/09/2026) có ảnh `.jpg`; `.png`/`.webp` là đuôi dự phòng, CHƯA gặp trên dữ liệu thật. Nhãn
    không có ảnh đi kèm thì bỏ (như RoadObstacle21). Không có ảnh có nhãn nào thì dừng: "chưa chấm", không ra số 0."""
    items = []
    for label in sorted((root / "labels_masks").glob("*_labels_semantic.png")):
        stem = label.name[:-len("_labels_semantic.png")]
        image = next((p for p in (root / "images" / f"{stem}{s}" for s in ROAD_ANOMALY_IMAGE_SUFFIXES) if p.exists()),
                     None)
        if image is not None:
            items.append({"id": stem, "condition": "validation", "image": image, "label": label, "invalid": None})
    if not items:
        raise SystemExit(f"CHƯA CHẤM RoadAnomaly21 — không có ảnh có nhãn dưới {root} (cần labels_masks/"
                         "<mã>_labels_semantic.png và images/<mã>.jpg của SegmentMeIfYouCan AnomalyTrack)")
    return items


def road_anomaly_unlabelled(root: Path, items: list[dict]) -> list[str]:
    """Ảnh trong `images/` không có nhãn (tập test SMIYC, nhãn không công bố): chỉ đếm, không chấm."""
    labelled = {Path(item["image"]).name for item in items}
    folder = root / "images"
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir()
                  if p.suffix.lower() in ROAD_ANOMALY_IMAGE_SUFFIXES and p.name not in labelled)


def road_anomaly_lut() -> np.ndarray:
    """1 (vật bất thường) -> BLOCKED; 0 (nền: đường, nhà, cây, trời...) và 255 (void) -> IGNORE."""
    lut = np.full(256, 255, np.uint8)
    lut[1] = 1
    return lut


def _keys(section) -> set[int]:
    keys = set()
    for key in section:
        if not str(key).isdigit() or not 0 <= int(key) <= 255:
            raise ValueError(f"Label id {key!r} is not an integer in 0..255")
        keys.add(int(key))
    return keys


def build_lut(mapping: dict) -> np.ndarray:
    """256-entry lookup from source label id to {0, 1, 255}; the three class lists must not overlap."""
    free, blocked, ignore = _keys(mapping["free"]), _keys(mapping["blocked"]), _keys(mapping.get("ignore", {}))
    if free & blocked or free & ignore or blocked & ignore:
        raise ValueError(f"Overlapping label ids in mapping: {sorted((free & blocked) | (free & ignore) | (blocked & ignore))}")
    lut = np.full(256, 255, np.uint8)
    lut[list(free)] = 0
    lut[list(blocked)] = 1
    return lut


def variant_luts(mapping: dict, base: np.ndarray) -> dict[str, np.ndarray]:
    variants = {}
    for name, overrides in mapping.get("variants", {}).items():
        lut = base.copy()
        for key, value in overrides.items():
            if not str(key).isdigit():
                continue                      # free-text notes live next to the overrides
            if int(value) not in (0, 1, 255):
                raise ValueError(f"Variant {name!r}: override {key} -> {value!r} is not 0, 1 or 255")
            lut[int(key)] = int(value)
        variants[name] = lut
    return variants


def confusion(pred: np.ndarray, truth: np.ndarray) -> np.ndarray:
    valid = truth != 255
    return np.bincount(truth[valid].astype(np.int64) * 2 + pred[valid], minlength=4).reshape(2, 2)


def per_source_class(raw: np.ndarray, truth: np.ndarray, pred: np.ndarray) -> np.ndarray:
    """(256, 2) counts of prediction per original label id, over scored pixels only."""
    valid = truth != 255
    return np.bincount(raw[valid].astype(np.int64) * 2 + pred[valid], minlength=512).reshape(256, 2)


def source_class_report(counts: np.ndarray, lut: np.ndarray, names: dict) -> dict:
    per_class, groups = {}, {}
    for label_id in np.flatnonzero(counts.sum(1)):
        total = int(counts[label_id].sum())
        as_blocked = int(counts[label_id, 1])
        per_class[str(label_id)] = {"name": names.get(str(label_id), "?"), "mapped_to": int(lut[label_id]),
                                    "pixels": total, "predicted_blocked_rate": as_blocked / total}
    for group, ids in CITYSCAPES_GROUPS.items():
        total = int(counts[list(ids)].sum())
        if total:
            groups[group] = {"pixels": total, "predicted_blocked_rate": int(counts[list(ids), 1].sum()) / total,
                             "share_of_scored_pixels": total / int(counts.sum())}
    return {"per_class": per_class, "groups": groups,
            "note": "predicted_blocked_rate is recall for BLOCKED classes and the false-alarm rate for FREE classes"}


def score_curves(pos_hist: np.ndarray, neg_hist: np.ndarray) -> dict:
    """Pixel-level AP, AUROC and FPR at 95 % TPR from score histograms (positives = BLOCKED truth)."""
    pos_total, neg_total = int(pos_hist.sum()), int(neg_hist.sum())
    if pos_total == 0 or neg_total == 0:
        return {"positives": pos_total, "negatives": neg_total, "average_precision": None, "auroc": None, "fpr_at_95_tpr": None}
    tp = np.cumsum(pos_hist[::-1])            # thresholds from high score to low
    fp = np.cumsum(neg_hist[::-1])
    tpr, fpr = tp / pos_total, fp / neg_total
    precision = tp / np.maximum(tp + fp, 1)
    recall_prev = np.concatenate([[0.0], tpr[:-1]])
    ap = float(np.sum((tpr - recall_prev) * precision))
    auroc = float(np.trapezoid(np.concatenate([[0.0], tpr]), np.concatenate([[0.0], fpr])))
    hit = np.flatnonzero(tpr >= 0.95)
    return {"positives": pos_total, "negatives": neg_total, "average_precision": ap, "auroc": auroc,
            "fpr_at_95_tpr": float(fpr[hit[0]]) if len(hit) else None}


def _read_label(path: Path) -> np.ndarray | None:
    # imdecode(np.fromfile): cv2.imread hỏng trên đường dẫn có ký tự tiếng Việt ở Windows
    data = np.fromfile(str(path), np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_UNCHANGED) if data.size else None


def _ground_truth(item: dict):
    raw = _read_label(item["label"])
    if raw is None or raw.ndim != 2:
        raise ValueError(f"Bad label for {item['id']}")
    invalid = None
    if item["invalid"] is not None:
        invalid = _read_label(item["invalid"])
        if invalid is None or invalid.shape != raw.shape:
            raise ValueError(f"Bad invalid mask for {item['id']}")
    return raw, invalid


def _apply(lut: np.ndarray, raw: np.ndarray, invalid) -> np.ndarray:
    truth = lut[raw]
    if invalid is not None:
        truth = np.where(invalid == 1, 255, truth).astype(np.uint8)
    return truth


def _ratio(numerator, denominator):
    return float(numerator) / float(denominator) if denominator > 0 else None


def anomaly_summary(matrix) -> dict:
    """Số đo từ ma trận nhầm lẫn 2x2 khi sự thật CHỈ có lớp BLOCKED (vật bất thường RoadAnomaly21).

    Cùng khóa với `metrics.summarize` để bảng từng ảnh và dòng in không đổi dạng, nhưng mIoU, IoU, precision, độ chính
    xác pixel và báo động giả là None: không có pixel FREE thật nào được chấm, nên `summarize` sẽ cho mIoU = IoU
    BLOCKED = recall và precision = 1 — những số đó không đo gì."""
    m = [[int(v) for v in row] for row in np.asarray(matrix).tolist()]
    if m[0][0] or m[0][1]:
        raise ValueError("anomaly_summary: có pixel FREE thật trong ma trận — dùng metrics.summarize")
    anomaly = m[1][0] + m[1][1]
    return {"valid_pixels": anomaly, "confusion_matrix": m, "mIoU": None, "iou_free": None, "iou_blocked": None,
            "pixel_accuracy": None, "blocked_precision": None, "blocked_recall": _ratio(m[1][1], anomaly),
            "blocked_as_free_rate": _ratio(m[1][0], anomaly), "predicted_free_that_is_blocked": None,
            "free_as_blocked_rate": None}


def recall_by_threshold(pos_hist: np.ndarray, thresholds=RECALL_THRESHOLDS) -> dict:
    """Recall BLOCKED (P ≥ t) ở từng ngưỡng t, tính từ histogram điểm `HIST_BINS` ô của pixel dương.

    Ô k chứa P trong [k/HIST_BINS, (k+1)/HIST_BINS), nên P ≥ t ⇔ ô ≥ t·HIST_BINS khi t·HIST_BINS nguyên (mọi t ở đây):
    khớp `predict_image` (bằng ngưỡng là BLOCKED) tới sai số làm tròn số thực của P·HIST_BINS."""
    bins = len(pos_hist)
    total = int(pos_hist.sum())
    out = {}
    for t in thresholds:
        k = int(round(float(t) * bins))
        out[f"{float(t):.2f}"] = int(pos_hist[k:].sum()) / total if total else None
    return out


def anomaly_report(raw_counts: np.ndarray, pos_hist: np.ndarray) -> dict:
    """Tóm tắt RoadAnomaly21 từ `raw_counts` (256, 2) = số pixel dự đoán FREE/BLOCKED theo nhãn gốc trên MỌI pixel."""
    anomaly, background, void = int(raw_counts[1].sum()), int(raw_counts[0].sum()), int(raw_counts[255].sum())
    return {
        "anomaly_pixels": anomaly, "anomaly_recall": _ratio(raw_counts[1, 1], anomaly),
        "anomaly_as_free_rate": _ratio(raw_counts[1, 0], anomaly),
        "anomaly_recall_by_threshold": recall_by_threshold(pos_hist),
        "anomaly_recall_by_threshold_note": "tính lại từ histogram P(BLOCKED) 1000 ô trên pixel vật bất thường, "
                                            "không chạy lại mô hình; ngưỡng của lần chạy nằm ở 'threshold'",
        "background_pixels": background, "background_predicted_blocked_rate": _ratio(raw_counts[0, 1], background),
        "background_note": "nền = nhãn 0 = mọi thứ không phải vật bất thường (đường, nhà, cây, trời, xe khác). Mô hình "
                           "ĐÚNG khi gọi nhà/cây là BLOCKED, nên đây KHÔNG phải tỉ lệ báo động giả; chỉ để tham khảo.",
        "void_pixels": void,
        "not_computed": "AP, FPR95, sIoU/PPV/F1 của SMIYC: cần điểm bất thường theo pixel, mô hình chỉ cho P(BLOCKED) "
                        "và nền gồm cả vật đúng là BLOCKED; mIoU/IoU/precision: không có pixel FREE thật. Không so "
                        "được với bảng xếp hạng SMIYC.",
    }


def detection_by_image(rows: list[dict]) -> dict:
    """Theo từng ảnh có pixel dương: bao nhiêu ảnh thấy ≥ một nửa vật, bao nhiêu ảnh bỏ sót hoàn toàn."""
    detected = [r for r in rows if r["blocked_pixels"] > 0 and r["blocked_recall"] is not None]
    return {"with_obstacle_pixels": len(detected),
            "at_least_half_detected": sum(1 for r in detected if r["blocked_recall"] >= 0.5),
            "fully_missed": sum(1 for r in detected if r["blocked_recall"] == 0.0),
            "median_obstacle_pixels": float(np.median([r["blocked_pixels"] for r in detected])) if detected else None}


def evaluate_items(dataset: str, items: list[dict], predict, lut: np.ndarray, *, variants: dict | None = None,
                   names: dict | None = None, known_ignore=None, progress=print) -> tuple[dict, list[dict]]:
    """Chấm từng ảnh bằng `predict(ảnh BGR) -> (nhãn uint8 0/1, P(BLOCKED) float32)` cùng kích thước ảnh.

    Trả (phần số đo của metrics.json — mọi thứ trừ checkpoint/ngưỡng/nguồn, bảng từng ảnh). Tách khỏi `main` để test
    chạy được trên dữ liệu tổng hợp với `predict` giả, không cần CUDA hay checkpoint. `known_ignore` (chỉ ACDC): các
    mã lớp được phép map sang IGNORE; mã khác map sang IGNORE được đếm vào `unmapped_label_values_seen`."""
    if dataset not in DATASETS:
        raise ValueError(f"dataset phải là một trong {DATASETS}")
    anomaly = dataset == "road_anomaly"
    summary = anomaly_summary if anomaly else summarize
    variants, names = variants or {}, names or {}
    conditions = sorted({item["condition"] for item in items})
    totals = {c: np.zeros((2, 2), np.int64) for c in conditions}
    variant_totals = {name: {c: np.zeros((2, 2), np.int64) for c in conditions} for name in variants}
    class_counts = np.zeros((256, 2), np.int64)
    raw_counts = np.zeros((256, 2), np.int64)        # dự đoán theo nhãn gốc trên MỌI pixel, kể cả pixel IGNORE
    pos_hist = np.zeros(HIST_BINS, np.int64)
    neg_hist = np.zeros(HIST_BINS, np.int64)
    rows, unmapped, values_seen = [], {}, set()
    started = time.perf_counter()
    for index, item in enumerate(items):
        image = read_image(item["image"])
        raw, invalid = _ground_truth(item)
        if raw.shape != image.shape[:2]:
            raise ValueError(f"Label/image size mismatch for {item['id']}")
        present = np.unique(raw)
        values_seen.update(int(v) for v in present)
        if anomaly and not set(present.tolist()) <= set(ROAD_ANOMALY_VALUES):
            raise ValueError(f"{item['id']}: nhãn RoadAnomaly21 có giá trị {sorted(set(present.tolist()))}, ngoài "
                             f"{list(ROAD_ANOMALY_VALUES)} của định dạng SMIYC — không chấm theo định dạng đoán")
        if known_ignore is not None:
            for value in present:
                if lut[value] == 255 and str(value) not in known_ignore:
                    unmapped[str(value)] = unmapped.get(str(value), 0) + 1
        truth = _apply(lut, raw, invalid)
        pred, prob = predict(image)
        pred = np.asarray(pred, np.uint8)
        if pred.shape != raw.shape or np.asarray(prob).shape != raw.shape:
            raise ValueError(f"{item['id']}: dự đoán {pred.shape} khác kích thước nhãn {raw.shape}")
        matrix = confusion(pred, truth)
        totals[item["condition"]] += matrix
        class_counts += per_source_class(raw, truth, pred)
        raw_counts += np.bincount(raw.ravel().astype(np.int64) * 2 + pred.ravel(), minlength=512).reshape(256, 2)
        for name, vlut in variants.items():
            variant_totals[name][item["condition"]] += confusion(pred, _apply(vlut, raw, invalid))
        bins = np.minimum((prob * HIST_BINS).astype(np.int64), HIST_BINS - 1)
        pos_hist += np.bincount(bins[truth == 1], minlength=HIST_BINS)
        neg_hist += np.bincount(bins[truth == 0], minlength=HIST_BINS)
        report = summary(matrix)
        valid = report["valid_pixels"]
        rows.append({"id": item["id"], "condition": item["condition"], "valid_pixels": valid,
                     "error_rate": (matrix[0, 1] + matrix[1, 0]) / valid if valid else None,
                     "iou_free": report["iou_free"], "iou_blocked": report["iou_blocked"],
                     "blocked_pixels": int(matrix[1].sum()), "blocked_recall": report["blocked_recall"],
                     "blocked_as_free_rate": report["blocked_as_free_rate"],
                     "free_as_blocked_rate": report["free_as_blocked_rate"]})
        if progress and (index + 1) % 100 == 0:
            progress(f"{index + 1}/{len(items)} images, {time.perf_counter() - started:.0f} s")

    overall = sum(totals.values())
    body = {"images": len(items), "seconds": time.perf_counter() - started,
            "evaluation_resolution": "original label resolution after un-letterboxing the prediction",
            "confusion_matrix_layout": "rows = ground truth (FREE, BLOCKED), columns = prediction; IGNORE excluded",
            "overall": summary(overall),
            "per_condition": {c: {"images": sum(1 for r in rows if r["condition"] == c), **summary(m)}
                              for c, m in totals.items()},
            "per_source_class": source_class_report(class_counts, lut, names),
            "score_curves_blocked_probability": score_curves(pos_hist, neg_hist),
            "variants": {name: {"overall": summary(sum(t.values())),
                                "per_condition": {c: summary(m) for c, m in t.items()}}
                         for name, t in variant_totals.items()},
            "unmapped_label_values_seen": unmapped,
            "label_values_seen": sorted(values_seen)}
    if dataset == "road_obstacle":
        body["obstacle_images"] = detection_by_image(rows)
    elif anomaly:
        body["anomaly"] = anomaly_report(raw_counts, pos_hist)
        body["anomaly_images"] = detection_by_image(rows)
        body["score_curves_blocked_probability"]["note"] = (
            "không có pixel âm (nhãn 0 là IGNORE vì gồm cả vật đúng là BLOCKED): AP/AUROC/FPR95 không tính")
    return body, rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--dataset", choices=DATASETS, required=True)
    parser.add_argument("--split", default="val", help="ACDC: val, val_ref, train or train_ref")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.5, help="BLOCKED probability threshold")
    parser.add_argument("--mapping", type=Path, default=PROJECT / "configs/acdc_cityscapes_to_binary_v1.json")
    parser.add_argument("--acdc-root", type=Path, default=PROJECT / "datasets/training/acdc")
    parser.add_argument("--road-obstacle-root", type=Path,
                        default=PROJECT / "datasets/training/road_obstacle/dataset_ObstacleTrack")
    parser.add_argument("--road-anomaly-root", type=Path,
                        default=PROJECT / "datasets/training/road_anomaly/dataset_AnomalyTrack",
                        help="thư mục AnomalyTrack của SegmentMeIfYouCan (có images/ và labels_masks/)")
    parser.add_argument("--examples", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N images (smoke test)")
    args = parser.parse_args(argv)

    known_ignore = None
    if args.dataset == "acdc":
        items = acdc_items(args.acdc_root, args.split)
        mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
        lut = build_lut(mapping)
        variants = variant_luts(mapping, lut)
        names = {**mapping["free"], **mapping["blocked"], **mapping.get("ignore", {})}
        known_ignore = set(mapping["ignore"])
        source = {"dataset": "ACDC", "split": args.split, "mapping": str(args.mapping),
                  "mapping_sha256": file_sha256(args.mapping), "invalid_mask": "ACDC *_gt_invIds.png == 1 -> IGNORE",
                  "resolved_classes": {"free": sorted(_keys(mapping["free"])), "blocked": sorted(_keys(mapping["blocked"])),
                                       "ignore": "every other label id"}}
    elif args.dataset == "road_obstacle":
        items = road_obstacle_items(args.road_obstacle_root)
        lut = np.full(256, 255, np.uint8)
        lut[0], lut[1] = 0, 1
        variants, names = {}, {"0": "road", "1": "obstacle"}
        source = {"dataset": "RoadObstacle21 (SegmentMeIfYouCan public validation subset)", "split": "validation",
                  "labels": "0 = road -> FREE, 1 = obstacle -> BLOCKED, 255 = outside the road -> IGNORE"}
    else:
        items = road_anomaly_items(args.road_anomaly_root)
        lut = road_anomaly_lut()
        variants, names = {}, {"0": "not_anomaly", "1": "anomaly", "255": "void"}
        unlabelled = road_anomaly_unlabelled(args.road_anomaly_root, items)
        source = {"dataset": "RoadAnomaly21 (SegmentMeIfYouCan AnomalyTrack, public validation subset)",
                  "split": "validation", "root": str(args.road_anomaly_root),
                  "labels": "0 = không phải vật bất thường (đường, nhà, cây, trời, xe khác) -> IGNORE; "
                            "1 = vật bất thường -> BLOCKED; 255 = void -> IGNORE",
                  "scored": "chỉ pixel vật bất thường: recall BLOCKED và tỉ lệ bị gọi FREE; mIoU/IoU/precision/báo "
                            "động giả không định nghĩa (None) vì không có pixel FREE thật",
                  "unlabelled_images_not_scored": len(unlabelled),
                  "unlabelled_note": "ảnh test của SMIYC, nhãn không công bố: không chấm"}
    if args.limit:
        items = items[:args.limit]
    # Kiểm CUDA SAU khi tìm dữ liệu: thiếu dữ liệu thì báo "chưa chấm" rõ ràng trên mọi máy, kể cả máy không có GPU.
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable; this evaluation does not fall back to CPU silently.")
    device = torch.device("cuda")

    state = load_checkpoint(args.checkpoint)
    cfg = state["config"]
    model = build_model(cfg["num_classes"], pretrained=False)
    model.load_state_dict(state["model"])
    model.to(device).eval()
    height, width = cfg["height"], cfg["width"]

    def predict(image):
        return predict_image(model, image, height, width, device, cfg["amp"], threshold=args.threshold)

    args.out.mkdir(parents=True, exist_ok=True)
    conditions = sorted({item["condition"] for item in items})
    body, rows = evaluate_items(args.dataset, items, predict, lut, variants=variants, names=names,
                                known_ignore=known_ignore, progress=lambda text: print(text, flush=True))
    metrics = {"created_utc": utc_now(), "checkpoint": str(args.checkpoint), "checkpoint_sha256": file_sha256(args.checkpoint),
               "checkpoint_epoch": state["epoch"], "threshold": args.threshold, "model_input": [height, width],
               "source": source, **body}
    atomic_write_json(args.out / "metrics.json", metrics)
    with (args.out / "per_image.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    # Panels: choose from the complete per-image table, then re-run the few chosen images.
    by_id = {item["id"]: item for item in items}
    chosen = []
    for condition in conditions:
        ranked = sorted((r for r in rows if r["condition"] == condition and r["valid_pixels"]), key=lambda r: r["error_rate"])
        middle = len(ranked) // 2
        picks = {"best": ranked[:args.examples], "worst": ranked[::-1][:args.examples],
                 "typical": ranked[max(0, middle - args.examples // 2):][:args.examples]}
        for kind, selected in picks.items():
            for rank, row in enumerate(selected, 1):
                item = by_id[row["id"]]
                image = read_image(item["image"])
                raw, invalid = _ground_truth(item)
                truth = _apply(lut, raw, invalid)
                pred, _ = predict(image)
                small = cv2.resize(image, (image.shape[1] // 2, image.shape[0] // 2), interpolation=cv2.INTER_AREA)
                shape = (small.shape[1], small.shape[0])
                danger = row["blocked_as_free_rate"]
                caption = (f"{row['id']} | {kind} #{rank} of {condition} | pixel error {row['error_rate']:.2%} | "
                           f"blocked->FREE {'n/a' if danger is None else format(danger, '.2%')}")
                name = f"{condition}_{kind}_{rank}_{row['id'].replace('/', '_')}.png"
                panel(cv2.cvtColor(small, cv2.COLOR_BGR2RGB),
                      cv2.resize(truth, shape, interpolation=cv2.INTER_NEAREST),
                      cv2.resize(pred, shape, interpolation=cv2.INTER_NEAREST), caption).save(args.out / name)
                chosen.append({"file": name, "kind": kind, **row})
    atomic_write_json(args.out / "examples.json", {"selection": "per condition, ranked by pixel error over scored pixels",
                                                   "examples": chosen})
    o = metrics["overall"]
    fmt = lambda v: "n/a" if v is None else f"{v:.4f}"
    if args.dataset == "road_anomaly":
        a = metrics["anomaly"]
        print(f"{source['dataset']}: {len(items)} images | anomaly recall {fmt(a['anomaly_recall'])} | anomaly->FREE "
              f"{fmt(a['anomaly_as_free_rate'])} | nền bị gọi BLOCKED {fmt(a['background_predicted_blocked_rate'])} "
              f"(không phải báo động giả) | mIoU không định nghĩa -> {args.out}", flush=True)
        return 0
    print(f"{source['dataset']} {source['split']}: {len(items)} images | mIoU {fmt(o['mIoU'])} | IoU free {fmt(o['iou_free'])} "
          f"blocked {fmt(o['iou_blocked'])} | blocked recall {fmt(o['blocked_recall'])} | blocked->FREE {fmt(o['blocked_as_free_rate'])} "
          f"| AP(blocked) {fmt(metrics['score_curves_blocked_probability']['average_precision'])} -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
