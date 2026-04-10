param(
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 5173,
    [int]$FrontendAltPort = 5174,
    [switch]$StopCpolar
)

$ErrorActionPreference = 'Stop'

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

Stop-PortListener -Port $BackendPort -Name 'backend'
Stop-PortListener -Port $FrontendPort -Name 'frontend'
Stop-PortListener -Port $FrontendAltPort -Name 'frontend'

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
