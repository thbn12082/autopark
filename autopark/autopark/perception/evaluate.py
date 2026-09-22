"""Evaluate a checkpoint on a frozen split: overall / per-camera metrics, per-image table, qualitative panels.

    python -m autopark.perception.evaluate --checkpoint runs/<name>/best.pt --split val --out runs/<name>/eval_val
    python -m autopark.perception.evaluate --checkpoint runs/<name>/best.pt --split test --final-test \
        --out runs/<name>/eval_test

The test split is for one report after model selection. Every test evaluation is appended to
`test_evaluations.jsonl` next to the checkpoint, so tuning against it would be visible.
Panels show the RAW argmax prediction everywhere; ground truth is never used to hide model errors.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch

from .checkpoint import atomic_write_json, load_checkpoint
from .dataset import CAMERAS, PreparedCache, SplitData, file_sha256
from .engine import decide, evaluate_split
from .metrics import summarize
from .model import build_model
from .train import PROJECT, utc_now

FREE_COLOR, BLOCKED_COLOR, IGNORE_COLOR = (0, 170, 0), (220, 40, 40), (110, 110, 110)
DANGER_COLOR, FALSE_ALARM_COLOR = (255, 0, 255), (255, 200, 0)
TITLES = ("Ảnh vào", "Nhãn gốc (xám = IGNORE)", "Dự đoán thô của mô hình", "Lỗi: tím = vật cản→FREE, vàng = FREE→vật cản")
ASCII_TITLES = ("Input", "Ground truth (gray = IGNORE)", "Raw model prediction", "Errors: magenta = blocked->FREE, yellow = FREE->blocked")


def _font(size=15):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size), TITLES
        except OSError:
            continue
    return ImageFont.load_default(), ASCII_TITLES


def _overlay(image, labels, with_ignore):
    colors = np.zeros_like(image)
    colors[labels == 0], colors[labels == 1] = FREE_COLOR, BLOCKED_COLOR
    out = (0.5 * image + 0.5 * colors).astype(np.uint8)
    if with_ignore:
        out[labels == 255] = IGNORE_COLOR
    return out


def panel(image, truth, pred, caption) -> Image.Image:
    errors = (0.35 * image).astype(np.uint8)
    errors[(truth == 1) & (pred == 0)] = DANGER_COLOR
    errors[(truth == 0) & (pred == 1)] = FALSE_ALARM_COLOR
    errors[truth == 255] = IGNORE_COLOR
    tiles = [image, _overlay(image, truth, True), _overlay(image, pred, False), errors]
    height, width = image.shape[:2]
    font, titles = _font()
    canvas = Image.new("RGB", (width * 4 + 15, height + 48), (20, 20, 20))
    draw = ImageDraw.Draw(canvas)
    for i, (tile, title) in enumerate(zip(tiles, titles)):
        canvas.paste(Image.fromarray(tile), (i * (width + 5), 24))
        draw.text((i * (width + 5) + 4, 3), title, fill=(235, 235, 235), font=font)
    draw.text((4, height + 27), caption, fill=(200, 200, 200), font=font)
    return canvas


def f_beta(precision, recall, beta):
    if precision is None or recall is None or precision + recall == 0:
        return None
    b2 = beta * beta
    return (1 + b2) * precision * recall / (b2 * precision + recall)


def threshold_sweep_report(sweep: dict, checkpoint: Path) -> dict:
    """Per-threshold metrics on validation plus two explicit selection rules (no test data involved)."""
    rows = []
    for t, m in sorted(sweep.items()):
        rows.append({"threshold": t, "mIoU": m["mIoU"], "iou_free": m["iou_free"], "iou_blocked": m["iou_blocked"],
                     "blocked_precision": m["blocked_precision"], "blocked_recall": m["blocked_recall"],
                     "blocked_as_free_rate": m["blocked_as_free_rate"], "free_as_blocked_rate": m["free_as_blocked_rate"],
                     "blocked_f2": f_beta(m["blocked_precision"], m["blocked_recall"], 2.0)})
    def best(key):
        defined = [r for r in rows if r[key] is not None]
        return max(defined, key=lambda r: r[key])["threshold"] if defined else None   # never "select" on no evidence

    return {"created_utc": utc_now(), "checkpoint": str(checkpoint), "split": "val", "rows": rows,
            "selection": {"max_mIoU": best("mIoU"), "max_blocked_F2": best("blocked_f2")},
            "rule": "F2 weights BLOCKED recall twice as much as precision: for a parking robot a missed obstacle "
                    "(blocked -> FREE) is the dangerous error, a false alarm only costs a stop. The chosen "
                    "threshold must be fixed here before any test evaluation."}


def per_image_rows(records, matrices):
    """`matrices` is the (N, C, C) tensor from evaluate_split; an all-ignore image gets error_rate None."""
    rows = []
    for record, matrix in zip(records, matrices):
        report = summarize(matrix)
        valid, counts = report["valid_pixels"], report["confusion_matrix"]
        wrong = counts[0][1] + counts[1][0]
        rows.append({"id": record["id"], "camera": record["camera"], "valid_pixels": valid,
                     "error_rate": wrong / valid if valid else None,
                     "iou_free": report["iou_free"], "iou_blocked": report["iou_blocked"],
                     "blocked_as_free_rate": report["blocked_as_free_rate"]})
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--split", choices=("val", "test"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--final-test", action="store_true",
                        help="required for --split test: confirms model selection is finished")
    parser.add_argument("--examples", type=int, default=3, help="best / typical / worst panels per camera")
    parser.add_argument("--threshold", type=float, default=0.5, help="BLOCKED probability threshold (ties -> BLOCKED)")
    parser.add_argument("--sweep", action="store_true",
                        help="validation only: score every threshold in 0.05..0.95 and write threshold_sweep.json")
    args = parser.parse_args(argv)
    if args.sweep and args.split != "val":
        parser.error("--sweep is a model-selection step and runs on the validation split only")
    if args.split == "test" and not args.final_test:
        parser.error("The test split is held out. Select the model on validation first, then pass --final-test.")
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable; evaluation does not fall back to CPU silently.")
    device = torch.device("cuda")

    state = load_checkpoint(args.checkpoint)
    cfg = state["config"]
    cache = PreparedCache.open(PROJECT / cfg["prepared_manifest"], cfg["require_handoff_split_verified"])
    if state["split_sha256"] != cache.split_sha256 or state["mapping_sha256"] != cache.manifest["mapping_sha256"]:
        raise SystemExit("Checkpoint was trained on a different split or label mapping; refusing to evaluate.")
    model = build_model(cfg["num_classes"], pretrained=False)
    model.load_state_dict(state["model"])
    model.to(device)

    data = SplitData(cache, args.split)
    predictions = np.empty((len(data), cfg["height"], cfg["width"]), np.uint8)

    def keep(positions, _images, _masks, logits):
        predictions[positions] = decide(logits, args.threshold).to(torch.uint8).cpu().numpy()

    sweep_thresholds = [round(0.05 * i, 2) for i in range(1, 20)] if args.sweep else None
    result = evaluate_split(model, data, batch_size=cfg["eval_batch_size"], device=device, amp=cfg["amp"],
                            num_classes=cfg["num_classes"], ignore_index=cfg["ignore_index"], on_batch=keep,
                            threshold=args.threshold, sweep_thresholds=sweep_thresholds)
    report = result["report"]
    if args.sweep:
        args.out.mkdir(parents=True, exist_ok=True)
        atomic_write_json(args.out / "threshold_sweep.json", threshold_sweep_report(result["sweep"], args.checkpoint))
    matrix = np.asarray(report["confusion_matrix"], dtype=np.float64)
    checkpoint_sha = file_sha256(args.checkpoint)
    args.out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.out / "metrics.json", {
        "created_utc": utc_now(), "checkpoint": str(args.checkpoint), "checkpoint_sha256": checkpoint_sha,
        "checkpoint_epoch": state["epoch"], "selected_by": cfg["select_checkpoint_by"], "threshold": args.threshold,
        "class_names": {"0": "FREE_CANDIDATE", "1": "OBSTACLE_OR_BLOCKED"},
        "confusion_matrix_layout": "rows = ground truth, columns = prediction, IGNORE (255) excluded",
        "confusion_matrix_row_normalized": (matrix / np.maximum(matrix.sum(1, keepdims=True), 1)).tolist(),
        "resolution": [cfg["height"], cfg["width"]], "split_sha256": cache.split_sha256, **report})

    rows = per_image_rows(data.records, result["per_image"])
    with (args.out / "per_image.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    chosen = []
    for camera in CAMERAS:
        ranked = sorted((i for i, row in enumerate(rows) if row["camera"] == camera and row["valid_pixels"]),
                        key=lambda i: rows[i]["error_rate"])
        middle = len(ranked) // 2
        picks = {"best": ranked[:args.examples], "worst": ranked[::-1][:args.examples],
                 "typical": ranked[max(0, middle - args.examples // 2):][:args.examples]}
        for kind, indices in picks.items():
            for rank, i in enumerate(indices, 1):
                row = rows[i]
                danger = row["blocked_as_free_rate"]
                caption = (f"{row['id']} | {kind} #{rank} of {camera} | pixel error {row['error_rate']:.2%} | "
                           f"blocked->FREE {'n/a' if danger is None else format(danger, '.2%')}")
                name = f"{camera}_{kind}_{rank}_{row['id']}.png"
                panel(data.images[i].numpy(), data.masks[i].numpy(), predictions[i], caption).save(args.out / name)
                chosen.append({"file": name, "kind": kind, **row})
    atomic_write_json(args.out / "examples.json", {
        "selection": "per camera, ranked by per-image pixel error over non-ignored pixels", "examples": chosen})

    if args.split == "test":
        with (args.checkpoint.parent / "test_evaluations.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"utc": utc_now(), "checkpoint_sha256": checkpoint_sha, "epoch": state["epoch"],
                                "threshold": args.threshold, "mIoU": report["mIoU"], "out": str(args.out)}) + "\n")
    fmt = lambda v: "n/a" if v is None else f"{v:.4f}"
    print(f"{args.split}: mIoU {fmt(report['mIoU'])} | IoU free {fmt(report['iou_free'])} blocked "
          f"{fmt(report['iou_blocked'])} | blocked recall {fmt(report['blocked_recall'])} precision "
          f"{fmt(report['blocked_precision'])} | blocked->FREE {fmt(report['blocked_as_free_rate'])} | "
          f"{report['images']} images -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
