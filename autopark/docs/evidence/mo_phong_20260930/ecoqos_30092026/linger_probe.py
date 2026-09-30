"""Plugin pytest tạm: trước mỗi test của test_planner_hard_cases ghi lại còn QEMU nào chạy
và những luồng Python nào còn sống (để xem test bo ảo chạy trước có để lại tải không)."""
import os
import subprocess
import threading
import time

LOG = os.path.join(os.path.dirname(__file__), "linger_probe.log")


def pytest_runtest_setup(item):
    if "test_planner_hard_cases" not in item.nodeid:
        return
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq qemu-system-xtensa.exe", "/NH"],
                         capture_output=True, text=True).stdout
    n = out.count("qemu-system-xtensa")
    threads = sorted(t.name for t in threading.enumerate())
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {item.nodeid}: qemu={n} threads={threads}\n")
