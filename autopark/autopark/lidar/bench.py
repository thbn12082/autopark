"""Phiên đo tĩnh LiDAR: ghi từng lần đặt vật, tính số đo, vẽ hình, gộp báo cáo (bước 2–3 "Khi nhận LiDAR").

    python -m autopark.lidar.bench record --out runs/lidar_bench/20260922 --name p01_truoc_0.5m \
        --seconds 15 --expected-distance 0.5 --expected-angle 0 [--warmup 120] [--mirror] [--port COMx]
    python -m autopark.lidar.bench analyze runs/lidar_bench/20260922/p01_truoc_0.5m.npz --expected-distance 0.5 --expected-angle 0
    python -m autopark.lidar.bench report runs/lidar_bench/20260922

Góc kỳ vọng theo quy ước dự án: độ, 0 là phía trước, dương về bên trái. Với mỗi bản ghi: tần số vòng, chu kỳ,
khoảng trống lớn nhất, số tia mỗi vòng, tỉ lệ tia không phản hồi; nếu có vật kỳ vọng: trong cửa sổ ±window°
quanh hướng kỳ vọng lấy trung vị khoảng cách từng vòng, rồi trung vị và độ lệch chuẩn qua các vòng, sai số so
với thước (mm), và hướng quan sát được của điểm gần nhất trong ±45° để chốt dấu góc. Ngưỡng đạt lấy từ
datasheet C1 (±30 mm, 8–12 Hz, 5 kHz mẫu); TIMEOUT hay lệch ngưỡng được ghi, không suy ra nguyên nhân.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

from autopark.image_io import imwrite
from autopark.perception.paths import atomic_write_json, utc_now
from autopark.power_throttling import apply_ecoqos_policy

from .recording import Recording, ScanRecorder, default_meta, read_recording, summarize
from .render import render_scan
from .rplidar_protocol import wrap_angle

SAMPLE_RATE_HZ = 5000.0          # datasheet: 5 kHz sample rate
RATE_RANGE_HZ = (8.0, 12.0)      # datasheet: 8–12 Hz
ACCURACY_M = 0.030               # datasheet: ±30 mm
DIRECTION_TOLERANCE_DEG = 5.0


def window_metrics(recording: Recording, expected_distance: float, expected_angle_deg: float, *,
                   window_deg: float = 5.0, search_deg: float = 45.0, skip_s: float = 0.0,
                   cluster_m: float = 0.05) -> dict:
    expected = math.radians(expected_angle_deg)
    window, search = math.radians(window_deg), math.radians(search_deg)
    medians, spreads, counts, nearest_angles, nearest_ranges = [], [], [], [], []
    t_start = recording.t[0] + skip_s
    for index in range(len(recording)):
        if recording.t[index] < t_start:
            continue
        angles, ranges, _ = recording.beams(index)
        finite = np.isfinite(ranges)
        offset = np.abs(wrap_angle(angles.astype(np.float64) - expected))
        inside = finite & (offset <= window)
        if inside.any():
            medians.append(float(np.median(ranges[inside])))
            spreads.append(float(np.std(ranges[inside])))
        counts.append(int(inside.sum()))
        near = finite & (offset <= search)
        if near.any():
            # the closest surface inside the search window: every beam within `cluster_m` of the minimum range;
            # its circular mean angle is the observed direction (a flat face has no single nearest beam)
            nearest = float(ranges[near].min())
            cluster = near & (ranges <= nearest + cluster_m)
            nearest_angles.append(math.atan2(float(np.sin(angles[cluster]).mean()), float(np.cos(angles[cluster]).mean())))
            nearest_ranges.append(nearest)
    if not medians:
        return {"scans_with_target": 0, "expected_distance_m": expected_distance, "expected_angle_deg": expected_angle_deg}
    medians_arr = np.array(medians)
    measured = float(np.median(medians_arr))
    observed_angle = math.degrees(float(np.median(nearest_angles))) if nearest_angles else None
    return {"expected_distance_m": expected_distance, "expected_angle_deg": expected_angle_deg,
            "window_deg": window_deg, "scans_with_target": len(medians),
            "beams_in_window_median": float(np.median(counts)) if counts else 0.0,
            "measured_distance_m": measured, "error_mm": (measured - expected_distance) * 1000.0,
            "spread_between_scans_mm": float(np.std(medians_arr)) * 1000.0,
            "spread_within_scan_mm": float(np.mean(spreads)) * 1000.0,
            "nearest_point_angle_deg": observed_angle,
            "nearest_point_range_m": float(np.median(nearest_ranges)) if nearest_ranges else None,
            "direction_error_deg": None if observed_angle is None else
            math.degrees(wrap_angle(np.array([math.radians(observed_angle) - expected]))[0])}


def analyze(recording: Recording, expected_distance: float | None = None, expected_angle_deg: float | None = None,
            *, window_deg: float = 5.0, skip_s: float = 0.0) -> dict:
    summary = summarize(recording)
    checks = {}
    rate = summary["rate_hz"]
    if rate:
        checks["rate_8_12_hz"] = RATE_RANGE_HZ[0] <= rate <= RATE_RANGE_HZ[1]
        expected_beams = SAMPLE_RATE_HZ / rate
        checks["beams_within_5pct_of_5khz"] = abs(summary["beams_median"] - expected_beams) <= 0.05 * expected_beams
        checks["no_gap_over_3_periods"] = summary["max_gap_s"] <= 3 * summary["median_period_s"]
    result = {"file": recording.path.name, "analyzed_utc": utc_now(), "summary": summary, "checks": checks,
              "target": None}
    if expected_distance is not None and expected_angle_deg is not None:
        target = window_metrics(recording, expected_distance, expected_angle_deg, window_deg=window_deg, skip_s=skip_s)
        result["target"] = target
        if target.get("scans_with_target"):
            checks["error_within_30mm"] = abs(target["error_mm"]) <= ACCURACY_M * 1000.0
            checks["direction_within_5deg"] = (target["direction_error_deg"] is not None
                                               and abs(target["direction_error_deg"]) <= DIRECTION_TOLERANCE_DEG)
        else:
            checks["error_within_30mm"] = False
            checks["direction_within_5deg"] = False
    result["passed"] = all(checks.values()) if checks else None
    return result


def render_placement(recording: Recording, path, expected_distance: float | None = None,
                     expected_angle_deg: float | None = None, max_range: float = 4.0) -> Path:
    index = len(recording) - 1
    scan = recording.scan(index)
    detections = [] if expected_distance is None else [(expected_distance, math.radians(expected_angle_deg or 0.0))]
    title = f"{recording.path.stem}  scan {index + 1}/{len(recording)}  beams {recording.n_beams[index]}"
    image = render_scan(scan, size=700, max_range=max_range, detections=detections, title=title)
    path = Path(path)
    imwrite(path, image)
    return path


def record(args) -> int:
    from .rplidar_c1 import RplidarC1Source, ScanReadError

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    source = RplidarC1Source.open(args.port, mirror=args.mirror)
    try:
        source.stop_output()
        modes = source.scan_modes()             # only answered while the device is not streaming
        source.start()
        described = source.describe()
        described.pop("source_id", None)
        if args.warmup > 0:
            print(f"làm nóng {args.warmup:.0f} s ...", flush=True)
            end = time.monotonic() + args.warmup
            while time.monotonic() < end:
                source.read()
        meta = default_meta(source.source_id, port=args.port, baudrate=source.transport.baudrate, name=args.name,
                            placement={"expected_distance_m": args.expected_distance,
                                       "expected_angle_deg": args.expected_angle, "note": args.note},
                            warmup_s=args.warmup, requested_seconds=args.seconds, **described)
        recorder = ScanRecorder(out / args.name, meta)
        end = time.monotonic() + args.seconds
        errors = 0
        while time.monotonic() < end:
            try:
                scan = source.read()
            except ScanReadError as exc:
                errors += 1
                print(f"LỖI ĐỌC: {exc}", flush=True)
                if errors >= 3:
                    break
                continue
            recorder.add(scan, quality=source.last_quality, t_first=source.last_revolution.t_first)
        path = recorder.close({"driver_stats": source.stats(), "read_errors": errors, "scan_modes": modes})
    finally:
        try:
            source.close()
        except OSError as exc:
            # Cổng đã chết (rút cáp): close() không gửi được STOP. Không ném lần hai trong finally — phần đã ghi vẫn được
            # lưu và phân tích bên dưới (sửa tối 24/09/2026; trước đó kết thúc bằng traceback, mất phần phân tích).
            print(f"CẢNH BÁO: đóng LiDAR không trọn vẹn (cổng đã lỗi, không gửi được STOP): {type(exc).__name__}: {exc}",
                  flush=True)
    recording = read_recording(path)
    result = analyze(recording, args.expected_distance, args.expected_angle, window_deg=args.window)
    atomic_write_json(path.with_name(path.stem + ".analysis.json"), result)
    render_placement(recording, path.with_suffix(".png"), args.expected_distance, args.expected_angle, max_range=args.max_range)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors >= 3:
        print(f"CẢNH BÁO: phiên dừng sớm sau {errors} lỗi đọc (đếm cả phiên, không phải liên tiếp); bản ghi chỉ có phần trước lỗi", flush=True)
        return 1
    return 0


def analyze_command(args) -> int:
    recording = read_recording(args.recording)
    result = analyze(recording, args.expected_distance, args.expected_angle, window_deg=args.window, skip_s=args.skip)
    atomic_write_json(recording.path.with_name(recording.path.stem + ".analysis.json"), result)
    render_placement(recording, recording.path.with_suffix(".png"), args.expected_distance, args.expected_angle,
                     max_range=args.max_range)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def report(directory) -> str:
    directory = Path(directory)
    rows = []
    for path in sorted(directory.glob("*.analysis.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        s, t = result["summary"], result.get("target") or {}
        rows.append("| {name} | {exp} | {meas} | {err} | {dir} | {rate} | {beams} | {nan} | {gap} | {ok} |".format(
            name=path.name.replace(".analysis.json", ""),
            exp="" if not t else f"{t['expected_distance_m']:.2f} m @ {t['expected_angle_deg']:.0f}°",
            meas="" if not t.get("scans_with_target") else f"{t['measured_distance_m']:.3f}",
            err="" if not t.get("scans_with_target") else f"{t['error_mm']:+.0f}",
            dir="" if not t.get("scans_with_target") or t.get("nearest_point_angle_deg") is None else f"{t['nearest_point_angle_deg']:+.1f}",
            rate=f"{s['rate_hz']:.2f}" if s["rate_hz"] else "", beams=f"{s['beams_median']:.0f}" if s["beams_median"] else "",
            nan=f"{100 * s['no_return_fraction']:.1f} %" if s["no_return_fraction"] is not None else "",
            gap=f"{1000 * s['max_gap_s']:.0f}" if s["max_gap_s"] is not None else "",
            ok={True: "ĐẠT", False: "KHÔNG", None: "-"}[result["passed"]] + ("" if result["passed"] is not False else
                " (" + ", ".join(k for k, v in result["checks"].items() if not v) + ")")))
    header = ("| Lần đặt | Kỳ vọng | Đo (m) | Sai số (mm) | Hướng điểm gần nhất (°) | Tần số (Hz) | Tia/vòng | "
              "Không phản hồi | Trống lớn nhất (ms) | Kết quả |\n|---|---|---|---|---|---|---|---|---|---|")
    text = header + "\n" + "\n".join(rows) + "\n"
    (directory / "report.md").write_text(text, encoding="utf-8")
    return text


def main(argv=None) -> int:
    apply_ecoqos_policy("lidar.bench")                 # trước mọi việc khác; trạng thái vào meta (default_meta)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("record", help="record one placement from the device and analyse it")
    r.add_argument("--port", default=None, help="cổng COM (hoặc auto); mặc định lidar_port trong configs/thiet_bi.json")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--name", required=True, help="file stem, e.g. p01_truoc_0.5m")
    r.add_argument("--seconds", type=float, default=15.0)
    r.add_argument("--warmup", type=float, default=0.0, help="seconds to scan and discard before recording")
    r.add_argument("--expected-distance", type=float, default=None, help="tape-measured distance to the target face (m)")
    r.add_argument("--expected-angle", type=float, default=None, help="target direction, project convention (deg)")
    r.add_argument("--window", type=float, default=5.0)
    r.add_argument("--max-range", type=float, default=4.0, help="picture radius (m)")
    r.add_argument("--mirror", action="store_true")
    r.add_argument("--note", default="")
    a = sub.add_parser("analyze", help="re-analyse an existing recording")
    a.add_argument("recording", type=Path)
    a.add_argument("--expected-distance", type=float, default=None)
    a.add_argument("--expected-angle", type=float, default=None)
    a.add_argument("--window", type=float, default=5.0)
    a.add_argument("--skip", type=float, default=0.0, help="ignore the first seconds of the recording")
    a.add_argument("--max-range", type=float, default=4.0)
    p = sub.add_parser("report", help="write report.md from the *.analysis.json files of a directory")
    p.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    if args.command == "record":
        from .port import LidarPortError, lidar_port

        try:
            args.port = lidar_port(args.port)        # bản ghi lưu cổng thật đã mở
        except LidarPortError as exc:
            parser.error(str(exc))
        return record(args)
    if args.command == "analyze":
        return analyze_command(args)
    print(report(args.directory))
    return 0


if __name__ == "__main__":
    sys.exit(main())
