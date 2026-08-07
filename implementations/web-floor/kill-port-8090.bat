@echo off
setlocal enabledelayedexpansion
set FOUND=0

for /f "tokens=5" %%p in ('netstat -aon ^| findstr /r /c:":8090[^0-9].*LISTENING"') do (
    set FOUND=1
    echo Killing process %%p listening on port 8090...
    taskkill /PID %%p /F
)

if "%FOUND%"=="0" (
    echo No process found listening on port 8090.
)

endlocal
