param(
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 5173,
    [int]$ParentFrontendPort = 5174,
    [bool]$KillExistingBackend = $true,
    [bool]$StopBeforeStart = $true,
    [bool]$StopCpolar = $true,
    [switch]$OpenBrowser
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendScript = Join-Path $PSScriptRoot 'start_backend.ps1'
$frontendScript = Join-Path $PSScriptRoot 'start_frontend.ps1'
$stopScript = Join-Path $PSScriptRoot 'stop_all.ps1'

$killExistingBackendInt = if ($KillExistingBackend) { 1 } else { 0 }
$childKillExistingInt = if ($StopBeforeStart) { 0 } else { 1 }
$parentKillExistingInt = 0

$backendCmd = "Set-Location '$repoRoot'; powershell -ExecutionPolicy Bypass -File '$backendScript' -Port $BackendPort -KillExisting $killExistingBackendInt"
$childFrontendCmd = "Set-Location '$repoRoot'; powershell -ExecutionPolicy Bypass -File '$frontendScript' -Port $FrontendPort -KillExisting $childKillExistingInt"
$parentFrontendCmd = "Set-Location '$repoRoot'; powershell -ExecutionPolicy Bypass -File '$frontendScript' -Port $ParentFrontendPort -KillExisting $parentKillExistingInt"

if ($StopBeforeStart) {
    Write-Host 'Stopping existing backend/frontend processes before startup...' -ForegroundColor Cyan
    $stopArgs = @(
        '-ExecutionPolicy', 'Bypass',
        '-File', $stopScript,
        '-BackendPort', $BackendPort,
        '-FrontendPort', $FrontendPort,
        '-FrontendAltPort', $ParentFrontendPort
    )
    if ($StopCpolar) {
        $stopArgs += '-StopCpolar'
    }
    & powershell @stopArgs
}

Write-Host 'Launching backend and frontend windows...' -ForegroundColor Green
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $backendCmd)
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $childFrontendCmd)
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $parentFrontendCmd)

Write-Host "Child URL:  http://127.0.0.1:$FrontendPort/" -ForegroundColor Cyan
Write-Host "Parent URL: http://127.0.0.1:$ParentFrontendPort/" -ForegroundColor Cyan
Write-Host "Backend docs: http://127.0.0.1:$BackendPort/docs" -ForegroundColor Cyan

if ($OpenBrowser.IsPresent) {
    Start-Process "http://127.0.0.1:$FrontendPort"
    Start-Process "http://127.0.0.1:$ParentFrontendPort"
}
