# Launch the native live JARVIS desktop application.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root 'dist\jarvis_desktop.exe'
if (-not (Test-Path $exe)) {
    throw "dist\jarvis_desktop.exe not found. Build first with scripts\build_exe.ps1"
}
Start-Process $exe
