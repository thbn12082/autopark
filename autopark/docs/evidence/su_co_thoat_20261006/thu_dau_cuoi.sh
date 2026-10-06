#!/usr/bin/env bash
# Thử đầu–cuối bộ theo dõi trên tiến trình VÔ HẠI của chính mình (06/10/2026): chay_co_theo_doi.py chạy con_ngu.py
# (ngủ, ghi thời gian); sau 8 s, một PowerShell khác Stop-Process đúng PID python gốc (như 02/10/2026 14:29:12).
# Kỳ vọng: tom_tat.json mã 0xFFFFFFFF; su_kien.txt có "LỆNH GIẾT (log Windows PowerShell …)" và "THOÁT … 0xFFFFFFFF".
# Bản trong repo (06/10/2026): thư mục kết quả là tham số (mặc định runs/su_co_thoat/thu_dau_cuoi_<ngày giờ>) và phải
# chưa có; bản nháp xóa (rm -rf) thư mục thu_dau_cuoi/ cạnh script, tức sẽ xóa kết quả lưu trong thư mục bằng chứng này.
# Dùng (Git Bash): bash thu_dau_cuoi.sh [thư mục kết quả mới]
S="$(cd "$(dirname "$0")" && pwd)"
A="$(cd "$S/../../.." && pwd)"                # thư mục autopark của repo
R="${1:-$A/runs/su_co_thoat/thu_dau_cuoi_$(date +%Y%m%d_%H%M%S)}"
[ -e "$R" ] && { echo "thư mục $R đã có; chọn thư mục mới"; exit 2; }
mkdir -p "$R" || exit 2
cd "$A" || exit 1
.venv/Scripts/python.exe -X utf8 "$S/chay_co_theo_doi.py" --ra "$R" --theo-doi --khoang 5 --toi-da 90 --cho-wer 2 -- \
  .venv/Scripts/python.exe -X utf8 "$S/con_ngu.py" "$R/con.pid" "$R/con.out" &
W=$!
for i in $(seq 1 100); do [ -s "$R/pids.txt" ] && grep -q "python=" "$R/pids.txt" && break; sleep 0.2; done
sleep 8
P=$(grep "python=" "$R/pids.txt" | cut -d= -f2 | tr -d '\r')
echo "giết python gốc pid $P lúc $(date +%H:%M:%S.%N | cut -c1-12)"
powershell -NoProfile -Command "Stop-Process -Id $P -Force -ErrorAction SilentlyContinue"
wait $W; echo "wrapper thoát, bash \$?=$?"
sleep 22
echo "--- su_kien.txt"; cat "$R/theo_doi/su_kien.txt"
echo "--- tom_tat (mã)"; grep -E '"ma_|"nghia_|"gio_thoat|git_bash' "$R/tom_tat.json"
