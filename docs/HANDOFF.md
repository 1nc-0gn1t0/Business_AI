# Business AI — HANDOFF

## H-02 · input/resource limits · 26.10.2026 (МСК)

- PR [#19](https://github.com/1nc-0gn1t0/Business_AI/pull/19) merged
  `2026-10-25T22:02:19Z`, main `c3c8c73d92c1f63664b440faee62d69c9c5fce2e`.
  Fetch/ff-only, divergence0/0, чистое дерево до начала; ветка
  `codex/H-02-api-resource-limits`. Exact HEAD/новый PR/CI — в финальном отчёте/PR.
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
