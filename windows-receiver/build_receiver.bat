@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
py -3 -m PyInstaller --noconfirm --clean --onefile --noconsole --name ReadestRemoteReceiver --collect-all pystray --collect-all qrcode --collect-all cryptography receiver.py
if errorlevel 1 exit /b 1
echo Built: %~dp0dist\ReadestRemoteReceiver.exe
