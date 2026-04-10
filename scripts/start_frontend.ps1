param(
    [int]$Port = 5173,
    [bool]$KillExisting = $true
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot 'frontend'

Set-Location $frontendDir

Write-Host 'Installing frontend dependencies...' -ForegroundColor Cyan
npm install | Out-Host

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owningProcess = $listener.OwningProcess
    if ($KillExisting) {
        Write-Host "Port $Port is in use by PID $owningProcess, stopping it..." -ForegroundColor Yellow
        Stop-Process -Id $owningProcess -Force
    } else {
        Write-Host "Port $Port is in use by PID $owningProcess, Vite may choose another port." -ForegroundColor Yellow
    }
}

Write-Host "Starting frontend on http://127.0.0.1:$Port" -ForegroundColor Green
npm run dev -- --host 0.0.0.0 --port $Port
