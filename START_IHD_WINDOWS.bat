@echo off
cd /d "%~dp0"
set "PYCMD="
where py >nul 2>&1 && set "PYCMD=py -3.11"
if not defined PYCMD (
    where python >nul 2>&1 && set "PYCMD=python"
)
if not defined PYCMD (
    echo Python 3.11 is not available. Install it or add it to PATH.
    pause
    exit /b 1
)
start "IHD Server" cmd /k "%PYCMD% server.py"
set /a attempt=0
:wait_for_server
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8787' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel%==0 goto open_browser
if %attempt% GEQ 15 goto server_timeout
set /a attempt+=1
timeout /t 1 /nobreak >nul
goto wait_for_server
:open_browser
start "" "http://127.0.0.1:8787"
exit /b 0
:server_timeout
echo Server did not respond on http://127.0.0.1:8787 after 15 seconds.
pause
exit /b 1
