"""Loss and confusion-matrix metrics with IGNORE excluded. Rows are ground truth, columns are predictions."""
import torch
import torch.nn.functional as F

FREE, BLOCKED = 0, 1


def segmentation_loss(logits, target, ignore_index=255, class_weights=None):
    """Mean cross-entropy over non-ignored pixels. An all-ignore batch gives a finite zero, not NaN.

    Returns (loss, valid_pixel_count); both stay on the device so the caller decides when to synchronize.
    """
    target = target.long()
    valid = target != ignore_index
    total = F.cross_entropy(logits.float(), target, weight=class_weights, ignore_index=ignore_index,
                            reduction="sum")
    denominator = valid.sum() if class_weights is None else class_weights[target[valid]].sum()
    return total / denominator.clamp(min=1), valid.sum()


def confusion_matrices(pred, target, num_classes=2, ignore_index=255):
    """Per-image confusion matrices (B, C, C) int64 for pred/target of shape (B, H, W)."""
    batch = target.shape[0]
    target = target.long()
    valid = target != ignore_index
    cells = num_classes * num_classes
    image = torch.arange(batch, device=target.device).view(-1, 1, 1).expand_as(target)
    flat = image[valid] * cells + target[valid] * num_classes + pred.long()[valid]
    return torch.bincount(flat, minlength=batch * cells).view(batch, num_classes, num_classes)


def _ratio(numerator, denominator):
    return float(numerator) / float(denominator) if denominator > 0 else None


def summarize(matrix) -> dict:
    """Metrics from a 2x2 confusion matrix (rows = truth). Undefined ratios are None, never 0 or NaN."""
    m = [[int(v) for v in row] for row in matrix.tolist()]
    true_free, true_blocked = sum(m[FREE]), sum(m[BLOCKED])
    pred_free, pred_blocked = m[FREE][FREE] + m[BLOCKED][FREE], m[FREE][BLOCKED] + m[BLOCKED][BLOCKED]
    iou_free = _ratio(m[FREE][FREE], true_free + pred_free - m[FREE][FREE])
    iou_blocked = _ratio(m[BLOCKED][BLOCKED], true_blocked + pred_blocked - m[BLOCKED][BLOCKED])
    defined = [v for v in (iou_free, iou_blocked) if v is not None]
    return {
        "valid_pixels": true_free + true_blocked,
        "confusion_matrix": m,
        "mIoU": sum(defined) / len(defined) if defined else None,
        "iou_free": iou_free,
        "iou_blocked": iou_blocked,
        "pixel_accuracy": _ratio(m[FREE][FREE] + m[BLOCKED][BLOCKED], true_free + true_blocked),
        "blocked_precision": _ratio(m[BLOCKED][BLOCKED], pred_blocked),
        "blocked_recall": _ratio(m[BLOCKED][BLOCKED], true_blocked),
        # Safety view: a blocked pixel called FREE is the dangerous error.
        "blocked_as_free_rate": _ratio(m[BLOCKED][FREE], true_blocked),
        "predicted_free_that_is_blocked": _ratio(m[BLOCKED][FREE], pred_free),
        "free_as_blocked_rate": _ratio(m[FREE][BLOCKED], true_free),
    }
