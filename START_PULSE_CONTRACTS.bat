@echo off
cd /d "%~dp0"
if exist "pilot_settings.cmd" (
    call "%~dp0START_V10_PILOT_LOCAL.bat"
    exit /b %ERRORLEVEL%
)
echo =====================================================
echo  PULSE CONTRACTS OS - VERSION 10
 echo  This old launcher is disabled for safety.
echo =====================================================
echo.
echo First run SETUP_V10_PILOT.bat to create a protected
 echo pilot database and your administrator login.
echo Then run START_V10_PILOT_LOCAL.bat.
echo.
pause
exit /b 1
