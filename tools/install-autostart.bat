@echo off
setlocal

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SCRIPT_PATH=%~dp0start-weaver.bat"

echo ==========================================
echo Registering Weaver to start on Windows boot
echo ==========================================
echo.

:: Use PowerShell to create a proper shortcut (.lnk) in the Startup folder
powershell -Command "$wshell = New-Object -ComObject WScript.Shell; $s = $wshell.CreateShortcut('%STARTUP_DIR%\StartWeaver.lnk'); $s.TargetPath = '%SCRIPT_PATH%'; $s.WindowStyle = 7; $s.Save()"

if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] Weaver will now start automatically in the background when you log into Windows.
    echo Shortcut created at: %STARTUP_DIR%\StartWeaver.lnk
) else (
    echo [ERROR] Failed to create shortcut.
)

echo.
pause
