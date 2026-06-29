@echo off
cd /d "%~dp0"
echo.
echo 🏺 墨禾陶瓷批发 - v2.1
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ⚠️ 首次运行，正在安装依赖...
    uv venv
    uv pip install fastapi uvicorn
    echo ✅ 依赖安装完成
)

:: 设置管理密码（上线前请修改）
set ADMIN_PASSWORD=guming2024

echo 🚀 启动服务器 http://localhost:8000
echo 🔐 管理密码: %ADMIN_PASSWORD%
echo.
.venv\Scripts\python backend/main.py
pause
