# H-06 checkpoint · 27.10.2026

Branch `codex/H-06-supply-chain-security`; clean base6405a1a. PR24/ed8774d merged
and six previous checks verified. No product/domain/backup changes authorised.

- H-06 card: controlled supply-chain baseline + scoped CI, no mass upgrade.
- Initial npm audit:0 advisories. Runtime pip-audit2.9.0:0 known vulnerabilities;
  full lock/dev audit with current2.10.1 pending. Only package names/versions sent
  to public registries; no .env/source upload.
- Gitleaks8.30.1 official ZIP checksum verified, full reachable git scan exit0;
  filesystem/build/.env scans and synthetic detection regression pending.
- Python43 lock entries inventoried (including project/conditional packages).
  Runtime/dev licenses and npm transitive notices pending verification.
- Found mutable Docker/action tags and unhashed Docker requirements; scanner/triage
  first, targeted hardening afterwards. No package upgrades made yet.
- QA volume exists: `h05qa-a1016d75d85a_postgres_data`; no deletion requested/performed.
- Private scanner outputs/tools: path in TEMP/h06-audit-path.txt; never commit raw
  secret reports or environment files. No scanners/tests counted as complete early.

Next: full dependency/image/license/secret baseline; scoped fixes + CI; regression;
report/HANDOFF/commit/push/PR. No UX/U/UI/BA-017/018 work, no subagents.

## Checkpoint2 · actual scanner evidence and hardening

- pip-audit2.10.1 full Windows set41 packages:0 findings; npm337 lock entries:0.
  43 Python entries include project/conditional artifacts. Sources verified public.
- Gitleaks8.30.1 history65 commits/nonshallow exit0; configured dir scan exit0.
  Two initial .venv SQLAlchemy false positives verified (key/passive parameters);
  installed deps excluded from first-party scope, dist/.env retained. Three synthetic
  PAT/age/DSN detection + redaction tests PASS. No real secrets printed/uploaded.
- Trivy0.76.1 official SHA verified, local image archives/no Docker socket upload:
  API before44HIGH/63MEDIUM/62LOW/1UNKNOWN; web3HIGH; DB26CRITICAL/239HIGH on Debian11.11;
  Ollama50HIGH/0CRITICAL. Counts are package occurrences, not exploit claims.
  Raw reports in private audit path. Full safe aggregation/triage pending.
- CRITICAL DB image baseline unresolved: don't call H-block/RC accepted. Supported
  image migration and detailed native-library reachability require bounded follow-up;
  no distro/PostGIS upgrade or owner risk acceptance invented. Local loopback preserved.
- Changes underway: pinned official action/base digests; Python Docker --require-hashes;
  remove runtime pip; remove unused curl and checksum/signature-patched brotli1.2.1-r0;
  api/migrate cap_drop ALL/no-new-privileges; limited CI diagnostic logs.
- Added scoped Supply chain CI (pip2.10.1/npm/Gitleaks pinned+synthetic selftest).
  First-party runtime license texts generated into shipped API/web notices;
  full inventory docs/qa/H-06-dependencies.json. Need root obligations/legal limits.
- Qwen specific manifest0edcdef34593... matches installed artifact; license layer
  d18a5cc7... verified SHA and exact installed-license match (Apache2). Ollama0.40.8.
- H-05 QA volume113,994,692 bytes, exact project labels distinct from working volume;
  QA-only DB read-only SQL:3 expected coffee/Kazan/2m profiles,9messages,0reports,
  no unexpected profiles. Stopped again; no volume deletion. Contains test auth hashes,
  so do not claim volume has no credential material or exhaustive no-PII proof.

Next: inspect current image builds/rescan patches; finish notices/report/exception
register (no approved ignores); integration/clean installs/regression; docs/commit/PR.

## Checkpoint3 · regression complete, release blockers documented

- api-after:8uniqueHIGH/29MEDIUM/33LOW/1UNKNOWN; web-after0. Final unique union across
  API/DB/Ollama/web16CRITICAL/174HIGH/305MEDIUM/329LOW/42UNKNOWN; full safe rows in
  H-06-advisories.csv, summaries JSON. Manual official PG17.5 advisories add coverage.
  No accepted ignores; owner approval absent, H-block not closed for RC/pilot.
- API image pip absent; web curl removed + official SHA/signed APK brotli1.2.1-r0.
  Final image secret scans0. Git strict and dir policy separated so committed deps
  paths cannot hide secrets. CI raw finding logs now private RunnerTemp only.
- Clean locked Python/npm install PASS. Regression broad quick364PASS/104DB SKIP,
  new source-boundary6tests PASS (final hook365quick); DB104PASS; extended102PASS/
  1550 examples; frontend45PASS/Chromium27PASS; Ruff/mypy123/TS/build PASS.
- H06 tmpfs Compose project `h06qa-2f85c6723c31`, private qa-context.json in auditDir;
  no persistent volume (HostConfig.Tmpfs=size256m,Mounts=[]). Smoke API/web/notice,
  finance/PDF39762bytes/JSON38733bytes/same hash/no token PASS. LLM explicit stub in
  this QA only; real Ollama unchanged, preflight5checks/exact manifest PASS.
- Full report/runbook/notices/license evidence/exception register/HANDOFF updated.
  H06 QA containers stopped; no persistent volume was created or deleted.
- Final prek: all seven hooks PASS; detector selftest (including inline allow bypass)
  and six supply-chain tests PASS. Final scanner command exposed PowerShell singleton
  splatting; workflow now explicitly types options as string[] (tool invocation fix).
  Remaining: final secret scan/docs check, commit/push, PR, exact HEAD CI.
