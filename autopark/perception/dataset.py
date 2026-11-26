"""Frozen WoodScape cache for training: read-only memory maps, verified split, deterministic batches."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

SPLITS = ("train", "val", "test")
CAMERAS = ("FV", "MVL", "MVR", "RV")
MASK_VALUES = (0, 1, 255)


class CacheError(RuntimeError):
    pass


def canonical_sha256(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def file_sha256(path, chunk=8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def check_splits(manifest) -> None:
    """The frozen split must partition the records; a record's own `split` field must agree."""
    records, seen = manifest["records"], set()
    for name in SPLITS:
        indices = manifest["splits"][name]
        unique = set(indices)
        if len(unique) != len(indices) or seen & unique:
            raise CacheError(f"Split '{name}' repeats or shares images with another split")
        if any(records[i]["index"] != i or records[i]["split"] != name for i in indices):
            raise CacheError(f"Split '{name}' disagrees with the per-record split/index fields")
        seen |= unique
    if seen != set(range(len(records))):
        raise CacheError("Splits do not cover every record exactly once")
    owners = {}
    for record in records:
        if owners.setdefault(record["group"], record["split"]) != record["split"]:
            raise CacheError(f"Leakage group {record['group']} crosses splits")


@dataclass
class PreparedCache:
    root: Path
    manifest: dict
    images: np.ndarray      # (N, H, W, 3) uint8 RGB, memory-mapped read-only
    masks: np.ndarray       # (N, H, W) uint8 in {0 FREE, 1 BLOCKED, 255 IGNORE}
    manifest_sha256: str
    split_sha256: str
    transfer_ready: dict | None

    @classmethod
    def open(cls, manifest_path, require_verified=True) -> "PreparedCache":
        manifest_path = Path(manifest_path)
        root = manifest_path.parent
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        marker_path = root / "TRANSFER_READY.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8")) if marker_path.exists() else None
        if require_verified:
            if not manifest.get("handoff_split_verified") or marker is None:
                raise CacheError("Cache is not verified against the frozen split. Run "
                                 "`python -m autopark.perception.verify_cache` first; do not train on it.")
            if not marker.get("ready") or marker.get("mapping_sha256") != manifest["mapping_sha256"]:
                raise CacheError("TRANSFER_READY.json does not match this manifest")
        count, height, width = len(manifest["records"]), manifest["height"], manifest["width"]
        images = np.load(root / "images.npy", mmap_mode="r", allow_pickle=False)
        masks = np.load(root / "masks.npy", mmap_mode="r", allow_pickle=False)
        if images.shape != (count, height, width, 3) or images.dtype != np.uint8:
            raise CacheError(f"images.npy has shape {images.shape} / {images.dtype}")
        if masks.shape != (count, height, width) or masks.dtype != np.uint8:
            raise CacheError(f"masks.npy has shape {masks.shape} / {masks.dtype}")
        check_splits(manifest)
        return cls(root, manifest, images, masks, file_sha256(manifest_path),
                   canonical_sha256(manifest["splits"]), marker)

    def indices(self, split, limit=None) -> np.ndarray:
        indices = np.asarray(self.manifest["splits"][split], dtype=np.int64)
        if limit is not None and 0 < limit < len(indices):
            # Evenly spaced so a small subset still spans cameras and recording runs.
            indices = indices[np.linspace(0, len(indices) - 1, limit).round().astype(np.int64)]
        return indices


class SplitData:
    """One split held in host memory as uint8; batches are decoded to float on the training device."""

    def __init__(self, cache: PreparedCache, split: str, limit=None):
        self.split = split
        self.indices = cache.indices(split, limit)
        self.records = [cache.manifest["records"][i] for i in self.indices]
        self.images = torch.from_numpy(np.ascontiguousarray(cache.images[self.indices]))
        self.masks = torch.from_numpy(np.ascontiguousarray(cache.masks[self.indices]))

    def __len__(self) -> int:
        return len(self.indices)

    def order(self, seed: int, epoch: int, shuffle: bool) -> np.ndarray:
        """Positions for one epoch. A pure function of (seed, epoch), so a resumed run sees the same order."""
        if not shuffle:
            return np.arange(len(self))
        return np.random.default_rng([seed, epoch]).permutation(len(self))

    def batch(self, positions, device):
        index = torch.as_tensor(np.asarray(positions), dtype=torch.long)
        # Blocking copies: the batch is ~12 MB, and an async copy from a reused buffer could race the next batch.
        return (self.images.index_select(0, index).to(device),
                self.masks.index_select(0, index).to(device))
