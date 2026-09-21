# Build the JARVIS core and desktop EXEs on Windows.
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install -e ".[all]"
python -m pip install --upgrade pyinstaller pytest faster-whisper huggingface-hub elevenlabs tzdata

Write-Host "== JARVIS: prepare bundled offline STT (faster-whisper tiny) ==" -ForegroundColor Cyan
$sttDir = Join-Path $PWD "vendor\stt_model"
Remove-Item $sttDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $sttDir | Out-Null

# Hugging Face can temporarily answer 429 when several GitHub runners hit the
# same model at once. Retry with backoff instead of failing the whole build.
$sttReady = $false
for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
        python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Systran/faster-whisper-tiny', local_dir=r'vendor/stt_model')"
        if (Test-Path "$sttDir\model.bin") {
            $sttReady = $true
            break
        }
    } catch {
        Write-Warning "STT model download attempt $attempt failed: $($_.Exception.Message)"
    }
    if ($attempt -lt 5) {
        $delay = 15 * $attempt
        Write-Host "Повтор загрузки STT через $delay сек..." -ForegroundColor Yellow
        Start-Sleep -Seconds $delay
    }
}
if (-not $sttReady) { throw "Offline faster-whisper model download failed after 5 attempts." }

Write-Host "== JARVIS: prepare bundled male voice ==" -ForegroundColor Cyan
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
if (-not $piperExe) { throw "Piper binary not found in downloaded archive." }
$piperRoot = $piperExe.Directory.FullName
Copy-Item "$piperRoot\*" $vendorPiper -Recurse -Force
$voiceBase = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/dmitri/medium"
Invoke-WebRequest -Uri "$voiceBase/ru_RU-dmitri-medium.onnx" -OutFile "$vendorPiper\ru_RU-dmitri-medium.onnx"
Invoke-WebRequest -Uri "$voiceBase/ru_RU-dmitri-medium.onnx.json" -OutFile "$vendorPiper\ru_RU-dmitri-medium.onnx.json"
if (-not (Test-Path "$vendorPiper\piper.exe")) { throw "Bundled Piper verification failed." }
if (-not (Test-Path "$vendorPiper\ru_RU-dmitri-medium.onnx")) { throw "Bundled Dmitri voice verification failed." }

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
Copy-Item "dist\jarvis_desktop.exe" "$release\JARVIS.exe"

@"
JARVIS — Windows x64

JARVIS.exe — единственное пользовательское приложение с графическим интерфейсом, голосом, памятью и инструментами.
Отдельный JARVIS Desktop.exe пользователю не нужен.
Piper не поставляется отдельно: локальный голос Windows используется как резерв для ElevenLabs.

Конфигурация сохраняется в %APPDATA%\JARVIS\settings.json.
"@ | Set-Content -Path "$release\README.txt" -Encoding UTF8

$package = "JARVIS-Windows-x64.zip"
Remove-Item $package -Force -ErrorAction SilentlyContinue
Compress-Archive -Path "$release\JARVIS.exe", "$release\README.txt" -DestinationPath $package -Force

Write-Host ""
Write-Host "Release ready:" -ForegroundColor Green
Write-Host "  $release\JARVIS.exe"
Write-Host "  $package"
