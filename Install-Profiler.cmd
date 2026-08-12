@echo off
rem Double-click this file to set the profiler up.
rem
rem It runs install.ps1 from the same folder: installs the Python
rem dependencies, then installs the `profiler` command. No Administrator
rem rights needed, and nothing is left running in the background.
rem
rem Any arguments are passed straight through, e.g.
rem     Install-Profiler.cmd -InstallDir D:\tools\profiler

setlocal
cd /d "%~dp0"

if not exist "%~dp0install.ps1" (
    echo install.ps1 was not found next to this file.
    echo Keep Install-Profiler.cmd in the profiler repo folder.
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" echo Setup exited with code %RC%. Read the messages above.
pause
exit /b %RC%
