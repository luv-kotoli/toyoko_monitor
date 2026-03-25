param(
  [string]$ServiceName = "ToyokoMonitorService",
  [string]$NssmPath = "nssm.exe"
)

$ErrorActionPreference = "Stop"

$nssmCommand = Get-Command $NssmPath -ErrorAction SilentlyContinue
if (-not $nssmCommand) {
  throw "nssm.exe was not found. Install NSSM and make sure it is in PATH, or pass the full path with -NssmPath."
}

$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $existingService) {
  Write-Host "Service $ServiceName does not exist."
  exit 0
}

if ($existingService.Status -ne "Stopped") {
  Stop-Service -Name $ServiceName -Force
}

& $nssmCommand.Source remove $ServiceName confirm
if ($LASTEXITCODE -ne 0) {
  throw "NSSM remove failed with exit code: $LASTEXITCODE"
}

Write-Host "Windows service removed: $ServiceName"
