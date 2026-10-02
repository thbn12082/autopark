"""Chạy lại trên một commit sạch (01/10/2026; bản sửa từ docs/evidence/mo_phong_20260930/chay_tren_commit.py: ngày lấy
lúc chạy, thư mục kết quả là tham số): bo ảo `kiem`, chạy lặp tests/test_firmware_qemu.py 10 lượt, rồi toàn bộ bộ test
ở `.venv` và `.venv-train` (offscreen). Chạy trong thư mục autopark của repo:

    .venv\\Scripts\\python.exe -X utf8 <đường dẫn script> <commit> <thư mục kết quả>

Gọi pytest bằng subprocess, không qua pytest.main, nên tiến trình con của test không chạy lại script này."""
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

VENV = Path(".venv/Scripts/python.exe")
VENV_TRAIN = Path(".venv-train/Scripts/python.exe")


def cpu_load() -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average"],
                       capture_output=True, text=True)
    return r.stdout.strip() or "?"


def junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    props = {p.get("name"): p.get("value") for p in suite.iter("property")}
    failed = [c.get("classname") + "::" + c.get("name") for c in suite.iter("testcase")
              if c.find("failure") is not None or c.find("error") is not None]
    return {k: suite.get(k) for k in ("tests", "failures", "errors", "skipped", "time")} | {
        "ecoqos": props.get("ecoqos"), "failed": failed}


def main() -> int:
    commit, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    day = time.strftime("%d/%m/%Y")
    log = [f"# Chạy trên commit {commit} (cây làm việc sạch), máy bàn, bắt đầu {day} {time.strftime('%H:%M:%S')}"]

    # 1) bo ảo: kiem
    t0 = time.strftime("%H:%M")
    r = subprocess.run([str(VENV), "-X", "utf8", "-m", "autopark.transport.qemu_board", "kiem"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    (out / f"kiem_bo_ao_{commit}.txt").write_text(
        f"$ python -X utf8 -m autopark.transport.qemu_board kiem   ({day} {t0}, máy bàn, commit {commit})\n"
        + r.stdout + r.stderr + f"exit={r.returncode}\n", encoding="utf-8")
    log.append(f"kiem: exit={r.returncode}")

    # 2) bo ảo: chạy lặp 10 lượt
    lines = [f"# Chạy lặp tests/test_firmware_qemu.py, commit {commit}, máy bàn, bắt đầu {day} {time.strftime('%H:%M:%S')}"]
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(1, 11):
            xml = Path(tmp) / f"lap_{i}.xml"
            start = time.monotonic()
            r = subprocess.run([str(VENV), "-X", "utf8", "-m", "pytest", "tests/test_firmware_qemu.py",
                                "-p", "no:cacheprovider", "--junitxml", str(xml)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
            text = r.stdout + r.stderr
            j = junit(xml)
            passed = int(j["tests"]) - int(j["failures"]) - int(j["errors"]) - int(j["skipped"])
            lines.append(f"lượt {i:2d}: {passed} đạt, {j['failures']} hỏng, {j['errors']} lỗi, {j['skipped']} bỏ qua; "
                         f"cảnh báo QEMU tự thoát (#175): {text.count('espressif/qemu#175')}; "
                         f"cảnh báo LOOP_OVERRUN: {text.count('LOOP_OVERRUN (máy bận)')}; "
                         f"{time.monotonic() - start:.0f}s")
    lines.append(f"# kết thúc {time.strftime('%H:%M:%S')}")
    (out / f"chay_lap_test_bo_ao_{commit}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.append("chạy lặp: " + "; ".join(line.split(":", 1)[1].split(";")[0].strip() for line in lines[1:-1]))

    # 3) toàn bộ bộ test, hai môi trường, lần lượt
    for name, python in ((".venv", VENV), (".venv-train", VENV_TRAIN)):
        xml = out / f"pytest_{name.lstrip('.').replace('-', '_')}_{commit}.xml"
        load, begin, start = cpu_load(), time.strftime("%H:%M:%S"), time.monotonic()
        r = subprocess.run([str(python), "-X", "utf8", "-m", "pytest", "-p", "no:cacheprovider", "--junitxml", str(xml)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        j = junit(xml)
        log.append(f"{name}: bắt đầu {begin}, tải CPU {load} %, exit={r.returncode}, {j['tests']} test, "
                   f"{j['failures']} hỏng, {j['errors']} lỗi, {j['skipped']} bỏ qua, {float(j['time']):.0f} s (JUnit), "
                   f"{time.monotonic() - start:.0f} s (cả lệnh), ecoqos={j['ecoqos']}, hỏng: {j['failed']}")
    log.append(f"# kết thúc {time.strftime('%H:%M:%S')}")
    (out / f"chay_tren_commit_{commit}.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
