# Build and verify the cloud-only JARVIS Windows x64 application.
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
$ErrorActionPreference = "Stop"

Write-Host "== JARVIS: install dependencies ==" -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
python -m pip install --upgrade "pyinstaller>=6.22,<7" pytest pillow

Write-Host "== JARVIS: prepare local Three.js engine ==" -ForegroundColor Cyan
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\prepare_3d_assets.ps1
if ($LASTEXITCODE -ne 0) { throw "Three.js asset preparation failed." }

Write-Host "== JARVIS: run tests ==" -ForegroundColor Cyan
python -m pytest tests/ -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed; release build aborted." }

Write-Host "== JARVIS: desktop import check ==" -ForegroundColor Cyan
python -c "import jarvis_desktop; print('JARVIS desktop import OK')"
if ($LASTEXITCODE -ne 0) { throw "Desktop import check failed." }

Write-Host "== JARVIS: prepare Windows application icon ==" -ForegroundColor Cyan
# Image.open('assets/jarvis-reactor-logo.png') was unreliable because the source PNG is corrupt; generate a valid fallback ICO directly.
python -c "from PIL import Image, ImageDraw; im=Image.new('RGBA',(256,256),(5,12,25,255)); d=ImageDraw.Draw(im); d.ellipse((24,24,232,232),outline=(0,220,255,255),width=8); d.ellipse((64,64,192,192),outline=(0,220,255,255),width=5); d.ellipse((112,112,144,144),fill=(0,220,255,255)); d.line((128,24,128,64),fill=(0,220,255,255),width=5); d.line((128,192,128,232),fill=(0,220,255,255),width=5); d.line((24,128,64,128),fill=(0,220,255,255),width=5); d.line((192,128,232,128),fill=(0,220,255,255),width=5); im.save('assets/jarvis-reactor-logo.ico',format='ICO',sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
if ($LASTEXITCODE -ne 0 -or !(Test-Path "assets/jarvis-reactor-logo.ico")) { throw "JARVIS application icon generation failed." }

Write-Host "== JARVIS: build EXE ==" -ForegroundColor Cyan
python -m PyInstaller jarvis_desktop.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "JARVIS.exe build failed." }

$release = "release"
Remove-Item $release -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item "dist\jarvis_desktop.exe" "$release\JARVIS.exe"

Write-Host "== JARVIS: packaged EXE startup smoke test ==" -ForegroundColor Cyan
$startupLog = Join-Path $env:APPDATA "JARVIS\startup-error.log"
Remove-Item $startupLog -Force -ErrorAction SilentlyContinue
$smoke = Start-Process -FilePath (Join-Path $release "JARVIS.exe") -ArgumentList "--smoke-test" -WorkingDirectory (Get-Location).Path -PassThru -Wait
if ($smoke.ExitCode -ne 0) { throw "JARVIS.exe startup smoke test failed with exit code $($smoke.ExitCode)." }
if (Test-Path $startupLog) { throw "JARVIS.exe wrote a startup-error.log during smoke test." }
Write-Host "Packaged EXE startup smoke test passed." -ForegroundColor Green

@"
JARVIS — Windows x64
Chat AI: Google Gemini API (internet and GEMINI_API_KEY required).
Speech recognition: Google Gemini API (GEMINI_API_KEY required).
Speech output: Google Gemini cloud TTS (GEMINI_API_KEY required).
No Groq, OpenRouter, or Hugging Face provider is configured.
No local AI models are bundled.

Configuration: enter GEMINI_API_KEY in the JARVIS control center. Speech recognition uses Gemini cloud API by default; local Whisper is available only when explicitly selected.
"@ | Set-Content -Path "$release\README.txt" -Encoding UTF8

Write-Host ""
Write-Host "Release ready:" -ForegroundColor Green
Write-Host "  $release\JARVIS.exe"
Write-Host ("  Size: {0:N1} MB" -f ((Get-Item "$release\JARVIS.exe").Length / 1MB))
