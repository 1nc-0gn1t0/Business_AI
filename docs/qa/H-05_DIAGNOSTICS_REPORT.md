# H-05 · Safe diagnostics · 27.10.2026

Ветка `codex/H-05-safe-diagnostics`, base365bff3. PR23/a50e6da merged, проверено
GitHub REST; main ff-only, исходное дерево чистое. Одна задача, без H-06/BA-017/018.
Инвентаризация до реализации и checkpoints: [checkpoint](H-05_CHECKPOINT.md).
Контракты/retention/troubleshooting: [DIAGNOSTICS](../DIAGNOSTICS.md).

## Реализация

- Pure ASGI wrapper с server-generated request ID, additive error envelope и
  allowlisted structured events. Успешные bodies/PDF/JSON snapshots не изменяются.
  Порядок: diagnostic boundary → H-02 limits → handlers; ранние413/429 тоже имеют ID.
- Отдельные /livez, /readyz; legacy /healthz сохранён. Protected diagnostics по
  отдельному≥32-character token, default404. No inference в probes; present≠live PASS.
- Бounded counters/totals, последних32 событий, максимум65 code buckets, process-local
  queue/pool снимок. CLI честно сообщает, что его counters относятся к новому процессу.
- H-03 stageB duration и queue wait; DB phases/CAS/ownership/consent/atomic writes не
  перепроектированы. Pool timeout5s, hide SQL parameters; model404/server500 коды.
- Raw access/proxy errors отключены, JSON Docker logs10MiB×3. Сторонний exception text
  не форматируется. Ошибка после headers отмечается severity=error при фактическом200,
  поскольку уже отправленный status изменить нельзя; это отдельно проверено.
- Frontend показывает проверенный32hex ID, новые понятные model/pool/export ошибки;
  сохранение draft и явный ручной retry. Download network exception sanitized.
  OpenAPI/TS regenerated,87 additive lines, прежние v1 поля не удалены.

Исполняемый diff больше ориентира300 строк: атомарная цель включает общую ASGI границу,
probes/access guard и минимальные интеграционные точки. Нет новых зависимостей,
таблиц/миграций, инфраструктурных сервисов или изменений продуктовых алгоритмов.

## Fault injection и восстановление

[Агрегаты](H-05-evidence.json) содержат только безопасные измерения, без credentials,
профилей, prompts и payload. Native Docker28.0.1/WSL2, Windows/i7-11800H/16GB,
RTX3050Ti4GB; один API worker. Отдельный UUID Compose project, новая тестовая БД/volume,
порты18005/15175, отдельные h05 image tags; рабочие сервисы не пересоздавались.

| Сценарий | Фактический результат |
|---|---|
| PostgreSQL остановлен только в QA project | /livez200, /readyz503 database_unavailable за4.015s |
| Запись при DB down, затем recovery |503; после запуска /readyz200, тот же профиль и count сессий |
| Отсутствующая Qwen в настоящей Ollama |503 llm_model_missing за0.109s; профиль не изменён; bundle degraded/model missing |
| Ollama endpoint закрыт в QA config |503 llm_unavailable за0.360s; профиль не изменён; bundle degraded/model unknown |
| API body>limit |413 request_body_too_large, ID; session count не вырос |
| Отрицательный budget |422 http_422; ввод не отражён; профиль не изменён |
| Возвращены обычные настройки | DB ok/model present, ready_unverified, inference not_tested |
| Schema0007 / extension missing | Реальная изолированная БД:503; upgrade head→200; без idle in transaction |
| Pool exhausted | Контролируемый SQLAlchemy PoolTimeout→503 database_capacity_busy; нет raw exception |
| Dependency timeout/malformed/oversized tags | Mock transport: bounded safe unknown; не выполняется generation |
| Queue full/wait expired/cancellation | Существующие real-Postgres H-03 tests PASS; no partial writes/slot leaks |
| SQL error после flush | H-01/H-03 rollback+audit/receipt assertions PASS; ID и safe503 |
| Unexpected/export exception | Изолированный ASGI fault→500 internal_error/export_failed, без traceback/marker |
| Неавторизованный bundle |404 до probes, неверный/короткий/отсутствующий token не открывает данные |
| Error/log sentinels |25 diagnostic tests, безопасный formatter; реальные fault API logs без tokens/markers |

Экспортная ошибка инъецирована контролируемой route exception, а не повреждением
рабочих snapshots. GPU timeout/invalid model responses проверены transport/stub tests;
реальную Ollama не перегружали и её глобальный сервис не останавливали.

## Настоящая Qwen, отдельно от mock

`qwen3:4b-instruct-2507-q4_K_M`, фактический `extraction_mode=ollama`, HTTP200:
«Хочу открыть кофейню в Казани. Бюджет — 2 миллиона рублей» → Казань/кофейня/
Decimal2000000.00. Измеренный warm запрос **8.094s**;34 telemetry samples во время
active inference, pool_checked_out peak0. Bundle DB probe использует отдельное
закрываемое соединение; idle-in-transaction и общий CAS/rollback отдельно проверены
реальными PostgreSQL-тестами. Это один выбранный smoke, не новая массовая оценка
качества/p95 и не доказательство соответствия всем QG-OPS targets.

Две первоначальные проверки measurement harness завершились AssertionError:
сравнение строки2000000.00 с2000000 и подсчёт pool peak **всех** стадий вместо
active inference. Проверен сохранённый синтетический профиль: модель извлекла поля
корректно. Исправлена только проверка (Decimal и active-phase sampling), повтор PASS;
ошибка модели/бизнес-логики этими assertions не подтверждена.

## Регрессия и воспроизведение

Команды из корня repo (логам не нужны credentials):

```powershell
uv run --locked --project apps/api pytest apps/api/tests -m 'not extended' -q
uv run --locked --project apps/api pytest apps/api/tests -m extended --hypothesis-show-statistics
uv run --locked --project apps/api pytest apps/api/tests/test_diagnostics.py -q
# db-tests с актуальными app/migrations/tests bind mounts, как в H-04:
docker compose --profile test run --rm --no-deps `
  -v "${PWD}/apps/api/app:/app/app:ro" `
  -v "${PWD}/apps/api/migrations:/app/migrations:ro" `
  -v "${PWD}/apps/api/tests/integration:/app/tests/integration:ro" `
  db-tests /app/.venv/bin/python -m pytest tests/integration -q -p no:cacheprovider
npm --prefix apps/web test
npm --prefix apps/web run test:e2e
npm --prefix apps/web run build
prek run --all-files
```

Для crypto tests нужен реально установленный age1.3.2 (`BA_AGE_BINARY` из приватного
tools path), только disposable test keys; при Windows temp ACL conflict — новый
PYTEST_DEBUG_TEMPROOT, без изменения старых ACL. Нет реального backup-key в fixtures.

- Backend final quick: **359 PASS /104 DB SKIP**, extended102 отдельно.
- PostgreSQL/PostGIS: **104 уникальных PASS**:100 сразу,4 после обновления exact-body
  assertions под additive envelope; затем14 readiness/H-03 tests повторены PASS на
  финальном probe path. Четыре первоначальных FAIL не скрыты: их detail/rollback/hash
  assertions не ослаблены, добавлена проверка ID. Новых DB SKIP/XFAIL в реальном run нет.
- Extended: **102 PASS**,1550 passing Hypothesis examples; финансовые/гео golden не менялись.
- Frontend: **45 PASS**; Chromium mock **27 PASS**, включая390px, ошибки и request ID;
  Firefox/WebKit не запускались: navigation/forms/download protocol не менялись.
- Ruff/format/mypy122 files, TypeScript, build, семь prek hooks PASS. Первый prek
  заметил параллельное изменение файлов при выполнении hooks; повтор без параллельных
  source edits PASS. Это не игнорированный lint failure.
- Isolated Compose build/smoke PASS: API/web legacy health, schema readiness, React assets,
  protected bundle и настоящая Qwen. Известный Vite large chunk warning остаётся.
- CI exact HEAD сверяется после push/PR; до результата не считать CI подтверждённым.

## Gates, ограничения и сохранность

QG-PR/QG-SAFE: targeted negative/owner/error/ASGI tests, стандартная регрессия и
документация. QG-OPS выполнен в **diagnostics subset**, не весь8h soak/p95/DR/RC gate.
Новых подтверждённых P0 в разрешённых проверках нет; полного pentest не проводили.

Нет promises distributed monitoring: worker1, RAM counters сбрасываются; permanent
alerting отсутствует. /livez не certifies dependencies, /readyz не certifies качество
Qwen/OSM/банковских условий. Подробности недоступны до ручного выбора operator token.
Сбор сырых PG/Ollama/host logs не входит в безопасный bundle. Ошибки до ASGI ID не имеют.
CLI workers/replicas/direct Ollama clients не координируются. H-06/scanners и R-12
key custody/offsite/реальное расписание остаются открытыми.

Baseline F-00/private archive проверен SHA-256:
`690133a959640c3ee0167c46bc39eea13b966f2fff615f4158c10eda85e74feb` — прежний.
Рабочие containers/пользовательские volumes сохранены. QA containers остановлены;
автоматическая проверка отклонила удаление QA volume (`blocked by policy`, без
подробной причины), поэтому новый synthetic volume/private TEMP context сохранён.
Удаление не обходилось. Это не blocker реализации H-05; оператор может проверить
сохранённый QA project перед своей очисткой. Не выдавать локальную диагностику за RC.
