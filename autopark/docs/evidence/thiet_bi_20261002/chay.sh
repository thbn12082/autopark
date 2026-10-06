#!/usr/bin/env bash
# Lượt đo thiết bị thật chạy từ xa 02/10/2026 (người dùng không ở bàn; cho phép chạy thiết bị khi vắng người,
# ảnh cảnh chỉ lưu cục bộ trong runs/, không đưa lên Git). Chạy từ D:\xetulai\autopark\autopark.
O=runs/thiet_bi_20261002
cpu() { powershell -NoProfile -Command "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average"; }
dfree() { powershell -NoProfile -Command "[math]::Round((Get-PSDrive D).Free/1GB,1)"; }
log() { echo "$(date '+%d/%m/%Y %H:%M:%S') $*" | tee -a $O/nhat_ky.txt; }
log "bắt đầu; tải CPU $(cpu) %; ổ D trống $(dfree) GB"
log "1) camera_bench list"; .venv/Scripts/python.exe -X utf8 -m autopark.video.camera_bench list > $O/camera_list.txt 2>&1; log "exit=$?"
log "2) camera_bench measure 4 camera 640x480 60 s; tải CPU $(cpu) %"
.venv/Scripts/python.exe -X utf8 -m autopark.video.camera_bench measure --index 0 1 2 3 --width 640 --height 480 --seconds 60 --name m_4cam_480p_auto --out runs/camera_bench/20261002 > $O/camera_measure.txt 2>&1; log "exit=$?"
log "3) fusion.demo 30 s, LiDAR cổng của configs/thiet_bi.json, warmup 4,5 s; tải CPU $(cpu) %"
.venv/Scripts/python.exe -X utf8 -m autopark.fusion.demo --seconds 30 --warmup 4.5 > $O/fusion_demo.txt 2>&1; log "exit=$?"
log "4) rig.bench ghi thử 60 s (đo MB/s); tải CPU $(cpu) %; ổ D trống $(dfree) GB"
.venv-train/Scripts/python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 60 --name ld1_thu_ghi --out runs/rig_bench/20261002 --record runs/rig_recordings/20261002_ld1_thu_ghi > $O/ld1_thu_ghi.txt 2>&1; log "exit=$?"
MBPS=$(.venv/Scripts/python.exe -X utf8 -c "import json,glob; f=glob.glob('runs/rig_bench/20261002/ld1_thu_ghi*.rig.json'); d=json.load(open(f[0],encoding='utf-8')) if f else {}; print((d.get('recording') or {}).get('mb_per_s') or 0)")
FREE=$(dfree)
NEED=$(.venv/Scripts/python.exe -c "print(round(float('$MBPS')*1800/1024*1.25,1))")
log "MB/s ghi thử = $MBPS; LD-1 30 phút cần ≈ $NEED GB (đã cộng 25 %); ổ D trống $FREE GB"
REC=""
if .venv/Scripts/python.exe -c "import sys; sys.exit(0 if float('$MBPS')>0 and float('$FREE')-float('$NEED')>=15 else 1)"; then REC="--record runs/rig_recordings/20261002_ld1"; fi
log "5) LD-1 chạy thử 30 phút ${REC:-(không ghi phiên)}; tải CPU $(cpu) %"
.venv-train/Scripts/python.exe -X utf8 -m autopark.rig.bench --ports 1 2 3 4 --lidar --seconds 1800 --name ld1 --out runs/rig_bench/20261002 $REC > $O/ld1.txt 2>&1; log "exit=$?"
log "xong; tải CPU $(cpu) %; ổ D trống $(dfree) GB"
