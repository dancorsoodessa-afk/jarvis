$ErrorActionPreference = "Continue"

Write-Host "=== JARVIS AI BACKEND DIAGNOSTIC ==="
Write-Host ""

Write-Host "[1] JARVIS environment"
foreach ($name in @("JARVIS_PROVIDER","JARVIS_CHAT_URL","JARVIS_CHAT_MODEL","JARVIS_CHAT_KEY","JARVIS_LOCAL")) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ($name -eq "JARVIS_CHAT_KEY" -and $value) { $value = "<set>" }
    Write-Host ("{0} = {1}" -f $name, $(if ($value) { $value } else { "<empty>" }))
}
Write-Host ""

Write-Host "[2] Dragon-related processes"
$dragon = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match "dragon"
}
if ($dragon) {
    $dragon | Select-Object Id, ProcessName, Path | Format-Table -AutoSize
} else {
    Write-Host "Dragon process не найден."
}
Write-Host ""

Write-Host "[3] Common local AI ports"
$ports = 1234,11434,8080,8000,10000,9119
foreach ($port in $ports) {
    $test = Test-NetConnection 127.0.0.1 -Port $port -WarningAction SilentlyContinue
    Write-Host ("127.0.0.1:{0} -> {1}" -f $port, $(if ($test.TcpTestSucceeded) { "OPEN" } else { "closed" }))
}
Write-Host ""

Write-Host "[4] OpenAI-compatible /v1/models"
$bases = @(
    "http://127.0.0.1:1234/v1",
    "http://127.0.0.1:11434/v1",
    "http://127.0.0.1:8080/v1",
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:10000/v1",
    "http://127.0.0.1:9119/v1"
)
foreach ($base in $bases) {
    try {
        $models = Invoke-RestMethod -Uri "$base/models" -TimeoutSec 3
        $ids = @($models.data | ForEach-Object { $_.id } | Where-Object { $_ })
        if ($ids.Count -gt 0) {
            Write-Host "$base -> OK"
            $ids | ForEach-Object { Write-Host "  MODEL: $_" }
        } else {
            Write-Host "$base -> отвечает, но моделей нет"
        }
    } catch {
        Write-Host "$base -> недоступен"
    }
}
Write-Host ""
Write-Host "=== END ==="
