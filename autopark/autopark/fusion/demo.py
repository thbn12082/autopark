"""Thử nghiệm bàn: LiDAR thật (hoặc bản ghi) → lớp LiveLidar → bản đồ hợp nhất → phiên đỗ mô phỏng giai đoạn 0.

    python -m autopark.fusion.demo --seconds 30
    python -m autopark.fusion.demo --recording runs/lidar_bench/20260922/p07_nen_phong.npz --seconds 10
    python -m autopark.fusion.demo --seconds 30 --warmup 4.5

Không có `--recording` thì mở LiDAR thật ở `--port`, hoặc (không có `--port`) ở `lidar_port` của configs/thiet_bi.json
(29/09/2026; autopark/lidar/port.py).

Xe ảo đứng ở xuất phát của sa bàn 3 × 2 m, hướng +x; LiDAR thật ĐỨNG YÊN tại đúng vị trí xuất phát đó, cùng hướng
xe, và quan sát sa bàn như một cảm biến cố định: vật thật cách LiDAR 1 m phía trước là vật cách xuất phát 1 m.
(Gán LiDAR vào xe ảo đang chạy là sai, vì LiDAR không chuyển động theo xe: đo ngày 22/09, cả cảnh bị dịch theo xe
và mọi mép vật trở thành "vật mới" ngay sau khi xuất phát.) Trình tự: (1) bỏ các vòng lúc mô-tơ C1 còn tăng tốc
(mật độ tia đổi từng vòng; quy tắc ở đoạn "Bỏ vòng khởi động" dưới), rồi `initial_scans` vòng được đồng bộ vào sa bàn
thành vật cản có sẵn; (2) lập đường thẳng tới đích, nếu đồ vật quanh bàn đã chặn thì báo và thôi; xả bộ đệm
LiDAR sau khi lập đường để vòng quét tiếp theo là dữ liệu hiện tại chứ không phải tồn đọng; (3) chạy; mỗi vòng
quét mới chỉ đưa THÔNG TIN MỚI vào (ô bị chạm ở 2 trong 3 vòng gần nhất, cách vật đã biết hơn một ô), nên đưa tay
hoặc hộp vào trước LiDAR lúc xe đang chạy sẽ phát MAP_CHANGED → phanh → dừng → chờ lập lại đường; mất LiDAR quá
`--max-age` giây cũng dừng. Đây là xe ảo: không có lệnh nào tới phần cứng chấp hành, và quãng phanh là của mô phỏng.

Rút cáp LiDAR giữa chừng (cổng nối tiếp lỗi: `LidarTransportError` của driver, hoặc `OSError` từ nguồn khác): demo
ghi rõ "mất kết nối LiDAR", thôi đọc cổng, dừng xe ảo và kết thúc khi xe ảo đứng yên; đóng cổng đã chết không ném
lỗi lần hai; mã thoát 1. Lỗi cổng trước khi xe chạy (mở cổng, vòng khởi động, xả bộ đệm) cũng kết thúc gọn, mã thoát 1.
(Sửa tối 24/09/2026; chỉ thử với cổng GIẢ trong `tests/test_lidar_unplug.py`, CHƯA THỬ rút cáp C1 thật.)

Bản ghi `--recording` hết giữa lúc xe ảo chạy (`ScanStreamEnded` của `PacedReplay`): demo ghi "hết bản ghi LiDAR",
thôi đọc, dừng xe ảo như trên và kết thúc khi xe ảo đứng yên, mã thoát 0 (hết bản ghi là kết thúc bình thường của
phát lại). Hết ngay trong lúc khởi động (chưa đủ vòng quét): báo lỗi, mã thoát 1. Trước đó cả hai trường hợp dừng
bằng traceback. (Sửa tối 24/09/2026; chỉ thử với nguồn giả trong `tests/test_lidar_unplug.py`.)

Bỏ vòng khởi động (sửa muộn tối 24/09/2026). Trước đây demo bỏ đúng 15 vòng đầu. Ba lần khởi động đã ghi (p07 và
live_headless ngày 22/09, k01 ngày 24/09) cho thấy số tia/vòng còn đổi tới vòng 21–22, tức ≈ 4,2 s sau lệnh SCAN
(GIAI_DOAN_3_CHUAN_BI.md mục 2). Bỏ 15 vòng thì 10 vòng nền có 504–552 tia/vòng. Nay demo bỏ vòng cho tới khi đủ CẢ
HAI điều kiện: đã bỏ ≥ `--initial-skip` vòng (mặc định 22) và stamp của vòng ≥ `--warmup` giây trên đồng hồ phiên
của nguồn (mặc định 0 = chỉ đếm vòng). Vòng đầu tiên thỏa cả hai là vòng nền đầu tiên.
- Mặc định 22 vòng: trên cả ba bản ghi, 10 vòng nền rơi vào vòng 23–32, có 500–512 tia/vòng, tức khoảng ổn định.
  Dự phòng chỉ 1–2 vòng.
- `--warmup 4.5` (ĐỀ XUẤT – CHỜ CHỐT làm mặc định): với driver C1, đồng hồ phiên tính từ ngay trước lệnh SCAN, nên
  điều kiện này không phụ thuộc tốc độ quay lúc đầu (ở p07 các vòng đầu chỉ dài ≈ 78 ms, vòng thứ 23 về lúc ≈ 4,4 s).
  Trên ba bản ghi, vòng nền đầu lùi tới vòng 25, thêm 2 vòng dự phòng. Chưa đặt làm mặc định vì hai test `main()`
  trong `tests/test_lidar_unplug.py` dùng C1 giả có đồng hồ gần như đứng yên và giả định khởi động xong trước 40 vòng.
- Với `--recording`, stamp tính từ vòng đầu CỦA BẢN GHI (≈ 2,2 s sau SCAN, hoặc sau phần làm nóng của `bench`), nên
  `--warmup` chờ lâu hơn cần thiết. Như vậy là thận trọng, không sai.
Báo cáo ghi `warmup` (số vòng bỏ, stamp vòng nền đầu, số tia ít/nhiều nhất của các vòng nền) để đối chiếu ở lần chạy
thật. Chỉ kiểm bằng nguồn giả (`tests/test_fusion_demo.py`) và bằng cách tính lại trên ba bản ghi; CHƯA chạy với C1
thật. Ảnh hưởng của vòng khởi động lên bản đồ nền: CHƯA ĐO.
`--initial-skip` âm, hoặc `--warmup` âm / NaN / vô cực, bị từ chối như lỗi dòng lệnh (mã thoát 2, không traceback)
TRƯỚC khi mở cổng, nên mô-tơ C1 không quay vì một lỗi gõ (sửa sau rà soát, muộn tối 24/09/2026; thử bằng C1 giả,
không mở cổng thật).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time

from autopark.application.session import Session
from autopark.domain.sensors import SourceStamp
from autopark.domain.types import Bounds, ParkingGoal, Pose, Scenario, VehicleConfig
from autopark.perception.costmap import GridSpec

from .bridge import ObstacleBridge
from .fuse import fuse
from .layers import LiveLidarLayer, ScanUnion, StaticMapLayer, sensor_pose_in_map

DEFAULT_BOUNDS = Bounds(0.0, 0.0, 3.0, 2.0)
DEFAULT_START = Pose(0.5, 1.0, 0.0)
DEFAULT_GOAL = Pose(2.0, 1.0, 0.0)
# Khởi động mô-tơ C1 (ba bản ghi p07, live_headless, k01; GIAI_DOAN_3_CHUAN_BI.md mục 2): số tia/vòng về khoảng ổn định
# 500–516 từ vòng 21–22 kể từ vòng đầu, ≈ 4,2 s sau lệnh SCAN. Hai ngưỡng dưới là tạm, CHƯA CHỐT (mới ba lần khởi động).
SPIN_UP_REVOLUTIONS = 22        # mặc định của run_demo và --initial-skip
SPIN_UP_S = 4.5                 # giá trị đề xuất cho --warmup (ĐỀ XUẤT – CHỜ CHỐT làm mặc định; xem docstring)


def default_vehicle() -> VehicleConfig:
    """The phase-0 simulated vehicle from configs/vehicle_default.json (falls back to the test vehicle)."""
    path = Path(__file__).resolve().parents[2] / "configs" / "vehicle_default.json"
    if path.exists():
        return VehicleConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
    return VehicleConfig("xe_test", 0.19, 0.14, 0.06, 0.06, math.radians(30), 0.3, 0.3, 0.6, math.radians(90))


def _is_port_failure(exc: BaseException) -> bool:
    """Lỗi của chính cổng (rút cáp): thử đọc lại không giúp gì. Hết thời gian chờ một vòng quét thì không phải."""
    from autopark.lidar.rplidar_c1 import LidarTransportError

    return isinstance(exc, (LidarTransportError, OSError))


def _is_stream_end(exc: BaseException) -> bool:
    """`ScanStreamEnded` của `PacedReplay` (bản ghi hết). Không import `lidar.live_view` ở đây vì mô-đun đó kéo theo
    PySide6: nếu nó chưa được nạp thì không nguồn nào của nó có thể đã ném lỗi này."""
    live_view = sys.modules.get("autopark.lidar.live_view")
    return live_view is not None and isinstance(exc, live_view.ScanStreamEnded)


def run_demo(source, *, seconds: float, cfg: VehicleConfig | None = None, bounds: Bounds = DEFAULT_BOUNDS,
             start: Pose = DEFAULT_START, goal: Pose = DEFAULT_GOAL, resolution: float = 0.05, initial_scans: int = 10,
             initial_skip: int = SPIN_UP_REVOLUTIONS, warmup_s: float = 0.0, max_age_s: float = 0.3,
             clock=time.monotonic, sleep=time.sleep, log=print) -> dict:
    """`source` needs `read() -> LidarScan` (blocking, raises on failure) and `now() -> float` (its session clock).

    Khởi động: bỏ vòng tới khi đã bỏ ≥ `initial_skip` vòng VÀ stamp của vòng ≥ `warmup_s` (đồng hồ phiên của nguồn;
    driver C1: giây kể từ lệnh SCAN). `warmup_s=0` = chỉ đếm vòng. Kết quả nằm ở `report["warmup"]`.

    `ScanReadError` (một vòng quét không tới kịp) được đếm và đọc tiếp. Lỗi cổng (`LidarTransportError`/`OSError`)
    ghi vào `report["transport_error"]`: trước khi chạy thì trả báo cáo ngay (kèm `report["error"]`), khi đang chạy
    thì thôi đọc, dừng xe ảo và chờ nó đứng yên. `ScanStreamEnded` (bản ghi hết) đặt `report["stream_ended"]`:
    trước khi chạy thì trả báo cáo ngay (kèm `report["error"]`), khi đang chạy thì dừng xe ảo như lỗi cổng nhưng không
    tính là lỗi. Chỉ các lỗi trên được bắt; ngoại lệ khác của nguồn vẫn thoát ra như trước, ví dụ `ProtocolError`
    khi `read()` của driver tự gọi `start()` mà thiết bị trả lời sai, hoặc `RuntimeError` của `now()` khi nguồn chưa
    `start()` (sửa và thử bằng nguồn giả tối 24/09/2026)."""
    from autopark.lidar.rplidar_c1 import ScanReadError

    # warmup_s phải hữu hạn: NaN làm điều kiện chờ luôn sai (không chờ), vô cực làm demo bỏ vòng mãi mãi
    if initial_skip < 0 or not (0.0 <= warmup_s < math.inf) or initial_scans < 1:
        raise ValueError("need initial_skip >= 0, warmup_s >= 0 (finite) and initial_scans >= 1")
    cfg = cfg or default_vehicle()
    scenario = Scenario("ban_thu_lidar", bounds, start, ParkingGoal(goal), obstacles=[])
    session = Session(scenario, cfg)
    grid = GridSpec(bounds.xmin, bounds.xmax, bounds.ymin, bounds.ymax, resolution)
    layer = LiveLidarLayer(grid, window=3, max_age_s=max_age_s, self_mask=cfg, mask_margin=0.10)   # own body + cable ignored
    bridge = ObstacleBridge(session, prefix="lidar", path_margin=0.10)          # only the path corridor stops the car
    report = {"status": None, "initial_obstacles": 0, "new_obstacles": 0, "events": [], "stop_reason": "",
              "collided": None, "scans": 0, "read_errors": 0, "transport_error": None, "stream_ended": False,
              "error": None, "warmup": {"skipped": 0, "min_revolutions": initial_skip, "until_s": warmup_s,
                                        "first_map_scan_s": None, "map_beams_min": None, "map_beams_max": None}}
    warmup = report["warmup"]

    def abort_before_run(exc: BaseException, stage: str) -> dict:
        if _is_stream_end(exc):
            report["stream_ended"] = True
            report["error"] = f"bản ghi LiDAR hết {stage}: mới có {report['scans']} vòng quét"
        else:
            report["read_errors"] += 1
            if _is_port_failure(exc):
                report["transport_error"] = f"{type(exc).__name__}: {exc}"
                report["error"] = f"mất kết nối LiDAR {stage} (lỗi cổng nối tiếp, rút cáp?): {exc}"
            else:
                report["error"] = f"LiDAR không cho đủ vòng quét {stage}: {exc}"
        report["status"] = "LỖI LIDAR TRƯỚC KHI CHẠY"
        log(f"{report['status']}: {report['error']}")
        return report

    known = ScanUnion(grid)
    try:
        # motor spin-up: beam density still changing. Skip until BOTH hold: `initial_skip` revolutions skipped and the
        # revolution's stamp (source session clock; C1 driver: seconds since SCAN) >= warmup_s. The first revolution
        # that satisfies both is the first one of the static map.
        scan = source.read()
        report["scans"] += 1
        while warmup["skipped"] < initial_skip or scan.stamp.t < warmup_s:
            warmup["skipped"] += 1
            scan = source.read()
            report["scans"] += 1
        warmup["first_map_scan_s"] = float(scan.stamp.t)
        beams = []
        # bench "static map": everything hit in at least 2 of the initial scans (audit 22/09: 1-of-10 kept 29 %
        # flicker cells; 2-of-10 keeps what the live 2-of-3 rule would also call occupied)
        for index in range(initial_scans):
            if index:
                scan = source.read()
                report["scans"] += 1
            beams.append(len(scan.angles_rad))
            scan = layer.filter_scan(scan)
            known.add(scan, sensor_pose_in_map(start, layer.mount), max_range=layer.max_range)
            layer.add_scan(scan, start)
        warmup["map_beams_min"], warmup["map_beams_max"] = min(beams), max(beams)
    except (ScanReadError, OSError) as exc:
        return abort_before_run(exc, "trong lúc khởi động")
    except RuntimeError as exc:
        if not _is_stream_end(exc):
            raise
        return abort_before_run(exc, "trong lúc khởi động")
    static = StaticMapLayer("bench_static")
    static.set(known.costmap(SourceStamp("bench_static", max(0.0, source.now()), True, "map"),
                             min_hits=min(2, initial_scans)))                                  # seen in >= 2 scans
    initial = bridge.sync(fuse([static], grid, now=source.now()))
    report["initial_obstacles"] = len(initial)
    log(f"bỏ {warmup['skipped']} vòng khởi động mô-tơ (vòng nền đầu ở t={warmup['first_map_scan_s']:.2f} s "
        f"trên đồng hồ nguồn; ngưỡng ≥ {initial_skip} vòng và ≥ {warmup_s:g} s); nền dựng từ {initial_scans} vòng, "
        f"{warmup['map_beams_min']}–{warmup['map_beams_max']} tia/vòng")
    log(f"vật cản có sẵn quanh LiDAR (trong sa bàn): {len(initial)}")
    result = session.plan_sync()
    if not result.ok:
        report["status"] = f"KHÔNG LẬP ĐƯỢC ĐƯỜNG: {result.message}"
        log(report["status"])
        return report
    flush = getattr(source, "flush", None)
    if flush is not None:
        try:
            flush()                                     # planning took time: discard the backlog
        except OSError as exc:
            return abort_before_run(exc, "lúc xả bộ đệm sau khi lập đường")
    session.start_run()
    log("xe ảo bắt đầu chạy; đưa vật vào trước LiDAR để thử dừng")
    last_wall = clock()
    deadline = last_wall + seconds
    seen_events = 0
    reading_over = False                                # cổng chết hoặc bản ghi hết: không đọc nữa
    while session.simulating and clock() < deadline:
        scan = None
        added = []
        if not reading_over:
            try:
                scan = source.read()
                report["scans"] += 1
            except (ScanReadError, OSError) as exc:
                report["read_errors"] += 1
                if _is_port_failure(exc):
                    # Cổng đã chết: đọc lại chỉ ném lỗi liên tục. Thôi đọc, dừng xe ảo ngay (không chờ lớp LiDAR
                    # hết hạn); vòng lặp chỉ còn tiến mô phỏng cho tới khi xe ảo đứng yên.
                    reading_over = True
                    report["transport_error"] = f"{type(exc).__name__}: {exc}"
                    log(f"mất kết nối LiDAR (lỗi cổng nối tiếp, rút cáp?): {exc} — thôi đọc cổng, dừng xe ảo; "
                        f"demo kết thúc khi xe ảo đứng yên")
                    session.request_stop(f"Mất kết nối LiDAR (lỗi cổng nối tiếp): {exc}")
                else:
                    log(f"lỗi đọc LiDAR: {exc}")
            except RuntimeError as exc:
                if not _is_stream_end(exc):
                    raise
                # Bản ghi hết: như cổng chết nhưng là kết thúc bình thường của phát lại, không tính là lỗi.
                reading_over = True
                report["stream_ended"] = True
                log("hết bản ghi LiDAR — thôi đọc, dừng xe ảo; demo kết thúc khi xe ảo đứng yên")
                session.request_stop("Hết bản ghi LiDAR")
        now = source.now()
        if reading_over:
            sleep(0.02)                                 # không còn gì để đọc: để xe ảo phanh theo thời gian thực
        else:
            if scan is not None:
                layer.add_scan(scan, start)             # the real sensor does not move with the virtual car
            added = bridge.inject(fuse([static, layer], grid, now))
            report["new_obstacles"] += len(added)
        wall = clock()
        session.advance(wall - last_wall)
        last_wall = wall
        if added:
            where = "; ".join(f"({o.cx:.2f}, {o.cy:.2f}) {o.width * 100:.0f}×{o.height * 100:.0f} cm" for o in added[:5])
            log(f"t={now:6.2f}s  vật cản mới: {len(added)} [{where}]  → {session.state.value}")
        for event in session.safety_events[seen_events:]:
            log(f"t={now:6.2f}s  sự kiện an toàn: {event.code}: {event.message}")
        seen_events = len(session.safety_events)
    report["status"] = session.state.value
    report["events"] = [e.code for e in session.safety_events]
    report["stop_reason"] = session.stop_reason
    report["collided"] = None if session.world is None else session.world.collided
    report["bridge_stops"] = bridge.stops
    report["off_path_obstacles"] = len(bridge.seen)
    log(f"kết thúc: {report['status']}, sự kiện {report['events']}, va chạm {report['collided']}, "
        f"vật mới ngoài đường (không dừng): {len(bridge.seen)}"
        + (f"; mất kết nối LiDAR: {report['transport_error']}" if report["transport_error"] else "")
        + ("; hết bản ghi LiDAR" if report["stream_ended"] else ""))
    return report


def _close_quietly(source) -> str | None:
    """Đóng nguồn. Cổng đã chết (rút cáp) thì `close()` không gửi được STOP và ném `OSError`: trả thông báo thay vì
    ném lần hai trong `finally`."""
    try:
        source.close()
    except OSError as exc:
        return f"đóng LiDAR không trọn vẹn (cổng đã lỗi, không gửi được STOP): {type(exc).__name__}: {exc}"
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--port", help="COM port of the RPLIDAR C1 (or auto); default: lidar_port in configs/thiet_bi.json")
    where.add_argument("--recording", type=Path, help="replay a .npz recording at real-time pace")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--max-age", type=float, default=0.3)
    parser.add_argument("--mirror", action="store_true")
    parser.add_argument("--resolution", type=float, default=0.05)
    parser.add_argument("--initial-skip", type=int, default=SPIN_UP_REVOLUTIONS,
                        help="skip at least this many revolutions at start-up (C1 motor still spinning up)")
    parser.add_argument("--warmup", type=float, default=0.0,
                        help=f"and skip every revolution stamped earlier than this many seconds on the source clock "
                             f"(driver: since the SCAN command; --recording: since its first revolution); 0 = count "
                             f"only; suggested {SPIN_UP_S:g}")
    args = parser.parse_args(argv)
    # kiểm TRƯỚC khi mở cổng: sau `start()` mô-tơ C1 đã quay. `not (0 <= x < inf)` loại cả NaN và vô cực
    if args.initial_skip < 0 or not (0.0 <= args.warmup < math.inf):
        parser.error("--initial-skip phải ≥ 0 và --warmup phải là số hữu hạn ≥ 0")
    if args.recording is None:
        from autopark.lidar.port import LidarPortError, lidar_port
        from autopark.lidar.rplidar_c1 import RplidarC1Source
        from autopark.lidar.rplidar_protocol import ProtocolError

        try:
            port = lidar_port(args.port)
        except LidarPortError as exc:
            print(f"không xác định được cổng LiDAR: {exc}", file=sys.stderr)
            return 1
        source = None
        try:
            source = RplidarC1Source.open(port, mirror=args.mirror)
            source.start()
        except (OSError, ProtocolError) as exc:        # cổng không có/đang bận, thiết bị không trả lời đúng
            print(f"không mở được LiDAR trên {port}: {type(exc).__name__}: {exc}", file=sys.stderr)
            if source is not None:
                problem = _close_quietly(source)
                if problem:
                    print(problem, file=sys.stderr)
            return 1
    else:
        from autopark.lidar.live_view import PacedReplay

        source = PacedReplay(args.recording)
    problem = None
    try:
        report = run_demo(source, seconds=args.seconds, max_age_s=args.max_age, resolution=args.resolution,
                          initial_skip=args.initial_skip, warmup_s=args.warmup)
    finally:
        problem = _close_quietly(source)
        if problem:
            print(problem, file=sys.stderr)
    report["close_error"] = problem
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] is not None and not report["error"] and not report["transport_error"] else 1


if __name__ == "__main__":
    sys.exit(main())
