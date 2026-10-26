param(
    [Parameter(Mandatory)][string]$Config,
    [Parameter(Mandatory)][string]$Python,
    [string]$TaskName = 'BusinessAIEncryptedBackup',
    [switch]$Install,
    [switch]$TestOnly
)
$ErrorActionPreference = 'Stop'
$Config = (Resolve-Path -LiteralPath $Config).Path
$Python = (Resolve-Path -LiteralPath $Python).Path
$resolved = & $Python -c 'import sys,pathlib,json;print(json.dumps(dict(python=str(pathlib.Path(sys._base_executable).resolve()),config=str(pathlib.Path(sys.argv[1]).resolve()))))' $Config | ConvertFrom-Json
if ($LASTEXITCODE) { throw 'Cannot resolve native scheduler paths' }
$Python = $resolved.python
$Config = $resolved.config
$scriptFile = Join-Path $PSScriptRoot 'run_backup_job.ps1'
$runner = (Get-Command pwsh -ErrorAction Stop).Source
$account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
if (-not $Install -and -not $TestOnly) {
    Write-Output 'No tasks installed. Review configuration, then run with -Install (12h backup / hourly status, logged-in user only).'
    exit 0
}
if ($TestOnly) {
    $c = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
    if ($c.database -notmatch '^f00_restore_[a-z0-9_]+$') { throw 'TestOnly requires an isolated QA source' }
    $TaskName = 'BusinessAI-H04FU-test-' + [guid]::NewGuid().ToString('N')
    try {
        $action = New-ScheduledTaskAction -Execute $runner -Argument ('-NoProfile -File "{0}" -Operation backup -Config "{1}" -Python "{2}"' -f $scriptFile,$Config,$Python) -WorkingDirectory (Split-Path $PSScriptRoot)
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(15)
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
        $deadline = (Get-Date).AddMinutes(3)
        do {
            Start-Sleep -Seconds 5
            $info = Get-ScheduledTaskInfo -TaskName $TaskName
            $task = Get-ScheduledTask -TaskName $TaskName
            if ($info.LastRunTime.Year -gt 2000 -and $task.State -ne 'Running' -and $info.LastTaskResult -notin @(267009,267011)) {
                if ($info.LastTaskResult -ne 0) { throw ('Scheduled backup failed (result {0}); inspect private status/events' -f $info.LastTaskResult) }
                Write-Output 'Scheduled trigger actually executed: PASS'
                return
            }
        } while ((Get-Date) -lt $deadline)
        throw 'Scheduled trigger did not complete before deadline'
    } finally {
        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
    }
} else {
    # Never replace an existing operator task silently.
    foreach ($operation in @('backup','status')) {
        $name = if ($operation -eq 'backup') { $TaskName } else { "$TaskName-Status" }
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw 'Task exists; review it explicitly' }
    }
    foreach ($operation in @('backup','status')) {
        $name = if ($operation -eq 'backup') { $TaskName } else { "$TaskName-Status" }
        $hours = if ($operation -eq 'backup') { 12 } else { 1 }
        $action = New-ScheduledTaskAction -Execute $runner -Argument ('-NoProfile -File "{0}" -Operation {1} -Config "{2}" -Python "{3}"' -f $scriptFile,$operation,$Config,$Python) -WorkingDirectory (Split-Path $PSScriptRoot)
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours $hours)
        Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    }
    Write-Output 'Installed. Review LastRunTime / LastTaskResult and run encrypted_backup.py status. No wake/always-on/offsite guarantee.'
}
