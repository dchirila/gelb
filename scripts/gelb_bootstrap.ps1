# Bootstrap script for GeLB development environment
# Removes existing venv, creates a new one, and installs requirements

$ErrorActionPreference = "Stop"

Write-Host "Setting up GeLB development environment..."

# Get the root directory (parent of scripts directory)
$rootDir = Split-Path -Parent $PSScriptRoot

# Define venv path
$venvPath = Join-Path $rootDir "venv"

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

# Create new virtual environment
Write-Host "Creating new virtual environment..."
python -m venv $venvPath

# Activate virtual environment
Write-Host "Activating virtual environment..."
& "$venvPath\Scripts\Activate.ps1"

# Upgrade pip
Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

# Install requirements
$requirementsPath = Join-Path $rootDir "requirements.txt"
if (Test-Path $requirementsPath) {
    Write-Host "Installing requirements..."
    pip install -r $requirementsPath
} else {
    Write-Host "Warning: requirements.txt not found at $requirementsPath" -ForegroundColor Yellow
    exit 1
}

Write-Host "GeLB development environment setup complete!" -ForegroundColor Green
