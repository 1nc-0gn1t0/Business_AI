# BA2/U-02 checkpoint · 29.10.2026

- PR32 merged:7281121fc78c45fe7adda9115761a01137e1b907; main synced, initial clean.
- Branch codex/U-02-dynamic-data-acquisition. No agents/U-03/frontend changes.
- Audit: OSM local/Overpass import ready, network review_required; synthetic local only;
  GHSL/licensed placeholders, no remote adapters. Exact inventory goes in acquisition doc.
- Existing POI importer atomic, versioned/advisory-locked, batch500; JSON materialized.
  Walking importer separate; no vehicle-network qualification. H-03 in-process LLM queue
  remains independent; acquisition worker separate process/image, no LLM calls.
- Plan: bounded POI-only Overpass profile, pinned TLS peer transport, operator-only v2 API,
  PostgreSQL jobs/events/idempotency/checkpoint, one supervised process with local process
  lock + DB lock + fencing. Same-installation recovery only after process-lock proof;
  expired lease alone never starts another import. No city-wide fetch.
- Implemented jobs/events/idempotency migration0009; operator API/CLI, mutex+lease+fence,
  checkpoint normalized artifact in DB, atomic existing importer+result/events publication.
  State-directory process lock survives container replacement; other installation recovery
  fails closed. API/H-03 separate, no subprocess importer.
- Security/unit/registry62PASS before final additions. First8worker tests PASS; populated
  additive migration PASS after using the full H-04 populated fixture. Final tests running.
- Live Moscow AOI37.611/55.760/37.613/55.762 PASS:23POI, ODbL,23validWGS84 points.
  Download39.346s/import0.067756s/CPU0.029344s/peakRSS91545600bytes/PGgrowth90112bytes.
  HTTP v2 coverage available only POI/exact AOI; city partial, vehicle/admin/walking missing.
  Repeated operator HTTP request reused cache with no fourth network reservation.
  Evidence docs/qa/u-02/live-moscow.json. Earlier job2attempts failed DNS/network; preserved.
- Source docs prohibit public app backend/bulk; packaged network remains review_required.
  Temporary reviewed operator_smoke permission has explicit expiry. No production approval.
- QA container business-ai-u02-qa-ac4d37be, tmpfs/no volumes, port58360; private TEMP
  business-ai-u02-qa.json/live.json holds restart details. Working containers untouched.
- Frozen final worker/PostGIS18PASS73.57s; focused unit/registry/legacy geo86PASS.
  Broad DB125PASS/1H04fixture failure fixed by cancelled job seed (assertion retained),
  populated migration/PDF+JSON rerun PASS. Final guard tests include active SQL backend,
  SKIP LOCKED busy job, lost lease/fence, metadata limit and pinned resource config.
- Ruff/format/mypy139files PASS. Strict v1 OpenAPI unchanged; generated v2 types,
  web build232KB unchanged/Chromium coffee1PASS. Live local Qwen HTTP200/profile/56s,
  corrected Decimal harness check, no repeat inference.
- Hardened Compose smoke PASS after tmpfs UID999 fix; no persistent mounts. Optional
  overlay config quiet PASS. Two-container shared-state process exclusion PASS.
- All owned QA containers/cluster/project network removed; existing volumes untouched.
- Pending: mandatory prek during commit, push/PR/exact-HEAD CI. No U-03 work.
