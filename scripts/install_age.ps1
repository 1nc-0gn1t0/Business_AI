param([Parameter(Mandatory)][string]$Directory)
$ErrorActionPreference = 'Stop'
# Official release hashes pinned independently of each download. No global install/PATH change.
if ($IsWindows -or $env:OS -eq 'Windows_NT') {
    $asset = 'age-v1.3.2-windows-amd64.zip'
    $sha = 'f48d8f8f9ebe903ab5027ed067652f2cc1db94bc206976430133b905dcd8e8c7'
} elseif ($IsLinux) {
    $asset = 'age-v1.3.2-linux-amd64.tar.gz'
    $sha = 'cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10'
} else { throw 'Supported installer targets: Windows/Linux amd64' }
New-Item -ItemType Directory -Path $Directory -ErrorAction Stop | Out-Null
$archive = Join-Path $Directory $asset
Invoke-WebRequest "https://github.com/FiloSottile/age/releases/download/v1.3.2/$asset" -OutFile $archive
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha) {
    throw 'age release checksum mismatch; nothing executed'
}
if ($asset.EndsWith('.zip')) { Expand-Archive -LiteralPath $archive -DestinationPath $Directory }
else {
    tar -xzf $archive -C $Directory
    if ($LASTEXITCODE) { throw 'age extraction failed' }
}
Write-Output (Join-Path $Directory 'age')
