"""flush() của driver C1 đã sửa có bỏ được phần ứ trên cổng CP210x thật không (02/10/2026)."""
import sys
import time

sys.path.insert(0, r"D:\xetulai\_wt\gop\autopark")
from autopark.lidar.rplidar_c1 import RplidarC1Source  # noqa: E402

src = RplidarC1Source.open("COM3")
print("driver:", sys.modules["autopark.lidar.rplidar_c1"].__file__)
first = src.read()
print("vòng đầu:", len(first.ranges_m), "tia")
for pause in (0.5, 1.0):
    time.sleep(pause)
    before = src.transport.in_waiting
    t = time.perf_counter()
    src.flush()
    took = (time.perf_counter() - t) * 1000
    after = src.transport.in_waiting
    scan = src.read()
    print(f"ngưng đọc {pause:.1f} s: chờ {before} byte -> flush {took:.1f} ms -> còn {after} byte; vòng kế: {len(scan.ranges_m)} tia")
print(src.stats())
src.close()
