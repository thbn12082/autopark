r"""Phát lại một bản ghi chạy xe (LiDAR + bốn camera, nút "Ghi LiDAR" có "Kèm camera") qua ảnh quanh xe (29/11/2026).

    .venv\Scripts\python.exe -X utf8 -m autopark.perception.bev_replay --recording runs\lidar_pi\chay_<giờ>.npz --out runs\bev\replay

Mỗi khung: odometry khớp scan LiDAR cho tư thế xe, ảnh nhớ mặt sàn lấp vùng mù bằng ảnh thật đã thấy, phần còn lại AI
(LaMa) vẽ, điểm LiDAR canh vùng tô. Ghi `bev.mp4` (ảnh quanh xe cạnh bốn camera), vài ảnh `.png` và `tom_tat.json`
(tỉ lệ vùng mù lấy từ ảnh nhớ theo thời gian, trạng thái odometry). Chạy AI đồng bộ (`--ai sync`, mặc định) để mỗi
khung có kết quả AI như khi xem trực tiếp đủ lâu; `--ai off` để so.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def load_camera_index(cam_dir: Path) -> dict[int, list[tuple[int, Path]]]:
    out = {}
    for port in (1, 2, 3, 4):
        files = sorted((int(p.stem), p) for p in (cam_dir / f"cam_p{port}").glob("*.jpg") if p.stem.isdigit())
        out[port] = files
    return out


def latest_before(files: list[tuple[int, Path]], t_ns: int) -> Path | None:
    lo, hi = 0, len(files)
    while lo < hi:
        mid = (lo + hi) // 2
        if files[mid][0] <= t_ns:
            lo = mid + 1
        else:
            hi = mid
    return files[lo - 1][1] if lo else None


def read_jpeg(path: Path) -> np.ndarray | None:
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)


def replay(recording: Path, out: Path, *, ai: str = "sync", fps: float = 5.0, max_frames: int | None = None) -> dict:
    from autopark.lidar.recording import read_lidar_any
    from autopark.lidar.scan_odometry import ScanOdometry
    from autopark.perception import surround_view as sv

    rec = read_lidar_any(recording)
    cam_dir = Path(str(recording).removesuffix(".npz") + "_cam")
    cams = load_camera_index(cam_dir)
    if not all(cams.values()):
        raise SystemExit(f"thiếu ảnh camera trong {cam_dir} (cần cam_p1..cam_p4/*.jpg)")
    out.mkdir(parents=True, exist_ok=True)

    renderer = sv.SurroundViewRenderer(ai_fill=(ai != "off"))
    if renderer.is_preview:
        raise SystemExit("chưa hiệu chuẩn đủ bốn camera (ảnh quanh xe đang ở chế độ xem thử)")
    if ai == "sync" and renderer._fill_gaps:
        from autopark.perception import bev_inpaint
        inpainter = bev_inpaint.shared_inpainter()
        if inpainter is None:
            raise SystemExit(f"không dùng được LaMa: {bev_inpaint.shared_error()}")
        tiled = bev_inpaint.TiledFill(inpainter.fill, renderer._gaps.shape)
        renderer._ai_result = lambda composite: tiled(composite, renderer._gaps)      # chờ AI mỗi khung (phát lại)

    odo = ScanOdometry()
    scan_t = rec.t
    t_start = max(scan_t[0], max(files[0][0] for files in cams.values()) * 1e-9)
    t_end = min(scan_t[-1], min(files[-1][0] for files in cams.values()) * 1e-9)
    times = np.arange(t_start, t_end, 1.0 / fps)
    if max_frames:
        times = times[:max_frames]
    writer = None
    summary = {"recording": str(recording), "frames": 0, "odometry_failed_scans": 0, "memory_fraction": []}
    next_scan, pose = 0, None
    for k, t in enumerate(times):
        while next_scan < len(scan_t) and scan_t[next_scan] <= t:
            a0, a1 = rec.offsets[next_scan], rec.offsets[next_scan + 1]
            step = odo.update(rec.angles[a0:a1].astype(np.float64), rec.ranges[a0:a1].astype(np.float64),
                              float(scan_t[next_scan]))
            if step.status == "FAILED":
                summary["odometry_failed_scans"] += 1
            else:
                pose = (float(step.x), float(step.y), float(step.theta))
            last_scan = (rec.angles[a0:a1], rec.ranges[a0:a1])
            next_scan += 1
        frames = {}
        for port, files in cams.items():
            path = latest_before(files, int(t * 1e9))
            image = read_jpeg(path) if path is not None else None
            if image is not None:
                frames[port] = image
        if len(frames) < 4 or next_scan == 0:
            continue
        angles, ranges = last_scan
        good = np.isfinite(ranges) & (ranges > 0.02)
        th = angles[good] + np.radians(sv.LIDAR_YAW_DEG)
        lidar_xy = np.column_stack([sv.LIDAR_MOUNT_XY[0] + ranges[good] * np.cos(th),
                                    sv.LIDAR_MOUNT_XY[1] + ranges[good] * np.sin(th)])
        bev = renderer.render(frames, lidar_xy=lidar_xy, lidar_pose=pose, pose_epoch=1)
        summary["memory_fraction"].append(round(renderer.memory_fraction, 3))
        cams_small = [cv2.resize(frames[p], (320, 180)) for p in (1, 2, 3, 4)]
        side = np.vstack([np.hstack(cams_small[:2]), np.hstack(cams_small[2:])])
        side = cv2.resize(side, (640, 360))
        canvas = np.zeros((480, 480 + 640, 3), np.uint8)
        canvas[:, :480] = bev
        canvas[60:420, 480:] = side
        cv2.putText(canvas, f"t={t - t_start:5.1f}s anh nho {100 * renderer.memory_fraction:3.0f}%", (490, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        if writer is None:
            writer = cv2.VideoWriter(str(out / "bev.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps,
                                     (canvas.shape[1], canvas.shape[0]))
        writer.write(canvas)
        if k % max(1, int(fps * 5)) == 0:
            cv2.imencode(".png", canvas)[1].tofile(str(out / f"khung_{k:04d}.png"))
        summary["frames"] += 1
    if writer is not None:
        writer.release()
    renderer.close()
    fractions = summary["memory_fraction"]
    summary["memory_fraction_mean"] = round(float(np.mean(fractions)), 3) if fractions else 0.0
    (out / "tom_tat.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Phát lại bản ghi chạy xe qua ảnh quanh xe (ảnh nhớ + AI + LiDAR canh)")
    p.add_argument("--recording", type=Path, required=True, help="runs/lidar_pi/chay_<giờ>.npz (kèm thư mục _cam)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--ai", choices=("sync", "off"), default="sync")
    p.add_argument("--fps", type=float, default=5.0)
    p.add_argument("--max-frames", type=int, default=None)
    a = p.parse_args(argv)
    s = replay(a.recording, a.out, ai=a.ai, fps=a.fps, max_frames=a.max_frames)
    print(f"{s['frames']} khung → {a.out / 'bev.mp4'}; ảnh nhớ trung bình {100 * s['memory_fraction_mean']:.0f}% vùng mù;"
          f" odometry hỏng {s['odometry_failed_scans']} vòng")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
