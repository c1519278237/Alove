param(
    [string]$ApiBaseUrl = 'http://10.0.2.2:8000/api/v1'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$flutterExe = 'E:\DevTools\flutter\bin\flutter.bat'
$env:ANDROID_HOME = 'C:\Users\Administrator\AppData\Local\Android\Sdk'
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
Set-Location -LiteralPath (Join-Path $projectRoot 'apps\mobile')
& $flutterExe build apk --debug `
    --dart-define="API_BASE_URL=$ApiBaseUrl"
Write-Host 'APK: apps\mobile\build\app\outputs\flutter-apk\app-debug.apk'
