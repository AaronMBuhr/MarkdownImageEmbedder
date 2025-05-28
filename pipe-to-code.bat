@echo off
setlocal enabledelayedexpansion
set CODE="c:\program files\microsoft vs code\code.exe"
:: Check for continue mode which handles the second phase
if "%~1"=="-continue" goto continue
:: Check for keyboard mode argument
set KEYBOARD_MODE=0
if "%~1"=="-k" set KEYBOARD_MODE=1
if "%~1"=="--keyboard" set KEYBOARD_MODE=1
if "%~1"=="-h" goto :usage
if "%~1"=="--help" goto :usage
:: Create a temp file with no extension for content-sensitive highlighting
set "TEMPFILE=%TEMP%\pipe-to-code-%RANDOM%"
:: Capture input based on mode
if 1==1 (
    findstr /B /V "$THIS IS THE START OF THE LINE THAT SHOULDN'T BE THERE" > "%TEMPFILE%.raw" 2>nul
    
    :: Process the file to remove line numbers
    if exist "%TEMPFILE%.raw" (
        type "%TEMPFILE%.raw" | powershell -Command "$input | ForEach-Object { $_ -replace '^[0-9]+:', '' }" > "%TEMPFILE%"
        del "%TEMPFILE%.raw" 2>nul
    )
)
:: Check if the file was created and has content
if not exist "%TEMPFILE%" (
    echo ERROR: Failed to create temp file
    exit /b 1
)
for %%F in ("%TEMPFILE%") do set size=%%~zF
if %size% EQU 0 (
    echo ERROR: No input received
    del "%TEMPFILE%" 2>nul
    exit /b 1
)
:: Launch a separate instance of this script to handle opening the file.
:: Use the full path to this script with proper nested quoting.
echo Launching VS Code with temp file: "%TEMPFILE%" (size: %size% bytes)
start "" c:\utils\winutils\silentcmd.exe "%~f0" -continue "%TEMPFILE%"
:: Main script exits immediately, returning control to the terminal.
exit /b 0
:usage
echo.
echo pipe-to-code - Pipe text to a VS Code window
echo.
echo Usage:
echo   command ^| pipe-to-code         Pipe command output to VS Code
echo   pipe-to-code -k                Open VS Code with keyboard input
echo   pipe-to-code --keyboard        Same as -k
echo   pipe-to-code -h                Show this help
echo.
exit /b 1
:continue
if "%~2"=="" goto :usage
:: Debug: Check if the file exists and has content
if not exist "%~2" (
    echo ERROR: File not found: "%~2" >nul
    exit /b 1
)
:: Get file size to check if it's empty
for %%F in ("%~2") do set size=%%~zF
if !size! EQU 0 (
    echo ERROR: File is empty: "%~2" >nul
    exit /b 1
)
:: This is the continuation part - open the file in VS Code silently 
:: No output about opening file - just do it
%CODE% -n -w "%~2" >nul 2>nul
:: After VS Code closes, delete the temp file
del "%~2" 2>nul
exit /b 0
