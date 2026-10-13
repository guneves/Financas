<#
.SYNOPSIS
    Starts the FinanceMVP backend and frontend together.

.DESCRIPTION
    Replaces the two-terminal routine. Launches Flask (port 5000) and Vite
    (port 5173) as background jobs, waits for both to answer, and keeps
    streaming their output until you press Ctrl+C — which stops both.

.PARAMETER Tests
    Run the backend test suite instead of starting the app.

.PARAMETER Built
    Build the frontend and start the backend alone: Flask serves the build at
    http://localhost:5000, screen and API on one origin. This is the mode the
    phone uses (through `tailscale serve`); there is no Vite and no hot reload.

.PARAMETER NoBrowser
    Do not open the browser once the frontend is up.

.EXAMPLE
    .\start.ps1
    .\start.ps1 -Tests
    .\start.ps1 -Built
#>

[CmdletBinding()]
param(
    [switch]$Tests,
    [switch]$Built,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
$BackendDir = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'
$Python = Join-Path $Root '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    Write-Host "Virtualenv not found at $Python" -ForegroundColor Red
    Write-Host "Create it with:  python -m venv .venv" -ForegroundColor Yellow
    Write-Host "Then:            .venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt" -ForegroundColor Yellow
    exit 1
}

if ($Tests) {
    Write-Host 'Running backend tests...' -ForegroundColor Cyan
    Push-Location $BackendDir
    try {
        & $Python -m pytest
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
    Write-Host 'Frontend dependencies missing. Running npm install...' -ForegroundColor Yellow
    Push-Location $FrontendDir
    try { npm install } finally { Pop-Location }
}

if (-not (Test-Path (Join-Path $BackendDir '.env'))) {
    Write-Host 'backend\.env not found — copying from .env.example.' -ForegroundColor Yellow
    Write-Host 'Set a real JWT_SECRET before using this outside localhost.' -ForegroundColor Yellow
    Copy-Item (Join-Path $BackendDir '.env.example') (Join-Path $BackendDir '.env')
}

if ($Built) {
    Write-Host 'Building the frontend...' -ForegroundColor Cyan
    Push-Location $FrontendDir
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Frontend build failed.' -ForegroundColor Red
            exit $LASTEXITCODE
        }
    } finally {
        Pop-Location
    }
}

$jobs = @()

Write-Host 'Starting backend on http://localhost:5000 ...' -ForegroundColor Cyan
$jobs += Start-Job -Name 'financas-backend' -ScriptBlock {
    param($python, $dir)
    Set-Location $dir
    & $python app.py 2>&1
} -ArgumentList $Python, $BackendDir

if (-not $Built) {
    Write-Host 'Starting frontend on http://localhost:5173 ...' -ForegroundColor Cyan
    $jobs += Start-Job -Name 'financas-frontend' -ScriptBlock {
        param($dir)
        Set-Location $dir
        npm run dev 2>&1
    } -ArgumentList $FrontendDir
}

function Wait-ForUrl {
    param([string]$Url, [int]$TimeoutSeconds = 45)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

try {
    if (Wait-ForUrl 'http://localhost:5000/api/health') {
        Write-Host 'Backend is up.' -ForegroundColor Green
    } else {
        Write-Host 'Backend did not answer /api/health in time — check the log below.' -ForegroundColor Yellow
    }

    if ($Built) {
        if (Wait-ForUrl 'http://localhost:5000/') {
            Write-Host 'The built app is served at http://localhost:5000.' -ForegroundColor Green
            if (-not $NoBrowser) { Start-Process 'http://localhost:5000' }
        } else {
            Write-Host 'The backend did not serve the build in time. Check the log below.' -ForegroundColor Yellow
        }
    } elseif (Wait-ForUrl 'http://localhost:5173') {
        Write-Host 'Frontend is up.' -ForegroundColor Green
        if (-not $NoBrowser) { Start-Process 'http://localhost:5173' }
    } else {
        Write-Host 'Frontend did not answer in time — check the log below.' -ForegroundColor Yellow
    }

    Write-Host ''
    Write-Host 'Running. Press Ctrl+C to stop.' -ForegroundColor Cyan
    Write-Host ''

    while ($true) {
        $jobs | Receive-Job
        $dead = $jobs | Where-Object { $_.State -in @('Failed', 'Completed', 'Stopped') }
        if ($dead) {
            Write-Host "Service '$($dead[0].Name)' exited. Shutting down." -ForegroundColor Red
            break
        }
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host 'Stopping services...' -ForegroundColor Cyan
    $jobs | Receive-Job -ErrorAction SilentlyContinue
    $jobs | Stop-Job -ErrorAction SilentlyContinue
    $jobs | Remove-Job -Force -ErrorAction SilentlyContinue
    Write-Host 'Done.' -ForegroundColor Green
}
