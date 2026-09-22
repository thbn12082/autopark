"""Export a checkpoint to ONNX, verify it against PyTorch on real images, and measure single-image latency.

    python -m autopark.perception.export_onnx --checkpoint runs/<run>/best.pt --out runs/<run>/export

The ONNX graph takes a normalised float32 NCHW tensor (1, 3, H, W) and returns the two-class logits at the
same size; letterboxing and normalisation stay in Python (predict.py). Latency numbers are for THIS machine
only; the laptop that will drive the car (RTX 3050 Ti 4 GB) must be measured with the same command.
"""
import argparse
import json
from pathlib import Path
import platform
import statistics
import sys
import time

import numpy as np
import torch
from torch import nn

from .augment import normalize, to_float
from .checkpoint import atomic_write_json, load_checkpoint
from .data import letterbox, read_image
from .dataset import PreparedCache, SplitData, file_sha256
from .model import build_model
from .train import PROJECT, environment_info, utc_now


class LogitsOnly(nn.Module):
    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(self, x):
        return self.model(x)["out"]


def sample_inputs(cfg: dict, count: int) -> tuple[np.ndarray, str]:
    """Normalised NCHW float32 batches from real validation images (never test); synthetic noise when the
    prepared cache is absent (e.g. on the vehicle laptop), which is enough for parity and latency."""
    manifest = PROJECT / cfg["prepared_manifest"]
    if manifest.exists():
        cache = PreparedCache.open(manifest, cfg["require_handoff_split_verified"])
        data = SplitData(cache, "val", limit=count)
        images_u8, _ = data.batch(np.arange(len(data)), torch.device("cpu"))
        return normalize(to_float(images_u8)).numpy().astype(np.float32), "validation split"
    rng = np.random.default_rng(0)
    images_u8 = torch.from_numpy(rng.integers(0, 256, (count, cfg["height"], cfg["width"], 3), dtype=np.uint8))
    return normalize(to_float(images_u8)).numpy().astype(np.float32), "synthetic noise (prepared cache not present)"


def time_calls(fn, warmup: int, runs: int) -> dict:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(runs):
        tick = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - tick) * 1000.0)
    samples.sort()
    return {"runs": runs, "warmup": warmup, "p50_ms": statistics.median(samples),
            "p95_ms": samples[int(0.95 * (runs - 1))], "min_ms": samples[0], "max_ms": samples[-1]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument("--verify-images", type=int, default=16)
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--skip-export", action="store_true", help="only benchmark an existing model.onnx")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    state = load_checkpoint(args.checkpoint)
    cfg = state["config"]
    height, width = cfg["height"], cfg["width"]
    model = build_model(cfg["num_classes"], pretrained=False)
    model.load_state_dict(state["model"])
    wrapped = LogitsOnly(model).eval()
    onnx_path = args.out / "model.onnx"
    report = {"created_utc": utc_now(), "checkpoint": str(args.checkpoint), "checkpoint_sha256": file_sha256(args.checkpoint),
              "checkpoint_epoch": state["epoch"], "input": {"name": "image", "shape": [1, 3, height, width],
                                                            "dtype": "float32", "preprocessing": "letterbox + ImageNet normalisation (predict.py)"},
              "output": {"name": "logits", "shape": [1, cfg["num_classes"], height, width]},
              "machine": {"platform": platform.platform(), "processor": platform.processor(),
                          "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},
              "note": "latency measured on this machine only; repeat on the vehicle laptop"}

    if not args.skip_export:
        example = torch.zeros(1, 3, height, width)
        torch.onnx.export(wrapped, (example,), str(onnx_path), input_names=["image"], output_names=["logits"],
                          opset_version=args.opset, dynamo=False)
        import onnx
        onnx_model = onnx.load(str(onnx_path))
        onnx.checker.check_model(onnx_model)
        report["onnx"] = {"file": onnx_path.name, "bytes": onnx_path.stat().st_size, "sha256": file_sha256(onnx_path),
                          "opset": args.opset, "ir_version": onnx_model.ir_version, "exporter": "torchscript (dynamo=False)"}

    if "onnx" not in report:
        report["onnx"] = {"file": onnx_path.name, "bytes": onnx_path.stat().st_size, "sha256": file_sha256(onnx_path),
                          "note": "existing file, not re-exported in this run"}
    inputs, input_source = sample_inputs(cfg, args.verify_images)
    with torch.no_grad():
        reference = np.concatenate([wrapped(torch.from_numpy(inputs[i:i + 1])).numpy() for i in range(len(inputs))])

    import onnxruntime as ort
    providers = ort.get_available_providers()
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    outputs = np.concatenate([session.run(None, {"image": inputs[i:i + 1]})[0] for i in range(len(inputs))])
    difference = np.abs(outputs - reference)
    label_agreement = float((outputs.argmax(1) == reference.argmax(1)).mean())
    report["verification"] = {"images": int(len(inputs)), "source": f"{input_source}, fp32 torch CPU vs onnxruntime CPU",
                              "max_abs_logit_difference": float(difference.max()),
                              "mean_abs_logit_difference": float(difference.mean()),
                              "argmax_agreement": label_agreement, "onnxruntime": ort.__version__,
                              "available_providers": providers}
    if label_agreement < 0.999:
        raise SystemExit(f"ONNX output disagrees with PyTorch on {1 - label_agreement:.2%} of pixels")

    single = inputs[:1]
    latency = {"onnxruntime_cpu_fp32": time_calls(lambda: session.run(None, {"image": single}), 10, args.runs)}
    cpu_model = wrapped
    x_cpu = torch.from_numpy(single)
    with torch.no_grad():
        latency["torch_cpu_fp32"] = time_calls(lambda: cpu_model(x_cpu), 5, max(10, args.runs // 5))
    if torch.cuda.is_available():
        gpu_model = LogitsOnly(model).cuda().eval()
        x_gpu = x_cpu.cuda()

        def run_fp32():
            with torch.no_grad():
                gpu_model(x_gpu)
            torch.cuda.synchronize()

        def run_fp16():
            with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
                gpu_model(x_gpu)
            torch.cuda.synchronize()
        latency["torch_cuda_fp32"] = time_calls(run_fp32, 20, args.runs)
        latency["torch_cuda_fp16_autocast"] = time_calls(run_fp16, 20, args.runs)
        sample = PROJECT / "datasets/training/woodscape/rgb_images/00007_FV.png"
        image = read_image(sample) if sample.exists() else np.random.default_rng(0).integers(0, 256, (966, 1280, 3), dtype=np.uint8)

        def end_to_end():
            prepared, _, _ = letterbox(image, np.zeros(image.shape[:2], np.uint8), height, width)
            rgb = torch.from_numpy(prepared[..., ::-1].copy()).unsqueeze(0).cuda()
            with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
                logits = gpu_model(normalize(to_float(rgb)))
            logits.float().softmax(1)[0, 1].cpu().numpy()
        latency["torch_cuda_fp16_end_to_end_1280x966_input"] = time_calls(end_to_end, 10, max(20, args.runs // 2))
    report["latency_single_image_ms"] = latency
    report["environment"] = environment_info()
    atomic_write_json(args.out / "export_report.json", report)
    print(json.dumps({"verification": report["verification"], "latency": {k: round(v["p50_ms"], 2) for k, v in latency.items()}},
                     indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
