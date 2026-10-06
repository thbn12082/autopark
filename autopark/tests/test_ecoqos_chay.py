"""Đo vòng điều khiển 50 Hz của ứng dụng giao diện khi chạy (thêm 02/10/2026, `autopark/evaluation/ecoqos_chay.py`,
lệnh `python -m autopark.evaluation.ecoqos_gui do-chay`).

Test không mở cửa sổ thật nào: Qt chạy offscreen; cửa sổ, màn che và tiến trình con trong `do_mot_lan_chay` là đồ giả
(dùng lại đồ giả của tests/test_ecoqos_gui.py); test tiến trình con chạy `con --chay` với Qt offscreen. Không cổng COM,
không camera, không LiDAR; VehicleIO chỉ với bo mô phỏng (liệt kê cổng COM trong giao diện bị thay bằng hàm làm hỏng
test). Không mang dấu `planner_budget`. Lượt đo thật chạy bằng tay, máy rảnh (≈ 16–30 phút cửa sổ thật)."""
import gzip
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from autopark.evaluation import ecoqos_chay as ec  # noqa: E402
from autopark.evaluation import ecoqos_gui as eg  # noqa: E402
from autopark.evaluation.ecoqos_gui import TrangThaiMay  # noqa: E402
from tests.test_ecoqos_gui import BanLamViecGia, FakeCuaSo, FakeManChe, _bom, _chup, _env_offscreen  # noqa: E402

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="đọc / đặt điều tiết của Windows")
WIN11 = sys.platform == "win32" and sys.getwindowsversion().build >= 22000


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# --------------------------------------------------------------------------------------------- thống kê (hàm thuần)

def _chuoi_gia(khoang_ms: list[float], *, rt: float = 1.0, buoc_dung: int | None = None,
               tinh_moi_buoc_us: int = 20) -> tuple[dict, int]:
    """Chuỗi thô giả như `DauDoChay` ghi. Nhịp giao diện thứ i đến sau khoang_ms[i] ms thật (nhịp đầu tính từ lúc
    bấm); real_dt = ms nguyên (QElapsedTimer cắt phần lẻ), chặn 100 ms; phiên chạy bước 5 ms theo bộ tích lũy như
    `Session.advance` (tính bằng µs nguyên cho khỏi sai số dấu phẩy động); nhịp điều khiển ở bước chia hết cho 4,
    các bước trong một nhịp cách nhau 1 µs. Từ bước `buoc_dung` phiên ở STOPPING. Trả (chuỗi, số bước)."""
    gd = {k: [] for k in ("w_us", "dt_ms", "buoc", "dk", "xu_ly_us", "tinh_us", "lagging")}
    dk = {k: [] for k in ("w_us", "buoc", "dung")}
    w_us, tich_luy, buoc = 0, 0, 0
    for k in khoang_ms:
        w_us += int(round(k * 1000))
        dt_ms = min(int(k), 100)
        tich_luy += int(round(dt_ms * 1000 * rt))
        n = n_dk = 0
        while tich_luy >= 5000:
            if buoc % 4 == 0:
                dk["w_us"].append(w_us + n)
                dk["buoc"].append(buoc)
                if buoc_dung is not None and buoc >= buoc_dung:
                    dk["dung"].append(len(dk["w_us"]) - 1)
                n_dk += 1
            buoc, n, tich_luy = buoc + 1, n + 1, tich_luy - 5000
        gd["w_us"].append(w_us)
        gd["dt_ms"].append(dt_ms)
        gd["buoc"].append(n)
        gd["dk"].append(n_dk)
        gd["xu_ly_us"].append(n * tinh_moi_buoc_us + 300)
        gd["tinh_us"].append(n * tinh_moi_buoc_us)
    return {"gd": gd, "dk": dk}, buoc


def _thong_ke(khoang_ms: list[float], rt: float = 1.0, **kw) -> dict:
    chuoi, buoc = _chuoi_gia(khoang_ms, rt=rt, **kw)
    return ec.thong_ke_nhip(chuoi, rt=rt, tg_tuong_s=sum(khoang_ms) / 1000, tg_phien_s=buoc * 0.005)


def test_phan_vi_noi_suy_tuyen_tinh():
    assert ec._phan_vi([], 0.5) is None and ec._phan_vi([None], 0.5) is None
    assert ec._phan_vi([7.0], 0.95) == 7.0
    xs = [4.0, 1.0, None, 3.0, 2.0]                          # sắp: 1 2 3 4 (bỏ None)
    assert (ec._phan_vi(xs, 0.0), ec._phan_vi(xs, 1.0)) == (1.0, 4.0)
    assert ec._phan_vi(xs, 0.5) == pytest.approx(2.5)
    assert ec._phan_vi(xs, 0.95) == pytest.approx(3.85)     # như numpy.percentile(..., 95): 0,95·3 = 2,85
    assert ec._phan_vi(range(101), 0.99) == pytest.approx(99.0)


def test_thong_ke_nhip_deu_16ms():
    # 16 ms đều, real_dt đúng 16 ms: 3–4 bước mỗi nhịp, tối đa một nhịp điều khiển mỗi nhịp giao diện
    tk = _thong_ke([16.0] * 200)
    assert set(tk) == set(ec.KHOA_THONG_KE)
    assert (tk["nhip_gd_p50_ms"], tk["nhip_gd_p95_ms"], tk["nhip_gd_max_ms"]) == (16.0, 16.0, 16.0)
    assert (tk["so_nhip_gd"], tk["tre_nhip_dau_ms"], tk["nhip_gd_bi_chan"], tk["mat_chan_s"]) == (200, 16.0, 0, 0.0)
    assert tk["troi_lam_tron_pct"] == 0.0 and tk["ty_le_phien"] == pytest.approx(1.0, abs=0.002)
    assert tk["so_nhip_dk"] == tk["so_nhip_dk_ly_thuyet"] == 160 and tk["so_nhip_dk_dung"] == 0
    assert 16.0 <= tk["khoang_dk_max_ms"] <= 33.0 and tk["khoang_dk_tren_han"] == 0
    # bước s chỉ chạy khi phiên đủ (s + 1)·5 ms, ở nhịp giao diện kế tiếp: trễ ≤ một nhịp 16 ms + một bước 5 ms
    assert 5.0 <= tk["tre_dk_p50_ms"] <= tk["tre_dk_max_ms"] <= 21.0
    assert tk["buoc_moi_nhip_max"] == 4 and tk["tinh_moi_buoc_p50_us"] == 20.0 and tk["lagging_nhip"] == 0
    assert tk["xu_ly_max_ms"] == pytest.approx(0.38)
    # 16,4 ms thật mà real_dt chỉ 16 ms (QElapsedTimer cắt phần lẻ): trôi 0,4 / 16,4 = 2,44 %, phiên chậm đúng bấy nhiêu
    tk = _thong_ke([16.4] * 200)
    assert tk["troi_lam_tron_pct"] == pytest.approx(100 * 0.4 / 16.4, abs=0.2)
    assert tk["ty_le_phien"] == pytest.approx(1 - tk["troi_lam_tron_pct"] / 100, abs=0.005)
    assert tk["mat_chan_s"] == 0.0 and tk["nhip_gd_bi_chan"] == 0 and tk["khoang_dk_max_ms"] <= 34.0
    assert tk["tre_dk_max_ms"] > 60.0                       # trễ so với lịch lý tưởng gồm cả phần trôi (200 × 0,4 ms)


def test_thong_ke_nhip_khoang_dai_bi_chan_qua_han_va_watchdog():
    tk = _thong_ke([16.0] * 100 + [350.0] + [16.0] * 100)
    assert tk["nhip_gd_bi_chan"] == 1 and tk["mat_chan_s"] == pytest.approx(0.25)
    assert tk["nhip_gd_max_ms"] == 350.0 and tk["khoang_dk_tren_han"] >= 1 and tk["khoang_dk_tren_watchdog"] == 0
    assert 350.0 <= tk["khoang_dk_max_ms"] <= 350.0 + 33.0
    assert tk["tre_dk_max_ms"] >= 250.0                     # sau khoảng dài, mọi nhịp trễ thêm ≈ 250 ms
    assert tk["ty_le_phien"] == pytest.approx((3200 + 100) / (3200 + 350), abs=0.003)
    tk = _thong_ke([16.0] * 100 + [600.0] + [16.0] * 100, rt=2.0)
    assert tk["khoang_dk_tren_watchdog"] == 1 and tk["mat_chan_s"] == pytest.approx(2.0 * 0.5)
    # khoảng dài lúc phiên đang dừng (STOPPING) không tính vào khoảng điều khiển
    tk = _thong_ke([16.0] * 100 + [350.0] + [16.0] * 20, buoc_dung=320)
    assert tk["so_nhip_dk_dung"] > 0 and tk["khoang_dk_tren_han"] == 0 and tk["khoang_dk_max_ms"] <= 33.0
    assert tk["so_nhip_dk"] == tk["so_nhip_dk_ly_thuyet"] == 80 and tk["nhip_gd_bi_chan"] == 1


def test_thong_ke_nhip_rong_va_mot_nhip():
    for chuoi in (None, {}, ec._chuoi_rong()):
        tk = ec.thong_ke_nhip(chuoi, rt=None, tg_tuong_s=None, tg_phien_s=None)
        assert set(tk) == set(ec.KHOA_THONG_KE) and all(v is None for v in tk.values()), chuoi
    mot = {"gd": {"w_us": [16000], "dt_ms": [16], "buoc": [3], "dk": [1], "xu_ly_us": [400], "tinh_us": [60],
                  "lagging": []}, "dk": {"w_us": [16001], "buoc": [0], "dung": []}}
    tk = ec.thong_ke_nhip(mot, rt=1.0, tg_tuong_s=0.016, tg_phien_s=0.015)
    assert set(tk) == set(ec.KHOA_THONG_KE)
    assert (tk["so_nhip_gd"], tk["tre_nhip_dau_ms"], tk["nhip_gd_bi_chan"]) == (1, 16.0, 0)
    assert tk["nhip_gd_p50_ms"] is None and tk["troi_lam_tron_pct"] is None and tk["khoang_dk_max_ms"] is None
    assert (tk["so_nhip_dk"], tk["so_nhip_dk_ly_thuyet"], tk["tre_dk_max_ms"]) == (1, 1, 16.001)
    assert tk["tinh_moi_buoc_p50_us"] == 20.0 and tk["ty_le_phien"] == pytest.approx(0.015 / 0.016)
    tk = ec.thong_ke_nhip(mot, rt=float("nan"), tg_tuong_s=0.0, tg_phien_s=None)     # rt hỏng: không chia, không ném
    assert tk["ty_le_phien"] is None and tk["mat_chan_s"] is None and tk["tre_dk_max_ms"] is None


# ------------------------------------------------------------------------------------------- lý do loại, tóm tắt

_MAY_CHAY = {
    "che_do": "chay", "kich_ban": "kich_ban_bai_do_xe.json", "kich_ban_lech": 0.0, "nhanh": ["SIM", "VEHICLE_IO"],
    "bat_dau": "02/10/2026 09:00:00", "ket_thuc": "02/10/2026 09:16:00", "nhip_ms": 16, "rt": 1.0,
    "git": {"commit": "abc1234", "so_tep_chua_commit": 0},
    "cpu": {"logic": 32, "lop": {"1": list(range(16)), "0": list(range(16, 32))}},
    "nguon": {"ke_hoach": {"guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", "ten": "High performance"}},
    "lenh": "python -X utf8 -m autopark.evaluation.ecoqos_gui do-chay --ra x",
    "khoi_tien_trinh": [
        {"khoi": 0, "bien_the": "gui_system", "nhanh": "SIM", "dieu_tiet": {"ecoqos": "system", "dong_ho": "system"},
         "cach_tat": None},
        {"khoi": 0, "bien_the": "gui_off", "nhanh": "SIM", "dieu_tiet": {"ecoqos": "off", "dong_ho": "system"},
         "cach_tat": "theo_pid"}],
}
_TRUOC = {"thuong": "giao_dien", "thu_nho": "trung_tinh", "bi_che": "man_che"}


def _dong_chay(bien_the: str, trang_thai: str, *, nhanh: str = "SIM", lan: int = 1, tinh: float = 20.0,
               p95: float = 16.6, dk_max: float = 33.0, tren_han: int = 0, mat: float = 0.0,
               ket_qua: str = "COMPLETED", **ghi_de) -> dict:
    """Một dòng chế độ chạy hợp lệ (đủ khóa COT_CHAY), đổi bằng `ghi_de`."""
    d = dict.fromkeys(ec.COT_CHAY)
    d.update(thoi_diem="09:00:00", khoi=0, bien_the=bien_the, nhanh=nhanh, pid=100, lan=lan, khoi_dong=(lan == 0),
             trang_thai=trang_thai, ecoqos="system" if bien_the == "gui_system" else "off",
             dong_ho="ton_trong" if bien_the == "gui_off_dh" else "system", uu_tien="normal", phan_giai_ms=0.5,
             phien="mo", ket_noi="active", ban_lam_viec="Default", man_hinh="bat", vang_s=100.0, phien_sau="mo",
             man_hinh_sau="bat", vang_s_sau=125.0, cua_so_truoc=_TRUOC[trang_thai],
             gui_thu_nho=trang_thai == "thu_nho", gui_hien=trang_thai != "thu_nho",
             gui_lo_ra=1.0 if trang_thai == "thuong" else (0.0 if trang_thai == "bi_che" else None),
             che_kin=True if trang_thai == "bi_che" else None, mau_n=21, mau_sai=0, lap_lai_duong=False,
             ket_qua=ket_qua, dung_boi_cong_cu=ket_qua == "KHONG_XONG", rt=1.0, tg_tuong_s=21.7, tg_phien_s=21.0,
             ty_le_phien=0.968, mat_chan_s=mat, troi_lam_tron_pct=3.1, tre_nhip_dau_ms=16.0, so_nhip_gd=1300,
             nhip_gd_p50_ms=16.0, nhip_gd_p95_ms=p95, nhip_gd_p99_ms=p95 + 1.0, nhip_gd_max_ms=max(33.0, dk_max),
             nhip_gd_bi_chan=0, tinh_moi_buoc_p50_us=tinh, tinh_moi_buoc_p95_us=tinh * 1.2, lagging_nhip=0,
             so_nhip_dk=1050, so_nhip_dk_ly_thuyet=1050, so_nhip_dk_dung=0, khoang_dk_max_ms=dk_max,
             khoang_dk_tren_han=tren_han, khoang_dk_tren_watchdog=0, tre_dk_p95_ms=40.0, cung_ket_qua_moc=True,
             lech_moc=0.0, tai_nen_pct=2.0, cpu_ty_le=0.12, ty_le_e=0.1, ghi_chu="", thong_diep="Đỗ xong")
    d.update(ghi_de)
    return d


def _hai(bien_the: str, trang_thai: str, **kw) -> list[dict]:
    return [_dong_chay(bien_the, trang_thai, lan=i + 1, **kw) for i in range(2)]


def _dong_ket_luan(van_ban: str, dau: str) -> str:
    return next(d for d in van_ban.splitlines() if d.startswith(dau))


def test_ly_do_loai_luot_chay():
    assert eg.ly_do_loai(_dong_chay("gui_system", "thu_nho")) is None
    assert eg.ly_do_loai(_dong_chay("gui_system", "thu_nho", mau_sai=1)) == "doi_trang_thai_trong_chay"
    assert eg.ly_do_loai(_dong_chay("gui_system", "thuong", ghi_chu="khong_giu_duoc_ecoqos")) == "khong_giu_duoc_ecoqos"
    assert eg.ly_do_loai(_dong_chay("gui_off_dh", "bi_che", ghi_chu="khong_tat_duoc_ecoqos")) == "khong_tat_duoc_ecoqos"
    assert eg.ly_do_loai(_dong_chay("gui_system", "thu_nho", ket_qua="KHONG_XONG")) is None      # một phát hiện
    assert eg.ly_do_loai(_dong_chay("gui_system", "thuong", lan=0, mau_sai=3)) == "khoi_dong"       # loại trước tiên
    assert eg.ly_do_loai(_dong_chay("gui_system", "thu_nho", ket_qua="KHONG_TRA_LOI")) == "khong_tra_loi"
    assert eg.ly_do_loai(_dong_chay("gui_system", "thu_nho", cua_so_truoc="giao_dien", mau_sai=2)) == \
        "gui_van_o_truoc"
    assert eg.LY_DO.index("doi_trang_thai_trong_chay") == eg.LY_DO.index("gui_khong_o_truoc") + 1
    assert eg.LY_DO.index("khong_giu_duoc_ecoqos") == eg.LY_DO.index("khong_tat_duoc_ecoqos") + 1


def test_tom_tat_chay_thu_nho_cham_ro_va_het_khi_tat_ecoqos():
    dong = (_hai("gui_system", "thuong")
            + _hai("gui_system", "thu_nho", tinh=40.0, p95=31.0, dk_max=312.0, tren_han=3, mat=0.42)
            + _hai("gui_system", "bi_che") + [r for tt in eg.TRANG_THAI for r in _hai("gui_off", tt)]
            + [_dong_chay("gui_system", "thuong", lan=0)])
    van_ban = ec.tom_tat_chay(dong, _MAY_CHAY)
    thu_nho = _dong_ket_luan(van_ban, "- SIM, thu_nho:")
    assert thu_nho.startswith("- SIM, thu_nho: chậm rõ (tính/bước hệ số 2,00; nhịp giao diện p95 hệ số 1,87; khoảng ĐK "
                              "lớn nhất 312 ms; 6 khoảng ĐK > 0,15 s; mất 0,42 s phiên do chặn 0,1 s; COMPLETED 2/2 "
                              "lượt hợp lệ; mốc COMPLETED 2/2)"), thu_nho
    assert "tính/bước: Windows hạ tốc tiến trình (tắt EcoQoS thì hết: gui_off tính/bước hệ số 1,00" in thu_nho
    assert "nhịp giao diện: Windows hạ tốc tiến trình (tắt EcoQoS thì hết: gui_off nhịp p95 hệ số 1,00" in thu_nho
    assert "không thấy chậm" in _dong_ket_luan(van_ban, "- SIM, bi_che:")
    assert "KẾT LUẬN: KHÔNG KẾT LUẬN" not in van_ban and "khoi_dong 1" in _dong_ket_luan(van_ban, "Lượt bị loại")
    assert "thường 33, thu nhỏ 312, bị che 33 ms" in _dong_ket_luan(van_ban, "- Hệ quả (SUY RA)")
    assert "- VEHICLE_IO: KHÔNG KẾT LUẬN" in van_ban                    # nhánh có trong may.json mà không có lượt
    bang = _dong_ket_luan(van_ban, "SIM        gui_system  thu_nho")
    assert "2/2" in bang and "COMPLETED 2" in bang and "16,0/31,0/312" in bang
    assert "EcoQoS từng khối (đọc lại sau khi đặt biến thể): gui_system: ecoqos system, đồng hồ system " \
           "(AUTOPARK_KEEP_ECOQOS=1); gui_off: ecoqos off, đồng hồ system, cách tắt theo_pid" in van_ban


def test_tom_tat_chay_do_phan_giai_dong_ho():
    dong = (_hai("gui_system", "thuong") + _hai("gui_system", "thu_nho", p95=33.2)
            + _hai("gui_off", "thuong") + _hai("gui_off", "thu_nho", p95=33.2)
            + _hai("gui_off_dh", "thuong") + _hai("gui_off_dh", "thu_nho"))
    thu_nho = _dong_ket_luan(ec.tom_tat_chay(dong, _MAY_CHAY), "- SIM, thu_nho:")
    assert "chậm rõ (tính/bước hệ số 1,00; nhịp giao diện p95 hệ số 2,00" in thu_nho and "tính/bước:" not in thu_nho
    assert ("nhịp giao diện: do Windows bỏ qua độ phân giải đồng hồ khi cửa sổ ẩn (tắt EcoQoS chưa đủ; luôn tôn trọng "
            "độ phân giải đồng hồ thì hết") in thu_nho
    # gui_off_dh cũng chậm: không phải (chỉ) do EcoQoS; chưa đo gui_off_dh: nói rõ
    dong_dh = [d | {"nhip_gd_p95_ms": 33.2} if d["bien_the"] == "gui_off_dh" and d["trang_thai"] == "thu_nho" else d
               for d in dong]
    assert "luôn tôn trọng độ phân giải đồng hồ cũng vẫn chậm" in \
        _dong_ket_luan(ec.tom_tat_chay(dong_dh, _MAY_CHAY), "- SIM, thu_nho:")
    khong_dh = [d for d in dong if d["bien_the"] != "gui_off_dh"]
    assert "chưa đo gui_off_dh (đo lại với --bien-the gui_off,gui_off_dh)" in \
        _dong_ket_luan(ec.tom_tat_chay(khong_dh, _MAY_CHAY), "- SIM, thu_nho:")


def test_tom_tat_chay_khong_du_va_khong_ket_luan_khi_phien_khoa():
    dong = [_dong_chay("gui_system", "thuong"), _dong_chay("gui_system", "thu_nho", tinh=60.0)]
    thu_nho = _dong_ket_luan(ec.tom_tat_chay(dong, _MAY_CHAY), "- SIM, thu_nho:")
    assert "không đủ lượt hợp lệ để so" in thu_nho and "cần ≥ 2 lượt mỗi bên" in thu_nho and "chậm" not in thu_nho
    khoa = [r | {"phien": "khoa", "phien_sau": "khoa", "ban_lam_viec": ""}
            for tt in eg.TRANG_THAI for r in _hai("gui_system", tt)]
    van_ban = ec.tom_tat_chay(khoa, _MAY_CHAY)
    assert "KẾT LUẬN: KHÔNG KẾT LUẬN" in van_ban and eg.GIAI_THICH_KHOA in van_ban and "chậm rõ" not in van_ban
    assert f"phien_khoa {len(khoa)}" in _dong_ket_luan(van_ban, "Lượt bị loại")
    assert ec.tom_tat_chay([], _MAY_CHAY).endswith("Chưa có lần đo nào.\n")


def test_tom_tat_chay_khong_xong_la_cham_va_bao_ket_qua_khac_moc():
    dong = (_hai("gui_system", "thuong") + [_dong_chay("gui_system", "thu_nho", lan=1),
                                            _dong_chay("gui_system", "thu_nho", lan=2, ket_qua="KHONG_XONG",
                                                       cung_ket_qua_moc=None, lech_moc=None)]
            + [_dong_chay("gui_system", "bi_che", lan=3, cung_ket_qua_moc=False, lech_moc=0.0123),
               _dong_chay("gui_system", "bi_che", lan=4, lagging_nhip=2)])
    van_ban = ec.tom_tat_chay(dong, _MAY_CHAY)
    thu_nho = _dong_ket_luan(van_ban, "- SIM, thu_nho:")
    assert thu_nho.startswith("- SIM, thu_nho: chậm rõ (") and "COMPLETED 1/2 (KHONG_XONG 1) lượt hợp lệ" in thu_nho
    assert "nhịp giao diện: chưa đủ lượt gui_off hợp lệ để tách" in thu_nho
    assert "Kết quả giống lượt khởi động cùng tiến trình: 4/5" in van_ban
    assert _dong_ket_luan(van_ban, "CẢNH BÁO: 1 lượt cho kết quả khác").endswith("khối 0 gui_system SIM lần 3")
    assert _dong_ket_luan(van_ban, "- lagging:").startswith("- lagging: 2 nhịp")
    assert "thường 0,968, thu nhỏ 0,968, bị che 0,968" in _dong_ket_luan(van_ban, "- Thời gian phiên / đồng hồ thật")


# ---------------------------------------------------------------------------------- một lượt (đồ giả, đồng hồ giả)

class DongHoGia:
    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _kq_chay_gia(yeu_cau: str, chuoi_buoc: tuple[dict, int], *, nhanh: str = "SIM", dung: bool = False) -> dict:
    """Thông điệp ket_qua_chay giả (đủ khóa như `DauDoChay._ket_thuc`) từ một chuỗi `_chuoi_gia`."""
    chuoi, buoc = chuoi_buoc
    return {"loai": "ket_qua_chay", "yeu_cau": yeu_cau, "lan": 0, "nhanh": nhanh,
            "ket_qua": "STOPPED" if dung else "COMPLETED", "ly_do": "Người dùng yêu cầu dừng" if dung else "Đỗ xong",
            "ma_su_kien": [], "dung_boi_cong_cu": dung, "rt": 1.0, "nhip_ms": 16, "t_bat_dau": 5.0,
            "t_ket_thuc": 5.0 + sum(chuoi["gd"]["dt_ms"]) / 1000, "tg_phien_s": buoc * 0.005,
            "bao_cao": {"completed": not dung, "collided": False, "sim_time": buoc * 0.005, "distance": 0.5,
                        "position_error": 0.004, "heading_error": 0.01, "path_finished": not dung},
            "cuoi": [2.0, 1.0, 0.0, 0.0, 0.0], "van_tay_duong": "abc123def456",
            "vehicle_io": None if nhanh == "SIM" else {"lenh_gui": 300, "telemetry_nhan": 60, "trang_thai_bo": "RUNNING",
                                                       "ma_dung": []},
            "chuoi": chuoi, "dieu_tiet": {"ecoqos": "system", "dong_ho": "system"}}


class FakeConChay:
    """Tiến trình giao diện giả của chế độ chạy. `cap_quyen` / `len_truoc` theo bàn làm việc giả `ban`; `chuan_bi` trả
    `san_sang`; `plan` lập đường OK; `chay` bắt đầu; ket_qua_chay tới sau `tg_chay` giây đồng hồ giả (None: chỉ khi
    bị dừng, và chỉ khi `dung_duoc`). `doc` không có gì thì tiến đồng hồ giả đúng `het_han`. `khi_doc(i)` gọi trước lần
    đọc thứ i (từ 1) trong lúc chạy."""

    pid = 4242
    con_song = True

    def __init__(self, nhat_ky: list, dong_ho: DongHoGia, *, ban=None, san_sang: bool = True,
                 tg_chay: float | None = 3.0, dung_duoc: bool = True, khi_doc=None, chuoi=None):
        self.nhat_ky, self.dong_ho, self.ban, self.san_sang = nhat_ky, dong_ho, ban, san_sang
        self.tg_chay, self.dung_duoc, self.khi_doc = tg_chay, dung_duoc, khi_doc
        self.chuoi = chuoi or _chuoi_gia([16.0] * 60)
        self._tin: list[dict] = []
        self._chay: tuple[str, float] | None = None
        self._dung = False
        self._lan_doc = 0

    def gui(self, lenh: str) -> bool:
        self.nhat_ky.append(("con.gui", lenh))
        ten, yc = eg._tach_lenh(lenh)
        if ten == "cap_quyen":
            ok, loi = self.ban.cap_quyen("con") if self.ban else (True, 0)
            self._tin.append({"loai": "cap_quyen", "yeu_cau": yc, "ok": ok, "loi": loi})
        elif ten == "len_truoc":
            ok = self.ban.dat_truoc("con", "giao_dien") if self.ban else True
            self._tin.append({"loai": "len_truoc", "yeu_cau": yc, "ok": ok, "truoc_hwnd": None})
        elif ten == "chuan_bi":
            self._tin.append({"loai": "chuan_bi", "yeu_cau": yc, "trang_thai_phien": "READY" if self.san_sang
                              else "EDITING", "san_sang": self.san_sang, "co_duong": self.san_sang})
        elif ten == "plan":
            self.san_sang = True
            self._tin.append({"loai": "ket_qua", "yeu_cau": yc, "lan": 0, "ket_qua": "OK", "thong_diep": "Tìm được"})
        elif ten == "chay":
            self._chay = (yc, self.dong_ho())
            self._tin.append({"loai": "bat_dau_chay", "yeu_cau": yc, "lan": 0, "nhanh": "SIM", "rt": 1.0,
                              "t_bam": 4.99, "t_bat_dau": 5.0, "tg_khoi_dong_ms": 10.0})
        elif ten == "dung":
            self._dung = True
            self._tin.append({"loai": "dung", "yeu_cau": yc, "ok": True})
        return True

    def doc(self, het_han, loai, yeu_cau=None):
        self.nhat_ky.append(("con.doc", yeu_cau))
        muon = {loai} if isinstance(loai, str) else set(loai)
        for i, tin in enumerate(self._tin):
            if tin["loai"] in muon and (yeu_cau is None or tin.get("yeu_cau") == yeu_cau):
                return self._tin.pop(i)
        if "ket_qua_chay" in muon and self._chay is not None:
            self._lan_doc += 1
            if self.khi_doc is not None:
                self.khi_doc(self._lan_doc)
            yc, t_chay = self._chay
            xong = (self.tg_chay is not None and self.dong_ho() + het_han >= t_chay + self.tg_chay) or \
                   (self._dung and self.dung_duoc)
            if xong:
                self.dong_ho.t = max(self.dong_ho.t, t_chay + (self.tg_chay or 0.0))
                self._chay = None
                return _kq_chay_gia(yc, self.chuoi, dung=self._dung)
        self.dong_ho.t += het_han
        return None


def _ngu_canh_chay(nhat_ky: list, gui, che, dong_ho: DongHoGia, *, ban: BanLamViecGia, han: float = 180.0,
                   ghi_chuoi=None) -> ec.NguCanhChay:
    vang = iter([100.0, 130.0] * 4)
    chup = iter([_chup(0.0, [0.0, 0.0], [0.0, 0.0]), _chup(3.0, [0.1, 0.0], [2.9, 3.0]),
                 _chup(7.0, [0.6, 0.4], [6.4, 6.6])] * 4)
    cpu = iter([10.0, 10.5] * 4)

    def doc_may() -> TrangThaiMay:
        pid, hwnd, exe = ban.doc_truoc()
        return TrangThaiMay("mo", "active", "Default", "bat", next(vang), pid, hwnd, exe)

    return ec.NguCanhChay(doc_may=doc_may, doc_truoc=ban.doc_truoc, chup_cpu=lambda: next(chup),
                          ecoqos_cua=lambda pid: "system", uu_tien_cua=lambda pid: "normal",
                          cpu_cua=lambda pid: next(cpu), ngu=lambda s: nhat_ky.append(("ngu", s)), gui=gui, che=che,
                          cho=5.0, khoi=1, bien_the="gui_system", lop_cpu={1: [0], 0: [1]}, nhanh="SIM",
                          han_chay_s=han, dong_ho=dong_ho,
                          doc_dieu_tiet=lambda pid: {"ecoqos": "system", "dong_ho": "system"},
                          doc_phan_giai=lambda: (15.625, 0.5, 0.5), ghi_chuoi=ghi_chuoi)


def _bo_gia(nhat_ky: list, **kw) -> tuple:
    ban, dong_ho = BanLamViecGia("giao_dien"), DongHoGia()
    con = FakeConChay(nhat_ky, dong_ho, ban=ban, **kw)
    return con, FakeCuaSo(nhat_ky, ban), FakeManChe(nhat_ky, ban), ban, dong_ho


def test_do_mot_lan_chay_voi_do_gia():
    nhat_ky: list = []
    luu: list = []
    con, gui, che, ban, dong_ho = _bo_gia(nhat_ky)
    nc = _ngu_canh_chay(nhat_ky, gui, che, dong_ho, ban=ban,
                        ghi_chuoi=lambda ten, du_lieu: (luu.append((ten, du_lieu)), f"nhip/{ten}.json.gz")[1])
    dong = ec.do_mot_lan_chay(con, 3, "thu_nho", nc)
    assert list(dong) == list(ec.COT_CHAY)
    i_chuan_bi, i_chay = nhat_ky.index(("con.gui", "chuan_bi c3")), nhat_ky.index(("con.gui", "chay 3"))
    assert (i_chuan_bi < nhat_ky.index(("che.len_truoc", "trung_tinh")) < nhat_ky.index("gui.thu_nho")
            < nhat_ky.index(("ngu", 3.0)) < nhat_ky.index(("ngu", 2.0)) < i_chay)
    assert ("con.gui", "plan p3") not in nhat_ky and dong["lap_lai_duong"] is False
    assert (dong["ket_qua"], dong["khoi_dong"], dong["nhanh"], dong["ecoqos"], dong["dong_ho"]) == \
        ("COMPLETED", False, "SIM", "system", "system")
    assert (dong["cua_so_truoc"], dong["gui_thu_nho"], dong["phan_giai_ms"]) == ("trung_tinh", True, 0.5)
    assert (dong["so_nhip_gd"], dong["nhip_gd_p50_ms"], dong["tg_tuong_s"], dong["rt"]) == (60, 16.0, 0.96, 1.0)
    assert dong["so_nhip_dk"] == dong["so_nhip_dk_ly_thuyet"] and dong["ty_le_phien"] == pytest.approx(1.0, abs=0.01)
    assert (dong["mau_n"], dong["mau_sai"], dong["mau_sai_dau"]) == (2, 0, None)
    assert (dong["sai_vi_tri_cm"], dong["quang_duong_m"], dong["cung_ket_qua_moc"]) == (0.4, 0.5, None)
    assert dong["cpu_tien_trinh_s"] == 0.5 and dong["cpu_ty_le"] == pytest.approx(0.5 / 0.96, abs=1e-3)
    assert dong["tep_chuoi"] == "nhip/k1_gui_system_SIM_l03_thu_nho.json.gz" and eg.ly_do_loai(dong) is None
    ten, du_lieu = luu[0]
    assert du_lieu["chuoi"] == con.chuoi[0] and len(du_lieu["mau"]) == 2 and du_lieu["khoa"]["lan"] == 3
    # mốc kiểm tính xác định: cùng kết quả → True; khác vân tay đường (đã lập lại) → không so
    moc = ec.moc_tu_dong(dong, nc.kq_gan_nhat)
    assert moc is not None and ec.so_moc(nc.kq_gan_nhat, moc) == (True, 0.0)
    khac = nc.kq_gan_nhat | {"cuoi": [2.0, 1.0001, 0.0, 0.0, 0.0]}
    assert ec.so_moc(khac, moc)[0] is False and ec.so_moc(khac | {"van_tay_duong": "khac"}, moc) == (None, None)

    # chưa có đường: về "thường", lập đường, rồi mới đổi sang trạng thái đo
    nhat_ky.clear()
    con, gui, che, ban, dong_ho = _bo_gia(nhat_ky, san_sang=False)
    dong = ec.do_mot_lan_chay(con, 4, "bi_che", _ngu_canh_chay(nhat_ky, gui, che, dong_ho, ban=ban))
    assert (nhat_ky.index("gui.khoi_phuc") < nhat_ky.index(("con.gui", "plan p4")) < nhat_ky.index("che.hien")
            < nhat_ky.index(("con.gui", "chay 4")))
    assert dong["lap_lai_duong"] is True and "lap_lai_duong" in dong["ghi_chu"] and dong["ket_qua"] == "COMPLETED"
    assert dong["che_kin"] is True and dong["cua_so_truoc"] == "man_che" and eg.ly_do_loai(dong) is None

    # một mẫu sai giữa lượt (giao diện lên trước ở mẫu thứ hai): lượt bị loại
    nhat_ky.clear()

    def len_truoc(i: int) -> None:
        ban.truoc = "giao_dien" if i == 2 else "trung_tinh"

    con, gui, che, ban, dong_ho = _bo_gia(nhat_ky, khi_doc=len_truoc)
    dong = ec.do_mot_lan_chay(con, 5, "thu_nho", _ngu_canh_chay(nhat_ky, gui, che, dong_ho, ban=ban))
    assert (dong["mau_n"], dong["mau_sai"], dong["mau_sai_dau"]) == (2, 1, "t=2,0 s: truoc:giao_dien")
    assert eg.ly_do_loai(dong) == "doi_trang_thai_trong_chay"


def test_do_mot_lan_chay_qua_han_bam_dung_va_khong_dung_duoc():
    nhat_ky: list = []
    con, gui, che, ban, dong_ho = _bo_gia(nhat_ky, tg_chay=None, chuoi=_chuoi_gia([16.0] * 30, buoc_dung=60))
    dong = ec.do_mot_lan_chay(con, 2, "thuong", _ngu_canh_chay(nhat_ky, gui, che, dong_ho, ban=ban, han=2.5))
    assert ("con.gui", "dung d2") in nhat_ky and nhat_ky.count(("con.gui", "dung d2")) == 1
    assert (dong["ket_qua"], dong["dung_boi_cong_cu"], dong["so_nhip_gd"]) == ("KHONG_XONG", True, 30)
    assert dong["so_nhip_dk_dung"] > 0 and dong["cung_ket_qua_moc"] is None and eg.ly_do_loai(dong) is None
    # không bao giờ có kết quả, kể cả sau khi bấm Dừng: KHONG_TRA_LOI, khối dừng sớm
    nhat_ky.clear()
    con, gui, che, ban, dong_ho = _bo_gia(nhat_ky, tg_chay=None, dung_duoc=False)
    t0 = dong_ho()
    dong = ec.do_mot_lan_chay(con, 3, "thuong", _ngu_canh_chay(nhat_ky, gui, che, dong_ho, ban=ban, han=2.5))
    assert list(dong) == list(ec.COT_CHAY) and dong["ket_qua"] == "KHONG_TRA_LOI"
    assert "khong_dung_duoc" in dong["ghi_chu"] and eg.ly_do_loai(dong) == "khong_tra_loi"
    assert dong_ho() - t0 == pytest.approx(2.5 + ec.CHO_DUNG_S, abs=1.0)
    # đầu dò từ chối bấm (ví dụ đường vượt giới hạn đổi chiều): BO_QUA, không chờ
    nhat_ky.clear()
    con, gui, che, ban, dong_ho = _bo_gia(nhat_ky)
    con.gui = lambda lenh, _goc=con.gui: (con._tin.append({"loai": "loi", "yeu_cau": "4", "thong_diep": "T12"})
                                         if lenh == "chay 4" else _goc(lenh)) or True
    dong = ec.do_mot_lan_chay(con, 4, "thuong", _ngu_canh_chay(nhat_ky, gui, che, dong_ho, ban=ban))
    assert (dong["ket_qua"], dong["thong_diep"]) == ("BO_QUA", "T12") and "dau_do_tu_choi" in dong["ghi_chu"]


def test_ghi_chuoi_nen_doc_lai_va_xac_dinh(tmp_path):
    du_lieu = {"khoa": {"lan": 1}, "chuoi": _chuoi_gia([16.0] * 20)[0], "mau": [{"t": 1.0, "sai": None}],
               "nan": float("nan")}
    a = ec.ghi_chuoi(tmp_path / "a", "k0_gui_system_SIM_l01_thuong", du_lieu)
    b = ec.ghi_chuoi(tmp_path / "b", "k0_gui_system_SIM_l01_thuong", du_lieu)
    assert a == b == "nhip/k0_gui_system_SIM_l01_thuong.json.gz"
    raw = (tmp_path / "a" / a).read_bytes()
    assert raw == (tmp_path / "b" / b).read_bytes()                   # gzip mtime = 0: cùng dữ liệu, cùng byte
    lai = json.loads(gzip.decompress(raw))
    assert lai["chuoi"] == du_lieu["chuoi"] and lai["nan"] is None and lai["mau"] == du_lieu["mau"]


# -------------------------------------------------------------------------------- đầu dò trong cửa sổ thật (offscreen)

def _phien_thang(scenario, cfg, x_dich: float = 2.0):
    from autopark.application.session import Session
    from autopark.domain.types import ParkingGoal, Pose

    scenario.obstacles = []
    scenario.start = Pose(0.5, 1.0, 0.0)
    scenario.goal = ParkingGoal(Pose(x_dich, 1.0, 0.0))
    return Session(scenario, cfg)


@pytest.fixture
def cua_so_thang(qapp, monkeypatch, scenario, cfg, tmp_path):
    """MainWindow quanh một phiên đường thẳng; liệt kê cổng COM làm hỏng test; hộp thoại của test ghi lại; thư mục dấu
    đồng bộ trỏ vào tmp_path (lần chạy không được ghi tệp nào ở đó: không có dấu nào)."""
    from autopark.planning import portfolio
    from autopark.ui import main_window

    monkeypatch.setattr(portfolio, "plan", portfolio.plan)            # lớp bọc ghi_nac luôn được gỡ
    monkeypatch.setattr(main_window, "list_serial_ports", lambda: pytest.fail("không được liệt kê cổng COM"))
    hop_thoai: list = []
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *a, **k: hop_thoai.append(a[1:]))
    window = main_window.MainWindow(_phien_thang(scenario, cfg))
    for ten in ("_refresh_ports", "_probe_board", "_clear_board_fault"):   # đầu dò không bao giờ chạm bo / cổng
        setattr(window, ten, lambda *a, _ten=ten, **k: pytest.fail(f"đầu dò không được gọi {_ten}"))
    window.sync_dir = tmp_path / "sync_marks"
    window.hop_thoai_test = hop_thoai
    yield window
    window.close()


def _kiem_chuoi(kq: dict) -> dict:
    gd, dk = kq["chuoi"]["gd"], kq["chuoi"]["dk"]
    assert len(dk["w_us"]) > 10 and sum(gd["dk"]) == len(dk["w_us"])
    assert all(len(v) == len(gd["w_us"]) for k, v in gd.items() if k != "lagging")
    assert gd["w_us"] == sorted(gd["w_us"]) and dk["w_us"] == sorted(dk["w_us"]) and gd["w_us"][0] >= 0
    assert all(b % 4 == 0 for b in dk["buoc"]) and dk["buoc"] == sorted(dk["buoc"])
    assert sum(gd["buoc"]) == round(kq["tg_phien_s"] / 0.005)
    tk = ec.thong_ke_nhip(kq["chuoi"], rt=kq["rt"], tg_tuong_s=kq["t_ket_thuc"] - kq["t_bat_dau"],
                          tg_phien_s=kq["tg_phien_s"])
    assert tk["so_nhip_dk"] == tk["so_nhip_dk_ly_thuyet"] and tk["lagging_nhip"] == 0
    assert tk["tinh_moi_buoc_p50_us"] > 0 and tk["nhip_gd_p50_ms"] > 0 and 0 < tk["ty_le_phien"] <= 1.05
    return tk


def test_dau_do_chay_qua_cua_so_that_sim_va_bo_mo_phong(cua_so_thang):
    from autopark.application.session import SessionState
    from autopark.ui.main_window import MainWindow
    from PySide6.QtWidgets import QMessageBox

    window = cua_so_thang
    window.spin_rt.setValue(8.0)
    gia = vars(QMessageBox)["warning"]                               # hàm ghi lại của test (cua_so_thang)
    tin: list[dict] = []
    dau_do = eg.DauDoKeHoach(window, tin.append)
    go_nac = eg.ghi_nac(dau_do.nhan_nac)
    dd = ec.DauDoChay(window, tin.append)
    try:
        assert dd.xu_ly("chuan_bi c0")
        assert tin[-1] == {"loai": "chuan_bi", "yeu_cau": "c0", "trang_thai_phien": "EDITING", "san_sang": False,
                           "co_duong": False}
        assert not dd.xu_ly("plan p0")                               # lệnh lập đường là của DauDoKeHoach
        dau_do.xu_ly("plan p0")
        _bom(window, tin, 2)
        assert (tin[-1]["loai"], tin[-1]["ket_qua"], tin[-1]["yeu_cau"]) == ("ket_qua", "OK", "p0")
        dd.xu_ly("chuan_bi c1")
        assert tin[-1]["san_sang"] is True and tin[-1]["trang_thai_phien"] == "READY"
        dd.xu_ly("chay 1")
        bat_dau = tin[-1]
        assert (bat_dau["loai"], bat_dau["yeu_cau"], bat_dau["nhanh"], bat_dau["rt"]) == \
            ("bat_dau_chay", "1", "SIM", 8.0)
        assert bat_dau["t_bat_dau"] >= bat_dau["t_bam"] and window.session.state == SessionState.RUNNING
        _bom(window, tin, len(tin) + 1)
        kq = tin[-1]
        assert (kq["loai"], kq["ket_qua"], kq["yeu_cau"], kq["dung_boi_cong_cu"], kq["vehicle_io"]) == \
            ("ket_qua_chay", "COMPLETED", "1", False, None)
        assert kq["bao_cao"]["completed"] is True and len(kq["cuoi"]) == 5 and len(kq["van_tay_duong"]) == 12
        assert kq["nhip_ms"] == 16 and kq["t_ket_thuc"] > kq["t_bat_dau"]
        tk = _kiem_chuoi(kq)
        assert tk["so_nhip_dk_dung"] == 0                           # đỗ xong khi đang RUNNING: không có STOPPING
        # lần chạy thứ hai từ COMPLETED (Bắt đầu đỗ lại): bước cố định nên ra cùng kết quả
        dd.xu_ly("chuan_bi c2")
        assert tin[-1]["san_sang"] is True
        dd.xu_ly("chay 2")
        _bom(window, tin, len(tin) + 1)
        kq2 = tin[-1]
        assert (kq2["loai"], kq2["lan"]) == ("ket_qua_chay", 1)
        assert (kq2["cuoi"], kq2["van_tay_duong"], kq2["tg_phien_s"]) == (kq["cuoi"], kq["van_tay_duong"],
                                                                         kq["tg_phien_s"])
        assert ec.so_moc(kq2, ec.moc_tu_dong({"lan": 0}, kq)) == (True, 0.0)
        # VehicleIO với bo mô phỏng, chọn như người dùng chọn ở ô nhánh chạy (khi phiên sẵn sàng)
        dd.xu_ly("chuan_bi c3")
        assert tin[-1]["san_sang"] is True
        assert ec.chon_nhanh(window, "VEHICLE_IO") is None and window.board_port() is None
        assert window.session.vehicle_link is not None and not window.session.vehicle_link.realtime
        dd.xu_ly("chay 3")
        assert tin[-1]["loai"] == "bat_dau_chay" and tin[-1]["nhanh"] == "VEHICLE_IO"
        _bom(window, tin, len(tin) + 1)
        kq3 = tin[-1]
        assert (kq3["loai"], kq3["ket_qua"], kq3["nhanh"]) == ("ket_qua_chay", "COMPLETED", "VEHICLE_IO")
        tk3 = _kiem_chuoi(kq3)
        vio = kq3["vehicle_io"]
        assert vio["lenh_gui"] >= tk3["so_nhip_dk"] and vio["telemetry_nhan"] > 0 and vio["ma_dung"] == []
        # trang_thai_bo = VehicleLink.result["board_state"]: khung telemetry cuối nhận được trước khi DISARM được xác
        # nhận (bo mô phỏng trả ACK trước khung kế tiếp, nên thường còn RUNNING); chính bo mô phỏng đã về DISARMED
        from autopark.transport.protocol import State
        assert vio["trang_thai_bo"] in {s.name for s in State}
        assert window.session.run_link.io.firmware.state == State.DISARMED
        # bo mô phỏng cũng chạy theo thời gian phiên và có seed: lần chạy lại ra cùng kết quả
        dd.xu_ly("chuan_bi c4")
        dd.xu_ly("chay 4")
        _bom(window, tin, len(tin) + 1)
        kq4 = tin[-1]
        assert kq4["loai"] == "ket_qua_chay" and kq4["vehicle_io"]["lenh_gui"] == vio["lenh_gui"]
        assert ec.so_moc(kq4, ec.moc_tu_dong({"lan": 0}, kq3)) == (True, 0.0)
        assert dd.hop_thoai == [] and window.hop_thoai_test == []
    finally:
        dd.go()
        go_nac()
    for ten, doi_tuong in (("advance_by", window), ("advance", window.session),
                           ("_step_closed_loop", window.session)):
        assert ten not in vars(doi_tuong)                            # trả lại phương thức của lớp
    assert window.advance_by.__func__ is MainWindow.advance_by
    assert vars(QMessageBox)["warning"] is gia
    assert not window.sync_dir.exists()                              # không tệp dấu đồng bộ nào được ghi


def test_dau_do_chay_tu_choi_khong_mo_hop_thoai(cua_so_thang):
    from autopark.application.session import SessionError, SessionState
    from PySide6.QtWidgets import QMessageBox

    window = cua_so_thang
    window.spin_rt.setValue(8.0)
    gia = vars(QMessageBox)["warning"]                               # hàm ghi lại của test (cua_so_thang)
    tin: list[dict] = []
    dd = ec.DauDoChay(window, tin.append)
    try:
        assert dd.xu_ly("chay 1") and (tin[-1]["loai"], tin[-1]["yeu_cau"]) == ("loi", "1")
        assert "EDITING" in tin[-1]["thong_diep"]
        assert dd.xu_ly("dung 2") and tin[-1] == {"loai": "loi", "yeu_cau": "2",
                                                  "thong_diep": "không có lần chạy nào đang đo"}
        assert not any(dd.xu_ly(lenh) for lenh in ("plan 3", "cap_quyen q1", "len_truoc t1", "thoat"))
        assert window.plan(sync=True).ok
        # run() bị phiên từ chối: hộp thoại được ghi lại (không mở), lệnh trả `loi` kèm nội dung hộp thoại
        def tu_choi() -> None:
            raise SessionError("thử từ chối")

        window.session.start_run = tu_choi
        dd.xu_ly("chay 4")
        del window.session.start_run
        assert tin[-2]["loai"] == "hop_thoai" and tin[-2]["ham"] == "warning"
        assert tin[-1]["loai"] == "loi" and "run() không vào RUNNING (phiên đang READY)" in tin[-1]["thong_diep"]
        assert "Không bắt đầu được: thử từ chối" in tin[-1]["thong_diep"]
        dd.xu_ly("chay 5")
        assert tin[-1]["loai"] == "bat_dau_chay"
        dd.xu_ly("chay 6")
        assert tin[-1]["loai"] == "loi" and "đang đo một lần chạy khác" in tin[-1]["thong_diep"]
        dd.xu_ly("chuan_bi c7")
        assert tin[-1]["loai"] == "loi" and tin[-1]["yeu_cau"] == "c7"
        for _ in range(3):
            window._on_tick()
            time.sleep(0.01)
        dd.xu_ly("dung 8")
        assert tin[-1] == {"loai": "dung", "yeu_cau": "8", "ok": True}
        assert window.session.state == SessionState.STOPPING
        _bom(window, tin, len(tin) + 1)
        kq = tin[-1]
        assert (kq["loai"], kq["ket_qua"], kq["dung_boi_cong_cu"], kq["yeu_cau"]) == ("ket_qua_chay", "STOPPED", True,
                                                                                    "5")
        assert ec.thong_ke_nhip(kq["chuoi"], rt=kq["rt"], tg_tuong_s=1.0, tg_phien_s=1.0)["so_nhip_dk_dung"] > 0
        # chặn hộp thoại: trả Ok / No ngay, ghi lại, không chặn
        assert QMessageBox.warning(window, "Tiêu đề", "Nội dung") == QMessageBox.StandardButton.Ok
        assert QMessageBox.question(window, "Hỏi", "Có không?") == QMessageBox.StandardButton.No
        assert [h["ham"] for h in dd.hop_thoai] == ["warning", "warning", "question"]
        assert tin[-1] == {"loai": "hop_thoai", "ham": "question", "tieu_de": "Hỏi", "noi_dung": "Có không?"}
    finally:
        dd.go()
    assert vars(QMessageBox)["warning"] is gia


def test_on_tick_chan_real_dt_bang_hang_so_cua_cong_cu(qapp):
    """Hằng số CHAN_REAL_DT_S của công cụ phải khớp chặn real_dt trong `MainWindow._on_tick` (không sửa ứng dụng):
    đồng hồ giả trả 5000 ms, nhịp kế tiếp phải gọi advance_by đúng CHAN_REAL_DT_S."""
    from autopark.ui.app import DEFAULT_SCENARIO, build_window

    window = build_window(DEFAULT_SCENARIO)
    try:
        window._start_manual()
        assert window.session.simulating
        goi: list[float] = []
        window.advance_by = goi.append

        class DongHo:
            def restart(self) -> int:
                return 5000

        window._clock = DongHo()
        window._on_tick()
        assert goi == [ec.CHAN_REAL_DT_S]
    finally:
        window.close()


def test_hang_so_khop_ma_nguon():
    from autopark.application.session import Session
    from autopark.transport.firmware_model import FirmwareConfig
    from autopark.transport.vehicle_io import VehicleIO

    assert ec.HAN_LENH_S == inspect.signature(VehicleIO.__init__).parameters["default_validity_s"].default
    assert ec.WATCHDOG_LIEN_LAC_S == FirmwareConfig().link_timeout_ms / 1000
    mac_dinh = inspect.signature(ec.thong_ke_nhip).parameters
    assert (mac_dinh["dt_buoc"].default, mac_dinh["dk_moi"].default) == (Session.PHYSICS_DT, Session.CONTROL_EVERY)
    assert set(ec.KHOA_THONG_KE) <= set(ec.COT_CHAY) and len(set(ec.COT_CHAY)) == len(ec.COT_CHAY)
    assert not hasattr(ec, "main")              # điểm vào duy nhất là ecoqos_gui (mọi `main` đều phải được phân loại)


# ------------------------------------------------------------------------------- tiến trình con thật (offscreen)

def _ghi_kich_ban_thang(thu_muc: Path) -> Path:
    from autopark.domain.types import ParkingGoal, Pose
    from autopark.storage.scenario_store import load_scenario, save_scenario

    kb = load_scenario(eg.PROJECT_ROOT / "scenarios" / "bai_do_xe.json")
    kb.obstacles, kb.slot = [], None
    kb.start, kb.goal = Pose(0.5, 1.0, 0.0), ParkingGoal(Pose(1.2, 1.0, 0.0))
    return save_scenario(kb, Path(thu_muc) / "thang.json")


def test_con_chay_giao_thuc(tmp_path):
    pytest.importorskip("PySide6")
    kich_ban = _ghi_kich_ban_thang(tmp_path)
    nhat_ky: list[str] = []
    p = eg.TienTrinhCon(["con", "--kich-ban", str(kich_ban), "--chay", "--nhanh", "VEHICLE_IO", "--cho-phep-offscreen"],
                        "con", ghi=nhat_ky.append, env=_env_offscreen())
    try:
        ss = p.doc(60.0, ("san_sang", "loi"))
        assert ss is not None and ss["loai"] == "san_sang", nhat_ky
        assert (ss["nhanh"], ss["nhip_ms"], ss["rt"], ss["pid"]) == ("VEHICLE_IO", 16, 1.0, p.pid)
        link = ss["vehicle_link"]
        assert (link["mode"], link["io_simulated"], link["port"], link["evidence"]) == \
            ("VEHICLE_IO", True, None, "simulation_only")
        assert "max_cusps" in ss["chinh_sach_doi_chieu"] and ss["max_speed_mps"] > 0 and "delay_s" in ss["phan_hoi"]
        if WIN11:                                   # AUTOPARK_KEEP_ECOQOS=1 (mặc định của moi_truong_con)
            assert ss["ecoqos"] == "system" and ss["dieu_tiet"] == {"ecoqos": "system", "dong_ho": "system"}
        assert p.gui("chuan_bi c0")
        assert p.doc(30.0, ("chuan_bi", "loi"), "c0") == {"loai": "chuan_bi", "yeu_cau": "c0",
                                                          "trang_thai_phien": "EDITING", "san_sang": False,
                                                          "co_duong": False}
        assert p.gui("chay 1")
        loi = p.doc(30.0, ("bat_dau_chay", "loi"), "1")
        assert loi is not None and loi["loai"] == "loi" and "EDITING" in loi["thong_diep"]
        # một lần chạy ngắn thật trong vòng sự kiện Qt (QTimer 16 ms, offscreen): lập đường, chạy, kết quả
        assert p.gui("plan p2")
        lap = p.doc(40.0, ("ket_qua", "loi"), "p2")
        assert lap is not None and (lap["loai"], lap["ket_qua"]) == ("ket_qua", "OK"), (lap, nhat_ky)
        assert p.gui("chay 3")
        bat_dau = p.doc(30.0, ("bat_dau_chay", "loi"), "3")
        assert bat_dau is not None and bat_dau["loai"] == "bat_dau_chay", bat_dau
        kq = p.doc(60.0, ("ket_qua_chay", "loi"), "3")
        assert kq is not None and (kq["loai"], kq["ket_qua"], kq["nhanh"]) == ("ket_qua_chay", "COMPLETED", "VEHICLE_IO")
        tk = _kiem_chuoi(kq)
        assert kq["vehicle_io"]["lenh_gui"] >= tk["so_nhip_dk"] and tk["nhip_gd_p50_ms"] >= 10.0
        assert p.gui("thoat")
        assert p.proc.wait(timeout=30) == 0
    finally:
        p.dong()
    sai = subprocess.run([sys.executable, "-X", "utf8", "-m", eg.MODULE, "con", "--kich-ban", str(kich_ban), "--chay",
                          "--nhanh", "XYZ"], cwd=eg.PROJECT_ROOT, capture_output=True, env=_env_offscreen(),
                         timeout=120)
    assert sai.returncode == 2 and b"XYZ" in sai.stderr


# -------------------------------------------------------------------------------------------- dòng lệnh, tệp

def test_do_chay_tu_choi_tham_so_sai_truoc_khi_mo_gi(tmp_path, monkeypatch, capsys):
    """Tham số sai: mã 2 trước khi tạo thư mục hay mở tiến trình con nào (lượt đo thật chỉ chạy bằng tay)."""
    monkeypatch.setattr(eg, "TienTrinhCon", lambda *a, **k: pytest.fail("không được mở tiến trình con"))
    monkeypatch.setattr(sys, "platform", "win32")             # các bước kiểm tham số không gọi Win32
    moi = tmp_path / "moi"
    for sai in (["--nhanh", "SIM,OBSERVE"], ["--nhanh", "SIM,SIM"], ["--nhanh", ""], ["--bien-the", "khong_cua_so"],
                ["--bien-the", "gui_x"], ["--trang-thai", "thuong,nghieng"],
                ["--kich-ban", "scenarios/bai_do_xe.json", "--ca", "uturn_w46"],
                ["--kich-ban", str(tmp_path / "khong_co.json")], ["--ca", "khong_co"], ["--cho", "1"],
                ["--khoi", "0"], ["--lap", "0"], ["--toi-da-chay", "10"]):
        assert eg.main(["do-chay", "--ra", str(moi), *sai]) == 2, sai
    assert not moi.exists()
    loi = capsys.readouterr().err
    assert "chưa có ở chế độ chạy" in loi and "--kich-ban và --ca không dùng cùng nhau" in loi
    assert "--toi-da-chay phải ≥ 30 giây" in loi and "không có tệp kịch bản" in loi
    cu = tmp_path / "cu"
    cu.mkdir()
    (cu / "ket_qua.jsonl").write_text("", encoding="utf-8")
    assert eg.main(["do-chay", "--ra", str(cu)]) == 2
    assert "chọn thư mục mới" in capsys.readouterr().err
    monkeypatch.setattr(sys, "platform", "linux")
    assert eg.main(["do-chay", "--ra", str(moi)]) == 2 and not moi.exists()


class FakeTienTrinhChay:
    """TienTrinhCon giả cho `do-chay`: `con --chay` báo san_sang (EcoQoS "system"); chuan_bi / plan / chay / dung /
    cap_quyen / len_truoc trả lời ngay; ket_qua_chay tới ngay sau `chay`, trừ khi `ket_qua` False (không bao giờ tới,
    kể cả sau khi bấm Dừng). `doc` không có gì thì tiến đồng hồ giả đúng `het_han`."""

    def __init__(self, tham_so, ten, *, dong_ho: DongHoGia, ket_qua: bool = True, ghi=None, env=None):
        from types import SimpleNamespace

        self.tham_so, self.ten, self.env, self.dong_ho, self.ket_qua = list(tham_so), ten, env, dong_ho, ket_qua
        self.pid, self.proc, self.con_song = 4242, SimpleNamespace(pid=4241), True
        self.nhanh = self.tham_so[self.tham_so.index("--nhanh") + 1]
        self.lenh: list[str] = []
        self._san_sang = False
        self._tin = [{"loai": "san_sang", "pid": 4242, "hwnd": FakeCuaSo.hwnd, "nen_tang": "windows",
                      "ecoqos": "system", "nhanh": self.nhanh, "nhip_ms": 16, "rt": 1.0,
                      "dieu_tiet": {"ecoqos": "system", "dong_ho": "system"},
                      "chinh_sach_doi_chieu": {"max_cusps": None, "warn_cusps": 7}, "phan_hoi": {"delay_s": 0.0},
                      "max_speed_mps": 0.3, "vehicle_link": None if self.nhanh == "SIM" else {"io_simulated": True}}]

    def gui(self, lenh: str) -> bool:
        self.lenh.append(lenh)
        ten, yc = eg._tach_lenh(lenh)
        if ten == "chuan_bi":
            self._tin.append({"loai": "chuan_bi", "yeu_cau": yc, "trang_thai_phien": "READY" if self._san_sang
                              else "EDITING", "san_sang": self._san_sang, "co_duong": self._san_sang})
        elif ten == "plan":
            self._san_sang = True
            self._tin.append({"loai": "ket_qua", "yeu_cau": yc, "ket_qua": "OK", "thong_diep": "Tìm được"})
        elif ten in ("cap_quyen", "len_truoc"):
            self._tin.append({"loai": ten, "yeu_cau": yc, "ok": True, "loi": 0, "truoc_hwnd": FakeCuaSo.hwnd})
        elif ten == "chay":
            self._tin.append({"loai": "bat_dau_chay", "yeu_cau": yc, "lan": 0, "nhanh": self.nhanh, "rt": 1.0,
                              "t_bam": 4.99, "t_bat_dau": 5.0, "tg_khoi_dong_ms": 10.0})
            if self.ket_qua:
                self._tin.append(_kq_chay_gia(yc, _chuoi_gia([16.0] * 50), nhanh=self.nhanh))
        elif ten == "dung":
            self._tin.append({"loai": "dung", "yeu_cau": yc, "ok": True})
        return True

    def doc(self, het_han, loai, yeu_cau=None):
        muon = {loai} if isinstance(loai, str) else set(loai)
        for i, tin in enumerate(self._tin):
            if tin["loai"] in muon and (yeu_cau is None or "yeu_cau" not in tin or tin["yeu_cau"] == yeu_cau):
                return self._tin.pop(i)
        self.dong_ho.t += het_han
        return None

    def dong(self, cho: float = 10.0) -> int:
        self.con_song = False
        return 0


def _do_chay_gia(monkeypatch, *, ket_qua=lambda ten: True, ecoqos_san_sang=lambda ten: "system") -> list:
    """Thay mọi thứ `do-chay` chạm tới (tiến trình con, cửa sổ, lớp Win32, đọc máy) bằng đồ giả; trả list các tiến trình
    giả đã tạo. `ket_qua(ten)`: tiến trình `ten` ("<biến thể>/<nhánh>") có trả ket_qua_chay không;
    `ecoqos_san_sang(ten)`: EcoQoS nó tự đọc lúc sẵn sàng (None = không đọc được)."""
    import functools

    dong_ho = DongHoGia()
    tao: list[FakeTienTrinhChay] = []
    dieu_tiet = {"ecoqos": "system", "dong_ho": "system"}

    def tien_trinh(tham_so, ten, **kw):
        dieu_tiet.update(ecoqos="system", dong_ho="system")         # tiến trình mới: mặc định của Windows
        tao.append(FakeTienTrinhChay(tham_so, ten, dong_ho=dong_ho, ket_qua=ket_qua(ten), **kw))
        tao[-1]._tin[0]["ecoqos"] = ecoqos_san_sang(ten)
        return tao[-1]

    class CuaSo(FakeCuaSo):
        ton_tai = True

    may = TrangThaiMay("mo", "active", "Default", "bat", 100.0, 4242, FakeCuaSo.hwnd, "python.exe")
    monkeypatch.setattr(eg, "TienTrinhCon", tien_trinh)
    monkeypatch.setattr(eg, "CuaSoWin32", lambda hwnd: CuaSo([]))
    monkeypatch.setattr(eg, "doc_trang_thai_may", lambda *a, **k: may)
    for ten, gia_tri in (("doc_git", {}), ("dat_dpi_vat_ly", True), ("doc_windows", {}), ("doc_nguon", {}),
                         ("lop_cpu", None), ("_chay_powercfg", None), ("phan_giai_dong_ho_ms", (15.625, 0.5, 0.5))):
        monkeypatch.setattr(eg, ten, lambda *a, _g=gia_tri, **k: _g)
    monkeypatch.setattr(eg, "doc_dieu_tiet", lambda pid=None: dict(dieu_tiet))
    monkeypatch.setattr(eg, "disable_power_throttling", lambda pid: dieu_tiet.update(ecoqos="off") or True)
    monkeypatch.setattr(eg, "execution_speed_throttling", lambda pid=None: dieu_tiet["ecoqos"])
    monkeypatch.setattr(eg, "dat_ton_trong_dong_ho", lambda pid: dieu_tiet.update(ecoqos="off", dong_ho="ton_trong")
                        or True)
    monkeypatch.setattr(ec, "NguCanhChay", functools.partial(
        ec.NguCanhChay, doc_may=lambda: may, doc_truoc=lambda: (4242, FakeCuaSo.hwnd, "python.exe"),
        chup_cpu=lambda: _chup(0.0, [0.0, 0.0]), ecoqos_cua=lambda pid: dieu_tiet["ecoqos"],
        uu_tien_cua=lambda pid: "normal", cpu_cua=lambda pid: 1.0, ngu=lambda s: None, dong_ho=dong_ho,
        doc_dieu_tiet=lambda pid: dict(dieu_tiet), doc_phan_giai=lambda: (15.625, 0.5, 0.5)))
    return tao


def test_do_chay_voi_tien_trinh_gia(tmp_path, monkeypatch, capsys):
    """Cả lệnh `do-chay` với tiến trình con, cửa sổ và lớp Win32 giả (không mở cửa sổ, không chạm tiến trình hay thiết
    lập thật nào): 3 biến thể × 2 nhánh, chỉ trạng thái thường; khối gui_off_dh/VEHICLE_IO có lần chạy không dừng được
    nên dừng sớm, các khối sau vẫn đo."""
    tao = _do_chay_gia(monkeypatch, ket_qua=lambda ten: ten != "gui_off_dh/VEHICLE_IO")
    ra = tmp_path / "ra"
    assert eg.main(["do-chay", "--ra", str(ra), "--bien-the", "gui_system,gui_off,gui_off_dh", "--trang-thai", "thuong",
                    "--khoi", "1", "--lap", "1", "--cho", "2", "--toi-da-chay", "30"]) == 0
    assert [(p.ten, p.env.get("AUTOPARK_KEEP_ECOQOS")) for p in tao] == [
        ("gui_system/SIM", "1"), ("gui_system/VEHICLE_IO", "1"), ("gui_off/SIM", None), ("gui_off/VEHICLE_IO", None),
        ("gui_off_dh/SIM", None), ("gui_off_dh/VEHICLE_IO", None)]
    kich_ban = str((ra / "kich_ban_bai_do_xe.json").resolve())     # bản sao trong --ra, đường dẫn tuyệt đối
    assert all(p.tham_so == ["con", "--kich-ban", kich_ban, "--chay", "--nhanh", p.nhanh] for p in tao)
    assert tao[-1].lenh.count("dung d0") == 1
    dong = eg._doc_jsonl(ra / "ket_qua.jsonl")
    assert all(list(d) == list(ec.COT_CHAY) for d in dong)
    assert [(d["bien_the"], d["nhanh"], d["lan"], d["ket_qua"]) for d in dong][-3:] == [
        ("gui_off_dh", "SIM", 0, "COMPLETED"), ("gui_off_dh", "SIM", 1, "COMPLETED"),
        ("gui_off_dh", "VEHICLE_IO", 0, "KHONG_TRA_LOI")]
    assert len(dong) == 11 and "khong_dung_duoc" in dong[-1]["ghi_chu"]
    lan1 = [d for d in dong if d["lan"] == 1]
    assert len(lan1) == 5 and all(eg.ly_do_loai(d) is None and d["cung_ket_qua_moc"] is True for d in lan1)
    assert {(d["bien_the"], d["ecoqos"], d["dong_ho"]) for d in lan1} == {
        ("gui_system", "system", "system"), ("gui_off", "off", "system"), ("gui_off_dh", "off", "ton_trong")}
    assert all((ra / d["tep_chuoi"]).is_file() for d in dong if d["ket_qua"] == "COMPLETED")
    may_json = json.loads((ra / "may.json").read_text(encoding="utf-8"))
    assert (may_json["che_do"], may_json["kich_ban"], may_json["kich_ban_lech"], may_json["nhip_ms"]) == \
        ("chay", "kich_ban_bai_do_xe.json", 0.0, 16)
    assert [k["cach_tat"] for k in may_json["khoi_tien_trinh"]] == [None, None, "theo_pid", "theo_pid",
                                                                    "theo_pid_dong_ho", "theo_pid_dong_ho"]
    assert may_json["khoi_tien_trinh"][0]["tg_chay_khoi_dong_s"] == 0.8 and may_json["so_dong"] == 11
    # khối bị bỏ dở (sửa sau rà soát 02/10/2026): mã thoát vẫn 0 nhưng may.json và tom_tat.txt ghi lại
    assert may_json["so_lan_du_kien"] == 12 and may_json["dung_giua_chung"] == ""
    assert may_json["khoi_bo_do"] == [{"khoi": 0, "bien_the": "gui_off_dh", "nhanh": "VEHICLE_IO", "lan": 0,
                                       "trang_thai": "thuong", "luot_bo": 1}]
    tom_tat = (ra / "tom_tat.txt").read_text(encoding="utf-8")
    assert tom_tat == ec.tom_tat_chay(dong, may_json)
    assert ("CẢNH BÁO: 1 lần chạy không dừng được (không có kết quả cả sau khi bấm Dừng; phần còn lại của khối bị bỏ, "
            "không có dòng): khối 0 gui_off_dh VEHICLE_IO lần 0 thuong (bỏ 1 lượt còn lại của khối).") in tom_tat
    assert "CẢNH BÁO: chỉ 11/12 lượt dự kiến có dòng (1 lượt của khối bị bỏ dở)." in tom_tat
    assert eg.ly_do_loai(dong[-1]) == "khoi_dong"                  # lượt khởi động: chỉ dòng CẢNH BÁO nói ra nó
    ra_man_hinh = capsys.readouterr().out
    assert "Lượt khởi động: 0,8 s mô phỏng / 0,8 s thật" in ra_man_hinh
    assert ("CẢNH BÁO: gui_off_dh/VEHICLE_IO: lần chạy không dừng được; bỏ phần còn lại của khối này (1 lượt chưa đo)"
            in ra_man_hinh)
    assert "Xong: 11/12 lần chạy (1 khối bị bỏ dở vì lần chạy không dừng được, 1 lượt chưa đo" in ra_man_hinh


def test_tom_tat_chay_bao_lan_chay_khong_dung_duoc_va_thieu_luot():
    """Hàm thuần (thêm 02/10/2026): mọi dòng có ghi chú `khong_dung_duoc` được kể tên (kể cả lượt khởi động, bị loại với
    lý do khoi_dong), số dòng ít hơn `so_lan_du_kien` thì có CẢNH BÁO; may.json không có `khoi_bo_do` vẫn tóm tắt được;
    lịch đo đi hết thì không có dòng nào trong hai dòng đó."""
    ket = _dong_chay("gui_off", "thuong", lan=0, ket_qua="KHONG_TRA_LOI", ghi_chu="khong_dung_duoc")
    dong = _hai("gui_system", "thuong") + [ket]
    may = _MAY_CHAY | {"so_lan_du_kien": 8, "dung_giua_chung": "Ctrl+C"}
    van_ban = ec.tom_tat_chay(dong, may)
    assert _dong_ket_luan(van_ban, "CẢNH BÁO: 1 lần chạy không dừng được").endswith(
        "không có dòng): khối 0 gui_off SIM lần 0 thuong.")
    assert "CẢNH BÁO: chỉ 3/8 lượt dự kiến có dòng (5 lượt sau khi dừng giữa chừng)." in van_ban
    may["khoi_bo_do"] = [{"khoi": 0, "bien_the": "gui_off", "nhanh": "SIM", "lan": 0, "trang_thai": "thuong",
                          "luot_bo": 3}]
    van_ban = ec.tom_tat_chay(dong, may)
    assert "khối 0 gui_off SIM lần 0 thuong (bỏ 3 lượt còn lại của khối)." in van_ban
    assert ("CẢNH BÁO: chỉ 3/8 lượt dự kiến có dòng (3 lượt của khối bị bỏ dở; 2 lượt sau khi dừng giữa chừng)."
            in van_ban)
    du = ec.tom_tat_chay(_hai("gui_system", "thuong"), _MAY_CHAY | {"so_lan_du_kien": 2})
    assert "không dừng được" not in du and "lượt dự kiến có dòng" not in du


def test_dat_bien_the_gui_system_khong_doc_duoc_ecoqos_khong_loai(monkeypatch):
    """Chế độ chạy (sửa sau rà soát 02/10/2026): EcoQoS lúc sẵn sàng không đọc được (None) không phải "khác mặc định":
    không ghi chú loại khối; "on"/"off" đọc được thì vẫn loại."""
    monkeypatch.setattr(eg, "doc_dieu_tiet", lambda pid=None: None)
    ghi_chu, cach_tat, dieu_tiet, nhat_ky = ec._dat_bien_the("gui_system", 4242, {"ecoqos": None})
    assert (ghi_chu, cach_tat, dieu_tiet) == ("", None, None) and "không đọc được EcoQoS" in nhat_ky
    assert ec._dat_bien_the("gui_system", 4242, {"ecoqos": "system"})[0] == ""
    assert ec._dat_bien_the("gui_system", 4242, {"ecoqos": "off"})[0] == "khong_giu_duoc_ecoqos"
    assert ec._dat_bien_the("gui_system", 4242, {})[0] == ""                           # khóa thiếu: cũng là không biết


def test_do_chay_gui_system_khong_doc_duoc_ecoqos_van_giu_dong(tmp_path, monkeypatch, capsys):
    """Cả lệnh `do-chay` với đồ giả: giao diện báo EcoQoS lúc sẵn sàng None (máy không đọc được) → dòng gui_system vẫn
    hợp lệ, công cụ in cảnh báo "không đọc được EcoQoS" chứ không phải "khong_giu_duoc_ecoqos" (rà soát 02/10/2026)."""
    _do_chay_gia(monkeypatch, ecoqos_san_sang=lambda ten: None)
    ra = tmp_path / "ra"
    assert eg.main(["do-chay", "--ra", str(ra), "--nhanh", "SIM", "--bien-the", "gui_system", "--trang-thai", "thuong",
                    "--khoi", "1", "--lap", "1", "--cho", "2", "--toi-da-chay", "30"]) == 0
    dong = eg._doc_jsonl(ra / "ket_qua.jsonl")
    assert [(d["lan"], d["ghi_chu"], eg.ly_do_loai(d)) for d in dong] == [(0, "", "khoi_dong"), (1, "", None)]
    ra_man_hinh = capsys.readouterr().out
    assert ("CẢNH BÁO: gui_system/SIM (pid 4242) lúc sẵn sàng không đọc được EcoQoS" in ra_man_hinh
            and "các dòng của khối này vẫn được giữ" in ra_man_hinh)
    assert "khong_giu_duoc_ecoqos" not in ra_man_hinh and "các dòng của khối này bị loại" not in ra_man_hinh
    may_json = json.loads((ra / "may.json").read_text(encoding="utf-8"))
    assert may_json["khoi_tien_trinh"][0]["ecoqos_san_sang"] is None and may_json["khoi_bo_do"] == []


def test_dau_do_chay_ghi_gioi_han_doi_chieu_co_hieu_luc(qapp):
    """`chinh_sach_doi_chieu` của san_sang (và may.json) là giới hạn START thật sự áp: tệp sa bàn gắn nghiệm thu DO-1 →
    tối đa 2 lần đổi chiều theo kịch bản, không phải chính sách của cờ (max_cusps None) (sửa sau rà soát 02/10/2026)."""
    from autopark.application.cusp_policy import SOURCE_ACCEPTANCE
    from autopark.ui.app import build_window

    window = build_window(eg.PROJECT_ROOT / "scenarios" / "nghiem_thu" / "do1.json")
    dd = ec.DauDoChay(window, lambda tin: None)
    try:
        doi_chieu = dd.thong_tin("SIM")["chinh_sach_doi_chieu"]
        assert doi_chieu == window.session.cusp_limit().to_dict()
        assert (doi_chieu["source"], doi_chieu["max_cusps"], doi_chieu["key"]) == (SOURCE_ACCEPTANCE, 2, "DO-1")
        assert window.session.cusp_policy.to_dict()["max_cusps"] is None       # cờ một mình không chặn
        assert json.loads(json.dumps(eg._sach(doi_chieu), ensure_ascii=False)) == doi_chieu
    finally:
        dd.go()
        window.close()


def test_tom_tat_dong_lenh_chon_che_do(tmp_path, capsys):
    from tests.test_ecoqos_gui import _MAY, _ba

    dong = [r for tt in eg.TRANG_THAI for r in _hai("gui_system", tt) + _hai("gui_off", tt)]
    (tmp_path / "ket_qua.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in dong),
                                            encoding="utf-8")
    (tmp_path / "may.json").write_text(json.dumps(_MAY_CHAY, ensure_ascii=False), encoding="utf-8")
    assert eg.main(["tom-tat", "--ra", str(tmp_path)]) == 0
    assert (tmp_path / "tom_tat.txt").read_text(encoding="utf-8") == ec.tom_tat_chay(dong, _MAY_CHAY)
    assert "Đo vòng điều khiển của ứng dụng giao diện khi chạy" in capsys.readouterr().out
    (tmp_path / "may.json").unlink()                           # thiếu may.json: dòng có khóa "nhanh" là chế độ chạy
    assert eg.main(["tom-tat", "--ra", str(tmp_path)]) == 0
    assert (tmp_path / "tom_tat.txt").read_text(encoding="utf-8") == ec.tom_tat_chay(dong, {})
    cu = tmp_path / "cu"                                       # thư mục của chế độ lập đường: như trước
    cu.mkdir()
    dong_cu = [r for bt in ("gui_system", "gui_off") for tt in eg.TRANG_THAI for r in _ba(bt, tt, 3.6)]
    (cu / "ket_qua.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in dong_cu),
                                      encoding="utf-8")
    (cu / "may.json").write_text(json.dumps(_MAY, ensure_ascii=False), encoding="utf-8")
    assert eg.main(["tom-tat", "--ra", str(cu)]) == 0
    assert (cu / "tom_tat.txt").read_text(encoding="utf-8") == eg.tom_tat(dong_cu, _MAY)


# --------------------------------------------------------------------------------------------- Windows thật

@windows_only
def test_doc_dieu_tiet_phan_giai_va_ton_trong_dong_ho_tren_windows():
    """Chỉ đọc trên tiến trình pytest; chỉ ĐẶT trên một tiến trình con ngắn hạn (rồi giết nó)."""
    phan_giai = eg.phan_giai_dong_ho_ms()
    assert phan_giai is not None
    tho, min_, hien = phan_giai
    assert 0.4 <= min_ <= hien <= tho <= 16.0
    if not WIN11:
        pytest.skip("ProcessPowerThrottling đọc được từ Windows 11 (bản 22000)")
    cua_pytest = eg.doc_dieu_tiet(None)
    assert cua_pytest == eg.doc_dieu_tiet(os.getpid())
    assert cua_pytest["ecoqos"] in ("system", "on", "off") and cua_pytest["dong_ho"] in ("system", "bo_qua", "ton_trong")
    con = subprocess.Popen([sys.executable, "-c", "import os, time; print(os.getpid(), flush=True); time.sleep(30)"],
                           stdout=subprocess.PIPE, text=True)
    try:
        pid = int(con.stdout.readline())                         # pid của trình thông dịch thật (không phải launcher)
        assert eg.dat_ton_trong_dong_ho(pid) is True
        assert eg.doc_dieu_tiet(pid) == {"ecoqos": "off", "dong_ho": "ton_trong"}
    finally:
        con.kill()
        con.wait(timeout=30)
    assert eg.dat_ton_trong_dong_ho(None) is False               # không bao giờ đặt cho chính tiến trình này
    assert eg.doc_dieu_tiet(None) == cua_pytest
