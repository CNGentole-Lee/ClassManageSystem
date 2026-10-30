@echo off
REM Windows: double-click to run the full test suite.
cd /d "%~dp0.."

set "PY=.conda\python.exe"
if not exist "%PY%" set "PY=.venv-build\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo Using interpreter: %PY%
"%PY%" tools\run_all_tests.py %*
set CODE=%ERRORLEVEL%

echo.
pause
exit /b %CODE%
