# Bootstrap script for GeLB development environment
# Removes existing venv, creates a new one, and installs requirements using uv.
#
# Checks system prerequisites (Python >= 3.11, git) and fails fast with
# actionable hints when anything is missing. Java is NOT required at
# bootstrap time -- it's only needed by .\scripts\regenerate_antlr.ps1
# (and only when the ANTLR4 generated_code/ files are missing or out of date).

$ErrorActionPreference = "Stop"

Write-Host "Setting up GeLB development environment with uv..."

# Get the root directory (parent of scripts directory)
$rootDir = Split-Path -Parent $PSScriptRoot

# Define venv path
$venvPath = Join-Path $rootDir ".venv"

# --- Prerequisite checks ---
#
# git is a hard requirement (the project itself is a git repo). Python
# >= 3.11 is also hard (matches `requires-python` in pyproject.toml).
# A C/Fortran toolchain is NOT checked here on Windows because the GeLB
# CPU backend on Windows typically uses MinGW/MSYS2 or WSL -- which path
# the user takes is up to them, and we don't want to second-guess it.
function Test-Prereqs {
    $missingHard = @()

    # Hard: git
    try { $null = Get-Command git -ErrorAction Stop }
    catch { $missingHard += "git" }

    # Hard: python >= 3.11
    $pythonCmd = $null
    foreach ($candidate in @("python3", "python", "py")) {
        try {
            $null = Get-Command $candidate -ErrorAction Stop
            $pythonCmd = $candidate
            break
        } catch { }
    }
    if (-not $pythonCmd) {
        $missingHard += "python (>= 3.11)"
    } else {
        try {
            $pyver = & $pythonCmd -c "import sys; print('{}.{}'.format(*sys.version_info[:2]))" 2>$null
            $parts = $pyver -split '\.'
            $pymaj = [int]$parts[0]
            $pymin = [int]$parts[1]
            if ($pymaj -lt 3 -or ($pymaj -eq 3 -and $pymin -lt 11)) {
                $missingHard += "python >= 3.11 (found $pyver)"
            }
        } catch {
            $missingHard += "python (version check failed)"
        }
    }

    if ($missingHard.Count -gt 0) {
        Write-Host ""
        $list = ($missingHard | ForEach-Object { "  - $_" }) -join "`n"
        Write-Error "The following required tools are missing:`n$list`n`nInstall them and re-run this script. On Windows you can use winget:`n  winget install --id Git.Git`n  winget install --id Python.Python.3.12"
        exit 1
    }
}

Test-Prereqs

# --- uv detection / install ---
#
# uv ships as a single static binary on Windows; the official installer
# drops it into $env:LOCALAPPDATA\Programs\uv (newer) or $env:USERPROFILE\
# .cargo\bin (older). We check both before falling back to the installer.
function Test-UvOnPath {
    try {
        $null = Get-Command uv -ErrorAction Stop
        return $true
    } catch {
        $candidates = @(
            (Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe"),
            (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe"),
            (Join-Path $env:USERPROFILE ".local\bin\uv.exe")
        )
        foreach ($candidate in $candidates) {
            if (Test-Path $candidate) {
                $env:Path = (Split-Path $candidate -Parent) + ";" + $env:Path
                return $true
            }
        }
        return $false
    }
}

if (-not (Test-UvOnPath)) {
    Write-Host "uv is not installed. Installing uv via the official installer..."
    irm https://astral.sh/uv/install.ps1 | iex
    # Refresh PATH from the registry so newly installed binaries are visible.
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (Test-UvOnPath)) {
        Write-Error "uv was installed but isn't on PATH. Restart your terminal and re-run."
        exit 1
    }
}

Write-Host "uv: $(uv --version) at $((Get-Command uv).Source)"

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
