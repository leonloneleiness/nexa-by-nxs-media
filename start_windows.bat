@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chưa cài đặt NEXA. Chạy setup_windows.bat trước.
  pause & exit /b 1
)
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 (
  echo NEXA đã thoát với lỗi. Xem logs\nexa.log
  pause
)
