# chfs-py 一键部署脚本 - 完整版
# 包含环境检查、依赖安装、配置生成、服务安装等全套功能

param(
    [string]$InstallPath = "C:\chfs-py",
    [string]$DataPath = "C:\chfs-data", 
    [string]$ServiceName = "chfs-py",
    [int]$Port = 8080,
    [string]$AdminUser = "admin",
    [string]$AdminPass = "admin123",
    [switch]$InstallService = $false,
    [switch]$StartService = $false,
    [switch]$OpenFirewall = $false,
    [switch]$CreateDesktopShortcut = $false,
    [switch]$Force = $false,
    [switch]$Help = $false
)

# 显示帮助
if ($Help) {
    Write-Host @"
chfs-py 一键部署脚本

用法: .\一键部署.ps1 [选项]

选项:
  -InstallPath PATH     安装路径 (默认: C:\chfs-py)
  -DataPath PATH        数据路径 (默认: C:\chfs-data)
  -ServiceName NAME     服务名称 (默认: chfs-py)
  -Port PORT            监听端口 (默认: 8080)
  -AdminUser USER       管理员用户名 (默认: admin)
  -AdminPass PASS       管理员密码 (默认: admin123)
  -InstallService       安装为 Windows 服务
  -StartService         安装后立即启动服务
  -OpenFirewall         打开 Windows 防火墙端口
  -CreateDesktopShortcut 创建桌面快捷方式
  -Force                强制覆盖现有安装
  -Help                 显示此帮助信息

示例:
  .\一键部署.ps1
  .\一键部署.ps1 -InstallService -StartService -OpenFirewall
  .\一键部署.ps1 -Port 9000 -AdminUser myuser -AdminPass mypass
"@
    exit 0
}

# 检查管理员权限
function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# 需要管理员权限的操作
$needAdmin = $InstallService -or $StartService -or $OpenFirewall

if ($needAdmin -and -not (Test-Administrator)) {
    Write-Host "❌ 此操作需要管理员权限" -ForegroundColor Red
    Write-Host "请以管理员身份运行 PowerShell 后重试" -ForegroundColor Yellow
    exit 1
}

# 设置控制台
$Host.UI.RawUI.WindowTitle = "chfs-py 一键部署"
Clear-Host

# 显示横幅
Write-Host @"
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║    ██████╗██╗  ██╗███████╗███████╗      ██████╗ ██╗   ██╗   ║
║   ██╔════╝██║  ██║██╔════╝██╔════╝      ██╔══██╗╚██╗ ██╔╝   ║
║   ██║     ███████║█████╗  ███████╗█████╗██████╔╝ ╚████╔╝    ║
║   ██║     ██╔══██║██╔══╝  ╚════██║╚════╝██╔═══╝   ╚██╔╝     ║
║   ╚██████╗██║  ██║██║     ███████║      ██║        ██║      ║
║    ╚═════╝╚═╝  ╚═╝╚═╝     ╚══════╝      ╚═╝        ╚═╝      ║
║                                                              ║
║              🚀 轻量文件服务器 - 一键部署 🚀                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"@ -ForegroundColor Cyan

Write-Host ""
Write-Host "部署配置:" -ForegroundColor Green
Write-Host "  安装路径: $InstallPath" -ForegroundColor White
Write-Host "  数据路径: $DataPath" -ForegroundColor White
Write-Host "  监听端口: $Port" -ForegroundColor White
Write-Host "  管理员账户: $AdminUser / $AdminPass" -ForegroundColor White
Write-Host "  安装服务: $(if($InstallService){'是'}else{'否'})" -ForegroundColor White
Write-Host ""

# 确认开始部署
if (-not $Force) {
    $confirm = Read-Host "是否开始部署? (y/N)"
    if ($confirm -ne 'y' -and $confirm -ne 'Y') {
        Write-Host "部署已取消" -ForegroundColor Yellow
        exit 0
    }
}

Write-Host "开始部署..." -ForegroundColor Green
Write-Host ""

# 步骤 1: 检查 Python 环境
Write-Host "[1/10] 检查 Python 环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python 未安装"
    }
    Write-Host "✅ Python 已安装: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ 未找到 Python" -ForegroundColor Red
    Write-Host ""
    Write-Host "正在下载 Python 安装程序..." -ForegroundColor Yellow
    
    $pythonUrl = "https://www.python.org/ftp/python/3.11.7/python-3.11.7-amd64.exe"
    $pythonInstaller = "$env:TEMP\python-installer.exe"
    
    try {
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonInstaller
        Write-Host "开始安装 Python..." -ForegroundColor Yellow
        Start-Process -FilePath $pythonInstaller -ArgumentList "/quiet", "InstallAllUsers=1", "PrependPath=1" -Wait
        Remove-Item $pythonInstaller -Force
        
        # 刷新环境变量
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        
        Write-Host "✅ Python 安装完成" -ForegroundColor Green
    } catch {
        Write-Host "❌ Python 自动安装失败，请手动安装" -ForegroundColor Red
        Write-Host "下载地址: https://www.python.org/downloads/" -ForegroundColor Cyan
        exit 1
    }
}

# 步骤 2: 创建安装目录
Write-Host "[2/10] 创建安装目录..." -ForegroundColor Yellow
try {
    if (Test-Path $InstallPath) {
        if ($Force) {
            Remove-Item $InstallPath -Recurse -Force
        } else {
            Write-Host "⚠️ 安装目录已存在: $InstallPath" -ForegroundColor Yellow
        }
    }
    
    New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
    Write-Host "✅ 安装目录创建完成: $InstallPath" -ForegroundColor Green
} catch {
    Write-Host "❌ 创建安装目录失败: $_" -ForegroundColor Red
    exit 1
}

# 步骤 3: 复制项目文件
Write-Host "[3/10] 复制项目文件..." -ForegroundColor Yellow
try {
    $sourceFiles = @("app", "templates", "static", "pyproject.toml", "README.md", "LICENSE")
    
    foreach ($item in $sourceFiles) {
        if (Test-Path $item) {
            Copy-Item -Path $item -Destination $InstallPath -Recurse -Force
            Write-Host "  ✅ 复制: $item" -ForegroundColor Green
        }
    }
    
    Write-Host "✅ 项目文件复制完成" -ForegroundColor Green
} catch {
    Write-Host "❌ 复制项目文件失败: $_" -ForegroundColor Red
    exit 1
}

# 步骤 4: 创建数据目录
Write-Host "[4/10] 创建数据目录..." -ForegroundColor Yellow
try {
    $dataDirs = @(
        $DataPath,
        "$DataPath\public",
        "$DataPath\home",
        "$DataPath\temp", 
        "$DataPath\logs",
        "$DataPath\public\_text"
    )
    
    foreach ($dir in $dataDirs) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  ✅ 创建: $dir" -ForegroundColor Green
    }
    
    # 创建欢迎文件
    $welcomeFile = "$DataPath\public\欢迎使用.txt"
    @"
🎉 欢迎使用 chfs-py 文件服务器！

📁 这是您的文件服务器，您可以：
  • 通过 Web 界面管理文件
  • 使用 WebDAV 挂载为网络驱动器
  • 分享文本内容
  • 设置用户权限

🌐 访问地址：
  • Web界面：http://127.0.0.1:$Port
  • WebDAV：http://127.0.0.1:$Port/webdav

👤 管理员账户：$AdminUser / $AdminPass

📖 更多信息请查看安装目录中的 README.md

部署时间：$(Get-Date)
"@ | Out-File -FilePath $welcomeFile -Encoding UTF8
    
    Write-Host "✅ 数据目录创建完成" -ForegroundColor Green
} catch {
    Write-Host "❌ 创建数据目录失败: $_" -ForegroundColor Red
    exit 1
}

# 步骤 5: 创建虚拟环境
Write-Host "[5/10] 创建虚拟环境..." -ForegroundColor Yellow
try {
    Set-Location $InstallPath
    python -m venv venv
    
    # 激活虚拟环境并安装依赖
    & "venv\Scripts\Activate.ps1"
    pip install --upgrade pip --quiet
    pip install -e . --quiet
    
    Write-Host "✅ 虚拟环境创建完成" -ForegroundColor Green
} catch {
    Write-Host "❌ 创建虚拟环境失败: $_" -ForegroundColor Red
    exit 1
}

# 步骤 6: 生成配置文件
Write-Host "[6/10] 生成配置文件..." -ForegroundColor Yellow
try {
    $configContent = @"
# chfs-py 部署配置文件
# 生成时间: $(Get-Date)

server:
  addr: "0.0.0.0"
  port: $Port
  tls:
    enabled: false
    certfile: ""
    keyfile: ""

shares:
  - name: "public"
    path: "$($DataPath.Replace('\', '\\'))\public"
  - name: "home" 
    path: "$($DataPath.Replace('\', '\\'))\home"
  - name: "temp"
    path: "$($DataPath.Replace('\', '\\'))\temp"

users:
  - name: "$AdminUser"
    pass: "$AdminPass"
    pass_bcrypt: false
  - name: "guest"
    pass: "guest"
    pass_bcrypt: false

rules:
  - who: "$AdminUser"
    allow: ["R", "W", "D"]
    roots: ["public", "home", "temp"]
    paths: ["/"]
    ip_allow: ["*"]
  - who: "guest"
    allow: ["R"]
    roots: ["public"]
    paths: ["/"]
    ip_allow: ["*"]

logging:
  json: false
  file: "$($DataPath.Replace('\', '\\'))\logs\chfs.log"
  level: "INFO"
  max_size_mb: 100
  backup_count: 5

rateLimit:
  rps: 100
  burst: 200
  maxConcurrent: 50

ipFilter:
  allow:
    - "127.0.0.1/32"
    - "192.168.0.0/16"
    - "10.0.0.0/8"
    - "172.16.0.0/12"
    - "::1/128"
  deny: []

ui:
  brand: "chfs-py"
  title: "文件服务器"
  # maxUploadSize: 104857600  # Optional upload cap (bytes); omit for unlimited
  language: "zh"

dav:
  enabled: true
  mountPath: "/webdav"
  lockManager: true
  propertyManager: true

hotReload:
  enabled: true
  watchConfig: true
  debounceMs: 1000
"@
    
    $configPath = "$InstallPath\chfs.yaml"
    $configContent | Out-File -FilePath $configPath -Encoding UTF8
    Write-Host "✅ 配置文件生成完成: $configPath" -ForegroundColor Green
} catch {
    Write-Host "❌ 生成配置文件失败: $_" -ForegroundColor Red
    exit 1
}

# 步骤 7: 创建启动脚本
Write-Host "[7/10] 创建启动脚本..." -ForegroundColor Yellow
try {
    $startScript = @"
@echo off
title chfs-py 文件服务器
cd /d "$InstallPath"
call venv\Scripts\activate.bat
python -m app.main --config chfs.yaml
pause
"@
    
    $startScript | Out-File -FilePath "$InstallPath\启动服务器.bat" -Encoding UTF8
    
    # 创建 PowerShell 启动脚本
    $psScript = @"
Set-Location "$InstallPath"
& "venv\Scripts\Activate.ps1"
python -m app.main --config chfs.yaml
"@
    
    $psScript | Out-File -FilePath "$InstallPath\启动服务器.ps1" -Encoding UTF8
    
    Write-Host "✅ 启动脚本创建完成" -ForegroundColor Green
} catch {
    Write-Host "❌ 创建启动脚本失败: $_" -ForegroundColor Red
    exit 1
}

# 步骤 8: 安装 Windows 服务（可选）
if ($InstallService) {
    Write-Host "[8/10] 安装 Windows 服务..." -ForegroundColor Yellow
    try {
        # 检查 NSSM
        $nssmPath = $null
        $nssmLocations = @("nssm.exe", "C:\tools\nssm\win64\nssm.exe")
        
        foreach ($location in $nssmLocations) {
            if (Get-Command $location -ErrorAction SilentlyContinue) {
                $nssmPath = $location
                break
            }
        }
        
        if (-not $nssmPath) {
            Write-Host "下载 NSSM..." -ForegroundColor Yellow
            $nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
            $nssmZip = "$env:TEMP\nssm.zip"
            $nssmDir = "$env:TEMP\nssm"
            
            Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip
            Expand-Archive -Path $nssmZip -DestinationPath $nssmDir -Force
            
            $nssmPath = "$nssmDir\nssm-2.24\win64\nssm.exe"
            Copy-Item $nssmPath "$InstallPath\nssm.exe"
            $nssmPath = "$InstallPath\nssm.exe"
            
            Remove-Item $nssmZip -Force
            Remove-Item $nssmDir -Recurse -Force
        }
        
        # 安装服务
        $pythonPath = "$InstallPath\venv\Scripts\python.exe"
        $arguments = "-m app.main --config chfs.yaml"
        
        & $nssmPath install $ServiceName $pythonPath $arguments
        & $nssmPath set $ServiceName AppDirectory $InstallPath
        & $nssmPath set $ServiceName DisplayName "chfs-py 文件服务器"
        & $nssmPath set $ServiceName Description "轻量级文件服务器，支持 Web 界面和 WebDAV"
        & $nssmPath set $ServiceName Start SERVICE_AUTO_START
        
        Write-Host "✅ Windows 服务安装完成" -ForegroundColor Green
        
        if ($StartService) {
            & $nssmPath start $ServiceName
            Write-Host "✅ 服务已启动" -ForegroundColor Green
        }
        
    } catch {
        Write-Host "⚠️ 服务安装失败: $_" -ForegroundColor Yellow
        Write-Host "可以稍后手动安装服务" -ForegroundColor Yellow
    }
} else {
    Write-Host "[8/10] 跳过服务安装" -ForegroundColor Gray
}

# 步骤 9: 配置防火墙（可选）
if ($OpenFirewall) {
    Write-Host "[9/10] 配置防火墙..." -ForegroundColor Yellow
    try {
        New-NetFirewallRule -DisplayName "chfs-py File Server" -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow
        Write-Host "✅ 防火墙规则已添加" -ForegroundColor Green
    } catch {
        Write-Host "⚠️ 防火墙配置失败: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "[9/10] 跳过防火墙配置" -ForegroundColor Gray
}

# 步骤 10: 创建快捷方式（可选）
if ($CreateDesktopShortcut) {
    Write-Host "[10/10] 创建桌面快捷方式..." -ForegroundColor Yellow
    try {
        $WshShell = New-Object -comObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\chfs-py 文件服务器.lnk")
        $Shortcut.TargetPath = "$InstallPath\启动服务器.bat"
        $Shortcut.WorkingDirectory = $InstallPath
        $Shortcut.Description = "chfs-py 轻量文件服务器"
        $Shortcut.Save()
        
        Write-Host "✅ 桌面快捷方式已创建" -ForegroundColor Green
    } catch {
        Write-Host "⚠️ 创建快捷方式失败: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "[10/10] 跳过快捷方式创建" -ForegroundColor Gray
}

# 部署完成
Write-Host ""
Write-Host "🎉 部署完成！" -ForegroundColor Green
Write-Host ""
Write-Host "📍 安装信息:" -ForegroundColor Cyan
Write-Host "  程序目录: $InstallPath" -ForegroundColor White
Write-Host "  数据目录: $DataPath" -ForegroundColor White
Write-Host "  配置文件: $InstallPath\chfs.yaml" -ForegroundColor White
Write-Host ""
Write-Host "🌐 访问地址:" -ForegroundColor Cyan
Write-Host "  Web界面: http://127.0.0.1:$Port" -ForegroundColor White
Write-Host "  WebDAV:  http://127.0.0.1:$Port/webdav" -ForegroundColor White
Write-Host ""
Write-Host "👤 管理员账户: $AdminUser / $AdminPass" -ForegroundColor Cyan
Write-Host ""
Write-Host "🚀 启动方式:" -ForegroundColor Cyan
if ($InstallService -and $StartService) {
    Write-Host "  服务已自动启动，可通过服务管理器控制" -ForegroundColor White
} else {
    Write-Host "  双击: $InstallPath\启动服务器.bat" -ForegroundColor White
    Write-Host "  或运行: $InstallPath\启动服务器.ps1" -ForegroundColor White
}
Write-Host ""

# 询问是否立即启动
if (-not $InstallService -or -not $StartService) {
    $startNow = Read-Host "是否立即启动服务器? (y/N)"
    if ($startNow -eq 'y' -or $startNow -eq 'Y') {
        Write-Host ""
        Write-Host "正在启动服务器..." -ForegroundColor Yellow
        Start-Sleep 2
        Start-Process "http://127.0.0.1:$Port"
        Set-Location $InstallPath
        & "venv\Scripts\Activate.ps1"
        python -m app.main --config chfs.yaml
    }
}

Write-Host "感谢使用 chfs-py！" -ForegroundColor Green
