"""Tiến trình con vô hại cho thí nghiệm Stop-Process: ghi pid (của trình thông dịch gốc, như PID 26456 ngày 02/10/2026)
rồi cứ 5 ms ghi time.time() vào tệp (flush), tối đa 60 s. Việc 8, 06/10/2026."""
import os
import sys
import time

pid_file, out_file = sys.argv[1], sys.argv[2]
with open(out_file, "w", encoding="utf-8") as out:
    with open(pid_file, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    t_end = time.time() + 60
    while time.time() < t_end:
        out.write(f"{time.time():.4f}\n")
        out.flush()
        time.sleep(0.005)
