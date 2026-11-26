"""Kiểm tra các gói dữ liệu đã tải; không chạy code từ archive của bên thứ ba."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent


def read_image(path, flags=cv2.IMREAD_COLOR):
    # imread trên Windows không đọc ổn đường dẫn có dấu; Python xử lý đường dẫn.
    try:
        return cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), flags)
    except OSError:
        return None


def audit_avm():
    root = ROOT / "avm_ss"
    images = sorted((root / "images").glob("*.jpg"))
    masks = list((root / "gt").glob("*.png"))
    colors, shapes, errors, digests = Counter(), Counter(), [], {}
    palette = {0, 255, 65280, 16711680, 16777215}
    pairs = []
    for path in images:
        mask_path = root / "gt" / (path.stem + ".png")
        image, mask = read_image(path), read_image(mask_path)
        if image is None or mask is None or image.shape != mask.shape:
            errors.append(path.name)
            continue
        shapes[str(image.shape)] += 1
        rgb = cv2.cvtColor(mask, cv2.COLOR_BGR2RGB).astype(np.uint32)
        packed = (rgb[:, :, 0] << 16) + (rgb[:, :, 1] << 8) + rgb[:, :, 2]
        values, counts = np.unique(packed, return_counts=True)
        colors.update({int(v): int(n) for v, n in zip(values, counts)})
        digests[path.stem] = hashlib.sha256(path.read_bytes()).hexdigest()
        pairs.append({"image": path.relative_to(ROOT).as_posix(),
                      "mask": mask_path.relative_to(ROOT).as_posix(), "id": path.stem})
    splits = {}
    for split in ("train", "test"):
        rows = (root / f"{split}_db.txt").read_text().splitlines()
        splits[split] = [Path(line.split()[0]).stem for line in rows if line.strip()]
    overlap = set(splits["train"]) & set(splits["test"])
    train_hashes = {digests[i] for i in splits["train"] if i in digests}
    test_hashes = {digests[i] for i in splits["test"] if i in digests}
    report = {"images": len(images), "masks": len(masks), "pairs": len(pairs), "shapes": shapes,
              "bad_pairs": errors, "palette_rgb_packed": colors,
              "unexpected_palette": sorted(set(colors) - palette),
              "splits": {k: len(v) for k, v in splits.items()}, "split_id_overlap": sorted(overlap),
              "exact_image_hash_overlap": len(train_hashes & test_hashes),
              "missing_split_ids": sorted((set(splits['train']) | set(splits['test'])) - digests.keys())}
    report["unknown_color_policy"] = "RGB (255,255,0) and all unmapped colors -> UNKNOWN/IGNORE 255"
    (ROOT / "avm_pairs.json").write_text(json.dumps({"pairs": pairs, "splits": splits}, indent=2), encoding="utf-8")
    return report


def audit_drow():
    root = ROOT / "drow/DROWv2-data"
    splits = {}
    for split in ("train", "val", "test"):
        files = sorted((root / split).glob("*.csv"))
        lines = 0
        fields = Counter()
        for path in files:
            with path.open("rb") as f:
                for line in f:
                    if line.strip():
                        lines += 1
                        fields[line.count(b",") + 1] += 1
        splits[split] = {"scan_files": len(files), "scan_rows": lines, "columns": fields,
                         "person_annotation_files": len(list((root / split).glob("*.wp"))),
                         "wheelchair_annotation_files": len(list((root / split).glob("*.wc"))),
                         "walking_aid_annotation_files": len(list((root / split).glob("*.wa")))}
    orphans = []
    for split in ("train", "val", "test"):
        folder = root / split
        scan_names = {p.stem for p in folder.glob("*.csv")}
        for extension in ("wp", "wc", "wa"):
            orphans.extend(p.relative_to(root).as_posix() for p in folder.glob("*." + extension)
                           if p.stem not in scan_names)
    return {"splits": splits, "note": "Column count only; not a geometric/label accuracy audit.",
            "orphan_annotations": sorted(orphans),
            "csv_schema": {"sequence_id_column": 0, "timestamp_column": 1, "range_columns": [2, 451],
                           "reference": "https://github.com/VisualComputingInstitute/DROW/blob/master/v2/utils/__init__.py"}}


def audit_woodscape():
    root = ROOT / "woodscape_subset"
    if not (root / "manifest.json").exists():
        return {"status": "not_completed"}
    manifest = json.loads((root / "manifest.json").read_text())
    cameras, shapes, values, errors = Counter(), Counter(), set(), []
    for pair in manifest["pairs"]:
        image = read_image(root / "rgb" / pair["name"])
        mask = read_image(root / "semantic" / pair["name"], cv2.IMREAD_UNCHANGED)
        if image is None or mask is None or image.shape[:2] != mask.shape[:2] or mask.ndim != 2:
            errors.append(pair["name"])
            continue
        cameras[pair["camera"]] += 1
        shapes[str(image.shape)] += 1
        values.update(int(v) for v in np.unique(mask))
    calibrations = 0
    for pair in manifest["pairs"]:
        path = root / "calibration" / Path(pair["name"]).with_suffix(".json")
        if path.exists():
            json.loads(path.read_text(encoding="utf-8"))
            calibrations += 1
    return {"subset_only": True, "pairs": len(manifest["pairs"]), "cameras": cameras,
            "image_shapes": shapes, "class_ids": sorted(values), "bad_pairs": errors,
            "matching_calibrations": calibrations,
            "local_bytes": sum(p.stat().st_size for p in root.rglob("*") if p.is_file()),
            "status": "verified_subset" if not errors else "invalid_pairs"}


if __name__ == "__main__":
    report = {"avm_ss": audit_avm(), "drow_v2": audit_drow(), "woodscape": audit_woodscape()}
    (ROOT / "download_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
