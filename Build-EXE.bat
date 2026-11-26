@echo off
rem Builds a stand-alone program folder: dist\HLineStation\HLineStation.exe
rem Copy that whole folder to the outreach laptop - no Python needed there.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Run-HLineStation.bat once first so Python and the libraries are set up.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --name HLineStation ^
  --icon assets\hline_icon.ico ^
  --add-data "data;data" --add-data "drivers;drivers" --add-data "assets;assets" ^
  HLineStation.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
echo.
echo Done!  Your program is in:  %~dp0dist\HLineStation\HLineStation.exe
explorer "%~dp0dist\HLineStation"
pause
