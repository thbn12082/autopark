"""Thời gian plan_sync của kịch bản test đỗ qua bo ảo khi ghim tiến trình vào một nhóm CPU logic (mặt nạ hex)."""
import ctypes
import math
import os
import statistics
import sys
import time

mask = int(sys.argv[1], 16)
k32 = ctypes.WinDLL("kernel32")
k32.GetCurrentProcess.restype = ctypes.c_void_p
k32.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
assert k32.SetProcessAffinityMask(k32.GetCurrentProcess(), mask)

REPO = r"D:/xetulai/autopark/autopark"
sys.path.insert(0, REPO)
os.chdir(REPO)
from autopark.power_throttling import apply_ecoqos_policy  # noqa: E402

apply_ecoqos_policy("pytest")
from autopark.application.session import Session  # noqa: E402
from autopark.domain.types import Bounds, ParkingGoal, Pose, Scenario, VehicleConfig  # noqa: E402

cfg = VehicleConfig(name="xe_test", wheelbase=0.19, width=0.14, front_overhang=0.06, rear_overhang=0.06,
                    max_steer=math.radians(30), max_speed=0.3, max_accel=0.3, max_decel=0.6,
                    max_steer_rate=math.radians(90))
times = []
for _ in range(12):
    sc = Scenario(name="test", bounds=Bounds(0.0, 0.0, 3.0, 2.0), start=Pose(0.5, 1.0, 0.0),
                  goal=ParkingGoal(Pose(1.1, 1.0, 0.0)), obstacles=[])
    t0 = time.perf_counter()
    s = Session(sc, cfg)
    assert s.plan_sync().ok
    times.append(1000 * (time.perf_counter() - t0))
    s.close()
print(f"mặt nạ {sys.argv[1]}: lần 1 {times[0]:.0f} ms; lần 2..12 trung vị {statistics.median(times[1:]):.0f}, "
      f"min {min(times[1:]):.0f}, max {max(times[1:]):.0f} ms")
