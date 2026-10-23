$ErrorActionPreference = "Stop"

$vendor = Join-Path (Get-Location) "ui\vendor"
New-Item -ItemType Directory -Force -Path $vendor | Out-Null

$base = "https://raw.githubusercontent.com/mrdoob/three.js/r180/build"
$files = @("three.module.js", "three.core.js")
foreach ($file in $files) {
    $destination = Join-Path $vendor $file
    if (-not (Test-Path $destination) -or (Get-Item $destination).Length -lt 10000) {
        Write-Host "Downloading pinned Three.js engine asset: $file" -ForegroundColor Cyan
        Invoke-WebRequest -Uri "$base/$file" -OutFile $destination -UseBasicParsing
    }
    if (-not (Test-Path $destination) -or (Get-Item $destination).Length -lt 10000) {
        throw "Three.js engine asset is missing or incomplete: $destination"
    }
}
Write-Host "Three.js r180 assets are ready." -ForegroundColor Green
