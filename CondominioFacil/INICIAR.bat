@echo off
if /I "%~1"=="--preparar" goto prepare
start "" wscript.exe "%~dp0INICIAR.vbs"
exit /b 0
:prepare
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run
py -3 --version >nul 2>&1
if errorlevel 1 exit /b 2
py -3 -m venv .venv
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
:run
".venv\Scripts\python.exe" -c "import win32com.client, tkinter, pypdf" >nul 2>&1
if errorlevel 1 goto repair
goto launch
:repair
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -c "import win32com.client, tkinter, pypdf" >nul 2>&1
if errorlevel 1 exit /b 1
:launch
if not exist ".venv\Scripts\pythonw.exe" exit /b 1
start "" ".venv\Scripts\pythonw.exe" "launcher.py"
exit /b 0
