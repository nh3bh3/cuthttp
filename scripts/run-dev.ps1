# PowerShell script to run chfs-py in development mode
# Usage: .\scripts\run-dev.ps1 [-Config chfs.yaml] [-Host 0.0.0.0] [-Port 8080] [-Reload]

param(
    [string]$Config = "chfs.yaml",
    [string]$Host = $null,
    [int]$Port = 0,
    [switch]$Reload = $false,
    [switch]$Debug = $false,
    [switch]$Help = $false
)

# Show help
if ($Help) {
    Write-Host "chfs-py Development Server" -ForegroundColor Green
    Write-Host ""
    Write-Host "Usage: .\scripts\run-dev.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Config FILE    Configuration file path (default: chfs.yaml)"
    Write-Host "  -Host HOST      Host to bind to (overrides config)"
    Write-Host "  -Port PORT      Port to bind to (overrides config)"
    Write-Host "  -Reload         Enable auto-reload on code changes"
    Write-Host "  -Debug          Enable debug mode"
    Write-Host "  -Help           Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\scripts\run-dev.ps1"
    Write-Host "  .\scripts\run-dev.ps1 -Config my-config.yaml -Port 9000 -Reload"
    Write-Host "  .\scripts\run-dev.ps1 -Debug -Reload"
    Write-Host ""
    exit 0
}

# Set console title
$Host.UI.RawUI.WindowTitle = "chfs-py Development Server"

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "chfs-py Development Server" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# Check if we're in the right directory
if (-not (Test-Path "app")) {
    Write-Host "Error: app directory not found. Please run this script from the project root." -ForegroundColor Red
    Write-Host "Current directory: $(Get-Location)" -ForegroundColor Yellow
    exit 1
}

# Check if configuration file exists
if (-not (Test-Path $Config)) {
    Write-Host "Warning: Configuration file '$Config' not found." -ForegroundColor Yellow
    Write-Host "The application will use default settings." -ForegroundColor Yellow
    Write-Host ""
}

# Check for Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Python not found in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.11+ and ensure it's in your PATH" -ForegroundColor Yellow
    exit 1
}

# Check if virtual environment exists and activate it
$venvPaths = @("venv", ".venv", "env", ".env")
$venvFound = $false

foreach ($venvPath in $venvPaths) {
    $activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
    if (Test-Path $activateScript) {
        Write-Host "Activating virtual environment: $venvPath" -ForegroundColor Yellow
        try {
            & $activateScript
            $venvFound = $true
            break
        } catch {
            Write-Host "Warning: Failed to activate virtual environment: $venvPath" -ForegroundColor Yellow
        }
    }
}

if (-not $venvFound) {
    Write-Host "No virtual environment found. Using system Python." -ForegroundColor Yellow
    Write-Host "Consider creating a virtual environment:" -ForegroundColor Yellow
    Write-Host "  python -m venv venv" -ForegroundColor Cyan
    Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor Cyan
    Write-Host "  pip install -e ." -ForegroundColor Cyan
    Write-Host ""
}

# Check if dependencies are installed
try {
    python -c "import fastapi, uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Import failed"
    }
    Write-Host "Dependencies: OK" -ForegroundColor Green
} catch {
    Write-Host "Warning: Dependencies not installed or incomplete" -ForegroundColor Yellow
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    
    if (Test-Path "pyproject.toml") {
        pip install -e .
    } elseif (Test-Path "requirements.txt") {
        pip install -r requirements.txt
    } else {
        Write-Host "Error: No pyproject.toml or requirements.txt found" -ForegroundColor Red
        exit 1
    }
}

# Set environment variables
if ($Debug) {
    $env:CHFS_DEBUG = "1"
    Write-Host "Debug mode: Enabled" -ForegroundColor Yellow
}

# Build uvicorn command
$uvicornArgs = @(
    "app.main:create_app"
    "--factory"
)

# Add host and port if specified
if ($Host) {
    $uvicornArgs += "--host", $Host
    Write-Host "Host override: $Host" -ForegroundColor Yellow
}

if ($Port -gt 0) {
    $uvicornArgs += "--port", $Port.ToString()
    Write-Host "Port override: $Port" -ForegroundColor Yellow
}

# Add reload if specified
if ($Reload) {
    $uvicornArgs += "--reload"
    Write-Host "Auto-reload: Enabled" -ForegroundColor Yellow
}

# Add additional uvicorn options for development
$uvicornArgs += @(
    "--access-log"
    "--log-level", "info"
)

Write-Host ""
Write-Host "Configuration file: $Config" -ForegroundColor Cyan
Write-Host "Starting server..." -ForegroundColor Green
Write-Host ""

# Run the server
try {
    uvicorn @uvicornArgs
} catch {
    Write-Host ""
    Write-Host "Server stopped or failed to start" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Server shutdown complete" -ForegroundColor Green
