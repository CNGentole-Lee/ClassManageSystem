@echo off
REM Build the Windows installer with Inno Setup.
REM Usage: packaging\windows\make_installer.bat
REM Requires: PyInstaller output in dist\ClassManageSystem\ plus ISCC.exe.
setlocal

set "ROOT=%~dp0..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo [x] ISCC.exe not found. Install Inno Setup 6 first.
  exit /b 1
)
if not exist "%ROOT%\dist\ClassManageSystem\ClassManageSystem.exe" (
  echo [x] dist\ClassManageSystem\ClassManageSystem.exe not found.
  echo     Run packaging\windows\build.bat first.
  exit /b 1
)

for /f "tokens=2 delims==" %%v in ('findstr /b /c:"VERSION = " "%ROOT%\namepicker\about_dialog.py"') do set "VER=%%~v"
set "VER=%VER:"=%"

echo RepoRoot: %ROOT%
echo Version : %VER%
"%ISCC%" "/DRepoRoot=%ROOT%" "/DMyAppVersion=%VER%" "%ROOT%\packaging\windows\installer.iss"
if errorlevel 1 (
  echo [x] Inno Setup failed.
  exit /b 1
)
echo [i] installer written to %ROOT%\dist
endlocal
