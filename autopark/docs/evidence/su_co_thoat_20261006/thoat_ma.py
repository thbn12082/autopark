"""Tự thoát bằng ExitProcess(mã) — KHÔNG gây ngoại lệ, nên không có WER/dump. Dùng để xem Git Bash (MSYS) đổi mã thoát
32 bit của tiến trình Windows gốc thành $? thế nào. Việc 8, 06/10/2026.
Dùng: python thoat_ma.py 0xC000007F"""
import ctypes
import sys

code = int(sys.argv[1], 0) & 0xFFFFFFFF
k32 = ctypes.WinDLL("kernel32")
k32.ExitProcess.argtypes = [ctypes.c_uint]
k32.ExitProcess(code)
