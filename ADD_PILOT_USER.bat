@echo off
setlocal
cd /d "%~dp0"
if not exist "pilot_settings.cmd" (echo Run setup first.&pause&exit /b 1)
call "pilot_settings.cmd"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (set "PYTHON=py") else (set "PYTHON=python")
echo Enter the new user's name and access level.
set /p USERNAME=Username: 
echo Roles: Admin, Coordinator, Viewer
set /p ROLE=Role: 
%PYTHON% scripts\manage_pilot_users.py add "%USERNAME%" --role "%ROLE%"
pause
