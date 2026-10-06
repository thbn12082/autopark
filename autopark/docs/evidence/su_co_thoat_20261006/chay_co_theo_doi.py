"""Chạy một lệnh dài (LD-1, bộ test đầy đủ) có theo dõi để biết VÌ SAO nó thoát — Việc 8, viết 06/10/2026.

Bản trong repo (06/10/2026), sửa theo phản biện so với bản nháp đã dùng cho các lượt 06/10/2026:
- --het-gio S: quá S giây thì taskkill /T /F cả cây tiến trình của lệnh, ghi "HẾT GIỜ" và mã vào tom_tat.json
  (--toi-da chỉ là thời gian của bộ theo dõi, không giới hạn lệnh);
- chép mọi dump mới của thư mục dump (mặc định %LOCALAPPDATA%\\CrashDumps) vào <ra>/dump/ ngay sau khi lệnh thoát
  (DumpCount mặc định 10: dump mới đẩy dump cũ nhất ra);
- chỉ quét bản ghi phiên Claude tìm lệnh giết khi mã >= 0xC0000000 (crash, hay 0xFFFFFFFF = bị giết), và chỉ ghi
  nguyên câu lệnh nhắm PID đang canh (tim_lenh_giet.py --pid); lệnh giết python theo tên chỉ ghi giờ và loại lệnh:
  không ghi lệnh của dự án khác;
- tìm báo cáo WER mới ở cả ReportArchive lẫn ReportQueue.

Vì sao cần (điều tra 06/10/2026 hai kiểu thoát bất thường; docs/CHUYEN_MAY_BAN.md mục 16):
1. Git Bash chỉ cho $? 8 bit: mọi NTSTATUS >= 0xC0000000 thành 127, trừ 0xC0000005 -> 139, 0xC0000017 -> 138,
   0xC000001D -> 132, 0xC000013A -> 130; Stop-Process -Force (mã 0xFFFFFFFF) cũng thành 127 (đo 06/10/2026).
2. Tiến trình mở từ Git Bash mang ErrorMode SEM_NOGPFAULTERRORBOX (0x3) nên Windows Error Reporting KHÔNG ghi sự kiện
   1000/1001 và KHÔNG ghi minidump; mở từ PowerShell thì 0x8001 và WER ghi đủ.
3. Không ghi PID nên không biết tiến trình nào là của mình (02/10/2026 một phiên tác tử khác dừng nhầm theo PID).

Script này (một tiến trình, chỉ chờ, gần như không tốn CPU):
- tự đặt ErrorMode 0x8001 (SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX, như PowerShell) rồi mới mở lệnh; con thừa
  hưởng, nên crash có sự kiện Application Error 1000 và minidump (LocalDumps bật sẵn trên máy bàn; KHÔNG sửa registry,
  không cần quyền quản trị);
- ghi <ra>/pids.txt (launcher=, python=), đầu ra của lệnh (stdout + stderr) vào <ra>/dau_ra.txt, mở handle tới python
  gốc để đọc mã thoát 32 bit và giờ thoát của chính nó;
- --theo-doi: chạy theo_doi_mo_rong.ps1 (cùng thư mục) canh hai PID đó;
- khi xong: mã thoát hex + nghĩa + "$? Git Bash sẽ báo"; dump mới (chép vào <ra>/dump/); sự kiện WER mới; báo cáo WER
  mới; lệnh giết nhắm PID của mình (nếu mã >= 0xC0000000); tất cả vào <ra>/tom_tat.json;
- tự thoát bằng ĐÚNG mã 32 bit của lệnh (PowerShell thấy đủ; Git Bash thấy như bảng ở trên).

Dùng (từ thư mục autopark của repo; mọi thứ sau -- là lệnh):
  .venv/Scripts/python.exe -X utf8 docs/evidence/su_co_thoat_20261006/chay_co_theo_doi.py --ra <thư mục kết quả> \\
      --het-gio 2400 --theo-doi -- .venv-train/Scripts/python.exe -X utf8 -X faulthandler -m autopark.rig.bench ...
Để <ra> ngoài git (runs/ hay thư mục tạm): dau_ra.txt, dump/, lenh_giet.txt, theo_doi/python.csv và theo_doi/gpu_app.csv
có thể chứa đường dẫn riêng của máy hay dòng lệnh, tên của tiến trình khác; KHÔNG chép lenh_giet.txt, python.csv,
gpu_app.csv vào docs/evidence; tệp khác chỉ chép bản đã lọc.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
k32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
k32.SetErrorMode.restype = wt.UINT
k32.SetErrorMode.argtypes = [wt.UINT]
k32.GetErrorMode.restype = wt.UINT
k32.ExitProcess.argtypes = [wt.UINT]
k32.CloseHandle.argtypes = [wt.HANDLE]

SEM_FAILCRITICALERRORS, SEM_NOGPFAULTERRORBOX, SEM_NOOPENFILEERRORBOX = 0x1, 0x2, 0x8000
PROCESS_QUERY_LIMITED_INFORMATION, SYNCHRONIZE = 0x1000, 0x100000
TH32CS_SNAPPROCESS = 0x2


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]

NGHIA = {
    0x00000000: "thoát bình thường",
    0x00000001: "lỗi thường (Python có traceback; hoặc taskkill /F, Popen.kill())",
    0x00000002: "lỗi dòng lệnh (argparse)",
    0x00000003: "abort() kiểu cũ của CRT",
    0xFFFFFFFF: "BỊ GIẾT bằng TerminateProcess(-1): Stop-Process -Force / .NET Process.Kill()",
    0xC0000005: "ACCESS VIOLATION",
    0xC0000409: "fail-fast: __fastfail / abort() của UCRT / kiểm /GS",
    0xC0000374: "HEAP CORRUPTION",
    0xC00000FD: "STACK OVERFLOW",
    0xC0000017: "STATUS_NO_MEMORY",
    0xC000012D: "STATUS_COMMITMENT_LIMIT (hết commit)",
    0xC000007F: "STATUS_DISK_FULL",
    0xC000001D: "ILLEGAL INSTRUCTION",
    0xC000013A: "Ctrl+C / đóng console",
    0xE06D7363: "ngoại lệ C++ không bắt",
    0xC06D007F: "delay-load: không thấy hàm trong DLL",
    0x40010004: "DBG_TERMINATE_PROCESS (trình gỡ lỗi giết)",
}
# đo 06/10/2026 (bang_ma_thoat.sh, Git Bash 5.3.15 / MSYS 3.6.9): NTSTATUS lỗi -> tín hiệu, còn lại -> 127
GIT_BASH_TIN_HIEU = {0xC0000005: 139, 0xC0000017: 138, 0xC000001D: 132, 0xC000013A: 130}


def ma_git_bash(code: int) -> int:
    code &= 0xFFFFFFFF
    if code >= 0xC0000000:
        return GIT_BASH_TIN_HIEU.get(code, 127)
    return code & 0xFF


def nghia(code: int) -> str:
    code &= 0xFFFFFFFF
    if code in NGHIA:
        return NGHIA[code]
    return "NTSTATUS lỗi khác" if code >= 0xC0000000 else f"mã thường {code}"


def tien_trinh_con(pid_cha: int) -> list[tuple[int, str]]:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    out = []
    e = PROCESSENTRY32W()
    e.dwSize = ctypes.sizeof(e)
    ok = k32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        if e.th32ParentProcessID == pid_cha:
            out.append((e.th32ProcessID, e.szExeFile))
        ok = k32.Process32NextW(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return out


def ft_sang_gio(ft: wt.FILETIME) -> str | None:
    v = (ft.dwHighDateTime << 32) | ft.dwLowDateTime
    if not v:
        return None
    t = dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(microseconds=v // 10)
    return t.astimezone().isoformat(timespec="milliseconds")


def ma_va_gio(h) -> tuple[int | None, str | None]:
    code = wt.DWORD()
    if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
        return None, None
    c, e, k, u = wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
    k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u))
    return code.value, ft_sang_gio(e)


def ds_moi(thu_muc: Path, tu: float) -> list[str]:
    if not thu_muc.is_dir():
        return []
    try:
        return sorted(f"{p.name} ({p.stat().st_size} B, {dt.datetime.fromtimestamp(p.stat().st_mtime):%H:%M:%S})"
                      for p in thu_muc.iterdir() if p.stat().st_mtime >= tu)
    except OSError as exc:
        return [f"không đọc được {thu_muc.name}: {exc}"]


def anh_chup(thu_muc: Path) -> dict[str, tuple[int, float]]:
    """Tên -> (cỡ, mtime) của các tệp trong thư mục dump, chụp TRƯỚC khi mở lệnh."""
    try:
        return {p.name: (p.stat().st_size, p.stat().st_mtime) for p in thu_muc.iterdir() if p.is_file()}
    except OSError:
        return {}


def chep_dump_moi(thu_muc: Path, truoc: dict[str, tuple[int, float]], dich: Path, da_chep: set[str]) -> list[str]:
    """Chép các tệp mới (hay đổi) so với ảnh chụp trước khi chạy vào <ra>/dump/; trả danh sách đã chép lần này."""
    out = []
    for ten, (co, mtime) in sorted(anh_chup(thu_muc).items()):
        if ten in da_chep or truoc.get(ten) == (co, mtime):
            continue
        try:
            dich.mkdir(parents=True, exist_ok=True)
            shutil.copy2(thu_muc / ten, dich / ten)
            da_chep.add(ten)
            out.append(f"{ten} ({co} B, {dt.datetime.fromtimestamp(mtime):%H:%M:%S}) -> dump/{ten}")
        except OSError as exc:
            out.append(f"{ten}: không chép được: {exc}")
    return out


def su_kien_wer(tu_utc: dt.datetime) -> str:
    ps = ("$s=[datetime]::Parse('%s').ToLocalTime(); Get-WinEvent -FilterHashtable @{LogName='Application'; "
          "ProviderName='Application Error','Windows Error Reporting','Application Hang'; StartTime=$s} "
          "-ErrorAction SilentlyContinue | Sort-Object TimeCreated | ForEach-Object { '{0:HH:mm:ss} {1} id={2}: {3}' "
          "-f $_.TimeCreated, $_.ProviderName, $_.Id, "
          "(($_.Message -replace '\\s+',' ') -replace '^(.{0,400}).*','$1') }"
          % tu_utc.isoformat())
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        return r.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"không đọc được log: {exc}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ra", type=Path, required=True, help="thư mục kết quả (tạo nếu chưa có)")
    ap.add_argument("--het-gio", type=float, default=0.0,
                    help="hạn giờ của lệnh, giây (0 = không hạn); quá hạn thì taskkill /T /F cả cây tiến trình")
    ap.add_argument("--theo-doi", action="store_true", help="chạy theo_doi_mo_rong.ps1 canh PID của lệnh")
    ap.add_argument("--khoang", type=int, default=10, help="chu kỳ theo dõi, giây")
    ap.add_argument("--toi-da", type=int, default=0,
                    help="thời gian theo dõi tối đa, giây (0 = --het-gio + 120, hoặc 7200 nếu không có hạn giờ); "
                         "KHÔNG giới hạn lệnh")
    ap.add_argument("--cho-wer", type=float, default=20.0,
                    help="khi mã là crash (>= 0xC0000000, trừ 0xFFFFFFFF): chờ WER ghi xong rồi mới đọc log, giây")
    ap.add_argument("--thu-muc-dump", type=Path,
                    default=Path(os.environ.get("LOCALAPPDATA", "")) / "CrashDumps",
                    help="thư mục minidump của WER (LocalDumps; mặc định %%LOCALAPPDATA%%\\CrashDumps)")
    ap.add_argument("--env", action="append", default=[], help="KEY=VAL thêm vào môi trường của lệnh")
    ap.add_argument("--giu-error-mode", action="store_true", help="KHÔNG đổi ErrorMode (để đối chứng)")
    ap.add_argument("lenh", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    lenh = a.lenh[1:] if a.lenh and a.lenh[0] == "--" else a.lenh
    if not lenh:
        ap.error("thiếu lệnh sau --")
    if Path(lenh[0]).exists():                 # CreateProcess không tìm được đường tương đối kiểu ".venv/Scripts/…"
        lenh[0] = os.path.normpath(str(Path(lenh[0]).resolve()))
    a.ra.mkdir(parents=True, exist_ok=True)
    em_cu = k32.GetErrorMode()
    if not a.giu_error_mode:
        k32.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX)
    env = os.environ.copy()
    for kv in a.env:
        k, _, v = kv.partition("=")
        env[k] = v
    dumps = a.thu_muc_dump
    wer_dirs = [Path(r"C:/ProgramData/Microsoft/Windows/WER") / x for x in ("ReportArchive", "ReportQueue")]
    wer_dirs += [Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/WER" / x
                 for x in ("ReportArchive", "ReportQueue")]
    dump_truoc = anh_chup(dumps)
    da_chep: set[str] = set()
    t0 = time.time()
    t0_utc = dt.datetime.now(dt.timezone.utc)
    log = open(a.ra / "dau_ra.txt", "wb")
    log.write(f"# {dt.datetime.now():%d/%m/%Y %H:%M:%S} cwd={os.getcwd()}\n# lệnh: {lenh}\n".encode("utf-8"))
    log.flush()
    p = subprocess.Popen(lenh, stdout=log, stderr=subprocess.STDOUT, env=env)
    con, ten_con = p.pid, None
    for _ in range(300):                                   # venv launcher mở python gốc ngay; chờ tối đa 30 s
        ds = [x for x in tien_trinh_con(p.pid) if x[1].lower().startswith("python")]
        if ds:
            con, ten_con = ds[0]
            break
        if p.poll() is not None:
            break
        time.sleep(0.1)
    h_con = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, con) if con != p.pid else None
    (a.ra / "pids.txt").write_text(f"launcher={p.pid}\npython={con}\n", encoding="utf-8")
    print(f"đã chạy: launcher pid {p.pid}, python gốc pid {con} ({ten_con or 'chính nó'}); ErrorMode cũ 0x{em_cu:X} -> "
          f"0x{k32.GetErrorMode():X}; hạn giờ {a.het_gio:g} s" + (" (không hạn)" if a.het_gio <= 0 else ""),
          flush=True)
    mon = None
    if a.theo_doi:
        toi_da = a.toi_da or (int(a.het_gio) + 120 if a.het_gio > 0 else 7200)
        mon = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                str(HERE / "theo_doi_mo_rong.ps1"), "-Ra", str(a.ra / "theo_doi"),
                                "-Giay", str(toi_da), "-Khoang", str(a.khoang), "-CanhPidFile",
                                str(a.ra / "pids.txt"), "-DungKhiHetCanh"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    het_gio = None
    try:
        rc = p.wait(timeout=a.het_gio if a.het_gio > 0 else None)
    except subprocess.TimeoutExpired:
        luc = dt.datetime.now()
        print(f"HẾT GIỜ sau {a.het_gio:g} s: taskkill /T /F /PID {p.pid}", flush=True)
        r = subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, text=True,
                           errors="replace")
        het_gio = {"trang_thai": "HẾT GIỜ", "giay": a.het_gio, "luc": luc.isoformat(timespec="seconds"),
                   "taskkill": " ".join((r.stdout + r.stderr).split())[:500], "taskkill_ma": r.returncode}
        try:
            rc = p.wait(timeout=60)
        except subprocess.TimeoutExpired:               # không giết được: ghi lại, vẫn đọc tiếp những gì đọc được
            het_gio["trang_thai"] = "HẾT GIỜ, taskkill không dừng được lệnh sau 60 s"
            rc = 0xFFFFFFFF
    rc &= 0xFFFFFFFF
    if het_gio is not None:
        trang_thai_gio = het_gio
    elif a.het_gio > 0:
        trang_thai_gio = f"không (hạn {a.het_gio:g} s)"
    else:
        trang_thai_gio = "không đặt hạn giờ"
    t1_utc = dt.datetime.now(dt.timezone.utc)
    log.close()
    dump_chep = chep_dump_moi(dumps, dump_truoc, a.ra / "dump", da_chep)        # ngay sau khi lệnh thoát
    ma_con, gio_con = (ma_va_gio(h_con) if h_con else (None, None))
    ma_xet = [c for c in (rc, ma_con) if c is not None]
    if any(c >= 0xC0000000 and c != 0xFFFFFFFF for c in ma_xet) and a.cho_wer > 0:
        print(f"mã crash: chờ WER {a.cho_wer:g} s", flush=True)
        time.sleep(a.cho_wer)
        dump_chep += chep_dump_moi(dumps, dump_truoc, a.ra / "dump", da_chep)   # dump ghi muộn (nếu có)
    tom = {
        "lenh": lenh, "cwd": os.getcwd(), "bat_dau": t0_utc.astimezone().isoformat(timespec="seconds"),
        "ket_thuc": t1_utc.astimezone().isoformat(timespec="seconds"), "error_mode_con": "0x%X" % k32.GetErrorMode(),
        "het_gio": trang_thai_gio,
        "pid_launcher": p.pid, "pid_python": con,
        "ma_launcher": "0x%08X" % rc, "nghia_launcher": nghia(rc), "git_bash_se_bao": ma_git_bash(rc),
        "ma_python": None if ma_con is None else "0x%08X" % ma_con,
        "nghia_python": None if ma_con is None else nghia(ma_con), "gio_thoat_python": gio_con,
        "su_kien_wer": su_kien_wer(t0_utc - dt.timedelta(seconds=5)).splitlines(),
        "dump_moi_da_chep": dump_chep, "bao_cao_wer_moi": [f"{d.parent.name}/{d.name}: {x}" for d in wer_dirs
                                                            for x in ds_moi(d, t0)],
    }
    if het_gio is None and any(c >= 0xC0000000 for c in ma_xet):
        pid_canh = sorted({p.pid, con})
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", str(HERE / "tim_lenh_giet.py"),
                                (t0_utc - dt.timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S"),
                                (t1_utc + dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")]
                               + [x for pid in pid_canh for x in ("--pid", str(pid))],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
            (a.ra / "lenh_giet.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
            tom["lenh_giet"] = (r.stdout + r.stderr).splitlines()[:40]
        except Exception as exc:  # noqa: BLE001
            tom["lenh_giet"] = [f"không quét được: {exc}"]
    (a.ra / "tom_tat.json").write_text(json.dumps(tom, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"thoát: launcher 0x{rc:08X} ({nghia(rc)}; Git Bash sẽ báo {ma_git_bash(rc)}), python gốc "
          f"{'?' if ma_con is None else '0x%08X' % ma_con} lúc {gio_con}"
          f"{'; HẾT GIỜ' if het_gio else ''}; sự kiện WER {len(tom['su_kien_wer'])}, dump mới đã chép "
          f"{len(dump_chep)}; xem {a.ra / 'tom_tat.json'}", flush=True)
    if mon is not None and mon.poll() is None:
        print("theo dõi vẫn chạy thêm ≈ 15 s rồi tự dừng (-DungKhiHetCanh)", flush=True)
    sys.stdout.flush()
    k32.ExitProcess(rc)


if __name__ == "__main__":
    main()
