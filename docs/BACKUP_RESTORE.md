# Локальный PostgreSQL backup и изолированный restore · F-00 / H-04

Область: одна БД текущего Compose, PostgreSQL/PostGIS 17/3.5. Никаких DROP,
`--clean`, восстановления поверх существующей БД или удаления volumes.
Реальные результаты: [F-00 baseline](baselines/F-00_BASELINE.md).
Процедура F-00 переиспользована в H-04; это on-demand backup одной БД, не production
DR/PITR. [Миграционная политика](MIGRATIONS.md), [результаты H-04](evals/H-04-migration-restore.json).

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

## H-04: safeguards и результаты, 26.10.2026

Переиспользованы F-00 `pg_dump -Fc`, exported snapshot, aggregate fingerprints,
выбор единственного штатного контейнера, new-target/transactional restore. Формат
`f00-pgdump-v1` сохранён; старый baseline не переписан. Добавлены:

- `verify --directory <private>` — SHA-256 и размер (если записан в manifest),
  без подключения к БД. Symlink files отвергаются. SHA — обнаружение повреждения,
  **не** аутентификация: dump и manifest должны поступать из доверенного хранилища.
- `backup --database f00_restore_<id>` — опциональный явный источник QA; working
  names здесь запрещены. Без флага — прежний штатный источник, только чтение.
- Private files0600 на POSIX; на Windows необходим ACL родительского каталога
  по инструкции выше (chmod не заменяет NTFS ACL). В H-04 проверено: inheritance
  отключено, доступ только текущему оператору. Не менять ACL существующих baseline.
- Restore report отдельно измеряет `restore_seconds` (createdb+pg_restore) и
  `verification_seconds` (Docker worker/schema/count/hash); старое суммарное поле
  `restore_verify_seconds` сохранено. Ошибки subprocess скрывают stderr/SQL/data.

На новой заполненной фикстуре проверены все17 app tables + alembic_version и
spatial_ref_sys: source/target rows, SHA, schema, indexes/extensions/server version
совпали. Среди данных:2 profiles,4 messages,4 revisions,5 consents,2 drafts,
1 receipt,9 audit events,1 report,153 POI,1 polygon,5 walk edges,1 provider dataset.
Данные пользователя синтетические; маленький OSM input — уже хранимая test fixture,
граф — синтетическая топология. Нет нового Overpass/банковского вызова.

После смоделированной ошибки DDL восстановлена новая БД; API ownership и foreign
owner отказ, старая квитанция, кириллица/₽, PDF/JSON byte hashes PASS. Отдельные
Alembic tests проверяют rollback actual0008 после SQL error/termination и retry
**с 0007**. Эти проверки не смешиваются: full dump H-04 сделан уже после upgrade.
Повторный restore в existing target отказал; checksum-valid, но невалидный pg archive
оставил новую пустую БД (0 public tables). Никакой автоматической очистки при сбое.

Размер архива117876 bytes, backup3.437s, restore1.125s, verification2.156s, вместе3.281s.
PostgreSQL17.5/PostGIS3.5.2; i7-11800H, host RAM16GiB, Docker16 CPUs/7.64GiB RAM,
GPU не используется. Полные hashes/counts: [H-04 JSON](evals/H-04-migration-restore.json).
У F-00 archive5.95MB и restore15.093s остаётся отдельное более крупное evidence;
H-04 не переизмеряет его и не выдаёт меньший drill за production RTO.

**RPO/RTO:** QG-OPS ставит RC-цели ≤24h/≤60min. DB-only restore этого fixture меньше
60min, но общий RTO с восстановлением машины/образов/модели и переключением **не измерен**.
Планировщик/мониторинг backup/PITR отсутствуют: реальный RPO = возраст последнего
пригодного snapshot; потеряются все последующие committed writes. В данном drill
writers остановлены, потери snapshot-данных нет. RPO≤24h и полный QG-OPS **не достигнуты**.

## Политика шифрования и хранения (ещё не внедрена)

Архивы F-00/H-04 **не зашифрованы**. ACL защищает локальный доступ, не украденный диск,
администратора или скопированный архив. Не передавать/offsite незашифрованные копии.

Отдельный эксплуатационный блок **OPS-ENC**, до RC/любого переноса backup, оценка2–4ч:

1. Оператор выбирает место ключа и резервную офлайн-копию. Использовать
   [age](https://github.com/FiloSottile/age), BSD-3-Clause, recipient encryption с X25519;
   не собственную криптографию. Проверить release/целостность бинарника и зафиксировать
   его версию. Это операторский инструмент, не новая runtime-зависимость API.
2. `age-keygen -o <private-key-path>` в отдельном ACL-protected каталоге **вне Git и
   backup directory**. В unattended backup доступен только public recipient;
   identity/private key остаётся у оператора на зашифрованном носителе. Не env var,
   не CI secret artifact, не команда с literal key. Публичный recipient не секрет,
   но его fingerprint оператор сверяет независимо при замене/ротации.
3. Упаковать dump+manifest в один архив приватного staging и зашифровать:
   `age -r <public-recipient> -o <new-archive.age> <private-package>`.
   Оба файла шифруются, чтобы manifest не раскрывал структуру/источник вне хранилища.
4. Реальный decrypt drill: `age -d -i <private-key-path> -o <new-private-package> <archive.age>`;
   проверить exit0, безопасно распаковать только собственный package в новый private
   staging, выполнить `verify`, restore в новый UUID target и owner/PDF/receipt smoke.
   Проверить wrong key, tampered/truncated ciphertext, отсутствие частичных публикаций.
5. Только после успешного drill применять к рабочим backup. Plaintext staging
   удалять осознанно только после проверенной encrypted copy; на SSD secure erase
   отдельного файла не гарантируется, поэтому staging должен находиться на encrypted
   storage. Ключ/offsite recovery проверить с владельцем; ключ рядом с архивом недопустим.

H-04 не устанавливает age и не генерирует ключ владельца автоматически: безопасное
custody/offsite и выбор encrypted storage требуют отдельного решения. Временный ключ
в том же каталоге не закрывает риск. Критерии OPS-ENC: реальный encrypted roundtrip,
negative tests, pinned tool, инструкция lost-key/rotation и независимое хранение.
Не начинать эту отдельную задачу без указания; ограничение зарегистрировано R-12.

Предлагаемая локальная retention policy: backup перед каждым schema/release change
и ежедневно при включённом компьютере; хранить7 daily +4 weekly + последний проверенный
pre-upgrade snapshot до приёмки новой версии. Планировщик/уведомления и encrypted offsite
пока не настроены. Не удалять последнюю восстанавливаемую копию, единственный baseline,
legal-hold и текущий pre-upgrade backup. Удаление старых копий — ручное по inventory,
успешному restore-drill и решению владельца. Период уточняется перед пилотом.

Restore одно-базовый: cluster roles/ACL/DB settings/model volume/host disaster recovery
не покрыты. Копии служебных ролей и конфигурации отдельно защищать; не выгружать пароли
в публичный manifest. Правила [PostgreSQL dump](https://www.postgresql.org/docs/17/backup-dump.html)
и [restore](https://www.postgresql.org/docs/17/app-pgrestore.html) применимы только к
доверенному источнику: восстановление исполняет SQL из архива.
