@echo off
rem Build the whole AirMirror installer:
rem   1) freeze the Python tray app with PyInstaller
rem   2) build the portable UxPlay + GStreamer bundle (MSYS2 UCRT64)
rem   3) compile the Inno Setup script
setlocal

cd /d "%~dp0"

echo === 1/3 PyInstaller ===
python -m PyInstaller --noconfirm --clean --windowed --name AirMirror ^
  --icon airmirror.ico --add-data "airmirror.ico;." AirMirror.py
if errorlevel 1 goto :fail

echo === 2/3 portable UxPlay bundle ===
if not defined MSYS2_ROOT set "MSYS2_ROOT=C:\msys64"
if not exist "%MSYS2_ROOT%\msys2_shell.cmd" (
  echo ERROR: MSYS2 not found at "%MSYS2_ROOT%". Set MSYS2_ROOT to your MSYS2 folder.
  goto :fail
)
"%MSYS2_ROOT%\msys2_shell.cmd" -ucrt64 -defterm -no-start -here -c "bash build-portable.sh"
if errorlevel 1 goto :fail

echo === 3/3 Inno Setup ===
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo ERROR: Inno Setup 6 not found. Install it or set ISCC to the compiler path.
  goto :fail
)
"%ISCC%" installer.iss
if errorlevel 1 goto :fail

echo.
echo DONE: installer\AirMirror-Setup-1.0.0.exe
goto :eof

:fail
echo.
echo BUILD FAILED
exit /b 1
