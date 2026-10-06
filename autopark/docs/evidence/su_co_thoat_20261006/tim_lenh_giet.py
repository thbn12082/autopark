"""Tìm lệnh có thể giết tiến trình python (Stop-Process, taskkill, .Kill(), kill, TerminateProcess, wmic … delete)
trong MỌI bản ghi phiên Claude Code trên máy (<thư mục người dùng>/.claude/projects/**/*.jsonl), trong một khoảng giờ
UTC. Chỉ đọc. Việc 8, 06/10/2026.

Bản trong repo (06/10/2026), sửa theo phản biện: thư mục bản ghi lấy theo Path.home() (bản nháp viết cứng đường dẫn
hồ sơ của máy bàn, sang máy khác sẽ quét 0 tệp mà không báo); báo rõ và thoát mã 2 khi quét 0 tệp; thêm --pid. Sửa lần
hai (06/10/2026 tối): với --pid, lệnh giết python theo tên chỉ in giờ và loại lệnh (bản trước in cả câu lệnh).

Hai chế độ:
- có --pid (chay_co_theo_doi.py dùng): tách lệnh thành câu (theo ; && || và xuống dòng), chỉ xét câu lệnh giết.
  Câu có một trong các PID đó (số đứng riêng): in nguyên câu (cắt 200 ký tự), kèm giờ và tên công cụ. Câu không có PID
  đó nhưng có chữ "python" (coi là giết python theo tên, hay theo cỡ): chỉ in giờ, tên công cụ và loại lệnh, dạng
  "lệnh giết python theo tên (Stop-Process; không nhắm PID đang tìm); dòng lệnh không ghi". Câu khác: bỏ qua. KHÔNG in
  thư mục dự án, tệp bản ghi hay phần còn lại của lệnh; dòng lệnh chỉ được in khi nhắm đúng PID đang tìm.
- không có --pid (tra tay): in mọi lệnh khớp, kèm thư mục dự án và tệp bản ghi, cắt 700 ký tự. Kết quả có thể chứa
  đường dẫn và lệnh của dự án khác: ĐỪNG chép vào repo.
Chỉ thấy lệnh do phiên Claude Code chạy (công cụ Bash, PowerShell, Monitor); lệnh người gõ tay hay chương trình khác
không có ở đây.

Dùng: tim_lenh_giet.py 2026-10-02T07:20 2026-10-02T07:35 [--pid 26456 --pid 33860]
"""
import argparse
import json
import re
import sys
from pathlib import Path

GIET = (r"Stop-Process|taskkill|\.Kill\(|\bkill\b|TerminateProcess|wmic\s+process|pkill|killall|"
        r"\.terminate\(\)|\.kill\(\)|os\.kill|signal\.SIG")
PAT = re.compile(GIET + r"|Get-Process\s+python", re.I)
TACH = re.compile(r";|&&|\|\||\r?\n")                    # ranh giới câu lệnh (dấu | đơn là ống, không tách)
PROJ = Path.home() / ".claude" / "projects"


def hien_thi(p: Path) -> str:
    return str(p).replace(str(Path.home()), "~")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tu", help="giờ UTC bắt đầu, dạng 2026-10-02T07:20[:00]")
    ap.add_argument("den", help="giờ UTC kết thúc")
    ap.add_argument("--pid", type=int, action="append", default=[],
                    help="chỉ in nguyên câu lệnh giết nhắm PID này (lặp được); lệnh giết python theo tên chỉ in giờ "
                         "và loại lệnh; không in lệnh nào khác")
    a = ap.parse_args()
    files = sorted(PROJ.glob("**/*.jsonl"))
    if not files:
        print(f"KHÔNG QUÉT ĐƯỢC: 0 tệp bản ghi phiên trong {hien_thi(PROJ)} (máy khác? Claude Code chưa chạy ở đây?)")
        return 2
    pid_re = re.compile(r"(?<!\d)(" + "|".join(str(x) for x in a.pid) + r")(?!\d)") if a.pid else None
    giet_re = re.compile(GIET, re.I)
    hits = []
    so_pid = so_ten = 0
    for f in files:
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"timestamp":"' not in line:
                    continue
                m = re.search(r'"timestamp":"([^"]+)"', line)
                if not m or not (a.tu <= m.group(1) <= a.den):
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                content = (rec.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not (isinstance(part, dict) and part.get("type") == "tool_use"
                            and part.get("name") in ("Bash", "PowerShell", "Monitor")):   # lệnh thật sự chạy
                        continue
                    cmd = str((part.get("input") or {}).get("command") or "")
                    if not PAT.search(cmd):
                        continue
                    if pid_re is None:
                        hits.append((m.group(1), str(f.relative_to(PROJ))[-90:], part.get("name"), cmd[:700]))
                        continue
                    for c in TACH.split(cmd):
                        c = c.strip()
                        g = giet_re.search(c)
                        if not g:
                            continue
                        if pid_re.search(c):                       # nhắm đúng PID đang tìm: in nguyên câu
                            hits.append((m.group(1), "", part.get("name"), c[:200]))
                            so_pid += 1
                        elif re.search(r"python", c, re.I):         # giết python theo tên: chỉ giờ và loại lệnh
                            hits.append((m.group(1), "", part.get("name"),
                                         f"lệnh giết python theo tên ({g.group(0)}; không nhắm PID đang tìm); "
                                         "dòng lệnh không ghi"))
                            so_ten += 1
    hits.sort()
    if pid_re is None:
        print("số tệp bản ghi quét:", len(files), "; số lệnh khớp:", len(hits))
    else:
        print(f"số tệp bản ghi quét: {len(files)} ; số câu lệnh giết nhắm PID {', '.join(map(str, a.pid))}: {so_pid}"
              f" ; số lệnh giết python theo tên (chỉ ghi giờ): {so_ten}")
    for gio, tep, cong_cu, lenh in hits:
        if tep:
            print("=" * 20, gio, tep, cong_cu)
        else:
            print("=" * 20, gio, cong_cu)
        print(lenh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
