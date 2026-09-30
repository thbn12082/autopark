"""Chạy riêng ca uturn_w46 (như tests/test_planner_hard_cases.py) N lần, in trạng thái và thời gian.
Tham số: <default|noeco> <N>. noeco = tắt EcoQoS cho chính tiến trình này trước khi đo."""
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(r"D:\xetulai\autopark\autopark")
sys.path.insert(0, str(ROOT))

from autopark.evaluation.bench import run_case  # noqa: E402
from autopark.evaluation.hard_cases import build_cases  # noqa: E402
from autopark.planning import portfolio  # noqa: E402
from autopark.storage.scenario_store import load_vehicle_config  # noqa: E402

mode, n = sys.argv[1], int(sys.argv[2])
if mode == "noeco":
    class PPTS(ctypes.Structure):
        _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    s = PPTS(1, 1, 0)
    print("SetProcessInformation:", bool(k.SetProcessInformation(k.GetCurrentProcess(), 4, ctypes.byref(s), ctypes.sizeof(s))))

cfg = load_vehicle_config(ROOT / "configs" / "vehicle_default.json")
cases = build_cases(cfg)
for i in range(n):
    r = run_case(portfolio.plan, cases["uturn_w46"], cfg, time_limit=8.0)
    print(f"{time.strftime('%H:%M:%S')} {mode} #{i}: {r.status} elapsed={r.elapsed:.2f}s cusps={r.cusps}", flush=True)
