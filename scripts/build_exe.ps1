# Build the JARVIS core and desktop EXEs on Windows.
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install -e ".[all]"
python -m pip install --upgrade pyinstaller pytest

Write-Host "== JARVIS: tests ==" -ForegroundColor Cyan
pytest tests/ -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed; release build aborted." }

Write-Host "== JARVIS: core ==" -ForegroundColor Cyan
pyinstaller jarvis.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "JARVIS.exe build failed." }

Write-Host "== JARVIS: desktop ==" -ForegroundColor Cyan
pyinstaller jarvis_desktop.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "JARVIS Desktop.exe build failed." }

$release = "release"
Remove-Item $release -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item "dist\jarvis.exe" "$release\JARVIS.exe"
Copy-Item "dist\jarvis_desktop.exe" "$release\JARVIS Desktop.exe"

@"
JARVIS — Windows x64

Основное приложение: JARVIS Desktop.exe
Ядро: JARVIS.exe

JARVIS Desktop.exe — основной графический интерфейс.
JARVIS.exe — отдельное ядро/CLI и не требуется запускать вручную для обычной работы Desktop.

Конфигурация сохраняется в %APPDATA%\JARVIS\settings.json.
"@ | Set-Content -Path "$release\README.txt" -Encoding UTF8

$package = "JARVIS-Windows-x64.zip"
Remove-Item $package -Force -ErrorAction SilentlyContinue
Compress-Archive -Path "$release\JARVIS.exe", "$release\JARVIS Desktop.exe", "$release\README.txt" -DestinationPath $package -Force

Write-Host ""
Write-Host "Release ready:" -ForegroundColor Green
Write-Host "  $release\JARVIS.exe"
Write-Host "  $release\JARVIS Desktop.exe"
Write-Host "  $package"
