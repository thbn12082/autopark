"""Prepare a frozen, auditable WoodScape training cache without modifying raw data."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

from .data import label_lookup, polygon_mask, letterbox, perceptual_hashes, grouped_split


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("datasets/training/woodscape"))
    parser.add_argument("--metadata", type=Path, default=Path("datasets/woodscape_metadata/training_frame_metadata.json"))
    parser.add_argument("--mapping", type=Path, default=Path("configs/woodscape_binary_v1.json"))
    parser.add_argument("--out", type=Path, default=Path("datasets/prepared/woodscape_binary_v1"))
    parser.add_argument("--height", type=int, default=384)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cv2.setNumThreads(1)
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    lookup = label_lookup(mapping)
    meta = json.loads(args.metadata.read_text(encoding="utf-8"))["frames"]
    files = sorted((args.source / "rgb_images").glob("*.png"))
    if len(files) != 8234:
        raise ValueError(f"Expected audited full release (8234), got {len(files)}")
    images = np.lib.format.open_memmap(args.out / "images.npy", mode="w+", dtype=np.uint8,
                                      shape=(len(files), args.height, args.width, 3))
    masks = np.lib.format.open_memmap(args.out / "masks.npy", mode="w+", dtype=np.uint8,
                                     shape=(len(files), args.height, args.width))
    records, unknown, skip_total, changed, comparable = [], set(), 0, 0, 0
    def convert(item):
        index, path = item
        raw = path.read_bytes()
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        ap = args.source / "instance_annotations" / (path.stem + ".json")
        annotation_raw = ap.read_bytes()
        annotation = next(iter(json.loads(annotation_raw).values()))
        if image is None or image.shape[:2] != (annotation["image_height"], annotation["image_width"]):
            raise ValueError(f"Bad pair {path.name}")
        mask, missing, skipped = polygon_mask(annotation, lookup)
        gp = args.source / "semantic_annotations/gtLabels" / path.name
        official = cv2.imdecode(np.frombuffer(gp.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
        if official is None or official.shape != mask.shape:
            raise ValueError(f"Bad semantic reference {path.name}")
        valid = (official > 0) & (mask != 255)
        original_binary = np.where(official <= 2, 0, 1)
        differences = int(((mask != original_binary) & valid).sum())
        expected_pixels = int(valid.sum())
        p_hash, d_hash = perceptual_hashes(image)
        prepared, target, transform = letterbox(image, mask, args.height, args.width)
        images[index] = cv2.cvtColor(prepared, cv2.COLOR_BGR2RGB)
        masks[index] = target
        frame = meta[path.stem]
        record = {"index": index, "id": path.stem, "camera": path.stem.rsplit("_", 1)[-1],
                  **frame, "image_sha256": hashlib.sha256(raw).hexdigest(),
                  "annotation_sha256": hashlib.sha256(annotation_raw).hexdigest(),
                  "phash": p_hash, "dhash": d_hash, "transform": transform,
                  "pixels": {str(k): int((target == k).sum()) for k in (0, 1, 255)},
                  "semantic_disagreement": differences, "semantic_comparable": expected_pixels}
        return record, missing, skipped, differences, expected_pixels
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for record, missing, skipped, diff, count in pool.map(convert, enumerate(files)):
            records.append(record); unknown.update(missing); skip_total += skipped
            changed += diff; comparable += count
            if len(records) % 250 == 0:
                print("PREPARE", len(records), "/", len(files), round(time.perf_counter()-started, 1), "s", flush=True)
    images.flush(); masks.flush()
    if unknown:
        raise ValueError(f"Unmapped classes require review: {sorted(unknown)}")
    disagreement = changed / max(1, comparable)
    if disagreement > .02:
        raise ValueError(f"Polygon conversion disagrees with released known classes: {disagreement:.2%}")
    splits, grouping = grouped_split(records)
    statistics = {}
    for name, indices in splits.items():
        pixels = {str(k): sum(records[i]["pixels"][str(k)] for i in indices) for k in (0, 1, 255)}
        statistics[name] = {"images": len(indices), "pixels": pixels,
                            "cameras": dict(Counter(records[i]["camera"] for i in indices))}
        if set(statistics[name]["cameras"]) != {"FV", "MVL", "MVR", "RV"} or not pixels["0"] or not pixels["1"]:
            raise ValueError(f"Unbalanced/empty split: {name}")
    manifest = {"schema_version": 1, "height": args.height, "width": args.width, "seed": 20260920,
                "source": "https://github.com/valeoai/WoodScape", "mapping": mapping,
                "mapping_sha256": hashlib.sha256(args.mapping.read_bytes()).hexdigest(),
                "statistics": statistics, "grouping": grouping, "splits": splits, "records": records,
                "skipped_degenerate_annotations": skip_total, "unmapped_classes": sorted(unknown),
                "released_semantic_comparison": {"pixels": comparable, "differences": changed, "rate": disagreement},
                "preparation_seconds": time.perf_counter()-started,
                "prepared": True, "official_test_set": False,
                "ignore_policy": "255 excluded from loss/metrics, not trained as an unknown class"}
    (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "audit.json").write_text(json.dumps({k:v for k,v in manifest.items() if k not in ("records","splits")}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"statistics": statistics, "grouping": grouping, "semantic_disagreement_rate": disagreement}, indent=2))


if __name__ == "__main__":
    main()
