@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0ReadestRemoteReceiver.exe" (
    echo Installing Readest Remote receiver startup...
    "%~dp0ReadestRemoteReceiver.exe" --install-startup
    if errorlevel 1 goto failed
    tasklist /fi "imagename eq ReadestRemoteReceiver.exe" | find /i "ReadestRemoteReceiver.exe" >nul
    if errorlevel 1 start "" "%~dp0ReadestRemoteReceiver.exe" --tray
    echo.
    echo Setup complete. Readest Remote shortcuts are on the Desktop and Start menu.
    echo Use either shortcut to reopen the receiver after choosing Exit in the tray.
    echo Scan the pairing QR from the Readest Remote tray icon.
    pause
    exit /b 0
)
where py >nul 2>nul
if errorlevel 1 (
    echo Packaged receiver is missing and Python launcher was not found.
    echo Download the Windows receiver ZIP from the GitHub release, or install Python 3.
    pause
    exit /b 1
)
echo Installing receiver dependencies for source setup...
py -3 -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Installing startup and launching receiver...
py -3 receiver.py --install-startup
if errorlevel 1 goto failed
for /f "delims=" %%P in ('py -3 -c "import os,sys; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"') do set "PYTHONW=%%P"
if not exist "%PYTHONW%" goto failed
start "" "%PYTHONW%" "%~dp0receiver.py" --tray
echo Setup complete. Readest Remote shortcuts are on the Desktop and Start menu.
echo Use either shortcut to reopen the receiver after choosing Exit in the tray.
echo Scan the pairing QR from the tray icon.
pause
exit /b 0
:failed
echo Setup failed. Check the error above and try again.
pause
exit /b 1
