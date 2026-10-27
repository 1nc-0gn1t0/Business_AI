# DESIGN-01 · Product UI checkpoint

- PR26 merged (d270675), initially clean main; branch codex/DESIGN-01-product-redesign.
- User explicitly prioritizes hackathon product UX/UI; release security baseline
  stays OPEN. This does not complete all UX/UI roadmap cards or BA-017/018.
- Implemented: navy shell/light canvas, local Golos OFL font, seven stages, real
  home composer, external profile panel, map/list selection, finance results first,
  report overview, responsive layouts and keyboard focus/reduced-motion states.
- No backend/domain/API/schema/LLM/backup/volume changes. Existing state, CAS,
  ownership, separate consents, provenance and exports retained.
- Confirmed checks: ESLint/TypeScript/build PASS; Vitest48 PASS; Chromium30 mock
  PASS (27 previous + 3 widths); selected backend59 PASS. Initial failures fixed:
  mobile sensitivity overflow, receipt fingerprint wrapping, duplicate new action;
  tests for lazy map/new-project explicitly navigate the desired stage.
- Actual Vite5174 against existing API8000/PostGIS/Ollama0.40.8: two real Qwen turns,
  coffee/Kazan/2m/format/own funds, server confirm v3; five zones, marker/card select,
  compare; finance285000 ->275000 base after rent80000->90000; six bank demo cards;
  report PDF53940bytes/10pages +JSON128526bytes downloaded through browser.
- Report JSON SHA8bfabc7cf6da24a5c64ff893301b422e0cc063a9351078c4a0be29506fde79c0.
  Screenshots docs/qa/design-01, genuine API responses; no route mocks in live browser.
- Walking actual catchment200 and separate-consent mock lead/receipt passed; marketing
  declined. Thirteen screenshots visually reviewed. Final code lint/type/build PASS;
  final Chromium30PASS/35.3s and prek7/7hooks PASS. Documentation/notices/HANDOFF updated.
- Remaining: commit/push/PR and exact HEAD CI. Firefox/WebKit not installed; not PASS.
- Do not rerun heavy H audits. Do not start new tasks. Working Compose has old DB image;
  don't run compose up against existing PGDATA. No deleting volumes/user data.
