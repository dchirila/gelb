# Regenerate ANTLR4 files for GeLB
# This script should be run from the root of the GeLB repository.
#
# Supported: Windows 11 (winget for Java install if missing).
# Java is required; the script will detect common install locations
# and offer to install via winget if not found.

$ErrorActionPreference = "Stop"

Write-Host "Regenerating ANTLR4 files..."

# --- Virtual environment ---
if (-not (Test-Path ".venv")) {
    Write-Error "Virtual environment not found. Please run gelb_bootstrap.ps1 first."
    exit 1
}

# Add venv Scripts to PATH so that the `antlr4` CLI (from antlr4-tools)
# is found by subprocess.run inside invoke_antlr4_tool()
$env:PATH = "$(Get-Location)\.venv\Scripts;$env:PATH"

# --- Java detection ---
$javaFound = $false

# Check if java is already on PATH
try {
    $null = Get-Command java -ErrorAction Stop
    $javaFound = $true
} catch {
    # Not on PATH -- search common Windows locations
    $searchPaths = @(
        "$env:ProgramFiles\Java",
        "$env:ProgramFiles\Eclipse Adoptium",
        "$env:ProgramFiles\Microsoft\jdk-*",
        "$env:ProgramFiles\Zulu",
        "$env:LOCALAPPDATA\Programs\Eclipse Adoptium"
    )

    foreach ($pattern in $searchPaths) {
        $candidates = Get-ChildItem -Path $pattern -Directory -ErrorAction SilentlyContinue |
                      Sort-Object Name -Descending |
                      Select-Object -First 1
        if ($candidates) {
            $jdkDir = $candidates.FullName
            $env:JAVA_HOME = $jdkDir
            $env:PATH = "$jdkDir\bin;$env:PATH"
            $javaFound = $true
            Write-Host "Found Java at $jdkDir"
            break
        }
    }

    if (-not $javaFound) {
        Write-Host ""
        Write-Host "Java not found. Attempting to install via winget..." -ForegroundColor Yellow

        try {
            $null = Get-Command winget -ErrorAction Stop
            winget install --id Microsoft.OpenJDK.21 --accept-package-agreements --accept-source-agreements
            # After install, refresh PATH
            $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                        [System.Environment]::GetEnvironmentVariable("PATH", "User")
            try {
                $null = Get-Command java -ErrorAction Stop
                $javaFound = $true
                Write-Host "Java installed successfully." -ForegroundColor Green
            } catch {
                Write-Error "Java was installed but is not yet on PATH. Please restart your terminal and try again."
                exit 1
            }
        } catch {
            Write-Host ""
            Write-Error "Java is required but not found, and winget is not available.`nInstall a JDK manually: https://adoptium.net/"
            exit 1
        }
    }
}

# Set JAVA_HOME if not already set
if (-not $env:JAVA_HOME) {
    $javaBin = (Get-Command java).Source
    # Resolve to real path and strip \bin\java.exe
    $env:JAVA_HOME = Split-Path (Split-Path $javaBin -Parent) -Parent
}

# --- Regenerate ---
& .\.venv\Scripts\python.exe -c "from gelb.utils.misc import invoke_antlr4_tool; invoke_antlr4_tool()"

if ($LASTEXITCODE -eq 0) {
    Write-Host "ANTLR4 files regenerated successfully."
} else {
    Write-Error "Failed to regenerate ANTLR4 files."
    exit 1
}
