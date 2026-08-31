$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$flutterExe = 'E:\DevTools\flutter\bin\flutter.bat'
if (-not (Test-Path -LiteralPath $flutterExe)) {
    throw 'Flutter was not found at E:\DevTools\flutter.'
}
Set-Location -LiteralPath (Join-Path $projectRoot 'apps\mobile')
& $flutterExe run -d web-server --web-port 8080 `
    --dart-define='API_BASE_URL=http://127.0.0.1:8000/api/v1'
