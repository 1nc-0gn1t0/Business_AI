# DESIGN-03 checkpoint · 28.10.2026

- PR28 merged/main45c6a0d2, branch codex/DESIGN-03-vi-mascot; initial clean.
- User attachments A/B/C inspected. Actual sheet has22 labelled states.14original crops
  WebP282476bytes/avatar5216bytes. Sources/crops/hashes in src/assets/vi/provenance.json.
  No redraw/other model/bank ad/logo reuse. Crop contact sheet checked, no adjacent labels.
- New Landing/App lazy wrapper; old App moved to BusinessFlow, guards retained.
 3bubble dock (2decorative), native welcome dialog, Escape/outside/close +focus restoration.
  Root/home preserves mounted workspace. Hash marks screen, never backend readiness.
- Real operation-linked mascot states in chat/geo/finance/bank/export; success only after
  prepared current server report. Initial rules mode not mislabelled as stub during Qwen.
- Fixed reproduced native focus restoration ordering and animation transform overriding
  mobile scaling; normal-motion live screenshots reviewed after fixes.
- Chromium37/37 PASS (~1.2min), including32previous +5new. New mobile test390x568,
  actual screenshots390x844. Focused Vi/report unit8PASS; full final unit/prek pending.
- Real browser no-mock full flow PASS (~1.4min):4Qwen turns,profilev5,5PostGIS zones,
  finance285000→275000,2demo matches,credit not_assessed,PDF54646bytes/JSON128381bytes.
  Final screenshot07 captures actual pending geo request, no artificial hold. 23UI screenshots
  and sanitized JSON in docs/qa/design-03. Downloads outside Git. No browser errors.
- Build PASS: initial JS230.11kB/gzip72.42, lazy BusinessFlow85.47kB, map1111.61kB;
  map size warning remains. No dependencies/backend/contracts/DB/volumes changed.
- Vite5176 proxies existing temporary API8001 (current backend code unchanged), real local
  PG17.5/PostGIS3.5.2/Ollama0.40.8/Qwen4B. Existing volumes/F00 untouched.
- Next: docs/HANDOFF/README; final unit+prek/type/lint, diff,commit/push/PR/CI.
  No extra models/agents, no next roadmap/security/research tasks.

## Final verification checkpoint

- Full Vitest62PASS; lint/TS/build PASS. Final bundle230.11kB/gzip72.42,
  flow85.47/gzip23.60. Prior37full Chromium PASS; final5Vi cases PASS after adding
  Browser Back with consent-open regression on1440/768/390. CI will repeat37 on exact HEAD.
- Native consent hidden under landing reproduced document inertness; fixed via active
  presentation prop and dialog cleanup, no consent decision/API semantics changed.
-23current UI screenshots +separate asset contact sheet; start-question recaptured after
  compact greeting addition without repeating LLM. Real full route and pending screenshots
  already verified. No heavy audits/evaluation repeated.
- Docs/README/HANDOFF/link checks/diff check done. Remaining: commit hooks,push,PR,CI.
