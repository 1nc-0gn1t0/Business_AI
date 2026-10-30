# BA2/U-05 checkpoint · 30.10.2026

- PR35 verified merged; main dd8503455b2c46c8387cd6411fa0f0276983b6a7,
  clean before branch codex/U-05-universal-financial-scenarios.
- Scope: owner-bound financial inputs/review and immutable v2 results, reviewed
  auto/school/generic adapters, one bounded H-03 Qwen proposal, minimal no-map UI.
- Reuse v1 Decimal money/canonical, InputSource/DataOrigin, U-04 ProfileV2,
  conversation authorization/consent; never alter v1 formulas or reports.
- Financial input CAS is separate from profile CAS, always bound to the current
  confirmed profile revision/config hash. Profile edits invalidate current results.
- Plan: pure contracts/math tests → persistence/API/security → Qwen → UI/E2E/live
  → docs/hooks/commit/PR/CI. No U-06 or automatic merge.
- Implemented typed inputs/ranges, auto/school/generic ledger/adapters, break-even,
  one-at-a-time sensitivity, three input-driven scenarios and no-save what-if.
  Additive0012: workspaces/actions/results; bounded stock quotas, same conversation
  lock/owner/consent plus financial-input CAS, durable proposal receipts/fencing.
- New v2 API and minimal finance UI integrated with U-04 server stages; opt-in
  BA_FINANCE_V2_ENABLED=0. v1 finance and immutable report code unchanged.
- Verified: math/contract/industry unit97PASS; new financial + U-04 DB19PASS;
  populated/repeat migrations/reports/new concurrency DB41PASS (overlapping sets).
  UI4PASS + industry4PASS, Chromium3PASS1440/768/390 before final small copy/collapse
  polish. TypeScript/mypy173files/build PASS; strict actual OpenAPI36paths/126schemas
  deep-equal to base main. Final hooks/regression/CI not yet run.
- Live Qwen attempt FAILED503 in all3cases; evidence live-qwen-initial.json, not PASS.
  Ollama absent from standard Windows and both Ubuntu WSL paths. Existing local
  endpoint/model location requested asynchronously from owner. Do not install a
  replacement model or claim Completed without a full live proposal/review scenario.
- Temporary isolated QA DB context: %TEMP%/business-ai-u05-qa.json (private).
  Compose smoke build running; %TEMP%/business-ai-u05-compose.json contains config
  path/project/ports. No user volumes changed; use tmpfs only. Do not print credentials.
- Final independent checks: unit36PASS, PostGIS66PASS plus generic/cache2PASS;
  populated/reports41PASS (overlap); full Chromium49PASS; real no-mock manual-school
  1PASS5.2s/3distinct scenarios/what-if/reload/JSON, page/console0, widths1440/768/390.
  Compose healthy/PostGIS3.6/schema0012/0persistent volumes. Screenshots inspected.
- Initial real browser failure: asynchronous checkbox collection before save response;
  fixed explicit wait, no production defect or hidden test result. Initial prek exit1
  while QA/docs changed concurrently; API tests538PASS and other6hooks PASS. Final
  commit hook/CI recorded in delivery report. Source/final math36PASS current.
- Final standalone7prek hooks PASS with no concurrent source/artifact edits.
- User requested starting Ollama/in-container search. Docker default/desktop-linux
  point to same engine c37a62ab-38b5-4ad3-aa6c-59118019066a; containers/volumes empty.
  All4images scanned read-only/network-none, no ollama/qwen/GGUF/manifests. Prior
  documented runtime0.40.8 has official image digest
  sha256:2b8eecdb85aa6ea67c381c8ecffec04b2658496cf2821a8f88b0485bdff198e8.
  GPU3050Ti4GB available. Tool auto-review rejected combined create/start/pull command
  ("blocked by policy", no further reason); no operation ran. Explicit user approval
  for creating a new same-model local container/volume is pending. Do not retry the
  rejected action without that new authorization. No different/additional model.
- Status PARTIAL until existing local Qwen can generate/review a full valid scenario.
  Owner input still pending. Preserve failed live evidence; do not claim generation
  quality or install a replacement model. QA services stopped after evidence.
- New owner steering supersedes pending creation request: NO installation/download.
  Environment diagnosis completed: native Windows host, Compose/native base URLs
  distinguished; HTTP unavailable from both native process and existing API image.
  IPv4 refuses connection; no listener/process/WSL unit found. Accessible storage
  lookup cannot establish what happened to historic runtime. Sanitized JSON evidence
  and exact Windows/WSL/container recovery commands added. Do not retry model creation.
  Current checkpoint commit905bf8743664307457138d86264eae58a268f6b5 pushed; PR form only
  prepared, not submitted. Continue same branch; no merge/U-06.
- Next after owner supplies endpoint: same branch/PR, run native live harness, inspect
  rejected hypotheses/manual corrections/timing; rerun only affected checks. No U-06.
