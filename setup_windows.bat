@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo === NEXA — by NXS MEDIA: cài đặt ===

where py >nul 2>nul
if errorlevel 1 (
  echo [LỖI] Không tìm thấy Python launcher "py". Cài Python 3.11 64-bit từ https://www.python.org/downloads/windows/
  echo       và tích "Add python.exe to PATH" + "py launcher".
  pause & exit /b 1
)
py -3.11 -c "import sys; raise SystemExit(0 if sys.maxsize > 2**32 else 1)" >nul 2>nul
if errorlevel 1 (
  echo [LỖI] Cần Python 3.11 bản 64-bit. Kiểm tra bằng lệnh: py -0
  pause & exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Tạo môi trường ảo .venv ...
  py -3.11 -m venv .venv || (echo [LỖI] Không tạo được .venv & pause & exit /b 1)
)

echo Cài thư viện (lần đầu có thể mất 5-15 phút)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo [LỖI] Cài thư viện thất bại. Xem thông báo phía trên. & pause & exit /b 1)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Đã tạo .env từ .env.example. Mở .env và thay YOUR_NEW_GEMINI_API_KEY bằng key MỚI của anh.
)

".venv\Scripts\python.exe" scripts\generate_sounds.py
echo Tải model (MediaPipe hand landmarker + faster-whisper)...
".venv\Scripts\python.exe" scripts\download_models.py
if errorlevel 1 echo [CẢNH BÁO] Tải model chưa xong; NEXA sẽ thử tải lại khi cần.

".venv\Scripts\python.exe" scripts\diagnose.py --quick
echo.
echo Xong. Chạy start_windows.bat để mở NEXA.
echo (Tùy chọn) Cài NEXA Bridge cho YouTube: xem browser_bridge\README.md
pause
