@echo off
rem Kiem may moi bang mot lenh: cau hinh, cong USB, LiDAR, toc do AI, ban thu 480p va 720p (khoang 4 phut).
rem Ket qua: runs\may_moi_<ngay gio>\tom_tat.md. Xem docs\MAY_NOP_DO_AN.md.
cd /d "%~dp0"
if not exist ".venv-train\Scripts\python.exe" (
  echo Chua co .venv-train. Chay cai_dat_train.cmd truoc.
  pause
  exit /b 1
)
".venv-train\Scripts\python.exe" -X utf8 -m autopark.rig.may_moi %*
pause
