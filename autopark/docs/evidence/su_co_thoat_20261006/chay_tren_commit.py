"""Chạy lại trên một commit, bản có theo dõi (06/10/2026; bản sửa từ docs/evidence/cong_cu_20261002/chay_tren_commit.py,
bản cũ giữ nguyên vì là bằng chứng của các lượt đã ghi). Như bản cũ: bo ảo `kiem`, chạy lặp tests/test_firmware_qemu.py
10 lượt, rồi toàn bộ bộ test ở `.venv` và `.venv-train` (offscreen).

Khác bản cũ (lượt `.venv` ngày 06/10/2026 thoát 0xC0000005 lúc tắt mà không để lại dấu vết gì; CHUYEN_MAY_BAN.md
mục 16):
- đặt ErrorMode 0x8001 cho chính nó trước khi mở tiến trình con (con thừa hưởng), nên crash có sự kiện WER và minidump;
  chạy từ Git Bash mà không đặt thì con mang 0x3 (SEM_NOGPFAULTERRORBOX) và WER không ghi gì;
- pytest chạy với -X faulthandler; stdout + stderr của từng lượt pytest ghi ra tệp `*.dau_ra.txt` (bản cũ bỏ đi);
- mã thoát ghi cả dạng hex, kèm nghĩa và "$? Git Bash sẽ báo"; thiếu JUnit (chết trước khi ghi) không làm hỏng script;
- dump mới của %LOCALAPPDATA%\\CrashDumps được liệt kê và chép sang thư mục dump (mặc định
  runs/dump/chay_tren_commit_<commit>_<giờ>, git bỏ qua; KHÔNG chép dump vào docs/evidence);
- hạn giờ cho từng lượt (quá hạn thì taskkill /T /F cả cây tiến trình, ghi "HẾT GIỜ");
- ghi HEAD và cây làm việc có sạch không (bản cũ ghi "cây làm việc sạch" mà không kiểm);
- --chi-test: chỉ chạy các test cho trước ở hai venv và bỏ phần bo ảo, để kiểm script trong vài giây (thêm
  --lap-bo-ao 1 để kiểm cả phần bo ảo: kiem và một lượt chạy lặp, khoảng một phút, QEMU dùng ≈ 1 lõi).
Chú ý: với ErrorMode 0x8001, WER ghi cả các lần QEMU crash trong test bo ảo (có lẽ lỗi tự thoát lúc khởi động
espressif/qemu#175 mà QemuBoard tự thử lại; suy luận); mỗi dump mới làm WER xóa dump cũ nhất khi thư mục đã đủ 10
(DumpCount mặc định): sao lưu CrashDumps trước nếu cần giữ.
Tệp `*.dau_ra.txt` (và JUnit) có thể chứa đường dẫn thư mục tạm trong hồ sơ người dùng khi có test hỏng: xem và lọc
trước khi commit.

Chạy trong thư mục autopark của repo:

    .venv\\Scripts\\python.exe -X utf8 docs\\evidence\\su_co_thoat_20261006\\chay_tren_commit.py <commit> <kết quả>
    .venv\\Scripts\\python.exe -X utf8 docs\\evidence\\su_co_thoat_20261006\\chay_tren_commit.py thu <thư mục tạm> \\
        --chi-test tests/test_geometry.py                                        (kiểm script, vài giây)

Gọi pytest bằng subprocess, không qua pytest.main, nên tiến trình con của test không chạy lại script này."""
import argparse
import datetime as dt
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from chay_co_theo_doi import (SEM_FAILCRITICALERRORS, SEM_NOOPENFILEERRORBOX, anh_chup, chep_dump_moi,  # noqa: E402
                              k32, ma_git_bash, nghia, su_kien_wer)

VENV = Path(".venv/Scripts/python.exe")
VENV_TRAIN = Path(".venv-train/Scripts/python.exe")
MA_PYTEST = {0: "đạt", 1: "có test hỏng", 2: "bị ngắt", 3: "lỗi nội bộ của pytest", 4: "lỗi dòng lệnh",
             5: "không có test"}


def cpu_load() -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average"],
                       capture_output=True, text=True)
    return r.stdout.strip() or "?"


def trang_thai_cay() -> str:
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        doi = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace").stdout.splitlines()
    except OSError as exc:
        return f"không đọc được git: {exc}"
    return f"HEAD {head}, cây làm việc " + ("sạch" if not doi else f"KHÔNG sạch ({len(doi)} mục đổi hay chưa theo dõi)")


def junit(path: Path) -> dict | None:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    props = {p.get("name"): p.get("value") for p in suite.iter("property")}
    failed = [c.get("classname") + "::" + c.get("name") for c in suite.iter("testcase")
              if c.find("failure") is not None or c.find("error") is not None]
    return {k: suite.get(k) for k in ("tests", "failures", "errors", "skipped", "time")} | {
        "ecoqos": props.get("ecoqos"), "failed": failed}


def chay(cmd: list, dau_ra: Path, het_gio: float, env: dict) -> dict:
    """Chạy một lệnh, stdout + stderr vào tệp; quá hạn thì taskkill /T /F. Trả mã 32 bit, có hết giờ không, số giây."""
    t0, t0_utc = time.monotonic(), dt.datetime.now(dt.timezone.utc)
    cmd = [str(c) for c in cmd]
    with open(dau_ra, "wb") as f:
        f.write(f"# {dt.datetime.now():%d/%m/%Y %H:%M:%S} $ {' '.join(cmd)}\n".encode("utf-8"))
        f.flush()
        p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
        het = False
        try:
            rc = p.wait(timeout=het_gio if het_gio > 0 else None)
        except subprocess.TimeoutExpired:
            het = True
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            try:
                rc = p.wait(timeout=60)
            except subprocess.TimeoutExpired:
                rc = 0xFFFFFFFF
        rc &= 0xFFFFFFFF
        f.write(f"\n# {dt.datetime.now():%H:%M:%S} mã thoát {rc} = 0x{rc:08X} ({nghia(rc)}; Git Bash sẽ báo "
                f"{ma_git_bash(rc)}){'; HẾT GIỜ sau %g s, đã taskkill /T /F' % het_gio if het else ''}\n"
                .encode("utf-8"))
    return {"rc": rc, "het_gio": het, "han": het_gio, "giay": time.monotonic() - t0, "tu_utc": t0_utc}


def mo_ta_ma(r: dict) -> str:
    rc = r["rc"]
    s = f"exit={rc}" if rc in MA_PYTEST else f"exit={rc} = 0x{rc:08X} ({nghia(rc)}; Git Bash sẽ báo {ma_git_bash(rc)})"
    return s + (f", HẾT GIỜ sau {r['han']:g} s (taskkill /T /F)" if r["het_gio"] else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("commit", help="nhãn commit (ghi vào tên tệp); HEAD thật và độ sạch của cây được ghi riêng")
    ap.add_argument("ra", type=Path, help="thư mục kết quả")
    ap.add_argument("--chi-test", nargs="+", metavar="TEST",
                    help="chỉ chạy các test này ở hai venv (thay toàn bộ bộ test); kèm theo bỏ phần bo ảo, trừ khi có "
                         "--lap-bo-ao")
    ap.add_argument("--lap-bo-ao", type=int, default=None,
                    help="số lượt chạy lặp tests/test_firmware_qemu.py (mặc định 10; với --chi-test mặc định 0); "
                         "0 = bỏ cả phần bo ảo (kiem và chạy lặp)")
    ap.add_argument("--het-gio-pytest", type=float, default=3000, help="hạn giờ mỗi lượt toàn bộ test, giây")
    ap.add_argument("--het-gio-bo-ao", type=float, default=600, help="hạn giờ của kiem và của mỗi lượt chạy lặp, giây")
    ap.add_argument("--cho-wer", type=float, default=20, help="mã là crash: chờ WER ghi xong, giây")
    ap.add_argument("--khong-faulthandler", action="store_true", help="bỏ -X faulthandler (điều kiện như bản cũ)")
    ap.add_argument("--dump-ra", type=Path, help="thư mục chép dump mới (mặc định runs/dump/chay_tren_commit_…)")
    a = ap.parse_args()
    if a.lap_bo_ao is None:
        a.lap_bo_ao = 0 if a.chi_test else 10
    commit, out = a.commit, a.ra
    out.mkdir(parents=True, exist_ok=True)
    em_cu = k32.GetErrorMode()
    k32.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    fh = [] if a.khong_faulthandler else ["-X", "faulthandler"]
    day = time.strftime("%d/%m/%Y")
    dump_nguon = Path(os.environ.get("LOCALAPPDATA", "")) / "CrashDumps"
    dump_dich = a.dump_ra or Path("runs") / "dump" / f"chay_tren_commit_{commit}_{time.strftime('%Y%m%d_%H%M%S')}"
    dump_truoc, da_chep = anh_chup(dump_nguon), set()
    log = [f"# Chạy trên commit {commit}, máy bàn, bắt đầu {day} {time.strftime('%H:%M:%S')}; {trang_thai_cay()}",
           f"# ErrorMode 0x{em_cu:X} -> 0x{k32.GetErrorMode():X} (tiến trình con thừa hưởng; WER ghi sự kiện và "
           f"minidump); pytest {'KHÔNG ' if a.khong_faulthandler else ''}có -X faulthandler; hạn giờ: toàn bộ test "
           f"{a.het_gio_pytest:g} s, bo ảo {a.het_gio_bo_ao:g} s; dump mới chép vào {dump_dich}"]
    if a.chi_test:
        log.append(f"# CHẾ ĐỘ KIỂM SCRIPT: chỉ chạy {' '.join(a.chi_test)} ở hai venv; phần bo ảo: "
                   + (f"kiem và {a.lap_bo_ao} lượt chạy lặp" if a.lap_bo_ao > 0 else "bỏ"))

    def sau_luot(r: dict, dau_ra: Path) -> str:
        """Sau mỗi lượt: chép dump mới; mã là crash thì chờ WER rồi đọc sự kiện WER, ghi thêm vào tệp đầu ra."""
        them = chep_dump_moi(dump_nguon, dump_truoc, dump_dich, da_chep)
        crash = r["rc"] >= 0xC0000000 and r["rc"] != 0xFFFFFFFF
        su_kien = []
        if crash and a.cho_wer > 0:
            time.sleep(a.cho_wer)
            them += chep_dump_moi(dump_nguon, dump_truoc, dump_dich, da_chep)
        if crash or them:
            su_kien = su_kien_wer(r["tu_utc"] - dt.timedelta(seconds=5)).splitlines()
            with open(dau_ra, "ab") as f:
                f.write(("# sự kiện WER từ lúc bắt đầu lượt: " + str(len(su_kien)) + "\n"
                         + "".join(f"#   {x}\n" for x in su_kien) + "".join(f"# dump mới: {x}\n" for x in them))
                        .encode("utf-8"))
        return (f"; dump mới {len(them)}: {', '.join(x.split(' ')[0] for x in them)}" if them else "") + \
               (f"; sự kiện WER {len(su_kien)}" if su_kien else "")

    if a.lap_bo_ao > 0:
        # 1) bo ảo: kiem
        f_kiem = out / f"kiem_bo_ao_{commit}.txt"
        r = chay([VENV, "-X", "utf8", "-m", "autopark.transport.qemu_board", "kiem"], f_kiem, a.het_gio_bo_ao, env)
        log.append(f"kiem: {mo_ta_ma(r)}{sau_luot(r, f_kiem)}")

        # 2) bo ảo: chạy lặp; đầu ra mọi lượt gộp vào một tệp
        lines = [f"# Chạy lặp tests/test_firmware_qemu.py, commit {commit}, máy bàn, bắt đầu {day} "
                 f"{time.strftime('%H:%M:%S')}"]
        f_lap = out / f"chay_lap_test_bo_ao_{commit}.dau_ra.txt"
        f_lap.write_bytes(b"")
        Path("runs").mkdir(exist_ok=True)              # thư mục tạm trong runs/ (git bỏ qua): đường dẫn ghi vào đầu ra
        with tempfile.TemporaryDirectory(dir="runs") as tmp:  # không chứa hồ sơ người dùng như %TEMP%
            for i in range(1, a.lap_bo_ao + 1):
                xml, d = Path(tmp) / f"lap_{i}.xml", Path(tmp) / f"lap_{i}.txt"
                r = chay([VENV, "-X", "utf8", *fh, "-m", "pytest", "tests/test_firmware_qemu.py", "-p",
                          "no:cacheprovider", "--junitxml", xml], d, a.het_gio_bo_ao, env)
                them = sau_luot(r, d)
                text = d.read_text(encoding="utf-8", errors="replace")
                with open(f_lap, "ab") as f:
                    f.write(f"######## lượt {i}\n{text}".encode("utf-8"))
                j = junit(xml)
                if j:
                    passed = int(j["tests"]) - int(j["failures"]) - int(j["errors"]) - int(j["skipped"])
                    kq = f"{passed} đạt, {j['failures']} hỏng, {j['errors']} lỗi, {j['skipped']} bỏ qua"
                else:
                    kq = "JUnit thiếu hay không đọc được"
                ma = "" if r["rc"] in (0, 1) and not r["het_gio"] else f"; {mo_ta_ma(r)}"
                lines.append(f"lượt {i:2d}: {kq}; cảnh báo QEMU tự thoát (#175): "
                             f"{text.count('espressif/qemu#175')}; cảnh báo LOOP_OVERRUN: "
                             f"{text.count('LOOP_OVERRUN (máy bận)')}; {r['giay']:.0f}s{ma}{them}")
        lines.append(f"# kết thúc {time.strftime('%H:%M:%S')}")
        (out / f"chay_lap_test_bo_ao_{commit}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.append("chạy lặp: " + "; ".join(line.split(":", 1)[1].split(";")[0].strip() for line in lines[1:-1]))

    # 3) toàn bộ bộ test (hay chỉ --chi-test), hai môi trường, lần lượt
    for name, python in ((".venv", VENV), (".venv-train", VENV_TRAIN)):
        ten = name.lstrip(".").replace("-", "_")
        xml, dau_ra = out / f"pytest_{ten}_{commit}.xml", out / f"pytest_{ten}_{commit}.dau_ra.txt"
        load, begin = cpu_load(), time.strftime("%H:%M:%S")
        r = chay([python, "-X", "utf8", *fh, "-m", "pytest", *(a.chi_test or []), "-p", "no:cacheprovider",
                  "--junitxml", xml], dau_ra, a.het_gio_pytest, env)
        them = sau_luot(r, dau_ra)
        j = junit(xml)
        so = (f"{j['tests']} test, {j['failures']} hỏng, {j['errors']} lỗi, {j['skipped']} bỏ qua, "
              f"{float(j['time']):.0f} s (JUnit), " if j else "JUnit thiếu hay không đọc được, ")
        log.append(f"{name}: bắt đầu {begin}, tải CPU {load} %, {mo_ta_ma(r)}, {so}{r['giay']:.0f} s (cả lệnh), "
                   f"ecoqos={j['ecoqos'] if j else '?'}, hỏng: {j['failed'] if j else '?'}; đầu ra {dau_ra.name}{them}")
    log.append(f"# kết thúc {time.strftime('%H:%M:%S')}")
    (out / f"chay_tren_commit_{commit}.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
