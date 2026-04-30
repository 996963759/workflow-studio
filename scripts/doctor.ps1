param(
  [switch]$SkipDocker
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root "server\.venv\Scripts\python.exe"

Set-Location $Root

Write-Host "Checking Node dependencies..."
if (-not (Test-Path "node_modules")) {
  throw "node_modules not found. Run npm.cmd install first."
}

Write-Host "Checking Python virtual environment..."
if (-not (Test-Path $Python)) {
  throw "Backend venv not found. Run python -m venv server/.venv and install requirements."
}

Write-Host "Checking frontend lint..."
npm.cmd run lint

Write-Host "Checking frontend build..."
Remove-Item dist -Recurse -Force -ErrorAction SilentlyContinue
npm.cmd run build

Write-Host "Checking backend imports..."
& $Python -m compileall server/src server/scripts server/tests

Write-Host "Checking backend unit tests..."
& $Python -m unittest discover server/tests

Write-Host "Checking Alembic configuration..."
& $Python -m alembic current

if (-not $SkipDocker) {
  Write-Host "Checking Docker Compose configuration..."
  docker compose config | Out-Null
}

Write-Host ""
Write-Host "Project doctor checks passed."
