<#
.SYNOPSIS
    Builds the signed Android APK and installs it on the phone over USB.

.DESCRIPTION
    The APK is all native (Kotlin/Compose, no WebView since session E), so there is no
    web build: the server address goes to gradle (-PfinancasApiBase, BuildConfig.API_BASE_URL).
    1. Runs the native unit tests and assembles the release APK, signed with the
       key from new-keystore.ps1. The version is the commit count and date+commit,
       so every build is newer than the last and recognisable.
    2. Installs it with `adb install -r` on the one phone connected with USB
       debugging on. The install keeps the app's data: the offline queue, the
       saved cache and the login survive the update.

    Needs Android Studio (its JDK and SDK) and a key from new-keystore.ps1.

.PARAMETER ApiBase
    The backend address the app talks to. Default: the home server's Tailscale HTTPS name
    (`tailscale serve` in front of the Docker container, DEPLOY.md).

.PARAMETER NoInstall
    Build only; do not look for a phone.

.PARAMETER VersionCode
    Override the versionCode (default: the commit count). CI-built APKs are 10000 + the
    workflow run number, so a local build over one needs a higher value here.

.PARAMETER SkipTests
    Skip the native unit tests (faster; the APK is the same).

.EXAMPLE
    .\mobile\build-apk.ps1
    .\mobile\build-apk.ps1 -NoInstall
#>

[CmdletBinding()]
param(
    [string]$ApiBase = 'https://guilhermeserver.tail5084ff.ts.net',
    [switch]$NoInstall,
    [switch]$SkipTests,
    [int]$VersionCode = 0
)

. (Join-Path $PSScriptRoot 'android-tools.ps1')

$Root = Split-Path $PSScriptRoot -Parent
$AndroidDir = Join-Path $Root 'frontend\android'
$Apk = Join-Path $AndroidDir 'app\build\outputs\apk\release\app-release.apk'

function Invoke-Step([string]$Title, [scriptblock]$Action) {
    Write-Host "==> $Title" -ForegroundColor Cyan
    # Gradle and apksigner print progress on stderr; under 'Stop', Windows PowerShell
    # would call that a failure when the output is redirected. The exit code decides.
    $ErrorActionPreference = 'Continue'
    & $Action
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed: $Title (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

if (-not ($ApiBase -match '^https://')) {
    Write-Host "ApiBase must be an https:// address (got '$ApiBase')." -ForegroundColor Red
    exit 1
}
$ApiBase = $ApiBase.TrimEnd('/')

if (-not (Test-Path $KeystoreProperties)) {
    Write-Host "No signing key: $KeystoreProperties is missing." -ForegroundColor Red
    Write-Host 'Create it once with:  .\mobile\new-keystore.ps1   (and back up the folder it prints).' -ForegroundColor Yellow
    exit 1
}

$env:JAVA_HOME = Find-JavaHome
$env:ANDROID_HOME = Find-AndroidSdk
$env:FINANCAS_KEYSTORE_PROPERTIES = $KeystoreProperties
$Adb = Join-Path $env:ANDROID_HOME 'platform-tools\adb.exe'

# Version: the commit count always grows (Android refuses to install a lower
# versionCode over a higher one); the name says which commit, and -dirty when the
# tree had uncommitted changes.
$versionCode = if ($VersionCode -gt 0) { $VersionCode } else { [int](git -C $Root rev-list --count HEAD) }
$sha = (git -C $Root rev-parse --short HEAD).Trim()
$dirty = if (git -C $Root status --porcelain) { '-dirty' } else { '' }
$versionName = '{0}-{1}{2}' -f (Get-Date -Format 'yyyy.MM.dd'), $sha, $dirty
Write-Host "Version $versionName (code $versionCode), API $ApiBase" -ForegroundColor Cyan

$gradleTasks = @()
if (-not $SkipTests) { $gradleTasks += 'testReleaseUnitTest' }
$gradleTasks += 'assembleRelease'

Push-Location $AndroidDir
try {
    Invoke-Step 'Building the signed APK' {
        .\gradlew.bat @gradleTasks "-PfinancasVersionCode=$versionCode" "-PfinancasVersionName=$versionName" "-PfinancasApiBase=$ApiBase"
    }
} finally {
    Pop-Location
}

if (-not (Test-Path $Apk)) {
    Write-Host "Gradle finished but $Apk is missing." -ForegroundColor Red
    exit 1
}

# Refuse an unsigned or wrongly signed APK before it reaches the phone.
$buildTools = Get-ChildItem (Join-Path $env:ANDROID_HOME 'build-tools') -Directory -ErrorAction SilentlyContinue |
    Sort-Object { [version]($_.Name -replace '[^0-9.].*$', '') } | Select-Object -Last 1
if ($buildTools) {
    Invoke-Step 'Checking the signature' { & (Join-Path $buildTools.FullName 'apksigner.bat') verify $Apk }
}

Write-Host "APK: $Apk" -ForegroundColor Green
if ($NoInstall) { exit 0 }

$devices = @(& $Adb devices | Select-String -Pattern '^(\S+)\s+device$' | ForEach-Object { $_.Matches[0].Groups[1].Value })
if ($devices.Count -eq 0) {
    Write-Host 'No phone found. Connect it with USB, enable USB debugging, accept the prompt on the phone, and run again.' -ForegroundColor Yellow
    Write-Host '(Or install the APK above by hand; it is already built.)' -ForegroundColor Yellow
    exit 1
}
if ($devices.Count -gt 1) {
    Write-Host "More than one device connected ($($devices -join ', ')). Leave only the phone connected." -ForegroundColor Yellow
    exit 1
}

Write-Host "==> Installing on $($devices[0])" -ForegroundColor Cyan
# adb reports failures on stderr; under 'Stop', Windows PowerShell would throw on the
# first stderr line instead of letting us read the reason.
$ErrorActionPreference = 'Continue'
$output = & $Adb -s $devices[0] install -r $Apk 2>&1 | Out-String
$ErrorActionPreference = 'Stop'
Write-Host $output.Trim()
if ($output -match 'INSTALL_FAILED_UPDATE_INCOMPATIBLE') {
    # Never uninstall automatically: that would delete the offline queue.
    Write-Host 'The installed app was signed with a different key. Check the Pendentes screen is empty,' -ForegroundColor Yellow
    Write-Host 'then uninstall it from the phone and run this again.' -ForegroundColor Yellow
    exit 1
}
if ($output -match 'INSTALL_FAILED_VERSION_DOWNGRADE') {
    # CI-built APKs are 10000 + run number (DEPLOY.md, "New APK"): a local build is lower.
    Write-Host 'The phone has a newer APK (from CI). Pass -VersionCode above it to install this build.' -ForegroundColor Yellow
    exit 1
}
if ($output -notmatch 'Success') { exit 1 }
Write-Host 'Installed.' -ForegroundColor Green
