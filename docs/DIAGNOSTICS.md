# H-05 · безопасная диагностика локального deployment

Один worker, существующий модульный монолит. Это не observability-платформа и не
сертификация RC. [QA](qa/H-05_DIAGNOSTICS_REPORT.md), [API limits](API_LIMITS.md),
[H-03 measurement](PERFORMANCE.md), [backup status](BACKUP_RESTORE.md).

## Проверки и границы

| Проверка | Назначение | Ответ / ограничение |
|---|---|---|
| `GET /livez` | Event loop отвечает | 200; без БД, пула, очереди и inference |
| `GET /readyz` | Готовность DB-backed операций | 200 либо503; PostgreSQL, вызов PostGIS_Version, точная поддержанная revision0008 |
| `GET /healthz` | Совместимость старого smoke/frontend | Прежний200 DTO с PostGIS version; не проверяет схему/модель |
| `GET /api/v1/diagnostics` | Opt-in bundle работающего процесса | По умолчанию404; отдельный header token, затем bounded DB/Ollama probes/counters/queue/pool |
| `python -m app.readiness` | Локальный operator probe | Те же зависимости; **новый процесс**, поэтому его queue/counters не описывают работающий API |

DB probe: connect_timeout2s, statement_timeout1s, общий async deadline4s плюс небольшие
накладные расходы HTTP. Autocommit и закрытие connection в context manager; отдельное
диагностическое соединение не занимает SQLAlchemy pool. Ошибки схемы/расширения не
публикуют SQL, имена таблиц, DSN или ожидаемую внутреннюю revision.

Ollama probe только в opt-in bundle: GET /api/tags, HTTP timeout2s, общий3s,
raw response≤64KiB, redirects/proxy environment выключены. DB/model probes параллельны.
Model presence отличается от inference: `inference=not_tested` всегда. Stub обозначен
`provider=stub`, model/ollama `not_checked`, общего статуса полноценной модели нет.
`ready_unverified` означает доступные prerequisites, **не** проверенное качество ответа.
`degraded` — БД готова, локальный диалог не подтверждён; `unavailable` — БД/схема не готовы.
Очередь busy/full — состояние ёмкости, не доказательство неисправности GPU.

Readiness не вызывает модель и не отключает приложение целиком: при отказе Ollama
ручной профиль/гео/финансы/каталог/согласия/сохранённые отчёты остаются доступны, если БД
и соответствующие данные готовы. При отказе БД liveness и публичный статический каталог
могут отвечать, а DB-backed операции возвращают503. Readiness не сертифицирует покрытие
OSM, актуальность банка, наличие шрифтов или целостность всех сохранённых PDF.
Экспорт в bundle явно `not_checked`: создание PDF в health не выполняется.

## Доступ к подробностям

Оператор самостоятельно задаёт `BA_DIAGNOSTICS_TOKEN` (не менее32 символов) через
приватное окружение или игнорируемый `.env`, затем пересоздаёт **только свой** API.
Не вставлять значение в URL, CLI arguments, Git, скриншоты или сообщения.
Compose передаёт переменную только backend. Токен не является guest credential.
Отсутствие/короткое значение и неверный `X-Diagnostics-Token` →404 до любых probes;
сравнение constant-time. Endpoint не включён в OpenAPI; это не замена авторизации.
Доступ ограничен реально сервером, а не браузером; deployment остаётся на loopback.

Для чтения работающего процесса, после безопасного помещения токена в окружение
текущего PowerShell:

```powershell
$bundle = Invoke-RestMethod http://127.0.0.1:8000/api/v1/diagnostics `
  -Headers @{'X-Diagnostics-Token'=$env:BA_DIAGNOSTICS_TOKEN} -TimeoutSec 8
$bundle | ConvertTo-Json -Depth 8
```

Bundle не содержит адресов сервисов, названия configured model, тела диалога, профилей,
guest/diagnostic tokens, SQL, prompts или файлов. Перед внешней передачей оператор
проверяет состав; частота/время событий остаются эксплуатационными метаданными.
Старый `scripts/demo_ready.py` сохранён; `--diagnostics` дополнительно проверяет
/readyz и защищённый endpoint, беря token только из окружения. Он не выполняет inference.

## Correlation и ошибки

Каждый дошедший до HTTP ASGI запрос получает **новый** случайный32hex `X-Request-ID`.
Входной X-Request-ID игнорируется независимо от синтаксиса: нет log injection и
подмены контекста чужого запроса. В ошибках добавлены top-level `code`, безопасное
`message`, `request_id`; прежний `detail` сохранён. 422 по-прежнему не отражает input,
ctx или произвольные ключи. Header Retry-After H-02 сохраняется только при известном
реальном window; queue429 не получает вымышленного времени ожидания.

| Событие | HTTP / code | Безопасное восстановление |
|---|---|---|
| Неизвестный route/невалидные параметры | 400/404/422 `http_<status>` либо domain code | Исправить запрос; owner404 не раскрывает существование чужого объекта |
| CAS / consent revision | 409 прежние domain codes | Перечитать состояние, проверить правки |
| Body limit / quota | 413/429 прежние H-02 codes | Уменьшить ввод / проверить quota; не создавать новые сессии ради обхода |
| Pool timeout | 503 `database_capacity_busy` | Проверить нагрузку/пул и повторить позже |
| DB connection/SQL operation | 503 `database_unavailable` | Проверить БД; повторную запись предварить чтением текущего состояния |
| Несовместимая схема / PostGIS | 503 `database_schema_incompatible` / `postgis_unavailable` | Проверить migration policy/расширения, не выполнять downgrade |
| Ollama недоступна | 503 `llm_unavailable` | Проверить сервис; текст сохранён, повтор вручную |
| Ollama chat404 | 503 `llm_model_missing` | Проверить модель и совместимость endpoint;404 само по себе не доказывает только отсутствие модели |
| Повторный HTTP500 сервера модели | 502 `llm_server_error` | Проверить локальный inference-сервис |
| Model response invalid / deadline | 502 `llm_invalid_response` /504 `llm_timeout` | Повтор вручную либо ручная правка профиля |
| Queue full / wait expired | 429 `llm_queue_full` / `llm_queue_timeout` | Дождаться ёмкости и повторить; без автоотправки |
| Cancellation / stale snapshot | Локальный499 /409, прежние codes | Сначала перечитать профиль; после commit ответ мог потеряться |
| Unexpected / unexpected report error | 500 `internal_error` / `export_failed` | Найти событие по ID; проверить metadata отчёта перед повтором |

Точное состояние «модель загружается» не определяется /api/tags. Оно не имитируется:
наблюдаем presence, bounded wait/timeout и отдельный результат настоящего запроса.
Ошибки до ASGI (недоступный backend, proxy failure, malformed HTTP) не могут получить
backend request ID. Frontend показывает безопасную network/timeout ошибку, не выдумывает ID.
Frontend принимает ID только32hex, добавляет его к существующему сообщению, сохраняет
чатовый draft; автоматических повторов записей нет. Скачивание также имеет безопасную
transport error и30s deadline; ошибки сети не раскрывают произвольный текст исключения.

## События, метрики и retention

Allowlist JSON event: timestamp UTC, severity, request_id, operation, status,
duration_seconds, code, application_version. Ни URL/query/IP/session ID, ни тела/headers,
ни exception string/stacktrace/SQL parameters в него не попадают. Форматтер сторонних
логов выдаёт только `external_log_suppressed`; подробности ищутся в собственном событии
запроса. По умолчанию Uvicorn access выключен, nginx access/error logs выключены, чтобы
не сохранять URL с секретами. Поэтому proxy diagnostics выполняются прямым /livez и
проверкой контейнера. SQLAlchemy hide_parameters=True, pool wait≤5s. Domain handlers
по-прежнему безопасны, неожиданные исключения перехватываются до Uvicorn traceback.
Исключение **после начала ответа** уже нельзя заменить500 на проводе; безопасный failure
event остаётся, а клиент должен обнаружить оборванный ответ. Streaming product endpoints
сейчас отсутствуют.

| Показатель | Источник / единицы | Просмотр / ограничения |
|---|---|---|
| Requests по operation/status class | ASGI boundary, число | bundle counts; latency total seconds, среднее=total/count, не p95 |
| Errors/quota/DB/export codes | allowlisted events, число | bundle codes≤65 buckets; overflow=other |
| Queue wait | получение FIFO lease, секунды | queue events/totals; rejects/timeout отдельные codes |
| Inference duration/result | существующая стадияB, секунды | inference events; не включает snapshot read/final write |
| Queue occupancy/limits | существующая FIFO | bundle active/waiting/limits, моментальный снимок |
| Pool checked out | SQLAlchemy QueuePool | bundle; DB probe использует отдельное connection |

Счётчики/суммы только в памяти **одного worker**, сбрасываются при рестарте; последних
событий≤32, поле code≤79 ASCII, buckets≤65. Нет user-keyed cardinality и накопления
body. Docker api/web json-file rotation10MiB×3; ротация применяется к новым контейнерам.
Нет долговременного p95, распределённых метрик, alert delivery или автоматического
отслеживания GPU. Backup status/RPO — отдельный проверенный инструмент H-04-FU;
диагностика приложения не переопределяет его результат и не читает private archives.

## Короткий runbook

1. `docker compose ps` и прямой `GET http://127.0.0.1:8000/livez`. Если недоступен —
   проверить состояние API, порт и Docker, не многократно отправлять пользовательские данные.
2. `GET /readyz`; при503 проверить DB health, bounded diagnostic bundle, затем
   `docs/MIGRATIONS.md`. Не удалять volumes, не применять сгенерированные DROP/downgrade.
3. Проверить локальный Ollama service (`ollama list`), доступность из API-контейнера.
   Изолированный CLI `docker compose exec -T api python -m app.readiness` выполняет
   probes без генерации и без печати endpoint/credentials.
4. Model `present` ещё не live PASS. Один согласованный короткий диалог должен
   вернуть `extraction_mode=ollama`; не публиковать его payload в логах.
5. Для очереди смотреть **работающий** protected bundle: active≤1, waiting≤configured
   limit. При таймауте/переполнении не устраивать retry storm и не менять worker count.
6. Найти ID из UI: `docker compose logs --tail 200 api | Select-String '<32hex-ID>'`.
   В выводе должны быть только безопасные JSON events. Не добавлять --verbose/SQL echo.
7. Для внешнего отчёта сохранить только проверенные bundle/allowlisted events;
   не собирать `.env`, docker inspect environment, raw DB/Ollama logs или private backups.
8. После восстановления повторить /livez, /readyz, opt-in model probe и одно безопасное
   чтение своего состояния. Перед повторной записью/заявкой перечитать version/receipt.
   Дефекты с утечкой/частичной записью блокируют продвижение; новые функции не включать.
