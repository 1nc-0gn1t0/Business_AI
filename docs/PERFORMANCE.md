# Business AI · измерения производительности

## H-03 · PostgreSQL во время inference · 26.10.2026

Источник: main559a193 (H-02 PR#20 merged), новая feature-ветка H-03. До изменения
message path повторён H-01 controlled probe в UUID-БД: **1 idle in transaction,
1 checked-out connection**, XFAIL. После исправления тот же desired assertion дал
XPASS, маркер снят: **0/0**, PASS. Assertions не ослаблены. Объективные значения:
[H-03-inference-pool.json](evals/H-03-inference-pool.json).

| Контролируемая проверка | Результат |
|---|---|
| Один блокирующий stub, до/после | idle transaction1→0, pool checked-out1→0 |
| Две независимые Session read/write | подтверждено; обе завершены после шага |
| pool_size1/max_overflow0, пять параллельных GET geo/datasets при inference | все200, 67.28…72.26ms; pool во время модели0, pg_stat_activity только idle без transaction |
| Два диалога + третья попытка | active1/waiting1; overflow429 без Retry-After/записи; max model concurrency1 |
| Ожидание с test wait=.05s | 429 за.0728s включая чтение; queued model calls0; повтор успешен |
| Смена города/бюджета |409, новая правка сохранена, старый inference не пишет history |
| revoke / revoke→grant |403 /409, старый результат не сохраняется |
| disconnect active/queued, timeout, post-flush SQL error | нет частичной записи, pool/slot освобождены; retry с актуальной версией проходит |

Это небольшой controlled probe, **не** p95/нагрузочный benchmark. Читатели выполняли
metadata lookup, а не пять тяжёлых ranking jobs. Исходный/повторный GET был25.83/17.67ms;
из одной пары нельзя делать вывод о приросте скорости. Суть проверки — возврат
единственного connection ещё до inference, не увеличение pool_size.

### Отдельная настоящая Qwen

Новая изолированная копия F-00, отдельные API8017/web5177; рабочие write API не использованы.
Qwen `qwen3:4b-instruct-2507-q4_K_M`, ID0edcdef34593, Q4_K_M, Ollama0.40.8.
Manual `live_inference_probe.py` вызывает настоящий message HTTP-handler через ASGI,
настоящие Ollama HTTP и PostgreSQL. Instrumentation оборачивает вызов только для
сигнала начала/конца, не заменяет вход/выход/транспорт модели. Отдельный inspector
подключён к postgres; каждые50ms внутри inference измеряются QueuePool.checkedout и
pg_stat_activity целевой БД. Граничные выборки, попавшие в завершение inference, исключены.

**538 выборок, peak checked-out0, peak idle-in-transaction0; request27.609s**.
Правильно извлечены кофейня/Казань/2000000.00₽. Это один live turn, не оценка p95,
не классифицированный cold/warm benchmark и не повтор полного BA-016 evaluation.
Цель warm p95≤15s этой выборкой не доказана. Реальные Chromium E2E: **3 PASS/57.4s** —
пекарня500тыс/Казань, автосервис10млн/Самара без покрытия, полная кофейня/Казань2млн:
профиль/OSM/сеть/финансы/каталог/consents/mock receipt/PDF+JSON без console pageerrors.

### Воспроизведение

```powershell
docker compose --profile test run --build --rm db-tests /app/.venv/bin/python -m pytest tests/integration/test_h01_triage.py tests/integration/test_inference_lifecycle.py -q -s -p no:cacheprovider
# Только заранее созданная isolated copy: f00_restore_h03_<32 hex UUID>.
# Сначала backup_postgres.py restore согласно BACKUP_RESTORE.md, никогда working DB.
docker compose --profile test run --no-deps --rm -e PGDATABASE=<isolated-db> -e LLM_PROVIDER=ollama -e OLLAMA_BASE_URL=http://host.docker.internal:11434 db-tests /app/.venv/bin/python -m tests.integration.live_inference_probe
$env:BA010_REAL='1'
$env:BA_TEST_WEB_URL='http://127.0.0.1:5177'
$env:BA010_ARTIFACT_DIR=Join-Path $env:TEMP 'business-ai-h03-browser'
npm --prefix apps/web run test:e2e
```

Proxy QA web должен ссылаться **на именованный QA API**, не на `api` alias общей
Compose-сети, иначе можно попасть в рабочую БД. Секреты не помещать в command args,
артефакты/логи; guest key только в памяти/sessionStorage. Backup F-00 SHA не менялся.
8-hour soak/5-heavy-client load/полная cancellation GPU внутри Ollama/распределённая
очередь не проверялись и не заявлены. QG-OPS подтверждён в части H-03 connection lifecycle,
bounded queue и responsiveness; остальные проектные targets остаются Q-04/RC.

## BA-016 · исторические измерения

25.10.2026. Это малый локальный benchmark, не нагрузочный тест и не production SLA.

## Окружение

Windows + Docker Desktop/WSL2, Docker Engine 28.0.1, Python 3.12, PostgreSQL 17/PostGIS 3.5,
16 ГБ RAM хоста; лимит Docker VM около 7.64 GiB. RTX 3050 Ti Laptop 4096 MiB,
драйвер 617.14. Ollama 0.40.8, только `qwen3:4b-instruct-2507-q4_K_M` (Q4_K_M).
`ollama ps`: 2.9 GB, 18% CPU / 82% GPU, context4096; это частичный offload.
Снимок `nvidia-smi`: 2362 MiB VRAM занято; Docker stats: Ollama2.833 GiB,
Postgres311.8 MiB, тестовый API70.15 MiB. Это наблюдения, не верхние границы памяти.

LLM: temperature0, seed42, num_predict384, think=false, keep_alive10m,
серверный timeout120 с, клиент 190 с. Модель не скачивалась и не заменялась.

## Задержки настоящей Qwen через Business AI HTTP

Не включены короткие подтверждения без inference. Цифры содержат извлечение,
валидацию и транзакцию; HTTP wall time не равен GPU inference time.

| Прогон | Обращений к модели | Медиана | p95 nearest rank | Максимум |
|---|---:|---:|---:|---:|
| Первый полный | 117 | 5.203 с | 9.110 с | 71.312 с |
| Повторный полный | 117 | 5.360 с | 8.922 с | 11.672 с |
| Выбранные повторы | 18 | 6.375 с | 8.938 с | 8.938 с |

71 с — первый запрос первого прогона; он включает холодный старт/прогрев, его
не вычёркивали. Причина задержки по GPU kernel traces не исследовалась.
Стабильный median не означает отсутствие ошибок: LLM-022/028 стабильно неверны.

## Небольшой последовательный API benchmark

[Сырые замеры](evals/BA-016-benchmark.json). Для каждого endpoint один исключённый
warm-up и пять запросов без параллельной LLM/нагрузки. Указанный p95 при n=5 фактически
максимум, поэтому его нельзя трактовать как надёжную оценку хвоста распределения.

| Операция | Медиана, мс | Максимум / coarse p95, мс |
|---|---:|---:|
| health/PostGIS | 42.522 | 49.690 |
| Генерация + рейтинг пяти зон | 210.429 | 256.326 |
| Catchment600 м, реальный граф | 296.325 | 345.245 |
| Три финансовых сценария/чувствительность | 28.961 | 33.131 |
| Финансовый отчёт PDF+JSON/сохранение | 136.855 | 196.685 |

Fingerprint ranking/catchment/finance стабилен на всех пяти повторениях.
Отчёт benchmark — **только финансы**, не полный геоотчёт на 12 страниц;
созданы 6 локальных снимков в отдельной тестовой беседе. Полный real browser suite:
3 сценария/133.63 с, включая cold Qwen, карту, UI ожидания и скачивания.

Дополнительная реальная walking-проверка трёх точек Казани/600 м:
49.119,55.788 →569 достижимых POI; 49.132,55.789 →159; 49.155,55.788 →308.
Один кандидат попал в компоненту из 8 узлов и **не получил** сетевой рейтинг;
это ограничение графа, не доказательство физической недоступности.

```powershell
uv run --locked --project apps/api python scripts/benchmark_local.py --output tmp/ba016-benchmark.json
uv run --locked --project apps/api python scripts/eval_walking.py --api http://127.0.0.1:8016 --output tmp/ba016-walking.json
```

Benchmark разрешён только на изолированном localhost:8016, использует явные
синтетические финансовые допущения и реальные локальные OSM. Никаких банковских вызовов.
Не измерены: concurrency SLA, длительный soak, холодный PostgreSQL/все cache misses,
полная память процесса по времени. Vite сохраняет прежнее предупреждение о большом
MapLibre chunk (~1.4 MB); оптимизация bundle не входила в исправления BA-016.
