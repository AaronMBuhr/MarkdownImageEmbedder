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

rem Set default quality value if not provided (range 1-9, default is 5)
set "QUALITY=%1"
if "%QUALITY%"=="" set "QUALITY=5"

rem Validate quality is between 1 and 9
if %QUALITY% LSS 1 (
    echo WARNING: Quality value %QUALITY% is too low. Setting to minimum value of 1.
    set "QUALITY=1"
)
if %QUALITY% GTR 9 (
    echo WARNING: Quality value %QUALITY% is too high. Setting to maximum value of 9.
    set "QUALITY=9"
)

rem Set directories and log file
set "SOURCE_DIR=d:\temp\ind"
set "OUTPUT_DIR=F:\temp\markdown"
set "LOG_FILE=%OUTPUT_DIR%\MarkdownImageEmbedder.log"
rem Set the path to the Python markdown_image_embedder.py script
set "MARKDOWN_PY=E:\Source\Mine\MarkdownImageEmbedder\markdown_image_embedder.py"

rem Create output directory if it doesn't exist
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%" 2>nul
if errorlevel 1 (
    echo ERROR: Failed to create output directory "%OUTPUT_DIR%"
    goto :end
)

rem Clear log file if it exists
if exist "%LOG_FILE%" del "%LOG_FILE%"
echo Log started at %date% %time% > "%LOG_FILE%"

rem Check if markdown_image_embedder.py exists
if not exist "%MARKDOWN_PY%" (
    echo ERROR: markdown_image_embedder.py not found at: "%MARKDOWN_PY%" >> "%LOG_FILE%"
    echo ERROR: markdown_image_embedder.py not found at: "%MARKDOWN_PY%"
    echo Please update the MARKDOWN_PY variable with the correct path.
    goto :end
)

echo Processing markdown files recursively from %SOURCE_DIR%...
rem Process all markdown files recursively
for /R "%SOURCE_DIR%" %%F in (*.md) do (
    echo Processing %%~nxF

    rem Get the file directory (remove trailing backslash)
    set "FDIR=%%~dpF"
    set "FDIR=!FDIR:~0,-1!"

    rem Get the subdirectory path relative to SOURCE_DIR
    set "FILEPATH=%%~dpF"
    set "FILEPATH=!FILEPATH:%SOURCE_DIR%\=!"

    rem Set output path
    set "OUTPUT_SUBDIR=%OUTPUT_DIR%\!FILEPATH!"
    if not exist "!OUTPUT_SUBDIR!" mkdir "!OUTPUT_SUBDIR!" 2>nul
    set "OUTPATH=!OUTPUT_SUBDIR!\%%~nxF"

    echo   Processing: "%%F" to "!OUTPATH!"
    
    rem Run the Python script with the given parameters.
    rem Using -m 12 to set max file size (in MB) similar to the original; adjust as needed.
    python "%MARKDOWN_PY%" -v -q %QUALITY% -y -m 12 -p "!FDIR!" -i "%%F" -o "!OUTPATH!" 2>> "%LOG_FILE%"

    rem Check the result of the command
    if !ERRORLEVEL! NEQ 0 (
        echo   Error processing "%%~nxF" >> "%LOG_FILE%"
        echo   Error processing "%%~nxF"
    ) else (
        echo   Successfully processed "%%~nxF"
    )

    rem Clean up any temporary file if created by the Python script
    del "%TEMP%\temp_markdown.md" >nul 2>&1
    echo [%date% %time%] Processed %%~nxF >> "%LOG_FILE%"
)

echo All files processed.
echo Results written to %OUTPUT_DIR%
echo Log file available at %LOG_FILE%
:end
endlocal
