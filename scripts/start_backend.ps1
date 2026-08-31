$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Python virtual environment .venv was not found. See README.md.'
}
Set-Location -LiteralPath $projectRoot
& $pythonExe -m uvicorn app.main:app --reload --app-dir services/api --host 0.0.0.0 --port 8000
