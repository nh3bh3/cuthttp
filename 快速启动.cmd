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
set "PIP_COMMON_OPTS=--quiet --disable-pip-version-check"
set "REQUIRED_PACKAGES=fastapi uvicorn[standard] wsgidav pyyaml jinja2 aiofiles watchdog passlib[bcrypt] python-multipart asgiref typing-extensions"

echo 正在安装依赖包...
pip install %REQUIRED_PACKAGES% %PIP_COMMON_OPTS%
if errorlevel 1 (
    echo 依赖安装失败，尝试使用国内镜像源...
    pip install %REQUIRED_PACKAGES% %PIP_COMMON_OPTS% -i https://pypi.tuna.tsinghua.edu.cn/simple
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
        echo   Web界面：http://127.0.0.1:8082
        echo   WebDAV：http://127.0.0.1:8082/webdav
        echo.
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
echo 访问地址：
echo    Web界面：http://127.0.0.1:8082
echo    WebDAV： http://127.0.0.1:8082/webdav

echo 登录账户：admin / 123456

echo 数据目录：%CD%\data

echo ===============================================================
echo.

echo 请选择需要执行的操作：
echo   [1] 启动服务器端（当前窗口）
echo   [2] 启动用户端（仅打开浏览器）
echo   [3] 分别启动服务器端（新窗口）和用户端
echo   [Q] 退出脚本
echo.

:menu
set "choice="
set /p choice=请输入选项 [1/2/3/Q]：
if /I "%choice%"=="1" goto run_server
if /I "%choice%"=="2" goto open_client
if /I "%choice%"=="3" goto start_both
if /I "%choice%"=="Q" goto goodbye
echo.
echo 无效的选项，请重新输入。
echo.
goto menu

:run_server
echo.
echo 正在启动服务器端...
set "CHFS_CONFIG=%CD%\chfs-simple.yaml"
python -m app.main --config chfs-simple.yaml
echo.
echo [92m服务器已停止，感谢使用！[0m
pause
goto :EOF

:open_client
echo.
echo 正在打开浏览器...
start "" http://127.0.0.1:8082
echo 已启动用户端（浏览器）。
pause
goto :EOF

:start_both
echo.
echo 正在新窗口启动服务器端，并打开用户端...
start "chfs-py 服务器" cmd /k "set CHFS_CONFIG=%CD%\chfs-simple.yaml && python -m app.main --config chfs-simple.yaml"
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8082
echo 服务器端和用户端已分别启动。
pause
goto :EOF

:goodbye
echo.
echo 已退出脚本。
goto :EOF

