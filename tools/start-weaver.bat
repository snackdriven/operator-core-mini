@echo off
setlocal

:: Determine the directory where this batch script lives
set "SCRIPT_DIR=%~dp0"

:: Check if python is available
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

:: Ensure 'schedule' is installed quietly
python -m pip install schedule >nul 2>&1

echo Starting Weaver Daemon in the background...
echo Logs will be written to %SCRIPT_DIR%..\logs\weaver.log

:: Start the python script using pythonw to hide the console window
start "" pythonw "%SCRIPT_DIR%weaver.py"

echo Weaver is now running.
:: Wait a moment so the user sees the success message
ping 127.0.0.1 -n 3 > nul
