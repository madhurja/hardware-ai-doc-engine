$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo

$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$localUrl = "http://127.0.0.1:8000"
$hostIps = @()
try {
    $hostIps = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
        Where-Object { $_.AddressFamily -eq "InterNetwork" -and -not $_.IPAddressToString.StartsWith("127.") } |
        ForEach-Object { $_.IPAddressToString } |
        Select-Object -Unique
} catch {
    $hostIps = @()
}

Write-Host ""
Write-Host "Hardware AI Documentation Engine"
Write-Host "Local app link: $localUrl"
foreach ($ip in $hostIps) {
    Write-Host "Android same-Wi-Fi link: http://$ip`:8000"
}
Write-Host ""
Write-Host "Keep this window open while using the app."
Write-Host ""

Start-Process $localUrl
& $python -m uvicorn app:app --host 0.0.0.0 --port 8000
