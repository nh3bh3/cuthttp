@echo off
:: chfs-py 简单启动脚本 - 修复版本
setlocal enabledelayedexpansion
chcp 65001 > nul
title chfs-py 文件服务器

:: 检查项目结构
if not exist "app\main.py" (
    echo.
    echo 错误：请将此脚本放在 chfs-py 项目根目录中
    echo.
    pause
    exit /b 1
)

cls
echo.
echo ===============================================================
echo                   chfs-py 轻量文件服务器
echo ===============================================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误：未安装 Python
    echo 请先下载安装 Python 3.11+：https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo Python 环境检查通过
echo.

:: 安装依赖（分步安装，更稳定）
echo 正在安装依赖包...
echo.

:: 先安装基础包
pip install --quiet --disable-pip-version-check fastapi
pip install --quiet --disable-pip-version-check "uvicorn[standard]"
pip install --quiet --disable-pip-version-check pyyaml
pip install --quiet --disable-pip-version-check jinja2
pip install --quiet --disable-pip-version-check aiofiles
pip install --quiet --disable-pip-version-check watchdog
pip install --quiet --disable-pip-version-check "passlib[bcrypt]"
pip install --quiet --disable-pip-version-check python-multipart
pip install --quiet --disable-pip-version-check asgiref
pip install --quiet --disable-pip-version-check typing-extensions

:: 最后安装 wsgidav（可能有依赖问题）
pip install --quiet --disable-pip-version-check wsgidav
if errorlevel 1 (
    echo 警告：WebDAV 组件安装失败，将禁用 WebDAV 功能
    set "DISABLE_WEBDAV=1"
)

echo 依赖安装完成
echo.

:: 创建目录
if not exist "data" mkdir data
if not exist "data\public" mkdir data\public
if not exist "data\home" mkdir data\home
if not exist "logs" mkdir logs

:: 创建简化配置文件
if not exist "chfs-simple.yaml" (
    set "CONFIG_PATH=%CD:\=\\%"
    (
        echo server:
        echo   addr: "0.0.0.0"
        echo   port: 8081
        echo.
        echo shares:
        echo   - name: "public"
        echo     path: "!CONFIG_PATH!\\data\\public"
        echo   - name: "home"
        echo     path: "!CONFIG_PATH!\\data\\home"
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
        echo   file: "!CONFIG_PATH!\\logs\\chfs.log"
        echo   level: "INFO"
        echo.
        echo rateLimit:
        echo   rps: 100
        echo   burst: 200
        echo   maxConcurrent: 50
        echo.
        echo ipFilter:
        echo   allow: ["*"]
        echo   deny: []
        echo.
        echo ui:
        echo   brand: "chfs-py"
        echo   title: "文件服务器"
        echo   language: "zh"
        echo   maxUploadSize: 104857600
        echo.
        if not defined DISABLE_WEBDAV (
            echo dav:
            echo   enabled: true
            echo   mountPath: "/webdav"
        ) else (
            echo dav:
            echo   enabled: false
        )
        echo.
        echo hotReload:
        echo   enabled: true
        echo   watchConfig: true
    ) > chfs-simple.yaml
)

:: 创建欢迎文件
if not exist "data\public\欢迎使用.txt" (
    (
        echo 欢迎使用 chfs-py 文件服务器！
        echo.
        echo 这是公共文件夹，您可以：
        echo   - 上传文件
        echo   - 创建文件夹
        echo   - 下载文件
        echo   - 分享文本
        echo.
        echo 访问地址：
        echo   Web界面：http://127.0.0.1:8081
        if not defined DISABLE_WEBDAV (
            echo   WebDAV：http://127.0.0.1:8081/webdav
        )
        echo.
        echo 默认账户：admin / 123456
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
echo   Web界面：http://127.0.0.1:8081
if not defined DISABLE_WEBDAV (
    echo   WebDAV： http://127.0.0.1:8081/webdav
)
echo.
echo 登录账户：admin / 123456
echo.
echo 数据目录：%CD%\data
echo.
echo 提示：按 Ctrl+C 可停止服务器
echo.
echo ===============================================================
echo.

:: 3秒后打开浏览器
echo 3秒后自动打开浏览器...
timeout /t 3 /nobreak >nul
start http://127.0.0.1:8081

:: 启动服务器
python -m app.main --config chfs-simple.yaml

echo.
echo 服务器已停止，感谢使用！
pause
