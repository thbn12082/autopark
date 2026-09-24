"""Suy luận trực tiếp theo lô cho nhiều camera: cùng tiền xử lý với `predict.py`, đo thời gian từng khâu.

Tiền xử lý giữ nguyên `predict.predict_image` (letterbox của cache, INTER_AREA, chuẩn hóa ImageNet, softmax, cắt phần
letterbox rồi phóng về kích thước ra) để kết quả trên ảnh camera trùng với kết quả của lệnh `predict` trên cùng ảnh;
test `test_perception_live.py` kiểm điều đó. Khác biệt duy nhất: nhiều ảnh chạy chung một lô trên GPU, và bản đồ xác
suất được trả về ở kích thước `out_size` do người gọi chọn (hiển thị không cần độ phân giải gốc).

Mô hình chỉ biết FREE / BLOCKED trên ảnh đã học (WoodScape fisheye, đường phố). Trên ảnh sa bàn nó chưa từng được
chấm; lớp tô màu là để NHÌN, không phải bằng chứng xe đi qua được.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import cv2
import numpy as np
import torch

from .augment import normalize, to_float
from .checkpoint import load_checkpoint
from .data import letterbox
from .engine import autocast
from .model import build_model
from autopark.video.multicam import fit_width  # noqa: F401 - dùng lại, không cần torch


@dataclass
class InferTiming:
    batch: int
    pre_ms: float          # letterbox + chuyển sang tensor trên GPU
    model_ms: float        # mạng + softmax (đã đồng bộ CUDA)
    post_ms: float         # về CPU, cắt letterbox, phóng về out_size
    total_ms: float


class LiveSegmenter:
    def __init__(self, checkpoint: str | Path, device: str | None = None, amp: bool | None = None):
        self.checkpoint = Path(checkpoint)
        state = load_checkpoint(self.checkpoint)
        cfg = state["config"]
        self.height, self.width = int(cfg["height"]), int(cfg["width"])
        self.epoch = state.get("epoch")
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        self.model = build_model(cfg["num_classes"], pretrained=False)
        self.model.load_state_dict(state["model"])
        self.model.to(self.device).eval()
        self.amp = (bool(cfg.get("amp", False)) if amp is None else amp) and self.device.type == "cuda"
        self.name = self.checkpoint.parent.name

    def _sync(self) -> None:
        if self.device.type == "cuda":
            torch.cuda.synchronize(self.device)

    @torch.no_grad()
    def infer(self, images_bgr: list[np.ndarray], out_size=None) -> tuple[list[np.ndarray], InferTiming]:
        """Trả xác suất BLOCKED (float32, [0, 1]) cho từng ảnh. `out_size`: None = kích thước gốc, (rộng, cao) chung,
        hoặc một danh sách (rộng, cao) theo từng ảnh (để giữ tỉ lệ khi các camera khác mode)."""
        if not images_bgr:
            return [], InferTiming(0, 0.0, 0.0, 0.0, 0.0)
        t0 = time.perf_counter()
        prepared, boxes = [], []
        for image in images_bgr:
            h, w = image.shape[:2]
            out, _, box = letterbox(image, np.zeros((h, w), np.uint8), self.height, self.width)
            prepared.append(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
            boxes.append((box, (w, h)))
        batch = torch.from_numpy(np.stack(prepared)).to(self.device, non_blocking=False)
        self._sync()
        t1 = time.perf_counter()
        with autocast(self.device, self.amp):
            logits = self.model(normalize(to_float(batch)))["out"]
        blocked = logits.float().softmax(1)[:, 1]
        self._sync()
        t2 = time.perf_counter()
        blocked = blocked.cpu().numpy()
        results = []
        for k, (box, (w, h)) in enumerate(boxes):
            crop = blocked[k, box["y"]:box["y"] + box["height"], box["x"]:box["x"] + box["width"]]
            size = (w, h) if out_size is None else (out_size[k] if isinstance(out_size, list) else out_size)
            results.append(cv2.resize(crop, size, interpolation=cv2.INTER_LINEAR))
        t3 = time.perf_counter()
        ms = lambda a, b: 1000.0 * (b - a)
        return results, InferTiming(len(images_bgr), ms(t0, t1), ms(t1, t2), ms(t2, t3), ms(t0, t3))


def list_checkpoints(runs_dir: str | Path = "runs") -> list[Path]:
    """Mọi `runs/*/best.pt`, lượt nền WoodScape (checkpoint tham chiếu, HUAN_LUYEN.md mục 18) đứng đầu."""
    found = sorted(Path(runs_dir).glob("*/best.pt"))
    reference = [p for p in found if p.parent.name == "ai_woodscape_rtx4000_v1"]
    return reference + [p for p in found if p not in reference]
