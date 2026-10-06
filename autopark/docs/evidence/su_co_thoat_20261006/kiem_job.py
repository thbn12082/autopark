"""Tiến trình python này có nằm trong job object nào không, cờ LimitFlags của job là gì, ErrorMode là gì,
và tiến trình cha là ai. Chỉ đọc, không đổi gì. (Việc 8, 06/10/2026)
Bản trong repo (06/10/2026): khai báo kiểu HANDLE cho GetCurrentProcess / IsProcessInJob; bản nháp không khai báo nên
handle giả −1 bị cắt còn 32 bit, IsProcessInJob thất bại (lỗi 6) và in False sai."""
import ctypes
import ctypes.wintypes as wt
import os
import sys

k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wt.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wt.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wt.DWORD),
        ("SchedulingClass", wt.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


FLAGS = {
    0x00000001: "WORKINGSET",
    0x00000002: "PROCESS_TIME",
    0x00000004: "JOB_TIME",
    0x00000008: "ACTIVE_PROCESS",
    0x00000010: "AFFINITY",
    0x00000020: "PRIORITY_CLASS",
    0x00000040: "PRESERVE_JOB_TIME",
    0x00000080: "SCHEDULING_CLASS",
    0x00000100: "PROCESS_MEMORY",
    0x00000200: "JOB_MEMORY",
    0x00000400: "DIE_ON_UNHANDLED_EXCEPTION",
    0x00000800: "BREAKAWAY_OK",
    0x00001000: "SILENT_BREAKAWAY_OK",
    0x00002000: "KILL_ON_JOB_CLOSE",
    0x00004000: "SUBSET_AFFINITY",
}

k32.GetCurrentProcess.restype = wt.HANDLE
k32.IsProcessInJob.argtypes = [wt.HANDLE, wt.HANDLE, ctypes.POINTER(wt.BOOL)]
in_job = wt.BOOL()
k32.IsProcessInJob(k32.GetCurrentProcess(), None, ctypes.byref(in_job))
info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
ret = wt.DWORD()
ok = k32.QueryInformationJobObject(None, 9, ctypes.byref(info), ctypes.sizeof(info), ctypes.byref(ret))
flags = info.BasicLimitInformation.LimitFlags if ok else None
names = [n for b, n in FLAGS.items() if flags and flags & b]
k32.GetErrorMode.restype = wt.UINT
em = k32.GetErrorMode()

# tiến trình cha
import subprocess  # noqa: E402

ppid = os.getppid() if hasattr(os, "getppid") else None
parent = ""
try:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={ppid}'; $p.Name + ' | ' + $p.ExecutablePath"],
        capture_output=True, text=True, timeout=30)
    parent = out.stdout.strip()
except Exception as exc:  # noqa: BLE001
    parent = f"? {exc}"

print("sys.executable      :", sys.executable)
print("sys._base_executable:", getattr(sys, "_base_executable", None))
print("__PYVENV_LAUNCHER__ :", os.environ.get("__PYVENV_LAUNCHER__"))
print("pid / ppid          :", os.getpid(), "/", ppid, "->", parent)
print("IsProcessInJob      :", bool(in_job.value))
print("QueryInformationJob :", "ok" if ok else f"lỗi {ctypes.get_last_error()}",
      "LimitFlags=0x%X" % flags if flags is not None else "", names)
print("GetErrorMode        : 0x%X (SEM_FAILCRITICALERRORS=1, SEM_NOGPFAULTERRORBOX=2, SEM_NOOPENFILEERRORBOX=0x8000)" % em)
