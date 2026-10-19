param(
    [string]$WebUrl = "http://127.0.0.1:5173",
    [string]$ApiUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
foreach ($url in @("$ApiUrl/healthz", "$WebUrl/healthz")) {
    $health = Invoke-RestMethod -Uri $url -TimeoutSec 15
    if ($health.status -ne "ok" -or $health.database -ne "ok" -or !$health.postgis_version) {
        throw "Invalid health response: $url"
    }
    Write-Host "PASS $url (PostGIS $($health.postgis_version))"
}

$page = Invoke-WebRequest -Uri $WebUrl -UseBasicParsing -TimeoutSec 15
if ($page.StatusCode -ne 200 -or $page.Content -notmatch '<title>Business AI' -or $page.Content -notmatch '/assets/') {
    throw "Built React page is unavailable: $WebUrl"
}
Write-Host "PASS $WebUrl (built React page)"
