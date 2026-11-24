@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chua co moi truong .venv. Chay cai_dat.cmd truoc.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 -m autopark.ui.remote_sensor_view %*
if errorlevel 1 pause
