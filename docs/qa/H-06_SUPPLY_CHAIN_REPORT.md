# H-06 · Dependency, license and secrets audit · 27.10.2026

Follow-up: [H-06-FU](H-06-FU_CONTAINER_REPORT.md) repeats image scans with a newer,
internally frozen DB and verifies an isolated encrypted PG17/PostGIS upgrade.
Tables below are historical H-06 evidence; do not overwrite/mix their advisory date.

**Audit/hardening result; not an accepted secure release baseline.** Legacy DB image
contains unresolved CRITICAL/HIGH findings and PostgreSQL17.5 needs a security update.
No owner-approved risk exceptions have been invented. H-01…H-06 cannot yet be called
fully closed for RC/pilot. This PR makes findings reproducible and adds scoped gates;
the image migration/native reachability decision is an explicit follow-up.

Branch `codex/H-06-supply-chain-security`, clean base6405a1a. PR24/ed8774d merged
and six checks verified before starting. Scope follows the4–6h H-06 card: controlled
baseline, targeted hardening, free scanners and CI. No product algorithms, schemas,
consent/ownership/CAS/idempotency, LLM orchestration or backup architecture changed.
Checkpoint: [H-06_CHECKPOINT](H-06_CHECKPOINT.md).

## Evidence and methods

- [43 Python lock entries /337 npm lock entries](H-06-dependencies.json): exact
  versions, sources/integrity, provided license-file hashes and verification status.
  Python entry count includes the project and conditional dependencies; Windows audit
  evaluated41 third-party distributions. npm has28 runtime entries; clean Windows
  install added287 packages (platform conditionals explain the difference).
- [Image advisory summary](H-06-advisories.json), [all package findings](H-06-advisories.csv),
  [deduplicated final union](H-06-summary.json). Before/after image labels remain explicit.
  A package occurrence is not a unique CVE or a proven exploit.
- pip-audit2.10.1, npm audit, Gitleaks8.30.1, Trivy0.76.1. Official release binary hashes
  verified before use. Trivy DBv2 UpdatedAt2026-10-27T01:25:30Z,
  DownloadedAt2026-10-27T05:53:26Z. Scans completed with a current advisory DB.
- pip-audit queried PyPI with package names/versions; npm queried the public npm
  registry. **No source, .env, prompts, reports, keys or user records uploaded.**
  Gitleaks and Trivy inspected local files/image archives; no Docker socket upload.
- Original runtime scan with pip-audit2.9.0 was0; the final full-set run uses2.10.1.
  This is not evidence of absolute safety or comprehensive native-library coverage.

## Inventory: substantial components

| Component | Actual version / identity | Source and fixation | License evidence / action |
|---|---|---|---|
| Python | Windows3.12.15, API3.12.16 | official python:3.12-slim digest12316deb… | PSF + base third parties; pin added |
| FastAPI / Pydantic |0.146.0 /2.14.1, core2.50.1 | PyPI uv.lock hashes | MIT, installed texts |
| SQLAlchemy / Alembic |2.1.5 /1.20.0 | PyPI lock | MIT, installed texts |
| Psycopg / binary |3.3.6 /3.3.6 | PyPI lock | LGPL-3.0-only; native/replacement/source obligations require review |
| libpq | Windows18.4, Linux18.6 | bundled psycopg binary, queried PQlibVersion | PostgreSQL/native third parties; pip-audit alone does not audit these libraries |
| ReportLab / Pillow |4.5.1 /13.0.0 | PyPI lock | provided BSD-style /MIT-CMU texts retained |
| httpx2/httpcore2 |2.14.0 | PyPI→official pydantic/httpx2 | BSD-3-Clause; no adapter replacement |
| React / react-dom |19.3.1 | npm lock SHA512 | MIT, shipped notices |
| MapLibre |6.15.0 | npm lock | BSD-3-Clause,28 runtime npm notices verified |
| TypeScript/Vite/Vitest/Playwright |5.9.3 /7.3.7 /4.1.12 /1.64.1 | npm lock | Apache2/MIT/MIT/Apache2; dev tools |
| Node |24.20.0 locally; node:24-alpine digest06d7adf3… for build | official base digest | Node MIT plus bundled notices |
| nginx |1.30.6, Alpine3.24.3 | stable-alpine digest47928bf6… | BSD-style + OS licenses; curl removed, Brotli patched |
| PostgreSQL/PostGIS |17.5/3.5.2, Debian11.11 | postgis/postgis digest01a6a70e… | PostgreSQL License /GPL2-or-later; **release blocker** |
| GEOS/PROJ/libxml |3.9.0/7.2.1/2.9.10 | DB image native packages | independent native licenses; old native stack requires follow-up |
| Ollama |0.40.8, Ubuntu24.04 | external container digest2b8eecdb… | source MIT; native/GPU image terms separate |
| Qwen |qwen3:4b-instruct-2507-q4_K_M,4.0B,GGUF | manifest0edcdef34593… | specific Apache2 license blob matched installed artifact |
| age |1.3.2 | existing H-04-FU SHA-pinned official binaries | BSD-3-Clause; backup code unchanged |
| uv / pip-audit / Gitleaks / Trivy |0.13.1/2.10.1/8.30.1/0.76.1 | official public sources, version pins/checksums | audit/build-only, not new application dependencies |
| GitHub Actions | checkoutv5, setup-nodev6, setup-uvv10.3.0 | all resolved to full40hex official commits | existing source versions, read-only permissions |

OpenCV, Python GDAL, Shapely, OSMnx and NetworkX are **not** project dependencies.
Geo operations use PostGIS; GDAL and other native components present in its image
must not be confused with a Python import. `httpx2-jsfetch1.0` is Emscripten-only,
uninstalled on supported Windows/Linux; its license text remains unverified.

## Vulnerabilities: counts and triage

Unique IDs within each final image (vendor severity; not additive across images):

| Image | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN |
|---|---:|---:|---:|---:|---:|
| API after |0|8|29|33|1|
| Web after |0|0|0|0|0|
| DB, unchanged |16|151|276|333|41|
| Ollama, unchanged |0|46|57|8|2|

Final union, highest reported severity per ID: **16 CRITICAL,174 HIGH,305 MEDIUM,
329 LOW,42 UNKNOWN**. These are image/native findings; Python and npm package audits
reported0. Manually reviewed PostgreSQL advisories below are separate and may be
missing from distribution scanners for PGDG packages. Full rows include package,
installed/fixed version, status and advisory URL. Empty fixed version means the
scanner did not identify a stable-distro fix, not that no upstream fix exists.

### Fixed within H-06

- **CVE-2026-92392**, curl/libcurl8.22.0-r0; Alpine fix8.23.0-r0. Current nginx
  application does not use the curl CLI. Removed curl and its unused automatic
  dependency closure, verified nginx/wget/proxy/assets/notices still work.
- **CVE-2026-111497**, Brotli decoder; patched brotli-libs to1.2.1-r0 from official
  Alpine3.24. APK signature and hardcoded SHA256 checked. It is not a floating apk upgrade.
- Runtime pip25.0.1 removed after dependency installation: **CVE-2025-8869,
  CVE-2026-13346, CVE-2026-3219, CVE-2026-6357, CVE-2026-8643** (MEDIUM),
  **CVE-2026-1703** (LOW). pip is not needed to serve the application. Build/test
  stages retain installation tooling; their trust boundary is not certified by this removal.
- Rescan: web3HIGH occurrences/2unique→0; API pip findings removed. An ID removed
  from one image can still exist in the old DB image; no global eradication claim.

### Open findings, not silently accepted

| Group | Actual relevance / evidence | Risk and action |
|---|---|---|
| API CVE-2026-76642,78408,78409,78410 (util-linux) | Local mount/nsenter/namespace conditions. No HTTP route exposes them; API runs as app with all capabilities dropped and no-new-privileges. Debian13 tracker lists no stable fix | P1 baseline review; candidate not-reached explanation, **not approved exception**; do not claim kernel-wide proof |
| API CVE-2025-69720 (ncurses) | Upstream describes infocmp CLI input, not every libtinfo call. No application invocation of infocmp found | P2 contextual risk, upstream stable fix/review pending |
| API CVE-2026-16742 /54369 /9538 | systemd-homed, ACL privileged symlink operations, Perl Archive::Tar respectively; no homed service or Perl archive pipeline in app | No demonstrated business-path reachability; P1/P2 review pending, not suppressed scanner rows |
| DB legacy native image | Debian11.11 EOSL=true;26CRITICAL/239HIGH package occurrences,16/151 unique. Raster/media/XML/Go utilities and old libraries need per-binary analysis | **P1 release blocker**. No attacker PoC against working DB. Do not mass-update/downgrade or switch distro within this PR |
| PostgreSQL17.5 itself | Official [PG17 security list](https://www.postgresql.org/support/security/17/): e.g. CVE-2026-6479 fixed17.10 (pre-auth SSL/GSS DoS), CVE-2026-2006 fixed17.8, CVE-2026-14664 fixed17.11 (authenticated server memory corruption) | Server version affected; business-path exploit not proven. DB port is not host-published, but network restriction does not remediate server bugs. Upgrade/recovery follow-up required |
| Ollama/native/Go image |50HIGH occurrences/46unique; loopback11434, no privileged mode/extra capabilities. Official model manifest pinned; no untrusted GGUF import tested | P1 before external release; application-specific/CUDA/native parser coverage incomplete. Keep local trusted-use restriction, plan tested image update |

Primary context sources: [Debian util-linux](https://security-tracker.debian.org/tracker/CVE-2026-76642),
[nsenter](https://security-tracker.debian.org/tracker/CVE-2026-78408),
[infocmp](https://security-tracker.debian.org/tracker/CVE-2025-69720),
[Perl Archive::Tar](https://security-tracker.debian.org/tracker/CVE-2026-9538).
Vendor HIGH alone does not establish remote exploitability; absence of a demonstrated
path does not establish safety. No scanner exception with owner approval exists yet.

## Secrets, files and build artifacts

- Gitleaks strict history:65 reachable commits, non-shallow, `--all --full-history`,0.
  Current tracked/untracked first-party files, actual build output, fixtures and
  `.env.example`:0. Actual .env files at root/API/web were absent; template password
  is a documented local placeholder, not an actual production credential.
- History config does not exclude paths. Directory-only config excludes installed
  .venv/node_modules/Git object storage, **not dist or first-party fixtures**.
  Initial broad directory scan found2 SQLAlchemy parameter-name false positives
  (`keyfunc`/`passive` source), manually verified; not real secrets or accepted leaks.
- Real Gitleaks self-test: clean fixture exit0, synthetic unusable PAT/age/DSN fixtures
  exit1 even with inline allow annotations, reports/stdout/stderr redacted. No genuine
  user credential generated/read. .gitleaksignore absent and prohibited by regression gate.
- Trivy secret scans of final API/web root filesystems:0. Build layers reviewed:
  no secret ARG/ENV, selective API COPY, context exclusions for env/keys/archives,
  frontend context excludes .npmrc. Deleted files are public APK/pip artifacts;
  no sensitive build input was provided. This is not forensic certification of every
  historical image layer or OCR of screenshots/PDFs.
- No real secret found requiring rotation. Host credential stores/private backup
  keys were not accessed. Raw secret reports and registry/tool error logs remain
  outside Git/CI artifacts; only safe summaries are published.

## Docker / CI / reproducibility

Official Python/Node/nginx/PostGIS references now have immutable digests. DB pin
records the known legacy identity; **pinning is not a security fix**. Python runtime
requirements now carry hashes and pip --require-hashes; test uv wheel hashes separately
pinned. Application package versions/uv.lock/npm lock did not change.
API/migration containers run nonroot with cap_drop ALL/no-new-privileges. nginx master,
Postgres init and external Ollama retain upstream root startup patterns; no new root
privileges/socket mounts/host DB ports added. Least-privilege DB roles and native-image
redesign require a follow-up; no ownership semantics changed here.

All Actions pinned, contents:read, persist-credentials:false; no pull_request_target,
privileged untrusted workflow or secrets in build args. New Supply chain job fails
on Python/npm findings or scan errors; Gitleaks covers history/current files and
positive/redaction self-test. No broad ignores, continue-on-error or uploaded reports.
**Image/native release risk is not gated away by this scoped green package CI.**
Full image scan commands below deliberately return nonzero on remaining HIGH/CRITICAL.

Clean locked Windows Python install/imports PASS; clean npm ci287 packages PASS,
0 advisories. npm warned that its lifecycle-script approval policy skipped some
postinstall hooks; compiled dependency use is separately covered by actual builds.
Sources/hashes control package identity, not bit-for-bit output: platform markers,
Python/Node CI patch selection, timestamps, registries and isolated scanner transitive
dependencies remain external variables. No bitwise reproducibility assertion.

## H-05 retained QA volume

Exact volume `h05qa-a1016d75d85a_postgres_data`, labels projecth05qa-a1016d75d85a;
distinct from `business-ai_postgres_data`. Read-only helper measured **113,994,692 bytes**
(~108.7MiB). Only the known QA DB was briefly started; READ ONLY transaction counted
3 profiles (all coffee/Kazan/2m),9 messages,0 reports,0 unexpected profiles. Stopped
again. Creation history and bounded checks support synthetic-only use; not exhaustive
PII proof. PostgreSQL contains test authentication hashes, so it is not secret-free.

Owner-only cleanup, **not executed by this task**: inspect exact project/container
mounts and labels; confirm the working DB uses business-ai_postgres_data; remove only
stopped containers belonging to h05qa-a1016d75d85a; then manually remove exactly
`h05qa-a1016d75d85a_postgres_data` in Docker Desktop. Stop if any unexpected consumer
or label appears. Never use prune, wildcard volume deletion, --remove-orphans on the
working project, or bypass the earlier policy block. Private TEMP context is separate.

## Regression and operations

- Backend quick **364PASS/104DB SKIP** on broad regression; additional source-policy
  test PASS (final hook365quick); Postgres/PostGIS **104PASS** separately;
  extended **102PASS/1550 examples**; frontend **45PASS**, Chromium mock **27PASS**.
- Ruff/format/mypy123files/TypeScript/build PASS; final prek/commit hooks recorded
  before push. Exact HEAD CI checked after push, not assumed from local tests.
- Actual new image Compose smoke PASS: migration head, API/web health, React assets,
  shipped notices HTTP200. One isolated QA project used a256MiB tmpfs DB, **no new
  persistent volume**; cap_drop/no-new-privileges exercised. Product Qwen/Ollama
  untouched; read-only demo preflight5 checks PASS including exact installed digest.
  No new live inference or full LLM evaluation claimed.
- Actual runtime (pip absent): confirmed synthetic profile→finance→PDF39762bytes/
  JSON38733bytes, same snapshot hash, credentials absent. Proves runtime export,
  independently of the integration-test image which retains installation tools.
- Current working containers and all user/baseline volumes preserved. No destructive
  cleanup, force push, bank/network attack testing or application-domain refactoring.
  QG-PR/Safe audit subset passed; full QG-OPS/RC not asserted.

## Reproduce and follow-up

See [audit runbook](../SUPPLY_CHAIN.md) and [license notices](../../THIRD_PARTY_NOTICES.md).
No raw private reports are required to reproduce. Re-scan with fresh advisory data
before accepting a release: CVE counts are time-bounded, not permanent assurances.

**H-06-FU proposal, not started:** select a supported PG17/PostGIS image with approved
native licenses; inventory exact extension/locale versions; apply H-04 populated
upgrade + encrypted backup/restore + report/geo golden checks in disposable DBs;
scan all final images; examine remaining native CRITICAL/HIGH or obtain explicit
owner-approved, scoped, expiring exceptions; test Ollama image update separately.
No persistent DB/image update is performed automatically. Research/UX/U/UI remain
unstarted. H-block acceptance waits for resolution/owner decision on these blockers.
