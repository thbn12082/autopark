"""Per-camera region-of-interest masks: pixels a segmentation output may be trusted on.

The model only knows FREE and BLOCKED; on the ego-vehicle body, the fisheye border and other regions that
were IGNORE in training its output is meaningless. A ROI mask (255 = usable, 0 = excluded) removes those
pixels before anything downstream reads the prediction; excluded pixels become IGNORE/UNKNOWN, never FREE.

    python -m autopark.perception.roi build --out configs/roi/woodscape_v1

builds one mask per WoodScape camera from the training split: pixels labelled `ego_vehicle` in more than
--ego-threshold of the images, or nearly black in more than --dark-fraction of the images (lens border), are
excluded. The sky is not part of the ROI problem: the ground projection (costmap.py) never uses rays above
the horizon. For the project's own cameras the same file format is used, built from a few hand-drawn masks.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

import cv2
import numpy as np

from autopark.image_io import imread, imwrite

from .data import label_lookup, letterbox, polygon_mask, read_image
from .dataset import CAMERAS
from .paths import PROJECT, atomic_write_json, utc_now


def apply_roi(labels: np.ndarray, roi: np.ndarray, ignore: int = 255) -> np.ndarray:
    """labels with every pixel outside the ROI set to `ignore`."""
    if labels.shape != roi.shape:
        raise ValueError(f"ROI shape {roi.shape} differs from labels {labels.shape}")
    return np.where(roi > 0, labels, np.uint8(ignore)).astype(np.uint8)


def load_roi(path, shape=None) -> np.ndarray:
    roi = imread(path, cv2.IMREAD_GRAYSCALE)
    if roi is None:
        raise ValueError(f"Cannot read ROI {path}")
    if shape is not None and roi.shape != tuple(shape):
        raise ValueError(f"ROI {path} is {roi.shape}, expected {tuple(shape)}")
    return roi


def roi_to_model_size(roi_native: np.ndarray, height: int, width: int) -> np.ndarray:
    """Letterbox a native-resolution ROI exactly like the training images; padding is excluded."""
    usable = (roi_native > 0).astype(np.uint8)
    _, boxed, _ = letterbox(np.zeros((*roi_native.shape, 3), np.uint8), usable, height, width)
    return np.where(boxed == 1, 255, 0).astype(np.uint8)


def build(args) -> int:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    records = [manifest["records"][i] for i in manifest["splits"]["train"]]
    by_camera = defaultdict(list)
    for record in records:
        by_camera[record["camera"]].append(record["id"])
    source = Path(args.source)
    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    lookup = {name: 0 for name in label_lookup(mapping)}   # every known class -> not ego ...
    lookup["ego_vehicle"] = 1                               # ... except the ego body; unknown tags -> 255 (ignored)
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"created_utc": utc_now(), "source_split": "train", "ego_threshold": args.ego_threshold,
              "dark_threshold": args.dark_threshold, "dark_fraction": args.dark_fraction,
              "dark_sample_every": args.dark_sample_every, "model_size": [args.height, args.width], "cameras": {}}
    for camera in CAMERAS:
        ids = by_camera[camera]
        ego = None
        dark = None
        dark_n = 0
        for n, image_id in enumerate(ids):
            annotation = next(iter(json.loads((source / "instance_annotations" / f"{image_id}.json").read_bytes()).values()))
            if ego is None:
                ego = np.zeros((annotation["image_height"], annotation["image_width"]), np.int32)
                dark = np.zeros_like(ego)
            # Same z-order rasterisation as the label generator: objects drawn over the ego polygon win.
            mask, _, _ = polygon_mask(annotation, lookup)
            ego += (mask == 1)
            if n % args.dark_sample_every == 0:
                gray = cv2.cvtColor(read_image(source / "rgb_images" / f"{image_id}.png"), cv2.COLOR_BGR2GRAY)
                dark += (gray < args.dark_threshold)
                dark_n += 1
        ego_frequency = ego / len(ids)
        dark_frequency = dark / max(1, dark_n)
        usable = (ego_frequency < args.ego_threshold) & (dark_frequency < args.dark_fraction)
        roi = np.where(usable, 255, 0).astype(np.uint8)
        imwrite(args.out / f"roi_{camera}.png", roi)
        small = roi_to_model_size(roi, args.height, args.width)
        imwrite(args.out / f"roi_{camera}_{args.width}x{args.height}.png", small)
        imwrite(args.out / f"ego_frequency_{camera}.png", np.round(ego_frequency * 255).astype(np.uint8))
        report["cameras"][camera] = {
            "images": len(ids), "dark_samples": dark_n, "native_size": [int(roi.shape[0]), int(roi.shape[1])],
            "excluded_fraction_native": float((roi == 0).mean()),
            "excluded_fraction_model_size": float((small == 0).mean()),
            "ego_excluded_fraction": float((ego_frequency >= args.ego_threshold).mean()),
            "border_excluded_fraction": float((dark_frequency >= args.dark_fraction).mean()),
            "ego_frequency_percentiles": {p: float(np.percentile(ego_frequency, p)) for p in (50, 90, 99)}}
        print(f"{camera}: {len(ids)} images, excluded {report['cameras'][camera]['excluded_fraction_native']:.1%} "
              f"(ego {report['cameras'][camera]['ego_excluded_fraction']:.1%}, border "
              f"{report['cameras'][camera]['border_excluded_fraction']:.1%})", flush=True)
    report["notes"] = ("Built from WoodScape training-split ego_vehicle polygons and near-black pixels. Four files "
                       "(06418_MVR, 06419_RV, 06423_MVR, 06424_RV) carry a front-camera calibration despite their "
                       "names; they are a negligible fraction under the frequency threshold. These masks describe "
                       "the WoodScape rigs, not the project's own camera mounts.")
    atomic_write_json(args.out / "roi_manifest.json", report)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="build WoodScape per-camera ROI masks from ego_vehicle polygons")
    b.add_argument("--source", type=Path, default=PROJECT / "datasets/training/woodscape")
    b.add_argument("--manifest", type=Path, default=PROJECT / "datasets/prepared/woodscape_binary_v1/manifest.json")
    b.add_argument("--mapping", type=Path, default=PROJECT / "configs/woodscape_binary_v1.json")
    b.add_argument("--out", type=Path, default=PROJECT / "configs/roi/woodscape_v1")
    b.add_argument("--ego-threshold", type=float, default=0.2, help="exclude pixels that are ego_vehicle in > this fraction of images")
    b.add_argument("--dark-threshold", type=int, default=8)
    b.add_argument("--dark-fraction", type=float, default=0.95)
    b.add_argument("--dark-sample-every", type=int, default=4)
    b.add_argument("--height", type=int, default=384)
    b.add_argument("--width", type=int, default=512)
    args = parser.parse_args(argv)
    if args.command == "build":
        return build(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
