# Business AI 2.0 — U-01: Data Registry & Coverage

29.10.2026. База: PR31 merged, main `ffc06f1d6b42c3c0fda3939edc19cdacda03115a`.
Ветка `codex/U-01-data-registry-coverage`. Фактические commit/PR/CI — в сообщении сдачи.
Это функциональная часть registry/coverage U-00; U-02/agent/industry engine не начаты.

## Реализация и источник истины

| Компонент | Реализовано |
| --- | --- |
| [registry.json](../../apps/api/app/data/registry.json) | Reviewed operator config: revision,4source registrations,18categories,3freshness policies,3territory identities |
| [registry_schemas.py](../../apps/api/app/data/registry_schemas.py) | Frozen extra-forbid DTO, references/unique IDs/aliases/license/origin/adapter validation, bounded query/result/requirements |
| [registry.py](../../apps/api/app/data/registry.py) | Safe config loading/hash/source lookup, independent local-use/acquisition permission and freshness evaluation |
| [providers.py](../../apps/api/app/data/providers.py) | Existing DataProvider protocol/metadata/converters; v1 sources is a projection of the same registry |
| [coverage.py](../../apps/api/app/data/coverage.py) | Bounded active metadata read, PostGIS extent tests, orthogonal assessment, deterministic sufficiency/grouping |
| [api/registry.py](../../apps/api/app/api/registry.py) | Versioned public metadata API, no admin write/fetch endpoint |

Новых таблиц, дублирующего dataset store и миграций **нет**. Source of truth остаются
`geo_datasets`, `walk_graphs`, `provider_datasets`; геообъекты/рёбра не переписываются.
Переиспользованы OSMProvider.metadata/SyntheticProvider.metadata/WalkGraphView,
ProviderId/DataMode, единственный DataOrigin и исходные versions/лицензии/limitations.
DatasetReference — безопасная projection существующей metadata, не новая provenance БД.
Legacy timestamp aliases/stale поля не копируются в v2: даты и новая freshness явны.

Реестр не привязан к coffee/auto/online/закрытому списку отраслей. Категории географии,
демографии, экономики, пользовательского ввода и сценариев отделены от отраслей.
Наличие категории в каталоге не означает реализованный adapter или доступные данные.
Новые category/source IDs добавляются конфигурацией; новый Python adapter требует кода
и отдельной проверки. Base4provider identities/origins сохраняются ради v1.

Три city IDs — проектные идентичности Казани/Москвы/Новосибирска с reviewed aliases;
это **не** импорт границ. `boundary_status=unknown`. Country code расширяем, ambiguous
aliases запрещены; fuzzy/nearest covered city normalization не добавлялась.

## Конфигурация и права

По умолчанию используется packaged registry.json. `BA_DATA_REGISTRY_PATH` задаётся
оператором на host/container вне HTTP; файл≤128KiB, проверяется Pydantic. После изменения
нужен restart процесса, revision/hash меняются; никакого public admin API/hot reload.
Некорректный файл даёт503 `data_registry_invalid` без пути/содержимого в ответе.

SourceDefinition разделяет adapter status, categories, acquisition methods, geographic
applicability, license/attribution, allowed use, network permission, declared availability,
policy revision и resource-policy reference. Unknown license не равна разрешению.
`verified_local_use` относится к существующему локальному назначению/атрибуции,
не юридическому заключению о любом распространении; redistribution по умолчанию не разрешён.
Даты formal license/remote availability review не выдуманы: optional/null, если неизвестны.

- OSM: реализован local read/operator importer, ODbL/attribution сохранены;
  remote availability unknown/network review_required. Каталог не запускает fetch.
- Synthetic: существующие authored scenarios/CC0, только explicit demo mode и server flag;
  network forbidden. Не runtime генерация рыночных значений.
- GHSL/Licensed: placeholders/not_integrated, конкретная лицензия/набор не подтверждены,
  network forbidden. Не создаются фиктивные наблюдения населения/аренды.

AcquisitionOption показывает все оси и `potentially_available`, но
`automatic_acquisition_implemented=false` всегда в U-01. `permitted` возможно только
для явно разрешённого назначения/сети/готового operator adapter и заявленной доступности;
это предложение operator acquisition, не действующий job endpoint. Tests используют
искусственно разрешённые policy fixtures, а не объявляют public endpoint проверенным.

Новый service проверяет права использования evidence перед sufficiency. Это не глобальная
перенастройка исторических v1 geo APIs/не сетевой firewall для всего приложения;
v1 policy/DTO/формулы сохранены. Новая политика действует на v2 assessment и будущие tools.

## Coverage: точное значение состояний

Вход: optional territory ID/AOI,1–10distinct category IDs, optional period, purpose,
real/demo mode. AOI наследует bounded WGS84 Bounds v1 (включая≤0,1square degree).
Размер AOI не является обещанием скорости/полноты всего города.

| Поле | Значения / смысл |
| --- | --- |
| local_status | available/partial/stale/missing/unknown — локальная пригодность в выбранном scope/mode |
| availability | present/missing/unknown — наличие matching metadata, отдельно от права использования |
| freshness | current/stale/unknown — по выбранной policy; partial может одновременно быть stale |
| completeness | full_for_requested_scope/partial/unknown — покрытие **выгрузки**, не репрезентативность рынка |
| object_quality | unknown либо not_applicable для authored scenarios; не фиктивные проценты качества |
| summary | U-00 usable/stale/partial/acquirable/source_unavailable/not_available_from_approved_sources/unknown |
| acquisition | независимые technical/license/network/availability/local-use признаки и причины |

`available` означает подходящий current snapshot для явно заданного AOI, а не «все
предприятия/весь город известны». Пустая выборка не доказывает отсутствие объектов.
City-only Kazan даёт partial; нет проверенной boundary, поэтому нет100%площади города.
Противоречивые territory/AOI сохраняют геометрический fit, но блокируют usable evidence.
Неизвестный territory без AOI — unknown, не nearest Kazan. Без координат/identity
пространственный охват не угадывается. Необоснованные alias/query metadata — unknown.

Читаются active metadata с cap+1, не все POI/edges. `ST_Covers` включает границу bbox;
`ST_Intersects` отличает partial/outside. В PostGIS передаются только4scalar bounds
на dataset, не большие геометрии в Python. Проверенный legacy POI query сопоставляется
с существующим build_query; произвольный query string не объявляется поддержкой слоя.
Administrative extract polygons всегда partial, walking не vehicle network.

Несколько partial datasets не объединяются в заявленный full: для mosaics нужен
согласованный manifest/version policy U-02. Если metadata повреждена/неаттестована или
cap превышен, metadata_complete=false; отсутствие результата — unknown, не false missing.
Доступный пригодный cache остаётся usable, даже если remote source offline.

## Freshness и периоды

В v2 отдельно представлены source_timestamp, published_at, observed_at, fetched_at,
generated_at, imported_at, temporal_coverage, next_update_at. Неизвестное остаётся null.
OSM osm_base — snapshot/source timestamp, **не дата обследования предприятия**.
Файл, скачанный сегодня, не делает неизвестное наблюдение свежим.

Policies конфигурируются без DDL: source_timestamp/period_end/generated_at/unknown,
nullable max_age_days и rationale. `generated_at` разрешён как основание только для
synthetic template cadence. OSM mapped POI наследует существующий30дневный review
cadence (exact duration boundary), synthetic —365дней авторского шаблона; administrative/
walking/непроверенные категории — unknown, пока нет обоснованной политики.
Универсального срока для всей экономики/географии не введено.

Period.kind=observation_interval по умолчанию: один снимок не подтверждает весь интервал.
Явный snapshot_window допускает поиск source snapshot внутри окна; ответ отмечает
snapshot_in_period, не историческую time series. Старый snapshot вне периода и unknown
measurement различимы. Publication/next update metadata не выводятся из download time.

## Sufficiency: внутренний сервис, без Qwen/planner

`sufficiency(requirements,result)` возвращает решения по каждой переданной потребности.
`assess_sufficiency(requirements,result,revision)` группирует server-defined critical_for
и даёт allowed_tasks/blocked_tasks. Список≤20, IDs distinct. Нет генерации требований,
выбора отрасли, DAG/executor dispatch или самостоятельного назначения tool names.

Проверяются usable evidence, accepted origins, current freshness, required/optional,
allow_partial и require_known_quality. Только optional requirements не дают пустого
«успешного» алгоритма. Technical eligibility — не authorization/наличие executor и не
достоверность бизнес-рекомендации. При quality unknown и требовании известного качества
операция блокируется. Возможные действия:use_pinned/cache_revalidate/request_acquisition/
ask_user/omit_optional/block; они **не выполняются** этим сервисом.

Assumptions: сохраняется DataOrigin.SYNTHETIC, real mode их не подставляет. Даже
accepted_origins=synthetic/allow_assumption=true не подтверждает шаблон автоматически:
до owner-scoped review механизма U-05 decision требует ask_user. Подтверждение в будущем
не должно менять origin на observed. Private user inputs не читаются публичным каталогом;
для них unknown/ask_user, без budget других сессий.

## API и безопасность

```http
GET /api/v2/data-registry
POST /api/v2/data-registry/coverage
Content-Type: application/json

{"territory":"ru-kazan","categories":["geo.mapped_poi","geo.vehicle_network"]}
```

Первый endpoint возвращает catalog/revision/config_sha256/categories/policies/identities.
Второй — query/evaluated_at/assessments/metadata_complete/limitations.
Для существующей базы первый item partial, vehicle layer missing. Москва без импорта:
mapped_poi missing, remote permission unknown, potentially_available=true.
Точный AOI из dataset metadata может быть available только внутри его заявленного extent.

Endpoints публичны, как существующий public OSM metadata API: они не читают profiles,
messages, consent, leads или owner data. User categories возвращают unknown без evidence.
Нельзя передать conversation_id/owner/token/SQL/URL/path для расширения доступа.
Source URLs/queries/runtime internals не включены в DatasetReference. Network и LLM
не вызываются, новых записей в БД нет. Любые будущие private evidence APIs требуют
отдельного owner-scoped контракта; этот public reader для них не подходит.

Errors:422invalid DTO/unknown_data_category,404data_source_not_found во внутреннем lookup,
403demo_data_disabled,503data_registry_invalid/существующие DB errors. H-05 safe errors/
X-Request-ID сохранены. H-02 body/структурные/frequency caps действуют, POST coverage
включён в общий heavy budget (active_heavy default2), нового rate limiter нет.

## Проверки и фактические границы

- Сравнение baseline/current OpenAPI:39старых paths и128schemas идентичны.
  TS types regenerated; frontend runtime не менялся, typecheck/build PASS.
- Новые unit/API tests: registry conflicts/unknown sources/extensibility, freshness
  boundaries/future clock/no measurement date, interval vs snapshot, coverage axes,
  permissions/offline cache, assumptions/technical vs quality, safe config errors и422.
-10новых PostGIS tests: искусственные POI/walking/scenario fixtures, covers/intersects,
  no POI/edge scan, Kazan identity partial/Moscow missing, no-map/private inputs/two owners,
  no network/LLM, invalid category до SQL, cap overflow unknown, immutable table fingerprints,
  repeated upgrade и alembic check. Не реальные геоданные Москвы.
- Общий локальный DB run:112PASS/1FAIL — прежний async readiness на Windows Proactor.
  Причина подтверждена установленным psycopg. Selector loop только в test process:
  повтор readiness+final registry **12PASS**, без ослабления assertions/product changes.
  Остальная существующая DB-регрессия, включая populated0007→0008, прошла в первом run.
- Focused unit/provider/finance79PASS, включая unknown-source lookup;36новых unit/API
  tests и существующие provider/finance regressions. Mandatory prek/CI проверяют более
  широкий набор. Новые universal planning/import/industry scenarios не объявлены PASS.

Реальная read-only metadata база: [evidence](../qa/u-01/read-only-kazan.json),
kazan-centre23852POI/8polygons, bbox49.05/55.7/49.25/55.85, прежний44157bdc…version.
20coverage calls по точному extent: median3,040ms/max36,962ms (существующий локальный
runtime, один клиент, metadata only). Small artificial PostGIS fixture:20calls,
последний median5,882ms/max9,505ms на Windows host→изолированный контейнер.
Это не SLA, benchmark всей Казани/Москвы или измерение импорта.

Новая БД не нужна: повторный head/check и fingerprints всех19public application tables
проверены на заполненной isolated fixture. Новых migrations/constraints/indexes нет;
existing active metadata indexes используются обычными queries. Работа имеет O(metadata cap),
не O(POI count); для большого каталога U-02 должен добавить spatial metadata indexes/пагинацию
по измерениям, а не увеличивать cap бесконечно. max_datasets=100, operator-configurable1…1000.
До3×(cap+1)metadata rows читаются, result общий≤cap; overflow явно unknown.

Изолированный PG17/PostGIS3.6 использует tmpfs, без user volumes. Рабочая БД/F-00/
backup/старые reports не изменялись. GPU/live Qwen не запускались: extraction/LLM
не затронуты. Existing CI/prek выполняют регрессию; точный итог/commit/PR — в сдаче.

### Воспроизведение

Из корня репозитория:

```powershell
uv run --locked --project apps/api pytest apps/api/tests/test_registry.py apps/api/tests/test_data_providers.py apps/api/tests/test_finance.py -q
uv run --locked --project apps/api ruff check apps/api
uv run --locked --project apps/api mypy --config-file apps/api/pyproject.toml apps/api/app apps/api/tests apps/api/migrations
prek run --all-files
```

Для DB tests использовать только изолированный PostgreSQL/PostGIS с отдельными
`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, правом создания тестовых БД и
`BA_RUN_DB_TESTS=1`, как описано в integration support. Затем:

```powershell
uv run --locked --project apps/api pytest apps/api/tests/integration/test_registry.py -q -s
```

На Windows при запуске async readiness через pytest нужен Selector loop в тестовом
процессе: `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())`
перед `pytest.main(...)`. Linux CI не требует этой настройки. При старых ACL на
pytest temp directory задать `PYTEST_DEBUG_TEMPROOT` на доступный временный каталог.
Сценарии не загружают реальные данные Москвы и не требуют Qwen или внешней сети.

## Что остаётся U-02 и позже

Нет fetch jobs, worker, broker, новых импортов, whole-Moscow dataset, agent/browser,
industry policies, assumption generator, finance rewrite или frontend progress.
Resource policy ref остаётся u02-measurements-pending:512MiB не превращены в blanket cap.
Нужны source/terms/egress approval, measured per-operation RAM/CPU/disk/WAL/network,
dataset-group versions, checkpoints/dedup/cancel/fencing/activation. Legacy in-memory
parsers требуют bounded tiles/peak-RSS evidence; этот registry не делает их streaming.

Для U-02 доступны load_registry/source_definition/CoverageQuery/coverage/freshness/
assess_sufficiency и типизированные AcquisitionOption. Пока network review/adapter
не готовы, importer не должен запускаться по одному potentially_available=true.
U-02 не начат; переход и merge только по решению владельца.
