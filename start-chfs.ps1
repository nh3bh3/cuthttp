# chfs-py 一键启动脚本 (Windows)
# 自动配置环境、创建目录、启动服务器

param(
    [string]$Port = "8080",
    [string]$Host = "0.0.0.0",
    [switch]$AutoConfig = $true,
    [switch]$CreateDirs = $true,
    [switch]$InstallDeps = $true,
    [switch]$OpenBrowser = $true,
    [switch]$Help = $false
)

# 显示帮助信息
if ($Help) {
    Write-Host "chfs-py 一键启动脚本" -ForegroundColor Green
    Write-Host ""
    Write-Host "用法: .\start-chfs.ps1 [选项]"
    Write-Host ""
    Write-Host "选项:"
    Write-Host "  -Port PORT        监听端口 (默认: 8080)"
    Write-Host "  -Host HOST        监听地址 (默认: 0.0.0.0)"
    Write-Host "  -AutoConfig       自动生成配置文件 (默认: 开启)"
    Write-Host "  -CreateDirs       自动创建数据目录 (默认: 开启)"
    Write-Host "  -InstallDeps      自动安装依赖 (默认: 开启)"
    Write-Host "  -OpenBrowser      启动后打开浏览器 (默认: 开启)"
    Write-Host "  -Help             显示此帮助信息"
    Write-Host ""
    Write-Host "示例:"
    Write-Host "  .\start-chfs.ps1                    # 使用默认配置启动"
    Write-Host "  .\start-chfs.ps1 -Port 9000         # 使用端口 9000"
    Write-Host "  .\start-chfs.ps1 -Host 127.0.0.1    # 只监听本地"
    Write-Host ""
    exit 0
}

# 设置控制台标题和颜色
$Host.UI.RawUI.WindowTitle = "chfs-py 一键启动"
$ErrorActionPreference = "Stop"

# 显示欢迎信息
Clear-Host
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "chfs-py 轻量文件服务器 - 一键启动" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# 获取当前目录
$ProjectRoot = Get-Location
Write-Host "项目目录: $ProjectRoot" -ForegroundColor Cyan
Write-Host "监听地址: ${Host}:${Port}" -ForegroundColor Cyan
Write-Host ""

# 步骤 1: 检查 Python 环境
Write-Host "[1/7] 检查 Python 环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python 未找到"
    }
    Write-Host "✓ Python 已安装: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ 错误: 未找到 Python" -ForegroundColor Red
    Write-Host ""
    Write-Host "请先安装 Python 3.11+ 并确保已添加到 PATH 环境变量" -ForegroundColor Yellow
    Write-Host "下载地址: https://www.python.org/downloads/" -ForegroundColor Cyan
    Write-Host ""
    Read-Host "按 Enter 键退出"
    exit 1
}

# 步骤 2: 检查项目结构
Write-Host "[2/7] 检查项目结构..." -ForegroundColor Yellow
$requiredFiles = @("app/main.py", "app/config.py", "pyproject.toml")
$missingFiles = @()

foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        $missingFiles += $file
    }
}

if ($missingFiles.Count -gt 0) {
    Write-Host "✗ 错误: 缺少必要文件:" -ForegroundColor Red
    foreach ($file in $missingFiles) {
        Write-Host "  - $file" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "请确保在正确的项目目录中运行此脚本" -ForegroundColor Yellow
    Read-Host "按 Enter 键退出"
    exit 1
}
Write-Host "✓ 项目结构完整" -ForegroundColor Green

# 步骤 3: 创建虚拟环境（如果不存在）
Write-Host "[3/7] 检查虚拟环境..." -ForegroundColor Yellow
$venvPath = "venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "创建虚拟环境..." -ForegroundColor Yellow
    python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ 创建虚拟环境失败" -ForegroundColor Red
        Read-Host "按 Enter 键退出"
        exit 1
    }
    Write-Host "✓ 虚拟环境已创建" -ForegroundColor Green
} else {
    Write-Host "✓ 虚拟环境已存在" -ForegroundColor Green
}

# 激活虚拟环境
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    Write-Host "激活虚拟环境..." -ForegroundColor Yellow
    & $activateScript
    Write-Host "✓ 虚拟环境已激活" -ForegroundColor Green
} else {
    Write-Host "⚠ 警告: 无法激活虚拟环境，使用系统 Python" -ForegroundColor Yellow
}

# 步骤 4: 安装依赖
if ($InstallDeps) {
    Write-Host "[4/7] 安装依赖包..." -ForegroundColor Yellow
    
    # 检查是否已安装
    try {
        python -c "import fastapi, uvicorn, wsgidav" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ 依赖包已安装" -ForegroundColor Green
        } else {
            throw "依赖未安装"
        }
    } catch {
        Write-Host "安装依赖包..." -ForegroundColor Yellow
        pip install -e . --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Host "✗ 依赖安装失败" -ForegroundColor Red
            Read-Host "按 Enter 键退出"
            exit 1
        }
        Write-Host "✓ 依赖安装完成" -ForegroundColor Green
    }
} else {
    Write-Host "[4/7] 跳过依赖安装" -ForegroundColor Gray
}

# 步骤 5: 创建数据目录
if ($CreateDirs) {
    Write-Host "[5/7] 创建数据目录..." -ForegroundColor Yellow
    
    $dataDirs = @(
        "chfs-data",
        "chfs-data\public",
        "chfs-data\home", 
        "chfs-data\temp",
        "chfs-data\logs",
        "chfs-data\public\_text"
    )
    
    foreach ($dir in $dataDirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            Write-Host "  ✓ 创建目录: $dir" -ForegroundColor Green
        }
    }
    
    # 创建示例文件
    $readmeContent = @"
# chfs-py 数据目录

这是 chfs-py 文件服务器的数据目录。

## 目录说明
- public/ - 公共文件共享
- home/ - 用户主目录
- temp/ - 临时文件
- logs/ - 日志文件
- public/_text/ - 文本分享存储

## 使用说明
1. 将文件放在相应目录中
2. 通过 Web 界面或 WebDAV 访问
3. 支持上传、下载、重命名、删除等操作

创建时间: $(Get-Date)
"@
    
    $readmePath = "chfs-data\README.md"
    if (-not (Test-Path $readmePath)) {
        $readmeContent | Out-File -FilePath $readmePath -Encoding UTF8
        Write-Host "  ✓ 创建说明文件: $readmePath" -ForegroundColor Green
    }
    
    Write-Host "✓ 数据目录准备完成" -ForegroundColor Green
} else {
    Write-Host "[5/7] 跳过目录创建" -ForegroundColor Gray
}

# 步骤 6: 生成配置文件
if ($AutoConfig) {
    Write-Host "[6/7] 生成配置文件..." -ForegroundColor Yellow
    
    $configPath = "chfs.yaml"
    if (-not (Test-Path $configPath)) {
        $currentDir = (Get-Location).Path.Replace('\', '\\')
        
        $configContent = @"
# chfs-py 自动生成配置文件
# 生成时间: $(Get-Date)

server:
  addr: "$Host"
  port: $Port
  tls:
    enabled: false
    certfile: ""
    keyfile: ""

# 共享目录
shares:
  - name: "public"
    path: "$currentDir\\chfs-data\\public"
  - name: "home"
    path: "$currentDir\\chfs-data\\home"
  - name: "temp"
    path: "$currentDir\\chfs-data\\temp"

# 用户账户
users:
  - name: "admin"
    pass: "admin123"
    pass_bcrypt: false
  - name: "alice"
    pass: "alice123"
    pass_bcrypt: false
  - name: "guest"
    pass: "guest"
    pass_bcrypt: false

# 访问控制规则
rules:
  # 管理员拥有所有权限
  - who: "admin"
    allow: ["R", "W", "D"]
    roots: ["public", "home", "temp"]
    paths: ["/"]
    ip_allow: ["*"]
    ip_deny: []
  
  # Alice 对 public 和 home 有完整权限
  - who: "alice"
    allow: ["R", "W", "D"]
    roots: ["public", "home"]
    paths: ["/"]
    ip_allow: ["*"]
    ip_deny: []
  
  # 访客只能读取 public
  - who: "guest"
    allow: ["R"]
    roots: ["public"]
    paths: ["/"]
    ip_allow: ["*"]
    ip_deny: []

# 日志配置
logging:
  json: false
  file: "$currentDir\\chfs-data\\logs\\chfs.log"
  level: "INFO"
  max_size_mb: 50
  backup_count: 3

# 速率限制
rateLimit:
  rps: 100          # 每秒请求数
  burst: 200        # 突发容量
  maxConcurrent: 50 # 最大并发

# IP 过滤 (默认允许所有本地网络)
ipFilter:
  allow:
    - "127.0.0.1/32"      # 本机
    - "192.168.0.0/16"    # 私有网络 C 类
    - "10.0.0.0/8"        # 私有网络 A 类
    - "172.16.0.0/12"     # 私有网络 B 类
    - "::1/128"           # IPv6 本机
  deny: []

# UI 配置
ui:
  brand: "chfs-py"
  title: "chfs-py 文件服务器"
  textShareDir: "$currentDir\\chfs-data\\public\\_text"
  # maxUploadSize: 104857600  # 可选，取消注释以限制上传大小
  language: "zh"

# WebDAV 配置
dav:
  enabled: true
  mountPath: "/webdav"
  lockManager: true
  propertyManager: true

# 热重载配置
hotReload:
  enabled: true
  watchConfig: true
  debounceMs: 1000
"@
        
        $configContent | Out-File -FilePath $configPath -Encoding UTF8
        Write-Host "✓ 配置文件已生成: $configPath" -ForegroundColor Green
    } else {
        Write-Host "✓ 配置文件已存在: $configPath" -ForegroundColor Green
    }
} else {
    Write-Host "[6/7] 跳过配置生成" -ForegroundColor Gray
}

# 步骤 7: 启动服务器
Write-Host "[7/7] 启动服务器..." -ForegroundColor Yellow
Write-Host ""

# 显示启动信息
Write-Host "=" * 60 -ForegroundColor Green
Write-Host "🚀 chfs-py 服务器启动中..." -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Green
Write-Host ""
Write-Host "访问地址:" -ForegroundColor Cyan
Write-Host "  Web 界面: http://127.0.0.1:${Port}" -ForegroundColor White
Write-Host "  WebDAV:   http://127.0.0.1:${Port}/webdav" -ForegroundColor White
Write-Host ""
Write-Host "默认账户:" -ForegroundColor Cyan
Write-Host "  管理员: admin / admin123" -ForegroundColor White
Write-Host "  用户:   alice / alice123" -ForegroundColor White
Write-Host "  访客:   guest / guest" -ForegroundColor White
Write-Host ""
Write-Host "数据目录: $(Join-Path $ProjectRoot 'chfs-data')" -ForegroundColor Cyan
Write-Host "配置文件: $(Join-Path $ProjectRoot 'chfs.yaml')" -ForegroundColor Cyan
Write-Host ""
Write-Host "按 Ctrl+C 停止服务器" -ForegroundColor Yellow
Write-Host ""

# 等待一下让用户看到信息
Start-Sleep -Seconds 2

# 在后台启动浏览器（如果启用）
if ($OpenBrowser) {
    Start-Job -ScriptBlock {
        Start-Sleep -Seconds 3
        Start-Process "http://127.0.0.1:$using:Port"
    } | Out-Null
}

# 启动服务器
try {
    python -m app.main --config chfs.yaml --host $Host --port $Port
} catch {
    Write-Host ""
    Write-Host "服务器已停止" -ForegroundColor Yellow
} finally {
    Write-Host ""
    Write-Host "感谢使用 chfs-py！" -ForegroundColor Green
    Write-Host ""
}
