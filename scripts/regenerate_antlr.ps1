# PowerShell script to regenerate ANTLR4 files for GeLB
# This script should be run from the root of the GeLB repository

$ErrorActionPreference = "Stop"

Write-Host "Regenerating ANTLR4 files..."

# Ensure we're in the virtual environment
if (-not (Test-Path "venv")) {
    Write-Error "Virtual environment not found. Please run gelb_bootstrap.ps1 first."
    exit 1
}

# Activate virtual environment and run Python command
& .\venv\Scripts\python.exe -c "from gelb.utils.misc import invoke_antlr4_tool; invoke_antlr4_tool()"

if ($LASTEXITCODE -eq 0) {
    Write-Host "ANTLR4 files regenerated successfully."
} else {
    Write-Error "Failed to regenerate ANTLR4 files."
    exit 1
}
