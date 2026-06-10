param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [string]$QueueBackend = "kafka",
  [string]$KafkaBootstrapServers = "127.0.0.1:9092",
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root "server\.venv\Scripts\python.exe"
$WorkerMarker = "workflow-studio-worker-$QueueBackend"

function Test-PortListening {
  param([int]$Port)
  return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Test-TcpEndpoint {
  param(
    [string]$HostName,
    [int]$Port
  )
  $client = [System.Net.Sockets.TcpClient]::new()
  try {
    $connect = $client.BeginConnect($HostName, $Port, $null, $null)
    if (-not $connect.AsyncWaitHandle.WaitOne(2000)) { return $false }
    $client.EndConnect($connect)
    return $true
  } catch {
    return $false
  } finally {
    $client.Close()
  }
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

$env:RUN_JOB_QUEUE_BACKEND = $QueueBackend
if ($QueueBackend -notin @("kafka", "thread")) {
  throw "RUN_JOB_QUEUE_BACKEND must be kafka. Use thread only for automated tests."
}
if ($QueueBackend -eq "kafka") {
  $env:KAFKA_BOOTSTRAP_SERVERS = $KafkaBootstrapServers
  $firstKafkaServer = ($KafkaBootstrapServers -split ",")[0].Trim()
  $kafkaParts = $firstKafkaServer -split ":"
  if ($kafkaParts.Length -lt 2) {
    throw "KAFKA_BOOTSTRAP_SERVERS must look like 127.0.0.1:9092."
  }
  $kafkaHost = $kafkaParts[0]
  $kafkaPort = [int]$kafkaParts[1]
  if (-not (Test-TcpEndpoint $kafkaHost $kafkaPort)) {
    throw "Kafka is not reachable at $firstKafkaServer. Start Kafka first, or use docker compose up --build for the full Kafka stack."
  }
}

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

if ($QueueBackend -eq "kafka") {
  $existingWorker = Get-CimInstance Win32_Process |
    Where-Object {
      $_.CommandLine -like "*server.src.worker*" -and
      $_.CommandLine -like "*$WorkerMarker*"
    } |
    Select-Object -First 1
  if ($existingWorker) {
    Write-Host "Worker for $QueueBackend queue is already running. Reusing existing service."
  } else {
    Write-Host "Starting $QueueBackend worker ..."
    Start-Process -FilePath $Python `
      -ArgumentList "-m","server.src.worker",$WorkerMarker `
      -WorkingDirectory $Root `
      -WindowStyle Hidden
  }
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
$queueDetail = if ($QueueBackend -eq "kafka") { " ($KafkaBootstrapServers)" } else { "" }
Write-Host "Queue:    $QueueBackend$queueDetail"
Write-Host ""
Write-Host "Tip: run scripts/test-all.ps1 to execute the regression checks."
