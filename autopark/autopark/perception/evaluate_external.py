"""Evaluate a WoodScape checkpoint on data it was never trained on: ACDC and RoadObstacle21.

    python -m autopark.perception.evaluate_external --checkpoint runs/<run>/best.pt --dataset acdc --split val --out <dir>
    python -m autopark.perception.evaluate_external --checkpoint runs/<run>/best.pt --dataset road_obstacle --out <dir>

Images go through exactly the deployment path of predict.py (letterbox to the training size, un-letterbox,
resize back), and metrics are computed at the ORIGINAL label resolution. ACDC ground truth is Cityscapes
labelIds mapped with configs/acdc_cityscapes_to_binary_v1.json; pixels flagged invalid by ACDC are IGNORE.
Because BLOCKED on ACDC is dominated by vegetation and buildings, metrics are also broken down per source
class and per class group, so "obstacle -> FREE" can be read for people and vehicles separately.
RoadObstacle21 labels are already 0 = road, 1 = obstacle, 255 = outside the road, so only the road surface
is scored there. Both datasets differ from WoodScape in lens (pinhole), aspect ratio (16:9), country and
conditions: the numbers measure domain shift, not the model's in-distribution accuracy.
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


def _ground_truth(item: dict, lut: np.ndarray):
    raw = cv2.imread(str(item["label"]), cv2.IMREAD_UNCHANGED)
    if raw is None or raw.ndim != 2:
        raise ValueError(f"Bad label for {item['id']}")
    invalid = None
    if item["invalid"] is not None:
        invalid = cv2.imread(str(item["invalid"]), cv2.IMREAD_UNCHANGED)
        if invalid is None or invalid.shape != raw.shape:
            raise ValueError(f"Bad invalid mask for {item['id']}")
    return raw, invalid


def _apply(lut: np.ndarray, raw: np.ndarray, invalid) -> np.ndarray:
    truth = lut[raw]
    if invalid is not None:
        truth = np.where(invalid == 1, 255, truth).astype(np.uint8)
    return truth


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--dataset", choices=("acdc", "road_obstacle"), required=True)
    parser.add_argument("--split", default="val", help="ACDC: val, val_ref, train or train_ref")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.5, help="BLOCKED probability threshold")
    parser.add_argument("--mapping", type=Path, default=PROJECT / "configs/acdc_cityscapes_to_binary_v1.json")
    parser.add_argument("--acdc-root", type=Path, default=PROJECT / "datasets/training/acdc")
    parser.add_argument("--road-obstacle-root", type=Path,
                        default=PROJECT / "datasets/training/road_obstacle/dataset_ObstacleTrack")
    parser.add_argument("--examples", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N images (smoke test)")
    args = parser.parse_args(argv)
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable; this evaluation does not fall back to CPU silently.")
    device = torch.device("cuda")

    if args.dataset == "acdc":
        items = acdc_items(args.acdc_root, args.split)
        mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
        lut = build_lut(mapping)
        variants = variant_luts(mapping, lut)
        names = {**mapping["free"], **mapping["blocked"], **mapping.get("ignore", {})}
        source = {"dataset": "ACDC", "split": args.split, "mapping": str(args.mapping),
                  "mapping_sha256": file_sha256(args.mapping), "invalid_mask": "ACDC *_gt_invIds.png == 1 -> IGNORE",
                  "resolved_classes": {"free": sorted(_keys(mapping["free"])), "blocked": sorted(_keys(mapping["blocked"])),
                                       "ignore": "every other label id"}}
    else:
        items = road_obstacle_items(args.road_obstacle_root)
        lut = np.full(256, 255, np.uint8)
        lut[0], lut[1] = 0, 1
        variants, names = {}, {"0": "road", "1": "obstacle"}
        source = {"dataset": "RoadObstacle21 (SegmentMeIfYouCan public validation subset)", "split": "validation",
                  "labels": "0 = road -> FREE, 1 = obstacle -> BLOCKED, 255 = outside the road -> IGNORE"}
    if args.limit:
        items = items[:args.limit]

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
    totals = {c: np.zeros((2, 2), np.int64) for c in conditions}
    variant_totals = {name: {c: np.zeros((2, 2), np.int64) for c in conditions} for name in variants}
    class_counts = np.zeros((256, 2), np.int64)
    pos_hist = np.zeros(HIST_BINS, np.int64)
    neg_hist = np.zeros(HIST_BINS, np.int64)
    rows, unmapped = [], {}
    started = time.perf_counter()
    for index, item in enumerate(items):
        image = read_image(item["image"])
        raw, invalid = _ground_truth(item, lut)
        if raw.shape != image.shape[:2]:
            raise ValueError(f"Label/image size mismatch for {item['id']}")
        if args.dataset == "acdc":
            for value in np.unique(raw):
                if lut[value] == 255 and str(value) not in mapping["ignore"]:
                    unmapped[str(value)] = unmapped.get(str(value), 0) + 1
        truth = _apply(lut, raw, invalid)
        pred, prob = predict(image)
        matrix = confusion(pred, truth)
        totals[item["condition"]] += matrix
        class_counts += per_source_class(raw, truth, pred)
        for name, vlut in variants.items():
            variant_totals[name][item["condition"]] += confusion(pred, _apply(vlut, raw, invalid))
        bins = np.minimum((prob * HIST_BINS).astype(np.int64), HIST_BINS - 1)
        pos_hist += np.bincount(bins[truth == 1], minlength=HIST_BINS)
        neg_hist += np.bincount(bins[truth == 0], minlength=HIST_BINS)
        report = summarize(matrix)
        valid = report["valid_pixels"]
        rows.append({"id": item["id"], "condition": item["condition"], "valid_pixels": valid,
                     "error_rate": (matrix[0, 1] + matrix[1, 0]) / valid if valid else None,
                     "iou_free": report["iou_free"], "iou_blocked": report["iou_blocked"],
                     "blocked_pixels": int(matrix[1].sum()), "blocked_recall": report["blocked_recall"],
                     "blocked_as_free_rate": report["blocked_as_free_rate"],
                     "free_as_blocked_rate": report["free_as_blocked_rate"]})
        if (index + 1) % 100 == 0:
            print(f"{index + 1}/{len(items)} images, {time.perf_counter() - started:.0f} s", flush=True)

    overall = sum(totals.values())
    metrics = {"created_utc": utc_now(), "checkpoint": str(args.checkpoint), "checkpoint_sha256": file_sha256(args.checkpoint),
               "checkpoint_epoch": state["epoch"], "threshold": args.threshold, "model_input": [height, width],
               "source": source, "images": len(items), "seconds": time.perf_counter() - started,
               "evaluation_resolution": "original label resolution after un-letterboxing the prediction",
               "confusion_matrix_layout": "rows = ground truth (FREE, BLOCKED), columns = prediction; IGNORE excluded",
               "overall": summarize(overall),
               "per_condition": {c: {"images": sum(1 for r in rows if r["condition"] == c), **summarize(m)}
                                 for c, m in totals.items()},
               "per_source_class": source_class_report(class_counts, lut, names),
               "score_curves_blocked_probability": score_curves(pos_hist, neg_hist),
               "variants": {name: {"overall": summarize(sum(t.values())),
                                   "per_condition": {c: summarize(m) for c, m in t.items()}}
                            for name, t in variant_totals.items()},
               "unmapped_label_values_seen": unmapped}
    if args.dataset == "road_obstacle":
        detected = [r for r in rows if r["blocked_pixels"] > 0 and r["blocked_recall"] is not None]
        metrics["obstacle_images"] = {"with_obstacle_pixels": len(detected),
                                      "at_least_half_detected": sum(1 for r in detected if r["blocked_recall"] >= 0.5),
                                      "fully_missed": sum(1 for r in detected if r["blocked_recall"] == 0.0),
                                      "median_obstacle_pixels": float(np.median([r["blocked_pixels"] for r in detected])) if detected else None}
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
                raw, invalid = _ground_truth(item, lut)
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
    print(f"{source['dataset']} {source['split']}: {len(items)} images | mIoU {fmt(o['mIoU'])} | IoU free {fmt(o['iou_free'])} "
          f"blocked {fmt(o['iou_blocked'])} | blocked recall {fmt(o['blocked_recall'])} | blocked->FREE {fmt(o['blocked_as_free_rate'])} "
          f"| AP(blocked) {fmt(metrics['score_curves_blocked_probability']['average_precision'])} -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
