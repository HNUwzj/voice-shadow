param(
    [int]$Port = 8001,
    [object]$KillExisting = $true
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'
$venvActivate = Join-Path $backendDir '.venv\Scripts\Activate.ps1'
$venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'
$requirements = Join-Path $backendDir 'requirements.txt'

Set-Location $backendDir

if ($KillExisting -is [string]) {
    $text = $KillExisting.Trim().ToLowerInvariant()
    if ($text -in @('1', 'true', '$true', 'yes', 'y')) {
        $KillExisting = $true
    } elseif ($text -in @('0', 'false', '$false', 'no', 'n')) {
        $KillExisting = $false
    }
}
$KillExisting = [bool]$KillExisting

if (-not (Test-Path $venvPython)) {
    Write-Host 'Creating Python virtual environment...' -ForegroundColor Cyan
    python -m venv .venv
}

if (Test-Path $venvActivate) {
    . $venvActivate
}

Write-Host 'Installing backend dependencies...' -ForegroundColor Cyan
& $venvPython -m pip install -r $requirements | Out-Host

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owningProcess = $listener.OwningProcess
    if ($KillExisting) {
        Write-Host "Port $Port is in use by PID $owningProcess, stopping it..." -ForegroundColor Yellow
        Stop-Process -Id $owningProcess -Force
    } else {
        throw "Port $Port is already in use by PID $owningProcess."
    }
}

Write-Host "Starting backend on http://127.0.0.1:$Port" -ForegroundColor Green
& $venvPython -m uvicorn app.main:app --host 0.0.0.0 --port $Port --app-dir $backendDir
