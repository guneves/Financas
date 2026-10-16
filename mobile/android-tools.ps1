# Shared by build-apk.ps1 and new-keystore.ps1 (dot-sourced): finds the JDK and
# the Android SDK that Android Studio installs, and where the signing key lives.
# Environment variables win over the defaults, so a non-standard install works.

$ErrorActionPreference = 'Stop'

# Outside the repository on purpose: the keystore and its passwords never go to git.
$KeystoreDir = if ($env:FINANCAS_KEYSTORE_DIR) { $env:FINANCAS_KEYSTORE_DIR } else { Join-Path $HOME '.financas-android' }
$KeystoreProperties = if ($env:FINANCAS_KEYSTORE_PROPERTIES) { $env:FINANCAS_KEYSTORE_PROPERTIES } else { Join-Path $KeystoreDir 'keystore.properties' }

function Find-JavaHome {
    $candidates = @(
        $env:JAVA_HOME,
        'C:\Program Files\Android\Android Studio\jbr',
        (Join-Path $env:LOCALAPPDATA 'Programs\Android Studio\jbr')
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path (Join-Path $candidate 'bin\java.exe'))) { return $candidate }
    }
    Write-Host 'No JDK found. Install Android Studio (it bundles one in "jbr"), or set JAVA_HOME to a JDK 21.' -ForegroundColor Red
    exit 1
}

function Find-AndroidSdk {
    $candidates = @(
        $env:ANDROID_HOME,
        $env:ANDROID_SDK_ROOT,
        (Join-Path $env:LOCALAPPDATA 'Android\Sdk')
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path (Join-Path $candidate 'platform-tools'))) { return $candidate }
    }
    Write-Host 'No Android SDK found. Open Android Studio once and let it install the SDK, or set ANDROID_HOME.' -ForegroundColor Red
    exit 1
}
