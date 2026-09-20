# Build JARVIS Windows x64 with local Russian STT (Vosk) and Piper TTS.
$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install -e ".[all]"
python -m pip install --upgrade pyinstaller pytest

Write-Host "== JARVIS: prepare bundled Russian STT (Vosk small) ==" -ForegroundColor Cyan
$sttDir = Join-Path $PWD "vendor\stt_model"
Remove-Item $sttDir -Recurse -Force -ErrorAction SilentlyContinue
$sttParent = Join-Path $PWD "vendor"
New-Item -ItemType Directory -Force -Path $sttParent | Out-Null
$sttArchive = Join-Path $env:RUNNER_TEMP "vosk-ru-small.zip"
$sttUrl = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
Invoke-WebRequest -Uri $sttUrl -OutFile $sttArchive
Expand-Archive -Path $sttArchive -DestinationPath $sttParent -Force
$extracted = Join-Path $sttParent "vosk-model-small-ru-0.22"
if (-not (Test-Path "$extracted\am")) { throw "Vosk Russian model extraction failed." }
Rename-Item -Path $extracted -NewName "stt_model"
if (-not (Test-Path "$sttDir\am")) { throw "Bundled Vosk model verification failed." }

Write-Host "== JARVIS: prepare bundled male Piper voice ==" -ForegroundColor Cyan
$piperUrl = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
$piperArchive = Join-Path $env:RUNNER_TEMP "piper_windows_amd64.zip"
$piperExtract = Join-Path $env:RUNNER_TEMP "piper_extract"
$vendorPiper = Join-Path $PWD "vendor\piper"
Remove-Item $vendorPiper -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $piperExtract -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $piperExtract | Out-Null
New-Item -ItemType Directory -Force -Path $vendorPiper | Out-Null
Invoke-WebRequest -Uri $piperUrl -OutFile $piperArchive
Expand-Archive -Path $piperArchive -DestinationPath $piperExtract -Force
$piperExe = Get-ChildItem -Path $piperExtract -Filter "piper.exe" -Recurse | Select-Object -First 1
if (-not $piperExe) { throw "Piper binary not found." }
Copy-Item "$($piperExe.Directory.FullName)\*" $vendorPiper -Recurse -Force
$voiceBase = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/dmitri/medium"
Invoke-WebRequest -Uri "$voiceBase/ru_RU-dmitri-medium.onnx" -OutFile "$vendorPiper\ru_RU-dmitri-medium.onnx"
Invoke-WebRequest -Uri "$voiceBase/ru_RU-dmitri-medium.onnx.json" -OutFile "$vendorPiper\ru_RU-dmitri-medium.onnx.json"
if (-not (Test-Path "$vendorPiper\piper.exe")) { throw "Piper verification failed." }
if (-not (Test-Path "$vendorPiper\ru_RU-dmitri-medium.onnx")) { throw "Piper Russian voice verification failed." }

Write-Host "== JARVIS: tests ==" -ForegroundColor Cyan
pytest tests/ -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed; release build aborted." }

pyinstaller jarvis.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "JARVIS.exe build failed." }
pyinstaller jarvis_desktop.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "JARVIS Desktop.exe build failed." }

$release = "release"
Remove-Item $release -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item "dist\jarvis.exe" "$release\JARVIS.exe"
Copy-Item "dist\jarvis_desktop.exe" "$release\JARVIS Desktop.exe"
Copy-Item "vendor\piper" "$release\piper" -Recurse -Force
Copy-Item "vendor\stt_model" "$release\stt_model" -Recurse -Force
@"
JARVIS — Windows x64
Основное приложение: JARVIS Desktop.exe
STT: Vosk, русский, локально.
TTS: Piper, русский мужской голос, локально.
Настройки: %APPDATA%\JARVIS\settings.json
"@ | Set-Content -Path "$release\README.txt" -Encoding UTF8

$package = "JARVIS-Windows-x64.zip"
Remove-Item $package -Force -ErrorAction SilentlyContinue
Compress-Archive -Path "$release\JARVIS.exe", "$release\JARVIS Desktop.exe", "$release\piper", "$release\stt_model", "$release\README.txt" -DestinationPath $package -Force
Write-Host "Release ready: $package" -ForegroundColor Green
