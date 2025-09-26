@echo off
rem chfs-py 快速启动脚本 (中文版)
rem 双击即可启动，无需任何配置

setlocal enabledelayedexpansion
chcp 65001 > nul
title chfs-py 文件服务器

rem 检查是否在正确目录
if not exist "app\main.py" (
    echo.
    echo ❌ 错误：请将此脚本放在 chfs-py 项目根目录中
    echo.
    echo 项目结构应该是：
    echo   chfs-py\
    echo   ├── app\
    echo   ├── templates\
    echo   ├── 快速启动.cmd  ^<-- 此文件
    echo   └── ...
    echo.
    pause
    exit /b 1
)

cls
echo.
echo =================== chfs-py 轻量文件服务器 ====================
echo                     快速启动
echo ===============================================================
echo.

rem 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未安装 Python！
    echo.
    echo 📥 请先下载安装 Python 3.11+：
    echo    https://www.python.org/downloads/
    echo.
    echo 💡 安装时请勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo ✅ Python 环境检查通过
echo.

rem 快速安装依赖
echo 正在安装依赖包...
pip install fastapi uvicorn[standard] wsgidav pyyaml jinja2 aiofiles watchdog passlib[bcrypt] python-multipart asgiref typing-extensions --quiet --disable-pip-version-check
if errorlevel 1 (
    echo 依赖安装失败，尝试使用国内镜像源...
    pip install fastapi uvicorn[standard] wsgidav pyyaml jinja2 aiofiles watchdog passlib[bcrypt] python-multipart asgiref typing-extensions -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet --disable-pip-version-check
)

rem 创建基本目录
if not exist "data" mkdir data
if not exist "data\public" mkdir data\public
if not exist "data\home" mkdir data\home
if not exist "logs" mkdir logs

rem 创建简化配置文件
if not exist "chfs-simple.yaml" (
    (
        echo server:
        echo   addr: "0.0.0.0"
        echo   port: 8082
        echo.
        echo shares:
        echo   - name: "public"
        echo     path: "%CD%\data\public"
        echo   - name: "home"
        echo     path: "%CD%\data\home"
        echo.
        echo users:
        echo   - name: "admin"
        echo     pass: "123456"
        echo     pass_bcrypt: false
        echo.
        echo rules:
        echo   - who: "admin"
        echo     allow: ["R", "W", "D"]
        echo     roots: ["public", "home"]
        echo     paths: ["/"]
        echo     ip_allow: ["*"]
        echo.
        echo logging:
        echo   json: false
        echo   file: "%CD%\logs\chfs.log"
        echo   level: "INFO"
        echo.
        echo ui:
        echo   brand: "chfs-py"
        echo   title: "文件服务器"
        echo   language: "zh"
        echo.
        echo dav:
        echo   enabled: true
        echo   mountPath: "/webdav"
    ) > chfs-simple.yaml
)

rem 检测服务器 IPv4 地址，方便在其他电脑上访问
set "SERVER_ADDR="
for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /c:"IPv4 地址" /c:"IPv4 Address"') do (
    for /f "tokens=*" %%B in ("%%A") do (
        if not defined SERVER_ADDR set "SERVER_ADDR=%%B"
    )
)
if not defined SERVER_ADDR set "SERVER_ADDR=127.0.0.1"
set "SERVER_PORT=8082"
set "SERVER_ADDR=!SERVER_ADDR: =!"
set "ACCESS_URL=http://!SERVER_ADDR!:%SERVER_PORT%"

rem 在 data\public 中创建欢迎文件
if not exist "data\public\欢迎使用.txt" (
    (
        echo 🎉 欢迎使用 chfs-py 文件服务器！
        echo.
        echo 📁 这是公共文件夹，您可以：
        echo   - 上传文件
        echo   - 创建文件夹
        echo   - 下载文件
        echo   - 分享文本
        echo.
        echo 访问方式：
        echo   Web界面：!ACCESS_URL!
        echo   WebDAV： !ACCESS_URL!/webdav
        echo.
        echo 🌐 请使用服务器电脑的 IP 地址（当前检测为：!SERVER_ADDR!）在其他电脑的浏览器中访问。
        echo 👤 默认账户：admin / 123456
        echo.
        echo 📖 更多功能请查看项目文档
        echo.
        echo 创建时间：%date% %time%
    ) > "data\public\欢迎使用.txt"
)

echo 环境准备完成
echo.
echo ===============================================================
echo.
echo 启动文件服务器...
echo.
echo 访问地址（请在其他电脑上使用服务器的 IP 地址访问）：
echo    Web界面：!ACCESS_URL!
echo    WebDAV： !ACCESS_URL!/webdav

echo 登录账户：admin / 123456

echo 数据目录：%CD%\data

echo 提示：按 Ctrl+C 可停止服务器

echo ===============================================================
echo.
echo ✅ 准备完成，正在启动服务器...
echo.
echo 💡 如需在服务器这台电脑上打开 Web 界面，可运行同目录下的 "打开Web界面.cmd"
echo    其他电脑请在浏览器中访问: !ACCESS_URL!
echo.

rem 启动服务器
set "CHFS_CONFIG=%CD%\chfs-simple.yaml"
python -m app.main --config chfs-simple.yaml

echo.
echo [92m服务器已停止，感谢使用！[0m
pause
