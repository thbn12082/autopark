"""Phiên đo không giao diện: bốn camera + LiDAR + AI chạy đồng thời trong T giây, ghi số đo ra json.

    python -m autopark.rig.bench --ports 1 2 3 4 --lidar COM4 --seconds 120 --name u01_4cam_lidar_ai_480p --out runs/rig_bench/20260923_v3

Chạy trong `.venv-train` (cần torch cho AI; `--no-ai` thì chạy được cả trong `.venv`). Camera được chọn theo CỔNG HUB
(index OpenCV đổi sau khởi động lại). Kết quả: `<name>.rig.json` gồm cấu hình, số đo từng camera, độ lệch bộ ảnh,
LiDAR, AI (thời gian từng khâu, tuổi kết quả), tài nguyên (CPU, RAM, GPU, nhiệt độ GPU) và chuỗi theo giây.

`--max-wait-ms` (mặc định 60; ≤ 0 = quy tắc cũ, chờ mọi camera) là SÀN của ngưỡng chờ camera chưa có khung mới; ngưỡng
thực = max(sàn, 1,5 × chu kỳ khung TRUNG BÌNH đo được của camera nhanh nhất) — ≈ 63 ms ở 24 fps (nhịp xen kẽ 31/48 ms,
trung bình 41,9 ms), ≈ 100 ms ở 15 fps — rồi AI chấm bộ không có camera đó. Số bộ như thế và số lần từng cổng bị bỏ
được ghi ("chậm" trên dòng trực tiếp, `sets_partial_wait`, `lagging_per_port` trong json), cùng ngưỡng thực đã dùng
(`wait_limit_ms`) và số bộ phải để dành camera lệch pha cho bộ sau (`sets_regrouped`). Muốn so với số đo cũ (loạt
20260923_v3, trước khi có quy tắc này) thì chạy `--max-wait-ms 0`. Các số trên của phiên bật chờ chạy trước bản sửa bộ
ước lượng chu kỳ ngày 24/09 KHÔNG dùng được: bản đó ước chu kỳ ≈ 24–33 ms trên nhịp 31/48 ms và ghi "chậm" cho camera
khỏe (xem `video.multicam`).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from autopark.rig.core import Rig, RigConfig
from autopark.video.multicam import RIG_CLOCK, CameraSpec, MultiCameraManager, resolve_ports


def build_rig(args) -> Rig:
    specs = resolve_ports(args.ports) if args.index is None else \
        [CameraSpec(port=p, index=i) for p, i in zip(args.ports or range(len(args.index)), args.index)]
    clock = RIG_CLOCK                    # MỘT đồng hồ cho camera, LiDAR và rig (LiDAR cộng t0 của driver vào stamp)
    cams = MultiCameraManager(specs, width=args.width, height=args.height, fps=args.fps, fourcc=args.fourcc,
                              exposure=args.exposure, ring=args.ring, clock=clock)
    make_segmenter = None
    checkpoint = None
    if not args.no_ai:
        from autopark.perception.live import LiveSegmenter, list_checkpoints
        checkpoint = str(args.checkpoint or list_checkpoints(args.runs)[0])

        def make_segmenter(path: str):
            return LiveSegmenter(path, device=args.device)
    open_lidar = None
    if args.lidar:
        from autopark.lidar.rplidar_c1 import RplidarC1Source

        def open_lidar():
            return RplidarC1Source.open(args.lidar, mirror=args.mirror, clock=clock, first_revolution_timeout_s=4.0)
    cfg = RigConfig(width=args.width, height=args.height, fps=args.fps, fourcc=args.fourcc, exposure=args.exposure,
                    max_skew_s=None if args.max_skew_ms <= 0 else args.max_skew_ms / 1000.0,
                    max_wait_s=None if args.max_wait_ms <= 0 else args.max_wait_ms / 1000.0,
                    display_width=args.display_width, ai=not args.no_ai, checkpoint=checkpoint,
                    lidar_port=args.lidar, notes={"name": getattr(args, "name", None), "note": getattr(args, "note", "")})
    return Rig(cams, cfg, make_segmenter=make_segmenter, open_lidar=open_lidar, clock=clock)


def print_line(snap: dict) -> None:
    lagging = snap["cameras"].get("lagging_per_port", {})
    cams = " | ".join(f"p{c['port']} {c['fps_last2s']:.1f}fps cũ{c['duplicates']} cắt{c['truncated']} xé{c['torn']}"
                      f" chậm{lagging.get(c['port'], 0)}" + (" LỖI" if c["open_error"] else "")
                      for c in snap["cameras"]["cameras"])
    limit = (snap["cameras"].get("wait_limit_ms") or {}).get("median")
    parts = [f"t={snap['t_s']:6.1f}s", cams, f"bộ thiếu cam chậm {snap['cameras'].get('sets_partial_wait', 0)}"
             + ("" if limit is None else f" (ngưỡng chờ {limit} ms)")]
    if snap["lidar"]:
        parts.append(f"LiDAR {snap['lidar']['hz_last3s']:.1f}Hz")
    if snap["ai"]:
        a = snap["ai"]
        parts.append(f"AI {a['sets_per_s_last3s']:.1f} bộ/s {a['total_ms']['median']} ms")
    r = snap["resources"] or {}
    if r:
        parts.append(f"CPU {r.get('proc_cpu_cores')} lõi GPU {r.get('gpu_util_pct')}% {r.get('gpu_temp_c')}°C")
    print("  " + "  ·  ".join(str(p) for p in parts), flush=True)


def add_rig_args(p: argparse.ArgumentParser) -> None:
    """Tham số chung của lệnh đo và giao diện."""
    p.add_argument("--ports", type=int, nargs="*", default=None, help="cổng hub (mặc định: mọi camera thấy được)")
    p.add_argument("--index", type=int, nargs="*", default=None, help="bỏ qua tra cổng, mở theo index OpenCV (thử nhanh)")
    # Mặc định 640×480: đo 23/09/2026 bốn camera qua hub UGREEN, 720p có camera gần như MỌI khung bị cắt cụt (đáy do bộ
    # giải mã tô); 480p phần lớn thời gian sạch nhưng cổng 1 có đợt 30–36 % khung hỏng (docs/GIAI_DOAN_2_BAN_THU.md
    # mục 2.4). Khung hỏng bị nguồn loại và đếm ("cắt"/"xé"). Mô hình AI vốn thu ảnh về 512×384.
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--fourcc", default="MJPG")
    p.add_argument("--exposure", type=float, default=None)
    p.add_argument("--ring", type=int, default=3)
    p.add_argument("--max-skew-ms", type=float, default=60.0, help="bộ ảnh lệch hơn thế bị bỏ; ≤ 0 để tắt")
    # Cổng 1 ở 480p có đợt 26–36 % khung hỏng (đo 23/09); quy tắc cũ "chờ mọi camera có khung mới" làm AI chậm theo nó.
    # Giá trị này là SÀN: ngưỡng thực = max(sàn, 1,5 × chu kỳ khung TRUNG BÌNH đo được của camera nhanh nhất), để camera
    # khỏe chạy dưới 16,7 fps (--fps 15, phơi sáng tự động chỗ tối) không bị bỏ luân phiên. Sàn 60 ms và hệ số 1,5: lựa
    # chọn thiết kế, kiểm bằng mô phỏng đồng hồ giả và phát lại khoảng cách khung đo được (m04), CHƯA đo trên phần cứng
    # (xem video/multicam.py).
    p.add_argument("--max-wait-ms", type=float, default=60.0,
                   help="sàn của ngưỡng chờ camera chưa có khung mới; ngưỡng thực = max(giá trị này, 1,5 × chu kỳ khung "
                        "trung bình của camera nhanh nhất): ≈ 63 ms ở 24 fps, ≈ 100 ms ở 15 fps; hết hạn thì chấm bộ "
                        "không có camera đó; ≤ 0 để tắt (chờ mọi camera, như loạt 20260923_v3)")
    p.add_argument("--lidar", default=None, help="cổng COM của RPLIDAR C1, ví dụ COM4")
    p.add_argument("--mirror", action="store_true")
    p.add_argument("--no-ai", action="store_true")
    p.add_argument("--checkpoint", default=None, help="mặc định: runs/ai_woodscape_rtx4000_v1/best.pt")
    p.add_argument("--runs", default="runs")
    p.add_argument("--device", default=None, choices=(None, "cuda", "cpu"))
    p.add_argument("--display-width", type=int, default=640, help="bề rộng bản đồ xác suất AI (giữ tỉ lệ từng camera)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_rig_args(p)
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--warmup", type=float, default=5.0, help="giây chạy trước khi bắt đầu tính (LiDAR cần ≈ 2,2 s)")
    p.add_argument("--name", required=True)
    p.add_argument("--note", default="")
    p.add_argument("--out", type=Path, default=Path("runs/rig_bench"))
    p.add_argument("--switch-interval-ms", type=float, default=None,
                   help="sys.setswitchinterval (mặc định Python 5 ms): thử giả thuyết tranh chấp GIL giữa luồng camera và AI")
    args = p.parse_args(argv)
    default_switch = sys.getswitchinterval()
    if args.switch_interval_ms is not None:
        sys.setswitchinterval(args.switch_interval_ms / 1000.0)

    rig = build_rig(args)
    print(f"camera: {[(s.port, s.index) for s in rig.cams.specs]} (cổng, index)  LiDAR: {args.lidar}  AI: {rig.cfg.checkpoint}",
          flush=True)
    summary = None
    try:
        rig.start()
        time.sleep(args.warmup)
        rig.reset_counters()
        t_end = rig.clock() + args.seconds
        while rig.clock() < t_end:
            time.sleep(min(5.0, max(0.1, t_end - rig.clock())))
            print_line(rig.snapshot())
        summary = rig.summary()
    finally:
        alive = rig.stop()
    if summary is None:
        return 1
    summary["stop_alive"] = alive
    summary["python_switch_interval_s"] = sys.getswitchinterval()
    sys.setswitchinterval(default_switch)
    summary.update({"name": args.name, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "warmup_s": args.warmup, "argv": sys.argv[1:], "series": rig.series})
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.name}.rig.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print_summary(summary)
    print("đã ghi", path)
    bad = [c["port"] for c in summary["cameras"] if c["open_error"]]
    lidar_bad = summary["lidar"] is not None and (summary["lidar"]["open_error"] or summary["lidar"]["scans"] == 0)
    ai_bad = summary["ai"] is not None and (summary["ai"]["load_error"] or summary["ai"]["batches"] == 0)
    if alive:
        print("CẢNH BÁO: luồng chưa dừng:", alive)
    return 1 if bad or lidar_bad or ai_bad or alive else 0




def print_summary(s: dict) -> None:
    print(f"\n== {s['name']}: {s['duration_s']} s (đồng hồ {s['clock']['name']}, phân giải {s['clock']['resolution_s']:g} s) ==")
    for c in s["cameras"]:
        print(f"  cổng {c['port']} (index {c['index']}): {c['fps_mean']} fps TB (khung tốt), khung cũ {c['duplicates']}, "
              f"khung bị cắt {c['truncated']}, khung xé giữa ảnh {c['torn']}, đọc hỏng {c['read_failures']}, "
              f"khoảng cách max {c['gap_max_ms']} ms" + (f", LỖI MỞ {c['open_error']}" if c["open_error"] else ""))
    st = s["sets"]
    sk = st["skew_ms"]
    pol = s.get("policy") or {}
    wait = st.get("partial_wait_ms") or {}
    print(f"  bộ ảnh: {st['sets_built']} dùng, {st['sets_rejected_skew']} bỏ vì lệch, {st['sets_partial']} thiếu camera, "
          f"{st['sets_blocked_not_new']} bị chặn vì chưa đủ khung mới; khung không vào bộ nào {st['frames_skipped']}")
    limit = st.get("wait_limit_ms") or {}
    wait_txt = "TẮT (chờ mọi camera)" if pol.get("max_wait_ms") is None else (
        f"tối đa max({pol['max_wait_ms']} ms; {pol.get('wait_periods_of_fastest')} × chu kỳ camera nhanh nhất), "
        f"ngưỡng đã dùng trung vị {limit.get('median')} ms [{limit.get('min')}; {limit.get('max')}]")
    print(f"  chờ camera chậm {wait_txt}: {st.get('sets_partial_wait', 0)} bộ dùng thiếu camera chậm, số bộ theo cổng bị "
          f"bỏ {st.get('lagging_per_port', {})}; khung mới đã chờ trung vị {wait.get('median')} ms, max {wait.get('max')} ms; "
          f"{st.get('sets_regrouped', 0)} bộ để dành camera lệch pha cho bộ sau")
    print(f"  độ lệch bộ ảnh: trung vị {sk['median']} ms, p95 {sk['p95']} ms, max {sk['max']} ms (n {sk['n']})")
    if s["lidar"]:
        l = s["lidar"]
        vs = l["vs_set"]["last_minus_anchor_ms"]
        print(f"  LiDAR: {l['scans']} vòng, {l['hz_mean']} Hz TB, lỗi {l['errors']}, khoảng cách max {l['gap_max_ms']} ms"
              + (f", LỖI MỞ {l['open_error']}" if l["open_error"] else ""))
        print(f"     cuối vòng − mốc bộ ảnh (lúc ghép bộ): trung vị {vs['median']} ms, min {vs['min']}, max {vs['max']} (n {vs['n']})")
    if s["ai"]:
        a = s["ai"]
        print(f"  AI {a['model']} ({a['device']}, amp {a['amp']}): {a['batches']} lô = {a['images']} ảnh, {a['sets_per_s_mean']} bộ/s TB; "
              f"{a.get('batches_partial_wait', 0)} lô thiếu camera chậm; lô đầu {a['first_batch_ms']} ms (khởi tạo, không tính)")
        print(f"     một lô: trung vị {a['total_ms']['median']} ms (tiền xử lý {a['pre_ms']['median']}, mạng {a['model_ms']['median']}, "
              f"hậu xử lý {a['post_ms']['median']}), p95 {a['total_ms']['p95']} ms, max {a['total_ms']['max']} ms; lỗi {a['errors']}")
        print(f"     tuổi kết quả so với khung cũ nhất: trung vị {a['result_age_oldest_frame_ms']['median']} ms, "
              f"p95 {a['result_age_oldest_frame_ms']['p95']} ms; so với khung mới nhất: trung vị {a['result_age_newest_frame_ms']['median']} ms")
    r = s["resources"]
    pick = lambda k, f="mean": (r.get(k) or {}).get(f)
    print(f"  tài nguyên: CPU tiến trình {pick('proc_cpu_cores')} lõi (max {pick('proc_cpu_cores', 'max')}), máy {pick('sys_cpu_pct')} %, "
          f"RAM {pick('proc_rss_mb')} MB, GPU {pick('gpu_util_pct')} %, VRAM {pick('gpu_mem_used_mb')} MB, "
          f"nhiệt GPU {pick('gpu_temp_c', 'first')}→{pick('gpu_temp_c', 'last')} °C (max {pick('gpu_temp_c', 'max')}), {pick('gpu_power_w')} W")

if __name__ == "__main__":
    sys.exit(main())
