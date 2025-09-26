# PowerShell script to install chfs-py as a Windows service using NSSM
# Requires NSSM (Non-Sucking Service Manager): https://nssm.cc/

param(
    [string]$Action = "install",
    [string]$ServiceName = "chfs-py",
    [string]$DisplayName = "chfs-py File Server",
    [string]$Description = "Lightweight file server with WebDAV support",
    [string]$Config = "chfs.yaml",
    [string]$ExePath = "",
    [string]$WorkingDirectory = "",
    [string]$LogFile = "",
    [switch]$UseExe = $false,
    [switch]$StartService = $false,
    [switch]$Help = $false
)

# Show help
if ($Help) {
    Write-Host "chfs-py Windows Service Installer" -ForegroundColor Green
    Write-Host ""
    Write-Host "Usage: .\scripts\install-service.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Actions:"
    Write-Host "  install         Install the service (default)"
    Write-Host "  uninstall       Remove the service"
    Write-Host "  start           Start the service"
    Write-Host "  stop            Stop the service"
    Write-Host "  restart         Restart the service"
    Write-Host "  status          Show service status"
    Write-Host "  edit            Edit service configuration"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -ServiceName NAME       Service name (default: chfs-py)"
    Write-Host "  -DisplayName NAME       Display name for service"
    Write-Host "  -Description TEXT       Service description"
    Write-Host "  -Config FILE           Configuration file path (default: chfs.yaml)"
    Write-Host "  -ExePath PATH          Path to executable (for packaged .exe)"
    Write-Host "  -WorkingDirectory PATH Working directory (default: current)"
    Write-Host "  -LogFile PATH          Log file path"
    Write-Host "  -UseExe                Use packaged .exe instead of Python"
    Write-Host "  -StartService          Start service after installation"
    Write-Host "  -Help                  Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  # Install service using Python"
    Write-Host "  .\scripts\install-service.ps1"
    Write-Host ""
    Write-Host "  # Install service using packaged .exe"
    Write-Host "  .\scripts\install-service.ps1 -UseExe -ExePath .\dist\chfs-py.exe"
    Write-Host ""
    Write-Host "  # Install with custom configuration"
    Write-Host "  .\scripts\install-service.ps1 -Config production.yaml -StartService"
    Write-Host ""
    Write-Host "  # Uninstall service"
    Write-Host "  .\scripts\install-service.ps1 -Action uninstall"
    Write-Host ""
    Write-Host "Requirements:"
    Write-Host "  - NSSM (Non-Sucking Service Manager): https://nssm.cc/"
    Write-Host "  - Administrator privileges"
    Write-Host ""
    exit 0
}

# Check if running as administrator
function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Write-Host "Error: This script requires administrator privileges" -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again" -ForegroundColor Yellow
    exit 1
}

# Check for NSSM
$nssmPath = $null
$nssmLocations = @(
    "nssm.exe",
    ".\nssm.exe",
    ".\tools\nssm.exe",
    "C:\tools\nssm\win64\nssm.exe",
    "${env:ProgramFiles}\nssm\win64\nssm.exe",
    "${env:ProgramFiles(x86)}\nssm\win32\nssm.exe"
)

foreach ($location in $nssmLocations) {
    if (Get-Command $location -ErrorAction SilentlyContinue) {
        $nssmPath = $location
        break
    }
    if (Test-Path $location) {
        $nssmPath = $location
        break
    }
}

if (-not $nssmPath) {
    Write-Host "Error: NSSM (Non-Sucking Service Manager) not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please download NSSM from https://nssm.cc/ and either:" -ForegroundColor Yellow
    Write-Host "1. Add it to your PATH environment variable, or" -ForegroundColor Yellow
    Write-Host "2. Place nssm.exe in the current directory, or" -ForegroundColor Yellow
    Write-Host "3. Install it to C:\tools\nssm\" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "Using NSSM: $nssmPath" -ForegroundColor Green

# Set working directory
if (-not $WorkingDirectory) {
    $WorkingDirectory = Get-Location
}

# Determine executable and arguments
if ($UseExe) {
    if (-not $ExePath) {
        # Try to find packaged executable
        $exeLocations = @(
            ".\chfs-py.exe",
            ".\dist\chfs-py.exe",
            ".\build\chfs-py.exe"
        )
        
        foreach ($location in $exeLocations) {
            if (Test-Path $location) {
                $ExePath = Resolve-Path $location
                break
            }
        }
        
        if (-not $ExePath) {
            Write-Host "Error: Packaged executable not found" -ForegroundColor Red
            Write-Host "Please specify -ExePath or ensure chfs-py.exe exists in current directory or dist/ folder" -ForegroundColor Yellow
            exit 1
        }
    }
    
    $executable = $ExePath
    $arguments = "--config `"$Config`""
} else {
    # Use Python
    try {
        $pythonPath = (Get-Command python).Source
    } catch {
        Write-Host "Error: Python not found in PATH" -ForegroundColor Red
        Write-Host "Please ensure Python is installed and accessible" -ForegroundColor Yellow
        exit 1
    }
    
    $executable = $pythonPath
    $arguments = "-m app.main --config `"$Config`""
}

# Set log file
if (-not $LogFile) {
    $LogFile = Join-Path $WorkingDirectory "logs\chfs-service.log"
}

# Ensure log directory exists
$logDir = Split-Path $LogFile -Parent
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "chfs-py Windows Service Manager" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "Action: $Action" -ForegroundColor Cyan
Write-Host "Service Name: $ServiceName" -ForegroundColor Cyan
Write-Host "Executable: $executable" -ForegroundColor Cyan
Write-Host "Arguments: $arguments" -ForegroundColor Cyan
Write-Host "Working Directory: $WorkingDirectory" -ForegroundColor Cyan
Write-Host "Log File: $LogFile" -ForegroundColor Cyan
Write-Host ""

# Execute action
switch ($Action.ToLower()) {
    "install" {
        Write-Host "Installing service..." -ForegroundColor Yellow
        
        # Check if service already exists
        $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($existingService) {
            Write-Host "Warning: Service '$ServiceName' already exists" -ForegroundColor Yellow
            $response = Read-Host "Do you want to reinstall? (y/N)"
            if ($response -ne 'y' -and $response -ne 'Y') {
                Write-Host "Installation cancelled" -ForegroundColor Yellow
                exit 0
            }
            
            # Stop and remove existing service
            Write-Host "Stopping existing service..." -ForegroundColor Yellow
            & $nssmPath stop $ServiceName
            
            Write-Host "Removing existing service..." -ForegroundColor Yellow
            & $nssmPath remove $ServiceName confirm
        }
        
        # Install service
        Write-Host "Installing new service..." -ForegroundColor Yellow
        & $nssmPath install $ServiceName $executable $arguments
        
        if ($LASTEXITCODE -eq 0) {
            # Configure service
            & $nssmPath set $ServiceName DisplayName $DisplayName
            & $nssmPath set $ServiceName Description $Description
            & $nssmPath set $ServiceName AppDirectory $WorkingDirectory
            & $nssmPath set $ServiceName AppStdout $LogFile
            & $nssmPath set $ServiceName AppStderr $LogFile
            & $nssmPath set $ServiceName AppRotateFiles 1
            & $nssmPath set $ServiceName AppRotateOnline 1
            & $nssmPath set $ServiceName AppRotateSeconds 86400  # Daily rotation
            & $nssmPath set $ServiceName AppRotateBytes 10485760  # 10MB
            
            Write-Host "Service installed successfully!" -ForegroundColor Green
            
            if ($StartService) {
                Write-Host "Starting service..." -ForegroundColor Yellow
                & $nssmPath start $ServiceName
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Service started successfully!" -ForegroundColor Green
                } else {
                    Write-Host "Failed to start service" -ForegroundColor Red
                }
            } else {
                Write-Host "Service installed but not started" -ForegroundColor Yellow
                Write-Host "To start the service, run: $nssmPath start $ServiceName" -ForegroundColor Cyan
            }
        } else {
            Write-Host "Failed to install service" -ForegroundColor Red
            exit 1
        }
    }
    
    "uninstall" {
        Write-Host "Uninstalling service..." -ForegroundColor Yellow
        
        # Check if service exists
        $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if (-not $existingService) {
            Write-Host "Service '$ServiceName' does not exist" -ForegroundColor Yellow
            exit 0
        }
        
        # Stop service if running
        if ($existingService.Status -eq 'Running') {
            Write-Host "Stopping service..." -ForegroundColor Yellow
            & $nssmPath stop $ServiceName
        }
        
        # Remove service
        & $nssmPath remove $ServiceName confirm
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Service uninstalled successfully!" -ForegroundColor Green
        } else {
            Write-Host "Failed to uninstall service" -ForegroundColor Red
            exit 1
        }
    }
    
    "start" {
        Write-Host "Starting service..." -ForegroundColor Yellow
        & $nssmPath start $ServiceName
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Service started successfully!" -ForegroundColor Green
        } else {
            Write-Host "Failed to start service" -ForegroundColor Red
            exit 1
        }
    }
    
    "stop" {
        Write-Host "Stopping service..." -ForegroundColor Yellow
        & $nssmPath stop $ServiceName
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Service stopped successfully!" -ForegroundColor Green
        } else {
            Write-Host "Failed to stop service" -ForegroundColor Red
            exit 1
        }
    }
    
    "restart" {
        Write-Host "Restarting service..." -ForegroundColor Yellow
        & $nssmPath restart $ServiceName
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Service restarted successfully!" -ForegroundColor Green
        } else {
            Write-Host "Failed to restart service" -ForegroundColor Red
            exit 1
        }
    }
    
    "status" {
        Write-Host "Service Status:" -ForegroundColor Yellow
        
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service) {
            Write-Host "Name: $($service.Name)" -ForegroundColor Cyan
            Write-Host "Display Name: $($service.DisplayName)" -ForegroundColor Cyan
            Write-Host "Status: $($service.Status)" -ForegroundColor $(if ($service.Status -eq 'Running') { 'Green' } else { 'Yellow' })
            Write-Host "Start Type: $($service.StartType)" -ForegroundColor Cyan
            
            # Show NSSM configuration
            Write-Host ""
            Write-Host "NSSM Configuration:" -ForegroundColor Yellow
            & $nssmPath get $ServiceName Application
            & $nssmPath get $ServiceName AppParameters
            & $nssmPath get $ServiceName AppDirectory
        } else {
            Write-Host "Service '$ServiceName' not found" -ForegroundColor Red
        }
    }
    
    "edit" {
        Write-Host "Opening service configuration..." -ForegroundColor Yellow
        & $nssmPath edit $ServiceName
    }
    
    default {
        Write-Host "Error: Unknown action '$Action'" -ForegroundColor Red
        Write-Host "Valid actions: install, uninstall, start, stop, restart, status, edit" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Cyan
Write-Host "  View service status: Get-Service -Name $ServiceName" -ForegroundColor Gray
Write-Host "  View service logs: Get-Content '$LogFile' -Tail 50" -ForegroundColor Gray
Write-Host "  Edit service config: $nssmPath edit $ServiceName" -ForegroundColor Gray
Write-Host "  Windows Services: services.msc" -ForegroundColor Gray
Write-Host ""
