param(
    [Parameter(Mandatory)][string]$Config,
    [Parameter(Mandatory)][string]$Python,
    [ValidateSet('backup','status')][string]$Operation = 'backup'
)
$ErrorActionPreference = 'Stop'
try {
    Set-Location (Split-Path $PSScriptRoot)
    $settings = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
    # This directory is provisioned/ACL-checked by encrypted_backup.py first.
    # CLI errors are redacted; no keys/passwords are in arguments or output.
    $jobLog = Join-Path $settings.root "job-$Operation.log"
    $errorLog = Join-Path $settings.root "job-$Operation-error.log"
    $arguments = '"{0}" {1} --config "{2}"' -f (Join-Path $PSScriptRoot 'encrypted_backup.py'),$Operation,$Config
    $job = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory (Split-Path $PSScriptRoot) -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput $jobLog -RedirectStandardError $errorLog
    exit $job.ExitCode
} catch {
    Write-Output 'Backup job launcher failed; inspect task result and private configuration'
    exit 1
}
