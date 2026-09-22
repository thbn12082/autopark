"""Atomic files and checkpoints that load with torch's restricted unpickler (tensors + plain containers)."""
import json
import os
from pathlib import Path
import random

import numpy as np
import torch

from .paths import atomic_write_json  # noqa: F401  (re-exported; torch-free modules import it from .paths)


def atomic_save(state: dict, path) -> None:
    """A crash mid-write leaves the previous checkpoint intact instead of a truncated file."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    torch.save(state, temporary)
    os.replace(temporary, path)


def load_checkpoint(path, map_location="cpu") -> dict:
    return torch.load(path, map_location=map_location, weights_only=True)


def rng_state() -> dict:
    numpy_state = np.random.get_state()
    return {"python": random.getstate(),
            "numpy": [numpy_state[0], numpy_state[1].tolist(), *numpy_state[2:]],
            "torch": torch.get_rng_state(),
            "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else []}


def restore_rng_state(state: dict) -> None:
    version, internal, gauss = state["python"]
    random.setstate((version, tuple(internal), gauss))
    name, keys, *rest = state["numpy"]
    np.random.set_state((name, np.asarray(keys, dtype=np.uint32), *rest))
    torch.set_rng_state(state["torch"].cpu())
    if torch.cuda.is_available() and len(state["cuda"]) == torch.cuda.device_count():
        torch.cuda.set_rng_state_all([s.cpu() for s in state["cuda"]])
