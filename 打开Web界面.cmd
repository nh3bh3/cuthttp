@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

for /f "delims=" %%A in ('"prompt $E & for %%B in (1) do rem"') do set "ESC=%%A"
set "C_RESET=!ESC![0m"
set "C_TITLE=!ESC![96m"
set "C_SUCCESS=!ESC![92m"
set "C_WARN=!ESC![93m"
set "C_MUTED=!ESC![90m"

set "DEFAULT_HOST=127.0.0.1"
set "DEFAULT_PORT=8082"
set "TARGET="

call :print_logo
call :print_banner

echo.
echo !C_MUTED!🌐 请输入要打开的 chfs-py 服务器地址（支持 IP、域名或完整 URL）!C_RESET!
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
echo !C_MUTED!正在打开 chfs-py Web 界面：!C_RESET!!TARGET!
start "" "!TARGET!"

echo.
echo !C_SUCCESS!✅ 已在默认浏览器中尝试打开 !TARGET!!C_RESET!
call :print_tip "在其他电脑访问时，请填写服务器电脑的 IP 地址。"
call :print_tip "如需启动服务器，请运行同目录下的 \"快速启动.cmd\"。"

echo.
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

:print_banner
set "LINE======================================="
echo !C_TITLE!!LINE!!C_RESET!
echo !C_TITLE!   chfs-py Web 界面快速访问!C_RESET!
echo !C_TITLE!!LINE!!C_RESET!
exit /b 0

:print_tip
set "TIP_TEXT=%~1"
echo !C_WARN!💡 %TIP_TEXT%!C_RESET!
exit /b 0
