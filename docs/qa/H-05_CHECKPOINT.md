# H-05 checkpoint · 27.10.2026

Branch `codex/H-05-safe-diagnostics`, base365bff3. PR23 merged (GitHub REST),
main fast-forward, clean initial tree. H-05 scope matches approved card.
No H-06/research work; baseline/volumes untouched.

## Inventory before implementation

| Component | Current behavior | Gap | Target / verification |
|---|---|---|---|
| /healthz | DB/PostGIS probe, bounded connect/query | No separate liveness/schema check | Preserve legacy response; /livez and /readyz, dependency faults |
| Compose | API/web use /healthz; DB TCP pg_isready | Health doesn't validate schema | API /readyz; local smoke |
| FastAPI errors | Safe domain codes and redacted422 | No common request ID / generic500 protection | Outer ASGI boundary; sentinel fault tests |
| Logs | Plain app events, default server access logs | URLs/tracebacks potentially exposed | Allowlisted JSON events; disable raw access logs; sentinel assertions |
| Ollama | Cancellable bounded transport; generic503 | Missing model not distinguished | 404 model code; no prompt changes; transport tests |
| H-02/H-03 | Admission and bounded FIFO, separate DB phases | No safe counters/timings | Bounded process-local observations, preserve leases/CAS |
| Frontend | Safe error messages, timeout, preserved draft | No correlation ID | Validate server-generated ID and append to existing error display |
| demo_ready | Opt-in local data/model preflight | No bounded diagnostic bundle | Opt-in local CLI bundle, no secrets/body/URLs |
| H-04-FU | Private bounded logs/status/RPO checks | Separate operator diagnostics | Reuse documented status command; no backup changes |

## Stages

1. Inventory complete. Added pure ASGI ID/error boundary, allowlisted JSON events,
   bounded counters/recent32, /livez, /readyz, protected opt-in bundle, model404 code,
   queue/inference timing, bounded Docker logs and disabled raw proxy access/errors.
   No changes to DB phases, financial/geo/bank/consent rules or backup tools.
2. Targeted83PASS; initial quick352PASS/2FAIL due to additive envelope exact-body
   assertions (updated to assert preserved detail + new ID); extended102PASS;
   frontend44PASS before added download-network test; Chromium24PASS; build PASS.
   Ruff/mypy122files PASS. DB integration running; two failures need inspection.
3. DB failures были exact-body assertions: detail/rollback/hash checks сохранены,
   ID assertions добавлены;4 rerun PASS. Всего104 unique DB PASS;14 readiness/H-03
   tests повторно PASS. Extended102PASS/1550 examples, frontend45PASS, Chromium27PASS,
  25 diagnostics PASS; Ruff/mypy122/TS/build/prek7hooks PASS. Quick final summary
   verified:359PASS/104DB SKIP; TEMP/h05-quick-final.txt.
4. Реальный isolated Compose: DB down/recovery, missing model, unavailable Ollama,
   body413/budget422, no writes/profile changes, safe API logs PASS. Qwen real200,
  8.094s/34active samples/pool0. Aggregate safe evidence в H-05-evidence.json.
5. Docs/link/scope check, fresh image smoke, baseline SHA verified. QA containers
   stopped; automatic action review rejected volume deletion (blocked by policy),
   so synthetic QA volume/private context retained. No deletion workaround.
   Remaining: commit hook, push, PR и exact HEAD CI. GitHub browser авторизован.
   Не повторять live eval/старые тяжёлые тесты без новых причин.

Local logs (not committed): TEMP/h05-{quick,db,extended,e2e}.txt. No secrets recorded
in this checkpoint. Prior reports remain historical evidence only.
