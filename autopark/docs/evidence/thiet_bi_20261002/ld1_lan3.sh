#!/usr/bin/env bash
# LD-1 lần 3 (02/10/2026): chạy từ cây đã gộp đợt 2 (worktree D:\xetulai\_wt\gop) có bản sửa driver C1 (đọc bỏ byte cũ),
# kèm theo dõi bộ nhớ/ổ đĩa mỗi 10 s. Kết quả ghi vào runs/ của cây chính.
M=/d/xetulai/autopark/autopark
O=$M/runs/thiet_bi_20261002
log() { echo "$(date '+%d/%m/%Y %H:%M:%S') $*" | tee -a $O/nhat_ky.txt; }
cd /d/xetulai/_wt/gop/autopark || exit 1
PY=$M/.venv-train/Scripts/python.exe
log "LD-1 lần 3: mã $($PY -c 'import autopark, os; print(os.path.dirname(autopark.__file__))'); tải CPU $(powershell -NoProfile -Command "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average") %; ổ D trống $(powershell -NoProfile -Command "[math]::Round((Get-PSDrive D).Free/1GB,1)") GB"
powershell -NoProfile -ExecutionPolicy Bypass -File $O/theo_doi.ps1 -Out $O/theo_doi_ld1_lan3.csv -Seconds 2100 &
MON=$!
$PY -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 1800 --name ld1_lan3 --checkpoint $M/runs/ai_woodscape_rtx4000_v1/best.pt --out $M/runs/rig_bench/20261002 --record $M/runs/rig_recordings/20261002_ld1_lan3 > $O/ld1_lan3.txt 2>&1
RC=$?
log "LD-1 lần 3 exit=$RC; tải CPU $(powershell -NoProfile -Command "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average") %; ổ D trống $(powershell -NoProfile -Command "[math]::Round((Get-PSDrive D).Free/1GB,1)") GB"
kill $MON 2>/dev/null
