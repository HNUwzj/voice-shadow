param(
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 5173,
    [bool]$KillExistingBackend = $true,
    [bool]$StopBeforeStart = $true,
    [bool]$StopCpolar = $true
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendScript = Join-Path $PSScriptRoot 'start_backend.ps1'
$frontendScript = Join-Path $PSScriptRoot 'start_frontend.ps1'
$stopScript = Join-Path $PSScriptRoot 'stop_all.ps1'

$killExistingBackendInt = if ($KillExistingBackend) { 1 } else { 0 }

$backendCmd = "Set-Location '$repoRoot'; powershell -ExecutionPolicy Bypass -File '$backendScript' -Port $BackendPort -KillExisting $killExistingBackendInt"
$frontendCmd = "Set-Location '$repoRoot'; powershell -ExecutionPolicy Bypass -File '$frontendScript' -Port $FrontendPort"

if ($StopBeforeStart) {
    Write-Host 'Stopping existing backend/frontend processes before startup...' -ForegroundColor Cyan
    $stopCpolarFlag = if ($StopCpolar) { '$true' } else { '$false' }
    powershell -ExecutionPolicy Bypass -File $stopScript -BackendPort $BackendPort -FrontendPort $FrontendPort -FrontendAltPort 5174 -StopCpolar:$stopCpolarFlag
}

Write-Host 'Launching backend and frontend in separate windows...' -ForegroundColor Green
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $backendCmd)
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $frontendCmd)
