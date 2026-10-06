"""Công cụ đo EcoQoS của ứng dụng giao diện (thêm 02/10/2026, `autopark/evaluation/ecoqos_gui.py`).

Test không mở cửa sổ thật nào: Qt chạy offscreen, cửa sổ / màn che / tiến trình con trong `do_mot_lan` là đồ giả; hai
test tiến trình con chạy `con` với Qt offscreen. Không cổng COM, không camera. Không mang dấu `planner_budget`. Lượt đo
thật chạy bằng tay: docs/CHUYEN_MAY_BAN.md (mục đo EcoQoS của giao diện)."""
import json
import math
import os
import subprocess
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from autopark.evaluation import ecoqos_gui as eg  # noqa: E402
from autopark.evaluation.ecoqos_gui import ChupCpu, NguCanhDo, TrangThaiMay  # noqa: E402

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="đọc trạng thái Windows")


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _env_offscreen() -> dict:
    env, _ = eg.moi_truong_con()
    env["QT_QPA_PLATFORM"] = "offscreen"
    return env


# ------------------------------------------------------------------------------------------------- phép tính CPU

def _chup(t: float, ban_s: list[float], idle_s: list[float] | None = None) -> ChupCpu:
    """Lần chụp giả: CPU i đã bận ban_s[i] giây (kernel gồm cả idle, user 0); toàn máy = tổng."""
    idle_s = idle_s or [0.0] * len(ban_s)
    tung = tuple((int(i * 1e7), int((b + i) * 1e7), 0) for b, i in zip(ban_s, idle_s))
    he_thong = tuple(sum(c[k] for c in tung) for k in range(3))
    return ChupCpu(t, he_thong, tung)


def test_tai_va_ban_ron_theo_lop_tinh_tu_hai_lan_chup():
    a = ChupCpu(0.0, (1000, 2000, 500), ((0, 0, 0), (0, 0, 0), (0, 0, 0), (5_000_000, 9_000_000, 1_000_000)))
    b = ChupCpu(1.0, (1075, 2090, 510),
                ((5_000_000, 10_000_000, 10_000_000),          # bận 1,0 + 1,0 − 0,5 = 1,5 s
                 (20_000_000, 15_000_000, 5_000_000),          # luồng SMT bị đỗ: Δkernel + Δuser = Δidle → 0
                 (0, 2_000_000, 0),                            # 0,2 s
                 (6_000_000, 8_000_000, 1_000_000)))           # bộ đếm lùi: không bao giờ âm
    assert eg.tai_pct(a, b) == pytest.approx(25.0)             # idle 75 / (kernel + user) 100
    assert eg.ban_ron_lop(a, b, {1: [0, 1], 0: [2, 3]}) == pytest.approx({1: 1.5, 0: 0.2})
    assert eg.tai_pct(a, ChupCpu(2.0, None, None)) is None
    assert eg.ban_ron_lop(a, ChupCpu(2.0, (0, 0, 0), None), {1: [0]}) is None


def test_ty_le_loi_e_tru_phan_nen():
    lop = {1: [0, 1], 0: [2, 3]}                               # lớp 0 thấp nhất = lõi E
    c_nen = _chup(0.0, [0.0, 0.0, 0.0, 0.0])
    c0 = _chup(2.0, [0.1, 0.1, 0.5, 0.5])                      # nền: lớp 1 0,1 s/s, lớp 0 0,5 s/s
    # 4 s lập đường: nền chiếm lớp 1 0,4 s, lớp 0 2 s; thêm 4 s trên lớp 0
    c1 = _chup(6.0, [0.3, 0.3, 0.5 + 1.0 + 2.0, 0.5 + 1.0 + 2.0])
    them = eg.ban_ron_them(c_nen, c0, c1, lop)
    assert them == pytest.approx({1: 0.0, 0: 4.0}, abs=1e-6)
    assert eg.ty_le_e(them, 4.0) == pytest.approx(1.0)
    c1_p = _chup(6.0, [0.3 + 2.0, 0.3 + 2.0, 1.5, 1.5])        # 4 s thêm trên lớp 1 (lõi P), lớp 0 chỉ có nền
    assert eg.ty_le_e(eg.ban_ron_them(c_nen, c0, c1_p, lop), 4.0) == pytest.approx(0.0, abs=1e-6)
    c1_it = _chup(6.0, [0.3 + 0.5, 0.3, 1.5, 1.5])             # chỉ 0,5 s thêm < 0,3 × 4 s
    assert eg.ty_le_e(eg.ban_ron_them(c_nen, c0, c1_it, lop), 4.0) is None
    assert eg.ty_le_e(eg.ban_ron_them(c_nen, c0, c1, {0: [0, 1, 2, 3]}), 4.0) is None     # một lớp
    assert eg.ty_le_e(None, 4.0) is None


def test_thu_tu_do_xoay_vong_va_luot_khoi_dong():
    k0 = eg.thu_tu_do(eg.TRANG_THAI, 2, 0, "gui_system")
    k1 = eg.thu_tu_do(eg.TRANG_THAI, 2, 1, "gui_off")
    for ds in (k0, k1):
        assert ds[0] == (0, "thuong")                           # lượt khởi động, bị loại khi so sánh
        assert [lan for lan, _ in ds] == list(range(7))
        assert all(sum(tt == x for _, tt in ds[1:]) == 2 for x in eg.TRANG_THAI)
    assert [tt for _, tt in k0[1:]] != [tt for _, tt in k1[1:]]
    assert [tt for _, tt in k1[1:4]] == ["thu_nho", "bi_che", "thuong"]
    assert eg.thu_tu_do(eg.TRANG_THAI, 2, 0, "khong_cua_so") == [(i, "khong_cua_so") for i in range(7)]


# --------------------------------------------------------------------------------------------------------- tóm tắt

_MAY = {
    "ca": "uturn_w46", "han_lap_duong_s": 8.0, "bat_dau": "02/10/2026 09:00:00", "ket_thuc": "02/10/2026 09:08:00",
    "git": {"commit": "abc1234", "so_tep_chua_commit": 0},
    "cpu": {"logic": 32, "lop": {"1": list(range(16)), "0": list(range(16, 32))}},
    "nguon": {"ke_hoach": {"guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", "ten": "High performance"}},
    "lenh": "python -X utf8 -m autopark.evaluation.ecoqos_gui do --ra x",
}


def _dong(bien_the: str, trang_thai: str, tg: float, ket_qua: str = "OK", lan: int = 1, **ghi_de) -> dict:
    """Một dòng hợp lệ (đủ khóa COT), đổi bằng `ghi_de`."""
    d = dict.fromkeys(eg.COT)
    d.update(thoi_diem="09:00:00", khoi=0, bien_the=bien_the, pid=100, lan=lan, khoi_dong=(lan == 0),
             trang_thai=trang_thai, ecoqos="off" if bien_the == "gui_off" else "system", uu_tien="normal",
             phien="mo", ket_noi="active", ban_lam_viec="Default", man_hinh="bat", vang_s=100.0, phien_sau="mo",
             man_hinh_sau="bat", vang_s_sau=110.0, ket_qua=ket_qua, tg_tinh_s=tg, tg_giao_dien_s=tg + 0.01,
             tre_poll_s=0.01, tai_nen_pct=2.0, ghi_chu="", thong_diep="")
    if bien_the != "khong_cua_so":
        d.update(cua_so_truoc="giao_dien" if trang_thai == "thuong" else "khac:Code.exe",
                 gui_thu_nho=trang_thai == "thu_nho", gui_hien=trang_thai != "thu_nho",
                 gui_lo_ra=1.0 if trang_thai == "thuong" else (0.0 if trang_thai == "bi_che" else None),
                 che_kin=True if trang_thai == "bi_che" else None)
    d.update(ghi_de)
    return d


def _ba(bien_the: str, trang_thai: str, tg: float, ket_qua: str = "OK") -> list[dict]:
    return [_dong(bien_the, trang_thai, tg + 0.01 * i, ket_qua, lan=i + 1) for i in range(3)]


def _dong_ket_luan(van_ban: str, dau: str) -> str:
    return next(d for d in van_ban.splitlines() if d.startswith(dau))


def test_tom_tat_khong_ket_luan_khi_phien_khoa():
    dong = [r | {"phien": "khoa", "phien_sau": "khoa", "ban_lam_viec": ""}
            for bt in ("gui_system", "gui_off") for tt in eg.TRANG_THAI for r in _ba(bt, tt, 3.6)]
    dong += [r | {"phien": "khoa", "phien_sau": "khoa"} for r in _ba("khong_cua_so", "khong_cua_so", 3.6)]
    van_ban = eg.tom_tat(dong, _MAY)
    assert "KHÔNG KẾT LUẬN" in van_ban
    assert eg.GIAI_THICH_KHOA in van_ban
    assert "chậm rõ" not in van_ban
    assert f"phien_khoa {len(dong)}" in van_ban
    assert {eg.ly_do_loai(d) for d in dong} == {"phien_khoa"}


def test_tom_tat_cham_ro_khi_thu_nho_va_het_khi_tat_ecoqos():
    dong = (_ba("gui_system", "thuong", 3.6) + _ba("gui_system", "thu_nho", 8.0, "TIMEOUT")
            + [r for tt in eg.TRANG_THAI for r in _ba("gui_off", tt, 3.6)]
            + _ba("khong_cua_so", "khong_cua_so", 8.0, "TRACKING_FAILED"))
    van_ban = eg.tom_tat(dong, _MAY)
    thu_nho = _dong_ket_luan(van_ban, "- thu_nho:")
    assert "chậm rõ (hệ số 2,22; OK 0/3 lượt hợp lệ; mốc OK 3/3)" in thu_nho      # dòng kết luận ghi số lượt
    assert "Windows hạ tốc tiến trình (tắt EcoQoS cho tiến trình thì hết" in thu_nho
    assert "không đủ lượt hợp lệ để so (0 lượt hợp lệ" in _dong_ket_luan(van_ban, "- bi_che:")
    assert "CÓ hạ tốc tiến trình không cửa sổ" in van_ban
    assert "KHÔNG KẾT LUẬN" not in van_ban


def test_tom_tat_canh_bao_khi_khong_tien_trinh_nao_bi_ha():
    dong = [r for bt in ("gui_system", "gui_off") for tt in eg.TRANG_THAI for r in _ba(bt, tt, 3.6)]
    dong += _ba("khong_cua_so", "khong_cua_so", 3.61)
    van_ban = eg.tom_tat(dong, _MAY)
    assert "không thấy chậm" in _dong_ket_luan(van_ban, "- thu_nho:")
    assert "không thấy chậm" in _dong_ket_luan(van_ban, "- bi_che:")
    boi_canh = _dong_ket_luan(van_ban, "- Bối cảnh:")
    assert "KHÔNG hạ tốc cả tiến trình không cửa sổ" in boi_canh
    assert "không chứng minh giao diện an toàn" in boi_canh and "High performance" in boi_canh


def _nguyen_nhan_thu_nho(he_thong: list[dict], off: list[dict]) -> str:
    """Dòng kết luận "- thu_nho:" khi gui_system/thu_nho là `he_thong`, gui_off/thu_nho là `off` (mốc 3,61 s)."""
    dong = (_ba("gui_system", "thuong", 3.6) + he_thong + _ba("gui_off", "thuong", 3.6) + off
            + _ba("khong_cua_so", "khong_cua_so", 3.6))
    return _dong_ket_luan(eg.tom_tat(dong, _MAY), "- thu_nho:")


def _hong(bien_the: str, tg: float, ket_qua: str = "TIMEOUT") -> dict:
    return _dong(bien_the, "thu_nho", tg, ket_qua, lan=9)


@pytest.mark.parametrize("he_thong, off, mong", [
    # tắt EcoQoS bớt phần lớn (2,00 → 1,19): không được ghi "không phải do EcoQoS"
    (_ba("gui_system", "thu_nho", 7.2), _ba("gui_off", "thu_nho", 4.29), "một phần do EcoQoS"),
    # gui_off không chậm (hệ số 1,00), chỉ một lượt hỏng nhanh 3,5 s: vẫn là "tắt EcoQoS thì hết", có ghi OK 3/4
    (_ba("gui_system", "thu_nho", 8.0, "TIMEOUT"),
     _ba("gui_off", "thu_nho", 3.6) + [_hong("gui_off", 3.5, "TRACKING_FAILED")],
     "Windows hạ tốc tiến trình (tắt EcoQoS cho tiến trình thì hết: gui_off hệ số 1,00, OK 3/4 lượt hợp lệ)"),
    (_ba("gui_system", "thu_nho", 7.2), _ba("gui_off", "thu_nho", 7.2), "không phải do EcoQoS (tắt EcoQoS vẫn chậm"),
    # 1,31 so với 1,29: tắt EcoQoS gần như không đổi gì, không được kể là do EcoQoS
    (_ba("gui_system", "thu_nho", 4.72), _ba("gui_off", "thu_nho", 4.65), "không tách được (tắt EcoQoS không nhanh"),
    # "chậm rõ" chỉ vì một lượt hỏng (hệ số 1,00): so lượt hỏng của gui_off
    (_ba("gui_system", "thu_nho", 3.6) + [_hong("gui_system", 8.0)], _ba("gui_off", "thu_nho", 3.6),
     "có thể do EcoQoS (tắt EcoQoS thì không còn lượt không OK"),
    (_ba("gui_system", "thu_nho", 3.6) + [_hong("gui_system", 8.0)],
     _ba("gui_off", "thu_nho", 3.6) + [_hong("gui_off", 8.0)], "không tách được (tắt EcoQoS vẫn có lượt không OK"),
], ids=["tat_ecoqos_bot_phan_lon", "gui_off_mot_luot_hong_nhanh", "tat_ecoqos_van_cham", "chenh_it",
        "chi_vi_luot_hong_gui_off_sach", "chi_vi_luot_hong_gui_off_cung_hong"])
def test_tom_tat_nguyen_nhan_xet_he_so_chu_khong_mot_luot_hong(he_thong, off, mong):
    dong = _nguyen_nhan_thu_nho(he_thong, off)
    assert "chậm rõ" in dong and f"Nguyên nhân: {mong}" in dong, dong


def test_tom_tat_boi_canh_mot_luot_khong_cua_so_hong_khong_thanh_co_ha_toc():
    """Bối cảnh chỉ theo hệ số: một lượt khong_cua_so hỏng ở hệ số 1,00 không được thành "Windows CÓ hạ tốc" (câu đó
    bỏ mất lời cảnh báo "không chứng minh giao diện an toàn")."""
    dong = [r for bt in ("gui_system", "gui_off") for tt in eg.TRANG_THAI for r in _ba(bt, tt, 3.6)]
    dong += _ba("khong_cua_so", "khong_cua_so", 3.6)
    dong.append(_dong("khong_cua_so", "khong_cua_so", 3.6, "TRACKING_FAILED", lan=9))
    van_ban = eg.tom_tat(dong, _MAY)
    boi_canh = _dong_ket_luan(van_ban, "- Bối cảnh:")
    assert "CÓ hạ tốc" not in boi_canh
    assert "KHÔNG hạ tốc cả tiến trình không cửa sổ" in boi_canh and "OK 3/4 lượt hợp lệ" in boi_canh
    assert "không chứng minh giao diện an toàn" in boi_canh
    assert "không thấy chậm" in _dong_ket_luan(van_ban, "- thu_nho:")


def test_tom_tat_mot_luot_hop_le_khong_du_ket_luan():
    """Một lượt sống sót sau khi loại không đủ để ghi "chậm rõ"; dòng kết luận ghi số lượt hai bên."""
    thuong = [_dong("gui_system", "thuong", 3.6 + 0.01 * i, lan=i + 1) for i in range(4)]
    bi_loai = [_dong("gui_system", "thu_nho", 3.6, lan=10 + i, vang_s=100.0, vang_s_sau=1.0) for i in range(4)]
    mot = [_dong("gui_system", "thu_nho", 7.5, lan=20)]
    van_ban = eg.tom_tat(thuong + bi_loai + mot, _MAY)
    thu_nho = _dong_ket_luan(van_ban, "- thu_nho:")
    assert "chậm" not in thu_nho
    assert "không đủ lượt hợp lệ để so (OK 1/1 lượt hợp lệ; mốc OK 4/4; cần ≥ 2 lượt mỗi bên)" in thu_nho
    assert "không đủ lượt khong_cua_so hợp lệ" in _dong_ket_luan(van_ban, "- Bối cảnh:")
    # hai lượt thì so được, và dòng kết luận vẫn ghi số lượt
    van_ban = eg.tom_tat(thuong + bi_loai + mot + [_dong("gui_system", "thu_nho", 7.5, lan=21)], _MAY)
    thu_nho = _dong_ket_luan(van_ban, "- thu_nho:")
    assert thu_nho.startswith("- thu_nho: chậm rõ (hệ số 2,07; OK 2/2 lượt hợp lệ; mốc OK 4/4)")
    assert "chưa đủ lượt gui_off hợp lệ để tách (gui_off 0 lượt hợp lệ" in thu_nho
    # gui_off chỉ một lượt: cũng chưa tách được
    van_ban = eg.tom_tat(thuong + mot * 2 + _ba("gui_off", "thuong", 3.6) + [_dong("gui_off", "thu_nho", 3.6)], _MAY)
    assert "chưa đủ lượt gui_off hợp lệ để tách (gui_off OK 1/1" in _dong_ket_luan(van_ban, "- thu_nho:")


def test_tom_tat_loai_luot_khoi_dong_tai_cao_va_sai_trang_thai():
    loai = [
        _dong("gui_system", "thuong", 4.5, lan=0),                         # lượt khởi động
        _dong("gui_system", "thuong", 3.6, tai_nen_pct=60.0),
        _dong("gui_system", "thu_nho", 3.6, gui_thu_nho=False),            # đòi thu nhỏ mà cửa sổ không thu nhỏ
        _dong("gui_system", "bi_che", 3.6, che_kin=False),                 # màn che không phủ kín
        _dong("gui_system", "thu_nho", 3.6, vang_s=100.0, vang_s_sau=2.0),  # có người thao tác trong lượt
        # thu nhỏ / bị che kín nhưng giao diện vẫn là cửa sổ ở trước (focus): không phải điều kiện cần đo
        _dong("gui_system", "thu_nho", 3.6, cua_so_truoc="giao_dien"),
        _dong("gui_system", "bi_che", 3.6, cua_so_truoc="giao_dien"),
    ]
    assert [eg.ly_do_loai(d) for d in loai] == ["khoi_dong", "tai_nen_cao", "sai_trang_thai", "sai_trang_thai",
                                                "nguoi_dung_thao_tac", "gui_van_o_truoc", "gui_van_o_truoc"]
    assert eg.ly_do_loai(_dong("gui_system", "thuong", 3.6, ghi_chu="nguoi_dung_thao_tac")) == "nguoi_dung_thao_tac"
    assert eg.ly_do_loai(_dong("gui_system", "thuong", 3.6, gui_lo_ra=0.0)) == "sai_trang_thai"     # bị cửa sổ khác che
    hop_le = _ba("gui_system", "thuong", 3.6) + _ba("gui_system", "thu_nho", 3.6) + _ba("gui_system", "bi_che", 3.6)
    assert all(eg.ly_do_loai(d) is None for d in hop_le)
    assert eg.ly_do_loai(_dong("gui_system", "bi_che", 3.6, cua_so_truoc="man_che")) is None
    van_ban = eg.tom_tat(loai + hop_le, _MAY)
    dong_loai = _dong_ket_luan(van_ban, "Lượt bị loại")
    for chu in ("khoi_dong 1", "tai_nen_cao 1", "sai_trang_thai 2", "nguoi_dung_thao_tac 1", "gui_van_o_truoc 2"):
        assert chu in dong_loai
    assert "3/5" in _dong_ket_luan(van_ban, "gui_system   thuong")          # 3 hợp lệ trên 5 lượt "thường"
    # cột focus in cho mọi trạng thái có cửa sổ (trước đây chỉ "thường")
    assert _dong_ket_luan(van_ban, "gui_system   thuong").endswith("3/3")
    assert _dong_ket_luan(van_ban, "gui_system   thu_nho").endswith("0/3")
    assert _dong_ket_luan(van_ban, "gui_system   bi_che").endswith("0/3")


# ---------------------------------------------------------------------------------------------- một lần đo (đồ giả)

class FakeCon:
    """Tiến trình giao diện giả. `plan` trả lời bằng `tra_loi(yeu_cau)`; `cap_quyen` / `len_truoc` theo bàn làm việc giả
    `ban` (không có thì luôn được)."""

    pid = 4242
    con_song = True

    def __init__(self, nhat_ky: list, tra_loi, ban=None):
        self.nhat_ky, self.tra_loi, self.ban = nhat_ky, tra_loi, ban
        self._tin: dict | None = None

    def gui(self, lenh: str) -> bool:
        self.nhat_ky.append(("con.gui", lenh))
        ten, yeu_cau = eg._tach_lenh(lenh)
        self._tin = None
        if ten == "cap_quyen":
            ok, loi = self.ban.cap_quyen("con") if self.ban else (True, 0)
            self._tin = {"loai": "cap_quyen", "yeu_cau": yeu_cau, "ok": ok, "loi": loi}
        elif ten == "len_truoc":
            ok = self.ban.dat_truoc("con", "giao_dien") if self.ban else True
            self._tin = {"loai": "len_truoc", "yeu_cau": yeu_cau, "ok": ok, "truoc_hwnd": None}
        return True

    def doc(self, het_han, loai, yeu_cau=None):
        self.nhat_ky.append(("con.doc", yeu_cau))
        return self._tin if self._tin is not None else self.tra_loi(yeu_cau)


class FakeCuaSo:
    """Cửa sổ giao diện giả, phía tiến trình điều khiển (`CuaSoWin32`)."""

    hwnd = 777

    def __init__(self, nhat_ky: list, ban=None):
        self.nhat_ky, self.ban = nhat_ky, ban
        self.thu_nho_roi, self.hien = False, True

    def khoi_phuc(self):
        self.nhat_ky.append("gui.khoi_phuc")
        self.thu_nho_roi = False

    def hien_khong_kich_hoat(self):
        self.nhat_ky.append("gui.hien_khong_kich_hoat")
        self.thu_nho_roi = False

    def thu_nho(self):                                  # như lượt đo 02/10/2026: cửa sổ ở trước không đổi
        self.nhat_ky.append("gui.thu_nho")
        self.thu_nho_roi = True

    def len_truoc(self) -> bool:                        # SetForegroundWindow từ tiến trình điều khiển (chạy nền)
        self.nhat_ky.append("gui.len_truoc")
        return self.ban.dat_truoc("dieu_khien", "giao_dien") if self.ban else True

    def dua_len_dau(self):
        self.nhat_ky.append("gui.dua_len_dau")

    def ty_le_lo_ra(self):
        return None if self.thu_nho_roi else 1.0


class FakeManChe:
    """Phía điều khiển giả của tiến trình `che` (màn che + cửa sổ trung tính)."""

    pid = 5151
    ly_do_dong = ""
    hwnd_trung_tinh = 8002

    def __init__(self, nhat_ky: list, ban=None):
        self.nhat_ky, self.ban = nhat_ky, ban
        self.dang_hien = self.trung_tinh_hien = False

    def con_song(self) -> bool:
        return True

    def hien(self, gui) -> bool:
        self.nhat_ky.append("che.hien")
        self.dang_hien = True
        return True

    def hien_trung_tinh(self) -> bool:
        self.nhat_ky.append("che.trung_tinh")
        self.trung_tinh_hien = True
        return True

    def cap_quyen(self) -> dict:
        self.nhat_ky.append("che.cap_quyen")
        ok, loi = self.ban.cap_quyen("che") if self.ban else (True, 0)
        return {"loai": "cap_quyen", "ok": ok, "loi": loi}

    def len_truoc(self, cua_so: str) -> dict:
        self.nhat_ky.append(("che.len_truoc", cua_so))
        ok = self.ban.dat_truoc("che", "man_che" if cua_so == "che" else "trung_tinh") if self.ban else True
        return {"loai": "da_len_truoc", "cua_so": cua_so, "ok": ok, "truoc_hwnd": None}

    def an(self, cua_so=None):
        self.nhat_ky.append("che.an" if cua_so is None else f"che.an:{cua_so}")
        if cua_so in (None, "che"):
            self.dang_hien = False
            if self.ban:
                self.ban.an("man_che")
        if cua_so in (None, "trung_tinh"):
            self.trung_tinh_hien = False
            if self.ban:
                self.ban.an("trung_tinh")

    def kin(self, gui) -> bool:
        return self.dang_hien


CODE = (9090, "Code.exe")                               # (pid, tệp chạy) của một cửa sổ khác giao diện


class BanLamViecGia:
    """Quy tắc cửa sổ ở trước của Windows, rút gọn: AllowSetForegroundWindow chỉ được khi tiến trình gọi đang giữ cửa sổ
    ở trước; SetForegroundWindow chỉ được khi tiến trình gọi đang ở trước, hoặc sau một lần cấp quyền (ở đây quyền dùng
    MỘT lần, chặt hơn Windows); tiến trình điều khiển (chạy nền) không bao giờ ở trước. Ẩn cửa sổ đang ở trước thì một
    ứng dụng khác (Code.exe) lên trước; thu nhỏ giao diện không đổi cửa sổ ở trước (như lượt đo 02/10/2026 02:54).
    `tu_choi`: Windows từ chối mọi lần cấp quyền."""

    TIEN_TRINH = {"giao_dien": "con", "man_che": "che", "trung_tinh": "che"}
    HWND = {"giao_dien": FakeCuaSo.hwnd, "man_che": 8001, "trung_tinh": FakeManChe.hwnd_trung_tinh}

    def __init__(self, truoc: str = "giao_dien", tu_choi: bool = False):
        self.truoc, self.tu_choi, self.duoc_cap = truoc, tu_choi, False

    def cap_quyen(self, tien_trinh: str) -> tuple[bool, int]:
        if self.tu_choi or self.TIEN_TRINH.get(self.truoc) != tien_trinh:
            return False, 5                                     # ERROR_ACCESS_DENIED
        self.duoc_cap = True
        return True, 0

    def dat_truoc(self, tien_trinh: str, cua_so: str) -> bool:
        if self.TIEN_TRINH.get(self.truoc) == tien_trinh:
            self.truoc = cua_so
            return True
        if self.duoc_cap:
            self.truoc, self.duoc_cap = cua_so, False
            return True
        return False

    def an(self, cua_so: str) -> None:
        if self.truoc == cua_so:
            self.truoc = "khac:Code.exe"

    def doc_truoc(self) -> tuple[int, int, str]:
        if self.truoc.startswith("khac:"):
            return CODE[0], 888, self.truoc[5:]
        pid = FakeCon.pid if self.truoc == "giao_dien" else FakeManChe.pid
        return pid, self.HWND[self.truoc], "python.exe"


def _ngu_canh(nhat_ky: list, gui, che, truoc: tuple[int, str] = (FakeCon.pid, "python.exe"),
              ban: BanLamViecGia | None = None) -> NguCanhDo:
    """`truoc`: (pid, tệp chạy) cố định của cửa sổ đang ở trước, mặc định là giao diện (FakeCon.pid); có `ban` thì cửa
    sổ ở trước đọc từ bàn làm việc giả (đổi theo các bước của lượt)."""
    vang = iter([100.0, 107.0] * 4)
    # nền 3 s gần như rảnh (tải ≈ 1,7 %); 4 s lập đường: lõi P (lớp 1) bận 3,8 s, lõi E (lớp 0) 0,1 s
    chup = iter([_chup(0.0, [0.0, 0.0], [0.0, 0.0]), _chup(3.0, [0.1, 0.0], [2.9, 3.0]),
                 _chup(7.0, [3.9, 0.1], [3.1, 6.9])] * 4)
    cpu = iter([10.0, 13.6] * 4)

    def doc_truoc() -> tuple[int, int, str]:
        return ban.doc_truoc() if ban is not None else (truoc[0], 888, truoc[1])

    def doc_may() -> TrangThaiMay:
        pid, hwnd, exe = doc_truoc()
        return TrangThaiMay("mo", "active", "Default", "bat", next(vang), pid, hwnd, exe)

    return NguCanhDo(doc_may=doc_may, doc_truoc=doc_truoc, chup_cpu=lambda: next(chup),
                     ecoqos_cua=lambda pid: "system", uu_tien_cua=lambda pid: "normal", cpu_cua=lambda pid: next(cpu),
                     ngu=lambda s: nhat_ky.append(("ngu", s)), gui=gui, che=che, cho=5.0, khoi=1,
                     bien_the="gui_system", lop_cpu={1: [0], 0: [1]})


def _ket_qua_gia(yeu_cau):
    return {"loai": "ket_qua", "yeu_cau": yeu_cau, "lan": 2, "ket_qua": "OK", "thong_diep": "Tìm được đường",
            "tg_tinh_s": 3.62, "tg_giao_dien_s": 3.64, "tre_poll_s": 0.02, "elapsed_s": 3.6, "cusps": 18, "dai_m": 2.1,
            "nac": [{"nac": "gộp-nhanh", "ket_qua": "OK", "giay": 3.5, "bam": True}]}


def test_do_mot_lan_voi_cua_so_gia():
    nhat_ky: list = []
    gui, che = FakeCuaSo(nhat_ky), FakeManChe(nhat_ky)
    con = FakeCon(nhat_ky, _ket_qua_gia)
    dong = eg.do_mot_lan(con, 3, "thu_nho", _ngu_canh(nhat_ky, gui, che, CODE))
    assert list(dong) == list(eg.COT)
    # cửa sổ trung tính lên trước rồi mới thu nhỏ giao diện; màn che ẩn sau; rồi mới lập đường
    assert (nhat_ky.index("che.trung_tinh") < nhat_ky.index(("che.len_truoc", "trung_tinh"))
            < nhat_ky.index("gui.thu_nho") < nhat_ky.index("che.an:che") < nhat_ky.index(("con.gui", "plan 3")))
    assert ("ngu", 3.0) in nhat_ky and ("ngu", 2.0) in nhat_ky and ("con.doc", "3") in nhat_ky
    assert (dong["trang_thai"], dong["lan"], dong["khoi"], dong["khoi_dong"]) == ("thu_nho", 3, 1, False)
    assert (dong["ket_qua"], dong["tg_tinh_s"], dong["tg_giao_dien_s"], dong["cusps"]) == ("OK", 3.62, 3.64, 18)
    assert (dong["ecoqos"], dong["uu_tien"], dong["phien"], dong["phien_sau"], dong["man_hinh"]) == \
        ("system", "normal", "mo", "mo", "bat")
    assert dong["gui_thu_nho"] is True and dong["che_kin"] is None and dong["cua_so_truoc"] == "khac:Code.exe"
    assert dong["cpu_tien_trinh_s"] == pytest.approx(3.6)
    # nền 0,1 s / 3 s trên lớp 1 → 4 s lập đường: lớp 1 thêm 3,8 − 0,133 s, lớp 0 (lõi E) thêm 0,1 s
    assert dong["tai_nen_pct"] == 1.7 and dong["ban_ron_e_s"] == 0.1 and dong["ban_ron_p_s"] == pytest.approx(3.667)
    assert dong["ty_le_e"] == pytest.approx(0.1 / (0.1 + 3.8 - 0.4 / 3), abs=1e-3)
    # Code.exe ở trước: không tiến trình nào của công cụ cấp quyền được; vẫn là "ứng dụng khác ở trước" nên hợp lệ
    assert dong["cap_quyen_truoc"] == "khong_ai:khac:Code.exe"
    assert dong["ket_qua_dua_ra_truoc"] == "trung_tinh:khong_o_truoc:khac:Code.exe"
    assert eg.ly_do_loai(dong) is None
    # thu nhỏ rồi mà giao diện vẫn là cửa sổ ở trước (gặp ở lượt thử 02/10/2026): lượt bị loại
    dong = eg.do_mot_lan(con, 3, "thu_nho", _ngu_canh([], gui, che))
    assert dong["gui_thu_nho"] is True and dong["cua_so_truoc"] == "giao_dien"
    assert eg.ly_do_loai(dong) == "gui_van_o_truoc"

    nhat_ky.clear()
    dong = eg.do_mot_lan(con, 4, "bi_che", _ngu_canh(nhat_ky, gui, che, (FakeManChe.pid, "python.exe")))
    assert (nhat_ky.index("gui.hien_khong_kich_hoat") < nhat_ky.index("che.hien")
            < nhat_ky.index(("che.len_truoc", "che")) < nhat_ky.index(("con.gui", "plan 4")))
    assert "gui.khoi_phuc" not in nhat_ky                 # bị che: hiện lại giao diện mà không kích hoạt
    assert dong["che_kin"] is True and dong["gui_thu_nho"] is False and dong["cua_so_truoc"] == "man_che"
    assert (dong["cap_quyen_truoc"], dong["ket_qua_dua_ra_truoc"]) == (None, "man_che:ok")
    assert eg.ly_do_loai(dong) is None
    # màn che phủ kín nhưng không lấy được focus: giao diện vẫn ở trước dưới màn che, lượt bị loại
    dong = eg.do_mot_lan(con, 4, "bi_che", _ngu_canh([], gui, che))
    assert dong["che_kin"] is True and eg.ly_do_loai(dong) == "gui_van_o_truoc"

    nhat_ky.clear()
    dong = eg.do_mot_lan(con, 5, "thuong", _ngu_canh(nhat_ky, gui, che))
    assert (nhat_ky.index("gui.khoi_phuc") < nhat_ky.index(("con.gui", "len_truoc t5")) < nhat_ky.index("che.an")
            < nhat_ky.index(("con.gui", "plan 5")))
    assert "gui.dua_len_dau" not in nhat_ky and "gui.len_truoc" not in nhat_ky and dong["gui_lo_ra"] == 1.0
    assert (dong["cap_quyen_truoc"], dong["ket_qua_dua_ra_truoc"]) == (None, "giao_dien:ok")
    assert dong["cua_so_truoc"] == "giao_dien" and eg.ly_do_loai(dong) is None      # "thường": ở trước là đúng

    im_lang = FakeCon([], lambda yeu_cau: None)
    dong = eg.do_mot_lan(im_lang, 6, "thu_nho", _ngu_canh([], gui, che))
    assert dong["ket_qua"] == "KHONG_TRA_LOI" and eg.ly_do_loai(dong) == "khong_tra_loi"

    che.ly_do_dong, che.con_song = "nguoi_dung_dong", lambda: False      # người dùng đã bấm Esc trên màn che
    nhat_ky.clear()
    dong = eg.do_mot_lan(con, 7, "bi_che", _ngu_canh(nhat_ky, gui, che))
    assert dong["ket_qua"] == "BO_QUA" and "nguoi_dung_dong" in dong["ghi_chu"] and eg.ly_do_loai(dong) == "bo_qua"
    assert not any(isinstance(m, tuple) and m[0] == "con.gui" for m in nhat_ky)       # không lập đường
    # thu nhỏ khi tiến trình `che` đã đóng: chỉ thu nhỏ, ghi lại là không có cửa sổ trung tính
    nhat_ky.clear()
    dong = eg.do_mot_lan(con, 8, "thu_nho", _ngu_canh(nhat_ky, gui, che, CODE))
    assert "che.trung_tinh" not in nhat_ky and "gui.thu_nho" in nhat_ky and dong["ket_qua"] == "OK"
    assert dong["ket_qua_dua_ra_truoc"] == "trung_tinh:khong_hien:khac:Code.exe" and dong["cap_quyen_truoc"] is None


def _ba_doi_tuong(ban: BanLamViecGia, nhat_ky: list) -> tuple[FakeCon, FakeCuaSo, FakeManChe]:
    return FakeCon(nhat_ky, _ket_qua_gia, ban), FakeCuaSo(nhat_ky, ban), FakeManChe(nhat_ky, ban)


def test_cap_quyen_roi_cua_so_trung_tinh_va_man_che_len_truoc():
    """Giao diện đang ở trước cấp quyền (ASFW_ANY) → cửa sổ trung tính / màn che lên trước → lượt hợp lệ. Lượt đo
    02/10/2026 02:54 không có bước này: 15/16 lượt thu nhỏ / bị che vẫn có giao diện ở trước."""
    nhat_ky: list = []
    ban = BanLamViecGia("giao_dien")
    con, gui, che = _ba_doi_tuong(ban, nhat_ky)
    dong = eg.do_mot_lan(con, 2, "thu_nho", _ngu_canh(nhat_ky, gui, che, ban=ban))
    assert (dong["cap_quyen_truoc"], dong["ket_qua_dua_ra_truoc"]) == ("giao_dien:ok", "trung_tinh:ok")
    assert dong["cua_so_truoc"] == "trung_tinh" and dong["gui_thu_nho"] is True and eg.ly_do_loai(dong) is None
    # giao diện cấp quyền khi còn ở trước; cửa sổ trung tính lên trước rồi mới thu nhỏ (SW_MINIMIZE không chọn hộ)
    assert (nhat_ky.index(("con.gui", "cap_quyen q2")) < nhat_ky.index(("che.len_truoc", "trung_tinh"))
            < nhat_ky.index("gui.thu_nho") < nhat_ky.index(("con.gui", "plan 2")))
    # thu nhỏ → bị che: màn che cùng tiến trình với cửa sổ trung tính đang ở trước, không cần cấp quyền
    dong = eg.do_mot_lan(con, 3, "bi_che", _ngu_canh(nhat_ky, gui, che, ban=ban))
    assert (dong["cap_quyen_truoc"], dong["ket_qua_dua_ra_truoc"]) == (None, "man_che:ok")
    assert dong["cua_so_truoc"] == "man_che" and dong["che_kin"] is True and dong["gui_thu_nho"] is False
    assert eg.ly_do_loai(dong) is None and not che.trung_tinh_hien
    # bị che → thu nhỏ: cũng cùng tiến trình; màn che ẩn sau khi cửa sổ trung tính đã ở trước
    nhat_ky.clear()
    dong = eg.do_mot_lan(con, 4, "thu_nho", _ngu_canh(nhat_ky, gui, che, ban=ban))
    assert (dong["cap_quyen_truoc"], dong["ket_qua_dua_ra_truoc"], dong["cua_so_truoc"]) == \
        (None, "trung_tinh:ok", "trung_tinh")
    assert nhat_ky.index(("che.len_truoc", "trung_tinh")) < nhat_ky.index("che.an:che")
    assert eg.ly_do_loai(dong) is None and not che.dang_hien
    # thường → bị che: giao diện cấp quyền
    ban = BanLamViecGia("giao_dien")
    con, gui, che = _ba_doi_tuong(ban, nhat_ky)
    dong = eg.do_mot_lan(con, 5, "bi_che", _ngu_canh(nhat_ky, gui, che, ban=ban))
    assert (dong["cap_quyen_truoc"], dong["ket_qua_dua_ra_truoc"], dong["cua_so_truoc"]) == \
        ("giao_dien:ok", "man_che:ok", "man_che")
    assert eg.ly_do_loai(dong) is None


def test_windows_tu_choi_thi_dong_ghi_ly_do_va_bi_loai():
    """Windows từ chối cấp quyền: dòng vẫn được ghi, kèm bước bị từ chối; lý do loại chặn mọi dòng sai trạng thái."""
    nhat_ky: list = []
    ban = BanLamViecGia("giao_dien", tu_choi=True)
    con, gui, che = _ba_doi_tuong(ban, nhat_ky)
    thu_nho = eg.do_mot_lan(con, 2, "thu_nho", _ngu_canh(nhat_ky, gui, che, ban=ban))
    assert thu_nho["cap_quyen_truoc"] == "giao_dien:tu_choi:5"
    assert thu_nho["ket_qua_dua_ra_truoc"] == "trung_tinh:tu_choi:giao_dien"
    assert thu_nho["cua_so_truoc"] == "giao_dien" and eg.ly_do_loai(thu_nho) == "gui_van_o_truoc"
    bi_che = eg.do_mot_lan(con, 3, "bi_che", _ngu_canh(nhat_ky, gui, che, ban=ban))
    assert (bi_che["cap_quyen_truoc"], bi_che["ket_qua_dua_ra_truoc"]) == \
        ("giao_dien:tu_choi:5", "man_che:tu_choi:giao_dien")
    assert bi_che["che_kin"] is True and eg.ly_do_loai(bi_che) == "gui_van_o_truoc"
    # cửa sổ ở trước không thuộc công cụ: không ai cấp được; giao diện không lên trước được → lượt "thường" bị loại
    ban.truoc = "khac:Code.exe"
    nhat_ky.clear()
    thuong = eg.do_mot_lan(con, 4, "thuong", _ngu_canh(nhat_ky, gui, che, ban=ban))
    assert thuong["cap_quyen_truoc"] == "khong_ai:khac:Code.exe"
    assert thuong["ket_qua_dua_ra_truoc"] == "giao_dien:tu_choi:khac:Code.exe"
    assert thuong["cua_so_truoc"] == "khac:Code.exe" and thuong["gui_lo_ra"] == 1.0
    assert eg.ly_do_loai(thuong) == "gui_khong_o_truoc"
    assert nhat_ky.index("gui.len_truoc") < nhat_ky.index("gui.dua_len_dau")       # thử lần cuối, rồi chỉ thứ tự Z
    assert ("ở trước=khac:Code.exe (đưa ra trước: giao_dien:tu_choi:khac:Code.exe; cấp quyền: khong_ai:khac:Code.exe)"
            in eg.dong_console(thuong))
    van_ban = eg.tom_tat([thu_nho, bi_che, thuong], _MAY)
    assert "gui_van_o_truoc 2, gui_khong_o_truoc 1" in _dong_ket_luan(van_ban, "Lượt bị loại")
    chuyen = _dong_ket_luan(van_ban, "Đưa cửa sổ ra trước")
    for chu in ("giao_dien 0/1 (giao_dien:tu_choi:khac:Code.exe 1)", "trung_tinh 0/1 (trung_tinh:tu_choi:giao_dien 1)",
                "man_che 0/1 (man_che:tu_choi:giao_dien 1)", "giao_dien:tu_choi:5 2", "khong_ai:khac:Code.exe 1"):
        assert chu in chuyen, chuyen


@pytest.mark.parametrize("tu, cua_so_tu", [("thu_nho", "trung_tinh"), ("bi_che", "man_che")])
def test_ve_thuong_dua_giao_dien_len_truoc(tu, cua_so_tu):
    """Về "thường": tiến trình `che` (đang ở trước) cấp quyền; giao diện khôi phục rồi tự lên trước; màn che / cửa sổ
    trung tính chỉ ẩn SAU đó (ẩn trước thì Windows trao cửa sổ ở trước cho ứng dụng khác, không ai cấp quyền được)."""
    nhat_ky: list = []
    ban = BanLamViecGia("giao_dien")
    con, gui, che = _ba_doi_tuong(ban, nhat_ky)
    dong = eg.do_mot_lan(con, 1, tu, _ngu_canh(nhat_ky, gui, che, ban=ban))
    assert dong["cua_so_truoc"] == cua_so_tu and eg.ly_do_loai(dong) is None
    nhat_ky.clear()
    dong = eg.do_mot_lan(con, 2, "thuong", _ngu_canh(nhat_ky, gui, che, ban=ban))
    assert (dong["cap_quyen_truoc"], dong["ket_qua_dua_ra_truoc"]) == (f"{cua_so_tu}:ok", "giao_dien:ok")
    assert dong["cua_so_truoc"] == "giao_dien" and dong["gui_thu_nho"] is False and dong["gui_lo_ra"] == 1.0
    assert eg.ly_do_loai(dong) is None
    assert (nhat_ky.index("gui.khoi_phuc") < nhat_ky.index("che.cap_quyen") < nhat_ky.index(("con.gui", "len_truoc t2"))
            < nhat_ky.index("che.an") < nhat_ky.index(("con.gui", "plan 2")))
    assert not (che.dang_hien or che.trung_tinh_hien) and "gui.dua_len_dau" not in nhat_ky
    assert " ở trước=giao_dien" in eg.dong_console(dong) and "đưa ra trước" not in eg.dong_console(dong)


def test_cua_so_truoc_phan_biet_man_che_va_cua_so_trung_tinh():
    che = FakeManChe([])

    def may(pid, hwnd, exe="python.exe") -> TrangThaiMay:
        return TrangThaiMay("mo", "active", "Default", "bat", 1.0, pid, hwnd, exe)

    assert eg._cua_so_truoc(may(FakeCon.pid, 1), FakeCon.pid, che) == "giao_dien"
    assert eg._cua_so_truoc(may(FakeManChe.pid, FakeManChe.hwnd_trung_tinh), FakeCon.pid, che) == "trung_tinh"
    assert eg._cua_so_truoc(may(FakeManChe.pid, 8001), FakeCon.pid, che) == "man_che"
    assert eg._cua_so_truoc(may(9090, 5, "Code.exe"), FakeCon.pid, che) == "khac:Code.exe"
    assert eg._cua_so_truoc(may(None, None, ""), FakeCon.pid, che) == ""
    assert eg._cua_so_truoc(may(FakeManChe.pid, 8001), FakeCon.pid, None) == "khac:python.exe"


def test_tom_tat_dong_cu_khong_doi_va_thuong_khong_o_truoc_bi_loai():
    """Dòng cũ (trước 02/10/2026, không có hai khóa mới) tóm tắt y như trước; "thường" mà giao diện không ở trước lúc
    bấm bị loại khỏi mốc."""
    dong = [r for bt in ("gui_system", "gui_off") for tt in eg.TRANG_THAI for r in _ba(bt, tt, 3.6)]
    dong += _ba("khong_cua_so", "khong_cua_so", 3.61)
    cu = [{k: v for k, v in d.items() if k not in ("cap_quyen_truoc", "ket_qua_dua_ra_truoc")} for d in dong]
    van_ban = eg.tom_tat(cu, _MAY)
    assert van_ban == eg.tom_tat(dong, _MAY) and "Đưa cửa sổ ra trước" not in van_ban
    assert "ForegroundLockTimeout" not in van_ban                     # may.json cũ không có khoa_truoc_ms
    moi = [d | {"ket_qua_dua_ra_truoc": f"{eg.DICH_TRUOC[d['trang_thai']]}:ok"} if d["bien_the"] != "khong_cua_so"
           else d for d in dong]
    moi[0] = moi[0] | {"cap_quyen_truoc": "trung_tinh:ok"}
    van_ban = eg.tom_tat(moi, _MAY | {"windows": {"khoa_truoc_ms": 200000}})
    assert ("Đưa cửa sổ ra trước lúc đổi trạng thái (mọi lượt có cửa sổ, kể cả lượt bị loại; đọc lại cửa sổ ở trước "
            "ngay sau): giao_dien 6/6; trung_tinh 6/6; man_che 6/6. Cấp quyền trước đó (AllowSetForegroundWindow): "
            "trung_tinh:ok 1.") in van_ban
    assert "khóa cửa sổ ở trước (ForegroundLockTimeout) 200000 ms" in van_ban
    assert eg.ly_do_loai(_dong("gui_system", "thuong", 3.6, cua_so_truoc="trung_tinh")) == "gui_khong_o_truoc"
    assert eg.ly_do_loai(_dong("gui_system", "thuong", 3.6, cua_so_truoc="")) == "gui_khong_o_truoc"
    assert eg.ly_do_loai(_dong("gui_system", "thu_nho", 3.6, cua_so_truoc="trung_tinh")) is None


def test_ly_do_moi_khong_doi_cach_loai_dong_cu():
    """Hai lý do thêm 02/10/2026 (`doi_trang_thai_trong_chay` của chế độ chạy, `khong_giu_duoc_ecoqos` của gui_system)
    không đổi cách loại dòng lập đường cũ: dòng đó không có khóa `mau_sai`, ghi chú cũ không có lý do mới."""
    dong = [r for bt in ("gui_system", "gui_off") for tt in eg.TRANG_THAI for r in _ba(bt, tt, 3.6)]
    dong += [_dong("gui_system", "thuong", 4.5, lan=0),
             _dong("gui_off", "thu_nho", 3.6, ghi_chu="khong_tat_duoc_ecoqos")]
    assert all("mau_sai" not in d for d in dong)
    assert [eg.ly_do_loai(d) for d in dong[-2:]] == ["khoi_dong", "khong_tat_duoc_ecoqos"]
    assert all(eg.ly_do_loai(d) is None for d in dong[:-2])
    assert eg.ly_do_loai(_dong("gui_system", "thuong", 3.6, mau_sai=0)) is None
    giu = _dong("gui_system", "bi_che", 3.6, ghi_chu="khong_giu_duoc_ecoqos")
    assert eg.ly_do_loai(giu) == "khong_giu_duoc_ecoqos"
    assert "khoi_dong 1, khong_tat_duoc_ecoqos 1, khong_giu_duoc_ecoqos 1" in \
        _dong_ket_luan(eg.tom_tat(dong + [giu], _MAY), "Lượt bị loại")


@windows_only
def test_ham_win32_cap_quyen_va_dat_truoc_dung_tham_so(monkeypatch):
    """AllowSetForegroundWindow nhận ASFW_ANY = (DWORD)-1; SetForegroundWindow rồi đọc lại GetForegroundWindow. Hàm
    Win32 là đồ giả: test không đổi cửa sổ ở trước của máy đang chạy."""
    goi: list[tuple] = []
    tra = {"AllowSetForegroundWindow": 0, "SetForegroundWindow": 1, "GetForegroundWindow": 4242}

    def ham_gia(thu_vien, ten, restype, *argtypes):
        return lambda *args: (goi.append((thu_vien, ten, args)), tra[ten])[1]

    monkeypatch.setattr(eg, "_ham", ham_gia)
    ok, loi = eg.cho_phep_dat_truoc()
    assert goi == [("user32", "AllowSetForegroundWindow", (0xFFFFFFFF,))] and ok is False and isinstance(loi, int)
    goi.clear()
    assert eg.dat_cua_so_truoc(777) == (True, 4242)
    assert goi == [("user32", "SetForegroundWindow", (777,)), ("user32", "GetForegroundWindow", ())]


# ------------------------------------------------------------------------------------------- đầu dò trong giao diện

def _bom(window, tin: list, so_tin: int, toi_da_s: float = 20.0) -> None:
    """Gọi `_on_tick` như QTimer 16 ms cho tới khi đầu dò gửi đủ `so_tin` thông điệp."""
    cuoi = time.monotonic() + toi_da_s
    while len(tin) < so_tin and time.monotonic() < cuoi:
        window._on_tick()
        time.sleep(0.01)


def test_dau_do_lap_duong_qua_cua_so_that(qapp, monkeypatch):
    from autopark.planning import portfolio
    from autopark.ui import main_window
    from autopark.ui.app import DEFAULT_SCENARIO, build_window

    monkeypatch.setattr(portfolio, "plan", portfolio.plan)          # lớp bọc luôn được gỡ khi test xong
    # Ghi lại chứ không ném lỗi: lỗi ném ra trong plan() bị `except Exception` của đầu dò nuốt thành tin "loi" mang
    # đúng yeu_cau, nên bẫy ném lỗi không bắt được việc đầu dò quên kiểm trạng thái (review 02/10/2026).
    hop_thoai: list[tuple] = []
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *args, **kwargs: hop_thoai.append(args[1:]))
    window = build_window(DEFAULT_SCENARIO)
    goc = portfolio.plan
    try:
        tin: list[dict] = []
        dau_do = eg.DauDoKeHoach(window, tin.append)
        go = eg.ghi_nac(dau_do.nhan_nac)
        assert portfolio.plan is not goc
        dau_do.xu_ly("plan 1")
        dau_do.xu_ly("plan 2")                                       # đang PLANNING: từ chối, không gọi plan()
        assert hop_thoai == []
        assert len(tin) == 1 and (tin[0]["loai"], tin[0]["yeu_cau"]) == ("loi", "2")
        assert "phiên đang" in tin[0]["thong_diep"] and "plan() lỗi" not in tin[0]["thong_diep"]
        _bom(window, tin, 2)
        kq = tin[1]
        assert (kq["loai"], kq["ket_qua"], kq["lan"], kq["yeu_cau"]) == ("ket_qua", "OK", 0, "1")
        assert 0 < kq["tg_tinh_s"] <= kq["tg_giao_dien_s"]
        assert kq["nac"] and kq["nac"][-1]["bam"] is True
        assert kq["cusps"] is not None and kq["ecoqos_con"] in ("off", "system", "on", "khong_doc_duoc")
        dau_do.xu_ly("plan 3")                                       # lập lại từ READY
        _bom(window, tin, 3)
        assert (tin[2]["loai"], tin[2]["ket_qua"], tin[2]["lan"]) == ("ket_qua", "OK", 1)
        assert hop_thoai == []                                       # không lần nào plan() mở hộp thoại
        go()
        assert portfolio.plan is goc
    finally:
        window.close()


def test_dau_do_cap_quyen_va_len_truoc():
    """Lệnh thêm 02/10/2026: trả lời mang mã yêu cầu, BOOL, GetLastError / cửa sổ ở trước; SetForegroundWindow nhận
    HWND của chính cửa sổ giao diện. Hàm Win32 là đồ giả (không gọi AllowSetForegroundWindow thật)."""
    from types import SimpleNamespace

    goi: list = []
    cua_so = SimpleNamespace(_after_plan=lambda result: None, winId=lambda: 31337)
    tin: list[dict] = []
    dau_do = eg.DauDoKeHoach(cua_so, tin.append, cap_quyen=lambda: (goi.append("cap_quyen"), (False, 5))[1],
                             dat_truoc=lambda hwnd: (goi.append(hwnd), (True, hwnd))[1])
    dau_do.xu_ly("cap_quyen q7")
    dau_do.xu_ly("len_truoc t7")
    assert goi == ["cap_quyen", 31337]
    assert tin == [{"loai": "cap_quyen", "yeu_cau": "q7", "ok": False, "loi": 5},
                   {"loai": "len_truoc", "yeu_cau": "t7", "ok": True, "truoc_hwnd": 31337}]


def test_nen_lap_duong_khong_cua_so(tmp_path, monkeypatch):
    """Đối chứng không cửa sổ: cùng Session.plan_async + poll_plan, cùng thông điệp với `con`."""
    from autopark.application.session import Session
    from autopark.planning import portfolio
    from autopark.storage.scenario_store import load_scenario, load_vehicle_config

    monkeypatch.setattr(portfolio, "plan", portfolio.plan)
    duong_dan, _ = eg.viet_kich_ban("pillar_at_slot_mouth", tmp_path)
    scenario = load_scenario(duong_dan)
    session = Session(scenario, load_vehicle_config(scenario.vehicle_config_path))
    nac: dict = {}
    go = eg.ghi_nac(lambda ds, t: nac.update(ds=ds, t=t))
    try:
        kq = eg.chay_mot_lan_nen(session, 0, nac)
        assert (kq["loai"], kq["ket_qua"], kq["lan"]) == ("ket_qua", "OK", 0)
        assert 0 < kq["tg_tinh_s"] <= kq["tg_giao_dien_s"] and kq["nac"]
        assert eg.chay_mot_lan_nen(session, 1, nac)["lan"] == 1
    finally:
        go()
        session.close()


# ------------------------------------------------------------------------------------ tiến trình con thật (offscreen)

def test_con_tu_choi_nen_tang_offscreen(tmp_path):
    pytest.importorskip("PySide6")
    duong_dan, _ = eg.viet_kich_ban("pillar_at_slot_mouth", tmp_path)
    p = eg.TienTrinhCon(["con", "--kich-ban", str(duong_dan)], "con", env=_env_offscreen())
    try:
        tin = p.doc(30.0, ("loi", "san_sang"))
        assert tin is not None and tin["loai"] == "loi" and "offscreen" in tin["thong_diep"]
        assert p.proc.wait(timeout=30) == 2
    finally:
        p.dong()


def test_con_giao_thuc_dong_lenh(tmp_path):
    pytest.importorskip("PySide6")
    duong_dan, _ = eg.viet_kich_ban("pillar_at_slot_mouth", tmp_path)       # đo 0,69 s so với hạn 8 s
    nhat_ky: list[str] = []
    p = eg.TienTrinhCon(["con", "--kich-ban", str(duong_dan), "--cho-phep-offscreen"], "con", ghi=nhat_ky.append,
                        env=_env_offscreen())
    try:
        san_sang = p.doc(60.0, ("san_sang", "loi"))
        assert san_sang is not None and san_sang["loai"] == "san_sang", nhat_ky
        # pid tự báo (Scripts\python.exe của venv là trình khởi chạy: proc.pid có thể là pid khác)
        assert san_sang["pid"] == p.pid and isinstance(san_sang["hwnd"], int) and san_sang["nen_tang"] == "offscreen"
        win11 = sys.platform == "win32" and sys.getwindowsversion().build >= 22000
        if win11:
            # như biến thể gui_off: tắt EcoQoS từ ngoài theo pid tự báo; chính tiến trình lập đường phải thấy "off"
            assert san_sang["ecoqos"] == "system" and eg.disable_power_throttling(p.pid)
            assert eg.cpu_tien_trinh_s(p.pid) is not None and eg.uu_tien(p.pid) is not None
        # lệnh đưa cửa sổ ra trước: offscreen không phải cửa sổ thật, nên trả lời "không được" mà không gọi Win32
        assert p.gui("cap_quyen q1") and p.gui("len_truoc t1")
        assert p.doc(30.0, "cap_quyen", "q1") == {"loai": "cap_quyen", "yeu_cau": "q1", "ok": False, "loi": None}
        assert p.doc(30.0, "len_truoc", "t1") == {"loai": "len_truoc", "yeu_cau": "t1", "ok": False, "truoc_hwnd": None}
        assert p.gui("plan 1")
        kq = p.doc(40.0, ("ket_qua", "loi"), "1")
        assert kq is not None and (kq["loai"], kq["ket_qua"], kq["lan"]) == ("ket_qua", "OK", 0), (kq, nhat_ky)
        if win11:
            assert kq["ecoqos_con"] == "off"
        assert p.gui("thoat")
        assert p.proc.wait(timeout=30) == 0
    finally:
        p.dong()


def test_che_giao_thuc_va_tu_dong_khi_het_gio():
    """Tiến trình `che` (Qt offscreen): màn che và cửa sổ trung tính, các lệnh mới qua `ManChe`, rồi tự đóng khi hết
    `--toi-da` (bảo đảm dọn dẹp). Offscreen không phải cửa sổ thật: cap_quyen / len_truoc trả "không được", không gọi
    Win32."""
    pytest.importorskip("PySide6")
    nhat_ky: list[str] = []
    p = eg.TienTrinhCon(["che", "--toi-da", "6", "--cho-phep-offscreen"], "che", ghi=nhat_ky.append,
                        env=_env_offscreen())
    try:
        san_sang = p.doc(60.0, ("san_sang", "loi"))
        assert san_sang is not None and san_sang["loai"] == "san_sang", nhat_ky
        assert isinstance(san_sang["hwnd"], int) and isinstance(san_sang["hwnd_trung_tinh"], int)
        assert san_sang["hwnd"] != san_sang["hwnd_trung_tinh"] and san_sang["pid"] == p.pid
        che = eg.ManChe(p, san_sang)
        assert che.hwnd_trung_tinh == san_sang["hwnd_trung_tinh"] and che.con_song()
        assert che.hien_trung_tinh() and che.hwnd_trung_tinh == san_sang["hwnd_trung_tinh"]
        assert che.len_truoc("trung_tinh") == {"loai": "da_len_truoc", "cua_so": "trung_tinh", "ok": False,
                                               "truoc_hwnd": None}
        assert che.cap_quyen() == {"loai": "cap_quyen", "ok": False, "loi": None}
        assert p.gui("hien") and p.doc(10.0, "da_hien") == {"loai": "da_hien", "hwnd": san_sang["hwnd"]}
        che.an("che")
        che.an("trung_tinh")
        assert che.len_truoc("che")["ok"] is False and che.con_song()       # đã ẩn: không gọi SetForegroundWindow
        che.an()
        assert che.con_song() and che.ly_do_dong == ""
        assert che.hien_trung_tinh()               # hết giờ lúc cửa sổ đang hiện: vẫn phải tự đóng (bảo đảm dọn dẹp)
        tin = p.doc(40.0, ("het_gio", "nguoi_dung_dong"))                   # tự đóng sau --toi-da giây
        assert tin is not None and tin["loai"] == "het_gio", nhat_ky
        assert p.proc.wait(timeout=30) == 0
        assert p.doc(1.0, "nguoi_dung_dong") is None                        # không báo nhầm "người dùng đóng"
        assert not che.con_song() and che.ly_do_dong == "da_thoat"
    finally:
        p.dong()


def test_che_thoat_ngay_khi_dang_hien_cua_so():
    """Lệnh `thoat` (tiến trình điều khiển kết thúc, hoặc hết stdin) lúc màn che và cửa sổ trung tính đang hiện: thoát
    ngay, mã 0, không báo nhầm "người dùng đóng" (quit() của Qt 6 hỏi closeEvent; công cụ dùng exit())."""
    pytest.importorskip("PySide6")
    p = eg.TienTrinhCon(["che", "--toi-da", "120", "--cho-phep-offscreen"], "che", env=_env_offscreen())
    try:
        san_sang = p.doc(60.0, ("san_sang", "loi"))
        assert san_sang is not None and san_sang["loai"] == "san_sang"
        che = eg.ManChe(p, san_sang)
        assert che.hien_trung_tinh() and p.gui("hien") and p.doc(10.0, "da_hien") is not None
        t = time.monotonic()
        assert p.dong(cho=10.0) == 0 and time.monotonic() - t < 5.0
        assert p.doc(0.5, ("nguoi_dung_dong", "het_gio")) is None
    finally:
        p.dong()


# -------------------------------------------------------------------------------------------- kịch bản và dòng lệnh

def test_viet_kich_ban_giu_nguyen_ca(tmp_path):
    from autopark.evaluation.hard_cases import build_cases
    from autopark.storage.scenario_store import load_scenario, load_vehicle_config

    duong_dan, lech = eg.viet_kich_ban("uturn_w46", tmp_path)
    assert duong_dan == (tmp_path / "ca_uturn_w46.json").resolve() and lech == 0.0
    goc = build_cases(load_vehicle_config(eg.VEHICLE_CONFIG))["uturn_w46"].scenario
    lai = load_scenario(duong_dan)
    assert (lai.start, lai.goal, lai.bounds, lai.obstacles) == (goc.start, goc.goal, goc.bounds, goc.obstacles)
    assert lai.goal.pose.yaw == math.pi
    assert lai.vehicle_config_path == eg.VEHICLE_CONFIG.resolve()
    with pytest.raises(ValueError, match="khong_co_ca_nay"):
        eg.viet_kich_ban("khong_co_ca_nay", tmp_path)


def test_do_tu_choi_tham_so_sai_truoc_khi_mo_gi(tmp_path, monkeypatch, capsys):
    """Tham số sai: mã 2 trước khi tạo thư mục hay mở tiến trình con nào (lượt đo thật chỉ chạy bằng tay)."""
    monkeypatch.setattr(eg, "TienTrinhCon", lambda *a, **k: pytest.fail("không được mở tiến trình con"))
    monkeypatch.setattr(sys, "platform", "win32")             # các bước kiểm tham số không gọi Win32
    moi = tmp_path / "moi"
    for sai in (["--cho", "1"], ["--trang-thai", "thuong,nghieng"], ["--bien-the", "gui_x"], ["--ca", "khong_co"],
                ["--khoi", "0"]):
        assert eg.main(["do", "--ra", str(moi), *sai]) == 2, sai
    assert not moi.exists()
    cu = tmp_path / "cu"
    cu.mkdir()
    (cu / "ket_qua.jsonl").write_text("", encoding="utf-8")
    assert eg.main(["do", "--ra", str(cu)]) == 2
    assert "chọn thư mục mới" in capsys.readouterr().err
    monkeypatch.setattr(sys, "platform", "linux")
    assert eg.main(["do", "--ra", str(moi)]) == 2


def test_moi_truong_con_giu_ecoqos():
    """AUTOPARK_KEEP_ECOQOS (thêm 02/10/2026): mặc định đặt "1" (chế độ lập đường và gui_system giữ mặc định của
    Windows kể cả khi ứng dụng tự tắt EcoQoS), giu_ecoqos=False thì bỏ; cờ báo trong dict thứ hai; dict gốc không đổi."""
    goc = {"QT_QPA_PLATFORM": "offscreen", "AUTOPARK_RRT_SEED": "3", "AUTOPARK_KEEP_ECOQOS": "0", "PATH": "x"}
    env, co = eg.moi_truong_con(goc)
    assert env == {"PATH": "x", "AUTOPARK_KEEP_ECOQOS": "1"}
    assert co == {"QT_QPA_PLATFORM_da_bo": True, "AUTOPARK_RRT_SEED_da_bo": True, "AUTOPARK_KEEP_ECOQOS_dat": True}
    env, co = eg.moi_truong_con(goc, giu_ecoqos=False)
    assert env == {"PATH": "x"} and co["AUTOPARK_KEEP_ECOQOS_dat"] is False
    assert goc["AUTOPARK_KEEP_ECOQOS"] == "0" and goc["QT_QPA_PLATFORM"] == "offscreen"
    env, co = eg.moi_truong_con({"PATH": "x"})
    assert env["AUTOPARK_KEEP_ECOQOS"] == "1" and co["QT_QPA_PLATFORM_da_bo"] is False
    assert _env_offscreen()["AUTOPARK_KEEP_ECOQOS"] == "1"            # tiến trình con của các test ở đây cũng vậy


class FakeTienTrinh:
    """TienTrinhCon giả cho `chay_do`: `con` báo san_sang với EcoQoS `ecoqos`, lập đường OK ngay; giữ env đã nhận."""

    def __init__(self, tham_so, ten, *, ghi=None, env=None, ecoqos="system"):
        from types import SimpleNamespace

        self.tham_so, self.ten, self.env = list(tham_so), ten, env
        self.pid, self.proc, self.con_song = FakeCon.pid, SimpleNamespace(pid=FakeCon.pid - 1), True
        self._tin = [{"loai": "san_sang", "pid": FakeCon.pid, "hwnd": FakeCuaSo.hwnd, "nen_tang": "windows",
                      "ecoqos": ecoqos}]

    def gui(self, lenh: str) -> bool:
        ten, yeu_cau = eg._tach_lenh(lenh)
        if ten == "plan":
            self._tin.append(_ket_qua_gia(yeu_cau))
        elif ten in ("cap_quyen", "len_truoc"):
            self._tin.append({"loai": ten, "yeu_cau": yeu_cau, "ok": True, "loi": 0, "truoc_hwnd": FakeCuaSo.hwnd})
        return True

    def doc(self, het_han, loai, yeu_cau=None):
        muon = {loai} if isinstance(loai, str) else set(loai)
        for i, tin in enumerate(self._tin):
            if tin["loai"] in muon:
                return self._tin.pop(i)
        return None

    def dong(self, cho: float = 10.0) -> int:
        self.con_song = False
        return 0


@pytest.mark.parametrize("ecoqos, ly_do", [("system", None), ("off", "khong_giu_duoc_ecoqos"), (None, None)])
def test_do_gui_system_phai_o_mac_dinh_cua_windows(tmp_path, monkeypatch, capsys, ecoqos, ly_do):
    """Chế độ lập đường, biến thể gui_system (thêm 02/10/2026): tiến trình con nhận AUTOPARK_KEEP_ECOQOS=1, và EcoQoS lúc
    sẵn sàng phải là "system" (mặc định của Windows), không thì mọi dòng của khối bị loại `khong_giu_duoc_ecoqos` kèm
    cảnh báo. Không đọc được (None: Windows trước bản 22000) là KHÔNG BIẾT, không phải khác mặc định: dòng vẫn hợp lệ
    như trước khi có phép kiểm, chỉ có cảnh báo "không đọc được EcoQoS" (sửa sau rà soát 02/10/2026). Tiến trình con,
    cửa sổ và lớp Win32 là đồ giả: không mở cửa sổ, không chạm thiết lập máy."""
    import functools

    tao: list[FakeTienTrinh] = []

    def tien_trinh(tham_so, ten, **kw):
        tao.append(FakeTienTrinh(tham_so, ten, ecoqos=ecoqos, **kw))
        return tao[-1]

    class CuaSo(FakeCuaSo):
        ton_tai = True

    may = TrangThaiMay("mo", "active", "Default", "bat", 100.0, FakeCon.pid, FakeCuaSo.hwnd, "python.exe")
    monkeypatch.setattr(eg, "TienTrinhCon", tien_trinh)
    monkeypatch.setattr(eg, "CuaSoWin32", lambda hwnd: CuaSo([]))
    monkeypatch.setattr(eg, "doc_trang_thai_may", lambda *a, **k: may)
    for ten, gia_tri in (("doc_git", {}), ("dat_dpi_vat_ly", True), ("doc_windows", {}), ("doc_nguon", {}),
                         ("lop_cpu", None), ("_chay_powercfg", None)):
        monkeypatch.setattr(eg, ten, lambda *a, _g=gia_tri, **k: _g)
    monkeypatch.setattr(eg, "NguCanhDo", functools.partial(
        NguCanhDo, doc_may=lambda: may, doc_truoc=lambda: (FakeCon.pid, FakeCuaSo.hwnd, "python.exe"),
        chup_cpu=lambda: _chup(0.0, [0.0, 0.0]), ecoqos_cua=lambda pid: ecoqos, uu_tien_cua=lambda pid: "normal",
        cpu_cua=lambda pid: 1.0, ngu=lambda s: None))
    ra = tmp_path / "ra"
    assert eg.main(["do", "--ra", str(ra), "--ca", "pillar_at_slot_mouth", "--khoi", "1", "--lap", "1", "--cho", "2",
                    "--trang-thai", "thuong", "--bien-the", "gui_system"]) == 0
    assert [(p.tham_so[0], p.env.get("AUTOPARK_KEEP_ECOQOS")) for p in tao] == [("con", "1")]
    dong = eg._doc_jsonl(ra / "ket_qua.jsonl")
    doc = ecoqos or "khong_doc_duoc"
    assert [(d["lan"], d["ket_qua"], d["ecoqos"]) for d in dong] == [(0, "OK", doc), (1, "OK", doc)]
    assert eg.ly_do_loai(dong[1]) == ly_do and dong[1]["ghi_chu"] == (ly_do or "")
    ra_man_hinh = capsys.readouterr().out
    assert ("CẢNH BÁO: EcoQoS của giao diện" in ra_man_hinh) == (ly_do is not None)
    assert ("không phải mặc định của Windows" in ra_man_hinh) == (ly_do is not None)
    assert ("không đọc được EcoQoS" in ra_man_hinh and "vẫn được giữ" in ra_man_hinh) == (ecoqos is None)
    assert json.loads((ra / "may.json").read_text(encoding="utf-8"))["moi_truong"]["AUTOPARK_KEEP_ECOQOS_dat"] is True
    tom_tat = (ra / "tom_tat.txt").read_text(encoding="utf-8")
    assert ("khong_giu_duoc_ecoqos" in tom_tat) == (ly_do is not None)


def test_kiem_gui_system_khong_doc_duoc_khong_phai_khac_mac_dinh():
    """Luật chung của hai chế độ (sửa 02/10/2026): chỉ giá trị đọc được và khác "system" mới loại khối gui_system."""
    assert eg.kiem_gui_system("system") == "ok"
    assert eg.kiem_gui_system(None) == "khong_doc_duoc"
    assert eg.kiem_gui_system("off") == eg.kiem_gui_system("on") == "khong_giu_duoc_ecoqos"
    assert "22000" in eg.ECOQOS_KHONG_DOC_DUOC


def test_bien_the_noi_nghia_moi_cua_gui_system_va_gui_off():
    """Docstring của BIEN_THE định nghĩa nghĩa của số đo. Từ 02/10/2026 ứng dụng tự tắt EcoQoS (`ui.app.main`), nên
    "gui_system như người dùng mở app" sai: gui_system là mặc định của Windows (ứng dụng trước ngày đó hay chạy với
    AUTOPARK_KEEP_ECOQOS=1, tiến trình con dựng cửa sổ qua build_window), gui_off là ứng dụng hiện nay (sửa sau rà soát
    02/10/2026)."""
    import ast
    import inspect

    cay = ast.parse(inspect.getsource(eg))
    than = cay.body
    i = next(k for k, nut in enumerate(than) if isinstance(nut, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "BIEN_THE" for t in nut.targets))
    chu = " ".join(than[i + 1].value.value.split())                 # chuỗi ngay sau phép gán, bỏ xuống dòng
    assert "như người dùng mở app" not in chu
    assert "như ứng dụng trước 02/10/2026, hay ứng dụng chạy với AUTOPARK_KEEP_ECOQOS=1" in chu
    assert "`ui.app.build_window`, không qua `main()`" in chu
    assert "đúng lời gọi mà ứng dụng từ 02/10/2026 tự làm cho mình (power_throttling.apply_ecoqos_policy)" in chu
    dau = " ".join((eg.__doc__ or "").split())
    assert "`gui_off` là ứng dụng hiện nay" in dau


def test_tom_tat_dong_lenh_viet_lai_tu_tep(tmp_path, capsys):
    """`tom-tat --ra`: viết lại tom_tat.txt từ ket_qua.jsonl + may.json, đúng như hàm thuần `tom_tat`."""
    dong = [r for bt in ("gui_system", "gui_off") for tt in eg.TRANG_THAI for r in _ba(bt, tt, 3.6)]
    (tmp_path / "ket_qua.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in dong),
                                            encoding="utf-8")
    (tmp_path / "may.json").write_text(json.dumps(_MAY, ensure_ascii=False), encoding="utf-8")
    assert eg.main(["tom-tat", "--ra", str(tmp_path)]) == 0
    assert (tmp_path / "tom_tat.txt").read_text(encoding="utf-8") == eg.tom_tat(dong, _MAY)
    assert "không thấy chậm" in capsys.readouterr().out
    assert eg.main(["tom-tat", "--ra", str(tmp_path / "khong_co")]) == 2


def test_powercfg_bo_xu_ly_khong_thanh_cr_cr_lf(tmp_path, monkeypatch):
    """powercfg in xuống dòng CRLF. Tệp powercfg_bo_xu_ly.txt (ghi ở chế độ văn bản) không được có CR CR LF: trình soạn
    thảo hiện cách dòng đôi và git coi tệp là nhị phân (gặp ở lượt thử 02/10/2026). powercfg ở đây là đồ giả."""
    goi: list[list[str]] = []

    def run_gia(lenh, **kwargs):
        goi.append(lenh)
        return subprocess.CompletedProcess(lenh, 0, stderr=b"", stdout=(
            b"Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)\r\n"
            b"  Subgroup GUID: 54533251-82be-4824-96c1-47b60b740d00  (Processor power management)\r\n\r\n"))

    monkeypatch.setattr(eg.subprocess, "run", run_gia)
    chu = eg._chay_powercfg("/getactivescheme")
    assert "\r" not in chu and chu.count("\n") == 3
    assert eg._phan_tich_ke_hoach(chu) == {"guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", "ten": "High performance"}
    tep = eg.ghi_powercfg_bo_xu_ly(tmp_path, "02/10/2026 09:00:00")
    assert goi[-1] == ["powercfg", "/qh", "SCHEME_CURRENT", "SUB_PROCESSOR"]
    raw = tep.read_bytes()
    assert b"\r\r" not in raw and raw.count(b"\n") == 4                # dòng lệnh + 3 dòng của powercfg
    assert tep.read_text(encoding="utf-8").splitlines()[1].startswith("Power Scheme GUID: 8c5e7fda")


# --------------------------------------------------------------------------------------------- đọc Windows thật

@windows_only
def test_doc_trang_thai_may_tren_windows():
    may = eg.doc_trang_thai_may()
    assert may.phien in ("mo", "khoa", "khong_ro")
    assert may.ket_noi in (*eg._KET_NOI.values(), "khong_ro")
    assert may.ban_lam_viec in ("Default", "Winlogon", "Screen-saver", "")
    assert may.man_hinh in ("bat", "tat", "mo_toi", "khong_ro")
    assert may.vang_s is None or may.vang_s >= 0
    assert eg.doc_man_hinh() in ("bat", "tat", "mo_toi", "khong_ro")
    assert may.nhin_thay_duoc == (may.phien == "mo" and may.ket_noi == "active" and may.ban_lam_viec == "Default"
                                  and may.man_hinh in ("bat", "khong_ro"))
    assert may.to_dict()["nhin_thay_duoc"] == may.nhin_thay_duoc


@windows_only
def test_lop_cpu_va_chup_cpu_tren_windows():
    lop = eg.lop_cpu()
    n = os.cpu_count()
    if n <= 64:
        assert lop is not None and sorted(i for ds in lop.values() for i in ds) == list(range(n))
    chup = eg.chup_cpu()
    assert chup.he_thong is not None and len(chup.tung_cpu) == n
    truoc = eg.cpu_tien_trinh_s(os.getpid())
    t = time.perf_counter()
    while time.perf_counter() - t < 0.2:
        pass
    assert eg.cpu_tien_trinh_s(os.getpid()) > truoc
    assert eg.uu_tien(os.getpid()) in ("idle", "below_normal", "normal", "above_normal", "high", "realtime")
    assert eg.tai_pct(chup, eg.chup_cpu()) is not None
