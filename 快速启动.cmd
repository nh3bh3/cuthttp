@echo off
rem chfs-py 快速启动脚本 (中文版)
rem 双击即可启动，无需任何配置

setlocal enabledelayedexpansion
chcp 65001 > nul

rem ANSI 颜色支持
for /f "delims=" %%A in ('"prompt $E & for %%B in (1) do rem"') do set "ESC=%%A"
set "C_RESET=!ESC![0m"
set "C_TITLE=!ESC![96m"
set "C_SUBTITLE=!ESC![94m"
set "C_SUCCESS=!ESC![92m"
set "C_WARN=!ESC![93m"
set "C_ERROR=!ESC![91m"
set "C_MUTED=!ESC![90m"

title chfs-py 文件服务器

call :print_logo

call :print_section_header "chfs-py 轻量文件服务器" "快速启动"

rem 检查是否在正确目录
if not exist "app\main.py" (
    echo.
    echo !C_ERROR!❌ 错误：请将此脚本放在 chfs-py 项目根目录中!C_RESET!
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

echo.
call :print_step 1 "检查 Python 环境"
python --version >nul 2>&1
if errorlevel 1 (
    echo !C_ERROR!❌ 未安装 Python！!C_RESET!
    echo.
    echo !C_WARN!📥 请先下载安装 Python 3.11+：!C_RESET!
    echo    https://www.python.org/downloads/
    echo.
    echo !C_WARN!💡 安装时请勾选 "Add Python to PATH"!C_RESET!
    echo.
    pause
    exit /b 1
)

echo !C_SUCCESS!✅ Python 环境检查通过!C_RESET!

echo.
call :print_step 2 "安装 / 更新依赖"
set "PIP_PACKAGES=fastapi uvicorn[standard] wsgidav pyyaml jinja2 aiofiles watchdog passlib[bcrypt] python-multipart asgiref typing-extensions"
echo !C_MUTED!正在安装依赖包（如已安装会自动跳过）...!C_RESET!
pip install %PIP_PACKAGES% --quiet --disable-pip-version-check
if errorlevel 1 (
    echo !C_WARN!依赖安装失败，尝试使用清华镜像源...!C_RESET!
    pip install %PIP_PACKAGES% -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet --disable-pip-version-check
)

echo.
call :print_step 3 "初始化数据目录"
if not exist "data" mkdir data
if not exist "data\public" mkdir data\public
if not exist "data\home" mkdir data\home
if not exist "logs" mkdir logs

echo.
call :print_step 4 "生成默认配置"
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
    echo !C_SUCCESS!已生成 chfs-simple.yaml 配置文件!C_RESET!
) else (
    echo !C_MUTED!检测到已有配置文件，跳过生成步骤。!C_RESET!
)

echo.
call :print_step 5 "检测访问地址"
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

echo.
call :print_step 6 "准备欢迎文件"
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
        echo 📖 更多功能请查项目文档
        echo.
        echo 创建时间：%date% %time%
    ) > "data\public\欢迎使用.txt"
    echo !C_SUCCESS!已创建 data\public\欢迎使用.txt!C_RESET!
) else (
    echo !C_MUTED!欢迎文件已存在，保持原状。!C_RESET!
)

echo.
call :print_section_header "环境准备完成" "即将启动服务器"
echo    访问地址：
call :print_kv "Web 界面" "!ACCESS_URL!"
call :print_kv "WebDAV" "!ACCESS_URL!/webdav"
call :print_kv "默认账户" "admin / 123456"
call :print_kv "数据目录" "%CD%\data"

echo.
call :print_tip "在其他电脑访问时，请使用服务器电脑的 IP 地址。"
call :print_tip "如需在本机自动打开浏览器，可运行同目录下的 \"打开Web界面.cmd\"。"
call :print_tip "按 Ctrl+C 可停止服务器。"

echo.
echo !C_SUCCESS!✅ 准备完成，正在启动服务器...!C_RESET!

echo.
rem 启动服务器
set "CHFS_CONFIG=%CD%\chfs-simple.yaml"
python -m app.main --config chfs-simple.yaml

echo.
echo !C_SUCCESS!服务器已停止，感谢使用！!C_RESET!
pause
exit /b 0

:print_logo
set "LOGO_MAIN=!C_TITLE!"
set "LOGO_SHADOW=!C_MUTED!"
echo !LOGO_SHADOW!         ██████╗██╗  ██╗███████╗███████╗     ██████╗ ██╗   ██╗!C_RESET!
echo !LOGO_SHADOW!        ██╔════╝██║  ██║██╔════╝██╔════╝    ██╔═══██╗██║   ██║!C_RESET!
echo !LOGO_SHADOW!        ██║     ███████║█████╗  █████╗      ██║   ██║██║   ██║!C_RESET!
echo !LOGO_SHADOW!        ██║     ██╔══██║██╔══╝  ██╔══╝      ██║   ██║██║   ██║!C_RESET!
echo !LOGO_SHADOW!        ╚██████╗██║  ██║███████╗███████╗    ╚██████╔╝╚██████╔╝!C_RESET!
echo !LOGO_SHADOW!         ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝     ╚═════╝  ╚═════╝ !C_RESET!
echo !LOGO_MAIN!      ██████╗██╗  ██╗███████╗███████╗     ██████╗ ██╗   ██╗!C_RESET!
echo !LOGO_MAIN!     ██╔════╝██║  ██║██╔════╝██╔════╝    ██╔═══██╗██║   ██║!C_RESET!
echo !LOGO_MAIN!     ██║     ███████║█████╗  █████╗      ██║   ██║██║   ██║!C_RESET!
echo !LOGO_MAIN!     ██║     ██╔══██║██╔══╝  ██╔══╝      ██║   ██║██║   ██║!C_RESET!
echo !LOGO_MAIN!     ╚██████╗██║  ██║███████╗███████╗    ╚██████╔╝╚██████╔╝!C_RESET!
echo !LOGO_MAIN!      ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝     ╚═════╝  ╚═════╝ !C_RESET!
echo.
exit /b 0

:print_section_header
set "SECTION_TITLE=%~1"
set "SECTION_SUB=%~2"
set "LINE=============================================="
echo.
echo !C_TITLE!!LINE!!C_RESET!
echo !C_SUBTITLE!  %SECTION_TITLE%!C_RESET!
if defined SECTION_SUB echo !C_MUTED!  %SECTION_SUB%!C_RESET!
echo !C_TITLE!!LINE!!C_RESET!
exit /b 0

:print_step
set "STEP_NO=%~1"
set "STEP_TITLE=%~2"
echo !C_SUBTITLE!➤ 步骤 %STEP_NO%：!STEP_TITLE!!C_RESET!
exit /b 0

:print_tip
set "TIP_TEXT=%~1"
echo !C_WARN!💡 %TIP_TEXT%!C_RESET!
exit /b 0

:print_kv
set "KV_KEY=%~1"
set "KV_VALUE=%~2"
echo      !C_MUTED!%KV_KEY%：!C_RESET!!KV_VALUE!
exit /b 0
