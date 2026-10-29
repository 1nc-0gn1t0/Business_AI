# Business AI 2.0 / U-01 checkpoint

- PR31 merged/main ffc06f1d6b42c3c0fda3939edc19cdacda03115a; initial clean.
- Branch codex/U-01-data-registry-coverage. No agents, network acquisition, LLM or U-02 work.
- Added operator JSON registry with strict category/source/identity/policy validation;
  existing v1 source list projects same registrations. Default network requires review.
- Added v2 catalog and coverage; bounded existing metadata, PostGIS ST_Covers/Intersects
  on tiny extent envelopes, no POI/edge scans. Reuses ProviderDataset/DataOrigin.
- Local/freshness/completeness/acquirability/quality separated. City-only partial;
  source date not observation, period snapshot vs interval distinct. Assumptions retain
  synthetic origin, sufficiency does not auto-consume unreviewed templates.
- No schema/DDL migration needed; metadata source of truth unchanged. No new storage copy.
- Isolated PostgreSQL/PostGIS container business-ai-u01-qa-36a50541, tmpfs/no volume,
  local port in private TEMP/business-ai-u01-qa.json. Existing user/QA volumes untouched.
- Final contracts/code frozen: explicit source/publication/observation/fetch/import dates,
  snapshot-window vs observation-period semantics; safe metadata projection; source lookup;
  supplied-requirement sufficiency grouping, never tool authorization/execution.
- Full isolated DB run112PASS/1FAIL(existing psycopg/Windows Proactor readiness). Installed
  psycopg code confirms unsupported loop; Selector test-process rerun12PASS includes recovery.
  No product changes to readiness. New10registry PostGIS tests; existing populated upgrade/
  fingerprints/constraints regression passed. No new DDL needed.
- Real read-only Kazan smoke PASS:23852POI/8polygons, city partial/exact AOI available,
  Moscow missing, no imports/LLM.20requests median3.040ms/max36.962ms. Artificial final
  fixture n20 median5.882ms/max9.505ms on final source; final registry+readiness12PASS16.11s.
  Evidence contains no credentials/user payloads.
- OpenAPI39old paths/128schemas unchanged; final TS generated. Ruff/mypy130files,
  frontend typecheck/production build PASS. Focused79unit/provider/finance tests in final hooks.
- Docs/API_LIMITS/README/roadmap note/ADR accepted-addendum/HANDOFF updated.
- Owned tmpfs QA container stopped/removed after final tests, exact identity/image/mounts
  verified; no user volumes or historical containers touched.
- Pending: mandatory prek during commit, push/PR/exact-HEAD CI. No U-02 work.
