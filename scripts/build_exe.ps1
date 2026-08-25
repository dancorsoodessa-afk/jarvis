# Build jarvis.exe on Windows. Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
$ErrorActionPreference = "Stop"

python -m pip install --upgrade pyinstaller
python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "Tests failed, aborting build" }

pyinstaller jarvis.spec --clean --noconfirm
Write-Host ""
Write-Host "Done: dist\jarvis.exe" -ForegroundColor Green
