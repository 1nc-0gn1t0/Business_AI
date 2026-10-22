# BA-006: OSM/PostGIS — запуск, обновление и API

Геослой содержит настоящие OSM POI и административные границы. Аналитические
показатели, ранжирование и интерактивный frontend здесь не реализуются.
Решение: [ADR-0003](adr/ADR-0003-osm-snapshots.md).

## Загрузка и воспроизводимый импорт (Windows/PowerShell)

Из корня репозитория, с работающим Docker Desktop:

```powershell
docker compose up --build --detach --wait
$cacheDir = Join-Path (Get-Location) 'data/osm'
New-Item -ItemType Directory -Force $cacheDir | Out-Null
$snapshotName = 'kazan-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.raw.json'
docker compose run --rm --no-deps --volume "${cacheDir}:/osm" api python -m app.geo.cli fetch --slug kazan-centre --city Kazan --bbox 49.05,55.70,49.25,55.85 --output "/osm/$snapshotName"
docker compose run --rm --no-deps --volume "${cacheDir}:/osm:ro" api python -m app.geo.cli import --snapshot "/osm/$snapshotName"
```

Fetch создаёт JSON и соседний файл `.raw.manifest.json`. Вместо исходного сетевого
ответа сохраняется минимизированный JSON Overpass: редакторские идентификаторы,
контактные и неиспользуемые теги удаляются; координаты/OSM версии/даты не подменяются.
Manifest содержит оба SHA256, точный запрос, bbox, источник и даты.
Large caches исключены из Git. Два небольших реальных snapshot для CI — в
apps/api/tests/integration/fixtures, с отдельной атрибуцией и manifest.

Повторный import **того же файла** не создаёт дублей. Для обновления повторите
fetch с новым именем, затем import. Полная новая выборка заменяет активную версию
целиком, поэтому удалённые/перетегированные объекты не остаются в текущем слое.
Старые версии сохраняются в БД; автоматической очистки истории нет.

Для другой территории задайте другой slug, city и bbox; порядок CLI bbox:
**west,south,east,north**. В Overpass запросе порядок другой — CLI преобразует его.
Нельзя обновить существующий slug другим bbox/фильтром или более старым snapshot.
Историческая воспроизводимость обеспечивается кешем; повторная сетевая загрузка
заведомо может содержать новые редактирования OSM.

При 429/недоступности Overpass дождитесь восстановления или используйте кеш.
Можно явно задать другой совместимый публичный/собственный HTTPS endpoint через
`--endpoint`; автоматического обхода серверов/агрессивных повторов нет.
Частичный ответ с remark отклоняется. Пустой набор требует осознанного
`--allow-empty`; ошибка импорта откатывает транзакцию. Проверяйте diagnostics
и сохранённый исходник перед такой заменой. БД приложения/volumes не удаляются.

## API для будущей карты

OpenAPI: http://localhost:8000/docs. Эти read-only endpoints доступны также через
nginx `/api/` на web-порту. Данные читаются из локальной БД без вызова LLM/Overpass.

| GET | Назначение |
|---|---|
| /api/v1/geo/datasets | Активные наборы, покрытие, версии, даты и диагностика |
| /api/v1/geo/{slug}/pois | GeoJSON Point FeatureCollection, пространственные фильтры |
| /api/v1/geo/{slug}/districts | GeoJSON MultiPolygon, до 100 границ; truncated при превышении |
| /api/v1/geo/{slug}/categories | Доступные key:value категории и число OSM features |

```powershell
Invoke-RestMethod 'http://localhost:8000/api/v1/geo/datasets'
Invoke-RestMethod 'http://localhost:8000/api/v1/geo/kazan-centre/pois?bbox=49.115,55.785,49.12,55.79&category=amenity:cafe&limit=100'
Invoke-RestMethod 'http://localhost:8000/api/v1/geo/kazan-centre/pois?longitude=49.117&latitude=55.788&radius_m=500&category=amenity:cafe'
Invoke-RestMethod 'http://localhost:8000/api/v1/geo/kazan-centre/districts'
Invoke-RestMethod 'http://localhost:8000/api/v1/geo/kazan-centre/pois?district_id=2133462&category=amenity:cafe'
```

Фильтры можно сочетать (пересечение). Нужен bbox, полный набор
longitude/latitude/radius_m либо district_id. Допустимы limit=1…500 и offset=0…10000.
Возвращаются стабильный feature ID `node/…`, OSM ID/type/version, observed_at,
реальное имя или null, категории/теги, representation и distance_m (только для radius).
Порядок: расстояние при radius, затем OSM type/id. Используйте next_offset и
dataset.data_version: для offset>0 передайте data_version, иначе 422. При замене
набора будет 409 geo_dataset_changed; перечитайте слой с первой страницы.

404 geo_dataset_not_found — территория ещё не импортирована; 404 geo_district_not_found —
такой границы нет в текущей версии; 422 invalid_geo_query — фильтр/лимит неверен;
503 database_unavailable — БД недоступна. Сырые SQL/пароли не возвращаются.

## Происхождение и ограничения

Каждый слой возвращает origin=open_data, OpenStreetMap via Overpass API, URL,
ODbL-1.0, © OpenStreetMap contributors, osm_base, fetched_at, imported_at,
data_version, bbox, diagnostics и limitations. observed_at объекта — время его
последнего редактирования в OSM, не проверка действующей организации.
stale=true после 30 дней от osm_base — технический сигнал, не обещание свежести до 30 дней.
Для карты требуется видимая атрибуция и ссылка на ODbL: [правила OSM](https://www.openstreetmap.org/copyright).

- Покрытие POI — только сохранённый bbox, не весь город. Границы relation выбираются
  по member nodes внутри bbox: охватывающий район может отсутствовать в малой выборке.
  Расширьте bbox/создайте подходящий набор; границы не дорисовываются.
- Административный полигон может выходить за покрытие POI. Поэтому фильтр по району
  возвращает лишь загруженные POI, а не полный перечень организаций района.
- Node — точка OSM; way/relation — bbox center, не вход и не полигон здания.
  Центры вне покрытия и некорректные/неполные геометрии пропускаются с диагностикой.
- Пустой список не означает отсутствие конкурентов. OSM node+way могут описывать
  одну организацию; counts — число OSM features, не число уникальных бизнесов.
- Радиус — геодезические метры по прямой, не пешеходный catchment BA-013.
- Коммерческих метрик нет. Трафик, спрос, аренда, выручка не выводятся из числа POI.

## Фактическая локальная проверка 22.10.2026

Казань, bbox 49.05,55.70,49.25,55.85; upstream osm_base 2026-10-22T20:27:36Z.
Исходный ответ около 12.4 MB, 23877 элементов. Импортированы **23852 POI и 8
административных полигонов** (семь районов Казани и соседняя административная граница).
17 POI с центром вне bbox пропущены; 9540 объектов без имени сохранены с null.
Локальный data_version этого snapshot:
44157bdc66965a6239c3470d459668cf362a0e355f76893febf4556f838a8447
(это исходный локальный кеш normalization=none; новые fetch минимизируют поля).

В отдельной временной БД на том же Docker/PostGIS:

| Проверка | Измерение |
|---|---|
| Импорт после применения миграций | 2.739 s |
| Повторный импорт того же snapshot | 0.006 s, тот же ID |
| Три geo-таблицы с индексами | 11837440 bytes |
| Пиковый RSS Python-процесса | 164.4 MiB |
| EXPLAIN ANALYZE bbox | 0.427 ms, ix_geo_poi_geom |
| EXPLAIN ANALYZE radius 500 m | 12.662 ms, ix_geo_poi_geography |
| EXPLAIN ANALYZE район | 6.585 ms, ix_geo_poi_geom |

Это измерения одного запуска на RTX-ноутбуке/16 GB RAM; GPU не используется.
Запросы SQL COUNT для проверки планов, не обещание HTTP p95. После измерений
удалена только созданная временная test-БД. Основная БД сохранена.

Для больших территорий пока действуют лимиты 64 MiB/100000 элементов и bbox до
0.1 квадратного градуса. Импорт батчами по 500, GiST/GIN и ANALYZE; HTTP statement
timeout 5 s, операторский импорт 120 s. Для масштабирования нужны PBF/retention/тайлы.
