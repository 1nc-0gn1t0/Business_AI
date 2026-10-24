# Business AI — HANDOFF

## BA-014 · 24.10.2026 (МСК)

- PR #13 объединён: 3347d51f73dd45967453f2817f801286fc1d0f78.
  Main синхронизирован ff-only, исходное дерево чистое, main...origin/main=0/0.
- Ветка feat/BA-014-data-providers. Фактический HEAD/PR/CI — в итоговом отчёте.
  PR не объединять автоматически. BA-015 не начиналась.

## Реализовано

- app/data/{schemas,providers,importer}.py; app/api/data.py, main router.
  DataProvider Protocol/read/datasets + OSMProvider/SyntheticProvider.
  GHSLProvider/LicensedProvider — unavailable контракты, без фиктивных интеграций.
- Существующие MetricWithProvenance/DataOrigin/Bounds; nullable Indicator,
  качество/лицензия/даты/bbox/status/version, запрет смешения происхождения.
  OSM bbox counts по существующим PostGIS snapshots; rent/flow/demand missing.
- 0007_data_providers и ProviderDatasetRecord: immutable revision/SHA/document,
  история/active/imported_at, advisory lock/atomic swap, replay без rollback версии,
  конфликт прежней revision запрещён, валидация/проверка SHA при чтении.
- DATA_DEMO_ENABLED=false по умолчанию + явный mode=demo в каждом запросе.
  Выбор request-scoped, не меняет чужие сессии и предыдущие алгоритмы.
  API sources/policy/selection/{provider}/datasets/indicators, строгие DTO/ошибки.
- data/synthetic/coffee-kazan-v1.json — небольшой фиксированный авторский сценарий,
  CC0-1.0. Поток 1800, аренда 90000 RUB/месяц, покупки 90/день — только синтетика.
  Значения независимы, не рынок Казани/не доступное помещение/не прогноз прибыли.
- DataSources.tsx в карте/сравнении: явный real/demo/provider/version,
  provenance/пропуски/даты/ограничения/история; смена выбора убирает результат.
  Синтетика не переносится автоматически в scoring, walking или finance.
  Исправлено найденное реальным браузером мобильное переполнение таблицы.
- README/.env.example/compose, DATA_PROVIDERS.md, ADR-0010, USER_INTERFACE,
  synthetic README; API-типы сгенерированы из OpenAPI. Новых зависимостей нет.

## Настоящие API и локальная среда

- OSM kazan-centre data_version 44157bdc66965a6239c3470d459668cf362a0e355f76893febf4556f838a8447:
  23852 mapped POI, 819 mapped cafes; origin=open_data, ODbL-1.0,
  source OpenStreetMap via Overpass, osm_base=2026-10-22T20:27:36Z.
  Полнота картирования неизвестна, это не measured demand/traffic.
- Synthetic SHA adf6964b918eda73247a462f4be465d95d5d060580fa2493ef8294c9840708dd,
  revision coffee-kazan-v1, generated_at=2026-10-24T00:00:00Z,
  fixed-authored-scenario-v1, origin=synthetic/observed_at=null/not_applicable.
- Реальные HTTP-ответы (без токенов/персональных данных):
  docs/examples/BA-014-provider-indicators.json. Screenshots BA-014 отдельно.
- В текущем Compose API для проверки включён DATA_DEMO_ENABLED=true,
  набор импортирован операторским CLI. После recreate без явного env/.env flag
  снова false. Полное отключение без удаления данных — DATA_PROVIDERS.md.
- Миграция 0007 применена, db/api/web healthy, volumes/OSM/граф/согласия сохранены.
  Ollama/Qwen прежние, новые веса/внешние коммерческие API не подключались.

## Проверки

- pytest apps/api/tests/test_data_providers.py -q: 9 PASS (schema/provenance,
  запрет чужого origin/версии/неявного demo, воспроизводимый seed).
- Новые 5 PostgreSQL/API-тестов: общий контракт/count по SQL, missing/stale,
  outside/disable, GHSL/licensed unavailable, replay/conflict/history/tamper,
  стабильность BA-008/BA-013 при выборе demo.
- Все PostgreSQL/PostGIS integration: 65 PASS (78.22 s), включая migration/check/
  downgrade и прежние модули. Команда: docker compose --profile test run --no-deps
  --rm с read-only bind mounts актуальных app/tests/integration/migrations в db-tests.
  Первый targeted image build/run: 4 PASS; затем расширенный набор выше.
- npm --prefix apps/web test: 32 PASS, в том числе 3 DataSources mocked-API теста.
- npm --prefix apps/web run test:e2e: 3 mock Chromium PASS, без GPU/интернета/банка.
- BA010_REAL=1/BA010_ARTIFACT_DIR=test-results/ba014-regression: настоящий Qwen →
  profile → PostGIS → walking/scoring → finance/recalc → bank → consents/mock receipt →
  OSM indicators → явное demo/synthetic → real/clear: PASS, 26 s, без console errors,
  mobile width390 без overflow. Исторические скриншоты BA-013 не перезаписываются.
- prek run --all-files: Ruff/format/strict mypy/pytest/ESLint/TypeScript/Vitest PASS.
  Docker production build, healthy services, HTTP smoke PASS.
  Временные Docker Hub TLS timeouts устранены повтором; MapLibre large chunk warning прежний.
- Context7 docs fetch дал сетевую ошибку; валидация сверена с официальной Pydantic docs.

## Ограничения / следующий шаг

1. Проверить PR/CI BA-014; merge только по решению владельца.
2. GHSL/licensed не подключены: нужны проверенный набор/лицензия/договор.
3. Демо не отражает рынок; bbox сценария нельзя масштабировать на подрайон.
   Переход к другим источникам не является подтверждением коммерческой достоверности.
4. Промышленное подключение новых признаков в ranking/finance требует явного
   алгоритма/версии/правил смешения. В BA-014 они намеренно независимы.
5. UI snapshot, не подписка: обновление списка или версии убирает текущие показатели.
   Режим не сохраняется после reload. OSM history сохраняется в прежних таблицах.
6. BA-015 — только по отдельному разрешению. Банковская заявка остаётся mock.
