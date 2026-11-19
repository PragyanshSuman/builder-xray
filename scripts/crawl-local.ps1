<#
.SYNOPSIS
  Runs Builder X-Ray crawl jobs on this machine (ADR-003). Called nightly by the
  scheduled task created with register-crawl-task.ps1, or by hand.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\crawl-local.ps1 -Jobs survey
#>
param(
    # bxr subcommands to run, in order. Each gets CRAWL_ENABLED=1.
    [string[]]$Jobs = @('survey')
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repo 'data\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("crawl-{0:yyyyMMdd-HHmm}.log" -f (Get-Date))

function Write-Log([string]$msg) {
    $line = "{0:u} {1}" -f (Get-Date), $msg
    Add-Content -Path $log -Value $line -Encoding utf8
    Write-Output $line
}

Set-Location $repo
Write-Log "repo: $repo; jobs: $($Jobs -join ', ')"

# Pick up code/config changes, but never clobber local edits.
git pull --ff-only *>> $log
if ($LASTEXITCODE -ne 0) { Write-Log 'git pull failed; continuing with current checkout' }

$env:CRAWL_ENABLED = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
Set-Location (Join-Path $repo 'pipeline')

$failed = 0
foreach ($job in $Jobs) {
    Write-Log "start: bxr $job"
    python -m uv run bxr $job *>> $log
    $code = $LASTEXITCODE
    Write-Log "end: bxr $job (exit $code)"
    if ($code -ne 0) { $failed++ }
}

Write-Log "done; failed jobs: $failed"
exit $failed
