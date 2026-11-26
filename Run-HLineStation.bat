@echo off
setlocal
cd /d "%~dp0"
set "VENV=%~dp0.venv"

if exist "%VENV%\Scripts\pythonw.exe" goto run

echo ============================================================
echo  H-Line Station - first-time setup (needs internet, 2-3 min)
echo ============================================================
set "PY="
where py >nul 2>nul
if %errorlevel%==0 set "PY=py -3"
if not defined PY (
  python --version >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY goto nopython

%PY% -m venv "%VENV%"
if errorlevel 1 goto fail
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Setup complete.

:run
start "" "%VENV%\Scripts\pythonw.exe" "%~dp0HLineStation.py" %*
exit /b 0

:nopython
echo.
echo Python 3 was not found. Installing it now with winget...
winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
echo.
echo When the install finishes, CLOSE this window and double-click
echo Run-HLineStation.bat again.
pause
exit /b 1

:fail
echo.
echo Setup failed - see the messages above. Check your internet connection
echo and try again. (Delete the .venv folder to start setup from scratch.)
pause
exit /b 1
