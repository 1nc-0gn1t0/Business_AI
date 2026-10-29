# BA2/U-02 — Dynamic Data Acquisition & Durable Import

29.10.2026. Base: merged PR32/main `7281121fc78c45fe7adda9115761a01137e1b907`.
Branch `codex/U-02-dynamic-data-acquisition`; actual commit/PR/CI in delivery report.
U-03/agent/industry models/frontend changes are not part of this implementation.

## Audit: the four existing sources

This is the exact U-01 inventory, not a list of hypothetical providers.

| ID / name | Actual adapter / endpoint | Registered categories | License / attribution | Availability / network | Acquisition / authorization / limits |
| --- | --- | --- | --- | --- | --- |
| `osm` / OpenStreetMap | OSMProvider local metadata; existing POI/walking operator importers; Overpass `https://overpass-api.de/api/interpreter` | `geo.mapped_poi`, `geo.admin_polygons`, `geo.pedestrian_network` | ODbL-1.0 / © OpenStreetMap contributors; verified existing local analysis, not unrestricted redistribution | adapter ready; remote availability unknown, network review_required by default | U-02 implements **POI only**, expiring operator smoke approval; public Overpass needs no login, no credentials sent; one fetch at a time, >=60s spacing, <=10 reservations/day, <=2 attempts/job |
| `synthetic` / Синтетические сценарии | SyntheticProvider and local versioned scenario importer, no endpoint | `scenario.finance` | CC0-1.0 authored fixtures / Sab0tage — synthetic demonstration | ready; network forbidden | Explicit local demo flag only; no remote acquisition, source auth/request limits not applicable |
| `ghsl` / GHSL | Placeholder, no connected dataset/endpoint | `demography.population`, `demography.density` | Dataset license/attribution unconfirmed; review_required | not_integrated; network forbidden | No automatic adapter; authorization/remote quotas unknown, never assumed unrestricted |
| `licensed` / Лицензированные источники | Placeholder, no contract/endpoint | `economy.rent`, `economy.industry`, `economy.macro` | License/attribution/contract unconfirmed; review_required | not_integrated; network forbidden | No automatic adapter; credentials/quotas require a future contract |

All **18 category IDs**, unchanged from U-01:

```text
geo.mapped_poi             geo.admin_polygons        geo.pedestrian_network
geo.vehicle_network        geo.buildings             geo.parking
geo.transit                geo.organizations         geo.zones
demography.population      demography.density        demography.age
economy.rent               economy.industry          economy.macro
user.budget                user.costs                scenario.finance
```

Only `geo.mapped_poi` can be acquired by U-02. Parking/transit/organizations may appear
as tags inside a POI extract, but are **not separately qualified category coverage**.
Walking remains an existing offline/operator importer. Vehicle access/routing,
population, market rent and industry economics are not delivered by this adapter.
User inputs and authored scenarios are not external observations.

### Source permission is narrower than data licensing

Reviewed [Overpass Commons](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html)
and [OSM copyright](https://www.openstreetmap.org/copyright) on29.10.2026.
The public service discourages bulk extraction and relying on it as an application's
permanent backend. Our adapter is therefore **operator-only, one-off small-AOI smoke**,
not public automatic city preparation. Packaged registry remains network review_required.
ODbL attribution and share-alike obligations survive normalization/import; a permissive
dataset license does not grant unlimited server capacity or a production SLA.

Reviewed operator config adds to the existing `osm` registration:

```json
{
  "network_permission": "permitted",
  "availability": "ready",
  "acquisition_scope": "operator_smoke",
  "acquisition_approved_until": "<operator-reviewed expiry in RFC3339>",
  "policy_revision": "<review revision>"
}
```

These are fields inside a complete validated registry file, not a standalone config.
Record purpose/terms/date in policy_note; expiry is enforced again before publication.
No active permission/token is committed. A different endpoint, sustained public service
or large export needs a separately reviewed adapter/policy; no arbitrary URL override.
An offline existing cache remains reusable under valid **local** use permission.

## Existing importers and minimal extension

`geo/provider.py` already loads bounded Overpass JSON and hashes normalized bytes;
`geo/ingest.py` deduplicates OSM type/id, rejects conflicting versions, inserts batches
of500, validates locations and boundary geometry, serializes by slug advisory lock,
atomically switches active version and preserves historical snapshots. Existing GiST/
dataset/category indexes are reused. It does not delete old datasets or user objects.
Walking builds separate in-memory topology; it is not a vehicle-network adapter.

JSON parsing and dedup still materialize a **bounded small extract**. A job wrapper does
not make them streaming. New `build_poi_query` omits administrative geometry, requests
meta/centers with timeout25s/maxsize32MiB on the remote server. The legacy query and
its manifest/normalization outputs stay supported. U-01 attests the new query as POI
only. No boundaries, roads or whole-city claims are inferred from those points.

The existing importer accepts an optional cancellation/heartbeat checkpoint callback;
legacy callers retain the same behavior. Partial/malformed selected objects fail new
publication; empty extracts are rejected instead of proving absence of businesses.
Outside-AOI centers retain existing importer diagnostics/limitations.

## Jobs, publication and recovery

Additive Alembic `0009_acquisition` adds only:

- `acquisition_jobs`: bounded request, scope/policy hashes, attempt, lease, fencing token,
  installation ID, expected active version, normalized byte checkpoint/manifest, safe result.
- `acquisition_requests`: operator idempotency key → payload hash/job ID.
- `acquisition_events`: job ID + monotonic sequence primary key; time/state/stage/safe code.

Readiness expects0009. Existing profile, report, financial and geo tables are unchanged.
Populated0008→0009, repeat upgrade and Alembic check are tested; no production downgrade.

```text
queued → claimed → fetching → validating → importing → verifying → activating → succeeded
                    ↘ retry_wait / failed / cancel_requested → cancelled
expired interrupted work → recovery_required or verified stopped-worker recovery → retry_wait
```

Creation is serialized in a short transaction. Idempotency key + changed input gives409;
another key for the same active scope attaches to that job. Scope includes source,
adapter profile revision, category, normalized numeric AOI, territory and freshness intent.
Changed registry hash cannot silently join a job with different policy. The stored hash
also pins effective resource limits; mismatched API/worker resource configuration fails
closed before acquisition. A current U-01 full-for-requested-scope snapshot returns a
completed cache result, without network.

Worker `once` takes a PostgreSQL **session advisory lock**, then atomically claims with
`FOR UPDATE SKIP LOCKED` under the admission lock. Claim commits before DNS/download.
The separate worker connection holding this mutex is not an API/H-03 pool connection.
Heartbeats use short transactions; no database transaction spans network waiting or parsing.
Import is the existing bounded atomic transaction, with statement timeout25s and callback
checks every250 elements/before activation. It takes the same slug lock **before** checking
expected active version. Final fence/lease/policy/cancel checks, data activation, result
and events commit together. Failure rolls back the new data and preserves old active data.

Validated normalized bytes (<=8MiB DB constraint, <=4MiB default operation policy) and
manifest/hash form the durable checkpoint. Completed/terminal jobs clear blob data but
retain manifest/hash/events/result. Restart resumes the verified checkpoint, not an
unverified partial download; import rollback is retried as one bounded AOI transaction.
There is no claim of intra-import streaming/batch resume for an entire city.

### Lease expiry does not prove process death

One stable **dedicated state directory** holds installation identity and OS process lock.
All worker launches must share it. The heavy work runs in that same process, without
child importers. Another live process cannot acquire that lock even after DB lease loss.
After restart, only the same installation with the acquired process lock and expired
lease may fence/recover its old job; it waits the source cooldown and keeps attempt caps.
Recovery also waits until no active PostgreSQL backend tagged with that job remains:
client process death alone need not immediately stop a server-side statement.
Another installation becomes recovery_required and does no heavy work. Loss/corruption
of state directory requires operator investigation/restoration, not blind automatic reset.

The session DB mutex also prevents other installations running queued work concurrently.
If its connection dies, a surviving process still owns the OS lock; another installation
cannot recover its active job. Never copy a live installation identity into a second host
or change state directories to bypass exclusion. Multi-host execution is unsupported.

Private `staging` has an installation ownership marker. Under the held process lock,
only that verified directory is cleaned on restart/exit; symlinks/ownership mismatch fail
closed. No volumes, historical snapshots, backup files or arbitrary user paths are removed.
Cancel is intent202: the worker stops at bounded I/O/SQL/checkpoint boundaries. A cancellation
after the final publication lock may observe already succeeded; it cannot undo a published dataset.

## Network boundary

`acquisition/network.py` uses Python stdlib, no additional HTTP dependency:

- Exact HTTPS host443/path, fixed backend query template. No user URLs/headers/proxies/cookies.
- Resolve all returned A/AAAA; reject non-global, multicast, reserved, mapped/transition IPv6
  and mixed answers. One resolver thread/waiter,5s deadline; stuck resolver fails closed.
- Connect numerically to a validated address, check TCP and TLS peer, retain default CA/
  hostname verification and SNI `overpass-api.de`. No second DNS lookup or disabled TLS.
- Redirect0, encoding identity only, JSON content type, declared/streamed bytes cap,
  short chunks and checksum/manifest/format/source-time checks. No archive/XML execution.
- Connect5s/read45s/total120s:45s allows public queue15s + query25s. A socket watchdog bounds
  slow headers/body; certificate failures are not retried as successful alternatives.
- Source fetch reservations are durable; >=60s, <=10/day and <=2attempts/job, including
  failed attempts. Retry-After is respected conservatively; unknown/date header waits24h.

Responses remain data, never model/system instructions. Safe status codes only; no
response bodies/credentials/DSNs/source text in logs or public errors. Original OSM editor
user/UID/change-set fields are removed by existing normalization before DB checkpoint storage.

## Operator API and isolation

All `/api/v2/acquisitions` routes require `BA_ACQUISITION_ENABLED=1` and configured
`BA_ACQUISITION_OPERATOR_TOKEN` >=32characters, header `X-Acquisition-Token`, constant-time
comparison. Missing configuration503; missing/wrong token401. Guest/conversation tokens
do not grant job access. This is one trusted operator role, not a public multi-tenant jobs API.
Prepared datasets are global open-data records, whereas job events/files remain operator-only.
No public administrative policy mutation or generic downloader is introduced.

| Operation | Result |
| --- | --- |
| POST `/api/v2/acquisitions` |202JobView (queued/deduplicated/cache result) |
| GET `/api/v2/acquisitions/{uuid}` | bounded state/stage/result/error/event cursor |
| GET `/api/v2/acquisitions/{uuid}/events?after=0&limit=50` | ordered replay, maximum100events/request |
| POST `/api/v2/acquisitions/{uuid}/cancel` |202cancellation intent/result |
| POST `/api/v2/data-registry/coverage` | existing U-01 coverage reads published metadata |

Example body (all URLs/owner/paths/SQL extra fields rejected):

```json
{"source_id":"osm","category":"geo.mapped_poi","territory":"ru-moscow",
 "aoi":{"west":37.611,"south":55.760,"east":37.613,"north":55.762},
 "freshness":"current","idempotency_key":"operator-one-off-unique-key"}
```

H-02 body/admission caps apply; acquisition POST is heavy. Pending jobs<=2; retained jobs
<=100 and idempotency mappings<=200 by default. Capacity full stops with429, never silently
purges historical data. Structured failures include source_not_permitted, unsupported
category, AOI too large, queue/storage limits, version conflict, network/time/format/resource
errors. H-05 correlation and safe envelopes remain. No fictitious percentage is returned:
stage/events are real, completed/total null when not measured.

## Resource budgets and measured result

`BA_ACQUISITION_LIMITS_JSON` configures the operation class, separate from source permission.
Default: AOI<=250000m² (PostGIS geography),4MiB response/normalized blob,10000elements,
180s active attempt,60s lease,256MiB RSS check,256MiB free staging disk. Upper structural
caps8MiB/25000elements/1km² are not permission for bulk use. No universal512MiB limit.
Opt-in Docker worker:0.5CPU,768MiB memory,32pids, non-root, read-only root, no capabilities.
These are bounded POI profile controls, not city-size guarantees. Parsing is byte-bounded;
RSS checks follow expensive phases, while the container memory cap is the hard boundary.

[Real smoke evidence](../qa/u-02/live-moscow.json):29.10.2026, Moscow AOI
37.611/55.760/37.613/55.762, public Overpass, single operator-reviewed request.23POI
published, all geometries valid SRID4326; ODbL/attribution/source timestamp/hashes preserved.
Current source file11685bytes, normalized5538bytes; the two temporary data files together
17223bytes plus manifest. The retained manifest serializes to922bytes, giving a derived
sum18145bytes for the three files; this is not a measured filesystem peak or WAL size.
Download39.346014s includes DNS/TLS/server waiting; import/verification0.067756s;
import CPU0.029344s via process_time, peak process RSS91545600bytes (~87.3MiB) via Linux
getrusage, pg_database_size delta90112bytes. PG delta is approximate isolated-cluster
data growth, excludes WAL, not long-term disk capacity. New instrumentation also records
active CPU/time and temporary file bytes; these fields were not present in this first live measurement.

The first job failed twice (DNS timeout/network); it remains failed. After inspecting TLS
without disabling verification and aligning read timeout with documented queue/query time,
a separate operator retry succeeded. Three fetch reservations total, no unbounded retry.
Repeat HTTP request reused current cache with no new source reservation. U-01 HTTP result:
POI/exact AOI available, whole city partial, vehicle/admin/walking missing. This is not
complete Moscow coverage, proof that all businesses are mapped or vehicle analysis support.

H-03 remains the sole in-process LLM queue; the worker is separate and does not hold API
connections or call Ollama. This measured small profile replaces the unmeasured blanket
512MiB proposal; concurrent live Qwen latency/combined peak was not benchmarked. Existing
MVP memory observations are in PERFORMANCE. Do not enlarge operation budgets without
combined host/VM/PG/WAL/LLM measurements; sustained/large acquisition remains closed.

## Local operation and safe tests

First back up/upgrade the intended database according to existing migration/restore docs.
Never run migration/smoke against an old working PGDATA or historical QA volume. Use an
isolated Compose project and synthetic test credentials. Keep worker state directory stable
across replacement; API/worker must read the **same** reviewed registry revision.

```powershell
# Set BA_ACQUISITION_REGISTRY_FILE to a reviewed complete registry file.
# Set a random operator-only BA_ACQUISITION_OPERATOR_TOKEN outside Git/frontend.
docker compose -f compose.yaml -f compose.acquisition.yaml --profile acquisition config --quiet
docker compose -f compose.yaml -f compose.acquisition.yaml --profile acquisition up --build -d
```

Base Compose is unchanged unless the explicit overlay/profile is selected. The new
`acquisition_state` volume belongs only to this optional worker; do not remove existing
volumes. Native Linux/WSL CLI from the backend environment:

```sh
python -m app.data.acquisition.worker --state-dir /dedicated/stable/operator-state --once
```

Without `--once` it polls every2s; without enabled/configured permission it cannot fetch.
Use one supervisor/replica, shared stable state path and the same DB. Worker restart does
not require restarting API. API can remain available while worker is offline; jobs stay queued.

```powershell
uv run --locked --project apps/api pytest apps/api/tests/test_acquisition.py apps/api/tests/test_registry.py -q
# Only with PG* pointing to a disposable test server, BA_RUN_DB_TESTS=1:
uv run --locked --project apps/api pytest apps/api/tests/integration/test_acquisition.py -q
```

Integration fixtures are explicitly artificial and do not fetch the Internet. They test
claim exclusion, restart/fencing/checkpoint, cancel download/import, retry budgets/resources,
old-version retention, cache reuse without network permission, API guest isolation/events,
valid geometry/U-01 category scope and populated migration fingerprints. Network tests
use deterministic transport fixtures, including SSRF/DNS/peer/redirect/size/format/timeouts.
For async readiness on Windows use the documented Selector test-process configuration.
Final local/CI results and actual commit are in the delivery report/HANDOFF.

## Recorded checks before commit

- Focused unit/API/registry/legacy geo:86PASS. Ruff/format and mypy139files PASS.
- Final new worker/PostGIS suite:18PASS/73.57s, including stale lease/fence publication
  rollback, old server statement recovery, sticky cancellation, SKIP LOCKED exclusion,
  metadata-capacity protection and mismatched resource-policy refusal before fetch.
- Broader existing DB suite:125PASS/1failure. The H-04 fixture expected every table
  populated; new acquisition tables were empty. It now includes an explicitly cancelled
  synthetic job, retaining that assertion. Populated migration/immutable PDF+JSON rerun PASS.
- Real tiny Moscow acquisition and HTTP cache/coverage verification PASS; real local
  Qwen v1 profile persistence HTTP200/ollama/56s, Decimal comparison verified. Initial
  smoke harness compared formatted money strings incorrectly; no product fix/inference repeat.
- Cross-container process-lock exclusion PASS, including a live holder/failed second worker.
- Isolated hardened Compose: ready/database/PostGIS/schema all ok, head0009, web200,
  registry4sources/18categories, empty Moscow missing, default operator API503. Tmpfs
  test mount needed UID999; production image permissions were not weakened. Optional
  worker overlay config validated; real worker ran separately with stable shared bind state.
- TypeScript/production build PASS, initial232KB unchanged. Chromium mock coffee flow1PASS.
  Strict v1 OpenAPI unchanged; only U-01 v2 SourceDefinition/AcquisitionOption extended.
- All owned QA runtime containers/tmpfs clusters stopped/removed after evidence; no
  persistent/user volumes were created or removed by the smoke. Private temp context
  files remain outside Git; no active credentials/permission config is committed.

Mandatory prek hooks run at commit; exact-HEAD CI/commit/PR are reported in delivery.
SKIP is not PASS. Future city-wide acquisition/industry/agent scenarios are not tested here.

## Boundaries and U-03 interfaces

No Qwen agent, new inference queue, frontend flow, finance/industry changes, vehicle graph,
geocoder, whole-city import, Redis/Celery or paid services. No global synthetic fallback.
Larger territories must be explicitly partitioned into independently approved bounded AOIs;
no automatic tiling loop against public Overpass. Existing partial extents are not unioned
into a claimed complete city. A proper bulk source/export adapter and measured incremental
parsers/group activation must precede larger-scale preparation.

Future U-03 can wrap create/status/events/cancel plus U-01 coverage/sufficiency using backend
authority, never forwarding model-controlled credentials, URLs or budgets. Operator smoke
permission is not permission for a continuously operating agent. Public guest quotas,
owner subscriptions, sustained source approval, durable retention operations and combined
live inference stress remain separate follow-ups. U-03 is not started.
