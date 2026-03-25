param(
  [string]$ServiceName = "ToyokoMonitorService",
  [string]$DisplayName = "Toyoko Monitor",
  [string]$NssmPath = "nssm.exe"
)

$ErrorActionPreference = "Stop"

$nssmCommand = Get-Command $NssmPath -ErrorAction SilentlyContinue
if (-not $nssmCommand) {
  throw "nssm.exe was not found. Install NSSM and make sure it is in PATH, or pass the full path with -NssmPath."
}

$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingService) {
  throw "Service $ServiceName already exists. Remove the existing service first or use a different service name."
}

$startupTask = Get-ScheduledTask -TaskName "ToyokoMonitor" -ErrorAction SilentlyContinue
if ($startupTask) {
  Write-Warning "The logon scheduled task ToyokoMonitor was detected. Disable or remove it first to avoid duplicate starts and port 8000 conflicts."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$startCmd = Join-Path $repoRoot "scripts\windows\start-toyoko-monitor.cmd"
$stdoutLog = Join-Path $repoRoot "logs\nssm-service.stdout.log"
$stderrLog = Join-Path $repoRoot "logs\nssm-service.stderr.log"

$credential = Get-Credential -Message "Enter the Windows account that should run this service. Use the same account that owns the WSL/Ubuntu setup if possible."
$password = $credential.GetNetworkCredential().Password
if (-not $password) {
  throw "The service account password cannot be empty."
}

New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot "logs") | Out-Null

& $nssmCommand.Source install $ServiceName "C:\Windows\System32\cmd.exe" "/c `"$startCmd`""
if ($LASTEXITCODE -ne 0) {
  throw "NSSM install failed with exit code: $LASTEXITCODE"
}

& $nssmCommand.Source set $ServiceName DisplayName $DisplayName | Out-Null
& $nssmCommand.Source set $ServiceName Description "Run Toyoko Monitor via WSL and conda web." | Out-Null
& $nssmCommand.Source set $ServiceName Start SERVICE_AUTO_START | Out-Null
& $nssmCommand.Source set $ServiceName AppDirectory $repoRoot | Out-Null
& $nssmCommand.Source set $ServiceName AppStdout $stdoutLog | Out-Null
& $nssmCommand.Source set $ServiceName AppStderr $stderrLog | Out-Null
& $nssmCommand.Source set $ServiceName ObjectName $credential.UserName $password | Out-Null

Start-Service -Name $ServiceName

Write-Host "Windows service installed and started: $ServiceName"
Write-Host "Display name: $DisplayName"
Write-Host "Log file: $stdoutLog"
Write-Host "Log file: $stderrLog"
Write-Host "Manage it with services.msc or Task Manager -> Services."
