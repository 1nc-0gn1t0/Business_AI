param([Parameter(Mandatory)][string]$Image)
$ErrorActionPreference = 'Stop'
# Only a new tmpfs, never a user mount/volume. No network or privilege required.
foreach ($major in @('17', '18')) {
    $probe = @'
set -eu
printf '%s\n' "$1" > "$PGDATA/PG_VERSION"
printf 'unchanged\n' > "$PGDATA/sentinel"
if [ "$1" = 18 ]; then touch "$PGDATA/.business-ai-pg17-trixie-v1"; fi
set +e
business-ai-postgis-entrypoint postgres >/tmp/guard-output 2>&1
result=$?
set -e
test "$result" = 64
test "$(cat "$PGDATA/PG_VERSION")" = "$1"
test "$(cat "$PGDATA/sentinel")" = unchanged
test ! -e "$PGDATA/global/pg_control"
'@
    & docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges `
      --tmpfs '/var/lib/postgresql/data:uid=999,gid=999,mode=0700,size=16m' `
      --entrypoint sh $Image -c $probe probe $major
    if ($LASTEXITCODE) { throw 'PGDATA guard failed in disposable tmpfs' }
}
Write-Output 'PASS: unmarked PG17 and wrong-major PG18 refused without mutation'
