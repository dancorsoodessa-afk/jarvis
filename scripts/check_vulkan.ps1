$ErrorActionPreference = "Continue"

Write-Host "=== JARVIS LOCAL AI / VULKAN CHECK ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "GPU:"
Get-CimInstance Win32_VideoController |
    Select-Object Name, AdapterRAM, DriverVersion |
    Format-Table -AutoSize

Write-Host "Vulkan executables/libraries:"
Get-Command vulkaninfo, vkvia, vkcube -ErrorAction SilentlyContinue |
    Select-Object Name, Source

Write-Host ""
Write-Host "Vulkan registry:"
Get-ItemProperty "HKLM:\SOFTWARE\Khronos\Vulkan\Drivers" -ErrorAction SilentlyContinue |
    Format-List

Write-Host ""
Write-Host "llama.cpp:"
Get-Command llama-cli, llama-server -ErrorAction SilentlyContinue |
    Select-Object Name, Source

Write-Host ""
Write-Host "Ollama:"
Get-Command ollama -ErrorAction SilentlyContinue |
    Select-Object Name, Source

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
