# Business AI — HANDOFF

## Состояние на 22.10.2026

- PR #5 BA-005 объединён, merge 4c34f1389633399f388021bcc5215f600d2b79df.
  Перед BA-006 main синхронизирован с origin/main, дерево было чистым.
- BA-006 реализована в codex/BA-006-osm-postgis от 4c34f13. Итоговый коммит,
  PR и статус GitHub CI после push — в итоговом сообщении. Не объединять автоматически.
- BA-007 не начиналась. LLM-модуль BA-005 не изменён.

## Сделано в BA-006

- app/geo: сменный OSMProvider/OverpassProvider, operator-only CLI fetch/import,
  проверяемый snapshot с manifest, точным bbox/запросом, URL, OSM/fetch датами,
  исходным и нормализованным SHA256. poi_minimal_v1 удаляет редакторские идентификаторы
  и ненужные/контактные теги, не меняет геометрию/OSM ID/version/timestamp.
- Миграция 0004_osm_geo: geo_datasets, geo_pois, geo_districts, GiST/GIN,
  geometry(POINT/ MULTIPOLYGON,4326), PostgreSQL provenance/версии отдельно от метрик.
- Атомарный полный snapshot update, advisory lock на slug, идемпотентность,
  защита от старых snapshots и случайной пустой замены. История не удаляется.
- GeoJSON API /api/v1/geo: datasets, {slug}/pois, districts, categories;
  bbox/category/радиус в метрах/район, data_version для безопасной пагинации.
  Ограничения запросов и параметризованный SQL. HTTP не вызывает Overpass/LLM.
- Корректные null/диагностика для неизвестных имён/геометрии. Way/relation POI —
  явно обозначенный OSM bbox center. Административные полигоны собираются только
  из полных замкнутых линий, неполные/вложенные relation не достраиваются догадками.
- README, GEO_DATA.md, ADR-0003; две небольшие реальные OSM fixtures с ODbL
  и manifest для офлайн CI. Новых Python-зависимостей нет.

## Реальные локальные данные и проверки

- Источник: https://overpass-api.de/api/interpreter, OpenStreetMap / ODbL-1.0,
  © OpenStreetMap contributors. Bbox 49.05,55.70,49.25,55.85, часть Казани.
  osm_base 2026-10-22T20:27:36Z. data_version
  44157bdc66965a6239c3470d459668cf362a0e355f76893febf4556f838a8447.
- В БД приложения активен kazan-centre: 23852 POI, 8 административных полигонов.
  17 центров вне bbox исключены; 9540 POI без имени сохранены с null.
  Кеш data/osm/kazan-20261022.raw.json и .raw.manifest.json исключён из Git.
- В отдельной временной БД импорт 2.739 s, replay 0.006 s, три таблицы с индексами
  11837440 bytes, Python peak RSS 164.4 MiB. EXPLAIN ANALYZE подтвердил GiST:
  bbox 0.427 ms, radius 12.662 ms, район 6.585 ms. Это один запуск, не SLA.
- Реальные HTTP bbox/category/radius/district/districts и nginx proxy: 200,
  около 32–94 ms в локальной проверке; существующий scripts/smoke.ps1 PASS.
- pytest apps/api/tests -q: 114 passed, 37 skipped (БД отдельно).
- docker compose --profile test run --build --rm db-tests: 37 passed.
  Миграции upgrade/check/downgrade, реальные OSM spatial queries, provenance,
  cache replay, пустой/старый snapshot, rollback, удаление из активного слоя,
  конкурентный импорт, неполные границы; прежние conversation tests PASS.
- prek --all-files: Ruff lint/format, strict mypy, pytest, ESLint, TypeScript PASS.
  npm --prefix apps/web run build PASS. CI использует cached real fixtures,
  не нуждается в Overpass/Ollama/GPU. Фактический статус Actions — в итоговом отчёте.
- Docker и localhost проверялись вне песочницы. Для локального pytest использован
  отдельный PYTEST_DEBUG_TEMPROOT: старый системный pytest temp недоступен.
  Системные ACL/настройки не менялись. Удалялись только созданные временные test-БД;
  существующие данные/volumes сохранены.

## Ограничения и продолжение

- Покрытие ограничено bbox и выбранными тегами, не весь город/весь OSM.
  Boundary bbox в Overpass выбирает member nodes: охватывающий район может отсутствовать.
  Полигон может выходить за POI coverage. Пустой список не означает отсутствия бизнеса.
- OSM timestamp не доказывает физическую актуальность организации. Через 30 дней
  stale=true — технический сигнал, не гарантия качества. Возможны дубль node+way,
  пропуски, устаревшие теги. Дистанции прямые, без дорожного catchment.
- Нет трафика/спроса/аренды/дохода, synthetic или банковских условий.
  Большие территории требуют другого импорта (PBF), retention и тайлов.
- Обновление: новые fetch + import по GEO_DATA.md; работа без сети — import кеша.
  Администратор должен следить за свежестью, автообновление не настроено.
- Следующий шаг — review PR BA-006 владельцем. После разрешения — BA-007
  (candidate generation), без автоматического перехода/слияния.
