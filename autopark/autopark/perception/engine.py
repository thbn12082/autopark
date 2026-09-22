"""Inference pass shared by validation during training and by the evaluation CLI."""
import numpy as np
import torch

from .augment import normalize, to_float
from .dataset import CAMERAS, SplitData
from .metrics import confusion_matrices, segmentation_loss, summarize


def autocast(device, enabled: bool):
    return torch.autocast(device_type=device.type, dtype=torch.float16, enabled=enabled and device.type == "cuda")


def decide(logits: torch.Tensor, threshold: float = 0.5) -> torch.Tensor:
    """Two-class decision: BLOCKED where P(BLOCKED) >= threshold. Exact ties go to BLOCKED, never to FREE."""
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be in (0, 1)")
    return (logits.float().softmax(1)[:, 1] >= threshold).long()


@torch.no_grad()
def evaluate_split(model, data: SplitData, *, batch_size, device, amp, num_classes=2, ignore_index=255,
                   on_batch=None, threshold: float = 0.5, sweep_thresholds=None) -> dict:
    """No augmentation, no shuffling. Returns overall and per-camera metrics plus per-image matrices.

    `on_batch(positions, images_u8, masks, logits)` lets a caller keep predictions for visualisation.
    `sweep_thresholds` additionally accumulates one overall confusion matrix per BLOCKED-probability threshold.
    """
    model.eval()
    per_image, loss_sum, pixels = [], 0.0, 0
    sweep = {float(t): torch.zeros(num_classes, num_classes, dtype=torch.int64) for t in (sweep_thresholds or ())}
    for start in range(0, len(data), batch_size):
        positions = np.arange(start, min(start + batch_size, len(data)))
        images_u8, masks = data.batch(positions, device)
        with autocast(device, amp):
            logits = model(normalize(to_float(images_u8)))["out"]
        loss, valid = segmentation_loss(logits, masks, ignore_index)
        loss_sum += float(loss) * int(valid)
        pixels += int(valid)
        per_image.append(confusion_matrices(decide(logits, threshold), masks, num_classes, ignore_index).cpu())
        if sweep:
            blocked = logits.float().softmax(1)[:, 1]
            for t in sweep:
                sweep[t] += confusion_matrices((blocked >= t).long(), masks, num_classes, ignore_index).sum(0).cpu()
        if on_batch is not None:
            on_batch(positions, images_u8, masks, logits)
    per_image = torch.cat(per_image)
    cameras = [record["camera"] for record in data.records]
    report = {"split": data.split, "images": len(data), "loss": loss_sum / max(1, pixels), "threshold": threshold,
              **summarize(per_image.sum(0)), "per_camera": {}}
    for camera in CAMERAS:
        rows = [i for i, name in enumerate(cameras) if name == camera]
        if rows:
            report["per_camera"][camera] = {"images": len(rows), **summarize(per_image[rows].sum(0))}
    return {"report": report, "per_image": per_image, "sweep": {t: summarize(m) for t, m in sweep.items()}}
