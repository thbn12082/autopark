"""Biên dịch lõi firmware C++ (`firmware/esp32_vehicle/test/host`, cmake) và chạy nó trên `test/vectors.json`.

Bỏ qua khi máy không có cmake hoặc trình biên dịch C++ trên PATH (laptop nộp đồ án, máy bàn cũ), và trên Windows khi
đường dẫn repo hay thư mục tạm có ký tự ngoài bảng mã ANSI (ví dụ `D:\\gấp`, tên repo trên máy bàn tới 29/09/2026):
ninja và argv của exe MinGW đi qua bảng mã đó nên không mở được. Máy có công cụ thì build lỗi hay lệch vector là HỎNG,
không bỏ qua. Chỉ phủ `src/core`; `src/main.cpp` (lớp dán Arduino) không build ở đây. Build vào thư mục tạm, không đụng
`firmware/esp32_vehicle/build`."""
import json
import locale
import os
import re
import shutil
import subprocess

import pytest

from autopark.transport.vectors import DEFAULT_PATH

HOST_DIR = DEFAULT_PATH.parent / "host"
_COMPILERS = ("c++", "g++", "clang++", "cl")

pytestmark = pytest.mark.skipif(
    shutil.which("cmake") is None or not any(shutil.which(c) for c in _COMPILERS),
    reason="không có cmake hoặc trình biên dịch C++ trên PATH",
)


def _run(args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                          **kwargs)


@pytest.fixture(scope="module")
def host_tests(tmp_path_factory):
    build = tmp_path_factory.mktemp("firmware_host")
    if os.name == "nt":
        try:
            for path in (HOST_DIR, DEFAULT_PATH, build):     # test sau dùng tmp_path cùng thư mục gốc với `build`
                str(path).encode(locale.getencoding())       # bảng mã ANSI, kể cả khi chạy -X utf8
        except UnicodeEncodeError:
            pytest.skip("đường dẫn repo/thư mục tạm có ký tự ngoài bảng mã ANSI: ninja và exe MinGW không mở được")
    for args in (["cmake", "-S", str(HOST_DIR), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release"],
                 ["cmake", "--build", str(build), "--config", "Release"]):
        r = _run(args)
        assert r.returncode == 0, f"{' '.join(args)}\n{r.stdout}\n{r.stderr}"
    # Ninja/Makefile để exe ở gốc thư mục build; Visual Studio để ở Release/.
    exes = [p for p in build.rglob("host_tests*") if p.is_file() and p.suffix in ("", ".exe")]
    assert len(exes) == 1, exes
    return exes[0]


def test_cpp_core_matches_every_vector(host_tests):
    r = _run([str(host_tests), str(DEFAULT_PATH)])
    match = re.fullmatch(r"(\d+) checks, (\d+) failures", r.stdout.strip())
    assert r.returncode == 0 and match and match.group(2) == "0", f"{r.stdout}\n{r.stderr}"
    # 703 check lúc viết (29/09/2026); sàn thấp hơn để thêm/bớt vector không phải sửa test, nhưng đọc rỗng thì hỏng.
    assert int(match.group(1)) >= 500


def test_cpp_host_test_fails_on_a_wrong_vector(host_tests, tmp_path):
    """Vector sai một bit phải làm exe báo lệch và thoát 1 (nếu không, bài test trên đạt cho có)."""
    vectors = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    vectors["crc16"][0]["crc"] ^= 1
    bad = tmp_path / "vectors_sai.json"
    bad.write_text(json.dumps(vectors), encoding="utf-8")
    r = _run([str(host_tests), str(bad)])
    assert r.returncode == 1 and r.stdout.strip().endswith(" 1 failures"), f"{r.stdout}\n{r.stderr}"
