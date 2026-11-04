@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Pulse Fitness - SmartQuote Contracts OS (Local Pilot)
cd /d "%~dp0"

set "PILOT_EXE=%~dp0Pulse_ContractsOS_SmartQuote_Pilot.exe"
if not exist "%PILOT_EXE%" (
  echo SmartQuote Windows executable was not found.
  echo Download and extract the COMPLETE Windows pilot build from GitHub Actions.
  pause
  exit /b 1
)

if not exist "%~dp0private_runtime\contracts.sqlite3" (
  call :FirstTimeSetup
  if errorlevel 1 (
    echo Bootstrap could not complete. Nothing has been published.
    pause
    exit /b 1
  )
)

"%PILOT_EXE%" --has-admin >nul 2>&1
if errorlevel 1 (
  echo.
  echo Create a named Administrator account for the protected pilot.
  "%PILOT_EXE%" --create-admin
  if errorlevel 1 (
    echo Account setup incomplete.
    pause
    exit /b 1
  )
)

echo.
echo SmartQuote starts on this PC only.
echo Log in at: http://127.0.0.1:18080
echo SmartQuote Admin setup still needs the V10 source ZIP, Sage list,
echo and authorised tariffs/maintenance terms before issuing customer PDFs.
echo.
echo Keep this window open while using SmartQuote. Ctrl+C stops the server.
echo.
start "" "http://127.0.0.1:18080"
"%PILOT_EXE%" --serve
echo.
echo SmartQuote pilot has stopped.
pause


:FirstTimeSetup
echo.
echo SMARTQUOTE - FIRST TIME PRIVATE SETUP
echo =====================================
echo Please enter the full path to the latest approved Pulse Fitness
echo Maintenance Master spreadsheet. All customer data remains on this PC.
echo.
echo A fresh database will be made. Existing data is NEVER overwritten.
echo.
set /p "PULSE_MASTER=Approved Master .xlsx path: "
if not defined PULSE_MASTER (
  echo No file selected. Nothing changed.
  exit /b 1
)
rem Allow a filename pasted from Explorer with surrounding double quotes.
set "PULSE_MASTER=%PULSE_MASTER:"=%"
"%PILOT_EXE%" --bootstrap-master "%PULSE_MASTER%"
exit /b %errorlevel%
