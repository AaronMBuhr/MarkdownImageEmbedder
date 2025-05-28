@echo off
setlocal

rem --- Find the location of this batch script ---
set "SCRIPT_DIR=%~dp0"
rem Remove trailing backslash if present
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PS1_SCRIPT=%SCRIPT_DIR%\mie.ps1"

rem --- Check if PowerShell script exists ---
if not exist "%PS1_SCRIPT%" (
    echo ERROR: PowerShell script not found at: "%PS1_SCRIPT%"
    goto :eof
)

rem --- Check if PowerShell command is available ---
powershell.exe -Command "exit 0" >nul 2>&1
if errorlevel 1 (
    echo ERROR: powershell.exe command not found in PATH. Cannot execute mie.ps1.
    goto :eof
)

rem --- Execute PowerShell script ---
rem Allow Python script output to show while suppressing PowerShell messages
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1_SCRIPT%" %*

rem --- Capture and return exit code ---
set SCRIPT_EXIT_CODE=%ERRORLEVEL%

endlocal
exit /b %SCRIPT_EXIT_CODE%
