@echo off
rem Check if the required conda environment "mypython312" is active
if /I "%CONDA_DEFAULT_ENV%" NEQ "mypython312" (
    echo ERROR: The conda environment "mypython312" is not active.
    echo Please activate it with "conda activate mypython312" and try again.
    goto :end
)

rem Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not available in the PATH.
    echo Please ensure that Python is installed and available.
    goto :end
)

setlocal enabledelayedexpansion

rem Check if required arguments are provided
if "%~1"=="" (
    echo ERROR: Missing required arguments.
    echo Usage: %~nx0 input_file_pattern output_directory [additional_arguments]
    echo Example: %~nx0 "*.md" "output_folder" -a value
    goto :end
)

rem Get input file pattern and output directory (use ~1 to remove quotes)
set "INPUT_PATTERN=%~1"
set "OUTPUT_DIR=%~2"

rem Remove the first two arguments from the list
shift
shift

rem Create a variable to hold pass-through arguments, starting with -v
set "PASS_ARGS=-v"

rem Add any remaining arguments to PASS_ARGS
:parse_args
if "%~1"=="" goto done_args
set "PASS_ARGS=!PASS_ARGS! %~1"
shift
goto parse_args
:done_args

rem Set the path to the Python markdown_image_embedder.py script
set "MARKDOWN_PY=E:\Source\Mine\MarkdownImageEmbedder\markdown_image_embedder.py"

rem Create output directory if it doesn't exist
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%" 2>nul
if errorlevel 1 (
    echo ERROR: Failed to create output directory "%OUTPUT_DIR%"
    goto :end
)

rem Create a temporary log file
set "TEMP_LOG=%TEMP%\MarkdownImageEmbedder_%RANDOM%.log"
echo Log started at %date% %time% > "%TEMP_LOG%"

rem Check if markdown_image_embedder.py exists
if not exist "%MARKDOWN_PY%" (
    echo ERROR: markdown_image_embedder.py not found at: "%MARKDOWN_PY%" >> "%TEMP_LOG%"
    echo ERROR: markdown_image_embedder.py not found at: "%MARKDOWN_PY%"
    echo Please update the MARKDOWN_PY variable with the correct path.
    goto view_log
)

echo Processing file(s): "%INPUT_PATTERN%"
echo Output directory: "%OUTPUT_DIR%"
echo Pass-through arguments: %PASS_ARGS%

rem Check if input pattern contains wildcards
echo "%INPUT_PATTERN%" | findstr /C:"*" /C:"?" >nul
if errorlevel 1 (
    rem No wildcards, process as single file
    if not exist "%INPUT_PATTERN%" (
        echo ERROR: Input file not found: "%INPUT_PATTERN%"
        goto view_log
    )
    
    echo Processing file: "%INPUT_PATTERN%"
    
    rem Extract just the filename without path
    for %%F in ("%INPUT_PATTERN%") do set "FILENAME=%%~nxF"
    
    rem Set output path
    set "OUTPATH=%OUTPUT_DIR%\!FILENAME!"
    
    echo   Processing: "%INPUT_PATTERN%" to "!OUTPATH!"
    
    rem Run the Python script with the given parameters
    python "%MARKDOWN_PY%" !PASS_ARGS! -i "%INPUT_PATTERN%" -o "!OUTPATH!" 2>> "%TEMP_LOG%"
    
    rem Check the result of the command
    if !ERRORLEVEL! NEQ 0 (
        echo   Error processing "!FILENAME!" >> "%TEMP_LOG%"
        echo   Error processing "!FILENAME!"
    ) else (
        echo   Successfully processed "!FILENAME!"
    )
    
    echo [%date% %time%] Processed !FILENAME! >> "%TEMP_LOG%"
) else (
    rem Process files matching wildcard pattern
    set "FILE_COUNT=0"
    
    for %%F in ("%INPUT_PATTERN%") do (
        set /a "FILE_COUNT+=1"
        echo Processing %%~nxF
        
        rem Set output path
        set "OUTPATH=%OUTPUT_DIR%\%%~nxF"
        
        echo   Processing: "%%F" to "!OUTPATH!"
        
        rem Run the Python script with the given parameters
        python "%MARKDOWN_PY%" !PASS_ARGS! -i "%%F" -o "!OUTPATH!" 2>> "%TEMP_LOG%"
        
        rem Check the result of the command
        if !ERRORLEVEL! NEQ 0 (
            echo   Error processing "%%~nxF" >> "%TEMP_LOG%"
            echo   Error processing "%%~nxF"
        ) else (
            echo   Successfully processed "%%~nxF"
        )
        
        echo [%date% %time%] Processed %%~nxF >> "%TEMP_LOG%"
    )
    
    if !FILE_COUNT! EQU 0 (
        echo WARNING: No files found matching pattern: "%INPUT_PATTERN%"
    ) else (
        echo Processed !FILE_COUNT! files.
    )
)

echo All files processed.
echo Results written to "%OUTPUT_DIR%"

:view_log
rem Open the log file in Notepad
echo Opening log file...
start "" notepad "%TEMP_LOG%"

rem Wait for Notepad to close
echo Waiting for log viewer to close...
:wait_loop
tasklist | find "notepad.exe" >nul
if not errorlevel 1 (
    timeout /t 1 >nul
    goto wait_loop
)

rem Delete the temporary log file
del "%TEMP_LOG%" >nul 2>&1

:end
endlocal
