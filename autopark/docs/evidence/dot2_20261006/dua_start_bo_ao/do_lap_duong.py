"""Đo thời gian Session(scenario, cfg) + plan_sync() của kịch bản test đỗ qua bo ảo (đường thẳng 0,6 m), trong một
tiến trình mới: lần đầu (lạnh) và các lần sau (ấm). Không cần QEMU."""
import math
import os
import statistics
import sys
import time

REPO = r"D:/xetulai/autopark/autopark"
sys.path.insert(0, REPO)
os.chdir(REPO)
from autopark.power_throttling import apply_ecoqos_policy  # noqa: E402

eco = apply_ecoqos_policy("pytest").state
t_imp = time.perf_counter()
from autopark.application.session import Session  # noqa: E402
from autopark.domain.types import Bounds, Obstacle, ParkingGoal, Pose, Scenario, VehicleConfig  # noqa: E402
t_imp = time.perf_counter() - t_imp


def make():
    cfg = VehicleConfig(name="xe_test", wheelbase=0.19, width=0.14, front_overhang=0.06, rear_overhang=0.06,
                        max_steer=math.radians(30), max_speed=0.3, max_accel=0.3, max_decel=0.6,
                        max_steer_rate=math.radians(90))
    sc = Scenario(name="test", bounds=Bounds(0.0, 0.0, 3.0, 2.0), start=Pose(0.5, 1.0, 0.0),
                  goal=ParkingGoal(Pose(2.4, 0.4, math.pi / 2)), obstacles=[Obstacle("hop_1", 1.2, 1.0, 0.2, 0.2, 0.0)])
    sc.obstacles = []
    sc.start, sc.goal = Pose(0.5, 1.0, 0.0), ParkingGoal(Pose(1.1, 1.0, 0.0))
    return sc, cfg


times = []
for k in range(int(sys.argv[1]) if len(sys.argv) > 1 else 15):
    sc, cfg = make()
    t0 = time.perf_counter()
    s = Session(sc, cfg)
    r = s.plan_sync()
    times.append(1000 * (time.perf_counter() - t0))
    assert r.ok
    s.close()
import numpy  # noqa: E402

print(f"{sys.executable}: numpy {numpy.__version__}, EcoQoS {eco}, import Session {1000 * t_imp:.0f} ms; "
      f"lần 1 {times[0]:.0f} ms; lần 2..n: trung vị {statistics.median(times[1:]):.0f} ms, "
      f"min {min(times[1:]):.0f}, max {max(times[1:]):.0f} (n={len(times) - 1})")
