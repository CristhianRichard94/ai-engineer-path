@echo off
REM Runs JARVIS with no console window, as a background wake-word listener.
REM Add a shortcut to this file in shell:startup to auto-launch on login.
cd /d "%~dp0"
start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0main.py"
