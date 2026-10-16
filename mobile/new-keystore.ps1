<#
.SYNOPSIS
    Creates the release signing key for the Android app. Run it once, ever.

.DESCRIPTION
    Writes two files outside the repository, in %USERPROFILE%\.financas-android
    (or $env:FINANCAS_KEYSTORE_DIR):

      financas-release.jks   the key (PKCS12, RSA 4096, valid for 100 years)
      keystore.properties    where it is and its password, read by Gradle

    The password is generated here and stored only in keystore.properties.

    BACK UP THAT FOLDER (both files) somewhere that is not this PC. Android only
    installs an update signed with the same key: if the key is lost, the next
    build cannot replace the installed app, and uninstalling it deletes whatever
    is still waiting in its offline queue.

    Refuses to run if a keystore already exists, so it can never replace the key.

.EXAMPLE
    .\mobile\new-keystore.ps1
#>

[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'android-tools.ps1')

$Keystore = Join-Path $KeystoreDir 'financas-release.jks'
$Alias = 'financas'

if ((Test-Path $Keystore) -or (Test-Path $KeystoreProperties)) {
    Write-Host "A signing key already exists in $KeystoreDir. Nothing was changed." -ForegroundColor Yellow
    Write-Host 'Replacing it would make the installed app impossible to update. Delete it by hand only if you mean that.' -ForegroundColor Yellow
    exit 1
}

$JavaHome = Find-JavaHome
$Keytool = Join-Path $JavaHome 'bin\keytool.exe'

New-Item -ItemType Directory -Force $KeystoreDir | Out-Null

# 32 random bytes as hex: no characters that need escaping in a .properties file.
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$password = -join ($bytes | ForEach-Object { $_.ToString('x2') })

# The password goes through the environment, not the command line, so it does not
# show up in the process list. PKCS12 uses one password for the store and the key.
$env:FINANCAS_KEYSTORE_PASSWORD = $password
# keytool prints its progress on stderr; under 'Stop', Windows PowerShell would treat
# that as a failure whenever the output is redirected. The exit code is the real check.
$ErrorActionPreference = 'Continue'
try {
    & $Keytool -genkeypair -v `
        -keystore $Keystore -storetype PKCS12 `
        -alias $Alias -keyalg RSA -keysize 4096 -validity 36500 `
        -dname 'CN=Financas, O=Pessoal, C=BR' `
        -storepass:env FINANCAS_KEYSTORE_PASSWORD -keypass:env FINANCAS_KEYSTORE_PASSWORD
    if ($LASTEXITCODE -ne 0) { throw "keytool failed with exit code $LASTEXITCODE" }
} finally {
    Remove-Item Env:\FINANCAS_KEYSTORE_PASSWORD -ErrorAction SilentlyContinue
    $ErrorActionPreference = 'Stop'
}

# Forward slashes: a backslash is an escape character in a .properties file.
$storeFile = $Keystore -replace '\\', '/'
@(
    "storeFile=$storeFile",
    "storePassword=$password",
    "keyAlias=$Alias",
    "keyPassword=$password"
) | Set-Content -Path $KeystoreProperties -Encoding ascii

Write-Host ''
Write-Host "Signing key created in $KeystoreDir" -ForegroundColor Green
Write-Host 'Back up that whole folder now (a USB stick, a password manager, cloud storage you trust).' -ForegroundColor Yellow
Write-Host 'Without it, no future build can update the app installed on the phone.' -ForegroundColor Yellow
