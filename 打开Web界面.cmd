@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

set "DEFAULT_HOST=127.0.0.1"
set "DEFAULT_PORT=8082"
set "TARGET="

echo.
echo 🌐 请输入要打开的 chfs-py 服务器地址（可以是 IP、域名或完整 URL）
set /p "TARGET=服务器地址 (默认 http://%DEFAULT_HOST%:%DEFAULT_PORT%): "

if not defined TARGET (
    set "TARGET=http://%DEFAULT_HOST%:%DEFAULT_PORT%"
) else (
    echo !TARGET! | findstr /C"://" >nul
    if errorlevel 1 (
        set "TARGET=http://!TARGET!:%DEFAULT_PORT%"
    )
)

echo.
echo 正在打开 chfs-py Web 界面: !TARGET!
start "" "!TARGET!"
echo.
echo ✅ 已在默认浏览器中尝试打开 !TARGET!
echo 💡 如果在其他电脑访问，请填写服务器电脑的 IP 地址。
pause
