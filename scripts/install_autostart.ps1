# Install/uninstall JARVIS autostart for the current user (HKCU Run key).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1            # install
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Remove     # uninstall
#
# The agent starts hidden (window style is handled by Run key defaults) and
# listens on TCP IPC 127.0.0.1:8765 so the UI / remote clients can attach.
param(
    [switch]$Remove,
    [string]$ExePath = "$PWD\dist\jarvis.exe"
)

$RegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$Name = "JARVIS"

if ($Remove) {
    if (Get-ItemProperty -Path $RegPath -Name $Name -ErrorAction SilentlyContinue) {
        Remove-ItemProperty -Path $RegPath -Name $Name
        Write-Host "JARVIS autostart removed."
    } else {
        Write-Host "JARVIS autostart not found (nothing to remove)."
    }
    exit 0
}

if (-not (Test-Path $ExePath)) {
    Write-Error "jarvis.exe not found at: $ExePath. Build it first (scripts\build_exe.ps1)."
    exit 1
}

Set-ItemProperty -Path $RegPath -Name $Name `
    -Value "`"$ExePath`" --ipc-tcp 8765"
Write-Host "JARVIS will start at login: $ExePath --ipc-tcp 8765"
Write-Host "Remove later with: scripts\install_autostart.ps1 -Remove"
