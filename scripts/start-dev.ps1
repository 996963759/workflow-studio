param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root "server\.venv\Scripts\python.exe"

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
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return $true }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)
  return $false
}

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

if (Test-PortListening $BackendPort) {
  Write-Host "Backend port $BackendPort is already in use. Reusing existing service."
} else {
  Write-Host "Starting backend on http://127.0.0.1:$BackendPort ..."
  Start-Process -FilePath $Python `
    -ArgumentList "-m","uvicorn","server.src.main:app","--host","127.0.0.1","--port",$BackendPort `
    -WorkingDirectory $Root `
    -WindowStyle Hidden
}

if (Test-PortListening $FrontendPort) {
  Write-Host "Frontend port $FrontendPort is already in use. Reusing existing service."
} else {
  Write-Host "Starting frontend on http://127.0.0.1:$FrontendPort ..."
  Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run","dev","--","--host","127.0.0.1","--port",$FrontendPort `
    -WorkingDirectory $Root `
    -WindowStyle Hidden
}

$backendReady = Wait-HttpReady "http://127.0.0.1:$BackendPort/api/health" 30
$frontendReady = Wait-HttpReady "http://127.0.0.1:$FrontendPort" 30

Write-Host ""
Write-Host "Backend:  http://127.0.0.1:$BackendPort $(if ($backendReady) { '(ready)' } else { '(starting or unavailable)' })"
Write-Host "Frontend: http://127.0.0.1:$FrontendPort $(if ($frontendReady) { '(ready)' } else { '(starting or unavailable)' })"
Write-Host ""
Write-Host "Tip: run scripts/test-all.ps1 to execute the regression checks."
