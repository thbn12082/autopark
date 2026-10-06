"""Đo EcoQoS của ứng dụng giao diện thật khi cửa sổ thường / thu nhỏ / bị che (thêm 02/10/2026).

Công cụ đo, không sửa ứng dụng. Vì sao: docs/CHUYEN_MAY_BAN.md mục 8 còn dòng "CHƯA ĐO: ứng dụng thật gọi bộ lập kế
hoạch có hạn giờ trong tiến trình giao diện"; ngày 30/09/2026 Windows 11 hạ tốc một tiến trình KHÔNG có cửa sổ tới mức
ca `uturn_w46` hết hạn 8 s.

Cách đo. Tiến trình điều khiển (`do`; không Qt, không cửa sổ) mở GIAO DIỆN THẬT trong một tiến trình con (`con`: đúng
như `run_app.py <kịch bản>`, thêm một đầu dò nhỏ). Trước mỗi lần lập đường nó đặt cửa sổ vào một trạng thái bằng Win32:
thường (hiện, đưa lên trước), thu nhỏ, bị che kín bởi một cửa sổ đục luôn-trên-cùng của tiến trình thứ ba (`che`); chờ
ổn định; đọc EcoQoS và mức ưu tiên của tiến trình giao diện, trạng thái phiên (khóa, ngắt kết nối, bàn làm việc nhận
nhập, màn hình, thời gian không ai thao tác, cửa sổ đang ở trước), tải CPU (toàn máy, theo lớp lõi P/E, CPU của chính
tiến trình); rồi bảo đầu dò gọi `MainWindow.plan()` (hàm nút "Tìm đường đỗ" gọi) và ghi một dòng. Hai đối chứng:
`gui_off` (cùng giao diện, tắt EcoQoS theo pid bằng `power_throttling.disable_power_throttling`) và `khong_cua_so`
(tiến trình con không cửa sổ `nen`, lập đường qua cùng `Session.plan_async`: điều kiện của 30/09). Từ 02/10/2026 ứng
dụng tự tắt EcoQoS lúc khởi động (`ui.app.main` gọi `power_throttling.apply_ecoqos_policy`): `gui_system` là giao diện
ở mặc định của Windows (ứng dụng trước ngày đó, hay chạy với AUTOPARK_KEEP_ECOQOS=1), `gui_off` là ứng dụng hiện nay.

Cửa sổ ở trước (cập nhật 02/10/2026). Windows xếp QoS theo cửa sổ ở trước (foreground) và chỉ cho tiến trình đang ở
trước (hoặc được nó cho phép) đổi cửa sổ ở trước. Tiến trình điều khiển chạy nền (mở từ shell), nên ở lượt đo 02/10/2026
02:54 mọi lần nó gọi SetForegroundWindow lên màn che đều bị từ chối và SW_MINIMIZE thường để giao diện (đã thu nhỏ) vẫn
ở trước: 15/16 lượt thu nhỏ / bị che bị loại `gui_van_o_truoc`. Nay mỗi lần đổi trạng thái có một cửa sổ đích phải ở
trước (`DICH_TRUOC`): thường → giao diện; thu nhỏ → cửa sổ trung tính nhỏ của tiến trình `che` (320×120, góc dưới
phải, như người dùng đang ở ứng dụng khác); bị che → màn che. Nếu cửa sổ đang ở trước thuộc tiến trình khác tiến trình
của cửa sổ đích, tiến trình đó (giao diện, hoặc `che`) gọi AllowSetForegroundWindow(ASFW_ANY) theo lệnh `cap_quyen`;
rồi chính tiến trình sở hữu cửa sổ đích gọi SetForegroundWindow lên cửa sổ đó (lệnh `len_truoc`); tiến trình điều khiển
đọc lại GetForegroundWindow. Cửa sổ đích lên trước TRƯỚC khi thu nhỏ giao diện hay ẩn cửa sổ đang ở trước, để Windows
không tự trao cửa sổ ở trước cho một ứng dụng bất kỳ (từ đó không tiến trình nào của công cụ cấp quyền được nữa). Kết
quả ghi vào `cap_quyen_truoc` và `ket_qua_dua_ra_truoc`; bước nào bị Windows từ chối thì dòng vẫn được ghi, còn lý do
loại `gui_van_o_truoc` (thu nhỏ / bị che mà giao diện vẫn ở trước lúc bấm) và `gui_khong_o_truoc` (thường mà giao diện
không ở trước lúc bấm) chặn mọi dòng sai trạng thái. Không giả lập phím, không AttachThreadInput, không đổi thiết lập.

Chạy trong thư mục `autopark` của repo, lúc máy rảnh và không ai dùng máy (mở cửa sổ thật ≈ 8 phút), mỗi lệnh một dòng:
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.ecoqos_gui do --ra docs\\evidence\\ecoqos_giao_dien_<ngày>
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.ecoqos_gui do --ra runs\\thu_ecoqos --ca pillar_at_slot_mouth --khoi 1 --lap 1 --cho 2
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.ecoqos_gui tom-tat --ra <thư mục đã đo>

Trong `--ra`: ket_qua.jsonl (một dòng mỗi lần lập đường, khóa theo thứ tự `COT`), may.json (máy, nguồn điện, mã, môi
trường), tom_tat.txt (bảng, kết luận), ca_<ca>.json (kịch bản đã dùng), powercfg_bo_xu_ly.txt, nhat_ky.txt. Không ghi
CSV: autopark/.gitignore bỏ qua *.csv trong thư mục con của docs/evidence.

An toàn: không giả lập phím/chuột, không chụp màn hình, không đổi kế hoạch nguồn / màn hình / khóa máy, không mở cổng
COM, camera hay LiDAR (ca mô phỏng thuần). Màn che và cửa sổ trung tính đóng ngay khi bấm Esc hoặc bấm chuột (các lượt
"bị che" còn lại thành BO_QUA, lượt "thu nhỏ" chỉ còn thu nhỏ) và tự đóng sau thời gian tối đa; giao diện và tiến trình
`che` tự thoát khi tiến trình điều khiển chết (hết stdin). Quyền ASFW_ANY tự mất ở lần nhấn phím / chuột kế tiếp.
Các ngưỡng của tóm tắt (`NGUONG_CHAM`, `NGUONG_NHIEU`, `TOI_THIEU_LUOT`, `TAI_NEN_CAO`) chỉ để mô tả, không phải ngưỡng
nghiệm thu.

Chế độ chạy (thêm 02/10/2026, lệnh `do-chay`, mã ở `evaluation/ecoqos_chay.py`): cùng cách đặt trạng thái cửa sổ, nhưng
mỗi lượt bấm "Bắt đầu đỗ" (`MainWindow.run()`) và ghi vòng điều khiển 50 Hz của một lần chạy SIM hay VehicleIO với bo MÔ
PHỎNG (nhịp giao diện, nhịp điều khiển, thời gian phiên so với đồng hồ thật); tiến trình con là `con --chay --nhanh N`.
Không cổng COM, không camera, không LiDAR. Mặc định ≈ 16–30 phút cửa sổ thật:
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.ecoqos_gui do-chay --ra docs\\evidence\\ecoqos_chay_<ngày>
    .venv\\Scripts\\python.exe -X utf8 -m autopark.evaluation.ecoqos_gui do-chay --ra runs\\thu_ecoqos_chay --nhanh SIM --bien-the gui_system --khoi 1 --lap 1 --cho 2
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from dataclasses import asdict, dataclass
import functools
import json
import math
import os
from pathlib import Path
import platform
import queue
import re
import statistics
import struct
import subprocess
import sys
import threading
import time
from typing import Callable, Iterable, Sequence

from autopark.power_throttling import disable_power_throttling, execution_speed_throttling

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VEHICLE_CONFIG = PROJECT_ROOT / "configs" / "vehicle_default.json"
MODULE = "autopark.evaluation.ecoqos_gui"

TRANG_THAI = ("thuong", "thu_nho", "bi_che")
"""Trạng thái cửa sổ lúc bấm: hiện và ở trước / thu nhỏ / bị một cửa sổ đục luôn-trên-cùng che kín."""
BIEN_THE = ("gui_system", "gui_off", "khong_cua_so")
"""gui_system: giao diện, EcoQoS để Windows tự quyết — như ứng dụng trước 02/10/2026, hay ứng dụng chạy với
AUTOPARK_KEEP_ECOQOS=1 (tiến trình con dựng cửa sổ qua `ui.app.build_window`, không qua `main()`, nên không tự tắt);
gui_off: giao diện, tắt EcoQoS theo pid — đúng lời gọi mà ứng dụng từ 02/10/2026 tự làm cho mình
(power_throttling.apply_ecoqos_policy); khong_cua_so: tiến trình con không cửa sổ, cùng đường `Session.plan_async`
(điều kiện 30/09)."""

COT = (
    "thoi_diem", "khoi", "bien_the", "pid", "lan", "khoi_dong", "trang_thai",
    "ecoqos", "uu_tien",
    "phien", "ket_noi", "ban_lam_viec", "man_hinh", "vang_s", "phien_sau", "man_hinh_sau", "vang_s_sau",
    "cua_so_truoc", "gui_thu_nho", "gui_hien", "gui_lo_ra", "che_kin", "cap_quyen_truoc", "ket_qua_dua_ra_truoc",
    "ket_qua", "tg_tinh_s", "tg_giao_dien_s", "tre_poll_s", "elapsed_s", "cusps", "dai_m", "nac",
    "tai_nen_pct", "tai_trong_pct", "cpu_tien_trinh_s", "ban_ron_p_s", "ban_ron_e_s", "ty_le_e",
    "ghi_chu", "thong_diep",
)
"""Khóa của một dòng ket_qua.jsonl, theo thứ tự. Thời gian tính bằng perf_counter của tiến trình con (`tg_tinh_s`: từ lúc
bấm tới khi bộ lập kế hoạch trả về; `tg_giao_dien_s`: tới khi giao diện thấy kết quả; `tre_poll_s`: hiệu hai số đó).

`cua_so_truoc` (lúc bấm): giao_dien | man_che | trung_tinh | khac:<tệp chạy> | "" (không có cửa sổ nào ở trước). Hai
khóa thêm 02/10/2026 (dòng cũ không có, đọc như None) ghi bước đổi trạng thái ngay trước lượt (`chuyen_trang_thai`):
`cap_quyen_truoc`: None khi không cần (cửa sổ đích thuộc tiến trình đang ở trước); "<cửa sổ đang ở trước>:ok" |
":tu_choi:<GetLastError>" | ":khong_tra_loi" khi tiến trình của nó được bảo gọi AllowSetForegroundWindow(ASFW_ANY);
"khong_ai:<cửa sổ đang ở trước>" khi cửa sổ đó không thuộc công cụ (không ai cấp được quyền). `ket_qua_dua_ra_truoc`:
"<đích>:ok" khi đọc lại thấy cửa sổ đích ở trước ngay sau khi đổi trạng thái; ngược lại "<đích>:<mã>:<cửa sổ đang ở
trước>", mã là tu_choi (SetForegroundWindow trả FALSE), khong_o_truoc (trả TRUE nhưng cửa sổ khác ở trước),
khong_tra_loi (tiến trình sở hữu cửa sổ đích không trả lời) hoặc khong_hien (không có cửa sổ trung tính)."""

CHO_SAN_SANG_S = 60.0          # tiến trình con phải báo san_sang trong thời gian này
CHO_KET_QUA_S = 40.0           # hạn lập đường 8 s + kiểm chứng + dư
CHO_MAN_CHE_S = 10.0
TAI_NEN_CAO = 25.0             # %, tải nền toàn máy trong 2 s trước lúc bấm: cao hơn thì lượt bị loại
NGUONG_CHAM = 1.30             # hệ số (trung vị / trung vị mốc) từ đây trở lên: "chậm rõ"
NGUONG_NHIEU = 1.15            # từ đây trở lên: "có thể chậm nhẹ"
TOI_THIEU_LUOT = 2             # mỗi bên của một phép so cần ngần này lượt hợp lệ: một lượt không đủ để kết luận
LO_RA_TOI_THIEU = 0.5          # lượt "thường": ít nhất nửa số điểm mẫu trên cửa sổ phải thấy chính cửa sổ đó
GUID_CONSOLE_DISPLAY_STATE = "6fe69556-704a-47a0-8f24-c28d936fda47"
LOP_PHU_NGUON = {
    "00000000-0000-0000-0000-000000000000": "không có (Balanced)",
    "961cc777-2547-4f9d-8174-7d86181b8a7a": "Best power efficiency",
    "3af9b8d9-7c97-431d-ad78-34a8bfea439f": "Better performance",
    "ded574b5-45a0-4f42-8737-46345c09c238": "Best performance",
}
GIAI_THICH_KHOA = (
    "Phiên Windows bị khóa (Win+L, bảo vệ màn hình có mật khẩu, chính sách khóa khi không dùng) thì bàn làm việc nhận "
    "nhập chuyển sang Winlogon: cửa sổ AutoPark vẫn chạy trên bàn làm việc Default nhưng không được vẽ ra màn hình và "
    "không thể có focus. Với Windows, mọi cửa sổ lúc đó đều không ai nhìn thấy, nên ba trạng thái thường / thu nhỏ / "
    "bị che gộp thành một điều kiện và không còn lượt 'thường' nào làm mốc 'cửa sổ đang hiện'. Số đo khi khóa vẫn đúng "
    "nhưng trả lời câu hỏi khác (lập đường nhanh hay chậm khi máy khóa); nó KHÔNG cho biết thu nhỏ hay bị che có làm "
    "chậm hay không. Phiên ngắt kết nối (Remote Desktop) và màn hình tắt cũng vậy. Các lượt đó bị loại khỏi phép so "
    "sánh và đếm riêng; nếu cả lượt đo diễn ra khi khóa, tài liệu chỉ ghi 'đã đo khi phiên khóa: …; thu nhỏ/bị che: "
    "CHƯA ĐO'."
)
HAU_TO_TIEU_DE = " — đang đo EcoQoS"
CHU_MAN_CHE = ("AutoPark đang đo: cửa sổ này cố ý che ứng dụng để đo xem Windows có hạ tốc ứng dụng bị che hay không. "
               "Tự đóng sau tối đa {phut} phút. Esc hoặc bấm chuột: đóng ngay (lượt đo đang chạy bị bỏ).")
TIEU_DE_TRUNG_TINH = "AutoPark — cửa sổ trung tính khi đo EcoQoS"
CHU_TRUNG_TINH = ("AutoPark đang đo EcoQoS: cửa sổ này đứng trước trong lúc ứng dụng thu nhỏ, như khi bạn dùng ứng dụng "
                  "khác. Tự đóng sau tối đa {phut} phút; Esc hoặc bấm chuột: đóng ngay.")
CO_TRUNG_TINH = (320, 120)       # điểm ảnh logic: nhỏ, không che màn hình
ASFW_ANY = 0xFFFFFFFF            # AllowSetForegroundWindow(ASFW_ANY): mọi tiến trình (DWORD -1)
DICH_TRUOC = {"thuong": "giao_dien", "thu_nho": "trung_tinh", "bi_che": "man_che"}
"""Cửa sổ phải ở trước (foreground) sau khi đổi sang từng trạng thái: giao diện / cửa sổ trung tính / màn che."""
_TIEN_TRINH_CUA = {"giao_dien": "con", "trung_tinh": "che", "man_che": "che"}
LY_DO = ("khoi_dong", "khong_tra_loi", "bo_qua", "phien_khoa", "phien_khong_ro", "ngat_ket_noi", "ban_lam_viec_khac",
         "man_hinh_tat", "nguoi_dung_thao_tac", "tai_nen_cao", "sai_trang_thai", "gui_van_o_truoc",
         "gui_khong_o_truoc", "doi_trang_thai_trong_chay", "khong_tat_duoc_ecoqos", "khong_giu_duoc_ecoqos")
"""Lý do loại một lượt khỏi phép so sánh, theo thứ tự ưu tiên của `ly_do_loai`. `gui_van_o_truoc`: lượt "thu nhỏ" /
"bị che" mà cửa sổ ở trước (foreground) lúc bấm vẫn là giao diện, nên không phải điều kiện "người dùng đang làm việc
khác" cần đo (Windows xếp QoS theo cửa sổ ở trước / có focus; thu nhỏ bằng SW_MINIMIZE có lúc để giao diện ở trước,
gặp ở lượt thử 02/10/2026). `gui_khong_o_truoc` (thêm 02/10/2026): lượt "thường" mà giao diện không ở trước lúc bấm,
nên không phải mốc "người dùng đang nhìn ứng dụng" (ví dụ Windows từ chối đưa giao diện về trước); nếu không loại,
mốc có thể bị hạ tốc như lượt cần so và che mất khác biệt. Hai lý do thêm 02/10/2026 (dòng cũ không có, không đổi
cách loại dòng cũ): `doi_trang_thai_trong_chay` (chế độ chạy: một mẫu trạng thái cửa sổ lấy mỗi giây trong lúc xe chạy
không đúng trạng thái đang đo, khóa `mau_sai`); `khong_giu_duoc_ecoqos` (biến thể gui_system mà tiến trình giao diện
không còn ở mặc định của Windows lúc sẵn sàng, ví dụ ứng dụng tự tắt EcoQoS bỏ qua AUTOPARK_KEEP_ECOQOS=1; chỉ khi
EcoQoS đọc được, xem `kiem_gui_system`)."""

ECOQOS_KHONG_DOC_DUOC = ("không đọc được EcoQoS (GetProcessInformation(ProcessPowerThrottling) không có trước Windows "
                         "bản 22000, hoặc không mở được tiến trình)")


def kiem_gui_system(ecoqos: str | None) -> str:
    """Biến thể gui_system, EcoQoS mà tiến trình giao diện tự đọc lúc sẵn sàng (`execution_speed_throttling()`; chung
    cho chế độ lập đường và chế độ chạy, sửa 02/10/2026). "system" → "ok". None (không đọc được) → "khong_doc_duoc":
    trạng thái KHÔNG BIẾT chứ không phải khác mặc định, nên các dòng vẫn được giữ như trước khi có phép kiểm này và công
    cụ chỉ cảnh báo (`ECOQOS_KHONG_DOC_DUOC`). Giá trị khác ("on", "off") → "khong_giu_duoc_ecoqos": mọi dòng của khối
    bị loại."""
    if ecoqos is None:
        return "khong_doc_duoc"
    return "ok" if ecoqos == "system" else "khong_giu_duoc_ecoqos"


def han_lap_duong_s() -> float:
    """Hạn lập đường của ứng dụng: `PlannerParams().time_limit`, đặt lúc bấm (giao diện không có ô chỉnh)."""
    from autopark.planning.hybrid_astar import PlannerParams

    return float(PlannerParams().time_limit)


def _tron(x: float | None, n: int = 4) -> float | None:
    return None if x is None else round(float(x), n)


def _sach(x):
    """Bỏ NaN / vô cực (JSON chuẩn không có) khỏi một giá trị lồng nhau."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _sach(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_sach(v) for v in x]
    return x


# ------------------------------------------------------------------------------------------- đầu dò (tiến trình con)

def _gui_tin(tin: dict) -> None:
    """Tiến trình con → tiến trình điều khiển: một đối tượng JSON mỗi dòng trên stdout (UTF-8)."""
    sys.stdout.write(json.dumps(_sach(tin), ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _nac(attempt) -> dict:
    return {"nac": attempt.rung, "ket_qua": attempt.status, "giay": round(float(attempt.seconds), 3),
            "bam": bool(attempt.tracked)}


def ghi_nac(nhan: Callable[[list[dict], float], None]) -> Callable[[], None]:
    """Bọc `autopark.planning.portfolio.plan` (parking.py tra thuộc tính của module lúc gọi) để biết các nấc đã thử và
    lúc bộ lập kế hoạch trả về. Không có `attempts` thì truyền một list riêng; xong (kể cả khi lỗi) gọi
    `nhan([{"nac","ket_qua","giay","bam"}...], perf_counter())` từ luồng worker. Tham số và kết quả giữ nguyên.
    Trả hàm gỡ lớp bọc."""
    from autopark.planning import portfolio

    goc = portfolio.plan

    @functools.wraps(goc)
    def boc(*args, **kwargs):
        nhat_ky = args[7] if len(args) > 7 else kwargs.get("attempts")
        if nhat_ky is None and len(args) <= 7:                 # attempts là tham số thứ 8 của portfolio.plan
            nhat_ky = kwargs["attempts"] = []
        try:
            return goc(*args, **kwargs)
        finally:
            t_xong = time.perf_counter()
            try:
                nhan([_nac(a) for a in (nhat_ky or [])], t_xong)
            except Exception:  # noqa: BLE001 - đầu dò không được làm hỏng lần lập đường
                pass

    portfolio.plan = boc

    def go() -> None:
        if portfolio.plan is boc:
            portfolio.plan = goc

    return go


def _ket_qua(lan: int, result, t_bam: float, t_xong: float | None, t_thay: float, nac: list[dict]) -> dict:
    """Thông điệp `ket_qua` chung cho `con` và `nen`. `result` None: kết quả bị bỏ (sa bàn đổi trong lúc tính).
    `t_xong` None: không tới được portfolio (ví dụ GOAL_INVALID), khi đó tg_tinh_s lấy bằng tg_giao_dien_s."""
    tg_giao_dien = t_thay - t_bam
    traj = getattr(result, "trajectory", None)
    return {
        "loai": "ket_qua", "lan": lan,
        "ket_qua": result.status if result is not None else "BO_KET_QUA",
        "thong_diep": (result.message if result is not None else "kết quả bị bỏ (sa bàn đổi trong lúc tính)")[:200],
        "tg_tinh_s": _tron(t_xong - t_bam if t_xong is not None else tg_giao_dien),
        "tg_giao_dien_s": _tron(tg_giao_dien),
        "tre_poll_s": _tron(t_thay - t_xong) if t_xong is not None else None,
        "elapsed_s": _tron(result.elapsed) if result is not None else None,
        "cusps": traj.n_cusps if traj is not None else None,
        "dai_m": _tron(traj.length) if traj is not None else None,
        "nac": nac,
        "ecoqos_con": execution_speed_throttling() or "khong_doc_duoc",
    }


def _tach_lenh(dong: str) -> tuple[str, str | None]:
    """"plan 7" → ("plan", "7"): số sau lệnh là mã yêu cầu, trả lời mang lại trong `yeu_cau`."""
    ten, _, tham_so = dong.strip().partition(" ")
    return ten, (tham_so.strip() or None)


class DauDoKeHoach:
    """Đầu dò trong tiến trình giao diện: bấm "Tìm đường đỗ" theo lệnh và báo thời gian.

    Bọc `window._after_plan` bằng thuộc tính của đối tượng (`_on_tick` gọi `self._after_plan`). Chỉ gọi
    `window.plan()` khi phiên đang chỉnh hoặc sẵn sàng; trạng thái khác thì `plan()` sẽ mở hộp thoại modal, nên trả
    thông điệp `loi` thay vì gọi.

    Thêm 02/10/2026: `cap_quyen <mã>` gọi AllowSetForegroundWindow(ASFW_ANY) từ tiến trình giao diện (chỉ được khi nó
    đang ở trước), trả {"loai": "cap_quyen", "ok": BOOL, "loi": GetLastError}; `len_truoc <mã>` gọi SetForegroundWindow
    lên chính cửa sổ giao diện, trả {"loai": "len_truoc", "ok": BOOL, "truoc_hwnd": cửa sổ ở trước ngay sau}. Hai hàm
    Win32 tiêm được (`cap_quyen`, `dat_truoc`) để test và chế độ offscreen không gọi Win32 thật."""

    def __init__(self, window, emit: Callable[[dict], None],
                 cap_quyen: Callable[[], tuple[bool, int | None]] | None = None,
                 dat_truoc: Callable[[int], tuple[bool, int | None]] | None = None):
        self.window = window
        self.emit = emit
        self.lan = -1
        self._dang_do: tuple[int, float, str | None] | None = None      # (lan, t_bam, yeu_cau)
        self._nac: list[dict] = []
        self._t_xong: float | None = None
        self._cap_quyen = cap_quyen or cho_phep_dat_truoc
        self._dat_truoc = dat_truoc or dat_cua_so_truoc
        self._sau_goc = window._after_plan
        window._after_plan = self._sau_khi_lap

    def nhan_nac(self, nac: list[dict], t_xong: float) -> None:
        """Đưa cho `ghi_nac`: chạy ở luồng worker, chỉ gán hai thuộc tính."""
        self._nac, self._t_xong = nac, t_xong

    def xu_ly(self, lenh: str) -> None:
        from autopark.application.session import EDITABLE_STATES

        ten, yeu_cau = _tach_lenh(lenh)
        if ten == "cap_quyen":
            ok, loi = self._cap_quyen()
            self.emit({"loai": "cap_quyen", "yeu_cau": yeu_cau, "ok": bool(ok), "loi": loi})
            return
        if ten == "len_truoc":
            ok, truoc = self._dat_truoc(int(self.window.winId()))
            self.emit({"loai": "len_truoc", "yeu_cau": yeu_cau, "ok": bool(ok), "truoc_hwnd": truoc})
            return
        if ten != "plan":
            self.emit({"loai": "loi", "yeu_cau": yeu_cau, "thong_diep": f"lệnh lạ: {lenh!r}"})
            return
        state = self.window.session.state
        if state not in EDITABLE_STATES:                 # gồm PLANNING: lần trước chưa xong
            self.emit({"loai": "loi", "yeu_cau": yeu_cau,
                       "thong_diep": f"phiên đang {state.value}: không bấm 'Tìm đường đỗ' (sẽ mở hộp thoại)"})
            return
        # `_dang_do` còn mà phiên đã về chỉnh: lần trước bị hủy (nút Dừng), `_after_plan` không được gọi; bỏ nó
        self.lan += 1
        self._nac, self._t_xong = [], None
        self._dang_do = (self.lan, time.perf_counter(), yeu_cau)
        try:
            self.window.plan()
        except Exception as exc:  # noqa: BLE001 - báo về tiến trình điều khiển thay vì im lặng
            self._dang_do = None
            self.emit({"loai": "loi", "yeu_cau": yeu_cau, "thong_diep": f"plan() lỗi: {exc!r}"[:200]})

    def _sau_khi_lap(self, result) -> None:
        t_thay = time.perf_counter()
        self._sau_goc(result)
        if self._dang_do is None:                     # lần lập đường không do đầu dò bấm
            return
        lan, t_bam, yeu_cau = self._dang_do
        self._dang_do = None
        tin = _ket_qua(lan, result, t_bam, self._t_xong, t_thay, self._nac)
        tin["yeu_cau"] = yeu_cau
        self.emit(tin)


def _hang_lenh_stdin() -> queue.Queue:
    """Luồng nền đọc từng dòng lệnh của stdin vào hàng đợi; hết stdin (tiến trình điều khiển đã chết) thành "thoat".

    Đọc bằng os.read trên mô tả tệp, KHÔNG qua sys.stdin.buffer: luồng nền đang chặn trong BufferedReader giữ khóa của
    nó, và lúc tắt trình thông dịch Python dừng hẳn ("could not acquire lock for <stdin> at interpreter shutdown",
    mã thoát 0xC0000005; gặp 02/10/2026 khi tiến trình con thoát lúc stdin còn mở)."""
    hang: queue.Queue = queue.Queue()

    def doc() -> None:
        con_lai = b""
        try:
            fd = sys.stdin.fileno()
            while True:
                khoi = os.read(fd, 4096)
                if not khoi:
                    break
                *du_dong, con_lai = (con_lai + khoi).split(b"\n")
                for raw in du_dong:
                    dong = raw.decode("utf-8", "replace").strip()
                    if dong:
                        hang.put(dong)
        except (OSError, ValueError, AttributeError):    # không có stdin / stdin đã đóng
            pass
        hang.put("thoat")

    threading.Thread(target=doc, daemon=True, name="ecoqos-stdin").start()
    return hang


def chay_con(kich_ban: Path, cho_phep_offscreen: bool = False, *, chay: bool = False, nhanh: str = "SIM") -> int:
    """`con`: giao diện thật như `run_app.py <kich_ban>` (build_window, show, exec) cộng đầu dò. Từ chối nền tảng Qt
    không phải "windows" (offscreen không phải cửa sổ thật) trừ khi `cho_phep_offscreen` (chỉ dùng cho test).

    `chay` (thêm 02/10/2026, lệnh `do-chay`): thêm đầu dò vòng điều khiển `ecoqos_chay.DauDoChay` (lệnh chuan_bi | chay
    | dung, chặn hộp thoại modal) và chọn nhánh `nhanh` như người dùng chọn ở ô "Nhánh chạy khi bấm Bắt đầu đỗ";
    VEHICLE_IO chỉ với bo mô phỏng, không thì báo `loi` và thoát mã 2 (không mở cổng nào). Như `build_window`, không gọi
    chính sách EcoQoS lúc khởi động của `ui.app.main()` (nếu có): EcoQoS của từng biến thể do tiến trình điều khiển đặt
    và đọc lại."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0]])
    nen_tang = app.platformName()
    if nen_tang != "windows" and not cho_phep_offscreen:
        _gui_tin({"loai": "loi", "thong_diep": f"Qt đang dùng nền tảng '{nen_tang}': không phải cửa sổ thật"})
        return 2
    from autopark.ui.app import build_window

    try:
        window = build_window(Path(kich_ban))
    except Exception as exc:  # noqa: BLE001 - kịch bản hỏng: báo rồi thoát
        _gui_tin({"loai": "loi", "thong_diep": f"không dựng được cửa sổ: {exc!r}"[:300]})
        return 2
    dau_do_chay = None
    if chay:
        from autopark.evaluation.ecoqos_chay import DauDoChay, chon_nhanh

        dau_do_chay = DauDoChay(window, _gui_tin)          # chặn hộp thoại trước mọi bước có thể mở hộp thoại
        loi = chon_nhanh(window, nhanh)
        if loi is not None:
            _gui_tin({"loai": "loi", "thong_diep": loi})
            dau_do_chay.go()
            window.close()
            return 2
    win32 = (cho_phep_dat_truoc, dat_cua_so_truoc) if nen_tang == "windows" else (_khong_cap_quyen, _khong_dat_truoc)
    dau_do = DauDoKeHoach(window, _gui_tin, *win32)
    go_nac = ghi_nac(dau_do.nhan_nac)
    window.setWindowTitle(window.windowTitle() + HAU_TO_TIEU_DE)
    window.show()
    app.processEvents()
    san_sang = {"loai": "san_sang", "pid": os.getpid(), "hwnd": int(window.winId()), "nen_tang": nen_tang,
                "ecoqos": execution_speed_throttling()}
    if dau_do_chay is not None:
        san_sang.update(dau_do_chay.thong_tin(nhanh))
    _gui_tin(san_sang)
    hang = _hang_lenh_stdin()

    def xu_ly_hang() -> None:
        while True:
            try:
                lenh = hang.get_nowait()
            except queue.Empty:
                return
            if lenh == "thoat":
                nhip.stop()
                window.close()                            # closeEvent → Session.close()
                app.quit()
                return
            if dau_do_chay is None or not dau_do_chay.xu_ly(lenh):
                dau_do.xu_ly(lenh)

    nhip = QTimer()
    nhip.setInterval(50)
    nhip.timeout.connect(xu_ly_hang)
    nhip.start()
    try:
        return app.exec()
    finally:
        go_nac()
        if dau_do_chay is not None:
            dau_do_chay.go()


def chay_mot_lan_nen(session, lan: int, nac: dict) -> dict:
    """Một lần lập đường của `nen`: `plan_async` rồi `poll_plan` mỗi 16 ms bằng time.sleep, như `_on_tick` của giao
    diện. `nac` là dict mà `ghi_nac` điền ("ds", "t")."""
    from autopark.application.session import EDITABLE_STATES, SessionState

    if session.state not in EDITABLE_STATES:
        return {"loai": "loi", "thong_diep": f"phiên đang {session.state.value}"}
    nac.clear()
    t_bam = time.perf_counter()
    session.plan_async()
    result = None
    while session.state == SessionState.PLANNING:
        time.sleep(0.016)
        result = session.poll_plan()
    t_thay = time.perf_counter()
    return _ket_qua(lan, result, t_bam, nac.get("t"), t_thay, nac.get("ds", []))


def chay_nen(kich_ban: Path) -> int:
    """`nen`: đối chứng không cửa sổ. Dựng đúng các đối tượng build_window dựng (load_scenario, load_vehicle_config,
    Session), không có MainWindow."""
    from autopark.application.session import Session
    from autopark.storage.scenario_store import load_scenario, load_vehicle_config

    try:
        scenario = load_scenario(Path(kich_ban))
        session = Session(scenario, load_vehicle_config(scenario.vehicle_config_path))
    except Exception as exc:  # noqa: BLE001
        _gui_tin({"loai": "loi", "thong_diep": f"không nạp được kịch bản: {exc!r}"[:300]})
        return 2
    nac: dict = {}
    go_nac = ghi_nac(lambda ds, t: nac.update(ds=ds, t=t))
    _gui_tin({"loai": "san_sang", "pid": os.getpid(), "hwnd": None, "nen_tang": "khong_cua_so",
              "ecoqos": execution_speed_throttling()})
    hang = _hang_lenh_stdin()
    lan = -1
    try:
        while True:
            lenh = hang.get()
            if lenh == "thoat":
                return 0
            ten, yeu_cau = _tach_lenh(lenh)
            if ten != "plan":
                _gui_tin({"loai": "loi", "yeu_cau": yeu_cau, "thong_diep": f"lệnh lạ: {lenh!r}"})
                continue
            lan += 1
            tin = chay_mot_lan_nen(session, lan, nac)
            tin["yeu_cau"] = yeu_cau
            _gui_tin(tin)
    finally:
        session.close()
        go_nac()


def _khong_cap_quyen() -> tuple[bool, int | None]:
    """Thay `cho_phep_dat_truoc` khi Qt không chạy cửa sổ thật (test offscreen): từ chối, không gọi Win32."""
    return False, None


def _khong_dat_truoc(hwnd: int) -> tuple[bool, int | None]:
    """Thay `dat_cua_so_truoc` khi Qt không chạy cửa sổ thật: winId offscreen không phải HWND, không gọi Win32."""
    return False, None


def chay_che(toi_da_s: float, cho_phep_offscreen: bool = False) -> int:
    """`che`: hai cửa sổ của công cụ trong một tiến trình (cửa sổ trung tính thêm 02/10/2026).

    Màn che: đục, không viền, luôn trên cùng, có lời giải thích, phủ màn hình (trạng thái "bị che"). Cửa sổ trung tính:
    nhỏ (`CO_TRUNG_TINH`), có tiêu đề tiếng Việt, ở góc dưới phải màn hình chính, không luôn-trên-cùng; nó đứng trước
    trong lúc giao diện thu nhỏ (trạng thái "thu nhỏ"), như khi người dùng chuyển sang ứng dụng khác. Cả hai hiện mà
    KHÔNG tự lấy focus (WA_ShowWithoutActivating): chỉ lệnh `len_truoc` gọi SetForegroundWindow, sau khi tiến trình đang
    ở trước đã cấp quyền. Lệnh (một dòng): hien | trung_tinh | len_truoc che|trung_tinh | cap_quyen |
    an [che|trung_tinh] | thoat. Esc hoặc bấm chuột trên một trong hai cửa sổ (hay nút đóng của cửa sổ trung tính) báo
    `nguoi_dung_dong` rồi thoát; hết `toi_da_s` giây báo `het_gio` rồi thoát; cả hai cửa sổ đóng theo tiến trình."""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QFont, QPalette
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

    app = QApplication.instance() or QApplication([sys.argv[0]])
    nen_tang = app.platformName()
    if nen_tang != "windows" and not cho_phep_offscreen:
        _gui_tin({"loai": "loi", "thong_diep": f"Qt đang dùng nền tảng '{nen_tang}': màn che không phải cửa sổ thật"})
        return 2
    app.setQuitOnLastWindowClosed(False)
    cap_quyen, dat_truoc = ((cho_phep_dat_truoc, dat_cua_so_truoc) if nen_tang == "windows"
                            else (_khong_cap_quyen, _khong_dat_truoc))
    phut = max(1, math.ceil(toi_da_s / 60))
    da_bao: list[str] = []
    dang_thoat: list[bool] = []

    def thoat() -> None:
        # exit() chứ không quit(): quit() của Qt 6 hỏi closeEvent của mọi cửa sổ đang hiện trước khi thoát
        dang_thoat.append(True)
        app.exit(0)

    def ket_thuc(loai: str) -> None:
        if not da_bao:                                     # chỉ báo lý do đầu tiên
            da_bao.append(loai)
            _gui_tin({"loai": loai})
        thoat()

    class CuaSoCongCu(QWidget):
        def keyPressEvent(self, event) -> None:
            if event.key() == Qt.Key.Key_Escape:
                ket_thuc("nguoi_dung_dong")
            else:
                super().keyPressEvent(event)

        def mousePressEvent(self, event) -> None:
            ket_thuc("nguoi_dung_dong")

        def closeEvent(self, event) -> None:               # nút đóng của cửa sổ trung tính, Alt+F4
            if dang_thoat:                                 # chính công cụ đang thoát: không phải người dùng đóng
                event.accept()
                return
            event.ignore()
            ket_thuc("nguoi_dung_dong")

    man = CuaSoCongCu()
    man.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
    man.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    man.setWindowTitle("AutoPark — màn che khi đo EcoQoS")
    bang_mau = man.palette()
    bang_mau.setColor(QPalette.ColorRole.Window, QColor("#0c131b"))
    bang_mau.setColor(QPalette.ColorRole.WindowText, QColor("#e8eef3"))
    man.setPalette(bang_mau)
    man.setAutoFillBackground(True)
    chu = QLabel(CHU_MAN_CHE.format(phut=phut))
    chu.setWordWrap(True)
    chu.setAlignment(Qt.AlignmentFlag.AlignCenter)
    font = QFont()
    font.setPointSize(26)
    chu.setFont(font)
    bo_cuc = QVBoxLayout(man)
    bo_cuc.setContentsMargins(120, 80, 120, 80)
    bo_cuc.addStretch(1)
    bo_cuc.addWidget(chu)
    bo_cuc.addStretch(1)

    trung = CuaSoCongCu()                                  # cửa sổ thường, có tiêu đề và nút đóng, không thu nhỏ được
    trung.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint
                         | Qt.WindowType.WindowCloseButtonHint)
    trung.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    trung.setWindowTitle(TIEU_DE_TRUNG_TINH)
    trung.setFixedSize(*CO_TRUNG_TINH)
    chu_tt = QLabel(CHU_TRUNG_TINH.format(phut=phut))
    chu_tt.setWordWrap(True)
    chu_tt.setAlignment(Qt.AlignmentFlag.AlignCenter)
    bo_cuc_tt = QVBoxLayout(trung)
    bo_cuc_tt.setContentsMargins(10, 8, 10, 8)
    bo_cuc_tt.addWidget(chu_tt)
    cua_so = {"che": man, "trung_tinh": trung}

    QTimer.singleShot(int(toi_da_s * 1000), lambda: ket_thuc("het_gio"))
    hang = _hang_lenh_stdin()

    def xu_ly_hang() -> None:
        while True:
            try:
                lenh = hang.get_nowait()
            except queue.Empty:
                return
            ten, tham_so = _tach_lenh(lenh)
            if lenh == "hien":
                man.setGeometry(app.primaryScreen().geometry())
                man.show()                                 # không lấy focus; tiến trình điều khiển đặt luôn-trên-cùng
                app.processEvents()
                _gui_tin({"loai": "da_hien", "hwnd": int(man.winId())})
            elif lenh == "trung_tinh":
                vung = app.primaryScreen().availableGeometry()
                trung.move(vung.x() + vung.width() - trung.width() - 40,
                           vung.y() + vung.height() - trung.height() - 80)
                trung.show()
                app.processEvents()
                _gui_tin({"loai": "da_hien_trung_tinh", "hwnd": int(trung.winId())})
            elif ten == "len_truoc" and tham_so in cua_so:
                w = cua_so[tham_so]
                ok, truoc = dat_truoc(int(w.winId())) if w.isVisible() else (False, None)
                app.processEvents()
                _gui_tin({"loai": "da_len_truoc", "cua_so": tham_so, "ok": bool(ok), "truoc_hwnd": truoc})
            elif lenh == "cap_quyen":
                ok, loi = cap_quyen()
                _gui_tin({"loai": "cap_quyen", "ok": bool(ok), "loi": loi})
            elif ten == "an" and (tham_so is None or tham_so in cua_so):
                for ten_cua_so, w in cua_so.items():
                    if tham_so in (None, ten_cua_so):
                        w.hide()
                app.processEvents()
                _gui_tin({"loai": "da_an"})
            elif lenh == "thoat":
                thoat()
                return
            else:
                _gui_tin({"loai": "loi", "thong_diep": f"lệnh lạ: {lenh!r}"})

    nhip = QTimer()
    nhip.setInterval(50)
    nhip.timeout.connect(xu_ly_hang)
    nhip.start()
    _gui_tin({"loai": "san_sang", "pid": os.getpid(), "hwnd": int(man.winId()), "hwnd_trung_tinh": int(trung.winId()),
              "nen_tang": nen_tang})
    return app.exec()


# -------------------------------------------------------------------------------------------- lớp Windows (ctypes)

def _khong_nem(mac_dinh):
    """Hàm đọc/ghi Win32 không bao giờ ném lỗi: ngoài Windows hoặc khi lỗi thì trả `mac_dinh`."""
    def boc(ham):
        @functools.wraps(ham)
        def chay(*args, **kwargs):
            if sys.platform != "win32":
                return mac_dinh
            try:
                return ham(*args, **kwargs)
            except Exception:  # noqa: BLE001 - lớp đọc trạng thái không được làm hỏng lượt đo
                return mac_dinh
        return chay
    return boc


@functools.lru_cache(maxsize=None)
def _thu_vien(ten: str):
    import ctypes

    return ctypes.WinDLL(ten, use_last_error=True)


def _ham(thu_vien: str, ten: str, restype, *argtypes):
    """Hàm `ten` của DLL `thu_vien`, khai báo kiểu tường minh (HANDLE không bị cắt còn 32 bit)."""
    f = getattr(_thu_vien(thu_vien), ten)
    f.restype = restype
    f.argtypes = list(argtypes)
    return f


@functools.lru_cache(maxsize=None)
def _ct():
    """Các cấu trúc Win32 dùng ở đây (tạo một lần, chỉ gọi trên Windows)."""
    import ctypes
    from ctypes import wintypes
    from types import SimpleNamespace

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    class WTSINFOEX_LEVEL1_W(ctypes.Structure):
        _fields_ = [("SessionId", wintypes.ULONG), ("SessionState", ctypes.c_int), ("SessionFlags", wintypes.LONG),
                    ("WinStationName", wintypes.WCHAR * 33), ("UserName", wintypes.WCHAR * 21),
                    ("DomainName", wintypes.WCHAR * 18), ("LogonTime", ctypes.c_int64),
                    ("ConnectTime", ctypes.c_int64), ("DisconnectTime", ctypes.c_int64),
                    ("LastInputTime", ctypes.c_int64), ("CurrentTime", ctypes.c_int64),
                    ("BoDem", wintypes.DWORD * 6)]

    class WTSINFOEXW(ctypes.Structure):           # sizeof = 232 trên Windows 64 bit
        _fields_ = [("Level", wintypes.DWORD), ("Data", WTSINFOEX_LEVEL1_W)]

    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    CALLBACK = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p)

    class DEVICE_NOTIFY_SUBSCRIBE_PARAMETERS(ctypes.Structure):
        _fields_ = [("Callback", CALLBACK), ("Context", ctypes.c_void_p)]

    return SimpleNamespace(RECT=RECT, POINT=POINT, MONITORINFO=MONITORINFO, LASTINPUTINFO=LASTINPUTINFO, GUID=GUID,
                           WTSINFOEXW=WTSINFOEXW, SYSTEM_POWER_STATUS=SYSTEM_POWER_STATUS,
                           PROCESSENTRY32W=PROCESSENTRY32W, CALLBACK=CALLBACK,
                           DEVICE_NOTIFY_SUBSCRIBE_PARAMETERS=DEVICE_NOTIFY_SUBSCRIBE_PARAMETERS)


def _guid(chuoi: str):
    import uuid

    return _ct().GUID.from_buffer_copy(uuid.UUID(chuoi).bytes_le)


def _mo_tien_trinh(pid: int, quyen: int = 0x1000):
    """OpenProcess (mặc định PROCESS_QUERY_LIMITED_INFORMATION); handle hoặc None."""
    from ctypes import wintypes

    mo = _ham("kernel32", "OpenProcess", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    return mo(quyen, False, pid) or None


def _dong_handle(h) -> None:
    from ctypes import wintypes

    if h:
        _ham("kernel32", "CloseHandle", wintypes.BOOL, wintypes.HANDLE)(h)


_KET_NOI = {0: "active", 1: "connected", 2: "connect_query", 3: "shadow", 4: "disconnected", 5: "idle",
            6: "listen", 7: "reset", 8: "down", 9: "init"}
_UU_TIEN = {0x40: "idle", 0x4000: "below_normal", 0x20: "normal", 0x8000: "above_normal", 0x80: "high",
            0x100: "realtime"}


@dataclass(frozen=True)
class TrangThaiMay:
    """Trạng thái phiên Windows tại một thời điểm. Cửa sổ khác chỉ ghi tên tệp chạy, không ghi tiêu đề (tiêu đề có thể
    riêng tư)."""

    phien: str = "khong_ro"           # mo | khoa | khong_ro
    ket_noi: str = "khong_ro"         # active | connected | disconnected | ... | khong_ro
    ban_lam_viec: str = ""            # bàn làm việc nhận nhập: Default | Winlogon | "" (không mở được, thường khi khóa)
    man_hinh: str = "khong_ro"        # bat | tat | mo_toi | khong_ro
    vang_s: float | None = None       # giây kể từ lần thao tác phím/chuột cuối
    truoc_pid: int | None = None      # tiến trình của cửa sổ đang ở trước
    truoc_hwnd: int | None = None
    truoc_exe: str = ""

    @property
    def nhin_thay_duoc(self) -> bool:
        """Có người có thể nhìn thấy màn hình: phiên mở, đang nối, bàn làm việc Default, màn hình không tắt/mờ."""
        return (self.phien == "mo" and self.ket_noi == "active" and self.ban_lam_viec == "Default"
                and self.man_hinh in ("bat", "khong_ro"))

    def to_dict(self) -> dict:
        return {**asdict(self), "nhin_thay_duoc": self.nhin_thay_duoc}


@_khong_nem(("khong_ro", "khong_ro"))
def _doc_phien() -> tuple[str, str]:
    """(phien, ket_noi) của phiên hiện tại: WTSSessionInfoEx (cờ khóa) và WTSConnectState."""
    import ctypes
    from ctypes import wintypes

    ct = _ct()
    hoi = _ham("wtsapi32", "WTSQuerySessionInformationW", wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD,
               ctypes.c_int, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD))
    tra = _ham("wtsapi32", "WTSFreeMemory", None, ctypes.c_void_p)

    def doc(lop: int, chuyen: Callable[[int, int], str]) -> str:
        buf, n = ctypes.c_void_p(), wintypes.DWORD()
        if not hoi(None, 0xFFFFFFFF, lop, ctypes.byref(buf), ctypes.byref(n)) or not buf.value:
            return "khong_ro"
        try:
            return chuyen(buf.value, n.value)
        finally:
            tra(buf)

    def phien(dia_chi: int, n: int) -> str:
        if n < ctypes.sizeof(ct.WTSINFOEXW):
            return "khong_ro"
        info = ct.WTSINFOEXW.from_address(dia_chi)
        co = info.Data.SessionFlags
        if info.Level != 1 or co not in (0, 1):                 # -1: WTS_SESSIONSTATE_UNKNOWN
            return "khong_ro"
        dao = tuple(sys.getwindowsversion()[:2]) == (6, 1)      # Windows 7 / 2008 R2: nghĩa hai cờ bị đảo
        return "khoa" if (co == 0) != dao else "mo"

    def ket_noi(dia_chi: int, n: int) -> str:
        return _KET_NOI.get(ctypes.c_int.from_address(dia_chi).value, "khong_ro") if n >= 4 else "khong_ro"

    return doc(25, phien), doc(8, ket_noi)                       # WTSSessionInfoEx, WTSConnectState


@_khong_nem("")
def _ban_lam_viec_nhan() -> str:
    import ctypes
    from ctypes import wintypes

    mo = _ham("user32", "OpenInputDesktop", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    dong = _ham("user32", "CloseDesktop", wintypes.BOOL, wintypes.HANDLE)
    doc = _ham("user32", "GetUserObjectInformationW", wintypes.BOOL, wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
               wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    h = mo(0, False, 0x0001)                  # DESKTOP_READOBJECTS; NULL khi bàn làm việc nhận nhập là Winlogon
    if not h:
        return ""
    try:
        buf, can = ctypes.create_unicode_buffer(256), wintypes.DWORD()
        return buf.value if doc(h, 2, buf, ctypes.sizeof(buf), ctypes.byref(can)) else ""     # UOI_NAME
    finally:
        dong(h)


@_khong_nem(None)
def _vang_s() -> float | None:
    import ctypes
    from ctypes import wintypes

    ct = _ct()
    doc = _ham("user32", "GetLastInputInfo", wintypes.BOOL, ctypes.POINTER(ct.LASTINPUTINFO))
    nhip = _ham("kernel32", "GetTickCount", wintypes.DWORD)
    li = ct.LASTINPUTINFO(ctypes.sizeof(ct.LASTINPUTINFO), 0)
    if not doc(ctypes.byref(li)):
        return None
    return ((nhip() - li.dwTime) & 0xFFFFFFFF) / 1000.0


@_khong_nem("")
def ten_tien_trinh(pid: int) -> str:
    """Tên tệp chạy (không đường dẫn) của tiến trình `pid`; "" khi không đọc được."""
    import ctypes
    from ctypes import wintypes

    doc = _ham("kernel32", "QueryFullProcessImageNameW", wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD,
               wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    h = _mo_tien_trinh(pid)
    if h is None:
        return ""
    try:
        buf, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        return os.path.basename(buf.value) if doc(h, 0, buf, ctypes.byref(n)) else ""
    finally:
        _dong_handle(h)


@_khong_nem((None, None, ""))
def _cua_so_dang_truoc() -> tuple[int | None, int | None, str]:
    import ctypes
    from ctypes import wintypes

    hwnd = _ham("user32", "GetForegroundWindow", wintypes.HWND)()
    if not hwnd:
        return None, None, ""
    pid = wintypes.DWORD()
    _ham("user32", "GetWindowThreadProcessId", wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))(
        hwnd, ctypes.byref(pid))
    return (pid.value or None), int(hwnd), (ten_tien_trinh(pid.value) if pid.value else "")


@_khong_nem((False, None))
def cho_phep_dat_truoc() -> tuple[bool, int | None]:
    """AllowSetForegroundWindow(ASFW_ANY) gọi từ tiến trình này: (kết quả BOOL, GetLastError khi bị từ chối, 0 khi
    được). Windows chỉ cho khi tiến trình này được phép đặt cửa sổ ở trước (thường: nó đang ở trước); quyền của các
    tiến trình khác mất ở lần nhấn phím / chuột kế tiếp. Không đổi thiết lập nào."""
    import ctypes
    from ctypes import wintypes

    ok = bool(_ham("user32", "AllowSetForegroundWindow", wintypes.BOOL, wintypes.DWORD)(ASFW_ANY))
    return ok, (0 if ok else ctypes.get_last_error())


@_khong_nem((False, None))
def dat_cua_so_truoc(hwnd: int) -> tuple[bool, int | None]:
    """SetForegroundWindow(hwnd) gọi từ tiến trình này (tiến trình sở hữu cửa sổ): (kết quả BOOL, HWND đang ở trước
    ngay sau, None khi không có)."""
    from ctypes import wintypes

    ok = bool(_ham("user32", "SetForegroundWindow", wintypes.BOOL, wintypes.HWND)(hwnd))
    truoc = _ham("user32", "GetForegroundWindow", wintypes.HWND)()
    return ok, (int(truoc) if truoc else None)


@_khong_nem(None)
def khoa_truoc_ms() -> int | None:
    """Thời gian khóa cửa sổ ở trước sau lần nhập cuối (SPI_GETFOREGROUNDLOCKTIMEOUT, ms), chỉ đọc; None khi lỗi."""
    import ctypes
    from ctypes import wintypes

    gia_tri = wintypes.DWORD()
    ok = _ham("user32", "SystemParametersInfoW", wintypes.BOOL, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
              wintypes.UINT)(0x2000, 0, ctypes.byref(gia_tri), 0)
    return int(gia_tri.value) if ok else None


@_khong_nem("khong_ro")
def doc_man_hinh(cho: float = 0.5) -> str:
    """Trạng thái màn hình console (GUID_CONSOLE_DISPLAY_STATE): đăng ký nhận báo bằng hàm gọi lại, Windows báo ngay giá
    trị hiện tại; chờ tối đa `cho` giây rồi hủy đăng ký. bat | tat | mo_toi | khong_ro."""
    import ctypes
    from ctypes import wintypes

    ct = _ct()
    dang_ky = _ham("powrprof", "PowerSettingRegisterNotification", wintypes.DWORD, ctypes.POINTER(ct.GUID),
                   wintypes.DWORD, ctypes.POINTER(ct.DEVICE_NOTIFY_SUBSCRIBE_PARAMETERS),
                   ctypes.POINTER(ctypes.c_void_p))
    huy = _ham("powrprof", "PowerSettingUnregisterNotification", wintypes.DWORD, ctypes.c_void_p)
    gia_tri: list[int] = []
    xong = threading.Event()

    def goi_lai(_context, loai, setting):
        try:
            # PBT_POWERSETTINGCHANGE; POWERBROADCAST_SETTING: GUID (16 byte), DataLength (+16), Data (+20)
            if loai == 0x8013 and setting and ctypes.c_uint32.from_address(setting + 16).value >= 4:
                gia_tri.append(ctypes.c_uint32.from_address(setting + 20).value)
                xong.set()
        except Exception:  # noqa: BLE001 - không để lỗi đi qua lời gọi lại của Windows
            pass
        return 0

    cb = ct.CALLBACK(goi_lai)                              # giữ sống tới sau khi hủy đăng ký
    tham_so = ct.DEVICE_NOTIFY_SUBSCRIBE_PARAMETERS(cb, None)
    guid = _guid(GUID_CONSOLE_DISPLAY_STATE)
    h = ctypes.c_void_p()
    if dang_ky(ctypes.byref(guid), 2, ctypes.byref(tham_so), ctypes.byref(h)) != 0:     # DEVICE_NOTIFY_CALLBACK
        return "khong_ro"
    try:
        xong.wait(cho)
    finally:
        huy(h)
    return {0: "tat", 1: "bat", 2: "mo_toi"}.get(gia_tri[0], "khong_ro") if gia_tri else "khong_ro"


def doc_trang_thai_may(cho_man_hinh: float = 0.5) -> TrangThaiMay:
    """Đọc trạng thái phiên lúc này. Thời gian không thao tác đọc trước tiên (do_mot_lan so nó với đồng hồ của lượt)."""
    if sys.platform != "win32":
        return TrangThaiMay()
    vang = _vang_s()
    phien, ket_noi = _doc_phien()
    pid, hwnd, exe = _cua_so_dang_truoc()
    return TrangThaiMay(phien, ket_noi, _ban_lam_viec_nhan(), doc_man_hinh(cho_man_hinh), vang, pid, hwnd, exe)


@_khong_nem(None)
def lop_cpu() -> dict[int, list[int]] | None:
    """{EfficiencyClass: [số bộ xử lý logic]} từ GetSystemCpuSetInformation; lớp thấp nhất là lõi E. Chỉ nhóm 0: máy có
    hơn 64 bộ xử lý logic (nhiều nhóm) trả None."""
    import ctypes
    from ctypes import wintypes

    doc = _ham("kernel32", "GetSystemCpuSetInformation", wintypes.BOOL, ctypes.c_void_p, wintypes.ULONG,
               ctypes.POINTER(wintypes.ULONG), wintypes.HANDLE, wintypes.ULONG)
    can = wintypes.ULONG()
    doc(None, 0, ctypes.byref(can), None, 0)                 # lần đầu chỉ để biết cỡ bộ đệm
    if not can.value:
        return None
    buf = (ctypes.c_ubyte * can.value)()
    if not doc(buf, can, ctypes.byref(can), None, 0):
        return None
    raw = bytes(buf)[:can.value]
    lop: dict[int, list[int]] = {}
    dau = 0
    while dau + 8 <= len(raw):
        co, loai = struct.unpack_from("<II", raw, dau)       # Size, Type (0 = CpuSet)
        if co == 0:
            break
        if loai == 0 and dau + 8 + 11 <= len(raw):
            nhom = struct.unpack_from("<H", raw, dau + 8 + 4)[0]
            if nhom != 0:
                return None
            lop.setdefault(raw[dau + 8 + 10], []).append(raw[dau + 8 + 6])   # EfficiencyClass, LogicalProcessorIndex
        dau += co
    if not lop or sum(map(len, lop.values())) > 64:
        return None
    return {k: sorted(v) for k, v in sorted(lop.items())}


@dataclass(frozen=True)
class ChupCpu:
    """Một lần chụp bộ đếm CPU. Đơn vị 100 ns; thời gian kernel GỒM cả thời gian nhàn rỗi."""

    t: float                                                  # perf_counter lúc chụp
    he_thong: tuple[int, int, int] | None                     # (idle, kernel, user) toàn máy, GetSystemTimes
    tung_cpu: tuple[tuple[int, int, int], ...] | None         # (idle, kernel, user) từng bộ xử lý logic


@_khong_nem(None)
def _thoi_gian_he_thong() -> tuple[int, int, int] | None:
    import ctypes
    from ctypes import wintypes

    con_tro = ctypes.POINTER(ctypes.c_uint64)                 # FILETIME = số 64 bit (little endian)
    doc = _ham("kernel32", "GetSystemTimes", wintypes.BOOL, con_tro, con_tro, con_tro)
    idle, kernel, user = ctypes.c_uint64(), ctypes.c_uint64(), ctypes.c_uint64()
    if not doc(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    return idle.value, kernel.value, user.value


@_khong_nem(None)
def _thoi_gian_tung_cpu() -> tuple[tuple[int, int, int], ...] | None:
    import ctypes
    from ctypes import wintypes

    dem = _ham("kernel32", "GetActiveProcessorCount", wintypes.DWORD, wintypes.WORD)(0)      # nhóm 0
    if not 0 < dem <= 64:
        return None
    hoi = _ham("ntdll", "NtQuerySystemInformation", ctypes.c_long, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
               ctypes.POINTER(wintypes.ULONG))
    buf, tra = (ctypes.c_ubyte * (48 * dem))(), wintypes.ULONG()
    # SystemProcessorPerformanceInformation: {Idle, Kernel, User, Dpc, Interrupt: LARGE_INTEGER; ULONG} = 48 byte
    if hoi(8, buf, ctypes.sizeof(buf), ctypes.byref(tra)) != 0:
        return None
    raw = bytes(buf)
    return tuple(struct.unpack_from("<qqq", raw, 48 * i) for i in range(min(dem, tra.value // 48)))


def chup_cpu() -> ChupCpu:
    """Chụp bộ đếm toàn máy và từng bộ xử lý logic (phần không đọc được là None)."""
    return ChupCpu(time.perf_counter(), _thoi_gian_he_thong(), _thoi_gian_tung_cpu())


@_khong_nem(None)
def cpu_tien_trinh_s(pid: int) -> float | None:
    """Tổng thời gian CPU (kernel + user, giây) tiến trình `pid` đã dùng: OpenProcess + GetProcessTimes."""
    import ctypes
    from ctypes import wintypes

    con_tro = ctypes.POINTER(ctypes.c_uint64)
    doc = _ham("kernel32", "GetProcessTimes", wintypes.BOOL, wintypes.HANDLE, con_tro, con_tro, con_tro, con_tro)
    h = _mo_tien_trinh(pid)
    if h is None:
        return None
    try:
        tao, thoat, kernel, user = (ctypes.c_uint64() for _ in range(4))
        if not doc(h, ctypes.byref(tao), ctypes.byref(thoat), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        return (kernel.value + user.value) / 1e7
    finally:
        _dong_handle(h)


@_khong_nem(None)
def uu_tien(pid: int) -> str | None:
    """Lớp ưu tiên của tiến trình (GetPriorityClass): idle | below_normal | normal | above_normal | high | realtime."""
    from ctypes import wintypes

    h = _mo_tien_trinh(pid)
    if h is None:
        return None
    try:
        lop = _ham("kernel32", "GetPriorityClass", wintypes.DWORD, wintypes.HANDLE)(h)
        return _UU_TIEN.get(lop, f"0x{lop:x}") if lop else None
    finally:
        _dong_handle(h)


# Điều tiết nguồn của tiến trình (thêm 02/10/2026, chế độ chạy): ProcessPowerThrottling, PROCESS_POWER_THROTTLING_STATE
# {Version = 1, ControlMask, StateMask}. Bit EXECUTION_SPEED = EcoQoS (autopark/power_throttling.py chỉ dùng bit này);
# bit IGNORE_TIMER_RESOLUTION: Windows 11 có thể bỏ qua yêu cầu độ phân giải đồng hồ của tiến trình khi mọi cửa sổ của
# nó bị che kín, thu nhỏ hay ẩn (QTimer 16 ms khi đó có thể thưa tới ≈ 15,6 ms một nấc).
_DIEU_TIET = 4                    # PROCESS_INFORMATION_CLASS.ProcessPowerThrottling
_BIT_ECOQOS = 0x1                 # PROCESS_POWER_THROTTLING_EXECUTION_SPEED
_BIT_DONG_HO = 0x4                # PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION


def _voi_tien_trinh(pid: int | None, quyen: int, goi: Callable[[object], bool]) -> bool:
    """`goi(handle)` với tiến trình `pid` (None = chính tiến trình này: handle giả, không cần đóng); False khi không mở
    được tiến trình."""
    from ctypes import wintypes

    if pid is None:
        return goi(_ham("kernel32", "GetCurrentProcess", wintypes.HANDLE)())
    h = _mo_tien_trinh(pid, quyen)
    if h is None:
        return False
    try:
        return goi(h)
    finally:
        _dong_handle(h)


@_khong_nem(None)
def phan_giai_dong_ho_ms() -> tuple[float, float, float] | None:
    """Độ phân giải đồng hồ hệ thống (NtQueryTimerResolution, chỉ đọc): (thô nhất, mịn nhất, hiện tại), ms. Số TOÀN MÁY:
    từ Windows 10 2004 mỗi tiến trình có độ phân giải riêng, số này không cho biết tiến trình giao diện được bao nhiêu
    (chỉ báo)."""
    import ctypes
    from ctypes import wintypes

    con_tro = ctypes.POINTER(wintypes.ULONG)
    hoi = _ham("ntdll", "NtQueryTimerResolution", ctypes.c_long, con_tro, con_tro, con_tro)
    tho, min_, hien = wintypes.ULONG(), wintypes.ULONG(), wintypes.ULONG()
    if hoi(ctypes.byref(tho), ctypes.byref(min_), ctypes.byref(hien)) != 0:
        return None
    return tho.value / 1e4, min_.value / 1e4, hien.value / 1e4          # đơn vị 100 ns


@_khong_nem(None)
def doc_dieu_tiet(pid: int | None = None) -> dict[str, str] | None:
    """Điều tiết nguồn của tiến trình `pid` (None = tiến trình này), GetProcessInformation(ProcessPowerThrottling), chỉ
    đọc: {"ecoqos": system | on | off, "dong_ho": system | bo_qua | ton_trong} (Windows tự quyết / bật hay luôn bỏ qua
    / tắt hay luôn tôn trọng yêu cầu độ phân giải đồng hồ). None khi không đọc được (Windows trước bản 22000, không mở
    được tiến trình)."""
    import ctypes
    from ctypes import wintypes

    doc = _ham("kernel32", "GetProcessInformation", wintypes.BOOL, wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
               wintypes.DWORD)
    trang_thai = (wintypes.ULONG * 3)(1, 0, 0)
    if not _voi_tien_trinh(pid, 0x1000, lambda h: bool(doc(h, _DIEU_TIET, trang_thai, ctypes.sizeof(trang_thai)))):
        return None
    kiem, bat = trang_thai[1], trang_thai[2]

    def chu(bit: int, khi_bat: str, khi_tat: str) -> str:
        return "system" if not kiem & bit else (khi_bat if bat & bit else khi_tat)

    return {"ecoqos": chu(_BIT_ECOQOS, "on", "off"), "dong_ho": chu(_BIT_DONG_HO, "bo_qua", "ton_trong")}


@_khong_nem(False)
def dat_ton_trong_dong_ho(pid: int) -> bool:
    """Biến thể gui_off_dh của chế độ chạy: SetProcessInformation(ProcessPowerThrottling) lên tiến trình `pid` với
    ControlMask = EXECUTION_SPEED | IGNORE_TIMER_RESOLUTION, StateMask = 0, tức tắt EcoQoS VÀ luôn tôn trọng yêu cầu độ
    phân giải đồng hồ của tiến trình. Chỉ dùng cho tiến trình con của công cụ (cờ mất theo tiến trình); không bao giờ
    cho chính tiến trình này (pid None → False). Không đổi thiết lập máy."""
    import ctypes
    from ctypes import wintypes

    if pid is None:
        return False
    dat = _ham("kernel32", "SetProcessInformation", wintypes.BOOL, wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
               wintypes.DWORD)
    trang_thai = (wintypes.ULONG * 3)(1, _BIT_ECOQOS | _BIT_DONG_HO, 0)
    return _voi_tien_trinh(int(pid), 0x0200, lambda h: bool(dat(h, _DIEU_TIET, trang_thai, ctypes.sizeof(trang_thai))))


class CuaSoWin32:
    """Một cửa sổ cấp cao (HWND) của tiến trình khác. Không hàm nào ném lỗi. Tọa độ là điểm ảnh vật lý khi tiến trình
    điều khiển đã gọi `dat_dpi_vat_ly()` (lệnh `do` gọi lúc đầu)."""

    def __init__(self, hwnd: int):
        self.hwnd = int(hwnd)

    @_khong_nem(None)
    def _hien(self, lenh: int) -> None:
        import ctypes
        from ctypes import wintypes

        _ham("user32", "ShowWindow", wintypes.BOOL, wintypes.HWND, ctypes.c_int)(self.hwnd, lenh)

    def thu_nho(self) -> None:
        self._hien(6)                                  # SW_MINIMIZE (kích hoạt cửa sổ kế tiếp)

    def khoi_phuc(self) -> None:
        self._hien(9)                                  # SW_RESTORE (kích hoạt nếu Windows cho)

    def hien_khong_kich_hoat(self) -> None:
        self._hien(4)                                  # SW_SHOWNOACTIVATE: đang thu nhỏ thì hiện lại, không lấy focus

    def an(self) -> None:
        self._hien(0)                                  # SW_HIDE

    @_khong_nem(False)
    def len_truoc(self) -> bool:
        """SetForegroundWindow rồi kiểm lại. Windows có thể từ chối (ví dụ người đang gõ phím): khi đó False."""
        from ctypes import wintypes

        _ham("user32", "SetForegroundWindow", wintypes.BOOL, wintypes.HWND)(self.hwnd)
        return _ham("user32", "GetForegroundWindow", wintypes.HWND)() == self.hwnd

    @_khong_nem(None)
    def dua_len_dau(self) -> None:
        """Đưa cửa sổ lên đầu thứ tự Z mà không kích hoạt (khi `len_truoc` bị từ chối): đặt luôn-trên-cùng rồi bỏ
        ngay."""
        import ctypes
        from ctypes import wintypes

        dat = _ham("user32", "SetWindowPos", wintypes.BOOL, wintypes.HWND, ctypes.c_ssize_t, ctypes.c_int,
                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
        co = 0x0002 | 0x0001 | 0x0010                  # SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        dat(self.hwnd, -1, 0, 0, 0, 0, co)             # HWND_TOPMOST
        dat(self.hwnd, -2, 0, 0, 0, 0, co)             # HWND_NOTOPMOST: nằm trên mọi cửa sổ thường

    @property
    @_khong_nem(False)
    def ton_tai(self) -> bool:
        from ctypes import wintypes

        return bool(_ham("user32", "IsWindow", wintypes.BOOL, wintypes.HWND)(self.hwnd))

    @property
    @_khong_nem(None)
    def thu_nho_roi(self) -> bool | None:
        from ctypes import wintypes

        return bool(_ham("user32", "IsIconic", wintypes.BOOL, wintypes.HWND)(self.hwnd))

    @property
    @_khong_nem(None)
    def hien(self) -> bool | None:
        from ctypes import wintypes

        return bool(_ham("user32", "IsWindowVisible", wintypes.BOOL, wintypes.HWND)(self.hwnd))

    @property
    @_khong_nem(None)
    def tren_cung(self) -> bool | None:
        """Cửa sổ có kiểu WS_EX_TOPMOST."""
        import ctypes
        from ctypes import wintypes

        ten = "GetWindowLongPtrW" if ctypes.sizeof(ctypes.c_void_p) == 8 else "GetWindowLongW"
        kieu = _ham("user32", ten, ctypes.c_ssize_t, wintypes.HWND, ctypes.c_int)(self.hwnd, -20)     # GWL_EXSTYLE
        return bool(kieu & 0x0008)

    @_khong_nem(None)
    def khung(self) -> tuple[int, int, int, int] | None:
        """GetWindowRect (gồm cả viền vô hình của cửa sổ có khung; dùng cho màn che không viền)."""
        import ctypes
        from ctypes import wintypes

        r = _ct().RECT()
        ok = _ham("user32", "GetWindowRect", wintypes.BOOL, wintypes.HWND, ctypes.POINTER(_ct().RECT))(
            self.hwnd, ctypes.byref(r))
        return (r.left, r.top, r.right, r.bottom) if ok else None

    @_khong_nem(None)
    def khung_nhin_thay(self) -> tuple[int, int, int, int] | None:
        """Khung nhìn thấy của cửa sổ: DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS), không có viền vô hình."""
        import ctypes
        from ctypes import wintypes

        r = _ct().RECT()
        hr = _ham("dwmapi", "DwmGetWindowAttribute", ctypes.c_long, wintypes.HWND, wintypes.DWORD, ctypes.c_void_p,
                  wintypes.DWORD)(self.hwnd, 9, ctypes.byref(r), ctypes.sizeof(r))
        return (r.left, r.top, r.right, r.bottom) if hr == 0 else None

    @_khong_nem(None)
    def man_hinh(self) -> tuple[int, int, int, int] | None:
        """Khung màn hình chứa cửa sổ (MonitorFromWindow MONITOR_DEFAULTTONEAREST + GetMonitorInfoW rcMonitor)."""
        import ctypes
        from ctypes import wintypes

        ct = _ct()
        mon = _ham("user32", "MonitorFromWindow", wintypes.HANDLE, wintypes.HWND, wintypes.DWORD)(self.hwnd, 2)
        if not mon:
            return None
        info = ct.MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if not _ham("user32", "GetMonitorInfoW", wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(ct.MONITORINFO))(
                mon, ctypes.byref(info)):
            return None
        r = info.rcMonitor
        return r.left, r.top, r.right, r.bottom

    @_khong_nem(False)
    def dat_tren_cung(self, khung: tuple[int, int, int, int]) -> bool:
        """SetWindowPos(HWND_TOPMOST) phủ đúng `khung` (trái, trên, phải, dưới) và hiện cửa sổ, không kích hoạt (đưa
        lên trước là việc của tiến trình sở hữu cửa sổ, sau khi được cấp quyền)."""
        import ctypes
        from ctypes import wintypes

        trai, tren, phai, duoi = khung
        return bool(_ham("user32", "SetWindowPos", wintypes.BOOL, wintypes.HWND, ctypes.c_ssize_t, ctypes.c_int,
                         ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)(
            self.hwnd, -1, trai, tren, phai - trai, duoi - tren, 0x0040 | 0x0010))   # SWP_SHOWWINDOW | SWP_NOACTIVATE

    @_khong_nem(None)
    def ty_le_lo_ra(self, n: int = 3) -> float | None:
        """Phần trong n×n điểm mẫu trên khung nhìn thấy mà cửa sổ trên cùng ở đó (WindowFromPoint → GetAncestor
        GA_ROOT) chính là cửa sổ này. 1 = lộ hết, 0 = bị che ở mọi điểm mẫu; None khi thu nhỏ hoặc không đọc được."""
        from ctypes import wintypes

        khung = self.khung_nhin_thay()
        if khung is None or self.thu_nho_roi:
            return None
        trai, tren, phai, duoi = khung
        if phai <= trai or duoi <= tren:
            return None
        ct = _ct()
        tai_diem = _ham("user32", "WindowFromPoint", wintypes.HWND, ct.POINT)
        goc = _ham("user32", "GetAncestor", wintypes.HWND, wintypes.HWND, wintypes.UINT)
        trung = 0
        for i in range(n):
            for j in range(n):
                x = trai + (phai - trai) * (2 * i + 1) // (2 * n)
                y = tren + (duoi - tren) * (2 * j + 1) // (2 * n)
                h = tai_diem(ct.POINT(x, y))
                trung += bool(h) and goc(h, 2) == self.hwnd              # GA_ROOT
        return trung / (n * n)


def _hop_khung(*khung: tuple[int, int, int, int] | None) -> tuple[int, int, int, int] | None:
    """Hình chữ nhật nhỏ nhất chứa mọi khung (trái, trên, phải, dưới) không None."""
    co = [k for k in khung if k is not None]
    if not co:
        return None
    return min(k[0] for k in co), min(k[1] for k in co), max(k[2] for k in co), max(k[3] for k in co)


def che_kin(che: CuaSoWin32 | None, gui: CuaSoWin32 | None) -> bool | None:
    """Màn che phủ kín giao diện: màn che còn, đang hiện, không thu nhỏ, luôn trên cùng (giao diện thì không); khung
    nhìn thấy của giao diện nằm trong GetWindowRect của màn che; và không điểm mẫu nào trên giao diện còn lộ ra."""
    if che is None or gui is None:
        return None
    if not (che.ton_tai and che.hien and not che.thu_nho_roi):
        return False
    if che.tren_cung is False or gui.tren_cung is True:
        return False
    k_gui, k_che = gui.khung_nhin_thay(), che.khung()
    if k_gui is None or k_che is None:
        return None
    if not (k_che[0] <= k_gui[0] and k_che[1] <= k_gui[1] and k_gui[2] <= k_che[2] and k_gui[3] <= k_che[3]):
        return False
    lo_ra = gui.ty_le_lo_ra()
    return lo_ra is None or lo_ra == 0


@_khong_nem(False)
def dat_dpi_vat_ly() -> bool:
    """Tiến trình điều khiển nhận biết DPI theo từng màn hình (v2): mọi khung đọc/ghi bằng điểm ảnh vật lý."""
    import ctypes
    from ctypes import wintypes

    try:
        f = _ham("user32", "SetProcessDpiAwarenessContext", wintypes.BOOL, ctypes.c_void_p)
    except AttributeError:
        return _ham("shcore", "SetProcessDpiAwareness", ctypes.c_long, ctypes.c_int)(2) == 0
    return bool(f(ctypes.c_void_p(-4)))                # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2


@_khong_nem([])
def chuoi_tien_trinh_cha(pid: int | None = None, toi_da: int = 8) -> list[str]:
    """Tên tệp chạy của tiến trình và các tổ tiên (cha, ông...), từ ảnh chụp Toolhelp32. Tiến trình cha đã thoát và
    pid bị dùng lại thì chuỗi có thể sai từ chỗ đó; chỉ để ghi điều kiện chạy."""
    import ctypes
    from ctypes import wintypes

    ct = _ct()
    chup = _ham("kernel32", "CreateToolhelp32Snapshot", wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD)
    dau = _ham("kernel32", "Process32FirstW", wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(ct.PROCESSENTRY32W))
    tiep = _ham("kernel32", "Process32NextW", wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(ct.PROCESSENTRY32W))
    h = chup(0x2, 0)                                    # TH32CS_SNAPPROCESS
    if not h or h == ctypes.c_void_p(-1).value:
        return []
    bang: dict[int, tuple[int, str]] = {}
    try:
        e = ct.PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = dau(h, ctypes.byref(e))
        while ok:
            bang[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile)
            ok = tiep(h, ctypes.byref(e))
    finally:
        _dong_handle(h)
    chuoi, hien_tai, da_qua = [], os.getpid() if pid is None else pid, set()
    while hien_tai in bang and hien_tai not in da_qua and len(chuoi) < toi_da:
        da_qua.add(hien_tai)
        cha, ten = bang[hien_tai]
        chuoi.append(ten)
        hien_tai = cha
    return chuoi


@_khong_nem({})
def doc_windows() -> dict:
    """Bản Windows, phiên, nâng quyền, chuỗi tiến trình cha (để ghi điều kiện chạy vào may.json)."""
    import ctypes
    from ctypes import wintypes

    ubr = None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
            ubr = winreg.QueryValueEx(k, "UBR")[0]
    except OSError:
        pass
    phien = wintypes.DWORD()
    co_phien = _ham("kernel32", "ProcessIdToSessionId", wintypes.BOOL, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))(
        os.getpid(), ctypes.byref(phien))
    return {
        "ban": platform.platform(), "build": sys.getwindowsversion().build, "ubr": ubr,
        "phien_id": phien.value if co_phien else None,
        "phien_console": _ham("kernel32", "WTSGetActiveConsoleSessionId", wintypes.DWORD)(),
        "nang_quyen": bool(_ham("shell32", "IsUserAnAdmin", wintypes.BOOL)()),
        "to_tien": chuoi_tien_trinh_cha(),
        "khoa_truoc_ms": khoa_truoc_ms(),                # thêm 02/10/2026; may.json cũ không có
    }


def _chay_powercfg(*tham_so: str) -> str | None:
    """Chạy `powercfg` chỉ để ĐỌC (không đổi gì); trả chữ in ra (xuống dòng "\\n"), None khi lỗi.

    powercfg in xuống dòng CRLF. Trả nguyên như vậy thì write_text (chế độ văn bản) trên Windows ghi thành CR CR LF:
    trình soạn thảo hiện cách dòng đôi và git coi tệp là nhị phân (gặp 02/10/2026 ở powercfg_bo_xu_ly.txt)."""
    try:
        r = subprocess.run(["powercfg", *tham_so], capture_output=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        chu = r.stdout.decode("oem", "replace")
    except LookupError:                                 # bảng mã "oem" chỉ có trên Windows
        chu = r.stdout.decode("utf-8", "replace")
    return chu.replace("\r\n", "\n")


def ghi_powercfg_bo_xu_ly(ra: Path, luc: str) -> Path:
    """Ghi `ra/powercfg_bo_xu_ly.txt`: thiết lập bộ xử lý của kế hoạch nguồn đang dùng (`powercfg /qh SCHEME_CURRENT
    SUB_PROCESSOR`, chỉ đọc), dòng đầu ghi lệnh và lúc đọc `luc`. Trả đường dẫn tệp."""
    bo_xu_ly = _chay_powercfg("/qh", "SCHEME_CURRENT", "SUB_PROCESSOR")
    dau_tep = f"$ powercfg /qh SCHEME_CURRENT SUB_PROCESSOR   ({luc}, chỉ đọc)\n"
    tep = Path(ra) / "powercfg_bo_xu_ly.txt"
    tep.write_text(dau_tep + (bo_xu_ly or "(không đọc được)\n"), encoding="utf-8")
    return tep


def _phan_tich_ke_hoach(chu: str | None) -> dict:
    m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s*(?:\((.*)\))?",
                  chu or "")
    return {"guid": m.group(1).lower(), "ten": (m.group(2) or "").strip()} if m else {"guid": None, "ten": None}


def _phan_tich_tat_man_hinh(chu: str | None) -> tuple[int | None, int | None]:
    """(AC, DC) giây của `powercfg /q SCHEME_CURRENT SUB_VIDEO VIDEOIDLE`; 0 = không bao giờ tắt. Windows bản địa hóa
    thì không có chữ "AC"/"DC": lấy hai số hex cuối (AC rồi DC)."""
    if not chu:
        return None, None
    ac = re.search(r"\bAC\b[^\n]*:\s*0x([0-9a-fA-F]+)", chu)
    dc = re.search(r"\bDC\b[^\n]*:\s*0x([0-9a-fA-F]+)", chu)
    if ac and dc:
        return int(ac.group(1), 16), int(dc.group(1), 16)
    so = re.findall(r":\s*0x([0-9a-fA-F]+)", chu)
    return (int(so[-2], 16), int(so[-1], 16)) if len(so) >= 2 else (None, None)


@_khong_nem({})
def doc_nguon() -> dict:
    """Kế hoạch nguồn, lớp phủ nguồn, điện lưới / tiết kiệm pin, thời gian tắt màn hình (chỉ đọc)."""
    import ctypes
    from ctypes import wintypes
    import uuid

    ct = _ct()
    lop_phu = None
    try:
        g = ct.GUID()
        if _ham("powrprof", "PowerGetEffectiveOverlayScheme", wintypes.DWORD, ctypes.POINTER(ct.GUID))(
                ctypes.byref(g)) == 0:
            chuoi = str(uuid.UUID(bytes_le=bytes(g)))
            lop_phu = {"guid": chuoi, "ten": LOP_PHU_NGUON.get(chuoi, "?")}
    except AttributeError:                               # Windows cũ không có hàm này
        pass
    st = ct.SYSTEM_POWER_STATUS()
    co_st = _ham("kernel32", "GetSystemPowerStatus", wintypes.BOOL, ctypes.POINTER(ct.SYSTEM_POWER_STATUS))(
        ctypes.byref(st))
    ac_s, dc_s = _phan_tich_tat_man_hinh(_chay_powercfg("/q", "SCHEME_CURRENT", "SUB_VIDEO", "VIDEOIDLE"))
    return {
        "ke_hoach": _phan_tich_ke_hoach(_chay_powercfg("/getactivescheme")),
        "lop_phu": lop_phu,
        "dien_luoi": {1: True, 0: False}.get(st.ACLineStatus) if co_st else None,
        "tiet_kiem_pin": (st.SystemStatusFlag == 1) if co_st else None,
        "tat_man_hinh_ac_s": ac_s, "tat_man_hinh_dc_s": dc_s,
    }


def doc_git() -> dict:
    """Commit HEAD (ngắn) và các dòng `git status --porcelain` của repo chứa mã đang chạy."""
    def chay(*tham_so: str) -> str | None:
        try:
            r = subprocess.run(["git", "-C", str(PROJECT_ROOT), *tham_so], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=20,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout if r.returncode == 0 else None

    commit, trang_thai = chay("rev-parse", "--short", "HEAD"), chay("status", "--porcelain")
    sua = [d for d in (trang_thai or "").splitlines() if d.strip()]
    return {"commit": commit.strip() if commit else None, "sua_doi_chua_commit": sua[:200],
            "so_tep_chua_commit": len(sua) if trang_thai is not None else None}


# ----------------------------------------------------------------------------------------------------- phép tính CPU

def tai_pct(a: ChupCpu | None, b: ChupCpu | None) -> float | None:
    """Tải toàn máy (%) giữa hai lần chụp: 100·(1 − Δidle / (Δkernel + Δuser)); kernel gồm cả idle."""
    if a is None or b is None or a.he_thong is None or b.he_thong is None:
        return None
    d_idle, d_kernel, d_user = (y - x for x, y in zip(a.he_thong, b.he_thong))
    tong = d_kernel + d_user
    if tong <= 0:
        return None
    return min(100.0, max(0.0, 100.0 * (1.0 - d_idle / tong)))


def ban_ron_lop(a: ChupCpu | None, b: ChupCpu | None, lop: dict[int, list[int]]) -> dict[int, float] | None:
    """Giây bận của từng lớp lõi giữa hai lần chụp: Σ max(0, Δkernel + Δuser − Δidle) / 1e7 trên các bộ xử lý của lớp.
    Tính bằng giây chứ không bằng tỉ lệ từng CPU: tỉ lệ hỏng ở luồng SMT anh em đang bị "đỗ" (Δkernel + Δuser =
    Δidle)."""
    if a is None or b is None or a.tung_cpu is None or b.tung_cpu is None or not lop:
        return None
    n = min(len(a.tung_cpu), len(b.tung_cpu))
    ket_qua = {}
    for cap, ds in lop.items():
        ban = 0.0
        for i in ds:
            if i < n:
                (i0, k0, u0), (i1, k1, u1) = a.tung_cpu[i], b.tung_cpu[i]
                ban += max(0, (k1 - k0) + (u1 - u0) - (i1 - i0)) / 1e7
        ket_qua[cap] = ban
    return ket_qua


def ban_ron_them(c_nen: ChupCpu | None, c0: ChupCpu | None, c1: ChupCpu | None,
                 lop: dict[int, list[int]]) -> dict[int, float] | None:
    """Giây bận THÊM của từng lớp trong lúc lập đường (c0 → c1) so với nền (c_nen → c0): bận − tốc độ nền × thời gian."""
    nen, trong = ban_ron_lop(c_nen, c0, lop), ban_ron_lop(c0, c1, lop)
    if nen is None or trong is None:
        return None
    t_nen, t_trong = c0.t - c_nen.t, c1.t - c0.t
    if t_nen <= 0 or t_trong <= 0:
        return None
    return {cap: trong[cap] - nen[cap] / t_nen * t_trong for cap in trong}


def ty_le_e(them: dict[int, float] | None, tg_tinh: float | None, toi_thieu: float = 0.3) -> float | None:
    """Phần CPU bận thêm rơi vào lõi E (lớp EfficiencyClass thấp nhất): E / (E + các lớp còn lại), phần âm tính là 0.
    None khi chưa tới hai lớp, hoặc tổng bận thêm < toi_thieu·tg_tinh (quá ít để nói gì; 0,3 hợp với bộ lập kế hoạch
    bận, chế độ chạy dùng 0,1 vì giao diện tải nhẹ). Chỉ là chỉ báo: bộ đếm toàn máy."""
    if not them or len(them) < 2 or not tg_tinh or tg_tinh <= 0:
        return None
    e = min(them)
    them_e = max(0.0, them[e])
    them_p = sum(max(0.0, v) for cap, v in them.items() if cap != e)
    if them_e + them_p < toi_thieu * tg_tinh:
        return None
    return them_e / (them_e + them_p)


# ------------------------------------------------------------------------------------------------- tiến trình điều khiển

def thu_tu_do(trang_thai: Sequence[str], lap: int, khoi: int, bien_the: str) -> list[tuple[int, str]]:
    """Thứ tự (lần, trạng thái) trong một khối. Lần 0 là "thuong", lượt khởi động: ngày 30/09 lần gọi đầu tiên trong
    mỗi tiến trình khác các lần sau, nên lượt này bị loại khi so sánh. Sau đó `lap` vòng các trạng thái, vòng j xoay
    (khoi + j) bước. Tiến trình không cửa sổ: 1 + lap·len(trang_thai) lần "khong_cua_so"."""
    if bien_the == "khong_cua_so":
        return [(i, "khong_cua_so") for i in range(1 + lap * len(trang_thai))]
    ds: list[tuple[int, str]] = [(0, "thuong")]
    n = len(trang_thai)
    for j in range(lap):
        k = (khoi + j) % n
        for tt in list(trang_thai[k:]) + list(trang_thai[:k]):
            ds.append((len(ds), tt))
    return ds


def _xoay(ds: Sequence[str], k: int) -> list[str]:
    k %= len(ds)
    return list(ds[k:]) + list(ds[:k])


BIEN_GIU_ECOQOS = "AUTOPARK_KEEP_ECOQOS"
"""Biến môi trường (cùng tests/conftest.py, thêm vào công cụ 02/10/2026): "1" = giữ EcoQoS mặc định của Windows ở
tiến trình nào có tự tắt EcoQoS theo biến này."""


def moi_truong_con(goc: dict[str, str] | None = None, *,
                   giu_ecoqos: bool = True) -> tuple[dict[str, str], dict[str, bool]]:
    """Biến môi trường cho tiến trình con: bỏ QT_QPA_PLATFORM (shell của tác tử hay đặt offscreen) và AUTOPARK_RRT_SEED.
    `giu_ecoqos` (thêm 02/10/2026): True đặt AUTOPARK_KEEP_ECOQOS=1, False bỏ biến đó. Mặc định True: chế độ lập đường
    và biến thể gui_system đo mặc định của Windows như ngày 02/10/2026, kể cả khi ứng dụng đã tự tắt EcoQoS.
    Trả (env, {"QT_QPA_PLATFORM_da_bo": bool, "AUTOPARK_RRT_SEED_da_bo": bool, "AUTOPARK_KEEP_ECOQOS_dat": bool})."""
    env = dict(os.environ if goc is None else goc)
    da_bo = {f"{khoa}_da_bo": env.pop(khoa, None) is not None for khoa in ("QT_QPA_PLATFORM", "AUTOPARK_RRT_SEED")}
    if giu_ecoqos:
        env[BIEN_GIU_ECOQOS] = "1"
    else:
        env.pop(BIEN_GIU_ECOQOS, None)
    da_bo[f"{BIEN_GIU_ECOQOS}_dat"] = giu_ecoqos
    return env, da_bo


class TienTrinhCon:
    """Một tiến trình con của công cụ (`con`, `nen`, `che`): lệnh một dòng qua stdin, thông điệp JSON một dòng qua stdout
    (stderr gộp vào stdout). Dòng không phải JSON (cảnh báo Qt, traceback) vào nhật ký qua `ghi`.

    `pid` là pid mà tiến trình con tự báo trong `san_sang`, KHÔNG phải `proc.pid`: Scripts\\python.exe của venv là trình
    khởi chạy, nó mở trình thông dịch thật làm tiến trình con (đo 02/10/2026: hai pid khác nhau). Tắt EcoQoS, đọc mức ưu
    tiên, CPU, cửa sổ đang trước đều phải theo pid thật. Kill trình khởi chạy thì tiến trình thật chết theo (trình khởi
    chạy giữ nó trong một job)."""

    def __init__(self, tham_so: Sequence[str], ten: str, *, ghi: Callable[[str], None] | None = None,
                 env: dict[str, str] | None = None):
        self.ten = ten
        self._ghi = ghi or (lambda dong: None)
        self._hang: queue.Queue = queue.Queue()
        self._het = False
        self.pid_bao: int | None = None                   # pid trong thông điệp san_sang
        self.proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", MODULE, *tham_so], cwd=PROJECT_ROOT,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     env=moi_truong_con()[0] if env is None else env,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._luong = threading.Thread(target=self._doc_stdout, daemon=True, name=f"ecoqos-{ten}")
        self._luong.start()

    @property
    def pid(self) -> int:
        """Pid của tiến trình Python thật (sau `san_sang`); trước đó là pid của Popen."""
        return self.pid_bao if self.pid_bao is not None else self.proc.pid

    @property
    def con_song(self) -> bool:
        return self.proc.poll() is None

    def _doc_stdout(self) -> None:
        for raw in iter(self.proc.stdout.readline, b""):
            dong = raw.decode("utf-8", "replace").rstrip("\r\n")
            if dong.startswith("{"):
                try:
                    tin = json.loads(dong)
                except ValueError:
                    tin = None
                if isinstance(tin, dict):
                    if tin.get("loai") == "san_sang" and isinstance(tin.get("pid"), int):
                        self.pid_bao = tin["pid"]          # gán trước khi đưa vào hàng: ai đọc được tin là thấy pid
                    self._hang.put(tin)
                    continue
            if dong.strip():
                try:
                    self._ghi(f"[{self.ten}] {dong}")
                except (OSError, ValueError):              # nhật ký đã đóng: bỏ dòng, vẫn đọc tiếp tới hết
                    pass
        self._hang.put(None)                               # hết stdout: tiến trình con đã thoát

    def gui(self, lenh: str) -> bool:
        try:
            self.proc.stdin.write((lenh + "\n").encode("utf-8"))
            self.proc.stdin.flush()
            return True
        except (OSError, ValueError):                      # tiến trình con đã thoát / stdin đã đóng
            return False

    def doc(self, het_han: float, loai: str | Iterable[str], yeu_cau: str | None = None) -> dict | None:
        """Thông điệp đầu tiên có `loai` thuộc tập cho trước (và mang đúng `yeu_cau`, nếu thông điệp có khóa đó) trong
        `het_han` giây. None khi hết giờ hoặc tiến trình con đã đóng stdout. Thông điệp khác ghi nhật ký rồi bỏ qua."""
        muon = {loai} if isinstance(loai, str) else set(loai)
        cuoi = time.monotonic() + het_han
        while True:
            con_lai = cuoi - time.monotonic()
            try:
                # từng lát ngắn để Ctrl+C có tác dụng; hết stdout thì chỉ còn đọc nốt hàng đợi
                tin = self._hang.get(timeout=0 if self._het else max(0.0, min(0.25, con_lai)))
            except queue.Empty:
                if self._het or con_lai <= 0:
                    return None
                continue
            if tin is None:
                self._het = True
                continue
            if tin.get("loai") in muon and (yeu_cau is None or "yeu_cau" not in tin or tin["yeu_cau"] == yeu_cau):
                return tin
            self._ghi(f"[{self.ten}] bỏ qua: {json.dumps(tin, ensure_ascii=False)[:300]}")

    def dong(self, cho: float = 10.0) -> int | None:
        """Đóng mềm ("thoat", đóng stdin, chờ `cho` giây), không được thì kill. Trả mã thoát."""
        if self.proc.poll() is None:
            self.gui("thoat")
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            ma = self.proc.wait(timeout=cho)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            try:
                ma = self.proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                ma = None
        self._luong.join(timeout=2.0)
        if not self._luong.is_alive():
            self.proc.stdout.close()
        return ma


class ManChe:
    """Phía điều khiển của tiến trình con `che` (màn che và, từ 02/10/2026, cửa sổ trung tính). Người dùng đóng một
    trong hai cửa sổ (Esc, bấm chuột, nút đóng) hoặc tiến trình hết giờ thì `ly_do_dong` khác rỗng: mọi lượt "bị che"
    sau đó thành BO_QUA, lượt "thu nhỏ" chỉ còn thu nhỏ (không có cửa sổ trung tính; `gui_van_o_truoc` vẫn chặn).
    `san_sang`: thông điệp san_sang của tiến trình (lấy HWND của cửa sổ trung tính để phân biệt với màn che)."""

    def __init__(self, con: TienTrinhCon, san_sang: dict | None = None):
        self.con = con
        self.cua_so: CuaSoWin32 | None = None
        self.hwnd_trung_tinh: int | None = (san_sang or {}).get("hwnd_trung_tinh")
        self.ly_do_dong = ""                     # nguoi_dung_dong | het_gio | khong_tra_loi | da_thoat

    @property
    def pid(self) -> int:
        return self.con.pid

    def con_song(self) -> bool:
        """Màn che còn dùng được. Đọc (không chờ) thông điệp nguoi_dung_dong / het_gio đang đợi trong hàng."""
        if not self.ly_do_dong:
            tin = self.con.doc(0.0, ("nguoi_dung_dong", "het_gio"))
            if tin is not None:
                self.ly_do_dong = tin["loai"]
            elif not self.con.con_song:
                self.ly_do_dong = "da_thoat"
        return not self.ly_do_dong

    def _lenh(self, lenh: str, cho_loai: str) -> dict | None:
        if not self.con_song():
            return None
        self.con.gui(lenh)
        tin = self.con.doc(CHO_MAN_CHE_S, (cho_loai, "nguoi_dung_dong", "het_gio"))
        if tin is None or tin["loai"] != cho_loai:
            self.ly_do_dong = tin["loai"] if tin is not None else "khong_tra_loi"
            return None
        return tin

    def hien(self, gui: CuaSoWin32) -> bool | None:
        """Hiện màn che phủ màn hình chứa giao diện (và cả phần cửa sổ giao diện thò ra ngoài màn hình, nếu có), luôn
        trên cùng, không kích hoạt; trả `che_kin`. None: màn che không còn. Đưa màn che lên trước: `len_truoc("che")`
        (tiến trình điều khiển chạy nền gọi SetForegroundWindow thì bị từ chối, như lượt đo 02/10/2026 02:54)."""
        tin = self._lenh("hien", "da_hien")
        if tin is None:
            return None
        self.cua_so = CuaSoWin32(int(tin["hwnd"]))
        # Qt đặt màn che ở màn hình chính; ở đây đặt lại theo màn hình của giao diện. Giao diện 1440×900 (điểm ảnh
        # logic) có thể lớn hơn màn hình khi tỉ lệ hiển thị cao: phủ cả khung cửa sổ của nó (trừ khi cửa sổ đang thu
        # nhỏ: khung khi đó là (-32000, -32000, ...)).
        khung_gui = gui.khung() if gui.thu_nho_roi is False else None
        if khung_gui is not None and min(khung_gui) <= -30000:
            khung_gui = None
        khung = _hop_khung(gui.man_hinh(), khung_gui)
        if khung is not None:
            self.cua_so.dat_tren_cung(khung)
        return self.kin(gui)

    def kin(self, gui: CuaSoWin32) -> bool | None:
        return che_kin(self.cua_so, gui) if self.con_song() else False

    def hien_trung_tinh(self) -> bool:
        """Hiện cửa sổ trung tính (không kích hoạt). False: tiến trình `che` không còn."""
        tin = self._lenh("trung_tinh", "da_hien_trung_tinh")
        if tin is None:
            return False
        if isinstance(tin.get("hwnd"), int):
            self.hwnd_trung_tinh = tin["hwnd"]
        return True

    def cap_quyen(self) -> dict | None:
        """Tiến trình `che` (khi một cửa sổ của nó đang ở trước) gọi AllowSetForegroundWindow(ASFW_ANY): thông điệp
        {"ok", "loi"}, None khi không trả lời."""
        return self._lenh("cap_quyen", "cap_quyen")

    def len_truoc(self, cua_so: str) -> dict | None:
        """Tiến trình `che` gọi SetForegroundWindow lên cửa sổ của nó (`cua_so`: "che" | "trung_tinh"): thông điệp
        {"ok", "truoc_hwnd"}, None khi không trả lời."""
        return self._lenh(f"len_truoc {cua_so}", "da_len_truoc")

    def an(self, cua_so: str | None = None) -> None:
        """Ẩn `cua_so` ("che" | "trung_tinh"), hoặc cả hai khi None."""
        self._lenh("an" if cua_so is None else f"an {cua_so}", "da_an")

    def dong(self) -> None:
        self.con.dong()


@dataclass
class NguCanhDo:
    """Những thứ một lần đo cần, tiêm được để test thay bằng đồ giả."""

    doc_may: Callable[[], TrangThaiMay] = doc_trang_thai_may
    doc_truoc: Callable[[], tuple[int | None, int | None, str]] = _cua_so_dang_truoc   # (pid, hwnd, exe), nhẹ
    chup_cpu: Callable[[], ChupCpu] = chup_cpu
    ecoqos_cua: Callable[[int], str | None] = execution_speed_throttling
    uu_tien_cua: Callable[[int], str | None] = uu_tien
    cpu_cua: Callable[[int], float | None] = cpu_tien_trinh_s
    ngu: Callable[[float], None] = time.sleep
    gui: CuaSoWin32 | None = None
    che: ManChe | None = None
    cho: float = 5.0
    khoi: int = 0
    bien_the: str = "gui_system"
    lop_cpu: dict[int, list[int]] | None = None
    ghi_chu: str = ""                            # ghi chú chung của cả khối (ví dụ "khong_tat_duoc_ecoqos")


def _phan_loai_truoc(pid: int | None, hwnd: int | None, exe: str, pid_gui: int | None, che) -> str:
    """Tên cửa sổ đang ở trước: giao_dien (mọi cửa sổ của tiến trình giao diện) | trung_tinh | man_che (các cửa sổ khác
    của tiến trình `che`) | khac:<tệp chạy> | "" (không có cửa sổ nào ở trước)."""
    if hwnd is None and pid is None:
        return ""
    if pid_gui is not None and pid == pid_gui:
        return "giao_dien"
    if che is not None and pid == che.pid:
        hwnd_tt = getattr(che, "hwnd_trung_tinh", None)
        return "trung_tinh" if hwnd_tt is not None and hwnd == hwnd_tt else "man_che"
    return f"khac:{exe or '?'}"


def _cua_so_truoc(may: TrangThaiMay, pid: int | None, che: ManChe | None) -> str:
    return _phan_loai_truoc(may.truoc_pid, may.truoc_hwnd, may.truoc_exe, pid, che)


@dataclass
class KetQuaChuyen:
    """Kết quả `chuyen_trang_thai`: hai khóa của dòng, lượt có dựa vào cửa sổ trung tính không, và (lý do, thông điệp)
    khi không đặt được trạng thái (lượt thành BO_QUA, không lập đường)."""

    cap_quyen_truoc: str | None = None
    ket_qua_dua_ra_truoc: str | None = None
    dung_trung_tinh: bool = False
    bo_qua: tuple[str, str] | None = None


def _truoc_luc_nay(nc: NguCanhDo, pid_gui: int | None) -> str:
    pid, hwnd, exe = nc.doc_truoc()
    return _phan_loai_truoc(pid, hwnd, exe, pid_gui, nc.che)


def _hoi_con(con, lenh: str, loai: str, yeu_cau: str) -> dict | None:
    """Gửi `<lenh> <yeu_cau>` cho tiến trình giao diện; thông điệp `loai` mang đúng mã, None khi quá CHO_MAN_CHE_S."""
    return con.doc(CHO_MAN_CHE_S, loai, yeu_cau) if con.gui(f"{lenh} {yeu_cau}") else None


def _cap_quyen(con, che, truoc: str, yeu_cau: str) -> str:
    """Bảo tiến trình đang giữ cửa sổ ở trước (`truoc`) gọi AllowSetForegroundWindow(ASFW_ANY); trả giá trị cho
    `cap_quyen_truoc`. Cửa sổ ở trước không thuộc công cụ thì không ai cấp được: "khong_ai:<cửa sổ đó>"."""
    if truoc == "giao_dien":
        tin = _hoi_con(con, "cap_quyen", "cap_quyen", yeu_cau)
    elif truoc in ("trung_tinh", "man_che") and che is not None:
        tin = che.cap_quyen()
    else:
        return f"khong_ai:{truoc or 'khong_co'}"
    if tin is None:
        return f"{truoc}:khong_tra_loi"
    return f"{truoc}:ok" if tin.get("ok") else f"{truoc}:tu_choi:{tin.get('loi')}"


def _dua_ra_truoc(con, nc: NguCanhDo, dich: str, yeu_cau: str) -> tuple[str | None, bool | None]:
    """Đưa cửa sổ `dich` lên trước. Cửa sổ đang ở trước (đọc NGAY lúc này, sau các bước trước đó) thuộc tiến trình khác
    tiến trình của `dich` thì tiến trình đó cấp quyền trước; rồi tiến trình sở hữu `dich` gọi SetForegroundWindow lên
    chính cửa sổ đó. Trả (cap_quyen_truoc, BOOL của SetForegroundWindow; None khi không trả lời)."""
    truoc = _truoc_luc_nay(nc, con.pid)
    cap = None
    if _TIEN_TRINH_CUA.get(truoc) != _TIEN_TRINH_CUA[dich]:
        cap = _cap_quyen(con, nc.che, truoc, f"q{yeu_cau}")
    if dich == "giao_dien":
        tin = _hoi_con(con, "len_truoc", "len_truoc", f"t{yeu_cau}")
    else:
        tin = nc.che.len_truoc("che" if dich == "man_che" else "trung_tinh")
    return cap, (None if tin is None else bool(tin.get("ok")))


def _ket_qua_ra_truoc(dich: str, ok: bool | None, sau: str) -> str:
    """Giá trị `ket_qua_dua_ra_truoc` từ cửa sổ đang ở trước đọc lại sau khi đổi trạng thái (`sau`)."""
    if sau == dich:
        return f"{dich}:ok"
    ma = "khong_tra_loi" if ok is None else ("khong_o_truoc" if ok else "tu_choi")
    return f"{dich}:{ma}:{sau or 'khong_co'}"


def chuyen_trang_thai(con, trang_thai: str, nc: NguCanhDo, lan: int) -> KetQuaChuyen:
    """Bước 1 của một lần đo (viết lại 02/10/2026): đặt giao diện vào `trang_thai` và đưa `DICH_TRUOC[trang_thai]` lên
    trước bằng `_dua_ra_truoc` (cấp quyền từ tiến trình đang ở trước, rồi tiến trình sở hữu cửa sổ đích tự gọi
    SetForegroundWindow). Cửa sổ đích lên trước TRƯỚC khi thu nhỏ giao diện hay ẩn cửa sổ đang ở trước: SW_MINIMIZE / ẩn
    cửa sổ đang ở trước để Windows tự kích hoạt "cửa sổ kế tiếp" (ở lượt đo 02/10/2026 02:54: thường là giao diện đã
    thu nhỏ, có lần là Code.exe), và khi một ứng dụng ngoài công cụ ở trước thì không ai cấp quyền được nữa.
    - thường: khôi phục giao diện (SW_RESTORE), giao diện tự lên trước; chưa ở trước thì tiến trình điều khiển thử
      SetForegroundWindow rồi đưa lên đầu thứ tự Z (không kích hoạt); sau cùng ẩn màn che và cửa sổ trung tính.
    - thu nhỏ: hiện cửa sổ trung tính, đưa nó lên trước, rồi thu nhỏ giao diện (SW_MINIMIZE) và ẩn màn che. Tiến trình
      `che` không còn thì chỉ thu nhỏ ("trung_tinh:khong_hien:...").
    - bị che: hiện lại giao diện nếu đang thu nhỏ (SW_SHOWNOACTIVATE), hiện màn che phủ kín, đưa màn che lên trước, ẩn
      cửa sổ trung tính. Màn che không còn thì `bo_qua`.
    Bước nào bị từ chối thì chỉ ghi lại; lý do loại `gui_van_o_truoc` / `gui_khong_o_truoc` (đọc lúc bấm) quyết định."""
    gui, che = nc.gui, nc.che
    kq = KetQuaChuyen()
    che_song = che is not None and che.con_song()
    dich, yeu_cau = DICH_TRUOC[trang_thai], str(lan)
    ok: bool | None = None
    if trang_thai == "bi_che":
        if not che_song:
            kq.bo_qua = (che.ly_do_dong if che is not None else "khong_co_man_che", "màn che không còn")
            return kq
        gui.hien_khong_kich_hoat()
        if che.hien(gui) is None:
            kq.bo_qua = (che.ly_do_dong or "man_che_khong_hien", "màn che không hiện được")
            return kq
        kq.cap_quyen_truoc, ok = _dua_ra_truoc(con, nc, dich, yeu_cau)
        che.an("trung_tinh")
    elif trang_thai == "thu_nho":
        if che_song and che.hien_trung_tinh():
            kq.dung_trung_tinh = True
            kq.cap_quyen_truoc, ok = _dua_ra_truoc(con, nc, dich, yeu_cau)
        gui.thu_nho()
        if che is not None:
            che.an("che")
    else:
        gui.khoi_phuc()
        kq.cap_quyen_truoc, ok = _dua_ra_truoc(con, nc, dich, yeu_cau)
        if _truoc_luc_nay(nc, con.pid) != "giao_dien" and not gui.len_truoc():
            gui.dua_len_dau()                    # không được quyền đặt foreground: ít nhất không bị cửa sổ khác che
        if che is not None:
            che.an()
    sau = _truoc_luc_nay(nc, con.pid)
    if trang_thai == "thu_nho" and not kq.dung_trung_tinh:
        kq.ket_qua_dua_ra_truoc = f"{dich}:khong_hien:{sau or 'khong_co'}"
    else:
        kq.ket_qua_dua_ra_truoc = _ket_qua_ra_truoc(dich, ok, sau)
    return kq


def do_mot_lan(con, lan: int, trang_thai: str, nc: NguCanhDo) -> dict:
    """Một lần đo: đặt trạng thái cửa sổ (`chuyen_trang_thai`), chờ `nc.cho` giây (2 s cuối là nền CPU), đọc máy, bấm
    "Tìm đường đỗ" (lệnh `plan <lan>`, chờ tối đa CHO_KET_QUA_S), đọc lại. Trả một dòng đủ khóa COT."""
    t_dau = time.perf_counter()
    dong = dict.fromkeys(COT)
    dong.update(thoi_diem=time.strftime("%H:%M:%S"), khoi=nc.khoi, bien_the=nc.bien_the, pid=con.pid, lan=lan,
                khoi_dong=(lan == 0), trang_thai=trang_thai, thong_diep="")
    ghi_chu = [nc.ghi_chu] if nc.ghi_chu else []
    gui, che = nc.gui, nc.che

    def bo_qua(ly_do: str, thong_diep: str) -> dict:
        dong.update(ket_qua="BO_QUA", thong_diep=thong_diep, ghi_chu=";".join(dict.fromkeys(ghi_chu + [ly_do])))
        return dong

    # 1. trạng thái cửa sổ
    if trang_thai in TRANG_THAI and gui is None:
        return bo_qua("khong_co_cua_so", "biến thể này không có cửa sổ giao diện")
    chuyen = KetQuaChuyen()
    if trang_thai in TRANG_THAI:
        chuyen = chuyen_trang_thai(con, trang_thai, nc, lan)
        dong.update(cap_quyen_truoc=chuyen.cap_quyen_truoc, ket_qua_dua_ra_truoc=chuyen.ket_qua_dua_ra_truoc)
        if chuyen.bo_qua is not None:
            return bo_qua(*chuyen.bo_qua)

    # 2. chờ ổn định; nền CPU là 2 s cuối
    nc.ngu(max(0.0, nc.cho - 2.0))
    c_nen = nc.chup_cpu()
    nc.ngu(2.0)
    may0 = nc.doc_may()
    ecoqos, muc_uu_tien, cpu0 = nc.ecoqos_cua(con.pid), nc.uu_tien_cua(con.pid), nc.cpu_cua(con.pid)
    if gui is not None:
        dong.update(gui_thu_nho=gui.thu_nho_roi, gui_hien=gui.hien, gui_lo_ra=_tron(gui.ty_le_lo_ra(), 3))
    if trang_thai == "bi_che":
        dong["che_kin"] = che.kin(gui)
    c0 = nc.chup_cpu()

    # 3. bấm
    yeu_cau = str(lan)
    kq = con.doc(CHO_KET_QUA_S, ("ket_qua", "loi"), yeu_cau) if con.gui(f"plan {yeu_cau}") else None

    # 4. đọc lại
    c1 = nc.chup_cpu()
    t_sau = time.perf_counter()
    may1 = nc.doc_may()
    cpu1 = nc.cpu_cua(con.pid)

    dong.update(ecoqos=ecoqos or "khong_doc_duoc", uu_tien=muc_uu_tien or "khong_doc_duoc",
                phien=may0.phien, ket_noi=may0.ket_noi, ban_lam_viec=may0.ban_lam_viec, man_hinh=may0.man_hinh,
                vang_s=_tron(may0.vang_s, 3), phien_sau=may1.phien, man_hinh_sau=may1.man_hinh,
                vang_s_sau=_tron(may1.vang_s, 3), cua_so_truoc=_cua_so_truoc(may0, con.pid, che))
    if kq is None:
        dong.update(ket_qua="KHONG_TRA_LOI", thong_diep=(f"không có kết quả trong {CHO_KET_QUA_S:.0f} s" if con.con_song
                                                         else "tiến trình con đã thoát"))
    elif kq.get("loai") == "loi":
        ghi_chu.append("dau_do_tu_choi")
        dong.update(ket_qua="BO_QUA", thong_diep=str(kq.get("thong_diep", ""))[:200])
    else:
        for khoa in ("ket_qua", "tg_tinh_s", "tg_giao_dien_s", "tre_poll_s", "elapsed_s", "cusps", "dai_m", "nac",
                     "thong_diep"):
            dong[khoa] = kq.get(khoa)
    dong["tai_nen_pct"] = _tron(tai_pct(c_nen, c0), 1)
    dong["tai_trong_pct"] = _tron(tai_pct(c0, c1), 1)
    dong["cpu_tien_trinh_s"] = _tron(cpu1 - cpu0, 3) if cpu0 is not None and cpu1 is not None else None
    them = ban_ron_them(c_nen, c0, c1, nc.lop_cpu) if nc.lop_cpu else None
    if them:
        e = min(them)
        dong["ban_ron_e_s"] = round(max(0.0, them[e]), 3)
        dong["ban_ron_p_s"] = round(sum(max(0.0, v) for cap, v in them.items() if cap != e), 3)
        dong["ty_le_e"] = _tron(ty_le_e(them, dong["tg_tinh_s"]), 3)
    if (trang_thai == "bi_che" or chuyen.dung_trung_tinh) and not che.con_song():    # người dùng đóng giữa lượt
        ghi_chu.append(che.ly_do_dong)
        dong.update(ket_qua="BO_QUA", thong_diep=f"{dong['ket_qua']}: {dong['thong_diep'] or ''}"[:200])
    if may1.vang_s is not None and may1.vang_s + 0.25 < t_sau - t_dau:
        ghi_chu.append("nguoi_dung_thao_tac")             # có phím/chuột sau khi lượt này bắt đầu
    dong["ghi_chu"] = ";".join(dict.fromkeys(g for g in ghi_chu if g))
    return dong


def viet_kich_ban(ca: str, ra: Path | str) -> tuple[Path, float]:
    """Ghi ca khó `ca` (bản sao sâu, cấu hình xe configs/vehicle_default.json) thành `ra/ca_<ca>.json`, nạp lại như
    giao diện nạp, và trả (đường dẫn, độ lệch lớn nhất của xuất phát / đích / sa bàn / vật cản / ô đỗ). Ca không có thì
    ValueError."""
    from autopark.evaluation.hard_cases import build_cases
    from autopark.storage.scenario_store import load_scenario, load_vehicle_config, save_scenario

    cfg = load_vehicle_config(VEHICLE_CONFIG)
    cac_ca = build_cases(cfg)
    if ca not in cac_ca:
        raise ValueError(f"không có ca {ca!r}; các ca: {', '.join(sorted(cac_ca))}")
    goc = copy.deepcopy(cac_ca[ca].scenario)
    goc.vehicle_config_path = VEHICLE_CONFIG
    duong_dan = save_scenario(goc, Path(ra) / f"ca_{ca}.json")
    lai = load_scenario(duong_dan)
    lai.sync_goal(load_vehicle_config(lai.vehicle_config_path))      # như Session(scenario, cfg) của giao diện
    return duong_dan, do_lech_kich_ban(goc, lai)


def viet_kich_ban_tep(nguon: Path | str, ra: Path | str) -> tuple[Path, float]:
    """Như `viet_kich_ban` cho một tệp kịch bản (thêm 02/10/2026, chế độ chạy): nạp `nguon` (đường dẫn cấu hình xe tương
    đối theo tệp nguồn), ghi `ra/kich_ban_<tên tệp>.json` (đường dẫn cấu hình xe tính lại theo `ra`), nạp lại; trả
    (đường dẫn, độ lệch lớn nhất). Hai bản đều `sync_goal` như `Session(scenario, cfg)` của giao diện."""
    from autopark.storage.scenario_store import load_scenario, load_vehicle_config, save_scenario

    goc = load_scenario(nguon)
    goc.sync_goal(load_vehicle_config(goc.vehicle_config_path))
    duong_dan = save_scenario(copy.deepcopy(goc), Path(ra) / f"kich_ban_{Path(nguon).stem}.json")
    lai = load_scenario(duong_dan)
    lai.sync_goal(load_vehicle_config(lai.vehicle_config_path))
    return duong_dan, do_lech_kich_ban(goc, lai)


def do_lech_kich_ban(a, b) -> float:
    """Độ lệch lớn nhất (m hoặc rad) giữa hai kịch bản; khác cấu trúc (số vật cản, có/không ô đỗ, kiểu đỗ) là vô cực."""
    from autopark.domain.types import wrap_angle

    def tu_the(p, q) -> list[float]:
        return [abs(p.x - q.x), abs(p.y - q.y), abs(wrap_angle(p.yaw - q.yaw))]

    lech = tu_the(a.start, b.start) + tu_the(a.goal.pose, b.goal.pose)
    lech += [abs(a.goal.tolerance_xy - b.goal.tolerance_xy), abs(a.goal.tolerance_yaw - b.goal.tolerance_yaw)]
    lech += [abs(x - y) for x, y in zip(a.bounds.to_dict().values(), b.bounds.to_dict().values())]
    vat_b = {o.id: o for o in b.obstacles}
    if len(a.obstacles) != len(b.obstacles) or set(vat_b) != {o.id for o in a.obstacles} or a.mode != b.mode:
        return math.inf
    for o in a.obstacles:
        p = vat_b[o.id]
        lech += [abs(o.cx - p.cx), abs(o.cy - p.cy), abs(o.width - p.width), abs(o.height - p.height),
                 abs(wrap_angle(o.yaw - p.yaw))]
    if (a.slot is None) != (b.slot is None):
        return math.inf
    if a.slot is not None:
        lech += [abs(a.slot.cx - b.slot.cx), abs(a.slot.cy - b.slot.cy), abs(wrap_angle(a.slot.yaw - b.slot.yaw)),
                 abs(a.slot.length - b.slot.length), abs(a.slot.width - b.slot.width)]
    return max(lech)


def dong_console(dong: dict) -> str:
    """Một dòng in ra màn hình / nhat_ky.txt cho mỗi lần đo. Lượt có cửa sổ ghi thêm cửa sổ ở trước lúc bấm, và bước đưa
    cửa sổ ra trước khi nó không thành (thêm 02/10/2026)."""
    e = dong.get("ty_le_e")
    ly_do = ly_do_loai(dong)
    truoc = ""
    if dong.get("trang_thai") in TRANG_THAI and dong.get("cua_so_truoc") is not None:     # None: bỏ trước khi đọc
        truoc = f" ở trước={dong['cua_so_truoc'] or 'không có'}"
        ra_truoc = dong.get("ket_qua_dua_ra_truoc")
        if ra_truoc and ra_truoc != f"{DICH_TRUOC[dong['trang_thai']]}:ok":
            truoc += f" (đưa ra trước: {ra_truoc}; cấp quyền: {dong.get('cap_quyen_truoc') or 'không cần'})"
    return (f"{dong.get('thoi_diem')} khối {dong.get('khoi')} {dong.get('bien_the')} lần {dong.get('lan')} "
            f"{dong.get('trang_thai')}: {dong.get('ket_qua')} {_so(dong.get('tg_tinh_s'))} s "
            f"(giao diện {_so(dong.get('tg_giao_dien_s'))} s) ecoqos={dong.get('ecoqos')} phiên={dong.get('phien')} "
            f"màn hình={dong.get('man_hinh')} tải nền {_so(dong.get('tai_nen_pct'), 0)} % "
            f"lõi E {_so(None if e is None else 100 * e, 0)} %" + truoc + (f" [loại: {ly_do}]" if ly_do else ""))


class _DungDo(RuntimeError):
    """Dừng cả lượt đo (tiến trình con không khởi động, cửa sổ bị đóng...)."""


def _doc_jsonl(tep: Path) -> list[dict]:
    if not tep.exists():
        return []
    return [json.loads(d) for d in tep.read_text(encoding="utf-8").splitlines() if d.strip()]


def _ghi_json(tep: Path, du_lieu: dict) -> None:
    tep.write_text(json.dumps(_sach(du_lieu), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _bay_gio() -> str:
    return time.strftime("%d/%m/%Y %H:%M:%S")


def _ten_cac_ca() -> list[str]:
    from autopark.evaluation.hard_cases import build_cases
    from autopark.storage.scenario_store import load_vehicle_config

    return sorted(build_cases(load_vehicle_config(VEHICLE_CONFIG)))


def _tach_ds(chuoi: str) -> list[str]:
    return [x.strip() for x in chuoi.split(",") if x.strip()]


def chay_do(args, argv: Sequence[str]) -> int:
    """Lệnh `do`. Mã thoát: 0 khi mọi lần đo đã có dòng (kể cả dòng bị loại khi so sánh); 1 khi phải dừng giữa chừng
    (tiến trình con không khởi động trong 60 s, cửa sổ bị ai đó đóng, Ctrl+C), các dòng đã ghi vẫn giữ và tom_tat.txt
    vẫn được viết; 2 khi tham số sai."""
    def loi(thong_diep: str) -> int:
        print(f"Lỗi: {thong_diep}", file=sys.stderr)
        return 2

    if sys.platform != "win32":
        return loi("chỉ chạy trên Windows (EcoQoS là cơ chế của Windows 11)")
    ra = Path(args.ra)
    if (ra / "ket_qua.jsonl").exists():
        return loi(f"{ra / 'ket_qua.jsonl'} đã có: chọn thư mục mới")
    trang_thai, bien_the = _tach_ds(args.trang_thai), _tach_ds(args.bien_the)
    la = [t for t in trang_thai if t not in TRANG_THAI] + [b for b in bien_the if b not in BIEN_THE]
    if la or not trang_thai or not bien_the or len(set(trang_thai)) != len(trang_thai) \
            or len(set(bien_the)) != len(bien_the):
        return loi(f"tên lạ hoặc lặp: {', '.join(la) or '(danh sách rỗng/lặp)'}; trạng thái hợp lệ: "
                   f"{', '.join(TRANG_THAI)}; biến thể hợp lệ: {', '.join(BIEN_THE)}")
    if args.ca not in _ten_cac_ca():
        return loi(f"không có ca {args.ca!r}; các ca: {', '.join(_ten_cac_ca())}")
    if args.cho < 2:
        return loi("--cho phải ≥ 2 giây (2 s cuối dùng để đo tải nền)")
    if args.khoi < 1 or args.lap < 1:
        return loi("--khoi và --lap phải ≥ 1")

    git = doc_git()                                       # đọc trước khi tạo thư mục kết quả
    ra.mkdir(parents=True, exist_ok=True)
    dpi = dat_dpi_vat_ly()
    kich_ban, lech = viet_kich_ban(args.ca, ra)
    env, da_bo = moi_truong_con()
    lop = lop_cpu()
    han = han_lap_duong_s()
    lich = [(k, bt, thu_tu_do(trang_thai, args.lap, k, bt)) for k in range(args.khoi) for bt in _xoay(bien_the, k)]
    so_lan = sum(len(ds) for _, _, ds in lich)
    uoc_tinh_s = so_lan * (args.cho + han + 2.0) + len(lich) * 10.0     # cận trên: mọi lần đều hết hạn
    may_dau = doc_trang_thai_may()
    may = {
        "cong_cu": MODULE, "lenh": f"python -X utf8 -m {MODULE} " + subprocess.list2cmdline(list(argv)),
        "python_exe": sys.executable,
        "bat_dau": _bay_gio(), "ket_thuc": None, "git": git, "windows": doc_windows(),
        "cpu": {"logic": os.cpu_count(), "lop": {str(k): v for k, v in (lop or {}).items()} or None},
        "nguon": doc_nguon(), "moi_truong": da_bo, "dpi_vat_ly": dpi,
        "python": sys.version.split()[0], "pyside6": _phien_ban("PySide6"),
        "ca": args.ca, "kich_ban": kich_ban.name, "cau_hinh": "configs/vehicle_default.json",
        "kich_ban_lech": lech if math.isfinite(lech) else "khac_cau_truc",
        "han_lap_duong_s": han, "khoi": args.khoi, "lap": args.lap, "cho_s": args.cho, "trang_thai": trang_thai,
        "bien_the": bien_the, "so_lan_du_kien": so_lan, "uoc_tinh_s": round(uoc_tinh_s),
        "trang_thai_may_dau": may_dau.to_dict(), "trang_thai_may_cuoi": None, "so_dong": 0, "dung_giua_chung": "",
    }
    _ghi_json(ra / "may.json", may)
    ghi_powercfg_bo_xu_ly(ra, may["bat_dau"])

    khoa_ghi = threading.Lock()
    nhat_ky = (ra / "nhat_ky.txt").open("a", encoding="utf-8")

    def ghi(dong: str) -> None:
        with khoa_ghi:
            if not nhat_ky.closed:                        # luồng đọc của tiến trình con có thể còn chạy lúc kết thúc
                nhat_ky.write(dong + "\n")
                nhat_ky.flush()

    def in_ra(dong: str) -> None:
        print(dong, flush=True)
        ghi(dong)

    in_ra(f"{_bay_gio()} Đo EcoQoS của giao diện: ca {args.ca}, {args.khoi} khối × {len(bien_the)} biến thể, {so_lan} "
          f"lần lập đường, ước tính ≤ {math.ceil(uoc_tinh_s / 60)} phút. Kết quả: {ra}")
    in_ra("Đừng dùng máy trong lúc đo (một lần nhấn phím / chuột làm mất quyền đặt cửa sổ ở trước). Màn che và cửa sổ "
          "trung tính: Esc hoặc bấm chuột để đóng (các lượt 'bị che' còn lại bị bỏ).")
    if lech:
        in_ra(f"CẢNH BÁO: kịch bản lệch {f'{lech:.3g}' if math.isfinite(lech) else 'khác cấu trúc'} sau khi lưu và nạp "
              f"lại (vẫn đo; ghi trong tóm tắt)")
    if not may_dau.nhin_thay_duoc:
        in_ra(f"CẢNH BÁO: lúc bắt đầu phiên={may_dau.phien}, kết nối={may_dau.ket_noi}, bàn làm việc="
              f"'{may_dau.ban_lam_viec}', màn hình={may_dau.man_hinh}. {GIAI_THICH_KHOA}")

    tien_trinh: list[TienTrinhCon] = []
    che: ManChe | None = None
    so_dong, ma, ly_do_dung = 0, 0, ""

    def khoi_dong(tham_so: list[str], ten: str) -> tuple[TienTrinhCon, dict]:
        p = TienTrinhCon(tham_so, ten, ghi=ghi, env=env)
        tien_trinh.append(p)
        tin = p.doc(CHO_SAN_SANG_S, ("san_sang", "loi"))
        if tin is None or tin.get("loai") != "san_sang":
            raise _DungDo(f"tiến trình {ten} không sẵn sàng trong {CHO_SAN_SANG_S:.0f} s: "
                          f"{(tin or {}).get('thong_diep', 'không trả lời')}")
        ghi(f"{_bay_gio()} {ten}: pid {p.pid} (Popen {p.proc.pid}), {json.dumps(tin, ensure_ascii=False)}")
        return p, tin

    try:
        if any(t in ("thu_nho", "bi_che") for t in trang_thai) and any(b != "khong_cua_so" for b in bien_the):
            toi_da = min(1800.0, uoc_tinh_s + 120.0)       # màn che và cửa sổ trung tính (thu nhỏ) cùng tiến trình
            che = ManChe(*khoi_dong(["che", "--toi-da", f"{toi_da:.0f}"], "che"))
        with (ra / "ket_qua.jsonl").open("a", encoding="utf-8") as tep:
            for khoi, bt, ds in lich:
                lenh = ["nen" if bt == "khong_cua_so" else "con", "--kich-ban", str(kich_ban)]
                p, tin = khoi_dong(lenh, bt)
                gui = CuaSoWin32(int(tin["hwnd"])) if bt != "khong_cua_so" and tin.get("hwnd") else None
                ghi_chu = ""
                kiem = kiem_gui_system(tin.get("ecoqos")) if bt == "gui_system" else "ok"   # thêm 02/10/2026
                if kiem == "khong_giu_duoc_ecoqos":
                    ghi_chu = "khong_giu_duoc_ecoqos"
                    in_ra(f"CẢNH BÁO: EcoQoS của giao diện (pid {p.pid}) lúc sẵn sàng là {tin.get('ecoqos')}, không "
                          f"phải mặc định của Windows (system); các dòng của khối này bị loại")
                elif kiem == "khong_doc_duoc":
                    in_ra(f"CẢNH BÁO: giao diện (pid {p.pid}) lúc sẵn sàng {ECOQOS_KHONG_DOC_DUOC}: không kiểm được "
                          f"gui_system còn ở mặc định của Windows; các dòng của khối này vẫn được giữ")
                if bt == "gui_off":
                    tat = disable_power_throttling(p.pid)
                    sau = execution_speed_throttling(p.pid)
                    ghi(f"{_bay_gio()} gui_off: disable_power_throttling({p.pid}) = {tat}, EcoQoS đọc lại: {sau}")
                    if not (tat and sau == "off"):
                        ghi_chu = "khong_tat_duoc_ecoqos"
                        in_ra(f"CẢNH BÁO: không tắt được EcoQoS cho pid {p.pid} (đọc lại: {sau}); các dòng của khối "
                              f"này bị loại")
                nc = NguCanhDo(gui=gui, che=che if gui is not None else None, cho=args.cho, khoi=khoi, bien_the=bt,
                               lop_cpu=lop, ghi_chu=ghi_chu)
                for lan, tt in ds:
                    if not p.con_song or (gui is not None and not gui.ton_tai):
                        raise _DungDo(f"tiến trình {bt} (pid {p.pid}) đã thoát hoặc cửa sổ đã bị đóng, "
                                      f"trước lần {lan}")
                    dong = do_mot_lan(p, lan, tt, nc)
                    tep.write(json.dumps(_sach(dong), ensure_ascii=False) + "\n")
                    tep.flush()
                    so_dong += 1
                    in_ra(dong_console(dong))
                if che is not None and gui is not None:
                    che.an()
                p.dong()
    except _DungDo as exc:
        ma, ly_do_dung = 1, str(exc)
        in_ra(f"{_bay_gio()} DỪNG: {exc}")
    except KeyboardInterrupt:
        ma, ly_do_dung = 1, "Ctrl+C"
        in_ra(f"{_bay_gio()} DỪNG: Ctrl+C")
    finally:
        for p in tien_trinh:                               # dong() gọi lại với tiến trình đã đóng thì không làm gì
            p.dong()
        may.update(ket_thuc=_bay_gio(), trang_thai_may_cuoi=doc_trang_thai_may().to_dict(), so_dong=so_dong,
                   dung_giua_chung=ly_do_dung)
        _ghi_json(ra / "may.json", may)
        van_ban = tom_tat(_doc_jsonl(ra / "ket_qua.jsonl"), may)
        (ra / "tom_tat.txt").write_text(van_ban, encoding="utf-8")
        in_ra(f"{_bay_gio()} Xong: {so_dong}/{so_lan} lần đo; tóm tắt: {ra / 'tom_tat.txt'}")
        nhat_ky.close()
    return ma


def _phien_ban(goi: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(goi)
    except PackageNotFoundError:
        return None


# --------------------------------------------------------------------------------------------------------- tóm tắt

def _so(x: float | None, n: int = 2) -> str:
    """Số thập phân dấu phẩy (tài liệu tiếng Việt); "–" khi không có."""
    return "–" if x is None else f"{x:.{n}f}".replace(".", ",")


def _sai_trang_thai(dong: dict) -> bool:
    tt = dong.get("trang_thai")
    if tt == "thuong":
        lo_ra = dong.get("gui_lo_ra")
        return (dong.get("gui_thu_nho") is True or dong.get("gui_hien") is False
                or (lo_ra is not None and lo_ra < LO_RA_TOI_THIEU))
    if tt == "thu_nho":
        return dong.get("gui_thu_nho") is not True
    if tt == "bi_che":
        return dong.get("che_kin") is not True
    return False


def ly_do_loai(dong: dict) -> str | None:
    """Lý do loại một dòng khỏi phép so sánh; None = dòng hợp lệ. Mỗi dòng mang một lý do, theo thứ tự `LY_DO`."""
    ghi_chu = str(dong.get("ghi_chu") or "")
    if dong.get("khoi_dong"):
        return "khoi_dong"
    if dong.get("ket_qua") == "KHONG_TRA_LOI":
        return "khong_tra_loi"
    if dong.get("ket_qua") == "BO_QUA":
        return "bo_qua"
    phien = (dong.get("phien"), dong.get("phien_sau"))
    if "khoa" in phien:
        return "phien_khoa"
    if any(p != "mo" for p in phien) or dong.get("ket_noi") in (None, "khong_ro"):
        return "phien_khong_ro"
    if dong.get("ket_noi") != "active":
        return "ngat_ket_noi"
    if dong.get("ban_lam_viec") != "Default":
        return "ban_lam_viec_khac"
    if dong.get("man_hinh") in ("tat", "mo_toi") or dong.get("man_hinh_sau") in ("tat", "mo_toi"):
        return "man_hinh_tat"
    vang, vang_sau = dong.get("vang_s"), dong.get("vang_s_sau")
    if "nguoi_dung_thao_tac" in ghi_chu or (vang is not None and vang_sau is not None and vang_sau < vang):
        return "nguoi_dung_thao_tac"
    if (dong.get("tai_nen_pct") or 0.0) > TAI_NEN_CAO:
        return "tai_nen_cao"
    if _sai_trang_thai(dong):
        return "sai_trang_thai"
    if dong.get("trang_thai") in ("thu_nho", "bi_che") and dong.get("cua_so_truoc") == "giao_dien":
        return "gui_van_o_truoc"
    if dong.get("trang_thai") == "thuong" and dong.get("cua_so_truoc") != "giao_dien":
        return "gui_khong_o_truoc"
    if (dong.get("mau_sai") or 0) > 0:                     # chế độ chạy; dòng lập đường không có khóa này
        return "doi_trang_thai_trong_chay"
    if "khong_tat_duoc_ecoqos" in ghi_chu:
        return "khong_tat_duoc_ecoqos"
    if "khong_giu_duoc_ecoqos" in ghi_chu:
        return "khong_giu_duoc_ecoqos"
    return None


def _nhom(ds: list[dict], bien_the: str, trang_thai: str) -> list[dict]:
    return [d for d in ds if d.get("bien_the") == bien_the and d.get("trang_thai") == trang_thai]


def _tg(ds: list[dict]) -> list[float]:
    return [d["tg_tinh_s"] for d in ds if d.get("tg_tinh_s") is not None]


def _trung_vi(xs: Iterable[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _du_luot(ds: list[dict]) -> bool:
    """Nhóm có đủ TOI_THIEU_LUOT lượt (có thời gian) để làm một bên của phép so."""
    return len(_tg(ds)) >= TOI_THIEU_LUOT


def _he_so(xet: list[dict], moc: list[dict]) -> float | None:
    """Hệ số trung vị tg_tinh_s xet / moc; None khi một bên có ít hơn TOI_THIEU_LUOT lượt."""
    if not (_du_luot(xet) and _du_luot(moc)):
        return None
    b = _trung_vi(_tg(moc))
    return _trung_vi(_tg(xet)) / b if b and b > 0 else None


def _muc_he_so(he_so: float | None) -> str:
    """Mức chậm CHỈ theo hệ số trung vị (lượt không OK không đổi mức): dòng bối cảnh dùng mức này."""
    if he_so is None:
        return "khong_du"
    return "cham_ro" if he_so >= NGUONG_CHAM else ("cham_nhe" if he_so >= NGUONG_NHIEU else "khong_cham")


def _co_hong(ds: list[dict]) -> bool:
    return any(d.get("ket_qua") != "OK" for d in ds)


def _so_sanh(xet: list[dict], moc: list[dict]) -> tuple[str, float | None]:
    """Kết luận (b) cho một trạng thái: ("cham_ro" | "cham_nhe" | "khong_cham" | "khong_du", hệ số trung vị tg_tinh_s
    xet / moc). Chậm rõ: hệ số ≥ NGUONG_CHAM, hoặc có lượt không OK trong khi mọi lượt mốc đều OK; chậm nhẹ: hệ số ≥
    NGUONG_NHIEU; không đủ: một bên có ít hơn TOI_THIEU_LUOT lượt. Quy tắc "có lượt không OK" chỉ dùng ở đây: dòng
    nguyên nhân và bối cảnh không dùng (một lượt hỏng nhanh không phải "vẫn chậm" hay "Windows có hạ tốc")."""
    he_so = _he_so(xet, moc)
    if he_so is None:
        return "khong_du", None
    if he_so < NGUONG_CHAM and _co_hong(xet) and not _co_hong(moc):
        return "cham_ro", he_so
    return _muc_he_so(he_so), he_so


def _dem_ok(ds: list[dict]) -> str:
    """"OK 3/4": số lượt OK trên số lượt hợp lệ của nhóm; "0" khi nhóm rỗng."""
    return f"OK {sum(d.get('ket_qua') == 'OK' for d in ds)}/{len(ds)}" if ds else "0"


def _nguyen_nhan(he_so: float, off: list[dict], moc_off: list[dict]) -> str:
    """Kết luận (c): vì sao gui_system chậm (hệ số `he_so`) ở một trạng thái, từ gui_off cùng trạng thái so với mốc
    `moc_off`. EcoQoS chỉ được kể là nguyên nhân khi tắt nó làm nhanh hơn rõ (hệ số gui_system ≥ NGUONG_NHIEU × hệ số
    gui_off). Khi gui_system bị coi là chậm CHỈ vì có lượt không OK (hệ số < NGUONG_NHIEU) thì so lượt không OK."""
    he_so_off = _he_so(off, moc_off)
    if he_so_off is None:
        return (f"chưa đủ lượt gui_off hợp lệ để tách (gui_off {_dem_ok(off)} lượt hợp lệ, mốc {_dem_ok(moc_off)}; "
                f"cần ≥ {TOI_THIEU_LUOT} lượt mỗi bên)")
    so_lieu = f"gui_off hệ số {_so(he_so_off)}, {_dem_ok(off)} lượt hợp lệ"
    if he_so < NGUONG_NHIEU:
        if he_so_off < NGUONG_NHIEU and not _co_hong(off):
            return f"có thể do EcoQoS (tắt EcoQoS thì không còn lượt không OK: {so_lieu})"
        return f"không tách được (tắt EcoQoS vẫn có lượt không OK hoặc vẫn chậm: {so_lieu})"
    if he_so >= NGUONG_NHIEU * he_so_off:
        if he_so_off < NGUONG_NHIEU:
            return f"Windows hạ tốc tiến trình (tắt EcoQoS cho tiến trình thì hết: {so_lieu})"
        return f"một phần do EcoQoS (tắt EcoQoS thì nhanh hơn nhưng vẫn chậm: {so_lieu})"
    if he_so_off >= NGUONG_CHAM:
        return f"không phải do EcoQoS (tắt EcoQoS vẫn chậm như vậy: {so_lieu})"
    return f"không tách được (tắt EcoQoS không nhanh hơn rõ: {so_lieu})"


_NHAN_MUC = {"cham_ro": "chậm rõ", "cham_nhe": "có thể chậm nhẹ", "khong_cham": "không thấy chậm",
             "khong_du": "không đủ lượt hợp lệ để so"}


def _khoang(ds: list[int]) -> str:
    """[0, 1, 2, 5] → "0–2, 5"."""
    ra, i = [], 0
    while i < len(ds):
        j = i
        while j + 1 < len(ds) and ds[j + 1] == ds[j] + 1:
            j += 1
        ra.append(f"{ds[i]}–{ds[j]}" if j > i else f"{ds[i]}")
        i = j + 1
    return ", ".join(ra)


def _co_khong(x) -> str:
    return "?" if x is None else ("có" if x else "không")


def _lech_chu(x) -> str:
    """Độ lệch kịch bản (m hoặc rad) để in: số thì dạng 3 chữ số có nghĩa, dấu phẩy; chữ ("khac_cau_truc") giữ nguyên."""
    if isinstance(x, (int, float)):
        return "0" if x == 0 else f"{x:.3g}".replace(".", ",")
    return "?" if x is None else str(x)


def _giay_man_hinh(s) -> str:
    return "?" if s is None else ("không bao giờ" if s == 0 else f"{s} s")


def _dem(ds: list[dict], khoa: str) -> str:
    dem = Counter(str(d[khoa]) for d in ds if d.get(khoa) is not None)
    return ", ".join(f"{k} {v}" for k, v in dem.most_common()) or "–"


def _phan_dau(dong: list[dict], may: dict) -> list[str]:
    ra = [
        f"Đo EcoQoS của ứng dụng giao diện (python -m {MODULE})",
        f"Ca: {may.get('ca', '?')}; hạn lập đường {_so(may.get('han_lap_duong_s'), 1)} s; kịch bản "
        f"{may.get('kich_ban', '?')} (lệch sau khi lưu và nạp lại: {_lech_chu(may.get('kich_ban_lech'))})",
        f"Thời gian: {may.get('bat_dau', '?')} → {may.get('ket_thuc', '?')}"
        + (f"; DỪNG GIỮA CHỪNG: {may['dung_giua_chung']}" if may.get("dung_giua_chung") else ""),
    ] + _dong_may_chung(dong, may)
    if may.get("kich_ban_lech"):
        ra.append(f"CẢNH BÁO: kịch bản lệch {_lech_chu(may['kich_ban_lech'])} sau khi lưu và nạp lại.")
    dau = may.get("trang_thai_may_dau") or {}
    if dau and not dau.get("nhin_thay_duoc", True):
        ra.append(f"CẢNH BÁO: lúc bắt đầu phiên={dau.get('phien')}, kết nối={dau.get('ket_noi')}, màn hình="
                  f"{dau.get('man_hinh')}.")
    return ra


def _dong_may_chung(dong: list[dict], may: dict) -> list[str]:
    """Các dòng điều kiện máy của phần đầu tóm tắt, chung cho chế độ lập đường và chế độ chạy (tách 02/10/2026): mã,
    CPU, nguồn, Windows, số lượt theo phiên / màn hình lúc bấm và tải nền, lệnh."""
    git, nguon, win, cpu = (may.get(k) or {} for k in ("git", "nguon", "windows", "cpu"))
    ke_hoach, lop_phu = nguon.get("ke_hoach") or {}, nguon.get("lop_phu") or {}
    lop = cpu.get("lop") or {}
    lop_chu = "; ".join(f"lớp {k}: LP {_khoang(v)}" for k, v in sorted(lop.items(), key=lambda kv: -int(kv[0])))
    tai = [d["tai_nen_pct"] for d in dong if d.get("tai_nen_pct") is not None]
    return [
        f"Mã: commit {git.get('commit', '?')} (+ {git.get('so_tep_chua_commit', '?')} tệp chưa commit)",
        f"CPU: {cpu.get('logic', '?')} bộ xử lý logic; {lop_chu or 'không đọc được lớp lõi'} "
        f"(lớp thấp nhất là lõi E)",
        f"Nguồn: kế hoạch {ke_hoach.get('ten') or '?'} ({ke_hoach.get('guid') or '?'}); lớp phủ "
        f"{lop_phu.get('ten') or '?'}; điện lưới {_co_khong(nguon.get('dien_luoi'))}; tiết kiệm pin "
        f"{_co_khong(nguon.get('tiet_kiem_pin'))}; tắt màn hình sau: "
        f"AC {_giay_man_hinh(nguon.get('tat_man_hinh_ac_s'))}, DC {_giay_man_hinh(nguon.get('tat_man_hinh_dc_s'))}",
        f"Windows: {win.get('ban', '?')} (UBR {win.get('ubr', '?')}); phiên {win.get('phien_id', '?')}, phiên console "
        f"{win.get('phien_console', '?')}; nâng quyền {_co_khong(win.get('nang_quyen'))}; tiến trình cha: "
        f"{' ← '.join(win.get('to_tien') or []) or '?'}"
        + (f"; khóa cửa sổ ở trước (ForegroundLockTimeout) {win['khoa_truoc_ms']} ms"
           if win.get("khoa_truoc_ms") is not None else ""),
        f"Số lượt theo phiên lúc bấm: {_dem(dong, 'phien')} (sau: {_dem(dong, 'phien_sau')}); theo màn hình lúc "
        f"bấm: {_dem(dong, 'man_hinh')} (sau: {_dem(dong, 'man_hinh_sau')}); tải nền "
        f"{_so(min(tai), 1) if tai else '–'}–{_so(max(tai), 1) if tai else '–'} %",
        f"Lệnh: {may.get('lenh', '?')}",
    ]


def _bang(dong: list[dict], hop_le: list[dict]) -> list[str]:
    ra = ["Bảng (chỉ lượt hợp lệ; tg tính = từ lúc bấm tới khi bộ lập kế hoạch trả về, giây; lõi E là chỉ báo):",
          f"{'biến thể':<13}{'trạng thái':<14}{'hợp lệ':>8}{'OK':>8}  {'tg tính: trung vị (min–max)':<30}"
          f"{'trễ poll':>9}{'lõi E':>8}{'CPU/tg':>8}  focus"]
    cap = [(bt, tt) for bt in BIEN_THE for tt in (("khong_cua_so",) if bt == "khong_cua_so" else TRANG_THAI)]
    for bt, tt in cap:
        tat_ca, hl = _nhom(dong, bt, tt), _nhom(hop_le, bt, tt)
        if not tat_ca:
            continue
        tg = _tg(hl)
        tg_chu = f"{_so(_trung_vi(tg))} ({_so(min(tg))}–{_so(max(tg))})" if tg else "–"
        e = _trung_vi(d.get("ty_le_e") for d in hl)
        cpu = _trung_vi(d["cpu_tien_trinh_s"] / d["tg_tinh_s"] for d in hl
                        if d.get("cpu_tien_trinh_s") is not None and d.get("tg_tinh_s"))
        # mọi trạng thái có cửa sổ: lượt "thu nhỏ" / "bị che" mà giao diện vẫn ở trước đã bị loại (gui_van_o_truoc)
        focus = (f"{sum(d.get('cua_so_truoc') == 'giao_dien' for d in hl)}/{len(hl)}" if bt != "khong_cua_so" else "")
        ok = sum(d.get("ket_qua") == "OK" for d in hl)
        ra.append(f"{bt:<13}{tt:<14}{f'{len(hl)}/{len(tat_ca)}':>8}{f'{ok}/{len(hl)}':>8}  {tg_chu:<30}"
                  f"{_so(_trung_vi(d.get('tre_poll_s') for d in hl), 3):>9}"
                  f"{(_so(100 * e, 0) + ' %') if e is not None else '–':>8}{_so(cpu):>8}  {focus}")
    return ra


def _co_khoa(dong: list[dict]) -> bool:
    """Có lượt nào phiên khóa, ngắt kết nối hay màn hình tắt / mờ."""
    return any("khoa" in (d.get("phien"), d.get("phien_sau"))
               or d.get("ket_noi") not in (None, "active", "khong_ro")
               or d.get("man_hinh") in ("tat", "mo_toi") or d.get("man_hinh_sau") in ("tat", "mo_toi")
               for d in dong)


def _ket_luan(dong: list[dict], hop_le: list[dict], may: dict, dem_loai: Counter) -> list[str]:
    moc = _nhom(hop_le, "gui_system", "thuong")
    loai_chu = ", ".join(f"{k} {dem_loai[k]}" for k in LY_DO if dem_loai.get(k)) or "không có"
    if not moc:
        ra = [f"KẾT LUẬN: KHÔNG KẾT LUẬN về thu nhỏ/bị che: không có lượt gui_system/thuong hợp lệ làm mốc "
              f"'cửa sổ đang hiện' (lượt bị loại: {loai_chu})."]
        if _co_khoa(dong):
            ra.append(GIAI_THICH_KHOA)
        return ra
    ra = [f"Kết luận (chỉ lượt hợp lệ; ngưỡng mô tả, không phải ngưỡng nghiệm thu: hệ số = trung vị tg tính / trung vị "
          f"của gui_system/thuong; ≥ {_so(NGUONG_CHAM)} hoặc có lượt không OK trong khi mọi lượt 'thường' đều OK là "
          f"chậm rõ; ≥ {_so(NGUONG_NHIEU)} là có thể chậm nhẹ; mỗi phép so cần ≥ {TOI_THIEU_LUOT} lượt hợp lệ mỗi bên; "
          f"dòng bối cảnh chỉ xét hệ số):"]
    ke_hoach = ((may.get("nguon") or {}).get("ke_hoach") or {}).get("ten") or "?"
    off_moc = _nhom(hop_le, "gui_off", "thuong")
    moc_off = off_moc if _du_luot(off_moc) else moc       # gui_off/thuong ít quá thì so với gui_system/thuong
    for tt in ("thu_nho", "bi_che"):
        xet = _nhom(hop_le, "gui_system", tt)
        muc, he_so = _so_sanh(xet, moc)
        dong_tt = (f"- {tt}: {_NHAN_MUC[muc]} (" + (f"hệ số {_so(he_so)}; " if he_so is not None else "")
                   + f"{_dem_ok(xet)} lượt hợp lệ; mốc {_dem_ok(moc)}"
                   + (f"; cần ≥ {TOI_THIEU_LUOT} lượt mỗi bên)" if muc == "khong_du" else ")"))
        if muc in ("cham_ro", "cham_nhe"):
            dong_tt += ". Nguyên nhân: " + _nguyen_nhan(he_so, _nhom(hop_le, "gui_off", tt), moc_off)
        ra.append(dong_tt)
    nen = _nhom(hop_le, "khong_cua_so", "khong_cua_so")
    moc_nen, ten_moc = (off_moc, "gui_off/thuong") if _du_luot(off_moc) else (moc, "gui_system/thuong")
    he_so_nen = _he_so(nen, moc_nen)
    muc_nen = _muc_he_so(he_so_nen)          # (d) chỉ theo hệ số: một lượt hỏng không thành "Windows CÓ hạ tốc"
    so_lieu = f"khong_cua_so / {ten_moc} = {_so(he_so_nen)}; khong_cua_so {_dem_ok(nen)} lượt hợp lệ"
    if muc_nen == "khong_du":
        ra.append(f"- Bối cảnh: không đủ lượt khong_cua_so hợp lệ (khong_cua_so {_dem_ok(nen)} lượt hợp lệ, mốc "
                  f"{ten_moc} {_dem_ok(moc_nen)}; cần ≥ {TOI_THIEU_LUOT} lượt mỗi bên): không biết lúc đo Windows "
                  f"có hạ tốc tiến trình không cửa sổ hay không.")
    elif muc_nen == "cham_ro":
        ra.append(f"- Bối cảnh: lúc đo Windows CÓ hạ tốc tiến trình không cửa sổ (như 30/09/2026): {so_lieu}.")
    elif muc_nen == "khong_cham":
        ra.append(f"- Bối cảnh: lúc đo Windows KHÔNG hạ tốc cả tiến trình không cửa sổ (khác 30/09/2026; {so_lieu}); "
                  f"'không thấy chậm' chỉ đúng với điều kiện lúc đo (kế hoạch nguồn {ke_hoach}), không chứng minh giao "
                  f"diện an toàn khi Windows có hạ tốc.")
    else:
        ra.append(f"- Bối cảnh: tiến trình không cửa sổ chậm nhẹ ({so_lieu}): không rõ lúc đo Windows có hạ tốc tiến "
                  f"trình không cửa sổ hay không.")
    chi_bao = []
    for tt in TRANG_THAI:
        e = _trung_vi(d.get("ty_le_e") for d in _nhom(hop_le, "gui_system", tt))
        chi_bao.append(f"{tt} {_so(100 * e, 0) + ' %' if e is not None else '–'}")
    ra.append("- Chỉ báo (không phải phép đo trực tiếp; bộ đếm toàn máy): phần CPU bận thêm rơi vào lõi E, gui_system: "
              + ", ".join(chi_bao) + ".")
    thuong = moc
    ra.append(f"- Cửa sổ ở trước (focus) lúc bấm, lượt gui_system/thuong hợp lệ: "
              f"{sum(d.get('cua_so_truoc') == 'giao_dien' for d in thuong)}/{len(thuong)}.")
    if _co_khoa(dong):
        ra.append(f"- Có lượt bị loại vì phiên khóa / ngắt kết nối / màn hình tắt. {GIAI_THICH_KHOA}")
    return ra


def _chuyen_cua_so(dong: list[dict]) -> list[str]:
    """Dòng "Đưa cửa sổ ra trước" của tóm tắt (thêm 02/10/2026): với mỗi cửa sổ đích, số lần nó ở trước ngay sau khi đổi
    trạng thái và các kết quả khác; kết quả các bước cấp quyền. Dòng cũ không có hai khóa đó: không in gì."""
    co = [d for d in dong if d.get("ket_qua_dua_ra_truoc")]
    if not co:
        return []
    phan = []
    for dich in ("giao_dien", "trung_tinh", "man_che"):
        ds = [str(d["ket_qua_dua_ra_truoc"]) for d in co if str(d["ket_qua_dua_ra_truoc"]).startswith(f"{dich}:")]
        if ds:
            khac = Counter(x for x in ds if x != f"{dich}:ok")
            phan.append(f"{dich} {len(ds) - sum(khac.values())}/{len(ds)}"
                        + (" (" + ", ".join(f"{k} {v}" for k, v in sorted(khac.items())) + ")" if khac else ""))
    cap = Counter(str(d["cap_quyen_truoc"]) for d in co if d.get("cap_quyen_truoc"))
    return [f"Đưa cửa sổ ra trước lúc đổi trạng thái (mọi lượt có cửa sổ, kể cả lượt bị loại; đọc lại cửa sổ ở trước "
            f"ngay sau): {'; '.join(phan)}. Cấp quyền trước đó (AllowSetForegroundWindow): "
            + (", ".join(f"{k} {v}" for k, v in sorted(cap.items())) or "không lượt nào cần") + "."]


def tom_tat(dong: list[dict], may: dict) -> str:
    """Nội dung tom_tat.txt từ các dòng ket_qua.jsonl và may.json. Hàm thuần: không đọc máy, không đọc tệp."""
    hop_le = [d for d in dong if ly_do_loai(d) is None]
    dem_loai = Counter(ly for ly in map(ly_do_loai, dong) if ly)
    ra = _phan_dau(dong, may) + [""]
    if not dong:
        return "\n".join(ra + ["Chưa có lần đo nào."]) + "\n"
    ra += _bang(dong, hop_le) + [""]
    ra.append("Lượt bị loại khỏi phép so sánh: "
              + (", ".join(f"{k} {dem_loai[k]}" for k in LY_DO if dem_loai.get(k)) or "không có"))
    ra += _chuyen_cua_so(dong)
    ra.append("")
    ra += _ket_luan(dong, hop_le, may, dem_loai)
    return "\n".join(ra) + "\n"


def chay_tom_tat(args) -> int:
    ra = Path(args.ra)
    if not (ra / "ket_qua.jsonl").exists():
        print(f"Lỗi: không có {ra / 'ket_qua.jsonl'}", file=sys.stderr)
        return 2
    tep_may = ra / "may.json"
    may = json.loads(tep_may.read_text(encoding="utf-8")) if tep_may.exists() else {}
    dong = _doc_jsonl(ra / "ket_qua.jsonl")
    if may.get("che_do") == "chay" or (not may and dong and "nhanh" in dong[0]):     # chế độ chạy (02/10/2026)
        from autopark.evaluation.ecoqos_chay import tom_tat_chay

        van_ban = tom_tat_chay(dong, may)
    else:
        van_ban = tom_tat(dong, may)
    (ra / "tom_tat.txt").write_text(van_ban, encoding="utf-8")
    print(van_ban, end="")
    return 0


# ------------------------------------------------------------------------------------------------------- dòng lệnh

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog=f"python -X utf8 -m {MODULE}", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="lenh", required=True)
    do = sub.add_parser("do", help="đo: mở giao diện thật, đổi trạng thái cửa sổ, lập đường, ghi kết quả")
    do.add_argument("--ra", required=True, help="thư mục kết quả MỚI (ví dụ docs\\evidence\\ecoqos_giao_dien_<ngày> "
                                                "hoặc runs\\thu_ecoqos)")
    do.add_argument("--ca", default="uturn_w46", help="ca trong evaluation/hard_cases.py (mặc định uturn_w46, ≈ 3,6 s)")
    do.add_argument("--khoi", type=int, default=2, help="số khối; mỗi khối chạy mọi biến thể, thứ tự xoay vòng")
    do.add_argument("--lap", type=int, default=2, help="số vòng các trạng thái trong một khối (sau lượt khởi động)")
    do.add_argument("--cho", type=float, default=5.0, help="giây chờ ổn định sau khi đổi trạng thái (≥ 2)")
    do.add_argument("--trang-thai", default=",".join(TRANG_THAI), help="danh sách, cách nhau bằng dấu phẩy")
    do.add_argument("--bien-the", default=",".join(BIEN_THE), help="danh sách, cách nhau bằng dấu phẩy")
    dc = sub.add_parser("do-chay", help="đo vòng điều khiển 50 Hz của lần chạy (SIM, bo mô phỏng) khi cửa sổ thường / "
                                        "thu nhỏ / bị che (thêm 02/10/2026)")
    dc.add_argument("--ra", required=True, help="thư mục kết quả MỚI (ví dụ docs\\evidence\\ecoqos_chay_<ngày> hoặc "
                                                "runs\\thu_ecoqos_chay)")
    dc.add_argument("--kich-ban", default=None, help="tệp kịch bản (mặc định scenarios/bai_do_xe.json, ≈ 21 s mô phỏng)")
    dc.add_argument("--ca", default=None, help="ca trong evaluation/hard_cases.py thay cho --kich-ban")
    dc.add_argument("--nhanh", default="SIM,VEHICLE_IO", help="nhánh chạy, cách nhau bằng dấu phẩy: SIM, VEHICLE_IO "
                                                            "(chỉ bo mô phỏng)")
    dc.add_argument("--bien-the", default="gui_system,gui_off", help="gui_system, gui_off, gui_off_dh")
    dc.add_argument("--trang-thai", default=",".join(TRANG_THAI), help="danh sách, cách nhau bằng dấu phẩy")
    dc.add_argument("--khoi", type=int, default=2, help="số khối; mỗi khối chạy mọi (biến thể, nhánh), xoay vòng")
    dc.add_argument("--lap", type=int, default=1, help="số vòng các trạng thái trong một khối (sau lượt khởi động)")
    dc.add_argument("--cho", type=float, default=5.0, help="giây chờ ổn định sau khi đổi trạng thái (≥ 2)")
    dc.add_argument("--toi-da-chay", type=float, default=300.0,
                    help="giây thật tối đa một lần chạy (≥ 30); quá thì công cụ bấm Dừng (lượt KHONG_XONG)")
    dc.add_argument("--khong-giu-chuoi", action="store_true", help="không ghi chuỗi nhịp thô nhip/*.json.gz")
    tt = sub.add_parser("tom-tat", help="viết lại tom_tat.txt từ ket_qua.jsonl và may.json")
    tt.add_argument("--ra", required=True)
    con = sub.add_parser("con", help="(nội bộ, lệnh `do` mở) giao diện thật cộng đầu dò")
    con.add_argument("--kich-ban", required=True)
    con.add_argument("--cho-phep-offscreen", action="store_true", help="chỉ cho test: chấp nhận Qt offscreen")
    con.add_argument("--chay", action="store_true",
                     help="(lệnh `do-chay`) đầu dò vòng điều khiển: chuan_bi | chay | dung")
    con.add_argument("--nhanh", choices=("SIM", "VEHICLE_IO"), default="SIM",
                     help="nhánh chạy với --chay (VEHICLE_IO: chỉ bo mô phỏng)")
    nen = sub.add_parser("nen", help="(nội bộ, lệnh `do` mở) đối chứng không cửa sổ")
    nen.add_argument("--kich-ban", required=True)
    che = sub.add_parser("che", help="(nội bộ, lệnh `do` mở) màn che")
    che.add_argument("--toi-da", type=float, default=900.0, help="giây tối đa trước khi màn che tự đóng")
    che.add_argument("--cho-phep-offscreen", action="store_true", help="chỉ cho test: chấp nhận Qt offscreen")
    args = parser.parse_args(argv)
    if args.lenh == "do":
        return chay_do(args, argv)
    if args.lenh == "do-chay":
        from autopark.evaluation.ecoqos_chay import chay_do_chay

        return chay_do_chay(args, argv)
    if args.lenh == "tom-tat":
        return chay_tom_tat(args)
    if args.lenh == "con":
        return chay_con(Path(args.kich_ban), args.cho_phep_offscreen, chay=args.chay, nhanh=args.nhanh)
    if args.lenh == "nen":
        return chay_nen(Path(args.kich_ban))
    return chay_che(args.toi_da, args.cho_phep_offscreen)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")           # console không UTF-8 vẫn in được chữ Việt
    sys.exit(main())
