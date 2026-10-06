#!/usr/bin/env bash
# Tái hiện cơ chế LD-1 lần 1 trên một tiến trình vô hại của chính mình: Git Bash chạy venv launcher -> python gốc;
# một PowerShell khác gọi Stop-Process -Id <pid python gốc> -Force. Đo: $? bash thấy, mã đầy đủ, độ trễ từ lúc gọi
# powershell tới lần ghi cuối của tiến trình con. Không đụng tiến trình nào khác. Việc 8, 06/10/2026.
S="$(cd "$(dirname "$0")" && pwd)"
VENV=/d/xetulai/autopark/autopark/.venv/Scripts/python.exe
for lan in 1 2 3; do
  rm -f "$S/con.pid" "$S/con.out"
  "$VENV" -X utf8 "$S/con_ngu.py" "$S/con.pid" "$S/con.out" &
  BG=$!
  for i in $(seq 1 200); do [ -s "$S/con.pid" ] && break; sleep 0.05; done
  sleep 0.5
  P=$(cat "$S/con.pid")
  T_CALL=$(date +%s.%N)
  powershell -NoProfile -Command "Stop-Process -Id $P -Force"
  T_RET=$(date +%s.%N)
  wait $BG; RC=$?
  LAST=$(tail -1 "$S/con.out")
  python_line=$("$VENV" -c "print(f'tre_tu_luc_goi_toi_lan_ghi_cuoi={float(\"$LAST\")-float(\"$T_CALL\"):.3f}s  powershell_chay={float(\"$T_RET\")-float(\"$T_CALL\"):.3f}s')")
  echo "lần $lan: pid python gốc=$P  bash \$?=$RC  $python_line"
done
# mã đầy đủ mà venv launcher trả khi con bị Stop-Process (xem bằng PowerShell, như gợi ý trong ld1_lan2.sh)
powershell -NoProfile -Command "\$p = Start-Process -FilePath '$(cygpath -w "$VENV")' -ArgumentList '-X','utf8','$(cygpath -w "$S/con_ngu.py")','$(cygpath -w "$S/con2.pid")','$(cygpath -w "$S/con2.out")' -PassThru -WindowStyle Hidden; for (\$i=0; \$i -lt 100 -and -not (Test-Path '$(cygpath -w "$S/con2.pid")'); \$i++) { Start-Sleep -Milliseconds 50 }; Start-Sleep -Milliseconds 300; \$c = [int](Get-Content '$(cygpath -w "$S/con2.pid")'); Stop-Process -Id \$c -Force; \$p.WaitForExit(); 'launcher ExitCode = ' + \$p.ExitCode + ' = 0x' + ('{0:X8}' -f \$p.ExitCode)"
rm -f "$S/con.pid" "$S/con.out" "$S/con2.pid" "$S/con2.out"
