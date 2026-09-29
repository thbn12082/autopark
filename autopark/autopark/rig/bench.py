"""Phiên đo không giao diện: bốn camera + LiDAR + AI chạy đồng thời trong T giây, ghi số đo ra json.

    python -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 120 --name u01_4cam_lidar_ai_480p --out runs/rig_bench/20260923_v3

`--lidar` không kèm giá trị: LiDAR ở `lidar_port` của configs/thiet_bi.json (29/09/2026; lidar/port.py); `--lidar COMx`
ghi đè; không có `--lidar`: chạy không LiDAR.

Chạy trong `.venv-train` (cần torch cho AI; `--no-ai` thì chạy được cả trong `.venv`). Camera được chọn theo CỔNG HUB
(index OpenCV đổi sau khởi động lại). Kết quả: `<name>.rig.json` gồm cấu hình, số đo từng camera, độ lệch bộ ảnh,
LiDAR, AI (thời gian từng khâu, tuổi kết quả), tài nguyên (CPU, RAM, GPU, nhiệt độ GPU) và chuỗi theo giây.

`--max-wait-ms` (mặc định 60; ≤ 0 = quy tắc cũ, chờ mọi camera) là SÀN của ngưỡng chờ camera lỡ nhịp; từ tối 24/09
mỗi camera có ngưỡng RIÊNG = max(sàn, 1,5 × chu kỳ khung TRUNG BÌNH đo được của CHÍNH camera đó) — ≈ 63 ms ở 24 fps
(nhịp xen kẽ 31/48 ms, trung bình 41,9 ms), ≈ 100 ms ở 15 fps — rồi AI chấm bộ không có camera đó. Camera khỏe mà chậm
hơn thì định nhịp cả chuỗi, không bị bỏ. Số bộ như thế và số lần từng cổng bị bỏ được ghi ("chậm" trên dòng trực tiếp,
`sets_partial_wait`, `lagging_per_port` trong json), cùng ngưỡng lớn nhất trong bộ (`wait_limit_ms`), nhịp từng camera
(`period_ms`) và số bộ phải để dành camera lệch pha cho bộ sau (`sets_regrouped`). Muốn so với số đo cũ (loạt
20260923_v3, trước khi có quy tắc chờ) thì chạy `--max-wait-ms 0`. Số của các phiên bật chờ ghi TRƯỚC tối 24/09 (w01–w05,
may_moi m01/m02; json không có `policy.wait_rule`) là của quy tắc cũ: một ngưỡng chung theo camera NHANH NHẤT, bỏ nhầm
camera khỏe khi các camera khác nhịp (docs/GIAI_DOAN_2_BAN_THU.md mục 10.1).

Ghi và phát lại (docs/GHI_PHAT_LAI_BAN_THU.md):

    python -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 120 --name g01 --record runs/rig_recordings/g01
    python -m autopark.rig.bench --replay runs/rig_recordings/g01 --name g01_phat_lai --out runs/rig_bench/phat_lai

`--record <thư mục>` ghi mọi khung tốt (JPEG q95, hoặc `--record-format png`), sự kiện khung hỏng và vòng LiDAR của đúng
cửa sổ đo (sau phần làm nóng). `--replay <thư mục>` chạy cả bàn thử (bộ ảnh, chờ camera chậm, AI, LiDAR so với bộ ảnh) từ
bản ghi thay cho camera và LiDAR — không mở thiết bị nào. Khi phát lại: đồng hồ phát lại bắt đầu sau khi AI nạp xong mô
hình, phần làm nóng mặc định 0 s, phiên đo phủ trọn bản ghi và tự dừng khi hết (`replay.finished` trong json); quy tắc ghép
bộ (`--max-skew-ms`, `--max-wait-ms`) lấy từ dòng lệnh, nên cùng một bản ghi so được các quy tắc với nhau.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

from autopark.lidar.port import LidarPortError
from autopark.rig.core import Rig, RigConfig
from autopark.video.multicam import RIG_CLOCK, CameraSpec, MultiCameraManager, resolve_ports

LIVE_SECONDS = 60.0            # --seconds mặc định khi đo thiết bị thật
LIVE_WARMUP_S = 5.0            # --warmup mặc định khi đo thiết bị thật (LiDAR cần ≈ 2,2 s tới vòng đầu)
REPLAY_MARGIN_S = 10.0         # phát lại: hạn cứng = độ dài bản ghi / speed + chừng ấy (phòng nguồn không bao giờ "hết")
REPLAY_END_GRACE_S = 0.3       # phát lại: sau mục cuối, chờ chừng ấy để AI chấm nốt bộ cuối rồi mới chốt số


def segmenter_factory(args):
    """(hàm tạo bộ phân đoạn, checkpoint) hoặc (None, None) khi --no-ai. Tách riêng để test thay bằng bộ giả."""
    if args.no_ai:
        return None, None
    from autopark.perception.live import LiveSegmenter, list_checkpoints
    checkpoint = str(args.checkpoint or list_checkpoints(args.runs)[0])

    def make_segmenter(path: str):
        return LiveSegmenter(path, device=args.device)
    return make_segmenter, checkpoint


def build_rig(args) -> Rig:
    clock = RIG_CLOCK                    # MỘT đồng hồ cho camera, LiDAR và rig (LiDAR cộng t0 của driver vào stamp)
    replay = None
    notes = {"name": getattr(args, "name", None), "note": getattr(args, "note", "")}
    if getattr(args, "replay", None):
        from autopark.rig.replay import ReplaySession
        if args.index is not None or args.lidar is not None:
            raise ValueError("--replay chạy từ bản ghi: không dùng cùng --index hay --lidar (--ports thì chọn cổng trong bản ghi)")
        replay = ReplaySession(args.replay, speed=args.replay_speed, ports=args.ports, clock=clock)
        mode = replay.camera_mode()
        width, height = int(mode.get("width") or args.width), int(mode.get("height") or args.height)
        fps, fourcc, exposure = mode.get("fps") or args.fps, mode.get("fourcc") or args.fourcc, mode.get("exposure")
        cams = MultiCameraManager(replay.camera_specs(), width=width, height=height, fps=fps, fourcc=fourcc,
                                  exposure=exposure, ring=args.ring, clock=clock, open_source=replay.open_camera)
        open_lidar = replay.open_lidar if replay.has_lidar else None
        lidar_port = ((replay.meta.get("lidar_source") or {}).get("port")) if replay.has_lidar else None
        notes.update({"replay": str(args.replay), "replay_speed": replay.speed})
    else:
        open_lidar = None
        lidar_port = None
        if args.lidar is not None:           # "" = "--lidar" không kèm giá trị → configs/thiet_bi.json
            from autopark.lidar.port import lidar_port as resolve_lidar_port
            from autopark.lidar.rplidar_c1 import RplidarC1Source

            # TRƯỚC khi tra/dựng camera: tệp cấu hình hỏng thì báo ngay, chưa chạm thiết bị nào
            lidar_port = resolve_lidar_port(args.lidar)     # LidarPortError (ValueError) nếu không xác định được

            def open_lidar():
                return RplidarC1Source.open(lidar_port, mirror=args.mirror, clock=clock, first_revolution_timeout_s=4.0)
        specs = resolve_ports(args.ports) if args.index is None else \
            [CameraSpec(port=p, index=i) for p, i in zip(args.ports or range(len(args.index)), args.index)]
        width, height, fps, fourcc, exposure = args.width, args.height, args.fps, args.fourcc, args.exposure
        cams = MultiCameraManager(specs, width=width, height=height, fps=fps, fourcc=fourcc,
                                  exposure=exposure, ring=args.ring, clock=clock)
    make_segmenter, checkpoint = segmenter_factory(args)
    cfg = RigConfig(width=width, height=height, fps=fps, fourcc=fourcc, exposure=exposure,
                    max_skew_s=None if args.max_skew_ms <= 0 else args.max_skew_ms / 1000.0,
                    max_wait_s=None if args.max_wait_ms <= 0 else args.max_wait_ms / 1000.0,
                    display_width=args.display_width, ai=not args.no_ai, checkpoint=checkpoint,
                    lidar_port=lidar_port, notes=notes)
    return Rig(cams, cfg, make_segmenter=make_segmenter, open_lidar=open_lidar, clock=clock, replay=replay)


def recording_options(args) -> dict:
    return {"image_format": args.record_format, "jpeg_quality": args.jpeg_quality}


def check_record_args(p: argparse.ArgumentParser, args, folder: Path | None = None) -> None:
    """Kiểm tham số ghi NGAY khi đọc dòng lệnh, trước khi mở camera, quay LiDAR, nạp AI và làm nóng — không để lỗi
    hiện ra sau vài chục giây khởi động. `RigRecorder` vẫn kiểm lại lúc bắt đầu ghi (giao diện, test gọi thẳng)."""
    if not 1 <= args.jpeg_quality <= 100:            # RigRecorder kiểm cả khi ghi PNG
        p.error(f"--jpeg-quality phải trong 1..100 (đang là {args.jpeg_quality})")
    if folder is not None and folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        p.error(f"--record: {folder} đã có dữ liệu (hoặc không phải thư mục); không ghi đè — chọn thư mục mới")


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
    rec = snap.get("recording")
    if rec:
        parts.append(f"ghi {rec['state']} {rec['frames_total']} khung, bỏ {rec['dropped_total']}, chờ ghi {rec['pending_frames']}"
                     + (f" LỖI GHI: {rec['error']}" if rec["error"] else ""))
    rp = snap.get("replay")
    if rp:
        parts.append(f"phát lại {rp['position_s']}/{rp['duration_s']} s" + (" HẾT BẢN GHI" if rp["finished"] else ""))
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
    # Giá trị này là SÀN: ngưỡng thực RIÊNG từng camera = max(sàn, 1,5 × chu kỳ khung TRUNG BÌNH đo được của CHÍNH camera
    # đó), để camera khỏe chạy dưới 16,7 fps (--fps 15, phơi sáng tự động chỗ tối) hay chậm hơn camera khác không bị bỏ.
    # Sàn 60 ms và hệ số 1,5: lựa chọn thiết kế, kiểm bằng mô phỏng đồng hồ giả và phát lại khoảng cách khung đo được
    # (xem video/multicam.py, docs/GIAI_DOAN_2_BAN_THU.md mục 10.1–10.2).
    p.add_argument("--max-wait-ms", type=float, default=60.0,
                   help="sàn của ngưỡng chờ camera lỡ nhịp; ngưỡng thực riêng từng camera = max(giá trị này, 1,5 × chu "
                        "kỳ khung trung bình của chính camera đó): ≈ 63 ms ở 24 fps, ≈ 100 ms ở 15 fps; hết hạn thì "
                        "chấm bộ không có camera đó; ≤ 0 để tắt (chờ mọi camera, như loạt 20260923_v3)")
    p.add_argument("--lidar", nargs="?", const="", default=None, metavar="COMx",
                   help="dùng RPLIDAR C1; không kèm giá trị thì cổng lấy từ lidar_port của configs/thiet_bi.json, kèm "
                        "COMx (hoặc auto) thì ghi đè; không có --lidar: không LiDAR")
    p.add_argument("--mirror", action="store_true")
    p.add_argument("--no-ai", action="store_true")
    p.add_argument("--checkpoint", default=None, help="mặc định: runs/ai_woodscape_rtx4000_v1/best.pt")
    p.add_argument("--runs", default="runs")
    p.add_argument("--device", default=None, choices=(None, "cuda", "cpu"))
    p.add_argument("--display-width", type=int, default=640, help="bề rộng bản đồ xác suất AI (giữ tỉ lệ từng camera)")
    p.add_argument("--replay", type=Path, default=None,
                   help="chạy từ một phiên đã ghi (thư mục của --record hay nút 'Ghi phiên') thay cho camera và LiDAR thật")
    p.add_argument("--replay-speed", type=float, default=1.0,
                   help="tốc độ phát lại (2 = nhanh gấp đôi; khoảng cách stamp chia theo, ngưỡng tuyệt đối thì không)")
    p.add_argument("--record-format", choices=("jpg", "png"), default="jpg",
                   help="ảnh khi ghi phiên: jpg (mặc định, ≈ 160 KB/khung 480p ở q95) hay png (không mất mát, ≈ 700 KB)")
    p.add_argument("--jpeg-quality", type=int, default=95, help="chất lượng JPEG khi ghi phiên")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_rig_args(p)
    p.add_argument("--seconds", type=float, default=None,
                   help=f"độ dài phần đo (mặc định {LIVE_SECONDS:g} s; khi --replay: tới hết bản ghi)")
    p.add_argument("--warmup", type=float, default=None,
                   help=f"giây chạy trước khi bắt đầu tính (mặc định {LIVE_WARMUP_S:g} s, LiDAR cần ≈ 2,2 s; khi --replay: 0)")
    p.add_argument("--name", required=True)
    p.add_argument("--note", default="")
    p.add_argument("--out", type=Path, default=Path("runs/rig_bench"))
    p.add_argument("--record", type=Path, default=None,
                   help="ghi phiên (mọi khung tốt, sự kiện khung hỏng, vòng LiDAR của phần đo) vào thư mục này (phải chưa có "
                        "hoặc rỗng; kiểm ngay khi đọc dòng lệnh, trước khi mở thiết bị)")
    p.add_argument("--switch-interval-ms", type=float, default=None,
                   help="sys.setswitchinterval (mặc định Python 5 ms): thử giả thuyết tranh chấp GIL giữa luồng camera và AI")
    args = p.parse_args(argv)
    if args.replay is not None and args.record is not None and args.replay.resolve() == args.record.resolve():
        p.error("--record không được trùng thư mục --replay")
    if args.record is not None:
        check_record_args(p, args, args.record)
    default_switch = sys.getswitchinterval()
    if args.switch_interval_ms is not None:
        sys.setswitchinterval(args.switch_interval_ms / 1000.0)

    try:
        rig = build_rig(args)
    except LidarPortError as exc:
        p.error(str(exc))
    replay = rig.replay
    warmup = args.warmup if args.warmup is not None else (0.0 if replay is not None else LIVE_WARMUP_S)
    if args.seconds is not None:
        seconds = args.seconds
    elif replay is not None:
        seconds = replay.duration_s / replay.speed + REPLAY_MARGIN_S
    else:
        seconds = LIVE_SECONDS
    print(f"camera: {[(s.port, s.index) for s in rig.cams.specs]} (cổng, index)  LiDAR: {rig.cfg.lidar_port}  "
          f"AI: {rig.cfg.checkpoint}", flush=True)
    if replay is not None:
        print(f"PHÁT LẠI {replay.folder} ×{replay.speed:g}: {len(replay.ports)} camera, LiDAR {'có' if replay.has_lidar else 'không'}, "
              f"dài {replay.duration_s:.1f} s (trạng thái lúc ghi: {replay.meta.get('status')})", flush=True)
    summary = None
    try:
        rig.start(begin_replay=False)
        # Từ 24/09: chờ AI nạp mô hình VÀ làm nóng mọi cỡ lô (≈ 7 s trên máy bàn) trước phần làm nóng, cả khi đo thiết bị
        # thật, để cửa sổ đo không có đoạn AI chưa chạy (xem AIWorker.warm_up).
        if rig.ai is not None and not rig.wait_model():
            print("CẢNH BÁO: AI chưa nạp xong mô hình" + (", vẫn bắt đầu phát lại" if replay is not None else ", vẫn đo"),
                  flush=True)
        time.sleep(warmup)
        rig.reset_counters()
        if args.record is not None:
            rig.start_recording(args.record, notes={"name": args.name, "note": args.note, "argv": sys.argv[1:]},
                                **recording_options(args))
            print(f"đang ghi phiên vào {args.record}", flush=True)
        if replay is not None:
            replay.begin()
        t_end = rig.clock() + seconds
        next_line = rig.clock() + 5.0
        while (now := rig.clock()) < t_end:
            if replay is not None and replay.finished:
                time.sleep(REPLAY_END_GRACE_S)          # AI chấm nốt bộ cuối
                break
            time.sleep(max(0.0, min(0.1 if replay is not None else 5.0, t_end - now, next_line - now)))
            if rig.clock() >= next_line:
                print_line(rig.snapshot())
                next_line += 5.0
        rig.stop_recording(wait=False)                  # ngừng nhận ngay; bộ ghi ghi nốt trong rig.stop()
        print_line(rig.snapshot())
        summary = rig.summary()
    finally:
        alive = rig.stop()
    if summary is None:
        return 1
    summary["recording"] = rig.recording_status()      # trạng thái cuối (đã ghi nốt hàng đợi, meta.json cuối)
    summary["replay"] = rig.replay_status()
    summary["stop_alive"] = alive
    summary["python_switch_interval_s"] = sys.getswitchinterval()
    sys.setswitchinterval(default_switch)
    summary.update({"name": args.name, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "warmup_s": warmup, "argv": sys.argv[1:] if argv is None else list(argv), "series": rig.series})
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.name}.rig.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print_summary(summary)
    print("đã ghi", path)
    bad = [c["port"] for c in summary["cameras"] if c["open_error"]]
    lidar_bad = summary["lidar"] is not None and (summary["lidar"]["open_error"] or summary["lidar"]["scans"] == 0)
    ai_bad = summary["ai"] is not None and (summary["ai"]["load_error"] or summary["ai"]["batches"] == 0)
    rec = summary["recording"]
    rec_bad = rec is not None and (rec["error"] is not None or rec["dropped_total"] > 0 or rec["state"] != "xong")
    # phát lại không --seconds phải chạy tới hết bản ghi; tới hạn cứng mà chưa hết = có nguồn kẹt (--seconds ngắn hơn
    # bản ghi thì dừng sớm là đúng ý, không tính)
    replay_stuck = replay is not None and args.seconds is None and not (summary["replay"] or {}).get("finished")
    if alive:
        print("CẢNH BÁO: luồng chưa dừng:", alive)
    if rec_bad:
        print(f"CẢNH BÁO: bản ghi {rec['folder']} không trọn: trạng thái {rec['state']}, bỏ {rec['dropped_total']} khung, "
              f"lỗi {rec['error']}")
    if replay_stuck:
        print(f"CẢNH BÁO: phát lại chạy tới hạn cứng ({seconds:.1f} s) mà chưa hết bản ghi — nguồn phát lại kẹt? "
              f"xem replay.cameras / read_failures trong {path}")
    return 1 if bad or lidar_bad or ai_bad or alive or rec_bad or replay_stuck else 0


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
        f"tối đa max({pol['max_wait_ms']} ms; {pol.get('wait_periods_of_own')} × chu kỳ của CHÍNH từng camera), "
        f"ngưỡng lớn nhất trong bộ trung vị {limit.get('median')} ms [{limit.get('min')}; {limit.get('max')}]")
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
              f"{a.get('batches_partial_wait', 0)} lô thiếu camera chậm; lô đầu {a['first_batch_ms']} ms (khởi tạo, không tính)"
              + (f"; làm nóng theo cỡ lô {a['warm_up_ms']} ms" if a.get('warm_up_ms') else ""))
        print(f"     một lô: trung vị {a['total_ms']['median']} ms (tiền xử lý {a['pre_ms']['median']}, mạng {a['model_ms']['median']}, "
              f"hậu xử lý {a['post_ms']['median']}), p95 {a['total_ms']['p95']} ms, max {a['total_ms']['max']} ms; lỗi {a['errors']}")
        print(f"     tuổi kết quả so với khung cũ nhất: trung vị {a['result_age_oldest_frame_ms']['median']} ms, "
              f"p95 {a['result_age_oldest_frame_ms']['p95']} ms; so với khung mới nhất: trung vị {a['result_age_newest_frame_ms']['median']} ms")
    r = s["resources"]
    pick = lambda k, f="mean": (r.get(k) or {}).get(f)
    print(f"  tài nguyên: CPU tiến trình {pick('proc_cpu_cores')} lõi (max {pick('proc_cpu_cores', 'max')}), máy {pick('sys_cpu_pct')} %, "
          f"RAM {pick('proc_rss_mb')} MB, GPU {pick('gpu_util_pct')} %, VRAM {pick('gpu_mem_used_mb')} MB, "
          f"nhiệt GPU {pick('gpu_temp_c', 'first')}→{pick('gpu_temp_c', 'last')} °C (max {pick('gpu_temp_c', 'max')}), {pick('gpu_power_w')} W")
    rec = s.get("recording")
    if rec:
        print(f"  ghi phiên → {rec['folder']}: {rec['state']}, {rec['frames_total']} khung {rec['image_format']} "
              f"{rec['frames']}, bỏ {rec['dropped_total']}, LiDAR {rec['lidar_scans']} vòng, {rec['mb_written']} MB "
              f"({rec['mb_per_s']} MB/s)" + (f", LỖI: {rec['error']}" if rec["error"] else ""))
    rp = s.get("replay")
    if rp:
        late = [c["late_ms"]["median"] for c in rp["cameras"].values() if c["late_ms"]["median"] is not None]
        print(f"  phát lại {rp['folder']} ×{rp['speed']:g}: {'hết bản ghi' if rp['finished'] else 'CHƯA hết bản ghi'} "
              f"({rp['position_s']}/{rp['duration_s']} s); khung ra muộn so với lịch, trung vị theo camera {late} ms; "
              f"khung thiếu trong bản ghi {rp['missing_in_recording']}")

if __name__ == "__main__":
    sys.exit(main())
