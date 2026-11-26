"""WoodScape polygon labels, aspect-preserving preprocessing and leakage groups."""
from collections import defaultdict
import hashlib
import json
import math
import random

import cv2
import numpy as np


def read_image(path, flags=cv2.IMREAD_COLOR):
    image = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), flags)
    if image is None:
        raise ValueError(f"Cannot decode {path}")
    return image


def label_lookup(mapping):
    lookup = {}
    for key, value in (("free", 0), ("blocked", 1), ("ignore", 255)):
        for name in mapping[key]:
            if name in lookup:
                raise ValueError(f"Duplicate class mapping: {name}")
            lookup[name] = value
    return lookup


def polygon_mask(annotation, lookup):
    h, w = annotation["image_height"], annotation["image_width"]
    mask = np.full((h, w), 255, np.uint8)
    unknown, skipped = set(), 0
    # Same stable z-order and integer point convention as the author's generator.
    for item in sorted(annotation["annotation"], key=lambda a: a["z_order"]):
        tags = item["tags"]
        if len(tags) != 1:
            skipped += 1
            continue
        tag = tags[0]
        if tag not in lookup:
            unknown.add(tag)
        points = np.asarray(item["segmentation"], dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
            raise ValueError("Malformed polygon")
        if len(points) < 3:
            skipped += 1
            continue
        cv2.fillPoly(mask, [points.astype(np.int32)], lookup.get(tag, 255))
    return mask, sorted(unknown), skipped


def letterbox(image, mask, height, width):
    if image.shape[:2] != mask.shape:
        raise ValueError("Image and mask dimensions differ")
    h, w = mask.shape
    scale = min(width / w, height / h)
    nw, nh = round(w * scale), round(h * scale)
    x, y = (width - nw) // 2, (height - nh) // 2
    output = np.zeros((height, width, 3), np.uint8)
    target = np.full((height, width), 255, np.uint8)
    output[y:y+nh, x:x+nw] = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)
    target[y:y+nh, x:x+nw] = cv2.resize(mask, (nw, nh), interpolation=cv2.INTER_NEAREST)
    return output, target, {"scale": scale, "x": x, "y": y, "width": nw, "height": nh}


def perceptual_hashes(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    difference = small[:, 1:] > small[:, :-1]
    dct = cv2.dct(cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32))[:8, :8]
    threshold = np.median(dct.ravel()[1:])
    perceptual = dct > threshold
    def number(bits):
        return int.from_bytes(np.packbits(bits.ravel()).tobytes(), "big")
    return number(perceptual), number(difference)


class UnionFind:
    def __init__(self, count):
        self.parent = list(range(count))

    def find(self, node):
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


class BKTree:
    def __init__(self):
        self.root = None

    def add(self, value, index):
        node = (value, [index], {})
        if self.root is None:
            self.root = node
            return
        current = self.root
        while True:
            distance = (value ^ current[0]).bit_count()
            if distance == 0:
                current[1].append(index)
                return
            if distance not in current[2]:
                current[2][distance] = node
                return
            current = current[2][distance]

    def query(self, value, radius):
        stack = [self.root] if self.root else []
        while stack:
            node = stack.pop()
            distance = (value ^ node[0]).bit_count()
            if distance <= radius:
                yield from node[1]
            stack.extend(child for edge, child in node[2].items()
                         if distance-radius <= edge <= distance+radius)


def grouped_split(records, seed=20260920):
    """Group timestamp runs + exact/near duplicates BEFORE splitting.

job_batch_id is an annotation batch, not a verified recording ID. Timestamp runs
are a heuristic; preserve that limitation in the manifest and reports.
"""
    groups = UnionFind(len(records))
    batches = defaultdict(list)
    for i, record in enumerate(records):
        batches[record["job_batch_id"]].append(i)
    temporal_links = 0
    for indices in batches.values():
        indices.sort(key=lambda i: (int(records[i]["id"].split("_")[0]), records[i]["id"]))
        deltas = [records[b]["timestamp_raw"] - records[a]["timestamp_raw"]
                  for a, b in zip(indices, indices[1:])]
        positive = [d for d in deltas if d > 0]
        threshold = float(np.median(positive)) * 30 if positive else math.inf
        for a, b in zip(indices, indices[1:]):
            delta = records[b]["timestamp_raw"] - records[a]["timestamp_raw"]
            if 0 <= delta <= threshold:
                groups.join(a, b)
                temporal_links += 1
    hashes, tree, near_links, exact_links = {}, BKTree(), 0, 0
    for i, record in enumerate(records):
        digest = record["image_sha256"]
        if digest in hashes:
            groups.join(i, hashes[digest]); exact_links += 1
        hashes[digest] = i
        for j in tree.query(record["phash"], 6):
            if (record["dhash"] ^ records[j]["dhash"]).bit_count() <= 8:
                groups.join(i, j)
                near_links += 1
        tree.add(record["phash"], i)
    components = defaultdict(list)
    for i in range(len(records)):
        components[groups.find(i)].append(i)
    chunks = list(components.values())
    rng = random.Random(seed); rng.shuffle(chunks); chunks.sort(key=len, reverse=True)
    names, ratios = ("train", "val", "test"), (.70, .15, .15)
    splits = {name: [] for name in names}
    targets = dict(zip(names, [len(records)*ratio for ratio in ratios]))
    for component in chunks:
        name = max(names, key=lambda key: targets[key] - len(splits[key]))
        splits[name].extend(component)
    for name, indices in splits.items():
        indices.sort()
        for i in indices:
            records[i]["split"] = name
            records[i]["group"] = groups.find(i)
    if min(len(splits["val"]), len(splits["test"])) < len(records) * .1:
        raise ValueError("Groups too large for a usable held-out split; review grouping")
    audit = {"group_count": len(chunks), "largest_group": max(map(len, chunks)),
             "temporal_links": temporal_links, "exact_duplicate_links": exact_links,
             "near_duplicate_links": near_links, "phash_distance": 6, "dhash_distance": 8,
             "known_duplicate_groups_crossing_splits": 0,
             "limitation": "Timestamp-run heuristics, not verified recording/session IDs; scene leakage cannot be ruled out."}
    return splits, audit
