# mie.ps1 - Wrapper for markdown_image_embedder.py

# --- Configuration ---
$ErrorActionPreference = 'Stop' # Exit script on most errors
$PythonScriptPath = "E:\Source\Mine\MarkdownImageEmbedder\markdown_image_embedder.py"
$LogDir = $env:TEMP # Or set a more permanent location
$Verbose = $false # Set to true for debug output - all output is suppressed by default
# --- End Configuration ---

# --- Basic Validation ---
# Check if the Python script exists
if (-not (Test-Path -Path $PythonScriptPath -PathType Leaf)) {
    Write-Error "Python script not found at: $PythonScriptPath"
    exit 1
}

# Check if any arguments were passed (PowerShell specific check)
if ($args.Count -eq 0) {
    Write-Host "ERROR: No arguments specified." -ForegroundColor Red
    Write-Host "Usage: .\mie.ps1 [options_or_input_files...]"
    Write-Host "Example: .\mie.ps1 --backup -v '*.md' 'File with spaces & ampersand.md'"
    Write-Host "Common options: -b (backup), --overwrite, -v (verbose), -d (debug), -q (quiet), -p (path)"
    exit 1
}

# --- Log File Setup ---
$RandomPart = "{0:X4}{1:X4}" -f (Get-Random -Maximum 65536), (Get-Random -Maximum 65536)
$LogFile = Join-Path -Path $LogDir -ChildPath "mie_log_$RandomPart.log"

# --- Execution ---
if ($Verbose) { Write-Host "Passing arguments to Python: $($args -join ' ')" -ForegroundColor Cyan }
if ($Verbose) { Write-Host "Log file will be: $LogFile" -ForegroundColor Cyan }

# Check if we need to add --backup automatically
$hasOutputOption = $false
foreach ($arg in $args) {
    if ($arg -eq "--backup" -or $arg -eq "-b" -or 
        $arg -eq "--overwrite" -or 
        $arg -eq "--output-file" -or $arg -eq "-o") {
        $hasOutputOption = $true
        break
    }
    # Also check for -o followed by a value
    if ($arg -eq "-o") {
        $hasOutputOption = $true
        break
    }
}

# Construct arguments for Python
# Pass through all original arguments ($args) and add --log-file
$PythonArgs = @()  # Start with empty array
$PythonArgs += $args  # Add all user arguments

# Add --backup if no output/backup option was specified
if (-not $hasOutputOption) {
    if ($Verbose) { Write-Host "No output option specified. Adding --backup automatically." -ForegroundColor Yellow }
    $PythonArgs += "--backup"
}

# Add log file option (as separate arguments, not as a quoted string)
$PythonArgs += "--log-file"
$PythonArgs += $LogFile

if ($Verbose) { Write-Host "--- Running Python Script ---" -ForegroundColor Gray }

# Execute Python script
# Use '&' call operator for executable and pass args as array
try {
    & python $PythonScriptPath $PythonArgs
    $ScriptExitCode = $LASTEXITCODE
} catch {
    Write-Error "Error executing Python script: $_"
    $ScriptExitCode = 1 # Assume error exit code
}

if ($Verbose) { Write-Host "--- Python Script Finished (Exit Code: $ScriptExitCode) ---" -ForegroundColor Gray }

# --- View Log ---
if (Test-Path -Path $LogFile -PathType Leaf) {
    if ($Verbose) { Write-Host "Launching pipe-to-code.bat for '$LogFile' in background..." -ForegroundColor Cyan }
    try {
        Start-Process -FilePath "pipe-to-code.bat" -ArgumentList "-continue", $LogFile -NoNewWindow
    } catch {
        if ($Verbose) { Write-Warning "pipe-to-code.bat failed: $_" }
    }
}

if ($Verbose) { Write-Host "PowerShell script finished." -ForegroundColor Green }
exit $ScriptExitCode 