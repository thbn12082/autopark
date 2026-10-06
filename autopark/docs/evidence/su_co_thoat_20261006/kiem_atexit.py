"""Gói nào đăng ký hàm dọn dẹp lúc tắt (atexit / threading._register_atexit) trong tiến trình test .venv.
Chỉ nhập gói, không mở thiết bị, không tạo cửa sổ. Việc 8, 06/10/2026."""
import atexit
import os
import sys
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_reg = atexit.register
_treg = threading._register_atexit
log = []


def reg(func, *a, **k):
    log.append(("atexit", getattr(func, "__module__", "?"), getattr(func, "__qualname__", repr(func)), CUR))
    return _reg(func, *a, **k)


def treg(func, *a, **k):
    log.append(("threading._register_atexit", getattr(func, "__module__", "?"), getattr(func, "__qualname__", repr(func)), CUR))
    return _treg(func, *a, **k)


atexit.register = reg
threading._register_atexit = treg
CUR = "?"
for name in ("numpy", "cv2", "shapely", "serial", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
             "concurrent.futures.process", "multiprocessing.pool", "logging", "autopark.ui.app",
             "autopark.rig.core", "autopark.video.multicam", "autopark.transport.vehicle_io"):
    CUR = name
    n0 = atexit._ncallbacks()
    try:
        __import__(name)
        ok = "ok"
    except Exception as exc:  # noqa: BLE001
        ok = f"lỗi {type(exc).__name__}: {exc}"
    print(f"{name:32s} {ok:10s} atexit {n0} -> {atexit._ncallbacks()}")
print("--- đăng ký thấy được qua atexit.register / threading._register_atexit:")
for row in log:
    print("  ", row)
print("threading._threading_atexits:", [getattr(f, "__qualname__", f) for f in getattr(threading, "_threading_atexits", [])])
print("số luồng Python:", threading.active_count(), [t.name for t in threading.enumerate()])
