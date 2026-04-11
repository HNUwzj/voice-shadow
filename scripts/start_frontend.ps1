param(
    [int]$Port = 5173,
    [object]$KillExisting = $true,
    [int[]]$ExtraPortsToClear = @(5174, 5175, 5176)
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot 'frontend'

Set-Location $frontendDir

Write-Host 'Installing frontend dependencies...' -ForegroundColor Cyan
npm install | Out-Host

if ($KillExisting -is [string]) {
    $text = $KillExisting.Trim().ToLowerInvariant()
    if ($text -in @('1', 'true', '$true', 'yes', 'y')) {
        $KillExisting = $true
    } elseif ($text -in @('0', 'false', '$false', 'no', 'n')) {
        $KillExisting = $false
    }
}
$KillExisting = [bool]$KillExisting

function Stop-PortListener([int]$TargetPort) {
    $listener = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) {
        return
    }

    $owningProcess = $listener.OwningProcess
    Write-Host "Port $TargetPort is in use by PID $owningProcess, stopping it..." -ForegroundColor Yellow
    Stop-Process -Id $owningProcess -Force -ErrorAction SilentlyContinue
}

function Stop-RepoViteProcesses() {
    $escapedFrontendDir = [regex]::Escape($frontendDir)
    $processes = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match 'vite' -and
            $_.CommandLine -match $escapedFrontendDir
        }

    foreach ($proc in $processes) {
        Write-Host "Stopping existing frontend process PID $($proc.ProcessId)..." -ForegroundColor Yellow
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

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

if ($KillExisting) {
    Stop-RepoViteProcesses

    foreach ($extraPort in $ExtraPortsToClear) {
        if ($extraPort -ne $Port) {
            Stop-PortListener -TargetPort $extraPort
        }
    }
}

Write-Host "Starting frontend on http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Frontend URL: http://127.0.0.1:$Port/" -ForegroundColor Cyan
npm run dev -- --host 0.0.0.0 --port $Port --strictPort
