@echo off
REM ============================================================
REM  Build the Windows EXE [run this ON A WINDOWS MACHINE].
REM  PyInstaller cannot cross-compile, so this cannot run on macOS.
REM
REM  Usage:
REM      packaging\windows\build.bat
REM          Default: Tsinghua PyPI mirror [fast in mainland China].
REM      packaging\windows\build.bat official
REM          Use the official PyPI.
REM      packaging\windows\build.bat https://mirrors.aliyun.com/pypi/simple/
REM          Use a custom mirror.
REM
REM  The mirror only applies to this script; it does NOT change your
REM  system-wide pip config [no pip.ini is written].
REM
REM  Output: dist\ClassManageSystem.exe
REM ============================================================
setlocal
cd /d "%~dp0..\.."

REM ---- 1] pip mirror [default: Tsinghua] ----
set "MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple"
set "TRUSTED=pypi.tuna.tsinghua.edu.cn"
if /i "%~1"=="official" (
  set "MIRROR="
  set "TRUSTED="
) else if not "%~1"=="" (
  set "MIRROR=%~1"
  set "TRUSTED="
)
if defined MIRROR (
  echo [i] pip mirror: %MIRROR%
) else (
  echo [i] pip mirror: official PyPI
)

set "PY=python"
py -3.12 --version >nul 2>nul && set "PY=py -3.12"

echo [1/6] Python:
%PY% --version || goto :error

echo [2/6] Build venv .venv-build:
if not exist ".venv-build" (
  %PY% -m venv .venv-build || goto :error
)
set "VPY=.venv-build\Scripts\python.exe"

REM Mirror args as one variable; empty when using the official index.
set "PIP_MIRROR="
if defined MIRROR set "PIP_MIRROR=-i %MIRROR% --trusted-host %TRUSTED%"
REM Big wheels [PyQt5 is about 50 MB] need a longer timeout and retries.
set "PIP_OPTS=--timeout 60 --retries 5"

echo [3/6] Installing dependencies:
"%VPY%" -m pip install --upgrade pip %PIP_MIRROR% %PIP_OPTS% || goto :error
"%VPY%" -m pip install -r requirements.txt pyinstaller %PIP_MIRROR% %PIP_OPTS% || goto :error

echo [4/6] Platform self-check: registry backup / SetWindowPos / encoding / file locking
"%VPY%" tools\windows_check.py || goto :error

echo [5/6] Storage and operation-log checks:
"%VPY%" tools\config_check.py || goto :error
"%VPY%" tools\config_crypto_check.py || goto :error
"%VPY%" tools\log_crypto_check.py || goto :error

echo [6/6] Building EXE:
REM Keep PyInstaller cache inside the project, not in %LOCALAPPDATA%.
set "PYINSTALLER_CONFIG_DIR=%CD%\.pyinstaller-cache"
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
echo  If it stalled while downloading, retry with another mirror:
echo    packaging\windows\build.bat https://mirrors.aliyun.com/pypi/simple/
echo ============================================================
exit /b 1
