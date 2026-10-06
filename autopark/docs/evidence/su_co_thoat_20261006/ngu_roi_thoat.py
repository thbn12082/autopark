"""Ngủ N giây rồi tự thoát bằng ExitProcess(mã) — không ngoại lệ, không WER. Thử chay_co_theo_doi.py. Việc 8, 06/10/2026.
Dùng: ngu_roi_thoat.py 12 0xFFFFFFFF"""
import ctypes
import sys
import time

time.sleep(float(sys.argv[1]))
k32 = ctypes.WinDLL("kernel32")
k32.ExitProcess.argtypes = [ctypes.c_uint]
k32.ExitProcess(int(sys.argv[2], 0) & 0xFFFFFFFF)
