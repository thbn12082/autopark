"""Tắt EcoQoS (power throttling của Windows 11) cho một tiến trình (thêm 30/09/2026).

Windows 11 tự quyết EcoQoS cho từng tiến trình: tiến trình không có cửa sổ hiện (ví dụ pytest mở từ một shell chạy nền)
có thể bị dồn sang lõi E hay hạ xung dù máy rảnh. Đo 30/09/2026 trên máy bàn (i9-14900), nhóm test `planner_budget` mở
từ shell không cửa sổ: để Windows tự quyết thì 2/2 lượt có test hỏng (1 và 3 test, ví dụ `uturn_w46` hết hạn 8 s), tổng
thời gian 55 s và 103 s; tiến trình tự tắt EcoQoS thì 2/2 lượt đạt 15/15, 36 s và 40 s (docs/CHUYEN_MAY_BAN.md mục 8).

Dùng ở: QEMU của bo ảo (`transport/qemu_board.py`), tiến trình pytest (`tests/conftest.py`). Chỉ có tác dụng trên
Windows; nơi khác các hàm trả False / None và không làm gì.
"""
from __future__ import annotations

import sys

_PROCESS_POWER_THROTTLING = 4               # PROCESS_INFORMATION_CLASS.ProcessPowerThrottling
_EXECUTION_SPEED = 0x1                      # PROCESS_POWER_THROTTLING_EXECUTION_SPEED
_PROCESS_SET_INFORMATION = 0x0200
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _kernel32():
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.SetProcessInformation.restype = wintypes.BOOL
    kernel32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.GetProcessInformation.restype = wintypes.BOOL
    kernel32.GetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    return kernel32


def _state_struct(control_mask: int = 0, state_mask: int = 0):
    import ctypes
    from ctypes import wintypes

    class PowerThrottlingState(ctypes.Structure):
        _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]

    return PowerThrottlingState(1, control_mask, state_mask)     # Version 1 = PROCESS_POWER_THROTTLING_CURRENT_VERSION


def _call_on_process(pid: int | None, access: int, call) -> bool:
    """Gọi `call(kernel32, handle)` với tiến trình `pid` (None = tiến trình hiện tại); False nếu không mở được tiến trình."""
    kernel32 = _kernel32()
    if pid is None:
        return call(kernel32, kernel32.GetCurrentProcess())     # handle giả, không cần đóng
    handle = kernel32.OpenProcess(access, False, pid)
    if not handle:
        return False
    try:
        return call(kernel32, handle)
    finally:
        kernel32.CloseHandle(handle)


def disable_power_throttling(pid: int | None = None) -> bool:
    """Tắt EcoQoS cho tiến trình `pid` (None = tiến trình đang chạy): SetProcessInformation(ProcessPowerThrottling),
    kiểm soát EXECUTION_SPEED với trạng thái tắt. Không ảnh hưởng tiến trình con mở sau đó. Trả False khi không làm được
    (không phải Windows, Windows chưa có API này, không mở được tiến trình); không ném lỗi."""
    if sys.platform != "win32":
        return False
    import ctypes

    def call(kernel32, handle) -> bool:
        state = _state_struct(_EXECUTION_SPEED, 0)
        return bool(kernel32.SetProcessInformation(handle, _PROCESS_POWER_THROTTLING, ctypes.byref(state),
                                                   ctypes.sizeof(state)))

    try:
        return _call_on_process(pid, _PROCESS_SET_INFORMATION, call)
    except (OSError, AttributeError):                             # AttributeError: kernel32 cũ không có hàm này
        return False


def execution_speed_throttling(pid: int | None = None) -> str | None:
    """Trạng thái EcoQoS (EXECUTION_SPEED) của tiến trình `pid` (None = tiến trình đang chạy): "off" (đã tắt tường minh),
    "on" (đã bật tường minh), "system" (Windows tự quyết, mặc định), hoặc None khi không đọc được (không phải Windows,
    Windows chưa hỗ trợ GetProcessInformation với ProcessPowerThrottling, không mở được tiến trình)."""
    if sys.platform != "win32":
        return None
    import ctypes

    result: list[str] = []

    def call(kernel32, handle) -> bool:
        state = _state_struct()
        if not kernel32.GetProcessInformation(handle, _PROCESS_POWER_THROTTLING, ctypes.byref(state),
                                              ctypes.sizeof(state)):
            return False
        if not state.ControlMask & _EXECUTION_SPEED:
            result.append("system")
        else:
            result.append("on" if state.StateMask & _EXECUTION_SPEED else "off")
        return True

    try:
        ok = _call_on_process(pid, _PROCESS_QUERY_LIMITED_INFORMATION, call)
    except (OSError, AttributeError):
        return None
    return result[0] if ok else None
