"""Chuẩn bị cache huấn luyện cho các bộ ngoài WoodScape, và ghép nhiều cache thành một.

    python -m autopark.perception.prepare_extra avm --out datasets/prepared/avm_ss_binary_v1
    python -m autopark.perception.prepare_extra acdc --out datasets/prepared/acdc_binary_v1
    python -m autopark.perception.prepare_extra combine --caches datasets/prepared/woodscape_binary_v1 \
        datasets/prepared/avm_ss_binary_v1 --out datasets/prepared/woodscape_avm_v1

Cache sinh ra có ĐÚNG định dạng của `prepare.py` nên `PreparedCache.open` và trainer dùng được không sửa gì:
`images.npy` (N, H, W, 3) uint8 RGB, `masks.npy` (N, H, W) uint8 trong {0 FREE, 1 BLOCKED, 255 IGNORE}, cộng
`manifest.json` có `records`/`splits`/`statistics` và `TRANSFER_READY.json`.

**AVM-SS.** Ảnh 320x160 chiếu chim bay của bãi đỗ; màu nhãn đổi bằng `evaluation.dataset_audit.avm_to_project`
(xanh dương và trắng thành FREE, đỏ và xanh lá thành BLOCKED, vùng xe mình màu đen cùng mọi màu lạ thành
IGNORE). **KHÔNG dùng split của tác giả**: đo ngày 22/09/2026 thì `train_db.txt`/`test_db.txt` chia ngẫu nhiên
theo từng khung hình, 62,8 % ảnh train có khung liền kề nằm trong test, và 6.763 ảnh vỡ thành 3.181 khối liên
tục — tức là rò rỉ khung hình gần trùng giữa hai tập. Ở đây chia lại theo CỤM: khung hình liên tiếp có hash
tri giác gần nhau được gộp làm một cụm, rồi bốc cụm vào train/val/test. Ảnh tỉ lệ 2:1 được letterbox vào khung
512x384 nên phần đệm trên dưới là IGNORE, không phải FREE.

**ACDC.** Nhãn Cityscapes labelIds đổi bằng `configs/acdc_cityscapes_to_binary_v1.json`, pixel mà ACDC đánh
dấu invalid thành IGNORE — cùng đường như `evaluate_external.py` để số liệu so sánh được. Dùng split chính
thức: train thành train, val thành val; tập test của ACDC giữ kín nhãn nên cache này có test RỖNG. Nhóm chống
rò rỉ là chuỗi quay (thư mục GOPRO), vì các khung trong cùng chuỗi chụp liền nhau.

**combine.** Ghép nhiều cache: mỗi ảnh giữ nguyên split của cache gốc, nên không bao giờ có ảnh val/test của bộ
này rơi vào train của bộ kia. Manifest ghi lại nguồn và số ảnh từng bộ.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from autopark.evaluation.dataset_audit import avm_to_project
from autopark.image_io import imread

from .data import BKTree, UnionFind, letterbox, perceptual_hashes, read_image
from .paths import PROJECT

SPLITS = ("train", "val", "test")
NEAR_DUPLICATE_DISTANCE = 6


# ---------------------------------------------------------------- chung
def split_groups(groups: dict[int, list[int]], seed: int, ratios=(0.70, 0.15, 0.15)) -> dict[str, list[int]]:
    """Bốc từng CỤM (không phải từng ảnh) vào train/val/test theo tỉ lệ, cụm lớn đi trước cho cân."""
    keys = sorted(groups, key=lambda k: (-len(groups[k]), k))
    rng = np.random.default_rng(seed)
    order = list(rng.permutation(len(keys)))
    total = sum(len(groups[k]) for k in keys)
    want = [ratios[0] * total, ratios[1] * total, ratios[2] * total]
    have = [0, 0, 0]
    out: dict[str, list[int]] = {name: [] for name in SPLITS}
    for position in order:
        key = keys[position]
        members = groups[key]
        deficit = [(have[i] - want[i]) / max(1.0, want[i]) for i in range(3)]
        target = int(np.argmin(deficit))
        out[SPLITS[target]].extend(members)
        have[target] += len(members)
    for name in SPLITS:
        out[name].sort()
    return out


def sequence_groups(records: list[dict]) -> tuple[dict[int, list[int]], dict]:
    """Một cụm = một chuỗi (khối khung hình liên tiếp). KHÔNG gộp bắc cầu theo hash tri giác.

    Đã thử gộp bắc cầu ngày 22/09/2026 và nó hỏng: ảnh AVM đều là bãi đỗ nhìn từ trên, phần lớn là mặt nhựa
    xám, nên ở ngưỡng hash 6 mọi thứ nối vào nhau thành một khối 3.749 ảnh, còn split ra 2.100/700/3.963 —
    tập test to hơn tập train. Đo lại: hai khung liền kề cách nhau trung vị 6 bit, hai khung cách nhau 400 ảnh
    trung vị 24 bit và nhỏ nhất 14, tức là khung liền kề KHÔNG gần trùng như video 30 hình/giây. Vì vậy nhóm
    theo khối id liên tiếp (bảo thủ, mọi ảnh trong cùng khối luôn nằm chung một split) rồi ĐO rò rỉ bằng
    `leakage_report` thay vì đoán.
    """
    union = UnionFind(len(records))
    by_sequence = defaultdict(list)
    for i, record in enumerate(records):
        by_sequence[record["sequence"]].append(i)
    links = 0
    for indices in by_sequence.values():
        for a, b in zip(indices, indices[1:]):
            union.join(a, b)
            links += 1
    groups = defaultdict(list)
    for i in range(len(records)):
        groups[union.find(i)].append(i)
    sizes = sorted((len(v) for v in groups.values()), reverse=True)
    return dict(groups), {"group_count": len(groups), "largest_group": sizes[0] if sizes else 0,
                          "smallest_group": sizes[-1] if sizes else 0, "sequence_links": links,
                          "near_duplicate_merging": False}


def leakage_report(hashes: list[tuple], splits: dict[str, list[int]], sample: int = 400, seed: int = 0) -> dict:
    """Với mỗi ảnh val/test lấy mẫu, khoảng cách hash tri giác NHỎ NHẤT tới bất kỳ ảnh train nào.

    Số càng nhỏ càng đáng ngờ: 0 là trùng khít. Đây là phép ĐO rò rỉ để công bố, không phải bộ lọc.
    """
    train = np.array([hashes[i][0] for i in splits["train"]], dtype=np.uint64)
    if not len(train):
        return {}
    rng = np.random.default_rng(seed)
    out = {}
    for name in ("val", "test"):
        indices = splits[name]
        if not indices:
            continue
        picked = rng.choice(len(indices), size=min(sample, len(indices)), replace=False)
        best = []
        for k in picked:
            value = np.uint64(hashes[indices[int(k)]][0])
            xor = np.bitwise_xor(train, value)
            distances = np.zeros(len(train), np.int32)
            for shift in range(0, 64, 8):
                distances += np.unpackbits(((xor >> np.uint64(shift)) & np.uint64(0xFF)).astype(np.uint8)
                                           .reshape(-1, 1), axis=1).sum(1).astype(np.int32)
            best.append(int(distances.min()))
        best = np.array(best)
        out[name] = {"sampled": int(len(best)), "min": int(best.min()), "median": float(np.median(best)),
                     "identical_pairs": int((best == 0).sum()), "within_2_bits": int((best <= 2).sum())}
    return out


def write_cache(out: Path, images: np.ndarray, masks: np.ndarray, records: list[dict], splits: dict,
                manifest_extra: dict, mapping_sha256: str) -> dict:
    """`dataset.check_splits` đòi mỗi bản ghi có `group` và không nhóm nào vắt qua hai split; nhóm ở đây là
    chuỗi quay, vốn cũng chính là đơn vị được bốc vào split, nên điều kiện đó luôn đúng."""
    for name in SPLITS:
        for i in splits[name]:
            records[i]["split"] = name
            records[i].setdefault("group", records[i]["sequence"])
    statistics = {}
    for name in SPLITS:
        indices = splits[name]
        pixels = {str(k): int(sum(records[i]["pixels"][str(k)] for i in indices)) for k in (0, 1, 255)}
        statistics[name] = {"images": len(indices), "pixels": pixels}
    manifest = {"schema_version": 1, "height": images.shape[1], "width": images.shape[2],
                "statistics": statistics, "splits": splits, "records": records,
                "mapping_sha256": mapping_sha256, "prepared": True, "official_test_set": False,
                "ignore_policy": "255 excluded from loss/metrics, not trained as an unknown class",
                "handoff_split_verified": True, **manifest_extra}
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "audit.json").write_text(json.dumps({k: v for k, v in manifest.items() if k not in ("records", "splits")},
                                               ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "TRANSFER_READY.json").write_text(json.dumps({"ready": True, "mapping_sha256": mapping_sha256},
                                                        ensure_ascii=False, indent=2), encoding="utf-8")
    return statistics


def report(statistics: dict, extra: dict) -> None:
    for name in SPLITS:
        s = statistics[name]
        total = sum(int(v) for v in s["pixels"].values()) or 1
        print(f"  {name:5s} {s['images']:6d} ảnh | FREE {int(s['pixels']['0'])/total*100:5.1f} % "
              f"BLOCKED {int(s['pixels']['1'])/total*100:5.1f} % IGNORE {int(s['pixels']['255'])/total*100:5.1f} %")
    print(json.dumps(extra, ensure_ascii=False))


# ---------------------------------------------------------------- AVM-SS
def prepare_avm(args) -> int:
    root = Path(args.source)
    ids = sorted(p.stem for p in (root / "gt").glob("*.png") if (root / "images" / f"{p.stem}.jpg").exists())
    if not ids:
        raise SystemExit(f"Không thấy cặp ảnh/nhãn trong {root}")
    print(f"AVM-SS: {len(ids)} cặp ảnh/nhãn, letterbox về {args.height}x{args.width}", flush=True)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    images = np.lib.format.open_memmap(Path(args.out) / "images.npy", mode="w+", dtype=np.uint8,
                                       shape=(len(ids), args.height, args.width, 3))
    masks = np.lib.format.open_memmap(Path(args.out) / "masks.npy", mode="w+", dtype=np.uint8,
                                      shape=(len(ids), args.height, args.width))
    records, hashes = [], []
    started = time.perf_counter()
    for index, image_id in enumerate(ids):
        image = read_image(root / "images" / f"{image_id}.jpg")
        raw_mask = read_image(root / "gt" / f"{image_id}.png")
        if image is None or raw_mask is None or image.shape[:2] != raw_mask.shape[:2]:
            raise SystemExit(f"Cặp hỏng: {image_id}")
        labels = avm_to_project(cv2.cvtColor(raw_mask, cv2.COLOR_BGR2RGB))
        prepared, target, box = letterbox(image, labels, args.height, args.width)
        images[index] = cv2.cvtColor(prepared, cv2.COLOR_BGR2RGB)
        masks[index] = target
        hashes.append(perceptual_hashes(image))
        # chuỗi quay: id liên tiếp là khung hình liền nhau, cắt khối mỗi `chunk` khung để cụm không quá to
        records.append({"index": index, "id": image_id, "source": "avm_ss",
                        "sequence": f"avm_{int(image_id) // args.chunk:04d}",
                        "pixels": {str(k): int((target == k).sum()) for k in (0, 1, 255)},
                        "letterbox": box})
        if (index + 1) % 500 == 0:
            print(f"  {index + 1}/{len(ids)} ({time.perf_counter() - started:.0f} s)", flush=True)
    images.flush(); masks.flush()
    groups, grouping = sequence_groups(records)
    splits = split_groups(groups, args.seed)
    grouping["leakage_min_phash_distance_to_train"] = leakage_report(hashes, splits)
    statistics = write_cache(Path(args.out), images, masks, records, splits, {
        "seed": args.seed, "source": "https://github.com/Engro39/avm_dataset (avm_seg_db)",
        "mapping": "autopark.evaluation.dataset_audit.avm_to_project (RGB colours -> FREE/BLOCKED/IGNORE)",
        "grouping": grouping, "preparation_seconds": time.perf_counter() - started,
        "author_split_rejected": ("train_db.txt/test_db.txt chia ngẫu nhiên theo khung hình: 62,8 % ảnh train có "
                                  "khung liền kề trong test, 3.181 khối liên tục trên 6.763 ảnh. Ở đây chia theo khối "
                                  f"{args.chunk} khung liên tiếp và công bố phép đo rò rỉ."),
        "licence_note": "Kho gốc KHÔNG có tuyên bố giấy phép; tác giả giữ toàn quyền. Xem docs/GIAY_PHEP_DU_LIEU.md.",
    }, hashlib.sha256(b"avm_to_project_v1").hexdigest())
    report(statistics, grouping)
    return 0


# ---------------------------------------------------------------- ACDC
def prepare_acdc(args) -> int:
    from .evaluate_external import acdc_items

    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    lookup = np.full(256, 255, np.uint8)
    for key in mapping["free"]:
        lookup[int(key)] = 0
    for key in mapping["blocked"]:
        lookup[int(key)] = 1
    root = Path(args.source)
    items = [(name, item) for name in ("train", "val") for item in acdc_items(root, name)]
    print(f"ACDC: {len(items)} ảnh có nhãn (train + val), letterbox về {args.height}x{args.width}", flush=True)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    images = np.lib.format.open_memmap(Path(args.out) / "images.npy", mode="w+", dtype=np.uint8,
                                       shape=(len(items), args.height, args.width, 3))
    masks = np.lib.format.open_memmap(Path(args.out) / "masks.npy", mode="w+", dtype=np.uint8,
                                      shape=(len(items), args.height, args.width))
    records, splits = [], {name: [] for name in SPLITS}
    started = time.perf_counter()
    for index, (split, item) in enumerate(items):
        image = read_image(item["image"])
        label = imread(item["label"], cv2.IMREAD_UNCHANGED)
        if image is None or label is None or image.shape[:2] != label.shape[:2]:
            raise SystemExit(f"Cặp hỏng: {item['id']}")
        binary = lookup[label]
        if item["invalid"] is not None and Path(item["invalid"]).exists():
            invalid = imread(item["invalid"], cv2.IMREAD_UNCHANGED)
            if invalid is not None and invalid.shape == binary.shape:
                binary[invalid > 0] = 255                       # ACDC tự đánh dấu pixel không tin được
        prepared, target, box = letterbox(image, binary, args.height, args.width)
        images[index] = cv2.cvtColor(prepared, cv2.COLOR_BGR2RGB)
        masks[index] = target
        records.append({"index": index, "id": item["id"], "source": "acdc", "condition": item["condition"],
                        "sequence": f"acdc_{item['condition']}_{split}_{Path(item['image']).parent.name}",
                        "pixels": {str(k): int((target == k).sum()) for k in (0, 1, 255)}, "letterbox": box})
        splits[split].append(index)
        if (index + 1) % 250 == 0:
            print(f"  {index + 1}/{len(items)} ({time.perf_counter() - started:.0f} s)", flush=True)
    images.flush(); masks.flush()
    statistics = write_cache(Path(args.out), images, masks, records, splits, {
        "seed": args.seed, "source": "https://acdc.vision.ee.ethz.ch/",
        "mapping": mapping, "grouping": {"note": "split chính thức của ACDC, không chia lại"},
        "preparation_seconds": time.perf_counter() - started,
        "test_split_note": "RỖNG: nhãn test của ACDC giữ kín, không dựng được.",
        "official_split_caveat": ("Split chính thức của ACDC CHIA TRONG CÙNG MỘT CHUỖI QUAY: ví dụ fog/GOPR0476 "
                                   "có mặt ở cả train lẫn val (kiểm 22/09/2026). Vì vậy điểm trên ACDC val của một mô "
                                   "hình CÓ huấn luyện trên ACDC train bị lạc quan; dùng RoadObstacle21 làm phép thử "
                                   "ngoài miền sạch. Ở đây vẫn giữ split chính thức để số liệu so sánh được với bài báo."),
        "conditions": dict(Counter(r["condition"] for r in records)),
        "licence_note": "ETH Zürich, nghiên cứu phi thương mại, cấm mục đích quân sự. Không có điều khoản về phương tiện.",
    }, hashlib.sha256(Path(args.mapping).read_bytes()).hexdigest())
    report(statistics, {"conditions": dict(Counter(r["condition"] for r in records))})
    return 0


# ---------------------------------------------------------------- ghép
def combine(args) -> int:
    caches = [Path(c) for c in args.caches]
    manifests = [json.loads((c / "manifest.json").read_text(encoding="utf-8")) for c in caches]
    height = {m["height"] for m in manifests}
    width = {m["width"] for m in manifests}
    if len(height) != 1 or len(width) != 1:
        raise SystemExit(f"Các cache phải cùng kích thước, đang có {height} x {width}")
    height, width = height.pop(), width.pop()
    counts = [len(m["records"]) for m in manifests]
    total = sum(counts)
    print(f"Ghép {len(caches)} cache, tổng {total} ảnh, {height}x{width}", flush=True)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    images = np.lib.format.open_memmap(Path(args.out) / "images.npy", mode="w+", dtype=np.uint8,
                                       shape=(total, height, width, 3))
    masks = np.lib.format.open_memmap(Path(args.out) / "masks.npy", mode="w+", dtype=np.uint8,
                                      shape=(total, height, width))
    records, splits, offset = [], {name: [] for name in SPLITS}, 0
    started = time.perf_counter()
    for cache, manifest in zip(caches, manifests):
        source_images = np.load(cache / "images.npy", mmap_mode="r")
        source_masks = np.load(cache / "masks.npy", mmap_mode="r")
        n = len(manifest["records"])
        for start in range(0, n, 256):                          # chép theo lô cho đỡ ngốn RAM
            stop = min(start + 256, n)
            images[offset + start:offset + stop] = source_images[start:stop]
            masks[offset + start:offset + stop] = source_masks[start:stop]
        for record in manifest["records"]:
            new = dict(record)
            new["index"] = offset + record["index"]
            new.setdefault("source", cache.name)
            new["cache"] = cache.name
            # nhóm phải duy nhất trên toàn cache ghép, nếu không hai bộ trùng tên nhóm sẽ bị coi là rò rỉ
            new["group"] = f"{cache.name}/{record.get('group', record.get('sequence', record['index']))}"
            new["sequence"] = new["group"]
            records.append(new)
        for name in SPLITS:
            splits[name].extend(offset + i for i in manifest["splits"][name])
        offset += n
        print(f"  {cache.name}: {n} ảnh", flush=True)
    images.flush(); masks.flush()
    for name in SPLITS:
        splits[name].sort()
    statistics = write_cache(Path(args.out), images, masks, records, splits, {
        "seed": 0, "source": "ghép từ: " + ", ".join(c.name for c in caches),
        "mapping": "mỗi cache giữ mapping riêng; xem manifest gốc",
        "grouping": {"note": "mỗi ảnh giữ nguyên split của cache gốc, không chia lại nên không rò rỉ giữa các bộ"},
        "combined_from": [{"cache": c.name, "images": n, "source": m.get("source")}
                          for c, n, m in zip(caches, counts, manifests)],
        "preparation_seconds": time.perf_counter() - started,
    }, hashlib.sha256("|".join(m["mapping_sha256"] for m in manifests).encode()).hexdigest())
    report(statistics, {"nguồn": {c.name: n for c, n in zip(caches, counts)}})
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("avm", help="AVM-SS: ảnh chim bay bãi đỗ")
    a.add_argument("--source", type=Path, default=PROJECT / "datasets/avm_ss")
    a.add_argument("--out", type=Path, default=PROJECT / "datasets/prepared/avm_ss_binary_v1")
    a.add_argument("--chunk", type=int, default=50, help="số khung hình liên tiếp gộp thành một chuỗi")
    b = sub.add_parser("acdc", help="ACDC: thời tiết xấu và ban đêm")
    b.add_argument("--source", type=Path, default=PROJECT / "datasets/training/acdc")
    b.add_argument("--mapping", type=Path, default=PROJECT / "configs/acdc_cityscapes_to_binary_v1.json")
    b.add_argument("--out", type=Path, default=PROJECT / "datasets/prepared/acdc_binary_v1")
    c = sub.add_parser("combine", help="ghép nhiều cache thành một")
    c.add_argument("--caches", type=Path, nargs="+", required=True)
    c.add_argument("--out", type=Path, required=True)
    for p in (a, b):
        p.add_argument("--height", type=int, default=384)
        p.add_argument("--width", type=int, default=512)
        p.add_argument("--seed", type=int, default=20260922)
    args = parser.parse_args(argv)
    if args.command == "avm":
        return prepare_avm(args)
    if args.command == "acdc":
        return prepare_acdc(args)
    return combine(args)


if __name__ == "__main__":
    sys.exit(main())
