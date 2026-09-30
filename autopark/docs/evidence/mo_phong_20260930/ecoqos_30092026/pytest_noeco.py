"""Chạy pytest trong một tiến trình đã tự tắt EcoQoS (SetProcessInformation, ProcessPowerThrottling,
kiểm soát EXECUTION_SPEED, trạng thái tắt). Tham số truyền thẳng cho pytest. Chạy trong thư mục autopark của repo.

Mọi thứ nằm dưới `if __name__ == "__main__"`: vài test mở ProcessPoolExecutor (spawn), tiến trình con chạy lại tệp
này dưới tên `__mp_main__`. Bản đầu (30/09/2026 10:57) thiếu chặn này nên mỗi tiến trình con chạy lại cả bộ test."""
import ctypes
import os
import sys
from ctypes import wintypes


def disable_ecoqos() -> bool:
    class PPTS(ctypes.Structure):
        _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    state = PPTS(1, 1, 0)
    return bool(k.SetProcessInformation(k.GetCurrentProcess(), 4, ctypes.byref(state), ctypes.sizeof(state)))


if __name__ == "__main__":
    print("EcoQoS tắt:", disable_ecoqos(), flush=True)
    sys.path.insert(0, os.getcwd())          # như `python -m pytest`
    import pytest

    sys.exit(pytest.main(sys.argv[1:]))
