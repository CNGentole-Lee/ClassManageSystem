@echo off
REM ============================================================
REM  Build the Windows EXE [run this ON A WINDOWS MACHINE].
REM  PyInstaller cannot cross-compile, so this cannot run on macOS.
REM
REM  Usage:
REM      packaging\windows\build.bat
REM          AUTO-SELECT. Probes every candidate index and uses the
REM          fastest one that answers. No country check, no guessing:
REM          it measures.  [see "How auto-select works" below]
REM      packaging\windows\build.bat official
REM          Force the official PyPI; skip probing entirely.
REM      packaging\windows\build.bat https://your.mirror/simple
REM          Force one index. The trusted host is parsed from the URL.
REM
REM  How auto-select works:
REM      1. curl.exe sends a 1 KB ranged request to each candidate and
REM         reports two numbers: HTTP status and time_total [seconds].
REM      2. time_total is converted to whole milliseconds in pure batch
REM         [batch has no floats].  "0.042" -> "0" + "042" -> 42 ms.
REM      3. The candidate with the SMALLEST ms wins.  000 = unreachable.
REM      4. No curl [Windows older than 17063]?  Probing is skipped and
REM         the built-in order is used instead: Tsinghua > Aliyun >
REM         pypi.org - still China-mirrors-first, just without timing.
REM      5. If the winner dies mid-install, the script retries with the
REM         next candidate instead of aborting on the first timeout.
REM
REM  The index only applies to this script; it does NOT change your
REM  system-wide pip config [no pip.ini is written].
REM
REM  Output: dist\ClassManageSystem.exe
REM ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0..\.."

REM ---- 1] Candidate indexes [built-in order: China mirrors first] ----
set "CAND_N=3"
set "CAND_NAME[1]=Tsinghua"
set "CAND_URL[1]=https://pypi.tuna.tsinghua.edu.cn/simple"
set "CAND_HOST[1]=pypi.tuna.tsinghua.edu.cn"
set "CAND_NAME[2]=Aliyun"
set "CAND_URL[2]=https://mirrors.aliyun.com/pypi/simple"
set "CAND_HOST[2]=mirrors.aliyun.com"
set "CAND_NAME[3]=pypi.org"
set "CAND_URL[3]=https://pypi.org/simple"
set "CAND_HOST[3]=pypi.org"

REM ---- 2] Build the working list from %1 ----
set "LIST_N=0"
set "PROBE=1"
if /i "%~1"=="official" (
  set "LIST_N=1"
  set "LIST_NAME[1]=pypi.org"
  set "LIST_URL[1]=https://pypi.org/simple"
  set "LIST_HOST[1]=pypi.org"
  set "PROBE=0"
) else if not "%~1"=="" (
  set "LIST_N=1"
  set "LIST_NAME[1]=custom"
  set "LIST_URL[1]=%~1"
  set "LIST_HOST[1]="
  for /f "tokens=3 delims=/" %%h in ("%~1") do set "LIST_HOST[1]=%%h"
  set "PROBE=0"
) else (
  for /L %%k in (1,1,!CAND_N!) do (
    set /a "LIST_N+=1"
    set "LIST_NAME[!LIST_N!]=!CAND_NAME[%%k]!"
    set "LIST_URL[!LIST_N!]=!CAND_URL[%%k]!"
    set "LIST_HOST[!LIST_N!]=!CAND_HOST[%%k]!"
  )
)

REM ---- 3] Probe: pick the fastest reachable index ----
set "PICK=1"
if "!PROBE!"=="0" goto :probe_done
where curl.exe >nul 2>nul
if errorlevel 1 (
  echo [i] curl not found - skipping probe, using built-in order
  goto :probe_done
)

echo [i] probing !LIST_N! indexes, picking the fastest:
set "BEST_MS="
for /L %%k in (1,1,!LIST_N!) do call :probe_one %%k
if not defined BEST_MS (
  echo [i] none answered - using built-in order
  goto :probe_done
)
set "SEL_NAME=!LIST_NAME[%PICK%]!"
echo [i] selected: !SEL_NAME! [!BEST_MS! ms, fastest reachable]
:probe_done

REM ---- 4] Build pip arg list ----
REM NOTE: --trusted-host must be appended LAST and only when a host was
REM parsed. A dangling "--trusted-host" with no value makes pip swallow
REM the NEXT option as the hostname [it eats --timeout] instead of
REM failing loudly - that silently drops the timeout back to pip default.
set "PIP_OPTS=--timeout 60 --retries 5"

set "PY=python"
py -3.12 --version >nul 2>nul && set "PY=py -3.12"

echo [1/6] Python:
%PY% --version || goto :error

echo [2/6] Build venv .venv-build:
if not exist ".venv-build" (
  %PY% -m venv .venv-build || goto :error
)
set "VPY=.venv-build\Scripts\python.exe"

echo [3/6] Installing dependencies:
set "INSTALLED=0"
for /L %%k in (!PICK!,1,!LIST_N!) do (
  if "!INSTALLED!"=="0" call :try_install %%k
)
if "!INSTALLED!"=="0" goto :error

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
REM ---- 7] GPL-3.0: the licence must be INSIDE the single EXE ----
REM We ship one EXE; the user gets no other files, so LICENSE has to be
REM bundled (spec datas -> unpacked to _MEIPASS at runtime, read by the
REM About dialog). The spec already aborts the build if it is missing;
REM this is a second, visible check on the produced artifact.
if not exist "LICENSE" (
  echo [x] LICENSE missing in project root - refusing to ship a build
  goto :error
)
if not exist "dist\ClassManageSystem.exe" (
  echo [x] dist\ClassManageSystem.exe was not produced
  goto :error
)
echo [i] LICENSE is bundled inside the EXE [the About dialog reads it]

echo.
echo ============================================================
echo  DONE
echo  Output: %CD%\dist\ClassManageSystem.exe
echo  Distribute: dist\ClassManageSystem.exe  [single file, LICENSE inside]
echo ============================================================
exit /b 0

REM ============================================================
REM  :probe_one %1 = index number
REM  Sets BEST_MS / PICK when this index is reachable and faster.
REM ============================================================
:probe_one
set "K=%1"
set "CODE="
set "SEC="
for /f "usebackq tokens=1,2" %%c in (`curl.exe -s -o nul -w "%%{http_code} %%time_total" --max-time 8 -r 0-1023 "!LIST_URL[%K%]!" 2^>nul`) do (
  set "CODE=%%c"
  set "SEC=%%d"
)
if not defined SEC goto :probe_unreachable
if "!CODE!"=="000" goto :probe_unreachable

REM "0.042" -> whole seconds "0", fraction "042"
for /f "tokens=1,2 delims=." %%s in ("!SEC!") do (
  set "S=%%s"
  set "F=%%t"
)
if not defined F set "F=0"
REM Pad to exactly 3 digits so "5" means 500 ms, not 5 ms.
set "F3=!F!000"
set "F3=!F3:~0,3!"
REM "1!F3!-1000" keeps leading zeros out of octal: batch reads 042 as
REM 34 decimal, but 1042-1000 is the 42 we actually want.
set /a "MS=1!F3!-1000"
if defined S (
  if not "!S!"=="0" set /a "MS+=!S!*1000"
)
echo     !LIST_NAME[%K%]!  -> !CODE!  !MS! ms
if not defined BEST_MS (
  set "BEST_MS=!MS!"
  set "PICK=!K!"
) else if !MS! LSS !BEST_MS! (
  set "BEST_MS=!MS!"
  set "PICK=!K!"
)
goto :eof

:probe_unreachable
echo     !LIST_NAME[%K%]!  -> unreachable
goto :eof

REM ============================================================
REM  :try_install %1 = index number.  Sets INSTALLED=1 on success.
REM ============================================================
:try_install
set "K=%1"
set "MIRROR=!LIST_URL[%K%]!"
set "TRUSTED=!LIST_HOST[%K%]!"
set "PIP_MIRROR="
if defined MIRROR set "PIP_MIRROR=-i !MIRROR!"
if defined TRUSTED set "PIP_MIRROR=!PIP_MIRROR! --trusted-host !TRUSTED!"
echo     trying [!K!/!LIST_N!] !LIST_NAME[%K%]!
"%VPY%" -m pip install --upgrade pip !PIP_MIRROR! %PIP_OPTS%
if errorlevel 1 goto :ti_fail
"%VPY%" -m pip install -r requirements.txt pyinstaller !PIP_MIRROR! %PIP_OPTS%
if errorlevel 1 goto :ti_fail
set "INSTALLED=1"
goto :eof

:ti_fail
echo [!] !LIST_NAME[%K%]! failed, trying next index...
goto :eof

:error
echo.
echo ============================================================
echo  BUILD FAILED - see the messages above
echo ============================================================
echo  If every index failed while DOWNLOADING, pass one by hand:
echo    packaging\windows\build.bat official
echo    packaging\windows\build.bat https://your.mirror/simple
echo.
echo  If it failed on a MISSING DLL or import, it is not the network:
echo  read the error above instead of switching mirrors.
echo ============================================================
exit /b 1
