@echo off
REM Runs JARVIS with no console window, as a background wake-word listener,
REM plus the control UI server (which opens the browser on start).
REM Add a shortcut to this file in shell:startup to auto-launch on login.
cd /d "%~dp0"
start "" "C:\Users\Cristhian\AppData\Local\Programs\Python\Python313\pythonw.exe" "%~dp0main.py"
start "" "C:\Users\Cristhian\AppData\Local\Programs\Python\Python313\pythonw.exe" "%~dp0ui\server.py"
