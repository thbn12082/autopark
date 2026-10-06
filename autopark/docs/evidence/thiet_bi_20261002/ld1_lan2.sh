#!/usr/bin/env bash
# LD-1 chạy thử lần 2 (02/10/2026), kèm theo dõi bộ nhớ/ổ đĩa mỗi 10 s để biết vì sao lần 1 dừng ở t ≈ 1050 s.
O=runs/thiet_bi_20261002
log() { echo "$(date '+%d/%m/%Y %H:%M:%S') $*" | tee -a $O/nhat_ky.txt; }
powershell -NoProfile -ExecutionPolicy Bypass -File $O/theo_doi.ps1 -Out $O/theo_doi_ld1_lan2.csv -Seconds 2100 &
MON=$!
log "LD-1 lần 2: 30 phút, ghi phiên; tải CPU $(powershell -NoProfile -Command "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average") %"
.venv-train/Scripts/python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 1800 --name ld1_lan2 --out runs/rig_bench/20261002 --record runs/rig_recordings/20261002_ld1_lan2 > $O/ld1_lan2.txt 2>&1
RC=$?
log "LD-1 lần 2 exit=$RC (mã đầy đủ của Windows nếu khác 0 xem bằng PowerShell)"
kill $MON 2>/dev/null
