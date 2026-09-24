"""Kiểm một máy mới bằng một lệnh — dùng cho laptop i7-12700H + RTX 3050 Ti mang đi nộp đồ án (docs/MAY_NOP_DO_AN.md).

    .venv-train\\Scripts\\python.exe -X utf8 -m autopark.rig.may_moi
    .venv-train\\Scripts\\python.exe -X utf8 -m autopark.rig.may_moi --dry-run        (chỉ in kế hoạch, không mở thiết bị)

Các bước, mỗi bước chạy riêng, bước lỗi được ghi lại rồi chạy tiếp bước sau:

1. `env`: cấu hình máy (CPU, RAM, Python, torch, CUDA, GPU, VRAM, driver NVIDIA, OpenCV) → `env.json`.
2. `usb`: sơ đồ camera và hub (`camera_bench list`) → `usb_topology.json`.
3. `lidar`: tìm cổng COM của RPLIDAR C1 (bộ chuyển CP210x, VID 10C4 PID EA60), đọc thông tin/sức khỏe, ghi 15 s quét tĩnh
   có phân tích → `lidar_info.json`, `lidar/`.
4. `ai`: thời gian một lô bốn ảnh 640×480 qua mô hình tham chiếu (cùng lớp `LiveSegmenter` của bàn thử), VRAM dùng →
   `ai_latency.json`.
5. `rig480`: bàn thử bốn camera 640×480 + LiDAR + AI (`rig.bench`, mặc định 120 s) → `m01_480p_lidar_ai.rig.json`.
6. `cam720`: bốn camera 1280×720, chỉ camera, 30 s — xem khung bị cắt trên bộ điều khiển USB của máy này →
   `m02_720p_chi_camera.rig.json`.
7. `tom_tat.md`: tóm tắt, so với máy bàn nếu có tệp tham chiếu (`docs/evidence/may_ban/tham_chieu_*.json`).

Không sửa gì trên máy ngoài thư mục kết quả (mặc định `runs/may_moi_<ngày giờ>`). Camera chọn theo cổng hub nếu cắm qua hub;
cắm thẳng vào máy thì không có số cổng hub, lệnh tự mở theo index DirectShow.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime
import io
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback

import numpy as np

CP210X_VID, CP210X_PID = 0x10C4, 0xEA60
STEPS = ("env", "usb", "lidar", "ai", "rig480", "cam720")
REFERENCE_GLOB = "docs/evidence/may_ban/tham_chieu_*.json"


# ----------------------------------------------------------------------------------------------- từng bước

def find_lidar_port(comports=None) -> str | None:
    """Cổng COM của bộ chuyển CP210x (RPLIDAR C1). Số COM khác nhau giữa các máy (máy bàn: COM4)."""
    if comports is None:
        from serial.tools import list_ports
        comports = list_ports.comports()
    for port in comports:
        if getattr(port, "vid", None) == CP210X_VID and getattr(port, "pid", None) == CP210X_PID:
            return port.device
    return None


def env_report() -> dict:
    info = {"created_local": datetime.now().isoformat(timespec="seconds"), "platform": platform.platform(),
            "machine": platform.machine(), "processor": platform.processor(), "cpu_count": os.cpu_count(),
            "python": sys.version.split()[0]}
    try:
        import psutil
        info["ram_gb"] = round(psutil.virtual_memory().total / 2 ** 30, 1)
    except Exception as exc:  # noqa: BLE001
        info["ram_gb_error"] = repr(exc)
    try:
        import cv2
        info["opencv"] = cv2.__version__
    except Exception as exc:  # noqa: BLE001
        info["opencv_error"] = repr(exc)
    try:
        import torch
        info["torch"] = torch.__version__
        info["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            prop = torch.cuda.get_device_properties(0)
            info["gpu"] = prop.name
            info["gpu_vram_gb"] = round(prop.total_memory / 2 ** 30, 1)
            info["cuda_runtime"] = torch.version.cuda
    except Exception as exc:  # noqa: BLE001
        info["torch_error"] = repr(exc)
    try:
        import pynvml
        pynvml.nvmlInit()
        driver = pynvml.nvmlSystemGetDriverVersion()
        info["nvidia_driver"] = driver.decode() if isinstance(driver, bytes) else driver
        pynvml.nvmlShutdown()
    except Exception as exc:  # noqa: BLE001
        info["nvidia_driver_error"] = repr(exc)
    return info


def camera_selection(resolve=None, dshow=None) -> dict:
    """Tham số chọn camera cho rig.bench: theo cổng hub nếu có, không thì theo index DirectShow của các 'HD Camera'."""
    if resolve is None or dshow is None:
        from autopark.video import camera_bench as cb
        from autopark.video.multicam import resolve_ports
        resolve = resolve or resolve_ports
        dshow = dshow or cb.dshow_device_paths
    try:
        specs = resolve(None)
    except Exception as exc:  # noqa: BLE001
        specs, error = [], repr(exc)
    else:
        error = None
    if specs:
        ports = [s.port for s in specs]
        return {"mode": "ports", "argv": ["--ports", *map(str, ports)], "ports": ports, "note": "qua hub, chọn theo cổng"}
    rows = dshow()
    # camera của dự án: Sunplus 1BCF:0B09 ("HD Camera"); webcam gắn sẵn của laptop có thể cũng tên "... HD Camera" nên lọc
    # theo VID/PID trong DevicePath trước, tên đúng "HD Camera" sau, còn không thì lấy hết
    ours = [i for i, row in enumerate(rows) if "vid_1bcf&pid_0b09" in str(row.get("device_path", "")).lower()]
    named = [i for i, row in enumerate(rows) if str(row.get("name", "")).strip() == "HD Camera"]
    indices = ours or named or list(range(len(rows)))
    if not indices:
        raise RuntimeError(f"không thấy camera nào (DirectShow rỗng; tra cổng hub: {error})")
    return {"mode": "index", "argv": ["--index", *map(str, indices)], "indices": indices,
            "note": "không thấy camera nào qua hub (cắm thẳng vào máy?): mở theo index DirectShow"
                    + (f"; lỗi tra cổng: {error}" if error else "")}


def ai_latency(make_segmenter, batches: int = 60, warmup: int = 5, batch: int = 4, size=(640, 480), seed: int = 0) -> dict:
    """Thời gian một lô `batch` ảnh qua mô hình (tiền xử lý + mạng + hậu xử lý, có đồng bộ CUDA như bàn thử)."""
    rng = np.random.default_rng(seed)
    images = [rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8) for _ in range(batch)]
    segmenter = make_segmenter()
    peak = None
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:  # noqa: BLE001
        torch = None
    for _ in range(warmup):
        segmenter.infer(images, out_size=(size[0], size[1]))
    totals, models = [], []
    for _ in range(batches):
        _, timing = segmenter.infer(images, out_size=(size[0], size[1]))
        totals.append(timing.total_ms)
        models.append(timing.model_ms)
    if torch is not None and torch.cuda.is_available():
        peak = round(torch.cuda.max_memory_allocated() / 2 ** 20, 1)
    pct = lambda v, q: round(float(np.percentile(v, q)), 2)  # noqa: E731
    return {"batch": batch, "size": list(size), "batches": batches, "device": str(getattr(segmenter, "device", None)),
            "amp": getattr(segmenter, "amp", None), "model": getattr(segmenter, "name", None),
            "total_ms": {"median": pct(totals, 50), "p95": pct(totals, 95), "max": round(max(totals), 2)},
            "model_ms": {"median": pct(models, 50), "p95": pct(models, 95)},
            "sets_per_s_upper_bound": round(1000.0 / float(np.median(totals)), 1), "peak_vram_mb": peak}


# ----------------------------------------------------------------------------------------------- khung chạy

def run_step(name: str, fn, results: dict) -> None:
    t0 = time.perf_counter()
    print(f"\n==== {name} ====", flush=True)
    try:
        value = fn()
        results[name] = {"ok": True, "seconds": round(time.perf_counter() - t0, 1), "value": value}
    except Exception as exc:  # noqa: BLE001
        results[name] = {"ok": False, "seconds": round(time.perf_counter() - t0, 1), "error": repr(exc),
                         "traceback": traceback.format_exc()[-3000:]}
        print(f"LỖI ở bước {name}: {exc!r} — chạy tiếp bước sau", flush=True)


def capture_stdout(fn):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn()
    return code, buf.getvalue()


def load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def find_reference(root: Path) -> dict | None:
    files = sorted(root.glob(REFERENCE_GLOB))
    return load_json(files[-1]) if files else None


def rig_digest(rig: dict | None) -> dict | None:
    if not rig:
        return None
    cams = sorted(rig.get("cameras", []), key=lambda c: c["port"])
    ai = rig.get("ai") or {}
    lidar = rig.get("lidar") or {}
    res = rig.get("resources") or {}
    pick = lambda k, f="mean": (res.get(k) or {}).get(f)  # noqa: E731
    return {"seconds": rig.get("duration_s"), "size": [rig["config"]["width"], rig["config"]["height"]],
            "good_fps": [c["fps_mean"] for c in cams], "damaged": [c.get("truncated", 0) + c.get("torn", 0) for c in cams],
            "frames": [c["frames"] for c in cams], "open_errors": [c["open_error"] for c in cams if c.get("open_error")],
            "ai_sets_per_s": ai.get("sets_per_s_mean"), "ai_batch_ms_median": (ai.get("total_ms") or {}).get("median"),
            "ai_result_age_ms_median": (ai.get("result_age_oldest_frame_ms") or {}).get("median"),
            "lidar_hz": lidar.get("hz_mean"), "lidar_errors": lidar.get("errors"),
            "sets": (rig.get("sets") or {}).get("sets_built"), "sets_partial_wait": (rig.get("sets") or {}).get("sets_partial_wait"),
            "lagging_per_port": [((rig.get("sets") or {}).get("lagging_per_port") or {}).get(str(c["port"]),
                                 ((rig.get("sets") or {}).get("lagging_per_port") or {}).get(c["port"], 0)) for c in cams],
            "proc_cpu_cores": pick("proc_cpu_cores"), "gpu_util_pct": pick("gpu_util_pct"),
            "gpu_temp_last": pick("gpu_temp_c", "last"), "stop_alive": rig.get("stop_alive")}


def build_digest(out: Path, results: dict) -> dict:
    digest = {"env": (results.get("env") or {}).get("value"), "steps": {k: v.get("ok") for k, v in results.items()},
              "errors": {k: v.get("error") for k, v in results.items() if not v.get("ok")}}
    usb = load_json(out / "usb_topology.json")
    if usb:
        mapping = usb.get("dshow_index_to_port", [])
        digest["usb"] = {"cameras": len(mapping), "with_hub_port": sum(m.get("hub_port") is not None for m in mapping),
                         "hubs": [h.get("friendly_name") for h in usb.get("hubs", [])]}
    # đọc từ đĩa trước (chạy lại vài bước bằng --steps vẫn giữ kết quả các bước cũ), rồi mới tới kết quả của lần chạy này
    lidar = dict((results.get("lidar") or {}).get("value") or {})
    info = load_json(out / "lidar_info.json") or {}
    lidar.setdefault("health", (info.get("health") or {}).get("name"))
    analysis_path = Path(lidar.get("analysis") or out / "lidar" / "l01_tinh.analysis.json")
    analysis = load_json(analysis_path)
    if analysis:
        s = analysis.get("summary", {})
        digest["lidar"] = {"port": lidar.get("port"), "health": lidar.get("health"), "rate_hz": s.get("rate_hz"),
                           "beams_median": s.get("beams_median"), "no_return_fraction": s.get("no_return_fraction"),
                           "passed": analysis.get("passed")}
    elif lidar:
        digest["lidar"] = {"port": lidar.get("port"), "health": lidar.get("health")}
    ai = (results.get("ai") or {}).get("value") or load_json(out / "ai_latency.json")
    if ai:
        digest["ai"] = {"total_ms_median": ai["total_ms"]["median"], "total_ms_p95": ai["total_ms"]["p95"],
                        "model_ms_median": ai["model_ms"]["median"], "peak_vram_mb": ai.get("peak_vram_mb"),
                        "device": ai.get("device")}
    digest["rig480"] = rig_digest(load_json(out / "m01_480p_lidar_ai.rig.json"))
    digest["cam720"] = rig_digest(load_json(out / "m02_720p_chi_camera.rig.json"))
    return digest


def _fmt(value, nd=1):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{nd}f}".replace(".", ",")
    if isinstance(value, list):
        return " / ".join(_fmt(v, nd) for v in value)
    return str(value)


def summary_markdown(digest: dict, reference: dict | None) -> str:
    ref = (reference or {}).get("digest") or {}
    env = digest.get("env") or {}
    lines = [f"# Kiểm máy mới — {env.get('created_local', '')}", "",
             f"Máy: {env.get('processor') or env.get('machine')}, {env.get('cpu_count')} luồng, RAM {env.get('ram_gb')} GB, "
             f"{env.get('platform')}. GPU: {env.get('gpu', '—')} ({env.get('gpu_vram_gb', '—')} GB), driver "
             f"{env.get('nvidia_driver', '—')}, torch {env.get('torch', '—')} CUDA {env.get('cuda_runtime', '—')}, "
             f"OpenCV {env.get('opencv', '—')}, Python {env.get('python')}.", ""]
    failed = digest.get("errors") or {}
    lines.append("Bước lỗi: " + (", ".join(f"{k} ({v})" for k, v in failed.items()) if failed else "không có") + ".")
    lines += ["", "| Số đo | Máy này | Máy bàn (tham chiếu) |", "|---|---|---|"]

    def row(label, path, nd=1):
        def get(d):
            for key in path:
                d = (d or {}).get(key) if isinstance(d, dict) else None
            return d
        lines.append(f"| {label} | {_fmt(get(digest), nd)} | {_fmt(get(ref), nd)} |")

    row("Camera thấy qua DirectShow / có số cổng hub", ("usb", "cameras"))
    row("… trong đó có số cổng hub", ("usb", "with_hub_port"))
    row("LiDAR: cổng COM", ("lidar", "port"))
    row("LiDAR: tốc độ quay (Hz)", ("lidar", "rate_hz"), 2)
    row("LiDAR: số tia mỗi vòng (trung vị)", ("lidar", "beams_median"), 0)
    row("AI: một lô 4 ảnh 480p, trung vị (ms)", ("ai", "total_ms_median"))
    row("AI: một lô, p95 (ms)", ("ai", "total_ms_p95"))
    row("AI: VRAM đỉnh (MB)", ("ai", "peak_vram_mb"), 0)
    row("Bàn thử 480p: khung tốt/s từng camera", ("rig480", "good_fps"), 2)
    row("Bàn thử 480p: khung hỏng từng camera", ("rig480", "damaged"), 0)
    row("Bàn thử 480p: bộ AI/s", ("rig480", "ai_sets_per_s"), 2)
    row("Bàn thử 480p: một lô AI, trung vị (ms)", ("rig480", "ai_batch_ms_median"))
    row("Bàn thử 480p: tuổi kết quả AI, trung vị (ms)", ("rig480", "ai_result_age_ms_median"))
    row("Bàn thử 480p: LiDAR (Hz)", ("rig480", "lidar_hz"), 2)
    row("Bàn thử 480p: CPU tiến trình (lõi)", ("rig480", "proc_cpu_cores"), 2)
    row("Bàn thử 480p: GPU (%)", ("rig480", "gpu_util_pct"), 0)
    row("Bàn thử 480p: số bộ ảnh", ("rig480", "sets"), 0)
    row("… bộ thiếu camera chậm", ("rig480", "sets_partial_wait"), 0)
    row("720p chỉ camera: khung tốt/s", ("cam720", "good_fps"), 2)
    row("720p chỉ camera: khung hỏng", ("cam720", "damaged"), 0)
    row("720p chỉ camera: bộ ảnh", ("cam720", "sets"), 0)
    row("… bộ thiếu camera chậm", ("cam720", "sets_partial_wait"), 0)
    row("… số lần từng cổng bị bỏ vì chậm", ("cam720", "lagging_per_port"), 0)
    lines += ["", "Ghi chú:",
              "- Khung hỏng ở 720p phụ thuộc cảnh camera nhìn (cảnh nhiều chi tiết cho khung JPEG lớn hơn): so hai máy thì "
              "đặt camera nhìn cùng một cảnh.",
              "- Tham chiếu máy bàn: " + ((reference or {}).get("note") or "chưa có tệp tham chiếu") + ".",
              "- Chi tiết từng bước: `may_moi.json`, `*.rig.json`, `lidar/`, `ai_latency.json`, `usb_topology.json`."]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------------------------- CLI

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", type=Path, default=None, help="thư mục kết quả (mặc định runs/may_moi_<ngày giờ>)")
    p.add_argument("--lidar", default=None, help="cổng COM của LiDAR; mặc định tự tìm bộ chuyển CP210x")
    p.add_argument("--seconds", type=float, default=120.0, help="thời lượng phiên bàn thử 480p")
    p.add_argument("--steps", nargs="*", default=list(STEPS), choices=STEPS)
    p.add_argument("--checkpoint", default=None, help="mặc định: runs/ai_woodscape_rtx4000_v1/best.pt")
    p.add_argument("--runs", default="runs")
    p.add_argument("--dry-run", action="store_true", help="in kế hoạch, không mở thiết bị nào")
    args = p.parse_args(argv)
    out = args.out or Path(args.runs) / f"may_moi_{datetime.now():%Y%m%d_%H%M}"
    root = Path(__file__).resolve().parents[2]
    print(f"Kết quả vào: {out}\nCác bước: {', '.join(args.steps)}", flush=True)
    if args.dry_run:
        return 0
    out.mkdir(parents=True, exist_ok=True)
    previous = load_json(out / "may_moi.json") or {}
    results: dict = dict(previous.get("results") or {})          # chạy lại vài bước: giữ kết quả các bước khác
    context: dict = {}

    def checkpoint() -> str:
        if args.checkpoint:
            return args.checkpoint
        reference = Path(args.runs) / "ai_woodscape_rtx4000_v1" / "best.pt"
        found = [reference] if reference.exists() else sorted(Path(args.runs).glob("*/best.pt"))
        if not found:
            raise FileNotFoundError(f"không có checkpoint trong {args.runs}/*/best.pt — chép "
                                    "runs/ai_woodscape_rtx4000_v1/best.pt từ máy bàn (docs/MAY_NOP_DO_AN.md bước 2)")
        return str(found[0])

    def lidar_port() -> str:
        if "lidar_port" not in context:
            context["lidar_port"] = args.lidar or find_lidar_port()
        if not context["lidar_port"]:
            raise RuntimeError("không thấy bộ chuyển CP210x của LiDAR (cắm LiDAR, cài driver CP210x, hoặc truyền --lidar COMx)")
        return context["lidar_port"]

    def cameras() -> dict:
        if "cameras" not in context:
            context["cameras"] = camera_selection()
            print("camera:", context["cameras"]["note"], context["cameras"]["argv"], flush=True)
        return context["cameras"]

    if "env" in args.steps:
        run_step("env", lambda: env_report(), results)
        (out / "env.json").write_text(json.dumps((results["env"].get("value") or {}), ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    if "usb" in args.steps:
        def usb():
            from autopark.video import camera_bench as cb
            code = cb.main(["list", "--out", str(out / "usb_topology.json")])
            if code:
                raise RuntimeError(f"camera_bench list trả mã {code}")
            return {"file": str(out / "usb_topology.json")}
        run_step("usb", usb, results)
    if "lidar" in args.steps:
        def lidar():
            from autopark.lidar import bench as lidar_bench
            from autopark.lidar import rplidar_c1
            port = lidar_port()
            code, text = capture_stdout(lambda: rplidar_c1.main(["info", "--port", port]))
            info = json.loads(text[text.index("{"):]) if "{" in text else {"raw": text}
            (out / "lidar_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
            code = lidar_bench.main(["record", "--port", port, "--out", str(out / "lidar"), "--name", "l01_tinh",
                                     "--seconds", "15", "--warmup", "3", "--note", "kiểm máy mới"])
            return {"port": port, "health": (info.get("health") or {}).get("name"),
                    "serial": (info.get("device") or {}).get("serial"),
                    "analysis": str(out / "lidar" / "l01_tinh.analysis.json"), "bench_exit": code}
        run_step("lidar", lidar, results)
    if "ai" in args.steps:
        def ai():
            path = checkpoint()
            try:
                from autopark.perception.live import LiveSegmenter
            except ImportError as exc:
                raise RuntimeError(f"thiếu {exc.name}: chạy lệnh này bằng .venv-train (có torch), không phải .venv") from exc
            value = ai_latency(lambda: LiveSegmenter(path))
            value["checkpoint"] = path
            (out / "ai_latency.json").write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
            return value
        run_step("ai", ai, results)
    if "rig480" in args.steps:
        def rig480():
            from autopark.rig import bench
            argv_ = [*cameras()["argv"], "--seconds", str(args.seconds), "--name", "m01_480p_lidar_ai", "--out", str(out),
                     "--checkpoint", checkpoint(), "--note", "kiểm máy mới, 480p + LiDAR + AI"]
            try:
                argv_ += ["--lidar", lidar_port()]
            except RuntimeError as exc:
                print(f"chạy không LiDAR: {exc}", flush=True)
            code = bench.main(argv_)
            if code:
                raise RuntimeError(f"rig.bench trả mã {code}: camera không mở, LiDAR không quét, AI không chạy hoặc luồng "
                                   "chưa dừng (xem log phía trên; tệp .rig.json vẫn được ghi)")
            return {"exit": code}
        run_step("rig480", rig480, results)
    if "cam720" in args.steps:
        def cam720():
            from autopark.rig import bench
            code = bench.main([*cameras()["argv"], "--width", "1280", "--height", "720", "--no-ai", "--seconds", "30",
                               "--name", "m02_720p_chi_camera", "--out", str(out),
                               "--note", "kiểm máy mới, 720p chỉ camera: khung bị cắt"])
            if code:
                raise RuntimeError(f"rig.bench 720p trả mã {code} (xem log phía trên)")
            return {"exit": code}
        run_step("cam720", cam720, results)

    digest = build_digest(out, results)
    reference = find_reference(root)
    (out / "may_moi.json").write_text(json.dumps({"results": results, "digest": digest}, ensure_ascii=False, indent=1,
                                                 default=str), encoding="utf-8")
    text = summary_markdown(digest, reference)
    (out / "tom_tat.md").write_text(text, encoding="utf-8")
    print("\n" + text)
    print(f"Đã ghi {out / 'tom_tat.md'} và {out / 'may_moi.json'}")
    return 0 if all(v.get("ok") for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
