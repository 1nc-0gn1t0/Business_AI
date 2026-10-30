# Миграции и возврат совместимого приложения · H-04

**U-05,30.10.2026:** head/readiness `0012_financial_scenarios`. Additive owner-FK
tables `financial_workspaces/actions/results`, bounded JSON checks, owner/time indexes
and idempotency/result fingerprint uniqueness. No v1 profile/finance/report bytes are
rewritten. Populated/repeated upgrade and immutable old report regression PASS; new
tables are seeded via real APIs on a separate generic fixture project. No user-data
downgrade was run. Enable BA_FINANCE_V2_ENABLED only after upgrade and industry review;
application rollback disables flags rather than dropping financial history.
[Contracts and limits](architecture/BUSINESS_AI_2_FINANCIAL_SCENARIOS.md).

**U-03,29.10.2026:** актуальный head/readiness `0010_agent_runs`, одна additive owner-FK
таблица ограниченных traces/idempotency/grants. Profile/geo/finance/report данные не
меняются. Populated upgrade/repeated head/report-byte preservation прошли целевую
регрессию; H-04 fixture включает terminal synthetic agent run без model/network calls.
Rollback приложения отключает feature flag, а не запускает destructive downgrade.
[Контракты](architecture/BUSINESS_AI_2_QWEN_TOOL_AGENT.md).

**U-02,29.10.2026:** текущий head/readiness теперь `0009_acquisition` — три additive
таблицы jobs/requests/events. Проверены populated0008→0009, repeat head/check и hashes
прежних записей. Ни geo objects, ни immutable reports не мигрируются. Ниже сохранён
исторический протокол H-04; он не означает автоматический upgrade рабочей установки.
[Изменения и безопасный запуск worker](architecture/BUSINESS_AI_2_DYNAMIC_ACQUISITION.md).

26.10.2026. Только PostgreSQL17/PostGIS3.5, приложение в `public`. Не разрешает
автоматическое обновление/переключение рабочей БД. [Backup runbook](BACKUP_RESTORE.md).

## Поддерживаемый переход и контракты

- Для текущего head `0008_analytical_reports` проверен заполненный predecessor
  `0007_data_providers`. У 0007 нет таблицы отчётов: они создаются **после** upgrade,
  затем проверяются при повторном upgrade и restore. Отчёт на 0007 не «восстановлен».
- App H-03 требует 0008 для всех функций. Его report route на 0007 возвращает
  безопасный503 `database_unavailable`, без записи. `/healthz` не является schema
  compatibility gate. Версию сверять отдельно **перед** включением приложения.
- Исторические миграции не переписаны. Новые изменения: expand → backfill → switch
  → отдельно согласованный contract. Nullable/additive stage сохраняет чтение
  прежнего приложения; это проверяется для каждого будущего перехода, не обещается
  произвольная обратная совместимость. Не изменять immutable JSON/PDF snapshots.
- Изменение нескольких таблиц выполняется транзакционно. `CREATE INDEX CONCURRENTLY`,
  `autocommit_block`, внешние действия и backfill требуют отдельного плана частичного
  сбоя, checkpoint/retry/cleanup. H-04 доказывает **текущие transactional migrations**.

## Операторский порядок обновления

1. Один оператор; остановить новые записи и фоновые импорты на время DDL. Записать
   git SHA, immutable image ID/digest прежнего приложения, schema revision, версии
   PostgreSQL/PostGIS. Не полагаться на `latest`; не удалять старый образ.
2. Создать новый приватный backup, проверить SHA, восстановить его в **новую** БД
   по BACKUP_RESTORE. Убедиться, что место на диске позволяет хранить обе копии.
3. На копии запустить целевой образ migration CLI с `PGDATABASE=<copy>`:
   `alembic current`, `alembic upgrade head`, `alembic check`, повторный upgrade.
   PG* передаются средой/защищённым env-файлом; не писать URL/пароли в команды/логи.
4. Проверить counts/hashes/FK/unique/indexes, геометрии, старые snapshots, owner и
   foreign-owner отказ, байты PDF/JSON и mock-квитанции. Инструкции воспроизведения ниже.
5. Просмотреть миграционный SQL вручную. `alembic check` — проверка ORM drift, **не**
   доказательство безопасности DDL; enums/check constraints/functions/grants требуют
   отдельного просмотра и SQL-тестов. Autogenerate никогда не применять вслепую.
6. Только после проверки копии владелец выполняет upgrade рабочей БД целевым образом.
   Настроить разумный `lock_timeout` через PGOPTIONS на время maintenance; значение
   подбирать по конкретной миграции. Длинный backfill не запускать с бездумным timeout.
7. Сверить revision и выполнить read/export/owner smoke, затем открыть запись. Если
   stage не прошёл — держать affected app выключенным, сохранить backup/ошибки приватно.

`docker compose up` запускает migration dependency. До планового обновления заполненной
БД перечисленные шаги обязательны; Compose сам не создаёт backup и не проверяет
совместимость произвольных app/schema версий.

## Сбой и app rollback

- После SQL error/потери соединения дождаться завершения backend/rollback. Проверить
  `alembic_version`, фактические объекты и committed counts/hashes, а не только exit code.
- В тестах 0008 после create_table прерывается делением на ноль и отдельно
  `pg_terminate_backend` во время `pg_sleep`. Таблица/новая revision не коммитятся;
  прежняя запись остаётся. Повторный обычный upgrade проходит. Убивается **только**
  backend с уникальной тестовой БД и `application_name=h04-fault`.
- Если transactional rollback полон и схема совместима со старым образом — вернуть
  зафиксированный образ, выполнить read smoke, затем разрешить записи.
- При contract migration/неясном частичном состоянии: остановить writers, сохранить
  аварийную БД, восстановить pre-upgrade backup в **новую** БД; проверить её прежним
  совместимым образом. Переключить PGDATABASE только вручную после owner/export smoke.
  Записи после snapshot могут быть потеряны; reconciliation/WAL/PITR не реализованы.
- Проверен реальный F-00 image ID из baseline на восстановленной 0008: профиль,
  чужой owner отказ, квитанция и byte-identical PDF/JSON. Это **read-only compatibility
  smoke**, не рекомендация возвращать старые H-01…03 дефекты или полная сертификация rollback.
- CLI `alembic downgrade` запрещён по умолчанию **до подключения**. Единственное
  исключение: `-x allow_test_downgrade=true` плюс PGDATABASE, точно соответствующая
  `business_ai_test_<32hex>` или `ba003_test_<32hex>`. F-00 restore copies не подходят.
  Это защита от ошибки оператора, не DB authorization: прямой SQL/программный Alembic
  способны её обойти. Programmatic callers обязаны применять ту же политику.

## D-04: PostGIS/TIGER

Причина: PostgreSQL inspector отражал видимые TIGER tables из inherited search_path
как default-schema tables; ORM их не содержит и Alembic предлагал DROP. В env.py
теперь session search_path и dialect default schema фиксируются на `public`;
таблицы, принадлежащие расширениям в public, исключаются через `pg_depend/pg_extension`.
Остальные public tables, включая неизвестные ORM, **не** исключены.

Тест создаёт настоящее расширение `postgis_tiger_geocoder` и search_path `public,tiger`.
Со старым env `alembic check` FAIL (ложные remove_table); с новым PASS. После добавления
лишней таблицы и столбца приложения check снова FAIL с remove_table/remove_column.
Сгенерированные destructive migrations не выполняются. Существующие extensions/данные
не удаляются, search_path рабочей БД/роли не меняется.

Ограничение: app tables в иных schemas этот policy не проверяет; при переходе к
multi-schema нужен отдельный ADR, metadata schemas/include_schemas и regression.
`alembic check` не проверяет сами таблицы расширений; их обновление — отдельная процедура.

## Воспроизведение автоматических проверок

```powershell
docker compose --profile test run --build --rm db-tests
```

Новые `test_populated_upgrade.py`: populated 0007→0008/replay; все 17 app tables
заполнены; FK/unique реально отвергают нарушения; hashes включают JSONB/bytea PDF,
provenance, consent revisions/withdrawal, drafts/receipt/audit, geo/graph/provider.
Два owner проверяются до/после; старые snapshots валидируются существующими DTO.
Дополнительно SQL failure, backend termination, запрет downgrade, отсутствующий
DB user и недоступный адрес → safe503. Working DB не является test target.

## Ручной backup drill с той же фикстурой

Сначала создать `$taskPrivate` с ACL по BACKUP_RESTORE. Он находится **вне Git**.
Файл `fixture-state.json` содержит только новые тестовые credentials, но всё равно
приватный: не публиковать/не прикладывать к CI. Helper запускается root только для
доступа к его файлу0600 в приватном bind mount; приложение продолжает работать app user.

```powershell
$taskSource = 'f00_restore_h04_' + [guid]::NewGuid().ToString('N')
$taskTarget = 'f00_restore_h04_' + [guid]::NewGuid().ToString('N')
docker compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" --template=template0 "$1"' -- $taskSource
if ($LASTEXITCODE) { throw 'Choose a fresh source; do not reuse an existing DB' }
docker compose --profile test run --build --rm --no-deps --user root -v "${taskPrivate}:/private" db-tests /app/.venv/bin/python -m tests.integration.h04_drill seed --database $taskSource --private /private
if ($LASTEXITCODE) { throw 'Seed failed; preserve private artifacts for diagnosis' }
$taskArchive = Join-Path $taskPrivate 'snapshot'
uv run --locked --project apps/api python scripts/backup_postgres.py backup --directory $taskArchive --database $taskSource
if ($LASTEXITCODE) { throw 'Backup failed' }
uv run --locked --project apps/api python scripts/backup_postgres.py verify --directory $taskArchive
if ($LASTEXITCODE) { throw 'Checksum mismatch' }
uv run --locked --project apps/api python scripts/backup_postgres.py restore --directory $taskArchive --database $taskTarget
if ($LASTEXITCODE) { throw 'Restore failed; do not switch application' }
docker compose --profile test run --rm --no-deps --user root -v "${taskPrivate}:/private:ro" db-tests /app/.venv/bin/python -m tests.integration.h04_drill verify --database $taskTarget --private /private
if ($LASTEXITCODE) { throw 'Restored application semantics differ' }
```

`--database` для backup — только явно выбранная QA source с `f00_restore_` prefix;
без опции сохраняется F-00 поведение (штатная working DB, read-only snapshot).
Для отказа/прерывания миграции повторить автоматические fault tests; не редактировать
installed migration history и не переносить fault injection в рабочий контейнер.
Реальные H-04 агрегаты: [evidence JSON](evals/H-04-migration-restore.json).

## Запрещено на рабочей БД

Destructive downgrade, `DROP DATABASE`, `pg_restore --clean/--create`, volumes removal,
тестовые faults, конкурентные migration operators, arbitrary autogenerate execution.
Не заменять backup директорию и не удалять baseline ради освобождения места. Для
очистки QA сначала сверить **полное UUID-имя**, provenance создания и отсутствие
нужных данных; сохранять рабочую/старые QA БД. Скрипт restore сам ничего не удаляет.

## 0011_industry_profile · BA2/U-04

Добавляет `industry_profiles(profile_id PK/FK → business_profiles.id ON DELETE CASCADE,
document JSONB)` и object/48KiB constraint. Счётчик версии/owner/consent остаётся у
существующего conversation. Старые строки business_profiles и immutable reports не
переписываются. Перед opt-in BA_INDUSTRY_ENABLED=1 примените upgrade head по обычному
runbook. Повторный upgrade безопасен; рабочий downgrade не выполняйте.
