"""L-RASPP / MobileNetV3-Large for two-class FREE / BLOCKED segmentation."""
from torch import nn

# L-RASPP sums two per-pixel classifiers (low-level and high-level branch); both must change class count.
CLASSIFIER_HEADS = ("low_classifier", "high_classifier")


def build_model(num_classes: int = 2, pretrained: bool = True) -> nn.Module:
    from torchvision.models.segmentation import LRASPP_MobileNet_V3_Large_Weights, lraspp_mobilenet_v3_large

    weights = LRASPP_MobileNet_V3_Large_Weights.COCO_WITH_VOC_LABELS_V1 if pretrained else None
    # weights_backbone defaults to an ImageNet download; pass None so an untrained build stays offline.
    model = lraspp_mobilenet_v3_large(weights=weights, weights_backbone=None)
    for name in CLASSIFIER_HEADS:
        old = getattr(model.classifier, name)
        if not isinstance(old, nn.Conv2d) or old.kernel_size != (1, 1):
            raise TypeError(f"Unexpected L-RASPP head layout: {name} is {old!r}")
        setattr(model.classifier, name, nn.Conv2d(old.in_channels, num_classes, kernel_size=1))
    stale = [name for name, module in model.classifier.named_modules()
             if name.endswith("classifier") and module.out_channels != num_classes]
    if stale:
        raise RuntimeError(f"Classifier heads still have the old class count: {stale}")
    return model


def parameter_groups(model: nn.Module, backbone_lr: float, head_lr: float) -> list[dict]:
    groups = [{"name": "backbone", "params": list(model.backbone.parameters()), "lr": backbone_lr},
              {"name": "head", "params": list(model.classifier.parameters()), "lr": head_lr}]
    grouped = {id(p) for group in groups for p in group["params"]}
    if grouped != {id(p) for p in model.parameters()}:
        raise RuntimeError("Parameter groups do not cover the model exactly once")
    return groups
