@echo off
rem Double-click this file to remove the profiler.
rem
rem It runs uninstall.ps1 from the same folder: deletes the `profiler`
rem command, takes it off your PATH, and clears the leftovers of older
rem revisions. No Administrator rights needed.
rem
rem Your repo folder and any profiling output are left alone.
rem
rem Any arguments are passed straight through, e.g.
rem     Uninstall-Profiler.cmd -RemovePackages
rem     Uninstall-Profiler.cmd -InstallDir D:\tools\profiler

setlocal
cd /d "%~dp0"

if not exist "%~dp0uninstall.ps1" (
    echo uninstall.ps1 was not found next to this file.
    echo Keep Uninstall-Profiler.cmd in the profiler repo folder.
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" echo Uninstall exited with code %RC%. Read the messages above.
pause
exit /b %RC%
