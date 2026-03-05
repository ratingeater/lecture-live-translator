$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @()

function Add-PythonCandidate {
  param(
    [string]$Path
  )

  if (-not [string]::IsNullOrWhiteSpace($Path) -and (Test-Path $Path)) {
    $script:pythonCandidates += $Path
  }
}

function Test-UvicornAvailable {
  param(
    [string]$PythonPath
  )

  & $PythonPath -c "import uvicorn" *> $null
  return ($LASTEXITCODE -eq 0)
}

try {
  $currentPython = (Get-Command python -ErrorAction Stop).Source
  Add-PythonCandidate -Path $currentPython
} catch {
}

if ($env:CONDA_PREFIX) {
  Add-PythonCandidate -Path (Join-Path $env:CONDA_PREFIX "python.exe")
}

if ($env:VIRTUAL_ENV) {
  $activePython = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
  Add-PythonCandidate -Path $activePython
}

@(
  (Join-Path $projectRoot ".venv312\Scripts\python.exe"),
  (Join-Path $projectRoot ".venv\Scripts\python.exe")
) | Select-Object -Unique | ForEach-Object { Add-PythonCandidate -Path $_ }

$python = $pythonCandidates |
  Select-Object -Unique |
  Where-Object { Test-UvicornAvailable -PythonPath $_ } |
  Select-Object -First 1

if (-not $python) {
  throw "No usable Python interpreter with uvicorn was found."
}

Set-Location $projectRoot
Write-Host ("Using Python: {0}" -f $python)
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
