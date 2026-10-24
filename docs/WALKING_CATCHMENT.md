# BA-013: пешеходная сеть и catchment

`app/geo/walk_*` расширяет модульный монолит без новых пакетов, GPU, платного
маршрутизатора или сетевых запросов из пользовательского API. POI BA-006 и
исходный рейтинг BA-008 сохраняются. Решение — ADR-0009.

## Загрузка и воспроизведение

Источник: [OpenStreetMap](https://www.openstreetmap.org/copyright), ODbL-1.0,
публичный Overpass. Дорожный и POI snapshots независимы: даты/версии передаются
отдельно. Первая дорожная область — bbox WGS84 49.08,55.76,49.18,55.82 в Казани,
внутри POI bbox BA-006. Это часть города, не полное покрытие Казани.

```powershell
docker compose up --build --detach --wait --wait-timeout 180
$walkCache = Join-Path (Get-Location) 'data/osm'
New-Item -ItemType Directory -Force $walkCache | Out-Null
# Новое имя для каждой загрузки; существующие файлы не перезаписываются:
docker compose run --rm --no-deps --volume "${walkCache}:/osm" api python -m app.geo.walk_cli fetch --path /osm/kazan-walking-20261024.raw.json --slug kazan-centre --city Kazan --bbox 49.08,55.76,49.18,55.82
docker compose run --rm --no-deps --volume "${walkCache}:/osm:ro" api python -m app.geo.walk_cli import --path /osm/kazan-walking-20261024.raw.json
```

JSON + `.raw.manifest.json`: точный запрос/endpoint/bbox, исходный и сохранённый
SHA256, osm_base/fetched_at, normalization, лицензия/атрибуция. Это контроль
целостности, не цифровая подпись источника. Кеш вне Git. User/uid/changeset,
контакты и неиспользуемые теги удаляются. Node IDs, refs, версии/даты сохраняются.
Запрос получает highway ways, полные referenced nodes и restriction relations.
`remark`, неверные SHA/query, отсутствующие nodes, пустой/слишком большой граф
отклоняются. Ошибка не превращается в пустой успешный импорт. HTTPS endpoint
можно задать через --endpoint; автоматического обхода серверов/частых повторов нет.

Миграция 0006: walk_graphs/walk_edges. Импорт атомарный, advisory lock по slug,
одна активная версия. Replay того же snapshot/build/runtime идемпотентен,
старый osm_base не заменяет новый. Исторические графы сохраняются и доступны
по graph_version. Изменение build policy даёт новую версию для того же JSON.
Volumеs не удалять; откаты миграций тестируются в изолированных БД.

## Правила графа

- Вершина — OSM node ID, ребро — пара последовательных refs way. Пересекающиеся
  линии с разными IDs не соединяются по координатам/близости. Мосты/тоннели
  соединяются только по настоящим общим nodes, без ST_Node/геометрического слияния.
- Footway/pedestrian/path/steps и допустимые обычные дороги; motorway/trunk
  требуют явного foot-разрешения. Foot приоритетнее access. Private/no и
  неизвестные значения запрещаются. Допуск обычной дороги без foot=no —
  гипотеза по OSM-тегам, не доказательство отдельного тротуара/перехода.
- oneway:foot, foot:forward/backward задают направления. Автомобильные oneway
  и roundabout сами по себе не запрещают пешеходам обратное направление.
- Access/foot запреты, locked=yes и непроходимые/неизвестные node barriers
  исключают инцидентные сегменты. Gate без явного foot-разрешения исключён;
  bollard/cycle_barrier/entrance/kerb допускаются по пешему профилю.
- Construction/proposed, lifecycle abandoned/disused, area=yes и sidewalk=separate
  исключены; отдельный тротуар должен иметь собственную OSM-линию.
- Conditional access не интерпретируется по времени: объект исключён. Явные
  restriction:foot исключают участвующие ways целиком, поскольку turn-state
  automaton не реализован. Общие автомобильные turn restrictions не применяются.
- Сегменты с концом вне bbox исключены. Вычисляются слабосвязные компоненты.
  Максимальные по числу nodes считаются основными; остальные показываются,
  но не ранжируются численно. Это фильтр качества, не доказательство изоляции.

Это не полноценный навигатор: нет проверки входов, многоэтажных помещений,
расписаний, текущих ремонтов, уклонов/ширины и wheelchair-маршрутов.
Правила сверены с [access](https://wiki.openstreetmap.org/wiki/Key:access),
[oneway:foot](https://wiki.openstreetmap.org/wiki/Key:oneway:foot),
[barrier](https://wiki.openstreetmap.org/wiki/Key:barrier) и
[Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL).

## Расчёт и качество

Bounded directed Dijkstra на heapq загружает локальные рёбра в прямом радиусе
budget + max_snap + 5 м. Стоимость — ST_Length(geography) в метрах WGS84.
Старт и POI привязываются к одному ближайшему допустимому ребру, tie-break edge_id,
независимо от достижимости (не выбирается более удобная компонента).
Виртуальное начало внутри ребра и его направления учитываются, включая частичные
отрезки до конца бюджета. Выход — достижимые интервалы рёбер, **не polygon buffer**.

Стоимость = соединитель старта + путь по графу + соединитель POI. Соединители
по прямой явно модельные, max_snap=30 м по умолчанию (0 оставляет совпадение с
сетью с численным допуском 1 мм). Это не проверенные входы/проходы через стены или
реки. Только наземные non-bridge/non-tunnel рёбра layer=0 принимают соединитель;
мосты/тоннели могут участвовать в маршруте через настоящие nodes.

Привязка ST_Transform/ST_LineLocatePoint в локальной UTM (Казань EPSG:32639).
Выход EPSG:4326, longitude/latitude. Доли коротких двухточечных рёбер линейно
интерполируются в WGS84, стоимость взвешена geography; это небольшое геометрическое
приближение, не 3D-маршрут. Расстояния округляются до мм.

fully_covered: budget + snap + 1 м помещаются в общий bbox POI/графа. Это не полнота
картирования. Выход бюджета за bbox или неосновная компонента → partial, counts —
известные нижние границы, score null. No route не доказывает физическую недоступность.
graph_unavailable/outside_coverage/no_network_access/resource_limit не заменяются
прямыми маршрутами; UI показывает прочерк вместо якобы измеренного нуля.

## API и scoring

- GET `/api/v1/geo/{slug}/walking-graph?graph_version=…` → metadata или null.
- POST `…/{slug}/catchment`: `{longitude,latitude,distance_m:600,max_snap_m:30,
  data_version?,graph_version?}` → CatchmentResult/GeoJSON/counts/версии/ограничения.
- POST `…/{slug}/walking-rankings`: `{ranking:<RankingRequest>,max_snap_m:30,
  graph_version?}` → `{baseline,network,catchments:{candidate_id:…}}`.

Budget 50–2000 м (целые), snap 0–100, до 20000 локальных рёбер и 5000 POI.
GiST geometry/geography + graph PK; импорт батчами 500 и ANALYZE. SQL/API read-only.
Неизвестная версия графа → 409 walking_graph_version_not_found, смена POI →
прежний geo_dataset_changed; неправильный ввод → 422. DTO — OpenAPI/api-schema.d.ts.

Прежний `/rankings` остаётся geodesic_straight_line / osm-cohort-minmax-v1.
Новый opt-in osm-foot-cohort-minmax-v1 использует те же веса/категории/min-max,
но counts/nearest берёт из catchment. distance_method и policy/fingerprint отдельные.
Плотность конкурентов на км² круга в сетевом режиме null: площадь не вычислялась.
Для score нужны ≥2 покрытых зоны на основной компоненте и наблюдаемые активные
сигналы. Веса не перенормируются из-за пропусков. Разница — пути/связность/привязка
и состав сопоставимой группы, не спрос/прибыль. Финансы и банковские продукты независимы.

MapLibre: линии, POI, старт, настройка budget/snap, выбор зоны/клик/координаты.
Явный поиск во внутренней области графа сужает окно кандидатов на 1/6 bbox с каждой
стороны. Это UI-пресет окна поиска, не пешеходный полигон или гарантия покрытия.
Все проверки/вычисления остаются на сервере; исходный поиск сохранён.

## Настоящие данные Казани: 24.10.2026, МСК

OSM base 23.10 21:04:36Z = 24.10 00:04:36 МСК. Кеш 7.94 MB.
41640 рёбер, 36496 nodes, 612 компонент, основная 32135 nodes. Исключены
1439 ways, 3191 barrier-сегмент, 1720 граничных сегментов.
Graph a63822aec055fe6fc4190edd6ed424ffa9bbf0ef2657b6fe970b3232d91ce045;
data c688d0dfd37dcf8fbef4536321271e85f335f9eec85cbc2fe75efed4b71a827e.

600 м, snap≤30 м. POI — features, не уникальные компании:

| Старт lon,lat | POI прямая / сеть | Пример | Прямая / сеть+соединители |
|---|---|---|---|
| 49.119,55.788 | 1089 / 569 | «Вкусно — и точка» | 126.2 / 190.1 м |
| 49.132,55.789 | 636 / 159 | Библиотека КГМА | 169.9 / 288.5 м |
| 49.155,55.788 | 547 / 308 | Кинотеатр «Мир» | 419.1 / 518.3 м |

Пять зон: score прямая→сеть = 82.38→null (компонента 8 nodes), 27.70→38.72,
65.42→87.89, 15.76→16.67, 83.64→38.89. Это сравнение методик, не бизнеса.
Запросы/компоненты: examples/BA-013-kazan-catchments.json. В отчёте геометрии/POI
сокращены до 20/10, counts из полных ответов. Повтор: `python scripts/eval_walking.py
--output local-walking-eval.json` (этот локальный файл не коммитить).

Первые catchments: 192–600 мс, 1885–2539 загруженных рёбер, 522–784 посещённых nodes;
сравнение пяти зон около 0.7 с на прогретой БД. Это измерения, не SLA. GPU не используется.
Неограниченный in-memory cache не добавлялся: рядом работает Ollama, версии проще
изолировать индексированными запросами. Предварительно вычислены компоненты.

Тесты интеграции используют явно синтетическую контролируемую топологию;
это не проверка настоящего OSM. Реальные HTTP/browser проверки — отдельные,
через Qwen/Compose и загруженный снимок. Итоги и команды — HANDOFF.
