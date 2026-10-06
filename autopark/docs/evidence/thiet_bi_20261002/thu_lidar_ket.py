"""Thử lại lỗi 'bad response descriptor' của LD-1 lần 2 (02/10/2026): C1 bị bỏ lại đang quét (tiến trình trước chết
không gửi STOP). Đo: (1) gọi start() lặp lại trong CÙNG một cổng có tự hồi phục không; (2) đóng rồi mở lại cổng; (3) RESET.
Chạy sau khi đã giết một tiến trình 'rplidar_c1 stream' đang quét."""
import sys
import time

sys.path.insert(0, r"D:\xetulai\autopark\autopark")
from autopark.lidar.rplidar_c1 import RplidarC1Source  # noqa: E402

PORT = "COM3"
mode = sys.argv[1] if len(sys.argv) > 1 else "retry"
src = RplidarC1Source.open(PORT)
print("settle_s =", src.settle_s)
ok = False
for k in range(int(sys.argv[2]) if len(sys.argv) > 2 else 10):
    try:
        src.start()
        ok = True
        print(f"lần {k}: start() đạt")
        break
    except Exception as exc:  # noqa: BLE001
        waiting = getattr(src.transport, "in_waiting", None)
        print(f"lần {k}: {type(exc).__name__}: {exc} (in_waiting {waiting})")
        if mode == "reset" and k == 0:
            banner = src.reset()
            print("RESET, banner:", banner[:40])
        time.sleep(0.2)
if not ok and mode == "retry":
    print("-> đóng rồi mở lại cổng")
    try:
        src.close()
    except Exception as exc:  # noqa: BLE001
        print("close:", exc)
    src = RplidarC1Source.open(PORT)
    try:
        src.start()
        print("sau khi mở lại: start() đạt")
        ok = True
    except Exception as exc:  # noqa: BLE001
        print(f"sau khi mở lại: {type(exc).__name__}: {exc}")
if ok:
    scan = src.read()
    print("một vòng:", len(scan.ranges_m), "tia")
src.close()
