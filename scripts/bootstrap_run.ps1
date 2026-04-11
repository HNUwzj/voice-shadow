param(
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 5173,
    [int]$ParentFrontendPort = 5174,
    [switch]$OpenBrowser,
    [bool]$StopCpolar = $false
)

$ErrorActionPreference = "Stop"

function Assert-Command([string]$Name, [string]$Hint) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Missing command: $Name. $Hint"
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$envExample = Join-Path $backendDir ".env.example"
$envFile = Join-Path $backendDir ".env"
$startAllScript = Join-Path $PSScriptRoot "start_all.ps1"

Write-Host "Checking prerequisites..." -ForegroundColor Cyan
Assert-Command -Name "python" -Hint "Install Python 3.10+ and add it to PATH."
Assert-Command -Name "node" -Hint "Install Node.js 18+ and add it to PATH."
Assert-Command -Name "npm" -Hint "Install npm 9+ and add it to PATH."

if (-not (Test-Path $startAllScript)) {
    throw "Script not found: $startAllScript"
}

if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host "Created backend/.env from .env.example" -ForegroundColor Yellow
}

if (Test-Path $envFile) {
    $apiLine = Select-String -Path $envFile -Pattern "^DASHSCOPE_API_KEY=" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($apiLine) {
        $apiValue = ($apiLine.Line -split "=", 2)[1].Trim()
        if (-not $apiValue -or $apiValue -eq "your_dashscope_api_key_here") {
            Write-Host "Warning: DASHSCOPE_API_KEY is not configured in backend/.env" -ForegroundColor Yellow
        }
    }
}

Write-Host "Bootstrapping and launching services..." -ForegroundColor Green
$startAllParams = @{
    BackendPort = $BackendPort
    FrontendPort = $FrontendPort
    ParentFrontendPort = $ParentFrontendPort
    StopBeforeStart = $true
    StopCpolar = $StopCpolar
}

if ($OpenBrowser.IsPresent) {
    $startAllParams.OpenBrowser = $true
}

Set-Location $repoRoot
& $startAllScript @startAllParams
