"""Project a FREE/BLOCKED mask onto the ground plane and fill the project's Costmap contract.

    python -m autopark.perception.costmap --checkpoint runs/<run>/best.pt --image <woodscape png> \
        --roi configs/roi/woodscape_v1 --out runs/perception_integration/costmap_<id>

Method (per camera, flat ground z = 0 in the vehicle frame):
1. Every grid cell centre is projected INTO the image with the calibrated fisheye model (forward projection only,
   no polynomial inversion) and takes the label of that pixel: FREE -> 0, BLOCKED -> 1, IGNORE / outside the
   image / outside the ROI -> UNKNOWN (-1).
2. Occlusion sweep: along each azimuth from the camera, everything behind the first OCCUPIED cell becomes
   UNKNOWN. A tall obstacle therefore marks only its ground contact as OCCUPIED instead of smearing along the
   ray, and the hidden ground behind it is not reported as FREE.
3. Cells beyond --max-range are UNKNOWN (one pixel covers many cells there).

Grid layout: cells[row][col] with row = y index from origin.y (left is +y) and col = x index from origin.x
(forward is +x); origin = Pose(x_min, y_min, 0) in the vehicle frame. UNKNOWN is blocked for planning, so any
uncertainty here fails safe. Calibration error, ground slope and the model's own errors all end up in this grid.
"""
import argparse
from dataclasses import dataclass
import math
from pathlib import Path
import sys

import cv2
import numpy as np

from autopark.domain.sensors import Costmap, SourceStamp
from autopark.domain.types import Pose
from autopark.image_io import imwrite

from .calibration import CameraCalibration, load_woodscape_calibration
from .paths import PROJECT, atomic_write_json, utc_now

UNKNOWN, FREE, OCCUPIED = -1, 0, 1
COLORS = {UNKNOWN: (110, 110, 110), FREE: (0, 170, 0), OCCUPIED: (40, 40, 220)}


@dataclass(frozen=True)
class GridSpec:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    resolution: float

    def __post_init__(self):
        if self.resolution <= 0 or self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("Grid must have positive size and resolution")
        for span in ((self.x_max - self.x_min) / self.resolution, (self.y_max - self.y_min) / self.resolution):
            if abs(span - round(span)) > 1e-6:
                raise ValueError("Grid extents must be integer multiples of the resolution")

    @property
    def shape(self) -> tuple[int, int]:
        rows = int(round((self.y_max - self.y_min) / self.resolution))
        cols = int(round((self.x_max - self.x_min) / self.resolution))
        return rows, cols

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        rows, cols = self.shape
        xs = self.x_min + (np.arange(cols) + 0.5) * self.resolution
        ys = self.y_min + (np.arange(rows) + 0.5) * self.resolution
        return np.meshgrid(xs, ys)            # each (rows, cols)

    def index(self, x: float, y: float) -> tuple[int, int]:
        """Cell containing (x, y); points on the far edges belong to the last cell."""
        rows, cols = self.shape
        if not (self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max):
            raise ValueError(f"({x}, {y}) is outside the grid")
        row = min(rows - 1, int(math.floor((y - self.y_min) / self.resolution + 1e-9)))
        col = min(cols - 1, int(math.floor((x - self.x_min) / self.resolution + 1e-9)))
        return row, col


def _check_max_range(max_range) -> None:
    if max_range is None:
        return
    try:
        value = float(max_range)
    except (TypeError, ValueError):
        raise ValueError(f"max_range phải là None hoặc số > 0 (nhận {max_range!r})") from None
    if math.isnan(value) or value <= 0:
        raise ValueError(f"max_range phải là None hoặc số > 0 (nhận {max_range!r})")


def _range_arg(text: str) -> float:
    """--max-range: số hữu hạn > 0 (NaN, ±inf, ≤ 0 bị argparse từ chối, mã 2)."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"không phải số: {text!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"phải là số hữu hạn > 0 (nhận {text!r})")
    return value


def project_labels(labels: np.ndarray, calibration: CameraCalibration, grid: GridSpec, *,
                   max_range: float | None = None, azimuth_bin_deg: float = 0.5) -> np.ndarray:
    """labels (H, W) uint8 in {0, 1, 255} at the calibration's native size -> grid states (rows, cols) int8.

    `max_range`: None = không giới hạn; ngoài ra phải là số > 0. NaN bị từ chối (từ 25/09/2026): trước đó
    `distance > nan` luôn sai nên giới hạn tầm âm thầm biến mất (cùng lỗi đã sửa ở `bev.check_max_range`)."""
    _check_max_range(max_range)
    expected = (calibration.intrinsics.height, calibration.intrinsics.width)
    if labels.shape != expected:
        raise ValueError(f"labels are {labels.shape}, calibration expects {expected}: apply the ROI and project at "
                         f"native resolution, not at the model's letterbox size")
    gx, gy = grid.centers()
    u, v, valid = calibration.ground_to_pixel(np.column_stack([gx.ravel(), gy.ravel()]))
    states = np.full(gx.size, UNKNOWN, np.int8)
    ui = np.rint(u[valid]).astype(np.int64)         # valid already guarantees 0 <= u <= width - 1
    vi = np.rint(v[valid]).astype(np.int64)
    sampled = labels[vi, ui]
    states[np.flatnonzero(valid)[sampled == 0]] = FREE
    states[np.flatnonzero(valid)[sampled == 1]] = OCCUPIED

    cam_x, cam_y = calibration.extrinsics.translation[:2]
    dx, dy = gx.ravel() - cam_x, gy.ravel() - cam_y
    distance = np.hypot(dx, dy)
    if max_range is not None:
        states[distance > max_range] = UNKNOWN

    # Occlusion sweep: each OCCUPIED cell shadows every azimuth its square footprint subtends as seen from the
    # camera (exact corner angles, not a perpendicular-diagonal approximation), and any cell farther away
    # inside that shadow becomes UNKNOWN. A cell whose footprint contains the camera position shadows everything.
    n_bins = int(round(360.0 / azimuth_bin_deg))
    bin_size = 2 * np.pi / n_bins
    azimuth = np.arctan2(dy, dx)
    cell_bin = np.floor((azimuth + np.pi) / bin_size).astype(np.int64) % n_bins
    occupied = np.flatnonzero(states == OCCUPIED)
    if len(occupied):
        half = grid.resolution / 2
        corner_dx = dx[occupied, None] + np.array([[-half, half, half, -half]])
        corner_dy = dy[occupied, None] + np.array([[-half, -half, half, half]])
        offsets = np.arctan2(corner_dy, corner_dx) - azimuth[occupied, None]
        offsets = (offsets + np.pi) % (2 * np.pi) - np.pi          # wrap each corner's angle relative to the centre
        half_extent = np.abs(offsets).max(axis=1)
        contains_camera = (np.abs(dx[occupied]) <= half) & (np.abs(dy[occupied]) <= half)
        half_extent[contains_camera] = np.pi
        lo = np.floor((azimuth[occupied] - half_extent + np.pi) / bin_size).astype(np.int64)
        hi = np.floor((azimuth[occupied] + half_extent + np.pi) / bin_size).astype(np.int64)
        counts = np.minimum(hi - lo + 1, n_bins)
        expanded_bins = (np.repeat(lo, counts) + _ranges(counts)) % n_bins
        nearest = np.full(n_bins, np.inf)
        np.minimum.at(nearest, expanded_bins, np.repeat(distance[occupied], counts))
        hidden = distance > nearest[cell_bin] + 1e-9
        states[hidden] = UNKNOWN
    return states.reshape(gx.shape)


def _ranges(counts: np.ndarray) -> np.ndarray:
    """[0..c0-1, 0..c1-1, ...] for the run lengths in `counts` (vectorised)."""
    total = int(counts.sum())
    starts = np.cumsum(counts) - counts
    return np.arange(total) - np.repeat(starts, counts)


def to_costmap(states: np.ndarray, grid: GridSpec, stamp: SourceStamp) -> Costmap:
    return Costmap(stamp, grid.resolution, Pose(grid.x_min, grid.y_min, 0.0),
                   tuple(tuple(int(v) for v in row) for row in states))


def costmap_to_dict(costmap: Costmap) -> dict:
    return {"stamp": {"source_id": costmap.stamp.source_id, "t": costmap.stamp.t, "valid": costmap.stamp.valid,
                      "frame_id": costmap.stamp.frame_id},
            "resolution_m": costmap.resolution_m, "origin": costmap.origin.to_dict(),
            "layout": "cells[row][col]: row = y index from origin (left +), col = x index from origin (forward +)",
            "values": {"-1": "UNKNOWN (blocked for planning)", "0": "FREE", "1": "OCCUPIED"},
            "cells": [list(row) for row in costmap.cells]}


def render(states: np.ndarray, grid: GridSpec, calibration: CameraCalibration | None = None,
           image_bgr: np.ndarray | None = None, scale: int = 4) -> np.ndarray:
    """Top-down picture: vehicle +x up, +y left. Optionally paints the camera image onto FREE/OCCUPIED cells."""
    rows, cols = states.shape
    canvas = np.zeros((cols, rows, 3), np.uint8)      # picture row = x (flipped), picture col = y (flipped)
    for value, color in COLORS.items():
        canvas[(states.T[::-1, ::-1] == value)] = color
    if image_bgr is not None and calibration is not None:
        gx, gy = grid.centers()
        u, v, ok = calibration.ground_to_pixel(np.column_stack([gx.ravel(), gy.ravel()]))
        ui = np.clip(np.rint(u), 0, image_bgr.shape[1] - 1).astype(int)
        vi = np.clip(np.rint(v), 0, image_bgr.shape[0] - 1).astype(int)
        texture = np.zeros((rows * cols, 3), np.uint8)
        texture[ok] = image_bgr[vi[ok], ui[ok]]
        texture = texture.reshape(rows, cols, 3).transpose(1, 0, 2)[::-1, ::-1]
        painted = states.T[::-1, ::-1] != UNKNOWN
        canvas[painted] = (0.55 * texture[painted] + 0.45 * canvas[painted]).astype(np.uint8)
    canvas = cv2.resize(canvas, (rows * scale, cols * scale), interpolation=cv2.INTER_NEAREST)

    def px(x, y):
        return int((grid.y_max - y) / grid.resolution * scale), int((grid.x_max - x) / grid.resolution * scale)

    for x in range(int(np.ceil(grid.x_min)), int(grid.x_max) + 1):
        cv2.line(canvas, px(x, grid.y_min), px(x, grid.y_max), (70, 70, 70), 1)
    for y in range(int(np.ceil(grid.y_min)), int(grid.y_max) + 1):
        cv2.line(canvas, px(grid.x_min, y), px(grid.x_max, y), (70, 70, 70), 1)
    cv2.circle(canvas, px(0, 0), 6, (255, 255, 0), -1)
    if calibration is not None:
        t = calibration.extrinsics.translation
        cv2.circle(canvas, px(t[0], t[1]), 6, (0, 255, 255), -1)
    return canvas


def main(argv=None) -> int:
    import torch

    from .data import read_image
    from .model import build_model
    from .predict import predict_image
    from .roi import apply_roi, load_roi

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True, help="a WoodScape rgb_images/<id>.png")
    parser.add_argument("--calibration-archive", type=Path, default=PROJECT / "datasets/woodscape_metadata/calibration.zip")
    parser.add_argument("--roi", type=Path, default=PROJECT / "configs/roi/woodscape_v1",
                        help="directory holding roi_<camera>.png (native size)")
    parser.add_argument("--no-roi", action="store_true",
                        help="project without a ROI: the ego body gets model labels, so the costmap is marked NOT usable")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--grid", type=float, nargs=5, metavar=("XMIN", "XMAX", "YMIN", "YMAX", "RES"),
                        default=(-10.0, 15.0, -10.0, 10.0, 0.1))
    parser.add_argument("--max-range", type=_range_arg, default=12.0)
    args = parser.parse_args(argv)
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable.")
    device = torch.device("cuda")
    image_id = args.image.stem
    camera = image_id.rsplit("_", 1)[-1]
    calibration = load_woodscape_calibration(args.calibration_archive, image_id)
    grid = GridSpec(*args.grid)

    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    cfg = state["config"]
    model = build_model(cfg["num_classes"], pretrained=False)
    model.load_state_dict(state["model"])
    model.to(device).eval()
    image = read_image(args.image)
    labels, _ = predict_image(model, image, cfg["height"], cfg["width"], device, cfg["amp"], threshold=args.threshold)
    if args.no_roi:
        roi_note = "NO ROI: ego-body pixels carry meaningless labels; costmap stamped invalid"
    else:
        roi_path = args.roi / f"roi_{camera}.png"
        if not roi_path.exists():
            raise SystemExit(f"ROI {roi_path} not found; build it with `python -m autopark.perception.roi build` "
                             f"or pass --no-roi to produce an explicitly unusable costmap")
        labels = apply_roi(labels, load_roi(roi_path, labels.shape))
        roi_note = str(roi_path)

    states = project_labels(labels, calibration, grid, max_range=args.max_range)
    stamp = SourceStamp(f"camera_{camera}_segmentation", 0.0, not args.no_roi, "vehicle")
    costmap = to_costmap(states, grid, stamp)
    args.out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.out / "costmap.json", {
        "created_utc": utc_now(), "image": str(args.image), "checkpoint": str(args.checkpoint), "roi": roi_note,
        "usable_for_planning": not args.no_roi, "threshold": args.threshold,
        "calibration": {"name": calibration.name, "translation": calibration.extrinsics.translation,
                        "quaternion_xyzw": calibration.extrinsics.quaternion_xyzw},
        "grid": {"x_min": grid.x_min, "x_max": grid.x_max, "y_min": grid.y_min, "y_max": grid.y_max,
                 "resolution": grid.resolution, "max_range": args.max_range},
        "counts": {"free": int((states == FREE).sum()), "occupied": int((states == OCCUPIED).sum()),
                   "unknown": int((states == UNKNOWN).sum())},
        "assumptions": "flat ground z=0 in the vehicle frame; per-image WoodScape calibration; occlusion behind the "
                       "first OCCUPIED cell per azimuth is UNKNOWN; this is a single-camera, single-frame costmap "
                       "with no fusion or temporal filtering",
        "costmap": costmap_to_dict(costmap)})
    colors = np.zeros_like(image)
    colors[labels == 0], colors[labels == 1], colors[labels == 255] = (0, 170, 0), (40, 40, 220), (110, 110, 110)
    imwrite(args.out / "labels_overlay.jpg", cv2.addWeighted(image, 0.5, colors, 0.5, 0))
    imwrite(args.out / "costmap.png", render(states, grid, calibration))
    imwrite(args.out / "costmap_textured.png", render(states, grid, calibration, image))
    print(f"{image_id}: free {int((states == FREE).sum())} occupied {int((states == OCCUPIED).sum())} "
          f"unknown {int((states == UNKNOWN).sum())} cells -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
