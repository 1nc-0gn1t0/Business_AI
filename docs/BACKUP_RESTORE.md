# Локальный PostgreSQL backup и изолированный restore · F-00

Область: одна БД текущего Compose, PostgreSQL/PostGIS 17/3.5. Никаких DROP,
`--clean`, восстановления поверх существующей БД или удаления volumes.
Реальные результаты: [F-00 baseline](baselines/F-00_BASELINE.md).
Это on-demand процедура, не выполненная H-04 и не production backup policy.

## Предусловия

- Запускать из корня repo; Docker Desktop, штатные db/api запущены, зависимости
  `uv sync --locked --project apps/api` уже установлены. Тесты — в отдельных БД.
- Доверенный локальный источник/архив; restore выполняет SQL из архива.
  Не принимать dumps из неизвестного источника.
- Не запускать DDL/migrations/imports и sequence-changing writers во время backup.
  Обычные concurrent writes покрывает единый exported snapshot. Работающие writers
  на UUID-таблицах не требуют выключения приложения.
- На диске достаточно места для архива, metadata и новой БД. Dump содержит
  переписку/профили/consents/token hashes и должен храниться **вне Git**, с ACL;
  скрипт не шифрует данные. Перед переносом использовать согласованное encrypted
  storage. Нет cluster roles/ACL/tablespaces/WAL/PITR/model volume backup.

## Windows: создать новый приватный каталог и backup

```powershell
# Каждый запуск имеет новый parent; не применять ACL к чужому существующему каталогу.
$taskId = [guid]::NewGuid().ToString('N')
$taskPrivate = Join-Path $env:LOCALAPPDATA "BusinessAI/backups/$taskId"
New-Item -ItemType Directory -Path $taskPrivate -ErrorAction Stop | Out-Null
$taskAccount = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskGrant = '{0}:(OI)(CI)F' -f $taskAccount
icacls $taskPrivate /inheritance:r /grant:r $taskGrant
if ($LASTEXITCODE -ne 0) { throw 'Private directory ACL failed' }
$taskArchive = Join-Path $taskPrivate 'snapshot'
uv run --locked --project apps/api python scripts/backup_postgres.py backup --directory $taskArchive
if ($LASTEXITCODE -ne 0) { throw 'Backup failed; retain partial artifacts for diagnosis' }
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $taskArchive 'database.dump')
```

`backup.json` содержит SHA/размер/время, source DB/role, public table fingerprints,
schema fingerprint и версии extensions. Успех — exit 0 и готовые оба файла.
Partial folder не перезаписывается: исправить причину и выбрать новый каталог.
Не публиковать dump/metadata целиком без отдельной проверки состава.

Binary pg_dump stdout идёт прямо в Python file handle, не через текстовый PowerShell
pipeline. `pg_dump -Fc --no-owner --no-acl --snapshot=<held snapshot>` использует
тот же repeatable-read snapshot, что и source counts/hashes. Capture connection
закрывается после dump; idle timeout ограничен. Предел команды — 600 с, lock wait — 5 с.

Скрипт выбирает **единственный running non-oneoff** контейнер каждой service;
обычный `docker compose exec api` при существующем `compose run api` может выбрать QA.
При нескольких штатных API/DB контейнерах скрипт отказывает, не угадывает источник.
Пароли остаются в существующем PG* окружении контейнера; URL с паролем не создаётся.

## Восстановить только в новую изолированную БД

```powershell
$taskRestoreDb = 'f00_restore_' + [guid]::NewGuid().ToString('N')
uv run --locked --project apps/api python scripts/backup_postgres.py restore --directory $taskArchive --database $taskRestoreDb
if ($LASTEXITCODE -ne 0) { throw 'Restore/verification failed; keep target for diagnosis' }
```

Прежде чем создавать target, проверяется archive SHA-256. Разрешены только
`f00_restore_[a-z0-9_]{1,48}`; `createdb --template=template0` отказывает существующей
БД. Затем `pg_restore --single-transaction --exit-on-error --no-owner --no-acl`.
Нет `--create`: имя из архива не может перенаправить restore в рабочую БД.

После restore сравниваются rows/SHA каждой public table (JSONB text sorted with C
collation), columns/constraints/indexes/sequence values, extension/server versions
и число invalid indexes. Это проверка структуры и данных приложения, не логическое
доказательство семантики любого расширения. JSON-отчёт `<target>.json` рядом с архивом
имеет PASS/FAIL. Existing target/report никогда не перезаписываются; при ошибке
новый target/partial artifacts остаются для диагностики, удаления автоматически нет.
Schema mismatch не исправляется autogenerate/drop командами.

Database/role settings (search_path/permissions), cluster globals и инфраструктура
не переносятся этой процедурой. Нужные настройки проверять отдельно перед ручным
переключением приложения; приложение автоматически на restored DB не переключается.
Потерянный guest token backup не восстанавливает: в БД хранится только его hash.

## Проверки F-00 и окончание QA

F-00 проверила два restore: `_a1` для real browser QA, `_a2` как нетронутую reference
copy. В `_a2` дополнительно прочитаны и проверены хеши 5 исторических reports и 12
mock receipts. Все source public fingerprints после QA совпали с backup.

Для отдельного HTTP QA можно создать **с новым именем и свободным портом** API,
указав `PGDATABASE=<target>` через `compose run -e`, а Vite — `BA_TEST_API_URL`.
До запуска browser проверить фактическую DB через `docker exec <точное QA-имя>`.
Не включать tokens в traces/HAR/logs. В F-00 использовались QA API 8017/Vite 4175;
после проверок эти созданные F-00 процессы остановлены, БД и volumes сохранены.

Не менять source volume и не удалять прежние eval containers ради orphan warning.
Очистку собственных QA-копий выполнять позже только осознанно, после приёмки результата.

Руководства: [PostgreSQL 17 pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html),
[pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).
Custom archive восстанавливается pg_restore; роли/настройки кластера — отдельная задача.
