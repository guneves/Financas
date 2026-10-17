<#
.SYNOPSIS
    Deploys (or rolls back) the app on the home server by hand, from this PC.

.DESCRIPTION
    The everyday deploy is automatic: a push to main runs .github/workflows/deploy.yml,
    which builds ghcr.io/guneves/financas-app and has the server pull it. This script
    does the server half of that by hand, for when the workflow is not an option:

      1. copies compose.yaml to the server if it differs (the server's .env is never written);
      2. over ssh, pulls the image from GHCR and runs `docker compose up -d`.

    It never builds: the image must already be in GHCR (pushed by the workflow).
    Every command on the server is `sudo docker ...` with no environment variables,
    so the NOPASSWD sudoers rule (no SETENV) covers it.

.PARAMETER Rollback
    A commit SHA (as tagged in GHCR, the full 40 characters): pull that image,
    retag it as :latest and restart. Migrations are not undone.

.PARAMETER CreateOnly
    Pull and create the container without starting it — the first deploy, before
    importing the PC's data into the volume (see DEPLOY.md).

.PARAMETER Server
    The ssh destination (user@host). Default: $env:FINANCAS_SERVER.

.EXAMPLE
    .\deploy.ps1
    .\deploy.ps1 -Rollback 5291150c0ffee...
    .\deploy.ps1 -CreateOnly
#>

[CmdletBinding()]
param(
    [string]$Rollback,
    [switch]$CreateOnly,
    [string]$Server = $env:FINANCAS_SERVER
)

$ErrorActionPreference = 'Stop'

if (-not $Server) {
    throw 'No server: pass -Server user@host or set FINANCAS_SERVER (DEPLOY.md).'
}

$RemoteDir = '/srv/apps/financas'
$Image = 'ghcr.io/guneves/financas-app'

function Invoke-Native {
    param([string]$What, [scriptblock]$Command)
    Write-Host "==> $What" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$What failed (exit code $LASTEXITCODE)."
    }
}

if ($Rollback -and $Rollback -notmatch '^[0-9a-f]{40}$') {
    throw 'Rollback takes the full 40-character commit SHA (the GHCR tag).'
}

# --- 1. The server's directory and compose.yaml -------------------------------
Write-Host "==> Checking $Server`:$RemoteDir" -ForegroundColor Cyan
$remote = ssh $Server "if [ ! -d $RemoteDir ]; then echo nodir; elif [ ! -f $RemoteDir/.env ]; then echo noenv; else sha256sum $RemoteDir/compose.yaml 2>/dev/null | cut -d' ' -f1; fi"
if ($LASTEXITCODE -ne 0) { throw "Could not reach $Server over ssh." }
$remote = "$remote".Trim()
if ($remote -eq 'nodir') {
    throw "$RemoteDir does not exist on the server. Do the first-time setup in DEPLOY.md."
}
if ($remote -eq 'noenv') {
    throw "$RemoteDir/.env does not exist on the server. Create it first (DEPLOY.md); this script never writes it."
}

$compose = Join-Path $PSScriptRoot 'compose.yaml'
if ($remote -ne (Get-FileHash $compose -Algorithm SHA256).Hash.ToLower()) {
    # Only compose.yaml, by name: the server's .env is never in a copy.
    Invoke-Native 'Copying compose.yaml (changed)' { scp $compose "${Server}:$RemoteDir/compose.yaml" }
} else {
    Write-Host '    compose.yaml unchanged' -ForegroundColor DarkGray
}

# --- 2. Pull and start ---------------------------------------------------------
if ($Rollback) {
    $pull = "sudo docker pull ${Image}:$Rollback && sudo docker tag ${Image}:$Rollback ${Image}:latest"
    $what = "Rolling back to $Rollback"
} else {
    $pull = 'sudo docker compose pull'
    $what = 'Pulling the latest image'
}
if ($CreateOnly) {
    $start = 'sudo docker compose create'
} else {
    $start = 'sudo docker compose up -d && sudo docker image prune -f > /dev/null && sudo docker compose ps'
}
Invoke-Native $what { ssh $Server "cd $RemoteDir && $pull && $start" }

if ($CreateOnly) {
    Write-Host 'Container created, not started. Import the data (DEPLOY.md), then run .\deploy.ps1.' -ForegroundColor Yellow
} elseif ($Rollback) {
    Write-Host "Running $Rollback. The next push to main (or .\deploy.ps1) moves :latest forward again." -ForegroundColor Green
} else {
    Write-Host 'Deployed.' -ForegroundColor Green
}
