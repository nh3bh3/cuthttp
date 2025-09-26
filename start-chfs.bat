@echo off
:: chfs-py 一键启动脚本 (批处理版本)
:: 适用于不支持 PowerShell 的环境

setlocal enabledelayedexpansion
chcp 65001 > nul

:: 设置颜色代码
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "CYAN=[96m"
set "WHITE=[97m"
set "RESET=[0m"

:: 设置默认参数
set "PORT=8080"
set "HOST=0.0.0.0"

:: 显示标题
title chfs-py 一键启动
cls
echo %CYAN%============================================================%RESET%
echo %GREEN%           chfs-py 轻量文件服务器 - 一键启动%RESET%
echo %CYAN%============================================================%RESET%
echo.

:: 获取当前目录
set "PROJECT_ROOT=%CD%"
echo %CYAN%项目目录: %PROJECT_ROOT%%RESET%
echo %CYAN%监听地址: %HOST%:%PORT%%RESET%
echo.

:: 步骤 1: 检查 Python 环境
echo %YELLOW%[1/6] 检查 Python 环境...%RESET%
python --version >nul 2>&1
if errorlevel 1 (
    echo %RED%✗ 错误: 未找到 Python%RESET%
    echo.
    echo %YELLOW%请先安装 Python 3.11+ 并确保已添加到 PATH 环境变量%RESET%
    echo %CYAN%下载地址: https://www.python.org/downloads/%RESET%
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
echo %GREEN%✓ Python 已安装: %PYTHON_VERSION%%RESET%

:: 步骤 2: 检查项目结构
echo %YELLOW%[2/6] 检查项目结构...%RESET%
if not exist "app\main.py" (
    echo %RED%✗ 错误: 缺少 app\main.py%RESET%
    goto :error_exit
)
if not exist "pyproject.toml" (
    echo %RED%✗ 错误: 缺少 pyproject.toml%RESET%
    goto :error_exit
)
echo %GREEN%✓ 项目结构完整%RESET%

:: 步骤 3: 创建虚拟环境
echo %YELLOW%[3/6] 检查虚拟环境...%RESET%
if not exist "venv\" (
    echo 创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo %RED%✗ 创建虚拟环境失败%RESET%
        goto :error_exit
    )
    echo %GREEN%✓ 虚拟环境已创建%RESET%
) else (
    echo %GREEN%✓ 虚拟环境已存在%RESET%
)

:: 激活虚拟环境
if exist "venv\Scripts\activate.bat" (
    echo 激活虚拟环境...
    call venv\Scripts\activate.bat
    echo %GREEN%✓ 虚拟环境已激活%RESET%
) else (
    echo %YELLOW%⚠ 警告: 无法激活虚拟环境，使用系统 Python%RESET%
)

:: 步骤 4: 安装依赖
echo %YELLOW%[4/6] 安装依赖包...%RESET%
python -c "import fastapi, uvicorn, wsgidav" >nul 2>&1
if errorlevel 1 (
    echo 安装依赖包...
    pip install -e . --quiet
    if errorlevel 1 (
        echo %RED%✗ 依赖安装失败%RESET%
        goto :error_exit
    )
    echo %GREEN%✓ 依赖安装完成%RESET%
) else (
    echo %GREEN%✓ 依赖包已安装%RESET%
)

:: 步骤 5: 创建数据目录
echo %YELLOW%[5/6] 创建数据目录...%RESET%

if not exist "chfs-data\" mkdir "chfs-data"
if not exist "chfs-data\public\" mkdir "chfs-data\public"
if not exist "chfs-data\home\" mkdir "chfs-data\home"
if not exist "chfs-data\temp\" mkdir "chfs-data\temp"
if not exist "chfs-data\logs\" mkdir "chfs-data\logs"
if not exist "chfs-data\public\_text\" mkdir "chfs-data\public\_text"

:: 创建示例文件
if not exist "chfs-data\README.txt" (
    echo # chfs-py 数据目录 > "chfs-data\README.txt"
    echo. >> "chfs-data\README.txt"
    echo 这是 chfs-py 文件服务器的数据目录。 >> "chfs-data\README.txt"
    echo. >> "chfs-data\README.txt"
    echo 目录说明: >> "chfs-data\README.txt"
    echo - public\ - 公共文件共享 >> "chfs-data\README.txt"
    echo - home\ - 用户主目录 >> "chfs-data\README.txt"
    echo - temp\ - 临时文件 >> "chfs-data\README.txt"
    echo - logs\ - 日志文件 >> "chfs-data\README.txt"
    echo. >> "chfs-data\README.txt"
    echo 创建时间: %date% %time% >> "chfs-data\README.txt"
)

echo %GREEN%✓ 数据目录准备完成%RESET%

:: 步骤 6: 生成配置文件
echo %YELLOW%[6/6] 生成配置文件...%RESET%

if not exist "chfs.yaml" (
    :: 转换路径中的反斜杠
    set "CONFIG_PATH=%PROJECT_ROOT:\=\\%"
    
    (
        echo # chfs-py 自动生成配置文件
        echo # 生成时间: %date% %time%
        echo.
        echo server:
        echo   addr: "%HOST%"
        echo   port: %PORT%
        echo   tls:
        echo     enabled: false
        echo     certfile: ""
        echo     keyfile: ""
        echo.
        echo # 共享目录
        echo shares:
        echo   - name: "public"
        echo     path: "!CONFIG_PATH!\\chfs-data\\public"
        echo   - name: "home"
        echo     path: "!CONFIG_PATH!\\chfs-data\\home"
        echo   - name: "temp"
        echo     path: "!CONFIG_PATH!\\chfs-data\\temp"
        echo.
        echo # 用户账户
        echo users:
        echo   - name: "admin"
        echo     pass: "admin123"
        echo     pass_bcrypt: false
        echo   - name: "alice"
        echo     pass: "alice123"
        echo     pass_bcrypt: false
        echo   - name: "guest"
        echo     pass: "guest"
        echo     pass_bcrypt: false
        echo.
        echo # 访问控制规则
        echo rules:
        echo   - who: "admin"
        echo     allow: ["R", "W", "D"]
        echo     roots: ["public", "home", "temp"]
        echo     paths: ["/"]
        echo     ip_allow: ["*"]
        echo   - who: "alice"
        echo     allow: ["R", "W", "D"]
        echo     roots: ["public", "home"]
        echo     paths: ["/"]
        echo     ip_allow: ["*"]
        echo   - who: "guest"
        echo     allow: ["R"]
        echo     roots: ["public"]
        echo     paths: ["/"]
        echo     ip_allow: ["*"]
        echo.
        echo # 日志配置
        echo logging:
        echo   json: false
        echo   file: "!CONFIG_PATH!\\chfs-data\\logs\\chfs.log"
        echo   level: "INFO"
        echo.
        echo # UI 配置
        echo ui:
        echo   brand: "chfs-py"
        echo   title: "chfs-py 文件服务器"
        echo   textShareDir: "!CONFIG_PATH!\\chfs-data\\public\\_text"
        echo   maxUploadSize: 104857600
        echo   language: "zh"
        echo.
        echo # WebDAV 配置
        echo dav:
        echo   enabled: true
        echo   mountPath: "/webdav"
    ) > chfs.yaml
    
    echo %GREEN%✓ 配置文件已生成: chfs.yaml%RESET%
) else (
    echo %GREEN%✓ 配置文件已存在: chfs.yaml%RESET%
)

:: 启动服务器
echo.
echo %GREEN%============================================================%RESET%
echo %GREEN%🚀 chfs-py 服务器启动中...%RESET%
echo %GREEN%============================================================%RESET%
echo.
echo %CYAN%访问地址:%RESET%
echo %WHITE%  Web 界面: http://127.0.0.1:%PORT%%RESET%
echo %WHITE%  WebDAV:   http://127.0.0.1:%PORT%/webdav%RESET%
echo.
echo %CYAN%默认账户:%RESET%
echo %WHITE%  管理员: admin / admin123%RESET%
echo %WHITE%  用户:   alice / alice123%RESET%
echo %WHITE%  访客:   guest / guest%RESET%
echo.
echo %CYAN%数据目录: %PROJECT_ROOT%\chfs-data%RESET%
echo %CYAN%配置文件: %PROJECT_ROOT%\chfs.yaml%RESET%
echo.
echo %YELLOW%按 Ctrl+C 停止服务器%RESET%
echo.

:: 等待 3 秒后打开浏览器
start /b timeout /t 3 /nobreak >nul && start http://127.0.0.1:%PORT%

:: 启动服务器
python -m app.main --config chfs.yaml --host %HOST% --port %PORT%

echo.
echo %GREEN%感谢使用 chfs-py！%RESET%
echo.
pause
exit /b 0

:error_exit
echo.
echo %YELLOW%请确保在正确的项目目录中运行此脚本%RESET%
pause
exit /b 1
