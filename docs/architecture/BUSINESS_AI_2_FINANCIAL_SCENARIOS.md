# BA2/U-05 · Scenario assumptions and universal financial scenarios

31.10.2026. Base: merged PR35/main `dd8503455b2c46c8387cd6411fa0f0276983b6a7`.
Branch `codex/U-05-universal-financial-scenarios`. Real Qwen proposals, review,
three scenarios, persistence and Chromium validation now pass. Final delivery/CI is
recorded in HANDOFF and the PR. U-06 is not started.

CI dependency maintenance: dev-only pypdf6.21.2→6.21.4 fixes seven advisories;
production Python requirements are unchanged. The existing frontend toolchain's
[minimatch advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249) requires11.0.1.
`package.json` pins that engine for all consumers. Redocly1.34.22 still expects a
callable CommonJS export: `tools/patch-redocly-minimatch.cjs` adapts only that import
to the public named export during npm ci, checks the exact version/source, and
tests resolver header matching without network. It is idempotent and fails closed
if upstream changes; Docker executes the same script. Actual generated API types
are byte-identical. Remove this temporary adapter once openapi-typescript supports
a modern Redocly; do not disable audits or force an incompatible Redocly upgrade.

## Architecture and compatibility

`ProfileV2 → reviewed FinancialDefinition → input resolution/review → Decimal ledger
→ input-driven scenarios → validation → owner-bound versioned snapshot`.

- Reuse U-04's industry classification and confirmed profile, guest authorization,
  assistant consent, conversation row lock and config SHA. No second classifier.
- `app/finance/v2/registry.py`: three closed adapter definitions, explicit units,
  domains, capacity rules and limitations. No user/model formulas or evaluation.
- `engine.py`: industry-specific volume/period adapters feed one common ledger.
  Reuse v1 `money`/HALF_UP and canonical encoding, `InputSource` and `DataOrigin`.
  The adapters do not pretend orders, students and coffee sales are interchangeable.
- `service.py`: workspace, input CAS, command receipts/review/history and append-only
  snapshots. `llm.py`: one structured exploratory proposal through existing H-03.
- Legacy `app/finance/engine.py`, strict v1 DTOs and report generator are untouched.
  The existing coffee route remains v1. There is no automatic v2→coffee fallback.
- U-04 auto/school/generic configs advance to `u05-v1`; coffee stays `u04-v1`.
  Old config hashes require review again. Financial definitions have their own
  version/hash and are selected by a backend capability, never a model-supplied tool.

## Financial definitions, periods and limits

All money is RUB; inputs are decimal strings or exact integers, never binary floats
or booleans. General scalar cap1e12, reviewed per-driver caps are usually lower.
Counts requiring whole units are explicitly validated. Budget is profile context,
not monthly revenue or proof of adequate capital. Missing values are absent, not0.

### Auto repair

Drivers: posts, working days/month, maximum orders/post/day at full utilization,
utilization0…1, revenue/order including parts, materials/order, variable labor/order,
monthly rent/fixed payroll/utilities/marketing/other costs. Variable and fixed labor
must represent disjoint costs; parts are not added as extra revenue a second time.

```
capacity = posts × days × maximum_orders_per_post_day
orders = capacity × utilization
revenue = orders × revenue_per_order
variable = orders × (materials_per_order + variable_labor_per_order)
fixed = rent + fixed_payroll + utilities + marketing + other_fixed
operating_result = revenue - variable - fixed
```

Utilization is applied once. The finite throughput input is a reviewed scenario
constraint, not measured Moscow demand, road accessibility or a service-time study.

### Online school

Paying students, student capacity, price/student/payment, variable/student/payment,
commission ratio, fixed monthly teachers/platform/marketing/other costs.
`billing_model` is explicitly selected; free-text U-04 payment labels are not silently
converted. Planned U-04 students are not automatically treated as paying students.

| Billing | Revenue | Fixed expenses | Period |
|---|---|---|---|
| `monthly` | paying_students × monthly_price | monthly sum | one chosen month |
| `subscription` | paying_students × monthly_subscription | monthly sum | one chosen month; no assumed renewals |
| `course` | cohort_students × whole_course_price **once** | monthly sum × course_months | one cohort over the complete course |

Variable costs = students × variable/student/payment + revenue × commission ratio.
Students cannot exceed capacity in any scenario. Course duration1…36 whole months.
Changing billing basis invalidates all payment-period confirmations. No invented
churn, CAC, retention, registered→paying conversion or recurring course revenue.

### Generic

One explicitly defined homogeneous sale/service unit per month, volume, unit price,
variable/unit, and the same separate monthly fixed-cost buckets. Revenue=volume×price.
Different revenue streams with different units/margins are **not** silently averaged;
this limited adapter requires one compatible unit or returns missing/unsupported
inputs. Capacity is unknown, not infinite proven capacity. No industry substitution.

## Input resolver, provenance and assumptions

`FinancialDocument`: profile revision/config SHA, financial version/SHA, input revision,
billing basis and bounded entries. Each entry has base/low/high, unit, InputSource,
epistemic state, review, method, basis, revision and creation time. Qwen entries also
record model and prompt revision. Snapshots link entries to the owner/profile/scenario.

Exact compatible confirmed profile drivers can be reused: auto posts/days/utilization/
average order/rent/payroll; school price/teachers/marketing. Planned orders are not
maximum throughput, monthly materials are not materials/order, and planned students
are not paying students. Incompatible facts stay in ProfileV2; financial input is
requested separately. No silent unit conversion, fill-with-zero or synthetic default.

U-01's actual source audit still has no implemented economic-rent/payroll/demand
adapter: licensed/GHSL are placeholders; OSM POI is not an economic measurement.
U-02/U-03 network/import permissions are unchanged. This resolver uses available
compatible confirmed user inputs; it does not pretend missing external facts exist.
No network access is needed for manual entry or recalculation.

| Value | Origin / epistemic | Review |
|---|---|---|
| User input | user_input / user_provided | proposed → confirmed/rejected |
| User scenario / Qwen hypothesis | synthetic / assumed | proposed → confirmed/rejected |
| Calculated metrics | modelled / derived, formula + input paths | immutable input snapshot |
| Unknown | absent entry | listed in missing requirements |

Public update DTOs cannot submit source attestations, observed status, URLs or credentials.
Confirming a hypothesis never changes synthetic/assumed. An explicit user correction
creates a new revision; the previous source/value remains in bounded action history
and existing snapshots. Financial output includes `contains_assumptions`, formulas
and `metric_inputs` linking derived values to entries with their original provenance.

## Structured Qwen proposal

Explicit user action requests **at most8** currently absent/rejected reviewed drivers;
existing proposed/confirmed entries cannot be replaced. More missing fields require
another explicit request or manual input; there is no automatic agent loop.
`AssumptionProposal={model,assumptions:[parameter,base,low,high,unit,basis,epistemic,source]}`.

- Existing local model/transport, one H-03 slot, one attempt, deterministic sampling.
  Context4096 by existing settings; output budget1536; bounded preflight/context check.
- Decimal-string schema and reviewed parameter IDs. Source is the literal
  `exploratory_no_market_evidence`; no tools/formulas/source claims are accepted.
- Backend verifies model/IDs/duplicates/units/ranges/domains/context-fixed values,
  known capacity constraints and unsupported statistical/source claims.
- Numerical validity does not establish economic realism. An empty proposal is allowed;
  ask the user instead of inventing a fact. No repair by automatic fake templates.
- Queue/inference runs with no DB connection. Publication rechecks ownership,
  profile/input CAS, consent revision, receipt state and deadline.
- Errors keep their safe code, leave inputs unchanged and permit manual operation.
  A repeated request ID never invokes Qwen again; failed/interrupted calls require a
  new explicit request. A late answer cannot overwrite a subsequent edit.

## Scenarios, rounding, break-even and sensitivity

`conservative/base/optimistic` use confirmed low/base/high drivers. Conservative takes
low revenue/volume and high costs; optimistic reverses them. Physical context stays
fixed and cannot conceal a range. This is not profit×0.5/1.5 or a probability claim.

All arithmetic uses local Decimal precision64 / HALF_UP, independent of ambient context.
Revenue, variable and fixed costs round to kopecks before subtraction. Unit contribution
retains exact Decimal precision for break-even, not a rounded display margin.

Break-even units=ceil(fixed/exact contribution per unit). Nonpositive contribution
returns `nonpositive_margin` with no invented number; exceeding known capacity returns
`above_capacity`. No divide-by-zero. Zero sales yield no safety-margin ratio.
Generic capacity remains unknown. Periods are month or complete course cohort.
Negative unit margin can reverse scenario ordering as volume rises; a structured
warning and visible explanation preserve the computed loss instead of manufacturing
an optimistic profit.

Sensitivity perturbs one eligible economic driver ±10%, holding all other inputs fixed;
whole student counts round HALF_UP and domain/capacity failures return `outside_domain`.
These are controlled probes, not distributions. `what-if` accepts explicit temporary
updates, confirms only those for the preview, and does not persist inputs or results.
Saving them is a separate action and requires review before the next saved calculation.
No Monte Carlo, tax accounting, EBITDA/net-profit claims, CAPEX schedule, ROI or runway.

## Versioned API and storage

All endpoints below require the existing conversation token and assistant consent.
Prefix `/api/v2/conversations/{id}/financial-scenarios`:

| Method / suffix | Operation |
|---|---|
| GET root | configuration, current input version, missing/review, latest current result, proposal status |
| PATCH root | explicit user updates / billing basis / reset after changed profile |
| POST `/propose` | bounded Qwen exploratory proposal |
| POST `/review` | explicit confirm/reject parameter IDs |
| POST `/calculate` | deterministic three-scenario or structured partial result |
| POST `/what-if` | non-persisted temporary calculation |
| GET `/results/{uuid}` | owner-authorized historical snapshot |

Commands carry `request_id`, `expected_profile_revision`, `expected_input_revision`.
PATCH adds typed updates and optional billing/reset; review carries disjoint confirm/
reject lists. No URL/SQL/path/formula inputs. Decimal responses remain strings.
Errors distinguish profile/input conflict, review/period/unit/domain/capacity problems,
forbidden source claims, disabled feature, quotas and model availability. Invalid owner
is404; missing token401; withdrawn consent403. Raw SQL/LLM payloads/secrets are not logged.

Migration0012 adds `financial_workspaces`, `financial_actions`, `financial_results`.
All rows are owner-scoped FK to conversations; JSON size checks64/64/192KiB, owner/time
indexes, composite receipt PK and owner/fingerprint uniqueness. No old financial rows,
report snapshots or volumes are migrated/rewritten. Results are append-only through
the application API; database administrators remain trusted. No user-data downgrade.

Financial input CAS is separate from profile CAS, under the **same conversation row
lock**, and always bound to the current confirmed ProfileV2/config. Profile edits
invalidate the current financial result. Reset is explicit and does not transfer
incompatible assumptions. Historic snapshots remain readable with ownership/consent.
Publication uses a fresh guarded transaction after computation/inference. Action IDs
persist before model dispatch;180s deadlines fence late publication and interrupted
actions are not automatically replayed. No second queue or worker infrastructure.

Stock limits:100actions/owner,2000global;20results/owner,200global, checked under a
short global PostgreSQL stock lock. Limits stop writes without deleting old data.
H-02 body/structure/rate limits apply; inference uses H-03 rather than analytical slots.
The entire city or a geospatial graph is never loaded for financial calculations.

## Frontend, restoration and Vi

Existing U-04 server stages select the supported financial capability. School/generic
do not acquire a mandatory map; auto finance is independent of unsupported vehicle ranking.
The coffee Finance/bank/report route is retained. No landing/motion redesign.

Parameters are progressively disclosed, units visible, Qwen/user/scenario provenance
and proposed/confirmed/rejected states distinguished. Selecting checkboxes and pressing
Use is explicit review. Dirty drafts hide the previous output; previews are labelled
unsaved. Saving inputs invalidates the old current result. Reload reads server state,
not a local completion flag. Conflict/consent errors clear stale output and offer refresh.
Three scenario KPIs, break-even, drivers, sensitivity and limitations are available.
The downloaded v2 JSON is the actual saved structured scenario snapshot; no replacement
PDF, market research claim or fake banking approval is produced. Existing Vi states
reflect waiting/error/calculation completion, including negative financial results.

## Explicit artificial arithmetic examples

These are independently specified **test scenarios**, not observations of Moscow/Kazan.

- Auto:4posts×25days×2maximum orders=200capacity; utilization.5/.75/1 →100/150/200orders.
  Price10000, materials3000/order, labor1000/order; rent100000 + payroll200000 + utilities
  20000 + marketing30000 + other50000 =400000fixed. Revenue1/1.5/2million;
  operating result200000/500000/800000. Break-even67orders within capacity.
- School:20paying students×10000=200000revenue; variable1000/student plus5%commission
  =30000; teachers60000/platform10000/marketing30000/other50000=150000fixed/month.
  Monthly/subscription result20000 for one month. One3month course:450000fixed,
  result−280000; break-even53students exceeds capacity30. Teachers70000/month yields
  −310000 for the course in non-persisted what-if.
- Generic:100units/month×2000, variable500/unit, fixed50000 →100000operating result;
 34units break-even; capacity unknown.
- Legacy coffee full control fixture: check300,100sales/day,30days,.35variable ratio,
  rent80000/payroll180000/utilities20000/other20000 →900000revenue,315000variable,
  300000fixed,285000operating result. Existing full startup/scenario fixture is retained
  in `tests/test_finance.py`; this is not a test of just one isolated final number.

## Verification and local operation

### Completion on the recovered runtime · 31 October

No recovery worktree changes are included in U-05. The existing model/server is
reused read-only for configuration, with inference requests only: Ollama**0.40.11**,
`qwen3:4b-instruct-2507-q4_K_M`, manifest
`0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
The server has no host11434 listener: QA connects through the existing Docker network
to `http://business-ai-recovered-ollama-1:11434`. No model pull/new LLM/queue/tunnel.
The recovered DB remains0011 and its Compose project/volumes/config are untouched.

`business-ai-u05-final` owns a NEW PostgreSQL/PostGIS database/volume and8015/5185
loopback ports. API/test containers join the model network; their PGHOST is the
unique **u05-finance-db** alias on their own network, never the ambiguous shared `db`.
Migration0012 is applied only there or in temporary test databases.

The first recovered live trial is retained in `live-qwen-recovered.json`:
auto hypotheses had100000working days/utilization2.0; school exceeded capacity.
Both were rejected422 without publishing values. Generic completed successfully.
These are real model failures, not transport failures or mock successes.

Prompt/schema `qwen-assumptions-u05-v2` now puts parameter/unit before the numeric
values and provides a per-parameter anyOf schema: exact IDs/units, decimal-string
domain patterns, integer domains and confirmed school-capacity bound. Fixed-context
ranges are explained explicitly. Backend validation still independently rejects
range order/context/capacity/source claims. No generated value is automatically
repaired, confirmed or widened into an invented interval.

Final live API matrix (`live-qwen-final.json`): all3models propose/review/calculate
successfully,32.727/19.917/16.229s; replay added0model calls in each case.
Auto/generic returned point ranges in this trial, so their three outputs coincide.
This is an honest consequence of identical inputs, not profit multiplication.
Point ranges may be edited by the user; hypothesis validity is not market realism.

Real Chromium (`live-browser/evidence.json`): actual U-04 Qwen classification and
4financial hypotheses,24.082s proposal; unreviewed calculation remains partial;
tuition explicitly rejected then corrected to6500/6000/7500RUB/student/payment;
3other Qwen assumptions confirmed while retaining synthetic/assumed origin.
Three saved outcomes **-630000/-25000/502500RUB**, reload and JSON pass;
1440/768/390screenshots, page/console errors0, geo/coffee requests0.
Separate real manual-school test checks full-course periods, unsaved what-if and
reload; real legacy coffee checks local Qwen→PostGIS→v1finance→bank→PDF/JSON.

Validation:49finance unit tests including independent Fraction oracle for all
adapters/month/cohort periods;172PostGIS integration tests, including a populated
0011→0012/repeat/check and byte-identical legacy files;49mock Chromium tests,
3separate real browser scenarios. Sets overlap with full pytest/prek and are not
summed as unique tests. Seven hooks passed; final commit/CI state is in the PR.
Actual v1 OpenAPI36paths/126recursive schemas remains deep-equal to main.

Current Linux live-harness Python peak RSS116867072bytes excludes the Ollama server,
PostgreSQL, native GPU allocations and full machine. Twenty pure calculations/model:
mean0.580/0.654/0.722ms, max3.325ms. HTTP/TestClient calculation48…55ms includes DB
and publication. Host GPU snapshot2348MiB/4096MiB includes desktop and the shared
model; it is not an isolated peak. No whole-city/throughput/SLA claim.

Tested local commands (private QA env/overlay contain credentials, never Git):

```powershell
$qa = Join-Path $env:USERPROFILE '.cache/business-ai/u05-final'
$compose = @('compose','--env-file',"$qa/qa.env",'-p','business-ai-u05-final',
  '-f','compose.yaml','-f',"$qa/qa.yaml")
docker @compose up -d --wait db api web
docker @compose run --rm --no-deps -T -e LLM_PROVIDER=ollama `
  -v "${PWD}/docs/qa/u-05:/evidence" db-tests /app/.venv/bin/python `
  -m tests.integration.u05_live --output /evidence/live-qwen-final.json
$env:BA010_REAL='1'; $env:BA_U05_QWEN_REAL='1'
$env:BA_TEST_WEB_URL='http://127.0.0.1:5185'
npm --prefix apps/web run test:e2e -- --grep 'U-05 real Qwen school'
# Stop this QA project only; do not operate on business-ai-recovered.
docker @compose stop
```

For a different installation, create its own isolated QA env/DB and use the actual
existing model endpoint. Do not copy this machine's network assumption blindly.
Build current API/db-tests images before the harness; enable both industry/finance
flags in the private QA env. No recovery backup/installation files are required by
the feature PR. CPU-only model performance and general economic plausibility remain
unverified. CI intentionally uses scripted fixtures, never downloads model weights.

### Historical evidence and diagnosis · 30 October (superseded)

Evidence at that checkpoint: `docs/qa/u-05/`. Initial live harness tried the configured
Ollama endpoint; all3proposal calls returned503 `llm_unavailable`, with no hypotheses
or financial live success. Windows standard paths and both Ubuntu WSL distributions
had no accessible Ollama binary/service/model. Existing endpoint/location requested
from owner. **Live model validity, rejection proportion and successful complete Qwen
scenario are unverified; U-05 cannot be accepted Completed on these tests alone.**

Final finance unit36PASS; targeted PostGIS66PASS (finance/industry/agent/registry/geo),
generic/cache2PASS; populated migrations/reports41PASS (sets overlap). Full Chromium
49PASS; real built Compose manual school1PASS5.2s, no mocks/Ollama, page/console errors0,
review/three distinct scenarios/unsaved what-if/reload/JSON and1440/768/390 screenshots.
First real browser trial collected checkboxes before the save response rendered;
explicitly waiting for the review UI fixed this test synchronization error.
Actual deep v1 OpenAPI comparison36paths/126recursive schemas unchanged.
Full API pytest538PASS/168SKIP/102deselected before2final unit additions; initial prek
exit1 was concurrent QA/docs writes, not failing tests. Final hooks/CI in delivery report.
Final standalone7prek hooks passed. Owner-requested Docker lookup found no existing
Ollama containers, volumes, binary or model in the4available images; both contexts
refer to the same daemon. Automatic approval rejected restoring the same-version
local container/model ("blocked by policy", no detailed reason). No download/start
occurred; explicit creation authorization has been requested.

### Environment-first follow-up requested by owner

The owner subsequently **stopped all recreation/download** and requested diagnosis.
That instruction supersedes the earlier creation question. No new Ollama, model,
model volume, public listener, firewall rule or tunnel was installed/created.
The historical U-03/U-04 successes are not disputed or re-labelled as mocks.
Current reproducible observations are in
[`ollama-environment-diagnostic.json`](../qa/u-05/ollama-environment-diagnostic.json).

| Check | Observed now |
|---|---|
| Execution | Native Windows11 x64 / PowerShell7.6.5, Acer Nitro AN517-54; not a WSL/container process |
| Remote sandbox | No remote Linux/SSH execution evidence; CODEX_CI=1 is not sufficient evidence of a remote host |
| Native backend factory | OllamaLLM, `http://127.0.0.1:11434`, exact configured Qwen name |
| Compose backend | `http://host.docker.internal:11434`; `.env.example`/Compose agree |
| Current API process | None found; diagnostic process and actual API image were checked separately |
| Native HTTP | `/api/version` and `/api/tags` fail on IPv4 loopback; no expected listener |
| API-image HTTP | Host name resolves; host IPv4 TCP refuses connection, IPv6 has no route |
| Binary / model files | Not located in accessible current storage/images/WSL locations; not proof of permanent absence |
| Current version | Unknown until HTTP/installed CLI responds;0.40.8 is historical evidence only |

This identifies a serving-endpoint availability problem **before** Qwen generation.
It does not establish why the previous installation/storage changed or where it is
currently located. The IPv6 diagnostic error does not justify changing network
security; the independent IPv4 no-listener/refusal is recorded separately.

Run these read-only checks in the owner's ordinary Windows terminal; they do not
install, download, expose or reconfigure anything:

```powershell
Get-Command ollama.exe -All -ErrorAction SilentlyContinue | Select-Object Source
Get-Process *ollama* -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path
Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue
Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 5
(Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 5).models |
  Select-Object name,digest,size
[Environment]::GetEnvironmentVariable('OLLAMA_MODELS','User')
[Environment]::GetEnvironmentVariable('OLLAMA_MODELS','Machine')
```

If an existing Windows executable is resolved and no server is running, start that
executable, retaining its existing environment/model storage. Do not change
OLLAMA_HOST/OLLAMA_MODELS or pull a replacement:

```powershell
$existingOllama = Get-Command ollama.exe -ErrorAction SilentlyContinue
$existingBind = [Environment]::GetEnvironmentVariable('OLLAMA_HOST')
if ($existingBind -and $existingBind -notmatch '^(https?://)?(127\.0\.0\.1|localhost|\[::1\])(:\d+)?/?$') {
  throw 'Existing bind is not explicitly loopback: inspect it; do not expose or reconfigure automatically.'
}
if ($existingOllama) {
  Start-Process -FilePath $existingOllama.Source -ArgumentList 'serve' -WindowStyle Hidden
} else {
  Write-Output 'Existing executable not resolved: locate its original path; do not reinstall or pull.'
}
```

For WSL inspect the actual existing distribution/service first (both distributions
below exist on the checked host). Only a loaded existing service may be started;
`not-found` means stop diagnosis there, not create a new unit or install a model:

```powershell
wsl --list --verbose
wsl -d Ubuntu-24.04 -- bash -lc 'command -v ollama; systemctl show ollama -p LoadState -p ActiveState -p FragmentPath; curl --noproxy "*" -fsS --max-time 5 http://127.0.0.1:11434/api/version'
wsl -d Ubuntu -- bash -lc 'command -v ollama; systemctl show ollama -p LoadState -p ActiveState -p FragmentPath; curl --noproxy "*" -fsS --max-time 5 http://127.0.0.1:11434/api/version'
# If the selected distribution reports LoadState=loaded:
wsl -d Ubuntu-24.04 -- sudo systemctl start ollama
```

For an existing Docker setup inspect the **original** container and mounts/context;
do not create a replacement container/volume or run Compose against working PGDATA:

```powershell
docker context ls
docker ps -a --format '{{.Names}} {{.Image}} {{.Status}} {{.Ports}}'
docker volume ls
# Substitute the existing container name only after it is found:
# docker inspect <existing-name> --format '{{json .HostConfig.PortBindings}} {{json .Mounts}}'
# docker start <existing-name>  # only if the existing config does not expose Ollama publicly
# docker exec <existing-name> ollama list
# docker exec <existing-api-name> python -c "import os,urllib.request; u=os.environ.get('OLLAMA_BASE_URL','http://127.0.0.1:11434'); print(urllib.request.urlopen(u+'/api/version',timeout=5).read().decode())"
```

The last command checks from the API container, where localhost means that container,
not Windows. If the old model does not appear after restoring its original server,
inspect its original OLLAMA_MODELS/mount before any download. Once `/api/tags` lists
the exact model, a short real probe can run without pulling or changing names:

```powershell
$wantedModel = 'qwen3:4b-instruct-2507-q4_K_M'
$knownModels = (Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 5).models.name
if ($wantedModel -notin $knownModels) { throw 'Existing target model not visible; inspect original storage, do not pull.' }
$probe = @{ model=$wantedModel; stream=$false; think=$false;
  messages=@(@{role='user';content='Ответь одним словом: готов'});
  options=@{temperature=0;num_ctx=4096;num_predict=32} } | ConvertTo-Json -Depth 6
Invoke-RestMethod http://127.0.0.1:11434/api/chat -Method Post -ContentType 'application/json' -Body $probe -TimeoutSec 180
```

Exact read-only repro using the **already built** U-05 API image when no API container
is running (no image pull, published ports, GPU/model process or persistent volume):

```powershell
$check = 'import urllib.request; from app.adapters.llm import get_llm; b=get_llm(); print(b.settings.base_url); h=urllib.request.build_opener(urllib.request.ProxyHandler({})); print(h.open(b.settings.base_url+"/api/version",timeout=5).read().decode())'
docker run --rm --pull=never --read-only --cap-drop ALL --security-opt no-new-privileges `
  -e LLM_PROVIDER=ollama -e OLLAMA_BASE_URL=http://host.docker.internal:11434 `
  --entrypoint python business-ai-u05-api:latest -c $check
```

Then run the existing U-05 live harness against an isolated PG server with the
effective reachable base URL, preserving all prior failed evidence. While the
original runtime cannot be reached, **live Qwen validation stays BLOCKED**; native
manual/explicitly scripted integration tests are not substitutes for that gate.
CLI/storage reference: [official CLI](https://github.com/ollama/ollama/blob/main/docs/cli.mdx),
[model storage](https://github.com/ollama/ollama/blob/main/envconfig/config.go),
[official Docker instructions](https://github.com/ollama/ollama/blob/main/docs/docker.mdx).
Mock screenshots are explicitly named `financial-mock-*`; actual browser artifacts,
when successful, are named `real-school-*`. Failed trials are retained.

Measured CPU-only synthetic fixtures:100calculations/model, median auto0.649ms,
school0.415ms/generic0.377ms; max1.587ms. Separate tracemalloc single-calculation peaks
42696/37720/36856bytes exclude interpreter/native allocations/DB/OS/Ollama. The real
browser-triggered calculation236ms includes click/HTTP/DB/result publication; it is
not pure Python time. GPU/full system peak and successful model inference remain
unmeasured. No SLA or general market prediction claim follows from these samples.

Enable only after additive upgrade: `BA_INDUSTRY_ENABLED=1`, `BA_FINANCE_V2_ENABLED=1`.
Both default0; `BA_AGENT_ENABLED` is independent. With finance disabled U-04 retains
its existing partial route. Agent/network permissions are not expanded by either flag.
One API worker remains required by H-03. Never run a new DB image on an old working volume.

```powershell
uv run --locked --project apps/api pytest apps/api/tests/test_finance_v2.py apps/api/tests/test_finance.py -q
npm --prefix apps/web run typecheck
npm --prefix apps/web run lint
npm --prefix apps/web run test -- --run src/FinancialScenarios.test.tsx
npm --prefix apps/web run test:e2e -- --grep 'U-05'
```

For PostGIS use PG* for an isolated disposable QA server, `BA_RUN_DB_TESTS=1`, and the
existing Windows Selector event-loop test configuration (not a Proactor workaround
that hides failures). Run integration financial/industry/agent/reports/populated/migrations.
Native live harness: `PYTHONPATH=apps/api`, configured existing Ollama and isolated PG*,
`uv run --locked --project apps/api python -m tests.integration.u05_live --output docs/qa/u-05/live-qwen.json`.
Actual manual browser: isolated built Compose, BA010_REAL=1, BA_U05_REAL=1,
BA_TEST_WEB_URL to its web port; run Chromium grep `U-05 real`. This test does not use Qwen.

## U-06 boundary

Available states: missing/review-required/confirmed inputs; durable proposal request
UUID/time/running/completed/failed/interrupted; calculated/partial snapshot; stale
profile/input conflict. These can drive existing Vi states. There is no financial
event cursor or fake percent, telescope animation, full new PDF integration, autonomous
external finance lookup or U-06 work in this PR. Resolve the live model blocker before
acceptance and before drawing conclusions about model proposal quality.
