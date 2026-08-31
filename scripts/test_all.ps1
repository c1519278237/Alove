$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$dartExe = 'E:\DevTools\flutter\bin\cache\dart-sdk\bin\dart.exe'
$flutterExe = 'E:\DevTools\flutter\bin\flutter.bat'

Set-Location -LiteralPath $projectRoot
& $pythonExe -m ruff check services/api/app services/api/tests
& $pythonExe -m pytest services/api/tests -c services/api/pyproject.toml
Set-Location -LiteralPath (Join-Path $projectRoot 'apps\mobile')
& $dartExe analyze
& $flutterExe test --no-pub
