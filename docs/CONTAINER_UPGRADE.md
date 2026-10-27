# Container upgrade / H-06-FU · Linux amd64 · 27 October 2026

**Existing installations: do not run an in-place `docker compose up` against the
old PGDATA.** PostgreSQL remains major17, but PostGIS3.5→3.6 changes Debian11→13
and glibc. Use an authenticated encrypted dump and a **new project/cluster/volume**.
The guarded image refuses an existing unmarked directory before starting PostgreSQL.
Do not defeat that guard by adding its marker to an old volume.

[Measured evidence](qa/H-06-FU_CONTAINER_REPORT.md), [backup procedure](BACKUP_RESTORE.md).
No working container, F-00 archive or existing volume was upgraded by this task.

## Images and compatibility

- DB build: `docker build -f infra/docker/postgis.Dockerfile -t business-ai-postgis-hardened infra/docker`.
  Base17-3.6 digest1ac10b25…; PostgreSQL17.11/PostGIS3.6.4/Debian13.7.
  Runs as postgres999:999, no gosu, no capabilities. Do not chown an old user volume.
- API: same Python3.12/glibc base and locked Python packages. Runtime mount package,
  nsenter and infocmp removed; essential shared libraries retained. Their scanner
  findings are still reported. Build with `docker compose build api` (no startup).
- Web unchanged. Ollama0.40.11 digestdea72d1e… tested on the same Qwen GGUF/digest,
  GPU and CPU. README new-install command is pinned; it does not update an existing
  container. Keep loopback binding, OLLAMA_NO_CLOUD=1 and one active model/inference.
- pg_dump17.5→pg_restore17.11 tested. No major upgrade or direct old-PGDATA reuse.
  Schema stays0008_reports. SQLAlchemy/psycopg/Alembic app versions unchanged.

## Safe owner-operated migration

1. Record current container/image IDs, DB role/settings, extensions and all schemas.
   Check free disk/RAM; preserve original Compose config/images/volume. Stop writers
   for final cutover, including ingestion/DDL. Never run prune, volume rm or downgrade.
2. Follow BACKUP_RESTORE to create and authenticate a new **age** backup using the
   existing project. Keep identity separately. Record public ciphertext checksums;
   no plaintext dumps, passwords or private manifest in Git/CI.
3. Build new images only. Start a different project (for example
   `h06futarget-<unique-id>`) on unused loopback ports, with a **new** volume or tmpfs.
   Never attach business-ai_postgres_data or the H-05 QA volume. For tmpfs set
   `uid=999,gid=999,mode=0700`; named Docker volumes inherit image directory ownership.
   Initial bootstrap DB and target DB must have different names.
4. Authenticate the archive before createdb; create target from template0. Restore
   transactionally with `--exit-on-error --single-transaction --no-owner --no-acl`.
   Recreate roles/settings separately as applicable; backups do not carry cluster globals.
5. Compare every application table count/SHA, schema/index fingerprint, invalid indexes,
   extensions and geometries. Check Alembic upgrade/check, owner404, consents, CAS,
   idempotency, audit, immutable PDF/JSON and geo/finance/new export/readiness.
   Never waive a hash mismatch just because server/extension versions should change.
6. H-06-FU tool below allows only the measured transition; unknown versions/extensions
   fail. Extra user schemas, nonempty user topology/TIGER data, custom functions,
   cluster roles/collations need their own fingerprints and validation before cutover.
   This rehearsal covers public application data and five extension versions, not
   arbitrary uninspected schemas or logical equivalence of every spatial function.
7. Geo ranking intentionally fingerprints `spatial_runtime`. Recalculate on the new
   runtime before creating a new report; stale references return409. Do not alter old
   immutable report bytes. Fixture scores remained exactly equal, not a guarantee
   for every real geometry after GEOS/PROJ changes.
8. Only the owner switches configured API/ports after acceptance and final backup.
   Keep the original cluster stopped/preserved as rollback source. After new writes,
   switching back loses those writes unless reconciled; define a write-freeze/recovery
   decision first. App-only rollback can keep the verified compatible schema.
   Never downgrade new PGDATA or share it between old/new containers.

Upstream rationale: [docker-postgis](https://github.com/postgis/docker-postgis),
[PG versioning](https://www.postgresql.org/support/versioning/),
[PostGIS upgrades](https://postgis.net/docs/postgis_administration.html#upgrading).
PostGIS image Docker recipes are MIT; installed PostGIS remains GPL2-or-later,
PostgreSQL permissive. Native/GPU redistribution obligations still require review.

## Reproduce the isolated populated drill

Use new private directories/configs, temporary **synthetic** age keys only, and exact
image pins from the report. No real user fixtures. Build integration stage:

```powershell
docker build --target integration-tests -t business-ai-h06fu-fixture apps/api
docker build -f infra/docker/postgis.Dockerfile -t business-ai-h06fu-db infra/docker
docker build -t business-ai-h06fu-api apps/api
./scripts/check_postgis_guard.ps1 -Image business-ai-h06fu-db
```

Create two separate private Compose files. Each has `db` and `api`; optional `fixture`
service uses business-ai-h06fu-fixture and `/app/.venv/bin/python` entrypoint, mounting
only the new private fixture directory at `/fixture`. Use synthetic password via
protected config/environment, PGHOST=db, PGUSER=business_ai, PGPORT=5432, LLM_PROVIDER=stub.
Source DB uses original digest01a6a70e…; target uses business-ai-h06fu-db and cap_dropALL.
Both DBs use tmpfs768MiB (target uid999/gid999). Source/target api uses the runtime
image and the corresponding PGDATABASE. Do not expose PostgreSQL ports. Target API/web
loopback ports must be unused; web health probe uses127.0.0.1, not localhost/IPv6.

Start source db under `h06fusource-<unique-id>`; create a new
`f00_restore_<unique-source>` with createdb/template0. Then:

```powershell
# $src/$dst are arrays: docker compose --project-directory <repo> -p <unique-project> -f <private-file>
docker @src run --rm --no-deps -T fixture -m tests.integration.h04fu_fixture seed --database $sourceDb --private /fixture --size large
# Test the working installation's extension set on synthetic data too:
docker @src exec -T db psql -U business_ai -d $sourceDb -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION fuzzystrmatch; CREATE EXTENSION postgis_topology; CREATE EXTENSION postgis_tiger_geocoder;'
uv run --locked --project apps/api python scripts/encrypted_backup.py backup --config $sourceConfig
uv run --locked --project apps/api python scripts/encrypted_backup.py verify --config $sourceConfig --bundle $bundle --identity $temporaryIdentity
docker @dst up -d --wait db
uv run --locked --project apps/api python scripts/restore_container_upgrade.py --config $targetConfig --bundle $bundle --identity $temporaryIdentity --target $targetDb
docker @dst run --rm --no-deps -T fixture -m tests.integration.h04fu_fixture verify --database $targetDb --private /fixture --size large
docker @dst run --rm --no-deps -T -e BA_RUN_DB_TESTS=1 fixture -m pytest tests/integration -q -p no:cacheprovider
```

Configs follow encrypted_backup.py: `{root, age_binary, project, compose_files,
database, recipient}`. root and identity must be separately protected; never put
identity values into JSON/CLI. Target project must start `h06futarget-` and target DB
must satisfy existing f00_restore_ validation. The normal encrypted restore deliberately
still requires equal versions; do not weaken it for migrations. This separate drill
permits only17.5/3.5.2→17.11/3.6.4, plpgsql1.0, optional fuzzystrmatch1.2 and
topology/TIGER3.5.2→3.6.4, with identical extension names and fingerprints.

On any mismatch preserve the isolated target and stop; no automatic deletion or
retry over an existing DB. After tests stop only exact new QA containers. H-05 QA
volume remains untouched; cleanup is a separate owner action.

## Image gate

`supply-chain.yml` builds final runtimes without starting a DB or downloading weights.
Checksum-pinned Trivy0.76.1 downloads one advisory DB and scans all four images with
that cache. `scripts/image_security.py` rejects incomplete scans, advisory DB older
than48h/future timestamps, and HIGH/CRITICAL with a reported fixed version. It reports
all unresolved counts and `release_baseline=OPEN` independently of the gate exit code.
No --ignore-unfixed, ignorefiles, VEX suppression or approved exceptions are installed.
An empty distro FixedVersion is not proof that no upstream fix exists: verify supported
repositories and vendor security pages. Never import unstable native ABI merely to
reduce a counter. Repeat scans before accepting any release.
