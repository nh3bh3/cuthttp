@echo off
:: chfs-py 依赖安装脚本
setlocal enabledelayedexpansion
chcp 65001 > nul
title chfs-py 依赖安装

cls
echo.
echo ===============================================================
echo                    chfs-py 依赖安装程序
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

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
echo Python 版本：%PYTHON_VERSION%
echo.

:: 升级 pip
echo 升级 pip...
python -m pip install --upgrade pip --quiet

:: 安装核心依赖
echo.
echo 安装核心依赖包...
echo.

set "PACKAGES=fastapi uvicorn pyyaml jinja2 aiofiles watchdog python-multipart asgiref typing-extensions"

for %%p in (%PACKAGES%) do (
    echo 安装 %%p...
    pip install "%%p" --quiet --disable-pip-version-check
    if errorlevel 1 (
        echo   失败，尝试国内镜像源...
        pip install "%%p" -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet --disable-pip-version-check
    )
)

:: 安装 passlib
echo 安装 passlib...
pip install "passlib[bcrypt]" --quiet --disable-pip-version-check
if errorlevel 1 (
    echo   失败，尝试分别安装...
    pip install passlib --quiet --disable-pip-version-check
    pip install bcrypt --quiet --disable-pip-version-check
)

:: 安装 uvicorn 扩展
echo 安装 uvicorn 扩展...
pip install "uvicorn[standard]" --quiet --disable-pip-version-check
if errorlevel 1 (
    echo   标准扩展安装失败，使用基础版本
)

:: 尝试安装 WebDAV 支持
echo.
echo 安装 WebDAV 支持...
pip install wsgidav --quiet --disable-pip-version-check
if errorlevel 1 (
    echo   WebDAV 安装失败，将在运行时禁用 WebDAV 功能
    echo   这不影响基本的文件服务器功能
    set "WEBDAV_FAILED=1"
)

:: 验证安装
echo.
echo 验证安装...
python -c "import fastapi, uvicorn, pyyaml, jinja2, aiofiles" 2>nul
if errorlevel 1 (
    echo 错误：核心依赖安装失败
    pause
    exit /b 1
)

echo.
echo ===============================================================
echo                      安装完成！
echo ===============================================================
echo.
echo 核心功能：已安装
if defined WEBDAV_FAILED (
    echo WebDAV 功能：安装失败（可选功能）
) else (
    echo WebDAV 功能：已安装
)
echo.
echo 现在可以运行 "快速启动.cmd" 来启动服务器
echo.
pause
