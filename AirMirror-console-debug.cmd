@echo off
setlocal
rem ============================================================
rem  UxPlay launcher - AirMirror development console
rem  iPhone: Control Center -> Screen Mirroring -> "AirMirror"
rem  Alt+Enter = toggle fullscreen, Ctrl+C = stop
rem ============================================================
if not defined MSYS2_ROOT set "MSYS2_ROOT=C:\msys64"
set "PATH=%MSYS2_ROOT%\ucrt64\bin;%PATH%"

rem -vsync no : no timestamp buffering (lowest latency for screen mirroring)
rem -fps 60   : allow up to 60 fps instead of 30
"%MSYS2_ROOT%\ucrt64\bin\uxplay.exe" -n "AirMirror" -vs d3d12videosink -vsync no -fps 60 %*

echo.
echo UxPlay has stopped.
pause
