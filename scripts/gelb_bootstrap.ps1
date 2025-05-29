# Bootstrap script for GeLB development environment
# Removes existing venv, creates a new one, and installs requirements using uv

$ErrorActionPreference = "Stop"

Write-Host "Setting up GeLB development environment with uv..."

# Get the root directory (parent of scripts directory)
$rootDir = Split-Path -Parent $PSScriptRoot

# Define venv path
$venvPath = Join-Path $rootDir ".venv"

# Check if uv is installed
try {
    uv --version | Out-Null
}
catch {
    Write-Host "uv is not installed. Installing uv..."
    # Install uv using the official installer
    irm https://astral.sh/uv/install.ps1 | iex
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

# Remove existing venv if it exists
if (Test-Path $venvPath) {
    Write-Host "Removing existing virtual environment..."
    try {
        # First try to remove with normal force
        Remove-Item -Path $venvPath -Recurse -Force -ErrorAction Stop
    }
    catch {
        Write-Host "Warning: Unable to remove some files in the virtual environment. They may be in use." -ForegroundColor Yellow
        Write-Host "Please close any applications that might be using the virtual environment and try again." -ForegroundColor Yellow
        Write-Host "Alternatively, you can restart your computer and run this script again." -ForegroundColor Yellow
        Write-Host "Error details: $_" -ForegroundColor Red
        exit 1
    }
}

# Create new virtual environment and install dependencies
Write-Host "Creating virtual environment and installing dependencies..."
Set-Location $rootDir
uv venv
uv sync --all-extras

Write-Host "GeLB development environment setup complete!" -ForegroundColor Green
Write-Host "To activate the environment, run: .venv\Scripts\activate" -ForegroundColor Green
