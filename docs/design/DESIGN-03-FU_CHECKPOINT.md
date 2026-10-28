# DESIGN-03-FU checkpoint

- PR29 merged/main718bcf936; branch codex/DESIGN-03-FU-landing-vi-animation; initial clean.
- Original A/B/C available. Reference measured on1919x920 page area: left7.3%, header~112px,
  headingtop~14%, right character~48%+, white64pxCTA, bottom promos and rounded transition.
- Abstract CSS card removed. New landing.css matches composition, own original Vi B in
  right advertising position, no bank photo/logo/auth. White CTA and third bubble open same Vi.
- Native welcome semantics/focus preserved. Layered greeting/portrait uses7WebP raster parts
 66024bytes after final alpha cleanup from verified B. Repro helper scripts/prepare_vi_motion.py;
 original14WebP kept unchanged. Seven layers use ?no-inline imports.
  Manual matte/exterior flood +bounded wrist; eye surface gradient only under extracted eyes.
  Early bad masks discarded; final normal/blink browser PoC visually checked.
- Independent hand wave3short cycles/1.8s, independent3feathers, source-eye blink; whole-body
  primitives for other emotion rasters. Idle finite; no per-frameJS/no new model/service.
  Reduced motion static. First-click SVG remount interference fixed with pointer-events:none.
- Main dev badges removed; one nonofficial footer. Finance short preliminary/scenario note,
  full synthetic/formula/profit restrictions under How calculated. Bank one demo notice,
  repeated card tags moved into details. Consent/mock point-of-action text unchanged.
- Final unit62PASS5.84s; TypeScript/build PASS. Initial JS232.00KB/gzip73.27,
  lazy map unchanged. Helper Ruff check/format PASS; repo-wide7hooks run on final commit.
- Full mock Chromium41PASS/1FAIL(old Ollama UI text assertion). Corrected assertion,
  then14targeted Vi/motion/error tests PASS50.3s, including5new motion specs.
 42unique scenarios covered; final full CI not yet known. No SKIP counted as PASS.
- Five final browser WebM clips recorded with final layer assets. Frames inspected;
  controlled-mock operation clips explicitly not live Qwen.23screenshots; final landing
  desktop/tablet/mobile/panels refreshed after alpha cleanup, no horizontal overflow.
- Real API/Qwen/PostGIS flow1PASS1.9min,4turns67.782/8.993/7.435/8.082s,profilev5,
 5zones,rent80000→90000/base285000→275000,2demo matches/not_assessed,PDF/JSON,browser errors0.
  Safe live-evidence JSON and screenshots saved; downloads outside Git.
- Docs/README/HANDOFF prepared. Remaining: final diff/mandatory commit hooks, push/PR/CI.
  No backend/DB/volumes/F-00 changes. Do not start next task or merge PR.
