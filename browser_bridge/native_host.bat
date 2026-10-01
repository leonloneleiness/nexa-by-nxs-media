@echo off
rem Trình duyệt gọi tệp này qua Native Messaging. Dùng Python trong môi trường ảo của NEXA.
"%~dp0..\.venv\Scripts\python.exe" -u "%~dp0native_host.py" %*
