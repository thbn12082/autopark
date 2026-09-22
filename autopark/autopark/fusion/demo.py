"""Thử nghiệm bàn: LiDAR thật (hoặc bản ghi) → lớp LiveLidar → bản đồ hợp nhất → phiên đỗ mô phỏng giai đoạn 0.

    python -m autopark.fusion.demo --port COM4 --seconds 30
    python -m autopark.fusion.demo --recording runs/lidar_bench/20260922/p07_nen_phong.npz --seconds 10

Xe ảo đứng ở xuất phát của sa bàn 3 × 2 m, hướng +x; LiDAR thật ĐỨNG YÊN tại đúng vị trí xuất phát đó, cùng hướng
xe, và quan sát sa bàn như một cảm biến cố định: vật thật cách LiDAR 1 m phía trước là vật cách xuất phát 1 m.
(Gán LiDAR vào xe ảo đang chạy là sai, vì LiDAR không chuyển động theo xe: đo ngày 22/09, cả cảnh bị dịch theo xe
và mọi mép vật trở thành "vật mới" ngay sau khi xuất phát.) Trình tự: (1) bỏ `initial_skip` vòng đầu (mô-tơ C1 còn tăng
tốc, mật độ tia đổi từng vòng), rồi `initial_scans` vòng được đồng bộ vào sa bàn thành vật cản có sẵn; (2) lập
đường thẳng tới đích, nếu đồ vật quanh bàn đã chặn thì báo và thôi; xả bộ đệm LiDAR sau khi lập đường để vòng
quét tiếp theo là dữ liệu hiện tại chứ không phải tồn đọng; (3) chạy; mỗi vòng quét mới chỉ đưa THÔNG TIN MỚI
vào (ô bị chạm ở 2 trong 3 vòng gần nhất, cách vật đã biết hơn một ô), nên đưa tay hoặc hộp vào trước LiDAR lúc
xe đang chạy sẽ phát MAP_CHANGED → phanh → dừng → chờ lập lại đường; mất LiDAR quá `--max-age` giây cũng dừng. Đây là xe ảo: không có lệnh nào
tới phần cứng chấp hành, và quãng phanh là của mô phỏng.
"""
from __future__ import annotations

import argparse
import json
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


def default_vehicle() -> VehicleConfig:
    """The phase-0 simulated vehicle from configs/vehicle_default.json (falls back to the test vehicle)."""
    path = Path(__file__).resolve().parents[2] / "configs" / "vehicle_default.json"
    if path.exists():
        return VehicleConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
    import math

    return VehicleConfig("xe_test", 0.19, 0.14, 0.06, 0.06, math.radians(30), 0.3, 0.3, 0.6, math.radians(90))


def run_demo(source, *, seconds: float, cfg: VehicleConfig | None = None, bounds: Bounds = DEFAULT_BOUNDS,
             start: Pose = DEFAULT_START, goal: Pose = DEFAULT_GOAL, resolution: float = 0.05, initial_scans: int = 10,
             initial_skip: int = 15, max_age_s: float = 0.3, clock=time.monotonic, log=print) -> dict:
    """`source` needs `read() -> LidarScan` (blocking, raises on failure) and `now() -> float` (its session clock)."""
    from autopark.lidar.rplidar_c1 import ScanReadError

    cfg = cfg or default_vehicle()
    scenario = Scenario("ban_thu_lidar", bounds, start, ParkingGoal(goal), obstacles=[])
    session = Session(scenario, cfg)
    grid = GridSpec(bounds.xmin, bounds.xmax, bounds.ymin, bounds.ymax, resolution)
    layer = LiveLidarLayer(grid, window=3, max_age_s=max_age_s, self_mask=cfg, mask_margin=0.10)   # own body + cable ignored
    bridge = ObstacleBridge(session, prefix="lidar", path_margin=0.10)          # only the path corridor stops the car
    report = {"status": None, "initial_obstacles": 0, "new_obstacles": 0, "events": [], "stop_reason": "",
              "collided": None, "scans": 0, "read_errors": 0}
    for _ in range(initial_skip):
        source.read()                                   # motor spin-up: beam density still changing
        report["scans"] += 1
    # bench "static map": everything hit in at least 2 of the initial scans (audit 22/09: 1-of-10 kept 29 %
    # flicker cells; 2-of-10 keeps what the live 2-of-3 rule would also call occupied)
    known = ScanUnion(grid)
    for _ in range(initial_scans):
        scan = layer.filter_scan(source.read())
        known.add(scan, sensor_pose_in_map(start, layer.mount), max_range=layer.max_range)
        layer.add_scan(scan, start)
        report["scans"] += 1
    static = StaticMapLayer("bench_static")
    static.set(known.costmap(SourceStamp("bench_static", max(0.0, source.now()), True, "map"),
                             min_hits=min(2, initial_scans)))                                  # seen in >= 2 scans
    initial = bridge.sync(fuse([static], grid, now=source.now()))
    report["initial_obstacles"] = len(initial)
    log(f"vật cản có sẵn quanh LiDAR (trong sa bàn): {len(initial)}")
    result = session.plan_sync()
    if not result.ok:
        report["status"] = f"KHÔNG LẬP ĐƯỢC ĐƯỜNG: {result.message}"
        log(report["status"])
        return report
    flush = getattr(source, "flush", None)
    if flush is not None:
        flush()                                         # planning took time: discard the backlog
    session.start_run()
    log("xe ảo bắt đầu chạy; đưa vật vào trước LiDAR để thử dừng")
    last_wall = clock()
    deadline = last_wall + seconds
    seen_events = 0
    while session.simulating and clock() < deadline:
        scan = None
        try:
            scan = source.read()
            report["scans"] += 1
        except ScanReadError as exc:
            report["read_errors"] += 1
            log(f"lỗi đọc LiDAR: {exc}")
        now = source.now()
        if scan is not None:
            layer.add_scan(scan, start)                 # the real sensor does not move with the virtual car
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
        f"vật mới ngoài đường (không dừng): {len(bridge.seen)}")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--port", help="COM port of the RPLIDAR C1")
    where.add_argument("--recording", type=Path, help="replay a .npz recording at real-time pace")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--max-age", type=float, default=0.3)
    parser.add_argument("--mirror", action="store_true")
    parser.add_argument("--resolution", type=float, default=0.05)
    args = parser.parse_args(argv)
    if args.port:
        from autopark.lidar.rplidar_c1 import RplidarC1Source

        source = RplidarC1Source.open(args.port, mirror=args.mirror)
        source.start()
    else:
        from autopark.lidar.live_view import PacedReplay

        source = PacedReplay(args.recording)
    try:
        report = run_demo(source, seconds=args.seconds, max_age_s=args.max_age, resolution=args.resolution)
    finally:
        source.close()
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] not in (None,) else 1


if __name__ == "__main__":
    sys.exit(main())
