$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$startCmd = Join-Path $repoRoot "scripts\windows\start-toyoko-monitor.cmd"
$taskName = "ToyokoMonitor"

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$startCmd`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew

Register-ScheduledTask `
  -TaskName $taskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Description "Start Toyoko Monitor in WSL at logon" `
  -Force | Out-Null

Write-Host "Registered scheduled task: $taskName"
Write-Host "Start command: $startCmd"
Write-Host "Run once now with: Start-ScheduledTask -TaskName $taskName"
