# Business AI 2.0 / U-00 checkpoint

- PR30 merged; main `0c7749b05f17aad9ad16e4350d267a28ef45e119`, initial tree clean.
- Branch `codex/U-00-universal-analysis-architecture`; docs-only, no U-01 implementation.
- Read current README/context/workflow, roadmap U-00..12/history, relevant DTO/domain/LLM,
  H-03 lifecycle, geo/provider/import/ranking, finance, ORM/report and frontend state.
- Existing roadmap IDs conflict with owner-selected seven-stage plan. Use `BA2/U-xx`
  versus `roadmap-v1/U-xx` in new documents; preserve all original cards/statuses.
- Reuse DataOrigin/MetricWithProvenance/InputSource/FinancialMetric, DataProvider,
  OSM manifests/importers, H-02 caps/H-03 queue, immutable report snapshots.
- AnalysisRunRecord exists, ownerless, no live writes; nonempty dataset constraint needs
  versioned expansion for no-map runs. Profile v1 extra-forbid forbids silent field addition.
- Read-only API8001: only kazan-centre,23852POI,8districts,bbox49.05/55.7/49.25/55.85,
  version44157bdc...,stale=false. Map display is not city coverage. No imports performed.
- Three architecture documents + ADR0013 Proposed completed. README/ADR index/HANDOFF and
  additive roadmap note point to them; no original roadmap cards renamed/status-changed.
- Contracts cover ProfileV2/no-map/unknown, validated DAG/capabilities, registry/coverage,
  source-ID egress/security, PG jobs/leases/checkpoints/fenced activation, assumption review,
  Decimal adapters/legacy report compatibility, actual event cursor/Vi stages.
- Resource caps are proposed candidates, not measured SLA. Source network stays disabled
  without proven egress controls; stale lease does not silently release old worker slot.
- Static validation PASS:31relative links/0broken,13legacy mappings,6future stages.
  Existing-code probes PASS: v1 rejects added fields; unknown industry has no coffee fallback;
  Moscow is not Kazan; AnalysisRun owner field absent; no-zone finance JSON roundtrip yields
  same result/base285000RUB; single DataOrigin enum preserved. No new runtime integration test.
- git diff --check PASS. Pending: final mandatory prek/commit, push/PR/exact-HEAD CI.
  No executable changes, imports/LLM calls/migrations/volume operations. U-01 not started.
