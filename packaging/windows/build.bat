@echo off
REM ============================================================
REM  Build the Windows EXE (run this ON A WINDOWS MACHINE).
REM  PyInstaller cannot cross-compile, so this cannot run on macOS.
REM
REM  Output: dist\ClassManageSystem.exe
REM ============================================================
setlocal
cd /d "%~dp0..\.."

set "PY=python"
py -3.12 --version >nul 2>nul && set "PY=py -3.12"

echo [1/6] Python:
%PY% --version || goto :error

echo [2/6] Build venv (.venv-build):
if not exist ".venv-build" (
  %PY% -m venv .venv-build || goto :error
)
set "VPY=.venv-build\Scripts\python.exe"

echo [3/6] Installing dependencies:
"%VPY%" -m pip install --upgrade pip || goto :error
"%VPY%" -m pip install -r requirements.txt pyinstaller || goto :error

echo [4/6] Platform self-check (registry backup / SetWindowPos / encoding / locking):
"%VPY%" tools\windows_check.py || goto :error

echo [5/6] Storage and operation-log checks:
"%VPY%" tools\config_check.py || goto :error
"%VPY%" tools\config_crypto_check.py || goto :error
"%VPY%" tools\log_crypto_check.py || goto :error

echo [6/6] Building EXE:
"%VPY%" -m PyInstaller packaging\windows\ClassManageSystem.spec --noconfirm --clean || goto :error

echo.
echo ============================================================
echo  DONE
echo  Output: %CD%\dist\ClassManageSystem.exe
echo ============================================================
exit /b 0

:error
echo.
echo ============================================================
echo  BUILD FAILED - see the messages above
echo ============================================================
exit /b 1
