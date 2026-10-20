@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (set "PYTHON=py") else (set "PYTHON=python")
%PYTHON% -m pip install -r requirements.txt
if errorlevel 1 (echo Could not install Python requirements.&pause&exit /b 1)
%PYTHON% scripts\setup_pilot.py
pause
