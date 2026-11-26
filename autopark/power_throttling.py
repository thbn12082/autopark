"""Tắt EcoQoS (power throttling của Windows 11) cho một tiến trình (thêm 30/09/2026).

Windows 11 tự quyết EcoQoS cho từng tiến trình: tiến trình không có cửa sổ hiện (ví dụ pytest mở từ một shell chạy nền)
có thể bị dồn sang lõi E hay hạ xung dù máy rảnh. Đo 30/09/2026 trên máy bàn (i9-14900), nhóm test `planner_budget` mở
từ shell không cửa sổ: để Windows tự quyết thì 2/2 lượt có test hỏng (1 và 3 test, ví dụ `uturn_w46` hết hạn 8 s), tổng
thời gian 55 s và 103 s; tiến trình tự tắt EcoQoS thì 2/2 lượt đạt 15/15, 36 s và 40 s (docs/VAN_HANH.md).

Dùng ở: QEMU của bo ảo (`transport/qemu_board.py`, tắt theo pid), công cụ đo `evaluation/ecoqos_gui.py` (đọc trạng
thái, tắt theo pid cho biến thể đối chứng) và, qua `apply_ecoqos_policy`, chính tiến trình pytest (`tests/conftest.py`)
cùng mọi ứng dụng và công cụ có hành vi thời gian thực.

Từ 02/10/2026 (người dùng giao quyết định 02/10/2026, theo đề xuất ở docs/VAN_HANH.md): `main()` của mỗi
điểm vào mở thiết bị chạy liên tục (camera, LiDAR, cổng serial, bo ảo), chạy theo hạn giờ đồng hồ thật (hạn lập đường,
hạn dữ liệu cũ, vòng điều khiển) hay ghi số đo thời gian để so với ngân sách thời gian thực gọi
`apply_ecoqos_policy("<tên>")` NGAY ĐẦU, trước khi đọc dòng lệnh: tắt EcoQoS cho CHÍNH tiến trình đó. Đặt biến môi
trường AUTOPARK_KEEP_ECOQOS=1 (đúng giá trị "1") để giữ mặc định của Windows; cùng một biến cho pytest, ứng dụng và
công cụ, không có tham số dòng lệnh. Nơi ghi kết quả đọc lại `ecoqos_state()` lúc ghi (khóa "ecoqos": off / system /
on / unknown). Hàm `build_window` của giao diện KHÔNG gọi nó: biến thể gui_system của `evaluation/ecoqos_gui.py` dựng
cửa sổ qua đó. Tiến trình con không thừa hưởng trạng thái: QEMU vẫn do `QemuBoard(boost=True)` tắt theo pid (biến môi
trường không áp vào đó), tiến trình con của `--workers` tự gọi qua `initializer`.

Chỉ có tác dụng trên Windows; nơi khác các hàm trả False / None / "unknown" và không làm gì.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import sys

KEEP_ECOQOS_ENV = "AUTOPARK_KEEP_ECOQOS"     # "1" = giữ mặc định của Windows (không tắt EcoQoS); giá trị khác = tắt

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


# ------------------------------------------------- chính sách cho chính tiến trình đang chạy (thêm 02/10/2026)

_ECOQOS_WHY = ("EcoQoS là chế độ tiết kiệm điện của Windows 11: Windows có thể dồn tiến trình sang lõi tiết kiệm hay "
               "hạ xung khi cửa sổ bị thu nhỏ. Đo 02/10/2026 trên máy bàn: để Windows tự quyết thì cửa sổ thu nhỏ làm "
               "lập đường uturn_w46 hết hạn 8 s ở 4/4 lượt; tiến trình tự tắt EcoQoS thì 4/4 đạt "
               "(docs/VAN_HANH.md).")
_DONT_MINIMIZE = " Đừng thu nhỏ cửa sổ khi đang lập đường hay đang chạy."


def keep_ecoqos_requested() -> bool:
    """True khi người dùng muốn giữ mặc định của Windows: biến môi trường AUTOPARK_KEEP_ECOQOS đúng bằng "1" (cùng quy
    tắc với tests/conftest.py; "0", "", "true", " 1"… đều là tắt EcoQoS)."""
    return os.environ.get(KEEP_ECOQOS_ENV) == "1"


def ecoqos_state(pid: int | None = None) -> str:
    """Trạng thái EcoQoS để ghi vào tệp kết quả, đọc ngay lúc gọi: "off", "system", "on" như
    `execution_speed_throttling`, hoặc "unknown" khi không đọc được (cùng tập giá trị với thuộc tính `ecoqos` của tệp
    JUnit). Không bao giờ ném Exception."""
    try:
        return execution_speed_throttling(pid) or "unknown"
    except Exception:  # noqa: BLE001 - chỉ để ghi lại, không được làm hỏng tiến trình gọi
        return "unknown"


@dataclass(frozen=True)
class EcoQoSPolicy:
    """Kết quả `apply_ecoqos_policy` cho tiến trình đang chạy.

    `request`: "disable" (đã yêu cầu tắt) hay "keep" (AUTOPARK_KEEP_ECOQOS=1); `set_ok`: SetProcessInformation có nhận
    không (None khi "keep"); `state`: đọc lại ngay sau đó (off / system / on / unknown); `windows`: có phải Windows."""

    component: str
    request: str
    set_ok: bool | None
    state: str
    windows: bool

    @property
    def level(self) -> str:
        """Mức báo: "ok" (đã tắt), "warn" (giữ mặc định theo biến môi trường), "danger" (yêu cầu tắt mà Windows không
        nhận), "info" (không phải Windows, hoặc đã tắt mà không đọc lại được: Windows trước bản 22000)."""
        if self.state == "off":
            return "ok"
        if self.request == "keep":
            return "warn"
        if not self.windows:
            return "info"
        if self.state in ("system", "on") or self.set_ok is False:
            return "danger"
        return "info"

    def short_vi(self) -> str:
        """Chữ ngắn cho nhãn ở thanh trạng thái."""
        level = self.level
        if level == "ok":
            return "EcoQoS: tắt"
        if level == "warn":
            return f"EcoQoS: Windows tự quyết ({KEEP_ECOQOS_ENV}=1)"
        if level == "danger":
            return f"EcoQoS: KHÔNG tắt được (Windows báo: {self.state})"
        if self.windows:
            return "EcoQoS: đã yêu cầu tắt (không đọc lại được)"
        return "EcoQoS: không áp dụng (không phải Windows)"

    def explain_vi(self) -> str:
        """Chú thích (tooltip) của nhãn: vì sao tắt, số đo, cách giữ mặc định của Windows."""
        level = self.level
        if level == "ok":
            tail = (" Ứng dụng đã tự tắt EcoQoS cho tiến trình này lúc khởi động. Muốn giữ mặc định của Windows (chỉ "
                    f"để đo đúng điều kiện đó): đặt biến môi trường {KEEP_ECOQOS_ENV}=1 trước khi chạy.")
        elif level == "warn":
            tail = f" Đang giữ mặc định của Windows vì {KEEP_ECOQOS_ENV}=1." + _DONT_MINIMIZE
        elif level == "danger":
            tail = f" Ứng dụng đã yêu cầu tắt nhưng Windows không nhận (đọc lại: {self.state})." + _DONT_MINIMIZE
        else:
            tail = (" Không đọc được trạng thái EcoQoS của tiến trình (Windows trước bản 22000, hoặc không phải "
                    "Windows).")
        return _ECOQOS_WHY + tail

    def cli_line(self) -> str:
        """Một dòng cho công cụ dòng lệnh; khi không tắt được thì bắt đầu bằng "CẢNH BÁO"."""
        level = self.level
        if level == "ok":
            return f"EcoQoS của tiến trình: off (đã tự tắt; {KEEP_ECOQOS_ENV}=1 để giữ mặc định của Windows)"
        if level == "warn":
            return f"EcoQoS của tiến trình: {self.state} (giữ mặc định của Windows theo {KEEP_ECOQOS_ENV}=1)"
        if level == "danger":
            return (f"CẢNH BÁO: không tắt được EcoQoS (Windows báo: {self.state}); số đo thời gian và hạn giờ có thể "
                    "hỏng khi cửa sổ bị thu nhỏ")
        return f"EcoQoS của tiến trình: {self.state} (không đọc được hoặc không phải Windows)"


def apply_ecoqos_policy(component: str) -> EcoQoSPolicy:
    """Áp chính sách EcoQoS cho CHÍNH tiến trình đang chạy (tiến trình con không thừa hưởng): tắt, trừ khi
    AUTOPARK_KEEP_ECOQOS=1, rồi đọc lại. `component`: tên điểm vào, vd. "ui.app", "rig.bench"
    (chỉ để gỡ lỗi, không ghi vào tệp nào).

    Không dùng Qt, không in gì (vài công cụ in đúng một dòng JSON ra stdout), không bao giờ ném Exception: không làm
    được thì `level` là "danger" và nơi gọi tự báo; không dừng chương trình. Gọi lại trong cùng tiến trình là vô hại
    (may_moi gọi rig.bench.main hai lần). Là hàm cấp mô-đun nên dùng được làm `initializer` của ProcessPoolExecutor.
    Tra `disable_power_throttling` / `execution_speed_throttling` theo tên mô-đun lúc gọi, nên test thay được lớp
    Win32."""
    keep = keep_ecoqos_requested()
    set_ok: bool | None = None
    if not keep:
        try:
            set_ok = bool(disable_power_throttling())
        except Exception:  # noqa: BLE001 - không được làm hỏng tiến trình gọi
            set_ok = False
    return EcoQoSPolicy(component, "keep" if keep else "disable", set_ok, ecoqos_state(), sys.platform == "win32")
