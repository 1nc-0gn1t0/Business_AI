# Business AI — HANDOFF

## BA-013 · 24.10.2026 (МСК)

- PR #12 объединён: 654cc8970b037706bc2d978df44ca4dd991e971d.
  Main синхронизирован ff-only, дерево перед началом чистое.
- Ветка codex/BA-013-walking-catchment. Фактический HEAD/PR/CI — в итоговом отчёте.
  PR не объединять автоматически. BA-014 не начиналась.

## Реализовано

- Независимый OSM road snapshot fetch/load/import CLI app.geo.walk_cli;
  app/geo/walk_import.py, walk_graph.py, walking.py, walk_ranking.py, DTO.
  Миграция 0006_walking_graph: walk_graphs/walk_edges + GiST geometry/geography.
  История/атомарная активация/advisory lock/replay, SHA/query/time validation,
  минимизация OSM editor/contact tags. POI BA-006 не перезагружаются.
- Топология только по общим OSM node IDs, сегмент каждой пары refs, directions
  oneway:foot/foot:forward/backward, conservative access/barriers/conditional policy.
  Пересечение мостов не создаёт связи. Ограниченные модельные соединители к
  одному ближайшему наземному ребру; никаких fallback прямых маршрутов.
- Bounded directed Dijkstra на CPU, частичные достижимые интервалы рёбер,
  POI counts/прямые и сетевые дистанции/unknown cases/coverage/component quality.
  WGS84 geography lengths, UTM snap fractions, GeoJSON EPSG:4326.
- GET …/walking-graph, POST …/catchment, POST …/walking-rankings.
  Новый opt-in ответ baseline/network/catchments. Веса/min-max BA-008 сохранены,
  новые метод/версия/policy fingerprint. Неосновные компоненты/плохое покрытие
  не получают численный score; плотность по площади в сетевом режиме null.
  Прежний /rankings остаётся по прямой. Банк/финансы/LLM не определяют метрики.
- React Walking + GeoMap: budget/snap, выбор точки кликом/зоной/координатами,
  достижимые линии/POI/старт, таблицы/ограничения/версии, отдельное сравнение.
  Явный новый поиск зон во внутреннем окне графа, исходный поиск сохранён.
  Устаревшие результаты не подмешиваются к новой группе.
- README, WALKING_CATCHMENT.md, GEO_DATA/ZONE_RANKING/USER_INTERFACE, ADR-0009,
  scripts/eval_walking.py и компактный реальный отчёт BA-013-kazan-catchments.json.
  Исторические скриншоты BA-012 сохранены; новые артефакты BA-013 отдельно.

## Настоящие данные и измерения

- Overpass https://overpass-api.de/api/interpreter, ODbL/© OSM contributors.
  bbox 49.08,55.76,49.18,55.82 внутри POI-области Казани. Кеш 7.94 MB, вне Git:
  data/osm/kazan-walking-20261024.raw.json и .raw.manifest.json.
  Source base 2026-10-23T21:04:36Z (24.10 00:04:36 МСК).
- 41640 рёбер, 36496 nodes, 612 weak components, основная 32135 nodes.
  Build osm-foot-node-topology-v2-components, algorithm osm-foot-dijkstra-segments-v1.
  Graph a63822aec055fe6fc4190edd6ed424ffa9bbf0ef2657b6fe970b3232d91ce045.
  Data c688d0dfd37dcf8fbef4536321271e85f335f9eec85cbc2fe75efed4b71a827e.
- При 600 м/snap30 три точки дают POI прямая→сеть: 1089→569, 636→159, 547→308.
  Примеры: «Вкусно — и точка» 126.2→190.1 м; библиотека КГМА 169.9→288.5 м;
  кинотеатр «Мир» 419.1→518.3 м (сеть включает модельные соединители).
- Фиксированная группа 5 зон: 82.38→null (компонента 8 nodes), 27.70→38.72,
  65.42→87.89, 15.76→16.67, 83.64→38.89. Разные метод/группа/привязка,
  не изменение спроса/прибыли. UI-пресет создаёт свою явно новую группу.
- Первые catchments 192–600 мс, 1885–2539 локальных рёбер, 522–784 visited nodes.
  Сравнение 5 зон около 0.7 с на прогретой БД; не SLA. GPU не используется,
  новые модели/пакеты/сервисы не устанавливались в приложение.

## Проверки

- pytest test_walking.py + test_walk_snapshot.py: bounded Dijkstra/directions,
  access/barriers, disconnected crossings/partial edges/reproducibility/10k-chain,
  snapshot hash/query; проходят также через prek. Новых unit cases: 16.
- docker compose --profile test run --build --rm db-tests: 60 PASS.
  Миграция/check/downgrade + прежние модули + 4 новых controlled topology tests.
  Дополнительные boundary/foot restriction assertions проверены целевым повтором.
  Синтетическая тестовая топология не выдана за настоящий OSM.
- npm --prefix apps/web test: 29 PASS, включая 3 Walking mocked-API теста.
- npm --prefix apps/web run test:e2e: 3 mock Chromium PASS без GPU/модели/банка.
- BA010_REAL=1 + BA010_ARTIFACT_DIR=test-results/ba013-regression: настоящий
  Qwen→profile→PostGIS zones→walking map→finance/recalc→bank→consent→mock receipt,
  затем UI-поиск внутри графа и сетевое сравнение: PASS, без console/page errors.
  Новый тест не перехватывает реальные API. Screenshots/verification BA-013 в docs.
- prek run --all-files: Ruff/format/mypy/pytest/ESLint/TypeScript/Vitest PASS.
  Compose build/health и HTTP smoke PASS; прежний MapLibre large-chunk warning.
  Volumes/POI/согласия/заявки сохранены, системные настройки не менялись.
- find-docs/Context7 нашёл PostGIS, docs fetch дал сетевую ошибку; сверка по
  официальным PostGIS docs/OSM Wiki. В код не добавлены сторонние routing библиотеки.

## Ограничения и следующие действия

1. Проверить PR/CI BA-013; merge только по решению владельца.
2. OSM неполон. Нет пути/неосновная компонента не доказывают физическую недоступность.
   Полнота bbox не равна полноте картирования. Counts — features, не компании/люди.
3. Соединители по прямой модельные, не проверенные входы/проходы через барьеры;
   нет temporal/turn-state/indoor/3D/wheelchair навигации и точного полигона catchment.
   Для промышленного использования нужны расширение покрытия и полевая проверка.
4. Каталог/consent/mock остаются демонстрационными (BA-011/012), настоящего банка нет.
5. BA-014 — только по отдельному разрешению. Веса/финансы/банк не переучивались.
