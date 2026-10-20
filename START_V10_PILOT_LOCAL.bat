@echo off
setlocal
cd /d "%~dp0"
if not exist "pilot_settings.cmd" (
 echo Pilot has not been set up. Run SETUP_V10_PILOT.bat first.
 pause
 exit /b 1
)
call "pilot_settings.cmd"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (set "PYTHON=py") else (set "PYTHON=python")
echo Starting isolated Contracts OS pilot at http://127.0.0.1:8000
start "" "http://127.0.0.1:8000"
%PYTHON% run.py
pause
