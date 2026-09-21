@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chua co moi truong .venv. Chay cai_dat.cmd truoc.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run_app.py %*
