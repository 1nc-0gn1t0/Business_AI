# Business AI — HANDOFF

## BA-015 · 25.10.2026 (МСК)

- PR #14 объединён: 1cc82c401bc755964dd420e24044d0916a82c0c9.
  Main обновлён ff-only, исходное дерево чистое, main...origin/main=0/0.
- Ветка feat/BA-015-report-export. Фактический HEAD/PR/CI — в итоговом отчёте.
  PR не объединять автоматически. BA-016 не начиналась.

## Сделано

- reporting/{schemas,service,pdf,limits}.py + api/reports.py: ReportRequest с DTO
  прежних сервисов/fingerprints, проверка owner/profile/version и реконструкция
  BA-008/009/011/013/014 сервером. Нет доверия присланным итоговым цифрам/summary/PDF.
- 0008_analytical_reports и ReportRecord: owner UUID, immutable JSONB snapshot/SHA,
  готовые PDF bytes/SHA, версия профиля/дата. Два формата из одного ReportSnapshot.
  Профиль проверяется под существующей блокировкой conversation; history не удаляется.
- Typed POST …/reports, GET …/{id}, GET …/{id}/snapshot,
  GET …/{id}/file?format=pdf|json. Guest token только в header; чужие ID →404.
  Download filename ASCII UUID, Content-Type, private/no-store/nosniff, общий SHA.
  Проверка целостности/актуальности, explicit historical=true; demo disable не обходится.
- ReportLab 4.5.1 (runtime), pypdf 6.21.2 (dev), lock/requirements обновлены.
  Встроен DejaVu Sans с полным LICENSE; русский/₽ без внешнего font download.
- PDF: проект/зоны/выбор/факторы/схема/источники, walking, три финсценария/график/
  вводные/чувствительность/формулы, банк, явные ProviderResult, резюме/ограничения.
  Нет тайлов/внешних PDF/LLM вызовов. Synthetic отдельно и в каждой строке.
- JSON сохраняет полные типизированные результаты/геометрии/версии/источники,
  provenance_rules/metric_units. В PDF только top8 walking-категорий с явной ссылкой
  на полный JSON; baseline BA-008 не подменяется сетевым score.
- React ReportExport + lifecycle callbacks Finance/BankProducts/Locations/DataSources:
  текущие посчитанные результаты, подготовка, два скачивания, блокировка после edits.
  Изменение поисковых весов очищает прежний анализ. Нет mock lead side effects.
- README, REPORT_EXPORT.md, USER_INTERFACE, ADR-0011, примеры/скриншоты BA-015.
  Старые BA-014 артефакты реальный тест больше не перезаписывает.

## Реальный пример

- docs/examples/BA-015-kazan-coffee.pdf: 12 страниц, 59912 bytes.
- docs/examples/BA-015-kazan-coffee.json: 502171 bytes.
- Report UUID 9b2fa2b1-4c9f-49a2-8a82-3834d8a5bdd0, profile v3,
  created_at=2026-10-25T13:08:26.492183Z (16:08:26 МСК).
- Snapshot SHA c50c1dc9525d7f1ca10f601375fd124d63eeb4d2d697645a67e56b0a48e85ad9.
  PDF SHA 07b30d9fd405c923b7d8f4dccfd0ffa4b713d610489742919a279bdf359ff3d2.
- Кофейня/Казань/2 млн ₽: OSM 44157bdc… и настоящий walking graph a63822ae…,
  5 зон; ручная walking-точка 49.119,55.788, 600 м, 569 reachable POI.
  Это не фактический вход в выбранную зону и не доказательство спроса.
- Финансовые допущения: 1.8 млн ₽ старт, 200 тыс ₽ остаток модельного бюджета,
  операционный результат -50 тыс /265 тыс /608200 ₽/месяц. Не прибыль/cash flow.
  Сценарная аренда 100000 ₽ из пользовательского редактирования независима от
  SyntheticProvider rent 90000 ₽; origin/provenance сохранены раздельно.
- Банковский каталог демонстрационный, credit_decision=not_assessed. В банк ничего
  не отправлено экспортом. В JSON нет guest token/истории переписки/lead contacts.
- Скриншоты docs/screenshots/BA-015-report-export{,-mobile}.png и verification.json.

## Проверки

- pytest tests/test_reporting.py: 2 PASS — структура JSON/PDF, кириллица/₽,
  одинаковые байты при фиксированном снимке, отсутствие гостевых секретов.
- 5 новых PostgreSQL/API-тестов: один снимок/финансовая независимая сверка,
  повторное чтение, авторизация/изоляция, no lead consent, changed inputs/profile,
  historical/integrity, partial/body bound, OSM/bank, synthetic/disable.
- Полный PostgreSQL/PostGIS набор: 70 PASS (78.35 с), включая migration/check/downgrade.
  docker compose --profile test run --no-deps --rm с read-only mounts актуальных
  app/tests/integration/migrations в db-tests. Целевой image build/run: 5 PASS.
  После добавления typed snapshot endpoint: целевой тест повторно PASS.
- Frontend: 35 тестов, в том числе 3 новых ReportExport (mock API).
  npm --prefix apps/web run test:e2e: 3 mock Chromium PASS.
- BA010_REAL=1 + BA010_ARTIFACT_DIR=test-results/ba015-regression: настоящий Qwen →
  профиль → PostGIS → walking → finance/recalc → bank → explicit synthetic provider →
  preparation → PDF/JSON browser downloads → stale rent/block → прежняя mock-заявка:
  PASS, последний 28.6 с, без console/page errors, 390px без overflow.
- Все 12 страниц PDF отрендерены Poppler и просмотрены; обрезаний/наложений нет.
  Отдельно проверены проект/финансы/синтетика/формулы и нумерация. Промежуточные PNG
  в ignored tmp/pdfs. После визуального QA убраны почти пустые хвостовые страницы.
- prek run --all-files: Ruff/format/strict mypy/pytest/ESLint/TS/Vitest PASS.
  Docker builds/healthy services/HTTP smoke PASS; MapLibre large-chunk warning прежний.
- find-docs/Context7 не ответил (fetch failed); сверка ReportLab API/лицензии шрифта
  по официальным docs. Навык pdf применён с artifact marker и visual QA.

## Ограничения / дальше

1. Проверить PR/CI BA-015. Merge только по решению владельца.
2. Это аналитический snapshot, не объявление о помещении/прибыль/одобрение кредита.
   Нет платных сервисов/реальной банковской передачи. GHSL/licensed по-прежнему unavailable.
3. UI держит текущий подготовленный ID в памяти: после reload нужна новая preparation;
   исторические IDs доступны владельцу по API. Финансовые локальные edits отслеживает UI.
4. Лимиты: body128KiB/snapshot4MiB/PDF3MiB/40pages/20reports per conversation,
   checks20/30s (не hard preemption), SQL5s. Для публичного пилота нужны общие квоты,
   retention/удаление/нагрузочные проверки. Tagged PDF/PDF-A/скринридер не сертифицированы.
5. PDF metadata CreationDate=2000 invariant, фактическая дата на страницах/в JSON.
   Менять renderer/ReportLab/font — с новой версией. Денежные DTO сохраняют Decimal.
6. Локальный Compose использует DATA_DEMO_ENABLED=true для реального теста;
   default false, существующие OSM/volumes/Ollama/согласия сохранены.
7. BA-016 — только по отдельному разрешению.
