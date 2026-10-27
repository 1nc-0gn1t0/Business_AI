param([Parameter(Mandatory=$true)][string]$Directory)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Directory) { throw 'Choose a new tool directory' }
if ($IsWindows -or $env:OS -eq 'Windows_NT') {
    $asset = 'gitleaks_8.30.1_windows_x64.zip'
    $sha = 'd29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e'
    $binary = 'gitleaks.exe'
} elseif ($IsLinux) {
    $asset = 'gitleaks_8.30.1_linux_x64.tar.gz'
    $sha = '551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb'
    $binary = 'gitleaks'
} else { throw 'Supported tooling: Windows/Linux x64' }
New-Item -ItemType Directory -Path $Directory | Out-Null
$archive = Join-Path $Directory $asset
Invoke-WebRequest "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/$asset" -OutFile $archive
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha) {
    throw 'Gitleaks checksum mismatch; nothing executed'
}
if ($asset.EndsWith('.zip')) { Expand-Archive -LiteralPath $archive -DestinationPath $Directory }
else {
    tar -xzf $archive -C $Directory
    if ($LASTEXITCODE) { throw 'Gitleaks extraction failed' }
}
Write-Output (Join-Path $Directory $binary)
