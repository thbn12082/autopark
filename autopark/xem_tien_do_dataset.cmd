@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 -c "from pathlib import Path; print(Path('datasets/TRANG_THAI_TAI_DAY_DU.md').read_text(encoding='utf-8'))"
pause
