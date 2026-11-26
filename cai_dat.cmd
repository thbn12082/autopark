@echo off
cd /d "%~dp0"
call "%~dp0kiem_venv.cmd" .venv || goto end
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install -r requirements-phase0.lock
if errorlevel 1 goto end
".venv\Scripts\python.exe" -m pip install -e . --no-deps
:end
pause
