@echo off
echo Installing JARVIS dependencies into venv...
call "%~dp0venv\Scripts\activate.bat"
pip install -r "%~dp0requirements.txt"
echo.
echo Done! All dependencies installed.
pause
