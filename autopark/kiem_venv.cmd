@echo off
rem Goi tu cai_dat.cmd va cai_dat_train.cmd: call kiem_venv.cmd <thu muc venv>. Ma 0 = dung duoc hoac chua co; 1 = dung lai.
rem venv chep tu may khac (pyvenv.cfg tro ve Python cua may cu) van co python.exe nhung khong chay ("No Python at ..."):
rem doi ten thanh <venv>.hong-tu-may-cu (khong xoa) de script tao venv moi. Xem docs\CHUYEN_MAY_BAN.md (29/09/2026).
if not exist "%~1\Scripts\python.exe" exit /b 0
"%~1\Scripts\python.exe" -c "import sys" >nul 2>nul && exit /b 0
if exist "%~1.hong-tu-may-cu" (
  echo %~1 khong chay duoc va da co %~1.hong-tu-may-cu: xoa hoac doi ten thu muc do roi chay lai.
  exit /b 1
)
echo %~1 khong chay duoc ^(thuong la chep tu may khac^): doi ten thanh %~nx1.hong-tu-may-cu roi tao moi.
ren "%~1" "%~nx1.hong-tu-may-cu"
if exist "%~1" exit /b 1
exit /b 0
