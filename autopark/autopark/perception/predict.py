"""Run a trained checkpoint on stored image files and save label map, BLOCKED probability and overlay.

    python -m autopark.perception.predict --checkpoint runs/<name>/best.pt --input some_image.png --out runs/<name>/predict

Preprocessing is the cache's own letterbox (same function, same interpolation), undone afterwards so outputs
match the input size. The model only knows FREE and BLOCKED: regions that were IGNORE in training (sky, ego
vehicle, image border) still receive one of the two labels and mean nothing there. A FREE pixel is a candidate
on a stored image, not proof that a vehicle can drive over it.
"""
import argparse
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import torch

from .augment import normalize, to_float
from .checkpoint import atomic_write_json, load_checkpoint
from .data import letterbox, read_image
from .dataset import file_sha256
from .engine import autocast
from .model import build_model
from .train import utc_now

EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp")
FREE_BGR, BLOCKED_BGR = (0, 170, 0), (40, 40, 220)


def _write(path: Path, image, extension: str) -> None:
    ok, encoded = cv2.imencode(extension, image)      # imwrite cannot handle non-ASCII Windows paths
    if not ok:
        raise ValueError(f"Cannot encode {path}")
    path.write_bytes(encoded.tobytes())


@torch.no_grad()
def predict_image(model, image_bgr, height: int, width: int, device, amp: bool):
    """Returns (labels uint8 {0 FREE, 1 BLOCKED}, probability of BLOCKED float32), both at the input size."""
    original_height, original_width = image_bgr.shape[:2]
    prepared, _, box = letterbox(image_bgr, np.zeros((original_height, original_width), np.uint8), height, width)
    rgb = torch.from_numpy(cv2.cvtColor(prepared, cv2.COLOR_BGR2RGB)).unsqueeze(0).to(device)
    with autocast(device, amp):
        logits = model(normalize(to_float(rgb)))["out"]
    blocked = logits.float().softmax(1)[0, 1].cpu().numpy()
    blocked = blocked[box["y"]:box["y"] + box["height"], box["x"]:box["x"] + box["width"]]
    blocked = cv2.resize(blocked, (original_width, original_height), interpolation=cv2.INTER_LINEAR)
    return (blocked >= 0.5).astype(np.uint8), blocked


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True, help="image file or a directory of images")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    args = parser.parse_args(argv)
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable. Pass --device cpu explicitly if a slow CPU run is intended.")
    device = torch.device(args.device)
    files = [args.input] if args.input.is_file() else sorted(
        p for p in args.input.iterdir() if p.suffix.lower() in EXTENSIONS)
    if not files:
        raise SystemExit(f"No images found at {args.input}")

    state = load_checkpoint(args.checkpoint)
    cfg = state["config"]
    model = build_model(cfg["num_classes"], pretrained=False)
    model.load_state_dict(state["model"])
    model.to(device).eval()
    amp = bool(cfg["amp"]) and device.type == "cuda"

    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    for path in files:
        image = read_image(path)
        tick = time.perf_counter()
        labels, blocked = predict_image(model, image, cfg["height"], cfg["width"], device, amp)
        if device.type == "cuda":
            torch.cuda.synchronize()
        seconds = time.perf_counter() - tick
        colors = np.where(labels[..., None] == 1, np.array(BLOCKED_BGR, np.uint8), np.array(FREE_BGR, np.uint8))
        _write(args.out / f"{path.stem}_labels.png", labels, ".png")
        _write(args.out / f"{path.stem}_prob_blocked.png", np.round(blocked * 255).astype(np.uint8), ".png")
        _write(args.out / f"{path.stem}_overlay.jpg", cv2.addWeighted(image, 0.5, colors, 0.5, 0), ".jpg")
        results.append({"file": path.name, "size": [int(image.shape[1]), int(image.shape[0])],
                        "blocked_fraction": float(labels.mean()), "seconds_including_pre_post": seconds})
        print(f"{path.name}: blocked {labels.mean():.1%} in {seconds * 1000:.0f} ms", flush=True)
    atomic_write_json(args.out / "predictions.json", {
        "created_utc": utc_now(), "checkpoint": str(args.checkpoint), "checkpoint_sha256": file_sha256(args.checkpoint),
        "checkpoint_epoch": state["epoch"], "device": str(device), "model_input": [cfg["height"], cfg["width"]],
        "labels": {"0": "FREE_CANDIDATE", "1": "OBSTACLE_OR_BLOCKED"},
        "limitations": "Two-class output only: sky, ego vehicle and border regions were IGNORE in training and their "
                       "labels are meaningless. FREE is a candidate on a stored image, not verified traversability. "
                       "The first image includes CUDA warm-up time.",
        "results": results})
    return 0


if __name__ == "__main__":
    sys.exit(main())
