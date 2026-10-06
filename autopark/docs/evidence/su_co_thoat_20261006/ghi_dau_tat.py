"""Plugin pytest tạm (Việc 8, 06/10/2026): khoanh vùng chỗ tiến trình pytest chết LÚC TẮT (lượt .venv 02/10/2026 thoát
139 và lượt 06/10/2026 thoát 0xC0000005, cả hai sau khi chạy hết test).

Dùng: thêm thư mục chứa tệp này vào PYTHONPATH và gọi pytest với `-p ghi_dau_tat`. Biến môi trường:
- GHI_DAU_TAT: tệp dấu (mặc định ghi_dau_tat.txt ở thư mục hiện hành); dump faulthandler ở
  GHI_DAU_TAT + ".faulthandler.txt";
- GHI_DAU_TAT_DEM_WIDGET: "1" (mặc định) đếm widget Qt ở phien_xong và unconfigure; "phien_xong" chỉ đếm ở phien_xong;
  "0" không đếm. Đếm gọi QApplication.allWidgets(), tức tạo wrapper Python cho mọi widget còn sống (lượt 06/10/2026:
  47 028 widget) ngay trước pha tắt, nên làm đổi điều kiện so với hai lần crash; tắt đi khi muốn giữ điều kiện gần nhất;
- GHI_DAU_TAT_HANG_S: > 0 thì faulthandler in traceback mọi luồng nếu pha tắt treo quá số giây này.

Thứ tự lúc tắt (bản trong repo, sửa theo phản biện 06/10/2026; pytest 9.1.1, Python 3.12):
1. pytest_sessionfinish (dấu phien_xong; JUnit được ghi ở đây);
2. pytest_unconfigure, gọi theo thứ tự ngược lúc đăng ký: plugin faulthandler của pytest TẮT faulthandler trước (chỉ bật
   lại ra stderr nếu có -X faulthandler), rồi unraisableexception gọi gc.collect() toàn phần
   (unraisableexception.py:172), các plugin khác, cuối cùng hook trylast của plugin này (dấu unconfigure; bật lại
   faulthandler ra tệp riêng);
3. dọn "cleanup stack" của config: gc.collect() toàn phần lần nữa (unraisableexception.py:99), teardown capture, đường
   ra của pytest;
4. Py_FinalizeEx: threading._shutdown (dấu thread_atexit_dau là việc ĐẦU TIÊN của nó; rồi _python_exit của
   concurrent.futures, chờ luồng không daemon) -> atexit LIFO (dấu atexit_dau; multiprocessing.util._exit_function,
   PySide6.QtCore.__moduleShutdown = hủy QApplication và mọi QObject còn sống, logging.shutdown; dấu atexit_cuoi) ->
   dọn module -> DLL_PROCESS_DETACH.
Không có -X faulthandler thì từ bước 2 trở đi faulthandler đã tắt (thí nghiệm thu_thu_tu/), nên crash ở đó không in gì.

Đọc DẤU CUỐI CÙNG trong tệp dấu (ghi bằng os.write, không đệm):
- phien_xong      -> chết trong pytest_unconfigure của plugin khác (gồm gc.collect() lần 1); traceback (nếu có
                     -X faulthandler) nằm trong đầu ra của lệnh (fd 2, dau_ra.txt của chay_co_theo_doi.py);
- unconfigure     -> chết trong cleanup stack (gc.collect() lần 2, teardown capture) hay đường ra của pytest;
- thread_atexit_dau -> chết trong threading._shutdown;
- atexit_dau      -> chết trong atexit (PySide6.__moduleShutdown, multiprocessing);
- atexit_cuoi     -> chết lúc dọn module hay DLL detach (hoặc thoát bình thường: xem mã thoát).
Từ dấu unconfigure trở đi traceback nằm ở <GHI_DAU_TAT>.faulthandler.txt. Cũng ghi số luồng Python, số luồng hệ điều
hành của tiến trình, số widget Qt còn sống, DLL lạ nạp trong tiến trình. Không đổi kết quả test, không mở thiết bị.
"""
import atexit
import ctypes
import ctypes.wintypes as wt
import faulthandler
import os
import sys
import threading
import time

import pytest

_PATH = os.environ.get("GHI_DAU_TAT", "ghi_dau_tat.txt")
_FD = os.open(_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0))
_FH_FILE = None
_HANG_S = float(os.environ.get("GHI_DAU_TAT_HANG_S", "0") or 0)
_DEM_WIDGET = (os.environ.get("GHI_DAU_TAT_DEM_WIDGET", "1") or "1").strip().lower()


def _so_luong_he_dieu_hanh() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        k32 = ctypes.WinDLL("kernel32")
        k32.CreateToolhelp32Snapshot.restype = wt.HANDLE

        class TE32(ctypes.Structure):
            _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                        ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", ctypes.c_long),
                        ("tpDeltaPri", ctypes.c_long), ("dwFlags", wt.DWORD)]
        snap = k32.CreateToolhelp32Snapshot(0x4, 0)
        e = TE32()
        e.dwSize = ctypes.sizeof(e)
        n, pid = 0, os.getpid()
        ok = k32.Thread32First(snap, ctypes.byref(e))
        while ok:
            n += e.th32OwnerProcessID == pid
            ok = k32.Thread32Next(snap, ctypes.byref(e))
        k32.CloseHandle(snap)
        return n
    except Exception:  # noqa: BLE001
        return None


def _module_la() -> str:
    """DLL nạp trong tiến trình mà không thuộc Windows/Python/site-packages (DLL bị chèn: hook của UltraViewer
    uvh64.dll thấy trong dump 02/10/2026 00:27, phần mềm bảo mật, overlay…)."""
    if sys.platform != "win32":
        return ""
    try:
        psapi = ctypes.WinDLL("psapi")
        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentProcess.restype = wt.HANDLE
        psapi.EnumProcessModules.argtypes = [wt.HANDLE, ctypes.POINTER(wt.HMODULE), wt.DWORD, ctypes.POINTER(wt.DWORD)]
        psapi.GetModuleFileNameExW.argtypes = [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD]
        h = k32.GetCurrentProcess()
        arr = (wt.HMODULE * 2048)()
        need = wt.DWORD()
        psapi.EnumProcessModules(h, arr, ctypes.sizeof(arr), ctypes.byref(need))
        out = []
        buf = ctypes.create_unicode_buffer(1024)
        for m in arr[: need.value // ctypes.sizeof(wt.HMODULE)]:
            psapi.GetModuleFileNameExW(h, wt.HMODULE(m), buf, 1024)
            low = buf.value.lower()
            if "\\windows\\" not in low and "python312" not in low and "site-packages" not in low:
                out.append(buf.value)
        return "module_la=" + ";".join(out)
    except Exception as exc:  # noqa: BLE001
        return f"module_la=? {exc}"


def _qt(moc: str) -> str:
    if "PySide6.QtWidgets" not in sys.modules:
        return "Qt chưa nạp"
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return "không có QApplication"
        if _DEM_WIDGET == "0" or (_DEM_WIDGET == "phien_xong" and moc != "phien_xong"):
            return f"QApplication còn; không đếm widget (GHI_DAU_TAT_DEM_WIDGET={_DEM_WIDGET})"
        return f"QApplication còn; top-level {len(app.topLevelWidgets())}, mọi widget {len(app.allWidgets())}"
    except Exception as exc:  # noqa: BLE001
        return f"không đọc được Qt: {exc}"


def _dau(nhan: str, chi_tiet: str = "") -> None:
    try:
        luong = [f"{t.name}{'(d)' if t.daemon else ''}" for t in threading.enumerate()]
        dong = (f"{time.strftime('%H:%M:%S')} {time.perf_counter():.3f} pid={os.getpid()} {nhan} "
                f"luong_py={len(luong)} {luong} luong_os={_so_luong_he_dieu_hanh()} {chi_tiet}\n")
        os.write(_FD, dong.encode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 - dấu không được làm hỏng lúc tắt
        pass


# đăng ký SỚM (lúc nạp plugin, trước khi test nạp PySide6) -> chạy MUỘN NHẤT trong atexit (LIFO)
atexit.register(_dau, "atexit_cuoi", "(sau PySide6.__moduleShutdown, multiprocessing._exit_function)")
_dau("nap_plugin", f"python {sys.version.split()[0]} argv={sys.argv[1:]} dem_widget={_DEM_WIDGET}")


def pytest_sessionfinish(session, exitstatus):
    _dau("phien_xong", f"exitstatus={int(exitstatus)} hong={session.testsfailed} so_test={session.testscollected} "
                       f"{_qt('phien_xong')}")


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    global _FH_FILE
    # chạy SAU pytest_unconfigure của plugin faulthandler (nó đã tắt faulthandler) và của unraisableexception
    # (gc.collect lần 1): bật lại faulthandler, ghi vào tệp riêng
    try:
        _FH_FILE = open(_PATH + ".faulthandler.txt", "a", encoding="utf-8")
        faulthandler.enable(file=_FH_FILE, all_threads=True)
        if _HANG_S > 0:
            faulthandler.dump_traceback_later(_HANG_S, repeat=False, file=_FH_FILE, exit=False)
    except Exception as exc:  # noqa: BLE001
        _dau("loi_bat_faulthandler", repr(exc))
    threading._register_atexit(_dau, "thread_atexit_dau", "(việc đầu của threading._shutdown)")
    atexit.register(_dau, "atexit_dau", "(trước PySide6.__moduleShutdown)")   # đăng ký MUỘN -> chạy SỚM nhất
    _dau("unconfigure", _qt("unconfigure") + " " + _module_la())
