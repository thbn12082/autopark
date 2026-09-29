@echo off
rem Cai moi truong .venv-train (torch CUDA 12.8, ban thu, hieu chuan, gan nhan) theo requirements-train.lock.
rem Can Python 3.12 va driver NVIDIA ho tro CUDA 12.8. Xem docs\MAY_NOP_DO_AN.md.
cd /d "%~dp0"
call "%~dp0kiem_venv.cmd" .venv-train || goto end
if not exist ".venv-train\Scripts\python.exe" (
  where py >nul 2>nul && (py -3.12 -m venv .venv-train) || (python -m venv .venv-train)
)
if not exist ".venv-train\Scripts\python.exe" (
  echo Khong tao duoc .venv-train. Cai Python 3.12 truoc.
  goto end
)
".venv-train\Scripts\python.exe" -m pip install -r requirements-train.lock --index-url https://download.pytorch.org/whl/cu128 --extra-index-url https://pypi.org/simple
if errorlevel 1 goto end
".venv-train\Scripts\python.exe" -m pip install -e . --no-deps
".venv-train\Scripts\python.exe" -c "import torch; ok = torch.cuda.is_available(); print('torch', torch.__version__, '| CUDA', ok, '|', torch.cuda.get_device_name(0) if ok else 'KHONG THAY GPU')"
:end
pause
