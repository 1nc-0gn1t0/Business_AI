# Business AI — HANDOFF

## H-06 · supply-chain audit/hardening · 27.10.2026 (МСК)

- PR24/ed8774d merged, main6405a1a ff-only, исходное дерево чистое; ветка
  `codex/H-06-supply-chain-security`. Итоговый SHA/PR/CI — в сообщении сдачи.
  [Отчёт](qa/H-06_SUPPLY_CHAIN_REPORT.md), [runbook](SUPPLY_CHAIN.md),
  [лицензии](../THIRD_PARTY_NOTICES.md), [checkpoint](qa/H-06_CHECKPOINT.md).
- Python lock43 entries (41 evaluated Windows distributions)/npm337 entries:
  0 package advisories. Strict Git65 reachable commits/current/build/image secrets0;
  PAT/age/DSN positive/redaction self-test PASS. .env отсутствуют, template placeholder
  публичный; реальные user keys/credential stores не читались.2 upstream .venv false
  positives проверены; history policy не имеет path exclusions.
- Actions full SHA/persist-credentials:false, base digests, Python artifact hashes,
  test uv wheel hashes; runtime pip removed, curl closure removed/Brotli1.2.1-r0.
  Web rescan0; API pip6 findings removed. API/migrate cap_dropALL/no-new-privileges;
  context key/env/archive exclusions. New scoped Supply chain CI с fail-closed
  pip/npm/Gitleaks и без raw findings в output/artifacts. App dependency versions,
  бизнес-логика, миграции, LLM orchestration и backup architecture не менялись.
- **H-блок пока НЕ принят для RC:** final image unique union16CRITICAL/174HIGH/
  305MEDIUM/329LOW/42UNKNOWN. DB Debian11.11 EOSL/PG17.5 (16critical/151high unique)
  и official PG advisories требуют отдельного supported image/migration/recovery
  follow-up. API8high/Ollama46high частично triaged; owner-approved exceptions нет.
  Это не число доказанных эксплойтов API. Изменения working DB/images не применялись.
- Runtime notices shipped API/web,43Python/337npm license inventory. Конкретный Qwen
  manifest/license blob совпали с installed artifact (Apache2), model digest в
  demo-manifestv2. LGPL/native/GPL/GPU redistribution и собственная app license
  требуют review. Нельзя объявлять legal compatibility/bitwise reproducibility.
- Регрессия: quick364PASS/104DB SKIP до финального source-policy test; затем6config
  tests PASS (итоговый hook включает365quick); DB104PASS, extended102PASS/1550examples,
  frontend45PASS/Chromium27PASS, Ruff/mypy123/TS/build PASS. Prek/final CI проверяются
  перед сдачей, SKIP не PASS. Actual tmpfs Compose/new runtime smoke: миграции,
  API/web/notices, finance, PDF39762bytes/JSON38733bytes/same hash/no token PASS.
  Product Ollama/Qwen не обновлялись; real inference не повторялся, preflight5PASS.
- H-05 volume `h05qa-a1016d75d85a_postgres_data`113994692bytes (~108.7MiB), labels QA,
  read-only check3 expected profiles/9messages/0reports; снова stopped, не удалён.
  Test auth hashes есть; это не утверждение полного отсутствия credential material.
  H-06 smoke DB — tmpfs256MiB, persistent volume не создаётся; existing volumes/F-00 сохранены.
- Следующее — review PR/решение владельца по H-06-FU proposal (не начат): supported
  DB image + H-04 populated/restore proof + native CVE triage; Ollama image review
  отдельно. Не начинать UX/U/UI/BA-017/018 или иные работы автоматически.

## H-05 · safe diagnostics · 27.10.2026 (МСК)

- PR23/a50e6da merged (REST verified), main365bff3 ff-only/чистый;
  ветка `codex/H-05-safe-diagnostics`. [QA report](qa/H-05_DIAGNOSTICS_REPORT.md),
  [evidence](qa/H-05-evidence.json), [runbook](DIAGNOSTICS.md),
  [checkpoint](qa/H-05_CHECKPOINT.md). Фактический финальный SHA/PR — в итоговом отчёте.
- /livez отдельно от DB/модели; /readyz bounded PostgreSQL/PostGIS/schema0008;
  legacy /healthz сохранён. Opt-in diagnostics default404, отдельный≥32char token,
  model presence≠inference PASS. Queue/pool/counters/recent32 process-local.
- Server-generated32hex request ID, error envelope additive с прежним detail,
  allowlisted JSON logs, no raw exception/URL/body/SQL, Docker10MiB×3. Frontend
  показывает ID/понятные pool/model/export ошибки, сохраняет draft, без auto retry.
  No dependencies/миграций/изменений формул/гео/банк/consent/backup архитектуры.
- Реальные isolated faults: DB down /livez200 /readyz503 за4.015s; recovery без
  записей/утраты профиля. Missing model503/.109s; Ollama down503/.360s; /readyz200,
  bundle degraded, recovery PASS. Synthetic secret/tokens отсутствуют в проверенных API logs.
- Actual Qwen4B coffee/Kazan/2m: HTTP200/extraction_mode=ollama,8.094s warm,
 34 active-phase samples/pool0. Две ранние measurement assertions ошиблись на
  Decimal string и границах фаз; проверки исправлены, модельные поля были корректны.
  Не полный live eval/p95/soak. DB H-03 tests отдельно подтверждают0 idle transaction.
- Проверки: quick359PASS/104DB SKIP (DB отдельно104uniquePASS, no XFAIL);
  extended102PASS/1550 examples; frontend45PASS; Chromium mock27PASS, в т.ч.390px/ID;
  Ruff/mypy122files/TS/build/prek7hooks/Compose smoke PASS. Exact CI после push
  фиксируется в PR/итоге; SKIP не засчитаны как PASS. QG-OPS только diagnostics subset.
- Baseline/рабочие containers/volumes сохранены; synthetic QA project изолирован.
  Остатки: single-worker/volatile counters, нет automatic alerts, loading/export health
  не сертифицируется; pre-ASGI/proxy/startup failures без backend ID; R-12 owner
  keys/scheduler/offsite, H-06 scanners, public auth/TTL и RC gates остаются открыты.
- Далее только review/merge владельцем. H-06 не начинать без разрешения.
  BA-017/018 — отдельный незавершённый исследовательский трек, не отменены.

## H-04-FU · encrypted backup и recovery · 26.10.2026 (МСК)

- PR[#22](https://github.com/1nc-0gn1t0/Business_AI/pull/22) H-04/c39d4ac merged
  `2026-10-26T06:07:10Z`; main930b8e4 ff-only, исходное дерево чистое. Ветка
  `codex/H-04-FU-backup-recovery`; реализация `8e40fc42bee97ca387f653f813faa2687a71c60d`,
  [PR#23](https://github.com/1nc-0gn1t0/Business_AI/pull/23) открыт/прикреплён, не merged.
  Финальный HEAD после исправления CI fixture/документации и exact SHA checks — в PR/отчёте.
- Новый `scripts/encrypted_backup.py`: pg_dump→age1.3.2 streaming, encrypted
  metadata, bounded buffers/deadline/atomic publication, OS lock, RPO/status exit2,
  private logs и explicit dry-run prune/keep≥1/PIN. Restore полностью authenticates
  в controlled private TempFile до createdb; no existing/source overwrite; hashes/
  schema/extensions сверяются. F-00 backup helper переиспользован с optional Compose
  prefix, legacy plaintext command сохранён только для совместимости/истории.
- `install_age.ps1` проверяет pinned official Windows/Linux SHA; CI ставит binary
  вне repo и реально тестирует crypto17 cases с disposable keys, без GPU/банка.
  `register_backup_task.ps1` preview/install/TestOnly + hidden `run_backup_job.ps1`:
  предложены12h backup/hourly status. **Постоянные задачи не включены.** Temporary
  native trigger действительно выполнился exit0, age8.823s, отдельно verify PASS.
  Два actual watch runs на PostgreSQL также PASS. Canonical paths решают packaged
  AppData vs native Task/Docker; JSON explicit UTF8. Real owner key не создавался.
- Fixtures small/large:17.54MB/58.15MB; large200 owners,16438 messages,8518 revisions,
  199 PDF/JSON,303 consents,52drafts/51receipts,457audit,20153POI/4905edges/2graphs.
  New synthetic users/data; small checked-in OSM extract,20k authored POI/grid.
  Частотные caps повышены только внутри fixture seed, runtime limits неизменны.
- Full clean Compose recovery **53.157s**: prepare/retrieve/cipher checks/auth,
  fresh cluster, restore19public tables/source-equal hashes, Alembic check, API/web
  readiness и реальные HTTP owner/history/receipt/audit/geo/finance/bank/PDF/JSON/
  Qwen4B. Model actual ollama, coffee/Kazan/2m PASS; не полный LLM eval.
  Large cipher11312502 bytes/backup8.406s; small133883bytes/backup4.375s,
  small authenticated restore+verify5.235s и отдельный API DTO/owner/export PASS.
- Реальные fault checks: wrong/missing identity/file, tamper/truncate (с пересчитанным
  public SHA), DB unavailable, duplicate target отказаны. pg_restore backend terminated
  только в owned QA DB:0 partial tables; target до/после сохраняется. Restore plaintext
  residues отсутствуют. Последняя хорошая копия сохраняется при FS/producer failure;
  PIN защищает реально rehearsed backup. Ошибка bootstrap readiness исправлена TCP
  health (`pg_isready -h127.0.0.1`), working containers не пересоздавались.
- [QA report](qa/H-04-FU_RECOVERY_REPORT.md), [evidence](qa/H-04-FU-evidence.json),
  [операторский runbook](BACKUP_RESTORE.md). RPO age510.177s на probe; isolated clock
  ровно24h OK/24h+1s STALE. Нет SLA для выключенного/спящего ПК, unlogged user,
  lost disk/key/offsite. RTO — полный **локальный** цикл при cached images/модели и
  доступном identity, не OS reinstall/model download/key-loss disaster.
- Регрессия: quick332PASS/102DB SKIP (отдельно102PASS, no XFAIL); crypto17PASS;
  extended102PASS/1550 property examples; frontend43PASS; Chromium24PASS; prek7hooks,
  Ruff/mypy/TS/build/Compose smoke PASS. Final commit hooks/CI сверяются перед сдачей.
  Без новых app dependencies/DTO/миграций/формул/гео/банк/LLM orchestration изменений.
  Первый Ubuntu CI:331PASS/1FAIL — watch test подменял общий time.sleep и захватывал
  Linux subprocess backoff waits. Воспроизведено в local Linux, выделен scheduler-only
  wait_interval без ослабления assertion; повторный Linux crypto17PASS. Не выдавать
  прежний CI за успех, дождаться exact final HEAD Windows/Ubuntu/Compose.
- **Остатки R-12:** инженерный OPS-ENC подтверждён для нового pipeline; owner должен
  создать реальные keys/custody, проверить real backup/restore, включить scheduler и
  защитить **исторические plaintext F-00/H-04** (они сохранены, не зашифрованы задним
  числом). Baseline SHA прежний690133a959640c3ee0167c46bc39eea13b966f2fff615f4158c10eda85e74feb.
  Offsite/globals/host/model DR/постоянный monitoring остаются; весь QG-OPS/RC не закрыт.
- Далее: review/merge H-04-FU решает владелец; H-05/H-06 и BA-017/018 не начинать
  автоматически. Исследовательский трек не отменён/не выполнен. Порядок roadmap сохранён.

## H-04 · заполненная БД и recovery · 26.10.2026 (МСК, исторический)

- PR[#21](https://github.com/1nc-0gn1t0/Business_AI/pull/21) H-03 headfb74296 merged
  `2026-10-26T05:33:55Z`; шесть exact-head checks SUCCESS. Main ff-only869453f,
  исходное дерево чистое; ветка `codex/H-04-migrations-restore`. Реализация
  `c9b86c5494bd13260f1680d7e0d7b5b31bb906ba`, опубликован
  [PR#22](https://github.com/1nc-0gn1t0/Business_AI/pull/22), прикреплён к чату.
  PR открыт, не объединён; фактический финальный HEAD/CI — в PR/итоговом отчёте.
- Исправлен **D-04**: Alembic connection scoped public + catalog-based exclusion
  extension-owned tables. Старый env воспроизводит ложный TIGER remove_table;
  новый check PASS, настоящие лишние app table/column обнаруживаются. Default CLI
  downgrade отказывает до подключения; исключение только explicit disposable UUID
  tests. Нет новых миграций/изменений app DTO/business logic/LLM/geo/finance/bank.
- Новый populated0007→0008 test:17 непустых app tables, counts/row SHA/FK/unique,
  PostGIS geometry/provenance, profile versions/consents/withdrawal/draft/receipt/audit.
  На0007 отчётов ещё нет; после upgrade создан immutable report, повторный upgrade
  сохраняет его bytes. SQL error/terminated Alembic backend после create_table
  полностью откатывают DDL/revision, retry PASS. Wrong user/config → safe503.
- F-00 operator tool переиспользован; дополнен offline verify, size/symlink check,
  POSIX0600, optional explicit isolated backup source, separate restore/verify timing,
  connect timeout. Windows private parent ACL проверен: только текущий оператор.
- Новый private QA archive117876 bytes, SHA6092bb27390f5394ee22be8519ae23aa9c01ad0e1f4647c3fdebc6524f31b5e6.
  Backup3.437s; restore1.125s + verification2.156s =3.281s. Все19 public tables/hash/
  schema/extensions/index/server checks PASS; owner/foreign-owner, receipt и старые
  PDF/JSON через API byte-identical. Реальный F-00 immutable image read-smoke на
  restored0008 PASS. Existing target refused; invalid pg archive оставил только
  новую пустую QA БД, working DB/volumes не затронуты.
- [MIGRATIONS](MIGRATIONS.md), [BACKUP_RESTORE](BACKUP_RESTORE.md), [evidence JSON](evals/H-04-migration-restore.json).
  Private fixture credentials/dumps вне Git. F-00 dump SHA не изменён:
  `690133a959640c3ee0167c46bc39eea13b966f2fff615f4158c10eda85e74feb`.
  Три созданные H-04 UUID-БД удалены после проверок по точным именам без FORCE;
  private archives/aggregate evidence сохранены, старые QA/F-00 БД и volumes не тронуты.
- Проверки: DB/PostGIS102PASS/no XFAIL; extended102PASS/1550 property examples;
  Chromium mock24PASS; frontend43PASS; build/TS/Ruff/mypy/prek7hooks PASS. Compose
  migrate image built, штатный DB Alembic check и API/web/PostGIS smoke PASS.
  Quick backend315PASS/102DB SKIP (они отдельно102PASS),102extended deselected.
  Первый Windows pytest tmp отказал существующему temp parent; отдельный
  PYTEST_DEBUG_TEMPROOT исправил окружение без изменения ACL старых каталогов.
  Неправильный FK probe сначала затронул несколько rows и получил unique violation;
  исправлен на один row, ожидаемый FK rejection подтверждён. Проверка private0600
  state выполняется тем же QA root UID, который его создал; app user не повышался.
- **Ограничения:** backup **не зашифрован**; OPS-ENC2–4ч с age/key custody/roundtrip
  вынесен отдельно до RC. Retention policy описана, scheduler/offsite/PITR отсутствуют,
  RPO≤24h/полный RTO≤60min не подтверждены; QG-OPS только DB recovery subset.
  Programmatic/direct SQL downgrade обходит CLI guard — это не RBAC. Public-only
  schema policy; nontransactional future migrations требуют собственного recovery.
  Полный live Qwen evaluation не повторялся: LLM/API business contracts не менялись;
  inference/concurrency/consent regression из H-01…03 вошла в DB102PASS.
- Далее: review/CI/merge H-04 решает пользователь. **H-05 не начинать автоматически**.
  BA-017/018 — отдельный невыполненный research track; сознательный технический
  порядок F-00→H-01…06→UX→U→UI→QA→RC сохранён, UX/U research dependencies не сняты.

## H-03 · inference без PostgreSQL connection · 26.10.2026 (МСК, исторический)

- H-02 [PR#20](https://github.com/1nc-0gn1t0/Business_AI/pull/20) merged
  `2026-10-26T02:45:22Z`; headf000ecd, main `559a193503f12ca4156526c3ab86474a5fde8e2a`.
  CI merge SHA: Windows/Ubuntu/Compose SUCCESS. Main ff-only/divergence0/0, исходное
  дерево чистое; ветка `codex/H-03-inference-isolation`. Реализация:
  `eb9a67e2a68ea711e3a46ae36694e1c19fcbb15a`, push CI Windows/Ubuntu/Compose SUCCESS
  ([run40264521878](https://github.com/1nc-0gn1t0/Business_AI/actions/runs/40264521878)).
  [PR#21](https://github.com/1nc-0gn1t0/Business_AI/pull/21) открыт в main и прикреплён
  к чату; не объединён. Итоговый SHA после этого doc commit/exact HEAD CI — в отчёте.
- H-03 реализована: short locked read → immutable DTO snapshot → Session closed →
  bounded FIFO/Qwen без БД → новая короткая write Session с owner/CAS/consent revision/
  quotas/validation и atomic profile/messages/revision commit. Withdraw→grant не
  легализует старый snapshot. Непосредственный inference вынесен из Conversations.update.
- Ollama async capability использует закреплённый httpx2 2.14.0 (из dev в runtime,
  без обновления lock versions). Sync API для offline adapters/eval сохранён; оба
  используют общий prompt/schema/grounding/parser. Новых таблиц/миграций/infra services/
  BusinessProfile schemas/geo/finance/bank/provenance/report formats нет.
- FIFO: active1/waiting1, wait10s; config `inference_queue_size`0…4,
  `inference_wait_seconds`(0,30]. LLM_TIMEOUT_SECONDS default120/max180 остаётся одним
  inference deadline. H-02 body/DTO/stock/window limits действуют. Messages считаются
  в heavy frequency, но не занимают аналитические active_heavy2 slots; общий active8.
  Queue429 без Retry-After, клиент сохраняет текст. Proxy240s/browser250s согласованы
  с максимальными queue/model settings и запасом на короткие DB phases.
- Cancellation: disconnect удаляет queued ticket/отменяет async Ollama и предотвращает
  запись. DB worker дожидается rollback/close, cancellation flag проверяется до записи
  и после flush перед commit. После уже выполненного commit ответ может потеряться —
  перечитать версию, CAS; не обещать exactly-once delivery. Sync fallback thread не
  убивается: lease держится до завершения, второй inference не запускается скрыто.
- **H01-P1-02 закрыт в реализации**: before probe1 idle tx/1pool; after0/0, реальный
  XPASS, затем xfail marker снят с desired assertion. Узкий pool1 обслужил пять
  параллельных GET geo/datasets (67–72ms) при модели; разные Session подтверждены.
  Реальная Qwen4B/Q4_K_M ID0edcdef34593:538 samples, pool peak0/idle tx peak0,
  request27.609s, кофейня/Казань/2млн корректны. [PERFORMANCE](PERFORMANCE.md),
  [сырые агрегаты](evals/H-03-inference-pool.json), ADR-0001/0002/API_LIMITS обновлены.
- Проверки: quick310PASS/95DB SKIP; extended102PASS/1550 property examples; отдельный
  Postgres/PostGIS **95PASS без XFAIL**; frontend43PASS; Chromium mock24PASS;
  real Qwen browser3PASS/57.4s (пекарня/автосервис/полная кофейня).
  Промежуточный full DB93PASS/2FAIL: старые transport mocks urllib обновлены на async
  без изменения assertions, targeted14PASS и финальный full95PASS. Никакой mock не
  выдан за live. Ruff/mypy/build/Compose smoke/ранний prek7hooks PASS; окончательные
  commit hooks/CI проверяются перед завершением.
- Live UI использовал новые API8017/web5177 и **новую копию** F-00 `f00_restore_h03_<uuid>`.
  Restore checks tables/schema/extensions/indexes/version PASS (14s), это подготовка
  изолированных тестов, **не выполнение H-04**. Named QA upstream исключает случайное
  попадание web в рабочий API alias. Source archive SHA неизменен
  `690133a959640c3ee0167c46bc39eea13b966f2fff615f4158c10eda85e74feb`.
  Не удалять существующие volumes/пользовательские/старые QA БД. Временная H-03 БД
  и её два QA-контейнера после проверки удалены по проверенному UUID/именам;
  исходная БД, старые QA и volumes сохранены.
- Новых P0 нет на выполненном scope. QG-OPS — доказаны connection lifecycle, bounded
  queue и доступность small reads; **не** p95/5-heavy-load/8ч soak/GPU kernel cancel.
  Single-worker/asyncio loop, не distributed protection. D-01…04/H-04…06 остаются.
  Первоначальные DockerHub/Context7 fetch timeouts обойдены existing images/первичными
  docs; последующая обычная Docker build успешно прошла, системные настройки не менялись.
  Окончательный локальный prek:7/7hooks PASS, OpenAPI TypeScript AST unchanged,
  doc links/evidence JSON/diff checks PASS. Commit hooks и exact HEAD CI — в PR/отчёте.
- Пользователь выполнил вход во встроенном браузере, PR создан через GitHub UI;
  credentials из Git helper не извлекались. Работа не блокируется авторизацией.
- **Далее:** review H-03. Не merge автоматически; H-04 только после отдельного
  разрешения. BA-017/018 остаются отдельным невыполненным исследовательским треком;
  порядок F-00→H-01…06→UX→U→UI→QA→RC сохранён, зависимости будущих UX/U не сняты.

## H-02 · input/resource limits · 26.10.2026 (МСК, исторический)

- PR [#19](https://github.com/1nc-0gn1t0/Business_AI/pull/19) merged
  `2026-10-25T22:02:19Z`, main `c3c8c73d92c1f63664b440faee62d69c9c5fce2e`.
  Fetch/ff-only, divergence0/0, чистое дерево до начала; ветка
  `codex/H-02-api-resource-limits`. Exact HEAD/новый PR/CI — в финальном отчёте/PR.
- Реализация опубликована коммитом `6149cf68b7a7648a075d1881d43bcf3933c81915`;
  GitHub CI этого SHA: **Windows/Ubuntu/Compose smoke — SUCCESS**,
  [run40241666474](https://github.com/1nc-0gn1t0/Business_AI/actions/runs/40241666474).
  Создание PR пока требует внешнего действия: автоматическая проверка отклонила
  REST-вызов с Git credential helper без пояснения причины; GitHub CLI отсутствует,
  встроенный браузер GitHub не авторизован. Пользователю показана compare-вкладка
  `main...codex/H-02-api-resource-limits` для входа/создания PR. Не считать PR созданным
  или задачу принятой, пока реальный PR не открыт; после входа завершить этот шаг,
  attach PR к чату и проверить exact HEAD CI. Документационный commit после указанного
  implementation SHA не меняет выполненные алгоритмы/тесты.
- Выполнена H-02, не H-03: [полная инвентаризация 18 write API, caps/квоты/config](API_LIMITS.md).
  Новый общий pure-ASGI envelope/admission заменил report-only middleware.
  Full profile соответствует PATCH200/20; strict version INTEGER; безопасные
  standard422 без input/context/arbitrary keys. HTTP413/422/429; реальный Retry-After
  только для временного окна; busy/stock не обещают время. React сохраняет draft,
  объясняет отказ; автоматического retry и redesign нет.
- PostgreSQL count/byte stock checks + короткая transaction advisory lock перед
  записью; owner/CAS/consent/idempotency сохранены. Новая guest session/restart не
  сбрасывает stock. Отзыв granted consent имеет ограниченное safety exception.
  Временные/active counters — **только один worker**, WEB_CONCURRENCY!=1 fail closed;
  CLI --workers>1/replicas запрещены deployment-инструкцией, автоматически не определяются.
  Нет новых сервисов/зависимостей/миграций, гео/финансовых/банковских алгоритмов или
  форматов сохранённых отчётов. OpenAPI/TS regenerated comparison: v1 fields/types
  сохранены, только новые validation bounds; formatting-only TS diff не включён.
- Результаты: backend quick **299 PASS/83 SKIP** (это DB skip, не успех), extended
  **102 PASS**, **1550** successful property examples; PostgreSQL/PostGIS **82 PASS/
  1 XFAIL**; frontend **41 PASS**; Chromium mock **22 PASS**, дополнительно4 targeted
  PASS с keyboard и390px. Новые refusal probes проверяют counts/version/no inference/
  no render/no sender, а не только status. H01-P1-01/P2-01 XPASS воспроизведён,
  xfail decorators сняты с сохранением assertions; **H01-P1-02 оставлен XFAIL для H-03**.
- Compose db/api/web healthy; build/HTTP smoke PASS, head `0008_analytical_reports`.
  Single live Qwen smoke в новой isolated H-02 UUID-БД: oversized413 не меняет
  version0, реальная кофейня/Казань/2млн распознана, modeollama/version1/history3,
  **22.04s**. Не полный BA-016 evaluation. Модель `qwen3:4b-instruct-2507-q4_K_M`,
  ID `0edcdef34593`; запущен существующий остановленный Ollama container, downloads нет.
  Working DB tests не выполнялись, пользовательские данные/volumes/F-00 сохранены;
  SHA backup неизменен: `690133a959640c3ee0167c46bc39eea13b966f2fff615f4158c10eda85e74feb`.
- Ограничения/remaining риски — SECURITY_TEST_REPORT и RISK_REGISTER. Не полный
  pentest/load, не multi-worker/public readiness; stock logical bytes не physical disk cap.
  H-03 transaction/queue, H-04…06 и D-01…04 остаются. Vite large-chunk warning прежний.
  Первые prek получили 3 Windows temp permission errors; использован отдельный
  PYTEST_DEBUG_TEMPROOT без смены ACL, изменения assertions или удаления данных.
  Повторный **prek: все 7 hooks PASS**; Ruff/format/mypy, ESLint/TypeScript и build PASS.
  18 write operations сверены с OpenAPI; относительные doc links/git diff --check PASS.
  Временная H-02 smoke-БД и только её контейнер после smoke удалены по проверенному
  UUID имени; существующие QA/пользовательские БД и volumes сохранены.
- Сознательный порядок F-00→H-01→H-02→H-03…06→UX→U→UI→QA→RC сохранён.
  BA-017/018 — отдельный research track, не отменён/не выполнен; зависимости UX/U
  требуют отдельного решения. **Далее: review/CI H-02; H-03 только после разрешения.
  Не merge автоматически, не начинать исследования или следующую задачу.**

## H-01 · ранний triage · 25.10.2026 (МСК, исторический)

- PR [#18](https://github.com/1nc-0gn1t0/Business_AI/pull/18) merged 18:33:42 UTC.
  Main `6d2cee01473cb88ad4ce0f0632436fda4a32e9c0`, ff-only/divergence 0/0,
  исходное дерево чистое. Ветка `codex/H-01-early-triage`; HEAD/PR/CI — в итоговом отчёте.
- **Сознательное изменение порядка владельцем:** F-00 → H-01 → H-02 → H-03 → H-04 →
  H-05 → H-06 → UX → Универсальность → UI → Комплексное QA → RC.
  BA-017/018 вынесены в отдельный research track, **не отменены и не выполнены**.
  Содержание карточек/зависимости roadmap не менялись; до UX/U требуется отдельное
  решение о research dependencies/сроках. Этот PR не разрешает их обойти.
- Scope — ограниченный H-01, не pentest/H-02. Проверены реальные owner/CAS/consent,
  idempotency, stale report, safe errors/log sinks/paths и предварительные resource caps.
  AnalysisRun DTO/ORM есть, HTTP CRUD пока нет — N/A, не PASS будущей авторизации.
- **Выявлено P0=0; подтверждены 2 P1 и 1 P2:** H01-P1-01 caps/guest budgets (R-01/03),
  H01-P1-02 DB transaction during inference (R-02), H01-P2-01 отражение собственного
  synthetic input в request-validation422. Не считать их доказанным DoS/IDOR/утечкой
  чужих секретов. Старые D-01…04 остаются; полный re-audit не проводился.
- Новые tests: 2 PASS rollback после успешного SQL flush (profile/history и
  submission/draft/audit); 3 strict XFAIL probes открытых findings. XFAIL не PASS,
  исправление должно дать XPASS с удалением метки, сохранением desired assertion.
- Свежий targeted offline:67 PASS/2 XFAIL (5,31 с); Postgres targeted:25 PASS/1 XFAIL
  (40,95 с), UUID fixture DBs. Новые tests входят в числа, не суммировать повторно.
  Воспроизводимые команды/матрица и все поля findings — SECURITY_TEST_REPORT;
  статусы каждого старого риска — RISK_REGISTER. Новый prek: все 7 hooks PASS;
  CI точного HEAD — в PR/итоговом сообщении, не в исторических результатах F-00 ниже.
- Docker Desktop был выключен; запущен штатно. Тестовый Compose использовал
  существующий db volume; рабочие write API не вызывались. Архив F-00 SHA неизменен,
  baseline files/продуктовые исходники/публичные API/алгоритмы/миграции не менялись.
- Не выполнялись live Qwen/GPU overload, load/soak, browser E2E, scanners/legal review.
  Реальные token/PII в отчёты не добавлялись, вводы только синтетические.
- **Далее:** review/решение владельца по H-01 PR. При отсутствии P0 допустим переход
  к H-02 только после отдельного разрешения, в контролируемом loopback scope.
  Не merge автоматически; H-02…06/BA-017/018 самостоятельно не начинать.

## F-00 baseline · сохранённая передача (текущий статус H-01 выше)

- PR [#17](https://github.com/1nc-0gn1t0/Business_AI/pull/17) merged 25.10 в 17:34:21 UTC.
  Main `709398cb48241df3c1202b0e7c958ab73bd9c99d`, fetch/ff-only, divergence 0/0,
  исходное дерево чистое. Roadmap утверждён владельцем; разрешена только F-00.
- Ветка `codex/F-00-mvp-baseline`; фактический HEAD/PR/CI — в итоговом сообщении.
  **Не объединять PR; не начинать H-01/BA-017/018 самостоятельно.**
- Baseline ID `f00-mvp-20261025-v1`: [baseline](baselines/F-00_BASELINE.md),
  [единый manifest](baselines/F-00-manifest.json), [backup/restore](BACKUP_RESTORE.md).
  Pins приложения/образов/locks/модели/OSM/graph/synthetic/алгоритмов и ограничения.
  Tag `baseline/f00-mvp-20261025-v1` только предложен, не создан.
- Добавлен операторский `scripts/backup_postgres.py` + 11 offline safety tests.
  Работает через существующие контейнеры, не новые сервисы/зависимости.
  Явно выбирает running non-oneoff: Compose exec api при QA иначе выбирал копию.
- Docker Engine 28.0.1, Postgres17.5/PostGIS3.5.2, db/api/web healthy, head 0008.
  До старта сервисы были остановлены/удалены, volumes сохранены; подняты из текущей
  сборки. API sources и built frontend побайтово совпали с checkout/dist.
- Свежая регрессия: 7 prek hooks PASS; fast API 261 PASS/72 SKIP/102 deselected (3,62 с),
  extended 102 PASS (6,17 с, 1550 property examples), DB 72 PASS (76,29 с), Vitest 35 PASS,
  Chromium 18 mock PASS (26,9 с), 3 real Qwen browser PASS (reporter 1,2 мин), build PASS.
  Новый operator suite 11 PASS; отдельный Ruff/format scripts PASS. Точные команды/NOT RUN
  в baseline. Это новые результаты; полный live corpus BA-016 не повторялся.
- Smoke 3/3, readiness 7/7. Сначала demo-preflight 5/7: DATA_DEMO_ENABLED=false по умолчанию;
  после явного `$env:DATA_DEMO_ENABLED='true'` перед Compose →7/7. `.env` не менялся.
- Финальный архив **вне Git**, private ACL текущего пользователя:
  `%LOCALAPPDATA%/BusinessAI/F00-20261025-private/backup-02/database.dump`.
  5 949 397 bytes, SHA `690133a959640c3ee0167c46bc39eea13b966f2fff615f4158c10eda85e74feb`.
  Backup15,016 с; restore+verify15,093 с в **новую** `f00_restore_20261025_a2`.
  19 public tables counts/hashes + schema/extensions/indexes совпали; 5 report hashes,
  12 mock receipts прочитаны. Повторный restore в существующий target отказан.
- Первая копия `…_a1` использована для 3 вымышленных QA-сессий, `…_a2` pristine.
  QA API business-ai-f00-qa:8017 и Vite4175 остановлены; обе БД/архива сохранены.
  **Все public fingerprints исходной рабочей БД совпали с backup. Никакие volumes,
  пользовательские записи, продуктовые исходники/формулы/миграции не удалялись/не менялись.**
- Новый D-04: default Alembic check exit 255 из-за TIGER/search_path; явный public scope
  PASS. Не запускать blind autogenerate/drop; исправление в H-04, не выполнено сейчас.
  D-01/02 Qwen и D-03 UI state остаются. Нет encryption/PITR/cluster DR, global quotas,
  полного workspace, full-city coverage, legal/brand/pilot approvals. Это локальный MVP.
- Дальше: владелец проверяет F-00 PR/принимает baseline и решает tag/следующую задачу.
  Плановый следующий шаг — BA-017-01, затем H-01, **только после отдельного указания**.

## BA-016 · сохранённые результаты реализации (не новый запуск)

- PR #15 merged: ea0354eafea2cc33cdcfc48a208262709bafd32d.
  Main синхронизирован ff-only, исходное дерево чистое.
- Ветка реализации feat/BA-016-comprehensive-testing; PR #16 уже merged (см. выше).
  BA-017/018 не начинать без указания владельца.

## Сделано

- Карта требований/рисков и реестр сценариев: TEST_MATRIX + docs/evals/BA-016-test-results.json.
  Новая pairwise-матрица 72 комбинаций (все пары 12 отраслей/6 городов/6 бюджетов),23 негативныхDTO.
- Hypothesis6.170.9 только dev:6 свойств/1550 examples, seeds16001–16006, shrinking.
  Fraction oracle для денег/BE; rent metamorphic; invalid money, coverage,
  normalization, confirmation reset. Extended выделен отдельным CI-шагом; без LLM/GPU.
- 61live-диалог/25 многотуровых,123 шага: два полных прогона настоящей Qwen;
 6 проблемных случаев×2 +4 финальных grounding-запроса. Raw результаты сохранены.
  qwen-v1 неизменён; v2 исправляет один ошибочный oracle (same city сохраняет confirm).
- Исправления: отрицательный бюджет/потерянные копейки/усечённая денежная цитата
  не превращаются в неверное изменение; clarification на сервере, не frontend patch.
  Prompt уточнён для decimal/сленга/альтернатив/формата. SQLAlchemy errors →safe503;
  UI различает Ollama timeout/invalid answer, явно называет demo-template кофейней.
- 15 новых browser fault/state сценариев (18mock с прежними), ещё 2real отраслевых
  пути (3real с прежним полным). Vite/Playwright поддерживают отдельный test API/URL.
  Real E2E пишет артефакты в output directory, не перезаписывает BA-015 примеры.
- demo manifest + read-only readiness; local benchmark. DEMO_GUIDE: запуск,
  отдельная БД, презентация, восстановление без удаления данных.
- README, TEST_MATRIX, LLM_EVALUATION (архив BA-005 сохранён), E2E_REPORT,
  SECURITY_TEST_REPORT, PERFORMANCE, DEMO_GUIDE,2 скриншота BA-016.

## Проверки

- API:352 PASS/72 SKIP без БД; отдельно 72Postgres/PostGIS PASS (92.18 с).
  Итого 459 именованных API/DB/Vitest проверок (453 обычных +6 property suites),
  1550generated examples отдельно; повторы не раздувают число сценариев.
- Vitest35 PASS. Browser18mock +3real PASS, real suite133.63 с.
  Реальные: пекарня/Казань/500 тыс, автосервис/Самара/10 млн/нет геоданных,
  кофейня/Казань/2 млн →walking/provider/finance/bank/PDFJSON/mock receipt.
- Реально скачанные PDF12 страниц/JSON502162 bytes: pypdf strict, кириллица,
  synthetic и отсутствие secret keys. Полный повторный visual QA всех страниц
  BA-016 не проводился; renderer не менялся. Два UI screenshots просмотрены/сохранены.
- Prek Ruff/format/strict mypy/pytest/ESLint/TS/Vitest PASS; build и Compose healthy
  db/api/web, HTTP smoke PASS. MapLibre large chunk warning остаётся.
- Readiness7/7 PASS, pinned OSM44157bdc…, graph a63822ae…, synthetic adf6964b….
  Новые большие датасеты/модели/платные API не загружались.

## Qwen и остаточные риски

- qwen3:4b-instruct-2507-q4_K_M, Q4_K_M, Ollama0.40.8,4096 ctx, seed42,temp0.
  RTX3050Ti4 GB:18%CPU/82%GPU, ~2362 MiBVRAM; Ollama2.833 GiBRAM (снимки, не лимиты).
- Initial54/61 диалогов,116/123 шага PASS. Final raw58/61,120/123;
  после отдельно записанного oracle adjudication59/61,121/123.
- Остались 2 устойчивые model errors: LLM-022 пропускает город при иностранной
  валюте; LLM-028 сохраняет «Козани». Повторы подтверждают. Обязателен review профиля.
  Только словесные суммы ещё зависят от семантики модели, не независимого parser.
- Нет независимого pentest, soak/concurrency SLA, Firefox/WebKit, legal review,
  глобальных квот/retention, реальной банковской интеграции. Это управляемое локальное
  демо, не готовность к публичному пилоту. Финансы/OSM — не рыночный прогноз.

## Окружение / дальше

- Рабочие volumes/данные сохранены, DATA_DEMO_ENABLED=true для проверенного демо.
  Isolated DB business_ai_eval_ba016 содержит только open/synthetic и вымышленные
  QA-сессии. API business-ai-ba016-eval:8016; Vite4174 использовался только для QA.
  Можно остановить эти 2 тестовых процесса, не удаляя БД/volumes.
- PR/CI BA-016 проверены, merged; roadmap утверждён, актуальный статус F-00 выше.
  Дальше только по разрешению владельца.
  Прежние BA-015 детали/источники/ограничения: REPORT_EXPORT.md, ADR-0011,
  docs/examples/BA-015-kazan-coffee.{pdf,json} и Git history.
