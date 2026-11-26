"""Measure training/inference throughput and peak VRAM on real batches before choosing batch_size.

    python -m autopark.perception.benchmark --config configs/train_woodscape_rtx4000_baseline.json \
        --out runs/<name>/benchmark.json --batch-sizes 8 16 32

Every candidate runs the trainer's own step (augment, AMP forward, backward, clip, optimizer step) on images from
the train split only. Numbers are measured after warm-up; nothing here is inferred from GPU specifications.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import torch

from .augment import AugmentConfig, augment, normalize, step_generator, to_float
from .checkpoint import atomic_write_json
from .dataset import PreparedCache, SplitData
from .engine import autocast
from .metrics import segmentation_loss
from .model import build_model, parameter_groups
from .train import PRETRAINED, PROJECT, environment_info, load_config, utc_now


def _gpu_memory_used_mb():
    try:
        return int(subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                           text=True, timeout=15).split()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def measure(cfg: dict, data: SplitData, batch_size: int, warmup: int, steps: int, device) -> dict:
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    model = build_model(cfg["num_classes"], pretrained=cfg["initialization"] == PRETRAINED)
    model.to(device)
    optimizer = torch.optim.AdamW(parameter_groups(model, cfg["backbone_lr"], cfg["head_lr"]),
                                  weight_decay=cfg["weight_decay"])
    scaler = torch.amp.GradScaler(device.type, enabled=cfg["amp"])
    augment_cfg = AugmentConfig(**cfg["augment"])
    order = data.order(cfg["seed"], 0, shuffle=True)
    result = {"batch_size": batch_size, "warmup_steps": warmup, "measured_steps": steps, "oom": False}
    try:
        model.train()
        data_seconds = step_seconds = 0.0
        for step in range(warmup + steps):
            if step == warmup:
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                data_seconds = step_seconds = 0.0
            tick = time.perf_counter()
            positions = order[step * batch_size:(step + 1) * batch_size]
            images_u8, masks = data.batch(positions, device)
            images, masks = augment(to_float(images_u8), masks, augment_cfg,
                                    step_generator(device, cfg["seed"], 0, step))
            torch.cuda.synchronize()
            loaded = time.perf_counter()
            optimizer.zero_grad(set_to_none=True)
            with autocast(device, cfg["amp"]):
                logits = model(normalize(images))["out"]
            loss, _ = segmentation_loss(logits, masks, cfg["ignore_index"])
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), cfg["grad_clip_norm"])
            scaler.step(optimizer)
            scaler.update()
            torch.cuda.synchronize()
            done = time.perf_counter()
            data_seconds += loaded - tick
            step_seconds += done - tick
        if not torch.isfinite(loss):
            raise FloatingPointError("Benchmark loss is not finite")
        result.update({
            "train_images_per_second": steps * batch_size / step_seconds,
            "train_seconds_per_batch": step_seconds / steps,
            "data_and_augment_fraction": data_seconds / step_seconds,
            "train_peak_allocated_mb": torch.cuda.max_memory_allocated() / 2**20,
            "train_peak_reserved_mb": torch.cuda.max_memory_reserved() / 2**20,
            "nvidia_smi_memory_used_mb": _gpu_memory_used_mb(), "last_loss": float(loss.detach())})

        model.eval()
        eval_batch = cfg["eval_batch_size"]
        eval_steps = max(4, steps // 4)
        with torch.no_grad():
            for step in range(2 + eval_steps):
                if step == 2:
                    torch.cuda.synchronize()
                    tick = time.perf_counter()
                images_u8, _ = data.batch(np.arange(step * eval_batch, (step + 1) * eval_batch) % len(data), device)
                with autocast(device, cfg["amp"]):
                    model(normalize(to_float(images_u8)))["out"].argmax(1)
            torch.cuda.synchronize()
        result.update({"eval_batch_size": eval_batch,
                       "eval_images_per_second": eval_steps * eval_batch / (time.perf_counter() - tick)})
    except torch.cuda.OutOfMemoryError as exc:
        result.update({"oom": True, "error": str(exc)[:300],
                       "peak_allocated_mb_before_oom": torch.cuda.max_memory_allocated() / 2**20})
    finally:
        del model, optimizer
        torch.cuda.empty_cache()
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-sizes", type=int, nargs="+", default=[8, 16, 32])
    parser.add_argument("--warmup", type=int, default=15)
    parser.add_argument("--steps", type=int, default=60)
    args = parser.parse_args(argv)
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable; this benchmark does not fall back to CPU.")
    device = torch.device("cuda")
    torch.backends.cudnn.benchmark = True

    # batch_size may still be null in the proposed config; each candidate is validated as a real value.
    cfg = load_config(args.config, [f"batch_size={args.batch_sizes[0]}"])
    cache = PreparedCache.open(PROJECT / cfg["prepared_manifest"], cfg["require_handoff_split_verified"])
    needed = (args.warmup + args.steps) * max(args.batch_sizes)
    data = SplitData(cache, "train", min(needed, len(cache.manifest["splits"]["train"])))
    train_images, val_images = len(cache.manifest["splits"]["train"]), len(cache.manifest["splits"]["val"])

    props = torch.cuda.get_device_properties(0)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "created_utc": utc_now(), "complete": False, "config_file": str(args.config), "height": cfg["height"],
        "width": cfg["width"], "amp": cfg["amp"], "model": cfg["model"],
        "data": "real train-split batches with training augmentation",
        "gpu": props.name, "vram_total_mb": props.total_memory / 2**20,
        "gpu_memory_used_before_mb_note": "nvidia_smi_memory_used_mb includes other processes on the desktop GPU",
        "train_images": train_images, "validation_images": val_images, "batch_sizes_requested": args.batch_sizes,
        "results": [], "environment": environment_info()}
    for batch_size in args.batch_sizes:
        if (args.warmup + args.steps) * batch_size > len(data):
            raise SystemExit(f"Not enough train images for batch {batch_size}")
        result = measure(load_config(args.config, [f"batch_size={batch_size}"]), data, batch_size,
                         args.warmup, args.steps, device)
        if not result["oom"]:
            result["estimated_seconds_per_epoch"] = (train_images / result["train_images_per_second"]
                                                     + val_images / result["eval_images_per_second"])
        report["results"].append(result)
        print(result, flush=True)
        atomic_write_json(args.out, report)      # keep finished candidates even if a later one is interrupted
    report["complete"] = True
    atomic_write_json(args.out, report)
    print(f"Wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
