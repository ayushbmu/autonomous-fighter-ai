$ErrorActionPreference = "Stop"

Set-Location "$PSScriptRoot/.."

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Error "Virtual environment not found. Run scripts/bootstrap.ps1 first."
}

& .\.venv\Scripts\python.exe -m pytest -q
