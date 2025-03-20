# Script to run the RST to HTML renderer

# Get the directory of this script
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Check if the virtual environment exists
$VenvPath = Join-Path -Path $ProjectRoot -ChildPath "venv"
$VenvActivate = Join-Path -Path $VenvPath -ChildPath "Scripts\Activate.ps1"

if (-not (Test-Path $VenvActivate)) {
    Write-Host "Virtual environment not found. Please run gelb_bootstrap.ps1 first." -ForegroundColor Red
    exit 1
}

# Activate the virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& $VenvActivate

# Run the RST to HTML renderer script
$RenderScript = Join-Path -Path $ScriptDir -ChildPath "render_rst_to_html.py"
Write-Host "Starting RST to HTML renderer..." -ForegroundColor Green
python $RenderScript
