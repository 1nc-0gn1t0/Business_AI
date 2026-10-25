# Business AI — HANDOFF

## Post-MVP planning · 25.10.2026 (МСК)

- PR [#16](https://github.com/1nc-0gn1t0/Business_AI/pull/16) объединён 25.10.2026:
  main `09f2f7d8f8fd7260b72e57b42e51758eb6ada488`, fetch/ff-only, divergence 0/0,
  исходное дерево чистое. [CI merged main](https://github.com/1nc-0gn1t0/Business_AI/actions/runs/40208572389) success.
- Ветка документации: `codex/post-mvp-master-roadmap`. Фактический commit/PR/CI
  текущего planning PR — в итоговом сообщении; не объединять автоматически.
- Созданы [POST_MVP_ROADMAP](roadmap/POST_MVP_ROADMAP.md),
  [QUALITY_GATES](roadmap/QUALITY_GATES.md), [RISK_REGISTER](roadmap/RISK_REGISTER.md).
  43 планируемых блока с зависимостями, критериями, оценками/рисками; сроки BA-017/018,
  архитектурные предложения и внешние pilot gates. README содержит ссылку.
- Сверены код/API/ORM/миграции/ADR/CI и BA-016 evidence. Подтверждены узкая отрасль/город,
  потеря части UI state после reload, отсутствие live AnalysisRun persistence и
  глобальных resource caps; DB transaction во время inference — риск, impact не измерен.
- Read-only API/PostGIS/readiness работают; новые live Qwen/E2E ради плана не запускались.
  Официальные VTB references доступны частично в поисковом представлении; прямой browser
  TLS не прошёл, визуальные brand tokens/права не подтверждены, предупреждения не обходились.
- **План требует утверждения. Никакие F/H/U/UI/Q, BA-017/018 не выполнены и не начаты.
  PROJECT_PLAN, исходный код, алгоритмы, модели и данные не менялись.**
- После разрешения: F-00 baseline → BA-017-01 protocol/recruitment человеком → H-01
  bounded triage; затем BA-017/018 до 31.10. Доступность 23 ч + до 4 ч резерва,
  реальные участники и вычитка требуют действий владельца; без интервью BA-017 partial.
- Проверки текущего planning PR: 43 уникальные карточки, все 15 атрибутов,
  зависимости без циклов, локальные Markdown-ссылки в 5 файлах — PASS;
  `git diff --check` — PASS. `uv tool run --from prek==0.5.4 prek run --all-files`
  (с отдельным PYTEST_DEBUG_TEMPROOT) — все 7 hooks PASS: Ruff/format/mypy/pytest,
  ESLint/TypeScript/Vitest. `scripts/demo_ready.py --require-demo-data` — 7/7 PASS,
  без inference. Новые live Qwen/DB integration/browser/performance не запускались:
  изменена только документация; исторические результаты ниже не засчитывались заново.

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
- PR/CI BA-016 проверены, merged; следующий шаг — утверждение Post-MVP roadmap.
  Дальше только по разрешению владельца.
  Прежние BA-015 детали/источники/ограничения: REPORT_EXPORT.md, ADR-0011,
  docs/examples/BA-015-kazan-coffee.{pdf,json} и Git history.
