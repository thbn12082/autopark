"""Đo vòng điều khiển 50 Hz của ứng dụng giao diện khi cửa sổ thường / thu nhỏ / bị che (thêm 02/10/2026, `do-chay`).

Công cụ đo, không sửa ứng dụng. Vì sao: docs/CHUYEN_MAY_BAN.md mục 10 còn dòng "Vòng điều khiển 50 Hz của lần chạy khi
cửa sổ bị thu nhỏ: CHƯA ĐO". Vòng điều khiển chạy trong luồng giao diện: QTimer 16 ms gọi `MainWindow._on_tick`, nó
gọi `advance_by(real_dt)` với real_dt = thời gian thật từ nhịp trước (QElapsedTimer, ms nguyên, chặn 0,1 s);
`Session.advance` chạy các bước 5 ms, cứ 4 bước một nhịp điều khiển (50 Hz). Nhánh SIM và bo mô phỏng chạy theo thời
gian phiên: nhịp giao diện thưa chỉ làm phiên chậm hơn đồng hồ thật. Với bo theo đồng hồ tường (bo thật, bo ảo QEMU)
khoảng giữa hai nhịp điều khiển dài hơn hạn lệnh 0,15 s là lệnh hết hạn: SUY RA, CHƯA ĐO với bo theo đồng hồ tường.

Cách đo. Lệnh `python -X utf8 -m autopark.evaluation.ecoqos_gui do-chay` (điểm vào duy nhất vẫn là `ecoqos_gui`;
mô-đun này không có `main`) dùng lại toàn bộ máy móc đã kiểm của chế độ lập đường: tiến trình con `con` (giao diện
thật, ở đây với `--chay --nhanh SIM|VEHICLE_IO`), tiến trình `che` (màn che, cửa sổ trung tính), `chuyen_trang_thai`
(đưa cửa sổ ra trước), đọc trạng thái phiên, CPU, EcoQoS. Mỗi lượt (`do_mot_lan_chay`): phiên chưa có đường thì lập
đường ở trạng thái thường; đặt cửa sổ vào trạng thái cần đo; chờ ổn định; bấm "Bắt đầu đỗ" (`MainWindow.run()`, hàm nút
gọi); lấy mẫu trạng thái cửa sổ mỗi giây tới khi xe dừng (lượt có mẫu sai bị loại). Đầu dò `DauDoChay` trong tiến
trình giao diện ghi từng nhịp giao diện (lúc gọi, real_dt, số bước, số nhịp điều khiển, thời gian xử lý, thời gian
tính) và từng nhịp điều khiển (lúc chạy, số bước), gửi về MỘT dòng JSON sau khi xe dừng; thống kê ở `thong_ke_nhip`,
tóm tắt ở `tom_tat_chay`. Lượt 0 của mỗi khối (thường) là lượt khởi động: bị loại khi so, làm mốc kiểm tính xác định
(SIM và bo mô phỏng chạy bước cố định nên các lần chạy phải ra cùng kết quả) và ước lượng thời gian một lần chạy.

Biến thể: gui_system (AUTOPARK_KEEP_ECOQOS=1, EcoQoS do Windows tự quyết, đọc lại phải là "system"; không đọc được thì
giữ dòng và cảnh báo, sửa 02/10/2026), gui_off (không
có biến đó; tắt EcoQoS theo pid, cùng lời gọi SetProcessInformation mà ứng dụng dùng khi tự tắt EcoQoS; tiến trình đã
"off" lúc sẵn sàng thì ghi cách tắt "ung_dung"), gui_off_dh (tắt EcoQoS VÀ luôn tôn trọng độ phân giải đồng hồ,
`dat_ton_trong_dong_ho`; chỉ chạy khi gui_off vẫn thưa nhịp lúc thu nhỏ). Mặc định (người dùng giao quyết định 02/10/2026, "làm hết"): kịch bản scenarios/bai_do_xe.json,
nhánh SIM và VEHICLE_IO (bo mô phỏng), biến thể gui_system và gui_off, 2 khối × (1 + 3) lượt, giữ chuỗi nhịp thô.

Trong `--ra`: ket_qua.jsonl (một dòng mỗi lượt, khóa theo `COT_CHAY`), may.json (`che_do` = "chay"; `khoi_bo_do`: khối
bị bỏ dở vì một lần chạy không dừng được, thêm 02/10/2026), tom_tat.txt,
kich_ban_<tên>.json hoặc ca_<ca>.json, nhip/<lượt>.json.gz (chuỗi thô, trừ khi --khong-giu-chuoi),
powercfg_bo_xu_ly.txt, nhat_ky.txt. Không ghi CSV.

An toàn: như chế độ lập đường (không giả lập phím/chuột, không chụp màn hình, không đổi kế hoạch nguồn / màn hình / khóa
máy). VehicleIO chỉ với bo MÔ PHỎNG: tiến trình con thoát mã 2 nếu thẻ "Bo điều khiển" chọn một cổng; không gọi
`_refresh_ports`, `_probe_board`, `_clear_board_fault`; không cổng COM, camera hay LiDAR. Cờ điều tiết chỉ đặt cho tiến
trình con của công cụ và mất theo tiến trình. Hằng số `HAN_LENH_S` (N-T10, ĐỀ XUẤT), `WATCHDOG_LIEN_LAC_S`,
`HE_SO_NHIP_*`, `MAT_DANG_KE_S` chỉ để mô tả, không phải ngưỡng nghiệm thu.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import functools
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Callable, Iterable, Sequence

from autopark.evaluation import ecoqos_gui as eg
from autopark.evaluation.ecoqos_gui import (CHO_KET_QUA_S, CHO_MAN_CHE_S, CHO_SAN_SANG_S, DICH_TRUOC, GIAI_THICH_KHOA,
                                            LY_DO, MODULE, NGUONG_CHAM, NGUONG_NHIEU, PROJECT_ROOT, TOI_THIEU_LUOT,
                                            TRANG_THAI, NguCanhDo, _sach, _so, _tach_lenh, _tron, _trung_vi)

NHANH_CHAY = ("SIM", "VEHICLE_IO")
"""Nhánh chạy đo được: SIM (mô phỏng giai đoạn 0) và VEHICLE_IO với bo MÔ PHỎNG (SimVehicleIO + FirmwareModel)."""
BIEN_THE_CHAY = ("gui_system", "gui_off", "gui_off_dh")
KICH_BAN_MAC_DINH = PROJECT_ROOT / "scenarios" / "bai_do_xe.json"

CHAN_REAL_DT_S = 0.1           # `MainWindow._on_tick`: real_dt = min(..., 0.1); test giữ hằng số này khớp hành vi
HAN_LENH_S = 0.15              # thời hạn mặc định của một COMMAND (VehicleIO default_validity_s; N-T10, ĐỀ XUẤT)
WATCHDOG_LIEN_LAC_S = 0.5      # FirmwareConfig.link_timeout_ms: không nhận gì 0,5 s thì bo về DISARMED
HE_SO_NHIP_CHAM = 1.5          # nhịp giao diện p95 / mốc từ đây: "chậm rõ" (mô tả)
HE_SO_NHIP_NHE = 1.2           # từ đây: "có thể chậm nhẹ"
MAT_DANG_KE_S = 0.05           # giây phiên mất do chặn real_dt từ đây là đáng kể
CHO_BAT_DAU_S = 15.0           # chờ trả lời lệnh `chay`
CHO_DUNG_S = 60.0              # sau khi công cụ bấm Dừng, chờ thêm ngần này
T_UOC_CHAY_S = 40.0            # ước lượng một lần chạy trước lượt khởi động (bai_do_xe ≈ 21 s mô phỏng)
TOI_THIEU_TOI_DA_CHAY_S = 30.0

COT_CHAY = (
    "thoi_diem", "khoi", "bien_the", "nhanh", "pid", "lan", "khoi_dong", "trang_thai",
    "ecoqos", "dong_ho", "uu_tien", "phan_giai_ms",
    "phien", "ket_noi", "ban_lam_viec", "man_hinh", "vang_s", "phien_sau", "man_hinh_sau", "vang_s_sau",
    "cua_so_truoc", "gui_thu_nho", "gui_hien", "gui_lo_ra", "che_kin", "cap_quyen_truoc", "ket_qua_dua_ra_truoc",
    "mau_n", "mau_sai", "mau_sai_dau",
    "lap_lai_duong", "van_tay_duong",
    "ket_qua", "ly_do_dung", "ma_su_kien", "dung_boi_cong_cu",
    "rt", "tg_tuong_s", "tg_phien_s", "ty_le_phien", "mat_chan_s", "troi_lam_tron_pct", "tre_nhip_dau_ms",
    "so_nhip_gd", "nhip_gd_p50_ms", "nhip_gd_p95_ms", "nhip_gd_p99_ms", "nhip_gd_max_ms", "nhip_gd_bi_chan",
    "xu_ly_p50_ms", "xu_ly_p95_ms", "xu_ly_max_ms", "tinh_moi_buoc_p50_us", "tinh_moi_buoc_p95_us",
    "buoc_moi_nhip_max", "lagging_nhip",
    "so_nhip_dk", "so_nhip_dk_ly_thuyet", "so_nhip_dk_dung", "khoang_dk_p50_ms", "khoang_dk_p99_ms",
    "khoang_dk_max_ms", "khoang_dk_tren_han", "khoang_dk_tren_watchdog",
    "tre_dk_p50_ms", "tre_dk_p95_ms", "tre_dk_max_ms",
    "sai_vi_tri_cm", "sai_huong_do", "quang_duong_m", "lech_moc", "cung_ket_qua_moc",
    "lenh_gui", "telemetry_nhan", "trang_thai_bo",
    "tai_nen_pct", "tai_trong_pct", "cpu_tien_trinh_s", "cpu_ty_le", "ban_ron_p_s", "ban_ron_e_s", "ty_le_e",
    "tep_chuoi", "ghi_chu", "thong_diep",
)
"""Khóa của một dòng ket_qua.jsonl ở chế độ chạy, theo thứ tự. Thời gian của đầu dò tính bằng perf_counter của tiến
trình con, tương đối với lúc `run()` trả về (`t_bat_dau`). `ket_qua`: COMPLETED | FAULT | STOPPED (kết quả của phiên),
KHONG_XONG (công cụ bấm Dừng vì quá `--toi-da-chay`: một phát hiện, KHÔNG bị loại), KHONG_TRA_LOI, BO_QUA. Các khóa
từ `so_nhip_gd` tới `tre_dk_max_ms` là `thong_ke_nhip`; `cung_ket_qua_moc` / `lech_moc`: kết quả giống lượt khởi
động cùng tiến trình hay không (None khi không so được). `lenh_gui`, `telemetry_nhan`, `trang_thai_bo` (chỉ VehicleIO):
`VehicleLink.result` lúc kết thúc lần chạy; `trang_thai_bo` là trạng thái trong khung telemetry cuối nhận được TRƯỚC
khi lệnh DISARM được xác nhận (bo mô phỏng xác nhận trước khung kế tiếp, nên thường còn RUNNING), không phải trạng thái
sau DISARM."""

KHOA_THONG_KE = (
    "tg_tuong_s", "tg_phien_s", "ty_le_phien", "mat_chan_s", "troi_lam_tron_pct", "tre_nhip_dau_ms",
    "so_nhip_gd", "nhip_gd_p50_ms", "nhip_gd_p95_ms", "nhip_gd_p99_ms", "nhip_gd_max_ms", "nhip_gd_bi_chan",
    "xu_ly_p50_ms", "xu_ly_p95_ms", "xu_ly_max_ms", "tinh_moi_buoc_p50_us", "tinh_moi_buoc_p95_us",
    "buoc_moi_nhip_max", "lagging_nhip",
    "so_nhip_dk", "so_nhip_dk_ly_thuyet", "so_nhip_dk_dung", "khoang_dk_p50_ms", "khoang_dk_p99_ms",
    "khoang_dk_max_ms", "khoang_dk_tren_han", "khoang_dk_tren_watchdog", "tre_dk_p50_ms", "tre_dk_p95_ms",
    "tre_dk_max_ms",
)
"""Khóa mà `thong_ke_nhip` trả (mọi khóa đều thuộc `COT_CHAY`)."""


# ------------------------------------------------------------------------------------------- đầu dò (tiến trình con)

def _us(giay: float) -> int:
    return int(round(giay * 1e6))


def _chuoi_rong() -> dict:
    """Chuỗi thô của một lần chạy. gd: một phần tử mỗi nhịp giao diện (lần gọi advance_by); dk: một phần tử mỗi nhịp
    điều khiển khi phiên đang RUNNING hoặc STOPPING (`dung` = chỉ số các nhịp lúc STOPPING)."""
    return {"gd": {k: [] for k in ("w_us", "dt_ms", "buoc", "dk", "xu_ly_us", "tinh_us", "lagging")},
            "dk": {k: [] for k in ("w_us", "buoc", "dung")}}


def _boc(doi_tuong, ten: str, moi) -> tuple:
    """Đặt thuộc tính `ten` của chính đối tượng (không phải của lớp) thành `moi`; trả bản ghi cho `_go_boc`."""
    rieng = vars(doi_tuong)
    ban_ghi = (doi_tuong, ten, ten in rieng, rieng.get(ten), moi)
    setattr(doi_tuong, ten, moi)
    return ban_ghi


def _go_boc(ban_ghi: tuple) -> None:
    """Trả lại thuộc tính `_boc` đã đặt, chỉ khi nó vẫn là của đầu dò (ai bọc tiếp sau thì không gỡ của người đó)."""
    doi_tuong, ten, co_rieng, cu, moi = ban_ghi
    if vars(doi_tuong).get(ten) is not moi:
        return
    if co_rieng:
        setattr(doi_tuong, ten, cu)
    else:
        delattr(doi_tuong, ten)


_HOP_THOAI = {"warning": "Ok", "critical": "Ok", "information": "Ok", "question": "No"}
"""Hàm tĩnh của QMessageBox mà đầu dò thay bằng hàm ghi lại, và nút được coi là đã bấm."""


def van_tay_duong(run_snapshot: dict | None) -> str | None:
    """12 ký tự đầu SHA-1 của đường trong `Session.run_snapshot` (JSON, khóa sắp xếp): hai lần chạy cùng đường thì
    cùng vân tay. Tính sau khi xe dừng nên không tốn gì trong lúc chạy."""
    if not run_snapshot or run_snapshot.get("trajectory") is None:
        return None
    raw = json.dumps(run_snapshot["trajectory"], sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _loi_cong(nhanh: str, cong: str) -> str:
    return f"nhánh {nhanh} chỉ đo với bo mô phỏng; thẻ Bo điều khiển đang chọn {cong}: không mở cổng, thoát"


def chon_nhanh(window, nhanh: str) -> str | None:
    """Chọn nhánh chạy `nhanh` ở ô "Nhánh chạy khi bấm Bắt đầu đỗ" như người dùng chọn (`combo_drive`). Chỉ bo mô
    phỏng: thẻ "Bo điều khiển" phải ở "Bo mô phỏng" (`board_port()` None) trước và sau khi chọn, và liên kết không chạy
    theo đồng hồ thật. Trả lời lỗi (tiến trình con thoát mã 2, không mở cổng nào) hoặc None."""
    if nhanh not in NHANH_CHAY:
        return f"nhánh lạ {nhanh!r}; hợp lệ: {', '.join(NHANH_CHAY)}"
    cong = window.board_port()
    if cong is not None:
        return _loi_cong(nhanh, cong)
    combo = window.combo_drive
    i = combo.findData(nhanh)
    if i < 0:
        return f"giao diện không có nhánh {nhanh}"
    if combo.currentIndex() != i:
        combo.setCurrentIndex(i)                           # → MainWindow._set_drive_mode (bo mô phỏng: không I/O)
    session = window.session
    cong = window.board_port()
    if cong is not None:
        return _loi_cong(nhanh, cong)
    if session.drive_mode.value != nhanh:
        return f"không chọn được nhánh {nhanh} (phiên vẫn ở {session.drive_mode.value})"
    link = session.vehicle_link
    if nhanh != "SIM" and (link is None or link.realtime):
        return f"nhánh {nhanh} chỉ đo với bo mô phỏng; liên kết đang chọn chạy theo đồng hồ thật: thoát"
    return None


class DauDoChay:
    """Đầu dò vòng điều khiển trong tiến trình giao diện (chế độ chạy, `con --chay`).

    Bọc ba thuộc tính của ĐỐI TƯỢNG (tra lúc gọi, nên lớp bọc có tác dụng mà không sửa ứng dụng): `window.advance_by`
    (`_on_tick` gọi `self.advance_by`), `session.advance` (`advance_by` gọi `self.session.advance`) và
    `session._step_closed_loop` (`advance` gọi `self._step_closed_loop`). Lớp bọc chỉ ghi khi đang đo một lần chạy,
    ngoài lúc đó chỉ chuyển tiếp; ghi thêm ≈ 1 µs mỗi bước. Lệnh (một dòng, trả lời mang `yeu_cau`):
    - `chuan_bi <mã>`: phiên đỗ xong / đã dừng / lỗi thì `window.reset()`; trả {"loai": "chuan_bi", "trang_thai_phien",
      "san_sang" (READY và có đường hợp lệ), "co_duong"}; phiên đang tính đường, xem trước, chạy, lái tay thì `loi`.
    - `chay <mã>`: kiểm trước những điều làm `run()` mở hộp thoại hay không chạy (trạng thái, đường, xuất phát, số lần
      đổi chiều T12, ô dấu đồng bộ), rồi gọi `window.run()` (hàm nút "Bắt đầu đỗ" gọi); trả "bat_dau_chay", hoặc `loi`
      khi phiên không vào RUNNING. Khi xe dừng (phiên rời RUNNING/STOPPING) gửi MỘT thông điệp "ket_qua_chay".
    - `dung <mã>`: đang đo và đang RUNNING thì `window.stop()` (nút Dừng); lần chạy đánh dấu `dung_boi_cong_cu`.
    Lệnh khác: `xu_ly` trả False (để `DauDoKeHoach` xử lý). `chan_hop_thoai`: thay QMessageBox.warning / critical /
    information (trả Ok) và question (trả No) bằng hàm ghi lại và báo {"loai": "hop_thoai", ...}: cửa sổ đang thu nhỏ
    không bao giờ đứng chờ một hộp thoại modal (hộp thoại tự dựng bằng QDialog.exec thì không chặn được). `go()` trả lại
    mọi thứ đã thay nếu chúng vẫn là của đầu dò."""

    def __init__(self, window, emit: Callable[[dict], None], *, dong_ho: Callable[[], float] = time.perf_counter,
                 chan_hop_thoai: bool = True):
        from autopark.application.session import SessionState
        from autopark.ui.main_window import RUN_OPEN_STATES

        self.window = window
        self.emit = emit
        self._dong_ho = dong_ho
        self._S = SessionState
        self._mo = RUN_OPEN_STATES                         # RUNNING, STOPPING: lần chạy đang mở
        self.lan = -1
        self.hop_thoai: list[dict] = []
        self._dang_do = False
        self._yeu_cau: str | None = None
        self._t_bat_dau = 0.0
        self._rt = 1.0
        self._nhanh = ""
        self._dung_boi_cong_cu = False
        self._chuoi = _chuoi_rong()
        self._tinh_s = 0.0
        session = window.session
        self._goc_advance_by = window.advance_by
        self._goc_advance = session.advance
        self._goc_buoc = session._step_closed_loop
        self._da_boc = [_boc(window, "advance_by", self._advance_by), _boc(session, "advance", self._advance),
                        _boc(session, "_step_closed_loop", self._buoc)]
        if chan_hop_thoai:
            from PySide6.QtWidgets import QMessageBox

            for ten, nut in _HOP_THOAI.items():
                self._da_boc.append(_boc(QMessageBox, ten, self._ham_hop_thoai(ten, getattr(QMessageBox.StandardButton,
                                                                                           nut))))

    # ---------------------------------------------------------------------------------------------- thông tin, gỡ
    def thong_tin(self, nhanh: str) -> dict:
        """Các khóa thêm vào thông điệp san_sang ở chế độ chạy. `chinh_sach_doi_chieu` là giới hạn đổi chiều CÓ HIỆU
        LỰC lúc Bắt đầu đỗ (`Session.cusp_limit().to_dict()`: cờ dòng lệnh gộp với giới hạn của kịch bản nghiệm thu mà
        tệp sa bàn gắn, cùng giới hạn `_kiem_truoc_khi_chay` và `start_run` dùng), không chỉ chính sách của cờ (sửa
        02/10/2026: trước đó ghi `cusp_policy.to_dict()`, nên tệp gắn DO-1 vẫn ghi max_cusps None)."""
        w, s = self.window, self.window.session
        link = s.vehicle_link
        return {"nhanh": nhanh, "nhip_ms": int(w._timer.interval()), "rt": w._time_scale(),
                "dieu_tiet": eg.doc_dieu_tiet(None), "chinh_sach_doi_chieu": s.cusp_limit().to_dict(),
                "phan_hoi": asdict(s.feedback_config), "max_speed_mps": s.cfg.max_speed,
                "vehicle_link": link.describe() if link is not None else None}

    def go(self) -> None:
        for ban_ghi in reversed(self._da_boc):
            _go_boc(ban_ghi)
        self._da_boc = []

    def _ham_hop_thoai(self, ten: str, tra):
        def thay(*args, **kwargs):
            tieu_de = kwargs.get("title", args[1] if len(args) > 1 else "")
            noi_dung = kwargs.get("text", args[2] if len(args) > 2 else "")
            tin = {"loai": "hop_thoai", "ham": ten, "tieu_de": str(tieu_de), "noi_dung": str(noi_dung)[:300]}
            self.hop_thoai.append(tin)
            self.emit(tin)
            return tra
        return thay

    # ------------------------------------------------------------------------------------------------------ lệnh
    def xu_ly(self, lenh: str) -> bool:
        ten, yeu_cau = _tach_lenh(lenh)
        if ten == "chuan_bi":
            self._chuan_bi(yeu_cau)
        elif ten == "chay":
            self._chay(yeu_cau)
        elif ten == "dung":
            self._dung(yeu_cau)
        else:
            return False
        return True

    def _loi(self, yeu_cau: str | None, thong_diep: str) -> None:
        self.emit({"loai": "loi", "yeu_cau": yeu_cau, "thong_diep": thong_diep[:300]})

    def _chuan_bi(self, yeu_cau: str | None) -> None:
        from autopark.application.session import SessionError

        S, s = self._S, self.window.session
        if self._dang_do:
            self._loi(yeu_cau, "đang đo một lần chạy: chưa chuẩn bị được")
            return
        if s.state in (S.COMPLETED, S.STOPPED, S.FAULT):
            try:
                self.window.reset()
            except SessionError as exc:
                self._loi(yeu_cau, f"không đặt lại được phiên: {exc}")
                return
        if s.state not in (S.EDITING, S.READY):
            self._loi(yeu_cau, f"phiên đang {s.state.value}: không chuẩn bị được")
            return
        duong = s.trajectory
        self.emit({"loai": "chuan_bi", "yeu_cau": yeu_cau, "trang_thai_phien": s.state.value,
                   "san_sang": bool(s.state == S.READY and duong is not None and duong.valid
                                    and not s.path_invalidated),
                   "co_duong": duong is not None})

    def _kiem_truoc_khi_chay(self) -> str | None:
        """Lý do `run()` sẽ mở hộp thoại hay không chạy; None khi bấm được."""
        S, s = self._S, self.window.session
        if self._dang_do:
            return "đang đo một lần chạy khác"
        if s.state not in (S.READY, S.COMPLETED):
            return f"phiên đang {s.state.value}: chỉ bấm 'Bắt đầu đỗ' khi sẵn sàng hoặc đỗ xong (sẽ mở hộp thoại)"
        duong = s.trajectory
        if duong is None or not duong.valid or s.path_invalidated:
            return "chưa có đường hợp lệ để chạy: Bắt đầu đỗ sẽ bị từ chối"
        kiem = s.start_check()
        if not kiem.ok:
            return f"xuất phát không hợp lệ: {kiem.describe()}"
        doi_chieu = s.cusp_check()
        if doi_chieu is not None and doi_chieu.refused:
            return (f"đường có {doi_chieu.n_cusps} lần đổi chiều, vượt giới hạn {doi_chieu.max_cusps} (T12): Bắt đầu "
                    f"đỗ sẽ bị từ chối")
        if self.window.sync_flash.lit():
            return "ô dấu đồng bộ còn sáng: run() sẽ không chạy"
        return None

    def _chay(self, yeu_cau: str | None) -> None:
        w, s = self.window, self.window.session
        ly_do = self._kiem_truoc_khi_chay()
        if ly_do is not None:
            self._loi(yeu_cau, ly_do)
            return
        self.lan += 1
        self._chuoi, self._yeu_cau, self._dung_boi_cong_cu = _chuoi_rong(), yeu_cau, False
        so_hop_thoai = len(self.hop_thoai)
        t_bam = self._dong_ho()
        self._t_bat_dau = t_bam
        self._dang_do = True                               # run() không gọi advance_by: lớp bọc chưa ghi gì
        try:
            w.run()
        except Exception as exc:  # noqa: BLE001 - báo về tiến trình điều khiển thay vì im lặng
            self._dang_do = False
            self._loi(yeu_cau, f"run() lỗi: {exc!r}")
            return
        t_bat_dau = self._dong_ho()
        self._t_bat_dau = t_bat_dau
        if s.state != self._S.RUNNING:
            self._dang_do = False
            hop = "; ".join(f"{h['tieu_de']}: {h['noi_dung']}" for h in self.hop_thoai[so_hop_thoai:]) or "không có"
            self._loi(yeu_cau, f"run() không vào RUNNING (phiên đang {s.state.value}); hộp thoại: {hop}")
            return
        self._rt, self._nhanh = float(w._time_scale()), s.drive_mode.value
        self.emit({"loai": "bat_dau_chay", "yeu_cau": yeu_cau, "lan": self.lan, "nhanh": self._nhanh, "rt": self._rt,
                   "t_bam": t_bam, "t_bat_dau": t_bat_dau, "tg_khoi_dong_ms": round((t_bat_dau - t_bam) * 1000, 3)})

    def _dung(self, yeu_cau: str | None) -> None:
        S, s = self._S, self.window.session
        if self._dang_do and s.state == S.RUNNING:
            self.window.stop()                             # như nút Dừng
            self._dung_boi_cong_cu = True
            self.emit({"loai": "dung", "yeu_cau": yeu_cau, "ok": True})
        elif self._dang_do and s.state == S.STOPPING:     # phiên tự dừng rồi: chờ nó xong, không tính là công cụ dừng
            self.emit({"loai": "dung", "yeu_cau": yeu_cau, "ok": True, "dang_dung": True})
        else:
            self._loi(yeu_cau, "không có lần chạy nào đang đo")

    # -------------------------------------------------------------------------------------------------- lớp bọc
    def _advance_by(self, real_dt: float):
        if not self._dang_do:
            return self._goc_advance_by(real_dt)
        s = self.window.session
        w0 = self._dong_ho()
        buoc0 = s.world.step_count if s.world is not None else 0
        dk = self._chuoi["dk"]["w_us"]
        dk0 = len(dk)
        self._tinh_s = 0.0
        kq = self._goc_advance_by(real_dt)
        w1 = self._dong_ho()
        gd = self._chuoi["gd"]
        gd["w_us"].append(_us(w0 - self._t_bat_dau))
        gd["dt_ms"].append(int(round(real_dt * 1000)))
        gd["buoc"].append((s.world.step_count if s.world is not None else buoc0) - buoc0)
        gd["dk"].append(len(dk) - dk0)
        gd["xu_ly_us"].append(_us(w1 - w0))
        gd["tinh_us"].append(_us(self._tinh_s))
        if s.lagging:
            gd["lagging"].append(len(gd["w_us"]) - 1)
        if s.state not in self._mo:
            self._ket_thuc(w1)
        return kq

    def _advance(self, real_dt: float):
        if not self._dang_do:
            return self._goc_advance(real_dt)
        t0 = self._dong_ho()
        kq = self._goc_advance(real_dt)
        self._tinh_s += self._dong_ho() - t0
        return kq

    def _buoc(self):
        if self._dang_do:
            s = self.window.session
            world = s.world
            if world is not None and s.state in self._mo and world.step_count % s.CONTROL_EVERY == 0:
                dk = self._chuoi["dk"]
                dk["w_us"].append(_us(self._dong_ho() - self._t_bat_dau))
                dk["buoc"].append(world.step_count)
                if s.state == self._S.STOPPING:
                    dk["dung"].append(len(dk["w_us"]) - 1)
        return self._goc_buoc()

    def _ket_thuc(self, t_ket_thuc: float) -> None:
        """Xe đã dừng: một thông điệp ket_qua_chay (≈ 100 KB với lần chạy 21 s), gửi sau khi lần chạy kết thúc."""
        self._dang_do = False
        s = self.window.session
        tin = {"loai": "ket_qua_chay", "yeu_cau": self._yeu_cau, "lan": self.lan, "nhanh": self._nhanh,
               "ket_qua": s.state.value, "ly_do": (s.stop_reason or "")[:200],
               "ma_su_kien": [e.code for e in s.safety_events][:20], "dung_boi_cong_cu": self._dung_boi_cong_cu,
               "rt": self._rt, "nhip_ms": int(self.window._timer.interval()), "t_bat_dau": self._t_bat_dau,
               "t_ket_thuc": t_ket_thuc, "tg_phien_s": s.world.time if s.world is not None else None,
               "bao_cao": None, "cuoi": None, "van_tay_duong": van_tay_duong(s.run_snapshot), "vehicle_io": None}
        bao_cao = s.report
        if bao_cao is not None:
            tin["bao_cao"] = {k: getattr(bao_cao, k) for k in ("completed", "collided", "sim_time", "distance",
                                                                "position_error", "heading_error", "path_finished")}
            cuoi = bao_cao.final_state
            tin["cuoi"] = [cuoi.pose.x, cuoi.pose.y, cuoi.pose.yaw, cuoi.speed, cuoi.steer]
        link = s.run_link
        if link is not None:
            kq = link.result or {}
            ma = [r.get("code") for r in link.event_rows if r.get("handling") in ("stop", "session_stop")]
            tin["vehicle_io"] = {"lenh_gui": kq.get("commands_sent"), "telemetry_nhan": kq.get("telemetry_received"),
                                 "trang_thai_bo": kq.get("board_state"), "ma_dung": list(dict.fromkeys(ma))[:20]}
        tin["chuoi"] = self._chuoi
        tin["dieu_tiet"] = eg.doc_dieu_tiet(None)
        self.emit(tin)


# ----------------------------------------------------------------------------------------------- thống kê (hàm thuần)

def _phan_vi(xs: Iterable[float | None], q: float) -> float | None:
    """Phân vị `q` (0..1) nội suy tuyến tính như numpy "linear"; None khi không có số nào."""
    ds = sorted(x for x in xs if x is not None)
    if not ds:
        return None
    vi_tri = q * (len(ds) - 1)
    duoi = math.floor(vi_tri)
    tren = min(duoi + 1, len(ds) - 1)
    return float(ds[duoi] + (ds[tren] - ds[duoi]) * (vi_tri - duoi))


def _ms(xs: list[float]) -> list[float]:
    return [x * 1000.0 for x in xs]


def thong_ke_nhip(chuoi: dict | None, *, rt: float | None, tg_tuong_s: float | None, tg_phien_s: float | None,
                  dt_buoc: float = 0.005, dk_moi: int = 4, chan_s: float = CHAN_REAL_DT_S,
                  han_lenh_s: float = HAN_LENH_S, watchdog_s: float = WATCHDOG_LIEN_LAC_S) -> dict:
    """Thống kê một lần chạy từ chuỗi thô của `DauDoChay` (thời gian tương đối với t_bat_dau). Trả mọi khóa
    `KHOA_THONG_KE`; chuỗi rỗng hay quá ngắn thì giá trị None, không bao giờ ném lỗi.

    Nhịp giao diện: Δ_i = w_i − w_{i−1} (i ≥ 1) cho p50/p95/p99/max; khoảng của nhịp đầu là w_0 (`tre_nhip_dau_ms`).
    `nhip_gd_bi_chan`: số khoảng (kể cả w_0) > chan_s + 1 ms, real_dt của nhịp đó bị chặn; `mat_chan_s` = rt·Σ max(0,
    khoảng − chan_s): giây phiên mất vì chặn. `troi_lam_tron_pct` = 100·Σ(Δ_i − real_dt_i)/ΣΔ_i trên các nhịp i ≥ 1
    không bị chặn: phần thời gian thật mất vì QElapsedTimer.restart() trả ms nguyên. `tinh_moi_buoc_*_us`: thời gian
    trong Session.advance / số bước (việc mỗi bước như nhau, nên là chỉ báo tốc độ CPU sạch nhất).
    Nhịp điều khiển: chỉ các nhịp lúc RUNNING (bỏ chỉ số `dung`); khoảng giữa hai nhịp liên tiếp (thời gian thật);
    `so_nhip_dk_ly_thuyet` = bước cuối // dk_moi + 1; `tre_dk` = w − bước·dt_buoc/rt: trễ so với lịch lý tưởng theo đồng
    hồ thật (gồm cả phần trôi do chặn và do làm tròn ms). `ty_le_phien` = tg_phien / (tg_tuong·rt)."""
    ra: dict = dict.fromkeys(KHOA_THONG_KE)
    gd = (chuoi or {}).get("gd") or {}
    dk = (chuoi or {}).get("dk") or {}
    rt_ok = rt is not None and math.isfinite(rt) and rt > 0
    ra["tg_tuong_s"], ra["tg_phien_s"] = _tron(tg_tuong_s, 6), _tron(tg_phien_s, 6)
    if rt_ok and tg_tuong_s and tg_tuong_s > 0 and tg_phien_s is not None:
        ra["ty_le_phien"] = _tron(tg_phien_s / (tg_tuong_s * rt), 5)

    w = [x / 1e6 for x in gd.get("w_us") or []]
    if w:
        dt = [x / 1000.0 for x in gd.get("dt_ms") or []]
        delta = [b - a for a, b in zip(w, w[1:])]
        khoang = [w[0]] + delta
        ra["so_nhip_gd"] = len(w)
        ra["tre_nhip_dau_ms"] = _tron(w[0] * 1000.0, 3)
        ra["nhip_gd_bi_chan"] = sum(k > chan_s + 0.001 for k in khoang)
        if rt_ok:
            ra["mat_chan_s"] = _tron(rt * sum(max(0.0, k - chan_s) for k in khoang), 5)
        if delta:
            ms = _ms(delta)
            for ten, q in (("p50", 0.5), ("p95", 0.95), ("p99", 0.99)):
                ra[f"nhip_gd_{ten}_ms"] = _tron(_phan_vi(ms, q), 3)
            ra["nhip_gd_max_ms"] = _tron(max(ms), 3)
            khong_chan = [(d, t) for d, t in zip(delta, dt[1:]) if t < chan_s - 1e-9]
            tong = sum(d for d, _ in khong_chan)
            if tong > 0:
                ra["troi_lam_tron_pct"] = _tron(100.0 * sum(d - t for d, t in khong_chan) / tong, 3)
        xu_ly = [x / 1000.0 for x in gd.get("xu_ly_us") or []]
        if xu_ly:
            ra["xu_ly_p50_ms"], ra["xu_ly_p95_ms"] = _tron(_phan_vi(xu_ly, 0.5), 3), _tron(_phan_vi(xu_ly, 0.95), 3)
            ra["xu_ly_max_ms"] = _tron(max(xu_ly), 3)
        buoc = gd.get("buoc") or []
        moi_buoc = [t / b for t, b in zip(gd.get("tinh_us") or [], buoc) if b > 0]
        ra["tinh_moi_buoc_p50_us"] = _tron(_phan_vi(moi_buoc, 0.5), 3)
        ra["tinh_moi_buoc_p95_us"] = _tron(_phan_vi(moi_buoc, 0.95), 3)
        ra["buoc_moi_nhip_max"] = max(buoc) if buoc else None
        ra["lagging_nhip"] = len(gd.get("lagging") or [])

    dk_w, dk_buoc = dk.get("w_us") or [], dk.get("buoc") or []
    if dk_w:
        dung = set(dk.get("dung") or [])
        ra["so_nhip_dk_dung"] = len(dung)
        chay = [(x / 1e6, b) for i, (x, b) in enumerate(zip(dk_w, dk_buoc)) if i not in dung]
        ra["so_nhip_dk"] = len(chay)
        if chay:
            ra["so_nhip_dk_ly_thuyet"] = chay[-1][1] // dk_moi + 1
            khoang_dk = [b[0] - a[0] for a, b in zip(chay, chay[1:])]
            if khoang_dk:
                ms = _ms(khoang_dk)
                ra["khoang_dk_p50_ms"] = _tron(_phan_vi(ms, 0.5), 3)
                ra["khoang_dk_p99_ms"] = _tron(_phan_vi(ms, 0.99), 3)
                ra["khoang_dk_max_ms"] = _tron(max(ms), 3)
                ra["khoang_dk_tren_han"] = sum(k > han_lenh_s for k in khoang_dk)
                ra["khoang_dk_tren_watchdog"] = sum(k > watchdog_s for k in khoang_dk)
            if rt_ok:
                tre = _ms([v - b * dt_buoc / rt for v, b in chay])
                ra["tre_dk_p50_ms"], ra["tre_dk_p95_ms"] = _tron(_phan_vi(tre, 0.5), 3), _tron(_phan_vi(tre, 0.95), 3)
                ra["tre_dk_max_ms"] = _tron(max(tre), 3)
    return ra


# ------------------------------------------------------------------------------------------ tiến trình điều khiển

@dataclass
class NguCanhChay(NguCanhDo):
    """`NguCanhDo` cộng những thứ của chế độ chạy (tiêm được để test). `kq_gan_nhat`: thông điệp ket_qua_chay của lượt
    vừa đo (None khi không có), để lấy mốc kiểm tính xác định sau lượt khởi động."""

    nhanh: str = "SIM"
    han_chay_s: float = 180.0
    chu_ky_mau_s: float = 1.0
    dong_ho: Callable[[], float] = time.monotonic
    doc_dieu_tiet: Callable[[int | None], dict | None] = eg.doc_dieu_tiet
    doc_phan_giai: Callable[[], tuple | None] = eg.phan_giai_dong_ho_ms
    moc: dict | None = None
    ghi_chuoi: Callable[[str, dict], str | None] | None = None
    kq_gan_nhat: dict | None = None


def mau_trang_thai(trang_thai: str, nc: NguCanhDo, pid_gui: int | None) -> str | None:
    """Một mẫu trạng thái cửa sổ trong lúc xe chạy: None khi vẫn đúng trạng thái đang đo, không thì mã sai. thường:
    giao diện phải ở trước ("truoc:<cửa sổ>") và không thu nhỏ ("thu_nho"); thu nhỏ: phải thu nhỏ ("khong_thu_nho")
    và giao diện không ở trước ("truoc:giao_dien"); bị che: màn che phải phủ kín ("khong_kin"), giao diện không ở
    trước."""
    truoc = eg._truoc_luc_nay(nc, pid_gui)
    gui = nc.gui
    if trang_thai == "thuong":
        if truoc != "giao_dien":
            return f"truoc:{truoc or 'khong_co'}"
        return "thu_nho" if gui is not None and gui.thu_nho_roi is True else None
    if trang_thai == "thu_nho" and (gui is None or gui.thu_nho_roi is not True):
        return "khong_thu_nho"
    if trang_thai == "bi_che" and (nc.che is None or nc.che.kin(gui) is not True):
        return "khong_kin"
    return "truoc:giao_dien" if truoc == "giao_dien" else None


def _hoi(con, lenh: str, yeu_cau: str, loai: str | Sequence[str], cho: float) -> dict | None:
    """Gửi `<lenh> <yeu_cau>`; thông điệp đầu tiên thuộc `loai` mang đúng mã trong `cho` giây, None khi không có."""
    return con.doc(cho, loai, yeu_cau) if con.gui(f"{lenh} {yeu_cau}") else None


def moc_tu_dong(dong: dict, kq: dict | None) -> dict | None:
    """Mốc kiểm tính xác định từ lượt khởi động: chỉ khi lượt có ket_qua_chay và xe không do công cụ dừng (lúc dừng
    phụ thuộc đồng hồ thật)."""
    if not kq or kq.get("loai") != "ket_qua_chay" or kq.get("dung_boi_cong_cu") or kq.get("cuoi") is None:
        return None
    return {"lan": dong.get("lan"), "nhanh": kq.get("nhanh"), "van_tay_duong": kq.get("van_tay_duong"),
            "ket_qua": kq.get("ket_qua"), "cuoi": list(kq["cuoi"]), "tg_phien_s": kq.get("tg_phien_s"),
            "quang_duong": (kq.get("bao_cao") or {}).get("distance")}


def so_moc(kq: dict | None, moc: dict | None, dung_sai: float = 1e-9) -> tuple[bool | None, float | None]:
    """(giống mốc, độ lệch lớn nhất của tư thế cuối [x, y, yaw, tốc độ, góc lái], thời gian phiên và quãng đường).
    (None, None) khi không so được: không có mốc, công cụ dừng xe, khác nhánh hay khác vân tay đường (đã lập lại)."""
    if moc is None or not kq or kq.get("loai") != "ket_qua_chay" or kq.get("dung_boi_cong_cu"):
        return None, None
    if kq.get("nhanh") != moc.get("nhanh") or kq.get("van_tay_duong") != moc.get("van_tay_duong"):
        return None, None
    a = list(moc.get("cuoi") or []) + [moc.get("tg_phien_s"), moc.get("quang_duong")]
    b = list(kq.get("cuoi") or []) + [kq.get("tg_phien_s"), (kq.get("bao_cao") or {}).get("distance")]
    if len(a) != len(b) or len(a) < 3 or any(x is None for x in a + b):
        return None, None
    lech = max(abs(float(x) - float(y)) for x, y in zip(a, b))
    return bool(lech <= dung_sai and kq.get("ket_qua") == moc.get("ket_qua")), lech


def ghi_chuoi(ra: Path | str, ten: str, du_lieu: dict) -> str:
    """Ghi `ra/nhip/<ten>.json.gz` (JSON gọn, gzip mtime = 0: cùng dữ liệu thì cùng byte); trả đường dẫn tương đối."""
    thu_muc = Path(ra) / "nhip"
    thu_muc.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(_sach(du_lieu), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (thu_muc / f"{ten}.json.gz").write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    return f"nhip/{ten}.json.gz"


def _noi(ghi_chu: list[str]) -> str:
    return ";".join(dict.fromkeys(g for g in ghi_chu if g))


def _dien_ket_qua(dong: dict, kq: dict) -> None:
    """Các khóa của dòng lấy thẳng từ thông điệp ket_qua_chay."""
    dung = bool(kq.get("dung_boi_cong_cu"))
    bao_cao = kq.get("bao_cao") or {}
    vio = kq.get("vehicle_io") or {}
    sai_vt, sai_huong = bao_cao.get("position_error"), bao_cao.get("heading_error")
    dong.update(ket_qua="KHONG_XONG" if dung else kq.get("ket_qua"), dung_boi_cong_cu=dung,
                ly_do_dung=(kq.get("ly_do") or "")[:200] or None, ma_su_kien=kq.get("ma_su_kien") or [],
                van_tay_duong=kq.get("van_tay_duong"), rt=kq.get("rt"),
                sai_vi_tri_cm=_tron(sai_vt * 100.0, 3) if sai_vt is not None else None,
                sai_huong_do=_tron(math.degrees(sai_huong), 3) if sai_huong is not None else None,
                quang_duong_m=_tron(bao_cao.get("distance"), 5), lenh_gui=vio.get("lenh_gui"),
                telemetry_nhan=vio.get("telemetry_nhan"), trang_thai_bo=vio.get("trang_thai_bo"),
                thong_diep=(kq.get("ly_do") or "")[:200])


def do_mot_lan_chay(con, lan: int, trang_thai: str, nc: NguCanhChay) -> dict:
    """Một lượt của chế độ chạy; trả một dòng đủ khóa `COT_CHAY`.
    0. `chuan_bi`: phiên chưa sẵn sàng thì về "thường" và lập đường (lệnh `plan`; lượt > 0 ghi `lap_lai_duong`): không
       bao giờ lập đường ở trạng thái đang đo.
    1. `chuyen_trang_thai` như chế độ lập đường.
    2. Chờ `nc.cho` giây (2 s cuối là nền CPU); đọc máy, điều tiết, ưu tiên, CPU, độ phân giải đồng hồ, cửa sổ.
    3. `chay <lan>` (bấm "Bắt đầu đỗ").
    4. Chờ ket_qua_chay, mỗi `chu_ky_mau_s` lấy một mẫu trạng thái cửa sổ (`mau_trang_thai`); quá `han_chay_s` thì gửi
       `dung d<lan>` một lần (mã riêng: trả lời của nó không lẫn với kết quả) và chờ thêm CHO_DUNG_S; vẫn không có kết
       quả thì KHONG_TRA_LOI, ghi chú "khong_dung_duoc" (khối dừng sớm).
    5. Đọc lại; thống kê (`thong_ke_nhip`), so mốc (`so_moc`), ghi chuỗi thô (`nc.ghi_chuoi`), CPU."""
    t_dau = time.perf_counter()
    dong = dict.fromkeys(COT_CHAY)
    dong.update(thoi_diem=time.strftime("%H:%M:%S"), khoi=nc.khoi, bien_the=nc.bien_the, nhanh=nc.nhanh, pid=con.pid,
                lan=lan, khoi_dong=(lan == 0), trang_thai=trang_thai, lap_lai_duong=False, mau_n=0, mau_sai=0,
                thong_diep="")
    ghi_chu = [nc.ghi_chu] if nc.ghi_chu else []
    gui, che = nc.gui, nc.che
    nc.kq_gan_nhat = None

    def ket(ket_qua: str, thong_diep: str, *them: str) -> dict:
        ghi_chu.extend(them)
        dong.update(ket_qua=ket_qua, thong_diep=str(thong_diep or "")[:200], ghi_chu=_noi(ghi_chu))
        return dong

    # 0. phiên sẵn sàng
    tin = _hoi(con, "chuan_bi", f"c{lan}", ("chuan_bi", "loi"), CHO_MAN_CHE_S)
    if tin is None:
        return ket("KHONG_TRA_LOI", "không trả lời chuan_bi" if con.con_song else "tiến trình con đã thoát")
    if tin.get("loai") == "loi":
        return ket("BO_QUA", tin.get("thong_diep", ""), "dau_do_tu_choi")
    if not tin.get("san_sang"):
        chuyen = eg.chuyen_trang_thai(con, "thuong", nc, lan)
        if chuyen.bo_qua is not None:
            return ket("BO_QUA", chuyen.bo_qua[1], chuyen.bo_qua[0])
        lap = _hoi(con, "plan", f"p{lan}", ("ket_qua", "loi"), CHO_KET_QUA_S)
        if lap is None or lap.get("loai") != "ket_qua" or lap.get("ket_qua") != "OK":
            ly = "không trả lời" if lap is None else (lap.get("ket_qua") or "") + ": " + str(lap.get("thong_diep", ""))
            return ket("BO_QUA", f"không lập được đường ({ly})", "khong_lap_duoc_duong")
        if lan > 0:
            dong["lap_lai_duong"] = True
            ghi_chu.append("lap_lai_duong")

    # 1. trạng thái cửa sổ
    chuyen = eg.chuyen_trang_thai(con, trang_thai, nc, lan)
    dong.update(cap_quyen_truoc=chuyen.cap_quyen_truoc, ket_qua_dua_ra_truoc=chuyen.ket_qua_dua_ra_truoc)
    if chuyen.bo_qua is not None:
        return ket("BO_QUA", chuyen.bo_qua[1], chuyen.bo_qua[0])

    # 2. chờ ổn định; nền CPU là 2 s cuối
    nc.ngu(max(0.0, nc.cho - 2.0))
    c_nen = nc.chup_cpu()
    nc.ngu(2.0)
    may0 = nc.doc_may()
    dieu_tiet = nc.doc_dieu_tiet(con.pid) or {}
    ecoqos = dieu_tiet.get("ecoqos") or nc.ecoqos_cua(con.pid)
    muc_uu_tien, cpu0, phan_giai = nc.uu_tien_cua(con.pid), nc.cpu_cua(con.pid), nc.doc_phan_giai()
    if gui is not None:
        dong.update(gui_thu_nho=gui.thu_nho_roi, gui_hien=gui.hien, gui_lo_ra=_tron(gui.ty_le_lo_ra(), 3))
    if trang_thai == "bi_che":
        dong["che_kin"] = che.kin(gui) if che is not None else None
    dong.update(ecoqos=ecoqos or "khong_doc_duoc", dong_ho=dieu_tiet.get("dong_ho") or "khong_doc_duoc",
                uu_tien=muc_uu_tien or "khong_doc_duoc", phan_giai_ms=_tron(phan_giai[2], 4) if phan_giai else None,
                phien=may0.phien, ket_noi=may0.ket_noi, ban_lam_viec=may0.ban_lam_viec, man_hinh=may0.man_hinh,
                vang_s=_tron(may0.vang_s, 3), cua_so_truoc=eg._cua_so_truoc(may0, con.pid, che))
    c0 = nc.chup_cpu()

    # 3. bấm "Bắt đầu đỗ"
    yeu_cau = str(lan)
    bat_dau = _hoi(con, "chay", yeu_cau, ("bat_dau_chay", "loi"), CHO_BAT_DAU_S)
    if bat_dau is None:
        return ket("KHONG_TRA_LOI", f"không có bat_dau_chay trong {CHO_BAT_DAU_S:.0f} s" if con.con_song
                   else "tiến trình con đã thoát")
    if bat_dau.get("loai") == "loi":
        return ket("BO_QUA", bat_dau.get("thong_diep", ""), "dau_do_tu_choi")

    # 4. chờ xe dừng, lấy mẫu trạng thái cửa sổ
    t0 = nc.dong_ho()
    het = t0 + nc.han_chay_s
    da_dung, kq = False, None
    mau: list[dict] = []
    while True:
        con_lai = het - nc.dong_ho()
        if con_lai <= 0:
            if da_dung:
                break
            con.gui(f"dung d{lan}")
            da_dung, het = True, nc.dong_ho() + CHO_DUNG_S
            continue
        cho = min(nc.chu_ky_mau_s, con_lai)
        t_hoi = nc.dong_ho()
        kq = con.doc(cho, ("ket_qua_chay", "loi"), yeu_cau)
        if kq is not None or not con.con_song:
            break
        sai = mau_trang_thai(trang_thai, nc, con.pid)
        pg = nc.doc_phan_giai()
        mau.append({"t": round(nc.dong_ho() - t0, 3), "sai": sai, "phan_giai_ms": pg[2] if pg else None})
        con_thieu = cho - (nc.dong_ho() - t_hoi)
        if con_thieu > 0.5 * cho:                          # doc() trả sớm (stdout đã đóng): không quay vòng bận
            nc.ngu(con_thieu)

    # 5. đọc lại
    c1 = nc.chup_cpu()
    t_sau = time.perf_counter()
    may1 = nc.doc_may()
    cpu1 = nc.cpu_cua(con.pid)
    sai = [m for m in mau if m["sai"]]
    dong.update(phien_sau=may1.phien, man_hinh_sau=may1.man_hinh, vang_s_sau=_tron(may1.vang_s, 3),
                mau_n=len(mau), mau_sai=len(sai),
                mau_sai_dau=f"t={_so(sai[0]['t'], 1)} s: {sai[0]['sai']}" if sai else None)
    nc.kq_gan_nhat = kq
    if kq is None:
        if da_dung and con.con_song:
            ghi_chu.append("khong_dung_duoc")
        dong.update(ket_qua="KHONG_TRA_LOI",
                    thong_diep=(f"không có kết quả sau {nc.han_chay_s:.0f} s + {CHO_DUNG_S:.0f} s (đã bấm Dừng)"
                                if da_dung else "tiến trình con đã thoát"))
    elif kq.get("loai") == "loi":
        ghi_chu.append("dau_do_tu_choi")
        dong.update(ket_qua="BO_QUA", thong_diep=str(kq.get("thong_diep", ""))[:200])
    else:
        _dien_ket_qua(dong, kq)
        tg_tuong = None
        if kq.get("t_ket_thuc") is not None and kq.get("t_bat_dau") is not None:
            tg_tuong = kq["t_ket_thuc"] - kq["t_bat_dau"]
        dong.update(thong_ke_nhip(kq.get("chuoi"), rt=kq.get("rt"), tg_tuong_s=tg_tuong,
                                  tg_phien_s=kq.get("tg_phien_s")))
        dong["cung_ket_qua_moc"], lech = so_moc(kq, nc.moc)
        dong["lech_moc"] = None if lech is None else float(f"{lech:.3g}")
        if nc.ghi_chuoi is not None:
            ten = f"k{nc.khoi}_{nc.bien_the}_{nc.nhanh}_l{lan:02d}_{trang_thai}"
            dong["tep_chuoi"] = nc.ghi_chuoi(ten, {"khoa": {k: dong[k] for k in ("khoi", "bien_the", "nhanh", "lan",
                                                                                 "trang_thai", "pid")},
                                                   "t_bat_dau": kq.get("t_bat_dau"), "rt": kq.get("rt"),
                                                   "nhip_ms": kq.get("nhip_ms"), "chuoi": kq.get("chuoi"),
                                                   "mau": mau})
    tg_tuong = dong.get("tg_tuong_s")
    dong["tai_nen_pct"] = _tron(eg.tai_pct(c_nen, c0), 1)
    dong["tai_trong_pct"] = _tron(eg.tai_pct(c0, c1), 1)
    cpu = cpu1 - cpu0 if cpu0 is not None and cpu1 is not None else None
    dong["cpu_tien_trinh_s"] = _tron(cpu, 3)
    dong["cpu_ty_le"] = _tron(cpu / tg_tuong, 3) if cpu is not None and tg_tuong else None
    them = eg.ban_ron_them(c_nen, c0, c1, nc.lop_cpu) if nc.lop_cpu else None
    if them:
        e = min(them)
        dong["ban_ron_e_s"] = round(max(0.0, them[e]), 3)
        dong["ban_ron_p_s"] = round(sum(max(0.0, v) for cap, v in them.items() if cap != e), 3)
        dong["ty_le_e"] = _tron(eg.ty_le_e(them, tg_tuong, toi_thieu=0.1), 3)
    if (trang_thai == "bi_che" or chuyen.dung_trung_tinh) and che is not None and not che.con_song():
        ghi_chu.append(che.ly_do_dong)                    # người dùng đóng màn che / cửa sổ trung tính giữa lượt
        dong.update(ket_qua="BO_QUA", thong_diep=f"{dong['ket_qua']}: {dong['thong_diep'] or ''}"[:200])
    if may1.vang_s is not None and may1.vang_s + 0.25 < t_sau - t_dau:
        ghi_chu.append("nguoi_dung_thao_tac")
    dong["ghi_chu"] = _noi(ghi_chu)
    return dong


def dong_console_chay(dong: dict) -> str:
    """Một dòng in ra màn hình / nhat_ky.txt cho mỗi lượt của chế độ chạy."""
    ly_do = eg.ly_do_loai(dong)
    truoc = ""
    if dong.get("cua_so_truoc") is not None:
        truoc = f" ở trước={dong['cua_so_truoc'] or 'không có'}"
        ra_truoc = dong.get("ket_qua_dua_ra_truoc")
        if ra_truoc and ra_truoc != f"{DICH_TRUOC.get(dong.get('trang_thai'), '')}:ok":
            truoc += f" (đưa ra trước: {ra_truoc}; cấp quyền: {dong.get('cap_quyen_truoc') or 'không cần'})"
    dau = (f"{dong.get('thoi_diem')} khối {dong.get('khoi')} {dong.get('bien_the')} {dong.get('nhanh')} lần "
           f"{dong.get('lan')} {dong.get('trang_thai')}: {dong.get('ket_qua')}")
    if dong.get("so_nhip_gd") is None:
        than = f" ({dong.get('thong_diep') or ''})"
    else:
        than = (f" {_so(dong.get('tg_phien_s'), 1)} s phiên / {_so(dong.get('tg_tuong_s'), 1)} s thật "
                f"({_so(dong.get('ty_le_phien'), 3)}); nhịp GD p95 {_so(dong.get('nhip_gd_p95_ms'), 1)} ms max "
                f"{_so(dong.get('nhip_gd_max_ms'), 0)} ms; khoảng ĐK max {_so(dong.get('khoang_dk_max_ms'), 0)} ms "
                f"(> {_so(HAN_LENH_S)} s: {dong.get('khoang_dk_tren_han')}); tính/bước "
                f"{_so(dong.get('tinh_moi_buoc_p50_us'), 1)} µs")
    return (dau + than + f"; ecoqos={dong.get('ecoqos')} đồng hồ={dong.get('dong_ho')}" + truoc
            + (f" [loại: {ly_do}]" if ly_do else ""))


def _dat_bien_the(bien_the: str, pid: int, san_sang: dict) -> tuple[str, str | None, dict | None, str]:
    """Đặt và đọc lại EcoQoS của tiến trình giao diện theo biến thể. Trả (ghi chú của khối, cách tắt, điều tiết đọc
    lại, dòng nhật ký). gui_system: phải còn "system" lúc sẵn sàng (đã đặt AUTOPARK_KEEP_ECOQOS=1); không đọc được
    (None) thì không loại (`ecoqos_gui.kiem_gui_system`, sửa 02/10/2026; `chay_do_chay` in cảnh báo). gui_off: đã "off"
    lúc sẵn sàng thì cách tắt "ung_dung", không thì tắt theo pid ("theo_pid") rồi đọc lại. gui_off_dh: tắt EcoQoS và
    luôn tôn trọng độ phân giải đồng hồ theo pid, đọc lại phải là {"ecoqos": "off", "dong_ho": "ton_trong"}."""
    if bien_the == "gui_system":
        dieu_tiet = eg.doc_dieu_tiet(pid)
        kiem = eg.kiem_gui_system(san_sang.get("ecoqos"))  # None: không biết → giữ dòng (chay_do_chay cảnh báo)
        ghi_chu = "khong_giu_duoc_ecoqos" if kiem == "khong_giu_duoc_ecoqos" else ""
        return ghi_chu, None, dieu_tiet, \
            (f"gui_system: EcoQoS lúc sẵn sàng {san_sang.get('ecoqos')}"
             + (f" ({eg.ECOQOS_KHONG_DOC_DUOC}; các dòng vẫn được giữ)" if kiem == "khong_doc_duoc" else "")
             + f", điều tiết {dieu_tiet}")
    if bien_the == "gui_off":
        if san_sang.get("ecoqos") == "off":
            dieu_tiet = eg.doc_dieu_tiet(pid)
            return "", "ung_dung", dieu_tiet, f"gui_off: ứng dụng đã tự tắt EcoQoS, điều tiết {dieu_tiet}"
        tat = eg.disable_power_throttling(pid)
        sau = eg.execution_speed_throttling(pid)
        dieu_tiet = eg.doc_dieu_tiet(pid)
        return ("" if tat and sau == "off" else "khong_tat_duoc_ecoqos"), "theo_pid", dieu_tiet, \
            f"gui_off: disable_power_throttling({pid}) = {tat}, EcoQoS đọc lại {sau}, điều tiết {dieu_tiet}"
    dat = eg.dat_ton_trong_dong_ho(pid)
    dieu_tiet = eg.doc_dieu_tiet(pid)
    ok = dat and dieu_tiet == {"ecoqos": "off", "dong_ho": "ton_trong"}
    return ("" if ok else "khong_tat_duoc_ecoqos"), "theo_pid_dong_ho", dieu_tiet, \
        f"gui_off_dh: dat_ton_trong_dong_ho({pid}) = {dat}, điều tiết đọc lại {dieu_tiet}"


def chay_do_chay(args, argv: Sequence[str]) -> int:
    """Lệnh `do-chay` (gọi từ `ecoqos_gui.main`). Mã thoát như `do`: 0 khi đã đi hết lịch đo — mọi lượt đã có dòng (kể
    cả dòng bị loại), TRỪ phần còn lại của khối nào có một lần chạy không dừng được (KHONG_TRA_LOI cả sau khi bấm Dừng,
    ghi chú `khong_dung_duoc`): khối đó bị bỏ dở, công cụ sang khối sau và vẫn trả 0; khi ấy may.json ghi
    `khoi_bo_do` (khối, biến thể, nhánh, lần, trạng thái, số lượt bỏ) và tom_tat.txt có dòng CẢNH BÁO (sửa 02/10/2026:
    trước đó không tệp nào ghi việc này); 1 khi phải dừng giữa chừng (các dòng đã ghi vẫn giữ, tom_tat.txt vẫn được
    viết); 2 khi tham số sai (trước khi tạo thư mục hay mở tiến trình nào)."""
    def loi(thong_diep: str) -> int:
        print(f"Lỗi: {thong_diep}", file=sys.stderr)
        return 2

    if sys.platform != "win32":
        return loi("chỉ chạy trên Windows (EcoQoS là cơ chế của Windows 11)")
    ra = Path(args.ra)
    if (ra / "ket_qua.jsonl").exists():
        return loi(f"{ra / 'ket_qua.jsonl'} đã có: chọn thư mục mới")
    nhanh, bien_the, trang_thai = (eg._tach_ds(x) for x in (args.nhanh, args.bien_the, args.trang_thai))
    if "khong_cua_so" in bien_the:
        return loi("biến thể khong_cua_so chưa có ở chế độ chạy (lần chạy cần cửa sổ giao diện)")
    la = ([x for x in nhanh if x not in NHANH_CHAY] + [b for b in bien_the if b not in BIEN_THE_CHAY]
          + [t for t in trang_thai if t not in TRANG_THAI])
    if la or not (nhanh and bien_the and trang_thai) or any(len(set(d)) != len(d) for d in (nhanh, bien_the,
                                                                                           trang_thai)):
        return loi(f"tên lạ hoặc lặp: {', '.join(la) or '(danh sách rỗng/lặp)'}; nhánh hợp lệ: {', '.join(NHANH_CHAY)}; "
                   f"biến thể hợp lệ: {', '.join(BIEN_THE_CHAY)}; trạng thái hợp lệ: {', '.join(TRANG_THAI)}")
    if args.kich_ban is not None and args.ca is not None:
        return loi("--kich-ban và --ca không dùng cùng nhau")
    nguon = Path(args.kich_ban) if args.kich_ban is not None else KICH_BAN_MAC_DINH
    if args.ca is not None and args.ca not in eg._ten_cac_ca():
        return loi(f"không có ca {args.ca!r}; các ca: {', '.join(eg._ten_cac_ca())}")
    if args.ca is None and not nguon.is_file():
        return loi(f"không có tệp kịch bản {nguon}")
    if args.cho < 2:
        return loi("--cho phải ≥ 2 giây (2 s cuối dùng để đo tải nền)")
    if args.khoi < 1 or args.lap < 1:
        return loi("--khoi và --lap phải ≥ 1")
    if not args.toi_da_chay >= TOI_THIEU_TOI_DA_CHAY_S:
        return loi(f"--toi-da-chay phải ≥ {TOI_THIEU_TOI_DA_CHAY_S:.0f} giây")

    git = eg.doc_git()                                    # đọc trước khi tạo thư mục kết quả
    ra.mkdir(parents=True, exist_ok=True)
    dpi = eg.dat_dpi_vat_ly()
    kich_ban, lech = eg.viet_kich_ban(args.ca, ra) if args.ca is not None else eg.viet_kich_ban_tep(nguon, ra)
    lop = eg.lop_cpu()
    phan_giai = eg.phan_giai_dong_ho_ms()
    may_dau = eg.doc_trang_thai_may()
    to_hop = [(bt, nh) for bt in bien_the for nh in nhanh]
    lich = [(k, bt, nh, eg.thu_tu_do(trang_thai, args.lap, k, bt)) for k in range(args.khoi)
            for bt, nh in eg._xoay(to_hop, k)]
    so_lan = sum(len(ds) for *_, ds in lich)
    uoc_tinh_s = sum(8.0 + 10.0 + len(ds) * (args.cho + T_UOC_CHAY_S + 5.0) for *_, ds in lich)
    nguon_dien = eg.doc_nguon()
    may = {
        "che_do": "chay", "cong_cu": MODULE,
        "lenh": f"python -X utf8 -m {MODULE} " + subprocess.list2cmdline(list(argv)),
        "python_exe": sys.executable, "bat_dau": eg._bay_gio(), "ket_thuc": None, "git": git,
        "windows": eg.doc_windows(),
        "cpu": {"logic": os.cpu_count(), "lop": {str(k): v for k, v in (lop or {}).items()} or None},
        "nguon": nguon_dien,
        "moi_truong": {"gui_system": eg.moi_truong_con(giu_ecoqos=True)[1],
                       "gui_off": eg.moi_truong_con(giu_ecoqos=False)[1]},
        "dpi_vat_ly": dpi, "python": sys.version.split()[0], "pyside6": eg._phien_ban("PySide6"),
        "ca": args.ca, "kich_ban_nguon": None if args.ca is not None else str(nguon), "kich_ban": kich_ban.name,
        "kich_ban_lech": lech if math.isfinite(lech) else "khac_cau_truc",
        "nhanh": nhanh, "bien_the": bien_the, "trang_thai": trang_thai, "khoi": args.khoi, "lap": args.lap,
        "cho_s": args.cho, "toi_da_chay_s": args.toi_da_chay, "giu_chuoi": not args.khong_giu_chuoi,
        "so_lan_du_kien": so_lan, "uoc_tinh_s": round(uoc_tinh_s),
        "phan_giai_dong_ho_ms": list(phan_giai) if phan_giai else None, "nhip_ms": None, "rt": None,
        "trang_thai_may_dau": may_dau.to_dict(), "trang_thai_may_cuoi": None, "so_dong": 0, "dung_giua_chung": "",
        "khoi_tien_trinh": [], "khoi_bo_do": [],
    }
    eg._ghi_json(ra / "may.json", may)
    eg.ghi_powercfg_bo_xu_ly(ra, may["bat_dau"])

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

    in_ra(f"{eg._bay_gio()} Đo vòng điều khiển khi chạy: kịch bản {kich_ban.name}, {len(lich)} khối (biến thể × nhánh "
          f"× {args.khoi}), {so_lan} lần chạy, ước tính ≈ {math.ceil(uoc_tinh_s / 60)} phút. Kết quả: {ra}")
    in_ra("Đừng dùng máy trong lúc đo (một lần nhấn phím / chuột làm mất quyền đặt cửa sổ ở trước và loại lượt đang "
          "chạy). Màn che và cửa sổ trung tính: Esc hoặc bấm chuột để đóng (các lượt 'bị che' còn lại bị bỏ).")
    tat_ac = nguon_dien.get("tat_man_hinh_ac_s")
    if isinstance(tat_ac, (int, float)) and 0 < tat_ac < uoc_tinh_s:
        in_ra(f"CẢNH BÁO: màn hình tự tắt sau {tat_ac} s khi cắm điện, ngắn hơn thời gian đo ước tính: các lượt sau đó "
              f"bị loại (man_hinh_tat); công cụ không đổi thiết lập.")
    if lech:
        in_ra(f"CẢNH BÁO: kịch bản lệch {f'{lech:.3g}' if math.isfinite(lech) else 'khác cấu trúc'} sau khi lưu và nạp "
              f"lại (vẫn đo; ghi trong tóm tắt)")
    if not may_dau.nhin_thay_duoc:
        in_ra(f"CẢNH BÁO: lúc bắt đầu phiên={may_dau.phien}, kết nối={may_dau.ket_noi}, bàn làm việc="
              f"'{may_dau.ban_lam_viec}', màn hình={may_dau.man_hinh}. {GIAI_THICH_KHOA}")

    tien_trinh: list = []
    che = None
    so_dong, ma, ly_do_dung = 0, 0, ""

    def khoi_dong(tham_so: list[str], ten: str, env: dict | None = None) -> tuple:
        p = eg.TienTrinhCon(tham_so, ten, ghi=ghi, env=env)
        tien_trinh.append(p)
        tin = p.doc(CHO_SAN_SANG_S, ("san_sang", "loi"))
        if tin is None or tin.get("loai") != "san_sang":
            raise eg._DungDo(f"tiến trình {ten} không sẵn sàng trong {CHO_SAN_SANG_S:.0f} s: "
                             f"{(tin or {}).get('thong_diep', 'không trả lời')}")
        ghi(f"{eg._bay_gio()} {ten}: pid {p.pid} (Popen {p.proc.pid}), {json.dumps(tin, ensure_ascii=False)}")
        return p, tin

    try:
        if any(t != "thuong" for t in trang_thai):
            toi_da = min(3600.0, uoc_tinh_s + 300.0)       # màn che và cửa sổ trung tính cùng tiến trình
            che = eg.ManChe(*khoi_dong(["che", "--toi-da", f"{toi_da:.0f}"], "che"))
        with (ra / "ket_qua.jsonl").open("a", encoding="utf-8") as tep:
            for khoi, bt, nh, ds in lich:
                env = eg.moi_truong_con(giu_ecoqos=(bt == "gui_system"))[0]
                p, tin = khoi_dong(["con", "--kich-ban", str(kich_ban), "--chay", "--nhanh", nh], f"{bt}/{nh}", env)
                gui = eg.CuaSoWin32(int(tin["hwnd"])) if tin.get("hwnd") else None
                ghi_chu, cach_tat, dieu_tiet, nhat_ky_bt = _dat_bien_the(bt, p.pid, tin)
                ghi(f"{eg._bay_gio()} {nhat_ky_bt}")
                if ghi_chu:
                    in_ra(f"CẢNH BÁO: {bt}/{nh} (pid {p.pid}): {ghi_chu} ({nhat_ky_bt}); các dòng của khối này bị "
                          f"loại")
                elif bt == "gui_system" and eg.kiem_gui_system(tin.get("ecoqos")) == "khong_doc_duoc":
                    in_ra(f"CẢNH BÁO: {bt}/{nh} (pid {p.pid}) lúc sẵn sàng {eg.ECOQOS_KHONG_DOC_DUOC}: không kiểm "
                          f"được giao diện còn ở mặc định của Windows; các dòng của khối này vẫn được giữ")
                may["nhip_ms"] = may["nhip_ms"] or tin.get("nhip_ms")
                may["rt"] = may["rt"] or tin.get("rt")
                khoi_tt = {"khoi": khoi, "bien_the": bt, "nhanh": nh, "pid": p.pid, "ecoqos_san_sang": tin.get("ecoqos"),
                           "dieu_tiet_san_sang": tin.get("dieu_tiet"), "dieu_tiet": dieu_tiet, "cach_tat": cach_tat,
                           "nhip_ms": tin.get("nhip_ms"), "rt": tin.get("rt"),
                           "chinh_sach_doi_chieu": tin.get("chinh_sach_doi_chieu"),
                           "max_speed_mps": tin.get("max_speed_mps"), "vehicle_link": tin.get("vehicle_link"),
                           "tg_chay_khoi_dong_s": None}
                may["khoi_tien_trinh"].append(khoi_tt)
                nc = NguCanhChay(gui=gui, che=che if gui is not None else None, cho=args.cho, khoi=khoi, bien_the=bt,
                                 lop_cpu=lop, ghi_chu=ghi_chu, nhanh=nh, han_chay_s=args.toi_da_chay,
                                 ghi_chuoi=None if args.khong_giu_chuoi else functools.partial(ghi_chuoi, ra))
                for i_lan, (lan, tt) in enumerate(ds):
                    if not p.con_song or (gui is not None and not gui.ton_tai):
                        raise eg._DungDo(f"tiến trình {bt}/{nh} (pid {p.pid}) đã thoát hoặc cửa sổ đã bị đóng, "
                                         f"trước lần {lan}")
                    dong = do_mot_lan_chay(p, lan, tt, nc)
                    tep.write(json.dumps(_sach(dong), ensure_ascii=False) + "\n")
                    tep.flush()
                    so_dong += 1
                    in_ra(dong_console_chay(dong))
                    if lan == 0:
                        nc.moc = moc_tu_dong(dong, nc.kq_gan_nhat)
                        tg = dong.get("tg_tuong_s")
                        if tg:
                            khoi_tt["tg_chay_khoi_dong_s"] = tg
                            nc.han_chay_s = min(args.toi_da_chay, max(60.0, 3.0 * tg + 20.0))
                            con_lai_s = (so_lan - so_dong) * (args.cho + tg + 5.0) + 18.0 * (len(lich) - 1)
                            in_ra(f"Lượt khởi động: {_so(dong.get('tg_phien_s'), 1)} s mô phỏng / {_so(tg, 1)} s thật "
                                  f"→ còn ≈ {math.ceil(con_lai_s / 60)} phút")
                    if "khong_dung_duoc" in (dong.get("ghi_chu") or ""):
                        bo = len(ds) - i_lan - 1                 # lượt còn lại của khối: không đo, không có dòng
                        may["khoi_bo_do"].append({"khoi": khoi, "bien_the": bt, "nhanh": nh, "lan": lan,
                                                  "trang_thai": tt, "luot_bo": bo})
                        in_ra(f"CẢNH BÁO: {bt}/{nh}: lần chạy không dừng được; bỏ phần còn lại của khối này ({bo} "
                              f"lượt chưa đo)")
                        break
                if che is not None and gui is not None:
                    che.an()
                p.dong()
    except eg._DungDo as exc:
        ma, ly_do_dung = 1, str(exc)
        in_ra(f"{eg._bay_gio()} DỪNG: {exc}")
    except KeyboardInterrupt:
        ma, ly_do_dung = 1, "Ctrl+C"
        in_ra(f"{eg._bay_gio()} DỪNG: Ctrl+C")
    finally:
        for p in tien_trinh:                               # dong() gọi lại với tiến trình đã đóng thì không làm gì
            p.dong()
        may.update(ket_thuc=eg._bay_gio(), trang_thai_may_cuoi=eg.doc_trang_thai_may().to_dict(), so_dong=so_dong,
                   dung_giua_chung=ly_do_dung)
        eg._ghi_json(ra / "may.json", may)
        van_ban = tom_tat_chay(eg._doc_jsonl(ra / "ket_qua.jsonl"), may)
        (ra / "tom_tat.txt").write_text(van_ban, encoding="utf-8")
        bo_do = may["khoi_bo_do"]
        in_ra(f"{eg._bay_gio()} Xong: {so_dong}/{so_lan} lần chạy"
              + (f" ({len(bo_do)} khối bị bỏ dở vì lần chạy không dừng được, {sum(k['luot_bo'] for k in bo_do)} lượt "
                 f"chưa đo: khoi_bo_do trong may.json)" if bo_do else "")
              + f"; tóm tắt: {ra / 'tom_tat.txt'}")
        nhat_ky.close()
    return ma


# --------------------------------------------------------------------------------------------------------- tóm tắt

_TEN_TRANG_THAI = {"thuong": "thường", "thu_nho": "thu nhỏ", "bi_che": "bị che"}
_TEN_CHIEU = {"tinh": "tính/bước", "nhip": "nhịp giao diện"}
_NHAN_MUC = {"cham_ro": "chậm rõ", "cham_nhe": "có thể chậm nhẹ", "khong_cham": "không thấy chậm",
             "khong_du": "không đủ lượt hợp lệ để so"}


def _nhom_chay(ds: list[dict], nhanh: str, bien_the: str, trang_thai: str) -> list[dict]:
    return [d for d in ds if d.get("nhanh") == nhanh and d.get("bien_the") == bien_the
            and d.get("trang_thai") == trang_thai]


def _lon_nhat(ds: list[dict], khoa: str) -> float | None:
    xs = [d[khoa] for d in ds if d.get(khoa) is not None]
    return max(xs) if xs else None


def _ds_nhanh(dong: list[dict], may: dict) -> list[str]:
    ds = [n for n in (may.get("nhanh") or []) if n in NHANH_CHAY]
    for d in dong:
        if d.get("nhanh") in NHANH_CHAY and d["nhanh"] not in ds:
            ds.append(d["nhanh"])
    return ds


def _dem_xong(ds: list[dict]) -> str:
    """"COMPLETED 2/2" (cộng các kết quả khác trong ngoặc); "0" khi nhóm rỗng."""
    if not ds:
        return "0"
    dem = Counter(str(d.get("ket_qua")) for d in ds)
    khac = ", ".join(f"{k} {v}" for k, v in dem.most_common() if k != "COMPLETED")
    return f"COMPLETED {dem.get('COMPLETED', 0)}/{len(ds)}" + (f" ({khac})" if khac else "")


def _he_so_chay(xet: list[dict], moc: list[dict], khoa: str) -> float | None:
    """Trung vị `khoa` của xet / của mốc; None khi một bên có ít hơn TOI_THIEU_LUOT giá trị."""
    a = [d[khoa] for d in xet if d.get(khoa) is not None]
    b = [d[khoa] for d in moc if d.get(khoa) is not None]
    if len(a) < TOI_THIEU_LUOT or len(b) < TOI_THIEU_LUOT:
        return None
    goc = _trung_vi(b)
    return _trung_vi(a) / goc if goc and goc > 0 else None


def _tuyet_doi(xet: list[dict], moc: list[dict]) -> list[str]:
    """Dấu hiệu tuyệt đối có ở xet mà mốc không có: mất > MAT_DANG_KE_S s phiên do chặn, khoảng điều khiển > hạn lệnh,
    lượt KHONG_XONG."""
    dau_hieu = {"mat_chan": lambda d: (d.get("mat_chan_s") or 0.0) > MAT_DANG_KE_S,
                "tren_han": lambda d: (d.get("khoang_dk_tren_han") or 0) > 0,
                "khong_xong": lambda d: d.get("ket_qua") == "KHONG_XONG"}
    return [ten for ten, co in dau_hieu.items() if any(map(co, xet)) and not any(map(co, moc))]


def _muc_chay(xet: list[dict], moc: list[dict]) -> tuple[str, dict]:
    """Mức chậm của gui_system ở một trạng thái so với mốc gui_system/thuong cùng nhánh, và số liệu. Chậm rõ: hệ số
    tính/bước ≥ NGUONG_CHAM, hoặc nhịp giao diện p95 ≥ HE_SO_NHIP_CHAM, hoặc có dấu hiệu tuyệt đối (`_tuyet_doi`); chậm
    nhẹ: tính/bước ≥ NGUONG_NHIEU hoặc nhịp p95 ≥ HE_SO_NHIP_NHE; không đủ: một bên ít hơn TOI_THIEU_LUOT lượt."""
    sl = {"hs_tinh": _he_so_chay(xet, moc, "tinh_moi_buoc_p50_us"),
          "hs_nhip": _he_so_chay(xet, moc, "nhip_gd_p95_ms"),
          "dk_max_ms": _lon_nhat(xet, "khoang_dk_max_ms"), "mat_chan_s": _lon_nhat(xet, "mat_chan_s"),
          "tren_han": sum(d.get("khoang_dk_tren_han") or 0 for d in xet), "tuyet_doi": []}
    if len(xet) < TOI_THIEU_LUOT or len(moc) < TOI_THIEU_LUOT:
        return "khong_du", sl
    sl["tuyet_doi"] = _tuyet_doi(xet, moc)
    hs_t, hs_n = sl["hs_tinh"], sl["hs_nhip"]
    if (hs_t is not None and hs_t >= NGUONG_CHAM) or (hs_n is not None and hs_n >= HE_SO_NHIP_CHAM) or sl["tuyet_doi"]:
        return "cham_ro", sl
    if (hs_t is not None and hs_t >= NGUONG_NHIEU) or (hs_n is not None and hs_n >= HE_SO_NHIP_NHE):
        return "cham_nhe", sl
    return "khong_cham", sl


def _chieu_cham(sl: dict) -> list[str]:
    """Các chiều mà gui_system chậm (số liệu của `_muc_chay`): "tinh" (tính/bước), "nhip" (nhịp giao diện, gồm cả dấu
    hiệu tuyệt đối)."""
    chieu = []
    if sl.get("hs_tinh") is not None and sl["hs_tinh"] >= NGUONG_NHIEU:
        chieu.append("tinh")
    if (sl.get("hs_nhip") is not None and sl["hs_nhip"] >= HE_SO_NHIP_NHE) or sl.get("tuyet_doi"):
        chieu.append("nhip")
    return chieu


def _cham_theo_chieu(xet: list[dict], moc: list[dict], chieu: str) -> bool | None:
    """Một nhóm có chậm theo chiều `chieu` ("tinh" | "nhip") so với mốc không; None khi không đủ lượt để nói."""
    if len(xet) < TOI_THIEU_LUOT or len(moc) < TOI_THIEU_LUOT:
        return None
    if chieu == "tinh":
        hs = _he_so_chay(xet, moc, "tinh_moi_buoc_p50_us")
        return None if hs is None else hs >= NGUONG_NHIEU
    hs = _he_so_chay(xet, moc, "nhip_gd_p95_ms")
    return bool((hs is not None and hs >= HE_SO_NHIP_NHE) or _tuyet_doi(xet, moc))


def _mo_ta_nhom(ten: str, xet: list[dict], moc: list[dict], chieu: str) -> str:
    if chieu == "tinh":
        so = f"tính/bước hệ số {_so(_he_so_chay(xet, moc, 'tinh_moi_buoc_p50_us'))}"
    else:
        so = (f"nhịp p95 hệ số {_so(_he_so_chay(xet, moc, 'nhip_gd_p95_ms'))}, khoảng ĐK lớn nhất "
              f"{_so(_lon_nhat(xet, 'khoang_dk_max_ms'), 0)} ms")
    return f"{ten} {so}, {len(xet)} lượt hợp lệ"


def _nguyen_nhan_chieu(chieu: str, nhanh: str, tt: str, hop_le: list[dict], moc_he_thong: list[dict]) -> str:
    """Vì sao gui_system chậm theo chiều `chieu` ở trạng thái `tt`: so gui_off và gui_off_dh cùng trạng thái với mốc
    "thường" của chính biến thể đó (ít lượt quá thì mốc gui_system/thuong)."""
    def nhom(bien_the: str) -> tuple[bool | None, str]:
        xet = _nhom_chay(hop_le, nhanh, bien_the, tt)
        moc = _nhom_chay(hop_le, nhanh, bien_the, "thuong")
        moc = moc if len(moc) >= TOI_THIEU_LUOT else moc_he_thong
        return _cham_theo_chieu(xet, moc, chieu), _mo_ta_nhom(bien_the, xet, moc, chieu)

    (c_off, so_off), (c_dh, so_dh) = nhom("gui_off"), nhom("gui_off_dh")
    if c_off is False:
        return f"Windows hạ tốc tiến trình (tắt EcoQoS thì hết: {so_off})"
    if c_dh is False and c_off:
        return (f"do Windows bỏ qua độ phân giải đồng hồ khi cửa sổ ẩn (tắt EcoQoS chưa đủ; luôn tôn trọng độ phân giải "
                f"đồng hồ thì hết: {so_off}; {so_dh})")
    if c_dh is False:
        return (f"tắt EcoQoS và luôn tôn trọng độ phân giải đồng hồ thì hết ({so_dh}); chưa đủ lượt gui_off hợp lệ để "
                f"tách hai nguyên nhân ({so_off})")
    if c_off and c_dh:
        return (f"không phải (chỉ) do EcoQoS: tắt EcoQoS vẫn chậm ({so_off}), luôn tôn trọng độ phân giải đồng hồ cũng "
                f"vẫn chậm ({so_dh})")
    if c_off:
        return (f"không phải (chỉ) do EcoQoS: tắt EcoQoS vẫn chậm ({so_off}); chưa đo gui_off_dh (đo lại với "
                f"--bien-the gui_off,gui_off_dh)")
    if c_dh:
        return (f"không phải (chỉ) do EcoQoS hay độ phân giải đồng hồ: gui_off_dh vẫn chậm ({so_dh}); chưa đủ lượt "
                f"gui_off hợp lệ ({so_off})")
    return f"chưa đủ lượt gui_off hợp lệ để tách ({so_off}; cần ≥ {TOI_THIEU_LUOT} lượt mỗi bên)"


def _dong_so_lieu(muc: str, sl: dict, xet: list[dict], moc: list[dict]) -> str:
    phan = []
    if sl.get("hs_tinh") is not None:
        phan.append(f"tính/bước hệ số {_so(sl['hs_tinh'])}")
    if sl.get("hs_nhip") is not None:
        phan.append(f"nhịp giao diện p95 hệ số {_so(sl['hs_nhip'])}")
    if sl.get("dk_max_ms") is not None:
        phan.append(f"khoảng ĐK lớn nhất {_so(sl['dk_max_ms'], 0)} ms")
    if sl.get("tren_han"):
        phan.append(f"{sl['tren_han']} khoảng ĐK > {_so(HAN_LENH_S)} s")
    if sl.get("mat_chan_s"):
        phan.append(f"mất {_so(sl['mat_chan_s'])} s phiên do chặn {_so(CHAN_REAL_DT_S, 1)} s")
    phan.append(f"{_dem_xong(xet)} lượt hợp lệ")
    phan.append(f"mốc {_dem_xong(moc)}" + (f"; cần ≥ {TOI_THIEU_LUOT} lượt mỗi bên" if muc == "khong_du" else ""))
    return "; ".join(phan)


def _theo_trang_thai(hop_le: list[dict], khoa: str, gop: Callable[[list[float]], float | None],
                     n: int = 2) -> str:
    """"thường a, thu nhỏ b, bị che c" của gui_system (mọi nhánh), giá trị gộp bằng `gop`."""
    phan = []
    for tt in TRANG_THAI:
        xs = [d[khoa] for d in hop_le if d.get("bien_the") == "gui_system" and d.get("trang_thai") == tt
              and d.get(khoa) is not None]
        phan.append(f"{_TEN_TRANG_THAI[tt]} {_so(gop(xs), n) if xs else '–'}")
    return ", ".join(phan)


def _ket_luan_chay(dong: list[dict], hop_le: list[dict], dem_loai: Counter, nhanh: list[str]) -> list[str]:
    loai_chu = ", ".join(f"{k} {dem_loai[k]}" for k in LY_DO if dem_loai.get(k)) or "không có"
    moc_theo = {nh: _nhom_chay(hop_le, nh, "gui_system", "thuong") for nh in nhanh}
    if not any(moc_theo.values()):
        ra = [f"KẾT LUẬN: KHÔNG KẾT LUẬN về thu nhỏ/bị che: không có lượt gui_system/thuong hợp lệ làm mốc 'cửa sổ "
              f"đang hiện' (lượt bị loại: {loai_chu})."]
        if eg._co_khoa(dong):
            ra.append(GIAI_THICH_KHOA)
        return ra
    ra = [f"Kết luận (chỉ lượt hợp lệ; ngưỡng mô tả, không phải ngưỡng nghiệm thu; mốc = gui_system/thuong cùng nhánh; "
          f"tính/bước hệ số ≥ {_so(NGUONG_CHAM)} hoặc nhịp giao diện p95 hệ số ≥ {_so(HE_SO_NHIP_CHAM, 1)}, "
          f"hoặc có lượt mất > {_so(MAT_DANG_KE_S)} s phiên do chặn {_so(CHAN_REAL_DT_S, 1)} s / khoảng điều khiển > "
          f"{_so(HAN_LENH_S)} s / KHONG_XONG mà mốc không có, là chậm rõ; tính/bước ≥ {_so(NGUONG_NHIEU)} hoặc nhịp p95 "
          f"≥ {_so(HE_SO_NHIP_NHE, 1)} là có thể chậm nhẹ; mỗi phép so cần ≥ {TOI_THIEU_LUOT} lượt hợp lệ mỗi bên):"]
    for nh in nhanh:
        moc = moc_theo[nh]
        if not moc:
            ra.append(f"- {nh}: KHÔNG KẾT LUẬN (không có lượt gui_system/thuong hợp lệ của nhánh này làm mốc).")
            continue
        for tt in ("thu_nho", "bi_che"):
            xet = _nhom_chay(hop_le, nh, "gui_system", tt)
            muc, sl = _muc_chay(xet, moc)
            dong_tt = f"- {nh}, {tt}: {_NHAN_MUC[muc]} ({_dong_so_lieu(muc, sl, xet, moc)})"
            if muc in ("cham_ro", "cham_nhe"):
                dong_tt += ". Nguyên nhân — " + "; ".join(
                    f"{_TEN_CHIEU[c]}: {_nguyen_nhan_chieu(c, nh, tt, hop_le, moc)}" for c in _chieu_cham(sl))
            ra.append(dong_tt + ".")
    ra.append(f"- Hệ quả (SUY RA): khoảng lớn nhất giữa hai nhịp điều khiển, gui_system: "
              f"{_theo_trang_thai(hop_le, 'khoang_dk_max_ms', max, 0)} ms. N-T10 (ĐỀ XUẤT): hạn COMMAND "
              f"{_so(HAN_LENH_S)} s, watchdog liên lạc {_so(WATCHDOG_LIEN_LAC_S, 1)} s. Nhánh SIM và bo mô phỏng không "
              f"theo đồng hồ tường nên lần chạy vẫn đúng; với bo theo đồng hồ tường (bo thật, bo ảo QEMU) khoảng > "
              f"{_so(HAN_LENH_S)} s làm lệnh hết hạn (bo về ARMED, COMMAND_TIMEOUT), > "
              f"{_so(WATCHDOG_LIEN_LAC_S, 1)} s bo về DISARMED: SUY RA, CHƯA ĐO với bo theo đồng hồ tường.")
    troi = _trung_vi(d.get("troi_lam_tron_pct") for d in hop_le)
    ra.append(f"- Thời gian phiên / đồng hồ thật × rt (trung vị, gui_system): "
              f"{_theo_trang_thai(hop_le, 'ty_le_phien', _trung_vi, 3)}; "
              f"trôi do làm tròn ms của QElapsedTimer ≈ {_so(troi, 2)} % (trung vị mọi lượt hợp lệ); mất do chặn "
              f"{_so(CHAN_REAL_DT_S, 1)} s (lớn nhất, giây phiên): {_theo_trang_thai(hop_le, 'mat_chan_s', max, 2)}.")
    ra += _dong_xac_dinh(dong)
    lag = sum(d.get("lagging_nhip") or 0 for d in hop_le)
    ra.append(f"- lagging: {lag} nhịp (qua giao diện real_dt bị chặn {_so(CHAN_REAL_DT_S, 1)} s nên nhánh SIM và bo mô "
              f"phỏng không bật được cờ này; xem cột mất do chặn).")
    ra.append(f"- Chỉ báo (không phải phép đo trực tiếp), gui_system: phần CPU bận thêm rơi vào lõi E (nhiễu khi tải "
              f"nhẹ): {_theo_trang_thai(_phan_tram(hop_le), 'ty_le_e_pct', _trung_vi, 0)} %; độ phân giải đồng hồ hệ "
              f"thống lúc bấm (toàn máy, chỉ báo): {_theo_trang_thai(hop_le, 'phan_giai_ms', _trung_vi, 3)} ms; CPU của "
              f"tiến trình / thời gian thật: {_theo_trang_thai(hop_le, 'cpu_ty_le', _trung_vi, 2)}.")
    if eg._co_khoa(dong):
        ra.append(f"- Có lượt bị loại vì phiên khóa / ngắt kết nối / màn hình tắt. {GIAI_THICH_KHOA}")
    return ra


def _phan_tram(ds: list[dict]) -> list[dict]:
    return [d | {"ty_le_e_pct": None if d.get("ty_le_e") is None else 100.0 * d["ty_le_e"]} for d in ds]


def _dong_xac_dinh(dong: list[dict]) -> list[str]:
    co = [d for d in dong if d.get("cung_ket_qua_moc") is not None]
    if not co:
        return ["- Kết quả giống lượt khởi động cùng tiến trình: không có lượt nào so được (thiếu mốc, công cụ dừng xe "
                "hoặc đã lập lại đường)."]
    khac = [d for d in co if d.get("cung_ket_qua_moc") is False]
    ra = [f"- Kết quả giống lượt khởi động cùng tiến trình: {len(co) - len(khac)}/{len(co)} (SIM và bo mô phỏng chạy "
          f"bước cố định nên phải giống; khác là có phụ thuộc đồng hồ thật, cần xem)."]
    if khac:
        lech = max((d.get("lech_moc") or 0.0) for d in khac)
        ra.append(f"CẢNH BÁO: {len(khac)} lượt cho kết quả khác lượt khởi động cùng tiến trình (lệch lớn nhất "
                  f"{eg._lech_chu(lech)}): "
                  + ", ".join(f"khối {d.get('khoi')} {d.get('bien_the')} {d.get('nhanh')} lần {d.get('lan')}"
                              for d in khac[:8]))
    return ra


def _bang_chay(dong: list[dict], hop_le: list[dict], nhanh: list[str]) -> list[str]:
    ra = [f"Bảng (chỉ lượt hợp lệ; GD = khoảng giữa hai nhịp giao diện, ms: trung vị các lượt của p50 / p95, lớn nhất "
          f"của max; tính/bước = µs tính mỗi bước 5 ms, trung vị; ĐK = nhịp điều khiển 50 Hz: khoảng lớn nhất ms, số "
          f"khoảng > {_so(HAN_LENH_S)} s, trễ p95 ms so với lịch lý tưởng; phiên/thật = thời gian phiên / (thời gian "
          f"thật × rt), trung vị; mất chặn = giây phiên mất do chặn real_dt {_so(CHAN_REAL_DT_S, 1)} s, lớn nhất; "
          f"lagging = tổng số nhịp):",
          f"{'nhánh':<11}{'biến thể':<12}{'trạng thái':<11}{'hợp lệ':>7}  {'kết quả':<24}{'GD p50/p95/max':<18}"
          f"{'tính/bước':>10}{'ĐK max':>8}{'>0,15s':>8}{'trễ p95':>9}{'phiên/thật':>11}{'mất chặn':>10}{'lagging':>8}"]
    for nh in nhanh:
        for bt in BIEN_THE_CHAY:
            for tt in TRANG_THAI:
                tat_ca = _nhom_chay(dong, nh, bt, tt)
                if not tat_ca:
                    continue
                hl = _nhom_chay(hop_le, nh, bt, tt)
                kq = ", ".join(f"{k} {v}" for k, v in Counter(str(d.get("ket_qua")) for d in hl).most_common()) or "–"
                gd = (f"{_so(_trung_vi(d.get('nhip_gd_p50_ms') for d in hl), 1)}/"
                      f"{_so(_trung_vi(d.get('nhip_gd_p95_ms') for d in hl), 1)}/"
                      f"{_so(_lon_nhat(hl, 'nhip_gd_max_ms'), 0)}")
                tren_han = sum(d.get("khoang_dk_tren_han") or 0 for d in hl) if hl else None
                lag = sum(d.get("lagging_nhip") or 0 for d in hl) if hl else None
                ra.append(f"{nh:<11}{bt:<12}{tt:<11}{f'{len(hl)}/{len(tat_ca)}':>7}  {kq:<24}{gd:<18}"
                          f"{_so(_trung_vi(d.get('tinh_moi_buoc_p50_us') for d in hl), 1):>10}"
                          f"{_so(_lon_nhat(hl, 'khoang_dk_max_ms'), 0):>8}{'–' if tren_han is None else tren_han:>8}"
                          f"{_so(_trung_vi(d.get('tre_dk_p95_ms') for d in hl), 0):>9}"
                          f"{_so(_trung_vi(d.get('ty_le_phien') for d in hl), 3):>11}"
                          f"{_so(_lon_nhat(hl, 'mat_chan_s'), 2):>10}{'–' if lag is None else lag:>8}")
    return ra


def _dong_ecoqos_khoi(khoi_tt: list[dict]) -> str:
    if not khoi_tt:
        return "EcoQoS từng khối: không có thông tin (may.json thiếu khoi_tien_trinh)"
    nhom: dict[str, Counter] = {}
    for k in khoi_tt:
        dt = k.get("dieu_tiet") or {}
        khoa = (dt.get("ecoqos") or k.get("ecoqos_san_sang") or "khong_doc_duoc", dt.get("dong_ho") or "khong_doc_duoc",
                k.get("cach_tat"))
        nhom.setdefault(str(k.get("bien_the")), Counter())[khoa] += 1
    phan = []
    for bt, dem in nhom.items():
        chu = ", ".join(f"ecoqos {e}, đồng hồ {d}" + (f", cách tắt {c}" if c else "") + (f" ×{n}" if n > 1 else "")
                        for (e, d, c), n in dem.items())
        phan.append(f"{bt}: {chu}" + (" (AUTOPARK_KEEP_ECOQOS=1)" if bt == "gui_system" else ""))
    return "EcoQoS từng khối (đọc lại sau khi đặt biến thể): " + "; ".join(phan)


def _phan_dau_chay(dong: list[dict], may: dict, nhanh: list[str]) -> list[str]:
    rt = may.get("rt") if may.get("rt") is not None else next((d["rt"] for d in dong if d.get("rt") is not None), None)
    nhip = may.get("nhip_ms")
    nhanh_chu = ", ".join(n + (" (bo mô phỏng)" if n == "VEHICLE_IO" else "") for n in nhanh) or "?"
    ra = [
        f"Đo vòng điều khiển của ứng dụng giao diện khi chạy (python -m {MODULE} do-chay)",
        f"Kịch bản: {may.get('kich_ban', '?')}" + (f" (ca {may['ca']})" if may.get("ca") else "")
        + f" (lệch sau khi lưu và nạp lại: {eg._lech_chu(may.get('kich_ban_lech'))}); nhánh: {nhanh_chu}; hệ số thời "
          f"gian {_so(rt, 1) if rt is not None else '?'}; nhịp QTimer {nhip if nhip is not None else '?'} ms; chặn "
          f"real_dt {_so(CHAN_REAL_DT_S, 1)} s",
        f"Thời gian: {may.get('bat_dau', '?')} → {may.get('ket_thuc', '?')}"
        + (f"; DỪNG GIỮA CHỪNG: {may['dung_giua_chung']}" if may.get("dung_giua_chung") else ""),
    ] + eg._dong_may_chung(dong, may) + [_dong_ecoqos_khoi(may.get("khoi_tien_trinh") or [])]
    if may.get("kich_ban_lech"):
        ra.append(f"CẢNH BÁO: kịch bản lệch {eg._lech_chu(may['kich_ban_lech'])} sau khi lưu và nạp lại.")
    dau = may.get("trang_thai_may_dau") or {}
    if dau and not dau.get("nhin_thay_duoc", True):
        ra.append(f"CẢNH BÁO: lúc bắt đầu phiên={dau.get('phien')}, kết nối={dau.get('ket_noi')}, màn hình="
                  f"{dau.get('man_hinh')}.")
    return ra + _canh_bao_thieu_luot(dong, may)


def _canh_bao_thieu_luot(dong: list[dict], may: dict) -> list[str]:
    """Dòng CẢNH BÁO khi lịch đo không đi hết (thêm 02/10/2026): mỗi lần chạy không dừng được (ghi chú
    `khong_dung_duoc`; khối của nó bị bỏ dở, số lượt bỏ lấy từ `may["khoi_bo_do"]` khi có) và số dòng ít hơn số lượt dự
    kiến (`so_lan_du_kien`). Lượt khởi động (lần 0) không dừng được bị loại với lý do `khoi_dong`, nên dòng này là chỗ
    duy nhất của tom_tat.txt nói ra nó."""
    ra: list[str] = []
    bo_do = [k for k in may.get("khoi_bo_do") or [] if isinstance(k, dict)]
    luot_bo = {(k.get("khoi"), k.get("bien_the"), k.get("nhanh"), k.get("lan")): k.get("luot_bo") for k in bo_do}
    ket = [d for d in dong if "khong_dung_duoc" in str(d.get("ghi_chu") or "")]
    if ket:
        phan = []
        for d in ket:
            bo = luot_bo.get((d.get("khoi"), d.get("bien_the"), d.get("nhanh"), d.get("lan")))
            phan.append(f"khối {d.get('khoi')} {d.get('bien_the')} {d.get('nhanh')} lần {d.get('lan')} "
                        f"{d.get('trang_thai')}" + (f" (bỏ {bo} lượt còn lại của khối)" if bo is not None else ""))
        ra.append(f"CẢNH BÁO: {len(ket)} lần chạy không dừng được (không có kết quả cả sau khi bấm Dừng; phần còn lại "
                  f"của khối bị bỏ, không có dòng): " + "; ".join(phan) + ".")
    du_kien = may.get("so_lan_du_kien")
    if isinstance(du_kien, int) and not isinstance(du_kien, bool) and len(dong) < du_kien:
        thieu = du_kien - len(dong)
        bo = sum(k.get("luot_bo") or 0 for k in bo_do)
        ly_do = []
        if bo:
            ly_do.append(f"{bo} lượt của khối bị bỏ dở")
        if may.get("dung_giua_chung") and thieu > bo:
            ly_do.append(f"{thieu - bo} lượt sau khi dừng giữa chừng")
        ra.append(f"CẢNH BÁO: chỉ {len(dong)}/{du_kien} lượt dự kiến có dòng"
                  + (f" ({'; '.join(ly_do)})" if ly_do else "") + ".")
    return ra


def tom_tat_chay(dong: list[dict], may: dict) -> str:
    """Nội dung tom_tat.txt của chế độ chạy từ các dòng ket_qua.jsonl và may.json. Hàm thuần: không đọc máy, không đọc
    tệp."""
    hop_le = [d for d in dong if eg.ly_do_loai(d) is None]
    dem_loai = Counter(ly for ly in map(eg.ly_do_loai, dong) if ly)
    nhanh = _ds_nhanh(dong, may)
    ra = _phan_dau_chay(dong, may, nhanh) + [""]
    if not dong:
        return "\n".join(ra + ["Chưa có lần đo nào."]) + "\n"
    ra += _bang_chay(dong, hop_le, nhanh) + [""]
    ra.append("Lượt bị loại khỏi phép so sánh: "
              + (", ".join(f"{k} {dem_loai[k]}" for k in LY_DO if dem_loai.get(k)) or "không có"))
    ra += eg._chuyen_cua_so(dong)
    mau_n, mau_sai = sum(d.get("mau_n") or 0 for d in dong), sum(d.get("mau_sai") or 0 for d in dong)
    ra.append(f"Mẫu trạng thái cửa sổ trong lúc chạy (mỗi giây): {mau_n} mẫu, {mau_sai} sai ở "
              f"{sum((d.get('mau_sai') or 0) > 0 for d in dong)} lượt (lượt có mẫu sai bị loại: "
              f"doi_trang_thai_trong_chay).")
    ra.append("")
    ra += _ket_luan_chay(dong, hop_le, dem_loai, nhanh)
    return "\n".join(ra) + "\n"
