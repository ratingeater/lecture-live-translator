$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
  (Join-Path $projectRoot ".venv312\Scripts\python.exe"),
  (Join-Path $projectRoot ".venv\Scripts\python.exe")
)

$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
  throw "找不到虚拟环境 Python，请先创建并安装依赖。"
}

Set-Location $projectRoot
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
