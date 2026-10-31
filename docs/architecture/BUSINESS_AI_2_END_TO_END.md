# Business AI 2.0 · U-06 integration and release validation

31.10.2026. Base main8fdeda3d8f59bbc664e01a404f15c87d6f978dec (PR36 merged).
Branch codex/U-06-end-to-end-vi-integration. Live A/B/C/D and resilience checks
passed on an isolated local stack. Final commit and exact-HEAD CI belong in the
delivery report/PR; this does not close the separate release security baseline.

## Integration inventory

| Component | Actual authority/storage | U-06 integration |
| --- | --- | --- |
| U04 classification | IndustryLLM structured proposal/H03; IndustryProfiles validates evidence/fields | Same dialogue and profile review; no second classifier |
| Applicable stages | industry.engine.plan, confirmed profile revision/config | Conditional finance/no-map/bank/result; frontend does not grant server permissions |
| U01 coverage | PostGIS dataset metadata, local/external eligibility separately | Existing U04 plan assessment; no city-wide claim from one object/tile |
| U02 acquisition | PostgreSQL jobs, events/cursor, leases/fences, separate bounded worker | Operator-only unchanged; no guest downloader or new imports |
| U03 tools | Persisted owner-scoped runs, bounded gateway and H03 | Existing opt-in API; not automatically invoked from every dialogue |
| U05 finance | Workspace, action receipts, immutable results | Read running/interrupted/failed/completed/cancelled, bounded polling, explicit cancellation |
| Legacy MVP | Existing geo/ranking/finance/bank/consent/lead/report services | Coffee path stays intact, no conversion from unknown industries |
| Frontend state | U04 revision/stages + U05 input revision/result + guest token | Reload rereads server; browser history only remembers an eligible screen |
| Vi | Original ViEmotion/ViMotion/assets | Real request/action state; neutral losses, uncertain partial, explicit cancellation |
| Previously lost state | Local U05 thinking; no next/result stage; old U04 partial text | Financial action restore and integrated read serializer, no second execution system |

## Contracts and boundaries

- Additive FinancialView.operation reflects an existing financial_actions receipt:
  request_id, kind, state, profile/input revisions, creation/deadline and safe code.
  It is a status snapshot, not an invented global event cursor. U02 retains its
  monotonic events; U03 retains its run receipts. No fictitious percentages.
- POST financial-scenarios/cancel uses the target action request_id and current
  expected profile/input revisions. Same owner/consent checks and row locking;
  repeated cancellation is harmless. State fence prevents late publication, async
  watcher cancels inference. A connection loss becomes interrupted, never success.
- UI polls only while an actual proposal/running receipt exists:2…5s, at most45
  reads per activation; abort on unmount, no automatic POST/retry. Network/auth errors
  stop false-success presentation. Model failures allow explicit manual input.
- GET /api/v2/conversations/{id}/analysis-result returns analysis-result-v2 under
  existing owner/assistant consent, using a short coherent profile row lock.
  financial contains the unchanged current U05 snapshot or null. UI and JSON use
  this same response. assessed_at applies to live applicability/coverage, NOT to
  the measurement date of source data or to the immutable snapshot timestamp.
- Stale inputs/profile/config hide the previous financial snapshot from current
  results; historical owner-bound /financial-scenarios/results/{id} is unchanged.
- v2 bank-products/matches reuses the existing matcher. Confirmation projection
  applies only to informational relevance; persisted v1 confirmation stays unchanged.
  No loan approval or external transfer. Mock leads for new industries remain
  unsupported; legacy coffee retains separate consents and mock receipts.
- No new schema migration. No bank/geo/financial algorithm or immutable v1 report
  renderer is changed. New-industry export is JSON; no claim of v2 PDF support.

## Observed live results

Existing Ollama0.40.11, exact qwen3:4b-instruct-2507-q4_K_M, manifest digest
0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0. No model
download, second server, public Ollama listener or cloud inference. The existing
H03 queue is unchanged. All financial computations still run in deterministic Python.

| Scenario | Actual result | Wall time / evidence |
| --- | --- | --- |
| A coffee/Kazan/2M | Real Qwen,5PostGIS zones, v1 finance285000→275000 after rent edit,2demo bank matches, PDF/JSON |38.7s initial warm rehearsal; final replay≈2.1min (first turn91.781s); coffee/live-evidence.json |
| B auto/Moscow/8M/4posts | Real classification and hypotheses, explicit review,3scenarios, informational bank, current JSON; geography unsupported/missing |37.423s; classification8.029s, proposal23.299s; auto_repair/evidence.json |
| C online school | Real classification/hypotheses, reject/correct tuition6500(6000…7500), review,3scenarios/sensitivity, bank, reload and JSON; no map request |34.783s; classification8.507s, proposal20.786s; online_school/evidence.json |
| D unusual service | Real generic classification, preserved idea, manually entered/reviewed homogeneous-unit finance, honest partial overall result |11.449s; classification6.779s; generic/evidence.json |
| Resilience | Cancel acknowledgement158ms, in-flight reload→interrupted61ms, no model values published; explicit manual recovery, offline/online same snapshot, stale hidden, foreign owner404, revoke403 |10.1s; resilience/evidence.json |
| Optional U03 | Real Qwen called check_data_coverage, succeeded as a tool execution; next_step=data_unavailable, NOT a completed Moscow analysis |10.513s; agent-readonly.json |

Paths above are relative to docs/qa/u-06. Browser fixtures are explicit synthetic
user/scenario inputs, not market observations. Qwen values remain assumed/synthetic
after confirmation. Generic uses no coffee coefficients. Main scenarios have zero
page/console errors; controlled offline/revoke errors in the resilience test are
listed separately, not suppressed or reported as zero. No Playwright network mocks
were used in these live scenarios. Screenshots1440/768/390 are actual app captures.

The coffee regression exercises the supported legacy mode with industry flag0;
B/C/D/resilience use industry/finance flags1. Coffee's U04 projection is separately
covered by existing unit/PostGIS/mock route tests. Agent flag1 is confined to the
isolated read-only TestClient probe; the ordinary QA API keeps agent0. No worker or
external fetch was started by that probe; its tiny geo fixture is labelled synthetic.

### Data and persistence

The new QA database uses schema0012. No U06 migration is needed. Actual cached
OSM data were imported with existing checksum-validating CLI tools:23852POI,
8boundaries (22Oct snapshot),41640walking edges (24Oct snapshot). POI bbox
49.05,55.70…49.25,55.85 and walking bbox49.08,55.76…49.18,55.82 differ. These are
limited Kazan extents, not whole-city coverage. No Moscow import or new Overpass
request occurred. Source attribution/licence remains ©OpenStreetMap contributors,
ODbL-1.0. Download/import time is not a new measurement date.

The recovered project/DB/volumes were not migrated, recreated or modified. A distinct
QA project/network/volume and unique DB alias prevent resolving its database to
the recovered stack. No private backups, .env or owner records are in the PR.
Populated migration/report tests check historical v1 PDF/JSON byte preservation;
current result reads never update stored financial or legacy report snapshots.

Container recreation preserved counts/hashes of6financial results,1legacy report,
1geo dataset and1walking graph (persistence.json). The later coffee replay creates
a separate new report normally. No historical result was rewritten. Final assets:
initial JS232.07KB/gzip73.31KB; lazy BusinessFlow121.53KB/gzip33.01KB; MapLibre
still loads separately. No new runtime dependency or mascot asset.

### Measurements and limits

- Repeated business runs above used a warm/reused model. A separate native probe
  observed the model already unloaded naturally: cold79.789s (load78.559s), warm
  0.986s. No forced unload/config change. It used16prompt/9output tokens with a
  48token cap, so it is NOT a cold full-business-analysis benchmark or SLA.
-35one-second /proc/1/status + pg_stat_activity samples during live work:
  API high-water RSS98.668MiB, at most1other DB connection,0idle-in-transaction.
  The sampler uses autocommit and excludes itself. This excludes model/PostgreSQL
  RAM, native/GPU allocations and unobserved peaks. See runtime-measurements.json.
- Financial browser HTTP round trips151…163ms, reload903…920ms. Independent100run
  pure-engine probes on the exact saved inputs match the saved results; means
  auto0.723/school0.557/generic0.587ms, maxima1.469/1.017/1.291ms. Excludes DB/LLM.
- Shared restored Windows/WSL2/Docker machine, not an isolated performance lab;
  CPU/GPU peak attribution and physical iPhone/Safari were not tested. Chromium
  viewport tests do not certify all mobile browsers or accessibility compliance.
- Optional U03 process peak RSS122171392bytes belongs to that probe, not the API
  or model. Source acquisition/network remains disabled by policy for guests.

## Verification and reproducible commands

Local results:49mock Chromium PASS; finance/industry unit78PASS; corrected targeted
UI17PASS (these sets overlap with hooks). Full PostGIS initially174PASS/2failures
from old exact stage expectations; the expectations now include the independent
informational bank stage and still forbid fake geo/finance. Updated industry module12PASS. All7prek hooks, final Docker production build,
Alembic drift check and container-recreation persistence PASS. Final full CI results
are recorded on the exact PR HEAD. Expanded/property tests102PASS. Actual v1 OpenAPI:
36paths/126recursive schemas deep-equal to base main. Redacted Gitleaks8.30.1
directory scan and scanner scope/redaction fixtures PASS. Never sum overlapping
sets or label scripted model/geo fixtures as live acquisition.

```powershell
# From repo root, after normal locked dependency installation:
uv run --locked --project apps/api pytest apps/api/tests -m extended -q
npm --prefix apps/web run test:e2e  # mock suites, no live Qwen
npm --prefix apps/web run build
prek run --all-files              # all7mandatory hooks; also enforced on commit

# Private operator QA env/overlay must target NEW volumes/DB and the existing LLM.
# QA_DIR is an operator-selected private directory, not a repository file.
$compose = @('compose','--env-file',"$QA_DIR/qa.env",'-p','business-ai-u06',
  '-f','compose.yaml','-f',"$QA_DIR/qa.yaml")
docker @compose build api web migrate db-tests
docker @compose up -d --wait db api web
docker @compose run --rm --no-deps -T db-tests

$env:BA010_REAL='1'; $env:BA_U06_REAL='1'
$env:BA_TEST_WEB_URL='http://127.0.0.1:5186'
npm --prefix apps/web run test:e2e -- --grep 'U-06 real'
$env:BA_U06_RESILIENCE='1'
npm --prefix apps/web run test:e2e -- --grep 'U-06 resilience'
# Existing coffee real.spec.ts needs the isolated legacy-mode flag0 and cached OSM.
# Restore industry1 afterward. Never change the recovered installation for a test.
```

PostGIS tests run in Linux containers, the established supported configuration for
psycopg async behaviour. No Windows Proactor failure was masked. Acquisition tests
cover atomic claim, checkpoint restart/recovery, old-worker fencing and cancellation
using controlled fixtures and real PostGIS; no live network worker restart is claimed.

## Deliberate limitations / release handoff

- Guest workflow does not expose operator imports or auto-enable U03. Existing
  source permissions, SSRF transport, H03 and worker concurrency remain unchanged.
- Unknown methods/data stay partial. Completion means applicable arithmetic finished,
  not representative market coverage, profitability, loan approval or investment advice.
- Bank matching is a separate live informational operation, not an immutable bank
  decision embedded in the financial snapshot. Needs/matches may be requested again
  after reload; new-industry mock lead/PDF remain unsupported. Legacy paths remain.
- Current coverage is explicitly live assessed_at metadata. Historical financial
  inputs/formulas/results remain immutable; this is not an immutable market-history
  snapshot or a promise to reproduce future catalogue/source availability.
- The current guest contract has no expiry timer. Missing/invalid/foreign tokens and
  consent withdrawal are tested; an invented TTL/expiry implementation was not added.
- No new images, telescope rig, industries, financial formulas, queue or heavy service.
  No automatic merge, deployment into the recovered DB, or next initiative.
- Existing scoped image/dependency gates do not close the separately documented
  unfixed/unassessed native-image release baseline. Owner review is still required.
