$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @()

if ($env:VIRTUAL_ENV) {
  $activePython = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
  if (Test-Path $activePython) {
    $pythonCandidates += $activePython
  }
}

$pythonCandidates += @(
  (Join-Path $projectRoot ".venv312\Scripts\python.exe"),
  (Join-Path $projectRoot ".venv\Scripts\python.exe")
) | Select-Object -Unique

$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
  throw "No project Python interpreter was found. Create the virtual environment first."
}

Set-Location $projectRoot
Write-Host ("Using Python: {0}" -f $python)
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
