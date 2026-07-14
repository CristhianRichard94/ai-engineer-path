# Registers JARVIS to auto-launch (headless, wake-word listening) on user login.
# Creates a shortcut in the Startup folder pointing at run_background.bat.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $root "run_background.bat"
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "JARVIS.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7  # minimized
$shortcut.Description = "JARVIS voice assistant - wake word listener"
$shortcut.Save()

Write-Host "Autostart registered: $shortcutPath -> $target"
