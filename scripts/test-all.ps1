param(
  [int]$SmokePort = 8001,
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root "server\.venv\Scripts\python.exe"
$StartedBackend = $null

function Test-PortListening {
  param([int]$Port)
  return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-HttpReady {
  param(
    [string]$Url,
    [int]$Seconds = 30
  )
  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
      if ($response.StatusCode -eq 200) { return $true }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)
  return $false
}

try {
  Set-Location $Root

  if (-not (Test-Path $Python)) {
    Write-Host "Creating backend virtual environment..."
    python -m venv server/.venv
  }

  if (-not $SkipInstall) {
    Write-Host "Installing backend dependencies..."
    & $Python -m pip install -r server/requirements.txt

    if (-not (Test-Path (Join-Path $Root "node_modules"))) {
      Write-Host "Installing frontend dependencies..."
      npm.cmd install
    }
  }

  Write-Host "Running frontend lint..."
  npm.cmd run lint

  Write-Host "Running frontend build..."
  npm.cmd run build

  Write-Host "Compiling backend Python files..."
  & $Python -m compileall server/src server/scripts server/tests

  Write-Host "Running backend unit tests..."
  & $Python -m unittest discover server/tests

  if (Test-PortListening $SmokePort) {
    throw "Smoke test port $SmokePort is already in use. Stop that process or pass -SmokePort with another value."
  }

  Write-Host "Starting temporary backend on http://127.0.0.1:$SmokePort ..."
  $StartedBackend = Start-Process -FilePath $Python `
    -ArgumentList "-m","uvicorn","server.src.main:app","--host","127.0.0.1","--port",$SmokePort `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru

  if (-not (Wait-HttpReady "http://127.0.0.1:$SmokePort/api/health" 30)) {
    throw "Temporary backend did not become ready on port $SmokePort."
  }

  Write-Host "Running backend smoke test..."
  $env:BASE_URL = "http://127.0.0.1:$SmokePort"
  & $Python server/scripts/smoke_test.py

  Write-Host ""
  Write-Host "All checks passed."
} finally {
  if ($StartedBackend -and -not $StartedBackend.HasExited) {
    Stop-Process -Id $StartedBackend.Id -ErrorAction SilentlyContinue
  }
}
