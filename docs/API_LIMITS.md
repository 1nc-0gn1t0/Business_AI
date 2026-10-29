# H-02 · API limits и квоты локального deployment

## Дополнение H-03 · действующее управление inference · 26.10.2026

Body/DTO/stock quotas H-02 и 18 write API не меняются. POST messages учитывается в
общем window600/60s и heavy window120/60s, общем active cap8, но **не занимает
аналитические active_heavy=2 slots**: модель имеет отдельную FIFO — 1 active и default
1 waiting. Без этого два диалога блокировали бы доступ к аналитике. Только настоящая
операция inference занимает model slot; точная фраза подтверждения его не требует.

Новые BA_API_LIMITS_JSON параметры (restart API): `inference_queue_size=1`, strict int
0…4 (0 — без ожидания), `inference_wait_seconds=10`, число(0,30]. Active inference всегда1.
Snapshot read/Session закрыты до очереди; очередь и Qwen не резервируют PostgreSQL
connection/row lock. После получения результата — новая Session, owner/profile CAS/
assistant consent revision/quota checks; withdraw→grant тоже инвалидирует snapshot.
Квоты хранения и атомарность H-02 действуют до записи, без повторного списания.

| Событие | Ответ |
|---|---|
| Очередь заполнена | 429 llm_queue_full |
| Ожидание превысило configured wait | 429 llm_queue_timeout |
| Активный inference превысил LLM_TIMEOUT_SECONDS | 504 llm_timeout, прежний код |
| Отзыв/смена согласия или версии | 403 consent_required_assistant /409 consent_revision_conflict /409 version_conflict |
| HTTP disconnect до записи | результат не сохраняется; локальный ASGI ответ499 request_cancelled, сетевой клиент уже отключён |

У queue429 нет Retry-After: точное время освобождения неизвестно. React сохраняет
сообщение, объясняет повтор без автоматической отправки. Таймаут Ollama default120s,
до180s; proxy240s/browser250s учитывают максимальное ожидание30s и запас на DB phases.
Отмена active async HTTP закрывает stream; отмена queued удаляет ticket. DB worker
дожидается безопасного rollback/close. Disconnect после commit не отменяет уже
сохранённые данные: перечитать профиль перед повтором (CAS).

Scope — **один worker/asyncio loop**. Никакой distributed queue, Redis/Celery или
защиты от прямых запросов к Ollama. Sync mock/legacy adapter не прерывается убийством
thread: слот освобождается только после его реального завершения, без второй модели
параллельно. Штатный Ollama path — async. Дальнейшие hard API/CPU budgets и soak — Q-04.
Измерения/ограничения: [PERFORMANCE](PERFORMANCE.md), [ADR-0002](adr/ADR-0002-local-llm.md).

Ниже сохранена исходная инвентаризация/политика H-02; описание общей heavy concurrency
для сообщений и переноса H01-P1-02 в H-03 заменено этим дополнением.

## Инвентаризация ДО изменения кода · 26.10.2026

Источник: main `c3c8c73d92c1f63664b440faee62d69c9c5fce2e`, OpenAPI и реальные
router/services/DTO. **18 write endpoints**, включая stateless операции и consent.
Указанные ниже пробелы фиксируются до реализации H-02. Не все POST записывают БД.
`C=/api/v1/conversations/{conversation_id}`, `G=/api/v1/geo/{slug}`.
Все остальные пути указаны полностью. «Нет body cap» означает отсутствие cap приложения;
Nginx перед web не защищает прямой локальный порт API.

| Method / endpoint | Body cap до H-02 | Строки / коллекции / числа до H-02 | LLM / тяжёлый расчёт / запись PostgreSQL | Потенциальный рост / пробел |
|---|---|---|---|---|
| POST `/api/v1/conversations` | нет | Body модели нет | нет / нет / да | conversation + profile + initial revision/message; нет global creation quota |
| PATCH `C/profile` | нет | text≤200; lists≤20; Money finite≤18 digits/2 decimals; version≥0 | нет / нет / да | revision + assistant message; lifetime/session caps нет |
| POST `C/messages` | нет | content1…4000; version≥0; extracted patch≤200/20 | да, кроме confirm phrase / да / да | user+assistant messages/revision; нет total message quota; транзакция при inference — H-03 |
| POST `C/profile/confirm` | нет | version≥0; профиль полный/positive budget | нет / нет / да | revision/message; confirmation не consent |
| POST `G/candidates` | нет | full profile text/lists без max; districts≤20, requirements≤10, limit≤10; cell250…2000m, distances bounded | нет / да / нет | grid/PostGIS/GeoJSON; нет общего body/admission budget |
| POST `G/rankings` | нет | CandidateRequest + finite nonnegative weights, existing scoring policy | нет / да / нет | candidates+metrics; алгоритм не менять |
| POST `G/catchment` | нет | existing bbox/coordinates/radius/snap/graph/version caps | нет / да / нет | bounded Dijkstra/POI result; нет общего admission budget |
| POST `G/walking-rankings` | нет | RankingRequest + walking settings, existing caps | нет / да / нет | несколько network calculations; нет общего admission budget |
| POST `/api/v1/finance/calculate` | нет | full profile unbounded; costs Money18/2, ratio[0,1), sales≤1M/day, days1…31, sensitivity≤6, source limitations1…10 | нет / да / нет | 3 scenarios/sensitivity; source strings без max |
| POST `C/bank-products/matches` | нет | expected_version≥0, typed needs/enums/booleans, digest64 | нет / небольшой / нет | owner checked; только текущий каталог, stateless result |
| POST `/api/v1/data-providers/selection` | нет | mode real/demo | нет / нет / нет | request-scoped; не глобальная настройка и не запись user state |
| POST `/api/v1/data-providers/indicators` | нет | provider enum, slug≤64, version64, metrics1…10 distinct, bbox bounds | нет / да / нет | existing source only; нет скрытого synthetic fallback |
| PUT `C/consents/{purpose}` | нет | purpose enum; decision enum; revision≥0; text_version без max | нет / нет / да | consent + audit при смене; без quota; отзыв должен оставаться доступен |
| POST `C/leads/drafts` | нет | fields text≤100; products1…6 unique; version≥0/digest64 | нет / небольшой / да | draft profile/payload/consents snapshots + audit; нет stock quota |
| PUT `C/leads/drafts/{draft_id}` | нет | DraftInput + expected_revision≥0 | нет / небольшой / да | bounded-by-DTO update + audit; caps на число revisions/audit нет |
| POST `C/leads/drafts/{draft_id}/confirm` | нет | revision≥0, confirmed=true, fingerprint64 | нет / нет / да, кроме replay | state + audit; stock policy отсутствует |
| POST `C/leads/drafts/{draft_id}/submit` | нет | action + UUID idempotency; owner/profile/consent/catalogue проверяются | нет / только local mock / да, кроме replay | receipt + submitted + audit atomic; unique draft/key; total stock не ограничен |
| POST `C/reports` | 128 KiB, actual chunks | typed input/fingerprints; providers≤3; profile сам по себе unbounded | нет / да / да | snapshot≤4MiB/PDF≤3MiB/40pages/20 per conversation; нет global count/byte quota |

GET messages/history/audit уже paginated ≤100; `GET C/leads` возвращает весь workspace.
GET report metadata/snapshot/file проверяет owner/staleness и читает/хеширует сохранённые
bytes; это тоже потребитель CPU/памяти/полосы и должен участвовать в admission policy.
Приватных HTTP операций AnalysisRun и HTTP операций backup/import нет.

## Измерения для выбора лимитов

До реализации воспроизведён offline scan текущего `qwen-v2.json`: 61 диалог,
максимум 5 turns, 2522 characters/message, максимум JSON wire body **13 145 bytes**
при escaped Unicode. Нормальный finance fixture: **6665 bytes**, 278 value nodes,
depth6, максимум 8 элементов в коллекции. Это измерения существующих сценариев,
не stress test и не точность Qwen. Ответ BA-015 JSON около 502 KiB — **response**,
а не основание разрешать такой же POST body. Существующий reports cap 128 KiB сохраняется.

Основа политики: текущие PATCH 200/20 и message4000 остаются default; общий body64KiB
даёт запас и для escaped 4000 Unicode chars (до48KiB). Reports128KiB, nodes4096,
depth16, items128 и generic text4096 — запас относительно измеренных fixture inputs.
Индивидуальные caps складываются: допустимое отдельное поле не гарантирует допустимость
всех максимально заполненных полей одновременно в пределах aggregate body budget.

## Действующая политика H-02

Для **всех 18 строк таблицы** действуют: body ≤65536 bytes (только POST reports —
131072), строка JSON ≤4096 Unicode code points, ключ ≤128, коллекция ≤128 элементов,
дерево ≤4096 value nodes и depth≤16 (root=0). Считаются значения, ключи ограничены
отдельно; JSON root — object, NaN/Infinity запрещены. Действующие более строгие DTO
применяются дополнительно. Полный BusinessProfile и PATCH теперь одинаково ограничены:
city/category/format/элемент preferences ≤200 characters, каждый список ≤20.
Message 1…4000, version/revision — strict integer 0…2147483647 (диапазон PostgreSQL
INTEGER). Денежные ограничения 18 digits/2 decimals и доменные числовые диапазоны
geo/finance сохранены. Прежние валидные fixture DTO проходят.

| Endpoints из инвентаризации | Дополнительная квота / отказ |
|---|---|
| create conversation | global conversations/revisions/messages; 429 до создания любых строк |
| profile PATCH, messages POST, confirm POST | общие owner/global revisions/messages; 429 preflight до Qwen и повторная атомарная проверка до записи |
| 4 geo POST + finance POST | общий heavy admission; 429 до handler; полные profile bounds →422 |
| bank matches + provider selection/indicators POST | общий admission + envelope/DTO; нет записи user resources |
| consent PUT | grants: общий admission; запись consent/audit stock; deactivation exception ниже |
| draft create/edit/confirm/submit | draft/receipt/audit stock; 429 до mock adapter/записи; replay не создаёт audit и не списывает stock |
| report POST | reports count и global bytes; 429 preflight и окончательная проверка; 413 при body overflow |
| report GET metadata/snapshot/file | общий heavy admission; сохранённый per-report cap остаётся ≤4MiB JSON/3MiB PDF/40 pages |

Верификация размера — pure ASGI: Content-Length проверяется до чтения, каждый actual
chunk — **до** добавления в bytearray. Отсутствующий/заниженный Content-Length не
обходит cap. Всё тело ограниченно буферизуется до handler; timeout чтения 10 секунд.
Невалидный envelope не запускает Qwen, SQL writes или renderer. Header names+values
≤16384 bytes, decoded UTF-8 path≤2048 bytes, raw query≤4096 bytes. Это application
limits после HTTP parsing, не защита от сетевого DoS/неограниченных TCP connections.

### Хранение и атомарность

| Ресурс (число строк) | Вся БД deployment | Одна conversation |
|---|---:|---:|
| conversations / profiles | 500 / одна profile на conversation | 1 |
| messages | 20000 | 400 |
| profile revisions | 10000 | 200 |
| consent history | 5000 | 60 |
| lead drafts | 1000 | 20 |
| mock receipts | 1000 | 20 |
| audit events | 20000 | 300 |
| reports | 200 | 20 |

Сумма PDF bytes + `octet_length(snapshot::text)` всех reports ≤134217728 bytes
(128MiB). Это logical payload cap, **не** предел диска PostgreSQL: TOAST/index/WAL,
backup, геоданные и AnalysisRun вне этой суммы. Остальные созданные HTTP ресурсы
ограничены counts × конечными размерами DTO. Импорты/прямой SQL — доверенные
операторские операции вне HTTP policy. Даты/версии геоданных, финансовые формулы,
сохранённые snapshots и алгоритмы не менялись.

Квоты не сбрасываются при новом guest ID, другом endpoint, рестарте процесса или
новой вкладке: используются реальные committed counts PostgreSQL. Проверки/записи
сериализованы transaction-level advisory lock `business-ai-h02-storage`; существующая
owner row lock берётся первой. Preflight не держит advisory lock во время inference
или render; финальная проверка выполняется в транзакции записи. При гонке один
запрос может выполнить расчёт и получить 429, но не превысит stock cap. Новый SQL
rollback не оставляет частичных profile/history/report/receipt/audit rows.
Это не reservation/очередь inference H-03.

Отзыв/decline **ранее granted** согласия пропускает stock cap, чтобы исчерпание квоты
не мешало отзыву. Новые grants заблокированы при полном consent/audit stock; после
заполнения возможно не более трёх дополнительных deactivation records и audits на
уже существующую conversation (три purpose). Повтор уже установленного состояния
не создаёт строки. Чтение текстов/согласий и PUT withdraw/decline обходят только
временное окно, но **не** body/active-request caps, owner/CAS checks. Grants окно
не обходят. Пока активные слоты заняты, отзыв может потребовать повторного запроса.
Маркетинговое согласие не стало обязательным. История и пользовательские данные
не удаляются. Снижение квот ниже existing usage блокирует рост, не чтение.

### Нагрузка и границы deployment

Один API worker, loopback Compose; общий fixed window 60s: 600 запросов, из них
120 heavy. Одновременно ≤8 API requests, из них ≤2 heavy (включая медленное чтение
body). Heavy: POST geo/finance/messages/reports и GET report metadata/snapshot/file.
Остальные `/api/v1/*` тоже учитываются; `/healthz` и OpenAPI/docs исключены.
Отклонённые validation/handler операции расходуют попытку, active slots освобождаются
при ответе/исключении/disconnect/timeout. Счётчики имеют фиксированный объём памяти,
без attacker-controlled IP/session map; X-Forwarded-For не используется.

Это запас для одного человека: нормальный flow — несколько десятков запросов,
heavy обычно длится секунды. 500 sessions/200 reports рассчитаны на локальное demo,
а не анонимный публичный сервис. Злоумышленник с доступом к локальному API всё ещё
может исчерпать общую квоту и ухудшить доступность. Решение оператора — проверить
usage/backup/retention policy, осознанно увеличить cap; автоперезапуск его не очистит.
Accounts/per-user admission/retention/public deployment требуют отдельной работы.

Временные/concurrency counters — **память одного процесса**, сбрасываются при restart.
DB stock checks координируются PostgreSQL, но это **не** multi-worker rate limiting.
`WEB_CONCURRENCY!=1` отвергается при старте; CLI `uvicorn --workers N` автоматически
не определяется и запрещён инструкцией deployment. Несколько API replicas/прямой
доступ к Ollama этой политикой не защищены. Redis/Celery/новые сервисы не добавлены.
H01-P1-02 (read transaction во время inference) открыт для H-03; hard compute
timeouts/нагрузка и публичный периметр не считаются закрытыми H-02.

### Конфигурация

`BA_API_LIMITS_JSON` — JSON object environment API, читается при старте, после изменения
нужен restart/recreate API. Частичные `global_records`/`owner_records` объединяются с
defaults. Неизвестные ключи, неверные типы/нулевые caps и несогласованные лимиты
останавливают старт с безопасной ошибкой. Тексты/списки DTO фиксируются при импорте
модулей; reload переменной в работающем процессе не поддерживается.

Все ключи defaults:

```json
{
  "body_bytes": 65536, "report_body_bytes": 131072,
  "header_bytes": 16384, "query_bytes": 4096, "path_bytes": 2048,
  "body_timeout_seconds": 10,
  "profile_chars": 200, "profile_items": 20, "message_chars": 4000,
  "text_chars": 4096, "collection_items": 128, "json_nodes": 4096, "json_depth": 16,
  "version_max": 2147483647,
  "window_seconds": 60, "requests_per_window": 600, "heavy_per_window": 120,
  "active_requests": 8, "active_heavy": 2,
  "report_storage_bytes": 134217728,
  "global_records": {"conversations":500,"messages":20000,"revisions":10000,
    "consents":5000,"drafts":1000,"receipts":1000,"audit":20000,"reports":200},
  "owner_records": {"messages":400,"revisions":200,"consents":60,"drafts":20,
    "receipts":20,"audit":300,"reports":20}
}
```

Пример PowerShell для Compose (не менять системные переменные):

```powershell
$env:BA_API_LIMITS_JSON = '{"global_records":{"conversations":600,"reports":220}}'
docker compose up -d api
```

Count settings — strict integers 1…1000000; report_storage_bytes≤1GiB,
body_timeout_seconds(0,120], version_max≤2147483647. Heavy budgets должны укладываться
в total, profile_items≤collection_items, text_chars≥profile_chars/message_chars,
report_body_bytes≥body_bytes. Изменять storage cap следует после проверки свободного
места; снижать DTO caps — после проверки уже сохранённых профилей/совместимости.

### Ответы и клиент

| Status | Code / смысл |
|---|---|
| 413 | request_body_too_large / report_request_too_large, старые report payload/PDF caps |
| 422 | invalid_request_structure / request_structure_too_large / request_text_too_long либо safe DTO detail list |
| 429 | request_rate_limited + реальный Retry-After seconds до конца окна |
| 429 | request_capacity_busy, resource_quota_exceeded, report_limit_reached; **без** Retry-After: момент освобождения/изменения stock неизвестен |
| 408 / 414 / 431 | request_body_timeout / request_target_too_large / request_headers_too_large |

DTO 422 сохраняет type/известный field location/static message, исключает input/ctx,
произвольные extra keys заменяет `<field>`; до16 ошибок/16 частей location. Ввод не
отражается в публичном response и не логируется. React показывает понятные сообщения,
сохраняет черновик чата, не делает automatic retry; отображает время только из
корректного Retry-After. Ограничения не меняют права owner и consent semantics.

## Воспроизведение и evidence · 26.10.2026

```powershell
uv run --locked --project apps/api pytest apps/api/tests/test_api_limits.py apps/api/tests/test_h01_triage.py -q
docker compose --profile test run --build --rm db-tests
uv run --locked --project apps/api pytest apps/api/tests -m extended --hypothesis-show-statistics
npm --prefix apps/web test
npm --prefix apps/web run test:e2e
uv tool run --from prek==0.5.4 prek run --all-files
```

DB tests используют UUID databases, а не рабочую БД. Изменения профиля/финансов/гео
проверяются существующей регрессией. H-01 oversized/422 probes переведены из strict
XFAIL в PASS после зафиксированного XPASS; assertions сохранены. Результаты и ограничения:
[SECURITY_TEST_REPORT](SECURITY_TEST_REPORT.md), [HANDOFF](HANDOFF.md).
На Windows с чужим недоступным `%TEMP%/pytest-of-inc` использован отдельный
`PYTEST_DEBUG_TEMPROOT=$env:TEMP/business-ai-h02-pytest`, без изменения ACL/удаления данных.

Технические основания: [Starlette pure ASGI middleware](https://www.starlette.io/middleware/),
[PostgreSQL transaction advisory locks](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS).


## Business AI 2.0 / U-01 — metadata endpoints

`GET /api/v2/data-registry`: public static catalog/revision/policies, no database/network.
`POST /api/v2/data-registry/coverage`: public imported metadata only, no writes/LLM/fetch;
included in H-02 heavy admission (default2active) and the existing frequency/body/JSON caps.
1–10distinct categories, existing bounded WGS84 Bounds, optional typed period/territory.
Metadata cap100 configurable via operator registry (1…1000); overflow is unknown, not missing.
No user profiles/consent/lead/report data or administrative source-policy writes exposed.
Source URLs/internal paths excluded.403demo_data_disabled,422invalid/unknown category,
503data_registry_invalid/DB failures,413/429as existing H-02. Correlation ID preserved.
Details: [registry implementation](architecture/BUSINESS_AI_2_DATA_REGISTRY_IMPLEMENTATION.md).

## Business AI 2.0 / U-02 — operator acquisition

`POST /api/v2/acquisitions`, `GET /api/v2/acquisitions/{id}`, GET `/{id}/events`,
POST `/{id}/cancel`: operator-only, enabled explicitly; guest token grants no access.
`BA_ACQUISITION_OPERATOR_TOKEN` >=32characters in `X-Acquisition-Token`, never query/frontend.
Disabled503; unauthorized401; policy403; conflict409; AOI/input422; capacity429.
Events after>=0/limit<=100; unknown progress remains null. POST reuses heavy admission.
Pending<=2, retained<=100jobs/200idempotency mappings; no automatic history purge.
Default per-operation AOI<=250000m²/4MiB/10000elements/180s; source caps>=60s/10perday/
2attempts. No global512MiB assumption. Operator config cannot exceed structural AOI/byte/
element caps. Expiring operator_smoke permission still required; network closed by default.
Full [policy, errors, recovery and measured limits](architecture/BUSINESS_AI_2_DYNAMIC_ACQUISITION.md).
