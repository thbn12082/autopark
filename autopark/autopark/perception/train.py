"""Train the WoodScape FREE/BLOCKED baseline: AMP, atomic checkpoints, exact resume, controlled stop.

    python -m autopark.perception.train --config configs/train_woodscape_rtx4000_baseline.json --out runs/<name>
    python -m autopark.perception.train --out runs/<name> --resume runs/<name>/latest.pt

Create an empty file named STOP in the run directory (or press Ctrl+C) to stop after the current update: the
run saves `latest.pt` and ends in state "stopped". Model selection uses validation mIoU only; the held-out
test split is never read here.
"""
import argparse
import copy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import signal
import subprocess
import sys
import time
import traceback
import zipfile

import numpy as np
import torch

from .augment import AugmentConfig, augment, normalize, step_generator, to_float
from .checkpoint import atomic_save, atomic_write_json, load_checkpoint, restore_rng_state, rng_state
from .dataset import PreparedCache, SplitData, file_sha256
from .engine import autocast, evaluate_split
from .metrics import segmentation_loss
from .model import build_model, parameter_groups

from .paths import PROJECT, utc_now  # noqa: E402  (shared with torch-free modules)
PRETRAINED = "torchvision_official_pretrained_weights"
MAX_CONSECUTIVE_BAD_UPDATES = 10

DEFAULTS = {
    "model": "lraspp_mobilenet_v3_large",
    "initialization": PRETRAINED,
    "num_classes": 2,
    "ignore_index": 255,
    "prepared_manifest": "datasets/prepared/woodscape_binary_v1/manifest.json",
    "require_handoff_split_verified": True,
    "height": 384,
    "width": 512,
    "seed": 20260920,
    "epochs": 30,
    "early_stopping_patience": 8,
    "batch_size": None,
    "eval_batch_size": 32,
    "grad_accum_steps": 1,
    "amp": True,
    "optimizer": "AdamW",
    "backbone_lr": 1e-4,
    "head_lr": 1e-3,
    "weight_decay": 1e-4,
    "lr_schedule": "warmup_poly",
    "warmup_updates": 300,
    "poly_power": 0.9,
    "grad_clip_norm": 10.0,
    "class_weights": "none",
    "augment": asdict(AugmentConfig()),
    "checkpoint_every_optimizer_steps": 200,
    "log_every_optimizer_steps": 20,
    "select_checkpoint_by": "validation_mIoU",
    "validation_split": "val",
    "limit_train": None,
    "limit_val": None,
    "device": "cuda",          # "cpu" is honoured only together with allow_cpu (deterministic tests)
    "allow_cpu": False,
}


class StopRequested(Exception):
    pass


def _merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path, overrides=()) -> dict:
    cfg = _merge(copy.deepcopy(DEFAULTS), json.loads(Path(path).read_text(encoding="utf-8")))
    for item in overrides:
        key, _, raw = item.partition("=")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        target = cfg
        *parents, leaf = key.split(".")
        for name in parents:
            target = target.setdefault(name, {})
        target[leaf] = value
    validate_config(cfg)
    return cfg


def validate_config(cfg: dict) -> None:
    if not isinstance(cfg["batch_size"], int) or cfg["batch_size"] < 1:
        raise ValueError("batch_size is not set. Run `python -m autopark.perception.benchmark` and record the "
                         "measured choice in the config before training.")
    expected = {"model": "lraspp_mobilenet_v3_large", "optimizer": "AdamW", "num_classes": 2,
                "ignore_index": 255, "select_checkpoint_by": "validation_mIoU", "lr_schedule": "warmup_poly"}
    for key, value in expected.items():
        if cfg[key] != value:
            raise ValueError(f"Unsupported {key}={cfg[key]!r}; this trainer implements {value!r}")
    if cfg["validation_split"] not in ("val", "train"):
        raise ValueError("validation_split must be 'val' (or 'train' for an overfit check); never the test split")
    if cfg["class_weights"] not in ("none", "train_inverse_frequency"):
        raise ValueError("class_weights must be 'none' or 'train_inverse_frequency'")
    if cfg["epochs"] < 1 or cfg["grad_accum_steps"] < 1 or cfg["eval_batch_size"] < 1:
        raise ValueError("epochs, grad_accum_steps and eval_batch_size must be >= 1")
    AugmentConfig(**cfg["augment"])


def lr_factor(update: int, total: int, warmup: int, power: float) -> float:
    if update < warmup:
        return (update + 1) / warmup
    return max(0.0, 1.0 - (update - warmup) / max(1, total - warmup)) ** power


def environment_info() -> dict:
    info = {"python": sys.version, "platform": platform.platform(), "processor": platform.processor(),
            "torch": torch.__version__, "torch_cuda": torch.version.cuda, "numpy": np.__version__,
            "cudnn": torch.backends.cudnn.version() if torch.cuda.is_available() else None,
            "cuda_available": torch.cuda.is_available()}
    try:
        import cv2
        import torchvision
        info["torchvision"], info["opencv"] = torchvision.__version__, cv2.__version__
    except ImportError as exc:
        info["import_error"] = str(exc)
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        info["gpu"] = {"name": props.name, "vram_bytes": props.total_memory,
                       "capability": list(torch.cuda.get_device_capability(0))}
    for key, command in (("nvidia_smi", ["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                                         "--format=csv,noheader"]),
                         ("pip_freeze", [sys.executable, "-m", "pip", "freeze"])):
        try:
            info[key] = subprocess.check_output(command, text=True, timeout=60).strip().splitlines()
        except (OSError, subprocess.SubprocessError) as exc:
            info[key] = f"unavailable: {exc}"
    return info


def snapshot_source(run_dir: Path, config_path: Path | None) -> dict:
    """Same idea as storage/run_store.py: keep the exact code that produced the run, with hashes."""
    files = sorted((PROJECT / "autopark/perception").glob("*.py")) + [PROJECT / "configs/woodscape_binary_v1.json"]
    if config_path is not None:
        files.append(config_path)
    hashes = {}
    with zipfile.ZipFile(run_dir / "source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            path = path.resolve()
            name = path.relative_to(PROJECT).as_posix() if path.is_relative_to(PROJECT) else path.name
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            archive.write(path, name)
    return hashes


class Trainer:
    def __init__(self, cfg: dict, run_dir: Path, resume_state: dict | None = None, config_path: Path | None = None):
        self.cfg, self.run_dir, self.config_path = cfg, run_dir, config_path
        self.stop_flag = False
        self.started = time.perf_counter()
        self.started_utc = utc_now()
        self.device = self._device()
        seed = cfg["seed"]
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        # Fixed input size, so autotuned kernels pay off. They are not bitwise deterministic; seeds fix the
        # data order and augmentation, not every floating-point sum.
        torch.backends.cudnn.benchmark = True

        self.cache = PreparedCache.open(PROJECT / cfg["prepared_manifest"], cfg["require_handoff_split_verified"])
        if (self.cache.manifest["height"], self.cache.manifest["width"]) != (cfg["height"], cfg["width"]):
            raise ValueError("Config size differs from the prepared cache")
        self.log(f"Loading splits into host memory from {self.cache.root}")
        self.train_data = SplitData(self.cache, "train", cfg["limit_train"])
        self.val_data = SplitData(self.cache, cfg["validation_split"], cfg["limit_val"])

        self.batch_size, self.accum = cfg["batch_size"], cfg["grad_accum_steps"]
        self.updates_per_epoch = (len(self.train_data) // self.batch_size) // self.accum
        if self.updates_per_epoch < 1:
            raise ValueError("Training subset is smaller than one optimizer update")
        self.total_updates = cfg["epochs"] * self.updates_per_epoch
        self.warmup = min(cfg["warmup_updates"], self.total_updates // 5)

        self.model = build_model(cfg["num_classes"], pretrained=cfg["initialization"] == PRETRAINED)
        # Plain NCHW on purpose: channels_last measured 5.5x slower in train mode here (51 vs 282 img/s at
        # batch 16, torch 2.11 + cuDNN 9.19 on Windows); see runs/ai_woodscape_rtx4000_v1/diagnosis_channels_last.json.
        self.model.to(self.device)
        self.optimizer = torch.optim.AdamW(parameter_groups(self.model, cfg["backbone_lr"], cfg["head_lr"]),
                                           weight_decay=cfg["weight_decay"])
        self.scheduler = torch.optim.lr_scheduler.LambdaLR(
            self.optimizer, lambda u: lr_factor(u, self.total_updates, self.warmup, cfg["poly_power"]))
        self.amp = bool(cfg["amp"]) and self.device.type == "cuda"
        self.scaler = torch.amp.GradScaler(self.device.type, enabled=self.amp)
        self.augment_cfg = AugmentConfig(**cfg["augment"])
        self.class_weights = self._class_weights()

        self.epoch, self.update_in_epoch, self.global_update = 0, 0, 0
        self.best = {"mIoU": None, "epoch": None}
        self.epochs_without_improvement = 0
        self.history: list[dict] = []
        self.counters = {"amp_skipped_updates": 0, "nonfinite_loss_updates": 0, "all_ignore_updates": 0}
        self.epoch_loss_sum, self.epoch_loss_updates, self.epoch_seconds = 0.0, 0, 0.0
        self.last_validation: dict | None = None
        if resume_state is not None:
            self._restore(resume_state)

    # ------------------------------------------------------------------ setup
    def _device(self) -> torch.device:
        if torch.cuda.is_available() and self.cfg["device"] != "cpu":
            return torch.device("cuda")
        if self.cfg["allow_cpu"]:
            return torch.device("cpu")
        raise RuntimeError("CUDA is unavailable. Fix the driver / CUDA build of torch; this run does not fall "
                           "back to CPU silently (set allow_cpu only for tests).")

    def _class_weights(self):
        if self.cfg["class_weights"] == "none":
            return None
        pixels = self.cache.manifest["statistics"]["train"]["pixels"]   # train only: no val/test statistics
        counts = torch.tensor([pixels["0"], pixels["1"]], dtype=torch.float64)
        return (counts.sum() / (len(counts) * counts)).float().to(self.device)

    def _restore(self, state: dict) -> None:
        for key, current in (("split_sha256", self.cache.split_sha256),
                             ("mapping_sha256", self.cache.manifest["mapping_sha256"])):
            if state[key] != current:
                raise ValueError(f"Checkpoint {key} differs from the current cache; refusing to resume")
        self.model.load_state_dict(state["model"])
        self.optimizer.load_state_dict(state["optimizer"])
        self.scheduler.load_state_dict(state["scheduler"])
        self.scaler.load_state_dict(state["scaler"])
        self.epoch, self.update_in_epoch = state["epoch"], state["update_in_epoch"]
        self.global_update, self.best = state["global_update"], dict(state["best"])
        self.epochs_without_improvement = state["epochs_without_improvement"]
        self.history, self.counters = list(state["history"]), dict(state["counters"])
        self.epoch_loss_sum, self.epoch_loss_updates = state["epoch_loss_sum"], state["epoch_loss_updates"]
        self.epoch_seconds = state["epoch_seconds"]
        restore_rng_state(state["rng"])
        self.log(f"Resumed at epoch {self.epoch}, update {self.update_in_epoch}/{self.updates_per_epoch} "
                 f"(global update {self.global_update})")

    # ------------------------------------------------------------------ bookkeeping
    def log(self, message: str) -> None:
        line = f"[{utc_now()}] {message}"
        print(line, flush=True)
        with (self.run_dir / "train.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _append(self, name: str, record: dict) -> None:
        with (self.run_dir / name).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")

    def write_status(self, state: str, message: str = "") -> None:
        atomic_write_json(self.run_dir / "status.json", {
            "state": state, "message": message, "pid": os.getpid(), "started_utc": self.started_utc,
            "updated_utc": utc_now(), "epoch": self.epoch, "epochs_total": self.cfg["epochs"],
            "update_in_epoch": self.update_in_epoch, "updates_per_epoch": self.updates_per_epoch,
            "global_update": self.global_update, "best_val_mIoU": self.best["mIoU"],
            "best_epoch": self.best["epoch"], "last_validation": self.last_validation,
            "counters": self.counters,
            "note": "If state is 'running' but updated_utc is old and the pid is gone, the process was killed; "
                    "resume from latest.pt."})

    def save(self, name: str) -> None:
        atomic_save({
            "format": 1, "model": self.model.state_dict(), "optimizer": self.optimizer.state_dict(),
            "scheduler": self.scheduler.state_dict(), "scaler": self.scaler.state_dict(),
            "epoch": self.epoch, "update_in_epoch": self.update_in_epoch, "global_update": self.global_update,
            "best": self.best, "epochs_without_improvement": self.epochs_without_improvement,
            "history": self.history, "counters": self.counters, "epoch_loss_sum": self.epoch_loss_sum,
            "epoch_loss_updates": self.epoch_loss_updates, "epoch_seconds": self.epoch_seconds,
            "config": self.cfg, "split_sha256": self.cache.split_sha256,
            "mapping_sha256": self.cache.manifest["mapping_sha256"],
            "manifest_sha256": self.cache.manifest_sha256, "rng": rng_state(),
            # str(): torch.__version__ is a TorchVersion object, which the restricted unpickler refuses.
            "versions": {"torch": str(torch.__version__), "python": platform.python_version()},
            "saved_utc": utc_now()}, self.run_dir / name)

    def write_manifest(self, resumed_from: str | None) -> None:
        path = self.run_dir / "run_manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"resumes": []}
        if resumed_from:
            manifest["resumes"].append({"utc": utc_now(), "checkpoint": resumed_from,
                                        "epoch": self.epoch, "update_in_epoch": self.update_in_epoch})
        else:
            weights = None
            if self.cfg["initialization"] == PRETRAINED:
                candidates = sorted((Path(torch.hub.get_dir()) / "checkpoints").glob("lraspp_mobilenet_v3_large-*.pth"))
                weights = [{"file": p.name, "sha256": file_sha256(p)} for p in candidates]
            manifest.update({
                "schema_version": 1, "evidence": "offline_training_on_stored_images", "created_utc": utc_now(),
                "command": sys.argv, "config": self.cfg,
                "config_file": str(self.config_path) if self.config_path else None,
                "environment": environment_info(), "pretrained_weights": weights,
                "data": {"manifest": self.cfg["prepared_manifest"], "manifest_sha256": self.cache.manifest_sha256,
                         "split_sha256": self.cache.split_sha256,
                         "mapping_sha256": self.cache.manifest["mapping_sha256"],
                         "transfer_ready": self.cache.transfer_ready,
                         "train_images": len(self.train_data), "validation_images": len(self.val_data),
                         "validation_split": self.cfg["validation_split"], "test_split_read": False},
                "schedule": {"updates_per_epoch": self.updates_per_epoch, "total_updates": self.total_updates,
                             "warmup_updates": self.warmup},
                "source_sha256": snapshot_source(self.run_dir, self.config_path),
                "git": "repository has no commits; source.zip holds the code used",
                "determinism": "seeded order and augmentation; cuDNN autotuned AMP kernels are not bitwise "
                               "deterministic"})
        atomic_write_json(path, manifest)

    # ------------------------------------------------------------------ stopping
    def request_stop(self, *_) -> None:
        self.stop_flag = True

    def _check_stop(self) -> None:
        if self.stop_flag or (self.run_dir / "STOP").exists():
            self.save("latest.pt")
            raise StopRequested

    # ------------------------------------------------------------------ training
    def train_epoch(self) -> dict:
        cfg, device = self.cfg, self.device
        self.model.train()
        order = self.train_data.order(cfg["seed"], self.epoch, shuffle=True)
        window_loss, window_updates, window_start, consecutive_bad = 0.0, 0, time.perf_counter(), 0
        grad_norm = float("nan")
        for update in range(self.update_in_epoch, self.updates_per_epoch):
            tick = time.perf_counter()
            self.optimizer.zero_grad(set_to_none=True)
            loss_value, valid_pixels = 0.0, 0
            for micro in range(self.accum):
                step = update * self.accum + micro
                positions = order[step * self.batch_size:(step + 1) * self.batch_size]
                images_u8, masks = self.train_data.batch(positions, device)
                images, masks = augment(to_float(images_u8), masks, self.augment_cfg,
                                        step_generator(device, cfg["seed"], self.epoch, step))
                with autocast(device, self.amp):
                    logits = self.model(normalize(images))["out"]
                loss, valid = segmentation_loss(logits, masks, cfg["ignore_index"], self.class_weights)
                self.scaler.scale(loss / self.accum).backward()
                loss_value += float(loss.detach()) / self.accum
                valid_pixels += int(valid)

            if not math.isfinite(loss_value):
                self.counters["nonfinite_loss_updates"] += 1
                consecutive_bad += 1
                if consecutive_bad >= MAX_CONSECUTIVE_BAD_UPDATES:
                    raise FloatingPointError(f"{consecutive_bad} consecutive non-finite losses at epoch "
                                             f"{self.epoch}, update {update}")
            elif valid_pixels == 0:
                self.counters["all_ignore_updates"] += 1   # nothing to learn from: no optimizer step at all
            else:
                consecutive_bad = 0
                self.scaler.unscale_(self.optimizer)
                grad_norm = float(torch.nn.utils.clip_grad_norm_(self.model.parameters(), cfg["grad_clip_norm"]))
                scale_before = self.scaler.get_scale()
                self.scaler.step(self.optimizer)
                self.scaler.update()
                if self.scaler.get_scale() >= scale_before:
                    self.scheduler.step()      # one scheduler step per optimizer step that really happened
                else:
                    self.counters["amp_skipped_updates"] += 1
                window_loss += loss_value
                window_updates += 1
                self.epoch_loss_sum += loss_value
                self.epoch_loss_updates += 1

            self.update_in_epoch, self.global_update = update + 1, self.global_update + 1
            self.epoch_seconds += time.perf_counter() - tick
            if self.global_update % cfg["log_every_optimizer_steps"] == 0:
                seconds = time.perf_counter() - window_start
                images = cfg["log_every_optimizer_steps"] * self.accum * self.batch_size
                record = {"utc": utc_now(), "epoch": self.epoch, "update_in_epoch": self.update_in_epoch,
                          "global_update": self.global_update,
                          "loss": window_loss / window_updates if window_updates else None,
                          "lr_backbone": self.optimizer.param_groups[0]["lr"],
                          "lr_head": self.optimizer.param_groups[1]["lr"],
                          "grad_norm": grad_norm if math.isfinite(grad_norm) else None,
                          "images_per_second": images / seconds, "amp_scale": self.scaler.get_scale(),
                          "vram_peak_allocated_mb": self._vram()[0]}
                self._append("train_steps.jsonl", record)
                self.log(f"epoch {self.epoch + 1}/{cfg['epochs']} update {self.update_in_epoch}/"
                         f"{self.updates_per_epoch} loss {record['loss']:.4f} lr_head {record['lr_head']:.2e} "
                         f"{record['images_per_second']:.0f} img/s" if record["loss"] is not None else
                         f"epoch {self.epoch + 1} update {self.update_in_epoch}: no valid updates in window")
                self.write_status("running")
                window_loss, window_updates, window_start = 0.0, 0, time.perf_counter()
            if self.global_update % cfg["checkpoint_every_optimizer_steps"] == 0:
                self.save("latest.pt")
            self._check_stop()
        return {"train_loss": self.epoch_loss_sum / self.epoch_loss_updates if self.epoch_loss_updates else None,
                "train_seconds": self.epoch_seconds,
                "train_images_per_second": self.updates_per_epoch * self.accum * self.batch_size
                                           / self.epoch_seconds if self.epoch_seconds else None}

    def _vram(self) -> tuple[float, float]:
        if self.device.type != "cuda":
            return 0.0, 0.0
        return (torch.cuda.max_memory_allocated() / 2**20, torch.cuda.max_memory_reserved() / 2**20)

    def run(self) -> str:
        cfg = self.cfg
        self.write_status("running", "training")
        self.log(f"Training {len(self.train_data)} images, validating on {len(self.val_data)} "
                 f"('{cfg['validation_split']}'); batch {self.batch_size} x accum {self.accum}, "
                 f"{self.updates_per_epoch} updates/epoch, AMP={self.amp}, device={self.device}")
        finish = "all_epochs"
        while self.epoch < cfg["epochs"]:
            train_report = self.train_epoch()
            tick = time.perf_counter()
            validation = evaluate_split(self.model, self.val_data, batch_size=cfg["eval_batch_size"],
                                        device=self.device, amp=self.amp, num_classes=cfg["num_classes"],
                                        ignore_index=cfg["ignore_index"])["report"]
            score = validation["mIoU"]
            if score is None or not math.isfinite(validation["loss"]):
                raise FloatingPointError(f"Validation produced no usable metric at epoch {self.epoch + 1}")
            improved = self.best["mIoU"] is None or score > self.best["mIoU"]
            allocated, reserved = self._vram()
            record = {"epoch": self.epoch + 1, "utc": utc_now(), **train_report,
                      "validation_seconds": time.perf_counter() - tick, "validation": validation,
                      "improved": improved, "vram_peak_allocated_mb": allocated, "vram_peak_reserved_mb": reserved,
                      "lr_head_end": self.optimizer.param_groups[1]["lr"], "counters": dict(self.counters)}
            self.history.append(record)
            self._append("epochs.jsonl", record)
            self.last_validation = {k: validation[k] for k in ("mIoU", "iou_free", "iou_blocked", "loss",
                                                               "blocked_recall", "blocked_precision",
                                                               "blocked_as_free_rate")}
            self.epoch += 1
            self.update_in_epoch, self.epoch_loss_sum, self.epoch_loss_updates, self.epoch_seconds = 0, 0.0, 0, 0.0
            if improved:
                self.best, self.epochs_without_improvement = {"mIoU": score, "epoch": self.epoch}, 0
            else:
                self.epochs_without_improvement += 1
            self.save("latest.pt")
            if improved:
                self.save("best.pt")
            self.log(f"epoch {self.epoch} done: train_loss {train_report['train_loss']:.4f} | val mIoU {score:.4f} "
                     f"(free {validation['iou_free']:.4f}, blocked {validation['iou_blocked']:.4f}) "
                     f"blocked->free {validation['blocked_as_free_rate']:.4f} | "
                     f"{'BEST' if improved else f'no improvement x{self.epochs_without_improvement}'}")
            self.write_status("running")
            patience = cfg["early_stopping_patience"]
            if patience and self.epochs_without_improvement >= patience:
                finish = "early_stopping"
                break
            self._check_stop()
        allocated, reserved = self._vram()
        atomic_write_json(self.run_dir / "training_summary.json", {
            "finish_reason": finish, "epochs_run": self.epoch, "best": self.best, "global_updates": self.global_update,
            "wall_seconds_this_process": time.perf_counter() - self.started, "counters": self.counters,
            "vram_peak_allocated_mb": allocated, "vram_peak_reserved_mb": reserved,
            "best_validation": next((h["validation"] for h in self.history if h["epoch"] == self.best["epoch"]), None),
            "test_split_read": False, "finished_utc": utc_now()})
        return finish


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="override a config value (JSON), e.g. --set epochs=1 --set augment.enabled=false")
    args = parser.parse_args(argv)

    run_dir = args.out
    resume_state = None
    if args.resume:
        if args.set:
            parser.error("--set cannot be combined with --resume; a resumed run keeps its original config")
        resume_state = load_checkpoint(args.resume)
        cfg = resume_state["config"]
        if args.config and load_config(args.config) != cfg:
            print("WARNING: --config differs from the checkpoint; continuing with the checkpoint's config", flush=True)
    else:
        if not args.config:
            parser.error("--config is required unless --resume is given")
        if (run_dir / "status.json").exists():
            parser.error(f"{run_dir} already holds a run; pick a new --out or use --resume")
        cfg = load_config(args.config, args.set)
    run_dir.mkdir(parents=True, exist_ok=True)
    stop_file = run_dir / "STOP"
    if stop_file.exists():
        parser.error(f"{stop_file} exists; remove it before starting")

    trainer = None
    try:
        trainer = Trainer(cfg, run_dir, resume_state, args.config.resolve() if args.config else None)
        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), trainer.request_stop)
        atomic_write_json(run_dir / "config_resolved.json", cfg)
        trainer.write_manifest(str(args.resume) if args.resume else None)
        finish = trainer.run()
        trainer.write_status("completed", finish)
        trainer.log(f"Completed ({finish}). Best validation mIoU {trainer.best['mIoU']:.4f} at epoch "
                    f"{trainer.best['epoch']}.")
        return 0
    except StopRequested:
        trainer.write_status("stopped", "stop requested; latest.pt saved, resume with --resume")
        trainer.log("Stopped on request; latest.pt saved.")
        return 3
    except BaseException as exc:
        detail = "".join(traceback.format_exception(exc))
        if trainer is not None:
            trainer.write_status("failed", f"{type(exc).__name__}: {exc}")
            trainer.log("FAILED\n" + detail)
        else:
            atomic_write_json(run_dir / "status.json", {"state": "failed", "updated_utc": utc_now(),
                                                         "message": f"{type(exc).__name__}: {exc}",
                                                         "traceback": detail})
        raise


if __name__ == "__main__":
    sys.exit(main())
