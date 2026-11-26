"""Batch preprocessing on the training device: synchronized geometric + photometric augmentation, normalization.

Geometry is applied to image and mask with the same sampling grid; the mask uses nearest-neighbour and every
pixel that falls outside the source image becomes IGNORE (255), never FREE. Randomness comes from a generator
seeded by (seed, epoch, step), so a resumed run reproduces the same augmentations without saved RNG state.
"""
from dataclasses import dataclass
import math

import torch
import torch.nn.functional as F

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
IGNORE = 255


@dataclass(frozen=True)
class AugmentConfig:
    enabled: bool = True
    hflip: float = 0.5
    scale_min: float = 0.75
    scale_max: float = 1.35
    brightness: float = 0.25
    contrast: float = 0.25
    saturation: float = 0.25

    def __post_init__(self):
        if not (0 < self.scale_min <= self.scale_max) or not 0 <= self.hflip <= 1:
            raise ValueError("Invalid augmentation ranges")
        if min(self.brightness, self.contrast, self.saturation) < 0 or max(self.brightness, self.contrast,
                                                                          self.saturation) >= 1:
            raise ValueError("Photometric jitter must be in [0, 1)")


def step_generator(device, seed: int, epoch: int, step: int) -> torch.Generator:
    generator = torch.Generator(device=device)
    generator.manual_seed(((seed * 1_000_003 + epoch) * 1_000_003 + step) & (2**63 - 1))
    return generator


def to_float(images_u8: torch.Tensor) -> torch.Tensor:
    """(B, H, W, 3) uint8 RGB -> (B, 3, H, W) float32 in [0, 1]."""
    return images_u8.permute(0, 3, 1, 2).float().div_(255.0)


def normalize(images: torch.Tensor) -> torch.Tensor:
    mean = images.new_tensor(IMAGENET_MEAN).view(1, 3, 1, 1)
    std = images.new_tensor(IMAGENET_STD).view(1, 3, 1, 1)
    return (images - mean) / std


def _gray(images: torch.Tensor) -> torch.Tensor:
    return (0.299 * images[:, 0:1] + 0.587 * images[:, 1:2] + 0.114 * images[:, 2:3])


def augment(images: torch.Tensor, masks: torch.Tensor, cfg: AugmentConfig, generator: torch.Generator):
    """images float (B, 3, H, W) in [0, 1]; masks uint8 (B, H, W). Same shapes and dtypes out."""
    if not cfg.enabled:
        return images, masks
    batch, _, height, width = images.shape
    u = torch.rand((batch, 7), generator=generator, device=images.device)

    log_min, log_max = math.log(cfg.scale_min), math.log(cfg.scale_max)
    scale = torch.exp(log_min + (log_max - log_min) * u[:, 0])          # >1 zooms in, <1 zooms out
    flip = torch.where(u[:, 1] < cfg.hflip, -1.0, 1.0)
    # Zoomed in: keep the crop window inside the image. Zoomed out: keep the whole image inside the frame.
    room = (1.0 - 1.0 / scale).abs()
    theta = torch.zeros((batch, 2, 3), device=images.device)
    theta[:, 0, 0] = flip / scale
    theta[:, 1, 1] = 1.0 / scale
    theta[:, 0, 2] = (u[:, 2] * 2 - 1) * room
    theta[:, 1, 2] = (u[:, 3] * 2 - 1) * room
    grid = F.affine_grid(theta, (batch, 3, height, width), align_corners=False)
    images = F.grid_sample(images, grid, mode="bilinear", padding_mode="zeros", align_corners=False)
    # Shift labels by one so that zero padding marks "outside the source image" unambiguously.
    shifted = masks.float().unsqueeze(1) + 1.0
    sampled = F.grid_sample(shifted, grid, mode="nearest", padding_mode="zeros", align_corners=False)
    sampled = sampled.squeeze(1).round().long()
    masks = torch.where(sampled == 0, torch.full_like(sampled, IGNORE), sampled - 1).to(torch.uint8)

    contrast = (1 + cfg.contrast * (u[:, 4] * 2 - 1)).view(-1, 1, 1, 1)
    brightness = (1 + cfg.brightness * (u[:, 5] * 2 - 1)).view(-1, 1, 1, 1)
    saturation = (1 + cfg.saturation * (u[:, 6] * 2 - 1)).view(-1, 1, 1, 1)
    mean = _gray(images).mean(dim=(1, 2, 3), keepdim=True)
    images = ((images - mean) * contrast + mean) * brightness
    gray = _gray(images)
    images = ((images - gray) * saturation + gray).clamp_(0.0, 1.0)
    return images, masks
