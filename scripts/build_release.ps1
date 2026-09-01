param(
    [Parameter(Mandatory = $true)]
    [string]$ApiBaseUrl,
    [switch]$Android
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$flutterExe = 'E:\DevTools\flutter\bin\flutter.bat'
Set-Location -LiteralPath (Join-Path $projectRoot 'apps\mobile')
& $flutterExe pub get
& $flutterExe build web --release --dart-define="API_BASE_URL=$ApiBaseUrl"
if ($Android) {
    $signingProperties = Join-Path $projectRoot 'apps\mobile\android\key.properties'
    if (-not (Test-Path -LiteralPath $signingProperties)) {
        throw 'Android production signing is missing. Copy android/key.properties.example to android/key.properties and configure a private release keystore first.'
    }
    & $flutterExe build apk --release --dart-define="API_BASE_URL=$ApiBaseUrl"
}
Write-Host "Release API: $ApiBaseUrl"
