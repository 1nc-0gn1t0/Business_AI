# H-06-FU checkpoint

- Base: PR25 merged (1bf0f5e), clean main; branch codex/H-06-FU-container-hardening.
- Scope: isolated container upgrade only. Working DB/volumes/F-00 and H05 QA volume untouched.
- Read H06 report/runbook, H04FU recovery tools/report, workflow/context/quality gates.
- Candidate source: upstream postgis/docker-postgis states 3.5 tags no longer updated;
  17-3.6 moves bullseye -> trixie. Keep PG17, use encrypted dump/new cluster/restore
  because glibc/collation changes can invalidate text indexes. Never mount old PGDATA.
- Candidate digests resolved, downloads/scans underway. No success claimed yet.
- Private tooling/results: TEMP/h06fu-audit-path.txt (no secrets in checkpoints).
- Next: same-DB-date baseline scans + per-Critical/High classification; DB proof;
  minimal API hardening; isolated Ollama GPU/CPU smoke; gates/regression/docs/PR.

## Checkpoint2 — upgrade and runtime evidence

- Frozen Trivy0.76.1 DB UpdatedAt2026-10-27T07:13:33Z, same cache for before/after.
  Before (unique): API0C/8H, DB16C/151H, Ollama0C/46H, web0.
  After: DB3C/36H (gosu removed, PG17.11/PostGIS3.6.4/trixie), API0C/8H,
  Ollama0C/0H/21M. No supported fix reported for remaining C/H; no exceptions approved.
- Nonroot DB with cap_drop ALL/new-PGDATA guard initialized in isolated tmpfs.
  Guard refused unmarked PG17 and marked wrong-major PG18; sentinel unchanged.
- Large source fixture:200 profiles,16438 messages,8518 revisions,199 reports,
  20153 POI,4905 edges. Encrypted age backup9.688s; initial restore all public hashes,
  schema/indexes identical (17.5/3.5.2 ->17.11/3.6.4). H04 fixture API verify PASS.
  Second restore with all five working extension names in progress, no working data used.
- Two harness errors corrected: exclusive write_json refused updating its existing
  private context (backup itself succeeded); temporary web probe used localhost/IPv6
  and was changed to127.0.0.1. Product healthcheck already used127.0.0.1.
- Actual new Ollama GPU full BusinessAI API:86.844s cold, correct city/category/budget,
  2344636907 VRAM bytes; warm short direct structured probe2.438s. CPU-only container
  same digest,0VRAM,short structured10.422s. Not full model evaluation/p95/browserE2E.
- Same Qwen GGUF digest0edcdef34593..., weights read-only from existing volume,
  no downloads or edits. GPU candidate stopped before CPU probe.
- Need finish extension restore/DB regression, scoped image gate tests/CI, frontend/
  property/prek/Compose/backup negatives, per-C/H triage/report/runbook/HANDOFF/PR.

## Checkpoint3 — final local gates

- Both restores PASS; second includes five extensions.19public rows/SHA/schema/indexes
  equal; source/target collation2.31/2.41 actual==recorded. No PGDATA reuse.
- New-runtime export48489PDF/57185JSON bytes PASS; original geo reference409 expected
  due spatial_runtime fingerprint, explicit API reranking refreshes it; scores equal.
- Final quick382PASS/104DB SKIP, separately104DB PASS;102extended/1550examples,
  frontend45/Chromium27 PASS; Ruff/mypy124/TypeScript/build/prek7hooks PASS.
  New17policy tests +6supply-chain tests PASS. Strict Git/current secret scans exit0.
- Real age wrong-key/tamper/duplicate/missing QA project refused; no new DB on failures.
- All exact H06FU source/target/GPU/CPU containers stopped. Original working container
  IDs unchanged; H05 QA volume only inspected, untouched. F00 SHA unchanged=true.
- Triage505before/after C/H package rows + safe scan/recovery JSON/report/runbook/ADR
  and HANDOFF updated. Union16C/174H ->3C/36H,166removedIDs/15newIDs, baseline OPEN.
- Remaining: commit hooks, push, PR, exact HEAD CI. No further product task started.
