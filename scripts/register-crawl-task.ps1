<#
.SYNOPSIS
  Registers (or updates) the nightly "BuilderXRay Crawl" scheduled task for the
  current user (ADR-003). Runs at 01:30 local time; if the PC was off, it runs
  at the next opportunity. No admin rights needed.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\register-crawl-task.ps1 -Jobs crawl-up
  Unregister-ScheduledTask -TaskName 'BuilderXRay Crawl' -Confirm:$false   # to remove
#>
param(
    [Parameter(Mandatory = $true)][string[]]$Jobs,
    [string]$At = '01:30'
)

$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'crawl-local.ps1'
$jobArgs = ($Jobs | ForEach-Object { "'$_'" }) -join ','
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command `"& '$script' -Jobs $jobArgs`""
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 5) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName 'BuilderXRay Crawl' -Action $action -Trigger $trigger `
    -Settings $settings -Description 'Builder X-Ray nightly polite crawl (see docs/adr/003)' -Force | Out-Null
Write-Output "Registered 'BuilderXRay Crawl' daily at $At with jobs: $($Jobs -join ', ')"
