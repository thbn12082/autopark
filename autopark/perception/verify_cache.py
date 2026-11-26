"""Verify an existing prepared cache against the frozen split, then mark it ready for training.

The handoff tool rebuilds the arrays from raw data. When the original arrays were copied instead, this does the
equivalent checks without rebuilding: manifest equality, array format, per-record pixel counts recomputed from
masks.npy, SHA-256 of every raw image/annotation, and a bit-exact regeneration of a per-camera sample.
Nothing is written unless every check passes.

    python -m autopark.perception.verify_cache
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from .checkpoint import atomic_write_json
from .data import label_lookup, letterbox, polygon_mask
from .dataset import CAMERAS, MASK_VALUES, check_splits, file_sha256

PROJECT = Path(__file__).resolve().parents[2]
RECORD_KEYS = ("id", "image_sha256", "annotation_sha256", "pixels", "split", "group", "camera", "transform")


def compare_manifests(current: dict, frozen: dict) -> None:
    for key in ("mapping_sha256", "mapping", "height", "width", "seed", "splits", "statistics", "grouping"):
        if current[key] != frozen[key]:
            raise ValueError(f"Cache manifest differs from the frozen manifest: {key}")
    if len(current["records"]) != len(frozen["records"]):
        raise ValueError("Record count differs from the frozen manifest")
    for new, old in zip(current["records"], frozen["records"]):
        for key in RECORD_KEYS:
            if new[key] != old[key]:
                raise ValueError(f"Record mismatch: {new['id']} / {key}")


def recount_pixels(masks: np.ndarray, records: list[dict], chunk=512) -> None:
    for start in range(0, len(records), chunk):
        block = np.asarray(masks[start:start + chunk])
        if not np.isin(block, MASK_VALUES).all():
            raise ValueError(f"masks.npy holds values outside {MASK_VALUES} near record {start}")
        counts = {value: (block == value).sum(axis=(1, 2)) for value in MASK_VALUES}
        for offset, record in enumerate(records[start:start + chunk]):
            found = {str(value): int(counts[value][offset]) for value in MASK_VALUES}
            if found != record["pixels"]:
                raise ValueError(f"Pixel counts differ for {record['id']}: {found} vs {record['pixels']}")


def hash_raw(source: Path, records: list[dict], workers: int) -> None:
    def one(record):
        image = hashlib.sha256((source / "rgb_images" / (record["id"] + ".png")).read_bytes()).hexdigest()
        label = hashlib.sha256((source / "instance_annotations" / (record["id"] + ".json")).read_bytes()).hexdigest()
        return record["id"], image == record["image_sha256"], label == record["annotation_sha256"]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        bad = [name for name, image_ok, label_ok in pool.map(one, records) if not (image_ok and label_ok)]
    if bad:
        raise ValueError(f"{len(bad)} raw files differ from the manifest hashes, e.g. {bad[:5]}")


def regenerate(source: Path, record: dict, lookup: dict, height: int, width: int):
    """Exactly the conversion in prepare.py: decode, polygon mask, letterbox, BGR->RGB."""
    raw = (source / "rgb_images" / (record["id"] + ".png")).read_bytes()
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    annotation = next(iter(json.loads((source / "instance_annotations" / (record["id"] + ".json")).read_bytes()).values()))
    mask, _, _ = polygon_mask(annotation, lookup)
    prepared, target, _ = letterbox(image, mask, height, width)
    return cv2.cvtColor(prepared, cv2.COLOR_BGR2RGB), target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cache", type=Path, default=PROJECT / "datasets/prepared/woodscape_binary_v1")
    parser.add_argument("--frozen", type=Path, default=PROJECT / "datasets/frozen_splits/woodscape_binary_v1/manifest.json")
    parser.add_argument("--source", type=Path, default=PROJECT / "datasets/training/woodscape")
    parser.add_argument("--mapping", type=Path, default=PROJECT / "configs/woodscape_binary_v1.json")
    parser.add_argument("--sample-per-camera", type=int, default=64)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)

    started = time.perf_counter()
    cv2.setNumThreads(1)
    manifest_path = args.cache / "manifest.json"
    current = json.loads(manifest_path.read_text(encoding="utf-8"))
    frozen = json.loads(args.frozen.read_text(encoding="utf-8"))
    compare_manifests(current, frozen)
    check_splits(current)
    mapping_sha = hashlib.sha256(args.mapping.read_bytes()).hexdigest()
    if mapping_sha != current["mapping_sha256"]:
        raise ValueError("configs mapping file differs from the mapping the cache was built with")
    print("OK manifest equals frozen manifest; splits partition the records; mapping hash matches", flush=True)

    records, height, width = current["records"], current["height"], current["width"]
    images = np.load(args.cache / "images.npy", mmap_mode="r", allow_pickle=False)
    masks = np.load(args.cache / "masks.npy", mmap_mode="r", allow_pickle=False)
    if images.shape != (len(records), height, width, 3) or images.dtype != np.uint8:
        raise ValueError(f"Wrong array format: images.npy {images.shape} {images.dtype}")
    if masks.shape != (len(records), height, width) or masks.dtype != np.uint8:
        raise ValueError(f"Wrong array format: masks.npy {masks.shape} {masks.dtype}")
    recount_pixels(masks, records)
    print(f"OK masks.npy: values in {MASK_VALUES}; per-record pixel counts match for {len(records)} records", flush=True)

    hash_raw(args.source, records, args.workers)
    print(f"OK raw images and annotations match manifest SHA-256 for {len(records)} records", flush=True)

    lookup = label_lookup(json.loads(args.mapping.read_text(encoding="utf-8")))
    rng = np.random.default_rng(current["seed"])
    sample = []
    for camera in CAMERAS:
        rows = [r["index"] for r in records if r["camera"] == camera]
        sample += sorted(rng.choice(rows, size=min(args.sample_per_camera, len(rows)), replace=False).tolist())
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rebuilt = list(pool.map(lambda i: regenerate(args.source, records[i], lookup, height, width), sample))
    mask_mismatch, image_mismatch, max_diff = [], [], 0
    for index, (image, mask) in zip(sample, rebuilt):
        if not np.array_equal(mask, masks[index]):
            mask_mismatch.append(records[index]["id"])
        difference = int(np.abs(image.astype(np.int16) - np.asarray(images[index]).astype(np.int16)).max())
        max_diff = max(max_diff, difference)
        if difference:
            image_mismatch.append(records[index]["id"])
    if mask_mismatch:
        raise ValueError(f"Regenerated masks differ from the cache for {len(mask_mismatch)} records: {mask_mismatch[:5]}")
    if image_mismatch:
        raise ValueError(f"Regenerated images differ from the cache for {len(image_mismatch)} records "
                         f"(max abs difference {max_diff}): {image_mismatch[:5]}")
    print(f"OK regenerated {len(sample)} records from raw data: images and masks bit-identical to the cache", flush=True)

    arrays = {name: {"sha256": file_sha256(args.cache / name), "bytes": (args.cache / name).stat().st_size}
              for name in ("images.npy", "masks.npy")}
    current["handoff_split_verified"] = True
    atomic_write_json(manifest_path, current)
    atomic_write_json(args.cache / "TRANSFER_READY.json", {
        "ready": True, "method": "verified_existing_copy_not_rebuilt",
        "verified_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "splits": {name: len(indices) for name, indices in current["splits"].items()},
        "mapping_sha256": current["mapping_sha256"], "frozen_manifest_sha256": file_sha256(args.frozen),
        "arrays": arrays, "opencv": cv2.__version__, "numpy": np.__version__,
        "checks": {"manifest_equals_frozen": True, "records_pixel_recount": len(records),
                   "raw_files_sha256_checked": len(records), "regenerated_bit_identical": len(sample),
                   "sample_per_camera": args.sample_per_camera},
        "seconds": round(time.perf_counter() - started, 1)})
    print(f"CACHE READY: train={len(current['splits']['train'])}, val={len(current['splits']['val'])}, "
          f"test={len(current['splits']['test'])}; frozen split preserved. "
          f"{round(time.perf_counter() - started, 1)} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
