"""Phiên đo không giao diện: bốn camera + LiDAR + AI chạy đồng thời trong T giây, ghi số đo ra json.

    python -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 120 --name u01_4cam_lidar_ai_480p --out runs/rig_bench/20260923_v3

`--lidar` không kèm giá trị: LiDAR ở `lidar_port` của configs/thiet_bi.json (29/09/2026; lidar/port.py); `--lidar COMx`
ghi đè; không có `--lidar`: chạy không LiDAR.

Chạy trong `.venv-train` (cần torch cho AI; `--no-ai` thì chạy được cả trong `.venv`). Camera được chọn theo CỔNG HUB
(index OpenCV đổi sau khởi động lại). Kết quả: `<name>.rig.json` gồm cấu hình, số đo từng camera, độ lệch bộ ảnh,
LiDAR, AI (thời gian từng khâu, tuổi kết quả), tài nguyên (CPU, RAM, GPU, nhiệt độ GPU) và chuỗi theo giây. Từ T10
(02/10/2026) `gap_max_ms` của từng camera tính cả khoảng hở còn mở lúc chốt số (`gap_end_ms`: camera ngừng hẳn trước
khi hết phần đo, hay không có khung tốt nào); nghĩa cũ ở `gap_closed_max_ms`; khi `--replay` khoảng hở cuối đo tới cuối
bản ghi. Khoảng đi qua lúc hết phần làm nóng (`reset_counters`) tính đủ cả phần trước đó, nên camera ngừng trong lúc
làm nóng có `gap_max_ms` lớn hơn `--seconds`.

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

Dấu đồng bộ video–log cho video R3 (T14, thêm 02/10/2026; docs/KICH_BAN_NGHIEM_THU.md mục 7):

    python -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name cb1 --out runs/rig_bench/<ngày> --sync-mark

`--sync-mark` nháy một ô trắng lớn có số, phủ cả một màn hình (`--sync-screen N` theo thứ tự Qt, mặc định 0 = màn hình
chính), 0,5 s ở đầu phần đo, ở cuối (bắt đầu `SYNC_END_LEAD_S` trước khi hết `--seconds`, tắt trước khi hết) và mỗi lần nhấn
Enter/Space/m trong cửa sổ lệnh này (chỉ khi cửa sổ lệnh đang được chọn); `--sync-every S` (S ≥ 2, tự bật `--sync-mark`)
thêm một dấu mỗi S giây. Mỗi dấu là một dòng của `<out>/<name>.sync.csv` (`perf_counter`, cùng đồng hồ với mọi stamp của
bàn thử; tệp đã có thì từ chối ngay, không ghi đè; phiên dừng trước dấu đầu thì tệp chỉ có tiêu đề được xóa) và `.rig.json`
có khóa `sync_marks` (`t_start_perf_s`: chuỗi `t_s` cộng giá trị này ra perf_counter). Không dùng với `--replay`. Bật dấu
đồng bộ thì tiến trình đo thêm một cửa sổ Qt và thức mỗi 20 ms: ảnh hưởng lên số đo CHƯA ĐO (so một lượt có và một lượt
không). Chỉ kiểm offscreen; màn hình thật CHƯA THỬ (hiệu ứng hiện/ẩn của Windows, tiêu điểm của cửa sổ lệnh; tắt khóa màn
hình khi chạy dài không người trông).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

from autopark.rig.core import Rig, RigConfig
from autopark.video.multicam import RIG_CLOCK, CameraSpec, MultiCameraManager, resolve_ports

LIVE_SECONDS = 60.0            # --seconds mặc định khi đo thiết bị thật
LIVE_WARMUP_S = 5.0            # --warmup mặc định khi đo thiết bị thật (LiDAR cần ≈ 2,2 s tới vòng đầu)
REPLAY_MARGIN_S = 10.0         # phát lại: hạn cứng = độ dài bản ghi / speed + chừng ấy (phòng nguồn không bao giờ "hết")
REPLAY_END_GRACE_S = 0.3       # phát lại: sau mục cuối, chờ chừng ấy để AI chấm nốt bộ cuối rồi mới chốt số
SYNC_POLL_S = 0.02             # dấu đồng bộ: nhịp vòng đo (đọc phím, tắt ô nháy đúng giờ)
SYNC_END_LEAD_S = 1.0          # dấu đồng bộ: dấu cuối khi phần đo còn chừng ấy giây (ô tắt trước khi hết --seconds)
SYNC_EVERY_MIN_S = 2.0         # --sync-every nhỏ nhất
SYNC_KEYS = ("\r", "\n", " ", "m", "M")    # phím trong cửa sổ lệnh tạo một dấu
SYNC_KEYS_PER_POLL = 32        # đọc tối đa chừng ấy phím mỗi nhịp (giữ phím lặp không làm kẹt vòng đo)


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


# ---------------------------------------------------------------------------- dấu đồng bộ video–log (T14, 02/10/2026)
def check_sync_args(p: argparse.ArgumentParser, args, path: Path) -> bool:
    """Kiểm tham số dấu đồng bộ NGAY khi đọc dòng lệnh, trước khi dựng Rig hay chạm thiết bị nào (sai → mã 2). True khi
    bật dấu đồng bộ (`--sync-mark`, hoặc `--sync-every` tự bật)."""
    wanted = args.sync_mark or args.sync_every is not None
    if args.sync_screen is not None and not wanted:
        p.error("--sync-screen chỉ dùng cùng --sync-mark hoặc --sync-every")
    if not wanted:
        return False
    if args.replay is not None:
        p.error("--sync-mark/--sync-every chỉ dùng khi đo thiết bị thật, không dùng với --replay (không có video R3 nào "
                "để đồng bộ với bản ghi)")
    if args.sync_every is not None and not (math.isfinite(args.sync_every) and args.sync_every >= SYNC_EVERY_MIN_S):
        p.error(f"--sync-every phải là số giây hữu hạn ≥ {SYNC_EVERY_MIN_S:g} (đang là {args.sync_every:g})")
    if args.sync_screen is not None and args.sync_screen < 0:
        p.error(f"--sync-screen phải ≥ 0 (đang là {args.sync_screen})")
    if path.exists():
        p.error(f"{path} đã có: không ghi đè dấu đồng bộ của phiên khác — đổi --name hoặc --out")
    return True


def console_key() -> str | None:
    """Một phím đã nhấn trong cửa sổ lệnh, không chờ; None khi chưa có phím. Phím mở rộng (mũi tên, F1…: "\\x00" hay
    "\\xe0" rồi một mã) bị đọc và bỏ. Không có msvcrt (ngoài Windows) hay không có cửa sổ lệnh: None. Hàm cấp mô-đun để
    test thay được."""
    try:
        import msvcrt

        if not msvcrt.kbhit():
            return None
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            msvcrt.getwch()                      # mã của phím mở rộng: bỏ
            return None
        return key
    except (ImportError, OSError):
        return None


class BenchSync:
    """Dấu đồng bộ của một phiên `rig.bench`: dấu đầu (`begin`), dấu theo phím và theo chu kỳ (`poll` mỗi nhịp vòng đo),
    dấu cuối kịp tắt trước khi hết phần đo, rồi `finish`/`close`. Dòng ghi `t_rig_s` = t_perf − `Rig.t_start`."""

    def __init__(self, app, marker, *, every_s: float | None, note: str, screen_info: dict):
        self.app, self.marker = app, marker
        self.every_s, self.note, self.screen_info = every_s, note, screen_info
        self.rig = None
        self.next_periodic: float | None = None
        self.end_done = False
        self.closed = False

    @property
    def log(self):
        return self.marker.log

    @property
    def flash(self):
        return self.marker.flash

    def _context(self, t_perf: float) -> dict:
        t_start = None if self.rig is None else self.rig.t_start
        return {"t_rig_s": None if t_start is None else round(t_perf - t_start, 4), "note": self.note}

    def _mark(self, trigger: str) -> dict | None:
        row = self.marker.mark(trigger, self._context)
        if row is None:
            print(f"  (chưa tạo dấu đồng bộ {trigger}: ô trước còn sáng hoặc chưa đủ {self.marker.min_gap_s:g} s)",
                  flush=True)
        else:
            print(f"  DẤU ĐỒNG BỘ #{row['n']} ({trigger}) t={row['t_rig_s']} s, perf_counter {row['t_perf']:.6f} s",
                  flush=True)
        self.app.processEvents()
        return row

    def _keys(self) -> list[str]:
        keys = []
        for _ in range(SYNC_KEYS_PER_POLL):
            key = console_key()
            if key is None:
                break
            keys.append(key)
        return keys

    def begin(self, rig) -> None:
        """Đầu phần đo (sau `reset_counters`): bỏ các phím đã nhấn trong lúc làm nóng, tạo dấu đầu."""
        self.rig = rig
        self._keys()
        self._mark("auto_start")
        if self.every_s is not None:
            self.next_periodic = rig.clock() + self.every_s

    def poll(self, now: float, t_end: float) -> None:
        """Một nhịp vòng đo: xử lý sự kiện Qt (ô tắt đúng giờ, cửa sổ không "đứng"), dấu theo phím và theo chu kỳ, rồi dấu
        cuối khi phần đo còn `SYNC_END_LEAD_S`. Phím và chu kỳ không tạo dấu khi đã quá gần dấu cuối (sau
        t_end − SYNC_END_LEAD_S − khoảng cách tối thiểu), để dấu cuối luôn kịp tắt trước khi hết phần đo."""
        self.app.processEvents()
        open_window = now <= t_end - SYNC_END_LEAD_S - self.marker.min_gap_s
        for key in self._keys():
            if key not in SYNC_KEYS:
                continue
            if open_window:
                self._mark("console_key")
            else:
                print("  (bỏ qua phím: sắp tới dấu đồng bộ cuối)", flush=True)
        if self.next_periodic is not None and now >= self.next_periodic:
            if open_window:
                self._mark("periodic")
            while self.next_periodic <= now:
                self.next_periodic += self.every_s
        if not self.end_done and now >= t_end - SYNC_END_LEAD_S and self.marker.ready():
            self.end_done = self._mark("auto_end") is not None

    def _pump(self) -> None:
        self.app.processEvents()
        time.sleep(SYNC_POLL_S / 4)

    def finish(self, timeout_s: float = 3.0) -> None:
        """Sau vòng đo, trước khi dừng ghi: phiên quá ngắn chưa có dấu cuối thì chờ được phép rồi tạo; rồi chờ ô tắt hẳn
        (tất cả tối đa `timeout_s`)."""
        deadline = time.perf_counter() + timeout_s
        if not self.end_done:
            while not self.marker.ready() and time.perf_counter() < deadline:
                self._pump()
            if self.marker.ready():
                self.end_done = self._mark("auto_end") is not None
        while self.flash.lit() and time.perf_counter() < deadline:
            self._pump()
        self.flash.finish()

    def close(self) -> None:
        """Tắt ô nháy. Phiên dừng trước dấu đầu (Ctrl+C lúc làm nóng, lỗi ở rig.start…) để lại tệp chỉ có dòng tiêu đề:
        xóa nó (không có dấu nào để giữ), để chạy lại đúng lệnh đó không bị `check_sync_args` từ chối (02/10/2026)."""
        self.flash.finish()
        self.flash.close()
        self.app.processEvents()
        self.closed = True
        log = self.log
        if not log.rows and log.path is not None:
            try:
                log.path.unlink(missing_ok=True)
            except OSError as exc:
                print(f"  (không xóa được tệp dấu đồng bộ rỗng {log.path}: {exc})", flush=True)
            else:
                log.path = None

    def summary(self) -> dict:
        """Khóa `sync_marks` của `.rig.json`."""
        log = self.log
        return {"file": None if log.path is None else str(log.path), "marks": log.marks, "clock": "perf_counter",
                "flash_ms": self.marker.flash_ms, "min_gap_s": self.marker.min_gap_s, "every_s": self.every_s,
                "screen": self.screen_info, "t_start_perf_s": None if self.rig is None else self.rig.t_start,
                "write_error": log.error, "rows": [dict(row) for row in log.rows]}


def open_bench_sync(args, path: Path) -> BenchSync:
    """Bật dấu đồng bộ: ô nháy toàn màn hình `--sync-screen` và tệp `path` (tạo ngay, có tiêu đề). Gọi SAU `build_rig`
    (khi bật AI, torch đã được nhập trước Qt: thứ tự DLL trên Windows, xem ui/rig_app.py) và TRƯỚC `rig.start()`. Lỗi:
    ImportError (thiếu PySide6), ValueError (không có màn hình đó), OSError (không tạo được tệp)."""
    from PySide6.QtWidgets import QApplication

    from autopark.evaluation.sync_marks import SyncMarkLog
    from autopark.ui.sync_flash import SyncFlash, SyncMarker

    app = QApplication.instance() or QApplication([])
    screens = app.screens()
    index = args.sync_screen or 0
    if not 0 <= index < len(screens):
        raise ValueError(f"--sync-screen {index}: máy có {len(screens)} màn hình (0…{len(screens) - 1})")
    screen = screens[index]
    flash = SyncFlash(None, screen)
    try:
        log = SyncMarkLog("rig.bench", path)
    except OSError:
        flash.close()
        raise
    geo = screen.geometry()
    info = {"index": index, "name": screen.name(), "geometry": [geo.x(), geo.y(), geo.width(), geo.height()],
            "transitions_off": flash.transitions_off}
    note = f"phiên {args.name}" + (f", ghi {args.record}" if args.record is not None else "")
    print(f"dấu đồng bộ: nháy trên màn hình {screen.name() or index} {geo.width()}×{geo.height()}, ghi {path}; "
          "Enter/Space/m trong cửa sổ này = một dấu", flush=True)
    return BenchSync(app, SyncMarker(log, flash), every_s=args.sync_every, note=note, screen_info=info)


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
    p.add_argument("--sync-mark", action="store_true",
                   help="dấu đồng bộ video–log (T14, cho video R3): nháy ô trắng lớn toàn màn hình 0,5 s ở đầu và cuối "
                        "phần đo và mỗi lần nhấn Enter/Space/m trong cửa sổ lệnh này; ghi <out>/<name>.sync.csv "
                        "(perf_counter, cùng đồng hồ với stamp bàn thử)")
    p.add_argument("--sync-every", type=float, default=None, metavar="S",
                   help=f"thêm một dấu mỗi S giây trong phần đo (S ≥ {SYNC_EVERY_MIN_S:g}; tự bật --sync-mark)")
    p.add_argument("--sync-screen", type=int, default=None, metavar="N",
                   help="màn hình để nháy theo thứ tự Qt, 0 = màn hình chính")
    args = p.parse_args(argv)
    if args.replay is not None and args.record is not None and args.replay.resolve() == args.record.resolve():
        p.error("--record không được trùng thư mục --replay")
    if args.record is not None:
        check_record_args(p, args, args.record)
    sync_file = args.out / f"{args.name}.sync.csv"
    sync_wanted = check_sync_args(p, args, sync_file)
    default_switch = sys.getswitchinterval()
    if args.switch_interval_ms is not None:
        sys.setswitchinterval(args.switch_interval_ms / 1000.0)

    try:
        rig = build_rig(args)
    except ValueError as exc:      # cổng LiDAR (LidarPortError), cổng hub không tra được (resolve_ports), --replay sai…
        p.error(str(exc))          # mã 2, không traceback (02/10/2026)
    sync = None
    if sync_wanted:
        try:
            sync = open_bench_sync(args, sync_file)      # sau build_rig (torch trước Qt), trước rig.start()
        except (ImportError, OSError, ValueError) as exc:
            p.error(f"không bật được dấu đồng bộ: {exc}")
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
        if sync is not None:
            sync.begin(rig)                             # dấu đầu, trước khi tính t_end
        t_end = rig.clock() + seconds
        next_line = rig.clock() + 5.0
        while (now := rig.clock()) < t_end:
            if replay is not None and replay.finished:
                time.sleep(REPLAY_END_GRACE_S)          # AI chấm nốt bộ cuối
                break
            step = min(0.1 if replay is not None else 5.0, t_end - now, next_line - now)
            time.sleep(max(0.0, step if sync is None else min(step, SYNC_POLL_S)))
            if sync is not None:
                sync.poll(rig.clock(), t_end)
            if rig.clock() >= next_line:
                print_line(rig.snapshot())
                next_line += 5.0
        if sync is not None:
            sync.finish()                               # phiên quá ngắn: dấu cuối ở đây, vẫn trước khi dừng ghi
        rig.stop_recording(wait=False)                  # ngừng nhận ngay; bộ ghi ghi nốt trong rig.stop()
        print_line(rig.snapshot())
        summary = rig.summary()
    finally:
        try:
            if sync is not None:
                sync.close()
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
    if sync is not None:
        summary["sync_marks"] = sync.summary()
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
    sync_bad = sync is not None and (sync.log.error is not None or sync.log.marks == 0)
    if alive:
        print("CẢNH BÁO: luồng chưa dừng:", alive)
    if sync_bad:
        log = sync.log
        # unwritten: số dòng tệp sống còn thiếu lúc kết thúc (SyncMarkLog ghi lại cả tệp ở lần ghi được sau lỗi)
        print("CẢNH BÁO: dấu đồng bộ không trọn: " + ("không tạo được dấu nào" if log.marks == 0 else f"{log.marks} dấu")
              + ("" if log.error is None else f"; LỖI GHI {log.error}: "
                 + (f"{log.unwritten} dòng chưa có trong {sync_file}" if log.unwritten else
                    f"{sync_file} đã được ghi lại đủ sau lỗi") + f", đủ mọi dòng ở khóa sync_marks của {path}"))
    if rec_bad:
        print(f"CẢNH BÁO: bản ghi {rec['folder']} không trọn: trạng thái {rec['state']}, bỏ {rec['dropped_total']} khung, "
              f"lỗi {rec['error']}")
    if replay_stuck:
        print(f"CẢNH BÁO: phát lại chạy tới hạn cứng ({seconds:.1f} s) mà chưa hết bản ghi — nguồn phát lại kẹt? "
              f"xem replay.cameras / read_failures trong {path}")
    return 1 if bad or lidar_bad or ai_bad or alive or rec_bad or replay_stuck or sync_bad else 0


def print_summary(s: dict) -> None:
    print(f"\n== {s['name']}: {s['duration_s']} s (đồng hồ {s['clock']['name']}, phân giải {s['clock']['resolution_s']:g} s) ==")
    for c in s["cameras"]:
        print(f"  cổng {c['port']} (index {c['index']}): {c['fps_mean']} fps TB (khung tốt), khung cũ {c['duplicates']}, "
              f"khung bị cắt {c['truncated']}, khung xé giữa ảnh {c['torn']}, đọc hỏng {c['read_failures']}, "
              f"khoảng cách max {c['gap_max_ms']} ms (hở cuối phiên {c.get('gap_end_ms')} ms)"
              + (f", LỖI MỞ {c['open_error']}" if c["open_error"] else ""))
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
    sm = s.get("sync_marks")
    if sm:
        print(f"  dấu đồng bộ: {sm['marks']} dấu → {sm['file']}"
              + (f", LỖI GHI: {sm['write_error']}" if sm["write_error"] else ""))

if __name__ == "__main__":
    sys.exit(main())
