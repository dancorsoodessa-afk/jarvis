# Build and verify the cloud-only JARVIS Windows x64 application.
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
$ErrorActionPreference = "Stop"

Write-Host "== JARVIS: install dependencies ==" -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
python -m pip install --upgrade "pyinstaller>=6.22,<7" pytest

Write-Host "== JARVIS: prepare local Three.js engine ==" -ForegroundColor Cyan
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\prepare_3d_assets.ps1
if ($LASTEXITCODE -ne 0) { throw "Three.js asset preparation failed." }

Write-Host "== JARVIS: run tests ==" -ForegroundColor Cyan
python -m pytest tests/ -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed; release build aborted." }

Write-Host "== JARVIS: desktop import check ==" -ForegroundColor Cyan
python -c "import jarvis_desktop; print('JARVIS desktop import OK')"
if ($LASTEXITCODE -ne 0) { throw "Desktop import check failed." }

Write-Host "== JARVIS: build EXE ==" -ForegroundColor Cyan
python -m PyInstaller jarvis_desktop.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "JARVIS.exe build failed." }

$release = "release"
Remove-Item $release -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item "dist\jarvis_desktop.exe" "$release\JARVIS.exe"

@"
JARVIS — Windows x64
Chat AI: Google Gemini API (internet and GEMINI_API_KEY required).
Speech recognition: Google Gemini API (GEMINI_API_KEY required).
Speech output: Google Gemini cloud TTS (GEMINI_API_KEY required).
No local AI models are bundled.

Configuration: enter GEMINI_API_KEY in the JARVIS control center.
"@ | Set-Content -Path "$release\README.txt" -Encoding UTF8

Write-Host "== JARVIS: packaged EXE startup smoke test ==" -ForegroundColor Cyan
$exePath = (Resolve-Path "$release\JARVIS.exe").Path
$process = Start-Process -FilePath $exePath -WorkingDirectory (Get-Location).Path -PassThru
try {
    Start-Sleep -Seconds 8
    $process.Refresh()
    if ($process.HasExited) {
        throw "JARVIS.exe exited during startup smoke test (exit code $($process.ExitCode))."
    }
    Write-Host "Startup smoke test passed: JARVIS.exe stayed alive for 8 seconds." -ForegroundColor Green
}
finally {
    $process.Refresh()
    if (!$process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "Release ready:" -ForegroundColor Green
Write-Host "  $release\JARVIS.exe"
Write-Host ("  Size: {0:N1} MB" -f ((Get-Item "$release\JARVIS.exe").Length / 1MB))
