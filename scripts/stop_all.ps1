param(
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 5173,
    [int]$FrontendAltPort = 5174,
    [switch]$StopCpolar
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot 'frontend'

function Stop-PortListener([int]$Port, [string]$Name) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $pidValue = $listener.OwningProcess
        Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped $Name PID $pidValue on port $Port" -ForegroundColor Yellow
    } else {
        Write-Host "$Name not running on port $Port" -ForegroundColor DarkGray
    }
}

function Stop-RepoViteProcesses() {
    $escapedFrontendDir = [regex]::Escape($frontendDir)
    $processes = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match 'vite' -and
            $_.CommandLine -match $escapedFrontendDir
        }

    if (-not $processes) {
        Write-Host 'No repo Vite process found' -ForegroundColor DarkGray
        return
    }

    foreach ($proc in $processes) {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped frontend Vite PID $($proc.ProcessId)" -ForegroundColor Yellow
    }
}

Stop-PortListener -Port $BackendPort -Name 'backend'
Stop-PortListener -Port $FrontendPort -Name 'frontend'
Stop-PortListener -Port $FrontendAltPort -Name 'frontend'
Stop-RepoViteProcesses

if ($StopCpolar.IsPresent) {
    $cpolarList = Get-Process cpolar -ErrorAction SilentlyContinue
    if ($cpolarList) {
        foreach ($proc in $cpolarList) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped cpolar PID $($proc.Id)" -ForegroundColor Yellow
        }
    } else {
        Write-Host 'cpolar is not running' -ForegroundColor DarkGray
    }
}

Write-Host 'Stop process routine completed.' -ForegroundColor Green
